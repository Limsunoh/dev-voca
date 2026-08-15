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

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import record, session
from .throttles import (
    RoundAnswerThrottle,
    RoundFinishThrottle,
    RoundStartThrottle,
)


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
