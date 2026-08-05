"""독립 동적 테스트 - 검수 게이트/권한/입력 검증을 깨뜨리려는 시도.

구현자 테스트(tests.py)와 별개로 설계했다. 통과 확인이 아니라 결함 찾기가 목적이다.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import Word

LIST_URL = "/api/vocab/words/"


def make_user(username, **kwargs):
    return get_user_model().objects.create_user(
        username=username, password="pw1234!x", **kwargs
    )


class ReviewGateLeakTest(TestCase):
    """미검수 단어가 사용자 조회 경로로 새는 길을 전방위로 찾는다."""

    @classmethod
    def setUpTestData(cls):
        # 검수된 것 3개, 미검수 3개. 카테고리/난이도/생성순을 섞어 정렬·필터 조합을 만든다.
        cls.reviewed = [
            Word.objects.create(
                term="alpha", meaning="알파", category="git",
                difficulty=Word.Difficulty.EASY, is_reviewed=True,
            ),
            Word.objects.create(
                term="mike", meaning="마이크", category="devops",
                difficulty=Word.Difficulty.HARD, is_reviewed=True,
            ),
            Word.objects.create(
                term="zulu", meaning="줄루", category="git",
                difficulty=Word.Difficulty.NORMAL, is_reviewed=True,
            ),
        ]
        cls.hidden = [
            Word.objects.create(
                term="bravo", meaning="브라보", category="git",
                difficulty=Word.Difficulty.EASY, description="secret-desc",
            ),
            Word.objects.create(
                term="november", meaning="노벰버", category="devops",
                difficulty=Word.Difficulty.HARD,
            ),
            Word.objects.create(
                term="zzz-last", meaning="마지막", category="git",
                difficulty=Word.Difficulty.NORMAL,
            ),
        ]

    def assert_no_leak(self, res, label):
        """요청이 통과했는데 미검수 단어가 섞여 나오지는 않는지 본다.

        200 만 받는다. 거부(400)까지 여기서 허용하면 필터가 통째로 고장나
        모든 요청이 400 이 되어도 "본문에 미검수가 없다" 며 통과한다.
        잘못된 값의 거부는 그 자체를 확인하는 테스트에서 따로 본다.

        거부 응답을 이 검사에 태우면 안 되는 이유가 하나 더 있다. DRF 의
        검증 에러는 사용자가 보낸 값을 그대로 되돌려주므로,
        ?category=<미검수단어의 term> 같은 요청은 DB 를 한 줄도 읽지 않고도
        본문에 그 term 이 찍힌다. 누출이 아닌데 누출로 잡히는 오탐이 된다.
        """
        self.assertEqual(res.status_code, 200, label)
        body = res.content.decode()
        for word in self.hidden:
            self.assertNotIn(word.term, body, f"{label}: 미검수 '{word.term}' 누출")

    # --- 정렬 조합 ---

    def test_ordering_variants_do_not_leak(self):
        """ordering 을 어떻게 바꿔도 미검수는 안 나온다."""
        for value in ["term", "-term", "created_at", "-created_at",
                      "difficulty", "-difficulty", "term,-created_at", "id", "-id",
                      "is_reviewed", "-is_reviewed"]:
            with self.subTest(ordering=value):
                res = self.client.get(LIST_URL, {"ordering": value})
                self.assert_no_leak(res, f"ordering={value}")

    def test_ordering_by_unlisted_field_is_ignored_not_500(self):
        """ordering_fields 에 없는 필드를 줘도 500 이 아니고 누출도 없다."""
        for value in ["password", "meaning", "description", "nonexistent__x", "; DROP TABLE"]:
            with self.subTest(ordering=value):
                res = self.client.get(LIST_URL, {"ordering": value})
                self.assert_no_leak(res, f"ordering={value}")

    # --- 검색 조합 ---

    def test_search_cannot_surface_unreviewed(self):
        """미검수 단어의 term/meaning/description 을 정확히 검색해도 0건."""
        for query in ["bravo", "브라보", "secret-desc", "november", "노벰버", "zzz"]:
            with self.subTest(search=query):
                res = self.client.get(LIST_URL, {"search": query})
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["count"], 0, f"search={query} 누출")

    def test_empty_search_does_not_bypass_filter(self):
        res = self.client.get(LIST_URL, {"search": ""})
        self.assert_no_leak(res, "search=(빈문자열)")
        self.assertEqual(res.json()["count"], 3)

    def test_search_with_ordering_and_category_combined(self):
        """세 필터를 겹쳐도 게이트가 유지된다."""
        res = self.client.get(
            LIST_URL, {"search": "a", "ordering": "-created_at", "category": "git"}
        )
        self.assert_no_leak(res, "search+ordering+category")

    # --- 필터 조합 ---

    def test_category_filter_does_not_leak(self):
        # 유효한 값만 넣는다. 거부되는 값을 섞으면 200 을 기대하는 케이스까지
        # 검증이 헐거워져, 필터가 통째로 고장나도 통과한다.
        for category in ["git", "devops", ""]:
            with self.subTest(category=category):
                res = self.client.get(LIST_URL, {"category": category})
                self.assert_no_leak(res, f"category={category}")

    def test_rejected_filter_echoes_input_but_reads_nothing(self):
        """거부된 요청이 입력을 되돌려줘도 DB 를 읽지 않는다.

        미검수 단어의 term 을 분류로 보내면 검증 에러 본문에 그 문자열이
        그대로 찍힌다. 이건 DB 에서 온 값이 아니라 방금 보낸 값이라 누출이
        아니다 - 그 단어의 뜻이나 설명은 나오지 않아야 한다.
        """
        hidden = self.hidden[0]

        res = self.client.get(LIST_URL, {"category": hidden.term})

        self.assertEqual(res.status_code, 400)
        body = res.content.decode()
        self.assertNotIn(hidden.meaning, body, "미검수 단어의 내용이 새어나왔다")

    def test_difficulty_filter_does_not_leak(self):
        for difficulty in ["1", "2", "3"]:
            with self.subTest(difficulty=difficulty):
                res = self.client.get(LIST_URL, {"difficulty": difficulty})
                self.assert_no_leak(res, f"difficulty={difficulty}")

    def test_is_reviewed_query_param_cannot_be_used_to_flip_gate(self):
        """?is_reviewed=false 같은 파라미터로 게이트를 뒤집을 수 없다."""
        for params in [{"is_reviewed": "false"}, {"is_reviewed": "0"},
                       {"is_reviewed": "False"}, {"is_reviewed": ""}]:
            with self.subTest(params=params):
                res = self.client.get(LIST_URL, params)
                self.assert_no_leak(res, f"{params}")

    # --- 페이지네이션 경계 ---

    def test_pagination_page_two_does_not_leak(self):
        """PAGE_SIZE 를 넘기는 데이터에서 뒷페이지에 미검수가 섞이지 않는다."""
        # 검수된 것을 25개로 늘려 2페이지를 만든다.
        Word.objects.bulk_create([
            Word(term=f"page-word-{i:03d}", meaning=f"뜻{i}", is_reviewed=True)
            for i in range(25)
        ])
        res = self.client.get(LIST_URL, {"page": 2})
        self.assert_no_leak(res, "page=2")

        total = self.client.get(LIST_URL).json()["count"]
        self.assertEqual(total, 3 + 25, "count 에 미검수가 포함되면 안 된다")

    def test_page_size_param_cannot_be_inflated(self):
        """page_size 를 크게 줘도 게이트는 유지된다(설정상 무시되는 것이 정상)."""
        res = self.client.get(LIST_URL, {"page_size": 10000})
        self.assert_no_leak(res, "page_size=10000")

    def test_page_zero_and_out_of_range_are_404_not_500(self):
        for page in ["0", "999999", "-1", "abc", ""]:
            with self.subTest(page=page):
                res = self.client.get(LIST_URL, {"page": page})
                self.assertIn(res.status_code, (200, 404), f"page={page} -> {res.status_code}")
                self.assertLess(res.status_code, 500, f"page={page} 에서 500")

    # --- 메서드 노출 ---

    def test_head_on_unreviewed_detail_is_404(self):
        """HEAD 로 미검수 단어의 존재가 드러나면 안 된다."""
        hidden = self.hidden[0]
        res = self.client.head(f"{LIST_URL}{hidden.pk}/")
        self.assertEqual(res.status_code, 404)

        visible = self.reviewed[0]
        self.assertEqual(self.client.head(f"{LIST_URL}{visible.pk}/").status_code, 200)

    def test_options_on_unreviewed_detail_does_not_reveal_content(self):
        """OPTIONS 응답에 미검수 단어 내용이 실리면 안 된다."""
        hidden = self.hidden[0]
        res = self.client.options(f"{LIST_URL}{hidden.pk}/")
        self.assertNotIn(hidden.term, res.content.decode())

    def test_head_on_list_does_not_leak(self):
        res = self.client.head(LIST_URL)
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("bravo", res.content.decode())

    # --- 세션 전환 ---

    def test_staff_logout_stops_seeing_unreviewed(self):
        """staff 로그인 후 로그아웃하면 즉시 미검수가 다시 숨겨진다(queryset 캐시 없음)."""
        staff = make_user("gate-staff", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(LIST_URL).json()["count"], 6)

        self.client.logout()
        res = self.client.get(LIST_URL)
        self.assertEqual(res.json()["count"], 3)
        self.assert_no_leak(res, "staff 로그아웃 후")

    def test_normal_authenticated_user_does_not_see_unreviewed(self):
        """staff 가 아닌 로그인 사용자는 일반 사용자와 같아야 한다."""
        self.client.force_login(make_user("gate-normal"))
        res = self.client.get(LIST_URL)
        self.assert_no_leak(res, "일반 로그인 사용자")
        self.assertEqual(
            self.client.get(f"{LIST_URL}{self.hidden[0].pk}/").status_code, 404
        )

    def test_inactive_staff_cannot_see_unreviewed(self):
        """is_active=False 인 staff 는 인증이 되지 않으므로 미검수를 못 본다."""
        staff = make_user("gate-inactive-staff", is_staff=True)
        self.client.force_login(staff)
        staff.is_active = False
        staff.save()

        res = self.client.get(LIST_URL)
        self.assert_no_leak(res, "비활성 staff")

    def test_api_root_does_not_leak(self):
        """DefaultRouter 의 API 루트가 데이터를 흘리지 않는다."""
        res = self.client.get("/api/vocab/")
        self.assertEqual(res.status_code, 200)
        self.assert_no_leak(res, "API 루트")


class PermissionTest(TestCase):
    """쓰기 경로 권한. 일반 사용자가 데이터를 바꿀 수 있으면 안 된다."""

    @classmethod
    def setUpTestData(cls):
        cls.word = Word.objects.create(
            term="target", meaning="대상", is_reviewed=True, category="git"
        )
        cls.hidden = Word.objects.create(term="hidden-target", meaning="숨김")

    def detail(self, word=None):
        return f"{LIST_URL}{(word or self.word).pk}/"

    def test_anonymous_write_methods_are_blocked(self):
        payload = {"term": "anon", "meaning": "익명"}
        for method, url in [
            ("post", LIST_URL),
            ("put", self.detail()),
            ("patch", self.detail()),
            ("delete", self.detail()),
        ]:
            with self.subTest(method=method):
                res = getattr(self.client, method)(
                    url, data=payload, content_type="application/json"
                )
                self.assertIn(res.status_code, (401, 403), f"{method} -> {res.status_code}")
        self.assertEqual(Word.objects.get(pk=self.word.pk).term, "target")

    def test_normal_user_write_methods_are_blocked(self):
        self.client.force_login(make_user("perm-normal"))
        payload = {"term": "changed", "meaning": "변경됨"}
        for method, url in [
            ("post", LIST_URL),
            ("put", self.detail()),
            ("patch", self.detail()),
            ("delete", self.detail()),
        ]:
            with self.subTest(method=method):
                res = getattr(self.client, method)(
                    url, data=payload, content_type="application/json"
                )
                self.assertEqual(res.status_code, 403, f"{method} -> {res.status_code}")
        self.word.refresh_from_db()
        self.assertEqual(self.word.term, "target")

    def test_staff_cannot_flip_is_reviewed_via_patch(self):
        """검수 게이트를 API 로 스스로 통과시킬 수 없다 - is_reviewed 는 읽기 전용."""
        self.client.force_login(make_user("perm-staff-patch", is_staff=True))

        res = self.client.patch(
            self.detail(self.hidden),
            data={"is_reviewed": True},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.hidden.refresh_from_db()
        self.assertFalse(self.hidden.is_reviewed, "PATCH 로 is_reviewed 가 바뀌었다")

    def test_staff_cannot_flip_is_reviewed_via_put(self):
        self.client.force_login(make_user("perm-staff-put", is_staff=True))

        res = self.client.put(
            self.detail(self.hidden),
            data={"term": "hidden-target", "meaning": "숨김", "is_reviewed": True},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.hidden.refresh_from_db()
        self.assertFalse(self.hidden.is_reviewed, "PUT 로 is_reviewed 가 바뀌었다")

    def test_superuser_cannot_flip_is_reviewed_via_api(self):
        """슈퍼유저라도 API 로는 검수 상태를 못 바꾼다(검수는 Admin 전용)."""
        admin = get_user_model().objects.create_superuser(
            username="perm-super", password="pw1234!x", email="a@b.c"
        )
        self.client.force_login(admin)

        self.client.patch(
            self.detail(self.hidden),
            data={"is_reviewed": True},
            content_type="application/json",
        )

        self.hidden.refresh_from_db()
        self.assertFalse(self.hidden.is_reviewed)

    def test_normal_user_cannot_create_even_with_valid_payload(self):
        self.client.force_login(make_user("perm-create"))
        res = self.client.post(LIST_URL, {"term": "sneak", "meaning": "몰래"})
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Word.objects.filter(term="sneak").exists())


class InvalidInputTest(TestCase):
    """잘못된 입력이 400/404 로 처리되고 500 으로 터지지 않아야 한다."""

    @classmethod
    def setUpTestData(cls):
        cls.word = Word.objects.create(term="exists", meaning="존재", is_reviewed=True)

    def login_staff(self, name="input-staff"):
        self.client.force_login(make_user(name, is_staff=True))

    # --- pk ---

    def test_malformed_pk_is_404_not_500(self):
        for pk in ["-1", "0", "abc", "9" * 30, "1.5", "%20", "null", "1;DROP TABLE"]:
            with self.subTest(pk=pk):
                res = self.client.get(f"{LIST_URL}{pk}/")
                self.assertEqual(res.status_code, 404, f"pk={pk} -> {res.status_code}")

    def test_malformed_pk_on_write_is_not_500(self):
        self.login_staff("input-staff-pk")
        for pk in ["-1", "abc", "9" * 30]:
            with self.subTest(pk=pk):
                res = self.client.delete(f"{LIST_URL}{pk}/")
                self.assertLess(res.status_code, 500, f"DELETE pk={pk} 에서 500")

    # --- 필드 검증 ---

    def test_over_max_length_term_is_400(self):
        """term max_length=100 초과는 400 이어야 한다(DB 에서 터지면 500)."""
        self.login_staff("input-staff-len")
        res = self.client.post(LIST_URL, {"term": "x" * 101, "meaning": "긴단어"})
        self.assertEqual(res.status_code, 400, res.content.decode()[:300])

    def test_over_max_length_meaning_is_400(self):
        self.login_staff("input-staff-len2")
        res = self.client.post(LIST_URL, {"term": "longmeaning", "meaning": "가" * 201})
        self.assertEqual(res.status_code, 400)

    def test_over_max_length_category_and_source_are_400(self):
        self.login_staff("input-staff-len3")
        res = self.client.post(
            LIST_URL,
            {"term": "catlen", "meaning": "뜻", "category": "c" * 51, "source": "s" * 101},
        )
        self.assertEqual(res.status_code, 400)
        body = res.json()
        self.assertIn("category", body)
        self.assertIn("source", body)

    def test_missing_required_fields_is_400(self):
        self.login_staff("input-staff-req")
        for payload in [{}, {"term": "onlyterm"}, {"meaning": "onlymeaning"}]:
            with self.subTest(payload=payload):
                res = self.client.post(LIST_URL, payload)
                self.assertEqual(res.status_code, 400)

    def test_whitespace_only_fields_are_400(self):
        self.login_staff("input-staff-ws")
        for payload in [
            {"term": "   ", "meaning": "뜻"},
            {"term": "단어", "meaning": "   "},
            {"term": "\t\n", "meaning": "\t"},
            {"term": "", "meaning": ""},
        ]:
            with self.subTest(payload=payload):
                res = self.client.post(LIST_URL, payload)
                self.assertEqual(res.status_code, 400, f"{payload} -> {res.status_code}")

    def test_term_is_stripped_before_uniqueness_check(self):
        """공백만 다른 중복이 뚫리지 않는다 - strip 후 중복이면 400."""
        self.login_staff("input-staff-strip")
        res = self.client.post(LIST_URL, {"term": "  exists  ", "meaning": "공백중복"})
        self.assertEqual(res.status_code, 400, "strip 후 중복인데 통과했다")

    def test_bad_difficulty_is_400_not_500(self):
        """choices 밖의 난이도는 400. (빈 문자열은 '미입력'이라 기본값이 적용된다)"""
        self.login_staff("input-staff-diff")
        for value in ["abc", "0", "99", "-1", "1.5"]:
            with self.subTest(difficulty=value):
                res = self.client.post(
                    LIST_URL, {"term": f"d-{value}", "meaning": "뜻", "difficulty": value}
                )
                self.assertEqual(res.status_code, 400, f"difficulty={value} -> {res.status_code}")

    def test_omitted_difficulty_falls_back_to_normal(self):
        """난이도를 안 보내면 모델 기본값(보통)이 들어간다."""
        self.login_staff("input-staff-diff-default")
        res = self.client.post(LIST_URL, {"term": "no-difficulty", "meaning": "뜻"})

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["difficulty"], Word.Difficulty.NORMAL)

    def test_wrong_type_payload_is_400_not_500(self):
        self.login_staff("input-staff-type")
        for payload in [
            {"term": ["list"], "meaning": "뜻"},
            {"term": {"a": 1}, "meaning": "뜻"},
            {"term": None, "meaning": "뜻"},
        ]:
            with self.subTest(payload=payload):
                res = self.client.post(
                    LIST_URL, data=payload, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400)

    def test_malformed_json_body_is_400_not_500(self):
        self.login_staff("input-staff-json")
        res = self.client.post(
            LIST_URL, data="{not json", content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

    def test_special_characters_are_stored_verbatim_as_json(self):
        """특수문자가 500 을 내지 않고, JSON 으로 원문 그대로 왕복한다.

        JSON 응답은 HTML 이스케이프 대상이 아니다(브라우저가 실행하지 않는다).
        렌더링 시점의 이스케이프는 프론트 책임이므로, 여기서는 값이 변형되지
        않는 것과 Content-Type 이 JSON 인 것을 확인한다.
        """
        self.login_staff("input-staff-special")
        for term in ["<script>alert(1)</script>", "'; DROP TABLE vocab_word; --",
                     "emoji-free ünïcødé", "back\\slash", 'quote"inside']:
            with self.subTest(term=term):
                res = self.client.post(LIST_URL, {"term": term, "meaning": "특수문자"})

                self.assertEqual(res.status_code, 201, res.content.decode()[:200])
                self.assertEqual(res["Content-Type"].split(";")[0], "application/json")
                self.assertEqual(res.json()["term"], term)
                self.assertTrue(Word.objects.filter(term=term).exists())

    def test_sql_injection_in_search_does_not_drop_data(self):
        """검색어의 SQL 조각이 실행되지 않는다(ORM 파라미터 바인딩)."""
        res = self.client.get(LIST_URL, {"search": "'; DROP TABLE vocab_word; --"})

        self.assertEqual(res.status_code, 200)
        self.assertTrue(Word.objects.filter(term="exists").exists())

    # --- 쿼리 파라미터 ---

    def test_bad_query_params_do_not_500(self):
        for params in [
            {"difficulty": "abc"},
            {"difficulty": "999999999999999999999"},
            {"difficulty": ""},
            {"category": "x" * 500},
            {"search": "%"},
            {"search": "'" + '"' + "\\"},
            {"ordering": "term" * 200},
        ]:
            with self.subTest(params=params):
                res = self.client.get(LIST_URL, params)
                self.assertLess(res.status_code, 500, f"{params} -> {res.status_code}")


class SerializerShapeTest(TestCase):
    """응답 스키마 - 목록에 무거운 필드가 없고, 상세에 필요한 필드가 다 있다."""

    @classmethod
    def setUpTestData(cls):
        cls.word = Word.objects.create(
            term="shape", meaning="모양", description="설명", example="ex",
            example_translation="예문해석", source="정처기", is_reviewed=True,
        )

    def test_list_omits_heavy_fields(self):
        item = self.client.get(LIST_URL).json()["results"][0]
        for field in ["description", "example", "example_translation", "is_reviewed", "source"]:
            self.assertNotIn(field, item, f"목록에 {field} 가 실렸다")

    def test_list_never_exposes_review_state(self):
        """목록 응답에 is_reviewed 가 없어야 클라이언트가 상태를 추론하지 못한다."""
        self.assertNotIn("is_reviewed", self.client.get(LIST_URL).json()["results"][0])

    def test_detail_has_difficulty_label(self):
        body = self.client.get(f"{LIST_URL}{self.word.pk}/").json()
        self.assertEqual(body["difficulty_label"], "보통")

    def test_reverse_url_matches_hardcoded_path(self):
        """URL 이 바뀌면 이 테스트 파일의 하드코딩 경로도 같이 깨져야 한다."""
        self.assertEqual(reverse("vocab:word-list"), LIST_URL)


class PronunciationTest(TestCase):
    """발음기호는 목록·상세 양쪽에 실린다."""

    @classmethod
    def setUpTestData(cls):
        cls.word = Word.objects.create(
            term="cache", pronunciation="/kæʃ/", meaning="캐시", is_reviewed=True
        )
        cls.no_pron = Word.objects.create(
            term="nopron", meaning="발음없음", is_reviewed=True
        )

    def test_list_and_detail_carry_pronunciation(self):
        """한쪽만 있으면 카드와 상세 화면이 갈린다."""
        item = self.client.get(f"{LIST_URL}?search=cache").json()["results"][0]
        detail = self.client.get(f"{LIST_URL}{self.word.pk}/").json()

        for body, where in [(item, "목록"), (detail, "상세")]:
            self.assertEqual(body["pronunciation"], "/kæʃ/", where)

    def test_missing_pronunciation_is_blank_not_null(self):
        """비어 있으면 빈 문자열이어야 화면이 조건부로 숨긴다."""
        item = self.client.get(f"{LIST_URL}?search=nopron").json()["results"][0]

        self.assertEqual(item["pronunciation"], "")

    def test_editing_pronunciation_resets_review(self):
        """발음을 고치면 검수가 풀린다. 잘못된 발음은 되돌리기 어렵다."""
        staff = get_user_model().objects.create_user(
            username="pron-reviewer", password="x", is_staff=True
        )
        self.client.force_login(staff)

        res = self.client.patch(
            f"{LIST_URL}{self.word.pk}/",
            {"pronunciation": "/kætʃ/"},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.word.refresh_from_db()
        self.assertFalse(self.word.is_reviewed, "발음이 바뀌었는데 검수가 유지됐다")


class CategoryLabelTest(TestCase):
    """분류는 영어 코드 대신 한글 라벨로 나간다."""

    @classmethod
    def setUpTestData(cls):
        cls.word = Word.objects.create(
            term="deploy", meaning="배포하다",
            category=Word.Category.DEVOPS, is_reviewed=True,
        )

    def test_list_and_detail_carry_label(self):
        """목록과 상세 모두 라벨을 준다. 한쪽만 있으면 화면이 갈린다."""
        item = self.client.get(LIST_URL).json()["results"][0]
        detail = self.client.get(f"{LIST_URL}{self.word.pk}/").json()

        for body, where in [(item, "목록"), (detail, "상세")]:
            self.assertEqual(body["category_label"], "배포·운영(DevOps)", where)
            # 필터 링크를 만들려면 영어 코드도 함께 필요하다.
            self.assertEqual(body["category"], "devops", where)

    def test_blank_category_gives_blank_label(self):
        """분류가 비어 있으면 라벨도 빈 문자열이어야 화면이 조건부로 숨긴다."""
        Word.objects.create(term="nocat", meaning="분류없음", is_reviewed=True)

        body = self.client.get(f"{LIST_URL}?search=nocat").json()["results"][0]

        self.assertEqual(body["category_label"], "")

    def test_categories_endpoint_lists_every_choice(self):
        """화면의 필터 버튼은 이 응답으로 만든다. 모델과 어긋나면 안 된다."""
        res = self.client.get(f"{LIST_URL}categories/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(),
            [{"value": v, "label": l} for v, l in Word.Category.choices],
        )

    def test_categories_is_public(self):
        """로그인 없이도 보여야 한다. 필터는 익명 사용자가 제일 많이 쓴다."""
        self.assertEqual(self.client.get(f"{LIST_URL}categories/").status_code, 200)

    def test_db_rejects_category_outside_choices(self):
        """DB 가 막는다. choices 는 full_clean() 을 타는 경로에서만 검사한다.

        seed_words 의 update_or_create 나 bulk_create 는 그 경로를 안 타므로,
        모델 검증만 믿으면 목록에 없는 값이 조용히 저장된다. 그렇게 들어가면
        화면에 영어 코드가 그대로 노출되고 그 필터 링크는 400 이 된다.
        """
        # 제약 위반은 트랜잭션을 깬다. atomic 으로 감싸야 이후 쿼리가 산다.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Word.objects.create(term="badcat", meaning="뜻", category="testing")

    def test_db_allows_blank_category(self):
        """분류 미정은 허용한다. Admin 에서 비워둘 수 있어야 한다."""
        Word.objects.create(term="nocat2", meaning="뜻", category="")

        self.assertEqual(Word.objects.get(term="nocat2").get_category_display(), "")

    def test_unknown_category_is_rejected(self):
        """목록에 없는 분류로 거르면 400. 조용히 전체를 주면 필터가 안 먹은 걸 모른다."""
        self.assertEqual(
            self.client.get(LIST_URL, {"category": "nonexistent"}).status_code, 400
        )
