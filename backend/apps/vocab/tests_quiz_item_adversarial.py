"""?item= 문제 내기의 경계.

tests_quiz_item.py 가 "그 항목이 정답인가" 를 본다면, 여기는 그 항목이
문제를 낼 수 없는 모양일 때(설명 없음, 단어가 안 든 문장, 상황 빈칸),
분류와 겹칠 때, 풀이 모자랄 때, 그리고 **검수 안 된 것이 보기나 정답으로
끼어드는지**를 본다.

무작위 출제라 한 번 통과는 우연일 수 있다. 결과가 갈릴 수 있는 곳은
여러 번 부른다.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Sentence, Word
from .quiz import QuizKind
from .tests_sentence_quiz_adversarial import (
    GRADE_URL as SENTENCE_GRADE_URL,
)
from .tests_sentence_quiz_adversarial import (
    QUIZ_URL as SENTENCE_QUIZ_URL,
)
from .tests_sentence_quiz_adversarial import (
    WORD_GRADE_URL,
    WORD_QUIZ_URL,
    decode_token,
)

# 여러 번 불러 무작위가 한쪽으로 쏠린 우연을 걸러낸다.
REPEAT = 12

# 응답에 있어야 하는 키. 여기 없는 것이 붙으면(정답 id, 검수 상태 등) 샌다.
WORD_KEYS = {"kind", "kind_label", "question", "prompt", "category", "category_label", "choices", "token"}
SENTENCE_KEYS = WORD_KEYS | {"answer_type", "source_sentence_id"}


def make_word(term: str, **extra) -> Word:
    fields = {
        "meaning": f"{term} 뜻",
        "description": f"{term} is described here.",
        "category": "git",
        "is_reviewed": True,
    }
    fields.update(extra)
    return Word.objects.create(term=term, **fields)


def make_sentence(text: str, **extra) -> Sentence:
    fields = {
        "translation": "번역",
        "context": f"{text} 할 때",
        "category": "git",
        "is_reviewed": True,
    }
    fields.update(extra)
    return Sentence.objects.create(text=text, **fields)


class ItemQuizMixin:
    """부르고 채점해 정답 id 를 받는 도우미."""

    def quiz(self, url: str, **params):
        return self.client.get(url, params)

    def answer_of(self, grade_url: str, body: dict) -> int:
        graded = self.client.post(
            grade_url, {"token": body["token"], "picked": -1}, content_type="application/json"
        )
        self.assertEqual(graded.status_code, 200, graded.content)
        return graded.json()["answer_id"]


class WordItemKindTest(ItemQuizMixin, TestCase):
    """단어 항목 + 유형 조합."""

    @classmethod
    def setUpTestData(cls):
        cls.plain = make_word("stash", description="")
        cls.described = make_word("rebase", description="Rebase moves commits onto another base.")
        cls.others = [make_word(t) for t in ("commit", "merge", "cherry")]

    def test_description_kind_without_description_falls_back(self):
        """설명 없는 단어로 설명 문제를 청하면 다른 단어 유형으로 낸다.

        빈 지문으로 내거나 404 를 내면 그 단어의 "이 단어로 문제 풀기" 가
        영영 안 된다. 정답은 여전히 그 단어다.
        """
        for _ in range(REPEAT):
            res = self.quiz(WORD_QUIZ_URL, item=self.plain.pk, kind="description")
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            self.assertIn(body["kind"], (QuizKind.MEANING, QuizKind.TERM))
            self.assertTrue(body["prompt"].strip())
            self.assertEqual(self.answer_of(WORD_GRADE_URL, body), self.plain.pk)

    def test_description_kind_hides_the_term(self):
        """설명 문제 지문에 정답 단어가 그대로 남으면 읽기만 해도 풀린다."""
        res = self.quiz(WORD_QUIZ_URL, item=self.described.pk, kind="description")
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["kind"], QuizKind.DESCRIPTION)
        self.assertNotIn("rebase", body["prompt"].lower())

    def test_sentence_kind_on_word_endpoint_stays_word_kind(self):
        """단어 쪽에 문장 유형을 보내도 단어 유형으로 낸다 - 묻는 말과 지문이
        어긋나면 "이 말이 나오는 상황은?" 에 뜻 보기가 붙는다."""
        for kind in ("blank", "situation", "nonsense"):
            res = self.quiz(WORD_QUIZ_URL, item=self.described.pk, kind=kind)
            self.assertEqual(res.status_code, 200, (kind, res.content))
            body = res.json()
            self.assertIn(body["kind"], QuizKind.WORD_KINDS)
            self.assertEqual(self.answer_of(WORD_GRADE_URL, body), self.described.pk)

    def test_item_choices_are_four_distinct_ids_including_item(self):
        for _ in range(REPEAT):
            body = self.quiz(WORD_QUIZ_URL, item=self.plain.pk).json()
            ids = [c["id"] for c in body["choices"]]
            self.assertEqual(len(ids), 4)
            self.assertEqual(len(set(ids)), 4)
            self.assertIn(self.plain.pk, ids)


class WordItemReviewGateTest(ItemQuizMixin, TestCase):
    """검수 안 된 단어가 보기로라도 끼면 안 된다.

    정답만 막고 보기는 안 막으면, 검수 안 된 뜻이 오답 보기로 화면에 뜬다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.target = make_word("commit")
        cls.reviewed = [cls.target, *(make_word(t) for t in ("merge", "rebase", "stash"))]
        cls.hidden = [
            make_word(f"hidden{i}", meaning=f"미검수 뜻 {i}", is_reviewed=False) for i in range(8)
        ]

    def test_distractors_are_reviewed_only(self):
        allowed = {w.pk for w in self.reviewed}
        for _ in range(REPEAT):
            res = self.quiz(WORD_QUIZ_URL, item=self.target.pk)
            self.assertEqual(res.status_code, 200, res.content)
            ids = {c["id"] for c in res.json()["choices"]}
            self.assertEqual(ids, allowed)
            self.assertNotIn("미검수", res.content.decode())

    def test_three_reviewed_is_404_even_with_many_unreviewed(self):
        """검수된 것이 넷이 안 되면 미검수로 보기를 채우지 않고 못 낸다."""
        self.reviewed[3].is_reviewed = False
        self.reviewed[3].save(update_fields=["is_reviewed"])
        res = self.quiz(WORD_QUIZ_URL, item=self.target.pk)
        self.assertEqual(res.status_code, 404)

    def test_staff_gets_same_404_for_unreviewed_item(self):
        """검수자로 로그인해도 미검수 단어로 문제를 내지 않는다. 목록에서 미검수를
        보여주는 건 검수하라는 것이지 학습하라는 것이 아니다."""
        staff = get_user_model().objects.create_user(
            email="staff@example.com", password="pw-12345678", is_staff=True
        )
        self.client.force_login(staff)
        hidden = self.quiz(WORD_QUIZ_URL, item=self.hidden[0].pk)
        missing = self.quiz(WORD_QUIZ_URL, item=987654)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json(), missing.json())

    def test_response_has_no_answer_field(self):
        """정답 id 나 검수 정보가 응답에 붙지 않는다. 토큰에도 정답 id 가 날것으로
        없다(base64 로 풀면 보이므로)."""
        body = self.quiz(WORD_QUIZ_URL, item=self.target.pk).json()
        self.assertEqual(set(body), WORD_KEYS)
        for choice in body["choices"]:
            self.assertEqual(set(choice), {"id", "text"})
        payload = decode_token(body["token"])
        self.assertNotIn(self.target.pk, payload.values())
        self.assertNotEqual(payload["a"], str(self.target.pk))


