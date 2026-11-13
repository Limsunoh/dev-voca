"""무작위 고르기(sampling.pick_random)로 바꾼 출제 경로를 깨뜨려 본다.

ORDER BY RANDOM() 대신 random_key 칸으로 몇 행만 읽어 고르게 되면서 지켜야
할 것들이다.

  - 검수 안 된 콘텐츠가 문제·보기·지문·일상영어에 나오지 않는다. 검수 안 된
    행을 키 사이사이에 촘촘히 깔아, 창이 그 행들을 읽어도 걸러지는지 본다.
  - 보기 넷이 서로 다르고 정답이 한 번만 들어 있다. 풀이 딱 넷일 때도
    모자라지 않는다.
  - 일상영어는 소리 낼 수 있는 것이 표본에 안 걸려도 대체 길로 찾고,
    그 길도 검수 게이트를 지킨다. 하나도 없으면 404 다.
  - 고른 결과가 키 몇 개에 쏠리지 않는다. 통계 문턱은 같은 알고리즘을 파이썬으로
    흉내내 1천~2천 번 돌린 최악값보다 넉넉히 잡았다(각 테스트 docstring).
  - 새 행마다, 그리고 마이그레이션으로 칸이 생긴 기존 행마다 키가 따로 채워진다.
"""

from __future__ import annotations

import string
from collections import Counter
from itertools import count, product

from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from . import quiz
from .models import DailyPhrase, Sentence, Word
from .sampling import pick_random

_serial = count()

QUIZ_URL = "/api/vocab/words/quiz/"
SENTENCE_QUIZ_URL = "/api/vocab/sentences/quiz/"
TALK_URL = "/api/vocab/talk/question/"


def _letters(n: int) -> list[str]:
    """숫자 없이 서로 다른 소문자 꼬리 n 개. 소리 낼 수 있는 이름을 만들 때 쓴다."""
    return ["".join(p) for p in product(string.ascii_lowercase, repeat=3)][:n]


def make_words(
    n: int, *, category: str = "git", reviewed: bool = True, prefix: str = "w", start_pk: int | None = None
) -> list[Word]:
    rows = [
        Word(
            pk=(start_pk + i) if start_pk is not None else None,
            term=f"{prefix} {next(_serial)}",
            meaning=f"{prefix} 뜻",
            description=f"{prefix} 설명",
            category=category,
            is_reviewed=reviewed,
        )
        for i in range(n)
    ]
    return Word.objects.bulk_create(rows)


def spread_keys(rows, *, offset: float = 0.0, total: int | None = None) -> None:
    """rows 의 키를 0~1 에 고르게 놓는다. offset 으로 다른 무리 사이에 끼운다."""
    total = total or len(rows)
    for i, row in enumerate(rows):
        type(row).objects.filter(pk=row.pk).update(random_key=(i + offset) / total)


