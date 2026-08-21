"""일일공부 이어 풀기.

**중간에 나간 사람이 오늘 판을 끝낼 수 있어야 한다.** 답하려면 토큰이
필요한데 토큰은 시작·답하기에서만 나오고, 시작은 하루 한 번 제약에
막힌다. 제한 시간이 없는 기능이라 중간 이탈이 예외가 아니다.

여기서 지키는 것 둘:

    이어 풀 수 있다        GET 이 토큰과 문제를 함께 준다
    문제를 갈아탈 수 없다  같은 순번에서는 늘 같은 문제가 나온다

두 번째가 특히 중요하다. 순번은 답할 때만 오르므로, 새로 뽑아주면
아는 문제가 나올 때까지 화면을 다시 열면 된다 - 사실상 만점이 된다.
_take_step 은 "한 순번은 한 번만 소비된다" 만 지키지 그것까지 막지
못한다. 지금까지는 문제 발급이 순번 소비와 붙어 있어 그 차이가 드러날
자리가 없었고, 이어 풀기가 그 둘을 처음 분리했다.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase

from . import daily_study
from .models import DailyStudy, StudyLength
from .session import SessionError
from .tests_daily_study import make_user, seed_words

START_URL = "/api/learning/daily/"
ANSWER_URL = "/api/learning/daily/answer/"


def _prompt(question: dict) -> str:
    """문제를 구분하는 값. 같은 문제면 같다."""
    return question["prompt"]


class ResumeTest(TestCase):
    """하다 만 판을 이어서 푼다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("이어풀기")

    def test_a_half_done_study_can_be_continued(self):
        """중간에 나가도 오늘 판을 끝낼 수 있다.

        이게 없으면 3문제 풀고 나간 사람이 완주 보너스를 영영 잃는다 -
        시작은 하루 한 번 제약에 막히고 답할 토큰은 받을 길이 없다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        daily_study.answer(self.user, token, question["choices"][0]["id"])

        # 화면을 떠났다가 다시 온다. 토큰은 잃었다.
        today = daily_study.today_of(self.user)
        resumed = daily_study.resume(today)

        self.assertIsNotNone(resumed, "이어 풀 토큰을 못 받았다")
        next_token, next_question = resumed
        daily_study.answer(self.user, next_token, next_question["choices"][0]["id"])

        study.refresh_from_db()
        self.assertEqual(study.answered, 2, "이어서 푼 답이 안 세어졌다")

    def test_the_question_does_not_change_between_visits(self):
        """화면을 다시 열어도 같은 문제가 나온다.

        새로 뽑아주면 순번을 소비하지 않고 문제만 바꿀 수 있다. 모르는
        문제가 나오면 다시 열고, 아는 것이 나올 때까지 반복한 뒤 답하면
        된다 - 40문제짜리를 사실상 만점으로 끝낸다.
        """
        _study, _token, first = daily_study.start(self.user, StudyLength.LONG)

        seen = {_prompt(first)}
        for _ in range(5):
            today = daily_study.today_of(self.user)
            resumed = daily_study.resume(today)
            self.assertIsNotNone(resumed)
            seen.add(_prompt(resumed[1]))

        self.assertEqual(
            len(seen), 1, f"같은 순번에서 문제가 바뀐다. 본 것: {len(seen)}가지"
        )

    def test_answering_moves_to_the_next_question(self):
        """답하면 다음 문제로 넘어간다. 고정이 진행을 막지 않는다."""
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        before = _prompt(question)

        _r, next_token, next_question, study = daily_study.answer(
            self.user, token, question["choices"][0]["id"]
        )

        self.assertIsNotNone(next_question, "다음 문제가 안 왔다")
        self.assertNotEqual(before, _prompt(next_question), "같은 문제가 또 나왔다")
        self.assertEqual(study.answered, 1)

        # 이어 풀기로 받아도 그 다음 문제다
        today = daily_study.today_of(self.user)
        resumed = daily_study.resume(today)
        self.assertEqual(
            _prompt(resumed[1]), _prompt(next_question), "이어 풀기가 다른 문제를 냈다"
        )

    def test_an_old_token_is_still_refused_after_resuming(self):
        """이어 풀기를 받아도 옛 토큰은 거절된다.

        되돌리기 방어가 약해지지 않았는지 본다. 토큰에 실리는 순번은 DB 의
        step 에서 읽으므로 새 토큰이든 옛 토큰이든 조건은 같아야 한다.
        """
        _study, first_token, question = daily_study.start(
            self.user, StudyLength.SHORT
        )
        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, first_token, picked)

        # 이어 풀 토큰을 받는다. 그래도 옛 토큰은 죽어 있어야 한다.
        today = daily_study.today_of(self.user)
        daily_study.resume(today)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, first_token, picked)

    def test_two_resume_tokens_consume_only_one_step(self):
        """이어 풀 토큰을 두 번 받아도 순번은 하나만 소비된다."""
        study, _token, _question = daily_study.start(self.user, StudyLength.SHORT)

        today = daily_study.today_of(self.user)
        token_a = daily_study.resume(today)[0]
        token_b = daily_study.resume(today)[0]

        daily_study.answer(self.user, token_a, 1)
        with self.assertRaises(SessionError):
            daily_study.answer(self.user, token_b, 1)

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "토큰 두 개가 각각 세어졌다")

    def test_a_finished_study_has_nothing_to_resume(self):
        """끝난 판은 이어 풀 것이 없다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        while question is not None:
            _r, token, question, study = daily_study.answer(
                self.user, token, question["choices"][0]["id"]
            )

        study.refresh_from_db()
        self.assertTrue(study.is_done)
        self.assertIsNone(daily_study.resume(study))


class ResumeApiTest(TestCase):
    """엔드포인트로 확인한다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("이어풀기API")
        self.client.force_login(self.user)

    def test_the_status_carries_a_token_when_a_study_is_open(self):
        """하다 만 판이 있으면 GET 이 이어 풀 토큰을 함께 준다."""
        started = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()
        self.client.post(
            ANSWER_URL,
            {
                "token": started["token"],
                "choice_id": started["question"]["choices"][0]["id"],
            },
            content_type="application/json",
        )

        body = self.client.get(START_URL).json()

        self.assertIsNotNone(body["token"], "이어 풀 토큰이 없다")
        self.assertIsNotNone(body["question"])
        self.assertEqual(body["today"]["answered"], 1)

    def test_the_status_has_no_token_before_starting(self):
        """아직 시작 안 했으면 토큰이 없다."""
        body = self.client.get(START_URL).json()

        self.assertIsNone(body["today"])
        self.assertIsNone(body["token"])

    def test_another_user_cannot_use_my_resume_token(self):
        """남의 이어 풀 토큰으로 답할 수 없다."""
        started = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()
        self.client.post(
            ANSWER_URL,
            {
                "token": started["token"],
                "choice_id": started["question"]["choices"][0]["id"],
            },
            content_type="application/json",
        )
        mine = self.client.get(START_URL).json()

        other = make_user("남의계정")
        attacker = self.client_class()
        attacker.force_login(other)

        got = attacker.post(
            ANSWER_URL,
            {"token": mine["token"], "choice_id": mine["question"]["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(got.status_code, 400, "남의 토큰이 통과했다")
        self.assertEqual(
            DailyStudy.objects.filter(user=other).count(), 0, "남의 판이 생겼다"
        )
