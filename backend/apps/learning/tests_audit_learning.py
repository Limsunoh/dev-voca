"""11-24 점검에서 고친 학습 규칙. 몫·상한처럼 개수를 따지는 것은
tests_audit_learning_dynamic.py 가 크기별로 본다.

- 복습 목록이 검수 취소·삭제된 대상을 거른다(review.visible_targets)
- 일일공부에서 지금 묶음의 카드 단어는 맞혀도 오답에서 빼지 않는다(keep_wrong). 학습
  차례가 끝난 뒤 전체에서 나온 문제는 평소대로 뺀다
- 한 판을 도중에 그만둬도 틀린 것은 오답 노트에 남는다(record.note_round_miss)
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import LoginToken
from apps.vocab import quiz
from apps.vocab.models import Word

from . import daily_study, record, review
from .models import ReviewState, StudyLength
from .tests_abuse import answer_id_of as round_answer_id
from .tests_daily_learning import answer_id_of as daily_answer_id
from .tests_daily_study import make_user, seed_words
from .tests_daily_study_edge import answer_wrong

START_URL = "/api/learning/rounds/"
ANSWER_URL = "/api/learning/rounds/answer/"


def _wrong(user, word_ids) -> None:
    ReviewState.objects.bulk_create(
        ReviewState(user=user, target_type=quiz.TARGET_WORD, target_id=pk, is_wrong=True)
        for pk in word_ids
    )


def _row(user, word_id) -> ReviewState | None:
    return ReviewState.objects.filter(
        user=user, target_type=quiz.TARGET_WORD, target_id=word_id
    ).first()


class ReviewSkipsHiddenTargetsTest(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습거름")
        self.words = list(Word.objects.order_by("pk").values_list("pk", flat=True)[:25])
        _wrong(self.user, self.words)

    def test_hidden_rows_in_front_do_not_block_the_rest(self):
        """앞 20줄이 검수에서 내려가도 뒤의 5개로 판이 열린다."""
        Word.objects.filter(pk__in=self.words[:20]).update(is_reviewed=False)

        self.assertEqual(review.count_due(self.user), 5)
        _token, question, total = review.start(self.user)
        self.assertEqual(total, 5)
        self.assertIsNotNone(question)

    def test_deleted_target_is_not_counted(self):
        Word.objects.filter(pk=self.words[0]).delete()
        self.assertEqual(review.count_due(self.user), 24)
        self.assertNotIn(
            self.words[0], [row.target_id for row in review.due_of(self.user)]
        )

    def test_count_matches_what_the_mistake_note_shows(self):
        Word.objects.filter(pk__in=self.words[:3]).update(is_reviewed=False)
        listed = ReviewState.objects.filter(user=self.user, is_wrong=True).filter(
            review.visible_targets()
        )
        self.assertEqual(review.count_due(self.user), listed.count())


class DailyStudyKeepsWrongTest(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("카드직후")

    def _answer_until(self, target_pk: int, *, correct: bool) -> None:
        """target 이 나올 때까지 맞히며 가다가, target 에서 correct 대로 답한다."""
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        while question is not None:
            right = daily_answer_id(token)
            if right == target_pk:
                if correct:
                    daily_study.answer(self.user, token, right)
                else:
                    answer_wrong(self.user, token, question)
                return
            _result, token, question, _s = daily_study.answer(self.user, token, right)
        self.fail("틀린 단어가 일일공부 문제로 안 나왔다")

    def test_correct_answer_right_after_the_card_keeps_it_wrong(self):
        target = Word.objects.visible().first()
        _wrong(self.user, [target.pk])

        self._answer_until(target.pk, correct=True)

        row = _row(self.user, target.pk)
        self.assertTrue(row.is_wrong, "카드로 본 직후의 정답이 오답을 풀었다")
        self.assertIsNone(row.last_correct_at)
        self.assertEqual(review.count_due(self.user), 1)

    def test_new_word_answered_right_is_still_recorded(self):
        """틀린 적 없는 단어는 전처럼 맞힌 시각이 남는다(오래된 것 고르기에 쓴다)."""
        _study, token, _question = daily_study.start(self.user, StudyLength.SHORT)
        right = daily_answer_id(token)
        daily_study.answer(self.user, token, right)

        row = _row(self.user, right)
        self.assertFalse(row.is_wrong)
        self.assertIsNotNone(row.last_correct_at)

    def test_wrong_answer_still_marks_it_wrong(self):
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        right = daily_answer_id(token)
        answer_wrong(self.user, token, question)
        self.assertTrue(_row(self.user, right).is_wrong)

    def test_review_still_clears_it(self):
        """오답에서 빼는 일은 복습이 맡는다. 연속 두 번이면 빠진다."""
        target = Word.objects.visible().first()
        _wrong(self.user, [target.pk])
        self._answer_until(target.pk, correct=True)

        for _ in range(review.GRADUATE_STREAK):
            token, question, _total = review.start(self.user)
            state = review._load(token)
            right = next(
                c["id"] for c in question["choices"]
                if quiz.resolve_answer(state["q"], c["id"])[0]
            )
            review.answer(self.user, token, right)

        self.assertFalse(_row(self.user, target.pk).is_wrong)


class RoundQuitKeepsWrongTest(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("그만두기")
        self.auth = {"HTTP_AUTHORIZATION": f"Token {LoginToken.objects.create(user=self.user).key}"}

    def _start(self, **auth):
        response = self.client.post(START_URL, {}, content_type="application/json", **auth)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def _answer(self, token: str, body: dict, **auth):
        return self.client.post(
            ANSWER_URL, {"token": token, **body}, content_type="application/json", **auth
        )

    def _wrong_choice(self, opened) -> tuple[int, int]:
        token = opened["token"]
        right = round_answer_id(token)
        picked = next(c["id"] for c in opened["question"]["choices"] if c["id"] != right)
        return right, picked

    def test_wrong_answer_is_kept_without_finishing(self):
        opened = self._start(**self.auth)
        right, picked = self._wrong_choice(opened)

        response = self._answer(opened["token"], {"choice_id": picked}, **self.auth)
        self.assertEqual(response.status_code, 200)

        row = ReviewState.objects.get(user=self.user, target_id=right)
        self.assertTrue(row.is_wrong)
        self.assertEqual(row.target_type, response.json()["result"]["answer_type"])

    def test_correct_answer_waits_for_finish(self):
        opened = self._start(**self.auth)
        right = round_answer_id(opened["token"])
        self._answer(opened["token"], {"choice_id": right}, **self.auth)
        self.assertFalse(ReviewState.objects.filter(user=self.user).exists())

    def test_skip_is_not_counted_as_wrong(self):
        opened = self._start(**self.auth)
        self._answer(opened["token"], {"skip": True}, **self.auth)
        self.assertFalse(ReviewState.objects.filter(user=self.user).exists())

    def test_failed_miss_write_does_not_break_the_round(self):
        """오답 기록이 실패해도 답은 200 이다. 끝내기가 같은 답을 다시 반영한다."""
        opened = self._start(**self.auth)
        _right, picked = self._wrong_choice(opened)
        with mock.patch.object(record, "bump_review_states", side_effect=RuntimeError("db")):
            response = self._answer(opened["token"], {"choice_id": picked}, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReviewState.objects.filter(user=self.user).exists())

    def test_guest_leaves_nothing(self):
        opened = self._start()
        _right, picked = self._wrong_choice(opened)
        self._answer(opened["token"], {"choice_id": picked})
        self.assertFalse(ReviewState.objects.exists())


class DailyStudyOutsideTheCardTest(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("학습뒤")

    def test_word_seen_on_a_card_earlier_is_cleared_after_the_study_part(self):
        """학습 차례가 끝난 뒤 전체에서 나온 문제는 카드 직후가 아니라 평소대로 뺀다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        while question is not None and daily_study._study_scope(study) is not None:
            right = daily_answer_id(token)
            _result, token, question, study = daily_study.answer(self.user, token, right)
        self.assertIsNotNone(question, "학습 차례 뒤 문제가 없다")

        right = daily_answer_id(token)
        _wrong(self.user, [right])
        daily_study.answer(self.user, token, right)
        self.assertFalse(_row(self.user, right).is_wrong)
