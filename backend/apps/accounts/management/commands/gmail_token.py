"""Gmail API 갱신 토큰을 받아 .env 에 적는다. 로컬 PC 에서 한 번 돌린다.

    python backend/manage.py gmail_token --sender <보내는 Gmail 주소>

1. .env 의 GMAIL_CLIENT_ID·GMAIL_CLIENT_SECRET 으로 구글 허락 화면을 브라우저에
   연다. Google Cloud 의 "데스크톱 앱" 클라이언트여야 한다. 그 유형만
   127.0.0.1 의 아무 포트로 돌아오는 것을 받아 준다.
2. 허락하면 구글이 127.0.0.1:<포트> 로 코드를 붙여 돌려보낸다. 잠깐 띄운 작은
   서버가 그 코드를 받는다.
3. 코드를 갱신 토큰으로 바꿔 .env 의 GMAIL_REFRESH_TOKEN 줄에 적는다. 어느
   계정으로 허락했는지도 화면에 알려 준다.

토큰과 코드는 화면에 찍지 않는다. 운영(Railway)에는 .env 에서 옮겨 넣는다.

토큰이 풀리는 경우: 구글 계정 비밀번호를 바꾸거나, 6개월 동안 안 쓰거나, OAuth
동의 화면이 "테스트" 상태여서 7일이 지났을 때. 동의 화면은 "프로덕션" 으로
게시해 둔다. 풀리면 이 명령을 다시 돌린다.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.gmail_api import TIMEOUT, TOKEN_URL, _error_name, _json

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
# openid email 은 어느 계정으로 허락했는지 알려고 같이 받는다. 보내는 주소는
# 허락한 계정으로 정해진다(Gmail 이 From 을 그 계정으로 바꾼다). 다른 계정으로
# 허락하면 운영 메일이 엉뚱한 주소에서 나간다.
SCOPE = f"openid email {GMAIL_SEND}"
KEY = "GMAIL_REFRESH_TOKEN"
WAIT_SECONDS = 300

DONE_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>devvoca</title>"
    "<p>받았습니다. 이 창은 닫아도 됩니다.</p>"
).encode("utf-8")
IGNORED_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>devvoca</title>"
    "<p>이번에 연 허락 화면의 응답이 아닙니다. 터미널에 찍힌 주소로 다시 여세요.</p>"
).encode("utf-8")


def upsert_env(text: str, key: str, value: str) -> str:
    """.env 글에서 key 줄을 value 로 바꾼다. 없으면 맨 끝에 더한다.

    같은 이름 줄이 여럿이면 전부 바꾼다. 하나만 바꾸면 .env 를 읽는 쪽이
    뒤의 옛 값을 쓴다. 주석(#)으로 막아 둔 줄은 건드리지 않는다. 사람이
    일부러 꺼 둔 값일 수 있다.
    """
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if "=" in line and line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            found = True
    if not found:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def approved_email(id_token: str) -> str:
    """id_token 에서 허락한 계정 주소를 꺼낸다.

    서명은 확인하지 않는다. 구글 토큰 주소에서 HTTPS 로 바로 받은 값이라
    중간에 바뀔 길이 없고, 여기서는 사람에게 보여 주고 비교하는 데만 쓴다.
    """
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return str(json.loads(base64.urlsafe_b64decode(payload)).get("email", ""))
    except (IndexError, ValueError, AttributeError):
        return ""


def write_env(path: Path, key: str, value: str) -> None:
    """임시 파일에 다 쓴 뒤 바꿔 끼운다.

    그 자리에서 바로 덮어쓰다 중간에 끊기면 .env 가 잘려 SECRET_KEY 같은
    다른 값까지 잃는다.
    """
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(upsert_env(text, key, value), encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        # Windows 에서 편집기나 백신이 .env 를 잡고 있으면 바꿔 끼우기가 실패한다.
        # 토큰이 든 임시 파일을 남기지 않는다.
        tmp.unlink(missing_ok=True)
        raise


class _CatchRedirect(BaseHTTPRequestHandler):
    """구글이 돌려보낸 요청에서 code·error 를 꺼내 서버에 둔다."""

    # 브라우저가 미리 열어 두고 요청을 안 보내는 연결이 있다. 기다리는 상한이
    # 없으면 그 연결을 읽다 멈춰 5분 마감도 못 본다.
    timeout = 5

    def do_GET(self) -> None:
        params = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        # 이번에 연 허락 화면의 state 가 붙은 것만 받는다. 같은 PC 의 다른
        # 프로그램이 이 포트를 한 번 불러도 기다리기가 끝나지 않는다.
        accepted = params.get("state") == self.server.expected_state and (  # type: ignore[attr-defined]
            "code" in params or "error" in params
        )
        if accepted:
            self.server.result = params  # type: ignore[attr-defined]
        # 받지 않은 요청에 "받았습니다" 를 보이면, 브라우저는 끝났다는데 명령은
        # 계속 기다리는 상태가 된다.
        self.send_response(200 if accepted else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DONE_PAGE if accepted else IGNORED_PAGE)

    def log_message(self, format: str, *args) -> None:
        # 기본 로그는 요청 줄을 찍는다. 그 줄에 코드가 들어 있다.
        return


class Command(BaseCommand):
    help = "Gmail API 갱신 토큰을 받아 .env 의 GMAIL_REFRESH_TOKEN 에 적는다(로컬에서 한 번)."

    def add_arguments(self, parser) -> None:
        # 로컬 .env 에는 EMAIL_HOST_USER 를 비워 두게 한다(로컬 개발이 실제 메일을
        # 보내지 않게). 그래서 보내는 주소를 인자로 받는다. 이 값이 없으면 다른
        # 계정으로 허락해도 알 길이 없다.
        parser.add_argument(
            "--sender",
            default="",
            help="보내는 Gmail 주소. 이 계정으로 허락했는지 확인한다. 없으면 EMAIL_HOST_USER.",
        )

    def handle(self, *args, **options) -> None:
        client_id = settings.GMAIL_CLIENT_ID
        client_secret = settings.GMAIL_CLIENT_SECRET
        if not client_id or not client_secret:
            raise CommandError(".env 에 GMAIL_CLIENT_ID 와 GMAIL_CLIENT_SECRET 을 먼저 넣으세요.")
        expected = (options.get("sender") or settings.EMAIL_HOST_USER).strip()
        if not expected:
            raise CommandError("보내는 주소를 알려 주세요: gmail_token --sender <보내는 Gmail 주소>")

        server = HTTPServer(("127.0.0.1", 0), _CatchRedirect)
        server.result = None  # type: ignore[attr-defined]
        server.expected_state = secrets.token_urlsafe(16)  # type: ignore[attr-defined]
        server.timeout = 5
        redirect_uri = f"http://127.0.0.1:{server.server_port}/"

        query = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            # offline + consent 라야 갱신 토큰이 온다. 전에 허락한 적이 있으면
            # consent 없이는 갱신 토큰을 빼고 준다.
            "access_type": "offline",
            "prompt": "consent",
            "state": server.expected_state,  # type: ignore[attr-defined]
            "login_hint": expected,
        }
        url = f"{AUTH_URL}?{urlencode(query)}"

        self.stdout.write("브라우저에서 구글 허락 화면을 엽니다. 안 열리면 아래 주소를 직접 여세요.")
        self.stdout.write(url)
        webbrowser.open(url)

        deadline = time.monotonic() + WAIT_SECONDS
        try:
            while server.result is None:  # type: ignore[attr-defined]
                if time.monotonic() > deadline:
                    raise CommandError(
                        f"{WAIT_SECONDS // 60}분 안에 허락이 오지 않았습니다. 다시 돌리세요."
                    )
                server.handle_request()
        finally:
            server.server_close()

        result = server.result  # type: ignore[attr-defined]
        if "error" in result:
            raise CommandError(f"구글이 허락하지 않았습니다: {result['error']}")

        try:
            response = httpx.post(
                TOKEN_URL,
                data={
                    "code": result["code"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise CommandError(f"구글에 연결하지 못했습니다({type(exc).__name__}). 다시 돌리세요.") from exc
        if response.status_code != 200:
            raise CommandError(f"토큰 교환 실패: {response.status_code} {_error_name(response)}")
        body = _json(response)
        if not body:
            raise CommandError("구글의 토큰 응답을 읽지 못했습니다. 다시 돌리세요.")

        # 허락 화면에서 권한 칸을 하나씩 끌 수 있다. Gmail 보내기 칸을 끄고
        # 허락하면 토큰은 오는데 메일은 못 보낸다. 여기서 막는다.
        if GMAIL_SEND not in str(body.get("scope", "")).split():
            raise CommandError("'Gmail 메일 보내기' 권한에 체크하지 않았습니다. 다시 돌려 체크하세요.")
        refresh_token = body.get("refresh_token")
        if not refresh_token:
            raise CommandError("갱신 토큰이 오지 않았습니다. 다시 돌리세요.")

        account = approved_email(str(body.get("id_token", "")))
        if not account:
            # openid email 을 같이 요청했으니 정상이면 늘 있다. 못 읽었는데 넘어가면
            # 다른 계정으로 허락한 경우를 막는 장치가 빈다.
            raise CommandError("어느 계정으로 허락했는지 확인하지 못했습니다. 다시 돌리세요.")
        if account.lower() != expected.lower():
            raise CommandError(
                f"{account} 로 허락했습니다. 보내는 주소는 {expected} 여야 합니다. "
                "그 계정으로 다시 돌리세요."
            )

        env_path = Path(settings.PROJECT_ROOT) / ".env"
        write_env(env_path, KEY, refresh_token)
        self.stdout.write(
            self.style.SUCCESS(
                f"{account} 의 {KEY} 를 {env_path} 에 적었습니다. "
                "값은 화면에 찍지 않습니다."
            )
        )
