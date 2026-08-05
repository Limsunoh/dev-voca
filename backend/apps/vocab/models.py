from django.db import models


class LearningItemQuerySet(models.QuerySet):
    """학습 콘텐츠 공통 조회 헬퍼."""

    def visible(self):
        """사용자에게 내보내도 되는 것만 - 검수 완료된 항목.

        뷰마다 filter(is_reviewed=True) 를 손으로 쓰면 언젠가 한 곳을 빠뜨린다.
        사용자 노출 경로는 이 메서드를 쓴다(CLAUDE.md 의 검수 규칙).
        """
        return self.filter(is_reviewed=True)


class LearningItem(models.Model):
    """모든 학습 콘텐츠(단어/문장/에러 메시지)가 공유하는 공통 필드.

    추상 모델이라 자체 테이블은 만들어지지 않고, 상속한 모델의 테이블에 필드만 합쳐진다.
    나중에 Sentence, ErrorMessage 를 추가할 때 이 클래스를 상속하면 된다.
    """

    class Difficulty(models.IntegerChoices):
        EASY = 1, "쉬움"
        NORMAL = 2, "보통"
        HARD = 3, "어려움"

    class Category(models.TextChoices):
        """분류. 값은 영어 코드, 라벨은 화면에 그대로 나가는 한글(영어) 병기.

        영어 코드를 화면에 뿌리면 devops, review 처럼 개발자용 식별자가
        그대로 보인다. 타겟이 영어가 약한 사람이라 라벨은 한글이 앞에 온다.
        영어를 괄호로 남기는 건 현장에서 쓰는 말이라 그 자체가 학습이 되기 때문.

        문장·에러 메시지 도메인이 생기면 그쪽도 이 목록을 쓴다. 그래서 Word 가
        아니라 LearningItem 에 둔다.
        """

        GIT = "git", "버전 관리(Git)"
        REVIEW = "review", "코드 리뷰(Code Review)"
        API = "api", "API"
        DATABASE = "database", "데이터베이스(Database)"
        DEVOPS = "devops", "배포·운영(DevOps)"
        DEBUG = "debug", "디버깅(Debugging)"

    difficulty = models.PositiveSmallIntegerField(
        "난이도", choices=Difficulty.choices, default=Difficulty.NORMAL
    )
    # blank 를 허용하는 건 분류를 아직 못 정한 항목을 받기 위해서다.
    # choices 를 줘도 빈 문자열은 통과하므로 Admin 에서 비워둘 수 있다.
    category = models.CharField(
        "분류", max_length=50, blank=True, choices=Category.choices
    )
    source = models.CharField(
        "출처", max_length=100, blank=True, help_text="예: 정처기 기출, AI 생성"
    )
    # AI가 생성한 항목은 False 로 저장되고, Admin 검수 후 True 가 된다.
    # 사용자에게 노출되는 조회는 반드시 is_reviewed=True 로 필터링한다.
    is_reviewed = models.BooleanField("검수 완료", default=False)
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    # 상속한 모델이 Word.objects.visible() 을 쓸 수 있게 한다.
    objects = LearningItemQuerySet.as_manager()

    class Meta:
        abstract = True


class Word(LearningItem):
    """개발 영어 단어 하나."""

    term = models.CharField("영어 단어", max_length=100, unique=True)
    meaning = models.CharField("한글 뜻", max_length=200)
    description = models.TextField("설명", blank=True)
    example = models.TextField("예문", blank=True)
    example_translation = models.TextField("예문 해석", blank=True)

    class Meta:
        verbose_name = "단어"
        verbose_name_plural = "단어"
        ordering = ["term"]
        indexes = [
            # 목록/검색이 항상 검수된 것만 보므로 term 정렬과 묶어서 인덱스
            models.Index(fields=["is_reviewed", "term"]),
        ]
        constraints = [
            # choices 는 폼과 full_clean() 에서만 검사한다. update_or_create 나
            # bulk_create 는 그 경로를 안 타므로 목록에 없는 값이 그냥 저장된다.
            #
            # 그렇게 들어간 값은 화면에서 조용히 깨진다. get_category_display()
            # 가 라벨을 못 찾아 원값을 그대로 돌려주므로 영어 코드가 노출되고,
            # 그 코드로 만들어진 필터 링크를 누르면 API 가 400 을 준다.
            # 넣는 시점에 막는다.
            models.CheckConstraint(
                condition=models.Q(
                    category__in=[*LearningItem.Category.values, ""]
                ),
                name="%(app_label)s_%(class)s_category_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.term} ({self.meaning})"
