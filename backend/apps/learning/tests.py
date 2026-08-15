"""학습 기록 테스트.

지키려는 것은 셋이다.

    - 하루 상한: 몇 판을 하든 그날 점수는 가장 잘한 한 판이다
    - 시간을 서버가 잰다: 클라이언트가 보낸 값으로는 점수를 못 바꾼다
    - 판은 한 번만 기록된다: 끝낸 토큰을 다시 보내도 소용없다

이 셋이 무너지면 순위표가 의미를 잃는다.
"""

from __future__ import annotations

import json
import secrets
from collections import Counter
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import calendar_kst, record, session
from .models import DailyScore, QuizAnswer, QuizSession, RoundStep, SessionKind

User = get_user_model()

START_URL = "/api/learning/rounds/"
ANSWER_URL = "/api/learning/rounds/answer/"
FINISH_URL = "/api/learning/rounds/finish/"

# 테스트 사용자를 만들 때 쓰는 비밀번호. 매번 새로 만든다.
#
# 고정 문자열로 두지 않는 이유: 값 자체는 아무 데서도 비교하지 않아
# 무엇이든 상관없는데, 리터럴로 두면 비밀값 탐지기(GitGuardian)가
# 하드코딩된 비밀번호로 보고 PR 을 막는다. 진짜 비밀값과 구분할 방법이
# 탐지기 쪽에 없으니, 애초에 리터럴을 두지 않는 편이 낫다.
PASSWORD = secrets.token_urlsafe(16)


def make_words(count: int = 12) -> None:
    """문제를 낼 수 있을 만큼 단어를 만든다.

    보기가 넷이라 최소 4개는 있어야 하고, 분류가 같은 것끼리 오답을
    뽑으므로 넉넉히 만든다.
    """
    Word.objects.bulk_create(
        [
            Word(
                term=f"term{i}",
                meaning=f"뜻{i}",
                description=f"설명{i}",
                category="git",
                is_reviewed=True,
            )
            for i in range(count)
        ]
    )


class CalendarTest(TestCase):
    """하루와 주의 경계. 여기가 틀리면 출석과 순위표가 하루씩 밀린다."""

    def test_late_evening_in_korea_is_still_today(self):
        """UTC 로 세면 밤 9시 학습이 다음 날로 넘어가 스트릭이 끊긴다."""
        # UTC 12:00 = KST 21:00 (같은 날)
        moment = datetime(2026, 8, 14, 12, 0, tzinfo=ZoneInfo("UTC"))

        self.assertEqual(calendar_kst.day_of(moment), datetime(2026, 8, 14).date())

    def test_midnight_in_korea_is_the_next_day(self):
        """UTC 15:00 = KST 다음날 00:00."""
        moment = datetime(2026, 8, 14, 15, 0, tzinfo=ZoneInfo("UTC"))

        self.assertEqual(calendar_kst.day_of(moment), datetime(2026, 8, 15).date())

    def test_week_starts_on_monday(self):
        """일요일에 한 것이 다음 주로 넘어가면 주간 순위가 갈린다."""
        sunday = datetime(2026, 8, 16).date()
        monday = datetime(2026, 8, 10).date()

        self.assertEqual(calendar_kst.week_start(sunday), monday)
        self.assertEqual(calendar_kst.week_start(monday), monday)


