"""상황 고르기 쿼리(LIKE)와 일상영어 출제 캐시(lru_cache)를 깨뜨려 보는 테스트.

2026-11-13 성능 개선으로 두 곳이 바뀌었다.

1. quiz._place_filter - 보기를 "정답과 같은 종류(자리/장면)" 로만 고르는
   쿼리를 Postgres 정규식에서 LIKE(contains/endswith)로 바꿨다. 정답의 종류는
   파이썬 _is_place 가 정하고 보기는 DB 가 정하므로, 둘이 같은 답을 내야
   한다. 갈리면 에러 없이 보기가 섞인 문제가 나온다.
2. talk.is_speakable - 결과를 lru_cache 로 기억한다. 출제가 문제마다 표현
   전부를 이 함수에 대므로, 기억한 답이 틀리거나 이상한 값을 기억하면
   소리로 채점할 수 없는 항목(약어·숫자·기호)이 출제된다.

옛 정규식 구현을 이 파일 안에 그대로 다시 만들어 두고 새 구현과 비교한다.
파이썬과 DB 가 갈리는 입력이 나오면, 그것이 이번에 생긴 것인지(회귀) 원래
있던 것인지를 그 비교로 가른다.
"""

import re

from django.core.cache import cache
from django.db.models import Q
from django.db.models.functions import Trim
from django.test import TestCase

from .models import DailyPhrase, PhraseScene, Sentence, Word
from .quiz import (
    CHOICE_COUNT,
    QuizKind,
    _is_place,
    _place_filter,
    make_situation_question,
)
from .talk import is_speakable

SITUATION_URL = "/api/vocab/sentences/quiz/"
TALK_URL = "/api/vocab/talk/question/"
PLACE_QUESTION = "이 말은 어디서 보이나?"

# 2026-11-13 이전 구현을 글자 그대로 옮긴 것. 새 구현과 비교하는 기준이다.
_OLD_SCENE_END = re.compile(r"(때|경우|중|뒤|전|후|면)$")
_OLD_PLACE_WORD = re.compile(
    r"(교재|로그|문서|메시지|화면|출력|콘솔|리포트|본문|응답|Events|Description)"
)


def _old_is_place(context: str) -> bool:
    context = context.strip()
    if _OLD_SCENE_END.search(context):
        return False
    return bool(_OLD_PLACE_WORD.search(context))


def _old_place_filter(pool, want_place: bool):
    trimmed = pool.annotate(_ctx=Trim("context"))
    is_place = Q(_ctx__regex=_OLD_PLACE_WORD.pattern) & ~Q(
        _ctx__regex=_OLD_SCENE_END.pattern
    )
    return trimmed.filter(is_place) if want_place else trimmed.exclude(is_place)


# 파이썬과 DB 가 같은 답을 내야 하는 값들. 앞뒤 스페이스는 여기 든다.
TRICKY_CONTEXTS = (
    # 자리 낱말과 장면 어미가 동시에 - 어미가 이겨야 한다
    "로그를 볼 때",
    "화면이 덜컹거릴 때",
    "응답을 JSON 으로 파싱할 경우",
    "콘솔 출력을 보는 중",
    "배포 뒤",
    "메시지를 보내기 전",
    "리포트를 쓴 후",
    "문서를 열면",
    # 어미 뒤·앞뒤 스페이스
    "로그를 볼 때 ",
    "로그를 볼 때   ",
    "   로그를 볼 때",
    "  서버 로그  ",
    "서버 로그 ",
    " 콘솔",
    # 순수 자리
    "서버 로그",
    "운영체제 교재",
    "API 응답 본문",
    "브라우저 콘솔",
    "CI 출력",
    "PR 리포트",
    "공식 문서",
    "커밋 메시지",
    "에러 화면",
    "AWS CloudTrail Events",
    "GitHub 저장소 Description",
    # 대소문자
    "events",
    "EVENTS",
    "Events",
    "description 칸",
    "DESCRIPTION",
    "로그events",
    # 낱말이 다른 낱말의 일부
    "로그인 화면이 안 뜰",
    "블로그",
    "카탈로그",
    "프롤로그 문서",
    "응답성",
    "출력기",
    "중간 점검",
    "전체 화면",
    "면접",
    "도면",
    "후보 목록",
    "뒤로 가기 버튼",
    "때때로 보는 로그",
    "로그 중간",
    "로그 중간 ",
    # 장면 어미 단독
    "때",
    "면",
    "회의가 길어질 때",
    "npm install 실행 시",
    # LIKE 와일드카드·정규식 메타문자
    "%",
    "_",
    "\\",
    "%로그%",
    "로그_",
    "_때",
    "%때",
    "\\때",
    "로그\\",
    "로그%",
    "[로그",
    "(로그|문서)",
    "로그.*",
    "^로그$",
    "로그$",
    "때$",
    "로그 때)",
    "로그 (때)",
    "a+b?c{2}",
    "'; --",
    '"로그"',
    # 비슷하게 생긴 다른 글자
    "로그를 볼 떄",
    "Ｅｖｅｎｔｓ",
    # 아주 긴 값(칸 최대 200자)
    "가" * 197 + "로그",
    "로그" + "가" * 197 + "때",
    "로그" + " " * 197 + "때",
    "로" * 200,
    # 빈 듯한 값
    " ",
    "   ",
)

