"""복습.

**점수가 없는 판이다.** 정답을 이미 본 문제가 나오므로 점수를 주면 아는
것만 골라 푸는 길이 열린다. 그래서 순위표에 안 들어간다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.vocab.models import Sentence, Word

from . import record, review
from .models import DailyScore, QuizAnswer, QuizSession, ReviewState
from .session import SessionError

PASSWORD = secrets.token_urlsafe(16)

START_URL = "/api/learning/review/"
ANSWER_URL = "/api/learning/review/answer/"


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def seed_words(count: int = 40) -> None:
    Word.objects.bulk_create(
        Word(
            term=f"word{i}",
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
