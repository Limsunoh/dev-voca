"""낱개 연습(단어·문장 채점)이 오답 노트를 고치는 경로를 깨뜨려 본다.

계약은 넷이다.

1. 게스트는 어떤 표에도 쓰지 않는다.
2. 로그인 + 틀림은 줄을 넣는다(is_wrong=True, streak=0).
3. 로그인 + 맞힘은 이미 틀린 줄만 내린다. 줄이 없거나 틀린 줄이 아니면
   아무것도 쓰지 않는다.
4. 채점이 200 이 아니면(잘못된 토큰, 검수 취소, 인증 실패) 쓰지 않는다.

연습 채점은 로그인 없이 열린 POST 이고 토큰을 몇 번이든 다시 낼 수 있어,
"누구의 줄을 어떤 조건에서 고치나" 가 이 파일이 지키는 전부다.
"""

from __future__ import annotations

import json
import threading
import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.core import signing
from django.core.cache import cache
from django.db import connection
from django.db.models.query import QuerySet
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.learning import daily_study, review
from apps.learning.models import DailyScore, QuizAnswer, QuizSession, ReviewState
from apps.learning.session import SessionError
from apps.learning.tests_daily_study_edge import _KeepsCacheTable
from apps.learning.tests_mistakes import make_sentence, make_user, make_word, mark
from apps.learning.tests_review import seed_words
from apps.learning.tests_review_race import _run_threads

from . import quiz
from .models import Sentence, Word
from .quiz import TARGET_SENTENCE, TARGET_WORD, sign_question

WORD_GRADE = "/api/vocab/words/grade/"
SENTENCE_GRADE = "/api/vocab/sentences/grade/"
MISTAKES = "/api/learning/mistakes/"


def question_token(target, others, answer_type: str = TARGET_WORD) -> str:
    """target 이 정답이고 others 가 나머지 보기인 문제 토큰."""
    return sign_question(target.pk, [target.pk, *(o.pk for o in others)], answer_type)


class PracticeCase(TestCase):
    """공통 셋업. 정답 단어 하나와 오답 셋, 로그인한 사람 한 명."""

    def setUp(self):
        cache.clear()
        self.user = make_user("연습")
        self.key = Token.objects.create(user=self.user).key
        self.word = make_word()
        self.others = [make_word() for _ in range(3)]
        self.token = question_token(self.word, self.others)
        self.wrong_pick = self.others[0].pk

    def post(self, url, token, picked, *, key=None):
        headers = {"HTTP_AUTHORIZATION": f"Token {key}"} if key else {}
        return self.client.post(
            url,
            {"token": token, "picked": picked},
            content_type="application/json",
            **headers,
        )

    def grade(self, picked, *, key="me", token=None, url=WORD_GRADE):
        """기본은 self.user 의 토큰으로 self.word 문제를 채점한다."""
        key = self.key if key == "me" else key
        return self.post(url, token or self.token, picked, key=key)

    def row(self, target=None, user=None) -> ReviewState | None:
        target = target or self.word
        return ReviewState.objects.filter(
            user=user or self.user,
            target_type="word" if isinstance(target, Word) else "sentence",
            target_id=target.pk,
        ).first()

    def assertNoRows(self):
        self.assertEqual(ReviewState.objects.count(), 0)

    @contextmanager
    def assertWritesNothing(self):
        """요청이 어느 표에도 INSERT·UPDATE·DELETE 를 안 낸다."""
        with CaptureQueriesContext(connection) as ctx:
            yield
        writes = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(writes, [])


class GuestTest(PracticeCase):
    """게스트 채점은 전과 같이 조회다."""

    def test_guest_writes_nothing_either_way(self):
        for picked, correct in ((self.wrong_pick, False), (self.word.pk, True)):
            with self.subTest(correct=correct), self.assertWritesNothing():
                res = self.grade(picked, key=None)
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["correct"], correct)
        self.assertNoRows()

    def test_guest_on_sentence_grade_writes_nothing(self):
        sentence = make_sentence()
        others = [make_sentence() for _ in range(3)]
        token = question_token(sentence, others, TARGET_SENTENCE)

        with self.assertWritesNothing():
            res = self.grade(others[0].pk, key=None, token=token, url=SENTENCE_GRADE)

        self.assertEqual(res.status_code, 200)
        self.assertNoRows()


