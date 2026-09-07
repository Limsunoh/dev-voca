"""mark_exam_scope / seed_exam_words 명령의 멱등성·dry-run·트랜잭션."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase

from apps.vocab.models import LearningItem, Word

Subject = LearningItem.ExamSubject


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out, stderr=StringIO())
    return out.getvalue()


class MarkExamScopeTest(TestCase):
    """표시 명령. 여러 번 돌려도 같은 결과여야 한다."""

    def setUp(self):
        # 목록에 있는 용어 몇 개만 심어둔다. DB 에 없는 것은 "없음" 으로
        # 보고되고 넘어가야 한다.
        self.deadlock = Word.objects.create(
            term="deadlock", meaning="교착 상태", is_reviewed=True
        )
        self.tcp = Word.objects.create(term="TCP", meaning="전송 제어 규약",
                                       is_reviewed=True)
        # 목록에 없는 단어. 표시가 붙으면 안 된다.
        self.outsider = Word.objects.create(term="zz-outsider", meaning="바깥",
                                            is_reviewed=True)

    def test_marks_known_terms_with_right_subject(self):
        run("mark_exam_scope")
        self.deadlock.refresh_from_db()
        self.tcp.refresh_from_db()
        self.assertTrue(self.deadlock.is_exam)
        self.assertEqual(self.deadlock.exam_subject, Subject.DATABASE)
        self.assertTrue(self.tcp.is_exam)
        self.assertEqual(self.tcp.exam_subject, Subject.SYSTEM)

    def test_does_not_touch_terms_outside_the_list(self):
        run("mark_exam_scope")
        self.outsider.refresh_from_db()
        self.assertFalse(self.outsider.is_exam)
        self.assertEqual(self.outsider.exam_subject, "")

    def test_dry_run_changes_nothing(self):
        out = run("mark_exam_scope", "--dry-run")
        self.deadlock.refresh_from_db()
        self.assertFalse(self.deadlock.is_exam)
        self.assertEqual(self.deadlock.exam_subject, "")
        self.assertIn("저장하지 않았습니다", out)

    def test_running_twice_is_idempotent(self):
        run("mark_exam_scope")
        first = list(
            Word.objects.filter(is_exam=True)
            .order_by("term")
            .values_list("term", "exam_subject")
        )
        second_out = run("mark_exam_scope")
        second = list(
            Word.objects.filter(is_exam=True)
            .order_by("term")
            .values_list("term", "exam_subject")
        )
        self.assertEqual(first, second)
        # 두 번째는 전부 "이미 표시돼 있음" 으로 빠져야 한다.
        self.assertIn("표시함: 0개", second_out)

    def test_does_not_erase_manual_marks(self):
        """Admin 에서 손으로 켠 것을 되돌리지 않는다(독스트링의 약속)."""
        self.outsider.is_exam = True
        self.outsider.exam_subject = Subject.DESIGN
        self.outsider.save()

        run("mark_exam_scope")

        self.outsider.refresh_from_db()
        self.assertTrue(self.outsider.is_exam)
        self.assertEqual(self.outsider.exam_subject, Subject.DESIGN)

    def test_does_not_flip_review_state(self):
        """표시를 다는 것이 검수 상태를 건드리면 안 된다."""
        unrev = Word.objects.create(term="deadlock-x", meaning="m")
        Word.objects.filter(pk=self.deadlock.pk).update(is_reviewed=False)
        run("mark_exam_scope")
        self.deadlock.refresh_from_db()
        unrev.refresh_from_db()
        self.assertFalse(self.deadlock.is_reviewed)
        self.assertFalse(unrev.is_reviewed)

    def test_reports_missing_terms(self):
        out = run("mark_exam_scope")
        # 심어둔 둘 말고는 전부 DB 에 없다.
        self.assertIn("DB 에 없는 단어", out)

    def test_rolls_back_on_midway_failure(self):
        """중간에 죽으면 절반만 표시된 상태로 남지 않는다(@transaction.atomic)."""
        real_save = Word.save
        calls = {"n": 0}

        def boom(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] > 1:
                raise DatabaseError("중간에 끊김")
            return real_save(self, *a, **kw)

        with patch.object(Word, "save", boom):
            with self.assertRaises(DatabaseError):
                call_command("mark_exam_scope", stdout=StringIO())

        # 하나라도 남아 있으면 롤백이 안 된 것이다.
        self.assertEqual(Word.objects.filter(is_exam=True).count(), 0)

    def test_marked_items_are_reachable_through_the_filter(self):
        """표시한 것이 실제로 정처기 필터에 잡히는지."""
        run("mark_exam_scope")
        res = self.client.get("/api/vocab/words/",
                              {"is_exam": "true", "exam_subject": "database"})
        self.assertIn("deadlock", [r["term"] for r in res.json()["results"]])


class SeedExamWordsTest(TestCase):
    """단어를 새로 채우는 명령."""

    def test_creates_words_as_reviewed_and_exam(self):
        run("seed_exam_words")
        created = Word.objects.filter(source="직접 작성")
        self.assertTrue(created.exists())
        for w in created:
            self.assertTrue(w.is_reviewed, msg=w.term)
            self.assertTrue(w.is_exam, msg=w.term)
            self.assertNotEqual(w.exam_subject, "", msg=w.term)

    def test_dry_run_creates_nothing(self):
        out = run("seed_exam_words", "--dry-run")
        self.assertEqual(Word.objects.count(), 0)
        self.assertIn("저장하지 않았습니다", out)

    def test_running_twice_creates_no_duplicates(self):
        run("seed_exam_words")
        first = Word.objects.count()
        out = run("seed_exam_words")
        self.assertEqual(Word.objects.count(), first)
        self.assertIn("추가: 0개", out)

    def test_does_not_overwrite_existing_word(self):
        """term 이 겹치면 건너뛴다 - 검수자가 고친 내용을 덮으면 안 된다."""
        from apps.vocab.management.commands.seed_exam_words import (
            EXAM_WORDS as SEED,
        )
        term = SEED[0][0]
        existing = Word.objects.create(
            term=term, meaning="검수자가 고친 뜻", is_reviewed=True
        )
        run("seed_exam_words")
        existing.refresh_from_db()
        self.assertEqual(existing.meaning, "검수자가 고친 뜻")

    def test_seeded_words_appear_in_exam_filter(self):
        run("seed_exam_words")
        res = self.client.get("/api/vocab/words/", {"is_exam": "true"})
        self.assertGreater(res.json()["count"], 0)

    def test_rolls_back_on_midway_failure(self):
        real_create = Word.objects.create
        calls = {"n": 0}

        def boom(*a, **kw):
            calls["n"] += 1
            if calls["n"] > 2:
                raise DatabaseError("중간에 끊김")
            return real_create(*a, **kw)

        with patch.object(Word.objects, "create", boom):
            with self.assertRaises(DatabaseError):
                call_command("seed_exam_words", stdout=StringIO())

        self.assertEqual(Word.objects.count(), 0)

    def test_no_seeded_word_violates_the_constraint(self):
        """심는 데이터 자체가 모순이면 DB 가 거절한다. 미리 확인."""
        run("seed_exam_words")
        self.assertEqual(
            Word.objects.filter(is_exam=False).exclude(exam_subject="").count(), 0
        )

    def test_subjects_are_all_valid_choices(self):
        run("seed_exam_words")
        valid = set(Subject.values)
        for w in Word.objects.filter(source="직접 작성"):
            self.assertIn(w.exam_subject, valid, msg=w.term)


class CommandsTogetherTest(TestCase):
    """두 명령을 이어서 - 실제 운영 순서다."""

    def test_seed_then_mark_is_stable(self):
        run("seed_exam_words")
        run("mark_exam_scope")
        before = list(
            Word.objects.order_by("term").values_list(
                "term", "is_exam", "exam_subject"
            )
        )
        # 순서를 바꿔 다시 돌려도 같아야 한다.
        run("mark_exam_scope")
        run("seed_exam_words")
        after = list(
            Word.objects.order_by("term").values_list(
                "term", "is_exam", "exam_subject"
            )
        )
        self.assertEqual(before, after)

    def test_no_orphan_rows_after_both(self):
        run("seed_exam_words")
        run("mark_exam_scope")
        self.assertEqual(
            Word.objects.filter(is_exam=False).exclude(exam_subject="").count(), 0
        )

    def test_everything_created_stays_hidden_if_unreviewed(self):
        """명령이 만든 것을 미검수로 바꾸면 목록에서 사라지는지."""
        run("seed_exam_words")
        w = Word.objects.filter(is_exam=True).first()
        Word.objects.filter(pk=w.pk).update(is_reviewed=False)
        res = self.client.get("/api/vocab/words/", {"is_exam": "true"})
        self.assertNotIn(w.term, [r["term"] for r in res.json()["results"]])
