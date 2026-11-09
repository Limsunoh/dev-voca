"""검색 순위(LearningItemViewSet._rank_by_search)와 단어 quiz 의 kind 검사.

순위 규칙: 제목 정확 일치, 제목 앞부분, 제목에 낱말이 모두 있음, 뜻에 낱말이
모두 있음, 나머지. 같은 순위 안에서는 그 목록의 기본 순서(단어 ABC, 문장 id)를
둔다. ordering 을 고른 요청에는 순위를 걸지 않는다.

기대값은 순서까지 손으로 적었다. 알파벳 순서가 우연히 순위 순서와 같아지지
않도록, 뒤 순위의 항목 이름을 일부러 앞 글자로 지었다(aaa-...).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounts.tests import PASSWORD

from .models import Sentence, Word
from .quiz import QuizKind

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"
WORD_QUIZ_URL = "/api/vocab/words/quiz/"
SENTENCE_QUIZ_URL = "/api/vocab/sentences/quiz/"
BAD_KIND = "그런 문제 유형은 없습니다."


def make_word(term: str, meaning: str = "무관한 뜻", **extra) -> Word:
    fields = {"is_reviewed": True, "description": ""}
    fields.update(extra)
    return Word.objects.create(term=term, meaning=meaning, **fields)


def make_sentence(text: str, translation: str = "무관한 해석", **extra) -> Sentence:
    fields = {"is_reviewed": True}
    fields.update(extra)
    return Sentence.objects.create(text=text, translation=translation, **fields)


class SearchClientMixin:
    """페이지를 끝까지 넘겨 행을 모은다."""

    def rows(self, url: str, params: dict) -> list[dict]:
        out, page = [], 1
        while True:
            res = self.client.get(url, {**params, "page": page})
            self.assertEqual(res.status_code, 200, (params, page, res.content[:200]))
            body = res.json()
            out += body["results"]
            if not body["next"]:
                return out
            page += 1

    def terms(self, params: dict) -> list[str]:
        return [row["term"] for row in self.rows(WORDS_URL, params)]

    def texts(self, params: dict) -> list[str]:
        return [row["text"] for row in self.rows(SENTENCES_URL, params)]


class PostgresOnlyTest(TestCase):
    def test_이_파일은_postgres_에서_돈다(self):
        """순위 SQL 의 대소문자 비교는 DB 마다 달라서 운영과 같은 DB 로 본다."""
        self.assertEqual(connection.vendor, "postgresql")


class WordRankTest(SearchClientMixin, TestCase):
    """단어 순위. "commit" 으로 찾는다."""

    EXPECTED = [
        "commit",  # 0: 제목 정확 일치
        "commit hash",  # 1: 제목 앞부분
        "committer",
        "pre-commit hook",  # 2: 제목 포함
        "precommit",
        "aaa-meaning",  # 3: 뜻 포함
        "zzz-meaning",
        "aaa-desc",  # 4: 설명에만 있음
        "zzz-desc",
    ]

    @classmethod
    def setUpTestData(cls):
        make_word("commit")
        make_word("commit hash")
        make_word("committer")
        make_word("pre-commit hook")
        make_word("precommit")
        make_word("aaa-meaning", "commit 의 뜻")
        make_word("zzz-meaning", "commit 의 뜻")
        make_word("aaa-desc", description="설명에만 commit 이 있다")
        make_word("zzz-desc", description="설명에만 commit 이 있다")
        make_word("stash", "숨기기")

    def test_제목_정확_앞부분_포함_뜻_나머지_순서다(self):
        self.assertEqual(self.terms({"search": "commit"}), self.EXPECTED)

    def test_대소문자가_달라도_순위가_같다(self):
        for query in ("COMMIT", "CoMmIt"):
            with self.subTest(query=query):
                self.assertEqual(self.terms({"search": query}), self.EXPECTED)

    def test_대소문자만_다른_제목은_둘_다_정확_일치다(self):
        make_word("COMMIT")

        got = self.terms({"search": "commit"})

        self.assertEqual(got[:2], ["COMMIT", "commit"])

    def test_앞뒤_공백과_쉼표는_순위에_영향이_없다(self):
        for query in ("  commit  ", "commit,", ",commit", ",commit,"):
            with self.subTest(query=query):
                self.assertEqual(self.terms({"search": query}), self.EXPECTED)

    def test_따옴표로_감싸도_정확_일치가_먼저다(self):
        for query in ('"commit"', "'commit'"):
            with self.subTest(query=query):
                self.assertEqual(self.terms({"search": query}), self.EXPECTED)

    def test_따옴표로_감싼_구는_정확_일치로_본다(self):
        got = self.terms({"search": '"commit hash"'})

        self.assertEqual(got, ["commit hash"])

    def test_같은_요청은_늘_같은_순서다(self):
        first = self.terms({"search": "commit"})

        for _ in range(3):
            self.assertEqual(self.terms({"search": "commit"}), first)

    def test_ordering_을_고르면_순위가_없다(self):
        got = self.terms({"search": "commit", "ordering": "term"})

        self.assertEqual(got, sorted(self.EXPECTED))

    def test_역순_ordering_도_순위가_없다(self):
        got = self.terms({"search": "commit", "ordering": "-term"})

        self.assertEqual(got, sorted(self.EXPECTED, reverse=True))

    def test_난이도_ordering_도_순위가_없다(self):
        Word.objects.filter(term="zzz-desc").update(difficulty=1)
        Word.objects.exclude(term="zzz-desc").update(difficulty=3)

        got = self.terms({"search": "commit", "ordering": "difficulty,term"})

        self.assertEqual(got[0], "zzz-desc")

    def test_빈_ordering_은_고르지_않은_것이라_순위가_걸린다(self):
        self.assertEqual(self.terms({"search": "commit", "ordering": ""}), self.EXPECTED)

    def test_검색어가_아닌_값은_순위가_없고_ABC순이다(self):
        expected = sorted([*self.EXPECTED, "stash"])
        for query in ("", "   ", ",", ",,,"):
            with self.subTest(query=query):
                self.assertEqual(self.terms({"search": query}), expected)

    def test_shuffle_과_같이_오면_순위가_먼저다(self):
        first = self.terms({"search": "commit", "shuffle": "seed-a"})

        self.assertEqual(first[0], "commit")
        self.assertEqual(set(first[1:3]), {"commit hash", "committer"})
        self.assertEqual(set(first[-2:]), {"aaa-desc", "zzz-desc"})
        self.assertEqual(self.terms({"search": "commit", "shuffle": "seed-a"}), first)

    def test_검색없는_목록은_ABC순_그대로다(self):
        self.assertEqual(self.terms({}), sorted([*self.EXPECTED, "stash"]))

    def test_count_는_걸린_개수와_같다(self):
        body = self.client.get(WORDS_URL, {"search": "commit"}).json()

        self.assertEqual(body["count"], len(self.EXPECTED))

    def test_상세에_search_를_붙여도_500이_아니다(self):
        """상세도 filter_queryset 을 지난다."""
        pk = Word.objects.get(term="commit").pk

        self.assertEqual(
            self.client.get(f"{WORDS_URL}{pk}/", {"search": "commit"}).status_code, 200
        )
        self.assertEqual(
            self.client.get(f"{WORDS_URL}{pk}/", {"search": "없는말"}).status_code, 404
        )


class WordMultiTermTest(SearchClientMixin, TestCase):
    """여러 낱말. SearchFilter 는 낱말마다 어느 칸이든 걸리면 통과시킨다."""

    @classmethod
    def setUpTestData(cls):
        make_word("merge commit")
        make_word("commit merge")
        make_word("merge commit strategy")
        make_word("aaa", "merge 와 commit 을 합친 뜻")
        make_word("merge", "commit 을 합친다")
        make_word("bbb", description="merge commit 설명")

    def test_낱말_순서대로면_정확_일치와_앞부분이_먼저다(self):
        self.assertEqual(
            self.terms({"search": "merge commit"}),
            ["merge commit", "merge commit strategy", "commit merge", "aaa", "bbb", "merge"],
        )

    def test_쉼표로_나눠도_띄어쓰기와_같다(self):
        self.assertEqual(
            self.terms({"search": "merge,commit"}),
            self.terms({"search": "merge commit"}),
        )

    def test_낱말_순서가_다르면_제목_포함으로_본다(self):
        got = self.terms({"search": "commit merge"})

        self.assertEqual(got[:1], ["commit merge"])
        self.assertEqual(got[1:3], ["merge commit", "merge commit strategy"])

    def test_따옴표_구와_낱말을_섞어도_된다(self):
        got = self.terms({"search": '"merge commit" strategy'})

        self.assertEqual(got, ["merge commit strategy"])


class SpecialCharacterTest(SearchClientMixin, TestCase):
    """LIKE 의 와일드카드가 순위에서 글자 그대로 쓰이는지 본다."""

    @classmethod
    def setUpTestData(cls):
        make_word("100%")
        make_word("100x")
        make_word("a_b")
        make_word("axb")
        make_word("back\\slash")
        make_word("backxslash")
        make_word("it's")

    def test_퍼센트는_글자다(self):
        self.assertEqual(self.terms({"search": "100%"}), ["100%"])

    def test_밑줄은_글자다(self):
        self.assertEqual(self.terms({"search": "a_b"}), ["a_b"])

    def test_역슬래시는_글자다(self):
        self.assertEqual(self.terms({"search": "back\\slash"}), ["back\\slash"])

    def test_작은따옴표가_낀_낱말도_정확_일치다(self):
        self.assertEqual(self.terms({"search": "it's"}), ["it's"])

    def test_이상한_검색어에도_500이_아니다(self):
        for query in ("%", "_", "'", '"', "\\", '"\\"', "\x00", "a" * 5000, "\u3000"):
            with self.subTest(query=query[:20]):
                res = self.client.get(WORDS_URL, {"search": query})
                self.assertLess(res.status_code, 500)


class WordPagingTest(SearchClientMixin, TestCase):
    """같은 순위가 쪽을 넘어갈 때."""

    @classmethod
    def setUpTestData(cls):
        # 앞부분 일치 7개와 포함 38개. 쪽(20개) 경계가 같은 순위 안에 걸린다.
        for n in range(7):
            make_word(f"zeta {n:02d}")
        for n in range(38):
            make_word(f"a-zeta {n:02d}")

    def test_쪽을_넘겨도_빠짐_겹침이_없고_순서가_맞다(self):
        got = self.terms({"search": "zeta"})

        self.assertEqual(
            got,
            [f"zeta {n:02d}" for n in range(7)] + [f"a-zeta {n:02d}" for n in range(38)],
        )
        self.assertEqual(len(got), len(set(got)))

    def test_같은_쪽을_다시_받아도_같다(self):
        params = {"search": "zeta", "page": 2}

        first = self.client.get(WORDS_URL, params).json()["results"]

        self.assertEqual(self.client.get(WORDS_URL, params).json()["results"], first)

    def test_쪽_번호_경계는_404이고_500이_아니다(self):
        for page in ("0", "-1", "abc", "9" * 30, "999999"):
            with self.subTest(page=page):
                res = self.client.get(WORDS_URL, {"search": "zeta", "page": page})
                self.assertEqual(res.status_code, 404)


class SentenceRankTest(SearchClientMixin, TestCase):
    """문장 순위. 같은 순위 안에서는 id 순이다."""

    @classmethod
    def setUpTestData(cls):
        # id 순서가 순위와 정반대가 되도록 뒤 순위부터 만든다.
        make_sentence("desc only", description="설명에만 deploy 가 있다")
        make_sentence("context only", context="deploy 할 때")
        make_sentence("zzz meaning", "deploy 를 끝냈다")
        make_sentence("aaa meaning", "deploy 를 시작했다")
        make_sentence("we deploy on friday")
        make_sentence("deploy failed")
        make_sentence("deploy it")
        make_sentence("deploy")
        make_sentence("no match")

    EXPECTED = [
        "deploy",
        "deploy failed",
        "deploy it",
        "we deploy on friday",
        "zzz meaning",
        "aaa meaning",
        "desc only",
        "context only",
    ]

    def test_본문_정확_앞부분_포함_해석_나머지_순서다(self):
        self.assertEqual(self.texts({"search": "deploy"}), self.EXPECTED)

    def test_ordering_을_고르면_순위가_없다(self):
        rows = self.rows(SENTENCES_URL, {"search": "deploy", "ordering": "-id"})
        ids = [row["id"] for row in rows]

        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_검색이_없으면_id_순이다(self):
        ids = [row["id"] for row in self.rows(SENTENCES_URL, {})]

        self.assertEqual(ids, sorted(ids))

    def test_여러_낱말과_따옴표(self):
        self.assertEqual(self.texts({"search": "deploy,failed"}), ["deploy failed"])
        self.assertEqual(self.texts({"search": '"deploy failed"'}), ["deploy failed"])


class SentencePagingTest(SearchClientMixin, TestCase):
    def test_본문이_같은_문장이_많아도_쪽을_넘겨_겹치지_않는다(self):
        """text 는 유일하지 않다. 순위가 같으면 id 가 순서를 정해야 한다."""
        made = [make_sentence("same text").pk for _ in range(45)]

        got = [row["id"] for row in self.rows(SENTENCES_URL, {"search": "same text"})]

        self.assertEqual(got, made)


class ReviewGateTest(SearchClientMixin, TestCase):
    """순위의 어느 칸에 걸려도 미검수는 일반 사용자에게 나가지 않는다."""

    HIDDEN_WORDS = ("commit", "commit hidden", "hidden commit", "h1", "h2")
    HIDDEN_TEXTS = ("deploy", "deploy hidden", "hidden deploy", "s1", "s2")

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.normal = user_model.objects.create_user(
            email="rank-normal@example.com", password=PASSWORD
        )
        cls.staff = user_model.objects.create_user(
            email="rank-staff@example.com", password=PASSWORD, is_staff=True
        )

        make_word("Commit", is_reviewed=True)
        make_word("commit log", is_reviewed=True)
        make_word("commit", is_reviewed=False)
        make_word("commit hidden", is_reviewed=False)
        make_word("hidden commit", is_reviewed=False)
        make_word("h1", "commit 뜻", is_reviewed=False)
        make_word("h2", description="commit 설명", is_reviewed=False)

        make_sentence("Deploy", is_reviewed=True)
        make_sentence("deploy", is_reviewed=False)
        make_sentence("deploy hidden", is_reviewed=False)
        make_sentence("hidden deploy", is_reviewed=False)
        make_sentence("s1", "deploy 해석", is_reviewed=False)
        make_sentence("s2", description="deploy 설명", is_reviewed=False)

    PARAM_SETS = (
        {},
        {"ordering": "term"},
        {"ordering": "-created_at"},
        {"shuffle": "seed"},
    )

    def assert_no_hidden(self) -> None:
        for extra in self.PARAM_SETS:
            with self.subTest(extra=extra):
                words = self.rows(WORDS_URL, {"search": "commit", **extra})
                self.assertEqual(
                    sorted(r["term"] for r in words), ["Commit", "commit log"]
                )
                body = self.client.get(WORDS_URL, {"search": "commit", **extra}).json()
                self.assertEqual(body["count"], 2)

        for extra in ({}, {"ordering": "-id"}, {"shuffle": "seed"}):
            with self.subTest(extra=extra):
                texts = self.texts({"search": "deploy", **extra})
                self.assertEqual(texts, ["Deploy"])

    def test_익명은_어느_순위로도_미검수를_못_본다(self):
        self.assert_no_hidden()

    def test_일반_로그인_사용자도_못_본다(self):
        self.client.force_login(self.normal)

        self.assert_no_hidden()

    def test_미검수_상세는_search_가_붙어도_404다(self):
        word = Word.objects.get(term="commit")
        sentence = Sentence.objects.get(text="deploy")

        self.assertEqual(
            self.client.get(f"{WORDS_URL}{word.pk}/", {"search": "commit"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"{SENTENCES_URL}{sentence.pk}/", {"search": "deploy"}).status_code,
            404,
        )

    def test_검수자는_대기가_앞이고_각_묶음_안은_순위순이다(self):
        self.client.force_login(self.staff)

        got = self.terms({"search": "commit"})

        self.assertEqual(
            got,
            ["commit", "commit hidden", "hidden commit", "h1", "h2", "Commit", "commit log"],
        )

    def test_검수자가_ordering_을_고르면_대기만_앞이고_순위는_없다(self):
        self.client.force_login(self.staff)

        got = self.terms({"search": "commit", "ordering": "term"})

        self.assertEqual(
            got,
            ["commit", "commit hidden", "h1", "h2", "hidden commit", "Commit", "commit log"],
        )

    def test_검수자의_문장_검색도_대기가_앞이고_순위순이다(self):
        self.client.force_login(self.staff)

        self.assertEqual(
            self.texts({"search": "deploy"}),
            ["deploy", "deploy hidden", "hidden deploy", "s1", "s2", "Deploy"],
        )


class ScreenSortStringsTest(SearchClientMixin, TestCase):
    """화면 정렬 표(WORD_SORTS, SENTENCE_SORTS)의 ordering 을 백엔드가 받는다."""

    @classmethod
    def setUpTestData(cls):
        make_word("zeta", difficulty=1)
        make_word("alpha", difficulty=3)
        make_word("mid", difficulty=2)
        # 윈도의 시계는 같은 시각을 낼 수 있어서 만든 시각을 직접 적는다.
        start = timezone.now()
        for minutes, term in enumerate(("zeta", "alpha", "mid")):
            Word.objects.filter(term=term).update(
                created_at=start + timedelta(minutes=minutes)
            )
        for n, level in enumerate((1, 3, 2)):
            make_sentence(f"sent {n}", difficulty=level)

    def test_단어_어려운_것부터(self):
        self.assertEqual(
            self.terms({"ordering": "-difficulty,term"}), ["alpha", "mid", "zeta"]
        )

    def test_단어_최근_추가순(self):
        self.assertEqual(
            self.terms({"ordering": "-created_at,term"}), ["mid", "alpha", "zeta"]
        )

    def test_문장_어려운_것부터(self):
        self.assertEqual(
            self.texts({"ordering": "-difficulty,id"}), ["sent 1", "sent 2", "sent 0"]
        )

    def test_문장_최근_추가순(self):
        self.assertEqual(
            self.texts({"ordering": "-created_at,-id"}), ["sent 2", "sent 1", "sent 0"]
        )


class WordQuizKindTest(TestCase):
    """단어 quiz 의 kind. 모르는 값은 문장 쪽과 같은 400 이다."""

    @classmethod
    def setUpTestData(cls):
        cls.words = [
            make_word(f"word{n}", f"뜻{n}", description=f"word{n} 를 설명한다", category="git")
            for n in range(6)
        ]
        cls.hidden = make_word("hidden", "숨김", is_reviewed=False, category="git")

    def get(self, **params):
        return self.client.get(WORD_QUIZ_URL, params)

    def assert_bad_kind(self, res) -> None:
        self.assertEqual(res.status_code, 400, res.content[:200])
        self.assertEqual(res.json()["detail"], BAD_KIND)

    def test_맞는_값은_그_유형으로_낸다(self):
        for kind in QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                res = self.get(kind=kind)
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["kind"], kind)

    def test_없거나_빈_값은_무작위_단어_유형이다(self):
        for params in ({}, {"kind": ""}):
            with self.subTest(params=params):
                res = self.get(**params)
                self.assertEqual(res.status_code, 200)
                self.assertIn(res.json()["kind"], QuizKind.WORD_KINDS)

    def test_틀린_값은_400이다(self):
        cases = (
            "foo",
            "MEANING",
            " meaning",
            "meaning ",
            "meaning,term",
            "['meaning']",
            "blank",
            "situation",
            "nonsense",
            "9" * 100,
            " ",
            "\x00",
        )
        for kind in cases:
            with self.subTest(kind=kind[:20]):
                self.assert_bad_kind(self.get(kind=kind))

    def test_kind_가_여럿이면_마지막_값을_검사한다(self):
        self.assert_bad_kind(self.client.get(f"{WORD_QUIZ_URL}?kind=meaning&kind=blank"))
        res = self.client.get(f"{WORD_QUIZ_URL}?kind=blank&kind=meaning")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["kind"], "meaning")

    def test_item_과_맞는_값이면_그_단어로_낸다(self):
        word = self.words[2]
        for kind in QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                res = self.get(item=word.pk, kind=kind)
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.json()["kind"], kind)
                graded = self.client.post(
                    "/api/vocab/words/grade/",
                    {"token": res.json()["token"], "picked": -1},
                    content_type="application/json",
                )
                self.assertEqual(graded.json()["answer_id"], word.pk)

    def test_item_과_틀린_값이면_400이다(self):
        self.assert_bad_kind(self.get(item=self.words[0].pk, kind="blank"))

    def test_미검수_item_에_틀린_값이어도_같은_400이다(self):
        """item 을 보기 전에 kind 를 막는다. 미검수 여부가 응답으로 갈리지 않는다."""
        visible = self.get(item=self.words[0].pk, kind="foo")
        hidden = self.get(item=self.hidden.pk, kind="foo")

        self.assertEqual(visible.status_code, hidden.status_code)
        self.assertEqual(visible.json(), hidden.json())

    def test_없는_item_에_맞는_값이면_400이_아니라_404다(self):
        res = self.get(item=999999, kind="meaning")

        self.assertEqual(res.status_code, 404)

    def test_분류와_틀린_값이면_400이다(self):
        self.assert_bad_kind(self.get(category="git", kind="foo"))

    def test_문제가_모자라도_틀린_값이면_400이다(self):
        Word.objects.all().delete()

        self.assert_bad_kind(self.get(kind="foo"))

    def test_단어_유형은_문장_quiz_에서_여전히_400이다(self):
        for kind in QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                res = self.client.get(SENTENCE_QUIZ_URL, {"kind": kind})
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["detail"], BAD_KIND)
