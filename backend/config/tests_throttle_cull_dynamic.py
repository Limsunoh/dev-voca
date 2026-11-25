"""요청 제한 표가 넘쳤을 때 살아 있는 카운터를 지우지 않는가(config/throttle_cache.py 의 _cull).

Django 기본 _cull 은 만료된 행을 지운 뒤에도 넘치면 키 이름순으로 앞 1/3 을 지운다. 이름순 맨
앞이 관리자 로그인과 이메일 로그인 카운터라, 행을 채우면 걸려 있던 429 가 풀렸다.

    실제 요청    MAX_ENTRIES 를 좁힌 캐시로 관리자 로그인·이메일 로그인 제한을 걸어 두고, 이름순
                 뒤쪽 키로 표를 채운 뒤에도 429 가 그대로인가
    만료된 행    넘치면 만료된 행은 지워지고 살아 있는 행은 남는가. set·add·touch 세 길 모두
    가드         _cull 을 Django 기본으로 바꾸면 위 테스트가 실패하는가(같은 파일 안에서 mock)

테스트 러너에서는 CULL_EVERY 가 1 이라 set 마다 센다. 캐시 자체의 쓰기·지우기 꼴은
tests_throttle_cache_dynamic 의 CullTest 가 본다.
"""

from __future__ import annotations

import copy
from unittest import mock

from apps.accounts.tests import PASSWORD
from apps.accounts.throttles import AdminLoginThrottle, EmailHourlyThrottle
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.cache.backends.db import DatabaseCache
from django.db import connection
from django.test import TestCase, override_settings

from config.throttle_cache import ThrottleDatabaseCache

User = get_user_model()
TABLE = settings.CACHES["default"]["LOCATION"]
MAX = 10


def small_caches(max_entries: int = MAX) -> dict:
    caches = copy.deepcopy(settings.CACHES)
    caches["default"]["OPTIONS"] = {"MAX_ENTRIES": max_entries}
    return caches


def keys() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT cache_key FROM "{TABLE}"')
        return {row[0] for row in cursor.fetchall()}


