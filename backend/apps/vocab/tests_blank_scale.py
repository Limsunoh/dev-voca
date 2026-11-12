"""빈칸 문제가 단어 수와 상관없이 같은 단어를 찾는지(quiz._terms_for).

지켜야 할 것.
- 문장에서 찾는 단어가 예전 방식(단어 전부를 정규식으로 대 보기)과 같다.
  경계("format" 안의 "for" 는 아님), 대소문자, 여러 낱말 용어, 기호가 낀 용어,
  숫자나 한글에 붙은 용어, 앞뒤 띄어쓰기가 있는 term, 100자 용어까지. 실제 시드
  문장 전부에서도 같다.
- 빈칸 문제 하나에 드는 쿼리 수가 단어 수에 따라 늘지 않고, 정규식에 넘기는
  단어도 몇 개뿐이다.
- 후보 조각이 너무 많은 긴 로그나 3천 자 넘는 문장은 빈칸 후보에서 빠지고, 다른
  문장으로 문제가 나온다. 수백 자 영어 문장과 한글이 섞인 문장은 빠지지 않는다.
- 쿼리가 쓰는 식이 Word 의 인덱스 식(TERM_KEY)과 같다. 다르면 결과는 같은데
  Postgres 가 인덱스를 못 써 단어 표를 매번 다 훑는다.
"""

from __future__ import annotations

import random
import time
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.learning import daily_study, session
from apps.learning.models import StudyLength
from apps.learning.tests_daily_study import make_user, seed_words

from . import quiz
from .models import TERM_KEY, Sentence, Word
from .quiz import (
    QuizKind,
    _blank_out,
    _term_candidates,
    _terms_for,
    _terms_in,
    make_blank_question,
)

LONG_TERM = "a" + "b" * 98 + "c"  # 100자, Word.term 의 최대 길이

TERMS = [
    "for",
    "format",
    "git",
    "GitHub",
    "CI/CD",
    "CI",
    ".gitignore",
    "node_modules",
    "C++",
    "pull request",
    "out of scope",
    "scope",
    "API",
    "404",
    "e.g.",
    "commit",
    LONG_TERM,
]

SENTENCES = [
    "Format the output for the user before you commit.",
    "Git and github are different; GitHub hosts git repos.",
    "Run the CI/CD pipeline, then check CI logs.",
    "Add node_modules to .gitignore so git ignores it.",
    "C++ templates are out of scope for this pull request.",
    "The API returned 404 for /api/v2/users.",
    "APIs and apis are plural, not the API itself.",
    "commit",
    "Use tools, e.g. linters, before each commit!",
    "formatting formats format",
    "commit을 먼저 하고 git 으로 올린다.",
    f"see {LONG_TERM}.",
    f"see {LONG_TERM}d",
]


def old_terms_in(text: str, words) -> list[tuple[int, str]]:
    """예전 방식 그대로: 단어 전부를 읽어 정규식으로 대 본다."""
    terms = [(pk, t.strip()) for pk, t in words.values_list("pk", "term") if t.strip()]
    return _terms_in(text, terms)


def new_terms_in(text: str, words) -> list[tuple[int, str]]:
    """make_blank_question 이 문장 하나에 하는 것과 같은 순서로 찾는다."""
    mine = _term_candidates(text)
    assert mine is not None
    terms = _terms_for(words, mine)
    return _terms_in(text, [(pk, term) for pk, term, key in terms if key in mine])


def answer_text(q) -> str:
    """문제의 정답 보기 글자."""
    return next(c.text for c in q.choices if c.id == q.answer_id)


def pick(found: list[tuple[int, str]]) -> str | None:
    """빈칸으로 가릴 단어. make_blank_question 과 같은 규칙(가장 긴 것, 동점은 앞)."""
    return max(found, key=lambda pair: len(pair[1]))[1] if found else None


class TermsForMatchesOldScanTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for term in TERMS:
            Word.objects.create(term=term, meaning=f"{term[:20]} 뜻", category="git", is_reviewed=True)
        # Admin 을 거치지 않고 들어간, 앞뒤 띄어쓰기가 낀 term 도 예전처럼 잡혀야 한다.
        Word.objects.create(term="  stash ", meaning="뜻", category="git", is_reviewed=True)

    def test_same_words_found_in_every_sentence(self):
        words = Word.objects.visible()
        for text in [*SENTENCES, "git stash pop", "STASH it"]:
            with self.subTest(text=text):
                self.assertEqual(new_terms_in(text, words), old_terms_in(text, words))

    def test_boundaries_and_case(self):
        words = Word.objects.visible()
        found = {t for _, t in new_terms_in(SENTENCES[0], words)}
        # "Format" 은 대소문자를 무시해 잡히고, "format" 안의 "for" 는 안 잡힌다.
        self.assertIn("format", found)
        self.assertIn("for", found)  # "output for the user" 의 for
        self.assertNotIn("for", {t for _, t in new_terms_in("formatting formats", words)})
        self.assertEqual({t for _, t in new_terms_in(SENTENCES[2], words)}, {"CI/CD", "CI"})
        # "APIs" 의 API 는 뒤에 s 가 붙어 아니다.
        self.assertEqual({t for _, t in new_terms_in(SENTENCES[6], words)}, {"API"})
        # 한글이 바로 붙어도 영어 알파벳이 아니라 경계다.
        self.assertIn("commit", {t for _, t in new_terms_in(SENTENCES[10], words)})
        # 100자 용어는 잡히고, 뒤에 알파벳이 붙으면 안 잡힌다.
        self.assertIn(LONG_TERM, {t for _, t in new_terms_in(SENTENCES[11], words)})
        self.assertNotIn(LONG_TERM, {t for _, t in new_terms_in(SENTENCES[12], words)})

    def test_filtered_words_stay_filtered(self):
        # 호출부가 좁힌 단어 묶음(검수된 것) 밖의 단어는 찾지 않는다.
        Word.objects.filter(term="commit").update(is_reviewed=False)
        found = {t for _, t in new_terms_in("commit", Word.objects.visible())}
        self.assertEqual(found, set())


class SeedSentencesMatchOldScanTest(TestCase):
    """실제 시드(단어 약 1천, 문장 약 4백)의 문장마다 예전과 같은 단어를 가린다."""

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

    def test_every_seed_sentence(self):
        words = Word.objects.visible()
        sentences = list(Sentence.objects.visible())
        self.assertGreater(len(sentences), 300)
        for s in sentences:
            old = old_terms_in(s.text, words)
            new = new_terms_in(s.text, words)
            with self.subTest(sentence=s.text):
                self.assertEqual(new, old)
                self.assertEqual(pick(new), pick(old))

    def test_every_seed_sentence_through_make_blank_question(self):
        """위 테스트는 make_blank_question 의 순서를 테스트 안에서 흉내 낸다.
        실제 함수를 문장 하나짜리 묶음으로 불러, 가린 단어가 예전 규칙과 같은지 본다.
        """
        words = Word.objects.visible()
        made = 0
        for s in Sentence.objects.visible():
            q = make_blank_question(Sentence.objects.filter(pk=s.pk), words)
            expected = pick(old_terms_in(s.text, words))
            with self.subTest(sentence=s.text):
                if q is None:
                    # 예전에도 못 냈어야 한다(가릴 단어가 없거나 가리면 단서가 안 남는다).
                    self.assertTrue(expected is None or _blank_out(s.text, expected) is None)
                    continue
                made += 1
                self.assertEqual(answer_text(q), expected)
        self.assertGreater(made, 150)


