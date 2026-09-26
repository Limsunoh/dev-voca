"""복습.

**점수가 없는 판이다.** 정답을 이미 본 문제가 나오므로 점수를 주면 아는
것만 골라 푸는 길이 열린다. 그래서 순위표에 안 들어간다.
"""

from __future__ import annotations

import secrets
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from unittest import mock
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import record, review, session
from .models import DailyScore, QuizAnswer, QuizSession, ReviewState, RoundStep
from .session import SessionError

PASSWORD = secrets.token_urlsafe(16)

START_URL = "/api/learning/review/"
ANSWER_URL = "/api/learning/review/answer/"


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def seed_words(count: int = 40) -> None:
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


def a_round(user, answers) -> None:
    """자유 문제풀이 한 판을 기록한다. answers 는 (단어pk, 맞았나) 목록."""
    record.save_round(
        user,
        {
            "kind": "free",
            "token_id": secrets.token_hex(8),
            "started_at": timezone.now(),
            "score": 0,
            "answered": len(answers),
            "correct": sum(1 for _pk, ok in answers if ok),
            "skipped": 0,
            "answers": [
                ("meaning", "word", pk, ok, False, 1000, 1 if ok else -1)
                for pk, ok in answers
            ],
        },
    )


class WriteBackTest(TestCase):
    """자유 문제풀이가 복습 목록을 채우는가."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("쓰기경로")

    def test_a_finished_round_fills_the_review_list(self):
        """판을 끝내면 푼 항목들이 복습 표에 남는다.

        이 쓰기가 없으면 복습 화면은 영원히 빈 목록이다 - 모델만 있고
        행을 만드는 코드가 없는 자리가 된다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(words[0], False), (words[1], True), (words[2], False)])

        self.assertEqual(ReviewState.objects.filter(user=self.user).count(), 3)

    def test_only_the_wrong_ones_are_due_right_away(self):
        """방금 맞힌 것은 복습에 안 나온다. 틀린 것만 나온다."""
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(words[0], False), (words[1], True), (words[2], True)])

        due = review.due_of(self.user)

        self.assertEqual([row.target_id for row in due], [words[0]])

    def test_a_skipped_answer_does_not_enter_the_list(self):
        """넘긴 것은 안 넣는다. 몰라서인지 시간이 없어서인지 모른다."""
        word = Word.objects.first()
        record.save_round(
            self.user,
            {
                "kind": "free",
                "token_id": secrets.token_hex(8),
                "started_at": timezone.now(),
                "score": 0,
                "answered": 1,
                "correct": 0,
                "skipped": 1,
                "answers": [("meaning", "word", word.pk, False, True, 1000, 0)],
            },
        )

        self.assertEqual(ReviewState.objects.filter(user=self.user).count(), 0)

    def test_the_same_item_twice_in_one_round_keeps_the_last_result(self):
        """한 판에 같은 항목이 두 번 나오면 마지막 결과가 남는다."""
        word = Word.objects.first()
        a_round(self.user, [(word.pk, False), (word.pk, True)])

        row = ReviewState.objects.get(user=self.user, target_id=word.pk)
        self.assertFalse(row.is_wrong, "마지막에 맞혔는데 틀린 것으로 남았다")

    def test_a_word_and_a_sentence_with_the_same_id_do_not_collide(self):
        """단어 5번과 문장 5번은 다른 항목이다.

        id 만으로 찾으면 하나를 고치려다 다른 하나를 덮는다.
        """
        word = Word.objects.first()
        ReviewState.objects.create(
            user=self.user,
            target_type="sentence",
            target_id=word.pk,
            is_wrong=True,
        )

        a_round(self.user, [(word.pk, True)])

        sentence_row = ReviewState.objects.get(
            user=self.user, target_type="sentence", target_id=word.pk
        )
        self.assertTrue(sentence_row.is_wrong, "문장 줄이 단어 결과로 덮였다")


class GraduationTest(TestCase):
    """연속 두 번 맞혀야 목록에서 빠진다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("졸업")
        self.word = Word.objects.first()
        a_round(self.user, [(self.word.pk, False)])

    def test_one_correct_answer_does_not_graduate(self):
        """한 번 맞힌 것으로는 안 빠진다. 찍어서 맞혔을 수 있다."""
        review._record(self.user, "word", self.word.pk, correct=True)

        due = review.due_of(self.user)
        self.assertEqual([row.target_id for row in due], [self.word.pk])

    def test_two_in_a_row_graduates(self):
        """연속 두 번이면 빠진다."""
        review._record(self.user, "word", self.word.pk, correct=True)
        streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertEqual(streak, 2)
        self.assertTrue(graduated)
        self.assertEqual(review.due_of(self.user), [])

    def test_a_wrong_answer_resets_the_streak(self):
        """중간에 틀리면 처음부터 다시 센다."""
        review._record(self.user, "word", self.word.pk, correct=True)
        review._record(self.user, "word", self.word.pk, correct=False)
        streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertEqual(streak, 1, "틀렸는데 연속이 안 끊겼다")
        self.assertFalse(graduated)

    def test_a_free_round_does_not_raise_the_streak(self):
        """자유 문제풀이에서 맞힌 것은 연속을 올리지 않는다.

        복습은 정답을 이미 본 자리라 그 둘을 갈라야 목록이 의미를 갖는다.
        """
        a_round(self.user, [(self.word.pk, True)])
        a_round(self.user, [(self.word.pk, True)])

        row = ReviewState.objects.get(user=self.user, target_id=self.word.pk)
        self.assertEqual(row.streak, 0, "자유 문제풀이가 연속을 올렸다")


class StaleTest(TestCase):
    """오래된 것도 복습에 나온다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("오래됨")
        self.word = Word.objects.first()

    def test_something_answered_long_ago_comes_back(self):
        """맞혔어도 7일이 지나면 다시 나온다."""
        row = ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=timezone.now() - timedelta(days=review.STALE_DAYS + 1),
        )

        due = review.due_of(self.user)
        self.assertEqual([one.pk for one in due], [row.pk])

    def test_something_answered_recently_stays_out(self):
        """어제 맞힌 것은 안 나온다."""
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=timezone.now() - timedelta(days=1),
        )

        self.assertEqual(review.due_of(self.user), [])

    def test_the_wrong_ones_come_before_the_stale_ones(self):
        """틀린 것을 먼저 낸다. 모르는 것부터 다룬다."""
        words = list(Word.objects.values_list("pk", flat=True)[:2])
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=words[0],
            is_wrong=False,
            last_correct_at=timezone.now() - timedelta(days=30),
        )
        ReviewState.objects.create(
            user=self.user, target_type="word", target_id=words[1], is_wrong=True
        )

        due = review.due_of(self.user)
        self.assertEqual(due[0].target_id, words[1], "오래된 것이 먼저 나왔다")


