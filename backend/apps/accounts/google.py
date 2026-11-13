"""구글 로그인.

화면이 구글 버튼에서 받은 신분 토큰(verify_google_credential), 또는 Next
서버가 구글 화면을 다녀와 받은 코드(fetch_google_user)를 넘기면, 여기서
구글에 직접 확인한다. 계정을 찾거나 만드는 일은 뷰가 한다.

코드가 아니라 사용자 정보를 그대로 받으면 안 된다. 그러면 누구든
"나는 admin@example.com 이다" 라고 보내서 남의 계정으로 들어올 수 있다.
구글에 되물어 확인하는 절차가 그것을 막는다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# 코드를 토큰으로 바꾸는 곳.
TOKEN_URL = "https://oauth2.googleapis.com/token"

# 그 토큰으로 사용자 정보를 받는 곳.
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# 구글이 응답하지 않을 때 무한정 기다리지 않는다. 사용자는 로그인
# 버튼을 누른 채 화면을 보고 있다.
TIMEOUT = 10.0


class GoogleAuthError(Exception):
    """구글 확인에 실패했다. 호출부가 400 으로 바꾼다."""


def _require(name: str) -> str:
    """설정값을 읽는다. 없으면 사유는 로그에만 남긴다.

    설정 이름을 응답에 담지 않는 이유: 사용자가 할 수 있는 일이 없고,
    무엇이 빠졌는지는 서버 사정이다.
    """
    value = getattr(settings, name, "")
    if not value:
        logger.error("%s 가 설정되지 않아 구글 로그인을 쓸 수 없습니다.", name)
        raise GoogleAuthError("구글 로그인을 지금 쓸 수 없습니다.")
    return value


def fetch_google_user(code: str, redirect_uri: str) -> dict:
    """구글이 준 코드로 사용자 정보를 받아온다.

    redirect_uri 를 함께 보내는 이유: 구글이 코드를 발급할 때 쓴 주소와
    같은지 대조한다. 다르면 거절한다 - 남의 코드를 가로채 다른 사이트에서
    쓰는 것을 막는 장치다.

    돌려주는 것: {"email": ..., "name": ..., "picture": ...}
    확인되지 않은 이메일은 여기서 걸러내므로 호출부는 검사할 필요가 없다.
    """
    client_id = _require("GOOGLE_CLIENT_ID")
    client_secret = _require("GOOGLE_CLIENT_SECRET")

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            token_res = client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code != 200:
                # 코드가 이미 쓰였거나, 만료됐거나, redirect_uri 가 다르다.
                raise GoogleAuthError("구글 로그인을 확인하지 못했습니다.")

            access_token = token_res.json().get("access_token")
            if not access_token:
                raise GoogleAuthError("구글이 토큰을 주지 않았습니다.")

            info_res = client.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_res.status_code != 200:
                raise GoogleAuthError("구글 계정 정보를 받지 못했습니다.")

    except httpx.HTTPError as exc:
        # 네트워크가 끊겼거나 구글이 응답하지 않는 경우.
        raise GoogleAuthError("구글에 연결할 수 없습니다.") from exc
    except ValueError as exc:
        # 200 인데 본문이 JSON 이 아닌 경우. 중간의 프록시가 안내 페이지를
        # 끼워 넣으면 이렇게 된다. 안 잡으면 500 이 난다.
        raise GoogleAuthError("구글 응답을 읽지 못했습니다.") from exc

    try:
        info = info_res.json()
    except ValueError as exc:
        raise GoogleAuthError("구글 응답을 읽지 못했습니다.") from exc

    email = (info.get("email") or "").strip()
    if not email:
        raise GoogleAuthError("구글 계정에 이메일이 없습니다.")

    # 확인되지 않은 이메일은 받지 않는다. 남의 주소를 적어둔 계정일 수
    # 있고, 그대로 받으면 그 주소의 진짜 주인 계정으로 들어가게 된다.
    if not info.get("email_verified"):
        raise GoogleAuthError("이메일이 확인되지 않은 구글 계정입니다.")

    return {
        "email": email,
        "name": (info.get("name") or "").strip(),
        "picture": _safe_picture(info.get("picture")),
    }


# 구글이 브라우저에 준 신분 토큰(ID 토큰)을 확인해 주는 곳.
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# 구글 ID 토큰의 발급자. 구글 문서가 두 표기를 모두 쓴다.
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_credential(credential: str, nonce_secret: str) -> dict:
    """구글 로그인 버튼이 브라우저에 준 신분 토큰을 확인한다.

    화면 아래 계정 창(FedCM)으로 로그인하면 페이지를 떠나지 않아 코드 대신
    이 토큰이 온다. 구글이 서명한 JWT 라 아무나 만들 수 없지만, 그대로 믿지
    않고 구글에 되물어 서명과 만료를 확인한다(tokeninfo).

    그 뒤 우리 것인지 본다:
    - aud 가 우리 클라이언트 ID 여야 한다. 다른 사이트용으로 발급된 토큰을
      가져와 들어오는 것을 막는다.
    - 토큰의 nonce 가 nonce_secret 의 sha256 이어야 한다. 화면은 버튼을 그릴
      때 비밀값을 정해 httpOnly 쿠키에 두고, 구글에는 그 해시만 넘긴다. 토큰은
      서명만 돼 있고 암호화돼 있지 않아 안의 nonce 는 누구나 읽지만, 비밀값은
      그 브라우저의 쿠키에만 있다. 그래서 새어 나간 토큰을 다른 곳에서 다시
      보내도 통과하지 못한다(OpenID Connect 가 권하는 방식).

    돌려주는 것은 fetch_google_user 와 같다.

    ponytail: 서명 확인을 구글 tokeninfo 에 맡겨 로그인마다 구글을 한 번
    부른다. 로그인이 많아지면 google-auth 로 공개키를 받아 두고 직접 확인한다.

    ponytail: 같은 토큰과 비밀값을 한 번만 쓰게 막지는 않는다. Next 에서 이리
    오는 요청 본문이 통째로 새면 토큰이 만료될 때까지(약 1시간) 다시 쓸 수
    있다. 본문을 남기는 로그가 없어 지금은 두고, 막으려면 쓴 nonce 를 DB 표에
    유일 값으로 남긴다(캐시는 지워질 수 있어 안 된다, settings 의 CACHES 주석).
    """
    client_id = _require("GOOGLE_CLIENT_ID")
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            # 주소(쿼리)가 아니라 본문에 싣는다. 주소는 로그에 남기 쉽다.
            res = client.post(TOKENINFO_URL, data={"id_token": credential})
    except httpx.HTTPError as exc:
        raise GoogleAuthError("구글에 연결할 수 없습니다.") from exc
    if res.status_code != 200:
        # 서명이 틀렸거나 만료됐다.
        raise GoogleAuthError("구글 로그인을 확인하지 못했습니다.")
    try:
        info = res.json()
    except ValueError as exc:
        raise GoogleAuthError("구글 응답을 읽지 못했습니다.") from exc
    if not isinstance(info, dict):
        raise GoogleAuthError("구글 응답을 읽지 못했습니다.")

    if info.get("aud") != client_id or info.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleAuthError("구글 로그인을 확인하지 못했습니다.")
    token_nonce = info.get("nonce")
    expected = hashlib.sha256(nonce_secret.encode()).hexdigest()
    # 바이트로 비교한다. 글자로 넘기면 한글 같은 값에서 TypeError 가 나 500 이 된다.
    if not isinstance(token_nonce, str) or not hmac.compare_digest(
        token_nonce.encode(), expected.encode()
    ):
        raise GoogleAuthError("구글 로그인을 확인하지 못했습니다.")

    email = info.get("email")
    if not isinstance(email, str) or not email.strip():
        raise GoogleAuthError("구글 계정에 이메일이 없습니다.")
    # tokeninfo 는 참거짓을 글자("true")로 준다.
    if info.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("이메일이 확인되지 않은 구글 계정입니다.")
    name = info.get("name")
    return {
        "email": email.strip(),
        "name": name.strip() if isinstance(name, str) else "",
        "picture": _safe_picture(info.get("picture")),
    }


def _safe_picture(value: object) -> str:
    """구글이 준 사진 주소. 믿을 수 있는 것만 통과시킨다.

    이 값은 그대로 저장돼 나중에 브라우저가 불러온다. 검사 없이 받으면
    구글 응답이 바뀌거나 중간에서 갈아치웠을 때 아무 주소나 화면에 박히고,
    사용자가 우리 화면을 여는 것만으로 그쪽 서버에 요청이 나간다.

    javascript: 같은 스킴도 여기서 걸린다. img 태그에서는 실행되지 않지만,
    나중에 이 값을 링크로 쓰는 곳이 생기면 그때 문제가 된다.
    """
    if not isinstance(value, str):
        return ""

    url = value.strip()
    if not url.startswith("https://"):
        return ""

    # DB 컬럼이 500자다. 넘치면 저장할 때 잘리거나 터진다.
    return url if len(url) <= 500 else ""
