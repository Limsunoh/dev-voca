"""문장 문제풀기 적대적 테스트.

구현자의 테스트와 별개로, 낱개 문제풀기 경로를 깨뜨릴 목적으로 쓴다.
확인하려는 계약은 넷이다.

1. 크로스 엔드포인트 - 문장 토큰이 단어 채점에서, 단어 토큰이 문장
   채점에서 어떻게 처리되는가. 토큰 salt 가 공용이라 서명만으로는 안 갈린다.
2. 검수 게이트 - 미검수 문장·단어가 문제·보기·해설에 새는가.
3. 입력 검증 - kind/category/exclude 에 무엇이 들어와도 500 이 아닌가.
4. 정답 노출 - 응답과 토큰에서 정답을 미리 알 수 있는가.
"""

import base64
import json
import re

from django.core import signing
from django.db.models import Q
from django.test import TestCase

from apps.learning import review

from .models import Sentence, Word
from .quiz import (
    _PLACE_WORD,
    _SCENE_END,
    TARGET_SENTENCE,
    TARGET_WORD,
    _is_place,
    make_situation_question,
    sign_question,
)

LIST_URL = "/api/vocab/sentences/"
QUIZ_URL = f"{LIST_URL}quiz/"
GRADE_URL = f"{LIST_URL}grade/"
WORD_QUIZ_URL = "/api/vocab/words/quiz/"
WORD_GRADE_URL = "/api/vocab/words/grade/"


def decode_token(token: str) -> dict:
    """토큰 앞부분을 base64 로 풀어 알맹이를 본다.

    signing.dumps 는 서명일 뿐 암호화가 아니다. 공격자가 무엇을 볼 수
    있는지 확인하려면 우리도 같은 방법으로 봐야 한다.
    """
    raw = token.split(":")[0]
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode())


class QuizFixtureMixin:
    """문제를 낼 수 있을 만큼의 최소 데이터.

    보기가 4개라 정답 1 + 오답 3 이 필요하고, 빈칸 문제는 문장 안에
    단어가 실제로 들어 있어야 만들어진다.
    """

    TERMS = ("commit", "rebase", "stash", "merge", "cherry")

    @classmethod
    def seed(cls, reviewed=True):
        cls.words = [
            Word.objects.create(
                term=term,
                meaning=f"{term} 뜻",
                description=f"{term} 설명",
                category="git",
                is_reviewed=reviewed,
            )
            for term in cls.TERMS
        ]
        cls.sentences = [
            Sentence.objects.create(
                text=f"Please {term} before you push.",
                translation=f"{term} 하세요",
                context=f"{term} 하라고 할 때",
                description=f"{term} 문장 설명",
                category="git",
                is_reviewed=reviewed,
            )
            for term in cls.TERMS
        ]

    def answer_of(self, token: str) -> int:
        """채점을 한 번 불러 정답 id 를 받아온다. 틀린 답을 보낸다."""
        graded = self.client.post(
            GRADE_URL, {"token": token, "picked": -1}, content_type="application/json"
        )
        return graded.json()["answer_id"]


