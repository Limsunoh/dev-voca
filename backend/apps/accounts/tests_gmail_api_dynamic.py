"""Gmail API 발송을 부르는 쪽까지 끝까지 밟아 보는 테스트.

tests_gmail_api.py 는 백엔드와 명령의 부품을 하나씩 본다. 여기서는 부품을
가짜로 바꾸지 않고, 바깥(구글)만 가짜로 둔 채 실제로 사용자가 지나는 길을
본다.

- 이메일 변경 API 가 구글 실패를 502 와 같은 안내로 끝내는가
- 파기 안내(purge)·daily_cleanup 의 로그와 오류에 주소·비밀값이 안 새는가
- settings 가 값이 일부만 있을 때 어느 백엔드를 고르는가
- gmail_token 의 루프백 서버가 state 가 틀린 요청을 무시하는가
"""

from __future__ import annotations

import base64
import email
import json
import logging
import os
import runpy
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import LoginToken

from . import purge
from .gmail_api import SEND_URL, TOKEN_URL, GmailApiBackend, GmailSendError
from .management.commands import gmail_token

User = get_user_model()

GMAIL = "apps.accounts.gmail_api.GmailApiBackend"
SMTP = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
SECRET = "client-secret-XYZ"
REFRESH = "refresh-token-XYZ"
PASSWORD = "Str0ng-pass!word"
EMAIL_CHANGE_URL = "/api/accounts/email-change/"
FAILED_DETAIL = "확인 메일을 보내지 못했습니다. 잠시 후 다시 시도해주세요."

# 운영과 같은 조건(DEBUG=False)에 Gmail 백엔드를 고른 상태.
GMAIL_ON = {
    "DEBUG": False,
    "EMAIL_BACKEND": GMAIL,
    "EMAIL_HOST_USER": "sender@gmail.com",
    "DEFAULT_FROM_EMAIL": "sender@gmail.com",
    "GMAIL_CLIENT_ID": "client-id",
    "GMAIL_CLIENT_SECRET": SECRET,
    "GMAIL_REFRESH_TOKEN": REFRESH,
}


