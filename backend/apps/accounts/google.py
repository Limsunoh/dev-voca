"""구글 로그인.

Next 서버가 구글에서 받은 코드를 이쪽으로 넘기면, 여기서 구글에 직접
확인하고 계정을 찾거나 만든다.

코드가 아니라 사용자 정보를 그대로 받으면 안 된다. 그러면 누구든
"나는 admin@example.com 이다" 라고 보내서 남의 계정으로 들어올 수 있다.
구글에 되물어 확인하는 절차가 그것을 막는다.
"""

from __future__ import annotations

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
