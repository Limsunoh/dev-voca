"""요청 제한 카운터를 두는 DB 캐시. Django 의 DatabaseCache 에서 set 만 가볍게 바꿨다.

Django 의 set 은 부를 때마다 캐시 표 전체를 COUNT(*) 하고(넘치면 지우려고), 트랜잭션을 열어
키를 SELECT 한 뒤 UPDATE 나 INSERT 를 한다. DRF 요청 제한은 요청마다 get 한 번과 set 한 번을
부르므로, 제한이 붙은 요청(한 판, 순위표, 채점, 소리내어 읽기, 가입·로그인)마다 DB 를 6번
오갔다(SELECT, COUNT, BEGIN, SELECT, UPDATE, COMMIT). 답하기 한 번이 부르는 쿼리 17개 중 6개였다.

set 을 INSERT ... ON CONFLICT DO UPDATE 한 문장으로 끝낸다. get 1 + set 1 로 2번이 된다.
캐시 표의 cache_key 가 기본 키라 ON CONFLICT 로 받을 수 있다(createcachetable).

표가 넘쳤는지 세는 일(COUNT 와 넘치면 지우기)은 set CULL_EVERY 번에 한 번꼴로만 한다. 그 사이에
표가 MAX_ENTRIES 를 조금 넘을 수 있다. 넘쳐도 만료된 행만 지운다(_cull). 만료된 행은 매일 정리도
지운다(accounts.throttles.sweep_expired_counters).

get, add, touch, delete 는 Django 그대로다. 이 캐시에는 요청 제한 카운터만 들어간다(settings 의
CACHES 주석).

Django 5.2 의 DatabaseCache._base_set 과 내부 값(_table, _max_entries, _cull 의 인자)에 기댄다. Django 를
올릴 때 _base_set 의 값·만료 시각 만드는 방식이 그대로인지 다시 대조한다.
"""

from __future__ import annotations

import base64
import pickle
import random
import sys
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.db import DatabaseCache
from django.db import DatabaseError, connections, router, transaction
from django.utils.timezone import now as tz_now

# set 몇 번에 한 번 표 크기를 세나. 테스트에서는 매번 센다. 확률로 세면 요청 하나의 쿼리 수가
# 1% 확률로 하나 늘어, 쿼리 수를 견주는 테스트가 가끔 빨개진다.
CULL_EVERY = 1 if sys.argv[1:2] == ["test"] else 100


class ThrottleDatabaseCache(DatabaseCache):
    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None) -> None:
        key = self.make_and_validate_key(key, version=version)
        timeout = self.get_backend_timeout(timeout)
        db = router.db_for_write(self.cache_model_class)
        connection = connections[db]
        quote_name = connection.ops.quote_name
        table = quote_name(self._table)

        # 만료 시각과 값의 꼴은 Django 의 DatabaseCache._base_set 과 같다. 다르면 get 이 못 읽는다.
        if timeout is None:
            exp = datetime.max
        else:
            exp = datetime.fromtimestamp(timeout, tz=timezone.utc if settings.USE_TZ else None)
        exp = connection.ops.adapt_datetimefield_value(exp.replace(microsecond=0))
        encoded = base64.b64encode(pickle.dumps(value, self.pickle_protocol)).decode("latin1")

        k, v, e = quote_name("cache_key"), quote_name("value"), quote_name("expires")
        upsert = (
            f"INSERT INTO {table} ({k}, {v}, {e}) VALUES (%s, %s, %s) "
            f"ON CONFLICT ({k}) DO UPDATE SET {v} = EXCLUDED.{v}, {e} = EXCLUDED.{e}"
        )

        def write(cursor) -> None:
            if random.random() < 1 / CULL_EVERY:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                num = cursor.fetchone()[0]
                if num > self._max_entries:
                    self._cull(db, cursor, tz_now().replace(microsecond=0), num)
            cursor.execute(upsert, [key, encoded, exp])

        try:
            # 바깥에 트랜잭션이 열려 있으면 저장점 안에서 쓴다(세기·지우기·쓰기 모두). 실패해도 바깥
            # 트랜잭션이 깨지지 않게. 열려 있지 않으면 그대로 쓴다(BEGIN·COMMIT 을 아낀다). 운영은
            # ATOMIC_REQUESTS 를 쓰지 않아 요청 제한은 늘 저장점 없이 돈다.
            if connection.in_atomic_block:
                with transaction.atomic(using=db), connection.cursor() as cursor:
                    write(cursor)
            else:
                with connection.cursor() as cursor:
                    write(cursor)
        except DatabaseError:
            # Django 처럼 조용히 넘긴다. 요청 제한 카운터 하나를 못 적었다고 요청을 실패시키지 않는다.
            return

    def _cull(self, db, cursor, now, num) -> None:
        """넘쳤을 때 만료된 행만 지운다. 살아 있는 카운터는 남긴다.

        Django 는 만료된 행을 지운 뒤에도 넘치면 키 이름순으로 앞 1/3 을 지운다. 여기 든 것은
        요청 제한 카운터뿐이라, 살아 있는 카운터를 지우면 그 제한이 0 부터 다시 센다. 그리고
        행은 밖에서 늘릴 수 있다. 가입·로그인은 접속 IP 제한이 먼저 막지만(views.FirstThrottleWins),
        IP 를 많이 가진 쪽이 이메일을 바꿔 가며 보내면 IP 마다 이메일별 카운터가 쌓인다. 이메일별
        시간당 카운터는 1시간 살아서 IP 수백 개면 2만 행이 찬다. 그러면 이름순 맨 앞인 관리자
        로그인 카운터부터, 이어 이메일별 비밀번호 추측 카운터가 지워졌다.

        살아 있는 행은 길어야 1시간 뒤 만료되므로 표는 끝없이 크지 않는다. 받는 요청 수 x
        카운터 수명만큼까지다. set·add·touch 가 모두 이 함수로 지운다. CULL_FREQUENCY 는
        보지 않는다(Django 는 0 이면 표를 통째로 비운다).
        """
        connection = connections[db]
        table = connection.ops.quote_name(self._table)
        expires = connection.ops.quote_name("expires")
        cursor.execute(
            f"DELETE FROM {table} WHERE {expires} < %s",
            [connection.ops.adapt_datetimefield_value(now)],
        )
