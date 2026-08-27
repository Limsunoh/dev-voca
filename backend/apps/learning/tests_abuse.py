"""판을 깨뜨려보는 테스트.

tests.py 가 "정상 흐름과 알려진 공격" 을 본다면 여기는 **아직 아무도 안 해본
짓** 을 본다. 세 가지를 노린다.

    - 검수 게이트: 검수 안 된 단어·문장이 문제 어디로도 새면 안 된다
    - 하루 상한: 자정 경계·여러 판·여러 계정으로도 한 판 이상 못 센다
    - 500 금지: 어떤 몸통을 던져도 4xx 여야 한다

난수가 든 자리는 전부 고정한다. 유형을 안 고정하면 "빈칸 문제를 검사했다"
고 믿고 실제로는 뜻 고르기만 다섯 번 본 테스트가 된다.
"""

from __future__ import annotations

import json
import random
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import calendar_kst, record, session
from .models import DailyScore, QuizSession, SessionKind

User = get_user_model()

START_URL = "/api/learning/rounds/"
ANSWER_URL = "/api/learning/rounds/answer/"
FINISH_URL = "/api/learning/rounds/finish/"

# 테스트 사용자를 만들 때 쓰는 비밀번호. 매번 새로 만든다.
# 리터럴로 두면 비밀값 탐지기가 하드코딩된 비밀번호로 본다.
# 값 자체는 아무 데서도 비교하지 않아 무엇이든 상관없다.
PASSWORD = secrets.token_urlsafe(16)

KST = session.timezone.get_current_timezone()


def make_words(count: int = 12, prefix: str = "term", reviewed: bool = True) -> None:
    """문제를 낼 수 있을 만큼 단어를 만든다. tests.py 의 것과 같은 모양."""
    Word.objects.bulk_create(
        [
            Word(
                term=f"{prefix}{i}",
                meaning=f"뜻{i}",
                description=f"설명{i}",
                category="git",
                is_reviewed=reviewed,
            )
            for i in range(count)
        ]
    )


@contextmanager
def forced_kind(kind: str):
    """문제 유형을 고정한다.

    session._make 와 quiz.make_question 이 같은 random 모듈을 쓴다.
    고르는 목록에 원하는 유형이 있을 때만 바꿔치기하고, 나머지 뽑기
    (오답 섞기 등)는 원래대로 둔다.
    """
    real_choice = random.choice

    def fake(seq):
        options = list(seq)
        return kind if kind in options else real_choice(seq)

    with mock.patch.object(random, "choice", side_effect=fake):
        yield


def kst(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=calendar_kst.KST)


@contextmanager
def frozen(moment: datetime):
    """서버 시계를 세운다. session·record 가 같은 timezone.now 를 본다."""
    with mock.patch.object(timezone, "now", return_value=moment):
        yield


def answer_id_of(token: str) -> int:
    """지금 나온 문제의 정답 id. 사용자는 알 수 없지만 테스트는 알아야 한다."""
    _, answer_id = quiz.resolve_answer(session._load(token)["q"], -1)
    return answer_id


