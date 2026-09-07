"""정처기 축의 검수 게이트·필터 조합·파라미터 남용."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.vocab.models import LearningItem, Sentence, Word

Subject = LearningItem.ExamSubject
WORDS = "/api/vocab/words/"
SENTS = "/api/vocab/sentences/"


def terms(res):
    return [row["term"] for row in res.json()["results"]]


class ExamReviewGateTest(TestCase):
    """미검수 정처기 항목이 사용자 경로로 새는지.

    이 프로젝트 최대 결함 유형이라 정처기가 붙은 모든 조회 경로를 훑는다.
    """

    @classmethod
    def setUpTestData(cls):
        # 미검수 정처기 단어. 어디에도 나오면 안 된다.
        cls.hidden = Word.objects.create(
            term="zz-hidden-exam", meaning="숨어야 하는 정처기 단어",
            is_exam=True, exam_subject=Subject.DATABASE, is_reviewed=False,
        )
        # 검수된 정처기 단어. 대조군.
        cls.shown = Word.objects.create(
            term="zz-shown-exam", meaning="보여야 하는 정처기 단어",
            is_exam=True, exam_subject=Subject.DATABASE, is_reviewed=True,
        )
        cls.hidden_sent = Sentence.objects.create(
            text="zz hidden exam sentence", translation="숨어야 함",
            is_exam=True, exam_subject=Subject.SYSTEM, is_reviewed=False,
        )

    def test_unreviewed_exam_word_absent_from_plain_list(self):
        res = self.client.get(WORDS, {})
        self.assertNotIn("zz-hidden-exam", terms(res))

    def test_unreviewed_exam_word_absent_from_exam_filter(self):
        """정처기 필터가 검수 필터를 덮어쓰지 않는가."""
        res = self.client.get(WORDS, {"is_exam": "true"})
        got = terms(res)
        self.assertNotIn("zz-hidden-exam", got)
        self.assertIn("zz-shown-exam", got)

    def test_unreviewed_exam_word_absent_from_subject_filter(self):
        res = self.client.get(
            WORDS, {"is_exam": "true", "exam_subject": "database"}
        )
        self.assertNotIn("zz-hidden-exam", terms(res))

    def test_unreviewed_exam_word_absent_from_subject_only_filter(self):
        """is_exam 없이 과목만 걸어도 마찬가지다."""
        res = self.client.get(WORDS, {"exam_subject": "database"})
        self.assertNotIn("zz-hidden-exam", terms(res))

    def test_unreviewed_exam_word_absent_from_search(self):
        res = self.client.get(WORDS, {"search": "zz-hidden-exam"})
        self.assertEqual(res.json()["count"], 0)

    def test_unreviewed_exam_word_absent_from_search_with_exam_filter(self):
        res = self.client.get(
            WORDS, {"search": "zz-hidden", "is_exam": "true"}
        )
        self.assertEqual(res.json()["count"], 0)

    def test_unreviewed_exam_word_detail_is_404(self):
        res = self.client.get(f"{WORDS}{self.hidden.pk}/")
        self.assertEqual(res.status_code, 404)

    def test_unreviewed_exam_word_hidden_under_shuffle(self):
        """섞기 시드를 바꿔가며 여러 번 - 정렬 경로가 게이트를 우회하는지."""
        for seed in ("a", "b", "seed3", "x" * 64):
            res = self.client.get(
                WORDS, {"is_exam": "true", "shuffle": seed}
            )
            self.assertNotIn("zz-hidden-exam", terms(res), msg=f"seed={seed}")

    def test_unreviewed_exam_word_hidden_across_ordering(self):
        for ordering in ("term", "-term", "created_at", "-difficulty"):
            res = self.client.get(
                WORDS,
                {"is_exam": "true", "ordering": ordering},
            )
            self.assertNotIn("zz-hidden-exam", terms(res), msg=ordering)

    def test_unreviewed_exam_word_hidden_across_all_pages(self):
        """페이지를 끝까지 넘겨도 안 나온다."""
        page = 1
        seen = []
        while page < 50:
            res = self.client.get(
                WORDS, {"is_exam": "true", "page": str(page)}
            )
            if res.status_code != 200:
                break
            body = res.json()
            seen += [r["term"] for r in body["results"]]
            if not body.get("next"):
                break
            page += 1
        self.assertNotIn("zz-hidden-exam", seen)
        self.assertIn("zz-shown-exam", seen)

    def test_unreviewed_exam_sentence_absent(self):
        res = self.client.get(SENTS, {"is_exam": "true"})
        texts = [r["text"] for r in res.json()["results"]]
        self.assertNotIn("zz hidden exam sentence", texts)

    def test_unreviewed_exam_sentence_detail_is_404(self):
        res = self.client.get(f"{SENTS}{self.hidden_sent.pk}/")
        self.assertEqual(res.status_code, 404)

    def test_exam_subjects_endpoint_leaks_no_content(self):
        """과목 목록은 정적 목록이라 콘텐츠가 실리면 안 된다."""
        res = self.client.get(f"{WORDS}exam_subjects/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([r["value"] for r in body],
                         [s.value for s in Subject])
        self.assertNotIn("zz-hidden-exam", res.content.decode())

    def test_quiz_never_serves_unreviewed_exam_word(self):
        """문제풀기 풀에도 안 들어간다. 30회 반복."""
        for _ in range(30):
            res = self.client.get(f"{WORDS}quiz/")
            if res.status_code != 200:
                continue
            self.assertNotIn("zz-hidden-exam", res.content.decode())

    def test_staff_sees_unreviewed_but_anonymous_does_not(self):
        """검수자에게만 보인다 - 게이트가 권한으로 갈리는지."""
        staff = get_user_model().objects.create_user(
            email="rev@example.com", password="pw", is_staff=True
        )
        self.client.force_login(staff)
        res = self.client.get(WORDS, {"is_exam": "true"})
        self.assertIn("zz-hidden-exam", terms(res))
        self.client.logout()
        res = self.client.get(WORDS, {"is_exam": "true"})
        self.assertNotIn("zz-hidden-exam", terms(res))


class ExamFilterCombinationTest(TestCase):
    """필터를 섞었을 때 조건이 서로를 잃는지."""

    @classmethod
    def setUpTestData(cls):
        mk = lambda **kw: Word.objects.create(is_reviewed=True, **kw)
        cls.a = mk(term="aa-db-hard", meaning="m", difficulty=3,
                   category=LearningItem.Category.CS,
                   is_exam=True, exam_subject=Subject.DATABASE)
        cls.b = mk(term="bb-db-easy", meaning="m", difficulty=1,
                   category=LearningItem.Category.CS,
                   is_exam=True, exam_subject=Subject.DATABASE)
        cls.c = mk(term="cc-sys-hard", meaning="m", difficulty=3,
                   category=LearningItem.Category.API,
                   is_exam=True, exam_subject=Subject.SYSTEM)
        cls.d = mk(term="dd-plain", meaning="m", difficulty=3,
                   category=LearningItem.Category.CS)

    def test_exam_and_subject_and_difficulty_all_apply(self):
        res = self.client.get(WORDS, {
            "is_exam": "true", "exam_subject": "database",
            "difficulty": "3",
        })
        self.assertEqual(terms(res), ["aa-db-hard"])

    def test_exam_and_category_intersect_not_replace(self):
        """분류와 정처기는 독립 축이다. 하나가 다른 하나를 덮으면 안 된다."""
        res = self.client.get(WORDS, {
            "is_exam": "true", "category": "api",
        })
        self.assertEqual(terms(res), ["cc-sys-hard"])

    def test_search_plus_exam_filter_intersect(self):
        res = self.client.get(WORDS, {
            "search": "db", "is_exam": "true",
        })
        self.assertEqual(sorted(terms(res)), ["aa-db-hard", "bb-db-easy"])

    def test_is_exam_false_excludes_exam_items(self):
        res = self.client.get(WORDS, {"is_exam": "false"})
        got = terms(res)
        self.assertIn("dd-plain", got)
        self.assertNotIn("aa-db-hard", got)

    # 페이지 크기는 settings 고정(PAGE_SIZE=20)이라 쿼리로 못 줄인다.
    # 2페이지를 만들려면 그만큼 채워야 한다.
    def _fill(self, n, tag, **kw):
        for i in range(n):
            Word.objects.create(
                term=f"fill-{tag}-{i:03}", meaning="m", is_reviewed=True, **kw
            )

    def test_filters_survive_page_two(self):
        """2페이지로 넘어가도 조건이 유지되는지. 방금 고친 자리다.

        1페이지가 꽉 차도록 정처기 database 를 25개 늘리고, 조건에 안 맞는
        항목도 25개 섞어둔다. 2페이지에 그 항목이 나오면 페이지를 넘길 때
        조건이 풀린 것이다.
        """
        self._fill(25, "db", is_exam=True, exam_subject=Subject.DATABASE)
        self._fill(25, "plain")

        p1 = self.client.get(WORDS, {
            "is_exam": "true", "exam_subject": "database", "page": "1",
        }).json()
        p2 = self.client.get(WORDS, {
            "is_exam": "true", "exam_subject": "database", "page": "2",
        }).json()

        # 27 = 셋업 2개 + 채운 25개. 조건에 안 맞는 것이 세어지면 안 된다.
        self.assertEqual(p1["count"], 27)
        self.assertEqual(p2["count"], 27)
        self.assertTrue(p2["results"])
        for row in p1["results"] + p2["results"]:
            self.assertTrue(row["is_exam"])
            self.assertEqual(row["exam_subject"], "database")

    def test_shuffle_keeps_exam_filter_and_partitions_pages(self):
        """섞어도 조건이 유지되고, 페이지가 겹치거나 빠지지 않는지."""
        self._fill(25, "db", is_exam=True, exam_subject=Subject.DATABASE)
        self._fill(25, "plain")

        seen = []
        for page in ("1", "2"):
            body = self.client.get(WORDS, {
                "is_exam": "true", "exam_subject": "database",
                "shuffle": "s1", "page": page,
            }).json()
            for row in body["results"]:
                self.assertTrue(row["is_exam"])
                self.assertEqual(row["exam_subject"], "database")
            seen += [r["term"] for r in body["results"]]

        # 같은 시드면 페이지가 겹치지 않아야 한다. 겹치면 어떤 항목은
        # 두 번 보이고 어떤 항목은 영영 안 보인다.
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), 27)

    def test_subject_filter_alone_still_gates_on_review(self):
        Word.objects.create(term="ee-unrev", meaning="m", is_exam=True,
                            exam_subject=Subject.DATABASE, is_reviewed=False)
        res = self.client.get(WORDS, {"exam_subject": "database"})
        self.assertNotIn("ee-unrev", terms(res))


class ExamParamAbuseTest(TestCase):
    """파라미터 남용. 500 이 나면 결함이다."""

    @classmethod
    def setUpTestData(cls):
        Word.objects.create(term="pp-exam", meaning="m", is_reviewed=True,
                            is_exam=True, exam_subject=Subject.DESIGN)

    def test_is_exam_junk_values_never_500(self):
        for value in ("yes", "on", "2", "abc", "", "null", "true;drop",
                      "TRUE", "False", "-1", "1.5", "x" * 5000, "０"):
            with self.subTest(value=value[:20]):
                res = self.client.get(WORDS, {"is_exam": value})
                self.assertLess(res.status_code, 500,
                                msg=f"is_exam={value[:40]} -> {res.status_code}")

    def test_exam_subject_junk_values_never_500(self):
        for value in ("nope", "DATABASE", "database ", " database",
                      "database'--", "' OR '1'='1", "%", "_", "x" * 5000,
                      "데이터베이스", "database,system", "[]", "{}"):
            with self.subTest(value=value[:20]):
                res = self.client.get(WORDS, {"exam_subject": value})
                self.assertLess(res.status_code, 500,
                                msg=f"exam_subject={value[:40]} -> {res.status_code}")

    def test_exam_subject_null_byte_never_500(self):
        res = self.client.get(WORDS, {"exam_subject": "database\x00"})
        self.assertLess(res.status_code, 500)

    def test_repeated_params_never_500(self):
        """같은 키를 여러 번. 배열로 들어오는 경우."""
        res = self.client.get(
            f"{WORDS}?is_exam=true&is_exam=false"
            "&exam_subject=database&exam_subject=system"
        )
        self.assertLess(res.status_code, 500)

    def test_sql_fragment_in_subject_does_not_leak_rows(self):
        """SQL 조각으로 필터를 무력화해 전체를 끌어오는지."""
        res = self.client.get(WORDS, {"exam_subject": "' OR '1'='1"})
        if res.status_code == 200:
            self.assertEqual(res.json()["count"], 0)

    def test_wildcard_in_subject_is_not_treated_as_pattern(self):
        """% 나 _ 가 LIKE 패턴으로 새면 전체가 나온다."""
        for value in ("%", "_", "d%", "%%"):
            res = self.client.get(WORDS, {"exam_subject": value})
            if res.status_code == 200:
                self.assertEqual(res.json()["count"], 0, msg=value)

    def test_pagination_bounds_with_exam_filter(self):
        for page in ("0", "-1", "999999", "abc", "2.7", "9" * 30):
            with self.subTest(page=page):
                res = self.client.get(WORDS, {"is_exam": "true", "page": page})
                self.assertLess(res.status_code, 500, msg=f"page={page}")

    def test_huge_page_size_with_exam_filter(self):
        for size in ("0", "-1", "999999", "abc"):
            res = self.client.get(WORDS, {"is_exam": "true", "page_size": size})
            self.assertLess(res.status_code, 500, msg=size)

    def test_bad_pk_on_detail_never_500(self):
        for pk in ("9" * 30, "abc", "-1", "0", "1.5", "%00"):
            with self.subTest(pk=pk):
                res = self.client.get(f"{WORDS}{pk}/")
                self.assertIn(res.status_code, (400, 404),
                              msg=f"pk={pk} -> {res.status_code}")

    def test_sentence_endpoint_same_abuse(self):
        for value in ("yes", "abc", "x" * 3000):
            res = self.client.get(SENTS, {"is_exam": value})
            self.assertLess(res.status_code, 500)
        for value in ("nope", "' OR '1'='1", "%"):
            res = self.client.get(SENTS, {"exam_subject": value})
            self.assertLess(res.status_code, 500)


class ExamSerializerFieldTest(TestCase):
    """목록·상세에 새 필드가 실제로 실리는지. 화면 배지가 이걸 본다."""

    @classmethod
    def setUpTestData(cls):
        cls.w = Word.objects.create(
            term="ser-exam", meaning="m", is_reviewed=True,
            is_exam=True, exam_subject=Subject.DATABASE,
        )
        cls.plain = Word.objects.create(
            term="ser-plain", meaning="m", is_reviewed=True,
        )

    def test_list_carries_exam_fields(self):
        res = self.client.get(WORDS, {"search": "ser-exam"})
        row = res.json()["results"][0]
        self.assertTrue(row["is_exam"])
        self.assertEqual(row["exam_subject"], "database")
        self.assertEqual(row["exam_subject_label"], "3과목 데이터베이스 구축")

    def test_detail_carries_exam_fields(self):
        row = self.client.get(f"{WORDS}{self.w.pk}/").json()
        self.assertTrue(row["is_exam"])
        self.assertEqual(row["exam_subject_label"], "3과목 데이터베이스 구축")

    def test_plain_item_has_empty_subject_label(self):
        """미분류는 빈 문자열이어야 한다. 화면이 이걸로 배지를 가른다."""
        row = self.client.get(f"{WORDS}{self.plain.pk}/").json()
        self.assertFalse(row["is_exam"])
        self.assertEqual(row["exam_subject"], "")
        self.assertEqual(row["exam_subject_label"], "")

    def test_exam_without_subject_label_is_empty(self):
        w = Word.objects.create(term="ser-nosub", meaning="m",
                                is_reviewed=True, is_exam=True)
        row = self.client.get(f"{WORDS}{w.pk}/").json()
        self.assertTrue(row["is_exam"])
        self.assertEqual(row["exam_subject_label"], "")

    def test_anonymous_cannot_write_exam_fields(self):
        """익명이 정처기 표시를 바꿀 수 있는지."""
        res = self.client.patch(
            f"{WORDS}{self.plain.pk}/",
            {"is_exam": True}, content_type="application/json",
        )
        self.assertIn(res.status_code, (401, 403))
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.is_exam)

    def test_normal_user_cannot_write_exam_fields(self):
        user = get_user_model().objects.create_user(
            email="plain@example.com", password="pw"
        )
        self.client.force_login(user)
        res = self.client.patch(
            f"{WORDS}{self.plain.pk}/",
            {"is_exam": True}, content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.is_exam)

    def test_staff_writing_orphan_subject_is_not_500(self):
        """검수자가 모순 조합을 보내면 400 이어야 한다. 500 이면 결함."""
        staff = get_user_model().objects.create_user(
            email="rev2@example.com", password="pw", is_staff=True
        )
        self.client.force_login(staff)
        res = self.client.patch(
            f"{WORDS}{self.plain.pk}/",
            {"is_exam": False, "exam_subject": "database"},
            content_type="application/json",
        )
        self.assertLess(res.status_code, 500,
                        msg=f"모순 조합 PATCH -> {res.status_code}")


class ExamScopeWriteValidationTest(TestCase):
    """모순 조합(is_exam=False + 과목)을 API 로 쓰려 할 때.

    DB 제약이 막아주지만, 그것만으로는 IntegrityError 가 그대로 올라와
    500 이 된다. 검수자가 Admin 이 아니라 API 로 고칠 때 밟는 자리라
    400 으로 돌려주는지 확인한다.

    실제로 이 자리에서 500 이 났었다 - 과목만 보내는 요청(아래
    subject_only)은 검수자가 가장 자연스럽게 할 법한 것인데도 터졌다.
    """

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            email="writer@example.com", password="pw", is_staff=True
        )
        self.client.force_login(self.staff)

    def _word(self, term, **kw):
        return Word.objects.create(term=term, meaning="m", is_reviewed=True, **kw)

    def assertBadRequest(self, res):
        self.assertEqual(
            res.status_code, 400, msg=f"기대 400, 받은 {res.status_code}"
        )

    def test_patch_with_both_fields_contradictory(self):
        w = self._word("wv-a")
        res = self.client.patch(
            f"{WORDS}{w.pk}/",
            {"is_exam": False, "exam_subject": "database"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_patch_subject_only_on_non_exam_item(self):
        """is_exam 을 안 보내고 과목만. 가장 밟기 쉬운 경로다."""
        w = self._word("wv-b")
        res = self.client.patch(
            f"{WORDS}{w.pk}/",
            {"exam_subject": "database"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_patch_turning_off_exam_while_subject_remains(self):
        """정처기만 끄면 과목이 남아 모순이 된다."""
        w = self._word("wv-c", is_exam=True, exam_subject=Subject.DATABASE)
        res = self.client.patch(
            f"{WORDS}{w.pk}/", {"is_exam": False}, content_type="application/json"
        )
        self.assertBadRequest(res)

    def test_create_with_contradictory_pair(self):
        res = self.client.post(
            WORDS,
            {"term": "wv-d", "meaning": "m", "is_exam": False,
             "exam_subject": "database"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_unknown_subject_is_rejected(self):
        w = self._word("wv-e")
        res = self.client.patch(
            f"{WORDS}{w.pk}/",
            {"is_exam": True, "exam_subject": "없는과목"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_valid_pair_still_works(self):
        """막는 김에 정상 경로까지 막으면 안 된다."""
        w = self._word("wv-f")
        res = self.client.patch(
            f"{WORDS}{w.pk}/",
            {"is_exam": True, "exam_subject": "database"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        w.refresh_from_db()
        self.assertTrue(w.is_exam)
        self.assertEqual(w.exam_subject, "database")

    def test_clearing_both_together_works(self):
        w = self._word("wv-g", is_exam=True, exam_subject=Subject.DATABASE)
        res = self.client.patch(
            f"{WORDS}{w.pk}/",
            {"is_exam": False, "exam_subject": ""},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        w.refresh_from_db()
        self.assertFalse(w.is_exam)
        self.assertEqual(w.exam_subject, "")

    def test_sentence_subject_only_is_rejected(self):
        """문장도 같은 규칙이다. 한쪽만 막으면 조용히 어긋난다."""
        s = Sentence.objects.create(text="sv a", translation="t",
                                    is_reviewed=True)
        res = self.client.patch(
            f"{SENTS}{s.pk}/",
            {"exam_subject": "database"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_sentence_create_contradictory_pair(self):
        res = self.client.post(
            SENTS,
            {"text": "sv b", "translation": "t", "is_exam": False,
             "exam_subject": "database"},
            content_type="application/json",
        )
        self.assertBadRequest(res)

    def test_no_orphan_row_exists_after_all_attempts(self):
        """위 시도들이 하나도 안 새어 들어갔는지 최종 확인."""
        for model in (Word, Sentence):
            self.assertEqual(
                model.objects.filter(is_exam=False)
                .exclude(exam_subject="")
                .count(),
                0,
                msg=model.__name__,
            )
