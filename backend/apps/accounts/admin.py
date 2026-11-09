"""계정 Admin.

기본 UserAdmin 을 그대로 쓸 수 없다. username 자리에 email 이 들어갔고,
기본 폼은 username 필드를 찾다가 터진다.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.db import transaction
from django.db.models import Case, F, Value, When

from .models import AVATAR_PHOTO, User


class UserCreateForm(AdminUserCreationForm):
    """Admin 의 계정 추가 폼.

    UserCreationForm 이 아니라 AdminUserCreationForm 을 상속해야 한다.
    아래 add_fieldsets 가 쓰는 usable_password 필드가 Admin 전용 폼에만
    있어서, 일반 폼을 상속하면 추가 화면이 500 이 된다.
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
    actions = ("delete_uploaded_photo",)
    readonly_fields = (
        "date_joined",
        "last_login",
        "terms_agreed_at",
        "terms_version",
        "age_confirmed_at",
        "last_seen_on",
        "purge_notice_sent_at",
    )

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "정보",
            {
                "fields": ("display_name", "avatar", "google_picture"),
                # google_picture 는 구글이 주는 값이라 손으로 고칠 것이
                # 아니지만, 사진이 안 뜬다는 문의가 왔을 때 무엇이 저장돼
                # 있는지 봐야 해서 열어둔다.
                "description": "보여지는 이름은 대소문자를 구분하지 않고 중복될 수 없습니다.",
            },
        ),
        (
            "권한",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                # is_staff 를 켜면 검수 권한이 생긴다(apps.vocab.views.can_review).
                # 미검수 단어를 볼 수 있게 되므로 함부로 켜지 않는다.
                "description": "is_staff 를 켜면 미검수 단어를 조회하고 수정할 수 있습니다.",
            },
        ),
        (
            "기록",
            {
                "fields": (
                    "date_joined",
                    "last_login",
                    "terms_agreed_at",
                    "terms_version",
                    "age_confirmed_at",
                    "last_seen_on",
                    "purge_notice_sent_at",
                ),
            },
        ),
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

    @admin.action(description="올린 사진 지우기", permissions=["change"])
    def delete_uploaded_photo(self, request, queryset) -> None:
        """약관을 어긴 사진을 지운다. 사진은 올릴 때 자동으로 거르지 않는다.

        내정보의 사진 삭제(AvatarPhotoView.delete)와 결과가 같아야 한다.
        avatar 가 사진을 가리키고 있었으면 비워서 원래 규칙으로 돌아가고,
        다른 아바타를 골라 둔 사람은 그대로 둔다.

        사진 칸을 읽지 않으려고 update 로 한 번에 지운다. 되돌릴 수 없으니
        이의 제기에 답할 수 있게 회원별로 작업 기록을 남긴다.
        """
        targets = queryset.filter(avatar_photo_key__isnull=False)
        # 지운 사진과 남긴 기록이 어긋나지 않게 한 묶음으로 처리한다.
        with transaction.atomic():
            members = list(targets.select_for_update().only("email"))
            targets.update(
                avatar_photo=None,
                avatar_photo_key=None,
                avatar_photo_at=None,
                avatar=Case(When(avatar=AVATAR_PHOTO, then=Value("")), default=F("avatar")),
            )
            for member in members:
                self.log_change(request, member, "올린 사진을 지웠습니다.")
        self.message_user(request, f"사진 {len(members)}장을 지웠습니다.")
