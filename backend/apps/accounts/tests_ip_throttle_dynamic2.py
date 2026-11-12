"""접속 IP 제한을 실서버로 두드려 본 시나리오를 회귀 테스트로 옮긴 것(2차).

runserver(DEBUG=0, 운영 비율 가입 30/hour, 로그인 60/hour)에 직접 요청해서 확인한 것 중
tests_ip_throttle.py, tests_ip_throttle_dynamic.py 가 보지 않던 조합만 남긴다.

- 틀린 비밀값과 머리 없는 요청이 같은 한 통(direct)을 나눠 쓰는지
- 그 통이 꽉 차도 Next 를 거친 요청(IP 가 있든 없든)은 막히지 않는지
- 공백 붙은 비밀값이 direct 가 아니라 IP 통으로 세지는지
- IPv4-mapped 의 16진 표기, mapped 에 존을 붙인 표기
- 시간 단위 제한의 429 문구가 "N분" 이고 Retry-After 가 1분을 넘는지
- 한국 시간 0시 경계(UTC 15:00)에서 날짜 문이 열리는지

비율은 앞의 두 파일처럼 get_rate 를 바꿔 좁힌다.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from datetime import timezone as dt_timezone
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings

from . import throttles
from .tests_ip_throttle import (
    CONSENT,
    LOGIN_URL,
    RELAY_MARK,
    SIGNUP_URL,
    _IpThrottleCase,
    mark,
    relayed,
)
from .throttles import (
    IP_COUNT_FROM,
    LoginIpThrottle,
    SignUpIpThrottle,
    came_through_next,
    client_ip_bucket,
)

WRONG_MARK = mark("wrong-relay")


def next_without_ip(secret: str = RELAY_MARK) -> dict[str, str]:
    """시행일 전 Next 가 싣는 꼴, 또는 Next 가 IP 를 못 읽은 꼴. 비밀값만 있다."""
    return {"HTTP_X_NEXT_RELAY": secret}


@override_settings(RELAY_SECRET=RELAY_MARK)
class SignUpDirectBucketMixTest(_IpThrottleCase):
    throttle = SignUpIpThrottle

    def setUp(self):
        super().setUp()
        self.n = 0
        self.counting_from(date.min)
        # 경고는 지문마다 프로세스에서 한 번만 찍는다. 앞 테스트가 찍은 지문을 비운다.
        throttles._WARNED.clear()
        self.addCleanup(throttles._WARNED.clear)

    def signup(self, **meta):
        self.n += 1
        payload = {"email": f"mix{self.n}@example.com", "password": mark("signup-pass"), **CONSENT}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json", **meta)

    def codes(self, *metas) -> list[int]:
        return [self.signup(**meta).status_code for meta in metas]

    def test_wrong_secret_and_no_header_share_one_direct_bucket(self):
        """비밀값을 틀리게 싣는 것과 아예 안 싣는 것은 같은 통이다. 둘을 번갈아 써서 통을
        둘로 늘릴 수 없다."""
        with self.assertLogs("apps.accounts.throttles", level="WARNING"):
            self.assertEqual(
                self.codes(relayed("198.51.100.1", secret=WRONG_MARK), {}, {}),
                [201, 201, 429],
            )

    def test_full_direct_bucket_does_not_block_next_requests(self):
        """봇이 direct 통을 다 써도 Next 를 거친 사람은 IP 가 있든 없든 가입된다."""
        self.codes({}, {})
        self.assertEqual(self.signup().status_code, 429)
        self.assertEqual(self.signup(**relayed("192.0.2.99")).status_code, 201)
        for _ in range(3):
            self.assertEqual(self.signup(**next_without_ip()).status_code, 201)

    def test_padded_secret_counts_in_ip_bucket_not_direct(self):
        """공백 붙은 비밀값은 맞는 값과 같은 IP 통에 든다. direct 통은 그대로 비어 있다."""
        padded = f"  {RELAY_MARK}\t"
        self.assertEqual(
            self.codes(
                relayed("203.0.113.50", secret=padded),
                relayed("203.0.113.50", secret=padded),
                relayed("203.0.113.50"),
            ),
            [201, 201, 429],
        )
        self.assertEqual(self.codes({}, {}), [201, 201])

    def test_ipv4_mapped_hex_spelling_shares_bucket(self):
        """::ffff:c633:640a 는 198.51.100.10 을 16진으로 적은 것이다."""
        self.assertEqual(
            self.codes(
                relayed("::ffff:198.51.100.10"),
                relayed("::ffff:c633:640a"),
                relayed("198.51.100.10"),
            ),
            [201, 201, 429],
        )

    def test_hourly_limit_message_is_in_minutes(self):
        """시간 단위 제한에 걸리면 "3412초" 가 아니라 "N분" 으로 적는다."""
        with mock.patch.object(SignUpIpThrottle, "get_rate", return_value="2/hour"):
            self.codes(relayed("203.0.113.9"), relayed("203.0.113.9"))
            res = self.signup(**relayed("203.0.113.9"))
        self.assertEqual(res.status_code, 429)
        detail = res.json()["detail"]
        self.assertRegex(detail, r"^시도가 너무 많습니다\. \d+분 뒤에 다시 해주세요\.$")
        minutes = int(re.search(r"(\d+)분", detail).group(1))
        self.assertGreater(int(res["Retry-After"]), 60)
        self.assertEqual(minutes, -(-int(res["Retry-After"]) // 60))

    def test_wrong_secret_warns_with_fingerprint_not_value_or_ip(self):
        """틀린 비밀값은 경고 한 줄. 비밀값도 접속 IP 도 아니고 보낸 값의 지문만 남긴다.
        같은 값이 되풀이되면 더 찍지 않고, 다른 값이면 다시 찍는다."""
        other = mark("wrong-relay-2")
        with self.assertLogs("apps.accounts.throttles", level="WARNING") as logs:
            self.signup(**relayed("198.51.100.77", secret=WRONG_MARK))
            self.signup(**relayed("198.51.100.78", secret=WRONG_MARK))
            self.signup(**relayed("198.51.100.79", secret=other))
        self.assertEqual(len(logs.output), 2)
        prints = [hashlib.sha256(v.encode()).hexdigest()[:8] for v in (WRONG_MARK, other)]
        for line, fingerprint in zip(logs.output, prints):
            self.assertIn(fingerprint, line)
        text = " | ".join(logs.output)
        for leaked in (WRONG_MARK, other, RELAY_MARK, "198.51.100.7"):
            self.assertNotIn(leaked, text)

    def test_wrong_secret_warns_even_before_policy_date(self):
        """날짜 문이 닫힌 동안에도 어긋난 비밀값은 알린다. 세기 시작하는 날 전에 고칠 수 있다."""
        self.counting_from(date.max)
        with self.assertLogs("apps.accounts.throttles", level="WARNING"):
            self.assertEqual(self.signup(**next_without_ip(WRONG_MARK)).status_code, 201)


@override_settings(RELAY_SECRET=RELAY_MARK)
class LoginNextWithoutIpTest(_IpThrottleCase):
    throttle = LoginIpThrottle

    def test_next_without_ip_is_not_counted_on_login(self):
        """로그인도 가입과 같다. Next 가 IP 를 못 실은 요청은 세지 않는다."""
        self.counting_from(date.min)
        for n in range(4):
            body = {"email": f"nl{n}@example.com", "password": mark("not-it")}
            res = self.client.post(
                LOGIN_URL, body, content_type="application/json", **next_without_ip()
            )
            self.assertEqual(res.status_code, 400)


class BucketSpellingTest(SimpleTestCase):
    def bucket(self, raw: str) -> str | None:
        return client_ip_bucket(RequestFactory().post("/", HTTP_X_NEXT_CLIENT_IP=raw))

    def test_mapped_with_zone_is_plain_ipv4(self):
        self.assertEqual(self.bucket("::ffff:198.51.100.10%eth0"), "198.51.100.10")

    def test_64_edges(self):
        """한 /64 의 첫 주소와 끝 주소는 같은 통, 바로 다음 /64 는 다른 통이다."""
        first = self.bucket("2001:db8:aaaa:1::")
        self.assertEqual(first, self.bucket("2001:db8:aaaa:1:ffff:ffff:ffff:ffff"))
        self.assertNotEqual(first, self.bucket("2001:db8:aaaa:2::"))


class WhitespaceServerSecretTest(SimpleTestCase):
    @override_settings(RELAY_SECRET="  \n")
    def test_whitespace_only_server_secret_trusts_nothing(self):
        """백엔드 비밀값이 공백뿐이면 비어 있는 것과 같다. 공백 머리도 믿지 않는다."""
        for sent in ("  \n", " ", RELAY_MARK):
            with self.subTest(sent=repr(sent)):
                request = RequestFactory().post("/", HTTP_X_NEXT_RELAY=sent)
                self.assertFalse(came_through_next(request))


@override_settings(RELAY_SECRET=RELAY_MARK)
class KoreanMidnightTest(_IpThrottleCase):
    """날짜 문은 한국 시간으로 연다. 시행일 0시(KST)는 UTC 로 전날 15:00 이다.

    timezone.localdate 를 고정하지 않고 timezone.now 만 바꿔, TIME_ZONE 설정까지 함께 본다.
    """

    throttle = SignUpIpThrottle

    def key_at(self, utc: datetime) -> str | None:
        request = RequestFactory().post(SIGNUP_URL, **relayed("203.0.113.7"))
        with mock.patch("django.utils.timezone.now", return_value=utc):
            return SignUpIpThrottle().get_cache_key(request, view=None)

    def test_opens_at_korean_midnight(self):
        day_before = date.fromordinal(IP_COUNT_FROM.toordinal() - 1)
        last_moment = datetime(
            day_before.year, day_before.month, day_before.day, 14, 59, 59, 999999,
            tzinfo=dt_timezone.utc,
        )
        opening = datetime(
            day_before.year, day_before.month, day_before.day, 15, 0, 0, tzinfo=dt_timezone.utc
        )
        self.assertIsNone(self.key_at(last_moment))
        self.assertIsNotNone(self.key_at(opening))


class WaitTextEdgeTest(SimpleTestCase):
    def test_boundaries(self):
        from config.exceptions import _wait_text

        self.assertEqual(_wait_text(59), "59초")
        self.assertEqual(_wait_text(61), "2분")
        self.assertEqual(_wait_text(3600), "60분")
