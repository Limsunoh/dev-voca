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
from .models import STUDY_PLANS, DailyStudy, ReviewState, StudyPlan
from .record import add_daily_study, bump_review_states
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


def plan_of(length: str) -> StudyPlan:
    """길이에 맞는 구성. 모르는 길이면 거절한다."""
    plan = STUDY_PLANS.get(length)
    if plan is None:
        raise SessionError("모르는 길이입니다.")
    return plan


def _fit_chunks(plan: StudyPlan, total: int, words: int) -> tuple[int, int]:
    """실제 문제 수에 맞춘 (묶음 크기, 묶음 수).

    콘텐츠가 적으면 total 이 계획보다 줄어든다(`min(plan.total,
    _answerable())`). 그때 묶음을 그대로 두면 **학습분 문제가 총 문제 수를
    넘는다** - 8개를 학습해놓고 문제가 5개면 세 묶음은 학습만 하고 문제가
    안 나온다.

    **단어 수로도 함께 자른다.** total 은 문장을 포함하는데(_answerable)
    학습은 단어만 뽑는다(_pick_for_study). 문장 100개 / 단어 6개인 DB 는
    total 이 안 줄어 4묶음(20단어)을 계획하지만 단어가 6개뿐이라 2묶음째
    부터 발급이 실패한다. 실패하면 issued_chunks 가 안 올라 그 뒤 슬라이스
    구간이 실제 발급분과 영영 어긋나고, 학습 카드를 보여준 묶음이 문제
    범위로 안 쓰인다.

    묶음 크기는 유지하고 개수만 줄인다. 크기를 줄이면 화면에 "이번엔
    2개" 라고 해놓고 다음 묶음에서 다르게 나온다.

    seed 만 넣은 DB 나 테스트에서 실제로 걸린다. 566개가 있는 운영에서는
    total 이 안 줄어 계획 그대로다.
    """
    if plan.chunk_size < 1:
        return 0, 0

    # 학습분이 total 을 넘지 않는 최대 묶음 수. 나머지는 전체에서 낸다.
    fits = min(total, words) // plan.chunk_size
    count = min(plan.chunk_count, fits)
    if count < 1:
        # 한 묶음도 못 채운다. 학습 없이 옛 방식으로 푼다 - 문제 수가
        # 묶음 크기보다 작은 판은 학습을 넣을 자리가 없다.
        return 0, 0
    return plan.chunk_size, count


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
    # pk 순으로 고정한다. **이것이 교착을 막지는 않는다** - 여기엔 행
    # 잠금이 없고 판마다 트랜잭션이 따로 돌아서, 한 트랜잭션이 여러 행을
    # 쥐는 상황 자체가 없다. Meta.ordering 으로 이미 결정적이기도 했다.
    #
    # Postgres 에서 관측한 교착의 실제 자리는 _publish 안쪽이다 -
    # add_daily_study 의 get_or_create 가 같은 (user, day) 로 동시에
    # INSERT 하면 유일 인덱스에서 서로를 기다린다. 답하기와 정산이 겹칠
    # 때 그 경합이 그대로 남아 있다.
    #
    # 그래도 순서를 적어두는 것은, 나중에 여기에 select_for_update 가
    # 붙었을 때 순서가 정의돼 있어야 하기 때문이다.
    stale = DailyStudy.objects.filter(
        user=user,
        finished_at__isnull=True,
        day__lt=calendar_kst.today(),
    ).order_by("pk")
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
    plan = plan_of(length)

    settle_stale(user)

    # **문제를 먼저 만든다.** 행을 만든 뒤 실패하면 지워야 하는데, 그
    # 사이에 다른 요청이 그 줄을 보면 "이미 시작했다" 를 듣고 되돌아온다.
    # 문제 만들기는 DB 읽기뿐이라 순서를 바꿔도 잃는 것이 없다.
    # (session.start 도 같은 순서다.)
    if make_question([], []) is None:
        raise SessionError("낼 수 있는 문제가 없습니다.")

    total = min(plan.total, _answerable(plan))
    chunk_size, chunk_count = _fit_chunks(
        plan, total, Word.objects.visible().count()
    )

    try:
        with transaction.atomic():
            study = DailyStudy.objects.create(
                user=user,
                day=calendar_kst.today(),
                length=length,
                total_questions=total,
                bonus=plan.bonus,
                chunk_size=chunk_size,
                chunk_count=chunk_count,
            )
    except IntegrityError:
        # (user, day) 유일 제약. 동시에 두 번 눌러도 하나만 만들어진다.
        raise SessionError("오늘 일일공부는 이미 시작했습니다.") from None

    # **첫 묶음을 먼저 뽑는다.** 안 뽑으면 learned_ids 가 비어 있어
    # 첫 문제가 전체에서 나온다 - 화면은 학습 카드를 보여주는데 문제는
    # 그것과 무관한 단어가 되어, 이 기능의 전제가 첫 문제부터 깨진다.
    issue_chunk(study)
    study.refresh_from_db()

    token, question = _next_question(study, [], [])
    if question is None:
        # 위에서 한 번 확인했으므로 여기 오는 것은 그 사이 콘텐츠가
        # 사라진 경우다. 줄은 남긴다 - 지우면 동시에 시작한 사람이
        # 거절당하고 아무 줄도 없는 상태가 된다.
        raise SessionError("낼 수 있는 문제가 없습니다.")

    return study, token, question


