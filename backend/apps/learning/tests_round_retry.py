"""한 판 답하기의 재전송을 깨뜨려 보는 테스트.

응답만 끊긴 사람이 같은 토큰·같은 답을 다시 보내면 처음 응답을 그대로
돌려준다(session._take_step 의 choice·reply). 이 길이 되돌리기 방어를 다시
여는지 본다.

    같은 답        처음 토큰·결과·문제 그대로. 새로 채점하지 않는다(경과 시간도 처음 것)
    다른 답        지금처럼 거절. 정답을 캐낸 뒤 옛 토큰 + 정답도 거절
    동시에         보기 넷을 동시에 보내도 하나만 성공. 같은 답끼리는 같은 응답
    넘기기         옛 토큰으로 넘기기 횟수를 되살리지 못한다
    복습           재전송은 여전히 거절(review.py 는 choice 를 안 넘긴다)
    500 금지       큰 수·음수·bool·문자열 몸통이 4xx 거나 정상 응답
"""

from __future__ import annotations

import threading
import unittest
from dataclasses import asdict
from datetime import timedelta

from django.core.cache import cache
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.vocab.models import Word

from . import review, session
from .models import RoundStep
from .tests import make_words
from .tests_abuse import ANSWER_URL, FINISH_URL, START_URL, answer_id_of, frozen
from .tests_daily_study_edge import _KeepsCacheTable
from .tests_review import a_round, make_user, seed_words


def wrong_of(token: str, question: dict) -> int:
    """지금 문제의 오답 보기 하나."""
    right = answer_id_of(token)
    return next(c["id"] for c in question["choices"] if c["id"] != right)


def round_id(token: str) -> str:
    return session._load(token)["id"]