# 파이썬 strip() 은 지우고 Postgres TRIM 은 안 지우는 끝 공백 글자. 어미 뒤에
# 붙으면 둘이 갈린다. 끝 줄바꿈·탭은 알고 둔 차이라 따로 둔다.
UNICODE_SPACE_CONTEXTS = (
    "로그를 볼 때　",  # 전각 공백
    "로그를 볼 때 ",  # NBSP
    "　서버 로그　",
    " 콘솔 ",
)
KNOWN_NEWLINE_TAB_CONTEXTS = (
    "로그를 볼 때\n",
    "로그를 볼 때\t",
    "로그를 볼 때 \n ",
)


def _sentence(context: str, n: int, **kw) -> Sentence:
    defaults = {
        "text": f"Sentence number {n}.",
        "translation": f"문장 {n}",
        "context": context,
        "description": f"설명 {n}",
        "category": "git",
        "is_reviewed": True,
    }
    defaults.update(kw)
    return Sentence.objects.create(**defaults)


class PlaceFilterParityTest(TestCase):
    """_place_filter(DB) 와 _is_place(파이썬) 가 같은 값을 자리로 보는가."""

    @classmethod
    def setUpTestData(cls):
        Sentence.objects.all().delete()
        values = TRICKY_CONTEXTS + UNICODE_SPACE_CONTEXTS + KNOWN_NEWLINE_TAB_CONTEXTS
        cls.by_pk = {
            _sentence(ctx, i).pk: ctx for i, ctx in enumerate(values)
        }

    def _ids(self, qs) -> set[int]:
        return set(qs.values_list("pk", flat=True))

    def _disagreements(self, filter_fn, values) -> list[str]:
        pool = Sentence.objects.filter(context__in=values)
        place_ids = self._ids(filter_fn(pool, True))
        return [
            repr(s.context)
            for s in pool
            if _is_place(s.context) != (s.pk in place_ids)
        ]

    def test_까다로운_값에서_DB와_파이썬이_같은_답을_낸다(self):
        """자리·어미 겹침, 스페이스, 대소문자, 와일드카드, 긴 값 전부."""
        self.assertEqual(self._disagreements(_place_filter, TRICKY_CONTEXTS), [])

    def test_자리와_장면이_풀을_정확히_둘로_나눈다(self):
        """True 쪽과 False 쪽은 겹치지 않고 합치면 풀 전체다.

        한 문장이 양쪽에 다 들거나 어디에도 안 들면, 그 문장은 보기로
        섞이거나 영영 보기로 안 나온다.
        """
        pool = Sentence.objects.all()
        place = self._ids(_place_filter(pool, True))
        scene = self._ids(_place_filter(pool, False))
        self.assertEqual(place & scene, set())
        self.assertEqual(place | scene, set(self.by_pk))

    def test_새_쿼리가_옛_정규식_쿼리와_같은_집합을_낸다(self):
        """유니코드 공백·줄바꿈까지 넣어도 LIKE 와 옛 정규식의 결과가 같다.

        파이썬과 DB 가 갈리는 값이 있더라도 이 테스트가 통과하면 그것은
        이번 변경이 만든 것이 아니다.
        """
        pool = Sentence.objects.all()
        for want_place in (True, False):
            with self.subTest(want_place=want_place):
                self.assertEqual(
                    self._ids(_place_filter(pool, want_place)),
                    self._ids(_old_place_filter(pool, want_place)),
                )

    def test_파이썬_판정이_옛_정규식과_같다(self):
        """정규식을 튜플에서 다시 만들었다. 옛 글자 그대로의 정규식과 답이 같아야 한다."""
        values = TRICKY_CONTEXTS + UNICODE_SPACE_CONTEXTS + KNOWN_NEWLINE_TAB_CONTEXTS
        diff = [repr(v) for v in values if _is_place(v) != _old_is_place(v)]
        self.assertEqual(diff, [])

    def test_유니코드_끝_공백은_옛_구현에서도_갈렸다(self):
        """전각 공백·NBSP 가 어미 뒤에 붙으면 파이썬은 장면, DB 는 자리로 본다.

        파이썬 strip() 은 이 글자를 지우고 Postgres TRIM 은 스페이스만
        지워서다. 옛 정규식 구현도 똑같이 갈렸으므로 회귀는 아니다. 독스트링은
        줄바꿈·탭만 적어 두었다. 둘 중 하나라도 바뀌면(고쳐지거나 새 구현만
        달라지면) 이 테스트가 알려 준다.
        """
        new = self._disagreements(_place_filter, UNICODE_SPACE_CONTEXTS)
        old = self._disagreements(_old_place_filter, UNICODE_SPACE_CONTEXTS)
        self.assertEqual(new, old)
        self.assertIn(repr("로그를 볼 때　"), new)
        self.assertIn(repr("로그를 볼 때 "), new)

    def test_끝_줄바꿈_탭은_알고_둔_차이다(self):
        """참고용. 독스트링에 적힌 차이가 새 구현과 옛 구현에서 같은지만 본다."""
        new = self._disagreements(_place_filter, KNOWN_NEWLINE_TAB_CONTEXTS)
        old = self._disagreements(_old_place_filter, KNOWN_NEWLINE_TAB_CONTEXTS)
        self.assertEqual(new, old)


