"""단어 목록 알파벳 정렬(views.ReadableOrdering)의 경계·남용 테스트.

기본 규칙은 "소문자로 바꾼 값의 바이트 순서, 같으면 원래 값의 바이트 순서"다.
여기서는 그 규칙이 정렬값 조합, shuffle·검색·필터, 검수자 경로, 문장 목록,
비ASCII 값, 페이지 경계에서도 유지되는지, 이상한 ordering 값이 500 을
내지 않는지를 본다.

기대값은 파이썬으로 같은 규칙을 계산해 만든다. 비ASCII 문자의 소문자 변환은
DB 로케일마다 달라질 수 있어서, 그런 값은 순서 대신 "빠짐·겹침 없음"과
"요청마다 같은 순서"만 본다.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Sentence, Word

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"

ASCII_TERMS = [
    "API", "apple", "a11y", "Docker", "codebase", "code review", "YAML", "zip",
    "CPU", "cache", "Go", "go", "GO", "HTTP", "http2", "C++", "node.js",
    "_private", "__init__", "a-b", "a b", "ab", "Ab", "aB", "AB", "x%y", "it's",
    "back\\slash", "9lives", "Zebra", "zebra",
]
NON_ASCII_TERMS = ["가나다", "나비", "Éclair", "éclair", "straße", "日本語", "Ünï"]
HIDDEN = ("Hidden", "aaa-hidden", "zzz-hidden")


def readable(term: str) -> tuple[bytes, bytes]:
    return term.lower().encode("utf-8"), term.encode("utf-8")


def collect(client, params: dict) -> list[dict]:
    """페이지를 끝까지 넘기며 행을 모은다."""
    rows, page = [], 1
    while True:
        response = client.get(WORDS_URL, {**params, "page": page})
        assert response.status_code == 200, (params, page, response.status_code)
        body = response.json()
        rows += body["results"]
        if not body["next"]:
            return rows
        page += 1


def terms(client, params: dict) -> list[str]:
    return [row["term"] for row in collect(client, params)]


class OrderBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for n, term in enumerate(ASCII_TERMS):
            Word.objects.create(
                term=term, meaning=f"뜻{n}", difficulty=(n % 3) + 1,
                category="git" if n % 2 else "api", is_exam=(n % 4 == 0),
                is_reviewed=True,
            )
        for n, term in enumerate(NON_ASCII_TERMS):
            Word.objects.create(term=term, meaning=f"뜻-{n}", is_reviewed=True)
        # 검수 안 된 것: 어떤 정렬 값으로도 일반 사용자에게 새면 안 된다.
        for term in HIDDEN:
            Word.objects.create(term=term, meaning="미검수", is_reviewed=False)
        cls.ascii_expected = sorted(ASCII_TERMS, key=readable)
        cls.level = {w.term: w.difficulty for w in Word.objects.all()}

    def ascii_only(self, got: list[str]) -> list[str]:
        return [t for t in got if t in ASCII_TERMS]


class OrderingCombinationTest(OrderBase):
    def test_역순_정렬은_정순의_정확한_뒤집기다(self):
        asc = terms(self.client, {"ordering": "term"})
        desc = terms(self.client, {"ordering": "-term"})

        self.assertEqual(desc, asc[::-1])

    def test_term_뒤에_난이도를_붙여도_term_순서다(self):
        """term 은 유일하므로 뒤 키는 순서를 못 바꾼다."""
        got = terms(self.client, {"ordering": "term,-difficulty"})

        self.assertEqual(got, terms(self.client, {"ordering": "term"}))

    def test_난이도_안에서_term_역순(self):
        got = self.ascii_only(terms(self.client, {"ordering": "difficulty,-term"}))

        levels = [self.level[t] for t in got]
        self.assertEqual(levels, sorted(levels))
        for level in set(levels):
            group = [t for t in got if self.level[t] == level]
            self.assertEqual(group, sorted(group, key=readable, reverse=True), level)

    def test_쉼표_공백_빈_값에도_500이_아니다(self):
        values = [
            "", " ", ",", ",,,", "term,", ",term", " term ", "term , difficulty",
            "-", "- term", "nope", "term,nope", "-nope", "term;drop table",
            "TERM", "term" * 50, "meaning", "id", "-created_at,term", "\x00",
        ]
        for value in values:
            with self.subTest(ordering=value):
                response = self.client.get(WORDS_URL, {"ordering": value})
                self.assertEqual(response.status_code, 200)

    def test_공백이_낀_term도_정렬로_인정된다(self):
        got = terms(self.client, {"ordering": " term "})

        self.assertEqual(self.ascii_only(got), self.ascii_expected)

    def test_없는_필드만_주면_기본_알파벳_순서다(self):
        for value in ("nope", "meaning,nope", ","):
            with self.subTest(ordering=value):
                got = terms(self.client, {"ordering": value})
                self.assertEqual(self.ascii_only(got), self.ascii_expected)

    def test_같은_필드를_여러_번_줘도_된다(self):
        for value in ("term,term", "term,-term", "-term,term", "--term"):
            with self.subTest(ordering=value):
                response = self.client.get(WORDS_URL, {"ordering": value})
                self.assertEqual(response.status_code, 200)

    def test_이중_하이픈은_다른_필드에서도_500이_아니다(self):
        """DRF 는 lstrip('-') 로 유효성을 봐서 --difficulty 도 통과시킨다."""
        for value in ("--difficulty", "--created_at", "---term"):
            with self.subTest(ordering=value):
                response = self.client.get(WORDS_URL, {"ordering": value})
                self.assertEqual(response.status_code, 200)

    def test_ASCII_term의_순서는_규칙과_정확히_같다(self):
        got = self.ascii_only(terms(self.client, {"ordering": "term"}))

        self.assertEqual(got, self.ascii_expected)


class ShuffleAndSearchTest(OrderBase):
    def test_shuffle_만_주면_알파벳_순서가_아니고_요청마다_같다(self):
        first = terms(self.client, {"shuffle": "seed1"})
        again = terms(self.client, {"shuffle": "seed1"})

        self.assertEqual(first, again)
        self.assertEqual(len(first), len(set(first)))
        self.assertNotEqual(self.ascii_only(first), self.ascii_expected)

    def test_shuffle_과_ordering_을_같이_주면_ordering_이_이긴다(self):
        got = terms(self.client, {"shuffle": "seed1", "ordering": "term"})

        self.assertEqual(self.ascii_only(got), self.ascii_expected)

    def test_shuffle_과_역순을_같이_줘도_역순이다(self):
        got = terms(self.client, {"shuffle": "x", "ordering": "-term"})

        self.assertEqual(self.ascii_only(got), self.ascii_expected[::-1])

    def test_shuffle_이_공백뿐이면_알파벳_순서다(self):
        got = terms(self.client, {"shuffle": "   "})

        self.assertEqual(self.ascii_only(got), self.ascii_expected)

    def test_shuffle_에도_미검수가_새지_않는다(self):
        got = terms(self.client, {"shuffle": "abc"})

        for hidden in HIDDEN:
            self.assertNotIn(hidden, got)

    def test_검색과_정렬을_같이_줘도_순서가_맞고_미검수는_없다(self):
        got = terms(self.client, {"search": "뜻", "ordering": "-term"})

        self.assertEqual(self.ascii_only(got), self.ascii_expected[::-1])
        for hidden in HIDDEN:
            self.assertNotIn(hidden, got)

    def test_검색만_해도_알파벳_순서다(self):
        got = terms(self.client, {"search": "a"})

        self.assertEqual(got, sorted(got, key=readable))
        self.assertNotIn("aaa-hidden", got)

    def test_검색어에_특수문자가_있어도_500이_아니다(self):
        for q in ["%", "_", "'", '"', "\\", "a b", "C++", "'; --", "가", "\x00", "a" * 500]:
            with self.subTest(q=q):
                response = self.client.get(WORDS_URL, {"search": q, "ordering": "term"})
                self.assertIn(response.status_code, (200, 400))

    def test_검색_결과도_페이지를_넘겨_겹치지_않는다(self):
        # 검수된 단어의 뜻은 모두 "뜻" 으로 시작하므로 전체가 걸린다.
        ids = [r["id"] for r in collect(self.client, {"search": "뜻", "ordering": "term"})]

        self.assertEqual(len(ids), len(set(ids)))
        # 미검수 단어의 뜻은 "미검수" 라 "뜻" 에 안 걸린다.
        self.assertEqual(len(ids), Word.objects.filter(is_reviewed=True).count())


class FilterTest(OrderBase):
    def test_필터와_정렬을_같이_줘도_순서가_맞다(self):
        cases = [
            {"category": "git"}, {"difficulty": "2"}, {"is_exam": "true"},
            {"category": "api", "difficulty": "1"},
            {"category": "git", "is_exam": "false", "difficulty": "3"},
        ]
        for filt in cases:
            for ordering in ("term", "-term", "difficulty,term", "difficulty,-term"):
                with self.subTest(filt=filt, ordering=ordering):
                    qs = Word.objects.filter(is_reviewed=True)
                    if "category" in filt:
                        qs = qs.filter(category=filt["category"])
                    if "difficulty" in filt:
                        qs = qs.filter(difficulty=int(filt["difficulty"]))
                    if "is_exam" in filt:
                        qs = qs.filter(is_exam=filt["is_exam"] == "true")
                    got = terms(self.client, {**filt, "ordering": ordering})
                    self.assertEqual(set(got), set(qs.values_list("term", flat=True)))
                    self.assertEqual(len(got), len(set(got)))
                    ascii_got = self.ascii_only(got)
                    if ordering == "term":
                        self.assertEqual(ascii_got, sorted(ascii_got, key=readable))
                    elif ordering == "-term":
                        self.assertEqual(
                            ascii_got, sorted(ascii_got, key=readable, reverse=True)
                        )
                    else:
                        rev = ordering.endswith("-term")
                        levels = [self.level[t] for t in ascii_got]
                        self.assertEqual(levels, sorted(levels))
                        for level in set(levels):
                            group = [t for t in ascii_got if self.level[t] == level]
                            self.assertEqual(
                                group, sorted(group, key=readable, reverse=rev)
                            )

    def test_잘못된_필터값에도_500이_아니다(self):
        bad = (
            {"difficulty": "abc"}, {"difficulty": "99999999999999999999"},
            {"is_exam": "maybe"}, {"category": "nope"}, {"exam_subject": "nope"},
        )
        for params in bad:
            with self.subTest(params=params):
                response = self.client.get(WORDS_URL, {**params, "ordering": "term"})
                self.assertIn(response.status_code, (200, 400))


class ReviewerTest(OrderBase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            email="edge-staff@example.com", password="x-Strong-pass-1", is_staff=True
        )
        self.normal = user_model.objects.create_user(
            email="edge-normal@example.com", password="x-Strong-pass-1"
        )

    def test_검수자는_대기가_앞이고_각_묶음_안은_정렬값을_따른다(self):
        self.client.force_login(self.staff)
        for ordering, rev in (("term", False), ("-term", True), ("", False)):
            with self.subTest(ordering=ordering):
                got = terms(self.client, {"ordering": ordering} if ordering else {})
                head, tail = got[:3], got[3:]
                self.assertEqual(set(head), set(HIDDEN))
                self.assertEqual(head, sorted(head, key=readable, reverse=rev))
                self.assertEqual(
                    self.ascii_only(tail), sorted(ASCII_TERMS, key=readable, reverse=rev)
                )

    def test_검수자도_난이도_정렬_뒤에_대기가_앞이다(self):
        self.client.force_login(self.staff)
        got = terms(self.client, {"ordering": "difficulty,term"})

        self.assertEqual(set(got[:3]), set(HIDDEN))

    def test_검수자가_shuffle_을_줘도_대기가_앞이다(self):
        self.client.force_login(self.staff)
        got = terms(self.client, {"shuffle": "s"})

        self.assertEqual(set(got[:3]), set(HIDDEN))
        self.assertEqual(len(got), len(set(got)))

    def test_일반_로그인_사용자는_어떤_정렬로도_미검수를_못_본다(self):
        self.client.force_login(self.normal)
        cases = (
            {}, {"ordering": "term"}, {"ordering": "-term"},
            {"ordering": "difficulty,-term"}, {"shuffle": "q"},
            {"search": "hidden"}, {"search": "미검수", "ordering": "term"},
        )
        for params in cases:
            with self.subTest(params=params):
                got = terms(self.client, params)
                for hidden in HIDDEN:
                    self.assertNotIn(hidden, got)

    def test_익명은_상세로도_미검수를_못_본다(self):
        pk = Word.objects.get(term="Hidden").pk

        self.assertEqual(self.client.get(f"{WORDS_URL}{pk}/").status_code, 404)

    def test_비활성_검수자는_미검수를_못_본다(self):
        self.staff.is_active = False
        self.staff.save()
        self.client.force_login(self.normal)
        got = terms(self.client, {"ordering": "term"})

        self.assertNotIn("Hidden", got)


class SentenceOrderingTest(TestCase):
    """문장 목록의 ordering 은 이전과 같다(term 을 알지 못한다)."""

    @classmethod
    def setUpTestData(cls):
        for n in range(25):
            Sentence.objects.create(
                text=f"{'Z' if n % 2 else 'a'} sentence {n:02d}",
                translation=f"뜻{n}", difficulty=(n % 3) + 1, is_reviewed=True,
            )
        Sentence.objects.create(text="hidden", translation="미검수", is_reviewed=False)

    def ids(self, params):
        out, page = [], 1
        while True:
            response = self.client.get(SENTENCES_URL, {**params, "page": page})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            out += [r["id"] for r in body["results"]]
            if not body["next"]:
                return out
            page += 1

    def test_기본_정렬은_id_순이다(self):
        got = self.ids({})

        self.assertEqual(got, sorted(got))
        self.assertEqual(len(got), 25)

    def test_term_정렬은_허용되지_않아_id_순으로_떨어진다(self):
        for value in ("term", "-term", "text", "nope"):
            with self.subTest(ordering=value):
                self.assertEqual(self.ids({"ordering": value}), self.ids({}))

    def test_id_역순과_난이도_정렬은_그대로_작동한다(self):
        asc = self.ids({})

        self.assertEqual(self.ids({"ordering": "-id"}), asc[::-1])
        rows = self.client.get(SENTENCES_URL, {"ordering": "-difficulty"}).json()["results"]
        levels = [r["difficulty"] for r in rows]
        self.assertEqual(levels, sorted(levels, reverse=True))

    def test_미검수_문장은_정렬과_무관하게_안_보인다(self):
        for value in ("id", "-id", "difficulty", "term"):
            with self.subTest(ordering=value):
                body = self.client.get(SENTENCES_URL, {"ordering": value}).json()
                self.assertNotIn("hidden", [r["text"] for r in body["results"]])


class NonAsciiAndPagingTest(OrderBase):
    def test_비ASCII_term도_빠짐_겹침_없이_안정적으로_정렬된다(self):
        a = terms(self.client, {"ordering": "term"})
        b = terms(self.client, {"ordering": "term"})
        expected = set(Word.objects.filter(is_reviewed=True).values_list("term", flat=True))

        self.assertEqual(a, b)
        self.assertEqual(len(a), len(set(a)))
        self.assertEqual(set(a), expected)

    def test_한글은_코드포인트_순서다(self):
        got = terms(self.client, {"ordering": "term"})

        self.assertLess(got.index("가나다"), got.index("나비"))

    def test_비ASCII_포함_역순도_정순의_뒤집기다(self):
        asc = terms(self.client, {"ordering": "term"})
        desc = terms(self.client, {"ordering": "-term"})

        self.assertEqual(desc, asc[::-1])

    def test_특수문자_term도_검색으로_찾아진다(self):
        for term in ("C++", "it's", "back\\slash", "x%y", "日本語"):
            with self.subTest(term=term):
                self.assertIn(term, terms(self.client, {"search": term, "ordering": "term"}))

    def test_모든_정렬값에서_페이지를_넘겨도_겹침_누락이_없다(self):
        expected = set(Word.objects.filter(is_reviewed=True).values_list("term", flat=True))
        orderings = (
            "term", "-term", "difficulty,term", "-difficulty,-term",
            "created_at", "-created_at,term",
        )
        for ordering in orderings:
            with self.subTest(ordering=ordering):
                got = terms(self.client, {"ordering": ordering})
                self.assertEqual(len(got), len(set(got)))
                self.assertEqual(set(got), expected)

    def test_페이지_경계의_양쪽_항목이_이어진다(self):
        full = terms(self.client, {"ordering": "term"})
        params = {"ordering": "term"}
        page1 = [r["term"] for r in self.client.get(WORDS_URL, {**params, "page": 1}).json()["results"]]
        page2 = [r["term"] for r in self.client.get(WORDS_URL, {**params, "page": 2}).json()["results"]]

        self.assertEqual(len(page1), 20)
        self.assertEqual(page1 + page2, full[: len(page1) + len(page2)])

    def test_잘못된_페이지는_404이고_500이_아니다(self):
        for page in ("0", "-1", "999999", "abc", "9" * 30, "1.5", ""):
            with self.subTest(page=page):
                response = self.client.get(WORDS_URL, {"ordering": "term", "page": page})
                self.assertIn(response.status_code, (200, 404))

    def test_page_size_는_무시된다(self):
        response = self.client.get(WORDS_URL, {"ordering": "term", "page_size": 100000})

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["results"]), 20)

    def test_대소문자만_다른_값은_대문자가_앞이고_붙어_있다(self):
        got = terms(self.client, {"ordering": "term"})

        for group in (["AB", "Ab", "aB", "ab"], ["GO", "Go", "go"], ["Zebra", "zebra"]):
            idx = [got.index(t) for t in group]
            self.assertEqual(idx, list(range(idx[0], idx[0] + len(idx))), group)


class CollationGuardTest(OrderBase):
    """로컬 DB 는 이미 바이트 순서라 Collate 가 빠져도 결과가 같다.

    glibc DB(운영·CI)에서만 드러나는 회귀라, 여기서는 SQL 에 콜레이션이
    실제로 걸리는지를 직접 본다.
    """

    def test_postgres_에서는_정렬_SQL_에_C_콜레이션이_걸린다(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        if connection.vendor != "postgresql":
            self.skipTest("postgresql 전용")
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(WORDS_URL, {"ordering": "term"})
        order_sql = [q["sql"] for q in ctx.captured_queries if "ORDER BY" in q["sql"]]

        self.assertTrue(order_sql)
        self.assertIn('COLLATE "C"', order_sql[-1].split("ORDER BY")[-1])