class ScoringTest(TestCase):
    """+1 / 0 / -1 규칙."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def _play_one(self, correct: bool, late: bool):
        """문제 하나를 풀고 결과를 돌려준다.

        정답은 판 상태에서 직접 읽는다. 예전에는 보기를 하나씩 보내며
        찾았는데, 그게 바로 되돌리기 공격이라 지금은 막혀 있다([ReplayTest]).
        """
        token, question = session.start()

        _, answer_id = quiz.resolve_answer(session._load(token)["q"], -1)
        wrong_id = next(
            c["id"] for c in question["choices"] if c["id"] != answer_id
        )

        picked = answer_id if correct else wrong_id

        if late:
            # 제한 시간을 넘긴 뒤에 답한 상황. 시계를 앞으로 돌린다.
            later = timezone.now() + timedelta(seconds=30)
            with mock.patch.object(timezone, "now", return_value=later):
                _, result, _ = session.answer(token, picked)
        else:
            _, result, _ = session.answer(token, picked)

        return result

    def test_correct_in_time_scores_one(self):
        result = self._play_one(correct=True, late=False)

        self.assertTrue(result.correct)
        self.assertTrue(result.in_time)
        self.assertEqual(result.score, 1)

    def test_correct_but_late_scores_nothing(self):
        """맞혔으니 벌은 없다. 다만 점수도 없다."""
        result = self._play_one(correct=True, late=True)

        self.assertTrue(result.correct)
        self.assertFalse(result.in_time)
        self.assertEqual(result.score, 0)

    def test_wrong_costs_a_point(self):
        """찍으면 손해여야 한다. 이것 때문에 마이너스가 나온다."""
        result = self._play_one(correct=False, late=False)

        self.assertFalse(result.correct)
        self.assertEqual(result.score, -1)

    def test_wrong_costs_a_point_even_when_late(self):
        result = self._play_one(correct=False, late=True)

        self.assertEqual(result.score, -1)

    def test_client_cannot_report_its_own_time(self):
        """걸린 시간은 서버가 잰다.

        클라이언트가 보낸 값을 쓰면 0 을 보내 항상 제한 시간 안이 된다.
        답 요청에 시간을 넣을 자리 자체가 없어야 한다.
        """
        token, question = session.start()

        later = timezone.now() + timedelta(seconds=30)
        with mock.patch.object(timezone, "now", return_value=later):
            _, result, _ = session.answer(token, question["choices"][0]["id"])

        # 30초가 지났으므로 어떤 유형이든 제한 시간 밖이다.
        self.assertFalse(result.in_time)
        self.assertGreaterEqual(result.elapsed_ms, 29_000)


class SkipTest(TestCase):
    """넘기기는 셋. 무제한이면 아무도 마이너스가 안 된다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def test_skip_scores_nothing_and_shows_the_answer(self):
        token, _ = session.start()

        _, result, _ = session.answer(token, None, skip=True)

        self.assertTrue(result.skipped)
        self.assertEqual(result.score, 0)
        # 넘긴 것도 학습이 되어야 하므로 정답은 알려준다.
        self.assertTrue(result.answer_text)

    def test_fourth_skip_is_refused(self):
        token, _ = session.start()

        for _ in range(session.MAX_SKIPS):
            token, _, _ = session.answer(token, None, skip=True)

        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=True)

    def test_answered_counts_the_answer_just_given(self):
        """다음 문제에 실리는 answered 가 방금 푼 답을 세야 한다.

        답을 센 뒤에 문제를 만들지 않으면 화면 숫자가 영구히 하나
        뒤처지고, 마지막 값에도 못 닿는다.
        """
        token, question = session.start()
        self.assertEqual(question["answered"], 0)

        for expected in range(1, 4):
            token, _, question = session.answer(token, None, skip=False)
            self.assertEqual(question["answered"], expected)

        # 끝낼 때 세는 값과도 맞아야 한다.
        self.assertEqual(session.finish(token)["answered"], 3)

    def test_skips_left_is_shown(self):
        token, question = session.start()
        self.assertEqual(question["skips_left"], session.MAX_SKIPS)

        token, _, question = session.answer(token, None, skip=True)

        self.assertEqual(question["skips_left"], session.MAX_SKIPS - 1)


