"""정기 정리(daily_cleanup)가 지켜야 할 것.

되돌릴 수 없이 계정을 지우는 명령이라, 잘못 지우는 길을 막는지를 본다.
PurgeTestBase 는 시계를 setUp 에서 고정한다. 자정 근처를 정확히 짚어야 하고, 실제 시계로
돌리면 자정에 빨개지는 테스트가 된다.

Django 테스트 러너는 메일 백엔드를 locmem 으로 바꾸므로 그대로 두면 명령이
"발송 계정 없음" 으로 멈춘다. 그래서 _really_sends 를 양쪽 이름 다 패치한다.
purge 가 그 이름을 import 해 가서 mail 쪽만 고치면 안 먹는다.
"""

from __future__ import annotations

import hashlib
import smtplib
import socket
import ssl
import threading
import unittest
from datetime import datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core import signing
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections, models
from django.db.models.signals import pre_delete
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts import purge
from apps.accounts.authentication import _mark_seen
from apps.accounts.models import LoginToken
from apps.accounts.throttles import EmailRateThrottle, sweep_expired_counters
from apps.learning import review, session
from apps.learning.models import (
    DailyScore,
    DailyStudy,
    QuizAnswer,
    QuizSession,
    ReviewState,
    RoundStep,
    StudyLength,
)
from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from apps.learning.tests_review import a_round, seed_words
from apps.vocab.models import Word

User = get_user_model()

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=KST)
ME_URL = "/api/accounts/me/"
LOGIN_URL = "/api/accounts/login/"
CACHE_TABLE = "throttle_cache"
WRITE_VERBS = ("INSERT", "UPDATE", "DELETE")

SMTP_SENDER = "apps.accounts.purge.send_account_mail"


def writes_in(captured) -> list[str]:
    """잡힌 쿼리 중 표를 바꾸는 것만."""
    return [
        query["sql"]
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith(WRITE_VERBS)
    ]


def add_counter(key: str, expires: datetime) -> None:
    """시도 횟수 행을 직접 넣는다. 만료 시각을 초 단위로 짚기 위해서다."""
    with connection.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO "{CACHE_TABLE}" (cache_key, value, expires) VALUES (%s, %s, %s)',
            [key, "x", expires],
        )


def counter_keys() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT cache_key FROM "{CACHE_TABLE}"')
        return {row[0] for row in cursor.fetchall()}


def aged_step(round_id: str, age_seconds: int, now: datetime) -> None:
    RoundStep.objects.create(round_id=round_id, step=0)
    RoundStep.objects.filter(round_id=round_id).update(
        created_at=now - timedelta(seconds=age_seconds)
    )


class PurgeTestBase(TestCase):
    """고정 시계, 발송 가능 상태, 회원 만들기."""

    mail_works = True

    def setUp(self):
        cache.clear()
        self.clock = NOW
        clock = mock.patch("django.utils.timezone.now", side_effect=lambda: self.clock)
        clock.start()
        self.addCleanup(clock.stop)

        if self.mail_works:
            self.purge_sends = self._patch("apps.accounts.purge._really_sends", True)
            self.mail_sends = self._patch("apps.accounts.mail._really_sends", True)

    def _patch(self, target: str, value):
        patcher = mock.patch(target, return_value=value)
        started = patcher.start()
        self.addCleanup(patcher.stop)
        return started

    def today(self):
        return self.clock.astimezone(KST).date()

    def member(self, name, seen_days_ago=0, notice_days_ago=None, **extra):
        """seen_days_ago 일 전에 마지막으로 쓴 회원. 안내 기록은 선택."""
        user = User.objects.create_user(
            email=f"{name}@example.com", display_name=name, **extra
        )
        notice = None
        if notice_days_ago is not None:
            notice = self.clock - timedelta(days=notice_days_ago)
        User.objects.filter(pk=user.pk).update(
            last_seen_on=self.today() - timedelta(days=seen_days_ago),
            purge_notice_sent_at=notice,
        )
        user.refresh_from_db()
        return user

    def run_cleanup(self, *args) -> str:
        out = StringIO()
        call_command("daily_cleanup", *args, stdout=out)
        return out.getvalue()

    def apply(self) -> str:
        return self.run_cleanup("--apply")

    def recipients(self) -> list[str]:
        return [message.to[0] for message in django_mail.outbox]

    def exists(self, user) -> bool:
        return User.objects.filter(pk=user.pk).exists()

    def noticed(self, user) -> bool:
        user.refresh_from_db()
        return user.purge_notice_sent_at is not None

    def visit(self, user):
        token = LoginToken.objects.create(user=user)
        return self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {token.key}")