class PickRandomEdgeTest(TestCase):
    """pick_random 의 경계."""

    def test_zero_and_negative_count_return_empty(self):
        make_words(5)
        for n in (0, -1, -100):
            with self.subTest(n=n):
                self.assertEqual(pick_random(Word.objects.visible(), n), [])

    def test_empty_querysets_do_not_crash(self):
        """none() 이나 빈 목록 pk__in 처럼 SQL 로 못 만드는 조각도 빈 결과다.

        일일공부 학습분은 words.filter(pk__in=word_ids) 를 넘긴다. 목록이 비면
        UNION 의 조각이 전부 EmptyResultSet 이 된다.
        """
        make_words(5)
        self.assertEqual(pick_random(Word.objects.none(), 3), [])
        self.assertEqual(pick_random(Word.objects.visible().filter(pk__in=[]), 3), [])
        # exclude 쪽 빈 목록은 "아무것도 안 뺀다" 다.
        self.assertEqual(len(pick_random(Word.objects.visible().exclude(pk__in=[]), 3)), 3)

    def test_large_count_over_pool_returns_each_row_once(self):
        """풀보다 많이 달라면 풀 전부를 한 번씩."""
        words = make_words(7)
        for n in (8, 25, 500):
            with self.subTest(n=n):
                picked = pick_random(Word.objects.visible(), n)
                self.assertCountEqual([w.pk for w in picked], [w.pk for w in words])

    def test_count_bigger_than_window_from_a_big_pool(self):
        """고를 수가 창(20)과 지점 수(4)를 넘어도 겹치지 않게 그만큼 준다."""
        make_words(200)
        for n in (21, 50, 81, 199, 200):
            with self.subTest(n=n):
                picked = pick_random(Word.objects.visible(), n)
                self.assertEqual(len(picked), n)
                self.assertEqual(len({w.pk for w in picked}), n)

    def test_all_keys_at_the_edges(self):
        """키가 0 이나 1 에 바짝 붙어 있어도 풀이 창(20)보다 작으면 빠짐없이 고른다.

        풀이 창보다 크면 이렇게 몰린 키에서는 몇 행이 거의 안 뽑힌다. 키가 행마다
        random() 이면 이렇게 몰리지 않고, 몰리는 것은 키를 손으로 복사했을 때뿐이다
        (DEPLOY.md). 같은 키를 여럿 두는 것도 그 경우라 여기서 다루지 않는다.
        """
        words = make_words(18)
        for i, w in enumerate(words):
            key = i * 1e-12 if i % 2 else 1 - (i + 1) * 1e-12
            Word.objects.filter(pk=w.pk).update(random_key=key)
        seen = set()
        for _ in range(200):
            picked = pick_random(Word.objects.visible(), 3)
            self.assertEqual(len({w.pk for w in picked}), 3)
            seen |= {w.pk for w in picked}
        self.assertEqual(seen, {w.pk for w in words})

    def test_unreviewed_rows_packed_between_keys_never_leak(self):
        """검수 안 된 행이 키 사이를 촘촘히 채워도 나오지 않는다.

        창은 키 순서로 20행을 읽는다. 검수 게이트가 queryset 조건이 아니라
        읽은 뒤 거르기였다면 여기서 창이 미검수로 다 차 버린다.
        """
        visible = make_words(6)
        hidden = make_words(300, reviewed=False, prefix="hidden")
        spread_keys(visible, offset=0.5, total=6)
        spread_keys(hidden)
        hidden_ids = {w.pk for w in hidden}

        for n in (1, 3, 6, 15):
            for _ in range(60):
                picked = pick_random(Word.objects.visible(), n)
                ids = {w.pk for w in picked}
                self.assertFalse(ids & hidden_ids, "미검수 단어가 뽑혔다")
                self.assertEqual(len(ids), min(n, 6))


