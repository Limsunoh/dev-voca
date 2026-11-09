"""가입 동의.

약관·처리방침 동의와 만 14세 이상 확인은 이메일 가입과 구글 가입 둘 다
서버가 검사한다. 화면을 거치지 않고 API 를 바로 불러도 동의 없는 계정은
생기지 않아야 하고, 동의한 계정에는 시각과 문서 버전이 남아야 한다.
"""

from __future__ import annotations

import threading
import unittest
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from .google import GoogleAuthError
from .models import TERMS_VERSION

User = get_user_model()

SIGNUP_URL = "/api/accounts/signup/"
GOOGLE_URL = "/api/accounts/google/"
REDIRECT_URI = "http://localhost:3000/api/auth/google/callback"
PASSWORD = "devvoca-pass-8821"
CONSENT = {"terms_agreed": True, "age_confirmed": True}


class SignUpConsentTest(TestCase):
    def setUp(self):
        cache.clear()

    def signup(self, **body):
        payload = {"email": "a@example.com", "password": PASSWORD, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def test_both_agreed_records_time_and_version(self):
        before = timezone.now()

        res = self.signup(**CONSENT)

        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="a@example.com")
        self.assertGreaterEqual(user.terms_agreed_at, before)
        self.assertEqual(user.age_confirmed_at, user.terms_agreed_at)
        self.assertEqual(user.terms_version, TERMS_VERSION)

    def test_missing_or_off_is_rejected_and_makes_no_account(self):
        cases = {
            "둘 다 없음": ({}, "terms_agreed"),
            "약관만 없음": ({"age_confirmed": True}, "terms_agreed"),
            "나이만 없음": ({"terms_agreed": True}, "age_confirmed"),
            "약관 꺼짐": ({"terms_agreed": False, "age_confirmed": True}, "terms_agreed"),
            "나이 꺼짐": ({"terms_agreed": True, "age_confirmed": False}, "age_confirmed"),
            "약관 null": ({"terms_agreed": None, "age_confirmed": True}, "terms_agreed"),
            "약관 이상한 값": ({"terms_agreed": "글쎄", "age_confirmed": True}, "terms_agreed"),
        }
        for name, (body, field) in cases.items():
            with self.subTest(name):
                res = self.signup(**body)
                self.assertEqual(res.status_code, 400)
                self.assertIn(field, res.json())
                self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_messages_are_korean_not_framework_defaults(self):
        body = self.signup().json()

        self.assertEqual(body["terms_agreed"], ["이용약관과 개인정보 처리방침에 동의해주세요."])
        self.assertEqual(body["age_confirmed"], ["만 14세 이상만 가입할 수 있습니다."])

    def test_consent_fields_are_not_echoed_back(self):
        body = self.signup(**CONSENT).json()

        self.assertNotIn("terms_agreed", body["user"])
        self.assertNotIn("age_confirmed", body["user"])
        self.assertNotIn("terms_agreed_at", body["user"])


