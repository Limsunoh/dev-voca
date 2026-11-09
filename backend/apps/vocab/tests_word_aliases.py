"""단어의 검색 전용 표기(Word.aliases)를 경계로 본다.

표기 항목과 통째로 맞으면 0, 항목 앞부분이면 1, 낱말 첫머리에 모든 낱말이
있으면 2, 그 다음이 뜻(3), 나머지(4)다. 표기는 목록 응답에만 나가고 문제·채점·
상세에는 없어야 한다.

순위가 ABC 순서와 우연히 겹치지 않도록, 뒤 순위 항목 이름을 앞 글자로 지었다.
"""

from io import StringIO
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests import PASSWORD
from apps.learning.views import StudyCardSerializer

from .management.commands import seed_word_aliases
from .models import Word
from .quiz import QuizKind
from .serializers import QuizWordSerializer, WordDetailSerializer
from .tests_search_rank import (
    SENTENCES_URL,
    WORD_QUIZ_URL,
    WORDS_URL,
    SearchClientMixin,
    make_sentence,
    make_word,
)

GRADE_URL = "/api/vocab/words/grade/"
ROUND_URL = "/api/learning/rounds/"
SEED_ALIASES = "apps.vocab.management.commands.seed_word_aliases.ALIASES"


class AliasRankTest(SearchClientMixin, TestCase):
    """한글 표기로 찾을 때의 순위. "커밋" 으로 찾는다."""

    EXPECTED = [
        "yyy-exact-second",  # 0: 뒤 항목 전체
        "zzz-exact",  # 0: 첫 항목 전체
        "www-prefix-second",  # 1: 뒤 항목 앞부분
        "xxx-prefix",  # 1: 항목 앞부분
        "vvv-word-start",  # 2: 공백 뒤 낱말 첫머리
        "bbb-meaning",  # 3: 뜻
        "aaa-desc",  # 4: 설명
        "aaa-middle",  # 4: 항목 가운데
    ]

    @classmethod
    def setUpTestData(cls):
        make_word("zzz-exact", aliases="커밋, 커미트")
        make_word("yyy-exact-second", aliases="커미트, 커밋")
        make_word("xxx-prefix", aliases="커밋메시지")
        make_word("www-prefix-second", aliases="깃, 커밋메시지")
        make_word("vvv-word-start", aliases="깃 커밋 훅")
        make_word("bbb-meaning", "커밋 의 뜻")
        make_word("aaa-desc", description="설명에만 커밋 이 있다")
        make_word("aaa-middle", aliases="리커밋")
        make_word("unrelated", aliases="머지")

    def test_표기_항목_앞부분_낱말첫머리_뜻_나머지_순서다(self):
        self.assertEqual(self.terms({"search": "커밋"}), self.EXPECTED)

    def test_표기가_뜻보다_앞선다(self):
        make_word("aaa-first-meaning", "커밋")

        got = self.terms({"search": "커밋"})

        self.assertLess(got.index("zzz-exact"), got.index("aaa-first-meaning"))

    def test_제목_일치와_표기_일치는_같은_순위로_ABC순이다(self):
        make_word("커밋")

        self.assertEqual(
            self.terms({"search": "커밋"})[:3], ["yyy-exact-second", "zzz-exact", "커밋"]
        )

    def test_count_는_걸린_개수와_같다(self):
        body = self.client.get(WORDS_URL, {"search": "커밋"}).json()

        self.assertEqual(body["count"], len(self.EXPECTED))

    def test_영문_표기는_대소문자를_가리지_않는다(self):
        make_word("zz-case", aliases="GitHub, 깃허브")

        for query in ("github", "GITHUB", "GitHub"):
            with self.subTest(query=query):
                self.assertEqual(self.terms({"search": query}), ["zz-case"])

    def test_공백이_든_표기_항목도_통째로_맞으면_0이다(self):
        make_word("zz-spaced", aliases="오토 인크리먼트, 오토인크리먼트")
        make_word("aa-meaning", "오토 인크리먼트 뜻")

        for query in ("오토 인크리먼트", "오토  인크리먼트", '"오토 인크리먼트"'):
            with self.subTest(query=query):
                self.assertEqual(
                    self.terms({"search": query}), ["zz-spaced", "aa-meaning"]
                )

    def test_쉼표만으로_이어도_항목으로_본다(self):
        make_word("zz-nospace", aliases="머지리퀘스트,엠알")
        make_word("aa-meaning", "엠알 뜻")

        self.assertEqual(self.terms({"search": "엠알"}), ["zz-nospace", "aa-meaning"])


