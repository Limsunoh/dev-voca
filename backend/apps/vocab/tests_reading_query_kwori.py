"""query 의 한글 발음을 "쿼리" 로 바꾼 것이 빈 DB 재구성 뒤 API 까지 가는지.

tests_reading_word_coverage 는 파일만 읽는다. tests_reading_rebuild 는 파일과
DB·API 의 reading 이 같은지만 보고 reading_note 는 안 본다. 여기서는 DEPLOY.md
순서로 시드하고 두 파일을 --reviewed 로 넣은 뒤, query 가 든 단어 다섯과 문장
둘을 상세 API 로 받아 "쿼리" 만 나오는지, slow query 의 설명이 바뀐 값인지 본다.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from apps.vocab.models import Sentence, Word
from apps.vocab.tests_reading_rebuild import RebuildMixin

QUERY_TERMS = ("query", "query string", "subquery", "media query", "slow query")
QUERY_SLUGS = ("db-add-index-suggestion", "cs-sql-injection-prevention")
OLD_FORMS = ("퀴리", "퀘리")
SLOW_QUERY_NOTE = "sl 은 s 뒤에 혀끝을 붙인 l 이 바로 이어진다."


def plain(text: str) -> str:
    return text.replace("**", "")


class QueryReadsKworiAfterRebuildTest(RebuildMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def assert_kwori(self, text: str, label: str) -> None:
        self.assertIn("쿼리", plain(text), label)
        for old in OLD_FORMS:
            self.assertNotIn(old, plain(text), label)

    def test_word_db_and_detail_api_read_kwori(self):
        """단어 다섯이 DB 와 상세 API 모두 "쿼리" 이고 검수 완료다."""
        for term in QUERY_TERMS:
            with self.subTest(term):
                word = Word.objects.get(term=term)
                self.assertTrue(word.is_reviewed)
                self.assertTrue(word.reading_reviewed)
                self.assert_kwori(word.reading, term)

                res = self.client.get(f"/api/vocab/words/{word.pk}/")
                self.assertEqual(res.status_code, 200)
                body = res.json()
                self.assert_kwori(body["reading"], term)
                for old in OLD_FORMS:
                    self.assertNotIn(old, plain(body["reading_note"]), term)

    def test_sentence_db_and_detail_api_read_kwori(self):
        """문장 둘이 DB 와 상세 API 모두 "쿼리" 다."""
        for slug in QUERY_SLUGS:
            with self.subTest(slug):
                sentence = Sentence.objects.get(slug=slug)
                self.assertTrue(sentence.is_reviewed)
                self.assertTrue(sentence.reading_reviewed)
                self.assert_kwori(sentence.reading, slug)

                res = self.client.get(f"/api/vocab/sentences/{sentence.pk}/")
                self.assertEqual(res.status_code, 200)
                self.assert_kwori(res.json()["reading"], slug)

    def test_slow_query_note_dropped_the_kwiri_sentence(self):
        """slow query 의 설명은 sl 문장만 남고, DB 와 API 가 그 값이다."""
        word = Word.objects.get(term="slow query")
        self.assertEqual(word.reading_note, SLOW_QUERY_NOTE)
        res = self.client.get(f"/api/vocab/words/{word.pk}/")
        self.assertEqual(res.json()["reading_note"], SLOW_QUERY_NOTE)

    def test_no_reviewed_reading_anywhere_keeps_old_form(self):
        """재구성한 DB 어디에도 "퀴리"·"퀘리" 발음이나 설명이 남지 않는다."""
        for old in OLD_FORMS:
            for raw in (old, f"**{old[0]}**{old[1:]}"):
                with self.subTest(raw):
                    self.assertFalse(Word.objects.filter(reading__contains=raw).exists())
                    self.assertFalse(Word.objects.filter(reading_note__contains=raw).exists())
                    self.assertFalse(Sentence.objects.filter(reading__contains=raw).exists())