class CrossEndpointTokenTest(QuizFixtureMixin, TestCase):
    """토큰을 남의 채점 엔드포인트로 보낸다.

    salt 가 vocab.quiz.answer 하나라 서명 검증은 양쪽 다 통과한다.
    갈리는 유일한 근거가 payload 의 at 이므로, 그게 실제로 막는지 본다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_sentence_token_rejected_by_word_grade(self):
        """상황 고르기 토큰을 단어 채점에 보내면 400."""
        res = self.client.get(QUIZ_URL, {"kind": "situation"})
        self.assertEqual(res.status_code, 200)
        body = res.json()

        cross = self.client.post(
            WORD_GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(cross.status_code, 400, cross.content)
        self.assertNotIn("word", cross.json())

    def test_word_token_graded_as_word_on_sentence_endpoint(self):
        """단어 토큰을 문장 채점에 보내도 문장 표를 뒤지지 않는다.

        at 이 word 이므로 문장 grade 도 Word 를 조회해야 한다. 여기서
        Sentence 를 뒤지면 같은 번호의 엉뚱한 문장이 정답으로 나온다.
        """
        res = self.client.get(WORD_QUIZ_URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()

        cross = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(cross.status_code, 200, cross.content)
        graded = cross.json()
        self.assertEqual(graded["answer_type"], TARGET_WORD)
        self.assertIn("word", graded)
        self.assertNotIn("sentence", graded)

    def test_blank_token_on_word_grade_returns_the_same_word(self):
        """빈칸 토큰은 정답이 단어라 단어 채점에서도 유효하다.

        막을 것이 아니라 확인해 둘 것이다 - 여기서 나오는 단어는 보기
        안의 정답이지 임의 pk 조회가 아니다.
        """
        res = self.client.get(QUIZ_URL, {"kind": "blank"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["answer_type"], TARGET_WORD)

        cross = self.client.post(
            WORD_GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(cross.status_code, 200)
        self.assertIn(cross.json()["answer_id"], [c["id"] for c in body["choices"]])

    def test_forged_answer_type_needs_secret_key(self):
        """at 만 바꿔치기하려면 서명을 다시 해야 한다 - 서명 없이는 400."""
        res = self.client.get(QUIZ_URL, {"kind": "situation"})
        token = res.json()["token"]
        payload = decode_token(token)
        payload["at"] = TARGET_WORD

        head = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        tampered = ":".join([head, *token.split(":")[1:]])

        graded = self.client.post(
            WORD_GRADE_URL,
            {"token": tampered, "picked": 1},
            content_type="application/json",
        )

        self.assertEqual(graded.status_code, 400)

    def test_sentence_answer_id_cannot_probe_word_table(self):
        """문장 pk 를 정답으로 서명한 토큰으로 단어 표를 훑을 수 없다.

        보기 넷을 돌려가며 부르면 pk 로 표를 훑는 통로가 되는데, 종류
        검사가 그걸 막는다.
        """
        sentence = self.sentences[0]
        token = sign_question(
            sentence.pk, [sentence.pk, 9991, 9992, 9993], answer_type=TARGET_SENTENCE
        )

        res = self.client.post(
            WORD_GRADE_URL,
            {"token": token, "picked": sentence.pk},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)


class ReviewGateTest(QuizFixtureMixin, TestCase):
    """미검수 항목이 문제·보기·해설 어디에도 안 나오는지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_quiz_404_when_all_sentences_unreviewed(self):
        """문장을 전부 미검수로 내리면 문제를 못 낸다."""
        Sentence.objects.update(is_reviewed=False)

        res = self.client.get(QUIZ_URL)

        self.assertEqual(res.status_code, 404)

    def test_unreviewed_sentence_never_in_situation_question(self):
        """미검수 문장이 상황 보기·지문 어디에도 안 섞인다."""
        hidden = Sentence.objects.create(
            text="Secret unreviewed sentence.",
            translation="비밀",
            context="아직 검수 안 된 상황",
            category="git",
            is_reviewed=False,
        )

        for _ in range(30):
            res = self.client.get(QUIZ_URL, {"kind": "situation"})
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertNotIn(hidden.pk, [c["id"] for c in body["choices"]])
            self.assertNotIn(hidden.context, [c["text"] for c in body["choices"]])
            self.assertNotEqual(body["prompt"], hidden.text)

    def test_unreviewed_word_never_in_blank_choices(self):
        """미검수 단어가 빈칸 보기로 안 섞인다."""
        hidden = Word.objects.create(
            term="unreviewedterm",
            meaning="비밀 뜻",
            category="git",
            is_reviewed=False,
        )

        for _ in range(30):
            res = self.client.get(QUIZ_URL, {"kind": "blank"})
            self.assertEqual(res.status_code, 200)
            choices = res.json()["choices"]
            self.assertNotIn(hidden.pk, [c["id"] for c in choices])
            self.assertNotIn(hidden.term, [c["text"] for c in choices])

    def test_unreviewed_sentence_never_becomes_blank_prompt(self):
        """미검수 문장이 빈칸 지문으로도 안 나온다."""
        hidden = Sentence.objects.create(
            text="Please commit this unreviewed line.",
            translation="비밀",
            context="비밀 상황",
            category="git",
            is_reviewed=False,
        )

        for _ in range(30):
            res = self.client.get(QUIZ_URL, {"kind": "blank"})
            self.assertEqual(res.status_code, 200)
            self.assertNotEqual(res.json()["source_sentence_id"], hidden.pk)

    def test_grade_404_when_sentence_unreviewed_after_issue(self):
        """문제를 낸 뒤 검수가 취소되면 정답을 안 보여준다."""
        res = self.client.get(QUIZ_URL, {"kind": "situation"})
        body = res.json()
        Sentence.objects.update(is_reviewed=False)

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(graded.status_code, 404)
        self.assertNotIn("sentence", graded.json())

    def test_grade_404_when_blank_answer_word_unreviewed_after_issue(self):
        """빈칸 문제도 같다 - 정답 단어의 검수가 풀리면 해설을 안 준다."""
        res = self.client.get(QUIZ_URL, {"kind": "blank"})
        body = res.json()
        Word.objects.update(is_reviewed=False)

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(graded.status_code, 404)
        self.assertNotIn("word", graded.json())

    def test_grade_body_hides_review_workflow_fields(self):
        """채점 응답에 is_reviewed·source 가 안 실린다."""
        for kind in ("situation", "blank"):
            with self.subTest(kind=kind):
                res = self.client.get(QUIZ_URL, {"kind": kind})
                body = res.json()

                graded = self.client.post(
                    GRADE_URL,
                    {"token": body["token"], "picked": body["choices"][0]["id"]},
                    content_type="application/json",
                )

                flat = json.dumps(graded.json(), ensure_ascii=False)
                self.assertNotIn("is_reviewed", flat)
                self.assertNotIn("source", flat)
                self.assertNotIn("created_by", flat)

    def test_quiz_body_hides_review_workflow_fields(self):
        """출제 응답에도 검수 정보가 없다.

        source_sentence_id 는 출처(source) 필드가 아니라 문장 id 라
        따로 본다.
        """
        res = self.client.get(QUIZ_URL)

        body = res.json()
        self.assertNotIn("is_reviewed", json.dumps(body, ensure_ascii=False))
        self.assertNotIn("source", body)
        self.assertNotIn("created_by", body)


