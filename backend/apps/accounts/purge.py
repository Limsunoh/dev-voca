"""오래 쓰지 않은 계정을 미리 알린 뒤 지운다.

마지막 이용에서 335일이 지나면 메일을 한 번 보내고, 안내한 지 30일이
지나도록 돌아오지 않으면 계정과 학습 기록을 지운다.

지우는 조건에 안내 시각을 넣은 이유: 메일이 못 나간 회원이 먼저 지워지면
안 된다. 안내가 나가지 않은 회원은 지워질 수 없는 구조로 둔다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from .gmail_api import GmailSendError
from .mail import MailNotConfigured, _really_sends, send_account_mail

logger = logging.getLogger(__name__)

NOTICE_AFTER_DAYS = 335
DELETE_AFTER_NOTICE_DAYS = 30


def _members() -> QuerySet:
    """대상이 되는 회원.

    관리자와 검수자는 오래 안 써도 지우지 않는다. 정지한 계정도 뺀다. 안내
    메일의 "로그인해 주세요" 를 따를 수 없고, 지우면 그 이메일로 다시 가입할
    수 있어 정지가 풀리는 셈이다. 정지 계정은 운영자가 판단해 지운다.
    """
    return get_user_model().objects.filter(
        is_staff=False, is_superuser=False, is_active=True
    )


def _stale_since() -> date:
    return timezone.localdate() - timedelta(days=NOTICE_AFTER_DAYS)


def due_for_notice() -> QuerySet:
    """안내 메일을 보낼 회원."""
    return _members().filter(
        last_seen_on__lte=_stale_since(), purge_notice_sent_at__isnull=True
    )


def due_for_delete() -> QuerySet:
    """지울 회원. 되돌릴 수 없는 작업이라 안내 시각에 더해 마지막 이용일도 본다."""
    return _members().filter(
        last_seen_on__lte=_stale_since(),
        purge_notice_sent_at__lte=timezone.now()
        - timedelta(days=DELETE_AFTER_NOTICE_DAYS),
    )


def build_notice_mail() -> tuple[str, str]:
    """안내 메일의 (제목, 본문). 광고 문구를 섞지 않는다."""
    days = DELETE_AFTER_NOTICE_DAYS
    subject = f"[DeVoca] 오래 이용하지 않은 계정을 {days}일 뒤 삭제합니다"
    body = (
        "DeVoca 계정을 오랫동안 이용하지 않으셔서 안내드립니다.\n\n"
        f"{days}일 안에 이용하지 않으시면 계정과 학습 기록(점수, 오답 노트, 복습 기록)이 "
        "삭제되며 되돌릴 수 없습니다.\n\n"
        f"계속 쓰시려면 {days}일 안에 DeVoca 에 로그인해 주세요. 이용하시면 이 안내는 "
        "취소됩니다.\n"
    )
    return subject, body


def send_notices() -> tuple[int, int]:
    """안내 메일을 보내고 (보낸 수, 실패 수) 를 돌려준다.

    한 통이 실패해도 나머지는 보낸다. 실패한 회원은 안내 시각이 안 찍혀 다음
    날 다시 시도한다.

    정말 나가는 백엔드가 아니면 시작하지 않는다. 콘솔 백엔드는 에러 없이
    끝나서, 메일이 한 통도 안 나갔는데 안내한 것으로 기록되고 30일 뒤에
    지워진다.
    """
    targets = list(due_for_notice().values_list("pk", "email"))
    if targets and not _really_sends():
        raise MailNotConfigured("발송 계정이 없어 파기 안내 메일을 보낼 수 없습니다.")

    subject, body = build_notice_mail()
    sent = failed = 0

    for pk, email in targets:
        try:
            send_account_mail(to=email, subject=subject, body=body)
        except (OSError, ValueError) as exc:
            # 예외 메시지에 주소가 들어 있을 수 있어 종류만 남긴다. GmailSendError
            # 는 상태 코드와 구글 오류 이름만 담으므로 문구까지 남긴다. 그래야
            # "토큰이 풀렸다(invalid_grant)" 를 로그에서 바로 안다.
            logger.error(
                "파기 안내 메일을 보내지 못했습니다. user=%s reason=%s",
                pk,
                str(exc) if isinstance(exc, GmailSendError) else type(exc).__name__,
            )
            failed += 1
            continue

        # 조건을 다시 건다. 메일을 보내는 사이 돌아온 회원에게 안내 시각을
        # 찍으면, 1년 뒤에 새 안내 없이 지워진다.
        due_for_notice().filter(pk=pk).update(purge_notice_sent_at=timezone.now())
        sent += 1

    return sent, failed


def delete_expired() -> int:
    """안내 기한이 지난 회원을 지우고 지운 수를 돌려준다.

    목록을 뽑은 뒤 돌아온 회원이 있을 수 있어 지우는 순간에 조건을 다시 걸고
    행을 잠근다. 잠그지 않으면 조건을 본 뒤 지우기 전에 돌아온 회원이 지워진다.
    학습 기록은 CASCADE 로 함께 지워진다.
    """
    deleted = 0

    for pk in list(due_for_delete().values_list("pk", flat=True)):
        with transaction.atomic():
            user = due_for_delete().select_for_update().only("pk").filter(pk=pk).first()
            if user is None:
                continue
            user.delete()
        deleted += 1

    return deleted
