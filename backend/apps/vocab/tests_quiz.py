"""문제풀기 테스트.

정답이 새지 않는가, 검수 게이트가 걸리는가, 토큰을 위조할 수 없는가가
핵심이다. 문제 자체는 무작위라 "어떤 문제가 나오는지" 는 고정하지 않고
"어떤 문제가 나와도 성립해야 하는 것" 만 확인한다.
"""

import base64
import hashlib
import json
import re
import time
from collections import Counter
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase

from .models import Word
from .quiz import (
    CHOICE_COUNT,
    TOKEN_MAX_AGE,
    QuizKind,
    _mask_term,
    grade_answer,
    make_question,
    sign_question,
)
from .views import MAX_EXCLUDE_IDS, _parse_ids

QUIZ_URL = "/api/vocab/words/quiz/"
GRADE_URL = "/api/vocab/words/grade/"


def sign(answer_id: int) -> str:
    """정답 하나로 토큰을 만든다. 보기는 겹치지 않는 값으로 채운다.

    id 는 항상 양수라 음수를 넣으면 실제 단어와 부딪히지 않는다.
    """
    return sign_question(answer_id, [answer_id, -2, -3, -4])


def make_words(count: int, category: str = "git", **kwargs) -> list[Word]:
    """문제를 낼 만큼의 단어를 만든다.

    term 이 unique 라 분류마다 접두사를 달리한다. 같은 이름을 두 번
    만들면 IntegrityError 로 터진다.
    """
    return [
        Word.objects.create(
            term=f"{category}-term{i}",
            meaning=f"{category} 뜻{i}",
            description=f"{category} 설명{i}",
            category=category,
            is_reviewed=True,
            **kwargs,
        )
        for i in range(count)
    ]


class QuizTokenTest(TestCase):
    """정답 토큰."""

    def test_grades_correct_pick(self):
        self.assertEqual(grade_answer(sign(42), 42), (True, 42))

    def test_grades_wrong_pick(self):
        """틀려도 정답 id 는 알려준다. 해설을 보여줘야 한다."""
        self.assertEqual(grade_answer(sign(42), -2), (False, 42))

    def test_forged_token_is_rejected(self):
        self.assertIsNone(grade_answer("아무거나", 1))

    def test_tampered_token_is_rejected(self):
        """한 글자만 바꿔도 서명이 깨진다."""
        token = sign(42)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

        self.assertIsNone(grade_answer(tampered, 42))

    def test_token_does_not_reveal_which_choice_is_correct(self):
        """토큰을 풀어봐도 넷 중 무엇이 정답인지 알 수 없어야 한다.

        문자열 검사만으로는 부족하다. signing.dumps 는 서명일 뿐
        암호화가 아니라서, base64 로 풀면 담은 값이 그대로 나온다.
        예전 방식은 정답 id 하나만 담아서, 풀면 바로 답이 보였다.

        보기 id 넷은 어차피 문제 응답에 그대로 나가므로 담아도 된다.
        감춰야 하는 건 그 넷 중 어느 것이냐다 - 정답과 오답이
        구별되지 않는지를 본다.
        """
        choices = [11, 22, 33, 44]
        token = sign_question(11, choices)

        body = token.split(":")[0]
        payload = json.loads(
            base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        )

        # 담긴 것은 보기 넷과 지문·nonce 뿐이다. 정답을 따로 담은
        # 자리가 있으면 풀자마자 답이 보인다.
        self.assertEqual(set(payload), {"a", "n", "c"})
        self.assertEqual(sorted(payload["c"]), choices)
        # 지문은 되돌릴 수 없는 값이라 보기와 무관해야 한다.
        # 정답이 무엇인지는 SECRET_KEY 로 넷을 하나씩 대조해야만 나온다.
        self.assertNotIn(payload["a"], [str(c) for c in choices])

    def test_same_answer_gives_different_tokens(self):
        """같은 정답이라도 토큰이 같으면 대조해서 알아낼 수 있다."""
        self.assertNotEqual(sign(42), sign(42))

    def test_pick_outside_choices_is_wrong(self):
        """보기에 없는 값을 보내도 터지지 않고 오답이 된다."""
        self.assertEqual(grade_answer(sign(42), 999), (False, 42))