class SameAnswerRetryTest(TestCase):
    """같은 토큰·같은 답의 재전송."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_same_answer_returns_the_first_reply_and_scores_once(self):
        """같은 답을 세 번 보내도 응답은 처음 것이고 끝내기 집계는 한 번이다."""
        token, question = session.start()
        picked = wrong_of(token, question)

        first = session.answer(token, picked)
        for _ in range(3):
            again = session.answer(token, picked)
            self.assertEqual(again[0], first[0], "재전송이 다른 토큰을 줬다")
            self.assertEqual(asdict(again[1]), asdict(first[1]))
            self.assertEqual(again[2], first[2], "재전송이 다른 다음 문제를 줬다")

        self.assertEqual(RoundStep.objects.filter(round_id=round_id(token)).count(), 1)
        summary = session.finish(first[0])
        self.assertEqual(summary["answered"], 1)
        self.assertEqual(summary["score"], session.SCORE_WRONG)

    def test_a_correct_answer_resent_is_still_one_point(self):
        """맞힌 답을 다시 보내도 +1 이 두 번 쌓이지 않는다."""
        token, _ = session.start()
        right = answer_id_of(token)

        next_token, result, _ = session.answer(token, right)
        session.answer(token, right)
        session.answer(token, right)

        self.assertEqual(result.score, session.SCORE_IN_TIME)
        self.assertEqual(session.finish(next_token)["score"], session.SCORE_IN_TIME)

    def test_resend_keeps_the_first_elapsed_time(self):
        """제때 맞힌 답을 한참 뒤 다시 보내도 처음 경과 시간·점수 그대로다.

        반대로 늦게 다시 보내 결과를 바꿀 수도 없다(새로 채점하지 않는다).
        """
        base = timezone.now()
        with frozen(base):
            token, _ = session.start()
        right = answer_id_of(token)

        with frozen(base + timedelta(milliseconds=500)):
            _, first, _ = session.answer(token, right)
        with frozen(base + timedelta(seconds=60)):
            _, again, _ = session.answer(token, right)

        self.assertEqual(first.elapsed_ms, 500)
        self.assertEqual(again.elapsed_ms, 500)
        self.assertTrue(again.in_time)
        self.assertEqual(again.score, session.SCORE_IN_TIME)

    def test_resent_token_continues_the_round(self):
        """재전송으로 받은 토큰으로 이어 풀면 정상으로 진행되고 끝난다."""
        token, question = session.start()
        picked = wrong_of(token, question)
        session.answer(token, picked)

        resent_token, _, next_question = session.answer(token, picked)
        token2, _, _ = session.answer(resent_token, next_question["choices"][0]["id"])

        self.assertEqual(session.finish(token2)["answered"], 2)
        # 이미 이어 푼 뒤의 재전송 토큰으로는 끝낼 수 없다.
        with self.assertRaises(session.SessionError):
            session.finish(resent_token)

    def test_resend_after_moving_on_does_not_rewind(self):
        """두 문제를 푼 뒤 첫 토큰을 다시 보내도 그 지점부터 다른 답으로 갈 수 없다."""
        t0, q0 = session.start()
        a0 = wrong_of(t0, q0)
        t1, _, q1 = session.answer(t0, a0)
        t2, _, _ = session.answer(t1, q1["choices"][0]["id"])

        replay_t1, _, _ = session.answer(t0, a0)
        self.assertEqual(replay_t1, t1)

        other = next(c["id"] for c in q1["choices"] if c["id"] != q1["choices"][0]["id"])
        with self.assertRaises(session.SessionError):
            session.answer(replay_t1, other)
        self.assertEqual(session.finish(t2)["answered"], 2)


class DifferentAnswerTest(TestCase):
    """다른 답의 재전송은 예전처럼 거절된다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_every_other_choice_is_refused(self):
        token, question = session.start()
        ids = [c["id"] for c in question["choices"]]
        session.answer(token, ids[0])

        for other in ids[1:]:
            with self.assertRaises(session.SessionError):
                session.answer(token, other)

    def test_mined_answer_on_the_old_token_is_refused(self):
        """오답으로 정답을 캐낸 뒤 옛 토큰 + 정답은 거절된다."""
        token, question = session.start()
        picked = wrong_of(token, question)
        next_token, first, _ = session.answer(token, picked)
        self.assertFalse(first.correct)

        with self.assertRaises(session.SessionError):
            session.answer(token, first.answer_id)
        self.assertEqual(session.finish(next_token)["score"], session.SCORE_WRONG)

    def test_skip_and_choice_do_not_match_each_other(self):
        """넘긴 뒤 같은 토큰으로 답을, 답한 뒤 같은 토큰으로 넘기기를 보내면 거절."""
        token, question = session.start()
        session.answer(token, None, skip=True)
        with self.assertRaises(session.SessionError):
            session.answer(token, answer_id_of(token))

        token, question = session.start()
        session.answer(token, question["choices"][0]["id"])
        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=True)

    def test_skip_with_a_choice_is_a_skip(self):
        """skip=True 에 보기를 같이 실어도 넘기기다. 보기만 바꿔 다시 보내도 같은 응답."""
        token, question = session.start()
        ids = [c["id"] for c in question["choices"]]
        first = session.answer(token, ids[0], skip=True)
        again = session.answer(token, ids[1], skip=True)

        self.assertTrue(first[1].skipped)
        self.assertEqual(again[0], first[0])

    def test_an_old_row_without_a_reply_is_refused(self):
        """배포 전에 생긴 행(choice 빈 값)이나 응답이 빠진 행은 재전송으로 열리지 않는다."""
        token, question = session.start()
        picked = question["choices"][0]["id"]
        RoundStep.objects.create(round_id=round_id(token), step=0)
        with self.assertRaises(session.SessionError):
            session.answer(token, picked)

        token, question = session.start()
        picked = question["choices"][0]["id"]
        RoundStep.objects.create(
            round_id=round_id(token), step=0, choice=f"choice:{picked}", reply=None
        )
        with self.assertRaises(session.SessionError):
            session.answer(token, picked)


