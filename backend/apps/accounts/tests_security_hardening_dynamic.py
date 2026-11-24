"""보안 보강(이메일 변경 전체 상한, 토큰 30일 만료, Admin 기기 쿠키)을 깨뜨려 보는 테스트.

요청 제한은 테스트 실행 중 넉넉한 값(sys.argv 가 test)이라 그대로는 아무것도 안 막는다.
운영 값을 settings 에서 다시 읽어 THROTTLE_RATES 에 걸고 센다(production_rates).

계약:
  - 이메일 변경 신청: 계정당 시간 5회, 서비스 전체 시간 15회. 계정 제한에 막힌 요청은 전체
    통을 채우지 않는다. 익명은 어느 통도 안 센다. 전체 통이 차면 처음 보내는 계정도 429.
  - 로그인 토큰: 발급하고 정확히 30일은 통과, 30일 1초는 401. 만료 토큰은 어느 API 에서도
    그 사용자로 인정되지 않는다.
  - Admin 로그인 기기 쿠키: 로그인에 성공한 브라우저만 받는다. 유효한 쿠키를 낸 시도는
    기기 통으로 세어, 남이 이메일 통을 채워도 그 브라우저는 들어온다. 다른 이메일의 쿠키,
    서명이 틀리거나 기한이 지난 쿠키는 이메일 통으로 센다. 쿠키를 훔쳐도 그 기기 몫만큼만
    더 대볼 수 있다.
"""

from __future__ import annotations

import functools
import importlib
import sys
import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.test import TestCase
from rest_framework.throttling import SimpleRateThrottle

from .models import LoginToken, token_digest
from .tests import EMAIL_CHANGE_URL, ME_URL, PASSWORD
from .throttles import (
    ADMIN_DEVICE_COOKIE,
    ADMIN_DEVICE_MAX_AGE,
    ADMIN_DEVICE_SALT,
    EmailChangeThrottle,
    EmailChangeTotalThrottle,
    email_ident,
)

User = get_user_model()

ADMIN_LOGIN = "/admin/login/"
WORDS_URL = "/api/vocab/words/"
TOO_MANY = r"^시도가 너무 많습니다\. "


