"""익히기 목록이 전체 개수를 기억하는 동작(pagination.TailReversingPaginator).

테스트 설정은 개수를 기억하지 않는다(settings 의 CACHES["counts"] 가 테스트에서
DummyCache). 여기서만 메모리 캐시로 바꿔 시험한다.

기억한 개수는 낡을 수 있다(5분 동안 단어가 공개·삭제된다). 뒤쪽 절반은 끝에서
세어 읽어서 개수가 틀리면 쪽 경계에서 항목이 빠지거나 겹친다. 그래서 낡은 개수를
기억한 채로 쪽을 끝까지 넘겨도 모든 항목이 한 번씩만 나오는지를 주로 본다.
"""

from __future__ import annotations

import secrets
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient

from .models import Word
from .pagination import TailReversingPaginator
from .views import SentenceViewSet, WordViewSet

WORDS = "/api/vocab/words/"

REMEMBER = {
    **settings.CACHES,
    "counts": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "list-counts-test",
        "TIMEOUT": 300,
    },
}


def _words(start: int, n: int, *, is_reviewed: bool = True) -> None:
    Word.objects.bulk_create(
        Word(term=f"w{i:03d}", meaning=f"뜻 {i}", description=f"설명 {i}",
             category=["git", "database"][i % 2], is_reviewed=is_reviewed)
        for i in range(start, start + n)
    )


def _count_queries(ctx: CaptureQueriesContext) -> int:
    return sum("COUNT(" in q["sql"].upper() for q in ctx.captured_queries)