def _response(status: int, body=None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example")
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(status, json=body, request=request)


TOKEN_OK = _response(200, {"access_token": "at-1", "expires_in": 3599})


class FakeGoogle:
    """httpx.Client 대역. 받은 요청을 쌓고 정해 둔 응답을 차례로 준다."""

    def __init__(self, *responses):
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

    def sent_raw(self, index: int = -1) -> email.message.Message:
        """index 번째 발송 요청의 원문을 메일로 풀어 준다."""
        sends = [kwargs for url, kwargs in self.calls if url == SEND_URL]
        return email.message_from_bytes(base64.urlsafe_b64decode(sends[index]["json"]["raw"]))


def _google(*responses) -> tuple[FakeGoogle, mock._patch]:
    fake = FakeGoogle(*responses)
    return fake, mock.patch("apps.accounts.gmail_api.httpx.Client", fake)


def _formatted(records) -> str:
    """로그 레코드를 운영 로그처럼 traceback 까지 붙여 글로 만든다."""
    formatter = logging.Formatter("%(message)s")
    return "\n".join(formatter.format(record) for record in records)


@override_settings(**GMAIL_ON)
class EmailChangeThroughGmailTest(TestCase):
    """이메일 변경 신청을 Gmail 백엔드로 끝까지 보낸다. 구글만 가짜다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="old@example.com", password=PASSWORD, display_name="주인"
        )
        self.token = LoginToken.objects.create(user=self.user)

    def request_change(self):
        return self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": "new@example.com", "current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def assert_502_without_leak(self, *responses):
        fake, patcher = _google(*responses)
        with patcher, self.assertLogs("apps.accounts.views", "ERROR") as logs:
            res = self.request_change()

        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["detail"], FAILED_DETAIL)
        text = _formatted(logs.records)
        for secret in (SECRET, REFRESH, "at-1", "new@example.com"):
            self.assertNotIn(secret, text)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        return fake

    def test_성공하면_202_이고_확인_링크가_새_주소로_간다(self):
        fake, patcher = _google(TOKEN_OK, _response(200, {"id": "m1"}))
        with patcher:
            res = self.request_change()

        self.assertEqual(res.status_code, 202)
        sent = fake.sent_raw()
        self.assertEqual(sent["To"], "new@example.com")
        self.assertEqual(sent["From"], "sender@gmail.com")
        body = sent.get_payload(decode=True).decode("utf-8")
        self.assertIn("/profile/email/", body)

    def test_토큰이_풀리면_502(self):
        """invalid_grant. 운영에서 가장 먼저 만날 실패다."""
        fake = self.assert_502_without_leak(_response(400, {"error": "invalid_grant"}))
        self.assertEqual(len(fake.calls), 1)

    def test_구글이_발송을_거절하면_502(self):
        self.assert_502_without_leak(
            TOKEN_OK, _response(403, {"error": {"status": "PERMISSION_DENIED", "message": "no"}})
        )

    def test_연결이_끊기면_502(self):
        self.assert_502_without_leak(httpx.ConnectError("getaddrinfo failed"))

    def test_발송_도중_시간_초과면_502(self):
        self.assert_502_without_leak(TOKEN_OK, httpx.ReadTimeout("timed out"))

    def test_토큰_응답이_JSON_이_아니어도_502(self):
        """프록시 안내 페이지. ValueError 가 새면 500 이 된다."""
        self.assert_502_without_leak(_response(200, text="<html>captive</html>"))

    def test_발송_응답이_JSON_이_아니어도_502(self):
        self.assert_502_without_leak(TOKEN_OK, _response(503, text="<html>down</html>"))

    @override_settings(GMAIL_REFRESH_TOKEN="")
    def test_백엔드는_Gmail_인데_토큰이_비면_구글에_그대로_묻고_502(self):
        """settings 를 거치지 않고 값이 빠진 경우. 500 이 아니어야 한다."""
        fake = self.assert_502_without_leak(_response(400, {"error": "invalid_request"}))
        self.assertEqual(fake.calls[0][1]["data"]["refresh_token"], "")


class BackendEdgeTest(SimpleTestCase):
    """백엔드 자체에서 기존 테스트가 안 본 자리."""

    @override_settings(**GMAIL_ON)
    def test_bcc_에_줄바꿈을_넣어도_머리가_늘지_않는다(self):
        """원문에 Bcc 를 직접 적으므로 머리 주입이 되는지 본다."""
        message = EmailMessage("s", "b", "sender@gmail.com", ["a@example.com"])
        message.bcc = ["x@example.com\nX-Evil: 1"]
        fake, patcher = _google(TOKEN_OK, _response(200, {"id": "m1"}))
        with patcher, self.assertRaises(ValueError):
            GmailApiBackend().send_messages([message])
        self.assertEqual([url for url, _ in fake.calls if url == SEND_URL], [])

    @override_settings(**GMAIL_ON)
    def test_한글_이름이_붙은_bcc_도_주소가_살아_있다(self):
        message = EmailMessage("제목", "본문", "sender@gmail.com", ["a@example.com"])
        message.bcc = ["숨은 사람 <hidden@example.com>"]
        fake, patcher = _google(TOKEN_OK, _response(200, {"id": "m1"}))
        with patcher:
            self.assertEqual(GmailApiBackend().send_messages([message]), 1)
        bcc = email.utils.getaddresses([fake.sent_raw()["Bcc"]])
        self.assertEqual(bcc[0][1], "hidden@example.com")

    @override_settings(**GMAIL_ON)
    def test_bcc_만_있는_메일도_보낸다(self):
        message = EmailMessage("s", "b", "sender@gmail.com", [], bcc=["only@example.com"])
        fake, patcher = _google(TOKEN_OK, _response(200, {"id": "m1"}))
        with patcher:
            self.assertEqual(GmailApiBackend().send_messages([message]), 1)
        self.assertEqual(fake.sent_raw()["Bcc"], "only@example.com")
        self.assertIsNone(fake.sent_raw()["To"])

    @override_settings(**GMAIL_ON)
    def test_여러_통이면_토큰은_한_번만_받는다(self):
        fake, patcher = _google(TOKEN_OK, _response(200, {}), _response(200, {}))
        messages = [EmailMessage("s", "b", "f@x.com", [f"u{i}@example.com"]) for i in range(2)]
        with patcher:
            self.assertEqual(GmailApiBackend().send_messages(messages), 2)
        self.assertEqual([url for url, _ in fake.calls], [TOKEN_URL, SEND_URL, SEND_URL])

    @override_settings(**GMAIL_ON)
    def test_fail_silently_여도_연결_실패는_조용히_0(self):
        fake, patcher = _google(httpx.ConnectError("x"))
        with patcher, self.assertLogs("apps.accounts.gmail_api", "WARNING") as logs:
            sent = GmailApiBackend(fail_silently=True).send_messages(
                [EmailMessage("s", "b", "f@x.com", ["u@example.com"])]
            )
        self.assertEqual(sent, 0)
        self.assertNotIn(REFRESH, _formatted(logs.records))

    @override_settings(**GMAIL_ON)
    def test_오류_이름에_토큰_응답의_다른_필드는_안_들어간다(self):
        """구글이 error_description 에 무엇을 적든 문구에는 error 만 들어간다."""
        fake, patcher = _google(
            _response(400, {"error": "invalid_grant", "error_description": "Token REFRESH leaked"})
        )
        with patcher, self.assertRaises(GmailSendError) as caught:
            GmailApiBackend().send_messages([EmailMessage("s", "b", "f@x.com", ["u@example.com"])])
        self.assertEqual(str(caught.exception), "Gmail 토큰 교환 실패: 400 invalid_grant")


@override_settings(**GMAIL_ON)
class PurgeNoticeThroughGmailTest(TestCase):
    """파기 안내를 Gmail 백엔드로 보낸다. 로그에 원인은 남고 주소는 안 남아야 한다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="sleepy@example.com", display_name="잠꾸러기")
        User.objects.filter(pk=self.user.pk).update(
            last_seen_on=timezone.localdate() - timedelta(days=400)
        )

    def notice_sent(self) -> bool:
        self.user.refresh_from_db()
        return self.user.purge_notice_sent_at is not None

    def run_failing(self, *responses) -> str:
        fake, patcher = _google(*responses)
        with patcher, self.assertLogs("apps.accounts.purge", "ERROR") as logs:
            self.assertEqual(purge.send_notices(), (0, 1))
        self.assertFalse(self.notice_sent())
        text = _formatted(logs.records)
        for secret in ("sleepy@example.com", SECRET, REFRESH):
            self.assertNotIn(secret, text)
        return text

    def test_토큰이_풀리면_로그에_invalid_grant_가_남는다(self):
        self.assertIn("invalid_grant", self.run_failing(_response(400, {"error": "invalid_grant"})))

    def test_연결_실패는_예외_이름만_남고_예외_문구는_안_남는다(self):
        text = self.run_failing(httpx.ConnectError("tunnel to sleepy@example.com refused"))
        self.assertIn("ConnectError", text)
        self.assertNotIn("tunnel", text)

    def test_보내면_안내_시각이_찍힌다(self):
        fake, patcher = _google(TOKEN_OK, _response(200, {"id": "m1"}))
        with patcher:
            self.assertEqual(purge.send_notices(), (1, 0))
        self.assertTrue(self.notice_sent())
        self.assertEqual(fake.sent_raw()["To"], "sleepy@example.com")

    def test_SMTP_오류는_여전히_종류만_남긴다(self):
        """GmailSendError 가 아닌 OSError 는 문구에 주소가 있을 수 있다."""
        err = OSError("550 mailbox sleepy@example.com unavailable")
        with mock.patch("apps.accounts.purge.send_account_mail", side_effect=err), self.assertLogs(
            "apps.accounts.purge", "ERROR"
        ) as logs:
            purge.send_notices()
        self.assertNotIn("sleepy@example.com", _formatted(logs.records))
        self.assertIn("OSError", _formatted(logs.records))


