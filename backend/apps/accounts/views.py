"""계정 API.

토큰을 응답 본문으로 돌려준다. 이 토큰은 브라우저가 아니라 Next 서버가
받아 httpOnly 쿠키에 넣는다 - 브라우저 자바스크립트가 토큰을 읽을 수 없어야
XSS 하나로 계정이 통째로 넘어가지 않는다.

그래서 이 API 는 브라우저가 직접 부르지 않는다. 단어·문장·문제풀기와 같은
경로(Next 중계)를 쓴다.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, SignUpSerializer, UserSerializer
from .throttles import EmailRateThrottle


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
