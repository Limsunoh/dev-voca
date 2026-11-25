"""보안 점검 보강(Admin 로그인 전체 상한, ASCII 이메일, 자격 변경 시 로그인 끊기, 운영 DRF 화면)을
깨뜨려 보는 테스트.

계약:
  - Admin 로그인: 기기 쿠키 없는 시도는 이메일과 상관없이 한 통(운영 시간당 30)으로 센다.
    username 이 없거나 공백이어도 센다. 막히면 Retry-After 가 한 시간 안의 정수다. 그 이메일의
    기기 쿠키를 낸 시도는 이 통을 타지 않고 채우지도 않는다. 남의 이메일에 쓴 쿠키나 서명이
    틀린 쿠키는 건너뛰기 표가 아니다.
  - 가입·이메일 변경: ASCII 밖 글자가 하나라도 든 주소는 400 이다(500 아님). 닮은 글자,
    한글 도메인, 폭 없는 글자 모두. punycode(xn--) 도메인은 ASCII 라 통과한다.
  - 비밀번호·이메일이 바뀌면 그 계정의 토큰이 모두 끝난다. 그러나 바뀐 직후 API 가 새로 준
    토큰은 살아 있다. 사진 갱신, 해시 갱신(로그인), 이어 가기, 프로필 수정은 로그인을 안
    끊는다.
  - 운영(DEBUG 아님)의 DRF 렌더러는 JSON 하나다.
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .authentication import SlimTokenAuthentication
from .models import LoginToken
from .tests import (
    CONSENT,
    EMAIL_CHANGE_CONFIRM_URL,
    EMAIL_CHANGE_URL,
    GOOGLE_URL,
    LOGIN_URL,
    ME_URL,
    PASSWORD,
    PHOTO_URL,
    REDIRECT_URI,
    SIGNUP_URL,
    _png,
    _upload,
)
from .tests_security_hardening_dynamic import (
    ADMIN_LOGIN,
    TOO_MANY,
    device_cookie_value,
    use_production_rates,
)
from .throttles import ADMIN_DEVICE_COOKIE

User = get_user_model()

PASSWORD_URL = "/api/accounts/password/"
RENEW_URL = "/api/accounts/token/renew/"
NEW_PASSWORD = PASSWORD + "-next"


def auth(key: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Token {key}"}


# ---- Admin 로그인 전체 통 --------------------------------------------------------


class AdminLoginTotalBucketCase(TestCase):
    """운영 값(전체 30, 이메일 10)으로 센다. 테스트 값은 넉넉해 아무것도 안 막는다."""

    BOSS = "boss@example.com"
    OTHER_ADMIN = "second@example.com"

    def setUp(self):
        cache.clear()
        use_production_rates(self, "admin_login", "admin_login_total")
        self.boss = User.objects.create_superuser(email=self.BOSS, password=PASSWORD)

    def post(self, client, data: dict):
        return client.post(ADMIN_LOGIN, data)

    def fill_all_bucket(self, already: int = 0) -> None:
        """쿠키 없는 시도를 이메일을 바꿔 가며 전체 통이 찰 때까지 낸다. 이메일 통에는 하나도
        안 걸린다. already 는 앞서 쿠키 없이 한 시도(처음 로그인 등)의 수다."""
        for n in range(30 - already):
            res = self.post(self.client_class(), {"username": f"u{n}@example.com", "password": "x"})
            self.assertEqual(res.status_code, 200, n)

    def logged_in_browser(self, email: str):
        browser = self.client_class()
        res = self.post(browser, {"username": email, "password": PASSWORD})
        self.assertEqual(res.status_code, 302)
        self.assertIn(ADMIN_DEVICE_COOKIE, res.cookies)
        browser.cookies.pop("sessionid", None)
        return browser


class AdminLoginTotalBucketTest(AdminLoginTotalBucketCase):
    def test_서른_번_뒤에는_맞는_비밀번호도_429_이고_Retry_After_는_한_시간_안의_정수(self):
        self.fill_all_bucket()

        stranger = self.client_class()
        res = self.post(stranger, {"username": self.BOSS, "password": PASSWORD})

        self.assertEqual(res.status_code, 429)
        self.assertRegex(res.content.decode(), TOO_MANY)
        seconds = int(res["Retry-After"])
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 3600)
        self.assertNotIn("_auth_user_id", stranger.session)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, res.cookies)

    def test_username_칸이_없거나_공백뿐이어도_500_없이_센다(self):
        bodies = [{}, {"username": "   "}, {"username": "", "password": ""}]
        codes = [self.post(self.client_class(), bodies[n % 3]).status_code for n in range(31)]

        self.assertEqual(codes[:30], [200] * 30)
        self.assertEqual(codes[30], 429)

    def test_기기_쿠키를_낸_시도는_전체_통을_채우지_않는다(self):
        browser = self.logged_in_browser(self.BOSS)
        # 로그인 한 번이 전체 통에 하나 남았다. 쿠키 있는 브라우저가 열 번 틀린다(기기 몫 전부).
        for _ in range(10):
            self.assertEqual(
                self.post(browser, {"username": self.BOSS, "password": "x"}).status_code, 200
            )

        # 쿠키 없는 시도는 아직 스물아홉 번이 남아 있어야 한다.
        codes = [
            self.post(
                self.client_class(), {"username": f"u{n}@example.com", "password": "x"}
            ).status_code
            for n in range(30)
        ]
        self.assertEqual(codes, [200] * 29 + [429])

    def test_다른_관리자의_이메일에는_내_기기_쿠키가_건너뛰기_표가_아니다(self):
        User.objects.create_superuser(email=self.OTHER_ADMIN, password=PASSWORD)
        browser = self.logged_in_browser(self.BOSS)
        self.fill_all_bucket(already=1)

        res = self.post(browser, {"username": self.OTHER_ADMIN, "password": PASSWORD})
        self.assertEqual(res.status_code, 429)
        self.assertNotIn("_auth_user_id", browser.session)

        # 자기 이메일로는 들어온다.
        self.assertEqual(
            self.post(browser, {"username": self.BOSS, "password": PASSWORD}).status_code, 302
        )

    def test_자기_이메일의_대문자_표기로도_쿠키가_통한다(self):
        browser = self.logged_in_browser(self.BOSS)
        self.fill_all_bucket(already=1)

        res = self.post(browser, {"username": "BOSS@Example.COM", "password": PASSWORD})
        self.assertEqual(res.status_code, 302)

    def test_서명이_틀린_쿠키는_전체_통을_건너뛰지_못한다(self):
        self.fill_all_bucket()
        forged = self.client_class()
        good = device_cookie_value(self.BOSS)
        forged.cookies[ADMIN_DEVICE_COOKIE] = good[:-2] + (
            "AA" if not good.endswith("AA") else "BB"
        )

        self.assertEqual(
            self.post(forged, {"username": self.BOSS, "password": PASSWORD}).status_code, 429
        )

    def test_서버가_낸_꼴의_쿠키는_처음_보는_브라우저에서도_통한다(self):
        """쿠키 값만 맞으면 된다. 로그인했던 그 클라이언트 객체일 필요는 없다."""
        self.fill_all_bucket()
        browser = self.client_class()
        browser.cookies[ADMIN_DEVICE_COOKIE] = device_cookie_value(self.BOSS)

        self.assertEqual(
            self.post(browser, {"username": self.BOSS, "password": PASSWORD}).status_code, 302
        )


# ---- ASCII 밖 이메일 -------------------------------------------------------------


# 이스케이프로 적는다. 소스에 그대로 두면 편집기가 바꿔도 테스트가 초록으로 남는다.
NON_ASCII_EMAILS = {
    "긴 s(U+017F)": "bo\u017fs@example.com",
    "점 없는 i(U+0131)": "b\u0131ll@example.com",
    "켈빈 기호(U+212A)": "\u212aate@example.com",
    "점 있는 I(U+0130)": "\u0130vy@example.com",
    "도메인의 폭 없는 공백": "boss@exa\u200bmple.com",
    "한글 도메인": "boss@한글.com",
    "한글 앞부분": "보스@example.com",
}


class PlainEmailSignUpTest(TestCase):
    def setUp(self):
        cache.clear()

    def signup(self, email: str):
        return self.client.post(
            SIGNUP_URL,
            {"email": email, "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

    def test_ASCII_밖_글자가_든_주소는_400_이고_계정이_안_생긴다(self):
        for label, email in NON_ASCII_EMAILS.items():
            with self.subTest(label):
                res = self.signup(email)
                self.assertEqual(res.status_code, 400)
                self.assertIn("email", res.json())
        self.assertEqual(User.objects.count(), 0)

    def test_punycode_도메인과_대문자_ASCII_는_받는다(self):
        self.assertEqual(self.signup("boss@xn--9n2bp8q.com").status_code, 201)
        self.assertEqual(self.signup("Boss@Example.COM").status_code, 201)
        self.assertTrue(User.objects.filter(email="boss@example.com").exists())

    def test_닮은_글자_가입을_시도한_뒤에도_진짜_주인의_로그인은_500_이_아니다(self):
        """막기 전에는 bo\u017fs 가 가입되고, 진짜 주인의 구글 로그인이 계정을 하나 더 만들어
        boss@example.com 의 이메일 로그인이 MultipleObjectsReturned 로 500 이 됐다."""
        self.signup("bo\u017fs@example.com")
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "boss@example.com", "name": "주인", "picture": ""},
        ):
            google = self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )
        self.assertEqual(google.status_code, 201)

        res = self.client.post(
            LOGIN_URL,
            {"email": "boss@example.com", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_ASCII_밖_주소로_로그인해도_500_이_아니다(self):
        User.objects.create_user(email="boss@example.com", password=PASSWORD)
        for label, email in NON_ASCII_EMAILS.items():
            with self.subTest(label):
                res = self.client.post(
                    LOGIN_URL, {"email": email, "password": "x"}, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400)


class PlainEmailChangeTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="old@example.com", password=PASSWORD)
        self.token = LoginToken.objects.create(user=self.user)

    def request_change(self, new_email: str):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": new_email, "current_password": PASSWORD},
                content_type="application/json",
                **auth(self.token.key),
            )
        return res, sent

    def test_ASCII_밖_글자가_든_새_주소는_400_이고_메일이_안_나간다(self):
        for label, email in NON_ASCII_EMAILS.items():
            with self.subTest(label):
                res, sent = self.request_change(email)
                self.assertEqual(res.status_code, 400)
                self.assertIn("new_email", res.json())
                sent.assert_not_called()

    def test_punycode_도메인으로는_바꿀_수_있다(self):
        res, sent = self.request_change("me@xn--9n2bp8q.com")
        self.assertEqual(res.status_code, 202)
        self.assertEqual(sent.call_args.kwargs["to"], "me@xn--9n2bp8q.com")

    def test_닮은_글자로_진짜_주소를_찜하지_못한다(self):
        """bo\u017fs 로 바꿔 두면 진짜 boss@example.com 의 가입이 "이미 가입된 이메일" 로 막혔다."""
        res, sent = self.request_change("bo\u017fs@example.com")
        # 막지 못했다면 링크까지 눌러 끝까지 간다. 신청만 보면 막혔는지 알 수 없다.
        if sent.called:
            link = sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]
            self.client.post(
                EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
            )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

        res = self.client.post(
            SIGNUP_URL,
            {"email": "boss@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        sent.assert_not_called()


# ---- 비밀번호·이메일이 바뀌면 로그인을 끊는다 -------------------------------------


class CredentialChangeFlowCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="member@example.com", password=PASSWORD, display_name="회원"
        )
        self.phone = LoginToken.objects.create(user=self.user)
        self.laptop = LoginToken.objects.create(user=self.user)

    def alive(self, key: str) -> bool:
        return self.client.get(ME_URL, **auth(key)).status_code == 200

    def assertAllEnded(self, *keys: str) -> None:
        for key in keys:
            self.assertFalse(self.alive(key), key[:6])

    def assertAllAlive(self, *keys: str) -> None:
        for key in keys:
            self.assertTrue(self.alive(key), key[:6])


class ApiCredentialChangeTest(CredentialChangeFlowCase):
    def test_비밀번호_변경이_준_새_토큰은_살고_옛_토큰은_모두_끝난다(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(self.phone.key),
        )
        self.assertEqual(res.status_code, 200)
        fresh = res.json()["token"]

        self.assertTrue(self.alive(fresh))
        self.assertAllEnded(self.phone.key, self.laptop.key)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)

    def test_이메일_변경_확인이_준_새_토큰은_살고_옛_토큰은_모두_끝난다(self):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            self.client.post(
                EMAIL_CHANGE_URL,
                {"new_email": "moved@example.com", "current_password": PASSWORD},
                content_type="application/json",
                **auth(self.phone.key),
            )
        link_token = sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

        # 신청한 폰에서 누른다. 새 토큰은 같은 계정으로 로그인한 요청에만 온다.
        res = self.client.post(
            EMAIL_CHANGE_CONFIRM_URL,
            {"token": link_token},
            content_type="application/json",
            **auth(self.phone.key),
        )
        self.assertEqual(res.status_code, 200)
        fresh = res.json()["token"]

        self.assertTrue(self.alive(fresh))
        self.assertAllEnded(self.phone.key, self.laptop.key)
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "moved@example.com")

    def test_새_토큰으로_곧바로_다시_비밀번호를_바꿔도_그_요청의_새_토큰이_산다(self):
        first = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **auth(self.phone.key),
        ).json()["token"]
        second = self.client.post(
            PASSWORD_URL,
            {"current_password": NEW_PASSWORD, "new_password": PASSWORD},
            content_type="application/json",
            **auth(first),
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(self.alive(second.json()["token"]))
        self.assertFalse(self.alive(first))


class FlowsThatKeepLoginsTest(CredentialChangeFlowCase):
    def test_구글_로그인이_사진을_갈아도_다른_기기는_안_끊긴다(self):
        self.user.google_picture = "https://lh3.googleusercontent.com/a/old"
        self.user.save(update_fields=["google_picture"])

        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={
                "email": "member@example.com",
                "name": "회원",
                "picture": "https://lh3.googleusercontent.com/a/new",
            },
        ):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI},
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            User.objects.get(pk=self.user.pk).google_picture,
            "https://lh3.googleusercontent.com/a/new",
        )
        self.assertAllAlive(self.phone.key, self.laptop.key, res.json()["token"])

    def test_구글_첫_로그인으로_만든_계정의_토큰이_산다(self):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "fresh@example.com", "name": "새사람", "picture": ""},
        ):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(self.alive(res.json()["token"]))

    def test_비밀번호_해시_갱신은_비밀번호_변경이_아니다(self):
        """Django 가 반복 횟수를 올리면 로그인하는 순간 해시를 다시 저장한다. 그것을 변경으로
        보면 장고를 올린 날 로그인하는 사람마다 다른 기기가 모두 끊긴다."""
        hasher = PBKDF2PasswordHasher()
        old_hash = hasher.encode(PASSWORD, hasher.salt(), iterations=1000)
        User.objects.filter(pk=self.user.pk).update(password=old_hash)

        res = self.client.post(
            LOGIN_URL,
            {"email": "member@example.com", "password": PASSWORD},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        # 해시가 실제로 다시 저장됐다(갱신 길을 탔다).
        self.assertNotEqual(User.objects.get(pk=self.user.pk).password, old_hash)
        self.assertAllAlive(self.phone.key, self.laptop.key, res.json()["token"])

    def test_이어_가기로_받은_새_토큰과_다른_기기가_산다(self):
        LoginToken.objects.filter(pk=self.phone.pk).update(
            created=timezone.now() - timedelta(days=2)
        )

        res = self.client.post(RENEW_URL, **auth(self.phone.key))

        self.assertEqual(res.status_code, 200)
        renewed = res.json()["token"]
        self.assertNotEqual(renewed, self.phone.key)
        self.assertAllAlive(renewed, self.laptop.key)

    def test_이름_수정과_사진_올리기는_로그인을_안_끊는다(self):
        self.assertEqual(
            self.client.patch(
                ME_URL,
                {"display_name": "새이름"},
                content_type="application/json",
                **auth(self.phone.key),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                PHOTO_URL, {"photo": _upload(_png())}, **auth(self.phone.key)
            ).status_code,
            200,
        )
        self.assertAllAlive(self.phone.key, self.laptop.key)

    def test_계정_삭제는_토큰을_같이_지운다(self):
        res = self.client.delete(
            ME_URL,
            {"current_password": PASSWORD},
            content_type="application/json",
            **auth(self.phone.key),
        )
        self.assertEqual(res.status_code, 204)
        self.assertFalse(LoginToken.objects.exists())

    def test_일일_정리는_활동_중인_회원의_토큰을_안_건드린다(self):
        stale = LoginToken.objects.create(user=self.user)
        LoginToken.objects.filter(pk=stale.pk).update(created=timezone.now() - timedelta(days=31))

        with mock.patch("apps.learning.management.commands.daily_cleanup.check_token"):
            call_command("daily_cleanup", "--apply", stdout=open(os.devnull, "w", encoding="utf-8"))

        self.assertFalse(LoginToken.objects.filter(pk=stale.pk).exists())
        self.assertAllAlive(self.phone.key, self.laptop.key)


class AdminFormCredentialChangeTest(CredentialChangeFlowCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(self.admin)

    def post_change(self, **changes):
        data = {
            "email": self.user.email,
            "display_name": self.user.display_name,
            "avatar": "",
            "google_picture": "",
            "is_active": "on",
            **changes,
        }
        return self.client.post(f"/admin/accounts/user/{self.user.pk}/change/", data)

    def test_회원_수정_폼에서_이메일을_바꾸면_끊긴다(self):
        self.assertEqual(self.post_change(email="moved@example.com").status_code, 302)
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "moved@example.com")
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_회원_수정_폼에서_이름만_바꾸면_안_끊긴다(self):
        self.assertEqual(self.post_change(display_name="바뀐이름").status_code, 302)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_회원_수정_폼에서_이메일의_대소문자만_바꾸면_안_끊긴다(self):
        self.assertEqual(self.post_change(email="Member@Example.com").status_code, 302)
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "member@example.com")
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_회원_수정_폼이_중복_이메일로_거절되면_안_끊긴다(self):
        res = self.post_change(email="admin@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_관리자가_자기_비밀번호를_바꾸면_자기_토큰도_끝나고_화면_세션은_남는다(self):
        own = LoginToken.objects.create(user=self.admin)
        res = self.client.post(
            f"/admin/accounts/user/{self.admin.pk}/password/",
            {"usable_password": "true", "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )
        self.assertEqual(res.status_code, 302)
        self.assertFalse(self.alive(own.key))
        # update_session_auth_hash 로 관리자 화면은 이어진다.
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertAllAlive(self.phone.key, self.laptop.key)


# ---- 운영의 DRF 화면 -------------------------------------------------------------


def renderers_when(debug: bool) -> list[str]:
    """DJANGO_DEBUG 를 바꿔 settings 를 다시 읽은 렌더러 목록. 끝나면 원래대로 되읽는다."""
    env = {
        "DJANGO_DEBUG": "1" if debug else "0",
        # 운영 조건에서 settings 가 요구하는 키. 값은 아무 글자나 길이만 맞추면 된다.
        "DJANGO_SECRET_KEY": "-".join(["settings", "reload", "only"] * 5),
        "DJANGO_ALLOWED_HOSTS": "testserver",
    }
    real_argv = sys.argv
    sys.argv = ["gunicorn"]
    try:
        with mock.patch.dict(os.environ, env):
            prod = importlib.reload(importlib.import_module("config.settings"))
            return list(prod.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"])
    finally:
        sys.argv = real_argv
        importlib.reload(importlib.import_module("config.settings"))


class BrowsableApiTest(TestCase):
    def test_운영에서는_JSON_렌더러_하나뿐이다(self):
        self.assertEqual(renderers_when(False), ["rest_framework.renderers.JSONRenderer"])

    def test_로컬에서는_브라우저_화면이_켜진다(self):
        self.assertIn("rest_framework.renderers.BrowsableAPIRenderer", renderers_when(True))


# ---- 지난 라운드에 찾은 두 결함과 그 뒤 고친 분기 ------------------------------------


class AdminDisablePasswordTest(CredentialChangeFlowCase):
    """Admin 비밀번호 화면의 "비밀번호 로그인 끄기". 지난번에는 토큰이 그대로 살았다."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        self.client.force_login(self.admin)

    def disable(self):
        return self.client.post(
            f"/admin/accounts/user/{self.user.pk}/password/",
            {"usable_password": "false", "unset-password": "1"},
        )

    def test_비밀번호_로그인을_끄면_그_회원의_토큰이_모두_끝난다(self):
        self.assertEqual(self.disable().status_code, 302)
        self.assertFalse(User.objects.get(pk=self.user.pk).has_usable_password())
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())
        # 관리자 자신의 화면은 이어진다.
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_unset_password_버튼_없이_보낸_끄기는_아무것도_안_바꾼다(self):
        res = self.client.post(
            f"/admin/accounts/user/{self.user.pk}/password/", {"usable_password": "false"}
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(User.objects.get(pk=self.user.pk).has_usable_password())
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_꺼진_뒤_다시_로그인한_토큰은_이름_저장에_안_끊긴다(self):
        """끄기 표시가 저장 뒤에도 남으면 다음 저장마다 끊는다."""
        self.disable()
        fresh = LoginToken.objects.create(user=self.user)
        user = User.objects.get(pk=self.user.pk)
        user.display_name = "다른이름"
        user.save()
        self.assertTrue(self.alive(fresh.key))

    def test_같은_객체로_끄고_저장한_뒤_다시_저장해도_새_토큰이_산다(self):
        user = User.objects.get(pk=self.user.pk)
        user.set_unusable_password()
        user.save()
        fresh = LoginToken.objects.create(user=self.user)
        user.display_name = "다른이름"
        user.save()
        self.assertTrue(self.alive(fresh.key))

    def test_저장하지_않은_새_객체에서_끄면_표시가_안_남는다(self):
        """Admin 의 계정 추가 폼(비밀번호 끄고 만들기)이 이 길이다. 만든 직후 토큰이 산다."""
        user = User(email="nopw@example.com")
        user.set_unusable_password()
        user.save()
        token = LoginToken.objects.create(user=user)
        user.display_name = "이름"
        user.save()
        self.assertTrue(LoginToken.objects.filter(pk=token.pk).exists())

    def test_끄고_비밀번호_아닌_칸만_저장하면_그때는_안_끊고_다음_전체_저장에_끊는다(self):
        user = User.objects.get(pk=self.user.pk)
        user.set_unusable_password()
        user.save(update_fields=["display_name"])
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)
        user.save()
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())