class PreviewTest(PurgeTestBase):
    """--apply 가 없으면 아무것도 안 바뀐다."""

    def _everything_due(self):
        self.gone = self.member("gone", seen_days_ago=500, notice_days_ago=40)
        self.stale = self.member("stale", seen_days_ago=400)
        aged_step("free-old", session.TOKEN_MAX_AGE + 60, self.clock)
        add_counter("old", self.clock - timedelta(hours=1))

    def test_preview_writes_to_no_table_and_sends_no_mail(self):
        """삭제·안내·진행 표시·시도 횟수 대상이 다 있어도 쓰기 쿼리가 0 이다."""
        self._everything_due()

        with CaptureQueriesContext(connection) as captured:
            output = self.run_cleanup()

        self.assertEqual(writes_in(captured), [])
        self.assertEqual(django_mail.outbox, [])
        self.assertTrue(self.exists(self.gone))
        self.assertFalse(self.noticed(self.stale))
        self.assertEqual(RoundStep.objects.count(), 1)
        self.assertEqual(counter_keys(), {"old"})
        self.assertIn("삭제 1명", output)
        self.assertIn("안내 메일 1명", output)
        self.assertIn("진행 표시 1행", output)
        self.assertIn("시도 횟수 1행", output)

    def test_preview_prints_no_email(self):
        """표준 출력은 호스팅 로그로 나간다."""
        self._everything_due()
        self.assertNotIn("@", self.run_cleanup())

    def test_preview_runs_without_a_mail_account(self):
        """미리 보기는 발송 계정이 없어도 끝까지 돈다."""
        self._everything_due()
        self.purge_sends.return_value = False
        self.mail_sends.return_value = False

        self.assertIn("안내 메일 1명", self.run_cleanup())


class NoticeTest(PurgeTestBase):
    """335일 지난 회원에게 안내가 한 번 간다."""

    def test_335_days_is_the_exact_boundary(self):
        """334일은 안 가고 335일부터 간다."""
        before = self.member("d334", seen_days_ago=334)
        edge = self.member("d335", seen_days_ago=335)
        after = self.member("d336", seen_days_ago=336)

        self.apply()

        self.assertCountEqual(self.recipients(), [edge.email, after.email])
        self.assertFalse(self.noticed(before))
        self.assertTrue(self.noticed(edge))
        self.assertTrue(self.noticed(after))

    def test_a_fresh_member_is_left_alone(self):
        self.member("fresh")
        self.apply()
        self.assertEqual(django_mail.outbox, [])

    def test_no_second_mail_on_following_days(self):
        """다음 날, 그다음 날 돌려도 다시 안 간다. 같은 날 두 번도 마찬가지다."""
        user = self.member("once", seen_days_ago=340)

        self.apply()
        self.apply()
        for _ in range(29):
            self.clock += timedelta(days=1)
            self.apply()

        self.assertEqual(self.recipients(), [user.email])

    def test_stamp_is_the_moment_of_sending(self):
        user = self.member("stamp", seen_days_ago=340)
        self.apply()
        user.refresh_from_db()
        self.assertEqual(user.purge_notice_sent_at, self.clock)

    def test_mail_says_when_and_how_to_keep_the_account(self):
        """받은 사람이 무엇을 언제까지 해야 하는지 알 수 있어야 한다."""
        self.member("words", seen_days_ago=340)
        self.apply()
        message = django_mail.outbox[0]
        self.assertIn("30일", message.subject)
        self.assertIn("30일", message.body)
        self.assertIn("로그인", message.body)


class DeleteTest(PurgeTestBase):
    """안내 뒤 30일이 지나고 이용이 없어야만 지운다."""

    def test_never_noticed_member_is_never_deleted(self):
        """안내가 안 나간 회원은 몇 년이 지나도 지우지 않고 안내부터 한다."""
        user = self.member("ancient", seen_days_ago=5000)

        self.apply()

        self.assertTrue(self.exists(user))
        self.assertEqual(self.recipients(), [user.email])

    def test_thirty_days_is_the_exact_boundary(self):
        """안내 뒤 정확히 30일이면 지우고, 1초 모자라면 안 지운다."""
        edge = self.member("edge", seen_days_ago=400, notice_days_ago=30)
        short = self.member("short", seen_days_ago=400)
        User.objects.filter(pk=short.pk).update(
            purge_notice_sent_at=self.clock - timedelta(days=30) + timedelta(seconds=1)
        )

        self.apply()

        self.assertFalse(self.exists(edge))
        self.assertTrue(self.exists(short))

    def test_old_notice_does_not_delete_someone_seen_recently(self):
        """안내 기록이 남아 있어도 최근에 쓴 사람은 안 지운다."""
        user = self.member("back", seen_days_ago=3, notice_days_ago=90)
        self.apply()
        self.assertTrue(self.exists(user))

    def test_full_timeline(self):
        """D일 안내, D+29일 생존, D+30일 삭제. 메일은 내내 한 통이다."""
        user = self.member("timeline", seen_days_ago=335)

        self.apply()
        self.assertEqual(len(django_mail.outbox), 1)

        self.clock += timedelta(days=29)
        self.apply()
        self.assertTrue(self.exists(user))

        self.clock += timedelta(days=1)
        self.apply()
        self.assertFalse(self.exists(user))
        self.assertEqual(len(django_mail.outbox), 1)

    def test_notice_and_delete_never_happen_in_one_run(self):
        user = self.member("samerun", seen_days_ago=900)
        self.apply()
        self.assertTrue(self.exists(user))
        self.assertTrue(self.noticed(user))