class BlankQuestionScaleTest(TestCase):
    """단어가 늘어도 빈칸 문제 하나의 쿼리 수와 정규식 검사 수가 그대로다."""

    def setUp(self):
        for term in ["commit", "branch", "merge", "rebase", "stash"]:
            Word.objects.create(term=term, meaning=f"{term} 뜻", category="git", is_reviewed=True)
        Sentence.objects.create(
            text="Please commit your changes before you switch branch.",
            translation="해석",
            category="git",
            is_reviewed=True,
        )

    def add_fillers(self, count: int) -> None:
        Word.objects.bulk_create(
            Word(term=f"filler{i}", meaning="뜻", category="git", is_reviewed=True)
            for i in range(count)
        )

    def count_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
        self.assertIsNotNone(q)
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_words(self):
        few = self.count_queries()
        self.add_fillers(3000)  # 예전 정규식 캐시(2048)를 넘는 수
        self.assertEqual(self.count_queries(), few)

    def test_regex_checks_only_narrowed_words(self):
        # 예전 방식은 쿼리 수가 같아서 위 테스트로는 못 잡는다. 느린 까닭은 단어
        # 전부를 정규식으로 대 보는 것이었다. 정규식에 넘기는 단어 수를 본다.
        self.add_fillers(3000)
        seen = []
        real = quiz._terms_in

        def spy(text, terms):
            seen.append(len(terms))
            return real(text, terms)

        with mock.patch.object(quiz, "_terms_in", side_effect=spy):
            self.assertIsNotNone(
                make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            )
        self.assertTrue(seen)
        self.assertLessEqual(max(seen), 5)

    def test_long_log_sentence_is_skipped_not_broken(self):
        # UUID 가 여럿 든 긴 에러는 후보 조각이 수만 개라 빈칸 후보에서 뺀다.
        # 같이 뽑힌 다른 문장으로 문제가 나오고, 쿼리도 터지지 않는다.
        uuids = " ".join(f"{i:08x}-1a2b-3c4d-5e6f-{i:012x}" for i in range(40))
        Sentence.objects.create(
            text=f"commit failed for ids {uuids}",
            translation="해석",
            category="git",
            is_reviewed=True,
        )
        self.assertIsNone(_term_candidates(f"commit failed for ids {uuids}"))
        for _ in range(5):
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assertIsNotNone(q)
            self.assertNotIn("failed for ids", q.prompt)


class QueryUsesIndexExpressionTest(TestCase):
    def test_index_and_query_share_term_key(self):
        index = next(i for i in Word._meta.indexes if i.name == "vocab_word_term_lower_idx")
        self.assertEqual(index.expressions, (TERM_KEY,))
        # 쿼리 쪽이 다른 식을 쓰면(예: Lower 만) 결과는 같아서 다른 테스트로는
        # 안 잡힌다. 실제로 나가는 SQL 을 본다.
        with CaptureQueriesContext(connection) as ctx:
            _terms_for(Word.objects.visible(), {"commit"})
        self.assertIn("LOWER(TRIM(", ctx.captured_queries[-1]["sql"].upper())


# 기호·숫자·대소문자·한글/일본어·공백 문자·겹치는 용어·정규식 특수문자가 낀 용어.
SYMBOL_TERMS = [
    "C#",
    ".NET",
    "NET",
    "ASP.NET",
    "std::vector",
    "vector",
    "node.js",
    "node",
    "--force",
    "force",
    "$PATH",
    "PATH",
    "<div>",
    "div",
    "a_b",
    "pull-request",
    "pull request",
    "request",
    "HTTP/2",
    "2.0",
    "404",
    "a+b",
    "(x|y)",
    "[z]",
    "^start$",
    ".*",
    "x|y",
    "\\d+",
    "it's",
    '"quoted"',
    "e.g.",
    "co-op",
    "push",
    "pull",
    LONG_TERM[:99],
    LONG_TERM,
]