class GoogleConsentTest(TestCase):
    def setUp(self):
        cache.clear()

    def google(self, **body):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **body}
        return self.client.post(GOOGLE_URL, payload, content_type="application/json")

    def patch_google(self, email="new@example.com"):
        return mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={
                "email": email,
                "name": "구글사용자",
                "picture": "https://lh3.googleusercontent.com/a/first",
            },
        )

    def test_new_account_without_consent_is_not_created(self):
        cases = {
            "둘 다 없음": {},
            "약관만": {"terms_agreed": True},
            "나이만": {"age_confirmed": True},
            "약관 꺼짐": {"terms_agreed": False, "age_confirmed": True},
            # 문자열 "true" 는 화면이 보내는 값이 아니다. 참처럼 보여도 받지 않는다.
            "문자열": {"terms_agreed": "true", "age_confirmed": "true"},
        }
        for name, body in cases.items():
            with self.subTest(name), self.patch_google():
                res = self.google(**body)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json(), {"code": "consent_required"})
                self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_new_account_with_consent_records_time_and_version(self):
        before = timezone.now()

        with self.patch_google():
            res = self.google(**CONSENT)

        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="new@example.com")
        self.assertGreaterEqual(user.terms_agreed_at, before)
        self.assertEqual(user.age_confirmed_at, user.terms_agreed_at)
        self.assertEqual(user.terms_version, TERMS_VERSION)

    def test_existing_account_logs_in_without_consent(self):
        """로그인 화면의 구글 버튼에는 체크박스가 없다."""
        User.objects.create_user(email="old@example.com", password=PASSWORD)

        with self.patch_google("old@example.com"):
            res = self.google()

        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.json())

    def test_existing_account_consent_record_is_not_overwritten(self):
        """동의 시각은 처음 동의한 때의 기록이다. 다시 로그인했다고 바뀌면 안 된다."""
        first = timezone.now() - timedelta(days=30)
        User.objects.create_user(
            email="old@example.com",
            password=PASSWORD,
            terms_agreed_at=first,
            terms_version="v0",
            age_confirmed_at=first,
        )

        with self.patch_google("old@example.com"):
            res = self.google(**CONSENT)

        self.assertEqual(res.status_code, 200)
        user = User.objects.get(email="old@example.com")
        self.assertEqual(user.terms_agreed_at, first)
        self.assertEqual(user.terms_version, "v0")

    def test_inactive_account_stays_blocked_without_consent(self):
        User.objects.create_user(email="old@example.com", password=PASSWORD, is_active=False)

        with self.patch_google("old@example.com"):
            res = self.google()

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {"detail": "사용할 수 없는 계정입니다."})

    def test_name_failure_log_does_not_contain_the_email(self):
        """로그는 오래 남고 여러 곳으로 복사되니 이메일 원문을 적지 않는다."""
        with (
            self.patch_google(),
            mock.patch.object(User.objects, "get_or_create", side_effect=IntegrityError),
            self.assertLogs("apps.accounts.views", level="WARNING") as logs,
        ):
            res = self.google(**CONSENT)

        self.assertEqual(res.status_code, 400)
        self.assertNotIn("new@example.com", "\n".join(logs.output))
        self.assertNotIn("@", "\n".join(logs.output))


class SignUpConsentEdgeTest(TestCase):
    """이메일 가입에 동의 칸을 이상하게 보냈을 때."""

    def setUp(self):
        cache.clear()

    def signup(self, **body):
        payload = {"email": "a@example.com", "password": PASSWORD, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def test_falsy_or_malformed_values_are_400_not_500(self):
        """거짓이거나 불린으로 읽을 수 없는 값은 계정 없이 400 이다. 목록·객체도 500 이 아니다."""
        values = [False, 0, 0.0, "", " ", "0", "false", "False", "off", "no", "n",
                  None, 2, -1, 1.5, "글쎄", [], [True], {}, {"a": 1}]
        for value in values:
            for body in (
                {"terms_agreed": value, "age_confirmed": True},
                {"terms_agreed": True, "age_confirmed": value},
                {"terms_agreed": value, "age_confirmed": value},
            ):
                with self.subTest(body=body):
                    res = self.signup(**body)

                    self.assertEqual(res.status_code, 400, res.content)
                    self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_form_post_without_the_fields_is_rejected(self):
        """폼 인코딩은 빠진 칸을 false 로 읽는다. 거기서도 계정이 생기면 안 된다."""
        res = self.client.post(SIGNUP_URL, {"email": "a@example.com", "password": PASSWORD})

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["terms_agreed"], ["이용약관과 개인정보 처리방침에 동의해주세요."])
        self.assertEqual(res.json()["age_confirmed"], ["만 14세 이상만 가입할 수 있습니다."])
        self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_client_cannot_write_the_consent_record(self):
        """시각과 버전은 서버가 정한다. 본문에 실어 보내도 무시한다."""
        res = self.signup(
            **CONSENT,
            terms_agreed_at="2000-01-01T00:00:00Z",
            age_confirmed_at="2000-01-01T00:00:00Z",
            terms_version="forged",
        )

        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="a@example.com")
        self.assertEqual(user.terms_version, TERMS_VERSION)
        self.assertGreater(user.terms_agreed_at.year, 2000)
        self.assertGreater(user.age_confirmed_at.year, 2000)

    def test_forged_record_does_not_replace_missing_consent(self):
        res = self.signup(terms_agreed_at="2000-01-01T00:00:00Z", terms_version="v1")

        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_duplicate_signup_leaves_the_old_record_alone(self):
        first = timezone.now() - timedelta(days=30)
        User.objects.create_user(
            email="a@example.com",
            password=PASSWORD,
            terms_agreed_at=first,
            terms_version="v0",
            age_confirmed_at=first,
        )

        res = self.signup(**CONSENT)

        self.assertEqual(res.status_code, 400)
        user = User.objects.get(email="a@example.com")
        self.assertEqual(user.terms_agreed_at, first)
        self.assertEqual(user.age_confirmed_at, first)
        self.assertEqual(user.terms_version, "v0")

    def test_not_an_object_body_is_400(self):
        for raw in ("[1, 2]", '"문자열"', "1", "null"):
            with self.subTest(raw):
                res = self.client.post(SIGNUP_URL, raw, content_type="application/json")

                self.assertEqual(res.status_code, 400, res.content)


