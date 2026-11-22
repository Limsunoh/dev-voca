"""닉네임 오류 문구를 실제 API·관리자 화면·마이그레이션으로 두드려 본다.

계약:
  - 가입(POST /signup/)과 내정보 수정(PATCH /me/)은 닉네임 문제를 네 문구로만 알린다.
    빈 값 / 12자 초과 / 금칙어 / 남이 쓰는 닉네임(대소문자만 달라도).
  - 검사를 지나 DB 제약에 걸린 경우(경합)도 같은 "이미 쓰고 있는 닉네임입니다." 다.
    이메일 탓으로 돌리거나 500 이 되면 안 된다.
  - 옛 말 "이름" 이 응답 어디에도 남지 않는다.
  - 지금 쓰는 닉네임을 그대로 보내면(금칙어가 든 운영 계정 이름이어도) 막지 않는다.
  - 관리자 사용자 폼의 중복 오류와 칸 라벨·설명도 "닉네임" 이다.
  - 마이그레이션 0011 은 verbose_name 만 바꾼다. 앞뒤로 오갈 수 있고 SQL 이 없다.
"""

import io
import json
import threading
import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.accounts import serializers as account_serializers
from apps.accounts.models import DISPLAY_NAME_MAX, LoginToken

from .tests import CONSENT, ME_URL, PASSWORD, SIGNUP_URL

User = get_user_model()

EMPTY = "닉네임을 입력해주세요."
TOO_LONG = f"닉네임은 {DISPLAY_NAME_MAX}자까지 쓸 수 있습니다."
FORBIDDEN = "쓸 수 없는 닉네임입니다. 다른 닉네임을 입력해주세요."
TAKEN = "이미 쓰고 있는 닉네임입니다."
OLD_WORD = "이름"

# NFC 로 다듬으면 두 글자로 늘어나는 글자(데바나가리 qa, 합성 제외 목록에 있다).
# 다듬기는 보통 글자를 줄이기만 해서, 우리 길이 문구에 닿는 값은 이런 것뿐이다.
NFC_GROWS = "\u0958"


def body_text(res) -> str:
    """응답 본문을 사람이 읽는 글자 그대로. \\uXXXX 로 숨은 옛 말도 잡는다."""
    return json.dumps(res.json(), ensure_ascii=False)


class NicknameApiMixin:
    """가입·내정보 수정 호출과 문구 단정."""

    def signup(self, display_name, email="new@example.com"):
        payload = {
            "email": email,
            "password": PASSWORD,
            "display_name": display_name,
            **CONSENT,
        }
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def patch_me(self, user, display_name, client=None):
        token = LoginToken.objects.create(user=user)
        return (client or self.client).patch(
            ME_URL,
            {"display_name": display_name},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

    def assertNicknameError(self, res, message):
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.json(), {"display_name": [message]})
        self.assertNotIn(OLD_WORD, body_text(res))

    def assertTooLongRejected(self, res):
        """글자 그대로 12자를 넘긴 값은 400 이고 옛 말이 없다.

        문구는 단정하지 않는다. ModelSerializer 가 모델의 max_length 로 만든 칸이
        다듬기 전에 먼저 막아 DRF 기본 문구("이 필드의 글자 수가 12 이하인지
        확인하세요.")가 나간다. 다듬기는 글자를 줄이기만 해서, 우리 문구(TOO_LONG)는
        NFC 로 늘어나는 드문 글자에만 닿는다(test_다듬으면_길어지는_값은_닉네임_길이_문구다).
        """
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(list(res.json()), ["display_name"])
        self.assertNotIn(OLD_WORD, body_text(res))