@functools.lru_cache(maxsize=1)
def production_rates() -> dict[str, str]:
    """운영에서 쓰는 요청 제한 값. sys.argv 를 잠시 바꿔 settings 를 다시 읽는다."""
    real_argv = sys.argv
    sys.argv = ["gunicorn"]
    try:
        prod = importlib.reload(importlib.import_module("config.settings"))
        rates = dict(prod.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
    finally:
        sys.argv = real_argv
        importlib.reload(importlib.import_module("config.settings"))
    return rates


def use_production_rates(test: TestCase, *scopes: str) -> None:
    patcher = mock.patch.dict(
        SimpleRateThrottle.THROTTLE_RATES, {s: production_rates()[s] for s in scopes}
    )
    patcher.start()
    test.addCleanup(patcher.stop)


class ProductionValuesTest(TestCase):
    """아래 테스트들이 거는 운영 값이 이번 변경이 말한 값인지."""

    def test_운영_값(self):
        rates = production_rates()
        self.assertEqual(rates["email_change"], "5/hour")
        self.assertEqual(rates["email_change_total"], "15/hour")
        self.assertEqual(rates["admin_login"], "10/hour")
        self.assertEqual(rates["practice_grade"], "120/min")


# ---- 이메일 변경 신청 --------------------------------------------------------


class EmailChangeTotalLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        use_production_rates(self, "email_change", "email_change_total")
        mailer = mock.patch("apps.accounts.views.send_account_mail")
        self.sent = mailer.start()
        self.addCleanup(mailer.stop)

    def account(self, n: int) -> str:
        user = User.objects.create_user(email=f"u{n}@example.com", password=PASSWORD)
        return LoginToken.objects.create(user=user).key

    def ask(self, key: str | None, n: int = 0, *, password: str = PASSWORD):
        headers = {"HTTP_AUTHORIZATION": f"Token {key}"} if key else {}
        return self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": f"new{n}@example.com", "current_password": password},
            content_type="application/json",
            **headers,
        )

    def total_count(self) -> int:
        key = EmailChangeTotalThrottle.cache_format % {
            "scope": EmailChangeTotalThrottle.scope,
            "ident": "all",
        }
        return len(cache.get(key, []))

    def account_count(self, key: str) -> int:
        user_pk = LoginToken.objects.get(digest=token_digest(key)).user_id
        cache_key = EmailChangeThrottle.cache_format % {
            "scope": EmailChangeThrottle.scope,
            "ident": f"u{user_pk}",
        }
        return len(cache.get(cache_key, []))

    def test_계정당_다섯_번째까지_되고_여섯_번째는_429(self):
        key = self.account(1)
        codes = [self.ask(key, i).status_code for i in range(6)]
        self.assertEqual(codes, [202] * 5 + [429])
        self.assertEqual(self.sent.call_count, 5)

    def test_계정_제한에_막힌_요청은_전체_통을_안_채운다(self):
        """막힌 채 계속 보내기만 해도 전체 통이 차면, 한 계정이 모두의 이메일 변경을 막는다."""
        key = self.account(1)
        for i in range(20):
            self.ask(key, i)
        self.assertEqual(self.total_count(), 5)

        # 다른 계정은 그대로 된다.
        self.assertEqual(self.ask(self.account(2), 99).status_code, 202)

    def test_틀린_비밀번호도_두_통을_센다(self):
        """제한이 입력 검사보다 먼저 돈다. 메일이 안 나간 신청도 센다(settings 주석의 판단)."""
        key = self.account(1)
        codes = [self.ask(key, i, password="nope").status_code for i in range(6)]
        self.assertEqual(codes, [400] * 5 + [429])
        self.assertEqual(self.total_count(), 5)
        self.sent.assert_not_called()

    def test_전체_통이_차면_처음_보내는_계정도_429(self):
        for n in range(3):
            key = self.account(n)
            for i in range(5):
                self.assertEqual(self.ask(key, n * 10 + i).status_code, 202)
        self.assertEqual(self.total_count(), 15)
        self.assertEqual(self.sent.call_count, 15)

        newcomer = self.account(9)
        res = self.ask(newcomer, 90)
        self.assertEqual(res.status_code, 429)
        self.assertRegex(res.json()["detail"], TOO_MANY)
        self.assertIn("Retry-After", res.headers)
        self.assertEqual(self.sent.call_count, 15, "막힌 신청이 메일을 보냈다")
        # 알려진 대가(FirstThrottleWins 머리말): 계정 통은 이미 한 번 썼다.
        self.assertEqual(self.account_count(newcomer), 1)

    def test_익명은_어느_통도_안_센다(self):
        for i in range(30):
            self.assertEqual(self.ask(None, i).status_code, 401)
        self.assertEqual(self.total_count(), 0)
        self.assertEqual(self.ask(self.account(1)).status_code, 202)

    def test_만료_토큰은_익명처럼_401_이고_통을_안_센다(self):
        key = self.account(1)
        LoginToken.objects.filter(digest=token_digest(key)).update(created=self.long_ago())
        for i in range(10):
            self.assertEqual(self.ask(key, i).status_code, 401)
        self.assertEqual(self.total_count(), 0)

    @staticmethod
    def long_ago():
        from django.utils import timezone

        return timezone.now() - LoginToken.LIFETIME - timedelta(seconds=1)


# ---- 로그인 토큰 30일 만료 ---------------------------------------------------