class StaleObjectSaveTest(CredentialChangeFlowCase):
    """다른 곳에서 이메일이 바뀐 뒤 이 객체로 이름만 저장하는 장면. 지난번에는 새 토큰까지 끊었다."""

    def move_email_elsewhere_and_log_in_again(self) -> LoginToken:
        other = User.objects.get(pk=self.user.pk)
        other.email = "moved@example.com"
        other.save(update_fields=["email"])
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())
        return LoginToken.objects.create(user=self.user)

    def test_refresh_뒤_이름을_저장해도_새_토큰이_산다(self):
        stale = User.objects.get(pk=self.user.pk)
        fresh = self.move_email_elsewhere_and_log_in_again()

        stale.refresh_from_db()
        stale.display_name = "새이름"
        stale.save()

        self.assertTrue(self.alive(fresh.key))
        self.assertEqual(User.objects.get(pk=self.user.pk).display_name, "새이름")

    def test_이메일만_다시_읽어도_기억이_갱신된다(self):
        stale = User.objects.get(pk=self.user.pk)
        fresh = self.move_email_elsewhere_and_log_in_again()
        stale.refresh_from_db(fields=["email"])
        stale.save()
        self.assertTrue(self.alive(fresh.key))

    def test_이메일을_빼고_읽은_객체의_이메일을_읽은_뒤_이름을_저장해도_안_끊는다(self):
        """defer 된 칸을 읽으면 Django 가 refresh_from_db(fields=[...]) 를 부른다."""
        lazy = User.objects.defer("email").get(pk=self.user.pk)
        self.assertEqual(lazy.email, "member@example.com")
        lazy.display_name = "새이름"
        lazy.save()
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)


