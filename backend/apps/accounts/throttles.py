"""로그인·가입 시도 제한.

두 가지로 센다.

- 이메일(EmailRateThrottle 분당, EmailHourlyThrottle 시간당): 한 계정의 비밀번호를
  반복해서 때리는 것. Admin 로그인(AdminLoginThrottle)도 이메일로 센다. 다만 그 이메일로
  로그인해 본 브라우저는 기기 쿠키로 따로 센다.
- 접속 IP(SignUpIpThrottle, LoginIpThrottle, GoogleIpThrottle): 이메일을 바꿔 가며
  계정을 찍어 내거나 여러 계정에 같은 비밀번호를 대보는 것. 이메일로는 한 번씩 다
  통과한다. 구글 로그인은 이메일을 모르므로 IP 로만 센다.

IP 는 그냥 볼 수 없다. 브라우저는 백엔드를 직접 부르지 않고 Next 서버가 대신
불러서, 백엔드가 보는 접속 주소는 늘 Next 서버(Vercel)다. 그래서 Next 가 실제
접속 IP 를 머리에 실어 보내고, 위조를 막으려고 둘이 나눠 가진 비밀값을 같이
싣는다(came_through_next, client_ip_bucket).
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import secrets
import unicodedata

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


def email_ident(email: str) -> str:
    """이메일로 세는 제한의 키. 로그인이 같은 계정으로 보는 이메일은 같은 키가 된다.

    Admin 폼은 이메일을 NFKC 로 바꾸고(전각 "ｂ" -> "b"), 계정은 email__iexact 로 찾는다.
    iexact 는 PostgreSQL 의 UPPER 라 "ſ"(U+017F) 가 "S", "ı" 가 "I" 가 된다. .lower() 로
    키를 만들면 이 변형들이 같은 계정에 로그인되면서 횟수는 따로 세어져 제한을 피한다.
    그래서 같은 두 단계(NFKC, upper)를 거친다.

    해시로 줄이는 이유: 이메일을 그대로 쓰면 키가 길어져 캐시 백엔드가 거부한다
    (memcached 는 250자 제한). 길이가 고정되면 그 걱정이 없고, 캐시에 이메일 원문이
    남지도 않는다. 서버 비밀값을 섞는 이유: 그냥 해시면 후보 이메일 목록과 대조해 캐시
    표의 키에서 원래 이메일을 알아낼 수 있다.
    """
    folded = unicodedata.normalize("NFKC", email.strip()).upper()
    return salted_hmac("accounts.throttles.email", folded, algorithm="sha256").hexdigest()


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

        return self.cache_format % {"scope": self.scope, "ident": email_ident(email)}


class EmailHourlyThrottle(EmailRateThrottle):
    """같은 이메일로 한 시간에 몇 번까지 로그인을 시도하나.

    분당 제한(auth_email)만 있으면 접속 IP 를 바꿔 가며 한 계정을 하루 1만 4천 번
    두드릴 수 있다.

    대가: 이메일만 알면 남이 시간당 30번씩 보내 그 계정의 이메일 로그인을 계속 막아 둘
    수 있다(창이 밀려가며 세므로 멈추면 한 시간 안에 풀린다). 구글 로그인은 막지 않는다.
    """

    scope = "auth_email_hour"


# 관리자 로그인 기기 쿠키(AdminLoginThrottle). 값은 "이메일 키:무작위" 를 서명한 것이다.
ADMIN_DEVICE_COOKIE = "admin_device"
ADMIN_DEVICE_SALT = "accounts.throttles.admin_device"
ADMIN_DEVICE_MAX_AGE = 180 * 24 * 60 * 60


def admin_device(request, email: str) -> str | None:
    """그 이메일로 로그인해 본 브라우저면 기기 키를 돌려준다. 아니면 None.

    서명이 틀리거나 기한(180일)이 지났거나 다른 이메일의 쿠키면 None 이다. 이메일은
    email_ident 로 견줘, 로그인이 같은 계정으로 보는 표기(대소문자, 전각 등)는 같게 친다.
    """
    value = request.get_signed_cookie(
        ADMIN_DEVICE_COOKIE, default=None, salt=ADMIN_DEVICE_SALT, max_age=ADMIN_DEVICE_MAX_AGE
    )
    if not value:
        return None
    owner, _, device = value.partition(":")
    if not device or not constant_time_compare(owner, email_ident(email)):
        return None
    return device


def issue_admin_device(response, email: str) -> None:
    """관리자 로그인에 성공한 응답에 기기 쿠키를 붙인다.

    Admin 주소에서만 보내고(path), 화면 스크립트가 못 읽고(httponly), 다른 사이트에서
    온 요청에는 안 실린다(SameSite=Strict).
    """
    response.set_signed_cookie(
        ADMIN_DEVICE_COOKIE,
        f"{email_ident(email)}:{secrets.token_hex(16)}",
        salt=ADMIN_DEVICE_SALT,
        max_age=ADMIN_DEVICE_MAX_AGE,
        path="/admin/",
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )


class AdminLoginThrottle(EmailRateThrottle):
    """관리자 로그인(/admin/login/) 시도. Admin 폼은 이메일을 username 칸에 싣는다.

    DRF 화면이 아니라 Django 폼이라 request.data 가 없다. 세는 방식은 위와 같다.

    이메일로만 세면 관리자 이메일을 아는 사람이 시간당 10번씩 보내 Admin 로그인을 계속
    막아 둘 수 있었다. Admin 은 Next 를 거치지 않아 접속 IP 를 믿을 수 없다(Railway
    문서는 X-Real-IP 를 사용자가 지어 보내면 덮어쓰는지 적지 않았다). 그래서 기기 쿠키를
    쓴다(OWASP 의 device cookie). 그 이메일로 로그인에 성공한 브라우저에는 쿠키를 주고,
    쿠키를 낸 시도는 이메일 통이 아니라 그 기기의 통으로 센다. 남이 이메일 통을 채워도
    로그인해 본 브라우저는 들어온다. 쿠키는 횟수를 따로 세게 할 뿐 로그인을 대신하지 않고,
    쿠키를 훔쳐도 그 기기 몫(시간당 10번)만큼만 더 대볼 수 있다.

    남은 대가: 처음 쓰는 브라우저는 여전히 이메일 통과 전체 통(AdminLoginTotalThrottle)에
    들어 막힐 수 있다. 풀어 주는 방법은 DEPLOY.md 의 "Admin 로그인이 429 로 막혔을 때".
    """

    scope = "admin_login"

    def get_cache_key(self, request, view) -> str | None:
        email = request.POST.get("username", "")
        if not email.strip():
            return None
        device = admin_device(request, email)
        if device is not None:
            return self.cache_format % {"scope": f"{self.scope}_device", "ident": device}
        return self.cache_format % {"scope": self.scope, "ident": email_ident(email)}


class AdminLoginTotalThrottle(SimpleRateThrottle):
    """기기 쿠키 없이 들어온 관리자 로그인 시도 전체를 한 통으로 센다. 이메일 통보다 먼저 돈다.

    이메일 통만 있으면 이메일을 바꿔 가며 끝없이 보낼 수 있다. 없는 이메일이어도 Django 가
    비밀번호 해시(PBKDF2 100만 회, 이 PC 에서 0.2초)를 돌아 작업자 CPU 를 먹고, 요청마다
    시도 횟수 행이 하나씩 쌓인다(넘쳐도 살아 있는 행은 안 지우지만 표가 커진다,
    config/throttle_cache.py 의 _cull). IP 를 믿을 수 없는 자리라(AdminLoginThrottle 주석)
    통 하나로 센다.

    대가: 남이 이 통을 채우면 처음 쓰는 브라우저의 관리자 로그인도 한 시간 막힌다. 로그인해
    본 브라우저는 기기 쿠키가 있어 이 통을 타지 않는다.
    """

    scope = "admin_login_total"

    def get_cache_key(self, request, view) -> str | None:
        if admin_device(request, request.POST.get("username", "")) is not None:
            return None
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


class EmailChangeTotalThrottle(EmailChangeThrottle):
    """이메일 변경 확인 메일의 서비스 전체 상한. 계정마다 세는 위 제한 다음에 둔다.

    계정마다 세는 것만으로는 계정을 여러 개 만들어 나눠 보내는 것을 못 막는다. 메일은
    Gmail 계정 하나로 나가고 하루에 보낼 수 있는 양이 정해져 있다(약 500통). 그 한도를
    이 신청이 다 쓰면 그날 오류 알림과 1년 미접속 삭제 안내가 모두 실패한다.

    대가: 이 통을 누가 채우면 그 한 시간 동안 모두의 이메일 변경이 막힌다. 이메일
    변경은 드문 일이고, 막히는 것은 확인 메일 보내기뿐이라 삭제 안내를 못 보내는 것보다
    가볍다. 하루로 세지 않는 이유는 처리방침 3절이 시도 기록을 1시간 넘게 두지 않는다고
    적어서다(바꾸려면 개정 공지).

    뷰가 FirstThrottleWins 라 계정 제한에 막힌 요청은 여기까지 오지 않는다. 안 그러면
    한 계정이 막힌 채 계속 보내기만 해도 이 통이 차서 모두가 막힌다.
    """

    scope = "email_change_total"

    def get_cache_key(self, request, view) -> str | None:
        # 익명을 세지 않는 판단은 부모와 같다. 키만 계정 대신 "all" 이다.
        if super().get_cache_key(request, view) is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": "all"}


class EmailChangeConfirmThrottle(SimpleRateThrottle):
    """확인 링크를 쓰는 쪽의 제한. 서명을 무작위로 찔러보는 것을 막는다.

    신청 쪽과 통을 나눈다. 여기는 로그인이 없어서(메일을 다른 기기에서
    열 수 있어야 한다) 계정으로 셀 수 없고, 통 하나로 합쳐 센다.

    요청자별로 못 나눈다. 이 프로젝트는 브라우저가 백엔드를 직접 부르지
    않고 Next 서버가 대신 불러서, 백엔드가 보는 주소는 늘 하나다. 확인 링크를
    여는 화면은 접속 IP 를 실어 보내지 않는다(client_ident 를 쓰는 곳은 가입·로그인과
    PerUserOrIpThrottle 뿐이다).

    그래서 요율을 넉넉히 잡는다. 한 통을 모두가 나눠 쓰므로 좁게 잡으면
    아무나 그 통을 태워 전원의 이메일 변경을 막는 스위치가 된다
    (문제풀기의 예전 게스트 한 통도 같은 위험을 배수로 완화했다). 확인
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
    이메일로 셀 수 없다. 접속 IP 는 Next 가 가입·로그인과, 로그인하지 않은 판·채점·
    순위표·소리내어 읽기 요청에만 실어 보낸다(client_ident).
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
    주소가 늘 하나다. 접속 IP 는 Next 가 가입·로그인과, 로그인하지 않은 판·채점·
    순위표·소리내어 읽기 요청에만 실어 보낸다(client_ident). 계정 단위가 유일한
    방어선이다.

    인증이 없으면 세지 않는다. 이 뷰는 IsAuthenticated 라 그 경우 401 로
    끝나고, 그런 요청을 한 통에 담으면 그것이 전원을 막는 스위치가 된다.
    """

    scope = "avatar_photo"

    def get_cache_key(self, request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": f"u{user.pk}"}


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


def client_ident(request: Request) -> str | None:
    """접속자를 세는 키. 가입·로그인 제한과, 로그인하지 않은 사람의 문제풀기·순위표·소리내어
    읽기 제한(PerUserOrIpThrottle)이 같이 쓴다.

    - Next 를 거친 요청: 접속 IP(IPv6 는 /64)마다 따로 센다. IP 원문은 캐시 키에 두지
      않고, 이메일과 같이 서버 비밀값을 섞은 해시로 바꾼다. Next 가 IP 를 싣지 못한
      요청은 None(세지 않음)이다.
    - Next 를 거치지 않은 요청(비밀값이 없거나 틀림): IP 를 보지 않고 한 통("direct")에
      담는다. 실제 사용자는 늘 Next 를 거치므로 이 통에는 봇과 시험하는 사람만 든다.
      Railway 앞단이 붙이는 X-Real-IP 는 사용자가 지어 보낸 값을 덮어쓰는지 문서로
      확인하지 못해 믿지 않는다.

    비밀값이 Railway 와 Vercel 중 한쪽에만 있거나 다르면, 또는 프론트를 이 기능 전으로
    되돌리면, 실제 사용자도 모두 direct 통에 든다(DEPLOY.md 의 RELAY_SECRET).
    """
    if not came_through_next(request):
        return "direct"
    bucket = client_ip_bucket(request)
    if bucket is None:
        return None
    return salted_hmac("accounts.throttles.ip", bucket, algorithm="sha256").hexdigest()


class _ClientIpThrottle(SimpleRateThrottle):
    """접속 IP 로 센다. 키는 client_ident."""

    def get_cache_key(self, request: Request, view) -> str | None:
        ident = client_ident(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PerUserOrIpThrottle(SimpleRateThrottle):
    """로그인했으면 계정별, 아니면 접속 IP 별(client_ident). 로그인 없이 쓸 수 있는 90초 한 판,
    순위표, 낱개 연습 채점, 소리내어 읽기의 제한이 상속한다(learning·vocab 의 throttles).

    통을 나누는 이유: 통이 하나뿐이면 한 사람이 한도를 다 쓰는 동안 나머지 전원이 막힌다.
    예전에는 로그인하지 않은 사람 전원을 "guest" 한 통으로 세서, 계정 없이 그 통만 채우면
    로그인하지 않은 방문자 전원이 429 를 봤다.

    로그인하지 않은 사람의 통(IP 하나, 또는 direct)은 계정 통의 guest_multiplier 배다.
    학교·회사 와이파이처럼 IP 하나를 여럿이 쓴다. direct 에도 같은 배수가 붙어, RELAY_SECRET
    이 어긋나 실제 사용자가 모두 direct 에 들어도 예전 guest 한 통과 같은 크기는 남는다.

    IP 를 못 실은 요청(client_ident 가 None)은 세지 않는다. 가입·로그인과 같다. Vercel 을
    거친 요청에는 x-forwarded-for 가 늘 있고, 비밀값 없이 바로 부른 요청은 direct 로 가므로
    이 길을 밖에서 고를 수 없다.
    """

    guest_multiplier = 20

    def get_cache_key(self, request: Request, view) -> str | None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            ident = f"u{user.pk}"
        else:
            ident = client_ident(request)
            if ident is None:
                return None
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def allow_request(self, request: Request, view) -> bool:
        # DRF 는 요청마다 새 인스턴스를 만든다. 여기서 값을 바꿔도
        # 다음 요청에 새지 않는다.
        user = getattr(request, "user", None)
        if self.num_requests and (user is None or not user.is_authenticated):
            self.num_requests *= self.guest_multiplier
        return super().allow_request(request, view)


class SignUpIpThrottle(_ClientIpThrottle):
    scope = "signup_ip"


class LoginIpThrottle(_ClientIpThrottle):
    scope = "login_ip"


class GoogleIpThrottle(_ClientIpThrottle):
    """구글 로그인 시도 제한. 이메일 로그인처럼 접속 IP 로 센다.

    구글 요청에는 코드나 신분 토큰만 들어 있어 이메일로 셀 수 없다. 예전에는 사이트
    전체를 한 통(1분에 120번)으로 셌는데, 그러면 한 사람이 그만큼 두드려 그동안 모두의
    구글 로그인을 막을 수 있었다. 이제 Next 를 거친 요청은 접속 IP 마다 따로 세고,
    백엔드를 바로 부른 요청은 "direct" 한 통에 담는다. 실제 사용자는 늘 Next 를 거치므로
    봇이 direct 통을 다 써도 막히지 않는다.

    로그인 여부로 통을 나누지 않는다(부모 클래스가 사용자를 보지 않는다). 토큰을 붙이면
    세지 않는 구현이면 계정 하나만 만들어 제한을 없앨 수 있다.

    예전 한 통에는 "우리 서버가 구글을 두드리는 총량" 을 묶는 뜻도 있었다. 그 총량
    상한은 일부러 두지 않는다. 다시 두면 누군가 그 상한을 채우는 순간 또 모두가 막힌다.
    이제 IP 하나는 한 시간에 60번까지라, 한 시간 내내 예전 상한(시간당 7200번)만큼
    보내려면 IP 가 120개(IPv6 는 /64 120개) 필요하다. 60번을 1분 안에 몰아 보내면 IP
    몇 개로도 그 1분은 예전 상한을 넘지만, 그 IP 들은 나머지 한 시간 동안 막힌다.
    ponytail: 총량 상한 없음. 구글이 우리 서버를 막기 시작하면 넉넉한 전체 상한을 IP
    제한과 함께 단다(IP 하나로는 못 채우는 크기로).
    """

    scope = "google_ip"
