"""계정 API.

토큰을 응답 본문으로 돌려준다. 이 토큰은 브라우저가 아니라 Next 서버가
받아 httpOnly 쿠키에 넣는다 - 브라우저 자바스크립트가 토큰을 읽을 수 없어야
XSS 하나로 계정이 통째로 넘어가지 않는다.

그래서 이 API 는 브라우저가 직접 부르지 않는다. 단어·문장·문제풀기와 같은
경로(Next 중계)를 쓴다.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_change import (
    InvalidToken as InvalidEmailChangeToken,
)
from .email_change import (
    build_mail as build_email_change_mail,
)
from .email_change import (
    make_token as make_email_change_token,
)
from .email_change import (
    read_token as read_email_change_token,
)
from .google import GoogleAuthError, fetch_google_user
from .mail import MailNotConfigured, send_account_mail
from .models import AVATAR_PHOTO, free_display_name
from .serializers import (
    AvatarPhotoSerializer,
    EmailChangeRequestSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    SignUpSerializer,
    UserSerializer,
)
from .throttles import (
    AvatarPhotoThrottle,
    EmailChangeConfirmThrottle,
    EmailChangeThrottle,
    EmailRateThrottle,
    GoogleRateThrottle,
    PasswordChangeThrottle,
)

logger = logging.getLogger(__name__)


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


class PasswordChangeView(APIView):
    """비밀번호 변경. 처음 설정하는 것도 여기서 받는다.

    **다른 기기의 토큰을 끊고 지금 기기만 새 토큰을 받는다.**

    끊는 이유: 비밀번호를 바꾸는 이유가 보통 "누가 내 계정에 들어와
    있다" 다. 비밀번호만 바꾸고 토큰을 남기면 그 사람이 이미 받아둔
    토큰으로 계속 들어온다 - 바꾼 이유가 해결되지 않는다. 토큰에 만료가
    없어서(로그아웃할 때만 지워진다) 저절로 풀리지도 않는다.

    지금 기기를 남기는 이유: 바꾸자마자 401 이 되면 화면이 로그인으로
    튕긴다. 사용자는 비밀번호가 바뀐 건지 실패한 건지 알 수 없고, 새
    비밀번호로 다시 로그인해보기 전까지는 확인할 방법이 없다.

    그래서 지우고 새로 만든다. get_or_create 로는 안 된다 - 그건 있던
    토큰을 그대로 돌려주므로 다른 기기가 안 끊긴다. _auth_response 를
    쓸 수 없는 이유가 이것이다.

    새 토큰은 Next 서버가 받아 쿠키를 덮어쓴다. 응답 모양을 로그인과
    같게 두어 그쪽이 같은 코드로 처리하게 한다.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordChangeThrottle]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        # 비밀번호를 먼저 저장한다. 토큰을 먼저 끊으면, 저장이 실패했을 때
        # 비밀번호는 그대로인데 모든 기기가 로그아웃된 상태로 남는다.
        was_unusable = serializer.validated_data["was_unusable"]
        serializer.save()

        # 이 계정의 토큰을 전부 지운다. 지금 요청이 들고 온 것까지 포함해서다 -
        # 남겨두고 재사용하면 "다른 기기를 끊었다" 가 성립하지 않는다.
        # 지금 기기는 바로 아래에서 새 토큰을 받는다.
        Token.objects.filter(user=request.user).delete()
        token = Token.objects.create(user=request.user)

        return Response(
            {
                "token": token.key,
                "user": UserSerializer(request.user).data,
                # 처음 설정한 것인지 바꾼 것인지. 화면 문구가 갈린다
                # ("비밀번호를 설정했습니다" / "비밀번호를 바꿨습니다").
                # 화면이 다시 판정하지 못한다 - 저장 뒤에는 양쪽 다
                # 비밀번호가 있는 상태다.
                "created": was_unusable,
            },
            status=status.HTTP_200_OK,
        )


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