class LoggedInRuleTest(PracticeCase):
    """줄을 넣고 내리는 규칙."""

    def test_wrong_inserts_a_row(self):
        res = self.grade(self.wrong_pick)

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["correct"])
        row = self.row()
        self.assertTrue(row.is_wrong)
        self.assertEqual(row.streak, 0)
        self.assertIsNone(row.last_correct_at)
        self.assertEqual(ReviewState.objects.count(), 1, "오답 보기에는 줄이 안 생긴다")

    def test_first_correct_writes_nothing(self):
        """처음 맞힌 항목에 줄이 생기면 7일 뒤 복습 목록이 는다."""
        with self.assertWritesNothing():
            res = self.grade(self.word.pk)

        self.assertTrue(res.json()["correct"])
        self.assertNoRows()

    def test_correct_on_a_row_that_is_not_wrong_changes_nothing(self):
        """오래된 맞힌 줄을 새 시각으로 고치면 복습의 "오래된 것" 에서 빠진다."""
        long_ago = timezone.now() - timedelta(days=30)
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            is_wrong=False,
            streak=1,
            last_correct_at=long_ago,
        )

        with self.assertWritesNothing():
            self.grade(self.word.pk)

        row = self.row()
        self.assertEqual(row.last_correct_at, long_ago)
        self.assertEqual(row.streak, 1)

    def test_correct_clears_a_wrong_row_and_keeps_streak(self):
        """연속은 복습에서만 움직인다. 연습 정답이 고치면 졸업 규칙이 깨진다."""
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            is_wrong=True,
            streak=1,
        )

        self.grade(self.word.pk)

        row = self.row()
        self.assertFalse(row.is_wrong)
        self.assertEqual(row.streak, 1)
        self.assertIsNotNone(row.last_correct_at)

    def test_wrong_on_a_known_row_breaks_streak_and_keeps_last_correct(self):
        when = timezone.now() - timedelta(days=2)
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            is_wrong=False,
            streak=2,
            last_correct_at=when,
        )

        self.grade(self.wrong_pick)

        row = self.row()
        self.assertTrue(row.is_wrong)
        self.assertEqual(row.streak, 0)
        self.assertEqual(row.last_correct_at, when)

    def test_practice_touches_no_score_table(self):
        """점수가 걸리지 않는 연습이다. 순위표·기록 표는 그대로여야 한다."""
        self.grade(self.wrong_pick)
        self.grade(self.word.pk)

        self.assertEqual(DailyScore.objects.count(), 0)
        self.assertEqual(QuizSession.objects.count(), 0)
        self.assertEqual(QuizAnswer.objects.count(), 0)

    def test_session_login_records_too(self):
        """Admin 브라우저의 세션 로그인도 같은 사용자로 기록된다."""
        self.client.force_login(self.user)

        self.grade(self.wrong_pick, key=None)

        self.assertTrue(self.row().is_wrong)

    def test_full_cycle_shows_then_hides_in_the_mistakes_list(self):
        """화면 약속: 틀리면 목록에 뜨고, 다시 맞히면 빠진다."""
        self.client.force_login(self.user)

        self.grade(self.wrong_pick)
        rows = self.client.get(MISTAKES).json()["results"]
        self.assertEqual([r["target_id"] for r in rows], [self.word.pk])
        self.assertEqual(rows[0]["target_type"], "word")

        self.grade(self.word.pk)
        self.assertEqual(self.client.get(MISTAKES).json()["results"], [])