class MakeQuestionTest(TestCase):
    """출제 로직."""

    def test_returns_none_when_not_enough_words(self):
        """보기를 채울 수 없으면 문제를 만들지 않는다."""
        make_words(2)

        self.assertIsNone(make_question(Word.objects.visible()))

    def test_choice_count(self):
        make_words(10)

        q = make_question(Word.objects.visible())

        self.assertEqual(len(q.choices), CHOICE_COUNT)

    def test_answer_is_among_choices(self):
        """정답이 보기에 없으면 아무도 맞힐 수 없다."""
        make_words(10)

        for _ in range(10):
            q = make_question(Word.objects.visible())
            self.assertIn(q.answer_id, [c.id for c in q.choices])

    def test_choices_are_distinct(self):
        """같은 보기가 두 번 나오면 정답이 둘로 보인다."""
        make_words(10)

        for _ in range(10):
            q = make_question(Word.objects.visible())
            ids = [c.id for c in q.choices]
            self.assertEqual(len(ids), len(set(ids)))

    def test_kind_can_be_fixed(self):
        make_words(10)

        for kind in QuizKind.ALL:
            q = make_question(Word.objects.visible(), kind=kind)
            self.assertEqual(q.kind, kind)

    def test_random_kind_covers_all(self):
        """유형을 지정하지 않으면 세 가지가 골고루 나온다."""
        make_words(10)

        kinds = {make_question(Word.objects.visible()).kind for _ in range(60)}

        self.assertEqual(kinds, set(QuizKind.ALL))

    def test_description_kind_skips_words_without_description(self):
        """설명이 없는 단어는 설명 문제로 낼 수 없다."""
        for i in range(10):
            Word.objects.create(
                term=f"nodesc{i}", meaning=f"뜻{i}", description="",
                category="git", is_reviewed=True,
            )
        Word.objects.create(
            term="only", meaning="유일", description="이것만 설명이 있다",
            category="git", is_reviewed=True,
        )

        for _ in range(10):
            q = make_question(Word.objects.visible(), kind=QuizKind.DESCRIPTION)
            self.assertEqual(q.prompt, "이것만 설명이 있다")

    def test_description_hides_the_term(self):
        """설명에 단어가 들어 있으면 답이 지문에 그대로 있다."""
        make_words(10)
        Word.objects.create(
            term="API",
            meaning="응용 프로그램 인터페이스",
            description="API 는 프로그램끼리 주고받는 약속이다. api 라고도 쓴다.",
            category="git",
            is_reviewed=True,
        )

        for _ in range(30):
            q = make_question(Word.objects.visible(), kind=QuizKind.DESCRIPTION)
            self.assertNotIn("API", q.prompt)
            # 대소문자만 다른 경우도 가려야 한다
            self.assertNotIn("api", q.prompt.lower())

    def test_exclude_is_respected(self):
        """방금 낸 문제를 다시 내지 않는다."""
        words = make_words(10)
        skip = [w.pk for w in words[:5]]

        for _ in range(20):
            q = make_question(Word.objects.visible(), exclude_ids=skip)
            self.assertNotIn(q.answer_id, skip)

    def test_distractors_prefer_same_category(self):
        """오답을 아무 데서나 뽑으면 답이 뻔해진다."""
        make_words(10, category="git")
        make_words(10, category="database")

        # git 단어가 정답인 문제를 여러 번 만들어 오답 분류를 본다
        same_category = 0
        total = 0
        for _ in range(20):
            q = make_question(Word.objects.visible(), kind=QuizKind.MEANING)
            answer = Word.objects.get(pk=q.answer_id)
            others = Word.objects.filter(
                pk__in=[c.id for c in q.choices]
            ).exclude(pk=answer.pk)
            total += others.count()
            same_category += others.filter(category=answer.category).count()

        # 분류마다 오답 후보가 넉넉하므로 전부 같은 분류에서 나와야 한다
        self.assertEqual(same_category, total)


class QuizAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_words(20)
        cls.hidden = Word.objects.create(
            term="secret-unreviewed",
            meaning="미검수",
            description="검수 전이라 나오면 안 된다",
            category="git",
            is_reviewed=False,
        )

    def test_question_has_no_answer_id(self):
        """정답이 응답에 있으면 개발자도구로 미리 본다."""
        body = self.client.get(QUIZ_URL).json()

        self.assertNotIn("answer_id", body)
        self.assertNotIn("answer", body)
        self.assertIn("token", body)

    def test_unreviewed_never_appears(self):
        """검수 전 단어는 문제로도 보기로도 나오면 안 된다."""
        for _ in range(30):
            res = self.client.get(QUIZ_URL)
            self.assertNotIn("secret-unreviewed", res.content.decode())
            self.assertNotIn("검수 전이라", res.content.decode())

    def test_grade_marks_exactly_one_choice_correct(self):
        """네 보기 중 하나만 정답이어야 한다."""
        q = self.client.get(QUIZ_URL).json()

        correct = [
            c["id"]
            for c in q["choices"]
            if self.client.post(
                GRADE_URL,
                {"token": q["token"], "picked": c["id"]},
                content_type="application/json",
            ).json()["correct"]
        ]

        self.assertEqual(len(correct), 1)

    def test_grade_returns_explanation(self):
        """맞든 틀리든 해설을 준다. 맞힌 사람도 왜 맞았는지 봐야 한다."""
        q = self.client.get(QUIZ_URL).json()

        body = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        self.assertIn("description", body["word"])
        self.assertIn("example", body["word"])
        self.assertIn("pronunciation", body["word"])

    def test_forged_token_is_rejected(self):
        res = self.client.post(
            GRADE_URL,
            {"token": "위조", "picked": 1},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_missing_token_is_rejected(self):
        res = self.client.post(
            GRADE_URL, {"picked": 1}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 400)

    def test_grade_does_not_expose_unreviewed(self):
        """미검수 단어의 토큰을 위조해도 내용이 새면 안 된다.

        토큰은 서버가 서명하므로 정상 경로로는 만들 수 없다. 다만
        검수가 취소된 뒤 옛 토큰으로 채점하는 경우가 있어 막아둔다.
        """
        token = sign(self.hidden.pk)

        res = self.client.post(
            GRADE_URL,
            {"token": token, "picked": self.hidden.pk},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 404)
        self.assertNotIn("검수 전이라", res.content.decode())

    def test_anonymous_can_grade(self):
        """채점은 POST 지만 로그인을 요구하면 문제풀기를 못 쓴다."""
        q = self.client.get(QUIZ_URL).json()

        res = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)

    def test_category_filter(self):
        make_words(10, category="api")

        for _ in range(10):
            q = self.client.get(QUIZ_URL, {"category": "api"}).json()
            self.assertEqual(q["category"], "api")

    def test_unknown_category_is_rejected(self):
        res = self.client.get(QUIZ_URL, {"category": "nonexistent"})

        self.assertEqual(res.status_code, 400)

    def test_not_enough_words_returns_404(self):
        """분류를 너무 좁히면 문제를 못 만든다. 조건을 바꾸라고 알려준다."""
        Word.objects.create(
            term="lonely", meaning="혼자", category="debug", is_reviewed=True
        )

        res = self.client.get(QUIZ_URL, {"category": "debug"})

        self.assertEqual(res.status_code, 404)

    def test_exclude_param_ignores_garbage(self):
        """사용자가 보내는 값이라 무엇이든 들어온다. 터지면 안 된다.

        유니코드 숫자를 같이 넣는 이유: "²" 나 아랍-인도 숫자는
        isdigit() 이 True 를 주는데 int() 는 그중 일부에서 터진다.
        """
        res = self.client.get(QUIZ_URL, {"exclude": "abc,,-1,3.5,²,٣,１"})

        self.assertEqual(res.status_code, 200)

    def test_exclude_param_is_capped(self):
        """긴 목록을 보내도 터지지 않는다.

        실제 단어와 안 겹치도록 큰 수만 보낸다. 여기서 보려는 건
        문제가 나오는지가 아니라 목록 길이를 제한하는지다.
        """
        res = self.client.get(
            QUIZ_URL, {"exclude": ",".join(str(i) for i in range(900000, 905000))}
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(_parse_ids("1," * 5000)), MAX_EXCLUDE_IDS)

    def test_staff_quiz_still_excludes_unreviewed(self):
        """검수자에게도 미검수를 문제로 내면 안 된다.

        목록에서는 검수하려고 보여주지만, 문제는 학습용이라 다르다.
        """
        staff = get_user_model().objects.create_user(
            username="reviewer", password="x", is_staff=True
        )
        self.client.force_login(staff)

        for _ in range(30):
            res = self.client.get(QUIZ_URL)
            self.assertNotIn("secret-unreviewed", res.content.decode())