SYMBOL_SENTENCES = [
    "Port the C# service to .NET 8, not ASP.NET.",
    "Use std::vector<int> instead of a raw vector.",
    "node.js runs node scripts; nodejs is not node.js.",
    "git push --force rewrites history; force-push carefully.",
    "Add it to $PATH (not PATH_INFO or PATHS).",
    "Wrap it in <div> tags; a <divider> is different.",
    "rename a_b to ab, not a_bc or xa_b.",
    "open a pull-request, then a pull request; the request waits.",
    "HTTP/2 is faster than HTTP/1.1; v2.0 and 2.0.1 differ. 4040 is not 404.",
    "a+b (x|y) [z] ^start$ .* \\d+ are regex-ish.",
    'it\'s "quoted" e.g. here.',
    "co-op and coop and co-opted",
    "Push and pull are the same length.",
    "PULL REQUEST in caps and Pull Request in title case.",
    "commit\tpush\npull\r\nrequest",
    "C#を学んでから.NETへ。pushした",
    "C#로 짜고 .NET에 올린 뒤 push했다",
    "push push push and PUSH again",
    "(pull)[push]{request}\"node\"'vector'",
    f"x {LONG_TERM[:99]} y",
    f"x {LONG_TERM} y",
    f"x {LONG_TERM}c y",
    f"x _{LONG_TERM}_ y",
]


class SymbolTermsMatchOldScanTest(TestCase):
    """기호가 낀 용어와 까다로운 문장에서 예전 방식과 같은 단어를 같은 순서로 찾는다."""

    @classmethod
    def setUpTestData(cls):
        # 일부러 term 순서와 다르게 만든다. pk 순서로 동점을 가르면 틀린다.
        for term in reversed(SYMBOL_TERMS):
            Word.objects.create(term=term, meaning="뜻", category="git", is_reviewed=True)

    def test_hand_picked_sentences(self):
        words = Word.objects.visible()
        for text in SYMBOL_SENTENCES:
            with self.subTest(text=text):
                old = old_terms_in(text, words)
                new = new_terms_in(text, words)
                self.assertEqual(new, old)
                self.assertEqual(pick(new), pick(old))

    def test_specific_expectations(self):
        words = Word.objects.visible()

        def found(text):
            return {t for _, t in new_terms_in(text, words)}

        # ASP.NET 안의 .NET 은 앞이 P(알파벳)라 아니다. 따로 쓴 .NET 은 맞다.
        self.assertEqual(found("ASP.NET only") & {"ASP.NET", ".NET"}, {"ASP.NET"})
        self.assertIn(".NET", found("to .NET 8"))
        # PATH_INFO 의 PATH 는 뒤가 밑줄(알파벳 아님)이라 맞는다 - 예전과 같다.
        self.assertIn("PATH", found("PATH_INFO"))
        self.assertNotIn("PATH", found("PATHS"))
        # 일본어·한글이 바로 붙어도 경계다.
        self.assertTrue({"C#", ".NET", "push"} <= found("C#を学んでから.NETへ。pushした"))
        # 99자 용어는 100자 용어 안에서 뒤가 c(알파벳)라 안 잡힌다.
        self.assertEqual(found(f"x {LONG_TERM} y") & {LONG_TERM, LONG_TERM[:99]}, {LONG_TERM})
        self.assertEqual(found(f"x {LONG_TERM}c y") & {LONG_TERM, LONG_TERM[:99]}, set())

    def test_random_sentences_match_old_scan(self):
        """기호·공백·한글을 섞어 무작위로 만든 문장 400개에서 예전과 같다(시드 고정)."""
        rng = random.Random(20261112)
        glue = [" ", " ", "\t", "\n", "-", "_", ".", ",", "(", ")", '"', "'", "/", ":",
                "#", "$", "1", "0", "가", "あ", "a", "Z", "s", ""]
        words = Word.objects.visible()
        for _ in range(400):
            parts = []
            for _ in range(rng.randint(1, 6)):
                term = rng.choice(SYMBOL_TERMS[:-2])  # 100자 근처는 위에서 따로 본다
                term = rng.choice([term, term.upper(), term.lower(), term.title()])
                parts += [rng.choice(glue), term, rng.choice(glue)]
            text = "".join(parts)
            with self.subTest(text=text):
                self.assertEqual(new_terms_in(text, words), old_terms_in(text, words))