class AliasWordStartTest(SearchClientMixin, TestCase):
    """낱말 첫머리만 친다. 항목 가운데에 걸린 것이 뜻 일치보다 앞서면 안 된다."""

    @classmethod
    def setUpTestData(cls):
        make_word("aaa-programming", aliases="프로그래밍")
        make_word("bbb-rog-end", aliases="블로그")
        make_word("ccc-meaning", "로그 를 남긴다")
        make_word("ddd-log", aliases="로그")
        make_word("eee-start", aliases="웹 로그 수집")

    def test_로그가_프로그래밍_표기에_걸려_뜻보다_앞서지_않는다(self):
        self.assertEqual(
            self.terms({"search": "로그"}),
            ["ddd-log", "eee-start", "ccc-meaning", "aaa-programming", "bbb-rog-end"],
        )

    def test_가운데에_걸린_표기도_검색_결과에는_남는다(self):
        """순위만 뒤로 간다. SearchFilter 는 칸 전체에서 찾는다."""
        self.assertIn("aaa-programming", self.terms({"search": "그래"}))


class AliasBoundaryTest(SearchClientMixin, TestCase):
    """항목 경계를 넘는 값은 전체 일치가 아니다."""

    def test_쉼표로_나눈_두_낱말은_항목_하나로_치지_않는다(self):
        """"커밋,커미트" 는 낱말 둘이다. 표기 전체와 맞아도 0 이 아니라 2 다."""
        make_word("aaa-two-items", aliases="커밋, 커미트")
        make_word("zzz-one-item", aliases="커밋 커미트")

        for query in ("커밋,커미트", "커밋 커미트"):
            with self.subTest(query=query):
                self.assertEqual(
                    self.terms({"search": query}), ["zzz-one-item", "aaa-two-items"]
                )

    def test_항목을_이어_붙인_값은_걸리지_않는다(self):
        make_word("aaa", aliases="커밋, 커미트")

        self.assertEqual(self.terms({"search": "커밋커미트"}), [])

    def test_항목_끝과_다음_항목_첫머리를_잇는_낱말은_뒤로_간다(self):
        make_word("aaa-cross", aliases="커밋, 커미트")
        make_word("zzz-meaning", "밋 커 뜻")

        self.assertEqual(self.terms({"search": "밋, 커"}), ["zzz-meaning", "aaa-cross"])

    def test_따옴표_안의_쉼표_공백은_저장값_전체와_일치로_치지_않는다(self):
        make_word("커밋, 커미트")  # 제목이 글자 그대로 같으니 이것만 0 이다.
        make_word("aaa-alias", aliases="커밋, 커미트")

        self.assertEqual(
            self.terms({"search": '"커밋, 커미트"'}), ["커밋, 커미트", "aaa-alias"]
        )

    def test_따옴표로_감싼_쉼표는_표기_항목을_넘어_맞지_않는다(self):
        make_word("aaa-two-items", aliases="커밋, 커미트", description="커밋,커미트")
        make_word("zzz-meaning", "커밋,커미트 뜻")

        self.assertEqual(
            self.terms({"search": '"커밋,커미트"'}), ["zzz-meaning", "aaa-two-items"]
        )

    def test_쉼표만_찾아도_표기가_빈_단어를_올리지_않는다(self):
        make_word("aaa-desc", description="쉼표, 가 있는 설명")
        make_word("zzz,title")

        self.assertEqual(self.terms({"search": '","'}), ["zzz,title", "aaa-desc"])

    def test_한_낱말이_표기에_없으면_낱말첫머리_순위가_아니다(self):
        make_word("aaa-one-word", aliases="커밋", description="훅 설명")
        make_word("zzz-both", aliases="훅 커밋")

        self.assertEqual(self.terms({"search": "커밋 훅"}), ["zzz-both", "aaa-one-word"])


