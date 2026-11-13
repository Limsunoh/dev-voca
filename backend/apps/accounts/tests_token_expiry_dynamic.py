"""처리방침 v4 와 rest_framework.authtoken 을 뺀 뒤를 깨뜨려 보는 테스트.

  - 가입(이메일·구글)하면 동의 기록의 버전이 화면 문서(LegalDoc.tsx 의 DOC_VERSION)와 같다.
  - authtoken 앱이 없어도 rest_framework.authtoken 을 부르는 곳이 없고, 그 관리자 화면은 404 다.
  - 운영 DB 처럼 빈 authtoken_token 표가 남아 있어도 탈퇴·관리자 삭제·1년 파기가 된다.
"""

from __future__ import annotations

import re
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import LoginToken

from .tests import CONSENT, GOOGLE_URL, ME_URL, PASSWORD, REDIRECT_URI, SIGNUP_URL

User = get_user_model()

# import 문만 본다. 주석·문서에 이름이 나오는 것은 괜찮다.
IMPORTS_AUTHTOKEN = re.compile(r"^\s*(from|import) rest_framework\.authtoken", re.M)

LEGAL_DOC = Path(settings.BASE_DIR).parent / "frontend" / "src" / "components" / "LegalDoc.tsx"


def doc_version() -> str:
    found = re.search(r'^export const DOC_VERSION = "([^"]+)";', LEGAL_DOC.read_text("utf-8"), re.M)
    assert found, "LegalDoc.tsx 에서 DOC_VERSION 을 못 찾았다"
    return found.group(1)


class SignUpRecordsShownVersionTest(TestCase):
    """가입 때 저장한 버전이 그때 화면에 보인 문서 버전과 같다."""

    def setUp(self):
        cache.clear()

    def test_이메일_가입은_화면_문서_버전으로_동의를_남긴다(self):
        res = self.client.post(
            SIGNUP_URL,
            {"email": "fresh@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="fresh@example.com")
        self.assertEqual(user.terms_version, doc_version())
        self.assertIsNotNone(user.terms_agreed_at)

    def test_구글_첫_가입도_화면_문서_버전으로_동의를_남긴다(self):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "g@example.com", "name": "구글", "picture": ""},
        ):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "leakmark-code", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="g@example.com").terms_version, doc_version())


class AuthtokenGoneTest(TestCase):
    """rest_framework.authtoken 이 INSTALLED_APPS 에 없다."""

    def test_앱이_빠졌고_코드가_그_모듈을_부르지_않는다(self):
        self.assertFalse(django_apps.is_installed("rest_framework.authtoken"))
        backend = Path(settings.BASE_DIR)
        users = [
            str(path.relative_to(backend))
            for path in (backend / "apps").rglob("*.py")
            if IMPORTS_AUTHTOKEN.search(path.read_text("utf-8"))
        ]
        self.assertEqual(users, [])

    def test_관리자_토큰_화면은_404(self):
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(admin)

        for url in ("/admin/authtoken/tokenproxy/", "/admin/authtoken/token/", "/admin/authtoken/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class LeftoverAuthtokenTableTest(TestCase):
    """운영 DB 처럼 빈 authtoken_token 표가 회원을 가리키는 외래 키와 함께 남아 있을 때."""

    def setUp(self):
        cache.clear()
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS authtoken_token ("
                '"key" varchar(40) PRIMARY KEY, created timestamptz NOT NULL, '
                "user_id bigint NOT NULL UNIQUE REFERENCES accounts_user(id) "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.key = LoginToken.objects.create(user=self.owner).key

    def assert_gone(self):
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
        self.assertEqual(LoginToken.objects.filter(user_id=self.owner.pk).count(), 0)

    def test_탈퇴가_된다(self):
        res = self.client.delete(
            ME_URL,
            {"current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.key}",
        )

        self.assertEqual(res.status_code, 204)
        self.assert_gone()

    def test_관리자_화면에서_지울_수_있다(self):
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(admin)

        res = self.client.post(f"/admin/accounts/user/{self.owner.pk}/delete/", {"post": "yes"})

        self.assertEqual(res.status_code, 302)
        self.assert_gone()

    def test_1년_미접속_파기가_된다(self):
        User.objects.filter(pk=self.owner.pk).update(
            last_seen_on=timezone.localdate() - timedelta(days=400),
            purge_notice_sent_at=timezone.now() - timedelta(days=40),
        )

        with mock.patch("apps.accounts.purge._really_sends", return_value=True), mock.patch(
            "apps.accounts.mail._really_sends", return_value=True
        ):
            out = StringIO()
            call_command("daily_cleanup", "--apply", stdout=out)

        self.assertIn("삭제 1명", out.getvalue())
        self.assert_gone()