class ReviewGateTest(TestCase):
    """검수 안 된 것은 어디에도 나오면 안 된다.

    이 프로젝트에서 제일 중요한 규칙이다. AI 가 만든 내용을 사람이
    확인하기 전에 보여주면, 영어가 약한 사람이 틀린 것을 그대로 외운다.

    이 클래스가 없으면 `.visible()` 을 `.all()` 로 바꿔도 나머지 테스트가
    전부 통과한다 - 다른 픽스처는 전부 is_reviewed=True 라서다.
    """

    @classmethod
    def setUpTestData(cls):
        make_words()
        # 검수 안 된 것 하나. 기본값이 False 다.
        cls.hidden = Word.objects.create(
            term="leaked-term", meaning="새면 안 되는 뜻", category="git"
        )
        # 미검수 문장은 **문제로 만들어질 수 있는 모양**이어야 한다.
        # 등록된 단어(term0)를 넣지 않으면 빈칸 문제 후보가 안 되고,
        # 상황이 하나뿐이면 상황 문제도 안 만들어진다. 그러면 필터를
        # 지워도 애초에 안 나와서 이 테스트가 아무것도 못 잡는다.
        cls.hidden_sentence = Sentence.objects.create(
            text="leaked term0 sentence text",
            translation="새면 안 되는 해석",
            context="새면 안 되는 상황",
            kind="phrase",
            category="git",
        )
        for i in range(4):
            Sentence.objects.create(
                text=f"leaked term{i} another sentence",
                translation=f"새면 안 되는 해석 {i}",
                context=f"새면 안 되는 상황 {i}",
                kind="phrase",
                category="git",
            )

    def test_unreviewed_never_appears_in_a_question(self):
        """지문에도 보기에도 안 나와야 한다."""
        for _ in range(40):
            token, question = session.start()
            blob = json.dumps(question, ensure_ascii=False)
            self.assertNotIn("leaked", blob)
            self.assertNotIn("새면 안 되는", blob)

    def test_unreviewed_never_appears_as_an_answer(self):
        """채점 뒤 정답을 보여줄 때도 마찬가지다.

        문제를 낸 뒤 검수가 취소되는 경우가 있다. 그때 정답이라고
        알려주면 안 된다.
        """
        text, extra = session._describe(quiz.TARGET_WORD, self.hidden.pk)
        self.assertEqual((text, extra), ("", ""))

        text, extra = session._describe(
            quiz.TARGET_SENTENCE, self.hidden_sentence.pk
        )
        self.assertEqual((text, extra), ("", ""))

    def test_an_unknown_answer_kind_shows_nothing(self):
        """모르는 종류를 단어로 떨어뜨리면 안 된다.

        에러 메시지나 아티클이 붙으면 id 가 같은 엉뚱한 단어가 정답으로
        나온다. 그럴듯해서 한참 모른다.
        """
        word = Word.objects.filter(is_reviewed=True).first()

        text, extra = session._describe("error", word.pk)

        self.assertEqual((text, extra), ("", ""))


