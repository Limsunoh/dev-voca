"""계정 API.

토큰을 응답 본문으로 돌려준다. 이 토큰은 브라우저가 아니라 Next 서버가
받아 httpOnly 쿠키에 넣는다 - 브라우저 자바스크립트가 토큰을 읽을 수 없어야
XSS 하나로 계정이 통째로 넘어가지 않는다.

그래서 이 API 는 브라우저가 직접 부르지 않는다. 단어·문장·문제풀기와 같은
경로(Next 중계)를 쓴다.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .google import GoogleAuthError, fetch_google_user
from .models import free_display_name
from .serializers import LoginSerializer, SignUpSerializer, UserSerializer

logger = logging.getLogger(__name__)
from .throttles import EmailRateThrottle, GoogleRateThrottle


def _auth_response(user: AbstractBaseUser, created: bool = False) -> Response:
    """토큰과 사용자 정보를 함께 돌려준다.

    두 번 왕복하지 않으려고 묶는다. 로그인 직후 화면이 바로 이름을
    보여줘야 하는데, 토큰만 주면 곧바로 내 정보를 또 물어야 한다.
    """
    token, _ = Token.objects.get_or_create(user=user)
    return Response(
        {"token": token.key, "user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


class SignUpView(APIView):
    """이메일 가입. 가입과 동시에 로그인된다.

    시도 제한은 같은 이메일을 반복해서 두드리는 것만 막는다. 이메일마다
    한 번씩 던져 가입 여부를 훑는 것은 이 제한으로 못 막는다 - 그건 요청
    주체를 알아야 세는데 백엔드는 전부 Next 서버로 보인다. 막으려면 실제
    클라이언트를 아는 Next 중계 쪽에 IP 제한을 둬야 한다.
    """

    permission_classes = [AllowAny]
    throttle_classes = [EmailRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return _auth_response(user, created=True)


class LoginView(APIView):
    """이메일 로그인.

    시도 제한이 없으면 한 계정의 비밀번호를 무한히 추측할 수 있다.
    백엔드가 공개 도메인이라 Next 중계를 건너뛰고 직접 두드릴 수 있다.
    """

    permission_classes = [AllowAny]
    throttle_classes = [EmailRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return _auth_response(serializer.validated_data["user"])


class GoogleLoginView(APIView):
    """구글 로그인. 계정이 없으면 만들고 있으면 그대로 들어온다.

    Next 서버가 구글에서 받은 코드를 넘긴다. 사용자 정보를 그대로 받지
    않는 이유: 그러면 누구든 남의 이메일을 적어 보내 그 계정으로 들어올
    수 있다. 코드를 받아 구글에 되물어 확인한다.

    이미 그 이메일로 계정이 있으면 새로 만들지 않고 붙는다. 안 묶으면
    같은 사람의 학습 기록이 두 계정으로 갈린다.

    **알려진 한계**: 구글은 "이 사람이 그 구글 계정의 주인" 임을 확인해줄
    뿐, 우리 DB 에 있던 그 행을 누가 만들었는지는 보증하지 않는다. 가입에
    메일 확인 절차가 없어서, 남의 주소로 미리 가입해두고 진짜 주인이
    구글로 들어오기를 기다리는 것이 가능하다. 그러면 두 사람이 같은
    계정을 쓰게 된다.

    막으려면 가입할 때 메일로 주소를 확인해야 한다. 토큰만 끊는 식으로는
    안 된다 - 먼저 가입한 쪽은 비밀번호를 알고 있어 곧바로 다시 받는다.
    반대로 두 방법을 번갈아 쓰는 정상 사용자는 구글로 들어올 때마다 다른
    기기에서 로그아웃된다. 얻는 것 없이 잃기만 한다.

    메일 확인을 붙이기 전까지는 이 한계를 안고 간다.
    """

    permission_classes = [AllowAny]
    # 누가 보냈는지로 나누지 않고 전체 합계로 센다. 이유는 throttles 에
    # 적어뒀다 - 요청자를 구분할 방법이 없어서 나누는 척하면 오히려 뚫린다.
    throttle_classes = [GoogleRateThrottle]

    def post(self, request: Request) -> Response:
        if not isinstance(request.data, dict):
            return Response(
                {"detail": "요청 형식이 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")

        if not isinstance(code, str) or not code.strip():
            return Response(
                {"detail": "구글 로그인 정보가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(redirect_uri, str) or not redirect_uri.strip():
            return Response(
                {"detail": "구글 로그인 정보가 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            info = fetch_google_user(code.strip(), redirect_uri.strip())
        except GoogleAuthError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        User = get_user_model()

        # 이메일은 저장할 때 소문자로 내려가므로 여기서도 맞춘다.
        email = info["email"].lower()

        # make_password(None) 로 비밀번호를 못 쓰는 값으로 넣는다. 만든 뒤
        # 따로 설정하면 그 사이에 password 가 빈 문자열인 행이 존재하고,
        # 그 상태로 로그인을 시도하면 400 이 아니라 500 이 난다.
        # 이름이 부딪히면 다시 뽑아 재시도한다. 뽑는 사이 다른 요청이 같은
        # 이름을 먼저 가져갈 수 있고, 그때 그냥 두면 IntegrityError 가 그대로
        # 올라가 500 이 된다. 사용자는 구글 로그인이 왜 안 되는지 알 수 없다.
        #
        # 두 번째는 이름을 비워 부른다. 그러면 save() 가 학습자1234 꼴로
        # 지어 넣어 부딪힐 여지가 거의 없다.
        for wanted in (info["name"], ""):
            try:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        # 구글이 준 이름을 첫 이름으로 쓴다. 이미 그 이름을
                        # 쓰는 사람이 있으면 뒤에 번호를 붙인다 - 동명이인
                        # 때문에 가입 자체가 막히면 안 된다.
                        "display_name": free_display_name(wanted),
                        "google_picture": info["picture"],
                        "password": make_password(None),
                    },
                )
                break
            except IntegrityError:
                continue
        else:
            logger.warning("구글 로그인에서 이름을 정하지 못했습니다: %s", email)
            return Response(
                {"detail": "잠시 후 다시 시도해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 사진은 로그인할 때마다 갱신한다. 구글에서 사진을 바꾸면 옛 주소가
        # 죽어서 깨진 그림이 남는다.
        #
        # 이름은 덮어쓰지 않는다. 사용자가 우리 화면에서 바꾼 이름이
        # 다음 로그인에 구글 이름으로 되돌아가면, 바꾼 것이 사라진 것처럼
        # 보이고 이유도 알 수 없다.
        if not created and user.google_picture != info["picture"]:
            user.google_picture = info["picture"]
            user.save(update_fields=["google_picture"])

        if not user.is_active:
            return Response(
                {"detail": "사용할 수 없는 계정입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _auth_response(user, created=created)


class LogoutView(APIView):
    """로그아웃. 토큰을 지운다.

    쿠키만 지우고 토큰을 남겨두면, 그 사이 토큰이 새어나간 경우 계속
    쓸 수 있다. 서버에서도 무효로 만든다.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """내 정보 조회와 수정.

    화면을 새로 그릴 때 쿠키의 토큰이 아직 유효한지 확인하는 용도로도
    쓴다. 토큰이 없거나 만료면 401 이 오고, 화면은 로그아웃 상태로 그린다.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
