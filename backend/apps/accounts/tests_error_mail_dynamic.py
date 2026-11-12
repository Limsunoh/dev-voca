"""500 오류 알림 메일의 경계와 남용(apps.accounts.error_mail, settings 의 메일 절).

tests_error_mail.py 가 기본 동작(한 통, 같은 오류 묶기, 상한)을 본다. 여기서는
깨지기 쉬운 자리를 본다.
- 설정 연결: 보내는 계정이 없으면 ADMINS 가 비고, mail_admins 가 이 처리기다.
- DEBUG 이거나 ADMINS 가 비면 아무것도 안 나간다.
- Gmail 이 실패하거나 느려도 사용자는 500 을 제대로 받는다.
- 메일 본문에 토큰·쿠키·비밀번호가 실리지 않는다.
- DRF 뷰의 500 도 알리고, 400·401·403·404 는 알리지 않는다.
- 같은 오류가 여러 작업 스레드에서 동시에 나도 한 통이다.
- 주소의 숫자·긴 조각은 인코딩을 돌려도 가려지고, 예외의 메시지·원인·메모는 안 실린다.
- 뷰가 처리해 답한 502·503 과 예외 없는 기록은 알리지 않는다.
- 하루 상한은 실제 로거를 거쳐도 지켜진다.
- 시행일(MESSAGE_FROM, 한국 시간 자정)부터 운영 로그 줄에 오류 메시지가 붙되, 한 줄로
  펴져 가짜 줄을 못 만들고, 원인·메모·묶음의 하위 예외와 요청의 다른 값은 안 실리며,
  메일에는 어느 날이든 메시지가 없다.
"""

from __future__ import annotations

import builtins
import io
import logging
import os
import runpy
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings
from django.core import mail
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.core.mail.backends.base import BaseEmailBackend
from django.http import Http404, HttpResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import path
from rest_framework import exceptions as drf_exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .error_mail import (
    DAY_SECONDS,
    MAX_PER_DAY,
    MAX_PER_WINDOW,
    MESSAGE_FROM,
    MESSAGE_LIMIT,
    ThrottledAdminEmailHandler,
    short_message,
)
from .mail import MailNotConfigured

SETTINGS_FILE = Path(settings.BASE_DIR) / "config" / "settings.py"


def mark(what: str) -> str:
    """새면 안 되는 값 대신 넣는 표시 글자. 메일·로그에 있으면 샌 것이다.

    비밀값처럼 생긴 글자를 이름(token, password 등) 옆에 적으면 GitGuardian 이 진짜
    자격증명으로 잡는다(#169, #170). 값을 여기서 만들어 소스에 그런 줄을 두지 않는다.
    """
    return f"leakmark-{what}"


HEADER_MARK = mark("header")
COOKIE_MARK = mark("cookie")
BODY_MARK = mark("body")
DB_MARK = mark("db")


# ---- 시험용 뷰 -------------------------------------------------------------


def boom(request, n):
    raise RuntimeError("일부러 낸 오류")


def django_403(request):
    raise PermissionDenied


def django_404(request):
    raise Http404


def django_400(request):
    raise BadRequest("잘못된 요청")


def django_suspicious(request):
    raise SuspiciousOperation("수상한 요청")


class DrfBoom(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, n):
        raise KeyError("drf 오류")

    def post(self, request, n):
        # 본문을 실제로 읽은 뒤 터진다. 읽은 값이 보고서에 실리는지 본다.
        _ = request.data
        raise KeyError("drf 오류")


class DrfStatus(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, kind):
        raise {
            "400": drf_exceptions.ValidationError({"x": "틀림"}),
            "403": drf_exceptions.PermissionDenied(),
            "404": drf_exceptions.NotFound(),
            "405": drf_exceptions.MethodNotAllowed("GET"),
        }[kind]


class DrfNeedsLogin(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"ok": True})


class DrfList(APIView):
    """쿼리 문자열을 읽는 평범한 목록 뷰(페이지 번호 등)."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"page": request.query_params.get("page")})


PII_EMAIL = "hong.gildong@example.com"


def boom_str(request, s):
    raise RuntimeError("주소 조각이 든 오류")


def boom_chained(request):
    """원인 예외와 덧붙인 메모에 이메일이 든다."""
    try:
        raise KeyError(PII_EMAIL)
    except KeyError as cause:
        err = ValueError(f"이미 있는 이메일: {PII_EMAIL}")
        err.add_note(f"memo {PII_EMAIL}")
        raise err from cause


class LoudError(Exception):
    """str·repr 둘 다 개인정보를 내뱉는 예외."""

    def __str__(self) -> str:
        return f"str {PII_EMAIL}"

    def __repr__(self) -> str:
        return f"repr {PII_EMAIL}"


def boom_loud(request):
    raise LoudError(PII_EMAIL)


def log_without_exception(request):
    # except 밖에서 exc_info=True 로 남기면 exc_info 가 (None, None, None) 이 된다.
    logging.getLogger("django.request").error("예외 없는 기록", exc_info=True)
    return HttpResponse("ok")


class Drf503(APIView):
    """뷰가 스스로 503 으로 답한다(처리한 실패)."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"detail": "잠시 후"}, status=503)


def boom_echo(request, s):
    """요청 값(주소 조각, 쿼리의 이메일)을 변수로 받아 오류 메시지에 담는다."""
    who = request.GET.get("email", "")
    raise RuntimeError(f"{s} {who}")


urlpatterns = [
    path("boom/<int:n>/", boom),
    path("django-403/", django_403),
    path("django-404/", django_404),
    path("django-400/", django_400),
    path("django-suspicious/", django_suspicious),
    path("drf-boom/<int:n>/", DrfBoom.as_view()),
    path("drf-status/<str:kind>/", DrfStatus.as_view()),
    path("drf-login/", DrfNeedsLogin.as_view()),
    path("drf-list/", DrfList.as_view()),
    path("boom-str/<str:s>/", boom_str),
    path("boom-chained/", boom_chained),
    path("boom-loud/", boom_loud),
    path("log-no-exc/", log_without_exception),
    path("drf-503/", Drf503.as_view()),
    path("boom-echo/<str:s>/", boom_echo),
]


# ---- 공통 -----------------------------------------------------------------


