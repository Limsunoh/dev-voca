"""기기별 로그인 토큰(LoginToken)을 깨뜨려 보는 테스트.

tests.py·tests_password.py·tests_email_token.py 가 한 기기·한 계정의 기본 흐름을
본다면, 여기는 기기 여럿과 다른 계정을 섞은 경우를 본다. 로그아웃이 남의 토큰을
지우지 않는가, 같은 토큰을 동시에 내도 500 이 안 나는가, 탈퇴·파기 뒤에 토큰이
남지 않는가, 이메일 변경 링크가 신청한 기기에만 묶이는가, 관리자 화면이 토큰
값을 흘리지 않는가.
"""

from __future__ import annotations

import re
import threading
import unittest
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token as DrfToken

from apps.accounts import purge
from apps.accounts.models import LoginToken

from .email_change import email_mark, read_token
from .tests import (
    CONSENT,
    EMAIL_CHANGE_CONFIRM_URL,
    EMAIL_CHANGE_URL,
    GOOGLE_URL,
    LOGIN_URL,
    LOGOUT_URL,
    ME_URL,
    PASSWORD,
    REDIRECT_URI,
    SIGNUP_URL,
)
from .tests_password import NEW_PASSWORD, OTHER_A, OTHER_B, PASSWORD_URL

User = get_user_model()

ADMIN_LIST_URL = "/admin/accounts/logintoken/"
ADMIN_ADD_URL = "/admin/accounts/logintoken/add/"
DRF_TOKEN_ADMIN_URL = "/admin/authtoken/tokenproxy/"

KEY_SHAPE = re.compile(r"^[0-9a-f]{40}$")


