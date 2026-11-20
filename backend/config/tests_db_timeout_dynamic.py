"""DB 를 기다리는 시간의 상한을 직접 띄워 보고 깨뜨려 본다(config/wsgi.py, settings.py).

상한은 "웹 서버 프로세스에만" 걸려야 한다. 그래서 웹 서버가 하는 것처럼 config.wsgi 를
불러온 하위 프로세스를 띄워 거기서 잰다. 이 테스트 프로세스(manage.py test)와
`manage.py shell` 은 상한이 없어야 한다 - 있으면 migrate·정리 크론이 10초에 잘린다.

    웹 프로세스        첫 연결, 닫고 다시 연 연결, transaction.atomic 안에서 처음 연 연결,
                       되돌린 트랜잭션 뒤, 다른 스레드의 연결이 모두 10초
    대조군             config.wsgi 없이 같은 하위 프로세스를 띄우면 0 (재는 방법이 맞는지)
    실제 요청          표를 잠근 채 목록을 요청하면 웹 프로세스가 10초 언저리에 500 으로 끝낸다.
                       상한이 없으면 잠금이 풀릴 때까지 멈춰 있다. 10초를 실제로 기다리는
                       테스트는 이것 하나뿐이다
    manage.py 쪽       테스트 프로세스와 `manage.py shell -c` 는 0
    connect_timeout    모든 PostgreSQL 연결에 5 가 libpq 까지 간다. 접속 주소에 값이 있으면
                       그 값이 남고, SQLite 에는 붙지 않는다
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from unittest import skipUnless

from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from apps.vocab.models import Word
from django.conf import settings
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

_POSTGRES_ONLY = skipUnless(connection.vendor == "postgresql", "PostgreSQL 설정이다")

# 하위 프로세스가 불러올 웹 서버 진입점. gunicorn 시작 명령(Procfile)이 부르는 것과 같다.
WEB_ENTRY = "config.wsgi"

# 하위 프로세스의 머리. DB 이름을 이 테스트가 쓰는 테스트 DB 로 돌린 뒤 진입점을 불러온다.
# 오류 알림 메일이 실제로 나가지 않게 ADMINS 를 비운다.
#
# DEBUG 는 운영처럼 끈다. 로컬 .env 처럼 켜 두면 500 화면이 프레임의 지역 변수를 그리며
# QuerySet 을 다시 평가해, 잠긴 표에서는 그 쿼리마다 10초씩 더 기다린다(목록 한 번에 여섯 번,
# 60초). 운영(DEBUG 꺼짐)에서는 처음 걸린 쿼리 하나로 끝난다.
_PRELUDE = """
import importlib, json, sys, threading, time
from django.conf import settings
settings.DATABASES["default"]["NAME"] = sys.argv[1]
settings.DEBUG = False
settings.ALLOWED_HOSTS = ["*"]
settings.SECURE_SSL_REDIRECT = False
settings.ADMINS = []
entry = sys.argv[2]
if entry:
    application = importlib.import_module(entry).application
else:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
from django.db import connection, transaction

def show():
    with connection.cursor() as c:
        c.execute("SHOW statement_timeout")
        return c.fetchone()[0]

def out(**kw):
    print("RESULT " + json.dumps(kw), flush=True)
"""


def run_child(body: str, entry: str | None, timeout: float = 60) -> dict:
    """웹 서버처럼 Django 를 띄운 하위 프로세스에서 body 를 돌리고 out() 결과를 받는다."""
    proc = subprocess.run(
        [sys.executable, "-c", _PRELUDE + body, connection.settings_dict["NAME"], entry or ""],
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        # SENTRY_DSN 을 비운다. DSN 이 있는 셸에서 돌려도 잠금 테스트의 500 이 실제 Sentry 로 가지 않게.
        env={**os.environ, "PYTHONUTF8": "1", "SENTRY_DSN": ""},
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    raise AssertionError(f"하위 프로세스 결과 없음 (rc={proc.returncode})\n{proc.stderr[-3000:]}")


_PROBE_ALL_PATHS = """
r = {"first": show()}
connection.close()
r["reopened"] = show()

connection.close()
with transaction.atomic():
    r["opened_in_atomic"] = show()
r["after_atomic"] = show()

connection.close()
try:
    with transaction.atomic():
        r["opened_in_rolled_back"] = show()
        raise RuntimeError("되돌린다")
except RuntimeError:
    pass
r["after_rollback"] = show()

box = {}
def in_thread():
    box["v"] = show()
    connection.close()
