"""하루와 한 주의 경계.

날짜를 만드는 곳을 여기 하나로 모은다. 여러 곳에서 각자 계산하면 한 곳만
고쳐지고 나머지가 남는다 - 출석은 맞는데 순위표 주 경계가 하루 어긋나는
식으로 드러나고, 그때는 원인을 찾기 어렵다.

기준은 한국 시간이다. UTC 로 세면 밤 9시에 공부한 것이 다음 날로 넘어가
스트릭이 억울하게 끊긴다. 사용자는 이유를 모른 채 떠난다.

settings.TIME_ZONE 이 이미 Asia/Seoul 이지만 여기서 명시적으로 잡는다.
설정이 바뀌어도 학습 기록의 하루 기준은 안 바뀌어야 하기 때문이다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

KST = ZoneInfo("Asia/Seoul")


def to_kst(moment: datetime) -> datetime:
    """어떤 시각이든 한국 시간으로 옮긴다."""
    if timezone.is_naive(moment):
        # USE_TZ=True 라 naive 가 들어올 일은 없지만, 들어오면 UTC 로 본다.
        # 조용히 현재 시간대로 해석하면 서버 설정에 따라 날짜가 달라진다.
        moment = timezone.make_aware(moment, UTC)
    return moment.astimezone(KST)


def day_of(moment: datetime) -> date:
    """그 시각이 속한 날(한국 기준).

    판을 **끝낸** 시각을 넣는다. 시작 시각으로 세면 판을 열기만 해도
    출석이 쌓여서, 하루에 한 번 열고 나가는 것으로 연속이 이어진다.
    """
    return to_kst(moment).date()


def today() -> date:
    """지금 기준 오늘(한국)."""
    return day_of(timezone.now())


def week_start(day: date) -> date:
    """그 날이 속한 주의 월요일.

    주간 순위표가 이 값으로 묶인다. 월요일로 잡는 이유: 주말에 몰아서 한
    것이 다음 주로 넘어가지 않는다. 일요일 시작이면 토·일이 갈린다.
    """
    return day - timedelta(days=day.weekday())


def this_week_start() -> date:
    return week_start(today())
