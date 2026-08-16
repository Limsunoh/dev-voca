"""순위표 세 가지.

    weekly    이번 주(월~일, KST) 자유 문제풀이 한 판 최고점
    all_time  전체 기간 한 판 최고점
    streak    꾸준함 - 하루 점수를 전부 더한 값

앞의 둘은 **한 판**을 보고, 꾸준함은 **하루 줄**을 본다. 재료가 다르지만
내보내는 모양은 같다 - 화면이 셋을 같은 컴포넌트로 그릴 수 있어야 한다.

## 상위 20명 + 내 순위

목록은 20명까지다. 내가 21등 밖이면 내 줄을 따로 계산해 붙인다.
순위권 밖 사람도 자기 위치를 알아야 다음에 또 들어온다.

**자르는 일도 세는 일도 DB 가 한다.** 전 사용자를 파이썬으로 끌어와 앞
20명만 쓰면 사람이 늘수록 조용히 느려진다 - 화면은 멀쩡해서 아무도 모른다.
내가 목록 밖이면 전체를 뒤지는 대신 **나보다 앞선 사람을 센다.**

목록의 정렬과 세는 조건이 **같은 규칙**이어야 한다. 한쪽만 바꾸면 화면에
같은 등수가 둘 나온다.

## 동점 처리

**먼저 달성한 사람이 위.** 늦게 온 사람이 앞사람을 밀어내려면 더 잘해야
한다. 이렇게 안 하면 같은 점수로 순위가 계속 뒤집혀 순위표가 불안해진다.

무엇을 "먼저 달성" 으로 볼지는 순위표마다 다르다.

    최고점 2종 - 그 판을 끝낸 시각(finished_at). 명확하다.
    꾸준함     - 누적이라 "그 점수에 도달한 순간" 이 없다. 날짜순으로
                 다시 쌓아 찾을 수는 있지만 사용자마다 전 기간을 훑어야
                 한다. 대신 **활동한 날 수가 많은 쪽**을 위로 둔다.
                 같은 42점이어도 사흘에 걸쳐 쌓은 사람이 이틀에 몰아친
                 사람보다 꾸준하다 - 순위표 이름과도 맞고 계산도 싸다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Max,
    Min,
    Q,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Greatest

from . import calendar_kst
from .models import DailyScore, QuizSession, SessionKind

User = get_user_model()

# 목록에 보여줄 인원. 이보다 뒤면 "내 순위" 로만 나온다.
TOP_SIZE = 20

WEEKLY = "weekly"
ALL_TIME = "all_time"
STREAK = "streak"
KINDS = (WEEKLY, ALL_TIME, STREAK)

# 하루 점수. DailyScore.total 과 **같은 식**을 SQL 로 다시 쓴 것이다.
#
# Coalesce 가 꼭 필요하다. best_free_score 는 "아직 한 판도 안 한 날" 을
# null 로 두는데, SQL 에서 null + 2 는 2 가 아니라 **null** 이다. 그러면
# 그 날이 합계에서 통째로 빠져 일일공부만 한 날의 점수가 사라진다.
# 파이썬 쪽 total 은 (x or 0) 으로 같은 일을 하고 있다.
_DAY_TOTAL = Greatest(
    Value(0),
    Coalesce(F("best_free_score"), Value(0)) + F("daily_study_score"),
    output_field=IntegerField(),
)

# "점수가 남은 날" 이면 1, 아니면 0. 활동일을 셀 때 이걸 더한다. 판을
# 열기만 해도 그 날 행이 생기므로 행 수로 세면 망친 날까지 활동일이 된다.
#
# **두 칸을 따로 보면 안 된다.** best=5, study=-5 인 날은 총점이 0인데
# 두 칸 중 하나가 양수라 활동일이 되어버린다. 점수를 1점도 안 준 날을
# 여럿 쌓아 동점자를 이기는 길이 열린다 - 막으려던 바로 그것이다.
# 그래서 위 _DAY_TOTAL 을 그대로 쓴다.
_DAY_COUNTS = Case(
    When(_day_total__gt=0, then=Value(1)),
    default=Value(0),
    output_field=IntegerField(),
)


@dataclass
class Row:
    """순위표 한 줄. 화면이 그대로 그린다."""

    rank: int
    display_name: str
    # accounts 와 같은 모양. {"type":"preset","key":"a3"} 또는
    # {"type":"photo","url":...}. 두 칸(avatar/google_picture)으로 내보내면
    # 프론트가 "구글 사진 있으면 그것" 규칙을 따로 들고 있어야 하고,
    # 아바타를 골라 구글 사진을 안 쓰기로 한 사람의 사진 URL 까지
    # 로그인 안 한 사람에게 나간다.
    avatar: dict[str, str]
    score: int
    # 몇 판 / 며칠. 최고점은 판 수, 꾸준함은 활동한 날 수다.
    entries: int
    # 이 줄이 나인가. 화면이 내 줄을 강조하는 데 쓴다.
    #
    # pk 를 내보내지 않는 이유: 화면이 알아야 할 것은 "이게 나인가" 뿐인데
    # pk 는 순차라 **가장 큰 값이 대략 가입자 수**다. 순위표는 로그인 없이
    # 보이므로 그대로 두면 누구나 규모를 셀 수 있다.
    is_me: bool = False


@dataclass
class Board:
    """순위표 하나."""

    kind: str
    rows: list[Row]
    # 내가 목록 밖일 때만 채운다. 목록 안이면 rows 에 이미 있다.
    me: Row | None = None
    # 이번 주 순위표만 채운다. 화면이 "8/10 ~ 8/16" 을 그린다.
    period_start: date | None = None
    period_end: date | None = None


def build(kind: str, user=None) -> Board:
    """순위표 하나를 만든다. user 가 없으면(게스트) me 는 비어 있다."""
    if kind not in KINDS:
        raise ValueError(f"모르는 순위표입니다: {kind}")

    # pk 가 없으면(게스트, 또는 저장 안 된 인스턴스) 어느 줄도 내 줄이 아니다.
    me_pk = user.pk if user is not None and user.is_authenticated else None

    top = [
        _row(i + 1, item, me_pk=me_pk)
        for i, item in enumerate(_source(kind).top(TOP_SIZE))
    ]

    board = Board(kind=kind, rows=top)

    if kind == WEEKLY:
        board.period_start = calendar_kst.this_week_start()
        board.period_end = calendar_kst.week_end(board.period_start)

    if me_pk is not None:
        board.me = _me_outside_top(kind, top, user)

    return board


# ---- 안쪽 ----


def _me_outside_top(kind: str, top: list[Row], user) -> Row | None:
    """내가 목록 밖이면 내 줄을. 목록 안이거나 기록이 없으면 None.

    목록 안이면 rows 에 이미 있으므로 두 번 보내지 않는다. 화면이 같은
    줄을 두 곳에 그리면 사용자가 자기가 둘인 줄 안다.

    목록 안인지는 **is_me 표시로 본다** - 목록을 만들 때 이미 붙여뒀다.
    화면이 강조에 쓰는 값과 같은 것을 보므로, 표시가 틀리면 여기도 같이
    틀려서 곧바로 드러난다.

    목록에 없으면 **따로 센다**. 목록은 20명에서 잘려 있으므로 밖에 있는
    사람은 거기 없다.
    """
    if any(row.is_me for row in top):
        return None

    mine = _my_standing(kind, user)
    if mine is None:
        return None

    item, ahead = mine
    # me 줄은 정의상 내 줄이다. 화면이 rows 와 me 를 같은 컴포넌트로
    # 그리므로 여기서도 표시가 맞아야 한다.
    return _row(ahead + 1, item, me_pk=user.pk)


def _my_standing(kind: str, user) -> tuple[dict, int] | None:
    """내 한 줄과, 나보다 앞선 사람 수.

    전체를 끌어오지 않는다. 내 점수를 구한 뒤 "나보다 위인 사람" 만 센다.

    **동점자도 세야 한다.** 목록은 동점이어도 1,2,3 으로 번호를 매기는데,
    여기서 동점자를 빼면 규칙이 갈린다. 같은 점수 20명이 목록의 2~21등을
    채우고 있을 때 21등이 자기 줄을 보면 "2등" 이 나온다 - 화면에 2등이
    둘이고, 19등 차이가 난다.
    """
    source = _source(kind)
    rows = source.mine(user)

    if not rows:
        return None

    item = rows[0]
    return item, source.ahead(item, user)


def _row(rank: int, item: dict, *, me_pk: int | None) -> Row:
    """조회 결과 한 줄을 화면용으로.

    이름과 아바타는 **accounts 의 규칙을 그대로 빌린다.** 여기서 다시
    쓰면 두 곳이 어긋난다 - 같은 사람이 프로필 화면과 순위표에서 다른
    그림, 다른 이름으로 나온다.

    빌리려고 User 를 가볍게 하나 만든다. DB 에 안 넣고 값만 담는다.
    행마다 진짜 User 를 조회하면 20명에 20번이 된다.

    pk 는 여기서만 쓰고 밖으로 안 내보낸다(is_me 로 바꿔 나간다).
    me_pk 가 None 이면 게스트라 어느 줄도 내 줄이 아니다.

    me_pk 를 키워드로 **반드시** 받는다. 기본값을 두면 새 호출부가
    빠뜨렸을 때 조용히 "내 줄 없음" 이 되는데, 화면에서는 강조가 안 되는
    것으로만 보여 원인을 찾기 어렵다.
    """
    shown = User(
        pk=item["user"],
        display_name=item.get("user__display_name") or "",
        avatar=item.get("user__avatar") or "",
        google_picture=item.get("user__google_picture") or "",
    )

    return Row(
        rank=rank,
        display_name=shown.name_for_display,
        avatar=shown.avatar_display,
        score=int(item["score"]),
        entries=int(item["entries"]),
        is_me=me_pk is not None and item["user"] == me_pk,
    )


def _visible_users() -> Q:
    """순위표에 낼 수 있는 사용자.

    탈퇴(is_active=False)한 계정은 뺀다. 행은 CASCADE 로 같이 지워지지만,
    비활성만 시킨 경우가 있어 여기서 한 번 더 거른다.
    """
    return Q(user__is_active=True)


def _rounds(*, this_week: bool) -> QuerySet:
    """순위표가 세는 판. 일일공부는 빼고 자유 문제풀이만 본다(3-3 에서 다시 볼 것)."""
    rounds = QuizSession.objects.filter(_visible_users(), kind=SessionKind.FREE)

    if this_week:
        start = calendar_kst.this_week_start()
        rounds = rounds.filter(finished_at__gte=calendar_kst.day_begins(start))

    return rounds


def _best_by_user(rounds: QuerySet) -> QuerySet:
    """사용자별 최고 한 판. 점수 내림차순.

    동점은 **첫 판 시각(first_at)** 으로 가른다. 규칙이 말하는 "최고점을
    낸 판 중 가장 이른 시각" 을 쓰고 싶지만, 집계 안에서 집계를 참조할 수
    없다(FILTER 안에 MAX 를 못 쓴다). 그래서 쓰는 절충이고, 한계는
    _best_round_ahead 의 ponytail 주석에 적어뒀다.

    이 정렬을 _best_round_ahead 가 조건으로 그대로 옮겨 쓴다. 한쪽만
    바꾸면 목록 번호와 내 등수가 어긋난다.

    꾸준함과 달리 0점 이하를 안 거른다. 저기는 판을 열기만 해도 행이 생겨
    안 거르면 0점이 꼬리에 쌓이지만, 여기 한 줄은 **판을 실제로 끝내야**
    생긴다. 끝까지 푼 사람에게 "당신은 순위표에 없습니다" 라고 하는 쪽이
    마이너스 점수를 보여주는 것보다 나쁘다.
    """
    return (
        rounds.values(
            "user", "user__display_name", "user__avatar", "user__google_picture"
        )
        .annotate(
            score=Max("score"),
            entries=Count("id"),
            first_at=Min("finished_at"),
        )
        .order_by("-score", "first_at", "user")
    )


def _best_round_rows(*, this_week: bool, limit: int) -> list[dict]:
    """상위 몇 명. 점수 내림차순, 동점이면 먼저 끝낸 판이 위."""
    return list(_best_by_user(_rounds(this_week=this_week))[:limit])


def _best_round_rows_for(this_week: bool, user) -> list[dict]:
    """내 한 줄만. 목록 밖일 때 쓴다."""
    return list(_best_by_user(_rounds(this_week=this_week).filter(user=user)))


def _streak_by_user(days: QuerySet, *, only_scored: bool = True) -> QuerySet:
    """사용자별 꾸준함. 하루 점수를 전부 더한 값.

    DailyScore.total 과 **같은 식**을 SQL 로 다시 쓴다. 파이썬 property 는
    DB 가 모르기 때문이다 - 그대로 두면 상위 20명을 알아내려고 전 사용자의
    전 날짜를 파이썬으로 끌어와야 한다.

    두 곳에 같은 규칙이 생기므로 한쪽만 고치면 화면 숫자와 순위가 어긋난다.
    테스트가 둘이 항상 같은 값을 내는지 본다.
    """
    rows = (
        days.annotate(_day_total=_DAY_TOTAL)
        .values("user", "user__display_name", "user__avatar", "user__google_picture")
        .annotate(
            score=Sum("_day_total"),
            # 동점이면 활동한 날이 많은 쪽이 위. 같은 점수를 더 여러 날에
            # 걸쳐 쌓았다는 뜻이라 "꾸준함" 이라는 이름과 맞는다.
            #
            # **점수가 남은 날만 센다.** 판을 열기만 해도 그 날 행이 생기므로
            # 행 수로 세면 망친 날도 활동일이 된다. 그러면 같은 점수에 망친
            # 날을 더 쌓은 사람이 위로 올라가 - 꾸준함이 아니라 "행을 많이
            # 만든 사람" 이 이긴다.
            entries=Sum(_DAY_COUNTS),
        )
    )

    if only_scored:
        # 0점은 뺀다. 위와 같은 이유로, 그냥 두면 한 문제도 안 푼 사람들이
        # 0점 동점으로 꼬리에 쌓인다.
        rows = rows.filter(score__gt=0)

    return rows.order_by("-score", "-entries", "user")


def _days() -> QuerySet:
    return DailyScore.objects.filter(_visible_users())


def _streak_rows_for(user) -> list[dict]:
    """내 한 줄만. 목록 밖일 때 쓴다.

    0점도 낸다. 목록에서는 0점을 빼지만 "내가 몇 등인가" 는 다른 질문이다 -
    매일 들어와 전부 마이너스로 끝낸 사람에게 "기록이 없습니다" 라고 하면
    안 된다. 그 사람이야말로 자기 위치를 보고 다시 올 사람이다.
    """
    return list(_streak_by_user(_days().filter(user=user), only_scored=False))


def _streak_ahead(item: dict, user) -> int:
    """꾸준함에서 나보다 앞선 사람 수.

    목록의 정렬(-score, -entries, user)을 그대로 조건으로 옮긴 것이다.
    한쪽만 바꾸면 목록 번호와 내 등수가 어긋난다.
    """
    # 0점도 포함해서 센다. 목록은 0점을 빼지만 여기서까지 빼면 score=0
    # 가지가 죽어, **0점끼리는 활동일이 달라도 전부 같은 등수**가 된다.
    # 목록에 안 보이는 사람들이라 눈에 안 띈다.
    rows = _streak_by_user(_days(), only_scored=False)

    # 집계 결과를 다시 거르는 것이라 HAVING 으로 나간다. order_by 를
    # 끊지 않으면 세기용 쿼리에 쓸데없는 정렬이 붙는다.
    return (
        rows.filter(
            Q(score__gt=item["score"])
            | Q(score=item["score"], entries__gt=item["entries"])
            | Q(score=item["score"], entries=item["entries"], user__lt=user.pk)
        )
        .order_by()
        .count()
    )


def _best_round_ahead(this_week: bool, item: dict, user) -> int:
    """최고점에서 나보다 앞선 사람 수.

    꾸준함과 같이 **세기만 한다.** 동점자를 꺼내와 그 안에서 내 자리를
    찾는 방식은 못 쓴다 - 꺼내는 양에 한도를 두면 그 밖의 사람들이 전부
    같은 등수로 뭉치고(61등부터 100등까지 다 "61등"), 한도를 없애면
    동점 수천 명을 통째로 메모리에 올린다.

    목록의 정렬(-score, first_at, user)을 그대로 조건으로 옮긴 것이다.
    한쪽만 바꾸면 목록 번호와 내 등수가 어긋난다.

    # ponytail: first_at 은 "그 사람의 첫 판" 이라 "최고점을 낸 판" 과
    # 다를 수 있다. 목록도 같은 값을 쓰므로 화면은 안 깨지지만, 규칙이
    # 말하는 "먼저 달성" 과는 어긋난다.
    #
    # 어긋나는 방향이 **먼저 시작한 사람 우대**다. 월요일부터 매일 한
    # 사람과 목요일에 처음 와서 같은 점수를 낸 사람이 있으면, 목요일
    # 사람이 먼저 그 점수에 도달했는데도 아래로 간다. all_time 은 창이
    # 없어 이 차이가 서비스 수명만큼 벌어진다 - 신규 유입은 동점으로는
    # 영영 못 이긴다.
    #
    # weekly 는 차이가 최대 6일이라 작아 보이지만 **선점이 가능해서**
    # 오히려 나쁘다. 월요일 아침에 아무 판이나 하나 던져두면 그 주 내내
    # 동점 우선권을 갖는다. 점수와 무관한 행동이 순위를 정한다.
    #
    # 정확히 하려면 최고점 판의 시각을 window function 으로 SQL 에
    # 올려야 한다.
    """
    rows = _best_by_user(_rounds(this_week=this_week))

    return (
        rows.filter(
            Q(score__gt=item["score"])
            | Q(score=item["score"], first_at__lt=item["first_at"])
            | Q(
                score=item["score"],
                first_at=item["first_at"],
                user__lt=user.pk,
            )
        )
        .order_by()
        .count()
    )


@dataclass(frozen=True)
class _Source:
    """순위표 하나가 쓰는 조회 세 개.

    **셋이 한 세트여야 한다.** 목록(top)이 매기는 순서와 세기(ahead)가
    쓰는 기준이 다르면 화면에 같은 등수가 둘 나온다. 한 줄에 묶어두면
    한쪽만 고치는 실수가 눈에 띈다.
    """

    top: Callable[[int], list[dict]]
    mine: Callable[[object], list[dict]]
    ahead: Callable[[dict, object], int]


def _source(kind: str) -> _Source:
    if kind == STREAK:
        return _Source(
            top=lambda limit: list(_streak_by_user(_days())[:limit]),
            mine=_streak_rows_for,
            ahead=_streak_ahead,
        )

    this_week = kind == WEEKLY
    return _Source(
        top=lambda limit: _best_round_rows(this_week=this_week, limit=limit),
        mine=lambda user: _best_round_rows_for(this_week, user),
        ahead=lambda item, user: _best_round_ahead(this_week, item, user),
    )
