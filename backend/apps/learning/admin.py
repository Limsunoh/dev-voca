"""학습 기록 Admin.

**보기 전용이다.** 여기 표는 전부 서버가 채점하며 쓰는 기록이다. 손으로
고친 값은 쓰는 쪽의 규칙(하루에는 최고 한 판만, 일일공부는 답마다 쌓이고
낮아지지 않음)을 거치지 않아서, 고친 줄만 규칙과 어긋난 채 남는다.

지울 수 있는 것은 판(문제풀기 기록) 하나다. 이상한 점수를 순위표에서
치우는 것이 이 화면의 쓰임이다. 판을 지우면 그날 하루 점수를 다시 센다 -
하루 점수는 "그날 최고 판의 점수" 를 복사해 둔 값이라, 판만 지우면
이번 주·전체 순위표에서는 빠지는데 꾸준함에는 남는다. 그 판이 남긴 복습
상태(오답 표시)는 되돌리지 않는다.

일일공부는 지우지 못하게 둔다. "하루 한 번" 을 그날 일일공부 줄이 있느냐로
지키므로, 줄을 지우면 그 사람은 그날 일일공부를 처음부터 다시 풀 수 있다.

**지운 판은 되살아날 수 있다.** 판이 두 번 남지 않는 것은 판 식별자의
유일 제약 덕분인데, 판을 지우면 그 식별자가 빈다. 끝내기 토큰은 10분
동안 유효해서(session.py), 그 안에 같은 토큰을 다시 보내면 같은 점수의
판이 새로 남는다. 막으려면 지운 식별자를 따로 남겨야 한다.
"""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction

from . import record
from .models import DailyScore, DailyStudy, QuizAnswer, QuizSession, ReviewState

USER_SEARCH = ("user__email", "user__display_name")


class ViewOnlyAdmin(admin.ModelAdmin):
    """추가·수정 없이 보기만. deletable 을 켠 것만 지울 수 있다.

    **has_delete_permission 은 막지 않는다.** 사용자를 지울 때 Django 는
    함께 지워질 모델마다 그 Admin 의 이 값을 묻고, 하나라도 False 면 사용자
    삭제 전체를 거절한다. 여기서 막으면 판을 한 번이라도 한 사람은 Admin
    에서 지울 수 없게 된다. 대신 이 표를 **직접** 지우는 입구 셋(목록의
    일괄 삭제, 상세의 삭제 링크, 삭제 화면)을 닫는다.

    슈퍼유저가 아닌 staff 가 사용자를 지우려면 이 표들의 지우기 권한
    (delete_dailyscore 등)도 있어야 한다. 표를 Admin 에 붙이면 Django 가
    그렇게 묻기 때문이다 - 권한을 나눠 줄 때 같이 준다.
    """

    deletable = False
    list_select_related = ("user",)
    search_fields = USER_SEARCH

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.deletable:
            actions.pop("delete_selected", None)
        return actions

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "show_delete": self.deletable}
        return super().change_view(request, object_id, form_url, extra_context)

    def delete_view(self, request, object_id, extra_context=None):
        if not self.deletable:
            raise PermissionDenied
        return super().delete_view(request, object_id, extra_context)


class QuizAnswerInline(admin.TabularInline):
    model = QuizAnswer
    extra = 0
    can_delete = False
    fields = ("kind", "target_type", "target_id", "is_correct", "is_skipped", "elapsed_ms", "score")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QuizSession)
class QuizSessionAdmin(ViewOnlyAdmin):
    deletable = True
    list_display = ("finished_at", "user", "kind", "score", "answered", "correct", "skipped")
    list_filter = ("kind",)
    search_fields = USER_SEARCH + ("token_id",)
    date_hierarchy = "finished_at"
    inlines = (QuizAnswerInline,)

    def delete_model(self, request, obj):
        user_id, day = obj.user_id, obj.day
        super().delete_model(request, obj)
        record.recount_best_free(user_id, day)

    def delete_queryset(self, request, queryset):
        # 여러 판을 지워도 (사람, 날) 한 쌍은 한 번만 센다. 정렬은 하루
        # 점수 줄을 잠그는 순서를 고정하려는 것이다 - 두 관리자가 서로 다른
        # 판을 지우며 같은 날들을 반대 순서로 잠그면 교착이 난다.
        days = sorted({(one.user_id, one.day) for one in queryset})
        with transaction.atomic():
            super().delete_queryset(request, queryset)
            for user_id, day in days:
                record.recount_best_free(user_id, day)


@admin.register(DailyScore)
class DailyScoreAdmin(ViewOnlyAdmin):
    list_display = ("day", "user", "best_free_score", "daily_study_score", "streak_points")
    date_hierarchy = "day"

    # "꾸준함 점수" 라고 부르지 않는다. 꾸준함 순위표는 이 값이 0 보다 큰
    # 날 수로 매기므로, 그 이름이면 여기 42 를 순위표의 "3일" 과 맞춰 보게 된다.
    @admin.display(description="하루 점수")
    def streak_points(self, obj):
        return obj.total


@admin.register(DailyStudy)
class DailyStudyAdmin(ViewOnlyAdmin):
    list_display = (
        "day",
        "user",
        "length",
        "answered",
        "total_questions",
        "correct",
        "score",
        "finished_at",
    )
    list_filter = ("length",)
    date_hierarchy = "day"


@admin.register(ReviewState)
class ReviewStateAdmin(ViewOnlyAdmin):
    list_display = ("user", "target_type", "target_id", "is_wrong", "streak", "last_correct_at")
    list_filter = ("target_type", "is_wrong")
