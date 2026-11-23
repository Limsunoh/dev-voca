"""로그인 이어 가기(LoginToken.renew, TokenRenewView)를 깨뜨려 보는 테스트.

이어 가기는 하루 지난 토큰을 같은 로그인(device)의 새 토큰으로 바꾼다. 옛 토큰은 새 토큰이
처음 쓰일 때 바뀐 것으로 적히고 한 시간 더 통한 뒤 죽는다. 그 뒤 다시 오면 새어 나간
것으로 보고 그 로그인을 통째로 끊는다.

여기서 보는 것:
- 응답을 잃은 사람(새 토큰을 못 받고 옛 토큰만 든 사람)이 끊기지 않는가
- 유예 안의 옛 토큰(다른 탭, 이미 출발한 요청)이 정상 사용자를 끊지 않는가
- 유예가 지난 옛 토큰은 그 로그인만 끊고 다른 기기·남의 계정은 그대로인가
- 하루·한 시간·30일 경계와 시계가 뒤로 가는 경우
- 로그아웃·비밀번호 변경·이메일 변경 링크가 바뀐 토큰과 함께 맞게 도는가
- 관리자 화면이 device 를 흘리지 않는가
- 동시에 몰릴 때(Postgres, 실제 스레드)
- 0012/0013 을 되돌렸다 다시 적용할 때와 이 칸을 모르는 옛 코드식 INSERT
"""

from __future__ import annotations

import io
import threading
import time
import unittest
from datetime import timedelta
from unittest import mock

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.admin import LoginTokenAdmin
from apps.accounts.models import LoginToken

from .tests import EMAIL_CHANGE_CONFIRM_URL, EMAIL_CHANGE_URL, LOGOUT_URL, ME_URL, PASSWORD
from .tests_password import NEW_PASSWORD, PASSWORD_URL

User = get_user_model()

RENEW_URL = "/api/accounts/token/renew/"
ADMIN_LIST_URL = "/admin/accounts/logintoken/"

DAY = LoginToken.RENEW_AFTER
GRACE = LoginToken.REPLACED_GRACE
LIFETIME = LoginToken.LIFETIME


