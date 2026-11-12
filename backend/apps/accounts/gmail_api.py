"""Gmail API 로 메일을 보내는 Django 메일 백엔드.

Railway 는 Hobby 요금제에서 바깥으로 나가는 SMTP(465·587)를 막는다
(docs.railway.com/networking/outbound-networking 의 Email delivery). 같은
서버에서 HTTPS(443)는 나간다. 그래서 SMTP 대신 Gmail API 에 HTTPS 로
보낸다. 보내는 계정은 SMTP 때와 같은 Gmail 이라 받는 사람 쪽에서 달라지는
것은 없다.

인증은 OAuth 갱신 토큰이다. 브라우저에서 한 번 허락해 받은 토큰
(`manage.py gmail_token`)을 환경변수에 두고, 보낼 때마다 그걸로 짧게 쓰는
접근 토큰을 받는다. 갱신 토큰은 이럴 때 풀린다.
- 구글 계정 비밀번호를 바꾸거나 허락을 취소했을 때
- 6개월 동안 한 번도 안 썼을 때. daily_cleanup 이 매일 check_token 으로 한 번씩
  써서 막는다.
풀리면 토큰 교환이 invalid_grant 로 실패한다. 그때는 gmail_token 을 다시 돌린다.
"""

from __future__ import annotations

import base64
import logging
import re

import httpx
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# 단계마다 따로 걸리는 값이다. 토큰 주소와 발송 주소는 호스트가 달라 연결을
# 두 번 맺고, 연결마다 TCP 연결·TLS 맺기·쓰기·읽기 네 단계에 이 제한이 걸린다.
# 대략 최악이 2 x 4단계 x 3초 = 24초다(읽기는 조각마다 걸리고 DNS 조회는 이
# 제한 밖이라 정확한 상한은 아니다).
# 처음에는 gunicorn 이 30초에 요청을 끊어서, 그 안에 끝나야 "메일을 보내지 못했습니다"
# 안내가 나갔다. 스레드 방식(--threads)으로 바꾼 뒤로는 gunicorn 이 끊지 않으므로
# (DEPLOY.md) 발송이 오래 멈추는 것을 막는 것은 이 값뿐이다. 멈춘 동안 스레드 하나를
# 붙잡는다. settings.EMAIL_TIMEOUT(10초)을 그대로 쓰면 80초까지 갈 수 있다.
TIMEOUT = httpx.Timeout(3.0)


class GmailSendError(OSError):
    """보내지 못했다.

    OSError 를 잇는 이유: 부르는 쪽(views.EmailChangeRequestView,
    purge.send_notices)이 SMTP 실패를 OSError 로 받는다. Gmail API
    실패도 같은 자리에서 같은 안내로 끝나게 맞춘다.

    문구에는 상태 코드와 구글이 준 오류 이름만 넣는다. 토큰이나 받는 사람
    주소는 넣지 않으므로 로그에 그대로 남겨도 된다.
    """


def _json(response: httpx.Response) -> dict:
    """응답 본문을 dict 로. 아니면 빈 dict.

    중간 프록시가 안내 페이지를 끼우면 200 인데 JSON 이 아니다. 여기서
    예외가 새면 부르는 쪽의 except OSError 를 지나 500 이 된다
    (google.py 의 같은 처리 참고).
    """
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _error_name(response: httpx.Response) -> str:
    """구글 오류 응답에서 원인 이름만 뽑는다.

    토큰 교환은 {"error": "invalid_grant"}, Gmail API 는
    {"error": {"status": "PERMISSION_DENIED", "message": ...}} 로 준다. 이름을
    남겨야 "다시 허락받아야 한다" 를 로그만 보고 안다.

    이름처럼 생긴 값(영문·밑줄)만 받는다. message 같은 설명 글에는 받는 사람
    주소가 들어갈 수 있고("Invalid To header: x@y"), 이 문구는 purge 로그에
    그대로 남는다.
    """
    error = _json(response).get("error", "")
    if isinstance(error, dict):
        error = error.get("status", "")
    error = str(error)
    return error if re.fullmatch(r"[A-Za-z_]{1,64}", error) else "(이름 없는 오류)"


def _access_token(client: httpx.Client) -> str:
    response = client.post(
        TOKEN_URL,
        data={
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "refresh_token": settings.GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
    )
    if response.status_code != 200:
        raise GmailSendError(
            f"Gmail 토큰 교환 실패: {response.status_code} {_error_name(response)}"
        )
    token = _json(response).get("access_token")
    if not token:
        raise GmailSendError("Gmail 토큰 교환 실패: 200 인데 access_token 이 없음")
    return token


def check_token() -> None:
    """갱신 토큰이 살아 있는지 메일 없이 확인한다. 실패하면 GmailSendError.

    한 번 쓰는 것만으로 6개월 미사용 만료가 다시 센다.
    """
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            _access_token(client)
    except httpx.HTTPError as exc:
        raise GmailSendError(f"Gmail API 연결 실패: {type(exc).__name__}") from exc


def _raw(message) -> str:
    mime = message.message()
    # Django 는 원문에 Bcc 를 안 적는다(SMTP 는 받는 사람을 따로 넘겨서 괜찮다).
    # Gmail API 는 원문 머리만 보고 보내므로, 적지 않으면 숨은 참조가 조용히
    # 빠진다. Gmail 은 Bcc 머리를 읽고 지운 뒤 보낸다.
    if message.bcc:
        mime["Bcc"] = ", ".join(message.bcc)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")


class GmailApiBackend(BaseEmailBackend):
    """settings.EMAIL_BACKEND 로 고른다. 고르는 조건은 settings.py 메일 절."""

    def send_messages(self, email_messages) -> int:
        messages = [m for m in email_messages if m.recipients()]
        if not messages:
            return 0

        sent = 0
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                # ponytail: 부를 때마다 접근 토큰을 새로 받는다. send_account_mail 은
                # 한 통씩 부르므로 한 통에 왕복이 둘이다. 하루 수십 통을 넘기면
                # 만료 시각(expires_in)까지 재사용한다.
                token = _access_token(client)
                for message in messages:
                    response = client.post(
                        SEND_URL,
                        json={"raw": _raw(message)},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if response.status_code != 200:
                        raise GmailSendError(
                            f"Gmail 발송 실패: {response.status_code} {_error_name(response)}"
                        )
                    sent += 1
        except GmailSendError as exc:
            if not self.fail_silently:
                raise
            logger.warning("Gmail API 발송 실패를 넘김: %s", exc)
        except httpx.HTTPError as exc:
            # 연결 끊김·시간 초과. 원인 이름만 남긴다.
            if not self.fail_silently:
                raise GmailSendError(f"Gmail API 연결 실패: {type(exc).__name__}") from exc
            logger.warning("Gmail API 연결 실패를 넘김: %s", type(exc).__name__)
        return sent
