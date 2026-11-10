"""하루 공부량(daily_length).

일일공부가 이 길이로 바로 시작한다. 화면은 처음 들어올 때 한 번 묻고, 내정보에서
바꾼다. 둘 다 이름·아바타와 같은 PATCH /me 로 저장한다.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token

from .tests import ME_URL, PASSWORD

User = get_user_model()


class DailyLengthTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        cls.token = Token.objects.create(user=cls.user)

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def patch(self, body):
        return self.client.patch(ME_URL, body, content_type="application/json", **self.auth())

    def test_new_account_has_not_chosen(self):
        # 비어 있어야 화면이 "아직 안 골랐다" 를 알고 묻는다.
        res = self.client.get(ME_URL, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["daily_length"], "")

    def test_saves_each_length(self):
        for length in ("5m", "10m", "30m"):
            with self.subTest(length=length):
                res = self.patch({"daily_length": length})

                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["daily_length"], length)
                self.user.refresh_from_db()
                self.assertEqual(self.user.daily_length, length)

    def test_rejects_unknown_length(self):
        # 일일공부가 모르는 길이를 저장하면 그 길이로 시작할 때 막힌다.
        for bad in ("15m", "5", "10M", " 5m", "30m ", "60m"):
            with self.subTest(bad=bad):
                res = self.patch({"daily_length": bad})

                self.assertEqual(res.status_code, 400)
                self.assertIn("daily_length", res.json())

        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_length, "")

    def test_rejects_wrong_type(self):
        for bad in (10, None, ["5m"], {"value": "5m"}):
            with self.subTest(bad=bad):
                res = self.patch({"daily_length": bad})

                self.assertEqual(res.status_code, 400)

    def test_can_clear_back_to_unchosen(self):
        self.patch({"daily_length": "10m"})

        res = self.patch({"daily_length": ""})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["daily_length"], "")

    def test_other_fields_untouched(self):
        # 같은 PATCH 로 이름을 고치는 화면이 공부량을 지우지 않아야 한다.
        self.patch({"daily_length": "30m"})

        self.patch({"display_name": "새이름"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_length, "30m")

    def test_requires_login(self):
        res = self.client.patch(
            ME_URL, {"daily_length": "5m"}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 401)