class QuizGateTest(TestCase):
    """출제 함수가 검수 안 된 것을 쓰지 않는다. 결과가 매번 달라 여러 번 돌린다."""

    def test_word_question_never_uses_unreviewed_and_choices_are_distinct(self):
        """정답·보기 모두 검수된 단어, 보기 넷이 서로 다르고 정답이 하나.

        같은 분류에 검수된 것은 둘뿐이고 미검수가 수백이다. 보기는 같은
        분류에서 먼저 채우고 모자란 몫을 전체에서 채운다.
        """
        same = make_words(2, category="git")
        other = make_words(5, category="database")
        hidden = make_words(200, category="git", reviewed=False, prefix="hidden")
        hidden += make_words(100, category="database", reviewed=False, prefix="hidden")
        hidden_ids = {w.pk for w in hidden}
        visible_ids = {w.pk for w in same + other}

        for _ in range(150):
            q = quiz.make_question(Word.objects.visible())
            self.assertIsNotNone(q)
            ids = [c.id for c in q.choices]
            self.assertEqual(len(ids), quiz.CHOICE_COUNT)
            self.assertEqual(len(set(ids)), quiz.CHOICE_COUNT, f"보기가 겹쳤다: {ids}")
            self.assertEqual(ids.count(q.answer_id), 1)
            self.assertFalse(set(ids) & hidden_ids, "미검수 단어가 보기에 나왔다")
            self.assertLessEqual(set(ids), visible_ids)

    def test_pool_of_exactly_four_always_makes_the_same_four(self):
        """풀이 딱 넷이면 늘 그 넷이 보기다. 하나라도 덜 읽으면 None 이 된다."""
        four = make_words(4)
        make_words(80, reviewed=False, prefix="hidden")
        for _ in range(100):
            q = quiz.make_question(Word.objects.visible())
            self.assertIsNotNone(q, "보기를 채울 수 있는데 못 만들었다")
            self.assertCountEqual([c.id for c in q.choices], [w.pk for w in four])

    def test_three_reviewed_words_cannot_make_a_question(self):
        """검수된 것이 셋뿐이면 미검수로 채우지 않고 None."""
        make_words(3)
        make_words(50, reviewed=False, prefix="hidden")
        for _ in range(30):
            self.assertIsNone(quiz.make_question(Word.objects.visible()))

    def test_exclude_leaves_one_candidate_which_is_always_the_answer(self):
        """정답 후보 제외(exclude_ids)를 지킨다. 남은 하나가 늘 정답이다."""
        words = make_words(10)
        keep = words[3]
        exclude = [w.pk for w in words if w.pk != keep.pk]
        for _ in range(50):
            q = quiz.make_question(Word.objects.visible(), exclude_ids=exclude)
            self.assertEqual(q.answer_id, keep.pk)
            self.assertEqual(len({c.id for c in q.choices}), 4)

    def test_exclude_everything_gives_none(self):
        words = make_words(10)
        self.assertIsNone(
            quiz.make_question(Word.objects.visible(), exclude_ids=[w.pk for w in words])
        )

    def test_description_kind_only_answers_words_with_description(self):
        """설명 문제는 설명 있는 단어만 정답이 된다(빈 설명을 빼는 조건)."""
        words = make_words(30)
        Word.objects.filter(pk__in=[w.pk for w in words[1:]]).update(description="")
        for _ in range(40):
            q = quiz.make_question(Word.objects.visible(), kind=quiz.QuizKind.DESCRIPTION)
            self.assertEqual(q.answer_id, words[0].pk)

    def test_narrowed_answer_pool_with_unreviewed_ids_only_answers_reviewed(self):
        """일일공부 학습분처럼 id 로 좁힌 풀에 미검수 id 가 섞여도 정답은 검수된 것."""
        visible = make_words(10)
        hidden = make_words(10, reviewed=False, prefix="hidden")
        ids = [visible[0].pk, *(w.pk for w in hidden)]
        words = Word.objects.visible()
        for _ in range(40):
            q = quiz.make_question(words.filter(pk__in=ids), choices_from=words)
            self.assertEqual(q.answer_id, visible[0].pk)

    def test_distractors_fill_from_other_categories_without_duplicates(self):
        """같은 분류에 하나뿐이면 둘은 다른 분류에서 채운다. 겹침·정답 섞임 없음."""
        answer, sibling = make_words(2, category="git")
        others = make_words(40, category="cs")
        make_words(100, category="git", reviewed=False, prefix="hidden")
        for _ in range(100):
            picked = quiz._pick_distractors(answer, Word.objects.visible(), 3)
            ids = [w.pk for w in picked]
            self.assertEqual(len(ids), 3)
            self.assertEqual(len(set(ids)), 3)
            self.assertNotIn(answer.pk, ids)
            self.assertIn(sibling.pk, ids, "같은 분류 것을 먼저 쓰지 않았다")
            self.assertTrue(all(w.is_reviewed for w in picked))
        self.assertTrue(others)


