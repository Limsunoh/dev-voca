from django.contrib import admin

from .models import DailyPhrase, Sentence, Word


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = (
        "term",
        "pronunciation",
        "reading",
        "meaning",
        "difficulty",
        "category",
        "is_reviewed",
        "reading_reviewed",
    )
    list_filter = (
        "is_reviewed",
        "reading_reviewed",
        "difficulty",
        "category",
        # 정처기 범위인데 과목이 안 붙은 것을 찾는 데 쓴다. 그 상태는
        # 허용되지만(아직 안 정한 것) 과목 필터로는 영영 안 나온다.
        "is_exam",
        "exam_subject",
    )
    search_fields = ("term", "meaning", "description")
    list_editable = ("is_reviewed", "reading_reviewed")
    readonly_fields = ("created_at", "updated_at")
    # **발음을 별도 묶음으로 둔다.** fieldsets 가 명시적이라 여기 없는
    # 필드는 폼에 아예 안 나온다 - 칸을 만들어놓고 이 목록에 안 넣으면
    # 관리자가 발음을 검수할 방법이 없어 화면에 영영 안 뜬다.
    fieldsets = (
        (None, {"fields": ("term", "pronunciation", "meaning", "description")}),
        (
            "발음",
            {
                "fields": ("reading", "reading_note", "reading_reviewed"),
                "description": (
                    "한글만 읽어도 통하게 적는다. 규칙은 apps/ai_pipeline/prompts/korean-reading.md. "
                    "강세는 **이렇게** 감싸면 화면에서 굵게 나온다(별표 짝을 "
                    "맞출 것 - 안 맞으면 엉뚱한 곳이 굵어지는데 티가 안 난다). "
                    "검수 전에는 화면에 안 나간다."
                ),
            },
        ),
        ("예문", {"fields": ("example", "example_translation")}),
        ("분류", {"fields": ("difficulty", "category", "source")}),
        (
            "정처기",
            {
                "fields": ("is_exam", "exam_subject"),
                "description": (
                    "분류와 다른 축이다. 한 항목이 CS 기초이면서 정처기 4과목일 수 있다. "
                    "과목을 채우려면 먼저 '정처기 범위' 를 켜야 한다 - 안 켜고 과목만 "
                    "고르면 DB 가 거절한다(어디에도 안 나오는 항목이 되기 때문)."
                ),
            },
        ),
        ("검수", {"fields": ("is_reviewed", "created_at", "updated_at")}),
    )

    @admin.action(description="선택한 단어를 검수 완료로 표시")
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(is_reviewed=True)
        self.message_user(request, f"{updated}개 단어를 검수 완료로 표시했습니다.")

    @admin.action(description="선택한 단어의 발음을 검수 완료로 표시")
    def mark_reading_reviewed(self, request, queryset):
        """발음만 따로 켠다.

        단어 검수와 나누는 이유: 배치로 발음을 채우면 단어는 이미 검수가
        끝났고 발음만 미검수인 상태가 된다. is_reviewed 로는 그 상태를
        나타낼 수 없다.
        """
        updated = queryset.update(reading_reviewed=True)
        self.message_user(request, f"{updated}개 단어의 발음을 검수 완료로 표시했습니다.")

    actions = ["mark_reviewed", "mark_reading_reviewed"]