def auth(key: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Token {key}"}


class DeviceMixin:
    """계정 둘(주인·남)과 기기별 토큰을 만드는 도구."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def device(self, user) -> str:
        return LoginToken.objects.create(user=user).key

    def me(self, key: str) -> int:
        return self.client.get(ME_URL, **auth(key)).status_code

    def logout(self, key: str) -> int:
        return self.client.post(LOGOUT_URL, **auth(key)).status_code

    def login(self, email="owner@example.com", password=PASSWORD):
        return self.client.post(
            LOGIN_URL, {"email": email, "password": password}, content_type="application/json"
        )


class IssueEveryTimeTest(DeviceMixin, TestCase):
    """로그인·가입·구글 로그인은 부를 때마다 새 토큰을 내고 응답 모양은 그대로다."""

    def google(self, email="owner@example.com", **extra):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": "구글", "picture": ""},
        ):
            return self.client.post(
                GOOGLE_URL,
                {"code": "leakmark-code", "redirect_uri": REDIRECT_URI, **extra},
                content_type="application/json",
            )

    def assert_auth_shape(self, res, status_code):
        self.assertEqual(res.status_code, status_code)
        body = res.json()
        self.assertEqual(set(body), {"token", "user"})
        self.assertRegex(body["token"], KEY_SHAPE)
        return body["token"]

    def test_로그인을_세_번_하면_서로_다른_토큰_셋이_모두_통한다(self):
        keys = [self.assert_auth_shape(self.login(), 200) for _ in range(3)]

        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 3)
        for key in keys:
            self.assertEqual(self.me(key), 200)

    def test_가입_응답은_201_이고_토큰_하나가_생긴다(self):
        res = self.client.post(
            SIGNUP_URL,
            {"email": "fresh@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

        key = self.assert_auth_shape(res, 201)
        user = User.objects.get(email="fresh@example.com")
        self.assertEqual(list(user.login_tokens.values_list("key", flat=True)), [key])

    def test_가입이_거절되면_토큰을_만들지_않는다(self):
        before = LoginToken.objects.count()

        res = self.client.post(
            SIGNUP_URL,
            {"email": "owner@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(LoginToken.objects.count(), before)

    def test_구글_로그인도_부를_때마다_새_토큰을_낸다(self):
        first = self.assert_auth_shape(self.google(), 200)
        second = self.assert_auth_shape(self.google(), 200)

        self.assertNotEqual(first, second)
        self.assertEqual(self.me(first), 200)
        self.assertEqual(self.me(second), 200)

    def test_구글_첫_로그인은_201_이고_토큰_하나다(self):
        key = self.assert_auth_shape(self.google("newbie@example.com", **CONSENT), 201)

        user = User.objects.get(email="newbie@example.com")
        self.assertEqual(list(user.login_tokens.values_list("key", flat=True)), [key])

    def test_다른_계정으로_로그인해도_내_토큰은_그대로다(self):
        mine = self.device(self.owner)

        self.assert_auth_shape(self.login("other@example.com"), 200)

        self.assertEqual(self.me(mine), 200)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 1)


class LogoutScopeTest(DeviceMixin, TestCase):
    """로그아웃은 요청이 들고 온 토큰 하나만 지운다."""

    def test_내_기기_하나만_지우고_다른_기기와_남의_토큰은_남는다(self):
        """남의 토큰까지 지우면 아무나 로그아웃 한 번으로 남을 끊는다."""
        phone, laptop, tablet = (self.device(self.owner) for _ in range(3))
        others = [self.device(self.other) for _ in range(2)]

        self.assertEqual(self.logout(laptop), 204)

        self.assertFalse(LoginToken.objects.filter(key=laptop).exists())
        self.assertEqual(self.me(laptop), 401)
        for key in (phone, tablet, *others):
            self.assertEqual(self.me(key), 200)
        self.assertEqual(LoginToken.objects.count(), 4)

    def test_로그아웃한_토큰을_다시_내면_401_이고_아무것도_안_지운다(self):
        gone = self.device(self.owner)
        kept = self.device(self.owner)
        self.assertEqual(self.logout(gone), 204)

        self.assertEqual(self.logout(gone), 401)
        self.assertEqual(self.me(kept), 200)

    def test_본문에_남의_토큰을_실어도_내_토큰만_지운다(self):
        """지울 대상은 본문이 아니라 인증에 쓴 토큰이다."""
        mine = self.device(self.owner)
        theirs = self.device(self.other)

        res = self.client.post(
            LOGOUT_URL, {"token": theirs, "key": theirs}, content_type="application/json",
            **auth(mine),
        )

        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.me(theirs), 200)
        self.assertEqual(self.me(mine), 401)

    def test_세션과_토큰을_함께_들고_오면_그_토큰만_지운다(self):
        """관리자 화면에 로그인한 브라우저가 토큰도 함께 보낸 경우."""
        self.client.force_login(self.owner)
        mine, spare = self.device(self.owner), self.device(self.owner)

        self.assertEqual(self.logout(mine), 204)

        self.assertEqual(list(LoginToken.objects.filter(user=self.owner)
                              .values_list("key", flat=True)), [spare])

    def test_세션만으로_로그아웃하면_어느_계정_토큰도_안_지운다(self):
        keys = [self.device(self.owner), self.device(self.other)]
        session = Client()
        session.force_login(self.owner)

        self.assertEqual(session.post(LOGOUT_URL).status_code, 204)

        self.assertEqual(LoginToken.objects.filter(key__in=keys).count(), 2)

    def test_로그인_없이_로그아웃하면_401_이고_아무것도_안_지운다(self):
        self.device(self.owner)

        self.assertEqual(self.client.post(LOGOUT_URL).status_code, 401)
        self.assertEqual(LoginToken.objects.count(), 1)


class HeaderShapeTest(DeviceMixin, TestCase):
    """이상한 Authorization 헤더는 500 이 아니라 401 이다."""

    def test_모양이_틀린_헤더는_401(self):
        key = self.device(self.owner)
        for header in (
            "Token",
            f"Token {key} extra",
            "Token " + "9" * 1000,
            "Token " + key.upper(),
            "Token " + key[:-1],
            f"Token {key}'--",
        ):
            with self.subTest(header=header[:50]):
                res = self.client.get(ME_URL, HTTP_AUTHORIZATION=header)
                self.assertEqual(res.status_code, 401)

    def test_옛_DRF_표에만_있는_토큰은_통하지_않는다(self):
        """옛 표는 남아 있지만 아무도 읽지 않아야 한다. 읽으면 로그아웃이 무의미하다."""
        old = DrfToken.objects.create(user=self.owner)
        self.assertFalse(LoginToken.objects.filter(key=old.key).exists())

        self.assertEqual(self.me(old.key), 401)

    def test_옮겨_온_토큰으로_로그아웃하면_옛_표에_남아도_더는_안_통한다(self):
        """0010 이 옛 값을 그대로 옮겼다. 로그아웃은 새 표에서만 지운다."""
        old = DrfToken.objects.create(user=self.owner)
        LoginToken.objects.create(user=self.owner, key=old.key)

        self.assertEqual(self.logout(old.key), 204)

        self.assertTrue(DrfToken.objects.filter(key=old.key).exists())
        self.assertEqual(self.me(old.key), 401)


class InactiveAccountTest(DeviceMixin, TestCase):
    """정지한 계정의 토큰은 어느 자리에서도 통하지 않는다."""

    def setUp(self):
        super().setUp()
        self.keys = [self.device(self.owner), self.device(self.owner)]
        User.objects.filter(pk=self.owner.pk).update(is_active=False)

    def test_정지_계정_토큰은_모든_기기에서_401(self):
        for key in self.keys:
            self.assertEqual(self.me(key), 401)
            self.assertEqual(self.logout(key), 401)
            res = self.client.post(
                PASSWORD_URL,
                {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                content_type="application/json",
                **auth(key),
            )
            self.assertEqual(res.status_code, 401)

    def test_정지_계정은_로그인해도_새_토큰이_안_생긴다(self):
        self.assertEqual(self.login().status_code, 400)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 2)

    def test_정지_계정은_구글_로그인해도_새_토큰이_안_생긴다(self):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "owner@example.com", "name": "", "picture": ""},
        ):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "leakmark-code", "redirect_uri": REDIRECT_URI},
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 2)

    def test_정지를_풀면_남아_있던_토큰이_다시_통한다(self):
        """정지는 토큰을 지우지 않는다. 다 끊으려면 토큰도 지워야 한다는 것을 못 박는다."""
        User.objects.filter(pk=self.owner.pk).update(is_active=True)

        self.assertEqual(self.me(self.keys[0]), 200)


class PasswordChangeScopeTest(DeviceMixin, TestCase):
    """비밀번호 변경은 그 계정 토큰만 전부 지우고 지금 기기에 하나를 낸다."""

    def change(self, key, new=NEW_PASSWORD):
        return self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": new},
            content_type="application/json",
            **auth(key),
        )

    def test_내_기기는_전부_끊기고_남의_기기는_그대로다(self):
        mine = [self.device(self.owner) for _ in range(3)]
        theirs = [self.device(self.other) for _ in range(2)]

        res = self.change(mine[1])

        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.json()), {"token", "user", "created"})
        fresh = res.json()["token"]
        self.assertEqual(
            list(LoginToken.objects.filter(user=self.owner).values_list("key", flat=True)),
            [fresh],
        )
        for key in mine:
            self.assertEqual(self.me(key), 401)
        for key in theirs:
            self.assertEqual(self.me(key), 200)

    def test_실패한_변경은_어느_토큰도_안_지운다(self):
        mine = [self.device(self.owner) for _ in range(2)]

        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD + "x", "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(mine[0]),
        )

        self.assertEqual(res.status_code, 400)
        for key in mine:
            self.assertEqual(self.me(key), 200)

    def test_세션으로_바꿔도_토큰을_다_지우고_하나를_낸다(self):
        old = [self.device(self.owner) for _ in range(2)]
        session = Client()
        session.force_login(self.owner)

        res = session.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 1)
        self.assertFalse(LoginToken.objects.filter(key__in=old).exists())


class AccountDeletionTest(DeviceMixin, TestCase):
    """탈퇴와 1년 미접속 파기는 그 계정의 토큰을 새 표·옛 표 모두에서 없앤다."""

    def stale(self, user):
        """파기 대상으로 만든다. 안내를 보낸 지 30일이 지났고 1년 가까이 안 썼다."""
        User.objects.filter(pk=user.pk).update(
            last_seen_on=timezone.localdate() - timedelta(days=400),
            purge_notice_sent_at=timezone.now() - timedelta(days=40),
        )

    def assert_only_others_left(self, others):
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
        self.assertEqual(LoginToken.objects.filter(user_id=self.owner.pk).count(), 0)
        self.assertEqual(DrfToken.objects.filter(user_id=self.owner.pk).count(), 0)
        for key in others:
            self.assertEqual(self.me(key), 200)

    def test_탈퇴하면_모든_기기의_토큰과_옛_표의_행이_사라진다(self):
        mine = [self.device(self.owner) for _ in range(3)]
        DrfToken.objects.create(user=self.owner)
        others = [self.device(self.other)]
        DrfToken.objects.create(user=self.other)

        res = self.client.delete(
            ME_URL, {"current_password": PASSWORD}, content_type="application/json",
            **auth(mine[0]),
        )

        self.assertEqual(res.status_code, 204)
        self.assert_only_others_left(others)
        self.assertTrue(DrfToken.objects.filter(user=self.other).exists())
        for key in mine:
            self.assertEqual(self.me(key), 401)

    def test_옛_표의_값과_같은_토큰으로_탈퇴해도_실패하지_않는다(self):
        """0010 이 옮긴 값을 쿠키에 든 채 탈퇴하는 사람. 두 표에 같은 값이 있다."""
        old = DrfToken.objects.create(user=self.owner)
        LoginToken.objects.create(user=self.owner, key=old.key)

        res = self.client.delete(
            ME_URL, {"current_password": PASSWORD}, content_type="application/json",
            **auth(old.key),
        )

        self.assertEqual(res.status_code, 204)
        self.assert_only_others_left([])

    def test_파기하면_토큰과_옛_표의_행이_함께_지워진다(self):
        for _ in range(2):
            LoginToken.objects.create(user=self.owner)
        DrfToken.objects.create(user=self.owner)
        others = [self.device(self.other)]
        self.stale(self.owner)

        self.assertEqual(purge.delete_expired(), 1)

        self.assert_only_others_left(others)

    def test_daily_cleanup_apply_로_파기해도_토큰이_남지_않는다(self):
        LoginToken.objects.create(user=self.owner)
        DrfToken.objects.create(user=self.owner)
        self.stale(self.owner)

        call_command("daily_cleanup", "--apply", stdout=StringIO())

        self.assert_only_others_left([])

    def test_관리자_화면에서_회원을_지워도_토큰이_남지_않는다(self):
        LoginToken.objects.create(user=self.owner)
        DrfToken.objects.create(user=self.owner)
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(admin)

        res = self.client.post(
            f"/admin/accounts/user/{self.owner.pk}/delete/", {"post": "yes"}
        )

        self.assertEqual(res.status_code, 302)
        self.client.logout()
        self.assert_only_others_left([])


class EmailLinkDeviceTest(DeviceMixin, TestCase):
    """이메일 변경 링크는 신청한 기기의 로그인이 살아 있는 동안만 통한다. 기기 셋으로 본다."""

    def setUp(self):
        super().setUp()
        self.phone, self.laptop, self.tablet = (self.device(self.owner) for _ in range(3))

    def issue(self, key, new_email="next@example.com", password=PASSWORD):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": new_email, "current_password": password},
                content_type="application/json",
                **auth(key),
            )
        self.assertEqual(res.status_code, 202)
        return sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

    def confirm(self, link):
        return Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )

    def assert_works(self, link, new_email="next@example.com"):
        res = self.confirm(link)
        self.assertEqual(res.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, new_email)
        return res.json()["token"]

    def assert_rejected(self, link):
        res = self.confirm(link)
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "owner@example.com")

    def test_가운데_기기에서_신청하면_양옆_기기가_로그아웃해도_통한다(self):
        link = self.issue(self.laptop)
        self.assertEqual(self.logout(self.phone), 204)
        self.assertEqual(self.logout(self.tablet), 204)

        self.assert_works(link)

    def test_두_기기에서_각각_신청하고_한쪽만_로그아웃하면_그쪽_링크만_죽는다(self):
        from_phone = self.issue(self.phone, "phone@example.com")
        from_tablet = self.issue(self.tablet, "tablet@example.com")
        self.assertEqual(self.logout(self.phone), 204)

        self.assert_rejected(from_phone)
        self.assert_works(from_tablet, "tablet@example.com")

    def test_신청한_기기가_아닌_곳에서_비밀번호를_바꿔도_링크는_죽는다(self):
        link = self.issue(self.tablet)

        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(self.phone),
        )
        self.assertEqual(res.status_code, 200)

        self.assert_rejected(link)

    def test_변경을_끝내면_다른_기기에서_받은_대기_링크도_죽는다(self):
        from_phone = self.issue(self.phone, "phone@example.com")
        from_laptop = self.issue(self.laptop, "laptop@example.com")

        fresh = self.assert_works(from_laptop, "laptop@example.com")

        self.assertEqual(
            list(LoginToken.objects.filter(user=self.owner).values_list("key", flat=True)),
            [fresh],
        )
        res = self.confirm(from_phone)
        self.assertEqual(res.status_code, 400)

    def test_세_기기를_번갈아_a_b_a_를_해도_옛_링크는_모두_죽는다(self):
        first = self.issue(self.phone, "next@example.com")
        fresh = self.assert_works(first)
        back = self.issue(fresh, "owner@example.com")
        newest = self.assert_works(back, "owner@example.com")
        # 돌아온 뒤 다른 기기 셋이 새로 로그인한다. 옛 링크가 그 토큰에 맞으면 안 된다.
        for _ in range(3):
            self.assertEqual(self.login().status_code, 200)

        self.assert_rejected(first)
        self.assert_rejected(back)
        self.assertEqual(self.me(newest), 200)

    def test_남의_계정에서_로그아웃하거나_비밀번호를_바꿔도_내_링크는_산다(self):
        link = self.issue(self.phone)
        stranger = self.device(self.other)
        self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(stranger),
        )
        self.assertEqual(self.logout(self.device(self.other)), 204)

        self.assert_works(link)

    def test_신청한_기기가_로그아웃한_뒤_다른_기기에서_다시_받으면_새_링크만_통한다(self):
        old = self.issue(self.phone)
        self.assertEqual(self.logout(self.phone), 204)
        new = self.issue(self.laptop)

        self.assert_rejected(old)
        self.assert_works(new)

    def test_남의_토큰과_같은_대조값은_내_계정에서_통하지_않는다(self):
        """확인 뷰가 링크의 회원 번호가 아니라 아무 계정의 토큰이나 대조하면 뚫린다."""
        link = self.issue(self.phone)
        user_id, mark, _ = read_token(link)
        self.assertEqual(user_id, self.owner.pk)
        others = LoginToken.objects.filter(user_id=self.other.pk)
        for key in others.values_list("key", flat=True):
            self.assertNotEqual(email_mark(self.owner.email, key), mark)
        LoginToken.objects.filter(key=self.phone).update(user=self.other)

        self.assert_rejected(link)


class SessionLinkBindingTest(DeviceMixin, TestCase):
    """관리자 세션으로 신청하면 그 계정의 토큰 하나에 묶이고, 새 토큰은 없을 때만 만든다."""

    def issue(self):
        session = Client()
        session.force_login(self.owner)
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = session.post(
                EMAIL_CHANGE_URL,
                {"new_email": "next@example.com", "current_password": PASSWORD},
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 202)
        return sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

    def confirm(self, link) -> int:
        return Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        ).status_code

    def test_토큰이_있으면_새로_만들지_않고_그중_하나에만_묶인다(self):
        keys = [self.device(self.owner) for _ in range(2)]

        link = self.issue()

        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 2)
        _, mark, _ = read_token(link)
        bound = [key for key in keys if email_mark(self.owner.email, key) == mark]
        self.assertEqual(len(bound), 1)

    def test_묶인_토큰이_지워지면_다른_토큰이_남아_있어도_거절된다(self):
        keys = [self.device(self.owner) for _ in range(2)]
        link = self.issue()
        _, mark, _ = read_token(link)
        (bound,) = [key for key in keys if email_mark(self.owner.email, key) == mark]

        LoginToken.objects.filter(key=bound).delete()

        self.assertEqual(self.confirm(link), 400)

    def test_묶이지_않은_토큰이_지워지면_링크는_산다(self):
        keys = [self.device(self.owner) for _ in range(2)]
        link = self.issue()
        _, mark, _ = read_token(link)
        (loose,) = [key for key in keys if email_mark(self.owner.email, key) != mark]

        LoginToken.objects.filter(key=loose).delete()

        self.assertEqual(self.confirm(link), 200)

    def test_남의_토큰만_있으면_내_토큰을_새로_만든다(self):
        """남의 토큰을 집어 오면 남의 로그아웃이 내 링크를 죽인다."""
        self.device(self.other)

        link = self.issue()

        mine = list(LoginToken.objects.filter(user=self.owner).values_list("key", flat=True))
        self.assertEqual(len(mine), 1)
        self.assertEqual(read_token(link)[1], email_mark(self.owner.email, mine[0]))


class AdminScreenTest(DeviceMixin, TestCase):
    """관리자 화면은 토큰 값을 보여주지 않고 추가를 막는다. 옛 DRF 화면은 없다."""

    def setUp(self):
        super().setUp()
        self.key = self.device(self.owner)
        self.spare = self.device(self.owner)
        self.token = LoginToken.objects.get(key=self.key)
        self.root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.admin = Client()
        self.admin.force_login(self.root)

    def change_url(self, token=None):
        return f"{ADMIN_LIST_URL}{(token or self.token).pk}/change/"

    def test_로그인_안_했거나_직원이_아니면_관리자_화면으로_돌려보낸다(self):
        member = Client()
        member.force_login(self.owner)
        for client in (Client(), member):
            res = client.get(ADMIN_LIST_URL)
            self.assertEqual(res.status_code, 302)
            self.assertIn("/admin/login/", res["Location"])

    def test_권한_없는_직원은_403(self):
        staff = User.objects.create_user(
            email="staff@example.com", password=PASSWORD, is_staff=True
        )
        client = Client()
        client.force_login(staff)

        self.assertEqual(client.get(ADMIN_LIST_URL).status_code, 403)
        self.assertEqual(client.get(self.change_url()).status_code, 403)

    def test_토큰을_들고_와도_관리자_화면에는_못_들어간다(self):
        """API 토큰은 세션이 아니다. 관리자 화면은 토큰을 인증으로 받지 않는다."""
        User.objects.filter(pk=self.owner.pk).update(is_staff=True, is_superuser=True)

        res = Client().get(ADMIN_LIST_URL, **auth(self.key))

        self.assertEqual(res.status_code, 302)

    def test_목록과_상세에_토큰_값이_안_나온다(self):
        for url in (ADMIN_LIST_URL, self.change_url(), f"{self.change_url()[:-7]}history/"):
            with self.subTest(url=url):
                res = self.admin.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertNotContains(res, self.key)
                self.assertNotContains(res, self.spare)

    def test_상세_주소는_토큰_값이_아니라_번호로_만든다(self):
        res = self.admin.get(ADMIN_LIST_URL)

        self.assertContains(res, self.change_url())
        self.assertNotEqual(self.admin.get(f"{ADMIN_LIST_URL}{self.key}/change/").status_code,
                            200)

    def test_추가_화면은_403(self):
        self.assertEqual(self.admin.get(ADMIN_ADD_URL).status_code, 403)
        self.assertEqual(self.admin.post(ADMIN_ADD_URL, {"user": self.owner.pk}).status_code,
                         403)
        self.assertEqual(LoginToken.objects.count(), 2)

    def test_DRF_토큰_화면은_떼어졌다(self):
        DrfToken.objects.create(user=self.owner)

        self.assertEqual(self.admin.get(DRF_TOKEN_ADMIN_URL).status_code, 404)
        res = self.admin.get("/admin/")
        self.assertNotContains(res, DRF_TOKEN_ADMIN_URL)
        self.assertContains(res, ADMIN_LIST_URL)

    def test_상세에서_저장해도_값과_주인이_안_바뀐다(self):
        res = self.admin.post(
            self.change_url(),
            {"key": "leakmark-" + "x" * 31, "user": self.other.pk, "created": "2000-01-01"},
        )

        self.assertIn(res.status_code, (200, 302))
        self.token.refresh_from_db()
        self.assertEqual(self.token.key, self.key)
        self.assertEqual(self.token.user_id, self.owner.pk)

    def test_관리자가_지우면_그_기기만_끊기고_기록에_값이_안_남는다(self):
        res = self.admin.post(self.change_url()[:-7] + "delete/", {"post": "yes"})

        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.me(self.key), 401)
        self.assertEqual(self.me(self.spare), 200)
        entry = LogEntry.objects.latest("action_time")
        self.assertNotIn(self.key, entry.object_repr)
        self.assertNotIn(self.key, entry.object_id)

    def test_일괄_삭제도_고른_기기만_끊는다(self):
        theirs = self.device(self.other)

        res = self.admin.post(
            ADMIN_LIST_URL,
            {"action": "delete_selected", "_selected_action": [self.token.pk], "post": "yes"},
        )

        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.me(self.key), 401)
        self.assertEqual(self.me(self.spare), 200)
        self.assertEqual(self.me(theirs), 200)

    def test_검색창에_토큰_값을_넣어도_찾아지지_않는다(self):
        """검색이 토큰 값을 보면 값을 맞혀 보는 창구가 된다."""
        res = self.admin.get(ADMIN_LIST_URL, {"q": self.key})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["cl"].result_count, 0)

    def test_회원_화면에서_토큰_값으로_걸러_볼_수_없다(self):
        res = self.admin.get("/admin/accounts/user/", {"login_tokens__key": self.key})

        self.assertNotEqual(res.status_code, 200)

    def test_주소_검색어로_토큰_값을_한_글자씩_맞혀_볼_수_없다(self):
        """?key__startswith= 같은 주소 검색어는 거절한다.

        Django 관리자 목록은 자기 표의 칸이면 list_filter 에 없어도 주소 검색어
        (lookup)를 받는다(ModelAdmin.lookup_allowed). 결과 개수가 0/1 로 갈리면
        16진수 40자를 한 글자씩 640번 안에 맞힌다. 화면에 값을 안 띄운 것이
        소용없어진다.
        """
        for lookup in ("key", "key__startswith", "key__exact", "key__in", "key__gte"):
            with self.subTest(lookup):
                res = self.admin.get(ADMIN_LIST_URL, {lookup: self.key[:20]})
                self.assertEqual(res.status_code, 400)

    def test_보기_권한만_있는_직원도_주소_검색어로_토큰을_못_거른다(self):
        key = self.device(self.owner)
        staff = User.objects.create_user(
            email="viewer@example.com", password=PASSWORD, is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_logintoken"))
        client = Client()
        client.force_login(staff)

        self.assertEqual(client.get(ADMIN_LIST_URL).status_code, 200)
        res = client.get(ADMIN_LIST_URL, {"key__startswith": key[:4]})

        self.assertEqual(res.status_code, 400)


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


@unittest.skipUnless(connection.vendor == "postgresql", "동시성은 Postgres 에서만 뜻이 있다")
class ConcurrencyTest(TransactionTestCase):
    """같은 토큰이나 같은 계정에 동시에 요청이 몰릴 때 500 이 없고 남는 토큰이 맞는가."""

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def device(self, user=None) -> str:
        return LoginToken.objects.create(user=user or self.owner).key

    def test_같은_토큰으로_동시에_로그아웃해도_500_없이_그_토큰만_사라진다(self):
        key = self.device()
        kept = [self.device(), self.device(self.other)]

        results = _together(*[
            (lambda client: client.post(LOGOUT_URL, **auth(key))) for _ in range(4)
        ])

        statuses = sorted(status for status, _ in results)
        self.assertEqual(len(statuses), 4)
        self.assertTrue(set(statuses) <= {204, 401}, statuses)
        self.assertIn(204, statuses)
        self.assertFalse(LoginToken.objects.filter(key=key).exists())
        self.assertEqual(LoginToken.objects.filter(key__in=kept).count(), 2)

    def test_한_계정의_기기들이_동시에_로그아웃하면_각자_것만_지운다(self):
        leaving = [self.device() for _ in range(3)]
        staying = self.device()

        results = _together(*[
            (lambda client, key=key: client.post(LOGOUT_URL, **auth(key))) for key in leaving
        ])

        self.assertEqual(sorted(status for status, _ in results), [204, 204, 204])
        self.assertEqual(
            list(LoginToken.objects.filter(user=self.owner).values_list("key", flat=True)),
            [staying],
        )

    def test_동시에_로그인해도_매번_다른_토큰이다(self):
        def login(client):
            return client.post(
                LOGIN_URL,
                {"email": "owner@example.com", "password": PASSWORD},
                content_type="application/json",
            )

        results = _together(*[login] * 5)

        self.assertEqual([status for status, _ in results], [200] * 5)
        keys = {body["token"] for _, body in results}
        self.assertEqual(len(keys), 5)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 5)

    def test_두_기기가_동시에_비밀번호를_바꿔도_500_없고_제삼의_기기는_끊긴다(self):
        """누가 이기든 변경에 끼지 않은 기기(가로챈 토큰)는 살아남으면 안 된다.

        남는 토큰은 200 응답으로 내준 것뿐이어야 한다. 엇갈려 둘 다 남을 수는
        있다(둘 다 지운 뒤 둘 다 만든 경우). 둘 다 옛 비밀번호를 알던 기기다.
        """
        phone, laptop, intruder = self.device(), self.device(), self.device()
        theirs = self.device(self.other)

        def change(key, new):
            return lambda client: client.post(
                PASSWORD_URL,
                {"current_password": PASSWORD, "new_password": new},
                content_type="application/json",
                **auth(key),
            )

        results = _together(change(phone, OTHER_A), change(laptop, OTHER_B))

        statuses = [status for status, _ in results]
        self.assertEqual(len(statuses), 2)
        self.assertTrue(set(statuses) <= {200, 400, 401}, statuses)
        self.assertIn(200, statuses)
        issued = {body["token"] for status, body in results if status == 200}
        left = set(LoginToken.objects.filter(user=self.owner).values_list("key", flat=True))
        self.assertTrue(left, "지금 기기마저 끊겼다")
        self.assertTrue(left <= issued, (left, issued))
        self.assertNotIn(intruder, left)
        self.assertTrue(LoginToken.objects.filter(key=theirs).exists())

    def test_비밀번호_변경과_다른_기기_로그아웃이_겹쳐도_500_이_없다(self):
        phone, laptop = self.device(), self.device()

        results = _together(
            lambda client: client.post(
                PASSWORD_URL,
                {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
                content_type="application/json",
                **auth(phone),
            ),
            lambda client: client.post(LOGOUT_URL, **auth(laptop)),
        )

        # 로그아웃은 비밀번호 변경이 토큰을 지운 뒤에 인증하면 401 이다. 어느 쪽이든 된다.
        statuses = sorted(status for status, _ in results)
        self.assertIn(statuses, ([200, 204], [200, 401]))
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 1)
        self.assertFalse(LoginToken.objects.filter(key__in=[phone, laptop]).exists())


class SabotageTest(DeviceMixin, TestCase):
    """방어를 일부러 빼면 위 테스트들이 빨개지는지 확인한다(구현 파일은 건드리지 않는다)."""

    def test_로그아웃이_계정_토큰을_다_지우면_범위_테스트가_잡는다(self):
        def wipe_all(self_view, request):
            from rest_framework.response import Response

            LoginToken.objects.filter(user=request.user).delete()
            return Response(status=204)

        with mock.patch("apps.accounts.views.LogoutView.post", wipe_all):
            result = unittest.TestResult()
            LogoutScopeTest("test_내_기기_하나만_지우고_다른_기기와_남의_토큰은_남는다").run(result)

        self.assertEqual(len(result.failures) + len(result.errors), 1)

    def test_확인_뷰가_아무_계정_토큰이나_대조하면_링크_테스트가_잡는다(self):
        real_filter = LoginToken.objects.filter

        def any_user(*args, **kwargs):
            if set(kwargs) == {"user"}:
                return LoginToken.objects.all()
            return real_filter(*args, **kwargs)

        with mock.patch.object(LoginToken.objects, "filter", side_effect=any_user):
            result = unittest.TestResult()
            EmailLinkDeviceTest("test_남의_토큰과_같은_대조값은_내_계정에서_통하지_않는다").run(
                result
            )

        self.assertEqual(len(result.failures) + len(result.errors), 1)

    def test_인증이_정지_계정을_통과시키면_정지_테스트가_잡는다(self):
        from .authentication import SlimTokenAuthentication

        def lax(self_auth, key):
            token = LoginToken.objects.select_related("user").get(key=key)
            return token.user, token

        with mock.patch.object(SlimTokenAuthentication, "authenticate_credentials", lax):
            result = unittest.TestResult()
            InactiveAccountTest("test_정지_계정_토큰은_모든_기기에서_401").run(result)

        self.assertEqual(len(result.failures) + len(result.errors), 1)
