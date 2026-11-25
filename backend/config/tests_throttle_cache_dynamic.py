"""요청 제한 카운터 캐시(config/throttle_cache.py 의 ThrottleDatabaseCache)를 깨뜨려 본다.

set 만 Django 의 DatabaseCache 와 다르게 쓴다(INSERT ... ON CONFLICT 한 문장). 그래서 기준은
"Django 의 DatabaseCache 와 같은 것을 적는가" 다. 같은 표에 두 백엔드로 써 보고 행을 견준다.

    같은 꼴      값(pickle·base64)과 만료 시각이 Django 가 적는 것과 글자까지 같다. 서로가 쓴 것을
                 읽는다. 만료가 지나면 없다고 한다. 시간 제한이 없으면 9999년이다
    덮어쓰기     같은 키를 다시 쓰면 행 하나가 바뀐다(INSERT 만 하면 두 번째부터 조용히 실패한다)
    넘치면 지움  테스트에서는 set 마다 세고, 지우는 결과가 Django 와 같은 키를 남긴다. 운영 간격
                 (CULL_EVERY)이면 세지 않고 넘친다
    트랜잭션     바깥 트랜잭션 안에서 쓰기·지우기가 실패해도 바깥이 깨지지 않는다. 바깥이 없을
                 때도 조용히 넘긴다
    요청 제한    DRF 가 한도에서 정확히 429 를 낸다. 트랜잭션 안(TestCase)과 밖 모두
    쿼리 수      제한이 걸린 요청의 카운터 쿼리가 읽기 1 + 쓰기 1 이고 트랜잭션을 열지 않는다.
                 Django 그대로면 읽기·세기·읽기·쓰기 4 에 BEGIN·COMMIT 이 붙는다
    나머지       add·touch·delete·get_or_set·incr·get_many 가 그대로 돈다
"""

from __future__ import annotations

import threading
import warnings
from datetime import datetime, timedelta
from unittest import mock

from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from apps.learning.tests_leaderboards_edge3 import make_user
from apps.learning.throttles import LeaderboardThrottle
from django.conf import settings
from django.core.cache import CacheKeyWarning, caches
from django.core.cache.backends.db import DatabaseCache
from django.db import DatabaseError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from config import throttle_cache
from config.throttle_cache import ThrottleDatabaseCache

TABLE = settings.CACHES["default"]["LOCATION"]
BOARD_URL = "/api/learning/leaderboards/all-time/"

# varchar(255) 를 넘는 키. 쓰기가 DB 오류(DataError)로 실패하게 만든다. memcached 경고는 의도한 것이다.
TOO_LONG_KEY = "k" * 400
warnings.filterwarnings("ignore", category=CacheKeyWarning, message=".*kkkk")


def new_cache(**options) -> ThrottleDatabaseCache:
    return ThrottleDatabaseCache(TABLE, {"OPTIONS": options} if options else {})


def django_cache(**options) -> DatabaseCache:
    return DatabaseCache(TABLE, {"OPTIONS": options} if options else {})


def raw_rows() -> dict[str, tuple[str, datetime]]:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT cache_key, value, expires FROM "{TABLE}"')
        return {key: (value, expires) for key, value, expires in cursor.fetchall()}


def raw_count() -> int:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{TABLE}"')
        return cursor.fetchone()[0]


class CacheBase(TestCase):
    def setUp(self):
        caches["default"].clear()