@override_settings(**GMAIL_ON)
class DailyCleanupRealCheckTokenTest(TestCase):
    """check_token 을 가짜로 바꾸지 않고, 구글만 가짜로 둔 채 daily_cleanup 을 돌린다."""

    def run_cleanup(self):
        return call_command("daily_cleanup", "--apply", stdout=mock.MagicMock())

    def test_토큰이_풀리면_명령이_실패하고_비밀값은_안_나온다(self):
        fake, patcher = _google(_response(400, {"error": "invalid_grant"}))
        with patcher, self.assertRaises(CommandError) as caught:
            self.run_cleanup()
        message = str(caught.exception)
        self.assertIn("invalid_grant", message)
        self.assertNotIn(REFRESH, message)
        self.assertNotIn(SECRET, message)
        self.assertEqual(fake.calls[0][0], TOKEN_URL)

    def test_시간_초과도_CommandError_로_끝난다(self):
        """httpx 예외가 그대로 새면 운영 로그에 원인 대신 traceback 만 남는다."""
        fake, patcher = _google(httpx.ConnectTimeout("slow"))
        with patcher, self.assertRaisesRegex(CommandError, "ConnectTimeout"):
            self.run_cleanup()

    def test_토큰이_살아_있으면_안내할_사람이_없어도_한_번_묻는다(self):
        fake, patcher = _google(TOKEN_OK)
        with patcher:
            self.run_cleanup()
        self.assertEqual([url for url, _ in fake.calls], [TOKEN_URL])

    def test_토큰이_풀려도_기한이_지난_회원은_먼저_지운다(self):
        """메일 계정 문제로 삭제까지 멈추면 안 된다(daily_cleanup 머리 주석)."""
        gone = User.objects.create_user(email="gone@example.com", display_name="떠난")
        User.objects.filter(pk=gone.pk).update(
            last_seen_on=timezone.localdate() - timedelta(days=400),
            purge_notice_sent_at=timezone.now() - timedelta(days=31),
        )
        fake, patcher = _google(_response(400, {"error": "invalid_grant"}))
        with patcher, self.assertRaises(CommandError):
            self.run_cleanup()
        self.assertFalse(User.objects.filter(pk=gone.pk).exists())

    def test_미리_보기는_구글에_안_묻는다(self):
        fake, patcher = _google()
        with patcher:
            call_command("daily_cleanup", stdout=mock.MagicMock())
        self.assertEqual(fake.calls, [])