class ReplayTest(TestCase):
    """옛 토큰을 다시 보내 점수를 만드는 길이 막혀야 한다.

    서명은 위조를 막을 뿐 되돌리기를 막지 못한다. 옛 토큰도 서명은 멀쩡하다.
    """

    @classmethod
    def setUpTestData(cls):
        make_words()

    def setUp(self):
        cache.clear()

    def _wrong_choice(self, question):
        """정답이 아닌 보기 하나. 답을 미리 알 수 없는 쪽에서 고른다."""
        return question["choices"][0]["id"]

    def test_answer_then_replay_original_token_is_refused(self):
        """답을 캐낸 뒤 원래 토큰으로 되돌리는 것을 막는다.

        1. 아무거나 골라 보낸다 -> 응답이 정답을 알려준다
        2. 원래 토큰 + 알아낸 정답으로 다시 보낸다 -> 제한 시간 안이라 +1
        """
        saved, question = session.start()

        _, first, _ = session.answer(saved, self._wrong_choice(question))

        with self.assertRaises(session.SessionError):
            session.answer(saved, first.answer_id)

    def test_replay_cannot_reset_skips(self):
        """넘기기를 다 쓴 뒤 옛 토큰으로 되돌려 다시 넘길 수 없다."""
        token, _ = session.start()
        before_skips = token

        for _ in range(session.MAX_SKIPS):
            token, _, _ = session.answer(token, None, skip=True)

        with self.assertRaises(session.SessionError):
            session.answer(before_skips, None, skip=True)

    def test_normal_play_is_not_affected(self):
        """정상 진행은 그대로 이어져야 한다."""
        token, _ = session.start()

        for _ in range(5):
            token, result, question = session.answer(token, None, skip=False)
            self.assertIsNotNone(question)

    def test_two_rounds_do_not_block_each_other(self):
        """판이 다르면 순번도 따로다. 남의 판 때문에 막히면 안 된다."""
        first, _ = session.start()
        second, _ = session.start()

        for _ in range(3):
            first, _, _ = session.answer(first, None, skip=False)

        # 두 번째 판은 아직 0번째다. 첫 판이 3번까지 갔다고 막히면 안 된다.
        second, _, question = session.answer(second, None, skip=False)
        self.assertIsNotNone(question)

    def test_a_refused_skip_does_not_kill_the_round(self):
        """거절당한 요청이 판을 죽이면 안 된다.

        검사하면서 순번까지 태우면, 넘기기를 한 번 더 눌러 거절당하는
        순간 토큰은 그대로인데 RoundStep 표에만 순번이 올라가 그 뒤 정상 요청이 전부
        막힌다. 오래된 탭에서 버튼을 한 번 잘못 누른 것만으로 판이
        통째로 날아간다.
        """
        token, question = session.start()

        for _ in range(session.MAX_SKIPS):
            token, _, question = session.answer(token, None, skip=True)

        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=True)

        # 거절 뒤에도 같은 토큰으로 계속 풀 수 있어야 한다.
        token, result, question = session.answer(token, question["choices"][0]["id"])
        self.assertIsNotNone(question)

    def test_a_refused_answer_over_the_cap_does_not_kill_the_round(self):
        """상한 초과로 거절당한 경우도 마찬가지다."""
        token, _ = session.start()
        state = session._load(token)
        state["a"] = [["meaning", "word", 1, 0, 0, 100, 0]] * session.MAX_ANSWERS
        capped = session._sign(state)

        with self.assertRaises(session.SessionError):
            session.answer(capped, None, skip=False)

        # 상한에 안 걸리는 원래 토큰은 여전히 살아 있어야 한다.
        _, _, question = session.answer(token, None, skip=False)
        self.assertIsNotNone(question)

    def test_sending_every_choice_at_once_scores_only_once(self):
        """보기를 전부 동시에 보내도 한 번만 채점돼야 한다.

        get 후 set 은 원자적이지 않아, 같은 토큰으로 보기 넷을 동시에
        보내면 넷 다 통과한다. 그러면 정답을 몰라도 맞은 응답의 토큰만
        남겨 매 문제 +1 을 확정할 수 있다 - 정직하게 푸는 것보다 항상
        이득이라 지배 전략이 된다.

        여기서는 순차로 본다. 진짜 동시 상황은 아래 _take_step 테스트가 본다.
        """
        token, question = session.start()

        picked = [c["id"] for c in question["choices"]]
        self.assertGreaterEqual(len(picked), 2)

        session.answer(token, picked[0])

        # 같은 토큰(같은 순번)으로 다른 보기를 또 보내는 것이 곧 그 공격이다.
        for other in picked[1:]:
            with self.assertRaises(session.SessionError):
                session.answer(token, other)

    def test_cache_pressure_does_not_open_the_door(self):
        """캐시를 아무리 채워도 되돌리기가 뚫리면 안 된다.

        한때 이 방어가 캐시에 있었다. 캐시는 항목이 넘치면 스스로 지우므로
        (cull), 답하기를 반복해 자기 판의 표시를 밀어낸 뒤 옛 토큰을 쓰면
        그만이었다. 표로 옮긴 지금은 캐시와 무관해야 한다.
        """
        saved, question = session.start()
        _, first, _ = session.answer(saved, question["choices"][0]["id"])

        cache.clear()  # cull 이 전부 쓸어간 최악의 경우

        with self.assertRaises(session.SessionError):
            session.answer(saved, first.answer_id)

    def _sweep_now(self):
        """확률을 걷어내고 sweep 을 실제로 돌린다.

        _sweep_old_steps 는 50번에 한 번만 일하므로, 그냥 부르면 98%
        확률로 아무것도 안 하고 돌아온다. 그 상태로 검사하면 sweep 이
        완전히 망가져도 테스트가 초록이다.
        """
        with mock.patch.object(session.random, "random", return_value=0.0):
            session._sweep_old_steps()

    def test_sweep_keeps_rows_that_are_still_alive(self):
        """sweep 이 살아 있는 표시를 지우면 안 된다.

        지우면 되돌리기 방어가 그 판에서 열린다.
        """
        token, _ = session.start()
        session.answer(token, None, skip=True)
        self.assertEqual(RoundStep.objects.count(), 1)

        self._sweep_now()

        self.assertEqual(RoundStep.objects.count(), 1)

    def test_sweep_removes_rows_past_their_life(self):
        """수명이 다한 표시는 지워야 한다. 안 지우면 표가 무한히 자란다."""
        token, _ = session.start()
        session.answer(token, None, skip=True)

        # auto_now_add 라 update 로만 나이를 먹일 수 있다.
        old = timezone.now() - timedelta(seconds=session.TOKEN_MAX_AGE + 60)
        RoundStep.objects.update(created_at=old)

        self._sweep_now()

        self.assertEqual(RoundStep.objects.count(), 0)

    def test_two_requests_cannot_take_the_same_step(self):
        """같은 순번을 두 요청이 나눠 가질 수 없어야 한다.

        이것이 위 공격의 핵심이다. 동시에 들어온 요청들은 **같은 상태를
        읽는다** - 읽고 나서 쓰는 방식이면 전부 통과해버린다. 그 상황을
        상태를 두 번 읽는 것으로 재현한다.
        """
        token, _ = session.start()
        first = session._load(token)
        second = session._load(token)  # 동시에 들어온 다른 요청이 읽은 같은 상태

        session._take_step(first)

        with self.assertRaises(session.SessionError):
            session._take_step(second)

    def test_finish_cannot_pick_the_best_moment(self):
        """가장 좋았던 시점의 토큰으로 끝낼 수 없어야 한다.

        판 식별자의 유일 제약은 같은 판을 두 번 남기는 것만 막는다.
        매 응답의 토큰을 모아뒀다가 점수가 높았던 시점 것으로 끝내면
        뒤에 틀린 -1 들이 없던 일이 되고, 오답 감점이 선택 사항이 된다.
        """
        token, question = session.start()

        _, answer_id = quiz.resolve_answer(session._load(token)["q"], -1)
        token, first, question = session.answer(token, answer_id)
        self.assertEqual(first.score, 1)
        good_moment = token

        # 그 뒤로 한 문제 더 푼다.
        token, _, _ = session.answer(token, question["choices"][0]["id"])

        with self.assertRaises(session.SessionError):
            session.finish(good_moment)

        # 최신 토큰으로는 정상적으로 끝난다.
        self.assertEqual(session.finish(token)["answered"], 2)

    def test_answer_count_is_capped(self):
        """한 판의 답 개수에 상한이 있다. 토큰이 무한정 길어지면 안 된다."""
        token, _ = session.start()
        state = session._load(token)
        state["a"] = [["meaning", "word", 1, 0, 0, 100, 0]] * session.MAX_ANSWERS
        token = session._sign(state)

        with self.assertRaises(session.SessionError):
            session.answer(token, None, skip=False)