class AnswerLeakTest(QuizFixtureMixin, TestCase):
    """정답을 화면 전에 알 수 있는지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_quiz_response_has_no_answer_id(self):
        """응답 어디에도 정답 id 를 가리키는 키가 없다."""
        for kind in ("situation", "blank"):
            with self.subTest(kind=kind):
                body = self.client.get(QUIZ_URL, {"kind": kind}).json()

                self.assertNotIn("answer_id", body)
                self.assertNotIn("answer", body)

    def test_situation_prompt_is_not_a_choice(self):
        """지문(문장)과 보기(상황)가 겹치면 그 자체가 답이 된다."""
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        self.assertNotIn(body["prompt"], [c["text"] for c in body["choices"]])

    def test_situation_choices_are_all_distinct(self):
        """보기 둘이 같으면 4지선다가 사실상 2지선다가 된다."""
        for _ in range(20):
            body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
            texts = [c["text"] for c in body["choices"]]

            self.assertEqual(len(set(texts)), len(texts))

    def test_token_payload_does_not_contain_answer_id(self):
        """토큰을 base64 로 풀어도 정답 id 가 안 보인다."""
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
        payload = decode_token(body["token"])

        # 담긴 키는 지문(a), nonce(n), 보기(c), 정답 종류(at) 뿐이다.
        self.assertEqual(set(payload), {"a", "n", "c", "at"})
        # 보기는 정렬돼 있어 담긴 순서가 단서가 되지 않는다.
        self.assertEqual(payload["c"], sorted(payload["c"]))
        self.assertEqual(payload["c"], sorted(c["id"] for c in body["choices"]))
        # 지문은 되돌릴 수 없는 값이다. 정답 id 를 알고 있어도 nonce 없이는
        # 같은 지문을 못 만들고, nonce 를 알아도 SECRET_KEY 가 있어야 한다.
        answer_id = self.answer_of(body["token"])
        self.assertNotEqual(payload["a"], str(answer_id))
        self.assertEqual(len(payload["a"]), 64)

    def test_same_answer_gives_different_fingerprint_each_time(self):
        """같은 정답이라도 문제마다 지문이 다르다 - 대조로 못 알아낸다."""
        seen = set()
        for _ in range(10):
            body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
            seen.add(decode_token(body["token"])["a"])

        self.assertEqual(len(seen), 10)

    def test_grade_result_does_not_expose_other_choices(self):
        """채점은 정답 하나만 알려준다 - 나머지 보기의 내용은 안 준다."""
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": -1},
            content_type="application/json",
        ).json()

        self.assertFalse(graded["correct"])
        self.assertIn(graded["answer_id"], [c["id"] for c in body["choices"]])
        self.assertEqual(graded["sentence"]["id"], graded["answer_id"])


class SituationChoiceKindTest(TestCase):
    """보기가 장면과 자리로 섞이는지.

    context 에는 성격이 다른 둘이 들어 있다 - "회의가 길어질 때" 는 장면,
    "운영체제 교재" 는 자리다. 한 문제에 섞이면 혼자 종류가 다른 것이
    눈에 띄어 답이 아닌 것부터 지워진다.
    """

    @classmethod
    def setUpTestData(cls):
        # 두 종류를 넉넉히 만든다. 한 종류가 넷을 못 채우면 문제 자체가
        # 안 만들어져 검사가 조용히 통과한다.
        cls.places = [
            f"{name} 로그" for name in ("nginx", "Spring", "Django", "Node")
        ]
        cls.scenes = [
            f"{what} 할 때" for what in ("배포", "리뷰", "회의", "장애 대응")
        ]
        for i, context in enumerate([*cls.places, *cls.scenes]):
            Sentence.objects.create(
                text=f"Sentence number {i} here.",
                translation=f"문장 {i}",
                context=context,
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )

    def test_choices_never_mix_places_with_scenes(self):
        """보기 넷은 전부 장면이거나 전부 자리다."""
        for _ in range(30):
            question = make_situation_question(Sentence.objects.visible())
            self.assertIsNotNone(question, "문제를 못 만들었다")

            kinds = {_is_place(c.text) for c in question.choices}

            self.assertEqual(
                len(kinds), 1, f"섞였다: {[c.text for c in question.choices]}"
            )

    def test_seed_data_choices_do_not_mix_by_sentence_ending(self):
        """시드 데이터로, **구현과 다른 기준**으로 섞임을 본다.

        위 검사는 `_is_place` 로 섞였는지를 판정한다 - 구현이 쓰는 함수와
        같아서, 그 함수의 판정이 틀려도 늘 통과한다(동어반복). 실제로
        낱말만 보던 때 "화면이 덜컹거릴 때" 를 자리로 오분류했는데 그
        검사는 초록이었다.

        여기서는 **어미**로 본다. "~때/경우/중" 으로 끝나면 문법적으로
        장면이 확실하다. 그런 값이 자리형 문제(보기가 전부 자리라고 보고
        "어디서 보이나?" 로 묻는 문제)에 끼면 안 된다.

        반대 방향은 안 본다. 어미가 "~때" 가 아니어도 장면인 값이 있다
        ("릴리스 준비 대화"·"npm install 실행 시" 같은 것이 31개). 그래서
        "어미가 다르면 섞인 것" 으로 보면 멀쩡한 문제를 틀렸다고 한다.
        """
        from .management.commands.seed_sentences import SENTENCES

        # **앞에서 자르면 안 된다.** 처음에는 `SENTENCES[:60]` 을 썼는데
        # 그 안에 자리형이 하나도 없어서, 아래 루프가 매번 continue 로
        # 빠지고 단언이 한 번도 안 돌았다. 어떤 구현을 넣어도 통과하는
        # 검사였다. 전부 넣고, 실제로 몇 번 봤는지도 세어 둔다.
        for i, row in enumerate(SENTENCES):
            context = row[6]
            if not context:
                continue
            Sentence.objects.create(
                text=f"Seeded sentence {i}.",
                translation=f"해석 {i}",
                context=context,
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )

        scene_end = re.compile(r"(때|경우|중|뒤|전|후|면)$")
        checked = 0
        for _ in range(60):
            question = make_situation_question(Sentence.objects.visible())
            if question is None or question.question != "이 말은 어디서 보이나?":
                continue
            checked += 1

            scenes = [c.text for c in question.choices if scene_end.search(c.text)]

            self.assertEqual(
                scenes,
                [],
                f"자리를 물었는데 장면이 보기에 있다: {[c.text for c in question.choices]}",
            )

        self.assertGreater(checked, 0, "자리형 문제가 한 번도 안 나와 검사가 헛돌았다")

    def test_question_wording_follows_the_choices(self):
        """보기가 자리면 묻는 말도 자리를 묻는다.

        "이 말이 나오는 상황은?" 에 "nginx 에러 로그" 가 보기로 나오면
        묻는 말과 답이 어긋난다.
        """
        seen = {}
        for _ in range(40):
            question = make_situation_question(Sentence.objects.visible())
            place = _is_place(question.choices[0].text)
            seen[place] = question.question

        self.assertIn(True, seen, "자리형 문제가 한 번도 안 나왔다")
        self.assertIn(False, seen, "장면형 문제가 한 번도 안 나왔다")
        self.assertNotEqual(seen[True], seen[False])

    def test_falls_back_to_mixed_choices_rather_than_no_question(self):
        """한 종류로 넷을 못 채우면 섞어서라도 낸다.

        복습은 틀린 문장을 정답으로 지정해 부른다. 여기서 None 을 내면
        그 문장이 복습에 영영 안 나와서, 보기가 섞이는 것보다 나쁘다.
        """
        # 자리형은 하나뿐이라 같은 종류로는 넷을 못 채운다.
        Sentence.objects.all().delete()
        contexts = ["nginx 로그", "배포할 때", "리뷰할 때", "회의할 때"]
        for i, context in enumerate(contexts):
            Sentence.objects.create(
                text=f"Only sentence {i} here.",
                translation=f"문장 {i}",
                context=context,
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )
        only_place = Sentence.objects.get(context="nginx 로그")

        question = make_situation_question(
            Sentence.objects.visible(), answer=only_place
        )

        self.assertIsNotNone(question, "자리형이 하나뿐이라고 문제를 못 내면 안 된다")
        self.assertIn(only_place.pk, [c.id for c in question.choices])
        # 섞였으면 자리를 묻지 않는다. 보기 넷 중 셋이 장면이라 말이 안 맞는다.
        self.assertEqual(question.question, "이 말이 나오는 상황은?")

    def test_place_questions_are_actually_produced(self):
        """자리형이 적어도 쿼리에서 걸러 셋을 채울 수 있어야 한다.

        종류를 파이썬에서 거르면 표본에 자리형이 셋 미만인 경우가 생겨
        문제가 None 이 되고, 이 유형이 조용히 사라진다.
        """
        # 자리형인지를 `_is_place` 로 세지 않는다. 그건 구현이 쓰는 함수라
        # 판정이 틀려도 같이 틀린다. 사용자가 실제로 보는 것, 즉 묻는 말로
        # 센다.
        made = 0
        for _ in range(40):
            question = make_situation_question(Sentence.objects.visible())
            if question is not None and question.question == "이 말은 어디서 보이나?":
                made += 1

        self.assertGreater(made, 0, "자리형 문제가 하나도 안 나왔다")

    def test_python_and_postgres_split_the_same_way(self):
        """_is_place 와 쿼리 필터가 같은 값을 자리로 봐야 한다.

        판정이 두 곳에 나뉘어 있다 - 묻는 말은 파이썬 `_is_place` 가
        정하고, 보기는 Postgres `context__regex` 가 뽑는다. 둘이 갈리면
        "어디서 보이나" 라고 묻고 장면을 보기로 주는 문제가 조용히 나온다.

        Postgres 정규식에는 부정 선행 검사가 없어 filter/exclude 를 겹쳐
        흉내 낸 자리라, 어느 한쪽만 고치면 바로 어긋난다.

        **자리 낱말을 가지면서 장면 어미로 끝나는 값**을 반드시 넣는다 -
        "로그를 볼 때" 처럼 두 규칙이 동시에 걸리는 값만이 어미 검사가
        빠졌는지 드러낸다. 깨끗한 값만 있으면 둘 다 같은 답을 내서
        검사가 조용히 통과한다.
        """
        for i, context in enumerate(
            ["로그를 볼 때", "화면이 덜컹거릴 때", "응답을 파싱할 때", "문서를 고칠 경우"]
        ):
            Sentence.objects.create(
                text=f"Ambiguous context sentence {i} here.",
                translation=f"섞인 상황 {i}",
                context=context,
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )

        pool = Sentence.objects.visible().exclude(context="")
        place_ids = set(
            pool.filter(context__regex=_PLACE_WORD.pattern)
            .exclude(context__regex=_SCENE_END.pattern)
            .values_list("pk", flat=True)
        )
        scene_ids = set(
            pool.exclude(
                Q(context__regex=_PLACE_WORD.pattern)
                & ~Q(context__regex=_SCENE_END.pattern)
            ).values_list("pk", flat=True)
        )

        disagree = [
            s.context for s in pool if _is_place(s.context) != (s.pk in place_ids)
        ]

        self.assertEqual(disagree, [], f"판정이 갈리는 상황 {len(disagree)}개")
        # 한쪽에만 들어가야 한다. 겹치면 장면이 자리형 보기로도 뽑힌다.
        self.assertEqual(place_ids & scene_ids, set(), "두 종류에 겹쳐 들어간 문장")

    def test_odd_context_values_do_not_break_the_query(self):
        """context 가 정규식 메타문자여도 500 이 아니라 문제이거나 None 이다.

        이 값은 `context__regex` 로 Postgres 정규식에 들어간다. 관리자가
        "[" 나 "\\" 하나만 넣어도 쿼리가 터지면 문제 내기 경로 전체가
        죽는다. 값 자체는 쿼리의 **대상**이지 패턴이 아니므로 터지면 안 된다.
        """
        odd = [
            " ",
            ".*",
            "[",
            "\\",
            "a{2,",
            "|",
            "^$",
            "[[:alpha:]]",
            "Description",  # 자리 낱말이 통째로 든 값
            "로그를 볼 때",  # 자리 낱말 + 장면 어미
            "가" * 200,  # 칸 최대 길이
        ]
        for i, context in enumerate(odd):
            Sentence.objects.create(
                text=f"Odd context sentence {i} here.",
                translation=f"이상한 상황 {i}",
                context=context,
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )

        for sentence in Sentence.objects.visible().exclude(context=""):
            with self.subTest(context=sentence.context[:20]):
                make_situation_question(
                    Sentence.objects.visible(), answer=sentence
                )

    def test_review_can_still_ask_a_lone_place_sentence(self):
        """자리형이 하나뿐이어도 복습이 그 문장을 낼 수 있어야 한다.

        위 폴백 테스트는 make_situation_question 을 직접 부르지만, 복습은
        review._make_for 를 거쳐 온다. 거기서 None 이 되면 틀린 문장이
        복습 목록에만 남고 화면에는 영영 안 나온다.
        """
        Sentence.objects.all().delete()
        lone = Sentence.objects.create(
            text="Check the nginx access log first.",
            translation="먼저 로그를 보라",
            context="nginx 로그",
            description="설명",
            category="git",
            is_reviewed=True,
        )
        for i in range(5):
            Sentence.objects.create(
                text=f"Scene sentence {i} goes here.",
                translation=f"장면 {i}",
                context=f"{i}번 배포할 때",
                description=f"설명 {i}",
                category="git",
                is_reviewed=True,
            )

        question = review._make_for(TARGET_SENTENCE, lone.pk)

        self.assertIsNotNone(question, "복습이 이 문장을 영영 못 낸다")
        self.assertIn(lone.pk, [c.id for c in question.choices])
        # 섞였으면 자리를 묻지 않는다 - 물으면 장면인 오답 셋이 먼저 지워진다.
        if len({_is_place(c.text) for c in question.choices}) != 1:
            self.assertEqual(question.question, "이 말이 나오는 상황은?")

    def test_too_few_sentences_yields_no_question_not_a_crash(self):
        """보기를 못 채우면 None 이다. 폴백이 있어도 없는 보기를 지어내지 않는다."""
        Sentence.objects.all().delete()
        answer = Sentence.objects.create(
            text="Only one place sentence here.",
            translation="하나뿐",
            context="nginx 로그",
            description="설명",
            category="git",
            is_reviewed=True,
        )
        Sentence.objects.create(
            text="Second place sentence here.",
            translation="둘",
            context="Django 로그",
            description="설명",
            category="git",
            is_reviewed=True,
        )

        self.assertIsNone(
            make_situation_question(Sentence.objects.visible(), answer=answer)
        )


class QuizParamValidationTest(QuizFixtureMixin, TestCase):
    """kind/category/exclude 에 무엇이 들어와도 500 이 아닌지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_word_kind_rejected_on_sentence_quiz(self):
        """단어 유형(meaning)은 문장 문제에 없다 - 400."""
        for kind in ("meaning", "term", "description"):
            with self.subTest(kind=kind):
                res = self.client.get(QUIZ_URL, {"kind": kind})
                self.assertEqual(res.status_code, 400)

    def test_unknown_kind_rejected(self):
        res = self.client.get(QUIZ_URL, {"kind": "nope"})
        self.assertEqual(res.status_code, 400)

    def test_empty_kind_falls_back_to_random(self):
        """빈 문자열은 안 준 것과 같다 - 400 이 아니라 정상 출제."""
        res = self.client.get(QUIZ_URL, {"kind": ""})
        self.assertEqual(res.status_code, 200)

    def test_long_kind_rejected_not_crashed(self):
        res = self.client.get(QUIZ_URL, {"kind": "a" * 5000})
        self.assertEqual(res.status_code, 400)

    def test_repeated_kind_param_is_validated(self):
        """?kind=blank&kind=meaning - 어느 값을 읽든 검증은 받아야 한다."""
        res = self.client.get(f"{QUIZ_URL}?kind=blank&kind=meaning")
        self.assertIn(res.status_code, (200, 400))
        if res.status_code == 200:
            self.assertEqual(res.json()["kind"], "blank")

    def test_unknown_category_rejected(self):
        res = self.client.get(QUIZ_URL, {"category": "no_such"})
        self.assertEqual(res.status_code, 400)

    def test_long_category_rejected_not_crashed(self):
        res = self.client.get(QUIZ_URL, {"category": "x" * 5000})
        self.assertEqual(res.status_code, 400)

    def test_null_byte_in_params_does_not_crash(self):
        """널바이트는 Postgres 가 거절한다 - 500 이 나면 안 된다."""
        for param in ("kind", "category"):
            with self.subTest(param=param):
                res = self.client.get(QUIZ_URL, {param: "a\x00b"})
                self.assertEqual(res.status_code, 400)

    def test_category_narrowed_to_empty_pool_is_404(self):
        """유효한 분류인데 그 안에 문장이 없으면 404 로 안내한다.

        400(없는 분류)과 갈라야 한다. 화면이 둘을 같게 다루면 "분류를
        넓혀보세요" 안내가 엉뚱한 자리에서 뜬다.
        """
        res = self.client.get(QUIZ_URL, {"category": "frontend"})

        self.assertEqual(res.status_code, 404)
        self.assertIn("detail", res.json())

    def test_exclude_garbage_does_not_crash(self):
        """음수·거대 수·문자·빈 조각 어느 것도 500 이 아니다."""
        cases = [
            "-1",
            "9" * 30,
            "abc",
            "1,,2",
            ",",
            "1.5",
            "٣",
            "²",
            "0x10",
            " 1 , 2 ",
            "null",
            "1;DROP TABLE vocab_sentence",
            "-9223372036854775809",
        ]
        for raw in cases:
            with self.subTest(exclude=raw):
                res = self.client.get(QUIZ_URL, {"exclude": raw})
                self.assertIn(res.status_code, (200, 404), f"{raw} -> {res.status_code}")

    def test_exclude_5000_ids_does_not_crash(self):
        res = self.client.get(
            QUIZ_URL, {"exclude": ",".join(str(i) for i in range(5000))}
        )
        self.assertIn(res.status_code, (200, 404))

    def test_exclude_all_sentences_yields_404_not_500(self):
        """전부 제외하면 낼 문제가 없다 - 404 로 안내가 나가야 한다."""
        ids = ",".join(str(s.pk) for s in Sentence.objects.all())

        res = self.client.get(QUIZ_URL, {"exclude": ids, "kind": "situation"})

        self.assertEqual(res.status_code, 404)
        self.assertIn("detail", res.json())

    def test_quiz_does_not_accept_post(self):
        """출제는 GET 전용.

        401 이 나오는 것은 SAFE_POST_ACTIONS 에 quiz 가 없어서다 -
        인증 검사가 메서드 검사보다 먼저 돈다. 200 만 아니면 된다.
        """
        res = self.client.post(QUIZ_URL, {}, content_type="application/json")
        self.assertIn(res.status_code, (401, 403, 405))