class BackendChoiceTest(SimpleTestCase):
    """settings.py 를 환경변수만 바꿔 다시 읽어 EMAIL_BACKEND 를 본다."""

    KEYS = (
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
    )
    FULL = {
        "EMAIL_HOST_USER": "sender@gmail.com",
        "EMAIL_HOST_PASSWORD": "app-password",
        "GMAIL_CLIENT_ID": "id",
        "GMAIL_CLIENT_SECRET": "secret",
        "GMAIL_REFRESH_TOKEN": "refresh",
    }

    def backend(self, **values) -> str:
        env = {k: v for k, v in os.environ.items() if k not in self.KEYS}
        env.update({"DJANGO_DEBUG": "1", "DJANGO_SECRET_KEY": "x"})
        env.update(values)
        path = Path(settings.BASE_DIR) / "config" / "settings.py"
        # .env 를 읽지 않게 막는다. 읽으면 이 PC 의 실제 값이 빈자리를 채운다.
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("dotenv.load_dotenv"):
            return runpy.run_path(str(path))["EMAIL_BACKEND"]

    def without(self, *keys) -> dict:
        return {k: v for k, v in self.FULL.items() if k not in keys}

    def test_다_있으면_Gmail_이_SMTP_보다_먼저다(self):
        self.assertEqual(self.backend(**self.FULL), GMAIL)

    def test_Gmail_값이_하나라도_빠지면_SMTP_로_내려간다(self):
        for key in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
            with self.subTest(missing=key):
                self.assertEqual(self.backend(**self.without(key)), SMTP)

    def test_Gmail_값이_빈_문자열이어도_빠진_것으로_본다(self):
        self.assertEqual(self.backend(**{**self.FULL, "GMAIL_REFRESH_TOKEN": ""}), SMTP)

    def test_보내는_주소가_없으면_Gmail_값이_다_있어도_console(self):
        self.assertEqual(self.backend(**self.without("EMAIL_HOST_USER")), CONSOLE)

    def test_Gmail_일부만_있고_앱_비밀번호도_없으면_console(self):
        self.assertEqual(
            self.backend(**self.without("EMAIL_HOST_PASSWORD", "GMAIL_REFRESH_TOKEN")), CONSOLE
        )

    def test_앱_비밀번호_없이_Gmail_만으로_된다(self):
        self.assertEqual(self.backend(**self.without("EMAIL_HOST_PASSWORD")), GMAIL)


