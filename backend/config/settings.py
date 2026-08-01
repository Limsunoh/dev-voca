"""devvoca Django 설정.

비밀값과 환경별 값은 프로젝트 루트의 .env 에서 읽는다. (.env.example 참고)
"""

import os
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
    SECURE_SSL_REDIRECT = True
    # HSTS 는 브라우저가 기억해버려 되돌리기 어렵다. 도메인이 확정되고 https 가
    # 안정적으로 뜬 뒤에 늘린다. 0 이면 헤더를 보내지 않는다.
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 서드파티
    "rest_framework",
    "django_filters",
    "corsheaders",
    # 로컬 앱
    "apps.vocab",
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

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
