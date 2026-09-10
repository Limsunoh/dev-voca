"""계정 관련 메일 발송.

메일을 보내는 곳을 여기 하나로 모은다. 흩어두면 "운영인데 계정이 없으면
막는다" 같은 판단이 한 곳만 고쳐지고 나머지는 조용히 콘솔로 떨어진다.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class MailNotConfigured(RuntimeError):
    """운영인데 발송 계정이 없다. 보내려는 순간에 터진다."""


def _really_sends() -> bool:
    """정말로 메일이 나가는 백엔드인가.

    "console 이면 안 나간다" 가 아니라 **"smtp 여야 나간다"** 로 판정한다.
    앞의 방식은 목록에 없는 백엔드를 전부 통과시킨다 - dummy(전부 버림)나
    locmem(메모리에 쌓기)로 두면 send_mail 이 조용히 성공하고, 화면은
    "보냈습니다" 인데 메일은 어디에도 없다. 이 모듈이 막겠다고 한 바로
    그 상황이 다른 이름으로 들어온다.
    """
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


def send_account_mail(*, to: str, subject: str, body: str) -> None:
    """계정 메일 한 통.

    **운영에서 계정이 비어 있으면 예외를 던진다.** settings 가 아니라
    여기서 막는 이유는 settings.py 주석에 적어뒀다 - 기동에서 막으면 CI 의
    `manage.py check` 가 메일과 무관하게 깨진다.

    조용히 콘솔로 떨어지는 것만은 반드시 막아야 한다. 그러면 확인 링크가
    안 갔는데 화면은 "보냈습니다" 라고 말하고, 사용자는 오지 않을 메일을
    기다리며 스팸함을 뒤진다. 실패는 실패라고 말해야 다시 시도할 수 있다.

    개발(DEBUG)에서는 콘솔로 찍는다. 앱 비밀번호 없이도 확인 링크를 눈으로
    보고 흐름을 끝까지 밟을 수 있어야 한다.
    """
    if not _really_sends() and not settings.DEBUG:
        raise MailNotConfigured(
            "발송 계정이 설정되지 않아 메일을 보낼 수 없습니다. "
            "EMAIL_HOST_USER 와 EMAIL_HOST_PASSWORD 를 확인하세요."
        )

    # fail_silently 를 끄고 둔다. 켜면 SMTP 가 거절해도 아무 일 없었던 듯
    # 넘어가, 위에서 막은 것과 똑같은 상황이 다른 경로로 생긴다.
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        recipient_list=[to],
        fail_silently=False,
    )
