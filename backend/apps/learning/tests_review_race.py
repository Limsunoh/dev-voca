"""복습 답과 일일공부·자유 문제풀이 답이 같은 줄을 동시에 고칠 때.

ReviewState 한 줄(사람 x 항목)을 세 경로가 고친다.

    복습 답          review._record           정답이면 연속 +1(상한 2), 오답이면 0
    일일공부 답      record.bump_review_states  오답이면 연속 0, 정답은 연속을 안 건드림
    자유 문제풀이    record.bump_review_states  (같음)

Postgres 의 실제 행 잠금 아래에서 여기를 본다. tests_review.RecordRaceTest 가
한 연결 안에서 순서를 고정해 재현한다면, 여기는 두 연결이 실제로 서로를
기다리는지, 그리고 그 결과가 둘 중 어느 한 순서로 차례로 한 것과 같은지를 본다.

불변식: 복습 정답(R)과 다른 곳의 오답(M)이 겹치면 결과는 둘 중 하나다.

    R 다음 M    R 이 (2, 졸업) 을 돌려주고, 줄은 연속 0 에 틀린 것으로 남는다
    M 다음 R    R 이 (1, 졸업 아님) 을 돌려주고, 줄은 연속 1 에 맞힌 것으로 남는다

어느 쪽이든 복습에서 맞힌 시각(last_correct_at)은 남는다 - 오답은 그 칸을
안 쓴다.
"""

from __future__ import annotations

import threading
import time
import unittest
from datetime import timedelta

from django.core.cache import cache
from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.vocab.models import Word

from . import record, review
from .models import ReviewState
from .tests_daily_study_edge import _KeepsCacheTable
from .tests_review import make_user, seed_words

# 한쪽을 잠금을 쥔 채로 붙잡아 두는 시간. 상대가 이만큼 기다렸으면 막힌 것이다.
HOLD = 1.0


def _is_review_update(sql: str) -> bool:
    return sql.lstrip().upper().startswith("UPDATE") and "learning_reviewstate" in sql