class RoundEndTest(TestCase):
    """90초. 클라이언트가 늘릴 수 없어야 한다."""

    @classmethod
    def setUpTestData(cls):
        make_words()

    def test_no_new_question_after_the_deadline(self):
        token, question = session.start()

        later = timezone.now() + timedelta(seconds=session.ROUND_SECONDS + 1)
        with mock.patch.object(timezone, "now", return_value=later):
            _, _, nxt = session.answer(token, question["choices"][0]["id"])

        self.assertIsNone(nxt)

    def test_the_last_answer_still_counts(self):
        """마감 직전에 받은 문제를 마감 직후에 답한 경우.

        버리면 사용자 입장에서 억울하다. 문제를 받은 시각이 마감 전이면
        그 답은 센다.
        """
        token, question = session.start()

        later = timezone.now() + timedelta(seconds=session.ROUND_SECONDS + 1)
        with mock.patch.object(timezone, "now", return_value=later):
            token, _, _ = session.answer(token, question["choices"][0]["id"])

        self.assertEqual(session.finish(token)["answered"], 1)


class RecordTest(TestCase):
    """끝난 판을 남기는 규칙."""

    @classmethod
    def setUpTestData(cls):
        make_words()
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def _summary(self, score: int, token_id: str = "tok", kind: str = SessionKind.FREE):
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

    def test_an_answer_of_the_wrong_shape_does_not_lose_the_round(self):
        """옛 모양의 답이 섞여도 판 자체는 남는다.

        판 상태가 토큰으로 오간다. 답의 칸 수를 늘린 배포 직후에는 옛
        모양의 토큰이 토큰 유효 시간만큼 들어오는데, 그때 500 이 나면 안 된다.
        """
        summary = self._summary(2)
        summary["answers"] = [
            ["meaning", "word", 1, 1, 0, 500, 1],
            ["meaning", "word", 1, 1, 0],  # 칸이 모자란 옛 모양
            ["meaning", "word", "여기에 숫자가 아닌 것", 1, 0, 500, 1],
            ["meaning", "word", 2, 0, 0, 700, -1],
        ]

        saved = record.save_round(self.user, summary)

        self.assertIsNotNone(saved)
        # 멀쩡한 두 줄만 남는다. 판 점수는 요약에서 온 값 그대로다.
        self.assertEqual(QuizAnswer.objects.filter(session=saved).count(), 2)
        self.assertEqual(saved.score, 2)

    def test_only_the_best_round_of_the_day_counts(self):
        """이것이 하루 상한이다.

        판을 전부 더하면 90초짜리를 네 시간 돌린 사람이 한 달 꾸준한
        사람을 하루 만에 앞지른다.
        """
        record.save_round(self.user, self._summary(5, "a"))
        record.save_round(self.user, self._summary(12, "b"))
        record.save_round(self.user, self._summary(3, "c"))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.best_free_score, 12)
        self.assertEqual(row.total, 12)
        # 판 자체는 셋 다 남는다. 기록과 점수는 다른 이야기다.
        self.assertEqual(QuizSession.objects.count(), 3)

    def test_a_negative_first_round_is_kept_as_is(self):
        """0 으로 시작하면 마이너스만 낸 날이 안 한 날과 구분되지 않는다."""
        record.save_round(self.user, self._summary(-4, "a"))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.best_free_score, -4)

    def test_a_bad_day_does_not_eat_the_streak_score(self):
        """하루 점수는 0 밑으로 내려가지 않는다.

        그대로 더하면 열심히 한 날 누적이 줄어든다.
        """
        record.save_round(self.user, self._summary(-4, "a"))

        self.assertEqual(DailyScore.objects.get(user=self.user).total, 0)

    def test_the_same_round_is_recorded_once(self):
        """판 상태가 토큰으로 오가서 끝낸 토큰을 다시 보낼 수 있다."""
        first = record.save_round(self.user, self._summary(7, "same"))
        again = record.save_round(self.user, self._summary(7, "same"))

        self.assertIsNotNone(first)
        self.assertIsNone(again)
        self.assertEqual(QuizSession.objects.count(), 1)

    def test_daily_study_adds_on_top(self):
        """일일공부는 하루 한 번이라 최고를 고를 것이 없고 그대로 쌓인다."""
        record.save_round(self.user, self._summary(6, "free"))
        record.save_round(self.user, self._summary(28, "daily", SessionKind.DAILY))

        row = DailyScore.objects.get(user=self.user)
        self.assertEqual(row.best_free_score, 6)
        self.assertEqual(row.daily_study_score, 28)
        self.assertEqual(row.total, 34)

    def test_answers_are_kept(self):
        """틀린 문제 다시풀기가 이 표에서 나온다."""
        record.save_round(self.user, self._summary(1, "a"))

        self.assertEqual(QuizAnswer.objects.count(), 1)


