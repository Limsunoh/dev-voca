"""일일공부 상태(GET /api/learning/daily/)에 하루 공부량이 같이 실린다.

화면은 이 값을 보고 고르는 단계 없이 바로 시작한다. /me 를 따로 묻지 않게
여기 싣는 것이라, 빠지면 저장해 둔 길이가 있어도 매번 고르는 화면이 뜬다.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token

User = get_user_model()

PASSWORD = secrets.token_urlsafe(16)
DAILY_URL = "/api/learning/daily/"


class DailyStatusCarriesLengthTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="d@example.com", password=PASSWORD)
        cls.token = Token.objects.create(user=cls.user)

    def status(self):
        res = self.client.get(DAILY_URL, HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_empty_until_chosen(self):
        self.assertEqual(self.status()["daily_length"], "")

    def test_reports_saved_length(self):
        User.objects.filter(pk=self.user.pk).update(daily_length="30m")

        self.assertEqual(self.status()["daily_length"], "30m")
