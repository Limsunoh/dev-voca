from django.urls import path

from .views import (
    AvatarPhotoFileView,
    AvatarPhotoView,
    EmailChangeConfirmView,
    EmailChangeRequestView,
    GoogleLoginView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    SignUpView,
)

app_name = "accounts"

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("google/", GoogleLoginView.as_view(), name="google"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path(
        "email-change/",
        EmailChangeRequestView.as_view(),
        name="email-change",
    ),
    path(
        "email-change/confirm/",
        EmailChangeConfirmView.as_view(),
        name="email-change-confirm",
    ),
    # 비밀번호 변경과 최초 설정이 같은 경로다. 구글로만 가입한 사람은
    # 비밀번호가 없어 "변경" 이 아니라 "설정" 이지만, 화면도 저장 경로도
    # 같아서 나누면 부르는 쪽이 먼저 판정해야 한다.
    path("password/", PasswordChangeView.as_view(), name="password"),
    path("photo/", AvatarPhotoView.as_view(), name="photo"),
    # 그림을 그대로 내려주는 자리. 위의 photo/ 와 달리 로그인이 필요 없다
    # (순위표가 남의 아바타를 그린다).
    # <uuid:> 라 형식이 안 맞는 값은 여기까지 오지도 않는다(404).
    path(
        "photo/<uuid:key>/",
        AvatarPhotoFileView.as_view(),
        name="photo-file",
    ),
]
