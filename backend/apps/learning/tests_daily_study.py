"""일일공부.

지키려는 것은 다섯이다.

    - 하루 한 번. 이미 시작했으면 다시 못 연다
    - 푼 만큼 그때그때 남는다. 나가도 점수가 사라지지 않는다
    - 감점이 없다. 틀려도 0 이지 마이너스가 아니다
    - 다 풀어야 완주 보너스. 길이별로 다르다
    - 로그인해야 쓴다. 진행이 DB 에 남는 기능이다

두 번째가 이 기능의 존재 이유다. 자유 문제풀이처럼 끝내기를 클라이언트에
맡기면, 더하기 규칙에서는 **점수가 깎이는 판을 버리는 것이 이득**이 된다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase

from apps.vocab.models import Word

from . import calendar_kst, daily_study
from .models import STUDY_PLANS, DailyScore, DailyStudy, StudyLength
from .session import SessionError

User = get_user_model()

START_URL = "/api/learning/daily/"
ANSWER_URL = "/api/learning/daily/answer/"

PASSWORD = secrets.token_urlsafe(16)


def make_user(name: str) -> User:
    return User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def seed_words(count: int = 120) -> None:
    """문제를 만들 수 있을 만큼 단어를 채운다.

    **RECENT_KEEP(40) 보다 넉넉해야 한다.** 출제가 최근 낸 정답을 후보에서
    빼므로, 단어가 40개 이하면 30분 코스(40문제)가 후보 고갈로 끊긴다 -
    판은 서버가 닫아주지만 40문제를 약속하고 30문제만 낸다. "넉넉히" 라고
    쓰고 30 을 뒀다가 실제로 그 자리에서 걸렸다.
    """
    tag = uuid4().hex[:6]
    Word.objects.bulk_create(
        Word(
            term=f"{tag}word{i}",
            meaning=f"뜻{i}",
            description=f"설명{i} 입니다",
            is_reviewed=True,
        )
        for i in range(count)
    )


def run_to_end(user, length: str) -> DailyStudy:
    """한 판을 끝까지 푼다. 늘 첫 보기를 고른다."""
    study, token, question = daily_study.start(user, length)

    while question is not None:
        picked = question["choices"][0]["id"]
        _, token, question, _s = daily_study.answer(user, token, picked)

    study.refresh_from_db()
    return study


def tomorrow():
    """하루 뒤로 간 시계.

    자정을 흉내낼 때 **day 를 밀지 않고 시계를 민다.** 프로덕션에서
    DailyStudy.day 는 만들 때 한 번 정해지고 다시는 안 바뀐다 - 움직이는
    것은 시계뿐이다. day 를 미는 방식은 이미 그날 줄에 쌓아둔 점수까지
    같이 옮긴 것처럼 보여, 순위표가 실제와 다르게 나온다.

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            ...
    """
    day_after = calendar_kst.today() + timedelta(days=1)
    return lambda: day_after


class PlanTest(TestCase):
    """길이별 문제 수와 보너스."""

    def test_longer_lengths_give_more_of_both(self):
        """길게 고를수록 문제도 보너스도 많아야 한다.

        보너스가 전부 같으면 짧은 것을 고르는 쪽이 항상 이득이라 긴
        선택지가 죽는다. 어느 것을 골라도 손해가 없어야 자기 사정에
        맞춰 고른다.
        """
        short = STUDY_PLANS[StudyLength.SHORT]
        medium = STUDY_PLANS[StudyLength.MEDIUM]
        long_ = STUDY_PLANS[StudyLength.LONG]

        self.assertLess(short[0], medium[0], "문제 수가 안 늘어난다")
        self.assertLess(medium[0], long_[0], "문제 수가 안 늘어난다")
        self.assertLess(short[1], medium[1], "보너스가 안 늘어난다")
        self.assertLess(medium[1], long_[1], "보너스가 안 늘어난다")

    def test_the_plan_matches_what_was_promised(self):
        """화면에 약속한 숫자 그대로여야 한다.

        단조성만 보면 (1,1)/(2,2)/(3,3) 으로 바뀌어도 통과한다. 이 값들은
        순위표 점수에 그대로 꽂히므로 조용히 바뀌면 아무도 모른다.
        """
        self.assertEqual(STUDY_PLANS[StudyLength.SHORT], (10, 5))
        self.assertEqual(STUDY_PLANS[StudyLength.MEDIUM], (25, 10))
        self.assertEqual(STUDY_PLANS[StudyLength.LONG], (40, 25))

    def test_an_unknown_length_is_refused(self):
        with self.assertRaises(SessionError):
            daily_study.plan_of("1h")


class OncePerDayTest(TestCase):
    """하루 한 번."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("하루한번")

    def test_starting_twice_is_refused(self):
        """두 번째 시작은 거절한다. 화면은 그때 결과를 보여준다."""
        daily_study.start(self.user, StudyLength.SHORT)

        with self.assertRaises(SessionError):
            daily_study.start(self.user, StudyLength.SHORT)

    def test_the_constraint_not_the_code_enforces_it(self):
        """제약이 막는 것이지 코드가 검사하는 것이 아니다.

        코드로 "있으면 거절" 하면 동시에 두 번 눌렀을 때 둘 다 통과하는
        창이 생긴다. 행을 직접 만들어 제약이 실제로 걸려 있는지 본다.
        """
        today = calendar_kst.today()
        DailyStudy.objects.create(
            user=self.user, day=today, length=StudyLength.SHORT, total_questions=10
        )

        with self.assertRaises(IntegrityError):
            DailyStudy.objects.create(
                user=self.user, day=today, length=StudyLength.LONG, total_questions=40
            )

    def test_yesterday_does_not_block_today(self):
        """어제 한 것이 오늘을 막으면 안 된다."""
        DailyStudy.objects.create(
            user=self.user,
            day=calendar_kst.today() - timedelta(days=1),
            length=StudyLength.SHORT,
            total_questions=10,
        )

        study, _, _ = daily_study.start(self.user, StudyLength.SHORT)

        self.assertEqual(study.day, calendar_kst.today())