class DeployOverlapTest(TestCase):
    """배포가 겹치거나 백엔드를 되돌렸을 때도 판이 이어진다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_a_row_inserted_without_choice_gets_the_db_default(self):
        """choice 칸을 모르는 옛 코드의 INSERT 가 NOT NULL 에 걸리지 않는다.

        걸리면 옛 _take_step 이 그 IntegrityError 를 되돌리기로 읽어 한 판과
        복습의 모든 답을 거절한다. 그래서 칸에 DB 기본값을 둔다(models.RoundStep).
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO learning_roundstep (round_id, step, created_at) VALUES (%s, %s, %s)",
                ["old-server", 0, timezone.now()],
            )
        row = RoundStep.objects.get(round_id="old-server", step=0)
        self.assertEqual(row.choice, "")
        self.assertIsNone(row.reply)

    def test_a_stored_reply_with_an_unknown_field_still_resends(self):
        """저장한 뒤 배포로 Result 의 칸이 빠져도 재전송이 500 이 아니다."""
        token, question = session.start()
        picked = wrong_of(token, question)
        first_token, first, _ = session.answer(token, picked)

        row = RoundStep.objects.get(round_id=round_id(token), step=0)
        row.reply["result"]["gone_in_this_deploy"] = 1
        row.save(update_fields=["reply"])

        again_token, again, _ = session.answer(token, picked)
        self.assertEqual(again_token, first_token)
        self.assertEqual(asdict(again), asdict(first))


class SkipRewindTest(TestCase):
    """옛 토큰으로 넘기기 횟수를 되살리지 못한다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_rewinding_skips_gives_back_the_same_tokens(self):
        t0, _ = session.start()
        issued = []
        token = t0
        for _ in range(session.MAX_SKIPS):
            token, _, _ = session.answer(token, None, skip=True)
            issued.append(token)

        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=True)

        # 옛 토큰에서 다시 넘기면 처음 응답만 나온다.
        replay = t0
        for expected in issued:
            replay, result, question = session.answer(replay, None, skip=True)
            self.assertEqual(replay, expected)
            self.assertTrue(result.skipped)

        self.assertEqual(question["skips_left"], 0)
        with self.assertRaises(session.SessionError):
            session.answer(replay, None, skip=True)

        # 넘긴 자리에 답을 끼워 넣을 수도 없다.
        with self.assertRaises(session.SessionError):
            session.answer(t0, answer_id_of(t0))

        summary = session.finish(issued[-1])
        self.assertEqual(summary["skipped"], session.MAX_SKIPS)
        self.assertEqual(summary["answered"], session.MAX_SKIPS)


class DeadlineRetryTest(TestCase):
    """마감과 마지막 답 근처의 재전송."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_resend_after_the_deadline_returns_the_first_reply(self):
        """마감 전에 답했고 응답만 끊긴 채 마감이 지났다. 재전송은 처음 응답 그대로다."""
        base = timezone.now()
        with frozen(base):
            token, question = session.start()
        picked = wrong_of(token, question)

        with frozen(base + timedelta(seconds=10)):
            first = session.answer(token, picked)
        self.assertIsNotNone(first[2])

        with frozen(base + timedelta(seconds=session.ROUND_SECONDS + 60)):
            again = session.answer(token, picked)
        self.assertEqual(again[0], first[0])
        self.assertEqual(again[2], first[2])

    def test_resending_the_last_answer_then_finishing(self):
        """마지막 답(다음 문제 없음)을 다시 보내도 끝내기는 정상, 집계는 한 번."""
        base = timezone.now()
        with frozen(base):
            token, question = session.start()
        picked = wrong_of(token, question)

        late = base + timedelta(seconds=session.ROUND_SECONDS + 30)
        with frozen(late):
            last_token, _, nxt = session.answer(token, picked)
            again_token, _, again_nxt = session.answer(token, picked)

        self.assertIsNone(nxt)
        self.assertIsNone(again_nxt)
        self.assertEqual(again_token, last_token)

        summary = session.finish(again_token)
        self.assertEqual(summary["answered"], 1)
        self.assertEqual(summary["score"], session.SCORE_WRONG)
        # 끝난 판 토큰에는 문제가 없어 더 답할 수 없다.
        with self.assertRaises(session.SessionError):
            session.answer(again_token, picked)


