"""학습 기록.

한 판(QuizSession)과 그 안의 답(QuizAnswer), 그리고 하루를 대표하는
한 줄(DailyScore)로 이루어진다.

DailyScore 를 따로 두는 이유가 이 앱의 핵심이다. 꾸준함 점수는
"그날 가장 잘한 한 판 + 그날 일일공부" 로 하루에 상한이 있다. 판을 전부
더하는 방식이면 90초짜리를 네 시간 돌린 사람이 한 달 꾸준히 한 사람을
하루 만에 앞지른다. 그 규칙을 코드가 아니라 **표 구조에** 담아두면
어디선가 깜빡할 수 없다 - 하루에 행이 하나뿐이라 더할 것이 없다.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from . import calendar_kst


class SessionKind(models.TextChoices):
    """판의 종류.

    자유 문제풀이만 최고점 순위표에 들어간다. 일일공부는 제한 시간도
    감점도 없어서 같은 자로 잴 수 없다.
    """

    FREE = "free", "자유 문제풀이"
    DAILY = "daily", "일일공부"


class QuizSession(models.Model):
    """한 판.

    끝난 판만 기록한다. 중간에 나간 판을 남기면 첫 문제만 맞히고 나가기를
    반복해 최고점을 올릴 수 있다.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_sessions",
        verbose_name="사용자",
    )

    kind = models.CharField(
        "종류", max_length=10, choices=SessionKind.choices, default=SessionKind.FREE
    )

    # 서버가 발급한 판 식별자. 같은 판을 두 번 제출해도 한 번만 기록되게
    # 막는 열쇠다. 판 상태는 서명 토큰에 담겨 오가므로, 이 값이 없으면
    # 끝낸 토큰을 그대로 다시 보내 기록을 여러 번 남길 수 있다.
    token_id = models.CharField("판 식별자", max_length=64, unique=True)

    started_at = models.DateTimeField("시작")
    finished_at = models.DateTimeField("종료")

    score = models.IntegerField("점수")
    answered = models.PositiveIntegerField("푼 문제")
    correct = models.PositiveIntegerField("맞은 문제")
    skipped = models.PositiveIntegerField("넘긴 문제", default=0)

    class Meta:
        verbose_name = "문제풀기 기록"
        verbose_name_plural = "문제풀기 기록"
        ordering = ["-finished_at"]
        indexes = [
            # 최고점 순위표가 이 조합으로 읽는다.
            models.Index(fields=["kind", "-score"]),
            # 내 기록·출석 조회.
            models.Index(fields=["user", "-finished_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.finished_at:%Y-%m-%d} {self.score}점"

    @property
    def day(self):
        """이 판이 속한 날(한국 기준). 끝낸 시각으로 센다."""
        return calendar_kst.day_of(self.finished_at)


class QuizAnswer(models.Model):
    """판 안의 답 하나.

    틀린 문제 다시풀기가 이 표에서 나온다. 그래서 맞은 것도 남긴다 -
    무엇을 이미 아는지도 알아야 복습에서 뺀다.

    **자유 문제풀이만 여기 남는다.** 일일공부는 DailyStudy 에 개수만
    쌓고 답 하나하나를 남기지 않는다 - 답마다 쓰기가 두 번이 되는 것을
    피했다(daily_study.py 첫머리). 복습이 일일공부 오답까지 필요해지면
    그때 답 표를 따로 만든다.
    """

    session = models.ForeignKey(
        QuizSession,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="판",
    )

    # 문제 유형(meaning/term/description/blank/situation).
    # 값 목록은 vocab.quiz.QuizKind 에 있다. choices 로 묶지 않는 이유:
    # 유형이 늘 때마다 마이그레이션이 생기고, 여기서는 무엇이 왔는지
    # 남기기만 하면 된다.
    kind = models.CharField("문제 유형", max_length=20)

    # 정답이 단어인지 문장인지. 빈칸 문제는 문장을 보여주지만 답은 단어다.
    target_type = models.CharField("대상 종류", max_length=10)
    target_id = models.PositiveBigIntegerField("대상 id")

    is_correct = models.BooleanField("맞았나")
    is_skipped = models.BooleanField("넘겼나", default=False)

    # 문제를 받은 시각과 답한 시각의 차이. 클라이언트가 잰 값이 아니라
    # 서버가 계산한 값이다 - 받은 값을 쓰면 0 을 보내 항상 만점이 된다.
    elapsed_ms = models.PositiveIntegerField("걸린 시간(ms)")

    # 이 답으로 얻은 점수. +1 / 0 / -1.
    # 다시 계산할 수 있지만 저장한다 - 규칙이 바뀌어도 그때 준 점수가
    # 무엇이었는지 남아야 사용자에게 설명할 수 있다.
    score = models.SmallIntegerField("점수")

    class Meta:
        verbose_name = "답"
        verbose_name_plural = "답"
        indexes = [
            # 틀린 문제 다시풀기가 이 조합으로 읽는다.
            models.Index(fields=["session", "is_correct"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.target_type}:{self.target_id} {self.score:+d}"


class DailyScore(models.Model):
    """하루를 대표하는 한 줄.

    꾸준함 순위표가 이 표를 사용자별로 더한 값이다. 하루에 행이 하나뿐이라
    몇 판을 하든 그날 점수는 정해진 상한 안에 있다.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_scores",
        verbose_name="사용자",
    )

    day = models.DateField("날짜(KST)")

    # 그날 자유 문제풀이 중 가장 높은 판의 점수. 판이 마이너스여도 그대로
    # 둔다 - 여기는 기록이고, 더할 때 0 으로 자르는 것은 total 쪽이다.
    #
    # 아직 한 판도 안 했으면 null 이다. 0 을 기본값으로 두면 "마이너스만
    # 낸 날" 과 "안 한 날" 이 구분되지 않아, 첫 판이 -3 일 때 그것을
    # 넣어야 할지 판단할 수 없다.
    best_free_score = models.IntegerField(
        "그날 최고 판 점수", null=True, blank=True, default=None
    )

    # 그날 일일공부로 얻은 점수(완주 보너스 포함). 일일공부는 하루 한 번이라
    # 최고를 고를 것이 없고 그대로 쌓인다.
    daily_study_score = models.IntegerField("그날 일일공부 점수", default=0)

    class Meta:
        verbose_name = "하루 점수"
        verbose_name_plural = "하루 점수"
        ordering = ["-day"]
        constraints = [
            # 하루에 한 줄. 이 제약이 곧 "하루 상한" 규칙이다.
            models.UniqueConstraint(
                fields=["user", "day"], name="learning_dailyscore_user_day_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-day"]),
            # 주간 순위표가 날짜 범위로 읽는다.
            models.Index(fields=["day"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.day} {self.total}점"

    @property
    def total(self) -> int:
        """그날 꾸준함 점수. 0 밑으로 내려가지 않는다.

        그날 판이 전부 마이너스일 수 있다. 그대로 더하면 열심히 한 날
        누적이 줄어든다 - 판 화면에서는 마이너스가 그대로 보여 긴장감이
        살아 있지만, 쌓는 쪽에서는 자른다.

        **같은 식이 SQL 로도 있다** - leaderboards.py 의 _streak_by_user.
        순위표는 상위 몇 명만 알면 되는데 여기 property 는 DB 가 모르기
        때문이다. 이 식을 고치면 저쪽도 같이 고쳐야 한다.
        """
        return max(0, (self.best_free_score or 0) + self.daily_study_score)


class RoundStep(models.Model):
    """판의 한 순번을 이미 처리했다는 표시.

    되돌리기(replay)를 막는다. 판 상태가 서명 토큰으로 오가서 옛 토큰을
    다시 보낼 수 있는데, 그대로 두면 답을 캐낸 뒤 되돌려 +1 을 확정하거나
    점수가 가장 높았던 시점을 골라 끝낼 수 있다. 자세한 것은 session.py.

    **캐시가 아니라 표를 쓰는 이유**가 이 모델의 존재 이유다.
    처음에는 DatabaseCache 에 넣었는데, 캐시는 항목이 넘치면 스스로 지운다
    (cull). 지워지면 방어가 열리므로, 공격자는 캐시를 채우기만 하면 된다 -
    답하기를 반복해 자기 판의 표시를 밀어내고 옛 토큰을 쓰면 그만이다.
    여기서는 우리가 지울 때만 지워지고, 유일 제약이 원자성을 준다.

    쓰기 경로가 열리는 것(로그인 없이 행을 만든다)은 감수한다. 캐시도
    어차피 DB 쓰기였고, 요청 제한이 양을 묶는다. 오래된 행은 sweep 이 지운다.
    """

    round_id = models.CharField("판 식별자", max_length=64)
    step = models.PositiveIntegerField("순번")
    created_at = models.DateTimeField("만든 때", auto_now_add=True)

    class Meta:
        verbose_name = "판 진행 표시"
        verbose_name_plural = "판 진행 표시"
        constraints = [
            # 원자성이 여기서 나온다. 같은 순번을 동시에 가져가려 하면
            # 하나만 INSERT 에 성공한다 - 읽고 나서 쓰면 둘 다 통과한다.
            models.UniqueConstraint(
                fields=["round_id", "step"],
                name="learning_roundstep_round_step_unique",
            ),
        ]
        indexes = [
            # sweep 이 오래된 것부터 지운다.
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.round_id}#{self.step}"


class StudyLength(models.TextChoices):
    """일일공부 길이. 사용자가 시작할 때 고른다.

    시간이 아니라 **문제 수**가 실제 규칙이다. 제한 시간이 없으므로
    "5분" 은 대략 그만큼 걸린다는 안내이지 마감이 아니다 - 천천히 풀어도
    불이익이 없어야 매일 온다.
    """

    SHORT = "5m", "5분"
    MEDIUM = "10m", "10분"
    LONG = "30m", "30분"


# 길이별 문제 수와 완주 보너스.
#
# 보너스를 길이에 비례시키는 이유: 전부 같은 값이면 짧은 것을 고르는 쪽이
# 항상 이득이라 긴 선택지가 사실상 죽는다. 자기 사정에 맞춰 고르게 하려면
# 어느 것을 골라도 손해가 없어야 한다.
STUDY_PLANS: dict[str, tuple[int, int]] = {
    StudyLength.SHORT: (10, 5),
    StudyLength.MEDIUM: (25, 10),
    StudyLength.LONG: (40, 25),
}


class DailyStudy(models.Model):
    """오늘의 일일공부 한 줄. 진행 상태를 서버가 들고 있다.

    자유 문제풀이와 달리 **토큰만으로는 안 된다.** 저기는 그날 최고 한 판만
    세므로 나쁜 판을 버려도 결과가 같지만, 여기는 더하기라서 점수가 깎이는
    판을 중간에 버리는 것이 이득이 된다. 끝내기를 클라이언트에 맡기면
    "마음에 안 들면 새로 시작" 이 열린다.

    그래서 답할 때마다 여기에 쌓는다. 나가도 푼 만큼 남고, 다시 들어와도
    이어지지 않는다 - 하루 한 번이라 이미 시작한 사람은 그 줄을 본다.

    DailyScore 와 나눠 둔 이유: 저기는 순위표가 읽는 집계표다. 진행 상태를
    섞으면 "하루를 대표하는 한 줄" 이라는 뜻이 흐려지고, 순위표 쿼리가
    안 쓰는 칸을 함께 끌고 다닌다.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="daily_studies",
        verbose_name="사용자",
    )

    day = models.DateField("날짜(KST)")

    length = models.CharField(
        "길이", max_length=8, choices=StudyLength.choices
    )

    # 낼 문제 수와 완주 보너스. 시작할 때 길이로 정해 **둘 다** 고정한다.
    # STUDY_PLANS 를 나중에 바꿔도 진행 중인 판의 규칙이 안 바뀐다.
    #
    # 보너스만 런타임에 STUDY_PLANS 를 보게 두면 반쪽만 고정된다 - 9/10 을
    # 푼 사람이 배포 한 번에 다른 보너스를 받고, 길이 값을 제거하면 조용히
    # 0 이 된다.
    total_questions = models.PositiveIntegerField("문제 수")
    bonus = models.PositiveIntegerField("완주 보너스", default=0)

    # 다음에 받을 순번. 답 하나가 이 값을 **원자적으로 가져간다**.
    #
    # 이게 없으면 같은 토큰으로 보기를 하나씩 다 넣어볼 수 있다. 첫 답의
    # 응답이 정답을 알려주므로, 옛 토큰에 그 답을 실어 다시 보내면 확실히
    # +1 이다. 진행 개수만 세는 것으로는 못 막는다 - 그쪽은 늘어나지만
    # 맞힌 개수도 같이 늘어나기 때문이다.
    #
    # session.py 는 같은 일을 RoundStep 표로 한다. 저기는 로그인 안 한
    # 사람도 풀어서 판마다 행을 만들 수 없었지만, 여기는 이미 하루 한 줄이
    # 있으니 칸 하나면 된다.
    step = models.PositiveIntegerField("다음 순번", default=0)

    # 이 순번에 낼 문제. 답하면 다음 문제로 덮인다.
    #
    # **한 순번에 문제 하나를 고정하려고 저장한다.** 이게 없으면 화면을
    # 새로 열 때마다 문제를 다시 뽑게 되고, 순번은 답할 때만 오르므로
    # 아는 문제가 나올 때까지 돌린 뒤 답하면 된다. _take_step 은 "한
    # 순번은 한 번만 소비된다" 를 지킬 뿐 "한 순번에 문제는 하나다" 를
    # 지키지 않는다 - 지금까지는 문제 발급이 순번 소비와 붙어 있어 그
    # 차이가 드러날 자리가 없었다.
    #
    # 서명하지 않은 원본을 담는다. 화면에 나갈 때 daily_study 가 서명하고,
    # 여기 있는 값은 서버만 읽는다.
    question = models.JSONField("이 순번의 문제", null=True, blank=True)

    answered = models.PositiveIntegerField("푼 문제 수", default=0)
    correct = models.PositiveIntegerField("맞힌 문제 수", default=0)

    # 지금까지 얻은 점수. 맞히면 +1, 틀리면 0 이라 answered 와 별개로 둘
    # 이유는 없어 보이지만, 완주 보너스가 여기 더해진다.
    score = models.IntegerField("점수", default=0)

    finished_at = models.DateTimeField(
        "끝낸 때", null=True, blank=True, default=None
    )

    created_at = models.DateTimeField("시작한 때", auto_now_add=True)

    class Meta:
        verbose_name = "일일공부"
        verbose_name_plural = "일일공부"
        ordering = ["-day"]
        constraints = [
            # 하루 한 번. 이 제약이 곧 그 규칙이다 - 코드로 검사하면
            # 동시에 두 번 시작하는 경로가 열린다.
            models.UniqueConstraint(
                fields=["user", "day"], name="learning_dailystudy_user_day_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-day"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.day} {self.answered}/{self.total_questions}"

    @property
    def is_done(self) -> bool:
        return self.finished_at is not None



class ReviewState(models.Model):
    """한 사람이 한 항목(단어/문장)을 얼마나 익혔는지.

    **왜 표가 따로 있나.** 복습 대상은 QuizAnswer 만으로도 뽑을 수 있지만,
    "복습에서 연속 두 번 맞혔나" 는 그 표로 세면 사람마다 항목마다 과거
    답을 거슬러 봐야 한다. 항목 수만큼 스캔이 늘어 목록 한 번 그리는 데
    표 전체를 훑게 된다. 그래서 연속 횟수만 여기 들고 있는다.

    자유 문제풀이의 답이 이 표를 갱신한다. 일일공부는 답을 하나하나
    남기지 않으므로 여기 안 들어온다(QuizAnswer docstring 참고).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_states",
        verbose_name="사용자",
    )

    # 무엇을 익히는 중인가. QuizAnswer 와 같은 (종류, id) 짝이다.
    # FK 로 묶지 않는 이유: 대상이 단어일 수도 문장일 수도 있어 한 칸에
    # 안 들어간다. 대상이 지워지면 이 줄은 고아가 되는데, 출제가 어차피
    # visible() 로 좁히므로 화면에는 안 나온다.
    target_type = models.CharField("대상 종류", max_length=10)
    target_id = models.PositiveBigIntegerField("대상 id")

    # **복습에서** 연속으로 맞힌 횟수. 틀리면 0 으로 돌아간다.
    # 자유 문제풀이에서 맞힌 것은 여기를 올리지 않는다 - 복습 목록을
    # 벗어나는 조건이라 복습으로 확인한 것만 세야 한다.
    streak = models.PositiveSmallIntegerField("연속 정답", default=0)

    # 마지막으로 맞힌 시각. 여기서 7일이 지나면 "오래된 것" 이 된다.
    # 틀리면 갱신하지 않는다 - 틀린 것은 이미 다른 조건으로 뽑힌다.
    last_correct_at = models.DateTimeField("마지막 정답", null=True, blank=True)

    # 마지막으로 이 항목에 답한 결과. 목록에서 "틀린 것" 을 고르는 조건.
    is_wrong = models.BooleanField("마지막에 틀렸나", default=False)

    created_at = models.DateTimeField("만든 때", auto_now_add=True)
    updated_at = models.DateTimeField("고친 때", auto_now=True)

    class Meta:
        verbose_name = "복습 상태"
        verbose_name_plural = "복습 상태"
        constraints = [
            # 사람마다 항목마다 한 줄. 이 제약이 곧 그 규칙이다.
            models.UniqueConstraint(
                fields=["user", "target_type", "target_id"],
                name="learning_reviewstate_user_target_unique",
            ),
        ]
        indexes = [
            # 목록을 뽑는 조건 그대로. 틀린 것 먼저, 그다음 오래된 것.
            models.Index(fields=["user", "is_wrong", "last_correct_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.target_type}:{self.target_id} streak={self.streak}"
