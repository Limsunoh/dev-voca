"""로그인하지 않은 사람을 접속 IP 별로 세는 제한을 깨뜨려 보는 테스트(learning 쪽).

대상: 한 판 시작·답하기·끝내기, 순위표 셋(apps.accounts.throttles.PerUserOrIpThrottle 을 상속).
vocab 쪽(낱개 연습 채점, 소리내어 읽기)은 apps/vocab/tests_guest_ip_throttle_dynamic.py 가
이 파일의 GuestIpThrottleCase 를 받아 같은 시나리오를 돈다.

계약.
  1. 비밀값(X-Next-Relay)이 맞고 X-Next-Client-IP 가 있으면 IP(IPv6 는 /64)마다 따로 센다.
     한 IP 가 한도를 다 써도 다른 IP 는 안 막힌다.
  2. 비밀값이 없거나 틀리면 IP 와 상관없이 "direct" 한 통이다.
  3. 비밀값은 맞는데 IP 가 없거나 IP 꼴이 아니면 세지 않는다.
  4. 로그인한 사람은 계정별이고, 실어 보낸 IP 머리가 IP 통에 섞이지 않는다.
  5. 로그인하지 않은 통의 한도는 계정 한도 x guest_multiplier(답하기 5, 나머지 20).

제한은 본문 검사보다 먼저 돈다. 그래서 빈 본문으로 불러 429 인지 아닌지만 본다(400 은
제한을 통과했다는 뜻이다). 비율은 get_rate 를 바꿔 1/min 으로 좁힌다. override_settings 로는
안 된다(DRF 가 스로틀을 만들 때 설정을 굳힌다, accounts/tests_ip_throttle.py).
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts import throttles as account_throttles
from apps.accounts.models import LoginToken
from apps.accounts.tests import PASSWORD
from apps.accounts.tests_ip_throttle import RELAY_MARK, mark, relayed

from .throttles import (
    LeaderboardThrottle,
    RoundAnswerThrottle,
    RoundFinishThrottle,
    RoundStartThrottle,
)

User = get_user_model()

WRONG_MARK = mark("wrong-relay")

IP_A = "203.0.113.7"
IP_B = "198.51.100.23"


def next_without_ip() -> dict[str, str]:
    """Next 가 접속 IP 를 못 읽었을 때 싣는 꼴. 비밀값만 있다."""
    return {"HTTP_X_NEXT_RELAY": RELAY_MARK}


class Endpoint:
    """부를 곳 하나와 그 자리의 배수."""

    def __init__(self, name: str, method: str, url: str, multiplier: int, scope: str):
        self.name = name
        self.method = method
        self.url = url
        self.multiplier = multiplier
        # 같은 scope 는 통을 같이 쓴다(단어·문장 채점). 섞임 검사에서 뺀다.
        self.scope = scope

    def __repr__(self) -> str:
        return self.name


LEARNING_ENDPOINTS = [
    Endpoint("round-start", "post", "/api/learning/rounds/", 20, "round_start"),
    Endpoint("round-answer", "post", "/api/learning/rounds/answer/", 5, "round_answer"),
    Endpoint("round-finish", "post", "/api/learning/rounds/finish/", 20, "round_finish"),
    Endpoint("weekly", "get", "/api/learning/leaderboards/weekly/", 20, "leaderboard:weekly"),
    Endpoint("all-time", "get", "/api/learning/leaderboards/all-time/", 20, "leaderboard:all_time"),
    Endpoint("streak", "get", "/api/learning/leaderboards/streak/", 20, "leaderboard:streak"),
]


@override_settings(RELAY_SECRET=RELAY_MARK)
class _GuestIpBase(TestCase):
    """셋업과 부르기 도구. 테스트 메서드는 없다."""

    ENDPOINTS: list[Endpoint] = LEARNING_ENDPOINTS
    # 비율을 좁힐 기반 클래스. 하위 클래스가 get_rate 를 덮지 않아 여기만 바꾸면 된다.
    THROTTLE_BASES: tuple[type, ...] = (account_throttles.PerUserOrIpThrottle,)
    BASE = 1

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        account_throttles._WARNED.clear()
        self.addCleanup(account_throttles._WARNED.clear)
        for base in self.THROTTLE_BASES:
            patcher = mock.patch.object(base, "get_rate", return_value=f"{self.BASE}/min")
            patcher.start()
            self.addCleanup(patcher.stop)

    # ---- 부르기 --------------------------------------------------------------

    def call(self, ep: Endpoint, **meta) -> int:
        caller = getattr(self.client, ep.method)
        if ep.method == "post":
            res = caller(ep.url, {}, content_type="application/json", **meta)
        else:
            res = caller(ep.url, **meta)
        self.assertLess(res.status_code, 500, f"{ep} 가 {res.status_code}")
        return res.status_code

    def burn(self, ep: Endpoint, n: int, **meta) -> list[int]:
        return [self.call(ep, **meta) for _ in range(n)]

    def guest_limit(self, ep: Endpoint) -> int:
        return self.BASE * ep.multiplier

    @contextmanager
    def fresh(self, ep: Endpoint):
        """엔드포인트 하나를 빈 캐시에서 subTest 로 돈다. 실패가 그 엔드포인트 이름으로 남는다."""
        with self.subTest(endpoint=ep.name):
            cache.clear()
            # 틀린 비밀값 경고는 지문마다 한 번만 찍는다. 앞 엔드포인트가 찍은 것을 비운다.
            account_throttles._WARNED.clear()
            yield

    def member(self, name: str) -> dict[str, str]:
        user = User.objects.create_user(email=f"{name}@example.com", password=PASSWORD)
        return {"HTTP_AUTHORIZATION": f"Token {LoginToken.objects.create(user=user).key}"}

    def key_of(self, throttle_cls: type, **meta) -> str | None:
        request = RequestFactory().get("/", **meta)
        request.user = SimpleNamespace(is_authenticated=False)
        view = SimpleNamespace(board_kind="weekly")
        return throttle_cls().get_cache_key(request, view)

    def no_ip_metas(self) -> list[dict[str, str]]:
        return [
            next_without_ip(),
            relayed(""),
            relayed("   "),
            relayed("localhost"),
            relayed("203.0.113.7, 10.0.0.1"),
            relayed("999.1.1.1"),
        ]

    def assert_never_counted(self, ep: Endpoint) -> None:
        metas = self.no_ip_metas()
        for i in range(self.guest_limit(ep) * 2 + 3):
            meta = metas[i % len(metas)]
            self.assertNotEqual(self.call(ep, **meta), 429, f"{ep} {meta}")


class GuestIpThrottleCase(_GuestIpBase):
    """한 앱의 엔드포인트 묶음을 받아 계약 다섯을 돈다. vocab 쪽이 ENDPOINTS 등만 바꿔 받는다.

    vocab 쪽은 이 모듈을 통째로 import 해서 상속한다. 이름으로 import 하면 그 모듈에서도
    이 클래스가 발견돼 learning 테스트가 두 번 돈다.
    """

    # 캐시 키를 직접 볼 스로틀.
    THROTTLE_CLASSES: tuple[type, ...] = (
        RoundStartThrottle,
        RoundAnswerThrottle,
        RoundFinishThrottle,
        LeaderboardThrottle,
    )

    # ---- 1. IP 마다 따로, 5. 한도는 계정 한도 x 배수 -------------------------------

    def test_한_IP가_한도를_다_써도_다른_IP는_안_막힌다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                limit = self.guest_limit(ep)
                codes = self.burn(ep, limit, **relayed(IP_A))
                self.assertNotIn(429, codes, f"배수 {ep.multiplier} 만큼 다 쓰기 전에 막혔다")
                self.assertEqual(self.call(ep, **relayed(IP_A)), 429, "IP 통에 한도가 없다")
                self.assertNotEqual(self.call(ep, **relayed(IP_B)), 429, "다른 IP 가 막혔다")
                self.assertNotEqual(self.call(ep, **relayed("2001:db8:9::1")), 429)
                # Next 를 거치지 않은 통(direct)도 IP 통과 따로다.
                self.assertNotEqual(self.call(ep), 429, "IP 통이 direct 통과 섞였다")

    def test_IPv6_는_64_로_묶고_v4_mapped_는_v4_와_같은_통이다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                limit = self.guest_limit(ep)
                same64 = ["2001:db8:1:2::1", "2001:db8:1:2:ffff::9", "2001:DB8:1:2::abcd"]
                for i in range(limit):
                    self.assertNotEqual(self.call(ep, **relayed(same64[i % 3])), 429)
                self.assertEqual(
                    self.call(ep, **relayed("2001:db8:1:2:dead::1")), 429,
                    "같은 /64 안에서 주소를 바꿔 통을 늘릴 수 있다",
                )
                self.assertNotEqual(self.call(ep, **relayed("2001:db8:1:3::1")), 429)

                cache.clear()
                for i in range(limit):
                    ip = "::ffff:192.0.2.5" if i % 2 else "192.0.2.5"
                    self.assertNotEqual(self.call(ep, **relayed(ip)), 429)
                self.assertEqual(self.call(ep, **relayed("::ffff:192.0.2.5")), 429)

    # ---- 2. 비밀값이 없거나 틀리면 direct 한 통 -----------------------------------

    def test_비밀값이_없거나_틀리면_IP와_무관하게_한_통이다(self):
        direct_metas = [
            {},
            {"HTTP_X_NEXT_CLIENT_IP": IP_A},
            relayed(IP_B, secret=WRONG_MARK),
            relayed("192.0.2.200", secret=mark("another-wrong")),
            relayed(IP_A, secret=""),
        ]
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                limit = self.guest_limit(ep)
                with self.assertLogs("apps.accounts.throttles", level="WARNING"):
                    for i in range(limit):
                        meta = direct_metas[i % len(direct_metas)]
                        self.assertNotEqual(self.call(ep, **meta), 429)
                    for meta in direct_metas:
                        self.assertEqual(self.call(ep, **meta), 429, f"direct 통이 갈렸다: {meta}")
                # direct 통이 꽉 차도 Next 를 거친 사람은 안 막힌다.
                self.assertNotEqual(self.call(ep, **relayed(IP_A)), 429)

    @override_settings(RELAY_SECRET="")
    def test_백엔드에_비밀값이_없으면_빈_비밀값을_실어도_direct_다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                for n in range(self.guest_limit(ep)):
                    ip = f"192.0.2.{n % 250 + 1}"
                    self.assertNotEqual(self.call(ep, **relayed(ip, secret="")), 429)
                self.assertEqual(self.call(ep, **relayed(IP_B, secret="")), 429)

    # ---- 3. 비밀값은 맞는데 IP 가 없거나 IP 꼴이 아니면 세지 않는다 ---------------------

    def test_비밀값은_맞는데_IP가_없거나_꼴이_아니면_세지_않는다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                if ep.scope.startswith("leaderboard"):
                    continue  # 순위표는 아래 test_순위표도_IP_없는_요청을_세지_않는다 가 본다.
                self.assert_never_counted(ep)

    # ---- 4. 로그인한 사람은 계정별, IP 통과 섞이지 않는다 -----------------------------

    def test_로그인한_사람은_계정_한도이고_IP_머리를_실어도_IP_통을_쓰지_않는다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                first = {**self.member(f"m1-{ep.name}"), **relayed(IP_A)}
                self.assertEqual(self.burn(ep, self.BASE, **first).count(429), 0)
                self.assertEqual(self.call(ep, **first), 429, "로그인한 사람에게 배수가 붙었다")

                # 같은 IP 의 다른 계정은 안 막힌다(계정별).
                self.assertNotEqual(self.call(ep, **self.member(f"m2-{ep.name}"), **relayed(IP_A)), 429)

                # 계정이 IP 머리를 실어 보낸 것이 IP 통을 깎지 않았다.
                codes = self.burn(ep, self.guest_limit(ep), **relayed(IP_A))
                self.assertNotIn(429, codes, "로그인한 요청이 IP 통에 섞였다")

    def test_IP_통이_꽉_차도_같은_IP의_로그인한_사람은_안_막힌다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                self.burn(ep, self.guest_limit(ep), **relayed(IP_A))
                self.assertEqual(self.call(ep, **relayed(IP_A)), 429)
                self.assertNotEqual(self.call(ep, **self.member(f"m3-{ep.name}"), **relayed(IP_A)), 429)
                # direct 통이 꽉 찬 경우도 같다.
                self.burn(ep, self.guest_limit(ep))
                self.assertEqual(self.call(ep), 429)
                self.assertNotEqual(self.call(ep, **self.member(f"m4-{ep.name}")), 429)

    # ---- 통끼리 섞이지 않는다 ----------------------------------------------------

    def test_한_자리의_IP_통을_다_써도_다른_자리는_안_막힌다(self):
        for ep in self.ENDPOINTS:
            with self.fresh(ep):
                self.burn(ep, self.guest_limit(ep), **relayed(IP_A))
                self.assertEqual(self.call(ep, **relayed(IP_A)), 429)
                for other in self.ENDPOINTS:
                    if other.scope == ep.scope:
                        continue
                    self.assertNotEqual(
                        self.call(other, **relayed(IP_A)), 429, f"{ep} 의 IP 통이 {other} 를 막았다"
                    )

    # ---- 캐시 키 ----------------------------------------------------------------

    def test_캐시_키에_IP_원문이_남지_않는다(self):
        """처리방침이 IP 해시로 센다고 적었다. 키에 원문이 남으면 캐시 표에 IP 가 쌓인다."""
        for cls in self.THROTTLE_CLASSES:
            with self.subTest(throttle=cls.__name__):
                for ip in (IP_A, "2001:db8:1:2::1"):
                    key = self.key_of(cls, **relayed(ip))
                    self.assertIsNotNone(key)
                    self.assertNotIn(ip, key)
                    self.assertNotIn("2001:db8", key)
                self.assertNotEqual(self.key_of(cls, **relayed(IP_A)), self.key_of(cls, **relayed(IP_B)))
                with self.assertLogs("apps.accounts.throttles", level="WARNING"):
                    wrong = self.key_of(cls, **relayed(IP_A, secret=WRONG_MARK))
                account_throttles._WARNED.clear()
                self.assertEqual(self.key_of(cls), wrong)

    def test_IP_없는_요청의_키는_None_이다(self):
        for cls in self.THROTTLE_CLASSES:
            if issubclass(cls, LeaderboardThrottle):
                continue  # 아래 LeaderboardNoIpTest 가 본다.
            with self.subTest(throttle=cls.__name__):
                self.assertIsNone(self.key_of(cls, **next_without_ip()))
                self.assertIsNone(self.key_of(cls, **relayed("localhost")))


class LeaderboardNoIpTest(_GuestIpBase):
    """순위표만 따로 본다. LeaderboardThrottle.get_cache_key 가 부모 키 뒤에 순위표 이름을
    붙이는데, 부모가 None(세지 않음)을 돌려주면 "None:weekly" 라는 글자 키가 되어 IP 없는
    요청이 순위표마다 한 통에 모였다(처음 구현에서 동적 테스트가 잡았다).
    """

    ENDPOINTS = [ep for ep in LEARNING_ENDPOINTS if ep.scope.startswith("leaderboard")]

    def test_순위표도_IP_없는_요청을_세지_않는다(self):
        for ep in self.ENDPOINTS:
            cache.clear()
            self.assert_never_counted(ep)

    def test_순위표의_IP_없는_요청_키는_None_이다(self):
        self.assertIsNone(self.key_of(LeaderboardThrottle, **next_without_ip()))


@override_settings(RELAY_SECRET=RELAY_MARK)
class ThrottleClassContractTest(TestCase):
    """learning·vocab 의 제한 클래스를 하나씩 직접 돌려 본다. 위 시나리오는 로그인 없이 부를 수
    있는 자리만 HTTP 로 부른다. 일일공부·복습처럼 로그인해야 닿는 클래스도 같은 부모를 쓰므로,
    부모를 합친 뒤 그 클래스들의 계정별 세기가 그대로인지는 여기서만 드러난다.

    DRF 처럼 요청마다 새 인스턴스를 만들어 allow_request 를 부른다.
    """

    EXPECTED_MULTIPLIER = {"RoundAnswerThrottle": 5}  # 나머지는 20.

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        account_throttles._WARNED.clear()
        self.addCleanup(account_throttles._WARNED.clear)
        patcher = mock.patch.object(
            account_throttles.PerUserOrIpThrottle, "get_rate", return_value="1/min"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.view = SimpleNamespace(board_kind="weekly")

    @staticmethod
    def all_classes() -> list[type]:
        """learning·vocab 의 throttles 모듈에 정의된 제한 클래스 전부."""
        import inspect

        from rest_framework.throttling import BaseThrottle

        from apps.vocab import throttles as vocab_throttles

        from . import throttles as learning_throttles

        found = []
        for module in (learning_throttles, vocab_throttles):
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseThrottle) and obj.__module__ == module.__name__:
                    found.append(obj)
        return found

    def allowed(self, cls: type, user=None, **meta) -> int:
        """새 인스턴스로 거듭 불러 몇 번까지 통과하는지 센다. 막히지 않으면 상한까지 센다."""
        user = user or SimpleNamespace(is_authenticated=False)
        count = 0
        for _ in range(50):
            request = RequestFactory().get("/", **meta)
            request.user = user
            if not cls().allow_request(request, self.view):
                return count
            count += 1
        return count

    def test_모든_제한_클래스가_하나의_부모를_쓴다(self):
        classes = self.all_classes()
        # learning 8개(판 셋, 순위표, 일일공부 둘, 복습 둘) + vocab 3개.
        self.assertEqual(len(classes), 11, [c.__name__ for c in classes])
        for cls in classes:
            with self.subTest(throttle=cls.__name__):
                self.assertTrue(issubclass(cls, account_throttles.PerUserOrIpThrottle))

    def test_로그인하지_않은_통은_클래스마다_정해진_배수다(self):
        for cls in self.all_classes():
            with self.subTest(throttle=cls.__name__):
                cache.clear()
                want = self.EXPECTED_MULTIPLIER.get(cls.__name__, 20)
                self.assertEqual(self.allowed(cls, **relayed(IP_A)), want)
                cache.clear()
                self.assertEqual(self.allowed(cls), want, "direct 통의 배수가 다르다")

    def test_로그인한_사람은_클래스마다_배수_없이_계정별이다(self):
        for cls in self.all_classes():
            with self.subTest(throttle=cls.__name__):
                cache.clear()
                one = SimpleNamespace(is_authenticated=True, pk=101)
                two = SimpleNamespace(is_authenticated=True, pk=102)
                self.assertEqual(self.allowed(cls, user=one, **relayed(IP_A)), 1)
                # 같은 IP 의 다른 계정은 따로 센다.
                self.assertEqual(self.allowed(cls, user=two, **relayed(IP_A)), 1)
                # 계정 통이 꽉 차 있어도 같은 IP 의 로그인하지 않은 통은 처음부터다.
                want = self.EXPECTED_MULTIPLIER.get(cls.__name__, 20)
                self.assertEqual(self.allowed(cls, **relayed(IP_A)), want)

    def test_IP를_못_실은_요청은_클래스마다_세지_않는다(self):
        for cls in self.all_classes():
            with self.subTest(throttle=cls.__name__):
                cache.clear()
                for meta in (next_without_ip(), relayed("localhost"), relayed("")):
                    self.assertEqual(self.allowed(cls, **meta), 50, meta)

    def test_IP마다_따로이고_direct는_IP와_무관한_한_통이다(self):
        for cls in self.all_classes():
            with self.subTest(throttle=cls.__name__):
                cache.clear()
                want = self.EXPECTED_MULTIPLIER.get(cls.__name__, 20)
                self.assertEqual(self.allowed(cls, **relayed(IP_A)), want)
                self.assertEqual(self.allowed(cls, **relayed(IP_B)), want)
                # 틀린 비밀값 경고는 지문마다 한 번만 찍는다. 앞 클래스가 찍은 것을 비운다.
                account_throttles._WARNED.clear()
                with self.assertLogs("apps.accounts.throttles", level="WARNING"):
                    self.assertEqual(self.allowed(cls, **relayed(IP_A, secret=WRONG_MARK)), want)
                # 비밀값 없이 다른 IP 를 실어도 같은 direct 통이라 바로 막힌다.
                self.assertEqual(self.allowed(cls, HTTP_X_NEXT_CLIENT_IP=IP_B), 0)


class LeaderboardBoardKindTest(_GuestIpBase):
    """순위표 키가 board_kind 를 먼저 읽는지. 부모 키가 None 인 길(IP 를 못 실은 요청)에서
    board_kind 를 읽기 전에 돌아가면, 그 뷰를 IP 있는 요청이 처음 부를 때까지 실수가 숨는다.
    """

    def key(self, view, user=None, **meta):
        request = RequestFactory().get("/", **meta)
        request.user = user or SimpleNamespace(is_authenticated=False)
        return LeaderboardThrottle().get_cache_key(request, view)

    def test_board_kind_를_빠뜨린_뷰는_어느_길에서도_터진다(self):
        from .views import LeaderboardView

        class Broken(LeaderboardView):
            pass

        cases = {
            "IP 없음": next_without_ip(),
            "IP 꼴 아님": relayed("localhost"),
            "빈 IP": relayed(""),
            "IP 있음": relayed(IP_A),
            "direct": {},
        }
        for name, meta in cases.items():
            with self.subTest(name):
                with self.assertRaises(AttributeError):
                    self.key(Broken(), **meta)
        with self.subTest("로그인"):
            with self.assertRaises(AttributeError):
                self.key(Broken(), user=SimpleNamespace(is_authenticated=True, pk=5), **next_without_ip())

    def test_순위표마다_키가_다르고_로그인_키는_계정을_따른다(self):
        member = SimpleNamespace(is_authenticated=True, pk=5)
        for who, user, meta in (("IP", None, relayed(IP_A)), ("direct", None, {}),
                                ("계정", member, relayed(IP_A))):
            with self.subTest(who):
                keys = {self.key(SimpleNamespace(board_kind=k), user=user, **meta)
                        for k in ("weekly", "all_time", "streak")}
                self.assertEqual(len(keys), 3)
                self.assertNotIn(None, keys)
                self.assertFalse(any(k.startswith("None") or "None:" in k for k in keys))
        self.assertIsNone(self.key(SimpleNamespace(board_kind="streak"), **relayed("localhost")))
