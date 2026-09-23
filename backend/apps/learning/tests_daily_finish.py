"""일일공부 닫기(_finish) - 최종 점수가 행의 지금 값으로 계산되는가.

_finish 는 최종 점수(다 풀었으면 score + bonus, 아니면 score)를 닫는
UPDATE 안에서 계산한다. 파이썬에서 읽어 두고 쓰면, 읽은 뒤 UPDATE 전에
커밋된 답을 옛 점수로 덮어쓴다. 여기서 보는 것:

    - 보너스 경계: 마지막 답에서 한 번, 못 끝낸 판은 0, 다시 닫아도 한 번
    - 세 호출자(answer, resume, settle_stale) 모두 판과 그날 줄이 같은 값
    - 정산과 답하기를 여러 순서로 끼워 넣기 (닫는 UPDATE 직전에 고정)
    - Postgres 에서 실제 스레드 경합을 여러 판 반복

모든 판에 걸리는 불변식은 하나다(_assert_settled):

    score == correct + (bonus if answered >= total_questions else 0)
    DailyScore.daily_study_score == score
"""

from __future__ import annotations

import threading
import unittest
from contextlib import contextmanager
from unittest import mock

from django.core.cache import cache
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase

from . import calendar_kst, daily_study
from .models import STUDY_PLANS, DailyScore, DailyStudy, StudyLength
from .session import SessionError
from .tests_daily_study import tomorrow
from .tests_daily_study_edge import (
    _correct_id_of,
    _KeepsCacheTable,
    make_user,
    seed_words,
)

SHORT = StudyLength.SHORT
TOTAL = STUDY_PLANS[SHORT].total
BONUS = STUDY_PLANS[SHORT].bonus


def play(user, count: int):
    """판을 열고 count 문제를 정답으로 푼다. (판, 다음 토큰, 다음 문제).

    정답으로 푸는 이유: 덮어쓰기가 나면 점수가 실제로 달라져야 드러난다.
    """
    study, token, question = daily_study.start(user, SHORT)
    for _ in range(count):
        _r, token, question, _s = daily_study.answer(
            user, token, _correct_id_of(token)
        )
    study.refresh_from_db()
    return study, token, question


def take_step_only(study_pk: int) -> DailyStudy:
    """다른 탭의 답이 채점만 커밋된 상태를 만든다. 닫기·발행은 안 한다.

    answer() 의 트랜잭션이 커밋된 직후, 커밋 뒤의 _finish/_publish 가
    아직 안 돈 순간이다.
    """
    other = DailyStudy.objects.get(pk=study_pk)
    daily_study._take_step(other, other.step, 1, True)
    return other


@contextmanager
def before_close(action):
    """닫는 UPDATE(finished_at 을 쓰는 것) 바로 앞에 action 을 한 번 끼운다.

    refresh_from_db 같은 특정 읽기 자리가 아니라 **쓰기 직전**에 건다.
    읽는 자리가 어디든(호출부의 쿼리셋이든 _finish 안이든) 그 뒤 UPDATE
    전까지가 창이므로, 여기가 가장 늦은 끼어들기다. action 안에서 다시
    닫기가 불려도 두 번째부터는 그대로 통과한다.
    """
    real_update = QuerySet.update
    fired = []

    def update(qs, **kwargs):
        if "finished_at" in kwargs and not fired:
            fired.append(True)
            action()
        return real_update(qs, **kwargs)

    with mock.patch.object(QuerySet, "update", update):
        yield fired


class _FinishBase(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("닫기경계")

    def _assert_settled(self, study_pk: int, *, answered: int, bonus: bool):
        """판이 닫혔고, 점수가 불변식을 지키고, 그날 줄과 같은가."""
        study = DailyStudy.objects.get(pk=study_pk)
        self.assertTrue(study.is_done, "판이 안 닫혔다")
        self.assertEqual(study.answered, answered, "푼 개수가 다르다")
        self.assertEqual(
            study.score,
            study.correct + (study.bonus if bonus else 0),
            "보너스가 틀렸거나 답이 덮어써졌다",
        )
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            study.score,
            "그날 줄과 판의 점수가 갈렸다",
        )
        return study