class SentenceQuizGateTest(TestCase):
    """빈칸·상황 문제의 검수 게이트와 보기."""

    def setUp(self):
        for term in ("cache", "commit", "branch", "merge"):
            Word.objects.create(term=term, meaning=f"{term} 뜻", category="git", is_reviewed=True)
        # 정답보다 긴 미검수 용어. 새면 "가장 긴 것" 규칙 때문에 그쪽이 정답이 된다.
        Word.objects.create(
            term="stale entry", meaning="숨김", category="git", is_reviewed=False
        )
        self.hidden_words = set(Word.objects.filter(is_reviewed=False).values_list("pk", flat=True))

    def test_blank_question_uses_only_reviewed_sentence_and_words(self):
        source = Sentence.objects.create(
            text="the cache has a stale entry", translation="번역", is_reviewed=True
        )
        hidden_sentences = Sentence.objects.bulk_create(
            Sentence(text=f"hidden cache line {i}", translation="번역", is_reviewed=False)
            for i in range(60)
        )
        hidden_ids = {s.pk for s in hidden_sentences}

        for _ in range(60):
            q = quiz.make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            self.assertIsNotNone(q)
            self.assertEqual(q.source_sentence_id, source.pk)
            self.assertNotIn(q.source_sentence_id, hidden_ids)
            ids = [c.id for c in q.choices]
            self.assertEqual(len(set(ids)), 4)
            self.assertFalse(set(ids) & self.hidden_words, "미검수 단어가 보기에 나왔다")
            self.assertEqual(q.prompt, "the ____ has a stale entry")

    def test_situation_question_never_uses_unreviewed_contexts(self):
        visible = Sentence.objects.bulk_create(
            Sentence(
                text=f"visible line {i}",
                translation="번역",
                context=f"보이는 상황 {i} 때",
                is_reviewed=True,
            )
            for i in range(6)
        )
        Sentence.objects.bulk_create(
            Sentence(
                text=f"hidden line {i}",
                translation="번역",
                context=f"숨은 상황 {i} 때",
                is_reviewed=False,
            )
            for i in range(200)
        )
        visible_ids = {s.pk for s in visible}

        for _ in range(80):
            q = quiz.make_situation_question(Sentence.objects.visible())
            self.assertIsNotNone(q)
            ids = [c.id for c in q.choices]
            labels = [c.text for c in q.choices]
            self.assertLessEqual(set(ids), visible_ids, "미검수 문장이 보기에 나왔다")
            self.assertEqual(len(set(ids)), 4)
            self.assertEqual(len(set(labels)), 4, f"상황 글자가 겹쳤다: {labels}")
            self.assertFalse(any("숨은" in t for t in labels))

    def test_situation_with_place_answer_keeps_same_kind(self):
        """자리형 정답이면 보기도 자리형. _place_filter 의 annotate 가 UNION 을 지나도 맞는다."""
        place = Sentence.objects.bulk_create(
            Sentence(text=f"place {i}", translation="번역", context=f"운영 로그 {i}", is_reviewed=True)
            for i in range(5)
        )
        Sentence.objects.bulk_create(
            Sentence(text=f"scene {i}", translation="번역", context=f"회의 {i} 때", is_reviewed=True)
            for i in range(30)
        )
        Sentence.objects.bulk_create(
            Sentence(text=f"hidden place {i}", translation="번역", context=f"숨은 로그 {i}", is_reviewed=False)
            for i in range(50)
        )
        place_ids = {s.pk for s in place}
        for _ in range(40):
            q = quiz.make_situation_question(Sentence.objects.visible(), answer=place[0])
            ids = {c.id for c in q.choices}
            self.assertEqual(q.question, "이 말은 어디서 보이나?")
            self.assertLessEqual(ids, place_ids)