def mail_handler() -> ThrottledAdminEmailHandler:
    handlers = [
        h for h in logging.getLogger("django").handlers if isinstance(h, ThrottledAdminEmailHandler)
    ]
    assert handlers, "settings.LOGGING 의 mail_admins 가 ThrottledAdminEmailHandler 가 아니다"
    return handlers[0]


def reset_counts() -> None:
    """처리기는 프로세스에 하나라 앞 테스트가 센 것을 비운다."""
    handler = mail_handler()
    handler._last_sent.clear()
    handler._sent_times.clear()


PRODUCTION_LIKE = dict(
    ROOT_URLCONF=__name__,
    ADMINS=[("DeVoca", "ops@example.com")],
    SERVER_EMAIL="ops@example.com",
    DEBUG=False,
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
)

GMAIL_ON = dict(
    EMAIL_BACKEND="apps.accounts.gmail_api.GmailApiBackend",
    GMAIL_CLIENT_ID="cid",
    GMAIL_CLIENT_SECRET=mark("gmail-client"),
    GMAIL_REFRESH_TOKEN=mark("gmail-refresh"),
)


class _ErrorMailCase(TestCase):
    def setUp(self):
        reset_counts()
        self.client.raise_request_exception = False


# ---- 설정 연결 --------------------------------------------------------------


class SettingsWiringTest(SimpleTestCase):
    """settings.py 를 환경변수만 바꿔 새로 읽어 본다."""

    BASE_ENV = {
        "DJANGO_SECRET_KEY": "x",
        "DJANGO_ALLOWED_HOSTS": "testserver",
        "SECURE_SSL_REDIRECT": "false",
        "USE_SQLITE": "1",
        "DJANGO_DEBUG": "0",
        "DEFAULT_FROM_EMAIL": "",
    }

    def load(self, **env) -> dict:
        values = {**self.BASE_ENV, **env}
        with mock.patch.dict(os.environ, values):
            if not values.get("DEFAULT_FROM_EMAIL"):
                os.environ.pop("DEFAULT_FROM_EMAIL", None)
            return runpy.run_path(str(SETTINGS_FILE))

    def test_no_sender_account_means_no_admins(self):
        """보내는 계정이 없으면(로컬·CI) 받을 사람도 없다."""
        ns = self.load(EMAIL_HOST_USER="")
        self.assertEqual(ns["ADMINS"], [])

    def test_sender_account_becomes_admin_and_server_email(self):
        ns = self.load(EMAIL_HOST_USER="ops@gmail.com")
        self.assertEqual(ns["ADMINS"], [("DeVoca", "ops@gmail.com")])
        self.assertEqual(ns["SERVER_EMAIL"], "ops@gmail.com")
        self.assertEqual(ns["EMAIL_SUBJECT_PREFIX"], "[DeVoca 오류] ")

    def test_logging_keeps_django_defaults_and_swaps_only_mail_class(self):
        """DEBUG 거름(require_debug_false)과 ERROR 문턱이 그대로 남아 있어야 한다."""
        ns = self.load(EMAIL_HOST_USER="ops@gmail.com")
        handler = ns["LOGGING"]["handlers"]["mail_admins"]
        self.assertEqual(handler["class"], "apps.accounts.error_mail.ThrottledAdminEmailHandler")
        self.assertIn("require_debug_false", handler["filters"])
        self.assertEqual(handler["level"], "ERROR")
        self.assertIn("mail_admins", ns["LOGGING"]["loggers"]["django"]["handlers"])

    def test_deepcopy_does_not_mutate_django_default_logging(self):
        """DEFAULT_LOGGING 을 직접 고치면 Django 의 다른 사용처까지 바뀐다."""
        from django.utils.log import DEFAULT_LOGGING

        self.load(EMAIL_HOST_USER="ops@gmail.com")
        self.assertEqual(
            DEFAULT_LOGGING["handlers"]["mail_admins"]["class"],
            "django.utils.log.AdminEmailHandler",
        )

    def test_live_process_uses_throttled_handler(self):
        """설정이 실제로 적용돼 django 로거에 이 처리기가 붙어 있다."""
        self.assertIsInstance(mail_handler(), ThrottledAdminEmailHandler)


# ---- 보내지 않아야 할 때 ---------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class WhenNotToSendTest(_ErrorMailCase):
    @override_settings(DEBUG=True)
    def test_debug_true_sends_nothing(self):
        """개발 중(DEBUG)에는 화면에 오류가 보이므로 메일을 안 보낸다."""
        self.client.get("/boom/1/")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(DEBUG=True)
    def test_debug_true_does_not_use_up_the_slot(self):
        """DEBUG 에서 거른 오류가 시간 창을 차지해, 끈 뒤 첫 오류가 묻히면 안 된다."""
        self.client.get("/boom/1/")
        with override_settings(DEBUG=False):
            self.client.get("/boom/1/")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(ADMINS=[])
    def test_empty_admins_sends_nothing_and_still_500(self):
        res = self.client.get("/boom/1/")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(len(mail.outbox), 0)

    def test_django_403_404_400_send_nothing(self):
        for url, status in (
            ("/django-403/", 403),
            ("/django-404/", 404),
            ("/django-400/", 400),
            ("/no-such-page/", 404),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status)
        self.assertEqual(len(mail.outbox), 0)

    def test_drf_client_errors_send_nothing(self):
        for kind, status in (("400", 400), ("403", 403), ("404", 404), ("405", 405)):
            with self.subTest(kind=kind):
                self.assertEqual(self.client.get(f"/drf-status/{kind}/").status_code, status)
        self.assertEqual(self.client.get("/drf-login/").status_code, 401)
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_json_body_sends_nothing(self):
        res = self.client.post("/drf-boom/1/", data="{not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_disallowed_host_sends_nothing(self):
        res = self.client.get("/boom/1/", HTTP_HOST="evil.example.com")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ROOT_URLCONF="config.urls")
    def test_login_with_too_many_form_fields_sends_nothing(self):
        """로그인하지 않은 누구나 폼 칸 1001개로 400 을 낼 수 있다. 메일은 안 간다.

        DRF 의 FormParser 가 본문을 QueryDict 로 읽다 TooManyFieldsSent 가 나고,
        Django 는 이를 400 으로 답하면서 django.security.TooManyFieldsSent 로거에
        ERROR 로 남긴다. 처리기는 django.security.* 를 모두 거른다.
        """
        form = "&".join(f"f{i}=1" for i in range(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS + 1))
        res = self.client.post(
            "/api/accounts/login/", data=form, content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_suspicious_operation_400_sends_nothing(self):
        """SuspiciousOperation 계열(400)은 django.security.* ERROR 지만 메일이 안 간다."""
        res = self.client.get("/django-suspicious/")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)