def auth(key: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Token {key}"}


def frozen(moment):
    """timezone.now 를 moment 로 고정한다. created 의 default 는 고정되지 않는다(함수 참조)."""
    return mock.patch("django.utils.timezone.now", return_value=moment)


class RenewMixin:
    """계정 둘과 나이를 정한 토큰을 만드는 도구."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def token(self, user=None, age=timedelta(0)) -> LoginToken:
        token = LoginToken.objects.create(user=user or self.owner)
        if age:
            self.age(token, age)
        return token

    def age(self, token: LoginToken, age: timedelta) -> None:
        LoginToken.objects.filter(pk=token.pk).update(created=timezone.now() - age)
        token.refresh_from_db()

    def renew(self, key: str):
        return self.client.post(RENEW_URL, **auth(key))

    def renewed(self, key: str) -> str:
        res = self.renew(key)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["token"]

    def me(self, key: str) -> int:
        return self.client.get(ME_URL, **auth(key)).status_code

    def row(self, key: str) -> LoginToken:
        return LoginToken.objects.get(key=key)

    def keys_of(self, user=None) -> set[str]:
        return set(
            LoginToken.objects.filter(user=user or self.owner).values_list("key", flat=True)
        )

    def push_replaced(self, key: str, ago: timedelta) -> None:
        """옛 토큰이 바뀐 시각을 ago 전으로 민다."""
        LoginToken.objects.filter(key=key).update(replaced_at=timezone.now() - ago)


class RenewContractTest(RenewMixin, TestCase):
    """응답 모양, 하루 경계, 같은 로그인 안에서만 이어지는지."""

    def test_하루_안_된_토큰은_그대로_돌려주고_행이_늘지_않는다(self):
        a = self.token(age=DAY - timedelta(minutes=1))

        res = self.renew(a.key)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.json()), {"token", "issued_at"})
        self.assertEqual(res.json()["token"], a.key)
        self.assertEqual(res.json()["issued_at"], int(a.created.timestamp()))
        self.assertEqual(LoginToken.objects.count(), 1)

    def test_하루_지난_토큰은_같은_로그인의_새_토큰을_받고_옛_토큰도_아직_통한다(self):
        a = self.token(age=DAY + timedelta(minutes=1))

        res = self.renew(a.key)

        body = res.json()
        self.assertEqual(res.status_code, 200)
        self.assertRegex(body["token"], r"^[0-9a-f]{40}$")
        self.assertNotEqual(body["token"], a.key)
        b = self.row(body["token"])
        self.assertEqual(b.device, a.device)
        self.assertEqual(b.user_id, self.owner.pk)
        self.assertFalse(b.delivered)
        self.assertIsNone(self.row(a.key).replaced_at)
        self.assertEqual(self.me(a.key), 200)

    def test_issued_at_은_새_토큰의_발급_시각_초_단위다(self):
        a = self.token(age=DAY * 2)

        body = self.renew(a.key).json()

        b = self.row(body["token"])
        self.assertIsInstance(body["issued_at"], int)
        self.assertEqual(body["issued_at"], int(b.created.timestamp()))
        # 밀리초면 13자리, 앞날·옛날이면 지금과 크게 다르다.
        self.assertLess(abs(body["issued_at"] - time.time()), 60)

    def test_정확히_하루면_새로_만들고_그보다_1마이크로초_어리면_그대로다(self):
        now = timezone.now()
        a = self.token()
        LoginToken.objects.filter(pk=a.pk).update(created=now - DAY + timedelta(microseconds=1))
        with frozen(now):
            self.assertEqual(self.renewed(a.key), a.key)

        LoginToken.objects.filter(pk=a.pk).update(created=now - DAY)
        with frozen(now):
            fresh = self.renewed(a.key)
        self.assertNotEqual(fresh, a.key)
        self.assertEqual(LoginToken.objects.count(), 2)

    def test_같은_계정의_다른_기기는_자기_로그인으로만_이어진다(self):
        phone = self.token(age=DAY * 2)
        laptop = self.token(age=DAY * 2)

        from_phone = self.renewed(phone.key)
        from_laptop = self.renewed(laptop.key)

        self.assertNotEqual(from_phone, from_laptop)
        self.assertEqual(self.row(from_phone).device, phone.device)
        self.assertEqual(self.row(from_laptop).device, laptop.device)
        # 폰이 이어 받은 뒤에도 노트북의 이어 가기는 폰의 새 토큰을 받지 않는다.
        self.assertEqual(self.renewed(laptop.key), from_laptop)

    def test_device_가_같아도_남의_계정_토큰은_이어_받지_않는다(self):
        mine = self.token(age=DAY * 2)
        theirs = self.token(self.other, age=timedelta(minutes=1))
        LoginToken.objects.filter(pk=theirs.pk).update(device=mine.device)

        fresh = self.renewed(mine.key)

        self.assertNotEqual(fresh, theirs.key)
        self.assertEqual(self.row(fresh).user_id, self.owner.pk)
        self.assertEqual(self.renewed(theirs.key), theirs.key)

    def test_로그인_없이_부르면_401(self):
        self.assertEqual(self.client.post(RENEW_URL).status_code, 401)

    def test_관리자_화면_세션은_400_이고_토큰을_만들지_않는다(self):
        root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(root)

        res = self.client.post(RENEW_URL)

        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())
        self.assertFalse(LoginToken.objects.filter(user=root).exists())

    def test_없는_토큰과_모양이_틀린_헤더는_401_이고_500_이_아니다(self):
        for header in (
            f"Token {'9' * 30}",
            f"Token {'a' * 40}",
            f"Token {'a' * 400}",
            "Token ",
            "Token a b",
            "Token -1",
            "Bearer " + "a" * 40,
        ):
            with self.subTest(header=header[:20]):
                res = self.client.post(RENEW_URL, HTTP_AUTHORIZATION=header)
                self.assertEqual(res.status_code, 401)

    def test_30일_지난_토큰은_401_이고_새_토큰을_안_만든다(self):
        a = self.token(age=LIFETIME + timedelta(seconds=1))

        self.assertEqual(self.renew(a.key).status_code, 401)
        self.assertEqual(LoginToken.objects.count(), 1)

    def test_정지_계정은_401_이고_새_토큰을_안_만든다(self):
        a = self.token(age=DAY * 2)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)

        self.assertEqual(self.renew(a.key).status_code, 401)
        self.assertEqual(LoginToken.objects.count(), 1)

    def test_GET_은_405_이고_새_토큰을_안_만든다(self):
        a = self.token(age=DAY * 2)

        self.assertEqual(self.client.get(RENEW_URL, **auth(a.key)).status_code, 405)
        self.assertEqual(LoginToken.objects.count(), 1)


class ResponseLossTest(RenewMixin, TestCase):
    """새 토큰을 실은 응답을 잃은 사람은 옛 토큰으로 계속 쓰고, 같은 새 토큰을 다시 받는다."""

    def test_몇_시간_뒤_옛_토큰으로_다시_오면_같은_새_토큰이다(self):
        a = self.token(age=DAY + timedelta(hours=1))
        b = self.renewed(a.key)
        self.age(self.row(b), timedelta(hours=5))

        self.assertEqual(self.me(a.key), 200)
        self.assertEqual(self.renewed(a.key), b)
        self.assertEqual(self.keys_of(), {a.key, b})

    def test_며칠_뒤_새_토큰도_하루가_지났어도_같은_새_토큰을_돌려준다(self):
        a = self.token(age=DAY * 4)
        b = self.renewed(a.key)
        self.age(self.row(b), DAY * 3)

        self.assertEqual(self.me(a.key), 200)
        body = self.renew(a.key).json()

        self.assertEqual(body["token"], b)
        self.assertEqual(body["issued_at"], int(self.row(b).created.timestamp()))
        self.assertEqual(self.keys_of(), {a.key, b})
        self.assertFalse(self.row(b).delivered)
        self.assertIsNone(self.row(a.key).replaced_at)

    def test_늦게_받은_새_토큰을_처음_쓰면_옛_토큰이_바뀐_것으로_적히고_다음_이어_가기가_된다(self):
        a = self.token(age=DAY * 4)
        b = self.renewed(a.key)
        self.age(self.row(b), DAY * 3)

        c = self.renewed(b)

        self.assertNotIn(c, (a.key, b))
        self.assertIsNotNone(self.row(a.key).replaced_at)
        self.assertTrue(self.row(b).delivered)
        self.assertEqual(self.row(c).device, a.device)

    def test_새_토큰이_안_쓰이면_옛_토큰은_발급_30일까지_통하고_그_뒤로_401(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)

        self.age(self.row(a.key), LIFETIME - timedelta(minutes=1))
        self.assertEqual(self.me(a.key), 200)
        self.age(self.row(a.key), LIFETIME + timedelta(minutes=1))
        self.assertEqual(self.me(a.key), 401)
        # 만료는 재사용 감지가 아니다. 새 토큰은 산다.
        self.assertEqual(self.me(b), 200)


class ReplacedGraceTest(RenewMixin, TestCase):
    """새 토큰이 쓰이기 시작한 뒤의 옛 토큰. 유예 안은 통하고, 지나면 그 로그인을 끊는다."""

    def setUp(self):
        super().setUp()
        self.a = self.token(age=DAY * 2)
        self.b = self.renewed(self.a.key)
        self.laptop = self.token(age=timedelta(hours=1))
        self.theirs = self.token(self.other, age=timedelta(hours=1))

    def start_using_new(self):
        self.assertEqual(self.me(self.b), 200)

    def test_새_토큰을_쓰기_시작한_직후_여러_탭이_옛_토큰과_섞여_와도_모두_통한다(self):
        self.start_using_new()

        for key in (self.a.key, self.b, self.a.key, self.a.key, self.b, self.a.key):
            self.assertEqual(self.me(key), 200)
        # 옛 토큰으로 온 이어 가기는 새 토큰을 돌려준다(쿠키를 다시 맞춘다).
        self.assertEqual(self.renewed(self.a.key), self.b)
        self.assertEqual(self.keys_of(), {self.a.key, self.b, self.laptop.key})

    def test_유예_59분째의_옛_토큰은_통한다(self):
        self.start_using_new()
        self.push_replaced(self.a.key, GRACE - timedelta(minutes=1))

        self.assertEqual(self.me(self.a.key), 200)
        self.assertEqual(self.me(self.b), 200)

    def test_정확히_한_시간째는_통하고_1마이크로초_뒤는_끊는다(self):
        self.start_using_new()
        replaced_at = self.row(self.a.key).replaced_at

        with frozen(replaced_at + GRACE):
            self.assertEqual(self.me(self.a.key), 200)
        with frozen(replaced_at + GRACE + timedelta(microseconds=1)):
            self.assertEqual(self.me(self.a.key), 401)
        self.assertFalse(LoginToken.objects.filter(key=self.b).exists())

    def test_유예가_지난_옛_토큰이_오면_그_로그인만_통째로_끊긴다(self):
        self.start_using_new()
        self.push_replaced(self.a.key, GRACE + timedelta(minutes=1))

        self.assertEqual(self.me(self.a.key), 401)

        self.assertFalse(LoginToken.objects.filter(device=self.a.device).exists())
        self.assertEqual(self.me(self.b), 401)
        self.assertEqual(self.me(self.laptop.key), 200)
        self.assertEqual(self.me(self.theirs.key), 200)

    def test_유예가_지난_옛_토큰으로_이어_가기를_불러도_401_이고_끊긴다(self):
        self.start_using_new()
        self.push_replaced(self.a.key, GRACE + timedelta(minutes=1))

        self.assertEqual(self.renew(self.a.key).status_code, 401)

        self.assertEqual(self.keys_of(), {self.laptop.key})

    def test_새_토큰을_여러_번_써도_바뀐_시각이_밀리지_않는다(self):
        """처음 쓰인 시각이 남아야 한다. 밀리면 옛 토큰의 유예가 쓸 때마다 늘어난다."""
        self.start_using_new()
        first = self.row(self.a.key).replaced_at

        with frozen(timezone.now() + timedelta(minutes=50)):
            self.assertEqual(self.me(self.b), 200)

        self.assertEqual(self.row(self.a.key).replaced_at, first)

    def test_세_대째로_넘어가면_앞의_두_토큰_중_먼저_바뀐_것의_시각은_그대로다(self):
        self.start_using_new()
        first = self.row(self.a.key).replaced_at
        self.age(self.row(self.b), DAY * 2)
        c = self.renewed(self.b)
        self.assertEqual(self.me(c), 200)

        self.assertEqual(self.row(self.a.key).replaced_at, first)
        self.assertIsNotNone(self.row(self.b).replaced_at)

        # 가장 오래된 옛 토큰이 유예 뒤에 오면 그 뒤로 이어 받은 토큰까지 모두 죽는다.
        self.push_replaced(self.a.key, GRACE + timedelta(minutes=1))
        self.assertEqual(self.me(self.a.key), 401)
        self.assertEqual(self.me(c), 401)
        self.assertEqual(self.keys_of(), {self.laptop.key})

    def test_새_토큰을_안_쓰면_옛_토큰은_며칠이_지나도_바뀐_것이_아니다(self):
        self.age(self.row(self.a.key), DAY * 20)

        self.assertEqual(self.me(self.a.key), 200)
        self.assertIsNone(self.row(self.a.key).replaced_at)


class LegacySharedTokenTest(RenewMixin, TestCase):
    """이 배포 전에 받은 토큰(0013 이 device 를 토큰 값으로 채운 것).

    11-13 전에는 계정당 토큰 하나를 폰과 PC 가 나눠 가졌다. 한쪽이 이어 간 뒤 다른 쪽이
    유예가 지나 그 값으로 와도 그 요청만 401 이고, 이어 받은 쪽은 끊지 않는다.
    """

    def setUp(self):
        super().setUp()
        self.shared = self.token(age=DAY * 2)
        LoginToken.objects.filter(pk=self.shared.pk).update(device=self.shared.key)
        self.shared.refresh_from_db()
        # 폰이 먼저 이어 받고 새 토큰을 쓰기 시작했다.
        self.phone = self.renewed(self.shared.key)
        self.assertEqual(self.me(self.phone), 200)
        self.laptop = self.token()

    def test_이어_받은_토큰의_device_는_옛_토큰_값이다(self):
        self.assertEqual(self.row(self.phone).device, self.shared.key)

    def test_유예_안에는_PC_의_옛_토큰도_통한다(self):
        self.push_replaced(self.shared.key, GRACE - timedelta(minutes=1))

        self.assertEqual(self.me(self.shared.key), 200)

    def test_유예가_지나_PC_가_옛_토큰으로_오면_그_요청만_401_이고_폰은_산다(self):
        self.push_replaced(self.shared.key, GRACE + timedelta(minutes=1))

        self.assertEqual(self.me(self.shared.key), 401)
        self.assertEqual(self.renew(self.shared.key).status_code, 401)

        self.assertEqual(self.me(self.phone), 200)
        self.assertEqual(self.me(self.laptop.key), 200)
        self.assertEqual(self.keys_of(), {self.shared.key, self.phone, self.laptop.key})

    def test_옛_토큰이_여러_번_와도_매번_401_이고_폰의_다음_이어_가기도_된다(self):
        self.push_replaced(self.shared.key, GRACE + timedelta(minutes=1))
        for _ in range(3):
            self.assertEqual(self.me(self.shared.key), 401)

        self.age(self.row(self.phone), DAY * 2)
        nxt = self.renewed(self.phone)
        self.assertNotEqual(nxt, self.phone)
        self.assertEqual(self.me(nxt), 200)

    def test_이어_받은_토큰이_다시_바뀐_뒤_유예가_지나_오면_그때는_로그인을_끊는다(self):
        """옛 토큰 예외는 device 가 자기 값인 토큰에만 걸린다. 그 뒤 세대는 원래 규칙이다."""
        self.age(self.row(self.phone), DAY * 2)
        nxt = self.renewed(self.phone)
        self.assertEqual(self.me(nxt), 200)
        self.push_replaced(self.phone, GRACE + timedelta(minutes=1))

        self.assertEqual(self.me(self.phone), 401)

        self.assertFalse(LoginToken.objects.filter(device=self.shared.key).exists())
        self.assertEqual(self.me(nxt), 401)
        self.assertEqual(self.me(self.laptop.key), 200)

    def test_옛_토큰으로_로그아웃하면_이어_받은_토큰도_지운다(self):
        self.assertEqual(self.client.post(LOGOUT_URL, **auth(self.shared.key)).status_code, 204)

        self.assertEqual(self.me(self.phone), 401)
        self.assertEqual(self.keys_of(), {self.laptop.key})


class ClockTest(RenewMixin, TestCase):
    """서버 시계가 앞뒤로 튀어도 500 이 없고 같은 로그인이 갈라지지 않는다."""

    def test_시계가_뒤로_가면_새_토큰을_또_만들지_않고_있는_것을_돌려준다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)
        # 새 토큰이 앞날에 만들어진 것처럼 된다(시계가 하루 뒤로 감).
        with frozen(timezone.now() - DAY):
            self.assertEqual(self.renewed(a.key), b)
            self.assertEqual(self.renewed(b), b)
            self.assertEqual(self.me(a.key), 200)
        self.assertEqual(self.keys_of(), {a.key, b})

    def test_시계가_31일_앞으로_튀면_모두_401_이고_다시_돌아오면_통한다(self):
        a = self.token(age=DAY * 2)
        with frozen(timezone.now() + LIFETIME + DAY):
            self.assertEqual(self.renew(a.key).status_code, 401)
        # 만료는 지우지 않는다(재사용 감지가 아니다).
        self.assertEqual(self.me(a.key), 200)


class ExpiredSelectionTest(RenewMixin, TestCase):
    """매일 정리는 발급 30일만 고른다. 바뀐 옛 토큰은 30일까지 남아 재사용 감지에 쓰인다."""

    def test_정확히_30일은_안_고르고_통하며_1마이크로초_넘으면_고르고_401(self):
        now = timezone.now()
        a = self.token()
        LoginToken.objects.filter(pk=a.pk).update(created=now - LIFETIME)
        with frozen(now):
            self.assertFalse(LoginToken.expired().filter(pk=a.pk).exists())
            self.assertEqual(self.me(a.key), 200)

        LoginToken.objects.filter(pk=a.pk).update(created=now - LIFETIME - timedelta(microseconds=1))
        with frozen(now):
            self.assertTrue(LoginToken.expired().filter(pk=a.pk).exists())
            self.assertEqual(self.me(a.key), 401)

    def test_유예가_지난_옛_토큰은_30일_전에는_고르지_않는다(self):
        a = self.token(age=DAY * 29)
        b = self.renewed(a.key)
        self.assertEqual(self.me(b), 200)
        self.push_replaced(a.key, DAY * 20)

        self.assertEqual(list(LoginToken.expired()), [])

    def test_30일_넘은_옛_토큰만_고르고_이어_받은_토큰은_남긴다(self):
        a = self.token(age=LIFETIME + DAY)
        b = self.token(age=DAY * 2)
        LoginToken.objects.filter(pk=b.pk).update(device=a.device)

        self.assertEqual(list(LoginToken.expired().values_list("key", flat=True)), [a.key])


class EndLoginTest(RenewMixin, TestCase):
    """로그아웃·비밀번호 변경이 이어 받은 토큰까지 함께 끝내는가."""

    def setUp(self):
        super().setUp()
        self.a = self.token(age=DAY * 2)
        self.b = self.renewed(self.a.key)
        self.laptop = self.token()
        self.theirs = self.token(self.other)

    def test_새_토큰으로_로그아웃하면_유예_안의_옛_토큰도_죽는다(self):
        self.assertEqual(self.me(self.b), 200)

        self.assertEqual(self.client.post(LOGOUT_URL, **auth(self.b)).status_code, 204)

        self.assertEqual(self.me(self.a.key), 401)
        self.assertEqual(self.keys_of(), {self.laptop.key})
        self.assertTrue(LoginToken.objects.filter(pk=self.theirs.pk).exists())

    def test_옛_토큰으로_로그아웃하면_아직_안_쓴_새_토큰도_죽는다(self):
        self.assertEqual(self.client.post(LOGOUT_URL, **auth(self.a.key)).status_code, 204)

        self.assertEqual(self.me(self.b), 401)
        self.assertEqual(self.keys_of(), {self.laptop.key})

    def test_비밀번호를_바꾸면_안_쓴_새_토큰까지_죽고_새_로그인을_받는다(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(self.a.key),
        )

        self.assertEqual(res.status_code, 200)
        fresh = res.json()["token"]
        self.assertEqual(self.keys_of(), {fresh})
        self.assertNotEqual(self.row(fresh).device, self.a.device)
        self.assertTrue(self.row(fresh).delivered)
        for key in (self.a.key, self.b, self.laptop.key):
            self.assertEqual(self.me(key), 401)
            self.assertEqual(self.renew(key).status_code, 401)
        self.assertTrue(LoginToken.objects.filter(pk=self.theirs.pk).exists())


class EmailLinkAcrossRenewTest(RenewMixin, TestCase):
    """이메일 변경 링크는 device 에 묶여 토큰이 바뀌어도 살고, 로그인을 끝내면 죽는다."""

    def setUp(self):
        super().setUp()
        self.a = self.token(age=DAY * 2)

    def issue(self, key: str, new_email="next@example.com") -> str:
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": new_email, "current_password": PASSWORD},
                content_type="application/json",
                **auth(key),
            )
        self.assertEqual(res.status_code, 202, res.content)
        return sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

    def confirm(self, link: str):
        return Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )

    def move_on(self) -> str:
        """이어 받고 새 토큰을 쓰기 시작하고, 옛 토큰의 유예까지 지나게 한다."""
        b = self.renewed(self.a.key)
        self.assertEqual(self.me(b), 200)
        self.push_replaced(self.a.key, GRACE + timedelta(minutes=5))
        return b

    def assert_email(self, email: str):
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, email)

    def test_옛_토큰으로_신청한_링크는_토큰이_바뀌어도_통한다(self):
        link = self.issue(self.a.key)
        self.move_on()

        res = self.confirm(link)

        self.assertEqual(res.status_code, 200, res.content)
        self.assert_email("next@example.com")

    def test_옛_토큰이_30일에_지워져도_새_토큰이_남아_있으면_통한다(self):
        link = self.issue(self.a.key)
        self.move_on()
        LoginToken.objects.filter(pk=self.a.pk).delete()

        self.assertEqual(self.confirm(link).status_code, 200)

    def test_새_토큰으로_로그아웃하면_옛_토큰으로_받은_링크도_죽는다(self):
        link = self.issue(self.a.key)
        b = self.move_on()
        self.assertEqual(self.client.post(LOGOUT_URL, **auth(b)).status_code, 204)

        self.assertEqual(self.confirm(link).status_code, 400)
        self.assert_email("owner@example.com")

    def test_재사용_감지로_끊기면_그_로그인의_링크도_죽는다(self):
        link = self.issue(self.a.key)
        self.move_on()
        self.assertEqual(self.me(self.a.key), 401)

        self.assertEqual(self.confirm(link).status_code, 400)
        self.assert_email("owner@example.com")

    def test_비밀번호를_바꾸면_이어_받은_뒤의_링크도_죽는다(self):
        b = self.move_on()
        link = self.issue(b)
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(b),
        )
        self.assertEqual(res.status_code, 200)

        self.assertEqual(self.confirm(link).status_code, 400)

    def test_변경을_끝내면_다른_링크와_이어_받은_토큰이_모두_죽는다(self):
        b = self.move_on()
        first = self.issue(b, "first@example.com")
        second = self.issue(b, "second@example.com")

        res = self.confirm(first)
        self.assertEqual(res.status_code, 200)
        fresh = res.json()["token"]

        self.assertEqual(self.confirm(second).status_code, 400)
        self.assertEqual(self.keys_of(), {fresh})
        self.assertNotEqual(self.row(fresh).device, self.a.device)
        self.assert_email("first@example.com")


class AdminDeviceLeakTest(RenewMixin, TestCase):
    """관리자 화면은 device 를 보여주지 않고, 주소 검색어로 한 글자씩 맞혀 볼 수도 없다."""

    def setUp(self):
        super().setUp()
        self.a = self.token(age=DAY * 2)
        self.b = self.renewed(self.a.key)
        self.root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.admin = Client()
        self.admin.force_login(self.root)

    def test_목록과_상세에_device_와_토큰_값이_안_나온다(self):
        urls = [ADMIN_LIST_URL] + [
            f"{ADMIN_LIST_URL}{pk}/change/"
            for pk in LoginToken.objects.values_list("pk", flat=True)
        ]
        for url in urls:
            with self.subTest(url=url):
                res = self.admin.get(url)
                self.assertEqual(res.status_code, 200)
                html = res.content.decode()
                self.assertNotIn(self.a.device, html)
                self.assertNotIn(self.a.key, html)
                self.assertNotIn(self.b, html)

    def test_주소_검색어로_device_를_거르면_400(self):
        part = self.a.device[:8]
        for lookup in (
            "device",
            "device__startswith",
            "device__istartswith",
            "device__exact",
            "device__in",
            "device__gte",
            "device__regex",
            "device__contains",
        ):
            with self.subTest(lookup):
                res = self.admin.get(ADMIN_LIST_URL, {lookup: part})
                self.assertEqual(res.status_code, 400)

    def test_회원을_거쳐_돌아오는_검색어로도_device_와_토큰을_못_거른다(self):
        for lookup in (
            "user__login_tokens__device__startswith",
            "user__login_tokens__device",
            "user__login_tokens__key__startswith",
        ):
            with self.subTest(lookup):
                res = self.admin.get(ADMIN_LIST_URL, {lookup: self.a.device[:8]})
                self.assertEqual(res.status_code, 400)

    def test_회원_화면에서_device_로_걸러_볼_수_없다(self):
        for lookup in ("login_tokens__device", "login_tokens__device__startswith"):
            with self.subTest(lookup):
                res = self.admin.get("/admin/accounts/user/", {lookup: self.a.device[:8]})
                self.assertNotEqual(res.status_code, 200)

    def test_검색창에_device_를_넣어도_안_찾아진다(self):
        res = self.admin.get(ADMIN_LIST_URL, {"q": self.a.device})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["cl"].result_count, 0)

    def test_바뀐_시각과_받음으로_거르는_것은_된다(self):
        """device 를 막느라 관리자가 쓸 칸까지 막지 않았나."""
        res = self.admin.get(ADMIN_LIST_URL, {"delivered__exact": "0"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["cl"].result_count, 1)


def _together(*calls):
    """calls 를 동시에 부르고 (상태 코드, 본문) 목록을 돌려준다."""
    barrier = threading.Barrier(len(calls))
    results = []
    lock = threading.Lock()

    def run(call):
        try:
            barrier.wait(timeout=10)
            res = call(Client(raise_request_exception=False))
            body = res.json() if res.content and res["Content-Type"].startswith(
                "application/json") else {}
            with lock:
                results.append((res.status_code, body))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run, args=(call,)) for call in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def _renew(key):
    return lambda client: client.post(RENEW_URL, **auth(key))


@unittest.skipUnless(connection.vendor == "postgresql", "동시성은 Postgres 에서만 뜻이 있다")
class RenewConcurrencyTest(RenewMixin, TransactionTestCase):
    """같은 로그인에 이어 가기와 지우는 요청이 동시에 몰려도 남는 토큰이 맞는가.

    누가 먼저 잠그느냐는 매번 다르다. 그래서 상태 코드 한 가지를 단정하지 않고 늘 성립하는
    것(새 토큰은 하나, 지운 로그인의 토큰은 0개)을 본다. 여러 번 돌려 순서를 바꿔 본다.
    """

    ROUNDS = 4

    def test_하루_지난_토큰으로_이어_가기_넷이_동시에_와도_새_토큰은_하나다(self):
        for _ in range(self.ROUNDS):
            a = self.token(age=DAY * 2)

            results = _together(*[_renew(a.key)] * 4)

            self.assertEqual([status for status, _ in results], [200] * 4, results)
            tokens = {body["token"] for _, body in results}
            self.assertEqual(len(tokens), 1, tokens)
            self.assertNotIn(a.key, tokens)
            self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 2)

    def test_같은_로그인의_로그아웃과_이어_가기가_겹쳐도_그_로그인의_토큰은_0개(self):
        laptop = self.token()
        for _ in range(self.ROUNDS):
            a = self.token(age=DAY * 2)

            results = _together(
                _renew(a.key),
                lambda client, key=a.key: client.post(LOGOUT_URL, **auth(key)),
            )

            statuses = sorted(status for status, _ in results)
            self.assertIn(statuses, ([200, 204], [204, 401]), results)
            self.assertFalse(LoginToken.objects.filter(device=a.device).exists())
        self.assertTrue(LoginToken.objects.filter(pk=laptop.pk).exists())

    def test_비밀번호_변경과_이어_가기가_겹쳐도_옛_로그인의_토큰이_안_남는다(self):
        for i in range(self.ROUNDS):
            # 매 판 비밀번호를 번갈아 바꾼다.
            current, new = (PASSWORD, NEW_PASSWORD) if i % 2 == 0 else (NEW_PASSWORD, PASSWORD)
            phone = self.token(age=DAY * 2)
            laptop = self.token(age=DAY * 2)
            old_devices = list(
                LoginToken.objects.filter(user=self.owner).values_list("device", flat=True)
            )

            results = _together(
                _renew(laptop.key),
                lambda client, key=phone.key, c=current, n=new: client.post(
                    PASSWORD_URL,
                    {"current_password": c, "new_password": n},
                    content_type="application/json",
                    **auth(key),
                ),
            )

            self.assertEqual(len(results), 2)
            changed = [body for status, body in results if "user" in body]
            self.assertEqual(len(changed), 1, results)
            self.assertTrue(all(status in (200, 401) for status, _ in results), results)
            self.assertFalse(
                LoginToken.objects.filter(device__in=old_devices).exists(), results
            )
            self.assertEqual(self.keys_of(), {changed[0]["token"]})

    def test_다른_기기_둘이_동시에_이어_가도_각자_자기_로그인의_새_토큰이다(self):
        phone, laptop = self.token(age=DAY * 2), self.token(age=DAY * 2)

        results = _together(_renew(phone.key), _renew(laptop.key))

        self.assertEqual([status for status, _ in results], [200, 200])
        devices = {LoginToken.objects.get(key=body["token"]).device for _, body in results}
        self.assertEqual(devices, {phone.device, laptop.device})

    def test_새_토큰이_동시에_처음_쓰여도_옛_토큰은_유예_안이라_통한다(self):
        a = self.token(age=DAY * 2)
        b = LoginToken.objects.get(key=self.renewed_by_client(a.key))

        results = _together(*[(lambda client: client.get(ME_URL, **auth(b.key)))] * 3)

        self.assertEqual([status for status, _ in results], [200] * 3)
        self.assertIsNotNone(LoginToken.objects.get(pk=a.pk).replaced_at)
        self.assertEqual(Client().get(ME_URL, **auth(a.key)).status_code, 200)

    def renewed_by_client(self, key: str) -> str:
        return Client().post(RENEW_URL, **auth(key)).json()["token"]


@unittest.skipUnless(connection.vendor == "postgresql", "동시성은 Postgres 에서만 뜻이 있다")
class LockSabotageTest(TransactionTestCase):
    """회원 행 잠금(lock_member)을 빼면 동시 이어 가기 테스트가 빨개지는가.

    잠금만 빼면 스레드 타이밍에 따라 통과할 때가 있다. 그래서 새 토큰을 만드는 자리에서
    네 요청을 모두 붙잡아 두어, 넷 다 "가장 새 토큰은 나" 를 읽은 뒤 만들게 한다. 진짜
    잠금이 있으면 둘째부터는 잠금에서 기다려 이 자리에 못 오므로 이 장치는 잠금을 뺀
    경우에만 쓴다.
    """

    def test_잠금을_빼면_동시_이어_가기_테스트가_잡는다(self):
        real_create = LoginToken.objects.create
        gate = threading.Barrier(4, timeout=10)

        def create_after_all_read(*args, **kwargs):
            if kwargs.get("delivered") is False:
                gate.wait()
            return real_create(*args, **kwargs)

        with mock.patch.object(
            LoginToken, "lock_member", staticmethod(lambda user_id: True)
        ), mock.patch.object(LoginToken.objects, "create", side_effect=create_after_all_read):
            result = unittest.TestResult()
            RenewConcurrencyTest(
                "test_하루_지난_토큰으로_이어_가기_넷이_동시에_와도_새_토큰은_하나다"
            )(result)

        self.assertEqual(len(result.failures), 1, result.errors)


@unittest.skipUnless(connection.vendor == "postgresql", "raw SQL 이 Postgres 문법이다")
class MigrationTest(TransactionTestCase):
    """0012/0013 을 되돌렸다 다시 적용한다(배포 직후). 이 칸을 모르는 옛 코드식 INSERT 도 넣는다."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)

    def migrate(self, target: str | None = None) -> None:
        args = ["accounts", target] if target else ["accounts"]
        call_command("migrate", *args, stdout=io.StringIO(), verbosity=0)

    def old_insert(self, key: str) -> None:
        """0011 시절 코드가 넣던 꼴. key·user_id·created 만 안다."""
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO accounts_logintoken (key, user_id, created) VALUES (%s, %s, now())",
                [key, self.owner.pk],
            )

    def test_되돌렸다_다시_적용하면_옛_토큰의_device_가_토큰_값이고_로그인이_산다(self):
        try:
            self.migrate("0011")
            self.old_insert("a" * 40)
            self.migrate("0012")
            # 0012 만 적용된 사이(0013 전)에 옛 코드가 넣어도 NOT NULL 에 안 걸린다.
            self.old_insert("b" * 40)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT key, device, delivered, replaced_at FROM accounts_logintoken"
                    " ORDER BY key"
                )
                rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            for _, device, delivered, replaced_at in rows:
                self.assertTrue(device)
                self.assertTrue(delivered)
                self.assertIsNone(replaced_at)
        finally:
            self.migrate()

        for key in ("a" * 40, "b" * 40):
            token = LoginToken.objects.get(key=key)
            self.assertEqual(token.device, key)
            self.assertEqual(Client().get(ME_URL, **auth(key)).status_code, 200)

    def test_최신_상태에서_옛_코드식_INSERT_는_서로_다른_device_를_받아_따로_로그아웃된다(self):
        self.old_insert("c" * 40)
        self.old_insert("d" * 40)

        c, d = LoginToken.objects.get(key="c" * 40), LoginToken.objects.get(key="d" * 40)
        self.assertTrue(c.device and d.device)
        self.assertLessEqual(len(c.device), 40)
        self.assertNotEqual(c.device, d.device)
        self.assertTrue(c.delivered)

        self.assertEqual(Client().post(LOGOUT_URL, **auth(c.key)).status_code, 204)
        self.assertEqual(Client().get(ME_URL, **auth(d.key)).status_code, 200)

    def test_옛_코드식_INSERT_로_만든_토큰도_이어_가기가_된다(self):
        self.old_insert("e" * 40)
        LoginToken.objects.filter(key="e" * 40).update(created=timezone.now() - DAY * 2)

        res = Client().post(RENEW_URL, **auth("e" * 40))

        self.assertEqual(res.status_code, 200)
        fresh = LoginToken.objects.get(key=res.json()["token"])
        self.assertEqual(fresh.device, LoginToken.objects.get(key="e" * 40).device)


