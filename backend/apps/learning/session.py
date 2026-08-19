"""한 판의 진행.

판 상태를 DB 가 아니라 **서명한 토큰**에 담아 오간다. 문제를 하나 낼 때마다
새 토큰을 내주고, 답이 올 때 그 토큰을 풀어 이어간다.

DB 를 안 쓰는 이유:
    - 로그인 안 한 사람도 문제를 푼다. 판마다 행을 만들면 누구든 무한히
      쓸 수 있는 쓰기 경로가 열린다.
    - 기록이 필요한 것은 **끝난 판**뿐이다. 중간 상태를 남길 이유가 없다.
    - 로그인 여부로 코드가 갈리지 않는다. 끝에서 한 번만 갈린다.

토큰은 위조할 수 없지만(서명) **되돌릴 수는 있다** - 옛 토큰을 저장해뒀다가
다시 보내면 그 지점부터 다시 진행된다. 이걸 막지 않으면 점수를 마음대로
만들 수 있다:

    1. 아무 보기나 골라 답을 보낸다 -> 응답이 정답을 알려준다
    2. 새로 받은 토큰을 버리고 **원래 토큰**을 정답과 함께 다시 보낸다
    3. 경과 시간은 원래 문제를 낸 시각부터 재므로 제한 시간 안이다 -> +1

넘기기 횟수도, 점수가 가장 높았던 시점을 골라 끝내는 것도 같은 방법이다.

그래서 판마다 순번(`n`)을 두고, 지나간 순번을 `RoundStep` 표에 남긴다.

    _take_step     순번을 **원자적으로** 가져간다(유일 제약). 읽고 나서
                   쓰면 동시에 온 요청이 전부 통과해, 보기를 네 개 동시에
                   보내고 맞은 것만 남기는 길이 열린다.
                   **실패할 수 있는 일을 다 끝낸 뒤에** 부른다 - 먼저
                   태우면 거절 한 번에 토큰과 표시가 어긋나 판이 죽는다.
    _check_replay  보기만 한다. 끝내기 전용이다.

표를 쓰는 이유는 `models.RoundStep` 에 적어뒀다 - 요약하면 캐시는 넘치면
스스로 지워서, 채우기만 하면 방어가 열린다.
"""

from __future__ import annotations

import logging
import random
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from .models import RoundStep

logger = logging.getLogger(__name__)

# 한 판의 길이. 모두 같아야 점수를 나란히 놓을 수 있어 고정한다.
ROUND_SECONDS = 90

# 판당 넘길 수 있는 횟수. 무제한이면 모르는 것을 전부 넘겨서 아무도
# 마이너스가 안 된다. 이 셋이 다 떨어지면 답을 골라야 다음으로 간다.
MAX_SKIPS = 3

# 점수. 제한 시간 안에 맞히면 +1, 지나서 맞히면 0, 틀리면 -1, 넘기면 0.
SCORE_IN_TIME = 1
SCORE_LATE = 0
SCORE_WRONG = -1
SCORE_SKIP = 0

# 판 토큰의 서명 용도. 문제 하나짜리 토큰(_SALT)과 달라야 한다 -
# 섞이면 한쪽에서 만든 것을 다른 쪽에서 풀 수 있다.
_SALT = "learning.session"

# 판 토큰 유효 시간(초). 90초짜리 판이니 10분이면 아주 넉넉하다.
# 이 값이 곧 되돌리기를 시도할 수 있는 창이고, RoundStep 행이 남는 기간이다.
TOKEN_MAX_AGE = 10 * 60

# 최근에 낸 문제를 다시 내지 않으려고 들고 있는 개수.
# 전부 들고 있으면 토큰이 길어지고, 90초에 30문제를 넘기기 어렵다.
RECENT_KEEP = 40

# 답 한 줄의 칸 수. 여기를 바꾸면 옛 모양의 토큰이 토큰 유효 시간만큼
# 들어온다. record 쪽도 이 값을 본다.
ANSWER_FIELDS = 7

# 한 판에서 받을 수 있는 답의 최대 개수. 90초에 200문제면 한 문제당
# 0.45초라 사람은 닿을 수 없다. 토큰이 무한정 길어지는 것을 막는 값이다.
MAX_ANSWERS = 200

