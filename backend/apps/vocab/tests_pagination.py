"""익히기 목록의 쪽 나누기(pagination.ContentPagination)가 기본 쪽 나누기와 같은 결과를 내는가.

새 쪽 나누기는 빠르게 하려고 뒤쪽 절반의 쪽을 정렬을 뒤집어 읽고 결과를
다시 뒤집는다(pagination 머리말). 사용자가 받는 결과는 DRF 기본(PageNumberPagination)과 같아야
한다. 같은 요청을 둘로 보내 쪽마다 목록·개수·다음/이전 링크를 비교한다.
정렬에 동점이 있으면(소문자로 같은 Zeta·zeta, 같은 난이도) 뒤집어 읽을 때 쪽
경계에서 항목이 겹치거나 빠질 수 있어, 그런 값을 거꾸로 읽는 쪽(뒤쪽 절반)에
놓이게 넣는다. 결과 비교만으로는 거꾸로 읽는 길을 탔는지 모르므로 그것도 따로
확인한다.
"""

from __future__ import annotations

import secrets
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.test import TestCase
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient

from .models import Sentence, Word
from .views import SentenceViewSet, WordViewSet

WORDS = "/api/vocab/words/"
SENTENCES = "/api/vocab/sentences/"


def _seed():
    words = []
    for i in range(53):
        words.append(Word(term=f"term{i:03d}", meaning=f"뜻 {i}", description=f"설명 {i}",
                          difficulty=1 + i % 3, category=["git", "database", "devops"][i % 3],
                          is_reviewed=i % 11 != 0))
    # 소문자로 같은 짝: 정렬이 원래 글자로 한 번 더 갈라야 쪽 경계가 흔들리지 않는다.
    # 앞쪽 짝(Go·API)은 거꾸로 안 읽는 쪽에, 뒤쪽 짝(Zeta)은 거꾸로 읽는 쪽에 온다.
    for term in ["Go", "go", "API", "api", "Api", "Zeta", "zeta", "ZETA", "Zulu", "zulu"]:
        words.append(Word(term=term, meaning="뜻 쿼리", description="설명", is_reviewed=True))
    Word.objects.bulk_create(words)
    Sentence.objects.bulk_create([
        Sentence(text=f"Sentence number {i} about a query.", translation=f"해석 {i} 쿼리",
                 difficulty=1 + i % 3, is_reviewed=i % 7 != 0)
        for i in range(64)
    ])


class SamePagesAsDefaultTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _seed()
        cls.staff = get_user_model().objects.create_user(
            email="pager-staff@example.com", password=secrets.token_urlsafe(16), is_staff=True
        )

    def _all_pages(self, client, url, params, *, default: bool):
        """1쪽부터 끝까지 받아 (쪽마다 응답 본문) 목록을 돌려준다."""
        views = (WordViewSet, SentenceViewSet)
        patches = [mock.patch.object(v, "pagination_class", PageNumberPagination) for v in views] if default else []
        for p in patches:
            p.start()
        try:
            first = client.get(url, params)
            self.assertEqual(first.status_code, 200, (url, params))
            pages = [first.json()]
            size = PageNumberPagination.page_size
            last = (pages[0]["count"] + size - 1) // size
            for number in range(2, last + 1):
                response = client.get(url, {**params, "page": number})
                self.assertEqual(response.status_code, 200, (url, params, number))
                pages.append(response.json())
            beyond = client.get(url, {**params, "page": max(last, 1) + 1})
            pages.append({"beyond_status": beyond.status_code})
            last_word = client.get(url, {**params, "page": "last"})
            pages.append({"last_status": last_word.status_code, "last": last_word.json() if last_word.status_code == 200 else None})
            return pages
        finally:
            for p in patches:
                p.stop()

    def _assert_same(self, client, url, params):
        mine = self._all_pages(client, url, params, default=False)
        theirs = self._all_pages(client, url, params, default=True)
        self.assertEqual(mine, theirs, (url, params))
        ids = [row["id"] for page in mine if "results" in page for row in page["results"]]
        self.assertEqual(len(ids), len(set(ids)), "쪽 사이에 같은 항목이 두 번 나왔다")
        if mine and "count" in mine[0]:
            self.assertEqual(len(ids), mine[0]["count"])

    def test_word_orderings_match_default(self):
        client = APIClient()
        for params in [
            {},
            {"ordering": "difficulty,term"},
            {"ordering": "-difficulty,term"},
            {"ordering": "-created_at,term"},
            {"ordering": "term"},
            {"ordering": "-term"},
            # 칸 하나만 고르면 같은 값이 많다. 뷰셋이 pk 를 붙여 순서를 하나로 정한다.
            {"ordering": "difficulty"},
            {"ordering": "-difficulty"},
            {"ordering": "-created_at"},
            {"shuffle": "seed-one"},
            {"category": "git"},
        ]:
            self._assert_same(client, WORDS, params)

    def test_word_searches_match_default(self):
        client = APIClient()
        for params in [
            {"search": "쿼리"},
            {"search": "a"},
            {"search": "term0"},
            {"search": "go"},
            {"search": "없는말"},
            {"search": "term", "ordering": "-difficulty,term"},
        ]:
            self._assert_same(client, WORDS, params)

    def test_sentences_match_default(self):
        client = APIClient()
        for params in [{}, {"ordering": "-created_at,-id"}, {"ordering": "difficulty"}, {"shuffle": "s2"},
                       {"search": "쿼리"}, {"search": "a"}]:
            self._assert_same(client, SENTENCES, params)

    def test_reviewer_view_matches_default(self):
        """검수자는 검수 대기를 앞에 모아 본다(정렬 키가 하나 더 붙는다)."""
        client = APIClient()
        client.force_authenticate(user=self.staff)
        for params in [{}, {"search": "term"}, {"ordering": "-difficulty,term"}, {"ordering": "difficulty"}]:
            self._assert_same(client, WORDS, params)
        for params in [{}, {"ordering": "difficulty"}]:
            self._assert_same(client, SENTENCES, params)

    def test_small_pages_match_default(self):
        """쪽이 작으면 거꾸로 읽는 쪽이 여럿 생겨, 끝이 아닌 구간을 자르는 계산도 거친다."""
        client = APIClient()
        with mock.patch.object(PageNumberPagination, "page_size", 7):
            for url, params in [(WORDS, {}), (WORDS, {"ordering": "-difficulty"}), (WORDS, {"shuffle": "s3"}),
                                (SENTENCES, {}), (SENTENCES, {"ordering": "difficulty"})]:
                self._assert_same(client, url, params)

    def test_back_pages_are_read_reversed(self):
        """뒤쪽 절반의 쪽만 거꾸로 읽는다. 결과가 같아도 이 길을 안 타면 빨라지지 않는다."""
        client = APIClient()
        cases = [(WORDS, {}), (WORDS, {"shuffle": "x"}), (WORDS, {"search": "term"}), (SENTENCES, {})]
        for url, params in cases:
            last = (client.get(url, params).json()["count"] + 19) // 20
            self.assertGreaterEqual(last, 3, (url, params))
            with mock.patch.object(QuerySet, "reverse", autospec=True, side_effect=QuerySet.reverse) as spy:
                client.get(url, {**params, "page": 1})
                self.assertEqual(spy.call_count, 0, (url, params))
                client.get(url, {**params, "page": last})
                self.assertGreater(spy.call_count, 0, (url, params))

    def test_bad_page_numbers_are_404(self):
        client = APIClient()
        for params in [{"page": 0}, {"page": -1}, {"page": "abc"}, {"page": "1.5"}, {"page": 999},
                       {"search": "쿼리", "page": 0}, {"search": "쿼리", "page": "abc"}, {"search": "쿼리", "page": 999}]:
            self.assertEqual(client.get(WORDS, params).status_code, 404, params)