class QuizEndpointGateTest(TestCase):
    """엔드포인트로 불러도 미검수가 안 나오고, 이상한 exclude 로 500 이 안 난다."""

    def setUp(self):
        cache.clear()
        self.visible = make_words(5, category="git")
        self.hidden = {w.pk for w in make_words(150, category="git", reviewed=False, prefix="hidden")}

    def test_word_quiz_endpoint_never_shows_unreviewed(self):
        for _ in range(60):
            res = self.client.get(QUIZ_URL, {"category": "git"})
            self.assertEqual(res.status_code, 200, res.content)
            ids = {c["id"] for c in res.json()["choices"]}
            self.assertFalse(ids & self.hidden)
            self.assertNotIn("hidden", res.content.decode())

    def test_odd_exclude_values_are_not_500(self):
        for raw in ("9" * 30, "-1,-2", "abc,,", "0", ",".join(str(w.pk) for w in self.visible)):
            with self.subTest(raw=raw[:20]):
                res = self.client.get(QUIZ_URL, {"exclude": raw})
                self.assertIn(res.status_code, (200, 404), res.content)


class TalkSamplingTest(TestCase):
    """일상영어 문제: 표본(10개)과 대체 길, 그리고 검수 게이트."""

    def setUp(self):
        cache.clear()
        Word.objects.all().delete()
        DailyPhrase.objects.all().delete()

    def _word(self, term: str, reviewed: bool = True, level: int = 1) -> Word:
        return Word.objects.create(
            term=term,
            meaning=f"{term} 뜻",
            pronunciation="/x/",
            reading="엑s",
            reading_reviewed=True,
            is_reviewed=reviewed,
            difficulty=level,
        )

    def _phrase(self, text: str, reviewed: bool = True, scene: str = "", level: int = 1) -> DailyPhrase:
        return DailyPhrase.objects.create(
            text=text,
            meaning=f"{text} 뜻",
            pronunciation="/x/",
            reading="엑s",
            is_reviewed=reviewed,
            scene=scene,
            difficulty=level,
        )

    def _ask(self, **params):
        return self.client.get(TALK_URL, params)

    def test_lone_speakable_word_is_found_past_the_sample(self):
        """소리 낼 수 있는 것이 80개 중 하나뿐이어도 매번 그것을 낸다(대체 길)."""
        for i in range(80):
            self._word(f"x{i}")  # 숫자가 들어 있어 소리로 채점 못 한다
        target = self._word("cache")
        for _ in range(30):
            res = self._ask(kind="dev")
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual(res.json()["id"], target.pk)

    def test_fallback_does_not_leak_unreviewed_speakable(self):
        """검수된 것은 전부 못 읽는 것, 읽을 수 있는 것은 전부 미검수면 404.

        대체 길은 풀을 다시 훑는다. 그 풀이 visible() 이 아니면 여기서 샌다.
        """
        for i in range(40):
            self._word(f"x{i}")
        for tail in _letters(40):
            self._word(f"hidden{tail}", reviewed=False)
        for _ in range(10):
            res = self._ask(kind="dev")
            self.assertEqual(res.status_code, 404, res.content)
            self.assertNotIn("hidden", res.content.decode())

    def test_unreviewed_speakable_never_shown_when_one_reviewed_exists(self):
        target = self._word("cache")
        for tail in _letters(60):
            self._word(f"hidden{tail}", reviewed=False)
        for i in range(30):
            self._word(f"x{i}")
        for _ in range(30):
            res = self._ask(kind="dev")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["id"], target.pk)

    def test_nothing_speakable_is_404(self):
        for i in range(15):
            self._word(f"x{i}")
        res = self._ask(kind="dev")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "읽을 것을 다 봤습니다. 잠시 뒤 다시 시작해보세요.")

    def test_empty_pool_is_404(self):
        res = self._ask(kind="dev")
        self.assertEqual(res.status_code, 404)

    def test_exclude_walks_every_speakable_phrase_once_then_404(self):
        """exclude 를 쌓으며 걸으면 읽을 수 있는 것이 정확히 한 번씩 나오고 404 로 끝난다.

        표본 고르기가 같은 것을 다시 고르거나 어떤 것을 영영 못 고르면 여기서 드러난다.
        """
        speakable = {self._phrase(f"good {t}").pk for t in _letters(25)}
        for i in range(25):
            self._phrase(f"number {i}")
        for t in _letters(20):
            self._phrase(f"hidden {t}", reviewed=False)

        seen: list[int] = []
        for _ in range(40):
            res = self._ask(exclude=",".join(map(str, seen)))
            if res.status_code == 404:
                break
            self.assertEqual(res.status_code, 200, res.content)
            seen.append(res.json()["id"])
        self.assertEqual(len(seen), len(set(seen)), "같은 것이 두 번 나왔다")
        self.assertEqual(set(seen), speakable)

    def test_scene_and_level_filters_hold_under_sampling(self):
        target = self._phrase("see you at lunch", scene="greeting", level=2)
        for t in _letters(40):
            self._phrase(f"other {t}", scene="shopping", level=2)
            self._phrase(f"level {t}", scene="greeting", level=1)
        self._phrase("hidden work line", reviewed=False, scene="greeting", level=2)
        for _ in range(20):
            res = self._ask(scene="greeting", level=2)
            self.assertEqual(res.status_code, 200, res.content)
            self.assertEqual(res.json()["id"], target.pk)

    def test_odd_exclude_is_not_500(self):
        self._word("cache")
        for raw in ("9" * 30, "-5", "a,b,,"):
            with self.subTest(raw=raw):
                res = self._ask(kind="dev", exclude=raw)
                self.assertEqual(res.status_code, 200, res.content)


