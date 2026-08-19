"""끝난 판을 기록한다.

로그인한 사람만 남긴다. 게스트는 화면에서 점수를 보고, 그 값은 브라우저에만
남는다 - 서버가 채점했더라도 계정이 없으면 순위표에 넣을 자리가 없다.

같은 판을 두 번 보내도 한 번만 남는다. 판 상태가 서명 토큰으로 오가서
끝낸 토큰을 그대로 다시 보낼 수 있기 때문이다. 판 식별자에 걸린 유일성
제약이 그것을 막는다.

**끝내기를 안 부르고 나가면 그 판은 안 남는다.** 자유 문제풀이에서는
문제가 안 된다 - 그날 점수가 최고 한 판이라 나쁜 판은 남겨도 어차피
안 세기 때문이다. 버리는 것과 남기는 것의 결과가 같다.

일일공부는 다르다. 그쪽은 **더하기**라서, 점수가 깎이는 판을 중간에
버리는 것이 이득이 된다. 그래서 daily_study.py 는 이 모듈을 안 쓰고
답할 때마다 DailyStudy 에 쌓는다 - 끝내기를 클라이언트에 맡기지 않는다.
"""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from . import calendar_kst
from .models import DailyScore, QuizAnswer, QuizSession, ReviewState, SessionKind
from .session import ANSWER_FIELDS

logger = logging.getLogger(__name__)


def save_round(user, summary: dict) -> QuizSession | None:
    """끝난 판을 남기고 그날 점수를 갱신한다.

    이미 기록된 판이면 None. 호출부는 그래도 집계를 그대로 돌려준다 -
    사용자 입장에서는 같은 판을 두 번 낸 것이고, 화면은 같은 결과를
    보면 된다.
    """
    finished_at = timezone.now()

    try:
        with transaction.atomic():
            session = QuizSession.objects.create(
                user=user,
                kind=summary["kind"]
                if summary["kind"] in SessionKind.values
                else SessionKind.FREE,
                token_id=summary["token_id"],
                started_at=summary["started_at"],
                finished_at=finished_at,
                score=summary["score"],
                answered=summary["answered"],
                correct=summary["correct"],
                skipped=summary["skipped"],
            )

            QuizAnswer.objects.bulk_create(
                _answer_rows(session, summary["answers"]),
                batch_size=100,
            )

            _bump_daily(session)

            # **자기 savepoint 안에서 부른다.** 여기서 IntegrityError 가
            # 바깥으로 나가면 save_round 가 그걸 "이미 기록된 판" 으로
            # 오인해 판 전체를 롤백한다 - 점수가 조용히 사라진다.
            # 복습 목록이 한 판 밀리는 것이 판을 잃는 것보다 낫다.
            try:
                with transaction.atomic():
                    _bump_review(user, summary["answers"])
            except IntegrityError:
                logger.warning(
                    "복습 목록 갱신에 실패했습니다. token_id=%s", summary["token_id"]
                )
    except IntegrityError:
        # 판 식별자가 겹쳤다 = 이미 기록된 판이다. 그 밖의 무결성 오류는
        # 여기까지 오지 않는다 - _bump_daily 는 UPDATE 만 쓰고,
        # get_or_create 는 안에서 자기 savepoint 로 경합을 처리하며,
        # _bump_review 는 위에서 savepoint 로 감싸 자기 오류를 삼킨다.
        logger.info("이미 기록된 판입니다. token_id=%s", summary["token_id"])
        return None

    return session


def _answer_rows(session: QuizSession, answers) -> list[QuizAnswer]:
    """답 목록을 행으로 바꾼다. 모양이 안 맞는 줄은 버린다.

    판 상태가 토큰으로 오가서, 칸 수를 늘린 배포 직후에는 **옛 모양**의
    토큰이 토큰 유효 시간만큼 들어온다. 그대로 풀면 ValueError 로 500 이 난다.
    그 판 전체를 잃느니 이상한 줄만 버리고 나머지를 남긴다.
    """
    rows = []
    for one in answers:
        if not isinstance(one, (list, tuple)) or len(one) != ANSWER_FIELDS:
            logger.warning("모양이 다른 답을 건너뜁니다. token_id=%s", session.token_id)
            continue

        kind, target_type, target_id, correct, skipped, elapsed_ms, score = one
        try:
            rows.append(
                QuizAnswer(
                    session=session,
                    kind=str(kind),
                    target_type=str(target_type),
                    target_id=int(target_id),
                    is_correct=bool(correct),
                    is_skipped=bool(skipped),
                    elapsed_ms=int(elapsed_ms),
                    score=int(score),
                )
            )
        except (TypeError, ValueError):
            logger.warning("값이 이상한 답을 건너뜁니다. token_id=%s", session.token_id)

    return rows