class AliasSpecialCharacterTest(SearchClientMixin, TestCase):
    """LIKE 와일드카드는 표기 안에서도 글자 그대로다."""

    @classmethod
    def setUpTestData(cls):
        make_word("zz-percent", aliases="백%, 퍼센트")
        make_word("zy-under", aliases="가_나")
        make_word("zx-back", aliases="가\\나")
        make_word("aa-other", aliases="백분율, 가다나, 가x나")

    def test_퍼센트는_글자다(self):
        self.assertEqual(self.terms({"search": "백%"}), ["zz-percent"])

    def test_밑줄은_글자다(self):
        self.assertEqual(self.terms({"search": "가_나"}), ["zy-under"])

    def test_역슬래시는_글자다(self):
        self.assertEqual(self.terms({"search": "가\\나"}), ["zx-back"])

    def test_와일드카드만으로는_모든_행을_못_끌어온다(self):
        self.assertEqual(self.terms({"search": "%"}), ["zz-percent"])
        self.assertEqual(self.terms({"search": "_"}), ["zy-under"])

    def test_이상한_검색어에도_500이_아니다(self):
        queries = (
            ",",
            '","',
            "','",
            ",,,",
            '"',
            "'",
            "\\",
            '"\\"',
            "%,_",
            "　",
            "커" * 5000,
        )
        for query in queries:
            with self.subTest(query=query[:20]):
                self.assertLess(self.client.get(WORDS_URL, {"search": query}).status_code, 500)

    @skipUnless(connection.vendor == "postgresql", "SQLite 는 LIKE 길이와 식 크기에 한도가 있다")
    def test_아주_긴_검색어에도_500이_아니다(self):
        for query in ("a" * 100000, " ".join(["커"] * 2000), ",".join(["가"] * 2000)):
            with self.subTest(query=query[:20]):
                self.assertLess(self.client.get(WORDS_URL, {"search": query}).status_code, 500)

    def test_널_문자는_400이다(self):
        for query in ("\x00", "커\x00밋", '"\x00"'):
            with self.subTest(query=query):
                res = self.client.get(WORDS_URL, {"search": query})
                self.assertEqual(res.status_code, 400)

    def test_깨진_인코딩도_500이_아니다(self):
        res = self.client.get(f"{WORDS_URL}?search=%ED%A0%80%FF")

        self.assertLess(res.status_code, 500)


class EmptySearchTest(SearchClientMixin, TestCase):
    """빈 검색어에는 순위가 없다. 표기가 빈 행의 ",," 에 걸리면 안 된다."""

    @classmethod
    def setUpTestData(cls):
        make_word("charlie", aliases="찰리")
        make_word("bravo")
        make_word("alpha", aliases="알파")

    def test_빈_값들은_ABC순이다(self):
        for query in ("", " ", '""', "''", '"" ""', ",", ",,"):
            with self.subTest(query=query):
                self.assertEqual(
                    self.terms({"search": query}), ["alpha", "bravo", "charlie"]
                )

    def test_빈_따옴표와_shuffle_이면_shuffle_순서_그대로다(self):
        self.assertEqual(
            self.terms({"search": '""', "shuffle": "seed-a"}),
            self.terms({"shuffle": "seed-a"}),
        )

    def test_문장도_빈_따옴표는_id_순이다(self):
        made = [make_sentence("b sentence").pk, make_sentence("a sentence").pk]

        got = [row["id"] for row in self.rows(SENTENCES_URL, {"search": '""'})]

        self.assertEqual(got, made)