class BonusBoundaryTest(_FinishBase):
    """보너스는 다 풀었을 때 정확히 한 번."""

    def test_the_last_answer_adds_the_bonus_exactly_once(self):
        """마지막 답에서 붙는다. 그 뒤 다시 닫아도, 정산해도 안 붙는다."""
        study, token, question = play(self.user, TOTAL)
        self.assertIsNone(token)
        self.assertIsNone(question)
        self._assert_settled(study.pk, answered=TOTAL, bonus=True)

        daily_study._finish(study)
        daily_study._finish(DailyStudy.objects.get(pk=study.pk))
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)

        study = self._assert_settled(study.pk, answered=TOTAL, bonus=True)
        self.assertEqual(study.score, TOTAL + BONUS)

    def test_one_short_of_the_end_gets_no_bonus_on_settle(self):
        """한 문제 모자라게 풀고 자정을 넘기면 보너스 없이 닫힌다."""
        study, _t, _q = play(self.user, TOTAL - 1)
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
        study = self._assert_settled(study.pk, answered=TOTAL - 1, bonus=False)
        self.assertEqual(study.score, TOTAL - 1)

    def test_a_study_with_no_answers_settles_to_zero(self):
        """하나도 안 풀고 넘긴 판은 0 으로 닫히고 그날 줄도 0 이다."""
        study, _t, _q = play(self.user, 0)
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
        study = self._assert_settled(study.pk, answered=0, bonus=False)
        self.assertEqual(study.score, 0)

    def test_a_stale_instance_claiming_completion_does_not_earn_the_bonus(self):
        """인메모리 값이 '다 풀었다' 여도 행이 아니면 보너스를 안 준다.

        판정을 인스턴스로 하면 낡은 인스턴스를 든 호출부가 보너스를 산다.
        """
        study, _t, _q = play(self.user, 3)
        study.answered = TOTAL
        study.score = 999
        daily_study._finish(study)

        self.assertEqual(study.score, 3, "인스턴스가 DB 값으로 안 맞춰졌다")
        self._assert_settled(study.pk, answered=3, bonus=False)

    def test_a_stale_instance_behind_the_row_still_gets_the_bonus(self):
        """인스턴스는 뒤처졌어도 행이 다 풀었으면 보너스를 준다."""
        study, _t, _q = play(self.user, TOTAL - 1)
        take_step_only(study.pk)  # 행은 이제 TOTAL 개
        self.assertEqual(study.answered, TOTAL - 1)

        daily_study._finish(study)

        self.assertEqual(study.score, TOTAL + BONUS)
        self._assert_settled(study.pk, answered=TOTAL, bonus=True)

    def test_a_completed_but_open_study_closed_twice_gets_one_bonus(self):
        """다 풀었는데 안 닫힌 판을 두 번 닫아도 보너스는 한 번."""
        study, _t, _q = play(self.user, TOTAL - 1)
        take_step_only(study.pk)

        daily_study._finish(DailyStudy.objects.get(pk=study.pk))
        daily_study._finish(DailyStudy.objects.get(pk=study.pk))

        study = self._assert_settled(study.pk, answered=TOTAL, bonus=True)
        self.assertEqual(study.score, TOTAL + BONUS)