def _run_threads(*calls):
    """calls 를 각자의 스레드(= 각자의 DB 연결)에서 돌리고 결과를 모은다.

    결과는 ("ok", 반환값, 걸린 초) 또는 ("err", 예외, 걸린 초).
    """
    results = [None] * len(calls)

    def one(index, fn):
        began = time.monotonic()
        try:
            results[index] = ("ok", fn(), time.monotonic() - began)
        except Exception as exc:  # 무엇이 났는지 그대로 본다
            results[index] = ("err", exc, time.monotonic() - began)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=one, args=(i, fn)) for i, fn in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class ReviewAnswerRaceTest(_KeepsCacheTable, TransactionTestCase):
    """복습 정답과 다른 곳의 오답이 실제 두 연결에서 겹칠 때."""

    ROUNDS = 12

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습실경합")
        self.long_ago = timezone.now() - timedelta(days=1)

    def _half_done(self, word_pk: int) -> ReviewState:
        """복습에서 한 번 맞힌 줄. 한 번 더 맞히면 졸업한다."""
        return ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=word_pk,
            streak=1,
            is_wrong=False,
            last_correct_at=self.long_ago,
        )

    def _hit(self, word_pk: int):
        return lambda: review._record(self.user, "word", word_pk, correct=True)

    def _miss(self, word_pk: int):
        return lambda: record.bump_review_states(self.user, {("word", word_pk): False})

    def _assert_one_serial_order(self, row: ReviewState, returned, label: str):
        if returned == (2, True):
            # R 다음 M.
            self.assertEqual(
                (row.streak, row.is_wrong), (0, True), f"{label}: 나중 오답이 사라졌다"
            )
        elif returned == (1, False):
            # M 다음 R.
            self.assertEqual(
                (row.streak, row.is_wrong),
                (1, False),
                f"{label}: 돌려준 값과 DB 가 다르다",
            )
        else:
            self.fail(f"{label}: 어느 순서로도 나올 수 없는 값을 돌려줬다 {returned}")
        self.assertGreater(
            row.last_correct_at, self.long_ago, f"{label}: 복습에서 맞힌 시각이 사라졌다"
        )

    def test_a_miss_arriving_during_the_review_write_waits_and_lands_last(self):
        """복습 정답이 줄을 고친 뒤 커밋 전에 오답이 오면, 오답은 기다렸다 뒤에 쓴다.

        복습 쪽은 UPDATE 와 방금 쓴 값 읽기를 한 트랜잭션에 묶는다. 묶음이
        풀리면 오답이 그 틈에 커밋돼, 맞힌 답에 "연속 0" 을 돌려준다.
        """
        word_pk = Word.objects.first().pk
        self._half_done(word_pk)
        review_wrote = threading.Event()
        miss_done = threading.Event()
        miss_finished_while_holding = []

        def hit():
            def wrapper(execute, sql, params, many, context):
                result = execute(sql, params, many, context)
                if _is_review_update(sql) and not review_wrote.is_set():
                    review_wrote.set()
                    miss_finished_while_holding.append(miss_done.wait(HOLD))
                return result

            with connection.execute_wrapper(wrapper):
                return review._record(self.user, "word", word_pk, correct=True)

        def miss():
            review_wrote.wait(10)
            try:
                self._miss(word_pk)()
            finally:
                miss_done.set()

        (r_kind, r_val, _), (m_kind, m_val, m_took) = _run_threads(hit, miss)

        self.assertEqual((r_kind, m_kind), ("ok", "ok"), (r_val, m_val))
        self.assertEqual(miss_finished_while_holding, [False], "오답이 잠금을 안 기다렸다")
        self.assertEqual(r_val, (2, True), "복습이 방금 쓴 값이 아닌 것을 돌려줬다")
        self.assertGreaterEqual(m_took, HOLD * 0.8, "오답이 잠금을 안 기다렸다")
        row = ReviewState.objects.get(user=self.user, target_id=word_pk)
        self._assert_one_serial_order(row, r_val, "R 다음 M")

    def test_a_review_answer_during_an_open_daily_miss_counts_from_zero(self):
        """일일공부 오답이 커밋 전일 때 복습 정답이 오면, 기다렸다 0 에서 센다.

        일일공부는 답 하나를 트랜잭션으로 묶어 bump_review_states 를 부른다
        (daily_study.answer). 복습 쪽이 커밋된 옛 값(1)을 읽어 두고 +1 하면
        방금 틀린 단어가 졸업한다.
        """
        word_pk = Word.objects.first().pk
        self._half_done(word_pk)
        miss_written = threading.Event()

        def miss():
            with transaction.atomic():
                self._miss(word_pk)()
                miss_written.set()
                time.sleep(HOLD)

        def hit():
            miss_written.wait(10)
            return self._hit(word_pk)()

        (m_kind, m_val, _), (r_kind, r_val, r_took) = _run_threads(miss, hit)

        self.assertEqual((m_kind, r_kind), ("ok", "ok"), (m_val, r_val))
        self.assertEqual(r_val, (1, False), "방금 틀린 단어가 졸업했다")
        self.assertGreaterEqual(r_took, HOLD * 0.5, "복습 쪽이 잠금을 안 기다렸다")
        row = ReviewState.objects.get(user=self.user, target_id=word_pk)
        self._assert_one_serial_order(row, r_val, "M 다음 R")

    def test_many_free_races_always_match_one_serial_order(self):
        """순서를 고정하지 않고 여러 번 겹친다. 매번 어느 한 순서의 결과다."""
        words = list(Word.objects.values_list("pk", flat=True)[: self.ROUNDS])
        for round_no, word_pk in enumerate(words):
            self._half_done(word_pk)
            barrier = threading.Barrier(2)

            def hit(word_pk=word_pk, barrier=barrier):
                barrier.wait()
                return self._hit(word_pk)()

            def miss(word_pk=word_pk, barrier=barrier):
                barrier.wait()
                return self._miss(word_pk)()

            (r_kind, r_val, _), (m_kind, m_val, _) = _run_threads(hit, miss)
            self.assertEqual((r_kind, m_kind), ("ok", "ok"), (round_no, r_val, m_val))
            row = ReviewState.objects.get(user=self.user, target_id=word_pk)
            self._assert_one_serial_order(row, r_val, f"{round_no}판")

    def test_two_review_tabs_answering_at_once_graduate_exactly_once(self):
        """두 탭이 같은 항목을 동시에 맞히면 연속은 2 이고 졸업 안내는 한 번이다.

        읽어 두고 +1 하면 둘 다 0 을 읽어 둘 다 1 을 쓴다 - 두 번 맞힌 것이
        한 번으로 줄어든다.
        """
        words = list(Word.objects.values_list("pk", flat=True)[: self.ROUNDS])
        for round_no, word_pk in enumerate(words):
            ReviewState.objects.create(
                user=self.user, target_type="word", target_id=word_pk, is_wrong=True
            )
            barrier = threading.Barrier(2)

            def hit(word_pk=word_pk, barrier=barrier):
                barrier.wait()
                return self._hit(word_pk)()

            results = _run_threads(hit, hit)
            self.assertTrue(all(r[0] == "ok" for r in results), (round_no, results))
            self.assertEqual(
                sorted(r[1] for r in results),
                [(1, False), (2, True)],
                f"{round_no}판: 두 번 맞힌 것이 한 번으로 줄었다",
            )
            row = ReviewState.objects.get(user=self.user, target_id=word_pk)
            self.assertEqual(row.streak, 2, f"{round_no}판")