t = threading.Thread(target=in_thread)
t.start(); t.join()
r["other_thread"] = box["v"]
out(**r)
"""


@_POSTGRES_ONLY
class WebProcessStatementTimeoutTest(TestCase):
    """config.wsgi 를 불러온 프로세스의 연결은 어떤 길로 열려도 10초다."""

    def test_every_connection_path_in_web_process_is_capped_at_10s(self):
        result = run_child(_PROBE_ALL_PATHS, WEB_ENTRY)
        # 어느 칸이 빠졌는지 바로 보이게 칸마다 비교한다.
        for path, value in result.items():
            with self.subTest(path=path):
                self.assertEqual(value, "10s")

    def test_control_without_config_wsgi_has_no_cap(self):
        """대조군. 같은 하위 프로세스라도 config.wsgi 를 안 거치면 0 이어야 재는 방법이 맞다."""
        result = run_child('out(first=show())', None)
        self.assertEqual(result["first"], "0")


@_POSTGRES_ONLY
class ManagePyHasNoStatementTimeoutTest(SimpleTestCase):
    """manage.py 로 도는 것(테스트, shell, migrate, 크론)에는 상한이 없다."""

    databases = {"default"}

    def test_test_process_has_no_cap(self):
        with connection.cursor() as c:
            c.execute("SHOW statement_timeout")
            self.assertEqual(c.fetchone()[0], "0")

    def test_manage_py_shell_has_no_cap(self):
        code = (
            "from django.db import connection\n"
            f"connection.settings_dict['NAME'] = {connection.settings_dict['NAME']!r}\n"
            "c = connection.cursor()\n"
            "c.execute('SHOW statement_timeout')\n"
            "print('RESULT', c.fetchone()[0])\n"
        )
        proc = subprocess.run(
            [sys.executable, "manage.py", "shell", "-c", code],
            cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=60,
            env={**os.environ, "SENTRY_DSN": ""},
        )
        self.assertIn("RESULT 0", proc.stdout, proc.stderr[-2000:])


@_POSTGRES_ONLY
class WebRequestGivesUpOnLockedTableTest(_KeepsCacheTable, TransactionTestCase):
    """다른 연결이 표를 쥐고 안 놓아도 웹 요청은 10초 언저리에 끝난다.

    상한이 없으면 요청이 잠금이 풀릴 때까지 스레드를 붙잡는다. 그것을 막는 것이
    이 변경의 목적이라, 상한 값(SHOW)만 보지 않고 한 번은 실제로 끊기는 것을 본다.
    """

    def test_list_request_is_cut_at_10s_with_500(self):
        Word.objects.create(term="lockme", meaning="잠금", category="git", is_reviewed=True)
        body = """
from wsgiref.util import setup_testing_defaults
env = {}
setup_testing_defaults(env)
env["PATH_INFO"] = "/api/vocab/words/"
status = []
started = time.monotonic()
response = application(env, lambda s, h, exc_info=None: status.append(s))
b"".join(response)
response.close()
out(status=status[0], elapsed=time.monotonic() - started)
"""
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute(f"LOCK TABLE {Word._meta.db_table} IN ACCESS EXCLUSIVE MODE")
            started = time.monotonic()
            # 상한이 없으면 여기서 멈춘다. 25초가 지나면 TimeoutExpired 로 실패한다.
            result = run_child(body, WEB_ENTRY, timeout=25)
            waited = time.monotonic() - started

        self.assertTrue(result["status"].startswith("500"), result)
        # 하위 프로세스가 뜨는 시간을 빼고 쿼리를 기다린 시간이 10초 언저리다.
        self.assertGreaterEqual(result["elapsed"], 9.5, result)
        self.assertLess(result["elapsed"], 15, result)
        self.assertLess(waited, 25)


class ConnectTimeoutTest(TestCase):
    """연결을 맺는 데 기다리는 시간(connect_timeout)."""

    @_POSTGRES_ONLY
    def test_current_connection_passes_5_to_libpq(self):
        # 접속 주소(CI 의 DATABASE_URL)에 값이 없으면 5 다. settings 에만 있고 libpq 로
        # 안 가면 소용없으니 실제 연결의 매개변수를 본다.
        with connection.cursor():
            pass
        params = connection.connection.info.get_parameters()
        expected = str(connection.settings_dict["OPTIONS"]["connect_timeout"])
        self.assertEqual(params.get("connect_timeout"), expected)
        if "connect_timeout" not in os.environ.get("DATABASE_URL", ""):
            self.assertEqual(expected, "5")

    def _options_under(self, **env: str) -> dict:
        """주어진 환경변수로 settings 만 읽어 default DB 의 ENGINE 과 OPTIONS 를 받는다."""
        # 지우지 않고 빈 값으로 덮는다. settings 의 load_dotenv 는 이미 있는 변수를 덮어쓰지
        # 않아서, 지우면 로컬 .env 의 DATABASE_URL·USE_SQLITE 가 다시 채워진다.
        clean = dict(os.environ)
        clean.update(
            DJANGO_SETTINGS_MODULE="config.settings",
            DJANGO_DEBUG="1",
            ANTHROPIC_API_KEY="",
            SENTRY_DSN="",
            DATABASE_URL="",
            USE_SQLITE="",
        )
        clean.update(env)
        code = (
            "import json, django\n"
            "from django.conf import settings\n"
            "d = settings.DATABASES['default']\n"
            "print('RESULT', json.dumps({'engine': d['ENGINE'], 'options': d.get('OPTIONS', {})}))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=settings.BASE_DIR,
            capture_output=True, text=True, timeout=60, env=clean,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT "):
                return json.loads(line[len("RESULT "):])
        raise AssertionError(proc.stderr[-2000:])

    def test_database_url_value_wins_over_default(self):
        got = self._options_under(DATABASE_URL="postgres://u@127.0.0.1:5433/x?connect_timeout=2")
        self.assertEqual(str(got["options"]["connect_timeout"]), "2")

    def test_database_url_without_value_gets_5(self):
        got = self._options_under(DATABASE_URL="postgres://u@127.0.0.1:5433/x?sslmode=disable")
        self.assertEqual(got["options"]["connect_timeout"], 5)
        # 다른 옵션을 덮어쓰지 않는다.
        self.assertEqual(got["options"]["sslmode"], "disable")

    def test_postgres_vars_get_5(self):
        got = self._options_under(POSTGRES_DB="x")
        self.assertEqual(got["options"], {"connect_timeout": 5})

    def test_sqlite_gets_nothing(self):
        # sqlite3.connect 는 connect_timeout 을 모른다. 붙으면 연결부터 TypeError 다.
        got = self._options_under(USE_SQLITE="1")
        self.assertEqual(got["engine"], "django.db.backends.sqlite3")
        self.assertNotIn("connect_timeout", got["options"])