def resume(study: DailyStudy) -> tuple[str, dict] | None:
    """하다 만 판을 이어 풀 토큰과 문제를 만든다. 못 만들면 None.

    **이게 없으면 중간에 나간 사람이 오늘 판을 영영 못 끝낸다.** 답하려면
    토큰이 필요한데 토큰은 시작할 때와 답할 때만 나오고, 시작은 하루 한 번
    제약에 막힌다. 제한 시간이 없어 천천히 푸는 것이 이 기능의 의도라
    중간에 나가는 것은 예외가 아니라 흔한 경로다.

    되돌리기(옛 토큰 재사용)는 _take_step 이 막는다 - 순번을 DB 의 step
    에서 읽으므로 새 토큰이든 옛 토큰이든 조건이 같다.

    **하지만 그것만으로는 부족하다.** _take_step 은 "한 순번은 한 번만
    소비된다" 를 지킬 뿐 "한 순번에 문제는 하나다" 는 지키지 않는다.
    문제를 매번 새로 뽑아주면 순번을 소비하지 않고 문제만 갈아탈 수 있어,
    아는 것이 나올 때까지 화면을 다시 열면 된다. 그래서 발급한 문제를
    DailyStudy.question 에 저장해두고 여기서는 그것을 다시 서명만 한다.
    """
    if study.is_done:
        return None

    # **저장해둔 문제를 다시 서명해 내려준다.** 새로 뽑으면 순번을 소비
    # 하지 않고 문제만 바꾸는 길이 열린다 - 아는 것이 나올 때까지 화면을
    # 새로 열면 되므로 사실상 만점이다. _take_step 은 "한 순번은 한 번만
    # 소비된다" 만 지키지 그것까지 막지 못한다.
    saved = study.question
    if isinstance(saved, dict) and "state" in saved and "body" in saved:
        # **순번이 맞는 문제만 다시 낸다.** 뒤처진 문제를 그대로 다시
        # 서명해 주면 _take_step 이 영원히 거절해서, 화면을 아무리 새로
        # 열어도 "이미 처리한 답입니다" 만 나온다 - 하루 한 번 제약이라
        # 다시 시작할 수도 없어 그 사람의 오늘이 끝난다.
        #
        # **이것은 예외 상황 전용이 아니다.** 마지막 답은 다음 문제를
        # 안 심으므로 저장분이 한 순번 뒤처진 채 판이 닫힌다 - 정상
        # 흐름에서 매판 한 번씩 지나간다. 그때는 _finish 가 question 을
        # 비워서 위 is_done 검사에 먼저 걸리고, 이 분기는 그 닫기가
        # 실패했을 때의 그물이다.
        #
        # 여기서 새로 뽑아도 문제 갈아타기는 안 열린다. 갈아타려면 답을
        # 해야 하는데, 순번이 어긋난 문제로는 애초에 답이 안 된다.
        stale_step = saved.get("state", {}).get("n") != study.step
        if not stale_step and _still_visible(saved):
            body = {**saved["body"], "answered": study.answered}
            return _sign(saved["state"]), body

        # 저장한 뒤 검수가 취소됐거나 지워졌다. 그대로 내보내면 아무도
        # 확인하지 않은 내용을 정답이라고 알려주게 된다(_describe 가 같은
        # 이유로 낼 때마다 visible() 을 다시 건다). 새로 뽑는다 - 문제를
        # 갈아탈 수 있게 되지만, 그건 검수가 실제로 바뀐 판에서만이고
        # 미검수 노출보다 작은 값이다.
        if stale_step:
            logger.warning(
                "저장된 문제의 순번이 어긋나 새로 냅니다. study=%s 저장=%s DB=%s",
                study.pk,
                saved.get("state", {}).get("n"),
                study.step,
            )
        else:
            logger.info("보기가 더는 보이지 않아 새로 냅니다. study=%s", study.pk)
    else:
        # 저장된 것이 없다. 이 칸이 생기기 전에 시작한 판이거나 저장에
        # 실패한 경우다. 새로 뽑되 그때 저장되므로 다음부터는 고정된다.
        #
        # **위 분기 밖에 두면 안 된다.** 이 폴백은 화면에 보인 카드와 다른
        # 단어로 문제가 나가는 자리라 로그가 유일한 관측 수단인데, 밖에
        # 두면 다른 이유로 내려온 경우에도 "저장된 문제가 없다" 를 덧붙여
        # 세 원인이 로그에서 안 갈린다.
        logger.info("저장된 문제가 없어 새로 냅니다. study=%s", study.pk)

    # 여기서도 묶음을 먼저 뽑는다. start·answer 와 같은 이유다.
    issue_chunk(study)
    study.refresh_from_db()

    token, question = _next_question(study, [], [])
    if question is None:
        # **여기서 판을 닫는다.** 안 닫으면 화면이 길이 고르기로 떨어지는데,
        # 하다 만 판이 있으면 거기서 길이 버튼도 막혀 있어 아무것도 못 하는
        # 상태가 된다. 다시 열 방법도 없다 - 시작은 하루 한 번 제약에 막힌다.
        #
        # answer() 는 같은 상황에서 이미 이렇게 한다. 이쪽만 안 하고
        # 있었다.
        logger.warning("이어 풀 문제를 못 만들어 판을 닫습니다. study=%s", study.pk)
        _finish(study)
        return None
    return token, question


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
    # **채점과 복습 갱신을 한 트랜잭션으로 묶는다.** 따로 커밋하면
    # 순번을 가져간 뒤 복습 쓰기가 실패했을 때 점수만 오르고 그 답은
    # 복습에 영영 안 뜬다 - 순번은 이미 소비돼서 재시도도 "이미 처리한
    # 답입니다" 로 막힌다. 그 한 문제는 복구할 방법이 없다.
    #
    # _take_step 의 조건부 UPDATE 는 트랜잭션과 무관하게 원자적이라
    # 감싸도 순번 보호가 약해지지 않는다. start() 도 같은 관용구다.
    #
    # **점수판 반영은 이 안에 안 넣는다.** 저기는 (user, day) 유일
    # 인덱스를 잡아서, 트랜잭션 안에서 잡으면 복습 갱신이 끝날 때까지
    # 그 락을 쥔다 - 답하기와 어제 판 정산이 겹치면 서로를 기다린다.
    # **다음 문제 심기까지 이 안에서 끝낸다.** 채점과 복습이 함께
    # 되돌려져야 하는데(위), 그 롤백 범위 안에 다음 문제까지 넣어야
    # 순번과 저장된 문제가 항상 같은 값을 가리킨다. 순번만 먼저 커밋하면
    # 그 사이에 들어온 새로고침이 한 순번 뒤처진 저장 문제를 보게 되고,
    # 그 상태를 어떻게 다루든(새로 뽑든 그대로 주든) 판정이 갈린다.
    #
    # **다만 "같은 순번에 토큰이 둘" 을 막는 것은 이 트랜잭션이 아니다.**
    # 그건 resume 이 저장된 문제를 다시 서명해 주는 것(위 docstring)이
    # 막는다 - 창 안에서 읽어도 같은 행을 읽으므로 정답이 같다. 창을
    # 없애는 것은 그 위의 안전망이지 유일한 방어가 아니다. 좁히면
    # 롤백이 깨지므로(test_a_failed_review_write_rolls_back_the_score)
    # 이 범위는 유지해야 한다.
    #
    # 안에 있는 것은 전부 DB 읽기와 이 판에 대한 쓰기뿐이라, 다른
    # 사용자의 행을 잡지 않는다.
    with transaction.atomic():
        done = _take_step(study, int(state["n"]), gained, correct)

        # **복습 상태를 갱신한다.** 순번을 가져간 뒤에 한다 - 거절당한 답
        # (되돌리기)이 복습에 반영되면 옛 토큰으로 is_wrong 을 지울 수 있다.
        #
        # 여기가 없으면 하루의 주 활동에서 틀린 것이 복습에 안 뜬다. 자유
        # 문제풀이만 복습을 채우는데, 일일공부만 하는 사람이 더 많다.
        bump_review_states(user, {(current["tt"], answer_id): correct})

        token, question = None, None
        if not done:
            # **다음 묶음을 먼저 뽑는다.** 안 뽑으면 learned_ids 가 비어
            # 있어 _study_scope 가 None 을 주고, 방금 본 것이 아니라
            # 전체에서 문제가 나온다.
            issue_chunk(study)
            study.refresh_from_db()

            token, question = _next_question(
                study, state.get("r", []), state.get("rs", [])
            )

    # **점수판은 커밋 뒤에 옮긴다.** 저기는 (user, day) 유일 인덱스를
    # 잡아서, 트랜잭션 안에서 잡으면 답하기와 어제 판 정산이 서로를
    # 기다린다(settle_stale 주석에 관측 기록이 있다).
    #
    # 중간에 그만둔 사람도 푼 만큼 순위표에 남아야 해서 매 답마다
    # 옮긴다. 여기서 실패해도 점수가 영영 뒤처지지는 않는다 -
    # add_daily_study 가 더 높은 점수로만 갱신하므로 다음 답이 따라잡고,
    # 다음 문제는 위에서 이미 심겨 커밋됐다.
    if done or question is None:
        # 남은 문제가 있는데 못 만드는 경우도 여기로 온다. 안 닫으면
        # 사용자가 다시는 못 끝낸다 - 오늘 줄이 영영 열린 채로 남는다.
        _finish(study)
        return result, None, None, study

    _publish(study)
    return result, token, question, study


