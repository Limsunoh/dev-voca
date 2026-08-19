"""학습 기록 API.

한 판은 세 번의 요청으로 이루어진다.

    POST /api/learning/rounds/          판을 연다. 첫 문제가 같이 온다
    POST /api/learning/rounds/answer/   답하거나 넘긴다. 다음 문제가 같이 온다
    POST /api/learning/rounds/finish/   판을 닫는다. 로그인했으면 기록된다

판 상태는 응답의 token 에 담겨 오간다. 서버는 판을 저장하지 않는다 -
이유는 session.py 첫머리에 적어뒀다.

로그인하지 않아도 풀 수 있다. 다만 기록되지 않으므로 순위표에 안 들어간다.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import daily_study, leaderboards, record, session
from .models import STUDY_PLANS, StudyLength
from .throttles import (
    DailyStudyAnswerThrottle,
    DailyStudyThrottle,
    LeaderboardThrottle,
    RoundAnswerThrottle,
    RoundFinishThrottle,
    RoundStartThrottle,
)

logger = logging.getLogger(__name__)


def _token_of(request: Request) -> str:
    token = request.data.get("token") if isinstance(request.data, dict) else None
    if not isinstance(token, str) or not token:
        raise session.SessionError("판 정보가 없습니다.")
    return token


def _fail(exc: session.SessionError) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class RoundStartView(APIView):
    """판을 연다."""

    permission_classes = [AllowAny]
    throttle_classes = [RoundStartThrottle]

    def post(self, request: Request) -> Response:
        try:
            token, question = session.start()
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {
                "token": token,
                "question": question,
                "round_seconds": session.ROUND_SECONDS,
                "max_skips": session.MAX_SKIPS,
            },
            status=status.HTTP_201_CREATED,
        )


class RoundAnswerView(APIView):
    """답하거나 넘긴다."""

    permission_classes = [AllowAny]
    throttle_classes = [RoundAnswerThrottle]

    def post(self, request: Request) -> Response:
        try:
            token = _token_of(request)
        except session.SessionError as exc:
            return _fail(exc)

        body = request.data if isinstance(request.data, dict) else {}
        skip = body.get("skip") is True

        picked = body.get("choice_id")
        # bool 은 int 의 하위라 True 가 1 로 통과한다. 그러면 id 1 번을
        # 고른 것으로 처리된다.
        if isinstance(picked, bool) or not isinstance(picked, int):
            picked = None

        if not skip and picked is None:
            return Response(
                {"detail": "보기를 고르거나 넘겨주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            next_token, result, question = session.answer(token, picked, skip=skip)
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {
                "token": next_token,
                "result": {
                    "correct": result.correct,
                    "skipped": result.skipped,
                    "in_time": result.in_time,
                    "score": result.score,
                    "elapsed_ms": result.elapsed_ms,
                    "answer_type": result.answer_type,
                    "answer_text": result.answer_text,
                    "answer_extra": result.answer_extra,
                },
                "question": question,
                "finished": question is None,
            }
        )


class RoundFinishView(APIView):
    """판을 닫는다. 로그인했으면 기록한다."""

    permission_classes = [AllowAny]
    throttle_classes = [RoundFinishThrottle]

    def post(self, request: Request) -> Response:
        try:
            token = _token_of(request)
            summary = session.finish(token)
        except session.SessionError as exc:
            return _fail(exc)

        saved = False
        if request.user.is_authenticated and summary["answered"] > 0:
            # 한 문제도 안 푼 판은 남기지 않는다. 열고 바로 닫기를 반복해
            # 행만 쌓는 것을 막는다.
            saved = record.save_round(request.user, summary) is not None

        return Response(
            {
                "score": summary["score"],
                "answered": summary["answered"],
                "correct": summary["correct"],
                "skipped": summary["skipped"],
                "recorded": saved,
                # 로그인 안 했으면 화면이 이 값을 보고 안내한다.
                "guest": not request.user.is_authenticated,
            }
        )


class LeaderboardView(APIView):
    """순위표 하나. 종류는 URL 로 갈린다.

    로그인하지 않아도 볼 수 있다. 순위표는 "나도 저기 오르고 싶다" 를
    만드는 화면이라 가입 전에 보여야 의미가 있다. 로그인했으면 내가
    몇 등인지도 같이 내려준다.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LeaderboardThrottle]

    # URL 마다 다른 값을 넣는다. 기본값을 두지 않는다 - 빈 문자열이
    # 기본이면 서브클래스가 빠뜨렸을 때 조용히 build() 까지 흘러간다.
    board_kind: str

    def get(self, request: Request) -> Response:
        board = leaderboards.build(self.board_kind, user=request.user)

        body = {
            "kind": board.kind,
            "rows": [asdict(row) for row in board.rows],
            "me": asdict(board.me) if board.me else None,
        }

        if board.period_start is not None:
            body["period"] = {
                "start": board.period_start,
                "end": board.period_end,
            }

        return Response(body)


