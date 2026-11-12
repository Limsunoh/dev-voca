"""가입·로그인을 접속 IP 로 세는 제한(throttles.SignUpIpThrottle, LoginIpThrottle).

처리방침 v3 시행일(IP_COUNT_FROM) 전에는 아무것도 세지 않는다. 시행일부터 Next 서버가
비밀값과 함께 넘긴 IP(IPv6 는 /64)마다 세고, 비밀값이 없거나 틀린 요청(백엔드를 바로
부른 것)은 IP 를 보지 않고 한 통으로 센다.

비율은 테스트에서 2/min 으로 좁힌다. override_settings 로는 안 되고 get_rate 를 바꾼다
(DRF 가 스로틀을 만들 때 설정을 한 번 읽고 굳힌다, tests.py 의 EmailRateThrottle 테스트).
"""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils.crypto import salted_hmac

from . import throttles
from .error_mail import MESSAGE_FROM
from .throttles import (
    IP_COUNT_FROM,
    LoginIpThrottle,
    SignUpIpThrottle,
    came_through_next,
    client_ip_bucket,
)

SIGNUP_URL = "/api/accounts/signup/"
LOGIN_URL = "/api/accounts/login/"
CONSENT = {"terms_agreed": True, "disclosure_agreed": True, "age_confirmed": True}


def mark(what: str) -> str:
    """비밀값 대신 넣는 표시 글자. 비밀값처럼 생긴 글자를 이름(password, secret 등) 옆에
    적으면 GitGuardian 이 진짜 자격증명으로 잡는다(#169, #170). 값을 여기서 만든다.
    """
    return f"leakmark-{what}"


RELAY_MARK = mark("relay")
LOGIN_MARK = mark("ip-login")


def relayed(ip: str, secret: str = RELAY_MARK) -> dict[str, str]:
    """Next 서버(frontend/src/lib/client-ip.ts)가 싣는 머리."""
    return {"HTTP_X_NEXT_RELAY": secret, "HTTP_X_NEXT_CLIENT_IP": ip}


class PolicyDateTest(SimpleTestCase):
    def test_ip_counting_starts_with_privacy_v3(self):
        """처리방침 v3 시행일(오류 메시지 기록과 같은 날)보다 먼저 세면 안 된다.

        프론트 쪽 날짜(client-ip.ts 의 IP_FROM)와 처리방침의 시행일 대조는
        client-ip.test.mts 가 본다.
        """
        self.assertEqual(IP_COUNT_FROM, MESSAGE_FROM)


@override_settings(RELAY_SECRET=RELAY_MARK)
class CameThroughNextTest(TestCase):
    def came(self, **meta) -> bool:
        return came_through_next(RequestFactory().post("/", **meta))

    def test_only_matching_secret_is_trusted(self):
        self.assertTrue(self.came(**relayed("203.0.113.7")))
        self.assertFalse(self.came(**relayed("203.0.113.7", secret=mark("wrong"))))
        self.assertFalse(self.came(HTTP_X_NEXT_CLIENT_IP="203.0.113.7"))

    @override_settings(RELAY_SECRET="")
    def test_no_secret_configured_trusts_nothing(self):
        # 백엔드에 비밀값이 없으면 빈 비밀값을 실은 요청도 믿으면 안 된다.
        self.assertFalse(self.came(**relayed("203.0.113.7", secret="")))
        self.assertFalse(self.came(**relayed("203.0.113.7")))

    def setUp(self):
        throttles._WARNED.clear()
        self.addCleanup(throttles._WARNED.clear)

    def test_same_wrong_value_warns_once_and_many_values_stop_at_limit(self):
        """봇이 머리만 지어 보내 로그를 채우지 못한다."""
        with self.assertLogs("apps.accounts.throttles", level="WARNING") as logs:
            for _ in range(5):
                self.came(**relayed("203.0.113.7", secret=mark("same")))
            for n in range(throttles._WARNED_LIMIT + 20):
                self.came(**relayed("203.0.113.7", secret=mark(f"bot{n}")))
        self.assertEqual(len(logs.output), throttles._WARNED_LIMIT)

    def test_wrong_secret_leaves_a_warning_without_the_value(self):
        """값이 어긋나면 실제 사용자 전원이 한 통에 든다. 그 원인을 알 길이 이 줄이다."""
        wrong = mark("wrong")
        with self.assertLogs("apps.accounts.throttles", level="WARNING") as logs:
            self.came(**relayed("203.0.113.7", secret=wrong))
        text = "\n".join(logs.output)
        self.assertIn("RELAY_SECRET", text)
        self.assertNotIn(wrong, text)
        self.assertNotIn(RELAY_MARK, text)

    def test_no_header_is_not_a_warning(self):
        """머리 없이 바로 부른 요청은 흔하다(봇, 시험). 로그를 채우지 않는다."""
        with self.assertNoLogs("apps.accounts.throttles", level="WARNING"):
            self.assertFalse(self.came())