class LoginTokenExpiryBoundaryTest(TestCase):
    """시계를 한 순간에 멈춰 경계를 잰다. 안 멈추면 '정확히 30일' 이 요청 사이에 지나간다."""

    NOW = datetime(2026, 11, 23, 3, 0, 0, tzinfo=dt_timezone.utc)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="t@example.com", password=PASSWORD)
        clock = mock.patch("django.utils.timezone.now", return_value=self.NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def token_aged(self, age: timedelta) -> str:
        return LoginToken.objects.create(user=self.user, created=self.NOW - age).key

    def me(self, key: str) -> int:
        return self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {key}").status_code

    def test_정확히_30일은_통과(self):
        self.assertEqual(self.me(self.token_aged(LoginToken.LIFETIME)), 200)

    def test_30일_1초는_401(self):
        key = self.token_aged(LoginToken.LIFETIME + timedelta(seconds=1))
        self.assertEqual(self.me(key), 401)
        self.assertTrue(LoginToken.objects.filter(digest=token_digest(key)).exists(), "지우는 것은 매일 정리 몫이다")

    def test_30일_1마이크로초도_401(self):
        self.assertEqual(self.me(self.token_aged(LoginToken.LIFETIME + timedelta(microseconds=1))), 401)

    def test_만료_판단이_매일_정리와_같다(self):
        """인증이 거절하는 토큰과 정리가 지우는 토큰이 다르면, 둘 사이에 낀 토큰이 생긴다."""
        ages = [timedelta(days=29), LoginToken.LIFETIME, LoginToken.LIFETIME + timedelta(seconds=1)]
        for age in ages:
            self.token_aged(age)
        by_method = {t.digest for t in LoginToken.objects.all() if t.is_expired()}
        by_query = set(LoginToken.expired().values_list("digest", flat=True))
        self.assertEqual(by_method, by_query)
        self.assertEqual(len(by_query), 1)

    def test_미래_시각_토큰은_통과(self):
        """시계가 뒤로 간 서버에서 만든 토큰. 만료로 치면 그 사이 로그인한 사람이 끊긴다."""
        self.assertEqual(self.me(self.token_aged(-timedelta(hours=1))), 200)


class ExpiredTokenEverywhereTest(TestCase):
    """만료 토큰은 /me 만이 아니라 어느 API 에서도 그 사용자로 인정되지 않는다."""

    def setUp(self):
        cache.clear()
        from django.utils import timezone

        self.user = User.objects.create_user(email="old@example.com", password=PASSWORD)
        self.key = LoginToken.objects.create(
            user=self.user, created=timezone.now() - LoginToken.LIFETIME - timedelta(minutes=1)
        ).key
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.key}"}

    def test_공개_목록도_게스트로_넘기지_않고_401(self):
        """프론트(withTokenOrGuest)는 401 을 받으면 쿠키를 버리고 게스트로 다시 부른다."""
        self.assertEqual(self.client.get(WORDS_URL, **self.auth).status_code, 401)

    def test_쓰는_API_도_401_이고_아무것도_안_바뀐다(self):
        before = User.objects.get(pk=self.user.pk)
        res = self.client.patch(
            ME_URL, {"display_name": "바뀜"}, content_type="application/json", **self.auth
        )
        self.assertEqual(res.status_code, 401)
        after = User.objects.get(pk=self.user.pk)
        self.assertEqual(after.display_name, before.display_name)

    def test_로그아웃도_401(self):
        res = self.client.post("/api/accounts/logout/", **self.auth)
        self.assertEqual(res.status_code, 401)

    def test_가드를_끄면_통과한다(self):
        """방어가 실제로 이 테스트를 지키는지. is_expired 를 끄면 200 이 나와야 한다."""
        with mock.patch.object(LoginToken, "is_expired", return_value=False):
            self.assertEqual(self.client.get(ME_URL, **self.auth).status_code, 200)


# ---- Admin 로그인 기기 쿠키 --------------------------------------------------