# ---- DRF 와 같은 오류 묶기 --------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class DrfServerErrorTest(_ErrorMailCase):
    def test_drf_500_sends_mail(self):
        res = self.client.get("/drf-boom/1/")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("KeyError", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].subject.startswith("[DeVoca 오류] "))

    def test_drf_same_bug_on_other_ids_is_one_mail(self):
        for n in (1, 2, 99999, 7):
            self.assertEqual(self.client.get(f"/drf-boom/{n}/").status_code, 500)
        self.assertEqual(len(mail.outbox), 1)

    def test_get_and_post_raising_on_different_lines_are_two_mails(self):
        """같은 예외 종류라도 난 자리가 다르면 다른 버그다."""
        self.client.get("/drf-boom/1/")
        self.client.post("/drf-boom/1/", data={}, content_type="application/json")
        self.assertEqual(len(mail.outbox), 2)

    def test_fifty_requests_of_same_bug_are_one_mail(self):
        """같은 버그가 50번 나도 한 통."""
        for n in range(50):
            self.client.get(f"/boom/{n}/")
        self.assertEqual(len(mail.outbox), 1)


# ---- 메일 본문의 비밀값 ---------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class SecretsNotInMailTest(_ErrorMailCase):
    def assert_no_secrets(self, *secrets: str) -> None:
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        text = message.subject + "\n" + message.body
        for alt in message.alternatives:
            text += "\n" + str(alt[0] if isinstance(alt, tuple) else alt.content)
        for secret in secrets:
            self.assertNotIn(secret, text)

    def test_authorization_header_and_cookies_are_not_in_mail(self):
        self.client.cookies["sessionid"] = COOKIE_MARK
        self.client.cookies["csrftoken"] = COOKIE_MARK + "c"
        res = self.client.get("/drf-boom/1/", HTTP_AUTHORIZATION=f"Token {HEADER_MARK}")
        self.assertEqual(res.status_code, 500)
        self.assert_no_secrets(HEADER_MARK, COOKIE_MARK)
        # 오류 메일은 요청 머리를 아예 넣지 않는 짧은 알림이다(가린 자리도 없다).
        self.assertNotIn("HTTP_AUTHORIZATION", mail.outbox[0].body)

    def test_json_password_body_is_not_in_mail(self):
        res = self.client.post(
            "/drf-boom/1/",
            data={"email": "a@example.com", "password": BODY_MARK},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {HEADER_MARK}",
        )
        self.assertEqual(res.status_code, 500)
        self.assert_no_secrets(BODY_MARK, HEADER_MARK)

    def test_form_encoded_password_is_not_in_mail(self):
        """폼 형식으로 보낸 비밀번호도 메일에 안 실린다.

        프론트는 JSON 으로만 보내지만 DRF 는 폼 형식도 받는다(FormParser). 오류 메일은
        요청 본문·머리·회원 정보를 아예 넣지 않는 짧은 알림이라 실릴 자리가 없다.
        """
        res = self.client.post("/drf-boom/1/", data={"password": BODY_MARK})
        self.assertEqual(res.status_code, 500)
        self.assert_no_secrets(BODY_MARK)

    SETTING_MARKS = {
        name: mark(name.lower())
        for name in (
            "GMAIL_CLIENT_SECRET",
            "GMAIL_REFRESH_TOKEN",
            "EMAIL_HOST_PASSWORD",
            "GOOGLE_CLIENT_SECRET",
            "SECRET_KEY",
        )
    }

    @override_settings(**SETTING_MARKS)
    def test_secret_settings_are_not_in_mail(self):
        """비밀 설정값이 메일에 실리지 않는다(짧은 알림이라 설정 절이 아예 없다)."""
        self.client.get("/boom/1/")
        self.assert_no_secrets(*self.SETTING_MARKS.values())

    def test_database_password_is_not_in_mail(self):
        db = {**settings.DATABASES["default"], "PASSWORD": DB_MARK}
        with override_settings(DATABASES={"default": db}):
            self.client.get("/boom/1/")
        self.assert_no_secrets(DB_MARK)


# ---- Gmail 이 실패하거나 느릴 때 ------------------------------------------------------


class FakeClient:
    """httpx.Client 자리에 넣는다. post 가 부를 때마다 action 을 따른다."""

    calls = 0

    def __init__(self, action):
        self.action = action

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        type(self).calls += 1
        return self.action(url)


def _patch_client(action) -> mock._patch:
    FakeClient.calls = 0
    return mock.patch("apps.accounts.gmail_api.httpx.Client", FakeClient(action))


@override_settings(**PRODUCTION_LIKE, **GMAIL_ON)
class GmailFailureTest(_ErrorMailCase):
    def assert_plain_500(self, res) -> None:
        self.assertEqual(res.status_code, 500)

    def test_connect_error_still_500(self):
        def action(url):
            raise httpx.ConnectError("down")

        with _patch_client(action):
            res = self.client.get("/boom/1/")
        self.assert_plain_500(res)

    def test_read_timeout_still_500(self):
        def action(url):
            raise httpx.ReadTimeout("slow")

        with _patch_client(action):
            res = self.client.get("/drf-boom/1/")
        self.assert_plain_500(res)

    def test_token_rejected_still_500(self):
        def action(url):
            return httpx.Response(400, json={"error": "invalid_grant"})

        with _patch_client(action):
            res = self.client.get("/boom/1/")
        self.assert_plain_500(res)

    def test_send_rejected_still_500(self):
        def action(url):
            if "token" in url:
                return httpx.Response(200, json={"access_token": "a"})
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})

        with _patch_client(action):
            res = self.client.get("/boom/1/")
        self.assert_plain_500(res)

    def test_unexpected_backend_error_does_not_break_response(self):
        """httpx 오류가 아닌 예외(백엔드 버그 등)가 나도 사용자는 500 을 받는다."""

        def action(url):
            raise RuntimeError("백엔드 안에서 예상 못 한 오류")

        with _patch_client(action):
            try:
                res = self.client.get("/boom/1/")
            except Exception as exc:  # 응답 대신 예외가 새면 실패
                self.fail(f"오류 메일 실패가 요청 밖으로 샜다: {exc!r}")
        self.assert_plain_500(res)

    def test_slow_gmail_only_delays_the_first_of_same_error(self):
        """Gmail 이 느려도 같은 오류의 두 번째 요청부터는 기다리지 않는다."""

        def action(url):
            time.sleep(0.3)
            raise httpx.ReadTimeout("slow")

        with _patch_client(action):
            self.client.get("/boom/1/")
            first_calls = FakeClient.calls
            for n in range(5):
                self.assertEqual(self.client.get(f"/boom/{n}/").status_code, 500)
        self.assertEqual(first_calls, 1)
        # 시간 대신 호출 수로 본다. 느린 CI 에서도 같은 계약이다.
        self.assertEqual(FakeClient.calls, 1)

    def test_successful_gmail_send_carries_prefix(self):
        sent = []

        def action(url):
            if "token" in url:
                return httpx.Response(200, json={"access_token": "a"})
            sent.append(url)
            return httpx.Response(200, json={"id": "m1"})

        with _patch_client(action):
            res = self.client.get("/boom/1/")
        self.assert_plain_500(res)
        self.assertEqual(len(sent), 1)