class GradeInputTest(QuizFixtureMixin, TestCase):
    """채점 본문에 무엇이 와도 500 이 아닌지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_non_dict_body_rejected(self):
        for body in ("[]", '"x"', "1", "null", "true"):
            with self.subTest(body=body):
                res = self.client.post(GRADE_URL, body, content_type="application/json")
                self.assertEqual(res.status_code, 400, body)

    def test_broken_json_is_400(self):
        res = self.client.post(GRADE_URL, "{", content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_missing_or_wrong_type_token_is_400(self):
        for token in (None, 1, [], {}, True):
            with self.subTest(token=token):
                res = self.client.post(
                    GRADE_URL,
                    {"token": token, "picked": 1},
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 400)

    def test_picked_true_is_not_treated_as_choice_one(self):
        """True 는 int 라 1 번 보기를 고른 것으로 처리되면 안 된다."""
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
        answer_id = self.answer_of(body["token"])
        if answer_id == 1:
            self.skipTest("정답 pk 가 1 이라 이 대조로는 못 가린다")

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": True},
            content_type="application/json",
        )

        self.assertEqual(graded.status_code, 200)
        self.assertFalse(graded.json()["correct"])

    def test_picked_weird_types_do_not_crash(self):
        token = self.client.get(QUIZ_URL, {"kind": "situation"}).json()["token"]
        for picked in ("1", 1.5, None, [], {}, 10**30, -(10**30)):
            with self.subTest(picked=picked):
                graded = self.client.post(
                    GRADE_URL,
                    {"token": token, "picked": picked},
                    content_type="application/json",
                )
                self.assertEqual(graded.status_code, 200)
                self.assertFalse(graded.json()["correct"])

    def test_garbage_token_is_400(self):
        for token in ("", "x", "a:b:c", "." * 100, "9" * 5000):
            with self.subTest(token=token):
                res = self.client.post(
                    GRADE_URL,
                    {"token": token, "picked": 1},
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 400)

    def test_signed_but_wrong_salt_is_400(self):
        """다른 용도로 서명된 값은 여기서 안 풀린다."""
        token = signing.dumps(
            {"a": "x", "n": "y", "c": [1], "at": "sentence"}, salt="other"
        )

        res = self.client.post(
            GRADE_URL, {"token": token, "picked": 1}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 400)

    def test_signed_payload_with_unknown_answer_type(self):
        """at 이 우리 값이 아니면 어느 표를 볼지 정할 수 없다.

        grade_answer 가 거절하므로(word 로 되돌리지 않는다) 표를 보는
        일 자체가 없다. 되돌리면 문장 pk 로 단어를 조회하게 되어, 같은
        번호의 엉뚱한 단어가 정답으로 뜬다.
        """
        token = sign_question(
            self.sentences[0].pk, [self.sentences[0].pk], answer_type="article"
        )

        res = self.client.post(
            GRADE_URL,
            {"token": token, "picked": self.sentences[0].pk},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertNotEqual(res.status_code, 500)

    def test_grade_is_post_only(self):
        """채점은 POST 전용. GET 으로는 토큰이 URL 과 서버 로그에 남는다."""
        res = self.client.get(GRADE_URL)
        self.assertEqual(res.status_code, 405)

    def test_grade_does_not_write(self):
        """이 경로는 DB 에 쓰지 않는다."""
        before = (Sentence.objects.count(), Word.objects.count())
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual((Sentence.objects.count(), Word.objects.count()), before)

    def test_regrading_same_token_is_stable(self):
        """같은 토큰을 여러 번 채점해도 정답이 흔들리지 않는다."""
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        answers = {self.answer_of(body["token"]) for _ in range(5)}

        self.assertEqual(len(answers), 1)


class ExcludeBehaviourTest(QuizFixtureMixin, TestCase):
    """exclude 가 실제로 그 문장을 막는지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_situation_exclude_blocks_that_sentence(self):
        """상황 문제의 answer_id 를 exclude 에 넣으면 다시 안 나온다."""
        first = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
        answer_id = self.answer_of(first["token"])

        for _ in range(20):
            res = self.client.get(
                QUIZ_URL, {"kind": "situation", "exclude": str(answer_id)}
            )
            self.assertEqual(res.status_code, 200)
            self.assertNotEqual(self.answer_of(res.json()["token"]), answer_id)

    def test_blank_exclude_uses_sentence_id_not_answer_id(self):
        """빈칸 문제는 source_sentence_id 로 걸러야 한다.

        정답은 단어 id 라 그걸 exclude 에 넣으면 문장이 안 걸러진다.
        화면(QuizBoard)이 그렇게 쓰고 있고, 백엔드가 그 값을 받아 실제로
        같은 문장을 막는지 확인한다.
        """
        body = self.client.get(QUIZ_URL, {"kind": "blank"}).json()
        source = body["source_sentence_id"]
        self.assertIsNotNone(source)

        for _ in range(20):
            again = self.client.get(QUIZ_URL, {"kind": "blank", "exclude": str(source)})
            self.assertEqual(again.status_code, 200)
            self.assertNotEqual(again.json()["source_sentence_id"], source)

    def test_sentence_exclude_reads_word_id_as_a_sentence_id(self):
        """exclude 는 문장 표에만 걸린다 - 단어 id 를 보내면 오해한다.

        두 표의 pk 가 같은 수열이라 단어 4번을 빼달라고 하면 문장 4번이
        빠진다. 그래서 화면이 빈칸 문제의 정답(단어 id)을 그대로 넣으면
        안 되고 source_sentence_id 를 넣어야 한다. 여기서 그 성질을
        못 박아둔다 - 이게 바뀌면 화면 쪽 분기를 다시 봐야 한다.
        """
        target = self.sentences[0]

        for _ in range(20):
            res = self.client.get(
                QUIZ_URL, {"kind": "situation", "exclude": str(target.pk)}
            )
            self.assertEqual(res.status_code, 200)
            self.assertNotEqual(self.answer_of(res.json()["token"]), target.pk)

    def test_blank_choices_are_word_ids(self):
        """빈칸 문제의 보기는 단어 id 다 - 문장 id 를 넣으면 안 된다."""
        body = self.client.get(QUIZ_URL, {"kind": "blank"}).json()
        choice_ids = {c["id"] for c in body["choices"]}
        word_ids = set(Word.objects.values_list("pk", flat=True))

        self.assertTrue(choice_ids <= word_ids)

    def test_situation_choices_are_sentence_ids(self):
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()
        choice_ids = {c["id"] for c in body["choices"]}
        sentence_ids = set(Sentence.objects.values_list("pk", flat=True))

        self.assertTrue(choice_ids <= sentence_ids)

    def test_situation_answer_type_is_sentence(self):
        res = self.client.get(QUIZ_URL, {"kind": "situation"})
        self.assertEqual(res.json()["answer_type"], TARGET_SENTENCE)

    def test_blank_answer_type_is_word(self):
        res = self.client.get(QUIZ_URL, {"kind": "blank"})
        self.assertEqual(res.json()["answer_type"], TARGET_WORD)

    def test_situation_has_no_source_sentence_id(self):
        """상황 문제는 answer_id 자체가 문장이라 따로 들고 있지 않는다."""
        res = self.client.get(QUIZ_URL, {"kind": "situation"})
        self.assertIsNone(res.json()["source_sentence_id"])