def sign_cookie(raw: str, *, at: float | None = None) -> str:
    """서버와 같은 방식(set_signed_cookie)으로 서명한 쿠키 값. at 을 주면 그 시각에 서명한다."""
    response = HttpResponse()
    with mock.patch("django.core.signing.time.time", return_value=at or time.time()):
        response.set_signed_cookie(ADMIN_DEVICE_COOKIE, raw, salt=ADMIN_DEVICE_SALT)
    return response.cookies[ADMIN_DEVICE_COOKIE].value


def read_cookie(value: str) -> str | None:
    """서버가 읽는 방식(get_signed_cookie)으로 푼 값. 틀리면 None."""
    request = HttpRequest()
    request.COOKIES[ADMIN_DEVICE_COOKIE] = value
    return request.get_signed_cookie(ADMIN_DEVICE_COOKIE, default=None, salt=ADMIN_DEVICE_SALT)


def device_cookie_value(email: str, device: str = "d" * 32, *, at: float | None = None) -> str:
    """서버가 내는 것과 같은 꼴의 쿠키 값."""
    return sign_cookie(f"{email_ident(email)}:{device}", at=at)


class AdminDeviceCookieCase(TestCase):
    BOSS = "boss@example.com"

    def setUp(self):
        cache.clear()
        use_production_rates(self, "admin_login")
        self.boss = User.objects.create_superuser(email=self.BOSS, password=PASSWORD)

    def post(self, client, email: str, password: str = "wrong"):
        return client.post(ADMIN_LOGIN, {"username": email, "password": password})

    def fill_email_bucket(self, email: str | None = None) -> None:
        """쿠키 없는 공격자가 그 이메일 통을 다 채운다."""
        attacker = self.client_class()
        codes = [self.post(attacker, email or self.BOSS).status_code for _ in range(11)]
        # 앞서 쿠키 없이 한 로그인도 이메일 통에 들어 있어 200 이 열 번보다 적을 수 있다.
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(302, codes)

    def logged_in_browser(self, email: str | None = None):
        """한 번 로그인에 성공해 기기 쿠키를 받은 브라우저. 세션은 끊어 둔다."""
        browser = self.client_class()
        res = self.post(browser, email or self.BOSS, PASSWORD)
        self.assertEqual(res.status_code, 302)
        self.assertIn(ADMIN_DEVICE_COOKIE, res.cookies)
        self.drop_session(browser)
        return browser

    @staticmethod
    def drop_session(browser) -> None:
        """세션 쿠키만 버린다. client.logout() 은 쿠키를 모두 지워 기기 쿠키까지 사라진다."""
        browser.cookies.pop(settings.SESSION_COOKIE_NAME, None)

    def browser_with(self, value: str):
        browser = self.client_class()
        browser.cookies[ADMIN_DEVICE_COOKIE] = value
        return browser


