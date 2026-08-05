from django.contrib import admin

from .models import Sentence, Word


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("term", "pronunciation", "meaning", "difficulty", "category", "is_reviewed")
    list_filter = ("is_reviewed", "difficulty", "category")
    search_fields = ("term", "meaning", "description")
    list_editable = ("is_reviewed",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("term", "pronunciation", "meaning", "description")}),
        ("예문", {"fields": ("example", "example_translation")}),
        ("분류", {"fields": ("difficulty", "category", "source")}),
        ("검수", {"fields": ("is_reviewed", "created_at", "updated_at")}),
    )

    @admin.action(description="선택한 단어를 검수 완료로 표시")
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(is_reviewed=True)
        self.message_user(request, f"{updated}개 단어를 검수 완료로 표시했습니다.")

    actions = ["mark_reviewed"]


@admin.register(Sentence)
class SentenceAdmin(admin.ModelAdmin):
    list_display = ("short_text", "translation", "kind", "category", "is_reviewed")
    list_filter = ("is_reviewed", "kind", "difficulty", "category")
    search_fields = ("text", "translation", "context", "description")
    list_editable = ("is_reviewed",)
    readonly_fields = ("created_at", "updated_at")
    # 검수 대기를 위로 올린다. 검수하러 들어와서 찾아 헤매지 않게.
    ordering = ("is_reviewed", "id")
    fieldsets = (
        (None, {"fields": ("text", "translation")}),
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

    actions = ["mark_reviewed"]