class WeeklyBestView(LeaderboardView):
    board_kind = leaderboards.WEEKLY


class AllTimeBestView(LeaderboardView):
    board_kind = leaderboards.ALL_TIME


class StreakView(LeaderboardView):
    board_kind = leaderboards.STREAK


class DailyStudyStartView(APIView):
    """오늘 일일공부를 연다.

    **로그인이 필요하다.** 진행이 DB 에 남아야 하는 기능이라 계정이 없으면
    이어서 볼 자리가 없다. 자유 문제풀이가 게스트를 받는 것과 다르다.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [DailyStudyThrottle]

    def get(self, request: Request) -> Response:
        """오늘 상태를 본다. 화면이 시작 전에 무엇을 그릴지 정한다."""
        # **어제 판을 여기서도 정산한다.** 시작할 때만 정산하면, 며칠 안
        # 들어온 사람의 판이 열린 채 남는다. 그리고 어제 판을 "오늘" 로
        # 내려주면 화면이 "이어서 풀기" 를 그리는데 이어 풀 토큰이 없다 -
        # 서버가 약속하지 않은 것을 화면이 약속하게 된다.
        # 정산이 실패해도 조회는 살린다. 화면 진입 경로라 여기서 500 이
        # 나면 일일공부를 아예 못 연다. 정산은 다음 조회나 시작에서 다시
        # 시도되는 성격이라 조회를 막을 만큼 급하지 않다 - 시작할 때는
        # 반대로 삼키지 않는다(열린 판이 둘이 되면 안 된다).
        try:
            daily_study.settle_stale(request.user)
        except Exception:
            logger.exception("일일공부 정산에 실패했습니다. user=%s", request.user.pk)

        study = daily_study.today_of(request.user)
        return Response(
            {
                "lengths": [
                    {
                        "value": value,
                        "label": label,
                        "questions": STUDY_PLANS[value][0],
                        "bonus": STUDY_PLANS[value][1],
                    }
                    for value, label in StudyLength.choices
                ],
                "today": _study_body(study) if study else None,
            }
        )

    def post(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        length = body.get("length")
        if not isinstance(length, str):
            return Response(
                {"detail": "길이를 골라주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            study, token, question = daily_study.start(request.user, length)
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {"token": token, "question": question, "study": _study_body(study)},
            status=status.HTTP_201_CREATED,
        )


class DailyStudyAnswerView(APIView):
    """일일공부 답 하나."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [DailyStudyAnswerThrottle]

    def post(self, request: Request) -> Response:
        try:
            token = _token_of(request)
        except session.SessionError as exc:
            return _fail(exc)

        body = request.data if isinstance(request.data, dict) else {}
        picked = body.get("choice_id")
        # bool 은 int 의 하위라 True 가 1 로 통과한다.
        if isinstance(picked, bool) or not isinstance(picked, int):
            return Response(
                {"detail": "보기를 골라주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result, next_token, question, studied = daily_study.answer(
                request.user, token, picked
            )
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {
                "result": {
                    "correct": result.correct,
                    "score": result.score,
                    "answer_type": result.answer_type,
                    "answer_text": result.answer_text,
                    "answer_extra": result.answer_extra,
                },
                "token": next_token,
                "question": question,
                "finished": question is None,
                "study": _study_body(studied),
            }
        )


def _study_body(study) -> dict:
    """오늘 줄을 화면용으로."""
    return {
        "length": study.length,
        "total": study.total_questions,
        "answered": study.answered,
        "correct": study.correct,
        "score": study.score,
        "bonus": study.bonus,
        "done": study.is_done,
    }