class MakeBlankQuestionPicksSameWordTest(TestCase):
    """make_blank_question 이 실제로 가리는 단어. 헬퍼 흉내가 아니라 함수 그대로 본다."""

    def setUp(self):
        for i in range(4):
            self.word(f"zzfiller{i}")

    def word(self, term: str, reviewed: bool = True) -> Word:
        return Word.objects.create(term=term, meaning="뜻", category="git", is_reviewed=reviewed)

    def ask(self, text: str):
        s = Sentence.objects.create(text=text, translation="해석", category="git", is_reviewed=True)
        return make_blank_question(Sentence.objects.filter(pk=s.pk), Word.objects.visible())

    def test_symbol_terms_answer_and_prompt(self):
        for term in ["--force", "force", "C#", ".NET", "pull request", "request", "$PATH"]:
            self.word(term)
        cases = [
            ("Run git push --force only on your own branch.", "--force",
             "Run git push ____ only on your own branch."),
            ("Port the C# service to .NET first.", ".NET", "Port the C# service to ____ first."),
            ("Open a pull request after the request is approved.", "pull request",
             "Open a ____ after the request is approved."),
            ("Check $PATH before running.", "$PATH", "Check ____ before running."),
        ]
        for text, answer, prompt in cases:
            with self.subTest(text=text):
                q = self.ask(text)
                self.assertIsNotNone(q)
                self.assertEqual(answer_text(q), answer)
                self.assertEqual(q.prompt, prompt)

    def test_tie_goes_to_term_order_not_pk_order(self):
        """길이가 같으면 term 순서가 앞인 것. push 를 먼저 만들어도 pull 이 답이다."""
        self.word("push")
        self.word("pull")
        for _ in range(5):
            q = self.ask("push the branch, then pull it back.")
            self.assertEqual(answer_text(q), "pull")

    def test_unreviewed_longer_term_is_not_used(self):
        """검수 안 된 pull request 가 있어도 검수된 request 로 낸다. 정답·보기에 안 샌다."""
        hidden = self.word("pull request", reviewed=False)
        self.word("request")
        for _ in range(5):
            q = self.ask("Open a pull request today.")
            self.assertIsNotNone(q)
            self.assertEqual(answer_text(q), "request")
            self.assertNotIn(hidden.pk, [c.id for c in q.choices])

    def test_regex_recheck_drops_case_fold_mismatch(self):
        """대소문자 접기가 파이썬 lower 와 정규식에서 다른 글자.

        터키어 대문자 I(U+0130)를 lower 하면 "i" + 윗점(U+0307) 두 글자가 된다.
        그래서 "xİndex" 의 조각을 lower 한 것이 term "xi" + 윗점 + "ndex" 와 같아져
        DB 에서 찾힌다. 예전 판정(정규식)은 둘을 같다고 보지 않는다. 정규식으로
        다시 보지 않으면 이 term 이 더 길어 정답으로 골랐다가 빈칸을 못 뚫어
        문제가 안 나온다. 첫 글자를 ASCII(x)로 둔 것은 조각이 비ASCII 로 시작할
        수 없어서다(_is_term_edge). 숨은 글자를 소스에 적지 않으려고 chr 로 만든다.
        """
        self.word("x" + "i" + chr(0x307) + "ndex")
        self.word("error")
        q = self.ask("x" + chr(0x130) + "ndex error")
        self.assertIsNotNone(q)
        self.assertEqual(answer_text(q), "error")