class RoundTest(TestCase):
    """판 진행."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("판진행")
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

    def test_a_round_asks_exactly_what_is_due(self):
        """복습할 것이 셋이면 세 문제가 나온다."""
        token, question, total = review.start(self.user)

        self.assertEqual(total, 3)

        asked = 0
        while question is not None:
            asked += 1
            picked = question["choices"][0]["id"]
            _result, token, question = review.answer(self.user, token, picked)

        self.assertEqual(asked, 3)

    def test_nothing_to_review_is_refused(self):
        """복습할 것이 없으면 시작할 수 없다."""
        ReviewState.objects.filter(user=self.user).delete()

        with self.assertRaises(SessionError):
            review.start(self.user)

    def test_the_question_is_about_the_item_being_reviewed(self):
        """복습 문제의 정답은 복습 목록의 그 항목이어야 한다.

        무작위로 고르면 복습이 아니라 그냥 문제풀이다.
        """
        due = review.due_of(self.user)
        wanted = {row.target_id for row in due}

        token, question, _total = review.start(self.user)

        answered = []
        while question is not None:
            picked = question["choices"][0]["id"]
            result, token, question = review.answer(self.user, token, picked)
            answered.append(result.answer_text)

        terms = set(Word.objects.filter(pk__in=wanted).values_list("term", flat=True))
        self.assertTrue(
            set(answered) <= terms, f"복습 목록 밖의 문제가 나왔다. {answered}"
        )

    def test_another_users_token_is_refused(self):
        """남의 토큰으로 내 연속 횟수를 올릴 수 없다."""
        other = make_user("남")
        token, question, _total = review.start(self.user)

        with self.assertRaises(SessionError):
            review.answer(other, token, question["choices"][0]["id"])

    def test_review_does_not_touch_the_score_board(self):
        """복습은 점수판을 안 건드린다. 순위표에 안 들어간다."""
        before = DailyScore.objects.filter(user=self.user).count()

        token, question, _total = review.start(self.user)
        while question is not None:
            picked = question["choices"][0]["id"]
            _result, token, question = review.answer(self.user, token, picked)

        self.assertEqual(DailyScore.objects.filter(user=self.user).count(), before)
        self.assertEqual(
            QuizSession.objects.filter(user=self.user).count(),
            1,
            "복습이 판을 기록했다 - 순위표에 들어간다",
        )


class ApiTest(TestCase):
    """엔드포인트."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("에이피아이")
        self.client.force_login(self.user)

    def test_login_is_required(self):
        """로그인 없이는 못 쓴다."""
        self.client.logout()

        self.assertEqual(self.client.get(START_URL).status_code, 401)
        self.assertEqual(self.client.post(START_URL).status_code, 401)

    def test_the_count_is_shown_before_starting(self):
        """시작 전에 몇 개 남았는지 본다."""
        words = list(Word.objects.values_list("pk", flat=True)[:2])
        a_round(self.user, [(pk, False) for pk in words])

        body = self.client.get(START_URL).json()

        self.assertEqual(body["due"], 2)
        self.assertEqual(body["round_size"], review.ROUND_SIZE)

    def test_the_graduate_streak_is_told_to_the_screen(self):
        """졸업 기준을 화면에 알려준다.

        화면이 "한 번 더 맞히면 끝" 을 이 값으로 센다. 안 주면 화면이
        2 를 박아두게 되고, 기준을 3 으로 올린 날 화면만 옛말을 계속한다 -
        실제로는 두 번 더 맞혀야 하는데 틀렸다는 신호가 어디에도 안 뜬다.
        """
        body = self.client.get(START_URL).json()

        self.assertEqual(body["graduate_streak"], review.GRADUATE_STREAK)

    def test_starting_with_nothing_due_is_a_400(self):
        """복습할 것이 없으면 400 이지 500 이 아니다."""
        got = self.client.post(START_URL)

        self.assertEqual(got.status_code, 400)

    def test_a_bool_choice_id_is_refused(self):
        """True 가 1 번 보기로 통과하면 안 된다."""
        word = Word.objects.first()
        a_round(self.user, [(word.pk, False)])
        token = self.client.post(START_URL).json()["token"]

        got = self.client.post(
            ANSWER_URL,
            {"token": token, "choice_id": True},
            content_type="application/json",
        )

        self.assertEqual(got.status_code, 400)

    def test_a_junk_token_is_refused(self):
        """다른 기능의 토큰이나 쓰레기 값을 넣어도 500 이 아니다."""
        got = self.client.post(
            ANSWER_URL,
            {"token": "아무거나", "choice_id": 1},
            content_type="application/json",
        )

        self.assertEqual(got.status_code, 400)


def seed_sentences(count: int = 12) -> None:
    """상황 문제를 낼 수 있는 문장. 보기가 넷이라 상황이 서로 달라야 한다."""
    Sentence.objects.bulk_create(
        Sentence(
            text=f"sentence text {i}",
            translation=f"해석{i}",
            context=f"상황{i}",
            is_reviewed=True,
        )
        for i in range(count)
    )


class DueConditionTest(TestCase):
    """_due 의 세 갈래가 조합에서도 성립하는가.

    네 가지가 동시에 맞아야 한다 - 하나를 고치다 다른 하나를 깨뜨리기
    쉬운 자리다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("대상조건")
        self.words = list(Word.objects.values_list("pk", flat=True)[:4])

    def _state(self, pk, **kwargs):
        return ReviewState.objects.create(
            user=self.user, target_type="word", target_id=pk, **kwargs
        )

    def test_the_four_cases_hold_together(self):
        """자유 정답은 빠지고, 복습 1회는 남고, 2회는 빠지고, 오래되면 돌아온다."""
        now = timezone.now()
        # 자유 문제풀이에서 방금 맞힌 것. streak 을 안 올리므로 0 이다.
        self._state(self.words[0], streak=0, is_wrong=False, last_correct_at=now)
        # 복습에서 한 번 맞힌 것.
        self._state(self.words[1], streak=1, is_wrong=False, last_correct_at=now)
        # 복습에서 두 번 맞혀 졸업한 것.
        self._state(
            self.words[2],
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=now,
        )
        # 졸업했지만 오래된 것.
        self._state(
            self.words[3],
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=now - timedelta(days=review.STALE_DAYS + 1),
        )

        due = {row.target_id for row in review.due_of(self.user)}

        self.assertNotIn(self.words[0], due, "자유 문제풀이에서 방금 맞힌 것이 나왔다")
        self.assertIn(self.words[1], due, "복습에서 한 번 맞힌 것이 빠졌다")
        self.assertNotIn(self.words[2], due, "연속 두 번 맞힌 것이 남았다")
        self.assertIn(self.words[3], due, "졸업했어도 오래되면 다시 나와야 한다")

    def test_the_stale_boundary(self):
        """7일 경계. 6일 23시간은 안 나오고 7일이 지나면 나온다."""
        now = timezone.now()
        self._state(
            self.words[0],
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=now - timedelta(days=review.STALE_DAYS, seconds=5),
        )
        self._state(
            self.words[1],
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=now - timedelta(days=review.STALE_DAYS) + timedelta(hours=1),
        )

        due = {row.target_id for row in review.due_of(self.user)}

        self.assertIn(self.words[0], due)
        self.assertNotIn(self.words[1], due)

    def test_a_row_that_was_never_answered_correctly_is_due(self):
        """한 번도 못 맞힌 것(last_correct_at 없음)은 나온다."""
        self._state(self.words[0], streak=0, is_wrong=False, last_correct_at=None)

        self.assertEqual(
            [row.target_id for row in review.due_of(self.user)], [self.words[0]]
        )

    def test_another_users_rows_never_leak(self):
        """남의 복습 상태는 내 목록에도 개수에도 안 들어온다."""
        other = make_user("남의상태")
        a_round(other, [(pk, False) for pk in self.words])

        self.assertEqual(review.count_due(self.user), 0)
        self.assertEqual(review.due_of(self.user), [])


class CountMatchesListTest(TestCase):
    """count_due 와 due_of 가 같은 조건을 보는가."""

    def setUp(self):
        cache.clear()
        seed_words(60)
        self.user = make_user("개수일치")

    def test_the_count_matches_the_list_when_under_the_round_size(self):
        """한 판에 들어가는 양이면 개수와 목록이 정확히 같다."""
        words = list(Word.objects.values_list("pk", flat=True)[:5])
        a_round(self.user, [(pk, False) for pk in words])

        self.assertEqual(review.count_due(self.user), len(review.due_of(self.user)))

    def test_the_list_is_capped_at_the_round_size(self):
        """대상이 한 판보다 많으면 목록만 잘린다. 개수는 전체를 말한다.

        화면이 "N개 남음" 과 "이번 판 M문제" 를 다른 값으로 그려야 한다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:30])
        a_round(self.user, [(pk, False) for pk in words])

        self.assertEqual(review.count_due(self.user), 30)
        self.assertEqual(len(review.due_of(self.user)), review.ROUND_SIZE)

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(START_URL).json()["due"], 30)
        self.assertEqual(
            self.client.post(START_URL).json()["total"], review.ROUND_SIZE
        )