class UpdateFieldsScopeTest(CredentialChangeFlowCase):
    """update_fields 에 든 칸만 비교한다. 저장하지 않은 칸의 변경으로는 끊지 않는다."""

    def scene_email_touched_but_only_name_saved(self):
        user = User.objects.get(pk=self.user.pk)
        user.email = "typo@example.com"
        user.display_name = "새이름"
        user.save(update_fields=["display_name"])
        return user

    def test_이메일을_안_저장하면_안_끊는다(self):
        self.scene_email_touched_but_only_name_saved()
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "member@example.com")
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_이름만_저장한_뒤_이메일을_저장하면_그때_끊는다(self):
        user = self.scene_email_touched_but_only_name_saved()
        user.save(update_fields=["email"])
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "typo@example.com")
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_비밀번호를_바꾸고_이름만_저장하면_안_끊는다(self):
        user = User.objects.get(pk=self.user.pk)
        user.set_password(NEW_PASSWORD)
        user.save(update_fields=["display_name"])
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(PASSWORD))
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_빈_update_fields_는_아무것도_안_한다(self):
        user = User.objects.get(pk=self.user.pk)
        user.email = "typo@example.com"
        user.save(update_fields=[])
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)


class GoogleLookalikeEmailTest(TestCase):
    """구글이 준 주소에 ASCII 밖 글자가 있으면 계정을 만들지도, 로그인시키지도 않는다."""

    def setUp(self):
        cache.clear()
        User.objects.create_user(email="boss@example.com", password=PASSWORD)

    def via_code(self, email):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": "닮은사람", "picture": ""},
        ):
            return self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )

    def via_credential(self, email):
        with mock.patch(
            "apps.accounts.views.verify_google_credential",
            return_value={"email": email, "name": "닮은사람", "picture": ""},
        ):
            return self.client.post(
                GOOGLE_URL,
                {"credential": "tok", "nonce": "n1", **CONSENT},
                content_type="application/json",
            )

    def test_코드_길과_신분_토큰_길_모두_닮은_글자_주소는_400(self):
        for label, email in NON_ASCII_EMAILS.items():
            for path in (self.via_code, self.via_credential):
                with self.subTest(label, path=path.__name__):
                    res = path(email)
                    self.assertEqual(res.status_code, 400)
                    self.assertNotIn("token", res.json())
        self.assertEqual(User.objects.count(), 1)

    def test_대문자_닮은_글자도_400_이고_진짜_주인의_로그인은_그대로다(self):
        self.assertEqual(self.via_code("BO\u017fS@Example.com").status_code, 400)
        login = self.client.post(
            LOGIN_URL,
            {"email": "boss@example.com", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)


# ---- 2차에서 찾은 세 빈틈 -----------------------------------------------------------


def _email_only_selects(queries) -> list[str]:
    """User.save 가 비교하려고 이메일 한 칸만 읽는 쿼리."""
    return [
        q["sql"]
        for q in queries
        if q["sql"].startswith('SELECT "accounts_user"."email" AS "email" FROM "accounts_user"')
    ]


class KelvinSignGoogleTest(TestCase):
    """구글이 켈빈 기호로 시작하는 주소를 주면 소문자가 된 kate@ 계정으로 들어가던 장면."""

    KELVIN = "\u212aate@example.com"

    def setUp(self):
        cache.clear()
        self.kate = User.objects.create_user(email="kate@example.com", password=PASSWORD)

    def google(self, email):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": "닮은사람", "picture": ""},
        ):
            return self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )

    def test_켈빈_기호_주소는_400_이고_남의_계정_토큰이_안_나온다(self):
        res = self.google(self.KELVIN)
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())
        self.assertFalse(LoginToken.objects.filter(user=self.kate).exists())
        self.assertEqual(User.objects.count(), 1)


