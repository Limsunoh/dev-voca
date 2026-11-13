"""큰 표에서 무작위로 몇 개 고르기.

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

import random
from typing import TypeVar

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
    parts = [
        queryset.filter(random_key__gte=r).annotate(_part=Value(i)).order_by("random_key")[:window]
        for i, r in enumerate(points)
    ]
    parts.append(queryset.annotate(_part=Value(_FROM_START)).order_by("random_key")[:window])

    by_part: dict[int, list[T]] = {}
    for row in _run(parts):
        by_part.setdefault(row._part, []).append(row)
    for rows in by_part.values():
        rows.sort(key=lambda row: row.random_key)

    head = by_part.get(_FROM_START, [])
    candidates: dict[int, T] = {}
    for i in range(len(points)):
        after = by_part.get(i, [])
        # 끝에 닿아 창이 덜 찼으면 맨 앞에서 이어 읽는다(한 바퀴 돌기).
        for row in after + head[: window - len(after)]:
            candidates.setdefault(row.pk, row)

    chosen = list(candidates.values())
    random.shuffle(chosen)
    return chosen[:count]


def _run(parts: list[QuerySet[T]]) -> list[T]:
    """조각들을 한 쿼리(UNION ALL)로 읽는다. 못 하는 DB 면 하나씩 읽는다.

    SQLite 는 LIMIT 이 붙은 조각끼리 합치지 못한다(USE_SQLITE 모드). 조각은
    많아야 다섯이라 따로 읽어도 된다.
    """
    features = connections[parts[0].db].features
    if features.supports_slicing_ordering_in_compound:
        return list(parts[0].union(*parts[1:], all=True))
    return [row for part in parts for row in part]