class ReviewGateTest(TestCase):
    """검수 안 된 항목이 복습으로 새는가.

    복습 목록은 지난 답에서 오므로, 그 뒤 검수에서 내려간 항목이 섞여
    있을 수 있다. 정답으로도 보기로도 나오면 안 된다.
    """

    def setUp(self):
        cache.clear()
        seed_words(60)
        self.user = make_user("검수게이트")

    def test_an_unreviewed_target_cannot_start_a_round(self):
        """대상이 검수에서 내려갔으면 그것만으로는 판이 안 열린다."""
        word = Word.objects.first()
        ReviewState.objects.create(
            user=self.user, target_type="word", target_id=word.pk, is_wrong=True
        )
        Word.objects.filter(pk=word.pk).update(is_reviewed=False)

        with self.assertRaises(SessionError):
            review.start(self.user)

    def test_an_unreviewed_word_never_appears_as_a_choice(self):
        """검수 안 된 단어가 오답 보기로도 안 나온다."""
        words = list(Word.objects.values_list("pk", flat=True))
        hidden = set(words[30:])
        Word.objects.filter(pk__in=hidden).update(is_reviewed=False)
        a_round(self.user, [(pk, False) for pk in words[:5]])

        token, question, _total = review.start(self.user)
        seen = set()
        while question is not None:
            seen |= {choice["id"] for choice in question["choices"]}
            _result, token, question = review.answer(
                self.user, token, question["choices"][0]["id"]
            )

        self.assertFalse(seen & hidden, "검수 안 된 단어가 보기로 새어나왔다")

    def test_a_target_pulled_mid_round_is_skipped(self):
        """판이 열린 뒤 검수에서 내려가면 그 문제를 건너뛴다."""
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        token, question, _total = review.start(self.user)
        Word.objects.filter(pk__in=words).update(is_reviewed=False)

        _result, _next_token, next_question = review.answer(
            self.user, token, question["choices"][0]["id"]
        )

        self.assertIsNone(next_question, "검수에서 내려간 항목이 계속 나왔다")

    def test_a_pulled_target_is_not_named_as_the_answer(self):
        """검수에서 내려간 항목을 정답이라고 알려주지 않는다."""
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        token, question, _total = review.start(self.user)
        Word.objects.filter(pk__in=words).update(is_reviewed=False)

        result, _next_token, _next_question = review.answer(
            self.user, token, question["choices"][0]["id"]
        )

        self.assertEqual(result.answer_text, "", "검수 취소된 단어를 정답으로 보여줬다")

    def test_a_vanished_target_is_skipped_without_repeating_the_next_one(self):
        """가운데 항목이 사라지면 건너뛰되, 뒤 항목을 두 번 내지 않는다.

        건너뛴 자리를 토큰에 반영하지 않으면 다음 요청이 같은 자리에서
        다시 세어, 뒤 항목이 두 번 나오고 판이 안 줄어든다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        due_ids = [row.target_id for row in review.due_of(self.user)]
        token, question, _total = review.start(self.user)

        # 아직 문제로 만들어지지 않은 가운데 자리를 검수에서 내린다.
        Word.objects.filter(pk=due_ids[1]).update(is_reviewed=False)

        asked = []
        while question is not None:
            result, token, question = review.answer(
                self.user, token, question["choices"][0]["id"]
            )
            asked.append(result.answer_text)

        self.assertEqual(
            len(asked), len(set(asked)), f"같은 항목이 두 번 출제됐다. {asked}"
        )

    def test_a_missing_first_target_does_not_repeat_the_second(self):
        """첫 대상이 사라진 채 시작해도 두 번째가 두 번 나오지 않는다."""
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        due_ids = [row.target_id for row in review.due_of(self.user)]
        Word.objects.filter(pk=due_ids[0]).update(is_reviewed=False)

        token, question, _total = review.start(self.user)

        asked = []
        while question is not None:
            result, token, question = review.answer(
                self.user, token, question["choices"][0]["id"]
            )
            asked.append(result.answer_text)

        self.assertEqual(
            len(asked), len(set(asked)), f"같은 항목이 두 번 출제됐다. {asked}"
        )


class TargetTypeTest(TestCase):
    """단어 5번과 문장 5번이 섞이는가."""

    def setUp(self):
        cache.clear()
        seed_words()
        seed_sentences()
        self.user = make_user("종류구분")

    def test_a_word_and_a_sentence_with_the_same_id_get_separate_questions(self):
        """id 가 겹쳐도 둘은 다른 항목이라 각각 나온다."""
        target_id = Word.objects.first().pk
        if not Sentence.objects.filter(pk=target_id).exists():
            Sentence.objects.create(
                id=target_id,
                text="collide text",
                translation="해석",
                context="충돌 상황",
                is_reviewed=True,
            )

        ReviewState.objects.create(
            user=self.user, target_type="word", target_id=target_id, is_wrong=True
        )
        ReviewState.objects.create(
            user=self.user, target_type="sentence", target_id=target_id, is_wrong=True
        )

        token, question, total = review.start(self.user)
        answered_types = []
        while question is not None:
            result, token, question = review.answer(
                self.user, token, question["choices"][0]["id"]
            )
            answered_types.append(result.answer_type)

        self.assertEqual(total, 2)
        self.assertEqual(sorted(answered_types), ["sentence", "word"])
        self.assertEqual(
            ReviewState.objects.filter(user=self.user).count(),
            2,
            "종류가 섞여 두 줄이 하나로 합쳐졌다",
        )

    def test_a_sentence_review_updates_the_sentence_row(self):
        """문장 복습이 문장 줄을 고친다. 같은 id 의 단어 줄을 만들지 않는다."""
        sentence = Sentence.objects.first()
        ReviewState.objects.create(
            user=self.user,
            target_type="sentence",
            target_id=sentence.pk,
            is_wrong=True,
        )

        token, question, _total = review.start(self.user)
        result, _next_token, _next_question = review.answer(
            self.user, token, question["choices"][0]["id"]
        )

        self.assertEqual(result.answer_type, "sentence")
        self.assertEqual(
            ReviewState.objects.filter(user=self.user, target_type="word").count(),
            0,
            "문장 복습이 단어 줄을 만들었다",
        )


class WriteBackEdgeTest(TestCase):
    """_bump_review 의 경계."""

    def setUp(self):
        cache.clear()
        seed_words(60)
        self.user = make_user("쓰기경계")

    def test_recording_the_same_round_twice_keeps_one_row_each(self):
        """같은 판을 두 번 기록해도 항목마다 한 줄이다."""
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        summary = {
            "kind": "free",
            "token_id": secrets.token_hex(8),
            "started_at": timezone.now(),
            "score": 0,
            "answered": len(words),
            "correct": 0,
            "skipped": 0,
            "answers": [
                ("meaning", "word", pk, False, False, 1000, -1) for pk in words
            ],
        }

        record.save_round(self.user, summary)
        second = record.save_round(self.user, summary)

        self.assertIsNone(second, "같은 판이 두 번 기록됐다")
        self.assertEqual(ReviewState.objects.filter(user=self.user).count(), 3)

    def test_a_large_round_with_repeats_makes_one_row_per_item(self):
        """대량 답에 같은 항목이 여러 번 있어도 항목당 한 줄이다."""
        words = list(Word.objects.values_list("pk", flat=True))
        answers = [(words[i % len(words)], i % 2 == 0) for i in range(500)]

        a_round(self.user, answers)

        self.assertEqual(
            ReviewState.objects.filter(user=self.user).count(),
            len({pk for pk, _ok in answers}),
        )


class ScoreIsolationTest(TestCase):
    """복습이 점수·순위표에 흔적을 남기는가."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("점수격리")
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])
        self.client.force_login(self.user)

    def test_the_leaderboards_do_not_move(self):
        """순위표 셋을 실제로 불러 복습 전후가 같은지 본다."""
        boards = ("weekly", "all-time", "streak")
        before = {
            name: self.client.get(f"/api/learning/leaderboards/{name}/").json()
            for name in boards
        }
        sessions = QuizSession.objects.count()
        answers = QuizAnswer.objects.count()
        daily = list(
            DailyScore.objects.values(
                "user", "day", "best_free_score", "daily_study_score"
            )
        )

        token, question, _total = review.start(self.user)
        while question is not None:
            _result, token, question = review.answer(
                self.user, token, question["choices"][0]["id"]
            )

        self.assertEqual(QuizSession.objects.count(), sessions, "복습이 판을 남겼다")
        self.assertEqual(QuizAnswer.objects.count(), answers, "복습이 답을 남겼다")
        self.assertEqual(
            list(
                DailyScore.objects.values(
                    "user", "day", "best_free_score", "daily_study_score"
                )
            ),
            daily,
            "복습이 하루 점수를 바꿨다",
        )
        for name in boards:
            after = self.client.get(f"/api/learning/leaderboards/{name}/").json()
            self.assertEqual(after, before[name], f"{name} 순위표가 복습으로 바뀌었다")


