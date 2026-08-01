from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

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

    def test_visible_manager_excludes_unreviewed(self):
        """Manager 헬퍼가 검수 필터를 실제로 건다."""
        Word.objects.create(term="commit", meaning="커밋하다", is_reviewed=True)
        Word.objects.create(term="stash", meaning="임시저장하다")

        self.assertEqual([w.term for w in Word.objects.visible()], ["commit"])


class WordAPITest(TestCase):
    """단어 API. 검수 게이트와 권한이 실제로 막는지 확인한다."""

    def setUp(self):
        self.reviewed = Word.objects.create(
            term="deploy", meaning="배포하다", category="devops", is_reviewed=True
        )
        self.unreviewed = Word.objects.create(
            term="rebase", meaning="재배치하다", category="git"
        )
        self.list_url = reverse("vocab:word-list")

    def detail_url(self, word):
        return reverse("vocab:word-detail", args=[word.pk])

    # --- 검수 게이트 (이 API 의 핵심 규칙) ---

    def test_list_hides_unreviewed(self):
        """검수 안 된 단어는 목록에 나오면 안 된다."""
        res = self.client.get(self.list_url)

        self.assertEqual(res.status_code, 200)
        self.assertEqual([w["term"] for w in res.json()["results"]], ["deploy"])

    def test_detail_of_unreviewed_is_404(self):
        """미검수 단어는 pk 를 알아도 볼 수 없다."""
        res = self.client.get(self.detail_url(self.unreviewed))

        self.assertEqual(res.status_code, 404)

    def test_search_does_not_leak_unreviewed(self):
        """검색으로도 미검수 단어가 새면 안 된다."""
        res = self.client.get(self.list_url, {"search": "재배치"})

        self.assertEqual(res.json()["count"], 0)

    def test_staff_sees_unreviewed(self):
        """관리자는 검수하려면 미검수 단어를 봐야 한다."""
        staff = get_user_model().objects.create_user(
            username="admin", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.get(self.list_url)

        self.assertEqual(res.json()["count"], 2)

    # --- 조회 ---

    def test_detail_of_reviewed_returns_full_fields(self):
        res = self.client.get(self.detail_url(self.reviewed))

        self.assertEqual(res.status_code, 200)
        self.assertIn("example", res.json())

    def test_filter_by_category(self):
        res = self.client.get(self.list_url, {"category": "devops"})

        self.assertEqual([w["term"] for w in res.json()["results"]], ["deploy"])

    def test_invalid_pk_returns_404_not_500(self):
        res = self.client.get(f"/api/vocab/words/{'9' * 30}/")

        self.assertEqual(res.status_code, 404)

    # --- 권한 ---

    def test_anonymous_cannot_create(self):
        res = self.client.post(self.list_url, {"term": "hack", "meaning": "침입"})

        self.assertIn(res.status_code, (401, 403))
        self.assertFalse(Word.objects.filter(term="hack").exists())

    def test_normal_user_cannot_delete(self):
        """로그인만 했다고 단어를 지울 수 있으면 안 된다."""
        user = get_user_model().objects.create_user(username="u", password="pw")
        self.client.force_login(user)

        res = self.client.delete(self.detail_url(self.reviewed))

        self.assertEqual(res.status_code, 403)
        self.assertTrue(Word.objects.filter(pk=self.reviewed.pk).exists())

    def test_staff_can_create(self):
        staff = get_user_model().objects.create_user(
            username="admin2", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.post(self.list_url, {"term": "merge", "meaning": "병합하다"})

        self.assertEqual(res.status_code, 201)

    def test_created_word_starts_unreviewed(self):
        """API 로 만든 단어도 검수 전 상태여야 한다 - is_reviewed 는 읽기 전용."""
        staff = get_user_model().objects.create_user(
            username="admin3", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.post(
            self.list_url,
            {"term": "squash", "meaning": "합치다", "is_reviewed": True},
        )

        self.assertEqual(res.status_code, 201)
        self.assertFalse(Word.objects.get(term="squash").is_reviewed)

    # --- 수정 시 재검수 ---

    def test_editing_content_resets_review(self):
        """검수된 단어의 내용을 고치면 검수 상태가 풀린다.

        플래그가 True 로 남으면 아무도 확인하지 않은 문장이 검수 완료 상태로
        사용자에게 나간다.
        """
        staff = get_user_model().objects.create_user(
            username="editor", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.patch(
            self.detail_url(self.reviewed),
            data={"meaning": "완전히 다른 뜻"},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.reviewed.refresh_from_db()
        self.assertFalse(self.reviewed.is_reviewed)

    def test_editing_only_category_keeps_review(self):
        """분류만 바꾼 것은 내용 변경이 아니므로 검수 상태를 유지한다."""
        staff = get_user_model().objects.create_user(
            username="editor2", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        self.client.patch(
            self.detail_url(self.reviewed),
            data={"category": "새분류"},
            content_type="application/json",
        )

        self.reviewed.refresh_from_db()
        self.assertTrue(self.reviewed.is_reviewed)

    def test_editing_with_same_content_keeps_review(self):
        """같은 값으로 다시 보내는 것은 변경이 아니다."""
        staff = get_user_model().objects.create_user(
            username="editor3", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        self.client.patch(
            self.detail_url(self.reviewed),
            data={"meaning": self.reviewed.meaning},
            content_type="application/json",
        )

        self.reviewed.refresh_from_db()
        self.assertTrue(self.reviewed.is_reviewed)

    # --- 입력 검증 ---

    def test_blank_term_is_rejected(self):
        staff = get_user_model().objects.create_user(
            username="admin4", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.post(self.list_url, {"term": "   ", "meaning": "뜻"})

        self.assertEqual(res.status_code, 400)

    def test_duplicate_term_is_400_not_500(self):
        staff = get_user_model().objects.create_user(
            username="admin5", password="pw", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.post(self.list_url, {"term": "deploy", "meaning": "중복"})

        self.assertEqual(res.status_code, 400)
