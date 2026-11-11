"""readings_word.json 이 단어 시드 네 묶음과 이름 하나까지 맞물리는지.

load_readings 는 term 으로 짝을 찾는다. 파일의 이름이 시드와 한 글자라도
다르면 그 줄은 조용히 건너뛰고, 시드에 있는데 파일에 없는 단어는 운영 DB 를
다시 만들 때 발음 없이 뜬다. 건수를 숫자로 박지 않고 시드와 맞대어 본다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.test import SimpleTestCase

from .management.commands import (
    seed_exam_words,
    seed_words,
    seed_words_launch,
    seed_words_more,
)
from .models import Word

WORD_FILE = Path(__file__).resolve().parent / "fixtures" / "readings_word.json"

# DEPLOY.md 의 단어 시드 순서.
SEEDS = (
    ("seed_words", seed_words.WORDS),
    ("seed_words_more", seed_words_more.WORDS),
    ("seed_words_launch", seed_words_launch.WORDS),
    ("seed_exam_words", seed_exam_words.EXAM_WORDS),
)


def seed_terms() -> list[str]:
    return [row[0] for _, rows in SEEDS for row in rows]


def file_rows() -> list[dict]:
    return json.loads(WORD_FILE.read_text(encoding="utf-8"))


class WordReadingFileMatchesSeedsTest(SimpleTestCase):
    def test_every_name_is_exactly_a_seed_term(self):
        """파일의 이름은 모두 시드 term 과 대소문자·공백까지 같다. 겹치지 않는다."""
        names = [r["term"] for r in file_rows()]
        self.assertEqual(len(names), len(set(names)))
        terms = set(seed_terms())
        self.assertEqual([n for n in names if n not in terms], [])

    def test_every_seed_term_has_a_reading(self):
        """시드 네 묶음의 단어가 빠짐없이 파일에 있다.

        새 단어를 시드에 더하면 발음도 여기에 더해야 한다. 안 그러면 DB 를
        다시 만들 때 그 단어만 발음 줄이 빈다.
        """
        names = {r["term"] for r in file_rows()}
        for seed, rows in SEEDS:
            with self.subTest(seed):
                self.assertEqual([row[0] for row in rows if row[0] not in names], [])
        self.assertEqual(len(file_rows()), len(set(seed_terms())))

    def test_query_family_reads_kwiri(self):
        """query 가 든 단어는 IPA 가 /kwɪri/, 한글 발음이 "퀴리" 계열로 같다."""
        ipa = {row[0]: row[1] for _, rows in SEEDS for row in rows}
        readings = {r["term"]: r["reading"] for r in file_rows()}
        family = [t for t in ipa if "query" in t.lower()]
        self.assertTrue(
            {"query", "slow query", "query string", "subquery", "media query"} <= set(family)
        )
        for term in family:
            with self.subTest(term):
                self.assertIn("kwɪri", ipa[term])
                self.assertNotIn("kwɛ", ipa[term])
                plain = readings[term].replace("**", "")
                self.assertIn("퀴리", plain)
                self.assertNotIn("퀘리", plain)

    def test_reading_fits_the_column(self):
        """한글 발음이 Word.reading 칸 길이를 넘지 않고 앞뒤 공백이 없다."""
        limit = Word._meta.get_field("reading").max_length
        for r in file_rows():
            with self.subTest(r["term"]):
                self.assertLessEqual(len(r["reading"]), limit)
                self.assertEqual(r["reading"], r["reading"].strip())
                self.assertIsNone(re.search(r"\s{2,}", r["reading"]))

    def test_cardinality_meaning_mentions_both_senses(self):
        """cardinality 는 정처기 뜻(행 수)을 먼저, 실무 뜻(값의 종류 수)을 함께 적는다."""
        row = next(row for row in seed_words.WORDS if row[0] == "cardinality")
        meaning, description = row[2], row[5]
        self.assertIn("행 수", meaning)
        self.assertIn("튜플", description)
        self.assertIn("degree", description)