# ---------------------------------------------------------------------------
# 독립 동적 테스트 - 위 구현자 테스트와 별개로 설계했다.
# 통과 확인이 아니라 결함 찾기가 목적이다.
# ---------------------------------------------------------------------------


class TokenSecrecyTest(TestCase):
    """토큰에서 정답을 알아낼 수 있는가.

    signing.dumps 는 서명이지 암호화가 아니다. 담긴 값은 base64 로 풀면
    그대로 보이므로, "무엇을 담지 않았는가" 를 실제로 디코드해서 본다.
    """

    @staticmethod
    def decode(token: str) -> dict:
        """서명 토큰의 payload 를 그대로 꺼낸다. 공격자가 하는 일과 같다."""
        body = token.split(":")[0]
        return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))

    def test_payload_carries_no_answer_id(self):
        """보기 넷 말고 정답을 따로 담은 자리가 있으면 풀자마자 답이 보인다."""
        payload = self.decode(sign_question(11, [11, 22, 33, 44]))

        self.assertEqual(set(payload), {"a", "n", "c"})
        self.assertEqual(sorted(payload["c"]), [11, 22, 33, 44])

    def test_fingerprint_is_not_a_plain_hash_of_the_id(self):
        """SECRET_KEY 없이 지문을 재현할 수 있으면 뚫린 것이다.

        공격자는 보기 넷과 nonce 를 안다(둘 다 토큰에 들어 있다).
        지문이 그냥 sha256(id:nonce) 라면 넷을 대조해 정답을 찾는다.
        HMAC 이라 SECRET_KEY 없이는 못 만든다.
        """
        payload = self.decode(sign_question(11, [11, 22, 33, 44]))

        guessed = {
            hashlib.sha256(f"{cid}:{payload['n']}".encode()).hexdigest()
            for cid in payload["c"]
        }

        self.assertNotIn(payload["a"], guessed, "SECRET_KEY 없이 정답이 대조됐다")

    def test_nonce_is_unpredictable(self):
        """nonce 가 예측 가능하면 지문을 미리 만들어 둘 수 있다.

        고정 입력에서 나오는 값(서명 등)을 쓰면 같은 nonce 가 반복된다.
        """
        nonces = {self.decode(sign(42))["n"] for _ in range(50)}

        self.assertEqual(len(nonces), 50, "nonce 가 반복된다")

    def test_same_answer_gives_different_fingerprint_each_time(self):
        """같은 정답의 지문이 매번 같으면 한 번 알아낸 값을 계속 대조한다."""
        prints = {self.decode(sign(42))["a"] for _ in range(50)}

        self.assertEqual(len(prints), 50, "지문이 반복된다")

    def test_token_from_other_salt_is_rejected(self):
        """다른 용도의 서명을 여기서 풀 수 있으면 안 된다."""
        token = signing.dumps({"a": "x", "n": "n", "c": [1]}, salt="other.purpose")

        self.assertIsNone(grade_answer(token, 1))