# 판을 열 때 이 확률로 오래된 진행 표시를 지운다. 매번 지우면 낭비고,
# 놓쳐도 다음 판이 지운다. 판 50번에 한 번꼴이면 쌓일 틈이 없다.
_SWEEP_CHANCE = 0.02


class SessionError(Exception):
    """판을 이어갈 수 없다. 호출부가 400 으로 바꾼다."""


@dataclass
class Result:
    """답 하나의 채점 결과. 화면이 바로 그린다."""

    correct: bool
    skipped: bool
    in_time: bool
    score: int
    elapsed_ms: int
    # 정답이 무엇이었는지. 틀렸을 때 이걸 봐야 학습이 된다.
    answer_id: int
    answer_type: str
    answer_text: str
    answer_extra: str = ""


def new_token_id() -> str:
    return secrets.token_urlsafe(12)


def start(kind: str = "free") -> tuple[str, dict]:
    """판을 연다. (판 토큰, 첫 문제) 를 돌려준다."""
    now = timezone.now()
    state = {
        "id": new_token_id(),
        "k": kind,
        # 시작 시각(ms). 마감은 이 값 + 90초라 클라이언트가 늘릴 수 없다.
        "s": _ms(now),
        # 순번. 답을 하나 받을 때마다 오른다. 되돌리기 판별에 쓴다.
        "n": 0,
        "sk": 0,
        "a": [],
        "r": [],
        "rs": [],
    }
    # 문제를 못 만드는 경우와 엮지 않으려고 먼저 부른다. 아래에서 raise 가
    # 나면 콘텐츠가 전부 미검수인 상황인데, 그때 청소까지 멈출 이유가 없다.
    _sweep_old_steps()

    question = _issue(state, now)
    if question is None:
        raise SessionError("낼 수 있는 문제가 없습니다.")

    return _sign(state), question


def answer(
    token: str, picked_id: int | None, *, skip: bool = False
) -> tuple[str, Result, dict | None]:
    """답 하나를 채점하고 다음 문제를 낸다.

    돌려주는 것: (새 판 토큰, 채점 결과, 다음 문제 또는 None)
    다음 문제가 None 이면 판이 끝난 것이다.
    """
    state = _load(token)
    current = state.get("q")
    if not isinstance(current, dict):
        raise SessionError("진행 중인 문제가 없습니다.")

    if len(state["a"]) >= MAX_ANSWERS:
        raise SessionError("한 판에 풀 수 있는 문제를 다 풀었습니다.")

    now = timezone.now()
    elapsed_ms = max(0, _ms(now) - int(current.get("t", _ms(now))))

    if skip:
        if int(state["sk"]) >= MAX_SKIPS:
            raise SessionError("넘기기를 다 썼습니다.")
        state["sk"] = int(state["sk"]) + 1
        result = _skip_result(current, elapsed_ms)
    else:
        result = _grade(current, picked_id, elapsed_ms)

    # 방금 푼 답을 **다음 문제를 만들기 전에** 센다. 다음 문제에 실리는
    # answered 가 이 값을 보기 때문이다 - 뒤에 세면 화면 숫자가 영구히
    # 하나 뒤처진다. append 는 실패할 수 없어 순서를 바꿔도 안전하다.
    state["a"].append(
        [
            current["k"],
            current["tt"],
            result.answer_id,
            1 if result.correct else 0,
            1 if result.skipped else 0,
            elapsed_ms,
            result.score,
        ]
    )

    # 다음 문제를 **순번을 가져가기 전에** 만든다. _issue 는 DB 를 치므로
    # 실패할 수 있는데, 순번을 먼저 태우면 클라이언트 토큰은 그대로인 채
    # 표시만 남아 그 판의 이후 요청이 전부 막힌다.
    #
    # 마감이 지났으면 새 문제를 안 낸다. 이미 받은 문제의 답은 위에서
    # 세었다 - 마감 직전에 받은 문제를 마감 직후에 답했다고 버리면
    # 사용자 입장에서 억울하다.
    question = None if _ms(now) >= _deadline_ms(state) else _issue(state, now)

    # 여기서부터는 실패할 것이 없다. 순번을 가져가고 반드시 새 토큰을 낸다.
    _take_step(state)

    if question is None:
        state.pop("q", None)

    return _sign(state), result, question


