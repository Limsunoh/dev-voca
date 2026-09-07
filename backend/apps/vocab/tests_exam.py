"""정처기 범위 표시.

분류(category)와 독립된 축이라 따로 확인한다 - 한 단어가 CS 기초이면서
정처기 4과목일 수 있고, 그 둘이 서로를 가리면 안 된다.
"""

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import LearningItem, Sentence, Word

Subject = LearningItem.ExamSubject
LIST_URL = "/api/vocab/words/"


class ExamFieldConstraintTest(TestCase):
    """DB 제약. choices 는 full_clean() 경로에서만 검사하므로 DB 가 막아야 한다."""

    def test_unknown_subject_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.create(
                term="x", meaning="t", is_exam=True, exam_subject="없는과목"
            )

    def test_subject_without_the_flag_is_rejected(self):
        """정처기가 아닌데 과목만 붙으면 어디에도 안 나오는 항목이 된다.

        화면은 is_exam 으로 거르므로 그런 항목은 목록에서 사라지는데,
        Admin 에서 보면 과목이 달려 있어 정처기인 줄 알게 된다.
        """
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.create(
                term="y", meaning="t", is_exam=False, exam_subject=Subject.DATABASE
            )

    def test_flag_without_a_subject_is_allowed(self):
        """과목을 아직 안 정한 정처기 항목은 있을 수 있다."""
        word = Word.objects.create(term="z", meaning="t", is_exam=True)

        self.assertTrue(word.is_exam)
        self.assertEqual(word.exam_subject, "")

    def test_sentences_have_the_same_constraints(self):
        """단어에만 걸고 문장을 빠뜨리면 한쪽으로 모순 상태가 들어온다."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.create(
                text="t", translation="t", is_exam=False, exam_subject=Subject.DESIGN
            )


class ExamFilterTest(TestCase):
    """목록 필터. 화면이 URL 로 좁히는 경로다."""

    @classmethod
    def setUpTestData(cls):
        Word.objects.create(
            term="deadlock",
            meaning="서로 기다리다 멈춤",
            category=LearningItem.Category.CS,
            is_exam=True,
            exam_subject=Subject.DATABASE,
            is_reviewed=True,
        )
        Word.objects.create(
            term="thread",
            meaning="실행 갈래",
            category=LearningItem.Category.CS,
            is_exam=True,
            exam_subject=Subject.LANGUAGE,
            is_reviewed=True,
        )
        Word.objects.create(
            term="rebase",
            meaning="옮겨 붙이기",
            category=LearningItem.Category.GIT,
            is_reviewed=True,
        )
        # 검수 안 된 정처기 단어. 게이트가 이 축에도 걸리는지 본다.
        Word.objects.create(
            term="hidden",
            meaning="숨김",
            is_exam=True,
            exam_subject=Subject.DESIGN,
            is_reviewed=False,
        )

    def terms(self, query: str = "") -> list[str]:
        res = self.client.get(f"{LIST_URL}{query}")
        self.assertEqual(res.status_code, 200)
        return [row["term"] for row in res.json()["results"]]

    def test_without_the_filter_everything_reviewed_shows(self):
        self.assertEqual(sorted(self.terms()), ["deadlock", "rebase", "thread"])

    def test_exam_only(self):
        self.assertEqual(sorted(self.terms("?is_exam=true")), ["deadlock", "thread"])

    def test_subject_narrows_further(self):
        self.assertEqual(self.terms("?exam_subject=database"), ["deadlock"])

    def test_unreviewed_exam_words_are_hidden(self):
        """검수 게이트는 정처기 축에도 그대로 걸린다."""
        self.assertNotIn("hidden", self.terms("?is_exam=true"))

    def test_unknown_subject_is_a_bad_request(self):
        """오래된 북마크나 오타. 서버 장애처럼 보이면 안 된다."""
        res = self.client.get(f"{LIST_URL}?exam_subject=없는것")

        self.assertEqual(res.status_code, 400)

    def test_category_and_exam_are_independent(self):
        """분류로 좁혀도 정처기 표시가 남는다.

        한 단어가 두 축에 다 속하므로, 분류를 걸었다고 정처기가
        사라지면 CS 기초를 보는 사람은 그게 시험 범위인지 모른다.
        """
        res = self.client.get(f"{LIST_URL}?category=cs&is_exam=true")

        terms = [row["term"] for row in res.json()["results"]]
        self.assertEqual(sorted(terms), ["deadlock", "thread"])

    def test_list_carries_the_subject_label(self):
        """카드가 배지를 그리려면 목록에 라벨이 있어야 한다."""
        res = self.client.get(f"{LIST_URL}?exam_subject=database")
        row = res.json()["results"][0]

        self.assertTrue(row["is_exam"])
        self.assertEqual(row["exam_subject"], "database")
        self.assertIn("3과목", row["exam_subject_label"])

    def test_subjects_endpoint_lists_five(self):
        res = self.client.get(f"{LIST_URL}exam_subjects/")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body), 5)
        self.assertEqual(body[0]["value"], "design")
        # 번호가 앞에 붙어야 수험생이 아는 순서와 맞춰볼 수 있다.
        self.assertTrue(body[0]["label"].startswith("1과목"))


class MarkExamScopeCommandTest(TestCase):
    """이미 있는 단어에 표시를 다는 명령."""

    def test_it_marks_a_known_term(self):
        Word.objects.create(term="TCP", meaning="순서대로 보내기", is_reviewed=True)

        call_command("mark_exam_scope", verbosity=0)

        word = Word.objects.get(term="TCP")
        self.assertTrue(word.is_exam)
        self.assertEqual(word.exam_subject, Subject.SYSTEM)

    def test_dry_run_saves_nothing(self):
        Word.objects.create(term="TCP", meaning="순서대로 보내기", is_reviewed=True)

        call_command("mark_exam_scope", dry_run=True, verbosity=0)

        self.assertFalse(Word.objects.get(term="TCP").is_exam)

    def test_running_twice_changes_nothing(self):
        """여러 번 돌려도 안전해야 한다 - 배포 때마다 도는 종류다."""
        Word.objects.create(term="TCP", meaning="순서대로 보내기", is_reviewed=True)

        call_command("mark_exam_scope", verbosity=0)
        before = Word.objects.get(term="TCP").updated_at
        call_command("mark_exam_scope", verbosity=0)

        self.assertEqual(Word.objects.get(term="TCP").updated_at, before)

    def test_it_does_not_touch_words_outside_the_list(self):
        """목록에 없는 단어의 표시를 지우지 않는다.

        Admin 에서 손으로 켠 것을 되돌리면 검수자의 판단을 덮어쓴다.
        """
        Word.objects.create(
            term="직접켠단어",
            meaning="t",
            is_exam=True,
            exam_subject=Subject.DESIGN,
            is_reviewed=True,
        )

        call_command("mark_exam_scope", verbosity=0)

        self.assertTrue(Word.objects.get(term="직접켠단어").is_exam)


class SeedExamWordsCommandTest(TestCase):
    """비어 있던 정처기 용어를 채우는 명령."""

    def test_it_creates_reviewed_words(self):
        """사람이 쓴 것이라 검수 대기를 거치지 않는다."""
        call_command("seed_exam_words", verbosity=0)

        word = Word.objects.get(term="pointer")
        self.assertTrue(word.is_reviewed)
        self.assertTrue(word.is_exam)
        self.assertEqual(word.exam_subject, Subject.LANGUAGE)

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_exam_words", verbosity=0)
        call_command("seed_exam_words", verbosity=0)

        self.assertEqual(Word.objects.filter(term="pointer").count(), 1)

    def test_every_seeded_word_has_a_subject(self):
        """과목 없이 들어가면 과목 필터로는 영영 안 나온다."""
        call_command("seed_exam_words", verbosity=0)

        without = Word.objects.filter(is_exam=True, exam_subject="")
        self.assertFalse(without.exists(), f"과목이 빈 것: {list(without)}")
