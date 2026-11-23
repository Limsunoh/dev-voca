"""닉네임 길이 안내를 깨뜨려 보는 테스트.

가입(POST /signup/)과 내정보 수정(PATCH /me/)이 같은 칸(display_name_field)과 같은
검사(validate_display_name)를 쓰는지, 경계에서 500 이나 DRF 기본 문구가 새지 않는지
본다.

계약:
- 다듬은 뒤(보이지 않는 글자·빈칸처럼 보이는 글자 제거, NFC) 12자를 넘으면
  {"display_name": ["닉네임은 12자까지 쓸 수 있습니다."]} 400.
- 원문이 64자를 넘어도 같은 문구 400(500 아님). 다듬으면 12자 이하라도 그렇다.
- 다듬으면 12자 이하이고 원문이 64자 이하면 통과하고, 다듬은 값이 저장된다.
- 빈 값·공백만·보이지 않는 글자만은 "닉네임을 입력해주세요.".
- 가입에서 display_name 을 아예 안 보내면 자동 생성.

보이지 않는 글자는 모두 \\u 이스케이프로 적는다. 실제 글자로 저장하면 편집기에서
안 보여 다음 사람이 모르고 지운다.
"""

from __future__ import annotations

import unicodedata

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import LoginToken

from .models import DISPLAY_NAME_MAX, GENERATED_NAME_PREFIX
from .tests import CONSENT, ME_URL, PASSWORD, SIGNUP_URL

User = get_user_model()

TOO_LONG = {"display_name": ["닉네임은 12자까지 쓸 수 있습니다."]}
EMPTY = {"display_name": ["닉네임을 입력해주세요."]}

ZWSP = "\u200b"  # 폭 없는 공백(Cf)
HANGUL_FILLER = "\u3164"  # 한글 채움 문자. 글자로 분류되지만 빈칸으로 보인다
IDEOGRAPHIC_SPACE = "\u3000"


def nfd(text: str) -> str:
    """한글을 자모로 푼다. 한 글자가 둘~셋으로 늘어난다."""
    return unicodedata.normalize("NFD", text)


class _Paths:
    """가입과 내정보 수정을 같은 모양으로 부른다."""

    def setUp(self):
        # 가입·수정 요율 통이 테스트 사이에 이어지지 않게.
        cache.clear()

    def signup(self, body: dict, email: str = "new@example.com"):
        payload = {"email": email, "password": PASSWORD, **CONSENT, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def patch_me(self, body: dict):
        return self.client.patch(
            ME_URL,
            body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )


class NicknameLengthSignUpTest(_Paths, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD, display_name="임선오"
        )

    def assertRejected(self, name: str, expected: dict):
        res = self.signup({"display_name": name})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.json(), expected)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def assertAccepted(self, name: str, stored: str):
        res = self.signup({"display_name": name})
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(User.objects.get(email="new@example.com").display_name, stored)

    def test_exactly_twelve_passes(self):
        self.assertAccepted("가" * DISPLAY_NAME_MAX, "가" * DISPLAY_NAME_MAX)

    def test_thirteen_is_rejected_with_our_wording(self):
        """DRF 기본 문구("이 필드의 글자 수가...")가 아니라 우리 문구여야 한다."""
        self.assertRejected("가" * 13, TOO_LONG)
        self.assertRejected("a" * 13, TOO_LONG)

    def test_raw_just_over_outer_limit_is_rejected_not_500(self):
        self.assertRejected("가" * 65, TOO_LONG)

    def test_huge_raw_value_is_rejected_not_500(self):
        self.assertRejected("x" * 20_000, TOO_LONG)
        self.assertRejected(ZWSP * 20_000, TOO_LONG)

    def test_hidden_chars_trimmed_to_twelve_pass_at_raw_64(self):
        """원문 64자 = 바깥 상한 안. 다듬으면 12자라 통과하고 다듬은 값이 저장된다."""
        name = "가" * DISPLAY_NAME_MAX + ZWSP * (64 - DISPLAY_NAME_MAX)
        self.assertEqual(len(name), 64)
        self.assertAccepted(name, "가" * DISPLAY_NAME_MAX)

    def test_hidden_chars_trimmed_to_twelve_still_rejected_at_raw_65(self):
        """원문이 64자를 넘으면 다듬으면 짧아도 같은 문구로 막는다(계약)."""
        name = "가" * DISPLAY_NAME_MAX + ZWSP * (65 - DISPLAY_NAME_MAX)
        self.assertRejected(name, TOO_LONG)

    def test_hidden_chars_do_not_rescue_a_thirteen_char_name(self):
        self.assertRejected(ZWSP.join("가" * 13), TOO_LONG)

    def test_blank_looking_letters_are_not_counted(self):
        self.assertAccepted(HANGUL_FILLER * 3 + "가" * 12 + HANGUL_FILLER * 3, "가" * 12)

    def test_decomposed_hangul_counts_after_nfc(self):
        """자모로 풀린 12글자는 원문 24자지만 모으면 12자다."""
        self.assertEqual(len(nfd("가" * 12)), 24)
        self.assertRejected(nfd("가" * 13), TOO_LONG)
        self.assertAccepted(nfd("가" * 12), "가" * 12)

    def test_inner_spaces_collapse_before_counting(self):
        """"가 가" 사이 빈칸 여러 개는 하나로 세어진다."""
        self.assertAccepted("가가가가가" + " " * 10 + "가가가가가가", "가가가가가 가가가가가가")

    def test_empty_and_blank_only_say_enter_a_name(self):
        for name in ("", "   ", ZWSP * 3, HANGUL_FILLER * 2, IDEOGRAPHIC_SPACE * 2, "\t\n"):
            with self.subTest(name=repr(name)):
                cache.clear()
                self.assertRejected(name, EMPTY)

    def test_missing_name_is_generated(self):
        res = self.signup({})
        self.assertEqual(res.status_code, 201, res.content)
        name = User.objects.get(email="new@example.com").display_name
        self.assertTrue(name.startswith(GENERATED_NAME_PREFIX), name)
        self.assertLessEqual(len(name), DISPLAY_NAME_MAX)

    def test_wrong_types_are_400_not_500(self):
        for value in (None, ["가"], {"a": "b"}):
            with self.subTest(value=value):
                cache.clear()
                res = self.signup({"display_name": value})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("display_name", res.json())

    def test_forbidden_and_taken_wording_unchanged(self):
        self.assertRejected("admin", {"display_name": ["쓸 수 없는 닉네임입니다. 다른 닉네임을 입력해주세요."]})
        self.assertRejected("임선오", {"display_name": ["이미 쓰고 있는 닉네임입니다."]})
        # 보이지 않는 글자를 끼워도 같은 이름이다.
        self.assertRejected("임" + ZWSP + "선오", {"display_name": ["이미 쓰고 있는 닉네임입니다."]})


