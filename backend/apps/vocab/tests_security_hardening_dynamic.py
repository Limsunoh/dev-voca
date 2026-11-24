"""낱개 채점 요청 제한(PracticeGradeThrottle)과 검색 낱말 상한(CappedSearchFilter)을 깨뜨려 본다.

계약:
  - 낱개 채점(단어·문장)은 로그인했으면 계정별 분당 120회, 게스트는 한 통에 그 20배.
    한 사람이 막혀도 다른 사람과 게스트는 안 막힌다. 429 는 다른 제한과 같은 한국어 안내다.
  - 소리내어 읽기의 제한은 기본 클래스 이름이 바뀐 뒤에도 그대로다(계정별, 게스트 20배,
    채점 통과 따로).
  - 검색은 앞 10낱말까지만 쓴다. 목록 필터와 순위 계산 둘 다. 따옴표로 묶은 말은 한 낱말이다.
  - 검수 안 된 항목은 낱말이 몇 개든 검색 결과에 안 나온다.

요청 제한 시계는 한 순간에 멈춘다. 120번 보내는 동안 1분이 넘어가면 결과가 바뀐다.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import LoginToken, token_digest
from apps.accounts.tests_security_hardening_dynamic import use_production_rates
from apps.learning.tests_mistakes import make_user

from .models import LearningItemQuerySet, Word
from .tests_search_rank import WORDS_URL, SearchClientMixin, make_word
from .throttles import PracticeGradeThrottle, TalkGradeThrottle, TalkQuestionThrottle

WORD_GRADE = "/api/vocab/words/grade/"
SENTENCE_GRADE = "/api/vocab/sentences/grade/"
TALK_QUESTION = "/api/vocab/talk/question/"
TALK_GRADE = "/api/vocab/talk/grade/"
TOO_MANY = r"^시도가 너무 많습니다\. \d+초 뒤에 다시 해주세요\.$"

FROZEN = 1_800_000_000.0


def freeze_throttle_clock(test: TestCase) -> None:
    patcher = mock.patch.object(SimpleRateThrottle, "timer", lambda self: FROZEN)
    patcher.start()
    test.addCleanup(patcher.stop)


class ThrottleCase(TestCase):
    def setUp(self):
        cache.clear()
        freeze_throttle_clock(self)
        self.a = LoginToken.objects.create(user=make_user("가")).key
        self.b = LoginToken.objects.create(user=make_user("나")).key

    def post(self, url: str, key: str | None = None):
        """본문은 비어 있다. 제한은 입력 검사보다 먼저 돌아 400 도 센다."""
        headers = {"HTTP_AUTHORIZATION": f"Token {key}"} if key else {}
        return self.client.post(url, {}, content_type="application/json", **headers)

    @contextmanager
    def rates(self, **rates: str):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, rates):
            yield


class PracticeGradeRealRateTest(ThrottleCase):
    """운영 값(120/min)을 그대로 걸어 센다."""

    def setUp(self):
        super().setUp()
        use_production_rates(self, "practice_grade")

    def test_계정은_120번째까지_되고_121번째는_429(self):
        codes = [self.post(WORD_GRADE, self.a).status_code for _ in range(120)]
        self.assertEqual(set(codes), {400})

        blocked = self.post(WORD_GRADE, self.a)
        self.assertEqual(blocked.status_code, 429)
        self.assertRegex(blocked.json()["detail"], TOO_MANY)
        self.assertIn("Retry-After", blocked.headers)

        # 다른 계정과 게스트는 그대로다.
        self.assertEqual(self.post(WORD_GRADE, self.b).status_code, 400)
        self.assertEqual(self.post(WORD_GRADE).status_code, 400)

    def test_단어와_문장_채점은_한_통을_나눠_쓴다(self):
        for i in range(120):
            self.post(WORD_GRADE if i % 2 else SENTENCE_GRADE, self.a)
        self.assertEqual(self.post(SENTENCE_GRADE, self.a).status_code, 429)
        self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 429)


class PracticeGradeGuestTest(ThrottleCase):
    def test_게스트는_한_통에_20배(self):
        with self.rates(practice_grade="1/min"):
            codes = [self.post(WORD_GRADE).status_code for _ in range(21)]
            self.assertEqual(codes, [400] * 20 + [429])
            # 게스트 통이 차도 로그인한 사람은 안 막힌다.
            self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 400)

    def test_로그인한_사람이_막혀도_게스트는_안_막힌다(self):
        with self.rates(practice_grade="1/min"):
            self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 400)
            self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 429)
            self.assertEqual(self.post(WORD_GRADE).status_code, 400)

    def test_만료_토큰은_401_이고_게스트_통도_계정_통도_안_센다(self):
        LoginToken.objects.filter(digest=token_digest(self.a)).update(
            created=timezone.now() - LoginToken.LIFETIME - timedelta(seconds=1)
        )
        with self.rates(practice_grade="1/min"):
            for _ in range(25):
                self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 401)
            self.assertEqual(self.post(WORD_GRADE).status_code, 400)

    def test_요율은_settings_의_practice_grade_다(self):
        self.assertEqual(PracticeGradeThrottle.scope, "practice_grade")
        self.assertIn("practice_grade", SimpleRateThrottle.THROTTLE_RATES)


class TalkThrottleRegressionTest(ThrottleCase):
    """기본 클래스 이름이 _TalkThrottle 에서 _PerUserOrGuest 로 바뀌었다. 동작은 그대로다."""

    def test_출제와_채점이_계정별로_센다(self):
        with self.rates(talk_question="1/min", talk_grade="1/min"):
            self.assertNotEqual(self.client.get(TALK_QUESTION, HTTP_AUTHORIZATION=f"Token {self.a}").status_code, 429)
            self.assertEqual(self.client.get(TALK_QUESTION, HTTP_AUTHORIZATION=f"Token {self.a}").status_code, 429)
            self.assertNotEqual(self.client.get(TALK_QUESTION, HTTP_AUTHORIZATION=f"Token {self.b}").status_code, 429)

            self.assertEqual(self.post(TALK_GRADE, self.a).status_code, 400)
            self.assertEqual(self.post(TALK_GRADE, self.a).status_code, 429)
            self.assertEqual(self.post(TALK_GRADE, self.b).status_code, 400)

    def test_게스트는_20배(self):
        with self.rates(talk_grade="1/min"):
            codes = [self.post(TALK_GRADE).status_code for _ in range(21)]
        self.assertEqual(codes, [400] * 20 + [429])

    def test_낱개_채점과_소리내어_읽기는_통이_따로다(self):
        """같은 통이면 낱개 연습을 많이 한 사람이 발음 연습에서 막힌다."""
        with self.rates(practice_grade="1/min", talk_grade="1/min"):
            self.post(WORD_GRADE, self.a)
            self.assertEqual(self.post(WORD_GRADE, self.a).status_code, 429)
            self.assertEqual(self.post(TALK_GRADE, self.a).status_code, 400)

    def test_scope_는_그대로(self):
        self.assertEqual(TalkQuestionThrottle.scope, "talk_question")
        self.assertEqual(TalkGradeThrottle.scope, "talk_grade")


# ---- 검색 낱말 상한 ----------------------------------------------------------


class SearchTermCapTest(SearchClientMixin, TestCase):
    def setUp(self):
        Word.objects.all().delete()
        make_word("alpha omega")
        make_word("alpha hidden", is_reviewed=False)

    def search(self, *terms: str) -> list[str]:
        return self.terms({"search": " ".join(terms)})

    def test_열한_번째_낱말은_무시한다(self):
        self.assertEqual(self.search(*["alpha"] * 10, "zzzz"), ["alpha omega"])

    def test_열_번째_낱말까지는_건다(self):
        self.assertEqual(self.search(*["alpha"] * 9, "zzzz"), [])

    def test_따옴표로_묶은_말은_한_낱말이다(self):
        """묶은 말을 둘로 세면 열 번째 zzzz 가 열한 번째로 밀려 무시된다."""
        self.assertEqual(self.search(*["alpha"] * 8, '"alpha omega"', "zzzz"), [])
        self.assertEqual(self.search(*["alpha"] * 9, '"alpha omega"', '"no such words"'), ["alpha omega"])

    def test_쉼표로_나눈_낱말도_센다(self):
        self.assertEqual(self.terms({"search": ",".join(["alpha"] * 10 + ["zzzz"])}), ["alpha omega"])

    def test_순위_계산도_앞_10낱말만_쓴다(self):
        """제목이 정확히 맞는 항목이 맨 앞이다. 11번째가 phrase 에 붙으면 정확 일치가 깨진다."""
        Word.objects.all().delete()
        title = " ".join(f"w{i}" for i in range(10))
        make_word("aaa " + title)  # 알파벳으로는 앞이지만 앞부분 일치가 아니다
        make_word(title)
        self.assertEqual(self.search(*title.split(), "w0"), [title, "aaa " + title])

    def test_SQL_에_열한_번째부터는_안_실린다(self):
        terms = [f"q{i:03d}x" for i in range(500)]
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(WORDS_URL, {"search": " ".join(terms)})
        self.assertEqual(res.status_code, 200)
        sql = "\n".join(q["sql"] for q in ctx.captured_queries)
        self.assertIn("q009x", sql)
        self.assertNotIn("q010x", sql)

    def test_검수_안_된_항목은_낱말이_몇_개든_안_나온다(self):
        for terms in (["alpha"], ["alpha"] * 10 + ["zzzz"], ["hidden"], ['"alpha hidden"']):
            with self.subTest(terms=terms):
                self.assertNotIn("alpha hidden", self.search(*terms))

    def test_검수_게이트를_끄면_새어_나온다(self):
        """위 테스트가 실제로 게이트를 지키는지. visible() 을 끄면 검수 안 된 항목이 보여야 한다."""
        with mock.patch.object(LearningItemQuerySet, "visible", lambda qs: qs.all()):
            self.assertIn("alpha hidden", self.search("hidden"))

    def test_상한을_끄면_열한_번째도_걸린다(self):
        """상한이 실제로 이 테스트를 지키는지."""
        from .views import CappedSearchFilter

        with mock.patch.object(CappedSearchFilter, "MAX_TERMS", 1000):
            self.assertEqual(self.search(*["alpha"] * 10, "zzzz"), [])