class MaskTermUnitTest(TestCase):
    """설명 문제에서 정답 단어를 가리는 규칙.

    지문에 답이 남으면 문제가 성립하지 않고, 반대로 너무 많이 가리면
    엉뚱한 낱말이 사라져 설명을 읽을 수 없게 된다.
    """

    def test_masks_regardless_of_case(self):
        """설명에서 "REST" 를 "Rest" 로 적은 경우가 있다."""
        for desc in ["API 는 약속", "api 는 약속", "ApI 는 약속"]:
            with self.subTest(desc=desc):
                self.assertNotIn("api", _mask_term(desc, "API").lower())

    def test_masks_every_occurrence(self):
        """한 번만 가리면 두 번째가 그대로 남는다."""
        masked = _mask_term("API 는 약속이다. api 라고도 쓴다.", "API")

        self.assertNotIn("api", masked.lower())

    def test_masks_derived_words(self):
        """파생어 안에 답이 남으면 지문만 읽고 맞힐 수 있다.

        실제 데이터에서 나온 사례들이다. 단어만 정확히 맞춰 가리면
        "nit" 문제의 지문에 "nitpick" 이 그대로 남는다.
        """
        cases = [
            ("nit", "nitpick 의 줄임말이고 'nit:' 처럼 쓴다"),
            ("spec", "specification 의 줄임말이다"),
            ("REST", "'RESTful' 의 기준은 팀마다 다르다"),
            ("watch", "watchpoint 와는 다르다"),
        ]
        for term, desc in cases:
            with self.subTest(term=term):
                self.assertNotIn(term.lower(), _mask_term(desc, term).lower())

    def test_masks_abbreviation_expansion(self):
        """약어는 원형을 읽으면 답이 나온다.

        단어 자체를 가려도 "Application Programming Interface 의
        줄임말" 이 남아 있으면 머리글자만 조합하면 된다. 566개 중
        112개가 이런 모양이었다.
        """
        cases = [
            ("API", "Application Programming Interface 의 줄임말이다"),
            ("SQL", "Structured Query Language 의 줄임말"),
            ("RBAC", "Role-Based Access Control 이라고 부른다"),
            ("MVP", "Minimum Viable Product 의 줄임말"),
            # 연결어가 소문자인 원형. 대문자만 찾으면 이게 남는다
            ("POC", "Proof of Concept 의 줄임말"),
        ]
        for term, desc in cases:
            with self.subTest(term=term):
                masked = _mask_term(desc, term)
                # 원형의 첫 낱말이 남아 있으면 나머지도 남은 것이다
                self.assertNotIn(desc.split()[0], masked)

    def test_keeps_unrelated_capitalized_phrases(self):
        """머리글자가 다른 덩어리는 건드리지 않는다."""
        masked = _mask_term("Git Bash 에서도 쓸 수 있다", "API")

        self.assertIn("Git Bash", masked)

    def test_masks_expansion_of_mixed_case_abbreviations(self):
        """소문자가 섞인 약어도 원형을 가려야 한다.

        isupper() 로 걸러내면 IaaS, PaaS, SaaS, IoC 가 전부 빠진다.
        셋은 같은 분류라 서로가 서로의 오답 보기로 들어오기까지 한다.
        """
        cases = [
            ("IaaS", "Infrastructure as a Service 의 줄임말"),
            ("PaaS", "Platform as a Service 의 줄임말"),
            ("IoC", "Inversion of Control 의 줄임말"),
        ]
        for term, desc in cases:
            with self.subTest(term=term):
                self.assertNotIn(desc.split()[0], _mask_term(desc, term))

    def test_masks_expansion_that_skips_connectives(self):
        """약어가 연결어를 빼고 만들어진 경우.

        "Redundant Array of Independent Disks" 는 of 를 빼야 RAID 가 된다.
        머리글자를 전부 세면 RAOID 라 안 맞아서 그냥 지나쳤고, 프로덕션
        퀴즈에서 원형이 지문에 그대로 나왔다.
        """
        cases = [
            ("RAID", "Redundant Array of Independent Disks 의 줄임말"),
            ("DRY", "Don't Repeat Yourself 의 줄임말"),
            ("YAGNI", "You Aren't Gonna Need It 에서 왔다"),
        ]
        for term, desc in cases:
            with self.subTest(term=term):
                self.assertNotIn(desc.split()[0], _mask_term(desc, term))

    def test_masks_expansion_across_line_breaks(self):
        """설명에 줄바꿈이 있어도 원형을 가려야 한다.

        Admin 에서 여러 줄로 입력하면 낱말 사이에 개행이 들어온다.
        구분자 처리가 어긋나면 마스킹이 조용히 안 걸린다.
        """
        masked = _mask_term("Create,\nRead, Update, Delete 의 앞 글자", "CRUD")

        self.assertNotIn("Create", masked)
        self.assertIn("____", masked)

    def test_masks_comma_separated_expansion(self):
        """나열로 적은 원형도 가린다."""
        masked = _mask_term("Create, Read, Update, Delete 의 앞 글자", "CRUD")

        self.assertNotIn("Create", masked)

    def test_keeps_sentences_whose_initials_differ(self):
        """머리글자가 다르면 낱말 수가 같아도 그대로 둔다.

        연결어를 소문자까지 허용하면서 매칭 범위가 넓어졌다. 머리글자
        대조가 없으면 영어 문장이 통째로 지워진다.
        """
        # 낱말 셋이라 API 와 길이는 같지만 머리글자는 ATI 다
        text = "A tag is 붙이는 방식"

        self.assertEqual(_mask_term(text, "API"), text)

    def test_masks_only_the_matching_phrase(self):
        """머리글자가 맞는 덩어리만 지우고 나머지 문장은 남긴다."""
        masked = _mask_term(
            "Application Programming Interface 의 줄임말이고 Git Bash 에서도 쓴다",
            "API",
        )

        self.assertNotIn("Application", masked)
        self.assertIn("Git Bash", masked)

    def test_masks_each_word_of_a_multiword_term(self):
        """여러 낱말로 된 단어는 낱말이 따로 나와도 가려야 한다.

        "pull request" 를 통째로 가려도 "merge request 라고도 부른다"
        가 남으면 답이 보인다. 실데이터에서 나온 사례들이다.
        """
        cases = [
            ("pull request", "merge request 라고 부르기도 한다", "request"),
            ("technical debt", "debt 의 b 는 소리 내지 않는다", "debt"),
            ("dynamic programming", "이름의 programming 은 다르다", "programming"),
        ]
        for term, desc, leaked in cases:
            with self.subTest(term=term):
                self.assertNotIn(leaked, _mask_term(desc, term))

    def test_keeps_short_words_of_a_multiword_term(self):
        """짧은 낱말까지 가리면 문장을 읽을 수 없다."""
        masked = _mask_term("big 은 크다는 뜻이고 O 는 차수를 말한다", "big O")

        # "big" 은 세 글자라 낱말 규칙 대상이 아니다
        self.assertIn("크다는", masked)

    def test_does_not_mask_inside_other_words(self):
        """부분 일치로 가리면 엉뚱한 낱말이 사라지고 그 모양이 힌트가 된다.

        "GET" 이 "forget" 안까지 가려 "for____" 가 되면, 지문이 망가지는
        데다 가려진 자리 길이가 오히려 답을 알려준다.
        """
        self.assertEqual(_mask_term("forget 은 다르다", "GET"), "forget 은 다르다")
        self.assertEqual(
            _mask_term("Rapid Application", "API"), "Rapid Application"
        )

    def test_masks_term_with_symbols(self):
        """C++ 나 .NET 처럼 기호가 붙은 단어도 가려야 한다.

        정규식으로 짜면 기호가 메타문자로 해석돼 엉뚱한 곳이 걸리거나
        터진다. \\b 는 기호 경계에서 판정이 뒤집힌다.
        """
        for desc, term in [("C++ 는 언어다", "C++"), (".NET 은 플랫폼", ".NET")]:
            with self.subTest(term=term):
                masked = _mask_term(desc, term)
                self.assertNotIn(term, masked)
                self.assertIn("____", masked)

    def test_unicode_case_change_does_not_corrupt_offsets(self):
        """lower() 가 길이를 바꾸는 문자에서 마스킹 위치가 밀리면 안 된다.

        'İ'(U+0130) 는 lower() 하면 두 글자가 된다. 소문자 문자열에서 찾은
        위치로 원본을 자르면 그만큼 어긋나, 단어 대신 옆 글자가 잘린다.
        """
        masked = _mask_term("İ 로 시작한다. API 는 약속이다", "API")

        self.assertEqual(masked, "İ 로 시작한다. ____ 는 약속이다")

    def test_blank_term_returns_description_unchanged(self):
        self.assertEqual(_mask_term("설명 그대로", ""), "설명 그대로")

    def test_term_absent_from_description(self):
        self.assertEqual(_mask_term("관계 없는 설명", "API"), "관계 없는 설명")