class RoundApiTest(TestCase):
    """API 로 한 판을 도는 흐름."""

    @classmethod
    def setUpTestData(cls):
        make_words()
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)
        cls.token = Token.objects.create(user=cls.user)

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def start(self, **extra):
        return self.client.post(START_URL, {}, content_type="application/json", **extra)

    def test_anyone_can_start_a_round(self):
        res = self.start()

        self.assertEqual(res.status_code, 201)
        self.assertIn("token", res.json())
        self.assertIn("question", res.json())

    def test_the_answer_is_not_in_the_question(self):
        """정답이 응답에 실리면 개발자도구로 미리 볼 수 있다."""
        body = self.start().json()

        self.assertNotIn("answer_id", body["question"])
        self.assertNotIn("answer_id", json_of(body))

    def test_a_guest_round_is_not_recorded(self):
        started = self.start().json()
        token = started["token"]
        answered = self.client.post(
            ANSWER_URL,
            {"token": token, "choice_id": started["question"]["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        res = self.client.post(
            FINISH_URL,
            {"token": answered["token"]},
            content_type="application/json",
        )

        self.assertTrue(res.json()["guest"])
        self.assertFalse(res.json()["recorded"])
        self.assertEqual(QuizSession.objects.count(), 0)

    def test_a_logged_in_round_is_recorded(self):
        started = self.start(**self.auth()).json()
        answered = self.client.post(
            ANSWER_URL,
            {"token": started["token"], "choice_id": started["question"]["choices"][0]["id"]},
            content_type="application/json",
            **self.auth(),
        ).json()

        res = self.client.post(
            FINISH_URL,
            {"token": answered["token"]},
            content_type="application/json",
            **self.auth(),
        )

        self.assertTrue(res.json()["recorded"])
        self.assertEqual(QuizSession.objects.count(), 1)

    def test_an_empty_round_is_not_recorded(self):
        """열고 바로 닫기를 반복해 행만 쌓는 것을 막는다."""
        started = self.start(**self.auth()).json()

        res = self.client.post(
            FINISH_URL,
            {"token": started["token"]},
            content_type="application/json",
            **self.auth(),
        )

        self.assertFalse(res.json()["recorded"])
        self.assertEqual(QuizSession.objects.count(), 0)

    def test_a_forged_token_is_refused(self):
        res = self.client.post(
            ANSWER_URL,
            {"token": "위조된-토큰", "choice_id": 1},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_true_is_not_taken_as_a_choice(self):
        """bool 은 int 의 하위라 True 가 1 번 보기로 통과할 수 있다."""
        started = self.start().json()

        res = self.client.post(
            ANSWER_URL,
            {"token": started["token"], "choice_id": True},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)


class FallbackDistributionTest(TestCase):
    """폴백이 돌아도 유형이 한쪽으로 쏠리면 안 된다.

    문장이 없는 DB(단어만 시드하고 문장은 아직 안 넣은 상태)에서는 문장
    유형이 항상 단어 유형으로 떨어진다. 그때 고정 순서로 훑으면 첫 후보가
    거의 항상 성공해서 그 유형 하나로 몰린다. 같은 유형이 이어지면
    답이 아니라 패턴을 외우게 된다.
    """

    @classmethod
    def setUpTestData(cls):
        make_words(12)  # 문장은 일부러 안 만든다

    def test_fallback_spreads_across_word_kinds(self):
        kinds = Counter()
        for _ in range(300):
            _, question = session.start()
            kinds[question["kind"]] += 1

        self.assertEqual(
            set(kinds), set(quiz.QuizKind.WORD_KINDS), f"유형이 다 안 나옴: {dict(kinds)}"
        )
        self.assertLess(
            max(kinds.values()) / 300, 0.5, f"한쪽으로 쏠림: {dict(kinds)}"
        )


class SentenceQuestionTest(TestCase):
    """문장 문제. 시간제 판에 들어갈 수 있는 모양이어야 한다."""

    @classmethod
    def setUpTestData(cls):
        make_words()
        Word.objects.create(
            term="rebase", meaning="옮겨 붙이기", category="git", is_reviewed=True
        )
        # 상황을 일부러 겹치게 만든다. 전부 다르면 "같은 상황을 보기에
        # 두 번 넣지 않는다" 는 규칙이 검사되지 않는다 - 코드에서 그 줄을
        # 통째로 지워도 테스트가 통과한다.
        #
        # 그렇다고 두 종류로 두면 안 된다. 보기가 넷이라 서로 다른 상황이
        # 최소 넷은 있어야 문제를 만들 수 있다. 겹치기도 하고 넷도 되게
        # 여섯 문장을 4종류로 나눈다(2, 2, 1, 1).
        contexts = ["상황 A", "상황 A", "상황 B", "상황 B", "상황 C", "상황 D"]
        for i, context in enumerate(contexts):
            Sentence.objects.create(
                text=f"Could you rebase this onto main? {i}",
                translation=f"해석 {i}",
                context=context,
                kind="phrase",
                category="git",
                is_reviewed=True,
            )

    def test_blank_hides_the_answer_in_the_sentence(self):
        question = quiz.make_blank_question(
            Sentence.objects.visible(), Word.objects.visible()
        )

        self.assertIsNotNone(question)
        self.assertIn(quiz.BLANK_MARK, question.prompt)
        # 정답이 지문에 그대로 남아 있으면 문제가 아니다.
        self.assertNotIn("rebase", question.prompt.lower())

    def test_situation_choices_are_all_different(self):
        """같은 상황 글자를 쓰는 문장이 있다. 보기 둘이 같으면 답이 둘이다."""
        made = 0
        for _ in range(10):
            question = quiz.make_situation_question(Sentence.objects.visible())
            if question is None:
                continue
            made += 1
            texts = [c.text for c in question.choices]
            self.assertEqual(len(texts), len(set(texts)))

        # 하나도 못 만들면 위 단언이 한 번도 안 돈다. 그 상태로 통과하면
        # 생성이 완전히 망가져도 초록이다.
        self.assertGreater(made, 0)

    def test_sentence_questions_get_more_time(self):
        """단어 3초로는 영어 문장을 읽을 수 없다.

        표만 비교하면 안 된다 - 표가 맞아도 문제에 그 값이 안 실리면
        화면은 3초를 쓴다. 실제로 만든 문제에서 확인한다.
        """
        blank = quiz.make_blank_question(
            Sentence.objects.visible(), Word.objects.visible()
        )
        word = quiz.make_question(Word.objects.visible(), quiz.QuizKind.MEANING)

        self.assertIsNotNone(blank)
        self.assertIsNotNone(word)
        self.assertGreater(blank.time_limit_ms, word.time_limit_ms)
        self.assertEqual(blank.time_limit_ms, quiz.TIME_LIMITS_MS[quiz.QuizKind.BLANK])


def json_of(body) -> str:

    return json.dumps(body, ensure_ascii=False)