class SameRowAsDjangoTest(CacheBase):
    """Django 의 DatabaseCache 와 같은 값·같은 만료 시각을 적는다."""

    def test_settings_use_this_backend(self):
        self.assertIsInstance(caches["default"], ThrottleDatabaseCache)

    def test_value_and_expires_match_django_byte_for_byte(self):
        values = [[1700000000.123, 1700000001.5], {"a": [1, 2]}, "한글 값", 0, None, b"\x00\xff"]
        frozen = 1_800_000_000.987
        for timeout in (60, 1, 3600 * 24 * 400, None):
            for i, value in enumerate(values):
                with self.subTest(timeout=timeout, value=value), mock.patch("time.time", return_value=frozen):
                    django_cache().set(f"dj{i}", value, timeout)
                    new_cache().set(f"nw{i}", value, timeout)
                    rows = raw_rows()
                    self.assertEqual(rows[f":1:dj{i}"], rows[f":1:nw{i}"])

    def test_each_backend_reads_what_the_other_wrote(self):
        new_cache().set("from_new", [1, 2, 3], 60)
        django_cache().set("from_django", {"x": "y"}, 60)
        self.assertEqual(django_cache().get("from_new"), [1, 2, 3])
        self.assertEqual(new_cache().get("from_django"), {"x": "y"})

    def test_no_timeout_is_year_9999(self):
        new_cache().set("forever", "v", None)
        _value, expires = raw_rows()[":1:forever"]
        self.assertEqual(expires.year, 9999)
        far = timezone.now() + timedelta(days=365 * 50)
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=far):
            self.assertEqual(new_cache().get("forever"), "v")

    def test_expires_is_stored_in_utc_not_local_time(self):
        """만료 시각이 지금 + timeout 이다. 지역 시각으로 적으면 9시간 어긋난다."""
        before = timezone.now()
        new_cache().set("soon", "v", 60)
        _value, expires = raw_rows()[":1:soon"]
        self.assertLess(abs((expires - before).total_seconds() - 60), 3, expires)

    def test_versions_and_prefix_go_into_the_key_like_django(self):
        cache = ThrottleDatabaseCache(TABLE, {"KEY_PREFIX": "pfx", "VERSION": 3})
        cache.set("k", 1)
        self.assertIn("pfx:3:k", raw_rows())
        self.assertEqual(cache.get("k"), 1)
        self.assertIsNone(cache.get("k", version=2))


class ExpiryTest(CacheBase):
    def test_get_says_missing_after_expiry(self):
        cache = new_cache()
        cache.set("short", "v", 100)
        now = timezone.now()
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=now + timedelta(seconds=50)):
            self.assertEqual(cache.get("short"), "v")
        with mock.patch("django.core.cache.backends.db.tz_now", return_value=now + timedelta(seconds=200)):
            self.assertIsNone(cache.get("short"))
            self.assertEqual(cache.get("short", "기본"), "기본")

    def test_zero_timeout_is_already_expired(self):
        cache = new_cache()
        cache.set("zero", "v", 0)
        self.assertIsNone(cache.get("zero"))

    def test_rewriting_an_expired_key_revives_it(self):
        cache = new_cache()
        cache.set("again", "old", 0)
        cache.set("again", "new", 60)
        self.assertEqual(cache.get("again"), "new")


class OverwriteTest(CacheBase):
    def test_second_set_replaces_value_and_expiry_in_one_row(self):
        cache = new_cache()
        cache.set("same", [1], 10)
        first_exp = raw_rows()[":1:same"][1]
        cache.set("same", [1, 2], 5000)
        rows = raw_rows()
        self.assertEqual(raw_count(), 1)
        self.assertEqual(cache.get("same"), [1, 2])
        self.assertGreater(rows[":1:same"][1], first_exp)

    def test_shorter_timeout_on_overwrite_also_applies(self):
        cache = new_cache()
        cache.set("shrink", "v", 5000)
        cache.set("shrink", "v", 0)
        self.assertIsNone(cache.get("shrink"))