class OddInputTest(TestCase):
    """이상한 값. 500 이 나면 안 되고, 재전송 규칙이 새지 않아야 한다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def test_negative_choice_resent_is_the_same_wrong(self):
        token, _ = session.start()
        first = session.answer(token, -5)
        again = session.answer(token, -5)
        self.assertEqual(again[0], first[0])
        self.assertEqual(first[1].score, session.SCORE_WRONG)
        with self.assertRaises(session.SessionError):
            session.answer(token, -6)

    def test_huge_choice_does_not_break_and_cannot_change_the_result(self):
        """칸(32자)보다 긴 수는 잘린다. 잘려서 같아지면 처음 응답이 올 뿐이다."""
        token, _ = session.start()
        first = session.answer(token, 10**30)
        again = session.answer(token, 10**30 + 1)
        self.assertEqual(again[0], first[0])
        self.assertEqual(asdict(again[1]), asdict(first[1]))
        self.assertEqual(session.finish(first[0])["score"], session.SCORE_WRONG)

    def test_huge_choice_cannot_be_used_to_land_on_the_right_answer(self):
        """큰 수로 먼저 보낸 뒤 정답 id 로 다시 보내도 거절된다(자른 값이 다르다)."""
        token, _ = session.start()
        session.answer(token, 10**30)
        with self.assertRaises(session.SessionError):
            session.answer(token, answer_id_of(token))


class ReviewResendTest(TestCase):
    """복습은 재전송을 그대로 거절한다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습재전송")
        words = list(Word.objects.values_list("pk", flat=True)[:3])
        a_round(self.user, [(pk, False) for pk in words])

    def test_same_answer_on_the_same_review_token_is_refused(self):
        token, question, _ = review.start(self.user)
        picked = question["choices"][0]["id"]
        review.answer(self.user, token, picked)

        with self.assertRaises(session.SessionError):
            review.answer(self.user, token, picked)

        row = RoundStep.objects.get(round_id=review._load(token)["id"], step=0)
        self.assertEqual(row.choice, "")
        self.assertIsNone(row.reply)