class ApiEdgeTest(TestCase):
    """엔드포인트의 경계·남용."""

    def setUp(self):
        cache.clear()
        seed_words(60)
        self.user = make_user("에이피아이경계")
        self.client.force_login(self.user)
        self.word = Word.objects.first()
        a_round(self.user, [(self.word.pk, False)])

    def _start(self) -> str:
        return self.client.post(START_URL).json()["token"]

    def _answer(self, body: dict):
        return self.client.post(ANSWER_URL, body, content_type="application/json")

    def test_the_count_endpoint_is_fine_with_nothing_due(self):
        """복습할 것이 없어도 조회는 200 이다."""
        ReviewState.objects.filter(user=self.user).delete()

        got = self.client.get(START_URL)

        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["due"], 0)

    def test_a_missing_or_odd_token_is_a_400(self):
        """토큰이 없거나 문자열이 아니면 400 이지 500 이 아니다."""
        for body in (
            {},
            {"choice_id": 1},
            {"token": "", "choice_id": 1},
            {"token": 123, "choice_id": 1},
            {"token": None, "choice_id": 1},
        ):
            self.assertEqual(self._answer(body).status_code, 400, body)

    def test_a_body_that_is_not_an_object_is_a_400(self):
        """리스트를 본문으로 보내도 500 이 아니다."""
        got = self.client.post(ANSWER_URL, [1, 2], content_type="application/json")

        self.assertEqual(got.status_code, 400)

    def test_odd_choice_ids_never_500(self):
        """문자열·실수·리스트·null 은 400, 정수는 그냥 오답으로 처리된다."""
        token = self._start()
        for bad in ("1", None, [1], {"a": 1}, 1.5, True):
            self.assertEqual(
                self._answer({"token": token, "choice_id": bad}).status_code,
                400,
                f"choice_id={bad!r}",
            )

        # 정수는 그냥 오답으로 처리된다. **토큰마다 한 번씩** 본다 - 첫 답이
        # 순번을 태우므로 같은 토큰으로 이어 보내면 되돌리기로 거절된다.
        for odd in (-1, 0, 10**30):
            fresh = self._start()
            got = self._answer({"token": fresh, "choice_id": odd})
            self.assertEqual(got.status_code, 200, f"choice_id={odd!r}")
            self.assertFalse(
                got.json()["result"]["correct"], f"choice_id={odd!r} 이 정답이 됐다"
            )

    def test_a_token_from_another_feature_is_refused(self):
        """자유 문제풀이·일일공부 토큰을 복습에 넣을 수 없다."""
        free = self.client.post("/api/learning/rounds/").json()["token"]
        daily = self.client.post(
            "/api/learning/daily/", {"length": "5m"}, content_type="application/json"
        ).json()["token"]

        for token in (free, daily):
            self.assertEqual(
                self._answer({"token": token, "choice_id": 1}).status_code, 400
            )

    def test_another_users_token_leaves_no_trace(self):
        """남의 토큰은 거절되고 그 계정에 줄도 안 생긴다."""
        token = self._start()
        other = make_user("남의계정")
        self.client.force_login(other)

        got = self._answer({"token": token, "choice_id": 1})

        self.assertEqual(got.status_code, 400)
        self.assertEqual(ReviewState.objects.filter(user=other).count(), 0)

    def test_an_expired_token_is_a_400(self):
        """만료된 토큰은 400 이다."""
        token = self._start()
        original = review.TOKEN_MAX_AGE
        review.TOKEN_MAX_AGE = -1
        try:
            self.assertEqual(
                self._answer({"token": token, "choice_id": 1}).status_code, 400
            )
        finally:
            review.TOKEN_MAX_AGE = original

    def test_twenty_questions_in_a_row_are_not_throttled(self):
        """한 판 20문제를 쉬지 않고 풀어도 429 가 안 난다."""
        words = list(Word.objects.values_list("pk", flat=True)[:20])
        a_round(self.user, [(pk, False) for pk in words])

        body = self.client.post(START_URL).json()
        token, question = body["token"], body["question"]

        asked = 0
        while question is not None:
            got = self._answer(
                {"token": token, "choice_id": question["choices"][0]["id"]}
            )
            self.assertEqual(got.status_code, 200, f"{asked}번째에서 막혔다")
            body = got.json()
            token, question = body["token"], body["question"]
            asked += 1

        self.assertEqual(asked, review.ROUND_SIZE)


class StreakResetTest(TestCase):
    """자유 문제풀이에서 틀리면 복습 연속이 끊기는가.

    "연속 두 번" 은 **중간에 틀린 적이 없다** 는 뜻이다. 자유 문제풀이의
    오답이 연속을 안 끊으면, 틀린 뒤 복습 한 번만 맞혀도 졸업한다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("연속끊기")
        self.word = Word.objects.first()

    def test_a_free_round_miss_breaks_the_streak(self):
        """복습 1회 정답 뒤 자유에서 틀리면 연속이 0 으로 돌아간다."""
        a_round(self.user, [(self.word.pk, False)])
        review._record(self.user, "word", self.word.pk, correct=True)

        a_round(self.user, [(self.word.pk, False)])

        row = ReviewState.objects.get(
            user=self.user, target_type="word", target_id=self.word.pk
        )
        self.assertEqual(row.streak, 0, "자유 문제풀이 오답이 연속을 안 끊었다")

    def test_one_review_answer_after_a_miss_does_not_graduate(self):
        """틀린 뒤 복습 한 번 맞힌 것으로는 졸업하지 않는다."""
        a_round(self.user, [(self.word.pk, False)])
        review._record(self.user, "word", self.word.pk, correct=True)
        a_round(self.user, [(self.word.pk, False)])

        _streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertFalse(graduated, "틀린 뒤 한 번 맞혔는데 졸업했다")
        self.assertEqual(
            review.count_due(self.user), 1, "졸업하지 않았는데 목록에서 빠졌다"
        )

    def test_a_graduated_item_missed_again_needs_two_more(self):
        """졸업했던 것이 다시 틀리면 또 연속 두 번을 채워야 한다."""
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            streak=review.GRADUATE_STREAK,
            is_wrong=False,
            last_correct_at=timezone.now(),
        )
        a_round(self.user, [(self.word.pk, False)])

        _streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertFalse(graduated, "다시 틀린 것이 한 번 맞히자 곧장 졸업했다")


class ReplayTest(TestCase):
    """같은 토큰을 다시 보내 졸업할 수 있는가.

    복습 응답은 맞든 틀리든 정답을 알려준다. 보기를 하나씩 넣어 정답을
    캐낸 뒤 **같은 토큰**을 정답과 함께 다시 보내면, 한 문제로 연속을
    채워 목록에서 지울 수 있다. 자유 문제풀이는 RoundStep 으로 이 길을
    막았다(session.py).
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("되돌리기")
        self.client.force_login(self.user)
        self.word = Word.objects.first()
        a_round(self.user, [(self.word.pk, False)])

    def test_replaying_one_question_cannot_graduate_it(self):
        """한 문제를 되돌려 보내는 것만으로 목록에서 빠지면 안 된다."""
        body = self.client.post(START_URL).json()
        token = body["token"]

        # 보기를 하나씩 넣어 정답을 캐내려 한다. 첫 답이 순번을 태우므로
        # 두 번째부터는 400 이어야 한다 - 그래야 정답을 알아낼 수 없다.
        codes = []
        for choice in body["question"]["choices"]:
            got = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": choice["id"]},
                content_type="application/json",
            )
            codes.append(got.status_code)

        self.assertEqual(codes[0], 200, "첫 답이 거절됐다")
        self.assertTrue(
            all(code == 400 for code in codes[1:]),
            f"되돌린 토큰이 통과했다. {codes}",
        )

        self.assertGreater(
            review.count_due(self.user),
            0,
            "한 문제를 되돌려 보내는 것만으로 복습 목록에서 졸업했다",
        )

    def test_replay_is_still_refused_after_the_round_steps_are_swept(self):
        """판 청소가 돌아도 살아 있는 복습 토큰의 되돌리기는 막혀야 한다.

        RoundStep 은 자유 문제풀이와 복습이 같이 쓰는데, 청소가 판 토큰
        수명(10분)으로 나이를 재서 10분 지난 복습 표시를 지웠다. 복습
        토큰은 6시간 사므로 그 뒤 옛 토큰을 다시 보내면 통과했다. 복습 판
        식별자에 앞머리가 빠져도 이 테스트가 깨진다.
        """
        body = self.client.post(START_URL).json()
        token = body["token"]
        first = body["question"]["choices"][0]["id"]
        got = self.client.post(
            ANSWER_URL, {"token": token, "choice_id": first},
            content_type="application/json",
        )
        self.assertEqual(got.status_code, 200)

        # 11분 지났고, 그 사이 누가 판을 열어 청소가 돌았다.
        old = timezone.now() - timedelta(seconds=session.TOKEN_MAX_AGE + 60)
        RoundStep.objects.update(created_at=old)
        with mock.patch.object(session.random, "random", return_value=0.0):
            session._sweep_old_steps()

        again = self.client.post(
            ANSWER_URL, {"token": token, "choice_id": first},
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 400, "청소 뒤 옛 복습 토큰이 통과했다")

    def test_round_steps_outlive_every_token_that_uses_them(self):
        """표시를 두는 기간이 이 표를 쓰는 토큰 수명보다 짧으면 안 된다.

        짧으면 그 차이만큼 되돌리기가 열린다. 복습 토큰 수명을 늘리는
        사람이 여기서 멈추게 둔다.
        """
        self.assertGreater(session.LONG_STEP_KEEP_SECONDS, review.TOKEN_MAX_AGE)

    def test_review_rounds_are_marked_long_lived(self):
        """복습 판의 표시에는 앞머리가 붙는다. 청소가 그것으로 기간을 가른다."""
        body = self.client.post(START_URL).json()
        self.client.post(
            ANSWER_URL,
            {"token": body["token"], "choice_id": body["question"]["choices"][0]["id"]},
            content_type="application/json",
        )
        self.assertTrue(
            RoundStep.objects.get().round_id.startswith(session.LONG_ROUND_PREFIX)
        )


