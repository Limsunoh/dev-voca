from django.db import models


class LearningItemQuerySet(models.QuerySet):
    """학습 콘텐츠 공통 조회 헬퍼."""

    def visible(self):
        """사용자에게 내보내도 되는 것만 - 검수 완료된 항목.

        뷰마다 filter(is_reviewed=True) 를 손으로 쓰면 언젠가 한 곳을 빠뜨린다.
        사용자 노출 경로는 이 메서드를 쓴다(CLAUDE.md 의 검수 규칙).

        **칸 하나만 가리는 게이트는 여기 못 담는다.** 발음(reading)은
        항목이 아니라 칸 단위로 검수되므로 쿼리셋으로 표현할 수 없다 -
        그쪽은 serializers.ReviewedReadingField 가 맡는다. 이 프로젝트의
        노출 게이트가 둘인 이유이고, 새 게이트를 만들 때 어느 쪽인지
        먼저 정해야 한다.
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
        FRONTEND = "frontend", "프론트엔드(Frontend)"
        CS = "cs", "CS 기초(Computer Science)"

    class ExamSubject(models.TextChoices):
        """정보처리기사 과목. 필기 5과목을 그대로 쓴다.

        분류(Category)와 따로 두는 이유: 한 항목이 양쪽에 다 속한다.
        deadlock 은 CS 기초이면서 정처기 "프로그래밍 언어 활용" 이다.
        분류에 과목을 섞으면 그 단어를 어느 한쪽에서만 만나게 된다.

        라벨에 과목 번호를 붙인다. 수험생은 "2과목" 으로 부르고 교재도
        그 순서를 따르므로, 이름만 적으면 자기가 아는 것과 맞춰보기 어렵다.
        """

        DESIGN = "design", "1과목 소프트웨어 설계"
        DEVELOP = "develop", "2과목 소프트웨어 개발"
        DATABASE = "database", "3과목 데이터베이스 구축"
        LANGUAGE = "language", "4과목 프로그래밍 언어 활용"
        SYSTEM = "system", "5과목 정보시스템 구축 관리"

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
    # 정처기 출제 범위인가. 분류(category)와 독립이다 - deadlock 은 CS 기초
    # 이면서 정처기라, 어느 한쪽으로만 두면 다른 쪽에서 안 보인다.
    #
    # 과목(exam_subject)이 아니라 이 불리언이 노출을 가른다. 과목은 아직
    # 안 정한 항목이 있을 수 있고, 그때도 "정처기 범위" 로는 묶여야 한다.
    is_exam = models.BooleanField(
        "정처기 범위", default=False, help_text="정보처리기사 출제 범위에 드는 항목"
    )
    exam_subject = models.CharField(
        "정처기 과목",
        max_length=20,
        blank=True,
        choices=ExamSubject.choices,
        help_text="정처기 범위일 때만 채운다. 비워두면 과목 미분류.",
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
    # IPA 발음기호. 예: /aɪˈdempətənt/
    #
    # 비워둘 수 있게 한다. 개발자만 쓰는 말은 사전에 없어 발음이 갈리는데,
    # 틀린 발음을 가르치느니 그 자리를 비우는 편이 낫다. 타겟이 영어가
    # 약한 사람이라 잘못 외우면 되돌리기 어렵다.
    pronunciation = models.CharField("발음기호", max_length=100, blank=True)
    # 발음기호 옆에 나란히 두는 한글. "한글만 읽어도 통한다" 가 이 칸의
    # 목적이고, 왜 그렇게 적는지는 prompts/korean-reading.md 에 있다.
    #
    # 발음기호와 마찬가지로 비워둘 수 있다. 갈리는 것을 억지로 채우면
    # 틀린 발음을 가르치게 된다.
    reading = models.CharField("한글 발음", max_length=120, blank=True)
    # 위 표기를 왜 그렇게 읽는지. 상세 화면에서 눌러야 보인다.
    #
    # 목록에는 안 나온다 - 짧게 훑는 자리에 설명이 끼면 훑기가 안 된다.
    reading_note = models.TextField("발음 설명", blank=True)
    # 발음을 따로 검수한다.
    #
    # is_reviewed 는 항목 단위라 이미 검수가 끝난 단어에 AI 발음을 채우면
    # 아무도 확인하지 않은 표기가 그대로 화면에 뜬다. 단어 자체는 멀쩡한데
    # 발음만 미검수인 상태를 나타낼 칸이 없어 생기는 구멍이다.
    #
    # 사람이 Admin 에서 직접 적은 것은 True 로 두면 된다.
    reading_reviewed = models.BooleanField("발음 검수됨", default=False)
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
            # 과목도 같은 이유로 막는다. 위 category 주석 참고.
            models.CheckConstraint(
                condition=models.Q(
                    exam_subject__in=[*LearningItem.ExamSubject.values, ""]
                ),
                name="%(app_label)s_%(class)s_exam_subject_valid",
            ),
            # 정처기 범위가 아닌데 과목이 붙어 있으면 앞뒤가 안 맞는다.
            # 화면은 is_exam 으로 거르므로 그런 항목은 과목만 달린 채
            # 어디에도 안 나오고, Admin 에서 보면 정처기인 줄 알게 된다.
            models.CheckConstraint(
                condition=models.Q(is_exam=True) | models.Q(exam_subject=""),
                name="%(app_label)s_%(class)s_exam_subject_needs_flag",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.term} ({self.meaning})"


class SentenceKind(models.TextChoices):
    """문장의 종류. 어디서 마주치는 문장인지.

    Sentence 안에 중첩하면 Meta 의 CheckConstraint 에서 참조할 수 없다
    (클래스 본문이 실행되는 중이라 Sentence 도 Kind 도 아직 이름이 없다).
    LearningItem.Category 는 이미 정의가 끝난 다른 클래스라 문제가 없었다.
    """

    PHRASE = "phrase", "실무 표현"
    ERROR = "error", "에러 메시지"


class Sentence(LearningItem):
    """개발하면서 마주치는 영어 문장 하나.

    단어를 다 외워도 문장이 안 읽히는 지점이 따로 있다. 리뷰 코멘트의
    돌려 말하는 표현("Could you...?" 은 요청이 아니라 사실상 지시다),
    에러 메시지의 관용구("refusing to", "unrelated histories") 같은 것들.

    실무 문장과 에러 메시지를 한 모델에 담고 kind 로 구분한다. 둘 다
    "읽고 뜻을 파악한다" 는 점에서 학습 방식이 같고, 화면·검색·검수도
    똑같이 돌아간다. 지금 테이블을 나누면 그 셋을 두 벌 만들어야 한다.
    """

    # Sentence.Kind 로 쓸 수 있게 붙여 둔다. Word.Category 와 같은 모양.
    Kind = SentenceKind

    # 시드가 "이미 넣은 항목" 을 찾을 때 쓰는 키.
    #
    # text 를 키로 쓰면 안 된다. 같은 문장이 다른 상황에서 나오는 것을
    # 일부러 허용하는데(unique 를 안 걸었다), 그 상태에서 --reset 을 돌리면
    # update_or_create 가 MultipleObjectsReturned 로 터진다.
    #
    # 사람이 Admin 에서 넣은 문장은 비어 있다. 그래서 unique 가 아니라
    # UniqueConstraint 로 "빈 값이 아닐 때만" 유일하게 만든다.
    slug = models.CharField("시드 키", max_length=100, blank=True)

    text = models.TextField("영어 문장")
    # 한글만 읽어도 통하게 적은 발음. 규칙은 apps/ai_pipeline/prompts/korean-reading.md.
    #
    # 문장에는 단어와 달리 "자세히" 를 두지 않는다. 길어서 화면이 감당하지
    # 못하고, 문장에서 정작 알아야 할 것은 단어 경계가 뭉개지는 것
    # ("Could you" -> "쿠쥬") 하나라 그건 표기 자체에 담긴다.
    #
    # 에러 메시지에도 넣는다. 눈으로 읽는 문장이지만 동료에게 말로 옮길
    # 일이 있다.
    #
    # 길이를 TextField 로 두는 이유는 text 와 같다 - 문장 길이에 상한을
    # 두면 긴 에러 메시지가 들어올 때 그 자리에서 막힌다.
    reading = models.TextField("한글 발음", blank=True)
    # 단어와 같은 이유로 발음을 따로 검수한다(Word.reading_reviewed 주석).
    reading_reviewed = models.BooleanField("발음 검수됨", default=False)
    translation = models.TextField("한글 해석")
    kind = models.CharField(
        "종류",
        max_length=20,
        choices=SentenceKind.choices,
        default=SentenceKind.PHRASE,
    )
    # 같은 문장이라도 어디서 나왔는지에 따라 뜻이 달라진다. 에러라면
    # 어떤 상황에서 뜨는지, 실무 표현이라면 누가 어떤 자리에서 쓰는지.
    context = models.CharField("나오는 상황", max_length=200, blank=True)
    description = models.TextField("설명", blank=True)

    class Meta:
        verbose_name = "문장"
        verbose_name_plural = "문장"
        ordering = ["id"]
        indexes = [
            # 목록이 항상 검수된 것만 보므로 정렬 키와 묶는다.
            models.Index(fields=["is_reviewed", "id"]),
        ]
        constraints = [
            # Word 와 같은 이유. choices 는 full_clean() 경로에서만 검사한다.
            models.CheckConstraint(
                condition=models.Q(
                    category__in=[*LearningItem.Category.values, ""]
                ),
                name="%(app_label)s_%(class)s_category_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=SentenceKind.values),
                name="%(app_label)s_%(class)s_kind_valid",
            ),
            # 과목도 같은 이유로 막는다. 위 category 주석 참고.
            models.CheckConstraint(
                condition=models.Q(
                    exam_subject__in=[*LearningItem.ExamSubject.values, ""]
                ),
                name="%(app_label)s_%(class)s_exam_subject_valid",
            ),
            # 정처기 범위가 아닌데 과목이 붙어 있으면 앞뒤가 안 맞는다.
            # 화면은 is_exam 으로 거르므로 그런 항목은 과목만 달린 채
            # 어디에도 안 나오고, Admin 에서 보면 정처기인 줄 알게 된다.
            models.CheckConstraint(
                condition=models.Q(is_exam=True) | models.Q(exam_subject=""),
                name="%(app_label)s_%(class)s_exam_subject_needs_flag",
            ),
            # slug 는 비어 있을 수 있으므로(Admin 에서 넣은 문장) unique=True 를
            # 못 쓴다. 빈 값이 아닐 때만 유일하게 만든다.
            #
            # 이게 없으면 시드를 두 터미널에서 동시에 돌렸을 때 같은 항목이
            # 두 벌 들어간다. get_or_create 의 재시도 안전장치는 DB 제약이
            # 있을 때만 작동한다.
            models.UniqueConstraint(
                fields=["slug"],
                condition=~models.Q(slug=""),
                name="%(app_label)s_%(class)s_slug_unique",
            ),
        ]

    def __str__(self) -> str:
        # 문장은 길어서 통째로 찍으면 Admin 목록이 읽기 어려워진다.
        head = self.text if len(self.text) <= 40 else f"{self.text[:40]}..."
        return f"[{self.get_kind_display()}] {head}"


class PhraseScene(models.TextChoices):
    """일상 표현을 쓰는 상황.

    LearningItem.Category 를 안 쓰는 이유: 그쪽 여덟 개가 전부 개발 분류
    (git·api·devops...)다. 거기에 "식당" 을 더하면 단어장 필터에도 그 항목이
    생기는데, 개발 단어를 보는 화면에 쓸 일이 없는 선택지가 늘어난다.

    모델 안에 중첩하지 않는 이유는 SentenceKind 와 같다 - Meta 의
    CheckConstraint 가 참조할 수 없다.

    **처음부터 다 만들지 않는다.** 60개에 실제로 쓰는 것만 두고, 표현이
    늘어 담을 곳이 없을 때 더한다. 미리 만들어두면 비어 있는 분류가
    화면 필터에 뜬다.
    """

    GREETING = "greeting", "인사·소개"
    SHOPPING = "shopping", "쇼핑·주문"
    ASKING = "asking", "묻기·길찾기"
    TROUBLE = "trouble", "곤란할 때"
    SMALLTALK = "smalltalk", "가벼운 대화"


class DailyPhrase(LearningItem):
    """일상 영어 표현 하나. 소리내어 말하는 연습에 쓴다.

    **Word 에 섞지 않고 표를 따로 두는 이유는 취향이 아니라 못 하기
    때문이다.** Word.term 이 unique=True 인데, 일상 영어의 기초 낱말이
    이미 개발 용어로 등록돼 있다 - 흔히 쓰는 32개를 세어보니 16개가
    충돌했다(commit·branch·cache·merge·push·pull·deploy·key·index·view·
    state·queue·stack·thread·port·token). 일상 영어 "commit(약속하다)" 을
    넣을 자리가 없다.

    unique 를 푸는 쪽도 검토했다. 안 되는 이유: 씨드 명령 넷과
    mark_exam_scope·generate_words 가 filter(term=...)·get_or_create(term=...)
    로 term 을 키처럼 쓴다. 제약을 풀면 그것들이 에러 없이 엉뚱한 행을
    집는다 - 오동작이라 한참 뒤에야 드러난다.

    두 번째 이유는 보기(오답) 풀이다. quiz.py 의 _pick_distractors 가 같은
    분류에서 먼저 뽑고 모자라면 **전체 풀에서** 채운다. 한 표에 두 종류가
    있으면 개발 용어 문제에 일상 표현 오답이 섞여 답이 뻔해진다.

    **낱말 하나가 아니라 표현이다.** "화장실이 어디예요" 를 못 말하는 것이
    일상 영어에서 막히는 지점이고, restroom 을 낱개로 외우는 것은 단어장이
    이미 하는 일이다. 그래서 text 에 여러 낱말이 들어온다.

    **정처기 필드(is_exam·exam_subject)는 이 표에서 안 쓴다.** LearningItem
    에서 물려받는 것이라 칸은 생기지만 항상 비어 있다. 상속의 대가로
    받아들였다 - 그 두 칸 때문에 추상을 하나 더 만들 이유는 안 된다.
    아래 CheckConstraint 가 값이 들어오는 것을 막는다.
    """

    # 낱말이 아니라 표현이라 term 이 아니라 text 다. Sentence 와 같은 이름을
    # 쓰는 이유는 둘 다 여러 낱말이기 때문이고, 그래서 채점도 낱말 단위다.
    #
    # unique=True 를 그대로 둔다. 같은 표현을 두 번 넣을 이유가 없고,
    # Word 와 다른 표라 개발 용어와는 안 부딪힌다.
    text = models.CharField("영어 표현", max_length=120, unique=True)

    # 상황. Category 를 안 쓰는 이유는 PhraseScene 주석에 있다.
    #
    # blank 를 허용하는 것은 Word.category 와 같은 이유다 - 아직 상황을
    # 못 정한 표현을 Admin 에서 받을 수 있어야 한다.
    scene = models.CharField(
        "상황", max_length=20, blank=True, choices=PhraseScene.choices
    )

    # IPA. **전체를 슬래시로 한 번만** 감싸고 안쪽은 낱말마다 공백으로
    # 끊는다. 개발 용어 361개가 전부 이 모양이라 두 갈래가 같아지고,
    # 화면이 갈래를 안 보고 같은 코드로 그린다.
    #
    # 낱말 경계가 필요한 이유: 화면이 wrong_at 으로 받은 자리를 강조하려면
    # text·pronunciation·reading 셋의 낱말 수가 같아야 한다.
    #
    # Word 와 달리 비워두지 않는다. 발음 연습이 이 표의 존재 이유이고,
    # 화면이 본보기를 IPA·한글발음으로 그린다(합성 음성이 없는 기계가
    # 있어서 "들어보기" 를 주된 장치로 못 쓴다). 비면 그 갈래에서 본보기가
    # 사라지므로 아래 제약으로 막는다.
    pronunciation = models.CharField("발음기호", max_length=200)

    # 한글만 읽어도 통하게 적은 발음. 규칙은 Word.reading 과 같고, 강세를
    # ** 로 감싼다(Reading 컴포넌트가 그것으로 굵게 그린다).
    #
    # **강세는 낱말 안에서 닫는다.** 공백을 걸치면(`**쏘r s**`) 공백으로
    # 세는 낱말 수가 어긋나 화면이 강조를 포기한다 - 개발 용어의
    # source map 이 실제로 그 상태다.
    reading = models.CharField("한글 발음", max_length=200)

    meaning = models.CharField("한글 뜻", max_length=200)

    class Meta:
        verbose_name = "일상 표현"
        verbose_name_plural = "일상 표현"
        ordering = ["text"]
        indexes = [
            # 출제가 항상 검수된 것만 보므로 Word 와 같은 모양으로 둔다.
            models.Index(fields=["is_reviewed", "text"]),
        ]
        constraints = [
            # choices 를 DB 에서도 막는다. 이유는 Word 쪽 주석과 같다 -
            # update_or_create·bulk_create 는 full_clean 을 안 타서
            # 목록에 없는 값이 그냥 저장되고, 화면에서 조용히 깨진다.
            models.CheckConstraint(
                condition=models.Q(scene__in=[*PhraseScene.values, ""]),
                name="%(app_label)s_%(class)s_scene_valid",
            ),
            # 발음이 비면 화면에 본보기가 없다. blank=False 는 폼에서만
            # 걸리므로 여기서도 막는다.
            models.CheckConstraint(
                condition=~models.Q(pronunciation="") & ~models.Q(reading=""),
                name="%(app_label)s_%(class)s_needs_pronunciation",
            ),
            # 이 표는 정처기와 무관하다. 값이 들어오면 Admin 에서 정처기
            # 범위처럼 보이는데 화면 어디에도 안 나온다.
            models.CheckConstraint(
                condition=models.Q(is_exam=False) & models.Q(exam_subject=""),
                name="%(app_label)s_%(class)s_not_exam",
            ),
        ]

    def __str__(self) -> str:
        return self.text