class WordItemCategoryTest(ItemQuizMixin, TestCase):
    """단어 항목 + 분류."""

    @classmethod
    def setUpTestData(cls):
        cls.git = [make_word(t) for t in ("commit", "merge", "rebase", "stash")]
        cls.api = [make_word(t, category="api") for t in ("endpoint", "payload")]
        cls.db = [make_word(t, category="database") for t in ("index", "query", "schema")]

    def test_category_keeps_distractors_in_category(self):
        """분류를 주면 보기도 그 분류에서만 뽑는다 - 풀 자체가 분류로 좁혀져 있다."""
        allowed = {w.pk for w in self.git}
        for _ in range(REPEAT):
            res = self.quiz(WORD_QUIZ_URL, item=self.git[0].pk, category="git")
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual({c["id"] for c in res.json()["choices"]}, allowed)

    def test_small_category_item_needs_no_category_param(self):
        """분류에 둘뿐인 단어도 분류 없이 부르면 다른 분류로 보기를 채워 낸다.
        상세 버튼은 분류를 안 붙이므로 이쪽이 실제 경로다."""
        res = self.quiz(WORD_QUIZ_URL, item=self.api[0].pk)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.answer_of(WORD_GRADE_URL, res.json()), self.api[0].pk)

    def test_small_category_with_category_param_is_404(self):
        res = self.quiz(WORD_QUIZ_URL, item=self.api[0].pk, category="api")
        self.assertEqual(res.status_code, 404)

    def test_bad_category_is_400_before_item_lookup(self):
        """분류가 틀렸으면 항목을 찾기 전에 400 이다. 항목 쪽 404 가 먼저 나면
        같은 요청에 두 가지 답이 섞인다."""
        for item in (self.git[0].pk, 987654, "abc"):
            res = self.quiz(WORD_QUIZ_URL, item=item, category="nope")
            self.assertEqual(res.status_code, 400, item)