class SabotageTest(TestCase):
    """방어를 일부러 빼면 위 테스트가 빨개지는지 본다. 구현 파일은 건드리지 않는다."""

    def run_case(self, case: type, name: str) -> int:
        """실패(단정이 틀림) 개수. 테스트가 엉뚱한 예외로 죽으면 그것은 잡은 것이 아니다."""
        result = unittest.TestResult()
        case(name)(result)
        self.assertEqual(result.errors, [])
        return len(result.failures)

    def test_유예를_안_보면_재사용_감지_테스트가_잡는다(self):
        with mock.patch.object(LoginToken, "replaced_past_grace", return_value=False):
            self.assertEqual(
                self.run_case(ReplacedGraceTest, "test_유예가_지난_옛_토큰이_오면_그_로그인만_통째로_끊긴다"),
                1,
            )

    def test_유예를_재지_않고_바로_끊으면_여러_탭_테스트가_잡는다(self):
        with mock.patch.object(LoginToken, "replaced_past_grace", lambda self: self.replaced_at is not None):
            self.assertEqual(
                self.run_case(
                    ReplacedGraceTest,
                    "test_새_토큰을_쓰기_시작한_직후_여러_탭이_옛_토큰과_섞여_와도_모두_통한다",
                ),
                1,
            )

    def test_이어_가기가_늘_새로_만들면_응답_유실_테스트가_잡는다(self):
        def always_new(token):
            return LoginToken.objects.create(user_id=token.user_id, device=token.device, delivered=False)

        with mock.patch.object(LoginToken, "renew", always_new):
            self.assertEqual(
                self.run_case(ResponseLossTest, "test_몇_시간_뒤_옛_토큰으로_다시_오면_같은_새_토큰이다"), 1
            )

    def test_이어_가기에서_옛_토큰을_바로_끝내면_응답_유실_테스트가_잡는다(self):
        real = LoginToken.renew

        def end_old_now(token):
            fresh = real(token)
            LoginToken.objects.filter(pk=token.pk).update(replaced_at=timezone.now() - GRACE * 2)
            return fresh

        with mock.patch.object(LoginToken, "renew", end_old_now):
            self.assertEqual(
                self.run_case(ResponseLossTest, "test_몇_시간_뒤_옛_토큰으로_다시_오면_같은_새_토큰이다"), 1
            )

    def test_바뀐_시각을_쓸_때마다_덮으면_유예_연장_테스트가_잡는다(self):
        def stamp_every_time(token):
            LoginToken.objects.filter(
                user_id=token.user_id, device=token.device, created__lt=token.created
            ).update(replaced_at=timezone.now())
            LoginToken.objects.filter(pk=token.pk).update(delivered=True)

        # delivered 가 True 가 되면 인증이 다시 부르지 않는다. 늘 부르게 해서 덮어쓰기를 본다.
        from apps.accounts import authentication

        real_auth = authentication.SlimTokenAuthentication.authenticate_credentials

        def always_mark(self_auth, key):
            user, token = real_auth(self_auth, key)
            stamp_every_time(token)
            return user, token

        with mock.patch.object(
            authentication.SlimTokenAuthentication, "authenticate_credentials", always_mark
        ):
            self.assertEqual(
                self.run_case(ReplacedGraceTest, "test_새_토큰을_여러_번_써도_바뀐_시각이_밀리지_않는다"), 1
            )

    def test_관리자_검색어_막기를_빼면_device_테스트가_잡는다(self):
        with mock.patch.object(
            LoginTokenAdmin, "lookup_allowed", django_admin.ModelAdmin.lookup_allowed
        ):
            # 검색어마다 subTest 라 막기를 빼면 여덟 개가 모두 빨개진다.
            self.assertEqual(
                self.run_case(AdminDeviceLeakTest, "test_주소_검색어로_device_를_거르면_400"), 8
            )

    def test_옛_공유_토큰_예외를_빼면_옛_토큰_테스트가_잡는다(self):
        """device 가 토큰 값인 옛 토큰도 유예 뒤에 오면 로그인을 끊게 만든다."""
        from rest_framework import exceptions

        from apps.accounts import authentication

        real_auth = authentication.SlimTokenAuthentication.authenticate_credentials

        def no_exception(self_auth, key):
            try:
                return real_auth(self_auth, key)
            except exceptions.AuthenticationFailed:
                token = LoginToken.objects.filter(key=key).first()
                if token and token.replaced_past_grace():
                    LoginToken.end_login(token.user_id, token.device)
                raise

        with mock.patch.object(
            authentication.SlimTokenAuthentication, "authenticate_credentials", no_exception
        ):
            self.assertEqual(
                self.run_case(
                    LegacySharedTokenTest,
                    "test_유예가_지나_PC_가_옛_토큰으로_오면_그_요청만_401_이고_폰은_산다",
                ),
                1,
            )

    def test_로그아웃이_들고_온_토큰만_지우면_옛_토큰_테스트가_잡는다(self):
        def only_this(self_view, request):
            from rest_framework.response import Response

            request.auth.delete()
            return Response(status=204)

        with mock.patch("apps.accounts.views.LogoutView.post", only_this):
            self.assertEqual(
                self.run_case(EndLoginTest, "test_새_토큰으로_로그아웃하면_유예_안의_옛_토큰도_죽는다"), 1
            )

    def test_정리가_바뀐_옛_토큰까지_고르면_선택_테스트가_잡는다(self):
        def too_eager(cls):
            from django.db.models import Q

            now = timezone.now()
            return cls.objects.filter(
                Q(created__lt=now - cls.LIFETIME) | Q(replaced_at__lt=now - cls.REPLACED_GRACE)
            )

        with mock.patch.object(LoginToken, "expired", classmethod(too_eager)):
            self.assertEqual(
                self.run_case(ExpiredSelectionTest, "test_유예가_지난_옛_토큰은_30일_전에는_고르지_않는다"), 1
            )
