"""익히기 목록이 개수를 기억할 때(pagination.TailReversingPaginator) 깨뜨려 보는 테스트.

목록 쪽 나누기는 전체 개수를 5분 동안 CACHES["counts"] 에 기억하고, 기억한 값이
낡았으면 몇몇 경우에 다시 센다. 약속은 이렇다.

- 쪽마다 받는 항목(results)과 next/previous 는 지금 DB 기준 DRF 기본
  (PageNumberPagination)과 같다. 기억한 개수가 낡았어도 같다.
- count 는 앞쪽 쪽에서만 낡을 수 있다(기억한 값 아니면 지금 값). 마지막 쪽과
  "last" 는 지금 값이다.
- 검수 안 된 항목은 일반 사용자의 어느 쪽에도 안 나오고, 검수자가 센 개수가
  일반 사용자에게 가지 않는다.
- 없는 쪽은 404, 있는 쪽은 200 이다. 기억한 개수 때문에 이것이 바뀌지 않는다.

테스트 실행 중 CACHES["counts"] 는 DummyCache 라 여기서는 LocMemCache 로 바꿔 둔다.
"""

from __future__ import annotations

import random
import secrets
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient

from .models import Sentence, Word
from .pagination import TailReversingPaginator
from .views import SentenceViewSet, WordViewSet

WORDS = "/api/vocab/words/"
SENTENCES = "/api/vocab/sentences/"

REMEMBERING = override_settings(
    CACHES={
        **settings.CACHES,
        "counts": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "list-count-dynamic",
            "TIMEOUT": 300,
        },
    }
)


def _make_user(prefix: str, **extra):
    return get_user_model().objects.create_user(
        email=f"{prefix}-{secrets.token_hex(4)}@example.com",
        password=secrets.token_urlsafe(16),
        **extra,
    )


@REMEMBERING
class RememberingHarness(TestCase):
    """기억하는 캐시를 켜 두고, 같은 요청을 기본 쪽 나누기로도 보내는 도구."""

    @classmethod
    def setUpTestData(cls):
        cls.member_user = _make_user("lcdyn-member")
        cls.staff_user = _make_user("lcdyn-staff", is_staff=True)

    def setUp(self):
        caches["counts"].clear()
        self.anon = APIClient()
        self.member = APIClient()
        self.member.force_authenticate(user=self.member_user)
        self.reviewer = APIClient()
        self.reviewer.force_authenticate(user=self.staff_user)

    def get(self, client, url, params, *, default: bool = False):
        """(상태, 본문 또는 None). default 면 DRF 기본 쪽 나누기로 보낸다."""
        patches = (
            [mock.patch.object(v, "pagination_class", PageNumberPagination) for v in (WordViewSet, SentenceViewSet)]
            if default
            else []
        )
        for p in patches:
            p.start()
        try:
            r = client.get(url, params)
        finally:
            for p in patches:
                p.stop()
        self.assertIn(r.status_code, (200, 404), (url, params, r.content[:300]))
        return r.status_code, (r.json() if r.status_code == 200 else None)

    def assert_page_like_default(self, mine, theirs, *, stale_count: int | None, ctx):
        """results·next·previous 는 기본과 같고, count 는 지금 값이나 기억한 값."""
        self.assertEqual(mine[0], theirs[0], ("상태코드가 다르다", ctx, mine, theirs))
        if mine[0] != 200:
            return
        a, b = mine[1], theirs[1]
        self.assertEqual(set(a), {"count", "next", "previous", "results"}, ctx)
        self.assertEqual([r["id"] for r in a["results"]], [r["id"] for r in b["results"]], ("results", ctx))
        self.assertEqual(a["results"], b["results"], ("results 본문", ctx))
        self.assertEqual(a["next"], b["next"], ("next", ctx))
        self.assertEqual(a["previous"], b["previous"], ("previous", ctx))
        allowed = {b["count"]} if stale_count is None else {b["count"], stale_count}
        self.assertIn(a["count"], allowed, ("count", ctx))
        if b["next"] is None:
            self.assertEqual(a["count"], b["count"], ("마지막 쪽의 count 는 지금 값이어야 한다", ctx))

    def walk(self, client, url, params, *, default: bool = False) -> list:
        """1쪽부터 next 링크를 따라 끝까지 받은 (상태, 본문) 목록."""
        out = [self.get(client, url, params, default=default)]
        guard = 0
        while out[-1][0] == 200 and out[-1][1]["next"]:
            guard += 1
            self.assertLess(guard, 500, "next 가 끝나지 않는다")
            nxt = out[-1][1]["next"]
            query = nxt.split("?", 1)[1]
            out.append(self.get(client, f"{url}?{query}", {}, default=default))
        return out


