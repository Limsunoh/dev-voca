"""학습 기록 Admin.

지키는 것 둘.

1. **판을 지우면 그날 하루 점수가 남은 판으로 다시 세진다.** 안 그러면
   지운 판의 점수가 꾸준함 순위표에만 남는다.
2. **보기 전용이다.** 추가·수정은 막고, 지우기는 판만 된다.
"""

from __future__ import annotations

import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from unittest import mock, skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db import connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from . import record
from .models import (
    DailyScore,
    DailyStudy,
    QuizSession,
    ReviewState,
    SessionKind,
    StudyLength,
)
from .tests_daily_study_edge import _KeepsCacheTable

PASSWORD = secrets.token_urlsafe(16)

# 한국 날짜 2026-09-10. UTC 로는 9/9 15:00 부터 9/10 15:00 까지다.
DAY = date(2026, 9, 10)
NEXT_DAY = date(2026, 9, 11)


def kst(day: date, hour: int, minute: int = 0) -> datetime:
    """한국 시각을 UTC 시각으로. 테스트가 기대값을 구현의 날짜 함수로 다시 세지 않게."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc) - timedelta(
        hours=9
    )


def make_user(name: str, **extra):
    return get_user_model().objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name, **extra
    )


def play(user, finished_at: datetime, score: int, kind=SessionKind.FREE) -> QuizSession:
    """판 하나를 끝낸 것처럼 남긴다. 하루 점수는 실제 기록 경로(_bump_daily)로 쌓는다."""
    session = QuizSession.objects.create(
        user=user,
        kind=kind,
        token_id=uuid4().hex,
        started_at=finished_at - timedelta(seconds=90),
        finished_at=finished_at,
        score=score,
        answered=10,
        correct=7,
    )
    # 판 쪽은 save_round 의 트랜잭션 안에서 부른다. _bump_daily 가 줄을
    # 잠그므로(select_for_update) 트랜잭션 밖에서는 부를 수 없다.
    with transaction.atomic():
        record._bump_daily(session)
    return session


def best_of(user, day):
    row = DailyScore.objects.filter(user=user, day=day).first()
    return "줄 없음" if row is None else row.best_free_score


class AdminDeleteRecountsTest(TestCase):
    def setUp(self):
        self.admin = make_user("관리자", is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)
        self.user = make_user("학생")

    def delete_one(self, session):
        url = reverse("admin:learning_quizsession_delete", args=[session.pk])
        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizSession.objects.filter(pk=session.pk).exists())

    def delete_many(self, *sessions):
        response = self.client.post(
            reverse("admin:learning_quizsession_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [s.pk for s in sessions],
                "post": "yes",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizSession.objects.filter(pk__in=[s.pk for s in sessions]).exists())

    def test_deleting_the_best_round_falls_back_to_the_next_best(self):
        play(self.user, kst(DAY, 9), 10)
        top = play(self.user, kst(DAY, 12), 30)
        play(self.user, kst(DAY, 18), -4)
        self.assertEqual(best_of(self.user, DAY), 30)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, DAY), 10)

    def test_deleting_a_lower_round_keeps_the_best(self):
        low = play(self.user, kst(DAY, 9), 10)
        play(self.user, kst(DAY, 12), 30)

        self.delete_one(low)

        self.assertEqual(best_of(self.user, DAY), 30)

    def test_a_negative_round_can_become_the_best(self):
        # 남은 판이 마이너스뿐이면 그 값이 그날 최고다(0 으로 올리지 않는다).
        top = play(self.user, kst(DAY, 9), 12)
        play(self.user, kst(DAY, 10), -3)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, DAY), -3)

    def test_deleting_the_only_round_empties_the_day(self):
        # 줄은 남기고 점수만 비운다. 줄을 지우면 그 순간 낸 일일공부 답의
        # 점수가 지워진 줄을 가리켜 사라질 수 있다(recount_best_free 참고).
        only = play(self.user, kst(DAY, 9), 12)

        self.delete_one(only)

        row = DailyScore.objects.get(user=self.user, day=DAY)
        self.assertIsNone(row.best_free_score)
        self.assertEqual(row.total, 0)

    def test_a_day_with_daily_study_points_keeps_its_row(self):
        only = play(self.user, kst(DAY, 9), 12)
        DailyScore.objects.filter(user=self.user, day=DAY).update(daily_study_score=7)

        self.delete_one(only)

        row = DailyScore.objects.get(user=self.user, day=DAY)
        self.assertIsNone(row.best_free_score)
        self.assertEqual(row.daily_study_score, 7)
        self.assertEqual(row.total, 7)

    def test_the_day_is_the_korean_day(self):
        # 세 판은 UTC 로는 모두 9/10 이다(14:30, 15:30, 23:00). 날의 경계를
        # UTC 자정으로 잡으면 9/11 판들이 창 밖으로 빠지거나 9/10 판(40)이
        # 섞여 들어온다.
        play(self.user, kst(DAY, 23, 30), 40)
        late = play(self.user, kst(NEXT_DAY, 0, 30), 25)
        play(self.user, kst(NEXT_DAY, 8), 5)

        self.delete_one(late)

        self.assertEqual(best_of(self.user, DAY), 40)
        self.assertEqual(best_of(self.user, NEXT_DAY), 5)

    def test_only_free_rounds_count(self):
        free = play(self.user, kst(DAY, 9), 12)
        QuizSession.objects.create(
            user=self.user,
            kind=SessionKind.DAILY,
            token_id=uuid4().hex,
            started_at=kst(DAY, 10),
            finished_at=kst(DAY, 10, 5),
            score=50,
            answered=10,
            correct=10,
        )

        self.delete_one(free)

        self.assertIsNone(best_of(self.user, DAY))

    def test_other_people_and_other_days_are_untouched(self):
        other = make_user("다른학생")
        play(other, kst(DAY, 9), 50)
        play(self.user, kst(NEXT_DAY, 9), 20)
        top = play(self.user, kst(DAY, 9), 30)
        play(self.user, kst(DAY, 10), 10)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, DAY), 10)
        self.assertEqual(best_of(self.user, NEXT_DAY), 20)
        self.assertEqual(best_of(other, DAY), 50)

    def test_bulk_delete_recounts_every_day_it_touched(self):
        a = play(self.user, kst(DAY, 9), 30)
        play(self.user, kst(DAY, 10), 10)
        b = play(self.user, kst(NEXT_DAY, 9), 20)
        c = play(self.user, kst(NEXT_DAY, 10), 15)
        other = make_user("다른학생")
        d = play(other, kst(DAY, 9), 50)

        self.delete_many(a, b, c, d)

        self.assertEqual(best_of(self.user, DAY), 10)
        self.assertIsNone(best_of(self.user, NEXT_DAY))
        self.assertIsNone(best_of(other, DAY))

    def test_answers_go_with_the_round(self):
        top = play(self.user, kst(DAY, 9), 30)
        top.answers.create(
            kind="meaning",
            target_type="word",
            target_id=1,
            is_correct=True,
            elapsed_ms=1000,
            score=3,
        )

        self.delete_one(top)

        self.assertFalse(top.answers.model.objects.filter(session_id=top.pk).exists())


class AdminIsViewOnlyTest(TestCase):
    def setUp(self):
        self.admin = make_user("관리자", is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)
        self.user = make_user("학생")
        self.session = play(self.user, kst(DAY, 9), 12)
        DailyStudy.objects.create(
            user=self.user, day=DAY, length=StudyLength.SHORT, total_questions=10
        )
        ReviewState.objects.create(user=self.user, target_type="word", target_id=1, is_wrong=True)
        self.rows = {
            "quizsession": self.session,
            "dailyscore": DailyScore.objects.get(user=self.user, day=DAY),
            "dailystudy": DailyStudy.objects.get(user=self.user, day=DAY),
            "reviewstate": ReviewState.objects.get(user=self.user),
        }

    def test_lists_and_details_open(self):
        for name, row in self.rows.items():
            with self.subTest(name):
                listing = self.client.get(reverse(f"admin:learning_{name}_changelist"))
                self.assertEqual(listing.status_code, 200)
                self.assertContains(listing, "학생@example.com")
                detail = self.client.get(reverse(f"admin:learning_{name}_change", args=[row.pk]))
                self.assertEqual(detail.status_code, 200)

    def test_search_by_email(self):
        for name in self.rows:
            with self.subTest(name):
                response = self.client.get(
                    reverse(f"admin:learning_{name}_changelist"), {"q": "학생@example"}
                )
                self.assertContains(response, "학생@example.com")

    def test_nothing_can_be_added(self):
        for name in self.rows:
            with self.subTest(name):
                response = self.client.get(reverse(f"admin:learning_{name}_add"))
                self.assertEqual(response.status_code, 403)

    def test_nothing_can_be_edited(self):
        url = reverse("admin:learning_quizsession_change", args=[self.session.pk])
        response = self.client.post(
            url,
            {
                "user": self.user.pk,
                "kind": SessionKind.FREE,
                "token_id": "x",
                "score": 999,
                "answered": 10,
                "correct": 7,
                "skipped": 0,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.score, 12)

    def test_only_rounds_can_be_deleted(self):
        for name, row in self.rows.items():
            if name == "quizsession":
                continue
            with self.subTest(name):
                url = reverse(f"admin:learning_{name}_delete", args=[row.pk])
                response = self.client.post(url, {"post": "yes"})
                self.assertEqual(response.status_code, 403)
                self.assertTrue(type(row).objects.filter(pk=row.pk).exists())

    def test_view_only_tables_offer_no_way_to_delete(self):
        # 지우기 권한은 열어 두고(사용자 삭제 때문에) 입구만 닫았다. 입구가
        # 남아 있으면 눌렀을 때 403 이 나는 버튼이 보인다.
        for name, row in self.rows.items():
            if name == "quizsession":
                continue
            with self.subTest(name):
                listing_url = reverse(f"admin:learning_{name}_changelist")
                listing = self.client.get(listing_url)
                self.assertNotContains(listing, 'value="delete_selected"')
                # 버튼만 숨긴 것이 아니라 손으로 보내도 안 지워진다.
                self.client.post(
                    listing_url,
                    {"action": "delete_selected", "_selected_action": [row.pk], "post": "yes"},
                )
                self.assertTrue(type(row).objects.filter(pk=row.pk).exists())
                detail = self.client.get(reverse(f"admin:learning_{name}_change", args=[row.pk]))
                self.assertNotContains(detail, f"/{row.pk}/delete/")

    def test_rounds_offer_delete(self):
        listing = self.client.get(reverse("admin:learning_quizsession_changelist"))
        self.assertContains(listing, 'value="delete_selected"')
        detail = self.client.get(
            reverse("admin:learning_quizsession_change", args=[self.session.pk])
        )
        self.assertContains(detail, f"/{self.session.pk}/delete/")

    def test_a_user_with_records_can_still_be_deleted(self):
        # Django 는 사용자를 지울 때 함께 지워질 모델마다 그 Admin 의 지우기
        # 권한을 묻는다. 보기 전용 표가 거기서 False 를 돌려주면 사용자 삭제가
        # 통째로 403 이 된다.
        url = reverse("admin:accounts_user_delete", args=[self.user.pk])

        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(DailyScore.objects.filter(pk=self.rows["dailyscore"].pk).exists())

    def test_staff_who_can_only_view_cannot_delete_rounds(self):
        staff = make_user("직원", is_staff=True)
        staff.user_permissions.add(
            Permission.objects.get(codename="view_quizsession", content_type__app_label="learning")
        )
        self.client.force_login(staff)

        url = reverse("admin:learning_quizsession_delete", args=[self.session.pk])
        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(QuizSession.objects.filter(pk=self.session.pk).exists())
        self.assertEqual(best_of(self.user, DAY), 12)

    def test_staff_without_permission_sees_nothing(self):
        staff = make_user("직원", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(reverse("admin:learning_quizsession_changelist"))

        self.assertEqual(response.status_code, 403)


class AdminEdgeTest(TestCase):
    """경계값과 잘못된 주소. 500 이 나면 안 된다."""

    def setUp(self):
        self.admin = make_user("관리자", is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)
        self.user = make_user("학생")

    def delete_one(self, session):
        url = reverse("admin:learning_quizsession_delete", args=[session.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 302)

    def test_a_round_at_exactly_korean_midnight_belongs_to_the_next_day(self):
        # 한국 9/11 00:00 정각(UTC 9/10 15:00)은 9/11 판이다. 창의 끝을
        # "이하" 로 잡으면 9/10 을 다시 셀 때 이 50 이 섞여 들어온다.
        play(self.user, kst(DAY, 23, 59) + timedelta(seconds=59, microseconds=999999), 7)
        top = play(self.user, kst(DAY, 9), 30)
        play(self.user, kst(NEXT_DAY, 0, 0), 50)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, DAY), 7)
        self.assertEqual(best_of(self.user, NEXT_DAY), 50)

    def test_a_round_at_exactly_korean_midnight_counts_after_its_own_day_is_recounted(self):
        # 창의 시작은 "이상" 이다. 9/11 00:00 정각 판은 9/11 을 다시 셀 때 들어가야 한다.
        play(self.user, kst(NEXT_DAY, 0, 0), 50)
        top = play(self.user, kst(NEXT_DAY, 9), 60)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, NEXT_DAY), 50)

    def test_deleting_a_daily_round_keeps_the_free_best(self):
        play(self.user, kst(DAY, 9), 12)
        daily = QuizSession.objects.create(
            user=self.user,
            kind=SessionKind.DAILY,
            token_id=uuid4().hex,
            started_at=kst(DAY, 10),
            finished_at=kst(DAY, 10, 5),
            score=50,
            answered=10,
            correct=10,
        )

        self.delete_one(daily)

        self.assertEqual(best_of(self.user, DAY), 12)

    def test_deleting_a_round_whose_day_has_no_row_makes_no_row(self):
        # 줄 없이 판만 있는 옛 데이터. 다시 센다고 줄을 새로 만들지 않는다.
        orphan = QuizSession.objects.create(
            user=self.user,
            kind=SessionKind.FREE,
            token_id=uuid4().hex,
            started_at=kst(DAY, 9),
            finished_at=kst(DAY, 9, 2),
            score=30,
            answered=10,
            correct=7,
        )

        self.delete_one(orphan)

        self.assertEqual(best_of(self.user, DAY), "줄 없음")

    def test_bulk_deleting_two_rounds_of_the_same_day(self):
        a = play(self.user, kst(DAY, 9), 30)
        b = play(self.user, kst(DAY, 10), 20)
        play(self.user, kst(DAY, 11), 5)

        response = self.client.post(
            reverse("admin:learning_quizsession_changelist"),
            {"action": "delete_selected", "_selected_action": [a.pk, b.pk], "post": "yes"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(best_of(self.user, DAY), 5)

    def test_staff_with_delete_permission_recounts_too(self):
        top = play(self.user, kst(DAY, 9), 30)
        play(self.user, kst(DAY, 10), 10)
        staff = make_user("직원", is_staff=True)
        staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="learning",
                codename__in=["view_quizsession", "delete_quizsession"],
            )
        )
        self.client.force_login(staff)

        self.delete_one(top)

        self.assertEqual(best_of(self.user, DAY), 10)

    def test_bad_ids_do_not_500(self):
        session = play(self.user, kst(DAY, 9), 30)
        for name in ("quizsession", "dailyscore", "dailystudy", "reviewstate"):
            for bad in ("9" * 30, "abc", "-1", "999999"):
                with self.subTest(name=name, bad=bad):
                    change = self.client.get(f"/admin/learning/{name}/{bad}/change/")
                    self.assertIn(change.status_code, (302, 404))
                    delete = self.client.post(
                        f"/admin/learning/{name}/{bad}/delete/", {"post": "yes"}
                    )
                    self.assertIn(delete.status_code, (302, 403, 404))
        self.assertTrue(QuizSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(best_of(self.user, DAY), 30)

    def test_bulk_delete_with_missing_ids_deletes_nothing(self):
        # 숫자가 아닌 값("abc")은 Django Admin 자체가 500 을 낸다(response_action
        # 이 pk__in 에 그대로 넣는다). 이 화면이 만든 문제가 아니라 뺐다.
        session = play(self.user, kst(DAY, 9), 30)

        response = self.client.post(
            reverse("admin:learning_quizsession_changelist"),
            {"action": "delete_selected", "_selected_action": ["9" * 30, "999999"], "post": "yes"},
        )

        self.assertLess(response.status_code, 500)
        self.assertTrue(QuizSession.objects.filter(pk=session.pk).exists())

    def test_date_drilldown_and_odd_search_do_not_500(self):
        play(self.user, kst(DAY, 9), 30)
        cases = {
            "quizsession": {"finished_at__year": "2026", "finished_at__month": "9"},
            "dailyscore": {"day__year": "2026", "day__month": "9", "day__day": "10"},
            "dailystudy": {"day__year": "2026"},
            "reviewstate": {"is_wrong__exact": "1"},
        }
        for name, params in cases.items():
            for q in ("", "   ", "%", "'; --", "가" * 500):
                with self.subTest(name=name, q=q[:10]):
                    response = self.client.get(
                        reverse(f"admin:learning_{name}_changelist"), {**params, "q": q}
                    )
                    self.assertEqual(response.status_code, 200)

    def test_round_detail_lists_answers_without_edit_controls(self):
        session = play(self.user, kst(DAY, 9), 30)
        session.answers.create(
            kind="meaning",
            target_type="word",
            target_id=77,
            is_correct=True,
            elapsed_ms=1000,
            score=3,
        )

        response = self.client.get(reverse("admin:learning_quizsession_change", args=[session.pk]))

        self.assertContains(response, "77")
        self.assertNotContains(response, "answers-0-DELETE")
        self.assertNotContains(response, 'name="_save"')


@skipUnless(connection.vendor == "postgresql", "줄 잠금 순서는 Postgres 에서만 확인된다")
class AdminDeleteRaceTest(_KeepsCacheTable, TransactionTestCase):
    """Admin 이 판을 지우는 사이 같은 사람이 같은 날 판을 끝낸다.

    그날 30·10 판이 있고 Admin 이 30 을 지우는 사이 20 판이 끝나면 최종
    best_free_score 는 20 이어야 한다. 어느 쪽이 먼저 그날 줄을 잡든.

    순서는 먼저 가는 쪽이 줄을 잡은 뒤 알리고 트랜잭션을 HOLD 초 붙잡아
    두는 것으로 강제한다. 그 사이에 다른 쪽이 출발한다. _bump_daily 가
    줄을 잠그지 않으면 **두 순서 모두** 10 이 남는다. 판 쪽의 조건부
    UPDATE 가 옛 값 30 을 보고 그 줄을 대상에서 빼 버려, Admin 이 먼저여도
    기다리지 않고, 판 쪽이 먼저여도 Admin 이 커밋 전의 20 을 못 본다.

    TransactionTestCase 인 이유: 스레드마다 커넥션이 달라, TestCase 의
    바깥 트랜잭션 안에서는 서로의 행이 안 보인다.
    """

    HOLD = 1.0

    def setUp(self):
        cache.clear()
        self.admin = make_user("관리자", is_staff=True, is_superuser=True)
        self.user = make_user("학생")
        self.top = play(self.user, kst(DAY, 9), 30)
        play(self.user, kst(DAY, 10), 10)
        # save_round 는 끝낸 시각을 지금으로 잡는다. 같은 날에 떨어지게 고정한다.
        clock = mock.patch.object(record, "timezone", mock.Mock(now=lambda: kst(DAY, 12)))
        clock.start()
        self.addCleanup(clock.stop)

    def finish_round(self):
        return record.save_round(
            self.user,
            {
                "kind": SessionKind.FREE,
                "token_id": uuid4().hex,
                "started_at": kst(DAY, 11, 58),
                "score": 20,
                "answered": 10,
                "correct": 8,
                "skipped": 0,
                "answers": [],
            },
        )

    def admin_client(self):
        client = Client()
        client.force_login(self.admin)
        return client

    def admin_delete_one(self):
        url = reverse("admin:learning_quizsession_delete", args=[self.top.pk])
        return self.admin_client().post(url, {"post": "yes"}).status_code

    def admin_delete_many(self):
        return (
            self.admin_client()
            .post(
                reverse("admin:learning_quizsession_changelist"),
                {"action": "delete_selected", "_selected_action": [self.top.pk], "post": "yes"},
            )
            .status_code
        )

    def run_race(self, first, second, hold_name):
        """first 가 record.<hold_name> 을 마치면(줄을 잡으면) second 를 출발시킨다."""
        locked = threading.Event()
        results = {}
        original = getattr(record, hold_name)

        def holding(*args, **kwargs):
            result = original(*args, **kwargs)
            locked.set()
            time.sleep(self.HOLD)
            return result

        def run(label, func, wait):
            try:
                if wait and not locked.wait(timeout=10):
                    results[label] = "먼저 가는 쪽이 줄을 잡지 못했다"
                    return
                results[label] = func()
            except Exception as exc:  # 무엇이 났는지 그대로 본다
                results[label] = exc
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=run, args=("first", first, False)),
            threading.Thread(target=run, args=("second", second, True)),
        ]
        with mock.patch.object(record, hold_name, holding):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        return results

    def assert_final_20(self, results, admin_label):
        round_label = "second" if admin_label == "first" else "first"
        self.assertEqual(results[admin_label], 302, results)
        self.assertIsInstance(results[round_label], QuizSession, results)
        self.assertFalse(QuizSession.objects.filter(pk=self.top.pk).exists())
        self.assertEqual(best_of(self.user, DAY), 20)

    def test_admin_locks_first_then_round_finishes(self):
        results = self.run_race(self.admin_delete_one, self.finish_round, "recount_best_free")

        self.assert_final_20(results, "first")

    def test_admin_bulk_locks_first_then_round_finishes(self):
        results = self.run_race(self.admin_delete_many, self.finish_round, "recount_best_free")

        self.assert_final_20(results, "first")

    def test_round_locks_first_then_admin_deletes(self):
        results = self.run_race(self.finish_round, self.admin_delete_one, "_bump_daily")

        self.assert_final_20(results, "second")

    def test_round_locks_first_then_admin_bulk_deletes(self):
        results = self.run_race(self.finish_round, self.admin_delete_many, "_bump_daily")

        self.assert_final_20(results, "second")
