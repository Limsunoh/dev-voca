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

from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.vocab.models import Word
from apps.vocab.serializers import QuizWordSerializer

from . import daily_study, leaderboards, record, review, session
from .models import STUDY_PLANS, StudyLength
from .throttles import (
    DailyStudyAnswerThrottle,
    DailyStudyThrottle,
    LeaderboardThrottle,
    ReviewAnswerThrottle,
    ReviewThrottle,
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

        # **이어 풀 토큰을 함께 내려준다.** 없으면 하다 만 사람이 오늘 판을
        # 영영 못 끝낸다 - 답하려면 토큰이 필요한데 시작은 하루 한 번
        # 제약에 막히기 때문이다. 제한 시간이 없는 기능이라 중간에 나가는
        # 것이 예외가 아니다.
        token, question = None, None
        learning: list[dict] = []
        if study is not None and not study.is_done:
            # **학습과 문제를 함께 내려준다.** 이번 묶음의 카드와, 그
            # 묶음에서 낸 문제를 한 번에 준다. 화면은 카드를 다 넘긴 뒤
            # 문제로 넘어간다 - 서버에 "봤다" 를 알릴 필요가 없다.
            #
            # 나눠서 주면 그 신호가 필요해지는데, 그건 점수와 무관한
            # 요청이라 되돌리기를 막을 이유가 없고 막지 않으면 왕복만
            # 늘어난다. 카드 몇 장은 그냥 같이 보내는 편이 싸다.
            #
            # **묶음 뽑기는 resume 에 맡긴다.** 여기서 먼저 부르면 그
            # 사이에 검수가 취소됐을 때 카드는 나가고 범위는 비는 조합이
            # 생긴다 - 화면이 보여준 카드와 무관한 단어로 문제가 나간다.
            resumed = daily_study.resume(study)
            if resumed is not None:
                token, question = resumed
                study.refresh_from_db()
                if daily_study.is_chunk_start(study):
                    learning = [
                        _word_body(w) for w in daily_study.learn_targets(study)
                    ]
            else:
                # **문제가 없으면 카드도 안 보낸다.** 화면은 카드를 다
                # 넘긴 뒤 문제로 넘어가는데, 넘어갈 문제가 없으면 길이
                # 고르기로 떨어진다 - 하다 만 판이 있으면 거기서 길이
                # 버튼도 막혀 있어 아무것도 못 하는 화면에 갇힌다.
                #
                # 이어 풀 문제를 못 만드는 판은 드물지만(묶음이 좁아
                # 보기를 못 채우고 전체 폴백까지 실패), 못 이어갈 카드를
                # 애초에 안 주는 편이 화면에서 막는 것보다 확실하다.
                learning = []

        # **캐시하지 않는다.** 응답에 매번 다른 서명 토큰이 실리므로,
        # 어디든 캐시가 붙으면 여러 사용자가 같은 토큰을 받는다. GET 은
        # 기본적으로 캐시 가능한 메서드라 프록시·중계 어디서든 붙을 수 있다.
        body = Response(
            {
                "lengths": [
                    {
                        "value": value,
                        "label": label,
                        "questions": STUDY_PLANS[value].total,
                        "bonus": STUDY_PLANS[value].bonus,
                        # 고르기 전에 "몇 개를 공부하는지" 를 보여준다.
                        # 문제 수만 있으면 길이 선택이 "얼마나 오래
                        # 걸리나" 로만 읽힌다.
                        "words": STUDY_PLANS[value].from_study,
                    }
                    for value, label in StudyLength.choices
                ],
                "today": _study_body(study) if study else None,
                "token": token,
                "question": question,
                # 이번 묶음의 학습 카드. 비어 있으면 문제를 풀 차례다.
                "learning": learning,
            }
        )
        body["Cache-Control"] = "no-store"
        return body

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

        # 시작하자마자 학습부터다. 첫 묶음을 함께 내려줘 화면이 바로
        # 그리게 한다 - 시작 직후 다시 GET 하면 그 사이가 빈 화면이다.
        learning = [_word_body(w) for w in daily_study.issue_chunk(study)]

        return Response(
            {
                "token": token,
                "question": question,
                "study": _study_body(study),
                "learning": learning,
            },
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
                # **끝났는지는 판이 정한다.** question 이 없는 것만 보면
                # 다음이 학습 차례일 때도 "끝" 으로 읽힌다.
                "finished": studied.is_done,
                "study": _study_body(studied),
                # **묶음이 넘어가는 답에만 카드가 실린다.** 묶음 안에서
                # 이어 푸는 답에는 빈 목록이라, 화면은 learning 이 오면
                # 학습을 보여주고 아니면 바로 다음 문제로 간다.
                "learning": (
                    [_word_body(w) for w in daily_study.learn_targets(studied)]
                    if not studied.is_done and daily_study.is_chunk_start(studied)
                    else []
                ),
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
        # 학습 진행. 화면이 "3묶음 중 2번째" 를 그린다.
        "chunk_size": study.chunk_size,
        "chunk_count": study.chunk_count,
        # 학습분을 지나면 마지막 묶음 번호에서 멈춘다. 안 막으면
        # answered 가 늘수록 계속 올라 화면이 "5/4묶음" 을 그린다.
        "chunk_index": (
            min(study.answered // study.chunk_size, max(study.chunk_count - 1, 0))
            if study.chunk_size
            else 0
        ),
    }


class StudyCardSerializer(QuizWordSerializer):
    """학습 카드 하나. 출제용 직렬화에 분류 이름만 더한다.

    **발음 게이트를 여기서 다시 쓰지 않는다.** reading 은 항목 검수와
    별개인 reading_reviewed 를 따르는데, 그 규칙은 ReviewedReadingField
    한 곳에만 두기로 한 것이다(vocab/models.py 의 visible() docstring 이
    "노출 게이트가 둘인 이유" 로 적어뒀다). 손으로 한 줄 더 쓰면 규칙이
    바뀔 때 이 자리만 남는다.

    상세 화면(WordDetailSerializer)이 아니라 출제용을 물려받는 이유는
    저기가 created_at 같은 관리용 칸까지 내려주기 때문이다.

    **description 은 물려받은 그대로 들어간다.** 카드에서는 접어두지만
    펼칠 때 왕복을 한 번 더 하면 그 순간 화면이 멈춘다 - 학습은 넘기는
    속도가 중요한 화면이다.
    """

    category_label = serializers.SerializerMethodField()

    class Meta(QuizWordSerializer.Meta):
        # category(코드)는 화면이 안 쓴다. 라벨만 준다.
        fields = [f for f in QuizWordSerializer.Meta.fields if f != "category"] + [
            "category_label"
        ]

    def get_category_label(self, word) -> str:
        return word.get_category_display() if word.category else ""


def _word_body(word: Word) -> dict:
    """학습 카드 하나."""
    return StudyCardSerializer(word).data


class ReviewStartView(APIView):
    """복습을 연다. GET 은 남은 개수만 본다.

    **로그인이 필요하다.** 무엇을 틀렸는지가 계정에 쌓여야 하는 기능이다.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReviewThrottle]

    def get(self, request: Request) -> Response:
        """복습할 것이 몇 개인가. 화면이 시작 버튼을 그릴지 정한다.

        **졸업 기준도 함께 내려준다.** 화면이 "한 번 더 맞히면 끝" 을
        띄우는데, 그 문구가 2 라는 숫자에 묶여 있다. 여기서 안 주면
        화면이 그 값을 따로 들고 있게 되고, 기준을 3 으로 올린 날
        화면만 옛말을 계속한다 - 틀렸다는 신호가 어디에도 안 뜬다.
        """
        return Response(
            {
                "due": review.count_due(request.user),
                "round_size": review.ROUND_SIZE,
                "graduate_streak": review.GRADUATE_STREAK,
            }
        )

    def post(self, request: Request) -> Response:
        try:
            token, question, total = review.start(request.user)
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {"token": token, "question": question, "total": total},
            status=status.HTTP_201_CREATED,
        )


class ReviewAnswerView(APIView):
    """복습 답 하나."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ReviewAnswerThrottle]

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
            result, next_token, question = review.answer(request.user, token, picked)
        except session.SessionError as exc:
            return _fail(exc)

        return Response(
            {
                "result": {
                    "correct": result.correct,
                    "streak": result.streak,
                    "graduated": result.graduated,
                    "answer_type": result.answer_type,
                    "answer_text": result.answer_text,
                    "answer_extra": result.answer_extra,
                },
                "token": next_token,
                "question": question,
                "finished": question is None,
            }
        )