# ---- 학습 ----


def _now_chunk(study: DailyStudy) -> int | None:
    """지금 순번이 속한 묶음 번호. 학습분 밖이면 None.

    같은 판정을 is_chunk_start / issue_chunk / _study_scope 세 곳이 쓴다.
    복붙해두면 chunk_count 규칙을 바꿀 때 한 곳을 빠뜨린다.
    """
    if study.chunk_size < 1 or study.is_done:
        return None

    now_chunk = study.answered // study.chunk_size
    if now_chunk >= study.chunk_count:
        return None  # 학습분을 지났다. 남은 문제는 전체에서 낸다
    return now_chunk


def is_chunk_start(study: DailyStudy) -> bool:
    """지금이 묶음의 첫 문제 자리인가. 화면이 학습을 보여줄 자리다.

    묶음 안에서 이어 푸는 중이면 False - 그때 카드를 다시 띄우면 방금
    본 것을 또 보게 되고, 문제 사이에 학습이 끼어드는 것으로 읽힌다.
    """
    if _now_chunk(study) is None:
        return False

    return study.answered % study.chunk_size == 0


def learn_targets(study: DailyStudy) -> list[Word]:
    """지금 묶음에서 학습할 단어들. 학습할 차례가 아니면 빈 목록.

    **순번(step) 체계 밖에 있다.** 학습은 점수에 영향이 없어서 되돌리기를
    막을 이유가 없고, _take_step 의 원자적 소비에 끼워 넣으면 "학습을
    소비했나" 라는 상태가 하나 더 늘어 조건이 복잡해진다.

    대신 learned_ids 의 길이로 진행을 센다. 이미 뽑아둔 묶음이면 그것을
    그대로 돌려준다 - 화면을 새로 열 때마다 다른 단어가 나오면 방금 본
    것과 문제가 어긋난다.
    """
    ids = _study_scope(study)
    return _words_in_order(ids) if ids else []


