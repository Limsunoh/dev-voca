"""로그인·가입 시도 제한.

두 가지로 센다.

- 이메일(EmailRateThrottle): 한 계정의 비밀번호를 반복해서 때리는 것.
- 접속 IP(SignUpIpThrottle, LoginIpThrottle): 이메일을 바꿔 가며 계정을 찍어
  내거나 여러 계정에 같은 비밀번호를 대보는 것. 이메일로는 한 번씩 다 통과한다.

IP 는 그냥 볼 수 없다. 브라우저는 백엔드를 직접 부르지 않고 Next 서버가 대신
불러서, 백엔드가 보는 접속 주소는 늘 Next 서버(Vercel)다. 그래서 Next 가 실제
접속 IP 를 머리에 실어 보내고, 위조를 막으려고 둘이 나눠 가진 비밀값을 같이
싣는다(came_through_next, client_ip_bucket).
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from datetime import date

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


def sweep_expired_counters(*, apply: bool) -> int:
    """수명이 다한 시도 횟수 행을 지운다. apply 가 False 면 세기만 한다.

    DB 캐시는 만료된 행을 스스로 치우지 않는다. 같은 키로 다시 읽거나 행이
    상한을 넘을 때만 지워져서, 이메일에서 나온 키가 정해진 기한 없이 남는다.
    """
    table = connection.ops.quote_name(settings.CACHES["default"]["LOCATION"])
    expires = connection.ops.quote_name("expires")
    now = connection.ops.adapt_datetimefield_value(
        timezone.now().replace(microsecond=0)
    )
    with connection.cursor() as cursor:
        if not apply:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {expires} < %s", [now])
            return cursor.fetchone()[0]
        cursor.execute(f"DELETE FROM {table} WHERE {expires} < %s", [now])
        return cursor.rowcount


class EmailRateThrottle(SimpleRateThrottle):
    """제출된 이메일 기준으로 시도 횟수를 센다."""

    scope = "auth_email"

    def get_cache_key(self, request, view) -> str | None:
        # 본문이 dict 가 아닐 수 있다. 그때는 어차피 400 이 되므로 세지 않는다.
        if not isinstance(request.data, dict):
            return None

        email = request.data.get("email")
        if not isinstance(email, str) or not email.strip():
            return None

        # 저장할 때와 같은 방식으로 낮춘다. 안 그러면 대소문자만 바꿔가며
        # 같은 계정을 계속 때릴 수 있다.
        #
        # 해시로 줄이는 이유: 이메일을 그대로 쓰면 키가 길어져 캐시 백엔드가
        # 거부한다(memcached 는 250자 제한). 길이가 고정되면 그 걱정이 없고,
        # 캐시에 이메일 원문이 남지도 않는다.
        #
        # 서버 비밀값을 섞는 이유: 그냥 해시면 후보 이메일 목록과 대조해 캐시
        # 표의 키에서 원래 이메일을 알아낼 수 있다.
        ident = salted_hmac(
            "accounts.throttles.email", email.strip().lower(), algorithm="sha256"
        ).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class GoogleRateThrottle(SimpleRateThrottle):
    """구글 로그인 시도 제한.

    이메일로 셀 수 없다. 구글 요청에는 코드나 신분 토큰만 들어 있고 이메일은
    구글에 물어봐야 나온다.

    요청자별로도 못 센다. 이 프로젝트는 모든 요청이 Next 서버 하나로
    보인다. 가입·로그인은 Next 가 비밀값과 함께 접속 IP 를 실어 보내
    IP 로 세지만(SignUpIpThrottle), 구글 중계(app/api/auth/google)는 아직
    싣지 않는다. 비밀값 없이 주소를 알려주는 머리는 아무나 지어낼 수 있다.
    인증 여부로 나누는 것도 안 된다. 토큰만 붙이면 세지 않는 구현이 있어, 계정 하나 만들면 그대로 뚫린다.

    그래서 통을 하나만 둔다. 여기서 재는 것은 "누가 얼마나" 가 아니라
    "우리 서버가 구글을 얼마나 두드리는가" 다. 그 총량에 상한을 두면
    남이 우리를 통해 구글을 때리는 것도 함께 막힌다.

    대가로 한 사람이 한도를 다 쓰면 그동안 모두가 막힌다. 그래서 실제
    사용량보다 훨씬 넉넉하게 잡는다.
    """

    scope = "auth_google"

    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class EmailChangeThrottle(SimpleRateThrottle):
    """이메일 변경 신청 제한. 확인 메일이 나가는 자리다.

    막으려는 것은 남의 주소로 반복해서 신청을 걸어 우리 이름으로 메일
    폭탄을 만드는 것이다. 로그인만 요구해서는 못 막는다. 계정 하나로
    무제한 보낼 수 있다.

    계정으로 센다. 이 요청은 IsAuthenticated 라 익명이 도달하지 않는다.

    익명이면 세지 않고 통과시킨다(None). 통 하나에 담으면 401 로 끝날
    요청들이 한 통을 채워, 아무나 그 통을 태우는 것만으로
    모두의 이메일 변경을 막을 수 있다. 어차피 인증에서 막힌다.
    """

    scope = "email_change"

    def get_cache_key(self, request, view) -> str | None:
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{request.user.pk}"}


class EmailChangeConfirmThrottle(SimpleRateThrottle):
    """확인 링크를 쓰는 쪽의 제한. 서명을 무작위로 찔러보는 것을 막는다.

    신청 쪽과 통을 나눈다. 여기는 로그인이 없어서(메일을 다른 기기에서
    열 수 있어야 한다) 계정으로 셀 수 없고, 통 하나로 합쳐 센다.

    요청자별로 못 나눈다. 이 프로젝트는 브라우저가 백엔드를 직접 부르지
    않고 Next 서버가 대신 불러서, 백엔드가 보는 주소는 늘 하나다. 나누는
    척하면 접속자 전원이 한 통에 담기면서 나눴다는 착각만 남는다.

    그래서 요율을 넉넉히 잡는다. 한 통을 모두가 나눠 쓰므로 좁게 잡으면
    아무나 그 통을 태워 전원의 이메일 변경을 막는 스위치가 된다
    (apps/learning/throttles.py 가 같은 위험을 배수로 완화한다). 확인
    링크를 누르는 일은 계정당 몇 번 없어서, 넉넉해도 무차별 시도를 막는
    목적은 그대로 선다. 서명을 맞히려면 그 정도로는 어림없다.
    """

    scope = "email_change_confirm"

    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class PasswordChangeThrottle(SimpleRateThrottle):
    """비밀번호 변경 시도 제한.

    막으려는 것은 현재 비밀번호를 반복해서 찔러보는 것이다. 이 통로는
    로그인과 성질이 같다. 맞는지 틀리는지를 응답으로 알려주므로, 제한이
    없으면 로그인 화면 대신 여기로 추측을 던질 수 있다. 로그인에만 제한을
    걸고 여기를 비워두면 그쪽 제한이 무의미해진다.

    계정으로 센다. 이 요청 본문에는 이메일이 없고 토큰으로 들어오므로
    이메일로 셀 수 없다. 접속 IP 는 Next 가 가입·로그인에만 실어 보낸다(SignUpIpThrottle).
    계정별로 나누면 한도를 다 쓴 사람만 기다린다. 통을 하나만 두면
    아무나 한도를 태워 전원의 비밀번호 변경을 막을 수 있다.

    인증이 없으면 세지 않는다. 이 뷰는 IsAuthenticated 라 그 경우 401 로
    끝나고, None 을 주면 DRF 가 제한을 건너뛴다. 인증 안 된 요청을 한
    통에 담으면 그것이 곧 전원을 막는 스위치가 된다.

    요율은 settings 의 DEFAULT_THROTTLE_RATES 에 둔다. 다른 통들과 한
    자리에 모여 있어야 조정할 때 흩어진 곳을 뒤지지 않는다.
    """

    scope = "password_change"

    def get_cache_key(self, request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{user.pk}"}


class ProfileUpdateThrottle(PasswordChangeThrottle):
    """이름·아바타 저장 제한.

    계정으로 세는 것은 비밀번호 변경과 같고 통만 따로 쓴다. 이름을 여러 번
    고치다가 비밀번호 변경까지 막히면 안 된다.
    """

    scope = "profile_update"


class AvatarPhotoThrottle(SimpleRateThrottle):
    """사진 올리기 제한.

    여기가 이 앱에서 제일 비싼 자리다. 요청 하나가 최대 5MB 를 받아 Pillow
    로 열고 줄인 뒤 다시 인코딩한다. 제한이 없으면 계정 하나로 큰 사진을
    반복해서 던지는 것만으로 CPU 와 메모리를 밀 수 있다.

    IP 로 못 막는다. 이 프로젝트는 Next 서버가 중계해서 백엔드가 보는
    주소가 늘 하나다. 접속 IP 는 Next 가 가입·로그인에만 실어 보낸다
    (SignUpIpThrottle). 계정 단위가 유일한 방어선이다.

    인증이 없으면 세지 않는다. 이 뷰는 IsAuthenticated 라 그 경우 401 로
    끝나고, 그런 요청을 한 통에 담으면 그것이 전원을 막는 스위치가 된다.
    """

    scope = "avatar_photo"

    def get_cache_key(self, request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{user.pk}"}


# 가입·로그인을 접속 IP 로 세기 시작하는 날(한국 시간). 처리방침 v3 가 "로그인·가입 시도 때
# 접속 IP 를 해시값으로 바꿔 1시간 단위로 센다" 를 싣고 시행하는 날이다. 처리방침 14절이
# "바꾸면 시행 7일 전부터 화면에 알린다" 고 약속해서 그 전에는 아무것도 세지 않는다. Next 도
# 이 날부터 IP 를 싣는다(frontend/src/lib/client-ip.ts 의 IP_FROM). 두 날짜와 처리방침
# v3 시행일(2026-11-19, 14절에 글자로 적음)이 같은지는 client-ip.test.mts 가 본다.
# PRIVACY_CHANGE.effective 는 v4 시행일(11-20)이라 견주지 않는다.
# ponytail: 날짜로 켜는 문이다. 시행일이 지나면 이 상수와 _ClientIpThrottle 의 날짜 비교,
# client-ip.ts 의 IP_FROM, 두 쪽 테스트의 날짜 고정을 지운다. `grep -rn IP_COUNT_FROM` 로 찾는다.
IP_COUNT_FROM = date(2026, 11, 19)

# Next 서버가 싣는 머리(frontend/src/lib/client-ip.ts). WSGI 가 HTTP_ 를 붙이고 - 를 _ 로 바꾼다.
RELAY_SECRET_HEADER = "HTTP_X_NEXT_RELAY"
CLIENT_IP_HEADER = "HTTP_X_NEXT_CLIENT_IP"


def came_through_next(request: Request) -> bool:
    """Next 서버가 보낸 요청인가. 둘이 나눠 가진 비밀값(RELAY_SECRET)으로 가른다.

    백엔드 주소는 공개돼 있어 아무나 Next 의 머리를 지어 바로 보낼 수 있다. 그래서
    비밀값이 맞을 때만 Next 에서 온 것으로 본다. 앞뒤 공백은 지우고 비교한다. 환경변수를
    화면에 붙여 넣다 줄바꿈이 붙으면 맞는 값도 틀린 값이 된다.

    머리는 왔는데 값이 틀리면 운영 로그에 한 줄 남긴다. Railway 와 Vercel 의 값이
    어긋나면 실제 사용자 전원이 "바로 부른 요청" 한 통에 들어 가입이 막히는데, 그 원인을
    알 길이 이것뿐이다. 값 대신 보낸 값의 지문(sha256 앞 8자)을 찍는다. 같은 지문이
    되풀이되면 Next 의 설정이 어긋난 것이고, 매번 다르면 머리를 지어 보내는 봇이다.
    지문마다 한 번만 찍어 봇이 로그를 채우지 못하게 한다.
    """
    sent = request.META.get(RELAY_SECRET_HEADER, "").strip()
    if not sent:
        return False
    secret = settings.RELAY_SECRET.strip()
    if secret and constant_time_compare(sent, secret):
        return True
    _warn_mismatch(sent)
    return False


# 이미 경고한 지문. 프로세스마다 따로 기억하고, 다시 띄우면 비운다.
# ponytail: 상한에 닿으면 더 찍지 않는다. 봇이 지문을 바꿔 가며 보내도 로그는 여기서 멈춘다.
_WARNED: set[str] = set()
_WARNED_LIMIT = 50


def _warn_mismatch(sent: str) -> None:
    fingerprint = hashlib.sha256(sent.encode("utf-8", "replace")).hexdigest()[:8]
    if fingerprint in _WARNED or len(_WARNED) >= _WARNED_LIMIT:
        return
    _WARNED.add(fingerprint)
    logger.warning(
        "X-Next-Relay 비밀값이 맞지 않음(보낸 값 지문 %s) - 같은 지문이 되풀이되면 "
        "Railway 와 Vercel 의 RELAY_SECRET 이 같은지 본다",
        fingerprint,
    )


def client_ip_bucket(request: Request) -> str | None:
    """Next 가 실어 보낸 접속 IP 를 세는 단위로 바꾼다. IP 꼴이 아니면 None.

    Next 는 Vercel 이 접속자 IP 로 덮어써 둔 x-forwarded-for 의 맨 앞을 싣는다. 사용자가
    이 값을 지어 보내도 Vercel 이 덮어쓴다. 이 함수는 came_through_next 가 참일 때만 부른다.

    IPv6 는 앞 64비트(/64)로 묶는다. 가정 회선이나 서버 한 대가 /64 를 통째로 받는 것이
    보통이라, 주소 하나 단위로 세면 주소를 바꿔 가며 통을 끝없이 늘릴 수 있다.
    IPv4 를 IPv6 꼴로 적은 것(::ffff:1.2.3.4)은 IPv4 로 센다. 표기만 다른 같은 주소다.
    """
    raw = request.META.get(CLIENT_IP_HEADER, "").strip()
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        # 존 표기(%eth0)는 같은 주소를 다른 글자로 만든다. 숫자만 남긴 주소로 바꾼다.
        # 네트워크로만 바꾸면 뒤 64비트가 0 인 주소(2001:db8::%eth0)에는 존이 남는다.
        bare = ipaddress.IPv6Address(ip.packed)
        return str(ipaddress.IPv6Network((bare, 64), strict=False))
    return str(ip)


class _ClientIpThrottle(SimpleRateThrottle):
    """접속 IP 로 센다. IP_COUNT_FROM 전에는 아무것도 세지 않는다.

    - Next 를 거친 요청: 접속 IP(IPv6 는 /64)마다 따로 센다. IP 원문은 캐시 키에 두지
      않고, 이메일과 같이 서버 비밀값을 섞은 해시로 바꾼다. Next 가 IP 를 싣지 못한
      요청은 세지 않는다.
    - Next 를 거치지 않은 요청(비밀값이 없거나 틀림): IP 를 보지 않고 한 통("direct")에
      담는다. 실제 사용자는 늘 Next 를 거치므로 이 통에는 봇과 시험하는 사람만 든다.
      Railway 앞단이 붙이는 X-Real-IP 는 사용자가 지어 보낸 값을 덮어쓰는지 문서로
      확인하지 못해 믿지 않는다.

    비밀값이 Railway 와 Vercel 중 한쪽에만 있거나 다르면, 또는 프론트를 이 기능 전으로
    되돌리면, 실제 사용자도 모두 direct 통에 든다(DEPLOY.md 의 RELAY_SECRET).
    """

    def get_cache_key(self, request: Request, view) -> str | None:
        # 비밀값 확인은 날짜 앞에서 한다. IP 를 보지 않는 일이라 처리방침과 상관없고,
        # 시행일 전에도 값이 어긋났다는 경고가 운영 로그에 나와 미리 맞출 수 있다.
        through_next = came_through_next(request)
        if timezone.localdate() < IP_COUNT_FROM:
            return None
        if not through_next:
            ident = "direct"
        else:
            bucket = client_ip_bucket(request)
            if bucket is None:
                return None
            ident = salted_hmac("accounts.throttles.ip", bucket, algorithm="sha256").hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class SignUpIpThrottle(_ClientIpThrottle):
    scope = "signup_ip"


class LoginIpThrottle(_ClientIpThrottle):
    scope = "login_ip"