class DescriptionQuizLeakTest(TestCase):
    """설명 유형 문제에서 정답이 지문에 남는가."""

    def test_answer_term_never_appears_in_prompt(self):
        """어떤 단어가 정답으로 뽑히든 지문에 그 단어가 있으면 안 된다."""
        make_words(10)
        Word.objects.create(
            term="REST",
            meaning="레스트",
            description="Rest 는 아키텍처 스타일이다. rest 라고도 한다.",
            category="git",
            is_reviewed=True,
        )

        for _ in range(40):
            q = make_question(Word.objects.visible(), kind=QuizKind.DESCRIPTION)
            answer = Word.objects.get(pk=q.answer_id)
            self.assertNotIn(
                answer.term.lower(), q.prompt.lower(), f"'{answer.term}' 가 지문에 남음"
            )

    def test_seed_data_has_no_leaking_description(self):
        """실제로 배포되는 566개를 전수로 본다.

        단위 테스트는 만들어 넣은 문장만 보므로, 실데이터의 예상 못 한
        모양을 못 잡는다. 실제로 괄호가 낀 "Atomicity(원자성),
        Consistency(일관성)..." 나 한글이 끼어든 "Carriage Return 과
        Line Feed" 가 마스킹을 빠져나갔다.

        단어가 그대로 남는 경우와, 낱말들의 머리글자를 조합하면 답이
        나오는 경우를 함께 본다. 후자가 약어에서 특히 많다.

        이 검사는 마스킹 코드보다 넓게 본다. 여기서는 한글을 건너뛰고
        영어 낱말을 이어 붙이는데, 마스킹은 한글에서 끊긴다. 그래서
        "Continuous 하게 Integration" 처럼 원형 사이에 한글이 낀 경우는
        여기서 잡히지만 코드로는 못 지운다 - 그때는 설명 문장을 고쳐야
        한다. 코드 검사가 아니라 데이터 품질 검사에 가깝다.
        """
        from .management.commands.seed_words import WORDS

        word_pattern = re.compile(r"[A-Za-z]['’A-Za-z]*")
        leaks = []

        for row in WORDS:
            term, description = row[0], row[5]
            if not description:
                continue

            masked = _mask_term(description, term)
            if term.lower() in masked.lower():
                leaks.append(f"{term}: 단어가 그대로 남음")
                continue

            # 연속한 영어 낱말의 머리글자가 약어와 맞으면 답이 보인다.
            #
            # 길이를 term 보다 길게도 잘라보는 이유: 약어가 연결어를 빼고
            # 만들어진 경우가 있다(RAID <- Redundant Array of Independent
            # Disks). 딱 맞는 길이만 보면 그런 원형을 놓친다.
            words = word_pattern.findall(masked)
            leaked = None
            for i in range(len(words)):
                for size in range(len(term), len(term) + 4):
                    segment = words[i : i + size]
                    if len(segment) < 2:
                        continue
                    every = "".join(w[0] for w in segment).upper()
                    major = "".join(
                        w[0] for w in segment if w[0].isupper()
                    ).upper()
                    if term.upper() in (every, major):
                        leaked = " ".join(segment)
                        break
                if leaked:
                    break

            if leaked:
                leaks.append(f"{term}: 원형 '{leaked}' 남음")

        self.assertEqual(leaks, [], f"설명에 답이 남는 단어 {len(leaks)}개")