class ExcludedAccountsTest(PurgeTestBase):
    """관리자·검수자·정지 계정은 안내도 삭제도 없다."""

    CASES = {
        "staff": {"is_staff": True},
        "super": {"is_superuser": True},
        "both": {"is_staff": True, "is_superuser": True},
        "banned": {"is_active": False},
    }

    def test_no_notice(self):
        users = [self.member(n, seen_days_ago=900, **f) for n, f in self.CASES.items()]

        self.apply()

        self.assertEqual(django_mail.outbox, [])
        for user in users:
            self.assertFalse(self.noticed(user), user.email)

    def test_no_delete_even_with_an_expired_notice(self):
        users = [
            self.member(n, seen_days_ago=900, notice_days_ago=60, **f)
            for n, f in self.CASES.items()
        ]

        self.apply()

        for user in users:
            self.assertTrue(self.exists(user), user.email)

    def test_preview_does_not_count_them(self):
        for name, flags in self.CASES.items():
            self.member(name, seen_days_ago=900, notice_days_ago=60, **flags)
        output = self.run_cleanup()
        self.assertIn("삭제 0명", output)
        self.assertIn("안내 메일 0명", output)


class LastSeenTest(PurgeTestBase):
    """토큰 인증이 마지막 이용일을 하루 한 번 적는다."""

    def _user_updates(self, captured):
        return [sql for sql in writes_in(captured) if "accounts_user" in sql]

    def test_a_returning_member_is_cancelled(self):
        """돌아온 회원은 이용일이 오늘이 되고 안내 기록이 비워진다."""
        user = self.member("returns", seen_days_ago=350, notice_days_ago=15)

        self.assertEqual(self.visit(user).status_code, 200)

        user.refresh_from_db()
        self.assertEqual(user.last_seen_on, self.today())
        self.assertIsNone(user.purge_notice_sent_at)

    def test_writes_once_a_day(self):
        """같은 날 두 번째 요청부터는 사용자 표에 안 쓴다."""
        user = self.member("daily", seen_days_ago=1)

        with CaptureQueriesContext(connection) as first:
            self.visit(user)
        with CaptureQueriesContext(connection) as second:
            self.visit(user)

        self.assertEqual(len(self._user_updates(first)), 1)
        self.assertEqual(self._user_updates(second), [])

    def test_only_the_two_columns_are_written(self):
        """다른 칸을 옛 값으로 덮으면 안 된다."""
        user = self.member("narrow", seen_days_ago=1)
        with CaptureQueriesContext(connection) as captured:
            self.visit(user)
        sql = self._user_updates(captured)[0]
        self.assertIn("last_seen_on", sql)
        self.assertIn("purge_notice_sent_at", sql)
        self.assertNotIn("avatar_photo", sql)
        self.assertNotIn("display_name", sql)

    def test_inactive_token_changes_nothing(self):
        user = self.member("off", seen_days_ago=400, notice_days_ago=10, is_active=False)
        old_seen = user.last_seen_on

        self.assertEqual(self.visit(user).status_code, 401)

        user.refresh_from_db()
        self.assertEqual(user.last_seen_on, old_seen)
        self.assertIsNotNone(user.purge_notice_sent_at)

    def test_forged_token_changes_nothing(self):
        user = self.member("forged", seen_days_ago=400, notice_days_ago=10)

        got = self.client.get(ME_URL, HTTP_AUTHORIZATION="Token 0000")

        self.assertEqual(got.status_code, 401)
        self.assertTrue(self.noticed(user))

    def test_kst_midnight_is_the_day_boundary(self):
        """23:59:59 와 00:00:00 은 다른 날이다. UTC 날짜로 세면 9시간 어긋난다."""
        self.clock = datetime(2026, 11, 8, 23, 59, 59, tzinfo=KST)
        user = self.member("midnight", seen_days_ago=2)

        self.visit(user)
        user.refresh_from_db()
        self.assertEqual(user.last_seen_on.isoformat(), "2026-11-08")

        self.clock = datetime(2026, 11, 9, 0, 0, 0, tzinfo=KST)
        with CaptureQueriesContext(connection) as captured:
            self.visit(user)
        user.refresh_from_db()
        self.assertEqual(user.last_seen_on.isoformat(), "2026-11-09")
        self.assertEqual(len(self._user_updates(captured)), 1)

    def test_kst_date_is_written_while_utc_is_still_yesterday(self):
        """KST 00:30 은 UTC 로 전날 15:30 이다. 적히는 것은 KST 날짜다."""
        self.clock = datetime(2026, 11, 8, 15, 30, 0, tzinfo=ZoneInfo("UTC"))
        user = self.member("utc", seen_days_ago=1)

        self.visit(user)

        user.refresh_from_db()
        self.assertEqual(user.last_seen_on.isoformat(), "2026-11-09")

    def test_returning_starts_a_new_year(self):
        """돌아온 뒤에는 다시 335일을 채워야 안내가 간다."""
        user = self.member("cycle", seen_days_ago=350, notice_days_ago=5)
        self.visit(user)

        self.clock += timedelta(days=334)
        self.apply()
        self.assertEqual(django_mail.outbox, [])

        self.clock += timedelta(days=1)
        self.apply()
        self.assertEqual(self.recipients(), [user.email])

        # 예전 안내가 다시 살아나 곧바로 지워지는 일이 없다.
        self.assertTrue(self.exists(user))