def expire(prefix: str) -> None:
    """그 접두어의 행을 이미 만료된 것으로 만든다."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE \"{TABLE}\" SET expires = NOW() - INTERVAL '1 hour' WHERE cache_key LIKE %s",
            [f":1:{prefix}%"],
        )


def fill(n: int, prefix: str = "throttle_zz_", target=None) -> None:
    """살아 있는 행을 채운다. 기본 접두어는 이름순으로 제한 카운터들보다 뒤에 온다."""
    for i in range(n):
        (target or cache).set(f"{prefix}{i:03d}", [1.0], 3600)


def django_cull():
    """가드 확인용. _cull 을 Django 기본(살아 있는 행도 이름순으로 지움)으로 되돌린다."""
    return mock.patch.object(ThrottleDatabaseCache, "_cull", DatabaseCache._cull)


@override_settings(CACHES=small_caches())
class LiveCountersSurviveFullTableTest(TestCase):
    def setUp(self):
        cache.clear()
        self.assertEqual(cache._max_entries, MAX)

    def narrow(self, throttle_class, rate: str) -> None:
        patcher = mock.patch.object(throttle_class, "get_rate", return_value=rate)
        patcher.start()
        self.addCleanup(patcher.stop)

    def admin_post(self):
        return self.client.post(
            "/admin/login/", {"username": "boss@example.com", "password": "wrong"}
        )

    def login_post(self):
        return self.client.post(
            "/api/accounts/login/",
            {"email": "member@example.com", "password": "wrong"},
            content_type="application/json",
        )

    def lock_admin(self) -> None:
        self.narrow(AdminLoginThrottle, "2/hour")
        User.objects.create_superuser(email="boss@example.com", password=PASSWORD)
        self.assertEqual(self.admin_post().status_code, 200)
        self.assertEqual(self.admin_post().status_code, 200)
        self.assertEqual(self.admin_post().status_code, 429)

    def lock_login(self) -> None:
        self.narrow(EmailHourlyThrottle, "2/hour")
        User.objects.create_user(email="member@example.com", password=PASSWORD)
        self.assertEqual(self.login_post().status_code, 400)
        self.assertEqual(self.login_post().status_code, 400)
        self.assertEqual(self.login_post().status_code, 429)

    def test_관리자_로그인_429_는_표를_채워도_유지된다(self):
        self.lock_admin()
        fill(MAX * 3)
        self.assertGreater(len(keys()), MAX)
        self.assertEqual(self.admin_post().status_code, 429)

    def test_이메일_로그인_429_는_표를_채워도_유지된다(self):
        self.lock_login()
        fill(MAX * 3)
        self.assertEqual(self.login_post().status_code, 429)
        # 맞는 비밀번호도 막힌다(카운터가 살아 있다).
        right = self.client.post(
            "/api/accounts/login/",
            {"email": "member@example.com", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(right.status_code, 429)

    def test_가드_django_기본_cull_이면_관리자_제한이_풀린다(self):
        """위 테스트가 _cull 을 실제로 지키는지. Django 기본으로 바꾸면 429 가 풀려야 한다."""
        self.lock_admin()
        with django_cull():
            fill(MAX * 3)
            self.assertNotEqual(self.admin_post().status_code, 429)

    def test_가드_django_기본_cull_이면_이메일_로그인_제한이_풀린다(self):
        self.lock_login()
        with django_cull():
            fill(MAX * 3)
            self.assertNotEqual(self.login_post().status_code, 429)


@override_settings(CACHES=small_caches())
class ExpiredRowsCulledTest(TestCase):
    """넘치면 만료된 행만 지운다. set·add·touch 가 모두 같은 _cull 을 탄다."""

    def setUp(self):
        cache.clear()
        # 준비하는 동안에는 넘치지 않는 캐시로 쓴다. 좁은 캐시로 쓰면 준비 중에 지워진다.
        roomy = ThrottleDatabaseCache(TABLE, {})
        fill(5, "dead_", roomy)
        expire("dead_")
        fill(MAX, "live_", roomy)
        self.dead = {f":1:dead_{i:03d}" for i in range(5)}
        self.live = {f":1:live_{i:03d}" for i in range(MAX)}

    def assert_only_dead_gone(self) -> None:
        now = keys()
        self.assertFalse(now & self.dead, "만료된 행이 남았다")
        self.assertTrue(self.live <= now, "살아 있는 행이 지워졌다")

    def test_set_이_넘치면_만료된_행만_지운다(self):
        cache.set("trigger", 1, 60)
        self.assert_only_dead_gone()
        self.assertIn(":1:trigger", keys())

    def test_add_가_넘치면_만료된_행만_지운다(self):
        self.assertTrue(cache.add("trigger", 1, 60))
        self.assert_only_dead_gone()

    def test_touch_가_넘치면_만료된_행만_지운다(self):
        self.assertTrue(cache.touch("live_000", 120))
        self.assert_only_dead_gone()

    def test_살아_있는_행만으로_넘쳐도_하나도_안_지운다(self):
        cache.clear()
        fill(MAX * 3)
        self.assertEqual(len(keys()), MAX * 3)

    def test_넘치지_않으면_만료된_행도_그대로다(self):
        """세기만 하고 넘치지 않았으면 지우지 않는다(Django 와 같다). 매일 정리가 치운다."""
        cache.clear()
        fill(2, "dead_")
        expire("dead_")
        cache.set("trigger", 1, 60)
        self.assertEqual(len(keys()), 3)

    def test_가드_django_기본이면_살아_있는_행도_지운다(self):
        # 만료된 행을 지운 뒤에도 넘쳐야 Django 가 살아 있는 행에 손을 댄다.
        fill(5, "live_x", ThrottleDatabaseCache(TABLE, {}))
        with django_cull():
            cache.set("trigger", 1, 60)
        self.assertFalse(self.live <= keys())
