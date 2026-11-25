"""무작위 고르기를 두 번 읽기로 바꾼 것(sampling.pick_random)이 예전과 같은 것을 고르는가.

예전에는 창의 행을 통째로 모델로 읽어 그중에서 골랐다. 지금은 창에서 번호와 키만 읽어 고른 뒤,
고른 번호의 행만 받은 queryset 으로 다시 읽는다. 지킬 것은 셋이다.

    같은 분포    같은 난수 씨앗이면 예전 코드와 같은 행을 같은 순서로 고른다. 창 크기, 한 바퀴
                 돌기, 겹치지 않게 count 개가 모두 여기에 들어 있다. 예전 코드는 아래
                 _old_pick_random 에 그대로 옮겨 두었다(main 5559065 의 sampling.py).
    검수 게이트  두 번째 읽기에도 받은 queryset 의 조건이 걸린다. 두 읽기 사이에 검수가 취소된
                 행은 나오지 않는다(덜 돌려준다).
    모양         모델 인스턴스, 무작위 순서, 모자라면 있는 만큼, only() 같은 queryset 설정 유지
"""

from __future__ import annotations

import random
from unittest import mock

from django.db import connection, connections
from django.db.models import Exists, OuterRef, Value
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from . import sampling
from .models import Sentence, Word
from .sampling import pick_random

# 예전 main 의 값. sampling 의 상수를 가져다 쓰면 그쪽이 바뀔 때 기준도 같이 바뀌어 차이를 못 본다.
_OLD_MAX_POINTS = 4
_OLD_MIN_WINDOW = 20
_OLD_FROM_START = -1


def _old_pick_random(queryset, count: int) -> list:
    """예전 main 의 pick_random. 창의 행을 통째로 읽어 고른다. 비교 기준으로만 쓴다."""
    if count < 1:
        return []
    points = [random.random() for _ in range(min(count, _OLD_MAX_POINTS))]
    window = max(_OLD_MIN_WINDOW, count)
    parts = [
        queryset.filter(random_key__gte=r).annotate(_part=Value(i)).order_by("random_key")[:window]
        for i, r in enumerate(points)
    ]
    parts.append(queryset.annotate(_part=Value(_OLD_FROM_START)).order_by("random_key")[:window])
    features = connections[parts[0].db].features
    if features.supports_slicing_ordering_in_compound:
        rows_all = list(parts[0].union(*parts[1:], all=True))
    else:
        rows_all = [row for part in parts for row in part]
    by_part: dict = {}
    for row in rows_all:
        by_part.setdefault(row._part, []).append(row)
    for rows in by_part.values():
        rows.sort(key=lambda row: row.random_key)
    head = by_part.get(_OLD_FROM_START, [])
    candidates: dict = {}
    for i in range(len(points)):
        after = by_part.get(i, [])
        for row in after + head[: window - len(after)]:
            candidates.setdefault(row.pk, row)
    chosen = list(candidates.values())
    random.shuffle(chosen)
    return chosen[:count]


def _words(n: int, prefix: str, **extra) -> list[Word]:
    return Word.objects.bulk_create(
        Word(**{"term": f"{prefix}{i:04d}", "meaning": "뜻", "description": "설명", "is_reviewed": True, **extra})
        for i in range(n)
    )


def _pks_new(queryset, count: int, seed: int) -> list[int]:
    random.seed(seed)
    return [row.pk for row in pick_random(queryset, count)]


def _pks_old(queryset, count: int, seed: int) -> list[int]:
    random.seed(seed)
    return [row.pk for row in _old_pick_random(queryset, count)]


class SameChoicesAsBeforeTest(TestCase):
    """같은 씨앗이면 예전 코드와 같은 행을 같은 순서로 고른다."""

    def setUp(self):
        _words(150, "big", category="git")
        _words(15, "small", category="database")
        _words(30, "hide", category="git", is_reviewed=False)

    def assert_same(self, queryset, counts=(1, 3, 4, 12, 15, 25, 60, 200), seeds=range(30)):
        for count in counts:
            for seed in seeds:
                with self.subTest(count=count, seed=seed):
                    self.assertEqual(_pks_new(queryset, count, seed), _pks_old(queryset, count, seed))

    def test_big_pool(self):
        self.assert_same(Word.objects.visible())

    def test_pool_smaller_than_window(self):
        self.assert_same(Word.objects.visible().filter(category="database"))

    def test_keys_bunched_low_so_points_wrap_around(self):
        """키를 모두 0.5 밑으로 몰면 지점 절반이 끝을 넘어 맨 앞에서 이어 읽는다."""
        for i, w in enumerate(Word.objects.order_by("pk")):
            Word.objects.filter(pk=w.pk).update(random_key=i / 1000)
        self.assert_same(Word.objects.visible())

    def test_narrowed_and_excluded_pool(self):
        some = list(Word.objects.visible().filter(category="git").values_list("pk", flat=True)[:40])
        self.assert_same(Word.objects.visible().filter(category="git").exclude(pk__in=some))

    def test_subquery_condition_like_daily_study(self):
        """daily_study 처럼 EXISTS 로 거른 queryset 도 같은 것을 고른다."""
        git = Word.objects.filter(pk=OuterRef("pk"), category="git")
        self.assert_same(Word.objects.visible().filter(~Exists(git)), counts=(1, 5, 20))


