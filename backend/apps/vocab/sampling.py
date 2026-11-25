"""큰 표에서 무작위로 몇 개 고르기.

함수는 둘이다. 문제를 낼 때는 pick_pooled 를 쓴다(아래 "후보 번호를 기억해 두고
고르기" 절). 조건에 맞는 번호를 작업자 메모리에 기억해 두고 고르므로 DB 왕복이 적다.
pick_random 은 기억이 없는 고르기다. 조건이 사람마다 달라 기억해도 다시 쓰일 일이
없을 때와, pick_pooled 가 후보가 너무 많아 기억하지 않을 때 쓴다. 이 머리말은
pick_random 의 방식이다.

`order_by("?")`(SQL 의 ORDER BY RANDOM())는 조건에 맞는 행을 전부 읽고
섞은 뒤 몇 개만 쓴다. 고르는 수와 상관없이 표 크기만큼 든다. 2026-11-13
측정에서 단어·문장이 33만 개씩일 때 문제 하나 내는 데 이것만 200ms 였다
(CODE_INSIGHTS 11-13).

그래서 콘텐츠마다 무작위 키 칸(`LearningItem.random_key`, 0 이상 1 미만,
인덱스 있음)을 두고, 무작위 값 r 을 찍어 "키 >= r" 인 행을 키 순서로 몇 개
읽는다. 표 크기와 상관없이 인덱스로 몇 행만 읽는다.

처음에는 키 칸 없이 id 범위에서 지점을 찍었다. 그러면 바로 앞에 빈 id 가
많은 행이 훨씬 자주 뽑힌다. 대량 생성 콘텐츠는 분류별로 id 가 몰려 있어,
같은 분류 안에서 보기를 고를 때 늘 같은 몇 개만 나왔다. 키는 id 나 분류와
상관없이 고르게 흩어져 있어 그 몰림이 없다.

그래도 완전히 고르지는 않다. 키는 한 번 정해지면 그대로라, 앞 간격이 넓은
행이 늘 조금 더 자주 뽑힌다. 그 차이를 줄이는 것은 지점 수가 아니라 한
지점에서 읽는 창의 크기다. 창 안에서는 고르게 고르므로, 행이 뽑힐 확률이
간격 하나가 아니라 간격 여러 개의 합을 따른다. 창을 20행 이상으로 두면 하위
1% 행도 평균의 절반 넘게 뽑힌다(표 크기와 상관없다). 창이 끝(키
1)에 닿으면 키가 작은 쪽으로 이어 읽어 한 바퀴를 돈다. 안 그러면 끝자락
행이 창을 다 못 채운 채 뽑혀 더 자주 나온다.

풀이 창보다 작으면 매번 풀 전체를 읽으므로 정확히 고르다.

한계 둘.
  - 키를 손으로 넣어 한쪽에 몰리면(같은 값을 복사하거나 0 근처에 모아 두면)
    지점이 늘 같은 자리에 떨어져 몇 행만 뽑힌다. 키는 DB 가 채우게 둔다
    (DEPLOY.md).
  - 조건이 표의 1% 쯤으로 좁고 Postgres 가 그 행 수를 실제보다 적게 짐작하면,
    지점마다 인덱스로 몇 행 읽는 대신 키가 그 지점 이상인 행을 전부 읽는다.
    단어 33만 개에서 정처기 과목 하나(3천 개)로 좁히면 240ms 였다(ORDER BY
    RANDOM() 은 36ms). 지금 부르는 곳(분류, 상황과 난이도, 문장)은 같은
    측정에서 10~55ms 다(2026-11-13). 좁은 조건으로 부르게 되면 먼저 재 본다.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Collection
from typing import TypeVar

from django.core.cache import caches
from django.core.exceptions import EmptyResultSet
from django.db import connections
from django.db.models import Model, QuerySet, Value

T = TypeVar("T", bound=Model)

# 지점을 최대 몇 개 찍나. 고를 수가 많을 때 한 창에서 다 뽑지 않게 나눈다.
MAX_POINTS = 4

# 한 지점에서 적어도 이만큼 읽는다(위 머리말의 창 크기).
MIN_WINDOW = 20

# 맨 앞(키가 가장 작은 쪽)을 읽는 조각의 표시. 지점 번호와 겹치지 않는 값.
_FROM_START = -1


def pick_random(queryset: QuerySet[T], count: int) -> list[T]:
    """queryset 에서 겹치지 않게 무작위로 최대 count 개.

    queryset 의 모델은 `random_key` 칸이 있어야 한다(LearningItem 을 물려받은
    모델). 기존 정렬은 무시하고, 자르기([:n])한 queryset 은 받지 않는다.
    결과 순서도 무작위다. 행이 count 개보다 적으면 있는 만큼 돌려준다.
    """
    if count < 1:
        return []

    points = [random.random() for _ in range(min(count, MAX_POINTS))]
    # 창이 고를 수보다 작으면 지점 창들이 겹칠 때 행이 있는데도 덜 돌려준다.
    window = max(MIN_WINDOW, count)

    # 지점마다 "키 >= r" 창 하나, 그리고 한 바퀴 돌 때 이어 읽을 맨 앞 창
    # 하나. 어느 조각에서 온 행인지 _part 로 표시해 한 쿼리로 읽는다.
    #
    # 창은 번호와 키만 읽는다. 고를 것은 count 개인데 창은 지점마다 20행 이상이라, 행 전체를
    # 모델로 만들면 1개를 고르려고 40개, 문장 12개를 고르려고 100개를 만든다. 답하기 요청
    # CPU 의 절반이 여기였다(2026-11-25 측정). 고른 번호의 행만 아래에서 다시 읽는다.
    parts = [
        queryset.filter(random_key__gte=r)
        .annotate(_part=Value(i))
        .order_by("random_key")
        .values_list("pk", "random_key", "_part")[:window]
        for i, r in enumerate(points)
    ]
    parts.append(
        queryset.annotate(_part=Value(_FROM_START))
        .order_by("random_key")
        .values_list("pk", "random_key", "_part")[:window]
    )

    # 조각마다 (키, 번호) 를 모아 키 순으로 둔다. 튜플이라 sort() 가 키 순이다.
    by_part: dict[int, list[tuple]] = {}
    for pk, key, part in _run(parts):
        by_part.setdefault(part, []).append((key, pk))
    for rows in by_part.values():
        rows.sort()

    head = by_part.get(_FROM_START, [])
    # 값 없는 dict 는 "넣은 순서를 지키는 집합" 으로 쓴다. 지점 창이 겹치면 같은 번호를 한 번만.
    candidates: dict[int, None] = {}
    for i in range(len(points)):
        after = by_part.get(i, [])
        # 끝에 닿아 창이 덜 찼으면 맨 앞에서 이어 읽는다(한 바퀴 돌기).
        for _key, pk in after + head[: window - len(after)]:
            candidates.setdefault(pk, None)

    chosen = list(candidates)
    random.shuffle(chosen)
    chosen = chosen[:count]
    if not chosen:
        return []
    # 받은 queryset 그대로(select_related·only 등을 지킨다) 고른 번호만 읽고, 고른 순서로 둔다.
    # 두 번 읽는 사이에 검수가 취소된 행은 빠진다(그만큼 덜 돌려준다).
    rows = {row.pk: row for row in queryset.filter(pk__in=chosen).order_by()}
    return [rows[pk] for pk in chosen if pk in rows]


def _run(parts: list[QuerySet]) -> list[tuple]:
    """조각들을 한 쿼리(UNION ALL)로 읽는다. 못 하는 DB 면 하나씩 읽는다.

    SQLite 는 LIMIT 이 붙은 조각끼리 합치지 못한다(USE_SQLITE 모드). 조각은
    많아야 다섯이라 따로 읽어도 된다.
    """
    features = connections[parts[0].db].features
    if features.supports_slicing_ordering_in_compound:
        return list(parts[0].union(*parts[1:], all=True))
    return [row for part in parts for row in part]


# ---- 후보 번호를 기억해 두고 고르기(pick_pooled) ----

# 기억해 둘 후보 수의 상한. 넘는 조건은 기억하지 않고 pick_random 으로 고른다.
# 번호 2만 개는 캐시에 약 100KB 로 들고(LocMem 은 피클로 둔다), 꺼낼 때마다 잠깐
# 0.7MB 를 쓴다. 조건 수십 개가 다 차도 작업자마다 수 MB 다. 지금은 가장 큰 조건이
# 일상 표현 6,113개다(2026-11-25). 콘텐츠가 늘면 큰 조건(검수된 단어 전부 등)부터
# 이 상한에 걸려 pick_random 으로 돌아간다.
POOL_MAX = 20_000

# 이보다 작은 조건은 기억하지 않는다. 문제 하나짜리(?item=)나 일일공부 묶음(2~5개)처럼
# 요청마다 다른 작은 조건이 칸을 채우면, 자주 쓰는 큰 조건이 밀려난다. 경계는 pick_random
# 의 창 크기다. 창(MIN_WINDOW) 이하의 조건은 pick_random 도 매번 전부를 읽으므로, 번호를
# 새로 읽어도 예전보다 비싸지 않다. 빈 조건을 기억하지 않는 것도 이 덕이다. 기억하면 새
# 분류에 처음 검수한 콘텐츠가 5분 동안 "문제를 낼 것이 없다" 로 나온다.
POOL_MIN = MIN_WINDOW + 1

# "너무 커서 기억하지 않는다" 를 기억해 두는 표시. 매번 2만 개를 세어 보지 않게 한다.
_TOO_BIG = "too-big"


def pick_pooled(queryset: QuerySet[T], count: int, exclude: Collection[int] = ()) -> list[T]:
    """pick_random 과 같은 일을 하되, 조건에 맞는 번호 목록을 기억해 두고 고른다.

    pick_random 은 고를 때마다 DB 를 두 번 다녀온다(번호 창 조각들을 합친 쿼리, 고른
    행 읽기). 문제 하나를 만들 때 정답·보기를 따로 고르므로 이것이 너덧 번 겹쳐, 답하기
    요청 서버 시간의 2/3 가 문제 만들기였다(2026-11-25 측정). 여기서는 조건마다 번호
    전체를 작업자 메모리(CACHES["pools"])에 5분 동안 두고 파이썬에서 고른 뒤, 고른
    행만 한 번 읽는다.

    exclude 는 queryset 에 걸지 말고 여기로 넘긴다. 방금 낸 문제·정답처럼 요청마다
    달라지는 것을 queryset 에 걸면 조건이 매번 달라져 기억이 쓰이지 않는다.

    늦게 보이는 것: 새로 검수된 콘텐츠는 기억이 끝날 때까지(최대 5분, 작업자마다)
    후보에 없다. 반대로 검수가 취소되거나 지워진 것은 나가지 않는다. 고른 행을 읽을
    때 queryset 의 조건(검수됨 등)을 그대로 다시 걸기 때문이다. 그렇게 빠져 덜 모이면
    기억을 버리고 한 번만 다시 고른다.

    pick_random 과 다른 점: 후보 전체에서 고르게 뽑는다(키 창의 치우침이 없다).
    """
    if count < 1:
        return []
    key = _pool_key(queryset)
    if key is None:
        # none() 이나 빈 pk__in 처럼 볼 것도 없이 비는 조건. pick_random 처럼 빈 결과다.
        return []
    rows, short = _pick_once(queryset, key, count, exclude)
    if short:
        # 기억한 뒤 검수가 취소되거나 지워진 행이 섞였다. 기억을 버리고 다시 센다.
        caches["pools"].delete(key)
        rows, _ = _pick_once(queryset, key, count, exclude)
    return rows


def _pool_key(queryset: QuerySet) -> str | None:
    """queryset 조건의 캐시 키. 볼 것도 없이 비는 조건이면 None.

    정렬을 뺀 번호 쿼리의 SQL 과 인자로 만든다(pagination 의 개수 캐시와 같은 방법).
    str(query) 는 인자를 따옴표 없이 끼워 넣어, 다른 조건이 같은 글이 될 수 있다.
    Django 5.2 는 none()·빈 pk__in 의 SQL 을 지을 때 EmptyResultSet 을 올린다.
    """
    ids = queryset.order_by().values_list("pk", flat=True)
    try:
        sql, params = ids.query.sql_with_params()
    except EmptyResultSet:
        return None
    return "pool:" + hashlib.sha256(repr((ids.db, sql, params)).encode()).hexdigest()


def _pick_once(
    queryset: QuerySet[T], key: str, count: int, exclude: Collection[int]
) -> tuple[list[T], bool]:
    """한 번 고른다. (고른 행, 고른 것보다 덜 읽혔나)."""
    pks = _pool(queryset, key)
    if pks is None:
        narrowed = queryset.exclude(pk__in=exclude) if exclude else queryset
        return pick_random(narrowed, count), False
    skip = set(exclude)
    # 뺄 것 수만큼 넉넉히 뽑고 빼면, 목록 전체를 거르지 않고도 남은 것 가운데 고르게 뽑힌다.
    drawn = random.sample(pks, min(len(pks), count + len(skip)))
    chosen = [pk for pk in drawn if pk not in skip][:count]
    if not chosen:
        return [], False
    rows = {row.pk: row for row in queryset.filter(pk__in=chosen).order_by()}
    picked = [rows[pk] for pk in chosen if pk in rows]
    return picked, len(picked) < len(chosen)


def _pool(queryset: QuerySet, key: str) -> tuple[int, ...] | None:
    """queryset 조건에 맞는 번호 전체. 너무 많으면(POOL_MAX 초과) None."""
    cache = caches["pools"]
    hit = cache.get(key)
    if hit is not None:
        return None if hit == _TOO_BIG else hit
    # 다른 표와 이어 붙인(조인) 조건이면 같은 번호가 여러 번 나올 수 있어 한 번씩만 둔다.
    pks = tuple(dict.fromkeys(queryset.order_by().values_list("pk", flat=True)[: POOL_MAX + 1]))
    if len(pks) > POOL_MAX:
        cache.set(key, _TOO_BIG)
        return None
    if len(pks) >= POOL_MIN:
        cache.set(key, pks)
    return pks
