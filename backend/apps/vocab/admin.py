from django.contrib import admin

from .models import Sentence, Word


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
    list_filter = ("is_reviewed", "reading_reviewed", "difficulty", "category")
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
    list_filter = ("is_reviewed", "reading_reviewed", "kind", "difficulty", "category")
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
