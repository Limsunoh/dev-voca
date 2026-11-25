"""후보 번호를 기억해 두고 고르기(sampling.pick_pooled)를 깨뜨려 보는 테스트.

pick_pooled 는 조건(queryset 의 SQL 과 인자)마다 번호 전체를 CACHES["pools"] 에 5분 동안
기억해 두고, 파이썬에서 고른 뒤 고른 행만 받은 queryset 으로 다시 읽는다. 지킬 것은 이렇다.

    검수 게이트  기억한 뒤 검수가 취소되거나 지워진 행은 정답·보기·빈칸 지문·상황 보기·말하기
                 문제로 나오지 않는다. 다시 읽을 때 queryset 조건을 걸기 때문이다. 그렇게
                 빠져 덜 모이면 기억을 버리고 한 번 다시 고른다.
    exclude      넘긴 번호는 고르지 않는다. 출제에서는 정답에만 쓰고 보기에는 안 쓴다.
    늦음         새로 검수된 것은 기억이 살아 있는 동안 안 나오고, 비우면 나온다(의도).
    하한         번호가 POOL_MIN 보다 적은 조건(빈 조건 포함)은 기억하지 않고 매번 새로 읽는다.
    상한         번호가 POOL_MAX 를 넘으면 pick_random 으로 돌아가고, exclude 는 그대로 지킨다.
    고름         exclude 를 뺀 남은 후보 전체에서 고르게 뽑는다.
    쿼리 수      기억이 살아 있으면 덜 묻는다.
    섞이지 않음  조건이 다르면 기억도 따로다.

그래서 기억 경로를 보는 테스트는 후보를 POOL_MIN 개 이상으로 만든다(BIG). 테스트 설정에서
CACHES["pools"] 는 DummyCache 라 여기서는 LocMemCache 로 바꿔 두고 테스트마다 비운다.
무작위로 갈리는 곳은 random.seed 로 고정한다.
"""

from __future__ import annotations

import random
from collections import Counter
from unittest import mock

from django.conf import settings
from django.core.cache import caches
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.learning import session

from . import quiz, sampling
from .models import DailyPhrase, Sentence, Word
from .quiz import QuizKind, make_blank_question, make_question, make_situation_question
from .sampling import pick_pooled

WORD_QUIZ = "/api/vocab/words/quiz/"
TALK_QUESTION = "/api/vocab/talk/question/"

# 기억되는 가장 작은 풀보다 조금 크게. 기억 경로를 보는 테스트가 쓴다.
BIG = sampling.POOL_MIN + 3

REMEMBERING = override_settings(
    CACHES={
        **settings.CACHES,
        "pools": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pick-pooled-dynamic",
            "TIMEOUT": 300,
            "OPTIONS": {"MAX_ENTRIES": 1000},
        },
    }
)


