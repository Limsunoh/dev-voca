"""로그인 이어 가기(POST /api/accounts/token/renew/, LoginToken.renew).

계약:
  - 발급 하루가 안 된 토큰은 그대로 돌려준다. 하루가 지났으면 같은 device 의 새 토큰을 낸다.
  - 옛 토큰은 새 토큰이 처음 쓰일 때 바뀐 것으로 적히고, 그 뒤 REPLACED_GRACE 동안만 통한다.
    새 토큰을 실은 응답을 잃어 옛 토큰만 든 사람은 끊기지 않고, 다시 부르면 같은 새 토큰을 받는다.
  - 유예가 지난 옛 토큰이 다시 오면 그 로그인(device)을 통째로 끊는다.
  - 로그아웃은 같은 device 의 토큰을 다 지운다.
  - 이메일 변경 링크는 토큰이 바뀌어도 산다.
  - 매일 정리(expired)는 발급 30일만 본다. 유예가 지난 바뀐 토큰을 미리 지우면 그것이 다시
    왔을 때 새어 나간 것을 못 알아본다.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import LoginToken, token_digest
from .tests import EMAIL_CHANGE_CONFIRM_URL, EMAIL_CHANGE_URL, LOGOUT_URL, ME_URL, PASSWORD

User = get_user_model()
RENEW_URL = "/api/accounts/token/renew/"


def auth(key: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Token {key}"}


def after_grace():
    """바뀐 옛 토큰의 유예가 막 지난 시각으로 시계를 옮긴다."""
    later = timezone.now() + LoginToken.REPLACED_GRACE + timedelta(seconds=1)
    return mock.patch("django.utils.timezone.now", return_value=later)


class TokenRenewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="renew@example.com", password=PASSWORD)
        self.token = LoginToken.objects.create(user=self.user)

    def age(self, token: LoginToken, delta: timedelta) -> None:
        LoginToken.objects.filter(pk=token.pk).update(created=timezone.now() - delta)

    def renew(self, key: str):
        return self.client.post(RENEW_URL, **auth(key))

    def me(self, key: str) -> int:
        return self.client.get(ME_URL, **auth(key)).status_code

    def rotate(self) -> str:
        """하루 지난 토큰을 이어 가 새 토큰을 받는다."""
        self.age(self.token, timedelta(days=1, minutes=1))
        res = self.renew(self.token.key)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["token"]

    def test_하루가_안_된_토큰은_그대로다(self):
        res = self.renew(self.token.key)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["token"], self.token.key)
        self.assertEqual(res.json()["issued_at"], int(self.token.created.timestamp()))
        self.assertEqual(LoginToken.objects.count(), 1)

    def test_하루가_지나면_같은_device_의_새_토큰을_낸다(self):
        new = self.rotate()

        self.assertNotEqual(new, self.token.key)
        fresh = LoginToken.objects.get(digest=token_digest(new))
        self.assertEqual(fresh.device, self.token.device)
        self.assertFalse(fresh.delivered)

    def test_새_토큰이_쓰이기_전에는_옛_토큰이_유예_뒤에도_통하고_같은_새_토큰을_받는다(self):
        """새 토큰을 실은 응답을 잃은 경우. 옛 토큰만 든 사람이 끊기면 안 된다."""
        new = self.rotate()

        with after_grace():
            self.assertEqual(self.me(self.token.key), 200)
            self.assertEqual(self.renew(self.token.key).json()["token"], new)
        self.assertEqual(LoginToken.objects.count(), 2)

    def test_새_토큰이_처음_쓰이면_옛_토큰은_유예_뒤_죽는다(self):
        new = self.rotate()

        self.assertEqual(self.me(new), 200)

        old = LoginToken.objects.get(digest=token_digest(self.token.key))
        self.assertIsNotNone(old.replaced_at)
        self.assertTrue(LoginToken.objects.get(digest=token_digest(new)).delivered)
        self.assertEqual(self.me(self.token.key), 200)  # 유예 안
        with after_grace():
            self.assertEqual(self.me(new), 200)
            # 인증에서는 죽었지만 정리는 아직 안 지운다(재사용 감지에 쓴다).
            self.assertEqual(list(LoginToken.expired()), [])

    def test_유예가_지난_옛_토큰이_다시_오면_그_로그인을_통째로_끊는다(self):
        new = self.rotate()
        self.me(new)
        other_device = LoginToken.objects.create(user=self.user)

        with after_grace():
            self.assertEqual(self.me(self.token.key), 401)
            self.assertEqual(self.me(new), 401)
            self.assertEqual(self.me(other_device.key), 200)

    def test_다시_부르면_같은_새_토큰이다(self):
        self.age(self.token, timedelta(days=2))
        first = self.renew(self.token.key).json()["token"]

        again = self.renew(self.token.key).json()["token"]

        self.assertEqual(again, first)
        self.assertEqual(LoginToken.objects.count(), 2)

    def test_매일_정리가_돈_뒤에도_옛_토큰이_다시_오면_로그인을_끊는다(self):
        """빼 간 쪽이 먼저 이어 가 새 토큰을 쓰고, 원래 주인은 며칠 뒤 옛 토큰으로 온다."""
        new = self.rotate()
        self.me(new)
        later = timezone.now() + timedelta(days=3)
        with mock.patch("django.utils.timezone.now", return_value=later):
            LoginToken.expired().delete()  # 매일 정리
            self.assertEqual(self.me(self.token.key), 401)
            self.assertFalse(LoginToken.objects.filter(digest=token_digest(new)).exists())

    def test_배포_전_공유_토큰은_유예가_지나도_로그인을_끊지_않는다(self):
        """11-13 전에는 폰과 PC 가 토큰 하나를 나눠 썼다(0013 이 device 를 토큰 값으로 채우고 0016 이
        둘을 같은 지문으로 바꿈).
        폰이 이어 간 뒤 PC 가 그 값으로 와도 폰은 그대로다. PC 만 다시 로그인한다."""
        LoginToken.objects.filter(pk=self.token.pk).update(device=self.token.digest)
        self.token.refresh_from_db()
        new = self.rotate()
        self.me(new)

        with after_grace():
            self.assertEqual(self.me(self.token.key), 401)
            self.assertEqual(self.me(new), 200)

    def test_로그아웃은_바뀐_직전_토큰까지_지운다(self):
        new = self.rotate()
        self.me(new)
        other_device = LoginToken.objects.create(user=self.user)

        self.assertEqual(self.client.post(LOGOUT_URL, **auth(new)).status_code, 204)

        self.assertEqual(list(LoginToken.objects.values_list("digest", flat=True)), [other_device.digest])

    def test_30일_지난_토큰은_이어_갈_수_없다(self):
        self.age(self.token, timedelta(days=30, seconds=1))

        self.assertEqual(self.renew(self.token.key).status_code, 401)

    def test_토큰이_바뀌어도_이메일_변경_링크는_산다(self):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": "next@example.com", "current_password": PASSWORD},
                content_type="application/json",
                **auth(self.token.key),
            )
        self.assertEqual(res.status_code, 202)
        link = sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

        new = self.rotate()
        self.me(new)
        LoginToken.objects.filter(digest=token_digest(self.token.key)).delete()  # 매일 정리가 지운 뒤

        res = self.client.post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 200, res.content)
