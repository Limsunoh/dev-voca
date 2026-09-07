"""제약 우회 탐색. update()/bulk_create/update_or_create/raw SQL/QuerySet.update 전부."""

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.vocab.models import LearningItem, Sentence, Word

Subject = LearningItem.ExamSubject


class ConstraintBypassTest(TestCase):
    """DB 제약을 우회하는 경로가 있는지. Word/Sentence 양쪽."""

    def _mk_word(self, **kw):
        base = dict(term="w-base", meaning="뜻", is_reviewed=True)
        base.update(kw)
        return Word.objects.create(**base)

    def _mk_sent(self, **kw):
        base = dict(text="s base", translation="번역", is_reviewed=True)
        base.update(kw)
        return Sentence.objects.create(**base)

    # ---- queryset.update() ----
    def test_word_update_cannot_orphan_subject(self):
        """update() 로 is_exam 만 False 로 내려 모순 상태를 만들 수 있는가."""
        w = self._mk_word(term="w1", is_exam=True, exam_subject=Subject.DATABASE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.filter(pk=w.pk).update(is_exam=False)

    def test_sentence_update_cannot_orphan_subject(self):
        s = self._mk_sent(text="s1", is_exam=True, exam_subject=Subject.DATABASE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.filter(pk=s.pk).update(is_exam=False)

    def test_word_update_cannot_set_unknown_subject(self):
        w = self._mk_word(term="w2", is_exam=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.filter(pk=w.pk).update(exam_subject="없는과목")

    def test_sentence_update_cannot_set_unknown_subject(self):
        s = self._mk_sent(text="s2", is_exam=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.filter(pk=s.pk).update(exam_subject="없는과목")

    def test_bulk_update_cannot_orphan_subject(self):
        w = self._mk_word(term="w3", is_exam=True, exam_subject=Subject.SYSTEM)
        w.is_exam = False
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.bulk_update([w], ["is_exam"])

    # ---- bulk_create ----
    def test_bulk_create_cannot_orphan_subject(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.bulk_create(
                [Word(term="bc1", meaning="m", is_exam=False,
                      exam_subject=Subject.DESIGN)]
            )

    def test_bulk_create_cannot_set_unknown_subject(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.bulk_create(
                [Word(term="bc2", meaning="m", is_exam=True, exam_subject="zz")]
            )

    def test_sentence_bulk_create_cannot_orphan_subject(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.bulk_create(
                [Sentence(text="bs1", translation="t", is_exam=False,
                          exam_subject=Subject.DESIGN)]
            )

    # ---- update_or_create / get_or_create ----
    def test_update_or_create_cannot_orphan_subject(self):
        self._mk_word(term="uoc", is_exam=True, exam_subject=Subject.DEVELOP)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.update_or_create(
                term="uoc", defaults={"is_exam": False}
            )

    def test_get_or_create_cannot_create_orphan(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.get_or_create(
                term="goc",
                defaults={"meaning": "m", "is_exam": False,
                          "exam_subject": Subject.DEVELOP},
            )

    # ---- 직접 save() ----
    def test_save_cannot_orphan_subject(self):
        w = self._mk_word(term="sv", is_exam=True, exam_subject=Subject.LANGUAGE)
        w.is_exam = False
        with self.assertRaises(IntegrityError), transaction.atomic():
            w.save()

    def test_save_update_fields_cannot_orphan_subject(self):
        """update_fields 로 한 칸만 저장해도 제약이 걸리는가."""
        w = self._mk_word(term="svu", is_exam=True, exam_subject=Subject.LANGUAGE)
        w.is_exam = False
        with self.assertRaises(IntegrityError), transaction.atomic():
            w.save(update_fields=["is_exam"])

    # ---- raw SQL ----
    def test_raw_sql_cannot_orphan_subject(self):
        """제약이 앱이 아니라 DB 에 있는지. raw SQL 이 최종 판정이다."""
        w = self._mk_word(term="raw1", is_exam=True, exam_subject=Subject.DESIGN)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE vocab_word SET is_exam = %s WHERE id = %s", [False, w.pk]
                )

    def test_raw_sql_cannot_set_unknown_subject(self):
        w = self._mk_word(term="raw2", is_exam=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE vocab_word SET exam_subject = %s WHERE id = %s",
                    ["없는과목", w.pk],
                )

    def test_raw_sql_sentence_cannot_orphan_subject(self):
        s = self._mk_sent(text="raws", is_exam=True, exam_subject=Subject.DESIGN)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE vocab_sentence SET is_exam = %s WHERE id = %s",
                    [False, s.pk],
                )

    def test_raw_sql_insert_orphan_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO vocab_word "
                    "(term, meaning, description, pronunciation, reading, example, "
                    " example_translation, difficulty, category, source, is_exam, "
                    " exam_subject, is_reviewed, reading_reviewed, created_at, updated_at) "
                    "VALUES (%s,%s,'','','','','',2,'cs','',%s,%s,%s,%s,"
                    "'2026-01-01 00:00:00','2026-01-01 00:00:00')",
                    ["rawins", "m", False, Subject.DESIGN, True, False],
                )

    # ---- 허용돼야 하는 것 ----
    def test_exam_without_subject_is_allowed(self):
        """과목 미분류 정처기는 허용. 이걸 막으면 표시를 못 단다."""
        w = self._mk_word(term="ok1", is_exam=True, exam_subject="")
        self.assertTrue(Word.objects.filter(pk=w.pk).exists())

    def test_plain_item_is_allowed(self):
        w = self._mk_word(term="ok2")
        self.assertFalse(w.is_exam)
        self.assertEqual(w.exam_subject, "")

    def test_turning_off_exam_with_subject_cleared_is_allowed(self):
        """둘을 함께 내리는 것은 정상 경로다."""
        w = self._mk_word(term="ok3", is_exam=True, exam_subject=Subject.DATABASE)
        Word.objects.filter(pk=w.pk).update(is_exam=False, exam_subject="")
        w.refresh_from_db()
        self.assertFalse(w.is_exam)
        self.assertEqual(w.exam_subject, "")

    def test_null_byte_in_subject_rejected(self):
        """널바이트가 섞인 과목. Postgres 는 NUL 을 저장 못 한다."""
        with self.assertRaises(Exception), transaction.atomic():
            Word.objects.create(
                term="nb", meaning="m", is_exam=True,
                exam_subject="database\x00",
            )

    def test_oversized_subject_rejected(self):
        """max_length=20 초과. 제약이든 길이든 조용히 잘리면 안 된다."""
        with self.assertRaises(Exception), transaction.atomic():
            Word.objects.create(
                term="os", meaning="m", is_exam=True, exam_subject="d" * 200
            )