class BrokenPayloadTest(TestCase):
    """문제 정보가 망가진 토큰이 400 인가 500 인가.

    quiz.resolve_answer 는 알맹이가 망가지면 None 을 돌려준다. 그것을
    바로 두 값으로 풀면 TypeError 로 500 이 난다 - session.py 는 같은
    자리에서 None 을 먼저 본다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("깨진문제정보")
        self.client.force_login(self.user)

    def _answer_with(self, question_payload):
        state = {
            "u": self.user.pk,
            "q": question_payload,
            "t": [["word", Word.objects.first().pk]],
            "n": 0,
        }
        return self.client.post(
            ANSWER_URL,
            {"token": signing.dumps(state, salt=review._SALT), "choice_id": 1},
            content_type="application/json",
        )

    def test_a_broken_question_payload_is_a_400(self):
        """모양이 깨진 문제 정보는 400 이다."""
        for payload in (
            {},
            {"n": "x", "c": [1], "tt": "word"},
            {"a": "x", "n": "y", "c": [], "tt": "word"},
            {"a": "x", "n": "y", "c": "abc", "tt": "word"},
        ):
            self.assertEqual(
                self._answer_with(payload).status_code, 400, f"payload={payload}"
            )

    def test_a_payload_whose_answer_is_not_among_the_choices_is_a_400(self):
        """지문과 보기가 안 맞는 토큰도 400 이다.

        SECRET_KEY 를 돌리면(SECRET_KEY_FALLBACKS) 진행 중이던 복습
        토큰이 정확히 이 모양이 된다 - 서명은 옛 키로 풀리는데 문제
        지문은 새 키로 계산돼 어느 보기와도 안 맞는다.
        """
        got = self._answer_with(
            {"a": "deadbeef", "n": "nonce", "c": [1, 2, 3, 4], "tt": "word"}
        )

        self.assertEqual(got.status_code, 400)

    def test_a_round_in_flight_survives_a_secret_key_rotation(self):
        """키를 돌리는 중 진행하던 복습에 답해도 500 이 아니다."""
        word = Word.objects.first()
        a_round(self.user, [(word.pk, False)])
        token = self.client.post(START_URL).json()["token"]

        old_key = settings.SECRET_KEY
        with override_settings(
            SECRET_KEY="new-" + secrets.token_urlsafe(16),
            SECRET_KEY_FALLBACKS=[old_key],
        ):
            got = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": 1},
                content_type="application/json",
            )

        self.assertEqual(got.status_code, 400)

class SecondCycleTest(TestCase):
    """7일 뒤 돌아온 항목도 다시 두 번 맞혀야 빠진다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("두번째")
        self.word = Word.objects.first()

    def test_a_stale_item_still_needs_two_in_a_row(self):
        """첫 사이클에서 졸업했어도 두 번째 사이클은 처음부터다.

        연속 횟수에 상한이 없으면 첫 졸업 때 2 를 넘긴 값이 그대로 남아,
        7일 뒤 돌아온 항목이 **한 번만** 맞혀도 곧장 재졸업한다. 두 번째
        사이클부터 "연속 두 번" 규칙이 통째로 죽는 자리다.
        """
        # 첫 사이클: 복습에서 두 번 맞혀 졸업.
        review._record(self.user, "word", self.word.pk, correct=True)
        review._record(self.user, "word", self.word.pk, correct=True)
        self.assertEqual(review.count_due(self.user), 0, "첫 졸업이 안 됐다")

        # 7일이 지나 목록에 돌아온다.
        ReviewState.objects.filter(user=self.user, target_id=self.word.pk).update(
            last_correct_at=timezone.now() - timedelta(days=review.STALE_DAYS + 1)
        )
        self.assertEqual(review.count_due(self.user), 1, "7일 뒤에 안 돌아왔다")

        # 판을 열면 돌아온 항목의 연속이 0 으로 리셋된다.
        review.start(self.user)

        # 한 번 맞힌다. 아직 빠지면 안 된다.
        _streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertFalse(graduated, "두 번째 사이클에서 한 번에 졸업했다")
        self.assertEqual(
            review.count_due(self.user), 1, "한 번 맞히고 목록에서 빠졌다"
        )


class ProgressContractTest(TestCase):
    """화면이 진행률을 그리는 근거. 서버가 준 값만 쓴다.

    화면(ReviewBoard)은 answered/total 을 스스로 세지 않고 문제 본문에
    실려 온 것을 그대로 그린다. 그래서 이 두 값의 약속이 깨지면 화면이
    "17/20 에서 끝나는 20문제" 같은 것을 보여준다 - 화면 코드는 멀쩡한데
    숫자만 틀리는, 눈으로 잡기 어려운 자리다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("진행률")
        self.client.force_login(self.user)

    def test_the_first_question_starts_the_count_at_zero(self):
        """첫 문제의 answered 는 0 이다.

        1 로 시작하면 마지막 문제가 total+1 이 되어 "21/20" 이 뜬다.
        화면이 이 값에 1 을 더하지 않기로 한 약속의 반대편이다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        body = self.client.post(START_URL).json()

        self.assertEqual(body["question"]["answered"], 0)
        self.assertEqual(body["question"]["total"], 3)

    def test_a_vanished_target_still_moves_the_count_forward(self):
        """대상이 사라져 건너뛰어도 진행이 그만큼 앞선다.

        목록을 뽑은 뒤 단어가 검수에서 내려가면 서버가 그 자리를
        건너뛴다. 건너뛴 만큼 answered 가 안 오르면 다음 요청이 같은
        자리에서 또 건너뛰어 살아 있는 항목을 두 번 낸다 - 화면에는
        같은 문제가 연달아 나오고 진행률이 제자리걸음을 한다.

        가운데 하나만 내린다. 뒤에 살아 있는 것을 남겨야 판이 끝나지
        않고 "건너뛴 다음 자리" 가 실제로 나온다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:4])
        a_round(self.user, [(pk, False) for pk in words])

        started = self.client.post(START_URL).json()
        targets = self._targets(started["token"])
        total = started["question"]["total"]
        self.assertGreaterEqual(total, 3, "이 시나리오는 세 자리 이상이 필요하다")

        # 지금 낸 것이 0 번, 그 다음 1 번을 내린다. 2 번은 살려둔다.
        vanished = int(targets[1][1])
        survivor = int(targets[2][1])
        Word.objects.filter(pk=vanished).update(is_reviewed=False)

        got = self.client.post(
            ANSWER_URL,
            {"token": started["token"], "choice_id": 1},
            content_type="application/json",
        )

        self.assertEqual(got.status_code, 200)
        body = got.json()
        self.assertIsNotNone(body["question"], "살아 있는 자리가 남았는데 끝났다")

        # 1 번을 건너뛰었으므로 2 번 자리가 나와야 한다.
        self.assertEqual(
            body["question"]["answered"],
            2,
            "건너뛴 만큼 진행이 안 올랐다 - 다음 요청이 같은 자리를 또 낸다",
        )
        self.assertEqual(body["question"]["total"], total, "판 크기가 도중에 바뀌었다")
        self.assertEqual(
            int(self._targets(body["token"])[body["question"]["answered"]][1]),
            survivor,
            "건너뛴 뒤 낸 문제가 살아 있는 그 항목이 아니다",
        )

    def test_the_count_never_passes_the_total(self):
        """끝까지 풀어도 answered 가 total 을 넘지 않는다.

        넘으면 화면 진행 막대가 100% 를 지나 칸 밖으로 자란다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

        body = self.client.post(START_URL).json()
        total = body["question"]["total"]
        token = body["token"]

        seen = [body["question"]["answered"]]
        for _ in range(total + 2):
            got = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": 1},
                content_type="application/json",
            ).json()
            if got["question"] is None:
                break
            seen.append(got["question"]["answered"])
            token = got["token"]

        for value in seen:
            self.assertLess(value, total, f"answered({value}) 가 total({total}) 이상")
        self.assertEqual(seen, sorted(seen), "진행이 뒤로 갔다")

    def _targets(self, token: str) -> list:
        """이 판이 낼 항목들. (종류, pk) 목록."""
        state = signing.loads(token, salt=review._SALT, max_age=review.TOKEN_MAX_AGE)
        return state["t"]