class CallerConsistencyTest(_FinishBase):
    """세 호출자 각각에서 판과 그날 줄이 같다."""

    def test_answer_closing_on_the_last_answer(self):
        study, _t, _q = play(self.user, TOTAL)
        self._assert_settled(study.pk, answered=TOTAL, bonus=True)

    def test_answer_closing_when_questions_run_out(self):
        study, token, _q = play(self.user, 2)
        with mock.patch.object(daily_study, "make_question", return_value=None):
            _r, next_token, _nq, _s = daily_study.answer(
                self.user, token, _correct_id_of(token)
            )
        self.assertIsNone(next_token)
        self._assert_settled(study.pk, answered=3, bonus=False)

    def test_resume_closing_an_unfinished_study(self):
        """resume 이 새 문제를 못 만들어 닫으면 보너스 없이 닫힌다."""
        study, _t, _q = play(self.user, 3)
        DailyStudy.objects.filter(pk=study.pk).update(question=None)
        study.refresh_from_db()

        with mock.patch.object(daily_study, "make_question", return_value=None):
            self.assertIsNone(daily_study.resume(study))

        self._assert_settled(study.pk, answered=3, bonus=False)

    def test_resume_closing_a_completed_but_open_study(self):
        """다 풀고도 안 닫힌 판을 resume 이 닫으면 보너스가 붙는다."""
        study, _t, _q = play(self.user, TOTAL - 1)
        take_step_only(study.pk)
        study.refresh_from_db()

        with mock.patch.object(daily_study, "make_question", return_value=None):
            self.assertIsNone(daily_study.resume(study))

        self._assert_settled(study.pk, answered=TOTAL, bonus=True)

    def test_settle_stale_closing_an_unfinished_study(self):
        study, _t, _q = play(self.user, 4)
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
        self._assert_settled(study.pk, answered=4, bonus=False)