@override_settings(CACHES=REMEMBER)
class RememberedCountTest(TestCase):
    """단어 60개(3쪽). 1·2쪽은 앞쪽이라 기억한 개수를 쓰고, 3쪽은 다시 센다."""

    def setUp(self):
        caches["counts"].clear()
        _words(0, 60)
        self.client = APIClient()

    def get(self, params: dict, client: APIClient | None = None) -> tuple[dict, int]:
        with CaptureQueriesContext(connection) as ctx:
            response = (client or self.client).get(WORDS, params)
        self.assertEqual(response.status_code, 200, (params, response.content[:200]))
        return response.json(), _count_queries(ctx)

    def walk(self, params: dict | None = None, client: APIClient | None = None) -> list[int]:
        """1쪽부터 next 가 없을 때까지 넘기며 id 를 모은다."""
        ids, page = [], 1
        while True:
            body, _ = self.get({**(params or {}), "page": page}, client)
            ids += [row["id"] for row in body["results"]]
            if not body["next"]:
                return ids
            page += 1

    def visible_ids_in_order(self, params: dict | None = None, client: APIClient | None = None) -> list[int]:
        """기본 쪽 나누기로 넘긴 결과(정답)."""
        with mock.patch.object(WordViewSet, "pagination_class", PageNumberPagination):
            ids, page = [], 1
            while True:
                body = (client or self.client).get(WORDS, {**(params or {}), "page": page}).json()
                ids += [row["id"] for row in body["results"]]
                if not body["next"]:
                    return ids
                page += 1

    def test_front_page_counts_once_then_remembers(self):
        first, counted = self.get({"page": 1})
        self.assertEqual((first["count"], counted), (60, 1))
        again, counted = self.get({"page": 1})
        self.assertEqual((again["count"], counted), (60, 0))
        second, counted = self.get({"page": 2})
        self.assertEqual((second["count"], counted), (60, 0))

    def test_back_page_always_counts(self):
        self.get({"page": 1})
        body, counted = self.get({"page": 3})
        self.assertEqual((body["count"], counted, len(body["results"])), (60, 1, 20))

    def test_shuffle_seeds_share_one_count(self):
        self.get({"page": 1, "shuffle": "seed-a"})
        body, counted = self.get({"page": 1, "shuffle": "seed-b"})
        self.assertEqual((body["count"], counted), (60, 0))

    def test_different_filters_are_counted_apart(self):
        self.get({"page": 1})
        git, _ = self.get({"page": 1, "category": "git"})
        found, _ = self.get({"page": 1, "search": "w01"})
        self.assertEqual(git["count"], 30)
        self.assertEqual(found["count"], 10)  # w010 ~ w019
        whole, counted = self.get({"page": 1})
        self.assertEqual((whole["count"], counted), (60, 0))

    def test_reviewer_count_does_not_reach_anonymous(self):
        """검수자 목록은 미검수까지 센다. 그 개수가 일반 사용자 목록에 나오면 안 된다."""
        _words(100, 15, is_reviewed=False)
        staff = get_user_model().objects.create_user(
            email=f"count-staff-{secrets.token_hex(4)}@example.com",
            password=secrets.token_urlsafe(16), is_staff=True,
        )
        reviewer = APIClient()
        reviewer.force_authenticate(user=staff)
        self.assertEqual(reviewer.get(WORDS, {"page": 1}).json()["count"], 75)
        body, counted = self.get({"page": 1})
        self.assertEqual((body["count"], counted), (60, 1))

    def test_added_words_are_neither_lost_nor_doubled(self):
        """개수를 기억한 뒤 단어가 늘어도 쪽을 끝까지 넘기면 모두 한 번씩 나온다."""
        self.get({"page": 1})
        _words(60, 15)  # w060 ~ w074, ABC순 맨 뒤
        Word.objects.bulk_create(  # 앞쪽 쪽에도 끼어들게
            Word(term=f"a{i}", meaning="뜻", is_reviewed=True) for i in range(5)
        )
        stale, _ = self.get({"page": 1})
        # 앞쪽 쪽은 기억한 개수를 그대로 보여 준다(5분까지 몇 개 틀릴 수 있다).
        self.assertEqual(stale["count"], 60)
        self.assertEqual(self.walk(), self.visible_ids_in_order())

    def test_every_ordering_survives_a_stale_count(self):
        """섞기·검색·검수자 정렬에서도 낡은 개수로 끝까지 넘기면 모두 한 번씩 나온다."""
        staff = get_user_model().objects.create_user(
            email=f"walk-staff-{secrets.token_hex(4)}@example.com",
            password=secrets.token_urlsafe(16), is_staff=True,
        )
        reviewer = APIClient()
        reviewer.force_authenticate(user=staff)
        cases = [
            ("섞기", {"shuffle": "seed"}, self.client),
            ("검색", {"search": "w"}, self.client),
            ("ABC순", {"ordering": "term"}, self.client),
            ("검수자", {}, reviewer),
        ]
        for n, (label, params, client) in enumerate(cases):
            with self.subTest(label):
                self.get({**params, "page": 1}, client)
                _words(200 + n * 20, 13)
                _words(400 + n * 20, 4, is_reviewed=False)
                self.assertEqual(self.walk(params, client), self.visible_ids_in_order(params, client))

    def test_shrunk_to_a_full_page_has_no_next(self):
        """60개를 기억한 뒤 40개가 되면 2쪽은 꽉 찬 채로 마지막 쪽이다."""
        self.get({"page": 1})
        Word.objects.filter(term__gte="w040").delete()
        body, _ = self.get({"page": 2})
        self.assertEqual((body["count"], len(body["results"])), (40, 20))
        self.assertIsNone(body["next"])

    def test_single_page_list_also_remembers(self):
        Word.objects.filter(term__gte="w015").delete()
        first, counted = self.get({"page": 1})
        self.assertEqual((first["count"], counted), (15, 1))
        again, counted = self.get({"page": 1})
        self.assertEqual((again["count"], counted), (15, 0))

    def test_grown_single_page_is_noticed(self):
        Word.objects.filter(term__gte="w015").delete()
        self.get({"page": 1})
        _words(15, 3)
        body, counted = self.get({"page": 1})
        self.assertEqual((body["count"], counted, len(body["results"])), (18, 1, 18))

    def test_removed_words_are_noticed(self):
        """기억한 개수보다 행이 적으면 다시 센다."""
        self.get({"page": 1})
        Word.objects.filter(term__gte="w010").delete()
        body, counted = self.get({"page": 1})
        self.assertEqual((body["count"], counted, len(body["results"])), (10, 1, 10))
        self.assertIsNone(body["next"])

    def test_page_beyond_remembered_count_is_found(self):
        self.get({"page": 1})
        _words(60, 30)  # 90개, 5쪽
        body, _ = self.get({"page": 5})
        self.assertEqual((body["count"], len(body["results"])), (90, 10))

    def test_last_uses_the_real_count(self):
        """"last" 는 개수로 쪽 번호를 정한다. 줄었으면 줄어든 마지막 쪽을 준다."""
        self.get({"page": 1})
        Word.objects.filter(term__gte="w030").delete()  # 30개, 2쪽
        body, _ = self.get({"page": "last"})
        self.assertEqual(body["count"], 30)
        self.assertEqual([row["id"] for row in body["results"]], self.visible_ids_in_order()[20:])


class RowFetchKeepsReviewGateTest(TestCase):
    """번호를 고른 뒤 그 행을 가져올 때도 같은 조건으로 거른다.

    두 쿼리 사이에 검수가 취소되면 고른 번호에 미검수 항목이 들 수 있다.
    고르는 단계를 바꿔 끼워 그 상황을 만든다.
    """

    def test_unreviewed_id_is_dropped(self):
        _words(0, 3)
        hidden = Word.objects.create(term="hidden", meaning="뜻", is_reviewed=False)
        shown = Word.objects.get(term="w000")
        with mock.patch.object(TailReversingPaginator, "_pick_ids", return_value=[shown.pk, hidden.pk]):
            body = APIClient().get(WORDS).json()
        self.assertEqual([row["id"] for row in body["results"]], [shown.pk])

    def test_sentences_use_the_same_paginator(self):
        self.assertIs(SentenceViewSet.pagination_class, WordViewSet.pagination_class)
