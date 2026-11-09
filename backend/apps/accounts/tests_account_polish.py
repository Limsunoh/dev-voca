"""시도 제한 문구와 내 정보 저장 제한."""

import importlib
import sys
from unittest import mock

from config.exceptions import exception_handler
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import Throttled

from apps.learning.models import DailyScore, QuizSession
from apps.learning.throttles import LeaderboardThrottle
from apps.vocab.models import Word

from .tests import PASSWORD
from .throttles import EmailRateThrottle, PasswordChangeThrottle, ProfileUpdateThrottle

User = get_user_model()

LOGIN_URL = "/api/accounts/login/"
ME_URL = "/api/accounts/me/"
PASSWORD_URL = "/api/accounts/password/"
STREAK_URL = "/api/learning/leaderboards/streak/"
WEEKLY_URL = "/api/learning/leaderboards/weekly/"
WORDS_URL = "/api/vocab/words/"
WRONG_PASSWORD = PASSWORD + "x"


class ThrottleMessageTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_limit_message_is_plain_korean_and_keeps_retry_after(self):
        body = {"email": "a@example.com", "password": WRONG_PASSWORD}
        with mock.patch.object(EmailRateThrottle, "get_rate", return_value="1/min"):
            self.client.post(LOGIN_URL, body, content_type="application/json")
            res = self.client.post(LOGIN_URL, body, content_type="application/json")

        self.assertEqual(res.status_code, 429)
        self.assertRegex(res.json()["detail"], r"^시도가 너무 많습니다\. \d+초 뒤에 다시 해주세요\.$")
        self.assertIn("Retry-After", res.headers)

    def test_other_errors_are_untouched(self):
        res = self.client.get(ME_URL)

        self.assertEqual(res.status_code, 401)
        self.assertNotIn("시도가", res.json()["detail"])


class ProfileUpdateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        token = Token.objects.create(user=self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def save(self, avatar):
        return self.client.patch(
            ME_URL, {"avatar": avatar}, content_type="application/json", **self.auth
        )

    def test_saving_is_limited_per_account(self):
        with mock.patch.object(ProfileUpdateThrottle, "get_rate", return_value="1/min"):
            codes = [self.save("a1").status_code, self.save("a2").status_code]

        self.assertEqual(codes, [200, 429])

    def test_another_account_is_not_limited(self):
        other = User.objects.create_user(email="b@example.com", password=PASSWORD)
        other_token = Token.objects.create(user=other)
        with mock.patch.object(ProfileUpdateThrottle, "get_rate", return_value="1/min"):
            self.save("a1")
            res = self.client.patch(
                ME_URL,
                {"avatar": "a2"},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {other_token.key}",
            )

        self.assertEqual(res.status_code, 200)

    def test_reading_is_not_limited(self):
        with mock.patch.object(ProfileUpdateThrottle, "get_rate", return_value="1/min"):
            codes = [self.client.get(ME_URL, **self.auth).status_code for _ in range(3)]

        self.assertEqual(codes, [200, 200, 200])

    def test_saving_does_not_use_up_password_attempts(self):
        with (
            mock.patch.object(ProfileUpdateThrottle, "get_rate", return_value="1/min"),
            mock.patch.object(PasswordChangeThrottle, "get_rate", return_value="1/min"),
        ):
            self.save("a1")
            res = self.client.delete(
                ME_URL,
                {"current_password": WRONG_PASSWORD},
                content_type="application/json",
                **self.auth,
            )

        self.assertEqual(res.status_code, 400)


class ThrottleMessageEdgeTest(TestCase):
    """429 문구의 경계와, 다른 오류를 건드리지 않는지."""

    def setUp(self):
        cache.clear()

    def handle(self, exc):
        return exception_handler(exc, {"view": None, "request": None})

    def test_wait_unknown_says_shortly_without_retry_after(self):
        """DRF 는 통이 넘치면 wait 를 None 으로 준다. 500 이나 'None초' 가 나면 안 된다."""
        res = self.handle(Throttled(wait=None))

        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.data["detail"], "시도가 너무 많습니다. 잠시 뒤에 다시 해주세요.")
        self.assertNotIn("Retry-After", res.headers)

    def test_fraction_rounds_up_like_the_header(self):
        res = self.handle(Throttled(wait=0.2))

        self.assertEqual(res.data["detail"], "시도가 너무 많습니다. 1초 뒤에 다시 해주세요.")
        self.assertEqual(res.headers["Retry-After"], "1")

    def test_number_on_screen_matches_header_and_clock(self):
        body = {"email": "a@example.com", "password": WRONG_PASSWORD}
        now = 1_800_000_000.0
        with (
            mock.patch.object(EmailRateThrottle, "get_rate", return_value="1/min"),
            mock.patch.object(EmailRateThrottle, "timer", side_effect=[now, now + 10]),
        ):
            self.client.post(LOGIN_URL, body, content_type="application/json")
            res = self.client.post(LOGIN_URL, body, content_type="application/json")

        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.headers["Retry-After"], "50")
        self.assertEqual(res.json()["detail"], "시도가 너무 많습니다. 50초 뒤에 다시 해주세요.")

    def test_other_domains_get_the_same_sentence(self):
        """전역 처리기라 순위표의 429 도 같은 문구다."""
        self.client.force_login(
            User.objects.create_user(email="a@example.com", password=PASSWORD)
        )
        with mock.patch.dict(LeaderboardThrottle.THROTTLE_RATES, {"leaderboard": "1/min"}):
            self.client.get(STREAK_URL)
            res = self.client.get(STREAK_URL)

        self.assertEqual(res.status_code, 429)
        self.assertRegex(res.json()["detail"], r"^시도가 너무 많습니다\. \d+초 뒤에 다시 해주세요\.$")

    def test_validation_and_method_errors_keep_their_shape(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        token = Token.objects.create(user=user)

        bad_login = self.client.post(LOGIN_URL, {}, content_type="application/json")
        put = self.client.put(
            ME_URL,
            {},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(bad_login.status_code, 400)
        self.assertIn("email", bad_login.json())
        self.assertEqual(put.status_code, 405)
        self.assertNotIn("시도가", put.json()["detail"])


class ProfileUpdateLimitEdgeTest(TestCase):
    """이름 저장 제한의 경계."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        self.token = Token.objects.create(user=self.user)
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def patch(self, data, **extra):
        return self.client.patch(ME_URL, data, content_type="application/json", **extra)

    def limited(self, rate="1/min"):
        return mock.patch.object(ProfileUpdateThrottle, "get_rate", return_value=rate)

    def test_requests_without_valid_token_do_not_fill_the_bucket(self):
        with self.limited():
            anon = [self.patch({"avatar": "a1"}).status_code for _ in range(3)]
            bad = self.patch({"avatar": "a1"}, HTTP_AUTHORIZATION="Token nope").status_code
            mine = self.patch({"avatar": "a1"}, **self.auth).status_code

        self.assertEqual(anon, [401, 401, 401])
        self.assertEqual(bad, 401)
        self.assertEqual(mine, 200)

    def test_thirty_pass_and_thirty_first_is_blocked(self):
        with self.limited("30/min"):
            codes = [
                self.patch({"avatar": "a1"}, **self.auth).status_code for _ in range(31)
            ]
            last = self.patch({"avatar": "a1"}, **self.auth)

        self.assertEqual(codes, [200] * 30 + [429])
        self.assertEqual(last.status_code, 429)
        self.assertRegex(last.json()["detail"], r"^시도가 너무 많습니다\. \d+초 뒤에 다시 해주세요\.$")
        self.assertIn("Retry-After", last.headers)

    def test_production_rate_is_thirty_per_minute(self):
        real_argv = sys.argv
        sys.argv = ["gunicorn"]
        try:
            prod = importlib.reload(importlib.import_module("config.settings"))
            rate = prod.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["profile_update"]
        finally:
            sys.argv = real_argv
            importlib.reload(importlib.import_module("config.settings"))

        self.assertEqual(rate, "30/min")

    def test_limit_opens_again_after_a_minute(self):
        now = 1_800_000_000.0
        with (
            self.limited(),
            mock.patch.object(
                ProfileUpdateThrottle, "timer", side_effect=[now, now + 59, now + 61]
            ),
        ):
            codes = [
                self.patch({"avatar": "a1"}, **self.auth).status_code for _ in range(3)
            ]

        self.assertEqual(codes, [200, 429, 200])

    def test_rejected_saves_count_too(self):
        """400 도 세야 이름 중복 여부를 무한정 찔러 볼 수 없다."""
        with self.limited():
            first = self.patch({"display_name": " "}, **self.auth)
            second = self.patch({"avatar": "a1"}, **self.auth)

        self.assertEqual((first.status_code, second.status_code), (400, 429))

    def test_bad_names_are_400_not_500(self):
        for value in ["", "   ", "가" * 13, None, ["x"], {"a": 1}, True]:
            with self.subTest(value=value):
                res = self.patch({"display_name": value}, **self.auth)
                self.assertEqual(res.status_code, 400)

    def test_bad_bodies_are_400_not_500(self):
        for body in ["[1, 2]", "not json", '"text"', "{"]:
            with self.subTest(body=body):
                res = self.client.patch(
                    ME_URL, body, content_type="application/json", **self.auth
                )
                self.assertEqual(res.status_code, 400)

    def test_taken_name_is_400_not_500(self):
        User.objects.create_user(
            email="b@example.com", password=PASSWORD, display_name="이미있는이름"
        )

        res = self.patch({"display_name": "이미있는이름"}, **self.auth)

        self.assertEqual(res.status_code, 400)
        self.assertIn("display_name", res.json())

    def test_used_up_name_saves_leave_other_account_actions_open(self):
        bad_password = {
            "current_password": WRONG_PASSWORD,
            "new_password": WRONG_PASSWORD + "y",
        }
        with self.limited():
            self.patch({"avatar": "a1"}, **self.auth)
            self.assertEqual(self.patch({"avatar": "a2"}, **self.auth).status_code, 429)
            read = self.client.get(ME_URL, **self.auth)
            change = self.client.post(
                PASSWORD_URL, bad_password, content_type="application/json", **self.auth
            )

        self.assertEqual(read.status_code, 200)
        self.assertEqual(change.status_code, 400)

    def test_used_up_password_attempts_leave_name_saving_open(self):
        bad_password = {"current_password": WRONG_PASSWORD, "new_password": WRONG_PASSWORD}
        with mock.patch.object(PasswordChangeThrottle, "get_rate", return_value="1/min"):
            self.client.post(
                PASSWORD_URL, bad_password, content_type="application/json", **self.auth
            )
            blocked = self.client.post(
                PASSWORD_URL, bad_password, content_type="application/json", **self.auth
            )
            saved = self.patch({"avatar": "a1"}, **self.auth)

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(saved.status_code, 200)


class ZeroRowsApiTest(TestCase):
    """화면이 '-' 로 그리는 줄을 서버는 그대로 주는지, 최고점 0점은 순위가 있는지."""

    def setUp(self):
        cache.clear()
        self.day = timezone.localdate()

    def user(self, name):
        user = User.objects.create_user(
            email=f"{name}@example.com", password=PASSWORD, display_name=name
        )
        return user, {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=user).key}"}

    def test_zero_day_streak_is_outside_the_list_but_has_my_row(self):
        scorer, _ = self.user("scorer")
        DailyScore.objects.create(user=scorer, day=self.day, best_free_score=5)
        zero, auth = self.user("zero")
        DailyScore.objects.create(user=zero, day=self.day, best_free_score=0)

        data = self.client.get(STREAK_URL, **auth).json()

        self.assertEqual([row["display_name"] for row in data["rows"]], ["scorer"])
        self.assertEqual(data["me"]["score"], 0)
        self.assertEqual(data["me"]["rank"], 2)

    def test_account_without_any_day_has_no_row(self):
        _, auth = self.user("nothing")

        data = self.client.get(STREAK_URL, **auth).json()

        self.assertIsNone(data["me"])

    def test_one_day_streak_keeps_its_rank(self):
        one, auth = self.user("oneday")
        DailyScore.objects.create(user=one, day=self.day, best_free_score=1)

        data = self.client.get(STREAK_URL, **auth).json()

        self.assertEqual(data["rows"][0]["rank"], 1)
        self.assertEqual(data["rows"][0]["score"], 1)

    def test_zero_point_best_round_is_still_ranked(self):
        zero, auth = self.user("zeropt")
        now = timezone.now()
        QuizSession.objects.create(
            user=zero,
            token_id="tests-account-polish-zero",
            started_at=now,
            finished_at=now,
            score=0,
            answered=1,
            correct=0,
            skipped=1,
            kind="free",
        )

        data = self.client.get(WEEKLY_URL, **auth).json()

        self.assertEqual(data["rows"][0]["score"], 0)
        self.assertEqual(data["rows"][0]["rank"], 1)
        self.assertTrue(data["rows"][0]["is_me"])


class ReviewGateWithGlobalHandlerTest(TestCase):
    """전역 예외 처리기를 바꿔도 검수 안 된 단어는 어느 경로로도 안 나간다."""

    def test_unreviewed_word_is_not_in_list_search_or_detail(self):
        shown = Word.objects.create(term="shownzzq", meaning="보임", is_reviewed=True)
        hidden = Word.objects.create(term="hiddenzzq", meaning="숨김", is_reviewed=False)

        listed = self.client.get(WORDS_URL)
        searched = self.client.get(WORDS_URL, {"search": "zzq"})
        detail = self.client.get(f"{WORDS_URL}{hidden.pk}/")

        self.assertIn("shownzzq", listed.content.decode())
        self.assertNotIn("hiddenzzq", listed.content.decode())
        self.assertIn("shownzzq", searched.content.decode())
        self.assertNotIn("hiddenzzq", searched.content.decode())
        self.assertEqual(detail.status_code, 404)
        self.assertNotIn("hiddenzzq", detail.content.decode())
        self.assertEqual(self.client.get(f"{WORDS_URL}{shown.pk}/").status_code, 200)

    def test_broken_ids_are_404_not_500(self):
        for pk in ["9" * 30, "abc", "-1", "0"]:
            with self.subTest(pk=pk):
                self.assertEqual(self.client.get(f"{WORDS_URL}{pk}/").status_code, 404)