class ReviewGateTest(TestCase):
    """검수 안 된 것이 판으로 새는지 본다.

    devvoca 에서 가장 자주 나는 결함이다. 목록·검색은 필터를 눈으로 볼 수
    있지만, 문제 출제는 지문·보기·정답 해설까지 경로가 넷이라 한 곳만
    빠뜨려도 조용히 샌다.
    """

    SECRET_MARKS = ("SECRET", "비밀")

    @classmethod
    def setUpTestData(cls):
        make_words(12, prefix="ok")
        Word.objects.bulk_create(
            [
                Word(
                    term=f"SECRETWORD{i}",
                    meaning=f"비밀뜻{i}",
                    description=f"비밀설명{i}",
                    category="git",
                    is_reviewed=False,
                )
                for i in range(6)
            ]
        )
        Sentence.objects.bulk_create(
            [
                Sentence(
                    text=f"Please ok3 this branch now {i}.",
                    translation=f"해석 {i}",
                    context=f"상황 {i}",
                    kind="phrase",
                    category="git",
                    is_reviewed=True,
                )
                for i in range(6)
            ]
            + [
                Sentence(
                    text=f"SECRETSENTENCE{i} ok3 here.",
                    translation=f"비밀해석 {i}",
                    context=f"비밀상황 {i}",
                    kind="phrase",
                    category="git",
                    is_reviewed=False,
                )
                for i in range(6)
            ]
        )

    def setUp(self):
        cache.clear()

    def assert_clean(self, payload) -> None:
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        for mark in self.SECRET_MARKS:
            self.assertNotIn(mark, blob, f"검수 안 된 내용이 샜다: {blob[:400]}")

    def test_no_unreviewed_content_in_any_question_kind(self):
        """다섯 유형 어느 것으로도 미검수 단어·문장이 나오면 안 된다."""
        for kind in quiz.QuizKind.ALL:
            with self.subTest(kind=kind), forced_kind(kind):
                token, question = session.start()
                self.assert_clean(question)

                for _ in range(6):
                    token, result, question = session.answer(token, -1)
                    self.assert_clean(result.__dict__)
                    if question is None:
                        break
                    self.assert_clean(question)

    def test_unreviewed_content_never_reaches_the_api(self):
        """API 응답 전체를 글자로 훑는다. 어느 칸으로 새든 잡힌다."""
        started = self.client.post(START_URL, {}, content_type="application/json")
        self.assert_clean(started.json())

        token = started.json()["token"]
        for _ in range(10):
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": -1},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200)
            self.assert_clean(res.json())
            token = res.json()["token"]
            if res.json()["finished"]:
                break

    def test_an_answer_unreviewed_after_the_question_is_not_shown(self):
        """문제를 낸 뒤 검수가 취소되면 정답 글자를 알려주지 않는다.

        아무도 확인하지 않은 내용을 정답이라고 보여주면 그대로 잘못 외운다.
        """
        with forced_kind(quiz.QuizKind.MEANING):
            token, _ = session.start()
            target = answer_id_of(token)
            Word.objects.filter(pk=target).update(is_reviewed=False)

            _, result, _ = session.answer(token, target)

        self.assertTrue(result.correct)
        self.assertEqual(result.answer_text, "")
        self.assertEqual(result.answer_extra, "")

    def test_a_corpus_with_nothing_reviewed_cannot_start(self):
        """전부 미검수면 문제를 못 낸다. 500 이 아니라 400 이어야 한다."""
        Word.objects.update(is_reviewed=False)
        Sentence.objects.update(is_reviewed=False)

        res = self.client.post(START_URL, {}, content_type="application/json")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(QuizSession.objects.count(), 0)