class ChoiceQualityTest(TestCase):
    """보기 품질. 문제가 성립하려면 정답이 하나로 읽혀야 한다."""

    @classmethod
    def setUpTestData(cls):
        make_words(30)

    def test_answer_position_is_not_biased(self):
        """정답이 늘 같은 자리에 오면 내용을 안 읽고도 맞힌다.

        400번 뽑아 네 자리에 고르게 퍼지는지 본다. shuffle 을 빠뜨리면
        정답이 항상 0번이라 이 검사가 바로 걸린다.
        """
        positions = Counter()
        for _ in range(400):
            q = make_question(Word.objects.visible())
            positions[[c.id for c in q.choices].index(q.answer_id)] += 1

        self.assertEqual(set(positions), {0, 1, 2, 3}, "안 나오는 자리가 있다")
        for slot, count in positions.items():
            self.assertGreater(count, 40, f"{slot}번 자리가 {count}회뿐")

    def test_choice_ids_are_distinct(self):
        """같은 단어가 두 보기로 나오면 정답이 둘로 보인다."""
        for _ in range(30):
            ids = [c.id for c in make_question(Word.objects.visible()).choices]
            self.assertEqual(len(ids), len(set(ids)))

    def test_answer_is_always_among_choices(self):
        for _ in range(30):
            q = make_question(Word.objects.visible())
            self.assertIn(q.answer_id, [c.id for c in q.choices])


class QuizBoundaryTest(TestCase):
    """단어가 모자란 경계. 500 이 아니라 404 여야 한다."""

    def test_no_words_at_all_is_404(self):
        self.assertEqual(self.client.get(QUIZ_URL).status_code, 404)

    def test_three_words_is_404(self):
        """보기 넷을 못 채운다."""
        make_words(3)

        self.assertEqual(self.client.get(QUIZ_URL).status_code, 404)

    def test_exactly_four_words_makes_a_question(self):
        """딱 네 개면 문제가 성립한다."""
        make_words(4)

        res = self.client.get(QUIZ_URL)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["choices"]), CHOICE_COUNT)

    def test_only_unreviewed_words_is_404(self):
        """검수된 단어가 하나도 없으면 문제를 못 낸다 - 미검수로 채우면 안 된다."""
        make_words(10)
        Word.objects.update(is_reviewed=False)

        self.assertEqual(self.client.get(QUIZ_URL).status_code, 404)

    def test_excluding_every_word_is_404(self):
        make_words(10)
        every = ",".join(str(w.pk) for w in Word.objects.all())

        self.assertEqual(
            self.client.get(QUIZ_URL, {"exclude": every}).status_code, 404
        )

    def test_category_with_one_word_is_404(self):
        make_words(10, category="git")
        Word.objects.create(
            term="lonely", meaning="혼자", category="debug", is_reviewed=True
        )

        self.assertEqual(
            self.client.get(QUIZ_URL, {"category": "debug"}).status_code, 404
        )


class QuizInputAttackTest(TestCase):
    """출제 쿼리스트링에 무엇을 넣어도 500 이 나면 안 된다."""

    @classmethod
    def setUpTestData(cls):
        make_words(20)

    def test_exclude_garbage_does_not_500(self):
        """유니코드 숫자·음수·소수·SQL 조각을 섞어도 버티는지.

        isdigit() 은 "²" 나 아랍-인도 숫자에도 True 를 주는데 int() 는
        그중 일부에서 터진다. 자릿수가 큰 값은 파이썬의 정수 변환 상한
        (4300자리)과 DB 의 bigint 범위 양쪽에서 터진다.
        """
        for raw in [
            "abc,,-1,3.5,²,٣,１",
            "'; DROP TABLE vocab_word; --",
            "0x10,1e5,١٢٣,①②③",
            "\x00,1",
            " 1 , 2 ",
            "9" * 5000,
            "99999999999999999999999999",
            ",".join(["9"] * 50000),
        ]:
            with self.subTest(exclude=raw[:30]):
                res = self.client.get(QUIZ_URL, {"exclude": raw})
                self.assertLess(res.status_code, 500, f"exclude={raw[:50]!r}")

    def test_exclude_ignores_oversized_ids(self):
        """bigint 를 넘는 값은 버린다. pk__in 에 넣으면 DB 가 거절한다."""
        self.assertEqual(_parse_ids("9" * 5000), [])
        self.assertEqual(_parse_ids(str(2**63)), [])
        self.assertEqual(_parse_ids(str(2**63 - 1)), [2**63 - 1])

    def test_exclude_list_is_capped(self):
        self.assertEqual(len(_parse_ids("1," * 5000)), MAX_EXCLUDE_IDS)

    def test_exclude_garbage_only_is_capped_too(self):
        """쓰레기만 보내 상한을 피하며 순회를 길게 끌 수 없다."""
        self.assertEqual(_parse_ids("a," * 100000), [])

    def test_kind_garbage_falls_back_to_random(self):
        """모르는 유형은 무작위로 떨어진다. 400 이든 200 이든 500 은 안 된다."""
        for kind in ["MEANING", "", "xxx", "meaning,term", "['meaning']", "9" * 100]:
            with self.subTest(kind=kind[:20]):
                res = self.client.get(QUIZ_URL, {"kind": kind})
                self.assertLess(res.status_code, 500)

    def test_list_filters_on_quiz_do_not_500(self):
        """목록용 필터를 붙여도 터지지 않는다. 출제는 분류만 받는다."""
        for params in [
            {"search": "git-term1"},
            {"search": "'"},
            {"ordering": "term"},
            {"ordering": "nonexistent"},
            {"difficulty": "2"},
            {"difficulty": "abc"},
        ]:
            with self.subTest(params=params):
                res = self.client.get(QUIZ_URL, params)
                self.assertLess(res.status_code, 500, f"{params}")

    def test_search_cannot_narrow_the_question_pool(self):
        """?search 로 출제 풀을 좁힐 수 있으면 정답 후보를 추릴 수 있다.

        목록은 검색이 되어야 하지만 출제는 아니다. quiz 가 목록과 같은
        filter_queryset 을 타면 이 검사가 깨진다.

        정답으로 나온 단어 종류를 직접 센다. 보기 전체를 보면 오답이
        섞여 다양해 보이고, 검색으로 풀이 4개 미만이 되어 404 로 죽는
        경우에도 "실패했으니 잡았다" 가 되어 무엇을 확인했는지 알 수 없다.
        """
        # 다른 분류에 단어를 넉넉히 둔다. 검색이 먹으면 정답이 git 쪽
        # 스무 개로 좁혀지고, 안 먹으면 마흔 개 전체에서 나온다.
        make_words(20, category="database")

        # 유형을 고정한다. 유형이 섞이면 지문이 term/meaning/description
        # 으로 갈려 종류가 부풀려진다.
        answers = set()
        for _ in range(40):
            res = self.client.get(
                QUIZ_URL, {"search": "database-term", "kind": QuizKind.MEANING}
            )
            self.assertEqual(res.status_code, 200)
            answers.add(res.json()["prompt"])

        # 검색이 먹으면 database 단어만 나온다. 안 먹으면 git 쪽도 섞인다.
        self.assertTrue(
            any(a.startswith("git-") for a in answers),
            "검색으로 출제 풀이 좁혀졌다",
        )


