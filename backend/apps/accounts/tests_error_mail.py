"""500 오류 알림 메일(apps.accounts.error_mail).

지켜야 할 것.
- 운영에서 처리하지 못한 예외(500)가 나면 ADMINS 로 짧은 알림이 한 통 간다.
- 같은 오류는 한 시간에 한 통. 모두 합쳐 한 시간 5통, 하루 30통. DB 장애처럼 모든
  요청이 실패해도 Gmail 하루 발송량을 오류 메일이 다 쓰지 않는다.
- 같은 오류인지는 예외 종류와 "우리 코드의 마지막 자리" 로 가른다. 라이브러리 안
  같은 줄에서 났어도 우리 코드 자리가 다르면 다른 오류다.
- 메일에는 회원 정보, 요청 본문·머리, 오류 메시지, 주소의 숫자가 안 실린다.
- 처리한 실패(502 처럼 뷰가 답한 것)와 django.security.*(400)는 알리지 않는다.
- 운영 로그의 "[서버 오류]" 줄에는 처리방침 v3 시행일(MESSAGE_FROM)부터 오류 메시지가
  한 줄로, 300자까지 붙는다. 그 전에는 안 붙는다.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from datetime import date, timedelta
from unittest import mock

from django.core import mail
from django.http import HttpResponse, JsonResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import path

from .error_mail import (
    DAY_SECONDS,
    MAX_PER_DAY,
    MAX_PER_WINDOW,
    MESSAGE_FROM,
    MESSAGE_LIMIT,
    WINDOW_SECONDS,
    ThrottledAdminEmailHandler,
    code_place,
    masked_path,
    request_method,
    short_message,
    signature,
)


# 시행일 문을 테스트마다 정해 둔다. 안 정하면 오늘 날짜를 따라가서, 시행일 전에 쓴
# "메시지가 안 실린다" 테스트가 시행일 아침에 저절로 빨개진다.
def messages_off():
    return mock.patch("apps.accounts.error_mail.MESSAGE_FROM", date.max)


def messages_on():
    return mock.patch("apps.accounts.error_mail.MESSAGE_FROM", date.min)


# 요청 머리에 싣는 값. 메일에 있으면 샌 것이다. 비밀값처럼 생긴 글자를 쓰면
# GitGuardian 이 진짜 자격증명으로 잡는다.
HEADER_MARK = "leakmark-header"


def boom(request, n):
    # 실제 코드처럼 값은 변수로 들어온다. 호출 경로에는 소스 줄이 찍히므로, 값이 소스에
    # 글자로 박혀 있으면 "값이 안 실린다" 를 확인할 수 없다.
    who = request.GET.get("email", "a@example.com")
    detail = "비밀" + " 메시지 " + who
    raise RuntimeError(detail)


def boom_other(request):
    raise ValueError("다른 오류")


def handled_502(request):
    # 메일 발송이 실패했을 때 accounts.views 가 하는 것처럼, 예외 없이 502 로 답한다.
    return JsonResponse({"detail": "메일을 보내지 못했습니다."}, status=502)


def json_key_a(request):
    return HttpResponse(json.loads("")["a"])


def json_key_b(request):
    return HttpResponse(json.loads("")["b"])


def fine(request):
    return HttpResponse("ok")


urlpatterns = [
    path("boom/<int:n>/", boom),
    path("boom-other/", boom_other),
    path("handled-502/", handled_502),
    path("json-a/", json_key_a),
    path("json-b/", json_key_b),
    path("fine/", fine),
]


def record_with_exc(exc: BaseException, name: str = "django.request") -> logging.LogRecord:
    try:
        raise exc
    except BaseException:
        info = sys.exc_info()
    return logging.LogRecord(
        name, logging.ERROR, __file__, 1, "Internal Server Error: %s", ("/x",), info
    )


def record_plain(name: str, msg: str) -> logging.LogRecord:
    return logging.LogRecord(name, logging.ERROR, __file__, 1, msg, (), None)


class SignatureTest(SimpleTestCase):
    def test_same_place_same_signature_even_if_message_differs(self):
        def raise_at_same_line(message: str):
            try:
                raise RuntimeError(message)
            except RuntimeError:
                return sys.exc_info()

        a = logging.LogRecord(
            "django.request", logging.ERROR, __file__, 1, "x", (), raise_at_same_line("1번")
        )
        b = logging.LogRecord(
            "django.request", logging.ERROR, __file__, 1, "y", (), raise_at_same_line("2번")
        )
        self.assertEqual(signature(a), signature(b))

    def test_different_exception_type_differs(self):
        self.assertNotEqual(
            signature(record_with_exc(RuntimeError("a"))),
            signature(record_with_exc(ValueError("a"))),
        )

    def test_library_line_from_different_our_lines_differs(self):
        # 둘 다 json 라이브러리 안의 같은 줄에서 터지지만, 부른 우리 코드 줄이 다르다.
        def call_a():
            try:
                json.loads("")
            except ValueError:
                return sys.exc_info()

        def call_b():
            try:
                json.loads("")
            except ValueError:
                return sys.exc_info()

        a = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", (), call_a())
        b = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", (), call_b())
        self.assertNotEqual(signature(a), signature(b))
        self.assertIn("apps/accounts/tests_error_mail.py:", code_place(a))


class MaskedPathTest(SimpleTestCase):
    def path_of(self, p: str) -> str:
        rec = record_plain("django.request", "x")
        rec.request = type("R", (), {"path": p})()
        return masked_path(rec)

    def test_numbers_uuids_and_long_tokens_are_masked(self):
        self.assertEqual(self.path_of("/api/vocab/words/123/"), "/api/vocab/words/:id/")
        self.assertEqual(
            self.path_of("/api/accounts/photo/123e4567-e89b-12d3-a456-426614174000/"),
            "/api/accounts/photo/:id/",
        )
        self.assertEqual(self.path_of("/confirm/abcdefghijklmnopqrstuvwxyzABCD/"), "/confirm/:id/")

    def test_plain_words_stay(self):
        self.assertEqual(self.path_of("/api/learning/daily/"), "/api/learning/daily/")

    def test_email_korean_name_and_short_token_are_masked(self):
        # 지금 이런 값을 주소로 받는 경로는 없다. 생겨도 새지 않게 "남길 것만 고른다".
        self.assertEqual(self.path_of("/x/a@example.com/"), "/x/:id/")
        self.assertEqual(self.path_of("/x/홍길동/"), "/x/:id/")
        self.assertEqual(self.path_of("/x/MQ/"), "/x/:id/")


class RequestMethodTest(SimpleTestCase):
    def method_of(self, m: str) -> str:
        rec = record_plain("django.request", "x")
        rec.request = type("R", (), {"method": m})()
        return request_method(rec)

    def test_known_methods_stay_and_others_are_hidden(self):
        self.assertEqual(self.method_of("GET"), "GET")
        self.assertEqual(self.method_of("post"), "POST")
        self.assertEqual(self.method_of("a@example.com"), "기타")


class ShouldSendTest(SimpleTestCase):
    def setUp(self):
        self.handler = ThrottledAdminEmailHandler()

    def test_same_error_once_per_window(self):
        rec = record_with_exc(RuntimeError("x"))
        self.assertTrue(self.handler.should_send(rec, now=0))
        self.assertFalse(self.handler.should_send(rec, now=10))
        self.assertFalse(self.handler.should_send(rec, now=WINDOW_SECONDS - 1))
        self.assertTrue(self.handler.should_send(rec, now=WINDOW_SECONDS + 1))

    def errors(self, count: int) -> list[logging.LogRecord]:
        # 종류가 다른 예외를 만든다. 같은 줄에서 나도 종류가 다르면 다른 오류다.
        return [record_with_exc(type(f"Err{i}", (Exception,), {})("x")) for i in range(count)]

    def test_hourly_cap(self):
        sent = [
            self.handler.should_send(r, now=i)
            for i, r in enumerate(self.errors(MAX_PER_WINDOW + 3))
        ]
        self.assertEqual(sum(sent), MAX_PER_WINDOW)

    def test_daily_cap(self):
        sent = 0
        for i, rec in enumerate(self.errors(MAX_PER_DAY + 10)):
            # 한 시간 상한에 안 걸리게 시간 창마다 하나씩 보낸다.
            sent += self.handler.should_send(rec, now=i * (WINDOW_SECONDS / MAX_PER_WINDOW + 1))
        self.assertEqual(sent, MAX_PER_DAY)
        self.assertTrue(
            self.handler.should_send(record_with_exc(KeyError("새 날")), now=DAY_SECONDS * 3)
        )

    def test_security_loggers_are_skipped(self):
        for name in ("django.security.DisallowedHost", "django.security.TooManyFieldsSent"):
            self.assertFalse(
                self.handler.should_send(record_with_exc(RuntimeError("x"), name=name), now=0)
            )

    def test_record_without_exception_is_skipped(self):
        self.assertFalse(
            self.handler.should_send(record_plain("django.request", "Bad Gateway: %s"), now=0)
        )


def mail_handler() -> ThrottledAdminEmailHandler:
    handlers = [
        h for h in logging.getLogger("django").handlers if isinstance(h, ThrottledAdminEmailHandler)
    ]
    assert handlers, "settings.LOGGING 의 mail_admins 가 ThrottledAdminEmailHandler 가 아니다"
    return handlers[0]


@override_settings(
    ROOT_URLCONF=__name__,
    ADMINS=[("DeVoca", "ops@example.com")],
    DEBUG=False,
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
)
class ServerErrorMailTest(TestCase):
    def setUp(self):
        # 로그 처리기는 프로세스에 하나라 앞 테스트가 센 것이 남아 있다.
        handler = mail_handler()
        handler._last_sent.clear()
        handler._sent_times.clear()
        self.client.raise_request_exception = False

    def test_500_sends_one_short_mail_to_admins(self):
        # 시행일 뒤로 둔다. 운영 로그에 메시지가 실리는 때에도 메일에는 안 실려야 한다.
        with messages_on():
            res = self.client.get(
                "/boom/77/?email=a@example.com", HTTP_AUTHORIZATION=f"Token {HEADER_MARK}"
            )
        self.assertEqual(res.status_code, 500)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["ops@example.com"])
        self.assertTrue(sent.subject.startswith("[DeVoca 오류] RuntimeError GET /boom/:id/"))
        self.assertIn("apps/accounts/tests_error_mail.py:", sent.body)
        # 회원·요청 정보와 오류 메시지는 안 실린다.
        for leaked in ("a@example.com", "비밀 메시지", HEADER_MARK, "77", "email="):
            self.assertNotIn(leaked, sent.subject + sent.body)

    def capture_two_errors(self) -> str:
        # 메일이 걸러지는 두 번째 요청까지 운영 로그(표준 오류)에 남는다.
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.client.get("/boom/5/?email=a@example.com")
            self.client.get("/boom/6/?email=a@example.com")
        self.assertEqual(len(mail.outbox), 1)
        return err.getvalue()

    def test_server_log_has_no_message_before_effective_date(self):
        with messages_off():
            log = self.capture_two_errors()
        lines = [line for line in log.splitlines() if line.startswith("[서버 오류]")]
        self.assertEqual(lines, ["[서버 오류] RuntimeError GET /boom/:id/"] * 2)
        self.assertIn("tests_error_mail.py", log)
        self.assertNotIn("비밀 메시지", log)
        self.assertNotIn("a@example.com", log)
        # 가리지 않은 주소도 없다(나중에 누가 request.path 를 그대로 쓰면 여기서 잡힌다).
        self.assertNotIn("/boom/5/", log)
        self.assertNotIn("/boom/6/", log)

    def test_server_log_has_message_from_effective_date(self):
        with messages_on():
            log = self.capture_two_errors()
        lines = [line for line in log.splitlines() if line.startswith("[서버 오류]")]
        self.assertEqual(
            lines, ["[서버 오류] RuntimeError GET /boom/:id/ - 비밀 메시지 a@example.com"] * 2
        )
        # 메시지가 붙어도 주소는 여전히 가린다. 쿼리 문자열도 안 실린다.
        self.assertNotIn("/boom/5/", log)
        self.assertNotIn("email=", log)

    def test_same_error_again_sends_nothing(self):
        self.client.get("/boom/1/")
        self.client.get("/boom/2/")
        self.client.get("/boom/3/")
        self.assertEqual(len(mail.outbox), 1)

    def test_different_error_sends_another(self):
        self.client.get("/boom/1/")
        self.client.get("/boom-other/")
        self.assertEqual(len(mail.outbox), 2)

    def test_same_library_line_from_two_views_sends_two(self):
        self.client.get("/json-a/")
        self.client.get("/json-b/")
        self.assertEqual(len(mail.outbox), 2)

    def test_handled_502_sends_nothing(self):
        self.assertEqual(self.client.get("/handled-502/").status_code, 502)
        self.assertEqual(len(mail.outbox), 0)

    def test_normal_request_sends_nothing(self):
        self.assertEqual(self.client.get("/fine/").status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_404_sends_nothing(self):
        self.assertEqual(self.client.get("/no-such-page/").status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ADMINS=[])
    def test_no_admins_sends_nothing_and_counts_nothing(self):
        self.assertEqual(self.client.get("/boom/1/").status_code, 500)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(mail_handler()._sent_times, [])


class ShortMessageTest(SimpleTestCase):
    """운영 로그 한 줄에 붙는 메시지. 시행일 문, 한 줄, 길이 상한."""

    def at(self, day: date):
        return mock.patch("apps.accounts.error_mail.timezone.localdate", return_value=day)

    def test_off_the_day_before_and_on_from_the_day(self):
        record = record_with_exc(RuntimeError("이미 있는 이메일"))
        with self.at(MESSAGE_FROM - timedelta(days=1)):
            self.assertEqual(short_message(record), "")
        with self.at(MESSAGE_FROM):
            self.assertEqual(short_message(record), "이미 있는 이메일")

    def test_newlines_are_folded_so_a_line_cannot_be_forged(self):
        record = record_with_exc(ValueError("첫 줄\n[서버 오류] 가짜\r\n\t끝"))
        with messages_on():
            self.assertEqual(short_message(record), "첫 줄 [서버 오류] 가짜 끝")

    def test_control_characters_become_spaces(self):
        # 터미널 색 바꾸기(ESC)와 글자 방향 뒤집기(U+202E)가 로그 화면에 그대로 닿지 않는다.
        record = record_with_exc(ValueError("a\x1b[31mb\u202ec\x00d\u2028e"))
        with messages_on():
            self.assertEqual(short_message(record), "a [31mb c d e")

    def test_long_message_is_cut_at_the_limit(self):
        record = record_with_exc(ValueError("가" * (MESSAGE_LIMIT * 3)))
        with messages_on():
            text = short_message(record)
        self.assertEqual(len(text), MESSAGE_LIMIT)
        self.assertTrue(text.endswith("…"))

    def test_cut_is_marked_even_if_folding_makes_it_short(self):
        # 빈칸이 많은 긴 메시지는 펴고 나면 300자보다 짧다. 뒤가 버려졌으면 그래도 "…".
        record = record_with_exc(RuntimeError("a" + " " * (MESSAGE_LIMIT * 5) + "tail"))
        with messages_on():
            self.assertEqual(short_message(record), "a…")

    def test_message_at_the_limit_is_kept_whole(self):
        record = record_with_exc(ValueError("가" * MESSAGE_LIMIT))
        with messages_on():
            self.assertEqual(short_message(record), "가" * MESSAGE_LIMIT)

    def test_broken_str_does_not_break_the_line(self):
        class BrokenStr(Exception):
            def __str__(self) -> str:
                raise RuntimeError("str 이 터진다")

        with messages_on():
            self.assertEqual(short_message(record_with_exc(BrokenStr())), "(메시지를 읽지 못함)")

    def test_record_without_exception_has_no_message(self):
        with messages_on():
            self.assertEqual(short_message(record_plain("django.request", "x")), "")
