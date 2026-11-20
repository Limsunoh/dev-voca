"""관리자 로그인 횟수 제한, 이메일당 시간 상한, 사진 형식 제한, API 권한 기본값.

비율은 get_rate 를 바꿔 좁힌다(tests_ip_throttle.py 머리말).
"""

from __future__ import annotations

import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from PIL import Image
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from .models import AvatarPhotoError, shrink_avatar_photo
from .throttles import AdminLoginThrottle, EmailHourlyThrottle, LoginIpThrottle

User = get_user_model()


class _Fake:
    """get_cache_key 가 보는 request.data 만 있는 요청."""

    def __init__(self, data):
        self.data = data


def _narrow(test: TestCase, throttle_class, rate: str) -> None:
    patcher = mock.patch.object(throttle_class, "get_rate", return_value=rate)
    patcher.start()
    test.addCleanup(patcher.stop)


class AdminLoginLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        _narrow(self, AdminLoginThrottle, "2/hour")
        User.objects.create_superuser(email="boss@example.com", password="right-pass-123")

    def _post(self, email: str, password: str = "wrong"):
        return self.client.post("/admin/login/", {"username": email, "password": password})

    def test_third_try_with_same_email_is_blocked(self):
        self.assertEqual(self._post("boss@example.com").status_code, 200)
        self.assertEqual(self._post("BOSS@example.com ").status_code, 200)
        blocked = self._post("boss@example.com", "right-pass-123")
        self.assertEqual(blocked.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lookalike_letters_count_as_the_same_email(self):
        """Admin 폼은 전각 글자를 보통 글자로, DB 는 "ſ" 를 "S" 로 본다. 같은 계정이면 같은 통이다."""
        self._post("\uff42oss@example.com")
        self._post("bo\u017fs@example.com")
        blocked = self._post("boss@example.com", "right-pass-123")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_other_email_and_page_view_are_not_counted(self):
        self._post("boss@example.com")
        self._post("boss@example.com")
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)
        self.assertEqual(self._post("someone@example.com").status_code, 200)

    def test_right_password_still_logs_in_under_limit(self):
        response = self._post("boss@example.com", "right-pass-123")
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)


class LoginHourlyLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        _narrow(self, EmailHourlyThrottle, "2/hour")

    def test_third_login_try_in_an_hour_is_blocked(self):
        body = {"email": "a@example.com", "password": "nope-nope-1"}
        codes = [self.client.post("/api/accounts/login/", body).status_code for _ in range(3)]
        self.assertEqual(codes, [400, 400, 429])

    def test_lookalike_letters_count_as_the_same_email(self):
        User.objects.create_user(email="boss@example.com", password="right-pass-123")
        for email in ("bo\u017fs@example.com", "BOSS@example.com"):
            self.client.post("/api/accounts/login/", {"email": email, "password": "x"})
        res = self.client.post(
            "/api/accounts/login/", {"email": "boss@example.com", "password": "right-pass-123"}
        )
        self.assertEqual(res.status_code, 429)

    def test_request_stopped_by_ip_limit_does_not_fill_email_count(self):
        """IP 제한에 막힌 요청이 이메일 횟수를 채우면, 남이 그 계정을 싸게 잠근다."""
        _narrow(self, LoginIpThrottle, "1/hour")
        body = {"email": "a@example.com", "password": "nope-nope-1"}
        codes = [self.client.post("/api/accounts/login/", body).status_code for _ in range(3)]
        self.assertEqual(codes, [400, 429, 429])
        self.assertEqual(len(cache.get(EmailHourlyThrottle().get_cache_key(_Fake(body), None))), 1)


def _image_bytes(fmt: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 20, 30)).save(out, format=fmt)
    return out.getvalue()


class AvatarFormatTest(SimpleTestCase):
    def test_phone_formats_pass(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                self.assertTrue(shrink_avatar_photo(_image_bytes(fmt)))

    def test_camera_jpeg_with_extra_pictures_passes(self):
        """폰 카메라 JPEG 는 사진 여러 장을 묶은 MPO 로 열리기도 한다. JPEG 로 받아야 한다."""
        out = io.BytesIO()
        first = Image.new("RGB", (64, 64), (1, 2, 3))
        first.save(out, format="MPO", save_all=True, append_images=[Image.new("RGB", (64, 64))])
        self.assertTrue(shrink_avatar_photo(out.getvalue()))

    def test_other_formats_are_refused(self):
        for fmt in ("GIF", "BMP", "TIFF"):
            with self.subTest(fmt=fmt), self.assertRaisesMessage(AvatarPhotoError, "JPG, PNG, WEBP"):
                shrink_avatar_photo(_image_bytes(fmt))


class DefaultPermissionTest(SimpleTestCase):
    def test_view_without_permission_classes_needs_login(self):
        class Forgot(APIView):
            def get(self, request):
                return Response({"ok": True})

        response = Forgot.as_view()(APIRequestFactory().get("/x/"))
        self.assertEqual(response.status_code, 401)