class FairnessTest(TestCase):
    """쏠림. 문턱은 같은 알고리즘의 파이썬 흉내로 잡았다.

    pick_random 을 그대로 옮긴 시뮬레이터로 각 시나리오를 1천~2천 번 돌린 최악값과
    문턱을 docstring 에 적었다. 문턱은 그 최악값보다 한참 밖이라 1만 번 돌려도
    거짓으로 빨개지지 않는다.
    """

    def test_distractors_with_evenly_spaced_keys_are_uniform(self):
        """키가 고르면 보기(3개 고르기)가 어느 행에도 쏠리지 않는다.

        정답 하나 + 같은 분류 120개, 4천 번. 키가 고르면 원형으로 대칭이라 행마다
        확률이 같다. 시뮬레이터 1천 번 최악값: 행 하나 0.57~1.44배, 앞 20행·뒤
        20행 묶음 0.93~1.08배. 문턱은 행 0.4~1.7배, 묶음 0.8~1.2배.

        이어 읽기를 빼면 앞 묶음이 0.5배, 맨 앞 창을 통째로 붙이면 2배가 되어
        묶음 문턱에 걸린다(시뮬레이터 값).
        """
        answer = make_words(1, category="git")[0]
        rows = make_words(120, category="git")
        Word.objects.filter(pk=answer.pk).update(random_key=0.5 / 120)
        spread_keys(rows)
        pool = Word.objects.visible()

        trials = 4000
        counts = Counter()
        for _ in range(trials):
            counts.update(w.pk for w in quiz._pick_distractors(answer, pool, 3))

        expected = trials * 3 / 120
        vals = [counts.get(w.pk, 0) for w in rows]
        self.assertNotIn(answer.pk, counts)
        self.assertGreater(min(vals), expected * 0.4, counts.most_common()[-3:])
        self.assertLess(max(vals), expected * 1.7, counts.most_common(3))
        front = sum(vals[:20]) / (expected * 20)
        back = sum(vals[-20:]) / (expected * 20)
        self.assertTrue(0.8 < front < 1.2, f"앞 20행 {front:.2f}배")
        self.assertTrue(0.8 < back < 1.2, f"뒤 20행 {back:.2f}배")

    def test_answers_with_db_filled_keys_and_clustered_ids_are_not_skewed(self):
        """DB 가 채운 키 그대로, id 가 셋으로 몰려도 정답이 쏠리지 않는다.

        60개, 3천 문제(행마다 기대 50). 키가 매번 새로 정해지므로 키 간격 차이가
        섞인다. 시뮬레이터 2천 번 최악값: 가장 많이 나온 행 2.08배, 가장 적게
        나온 행 0.24배. 문턱은 3배 미만, 한 번 이상.
        """
        make_words(20, category="git", start_pk=10)
        make_words(20, category="git", start_pk=700_000)
        make_words(20, category="git", start_pk=9_000_000)
        pool = Word.objects.visible()

        trials = 3000
        counts = Counter(quiz.make_question(pool, kind=quiz.QuizKind.MEANING).answer_id for _ in range(trials))
        expected = trials / 60
        self.assertEqual(len(counts), 60, "한 번도 정답이 안 된 단어가 있다")
        self.assertLess(max(counts.values()), expected * 3, counts.most_common(3))


