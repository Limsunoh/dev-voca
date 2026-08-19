"""일일공부 한 판.

자유 문제풀이(session.py)와 규칙이 다르다.

    제한 시간   없다. 천천히 풀어도 손해가 없어야 매일 온다
    감점        없다. 맞히면 +1, 틀리면 0
    끝나는 조건 시간이 아니라 **문제 수**. 길이를 고를 때 정해진다
    하루        한 번. 이미 했으면 결과만 본다

## 왜 DB 를 쓰나

자유 문제풀이는 판 상태를 전부 서명 토큰에 담고 끝낼 때 한 번 기록한다.
그래도 되는 이유는 그날 점수가 **최고 한 판**이라, 나쁜 판을 버리든 남기든
결과가 같기 때문이다.

일일공부는 **더하기**다. 그래서 같은 구조로 만들면 점수가 깎이는 판을
중간에 버리는 것이 이득이 된다 - "마음에 안 들면 새로 시작" 이 열린다.
record.py 첫머리가 이 위험을 경고해뒀다.

그래서 **답할 때마다 DB 에 쌓는다.** 나가도 푼 만큼 남고, 다시 들어와도
그 줄을 이어 본다. 하루 한 번은 (user, day) 유일 제약이 지킨다 - 코드로
검사하면 동시에 두 번 시작하는 경로가 열린다.

## 토큰은 여전히 쓴다

현재 문제와 최근에 낸 목록은 토큰에 담는다. 그 둘은 한 문제를 주고받는
동안만 필요하고, DB 에 넣으면 답마다 쓰기가 두 번이 된다.

토큰만으로는 **부족하다.** 진행 개수가 DB 에 있으니 옛 토큰을 보내도
answered 가 뒤로 가지는 않지만, 공격자가 원하는 것은 그게 아니다 -
**correct 를 올리는 것**이다. 첫 답의 응답이 정답을 알려주므로, 같은
토큰에 그 답을 실어 다시 보내면 확실히 +1 이다. 문제 수로 끝나는 규칙이라
절반만 탐색해도 만점이 된다.

그래서 순번(step)을 DailyStudy 에 두고 **답 하나가 그것을 원자적으로
가져간다**. 조건부 UPDATE 한 문장이 채점 반영과 소비를 함께 한다 -
읽고 나서 쓰면 동시에 온 요청이 전부 통과한다.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import calendar_kst
from .models import STUDY_PLANS, DailyStudy
from .record import add_daily_study
from .session import RECENT_KEEP, SessionError, _describe, make_question

logger = logging.getLogger(__name__)

# 문제 토큰의 서명 용도. 판 토큰(session._SALT)과 달라야 섞이지 않는다.
_SALT = "learning.daily_study"

# 토큰 유효 시간(초). 제한 시간이 없는 공부라 넉넉히 둔다 - 한 문제를
# 붙잡고 사전을 찾아봐도 만료되면 안 된다.
TOKEN_MAX_AGE = 6 * 60 * 60


@dataclass
class Answered:
    """답 하나의 결과. 화면이 그대로 그린다."""

    correct: bool
    score: int
    answer_type: str
    answer_text: str
    answer_extra: str


def plan_of(length: str) -> tuple[int, int]:
    """길이에 맞는 (문제 수, 완주 보너스). 모르는 길이면 거절한다."""
    plan = STUDY_PLANS.get(length)
    if plan is None:
        raise SessionError("모르는 길이입니다.")
    return plan


def today_of(user) -> DailyStudy | None:
    """오늘 줄. 아직 시작 안 했으면 None.

    **하루 한 번 판정과 화면 표시에만 쓴다.** 답할 때 이걸로 판을 고르면
    안 된다 - 자정을 넘긴 판이 오늘 날짜로 안 잡혀 토큰이 통째로 죽는다.
    답하기는 토큰이 지목한 판(_study_of_token)을 쓴다.
    """
    return DailyStudy.objects.filter(user=user, day=calendar_kst.today()).first()


def settle_stale(user) -> None:
    """어제 못 끝낸 판을 닫는다.

    안 닫으면 영원히 열린 채 남아 완주 보너스를 못 받는다 - 40문제를
    다 풀고 자정만 넘겼어도 마지막 답이 _finish 에 닿을 방법이 없다.

    **오늘 것을 보거나 시작할 때 부른다.** 시작할 때만 부르면 며칠 안
    들어온 사람의 판이 계속 열려 있다.

    **하나가 아니라 전부를 돈다.** 지금은 (user, day) 유일 제약과 start
    의 선행 정산 덕에 열린 판이 둘이 될 수 없어서 사실상 한 줄만 돈다.
    그 전제가 깨져도(정산을 건너뛰는 경로가 생기면) 조용히 남지 않게
    조건을 직접 건다 - "최근 하나" 를 집으면 나머지가 영영 열려 있다.

    점수는 이미 _publish 로 그날 줄에 가 있으므로 여기서 잃는 것은
    완주 보너스뿐이고, 완주했다면 애초에 _take_step 이 닫았을 것이다.
    """
    stale = DailyStudy.objects.filter(
        user=user,
        finished_at__isnull=True,
        day__lt=calendar_kst.today(),
    )
    for study in stale:
        _finish(study)


def _study_of_token(user, state: dict) -> DailyStudy:
    """토큰이 지목한 판. 남의 판은 못 집는다.

    **토큰이 자기 판을 밝혀야 한다.** 날짜로 찾으면 자정에 죽고, "열린 것
    중 최근" 으로 찾으면 판이 둘일 때 어긋난다 - 어제 토큰의 순번이 오늘
    판의 순번과 우연히 같으면 어제 문제의 답이 오늘 판에 세어진다.

    user 를 함께 거는 것이 중요하다. pk 만 보면 남의 판에 답할 수 있다.
    """
    study_id = state.get("sid")
    if not isinstance(study_id, int) or isinstance(study_id, bool):
        raise SessionError("문제 정보가 올바르지 않습니다.")

    study = DailyStudy.objects.filter(pk=study_id, user=user).first()
    if study is None:
        raise SessionError("진행 중인 일일공부가 없습니다.")
    return study


def start(user, length: str) -> tuple[DailyStudy, str, dict]:
    """오늘 일일공부를 연다. (줄, 문제 토큰, 첫 문제)

    이미 오늘 시작했으면 SessionError. 화면은 그때 today_of 로 결과를
    보여준다 - 여기서 그 줄을 돌려주면 "시작했다" 와 "이미 했다" 를
    호출부가 구분해야 해서 실수하기 쉽다.
    """
    total, bonus = plan_of(length)

    settle_stale(user)

    # **문제를 먼저 만든다.** 행을 만든 뒤 실패하면 지워야 하는데, 그
    # 사이에 다른 요청이 그 줄을 보면 "이미 시작했다" 를 듣고 되돌아온다.
    # 문제 만들기는 DB 읽기뿐이라 순서를 바꿔도 잃는 것이 없다.
    # (session.start 도 같은 순서다.)
    if make_question([], []) is None:
        raise SessionError("낼 수 있는 문제가 없습니다.")

    total = min(total, _answerable())

    try:
        with transaction.atomic():
            study = DailyStudy.objects.create(
                user=user,
                day=calendar_kst.today(),
                length=length,
                total_questions=total,
                bonus=bonus,
            )
    except IntegrityError:
        # (user, day) 유일 제약. 동시에 두 번 눌러도 하나만 만들어진다.
        raise SessionError("오늘 일일공부는 이미 시작했습니다.") from None

    token, question = _next_question(study, [], [])
    if question is None:
        # 위에서 한 번 확인했으므로 여기 오는 것은 그 사이 콘텐츠가
        # 사라진 경우다. 줄은 남긴다 - 지우면 동시에 시작한 사람이
        # 거절당하고 아무 줄도 없는 상태가 된다.
        raise SessionError("낼 수 있는 문제가 없습니다.")

    return study, token, question


def answer(
    user, token: str, picked_id: int | None
) -> tuple[Answered, str | None, dict | None, DailyStudy]:
    """답 하나를 채점하고 다음 문제를 낸다.

    돌려주는 것: (채점 결과, 다음 문제 토큰, 다음 문제, 그 판)
    문제가 None 이면 공부가 끝난 것이다. 판을 함께 돌려주는 이유는
    호출부가 다시 찾으면 자정을 넘긴 경우 엉뚱한 것을 집기 때문이다.

    **채점보다 저장이 먼저다.** 순서를 바꾸면 저장이 실패했을 때 사용자는
    맞았다는 화면을 보는데 점수가 안 오른다.
    """
    state = _load(token)
    current = state["q"]

    study = _study_of_token(user, state)
    if study.is_done:
        raise SessionError("이 일일공부는 이미 끝났습니다.")

    graded = quiz.resolve_answer(current, picked_id if picked_id is not None else -1)
    if graded is None:
        raise SessionError("문제 정보가 올바르지 않습니다. 새로 시작해주세요.")

    correct, answer_id = graded
    # 감점이 없다. 모르는 것을 만나도 손해가 없어야 매일 온다.
    gained = 1 if correct else 0

    text, extra = _describe(current["tt"], answer_id)
    result = Answered(
        correct=correct,
        score=gained,
        answer_type=current["tt"],
        answer_text=text,
        answer_extra=extra,
    )

    # 토큰에 실린 순번. 이 값이 DB 와 맞아야 통과한다.
    done = _take_step(study, int(state["n"]), gained, correct)
    if done:
        return result, None, None, study

    study.refresh_from_db()
    token, question = _next_question(study, state.get("r", []), state.get("rs", []))
    if question is None:
        # 남은 문제가 있는데 못 만든다. 여기서 끝내지 않으면 사용자가
        # 다시는 못 끝낸다 - 오늘 줄이 영영 열린 채로 남는다.
        _finish(study)
        return result, None, None, study

    return result, token, question, study


# ---- 안쪽 ----


def _answerable() -> int:
    """지금 낼 수 있는 문제 수.

    출제가 최근 낸 정답을 후보에서 빼므로(RECENT_KEEP), 콘텐츠가 적으면
    도중에 후보가 바닥난다. 그때 판은 서버가 닫아주지만 **40문제를
    약속하고 30문제만 낸 꼴**이 된다 - 사용자는 왜 일찍 끝났는지 모른다.

    그래서 시작할 때 낼 수 있는 만큼으로 줄여 약속을 지킨다. 보너스는
    안 줄인다 - 콘텐츠가 적은 것은 사용자 잘못이 아니다.

    운영 DB 는 검수된 단어가 이 수를 훨씬 넘으므로 평소에는 아무 일도
    일어나지 않는다. 콘텐츠를 정리하거나 새 분류를 좁게 열 때를 위한
    안전판이다.
    """
    return Word.objects.visible().count() + Sentence.objects.visible().count()


def _take_step(study: DailyStudy, step: int, gained: int, correct: bool) -> bool:
    """이 순번을 가져가며 답을 쌓는다. 이걸로 다 풀었으면 True.

    **한 문장이어야 한다.** 순번 확인과 반영을 나누면 동시에 온 요청이
    전부 같은 값을 읽고 전부 통과한다 - 같은 토큰으로 보기 네 개를 보내
    맞은 것만 남기는 길이 열린다.

    조건 셋이 각각 다른 것을 막는다.

        step=step         옛 토큰 재사용. 이게 이 함수의 존재 이유다
        answered__lt=...  문제 수 초과. 마지막 문제에 두 답이 겹칠 때
        finished_at=null  끝난 뒤 들어온 답
    """
    updated = DailyStudy.objects.filter(
        pk=study.pk,
        step=step,
        answered__lt=F("total_questions"),
        finished_at__isnull=True,
    ).update(
        step=F("step") + 1,
        answered=F("answered") + 1,
        correct=F("correct") + (1 if correct else 0),
        score=F("score") + gained,
    )

    if not updated:
        logger.info("일일공부 되돌리기를 거절했습니다. study=%s step=%s", study.pk, step)
        raise SessionError("이미 처리한 답입니다. 최신 화면에서 다시 풀어주세요.")

    study.refresh_from_db()

    if study.answered < study.total_questions:
        # **여기서도 점수판에 옮긴다.** 안 그러면 끝낸 판만 DailyScore 에
        # 닿아, 중간에 그만둔 사람은 푼 만큼 쌓아뒀는데 순위표에서 0 이다.
        # "푼 만큼 남는다" 가 이 표까지만 참이면 기획이 반쪽이다.
        _publish(study)
        return False

    _finish(study)
    return True


def _publish(study: DailyStudy) -> None:
    """지금까지의 점수를 그날 줄에 옮긴다. 보너스는 아직 없다."""

    add_daily_study(study.user, study.day, study.score)


def _finish(study: DailyStudy) -> None:
    """오늘 공부를 닫고 점수를 하루 줄에 옮긴다.

    완주 보너스는 **다 풀었을 때만** 준다. 중간에 못 끝내고 문제가 떨어져
    닫히는 경우도 있어서 여기서 조건을 본다.
    """
    # **먼저 읽는다.** 보너스 판정이 호출부의 refresh 여부에 달리면,
    # 새 호출부 하나가 그걸 빠뜨렸을 때 보너스가 조용히 나가거나 안 나간다.
    study.refresh_from_db()

    bonus = study.bonus if study.answered >= study.total_questions else 0
    final = study.score + bonus

    closed = DailyStudy.objects.filter(
        pk=study.pk, finished_at__isnull=True
    ).update(score=final, finished_at=timezone.now())

    # **진 요청은 여기서 돌아간다.** 반환값을 안 보면 두 요청이 각자 계산한
    # final 로 add_daily_study 를 불러, DailyScore 가 DailyStudy 와 다른
    # 값을 갖는다. 어느 쪽이 남는지도 순서에 달렸다.
    if not closed:
        # 이미 다른 요청이 닫았다. 그쪽이 쓴 값을 읽어 인스턴스를 맞춘다 -
        # 호출부가 이걸 화면에 그리므로 낡은 상태를 들고 나가면 안 된다.
        study.refresh_from_db()
        return

    # DB 에 쓴 값을 인스턴스에도 반영한다. 호출부가 다시 읽지 않고
    # 이 인스턴스를 그대로 화면에 그린다.
    study.refresh_from_db()
    _publish(study)


def _next_question(
    study: DailyStudy, recent_words: list, recent_sentences: list
) -> tuple[str | None, dict | None]:
    """다음 문제를 만들어 토큰에 심는다. 못 만들면 (None, None)."""
    question = make_question(list(recent_words), list(recent_sentences))
    if question is None:
        return None, None

    payload = quiz.answer_payload(question.answer_id, [c.id for c in question.choices])

    if question.answer_type == quiz.TARGET_WORD:
        recent_words = ([question.answer_id] + list(recent_words))[:RECENT_KEEP]
    else:
        recent_sentences = ([question.answer_id] + list(recent_sentences))[:RECENT_KEEP]
    if question.source_sentence_id is not None:
        recent_sentences = (
            [question.source_sentence_id] + list(recent_sentences)
        )[:RECENT_KEEP]

    state = {
        "q": {**payload, "k": question.kind, "tt": question.answer_type},
        # 어느 판의 문제인지. 날짜로 찾으면 자정에 죽고, "열린 것 중
        # 최근" 으로 찾으면 판이 둘일 때 어긋난다.
        "sid": study.pk,
        # 이 문제에 답할 때 가져갈 순번. DB 의 step 과 맞아야 통과한다.
        "n": study.step,
        "r": recent_words,
        "rs": recent_sentences,
    }

    return _sign(state), {
        "kind": question.kind,
        "kind_label": question.kind_label,
        "question": question.question,
        "prompt": question.prompt,
        "choices": [asdict(c) for c in question.choices],
        "category": question.category,
        "category_label": question.category_label,
        "answered": study.answered,
        "total": study.total_questions,
    }


def _sign(state: dict) -> str:
    return signing.dumps(state, salt=_SALT, compress=True)


def _load(token: str) -> dict:
    try:
        state = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except signing.SignatureExpired:
        raise SessionError("문제가 만료되었습니다. 새로고침해주세요.") from None
    except signing.BadSignature:
        raise SessionError("문제 정보가 올바르지 않습니다.") from None

    if not isinstance(state, dict):
        raise SessionError("문제 정보가 올바르지 않습니다.")

    # 모양까지 본다. 배포로 토큰 구조가 바뀌면 옛 모양이 유효 시간만큼
    # 들어오는데(여기는 6시간이다), int() 가 밖에서 터지면 400 이 아니라
    # 500 이 나간다. session._load 도 같은 이유로 키마다 검사한다.
    for key in ("sid", "n"):
        value = state.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise SessionError("문제 정보가 올바르지 않습니다.")
    if not isinstance(state.get("q"), dict):
        raise SessionError("진행 중인 문제가 없습니다.")
    for key in ("r", "rs"):
        if not isinstance(state.get(key), list):
            raise SessionError("문제 정보가 올바르지 않습니다.")

    return state