def _bump_review(user, answers) -> None:
    """푼 항목들의 복습 상태를 채운다.

    **복습 목록이 여기서 생긴다.** 이 쓰기가 없으면 review 화면은 표만
    있고 행이 없어 영원히 빈 목록이 된다.

    맞은 것도 남긴다 - "언제 마지막으로 맞혔나" 가 있어야 오래된 것을
    고를 수 있다. 다만 **연속 횟수는 안 올린다.** 그건 복습에서 확인한
    것만 세야 의미가 있다(review._record 참고).

    넘긴 답은 건너뛴다. 모르는 것일 수도 있지만 시간이 없어 넘긴 것일
    수도 있어, 틀렸다고 단정하면 목록이 넘긴 것으로 채워진다.
    """
    seen: dict[tuple[str, int], bool] = {}

    for one in answers:
        if not isinstance(one, (list, tuple)) or len(one) != ANSWER_FIELDS:
            continue

        _kind, target_type, target_id, correct, skipped, _elapsed, _score = one
        if skipped:
            continue

        try:
            key = (str(target_type), int(target_id))
        except (TypeError, ValueError):
            continue

        # 한 판에 같은 항목이 두 번 나오면 마지막 결과를 쓴다.
        seen[key] = bool(correct)

    if not seen:
        return

    now = timezone.now()
    # **종류까지 걸어 조회한다.** id 만으로 좁히면 단어 5번과 문장 5번이
    # 같이 걸려, 하나를 고치려다 다른 하나를 덮는다.
    lookup = Q()
    for target_type, target_id in seen:
        lookup |= Q(target_type=target_type, target_id=target_id)

    existing = {
        (row.target_type, row.target_id): row
        for row in ReviewState.objects.filter(user=user).filter(lookup)
    }

    new_rows = []
    changed = []
    for (target_type, target_id), correct in seen.items():
        row = existing.get((target_type, target_id))
        if row is None:
            new_rows.append(
                ReviewState(
                    user=user,
                    target_type=target_type,
                    target_id=target_id,
                    is_wrong=not correct,
                    last_correct_at=now if correct else None,
                )
            )
            continue

        row.is_wrong = not correct
        if correct:
            row.last_correct_at = now
        else:
            # **틀리면 연속을 끊는다.** 자유 문제풀이에서 맞힌 것은 연속을
            # 올리지 않지만(그건 복습에서 확인한 것만 센다), 틀린 것은
            # 끊어야 한다. 안 그러면 복습 1회 + 자유 오답 + 복습 1회 로
            # "연속" 아닌 두 번에 졸업한다.
            row.streak = 0
        changed.append(row)

    if new_rows:
        # 동시에 같은 판을 두 번 기록하면 겹칠 수 있다. 겹친 줄은 이미
        # 있는 것이니 버린다.
        ReviewState.objects.bulk_create(new_rows, ignore_conflicts=True)
    if changed:
        ReviewState.objects.bulk_update(
            changed, ["is_wrong", "last_correct_at", "streak"]
        )

def _bump_daily(session: QuizSession) -> None:
    """그날 한 줄을 갱신한다.

    자유 문제풀이는 **가장 높은 판 하나만** 남긴다. 이것이 하루 상한이다 -
    90초짜리를 네 시간 돌려도 그날 점수는 가장 잘한 한 판이 전부다.

    읽고-고치고-쓰지 않고 UPDATE 한 문장으로 끝내는 이유: 한 사람이 탭
    두 개로 동시에 판을 끝낼 수 있다. 파이썬에서 비교하면 둘 다 옛 값을
    읽어 낮은 쪽이 나중에 덮어쓴다.
    """
    day = calendar_kst.day_of(session.finished_at)
    row, _ = DailyScore.objects.get_or_create(user=session.user, day=day)
    rows = DailyScore.objects.filter(pk=row.pk)

    if session.kind == SessionKind.DAILY:
        # 일일공부는 하루 한 번이라 최고를 고를 것이 없다. 그대로 쌓는다.
        #
        # **지금은 이 경로로 안 온다.** 3-3 의 일일공부는 QuizSession 을
        # 만들지 않고 DailyStudy 로 진행해, 끝낼 때 add_daily_study 가
        # 그날 줄을 덮어쓴다. 여기는 그 이전 설계의 흔적이다.
        #
        # 지우지 않는 이유: QuizSession.kind 에 DAILY 가 여전히 있고,
        # 그것으로 save_round 를 부르는 옛 코드가 남아 있을 수 있다.
        # 그때 조용히 아무 일도 안 하는 것보다 예전 규칙대로 도는 편이 낫다.
        rows.update(daily_study_score=F("daily_study_score") + session.score)
        return

    # 그날 첫 판이면(아직 null) 마이너스여도 그대로 넣는다. 0 으로 시작하면
    # 마이너스만 낸 날이 "안 한 날" 과 구분되지 않는다.
    #
    # 날짜를 DB 에 묻지 않는 이유: finished_at__date 는 DB 가 settings 의
    # 시간대로 변환한 값이라, calendar_kst 와 설정이 갈리면 조용히 어긋난다.
    # 필드가 비었는지만 보면 그 의존이 사라진다.
    rows.filter(
        Q(best_free_score__isnull=True) | Q(best_free_score__lt=session.score)
    ).update(best_free_score=session.score)


def add_daily_study(user, day, score: int) -> None:
    """일일공부 점수를 그날 줄에 옮긴다.

    daily_study.py 가 공부를 닫을 때 한 번 부른다. 하루 한 번이라 최고를
    고를 것이 없고 그대로 쌓는다.

    **더하기가 아니라 덮어쓰기다.** 일일공부는 하루에 한 줄뿐이고 그 줄의
    최종 점수가 곧 그날 값이라, 더하면 한 번 더 불릴 때 점수가 두 배가 된다.

    **다만 낮아지지는 않는다.** 답할 때마다 불리므로 요청이 겹치면 늦게
    도착한 옛 값이 새 값을 덮을 수 있다 - 9번째 답이 9점을 쓰는 사이
    10번째가 끝내며 14점(보너스 포함)을 쓰면, 순서에 따라 9점이 남는다.
    일일공부 점수는 줄어들 일이 없으므로 조건 하나로 그 창을 닫는다.
    """
    row, _ = DailyScore.objects.get_or_create(user=user, day=day)
    DailyScore.objects.filter(pk=row.pk, daily_study_score__lt=score).update(
        daily_study_score=score
    )