class RandomKeyFillTest(TestCase):
    """새 행마다 키가 따로 채워진다."""

    def test_each_model_and_insert_path_gets_its_own_key(self):
        make_words(40)
        Word.objects.bulk_create(
            [Word(term=f"ignore {i}", meaning="뜻") for i in range(40)], ignore_conflicts=True
        )
        Word.objects.create(term="single", meaning="뜻")
        Sentence.objects.bulk_create(Sentence(text=f"s {i}", translation="번역") for i in range(40))
        DailyPhrase.objects.bulk_create(
            DailyPhrase(text=f"p {i}", meaning="뜻", pronunciation="/x/", reading="엑s")
            for i in range(40)
        )
        for model in (Word, Sentence, DailyPhrase):
            with self.subTest(model=model.__name__):
                keys = list(model.objects.values_list("random_key", flat=True))
                self.assertEqual(len(set(keys)), len(keys), "같은 키가 둘 이상이다")
                self.assertTrue(all(0 <= k < 1 for k in keys))

    def test_saving_an_existing_row_keeps_its_key(self):
        """Admin 이 고쳐 저장해도 키가 바뀌지 않는다(바뀌어도 해는 없지만 칸이 비면 안 된다)."""
        word = Word.objects.create(term="keep", meaning="뜻")
        key = Word.objects.get(pk=word.pk).random_key
        loaded = Word.objects.get(pk=word.pk)
        loaded.meaning = "고친 뜻"
        loaded.save()
        self.assertEqual(Word.objects.get(pk=word.pk).random_key, key)
        # create() 가 돌려준 객체를 다시 save 해도 터지지 않고 키가 남는다.
        word.meaning = "또 고침"
        word.save()
        self.assertTrue(0 <= Word.objects.get(pk=word.pk).random_key < 1)

    def test_key_is_not_in_api_output(self):
        make_words(5)
        res = self.client.get("/api/vocab/words/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("random_key", res.content.decode())


class RandomKeyMigrationTest(TransactionTestCase):
    """0015 를 기존 행이 있는 표에 걸면 행마다 다른 키가 들어간다.

    Postgres 는 volatile 기본값(random())으로 열을 더할 때 행마다 새로 부른다.
    상수 기본값처럼 한 번만 불러 모두 같은 값이 되면 무작위 고르기가 창 하나에 갇힌다.
    """

    before = [("vocab", "0014_search_trgm")]
    after = [("vocab", "0015_random_key")]

    def test_existing_rows_get_distinct_keys(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            OldWord = old_apps.get_model("vocab", "Word")
            OldWord.objects.bulk_create(
                OldWord(term=f"old {i}", meaning="뜻", is_reviewed=True) for i in range(50)
            )
        finally:
            executor = MigrationExecutor(connection)
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())

        keys = list(Word.objects.filter(term__startswith="old ").values_list("random_key", flat=True))
        self.assertEqual(len(keys), 50)
        self.assertEqual(len(set(keys)), 50, "기존 행이 같은 키를 받았다")
        self.assertTrue(all(0 <= k < 1 for k in keys))