class SignUpNicknameMessageTest(NicknameApiMixin, TestCase):
    """가입 API 가 닉네임 문제마다 정해진 문구를 내는지."""

    @classmethod
    def setUpTestData(cls):
        cls.holder = User.objects.create_user(
            email="holder@example.com", password=PASSWORD, display_name="DevKim"
        )

    def setUp(self):
        cache.clear()

    def test_공백만_보내면_입력해달라는_문구다(self):
        for value in ("", "   ", "\u3000", "\u3164\u3164", "\u200b"):
            with self.subTest(repr(value)):
                self.assertNicknameError(self.signup(value), EMPTY)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_13자는_막히고_12자는_가입된다(self):
        self.assertTooLongRejected(self.signup("가" * (DISPLAY_NAME_MAX + 1)))

        res = self.signup("가" * DISPLAY_NAME_MAX)

        self.assertEqual(res.status_code, 201, res.content)

    def test_다듬으면_길어지는_값은_닉네임_길이_문구다(self):
        """원문 12자인데 NFC 로 다듬으면 24자가 되는 값."""
        self.assertNicknameError(self.signup(NFC_GROWS * DISPLAY_NAME_MAX), TOO_LONG)

    def test_앞뒤_공백은_다듬은_뒤에_센다(self):
        """다듬기 전 길이로 세면 12자 닉네임이 공백 때문에 억울하게 막힌다."""
        res = self.signup("  " + "나" * DISPLAY_NAME_MAX + "  ")

        self.assertEqual(res.status_code, 201, res.content)

    def test_금칙어는_쓸_수_없다는_문구다(self):
        for value in ("관리자", "ADMIN운영자", "ＡＤＭＩＮ관리자", "dev voca"):
            with self.subTest(value):
                self.assertNicknameError(self.signup(value), FORBIDDEN)

    def test_남이_쓰는_닉네임은_대소문자만_달라도_막힌다(self):
        for value in ("DevKim", "devkim", "DEVKIM", " dEvKiM "):
            with self.subTest(value):
                self.assertNicknameError(self.signup(value), TAKEN)

    def test_닉네임_칸이_문자열이_아니면_400이다(self):
        for value in ({"a": 1}, ["x"]):
            with self.subTest(repr(value)):
                res = self.signup(value)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("display_name", res.json())


class MeNicknameMessageTest(NicknameApiMixin, TestCase):
    """내정보 수정 API 가 닉네임 문제마다 정해진 문구를 내는지."""

    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_user(
            email="me@example.com", password=PASSWORD, display_name="나의닉"
        )
        cls.holder = User.objects.create_user(
            email="holder@example.com", password=PASSWORD, display_name="DevKim"
        )

    def setUp(self):
        cache.clear()

    def assertMine(self, name):
        self.me.refresh_from_db()
        self.assertEqual(self.me.display_name, name)

    def test_공백만_보내면_입력해달라는_문구다(self):
        for value in ("", "   ", "\u3164", "\u2800\u2800"):
            with self.subTest(repr(value)):
                self.assertNicknameError(self.patch_me(self.me, value), EMPTY)
        self.assertMine("나의닉")

    def test_13자는_막힌다(self):
        self.assertTooLongRejected(self.patch_me(self.me, "a" * (DISPLAY_NAME_MAX + 1)))
        self.assertMine("나의닉")

    def test_아주_긴_값도_500이_아니라_400이다(self):
        self.assertTooLongRejected(self.patch_me(self.me, "가" * 5000))

    def test_다듬으면_길어지는_값은_닉네임_길이_문구다(self):
        self.assertNicknameError(self.patch_me(self.me, NFC_GROWS * DISPLAY_NAME_MAX), TOO_LONG)
        self.assertMine("나의닉")

    def test_금칙어는_쓸_수_없다는_문구다(self):
        self.assertNicknameError(self.patch_me(self.me, "운영팀장"), FORBIDDEN)
        self.assertMine("나의닉")

    def test_남이_쓰는_닉네임은_대소문자만_달라도_막힌다(self):
        for value in ("DevKim", "devkim", "DEVKIM"):
            with self.subTest(value):
                self.assertNicknameError(self.patch_me(self.me, value), TAKEN)
        self.assertMine("나의닉")

    def test_지금_닉네임을_그대로_보내면_통과한다(self):
        res = self.patch_me(self.me, "나의닉")

        self.assertEqual(res.status_code, 200, res.content)
        self.assertMine("나의닉")

    def test_관리자가_정해준_금칙어_닉네임도_그대로_보내면_통과한다(self):
        """운영 계정이 아바타만 바꿀 때도 닉네임을 함께 보낸다. 막으면 아무것도 못 바꾼다."""
        User.objects.filter(pk=self.me.pk).update(display_name="관리자")

        res = self.patch_me(self.me, "관리자")

        self.assertEqual(res.status_code, 200, res.content)
        self.assertMine("관리자")

    def test_내_닉네임의_대소문자만_바꾸는_것은_통과한다(self):
        User.objects.filter(pk=self.me.pk).update(display_name="MyNick")

        res = self.patch_me(self.me, "mynick")

        self.assertEqual(res.status_code, 200, res.content)
        self.assertMine("mynick")

    def test_미인증은_401이고_닉네임_검사까지_안_간다(self):
        res = self.client.patch(
            ME_URL, {"display_name": ""}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 401)