def issue_chunk(study: DailyStudy) -> list[Word]:
    """다음 묶음을 뽑아 저장하고 돌려준다. 뽑을 것이 없으면 빈 목록.

    이미 그 묶음을 뽑아뒀으면 저장된 것을 그대로 준다.

    **판정을 issued_chunks 로 한다.** learn_targets 가 비었는지로 보면
    안 된다 - 저기는 visible() 을 거치므로, 뽑아둔 단어가 미검수로
    내려가면 "아직 안 뽑았다" 로 오판해 GET 마다 새 묶음을 이어붙인다.
    실제로 그렇게 새로고침 여섯 번에 계획 8개가 14개로 불었다.

    **쓰기는 조건부 UPDATE 한 문장이다.** 읽고-고치고-쓰면 동시에 온
    두 요청이 각자 묶음을 이어붙여 같은 붕괴가 난다. _take_step 이
    순번을 지키는 방식과 같다.

    **묶음을 다 못 채우면 저장하지 않는다.** 부분 묶음을 넣으면
    learned_ids 의 구간 경계가 밀려, 그 뒤 문제가 전부 화면에 안 보인
    단어로 나간다. 그 판은 학습 없이 전체에서 낸다 - 후보가 모자라는
    드문 상황이라 판을 망치는 것보다 낫다.
    """
    now_chunk = _now_chunk(study)
    if now_chunk is None:
        return []

    if study.issued_chunks > now_chunk:
        return learn_targets(study)  # 이미 뽑았다

    picked = _pick_for_study(study)
    if len(picked) < study.chunk_size:
        # 후보가 모자란다. 부분 묶음은 저장하지 않는다.
        #
        # **여기서 학습분을 끝낸다.** 그냥 돌아가면 issued_chunks 는 그대로
        # 인데 answered 는 계속 오르고, 다음 묶음이 성공하는 순간 두 값이
        # 어긋난 채로 굳는다 - _study_scope 가 보는 슬라이스가 실제로
        # 발급된 묶음과 영영 안 맞아, 화면에 보여준 카드가 문제 범위로
        # 안 쓰인다. chunk_count 를 지금 순번으로 낮춰 "여기까지가 학습분"
        # 을 못 박으면 그 뒤는 전체에서 내는 옛 흐름으로 깔끔히 돌아간다.
        logger.info(
            "학습 묶음을 못 채워 학습분을 여기서 끝냅니다. "
            "study=%s 뽑음=%s 필요=%s 묶음=%s",
            study.pk,
            len(picked),
            study.chunk_size,
            now_chunk,
        )
        # chunk_size 도 함께 내린다. 둘은 한 몸으로 "학습이 있는 판인가" 를
        # 말하는데(모델 주석), 한쪽만 0 이면 서로 모순인 행이 남는다.
        DailyStudy.objects.filter(pk=study.pk).update(
            chunk_count=now_chunk,
            **({"chunk_size": 0} if now_chunk == 0 else {}),
        )
        study.refresh_from_db()
        return []

    ids = [w.pk for w in picked]

    # issued_chunks 가 now_chunk 그대로일 때만 쓴다. 동시에 온 다른
    # 요청이 이미 올렸으면 여기서 0 행이 되고, 그쪽이 넣은 것을 읽는다.
    #
    # **이어붙일 원본을 UPDATE 직전에 다시 읽는다.** 인메모리 값을 쓰면
    # issued_chunks 만 CAS 로 막히고 리스트는 read-modify-write 그대로다 -
    # 그 사이 다른 경로가 DailyStudy 를 통째로 save() 하면(Admin 이 진행
    # 중인 판을 열어 저장만 해도 그렇다) 낡은 리스트가 되살아나 구간
    # 경계가 밀린다. _take_step 이 F() 로 인메모리 값을 안 믿는 것과
    # 같은 이유다.
    #
    # _pick_for_study 가 수십 ms 를 쓰므로 그 사이가 창이다.
    kept = (
        DailyStudy.objects.filter(pk=study.pk)
        .values_list("learned_ids", flat=True)
        .first()
    )
    updated = DailyStudy.objects.filter(
        pk=study.pk, issued_chunks=now_chunk
    ).update(
        issued_chunks=now_chunk + 1,
        learned_ids=list(kept or []) + ids,
    )
    study.refresh_from_db()

    if not updated:
        return learn_targets(study)
    return picked


