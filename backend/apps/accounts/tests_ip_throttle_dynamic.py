"""접속 IP 제한(throttles.SignUpIpThrottle, LoginIpThrottle)을 깨뜨려 보는 테스트.

tests_ip_throttle.py 가 "비밀값이 맞으면 IP 로, 아니면 한 통" 이라는 뼈대를 본다면,
여기서는 그 경계를 비틀어 본다. 같은 IP 를 다르게 적어 통을 가르려는 시도, 비밀값을
조금만 바꾼 것, IP 칸에 엉뚱한 값을 넣은 것, 날짜 문 바로 앞뒤, 막힌 요청이 정말 아무
것도 만들지 않는지.

비율은 tests_ip_throttle.py 와 같이 get_rate 를 바꿔 2/min 으로 좁힌다.
"""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from .tests_ip_throttle import (
    CONSENT,
    LOGIN_URL,
    RELAY_MARK,
    SIGNUP_URL,
    _IpThrottleCase,
    mark,
    relayed,
)
from .throttles import IP_COUNT_FROM, LoginIpThrottle, SignUpIpThrottle, came_through_next


@override_settings(RELAY_SECRET=RELAY_MARK)
class SignUpIpBucketEdgeTest(_IpThrottleCase):
    throttle = SignUpIpThrottle

    def setUp(self):
        super().setUp()
        self.n = 0

    def signup(self, **meta):
        self.n += 1
        payload = {"email": f"edge{self.n}@example.com", "password": mark("signup-pass"), **CONSENT}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json", **meta)

    def codes(self, *metas) -> list[int]:
        return [self.signup(**meta).status_code for meta in metas]

    def test_ipv6_spellings_share_one_bucket(self):
        """같은 IPv6 를 0 을 채워 쓰거나 대문자로 써도 같은 통이다."""
        self.counting_from(date.min)
        self.assertEqual(
            self.codes(
                relayed("2001:db8::1"),
                relayed("2001:0db8:0:0:0:0:0:1"),
                relayed("2001:DB8::0001"),
            ),
            [201, 201, 429],
        )

    def test_surrounding_whitespace_is_the_same_ip(self):
        self.counting_from(date.min)
        self.assertEqual(
            self.codes(relayed("203.0.113.7"), relayed("  203.0.113.7\t"), relayed("203.0.113.7 ")),
            [201, 201, 429],
        )

    def test_bad_ip_with_right_secret_is_not_counted_and_makes_no_bucket(self):
        """비밀값이 맞아도 IP 칸이 IP 꼴이 아니면 세지 않는다. 글자마다 통을 만들지도 않는다.

        비밀값은 Next 만 가지고, Next 는 Vercel 이 준 IP 를 싣는다. IP 를 못 실은 것은
        Next 쪽 문제라 그 사용자를 바로 부른 봇의 통에 섞지 않는다.
        """
        self.counting_from(date.min)
        for raw in (
            "203.0.113.50, 10.0.0.1",
            "unknown",
            "a" * 8000,
            "203.0.113.7\x00",
            "0203.0.113.7",
        ):
            with self.subTest(raw=raw[:30]):
                request = RequestFactory().post(SIGNUP_URL, **relayed(raw))
                self.assertIsNone(SignUpIpThrottle().get_cache_key(request, view=None))
        # 바로 부른 통은 건드리지 않았다.
        self.assertEqual(self.codes({}, {}, {}), [201, 201, 429])

    def test_near_miss_secrets_are_not_trusted(self):
        """비밀값과 한 글자, 대소문자만 다른 값은 믿지 않는다."""
        for sent in (
            RELAY_MARK + "x",
            RELAY_MARK[:-1],
            RELAY_MARK.upper(),
            RELAY_MARK + "é",
        ):
            with self.subTest(sent=sent):
                request = RequestFactory().post("/", **relayed("203.0.113.7", secret=sent))
                self.assertFalse(came_through_next(request))

    def test_surrounding_whitespace_on_secret_is_ignored(self):
        """환경변수에 줄바꿈이 붙어도 같은 값으로 본다. 아니면 전원이 한 통에 든다."""
        for sent in (" " + RELAY_MARK, RELAY_MARK + " ", RELAY_MARK + "\n"):
            with self.subTest(sent=repr(sent)):
                request = RequestFactory().post("/", **relayed("203.0.113.7", secret=sent))
                self.assertTrue(came_through_next(request))
        with override_settings(RELAY_SECRET=RELAY_MARK + "\n"):
            request = RequestFactory().post("/", **relayed("203.0.113.7"))
            self.assertTrue(came_through_next(request))

    def test_non_ascii_secret_header_is_direct_not_500(self):
        self.counting_from(date.min)
        meta = relayed("203.0.113.7", secret=mark("éé"))
        self.assertEqual(self.codes(meta, meta, meta), [201, 201, 429])

    def test_blocked_request_creates_no_account(self):
        """429 로 막힌 가입은 계정을 만들지 않는다."""
        self.counting_from(date.min)
        users = get_user_model().objects
        self.codes(relayed("203.0.113.7"), relayed("203.0.113.7"))
        before = users.count()
        res = self.signup(**relayed("203.0.113.7"))
        self.assertEqual(res.status_code, 429)
        self.assertEqual(users.count(), before)
        self.assertFalse(users.filter(email=f"edge{self.n}@example.com").exists())

    def test_cache_key_is_salted_with_server_secret(self):
        """키는 서버 비밀값을 섞은 해시다. 그냥 해시면 IP 목록과 대조해 원래 IP 가 나온다."""
        self.counting_from(date.min)
        request = RequestFactory().post(SIGNUP_URL, **relayed("203.0.113.7"))
        key = SignUpIpThrottle().get_cache_key(request, view=None)
        with override_settings(SECRET_KEY=mark("other-server-key")):
            other = SignUpIpThrottle().get_cache_key(request, view=None)
        self.assertNotEqual(key, other)
        self.assertNotIn("203.0.113.7", key)
        self.assertNotIn("cb00:7107", key)
        ident = key.removeprefix("throttle_signup_ip_")
        self.assertEqual(len(ident), 64)

    def test_ipv6_cache_key_does_not_hold_the_raw_ip(self):
        self.counting_from(date.min)
        request = RequestFactory().post(SIGNUP_URL, **relayed("2001:db8::1"))
        key = SignUpIpThrottle().get_cache_key(request, view=None)
        self.assertNotIn("2001", key)
        self.assertNotIn("db8", key)

    def test_policy_date_boundary_in_korean_time(self):
        """시행일 전날까지는 아무것도 세지 않고, 시행일부터 센다.

        날짜 고정(counting_from)을 쓰지 않고 실제 IP_COUNT_FROM 에 오늘을 맞춘다.
        """
        day_before = date.fromordinal(IP_COUNT_FROM.toordinal() - 1)
        with mock.patch("django.utils.timezone.localdate", return_value=day_before):
            self.assertEqual(self.codes(*[relayed("203.0.113.7")] * 4), [201] * 4)
            # 바로 부른 요청도 시행일 전에는 세지 않는다.
            self.assertEqual(self.codes({}, {}, {}), [201] * 3)
        with mock.patch("django.utils.timezone.localdate", return_value=IP_COUNT_FROM):
            self.assertEqual(
                self.codes(relayed("203.0.113.8"), relayed("203.0.113.8"), relayed("203.0.113.8")),
                [201, 201, 429],
            )

    def test_signup_bucket_does_not_block_login(self):
        """가입 통을 다 쓴 IP 도 로그인은 된다(통이 따로다)."""
        self.counting_from(date.min)
        self.codes(relayed("203.0.113.7"), relayed("203.0.113.7"))
        body = {"email": "edge1@example.com", "password": mark("signup-pass")}
        res = self.client.post(
            LOGIN_URL, body, content_type="application/json", **relayed("203.0.113.7")
        )
        self.assertEqual(res.status_code, 200)


@override_settings(RELAY_SECRET=RELAY_MARK)
class LoginIpBucketEdgeTest(_IpThrottleCase):
    throttle = LoginIpThrottle

    def login(self, email: str, **meta):
        body = {"email": email, "password": mark("not-it")}
        return self.client.post(LOGIN_URL, body, content_type="application/json", **meta)

    def test_malformed_bodies_still_count_in_direct_bucket(self):
        """이메일이 없는 본문도 IP 통에서는 센다. 빈 본문으로 통을 비켜 갈 수 없다."""
        self.counting_from(date.min)
        for body in ("", "[]", '{"email": ""}'):
            self.client.post(LOGIN_URL, body, content_type="application/json")
        self.assertEqual(self.login("x@example.com").status_code, 429)

    def test_spraying_across_ipv6_spellings_is_blocked(self):
        self.counting_from(date.min)
        self.assertEqual(self.login("a@example.com", **relayed("2001:db8::1")).status_code, 400)
        self.assertEqual(self.login("b@example.com", **relayed("2001:0db8::0:1")).status_code, 400)
        self.assertEqual(
            self.login("c@example.com", **relayed("2001:db8:0:0:0:0:0:1")).status_code, 429
        )
