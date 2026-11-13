"""하루 공부량(daily_length)의 경계와 남용.

tests_daily_length.py 가 PATCH /me 의 기본 계약을 본다. 여기서는 그 밖의
자리를 본다.

    - 가입·로그인 응답에 칸이 실리는가. 프론트는 로그인 응답의 user 를 보고
      게스트가 고른 값을 옮길지 정한다(carryGuestDailyLength). 칸이 빠지면
      "옛 백엔드" 로 읽혀 옮기지 않는다.
    - 이 칸을 모르는 INSERT(배포가 엇갈린 옛 서버)가 db_default 로 살아남는가
    - 이상한 입력이 500 이 아니라 400 인가, 읽기 전용 칸을 같이 실어도 새지 않는가
    - 일일공부: 저장한 길이와 다른 길이로 시작해도("오늘만 다른 길이로")
      저장값이 안 바뀌는가, 저장해 둔 길이로 시작한 판에도 검수 안 된 단어가
      안 새는가
    - Admin 사용자 화면이 새 칸과 함께 열리는가
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase

from apps.accounts.models import LoginToken
from apps.learning.models import DailyStudy
from apps.learning.tests_daily_study import START_URL, seed_words
from apps.vocab.models import Word

from .tests import CONSENT, LOGIN_URL, ME_URL, PASSWORD, SIGNUP_URL

User = get_user_model()


class AuthResponseCarriesLengthTest(TestCase):
    """가입·로그인 응답의 user 에 daily_length 가 있다."""

    def setUp(self):
        cache.clear()

    def test_signup_response_has_empty_length(self):
        res = self.client.post(
            SIGNUP_URL,
            {"email": "new@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["user"]["daily_length"], "")

    def test_login_response_reports_saved_length(self):
        User.objects.create_user(email="old@example.com", password=PASSWORD, daily_length="30m")

        res = self.client.post(
            LOGIN_URL,
            {"email": "old@example.com", "password": PASSWORD},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["user"]["daily_length"], "30m")


class DbDefaultTest(TestCase):
    def test_insert_without_column_gets_empty_string(self):
        """이 칸을 모르는 옛 서버의 INSERT 도 NOT NULL 에 안 걸린다."""
        table = User._meta.db_table
        # 옛 서버가 넣는 칸만 골라 넣는다. 필수 칸이 늘어도 이 테스트가
        # 따라가도록, 모델에서 daily_length 를 뺀 실제 컬럼 목록으로 만든다.
        template = User(email="legacy@example.com")
        template.set_password(PASSWORD)
        fields = [
            f
            for f in User._meta.concrete_fields
            if not f.primary_key and f.attname != "daily_length"
        ]
        values = [f.get_db_prep_save(f.pre_save(template, True), connection) for f in fields]
        cols = ", ".join(connection.ops.quote_name(f.column) for f in fields)
        marks = ", ".join(["%s"] * len(fields))
        with connection.cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", values)

        self.assertEqual(User.objects.get(email="legacy@example.com").daily_length, "")


class PatchAbuseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="p@example.com", password=PASSWORD)
        cls.token = LoginToken.objects.create(user=cls.user)

    def patch(self, body, content_type="application/json"):
        return self.client.patch(
            ME_URL, body, content_type=content_type, HTTP_AUTHORIZATION=f"Token {self.token.key}"
        )

    def test_very_long_value_is_400(self):
        res = self.patch({"daily_length": "5m" * 5000})

        self.assertEqual(res.status_code, 400)

    def test_choice_label_instead_of_value_is_400(self):
        for bad in ("5분", "SHORT", "short", "5m\x00", "true", 5.0, True):
            with self.subTest(bad=bad):
                self.assertEqual(self.patch({"daily_length": bad}).status_code, 400)

    def test_form_encoded_body_is_not_500(self):
        res = self.patch("daily_length=10m", content_type="application/x-www-form-urlencoded")

        self.assertIn(res.status_code, (200, 400, 415))
        self.assertLess(res.status_code, 500)

    def test_readonly_fields_ride_along_but_do_not_change(self):
        res = self.patch({"daily_length": "10m", "is_staff": True, "email": "x@example.com"})

        self.user.refresh_from_db()
        self.assertLess(res.status_code, 500)
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.email, "p@example.com")

    def test_dead_token_is_401(self):
        res = self.client.patch(
            ME_URL,
            {"daily_length": "5m"},
            content_type="application/json",
            HTTP_AUTHORIZATION="Token " + "0" * 40,
        )

        self.assertEqual(res.status_code, 401)


class DailyStartWithSavedLengthTest(TestCase):
    """일일공부 시작과 하루 공부량의 관계."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = User.objects.create_user(
            email="s@example.com", password=PASSWORD, daily_length="30m"
        )
        self.client.force_login(self.user)

    def test_other_length_for_today_keeps_saved_value(self):
        """'오늘만 다른 길이로' 고른 판이 저장값을 덮지 않는다."""
        res = self.client.post(START_URL, {"length": "5m"}, "application/json")

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(DailyStudy.objects.get(user=self.user).length, "5m")
        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_length, "30m")
        self.assertEqual(self.client.get(START_URL).json()["daily_length"], "30m")

    def test_status_requires_login(self):
        self.client.logout()

        self.assertEqual(self.client.get(START_URL).status_code, 401)

    def test_saved_length_start_does_not_leak_unreviewed_words(self):
        """저장한 길이로 바로 시작한 판에도 검수 안 된 단어가 카드·보기로 안 나간다."""
        # 검수 안 된 단어를 검수된 것(120개)보다 훨씬 많이 둔다. 하나만 두면
        # 필터가 빠져도 우연히 안 뽑혀 통과한다.
        Word.objects.bulk_create(
            Word(term=f"unrevzzz{i}", meaning="숨김", description="숨김 설명", is_reviewed=False)
            for i in range(400)
        )
        hidden = set(Word.objects.filter(is_reviewed=False).values_list("id", flat=True))
        saved = self.client.get(START_URL).json()["daily_length"]

        res = self.client.post(START_URL, {"length": saved}, "application/json")

        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        card_ids = {c["id"] for c in body["learning"]}
        self.assertTrue(card_ids, "학습 카드가 없어 검사가 비었다")
        self.assertFalse(card_ids & hidden)
        self.assertNotIn("unrevzzz", res.content.decode())


class AdminShowsLengthTest(TestCase):
    def test_change_page_renders_with_field(self):
        admin = User.objects.create_superuser(email="adm@example.com", password=PASSWORD)
        target = User.objects.create_user(
            email="t@example.com", password=PASSWORD, daily_length="10m"
        )
        self.client.force_login(admin)

        res = self.client.get(f"/admin/accounts/user/{target.pk}/change/")

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'name="daily_length"')