def _pick_for_study(study: DailyStudy) -> list[Word]:
    """이번 묶음에 학습할 단어를 고른다.

    **틀린 것 > 안 본 것 > 오래된 것** 순이다. 복습 화면이 쓰는 정렬과
    같다(review.py) - 거기서 이미 "지금 모르는 것" 을 그 순서로 정의했고,
    학습이 다른 순서를 쓰면 두 화면이 서로 다른 것을 "모르는 것" 이라
    부르게 된다.

    이번 판에서 이미 학습한 것은 뺀다. 안 빼면 앞 묶음에서 본 단어가
    다음 묶음에 또 나오는데, 그건 복습이 아니라 버그로 보인다.
    """
    seen = set(study.learned_ids)

    # 이 사람의 복습 상태. 없는 단어는 "안 본 것" 이라 뒤에서 채운다.
    #
    # 모델 객체 대신 필요한 세 값만 읽는다. 한 판에 여섯 번까지 부르는
    # 자리라 매번 이 사람의 복습 줄을 통째로 만들면 낭비다 - 여기서 쓰는
    # 것은 is_wrong 과 last_correct_at 둘뿐이다.
    states = {
        target_id: (is_wrong, last_correct_at)
        for target_id, is_wrong, last_correct_at in ReviewState.objects.filter(
            user_id=study.user_id, target_type=quiz.TARGET_WORD
        ).values_list("target_id", "is_wrong", "last_correct_at")
    }

    # **틀린 것을 먼저 DB 에서 좁혀 가져온다.** 전체를 무작위로 자른 뒤
    # 분류하면, 틀린 단어가 그 표본에 안 들어가면 못 뽑는다 - 단어가
    # 566개고 틀린 것이 몇 개뿐일 때 그 확률이 크다. "틀린 것 먼저" 는
    # 이 기능의 약속이라 표본 운에 맡기면 안 된다.
    picked: list[Word] = []
    wrong_ids = [
        target_id
        for target_id, (is_wrong, _last) in states.items()
        if is_wrong and target_id not in seen
    ]
    if wrong_ids:
        picked.extend(
            Word.objects.visible()
            .filter(pk__in=wrong_ids)
            .order_by("?")[: study.chunk_size]
        )

    need = study.chunk_size - len(picked)
    if need < 1:
        return picked

    # 안 본 것. 복습 상태가 아예 없거나 맞힌 적이 없는 단어다.
    #
    # 후보를 무작위로 자르는 것은 여기서만 한다. 안 본 것은 대개
    # 수백 개라 순서를 정할 근거가 없고, 매번 같은 것이 나오면
    # 알파벳 앞쪽만 배우게 된다.
    known = set(states) | seen | {w.pk for w in picked}
    picked.extend(
        Word.objects.visible().exclude(pk__in=known).order_by("?")[:need]
    )

    need = study.chunk_size - len(picked)
    if need < 1:
        return picked

    # 오래된 것. 마지막으로 맞힌 지 오래된 순서다.
    chosen = {w.pk for w in picked}
    old_ids = sorted(
        (
            target_id
            for target_id, (_wrong, last_correct_at) in states.items()
            if last_correct_at is not None
            and target_id not in seen
            and target_id not in chosen
        ),
        key=lambda pk: states[pk][1],
    )
    if old_ids:
        # need 의 3배를 가져오는 것은 visible() 로 걸러 사라지는 몫의
        # 여유다. 복습 상태는 남아 있는데 그 단어가 미검수로 내려간
        # 경우가 있어서, 딱 need 개만 가져오면 몇 개는 빈손이 된다.
        # 미검수가 2/3 를 넘으면 이 여유로도 모자라는데, 그때는 묶음
        # 발급이 실패하고 issue_chunk 가 학습분을 거기서 끝낸다.
        found = {
            w.pk: w
            for w in Word.objects.visible().filter(pk__in=old_ids[: need * 3])
        }
        picked.extend(found[pk] for pk in old_ids if pk in found)

    return picked[: study.chunk_size]