class MailFailureTest(PurgeTestBase):
    """메일이 실패할 때."""

    def _failing_for(self, *emails, error=None):
        """주어진 주소만 실패하고 나머지는 보낸 것으로 친다."""
        delivered = []

        def fake(*, to, subject, body):
            if to in emails:
                raise error or smtplib.SMTPRecipientsRefused({to: (550, b"no")})
            delivered.append(to)

        return mock.patch(SMTP_SENDER, side_effect=fake), delivered

    def test_one_failure_does_not_stop_the_rest(self):
        a = self.member("a", seen_days_ago=400)
        bad = self.member("bad", seen_days_ago=400)
        c = self.member("c", seen_days_ago=400)
        patcher, delivered = self._failing_for(bad.email)

        with patcher, self.assertLogs("apps.accounts.purge", "ERROR"):
            output = self.apply()

        self.assertCountEqual(delivered, [a.email, c.email])
        self.assertTrue(self.noticed(a))
        self.assertTrue(self.noticed(c))
        self.assertFalse(self.noticed(bad))
        self.assertIn("안내 메일 2명, 실패 1명", output)

    def test_every_transport_error_is_contained(self):
        """SMTP 거절·접속 끊김·시간 초과·TLS·잘못된 주소가 다 한 통 실패로 끝난다."""
        errors = [
            smtplib.SMTPAuthenticationError(535, b"bad"),
            smtplib.SMTPServerDisconnected("gone"),
            socket.timeout("slow"),
            socket.gaierror("dns"),
            ConnectionRefusedError("refused"),
            ssl.SSLError("tls"),
            ValueError("Invalid address"),
        ]
        for index, error in enumerate(errors):
            with self.subTest(error=type(error).__name__):
                # 앞 회차에서 실패한 회원은 재시도 대상이라 치운다.
                User.objects.all().delete()
                bad = self.member(f"bad{index}", seen_days_ago=400)
                good = self.member(f"good{index}", seen_days_ago=400)
                patcher, delivered = self._failing_for(bad.email, error=error)

                with patcher, self.assertLogs("apps.accounts.purge", "ERROR"):
                    self.apply()

                self.assertEqual(delivered, [good.email])
                self.assertFalse(self.noticed(bad))

    def test_failed_member_is_retried_next_day_and_only_they_are(self):
        ok = self.member("ok", seen_days_ago=400)
        bad = self.member("retry", seen_days_ago=400)
        patcher, _ = self._failing_for(bad.email)

        with patcher, self.assertLogs("apps.accounts.purge", "ERROR"):
            self.apply()

        self.clock += timedelta(days=1)
        self.apply()

        self.assertEqual(self.recipients(), [bad.email])
        self.assertTrue(self.noticed(ok))
        self.assertTrue(self.noticed(bad))

    def test_failed_member_is_not_deleted_after_thirty_days(self):
        """안내가 계속 실패한 회원은 30일이 지나도 지우지 않는다."""
        bad = self.member("neverpass", seen_days_ago=400)
        patcher, _ = self._failing_for(bad.email)

        with patcher, self.assertLogs("apps.accounts.purge", "ERROR"), self.assertRaises(
            CommandError
        ):
            self.apply()

        self.clock += timedelta(days=60)
        with patcher, self.assertLogs("apps.accounts.purge", "ERROR"), self.assertRaises(
            CommandError
        ):
            self.apply()

        self.assertTrue(self.exists(bad))
        self.assertFalse(self.noticed(bad))

    def test_all_failed_is_a_command_error(self):
        one = self.member("x", seen_days_ago=400)
        two = self.member("y", seen_days_ago=400)
        patcher, _ = self._failing_for(one.email, two.email)

        with patcher, self.assertLogs("apps.accounts.purge", "ERROR"):
            with self.assertRaises(CommandError):
                self.apply()

        self.assertFalse(self.noticed(one))
        self.assertFalse(self.noticed(two))

    def test_no_account_is_a_command_error_and_stamps_nothing(self):
        user = self.member("noaccount", seen_days_ago=400)
        self.purge_sends.return_value = False

        with self.assertRaises(CommandError):
            self.apply()

        self.assertEqual(django_mail.outbox, [])
        self.assertFalse(self.noticed(user))

    def test_no_account_with_nobody_to_notify_succeeds(self):
        self.member("nobody")
        self.purge_sends.return_value = False
        self.assertIn("안내 메일 0명", self.apply())

    def test_broken_mail_does_not_hold_back_due_deletes(self):
        """메일 계정이 망가져도 기한이 지난 회원은 지워진다."""
        expired = self.member("due", seen_days_ago=500, notice_days_ago=31)
        self.member("needsmail", seen_days_ago=400)
        self.purge_sends.return_value = False

        with self.assertRaises(CommandError):
            self.apply()

        self.assertFalse(self.exists(expired))

    def test_no_email_address_reaches_the_logs_or_output(self):
        """예외 메시지에 주소가 있어도 로그·출력·CommandError 에 안 남는다."""
        good = self.member("good", seen_days_ago=400)
        bad = self.member("leak", seen_days_ago=400)
        patcher, _ = self._failing_for(bad.email)

        with patcher, self.assertLogs("apps.accounts.purge", "ERROR") as logs:
            output = self.apply()

        joined = "\n".join(logs.output)
        self.assertNotIn(bad.email, joined)
        self.assertNotIn("@", joined)
        self.assertIn(f"user={bad.pk}", joined)
        self.assertNotIn(good.email, output)
        self.assertNotIn("@", output)

        everyone_fails, _ = self._failing_for(good.email, bad.email)
        User.objects.update(purge_notice_sent_at=None)
        with everyone_fails, self.assertLogs("apps.accounts.purge", "ERROR"):
            with self.assertRaises(CommandError) as caught:
                self.apply()
        self.assertNotIn("@", str(caught.exception))