class IsolationTest(PracticeCase):
    """다른 사용자의 줄과 섞이지 않는다."""

    def setUp(self):
        super().setUp()
        self.other = make_user("남")

    def test_my_correct_does_not_clear_someone_elses_row(self):
        mark(self.other, self.word, wrong=True)
        mark(self.user, self.word, wrong=True)

        self.grade(self.word.pk)

        self.assertFalse(self.row().is_wrong)
        self.assertTrue(self.row(user=self.other).is_wrong)

    def test_someone_elses_wrong_row_does_not_open_my_correct(self):
        """맞힘 판정이 사용자를 안 거르면 내게 줄이 생긴다."""
        mark(self.other, self.word, wrong=True)

        with self.assertWritesNothing():
            self.grade(self.word.pk)

        self.assertIsNone(self.row())
        self.assertTrue(self.row(user=self.other).is_wrong)

    def test_a_token_issued_to_one_person_writes_only_for_who_sends_it(self):
        """문제 토큰은 사람에 안 묶인다. 쓰는 줄은 보낸 사람의 것이다."""
        other_key = Token.objects.create(user=self.other).key

        self.grade(self.wrong_pick, key=other_key)

        self.assertIsNone(self.row())
        self.assertTrue(self.row(user=self.other).is_wrong)

    def test_mistakes_list_shows_only_my_practice(self):
        self.grade(self.wrong_pick)
        self.client.force_login(self.other)

        self.assertEqual(self.client.get(MISTAKES).json()["results"], [])


class SameNumberDifferentKindTest(PracticeCase):
    """단어 N 번과 문장 N 번은 다른 줄이다. 빈칸 문제의 종류 키도 여기다."""

    def setUp(self):
        super().setUp()
        self.twin_word = Word.objects.create(
            pk=9_000_001, term="twinword", meaning="뜻", description="설명", is_reviewed=True
        )
        self.twin_sentence = Sentence.objects.create(
            pk=9_000_001, text="Twin sentence.", translation="해석", is_reviewed=True
        )

    def test_blank_answer_goes_to_the_word_row_not_the_sentence_row(self):
        """빈칸 문제는 문장을 보여주지만 정답은 단어다. 종류 키는 word."""
        token = question_token(self.twin_word, self.others, TARGET_WORD)

        self.grade(self.others[0].pk, token=token, url=SENTENCE_GRADE)

        self.assertTrue(self.row(self.twin_word).is_wrong)
        self.assertIsNone(self.row(self.twin_sentence))

    def test_situation_answer_goes_to_the_sentence_row(self):
        others = [make_sentence() for _ in range(3)]
        token = question_token(self.twin_sentence, others, TARGET_SENTENCE)

        self.grade(others[0].pk, token=token, url=SENTENCE_GRADE)

        self.assertTrue(self.row(self.twin_sentence).is_wrong)
        self.assertIsNone(self.row(self.twin_word))

    def test_correct_word_does_not_clear_the_sentence_with_the_same_number(self):
        mark(self.user, self.twin_sentence, wrong=True)
        token = question_token(self.twin_word, self.others)

        with self.assertWritesNothing():
            self.grade(self.twin_word.pk, token=token)

        self.assertTrue(self.row(self.twin_sentence).is_wrong)
        self.assertIsNone(self.row(self.twin_word))

    def test_correct_sentence_does_not_clear_the_word_with_the_same_number(self):
        mark(self.user, self.twin_word, wrong=True)
        others = [make_sentence() for _ in range(3)]
        token = question_token(self.twin_sentence, others, TARGET_SENTENCE)

        with self.assertWritesNothing():
            self.grade(self.twin_sentence.pk, token=token, url=SENTENCE_GRADE)

        self.assertTrue(self.row(self.twin_word).is_wrong)

    def test_a_sentence_token_on_the_word_endpoint_is_refused_without_writing(self):
        others = [make_sentence() for _ in range(3)]
        token = question_token(self.twin_sentence, others, TARGET_SENTENCE)

        with self.assertWritesNothing():
            res = self.grade(others[0].pk, token=token, url=WORD_GRADE)

        self.assertEqual(res.status_code, 400)
        self.assertNoRows()


