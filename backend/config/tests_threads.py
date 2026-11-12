"""한 프로세스 안에서 요청을 여러 스레드가 함께 처리할 때(Procfile --threads 4).

gunicorn gthread 는 미들웨어·URL 해석기·로깅 처리기를 프로세스 하나에 한 벌만
만들고 스레드들이 나눠 쓴다. 작업자(프로세스)마다 한 요청씩 받던 때는 동시에 도는
요청들이 서로 다른 프로세스라 메모리를 함께 쓸 일이 없었다. 여기서는 그것이 섞이지
않는지 본다.

LiveServerTestCase 를 쓰는 이유: 그 서버(ThreadedWSGIServer)가 요청마다 스레드를
띄우고 WSGI 처리기 하나를 함께 쓴다. gthread 와 같은 꼴이다. test client 는
요청을 테스트 스레드에서 하나씩 처리해 이 겹침을 재현하지 못한다.

    healthz        여러 스레드가 동시에 불러도 200 "ok", 다른 주소는 그대로 400
    /me/           토큰이 다른 요청이 동시에 와도 각자 자기 회원 정보만 받는다
    로그인         같은 계정으로 동시에 들어와도 500 없이 토큰 하나
    한 판 답       같은 토큰에 다른 보기 넷을 동시에, 하나만 통과
    오류 알림      같은 오류가 여러 스레드에서 동시에 나도 메일 한 통
"""

from __future__ import annotations

import io
import json
import logging
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from threading import Barrier

from apps.accounts.error_mail import ThrottledAdminEmailHandler
from apps.learning.tests import make_words
from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.test import LiveServerTestCase, SimpleTestCase, override_settings
from django.urls import path
from rest_framework.authtoken.models import Token

from config.urls import urlpatterns as real_urlpatterns

RAILWAY_HOST = "healthcheck.railway.app"


def mark(what: str) -> str:
    """비밀값 대신 넣는 표시 글자. 비밀값처럼 생긴 글자를 이름(password 등) 옆에 적으면
    GitGuardian 이 진짜 자격증명으로 잡는다(#169, #170). 값을 여기서 만들어 소스에 그런 줄을
    두지 않는다(tests_error_mail_dynamic.py 와 같은 방식).
    """
    return f"leakmark-{what}"


LOGIN_MARK = mark("thread-login")


def boom(request: HttpRequest) -> HttpResponse:
    raise RuntimeError("일부러 낸 오류")


# 처리하지 못한 오류를 내는 주소 하나를 더한다. 나머지는 실제 주소 그대로다.
urlpatterns = [*real_urlpatterns, path("__boom__/", boom)]


def mail_handler() -> ThrottledAdminEmailHandler:
    handlers = [
        h for h in logging.getLogger("django").handlers if isinstance(h, ThrottledAdminEmailHandler)
    ]
    assert handlers, "settings.LOGGING 의 mail_admins 가 ThrottledAdminEmailHandler 가 아니다"
    return handlers[0]