class GoogleConsentEdgeTest(TestCase):
    """구글 로그인의 동의 경계. 조금이라도 true 가 아니면 새 계정을 만들지 않는다."""

    def setUp(self):
        cache.clear()

    def google(self, **body):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **body}
        return self.client.post(GOOGLE_URL, payload, content_type="application/json")

    def patch_google(self, email="new@example.com", picture="https://lh3.googleusercontent.com/a/p"):
        return mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": "구글사용자", "picture": picture},
        )

    def test_only_the_literal_true_counts_for_a_new_account(self):
        values = [None, False, 0, 1, 2, "", "1", "on", "yes", "True", "true", [], [True], {}, {"a": 1}]
        for value in values:
            for body in (
                {"terms_agreed": value, "age_confirmed": True},
                {"terms_agreed": True, "age_confirmed": value},
            ):
                with self.subTest(body=body), self.patch_google():
                    res = self.google(**body)

                    self.assertEqual(res.status_code, 400, res.content)
                    self.assertEqual(res.json(), {"code": "consent_required"})
                    self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_form_encoded_consent_is_not_consent(self):
        """폼 인코딩은 값이 문자열로 온다. 화면이 보내는 모양이 아니다."""
        body = {"code": "c", "redirect_uri": REDIRECT_URI, "terms_agreed": "true", "age_confirmed": "true"}

        with self.patch_google():
            res = self.client.post(GOOGLE_URL, body)

        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.json(), {"code": "consent_required"})
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_client_cannot_write_the_consent_record(self):
        with self.patch_google():
            res = self.google(**CONSENT, terms_version="forged", terms_agreed_at="2000-01-01T00:00:00Z")

        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.terms_version, TERMS_VERSION)
        self.assertGreater(user.terms_agreed_at.year, 2000)

    def test_refused_attempt_issues_no_token(self):
        with self.patch_google():
            res = self.google()

        self.assertNotIn("token", res.json())
        self.assertEqual(User.objects.count(), 0)

    def test_google_error_is_not_reported_as_missing_consent(self):
        """구글 확인에 실패하면 그 안내가 먼저다. 동의가 없다고 가입 화면으로 보내면 원인이 가려진다."""
        with mock.patch(
            "apps.accounts.views.fetch_google_user", side_effect=GoogleAuthError("구글 확인 실패")
        ):
            res = self.google()

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {"detail": "구글 확인 실패"})

    def test_existing_account_matches_regardless_of_case(self):
        """구글이 대문자 섞어 준 주소도 기존 계정이다. 새 계정으로 보고 동의를 요구하면 안 된다."""
        User.objects.create_user(email="old@example.com", password=PASSWORD)

        with self.patch_google("Old@Example.COM"):
            res = self.google()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact="old@example.com").count(), 1)

    def test_existing_account_without_record_is_not_backfilled(self):
        """이 기능 전에 만든 계정. 체크 없이 들어온 로그인을 동의로 적어 넣으면 안 된다."""
        User.objects.create_user(email="old@example.com", password=PASSWORD)

        with self.patch_google("old@example.com"):
            self.google()
        with self.patch_google("old@example.com"):
            res = self.google(**CONSENT)

        self.assertEqual(res.status_code, 200)
        user = User.objects.get(email="old@example.com")
        self.assertIsNone(user.terms_agreed_at)
        self.assertIsNone(user.age_confirmed_at)
        self.assertEqual(user.terms_version, "")

    def test_existing_account_still_gets_its_picture_refreshed(self):
        User.objects.create_user(email="old@example.com", password=PASSWORD)

        with self.patch_google("old@example.com", picture="https://lh3.googleusercontent.com/a/new"):
            self.google()

        self.assertEqual(
            User.objects.get(email="old@example.com").google_picture,
            "https://lh3.googleusercontent.com/a/new",
        )

    def test_account_created_between_check_and_create_keeps_its_first_record(self):
        """있는지 본 뒤 만드는 사이에 다른 요청이 먼저 만든 경우. 그 사람의 기록을 안 덮는다."""
        first = timezone.now() - timedelta(days=1)

        def someone_else_got_there(wanted):
            User.objects.create_user(
                email="new@example.com",
                password=PASSWORD,
                terms_agreed_at=first,
                terms_version="v0",
                age_confirmed_at=first,
            )
            return "뒤늦은이름"

        with (
            self.patch_google(),
            mock.patch("apps.accounts.views.free_display_name", side_effect=someone_else_got_there),
        ):
            res = self.google(**CONSENT)

        self.assertEqual(res.status_code, 200)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.terms_agreed_at, first)
        self.assertEqual(user.terms_version, "v0")