class GraduateStreakContractTest(TestCase):
    """졸업 기준을 화면에 내려주는 약속.

    화면은 "한 번 더 맞히면 끝" 을 이 값으로 센다. 숫자를 화면에 박으면
    기준이 바뀐 날 화면만 옛말을 계속한다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("졸업기준")
        self.client.force_login(self.user)

    def test_it_is_a_positive_whole_number(self):
        """정수이고 1 이상이다.

        0 이나 음수가 내려가면 화면이 "연속 0번 맞히면 빠집니다" 처럼
        말이 안 되는 문구를 그린다. bool 은 파이썬에서 int 라 따로 막는다.
        """
        value = self.client.get(START_URL).json()["graduate_streak"]

        self.assertIsInstance(value, int)
        self.assertNotIsInstance(value, bool)
        self.assertGreaterEqual(value, 1)

    def test_it_matches_the_streak_that_actually_graduates(self):
        """내려준 값만큼 맞히면 실제로 목록에서 빠진다.

        상수만 복사해 내려주고 실제 졸업은 다른 수를 쓰면, 화면이 센
        "한 번 더" 뒤에도 항목이 그대로 남는다. 이 값이 진짜인지 본다.
        """
        word = Word.objects.first()
        a_round(self.user, [(word.pk, False)])

        need = self.client.get(START_URL).json()["graduate_streak"]

        for i in range(need - 1):
            _streak, graduated = review._record(
                self.user, "word", word.pk, correct=True
            )
            self.assertFalse(graduated, f"{i + 1}번 만에 졸업했다")

        _streak, graduated = review._record(self.user, "word", word.pk, correct=True)

        self.assertTrue(graduated, f"{need}번 맞혔는데 졸업이 안 됐다")
        self.assertEqual(review.count_due(self.user), 0)

    def test_it_is_told_to_everyone_including_the_empty_list(self):
        """복습할 것이 없어도 기준은 내려준다.

        화면이 빈 상태에서도 "연속 N번" 을 그린다. due 가 0 일 때만
        빼면 그 화면에서 숫자가 사라진다.
        """
        body = self.client.get(START_URL).json()

        self.assertEqual(body["due"], 0)
        self.assertIn("graduate_streak", body)


@contextmanager
def before_review_write(action):
    """복습 표를 고치는 첫 UPDATE 가 DB 에 닿기 바로 앞에 action 을 한 번 끼운다.

    _record 가 파이썬에서 어디서 읽든, 읽은 뒤 쓰기 전까지가 창이다. SQL
    단에서 걸어 두면 _record 가 save 로 쓰든 update 로 쓰든 같은 자리에
    끼운다. action 안의 UPDATE 는 그대로 통과한다.
    """
    fired = []

    def wrapper(execute, sql, params, many, context):
        if (
            not fired
            and sql.lstrip().upper().startswith("UPDATE")
            and "learning_reviewstate" in sql
        ):
            fired.append(True)
            action()
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield fired


class RecordRaceTest(TestCase):
    """복습 답을 쓰기 직전에 같은 단어의 다른 답이 끼어들면.

    일일공부·자유 문제풀이는 bump_review_states 로 같은 줄을 고친다. 복습
    답이 줄을 읽어 두고 파이썬에서 계산해 쓰면, 그 사이 들어온 답을 옛
    값으로 덮어쓴다. 스레드 경합에 기대면 가끔만 실패하므로 쓰기 직전에
    끼워 순서를 고정한다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습경합")
        self.word = Word.objects.first()
        self.key = ("word", self.word.pk)

    def _row(self) -> ReviewState:
        return ReviewState.objects.get(
            user=self.user, target_type="word", target_id=self.word.pk
        )

    def test_a_miss_just_before_the_second_correct_does_not_graduate(self):
        """복습 1회 정답 뒤, 두 번째 정답을 쓰기 직전에 일일공부 오답이 끼면.

        오답이 먼저 들어간 것이므로 연속은 0 에서 다시 센다 - 이번 정답이
        첫 번째다. 옛 코드는 읽어 둔 1 에 +1 해 2 로 덮어써 졸업시켰다.
        """
        a_round(self.user, [(self.word.pk, False)])
        review._record(self.user, "word", self.word.pk, correct=True)

        miss = partial(record.bump_review_states, self.user, {self.key: False})
        with before_review_write(miss) as fired:
            streak, graduated = review._record(
                self.user, "word", self.word.pk, correct=True
            )

        self.assertTrue(fired, "끼어들기가 안 일어났다")
        self.assertFalse(graduated, "방금 틀린 단어가 졸업했다")
        self.assertEqual(streak, 1)
        self.assertEqual(self._row().streak, 1, "화면에 준 값과 DB 가 다르다")
        self.assertEqual(review.count_due(self.user), 1, "틀린 단어가 목록에서 빠졌다")

    def test_a_review_miss_keeps_a_correct_time_written_just_before(self):
        """복습 오답을 쓰기 직전에 다른 곳의 정답이 끼면, 그 정답 시각은 남는다.

        옛 코드는 오답이어도 last_correct_at 을 읽어 둔 값으로 되썼다.
        """
        long_ago = timezone.now() - timedelta(days=30)
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            last_correct_at=long_ago,
        )

        hit = partial(record.bump_review_states, self.user, {self.key: True})
        with before_review_write(hit) as fired:
            streak, graduated = review._record(
                self.user, "word", self.word.pk, correct=False
            )

        row = self._row()
        self.assertTrue(fired, "끼어들기가 안 일어났다")
        self.assertEqual((streak, graduated), (0, False))
        self.assertTrue(row.is_wrong, "마지막 답(복습 오답)이 안 남았다")
        self.assertGreater(
            row.last_correct_at, long_ago, "방금 맞힌 시각을 옛 값으로 되돌렸다"
        )

    def test_a_free_miss_keeps_a_review_correct_time_written_just_before(self):
        """반대 방향: 자유·일일공부 오답을 쓰기 직전에 복습 정답이 끼면.

        오답이 나중이니 연속은 0 이고 틀린 것으로 남는다. 다만 복습에서
        맞힌 시각은 지우지 않는다 - 옛 코드는 오답 줄에도 last_correct_at
        을 읽어 둔 값으로 되썼다.
        """
        long_ago = timezone.now() - timedelta(days=30)
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            is_wrong=True,
            last_correct_at=long_ago,
        )

        hit = partial(review._record, self.user, "word", self.word.pk, correct=True)
        with before_review_write(hit) as fired:
            record.bump_review_states(self.user, {self.key: False})

        row = self._row()
        self.assertTrue(fired, "끼어들기가 안 일어났다")
        self.assertEqual(row.streak, 0, "나중에 온 오답이 연속을 안 끊었다")
        self.assertTrue(row.is_wrong)
        self.assertGreater(
            row.last_correct_at, long_ago, "방금 맞힌 시각을 옛 값으로 되돌렸다"
        )

    def test_another_review_answer_just_before_the_write_is_not_lost(self):
        """두 탭이 같은 항목을 맞혔는데 한쪽이 다른 쪽 쓰기 직전에 끼면.

        두 번 맞혔으니 연속은 2 이고, 나중 쪽이 졸업을 알린다. 읽어 둔 0 에
        +1 해 쓰면 끼어든 정답이 사라져 1 에 머문다.
        """
        a_round(self.user, [(self.word.pk, False)])

        other_tab = partial(
            review._record, self.user, "word", self.word.pk, correct=True
        )
        with before_review_write(other_tab) as fired:
            streak, graduated = review._record(
                self.user, "word", self.word.pk, correct=True
            )

        self.assertTrue(fired, "끼어들기가 안 일어났다")
        self.assertEqual((streak, graduated), (2, True), "끼어든 정답이 사라졌다")
        self.assertEqual(self._row().streak, 2)

    def test_start_keeps_a_streak_rebuilt_just_before_its_reset(self):
        """판을 열며 연속을 0 으로 되돌리기 직전에 새 사이클 정답이 쌓이면 남긴다.

        start 는 7일 지나 돌아온 졸업 항목(연속 2)의 연속을 지운다. 목록을
        읽은 뒤 그 사이 오답(0)과 복습 정답(1)이 들어왔으면 그 1 은 새
        사이클의 정답이라 지우면 안 된다.
        """
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            streak=review.GRADUATE_STREAK,
            last_correct_at=timezone.now() - timedelta(days=review.STALE_DAYS + 1),
        )

        def miss_then_hit():
            record.bump_review_states(self.user, {self.key: False})
            review._record(self.user, "word", self.word.pk, correct=True)

        with before_review_write(miss_then_hit) as fired:
            review.start(self.user)

        self.assertTrue(fired, "끼어들기가 안 일어났다")
        self.assertEqual(self._row().streak, 1, "새 사이클의 정답을 지웠다")