class AliasReviewGateTest(SearchClientMixin, TestCase):
    """미검수 단어는 표기로도 찾히지 않는다."""

    PARAM_SETS = (
        {},
        {"ordering": "term"},
        {"ordering": "-created_at"},
        {"shuffle": "seed"},
        {"category": "git"},
    )

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.normal = user_model.objects.create_user(
            email="alias-normal@example.com", password=PASSWORD
        )
        cls.staff = user_model.objects.create_user(
            email="alias-staff@example.com", password=PASSWORD, is_staff=True
        )
        cls.hidden_exact = make_word(
            "hidden-exact", aliases="커밋, 숨김표기", is_reviewed=False, category="git"
        )
        make_word("hidden-prefix", aliases="커밋메시지", is_reviewed=False, category="git")
        make_word("hidden-start", aliases="깃 커밋", is_reviewed=False, category="git")
        make_word("visible", aliases="커밋", category="git")
        make_word("visible-low", "커밋 뜻", category="git")

    def assert_no_hidden(self) -> None:
        for extra in self.PARAM_SETS:
            with self.subTest(extra=extra):
                rows = self.rows(WORDS_URL, {"search": "커밋", **extra})
                self.assertEqual(sorted(r["term"] for r in rows), ["visible", "visible-low"])
                body = self.client.get(WORDS_URL, {"search": "커밋", **extra}).json()
                self.assertEqual(body["count"], 2)
        self.assertEqual(self.terms({"search": "숨김표기"}), [])

    def test_익명은_표기로_미검수를_못_찾는다(self):
        self.assert_no_hidden()

    def test_일반_사용자도_못_찾는다(self):
        self.client.force_login(self.normal)

        self.assert_no_hidden()

    def test_미검수_상세는_표기_search_가_붙어도_404다(self):
        res = self.client.get(f"{WORDS_URL}{self.hidden_exact.pk}/", {"search": "숨김표기"})

        self.assertEqual(res.status_code, 404)

    def test_검수자는_대기가_앞이고_각_묶음_안은_순위순이다(self):
        self.client.force_login(self.staff)

        self.assertEqual(
            self.terms({"search": "커밋"}),
            ["hidden-exact", "hidden-prefix", "hidden-start", "visible", "visible-low"],
        )

    def test_검수자가_ordering_을_고르면_대기만_앞이고_순위는_없다(self):
        self.client.force_login(self.staff)

        self.assertEqual(
            self.terms({"search": "커밋", "ordering": "-term"}),
            ["hidden-start", "hidden-prefix", "hidden-exact", "visible-low", "visible"],
        )