class AdminDeviceCookieIssueTest(AdminDeviceCookieCase):
    def test_성공하면_쿠키를_속성과_함께_준다(self):
        res = self.post(self.client, self.BOSS, PASSWORD)

        self.assertEqual(res.status_code, 302)
        morsel = res.cookies[ADMIN_DEVICE_COOKIE]
        self.assertEqual(morsel["path"], "/admin/")
        self.assertTrue(morsel["httponly"])
        self.assertEqual(morsel["samesite"], "Strict")
        self.assertEqual(int(morsel["max-age"]), ADMIN_DEVICE_MAX_AGE)
        self.assertEqual(ADMIN_DEVICE_MAX_AGE, 180 * 24 * 60 * 60)
        # 서명돼 있고, 원문에 이메일이 없다.
        self.assertNotIn("boss", morsel.value)
        owner, _, device = read_cookie(morsel.value).partition(":")
        self.assertEqual(owner, email_ident(self.BOSS))
        self.assertEqual(len(device), 32)

    def test_로그인할_때마다_다른_기기_값(self):
        a = self.post(self.client_class(), self.BOSS, PASSWORD).cookies[ADMIN_DEVICE_COOKIE].value
        b = self.post(self.client_class(), self.BOSS, PASSWORD).cookies[ADMIN_DEVICE_COOKIE].value
        self.assertNotEqual(a, b)

    def test_틀린_비밀번호와_화면_보기는_쿠키를_안_준다(self):
        self.assertNotIn(ADMIN_DEVICE_COOKIE, self.post(self.client, self.BOSS).cookies)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, self.client.get(ADMIN_LOGIN).cookies)

    def test_직원이_아닌_회원은_맞는_비밀번호여도_쿠키가_없다(self):
        User.objects.create_user(email="member@example.com", password=PASSWORD)
        res = self.post(self.client, "member@example.com", PASSWORD)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, res.cookies)

    def test_이미_로그인한_채_틀린_비밀번호는_재발급_없음(self):
        self.client.force_login(self.boss)
        res = self.post(self.client, self.BOSS)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, res.cookies)

    def test_직원으로_로그인한_채_회원_비밀번호를_내도_쿠키가_없다(self):
        """request.user 가 앞서 로그인한 직원이라 is_staff 검사를 지나가는지 본다."""
        User.objects.create_user(email="member@example.com", password=PASSWORD)
        self.client.force_login(self.boss)
        res = self.post(self.client, "member@example.com", PASSWORD)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, res.cookies)

    def test_GET_으로_로그인된_화면을_열어도_쿠키가_없다(self):
        """이미 로그인한 직원이 로그인 주소를 열면 302 다. POST 가 아니니 주지 않는다."""
        self.client.force_login(self.boss)
        res = self.client.get(ADMIN_LOGIN)
        self.assertEqual(res.status_code, 302)
        self.assertNotIn(ADMIN_DEVICE_COOKIE, res.cookies)


