"""로그인 토큰 30일 만료(LoginToken.LIFETIME)를 실제 흐름으로 깨뜨려 보는 테스트.

tests_daily_cleanup.py 의 LoginTokenExpiryTest 가 "만든 토큰의 나이" 로 경계를 본다면,
여기는 로그인·비밀번호 변경·이메일 변경 확인으로 실제로 받은 토큰을 쓴다. 약속:
  - 쿠키(30일)가 살아 있는 기기의 토큰은 지우지 않는다. 30일이 지난 것만 지운다.
  - 다른 기기·다른 회원의 토큰, 다른 정리 대상(1년 미접속 파기)에 영향이 없다.
  - 비밀번호·이메일 변경으로 새로 받은 토큰은 그 시각부터 30일이다.
  - 메일이 실패해 명령이 CommandError 로 끝나도 토큰 삭제는 이미 끝나 있다.
  - 미리 보기는 아무것도 쓰지 않는다.

시계: LoginToken.created 의 default 는 모델을 읽을 때 잡은 timezone.now 함수 자체라,
django.utils.timezone.now 를 패치해도 새 토큰의 발급 시각은 실제 시계로 찍힌다.
그래서 로그인 같은 동작은 실제 시각에 하고, 정리를 돌릴 때만 시계를 앞으로 민다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import LoginToken
from apps.accounts.tests import EMAIL_CHANGE_CONFIRM_URL, EMAIL_CHANGE_URL, PASSWORD
from apps.accounts.tests_password import NEW_PASSWORD, PASSWORD_URL
from apps.learning.tests_daily_cleanup import (
    LOGIN_URL,
    ME_URL,
    PurgeTestBase,
    writes_in,
)

User = get_user_model()

LIFETIME = timedelta(days=30)


def auth(key: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Token {key}"}


class RealClockBase(PurgeTestBase):
    """PurgeTestBase 의 고정 시계를 실제 지금으로 맞춘다. 토큰 발급 시각과 같은 축이다."""

    def setUp(self):
        super().setUp()
        self.clock = datetime.now(UTC)
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def login(self, email="owner@example.com") -> LoginToken:
        res = self.client.post(
            LOGIN_URL, {"email": email, "password": PASSWORD}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        return LoginToken.objects.get(key=res.json()["token"])

    def aged(self, user, age: timedelta) -> LoginToken:
        """age 만큼 전에 발급한 토큰. 실제 지금 기준이다."""
        return LoginToken.objects.create(user=user, created=datetime.now(UTC) - age)

    def me(self, key: str) -> int:
        return self.client.get(ME_URL, **auth(key)).status_code

    def at(self, moment: datetime) -> None:
        self.clock = moment

    def alive(self, token: LoginToken) -> bool:
        return LoginToken.objects.filter(pk=token.pk).exists()


class LoginFlowExpiryTest(RealClockBase):
    """로그인해서 받은 토큰이 30일 경계에서 어떻게 되는가."""

    def test_29일_23시간_뒤의_정리는_토큰을_남기고_그_토큰으로_계속_쓴다(self):
        token = self.login()

        self.at(token.created + timedelta(days=29, hours=23))
        output = self.apply()

        self.assertIn("로그인 토큰 0개", output)
        self.assertTrue(self.alive(token))
        self.assertEqual(self.me(token.key), 200)

    def test_딱_30일인_순간의_정리도_지우지_않는다(self):
        """쿠키는 토큰보다 조금 늦게 붙어 이 순간에는 아직 살아 있다. 지우면 그 기기가 끊긴다."""
        token = self.login()

        self.at(token.created + LIFETIME)
        self.apply()

        self.assertTrue(self.alive(token))

    def test_30일_1초_뒤의_정리는_지우고_그_토큰은_401(self):
        token = self.login()

        self.at(token.created + LIFETIME + timedelta(seconds=1))
        output = self.apply()

        self.assertIn("로그인 토큰 1개", output)
        self.assertFalse(self.alive(token))
        self.assertEqual(self.me(token.key), 401)

    def test_기기_셋_중_30일_넘은_것만_지우고_남의_새_토큰은_남는다(self):
        old = self.aged(self.owner, timedelta(days=31))
        mid = self.aged(self.owner, timedelta(days=15))
        new = self.login()
        theirs_new = self.login("other@example.com")
        theirs_mid = self.aged(self.other, timedelta(days=29, hours=23))

        self.apply()

        left = set(LoginToken.objects.values_list("pk", flat=True))
        self.assertEqual(left, {mid.pk, new.pk, theirs_new.pk, theirs_mid.pk})
        self.assertEqual(self.me(old.key), 401)
        for token in (mid, new, theirs_new, theirs_mid):
            self.assertEqual(self.me(token.key), 200)

    def test_오래된_기기가_지워져도_계정과_다른_기기는_그대로다(self):
        old = self.aged(self.owner, timedelta(days=45))
        new = self.login()

        self.apply()

        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertEqual(self.me(old.key), 401)
        self.assertEqual(self.me(new.key), 200)

    def test_이틀_연속_돌려도_두_번째는_0개다(self):
        self.aged(self.owner, timedelta(days=31))
        self.assertIn("로그인 토큰 1개", self.apply())

        self.at(self.clock + timedelta(days=1))
        self.assertIn("로그인 토큰 0개", self.apply())


class ReissuedTokenTest(RealClockBase):
    """비밀번호·이메일 변경으로 새로 받은 토큰은 옛 토큰의 나이를 물려받지 않는다."""

    def assert_fresh_thirty_days(self, key: str, before: datetime) -> None:
        token = LoginToken.objects.get(key=key)
        self.assertGreaterEqual(token.created, before)

        self.at(token.created + LIFETIME - timedelta(seconds=1))
        self.apply()
        self.assertEqual(self.me(key), 200)

        self.at(token.created + LIFETIME + timedelta(seconds=1))
        self.apply()
        self.assertEqual(self.me(key), 401)

    def test_비밀번호를_바꾸면_새_토큰은_그_시각부터_30일이다(self):
        stale = self.aged(self.owner, timedelta(days=29))
        before = datetime.now(UTC)

        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(stale.key),
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.alive(stale))
        self.assert_fresh_thirty_days(res.json()["token"], before)

    def test_이메일_변경을_확인하면_새_토큰은_그_시각부터_30일이다(self):
        stale = self.aged(self.owner, timedelta(days=29))
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": "next@example.com", "current_password": PASSWORD},
                content_type="application/json",
                **auth(stale.key),
            )
        self.assertEqual(res.status_code, 202)
        link = sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]
        before = datetime.now(UTC)

        res = Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(self.alive(stale))
        self.assert_fresh_thirty_days(res.json()["token"], before)


class SameRunAsPurgeTest(RealClockBase):
    """1년 미접속 파기와 토큰 정리가 한 번에 돌 때."""

    def stale_member(self, name: str, **extra):
        """안내한 지 40일, 400일 안 쓴 회원. 이번 실행에서 지워진다."""
        user = User.objects.create_user(email=f"{name}@example.com", display_name=name)
        User.objects.filter(pk=user.pk).update(
            last_seen_on=self.today() - timedelta(days=400),
            purge_notice_sent_at=self.clock - timedelta(days=40),
            **extra,
        )
        return user

    def test_파기된_회원의_토큰은_파기로_사라지고_토큰_수에는_남의_것만_센다(self):
        gone = self.stale_member("gone")
        self.aged(gone, timedelta(days=60))
        self.aged(gone, timedelta(days=1))
        expired_mine = self.aged(self.owner, timedelta(days=31))
        fresh_mine = self.aged(self.owner, timedelta(days=1))

        # 미리 보기는 파기 전에 세서 파기될 회원의 오래된 토큰도 센다.
        self.assertIn("삭제 1명", self.run_cleanup())
        self.assertIn("로그인 토큰 2개", self.run_cleanup())
        self.assertEqual(LoginToken.objects.count(), 4)

        output = self.apply()

        # 파기가 먼저 돌아 그 회원의 토큰은 cascade 로 지워지고, 남은 것 중 만료만 센다.
        self.assertIn("삭제 1명", output)
        self.assertIn("로그인 토큰 1개", output)
        self.assertFalse(User.objects.filter(pk=gone.pk).exists())
        self.assertEqual(LoginToken.objects.filter(user_id=gone.pk).count(), 0)
        self.assertFalse(self.alive(expired_mine))
        self.assertEqual(self.me(fresh_mine.key), 200)

    def test_안내_메일이_못_나가_CommandError_여도_토큰은_이미_지워져_있다(self):
        expired = self.aged(self.owner, timedelta(days=31))
        fresh = self.aged(self.other, timedelta(days=1))
        # 안내할 회원이 있는데 발송 계정이 없다.
        needs_mail = User.objects.create_user(email="needs@example.com")
        User.objects.filter(pk=needs_mail.pk).update(
            last_seen_on=self.today() - timedelta(days=400)
        )
        self.purge_sends.return_value = False

        with self.assertRaises(CommandError):
            self.apply()

        self.assertFalse(self.alive(expired))
        self.assertTrue(self.alive(fresh))
        self.assertEqual(django_mail.outbox, [])

    def test_안내가_전부_실패해도_토큰은_이미_지워져_있다(self):
        expired = self.aged(self.owner, timedelta(days=31))
        needs_mail = User.objects.create_user(email="needs@example.com")
        User.objects.filter(pk=needs_mail.pk).update(
            last_seen_on=self.today() - timedelta(days=400)
        )

        with mock.patch(
            "apps.accounts.purge.send_account_mail", side_effect=OSError("down")
        ), self.assertLogs("apps.accounts.purge", "ERROR"), self.assertRaises(CommandError):
            self.apply()

        self.assertFalse(self.alive(expired))

    def test_정지된_회원의_오래된_토큰도_지운다(self):
        """파기 대상에서 빠지는 정지 계정도 토큰 정리에는 들어간다."""
        User.objects.filter(pk=self.other.pk).update(is_active=False)
        old = self.aged(self.other, timedelta(days=31))

        self.apply()

        self.assertFalse(self.alive(old))
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())


class PreviewWritesNothingTest(RealClockBase):
    """만료 토큰이 있어도 미리 보기는 쓰기 쿼리가 0 이다."""

    def test_미리_보기는_세기만_한다(self):
        expired = self.aged(self.owner, timedelta(days=40))
        fresh = self.login()

        with CaptureQueriesContext(connection) as captured:
            output = self.run_cleanup()

        self.assertEqual(writes_in(captured), [])
        self.assertIn("로그인 토큰 1개", output)
        self.assertEqual(self.me(expired.key), 200)
        self.assertEqual(self.me(fresh.key), 200)
