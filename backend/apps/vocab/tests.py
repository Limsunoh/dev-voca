from django.db import IntegrityError
from django.test import TestCase

from .models import Word


class WordModelTest(TestCase):
    def test_defaults_are_unreviewed_and_normal(self):
        """AI 파이프라인 규칙: 새로 만든 단어는 검수 전 상태여야 한다."""
        word = Word.objects.create(term="deploy", meaning="배포하다")
        self.assertFalse(word.is_reviewed)
        self.assertEqual(word.difficulty, Word.Difficulty.NORMAL)

    def test_term_is_unique(self):
        Word.objects.create(term="commit", meaning="커밋하다")
        with self.assertRaises(IntegrityError):
            Word.objects.create(term="commit", meaning="중복 단어")

    def test_reviewed_filter_excludes_unreviewed(self):
        """사용자 노출 경로는 is_reviewed=True 만 봐야 한다."""
        Word.objects.create(term="merge", meaning="병합하다", is_reviewed=True)
        Word.objects.create(term="rebase", meaning="재배치하다")

        visible = Word.objects.filter(is_reviewed=True)

        self.assertEqual([w.term for w in visible], ["merge"])

    def test_str_shows_term_and_meaning(self):
        word = Word(term="refactor", meaning="리팩터링하다")
        self.assertEqual(str(word), "refactor (리팩터링하다)")
