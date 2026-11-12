"""오류 알림 처리기가 처리기 잠금을 잡지 않게 바뀐 뒤(ThrottledAdminEmailHandler.handle).

잠금을 뺐으니 세 가지를 본다.
- 메일 한 통이 나가는 동안 같은 프로세스의 다른 오류 응답이 기다리지 않는다.
- 여러 스레드가 동시에 서로 다른 오류를 내도 메일 상한(한 시간 5통, 같은 오류 한 통)이
  지켜지고, 운영 로그의 "[서버 오류]" 덩어리가 섞이지 않고, 예외가 밖으로 새지 않는다.
- 파이썬 3.12+ 처럼 거름망이 바꾼 기록을 돌려주면 그 기록으로 emit 한다.

    LiveServer   다른 종류의 500 과 잘못된 Host(400)가 앞선 메일 발송을 기다리지 않는다
    단위         스레드 48개가 오류 16종을 세 번씩 동시에 낸다
    거름망       3.12 의 Filterer.filter 를 흉내 내 바뀐 기록이 emit 되는지 본다

사보타주: ThrottledAdminEmailHandler.handle 을 logging.Handler.handle 로 바꾸면 LiveServer
두 건(각 3초 대기)과 거름망 세 건이 빨개진다.
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from threading import Barrier
from unittest import mock

from apps.accounts.error_mail import MAX_PER_WINDOW, ThrottledAdminEmailHandler
from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from django.core.exceptions import SuspiciousOperation
from django.http import HttpRequest, HttpResponse
from django.test import LiveServerTestCase, SimpleTestCase, override_settings
from django.urls import path

from config.urls import urlpatterns as real_urlpatterns

ADMINS = [("ops", "ops@example.com")]
SLOW_MAIL_SECONDS = 3.0
# 예외에 담는 메시지. 덩어리 검사가 메시지 꼬리가 붙은 머리 줄도 받는지 보는 데 쓴다.
MESSAGE = "leakmark-" + "message"
# 시행일(error_mail.MESSAGE_FROM 이 생기면 그날)부터는 머리 줄 끝에 " - 오류 메시지" 가 붙는다.
# 여기서 보는 것은 덩어리가 섞이지 않는가라서 그 꼬리는 무엇이든 받는다.
HEADER = re.compile(r"^\[서버 오류\] (\S+) (\S+) (\S*)(?: - .*)?$")


def boom_runtime(request: HttpRequest) -> HttpResponse:
    raise RuntimeError("leakmark-runtime")


def boom_value(request: HttpRequest) -> HttpResponse:
    raise ValueError("leakmark-value")


urlpatterns = [
    *real_urlpatterns,
    path("__boom_runtime__/", boom_runtime),
    path("__boom_value__/", boom_value),
]


class FirstMailIsSlow:
    """mail_admins 대신 쓴다. 첫 통만 느린 Gmail 처럼 오래 걸린다.

    둘째 통부터 바로 돌아오게 해야 "다른 오류의 자기 메일" 이 아니라 "앞 메일을
    기다린 시간" 만 잴 수 있다.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.subjects: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, subject, message, **kwargs) -> None:
        with self._lock:
            first = not self.subjects
            self.subjects.append(subject)
        if first:
            self.started.set()
            time.sleep(SLOW_MAIL_SECONDS)