class SituationQuestionKindTest(TestCase):
    """make_situation_question 이 보기 넷을 같은 종류로만 내는가."""

    PLACES = (
        "서버 로그", "운영체제 교재", "공식 문서", "커밋 메시지", "에러 화면 캡처",
        "CI 출력", "브라우저 콘솔", "PR 리포트", "API 응답 본문",
        "AWS CloudTrail Events", "GitHub 저장소 Description",
        "  배포 로그  ", "%로그%", "로그_\\",
    )
    SCENES = (
        "로그를 볼 때", "화면이 덜컹거릴 때", "응답을 파싱할 경우", "배포 중",
        "머지 뒤", "커밋하기 전", "리뷰를 받은 후", "문서를 열면",
        "회의가 길어질 때", "로그를 볼 때 ", "events", "블로그를 볼 때", "%때",
        "로그 (때",
    )

    def setUp(self):
        Sentence.objects.all().delete()

    def _seed(self, places, scenes):
        n = 0
        for ctx in (*places, *scenes):
            _sentence(ctx, n)
            n += 1

    def _assert_same_kind(self, q):
        self.assertIsNotNone(q)
        self.assertEqual(len(q.choices), CHOICE_COUNT)
        texts = [c.text for c in q.choices]
        kinds = {_is_place(t) for t in texts}
        self.assertEqual(len(kinds), 1, texts)
        want_place = kinds.pop()
        self.assertEqual(q.question == PLACE_QUESTION, want_place, (q.question, texts))
        self.assertEqual(len(set(texts)), CHOICE_COUNT, texts)

    def test_넉넉하면_보기_넷이_늘_같은_종류다(self):
        self._seed(self.PLACES, self.SCENES)
        pool = Sentence.objects.visible()
        seen_kinds = set()
        for _ in range(80):
            q = make_situation_question(pool)
            self._assert_same_kind(q)
            seen_kinds.add(q.question)
        # 둘 다 실제로 나와야 위 단언이 양쪽을 다 본 것이다.
        self.assertEqual(seen_kinds, {PLACE_QUESTION, QuizKind.QUESTIONS[QuizKind.SITUATION]})

    def test_정답을_지정해도_같은_종류다(self):
        """복습 경로. 자리 낱말과 어미가 겹친 값·와일드카드 값을 정답으로."""
        self._seed(self.PLACES, self.SCENES)
        pool = Sentence.objects.visible()
        for ctx in ("로그를 볼 때", "로그를 볼 때 ", "%로그%", "로그_\\", "%때",
                    "  배포 로그  ", "events", "AWS CloudTrail Events"):
            answer = Sentence.objects.get(context=ctx)
            with self.subTest(ctx=ctx):
                for _ in range(10):
                    q = make_situation_question(pool, answer=answer)
                    self._assert_same_kind(q)
                    self.assertEqual(q.answer_id, answer.pk)
                    self.assertEqual(q.question == PLACE_QUESTION, _is_place(ctx))

    def test_자리가_모자라면_섞어서라도_낸다(self):
        """자리 셋(정답 + 둘)뿐이면 자리 문제는 None 이 아니라 섞인 장면형 문제다."""
        self._seed(self.PLACES[:3], self.SCENES)
        pool = Sentence.objects.visible()
        for ctx in self.PLACES[:3]:
            answer = Sentence.objects.get(context=ctx)
            q = make_situation_question(pool, answer=answer)
            self.assertIsNotNone(q)
            self.assertEqual(len(q.choices), CHOICE_COUNT)
            self.assertNotEqual(q.question, PLACE_QUESTION)
        # 장면 정답은 여전히 장면끼리.
        for _ in range(20):
            answer = Sentence.objects.filter(context__in=self.SCENES).order_by("?").first()
            self._assert_same_kind(make_situation_question(pool, answer=answer))

    def test_장면이_모자라면_섞어서라도_낸다(self):
        self._seed(self.PLACES, self.SCENES[:2])
        pool = Sentence.objects.visible()
        for ctx in self.SCENES[:2]:
            answer = Sentence.objects.get(context=ctx)
            q = make_situation_question(pool, answer=answer)
            self.assertIsNotNone(q)
            self.assertEqual(len(q.choices), CHOICE_COUNT)
        for _ in range(20):
            answer = Sentence.objects.filter(context__in=self.PLACES).order_by("?").first()
            self._assert_same_kind(make_situation_question(pool, answer=answer))

    def test_풀이_넷보다_작으면_None_이다(self):
        self._seed(self.PLACES[:2], self.SCENES[:1])
        self.assertIsNone(make_situation_question(Sentence.objects.visible()))

    def test_미검수_문장은_보기에_안_나온다(self):
        """검수 게이트. 미검수 자리·장면이 정답·보기 어디에도 새면 안 된다."""
        self._seed(self.PLACES, self.SCENES)
        hidden = {
            _sentence("숨은 로그", 900, is_reviewed=False).pk,
            _sentence("숨은 장면일 때", 901, is_reviewed=False).pk,
        }
        pool = Sentence.objects.visible()
        for _ in range(60):
            q = make_situation_question(pool)
            self.assertFalse(hidden & {c.id for c in q.choices})


