"""11-24 점검에서 막은 것 셋.

- 기기 쿠키 없는 Admin 로그인 시도 전체 상한(AdminLoginTotalThrottle)
- 닮은 글자(U+017F)가 든 이메일로 가입 막기(ensure_plain_email). 이메일 변경·구글
  로그인과 다른 글자들은 tests_audit_hardening_dynamic.py 가 본다.
- 비밀번호·이메일이 바뀌면 어느 길로 바꿨든 로그인 토큰을 모두 끊기(User.save)

비율은 get_rate 를 바꿔 좁힌다(tests_ip_throttle.py 머리말). 비밀번호는 리터럴로 두지
않는다(tests.py 의 PASSWORD 주석).
"""

from __future__ import annotations

import secrets
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase

from .models import LoginToken
from .throttles import AdminLoginThrottle, AdminLoginTotalThrottle

User = get_user_model()

PASSWORD = secrets.token_urlsafe(16)
OTHER_PASSWORD = secrets.token_urlsafe(16)

SIGNUP = "/api/accounts/signup/"
CONSENT = {"terms_agreed": True, "disclosure_agreed": True, "age_confirmed": True}

# 닮은 글자. 소스에 그대로 적으면 눈으로 구분이 안 된다.
LONG_S = chr(0x17F)  # PostgreSQL UPPER 에서 S
FULL_WIDTH_B = chr(0xFF42)


def _narrow(test: TestCase, throttle_class, rate: str) -> None:
    patcher = mock.patch.object(throttle_class, "get_rate", return_value=rate)
    patcher.start()
    test.addCleanup(patcher.stop)


class AdminLoginTotalLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        _narrow(self, AdminLoginTotalThrottle, "3/hour")
        User.objects.create_superuser(email="boss@example.com", password=PASSWORD)

    def _post(self, client: Client, email: str, password: str = "wrong"):
        return client.post("/admin/login/", {"username": email, "password": password})

    def test_blocked_try_does_not_leave_an_email_counter(self):
        """전체 통에 막힌 요청은 이메일 통까지 가지 않는다. 행이 쌓이지 않아야 막는 의미가 있다."""
        for n in range(3):
            self._post(self.client, f"user{n}@example.com")
        with mock.patch.object(AdminLoginThrottle, "allow_request") as email_bucket:
            self.assertEqual(self._post(self.client, "fresh@example.com").status_code, 429)
        email_bucket.assert_not_called()

    def test_browser_that_logged_in_before_is_not_blocked(self):
        # logout() 은 쿠키를 모두 비워 기기 쿠키까지 사라진다. 로그인한 채로 다시 낸다.
        known = Client()
        self.assertEqual(self._post(known, "boss@example.com", PASSWORD).status_code, 302)

        stranger = Client()
        for n in range(3):
            self._post(stranger, f"user{n}@example.com")
        self.assertEqual(self._post(stranger, "boss@example.com", PASSWORD).status_code, 429)

        self.assertNotEqual(self._post(known, "boss@example.com", PASSWORD).status_code, 429)

    def test_page_view_is_not_counted(self):
        for _ in range(5):
            self.assertEqual(self.client.get("/admin/login/").status_code, 200)
        self.assertEqual(self._post(self.client, "boss@example.com", PASSWORD).status_code, 302)


class PlainEmailTest(TestCase):
    def setUp(self):
        cache.clear()

    def _signup(self, email: str):
        return self.client.post(
            SIGNUP,
            {"email": email, "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

    def test_full_width_letters_are_refused_too(self):
        """전각 글자는 Django 의 이메일 검사기가 먼저 막는다. 어느 쪽이든 계정이 안 생기면 된다."""
        self.assertEqual(self._signup(f"{FULL_WIDTH_B}oss@example.com").status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_real_owner_can_still_sign_up(self):
        self._signup(f"bo{LONG_S}s@example.com")
        self.assertEqual(self._signup("boss@example.com").status_code, 201)


class CredentialChangeEndsLoginsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com", password=PASSWORD)
        LoginToken.objects.create(user=self.user)
        LoginToken.objects.create(user=self.user)

    def _tokens(self) -> int:
        return LoginToken.objects.filter(user=self.user).count()

    def _fresh(self):
        return User.objects.get(pk=self.user.pk)

    def test_new_password_ends_all_logins(self):
        user = self._fresh()
        user.set_password(OTHER_PASSWORD)
        user.save()
        self.assertEqual(self._tokens(), 0)

    def test_turning_off_password_login_ends_all_logins(self):
        user = self._fresh()
        user.set_unusable_password()
        user.save()
        self.assertEqual(self._tokens(), 0)

    def test_new_email_ends_all_logins(self):
        user = self._fresh()
        user.email = "other@example.com"
        user.save()
        self.assertEqual(self._tokens(), 0)

    def test_same_email_in_other_case_is_not_a_change(self):
        user = self._fresh()
        user.email = "ME@example.com"
        user.save()
        self.assertEqual(self._tokens(), 2)

    def test_other_fields_keep_logins(self):
        user = self._fresh()
        user.display_name = "새이름"
        user.save()
        self.assertEqual(self._tokens(), 2)

    def test_row_read_without_email_keeps_logins(self):
        user = User.objects.only("id", "display_name").get(pk=self.user.pk)
        user.display_name = "새이름"
        user.save(update_fields=["display_name"])
        self.assertEqual(self._tokens(), 2)

    def test_refreshing_other_fields_keeps_an_unsaved_email_change(self):
        """다른 칸만 다시 읽어도 메모리에서 바꾼 이메일은 바뀐 것으로 남는다."""
        user = self._fresh()
        user.email = "moved@example.com"
        user.refresh_from_db(fields=["display_name"])
        user.save()
        self.assertEqual(self._tokens(), 0)

    def test_new_email_on_a_row_read_without_email_ends_logins(self):
        user = User.objects.defer("email").get(pk=self.user.pk)
        user.email = "moved@example.com"
        user.save()
        self.assertEqual(self._tokens(), 0)

    def test_row_read_without_email_saved_unchanged_keeps_logins(self):
        user = User.objects.defer("email").get(pk=self.user.pk)
        user.display_name = "새이름"
        user.save()
        self.assertEqual(self._tokens(), 2)

    def test_second_save_after_change_does_not_end_new_login(self):
        user = self._fresh()
        user.email = "other@example.com"
        user.save()
        LoginToken.objects.create(user=self.user)
        user.display_name = "새이름"
        user.save()
        self.assertEqual(self._tokens(), 1)


class AdminPasswordScreenTest(TestCase):
    """Admin 비밀번호 화면에서 새 비밀번호를 정하는 길. "비밀번호 로그인 끄기" 는
    tests_audit_hardening_dynamic.py 의 AdminDisablePasswordTest 가 본다."""

    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com", password=PASSWORD)
        LoginToken.objects.create(user=self.user)
        User.objects.create_superuser(email="boss@example.com", password=OTHER_PASSWORD)
        self.client.login(username="boss@example.com", password=OTHER_PASSWORD)
        self.url = f"/admin/accounts/user/{self.user.pk}/password/"

    def test_new_password_ends_logins(self):
        new = secrets.token_urlsafe(16)
        response = self.client.post(
            self.url, {"usable_password": "true", "password1": new, "password2": new}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 0)