class CandidateLimitTest(TestCase):
    """후보 조각 상한(_MAX_CANDIDATES)의 경계와 긴 문장."""

    TEXT = "Run git push --force only on your own branch, then open a pull request today."

    def test_boundary_is_inclusive(self):
        with mock.patch.object(quiz, "_MAX_CANDIDATES", 10**6):
            size = len(_term_candidates(self.TEXT))
        with mock.patch.object(quiz, "_MAX_CANDIDATES", size):
            self.assertEqual(len(_term_candidates(self.TEXT)), size)
        with mock.patch.object(quiz, "_MAX_CANDIDATES", size - 1):
            self.assertIsNone(_term_candidates(self.TEXT))

    def test_long_plain_and_korean_sentences_still_make_blanks(self):
        """예전에 빈칸이 나오던 긴 문장이 상한 때문에 빠지면 안 된다.

        처음 상한(문장 하나 2,000개)은 영어 문장 700자, 한글이 섞인 문장 95자에서
        넘쳐 그 문장으로는 빈칸 문제가 아예 안 나왔다.
        """
        for term in ["commit", "zzfill1", "zzfill2", "zzfill3"]:
            Word.objects.create(term=term, meaning="뜻", category="git", is_reviewed=True)
        english = "Please commit your work. " + "Keep the history clean and small. " * 21
        # 용어를 가린 뒤에도 영어 글자가 남아야 빈칸 문제가 된다(_blank_out 의 단서 규칙).
        korean = "작업을 끝내면 commit 을 먼저 하고 git push 로 올린다. " + (
            "변경 내용을 짧게 설명한 뒤 PR 을 연다. " * 12
        )
        self.assertGreater(len(english), 700)
        self.assertGreater(len(korean), 300)
        for text in (english, korean):
            with self.subTest(length=len(text)):
                self.assertIsNotNone(_term_candidates(text))
                s = Sentence.objects.create(
                    text=text, translation="해석", category="git", is_reviewed=True
                )
                q = make_blank_question(Sentence.objects.filter(pk=s.pk), Word.objects.visible())
                self.assertIsNotNone(q)
                self.assertEqual(answer_text(q), "commit")
        self.assertLess(len(_term_candidates(korean)), 200)

    def test_repeated_characters_give_up_fast(self):
        """같은 글자가 길게 이어진 줄은 후보가 적어도 만드는 데 오래 걸렸다(20만 자 2초).

        3천 자 상한(_MAX_TEXT_LENGTH)에서 바로 뺀다.
        """
        started = time.perf_counter()
        self.assertIsNone(_term_candidates("0" * 200000))
        self.assertIsNone(_term_candidates("-" * 50000))
        self.assertLess(time.perf_counter() - started, 0.2)

    def test_huge_log_gives_up_fast(self):
        """수십만 자 로그는 3천 자 상한(_MAX_TEXT_LENGTH)에서 바로 뺀다."""
        log = " ".join(f"{i:08x}-1a2b-3c4d-5e6f-{i:012x}" for i in range(5000))
        started = time.perf_counter()
        self.assertIsNone(_term_candidates(log))
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_twelve_sentences_near_the_cap_in_one_query(self):
        """뽑힌 12문장이 모두 상한 근처여도 쿼리 하나로 묻고 터지지 않는다(SQLite 변수 상한)."""
        rng = random.Random(7)
        letters = "abcdefghijklmnopqrstuvwxyz"
        for term in ["commit", "zzfill1", "zzfill2", "zzfill3"]:
            Word.objects.create(term=term, meaning="뜻", category="git", is_reviewed=True)
        total = 0
        for _ in range(12):
            text = "commit "
            while True:
                more = text + "".join(rng.choice(letters) for _ in range(5)) + " "
                c = _term_candidates(more)
                if c is None or len(c) > 1900:
                    break
                text = more
            total += len(_term_candidates(text))
            Sentence.objects.create(text=text, translation="해석", category="git", is_reviewed=True)
        self.assertGreater(total, 12 * 1500)
        with CaptureQueriesContext(connection) as ctx:
            q = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
        self.assertIsNotNone(q)
        self.assertEqual(answer_text(q), "commit")
        lookups = [x for x in ctx.captured_queries if "LOWER(TRIM(" in x["sql"].upper()]
        self.assertEqual(len(lookups), 1)