class GmailTokenCommandTest(SimpleTestCase):
    """gmail_token 을 처음부터 끝까지. 브라우저 대신 스레드가 루프백 서버를 부른다."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / ".env").write_text(
            "DJANGO_SECRET_KEY=keep-me\nGMAIL_REFRESH_TOKEN=old\n", encoding="utf-8"
        )
        self.replies: list[int] = []
        self.exchange: list[dict] = []

    def _id_token(self, mail: str) -> str:
        claims = base64.urlsafe_b64encode(json.dumps({"email": mail}).encode()).decode().rstrip("=")
        return f"h.{claims}.s"

    def _browser(self, make_queries):
        """webbrowser.open 대역. 허락 화면 주소에서 돌아올 곳과 state 를 읽어 차례로 부른다."""

        def open_(url):
            query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
            redirect = query["redirect_uri"]

            def visit():
                for params in make_queries(query["state"]):
                    try:
                        with urllib.request.urlopen(f"{redirect}?{urlencode(params)}", timeout=5) as r:
                            self.replies.append(r.status)
                    except urllib.error.HTTPError as err:
                        # 받지 않은 요청은 400 이다. urlopen 은 그걸 예외로 던진다.
                        self.replies.append(err.code)

            self.visitor = threading.Thread(target=visit, daemon=True)
            self.visitor.start()
            return True

        return open_

    def _token_reply(self, mail="sender@gmail.com", scope=gmail_token.GMAIL_SEND, refresh=REFRESH):
        def post(url, data, timeout):
            self.exchange.append(data)
            body = {"scope": f"openid {scope}", "id_token": self._id_token(mail)}
            if refresh:
                body["refresh_token"] = refresh
            return _response(200, body)

        return post

    def run_command(self, make_queries, post=None, sender_setting="sender@gmail.com", args=(), **reply):
        out = mock.MagicMock()
        with override_settings(
            PROJECT_ROOT=self.root,
            GMAIL_CLIENT_ID="client-id",
            GMAIL_CLIENT_SECRET=SECRET,
            EMAIL_HOST_USER=sender_setting,
        ), mock.patch.object(gmail_token.webbrowser, "open", self._browser(make_queries)), mock.patch.object(
            gmail_token.httpx, "post", post or self._token_reply(**reply)
        ):
            call_command("gmail_token", *args, stdout=out)
        # 마지막 응답을 기록하기 전에 비교하지 않게 가짜 브라우저가 끝나길 기다린다.
        if getattr(self, "visitor", None):
            self.visitor.join(5)
        return "".join(str(call.args[0]) for call in out.write.call_args_list)

    def env(self) -> str:
        return (self.root / ".env").read_text(encoding="utf-8")

    def test_state_가_틀린_요청은_무시하고_맞는_요청의_코드만_쓴다(self):
        printed = self.run_command(
            lambda state: [
                {"state": "wrong", "code": "evil-code"},
                {"code": "no-state-code"},
                {"state": state},
                {"state": state, "code": "good-code"},
            ]
        )

        self.assertEqual([d["code"] for d in self.exchange], ["good-code"])
        self.assertEqual(self.exchange[0]["client_secret"], SECRET)
        self.assertEqual(self.env(), f"DJANGO_SECRET_KEY=keep-me\nGMAIL_REFRESH_TOKEN={REFRESH}\n")
        # 받지 않은 요청에는 400 을 돌려줘 브라우저가 "받았습니다" 로 속지 않는다.
        self.assertEqual(self.replies, [400, 400, 400, 200])
        for secret in (SECRET, REFRESH, "good-code"):
            self.assertNotIn(secret, printed)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".env"])

    def test_허락_화면이_redirect_uri_와_state_를_실어_보낸다(self):
        seen = {}

        def capture(state):
            seen["state"] = state
            return [{"state": state, "code": "c"}]

        self.run_command(capture)
        self.assertGreaterEqual(len(seen["state"]), 16)
        self.assertTrue(self.exchange[0]["redirect_uri"].startswith("http://127.0.0.1:"))

    def test_구글이_거절하면_env_를_안_건드린다(self):
        with self.assertRaisesRegex(CommandError, "access_denied"):
            self.run_command(lambda state: [{"state": state, "error": "access_denied"}])
        self.assertEqual(self.exchange, [])
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_다른_계정으로_허락하면_env_를_안_건드린다(self):
        with self.assertRaisesRegex(CommandError, "other@gmail.com"):
            self.run_command(lambda state: [{"state": state, "code": "c"}], mail="other@gmail.com")
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_허락한_계정을_못_읽으면_env_를_안_건드린다(self):
        def no_id_token(url, data, timeout):
            return _response(200, {"scope": f"openid {gmail_token.GMAIL_SEND}", "refresh_token": REFRESH})

        with self.assertRaisesRegex(CommandError, "확인하지 못했습니다"):
            self.run_command(lambda state: [{"state": state, "code": "c"}], post=no_id_token)
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_토큰_교환_중_연결이_끊기면_알아보기_쉬운_오류로_끝난다(self):
        def cut(url, data, timeout):
            raise httpx.ConnectError("reset")

        with self.assertRaisesRegex(CommandError, "연결하지 못했습니다"):
            self.run_command(lambda state: [{"state": state, "code": "c"}], post=cut)
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_토큰_응답이_JSON_이_아니면_권한_탓으로_돌리지_않는다(self):
        def page(url, data, timeout):
            return httpx.Response(200, text="<html>", request=httpx.Request("POST", url))

        with self.assertRaisesRegex(CommandError, "읽지 못했습니다"):
            self.run_command(lambda state: [{"state": state, "code": "c"}], post=page)

    def test_보내는_주소를_모르면_허락_화면을_열기_전에_멈춘다(self):
        opened = []
        with self.assertRaisesRegex(CommandError, "--sender"):
            self.run_command(lambda state: opened.append(state) or [], sender_setting="")
        self.assertEqual(opened, [])
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_로컬처럼_EMAIL_HOST_USER_가_비어도_sender_로_계정을_확인한다(self):
        with self.assertRaisesRegex(CommandError, "other@gmail.com"):
            self.run_command(
                lambda state: [{"state": state, "code": "c"}],
                sender_setting="",
                args=("--sender", "sender@gmail.com"),
                mail="other@gmail.com",
            )
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

        self.run_command(
            lambda state: [{"state": state, "code": "c"}],
            sender_setting="",
            args=("--sender", "sender@gmail.com"),
        )
        self.assertIn(f"GMAIL_REFRESH_TOKEN={REFRESH}", self.env())

    def test_계정은_대소문자를_가리지_않는다(self):
        self.run_command(lambda state: [{"state": state, "code": "c"}], mail="Sender@Gmail.com")
        self.assertIn(f"GMAIL_REFRESH_TOKEN={REFRESH}", self.env())

    def test_보내기_권한을_끄고_허락하면_실패한다(self):
        with self.assertRaisesRegex(CommandError, "권한"):
            self.run_command(
                lambda state: [{"state": state, "code": "c"}],
                scope="https://www.googleapis.com/auth/userinfo.email",
            )
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_갱신_토큰이_없으면_실패한다(self):
        with self.assertRaisesRegex(CommandError, "갱신 토큰"):
            self.run_command(lambda state: [{"state": state, "code": "c"}], refresh="")
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    def test_마감이_지나면_서버를_닫고_실패한다(self):
        with mock.patch.object(gmail_token, "WAIT_SECONDS", -1), self.assertRaises(CommandError):
            self.run_command(lambda state: [])
        self.assertIn("GMAIL_REFRESH_TOKEN=old", self.env())

    @override_settings(GMAIL_CLIENT_ID="", GMAIL_CLIENT_SECRET="")
    def test_클라이언트_값이_없으면_서버를_띄우기_전에_멈춘다(self):
        with mock.patch.object(gmail_token, "HTTPServer") as server, self.assertRaises(CommandError):
            call_command("gmail_token", stdout=mock.MagicMock())
        server.assert_not_called()


class WriteEnvTest(SimpleTestCase):
    """write_env 가 .env 를 잃지 않는가."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / ".env"

    def test_파일이_없으면_새로_만든다(self):
        gmail_token.write_env(self.path, "GMAIL_REFRESH_TOKEN", "v")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "GMAIL_REFRESH_TOKEN=v\n")

    def test_바꿔_끼우다_실패하면_원래_env_가_그대로다(self):
        self.path.write_text("DJANGO_SECRET_KEY=keep\nGMAIL_REFRESH_TOKEN=old\n", encoding="utf-8")
        with mock.patch.object(gmail_token.os, "replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                gmail_token.write_env(self.path, "GMAIL_REFRESH_TOKEN", "new")
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "DJANGO_SECRET_KEY=keep\nGMAIL_REFRESH_TOKEN=old\n"
        )

    def test_CRLF_와_한글_주석을_지키고_줄_하나만_바꾼다(self):
        self.path.write_bytes("# 메일 설정\r\nA=1\r\nGMAIL_REFRESH_TOKEN=old\r\n".encode("utf-8"))
        gmail_token.write_env(self.path, "GMAIL_REFRESH_TOKEN", "1//new")
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "# 메일 설정\nA=1\nGMAIL_REFRESH_TOKEN=1//new\n"
        )

    def test_dotenv_가_새_값을_읽는다(self):
        """export 접두어 줄이 남아 있어도 python-dotenv 가 읽는 값은 새 값이어야 한다."""
        from dotenv import dotenv_values

        self.path.write_text("export GMAIL_REFRESH_TOKEN=old\n", encoding="utf-8")
        gmail_token.write_env(self.path, "GMAIL_REFRESH_TOKEN", "new")
        self.assertEqual(dotenv_values(self.path)["GMAIL_REFRESH_TOKEN"], "new")


class ErrorNameTest(SimpleTestCase):
    """로그에 남는 오류 문구에는 이름처럼 생긴 값만 들어간다."""

    def test_설명_글은_주소가_섞일_수_있어_버린다(self):
        from apps.accounts.gmail_api import _error_name

        leaky = _response(400, {"error": {"code": 400, "message": "Invalid To header: victim@example.com"}})
        self.assertEqual(_error_name(leaky), "(이름 없는 오류)")
        proxy = _response(403, {"error": "blocked for victim@example.com"})
        self.assertNotIn("victim", _error_name(proxy))

    def test_구글의_오류_이름은_그대로_남긴다(self):
        from apps.accounts.gmail_api import _error_name

        self.assertEqual(_error_name(_response(400, {"error": "invalid_grant"})), "invalid_grant")
        self.assertEqual(
            _error_name(_response(403, {"error": {"status": "PERMISSION_DENIED", "message": "x"}})),
            "PERMISSION_DENIED",
        )
