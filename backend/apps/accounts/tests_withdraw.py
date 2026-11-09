"""계정 삭제(MeView.delete)와 삭제 뒤에 남는 것."""

import json
import threading
import unittest
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, connections, models
from django.db.models.deletion import Collector
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.learning import record
from apps.learning.models import DailyScore, QuizAnswer, QuizSession, ReviewState

from .serializers import UserSerializer
from .tests import CONSENT, PASSWORD
from .tests_consent import _KeepsCacheTable
from .throttles import PasswordChangeThrottle

User = get_user_model()

ME_URL = "/api/accounts/me/"
SIGNUP_URL = "/api/accounts/signup/"
WRONG_PASSWORD = PASSWORD + "x"


class WithdrawTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def delete(self, user, body):
        token, _ = Token.objects.get_or_create(user=user)
        return self.client.delete(
            ME_URL,
            body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

    def assertGone(self, user):
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def assertKept(self, user):
        self.assertTrue(User.objects.filter(pk=user.pk).exists())


class PasswordAccountTest(WithdrawTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def test_right_password_deletes(self):
        res = self.delete(self.user, {"current_password": PASSWORD})

        self.assertEqual(res.status_code, 204)
        self.assertGone(self.user)

    def test_staff_cannot_delete_here(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True)

        res = self.delete(self.user, {"current_password": PASSWORD})

        self.assertEqual(res.status_code, 403)
        self.assertKept(self.user)

    def test_superuser_without_staff_flag_cannot_delete_here(self):
        User.objects.filter(pk=self.user.pk).update(is_superuser=True)

        res = self.delete(self.user, {"current_password": PASSWORD})

        self.assertEqual(res.status_code, 403)
        self.assertKept(self.user)

    def test_wrong_password_keeps_account_and_names_the_field(self):
        res = self.delete(self.user, {"current_password": WRONG_PASSWORD})

        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.json())
        self.assertKept(self.user)

    def test_email_is_not_enough_when_account_has_password(self):
        res = self.delete(self.user, {"email": "a@example.com"})

        self.assertEqual(res.status_code, 400)
        self.assertKept(self.user)

    def test_odd_bodies_are_refused_not_crashed(self):
        for body in (
            {},
            [],
            {"current_password": 1},
            {"current_password": [PASSWORD]},
            {"current_password": "\ud800"},
        ):
            with self.subTest(body=body):
                self.assertEqual(self.delete(self.user, body).status_code, 400)
        self.assertKept(self.user)

    def test_login_is_required(self):
        res = self.client.delete(
            ME_URL, {"current_password": PASSWORD}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 401)
        self.assertKept(self.user)

    def test_old_token_stops_working(self):
        token = Token.objects.create(user=self.user)
        self.delete(self.user, {"current_password": PASSWORD})

        res = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(res.status_code, 401)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_same_email_can_sign_up_again_as_a_new_account(self):
        old_pk = self.user.pk
        self.delete(self.user, {"current_password": PASSWORD})

        res = self.client.post(
            SIGNUP_URL,
            {"email": "a@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 201)
        self.assertNotEqual(res.json()["user"]["id"], old_pk)


class GoogleOnlyAccountTest(WithdrawTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="g@example.com", password=None)

    def test_typed_email_deletes_ignoring_case_and_spaces(self):
        res = self.delete(self.user, {"email": "  G@Example.com "})

        self.assertEqual(res.status_code, 204)
        self.assertGone(self.user)

    def test_other_email_keeps_account_and_names_the_field(self):
        res = self.delete(self.user, {"email": "other@example.com"})

        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.json())
        self.assertKept(self.user)

    def test_empty_or_odd_email_is_refused(self):
        for body in ({}, {"email": ""}, {"email": 1}, {"current_password": WRONG_PASSWORD}):
            with self.subTest(body=body):
                self.assertEqual(self.delete(self.user, body).status_code, 400)
        self.assertKept(self.user)


class RecordsTest(WithdrawTestCase):
    def test_every_relation_to_user_is_cascade(self):
        # 새 FK 가 CASCADE 가 아니면 삭제가 500 이 되거나 기록이 남는다.
        for relation in User._meta.related_objects:
            with self.subTest(relation=relation.related_model.__name__):
                self.assertIs(relation.on_delete, models.CASCADE)

    def test_only_my_learning_records_go(self):
        me = User.objects.create_user(email="me@example.com", password=PASSWORD)
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        today = timezone.localdate()
        for user in (me, other):
            DailyScore.objects.create(user=user, day=today)
            ReviewState.objects.create(user=user, target_type="word", target_id=1)

        self.delete(me, {"current_password": PASSWORD})

        self.assertEqual(DailyScore.objects.filter(user_id=me.pk).count(), 0)
        self.assertEqual(ReviewState.objects.filter(user_id=me.pk).count(), 0)
        self.assertEqual(DailyScore.objects.filter(user=other).count(), 1)
        self.assertEqual(ReviewState.objects.filter(user=other).count(), 1)
        self.assertKept(other)


class ThrottleTest(WithdrawTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def test_password_guesses_are_limited(self):
        with mock.patch.object(PasswordChangeThrottle, "rate", "2/min", create=True):
            codes = [
                self.delete(self.user, {"current_password": WRONG_PASSWORD}).status_code
                for _ in range(3)
            ]

        self.assertEqual(codes, [400, 400, 429])
        self.assertKept(self.user)

    def test_reading_my_info_is_not_limited(self):
        token = Token.objects.create(user=self.user)
        with mock.patch.object(PasswordChangeThrottle, "rate", "1/min", create=True):
            codes = [
                self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {token.key}").status_code
                for _ in range(3)
            ]

        self.assertEqual(codes, [200, 200, 200])


class AdminLogTest(TestCase):
    def test_str_is_member_number_not_email(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD)

        self.assertEqual(str(user), f"회원 {user.pk}")

    def test_admin_delete_log_has_no_email(self):
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        target = User.objects.create_user(email="target@example.com", password=PASSWORD)
        self.client.force_login(admin)

        res = self.client.post(
            f"/admin/accounts/user/{target.pk}/delete/", {"post": "yes"}, follow=True
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(pk=target.pk).exists())
        entry = LogEntry.objects.get(object_id=str(target.pk))
        self.assertNotIn("target@example.com", entry.object_repr)
        self.assertNotIn("target@example.com", entry.change_message)


class BodyEdgeTest(WithdrawTestCase):
    """이상한 본문은 지우지 않고, 500 으로 터지지 않는다."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        self.token = Token.objects.create(user=self.user).key

    def raw(self, body, content_type="application/json", method="delete"):
        return getattr(self.client, method)(
            ME_URL, body, content_type=content_type, HTTP_AUTHORIZATION=f"Token {self.token}"
        )

    def test_broken_or_odd_json_is_400_and_keeps_account(self):
        cases = [
            '"문자열"', "1", "null", "true", "[]", "[1]", "{", '{"current_password":',
            '{"current_password":null}', '{"current_password":true}',
            '{"current_password":{"a":1}}', '{"current_password":[]}',
            '{"current_password":""}', '{"current_password":"   "}', "", "\x00",
        ]
        for body in cases:
            with self.subTest(body=body):
                res = self.raw(body)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertKept(self.user)

    def test_huge_password_is_refused_without_crashing(self):
        res = self.raw(json.dumps({"current_password": "x" * 1_000_000}))

        self.assertEqual(res.status_code, 400)
        self.assertKept(self.user)

    def test_body_over_upload_limit_is_refused(self):
        res = self.raw(json.dumps({"current_password": "x" * 5_000_000}))

        self.assertEqual(res.status_code, 400)
        self.assertKept(self.user)

    def test_form_encoded_body_works_like_json(self):
        res = self.raw(
            f"current_password={PASSWORD}", content_type="application/x-www-form-urlencoded"
        )

        self.assertEqual(res.status_code, 204)
        self.assertGone(self.user)

    def test_text_plain_is_rejected_and_keeps_account(self):
        res = self.raw(json.dumps({"current_password": PASSWORD}), content_type="text/plain")

        self.assertEqual(res.status_code, 415)
        self.assertKept(self.user)

    def test_other_methods_do_not_delete(self):
        auth = {"HTTP_AUTHORIZATION": f"Token {self.token}"}
        for method in ("post", "put"):
            with self.subTest(method=method):
                res = getattr(self.client, method)(
                    ME_URL, "{}", content_type="application/json", **auth
                )
                self.assertEqual(res.status_code, 405)
        self.assertEqual(self.client.trace(ME_URL, **auth).status_code, 405)
        self.assertKept(self.user)

    def test_method_override_header_does_not_delete(self):
        res = self.client.post(
            ME_URL,
            {"current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token}",
            HTTP_X_HTTP_METHOD_OVERRIDE="DELETE",
        )

        self.assertEqual(res.status_code, 405)
        self.assertKept(self.user)

    def test_ids_in_body_cannot_redirect_the_deletion(self):
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)

        res = self.client.delete(
            ME_URL,
            {"current_password": PASSWORD, "id": other.pk, "email": "other@example.com"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token}",
        )

        self.assertEqual(res.status_code, 204)
        self.assertGone(self.user)
        self.assertKept(other)

    def test_invalid_tokens_are_401(self):
        for header in ("Token nope", "Bearer x", "Token ", "Token " + "9" * 500):
            with self.subTest(header=header):
                res = self.client.delete(
                    ME_URL, "{}", content_type="application/json", HTTP_AUTHORIZATION=header
                )
                self.assertEqual(res.status_code, 401)
        self.assertKept(self.user)

    def test_suspended_account_is_401(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        res = self.raw(json.dumps({"current_password": PASSWORD}))

        self.assertEqual(res.status_code, 401)
        self.assertKept(self.user)

    def test_staff_is_refused_before_password_is_looked_at(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True)

        res = self.raw(json.dumps({"current_password": WRONG_PASSWORD}))

        self.assertEqual(res.status_code, 403)
        self.assertKept(self.user)

    def test_password_spaces_are_part_of_the_value(self):
        self.user.set_password(f"  {PASSWORD}  ")
        self.user.save()

        self.assertEqual(self.raw(json.dumps({"current_password": PASSWORD})).status_code, 400)
        self.assertKept(self.user)
        self.assertEqual(
            self.raw(json.dumps({"current_password": f"  {PASSWORD}  "})).status_code, 204
        )
        self.assertGone(self.user)


class GoogleOnlyEdgeTest(WithdrawTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="kevin@example.com", password=None)

    def test_lookalike_emails_do_not_match(self):
        for typed in (
            "kevin@example.com.",
            "ke\u212avin@example.com",
            "kevin@example.com\x00",
            "\u200bkevin@example.com",
            "a" * 2_000_000,
        ):
            with self.subTest(typed=ascii(typed[:30])):
                self.assertEqual(self.delete(self.user, {"email": typed}).status_code, 400)
                self.assertKept(self.user)


class ThrottleEdgeTest(WithdrawTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def test_bucket_is_shared_with_password_change_and_blocks_right_password(self):
        token = Token.objects.create(user=self.user).key
        with mock.patch.object(PasswordChangeThrottle, "rate", "2/min", create=True):
            self.client.post(
                "/api/accounts/password/",
                {"current_password": WRONG_PASSWORD, "new_password": WRONG_PASSWORD + "n"},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {token}",
            )
            first = self.delete(self.user, {"current_password": WRONG_PASSWORD})
            second = self.delete(self.user, {"current_password": PASSWORD})

        self.assertEqual((first.status_code, second.status_code), (400, 429))
        self.assertKept(self.user)

    def test_one_account_using_up_its_tries_does_not_block_another(self):
        other = User.objects.create_user(email="other@example.com", password=PASSWORD)
        with mock.patch.object(PasswordChangeThrottle, "rate", "1/min", create=True):
            for _ in range(2):
                self.delete(self.user, {"current_password": WRONG_PASSWORD})
            res = self.delete(other, {"current_password": PASSWORD})

        self.assertEqual(res.status_code, 204)


class LeftBehindTest(WithdrawTestCase):
    def test_every_row_and_the_photo_address_go_with_the_account(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        now = timezone.now()
        session = QuizSession.objects.create(
            user=user, token_id="t1", started_at=now, finished_at=now, score=30,
            answered=1, correct=1, skipped=0, kind="free",
        )
        QuizAnswer.objects.create(
            session=session, kind="meaning", target_type="word", target_id=1,
            is_correct=True, is_skipped=False, elapsed_ms=1, score=1,
        )
        DailyScore.objects.create(user=user, day=timezone.localdate(), best_free_score=30)
        ReviewState.objects.create(user=user, target_type="word", target_id=1)
        key = "11111111-1111-4111-8111-111111111111"
        User.objects.filter(pk=user.pk).update(
            avatar_photo=b"RIFFxxxxWEBP", avatar_photo_key=key, avatar_photo_at=now, avatar="photo"
        )
        photo_url = f"/api/accounts/photo/{key}/"
        self.assertEqual(self.client.get(photo_url).status_code, 200)

        res = self.delete(user, {"current_password": PASSWORD})

        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get(photo_url).status_code, 404)
        for query in (
            QuizSession.objects.filter(user_id=user.pk),
            QuizAnswer.objects.filter(session__user_id=user.pk),
            DailyScore.objects.filter(user_id=user.pk),
            ReviewState.objects.filter(user_id=user.pk),
            Token.objects.filter(user_id=user.pk),
        ):
            self.assertEqual(query.count(), 0, query.model.__name__)

    def test_deleted_google_account_must_agree_again(self):
        user = User.objects.create_user(email="g@example.com", password=None)
        self.delete(user, {"email": "g@example.com"})

        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "g@example.com", "name": "구글", "picture": ""},
        ):
            res = self.client.post(
                "/api/accounts/google/",
                {"code": "c", "redirect_uri": "http://localhost:3000/api/auth/google/callback"},
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {"code": "consent_required"})
        self.assertFalse(User.objects.filter(email="g@example.com").exists())


class AdminListTest(TestCase):
    def setUp(self):
        cache.clear()
        admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.client.force_login(admin)
        self.member = User.objects.create_user(email="m@example.com", password=PASSWORD)

    def test_learning_lists_show_the_email_column(self):
        now = timezone.now()
        DailyScore.objects.create(user=self.member, day=timezone.localdate())
        ReviewState.objects.create(user=self.member, target_type="word", target_id=1)
        QuizSession.objects.create(
            user=self.member, token_id="t1", started_at=now, finished_at=now, score=1,
            answered=1, correct=1, skipped=0, kind="free",
        )
        for model in ("quizsession", "dailyscore", "reviewstate"):
            with self.subTest(model=model):
                self.assertContains(self.client.get(f"/admin/learning/{model}/"), "m@example.com")
                self.assertEqual(self.client.get(f"/admin/learning/{model}/?o=2").status_code, 200)

    def test_daily_study_list_still_renders(self):
        self.assertEqual(self.client.get("/admin/learning/dailystudy/").status_code, 200)

    def test_user_list_still_shows_the_email(self):
        self.assertContains(self.client.get("/admin/accounts/user/"), "m@example.com")


def _run_together(*calls):
    """각자의 스레드(= 각자의 DB 연결)에서 돌리고 결과를 모은다. 예외는 그대로 담는다."""
    results = [None] * len(calls)

    def one(index, call):
        try:
            results[index] = call()
        except Exception as exc:
            results[index] = exc
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=one, args=(i, call), daemon=True) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class WithdrawRaceTest(_KeepsCacheTable, TransactionTestCase):
    """삭제와 다른 요청이 실제로 겹칠 때. 어느 쪽으로 끝나도 터지거나 남으면 안 된다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="race@example.com", password=PASSWORD)
        self.token = Token.objects.create(user=self.user).key

    def delete_now(self):
        client = Client(raise_request_exception=False)
        return client.delete(
            ME_URL,
            {"current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token}",
        ).status_code

    def test_same_delete_four_times_at_once_never_crashes(self):
        barrier = threading.Barrier(4)

        def go():
            barrier.wait(timeout=20)
            return self.delete_now()

        results = _run_together(go, go, go, go)

        for result in results:
            self.assertIn(result, (204, 401), results)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_during_first_round_of_the_day_leaves_no_rows(self):
        """오늘 첫 판이라 하루 점수 줄이 없는 경우. 어느 순서로 끝나도 줄이 안 남는다."""
        started = threading.Event()
        real = record._bump_review

        def slow(user, answers):
            started.set()
            threading.Event().wait(0.4)
            return real(user, answers)

        def save():
            now = timezone.now()
            with mock.patch.object(record, "_bump_review", slow):
                return record.save_round(
                    self.user,
                    {
                        "kind": "free",
                        "token_id": "race-1",
                        "started_at": now,
                        "score": 50,
                        "answered": 1,
                        "correct": 1,
                        "skipped": 0,
                        "answers": [["meaning", "word", 1, True, False, 10, 50]],
                    },
                )

        def delete():
            started.wait(timeout=10)
            return self.delete_now()

        saved, deleted = _run_together(save, delete)

        self.assertEqual(deleted, 204)
        self.assertNotIsInstance(saved, Exception, saved)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(QuizSession.objects.filter(user_id=self.user.pk).count(), 0)
        self.assertEqual(DailyScore.objects.filter(user_id=self.user.pk).count(), 0)

    def test_save_committing_during_the_delete_waits_and_delete_wins(self):
        """지울 목록을 모은 뒤에 저장이 끝나면, 잠금이 없을 때 삭제가 FK 오류로 끝난다."""
        collected = threading.Event()
        real_delete = Collector.delete

        def slow_delete(collector):
            collected.set()
            threading.Event().wait(0.5)
            return real_delete(collector)

        def save():
            collected.wait(timeout=10)
            now = timezone.now()
            return record.save_round(
                self.user,
                {
                    "kind": "free",
                    "token_id": "race-2",
                    "started_at": now,
                    "score": 50,
                    "answered": 1,
                    "correct": 1,
                    "skipped": 0,
                    "answers": [["meaning", "word", 1, True, False, 10, 50]],
                },
            )

        def delete():
            with mock.patch.object(Collector, "delete", slow_delete):
                return self.delete_now()

        saved, deleted = _run_together(save, delete)

        self.assertEqual(deleted, 204, (saved, deleted))
        self.assertNotIsInstance(saved, Exception, saved)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(QuizSession.objects.filter(user_id=self.user.pk).count(), 0)

    def test_profile_save_after_delete_does_not_bring_the_account_back(self):
        """인증을 지난 PATCH 가 삭제 뒤에 저장해도 INSERT 로 되살아나면 안 된다."""
        go_delete, deleted = threading.Event(), threading.Event()
        real = UserSerializer.validate_display_name

        def wait_for_delete(serializer, value):
            go_delete.set()
            deleted.wait(timeout=10)
            return real(serializer, value)

        def patch():
            client = Client(raise_request_exception=False)
            with mock.patch.object(UserSerializer, "validate_display_name", wait_for_delete):
                return client.patch(
                    ME_URL,
                    {"display_name": "되살아남"},
                    content_type="application/json",
                    HTTP_AUTHORIZATION=f"Token {self.token}",
                ).status_code

        def delete():
            go_delete.wait(timeout=10)
            status = self.delete_now()
            deleted.set()
            return status

        _run_together(patch, delete)

        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(User.objects.filter(email="race@example.com").exists())