class OtherOperationsTest(CacheBase):
    """set 만 바꿨다. 나머지가 그 set 과 섞여도 깨지지 않는다."""

    def test_add(self):
        cache = new_cache()
        self.assertTrue(cache.add("a", 1, 60))
        self.assertFalse(cache.add("a", 2, 60))
        self.assertEqual(cache.get("a"), 1)
        cache.set("b", "x", 0)
        self.assertTrue(cache.add("b", "y", 60), "만료된 키에는 add 가 된다")
        self.assertEqual(cache.get("b"), "y")

    def test_touch_moves_expiry(self):
        cache = new_cache()
        cache.set("t", "v", 100)
        self.assertTrue(cache.touch("t", 5000))
        _value, expires = raw_rows()[":1:t"]
        self.assertGreater(expires, timezone.now() + timedelta(seconds=4000))
        self.assertFalse(cache.touch("없음", 10))

    def test_delete_has_key_get_or_set_incr(self):
        cache = new_cache()
        cache.set("d", 1)
        self.assertTrue(cache.has_key("d"))
        self.assertTrue(cache.delete("d"))
        self.assertFalse(cache.delete("d"))
        self.assertIsNone(cache.get("d"))

        self.assertEqual(cache.get_or_set("g", lambda: [7], 60), [7])
        self.assertEqual(cache.get_or_set("g", lambda: [8], 60), [7])

        cache.set("n", 5)
        self.assertEqual(cache.incr("n", 3), 8)
        self.assertEqual(cache.get("n"), 8)

    def test_set_many_get_many_delete_many_clear(self):
        cache = new_cache()
        self.assertEqual(cache.set_many({"m1": 1, "m2": [2]}, 60), [])
        self.assertEqual(cache.get_many(["m1", "m2", "m3"]), {"m1": 1, "m2": [2]})
        cache.delete_many(["m1"])
        self.assertEqual(cache.get_many(["m1", "m2"]), {"m2": [2]})
        cache.clear()
        self.assertEqual(raw_count(), 0)


class CullTest(CacheBase):
    def run_sequence(self, cache) -> set[str]:
        caches["default"].clear()
        for i in range(30):
            cache.set(f"c{i:02d}", i, 3600 if i % 3 else 0)  # 셋 중 하나는 이미 만료
        return set(raw_rows())

    def test_culls_exactly_like_django_when_counting_every_set(self):
        """테스트에서는 set 마다 센다. 지우고 남는 키가 Django 와 같다."""
        self.assertEqual(throttle_cache.CULL_EVERY, 1)
        ours = self.run_sequence(new_cache(MAX_ENTRIES=5, CULL_FREQUENCY=2))
        theirs = self.run_sequence(django_cache(MAX_ENTRIES=5, CULL_FREQUENCY=2))
        self.assertEqual(ours, theirs)
        self.assertLessEqual(len(ours), 6)

    def test_cull_frequency_zero_clears_like_django(self):
        ours = self.run_sequence(new_cache(MAX_ENTRIES=5, CULL_FREQUENCY=0))
        theirs = self.run_sequence(django_cache(MAX_ENTRIES=5, CULL_FREQUENCY=0))
        self.assertEqual(ours, theirs)

    def test_production_interval_skips_counting_and_lets_table_grow(self):
        """운영 간격(100)에 random 이 1/100 밖이면 세지 않는다. 그 사이 상한을 넘을 수 있다."""
        cache = new_cache(MAX_ENTRIES=5)
        with mock.patch.object(throttle_cache, "CULL_EVERY", 100), \
                mock.patch.object(throttle_cache.random, "random", return_value=0.5), \
                CaptureQueriesContext(connection) as ctx:
            for i in range(12):
                cache.set(f"g{i}", i, 60)
        self.assertEqual(raw_count(), 12)
        self.assertFalse(any("COUNT(" in q["sql"] for q in ctx.captured_queries))

    def test_production_interval_counts_when_random_hits(self):
        cache = new_cache(MAX_ENTRIES=5, CULL_FREQUENCY=2)
        with mock.patch.object(throttle_cache, "CULL_EVERY", 100), \
                mock.patch.object(throttle_cache.random, "random", return_value=0.5):
            for i in range(12):
                cache.set(f"h{i:02d}", i, 60)
        with mock.patch.object(throttle_cache, "CULL_EVERY", 100), \
                mock.patch.object(throttle_cache.random, "random", return_value=0.001):
            cache.set("h99", 99, 60)
        self.assertLessEqual(raw_count(), 7)
        self.assertEqual(cache.get("h99"), 99, "센 뒤의 쓰기는 남는다")