class ScoringTest(TestCase):
    """점수 규칙."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("점수")

    def test_a_wrong_answer_never_subtracts(self):
        """틀려도 점수가 깎이지 않는다.

        자유 문제풀이는 -1 이다. 여기서 깎으면 모르는 것을 만날수록
        손해라 매일 오지 않는다.

        **score >= 0 을 보면 안 된다.** 완주 보너스가 5 라 감점이 있어도
        그 조건은 참이다. 맞힌 개수와 정확히 같은지를 본다.
        """
        from .tests_daily_study_edge import answer_wrong

        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 늘 틀린 보기를 고른다. "첫 보기" 로 풀면 우연히 다 맞을 수
        # 있어(4지선다 10문제면 100만분의 1) 감점 여부를 검사 못 한다.
        while question is not None:
            _, token, question, _s = answer_wrong(self.user, token, question)

        study.refresh_from_db()
        self.assertEqual(study.correct, 0, "틀리게 풀었는데 맞은 것이 있다")
        self.assertEqual(
            study.score,
            study.bonus,
            f"보너스 {study.bonus} 와 다르다 - 틀린 답에서 점수가 깎였다",
        )

    def test_finishing_adds_the_bonus(self):
        """다 풀면 보너스가 붙는다."""
        study = run_to_end(self.user, StudyLength.SHORT)

        bonus = STUDY_PLANS[StudyLength.SHORT][1]
        self.assertTrue(study.is_done, "안 끝났다")
        self.assertEqual(study.score, study.correct + bonus, "보너스가 안 붙었다")

    def test_the_score_lands_on_the_daily_row(self):
        """끝난 점수가 그날 줄에 옮겨진다. 꾸준함 순위표가 그걸 읽는다."""
        study = run_to_end(self.user, StudyLength.SHORT)

        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())
        self.assertEqual(row.daily_study_score, study.score)


class ProgressTest(TestCase):
    """푼 만큼 남는지, 되돌리기가 막히는지."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("중간이탈")

    def test_leaving_midway_keeps_what_was_earned(self):
        """세 문제만 풀고 나가도 그만큼 남는다.

        끝내기를 클라이언트에 맡기면 여기서 0 이 되고, 점수가 나쁜 판을
        버리는 것이 이득이 된다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(3):
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()

        self.assertEqual(study.answered, 3, "푼 것이 안 남았다")
        self.assertFalse(study.is_done, "아직 끝난 것이 아니다")

    def test_another_users_token_cannot_answer_my_study(self):
        """남의 토큰으로 내 판에 답할 수 없다.

        계정을 하나 더 만들어 거기서 정답을 알아낸 뒤 그 토큰을 내 계정으로
        보내면, 순번 방어만으로는 통과한다 - 둘 다 같은 순번에 있기 때문이다.
        토큰이 자기 판을 밝히고 그 판의 주인을 함께 보는 것이 이걸 막는다.
        """
        other = make_user("남")
        mine, _, _ = daily_study.start(self.user, StudyLength.SHORT)
        _, their_token, their_question = daily_study.start(other, StudyLength.SHORT)

        # 남의 계정으로 답해 정답을 알아낸다.
        daily_study.answer(other, their_token, their_question["choices"][0]["id"])

        # 그 토큰을 내 계정으로 보낸다.
        with self.assertRaises(SessionError):
            daily_study.answer(
                self.user, their_token, their_question["choices"][0]["id"]
            )

        mine.refresh_from_db()
        self.assertEqual(mine.answered, 0, "남의 토큰이 내 판을 채웠다")

    def test_yesterdays_open_study_is_settled_when_today_starts(self):
        """어제 못 끝낸 판은 오늘 시작할 때 정산한다.

        안 그러면 그 판이 영원히 열린 채 남는다. 열린 판이 둘이면 이어풀기가
        늘 최신 것을 집어, 어제 판은 40문제를 다 풀었어도 완주 보너스를
        못 받는다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, token, picked)

        # 하루 뒤에 다시 들어온다. 어제 판은 그대로 두고 시계만 민다.
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "어제 판이 아직 열려 있다")

    def test_a_study_started_yesterday_can_still_be_answered(self):
        """자정을 넘겨도 이어서 푼다.

        제한 시간이 없는 공부라 23:50 에 30분짜리를 시작하는 것이 권장
        사용법이다. 날짜로 판을 찾으면 자정에 토큰이 통째로 죽고, 그 판은
        열린 채 남아 끝내지도 못한다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        picked = question["choices"][0]["id"]
        _, token, question, _s = daily_study.answer(self.user, token, picked)

        # 자정을 넘긴다. 판은 어제 것 그대로고 시계만 오늘로 온다.
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertEqual(study.answered, 2, "자정을 넘기니 못 이어 푼다")

    def test_progress_reaches_the_score_board_before_finishing(self):
        """끝내기 전에도 점수판에 닿는다.

        "푼 만큼 남는다" 가 DailyStudy 표까지만 참이면 반쪽이다. 중간에
        그만둔 사람은 쌓아둔 점수가 있는데 순위표에서 0 이 된다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(3):
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        row = DailyScore.objects.filter(user=self.user, day=study.day).first()

        self.assertIsNotNone(row, "점수판에 행이 없다")
        self.assertEqual(row.daily_study_score, study.score, "점수판과 판이 다르다")
        self.assertFalse(study.is_done, "아직 끝난 것이 아니다")

    def test_an_unfinished_study_gets_no_bonus(self):
        """안 끝냈으면 보너스가 없다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, token, picked)

        study.refresh_from_db()

        self.assertLessEqual(study.score, 1, "안 끝났는데 보너스가 붙었다")

    def test_the_same_token_cannot_be_answered_twice(self):
        """옛 토큰을 다시 보내면 거절한다.

        **진행 개수만 보는 것으로는 부족하다.** 옛 토큰을 보내도 answered
        는 늘어나지만, 그때 correct 도 같이 늘어난다. 첫 답의 응답이 정답을
        알려주므로 같은 토큰에 그 답을 실어 다시 보내면 확실히 +1 이다.
        문제 수로 끝나는 규칙이라 절반만 탐색해도 만점이 된다.

        순번을 원자적으로 가져가는 것이 이걸 막는다.
        """
        _, first_token, question = daily_study.start(self.user, StudyLength.SHORT)

        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, first_token, picked)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, first_token, picked)

    def test_every_choice_cannot_be_tried_on_one_token(self):
        """같은 토큰으로 보기를 하나씩 다 넣어볼 수 없다.

        토큰 소비가 없으면 네 보기를 전부 시도할 수 있고 그중 하나는
        반드시 맞는다. 정답을 몰라도 문제마다 +1 이 된다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)

        daily_study.answer(self.user, token, question["choices"][0]["id"])

        for choice in question["choices"][1:]:
            with self.assertRaises(SessionError):
                daily_study.answer(self.user, token, choice["id"])

    def test_answering_past_the_total_is_refused(self):
        """문제 수를 넘겨 답할 수 없다.

        마지막 문제에 두 답이 겹치면 answered 가 total 을 넘고 그만큼
        점수가 는다. 정상 흐름만 보면 이 검사가 안 된다 - 순서대로 풀면
        어차피 안 넘치기 때문이다. **끝난 뒤 한 번 더 밀어넣는다.**
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        last_token = token
        while question is not None:
            last_token = token
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, last_token, picked)

        study.refresh_from_db()
        before = (study.answered, study.score)

        # 끝난 판에 마지막 토큰을 다시 보낸다.
        with self.assertRaises(SessionError):
            daily_study.answer(self.user, last_token, 1)

        study.refresh_from_db()
        self.assertEqual((study.answered, study.score), before, "끝난 뒤에 더 셌다")
        self.assertEqual(study.answered, study.total_questions, "초과해서 셌다")


class ApiTest(TestCase):
    """엔드포인트 두 개."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("api사람")

    def test_a_guest_cannot_use_it(self):
        """로그인해야 쓴다. 진행이 DB 에 남는 기능이다."""
        self.assertIn(self.client.get(START_URL).status_code, (401, 403))
        self.assertIn(self.client.post(START_URL, {}).status_code, (401, 403))

    def test_the_lengths_come_with_their_numbers(self):
        """화면이 고르기 전에 문제 수와 보너스를 보여줄 수 있어야 한다."""
        self.client.force_login(self.user)

        body = self.client.get(START_URL).json()

        self.assertEqual(len(body["lengths"]), len(StudyLength.choices))
        self.assertIsNone(body["today"], "시작 전인데 오늘 줄이 있다")
        for row in body["lengths"]:
            self.assertEqual(
                set(row), {"value", "label", "questions", "bonus"}, "칸이 바뀌었다"
            )

    def test_a_full_run_ends_by_itself(self):
        """마지막 문제를 풀면 서버가 닫는다. 끝내기 요청이 없다."""
        self.client.force_login(self.user)

        data = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()
        token = data["token"]

        total = STUDY_PLANS[StudyLength.SHORT][0]
        for _ in range(total):
            picked = data["question"]["choices"][0]["id"]
            data = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": picked},
                content_type="application/json",
            ).json()
            token = data.get("token")
            if data["finished"]:
                break

        self.assertTrue(data["finished"], "다 풀었는데 안 끝났다")
        self.assertIsNone(data["question"])
        self.assertTrue(data["study"]["done"])

    def test_starting_again_today_is_refused(self):
        """이미 했으면 막는다. 화면은 GET 으로 결과를 본다."""
        self.client.force_login(self.user)
        self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )

        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("이미", res.json()["detail"])
        self.assertIsNotNone(self.client.get(START_URL).json()["today"])

    def test_an_unknown_length_is_refused(self):
        self.client.force_login(self.user)

        res = self.client.post(
            START_URL, {"length": "1h"}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 400)
