"""관리자 회원 화면이 사진 바이트(avatar_photo)를 읽지 않는지, 저장해도 사진이 남는지 본다.

UserAdmin.get_queryset 이 avatar_photo 를 defer 한다. 막는 것 둘.

1. 목록·상세·검색·저장·비밀번호 바꾸기·"올린 사진 지우기" 가 SELECT 로 사진 칸을
   읽지 않는다. 읽으면 목록 한 쪽(100명)마다 사진 바이트를 통째로 가져온다.
2. defer 한 채로 저장해도 사진이 지워지거나 바뀌지 않는다. Django 는 읽은 칸만
   UPDATE 하는데, 그것이 깨지면 회원 정보를 고칠 때마다 사진이 사라진다.

SQL 에서 칸 이름은 따옴표째 찾는다. 따옴표 없이 찾으면 avatar_photo_key·
avatar_photo_at 도 걸린다.
"""

from __future__ import annotations

import re
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .admin import UserAdmin
from .models import AVATAR_PHOTO
from .tests import PASSWORD

User = get_user_model()

PHOTO = b"\x89PNG-fake-photo-bytes" * 500
PHOTO_COLUMN = re.compile(r'"avatar_photo"')


def photo_reads(queries, signed_in) -> list[str]:
    """사진 칸을 읽은 SELECT 문. UPDATE ... SET 은 쓰기라 뺀다.

    로그인한 관리자 자신의 행은 뺀다. 그것은 세션 인증(AuthenticationMiddleware)이
    요청마다 칸 제한 없이 읽는 것이라 UserAdmin 과 무관하다.
    """
    own = f'WHERE "accounts_user"."id" = {signed_in.pk} LIMIT 21'
    return [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith("SELECT")
        and PHOTO_COLUMN.search(q["sql"])
        and not q["sql"].rstrip().endswith(own)
    ]


def give_photo(user) -> None:
    User.objects.filter(pk=user.pk).update(
        avatar_photo=PHOTO,
        avatar_photo_key=uuid.uuid4(),
        avatar_photo_at=timezone.now(),
        avatar=AVATAR_PHOTO,
    )


def stored_photo(user) -> bytes | None:
    raw = User.objects.filter(pk=user.pk).values_list("avatar_photo", flat=True).get()
    return bytes(raw) if raw is not None else None


class UserAdminPhotoDeferTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password=PASSWORD, display_name="총괄"
        )
        cls.member = User.objects.create_user(
            email="member@example.com", password=PASSWORD, display_name="사진회원"
        )
        cls.other = User.objects.create_user(
            email="other@example.com", password=PASSWORD, display_name="다른회원"
        )
        give_photo(cls.member)
        give_photo(cls.other)

    def setUp(self):
        self.client.force_login(self.admin)

    def change_url(self, user) -> str:
        return reverse("admin:accounts_user_change", args=[user.pk])

    def capture(self, call):
        with CaptureQueriesContext(connection) as ctx:
            response = call()
        return response, ctx.captured_queries

    # ---- 읽기 ------------------------------------------------------------------

    def test_changelist_does_not_read_photo(self):
        response, queries = self.capture(
            lambda: self.client.get(reverse("admin:accounts_user_changelist"))
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "member@example.com")
        self.assertEqual(photo_reads(queries, self.admin), [])

    def test_changelist_search_and_filter_do_not_read_photo(self):
        for params in ({"q": "member"}, {"is_active__exact": "1"}, {"o": "1"}):
            with self.subTest(params):
                response, queries = self.capture(
                    lambda: self.client.get(reverse("admin:accounts_user_changelist"), params)
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(photo_reads(queries, self.admin), [])

    def test_change_view_does_not_read_photo(self):
        response, queries = self.capture(lambda: self.client.get(self.change_url(self.member)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(photo_reads(queries, self.admin), [])

    def test_password_change_view_does_not_read_photo(self):
        url = reverse("admin:auth_user_password_change", args=[self.member.pk])
        response, queries = self.capture(lambda: self.client.get(url))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(photo_reads(queries, self.admin), [])

    # ---- 저장 ------------------------------------------------------------------

    def edit_payload(self, user, **over) -> dict:
        """상세 화면의 폼 칸 그대로(읽기 전용 칸은 보내지 않는다)."""
        data = {
            "email": user.email,
            "display_name": user.display_name,
            "avatar": AVATAR_PHOTO,
            "google_picture": "",
            "daily_length": "",
            "is_active": "on",
        }
        data.update(over)
        return data

    def test_saving_change_form_keeps_photo_and_does_not_read_it(self):
        response, queries = self.capture(
            lambda: self.client.post(
                self.change_url(self.member),
                self.edit_payload(self.member, display_name="바뀐이름"),
            )
        )
        self.assertEqual(response.status_code, 302)

        self.member.refresh_from_db(fields=["display_name", "avatar", "avatar_photo_key"])
        self.assertEqual(self.member.display_name, "바뀐이름")
        self.assertEqual(stored_photo(self.member), PHOTO)
        self.assertEqual(self.member.avatar, AVATAR_PHOTO)
        self.assertIsNotNone(self.member.avatar_photo_key)
        self.assertEqual(photo_reads(queries, self.admin), [])
        # 쓰기 쪽도 사진 칸을 건드리지 않는다(같은 값으로 덮어써도 바이트를 다시 보낸다).
        writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("UPDATE")]
        self.assertTrue(writes)
        self.assertFalse([sql for sql in writes if PHOTO_COLUMN.search(sql)], writes)

    def test_changing_password_keeps_photo(self):
        url = reverse("admin:auth_user_password_change", args=[self.member.pk])
        new = PASSWORD + "-x"
        response, queries = self.capture(
            lambda: self.client.post(
                url, {"usable_password": "true", "password1": new, "password2": new}
            )
        )
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(new))
        self.assertEqual(stored_photo(self.member), PHOTO)
        self.assertEqual(photo_reads(queries, self.admin), [])

    # ---- 올린 사진 지우기 -------------------------------------------------------

    def test_delete_photo_action_clears_only_selected_and_does_not_read_photo(self):
        response, queries = self.capture(
            lambda: self.client.post(
                reverse("admin:accounts_user_changelist"),
                {"action": "delete_uploaded_photo", "_selected_action": [self.member.pk]},
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(stored_photo(self.member))
        self.member.refresh_from_db()
        self.assertIsNone(self.member.avatar_photo_key)
        self.assertEqual(self.member.avatar, "")
        # 고르지 않은 회원의 사진은 남는다.
        self.assertEqual(stored_photo(self.other), PHOTO)
        self.assertEqual(photo_reads(queries, self.admin), [])

    # ---- 가드가 정말 무는지 ----------------------------------------------------

    def test_detector_sees_photo_when_defer_is_removed(self):
        """defer 를 끄면 위 검사가 실제로 사진 칸 SELECT 를 잡는다(검사 자체의 확인)."""
        with mock.patch.object(UserAdmin, "get_queryset", BaseUserAdmin.get_queryset):
            _, listing = self.capture(
                lambda: self.client.get(reverse("admin:accounts_user_changelist"))
            )
            _, detail = self.capture(lambda: self.client.get(self.change_url(self.member)))
        self.assertTrue(photo_reads(listing, self.admin))
        self.assertTrue(photo_reads(detail, self.admin))