class FailureInsideTransactionTest(CacheBase):
    """TestCase 는 바깥 트랜잭션 안이다. 저장점이 없으면 실패한 쓰기가 바깥을 깨뜨린다."""

    def assert_outer_transaction_alive(self):
        # Postgres 는 트랜잭션 안에서 문장 하나가 실패하면 되돌릴 때까지 모든 문장을 거절한다.
        user = make_user("살아있음")
        self.assertTrue(type(user).objects.filter(pk=user.pk).exists())

    def test_failed_upsert_is_silent_and_outer_transaction_survives(self):
        self.assertTrue(connection.in_atomic_block)
        new_cache().set(TOO_LONG_KEY, "v", 60)
        self.assert_outer_transaction_alive()
        new_cache().set("ok", "v", 60)
        self.assertEqual(new_cache().get("ok"), "v")

    def test_failed_cull_is_silent_and_rolls_back_only_this_write(self):
        def broken_cull(db, cursor, now, num):
            cursor.execute('SELECT * FROM "no_such_table_for_cull"')

        cache = new_cache(MAX_ENTRIES=1)
        cache.set("first", 1, 60)
        cache.set("second", 2, 60)  # 이제 2 > 1 이라 다음 set 이 지우러 간다
        with mock.patch.object(cache, "_cull", side_effect=broken_cull):
            cache.set("third", 3, 60)
        self.assert_outer_transaction_alive()
        self.assertIsNone(cache.get("third"), "저장점과 함께 되돌려져야 한다")
        self.assertEqual(cache.get("first"), 1)

    def test_failed_write_inside_explicit_atomic_keeps_earlier_work(self):
        with transaction.atomic():
            user = make_user("앞일")
            new_cache().set(TOO_LONG_KEY, "v", 60)
            user.display_name = "앞일2"
            user.save()
        user.refresh_from_db()
        self.assertEqual(user.display_name, "앞일2")


class FailureInAutocommitTest(_KeepsCacheTable, TransactionTestCase):
    """운영처럼 바깥 트랜잭션이 없을 때."""

    def setUp(self):
        caches["default"].clear()

    def test_failed_upsert_is_silent_and_connection_is_usable(self):
        self.assertFalse(connection.in_atomic_block)
        new_cache().set(TOO_LONG_KEY, "v", 60)
        new_cache().set("ok", [1], 60)
        self.assertEqual(new_cache().get("ok"), [1])

    def test_writes_are_committed_without_a_transaction(self):
        """저장점 없이 바로 쓴 값이 다른 연결에서도 보인다(커밋됐다)."""
        new_cache().set("visible", "v", 60)
        result: list = []

        def other():
            try:
                result.append(new_cache().get("visible"))
            finally:
                connections.close_all()

        thread = threading.Thread(target=other)
        thread.start()
        thread.join()
        self.assertEqual(result, ["v"])

    def test_concurrent_sets_on_one_key_leave_one_row(self):
        """같은 키를 여러 스레드가 동시에 써도 오류가 없고 행은 하나다. 값은 누군가 쓴 것이다."""
        errors: list = []
        barrier = threading.Barrier(4)

        def hammer(n: int):
            try:
                barrier.wait()
                for i in range(25):
                    new_cache().set("race", (n, i), 60)
            except Exception as exc:  # noqa: BLE001 - 무엇이든 실패로 센다
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=hammer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual([k for k in raw_rows() if k.endswith("race")], [":1:race"])
        n, i = new_cache().get("race")
        self.assertIn(n, range(4))
        self.assertEqual(i, 24, "각 스레드의 마지막 쓰기 중 하나가 남는다")