class ClientIpBucketTest(SimpleTestCase):
    def bucket(self, raw: str) -> str | None:
        return client_ip_bucket(RequestFactory().post("/", HTTP_X_NEXT_CLIENT_IP=raw))

    def test_ipv4_as_is(self):
        self.assertEqual(self.bucket(" 203.0.113.7 "), "203.0.113.7")

    def test_ipv6_is_grouped_by_64(self):
        """한 /64 안에서 주소를 바꿔 가며 통을 늘릴 수 없다."""
        self.assertEqual(self.bucket("2001:db8:1:2::1"), "2001:db8:1:2::/64")
        self.assertEqual(self.bucket("2001:DB8:1:2:ffff::9"), "2001:db8:1:2::/64")
        self.assertNotEqual(self.bucket("2001:db8:1:3::1"), self.bucket("2001:db8:1:2::1"))

    def test_ipv4_mapped_and_zone_spellings_are_the_same_address(self):
        self.assertEqual(self.bucket("::ffff:203.0.113.7"), "203.0.113.7")
        self.assertEqual(self.bucket("2001:db8::1%eth0"), self.bucket("2001:db8::1"))
        # 뒤 64비트가 0 이면 네트워크로 바꿔도 존이 남는다. 존 이름만 바꿔 통을 늘리면 안 된다.
        self.assertEqual(self.bucket("2001:db8::%eth0"), "2001:db8::/64")
        self.assertEqual(self.bucket("2001:db8::%wlan0"), "2001:db8::/64")

    def test_not_an_ip_is_none(self):
        for raw in ("", "  ", "203.0.113.7, 10.0.0.1", "localhost", "999.1.1.1"):
            with self.subTest(raw=raw):
                self.assertIsNone(self.bucket(raw))


class _IpThrottleCase(TestCase):
    throttle = SignUpIpThrottle

    def setUp(self):
        cache.clear()
        patcher = mock.patch.object(self.throttle, "get_rate", return_value="2/min")
        patcher.start()
        self.addCleanup(patcher.stop)

    def counting_from(self, day: date) -> None:
        patcher = mock.patch.object(throttles, "IP_COUNT_FROM", day)
        patcher.start()
        self.addCleanup(patcher.stop)


