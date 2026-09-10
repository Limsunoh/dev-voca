"""devvoca Django 설정.

비밀값과 환경별 값은 프로젝트 루트의 .env 에서 읽는다. (.env.example 참고)
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# backend/config/settings.py -> backend/ -> devvoca/
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")


def env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


# 기본값을 False 로 둔다. 운영에서 DJANGO_DEBUG 를 깜빡 안 넣으면 에러 페이지에
# 소스코드와 설정값이 그대로 노출되므로, 켜는 쪽을 명시적으로 만든다.
# 로컬 개발은 .env 의 DJANGO_DEBUG=1 로 켠다.
DEBUG = env_bool("DJANGO_DEBUG", False)

# 운영에서는 폴백을 두지 않는다. 키를 깜빡하면 서버가 기동에 실패해야 한다 —
# 커밋된 기본 키로 조용히 뜨면 세션 쿠키·CSRF 토큰·비밀번호 재설정 링크가
# 전부 공개된 문자열로 서명되어 누구나 세션을 위조할 수 있다.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-only-change-me"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY 환경변수가 필요합니다. "
            "(로컬 개발이면 .env 에 DJANGO_DEBUG=1 을 넣으세요.)"
        )

# 로컬 기본값은 DEBUG 일 때만 준다. 운영에서 이 폴백을 두면 도메인을 깜빡했을 때
# 프로세스는 멀쩡히 뜨고 헬스체크도 통과하지만 실제 도메인으로 온 요청은 전부
# DisallowedHost(400) 이 된다 - 표면은 정상이고 사용자 경로만 죽는 조용한 다운.
_allowed_default = "localhost,127.0.0.1" if DEBUG else ""
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", _allowed_default).split(",") if h.strip()
]

# 배포 플랫폼이 도메인을 실행 시점에 정해주는 경우(Railway 등) 자동으로 넣는다.
# 플랫폼마다 변수명이 달라 하나씩 확인한다.
_platform_hosts = []
for _host_env in ("RAILWAY_PUBLIC_DOMAIN", "RENDER_EXTERNAL_HOSTNAME"):
    _host = (os.getenv(_host_env) or "").strip()
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
        _platform_hosts.append(_host)

# SECRET_KEY 와 같은 이유로 기동을 막는다. 플랫폼이 도메인 변수를 항상 주는 것은
# 아니고(Railway 는 도메인을 생성해야 채워지고, 커스텀 도메인은 빠진다),
# 없는 채로 뜨면 전 요청이 400 이 되므로 배포 실패가 낫다.
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS 환경변수가 필요합니다. "
        "배포 도메인을 콤마로 구분해 넣으세요. (예: devvoca.up.railway.app)"
    )

# Django 4.0+ 는 POST 요청에 Origin 검사를 한다. https 도메인은 여기에도 있어야
# Admin 로그인이 CSRF 오류로 막히지 않는다.
#
# ALLOWED_HOSTS 전체가 아니라 **플랫폼이 준 도메인만** 신뢰한다. 전체를 훑으면
# ALLOWED_HOSTS=* 를 쓸 때 이 목록이 비어 Admin 로그인이 막히고, 사설 IP 가
# 섞여 있으면 의도치 않은 origin 을 신뢰하게 된다.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
] + [f"https://{h}" for h in _platform_hosts]

# Django 4.0+ 는 이 목록에 스킴을 요구한다. .env 에 "devvoca.vercel.app" 처럼
# 스킴 없이 넣으면 기동은 되고 Admin 로그인에서만 403 이 나 원인 찾기가 어렵다.
CSRF_TRUSTED_ORIGINS = [
    o if "://" in o else f"https://{o}" for o in CSRF_TRUSTED_ORIGINS
]

# 운영은 프록시(Railway/Render)가 TLS 를 종료하고 앱에는 평문으로 넘긴다.
# 이 헤더 설정이 없으면 Django 가 요청을 http 로 인식한다.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # 위 프록시 헤더를 신뢰하도록 설정했으므로 안전하게 켤 수 있다.
    # (헤더 설정 없이 켜면 프록시 뒤에서 무한 리다이렉트에 빠진다.)
    #
    # 끌 수 있게 열어둔 이유는 CI 하나다. CI 는 운영과 같은 조건(DEBUG=False)
    # 으로 돌려야 SECRET_KEY·ALLOWED_HOSTS 가드가 실제로 서는지 검증되는데,
    # 이것까지 켜면 테스트 클라이언트의 http 요청이 전부 301 로 튕겨 아무것도
    # 확인 못 한다. 기본값이 True 라 운영에서 깜빡할 자리는 없다.
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    # HSTS 는 브라우저가 기억해버려 되돌리기 어렵다. 도메인이 확정되고 https 가
    # 안정적으로 뜬 뒤에 늘린다. 0 이면 헤더를 보내지 않는다.
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))


# 확인 링크가 가리킬 곳. 백엔드가 아니라 **화면(Next)** 주소다.
#
# 요청 헤더(Host)에서 뽑지 않는다. 그 값은 보내는 쪽이 지어낼 수 있어서,
# 남의 주소가 박힌 확인 링크를 우리 이름으로 발송하는 통로가 된다. 받는
# 사람은 devvoca 가 보낸 메일이라 믿고 누른다.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")

# 메일 발송.
#
# 이메일 변경이 본인 확인을 메일로 하기 때문에 필요하다. 없으면 그 기능만
# 못 쓰는 것이 아니라, 확인 링크가 안 가는데 화면은 "보냈습니다" 라고
# 말하는 상태가 된다 - 사용자는 스팸함만 뒤지게 된다.
#
# 서비스를 코드에 박지 않고 환경변수로 갈아끼우게 둔다. 지금은 Gmail SMTP
# 지만 하루 500통 제한이 있어, 사용자가 늘면 전용 서비스로 옮겨야 한다.
# 그때 고칠 곳이 .env 하나가 되도록 한다.
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")

# Gmail 은 계정 비밀번호가 아니라 앱 비밀번호를 받는다. 2단계 인증을 켠 뒤
# 발급하는 16자리다. 계정 비밀번호를 넣으면 인증이 거절된다.
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

# 받는 사람에게 보이는 주소. 보내는 계정과 다르면 Gmail 이 거절하거나
# 스팸으로 분류하므로 기본값을 보내는 계정으로 둔다.
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# 메일이 실제로 나가는지 여부.
#
# 계정이 설정돼 있으면 SMTP 로 보내고, 없으면 콘솔에 찍는다. 개발할 때
# 앱 비밀번호 없이도 확인 링크를 볼 수 있어야 하기 때문이다.
#
# **여기서 기동을 막지 않는다.** SECRET_KEY 처럼 없으면 죽게 만들고 싶지만,
# CI 는 운영과 같은 조건(DEBUG=False)으로 `manage.py check` 와
# `makemigrations --check` 를 돌린다. 기동에서 막으면 메일과 무관한 그
# 두 단계가 먼저 깨져, 앱 비밀번호를 CI 비밀값에 넣어야만 초록이 된다.
# 테스트에 쓰지도 않는 실제 발송 계정을 CI 에 두는 것은 맞바꿀 것이 아니다.
#
# 대신 **보내는 자리에서 막는다**(apps/accounts/mail.py). 운영에서 계정이
# 비어 있으면 메일을 보내려는 순간 오류가 나고, 화면은 "메일을 보낼 수 없다"
# 고 정확히 말한다. 조용히 콘솔로 떨어져 사용자가 스팸함을 뒤지는 상황만
# 막으면 되고, 그것은 발송 시점에 막는 것으로 충분하다.
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 서드파티
    "rest_framework",
    # 토큰 인증. 토큰은 Next 서버가 받아 httpOnly 쿠키에 넣으므로
    # 브라우저 자바스크립트가 읽지 못한다.
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    # 로컬 앱
    "apps.accounts",
    "apps.vocab",
    # 학습 기록·점수. 단어에도 문장에도 붙지 않는 도메인이라 따로 둔다.
    "apps.learning",
    # AI 콘텐츠 생성. 관리자 배치 전용 - 사용자 요청 경로에서 호출하지 않는다.
    "apps.ai_pipeline",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # whitenoise 는 SecurityMiddleware 바로 다음이어야 한다(공식 권장 위치).
    # 이게 없으면 DEBUG=False 인 배포 환경에서 Admin 의 CSS 가 전부 깨진다.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
#
# 우선순위: DATABASE_URL > USE_SQLITE > 개별 POSTGRES_* 변수
#
# 배포 플랫폼(Railway/Render/Heroku)은 DB 를 붙이면 DATABASE_URL 한 줄을 주입한다.
# 그걸 그대로 받으면 플랫폼을 옮겨도 코드를 고칠 일이 없다.
_database_url = os.getenv("DATABASE_URL", "").strip()

if _database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=600,          # 커넥션 재사용 (매 요청 새로 맺지 않는다)
            conn_health_checks=True,   # 끊긴 커넥션을 재사용해 500 나는 것을 막는다
        )
    }
elif env_bool("USE_SQLITE", False):
    # Docker 없이 빠르게 돌려볼 때만. 운영에서는 쓰지 않는다.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "devvoca"),
            "USER": os.getenv("POSTGRES_USER", "devvoca"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "devvoca"),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            # 5433 인 이유: 이 PC 는 호스트에 PostgreSQL 이 이미 5432 를 쓰고 있어
            # 컨테이너를 5433 으로 내보냈다. 기본값을 5432 로 두면 .env 없이 돌릴 때
            # 조용히 엉뚱한 DB(호스트의 것)에 붙는다.
            "PORT": os.getenv("POSTGRES_PORT", "5433"),
        }
    }


# 사용자 모델을 갈아끼운다. 로그인 키가 username 이 아니라 email 이다.
#
# 이 설정은 프로젝트 시작 시점에 정하라는 것이 Django 공식 권고다. 테이블이
# 이미 생긴 뒤에 바꾸면 auth_user 를 참조하는 외래키를 손으로 옮겨야 한다.
# 학습 기록이나 즐겨찾기가 사용자를 참조하기 시작하면 그 비용이 훨씬 커지므로
# 지금 바꾼다.
#
# 이미 만든 DB 에 적용할 때 할 일:
#   1. accounts 로 슈퍼유저를 다시 만든다(옛 auth_user 계정은 넘어오지 않는다)
#   2. django_admin_log.user_id 가 auth_user 를 계속 참조하므로 다시 걸어준다.
#      안 하면 두 번째 검수자가 Admin 에서 저장할 때 IntegrityError 가 난다.
#      제약 이름은 환경마다 다르니 먼저 확인한다:
#        SELECT conname FROM pg_constraint
#         WHERE contype='f' AND confrelid='auth_user'::regclass;
AUTH_USER_MODEL = "accounts.User"

# 구글 로그인. 없으면 그 기능만 못 쓰고 나머지는 그대로 돈다 -
# SECRET_KEY 처럼 기동을 막지 않는다.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# collectstatic 이 파일을 모으는 자리. 배포 시 이 명령을 돌려야 Admin CSS 가 나온다.
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        # 압축만 하고 파일명 해시(매니페스트)는 쓰지 않는다.
        #
        # Manifest 계열은 staticfiles.json 이 없으면 템플릿 렌더링 때 ValueError 로
        # 500 이 난다. 그런데 collectstatic 은 배포 플랫폼에 따라 web 프로세스와
        # 다른 컨테이너에서 돌 수 있어(Railway 의 release 커맨드가 그렇다) 만든
        # 매니페스트가 전달되지 않는다. 기동은 되고 페이지만 죽는 형태라 발견이 늦다.
        #
        # 캐시 버스팅이 필요해지면 collectstatic 을 빌드 단계(Dockerfile/Nixpacks)로
        # 옮겨 이미지에 구운 뒤 CompressedManifestStaticFilesStorage 로 올린다.
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Next.js 개발 서버에서 오는 요청 허용
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# 시도 횟수를 세는 자리.
#
# 기본값(프로세스 메모리)을 그대로 두면 워커마다 따로 센다. 워커가 둘이면
# 실제 한도가 두 배이고, 재시작하면 0으로 돌아간다. 제한을 걸어둔 의미가
# 그만큼 줄어든다.
#
# DB 를 쓰는 이유: Postgres 가 이미 있어 새로 붙일 것이 없다. 캐시 테이블은
# createcachetable 로 만든다. 트래픽이 늘어 이것이 부담이 되면 그때
# 공유 캐시(Redis)로 옮긴다.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "throttle_cache",
        # 기본값 300 을 넘으면 일부를 지워 자리를 만든다. 그때 노리던
        # 계정의 카운터가 함께 밀려나면 제한이 풀린다. 올려도 그 길은
        # 닫히지 않고 비용만 오른다 - 제대로 막으려면 아래 주석대로
        # Next 중계에 제한을 둬야 한다.
        #
        # 여기 들어오는 것은 요청 제한 카운터뿐이고 1분이면 만료되므로
        # 거의 쌓이지 않는다. 넉넉히 잡아도 된다.
        #
        # 되돌리기 방어는 여기 두지 않는다. 한때 뒀다가 옮겼는데, 이유는
        # cull 이다 - 캐시는 넘치면 스스로 지우므로 공격자가 항목을 채우면
        # 방어가 열린다. 지금은 apps.learning.models.RoundStep 표에 있다.
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # 토큰이 먼저다. API 요청은 Next 서버가 Authorization 헤더로 보낸다.
    #
    # 순서를 지킬 것. DRF 는 첫 번째 클래스의 인증 방식으로 401/403 을
    # 가르는데, 세션을 앞에 두면 로그인 안 한 요청이 401 대신 403 이 된다.
    # 프론트는 401 을 보고 "로그아웃 상태로 그리기" 를 판단하므로 그 분기가
    # 조용히 깨진다.
    #
    # 세션도 남겨두는 이유: Admin 화면과 DRF 의 브라우저 화면이 세션으로
    # 동작한다. 빼면 브라우저에서 API 를 눌러볼 수 없다.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # 기본 TokenAuthentication 이 아니다. 그건 사용자 행을 통째로 읽어
        # 프로필 사진 바이트까지 딸려오는데, 그러면 로그인한 사람의 모든
        # 요청이 그 무게를 진다. 이유는 그 클래스 주석에 적어뒀다.
        "apps.accounts.authentication.SlimTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # 속도 제한은 여기 두지 않는다. 이 구조에서는 오히려 해가 된다.
    #
    # 브라우저가 백엔드를 직접 부르지 않는다. 목록은 서버 컴포넌트가,
    # 문제풀기는 /api/quiz 중계가 대신 부른다. 그래서 백엔드가 보는
    # 요청자 주소는 항상 Next 서버 하나다. IP 로 세는 제한을 걸면
    # 접속자 전원이 한 통에 담겨, 한 사람이 빠르게 눌러도 나머지가
    # 429 를 받는다. 막고 싶은 반복 호출도 같은 통을 쓰니 구분되지 않는다.
    #
    # 제한이 필요해지면 실제 클라이언트를 아는 쪽, 즉 Next 중계에 둔다.
    #
    # 다만 로그인·가입은 예외다. 그쪽은 IP 가 아니라 제출된 이메일로 세므로
    # 위 문제를 피해간다(apps.accounts.throttles). 백엔드가 공개 도메인이라
    # Next 를 건너뛰고 직접 두드릴 수 있어, 제한이 없으면 한 계정의
    # 비밀번호를 무한히 추측할 수 있다.
    #
    # 이 제한이 막는 것은 거기까지다. 이메일마다 한 번씩 던져 가입 여부를
    # 훑는 것은 못 막는다 - 카운터가 이메일별이라 한 번씩은 다 통과한다.
    # 그건 실제 클라이언트를 아는 Next 중계에서 IP 로 막아야 한다.
    # 테스트에서는 넉넉하게 둔다. 테스트는 사람보다 훨씬 빠르게 요청해서
    # 운영 값이면 관계없는 테스트까지 429 로 막힌다.
    #
    # 설정을 아예 None 으로 끄지 않는 이유: DRF 는 스로틀 인스턴스를 만들
    # 때 이 값을 한 번 읽고 굳혀서, 나중에 override_settings 로 켜도 안
    # 돌아온다. 제한 자체를 검증하는 테스트가 조용히 무력해진다.
    "DEFAULT_THROTTLE_RATES": {
        "auth_email": "1000/min" if sys.argv[1:2] == ["test"] else "10/min",
        # 구글은 통을 하나만 둔다(apps.accounts.throttles 참고). 사이트
        # 전체가 함께 쓰는 값이라, 한 사람이 다 쓰면 그동안 모두가 막힌다.
        # 그래서 실제 사용량보다 훨씬 넉넉하게 잡는다 - 여기서 재는 것은
        # 개인의 시도 횟수가 아니라 우리 서버가 구글을 두드리는 총량이다.
        "auth_google": "2000/min" if sys.argv[1:2] == ["test"] else "120/min",
        # 이메일 변경 신청. 확인 메일이 나가는 자리라 낮게 잡는다 - 반복해서
        # 신청하면 우리 이름으로 남의 메일함을 채우는 통로가 된다. 계정별로
        # 세고, 주소를 바꾸는 일은 계정당 아주 가끔이라 좁아서 불편할 일이 없다.
        "email_change": "2000/min" if sys.argv[1:2] == ["test"] else "5/min",
        # 확인 링크를 쓰는 쪽은 로그인이 없어 통 하나를 모두가 나눠 쓴다.
        # 좁게 잡으면 아무나 그 통을 태워 전원을 막는 스위치가 되므로 넉넉히
        # 잡는다(이유는 apps.accounts.throttles 에 적어뒀다). 서명을 맞히는
        # 것은 이 정도 횟수로 될 일이 아니라 무차별 시도는 그대로 막힌다.
        "email_change_confirm": "2000/min" if sys.argv[1:2] == ["test"] else "120/min",
        # 비밀번호 변경. 현재 비밀번호를 대조하는 자리라 반복해서 찔러볼 수
        # 있다. 로그인 통(auth_email)과 따로 두는 이유는 세는 단위가 달라서다 -
        # 저쪽은 이메일, 여기는 이미 로그인한 계정이다.
        "password_change": "2000/min" if sys.argv[1:2] == ["test"] else "5/min",
        # 사진 올리기. 요청 하나가 5MB 를 받아 Pillow 로 열고 줄이는,
        # 이 앱에서 제일 비싼 자리다. 사람이 프로필 사진을 고르는 일은
        # 몇 번 안 되므로 스무 번이면 넉넉하다.
        "avatar_photo": "2000/min" if sys.argv[1:2] == ["test"] else "20/min",
        # 판은 로그인한 사람을 계정별로 가른다(apps.learning.throttles 참고).
        # 90초짜리 판이라 열고 닫기는 한 사람당 분당 하나꼴이면 충분하다.
        "round_start": "2000/min" if sys.argv[1:2] == ["test"] else "60/min",
        "round_finish": "2000/min" if sys.argv[1:2] == ["test"] else "60/min",
        # 답하기는 한 판에 수십 번 오간다. 90초에 40문제를 풀고 곧바로
        # 다음 판을 해도 걸리지 않을 값이어야 한다. 그래도 통을 두는 이유는
        # 요청마다 RoundStep 표에 쓰고 order_by("?") 로 표를 훑기 때문이다.
        "round_answer": "5000/min" if sys.argv[1:2] == ["test"] else "600/min",
        # 순위표는 읽기만 한다. 막는 것은 데이터가 아니라 집계 비용이다.
        # 이 값은 **순위표 하나당**이다 - 통을 셋으로 나눠 쓴다
        # (apps/learning/throttles.py 의 LeaderboardThrottle).
        "leaderboard": "5000/min" if sys.argv[1:2] == ["test"] else "60/min",
        # 일일공부. 하루 최대 40문제라 분당 30이면 손으로 닿지 않는다.
        # 로그인해야 쓸 수 있어 계정별로 센다.
        "daily_study": "5000/min" if sys.argv[1:2] == ["test"] else "30/min",
        # 답하기는 시작과 통을 나눈다. 40문제를 빠르게 푸는 것이 정상
        # 사용이라 조회·시작과 같은 통을 쓰면 판 중간에 막힌다.
        "daily_study_answer": "5000/min" if sys.argv[1:2] == ["test"] else "120/min",
        "review": "5000/min" if sys.argv[1:2] == ["test"] else "30/min",
        "review_answer": "5000/min" if sys.argv[1:2] == ["test"] else "120/min",
    },
}