class AliasCombinationTest(SearchClientMixin, TestCase):
    """ordering·shuffle·필터·쪽 넘김과 함께 쓸 때."""

    EXACT = [f"zeta {n:02d}" for n in range(25)]
    MEANING = [f"alpha {n:02d}" for n in range(25)]

    @classmethod
    def setUpTestData(cls):
        for term in cls.EXACT:
            make_word(term, aliases="제타, 지타", category="git", difficulty=2)
        for term in cls.MEANING:
            make_word(term, "제타 의 뜻", category="api", difficulty=1)

    def test_ordering_을_고르면_표기_순위가_없다(self):
        self.assertEqual(
            self.terms({"search": "제타", "ordering": "term"}), self.MEANING + self.EXACT
        )

    def test_빈_ordering_은_순위가_걸린다(self):
        self.assertEqual(
            self.terms({"search": "제타", "ordering": ""}), self.EXACT + self.MEANING
        )

    def test_쪽을_넘겨도_빠짐_겹침이_없고_순위가_맞다(self):
        got = self.terms({"search": "제타"})

        self.assertEqual(got, self.EXACT + self.MEANING)

    def test_shuffle_은_같은_순위_안에서만_섞는다(self):
        got = self.terms({"search": "제타", "shuffle": "seed-a"})

        self.assertEqual(set(got[:25]), set(self.EXACT))
        self.assertEqual(set(got[25:]), set(self.MEANING))
        self.assertNotEqual(got[:25], self.EXACT)
        self.assertEqual(self.terms({"search": "제타", "shuffle": "seed-a"}), got)

    def test_shuffle_과_ordering_이_같이_오면_ordering_이다(self):
        self.assertEqual(
            self.terms({"search": "제타", "shuffle": "seed-a", "ordering": "term"}),
            self.MEANING + self.EXACT,
        )

    def test_분류_필터와_같이_쓴다(self):
        self.assertEqual(self.terms({"search": "제타", "category": "api"}), self.MEANING)

    def test_난이도_ordering_과_같이_쓴다(self):
        got = self.terms({"search": "제타", "ordering": "difficulty,term"})

        self.assertEqual(got, self.MEANING + self.EXACT)

    def test_쪽_번호_경계는_404이고_500이_아니다(self):
        for page in ("0", "-1", "abc", "9" * 30, "999999"):
            with self.subTest(page=page):
                res = self.client.get(WORDS_URL, {"search": "제타", "page": page})
                self.assertEqual(res.status_code, 404)

    def test_page_size_를_크게_줘도_한_쪽_크기가_늘지_않는다(self):
        res = self.client.get(WORDS_URL, {"search": "제타", "page_size": 100000})

        self.assertEqual(res.status_code, 200)
        self.assertLess(len(res.json()["results"]), 50)

    def test_상세에_표기_search_를_붙이면_걸릴_때만_200이다(self):
        pk = Word.objects.get(term="zeta 00").pk

        self.assertEqual(self.client.get(f"{WORDS_URL}{pk}/", {"search": "지타"}).status_code, 200)
        self.assertEqual(self.client.get(f"{WORDS_URL}{pk}/", {"search": "없는말"}).status_code, 404)