class RecordReturnContractTest(TestCase):
    """_record 가 돌려준 (연속, 졸업) 이 DB 에 남은 값과 같은가."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("반환계약")
        self.word = Word.objects.first()

    def _row(self) -> ReviewState:
        return ReviewState.objects.get(
            user=self.user, target_type="word", target_id=self.word.pk
        )

    def test_three_correct_answers_stay_at_the_cap(self):
        """세 번 맞혀도 연속은 2 에서 멈춘다. 돌려준 값과 DB 가 매번 같다.

        상한이 없으면 첫 사이클에서 3 이 되고, 7일 뒤 돌아와 한 번만 맞혀도
        재졸업한다.
        """
        a_round(self.user, [(self.word.pk, False)])

        for expected in (1, 2, 2):
            streak, graduated = review._record(
                self.user, "word", self.word.pk, correct=True
            )
            self.assertEqual(streak, expected)
            self.assertEqual(graduated, expected >= review.GRADUATE_STREAK)
            self.assertEqual(self._row().streak, streak, "화면에 준 값과 DB 가 다르다")

    def test_an_over_cap_legacy_row_is_pulled_back_to_the_cap(self):
        """상한 전에 쌓인 큰 값(예: 5)도 다음 정답에서 2 로 내려온다."""
        ReviewState.objects.create(
            user=self.user, target_type="word", target_id=self.word.pk, streak=5
        )

        streak, _graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        self.assertEqual(streak, review.GRADUATE_STREAK)
        self.assertEqual(self._row().streak, review.GRADUATE_STREAK)

    def test_a_correct_answer_on_a_missing_row_creates_it(self):
        """줄이 없던 항목을 맞히면 연속 1 로 새로 생긴다."""
        streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=True
        )

        row = self._row()
        self.assertEqual((streak, graduated), (1, False))
        self.assertEqual((row.streak, row.is_wrong), (1, False))
        self.assertIsNotNone(row.last_correct_at)

    def test_a_wrong_answer_on_a_missing_row_creates_it_as_wrong(self):
        """줄이 없던 항목을 틀리면 틀린 것으로 생기고, 맞힌 시각은 비어 있다."""
        streak, graduated = review._record(
            self.user, "word", self.word.pk, correct=False
        )

        row = self._row()
        self.assertEqual((streak, graduated), (0, False))
        self.assertEqual((row.streak, row.is_wrong), (0, True))
        self.assertIsNone(row.last_correct_at)

    def test_a_review_miss_leaves_the_last_correct_time_alone(self):
        """복습 오답은 마지막 정답 시각을 안 바꾼다."""
        at = timezone.now() - timedelta(days=3)
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            streak=1,
            last_correct_at=at,
        )

        review._record(self.user, "word", self.word.pk, correct=False)

        row = self._row()
        self.assertEqual((row.streak, row.is_wrong), (0, True))
        self.assertEqual(row.last_correct_at, at)


def _pick_from_review_token(token: str, correct: bool) -> int:
    """복습 토큰을 풀어 정답(또는 오답) 보기 id 를 고른다.

    공격자 시점을 재현하는 도구다. 첫 답의 응답이 정답을 알려주므로 이만큼의
    정보는 누구나 얻는다.
    """
    state = signing.loads(token, salt=review._SALT, max_age=review.TOKEN_MAX_AGE)
    payload = state["q"]
    _, answer_id = quiz.resolve_answer(payload, -1)
    if correct:
        return answer_id
    return next(cid for cid in payload["c"] if cid != answer_id)


class ReviewApiFlowTest(TestCase):
    """HTTP 끝단으로 판을 돌린다: 시작 -> 답 -> 졸업 -> 7일 뒤 돌아와 다시 두 번."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("끝단흐름")
        self.client.force_login(self.user)
        self.word = Word.objects.first()

    def _start(self) -> str:
        got = self.client.post(START_URL)
        self.assertEqual(got.status_code, 201, got.content)
        return got.json()["token"]

    def _answer(self, token: str, correct: bool) -> dict:
        got = self.client.post(
            ANSWER_URL,
            {"token": token, "choice_id": _pick_from_review_token(token, correct)},
            content_type="application/json",
        )
        self.assertEqual(got.status_code, 200, got.content)
        return got.json()["result"]

    def _row(self) -> ReviewState:
        return ReviewState.objects.get(
            user=self.user, target_type="word", target_id=self.word.pk
        )

    def _due(self) -> int:
        return self.client.get(START_URL).json()["due"]

    def test_two_rounds_graduate_then_a_stale_return_needs_two_again(self):
        """틀린 단어는 연속 두 번 맞혀야 빠지고, 7일 뒤 돌아오면 다시 두 번이다."""
        a_round(self.user, [(self.word.pk, False)])

        first = self._answer(self._start(), correct=True)
        self.assertEqual((first["streak"], first["graduated"]), (1, False))
        second = self._answer(self._start(), correct=True)
        self.assertEqual((second["streak"], second["graduated"]), (2, True))
        self.assertEqual(self._due(), 0)

        ReviewState.objects.filter(pk=self._row().pk).update(
            last_correct_at=timezone.now() - timedelta(days=review.STALE_DAYS + 1)
        )
        self.assertEqual(self._due(), 1)

        token = self._start()
        self.assertEqual(self._row().streak, 0, "돌아온 항목의 연속을 안 지웠다")
        again = self._answer(token, correct=True)
        self.assertEqual((again["streak"], again["graduated"]), (1, False))
        self.assertEqual(self._due(), 1, "두 번째 사이클에서 한 번에 빠졌다")

    def test_a_wrong_answer_resets_and_keeps_the_correct_time(self):
        """API 로 틀리면 연속 0, 틀린 것으로 남고, 마지막 정답 시각은 그대로다."""
        a_round(self.user, [(self.word.pk, False)])
        self._answer(self._start(), correct=True)
        at = self._row().last_correct_at

        result = self._answer(self._start(), correct=False)

        row = self._row()
        self.assertEqual((result["streak"], result["graduated"]), (0, False))
        self.assertEqual((row.streak, row.is_wrong), (0, True))
        self.assertEqual(row.last_correct_at, at)