class ThrottleCountsTest(CacheBase):
    """DRF 요청 제한이 이 캐시로 정확히 센다. TestCase 라 저장점 길이다."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(LeaderboardThrottle, "get_rate", return_value="3/min")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fourth_request_in_a_minute_is_429(self):
        self.client.force_login(make_user("제한"))
        codes = [self.client.get(BOARD_URL).status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    def test_other_account_has_its_own_bucket(self):
        self.client.force_login(make_user("하나"))
        for _ in range(3):
            self.client.get(BOARD_URL)
        self.assertEqual(self.client.get(BOARD_URL).status_code, 429)
        self.client.force_login(make_user("둘"))
        self.assertEqual(self.client.get(BOARD_URL).status_code, 200)


class ThrottleQueriesTest(_KeepsCacheTable, TransactionTestCase):
    """운영처럼 바깥 트랜잭션이 없을 때의 요청 제한. 카운터 쿼리 수와 정확도를 본다."""

    def setUp(self):
        caches["default"].clear()
        self.user = make_user("쿼리수")

    def throttle_queries(self, *, cull_every: int | None = 100) -> tuple[list[str], int]:
        """순위표 한 번 요청의 카운터 쿼리와, 그 동안 커밋한 횟수."""
        self.client.force_login(self.user)
        self.client.get(BOARD_URL)  # 세션·첫 행을 미리 만든다
        wrapper = type(connections["default"])
        commits = mock.patch.object(wrapper, "commit", autospec=True, side_effect=wrapper.commit)
        with mock.patch.object(throttle_cache, "CULL_EVERY", cull_every or 1), \
                mock.patch.object(throttle_cache.random, "random", return_value=0.5), \
                CaptureQueriesContext(connection) as ctx, commits as spy:
            self.assertEqual(self.client.get(BOARD_URL).status_code, 200)
        sql = [q["sql"] for q in ctx.captured_queries if TABLE in q["sql"]]
        return sql, spy.call_count

    def test_counter_costs_one_read_and_one_upsert(self):
        sql, commits = self.throttle_queries()
        self.assertEqual(len(sql), 2, sql)
        self.assertTrue(sql[0].startswith("SELECT"), sql)
        self.assertIn("ON CONFLICT", sql[1])
        self.assertEqual(commits, 0, "카운터 쓰기에 트랜잭션을 열었다")

    def test_django_backend_costs_four_queries_and_a_transaction(self):
        """대조군. 같은 요청을 Django 의 DatabaseCache 로 하면 4 + BEGIN·COMMIT 이다."""
        django_default = {**settings.CACHES["default"], "BACKEND": "django.core.cache.backends.db.DatabaseCache"}
        with override_settings(CACHES={**settings.CACHES, "default": django_default}):
            sql, commits = self.throttle_queries()
        self.assertEqual(len(sql), 4, sql)
        self.assertEqual(commits, 1)

    def test_counting_interval_adds_only_the_count(self):
        sql, _ = self.throttle_queries(cull_every=None)
        self.assertEqual(len(sql), 3, sql)
        self.assertIn("COUNT(", sql[1])

    def test_limit_is_exact_without_outer_transaction(self):
        with mock.patch.object(LeaderboardThrottle, "get_rate", return_value="4/min"):
            self.client.force_login(self.user)
            codes = [self.client.get(BOARD_URL).status_code for _ in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 429, 429])

    def test_concurrent_requests_never_crash(self):
        """같은 계정이 동시에 순위표를 열어도 500 이 없다(쓰기 경합은 조용히 덮어쓴다)."""
        self.client.force_login(self.user)
        session = self.client.cookies
        codes: list[int] = []
        barrier = threading.Barrier(4)

        def hit():
            client = Client()
            client.cookies = session
            try:
                barrier.wait()
                for _ in range(5):
                    codes.append(client.get(BOARD_URL).status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=hit) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(set(codes), {200})


class DatabaseErrorIsTheOnlySwallowedErrorTest(CacheBase):
    def test_programming_errors_other_than_db_still_raise(self):
        """값이 pickle 이 안 되면 Django 처럼 그대로 터진다(조용히 넘기는 것은 DB 오류뿐)."""
        with self.assertRaises(Exception) as caught:
            new_cache().set("lambda", lambda: 1, 60)
        self.assertNotIsInstance(caught.exception, DatabaseError)