def _study_scope(study: DailyStudy) -> list[int] | None:
    """이번 문제를 낼 범위. None 이면 전체에서 낸다.

    학습분 순번(앞쪽 chunk_size * chunk_count 개)이면 그 순번이 속한
    묶음의 단어 id 를 준다.

    **아직 안 뽑은 묶음이면 None 을 준다.** 여기서 뽑지 않는 이유는
    책임을 나누기 위해서다 - 뽑아서 저장하는 것은 issue_chunk 하나이고,
    여기는 뽑힌 것을 읽기만 한다. 양쪽이 다 뽑으면 어느 쪽이 넣었는지에
    따라 learned_ids 가 달라진다.

    **"카드를 봤는지" 는 강제하지 않는다.** 서버는 학습 카드와 문제를
    같은 응답에 함께 내려주고, 사용자가 카드를 넘겼는지 추적하지 않는다.
    API 를 직접 치면 학습을 건너뛰고 바로 답할 수 있다 - 그래도 문제는
    묶음 안에서 나오므로 범위 약속은 지켜지고, 좁은 범위가 오히려 쉬워서
    건너뛰는 것이 이득도 아니다. 강제하려면 왕복이 하나 더 늘어난다.
    """
    now_chunk = _now_chunk(study)
    if now_chunk is None:
        return None

    if study.issued_chunks <= now_chunk:
        return None  # 아직 안 뽑았다. issue_chunk 가 뽑는다

    start = now_chunk * study.chunk_size
    ids = study.learned_ids[start : start + study.chunk_size]
    return ids or None


def _words_in_order(ids: list[int]) -> list[Word]:
    """id 순서를 지켜 단어를 읽는다. 사라진 것은 빠진다.

    순서를 지키는 이유: 화면이 "1/2" 처럼 번호를 매기는데, DB 가 주는
    순서로 두면 새로 고칠 때마다 번호와 단어가 뒤바뀐다.
    """
    found = {w.pk: w for w in Word.objects.visible().filter(pk__in=ids)}
    return [found[pk] for pk in ids if pk in found]


# ---- 안쪽 ----