class BlankQuestionApiPathsTest(TestCase):
    """빈칸 문제가 나가는 세 길(문장 문제풀기, 90초 한 판, 일일공부)을 HTTP 로 부르고 채점한다.

    문장은 둘이다. 짧은 문장의 답은 --force 이고, UUID 가 여럿 든 긴 로그는
    후보 상한을 넘어 빈칸 후보에서 빠진다. 긴 로그 안에도 --force 가 있어서,
    상한이 안 먹으면 긴 로그가 지문으로 나갈 수 있다.
    """

    TEXT = "Run git push --force only on your own branch."
    PROMPT = "Run git push ____ only on your own branch."

    def setUp(self):
        cache.clear()
        for term in ["--force", "force", "zzfiller1", "zzfiller2", "zzfiller3", "zzfiller4"]:
            Word.objects.create(term=term, meaning=f"{term} 뜻", category="git", is_reviewed=True)
        self.short = Sentence.objects.create(
            text=self.TEXT, translation="해석", category="git", is_reviewed=True
        )
        uuids = " ".join(f"{i:08x}-1a2b-3c4d-5e6f-{i:012x}" for i in range(40))
        Sentence.objects.create(
            text=f"git push --force failed for ids {uuids}",
            translation="해석",
            category="git",
            is_reviewed=True,
        )
        self.answer_id = Word.objects.get(term="--force").pk

    def assert_blank(self, question: dict) -> None:
        self.assertEqual(question["kind"], QuizKind.BLANK)
        self.assertEqual(question["prompt"], self.PROMPT)
        self.assertIn(self.answer_id, [c["id"] for c in question["choices"]])

    def test_sentence_quiz_and_grade(self):
        for params in ({"kind": QuizKind.BLANK}, {"kind": QuizKind.BLANK, "item": self.short.pk}):
            for _ in range(5):
                with self.subTest(params=params):
                    res = self.client.get("/api/vocab/sentences/quiz/", params)
                    self.assertEqual(res.status_code, 200, res.content)
                    body = res.json()
                    self.assert_blank(body)
                    graded = self.client.post(
                        "/api/vocab/sentences/grade/",
                        {"token": body["token"], "picked": self.answer_id},
                        content_type="application/json",
                    )
                    self.assertEqual(graded.status_code, 200, graded.content)
                    self.assertTrue(graded.json()["correct"])
                    self.assertEqual(graded.json()["word"]["term"], "--force")

    def test_round_blank_and_answer(self):
        real_choice = random.choice

        def force_blank(seq):
            return QuizKind.BLANK if seq is QuizKind.ALL else real_choice(seq)

        with mock.patch.object(session.random, "choice", side_effect=force_blank):
            res = self.client.post("/api/learning/rounds/", {}, content_type="application/json")
            self.assertEqual(res.status_code, 201, res.content)
            body = res.json()
            self.assert_blank(body["question"])
            answered = self.client.post(
                "/api/learning/rounds/answer/",
                {"token": body["token"], "choice_id": self.answer_id},
                content_type="application/json",
            )
        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertTrue(answered.json()["result"]["correct"])
        self.assertEqual(answered.json()["result"]["answer_text"], "--force")

    def test_daily_blank_and_answer(self):
        seed_words()
        self.client.force_login(make_user("빈칸규모"))

        def blank_only(*_args, **_kwargs):
            return make_blank_question(Sentence.objects.visible(), Word.objects.visible())

        with mock.patch.object(daily_study, "make_question", side_effect=blank_only):
            res = self.client.post(
                "/api/learning/daily/", {"length": StudyLength.SHORT}, "application/json"
            )
            self.assertEqual(res.status_code, 201, res.content)
            body = res.json()
            self.assert_blank(body["question"])
            answered = self.client.post(
                "/api/learning/daily/answer/",
                {"token": body["token"], "choice_id": self.answer_id},
                content_type="application/json",
            )
        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertTrue(answered.json()["result"]["correct"])