class SituationQuizApiTest(TestCase):
    """GET /api/vocab/sentences/quiz/?kind=situation 을 실제로 부른다."""

    def setUp(self):
        cache.clear()
        Sentence.objects.all().delete()
        Word.objects.all().delete()
        n = 0
        for ctx in (*SituationQuestionKindTest.PLACES, *SituationQuestionKindTest.SCENES):
            _sentence(ctx, n)
            n += 1
        self.hidden = {
            _sentence("숨은 로그", 900, is_reviewed=False).pk,
            _sentence("숨은 장면일 때", 901, is_reviewed=False).pk,
            _sentence("서버 로그", 902, is_reviewed=False).pk,
        }

    def test_상황_고르기가_200이고_보기가_같은_종류다(self):
        for _ in range(40):
            res = self.client.get(SITUATION_URL, {"kind": "situation"})
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            texts = [c["text"] for c in body["choices"]]
            self.assertEqual(len({_is_place(t) for t in texts}), 1, texts)
            self.assertEqual(body["question"] == PLACE_QUESTION, _is_place(texts[0]))
            self.assertFalse(self.hidden & {c["id"] for c in body["choices"]})

    def test_까다로운_문장을_지정해도_200이다(self):
        for ctx in ("%로그%", "로그_\\", "%때", "로그 (때", "로그를 볼 때 "):
            pk = Sentence.objects.get(context=ctx, is_reviewed=True).pk
            with self.subTest(ctx=ctx):
                res = self.client.get(SITUATION_URL, {"kind": "situation", "item": pk})
                self.assertEqual(res.status_code, 200, res.content)
                self.assertIn(pk, [c["id"] for c in res.json()["choices"]])

    def test_미검수_문장을_지정하면_정답이_되지_않는다(self):
        pk = next(iter(self.hidden))
        res = self.client.get(SITUATION_URL, {"kind": "situation", "item": pk})
        self.assertNotEqual(res.status_code, 500)
        if res.status_code == 200:
            self.assertNotIn(pk, [c["id"] for c in res.json()["choices"]])

    def test_풀이_비면_404이고_500이_아니다(self):
        res = self.client.get(SITUATION_URL, {"kind": "situation", "category": "cs"})
        self.assertEqual(res.status_code, 404, res.content)

    def test_이상한_exclude도_500이_아니다(self):
        for exclude in ("abc", "-1", "9" * 30, "1,,2", "%", "\\"):
            with self.subTest(exclude=exclude):
                res = self.client.get(SITUATION_URL, {"kind": "situation", "exclude": exclude})
                self.assertIn(res.status_code, (200, 400, 404), res.content)