def _letters(i: int) -> str:
    """0 -> "aa", 1 -> "ab" ... 글자만으로 된 이름. 빈칸 문제가 숫자 든 낱말을 안 볼 수 있어서다."""
    return chr(97 + i // 26) + chr(97 + i % 26)


def _words(n: int, prefix: str = "term", category: str = "git") -> list[Word]:
    return [
        Word.objects.create(
            term=f"{prefix}{_letters(i)}",
            meaning=f"{prefix} 뜻 {i}",
            description=f"{prefix}{_letters(i)} 를 설명하는 글",
            category=category,
            is_reviewed=True,
        )
        for i in range(n)
    ]


def _sentence(text: str, context: str = "", reviewed: bool = True) -> Sentence:
    return Sentence.objects.create(
        text=text, translation="해석", context=context, category="git", is_reviewed=reviewed
    )


def _phrase(text: str, reviewed: bool = True) -> DailyPhrase:
    return DailyPhrase.objects.create(
        text=text,
        meaning=f"{text} 뜻",
        pronunciation="/x/",
        reading="엑스",
        is_reviewed=reviewed,
        difficulty=1,
    )


def _hide(rows) -> set[int]:
    """검수를 취소한다. 취소한 번호."""
    ids = {row.pk for row in rows}
    type(rows[0]).objects.filter(pk__in=ids).update(is_reviewed=False)
    return ids


def _drop(rows) -> set[int]:
    """지운다. 지운 번호."""
    ids = {row.pk for row in rows}
    type(rows[0]).objects.filter(pk__in=ids).delete()
    return ids


def _ids(question) -> set[int]:
    """문제에 나온 번호 전부(정답과 보기)."""
    return {question.answer_id, *(choice.id for choice in question.choices)}


def _key(queryset) -> str:
    """sampling 이 쓰는 캐시 키. 공식을 여기 따로 적으면 sampling 쪽만 바뀌었을 때
    "기억하지 않는다" 를 보는 테스트가 아무 키도 못 찾아 늘 통과한다."""
    return sampling._pool_key(queryset)


_real_pick_once = sampling._pick_once


def _leaky_pick_once(queryset, key, count, exclude):
    """방어를 뺀 _pick_once. 고른 행을 queryset 조건 없이 다시 읽는다.

    테스트가 검수 게이트를 정말 무는지 보려고만 쓴다. 이걸로 바꿔 끼우면 기억해 둔 낡은
    번호가 그대로 나와야 한다.
    """
    pks = sampling._pool(queryset, key)
    if pks is None:
        return sampling.pick_random(queryset, count), False
    skip = set(exclude)
    candidates = [pk for pk in pks if pk not in skip]
    chosen = random.sample(candidates, min(count, len(candidates)))
    rows = {row.pk: row for row in queryset.model._base_manager.filter(pk__in=chosen)}
    return [rows[pk] for pk in chosen if pk in rows], False


def _no_retry_pick_once(queryset, key, count, exclude):
    """다시 고르기를 뺀 _pick_once. 덜 모여도 기억을 버리지 않는다."""
    rows, _short = _real_pick_once(queryset, key, count, exclude)
    return rows, False


@REMEMBERING
class PooledHarness(TestCase):
    def setUp(self) -> None:
        caches["pools"].clear()
        # 말하기 문제의 요청 수 제한이 default 캐시에 쌓인다.
        caches["default"].clear()


class GateAfterRememberingTests(PooledHarness):
    """기억한 뒤 검수가 취소되거나 지워진 것이 출제로 새지 않는다."""

    def _word_leaks(self, runs: int = 200) -> tuple[set[int], int]:
        """단어 BIG 개를 기억시킨 뒤 넷만 남기고 반은 검수 취소, 반은 지운다. (샌 번호, 못 만든 횟수)."""
        words = _words(BIG)
        random.seed(7)
        # 정답 풀(검수된 전부)과 보기 풀(같은 분류)을 둘 다 기억시킨다.
        self.assertIsNotNone(make_question(Word.objects.visible(), QuizKind.MEANING))
        self.assertIsNotNone(caches["pools"].get(_key(Word.objects.visible())))
        self.assertIsNotNone(caches["pools"].get(_key(Word.objects.visible().filter(category="git"))))
        rest = words[4:]
        hidden = _hide(rest[: len(rest) // 2])
        gone = _drop(rest[len(rest) // 2 :])

        leaked: set[int] = set()
        failed = 0
        for _ in range(runs):
            question = make_question(Word.objects.visible(), QuizKind.MEANING)
            if question is None:
                failed += 1
                continue
            leaked |= _ids(question) & (hidden | gone)
        return leaked, failed

    def test_검수취소_지운_단어는_정답에도_보기에도_안_나오고_문제는_늘_만들어진다(self) -> None:
        """남은 단어가 딱 넷이라, 낡은 번호를 골랐을 때 다시 고르지 않으면 문제를 못 만든다."""
        leaked, failed = self._word_leaks()
        self.assertEqual(leaked, set())
        self.assertEqual(failed, 0)

    def test_다시_읽기에_검수조건이_없으면_위_테스트가_샌다(self) -> None:
        """방어를 빼면 위 테스트가 실패하는지. 기억 경로를 정말 탔다는 증거이기도 하다."""
        with mock.patch.object(sampling, "_pick_once", _leaky_pick_once):
            leaked, _failed = self._word_leaks()
        self.assertNotEqual(leaked, set())

    def test_다시_고르기가_없으면_위_테스트에서_문제를_못_만든다(self) -> None:
        """기억을 버리고 다시 고르는 길이 빠지면 낡은 번호에 걸린 만큼 문제가 안 나온다."""
        with mock.patch.object(sampling, "_pick_once", _no_retry_pick_once):
            _leaked, failed = self._word_leaks()
        self.assertGreater(failed, 0)

    def test_낡은_번호에_걸리면_기억을_버리고_남은_것만_준다(self) -> None:
        """BIG 개를 기억한 뒤 하나만 남기고 다 검수 취소하고 전부 달라고 하면 남은 하나만 나온다.

        다시 센 번호는 하나라 POOL_MIN 보다 적어 기억하지 않는다. 낡은 기억도 지워져 있어야 한다.
        """
        words = _words(BIG)
        self.assertEqual(len(pick_pooled(Word.objects.visible(), BIG)), BIG)
        _hide(words[1:])

        picked = pick_pooled(Word.objects.visible(), BIG)

        self.assertEqual([w.pk for w in picked], [words[0].pk])
        self.assertIsNone(caches["pools"].get(_key(Word.objects.visible())))

    def test_낡은_번호에_걸려도_남은_것이_많으면_새로_기억한다(self) -> None:
        words = _words(BIG + 2)
        pick_pooled(Word.objects.visible(), 1)
        _hide(words[:2])
        pick_pooled(Word.objects.visible(), BIG + 2)
        self.assertEqual(
            set(caches["pools"].get(_key(Word.objects.visible()))), {w.pk for w in words[2:]}
        )

    def _blank_leaks(self) -> tuple[set[int], set[int], int]:
        """빈칸 문제. 문장과 단어를 BIG 개씩 기억시킨 뒤 일부를 숨긴다. (샌 문장, 샌 단어, 만든 횟수)."""
        words = _words(BIG, prefix="blank")
        sentences = [_sentence(f"Please {w.term} the change today.") for w in words]
        random.seed(11)
        for _ in range(5):
            make_blank_question(Sentence.objects.visible(), Word.objects.visible())
        self.assertIsNotNone(caches["pools"].get(_key(Sentence.objects.visible())))
        # 앞 절반의 문장을 숨긴다. 뒤쪽 단어 몇 개도 숨긴다 - 그 단어의 문장은 남아 있어
        # 빈칸을 못 뚫어야 하고, 보기로도 나오면 안 된다.
        hidden_sentences = _hide(sentences[: BIG // 2])
        hidden_words = _hide(words[BIG // 2 : BIG // 2 + 6])

        leaked_s: set[int] = set()
        leaked_w: set[int] = set()
        made = 0
        for _ in range(150):
            question = make_blank_question(Sentence.objects.visible(), Word.objects.visible())
            if question is None:
                continue
            made += 1
            if question.source_sentence_id in hidden_sentences:
                leaked_s.add(question.source_sentence_id)
            leaked_w |= _ids(question) & hidden_words
        return leaked_s, leaked_w, made

    def test_빈칸_문제에_검수취소한_문장도_단어도_안_나온다(self) -> None:
        leaked_s, leaked_w, made = self._blank_leaks()
        self.assertEqual(leaked_s, set())
        self.assertEqual(leaked_w, set())
        self.assertGreater(made, 0)

    def test_빈칸_다시_읽기에_검수조건이_없으면_샌다(self) -> None:
        with mock.patch.object(sampling, "_pick_once", _leaky_pick_once):
            leaked_s, leaked_w, _made = self._blank_leaks()
        self.assertTrue(leaked_s or leaked_w)

    def _situation_leaks(self) -> tuple[set[int], int]:
        """상황이 모두 다른 장면 문장 BIG 개를 기억시킨 뒤 넷만 남긴다. (샌 번호, 못 만든 횟수)."""
        rows = [
            _sentence(f"Situation line {_letters(i)}.", context=f"작업 {_letters(i)} 를 할 때")
            for i in range(BIG)
        ]
        random.seed(13)
        self.assertIsNotNone(make_situation_question(Sentence.objects.visible()))
        rest = rows[4:]
        hidden = _hide(rest[: len(rest) // 2])
        gone = _drop(rest[len(rest) // 2 :])

        leaked: set[int] = set()
        failed = 0
        for _ in range(200):
            question = make_situation_question(Sentence.objects.visible())
            if question is None:
                failed += 1
                continue
            leaked |= _ids(question) & (hidden | gone)
        return leaked, failed

    def test_상황_문제에_검수취소_지운_문장이_정답으로도_보기로도_안_나온다(self) -> None:
        leaked, failed = self._situation_leaks()
        self.assertEqual(leaked, set())
        self.assertEqual(failed, 0)

    def test_상황_다시_읽기에_검수조건이_없으면_샌다(self) -> None:
        with mock.patch.object(sampling, "_pick_once", _leaky_pick_once):
            leaked, _failed = self._situation_leaks()
        self.assertNotEqual(leaked, set())

    def _talk_leaks(self) -> set[int]:
        """일상 표현 BIG 개를 기억시킨 뒤 셋만 남긴다. 나온 것 중 숨긴 번호."""
        phrases = [_phrase(f"see you at the {_letters(i)} place") for i in range(BIG)]
        client = APIClient()
        random.seed(17)
        self.assertEqual(client.get(TALK_QUESTION).status_code, 200)
        rest = phrases[3:]
        hidden = _hide(rest[: len(rest) // 2])
        gone = _drop(rest[len(rest) // 2 :])

        seen: set[int] = set()
        for _ in range(40):
            response = client.get(TALK_QUESTION)
            self.assertEqual(response.status_code, 200)
            seen.add(response.json()["id"])
        return seen & (hidden | gone)

    def test_말하기_문제에_검수취소_지운_표현이_안_나온다(self) -> None:
        self.assertEqual(self._talk_leaks(), set())

    def test_말하기_다시_읽기에_검수조건이_없으면_샌다(self) -> None:
        with mock.patch.object(sampling, "_pick_once", _leaky_pick_once):
            self.assertNotEqual(self._talk_leaks(), set())


class ExcludeAndEdgeTests(PooledHarness):
    """exclude, 모자란 후보, 빈 풀, count 0."""

    def test_정답은_exclude_를_피하고_보기는_피하지_않는다(self) -> None:
        """BIG 개 중 하나만 남기고 다 빼도 정답은 그 하나이고, 보기는 뺀 것에서 채운다."""
        words = _words(BIG)
        excluded = [w.pk for w in words[1:]]
        random.seed(3)
        for _ in range(50):
            question = make_question(Word.objects.visible(), QuizKind.MEANING, exclude_ids=excluded)
            self.assertIsNotNone(question)
            self.assertEqual(question.answer_id, words[0].pk)
            self.assertEqual(len(question.choices), quiz.CHOICE_COUNT)
            self.assertTrue({c.id for c in question.choices} - {words[0].pk} <= set(excluded))

    def test_API_에서도_exclude_가_정답에만_걸린다(self) -> None:
        words = _words(BIG)
        client = APIClient()
        excluded = ",".join(str(w.pk) for w in words[1:])
        for _ in range(10):
            response = client.get(WORD_QUIZ, {"kind": "meaning", "exclude": excluded})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["prompt"], words[0].term)

    def test_말하기_문제의_exclude_는_기억이_있어도_지키고_다_빼면_404(self) -> None:
        phrases = [_phrase(f"good {_letters(i)} morning") for i in range(BIG)]
        client = APIClient()
        self.assertEqual(client.get(TALK_QUESTION).status_code, 200)
        but_last = ",".join(str(p.pk) for p in phrases[:-1])
        for _ in range(10):
            response = client.get(TALK_QUESTION, {"exclude": but_last})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["id"], phrases[-1].pk)
        everything = ",".join(str(p.pk) for p in phrases)
        self.assertEqual(client.get(TALK_QUESTION, {"exclude": everything}).status_code, 404)

    def test_빈칸_문제의_exclude_문장은_지문으로_안_나온다(self) -> None:
        words = _words(BIG, prefix="blank")
        sentences = [_sentence(f"Please {w.term} the change today.") for w in words]
        excluded = [s.pk for s in sentences[1:]]
        random.seed(5)
        for _ in range(30):
            question = make_blank_question(
                Sentence.objects.visible(), Word.objects.visible(), exclude_sentence_ids=excluded
            )
            self.assertIsNotNone(question)
            self.assertEqual(question.source_sentence_id, sentences[0].pk)

    def test_후보보다_많이_달라면_있는_만큼_겹치지_않게(self) -> None:
        for n in (4, BIG):
            caches["pools"].clear()
            Word.objects.all().delete()
            words = _words(n)
            picked = [w.pk for w in pick_pooled(Word.objects.visible(), 100)]
            self.assertEqual(sorted(picked), sorted(w.pk for w in words))
            picked = [w.pk for w in pick_pooled(Word.objects.visible(), 100, exclude=[words[0].pk])]
            self.assertEqual(sorted(picked), sorted(w.pk for w in words[1:]))

    def test_많이_빼도_count_개를_채운다(self) -> None:
        """뺄 것 수만큼 넉넉히 뽑는 방식이 모자라게 돌려주지 않는지. 남은 셋이 늘 다 나온다."""
        words = _words(BIG + 2)
        excluded = {w.pk for w in words[3:]}
        for seed in range(40):
            random.seed(seed)
            picked = [w.pk for w in pick_pooled(Word.objects.visible(), 3, exclude=excluded)]
            self.assertEqual(sorted(picked), sorted(w.pk for w in words[:3]))

    def test_풀에_없는_번호를_빼도_count_개를_채운다(self) -> None:
        words = _words(BIG)
        outsiders = list(range(10**9, 10**9 + 50))
        for seed in range(20):
            random.seed(seed)
            picked = pick_pooled(Word.objects.visible(), 5, exclude=outsiders)
            self.assertEqual(len({w.pk for w in picked}), 5)
            self.assertTrue({w.pk for w in picked} <= {w.pk for w in words})

    def test_전부_빼면_빈_목록(self) -> None:
        words = _words(BIG)
        self.assertEqual(pick_pooled(Word.objects.visible(), 2, exclude={w.pk for w in words}), [])

    def test_빈_풀은_빈_목록(self) -> None:
        _words(3)
        Word.objects.update(is_reviewed=False)
        self.assertEqual(pick_pooled(Word.objects.visible(), 3), [])
        self.assertIsNone(make_question(Word.objects.visible(), QuizKind.MEANING))

    def test_none_과_빈_pk_in_은_빈_목록이고_터지지_않는다(self) -> None:
        _words(3)
        self.assertEqual(pick_pooled(Word.objects.none(), 3), [])
        self.assertEqual(pick_pooled(Word.objects.visible().filter(pk__in=[]), 3), [])
        self.assertEqual(pick_pooled(Word.objects.none(), 3, exclude=[1, 2]), [])

    def test_count_0_과_음수는_DB_에_묻지_않고_빈_목록(self) -> None:
        _words(3)
        with self.assertNumQueries(0):
            self.assertEqual(pick_pooled(Word.objects.visible(), 0), [])
            self.assertEqual(pick_pooled(Word.objects.visible(), -1), [])

    def test_only_같은_queryset_설정을_지킨다(self) -> None:
        _words(BIG)
        pick_pooled(Word.objects.visible(), 1)
        picked = pick_pooled(Word.objects.visible().only("pk", "term"), 3)
        self.assertEqual(len(picked), 3)
        self.assertIn("meaning", picked[0].get_deferred_fields())


class SmallPoolTests(PooledHarness):
    """POOL_MIN 보다 적은 조건은 기억하지 않는다. 매번 새로 읽어 늦음이 없다."""

    def test_작은_풀은_매번_새로_읽어_새_단어가_바로_나온다(self) -> None:
        _words(sampling.POOL_MIN - 2)
        pick_pooled(Word.objects.visible(), 1)
        self.assertIsNone(caches["pools"].get(_key(Word.objects.visible())))
        late = Word.objects.create(term="lateone", meaning="늦게", category="git", is_reviewed=True)
        self.assertIn(late.pk, {w.pk for w in pick_pooled(Word.objects.visible(), 100)})

    def test_빈_풀은_기억하지_않아_처음_검수한_것이_바로_나온다(self) -> None:
        self.assertEqual(pick_pooled(Word.objects.visible(), 1), [])
        _words(1)
        self.assertEqual(len(pick_pooled(Word.objects.visible(), 1)), 1)

    def test_경계_POOL_MIN_빼기_하나는_기억하지_않고_POOL_MIN_은_기억한다(self) -> None:
        words = _words(sampling.POOL_MIN)
        _hide(words[:1])
        pick_pooled(Word.objects.visible(), 1)
        self.assertIsNone(caches["pools"].get(_key(Word.objects.visible())))
        Word.objects.filter(pk=words[0].pk).update(is_reviewed=True)
        pick_pooled(Word.objects.visible(), 1)
        self.assertEqual(len(caches["pools"].get(_key(Word.objects.visible()))), sampling.POOL_MIN)

    def test_작은_풀은_두번째도_두_쿼리(self) -> None:
        _words(5)
        pick_pooled(Word.objects.visible(), 1)
        with self.assertNumQueries(2):
            pick_pooled(Word.objects.visible(), 1)


class LateVisibilityTests(PooledHarness):
    """새로 검수한 것은 기억이 살아 있는 동안 안 나오고 비우면 나온다(의도한 늦음)."""

    def test_새_단어는_기억이_끝나야_나온다(self) -> None:
        _words(BIG)
        self.assertEqual(len(pick_pooled(Word.objects.visible(), 100)), BIG)
        late = Word.objects.create(term="lateone", meaning="늦게", category="git", is_reviewed=False)
        Word.objects.filter(pk=late.pk).update(is_reviewed=True)

        for _ in range(10):
            self.assertNotIn(late.pk, {w.pk for w in pick_pooled(Word.objects.visible(), 100)})

        caches["pools"].clear()
        self.assertIn(late.pk, {w.pk for w in pick_pooled(Word.objects.visible(), 100)})


class PoolMaxFallbackTests(PooledHarness):
    """번호가 POOL_MAX 를 넘으면 pick_random 으로 돌아간다."""

    def test_상한을_넘으면_pick_random_으로_고르고_exclude_를_지킨다(self) -> None:
        words = _words(10)
        excluded = {w.pk for w in words[:8]}
        with (
            mock.patch.object(sampling, "POOL_MAX", 3),
            mock.patch.object(sampling, "pick_random", wraps=sampling.pick_random) as spy,
        ):
            for seed in range(20):
                random.seed(seed)
                picked = pick_pooled(Word.objects.visible(), 10, exclude=excluded)
                self.assertEqual(sorted(w.pk for w in picked), sorted(w.pk for w in words[8:]))
        self.assertEqual(spy.call_count, 20)

    def test_상한을_넘은_조건은_다음부터_세지_않고_바로_pick_random(self) -> None:
        """두 번째부터는 번호를 세는 쿼리 없이 pick_random 의 두 쿼리만 쓴다."""
        _words(10)
        with mock.patch.object(sampling, "POOL_MAX", 3):
            pick_pooled(Word.objects.visible(), 1)
            with self.assertNumQueries(2):
                self.assertEqual(len(pick_pooled(Word.objects.visible(), 1)), 1)

    def test_딱_상한이면_기억한다(self) -> None:
        _words(BIG)
        with (
            mock.patch.object(sampling, "POOL_MAX", BIG),
            mock.patch.object(sampling, "pick_random", wraps=sampling.pick_random) as spy,
        ):
            self.assertEqual(len(pick_pooled(Word.objects.visible(), BIG)), BIG)
            self.assertEqual(len(pick_pooled(Word.objects.visible(), BIG)), BIG)
        spy.assert_not_called()
        self.assertEqual(len(caches["pools"].get(_key(Word.objects.visible()))), BIG)

    def test_상한을_넘어도_검수취소한_것은_안_나온다(self) -> None:
        words = _words(10)
        hidden = _hide(words[:5])
        with mock.patch.object(sampling, "POOL_MAX", 3):
            for seed in range(20):
                random.seed(seed)
                picked = {w.pk for w in pick_pooled(Word.objects.visible(), 10)}
                self.assertEqual(picked & hidden, set())
                self.assertEqual(len(picked), 5)


class UniformityTests(PooledHarness):
    """exclude 를 뺀 남은 후보 전체에서 고르게 뽑는다. 모두 기억 경로(BIG 이상)에서 본다."""

    def _assert_even(self, counts: Counter, expected: float, spread: float) -> None:
        for pk, n in counts.items():
            self.assertTrue(expected - spread <= n <= expected + spread, f"{pk}: {n}")

    def test_하나씩_뽑으면_전체에서_고르다(self) -> None:
        words = _words(BIG)
        random.seed(2026)
        draws = 200 * BIG
        counts = Counter(pick_pooled(Word.objects.visible(), 1)[0].pk for _ in range(draws))
        self.assertEqual(set(counts), {w.pk for w in words})
        # 기대 200, 표준편차 약 14. 4.5 표준편차 밖이면 치우친 것이다.
        self._assert_even(counts, 200, 62)

    def test_하나를_빼면_남은_것끼리_고르다(self) -> None:
        words = _words(BIG)
        random.seed(99)
        draws = 200 * (BIG - 1)
        counts = Counter(
            pick_pooled(Word.objects.visible(), 1, exclude=[words[0].pk])[0].pk for _ in range(draws)
        )
        self.assertEqual(set(counts), {w.pk for w in words[1:]})
        self._assert_even(counts, 200, 62)

    def test_많이_빼고_셋씩_뽑아도_남은_것끼리_고르다(self) -> None:
        """BIG 개 중 BIG-10 개를 빼고 셋씩 2천 번. 남은 열 개가 각각 기대 600(표준편차 약 20)."""
        words = _words(BIG)
        keep = words[:10]
        excluded = [w.pk for w in words[10:]]
        random.seed(7)
        counts: Counter = Counter()
        for _ in range(2000):
            picked = pick_pooled(Word.objects.visible(), 3, exclude=excluded)
            self.assertEqual(len({w.pk for w in picked}), 3)
            counts.update(w.pk for w in picked)
        self.assertEqual(set(counts), {w.pk for w in keep})
        self._assert_even(counts, 600, 92)

    def test_자리마다_고르다(self) -> None:
        """셋씩 뽑을 때 첫 자리에 오는 것도 고르다. 보기 순서가 정답을 흘리지 않는다."""
        words = _words(BIG)
        random.seed(8)
        draws = 200 * (BIG - 3)
        excluded = [w.pk for w in words[:3]]
        first = Counter(pick_pooled(Word.objects.visible(), 3, exclude=excluded)[0].pk for _ in range(draws))
        self.assertEqual(set(first), {w.pk for w in words[3:]})
        self._assert_even(first, 200, 62)


class QueryCountTests(PooledHarness):
    """기억이 살아 있으면 덜 묻는다."""

    def test_고르기_하나는_처음_두_쿼리_두번째부터_한_쿼리(self) -> None:
        _words(BIG)
        with self.assertNumQueries(2):
            pick_pooled(Word.objects.visible(), 2)
        with self.assertNumQueries(1):
            pick_pooled(Word.objects.visible(), 2)

    def test_단어_문제는_처음_네_쿼리_두번째부터_두_쿼리(self) -> None:
        """정답 고르기와 보기 고르기가 각각 번호 세기를 건너뛴다(한 분류라 보기 풀이 하나다)."""
        _words(BIG)
        random.seed(1)
        with self.assertNumQueries(4):
            self.assertIsNotNone(make_question(Word.objects.visible(), QuizKind.MEANING))
        with self.assertNumQueries(2):
            self.assertIsNotNone(make_question(Word.objects.visible(), QuizKind.MEANING))
        with self.assertNumQueries(2):
            self.assertIsNotNone(make_question(Word.objects.visible(), QuizKind.TERM))

    def test_기억이_꺼지면_두번째도_네_쿼리(self) -> None:
        """위 테스트가 기억 덕에 줄어든 것인지 보는 대조군."""
        _words(BIG)
        random.seed(1)
        with override_settings(
            CACHES={**settings.CACHES, "pools": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
        ):
            make_question(Word.objects.visible(), QuizKind.MEANING)
            with self.assertNumQueries(4):
                make_question(Word.objects.visible(), QuizKind.MEANING)


class SeparateConditionTests(PooledHarness):
    """조건이 다르면 기억도 따로다."""

    def test_분류가_다르면_다른_풀(self) -> None:
        git = {w.pk for w in _words(BIG, prefix="g", category="git")}
        api = {w.pk for w in _words(BIG, prefix="a", category="api")}
        everything = Word.objects.visible()
        self.assertEqual({w.pk for w in pick_pooled(everything.filter(category="git"), 100)}, git)
        self.assertEqual({w.pk for w in pick_pooled(everything.filter(category="api"), 100)}, api)
        self.assertEqual({w.pk for w in pick_pooled(everything, 100)}, git | api)
        # 셋 다 기억됐고, 다시 물어도 섞이지 않는다.
        self.assertEqual({w.pk for w in pick_pooled(everything.filter(category="git"), 100)}, git)
        self.assertEqual(len(caches["pools"].get(_key(everything))), 2 * BIG)

    def test_분류별_보기는_정답과_같은_분류에서(self) -> None:
        git = {w.pk for w in _words(BIG, prefix="g", category="git")}
        api = {w.pk for w in _words(BIG, prefix="a", category="api")}
        random.seed(21)
        for _ in range(60):
            question = make_question(Word.objects.visible(), QuizKind.MEANING)
            group = git if question.answer_id in git else api
            self.assertTrue(_ids(question) <= group)

    def test_모델이_다르면_다른_풀(self) -> None:
        _words(BIG)
        sentences = {_sentence(f"Line {_letters(i)}.").pk for i in range(BIG)}
        pick_pooled(Word.objects.visible(), 1)
        picked = pick_pooled(Sentence.objects.visible(), 100)
        self.assertTrue(all(isinstance(row, Sentence) for row in picked))
        self.assertEqual({row.pk for row in picked}, sentences)

    def test_일일공부의_좁힌_범위끼리_섞이지_않는다(self) -> None:
        """묶음은 작아 기억하지 않지만, 큰 묶음(BIG)이 기억된 뒤에도 다른 묶음에서만 나온다."""
        words = _words(3 * BIG)
        first = [w.pk for w in words[:BIG]]
        second = [w.pk for w in words[BIG : 2 * BIG]]
        small = [w.pk for w in words[2 * BIG : 2 * BIG + 2]]
        random.seed(31)
        for _ in range(10):
            self.assertIn(session.make_question([], [], word_ids=first).answer_id, first)
        for _ in range(30):
            self.assertIn(session.make_question([], [], word_ids=second).answer_id, second)
        for _ in range(20):
            self.assertIn(session.make_question([], [], word_ids=small).answer_id, small)

    def test_상황_문제의_자리와_장면_보기가_섞이지_않는다(self) -> None:
        places = {f"{_letters(i)} 서버 로그" for i in range(BIG)}
        scenes = {f"{_letters(i)} 배포할 때" for i in range(BIG)}
        for i, c in enumerate(sorted(places | scenes)):
            _sentence(f"Situation line {i}.", context=c)
        random.seed(41)
        kinds = set()
        for _ in range(80):
            question = make_situation_question(Sentence.objects.visible())
            texts = {c.text for c in question.choices}
            group = "place" if texts & places else "scene"
            kinds.add(group)
            self.assertTrue(texts <= (places if group == "place" else scenes), texts)
        self.assertEqual(kinds, {"place", "scene"})