class StepSweepClockTest(TestCase):
    """판 청소와 복습 토큰 수명이 시계 위에서 맞물리는가.

    RoundStep 은 자유 문제풀이(토큰 10분)와 복습(토큰 6시간)이 같이 쓴다.
    청소가 짧은 쪽에 맞추면 그 사이만큼 복습 되돌리기가 열린다. 행 나이만
    바꾸는 것으로는 "토큰은 아직 살아 있다" 를 못 보이므로, 서명 시계와
    청소 시계를 같이 앞으로 돌려 실제로 그 시각에 다시 보낸 것처럼 한다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("청소시계")
        self.client.force_login(self.user)
        a_round(self.user, [(Word.objects.first().pk, False)])

    def _answer_once(self) -> tuple[str, int]:
        """복습을 열고 첫 문제에 답한다. (그 토큰, 고른 보기)"""
        body = self.client.post(START_URL).json()
        choice = body["question"]["choices"][0]["id"]
        got = self.client.post(
            ANSWER_URL, {"token": body["token"], "choice_id": choice},
            content_type="application/json",
        )
        self.assertEqual(got.status_code, 200)
        return body["token"], choice

    @contextmanager
    def _later(self, seconds: float):
        """서명 검사와 청소가 보는 시각을 seconds 만큼 뒤로 민다."""
        real_time = signing.time.time
        real_now = timezone.now
        wall = real_time() + seconds
        moment = real_now() + timedelta(seconds=seconds)
        with mock.patch.object(signing.time, "time", return_value=wall), \
                mock.patch.object(session.timezone, "now", return_value=moment):
            yield

    def _sweep(self):
        with mock.patch.object(session.random, "random", return_value=0.0):
            session._sweep_old_steps()

    def test_replay_is_refused_at_every_age_the_review_token_still_accepts(self):
        """토큰이 받아지는 동안 어느 시각에 청소가 돌아도 되돌리기는 400 이다.

        11분(옛 청소 기준 바로 뒤), 1시간, 5시간 59분을 차례로 본다. 표시가
        남아 있어야 하고, 되돌린 토큰은 거절돼야 한다.
        """
        token, choice = self._answer_once()
        for seconds in (session.TOKEN_MAX_AGE + 60, 60 * 60, review.TOKEN_MAX_AGE - 60):
            with self.subTest(seconds=seconds), self._later(seconds):
                self._sweep()
                self.assertEqual(
                    RoundStep.objects.count(), 1, f"{seconds}초 뒤 청소가 살아 있는 표시를 지웠다"
                )
                again = self.client.post(
                    ANSWER_URL, {"token": token, "choice_id": choice},
                    content_type="application/json",
                )
                self.assertEqual(again.status_code, 400)
                self.assertIn("이미 처리한 답", again.json()["detail"])

    def test_after_the_token_dies_the_row_goes_and_replay_is_still_refused(self):
        """6시간이 넘으면 표시는 지워지고, 그때 다시 보내도 토큰 만료로 막힌다.

        표시가 먼저 사라지고 토큰이 나중에 죽는 틈이 없어야 한다.
        """
        token, choice = self._answer_once()
        with self._later(session.LONG_STEP_KEEP_SECONDS + 60):
            self._sweep()
            self.assertEqual(RoundStep.objects.count(), 0, "수명 지난 표시가 남았다")
            again = self.client.post(
                ANSWER_URL, {"token": token, "choice_id": choice},
                content_type="application/json",
            )
        self.assertEqual(again.status_code, 400)
        self.assertIn("만료", again.json()["detail"])

    def test_sweep_boundary_is_strictly_older_than_the_keep_window(self):
        """경계: 창 끝에서 1초 안쪽과 창 끝은 남고, 1초 바깥은 지워진다.

        창은 판마다 다르다. 복습처럼 앞머리가 붙은 판은 LONG_STEP_KEEP_SECONDS,
        나머지(90초 한 판)는 판 토큰 수명이다.
        """
        long = session.LONG_ROUND_PREFIX
        ages = {
            f"{long}inside": session.LONG_STEP_KEEP_SECONDS - 1,
            f"{long}edge": session.LONG_STEP_KEEP_SECONDS,
            f"{long}outside": session.LONG_STEP_KEEP_SECONDS + 1,
            "free-inside": session.TOKEN_MAX_AGE - 1,
            "free-edge": session.TOKEN_MAX_AGE,
            "free-outside": session.TOKEN_MAX_AGE + 1,
        }
        now = timezone.now()
        for round_id, age in ages.items():
            RoundStep.objects.create(round_id=round_id, step=0)
            RoundStep.objects.filter(round_id=round_id).update(
                created_at=now - timedelta(seconds=age)
            )

        with mock.patch.object(session.timezone, "now", return_value=now):
            self._sweep()

        self.assertEqual(
            sorted(RoundStep.objects.values_list("round_id", flat=True)),
            sorted([f"{long}edge", f"{long}inside", "free-edge", "free-inside"]),
        )

    def test_free_round_replay_is_still_refused_after_a_sweep(self):
        """자유 문제풀이 되돌리기 방어는 그대로다 - 청소가 돌아도 토큰이 사는 동안 막힌다."""
        token, question = session.start()
        _, first, _ = session.answer(token, question["choices"][0]["id"])
        with self._later(session.TOKEN_MAX_AGE - 5):
            self._sweep()
        self.assertEqual(RoundStep.objects.count(), 1)
        # 시계를 돌린 채 답하면 90초 마감에 먼저 걸려 무엇이 막았는지 모른다.
        with self.assertRaisesMessage(SessionError, "이미"):
            session.answer(token, first.answer_id)

    def test_sweep_does_not_run_on_most_calls(self):
        """확률 문을 지나지 못하면 아무것도 안 지운다(오래된 행도)."""
        RoundStep.objects.create(round_id="old", step=0)
        RoundStep.objects.update(
            created_at=timezone.now() - timedelta(seconds=session.LONG_STEP_KEEP_SECONDS * 2)
        )
        with mock.patch.object(session.random, "random", return_value=0.99):
            session._sweep_old_steps()
        self.assertEqual(RoundStep.objects.count(), 1)

    # ---- 90초 한 판과 복습이 섞여 있을 때 ----
    # 위 경계 테스트는 식별자를 손으로 만든다. 아래는 실제로 판을 열고 답해서
    # 생긴 행으로 보고, 청소도 운영에서 도는 유일한 자리(session.start)로 돌린다.

    def _open_free_and_answer(self) -> tuple[str, int]:
        """90초 한 판을 열고 첫 문제에 답한다. (그 토큰, 고른 보기)"""
        token, question = session.start()
        choice = question["choices"][0]["id"]
        session.answer(token, choice)
        return token, choice

    def test_after_ten_minutes_free_rows_go_and_review_rows_stay(self):
        """11분 뒤 누가 한 판을 열면 한 판 표시만 지워지고 복습 표시는 남는다.

        복습 쪽은 그 시각에 옛 토큰을 다시 보내도 "이미 처리한 답" 으로 막힌다.
        """
        review_token, review_choice = self._answer_once()
        self._open_free_and_answer()
        self.assertEqual(RoundStep.objects.count(), 2)

        with self._later(session.TOKEN_MAX_AGE + 60):
            with mock.patch.object(session.random, "random", return_value=0.0):
                session.start()  # 청소가 이 안에서 돈다
            left = list(RoundStep.objects.values_list("round_id", flat=True))
            again = self.client.post(
                ANSWER_URL, {"token": review_token, "choice_id": review_choice},
                content_type="application/json",
            )

        self.assertEqual(len(left), 1, f"남은 표시: {left}")
        self.assertTrue(left[0].startswith(session.LONG_ROUND_PREFIX))
        self.assertEqual(again.status_code, 400)
        self.assertIn("이미 처리한 답", again.json()["detail"])

    def test_free_round_ids_do_not_carry_the_long_prefix(self):
        """90초 한 판의 식별자에는 앞머리가 없다 - 있으면 6시간씩 쌓인다."""
        self._open_free_and_answer()
        self.assertFalse(
            RoundStep.objects.get().round_id.startswith(session.LONG_ROUND_PREFIX)
        )

    def test_free_round_replay_after_its_row_is_gone_is_refused_as_expired(self):
        """한 판 표시가 지워진 뒤에 옛 한 판 토큰을 보내면 만료로 막힌다.

        표시가 먼저 사라지고 토큰이 나중에 죽는 틈이 한 판 쪽에도 없어야 한다.
        """
        token, choice = self._open_free_and_answer()
        with self._later(session.TOKEN_MAX_AGE + 1):
            self._sweep()
            self.assertEqual(RoundStep.objects.count(), 0)
            with self.assertRaises(SessionError) as caught:
                session.answer(token, choice)
        self.assertNotIn("이미", str(caught.exception))