class PartialRefreshKeepsUnsavedEmailTest(CredentialChangeFlowCase):
    """메모리에서 이메일을 바꾼 뒤 다른 칸의 지연 로드가 일어나도, 저장하면 끊긴다."""

    def scene(self):
        user = User.objects.defer("display_name").get(pk=self.user.pk)
        user.email = "moved@example.com"
        self.assertEqual(user.display_name, "회원")  # refresh_from_db(fields=["display_name"])
        user.save()

    def test_다른_칸을_지연_로드한_뒤_이메일을_저장하면_끊긴다(self):
        self.scene()
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "moved@example.com")
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_직접_다른_칸만_다시_읽어도_끊긴다(self):
        user = User.objects.get(pk=self.user.pk)
        user.email = "moved@example.com"
        user.refresh_from_db(fields=["display_name"])
        user.save()
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())


class DeferredEmailAssignTest(CredentialChangeFlowCase):
    """이메일을 빼고 읽은 행에 이메일을 넣고 저장하는 장면. 비교할 값이 없어 안 끊었다."""

    def test_defer_로_뺀_행에_새_이메일을_넣고_저장하면_끊긴다(self):
        user = User.objects.defer("email").get(pk=self.user.pk)
        user.email = "moved@example.com"
        user.save()
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "moved@example.com")
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_only_로_읽은_행에_새_이메일만_저장해도_끊긴다(self):
        user = User.objects.only("pk").get(pk=self.user.pk)
        user.email = "moved@example.com"
        user.save(update_fields=["email"])
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_같은_이메일이나_대소문자만_다른_이메일을_넣으면_안_끊는다(self):
        for email in ("member@example.com", "MEMBER@Example.com"):
            with self.subTest(email):
                user = User.objects.defer("email").get(pk=self.user.pk)
                user.email = email
                user.save()
                self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 2)

    def test_DB_를_한_번_읽어_비교한다(self):
        """아래 평소 저장 테스트가 쓰는 탐지기가 실제 쿼리 모양을 잡는지 여기서 확인한다."""
        user = User.objects.defer("email").get(pk=self.user.pk)
        user.email = "member@example.com"
        with CaptureQueriesContext(connection) as ctx:
            user.save()
        self.assertEqual(len(_email_only_selects(ctx.captured_queries)), 1)


