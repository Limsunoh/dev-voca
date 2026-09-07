"""문장 도메인 테스트.

단어와 규칙이 같아 보이지만, 같은 규칙이 문장에도 실제로 걸리는지는
따로 확인해야 한다. 뷰를 공용 베이스로 묶었기 때문에 한쪽만 깨지는
경우는 줄었지만, 시리얼라이저와 모델 제약은 도메인마다 따로 있다.
"""

from collections import Counter
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .management.commands.seed_sentences import RETIRED_SLUGS, SENTENCES
from .management.commands.seed_sentences_more import SENTENCES as MORE_SENTENCES
from .models import Sentence, SentenceKind, Word

# 저장소에 박힌 문장 전부. 전수 검사는 이걸 돈다.
#
# **seed 명령이 늘면 여기에 한 덩이를 더한다.** 단어 쪽 tests.py 의
# ALL_SEEDED 와 같은 이유다 - 명령마다 자기 리스트를 갖고 있어서, 안 넣으면
# 그 명령의 문장은 검사를 통째로 건너뛴다. is_reviewed=True 로 바로 들어가는
# 통로라 아무도 안 본 데이터가 그대로 화면에 뜬다.
#
# 두 리스트의 열 순서는 같다(slug, text, translation, kind, category,
# difficulty, context, description). 그래도 위치로 쓰지 않고 이름을 붙이는
# 것은 다음 덩이를 더할 때 순서가 갈릴 수 있어서다.
ALL_SEEDED_SENTENCES: list[dict] = [
    {
        "slug": r[0],
        "text": r[1],
        "translation": r[2],
        "kind": r[3],
        "category": r[4],
        "difficulty": r[5],
        "context": r[6],
        "description": r[7],
    }
    for r in list(SENTENCES) + list(MORE_SENTENCES)
]

LIST_URL = "/api/vocab/sentences/"
QUIZ_URL = f"{LIST_URL}quiz/"
GRADE_URL = f"{LIST_URL}grade/"
WORD_GRADE_URL = "/api/vocab/words/grade/"


