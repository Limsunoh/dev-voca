"""하루 한 번 돌리는 정리.

사용:
    python manage.py daily_cleanup            # 몇 건인지 세기만 한다
    python manage.py daily_cleanup --apply    # 실제로 메일을 보내고 지운다

기본이 미리 보기인 이유: 계정을 지우는 작업은 되돌릴 수 없다. 옵션을 빠뜨렸을
때 아무 일도 안 일어나는 쪽이 안전하다. 등록 방법은 DEPLOY.md "정기 정리".

learning 에 둔 이유: accounts 는 다른 앱을 부르지 않는다. learning 은 이미
사용자 모델에 FK 로 묶여 있다.

출력에 이메일을 넣지 않는다. 건수만 있어도 운영에 충분하고, 표준 출력은
호스팅 업체의 로그로 나간다.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts import purge
from apps.accounts.gmail_api import GmailSendError, check_token
from apps.accounts.mail import GMAIL_BACKEND, MailNotConfigured
from apps.accounts.models import LoginToken
from apps.accounts.throttles import sweep_expired_counters
from apps.learning.session import expired_steps


class Command(BaseCommand):
    help = "오래 쓰지 않은 계정과 수명이 다한 기록을 정리한다. --apply 없이는 세기만 한다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 메일을 보내고 지운다",
        )

    def handle(self, *args, **options) -> None:
        if not options["apply"]:
            self.stdout.write(
                "[미리 보기] "
                f"삭제 {purge.due_for_delete().count()}명, "
                f"안내 메일 {purge.due_for_notice().count()}명, "
                f"진행 표시 {expired_steps().count()}행, "
                f"시도 횟수 {sweep_expired_counters(apply=False)}행, "
                f"로그인 토큰 {LoginToken.expired().count()}개"
            )
            return

        # 지우기를 먼저 한다. 메일 계정 문제로 안내가 실패해도 기한이 지난
        # 회원의 삭제는 돌아야 한다.
        deleted = purge.delete_expired()
        steps, _ = expired_steps().delete()
        counters = sweep_expired_counters(apply=True)
        tokens, _ = LoginToken.expired().delete()
        self.stdout.write(
            f"삭제 {deleted}명, 진행 표시 {steps}행, 시도 횟수 {counters}행, 로그인 토큰 {tokens}개"
        )

        try:
            sent, failed = purge.send_notices()
        except MailNotConfigured as exc:
            raise CommandError(str(exc)) from exc

        # Gmail API 로 보낼 때, 안내할 회원이 없던 날은 토큰을 한 번 써 본다.
        # 구글은 6개월 동안 안 쓴 갱신 토큰을 풀어 버린다. 서비스를 연 직후에는
        # 1년 미접속 회원이 없어 몇 달씩 한 통도 안 보내므로, 그대로 두면 첫 안내
        # 날에야 토큰이 죽은 걸 알고 그날 안내가 전부 실패한다. 보낸 날은 그
        # 발송이 이미 토큰을 썼으니 다시 묻지 않는다. 먼저 물으면 확인이 한 번
        # 일시 실패한 날 안내를 통째로 건너뛴다.
        if not sent and not failed and settings.EMAIL_BACKEND.endswith(GMAIL_BACKEND):
            try:
                check_token()
            except GmailSendError as exc:
                raise CommandError(
                    f"{exc}. invalid_grant 면 토큰이 풀린 것이다. DEPLOY.md 의 "
                    "'메일 발송 (Gmail API)' 대로 gmail_token 을 다시 돌려 새 토큰을 넣는다."
                ) from exc

        if failed and not sent:
            raise CommandError(
                f"안내 메일을 한 통도 보내지 못했습니다({failed}명 실패). 발송 계정이나 해당 회원의 주소를 확인하세요."
            )

        self.stdout.write(self.style.SUCCESS(f"안내 메일 {sent}명, 실패 {failed}명"))