class StaleCountGridTest(RememberingHarness):
    """기억한 개수 C 와 지금 개수 N 의 모든 조합에서 쪽 하나씩.

    쪽마다 캐시를 비우고 C 개가 보일 때 1쪽을 받아 C 를 기억시킨 뒤, 보이는 항목을
    N 개로 바꾸고(위치는 무작위) 그 쪽을 받는다. 앞서 받은 쪽이 다시 센 값을
    남기지 않도록 쪽마다 처음부터 한다. page_size 배수 근처, 0개, 쪽 수가 늘거나
    줄어드는 경우가 모두 이 격자에 든다.
    """

    ITEMS = 9
    ORDERINGS = [{}, {"ordering": "-term"}, {"shuffle": "s1"}, {"ordering": "difficulty"}]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Word.objects.bulk_create(
            [
                Word(term=t, meaning=f"뜻 {i}", difficulty=1 + i % 3, is_reviewed=False)
                for i, t in enumerate(["Api", "api", "beta", "Cache", "delta", "go", "Go", "zeta", "Zulu"])
            ]
        )
        cls.word_ids = list(Word.objects.order_by("pk").values_list("pk", flat=True))

    def _show(self, ids):
        Word.objects.update(is_reviewed=False)
        Word.objects.filter(pk__in=ids).update(is_reviewed=True)

    def test_every_remembered_and_actual_count(self):
        """C, N 이 0~9 인 모든 조합, 쪽 크기 2·3, 모든 쪽과 "last" 에서 기본과 같다."""
        for size in (2, 3):
            with mock.patch.object(PageNumberPagination, "page_size", size):
                for c in range(self.ITEMS + 1):
                    for n in range(self.ITEMS + 1):
                        rng = random.Random(f"{size}-{c}-{n}")
                        before, after = rng.sample(self.word_ids, c), rng.sample(self.word_ids, n)
                        params = self.ORDERINGS[(c * 10 + n) % len(self.ORDERINGS)]
                        pages = list(range(1, -(-max(c, n, 1) // size) + 2)) + ["last"]
                        for page in pages:
                            ctx = dict(size=size, c=c, n=n, page=page, params=params)
                            caches["counts"].clear()
                            self._show(before)
                            primed = self.get(self.anon, WORDS, params)
                            self.assertEqual(primed[1]["count"], c, ctx)
                            self._show(after)
                            q = {**params, "page": page}
                            mine = self.get(self.anon, WORDS, q)
                            theirs = self.get(self.anon, WORDS, q, default=True)
                            self.assert_page_like_default(mine, theirs, stale_count=c, ctx=ctx)
                            if page == "last":
                                self.assertEqual(mine, theirs, ctx)
                            if mine[0] == 200:
                                shown = {r["id"] for r in mine[1]["results"]}
                                self.assertLessEqual(shown, set(after), ("미검수가 나왔다", ctx))


class WalkAfterChangeTest(RememberingHarness):
    """개수를 기억한 뒤 데이터를 바꾸고 next 를 따라 끝까지 넘긴다.

    모든 쪽이 기본과 같고, 이어 붙인 id 에 겹침·빠짐이 없어야 한다.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Word.objects.bulk_create(
            [
                Word(
                    term=f"{'T' if i % 4 == 0 else 't'}{i:02d}",
                    meaning=f"뜻 {i} {'쿼리' if i % 3 == 0 else '캐시'}",
                    description="설명",
                    difficulty=1 + i % 3,
                    category="git" if i % 2 else "database",
                    is_reviewed=i % 7 != 3,
                )
                for i in range(47)
            ]
        )
        Sentence.objects.bulk_create(
            [Sentence(text=f"Sentence {i} about a query.", translation=f"해석 {i}", is_reviewed=i % 5 != 1) for i in range(31)]
        )

    def _ordered_terms(self):
        return list(Word.objects.order_by("term", "pk"))

    def _mutations(self):
        def add_front():
            Word.objects.bulk_create([Word(term=f"aa{i}", meaning="뜻 쿼리", is_reviewed=True) for i in range(6)])

        def add_back():
            Word.objects.bulk_create([Word(term=f"zz{i}", meaning="뜻 캐시", is_reviewed=True) for i in range(6)])

        def delete_front():
            Word.objects.filter(pk__in=[w.pk for w in self._ordered_terms()[:4]]).delete()

        def delete_middle():
            Word.objects.filter(pk__in=[w.pk for w in self._ordered_terms()[20:25]]).delete()

        def unreview_spread():
            Word.objects.filter(pk__in=[w.pk for w in self._ordered_terms()[::5]]).update(is_reviewed=False)

        def review_hidden():
            Word.objects.filter(is_reviewed=False).update(is_reviewed=True)

        def same_count_shifted():
            delete_front()
            Word.objects.bulk_create([Word(term=f"zy{i}", meaning="뜻", is_reviewed=True) for i in range(4)])

        def everything_gone():
            Word.objects.update(is_reviewed=False)

        return [add_front, add_back, delete_front, delete_middle, unreview_spread, review_hidden,
                same_count_shifted, everything_gone]

    PARAMS = [
        {},
        {"ordering": "-term"},
        {"ordering": "difficulty"},
        {"shuffle": "seed-1"},
        {"search": "쿼리"},
        {"category": "git"},
        {"category": "git", "shuffle": "x", "difficulty": "2"},
    ]

    def _check(self, client, params, mutate, size):
        ctx = dict(client=client.handler._force_user, params=params, mutate=mutate.__name__, size=size)
        caches["counts"].clear()
        # 1쪽과 last 를 받아 바뀌기 전 개수를 기억시킨다.
        before = self.get(client, WORDS, params)[1]["count"]
        self.get(client, WORDS, {**params, "page": "last"})
        self.get(client, WORDS, params)
        mutate()
        mine = self.walk(client, WORDS, params)
        theirs = self.walk(client, WORDS, params, default=True)
        self.assertEqual(len(mine), len(theirs), ("쪽 수가 다르다", ctx))
        for i, (a, b) in enumerate(zip(mine, theirs)):
            self.assert_page_like_default(a, b, stale_count=before, ctx={**ctx, "page": i + 1})
        ids = [r["id"] for _, body in mine for r in body["results"]]
        self.assertEqual(len(ids), len(set(ids)), ("겹침", ctx))
        self.assertEqual(len(ids), theirs[0][1]["count"], ("빠짐", ctx))
        if client is not self.reviewer:
            hidden = set(Word.objects.filter(is_reviewed=False).values_list("pk", flat=True))
            self.assertFalse(hidden & set(ids), ("미검수가 나왔다", ctx))
        if not params:
            want = Word.objects.all() if client is self.reviewer else Word.objects.filter(is_reviewed=True)
            self.assertEqual(set(ids), set(want.values_list("pk", flat=True)), ctx)
        # 바뀐 뒤 last 는 count 까지 기본과 같다.
        last = {**params, "page": "last"}
        self.assertEqual(self.get(client, WORDS, last), self.get(client, WORDS, last, default=True), ctx)

    def test_walk_after_change_anon_member_reviewer(self):
        """추가·삭제·검수 취소·검수 완료·개수는 같고 위치만 바뀜·전부 사라짐 뒤 끝까지 넘긴다."""
        for size in (3, 5):
            with mock.patch.object(PageNumberPagination, "page_size", size):
                for client in (self.anon, self.member, self.reviewer):
                    for params in self.PARAMS:
                        for mutate in self._mutations():
                            with transaction.atomic():
                                self._check(client, params, mutate, size)
                                transaction.set_rollback(True)

    def test_sentences_walk_after_unreview(self):
        """문장 목록도 같다: 기억한 뒤 검수 취소·추가."""
        with mock.patch.object(PageNumberPagination, "page_size", 4):
            for client in (self.anon, self.reviewer):
                for params in ({}, {"ordering": "-id"}, {"shuffle": "q"}, {"search": "query"}):
                    with transaction.atomic():
                        caches["counts"].clear()
                        before = self.get(client, SENTENCES, params)[1]["count"]
                        Sentence.objects.filter(pk__in=list(Sentence.objects.order_by("pk").values_list("pk", flat=True)[::3])).update(
                            is_reviewed=False
                        )
                        Sentence.objects.create(text="Zzz new sentence query.", translation="새", is_reviewed=True)
                        mine = self.walk(client, SENTENCES, params)
                        theirs = self.walk(client, SENTENCES, params, default=True)
                        self.assertEqual(len(mine), len(theirs), params)
                        for a, b in zip(mine, theirs):
                            self.assert_page_like_default(a, b, stale_count=before, ctx=params)
                        if client is self.anon:
                            hidden = set(Sentence.objects.filter(is_reviewed=False).values_list("pk", flat=True))
                            shown = {r["id"] for _, body in mine for r in body["results"]}
                            self.assertFalse(hidden & shown, params)
                        transaction.set_rollback(True)


class ReviewGateTest(RememberingHarness):
    """검수 게이트: 미검수 항목과 검수자 개수가 일반 사용자에게 새지 않는다."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Word.objects.bulk_create(
            [Word(term=f"g{i:02d}", meaning="뜻 쿼리", category="git", is_reviewed=i % 3 == 0) for i in range(30)]
        )
        cls.visible = set(Word.objects.filter(is_reviewed=True).values_list("pk", flat=True))
        cls.total = Word.objects.count()

    def test_reviewer_count_not_shared_with_users(self):
        """검수자가 먼저 센 뒤 익명·회원이 받는 count 는 검수된 개수다(그 반대도)."""
        for params in ({}, {"category": "git"}, {"search": "쿼리"}, {"shuffle": "a"}, {"ordering": "-term"}):
            for size in (3, 20):
                with mock.patch.object(PageNumberPagination, "page_size", size):
                    caches["counts"].clear()
                    self.assertEqual(self.get(self.reviewer, WORDS, params)[1]["count"], self.total)
                    for client in (self.anon, self.member):
                        for page in (1, 2, "last"):
                            status, body = self.get(client, WORDS, {**params, "page": page})
                            if status != 200:
                                continue
                            self.assertEqual(body["count"], len(self.visible), (params, size, page))
                            self.assertLessEqual({r["id"] for r in body["results"]}, self.visible)
                    caches["counts"].clear()
                    self.assertEqual(self.get(self.member, WORDS, params)[1]["count"], len(self.visible))
                    self.assertEqual(self.get(self.reviewer, WORDS, params)[1]["count"], self.total, params)

    def test_unreview_between_pick_and_fetch(self):
        """번호를 고른 직후 그중 하나가 검수 취소돼도 그 항목은 안 나간다."""
        original = TailReversingPaginator._pick_ids
        dropped = []

        def pick_then_unreview(paginator, bottom):
            ids = original(paginator, bottom)
            if ids:
                Word.objects.filter(pk=ids[0]).update(is_reviewed=False)
                dropped.append(ids[0])
            return ids

        with mock.patch.object(PageNumberPagination, "page_size", 4):
            for page in (1, 2, 3, "last"):
                with transaction.atomic():
                    with mock.patch.object(TailReversingPaginator, "_pick_ids", pick_then_unreview):
                        status, body = self.get(self.anon, WORDS, {"page": page})
                    self.assertEqual(status, 200, page)
                    self.assertNotIn(dropped[-1], {r["id"] for r in body["results"]}, page)
                    transaction.set_rollback(True)

    def test_unreview_after_remember_never_shows_item(self):
        """기억한 뒤 검수 취소된 항목은 앞쪽·뒤쪽 어느 쪽에서도 안 나오고 count 는 둘 중 하나."""
        with mock.patch.object(PageNumberPagination, "page_size", 2):
            before = self.get(self.anon, WORDS, {})[1]["count"]
            gone = sorted(self.visible)[::2]
            Word.objects.filter(pk__in=gone).update(is_reviewed=False)
            now = len(self.visible) - len(gone)
            for page in range(1, 7):
                status, body = self.get(self.anon, WORDS, {"page": page})
                if status == 200:
                    self.assertFalse(set(gone) & {r["id"] for r in body["results"]}, page)
                    self.assertIn(body["count"], (before, now), page)


class CountKeyTest(RememberingHarness):
    """다른 조건은 다른 키, 개수가 같은 조건(정렬·섞기 시드만 다름)은 같은 키."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Word.objects.bulk_create(
            [
                Word(
                    term=f"k{i:02d}",
                    meaning="쿼리 뜻" if i % 2 else "캐시 뜻",
                    category=["git", "database", "devops"][i % 3],
                    difficulty=1 + i % 3,
                    is_exam=i % 4 == 0,
                    exam_subject="database" if i % 4 == 0 else "",
                    is_reviewed=True,
                )
                for i in range(25)
            ]
        )
        Sentence.objects.bulk_create([Sentence(text=f"s{i} query", translation="뜻", is_reviewed=True) for i in range(7)])

    CONDITIONS = [
        {},
        {"category": "git"},
        {"category": "database"},
        {"difficulty": "1"},
        {"difficulty": "2"},
        {"is_exam": "true"},
        {"is_exam": "false"},
        {"exam_subject": "database"},
        {"search": "쿼리"},
        {"search": "캐시"},
        {"search": "k0"},
        {"search": "k1"},
        {"search": "k0 k1"},
        {"search": "%"},
        {"search": "_"},
        {"category": "git", "difficulty": "1"},
    ]

    def test_different_conditions_get_their_own_count(self):
        """조건을 바꿔 가며 받아도 count 가 기본(지금 DB)과 같다. 순서를 뒤집어도 같다."""
        with mock.patch.object(PageNumberPagination, "page_size", 3):
            for order in (self.CONDITIONS, list(reversed(self.CONDITIONS))):
                caches["counts"].clear()
                for params in order:
                    for page in (1, "last"):
                        q = {**params, "page": page}
                        self.assertEqual(self.get(self.anon, WORDS, q), self.get(self.anon, WORDS, q, default=True), q)
                # 문장과 단어는 같은 조건이어도 다른 표다.
                self.assertEqual(self.get(self.anon, SENTENCES, {})[1]["count"], 7)
                self.assertEqual(self.get(self.anon, WORDS, {})[1]["count"], 25)

    def _count_queries(self, client, url, params) -> int:
        with CaptureQueriesContext(connection) as ctx:
            self.get(client, url, params)
        return sum("COUNT(" in q["sql"].upper() for q in ctx.captured_queries)

    def test_order_and_seed_share_one_count(self):
        """정렬·섞기 시드만 다른 앞쪽 쪽은 다시 세지 않는다(같은 키)."""
        self.assertEqual(self._count_queries(self.anon, WORDS, {"category": "git"}), 1)
        for params in (
            {"category": "git", "shuffle": "a"},
            {"category": "git", "shuffle": "b"},
            {"category": "git", "ordering": "-term"},
            {"category": "git", "ordering": "difficulty"},
        ):
            self.assertEqual(self._count_queries(self.anon, WORDS, params), 0, params)
        # 검색 순위(정렬을 안 고르면 붙는다) 가 있어도 같은 키.
        self.assertEqual(self._count_queries(self.anon, WORDS, {"search": "쿼리", "ordering": "term"}), 1)
        self.assertEqual(self._count_queries(self.anon, WORDS, {"search": "쿼리"}), 0)
        # 익명과 회원은 같은 조건이다.
        self.assertEqual(self._count_queries(self.member, WORDS, {"search": "쿼리"}), 0)
        # 검수자는 다른 조건이다.
        self.assertEqual(self._count_queries(self.reviewer, WORDS, {"search": "쿼리"}), 1)


class PageBoundaryTest(RememberingHarness):
    """개수를 기억한 상태에서 이상한 쪽 번호. 상태와 본문이 기본과 같아야 한다."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Word.objects.bulk_create([Word(term=f"b{i:02d}", meaning="뜻", is_reviewed=True) for i in range(21)])

    PAGES = ["0", "-1", "-99", "abc", "9" * 30, "1.0", "2.5", " 2", "2 ", "+2", "1e1", "0x2", "last", "LAST",
             "", "٢", "２", "2", "3", "4", "None", "true", "9" * 5000]

    def _compare_all(self, ctx):
        for page in self.PAGES:
            q = {"page": page}
            self.assertEqual(self.get(self.anon, WORDS, q), self.get(self.anon, WORDS, q, default=True), (ctx, page[:20]))

    def test_odd_page_numbers_with_fresh_and_stale_count(self):
        """기억한 개수가 맞을 때, 늘었을 때, 줄었을 때, 0 이 됐을 때 모두 기본과 같다."""
        with mock.patch.object(PageNumberPagination, "page_size", 10):
            self.get(self.anon, WORDS, {})
            self._compare_all("fresh")
            for label, change in (
                ("grew", lambda: Word.objects.bulk_create([Word(term=f"c{i}", meaning="뜻", is_reviewed=True) for i in range(10)])),
                ("shrank", lambda: Word.objects.filter(term__startswith="b1").delete()),
                ("empty", lambda: Word.objects.update(is_reviewed=False)),
            ):
                with transaction.atomic():
                    caches["counts"].clear()
                    self.get(self.anon, WORDS, {})
                    change()
                    for page in self.PAGES:
                        caches["counts"].clear()
                        q = {"page": page}
                        # 쪽마다 바뀌기 전 개수(21)를 다시 심는다. 앞 쪽이 다시 센 값을 남기므로.
                        self._plant_stale(21)
                        self.assert_page_like_default(
                            self.get(self.anon, WORDS, q),
                            self.get(self.anon, WORDS, q, default=True),
                            stale_count=21,
                            ctx=(label, page[:20]),
                        )
                    transaction.set_rollback(True)

    def _plant_stale(self, value):
        """지금 익명 단어 목록의 키에 낡은 개수를 넣는다."""
        qs = Word.objects.visible().order_by("pk")
        paginator = TailReversingPaginator(qs, 10)
        caches["counts"].set(paginator._count_key, value)

    def test_page_size_param_is_ignored(self):
        """page_size·limit 를 보내도 쪽 크기는 그대로다(기본과 같다)."""
        for q in ({"page_size": "1000"}, {"page_size": "0"}, {"limit": "5"}, {"page_size": "-1", "page": "2"}):
            self.assertEqual(self.get(self.anon, WORDS, q), self.get(self.anon, WORDS, q, default=True), q)

    def test_planted_key_matches_view_key(self):
        """_plant_stale 이 뷰와 같은 키를 쓰는지(위 테스트의 전제)."""
        self._plant_stale(999)
        self.assertEqual(self.get(self.anon, WORDS, {})[1]["count"], 999)