class MalformedBodyTest(TestCase):
    """이상한 몸통으로 500 을 내려는 시도. 전부 4xx 여야 한다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()
        self.started = self.client.post(
            START_URL, {}, content_type="application/json"
        ).json()

    def post(self, url: str, body):
        return self.client.post(url, body, content_type="application/json")

    def test_bad_tokens_are_refused(self):
        """token 자리에 무엇이 오든 400."""
        cases = [
            {},
            {"token": ""},
            {"token": " "},
            {"token": None},
            {"token": 12345},
            {"token": True},
            {"token": ["a", "b"]},
            {"token": {"a": 1}},
            {"token": "위조된-토큰", "choice_id": 1},
            {"token": "a.b.c", "choice_id": 1},
            {"token": "x" * 200_000, "choice_id": 1},
        ]
        for url in (ANSWER_URL, FINISH_URL):
            for body in cases:
                with self.subTest(url=url, body=str(body)[:40]):
                    res = self.post(url, {**body, "choice_id": 1})
                    self.assertEqual(res.status_code, 400)

    def test_a_question_token_is_not_a_round_token(self):
        """다른 용도(salt)로 서명한 토큰을 판 토큰으로 못 쓴다."""
        other = quiz.sign_question(1, [1, 2, 3, 4])

        res = self.post(ANSWER_URL, {"token": other, "choice_id": 1})

        self.assertEqual(res.status_code, 400)

    def test_an_expired_token_is_refused(self):
        """수명이 다한 판 토큰. 서명은 멀쩡해도 거절해야 한다."""
        with mock.patch.object(session, "TOKEN_MAX_AGE", -1):
            res = self.post(
                ANSWER_URL, {"token": self.started["token"], "choice_id": 1}
            )

        self.assertEqual(res.status_code, 400)

    def test_bodies_that_are_not_objects(self):
        """JSON 배열·문자열·숫자·깨진 JSON. 파서까지 포함해서 4xx."""
        for raw in ("[1, 2, 3]", '"hello"', "42", "null", "{", "", "not json at all"):
            for url in (ANSWER_URL, FINISH_URL):
                with self.subTest(raw=raw, url=url):
                    res = self.client.post(
                        url, raw, content_type="application/json"
                    )
                    self.assertEqual(res.status_code, 400)

    def test_bad_choice_ids_are_refused(self):
        """정수가 아닌 보기 값은 400. 조용히 1번 보기로 읽히면 안 된다."""
        for picked in ("3", 1.5, None, True, False, [1], {"id": 1}, "", "٣"):
            with self.subTest(picked=repr(picked)):
                res = self.post(
                    ANSWER_URL,
                    {"token": self.started["token"], "choice_id": picked},
                )
                self.assertEqual(res.status_code, 400)

    def test_extreme_integers_are_just_wrong_answers(self):
        """아주 큰 수·음수는 거절이 아니라 오답이다. 500 이 나면 안 된다."""
        for picked in (0, -1, -(10**18), 10**30, 2**63):
            with self.subTest(picked=picked):
                started = self.client.post(
                    START_URL, {}, content_type="application/json"
                ).json()

                res = self.post(
                    ANSWER_URL, {"token": started["token"], "choice_id": picked}
                )

                self.assertEqual(res.status_code, 200)
                self.assertFalse(res.json()["result"]["correct"])
                self.assertEqual(res.json()["result"]["score"], session.SCORE_WRONG)

    def test_skip_must_be_a_real_true(self):
        """skip 에 참 같은 값(1, "true")을 넣어 공짜로 넘길 수 없다."""
        for value in (1, "true", "True", "yes", [1]):
            with self.subTest(value=repr(value)):
                res = self.post(
                    ANSWER_URL, {"token": self.started["token"], "skip": value}
                )
                self.assertEqual(res.status_code, 400)

    def test_finish_needs_no_choice(self):
        """끝내기는 token 만 있으면 된다. 남은 칸이 이상해도 무시한다."""
        res = self.post(
            FINISH_URL,
            {"token": self.started["token"], "choice_id": "이상한 값", "skip": "네"},
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["answered"], 0)


class RoundFlowAbuseTest(TestCase):
    """요청 순서와 타이밍만으로 이득을 볼 수 있는지."""

    @classmethod
    def setUpTestData(cls):
        make_words(45)
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        cls.key = Token.objects.create(user=cls.user)

    def setUp(self):
        cache.clear()

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.key.key}"}

    def play(self, hits: int, misses: int = 0) -> str:
        """정답 hits 개, 오답 misses 개를 풀고 마지막 토큰을 돌려준다."""
        token, _ = session.start()
        for _ in range(hits):
            token, _, _ = session.answer(token, answer_id_of(token))
        for _ in range(misses):
            token, _, _ = session.answer(token, -1)
        return token

    def test_finishing_twice_records_once(self):
        """끝내기를 두 번 보내도 한 판이다."""
        token = self.play(3)

        first = record.save_round(self.user, session.finish(token))
        second = record.save_round(self.user, session.finish(token))

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(QuizSession.objects.count(), 1)

    def test_finishing_early_then_playing_on_cannot_upgrade_the_record(self):
        """일찍 끝낸 뒤 더 풀어서 점수를 올려 다시 낼 수 없다.

        판 식별자가 하나라 두 번째 제출이 거절된다. 사용자에게는 손해지만
        점수를 부풀리는 쪽으로는 절대 안 열린다 - 여기가 열리면 "낮을 때
        한 번 내고, 오를 때마다 다시 내기" 가 지배 전략이 된다.
        """
        token = self.play(2)
        record.save_round(self.user, session.finish(token))

        for _ in range(5):
            token, _, _ = session.answer(token, answer_id_of(token))
        again = record.save_round(self.user, session.finish(token))

        self.assertIsNone(again)
        self.assertEqual(DailyScore.objects.get(user=self.user).best_free_score, 2)

    def test_two_rounds_at_once_still_count_as_the_best_one(self):
        """판 두 개를 번갈아 진행해도 그날 점수는 잘한 한 판이다."""
        left, _ = session.start()
        right, _ = session.start()

        for _ in range(2):
            left, _, _ = session.answer(left, answer_id_of(left))
        for _ in range(6):
            right, _, _ = session.answer(right, answer_id_of(right))

        record.save_round(self.user, session.finish(left))
        record.save_round(self.user, session.finish(right))

        self.assertEqual(QuizSession.objects.count(), 2)
        self.assertEqual(DailyScore.objects.get(user=self.user).best_free_score, 6)

    def test_holding_many_rounds_and_finishing_together_is_still_one_score(self):
        """판 여러 개를 쥐고 있다가 한꺼번에 끝내도 더해지지 않는다."""
        tokens = [self.play(i + 1) for i in range(4)]

        for token in tokens:
            record.save_round(self.user, session.finish(token))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.best_free_score, 4)
        self.assertEqual(row.total, 4)

    def test_answering_after_the_round_ended_is_refused(self):
        """끝난 판에 답을 더 보내면 400. 500 이 아니다."""
        token, question = session.start()
        later = timezone.now() + timedelta(seconds=session.ROUND_SECONDS + 1)
        with frozen(later):
            token, _, nxt = session.answer(token, question["choices"][0]["id"])
        self.assertIsNone(nxt)

        res = self.client.post(
            ANSWER_URL,
            {"token": token, "choice_id": 1},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_a_late_correct_answer_earns_nothing(self):
        """제한 시간이 지나서 맞힌 것은 0점이다. 마감 뒤에도 마찬가지다."""
        token, _ = session.start()
        target = answer_id_of(token)

        later = timezone.now() + timedelta(seconds=30)
        with frozen(later):
            _, result, _ = session.answer(token, target)

        self.assertTrue(result.correct)
        self.assertFalse(result.in_time)
        self.assertEqual(result.score, session.SCORE_LATE)

    def test_the_answer_cap_is_exactly_max_answers(self):
        """상한 바로 앞은 되고, 상한에서는 거절이다."""
        token, _ = session.start()
        state = session._load(token)
        state["a"] = [["meaning", "word", 1, 1, 0, 100, 1]] * (
            session.MAX_ANSWERS - 1
        )
        token = session._sign(state)

        token, _, _ = session.answer(token, -1)
        self.assertEqual(len(session._load(token)["a"]), session.MAX_ANSWERS)

        with self.assertRaises(session.SessionError):
            session.answer(token, -1)

    def test_a_round_never_records_more_than_the_answer_cap(self):
        """한 판의 점수 상한이 곧 하루 상한의 상한이다."""
        token, _ = session.start()
        state = session._load(token)
        state["a"] = [["meaning", "word", 1, 1, 0, 100, 1]] * session.MAX_ANSWERS
        summary = session.finish(session._sign(state))

        self.assertEqual(summary["score"], session.MAX_ANSWERS)
        self.assertEqual(summary["answered"], session.MAX_ANSWERS)

    def test_a_frozen_clock_never_costs_a_point(self):
        """0초에 답해도 감점 없이 +1 이다. 시간의 하한이 없다.

        사람은 90초에 25~30문제가 한계지만, 스크립트는 경과 시간이 0 이라
        매번 제한 시간 안이고 마감도 안 온다. 판을 끊는 것은 시계가 아니라
        MAX_ANSWERS 뿐이다 - 그 값이 곧 스크립트의 하루 점수 상한이다.
        """
        now = timezone.now()
        with frozen(now):
            token, _ = session.start()
            for _ in range(30):
                token, result, question = session.answer(token, answer_id_of(token))
                self.assertTrue(result.in_time)
                self.assertEqual(result.elapsed_ms, 0)
                self.assertIsNotNone(question)

            self.assertEqual(session.finish(token)["score"], 30)

    def test_a_round_is_not_bound_to_the_account_that_played_it(self):
        """지금은 판 토큰에 계정이 안 묶여 있다.

        게스트로 푼 판을 아무 계정으로나 낼 수 있다. 대리로 점수를
        올려주는 길이 열려 있다는 뜻이라, 여기가 붉어지면 그때 계정을
        토큰에 심었다는 신호다.
        """
        token = self.play(3)

        saved = record.save_round(self.user, session.finish(token))

        self.assertIsNotNone(saved)
        self.assertEqual(saved.user_id, self.user.pk)

    def test_a_guest_round_can_be_finished_by_a_logged_in_account(self):
        """게스트로 푼 판을 로그인해서 내면 그 계정 기록이 된다."""
        started = self.client.post(
            START_URL, {}, content_type="application/json"
        ).json()
        token = started["token"]
        for _ in range(3):
            token = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                content_type="application/json",
            ).json()["token"]

        res = self.client.post(
            FINISH_URL, {"token": token}, content_type="application/json", **self.auth()
        )

        self.assertTrue(res.json()["recorded"])
        self.assertEqual(QuizSession.objects.get().user_id, self.user.pk)

    def test_only_post_is_allowed(self):
        """다른 메서드는 405. 500 이 아니다."""
        for url in (START_URL, ANSWER_URL, FINISH_URL):
            for call in (self.client.get, self.client.put, self.client.delete):
                with self.subTest(url=url, call=call.__name__):
                    self.assertEqual(call(url).status_code, 405)

    def test_skips_do_not_come_back_by_starting_another_round(self):
        """다른 판을 열어도 이 판의 넘기기가 돌아오지 않는다."""
        token, _ = session.start()
        for _ in range(session.MAX_SKIPS):
            token, _, _ = session.answer(token, None, skip=True)

        session.start()  # 새 판을 열어 상태를 흔들어 본다

        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=True)


class DailyCapTest(TestCase):
    """하루 상한. 몇 판을 하든 그날은 한 판이다."""

    @classmethod
    def setUpTestData(cls):
        make_words(45)
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        cls.other = User.objects.create_user(email="b@example.com", password=PASSWORD)

    def setUp(self):
        cache.clear()

    def summary(self, score: int, token_id: str, kind: str = SessionKind.FREE) -> dict:
        return {
            "token_id": token_id,
            "kind": kind,
            "started_at": timezone.now(),
            "score": score,
            "answered": 3,
            "correct": max(score, 0),
            "skipped": 0,
            "answers": [["meaning", "word", 1, 1, 0, 500, 1]],
        }

    def test_twenty_rounds_leave_one_row(self):
        """스무 판을 해도 그날 행은 하나, 점수는 가장 높은 판이다."""
        for i in range(20):
            record.save_round(self.user, self.summary(i % 7, f"t{i}"))

        rows = DailyScore.objects.filter(user=self.user)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().best_free_score, 6)

    def test_a_worse_round_does_not_lower_the_day(self):
        """뒤에 못한 판이 앞의 최고 기록을 깎으면 안 된다."""
        record.save_round(self.user, self.summary(9, "a"))
        record.save_round(self.user, self.summary(-5, "b"))

        self.assertEqual(DailyScore.objects.get(user=self.user).best_free_score, 9)

    def test_accounts_do_not_share_a_day(self):
        record.save_round(self.user, self.summary(4, "a"))
        record.save_round(self.other, self.summary(11, "b"))

        self.assertEqual(DailyScore.objects.get(user=self.user).best_free_score, 4)
        self.assertEqual(DailyScore.objects.get(user=self.other).best_free_score, 11)

    def test_free_and_daily_study_are_counted_apart(self):
        """자유는 최고 하나, 일일공부는 쌓기. 섞어도 서로 안 먹는다."""
        record.save_round(self.user, self.summary(5, "a"))
        record.save_round(self.user, self.summary(2, "b"))
        record.save_round(self.user, self.summary(3, "c", SessionKind.DAILY))
        record.save_round(self.user, self.summary(4, "d", SessionKind.DAILY))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.best_free_score, 5)
        self.assertEqual(row.daily_study_score, 7)
        self.assertEqual(row.total, 12)

    def test_midnight_in_korea_splits_the_day(self):
        """KST 자정 경계. UTC 로 세면 저녁 판이 다음 날로 밀린다."""
        with frozen(kst(2026, 8, 14, 23, 59)):
            record.save_round(self.user, self.summary(7, "before"))
        with frozen(kst(2026, 8, 15, 0, 1)):
            record.save_round(self.user, self.summary(2, "after"))

        days = list(
            DailyScore.objects.filter(user=self.user)
            .order_by("day")
            .values_list("day", "best_free_score")
        )
        self.assertEqual(
            days, [(datetime(2026, 8, 14).date(), 7), (datetime(2026, 8, 15).date(), 2)]
        )

    def test_a_round_held_over_midnight_lands_on_the_finish_day(self):
        """자정 직전에 시작해 자정 직후에 끝낸 판은 새 날짜로 간다.

        끝낸 시각으로 세기 때문이다(calendar_kst.day_of 의 약속). 판을
        쥐고 있다가 날짜를 고르는 창은 토큰 수명(10분)만큼이다.
        """
        with frozen(kst(2026, 8, 14, 23, 57)):
            token, _ = session.start()
            token, _, _ = session.answer(token, answer_id_of(token))

        with frozen(kst(2026, 8, 15, 0, 1)):
            record.save_round(self.user, session.finish(token))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.day, datetime(2026, 8, 15).date())

    def test_a_round_cannot_be_banked_longer_than_the_token_lives(self):
        """토큰 수명이 지나면 그 판은 아예 낼 수 없다. 며칠씩 못 쟁인다."""
        with frozen(kst(2026, 8, 14, 23, 0)):
            token, _ = session.start()
            token, _, _ = session.answer(token, answer_id_of(token))

        with mock.patch.object(session, "TOKEN_MAX_AGE", -1):
            with self.assertRaises(session.SessionError):
                session.finish(token)

    def test_the_whole_day_through_the_api_is_capped(self):
        """API 로 하루 종일 돌려도 그날 점수는 한 판이다."""
        key = Token.objects.create(user=self.user)
        auth = {"HTTP_AUTHORIZATION": f"Token {key.key}"}

        best = 0
        for hits in (1, 4, 2):
            started = self.client.post(
                START_URL, {}, content_type="application/json", **auth
            ).json()
            token = started["token"]
            for _ in range(hits):
                res = self.client.post(
                    ANSWER_URL,
                    {"token": token, "choice_id": answer_id_of(token)},
                    content_type="application/json",
                    **auth,
                )
                token = res.json()["token"]
            done = self.client.post(
                FINISH_URL, {"token": token}, content_type="application/json", **auth
            ).json()
            self.assertTrue(done["recorded"])
            best = max(best, done["score"])

        self.assertEqual(QuizSession.objects.count(), 3)
        self.assertEqual(DailyScore.objects.get(user=self.user).best_free_score, best)


class QuestionQualityTest(TestCase):
    """문제 자체가 성한지. 정답이 보기에 없거나 지문에 남으면 못 푼다."""

    @classmethod
    def setUpTestData(cls):
        make_words(20)
        for i in range(8):
            Sentence.objects.create(
                text=f"Please term3 this branch before term7 lands {i}.",
                translation=f"해석 {i}",
                context=f"상황 {i}",
                kind="phrase",
                category="git",
                is_reviewed=True,
            )

    def setUp(self):
        cache.clear()

    def test_the_answer_is_always_among_the_choices(self):
        """정답이 보기에 없으면 아무도 못 맞힌다."""
        for kind in quiz.QuizKind.ALL:
            with self.subTest(kind=kind), forced_kind(kind):
                for _ in range(5):
                    token, question = session.start()
                    ids = [c["id"] for c in question["choices"]]
                    self.assertIn(answer_id_of(token), ids)

    def test_choices_are_never_repeated(self):
        """같은 보기가 둘이면 4지선다가 3지선다가 된다."""
        for kind in quiz.QuizKind.ALL:
            with self.subTest(kind=kind), forced_kind(kind):
                for _ in range(5):
                    _, question = session.start()
                    ids = [c["id"] for c in question["choices"]]
                    texts = [c["text"] for c in question["choices"]]
                    self.assertEqual(len(ids), quiz.CHOICE_COUNT)
                    self.assertEqual(len(set(ids)), len(ids))
                    self.assertEqual(len(set(texts)), len(texts), texts)

    def test_a_blank_question_never_shows_its_answer(self):
        """빈칸 문제 지문에 정답 단어가 남아 있으면 문제가 아니다."""
        with forced_kind(quiz.QuizKind.BLANK):
            for _ in range(8):
                token, question = session.start()
                if question["kind"] != quiz.QuizKind.BLANK:
                    continue
                answer = Word.objects.get(pk=answer_id_of(token))
                self.assertNotIn(answer.term.lower(), question["prompt"].lower())

    def test_the_grader_agrees_with_the_choices_shown(self):
        """화면에 보인 보기를 고르면 그대로 채점돼야 한다."""
        for kind in quiz.QuizKind.ALL:
            with self.subTest(kind=kind), forced_kind(kind):
                token, question = session.start()
                target = answer_id_of(token)

                _, result, _ = session.answer(token, target)

                self.assertTrue(result.correct)
                self.assertEqual(result.answer_id, target)
                self.assertNotEqual(result.answer_text, "")


class SituationChoiceTest(TestCase):
    """상황 문제의 보기. 같은 상황 글자를 쓰는 문장이 실제로 있다."""

    @classmethod
    def setUpTestData(cls):
        make_words(8)
        # 한 상황에 문장이 몰려 있는 모양. 그냥 뽑으면 오답 셋 중 둘이
        # 같은 상황이 되기 쉽다 - 시드 데이터가 이 모양이다("브라우저 콘솔"
        # 한 상황에 문장 14개).
        #
        # 상황을 넷으로 두는 이유: 보기가 넷이라 서로 다른 상황이 최소 넷은
        # 있어야 문제를 만들 수 있다. 셋만 두면 중복을 없앤 뒤 보기가
        # 모자라 아예 못 만들고(None), 그건 이 테스트가 보려는 것이 아니다.
        crowd = [
            ("빌드가 깨졌을 때", 4),
            ("브라우저 콘솔", 4),
            ("리뷰를 받을 때", 1),
            ("배포 직후", 1),
        ]
        Sentence.objects.bulk_create(
            [
                Sentence(
                    text=f"Something happens here {context}{i}.",
                    translation=f"해석 {i}",
                    context=context,
                    kind="phrase",
                    category="git",
                    is_reviewed=True,
                )
                for context, count in crowd
                for i in range(count)
            ]
        )

    def test_distractors_do_not_repeat_each_other(self):
        """오답끼리 같은 상황 글자를 쓰면 보기가 둘로 보인다.

        **고쳐진 결함이다. 회귀 방지용이다**(quiz.make_situation_question).
        정답과 겹치는 상황만 빼고 오답끼리는 안 본다. 시드 380개 중 149개가
        남과 상황을 공유하고(가장 많은 "브라우저 콘솔" 하나에 14개), 상황
        문제 한 번에 보기가 겹칠 확률이 1.2% 다.

        """
        made = 0
        for _ in range(10):
            question = quiz.make_situation_question(Sentence.objects.visible())
            self.assertIsNotNone(question)
            made += 1
            texts = [c.text for c in question.choices]
            self.assertEqual(len(set(texts)), len(texts), texts)
        self.assertEqual(made, 10)


class SmallCorpusTest(TestCase):
    """콘텐츠가 모자랄 때. 터지지 않고 400 으로 끝나야 한다."""

    def setUp(self):
        cache.clear()

    def test_no_words_at_all(self):
        res = self.client.post(START_URL, {}, content_type="application/json")

        self.assertEqual(res.status_code, 400)

    def test_three_words_cannot_fill_four_choices(self):
        make_words(3)

        res = self.client.post(START_URL, {}, content_type="application/json")

        self.assertEqual(res.status_code, 400)

    def test_four_words_are_enough(self):
        make_words(4)

        res = self.client.post(START_URL, {}, content_type="application/json")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.json()["question"]["choices"]), quiz.CHOICE_COUNT)

    def test_sentence_kinds_fall_back_to_words(self):
        """문장이 하나도 없어도 문장 유형이 뽑히면 단어 문제로 떨어진다."""
        make_words(12)

        for kind in quiz.QuizKind.SENTENCE_KINDS:
            with self.subTest(kind=kind), forced_kind(kind):
                _, question = session.start()
                self.assertIn(question["kind"], quiz.QuizKind.WORD_KINDS)

    def test_a_round_keeps_going_past_the_recent_list(self):
        """최근 목록보다 단어가 많으면 판이 도중에 끊기지 않는다."""
        make_words(session.RECENT_KEEP + 5)
        token, question = session.start()

        for i in range(session.RECENT_KEEP + 4):
            token, _, question = session.answer(token, -1)
            self.assertIsNotNone(question, f"{i + 1}번째 답에서 판이 끊겼다")


class KnownDefectTest(TestCase):
    """아직 안 고쳐진 것들. 고치면 표시를 지운다."""

    def setUp(self):
        cache.clear()

    def test_description_kind_without_candidates_kills_the_round(self):
        """유형 하나를 못 만들면 판이 통째로 끝난다.

        **고쳐진 결함이다. 회귀 방지용이다**(session._make). 문장 유형은 못 만들면
        단어 문제로 떨어지는데, 단어 유형은 그 자리에서 None 을 돌려준다.
        그러면 _issue 가 None 이 되어 마감 전인데도 판이 닫힌다.

        시드 566개는 전부 설명이 있어 지금 데이터로는 안 터진다. Admin 에서
        설명 없이 단어를 넣거나, 최근 40개가 설명 있는 후보를 다 먹으면
        그때 사용자는 "왜 30초 만에 끝났지" 를 보게 된다.
        """
        Word.objects.bulk_create(
            [
                Word(
                    term=f"w{i}",
                    meaning=f"뜻{i}",
                    description="",
                    category="git",
                    is_reviewed=True,
                )
                for i in range(12)
            ]
        )

        with forced_kind(quiz.QuizKind.MEANING):
            token, question = session.start()

        with forced_kind(quiz.QuizKind.DESCRIPTION):
            token, _, nxt = session.answer(token, question["choices"][0]["id"])

        self.assertIsNotNone(nxt, "설명 문제를 못 만들면 판이 그대로 끝난다")

    def test_blank_does_not_leave_a_derived_form_of_the_answer(self):
        """정답의 파생어가 지문에 남으면 답이 그대로 보인다.

        **고쳐진 결함이다. 회귀 방지용이다**(quiz._blank_out). 낱말 경계로 정확히
        일치하는 자리만 가려서 commit 을 가려도 commits 가 남는다.
        같은 파일의 _mask_term 은 이미 \\w* 로 파생어까지 가린다.

        시드 380개 중 5개가 그렇다:
            "____.decoder.JSONDecodeError: ..."      (정답 JSON)
            "IndexError: list ____ out of range"     (정답 index)
            "RecursionError: maximum ____ depth ..." (정답 recursion)
            "Rendered more hooks than ... ____."     (정답 render)
            "... multiple leaf nodes in the ____ graph" (정답 migration)
        """
        Word.objects.bulk_create(
            [
                Word(
                    term=f"zz{i}",
                    meaning=f"뜻{i}",
                    description=f"설명{i}",
                    category="git",
                    is_reviewed=True,
                )
                for i in range(8)
            ]
        )
        Word.objects.create(
            term="commit",
            meaning="반영",
            description="설명",
            category="git",
            is_reviewed=True,
        )
        Sentence.objects.create(
            text="Please commit your commits before the review.",
            translation="해석",
            context="상황",
            kind="phrase",
            category="git",
            is_reviewed=True,
        )

        question = quiz.make_blank_question(
            Sentence.objects.visible(), Word.objects.visible()
        )

        self.assertIsNotNone(question)
        self.assertNotIn("commit", question.prompt.lower(), question.prompt)