class GradeAttackTest(TestCase):
    """채점 조작. 위조·만료·이상한 타입으로 정답을 얻거나 터뜨릴 수 있는가."""

    @classmethod
    def setUpTestData(cls):
        make_words(20)

    def post(self, body, content_type="application/json"):
        return self.client.post(GRADE_URL, body, content_type=content_type)

    def grade(self, **payload):
        return self.post(json.dumps(payload))

    def test_non_object_body_is_400(self):
        """JSON 본문이 객체가 아닐 수 있다. dict 로 가정하면 500 이 난다."""
        for body in ("[]", '"문자열"', "123", "null", "true"):
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)

    def test_non_string_token_is_400(self):
        """token 자리에 숫자나 null 이 와도 터지면 안 된다."""
        for token in (None, 1, True, [], {}):
            with self.subTest(token=token):
                self.assertEqual(self.grade(token=token, picked=1).status_code, 400)

    def test_malformed_payload_in_valid_signature_is_400(self):
        """서명은 맞는데 담긴 모양이 틀린 경우.

        옛 형식의 토큰이 남아 있거나 우리 코드가 잘못 만든 경우다.
        서명을 통과했다고 모양까지 믿으면 채점 계산에서 터진다.
        """
        broken = [
            {"a": None, "n": None, "c": [1]},
            {"a": "x", "n": 1, "c": [1]},
            {"a": "x", "n": "y", "c": "목록아님"},
            {"a": "x", "n": "y", "c": []},
            {"a": "x", "n": "y", "c": ["문자열"]},
            {"c": [1]},
        ]
        for payload in broken:
            with self.subTest(payload=payload):
                token = signing.dumps(payload, salt="vocab.quiz.answer")
                self.assertEqual(self.grade(token=token, picked=1).status_code, 400)

    def test_boolean_picked_is_not_treated_as_choice_one(self):
        """파이썬에서 True 는 int 라 1 번 보기를 고른 것으로 처리될 수 있다."""
        token = sign_question(1, [1, 2, 3, 4])

        # 같은 토큰에 1 을 보내면 정답이다
        self.assertEqual(grade_answer(token, 1)[0], True)

        res = self.grade(token=token, picked=True)

        # True 를 보냈을 때 정답 처리되면 안 된다. 그 단어가 없으면 404.
        self.assertIn(res.status_code, (200, 404))
        if res.status_code == 200:
            self.assertFalse(res.json()["correct"])

    def test_truncated_token_is_400(self):
        """잘라낸 토큰은 서명이 깨져 거부된다."""
        token = self.client.get(QUIZ_URL).json()["token"]

        for cut in [1, len(token) // 2, len(token) - 5]:
            with self.subTest(cut=cut):
                self.assertEqual(self.grade(token=token[:cut], picked=1).status_code, 400)

    def test_expired_token_is_400(self):
        """어제 받은 토큰으로 오늘 채점되면 안 된다."""
        token = self.client.get(QUIZ_URL).json()["token"]

        with mock.patch("time.time", return_value=time.time() + TOKEN_MAX_AGE + 60):
            self.assertEqual(self.grade(token=token, picked=1).status_code, 400)

    def test_token_just_inside_max_age_still_works(self):
        """만료 직전까지는 채점된다. 경계를 반대쪽에서도 본다."""
        q = self.client.get(QUIZ_URL).json()

        with mock.patch("time.time", return_value=time.time() + TOKEN_MAX_AGE - 60):
            res = self.grade(token=q["token"], picked=q["choices"][0]["id"])

        self.assertEqual(res.status_code, 200)

    def test_other_questions_token_does_not_reveal_this_answer(self):
        """다른 문제의 토큰으로 이 문제 보기를 채점해도 정답 정보를 못 얻는다.

        토큰에 담긴 보기 넷 안에서만 정답을 찾으므로, 남의 보기 id 는
        어느 것과도 맞지 않아 오답이 된다.
        """
        q1 = self.client.get(QUIZ_URL).json()
        q2 = self.client.get(QUIZ_URL, {"exclude": str(q1["choices"][0]["id"])}).json()

        res = self.grade(token=q1["token"], picked=q2["choices"][0]["id"])

        self.assertLess(res.status_code, 500)

    def test_picked_of_any_type_is_not_500(self):
        """picked 는 사용자가 보내는 값이라 무엇이든 들어온다."""
        token = self.client.get(QUIZ_URL).json()["token"]

        for picked in ["1", None, [], {}, {"a": 1}, 1.5, 10**30, -(10**30), "9" * 400]:
            with self.subTest(picked=str(picked)[:20]):
                res = self.grade(token=token, picked=picked)
                self.assertEqual(res.status_code, 200, f"picked={picked!r}")
                self.assertFalse(res.json()["correct"], f"picked={picked!r} 가 정답 처리됨")

    def test_forged_payload_cannot_mark_anything_correct(self):
        """서명을 못 만들면 지문을 맞출 수 없다.

        salt 를 알아도 SECRET_KEY 가 없으면 signing.dumps 를 못 한다.
        여기서는 SECRET_KEY 가 있는 테스트라 서명은 되지만, 지문 자리에
        아무 값이나 넣으면 보기 넷 중 어느 것과도 맞지 않는다.
        """
        token = signing.dumps(
            {"a": "0" * 64, "n": "nonce", "c": [1, 2, 3, 4]},
            salt="vocab.quiz.answer",
        )

        self.assertEqual(self.grade(token=token, picked=1).status_code, 400)

    def test_forged_choice_list_does_not_500(self):
        """보기 자리에 이상한 값이 들어와도 버텨야 한다."""
        for choices in [[], [1] * 10000, ["a", "b"], [None], [[1]], [{"x": 1}]]:
            with self.subTest(c=str(choices)[:30]):
                token = signing.dumps(
                    {"a": "x" * 64, "n": "n", "c": choices},
                    salt="vocab.quiz.answer",
                )
                res = self.grade(token=token, picked=1)
                self.assertLess(res.status_code, 500, f"c={str(choices)[:40]}")

    def test_missing_token_field_is_400(self):
        self.assertEqual(self.grade(picked=1).status_code, 400)

    def test_form_encoded_body_is_400_not_500(self):
        res = self.post("picked=1", content_type="application/x-www-form-urlencoded")

        self.assertEqual(res.status_code, 400)


class GradeReviewGateTest(TestCase):
    """채점 경로의 검수 게이트. 익명도 staff 도 미검수를 못 본다."""

    @classmethod
    def setUpTestData(cls):
        make_words(20)
        cls.hidden = Word.objects.create(
            term="ZZ-secret-unreviewed",
            meaning="미검수 뜻",
            description="아무도 확인하지 않은 설명",
            category="git",
            is_reviewed=False,
        )

    def grade_hidden(self):
        return self.client.post(
            GRADE_URL,
            {"token": sign(self.hidden.pk), "picked": self.hidden.pk},
            content_type="application/json",
        )

    def test_anonymous_cannot_grade_into_unreviewed(self):
        res = self.grade_hidden()

        self.assertEqual(res.status_code, 404)
        self.assertNotIn("아무도 확인하지 않은", res.content.decode())

    def test_staff_cannot_grade_into_unreviewed(self):
        """목록은 미검수를 보여주지만 채점 해설은 안 된다."""
        self.client.force_login(
            get_user_model().objects.create_user(
                username="grade-staff", password="x", is_staff=True
            )
        )

        res = self.grade_hidden()

        self.assertEqual(res.status_code, 404)
        self.assertNotIn("아무도 확인하지 않은", res.content.decode())

    def test_superuser_cannot_grade_into_unreviewed(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(
                username="grade-super", password="x", email="a@b.c"
            )
        )

        self.assertEqual(self.grade_hidden().status_code, 404)

    def test_superuser_quiz_never_shows_unreviewed(self):
        """staff 뿐 아니라 superuser 도 미검수를 문제로 받지 않는다."""
        self.client.force_login(
            get_user_model().objects.create_superuser(
                username="quiz-super", password="x", email="b@c.d"
            )
        )

        for _ in range(30):
            self.assertNotIn(
                "ZZ-secret", self.client.get(QUIZ_URL).content.decode()
            )

    def test_word_unreviewed_after_question_issued_gives_404(self):
        """문제를 낸 뒤 검수가 취소되면 정답을 알려주지 않는다."""
        q = self.client.get(QUIZ_URL).json()
        Word.objects.update(is_reviewed=False)

        res = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 404)