class NicknameIntegrityErrorTest(NicknameApiMixin, TransactionTestCase):
    """검사를 지나 DB 제약에 걸린 쪽의 문구.

    중복 검사(name_taken)를 꺼서, 앞 단계가 못 본 경합을 그대로 만든다.
    TestCase 는 IntegrityError 뒤 트랜잭션이 깨져 이후 조회가 터지므로 쓰지 않는다.
    """

    def setUp(self):
        cache.clear()
        self.holder = User.objects.create_user(
            email="holder@example.com", password=PASSWORD, display_name="겹칠닉"
        )

    def no_precheck(self):
        return mock.patch.object(account_serializers, "name_taken", return_value=False)

    def test_가입이_DB_제약에_걸리면_닉네임_중복_문구다(self):
        with self.no_precheck():
            res = self.signup("겹칠닉")

        self.assertNicknameError(res, TAKEN)
        self.assertEqual(User.objects.count(), 1)

    def test_가입이_대소문자만_다른_닉네임으로_DB_제약에_걸려도_같은_문구다(self):
        User.objects.filter(pk=self.holder.pk).update(display_name="RaceNick")

        with self.no_precheck():
            res = self.signup("racenick")

        self.assertNicknameError(res, TAKEN)

    def test_내정보_수정이_DB_제약에_걸리면_닉네임_중복_문구다(self):
        me = User.objects.create_user(
            email="me@example.com", password=PASSWORD, display_name="원래닉"
        )

        with self.no_precheck():
            res = self.patch_me(me, "겹칠닉")

        self.assertNicknameError(res, TAKEN)
        me.refresh_from_db()
        self.assertEqual(me.display_name, "원래닉")