# 출제돼야 하는 것과 절대 안 되는 것. 안 되는 쪽은 약어·숫자·기호.
SPEAKABLE_PHRASES = (
    "nice to meet you", "how much is this", "see you later",
    "what's up", "I'm fine thanks", "thank you so much",
)
UNSPEAKABLE_PHRASES = (
    "see you at 5", "OK see you", "call me ASAP", "is it 24/7",
    "wow!", "C++ is hard", "what's the URL", "plan B",
)
SPEAKABLE_TERMS = ("cache", "rebase", "blue-green", "API key")
UNSPEAKABLE_TERMS = ("HTTP", "API", "I/O", "404", "C#", "OAuth2", "big O")


class SpeakableCacheTest(TestCase):
    """is_speakable 의 lru_cache 가 답을 바꾸지 않는가."""

    CORPUS = (
        *SPEAKABLE_PHRASES, *UNSPEAKABLE_PHRASES, *SPEAKABLE_TERMS, *UNSPEAKABLE_TERMS,
        "", " ", "I", "A", "a", "i", "café", "résumé", "TV", "tV", "big o",
        "x" * 120, "hello　world", "hello\nworld",
    )

    def setUp(self):
        is_speakable.cache_clear()

    def test_기억한_답이_원래_함수의_답과_같다(self):
        raw = is_speakable.__wrapped__
        for text in self.CORPUS:
            with self.subTest(text=text):
                first = is_speakable(text)
                second = is_speakable(text)
                self.assertEqual(first, raw(text))
                self.assertEqual(second, first)

    def test_두번째부터는_기억한_답을_쓴다(self):
        is_speakable("nice to meet you")
        before = is_speakable.cache_info().hits
        is_speakable("nice to meet you")
        self.assertEqual(is_speakable.cache_info().hits, before + 1)

    def test_크기가_항목_수보다_넉넉하다(self):
        """출제는 매번 전부를 같은 순서로 훑는다. 크기가 모자라면 한 번도 안 맞는다.

        2026-11-13 기준 일상 표현과 개발 용어를 합쳐 9,616개다.
        """
        self.assertGreaterEqual(is_speakable.cache_info().maxsize, 20000)

    def test_문자열이_아니면_예전처럼_오류이고_기억하지_않는다(self):
        for bad in (None, 5, 3.5, b"hello", ["hello"], {"a": 1}):
            with self.subTest(bad=repr(bad)):
                size = is_speakable.cache_info().currsize
                with self.assertRaises(TypeError):
                    is_speakable(bad)
                # 두 번째에도 오류여야 한다(첫 오류가 엉뚱한 답으로 굳지 않는다).
                with self.assertRaises(TypeError):
                    is_speakable(bad)
                self.assertEqual(is_speakable.cache_info().currsize, size)
        self.assertTrue(is_speakable("hello"))
        self.assertFalse(is_speakable("HTTP"))

    def test_str_하위_클래스도_같은_글자면_같은_답이다(self):
        class Marked(str):
            pass

        self.assertEqual(is_speakable(Marked("HTTP")), is_speakable("HTTP"))
        self.assertEqual(is_speakable(Marked("cache")), is_speakable("cache"))


