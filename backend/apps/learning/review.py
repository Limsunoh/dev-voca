"""틀린 것 다시 풀기.

**점수가 없는 판이다.** 순위표에 안 들어가고 DailyScore 도 안 건드린다.
정답을 이미 본 문제가 나오는 자리라 점수를 주면 아는 것만 골라 푸는 길이
열린다 - 그건 공부가 아니라 점수 채우기다. 대신 제한 시간도 없고 하루
횟수 제한도 없다. 이득이 없으니 막을 이유도 없다.

목록은 두 갈래에서 온다.

    틀린 것      마지막에 틀린 항목. 먼저 낸다 - 모르는 것부터 다룬다
    오래된 것    마지막으로 맞힌 지 7일이 지난 것. 틀린 것이 떨어지면 낸다

**연속 두 번 맞혀야 목록에서 빠진다.** 한 번으로 빼면 찍어서 맞힌 것이
그대로 졸업한다. 틀리면 연속이 0 으로 돌아간다.

**토큰 되돌리기를 막는다.** 점수가 없다고 방어까지 없어도 되는 것은
아니다 - 응답이 맞든 틀리든 정답을 알려주므로, 옛 토큰을 다시 보내면
보기를 훑어 정답을 알아낸 뒤 그 답으로 연속 2회를 채울 수 있다. 그러면
안 외운 단어가 복습 목록에서 조용히 사라진다. 이 기능이 지키는 유일한
것이 "무엇을 다시 볼지" 라 그게 곧 손해다.

막는 방법은 자유 문제풀이와 같다 - 판마다 식별자를 두고 지나간 순번을
session.RoundStep 에 남긴다. 표와 함수가 이미 있어 그대로 쓴다.

판 자체는 DB 에 안 남긴다. 점수가 없어 남길 것이 연속 횟수뿐이고,
그건 ReviewState 에 있다. 중간에 나가도 그때까지 맞힌 것은 반영돼 있다.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import timedelta

from django.core import signing
from django.db.models import Q
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from .models import ReviewState
from .session import SessionError, _describe, _take_step, new_token_id

logger = logging.getLogger(__name__)

# 한 판의 문제 수. 길이를 고르게 하지 않는다 - 모자랄 때는 있는 만큼만
# 내므로 고르게 해봐야 지킬 수 없는 약속이 된다.
ROUND_SIZE = 20

# 마지막으로 맞힌 지 이만큼 지나면 "오래된 것".
STALE_DAYS = 7

# 복습에서 이만큼 연속으로 맞히면 목록에서 빠진다.
GRADUATE_STREAK = 2

# 판 토큰과 문제 토큰이 섞이지 않게 한다. 다른 기능의 토큰을 넣어도
# 서명 확인에서 걸린다.
_SALT = "learning.review"
TOKEN_MAX_AGE = 60 * 60 * 6


@dataclass(frozen=True)
class Answered:
    """채점 결과. 화면이 그대로 그린다."""

    correct: bool
    streak: int
    graduated: bool
    answer_type: str
    answer_text: str
    answer_extra: str


def due_of(user) -> list[ReviewState]:
    """지금 복습할 것들. 틀린 것 먼저, 그다음 오래된 것.

    **정렬을 조건과 같은 순서로 둔다.** 목록을 뽑는 조건과 정렬이 갈리면
    화면이 "20개 남음" 이라 해놓고 다른 20개를 낸다.
    """
    return list(_due(user).order_by("-is_wrong", "last_correct_at", "pk")[:ROUND_SIZE])


def count_due(user) -> int:
    """복습할 것이 몇 개인가. 화면이 시작 전에 보여준다."""
    return _due(user).count()


def _due(user):
    """복습 대상 조건. 목록과 개수가 **같은 조건**을 써야 한다.

    갈리면 화면이 "3개 남음" 이라 해놓고 다른 것을 낸다.

    세 갈래다.

        틀린 것        is_wrong=True. 마지막에 틀렸다
        복습 중인 것   복습에서 한 번 맞혔지만 아직 두 번은 아닌 것
        오래된 것      마지막 정답이 STALE_DAYS 보다 오래됐거나 아예 없는 것

    **"복습 중" 과 "자유 문제풀이에서 맞힌 것" 을 가르는 것이 streak 이다.**
    둘 다 is_wrong=False 에 last_correct_at 이 최근이라 그것만으로는 못
    가른다. 자유 문제풀이는 streak 을 안 올리므로(0), 복습에서 한 번
    맞힌 것(1)만 여기 남는다.

    조건을 잘못 짜면 둘 중 하나가 깨진다.

    - streak__gte 를 통째로 빼면 복습에서 한 번 맞힌 것이 바로 졸업한다
    - streak__lt 를 그냥 넣으면 자유 문제풀이에서 방금 맞힌 것이(0) 곧장
      복습에 나온다
    """
    stale_before = timezone.now() - timedelta(days=STALE_DAYS)

    return ReviewState.objects.filter(user=user).filter(
        Q(is_wrong=True)
        | Q(last_correct_at__isnull=True)
        | Q(last_correct_at__lt=stale_before)
        # 복습을 시작해 한 번 맞힌 것. 두 번째를 맞혀야 끝난다.
        | Q(streak__gt=0, streak__lt=GRADUATE_STREAK)
    )


def start(user) -> tuple[str, dict, int]:
    """복습 판을 연다. (토큰, 첫 문제, 이 판의 문제 수)"""
    due = due_of(user)
    if not due:
        raise SessionError("복습할 것이 없습니다. 문제를 더 풀어보세요.")

    # **오래돼서 돌아온 것은 연속을 처음부터 센다.** 첫 사이클에서 이미
    # 2 를 채운 항목이 그 값을 들고 돌아오면 한 번만 맞혀도 곧장 재졸업해,
    # 두 번째 사이클부터 "연속 두 번" 이 사라진다.
    returning = [row.pk for row in due if row.streak >= GRADUATE_STREAK]
    if returning:
        ReviewState.objects.filter(pk__in=returning).update(streak=0)

    targets = [(row.target_type, row.target_id) for row in due]
    question, at = _question_at(targets, 0)
    if question is None:
        # 목록에는 있는데 하나도 못 냈다. 그 사이 검수에서 내려갔거나
        # 지워진 것들이다 - count_due 는 그것까지 세므로 화면이 "N개
        # 남음" 을 보여준 뒤 여기로 온다. 개수를 정확히 맞추려면 항목마다
        # 출제를 시도해봐야 해서 비싸다. 대신 문구를 갈라 "없다" 와
        # "지금은 못 낸다" 를 구분한다.
        raise SessionError("지금은 낼 수 있는 복습 문제가 없습니다.")

    token, body = _pack(user, new_token_id(), targets, at, question)
    return token, body, len(targets)


def answer(user, token: str, picked_id) -> tuple[Answered, str | None, dict | None]:
    """답 하나. (채점 결과, 다음 토큰, 다음 문제)

    마지막 문제였으면 다음 토큰과 문제가 None 이다.
    """
    state = _load(token)

    if state["u"] != user.pk:
        # 남의 토큰. 정답을 이미 본 문제로 내 연속 횟수를 올릴 수 있다.
        logger.info("남의 복습 토큰을 거절했습니다. user=%s", user.pk)
        raise SessionError("이 복습은 다른 계정의 것입니다.")

    graded = quiz.resolve_answer(state["q"], picked_id)
    if graded is None:
        # 알맹이가 망가진 토큰. SECRET_KEY 를 돌리면(무중단 배포의 표준)
        # 서명은 옛 키로 풀리는데 지문은 새 키로 계산돼 어느 보기와도 안
        # 맞는다. 그대로 언패킹하면 진행 중이던 복습이 전부 500 이다.
        raise SessionError("문제 정보가 올바르지 않습니다. 다시 시작해주세요.")

    correct, answer_id = graded
    target_type = state["q"]["tt"]

    # **채점 전에 순번을 태운다.** 이걸 안 하면 같은 토큰을 되돌려 보기를
    # 훑고, 알아낸 정답으로 연속 횟수를 채울 수 있다.
    _take_step(state)

    streak, graduated = _record(user, target_type, answer_id, correct)

    text, extra = _describe(target_type, answer_id)
    result = Answered(
        correct=correct,
        streak=streak,
        graduated=graduated,
        answer_type=target_type,
        answer_text=text,
        answer_extra=extra,
    )

    targets = [tuple(one) for one in state["t"]]

    # _take_step 이 state["n"] 을 이미 올려뒀다.
    question, at = _question_at(targets, int(state["n"]))
    if question is None:
        return result, None, None

    # **건너뛴 만큼을 순번에 반영한다.** _question_at 이 사라진 대상을
    # 지나치므로 그 전진분을 안 받으면, 다음 요청이 같은 자리에서 또
    # 건너뛰어 살아 있는 항목을 두 번 낸다.
    next_token, body = _pack(user, state["id"], targets, at, question)
    return result, next_token, body


# ---- 안쪽 ----


def _record(user, target_type: str, target_id: int, correct: bool) -> tuple[int, bool]:
    """이 항목의 복습 상태를 갱신한다. (연속 횟수, 졸업했나)

    **복습에서만 연속이 올라간다.** 자유 문제풀이의 정답으로 올리면
    정답을 안 보고 맞힌 것과 보고 맞힌 것이 섞인다 - 여기는 정답을 이미
    본 문제가 나오는 자리라 그 둘을 갈라야 목록이 의미를 갖는다.
    """
    row, _ = ReviewState.objects.get_or_create(
        user=user, target_type=target_type, target_id=target_id
    )

    if correct:
        # 상한을 둔다. 넘어가면 7일 뒤 돌아왔을 때 streak 이 이미 2 라
        # 한 번만 맞혀도 곧장 재졸업한다 - 두 번째 사이클부터 규칙이
        # 무너진다. 부호 없는 정수 상한(32767)도 같이 막힌다.
        row.streak = min(row.streak + 1, GRADUATE_STREAK)
        row.is_wrong = False
        row.last_correct_at = timezone.now()
    else:
        # 찍어서 한 번 맞힌 것이 졸업하지 않게, 틀리면 처음부터.
        row.streak = 0
        row.is_wrong = True

    row.save(update_fields=["streak", "is_wrong", "last_correct_at", "updated_at"])
    return row.streak, correct and row.streak >= GRADUATE_STREAK


def _question_at(targets: list, index: int) -> tuple[quiz.Question | None, int]:
    """목록의 index 번째 항목으로 문제를 만든다. 끝났으면 None.

    **대상이 사라졌으면 건너뛴다.** 목록을 뽑은 뒤 그 단어가 검수에서
    내려가거나 지워질 수 있다. 거기서 판을 끝내면 남은 문제를 못 푼다.
    """
    while index < len(targets):
        target_type, target_id = targets[index]
        question = _make_for(target_type, target_id)
        if question is not None:
            return question, index

        logger.info("복습 대상이 사라져 건너뜁니다. %s:%s", target_type, target_id)
        index += 1

    return None, index


def _make_for(target_type: str, target_id: int) -> quiz.Question | None:
    """이 항목을 정답으로 하는 문제 하나. 못 만들면 None.

    **검수 게이트를 여기서도 건다.** 목록은 지난 답에서 나오므로, 그 뒤
    검수에서 내려간 항목이 섞여 있을 수 있다.
    """
    if target_type == quiz.TARGET_WORD:
        target = Word.objects.visible().filter(pk=target_id).first()
        if target is None:
            return None
        return quiz.make_for_word(target, Word.objects.visible())

    target = Sentence.objects.visible().filter(pk=target_id).first()
    if target is None:
        return None
    return quiz.make_situation_question(Sentence.objects.visible(), answer=target)


def _pack(
    user, round_id: str, targets: list, index: int, question: quiz.Question
) -> tuple[str, dict]:
    """토큰과 화면용 문제를 만든다."""
    payload = quiz.answer_payload(question.answer_id, [c.id for c in question.choices])

    state = {
        # 누구의 판인가. 남의 토큰으로 내 연속 횟수를 올리는 것을 막는다.
        "u": user.pk,
        # 어느 판인가. 지나간 순번을 RoundStep 에 이 값으로 남긴다.
        "id": round_id,
        "q": {**payload, "k": question.kind, "tt": question.answer_type},
        "t": targets,
        "n": index,
    }

    body = {
        "kind": question.kind,
        "kind_label": question.kind_label,
        "question": question.question,
        "prompt": question.prompt,
        "choices": [asdict(c) for c in question.choices],
        "category": question.category,
        "category_label": question.category_label,
        "answered": index,
        "total": len(targets),
    }

    return signing.dumps(state, salt=_SALT), body


def _load(token: str) -> dict:
    """토큰을 푼다. 모양이 아니면 SessionError."""
    try:
        state = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except signing.SignatureExpired:
        raise SessionError("복습이 만료됐습니다. 다시 시작해주세요.") from None
    except signing.BadSignature:
        raise SessionError("판 정보를 읽을 수 없습니다.") from None

    if not isinstance(state, dict):
        raise SessionError("판 정보를 읽을 수 없습니다.")

    # bool 은 int 의 하위형이라 따로 뺀다.
    for key in ("u", "n"):
        value = state.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise SessionError("판 정보를 읽을 수 없습니다.")

    if not isinstance(state.get("id"), str) or not state["id"]:
        raise SessionError("판 정보를 읽을 수 없습니다.")

    if not isinstance(state.get("q"), dict) or not isinstance(state.get("t"), list):
        raise SessionError("판 정보를 읽을 수 없습니다.")

    # **알맹이 모양까지 본다.** 토큰 모양을 바꾼 배포 직후에는 옛 토큰이
    # 토큰 수명만큼 들어온다. 그대로 언패킹하면 ValueError 로 500 이다.
    if not isinstance(state["q"].get("tt"), str):
        raise SessionError("판 정보를 읽을 수 없습니다.")

    for one in state["t"]:
        if not isinstance(one, (list, tuple)) or len(one) != 2:
            raise SessionError("판 정보를 읽을 수 없습니다.")

    return state