@unittest.skipUnless(connection.vendor == "postgresql", "동시 저장은 PostgreSQL 에서만 본다")
class NicknameRaceTest(NicknameApiMixin, TransactionTestCase):
    """두 사람이 같은 닉네임을 동시에 저장한다.

    누가 이기는지는 스레드 타이밍에 달렸다. 늘 성립하는 것만 본다:
    성공은 하나뿐이고, 진 쪽은 500 이 아니라 닉네임 중복 문구다.
    두 요청이 같은 지점(중복 검사 직후)에서 만나도록 name_taken 을 장벽으로 감싼다.
    """

    def setUp(self):
        cache.clear()

    def run_pair(self, call_a, call_b):
        barrier = threading.Barrier(2, timeout=10)
        real = account_serializers.name_taken

        def gated(*args, **kwargs):
            result = real(*args, **kwargs)
            barrier.wait()
            return result

        results = {}

        def worker(key, call):
            try:
                results[key] = call()
            finally:
                connection.close()

        with mock.patch.object(account_serializers, "name_taken", side_effect=gated):
            threads = [
                threading.Thread(target=worker, args=("a", call_a)),
                threading.Thread(target=worker, args=("b", call_b)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        return [results["a"], results["b"]]

    def assertOneWins(self, responses, ok_status):
        codes = sorted(r.status_code for r in responses)
        self.assertEqual(codes, sorted([ok_status, 400]), [r.content for r in responses])
        loser = next(r for r in responses if r.status_code == 400)
        self.assertNicknameError(loser, TAKEN)

    def test_동시_가입_같은_닉네임(self):
        responses = self.run_pair(
            lambda: self.client_class().post(
                SIGNUP_URL,
                {"email": "a@example.com", "password": PASSWORD, "display_name": "동시닉", **CONSENT},
                content_type="application/json",
            ),
            lambda: self.client_class().post(
                SIGNUP_URL,
                {"email": "b@example.com", "password": PASSWORD, "display_name": "동시닉", **CONSENT},
                content_type="application/json",
            ),
        )

        self.assertOneWins(responses, 201)
        self.assertEqual(User.objects.filter(display_name__iexact="동시닉").count(), 1)

    def test_동시_수정_같은_닉네임(self):
        a = User.objects.create_user(email="a@example.com", password=PASSWORD, display_name="에이")
        b = User.objects.create_user(email="b@example.com", password=PASSWORD, display_name="비이")
        ta = LoginToken.objects.create(user=a).key
        tb = LoginToken.objects.create(user=b).key

        def patch(key, name):
            return lambda: self.client_class().patch(
                ME_URL,
                {"display_name": name},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {key}",
            )

        responses = self.run_pair(patch(ta, "동시닉"), patch(tb, "동시닉"))

        self.assertOneWins(responses, 200)
        self.assertEqual(User.objects.filter(display_name__iexact="동시닉").count(), 1)


class AdminNicknameFormTest(TestCase):
    """관리자 사용자 변경 화면의 닉네임 칸."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password=PASSWORD, display_name="총괄"
        )
        cls.holder = User.objects.create_user(
            email="holder@example.com", password=PASSWORD, display_name="DevKim"
        )
        cls.member = User.objects.create_user(
            email="member@example.com", password=PASSWORD, display_name="회원닉"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def change_url(self, user):
        return f"/admin/accounts/user/{user.pk}/change/"

    def post_change(self, user, **changes):
        data = {
            "email": user.email,
            "display_name": user.display_name,
            "avatar": "",
            "google_picture": "",
            "is_active": "on",
            **changes,
        }
        return self.client.post(self.change_url(user), data)

    def test_중복_닉네임은_새_문구의_폼_오류다(self):
        for value in ("DevKim", "devkim", " DEVKIM "):
            with self.subTest(value):
                res = self.post_change(self.member, display_name=value)
                self.assertEqual(res.status_code, 200)
                errors = res.context["adminform"].form.errors
                self.assertEqual(errors.get("display_name"), [TAKEN])
                self.assertContains(res, TAKEN)
        self.member.refresh_from_db()
        self.assertEqual(self.member.display_name, "회원닉")

    def test_자기_닉네임_그대로_저장은_통과한다(self):
        res = self.post_change(self.member)

        self.assertEqual(res.status_code, 302)

    def test_칸_라벨과_설명이_닉네임이고_옛_말이_없다(self):
        res = self.client.get(self.change_url(self.member))

        self.assertEqual(res.status_code, 200)
        form = res.context["adminform"].form
        self.assertEqual(form.fields["display_name"].label, "닉네임")
        self.assertContains(res, "닉네임은 대소문자를 구분하지 않고 중복될 수 없습니다.")
        self.assertNotContains(res, "보여지는 이름")

    def test_목록_화면의_열_머리도_닉네임이다(self):
        res = self.client.get("/admin/accounts/user/")

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "닉네임")
        self.assertNotContains(res, "보여지는 이름")

    def test_모델_verbose_name(self):
        self.assertEqual(User._meta.get_field("display_name").verbose_name, "닉네임")


class NicknameMigrationTest(TransactionTestCase):
    """0011 은 verbose_name 만 바꾼다. 앞뒤로 오가고, 운영 DB 에 날릴 SQL 이 없다."""

    def field_label_at(self, target):
        executor = MigrationExecutor(connection)
        state = executor.loader.project_state(target)
        return state.apps.get_model("accounts", "User")._meta.get_field("display_name").verbose_name

    def test_0011_의_상태는_닉네임이고_0010_은_옛_말이다(self):
        self.assertEqual(self.field_label_at([("accounts", "0011_alter_user_display_name")]), "닉네임")
        self.assertEqual(self.field_label_at([("accounts", "0010_copy_drf_tokens")]), "보여지는 이름")

    def test_되돌렸다가_다시_적용된다(self):
        User.objects.create_user(email="keep@example.com", password=PASSWORD, display_name="남을닉")
        out = io.StringIO()
        try:
            call_command("migrate", "accounts", "0010", stdout=out, verbosity=1)
            self.assertIn("Unapplying accounts.0011_alter_user_display_name", out.getvalue())
        finally:
            call_command("migrate", "accounts", stdout=out, verbosity=1)
        self.assertIn("Applying accounts.0011_alter_user_display_name", out.getvalue())
        self.assertEqual(User.objects.get(email="keep@example.com").display_name, "남을닉")

    def test_SQL_이_없다(self):
        out = io.StringIO()
        call_command("sqlmigrate", "accounts", "0011", stdout=out)
        sql = [
            line for line in out.getvalue().splitlines()
            if line.strip() and not line.strip().startswith("--")
            and line.strip().upper() not in ("BEGIN;", "COMMIT;")
        ]
        self.assertEqual(sql, [])
