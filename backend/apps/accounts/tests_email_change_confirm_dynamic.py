"""이메일 변경 확인이 누구에게 로그인 토큰을 주는가를 깨뜨려 본다(views.EmailChangeConfirmView).

링크만 가진 사람(로그인 없음, 다른 계정)은 주소를 바꾸지만 토큰을 못 받는다. 같은 계정의
로그인 토큰(이어 받은 새 토큰 포함)을 실은 요청만 받는다. 죽은 토큰·비활성 계정·동시에
두 번 누르기에서 주소와 남은 LoginToken 을 본다.

확인 흐름의 기본 테스트는 tests.EmailChangeTest 와 tests_email_token 에 있다.
"""

from __future__ import annotations

import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from .email_change import make_token
from .models import (
    LoginToken,
)
from .tests import EMAIL_CHANGE_CONFIRM_URL, ME_URL, PASSWORD

User = get_user_model()

OLD = "owner.1125@example.com"
NEW = "next.1125@example.com"


class ConfirmMixin:
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=OLD, password=PASSWORD)
        self.login = LoginToken.objects.create(user=self.user)
        self.link = make_token(
            user_id=self.user.pk, current_email=OLD, new_email=NEW, device=self.login.device
        )

    def confirm(self, login_key: str | None = None, client: Client | None = None):
        auth = {"HTTP_AUTHORIZATION": f"Token {login_key}"} if login_key else {}
        return (client or self.client).post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": self.link}, content_type="application/json", **auth
        )

    def email(self) -> str:
        self.user.refresh_from_db()
        return self.user.email


class ConfirmTokenGrantTest(ConfirmMixin, TestCase):
    def test_로그인_없이_누르면_주소는_바뀌고_토큰은_없다(self):
        res = self.confirm()

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("token", res.json())
        self.assertEqual(res.json()["user"]["email"], NEW)
        self.assertEqual(self.email(), NEW)
        # 옛 로그인은 끊기고 새로 만든 것도 없다.
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_다른_계정_토큰으로_누르면_토큰은_없고_그_계정은_그대로다(self):
        other = User.objects.create_user(email="other.1125@example.com", password=PASSWORD)
        other_login = LoginToken.objects.create(user=other)

        res = self.confirm(other_login.key)

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("token", res.json())
        self.assertEqual(self.email(), NEW)
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())
        # 누른 사람의 로그인은 살아 있고 남의 계정으로 바뀌지 않았다.
        self.assertEqual(LoginToken.objects.filter(user=other).count(), 1)
        me = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {other_login.key}")
        self.assertEqual(me.json()["email"], "other.1125@example.com")

    def test_같은_계정_토큰으로_누르면_새_토큰을_받고_옛_토큰은_죽는다(self):
        res = self.confirm(self.login.key)

        self.assertEqual(res.status_code, 200)
        new_key = res.json()["token"]
        self.assertNotEqual(new_key, self.login.key)
        self.assertEqual(self.email(), NEW)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {self.login.key}").status_code, 401
        )
        me = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {new_key}")
        self.assertEqual(me.json()["email"], NEW)

    def test_같은_계정의_다른_기기_토큰도_받는다(self):
        """신청한 기기와 누른 기기가 달라도 같은 계정이면 준다(메일을 폰에서 연 경우)."""
        phone = LoginToken.objects.create(user=self.user)

        res = self.confirm(phone.key)

        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.json())
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)

    def test_이어_받은_새_토큰으로_누르면_받는다(self):
        LoginToken.objects.filter(pk=self.login.pk).update(
            created=timezone.now() - timedelta(days=2)
        )
        aged = LoginToken.objects.get(pk=self.login.pk)
        aged.key = self.login.key
        renewed = aged.renew()
        self.assertNotEqual(renewed.pk, aged.pk)

        res = self.confirm(renewed.key)

        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.json())
        self.assertEqual(self.email(), NEW)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)

    def test_죽은_토큰을_실으면_401_이고_주소는_그대로다(self):
        """화면은 /me 로 확인된 토큰만 싣는다. 직접 실으면 인증이 먼저 막는다."""
        dead = "x" * 40

        res = self.confirm(dead)

        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.email(), OLD)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)

    def test_만료된_같은_계정_토큰도_401_이고_주소는_그대로다(self):
        LoginToken.objects.filter(pk=self.login.pk).update(
            created=timezone.now() - timedelta(days=31)
        )

        res = self.confirm(self.login.key)

        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.email(), OLD)

    def test_비활성_계정은_로그인_없이도_400(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        res = self.confirm()

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "사용할 수 없는 계정입니다.")
        self.assertNotIn("token", res.json())
        self.assertEqual(self.email(), OLD)

    def test_비활성_계정_자기_토큰을_실으면_401(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        res = self.confirm(self.login.key)

        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.email(), OLD)

    def test_같은_링크를_두_번_누르면_두_번째는_400_이고_토큰이_없다(self):
        self.assertEqual(self.confirm(self.login.key).status_code, 200)

        again = self.confirm()

        self.assertEqual(again.status_code, 400)
        self.assertNotIn("token", again.json())

    def test_세션으로_로그인한_같은_계정도_csrf_없이는_못_받는다(self):
        """SessionAuthentication 이 켜져 있다. 다른 사이트가 세션 쿠키로 보내면 CSRF 가 막는다."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        res = self.confirm(client=client)

        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.email(), OLD)


class ConfirmRaceTest(TransactionTestCase):
    """같은 계정 토큰으로 동시에 두 번 누른다. 성공은 하나뿐이고 토큰도 하나만 남는다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=OLD, password=PASSWORD)
        self.login = LoginToken.objects.create(user=self.user)
        self.link = make_token(
            user_id=self.user.pk, current_email=OLD, new_email=NEW, device=self.login.device
        )

    def test_동시에_두_번_눌러도_성공은_하나고_토큰은_하나만_남는다(self):
        barrier = threading.Barrier(3)
        results = []
        lock = threading.Lock()

        def press(login_key):
            try:
                barrier.wait(timeout=10)
                auth = {"HTTP_AUTHORIZATION": f"Token {login_key}"} if login_key else {}
                res = Client(raise_request_exception=False).post(
                    EMAIL_CHANGE_CONFIRM_URL,
                    {"token": self.link},
                    content_type="application/json",
                    **auth,
                )
                with lock:
                    results.append((res.status_code, "token" in res.json()))
            finally:
                connections.close_all()

        # 같은 계정 둘, 로그인 없는 쪽 하나.
        threads = [
            threading.Thread(target=press, args=(k,))
            for k in (self.login.key, self.login.key, None)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        statuses = sorted(code for code, _ in results)
        self.assertEqual(len(results), 3)
        self.assertNotIn(500, statuses)
        self.assertEqual(statuses.count(200), 1, results)
        # 토큰은 성공한 쪽이 같은 계정이었을 때만, 하나만 나간다.
        granted = [has for code, has in results if code == 200 and has]
        self.assertLessEqual(len(granted), 1)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), len(granted))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)


# ---------------------------------------------------------------------------
# 프로필 사진
# ---------------------------------------------------------------------------