@override_settings(RELAY_SECRET=RELAY_MARK)
class SignUpIpThrottleTest(_IpThrottleCase):
    throttle = SignUpIpThrottle

    def signup(self, n: int, **meta):
        payload = {"email": f"ip{n}@example.com", "password": mark("signup-pass"), **CONSENT}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json", **meta)

    def test_direct_requests_share_one_bucket_whatever_ip_they_claim(self):
        """백엔드를 바로 부른 봇은 IP 를 지어 보내도 한 통에 든다."""
        self.counting_from(date.min)
        self.assertEqual(self.signup(1, HTTP_X_NEXT_CLIENT_IP="198.51.100.1").status_code, 201)
        self.assertEqual(self.signup(2, HTTP_X_NEXT_CLIENT_IP="198.51.100.2").status_code, 201)
        self.assertEqual(self.signup(3, HTTP_X_NEXT_CLIENT_IP="198.51.100.3").status_code, 429)

    def test_wrong_secret_counts_as_direct(self):
        self.counting_from(date.min)
        wrong = mark("guess")
        self.assertEqual(self.signup(1, **relayed("198.51.100.1", secret=wrong)).status_code, 201)
        self.assertEqual(self.signup(2, **relayed("198.51.100.2", secret=wrong)).status_code, 201)
        self.assertEqual(self.signup(3, **relayed("198.51.100.3", secret=wrong)).status_code, 429)

    def test_relayed_requests_are_counted_per_ip(self):
        """한 IP 가 막혀도 다른 IP 의 사람은 가입할 수 있다."""
        self.counting_from(date.min)
        self.assertEqual(self.signup(1, **relayed("203.0.113.7")).status_code, 201)
        self.assertEqual(self.signup(2, **relayed("203.0.113.7")).status_code, 201)
        self.assertEqual(self.signup(3, **relayed("203.0.113.7")).status_code, 429)
        self.assertEqual(self.signup(4, **relayed("203.0.113.8")).status_code, 201)

    def test_ipv6_addresses_in_one_64_share_a_bucket(self):
        self.counting_from(date.min)
        self.assertEqual(self.signup(1, **relayed("2001:db8:1:2::1")).status_code, 201)
        self.assertEqual(self.signup(2, **relayed("2001:db8:1:2::2")).status_code, 201)
        self.assertEqual(self.signup(3, **relayed("2001:db8:1:2::3")).status_code, 429)

    def test_relayed_ip_bucket_is_separate_from_direct_bucket(self):
        """봇이 직접 부르는 통을 다 써도 Next 를 거친 사람은 막히지 않는다."""
        self.counting_from(date.min)
        self.signup(1)
        self.signup(2)
        self.assertEqual(self.signup(3).status_code, 429)
        self.assertEqual(self.signup(4, **relayed("203.0.113.7")).status_code, 201)

    def test_relayed_without_ip_is_not_counted(self):
        """Next 는 시행일 전에는 IP 없이 비밀값만 싣는다. 그 요청을 봇의 통에 넣지 않는다."""
        self.counting_from(date.min)
        meta = {"HTTP_X_NEXT_RELAY": RELAY_MARK}
        for n in range(1, 5):
            self.assertEqual(self.signup(n, **meta).status_code, 201)

    def test_wrong_secret_warns_even_before_policy_date(self):
        """시행일 전에 값이 어긋난 것을 알아야 미리 맞춘다. 세지는 않는다."""
        self.counting_from(date.max)
        throttles._WARNED.clear()
        self.addCleanup(throttles._WARNED.clear)
        with self.assertLogs("apps.accounts.throttles", level="WARNING"):
            res = self.signup(1, **relayed("203.0.113.7", secret=mark("drift")))
        self.assertEqual(res.status_code, 201)

    def test_nothing_is_counted_before_policy_date(self):
        """처리방침 v3 시행 전에는 IP 도, 바로 부른 요청의 한 통도 세지 않는다."""
        self.counting_from(date.max)
        for n in range(1, 4):
            self.assertEqual(self.signup(n, **relayed("203.0.113.7")).status_code, 201)
        for n in range(10, 14):
            self.assertEqual(self.signup(n).status_code, 201)

    def test_cache_key_is_a_salted_hash_of_the_bucket(self):
        """키는 서버 비밀값을 섞은 해시다. IP 원문도, 비밀값 없는 해시도 아니다."""
        self.counting_from(date.min)
        request = RequestFactory().post(SIGNUP_URL, **relayed("203.0.113.7"))
        key = SignUpIpThrottle().get_cache_key(request, view=None)
        expected = salted_hmac("accounts.throttles.ip", "203.0.113.7", algorithm="sha256")
        self.assertEqual(key, f"throttle_signup_ip_{expected.hexdigest()}")
        self.assertNotIn("203.0.113.7", key)

    @override_settings(RELAY_SECRET="")
    def test_without_secret_everyone_shares_the_direct_bucket(self):
        """한쪽에만 비밀값을 넣으면 실제 사용자도 한 통에 든다(DEPLOY.md 가 경고하는 것)."""
        self.counting_from(date.min)
        self.assertEqual(self.signup(1, **relayed("203.0.113.7")).status_code, 201)
        self.assertEqual(self.signup(2, **relayed("203.0.113.8")).status_code, 201)
        self.assertEqual(self.signup(3, **relayed("203.0.113.9")).status_code, 429)


@override_settings(RELAY_SECRET=RELAY_MARK)
class LoginIpThrottleTest(_IpThrottleCase):
    throttle = LoginIpThrottle

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(
            email="ip-login@example.com", password=LOGIN_MARK, display_name="아이피"
        )

    def login(self, email: str, **meta):
        body = {"email": email, "password": mark("not-it")}
        return self.client.post(LOGIN_URL, body, content_type="application/json", **meta)

    def test_spraying_many_accounts_from_one_ip_is_blocked(self):
        """계정마다 한 번씩 대보는 것은 이메일 제한에 안 걸린다. IP 로 막는다."""
        self.counting_from(date.min)
        self.assertEqual(self.login("a@example.com", **relayed("203.0.113.7")).status_code, 400)
        self.assertEqual(self.login("b@example.com", **relayed("203.0.113.7")).status_code, 400)
        self.assertEqual(self.login("c@example.com", **relayed("203.0.113.7")).status_code, 429)
        self.assertEqual(self.login("d@example.com", **relayed("203.0.113.8")).status_code, 400)

    def test_correct_login_still_works_from_another_ip(self):
        self.counting_from(date.min)
        self.login("a@example.com", **relayed("203.0.113.7"))
        self.login("b@example.com", **relayed("203.0.113.7"))
        body = {"email": "ip-login@example.com", "password": LOGIN_MARK}
        res = self.client.post(
            LOGIN_URL, body, content_type="application/json", **relayed("203.0.113.8")
        )
        self.assertEqual(res.status_code, 200)


class WaitTextTest(SimpleTestCase):
    def test_minutes_over_a_minute(self):
        """시간 단위 제한이라 "3412초" 대신 분으로 적는다."""
        from config.exceptions import _wait_text

        self.assertEqual(_wait_text(None), "잠시")
        self.assertEqual(_wait_text(54), "54초")
        # 1분 단위 제한은 DRF 가 올려서 60 이 된다. 예전 문구 그대로 초로 둔다.
        self.assertEqual(_wait_text(60), "60초")
        self.assertEqual(_wait_text(61), "2분")
        self.assertEqual(_wait_text(3412), "57분")
