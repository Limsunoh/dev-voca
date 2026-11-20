"""실제 sentry-sdk 로 오류를 만들어, 밖으로 나가는 봉투(envelope)에 비밀이 없는지 본다.

tests_sentry.py 는 scrub 함수만 따로 부른다. 여기서는 config.sentry.init 을 그대로
부르고(옵션을 손으로 베끼지 않는다) 전송 계층만 바꿔 끼운다. 그래서 SDK 가 이벤트에
붙이는 것 - breadcrumb, contexts, extra, 지역 변수 - 이 모두 검사 대상이 된다.

요청은 Django 테스트 클라이언트가 아니라 WSGIHandler 로 넣는다. sentry-sdk 는
WSGIHandler.__call__ 을 감싸 요청 주소·헤더를 이벤트에 싣고 요청마다 scope 를 새로
만든다. 테스트 클라이언트는 그 자리를 거치지 않아 운영과 다른 이벤트가 나온다.

가짜 DSN(.invalid) 을 쓰고 전송 계층을 갈아 끼우므로 네트워크로는 아무것도 안 나간다.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from unittest import mock

import sentry_sdk
from apps.accounts.models import LoginToken, User
from django.core.handlers.wsgi import WSGIHandler
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from sentry_sdk.transport import Transport

from config import sentry as devvoca_sentry

FAKE_DSN = "https://public@o0.ingest.invalid/1"
USER_AGENT = "Mozilla/5.0 (Linux; Android 15)"

# 요청에 싣는 비밀값. 서로 겹치지 않는 영숫자라 봉투 문자열에서 바로 찾을 수 있다.
RELAY_SECRET = "RelaySecretQ7w3"
CLIENT_IP = "203.0.113.77"
COOKIE_TOKEN = "CookieTokZ9k2"
PASSWORD = "PasswdX4m8"
QUERY_CODE = "QueryCodeP5n1"
PATH_TOKEN = "PathTokAb3x9"
LOCAL_SECRET = "LocalVarK2j6"
PROBE_EMAIL = "probe-sentry@example.com"

logger = logging.getLogger("apps.accounts.sentry_probe")


class ProbeError(RuntimeError):
    pass


@csrf_exempt
def boom_view(request, token):
    # 지역 변수에 비밀번호가 담긴 채로 터진다. include_local_variables 가 풀리면 실린다.
    password = request.POST.get("password")  # noqa: F841
    local_secret = LOCAL_SECRET  # noqa: F841
    raise ProbeError("probe failure")


class AuthedBoomView(APIView):
    """로그인한 사용자의 요청에서 터진다. 인증이 토큰을 DB 에서 찾는 질의를 먼저 낸다."""

    def get(self, request):
        assert request.user.is_authenticated
        raise ProbeError("authed probe failure")


@csrf_exempt
def signup_boom_view(request):
    """가입처럼 사용자 행을 만든 뒤 터진다. INSERT 의 값(이메일·비밀번호 해시)이 질의 기록에 남는다."""
    User.objects.create_user(email=PROBE_EMAIL, password=PASSWORD)
    raise ProbeError("signup probe failure")


def log_view(request):
    logger.error("probe error")
    try:
        raise ProbeError("logged failure")
    except ProbeError:
        logger.exception("probe exception")
    return HttpResponse("ok")


urlpatterns = [
    path("api/accounts/email/<str:token>/", boom_view),
    path("api/authed-boom/", AuthedBoomView.as_view()),
    path("api/signup-boom/", signup_boom_view),
    path("api/log-probe/", log_view),
]


class CaptureTransport(Transport):
    """나가려던 봉투를 그대로 모은다."""

    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes: list = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def text(self) -> str:
        return "\n".join(e.serialize().decode("utf-8") for e in self.envelopes)

    def events(self) -> list[dict]:
        return [
            item.payload.json
            for env in self.envelopes
            for item in env.items
            if item.type == "event"
        ]


@contextmanager
def keep_test_connection():
    """WSGIHandler 가 요청 앞뒤로 DB 연결을 닫지 않게 한다(테스트 클라이언트와 같은 처리).

    TestCase 는 트랜잭션 안에서 돈다. close_old_connections 가 그 연결을 닫으면 다음
    질의가 깨진다.
    """
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    try:
        yield
    finally:
        request_started.connect(close_old_connections)
        request_finished.connect(close_old_connections)


@override_settings(
    ROOT_URLCONF=__name__,
    DEBUG=False,
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
    ADMINS=[],
)
class SentryEnvelopeTest(TestCase):
    def setUp(self):
        self.transport = CaptureTransport()
        real_init = sentry_sdk.init

        def init_with_capture(**kwargs):
            return real_init(transport=self.transport, **kwargs)

        # config.sentry.init 이 SENTRY_DSN 을 보고 넘기는 옵션을 그대로 쓴다.
        with mock.patch.dict(os.environ, {"SENTRY_DSN": FAKE_DSN}), mock.patch.object(
            devvoca_sentry.sentry_sdk, "init", side_effect=init_with_capture
        ):
            devvoca_sentry.init()
        self.addCleanup(self.stop_sentry)
        self.assertTrue(sentry_sdk.get_client().is_active())

    @staticmethod
    def stop_sentry():
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)

    def call(self, method: str, url: str, data=None, **headers) -> int:
        """운영처럼 WSGIHandler 로 요청을 넣고 상태 코드를 돌려준다."""
        request = RequestFactory().generic(method, url, **headers) if data is None else (
            RequestFactory().post(url, data=data, **headers)
        )
        status: list[str] = []
        with keep_test_connection():
            response = WSGIHandler()(request.environ, lambda s, h, *a: status.append(s))
            b"".join(response)
            response.close()
        return int(status[0].split()[0])

    def assert_no_secret(self, secrets: list[str]) -> None:
        text = self.transport.text()
        leaked = [s for s in secrets if s in text]
        self.assertEqual(leaked, [], f"Sentry 로 나가는 봉투에 실렸다: {leaked}")

    def test_unhandled_500_leaks_no_request_secret_or_local_variable(self):
        """헤더·쿠키·본문·쿼리·경로 토큰·IP·지역 변수 값이 봉투 어디에도 없다."""
        status = self.call(
            "POST",
            f"/api/accounts/email/{PATH_TOKEN}/?code={QUERY_CODE}",
            data={"password": PASSWORD},
            HTTP_X_NEXT_RELAY=RELAY_SECRET,
            HTTP_X_NEXT_CLIENT_IP=CLIENT_IP,
            HTTP_X_FORWARDED_FOR=CLIENT_IP,
            HTTP_COOKIE=f"devvoca_token={COOKIE_TOKEN}",
            HTTP_USER_AGENT=USER_AGENT,
            REMOTE_ADDR=CLIENT_IP,
        )
        self.assertEqual(status, 500)

        events = self.transport.events()
        self.assertEqual(len(events), 1)
        self.assert_no_secret(
            [RELAY_SECRET, CLIENT_IP, COOKIE_TOKEN, PASSWORD, QUERY_CODE, PATH_TOKEN, LOCAL_SECRET]
        )

        # 오류 종류·메시지·호출 경로, 가린 주소와 User-Agent 는 남는다.
        event = events[0]
        exc = event["exception"]["values"][-1]
        self.assertEqual((exc["type"], exc["value"]), ("ProbeError", "probe failure"))
        frames = exc["stacktrace"]["frames"]
        self.assertTrue(any(f.get("function") == "boom_view" for f in frames))
        self.assertTrue(all("vars" not in f for f in frames))
        self.assertEqual(event["request"]["url"], "http://testserver/api/accounts/email/:id/")
        self.assertEqual(event["request"]["method"], "POST")
        self.assertEqual(event["request"]["headers"], {"User-Agent": USER_AGENT})
        self.assertNotIn("user", event)

    def test_authenticated_500_leaks_no_login_token(self):
        """로그인 토큰이 인증 질의 breadcrumb(db.params)으로 실려 나가지 않는다."""
        user = User.objects.create_user(email=PROBE_EMAIL, password="x" * 12)
        key = LoginToken.objects.create(user=user).key

        status = self.call("GET", "/api/authed-boom/", HTTP_AUTHORIZATION=f"Token {key}")
        self.assertEqual(status, 500)

        events = self.transport.events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["exception"]["values"][-1]["type"], "ProbeError")
        self.assert_no_secret([key, PROBE_EMAIL])

    def test_500_after_insert_leaks_no_email_or_password_hash(self):
        """같은 요청에서 사용자 행을 쓴 뒤 터져도 이메일·비밀번호 해시가 안 나간다."""
        status = self.call("POST", "/api/signup-boom/", data={})
        self.assertEqual(status, 500)

        hashed = User.objects.get(email=PROBE_EMAIL).password
        self.assertEqual(len(self.transport.events()), 1)
        self.assert_no_secret([PROBE_EMAIL, hashed, PASSWORD])

    def test_logger_error_and_exception_go_through_scrub(self):
        """logger.error / logger.exception 이 만든 이벤트도 before_send(scrub) 를 거친다."""
        status = self.call(
            "GET",
            f"/api/log-probe/?code={QUERY_CODE}",
            HTTP_X_NEXT_RELAY=RELAY_SECRET,
            HTTP_X_NEXT_CLIENT_IP=CLIENT_IP,
            HTTP_COOKIE=f"devvoca_token={COOKIE_TOKEN}",
            HTTP_USER_AGENT=USER_AGENT,
        )
        self.assertEqual(status, 200)

        events = self.transport.events()
        self.assertEqual(
            sorted(e["logentry"]["message"] for e in events), ["probe error", "probe exception"]
        )
        for event in events:
            # scrub 을 거쳤다면 요청 헤더는 User-Agent 하나, 주소는 쿼리가 없다.
            self.assertEqual(event["request"]["headers"], {"User-Agent": USER_AGENT})
            self.assertEqual(event["request"]["url"], "http://testserver/api/log-probe/")
            self.assertNotIn("user", event)
        self.assert_no_secret([RELAY_SECRET, CLIENT_IP, COOKIE_TOKEN, QUERY_CODE])


class SentryOffTest(SimpleTestCase):
    def test_init_without_dsn_activates_nothing(self):
        """SENTRY_DSN 이 없거나 공백뿐이면 sentry_sdk.init 을 부르지 않고 클라이언트도 꺼져 있다."""
        for value in (None, "", "   "):
            env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
            if value is not None:
                env["SENTRY_DSN"] = value
            with self.subTest(value=value), mock.patch.dict(
                os.environ, env, clear=True
            ), mock.patch.object(devvoca_sentry.sentry_sdk, "init") as init:
                devvoca_sentry.init()
                init.assert_not_called()
                self.assertFalse(sentry_sdk.get_client().is_active())