class ReviewGateOnSecondReadTest(TestCase):
    """두 번째 읽기에도 받은 queryset 의 조건이 걸린다."""

    def setUp(self):
        self.words = _words(60, "gate", category="git")
        _words(60, "never", category="git", is_reviewed=False)

    def unreview_half_between_reads(self):
        """첫 읽기 직후, 후보의 절반(짝수 번호)을 검수 취소한다. 사람이 Admin 에서 바꾼 것처럼."""
        original = sampling._run

        def run_then_unreview(parts):
            rows = original(parts)
            pks = [row[0] for row in rows if row[0] % 2 == 0]
            Word.objects.filter(pk__in=pks).update(is_reviewed=False)
            return rows

        return self.patch(sampling, "_run", run_then_unreview)

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_row_unreviewed_between_reads_is_dropped(self):
        self.unreview_half_between_reads()
        seen_any = False
        for seed in range(40):
            Word.objects.filter(term__startswith="gate").update(is_reviewed=True)
            random.seed(seed)
            picked = pick_random(Word.objects.visible(), 10)
            seen_any = seen_any or bool(picked)
            for row in picked:
                self.assertTrue(row.is_reviewed)
                self.assertTrue(Word.objects.get(pk=row.pk).is_reviewed, f"검수 취소된 {row.term} 가 나왔다")
                self.assertTrue(row.term.startswith("gate"))
        self.assertTrue(seen_any)

    def test_other_conditions_also_hold_on_second_read(self):
        """검수 말고 다른 조건(설명 있음)도 두 번째 읽기에 걸린다."""
        original = sampling._run

        def run_then_blank(parts):
            rows = original(parts)
            Word.objects.filter(pk__in=[row[0] for row in rows]).update(description="")
            return rows

        self.patch(sampling, "_run", run_then_blank)
        random.seed(1)
        self.assertEqual(pick_random(Word.objects.visible().exclude(description=""), 5), [])

    def test_unreviewed_never_returned_without_interference(self):
        for seed in range(100):
            random.seed(seed)
            for row in pick_random(Word.objects.visible(), 7):
                self.assertTrue(row.term.startswith("gate"), row.term)


class ResultShapeTest(TestCase):
    def test_returns_model_instances_of_the_queryset_model(self):
        Sentence.objects.bulk_create(
            Sentence(text=f"line {i}", translation="해석", is_reviewed=True) for i in range(8)
        )
        picked = pick_random(Sentence.objects.visible().only("id", "text"), 3)
        self.assertEqual(len(picked), 3)
        for row in picked:
            self.assertIsInstance(row, Sentence)
            self.assertIn("translation", row.get_deferred_fields(), "only() 가 두 번째 읽기에서 풀렸다")

    def test_fewer_rows_than_count_returns_all_once(self):
        rows = _words(5, "few")
        for seed in range(20):
            random.seed(seed)
            picked = [w.pk for w in pick_random(Word.objects.visible(), 50)]
            self.assertEqual(sorted(picked), sorted(w.pk for w in rows))

    def test_order_is_random(self):
        _words(6, "order")
        orders = set()
        for seed in range(30):
            random.seed(seed)
            orders.add(tuple(w.pk for w in pick_random(Word.objects.visible(), 6)))
        self.assertGreater(len(orders), 5, "늘 같은 순서로 돌려준다")

    def test_no_duplicates_when_windows_overlap(self):
        _words(25, "dup")
        for seed in range(50):
            random.seed(seed)
            picked = [w.pk for w in pick_random(Word.objects.visible(), 20)]
            self.assertEqual(len(picked), len(set(picked)))
            self.assertEqual(len(picked), 20)

    def test_two_queries_and_one_for_empty_pool(self):
        _words(30, "q")
        with CaptureQueriesContext(connection) as ctx:
            pick_random(Word.objects.visible(), 4)
        self.assertEqual(len(ctx.captured_queries), 2)
        self.assertNotIn('"description"', ctx.captured_queries[0]["sql"], "창 읽기가 행 전체를 읽는다")

        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(pick_random(Word.objects.visible().filter(term="없음"), 4), [])
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_zero_and_negative_count(self):
        _words(3, "z")
        self.assertEqual(pick_random(Word.objects.visible(), 0), [])
        self.assertEqual(pick_random(Word.objects.visible(), -1), [])