@admin.register(Sentence)
class SentenceAdmin(admin.ModelAdmin):
    list_display = (
        "short_text",
        "translation",
        "kind",
        "category",
        "is_reviewed",
        "reading_reviewed",
    )
    list_filter = (
        "is_reviewed",
        "reading_reviewed",
        "kind",
        "difficulty",
        "category",
        # 단어 쪽과 같은 이유. 위 WordAdmin 주석 참고.
        "is_exam",
        "exam_subject",
    )
    search_fields = ("text", "translation", "context", "description")
    list_editable = ("is_reviewed", "reading_reviewed")
    readonly_fields = ("created_at", "updated_at")
    # 검수 대기를 위로 올린다. 검수하러 들어와서 찾아 헤매지 않게.
    ordering = ("is_reviewed", "id")
    fieldsets = (
        (None, {"fields": ("text", "translation")}),
        (
            "발음",
            {
                # 문장에는 설명 칸이 없다. 길어서 화면이 감당하지 못한다.
                "fields": ("reading", "reading_reviewed"),
                "description": (
                    "단어 경계가 뭉개지는 것을 그대로 적는다"
                    '("Could you" -> "쿠쥬"). 규칙은 apps/ai_pipeline/prompts/korean-reading.md.'
                ),
            },
        ),
        ("맥락", {"fields": ("kind", "context", "description")}),
        ("분류", {"fields": ("difficulty", "category", "source")}),
        (
            "정처기",
            {
                "fields": ("is_exam", "exam_subject"),
                "description": (
                    "분류와 다른 축이다. 한 항목이 CS 기초이면서 정처기 4과목일 수 있다. "
                    "과목을 채우려면 먼저 '정처기 범위' 를 켜야 한다 - 안 켜고 과목만 "
                    "고르면 DB 가 거절한다(어디에도 안 나오는 항목이 되기 때문)."
                ),
            },
        ),
        ("검수", {"fields": ("is_reviewed", "created_at", "updated_at")}),
    )

    @admin.display(description="문장")
    def short_text(self, obj: Sentence) -> str:
        """목록에서는 앞부분만. 문장을 통째로 찍으면 표가 읽기 어려워진다."""
        return obj.text if len(obj.text) <= 60 else f"{obj.text[:60]}..."

    @admin.action(description="선택한 문장을 검수 완료로 표시")
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(is_reviewed=True)
        self.message_user(request, f"{updated}개 문장을 검수 완료로 표시했습니다.")

    @admin.action(description="선택한 문장의 발음을 검수 완료로 표시")
    def mark_reading_reviewed(self, request, queryset):
        """발음만 따로 켠다. 이유는 WordAdmin 쪽 주석과 같다."""
        updated = queryset.update(reading_reviewed=True)
        self.message_user(request, f"{updated}개 문장의 발음을 검수 완료로 표시했습니다.")

    actions = ["mark_reviewed", "mark_reading_reviewed"]


@admin.register(DailyPhrase)
class DailyPhraseAdmin(admin.ModelAdmin):
    """일상 표현 검수 화면.

    소리내어 읽기(일상영어)에만 쓰는 표다. 단어장·문제풀기에는 안 나온다.
    """

    list_display = (
        "text",
        "pronunciation",
        "reading",
        "meaning",
        "scene",
        "difficulty",
        "is_reviewed",
    )
    list_filter = ("is_reviewed", "scene", "difficulty")
    search_fields = ("text", "meaning")
    list_editable = ("is_reviewed",)
    readonly_fields = ("created_at", "updated_at")

    # **fieldsets 가 명시적이라 여기 없는 필드는 폼에 아예 안 나온다.**
    # WordAdmin 쪽 주석과 같은 함정이다 - 칸을 만들어놓고 이 목록에서
    # 빠뜨리면 관리자가 그 값을 고칠 방법이 없다.
    #
    # **일부러 뺀 것 셋**: category·is_exam·exam_subject 다. LearningItem
    # 에서 물려받았지만 이 표에서는 안 쓰고, DB 제약이 값이 들어오는 것을
    # 막는다(not_exam). 폼에 두면 관리자가 채울 수 있는 것처럼 보이는데
    # 저장하면 거절당한다 - 그게 더 나쁘다.
    #
    # 상황(scene)이 category 를 대신한다. 이유는 PhraseScene 주석에 있다.
    fieldsets = (
        (None, {"fields": ("text", "meaning")}),
        (
            "발음",
            {
                "fields": ("pronunciation", "reading"),
                "description": (
                    "**낱말 수를 셋 다 맞춰야 한다.** 표현·발음기호·한글발음의 "
                    "낱말 수가 같아야 화면이 틀린 낱말만 짚어줄 수 있고, "
                    "하나라도 어긋나면 그 표현은 강조 없이 통째로 그려진다. "
                    "발음기호는 바깥만 슬래시로 한 번 감싸고(/wɛr ɪz ðə/) "
                    "안쪽은 낱말마다 공백으로 끊는다. 한글발음의 강세는 "
                    "**이렇게** 감싸되 낱말 안에서 닫을 것 - 공백을 걸치면 "
                    "낱말 수가 어긋난다. 두 칸을 비우면 DB 가 거절한다."
                ),
            },
        ),
        (
            "분류",
            {
                "fields": ("scene", "difficulty", "source"),
                "description": (
                    "난이도는 낱말 수가 아니라 **발음이 어려운 정도**로 준다. "
                    "thank you 는 세 낱말이어도 쉬움이고 comfortable 은 한 "
                    "낱말이어도 어려움이다."
                ),
            },
        ),
        (
            "검수",
            {
                "fields": ("is_reviewed", "created_at", "updated_at"),
                "description": (
                    "검수 전에는 출제되지 않는다. 그리고 약어·숫자·기호가 "
                    "들어간 표현은 검수해도 출제되지 않는다 - 소리로 채점할 "
                    "수 없어서 걸러진다(apps/vocab/talk.py 의 is_speakable). "
                    "넣었는데 안 나오면 그것을 먼저 확인할 것."
                ),
            },
        ),
    )