def _answerable(plan: StudyPlan) -> int:
    """지금 낼 수 있는 문제 수.

    출제가 최근 낸 정답을 후보에서 빼므로(RECENT_KEEP), 콘텐츠가 적으면
    도중에 후보가 바닥난다. 그때 판은 서버가 닫아주지만 **40문제를
    약속하고 30문제만 낸 꼴**이 된다 - 사용자는 왜 일찍 끝났는지 모른다.

    그래서 시작할 때 낼 수 있는 만큼으로 줄여 약속을 지킨다. 보너스는
    안 줄인다 - 콘텐츠가 적은 것은 사용자 잘못이 아니다.

    운영 DB 는 검수된 단어가 이 수를 훨씬 넘으므로 평소에는 아무 일도
    일어나지 않는다. 콘텐츠를 정리하거나 새 분류를 좁게 열 때를 위한
    안전판이다.

    **단어와 문장은 서로를 못 채운다.** 둘을 그냥 더하면 단어 6개 +
    문장 100개인 DB 가 106 으로 세어져 25문제를 약속하는데, 실제로는
    열 문제 남짓에서 끊긴다. 출제가 종류를 매번 무작위로 고르는데
    (session.make_question), 단어 차례가 왔을 때 단어 후보가 비어 있으면
    거기서 판이 닫히기 때문이다. 문장이 아무리 많아도 그 자리를 대신
    못 낸다.

    한 종류로 낼 수 있는 수는 그 종류의 개수를 못 넘는다 - 최근 창이
    RECENT_KEEP 개를 물고 있어 한 바퀴를 돌면 후보가 빈다. 그래서
    **적은 쪽 종류가 병목**이고, 그 종류가 마르는 시점이 판의 끝이다.

    그래서 **적은 쪽 개수**가 섞어 내는 구간의 한계다. 종류가 무작위라
    적은 쪽이 언제 뽑힐지 모르니, 그 종류가 한 바퀴 도는 것보다 일찍
    끝내야 안전하다.

    **학습분은 이 병목을 안 탄다.** 그 구간은 문장을 아예 안 쓴다 -
    make_question 이 word_ids 를 받으면 종류 추첨을 건너뛰고 단어 문제만
    만든다(session.py). 전체의 75~80% 가 그 구간이라, 병목을 판 전체에
    걸면 문장 하나짜리 DB 가 40문제를 1문제로 줄인다.

    **문장 0개와 1개 사이의 계단은 줄었을 뿐 남아 있다.** 단어 40개
    기준으로 문장 0개면 40, 1개면 31, 10개면 다시 40 이다 - 문장이
    없으면 병목을 아예 안 걸기 때문이다. 덜 약속하는 쪽으로만 틀리고
    실제로 그만큼은 다 내주므로 그대로 둔다. 없애려면 나머지 구간의
    실제 소요(rest_room)와 비교해야 하는데, 그 계산이 출제 추첨의
    기대값에 기대게 되어 지금보다 틀리기 쉽다.

    그래서 **학습분(단어만) + 나머지(섞어 냄)** 로 나눠 센다. 실제로
    낼 수 있는 수보다 적게 약속하는 쪽으로만 틀리는데, 덜 약속하고 다
    내주는 것은 사용자가 손해를 안 본다 - 반대로 틀리면 "25문제" 를
    약속받고 8문제에서 끝나는 화면을 보게 된다.
    """
    words = Word.objects.visible().count()
    sentences = Sentence.objects.visible().count()

    # 학습분은 단어만 쓴다. 계획한 만큼 단어가 있으면 그대로 선다.
    learning = min(words, plan.from_study)

    # 나머지는 종류를 섞어 내므로 적은 쪽이 병목이다. 학습분에 쓴 단어는
    # 최근 창에 들어가 있어 그만큼 빠진다.
    #
    # **문장이 많아도 그만큼 더 못 낸다.** 섞어 내는 구간은 계획상
    # plan.total - plan.from_study 개뿐이라, 문장 100개가 있어도 그
    # 자리를 넘겨 셀 수 없다. 안 막으면 단어 6개 + 문장 100개가 106 으로
    # 세어져 원래 결함으로 돌아간다.
    rest_room = max(plan.total - plan.from_study, 0)
    rest_words = max(words - learning, 0)
    if not sentences:
        # 문장이 없으면 단어가 다 낸다. 섞이지 않으니 병목도 없다.
        rest = rest_words
    elif not rest_words:
        # 남은 단어가 없다. 단어 차례가 오면 거기서 끊기므로 문장이
        # 아무리 많아도 섞어 내는 구간은 서지 않는다.
        rest = 0
    else:
        rest = min(rest_words, sentences)

    return learning + min(rest, rest_room)