# ---- 동시성 ------------------------------------------------------------------


class ConcurrencyTest(SimpleTestCase):
    """gunicorn 작업자 안의 여러 스레드가 같은 처리기를 함께 쓴다.

    스레드 전환을 아주 잦게 바꾸고 여러 판을 돌려, 잠금이 빠지면 "확인한 뒤
    적기" 사이에 끼어든 스레드가 같은 오류를 또 보내게 만든다.
    """

    ROUNDS = 30
    THREADS = 16

    def setUp(self):
        self._interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

    def tearDown(self):
        sys.setswitchinterval(self._interval)

    def race(self, records: list[logging.LogRecord]) -> list[int]:
        """판마다 새 처리기로 records 를 동시에 넣고, 판마다 보낸 수를 돌려준다."""
        counts = []
        for _ in range(self.ROUNDS):
            handler = ThrottledAdminEmailHandler()
            results: list[bool] = []
            gate = threading.Barrier(len(records))

            def worker(rec, handler=handler, results=results, gate=gate):
                gate.wait()
                results.append(handler.should_send(rec, now=100.0))

            threads = [threading.Thread(target=worker, args=(r,)) for r in records]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            counts.append(results.count(True))
        return counts

    def test_same_error_from_many_threads_is_sent_once(self):
        try:
            raise RuntimeError("x")
        except RuntimeError:
            info = sys.exc_info()
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "m", (), info)
        self.assertEqual(set(self.race([record] * self.THREADS)), {1})

    def test_total_cap_holds_under_threads(self):
        # 처리하지 못한 예외만 알리므로 예외를 단다. 종류를 달리해 서로 다른 오류로 만든다.
        records = []
        for i in range(MAX_PER_WINDOW * 2):
            try:
                raise type(f"Err{i}", (Exception,), {})("x")
            except Exception:
                info = sys.exc_info()
            records.append(
                logging.LogRecord("django.request", logging.ERROR, __file__, 1, "m", (), info)
            )
        self.assertEqual(set(self.race(records)), {MAX_PER_WINDOW})