class AliasExposureTest(TestCase):
    """표기는 목록에만 나간다. 문제에 나가면 소리 표기가 정답 힌트가 된다."""

    MARK = "표식별칭"

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            email="alias-expo-staff@example.com", password=PASSWORD, is_staff=True
        )
        cls.user = get_user_model().objects.create_user(
            email="alias-expo@example.com", password=PASSWORD
        )
        Word.objects.bulk_create(
            Word(
                term=f"word{n}",
                meaning=f"뜻{n}",
                description=f"word{n} 를 설명한다",
                category="git",
                aliases=cls.MARK,
                is_reviewed=True,
            )
            for n in range(60)
        )
        cls.word = Word.objects.get(term="word0")

    def assert_clean(self, res) -> None:
        self.assertEqual(res.status_code, 200, res.content[:200])
        self.assertNotIn(self.MARK, res.content.decode())
        self.assertNotIn("aliases", res.content.decode())

    def test_목록에는_있다(self):
        """표식이 보이는 응답이 있어야 아래 테스트들이 뜻을 갖는다."""
        res = self.client.get(WORDS_URL, {"search": "word0"})

        self.assertEqual(res.json()["results"][0]["aliases"], self.MARK)

    def test_문제에_없다(self):
        for kind in QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                self.assert_clean(self.client.get(WORD_QUIZ_URL, {"kind": kind}))

    def test_낱개_문제에_없다(self):
        for kind in QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                self.assert_clean(
                    self.client.get(WORD_QUIZ_URL, {"kind": kind, "item": self.word.pk})
                )

    def test_채점_응답에_없다(self):
        question = self.client.get(WORD_QUIZ_URL, {"kind": "meaning"}).json()

        res = self.client.post(
            GRADE_URL,
            {"token": question["token"], "picked": -1},
            content_type="application/json",
        )

        self.assert_clean(res)

    def test_상세에_없다(self):
        self.assert_clean(self.client.get(f"{WORDS_URL}{self.word.pk}/"))

    def test_검수자_상세에도_없다(self):
        self.client.force_login(self.staff)

        self.assert_clean(self.client.get(f"{WORDS_URL}{self.word.pk}/"))

    def test_한_판_시작_응답에_없다(self):
        self.client.force_login(self.user)

        res = self.client.post(ROUND_URL, {}, content_type="application/json")

        self.assertLess(res.status_code, 300, res.content[:200])
        self.assertNotIn(self.MARK, res.content.decode())

    def test_문제_계열_직렬화_칸에_없다(self):
        for serializer in (QuizWordSerializer, StudyCardSerializer, WordDetailSerializer):
            with self.subTest(serializer=serializer.__name__):
                self.assertNotIn("aliases", serializer.Meta.fields)

    def test_검수자_PATCH_로_표기를_못_고친다(self):
        self.client.force_login(self.staff)

        res = self.client.patch(
            f"{WORDS_URL}{self.word.pk}/",
            {"aliases": "바뀐값"},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.word.refresh_from_db()
        self.assertEqual(self.word.aliases, self.MARK)


class SentenceUntouchedTest(SearchClientMixin, TestCase):
    """문장 목록에는 표기 칸이 없다. 순위와 응답이 예전 그대로다."""

    @classmethod
    def setUpTestData(cls):
        make_sentence("zz only deploy")
        make_sentence("deploy, 배포")
        make_sentence("배포 시작")
        make_sentence("aa", "배포 의 뜻")

    def test_쉼표_항목으로_쪼개_보지_않는다(self):
        """문장 본문의 쉼표 뒤 낱말을 표기 항목처럼 올리면 안 된다."""
        self.assertEqual(self.texts({"search": "배포"}), ["배포 시작", "deploy, 배포", "aa"])

    def test_문장_목록에는_aliases_가_없다(self):
        row = self.client.get(SENTENCES_URL, {"search": "배포"}).json()["results"][0]

        self.assertNotIn("aliases", row)


class AliasFieldTest(TestCase):
    def test_200자까지_받는다(self):
        make_word("max", aliases="가" * 200).full_clean()

    def test_201자는_검증에서_막힌다(self):
        word = Word(term="over", meaning="뜻", aliases="가" * 201)

        with self.assertRaises(ValidationError) as caught:
            word.full_clean()

        self.assertIn("aliases", caught.exception.message_dict)

    def test_비워_둘_수_있다(self):
        Word(term="blank", meaning="뜻", aliases="").full_clean()

    def test_마이그레이션이_모델과_맞다(self):
        out = StringIO()

        call_command("makemigrations", "vocab", "--check", "--dry-run", stdout=out)


class AliasAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            email="alias-admin@example.com", password=PASSWORD
        )
        cls.word = make_word("commit", aliases="커밋, 커미트")
        make_word("merge", aliases="머지")

    def setUp(self):
        self.client.force_login(self.admin)

    def test_검색으로_표기를_찾는다(self):
        res = self.client.get(reverse("admin:vocab_word_changelist"), {"q": "커미트"})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["cl"].result_count, 1)

    def test_편집_화면에_표기_칸이_있다(self):
        res = self.client.get(reverse("admin:vocab_word_change", args=[self.word.pk]))

        self.assertContains(res, 'name="aliases"')


