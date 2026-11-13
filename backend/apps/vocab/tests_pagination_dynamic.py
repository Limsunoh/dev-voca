"""익히기 목록 쪽 나누기(ContentPagination)를 깨뜨려 보는 테스트.

ContentPagination 은 뒤쪽 절반의 쪽을 정렬을 뒤집어 읽는다. 약속은 "사용자가 받는
결과가 DRF 기본(PageNumberPagination)과 같다" 이다. 여기서는 그 약속을 세 갈래로 친다.

1. 같은 요청을 기본 쪽 나누기로도 보내 응답 본문(count/next/previous/results)이 쪽마다
   같은지 본다. 기본 쪽도 정렬이 전순서가 아니면 흔들리므로, 기본과 같다는 것만으로는
   부족하다. 그래서
2. 모든 쪽을 이어 붙인 id 가 DB 에서 직접 뽑은 "보여야 할 집합" 과 정확히 같은지
   (겹침·빠짐 없음) 따로 본다.
3. 검수 안 된 항목이 익명·일반 사용자에게 어느 쪽에서도 안 나오는지 본다.

동점을 일부러 많이 만든다: 모두 같은 난이도, 같은 created_at, 대소문자만 다른 term.
쪽 크기를 1·2·3 으로 줄여 거꾸로 읽는 쪽을 최대한 많이 만든다.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient

from .models import Sentence, Word
from .views import SentenceViewSet, WordViewSet

WORDS = "/api/vocab/words/"
SENTENCES = "/api/vocab/sentences/"
FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _page_param(link: str | None) -> str | None:
    """next/previous 링크의 page 값. 링크가 없으면 None, page 가 빠졌으면 "(none)"."""
    if link is None:
        return None
    return parse_qs(urlparse(link).query).get("page", ["(none)"])[0]


class PagingHarness(TestCase):
    """쪽을 끝까지 넘기며 기본 쪽 나누기와 비교하는 공통 도구."""

    def setUp(self):
        self.anon = APIClient()
        self.member = APIClient()
        self.member.force_authenticate(user=self.normal_user)
        self.reviewer = APIClient()
        self.reviewer.force_authenticate(user=self.staff_user)

    @classmethod
    def _make_users(cls):
        User = get_user_model()
        cls.normal_user = User.objects.create_user(
            email=f"dyn-member-{secrets.token_hex(4)}@example.com", password=secrets.token_urlsafe(16)
        )
        cls.staff_user = User.objects.create_user(
            email=f"dyn-staff-{secrets.token_hex(4)}@example.com",
            password=secrets.token_urlsafe(16),
            is_staff=True,
        )

    def _walk(self, client, url, params, *, default: bool) -> list:
        """1쪽부터 끝까지, 그리고 last·끝+1 까지 받은 응답을 순서대로 모은다."""
        patches = (
            [mock.patch.object(v, "pagination_class", PageNumberPagination) for v in (WordViewSet, SentenceViewSet)]
            if default
            else []
        )
        for p in patches:
            p.start()
        try:
            first = client.get(url, params)
            self.assertEqual(first.status_code, 200, (url, params, first.content[:300]))
            body = first.json()
            out = [body]
            size = PageNumberPagination.page_size
            last = max(1, (body["count"] + size - 1) // size)
            for number in range(2, last + 1):
                r = client.get(url, {**params, "page": number})
                self.assertEqual(r.status_code, 200, (url, params, number))
                out.append(r.json())
            # 가운데·마지막을 숫자와 "last" 로 한 번 더(같은 응답이어야 한다).
            r_last = client.get(url, {**params, "page": "last"})
            out.append(("last", r_last.status_code, r_last.json() if r_last.status_code == 200 else None))
            out.append(("beyond", client.get(url, {**params, "page": last + 1}).status_code))
            return out
        finally:
            for p in patches:
                p.stop()

    def assert_same_as_default(self, client, url, params, expected_ids=None):
        """쪽마다 기본과 같고, 이어 붙인 id 에 겹침·빠짐이 없는지."""
        mine = self._walk(client, url, params, default=False)
        theirs = self._walk(client, url, params, default=True)
        self.assertEqual(mine, theirs, (url, params))

        pages = [p for p in mine if isinstance(p, dict)]
        ids = [row["id"] for p in pages for row in p["results"]]
        self.assertEqual(len(ids), len(set(ids)), ("쪽 사이에 같은 항목이 두 번 나왔다", url, params))
        self.assertEqual(len(ids), pages[0]["count"], (url, params))
        if expected_ids is not None:
            self.assertEqual(set(ids), set(expected_ids), ("빠졌거나 섞여 든 항목", url, params))
        # page=last 가 마지막 숫자 쪽과 같다.
        last_entry = next(p for p in mine if isinstance(p, tuple) and p[0] == "last")
        self.assertEqual(last_entry[1], 200)
        self.assertEqual(last_entry[2], pages[-1])
        return ids


class TieHeavyWordsTest(PagingHarness):
    """같은 값이 많은 데이터. 정렬이 pk 로 끝나지 않으면 쪽 경계가 흔들린다."""

    @classmethod
    def setUpTestData(cls):
        cls._make_users()
        terms = [f"tie{i:02d}" for i in range(23)]
        terms += ["Cache", "cache", "CACHE", "Queue", "queue", "QUEUE", "Node", "node"]
        terms += ["C++", "C#", "100%", "under_score", "it's", 'say "hi"', "back\\slash", "커밋 로그"]
        words = []
        for i, term in enumerate(terms):
            words.append(
                Word(
                    term=term,
                    meaning=f"같은 뜻 {i % 2}",
                    description="같은 설명",
                    aliases="커밋, 커미트" if i % 5 == 0 else "",
                    difficulty=2,
                    category="git",
                    is_exam=i % 4 == 0,
                    exam_subject="database" if i % 4 == 0 else "",
                    is_reviewed=i % 6 != 3,
                )
            )
        Word.objects.bulk_create(words)
        # created_at 도 전부 같게 한다.
        Word.objects.update(created_at=FIXED_TIME)
        Sentence.objects.bulk_create(
            [
                Sentence(text=f"Same sentence {i % 4}.", translation="같은 해석", difficulty=2, is_reviewed=i % 5 != 2)
                for i in range(29)
            ]
        )
        Sentence.objects.update(created_at=FIXED_TIME)
        cls.visible_words = list(Word.objects.filter(is_reviewed=True).values_list("id", flat=True))
        cls.all_words = list(Word.objects.values_list("id", flat=True))
        cls.visible_sentences = list(Sentence.objects.filter(is_reviewed=True).values_list("id", flat=True))
        cls.all_sentences = list(Sentence.objects.values_list("id", flat=True))

    WORD_ORDERINGS = [
        {},
        {"ordering": "difficulty"},
        {"ordering": "-difficulty"},
        {"ordering": "created_at"},
        {"ordering": "-created_at"},
        {"ordering": "difficulty,-created_at"},
        {"ordering": "-created_at,difficulty"},
        {"ordering": "term"},
        {"ordering": "-term"},
        {"ordering": "difficulty,-term"},
        {"ordering": "meaning"},  # 허용 안 된 칸: 기본 정렬로 돌아간다
        {"ordering": "pk"},
        {"ordering": "-id"},
        {"ordering": ""},
    ]

    def test_tiny_pages_word_orderings_anonymous(self):
        """쪽 크기 1~3, 동점투성이 정렬에서 익명 결과가 기본과 같고 겹침·빠짐이 없다."""
        for size in (1, 2, 3):
            with mock.patch.object(PageNumberPagination, "page_size", size):
                for params in self.WORD_ORDERINGS:
                    self.assert_same_as_default(self.anon, WORDS, params, self.visible_words)

    def test_tiny_pages_word_orderings_reviewer(self):
        """검수자 화면(is_reviewed 가 정렬 앞에 붙는다)도 같고, 검수 대기까지 전부 나온다."""
        with mock.patch.object(PageNumberPagination, "page_size", 2):
            for params in self.WORD_ORDERINGS + [{"shuffle": "seed"}]:
                self.assert_same_as_default(self.reviewer, WORDS, params, self.all_words)
            self.assert_same_as_default(self.reviewer, WORDS, {"shuffle": "seed", "search": "tie"})

    def test_tiny_pages_sentences(self):
        """문장: 같은 본문·같은 난이도·같은 시각. id·-id 정렬 포함."""
        with mock.patch.object(PageNumberPagination, "page_size", 2):
            for params in [
                {},
                {"ordering": "id"},
                {"ordering": "-id"},
                {"ordering": "difficulty"},
                {"ordering": "-created_at"},
                {"ordering": "difficulty,-created_at"},
                {"ordering": "-difficulty,id"},
                {"shuffle": "a"},
            ]:
                self.assert_same_as_default(self.anon, SENTENCES, params, self.visible_sentences)
                self.assert_same_as_default(self.reviewer, SENTENCES, params, self.all_sentences)
            for params in [{"search": "same"}, {"search": "같은"}, {"search": "Same sentence 1."}]:
                self.assert_same_as_default(self.anon, SENTENCES, params)

    def test_searches_with_odd_characters(self):
        """한 글자·한글·없는 말·특수문자·따옴표·표기(커밋) 검색."""
        with mock.patch.object(PageNumberPagination, "page_size", 2):
            for search in ["a", "e", "c", "커밋", "같은", "없는말xyz", "%", "_", "'", '"hi"', "\\", "C++",
                           "it's", "cache", "CACHE", "tie0", "tie, cache", "  "]:
                for params in [{"search": search}, {"search": search, "ordering": "-difficulty"},
                               {"search": search, "shuffle": "s"}]:
                    self.assert_same_as_default(self.anon, WORDS, params)
                    self.assert_same_as_default(self.member, WORDS, params)
            # 널 문자는 앞단에서 400 으로 막힌다. 기본과 같고 500 이 아니다.
            mine = self.anon.get(WORDS, {"search": "a\x00b", "page": 2})
            with mock.patch.object(WordViewSet, "pagination_class", PageNumberPagination):
                theirs = self.anon.get(WORDS, {"search": "a\x00b", "page": 2})
            self.assertEqual((mine.status_code, theirs.status_code), (400, 400))

    def test_filters(self):
        """분류·난이도·정처기 필터, 그리고 무시되는 값과 섞기 조합."""
        with mock.patch.object(PageNumberPagination, "page_size", 3):
            for params in [
                {"category": "git"},
                {"difficulty": "2"},
                {"difficulty": "1"},
                {"is_exam": "true"},
                {"is_exam": "yes"},
                {"exam_subject": "database"},
                {"is_exam": "true", "shuffle": "z", "search": "tie"},
                {"category": "git", "ordering": "-created_at"},
                {"shuffle": "z", "ordering": "difficulty"},
                {"page_size": "1000"},
            ]:
                self.assert_same_as_default(self.anon, WORDS, params)

    def test_bad_filter_values_match_default_status(self):
        """잘못된 필터 값은 기본과 같은 상태코드이고 500 이 아니다."""
        for params in [{"difficulty": "abc"}, {"exam_subject": "nope"}, {"category": "nope"}]:
            mine = self.anon.get(WORDS, params)
            with mock.patch.object(WordViewSet, "pagination_class", PageNumberPagination):
                theirs = self.anon.get(WORDS, params)
            self.assertEqual(mine.status_code, theirs.status_code, params)
            self.assertLess(mine.status_code, 500, params)


class NoUnreviewedLeakTest(PagingHarness):
    """검수 안 된 항목이 뒤집어 읽는 쪽을 포함해 어느 쪽에서도 안 나온다."""

    @classmethod
    def setUpTestData(cls):
        cls._make_users()
        # 미검수를 정렬 맨 끝(z...)과 맨 앞(a...)에 몰아 둔다. 뒤집어 읽는 쪽이 끝부터 센다.
        words = [Word(term=f"m{i:02d}", meaning="뜻", is_reviewed=True) for i in range(30)]
        words += [Word(term=f"zz{i}", meaning="뜻 쿼리", is_reviewed=False) for i in range(7)]
        words += [Word(term=f"aa{i}", meaning="뜻 쿼리", is_reviewed=False) for i in range(5)]
        Word.objects.bulk_create(words)
        sentences = [Sentence(text=f"ok {i}", translation="해석", is_reviewed=True) for i in range(25)]
        sentences += [Sentence(text=f"hidden {i}", translation="해석 쿼리", is_reviewed=False) for i in range(9)]
        Sentence.objects.bulk_create(sentences)
        cls.hidden_words = set(Word.objects.filter(is_reviewed=False).values_list("id", flat=True))
        cls.hidden_sentences = set(Sentence.objects.filter(is_reviewed=False).values_list("id", flat=True))

    def _ids_on_every_page(self, client, url, params):
        ids = []
        first = client.get(url, params).json()
        size = PageNumberPagination.page_size
        last = max(1, (first["count"] + size - 1) // size)
        for number in list(range(1, last + 1)) + ["last"]:
            r = client.get(url, {**params, "page": number})
            self.assertEqual(r.status_code, 200)
            ids += [row["id"] for row in r.json()["results"]]
        return ids, first["count"]

    def test_anonymous_and_member_never_see_unreviewed(self):
        """익명·일반 사용자: 모든 쪽(last 포함)에 미검수 id 가 없고 count 에도 안 잡힌다."""
        cases = [
            (WORDS, self.hidden_words, 30, [{}, {"ordering": "-term"}, {"shuffle": "q"}, {"search": "쿼리"},
                                            {"search": "zz"}, {"search": "aa"}, {"ordering": "-created_at"}]),
            (SENTENCES, self.hidden_sentences, 25, [{}, {"ordering": "-id"}, {"shuffle": "q"}, {"search": "hidden"}]),
        ]
        for size in (1, 4, 20):
            with mock.patch.object(PageNumberPagination, "page_size", size):
                for client in (self.anon, self.member):
                    for url, hidden, visible_count, param_list in cases:
                        for params in param_list:
                            ids, count = self._ids_on_every_page(client, url, params)
                            self.assertFalse(set(ids) & hidden, ("미검수 노출", url, params, size))
                            if not params.get("search"):
                                self.assertEqual(count, visible_count, (url, params))

    def test_unreviewed_detail_still_404_for_member(self):
        """filter_queryset 이 바뀌어 get_object 도 영향을 받는다. 미검수 상세는 여전히 404."""
        for pk in self.hidden_words:
            self.assertEqual(self.member.get(f"{WORDS}{pk}/").status_code, 404)
            self.assertEqual(self.reviewer.get(f"{WORDS}{pk}/").status_code, 200)
        for pk in self.hidden_sentences:
            self.assertEqual(self.anon.get(f"{SENTENCES}{pk}/").status_code, 404)

    def test_reviewer_sees_unreviewed_first(self):
        """검수자는 검수 대기가 앞쪽에 모인다(뒤집어 읽는 쪽에서도 순서 유지)."""
        with mock.patch.object(PageNumberPagination, "page_size", 4):
            ids = self.assert_same_as_default(self.reviewer, WORDS, {})
        self.assertEqual(set(ids[: len(self.hidden_words)]), self.hidden_words)


class CountBoundaryTest(PagingHarness):
    """0개·1개·쪽 크기의 배수·배수+1 에서 쪽 수·마지막 쪽·끝 너머가 기본과 같다."""

    @classmethod
    def setUpTestData(cls):
        cls._make_users()

    def _reset(self, n):
        Word.objects.all().delete()
        Word.objects.bulk_create(
            [Word(term=f"w{i:03d}", meaning="뜻", difficulty=1 + i % 3, is_reviewed=True) for i in range(n)]
        )

    def test_counts_around_page_size(self):
        for size, counts in [(5, [0, 1, 4, 5, 6, 9, 10, 11, 14, 15, 16, 25, 26]), (20, [0, 1, 19, 20, 21, 40, 41, 60, 61])]:
            with mock.patch.object(PageNumberPagination, "page_size", size):
                for n in counts:
                    self._reset(n)
                    for params in [{}, {"ordering": "-difficulty"}, {"shuffle": "b"}]:
                        ids = self.assert_same_as_default(self.anon, WORDS, params)
                        self.assertEqual(len(ids), n, (size, n, params))

    def test_bad_page_numbers_match_default_and_are_404(self):
        """0·-1·999·문자열·소수·아주 큰 수는 기본과 같이 404, 1 과 last 는 200."""
        self._reset(45)
        bad = ["0", "-1", "999", "abc", "1.5", "2.0", "9" * 30, "", " ", "1e3", "NaN", "inf", "LAST", "first"]
        with mock.patch.object(PageNumberPagination, "page_size", 10):
            for value in bad:
                mine = self.anon.get(WORDS, {"page": value})
                with mock.patch.object(WordViewSet, "pagination_class", PageNumberPagination):
                    theirs = self.anon.get(WORDS, {"page": value})
                self.assertEqual(mine.status_code, theirs.status_code, repr(value))
                self.assertLess(mine.status_code, 500, repr(value))
                if mine.status_code == 200:
                    self.assertEqual(mine.json(), theirs.json(), repr(value))
            for value in ["0", "-1", "999", "abc", "1.5", "9" * 30]:
                self.assertEqual(self.anon.get(WORDS, {"page": value}).status_code, 404, value)
            # 공백 낀 숫자·앞자리 0 은 int() 가 받아준다. 기본과 같은 쪽이어야 한다.
            for value in [" 4 ", "04", "5"]:
                mine = self.anon.get(WORDS, {"page": value})
                with mock.patch.object(WordViewSet, "pagination_class", PageNumberPagination):
                    theirs = self.anon.get(WORDS, {"page": value})
                self.assertEqual((mine.status_code, mine.json()), (theirs.status_code, theirs.json()), value)

    def test_response_shape_and_links(self):
        """키는 count/next/previous/results 넷, 링크의 page 값은 앞뒤 쪽 번호."""
        self._reset(45)
        with mock.patch.object(PageNumberPagination, "page_size", 10):
            expected = {
                1: (None, "2"),
                2: ("(none)", "3"),  # DRF 는 1쪽으로 가는 링크에서 page 를 뺀다
                3: ("2", "4"),
                4: ("3", "5"),
                5: ("4", None),
            }
            for number, (prev, nxt) in expected.items():
                body = self.anon.get(WORDS, {"page": number, "ordering": "-term"}).json()
                self.assertEqual(list(body.keys()), ["count", "next", "previous", "results"])
                self.assertEqual(body["count"], 45)
                self.assertEqual((_page_param(body["previous"]), _page_param(body["next"])), (prev, nxt), number)
                self.assertEqual(len(body["results"]), 10 if number < 5 else 5)
                # 쪽 안의 순서가 -term 그대로다(뒤집은 결과를 다시 안 뒤집으면 여기서 깨진다).
                terms = [row["term"] for row in body["results"]]
                self.assertEqual(terms, sorted(terms, reverse=True), number)
                # next 링크가 다른 파라미터(ordering)를 그대로 싣는다.
                if body["next"]:
                    self.assertEqual(parse_qs(urlparse(body["next"]).query).get("ordering"), ["-term"])
