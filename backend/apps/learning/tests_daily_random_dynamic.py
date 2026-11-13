"""일일공부를 무작위 고르기(pick_random)와 자른 개수 세기로 바꾼 뒤를 깨뜨려 본다.

  - 새 단어 고르기는 이 사람이 복습 상태를 가진 단어를 다시 고르지 않는다.
    EXISTS 로 빼므로, 다른 사람의 상태나 문장 쪽 상태가 섞여 들면 안 된다.
  - 검수 안 된 단어는 학습 목록에 들어가지 않는다.
  - 개수를 plan.total 까지만 세도 계획(문제 수·묶음)이 다 셀 때와 같다.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import daily_study
from .models import STUDY_PLANS, ReviewState, StudyLength
from .tests_daily_study import make_user


def _words(n: int, *, reviewed: bool = True, tag: str = "w") -> list[Word]:
    return Word.objects.bulk_create(
        Word(term=f"{tag} {i}", meaning="뜻", description="설명", is_reviewed=reviewed)
        for i in range(n)
    )


def _sentences(n: int, *, reviewed: bool = True) -> None:
    Sentence.objects.bulk_create(
        Sentence(text=f"sentence {i}", translation="번역", is_reviewed=reviewed) for i in range(n)
    )


def _states(user, words, **fields) -> None:
    ReviewState.objects.bulk_create(
        ReviewState(user=user, target_type=quiz.TARGET_WORD, target_id=w.pk, **fields)
        for w in words
    )


class PickWordsTest(TestCase):
    """_pick_words 의 안 본 것 고르기."""

    def setUp(self):
        cache.clear()
        self.user = make_user("고르기")
        self.other = make_user("남")

    def test_words_with_a_state_are_never_picked_as_unseen(self):
        """상태가 있는(틀리지도, 맞힌 적도 없는) 단어는 안 본 것에 안 든다.

        그런 단어는 틀린 것·오래된 것 갈래에도 안 들어가므로, 고른 것은 정확히
        상태 없는 다섯이어야 한다. EXISTS 조건이 빠지면 상태 있는 30개가 섞인다.
        """
        stated = _words(30, tag="stated")
        fresh = _words(5, tag="fresh")
        _states(self.user, stated, is_wrong=False)

        for _ in range(30):
            picked = daily_study._pick_words(self.user.pk, 10, set())
            self.assertCountEqual([w.pk for w in picked], [w.pk for w in fresh])

    def test_other_users_and_sentence_states_do_not_hide_words(self):
        """남의 복습 상태, 같은 id 의 문장 상태는 이 사람의 안 본 단어를 가리지 않는다."""
        fresh = _words(6, tag="fresh")
        _states(self.other, fresh, is_wrong=False)
        ReviewState.objects.bulk_create(
            ReviewState(user=self.user, target_type=quiz.TARGET_SENTENCE, target_id=w.pk)
            for w in fresh
        )
        picked = daily_study._pick_words(self.user.pk, 6, set())
        self.assertCountEqual([w.pk for w in picked], [w.pk for w in fresh])

    def test_unreviewed_and_seen_are_never_picked(self):
        visible = _words(8, tag="visible")
        _words(200, reviewed=False, tag="hidden")
        seen = {visible[0].pk, visible[1].pk}
        for _ in range(30):
            picked = daily_study._pick_words(self.user.pk, 20, seen)
            ids = {w.pk for w in picked}
            self.assertEqual(ids, {w.pk for w in visible[2:]})
            self.assertTrue(all(w.is_reviewed for w in picked))

    def test_wrong_first_then_unseen_without_duplicates(self):
        """틀린 것을 먼저 넣고, 안 본 것에서 그 단어를 다시 고르지 않는다."""
        wrong = _words(3, tag="wrong")
        fresh = _words(40, tag="fresh")
        _states(self.user, wrong, is_wrong=True)
        for _ in range(30):
            picked = daily_study._pick_words(self.user.pk, 5, set())
            ids = [w.pk for w in picked]
            self.assertEqual(len(ids), 5)
            self.assertEqual(len(set(ids)), 5, "같은 단어를 두 번 골랐다")
            self.assertEqual(set(ids[:3]), {w.pk for w in wrong})
            self.assertLessEqual(set(ids[3:]), {w.pk for w in fresh})

    def test_start_never_learns_unreviewed(self):
        """판을 열어도 학습 목록은 검수된 것만."""
        _words(60, tag="visible")
        hidden = {w.pk for w in _words(200, reviewed=False, tag="hidden")}
        study, _token, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()
        self.assertTrue(study.learned_ids)
        self.assertFalse(set(study.learned_ids) & hidden)


class CountUpToTest(TestCase):
    """_count_up_to 와 그것을 쓰는 계획 계산."""

    def test_counts_reviewed_only_and_stops_at_limit(self):
        _words(3)
        _words(20, reviewed=False, tag="hidden")
        visible = Word.objects.visible()
        self.assertEqual(daily_study._count_up_to(visible, 5), 3)
        self.assertEqual(daily_study._count_up_to(visible, 3), 3)
        self.assertEqual(daily_study._count_up_to(visible, 2), 2)
        _words(10, tag="more")
        self.assertEqual(daily_study._count_up_to(Word.objects.visible(), 5), 5)

    def test_capped_counts_give_the_same_plan_as_full_counts(self):
        """단어·문장 수 격자 전체에서, 자른 셈과 다 센 셈의 계획이 같다.

        _count_up_to 를 "다 센다" 로 바꿔 끼운 값과 비교한다. 콘텐츠가 plan.total
        보다 적을 때·많을 때·경계일 때를 모두 지난다.
        """
        grid = sorted({*range(0, 50), 55, 60, 80, 100, 1000})
        for length, plan in STUDY_PLANS.items():
            for words in grid:
                for sentences in (0, 1, 2, 5, 9, 10, 11, 24, 25, 26, 39, 40, 41, 100):
                    real = {Word: words, Sentence: sentences}

                    def capped(qs, limit):
                        return min(real[qs.model], limit)

                    def full(qs, limit):
                        return real[qs.model]

                    with mock.patch.object(daily_study, "_count_up_to", side_effect=capped):
                        got = daily_study._fit_plan(plan), daily_study._answerable(plan)
                    with mock.patch.object(daily_study, "_count_up_to", side_effect=full):
                        want = daily_study._fit_plan(plan), daily_study._answerable(plan)
                    if got != want:
                        self.fail(f"{length} 단어 {words} 문장 {sentences}: {got} != {want}")

    def test_plan_on_real_rows(self):
        """실제 행으로 세어도 적을 때는 줄고, 넉넉할 때는 계획 그대로다."""
        plan = STUDY_PLANS[StudyLength.MEDIUM]
        _words(6)
        _words(100, reviewed=False, tag="hidden")
        total, size, count = daily_study._fit_plan(plan)
        self.assertEqual(total, 6)
        self.assertEqual((size, count), (5, 1))

        _words(200, tag="more")
        _sentences(200)
        total, size, count = daily_study._fit_plan(plan)
        self.assertEqual((total, size, count), (plan.total, plan.chunk_size, plan.chunk_count))