class MailHandlerLockTest(SimpleTestCase):
    def test_handle_does_not_wait_for_handler_lock(self):
        """다른 스레드가 처리기 잠금을 쥐고 있어도(Gmail 로 보내는 중) 기록이 지나간다.

        logging.Handler.handle 을 그대로 쓰면 emit 전체가 처리기 잠금 안이라, 메일 한 통이
        나가는 동안(최악 24초) 같은 프로세스의 다른 500 응답이 함께 멈춘다.
        """
        handler = ThrottledAdminEmailHandler()
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "x", None, None)
        handler.acquire()
        worker = threading.Thread(target=handler.handle, args=(record,))
        try:
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive(), "handle 이 처리기 잠금을 기다린다")
        finally:
            handler.release()
            worker.join()


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용(운영과 같은 행 잠금)")
@override_settings(ROOT_URLCONF="config.tests_threads", SECURE_SSL_REDIRECT=False)
class SharedProcessThreadsTest(_KeepsCacheTable, LiveServerTestCase):
    # "localhost" 는 Windows 에서 IPv6 를 먼저 찔러 요청마다 2초씩 늦고, 그 사이 요청들이
    # 흩어져 겹치지 않는다.
    host = "127.0.0.1"

    def call(
        self,
        method: str,
        url_path: str,
        body: dict | None = None,
        token: str = "",
        host: str = "",
    ) -> tuple[int, bytes]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.live_server_url + url_path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Token {token}")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def together(self, calls) -> list[tuple[int, bytes]]:
        """calls 를 같은 순간에 출발시킨다."""
        gate = Barrier(len(calls))

        def run(fn):
            gate.wait()
            return fn()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return list(pool.map(run, calls))

    def assert_no_500(self, results):
        codes = [code for code, _ in results]
        self.assertNotIn(500, codes, f"500 이 섞였다: {codes}")

    def test_healthz_from_many_threads_stays_200_and_others_stay_400(self):
        calls = []
        for i in range(40):
            target = "/healthz" if i % 2 == 0 else "/api/vocab/words/"
            calls.append(lambda t=target: self.call("GET", t, host=RAILWAY_HOST))
        results = self.together(calls)
        for i, (code, body) in enumerate(results):
            if i % 2 == 0:
                self.assertEqual((code, body), (200, b"ok"))
            else:
                self.assertEqual(code, 400, "모르는 Host 가 /healthz 말고도 통과했다")

    def test_me_never_returns_another_users_row(self):
        """스레드끼리 request.user 가 섞이면 남의 이메일이 보인다."""
        users = []
        for i in range(6):
            user = get_user_model().objects.create_user(
                email=f"thread{i}@example.com", password=LOGIN_MARK, display_name=f"스레드{i}"
            )
            users.append((user.email, Token.objects.create(user=user).key))

        plan = users * 6
        results = self.together(
            [lambda t=token: self.call("GET", "/api/accounts/me/", token=t) for _, token in plan]
        )
        for (email, _), (code, body) in zip(plan, results, strict=True):
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)["email"], email)

    def test_same_account_logging_in_at_once_gets_one_token(self):
        user = get_user_model().objects.create_user(
            email="login-race@example.com", password=LOGIN_MARK, display_name="동시로그인"
        )
        body = {"email": user.email, "password": LOGIN_MARK}
        results = self.together(
            [lambda: self.call("POST", "/api/accounts/login/", body) for _ in range(8)]
        )
        self.assertEqual([code for code, _ in results], [200] * 8)
        self.assertEqual(len({json.loads(b)["token"] for _, b in results}), 1)
        self.assertEqual(Token.objects.filter(user=user).count(), 1)

    def test_four_choices_on_one_round_token_only_one_wins(self):
        make_words()
        for _ in range(3):
            code, raw = self.call("POST", "/api/learning/rounds/", {})
            self.assertEqual(code, 201)
            started = json.loads(raw)
            token = started["token"]
            ids = [c["id"] for c in started["question"]["choices"]]
            results = self.together(
                [
                    lambda c=c: self.call(
                        "POST", "/api/learning/rounds/answer/", {"token": token, "choice_id": c}
                    )
                    for c in ids
                ]
            )
            self.assert_no_500(results)
            self.assertEqual(sorted(code for code, _ in results), [200, 400, 400, 400])

    @override_settings(ADMINS=[("ops", "ops@example.com")])
    def test_same_error_from_many_threads_sends_one_mail(self):
        handler = mail_handler()
        handler._last_sent.clear()
        handler._sent_times.clear()
        # 프로세스에 하나뿐인 처리기라, 남긴 셈이 다른 메일 테스트로 넘어가지 않게 끝나면
        # 다시 비운다. should_send 가 두 값을 새 객체로 바꿔 끼우므로 그때 다시 읽는다.
        self.addCleanup(lambda: (handler._last_sent.clear(), handler._sent_times.clear()))
        mail.outbox = []

        # "[서버 오류]" 운영 로그 여덟 줄이 테스트 출력에 섞이지 않게 받아 둔다.
        with redirect_stderr(io.StringIO()):
            results = self.together([lambda: self.call("GET", "/__boom__/") for _ in range(8)])

        self.assertEqual([code for code, _ in results], [500] * 8)
        self.assertEqual(len(mail.outbox), 1, [m.subject for m in mail.outbox])
