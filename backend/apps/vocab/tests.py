import re
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .management.commands.seed_words import WORDS
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


# IPA 인데 짧아서 로마자 표기와 모양이 같은 것들. 아래 발음기호 형식
# 검사에서 예외로 통과시킨다.
SHORT_IPA_OK = {
    "/hed/",   # HEAD
    "/prun/",  # prune
    "/spek/",  # spec
    "/rest/",  # REST
    "/vju/",   # view
    "/sid/",   # seed
    "/ki/",    # key
    "/kju/",   # queue
}


class SeedWordsTest(TestCase):
    """초기 단어 데이터 커맨드."""

    def run_seed(self, *args: str) -> str:
        out = StringIO()
        call_command("seed_words", *args, stdout=out)
        return out.getvalue()

    def test_seeds_words_as_reviewed(self):
        """사람이 쓴 데이터라 바로 노출된다. AI 생성물과 반대다."""
        self.run_seed()

        self.assertTrue(Word.objects.exists())
        self.assertEqual(Word.objects.filter(is_reviewed=False).count(), 0)
        self.assertEqual(Word.objects.count(), Word.objects.visible().count())

    def test_is_idempotent(self):
        """두 번 돌려도 중복이 생기지 않는다."""
        self.run_seed()
        count = Word.objects.count()

        output = self.run_seed()

        self.assertEqual(Word.objects.count(), count)
        self.assertIn("건너뜀", output)

    def test_does_not_overwrite_without_reset(self):
        """이미 있는 단어의 수정 내용을 덮어쓰지 않는다."""
        Word.objects.create(term="commit", meaning="내가 고친 뜻", is_reviewed=True)

        self.run_seed()

        self.assertEqual(Word.objects.get(term="commit").meaning, "내가 고친 뜻")

    def test_reset_updates_existing(self):
        Word.objects.create(term="commit", meaning="옛 뜻", is_reviewed=True)

        self.run_seed("--reset")

        self.assertNotEqual(Word.objects.get(term="commit").meaning, "옛 뜻")

    def test_reset_does_not_promote_pending_review(self):
        """검수 대기 중인 단어를 승격시키면 안 된다.

        덮어쓰면 아무도 승인하지 않은 항목이 is_reviewed=True 가 되어,
        검수 플래그가 "사람이 봤다" 는 의미를 잃는다.
        """
        Word.objects.create(
            term="commit", meaning="AI 가 만든 뜻", is_reviewed=False, source="AI 생성"
        )

        output = self.run_seed("--reset")

        word = Word.objects.get(term="commit")
        self.assertFalse(word.is_reviewed, "검수 대기 단어가 승격됐다")
        self.assertEqual(word.meaning, "AI 가 만든 뜻", "내용까지 덮어썼다")
        self.assertIn("건너뛴", output)

    def test_force_pending_overwrites_explicitly(self):
        """명시적으로 요청하면 덮어쓴다."""
        Word.objects.create(
            term="commit", meaning="AI 가 만든 뜻", is_reviewed=False, source="AI 생성"
        )

        self.run_seed("--reset", "--force-pending")

        word = Word.objects.get(term="commit")
        self.assertTrue(word.is_reviewed)
        self.assertNotEqual(word.meaning, "AI 가 만든 뜻")

    def test_force_pending_alone_is_rejected(self):
        """--reset 없는 --force-pending 은 뜻이 없으므로 조용히 넘어가지 않는다."""
        with self.assertRaises(CommandError):
            self.run_seed("--force-pending")

        # 막기만 하고 절반 넣어두면 더 나쁘다.
        self.assertEqual(Word.objects.count(), 0)

    def test_partial_failure_saves_nothing(self):
        """중간에 터지면 앞서 넣은 것까지 전부 롤백한다.

        @transaction.atomic 이 없으면 몇 개만 들어간 상태로 남는데, 그러면
        다음 실행이 '이미 있네' 하고 건너뛰어 빠진 단어가 영영 안 들어온다.
        """
        real_save = Word.save
        calls = {"n": 0}

        def fail_on_third(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("중간 실패")
            return real_save(self, *args, **kwargs)

        with patch.object(Word, "save", fail_on_third):
            with self.assertRaises(RuntimeError):
                self.run_seed()

        self.assertEqual(Word.objects.count(), 0, "앞의 2개가 남았다")

    def test_reset_updates_reviewed_words_without_warning(self):
        """이미 검수된 단어는 그냥 갱신한다."""
        Word.objects.create(term="commit", meaning="옛 뜻", is_reviewed=True)

        output = self.run_seed("--reset")

        self.assertNotEqual(Word.objects.get(term="commit").meaning, "옛 뜻")
        self.assertNotIn("건너뛴", output)

    def test_data_quality(self):
        """빠진 필드나 잘못된 난이도가 없어야 한다."""
        terms = [w[0] for w in WORDS]
        self.assertEqual(len(terms), len(set(terms)), "중복된 단어가 있다")

        for term, pron, meaning, category, difficulty, desc, ex, ex_ko in WORDS:
            with self.subTest(term=term):
                self.assertTrue(term.strip())
                self.assertTrue(meaning.strip())
                self.assertTrue(desc.strip(), "설명이 비었다")
                self.assertTrue(ex.strip(), "예문이 비었다")
                self.assertTrue(ex_ko.strip(), "예문 해석이 비었다")
                self.assertIn(difficulty, (1, 2, 3))
                # 길이 제한은 모델에서 읽는다. 숫자를 다시 적으면 모델을
                # 고쳤을 때 조용히 어긋난다.
                self.assertLessEqual(
                    len(term), Word._meta.get_field("term").max_length
                )
                self.assertLessEqual(
                    len(meaning), Word._meta.get_field("meaning").max_length
                )
                self.assertLessEqual(
                    len(pron), Word._meta.get_field("pronunciation").max_length
                )

    def test_pronunciation_format(self):
        """발음기호는 미국식 IPA 를 슬래시로 감싼다. 없으면 빈 문자열.

        형식이 섞이면 화면에서 슬래시가 있다 없다 한다. 확신이 없어 비우는
        것은 허용하되, 적을 거면 형식을 지킨다.
        """
        for term, pron, *_rest in WORDS:
            with self.subTest(term=term):
                if not pron:
                    continue
                self.assertTrue(pron.startswith("/"), f"{term}: 슬래시로 시작해야 한다")
                self.assertTrue(pron.endswith("/"), f"{term}: 슬래시로 끝나야 한다")
                self.assertGreater(len(pron), 2, f"{term}: 발음기호가 비었다")

                # 미국식에는 음소적 장음이 없다. ː 를 쓰면 영국식 표기가
                # 섞여 학습자가 없는 소리를 길게 읽는다.
                self.assertNotIn("ː", pron, f"{term}: 미국식에는 장음 기호를 쓰지 않는다")

                # 한글이 섞이면 IPA 가 아니다.
                self.assertNotRegex(
                    pron, r"[가-힣]", f"{term}: 발음기호에 한글이 섞였다"
                )

                # "캐시" 를 /kaesi/ 로 적는 로마자 표기를 막는다. 한글 검사만으로는
                # 못 잡는다 - 한글 코드포인트가 없기 때문이다.
                #
                # ASCII 만으로 되어 있다고 로마자로 단정할 수는 없다. 아래
                # SHORT_IPA_OK 의 여덟 개는 실제 IPA 인데 짧아서 로마자와
                # 모양이 같다. 길이로 열어두면(len <= 5) /kaesi/ 같은 진짜
                # 로마자까지 함께 통과하므로 목록으로 박아둔다 - 새 항목을
                # 추가할 때 목록에 한 줄 넣는 것이 "사람이 봤다" 는 신호다.
                body = pron.strip("/").replace(" ", "")
                looks_like_ipa = (
                    re.search(r"[æðŋʃʒθʌɑɔəɚɜɛɪʊɡ]", body)
                    or "ˈ" in body
                    or "ˌ" in body
                    or pron in SHORT_IPA_OK
                )
                self.assertTrue(
                    looks_like_ipa,
                    f"{term}: IPA 고유 기호도 강세도 없다 - 로마자 표기인지 확인",
                )

    def test_multiword_pronunciation_has_one_primary_stress(self):
        """두 단어 구는 주강세가 하나다. 나머지는 2강세로 내린다.

        양쪽 다 1강세를 주면 어디를 세게 읽어야 할지 알 수 없다.
        """
        for term, pron, *_rest in WORDS:
            if not pron or " " not in pron:
                continue
            with self.subTest(term=term):
                self.assertEqual(
                    pron.count("ˈ"), 1, f"{term}: 주강세(ˈ)는 하나여야 한다"
                )

    def test_every_word_has_a_category(self):
        """분류가 빠지면 필터 화면에서 찾을 수 없다.

        분류별 개수 균형은 편집 방침이라 테스트로 고정하지 않는다.
        나중에 특정 분류를 집중적으로 늘리는 것도 정당한 변경이다.
        """
        for term, _pron, _meaning, category, *_rest in WORDS:
            with self.subTest(term=term):
                self.assertTrue(category.strip(), f"{term} 에 분류가 없다")


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