class RealQuestionTest(PracticeCase):
    """토큰을 직접 만들지 않고 실제 출제 응답으로 푼다."""

    def setUp(self):
        super().setUp()
        self.term_word = make_word()
        Word.objects.filter(pk=self.term_word.pk).update(term="rebasing")
        self.sentences = [
            Sentence.objects.create(
                text=f"Please stop rebasing branch {i}.",
                translation=f"해석 {i}",
                context=f"장면 {i} 때",
                is_reviewed=True,
            )
            for i in range(4)
        ]

    def _solve(self, url, query, pick):
        q = self.client.get(url + query, HTTP_AUTHORIZATION=f"Token {self.key}").json()
        choice_ids = [c["id"] for c in q["choices"]]
        return q, self.grade(
            pick(choice_ids), token=q["token"], url=url.replace("quiz", "grade")
        )

    def test_word_question(self):
        q, res = self._solve(
            "/api/vocab/words/quiz/",
            f"?item={self.word.pk}",
            lambda ids: next(i for i in ids if i != self.word.pk),
        )
        self.assertEqual(res.status_code, 200, q)
        self.assertTrue(self.row().is_wrong)

    def test_blank_question_records_the_word(self):
        sentence = self.sentences[0]
        q, res = self._solve(
            "/api/vocab/sentences/quiz/",
            f"?item={sentence.pk}&kind=blank",
            lambda ids: next(i for i in ids if i != self.term_word.pk),
        )
        self.assertEqual(q["kind"], "blank")
        self.assertEqual(res.json()["answer_type"], "word")
        self.assertTrue(self.row(self.term_word).is_wrong)
        self.assertIsNone(self.row(sentence))

    def test_item_without_kind_asks_situation_so_a_right_answer_clears_the_note(self):
        """"이 문장으로 문제 풀기" 가 빈칸으로 나오면 맞혀도 문장이 노트에 남는다."""
        sentence = self.sentences[2]
        mark(self.user, sentence, wrong=True)

        for _ in range(10):
            q, res = self._solve(
                "/api/vocab/sentences/quiz/",
                f"?item={sentence.pk}",
                lambda ids: sentence.pk,
            )
            self.assertEqual(q["kind"], "situation")
            self.assertEqual(res.status_code, 200)

        self.assertFalse(self.row(sentence).is_wrong)

    def test_item_without_context_falls_back_to_blank(self):
        sentence = Sentence.objects.create(
            text="Please stop rebasing now.",
            translation="해석",
            context="",
            is_reviewed=True,
        )
        res = self.client.get(f"/api/vocab/sentences/quiz/?item={sentence.pk}")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["kind"], "blank")

    def test_situation_question_records_the_sentence(self):
        sentence = self.sentences[1]
        q, res = self._solve(
            "/api/vocab/sentences/quiz/",
            f"?item={sentence.pk}&kind=situation",
            lambda ids: next(i for i in ids if i != sentence.pk),
        )
        self.assertEqual(q["kind"], "situation")
        self.assertEqual(res.json()["answer_type"], "sentence")
        self.assertTrue(self.row(sentence).is_wrong)


class ReviewGateTest(PracticeCase):
    """문제를 낸 뒤 검수가 취소된 항목. 정답도 쓰기도 없어야 한다."""

    def _retract(self, target):
        type(target).objects.filter(pk=target.pk).update(is_reviewed=False)

    def test_retracted_word_is_404_and_writes_nothing(self):
        self._retract(self.word)

        for picked in (self.wrong_pick, self.word.pk):
            with self.subTest(picked=picked), self.assertWritesNothing():
                res = self.grade(picked)
                self.assertEqual(res.status_code, 404)
                self.assertNotIn(self.word.meaning, res.content.decode())
        self.assertNoRows()

    def test_retracted_word_cannot_be_cleared_from_the_notes(self):
        """이미 틀린 줄은 그대로 있고 목록에서 가려질 뿐이다."""
        mark(self.user, self.word, wrong=True)
        self._retract(self.word)

        self.grade(self.word.pk)

        self.assertTrue(self.row().is_wrong)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(MISTAKES).json()["results"], [])

    def test_never_reviewed_answer_is_404_and_writes_nothing(self):
        hidden = make_word(reviewed=False)
        token = question_token(hidden, self.others)

        with self.assertWritesNothing():
            res = self.grade(self.others[0].pk, token=token)

        self.assertEqual(res.status_code, 404)
        self.assertNoRows()

    def test_retracted_sentence_is_404_and_writes_nothing(self):
        sentence = make_sentence()
        others = [make_sentence() for _ in range(3)]
        token = question_token(sentence, others, TARGET_SENTENCE)
        self._retract(sentence)

        with self.assertWritesNothing():
            res = self.grade(others[0].pk, token=token, url=SENTENCE_GRADE)

        self.assertEqual(res.status_code, 404)
        self.assertNotIn(sentence.translation, res.content.decode())
        self.assertNoRows()

    def test_retracted_blank_answer_on_sentence_endpoint_is_404(self):
        """빈칸 정답(단어)의 검수가 취소된 경우. 종류가 word 라도 같은 게이트다."""
        self._retract(self.word)

        with self.assertWritesNothing():
            res = self.grade(self.wrong_pick, url=SENTENCE_GRADE)

        self.assertEqual(res.status_code, 404)

    def test_deleted_word_is_404_and_writes_nothing(self):
        Word.objects.filter(pk=self.word.pk).delete()

        res = self.grade(self.wrong_pick)

        self.assertEqual(res.status_code, 404)
        self.assertNoRows()

    def test_staff_gets_no_exception_from_the_gate(self):
        """can_review 사용자도 채점 게이트는 같다."""
        staff = make_user("검수자")
        staff.is_staff = True
        staff.is_superuser = True
        staff.save()
        key = Token.objects.create(user=staff).key
        self._retract(self.word)

        res = self.grade(self.wrong_pick, key=key)

        self.assertEqual(res.status_code, 404)
        self.assertNoRows()

    def test_picking_a_retracted_distractor_records_only_the_answer(self):
        self._retract(self.others[0])

        self.grade(self.others[0].pk)

        self.assertTrue(self.row().is_wrong)
        self.assertIsNone(self.row(self.others[0]))


class BadInputTest(PracticeCase):
    """400 이고 500 이 아니며 쓰지 않는다."""

    def test_bad_bodies(self):
        for raw in ("[]", '"x"', "1", "null", "{"):
            for url in (WORD_GRADE, SENTENCE_GRADE):
                with self.subTest(raw=raw, url=url):
                    res = self.client.post(
                        url,
                        raw,
                        content_type="application/json",
                        HTTP_AUTHORIZATION=f"Token {self.key}",
                    )
                    self.assertEqual(res.status_code, 400)
        self.assertNoRows()

    def test_bad_tokens(self):
        other_salt = signing.dumps({"a": "x"}, salt="learning.review")
        legacy = signing.dumps(
            {"a": "x", "n": "y", "c": [self.word.pk]}, salt="vocab.quiz.answer"
        )
        unknown_kind = sign_question(self.word.pk, [self.word.pk], "phrase")
        for token in (
            "",
            "   ",
            "x" * 100_000,
            "한글",
            123,
            None,
            True,
            ["a"],
            {"a": 1},
            self.token + "x",
            self.token[:-1],
            other_salt,
            legacy,
            unknown_kind,
        ):
            for url in (WORD_GRADE, SENTENCE_GRADE):
                with self.subTest(token=str(token)[:20], url=url), self.assertWritesNothing():
                    res = self.post(url, token, self.word.pk, key=self.key)
                    self.assertEqual(res.status_code, 400)
        self.assertNoRows()

    def test_expired_token_is_refused_without_writing(self):
        with mock.patch.object(quiz, "TOKEN_MAX_AGE", -1), self.assertWritesNothing():
            res = self.grade(self.wrong_pick)

        self.assertEqual(res.status_code, 400)
        self.assertNoRows()

    def test_out_of_range_answer_ids_are_404(self):
        """서명된 토큰에 범위를 넘는 id 가 있어도 500 이 아니다."""
        for answer_id in (10**30, -1, 0):
            token = sign_question(answer_id, [answer_id, 2, 3, 4])
            with self.subTest(answer_id=answer_id):
                res = self.grade(2, token=token)
                self.assertEqual(res.status_code, 404)
        self.assertNoRows()

    def test_unusable_picks_grade_as_wrong_not_as_a_crash(self):
        """정수가 아닌 값은 기존 규칙대로 오답이다. 정답 pk 문자열도 정답이 아니다."""
        for picked in (str(self.word.pk), 1.5, None, True, [self.word.pk], {}, -1, 2**70):
            word = make_word()
            token = question_token(word, self.others)
            with self.subTest(picked=picked):
                res = self.grade(picked, token=token)
                self.assertEqual(res.status_code, 200)
                self.assertFalse(res.json()["correct"])
                self.assertTrue(self.row(word).is_wrong)

    def test_missing_pick_is_wrong_too(self):
        res = self.client.post(
            WORD_GRADE,
            json.dumps({"token": self.token}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.key}",
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["correct"])

    def test_get_is_not_allowed_and_writes_nothing(self):
        res = self.client.get(WORD_GRADE, HTTP_AUTHORIZATION=f"Token {self.key}")

        self.assertEqual(res.status_code, 405)
        self.assertNoRows()


class AccountStateTest(PracticeCase):
    """정지·로그아웃·위조 인증. 쓰기 전에 걸려야 한다."""

    def test_suspended_token_is_401_and_writes_nothing(self):
        mark(self.user, self.word, wrong=True)
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)

        for picked in (self.wrong_pick, self.word.pk):
            with self.subTest(picked=picked), self.assertWritesNothing():
                self.assertEqual(self.grade(picked).status_code, 401)
        self.assertTrue(self.row().is_wrong)
        self.assertEqual(ReviewState.objects.count(), 1)

    def test_suspended_session_is_treated_as_a_guest(self):
        self.client.force_login(self.user)
        type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)

        with self.assertWritesNothing():
            res = self.grade(self.wrong_pick, key=None)

        self.assertEqual(res.status_code, 200)
        self.assertNoRows()

    def test_a_token_after_logout_is_401(self):
        Token.objects.filter(key=self.key).delete()

        self.assertEqual(self.grade(self.wrong_pick).status_code, 401)
        self.assertNoRows()

    def test_malformed_authorization_is_401(self):
        # 실제 WSGI 서버는 헤더 바이트를 latin-1 로 풀어 넘긴다. 테스트 클라이언트는
        # 그 변환이 없어, 한글을 그대로 주면 서버에 없는 모양의 문자열이 된다.
        non_ascii = "Token 없는토큰".encode().decode("latin-1")
        for header in ("Token", "Token a b", non_ascii, "Token " + "9" * 500):
            with self.subTest(header=header[:16]):
                res = self.client.post(
                    WORD_GRADE,
                    {"token": self.token, "picked": self.wrong_pick},
                    content_type="application/json",
                    HTTP_AUTHORIZATION=header,
                )
                self.assertEqual(res.status_code, 401)
        self.assertNoRows()

    def test_session_post_without_csrf_cannot_write(self):
        """세션으로 쓸 수 있게 됐으니 교차 사이트 POST 가 막혀 있어야 한다."""
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        res = client.post(
            WORD_GRADE, {"token": self.token, "picked": self.wrong_pick}, format="json"
        )

        self.assertEqual(res.status_code, 403)
        self.assertNoRows()


class TokenReuseTest(PracticeCase):
    """문제 토큰은 유효 시간 안에 몇 번이든 낼 수 있다."""

    def test_replayed_wrong_leaves_one_row(self):
        for _ in range(3):
            self.assertEqual(self.grade(self.wrong_pick).status_code, 200)

        self.assertEqual(ReviewState.objects.count(), 1)
        self.assertTrue(self.row().is_wrong)

    def test_replayed_correct_on_a_fresh_word_never_creates_a_row(self):
        for _ in range(3):
            self.grade(self.word.pk)

        self.assertNoRows()

    def test_last_answer_wins_on_replay(self):
        """같은 토큰으로 오답 뒤 정답, 정답 뒤 오답. 마지막 결과가 남는다."""
        self.grade(self.wrong_pick)
        self.grade(self.word.pk)
        self.assertFalse(self.row().is_wrong)

        self.grade(self.wrong_pick)
        self.assertTrue(self.row().is_wrong)

    def test_replay_cannot_raise_the_review_streak(self):
        """맞힌 토큰을 반복해도 복습 연속은 안 오른다. 졸업은 복습에서만 한다."""
        mark(self.user, self.word, wrong=True)

        for _ in range(5):
            self.grade(self.word.pk)

        self.assertEqual(self.row().streak, 0)


class DownstreamListsTest(PracticeCase):
    """복습과 일일공부 출제에 미치는 영향."""

    def setUp(self):
        super().setUp()
        seed_words(10)

    def test_wrong_practice_appears_in_review(self):
        self.grade(self.wrong_pick)

        self.assertEqual([r.target_id for r in review.due_of(self.user)], [self.word.pk])

    def test_first_correct_never_enters_review_even_later(self):
        self.grade(self.word.pk)

        with mock.patch(
            "apps.learning.review.timezone.now",
            return_value=timezone.now() + timedelta(days=30),
        ):
            self.assertEqual(review.count_due(self.user), 0)

    def test_correct_after_wrong_leaves_review_until_it_is_stale(self):
        self.grade(self.wrong_pick)
        self.grade(self.word.pk)
        self.assertEqual(review.count_due(self.user), 0)

        ReviewState.objects.filter(user=self.user).update(
            last_correct_at=timezone.now() - timedelta(days=review.STALE_DAYS + 1)
        )
        self.assertEqual(review.count_due(self.user), 1)

    def test_practice_correct_does_not_graduate_a_review_in_progress(self):
        """복습에서 한 번 맞힌 줄은 연습으로 맞혀도 복습 목록에 남는다."""
        ReviewState.objects.create(
            user=self.user,
            target_type="word",
            target_id=self.word.pk,
            is_wrong=False,
            streak=1,
            last_correct_at=timezone.now(),
        )

        self.grade(self.word.pk)

        self.assertEqual(review.count_due(self.user), 1)

    def test_retracted_word_from_practice_is_not_served_by_review(self):
        self.grade(self.wrong_pick)
        Word.objects.filter(pk=self.word.pk).update(is_reviewed=False)

        with self.assertRaises(SessionError):
            review.start(self.user)

    def _pick(self):
        # 일일공부가 단어를 고르는 규칙(틀린 것 > 안 본 것 > 오래된 것)을 직접 본다.
        # _pick_for_study 는 첫 묶음이면 홈이 미리 뽑아 둔 것을 쓰므로(preview_words)
        # 여기서 보려는 순서를 지나지 않는다. 그래서 홈을 연 뒤 연습에서 틀린
        # 단어는 그날 첫 묶음에는 안 들어오고, 다음 묶음과 다음 날 미리 뽑기부터
        # 앞에 온다. 홈에서 본 단어로 시작하자는 결정(11-12) 그대로다.
        return daily_study._pick_words(self.user.pk, 1, set())

    def test_wrong_practice_is_picked_first_for_daily_study(self):
        self.grade(self.wrong_pick)

        for _ in range(5):
            self.assertEqual(
                [w.pk for w in self._pick()],
                [self.word.pk],
            )

    def test_cleared_word_is_no_longer_first_for_daily_study(self):
        self.grade(self.wrong_pick)
        self.grade(self.word.pk)

        for _ in range(5):
            self.assertNotIn(
                self.word.pk,
                [w.pk for w in self._pick()],
            )

    def test_wrong_sentence_does_not_pull_the_same_numbered_word_into_daily(self):
        Word.objects.create(
            pk=9_000_002, term="twinx", meaning="뜻", description="설명", is_reviewed=True
        )
        twin = Sentence.objects.create(
            pk=9_000_002, text="Twin.", translation="해석", is_reviewed=True
        )
        others = [make_sentence() for _ in range(3)]
        token = question_token(twin, others, TARGET_SENTENCE)
        self.grade(others[0].pk, token=token, url=SENTENCE_GRADE)

        picks = {
            tuple(w.pk for w in self._pick())
            for _ in range(25)
        }

        self.assertGreater(len(picks), 1, "틀린 단어처럼 매번 먼저 뽑혔다")


class MistakesPagingTest(PracticeCase):
    """연습으로 쌓인 목록의 페이지 경계."""

    def setUp(self):
        super().setUp()
        for _ in range(21):
            word = make_word()
            self.grade(self.wrong_pick, token=question_token(word, self.others))
        self.client.force_login(self.user)

    def test_page_boundaries_are_not_500(self):
        for query, expected in (
            ("?page=0", 404),
            ("?page=-1", 404),
            ("?page=abc", 404),
            ("?page=999999", 404),
            (f"?page={'9' * 30}", 404),
            ("?page=2", 200),
        ):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(MISTAKES + query).status_code, expected)

    def test_page_size_cannot_be_inflated(self):
        body = self.client.get(MISTAKES + "?page_size=99999").json()

        self.assertEqual(body["count"], 21)
        self.assertEqual(len(body["results"]), 20)


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class PracticeRaceTest(_KeepsCacheTable, TransactionTestCase):
    """실제 Postgres 연결 둘 이상이 같은 줄을 동시에 고칠 때."""

    def setUp(self):
        cache.clear()
        self.user = make_user("경합")
        self.key = Token.objects.create(user=self.user).key
        self.word = make_word()
        self.others = [make_word() for _ in range(3)]
        self.token = question_token(self.word, self.others)

    def _call(self, picked):
        def run():
            client = Client(raise_request_exception=False)
            return client.post(
                WORD_GRADE,
                {"token": self.token, "picked": picked},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Token {self.key}",
            ).status_code

        return run

    def _assert_all_ok(self, results):
        self.assertEqual([r[0] for r in results], ["ok"] * len(results), results)
        self.assertEqual([r[1] for r in results], [200] * len(results), results)

    def test_two_first_wrongs_that_both_read_no_row(self):
        """둘 다 "줄 없음" 을 읽은 뒤 INSERT 한다. 500 없이 줄 하나다.

        우연한 겹침에 맡기지 않는다. INSERT 직전에 서로를 기다리게 해
        겹치는 순서를 고정한다.
        """
        barrier = threading.Barrier(2)
        real = QuerySet.bulk_create

        def gated(queryset, *args, **kwargs):
            barrier.wait(timeout=10)
            return real(queryset, *args, **kwargs)

        with mock.patch.object(QuerySet, "bulk_create", gated):
            results = _run_threads(
                self._call(self.others[0].pk), self._call(self.others[1].pk)
            )

        self._assert_all_ok(results)
        self.assertEqual(ReviewState.objects.count(), 1)
        self.assertTrue(ReviewState.objects.get().is_wrong)

    def test_many_wrongs_leave_one_row(self):
        results = _run_threads(*[self._call(self.others[0].pk) for _ in range(8)])

        self._assert_all_ok(results)
        self.assertEqual(ReviewState.objects.count(), 1)

    def test_mixed_answers_on_one_row_never_crash(self):
        """맞힘과 틀림이 겹치면 순서는 정해지지 않지만 줄은 하나이고 연속은 0 이다."""
        mark(self.user, self.word, wrong=True)

        results = _run_threads(
            *[
                self._call(self.word.pk if i % 2 else self.others[0].pk)
                for i in range(8)
            ]
        )

        self._assert_all_ok(results)
        row = ReviewState.objects.get()
        self.assertEqual(row.streak, 0)