@override_settings(
    ROOT_URLCONF="config.tests_mail_handler_threads", ADMINS=ADMINS, SECURE_SSL_REDIRECT=False
)
class SlowMailDoesNotHoldOtherResponsesTest(_KeepsCacheTable, LiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        handler = mail_handler()
        reset_counts(handler)
        # 프로세스에 하나뿐인 처리기라, 남긴 셈이 다른 메일 테스트로 넘어가지 않게 끝나면 다시 비운다.
        self.addCleanup(reset_counts, handler)
        self.fake = FirstMailIsSlow()
        patcher = mock.patch("apps.accounts.error_mail.mail_admins", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        stderr = redirect_stderr(io.StringIO())
        stderr.__enter__()
        self.addCleanup(stderr.__exit__, None, None, None)

    def get(self, url_path: str, host: str = "") -> int:
        req = urllib.request.Request(self.live_server_url + url_path)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status
        except urllib.error.HTTPError as err:
            return err.code

    def while_first_mail_is_sending(self, url_path: str, host: str = "") -> tuple[int, float]:
        """첫 500 의 메일이 나가는 중에 다른 요청을 보내 그 응답 시간을 잰다."""
        first: list[int] = []
        worker = threading.Thread(target=lambda: first.append(self.get("/__boom_runtime__/")))
        worker.start()
        try:
            self.assertTrue(self.fake.started.wait(10), "첫 메일 발송이 시작되지 않았다")
            began = time.monotonic()
            code = self.get(url_path, host)
            elapsed = time.monotonic() - began
        finally:
            worker.join(30)
        self.assertEqual(first, [500])
        return code, elapsed

    def test_other_500_does_not_wait_for_slow_mail(self):
        code, elapsed = self.while_first_mail_is_sending("/__boom_value__/")
        self.assertEqual(code, 500)
        self.assertLess(elapsed, 1.5, f"다른 500 이 앞 메일을 {elapsed:.2f}초 기다렸다")
        # 다른 종류이므로 두 통 다 나간다(기다리지 않았다고 빠뜨린 게 아니다).
        self.assertEqual(len(self.fake.subjects), 2, self.fake.subjects)

    def test_bad_host_400_does_not_wait_for_slow_mail(self):
        code, elapsed = self.while_first_mail_is_sending(
            "/__boom_value__/", host="leakmark-host.example"
        )
        self.assertEqual(code, 400)
        self.assertLess(elapsed, 1.5, f"잘못된 Host 400 이 앞 메일을 {elapsed:.2f}초 기다렸다")
        self.assertEqual(len(self.fake.subjects), 1, self.fake.subjects)


def mail_handler() -> ThrottledAdminEmailHandler:
    handlers = [
        h for h in logging.getLogger("django").handlers if isinstance(h, ThrottledAdminEmailHandler)
    ]
    assert handlers, "settings.LOGGING 의 mail_admins 가 ThrottledAdminEmailHandler 가 아니다"
    return handlers[0]


def reset_counts(handler: ThrottledAdminEmailHandler) -> None:
    """셈을 비운다. should_send 가 두 값을 새 객체로 바꿔 끼우므로 부를 때마다 다시 읽는다."""
    handler._last_sent.clear()
    handler._sent_times.clear()


def raise_and_record(exc_type: type[BaseException]) -> logging.LogRecord:
    try:
        raise exc_type(MESSAGE)
    except BaseException:
        exc_info = sys.exc_info()
    record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", None, exc_info)
    record.request = mock.Mock(path="/api/vocab/words/123/", method="GET")
    return record


def error_kinds(count: int) -> list[type[Exception]]:
    """이름이 다른 예외 count 종. 서명(종류@자리)이 서로 다르다."""
    return [type(f"Leakmark{i}Error", (Exception,), {}) for i in range(count)]


@override_settings(ADMINS=ADMINS)
class ConcurrentDifferentErrorsTest(SimpleTestCase):
    KINDS = 16
    REPEAT = 3

    def setUp(self):
        self.handler = ThrottledAdminEmailHandler()
        self.sent: list[str] = []
        self.sent_lock = threading.Lock()

        def fake_mail(subject, message, **kwargs):
            # 보내는 중에 다른 스레드가 끼어들 틈을 넓힌다.
            time.sleep(0.05)
            with self.sent_lock:
                self.sent.append(subject)

        patcher = mock.patch("apps.accounts.error_mail.mail_admins", fake_mail)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fire_together(self, records: list[logging.LogRecord]) -> list[BaseException]:
        gate = Barrier(len(records))
        leaked: list[BaseException] = []

        def run(record):
            gate.wait()
            try:
                self.handler.handle(record)
            except BaseException as exc:  # 처리기 밖으로 나오면 안 된다
                leaked.append(exc)

        threads = [threading.Thread(target=run, args=(r,)) for r in records]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        return leaked

    def records(self) -> list[logging.LogRecord]:
        return [
            raise_and_record(kind) for kind in error_kinds(self.KINDS) for _ in range(self.REPEAT)
        ]

    def assert_blocks_intact(self, text: str, expected: int) -> None:
        """ "[서버 오류]" 덩어리마다 머리 한 줄 + "  File" 줄과 코드 줄의 짝만 있어야 한다."""
        blocks = re.split(r"(?m)^(?=\[서버 오류\] )", text)
        blocks = [b for b in blocks if b]
        self.assertEqual(len(blocks), expected, text[:2000])
        for block in blocks:
            lines = block.rstrip("\n").split("\n")
            match = HEADER.match(lines[0])
            self.assertIsNotNone(match, f"머리 줄이 깨졌다: {lines[0]!r}")
            self.assertRegex(match.group(1), r"^Leakmark\d+Error$")
            self.assertEqual(match.group(2), "GET")
            self.assertEqual(match.group(3), "/api/vocab/words/:id/")
            body = lines[1:]
            self.assertTrue(body, f"호출 경로가 빠졌다: {block!r}")
            self.assertEqual(len(body) % 2, 0, f"호출 경로가 섞였다: {block!r}")
            for i in range(0, len(body), 2):
                self.assertTrue(body[i].startswith('  File "'), f"섞인 줄: {body[i]!r}")
                self.assertTrue(body[i + 1].startswith("    "), f"섞인 줄: {body[i + 1]!r}")

    def assert_caps(self) -> None:
        self.assertEqual(len(self.sent), MAX_PER_WINDOW, self.sent)
        kinds = [s.split()[-3] for s in self.sent]
        self.assertEqual(len(kinds), len(set(kinds)), f"같은 오류가 두 통: {self.sent}")

    def test_caps_hold_and_stderr_blocks_stay_whole(self):
        records = self.records()
        out = io.StringIO()
        with redirect_stderr(out):
            leaked = self.fire_together(records)
        self.assertEqual(leaked, [])
        self.assert_caps()
        self.assert_blocks_intact(out.getvalue(), len(records))

    def test_blocks_stay_whole_on_real_text_stream(self):
        """운영 표준 오류처럼 버퍼가 있는 파일 스트림에서도 덩어리가 섞이지 않는다."""
        records = self.records() * 4
        fd, name = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        self.addCleanup(os.remove, name)
        with open(name, "w", encoding="utf-8", buffering=1) as stream:
            with redirect_stderr(stream):
                leaked = self.fire_together(records)
        self.assertEqual(leaked, [])
        with open(name, encoding="utf-8") as stream:
            self.assert_blocks_intact(stream.read(), len(records))

    def test_failing_mail_from_many_threads_does_not_leak(self):
        def broken_mail(subject, message, **kwargs):
            raise OSError("leakmark-gmail")

        records = self.records()
        out = io.StringIO()
        with mock.patch("apps.accounts.error_mail.mail_admins", broken_mail), redirect_stderr(out):
            leaked = self.fire_together(records)
        self.assertEqual(leaked, [])
        text = out.getvalue()
        # 실패해도 보낸 것으로 센다 - 상한만큼만 두드린다.
        self.assertEqual(text.count("[오류 알림 실패] OSError"), MAX_PER_WINDOW)
        self.assertNotIn("leakmark-gmail", text)
        server_part = re.sub(r"(?m)^\[오류 알림 실패\].*\n", "", text)
        self.assert_blocks_intact(server_part, len(records))


def filter_like_python_312(handler: logging.Handler):
    """파이썬 3.12 의 Filterer.filter. 거름망이 돌려준 기록으로 바꿔 끼운다.

    로컬은 3.11 이라 Filterer.filter 가 True/False 만 돌려준다. 운영(3.13)과 같게 흉내 낸다.
    """

    def filter(record):
        for f in handler.filters:
            result = f.filter(record) if hasattr(f, "filter") else f(record)
            if not result:
                return False
            if isinstance(result, logging.LogRecord):
                record = result
        return record

    return filter


class ReplacingFilterTest(SimpleTestCase):
    def handler_with(self, fn) -> tuple[ThrottledAdminEmailHandler, list[logging.LogRecord]]:
        handler = ThrottledAdminEmailHandler()
        handler.addFilter(fn)
        handler.filter = filter_like_python_312(handler)
        emitted: list[logging.LogRecord] = []
        handler.emit = emitted.append
        return handler, emitted

    def test_emits_the_record_the_filter_returned(self):
        original = raise_and_record(RuntimeError)

        def replace(record):
            new = logging.makeLogRecord(record.__dict__)
            new.msg = "leakmark-replaced"
            return new

        handler, emitted = self.handler_with(replace)
        rv = handler.handle(original)
        self.assertEqual(len(emitted), 1)
        self.assertIsNot(emitted[0], original)
        self.assertEqual(emitted[0].msg, "leakmark-replaced")
        self.assertIs(rv, emitted[0])

    def test_replaced_record_reaches_server_log(self):
        """바뀐 기록의 주소가 "[서버 오류]" 줄에 실린다(emit 까지 실제로 돈다)."""
        original = raise_and_record(RuntimeError)

        def replace(record):
            new = logging.makeLogRecord(record.__dict__)
            new.request = mock.Mock(path="/api/learning/rounds/", method="POST")
            return new

        handler = ThrottledAdminEmailHandler()
        handler.addFilter(replace)
        handler.filter = filter_like_python_312(handler)
        out = io.StringIO()
        with redirect_stderr(out):
            handler.handle(original)
        # 시행일부터는 머리 줄 끝에 " - 오류 메시지" 가 붙는다(HEADER 주석).
        self.assertRegex(
            out.getvalue(), r"(?m)^\[서버 오류\] RuntimeError POST /api/learning/rounds/(?: - .*)?$"
        )

    def test_filter_returning_false_emits_nothing(self):
        handler, emitted = self.handler_with(lambda record: False)
        self.assertFalse(handler.handle(raise_and_record(RuntimeError)))
        self.assertEqual(emitted, [])

    def test_security_record_returned_by_filter_still_skipped(self):
        """거름망이 로거 이름을 django.security.* 로 바꿔 돌려주면 그 이름으로 거른다."""

        def to_security(record):
            new = logging.makeLogRecord(record.__dict__)
            new.name = "django.security.DisallowedHost"
            return new

        handler = ThrottledAdminEmailHandler()
        handler.addFilter(to_security)
        handler.filter = filter_like_python_312(handler)
        out = io.StringIO()
        with redirect_stderr(out):
            handler.handle(raise_and_record(SuspiciousOperation))
        self.assertEqual(out.getvalue(), "")
