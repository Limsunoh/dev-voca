"""계정 Admin.

기본 UserAdmin 을 그대로 쓸 수 없다. username 자리에 email 이 들어갔고,
기본 폼은 username 필드를 찾다가 터진다.
"""

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.db import transaction
from django.db.models import Case, F, QuerySet, Value, When
from rest_framework.authtoken.models import TokenProxy

from .models import AVATAR_PHOTO, LoginToken, User, name_taken, shorten_display_name


class LowercaseEmailMixin:
    """이메일을 저장할 값(소문자)으로, 대소문자 구분 없이 검사한다.

    폼의 기본 중복 검사는 글자가 똑같은지만 봐서, 대소문자만 다른 주소가
    검사를 지나 save() 에서 DB 제약에 걸려 500 이 된다. 대문자가 섞인 옛
    행이 있으면 500 도 안 나고 같은 주소의 계정이 둘 생겨 그 주소의 로그인이
    깨진다.
    """

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("이미 가입된 이메일입니다.")
        return email


class UserCreateForm(LowercaseEmailMixin, AdminUserCreationForm):
    """Admin 의 계정 추가 폼.

    UserCreationForm 이 아니라 AdminUserCreationForm 을 상속해야 한다.
    아래 add_fieldsets 가 쓰는 usable_password 필드가 Admin 전용 폼에만
    있어서, 일반 폼을 상속하면 추가 화면이 500 이 된다.
    """

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email",)


class UserEditForm(LowercaseEmailMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def clean_display_name(self) -> str:
        """저장할 때 다듬어지는 값으로 중복을 본다.

        폼의 기본 검사는 다듬기 전 값을 봐서, 다듬으면 같아지는 이름이 검사를
        지나 save() 에서 DB 제약에 걸려 500 이 된다. 규칙을 어긴 회원의 이름을
        바꾸는 자리라 500 으로 죽으면 안 된다.

        금칙어는 보지 않는다. 운영 계정의 이름은 이 화면에서 정한다.
        """
        name = shorten_display_name(self.cleaned_data["display_name"])
        if name and name_taken(name, exclude_pk=self.instance.pk):
            raise forms.ValidationError("이미 쓰고 있는 이름입니다.")
        return name


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
                "fields": ("display_name", "avatar", "google_picture", "daily_length"),
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


# DRF 가 붙여 둔 "토큰" 화면을 뗀다. 그 표는 이제 아무도 안 읽어서, 거기서 토큰을
# 지워도 아무도 로그아웃되지 않는다. 지웠으니 끊겼다고 믿게 되는 화면이다.
admin.site.unregister(TokenProxy)


@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    """기기별 로그인 토큰. 지우면 그 기기만 로그아웃된다.

    계정 전체를 막으려면 사용자의 "활성" 을 끈다. 토큰을 다 지워도 비밀번호를
    아는 사람은 다시 로그인한다.

    토큰 값은 보이지 않는다. 화면에 띄우면 관리자 화면을 본 사람이 그 기기로
    로그인한 것처럼 쓸 수 있다. 새로 만들 이유도 없어서 추가는 막는다.
    """

    list_display = ("user", "created")
    search_fields = ("user__email",)
    fields = ("user", "created")
    readonly_fields = ("user", "created")

    def get_queryset(self, request) -> QuerySet[LoginToken]:
        # 회원 행에서 사진 바이트는 빼고 붙인다(SlimTokenAuthentication 과 같은 이유).
        return super().get_queryset(request).select_related("user").defer("user__avatar_photo")

    def has_add_permission(self, request) -> bool:
        return False

    def lookup_allowed(self, lookup, value, request=None) -> bool:
        # 목록 주소의 검색어(?key__startswith=...)로 토큰 값을 거르지 못하게 한다.
        # Django 는 자기 표의 칸이면 list_filter 에 없어도 받아 주는데, 결과가 1건인지
        # 0건인지로 40자를 한 글자씩 맞힐 수 있다. 막으면 400 이 난다.
        if lookup.split("__", 1)[0] == "key":
            return False
        return super().lookup_allowed(lookup, value, request)