class AdminDeviceCookieThrottleTest(AdminDeviceCookieCase):
    def test_이메일_통이_차도_쿠키_있는_브라우저는_들어오고_없는_브라우저는_429(self):
        browser = self.logged_in_browser()
        self.fill_email_bucket()

        res = self.post(browser, self.BOSS, PASSWORD)
        self.assertEqual(res.status_code, 302)
        self.assertIn("_auth_user_id", browser.session)

        stranger = self.client_class()
        blocked = self.post(stranger, self.BOSS, PASSWORD)
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        self.assertNotIn("_auth_user_id", stranger.session)

    def test_쿠키를_훔쳐도_기기_몫_열_번까지만_더_대볼_수_있다(self):
        browser = self.logged_in_browser()
        for _ in range(10):
            self.assertEqual(self.post(browser, self.BOSS).status_code, 200)
        blocked = self.post(browser, self.BOSS, PASSWORD)
        self.assertEqual(blocked.status_code, 429)
        self.assertNotIn("_auth_user_id", browser.session)

        # 기기 통의 시도는 이메일 통에 안 들어갔다. 처음 쓰는 브라우저는 열 번이 남아 있다.
        self.assertEqual(self.post(self.client_class(), self.BOSS, PASSWORD).status_code, 302)

    def test_쿠키_사본_여럿은_한_기기_통을_나눠_쓴다(self):
        """같은 쿠키를 여러 브라우저에 복사해도 몫이 늘지 않는다."""
        value = self.logged_in_browser().cookies[ADMIN_DEVICE_COOKIE].value
        copies = [self.browser_with(value) for _ in range(5)]
        for i in range(10):
            self.assertEqual(self.post(copies[i % 5], self.BOSS).status_code, 200)
        self.assertEqual(self.post(copies[0], self.BOSS, PASSWORD).status_code, 429)

    def test_전각_ſ_대문자_표기도_같은_기기로_친다(self):
        browser = self.logged_in_browser()
        self.fill_email_bucket()
        for email in ("ｂoss@example.com", "boſs@example.com", " BOSS@EXAMPLE.COM "):
            with self.subTest(email=email):
                self.drop_session(browser)
                self.assertEqual(self.post(browser, email, PASSWORD).status_code, 302)

    def test_표기를_바꿔_보낸_시도도_같은_기기_통이다(self):
        """표기마다 기기 통이 따로면 쿠키 하나로 열 번 넘게 대볼 수 있다."""
        browser = self.logged_in_browser()
        variants = ("boss@example.com", "ｂoss@example.com", "boſs@example.com", "BOSS@example.com")
        for i in range(10):
            self.assertEqual(self.post(browser, variants[i % 4]).status_code, 200)
        self.assertEqual(self.post(browser, "ｂoss@example.com", PASSWORD).status_code, 429)

    def test_다른_이메일의_쿠키는_이메일_통으로_센다(self):
        User.objects.create_superuser(email="other@example.com", password=PASSWORD)
        browser = self.logged_in_browser("other@example.com")
        self.fill_email_bucket()
        self.assertEqual(self.post(browser, self.BOSS, PASSWORD).status_code, 429)

    def test_위조_쿠키는_이메일_통으로_센다(self):
        self.fill_email_bucket()
        valid = device_cookie_value(self.BOSS)
        # 서명 끝 글자를 늘 다른 글자로 바꾼다. 서명에 시각이 들어가 실행마다 바뀌고 끝 글자는
        # 16가지 중 하나라, 고정 글자("A")로 바꾸면 16번에 한 번은 진짜 쿠키가 된다.
        tampered = valid[:-1] + ("B" if valid[-1] != "B" else "C")
        forged = [
            f"{email_ident(self.BOSS)}:{'d' * 32}",  # 서명 없음
            tampered,  # 서명 끝 한 글자 바꿈
            valid.replace("d" * 32, "e" * 32),  # 기기 값 바꿈
            signing.get_cookie_signer(salt="다른-salt").sign(f"{email_ident(self.BOSS)}:x"),
            valid.split(":")[0] + "::",
            "",
        ]
        # 앞 40자는 이메일 키라 모두 같다. 실패한 항목을 가리려면 번호와 끝을 본다.
        for i, value in enumerate(forged):
            with self.subTest(i=i, tail=value[-12:]):
                self.assertEqual(self.post(self.browser_with(value), self.BOSS, PASSWORD).status_code, 429)

    def test_기기_값이_빈_쿠키는_이메일_통으로_센다(self):
        """서명은 맞아도 기기 칸이 비면 모두가 한 기기 통을 나눠 쓰게 된다."""
        self.fill_email_bucket()
        for raw in (f"{email_ident(self.BOSS)}:", email_ident(self.BOSS)):
            with self.subTest(raw=raw[-5:]):
                browser = self.browser_with(sign_cookie(raw))
                self.assertEqual(self.post(browser, self.BOSS, PASSWORD).status_code, 429)

    def test_180일이_지난_쿠키는_이메일_통으로_센다(self):
        self.fill_email_bucket()
        now = time.time()
        stale = device_cookie_value(self.BOSS, at=now - ADMIN_DEVICE_MAX_AGE - 60)
        fresh = device_cookie_value(self.BOSS, at=now - ADMIN_DEVICE_MAX_AGE + 60)
        self.assertEqual(self.post(self.browser_with(stale), self.BOSS, PASSWORD).status_code, 429)
        self.assertEqual(self.post(self.browser_with(fresh), self.BOSS, PASSWORD).status_code, 302)

    def test_쿠키_있는_브라우저도_다른_계정은_그_이메일_통으로_센다(self):
        """boss 쿠키로 다른 관리자 이메일을 두드리면 그 이메일 통이 찬다."""
        User.objects.create_superuser(email="other@example.com", password=PASSWORD)
        browser = self.logged_in_browser()
        for _ in range(10):
            self.post(browser, "other@example.com")
        self.assertEqual(self.post(self.client_class(), "other@example.com", PASSWORD).status_code, 429)