def finish(token: str) -> dict:
    """판을 닫고 집계를 돌려준다. 기록은 호출부가 남긴다.

    끝낼 때도 되돌리기를 본다. 판 식별자의 유일 제약은 *같은 판을 두 번
    남기는 것* 만 막지, **가장 좋았던 시점의 토큰을 골라 내는 것** 은 못
    막는다 - 매 응답의 토큰을 모아뒀다가 +5 였던 시점 것으로 끝내면
    뒤에 틀린 -1 들이 없던 일이 된다. 그러면 오답 감점이 선택 사항이 된다.

    여기서는 검사만 하고 순번을 태우지 않는다. 끝내기는 여러 번 와도
    되고(같은 결과), 태우면 정상 재시도가 막힌다.
    """
    state = _load(token)
    _check_replay(state)
    answers = _sound_answers(state["a"])

    return {
        "token_id": state["id"],
        "kind": state["k"],
        "started_at": _dt(state["s"]),
        "score": sum(int(a[6]) for a in answers),
        "answered": len(answers),
        "correct": sum(1 for a in answers if a[3]),
        "skipped": sum(1 for a in answers if a[4]),
        "answers": answers,
        "skips_left": MAX_SKIPS - int(state["sk"]),
    }


# ---- 안쪽 ----


def _sound_answers(answers: list) -> list:
    """모양이 성한 답만 남긴다.

    판 상태가 토큰으로 오간다. 답의 칸 수를 바꾼 배포 직후에는 옛 모양의
    토큰이 토큰 유효 시간만큼 들어오는데, 칸이 **모자란** 쪽이면 집계에서
    IndexError 로 500 이 난다. record 쪽에도 같은 거름망이 있지만 그건
    로그인한 사람만 지나는 길이라, 집계 자체가 먼저 터지면 소용이 없다.
    """
    sound = [
        a
        for a in answers
        if isinstance(a, (list, tuple)) and len(a) == ANSWER_FIELDS
    ]
    if len(sound) != len(answers):
        # record 쪽에도 같은 거름망이 있지만 여기서 먼저 걸러 그쪽 로그가
        # 안 찍힌다. 배포 직후 옛 토큰이 얼마나 들어오는지 볼 신호다.
        logger.warning(
            "모양이 다른 답 %d개를 집계에서 뺐습니다.", len(answers) - len(sound)
        )
    return sound


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.get_current_timezone())


def _deadline_ms(state: dict) -> int:
    return int(state["s"]) + ROUND_SECONDS * 1000


def _check_replay(state: dict) -> None:
    """옛 토큰을 다시 보낸 것이면 막는다. **상태를 바꾸지 않는다.**

    끝내기 전용이다. 답하기 쪽은 _take_step 이 같은 것을 원자적으로 하니
    여기서 미리 볼 이유가 없다(조회만 한 번 더 늘 뿐이다).
    """
    if RoundStep.objects.filter(
        round_id=state["id"], step=int(state.get("n", 0))
    ).exists():
        raise SessionError("이미 지난 문제입니다. 최신 화면에서 다시 풀어주세요.")


def _take_step(state: dict) -> None:
    """이 순번을 이 요청이 가져간다. 동시에 와도 하나만 성공한다.

    원자성은 RoundStep 의 유일 제약에서 나온다. 읽고 나서 쓰는 방식으로는
    못 막는다 - 같은 토큰으로 보기 네 개를 동시에 보내면 넷 다 같은 값을
    읽고 넷 다 통과해서, 정답을 몰라도 맞은 응답의 토큰만 남기면 된다.

    바깥 트랜잭션을 안 깨려고 savepoint 를 쓴다. IntegrityError 는 여기서
    잡아 400 으로 바꿀 것이고, 그대로 두면 바깥이 통째로 롤백된다.
    """
    seq = int(state.get("n", 0))
    try:
        with transaction.atomic():
            RoundStep.objects.create(round_id=state["id"], step=seq)
    except IntegrityError:
        logger.info("되돌리기를 거절했습니다. round=%s step=%s", state["id"], seq)
        raise SessionError("이미 처리한 답입니다. 최신 화면에서 다시 풀어주세요.")

    state["n"] = seq + 1