class GradeResponseShapeTest(TestCase):
    """채점 응답 스키마. 프론트 GradeResult 타입과 어긋나면 런타임 undefined 다."""

    @classmethod
    def setUpTestData(cls):
        make_words(20)

    def test_word_carries_exactly_the_fields_frontend_expects(self):
        """frontend/src/lib/api/quiz.ts 의 GradeResult.word 와 짝을 맞춘다."""
        q = self.client.get(QUIZ_URL).json()

        body = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        self.assertEqual(set(body), {"correct", "answer_id", "word"})
        self.assertEqual(
            set(body["word"]),
            {
                "id",
                "term",
                "pronunciation",
                "meaning",
                "description",
                "example",
                "example_translation",
                "category",
            },
        )

    def test_grade_does_not_leak_review_workflow_fields(self):
        """채점은 익명 경로다. 검수 상태나 출처를 흘리면 안 된다."""
        q = self.client.get(QUIZ_URL).json()

        body = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        for field in ["is_reviewed", "source", "created_at", "updated_at"]:
            self.assertNotIn(field, body["word"], f"{field} 가 새어나갔다")

    def test_question_response_shape(self):
        """프론트 Question 타입과 짝. 정답 자리가 없어야 한다."""
        body = self.client.get(QUIZ_URL).json()

        self.assertEqual(
            set(body),
            {
                "kind",
                "kind_label",
                "question",
                "prompt",
                "category",
                "category_label",
                "choices",
                "token",
            },
        )
        for choice in body["choices"]:
            self.assertEqual(set(choice), {"id", "text"})