class RoundRetryHttpTest(TestCase):
    """중계가 부르는 길(/api/learning/rounds/answer/)로도 같은지."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def _start(self) -> dict:
        res = self.client.post(START_URL, {}, content_type="application/json")
        self.assertEqual(res.status_code, 201)
        return res.json()

    def _answer(self, body: dict):
        return self.client.post(ANSWER_URL, body, content_type="application/json")

    def test_same_body_twice_gives_the_same_response(self):
        started = self._start()
        body = {"token": started["token"], "choice_id": started["question"]["choices"][0]["id"]}

        first = self._answer(body)
        again = self._answer(body)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), first.json())

        finished = self.client.post(
            FINISH_URL, {"token": first.json()["token"]}, content_type="application/json"
        )
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.json()["answered"], 1)

    def test_another_choice_on_the_same_token_is_400(self):
        started = self._start()
        ids = [c["id"] for c in started["question"]["choices"]]
        self.assertEqual(self._answer({"token": started["token"], "choice_id": ids[0]}).status_code, 200)
        res = self._answer({"token": started["token"], "choice_id": ids[1]})
        self.assertEqual(res.status_code, 400)

    def test_odd_bodies_are_never_500(self):
        started = self._start()
        token = started["token"]
        first_id = started["question"]["choices"][0]["id"]
        for body in (
            {"token": token, "choice_id": True},
            {"token": token, "choice_id": str(first_id)},
            {"token": token, "choice_id": None},
            {"token": token, "choice_id": [first_id]},
            {"token": token, "skip": "true"},
        ):
            res = self._answer(body)
            self.assertEqual(res.status_code, 400, body)

        # 위 거절들은 순번을 태우지 않는다. 큰 수로 답하면 정상(오답)이다.
        res = self._answer({"token": token, "choice_id": 10**30})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["result"]["correct"])
        again = self._answer({"token": token, "choice_id": 10**30})
        self.assertEqual(again.json(), res.json())


def _run_together(calls):
    """calls 를 같은 순간에 각자의 스레드(= 각자의 DB 연결)로 돌린다."""
    results = [None] * len(calls)
    barrier = threading.Barrier(len(calls))

    def one(index, fn):
        barrier.wait()
        try:
            results[index] = ("ok", fn())
        except Exception as exc:  # 무엇이 났는지 그대로 본다
            results[index] = ("err", exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=one, args=(i, fn)) for i, fn in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class RoundRetryRaceTest(_KeepsCacheTable, TransactionTestCase):
    """실제 연결 여럿이 같은 순번을 두고 겹칠 때."""

    ROUNDS = 5

    def setUp(self):
        cache.clear()
        make_words()

    def _assert_no_500(self, results):
        errs = [r[1] for r in results if r[0] == "err"]
        self.assertTrue(
            all(isinstance(e, session.SessionError) for e in errs), f"예상 밖 예외: {errs}"
        )

    def test_four_choices_at_once_only_one_wins(self):
        for _ in range(self.ROUNDS):
            token, question = session.start()
            ids = [c["id"] for c in question["choices"]]
            results = _run_together([lambda c=c: session.answer(token, c) for c in ids])

            self._assert_no_500(results)
            ok = [r[1] for r in results if r[0] == "ok"]
            self.assertEqual(len(ok), 1, f"둘 이상 통과했다: {results}")
            self.assertEqual(RoundStep.objects.filter(round_id=round_id(token)).count(), 1)
            self.assertEqual(session.finish(ok[0][0])["answered"], 1)

    def test_mixed_choices_only_the_winners_copies_succeed(self):
        """보기 a 둘과 b, c 를 동시에. 이긴 답과 같은 것만 같은 응답을 받는다."""
        for _ in range(self.ROUNDS):
            token, question = session.start()
            ids = [c["id"] for c in question["choices"]]
            sent = [ids[0], ids[0], ids[1], ids[2]]
            results = _run_together([lambda c=c: session.answer(token, c) for c in sent])

            self._assert_no_500(results)
            winners = {sent[i] for i, r in enumerate(results) if r[0] == "ok"}
            self.assertEqual(len(winners), 1, f"다른 답 둘이 통과했다: {results}")
            winner = winners.pop()
            ok = [r[1] for r in results if r[0] == "ok"]
            self.assertEqual(len(ok), sent.count(winner), f"이긴 답의 사본이 거절됐다: {results}")
            self.assertEqual(len({o[0] for o in ok}), 1, "같은 답에 다른 토큰이 나갔다")
            for o in ok[1:]:
                self.assertEqual(asdict(o[1]), asdict(ok[0][1]))
                self.assertEqual(o[2], ok[0][2])
            self.assertEqual(RoundStep.objects.filter(round_id=round_id(token)).count(), 1)

    def test_the_same_answer_from_many_threads_gets_one_reply(self):
        for _ in range(self.ROUNDS):
            token, question = session.start()
            picked = question["choices"][0]["id"]
            results = _run_together([lambda: session.answer(token, picked)] * 8)

            self.assertTrue(all(r[0] == "ok" for r in results), f"같은 답이 거절됐다: {results}")
            self.assertEqual(len({r[1][0] for r in results}), 1)
            for r in results[1:]:
                self.assertEqual(r[1][2], results[0][1][2], "같은 답에 다른 다음 문제가 나갔다")
                self.assertEqual(asdict(r[1][1]), asdict(results[0][1][1]))
            self.assertEqual(RoundStep.objects.filter(round_id=round_id(token)).count(), 1)
            self.assertEqual(session.finish(results[0][1][0])["answered"], 1)

    def test_skips_at_once_on_the_last_skip_do_not_add_a_skip(self):
        """마지막 넘기기를 여러 스레드로 동시에. 넘기기 수는 한도 그대로다."""
        token, _ = session.start()
        for _ in range(session.MAX_SKIPS - 1):
            token, _, _ = session.answer(token, None, skip=True)

        results = _run_together([lambda: session.answer(token, None, skip=True)] * 6)
        self.assertTrue(all(r[0] == "ok" for r in results), results)
        last = results[0][1][0]
        with self.assertRaises(session.SessionError):
            session.answer(last, None, skip=True)
        self.assertEqual(session.finish(last)["skipped"], session.MAX_SKIPS)