class OrdinarySaveExtraQueryTest(CredentialChangeFlowCase):
    """이메일을 읽은 행의 평소 저장에서는 비교용 DB 읽기가 돌지 않는다."""

    def test_이름_저장은_UPDATE_한_번이다(self):
        user = User.objects.get(pk=self.user.pk)
        user.display_name = "새이름"
        with self.assertNumQueries(1):
            user.save()

    def test_구글_사진_칸_저장은_UPDATE_한_번이다(self):
        user = User.objects.get(pk=self.user.pk)
        user.google_picture = "https://lh3.googleusercontent.com/a/new"
        with self.assertNumQueries(1):
            user.save(update_fields=["google_picture"])

    def test_인증이_읽은_사진_뺀_행의_이름_저장도_UPDATE_한_번이다(self):
        user, _ = SlimTokenAuthentication().authenticate_credentials(self.phone.key)
        self.assertNotIn("avatar_photo", user.__dict__)  # 정말 사진을 빼고 읽은 행인지
        user.display_name = "새이름"
        with self.assertNumQueries(1):
            user.save()
        self.assertAllAlive(self.phone.key, self.laptop.key)

    def test_API_의_이름_수정과_구글_사진_갱신에서_비교용_읽기가_없다(self):
        self.user.google_picture = "https://lh3.googleusercontent.com/a/old"
        self.user.save(update_fields=["google_picture"])

        with CaptureQueriesContext(connection) as patch_ctx:
            res = self.client.patch(
                ME_URL,
                {"display_name": "새이름"},
                content_type="application/json",
                **auth(self.phone.key),
            )
        self.assertEqual(res.status_code, 200)

        with (
            mock.patch(
                "apps.accounts.views.fetch_google_user",
                return_value={
                    "email": "member@example.com",
                    "name": "회원",
                    "picture": "https://lh3.googleusercontent.com/a/new",
                },
            ),
            CaptureQueriesContext(connection) as google_ctx,
        ):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "c", "redirect_uri": REDIRECT_URI},
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 200)

        self.assertEqual(_email_only_selects(patch_ctx.captured_queries), [])
        self.assertEqual(_email_only_selects(google_ctx.captured_queries), [])
        self.assertAllAlive(self.phone.key, self.laptop.key)
