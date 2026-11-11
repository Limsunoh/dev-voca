"""빈칸 문제에서 에러 등급 말(error·warning·fatal·panic·exception)이 서로의 오답으로 나오지 않는지.

"____: cannot find symbol" 에 error 와 fatal 이 함께 보기로 나오면 둘 다 맞는
답이다. 정답이 등급 말이면 나머지 넷을 보기에서 빼야 하고, 정답이 등급 말이
아니면 빼지 말아야 한다. 빼서 보기가 모자란 문장은 건너뛰고 다른 문장을 본다.

보기와 문장 순서가 무작위라 한 번으로는 못 잡는다. 같은 호출을 여러 번 돌린다.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.learning import session

from .models import Sentence, Word
from .quiz import QuizKind, _blank_out, _terms_in, make_blank_question

LEVELS = ("error", "warning", "fatal", "panic", "exception")
LEVEL_REGEX = r"^(error|warning|fatal|panic|exception)$"
QUIZ_URL = "/api/vocab/sentences/quiz/"
GRADE_URL = "/api/vocab/sentences/grade/"

# 무작위 결과를 몇 번 뽑아 보는가. 보기 후보가 너댓 개라 이 정도면 섞인
# 경우가 빠짐없이 한 번은 나온다.
REPEAT = 40


def word(term: str, category: str = "debug", reviewed: bool = True) -> Word:
    return Word.objects.create(
        term=term, meaning=f"{term} 뜻", category=category, is_reviewed=reviewed
    )


def sentence(text: str, reviewed: bool = True) -> Sentence:
    return Sentence.objects.create(
        text=text, translation=f"{text} 해석", category="debug", is_reviewed=reviewed
    )


def is_level(term: str) -> bool:
    return term.strip().lower() in LEVELS


class LevelWordHelperMixin:
    def assert_no_other_level(self, question, answer_term: str | None = None):
        """정답이 등급 말이면 보기에 다른 등급 말이 없다. 보기는 4개, 겹치지 않는다."""
        self.assertIsNotNone(question)
        texts = [c.text for c in question.choices]
        self.assertEqual(len(texts), 4, texts)
        self.assertEqual(len({c.id for c in question.choices}), 4, texts)
        answer = next(c.text for c in question.choices if c.id == question.answer_id)
        if answer_term is not None:
            self.assertEqual(answer, answer_term)
        if is_level(answer):
            others = [t for t in texts if t != answer and is_level(t)]
            self.assertEqual(others, [], f"정답 {answer} 옆에 등급 말: {texts}")


class AnswerIsLevelWordTest(LevelWordHelperMixin, TestCase):
    """정답이 등급 말이면 다른 등급 말은 보기 후보에서 빠진다."""

    NON_LEVEL = ("stack trace", "breakpoint", "debugger", "core dump")

    def setUp(self):
        for term in self.NON_LEVEL:
            word(term)

    def check_answer(self, answer_term: str, text: str):
        # subTest 하나가 실패해도 다음 것이 깨끗한 상태에서 시작하게 먼저 지운다.
        Word.objects.filter(term__iregex=LEVEL_REGEX).delete()
        Sentence.objects.all().delete()
        for level in LEVELS:
            if level != answer_term.lower():
                word(level)
        word(answer_term)
        sentence(text)
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assert_no_other_level(q, answer_term)
            self.assertIn("____", q.prompt)

    def test_each_level_word_as_answer(self):
        """다섯 등급 말 각각이 정답일 때 나머지 넷이 한 번도 보기로 안 나온다."""
        for level in LEVELS:
            with self.subTest(level):
                self.check_answer(level, f"{level}: cannot find symbol")

    def test_capitalized_term_is_still_a_level_word(self):
        """term 이 "Error"·"FATAL" 처럼 대문자여도 등급 말로 본다."""
        for answer in ("Error", "FATAL", "Exception"):
            with self.subTest(answer):
                self.check_answer(answer, f"{answer.lower()}: cannot find symbol")

    def test_capitalized_distractor_is_also_excluded(self):
        """정답이 error 일 때 "Warning"·"PANIC" 처럼 대문자로 적힌 다른 등급 말도 빠진다."""
        word("error")
        word("Warning")
        word("PANIC")
        word("Fatal")
        sentence("error: cannot find symbol")
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assert_no_other_level(q, "error")

    def test_prompt_with_several_levels_blanks_only_the_answer(self):
        """한 문장에 등급 말이 여럿이면 가장 긴 것이 정답이고 나머지는 보기에서 빠진다.

        "Fatal error: Uncaught exception" 은 exception 이 정답이다. 지문에 남은
        Fatal·error 가 보기에도 있으면 지문 안의 말을 고르는 함정이 된다.
        """
        for level in LEVELS:
            word(level)
        sentence("Fatal error: Uncaught exception in main")
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assert_no_other_level(q, "exception")
            self.assertEqual(q.prompt, "Fatal error: Uncaught ____ in main")

    def test_same_category_first_after_exclusion(self):
        """등급 말을 뺀 뒤에도 오답은 같은 분류(debug)에서 먼저 고른다."""
        for level in LEVELS:
            word(level)
        for term in ("commit", "rebase", "stash", "merge", "cherry-pick"):
            word(term, category="git")
        sentence("panic: runtime error index out of range")
        debug_others = set(self.NON_LEVEL)
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assert_no_other_level(q)
            wrong = {c.text for c in q.choices if c.id != q.answer_id}
            self.assertTrue(wrong <= debug_others, wrong)


class AnswerIsNotLevelWordTest(LevelWordHelperMixin, TestCase):
    """정답이 등급 말이 아니면 등급 말은 그대로 보기 후보다. 과하게 빼지 않는다."""

    def setUp(self):
        for level in LEVELS:
            word(level)

    def wrong_terms(self, answer_term: str, text: str) -> set[str]:
        word(answer_term)
        sentence(text)
        seen: set[str] = set()
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assertIsNotNone(q)
            answer = next(c.text for c in q.choices if c.id == q.answer_id)
            self.assertEqual(answer, answer_term)
            seen |= {c.text for c in q.choices if c.id != q.answer_id}
        return seen

    def test_debug_word_answer_keeps_level_words(self):
        """정답이 stack trace 면 후보가 등급 말뿐이어도 문제가 나온다."""
        seen = self.wrong_terms("stack trace", "Read the stack trace first.")
        self.assertTrue(seen <= set(LEVELS))
        self.assertGreaterEqual(len(seen), 4)

    def test_longer_term_containing_error_is_not_a_level_word(self):
        """ "error handling" 이 정답이면 제외가 걸리지 않는다(정확히 같은 낱말만)."""
        seen = self.wrong_terms("error handling", "Add error handling to this call.")
        self.assertEqual(seen, set(LEVELS))

    def test_term_with_level_inside_word_is_not_excluded(self):
        """panicked·warnings·ErrorBoundary 처럼 등급 말을 품은 말이 정답이면 제외하지 않는다."""
        for answer, text in (
            ("panicked", "thread main panicked at src/main.rs"),
            ("ErrorBoundary", "Wrap the page in an ErrorBoundary component."),
            ("warnings", "Turn warnings into failures in CI."),
        ):
            with self.subTest(answer):
                # 앞 subTest 가 실패해도 그 문장이 남지 않게 먼저 지운다.
                Sentence.objects.all().delete()
                seen = self.wrong_terms(answer, text)
                self.assertTrue(seen & set(LEVELS), seen)


class SkipAndGiveUpTest(LevelWordHelperMixin, TestCase):
    """제외 때문에 보기가 모자라면 그 문장만 건너뛴다. 전부 안 되면 None."""

    def setUp(self):
        for level in LEVELS:
            word(level)

    def test_short_sentence_is_skipped_for_another(self):
        """error 문장은 보기가 모자라도 stack trace 문장으로 문제가 나온다.

        예전처럼 모자라면 바로 None 을 내면 문장 순서에 따라 절반쯤 실패한다.
        """
        word("stack trace")
        sentence("error: cannot find symbol")
        sentence("Read the stack trace first.")
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assertIsNotNone(q)
            self.assertIn("stack trace", [c.text for c in q.choices])
            self.assertEqual(q.prompt, "Read the ____ first.")

    def test_every_sentence_short_returns_none(self):
        """모든 문장이 모자라면 None 이다. 끝없이 돌지 않는다."""
        word("stack trace")
        for level in LEVELS:
            sentence(f"{level}: cannot find symbol")
        for i in range(20):
            sentence(f"{LEVELS[i % 5]}: line {i} failed")
        for _ in range(5):
            self.assertIsNone(
                make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            )

    def test_only_level_words_in_db_returns_none(self):
        """단어가 등급 말 다섯뿐이면 정답이 등급 말인 문제는 만들 수 없다."""
        sentence("fatal: not a git repository")
        self.assertIsNone(make_blank_question(Sentence.objects.visible(), Word.objects.visible()))

    def test_excluded_sentence_ids_still_respected(self):
        """건너뛰는 흐름이 exclude_sentence_ids 를 무시하지 않는다."""
        # 등급 말을 뺀 남은 후보가 둘뿐이라 error 문장은 못 쓴다.
        word("stack trace")
        word("breakpoint")
        good = sentence("Read the stack trace first.")
        other = sentence("Set a breakpoint here.")
        sentence("error: cannot find symbol")
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible(), [good.pk])
            self.assertIsNotNone(q)
            self.assertEqual(q.source_sentence_id, other.pk)


class ReviewGateTest(LevelWordHelperMixin, TestCase):
    """검수 안 된 단어·문장이 빈칸 문제의 정답·보기·지문으로 새지 않는다."""

    def test_unreviewed_never_in_choices_or_answer(self):
        for term in ("error", "stack trace", "breakpoint", "debugger"):
            word(term)
        hidden = {
            word(term, reviewed=False).pk
            for term in ("segmentation", "warning", "core dump", "symbol", "heap")
        }
        # 검수 안 된 segmentation 이 정답 후보에 들어오면 error 보다 길어 정답이 된다.
        sentence("error: segmentation fault near symbol")
        hidden_sentence = sentence("core dump written to heap", reviewed=False)
        for _ in range(REPEAT):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assert_no_other_level(q, "error")
            self.assertFalse({c.id for c in q.choices} & hidden)
            self.assertNotEqual(q.source_sentence_id, hidden_sentence.pk)


class BlankQuizApiTest(LevelWordHelperMixin, TestCase):
    """문장 문제풀기 API 로 빈칸 문제를 받아 채점까지 하는 경로."""

    @classmethod
    def setUpTestData(cls):
        for level in LEVELS:
            word(level)
        for term in ("stack trace", "breakpoint", "debugger"):
            word(term)
        word("core dump", reviewed=False)
        sentence("warning: unused variable x")
        sentence("panic: runtime error index out of range")

    def test_api_blank_never_offers_two_levels_and_grades(self):
        """보기에 등급 말은 정답 하나뿐이고, 그것을 고르면 맞았다고 채점한다."""
        hidden = Word.objects.get(term="core dump").pk
        for _ in range(REPEAT // 2):
            res = self.client.get(QUIZ_URL, {"kind": QuizKind.BLANK})
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            texts = [c["text"] for c in body["choices"]]
            levels = [t for t in texts if is_level(t)]
            self.assertEqual(len(levels), 1, texts)
            self.assertNotIn(hidden, [c["id"] for c in body["choices"]])

            answer_id = next(c["id"] for c in body["choices"] if is_level(c["text"]))
            graded = self.client.post(
                GRADE_URL,
                {"token": body["token"], "picked": answer_id},
                content_type="application/json",
            )
            self.assertEqual(graded.status_code, 200, graded.content)
            self.assertTrue(graded.json()["correct"])
            self.assertEqual(graded.json()["word"]["term"], levels[0])

    def test_round_session_blank_never_offers_two_levels(self):
        """한 판·일일공부가 쓰는 session.make_question 도 같은 규칙을 지킨다."""
        with mock.patch.object(session, "random") as fake:
            fake.choice.return_value = QuizKind.BLANK
            for _ in range(REPEAT // 2):
                q = session.make_question([], [])
                self.assertEqual(q.kind, QuizKind.BLANK)
                self.assert_no_other_level(q)


class SeededLevelSentenceTest(LevelWordHelperMixin, TestCase):
    """실제 시드로 채운 DB 에서 정답이 등급 말이 되는 문장을 모두 돌려 본다."""

    @classmethod
    def setUpTestData(cls):
        for command in (
            "seed_words",
            "seed_words_more",
            "seed_words_launch",
            "seed_exam_words",
            "seed_sentences",
            "seed_sentences_more",
        ):
            call_command(command, stdout=StringIO())

    def test_every_level_answer_sentence(self):
        """정답이 등급 말이 되는 시드 문장마다 보기에 다른 등급 말이 없다."""
        words = Word.objects.visible()
        terms = [(pk, t.strip()) for pk, t in words.values_list("pk", "term") if t.strip()]
        self.assertEqual(
            sorted(t for _, t in terms if is_level(t)), sorted(LEVELS), "시드에 등급 말 다섯이 있다"
        )

        targets = []
        for s in Sentence.objects.visible():
            found = _terms_in(s.text, terms)
            if not found:
                continue
            _, term = max(found, key=lambda pair: len(pair[1]))
            if is_level(term) and _blank_out(s.text, term) is not None:
                targets.append(s)
        self.assertTrue(targets, "정답이 등급 말인 시드 문장이 하나는 있다")

        for s in targets:
            for _ in range(5):
                q = make_blank_question(Sentence.objects.filter(pk=s.pk), words)
                with self.subTest(sentence=s.text):
                    # 등급 말을 빼도 debug 단어가 많아 보기는 늘 찬다.
                    self.assert_no_other_level(q)
