"""학습 기록 Admin(ViewOnlyAdmin)이 회원 사진 바이트를 읽지 않는지 본다.

list_select_related = ("user",) 가 회원 행을 칸 제한 없이 붙여, 목록 한 쪽마다 회원
사진(avatar_photo)까지 읽었다. ViewOnlyAdmin.get_queryset 이 user__avatar_photo 를
defer 한다.

막는 것.
1. 네 표(판·하루 점수·일일공부·복습)의 목록·검색·날짜 거르기가 사진 칸을 SELECT 하지
   않는다.
2. 판 지우기(상세의 삭제 화면, 목록의 일괄 삭제)가 그대로 되고, 회원 사진은 남는다.

SQL 의 칸 이름은 따옴표째 찾는다(avatar_photo_key·avatar_photo_at 과 구분).
로그인한 관리자 자신의 행은 세션 인증이 읽는 것이라 뺀다.
"""

from __future__ import annotations

import re
import uuid
from unittest import mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .admin import ViewOnlyAdmin
from .models import DailyScore, DailyStudy, QuizSession, ReviewState, StudyLength
from .tests_admin import DAY, kst, make_user, play

PHOTO = b"\x89PNG-fake-photo-bytes" * 500
PHOTO_COLUMN = re.compile(r'"accounts_user"\."avatar_photo"')
TABLES = ("quizsession", "dailyscore", "dailystudy", "reviewstate")


def stored_photo(user) -> bytes | None:
    raw = get_user_model().objects.filter(pk=user.pk).values_list("avatar_photo", flat=True).get()
    return bytes(raw) if raw is not None else None


class ViewOnlyAdminPhotoDeferTest(TestCase):
    def setUp(self):
        self.admin = make_user("관리자", is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)
        self.user = make_user("학생")
        get_user_model().objects.filter(pk=self.user.pk).update(
            avatar_photo=PHOTO, avatar_photo_key=uuid.uuid4(), avatar_photo_at=timezone.now()
        )
        self.session = play(self.user, kst(DAY, 9), 12)
        self.second = play(self.user, kst(DAY, 10), 8)
        DailyStudy.objects.create(
            user=self.user, day=DAY, length=StudyLength.SHORT, total_questions=10
        )
        ReviewState.objects.create(user=self.user, target_type="word", target_id=1, is_wrong=True)

    def photo_reads(self, queries) -> list[str]:
        own = f'WHERE "accounts_user"."id" = {self.admin.pk} LIMIT 21'
        return [
            q["sql"]
            for q in queries
            if q["sql"].lstrip().upper().startswith("SELECT")
            and PHOTO_COLUMN.search(q["sql"])
            and not q["sql"].rstrip().endswith(own)
        ]

    def get(self, url, params=None):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params or {})
        return response, ctx.captured_queries

    def test_changelists_do_not_read_member_photo(self):
        for name in TABLES:
            for params in ({}, {"q": "학생@example"}, {"o": "-1"}):
                with self.subTest(name, **params):
                    response, queries = self.get(
                        reverse(f"admin:learning_{name}_changelist"), params
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "학생@example.com")
                    self.assertEqual(self.photo_reads(queries), [])

    def test_date_drilldown_does_not_read_member_photo(self):
        for name in ("quizsession", "dailyscore", "dailystudy"):
            field = "finished_at" if name == "quizsession" else "day"
            params = {f"{field}__year": DAY.year, f"{field}__month": DAY.month}
            with self.subTest(name):
                response, queries = self.get(reverse(f"admin:learning_{name}_changelist"), params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.photo_reads(queries), [])

    def test_change_views_open_without_reading_member_photo(self):
        rows = {
            "quizsession": self.session,
            "dailyscore": DailyScore.objects.get(user=self.user, day=DAY),
            "dailystudy": DailyStudy.objects.get(user=self.user, day=DAY),
            "reviewstate": ReviewState.objects.get(user=self.user),
        }
        for name, row in rows.items():
            with self.subTest(name):
                response, queries = self.get(reverse(f"admin:learning_{name}_change", args=[row.pk]))
                self.assertEqual(response.status_code, 200)
                # 읽기 전용 user 칸이 회원 행을 따로 읽으면 사진까지 읽는다.
                # get_queryset 의 select_related("user") 가 막는다.
                self.assertEqual(self.photo_reads(queries), [])

    def test_deleting_a_round_keeps_member_photo(self):
        url = reverse("admin:learning_quizsession_delete", args=[self.session.pk])
        confirm, _ = self.get(url)
        self.assertEqual(confirm.status_code, 200)

        response = self.client.post(url, {"post": "yes"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizSession.objects.filter(pk=self.session.pk).exists())
        self.assertEqual(DailyScore.objects.get(user=self.user, day=DAY).best_free_score, 8)
        self.assertEqual(stored_photo(self.user), PHOTO)

    def test_bulk_delete_of_rounds_works_and_keeps_member_photo(self):
        listing = reverse("admin:learning_quizsession_changelist")
        selected = [self.session.pk, self.second.pk]
        with CaptureQueriesContext(connection) as ctx:
            confirm = self.client.post(
                listing, {"action": "delete_selected", "_selected_action": selected}
            )
            done = self.client.post(
                listing,
                {"action": "delete_selected", "_selected_action": selected, "post": "yes"},
            )

        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(done.status_code, 302)
        self.assertFalse(QuizSession.objects.filter(pk__in=selected).exists())
        self.assertEqual(stored_photo(self.user), PHOTO)
        self.assertEqual(self.photo_reads(ctx.captured_queries), [])

    def test_detector_sees_photo_when_defer_is_removed(self):
        """defer 를 끄면 위 검사가 실제로 사진 칸 SELECT 를 잡는다(검사 자체의 확인)."""
        with mock.patch.object(ViewOnlyAdmin, "get_queryset", admin.ModelAdmin.get_queryset):
            for name in TABLES:
                with self.subTest(name):
                    _, queries = self.get(reverse(f"admin:learning_{name}_changelist"))
                    self.assertTrue(self.photo_reads(queries))
