from django.contrib import admin

from .models import Word


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("term", "meaning", "difficulty", "category", "is_reviewed")
    list_filter = ("is_reviewed", "difficulty", "category")
    search_fields = ("term", "meaning", "description")
    list_editable = ("is_reviewed",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("term", "meaning", "description")}),
        ("예문", {"fields": ("example", "example_translation")}),
        ("분류", {"fields": ("difficulty", "category", "source")}),
        ("검수", {"fields": ("is_reviewed", "created_at", "updated_at")}),
    )

    @admin.action(description="선택한 단어를 검수 완료로 표시")
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(is_reviewed=True)
        self.message_user(request, f"{updated}개 단어를 검수 완료로 표시했습니다.")

    actions = ["mark_reviewed"]