class SentenceModelTest(TestCase):
    def test_str_truncates_long_text(self):
        """Admin 목록이 읽히도록 앞부분만 보여준다."""
        long_text = "a" * 100
        s = Sentence(text=long_text, translation="해석", kind=SentenceKind.ERROR)

        self.assertIn("에러 메시지", str(s))
        self.assertIn("...", str(s))
        self.assertLess(len(str(s)), len(long_text))

    def test_visible_hides_unreviewed(self):
        """검수 게이트 헬퍼가 문장에도 그대로 걸린다."""
        Sentence.objects.create(text="보임", translation="t", is_reviewed=True)
        Sentence.objects.create(text="숨김", translation="t", is_reviewed=False)

        visible = list(Sentence.objects.visible().values_list("text", flat=True))

        self.assertEqual(visible, ["보임"])

    def test_db_rejects_kind_outside_choices(self):
        """choices 는 full_clean() 경로에서만 검사하므로 DB 가 막아야 한다."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.create(text="x", translation="t", kind="unknown")

    def test_db_rejects_category_outside_choices(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sentence.objects.create(text="y", translation="t", category="testing")

    def test_same_text_can_repeat(self):
        """문장은 unique 가 아니다. 같은 표현이 다른 상황에서 나올 수 있다."""
        Sentence.objects.create(text="Looks good.", translation="좋아 보여요", context="리뷰")
        Sentence.objects.create(text="Looks good.", translation="좋아 보여요", context="배포 확인")

        self.assertEqual(Sentence.objects.filter(text="Looks good.").count(), 2)


class SeedSentencesTest(TestCase):
    def run_seed(self, *args: str) -> str:
        out = StringIO()
        call_command("seed_sentences", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_seeds_as_reviewed(self):
        """시드는 코드 리뷰를 거치므로 검수 완료로 들어간다."""
        self.run_seed()

        self.assertEqual(Sentence.objects.count(), len(SENTENCES))
        self.assertEqual(Sentence.objects.visible().count(), len(SENTENCES))

    def test_is_idempotent(self):
        self.run_seed()
        self.run_seed()

        self.assertEqual(Sentence.objects.count(), len(SENTENCES))

    def test_removes_retired_sentences(self):
        """목록에서 뺀 문장은 DB 에서도 지워야 한다.

        시드는 추가와 갱신만 하므로, 소스에서 지우기만 하면 이미 배포된
        DB 에는 그대로 남아 사용자에게 계속 보인다. 테스트는 빈 DB 에서
        시작해서 이 경로를 못 잡으므로 옛 항목을 일부러 넣고 확인한다.
        """
        retired = RETIRED_SLUGS[0]
        Sentence.objects.create(
            slug=retired,
            text="옛 문장",
            translation="옛 해석",
            kind=SentenceKind.ERROR,
            category=Sentence.Category.API,
            is_reviewed=True,
        )

        self.run_seed()

        self.assertFalse(Sentence.objects.filter(slug=retired).exists())
        self.assertEqual(Sentence.objects.count(), len(SENTENCES))

    def test_does_not_overwrite_without_reset(self):
        slug, text = SENTENCES[0][0], SENTENCES[0][1]
        Sentence.objects.create(
            slug=slug, text=text, translation="내가 고친 해석", is_reviewed=True
        )

        self.run_seed()

        self.assertEqual(
            Sentence.objects.get(slug=slug).translation, "내가 고친 해석"
        )

    def test_reset_does_not_promote_pending_review(self):
        """검수 대기 문장을 덮어쓰면 아무도 승인 안 한 내용이 노출된다."""
        slug, text = SENTENCES[0][0], SENTENCES[0][1]
        Sentence.objects.create(
            slug=slug, text=text, translation="AI 가 만든 해석",
            is_reviewed=False, source="AI 생성",
        )

        output = self.run_seed("--reset")

        s = Sentence.objects.get(slug=slug)
        self.assertFalse(s.is_reviewed, "검수 대기 문장이 승격됐다")
        self.assertEqual(s.translation, "AI 가 만든 해석", "내용까지 덮어썼다")
        self.assertIn("건너뛴", output)

    def test_force_pending_overwrites_explicitly(self):
        slug, text = SENTENCES[0][0], SENTENCES[0][1]
        Sentence.objects.create(
            slug=slug, text=text, translation="AI 가 만든 해석", is_reviewed=False
        )

        self.run_seed("--reset", "--force-pending")

        s = Sentence.objects.get(slug=slug)
        self.assertTrue(s.is_reviewed)
        self.assertNotEqual(s.translation, "AI 가 만든 해석")

    def test_reset_survives_duplicate_text(self):
        """같은 문장이 다른 상황으로 하나 더 있어도 --reset 이 터지지 않는다.

        모델이 text 중복을 일부러 허용한다. text 를 키로 쓰면 여기서
        MultipleObjectsReturned 로 크래시한다.
        """
        self.run_seed()
        text = SENTENCES[0][1]
        Sentence.objects.create(text=text, translation="다른 상황", is_reviewed=True)

        self.run_seed("--reset")

        self.assertEqual(Sentence.objects.filter(text=text).count(), 2)

    def test_force_pending_alone_is_rejected(self):
        """--reset 없는 --force-pending 은 뜻이 없으므로 조용히 넘어가지 않는다."""
        with self.assertRaises(CommandError):
            self.run_seed("--force-pending")

        self.assertEqual(Sentence.objects.count(), 0)

    def test_partial_failure_saves_nothing(self):
        """중간에 터지면 앞서 넣은 것까지 전부 롤백한다."""
        from unittest.mock import patch

        real_save = Sentence.save
        calls = {"n": 0}

        def fail_on_third(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("중간 실패")
            return real_save(self, *args, **kwargs)

        with patch.object(Sentence, "save", fail_on_third):
            with self.assertRaises(RuntimeError):
                self.run_seed()

        self.assertEqual(Sentence.objects.count(), 0, "앞의 2개가 남았다")

    def test_data_quality(self):
        """빠진 필드나 잘못된 값이 없어야 한다."""
        context_max = Sentence._meta.get_field("context").max_length
        slug_max = Sentence._meta.get_field("slug").max_length
        valid_kinds = set(SentenceKind.values)
        valid_categories = set(Sentence.Category.values)
        valid_difficulties = set(Sentence.Difficulty.values)

        for row in ALL_SEEDED_SENTENCES:
            slug, text, translation = row["slug"], row["text"], row["translation"]
            kind, category, difficulty = row["kind"], row["category"], row["difficulty"]
            context, desc = row["context"], row["description"]
            with self.subTest(slug=slug):
                self.assertTrue(slug.strip(), "slug 가 비었다")
                self.assertLessEqual(len(slug), slug_max)
                self.assertTrue(text.strip(), "문장이 비었다")
                self.assertTrue(translation.strip(), "해석이 비었다")
                self.assertTrue(desc.strip(), "설명이 비었다")
                self.assertIn(kind, valid_kinds)
                self.assertIn(category, valid_categories)
                self.assertIn(difficulty, valid_difficulties)
                self.assertLessEqual(len(context), context_max)

    def test_slugs_are_unique(self):
        """중복되면 뒤 항목이 앞 항목을 덮어써 문장이 조용히 사라진다."""
        slugs = [row["slug"] for row in ALL_SEEDED_SENTENCES]

        self.assertEqual(len(slugs), len(set(slugs)))

    def test_has_both_kinds(self):
        """실무 표현과 에러 메시지가 둘 다 있어야 kind 필터가 의미를 가진다."""
        kinds = {row["kind"] for row in ALL_SEEDED_SENTENCES}

        self.assertEqual(kinds, set(SentenceKind.values))

    def test_every_category_can_fill_a_quiz(self):
        """분류를 좁혀도 4지선다를 만들 수 있어야 한다.

        단어 쪽 문제풀기가 보기 넷을 같은 분류에서 뽑는다. 문장에도
        같은 방식을 쓸 텐데, 분류 하나에 셋 이하면 문제를 못 만든다.
        """
        counts = Counter(row["category"] for row in ALL_SEEDED_SENTENCES)

        for category in Sentence.Category.values:
            with self.subTest(category=category):
                self.assertGreaterEqual(
                    counts[category], 4, f"{category} 분류가 4개 미만이다"
                )


class SentenceAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.visible = Sentence.objects.create(
            text="Could you take another look?",
            translation="다시 봐주시겠어요?",
            kind=SentenceKind.PHRASE,
            category=Sentence.Category.REVIEW,
            context="리뷰 요청",
            is_reviewed=True,
        )
        cls.hidden = Sentence.objects.create(
            text="secret-pending-sentence",
            translation="미검수",
            kind=SentenceKind.ERROR,
            is_reviewed=False,
        )
        cls.staff = get_user_model().objects.create_user(
            email="reviewer@example.com", password="x", is_staff=True
        )

    def test_list_hides_unreviewed(self):
        res = self.client.get(LIST_URL)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 1)
        self.assertNotIn("secret-pending-sentence", res.content.decode())

    def test_detail_of_unreviewed_is_404(self):
        """숨긴 문장은 id 를 알아도 못 본다."""
        res = self.client.get(f"{LIST_URL}{self.hidden.pk}/")

        self.assertEqual(res.status_code, 404)

    def test_staff_sees_pending(self):
        self.client.force_login(self.staff)

        res = self.client.get(LIST_URL)

        self.assertEqual(res.json()["count"], 2)

    def test_staff_sees_pending_first(self):
        """검수 대기가 앞에 온다. 섞여 나오면 무엇이 검수 전인지 찾아야 한다.

        get_queryset 에서 order_by 를 걸면 OrderingFilter 가 뒤에 돌면서
        통째로 갈아끼운다. filter_queryset 에서 붙여야 살아남는다.
        """
        self.client.force_login(self.staff)

        results = self.client.get(LIST_URL).json()["results"]

        self.assertEqual(results[0]["id"], self.hidden.pk, "검수 대기가 뒤로 밀렸다")

    def test_staff_ordering_param_still_works(self):
        """검수 대기를 앞세우면서도 사용자가 고른 정렬은 유지한다."""
        self.client.force_login(self.staff)

        results = self.client.get(LIST_URL, {"ordering": "-id"}).json()["results"]

        # 대기가 먼저, 그 뒤로 검수된 것들이 id 역순
        self.assertEqual(results[0]["id"], self.hidden.pk)

    def test_list_carries_labels(self):
        item = self.client.get(LIST_URL).json()["results"][0]

        self.assertEqual(item["kind_label"], "실무 표현")
        self.assertEqual(item["category_label"], "코드 리뷰(Code Review)")
        self.assertEqual(item["difficulty_label"], "보통")

    def test_list_omits_heavy_fields(self):
        """목록에 설명과 검수 상태가 실리면 안 된다."""
        item = self.client.get(LIST_URL).json()["results"][0]

        for field in ["description", "is_reviewed", "source"]:
            self.assertNotIn(field, item, f"목록에 {field} 가 실렸다")

    def test_kind_filter(self):
        res = self.client.get(LIST_URL, {"kind": "phrase"})

        self.assertEqual(res.json()["count"], 1)
        self.assertEqual(self.client.get(LIST_URL, {"kind": "error"}).json()["count"], 0)

    def test_unknown_kind_is_rejected(self):
        """목록에 없는 종류로 거르면 400. 조용히 전체를 주면 필터가 안 먹은 걸 모른다."""
        self.assertEqual(
            self.client.get(LIST_URL, {"kind": "nonexistent"}).status_code, 400
        )

    def test_search_covers_text_and_translation(self):
        for term in ["another look", "다시 봐주"]:
            with self.subTest(term=term):
                self.assertEqual(self.client.get(LIST_URL, {"search": term}).json()["count"], 1)

    def test_search_never_reveals_pending(self):
        """미검수 문장의 내용으로 검색해도 나오면 안 된다."""
        res = self.client.get(LIST_URL, {"search": "secret-pending-sentence"})

        self.assertEqual(res.json()["count"], 0)

    def test_kinds_endpoint(self):
        res = self.client.get(f"{LIST_URL}kinds/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            [{"value": v, "label": l} for v, l in SentenceKind.choices],
        )

    def test_categories_endpoint_shared_with_words(self):
        """분류는 단어와 같은 목록을 쓴다. 어긋나면 필터 UI 가 갈린다."""
        sentence_categories = self.client.get(f"{LIST_URL}categories/").json()
        word_categories = self.client.get("/api/vocab/words/categories/").json()

        self.assertEqual(sentence_categories, word_categories)

    def test_anonymous_cannot_write(self):
        res = self.client.post(LIST_URL, {"text": "x", "translation": "y"})

        self.assertIn(res.status_code, (401, 403))
        self.assertEqual(Sentence.objects.filter(text="x").count(), 0)

    def test_non_staff_cannot_write(self):
        user = get_user_model().objects.create_user(email="normal@example.com", password="x")
        self.client.force_login(user)

        res = self.client.post(LIST_URL, {"text": "x", "translation": "y"})

        self.assertEqual(res.status_code, 403)

    def test_staff_create_starts_unreviewed(self):
        """API 로 만든 문장은 검수 전이다. is_reviewed 를 보내도 무시한다."""
        self.client.force_login(self.staff)

        res = self.client.post(
            LIST_URL,
            {"text": "new one", "translation": "새 문장", "is_reviewed": True},
        )

        self.assertEqual(res.status_code, 201)
        self.assertFalse(Sentence.objects.get(text="new one").is_reviewed)

    def test_editing_content_resets_review(self):
        """내용을 고치면 검수가 풀린다. 아무도 확인 안 한 내용이 나가면 안 된다."""
        self.client.force_login(self.staff)

        res = self.client.patch(
            f"{LIST_URL}{self.visible.pk}/",
            {"translation": "완전히 다른 해석"},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.visible.refresh_from_db()
        self.assertFalse(self.visible.is_reviewed, "내용이 바뀌었는데 검수가 유지됐다")

    def test_editing_only_difficulty_keeps_review(self):
        """난이도는 분류 정보라 바꿔도 '확인한 내용' 이 달라지지 않는다."""
        self.client.force_login(self.staff)

        self.client.patch(
            f"{LIST_URL}{self.visible.pk}/",
            {"difficulty": 3},
            content_type="application/json",
        )

        self.visible.refresh_from_db()
        self.assertTrue(self.visible.is_reviewed)

    def test_reverse_url_matches_hardcoded_path(self):
        self.assertEqual(reverse("vocab:sentence-list"), LIST_URL)


class SentenceQuizTest(TestCase):
    """문장 낱개 문제풀기.

    일일공부·복습이 이미 같은 생성 함수를 쓰지만 그쪽은 로그인 뒤 경로다.
    여기는 익명으로 열려 있고 채점까지 하므로 따로 확인한다.
    """

    @classmethod
    def setUpTestData(cls):
        # 상황 고르기는 context 가 있어야, 빈칸 채우기는 문장 안에 단어가
        # 있어야 낼 수 있다. 보기가 넷이라 각각 넷 이상 필요하다.
        for i in range(6):
            Sentence.objects.create(
                text=f"Deploy the service to staging {i}.",
                translation=f"스테이징에 배포합니다 {i}",
                context=f"배포를 알릴 때 {i}",
                kind=SentenceKind.PHRASE,
                is_reviewed=True,
            )
        for i in range(6):
            Word.objects.create(
                term=f"rollback{i}",
                meaning=f"되돌리기 {i}",
                is_reviewed=True,
            )
            Sentence.objects.create(
                text=f"We should rollback{i} the release.",
                translation=f"배포를 되돌려야 합니다 {i}",
                context=f"장애 대응 {i}",
                kind=SentenceKind.PHRASE,
                is_reviewed=True,
            )

    def test_anonymous_can_get_a_question(self):
        """로그인 없이 둘러보는 경로에도 문제풀이가 있다."""
        res = self.client.get(QUIZ_URL)

        self.assertEqual(res.status_code, 200)
        self.assertIn(res.json()["kind"], ("blank", "situation"))

    def test_question_carries_no_answer(self):
        """정답을 응답에 담으면 개발자도구로 미리 보인다."""
        body = self.client.get(QUIZ_URL).json()

        self.assertNotIn("answer_id", body)
        self.assertIn("token", body)

    def test_unknown_kind_is_rejected(self):
        """단어 유형을 문장 쪽에 넣으면 지문과 묻는 말이 어긋난다."""
        res = self.client.get(QUIZ_URL, {"kind": "meaning"})

        self.assertEqual(res.status_code, 400)

    def test_unknown_category_is_rejected(self):
        res = self.client.get(QUIZ_URL, {"category": "그런분류없음"})

        self.assertEqual(res.status_code, 400)

    def test_unreviewed_sentences_are_never_asked(self):
        """검수 안 된 내용을 정답이라고 채점하면 그대로 잘못 외운다."""
        Sentence.objects.update(is_reviewed=False)

        res = self.client.get(QUIZ_URL)

        self.assertEqual(res.status_code, 404)

    def test_blank_question_answers_with_a_word(self):
        """빈칸 채우기는 문장을 보여주지만 정답은 단어다."""
        body = self.client.get(QUIZ_URL, {"kind": "blank"}).json()

        self.assertEqual(body["kind"], "blank")
        self.assertEqual(body["answer_type"], "word")
        # 어느 문장에서 냈는지 알려줘야 화면이 그 문장을 다시 안 낸다.
        self.assertIsNotNone(body["source_sentence_id"])
        self.assertIn("____", body["prompt"])

    def test_situation_question_answers_with_a_sentence(self):
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        self.assertEqual(body["kind"], "situation")
        self.assertEqual(body["answer_type"], "sentence")

    def _solve(self, kind: str) -> dict:
        """문제를 받아 보기 넷을 다 넣어보고 정답이 나온 응답을 돌려준다."""
        body = self.client.get(QUIZ_URL, {"kind": kind}).json()
        for choice in body["choices"]:
            res = self.client.post(
                GRADE_URL,
                {"token": body["token"], "picked": choice["id"]},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, 200)
            if res.json()["correct"]:
                return res.json()
        self.fail("보기 넷 중에 정답이 없었다")

    def test_grading_a_blank_question_explains_the_word(self):
        graded = self._solve("blank")

        self.assertEqual(graded["answer_type"], "word")
        self.assertIn("word", graded)
        self.assertNotIn("sentence", graded)

    def test_grading_a_situation_question_explains_the_sentence(self):
        graded = self._solve("situation")

        self.assertEqual(graded["answer_type"], "sentence")
        self.assertIn("sentence", graded)
        # 상황 고르기는 이 값이 정답 보기라 채점 뒤에도 보여줘야 한다.
        self.assertTrue(graded["sentence"]["context"])

    def test_grade_hides_review_workflow_fields(self):
        """채점은 익명 경로다. 무엇이 AI 생성인지 알려주지 않는다."""
        graded = self._solve("situation")

        self.assertNotIn("is_reviewed", graded["sentence"])
        self.assertNotIn("source", graded["sentence"])

    def test_a_sentence_token_cannot_be_graded_as_a_word(self):
        """토큰 salt 가 단어·문장 공용이라 남의 토큰도 풀린다.

        종류를 안 보면 정답 id 가 Sentence pk 인 채로 Word 를 조회해,
        같은 번호의 엉뚱한 단어가 응답에 실린다. 보기를 돌려가며 부르면
        pk 로 표를 훑는 통로가 되고, 미검수 단어는 404 라 검수 상태까지
        드러난다.
        """
        body = self.client.get(QUIZ_URL, {"kind": "situation"}).json()

        for choice in body["choices"]:
            res = self.client.post(
                WORD_GRADE_URL,
                {"token": body["token"], "picked": choice["id"]},
                content_type="application/json",
            )
            self.assertEqual(
                res.status_code,
                400,
                "문장 토큰이 단어 채점에서 받아들여졌다",
            )
            self.assertNotIn("word", res.json())

    def test_bad_token_is_rejected(self):
        res = self.client.post(
            GRADE_URL,
            {"token": "아무거나", "picked": 1},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_non_dict_body_does_not_crash(self):
        """본문 전체가 사용자 입력이다. 배열이어도 500 이 나면 안 된다."""
        res = self.client.post(
            GRADE_URL, [1, 2, 3], content_type="application/json"
        )

        self.assertEqual(res.status_code, 400)

    def test_true_is_not_treated_as_choice_one(self):
        """파이썬에서 True 는 int 라 1 번 보기를 고른 것이 될 수 있다."""
        body = self.client.get(QUIZ_URL).json()

        res = self.client.post(
            GRADE_URL,
            {"token": body["token"], "picked": True},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["correct"])

    def test_exclude_is_capped(self):
        """긴 문자열을 보내 pk__in 을 무겁게 만들 수 없다."""
        res = self.client.get(QUIZ_URL, {"exclude": ",".join(str(i) for i in range(5000))})

        self.assertIn(res.status_code, (200, 404))