# ---- 주소 가리기의 경계 ---------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class MaskedPathThroughRequestTest(_ErrorMailCase):
    """실제 요청으로 낸 500 의 제목·본문에 주소 조각이 어떻게 실리는지 본다.

    Django 의 request.path 는 퍼센트 인코딩을 푼 값이라, 인코딩으로 숫자를 숨겨도
    풀린 뒤에 가려져야 한다.
    """

    def sent_text(self, url: str) -> str:
        self.assertEqual(self.client.get(url).status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        return mail.outbox[0].subject + "\n" + mail.outbox[0].body

    def test_percent_encoded_digits_are_masked(self):
        text = self.sent_text("/boom-str/%31%32%33%34%35/")
        self.assertIn("/boom-str/:id/", text)
        self.assertNotIn("12345", text)

    def test_long_letter_token_is_masked(self):
        segment = "abcdefghijklmnopqrstuvwxy"  # 25자, 숫자 없음
        text = self.sent_text(f"/boom-str/{segment}/")
        self.assertIn("/boom-str/:id/", text)
        self.assertNotIn(segment, text)

    def test_non_ascii_digits_are_masked(self):
        text = self.sent_text("/boom-str/%D9%A1%D9%A2%D9%A3/")  # 아라비아-인도 숫자 123
        self.assertIn("/boom-str/:id/", text)

    def test_email_with_digit_is_masked(self):
        text = self.sent_text("/boom-str/kim7%40example.com/")
        self.assertNotIn("kim7", text)
        self.assertNotIn("example.com", text)

    def test_query_string_never_appears(self):
        text = self.sent_text(f"/boom-str/x/?email={PII_EMAIL}&page=2&q=hello")
        self.assertNotIn(PII_EMAIL, text)
        self.assertNotIn("hello", text)
        self.assertNotIn("?", text)


# ---- 예외 내용 -------------------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class ExceptionContentNotInMailTest(_ErrorMailCase):
    """예외의 메시지뿐 아니라 원인(__cause__)·메모(add_note)·str/repr 도 안 실린다."""

    def sent_text(self, url: str) -> str:
        self.assertEqual(self.client.get(url).status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        return mail.outbox[0].subject + "\n" + mail.outbox[0].body

    def test_chained_cause_and_note_are_not_in_mail(self):
        text = self.sent_text("/boom-chained/")
        self.assertNotIn(PII_EMAIL, text)
        self.assertNotIn("hong.gildong", text)
        self.assertIn("ValueError", text)
        self.assertNotIn("KeyError", text)

    def test_custom_str_and_repr_are_not_in_mail(self):
        text = self.sent_text("/boom-loud/")
        self.assertNotIn(PII_EMAIL, text)
        self.assertIn("LoudError", text)

    def test_subject_is_kind_method_and_masked_path_only(self):
        self.sent_text("/boom/42/")
        self.assertEqual(mail.outbox[0].subject, "[DeVoca 오류] RuntimeError GET /boom/:id/")


# ---- 처리한 실패와 예외 없는 기록 --------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class HandledFailureSendsNothingTest(_ErrorMailCase):
    def test_drf_view_returning_503_sends_nothing(self):
        self.assertEqual(self.client.get("/drf-503/").status_code, 503)
        self.assertEqual(len(mail.outbox), 0)

    def test_error_log_with_empty_exc_info_sends_nothing(self):
        """except 밖의 logger.error(exc_info=True) 는 (None, None, None) 을 단다."""
        self.assertEqual(self.client.get("/log-no-exc/").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_security_logger_with_real_exception_sends_nothing(self):
        try:
            raise RuntimeError("x")
        except RuntimeError:
            logging.getLogger("django.security.Anything").error("x", exc_info=True)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(**{**PRODUCTION_LIKE, "ROOT_URLCONF": "config.urls"})
class EmailChangeMailFailureTest(_ErrorMailCase):
    """실제 이메일 변경 신청에서 확인 메일이 실패하면 뷰가 502·503 으로 답한다.

    이미 실패한 Gmail 에 오류 메일을 한 번 더 보내 응답을 늦추면 안 된다.
    """

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        from django.core.cache import cache
        from rest_framework.authtoken.models import Token

        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="old@example.com", password=BODY_MARK
        )
        self.token = Token.objects.create(user=self.user)

    def request_change(self, side_effect):
        with mock.patch("apps.accounts.views.send_account_mail", side_effect=side_effect) as m:
            res = self.client.post(
                "/api/accounts/email-change/",
                {"new_email": "new@example.com", "current_password": BODY_MARK},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {self.token.key}",
            )
        self.assertEqual(m.call_count, 1)
        return res

    def test_smtp_failure_502_sends_no_error_mail(self):
        res = self.request_change(OSError("gmail down"))
        self.assertEqual(res.status_code, 502)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(mail_handler()._sent_times, [])

    def test_mail_not_configured_503_sends_no_error_mail(self):
        res = self.request_change(MailNotConfigured("no sender"))
        self.assertEqual(res.status_code, 503)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(mail_handler()._sent_times, [])


# ---- 하루 상한(실제 로거를 거쳐) ----------------------------------------------------------


@override_settings(**PRODUCTION_LIKE)
class DailyCapThroughLoggerTest(_ErrorMailCase):
    """DB 장애가 하루 내내 이어져 서로 다른 오류가 계속 나도 하루 30통에서 멈춘다.

    시계를 바꿔 한 시간 상한(5통)에는 안 걸리게 13분 남짓마다 새 오류를 낸다.
    """

    STEP = 800  # 초. 한 시간 창 안에 많아야 5개가 든다.

    def log_new_error(self, i: int) -> None:
        try:
            raise type(f"DayErr{i}", (Exception,), {})("x")
        except Exception:
            logging.getLogger("django.request").error(
                "Internal Server Error", exc_info=True, extra={"status_code": 500}
            )

    def test_daily_cap_stops_at_max_and_reopens_next_day(self):
        clock = {"now": 0.0}
        with mock.patch(
            "apps.accounts.error_mail.time.monotonic", side_effect=lambda: clock["now"]
        ):
            for i in range(MAX_PER_DAY + 10):
                clock["now"] = i * self.STEP
                self.log_new_error(i)
            self.assertLess(clock["now"], DAY_SECONDS)
            self.assertEqual(len(mail.outbox), MAX_PER_DAY)

            # 첫 메일에서 하루가 지나면 다시 한 통이 나간다.
            clock["now"] = DAY_SECONDS + 1
            self.log_new_error(999)
        self.assertEqual(len(mail.outbox), MAX_PER_DAY + 1)


# ---- 운영 로그(표준 오류)에 요청 값이 실리지 않는다 ----------------------------------


class ExplodingBackend(BaseEmailBackend):
    """fail_silently 와 무관하게 터지는 메일 백엔드. 부른 횟수를 센다."""

    calls = 0

    def send_messages(self, email_messages) -> int:
        type(self).calls += 1
        raise RuntimeError("메일 백엔드 안에서 터짐")


PII_SEGMENT = "kim.cheolsu@example.org"
PII_QUERY_EMAIL = "lee.younghee@example.net"
QUERY_MARK = mark("query")
RAW_NUMBER = "8675309"


@override_settings(**PRODUCTION_LIKE)
class StderrCarriesNoValuesTest(_ErrorMailCase):
    """표준 오류 한 줄과 호출 경로에는 종류·방식·가린 주소·코드 줄만 남는다.

    소스 줄에 글자로 박힌 문자열은 코드라 실려도 된다. 여기서 넣는 값은 모두 요청으로
    들어와 변수로 흐른다(boom_echo).

    처리방침 v3 시행일(MESSAGE_FROM) 전의 모습이다. 시행일부터는 오류 메시지가 그 줄에
    붙어 boom_echo 가 메시지에 담은 값이 실린다(tests_error_mail.py 가 본다). 날짜를
    고정하지 않으면 이 테스트들이 시행일 아침에 저절로 빨개진다.
    """

    def setUp(self):
        super().setUp()
        before = mock.patch("apps.accounts.error_mail.MESSAGE_FROM", date.max)
        before.start()
        self.addCleanup(before.stop)

    VALUES = (
        PII_SEGMENT,
        PII_QUERY_EMAIL,
        QUERY_MARK,
        HEADER_MARK,
        COOKIE_MARK,
        BODY_MARK,
        PII_EMAIL,
        RAW_NUMBER,
    )

    def run_and_capture(self, fn) -> str:
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            fn()
        return err.getvalue()

    def assert_no_values(self, log: str) -> None:
        for value in self.VALUES:
            self.assertNotIn(value, log)

    def echo_post(self):
        self.client.cookies["sessionid"] = COOKIE_MARK
        res = self.client.post(
            f"/boom-echo/{PII_SEGMENT}/?email={PII_QUERY_EMAIL}&token={QUERY_MARK}",
            data={"email": PII_EMAIL, "password": BODY_MARK},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {HEADER_MARK}",
        )
        self.assertEqual(res.status_code, 500)

    def test_query_body_header_cookie_and_message_not_in_stderr(self):
        log = self.run_and_capture(self.echo_post)
        self.assertIn("[서버 오류] RuntimeError POST /boom-echo/:id/", log)
        self.assertIn("tests_error_mail_dynamic.py", log)
        self.assert_no_values(log)

    def test_made_up_method_is_hidden_in_stderr(self):
        log = self.run_and_capture(
            lambda: self.client.generic("KIM-CHEOLSU", f"/boom-echo/{RAW_NUMBER}/")
        )
        self.assertIn("[서버 오류] RuntimeError 기타 /boom-echo/:id/", log)
        self.assertNotIn("KIM-CHEOLSU", log)
        self.assert_no_values(log)

    def test_chained_cause_note_and_loud_str_not_in_stderr(self):
        def go():
            self.client.get("/boom-chained/")
            self.client.get("/boom-loud/")

        log = self.run_and_capture(go)
        self.assertEqual(log.count("[서버 오류]"), 2)
        self.assert_no_values(log)

    def test_newline_in_path_cannot_forge_a_log_line(self):
        log = self.run_and_capture(lambda: self.client.get("/boom-echo/a%0A[서버 오류] 가짜/"))
        self.assertEqual(log.count("[서버 오류]"), 1)


@override_settings(**PRODUCTION_LIKE, EMAIL_BACKEND=f"{__name__}.ExplodingBackend")
class EmitFailureTest(StderrCarriesNoValuesTest):
    """메일 백엔드가 터져도 응답은 500 이고, 메일은 한 번만 부르고, 값은 로그에 안 샌다.

    처리기 안 예외가 밖으로 새면 Django 가 그것을 새 500 으로 다시 기록해 메일을 또
    부른다. 로깅의 handleError 는 기본으로 표준 오류에 예외 전체와 기록의 인자(가리지
    않은 주소)를 찍으므로, 감싸기만 하고 끝나면 값이 그 길로 샌다.
    """

    def setUp(self):
        super().setUp()
        ExplodingBackend.calls = 0

    def test_backend_error_still_500_and_called_once(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            for n in range(3):
                self.assertEqual(self.client.get(f"/boom/{n}/").status_code, 500)
        self.assertEqual(ExplodingBackend.calls, 1)

    def test_backend_error_leaks_no_values_to_stderr(self):
        log = self.run_and_capture(self.echo_post)
        self.assertEqual(ExplodingBackend.calls, 1)
        self.assertIn("[서버 오류] RuntimeError POST /boom-echo/:id/", log)
        # 알림이 실패한 것도 흔적이 남는다. 이 줄이 없으면 운영에서 알림이 안 나가도 모른다.
        self.assertIn("[오류 알림 실패] RuntimeError", log)
        self.assert_no_values(log)


@override_settings(**PRODUCTION_LIKE, **GMAIL_ON)
class GmailRuntimeErrorCallsOnceTest(_ErrorMailCase):
    def test_gmail_client_runtime_error_is_one_call_and_500(self):
        """Gmail 백엔드가 못 잡는 예외(RuntimeError)여도 Gmail 은 한 번만 불린다."""

        def action(url):
            raise RuntimeError("예상 못 한 오류")

        with _patch_client(action), mock.patch("sys.stderr", new_callable=io.StringIO):
            res = self.client.get("/boom/1/")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(FakeClient.calls, 1)


# ---- 시행일(MESSAGE_FROM)부터 운영 로그에 붙는 오류 메시지 ---------------------------------
#
# 날짜 문을 지울 때(error_mail.py 의 ponytail 주석) MessageEffectiveDateKstTest 와
# MailNeverCarriesMessageTest 의 시행일 전날 경우도 같이 지운다. 나머지는 "메시지가 붙은
# 뒤" 의 모습이라 그대로 둔다.

MESSAGE_MARK = mark("message")
CAUSE_MARK = mark("cause")
NOTE_MARK = mark("note")
SUB_MARK = mark("sub-exception")


def messages_on():
    return mock.patch("apps.accounts.error_mail.MESSAGE_FROM", date.min)


def on_day(day: date):
    return mock.patch("apps.accounts.error_mail.timezone.localdate", return_value=day)


def boom_message(request, n):
    # 값은 변수로 흐른다. 호출 경로의 소스 줄에는 이름(MESSAGE_MARK)만 찍힌다.
    raise RuntimeError(MESSAGE_MARK)


def boom_chained_marks(request):
    try:
        raise KeyError(CAUSE_MARK)
    except KeyError as cause:
        err = ValueError(MESSAGE_MARK)
        err.add_note(NOTE_MARK)
        raise err from cause


def boom_group(request):
    # ExceptionGroup 은 3.11 내장인데 ruff 는 target-version 이 없어 미정의로 읽는다.
    raise builtins.ExceptionGroup(MESSAGE_MARK, [ValueError(SUB_MARK)])


class BrokenStrError(Exception):
    def __str__(self) -> str:
        raise RuntimeError(MESSAGE_MARK)


def boom_broken_str(request):
    raise BrokenStrError()


def boom_blank(request):
    raise RuntimeError(" \n\t ")


urlpatterns += [
    path("boom-message/<int:n>/", boom_message),
    path("boom-chained-marks/", boom_chained_marks),
    path("boom-group/", boom_group),
    path("boom-broken-str/", boom_broken_str),
    path("boom-blank/", boom_blank),
]


def server_lines(log: str) -> list[str]:
    return [line for line in log.splitlines() if line.startswith("[서버 오류]")]


def exc_record(exc: BaseException) -> logging.LogRecord:
    try:
        raise exc
    except BaseException:
        info = sys.exc_info()
    return logging.LogRecord(
        "django.request", logging.ERROR, __file__, 1, "Internal Server Error: %s", ("/x",), info
    )


class MessageEffectiveDateKstTest(SimpleTestCase):
    """시행일 경계는 한국 시간 자정이다. timezone.now 를 UTC 시각으로 고정해 본다.

    localdate 를 통째로 바꾸면 TIME_ZONE 이 UTC 로 바뀌거나 비교가 UTC 날짜로 바뀌어도
    모른다. 여기서는 실제 변환(Asia/Seoul)을 거친다.
    """

    def message_at(self, moment: datetime) -> str:
        with mock.patch("django.utils.timezone.now", return_value=moment.astimezone(UTC)):
            return short_message(exc_record(RuntimeError("m")))

    def test_off_one_second_before_kst_midnight_and_on_from_midnight(self):
        midnight = datetime.combine(MESSAGE_FROM, dtime(0), tzinfo=ZoneInfo("Asia/Seoul"))
        # UTC 로는 전날 15시다. UTC 날짜로 비교하면 9시간 늦게 켜진다.
        self.assertEqual(self.message_at(midnight - timedelta(seconds=1)), "")
        self.assertEqual(self.message_at(midnight), "m")
        self.assertEqual(self.message_at(midnight + timedelta(hours=9)), "m")
        self.assertEqual(self.message_at(midnight + timedelta(days=400)), "m")


class ShortMessageAbuseTest(SimpleTestCase):
    """메시지를 한 줄로 펴고 자르는 것의 경계. 시행일 뒤로 고정한다."""

    def setUp(self):
        patcher = messages_on()
        patcher.start()
        self.addCleanup(patcher.stop)

    def short(self, exc: BaseException) -> str:
        return short_message(exc_record(exc))

    def test_unicode_line_breaks_and_invisible_marks_are_folded(self):
        # U+2028·U+2029·NEL 은 줄바꿈으로 읽는 로그 화면이 있다. 폭 없는 문자·BOM·방향
        # 바꾸기 문자는 눈에 안 보이게 글자를 끼워 넣거나 뒤집는다.
        raw = "a\u2028b\u2029c\x85d\x0be\x0cf\u200bg\ufeffh\u00a0i\u202ej\u2066k"
        self.assertEqual(self.short(RuntimeError(raw)), "a b c d e f g h i j k")

    def test_unpaired_surrogates_are_folded(self):
        self.assertEqual(self.short(RuntimeError("a\ud800b\udfffc")), "a b c")

    def test_huge_message_is_cut_quickly(self):
        started = time.monotonic()
        text = self.short(RuntimeError("가" * 5_000_000))
        self.assertEqual(len(text), MESSAGE_LIMIT)
        self.assertTrue(text.endswith("…"))
        self.assertLess(time.monotonic() - started, 2)

    def test_exception_group_does_not_carry_member_messages(self):
        text = self.short(builtins.ExceptionGroup(MESSAGE_MARK, [ValueError(SUB_MARK)]))
        self.assertIn(MESSAGE_MARK, text)
        self.assertNotIn(SUB_MARK, text)

    def test_cause_and_notes_are_not_carried(self):
        try:
            try:
                raise KeyError(CAUSE_MARK)
            except KeyError as cause:
                err = ValueError(MESSAGE_MARK)
                err.add_note(NOTE_MARK)
                raise err from cause
        except ValueError as caught:
            text = self.short(caught)
        self.assertEqual(text, MESSAGE_MARK)

    def test_non_str_from_dunder_str_is_unreadable_not_a_crash(self):
        class NonStr(Exception):
            def __str__(self):
                return 5

        self.assertEqual(self.short(NonStr()), "(메시지를 읽지 못함)")

    def test_str_subclass_cannot_skip_folding(self):
        # __str__ 이 str 을 상속한 값을 돌려주고 자르기를 바꿔도, 펴기는 그 결과에 걸린다.
        class Sneaky(str):
            def __getitem__(self, key):
                return "x\n[서버 오류] 가짜"

        class SneakyError(Exception):
            def __str__(self):
                return Sneaky("hi")

        self.assertNotIn("\n", self.short(SneakyError()))

    def test_blank_message_is_empty(self):
        self.assertEqual(self.short(RuntimeError(" \n\t\u2028 ")), "")


@override_settings(**PRODUCTION_LIKE)
class MessageInLogNotElsewhereTest(StderrCarriesNoValuesTest):
    """시행일 뒤: 운영 로그 줄에는 메시지만 더 붙고, 요청의 다른 값과 메일에는 없다.

    StderrCarriesNoValuesTest 의 시험이 상속돼 시행일 뒤로 한 번 더 돈다. boom_echo 는
    주소 조각과 쿼리의 이메일을 메시지에 담으므로, 그 둘을 보는 시험만 여기서 덮어 쓴다.
    """

    VALUES = (QUERY_MARK, HEADER_MARK, COOKIE_MARK, BODY_MARK, PII_EMAIL, RAW_NUMBER)

    def setUp(self):
        super().setUp()
        # 부모 setUp 이 MESSAGE_FROM 을 date.max 로 둔 위에 다시 덮는다.
        patcher = messages_on()
        patcher.start()
        self.addCleanup(patcher.stop)

    def mail_text(self) -> str:
        return "\n".join(m.subject + "\n" + m.body for m in mail.outbox)

    def test_query_body_header_cookie_and_message_not_in_stderr(self):
        # 시행일 뒤에는 boom_echo 가 메시지에 담은 두 값만 실리고, 메일에는 없다.
        log = self.run_and_capture(self.echo_post)
        self.assertEqual(
            server_lines(log),
            [f"[서버 오류] RuntimeError POST /boom-echo/:id/ - {PII_SEGMENT} {PII_QUERY_EMAIL}"],
        )
        self.assert_no_values(log)
        self.assertNotIn(PII_SEGMENT, self.mail_text())
        self.assertNotIn(PII_QUERY_EMAIL, self.mail_text())

    def test_made_up_method_is_hidden_in_stderr(self):
        # 주소 조각(숫자)은 주소에서는 가려지고, boom_echo 가 담은 메시지로만 실린다.
        log = self.run_and_capture(
            lambda: self.client.generic("KIM-CHEOLSU", f"/boom-echo/{RAW_NUMBER}/")
        )
        self.assertEqual(
            server_lines(log), [f"[서버 오류] RuntimeError 기타 /boom-echo/:id/ - {RAW_NUMBER}"]
        )
        self.assertNotIn("KIM-CHEOLSU", log)

    def test_chained_cause_note_and_loud_str_not_in_stderr(self):
        # 메시지(str)는 실리지만 원인 예외(KeyError)·메모·repr 은 안 실린다.
        def go():
            self.client.get("/boom-chained/")
            self.client.get("/boom-loud/")

        log = self.run_and_capture(go)
        self.assertEqual(
            server_lines(log),
            [
                f"[서버 오류] ValueError GET /boom-chained/ - 이미 있는 이메일: {PII_EMAIL}",
                f"[서버 오류] LoudError GET /boom-loud/ - str {PII_EMAIL}",
            ],
        )
        self.assertEqual(log.count(PII_EMAIL), 2)
        self.assertNotIn("memo", log)
        self.assertNotIn("repr", log)
        self.assertNotIn("KeyError", log)

    def test_newline_in_path_cannot_forge_a_log_line(self):
        log = self.run_and_capture(lambda: self.client.get("/boom-echo/a%0A[서버 오류] 가짜/"))
        self.assertEqual(
            server_lines(log), ["[서버 오류] RuntimeError GET /boom-echo/:id/ - a [서버 오류] 가짜"]
        )

    def test_message_is_the_only_new_value_in_the_log(self):
        def go():
            self.client.cookies["sessionid"] = COOKIE_MARK
            self.client.post(
                f"/boom-message/{RAW_NUMBER}/?token={QUERY_MARK}",
                data={"password": BODY_MARK},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {HEADER_MARK}",
            )

        log = self.run_and_capture(go)
        self.assertEqual(
            server_lines(log),
            [f"[서버 오류] RuntimeError POST /boom-message/:id/ - {MESSAGE_MARK}"],
        )
        self.assert_no_values(log)
        self.assertEqual(len(mail.outbox), 1)
        for value in (MESSAGE_MARK, *self.VALUES):
            self.assertNotIn(value, self.mail_text())

    def test_chained_cause_note_and_group_members_not_in_stderr(self):
        def go():
            self.client.get("/boom-chained-marks/")
            self.client.get("/boom-group/")

        log = self.run_and_capture(go)
        lines = server_lines(log)
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0], f"[서버 오류] ValueError GET /boom-chained-marks/ - {MESSAGE_MARK}"
        )
        for value in (CAUSE_MARK, NOTE_MARK, SUB_MARK):
            self.assertNotIn(value, log)
            self.assertNotIn(value, self.mail_text())

    def test_request_value_cannot_forge_a_line_through_the_message(self):
        # 쿼리의 email 이 메시지로 들어온다. \n·\r·U+2028·ESC 로 가짜 줄을 만들어 본다.
        query = "%0A[서버 오류] f1%0D[서버 오류] f2%E2%80%A8[서버 오류] f3%1B[2J"
        log = self.run_and_capture(lambda: self.client.get(f"/boom-echo/a/?email={query}"))
        lines = server_lines(log)
        self.assertEqual(len(lines), 1)
        # 가짜 줄은 진짜 줄 안의 글자로만 남는다.
        self.assertEqual(lines[0].count("[서버 오류]"), 4)
        for bad in ("\r", "\u2028", "\x1b"):
            self.assertNotIn(bad, log)

    def test_throttled_repeats_still_log_their_own_message(self):
        def go():
            for word in ("first", "second", "third"):
                self.client.get(f"/boom-echo/{word}/")

        log = self.run_and_capture(go)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            [line.rsplit(" - ", 1)[1] for line in server_lines(log)], ["first", "second", "third"]
        )

    @override_settings(ADMINS=[])
    def test_no_admins_still_logs_message(self):
        log = self.run_and_capture(lambda: self.client.get("/boom-message/1/"))
        self.assertEqual(
            server_lines(log), [f"[서버 오류] RuntimeError GET /boom-message/:id/ - {MESSAGE_MARK}"]
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_broken_str_still_logs_the_line_and_sends_mail(self):
        log = self.run_and_capture(lambda: self.client.get("/boom-broken-str/"))
        self.assertEqual(
            server_lines(log),
            ["[서버 오류] BrokenStrError GET /boom-broken-str/ - (메시지를 읽지 못함)"],
        )
        self.assertNotIn("[오류 알림 실패]", log)
        self.assertNotIn(MESSAGE_MARK, log)
        self.assertEqual(len(mail.outbox), 1)

    def test_blank_message_adds_no_dash(self):
        log = self.run_and_capture(lambda: self.client.get("/boom-blank/"))
        self.assertEqual(server_lines(log), ["[서버 오류] RuntimeError GET /boom-blank/"])

    def test_surrogate_in_message_does_not_break_a_strict_utf8_stderr(self):
        # 운영의 표준 오류는 UTF-8 이다. 짝 없는 대리 문자가 그대로 가면 쓰기가 터져
        # "[서버 오류]" 줄 대신 "[오류 알림 실패]" 만 남는다.
        raw = io.BytesIO()
        strict = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", write_through=True)
        with mock.patch("sys.stderr", strict):
            mail_handler().emit(exc_record(RuntimeError("a\ud800b")))
        log = raw.getvalue().decode("utf-8")
        self.assertNotIn("[오류 알림 실패]", log)
        # 요청 없는 기록이라 주소가 비어 빈칸이 둘이다.
        self.assertEqual(server_lines(log), ["[서버 오류] RuntimeError 기타  - a b"])


@override_settings(**PRODUCTION_LIKE)
class MailNeverCarriesMessageTest(_ErrorMailCase):
    """알림 메일에는 시행일 전날·당일·다음 날 모두 메시지가 없다. 로그는 당일부터 붙는다."""

    def test_mail_has_no_message_on_any_day(self):
        cases = (
            (MESSAGE_FROM - timedelta(days=1), False),
            (MESSAGE_FROM, True),
            (MESSAGE_FROM + timedelta(days=1), True),
        )
        for day, logged in cases:
            with self.subTest(day=day):
                reset_counts()
                mail.outbox.clear()
                with on_day(day), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    res = self.client.get("/boom-message/3/")
                self.assertEqual(res.status_code, 500)
                self.assertEqual(len(mail.outbox), 1)
                sent = mail.outbox[0]
                self.assertNotIn(MESSAGE_MARK, sent.subject + sent.body)
                self.assertEqual(sent.subject, "[DeVoca 오류] RuntimeError GET /boom-message/:id/")
                self.assertEqual(MESSAGE_MARK in err.getvalue(), logged)


@override_settings(**PRODUCTION_LIKE, EMAIL_BACKEND=f"{__name__}.ExplodingBackend")
class EmitFailureAfterEffectiveTest(_ErrorMailCase):
    """시행일 뒤에 메일 백엔드가 터져도 실패 표시는 종류와 파일:줄 한 줄뿐이다."""

    def test_failure_line_is_one_line_without_any_message(self):
        ExplodingBackend.calls = 0
        with messages_on(), mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(self.client.get("/boom-message/1/").status_code, 500)
        log = err.getvalue()
        self.assertEqual(ExplodingBackend.calls, 1)
        self.assertEqual(
            server_lines(log), [f"[서버 오류] RuntimeError GET /boom-message/:id/ - {MESSAGE_MARK}"]
        )
        failures = [line for line in log.splitlines() if line.startswith("[오류 알림 실패]")]
        self.assertEqual(len(failures), 1)
        self.assertRegex(failures[0], r"^\[오류 알림 실패\] RuntimeError \S+\.py:\d+$")
        self.assertNotIn("메일 백엔드 안에서 터짐", log)
        self.assertEqual(log.count(MESSAGE_MARK), 1)