def _sweep_old_steps() -> None:
    """수명이 다한 진행 표시를 지운다.

    토큰이 만료되면 그 판의 표시는 쓸모가 없다 - 토큰 자체가 거부된다.
    매번 지우면 낭비라 가끔만 한다. 놓쳐도 다음 판이 지우므로 정확할
    필요가 없고, 안 지워져도 방어가 열리지는 않는다(캐시와 다른 점이다).
    """
    if random.random() >= _SWEEP_CHANCE:
        return

    cutoff = timezone.now() - timedelta(seconds=TOKEN_MAX_AGE)
    RoundStep.objects.filter(created_at__lt=cutoff).delete()


def _sign(state: dict) -> str:
    return signing.dumps(state, salt=_SALT)


def _load(token: str) -> dict:
    try:
        state = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise SessionError("판 정보가 올바르지 않습니다. 새로 시작해주세요.") from exc

    # 서명이 맞아도 모양까지 맞다는 보장은 없다. 옛 형식이 남아 있을 수도
    # 있고, 우리 코드가 잘못 만들었을 수도 있다.
    if not isinstance(state, dict):
        raise SessionError("판 정보가 올바르지 않습니다. 새로 시작해주세요.")
    for key, kind in (("id", str), ("k", str), ("s", int), ("sk", int), ("a", list)):
        if not isinstance(state.get(key), kind) or isinstance(state.get(key), bool):
            raise SessionError("판 정보가 올바르지 않습니다. 새로 시작해주세요.")
    state.setdefault("r", [])
    state.setdefault("rs", [])
    # 순번은 나중에 생긴 값이라 없을 수 있다(배포 직전에 시작한 판).
    # 그 판은 RoundStep 표에도 기록이 없어 0 부터 세도 문제되지 않는다.
    if not isinstance(state.get("n"), int) or isinstance(state.get("n"), bool):
        state["n"] = 0
    return state


def _issue(state: dict, now: datetime) -> dict | None:
    """다음 문제를 만들어 판 상태에 심는다. 못 만들면 None."""
    question = _make(state)
    if question is None:
        return None

    payload = quiz.answer_payload(question.answer_id, [c.id for c in question.choices])
    state["q"] = {
        **payload,
        "k": question.kind,
        "tt": question.answer_type,
        # 이 문제를 낸 시각. 서버 시계다 - 클라이언트가 잰 값을 받으면
        # 0 을 보내 항상 제한 시간 안이 된다.
        "t": _ms(now),
        "l": question.time_limit_ms,
    }

    # 방금 낸 것을 기억해 연달아 같은 문제가 나오지 않게 한다.
    if question.answer_type == quiz.TARGET_WORD:
        state["r"] = ([question.answer_id] + list(state["r"]))[:RECENT_KEEP]
    else:
        state["rs"] = ([question.answer_id] + list(state["rs"]))[:RECENT_KEEP]
    if question.source_sentence_id is not None:
        state["rs"] = ([question.source_sentence_id] + list(state["rs"]))[:RECENT_KEEP]

    return {
        "kind": question.kind,
        "kind_label": question.kind_label,
        "question": question.question,
        "prompt": question.prompt,
        "choices": [asdict(c) for c in question.choices],
        "category": question.category,
        "category_label": question.category_label,
        "time_limit_ms": question.time_limit_ms,
        "skips_left": MAX_SKIPS - int(state["sk"]),
        "deadline_ms": _deadline_ms(state),
        "answered": len(state["a"]),
    }


def _make(state: dict) -> quiz.Question | None:
    """유형을 골라 문제를 만든다. 판 상태에서 최근 목록을 꺼내 넘긴다."""
    return make_question(list(state["r"]), list(state["rs"]))