def _take_step(study: DailyStudy, step: int, gained: int, correct: bool) -> bool:
    """이 순번을 가져가며 답을 쌓는다. 이걸로 다 풀었으면 True.

    **한 문장이어야 한다.** 순번 확인과 반영을 나누면 동시에 온 요청이
    전부 같은 값을 읽고 전부 통과한다 - 같은 토큰으로 보기 네 개를 보내
    맞은 것만 남기는 길이 열린다.

    조건 셋이 각각 다른 것을 막는다.

        step=step         옛 토큰 재사용. 이게 이 함수의 존재 이유다
        answered__lt=...  문제 수 초과. 마지막 문제에 두 답이 겹칠 때
        finished_at=null  끝난 뒤 들어온 답

    **점수판(DailyScore)은 여기서 안 건드린다.** 그건 호출부가 이 함수
    밖에서 한다 - 저기는 (user, day) 유일 인덱스를 잡는데, 이 함수를
    감싼 트랜잭션 안에서 잡으면 커밋까지 그 락을 쥔 채로 복습 갱신까지
    기다리게 된다. 답하기와 어제 판 정산이 겹치는 자정 언저리가 정확히
    그 조합이고, 이 파일 첫머리(settle_stale)가 그 교착을 이미 적어뒀다.
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
    return study.answered >= study.total_questions


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

    # **저장된 문제를 함께 비운다.** 마지막 답은 다음 문제를 안 심으므로
    # study.question 이 한 순번 뒤처진 채 남는다. 그 상태에서 이 UPDATE 가
    # 실패하면(점수판 반영은 트랜잭션 밖이라 여기서 터질 수 있다) resume 이
    # 뒤처진 문제를 보고 새로 뽑아 주는데, 이미 다 푼 판이라 그 토큰으로
    # 답하면 _take_step 의 answered__lt 가 거절한다 - 화면을 새로 열어도
    # "이미 처리한 답입니다" 만 나오고 하루 한 번 제약이라 재시작도 못 한다.
    #
    # 닫는 자리에서 함께 비우면 세 호출자(answer, resume, settle_stale)가
    # 전부 여기를 지나므로 한 곳으로 막힌다.
    closed = DailyStudy.objects.filter(
        pk=study.pk, finished_at__isnull=True
    ).update(score=final, finished_at=timezone.now(), question=None)

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


def _still_visible(saved: dict) -> bool:
    """저장해둔 문제의 보기가 아직 사용자에게 보여도 되는가.

    낼 때 visible() 로 걸렀어도 그 뒤에 검수가 취소되거나 지워질 수 있다.
    토큰 수명이 6시간이라 그 사이에 충분히 일어난다.

    보기 하나라도 사라졌으면 문제를 통째로 버린다 - 그 자리만 비우면
    보기가 셋이 되어 찍기 확률이 올라가고, 정답이 사라진 경우에는 답이
    없는 문제가 된다.
    """
    body = saved.get("body")
    if not isinstance(body, dict):
        return False

    ids = [c.get("id") for c in body.get("choices") or [] if isinstance(c, dict)]
    if not ids:
        return False

    # 보기의 종류는 정답의 종류와 같다(같은 표에서 뽑는다).
    target_type = (saved.get("state") or {}).get("q", {}).get("tt")
    model = Word if target_type == quiz.TARGET_WORD else Sentence
    return model.objects.visible().filter(pk__in=ids).count() == len(ids)


def _next_question(
    study: DailyStudy, recent_words: list, recent_sentences: list
) -> tuple[str | None, dict | None]:
    """다음 문제를 만들어 토큰에 심는다. 못 만들면 (None, None).

    학습분 순번이면 **방금 본 묶음 안에서** 낸다. 그 뒤(나머지)는 전체에서
    낸다 - 학습분을 맨 앞에 몰아두는 이유는 STUDY_PLANS 주석에 있다.
    """
    word_ids = _study_scope(study)

    question = make_question(list(recent_words), list(recent_sentences), word_ids)
    if question is None and word_ids:
        # 좁은 범위로 못 만들었다. 묶음이 작아 보기를 못 채우거나 설명이
        # 없는 단어만 걸린 경우다. 판을 끝내는 것보다 전체에서 내는 편이
        # 낫다 - 사용자는 "왜 일찍 끝났지" 를 보게 된다.
        #
        # **로그를 남긴다.** 이 폴백이 돌면 화면에 보인 카드와 다른 단어로
        # 문제가 나가므로, 자주 돈다면 그건 기능이 약속을 못 지키는 것이다.
        # 조용히 떨어지면 그것을 알 방법이 없다.
        logger.info(
            "학습 범위로 문제를 못 만들어 전체에서 냅니다. study=%s 범위=%s",
            study.pk,
            word_ids,
        )
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

    body = {
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

    # **이 순번의 문제를 못박는다.** 저장해두지 않으면 화면을 새로 열
    # 때마다 다시 뽑게 되고, 순번은 답할 때만 오르므로 아는 문제가 나올
    # 때까지 돌린 뒤 답할 수 있다(resume 참고).
    study.question = {"state": state, "body": body}
    study.save(update_fields=["question"])

    return _sign(state), body


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