class InterleavingTest(_FinishBase):
    """정산과 답하기를 순서를 고정해 끼워 넣는다.

    끼우는 자리는 닫는 UPDATE 직전(before_close)이다. 파이썬에서 읽은
    값으로 점수를 쓰면 여기서 끼운 답이 사라진다.
    """

    def test_an_answer_committed_right_before_settles_close_is_kept(self):
        """정산이 닫기 직전에 다른 탭의 답(마지막 아님)이 통째로 끝난다."""
        study, token, _q = play(self.user, 3)

        def other_tab():
            daily_study.answer(self.user, token, _correct_id_of(token))

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            with before_close(other_tab) as fired:
                daily_study.settle_stale(self.user)
        self.assertTrue(fired, "끼워 넣기가 안 돌았다")

        study = self._assert_settled(study.pk, answered=4, bonus=False)
        self.assertEqual(study.score, 4, "끼어든 답이 덮어써졌다")

    def test_the_last_step_committed_right_before_settles_close_earns_the_bonus(self):
        """마지막 답의 채점만 커밋된 사이 정산이 닫는다. 보너스는 정산이 준다.

        그 뒤 답 쪽의 _finish 는 진다(0 행). 보너스는 한 번이다.
        """
        study, _token, _q = play(self.user, TOTAL - 1)
        answer_tab = []

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            with before_close(lambda: answer_tab.append(take_step_only(study.pk))):
                daily_study.settle_stale(self.user)
            daily_study._finish(answer_tab[0])

        study = self._assert_settled(study.pk, answered=TOTAL, bonus=True)
        self.assertEqual(study.score, TOTAL + BONUS)
        self.assertEqual(answer_tab[0].score, TOTAL + BONUS, "진 쪽 인스턴스가 낡았다")

    def test_the_whole_last_answer_right_before_settles_close_gives_one_bonus(self):
        """정산이 닫기 직전에 마지막 답이 닫기까지 끝낸다. 정산은 0 행이다."""
        study, token, _q = play(self.user, TOTAL - 1)

        def other_tab():
            daily_study.answer(self.user, token, _correct_id_of(token))

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            with before_close(other_tab):
                daily_study.settle_stale(self.user)

        study = self._assert_settled(study.pk, answered=TOTAL, bonus=True)
        self.assertEqual(study.score, TOTAL + BONUS)

    def test_an_answer_after_settle_closed_is_refused(self):
        """정산이 먼저 닫으면 뒤에 온 답은 거절되고 점수는 그대로다."""
        study, token, _q = play(self.user, 3)
        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
            with self.assertRaises(SessionError):
                daily_study.answer(self.user, token, _correct_id_of(token))
        self._assert_settled(study.pk, answered=3, bonus=False)

    def test_a_step_before_settle_and_a_late_publish_after_it(self):
        """답의 채점 -> 정산 전부 -> 답의 발행. 늦은 발행이 값을 안 바꾼다."""
        study, _t, _q = play(self.user, 3)
        answer_tab = take_step_only(study.pk)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
        daily_study._publish(answer_tab)

        self._assert_settled(study.pk, answered=4, bonus=False)

    def test_a_late_publish_of_an_older_score_does_not_lower_the_day(self):
        """정산이 보너스까지 쓴 뒤 옛 점수 발행이 늦게 와도 안 내려간다."""
        study, _t, _q = play(self.user, TOTAL - 1)
        stale = DailyStudy.objects.get(pk=study.pk)  # score = TOTAL - 1
        take_step_only(study.pk)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)
        daily_study._publish(stale)

        self._assert_settled(study.pk, answered=TOTAL, bonus=True)

    def test_a_settle_inside_a_settle_does_not_double_the_bonus(self):
        """두 정산이 겹친다 - 한쪽이 닫기 직전에 다른 쪽이 통째로 돈다."""
        study, _t, _q = play(self.user, TOTAL - 1)
        take_step_only(study.pk)  # 다 풀었지만 열린 판

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            with before_close(lambda: daily_study.settle_stale(self.user)):
                daily_study.settle_stale(self.user)

        study = self._assert_settled(study.pk, answered=TOTAL, bonus=True)
        self.assertEqual(study.score, TOTAL + BONUS)


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class SettleAnswerRaceTest(_KeepsCacheTable, TransactionTestCase):
    """실제 스레드로 정산과 답하기를 겹친다. 판마다 새 사용자로 여러 번.

    Postgres 전용이다(SQLite 는 동시 쓰기를 잠금 에러로 돌려준다).
    결정적 재현은 InterleavingTest 가 하고, 여기는 실제 DB 의 행 잠금
    아래에서도 같은 불변식이 서는지 본다.
    """

    reset_sequences = True
    ROUNDS = 12

    def setUp(self):
        cache.clear()
        seed_words()

    @staticmethod
    def _race(*calls):
        results = [None] * len(calls)
        barrier = threading.Barrier(len(calls))

        def one(index, fn, args):
            barrier.wait()
            try:
                results[index] = ("ok", fn(*args))
            except Exception as exc:  # 무엇이 났는지 그대로 본다
                results[index] = ("err", exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=one, args=(i, fn, args))
            for i, (fn, args) in enumerate(calls)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def _check(self, user, study_pk: int, results, round_no: int):
        errs = [r[1] for r in results if r[0] == "err"]
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs),
            f"{round_no}판: 500 이 났다: {errs}",
        )
        study = DailyStudy.objects.get(pk=study_pk)
        self.assertTrue(study.is_done, f"{round_no}판: 안 닫혔다")
        bonus = study.bonus if study.answered >= study.total_questions else 0
        self.assertEqual(
            study.score, study.correct + bonus, f"{round_no}판: 점수가 틀렸다"
        )
        self.assertEqual(
            DailyScore.objects.get(user=user, day=study.day).daily_study_score,
            study.score,
            f"{round_no}판: 그날 줄과 판이 갈렸다",
        )
        return study

    def _run_rounds(self, answered_before: int):
        outcomes = set()
        for round_no in range(self.ROUNDS):
            user = make_user(f"경합{answered_before}_{round_no}")
            study, token, _q = play(user, answered_before)
            picked = _correct_id_of(token)

            with mock.patch.object(calendar_kst, "today", tomorrow()):
                results = self._race(
                    (daily_study.settle_stale, (user,)),
                    (daily_study.answer, (user, token, picked)),
                )
            study = self._check(user, study.pk, results, round_no)
            outcomes.add(study.answered)
        return outcomes

    def test_settle_racing_a_middle_answer(self):
        """중간 답과 정산. 답이 들어가든 거절되든 판과 그날 줄이 같다."""
        outcomes = self._run_rounds(3)
        self.assertTrue(outcomes <= {3, 4}, outcomes)

    def test_settle_racing_the_last_answer(self):
        """마지막 답과 정산. 보너스는 다 풀었을 때만, 한 번."""
        outcomes = self._run_rounds(TOTAL - 1)
        self.assertTrue(outcomes <= {TOTAL - 1, TOTAL}, outcomes)

