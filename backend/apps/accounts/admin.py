"""계정 Admin.

기본 UserAdmin 을 그대로 쓸 수 없다. username 자리에 email 이 들어갔고,
기본 폼은 username 필드를 찾다가 터진다.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User


class UserCreateForm(AdminUserCreationForm):
    """Admin 의 계정 추가 폼.

    UserCreationForm 이 아니라 AdminUserCreationForm 을 상속해야 한다.
    아래 add_fieldsets 가 쓰는 usable_password 필드가 Admin 전용 폼에만
    있어서, 일반 폼을 상속하면 추가 화면이 통째로 500 이 된다.
    """

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    form = UserEditForm

    list_display = ("email", "display_name", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active")
    search_fields = ("email", "display_name")
    ordering = ("-date_joined",)
    readonly_fields = ("date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("정보", {"fields": ("display_name",)}),
        (
            "권한",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                # is_staff 를 켜면 검수 권한이 생긴다(apps.vocab.views.can_review).
                # 미검수 단어를 볼 수 있게 되므로 함부로 켜지 않는다.
                "description": "is_staff 를 켜면 미검수 단어를 조회하고 수정할 수 있습니다.",
            },
        ),
        ("기록", {"fields": ("date_joined", "last_login")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )
