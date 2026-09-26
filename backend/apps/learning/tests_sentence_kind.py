"""한 판·복습·일일공부 응답의 sentence_kind.

화면(QuestionCard)은 이 값이 "error" 일 때만 문장 지문을 고정폭으로
그린다. 문장 문제에는 지문 문장의 종류가, 단어 문제에는 "" 가 와야 한다.

일일공부는 낸 문제를 판에 저장했다가 이어 풀 때 그대로 다시 준다. 이
칸이 생기기 전에 저장된 문제에는 칸이 없으므로, 그 판을 이어 풀어도
깨지지 않는지도 본다.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Sentence, SentenceKind, Word
from apps.vocab.tests_sentence_kind import seed_sentences
from apps.vocab.tests_sentence_kind import seed_words as seed_git_words

from . import daily_study
from .models import DailyStudy, ReviewState, StudyLength
from .tests_daily_study import make_user, seed_words

ROUND_URL = "/api/learning/rounds/"
ROUND_ANSWER_URL = "/api/learning/rounds/answer/"
REVIEW_URL = "/api/learning/review/"
REVIEW_ANSWER_URL = "/api/learning/review/answer/"
DAILY_URL = "/api/learning/daily/"
DAILY_ANSWER_URL = "/api/learning/daily/answer/"

SENTENCE_KINDS = (quiz.QuizKind.BLANK, quiz.QuizKind.SITUATION)


class KindCheckMixin:
    """문제 하나의 sentence_kind 가 화면에 뜬 것과 맞는지."""

    def expected_kind(self, question: dict) -> str:
        if question["kind"] == quiz.QuizKind.SITUATION:
            return Sentence.objects.get(text=question["prompt"]).kind
        if question["kind"] == quiz.QuizKind.BLANK:
            # 빈칸 지문은 원문에서 용어 하나만 가렸다. 가린 자리 앞뒤로 찾는다.
            head, tail = question["prompt"].split(quiz.BLANK_MARK, 1)
            matches = [
                s
                for s in Sentence.objects.all()
                if s.text.startswith(head) and s.text.endswith(tail)
            ]
            self.assertEqual(len(matches), 1, question["prompt"])
            return matches[0].kind
        return ""

    def assert_kind(self, question: dict) -> None:
        self.assertIn("sentence_kind", question, "칸이 빠졌다")
        self.assertEqual(
            question["sentence_kind"], self.expected_kind(question), question["prompt"]
        )


class RoundSentenceKindTest(KindCheckMixin, TestCase):
    """한 판(POST /api/learning/rounds/ 와 답하기)."""

    def setUp(self):
        cache.clear()
        seed_git_words()
        seed_sentences()

    def play(self, kinds: list[str], answers: int = 6) -> list[dict]:
        with mock.patch.object(quiz.QuizKind, "ALL", kinds):
            res = self.client.post(ROUND_URL)
            self.assertEqual(res.status_code, 201, res.content)
            data = res.json()
            questions = [data["question"]]
            token = data["token"]
            for _ in range(answers):
                res = self.client.post(
                    ROUND_ANSWER_URL,
                    {"token": token, "choice_id": questions[-1]["choices"][0]["id"]},
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 200, res.content)
                data = res.json()
                if data["finished"]:
                    break
                token = data["token"]
                questions.append(data["question"])
        return questions

    def test_situation_questions_carry_the_answer_sentence_kind(self):
        questions = self.play([quiz.QuizKind.SITUATION])
        for q in questions:
            self.assert_kind(q)
        # 첫 문제는 반드시 상황 고르기다. 전부 단어로 떨어졌으면 아무것도 안 본 것이다.
        self.assertEqual(questions[0]["kind"], quiz.QuizKind.SITUATION)
        self.assertEqual(
            {q["sentence_kind"] for q in questions if q["kind"] == "situation"},
            {SentenceKind.ERROR, SentenceKind.PHRASE},
        )

    def test_blank_questions_carry_the_prompt_sentence_kind(self):
        questions = self.play([quiz.QuizKind.BLANK])
        self.assertEqual(questions[0]["kind"], quiz.QuizKind.BLANK)
        for q in questions:
            self.assert_kind(q)

    def test_word_questions_carry_empty_string(self):
        """단어 문제는 문장 종류가 없다. None 이 아니라 "" 다."""
        for kind in quiz.QuizKind.WORD_KINDS:
            questions = self.play([kind], answers=2)
            for q in questions:
                self.assertNotIn(q["kind"], SENTENCE_KINDS)
                self.assertEqual(q["sentence_kind"], "")


class ReviewSentenceKindTest(KindCheckMixin, TestCase):
    """복습(POST /api/learning/review/ 와 답하기)."""

    def setUp(self):
        cache.clear()
        seed_git_words()
        self.sentences = seed_sentences()
        self.user = make_user("복습글꼴")
        self.client.force_login(self.user)

    def wrong(self, target_type: str, target_id: int) -> None:
        ReviewState.objects.create(
            user=self.user, target_type=target_type, target_id=target_id, is_wrong=True
        )

    def drain(self) -> list[dict]:
        res = self.client.post(REVIEW_URL)
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        questions = []
        while data["question"] is not None:
            questions.append(data["question"])
            res = self.client.post(
                REVIEW_ANSWER_URL,
                {"token": data["token"], "choice_id": data["question"]["choices"][0]["id"]},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            data = res.json()
        return questions

    def test_each_sentence_review_carries_its_own_kind(self):
        """에러 문장·실무 표현·단어를 섞어 틀려 두면 각자의 값이 온다."""
        error = next(s for s in self.sentences if s.kind == SentenceKind.ERROR)
        phrase = next(s for s in self.sentences if s.kind == SentenceKind.PHRASE)
        word = Word.objects.get(term="rebase")
        self.wrong("sentence", error.pk)
        self.wrong("sentence", phrase.pk)
        self.wrong("word", word.pk)

        questions = self.drain()

        self.assertEqual(len(questions), 3)
        got = {q["prompt"]: q["sentence_kind"] for q in questions if q["kind"] == "situation"}
        self.assertEqual(got, {error.text: SentenceKind.ERROR, phrase.text: SentenceKind.PHRASE})
        words = [q for q in questions if q["kind"] != "situation"]
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["sentence_kind"], "")


class DailySentenceKindTest(KindCheckMixin, TestCase):
    """일일공부(시작·답하기·이어 풀기)."""

    def setUp(self):
        cache.clear()
        seed_words()
        seed_git_words()
        self.sentences = seed_sentences()
        self.error = next(s for s in self.sentences if s.kind == SentenceKind.ERROR)
        self.user = make_user("일일글꼴")
        self.client.force_login(self.user)

    def start(self) -> dict:
        res = self.client.post(
            DAILY_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def force_situation(self, sentence: Sentence):
        """출제를 이 문장의 상황 고르기로 못박는다. 판 길이·학습 범위와 무관하게."""

        def made(*_args, **_kwargs):
            return quiz.make_situation_question(Sentence.objects.visible(), answer=sentence)

        return mock.patch.object(daily_study, "make_question", made)

    def test_word_question_carries_empty_string(self):
        """학습분 문제는 단어라 ""."""
        data = self.start()
        self.assertEqual(data["question"]["sentence_kind"], "")

    def test_sentence_question_carries_kind_on_start_resume_and_answer(self):
        with self.force_situation(self.error):
            data = self.start()
            self.assertEqual(data["question"]["sentence_kind"], SentenceKind.ERROR)

            # 이어 풀기는 저장해 둔 것을 그대로 준다.
            resumed = self.client.get(DAILY_URL).json()
            self.assertEqual(resumed["question"]["prompt"], self.error.text)
            self.assertEqual(resumed["question"]["sentence_kind"], SentenceKind.ERROR)

            res = self.client.post(
                DAILY_ANSWER_URL,
                {"token": resumed["token"], "choice_id": resumed["question"]["choices"][0]["id"]},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            nxt = res.json()["question"]
            if nxt is None:
                # 묶음 끝이면 학습 차례. 다음 GET 이 문제를 준다.
                nxt = self.client.get(DAILY_URL).json()["question"]
            self.assertIsNotNone(nxt)
            self.assertEqual(nxt["sentence_kind"], SentenceKind.ERROR)

    def test_saved_question_from_before_the_field_still_resumes(self):
        """칸이 생기기 전에 저장된 문제도 이어 풀고 답할 수 있다."""
        with self.force_situation(self.error):
            self.start()
        study = DailyStudy.objects.get(user=self.user)
        study.question["body"].pop("sentence_kind")
        study.save(update_fields=["question"])

        res = self.client.get(DAILY_URL)
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["question"]["prompt"], self.error.text, "저장분 대신 새로 뽑았다")
        # 없는 칸은 없거나 빈 값으로 온다. 화면은 둘 다 본문체다.
        self.assertIn(data["question"].get("sentence_kind"), (None, ""))

        res = self.client.post(
            DAILY_ANSWER_URL,
            {"token": data["token"], "choice_id": data["question"]["choices"][0]["id"]},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        study.refresh_from_db()
        self.assertEqual(study.answered, 1)

    def test_daily_study_function_level_body_has_the_field(self):
        """_next_question 이 저장하는 body 에도 칸이 있다(이어 풀기의 원본)."""
        with self.force_situation(self.error):
            self.start()
        study = DailyStudy.objects.get(user=self.user)
        self.assertEqual(study.question["body"]["sentence_kind"], SentenceKind.ERROR)
