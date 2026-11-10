"""load_readings 가 번호가 아니라 이름으로 짝을 맞추는지.

단어는 term, 문장은 시드 키 slug 로 맞춘다. 운영 DB 를 다시 만들면 시드 순서에 따라
번호가 밀려서, 번호로 맞추면 엉뚱한 문장에 발음이 붙는다(2026-11 운영 DB 의 문장
200번이 로컬과 달랐다).
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from apps.vocab.models import Sentence, SentenceKind, Word


class LoadReadingsByNameTest(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Word.objects.create(term="cache", meaning="캐시", is_reviewed=True)
        self.queue = Word.objects.create(term="queue", meaning="큐", is_reviewed=True)
        self.sentence = Sentence.objects.create(
            slug="review-take-another-look",
            text="Could you take another look?",
            translation="다시 봐주시겠어요?",
            kind=SentenceKind.PHRASE,
            is_reviewed=True,
        )

    def load(self, rows: list, *args: str) -> str:
        path = Path(self.tmp.name) / "readings.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        out = StringIO()
        call_command("load_readings", str(path), *args, stdout=out)
        return out.getvalue()

    def test_word_is_matched_by_term(self):
        self.load([{"term": "queue", "reading": "**큐**"}])

        self.queue.refresh_from_db()
        self.assertEqual(self.queue.reading, "**큐**")

    def test_term_wins_over_a_stale_pk(self):
        """이름과 번호가 다르면 이름을 따른다. 번호는 DB 를 다시 만들면 밀린다."""
        self.load([{"term": "queue", "pk": self.cache.pk, "reading": "**큐**"}])

        self.cache.refresh_from_db()
        self.queue.refresh_from_db()
        self.assertEqual(self.cache.reading, "")
        self.assertEqual(self.queue.reading, "**큐**")

    def test_sentence_is_matched_by_slug(self):
        self.load(
            [{"slug": "review-take-another-look", "reading": "**쿧** 유"}],
            "--kind",
            "sentence",
        )

        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "**쿧** 유")

    def test_unknown_name_is_reported_and_skipped(self):
        out = self.load([{"term": "nope", "reading": "놉"}, {"term": "", "reading": "빈"}])

        self.assertIn("term=nope 를 찾지 못했습니다", out)
        self.assertIn("term= 를 찾지 못했습니다", out)
        self.assertIn("0개 채웠습니다", out)

    def test_name_of_the_wrong_type_does_not_crash(self):
        out = self.load([{"term": ["queue"], "reading": "리스트"}, {"term": 7, "reading": "숫자"}])

        self.assertIn("0개 채웠습니다", out)
        self.queue.refresh_from_db()
        self.assertEqual(self.queue.reading, "")

    def test_reviewed_reading_is_still_not_overwritten(self):
        Word.objects.filter(pk=self.queue.pk).update(reading="옛 발음", reading_reviewed=True)

        out = self.load([{"term": "queue", "reading": "새 발음"}])

        self.assertIn("term=queue 는 이미 검수됐습니다", out)
        self.queue.refresh_from_db()
        self.assertEqual(self.queue.reading, "옛 발음")

    def test_row_of_the_other_kind_does_not_fall_back_to_pk(self):
        """문장 줄을 단어로 넣으면(--kind 를 빠뜨림) 같은 번호의 단어에 붙지 않는다."""
        out = self.load([{"slug": "s1", "pk": self.queue.pk, "reading": "문장발음"}])

        self.assertIn("slug=s1 는 다른 종류의 줄입니다", out)
        self.queue.refresh_from_db()
        self.assertEqual(self.queue.reading, "")

        self.load(
            [{"term": "cache", "pk": self.sentence.pk, "reading": "**캐**sh"}],
            "--kind",
            "sentence",
        )
        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "")

    def test_name_repeated_in_the_file_is_skipped_either_way(self):
        """같은 이름이 둘이면 어느 쪽도 넣지 않는다. --reviewed 여부로 결과가 갈리면 안 된다."""
        rows = [{"term": "queue", "reading": "앞"}, {"term": "queue", "reading": "뒤"}]
        for args in ((), ("--reviewed",)):
            with self.subTest(args=args):
                out = self.load(rows, *args)

                self.assertIn("term=queue 가 파일에 두 번 이상 있습니다", out)
                self.queue.refresh_from_db()
                self.assertEqual(self.queue.reading, "")