class EmailChangeRequestView(APIView):
    """이메일 변경 신청. 새 주소로 확인 메일을 보낸다.

    여기서는 아무것도 바뀌지 않는다. 주소를 바꾸는 것은 링크를 누른
    다음이다 - 왜 그렇게 나눴는지는 email_change.py 머리말에 있다.
    """

    permission_classes = [IsAuthenticated]
    # 확인 메일을 보내는 자리라 제한을 건다. 없으면 남의 주소로 반복해서
    # 신청을 걸어 우리 이름으로 메일 폭탄을 보내는 통로가 된다. 로그인이
    # 필요하다는 것만으로는 못 막는다 - 계정 하나면 무제한이 된다.
    throttle_classes = [EmailChangeThrottle]

    def post(self, request: Request) -> Response:
        serializer = EmailChangeRequestSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data["new_email"]

        token = make_email_change_token(
            user_id=request.user.pk,
            current_email=request.user.email,
            new_email=new_email,
        )

        # 링크는 화면(Next) 주소로 만든다. 요청 헤더에서 뽑지 않는 이유는
        # settings 의 FRONTEND_BASE_URL 주석에 적어뒀다.
        link = f"{settings.FRONTEND_BASE_URL}/profile/email/{token}"
        subject, body = build_email_change_mail(link=link)

        try:
            send_account_mail(to=new_email, subject=subject, body=body)
        except MailNotConfigured:
            # 발송 계정이 없는 상태. 사용자 잘못이 아니라 서버 설정 문제다.
            logger.exception("이메일 변경 확인 메일을 보내지 못했습니다")
            return Response(
                {"detail": "지금은 확인 메일을 보낼 수 없습니다. 잠시 후 다시 시도해주세요."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except OSError:
            # SMTP 가 거절하거나 연결이 끊긴 경우. fail_silently 를 꺼뒀으므로
            # 여기로 온다. 조용히 성공으로 넘기면 사용자는 오지 않을 메일을
            # 기다리며 스팸함만 뒤진다.
            logger.exception("이메일 변경 확인 메일 발송에 실패했습니다")
            return Response(
                {"detail": "확인 메일을 보내지 못했습니다. 잠시 후 다시 시도해주세요."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"sent_to": new_email}, status=status.HTTP_202_ACCEPTED)


class EmailChangeConfirmView(APIView):
    """확인 링크를 눌렀을 때. 여기서 주소가 바뀐다.

    로그인을 요구하지 않는다. 메일을 다른 기기에서 열 수 있어야 하고,
    그 기기에 우리 로그인이 없을 수 있다. 토큰 자체가 증거다.

    **토큰이 유효한 것만으로는 부족하다.** 만든 시점과 쓰는 시점 사이에
    상황이 달라질 수 있어서, 쓸 때 다시 본다:
    - 그 사이 주소가 또 바뀌었나 (토큰에 담아둔 옛 주소와 대조)
    - 그 사이 다른 사람이 그 주소로 가입했나
    """

    permission_classes = [AllowAny]
    # 로그인 없이 열리는 자리라 제한을 건다. 서명을 무작위로 찔러보는 것을
    # 막는다. 뚫릴 가능성 자체는 낮지만, 시도를 공짜로 두면 안 된다.
    #
    # 신청 쪽과 다른 통을 쓴다. 여기는 통 하나를 모두가 나눠 쓰기 때문에,
    # 신청 쪽의 좁은 요율을 그대로 쓰면 아무나 그것을 태워 전원의 확인을
    # 막을 수 있다.
    throttle_classes = [EmailChangeConfirmThrottle]

    def post(self, request: Request) -> Response:
        token = request.data.get("token") if isinstance(request.data, dict) else None
        if not isinstance(token, str) or not token.strip():
            return Response(
                {"detail": "확인 링크가 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id, old_email, new_email = read_email_change_token(token.strip())
        except InvalidEmailChangeToken as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()

        # 잠근 채로 읽는다. 같은 링크를 두 번 눌렀을 때 두 요청이 나란히
        # 검사를 통과하는 것을 막는다.
        with transaction.atomic():
            try:
                user = User.objects.select_for_update().get(pk=user_id)
            except User.DoesNotExist:
                return Response(
                    {"detail": "확인 링크가 올바르지 않습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 정지된 계정을 링크로 되살릴 수 없게 한다. 아래
            # _auth_response 가 **새 토큰을 발급**하므로, 이 검사가 없으면
            # 정지 직전에 신청해둔 링크를 눌러 계정이 되살아난다. 기존
            # 토큰을 끊어도 소용없다 - 이 경로가 새로 내주기 때문이다.
            # 문구는 GoogleLoginView 와 같게 둔다.
            if not user.is_active:
                return Response(
                    {"detail": "사용할 수 없는 계정입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 신청 당시의 주소와 지금 주소가 다르면 그 사이에 또 바뀐 것이다.
            # 그대로 진행하면 나중에 바꾼 주소가 옛 주소로 되돌아간다.
            if user.email.lower() != old_email:
                return Response(
                    {"detail": "이미 처리되었거나 만료된 링크입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 신청 뒤에 다른 사람이 그 주소로 가입했을 수 있다. 여기서 안
            # 보면 아래 save 가 IntegrityError 로 500 이 된다.
            if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
                return Response(
                    {"detail": "이미 가입된 이메일입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.email = new_email
            try:
                # **savepoint 안에서 저장한다.** 바깥 atomic 을 안 깨기
                # 위해서다 - IntegrityError 가 나면 그 커넥션에 "롤백이
                # 필요함" 이 서고, 그 상태로 쿼리를 더 하면
                # TransactionManagementError 가 난다. 지금은 잡은 뒤 곧바로
                # return 이라 넘어가지만, 이 아래에 한 줄이라도 쿼리가
                # 늘어나는 순간 400 이 500 으로 바뀐다.
                # session.py 의 _take_step 과 같은 모양이다.
                with transaction.atomic():
                    user.save(update_fields=["email"])
            except IntegrityError:
                # 위에서 봤지만 그 사이 다른 요청이 먼저 들어올 수 있다.
                return Response(
                    {"detail": "이미 가입된 이메일입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # **다른 기기의 토큰을 끊는다.** 이메일이 바뀌었다는 것은 계정의
            # 주인이 바뀔 수 있는 사건이라, 옛 주소로 로그인해 있던 세션을
            # 남겨두면 안 된다. 새 토큰을 발급해 돌려주므로, 링크를 누른
            # 기기는 그대로 이어서 쓴다.
            Token.objects.filter(user=user).delete()

        # 지운 직후라 _auth_response 안의 get_or_create 가 create 로 떨어진다.
        # 순서를 바꾸면 옛 토큰이 그대로 돌아가 다른 기기가 안 끊긴다.
        return _auth_response(user)


class AvatarPhotoView(APIView):
    """프로필 사진 올리기와 지우기.

    JSON 이 아니라 파일을 받는다. 그래서 파서를 따로 지정한다 - 기본
    설정이 JSON 만 받게 돼 있으면 415 가 나고, 그 메시지로는 원인이
    안 보인다.

    /me/ 에 붙이지 않고 따로 두는 이유: PATCH /me/ 는 이름과 아바타를
    바꾸는 JSON 경로다. 거기에 파일을 섞으면 한쪽 필드만 보내는 부분
    수정에서 "이름만 바꾸려는데 사진이 지워지는지" 가 애매해진다.
    """

    permission_classes = [IsAuthenticated]
    # 5MB 를 받아 다시 인코딩하는 자리라 제한을 건다. 이유는 throttles 에
    # 적어뒀다.
    throttle_classes = [AvatarPhotoThrottle]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = AvatarPhotoSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data)

    def delete(self, request: Request) -> Response:
        """사진을 지우고 아바타로 되돌린다.

        avatar 도 함께 비운다. 사진만 지우고 avatar="photo" 를 남기면
        avatar_display 가 갈 곳을 잃고, 그때 나오는 것은 계정마다 고정된
        아바타다 - 사용자가 예전에 골라뒀던 아바타가 아니다. 비워두면
        "구글 사진이 있으면 그것, 없으면 고정 아바타" 라는 원래 규칙으로
        깨끗하게 돌아간다.

        고른 아바타가 사진이 아니었으면 그것은 그대로 둔다. 사진을
        지웠다고 골라둔 아바타까지 날릴 이유가 없다.
        """
        user = request.user
        fields = ["avatar_photo", "avatar_photo_key", "avatar_photo_at"]

        user.avatar_photo = None
        # 주소 값도 지운다. 남겨두면 사진 바이트가 없는데 주소만 살아 있는
        # 상태가 되고, 그 주소는 404 를 내지만 "이 값이 한때 쓰였다" 는
        # 것은 남는다. 다시 올릴 때 어차피 새로 만든다.
        user.avatar_photo_key = None
        user.avatar_photo_at = None
        if user.avatar == AVATAR_PHOTO:
            user.avatar = ""
            fields.append("avatar")

        user.save(update_fields=fields)
        return Response(UserSerializer(user).data)


class AvatarPhotoFileView(APIView):
    """올린 사진을 그림으로 내려준다.

    로그인을 요구하지 않는다. 순위표가 남의 아바타를 그리는 화면이라
    본인 것만 열면 그 줄들이 전부 깨진다. 구글 사진도 주소만 알면 누구나
    열리는 것과 같은 수준이다 - 프로필 사진은 원래 남에게 보이라고 올린다.

    **주소가 pk 가 아니라 avatar_photo_key(UUID) 인 것이 방어다.** pk 를
    쓰면 연번이라 1번부터 눌러보는 것만으로 사진 올린 계정을 전부 훑을 수
    있다. 순위표도 이름과 그림을 같이 보여주지만 그쪽은 상위 몇 줄이고
    페이지를 넘겨야 한다 - 같은 정보라도 전원을 한 번에 긁는 것과는
    비용이 다르다. 추측 못 하는 값이면 주소를 받은 사람만 열 수 있다.

    Response 가 아니라 HttpResponse 를 쓴다. DRF Response 는 렌더러를
    거치며 JSON 으로 바꾸려 들어서, 바이트를 그대로 내보낼 수 없다.
    """

    permission_classes = [AllowAny]
    # 인증을 아예 끈다. 켜둔 채로 두면 쿠키에 죽은 토큰이 있는 브라우저가
    # 그림 하나 받으려다 401 을 받는다. 이 응답에 사용자별 내용이 없어서
    # 인증을 볼 이유도 없다.
    authentication_classes: list = []

    def get(self, request: Request, key: uuid.UUID) -> HttpResponse:
        User = get_user_model()

        # 필요한 칸만 읽는다. only() 없이 가져오면 이 사용자의 모든 칸을
        # 끌고 오는데, 그림 요청은 화면 하나에 여러 개가 동시에 난다.
        #
        # is_active 를 함께 본다. 탈퇴한 계정의 사진이 순위표에서는
        # 사라졌는데 주소로는 계속 열리면 지운 것이 아니다.
        found = (
            User.objects.filter(avatar_photo_key=key, is_active=True)
            .only("avatar_photo", "avatar_photo_key", "avatar_photo_at")
            .first()
        )
        if found is None or not found.avatar_photo:
            raise Http404

        # BinaryField 는 백엔드에 따라 memoryview 로 온다(psycopg).
        # bytes 로 맞춰야 길이 계산과 ETag 가 같은 값을 낸다.
        data = bytes(found.avatar_photo)

        # ETag 로 같은 그림을 두 번 안 받게 한다. 주소에 ?v= 를 붙여
        # 캐시를 깨는데, 그것만으로는 "안 바뀌었으니 그대로 써라" 를
        # 말할 수 없다 - 새 주소는 언제나 새로 받는다.
        etag = f'"{int(found.avatar_photo_at.timestamp())}"'
        if request.headers.get("If-None-Match") == etag:
            return HttpResponse(status=304, headers={"ETag": etag})

        response = HttpResponse(data, content_type="image/webp")
        response["ETag"] = etag
        response["Content-Length"] = str(len(data))
        # 오래 캐시해도 안전하다. 사진을 바꾸면 avatar_photo_key 가 새로
        # 만들어져 주소가 통째로 달라지므로, 옛 그림이 남을 자리가 없다.
        #
        # private 이 아니라 public 인 이유: 이 응답은 누가 보든 같다.
        # 로그인도 안 보고 사용자마다 다른 내용도 없다.
        response["Cache-Control"] = "public, max-age=604800"
        return response