class NicknameLengthMeTest(_Paths, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="a@example.com", password=PASSWORD, display_name="테스터"
        )
        User.objects.create_user(email="b@example.com", password=PASSWORD, display_name="남의이름")
        cls.token = LoginToken.objects.create(user=cls.user)

    def assertRejected(self, name, expected: dict):
        res = self.patch_me({"display_name": name})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.json(), expected)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "테스터")

    def assertAccepted(self, name: str, stored: str):
        res = self.patch_me({"display_name": name})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["display_name"], stored)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, stored)

    def test_exactly_twelve_passes(self):
        self.assertAccepted("a" * 12, "a" * 12)

    def test_thirteen_is_rejected(self):
        self.assertRejected("가" * 13, TOO_LONG)

    def test_over_outer_limit_is_rejected_not_500(self):
        self.assertRejected("가" * 65, TOO_LONG)
        self.assertRejected("y" * 50_000, TOO_LONG)

    def test_hidden_chars_trimmed_to_twelve_pass(self):
        self.assertAccepted(ZWSP * 30 + "나" * 12 + ZWSP * 22, "나" * 12)

    def test_hidden_chars_over_raw_64_rejected(self):
        self.assertRejected(ZWSP * 60 + "나" * 5, TOO_LONG)

    def test_decomposed_hangul(self):
        self.assertAccepted(nfd("다" * 12), "다" * 12)

    def test_blank_only_says_enter_a_name(self):
        for name in ("", "  ", ZWSP, HANGUL_FILLER):
            with self.subTest(name=repr(name)):
                cache.clear()
                self.assertRejected(name, EMPTY)

    def test_null_and_wrong_types_are_400(self):
        for value in (None, ["x"], {"x": 1}):
            with self.subTest(value=value):
                cache.clear()
                res = self.patch_me({"display_name": value})
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("display_name", res.json())

    def test_patch_without_name_still_works(self):
        """아바타만 바꿀 때 이름이 필수로 바뀌면 안 된다."""
        res = self.patch_me({"avatar": "a2"})
        self.assertEqual(res.status_code, 200, res.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "테스터")

    def test_taken_wording_unchanged(self):
        self.assertRejected("남의이름", {"display_name": ["이미 쓰고 있는 닉네임입니다."]})

    def test_anonymous_patch_is_401(self):
        res = self.client.patch(ME_URL, {"display_name": "가" * 13}, content_type="application/json")
        self.assertEqual(res.status_code, 401)
