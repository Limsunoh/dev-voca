"""처리방침 v3 시행일(2026-11-19)까지 꺼 두던 날짜 문을 지운 뒤의 동작.

운영 로그 "[서버 오류]" 줄의 오류 메시지(error_mail.short_message)와 가입·로그인·구글
로그인의 접속 IP 세기(throttles._ClientIpThrottle)는 이제 날짜와 상관없이 늘 켜져 있다.
여기서는 서버 시각을 시행일 전날 한국 시간 23:59:59, 먼 과거, 먼 미래로 돌리고
서버 시각대(TIME_ZONE)를 바꿔도 둘 다 꺼지지 않는지 본다. 누가 지운 문과 같은
방식(timezone.localdate·timezone.now)으로 날짜 비교를 다시 넣으면 시행일 전날 칸에서
빨개진다. date.today()·datetime.now() 처럼 실제 시계를 읽으면 잡지 못한다.

시각은 django.utils.timezone.now 를 바꿔 돌린다. 지운 문은 timezone.localdate() 로
날짜를 셌고, 그것이 timezone.now 를 부른다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils.crypto import salted_hmac

from . import throttles
from .error_mail import short_message
from .tests_error_mail_dynamic import PRODUCTION_LIKE, _ErrorMailCase, _StderrCapture
from .tests_ip_throttle import CONSENT, RELAY_MARK, SIGNUP_URL, mark, relayed
from .throttles import GoogleIpThrottle, LoginIpThrottle, SignUpIpThrottle

# 시행일 전날 한국 시간 23:59:59. 지운 문이 있었다면 메시지도 IP 세기도 꺼졌을 마지막 순간이다.
EVE_KST = datetime(2026, 11, 18, 14, 59, 59, tzinfo=UTC)
INSTANTS = {
    "시행일 전날 KST 23:59:59": EVE_KST,
    "시행일 전날 UTC 0시": datetime(2026, 11, 18, 0, 0, tzinfo=UTC),
    "먼 과거": datetime(2000, 1, 1, tzinfo=UTC),
    "먼 미래": datetime(2999, 6, 1, tzinfo=UTC),
}
ZONES = ("Asia/Seoul", "UTC", "America/Los_Angeles", "Pacific/Kiritimati", "Etc/GMT+12")

# 숫자를 넣어 주소 조각으로는 가려지게(:id) 한다. 영어 소문자만이면 주소에 그대로 남는다.
MESSAGE_MARK = mark("clock7")


def at(instant: datetime):
    """서버 시각을 instant 로 돌린다."""
    return mock.patch("django.utils.timezone.now", return_value=instant)


def every_clock():
    """(설명, 시각, 시각대) 를 모두 돈다."""
    for label, instant in INSTANTS.items():
        for zone in ZONES:
            yield label, instant, zone


def record_of(exc: Exception) -> mock.Mock:
    return mock.Mock(exc_info=(type(exc), exc, None))


class ShortMessageIgnoresClockTest(SimpleTestCase):
    """운영 로그에 싣는 메시지는 서버 시각과 시각대에 따라 꺼지지 않는다."""

    def test_message_is_kept_at_every_clock_and_zone(self):
        for label, instant, zone in every_clock():
            with (
                self.subTest(when=label, zone=zone),
                override_settings(TIME_ZONE=zone),
                at(instant),
            ):
                self.assertEqual(short_message(record_of(RuntimeError(MESSAGE_MARK))), MESSAGE_MARK)

    def test_folding_and_limit_still_apply_on_the_eve(self):
        """문만 지웠고 한 줄로 펴기와 300자 자르기는 그대로다."""
        with at(EVE_KST):
            self.assertEqual(
                short_message(record_of(RuntimeError("가\n[서버 오류] 가짜"))),
                "가 [서버 오류] 가짜",
            )
            self.assertEqual(len(short_message(record_of(RuntimeError("x" * 5000)))), 300)
            self.assertEqual(short_message(record_of(RuntimeError(""))), "")


@override_settings(**PRODUCTION_LIKE)
class ServerErrorLineIgnoresClockTest(_StderrCapture, _ErrorMailCase):
    """실제 500 을 거쳐도 시행일 전 시각에 "[서버 오류]" 줄 끝 메시지가 붙고, 메일에는 없다."""

    def test_eve_and_far_past_still_log_the_message(self):
        for label in ("시행일 전날 KST 23:59:59", "먼 과거"):
            for zone in ("Asia/Seoul", "Etc/GMT+12"):
                with self.subTest(when=label, zone=zone):
                    mail.outbox.clear()
                    self.setUp()
                    with override_settings(TIME_ZONE=zone), at(INSTANTS[label]):
                        log = self.run_and_capture(
                            lambda: self.assertEqual(
                                self.client.get(f"/boom-echo/{MESSAGE_MARK}/").status_code, 500
                            )
                        )
                    line = next(x for x in log.splitlines() if x.startswith("[서버 오류]"))
                    self.assertEqual(
                        line, f"[서버 오류] RuntimeError GET /boom-echo/:id/ - {MESSAGE_MARK}"
                    )
                    self.assertEqual(len(mail.outbox), 1)
                    self.assertNotIn(MESSAGE_MARK, self.mail_text())


@override_settings(RELAY_SECRET=RELAY_MARK)
class IpKeyIgnoresClockTest(SimpleTestCase):
    """세 제한 모두, 시각과 시각대가 어떻든 같은 캐시 키를 만든다."""

    THROTTLES = (SignUpIpThrottle, LoginIpThrottle, GoogleIpThrottle)

    def setUp(self):
        throttles._WARNED.clear()
        self.addCleanup(throttles._WARNED.clear)

    def key(self, throttle, **meta) -> str | None:
        return throttle().get_cache_key(RequestFactory().post("/", **meta), view=None)

    def test_relayed_direct_and_missing_ip_at_every_clock(self):
        hashed = salted_hmac("accounts.throttles.ip", "2001:db8:1:2::/64", algorithm="sha256")
        for throttle in self.THROTTLES:
            for label, instant, zone in every_clock():
                with (
                    self.subTest(throttle=throttle.__name__, when=label, zone=zone),
                    override_settings(TIME_ZONE=zone),
                    at(instant),
                ):
                    self.assertEqual(
                        self.key(throttle, **relayed("2001:db8:1:2::9")),
                        f"throttle_{throttle.scope}_{hashed.hexdigest()}",
                    )
                    self.assertEqual(
                        self.key(throttle, HTTP_X_NEXT_CLIENT_IP="2001:db8:1:2::9"),
                        f"throttle_{throttle.scope}_direct",
                    )
                    self.assertIsNone(self.key(throttle, HTTP_X_NEXT_RELAY=RELAY_MARK))
                    self.assertIsNone(self.key(throttle, **relayed("not-an-ip")))

    def test_wrong_secret_warns_and_is_still_counted_on_the_eve(self):
        """지운 문은 비밀값 확인 뒤에 있어, 시행 전에는 경고만 나고 세지 않았다. 이제 둘 다 한다."""
        wrong = mark("eve-drift")
        with at(EVE_KST), self.assertLogs("apps.accounts.throttles", level="WARNING") as logs:
            key = self.key(SignUpIpThrottle, **relayed("203.0.113.7", secret=wrong))
        self.assertEqual(key, "throttle_signup_ip_direct")
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn(wrong, logs.output[0])

    def test_correct_secret_or_no_header_does_not_warn(self):
        with at(EVE_KST), self.assertNoLogs("apps.accounts.throttles", level="WARNING"):
            self.key(SignUpIpThrottle, **relayed("203.0.113.7"))
            self.key(SignUpIpThrottle, HTTP_X_NEXT_RELAY=RELAY_MARK)
            self.key(SignUpIpThrottle)


@override_settings(RELAY_SECRET=RELAY_MARK)
class SignUpBlockedOnTheEveTest(TestCase):
    """시각을 시행일 전날로 돌려도 실제 가입 요청이 IP 마다 막힌다."""

    def setUp(self):
        cache.clear()
        throttles._WARNED.clear()
        self.addCleanup(throttles._WARNED.clear)
        patcher = mock.patch.object(SignUpIpThrottle, "get_rate", return_value="2/min")
        patcher.start()
        self.addCleanup(patcher.stop)
        clock = at(EVE_KST)
        clock.start()
        self.addCleanup(clock.stop)

    def signup(self, n: int, **meta):
        payload = {"email": f"eve{n}@example.com", "password": mark("eve-pass"), **CONSENT}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json", **meta)

    def test_relayed_ip_is_counted(self):
        self.assertEqual(self.signup(1, **relayed("203.0.113.7")).status_code, 201)
        self.assertEqual(self.signup(2, **relayed("203.0.113.7")).status_code, 201)
        self.assertEqual(self.signup(3, **relayed("203.0.113.7")).status_code, 429)
        self.assertEqual(self.signup(4, **relayed("203.0.113.8")).status_code, 201)

    def test_wrong_secret_warns_and_fills_the_direct_bucket(self):
        wrong = mark("eve-guess")
        with self.assertLogs("apps.accounts.throttles", level="WARNING") as logs:
            codes = [
                self.signup(n, **relayed(f"198.51.100.{n}", secret=wrong)).status_code
                for n in (1, 2, 3)
            ]
        self.assertEqual(codes, [201, 201, 429])
        # 같은 지문은 한 번만 찍는다.
        self.assertEqual(len(logs.output), 1)
        # direct 통이 찼어도 Next 를 거친 사람은 막히지 않는다.
        self.assertEqual(self.signup(4, **relayed("203.0.113.7")).status_code, 201)