def make_question(
    recent_words: list[int], recent_sentences: list[int]
) -> quiz.Question | None:
    """유형을 골라 문제를 만든다.

    문장 문제를 섞는 비율을 고정하지 않고 매번 뽑는다. 순서를 정해두면
    "세 번째는 문장" 처럼 패턴을 외운다.

    문장 문제를 못 만드는 경우가 정상 흐름이라(빈칸으로 만들 수 있는
    문장이 절반쯤이다) 실패하면 단어 문제로 떨어진다.
    """
    words = Word.objects.visible()
    sentences = Sentence.objects.visible()

    kind = random.choice(quiz.QuizKind.ALL)

    if kind == quiz.QuizKind.BLANK:
        made = quiz.make_blank_question(sentences, words, recent_sentences)
        if made is not None:
            return made
    elif kind == quiz.QuizKind.SITUATION:
        made = quiz.make_situation_question(sentences, recent_sentences)
        if made is not None:
            return made
    else:
        made = quiz.make_question(words, kind, recent_words)
        if made is not None:
            return made

    # 못 만들었으면 남은 단어 유형을 하나씩 다 해본다.
    #
    # 유형마다 낼 수 있는 조건이 다르다. 설명 문제는 설명이 있는 단어만
    # 쓸 수 있는데(description 은 blank=True) 설명 없는 단어만 있으면 못
    # 만든다. 여기서 포기하면 _issue 가 None 이 되어 **마감 전인데 판이
    # 통째로 끝난다** - 사용자는 "왜 30초 만에 끝났지" 를 본다.
    #
    # 무작위로 한 번 더 뽑지 않고 전부 도는 이유: 한 번 더 뽑아봐야 같은
    # 유형이 걸리면 또 실패한다. 될 때까지 확실히 훑는다.
    # 순서를 섞는 이유: 고정 순서로 돌면 첫 후보가 거의 항상 성공해서
    # 폴백이 도는 상황(문장이 없는 DB 등)에서는 유형이 그것 하나로 쏠린다.
    # 같은 유형이 이어지면 답이 아니라 패턴을 외우게 된다.
    for fallback in random.sample(
        quiz.QuizKind.WORD_KINDS, len(quiz.QuizKind.WORD_KINDS)
    ):
        if fallback == kind:
            continue  # 위에서 이미 해봤다
        made = quiz.make_question(words, fallback, recent_words)
        if made is not None:
            return made

    return None


def _grade(current: dict, picked_id: int | None, elapsed_ms: int) -> Result:
    graded = quiz.resolve_answer(current, picked_id if picked_id is not None else -1)
    if graded is None:
        raise SessionError("문제 정보가 올바르지 않습니다. 새로 시작해주세요.")

    correct, answer_id = graded
    in_time = elapsed_ms <= int(current.get("l", 0))

    if not correct:
        score = SCORE_WRONG
    elif in_time:
        score = SCORE_IN_TIME
    else:
        score = SCORE_LATE

    text, extra = _describe(current["tt"], answer_id)
    return Result(
        correct=correct,
        skipped=False,
        in_time=in_time,
        score=score,
        elapsed_ms=elapsed_ms,
        answer_id=answer_id,
        answer_type=current["tt"],
        answer_text=text,
        answer_extra=extra,
    )


def _skip_result(current: dict, elapsed_ms: int) -> Result:
    """넘긴 경우. 정답은 알려준다 - 넘긴 것도 학습이 되어야 한다."""
    graded = quiz.resolve_answer(current, -1)
    if graded is None:
        raise SessionError("문제 정보가 올바르지 않습니다. 새로 시작해주세요.")

    _, answer_id = graded
    text, extra = _describe(current["tt"], answer_id)
    return Result(
        correct=False,
        skipped=True,
        in_time=False,
        score=SCORE_SKIP,
        elapsed_ms=elapsed_ms,
        answer_id=answer_id,
        answer_type=current["tt"],
        answer_text=text,
        answer_extra=extra,
    )


def _describe(target_type: str, target_id: int) -> tuple[str, str]:
    """정답을 화면에 보여줄 글자로.

    visible() 로 좁히는 이유: 문제를 낸 뒤 검수가 취소됐을 수 있다.
    아무도 확인하지 않은 내용을 정답이라고 알려주면 그대로 잘못 외운다.

    모르는 종류를 단어로 떨어뜨리지 않는 이유: 에러 메시지나 아티클이
    붙으면 그때 id 가 같은 **엉뚱한 단어**를 정답이라고 띄운다. 그럴듯한
    단어가 나와서 한참 모르고, 타겟이 영어 약한 주니어라 잘못 외우면
    되돌리기 어렵다. 차라리 빈 값을 내보내 화면에서 티가 나게 한다.
    """
    if target_type == quiz.TARGET_WORD:
        found = Word.objects.visible().filter(pk=target_id).first()
        return (found.term, found.meaning) if found else ("", "")

    if target_type == quiz.TARGET_SENTENCE:
        found = Sentence.objects.visible().filter(pk=target_id).first()
        return (found.context, found.translation) if found else ("", "")

    logger.warning("모르는 정답 종류입니다. target_type=%s", target_type)
    return ("", "")