class _KeepsCacheTable:
    """TransactionTestCase 의 flush 뒤에도 throttle_cache 표가 남게 한다."""

    def _fixture_teardown(self):
        super()._fixture_teardown()
        call_command("createcachetable", verbosity=0)


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class ConsentRaceTest(_KeepsCacheTable, TransactionTestCase):
    """같은 새 이메일로 동시에 들어온 요청. 실제 스레드와 행으로 겹친다.

    구글 확인이 끝난 자리에 Barrier 를 두어, 모든 요청이 "계정이 있나" 를 거의
    동시에 묻게 한다. 판마다 새 이메일을 쓴다.
    """

    ROUNDS = 8

    def setUp(self):
        cache.clear()

    def _race_google(self, email, bodies):
        barrier = threading.Barrier(len(bodies))

        def fake_google(code, redirect_uri):
            barrier.wait(timeout=20)
            return {"email": email, "name": "동시사용자", "picture": ""}

        results = [None] * len(bodies)

        def one(index, body):
            try:
                results[index] = Client().post(
                    GOOGLE_URL,
                    {"code": "c", "redirect_uri": REDIRECT_URI, **body},
                    content_type="application/json",
                )
            finally:
                connections.close_all()

        with mock.patch("apps.accounts.views.fetch_google_user", side_effect=fake_google):
            threads = [threading.Thread(target=one, args=(i, b)) for i, b in enumerate(bodies)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        return results

    def test_all_consented_makes_one_account(self):
        for n in range(self.ROUNDS):
            with self.subTest(round=n):
                email = f"race{n}@example.com"
                results = self._race_google(email, [CONSENT] * 5)

                codes = sorted(r.status_code for r in results)
                self.assertEqual(codes, [200, 200, 200, 200, 201], [r.content for r in results])
                user = User.objects.get(email=email)
                self.assertIsNotNone(user.terms_agreed_at)
                self.assertIsNotNone(user.age_confirmed_at)
                self.assertEqual(user.terms_version, TERMS_VERSION)

    def test_none_consented_makes_no_account(self):
        for n in range(self.ROUNDS):
            with self.subTest(round=n):
                email = f"none{n}@example.com"
                results = self._race_google(email, [{}] * 5)

                self.assertEqual([r.status_code for r in results], [400] * 5)
                self.assertFalse(User.objects.filter(email=email).exists())

    def test_mixed_never_makes_an_account_without_a_record(self):
        for n in range(self.ROUNDS):
            with self.subTest(round=n):
                email = f"mix{n}@example.com"
                bodies = [CONSENT, {}, CONSENT, {"terms_agreed": True}, {}]

                results = self._race_google(email, bodies)

                for body, res in zip(bodies, results):
                    self.assertLess(res.status_code, 500, res.content)
                    if body is CONSENT:
                        self.assertIn(res.status_code, (200, 201), res.content)
                    elif res.status_code == 400:
                        self.assertEqual(res.json(), {"code": "consent_required"})
                    else:
                        # 먼저 만들어진 뒤에 도착했으면 이미 있는 계정의 로그인이다.
                        self.assertEqual(res.status_code, 200, res.content)
                user = User.objects.get(email=email)
                self.assertIsNotNone(user.terms_agreed_at)
                self.assertEqual(sum(r.status_code == 201 for r in results), 1)

    def test_concurrent_email_signup_makes_one_account_with_a_record(self):
        barrier = threading.Barrier(4)
        results = [None] * 4

        def one(index):
            try:
                barrier.wait(timeout=20)
                results[index] = Client().post(
                    SIGNUP_URL,
                    {"email": "same@example.com", "password": PASSWORD, **CONSENT},
                    content_type="application/json",
                )
            finally:
                connections.close_all()

        threads = [threading.Thread(target=one, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(sorted(r.status_code for r in results), [201, 400, 400, 400])
        self.assertEqual(User.objects.get(email="same@example.com").terms_version, TERMS_VERSION)
