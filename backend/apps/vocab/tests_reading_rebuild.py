"""운영 DB 를 다시 만드는 절차(DEPLOY.md)대로 돌렸을 때 발음이 제자리에 붙는지.

tests_reading_keys 는 dry-run 건수만 본다. 여기서는 실제로 저장한 뒤 행마다
파일의 발음과 같은지, API 가 그것을 내보내는지, 시드 순서를 바꿔 번호가
밀려도 같은지, 다시 돌려도 검수된 것을 안 덮는지, 손으로 만든 파일의 이상한
줄이 엉뚱한 행에 붙지 않는지를 본다.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.vocab.models import Sentence, SentenceKind, Word

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WORD_FILE = FIXTURES / "readings_word.json"
SENTENCE_FILE = FIXTURES / "readings_sentence.json"

# DEPLOY.md "방법 1" 의 시드 순서. 발음과 무관한 seed_phrases 는 뺐다.
DEPLOY_ORDER = (
    "seed_words",
    "seed_words_more",
    "seed_words_launch",
    "seed_exam_words",
    "seed_word_aliases",
    "seed_sentences",
    "seed_sentences_more",
    "mark_exam_scope",
)


def run(command: str, *args: str) -> str:
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


def rows_of(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


class RebuildMixin:
    """시드 → dry-run → --reviewed 저장까지 DEPLOY.md 그대로 돌린다."""

    seed_order: tuple[str, ...] = DEPLOY_ORDER

    @classmethod
    def setUpTestData(cls):
        for command in cls.seed_order:
            run(command)
        cls.word_rows = rows_of(WORD_FILE)
        cls.sentence_rows = rows_of(SENTENCE_FILE)
        cls.dry_word = run("load_readings", str(WORD_FILE), "--dry-run")
        cls.dry_sentence = run(
            "load_readings", str(SENTENCE_FILE), "--kind", "sentence", "--dry-run"
        )
        cls.real_word = run("load_readings", str(WORD_FILE), "--reviewed")
        cls.real_sentence = run(
            "load_readings", str(SENTENCE_FILE), "--kind", "sentence", "--reviewed"
        )

    def assert_every_row_has_its_reading(self):
        """단어는 term, 문장은 slug 로 찾아 파일의 발음과 글자 하나까지 같다."""
        words = {w.term: w for w in Word.objects.all()}
        for row in self.word_rows:
            word = words[row["term"]]
            self.assertEqual(
                (word.reading, word.reading_reviewed), (row["reading"], True), row["term"]
            )

        sentences = {s.slug: s for s in Sentence.objects.exclude(slug="")}
        for row in self.sentence_rows:
            sentence = sentences[row["slug"]]
            self.assertEqual(
                (sentence.reading, sentence.reading_reviewed), (row["reading"], True), row["slug"]
            )

    def assert_nothing_else_got_a_reading(self):
        """파일에 없는 행에는 발음이 안 붙는다. 번호로 맞추면 여기가 깨진다."""
        named = {r["term"] for r in self.word_rows}
        self.assertFalse(Word.objects.exclude(term__in=named).exclude(reading="").exists())
        slugs = {r["slug"] for r in self.sentence_rows}
        self.assertFalse(Sentence.objects.exclude(slug__in=slugs).exclude(reading="").exists())


class DeployOrderRebuildTest(RebuildMixin, TestCase):
    def test_dry_run_fills_every_row_of_the_files(self):
        """dry-run 이 파일의 항목 수만큼 채운다고 알린다. 건수는 고정하지 않는다 -
        발음을 새로 적을 때마다 늘어난다(tests_reading_fixtures 와 같은 이유)."""
        self.assertIn(
            f"저장하면 {len(self.word_rows)}개가 채워지고 0개는 건너뜁니다", self.dry_word
        )
        self.assertIn(
            f"저장하면 {len(self.sentence_rows)}개가 채워지고 0개는 건너뜁니다", self.dry_sentence
        )

    def test_real_load_fills_every_row(self):
        self.assertIn(f"{len(self.word_rows)}개 채웠습니다. (0개 건너뜀)", self.real_word)
        self.assertIn(f"{len(self.sentence_rows)}개 채웠습니다. (0개 건너뜀)", self.real_sentence)
        self.assert_every_row_has_its_reading()
        self.assert_nothing_else_got_a_reading()

    def test_api_detail_shows_the_file_reading(self):
        """게스트가 상세 API 로 보는 발음이 파일과 같다. 검수 안 된 항목은 404."""
        client = APIClient()
        for row in self.word_rows:
            word = Word.objects.get(term=row["term"])
            res = client.get(f"/api/vocab/words/{word.pk}/")
            if not word.is_reviewed:
                self.assertEqual(res.status_code, 404, row["term"])
                continue
            self.assertEqual(res.status_code, 200, row["term"])
            self.assertEqual(res.json()["reading"], row["reading"], row["term"])

        for row in self.sentence_rows:
            sentence = Sentence.objects.get(slug=row["slug"])
            res = client.get(f"/api/vocab/sentences/{sentence.pk}/")
            if not sentence.is_reviewed:
                self.assertEqual(res.status_code, 404, row["slug"])
                continue
            self.assertEqual(res.status_code, 200, row["slug"])
            self.assertEqual(res.json()["reading"], row["reading"], row["slug"])

    def test_rerun_does_not_overwrite_reviewed_readings(self):
        """두 번째 실행은 전부 "이미 검수됐습니다" 로 건너뛰고, 고친 발음을 안 덮는다."""
        Word.objects.filter(term="commit").update(reading="사람이 고친 발음")
        Sentence.objects.filter(slug="review-rebase-request").update(
            reading="사람이 고친 문장 발음"
        )

        word_out = run("load_readings", str(WORD_FILE), "--reviewed")
        sentence_out = run("load_readings", str(SENTENCE_FILE), "--kind", "sentence", "--reviewed")

        self.assertIn(f"0개 채웠습니다. ({len(self.word_rows)}개 건너뜀)", word_out)
        self.assertEqual(word_out.count("이미 검수됐습니다"), len(self.word_rows))
        self.assertIn("term=commit 는 이미 검수됐습니다", word_out)
        self.assertIn(f"0개 채웠습니다. ({len(self.sentence_rows)}개 건너뜀)", sentence_out)
        self.assertEqual(sentence_out.count("이미 검수됐습니다"), len(self.sentence_rows))
        self.assertEqual(Word.objects.get(term="commit").reading, "사람이 고친 발음")
        self.assertEqual(
            Sentence.objects.get(slug="review-rebase-request").reading, "사람이 고친 문장 발음"
        )


class ShuffledSeedOrderRebuildTest(RebuildMixin, TestCase):
    """문장 먼저, seed_sentences_more 를 seed_sentences 앞에. 번호가 밀린다."""

    seed_order = (
        "seed_sentences_more",
        "seed_sentences",
        "seed_exam_words",
        "seed_words_launch",
        "seed_words_more",
        "seed_words",
        "seed_word_aliases",
        "mark_exam_scope",
    )

    def test_pks_really_shifted(self):
        """순서를 바꾼 게 실제로 번호를 바꿨는지. 안 바뀌면 이 클래스는 아무것도 못 본다."""
        first_word = Word.objects.order_by("pk").first()
        first_sentence = Sentence.objects.order_by("pk").first()
        self.assertNotEqual(first_word.term, self.word_rows[0]["term"])
        self.assertNotEqual(first_sentence.slug, self.sentence_rows[0]["slug"])

    def test_readings_still_land_by_name(self):
        self.assertIn(f"{len(self.word_rows)}개 채웠습니다. (0개 건너뜀)", self.real_word)
        self.assertIn(f"{len(self.sentence_rows)}개 채웠습니다. (0개 건너뜀)", self.real_sentence)
        self.assert_every_row_has_its_reading()
        self.assert_nothing_else_got_a_reading()


class UnreviewedLoadGateTest(TestCase):
    """--reviewed 없이 넣은 발음은 API 에 안 나온다. 항목이 검수됐어도 마찬가지다."""

    def test_unreviewed_reading_is_hidden_in_detail_and_list(self):
        word = Word.objects.create(term="cache", meaning="캐시", is_reviewed=True)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(
                json.dumps([{"term": "cache", "reading": "**캐**sh"}]), encoding="utf-8"
            )
            run("load_readings", str(path))

        word.refresh_from_db()
        self.assertEqual((word.reading, word.reading_reviewed), ("**캐**sh", False))
        client = APIClient()
        self.assertEqual(client.get(f"/api/vocab/words/{word.pk}/").json()["reading"], "")
        listed = client.get("/api/vocab/words/").json()
        items = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual([i.get("reading", "") for i in items if i["id"] == word.pk], [""])


class HostileReadingFileTest(TestCase):
    """손으로 만든 파일의 이상한 줄이 엉뚱한 행에 붙지 않는다."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Word.objects.create(term="cache", meaning="캐시", is_reviewed=True)
        self.queue = Word.objects.create(term="queue", meaning="큐", is_reviewed=True)
        self.seeded = Sentence.objects.create(
            slug="seeded-one",
            text="Seeded.",
            translation="시드",
            kind=SentenceKind.PHRASE,
            is_reviewed=True,
        )
        self.manual = Sentence.objects.create(
            slug="",
            text="Typed in Admin.",
            translation="관리자가 넣음",
            kind=SentenceKind.PHRASE,
            is_reviewed=True,
        )

    def load(self, rows: list, *args: str) -> str:
        path = Path(self.tmp.name) / "readings.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return run("load_readings", str(path), *args)

    def readings(self) -> list[str]:
        words = list(Word.objects.order_by("pk").values_list("reading", flat=True))
        sentences = list(Sentence.objects.order_by("pk").values_list("reading", flat=True))
        return words + sentences

    def test_unknown_term_does_not_fall_back_to_pk(self):
        """이름이 DB 에 없으면 pk 가 맞아도 붙이지 않는다."""
        out = self.load([{"term": "nope", "pk": self.cache.pk, "reading": "놉"}])

        self.assertIn("term=nope 를 찾지 못했습니다", out)
        self.assertEqual(self.readings(), ["", "", "", ""])

    def test_null_or_empty_slug_does_not_fall_back_to_pk(self):
        out = self.load(
            [
                {"slug": "", "pk": self.manual.pk, "reading": "빈"},
                {"slug": None, "pk": self.seeded.pk, "reading": "널"},
            ],
            "--kind",
            "sentence",
        )

        self.assertIn("0개 채웠습니다", out)
        self.assertEqual(self.readings(), ["", "", "", ""])

    def test_admin_sentence_without_slug_is_reachable_by_pk(self):
        """Admin 에서 넣어 slug 가 빈 문장은 slug 칸 없이 pk 로만 적으면 붙는다."""
        out = self.load([{"pk": self.manual.pk, "reading": "**타잎t** 인"}], "--kind", "sentence")

        self.assertIn("1개 채웠습니다", out)
        self.manual.refresh_from_db()
        self.assertEqual(self.manual.reading, "**타잎t** 인")

    def test_word_file_with_kind_sentence_fills_nothing(self):
        """단어 파일을 --kind sentence 로 돌려도 문장에 아무것도 안 붙는다."""
        out = self.load(
            [{"term": "cache", "reading": "**캐**sh"}, {"term": "queue", "reading": "**큐**"}],
            "--kind",
            "sentence",
        )

        self.assertIn("0개 채웠습니다. (2개 건너뜀)", out)
        self.assertEqual(self.readings(), ["", "", "", ""])

    def test_sentence_file_without_kind_fills_nothing(self):
        """--kind 를 빠뜨리면(기본 word) 문장 파일이 단어에 안 붙는다."""
        out = self.load([{"slug": "seeded-one", "reading": "씨딛"}])

        self.assertIn("0개 채웠습니다. (1개 건너뜀)", out)
        self.assertEqual(self.readings(), ["", "", "", ""])

    def test_term_in_different_case_is_not_matched(self):
        """대소문자가 다르면 다른 단어다. term 은 대소문자를 구분해 unique 다."""
        out = self.load(
            [{"term": "Cache", "reading": "대문자"}, {"term": "QUEUE", "reading": "큐"}]
        )

        self.assertIn("term=Cache 를 찾지 못했습니다", out)
        self.assertIn("term=QUEUE 를 찾지 못했습니다", out)
        self.assertEqual(self.readings(), ["", "", "", ""])

    def test_bool_and_float_pk_do_not_hit_pk_one(self):
        """true 와 1.0 은 pk 1 과 같은 dict 자리를 집는다. 정수만 받는다."""
        out = self.load(
            [{"pk": True, "reading": "참"}, {"pk": float(self.cache.pk), "reading": "실수"}]
        )

        self.assertIn("0개 채웠습니다", out)
        self.assertEqual(self.readings(), ["", "", "", ""])