class BlankPromptTest(QuizFixtureMixin, TestCase):
    """빈칸 지문이 정답을 그대로 보여주지 않는지."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_prompt_masks_the_answer_term(self):
        for _ in range(20):
            body = self.client.get(QUIZ_URL, {"kind": "blank"}).json()
            graded = self.client.post(
                GRADE_URL,
                {"token": body["token"], "picked": -1},
                content_type="application/json",
            ).json()
            term = graded["word"]["term"]

            self.assertNotIn(term.lower(), body["prompt"].lower())
            self.assertIn("____", body["prompt"])

    def test_blank_explanation_is_a_word_not_a_sentence(self):
        """빈칸 문제의 해설은 단어여야 한다 - 문장이 오면 화면이 엉뚱해진다."""
        body = self.client.get(QUIZ_URL, {"kind": "blank"}).json()

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        self.assertEqual(graded["answer_type"], TARGET_WORD)
        self.assertIn("word", graded)
        self.assertNotIn("sentence", graded)
        self.assertIn("term", graded["word"])

    def test_situation_explanation_is_a_sentence(self):
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        graded = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": body["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        self.assertEqual(graded["answer_type"], TARGET_SENTENCE)
        self.assertIn("sentence", graded)
        self.assertNotIn("word", graded)
        self.assertIn("context", graded["sentence"])


class SentenceQuizPermissionTest(QuizFixtureMixin, TestCase):
    """익명으로 열려 있어야 할 것과 막혀 있어야 할 것."""

    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def test_anonymous_can_quiz_and_grade(self):
        res = self.client.get(QUIZ_URL)
        self.assertEqual(res.status_code, 200)

        graded = self.client.post(
            GRADE_URL,
            {"token": res.json()["token"], "picked": -1},
            content_type="application/json",
        )
        self.assertEqual(graded.status_code, 200)

    def test_anonymous_cannot_create_sentence(self):
        """grade 를 익명 POST 로 열었다고 목록 POST 까지 열리면 안 된다."""
        res = self.client.post(
            LIST_URL,
            {"text": "hack", "translation": "해킹"},
            content_type="application/json",
        )
        self.assertIn(res.status_code, (401, 403))

    def test_anonymous_cannot_patch_sentence(self):
        res = self.client.patch(
            f"{LIST_URL}{self.sentences[0].pk}/",
            {"text": "changed"},
            content_type="application/json",
        )
        self.assertIn(res.status_code, (401, 403))

    def test_anonymous_cannot_delete_sentence(self):
        res = self.client.delete(f"{LIST_URL}{self.sentences[0].pk}/")
        self.assertIn(res.status_code, (401, 403))

    def test_bad_pk_on_detail_is_404_not_500(self):
        for pk in ("9" * 30, "abc", "-1", "0", "1.5"):
            with self.subTest(pk=pk):
                res = self.client.get(f"{LIST_URL}{pk}/")
                self.assertEqual(res.status_code, 404, f"{pk} -> {res.status_code}")