class RealBackendGateTest(PurgeTestBase):
    """정말 나가는 백엔드가 아니면 안내를 시작하지 않는다."""

    mail_works = False

    BACKENDS = (
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
    )

    def test_refuses_to_start_when_someone_is_due(self):
        """DEBUG 콘솔이면 에러 없이 끝나 "안내한 것" 으로 찍힌다. 그걸 막는다."""
        user = self.member("console", seen_days_ago=400)

        for backend in self.BACKENDS:
            with self.subTest(backend=backend), override_settings(
                DEBUG=True, EMAIL_BACKEND=backend
            ):
                with self.assertRaises(CommandError):
                    self.apply()
                self.assertFalse(self.noticed(user))

        self.assertEqual(django_mail.outbox, [])

    @override_settings(
        DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
    )
    def test_starts_when_nobody_is_due(self):
        self.member("fresh")
        self.assertIn("안내 메일 0명", self.apply())


class ComingBackMidRunTest(PurgeTestBase):
    """명령이 도는 사이 회원이 돌아올 때."""

    def test_return_during_sending_leaves_no_stamp(self):
        """메일을 보내는 도중 돌아온 회원은 안내 시각이 안 찍힌다."""
        back = self.member("midmail", seen_days_ago=340)
        other = self.member("othermail", seen_days_ago=340)

        def returns_while_mailing(*, to, subject, body):
            if to == back.email:
                self.visit(back)

        with mock.patch(SMTP_SENDER, side_effect=returns_while_mailing):
            self.apply()

        self.assertFalse(self.noticed(back))
        self.assertTrue(self.noticed(other))

    def test_returned_member_is_safe_a_year_later(self):
        """그때 찍혔다면 1년 뒤 새 안내 없이 지워질 자리다."""
        back = self.member("safe", seen_days_ago=340)

        with mock.patch(
            SMTP_SENDER, side_effect=lambda **kwargs: self.visit(back)
        ):
            self.apply()

        self.clock += timedelta(days=365)
        self.apply()
        self.assertTrue(self.exists(back))

    def test_return_after_the_list_is_drawn_blocks_the_delete(self):
        """지울 목록을 뽑은 뒤 돌아온 회원은 지우지 않는다."""
        back = self.member("late", seen_days_ago=400, notice_days_ago=31)
        gone = self.member("staysgone", seen_days_ago=400, notice_days_ago=31)
        real = purge.due_for_delete
        calls = {"n": 0}

        def wrapped():
            calls["n"] += 1
            if calls["n"] == 2:
                self.visit(back)
            return real()

        with mock.patch.object(purge, "due_for_delete", wrapped):
            deleted = purge.delete_expired()

        self.assertEqual(deleted, 1)
        self.assertTrue(self.exists(back))
        self.assertFalse(self.exists(gone))
        self.assertFalse(self.noticed(back))

    def test_suspended_after_the_list_is_not_deleted(self):
        """목록 뒤 정지된 계정도 지우는 순간의 조건에 걸린다."""
        user = self.member("banlate", seen_days_ago=400, notice_days_ago=31)
        real = purge.due_for_delete
        calls = {"n": 0}

        def wrapped():
            calls["n"] += 1
            if calls["n"] == 2:
                User.objects.filter(pk=user.pk).update(is_active=False)
            return real()

        with mock.patch.object(purge, "due_for_delete", wrapped):
            self.assertEqual(purge.delete_expired(), 0)

        self.assertTrue(self.exists(user))


