"""끝난 판을 기록한다.

로그인한 사람만 남긴다. 게스트는 화면에서 점수를 보고, 그 값은 브라우저에만
남는다 - 서버가 채점했더라도 계정이 없으면 순위표에 넣을 자리가 없다.

같은 판을 두 번 보내도 한 번만 남는다. 판 상태가 서명 토큰으로 오가서
끝낸 토큰을 그대로 다시 보낼 수 있기 때문이다. 판 식별자에 걸린 유일성
제약이 그것을 막는다.

**끝내기를 안 부르고 나가면 그 판은 안 남는다.** 자유 문제풀이에서는
문제가 안 된다 - 그날 점수가 최고 한 판이라 나쁜 판은 남겨도 어차피
안 세기 때문이다. 버리는 것과 남기는 것의 결과가 같다.

일일공부(SessionKind.DAILY)는 다르다. 그쪽은 **더하기**라서, 점수가
깎이는 판을 중간에 버리는 것이 이득이 된다. 일일공부를 만들 때는 끝내기를
클라이언트에 맡기면 안 된다(서버가 시작을 기록해두고 마감으로 닫는 식).
"""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from . import calendar_kst
from .models import DailyScore, QuizAnswer, QuizSession, SessionKind
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
    except IntegrityError:
        # 판 식별자가 겹쳤다 = 이미 기록된 판이다. 그 밖의 무결성 오류는
        # 여기까지 오지 않는다 - 아래 _bump_daily 는 UPDATE 만 쓰고,
        # get_or_create 는 안에서 자기 savepoint 로 경합을 처리한다.
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