class SentenceItemKindTest(ItemQuizMixin, TestCase):
    """문장 항목 + 유형 조합.

    빈칸은 단어가 든 문장에서만, 상황은 상황이 채워진 문장에서만 낼 수 있다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.words = [make_word(t) for t in ("commit", "merge", "rebase", "stash")]
        # 단어가 없고 상황만 있다.
        cls.no_word = make_sentence("Looks good to me.", context="리뷰를 승인할 때")
        # 단어가 있고 상황이 없다.
        cls.no_context = make_sentence("Please rebase onto main first.", context="")
        # 둘 다 없다.
        cls.neither = make_sentence("Nice catch, thanks.", context="")
        # 상황 보기 채우기용. 상황이 서로 다르다.
        cls.fillers = [
            make_sentence(f"Filler sentence {i}.", context=f"상황 {i} 일 때") for i in range(4)
        ]

    def test_blank_on_sentence_without_word_is_404(self):
        """빈칸을 청했는데 못 뚫으면 404 다. 조용히 상황 문제를 내면 고른 것과
        다른 문제가 나온다."""
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.no_word.pk, kind="blank")
        self.assertEqual(res.status_code, 404)

    def test_situation_on_sentence_without_context_is_404(self):
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.no_context.pk, kind="situation")
        self.assertEqual(res.status_code, 404)

    def test_no_kind_sentence_without_word_is_always_situation(self):
        """유형을 안 정했으면 되는 쪽으로 넘어간다. 그래도 정답은 그 문장이다."""
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.no_word.pk)
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            self.assertEqual(body["kind"], QuizKind.SITUATION)
            self.assertEqual(body["prompt"], self.no_word.text)
            self.assertEqual(self.answer_of(SENTENCE_GRADE_URL, body), self.no_word.pk)

    def test_no_kind_sentence_without_context_is_always_blank_on_it(self):
        """상황이 없으면 빈칸으로만 낸다. 다른 문장에 빈칸을 뚫으면 안 된다 -
        이 경로가 틀리면 무작위 풀에서 아무 문장이나 나온다."""
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.no_context.pk)
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            self.assertEqual(body["kind"], QuizKind.BLANK)
            self.assertEqual(body["source_sentence_id"], self.no_context.pk)
            self.assertEqual(body["prompt"], "Please ____ onto main first.")
            self.assertEqual(self.answer_of(SENTENCE_GRADE_URL, body), self.words[2].pk)

    def test_sentence_with_neither_is_404(self):
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.neither.pk)
        self.assertEqual(res.status_code, 404)

    def test_bad_kind_is_400_before_item_lookup(self):
        for item in (self.no_word.pk, 987654):
            res = self.quiz(SENTENCE_QUIZ_URL, item=item, kind="meaning")
            self.assertEqual(res.status_code, 400, item)

    def test_blank_item_ignores_exclude_of_itself(self):
        """방금 본 문장으로 풀러 왔으니 exclude 에 그 문장이 있어도 낸다."""
        res = self.quiz(
            SENTENCE_QUIZ_URL, item=self.no_context.pk, kind="blank", exclude=str(self.no_context.pk)
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["source_sentence_id"], self.no_context.pk)

    def test_response_keys(self):
        body = self.quiz(SENTENCE_QUIZ_URL, item=self.no_context.pk).json()
        self.assertEqual(set(body), SENTENCE_KEYS)


class SentenceItemReviewGateTest(ItemQuizMixin, TestCase):
    """문장 항목에서 검수 안 된 단어·문장이 끼는지."""

    @classmethod
    def setUpTestData(cls):
        cls.words = [make_word(t) for t in ("cherry", "merge", "rebase", "stash")]
        # 문장 안의 더 긴 용어가 미검수다. 가장 긴 것을 고르는 규칙이
        # 미검수까지 보면 이 단어가 정답이 된다.
        cls.hidden_word = make_word("cherry-pick", meaning="미검수 뜻", is_reviewed=False)
        cls.only_hidden = make_word("squash", meaning="미검수 뜻 둘", is_reviewed=False)
        cls.target = make_sentence("Just cherry-pick that commit.", context="")
        cls.hidden_only_sentence = make_sentence("Please squash it.", context="")
        cls.situation_target = make_sentence("Ship it.", context="배포를 허락할 때")
        cls.hidden_sentences = [
            make_sentence(f"Hidden {i}.", context=f"미검수 상황 {i}", is_reviewed=False)
            for i in range(6)
        ]
        cls.fillers = [
            make_sentence(f"Filler {i}.", context=f"보기 상황 {i} 일 때") for i in range(3)
        ]

    def test_blank_answer_is_never_unreviewed_word(self):
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.target.pk, kind="blank")
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            ids = {c["id"] for c in body["choices"]}
            self.assertEqual(ids, {w.pk for w in self.words})
            self.assertEqual(self.answer_of(SENTENCE_GRADE_URL, body), self.words[0].pk)
            self.assertNotIn("미검수", res.content.decode())

    def test_sentence_whose_only_word_is_unreviewed_cannot_blank(self):
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.hidden_only_sentence.pk, kind="blank")
        self.assertEqual(res.status_code, 404)

    def test_situation_distractors_are_reviewed_only(self):
        allowed = {self.situation_target.pk, *(s.pk for s in self.fillers)}
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.situation_target.pk, kind="situation")
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual({c["id"] for c in res.json()["choices"]}, allowed)
            self.assertNotIn("미검수", res.content.decode())

    def test_unreviewed_sentence_item_is_404_for_every_kind(self):
        """유형마다 다른 경로를 타므로 셋 다 본다."""
        for kind in ("", "blank", "situation"):
            params = {"item": self.hidden_sentences[0].pk}
            if kind:
                params["kind"] = kind
            res = self.client.get(SENTENCE_QUIZ_URL, params)
            self.assertEqual(res.status_code, 404, kind)
            self.assertEqual(res.json()["detail"], "이 문장으로는 지금 문제를 낼 수 없습니다.")


class SentenceItemSituationChoicesTest(ItemQuizMixin, TestCase):
    """상황 고르기 보기가 겹치지 않는지. 겹치면 4지선다가 3지선다가 된다."""

    @classmethod
    def setUpTestData(cls):
        cls.target = make_sentence("Can you take a look?", context="리뷰를 부탁할 때")
        # 정답과 같은 상황 글자를 쓰는 문장, 서로 같은 상황을 쓰는 문장이 많다.
        cls.same_as_answer = [
            make_sentence(f"PTAL {i}.", context="리뷰를 부탁할 때") for i in range(5)
        ]
        cls.dupes = [make_sentence(f"Dup {i}.", context="회의가 길어질 때") for i in range(5)]
        cls.distinct = [
            make_sentence(f"Other {i}.", context=f"다른 상황 {i} 일 때") for i in range(2)
        ]

    def test_choice_texts_are_distinct(self):
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.target.pk, kind="situation")
            self.assertEqual(res.status_code, 200, res.content)
            texts = [c["text"] for c in res.json()["choices"]]
            self.assertEqual(len(texts), 4)
            self.assertEqual(len(set(texts)), 4, texts)

    def test_not_enough_distinct_contexts_is_404(self):
        """서로 다른 상황이 넷이 안 되면 겹친 보기로 내지 않는다."""
        for one in self.distinct:
            one.delete()
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.target.pk, kind="situation")
        self.assertEqual(res.status_code, 404)


class SentenceItemCategoryTest(ItemQuizMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.git = [make_sentence(f"Git line {i}.", context=f"깃 상황 {i} 일 때") for i in range(4)]
        cls.api = make_sentence("Returns 404.", context="API 를 부를 때", category="api")

    def test_item_in_other_category_is_404(self):
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.api.pk, category="git")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "이 문장으로는 지금 문제를 낼 수 없습니다.")

    def test_same_category_distractors_stay_in_category(self):
        allowed = {s.pk for s in self.git}
        for _ in range(REPEAT):
            res = self.quiz(SENTENCE_QUIZ_URL, item=self.git[0].pk, category="git", kind="situation")
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual({c["id"] for c in res.json()["choices"]}, allowed)

    def test_bad_category_is_400(self):
        res = self.quiz(SENTENCE_QUIZ_URL, item=self.git[0].pk, category="nope")
        self.assertEqual(res.status_code, 400)


class ItemParseTest(ItemQuizMixin, TestCase):
    """?item= 값 읽기의 경계."""

    @classmethod
    def setUpTestData(cls):
        cls.words = [make_word(t) for t in ("commit", "merge", "rebase", "stash")]

    def test_surrounding_spaces_are_tolerated(self):
        res = self.quiz(WORD_QUIZ_URL, item=f" {self.words[0].pk} ")
        self.assertEqual(res.status_code, 200, res.content)

    def test_bigint_edges_are_400_or_404_not_500(self):
        """bigint 끝값은 조회까지 가도 되고(404), 넘으면 400 이다."""
        for raw, expected in (
            (str(2**63 - 1), 404),
            (str(2**63), 400),
            ("１２", 400),  # 전각 숫자
            ("²", 400),
            ("1e3", 400),
            ("0x10", 400),
            ("+1", 400),
        ):
            for url in (WORD_QUIZ_URL, SENTENCE_QUIZ_URL):
                res = self.client.get(url, {"item": raw})
                self.assertEqual(res.status_code, expected, (url, raw, res.content))

    def test_repeated_item_param_uses_one_value(self):
        """?item=1&item=2 는 500 이 아니어야 한다."""
        res = self.client.get(
            f"{WORD_QUIZ_URL}?item={self.words[0].pk}&item={self.words[1].pk}"
        )
        self.assertIn(res.status_code, (200, 400), res.content)

    def test_grade_rejects_json_garbage_after_item_quiz(self):
        """항목으로 낸 토큰도 보기 밖 id 를 고르면 틀림으로만 처리된다."""
        body = self.quiz(WORD_QUIZ_URL, item=self.words[0].pk).json()
        res = self.client.post(
            WORD_GRADE_URL,
            json.dumps({"token": body["token"], "picked": 987654}),
            content_type="application/json",
        )
        self.assertIn(res.status_code, (200, 400))
        if res.status_code == 200:
            self.assertFalse(res.json()["correct"])
