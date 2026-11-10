"""Gmail API 메일 백엔드와 갱신 토큰 명령.

실제 구글에는 붙지 않는다. httpx.Client 를 가짜로 바꿔 무엇을 보내는지,
실패를 어떻게 알리는지만 본다.
"""

from __future__ import annotations

import base64
import email
import json
import tempfile
from pathlib import Path
from unittest import mock

import httpx
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from .gmail_api import SEND_URL, TOKEN_URL, GmailApiBackend, GmailSendError, check_token
from .mail import _really_sends
from .management.commands.gmail_token import approved_email, upsert_env, write_env

GMAIL = "apps.accounts.gmail_api.GmailApiBackend"
CREDS = {
    "GMAIL_CLIENT_ID": "client-id",
    "GMAIL_CLIENT_SECRET": "client-secret",
    "GMAIL_REFRESH_TOKEN": "refresh-token",
    "EMAIL_TIMEOUT": 10,
}


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://example"))


class FakeClient:
    """httpx.Client 대역. post 가 받은 것을 쌓고 정해 둔 응답을 차례로 준다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _message(to: str = "user@example.com") -> EmailMessage:
    return EmailMessage(
        subject="이메일 변경 확인",
        body="아래 링크를 누르세요",
        from_email="sender@gmail.com",
        to=[to],
    )


@override_settings(**CREDS)
class GmailApiBackendTests(SimpleTestCase):
    def _send(self, client: FakeClient, messages, fail_silently: bool = False) -> int:
        with mock.patch("apps.accounts.gmail_api.httpx.Client", client):
            return GmailApiBackend(fail_silently=fail_silently).send_messages(messages)

    def test_sends_raw_message_with_bearer_token(self):
        client = FakeClient([_response(200, {"access_token": "at-1"}), _response(200, {"id": "m1"})])

        self.assertEqual(self._send(client, [_message()]), 1)

        token_url, token_kwargs = client.calls[0]
        self.assertEqual(token_url, TOKEN_URL)
        self.assertEqual(token_kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(token_kwargs["data"]["refresh_token"], "refresh-token")

        send_url, send_kwargs = client.calls[1]
        self.assertEqual(send_url, SEND_URL)
        self.assertEqual(send_kwargs["headers"]["Authorization"], "Bearer at-1")
        parsed = email.message_from_bytes(base64.urlsafe_b64decode(send_kwargs["json"]["raw"]))
        self.assertEqual(parsed["To"], "user@example.com")
        self.assertEqual(parsed["From"], "sender@gmail.com")

    def test_message_without_recipients_is_skipped_without_network(self):
        client = FakeClient([])
        self.assertEqual(self._send(client, [_message(to="")]), 0)
        self.assertEqual(client.calls, [])

    def test_revoked_refresh_token_raises_oserror_with_reason(self):
        client = FakeClient([_response(400, {"error": "invalid_grant"})])
        with self.assertRaises(OSError) as caught:
            self._send(client, [_message()])
        self.assertIsInstance(caught.exception, GmailSendError)
        self.assertIn("invalid_grant", str(caught.exception))
        self.assertNotIn("refresh-token", str(caught.exception))

    def test_gmail_rejection_raises_oserror(self):
        client = FakeClient([
            _response(200, {"access_token": "at-1"}),
            _response(403, {"error": {"status": "PERMISSION_DENIED", "message": "no"}}),
        ])
        with self.assertRaises(GmailSendError) as caught:
            self._send(client, [_message()])
        self.assertIn("PERMISSION_DENIED", str(caught.exception))

    def test_network_failure_becomes_oserror(self):
        client = FakeClient([httpx.ConnectError("unreachable")])
        with self.assertRaises(GmailSendError):
            self._send(client, [_message()])

    def test_token_200_but_not_json_is_oserror_not_500(self):
        # 중간 프록시가 안내 페이지를 끼운 경우. ValueError 가 새면 view 가 500 이 된다.
        page = httpx.Response(200, text="<html>", request=httpx.Request("POST", "https://example"))
        with self.assertRaises(GmailSendError):
            self._send(FakeClient([page]), [_message()])

    def test_token_200_without_access_token_is_oserror(self):
        with self.assertRaises(GmailSendError):
            self._send(FakeClient([_response(200, {})]), [_message()])

    def test_error_body_that_is_not_an_object_is_oserror(self):
        odd = httpx.Response(502, json=["bad gateway"], request=httpx.Request("POST", "https://example"))
        with self.assertRaises(GmailSendError):
            self._send(FakeClient([odd]), [_message()])

    def test_bcc_is_written_into_raw_so_gmail_delivers_it(self):
        client = FakeClient([_response(200, {"access_token": "at-1"}), _response(200, {"id": "m1"})])
        message = _message()
        message.bcc = ["hidden@example.com"]
        self._send(client, [message])
        parsed = email.message_from_bytes(base64.urlsafe_b64decode(client.calls[1][1]["json"]["raw"]))
        self.assertEqual(parsed["Bcc"], "hidden@example.com")

    def test_check_token_reports_revoked_token(self):
        with mock.patch(
            "apps.accounts.gmail_api.httpx.Client", FakeClient([_response(400, {"error": "invalid_grant"})])
        ):
            with self.assertRaisesRegex(GmailSendError, "invalid_grant"):
                check_token()

    def test_check_token_reports_network_failure(self):
        with mock.patch("apps.accounts.gmail_api.httpx.Client", FakeClient([httpx.ConnectTimeout("slow")])):
            with self.assertRaisesRegex(GmailSendError, "ConnectTimeout"):
                check_token()

    def test_fail_silently_returns_count_sent_before_failure(self):
        client = FakeClient([
            _response(200, {"access_token": "at-1"}),
            _response(200, {"id": "m1"}),
            _response(500, {"error": {"status": "INTERNAL"}}),
        ])
        self.assertEqual(self._send(client, [_message(), _message()], fail_silently=True), 1)


class ReallySendsTests(SimpleTestCase):
    def test_gmail_backend_counts_as_real(self):
        with override_settings(EMAIL_BACKEND=GMAIL):
            self.assertTrue(_really_sends())

    def test_smtp_still_counts_as_real(self):
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            self.assertTrue(_really_sends())

    def test_console_and_locmem_do_not(self):
        for backend in ("console", "locmem", "dummy"):
            with override_settings(EMAIL_BACKEND=f"django.core.mail.backends.{backend}.EmailBackend"):
                self.assertFalse(_really_sends(), backend)


class UpsertEnvTests(SimpleTestCase):
    def test_appends_when_missing(self):
        self.assertEqual(upsert_env("A=1\n", "GMAIL_REFRESH_TOKEN", "x"), "A=1\nGMAIL_REFRESH_TOKEN=x\n")

    def test_replaces_every_live_line_and_keeps_others(self):
        text = "A=1\nGMAIL_REFRESH_TOKEN=old\nB=2\nGMAIL_REFRESH_TOKEN = older\n"
        self.assertEqual(
            upsert_env(text, "GMAIL_REFRESH_TOKEN", "new"),
            "A=1\nGMAIL_REFRESH_TOKEN=new\nB=2\nGMAIL_REFRESH_TOKEN=new\n",
        )

    def test_leaves_commented_line_alone(self):
        text = "#GMAIL_REFRESH_TOKEN=old\n"
        self.assertEqual(
            upsert_env(text, "GMAIL_REFRESH_TOKEN", "new"),
            "#GMAIL_REFRESH_TOKEN=old\nGMAIL_REFRESH_TOKEN=new\n",
        )

    def test_does_not_match_longer_key(self):
        text = "GMAIL_REFRESH_TOKEN_OLD=keep\n"
        self.assertIn("GMAIL_REFRESH_TOKEN_OLD=keep", upsert_env(text, "GMAIL_REFRESH_TOKEN", "new"))

    def test_write_env_keeps_other_values_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("DJANGO_SECRET_KEY=s3cr3t\n", encoding="utf-8")
            write_env(path, "GMAIL_REFRESH_TOKEN", "new")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "DJANGO_SECRET_KEY=s3cr3t\nGMAIL_REFRESH_TOKEN=new\n",
            )
            self.assertEqual([p.name for p in Path(folder).iterdir()], [".env"])


class ApprovedEmailTests(SimpleTestCase):
    def _id_token(self, claims: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return f"header.{body}.signature"

    def test_reads_email_claim(self):
        self.assertEqual(approved_email(self._id_token({"email": "me@gmail.com"})), "me@gmail.com")

    def test_broken_token_gives_empty_string(self):
        self.assertEqual(approved_email("not-a-jwt"), "")
        self.assertEqual(approved_email("a.%%%.c"), "")


@override_settings(EMAIL_BACKEND=GMAIL)
class DailyCleanupTokenCheckTests(TestCase):
    """안내할 회원이 없는 날에도 토큰을 써 본다(6개월 미사용 만료 막기)."""

    def test_dead_token_fails_the_run_even_with_nobody_to_notify(self):
        with mock.patch(
            "apps.learning.management.commands.daily_cleanup.check_token",
            side_effect=GmailSendError("Gmail 토큰 교환 실패: 400 invalid_grant"),
        ):
            with self.assertRaisesRegex(CommandError, "invalid_grant"):
                call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())

    def test_live_token_runs_through(self):
        with mock.patch("apps.learning.management.commands.daily_cleanup.check_token") as check:
            call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())
        check.assert_called_once()

    def test_day_with_sent_notices_does_not_ask_again(self):
        # 보낸 날은 그 발송이 이미 토큰을 썼다. 먼저 물으면 확인이 한 번 일시
        # 실패한 날 안내를 통째로 건너뛴다.
        with mock.patch("apps.accounts.purge.send_notices", return_value=(1, 0)), mock.patch(
            "apps.learning.management.commands.daily_cleanup.check_token"
        ) as check:
            call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())
        check.assert_not_called()

    def test_day_with_only_failures_ends_with_the_existing_error(self):
        with mock.patch("apps.accounts.purge.send_notices", return_value=(0, 2)), mock.patch(
            "apps.learning.management.commands.daily_cleanup.check_token"
        ) as check:
            with self.assertRaisesRegex(CommandError, "한 통도"):
                call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())
        check.assert_not_called()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_smtp_backend_skips_the_check(self):
        with mock.patch("apps.learning.management.commands.daily_cleanup.check_token") as check:
            call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())
        check.assert_not_called()