class KstBoundaryTest(PurgeTestBase):
    """대상을 고르는 날짜가 KST 인가."""

    def test_stale_date_turns_over_at_kst_midnight(self):
        """23:59:59 에는 334일째라 안 가고, 00:00:00 이 되면 335일째라 간다."""
        self.clock = datetime(2026, 11, 8, 23, 59, 59, tzinfo=KST)
        user = self.member("turnover", seen_days_ago=334)

        self.apply()
        self.assertEqual(django_mail.outbox, [])

        self.clock = datetime(2026, 11, 9, 0, 0, 0, tzinfo=KST)
        self.apply()
        self.assertEqual(self.recipients(), [user.email])

    def test_cron_hour_uses_the_kst_date(self):
        """03:00 KST 는 UTC 로 전날 18:00 이다. 그 시각의 '오늘' 은 KST 날짜다."""
        self.clock = datetime(2026, 11, 8, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
        kst_today = datetime(2026, 11, 9).date()
        edge = self.member("cronedge", seen_days_ago=0)
        short = self.member("cronshort", seen_days_ago=0)
        User.objects.filter(pk=edge.pk).update(last_seen_on=kst_today - timedelta(days=335))
        User.objects.filter(pk=short.pk).update(last_seen_on=kst_today - timedelta(days=334))

        self.apply()

        self.assertEqual(self.recipients(), [edge.email])

    def test_delete_window_is_exact_time_not_calendar_days(self):
        """밤에 안내하고 30일 뒤 새벽이면 30일이 안 찼으니 안 지운다."""
        self.clock = datetime(2026, 10, 10, 23, 30, 0, tzinfo=KST)
        user = self.member("night", seen_days_ago=400)
        self.apply()

        self.clock = datetime(2026, 11, 9, 3, 0, 0, tzinfo=KST)
        self.assertEqual(self.today() - datetime(2026, 10, 10).date(), timedelta(days=30))
        self.apply()
        self.assertTrue(self.exists(user))

        self.clock = datetime(2026, 11, 10, 3, 0, 0, tzinfo=KST)
        self.apply()
        self.assertFalse(self.exists(user))


class RoundStepRetentionTest(PurgeTestBase):
    """일반 판과 복습 판의 보관 기한이 다르다."""

    def _ids(self):
        return set(session.expired_steps().values_list("round_id", flat=True))

    def test_each_kind_keeps_its_own_window(self):
        long = session.LONG_ROUND_PREFIX
        ages = {
            "free-inside": session.TOKEN_MAX_AGE - 1,
            "free-edge": session.TOKEN_MAX_AGE,
            "free-outside": session.TOKEN_MAX_AGE + 1,
            f"{long}at-eleven-minutes": session.TOKEN_MAX_AGE + 60,
            f"{long}inside": session.LONG_STEP_KEEP_SECONDS - 1,
            f"{long}edge": session.LONG_STEP_KEEP_SECONDS,
            f"{long}outside": session.LONG_STEP_KEEP_SECONDS + 1,
        }
        for round_id, age in ages.items():
            aged_step(round_id, age, self.clock)

        self.assertEqual(self._ids(), {"free-outside", f"{long}outside"})

    def test_prefix_must_be_at_the_start(self):
        """'long-' 이 가운데 있는 일반 판은 일반 판 기한을 받는다."""
        aged_step("xlong-abc", session.TOKEN_MAX_AGE + 60, self.clock)
        self.assertEqual(self._ids(), {"xlong-abc"})

    def test_apply_removes_only_expired_steps(self):
        long = session.LONG_ROUND_PREFIX
        aged_step("old-free", session.TOKEN_MAX_AGE + 60, self.clock)
        aged_step(f"{long}alive", 60 * 60, self.clock)

        output = self.apply()

        self.assertEqual(
            list(RoundStep.objects.values_list("round_id", flat=True)), [f"{long}alive"]
        )
        self.assertIn("진행 표시 1행", output)

    def test_review_outlives_every_token_it_guards(self):
        """표시는 토큰보다 오래 살아야 한다. 짧으면 그 차이만큼 되돌리기가 열린다."""
        self.assertGreater(session.LONG_STEP_KEEP_SECONDS, review.TOKEN_MAX_AGE)


class ReplayAfterCleanupTest(TestCase):
    """매일 정리가 돌아도 살아 있는 복습 토큰의 되돌리기는 막힌다."""

    START = "/api/learning/review/"
    ANSWER = "/api/learning/review/answer/"

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = User.objects.create_user(
            email="replay@example.com", display_name="되돌리기청소"
        )
        self.client.force_login(self.user)
        a_round(self.user, [(Word.objects.first().pk, False)])

    def _at(self, seconds):
        wall = signing.time.time() + seconds
        moment = timezone.now() + timedelta(seconds=seconds)
        return (
            mock.patch.object(signing.time, "time", return_value=wall),
            mock.patch("django.utils.timezone.now", return_value=moment),
        )

    def _replay(self, token, choice):
        return self.client.post(
            self.ANSWER,
            {"token": token, "choice_id": choice},
            content_type="application/json",
        )

    def test_live_review_token_stays_refused_after_cleanup(self):
        """11분·1시간·5시간 59분 뒤 정리가 돌아도 같은 토큰은 400 이다."""
        body = self.client.post(self.START).json()
        token, choice = body["token"], body["question"]["choices"][0]["id"]
        self.assertEqual(self._replay(token, choice).status_code, 200)

        for seconds in (session.TOKEN_MAX_AGE + 60, 3600, review.TOKEN_MAX_AGE - 60):
            clock, now = self._at(seconds)
            with self.subTest(seconds=seconds), clock, now:
                call_command("daily_cleanup", "--apply", stdout=StringIO())
                self.assertEqual(RoundStep.objects.count(), 1)
                again = self._replay(token, choice)
                self.assertEqual(again.status_code, 400)
                self.assertIn("이미 처리한 답", again.json()["detail"])


class CounterSweepTest(PurgeTestBase):
    """시도 횟수 행은 만료된 것만 지운다."""

    def _seed(self):
        add_counter("expired-long-ago", self.clock - timedelta(days=30))
        add_counter("expired-just-now", self.clock - timedelta(seconds=1))
        add_counter("expires-this-second", self.clock)
        add_counter("alive", self.clock + timedelta(seconds=30))

    def test_apply_removes_expired_rows_only(self):
        self._seed()
        self.assertEqual(sweep_expired_counters(apply=True), 2)
        self.assertEqual(counter_keys(), {"expires-this-second", "alive"})

    def test_preview_counts_the_same_rows_and_keeps_them(self):
        self._seed()
        self.assertEqual(sweep_expired_counters(apply=False), 2)
        self.assertEqual(len(counter_keys()), 4)


class CounterSweepRealClockTest(TestCase):
    """DB 캐시는 만료 시각을 time.time 으로 계산해 고정 시계와 어긋난다. 실제 시계로 본다."""

    def setUp(self):
        cache.clear()

    def test_real_throttle_entry_survives_while_alive(self):
        cache.set("live-entry", [1, 2, 3], 60)
        self.assertEqual(sweep_expired_counters(apply=True), 0)
        self.assertEqual(cache.get("live-entry"), [1, 2, 3])


class EmailThrottleKeyTest(TestCase):
    """이메일 제한은 해시를 바꾼 뒤에도 같은 사람을 같은 키로 센다."""

    def _key(self, email):
        request = mock.Mock(data={"email": email})
        return EmailRateThrottle().get_cache_key(request, None)

    def test_case_and_surrounding_spaces_share_a_key(self):
        base = self._key("user@example.com")
        for variant in ("USER@EXAMPLE.COM", "  user@example.com  ", "\tUser@Example.Com\n"):
            with self.subTest(variant=variant):
                self.assertEqual(self._key(variant), base)

    def test_different_emails_get_different_keys(self):
        self.assertNotEqual(self._key("a@example.com"), self._key("b@example.com"))

    def test_key_does_not_contain_or_reveal_the_email(self):
        """후보 이메일의 맨 SHA-256 과 대조해도 맞지 않아야 한다."""

        email = "user@example.com"
        key = self._key(email)
        self.assertNotIn(email, key)
        self.assertNotIn(hashlib.sha256(email.encode()).hexdigest(), key)

    def test_key_depends_on_the_server_secret(self):
        before = self._key("user@example.com")
        with override_settings(SECRET_KEY="another-secret-for-this-test-only"):
            self.assertNotEqual(self._key("user@example.com"), before)

    def test_non_string_or_blank_email_is_not_counted(self):
        for value in (None, 1, ["a@example.com"], "", "   "):
            with self.subTest(value=value):
                self.assertIsNone(self._key(value))


class EmailThrottleHttpTest(TestCase):
    """로그인 시도 제한이 실제로 같은 통에 담기고, 정리 뒤에도 유지된다."""

    def setUp(self):
        cache.clear()
        rate = mock.patch.object(EmailRateThrottle, "get_rate", return_value="3/min")
        rate.start()
        self.addCleanup(rate.stop)

    def _login(self, email):
        return self.client.post(
            LOGIN_URL,
            {"email": email, "password": "틀린비밀번호"},
            content_type="application/json",
        )

    def test_spelling_variants_hit_the_same_limit(self):
        for email in ("victim@example.com", "VICTIM@example.com", "  victim@EXAMPLE.com "):
            self.assertEqual(self._login(email).status_code, 400)

        self.assertEqual(self._login("Victim@Example.Com").status_code, 429)

    def test_cleanup_does_not_reset_a_live_counter(self):
        for _ in range(3):
            self._login("victim@example.com")

        call_command("daily_cleanup", "--apply", stdout=StringIO())

        self.assertEqual(self._login("victim@example.com").status_code, 429)


class CascadeTest(PurgeTestBase):
    """지운 회원의 학습 기록이 함께 지워지고 다른 회원은 그대로다."""

    def _give_records(self, user, word):
        a_round(user, [(word.pk, False)])
        DailyStudy.objects.create(
            user=user, day=self.today(), length=StudyLength.SHORT, total_questions=10
        )
        DailyScore.objects.update_or_create(
            user=user, day=self.today(), defaults={"best_free_score": 5}
        )
        LoginToken.objects.create(user=user)

    def test_records_go_with_the_member_and_nobody_else_is_touched(self):
        seed_words(2)
        word = Word.objects.first()
        gone = self.member("cascade", seen_days_ago=500, notice_days_ago=31)
        stays = self.member("bystander")
        self._give_records(gone, word)
        self._give_records(stays, word)
        word_count = Word.objects.count()
        stays_answers = QuizAnswer.objects.filter(session__user=stays).count()
        self.assertGreater(stays_answers, 0)

        self.apply()

        self.assertFalse(self.exists(gone))
        self.assertTrue(self.exists(stays))
        for model in (QuizSession, DailyScore, DailyStudy, ReviewState, LoginToken):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.filter(user_id=gone.pk).count(), 0)
                self.assertEqual(model.objects.filter(user=stays).count(), 1)
        self.assertEqual(QuizAnswer.objects.filter(session__user_id=gone.pk).count(), 0)
        self.assertEqual(QuizAnswer.objects.filter(session__user=stays).count(), stays_answers)
        self.assertEqual(Word.objects.count(), word_count)

    def test_nothing_points_at_a_member_in_a_way_that_blocks_delete(self):
        """PROTECT 가 생기면 그 회원에서 명령 전체가 멈춘다."""
        for relation in User._meta.related_objects:
            with self.subTest(model=relation.related_model.__name__):
                self.assertIs(relation.on_delete, models.CASCADE)

    def test_deleted_members_token_stops_working(self):
        gone = self.member("revoked", seen_days_ago=500, notice_days_ago=31)
        token = LoginToken.objects.create(user=gone).key

        self.apply()

        got = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(got.status_code, 401)