class SeedWordAliasesTest(TestCase):
    """seed_word_aliases 는 빈 칸만 채운다."""

    TABLE = {"commit": "커밋, 커미트", "merge": "머지", "ghost": "고스트"}

    @classmethod
    def setUpTestData(cls):
        make_word("commit")
        make_word("merge", aliases="관리자가 고친 값")
        make_word("not-in-table")

    def run_seed(self, *args: str) -> str:
        out = StringIO()
        with mock.patch(SEED_ALIASES, self.TABLE):
            call_command("seed_word_aliases", *args, stdout=out)
        return out.getvalue()

    def alias_of(self, term: str) -> str:
        return Word.objects.get(term=term).aliases

    def test_빈_칸만_채운다(self):
        out = self.run_seed()

        self.assertEqual(self.alias_of("commit"), "커밋, 커미트")
        self.assertEqual(self.alias_of("merge"), "관리자가 고친 값")
        self.assertIn("채움 1, 그대로 1, DB 에 없음 1", out)

    def test_표에_없는_단어는_건드리지_않는다(self):
        self.run_seed("--reset")

        self.assertEqual(self.alias_of("not-in-table"), "")

    def test_reset_은_덮어쓴다(self):
        out = self.run_seed("--reset")

        self.assertEqual(self.alias_of("merge"), "머지")
        self.assertIn("채움 2, 그대로 0, DB 에 없음 1", out)

    def test_dry_run_은_저장하지_않는다(self):
        out = self.run_seed("--dry-run")

        self.assertEqual(self.alias_of("commit"), "")
        self.assertIn("채움 1", out)
        self.assertIn("--dry-run", out)

    def test_reset_과_dry_run_을_같이_줘도_저장하지_않는다(self):
        self.run_seed("--reset", "--dry-run")

        self.assertEqual(self.alias_of("merge"), "관리자가 고친 값")
        self.assertEqual(self.alias_of("commit"), "")

    def test_DB_에_없는_단어는_건너뛰고_이름을_알린다(self):
        out = self.run_seed()

        self.assertIn("없음: ghost", out)
        self.assertFalse(Word.objects.filter(term="ghost").exists())

    def test_두_번_돌려도_같다(self):
        self.run_seed()
        out = self.run_seed()

        self.assertIn("채움 0, 그대로 2", out)
        self.assertEqual(self.alias_of("commit"), "커밋, 커미트")

    def test_미검수_단어를_검수로_바꾸지_않는다(self):
        hidden = make_word("hidden", is_reviewed=False)

        with mock.patch(SEED_ALIASES, {"hidden": "히든"}):
            call_command("seed_word_aliases", stdout=StringIO())

        hidden.refresh_from_db()
        self.assertEqual(hidden.aliases, "히든")
        self.assertFalse(hidden.is_reviewed)
        self.assertEqual(self.client.get(WORDS_URL, {"search": "히든"}).json()["count"], 0)

    def test_단어가_없는_DB_여도_돈다(self):
        Word.objects.all().delete()

        self.assertIn("채움 0, 그대로 0, DB 에 없음 3", self.run_seed())


class SeedAliasTableTest(TestCase):
    """실제 표의 값이 칸에 들어가고, 순위가 기대하는 모양이다."""

    def test_값이_칸_길이를_넘지_않는다(self):
        limit = Word._meta.get_field("aliases").max_length
        term_limit = Word._meta.get_field("term").max_length

        for term, aliases in seed_word_aliases.ALIASES.items():
            with self.subTest(term=term):
                self.assertLessEqual(len(aliases), limit)
                self.assertLessEqual(len(term), term_limit)

    def test_항목은_쉼표_공백으로_잇고_빈_항목이_없다(self):
        for term, aliases in seed_word_aliases.ALIASES.items():
            with self.subTest(term=term):
                items = aliases.split(", ")
                self.assertTrue(all(items), aliases)
                for item in items:
                    self.assertEqual(item, item.strip(), aliases)
                    self.assertNotIn(",", item, aliases)

    def test_한_표기에_같은_항목이_두_번_없다(self):
        for term, aliases in seed_word_aliases.ALIASES.items():
            with self.subTest(term=term):
                items = aliases.split(", ")
                self.assertEqual(len(items), len(set(items)), aliases)