class TalkQuestionCacheApiTest(TestCase):
    """GET /api/vocab/talk/question/ 이 캐시 전후로 같은 후보에서 내는가."""

    def setUp(self):
        cache.clear()
        # 캐시가 빠져도 이 클래스는 출제 결과만 보도록 cache_clear 가 없어도 돈다.
        getattr(is_speakable, "cache_clear", lambda: None)()
        DailyPhrase.objects.all().delete()
        Word.objects.all().delete()
        scenes = (PhraseScene.GREETING, PhraseScene.SHOPPING)
        self.ok_phrases, self.bad_phrases = set(), set()
        for i, text in enumerate((*SPEAKABLE_PHRASES, *UNSPEAKABLE_PHRASES)):
            p = DailyPhrase.objects.create(
                text=text,
                meaning="뜻",
                pronunciation="/x/",
                reading="엑스",
                is_reviewed=True,
                scene=scenes[i % 2],
                difficulty=DailyPhrase.Difficulty.EASY,
            )
            (self.ok_phrases if text in SPEAKABLE_PHRASES else self.bad_phrases).add(p.pk)
        # 검수 안 된 표현은 소리로 읽을 수 있어도 안 나와야 한다.
        self.hidden_phrase = DailyPhrase.objects.create(
            text="good morning everyone", meaning="뜻", pronunciation="/x/",
            reading="엑스", is_reviewed=False,
        ).pk
        self.ok_words, self.bad_words = set(), set()
        for text in (*SPEAKABLE_TERMS, *UNSPEAKABLE_TERMS):
            w = Word.objects.create(term=text, meaning="뜻", is_reviewed=True)
            (self.ok_words if text in SPEAKABLE_TERMS else self.bad_words).add(w.pk)
        self.hidden_word = Word.objects.create(
            term="stash", meaning="뜻", is_reviewed=False,
        ).pk

    def _served(self, times=60, **params) -> set[int]:
        ids = set()
        for _ in range(times):
            res = self.client.get(TALK_URL, params)
            self.assertEqual(res.status_code, 200, res.content)
            ids.add(res.json()["id"])
        return ids

    def test_캐시_전후로_같은_후보에서_낸다(self):
        cold = self._served()
        warm = self._served()
        for ids in (cold, warm):
            self.assertLessEqual(ids, self.ok_phrases)
            self.assertFalse(ids & self.bad_phrases)
            self.assertNotIn(self.hidden_phrase, ids)
        # 여섯 중 하나씩 60번이면 다 나온다(빠뜨릴 확률 6*(5/6)^60 < 1e-4).
        self.assertEqual(cold | warm, self.ok_phrases)

    def test_개발_용어도_약어_숫자_기호는_안_나온다(self):
        cold = self._served(kind="dev")
        warm = self._served(kind="dev")
        for ids in (cold, warm):
            self.assertLessEqual(ids, self.ok_words)
            self.assertFalse(ids & self.bad_words)
            self.assertNotIn(self.hidden_word, ids)

    def test_다_보면_404_문구가_그대로다(self):
        """exclude 로 소리 낼 수 있는 것을 다 빼면 고른 조건을 말하는 404."""
        everything = ",".join(map(str, self.ok_phrases))
        cases = (
            ({}, "읽을 것을 다 봤습니다. 잠시 뒤 다시 시작해보세요."),
            ({"level": 1}, "이 난이도는 다 봤습니다. 난이도를 바꾸거나 잠시 뒤 다시 해보세요."),
            ({"scene": PhraseScene.GREETING},
             "이 상황은 다 봤습니다. 상황을 바꾸거나 잠시 뒤 다시 해보세요."),
            ({"level": 1, "scene": PhraseScene.SHOPPING},
             "이 난이도·상황은 다 봤습니다. 다른 것을 고르거나 잠시 뒤 다시 해보세요."),
        )
        for warm in (False, True):
            if not warm:
                getattr(is_speakable, "cache_clear", lambda: None)()
            for params, detail in cases:
                with self.subTest(warm=warm, params=params):
                    res = self.client.get(TALK_URL, {**params, "exclude": everything})
                    self.assertEqual(res.status_code, 404, res.content)
                    self.assertEqual(res.json()["detail"], detail)

    def test_dev_는_scene_을_무시하고_문구도_상황을_말하지_않는다(self):
        everything = ",".join(map(str, self.ok_words))
        res = self.client.get(
            TALK_URL, {"kind": "dev", "scene": PhraseScene.GREETING, "exclude": everything}
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "읽을 것을 다 봤습니다. 잠시 뒤 다시 시작해보세요.")

    def test_exclude_하나만_남기면_그것만_나온다(self):
        keep = min(self.ok_phrases)
        others = ",".join(str(pk) for pk in self.ok_phrases if pk != keep)
        for _ in range(2):
            self.assertEqual(self._served(times=10, exclude=others), {keep})

    def test_이상한_exclude_level_scene_도_500이_아니다(self):
        for params in (
            {"exclude": "abc"}, {"exclude": "9" * 30}, {"exclude": "-1,-2"},
            {"level": "abc"}, {"level": "9" * 30}, {"scene": "%"}, {"scene": "\\"},
        ):
            with self.subTest(params=params):
                res = self.client.get(TALK_URL, params)
                self.assertIn(res.status_code, (200, 404), res.content)
