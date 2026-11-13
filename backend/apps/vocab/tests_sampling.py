"""무작위 고르기(sampling.pick_random)가 고르게, 조건대로 고르는가.

표 전체를 섞는 ORDER BY RANDOM() 대신 무작위 키 칸으로 몇 행만 읽어 고른다
(sampling 머리말). 빨라지는 대신 지켜야 할 것이 있다.

  - 몇 개만 늘 뽑히지 않는다. id 범위로 지점을 찍던 첫 시도는 앞에 빈 id 가
    많은 행이 거의 매번 뽑혔다. 분류별로 id 가 몰린 콘텐츠에서 같은 분류
    보기가 늘 같은 몇 개였다.
  - queryset 의 조건과 제외를 지킨다(검수 게이트도 여기에 들어 있다).
  - 풀이 작거나 비어도, 찍은 지점 뒤에 행이 없어도 고를 수 있는 만큼 고른다.
"""

from __future__ import annotations

from collections import Counter
from itertools import count

from django.test import TestCase

from .models import Word
from .sampling import pick_random

_serial = count()


def _words(n: int, *, category: str = "git", start_pk: int | None = None, reviewed: bool = True) -> list[Word]:
    rows = [
        Word(
            pk=(start_pk + i) if start_pk is not None else None,
            term=f"pick {category} {next(_serial)}",
            meaning="뜻",
            description="설명",
            category=category,
            is_reviewed=reviewed,
        )
        for i in range(n)
    ]
    return Word.objects.bulk_create(rows)


class PickRandomTest(TestCase):
    def test_no_item_is_picked_far_more_than_others_even_with_clustered_ids(self):
        """id 가 몇 덩어리로 몰리고 사이가 크게 비어도 고르게 뽑힌다."""
        _words(10, start_pk=10)
        _words(10, start_pk=500_000)
        _words(10, start_pk=9_000_000)
        pool = Word.objects.visible()

        counts = Counter(w.pk for _ in range(3000) for w in pick_random(pool, 1))

        self.assertEqual(len(counts), 30, "한 번도 안 뽑힌 항목이 있다")
        expected = 3000 / 30
        self.assertLess(max(counts.values()), expected * 2.5, counts.most_common(3))

    def test_respects_filters_and_exclusions(self):
        keep = _words(15, category="database")
        _words(15, category="git")
        _words(5, category="database", reviewed=False)
        excluded = {keep[0].pk, keep[1].pk}
        pool = Word.objects.visible().filter(category="database").exclude(pk__in=excluded)

        for _ in range(50):
            picked = pick_random(pool, 4)
            self.assertEqual(len(picked), 4)
            self.assertEqual(len({w.pk for w in picked}), 4, "같은 것이 두 번 뽑혔다")
            for word in picked:
                self.assertEqual(word.category, "database")
                self.assertTrue(word.is_reviewed)
                self.assertNotIn(word.pk, excluded)

    def test_small_or_empty_pool(self):
        self.assertEqual(pick_random(Word.objects.visible(), 3), [])
        self.assertEqual(pick_random(Word.objects.visible(), 0), [])

        few = _words(2)
        picked = pick_random(Word.objects.visible(), 5)
        self.assertEqual(sorted(w.pk for w in picked), sorted(w.pk for w in few))

    def test_fills_from_the_start_when_the_point_lands_past_every_key(self):
        """찍은 지점 뒤에 행이 없으면 키가 작은 쪽부터 채운다.

        키를 전부 0.5 아래에 두면 지점의 절반은 모든 키 뒤에 떨어진다. 그때도
        모자라지 않게 골라야 하고, 키가 가장 큰 행도 뽑혀야 한다.
        """
        words = _words(12)
        for i, word in enumerate(words):
            Word.objects.filter(pk=word.pk).update(random_key=i / 24)
        largest = words[-1].pk

        seen = set()
        for _ in range(300):
            picked = pick_random(Word.objects.visible(), 2)
            self.assertEqual(len(picked), 2)
            seen |= {w.pk for w in picked}
        self.assertEqual(seen, {w.pk for w in words})
        self.assertIn(largest, seen)

    def test_evenly_spaced_keys_are_picked_evenly(self):
        """키가 고르게 놓이면 모든 행이 같은 확률로 뽑힌다.

        풀(60행)이 창(20행)보다 커서, 끝에 닿은 창은 모자란 만큼만 맨 앞에서
        이어 읽어야 한다. 맨 앞 창을 통째로 붙이면 앞쪽 행이 두 배로, 이어 읽지
        않으면 끝 행이 몇 배로 더 뽑힌다.
        """
        words = _words(60)
        for i, word in enumerate(words):
            Word.objects.filter(pk=word.pk).update(random_key=i / 60)
        pool = Word.objects.visible()

        counts = Counter(w.pk for _ in range(6000) for w in pick_random(pool, 1))

        self.assertEqual(len(counts), 60, "한 번도 안 뽑힌 항목이 있다")
        self.assertLess(max(counts.values()), 100 * 1.5, counts.most_common(3))

    def test_returns_count_when_the_pool_has_enough(self):
        """고를 수가 창 기본값(20)보다 커도 풀에 있으면 그만큼 돌려준다."""
        _words(30)
        for _ in range(100):
            self.assertEqual(len(pick_random(Word.objects.visible(), 25)), 25)

    def test_new_rows_get_their_own_random_key(self):
        """DB 가 행마다 다른 키를 채운다(마이그레이션의 DEFAULT random())."""
        _words(50)
        keys = list(Word.objects.values_list("random_key", flat=True))
        self.assertEqual(len(set(keys)), 50)
        self.assertTrue(all(0 <= k < 1 for k in keys))