def _run_together(*calls):
    """calls 를 각자의 스레드(= 각자의 DB 연결)에서 같이 돌린다."""
    barrier = threading.Barrier(len(calls))
    errors: list[Exception] = []

    def one(fn):
        barrier.wait()
        try:
            fn()
        except Exception as exc:  # 무엇이 났는지 그대로 본다
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=one, args=(fn,)) for fn in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class RealConcurrencyTest(_KeepsCacheTable, TransactionTestCase):
    """실제 두 연결에서 겹칠 때. 한 번에 안 드러나서 여러 번 돌린다."""

    ROUNDS = 15

    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()

    def _stale(self, name, notice_days_ago=None):
        user = User.objects.create_user(email=f"{name}@example.com", display_name=name)
        notice = (
            None if notice_days_ago is None
            else timezone.now() - timedelta(days=notice_days_ago)
        )
        User.objects.filter(pk=user.pk).update(
            last_seen_on=self.today - timedelta(days=400), purge_notice_sent_at=notice
        )
        return user

    def _come_back(self, pk):
        """삭제가 먼저 끝났으면 실제 요청은 토큰이 없어 401 이고 여기까지 안 온다."""

        def visit():
            user = User.objects.filter(pk=pk).first()
            if user is not None:
                _mark_seen(user)

        return visit

    @mock.patch("apps.accounts.purge._really_sends", return_value=True)
    def test_return_racing_the_stamp_never_leaves_a_stamp(self, _sends):
        """돌아오기와 안내 찍기가 겹쳐도 돌아온 회원에게 안내 시각이 안 남는다."""
        for round_no in range(self.ROUNDS):
            user = self._stale(f"s{round_no}")
            with mock.patch(SMTP_SENDER):
                errors = _run_together(purge.send_notices, self._come_back(user.pk))

            self.assertEqual(errors, [])
            user.refresh_from_db()
            self.assertGreaterEqual(user.last_seen_on, self.today)
            self.assertIsNone(user.purge_notice_sent_at, f"{round_no}회차에 찍혔다")

    def test_return_racing_delete_ends_in_a_clean_state(self):
        """겹쳐도 예외가 없고, 살아남았다면 안내 기록이 비어 있다."""
        for round_no in range(self.ROUNDS):
            user = self._stale(f"d{round_no}", notice_days_ago=31)

            errors = _run_together(purge.delete_expired, self._come_back(user.pk))

            self.assertEqual(errors, [])
            alive = User.objects.filter(pk=user.pk).first()
            if alive is not None:
                self.assertGreaterEqual(alive.last_seen_on, self.today)
                self.assertIsNone(alive.purge_notice_sent_at)

    def test_return_between_check_and_delete_waits_for_the_lock(self):
        """조건을 본 뒤 DELETE 전에 돌아온 회원의 UPDATE 는 잠금에 막혀 반영되지 않는다.

        잠금이 없으면 UPDATE 가 커밋되고(돌아왔다고 기록) 곧바로 그 회원이 지워진다.
        """
        user = self._stale("interleave", notice_days_ago=31)
        coming_back = []
        result = {}

        def return_mid_delete(sender, instance, **kwargs):
            def back():
                try:
                    result["updated"] = User.objects.filter(pk=user.pk).update(
                        last_seen_on=self.today, purge_notice_sent_at=None
                    )
                finally:
                    connections.close_all()

            thread = threading.Thread(target=back)
            thread.start()
            thread.join(timeout=3)
            result["blocked"] = thread.is_alive()
            coming_back.append(thread)

        pre_delete.connect(return_mid_delete, sender=User)
        self.addCleanup(pre_delete.disconnect, return_mid_delete, sender=User)

        self.assertEqual(purge.delete_expired(), 1)
        coming_back[0].join(timeout=30)

        self.assertTrue(result["blocked"], "돌아온 회원의 UPDATE 가 잠금 없이 지나갔다")
        self.assertEqual(result["updated"], 0)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_two_deletes_at_once_do_not_blow_up(self):
        for round_no in range(self.ROUNDS):
            user = self._stale(f"t{round_no}", notice_days_ago=31)
            a_round(user, [(self._word().pk, False)])

            errors = _run_together(purge.delete_expired, purge.delete_expired)

            self.assertEqual(errors, [])
            self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def _word(self):
        word = Word.objects.first()
        if word is None:
            seed_words(1)
            word = Word.objects.first()
        return word
