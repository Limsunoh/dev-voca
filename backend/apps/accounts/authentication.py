"""토큰 인증.

기본 TokenAuthentication 을 그대로 쓰지 않는 이유가 셋이다. 기기별 토큰
(LoginToken)을 보는 것, 사진 바이트를 안 끌고 오는 것, 마지막 이용일을
남기는 것이다.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication

from .models import LoginToken


def _mark_seen(user) -> None:
    """마지막 이용일을 오늘로 적는다. 하루에 한 번만 쓴다.

    1년 미접속 파기(accounts.purge)가 이 값을 본다. last_login 은 쓸 수 없다.
    회원 로그인은 토큰을 바로 내주는 구조라 그 칸이 찍히지 않고, 토큰에
    만료도 없어서 로그인 시각은 이용 시각을 대신하지 못한다.

    파기 안내가 나간 뒤 돌아온 사람은 안내를 비운다. 그래야 다시 1년을 센다.
    """
    today = timezone.localdate()
    if user.last_seen_on == today:
        return

    type(user).objects.filter(pk=user.pk).update(
        last_seen_on=today, purge_notice_sent_at=None
    )
    user.last_seen_on = today
    user.purge_notice_sent_at = None


class SlimTokenAuthentication(TokenAuthentication):
    """토큰으로 사용자를 찾을 때 사진 바이트를 안 끌고 온다.

    기본 구현은 `select_related("user")` 를 컬럼 제한 없이 부른다. 그러면
    `accounts_user` 의 모든 칸이 딸려오는데, 거기에 `avatar_photo` 가 있다.
    한 장이 10~20KB 라, 그대로 두면 단어 목록·문제풀기·순위표까지 로그인한
    사람의 모든 API 요청이 그 무게를 진다. 화면 하나 그리는 데 /me/ 를 한 번
    부르므로 이동할 때마다 또 진다.

    models.py 의 avatar_photo 주석이 "행이 무거워지는 것보다 읽히는 자리가
    문제인데 그건 어느 질의에도 안 실어서 푼다" 고 적어뒀는데, 그 불변식을
    지키는 자리가 여기다. 여기를 빼면 그 주석이 틀린 말이 된다.

    `defer` 로 그 칸 하나만 뺀다. 지연 로드가 걱정될 수 있지만, 인증을
    통과한 뒤 `avatar_photo` 를 실제로 읽는 코드는 AvatarPhotoFileView
    하나뿐이고 그쪽은 자기 `only()` 로 따로 조회한다. 그래서 지연 로드가
    발동할 자리가 없다.
    """

    # DRF 기본값은 계정당 하나인 authtoken.Token 이다(LoginToken 주석).
    model = LoginToken

    def authenticate_credentials(self, key):
        model = self.get_model()
        try:
            token = (
                model.objects.select_related("user")
                .defer("user__avatar_photo")
                .get(key=key)
            )
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed(_("Invalid token.")) from None

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed(_("User inactive or deleted."))

        _mark_seen(token.user)

        return (token.user, token)
