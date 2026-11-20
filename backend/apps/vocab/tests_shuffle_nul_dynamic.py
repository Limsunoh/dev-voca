"""?shuffle= 에 NUL(\\x00)을 넣어 깨뜨려 본다(views.LearningItemViewSet._shuffle).

PostgreSQL 글자 칸은 NUL 을 못 담는다. 시드는 DRF 검증을 거치지 않고 SQL 인자로 가서
NUL 이 섞이면 500 이 났다. 약속은 셋이다.

1. NUL 이 어디에 몇 개 있어도 200 이다. NUL 만 있거나 NUL 과 공백뿐이면 안 섞은 것과 같다
2. NUL 을 뺀 시드와 같은 순서이고, 같은 시드면 쪽을 넘겨도 겹치거나 빠지지 않는다
3. 검수 안 된 항목은 어느 쪽에서도 안 나온다

끝으로 목록·출제·일상영어 주소의 다른 쿼리 값에 NUL 을 넣어도 500 이 아닌지 훑는다.
"""

from __future__ import annotations

from django.test import TestCase

from .models import Sentence, Word

WORDS = "/api/vocab/words/"
SENTENCES = "/api/vocab/sentences/"

# 시드에 NUL 을 넣는 자리와 개수. 둘째 값은 NUL 을 빼고 앞뒤 공백을 지운 시드다.
NUL_SEEDS = [
    ("\x00seed", "seed"),
    ("se\x00ed", "seed"),
    ("seed\x00", "seed"),
    ("\x00s\x00e\x00e\x00d\x00", "seed"),
    (" \x00seed\x00 ", "seed"),
    ("\x00 seed", "seed"),
    ("a" * 70 + "\x00", "a" * 70),
    ("\x00" + "a" * 70, "a" * 70),
    ("a" * 63 + "\x00b", "a" * 63 + "b"),
]

# NUL 을 빼면 아무것도 안 남는 시드. 섞지 않은 기본 순서여야 한다.
EMPTY_SEEDS = ["\x00", "\x00\x00\x00", "\x00 \x00", " \x00 ", "\t\x00\n"]


class _ShuffleNulCases:
    """단어와 문장에 똑같이 거는 경우들. TestCase 를 상속하지 않아 혼자서는 안 돈다."""

    url = WORDS
    reviewed_count = 30

    @classmethod
    def make(cls, n: int, reviewed: bool):
        raise NotImplementedError

    @classmethod
    def setUpTestData(cls):
        # 쪽 크기가 20 이라 30 개면 두 쪽이다. 섞은 순서가 쪽 경계를 넘는지 볼 수 있다.
        cls.reviewed = {cls.make(n, True).pk for n in range(cls.reviewed_count)}
        cls.hidden = {cls.make(n, False).pk for n in range(cls.reviewed_count, cls.reviewed_count + 6)}

    def get_ids(self, params: dict) -> list[int]:
        res = self.client.get(self.url, params)
        self.assertEqual(res.status_code, 200, (params, res.content[:300]))
        return [row["id"] for row in res.json()["results"]]

    def all_pages(self, params: dict) -> list[int]:
        return self.get_ids({**params, "page": 1}) + self.get_ids({**params, "page": 2})

    def test_nul_anywhere_gives_same_order_as_seed_without_nul(self):
        for raw, clean in NUL_SEEDS:
            with self.subTest(seed=repr(raw)):
                got = self.all_pages({"shuffle": raw})
                self.assertEqual(got, self.all_pages({"shuffle": clean}))
                # 같은 시드를 다시 보내도 같은 순서다. 아니면 쪽 넘기기가 깨진다.
                self.assertEqual(got, self.all_pages({"shuffle": raw}))
                # 두 쪽을 합치면 검수된 것 전부, 겹침 없이. 검수 안 된 것은 없다.
                self.assertEqual(len(got), len(set(got)))
                self.assertEqual(set(got), self.reviewed)

    def test_long_seed_with_nul_is_cut_after_removing_nul(self):
        # NUL 을 먼저 빼고 64 자로 자른다. 순서가 바뀌면 NUL 이 앞에 있을 때 시드가 한 글자 짧아진다.
        self.assertEqual(
            self.all_pages({"shuffle": "\x00" + "a" * 70}),
            self.all_pages({"shuffle": "a" * 64}),
        )

    def test_seed_that_is_only_nul_and_blank_means_no_shuffle(self):
        plain = self.all_pages({})
        for raw in EMPTY_SEEDS:
            with self.subTest(seed=repr(raw)):
                self.assertEqual(self.all_pages({"shuffle": raw}), plain)

    def test_nul_seed_with_ordering_keeps_chosen_ordering(self):
        ordering = "-difficulty" if self.url == WORDS else "-id"
        chosen = self.all_pages({"ordering": ordering})
        for raw in ["\x00", "se\x00ed"]:
            with self.subTest(seed=repr(raw)):
                self.assertEqual(self.all_pages({"shuffle": raw, "ordering": ordering}), chosen)

    def test_nul_seed_actually_shuffles(self):
        # NUL 을 뺀 뒤 시드가 남으면 섞여야 한다. 시드를 통째로 버리는 고침이면 여기서 걸린다.
        self.assertNotEqual(self.all_pages({"shuffle": "se\x00ed"}), self.all_pages({}))

    def test_unreviewed_never_leaks_under_nul_seed(self):
        for raw in [s for s, _ in NUL_SEEDS] + EMPTY_SEEDS:
            for page in (1, 2):
                with self.subTest(seed=repr(raw), page=page):
                    got = set(self.get_ids({"shuffle": raw, "page": page}))
                    self.assertFalse(got & self.hidden)


class WordShuffleNulTest(_ShuffleNulCases, TestCase):
    url = WORDS

    @classmethod
    def make(cls, n: int, reviewed: bool):
        return Word.objects.create(
            term=f"nulterm{n:03d}", meaning=f"뜻{n}", category="git",
            difficulty=(n % 3) + 1, is_reviewed=reviewed,
        )


class SentenceShuffleNulTest(_ShuffleNulCases, TestCase):
    url = SENTENCES

    @classmethod
    def make(cls, n: int, reviewed: bool):
        return Sentence.objects.create(
            text=f"nul sentence {n}", translation=f"문장 {n}", category="git",
            difficulty=(n % 3) + 1, is_reviewed=reviewed,
        )


class OtherQueryValuesWithNulTest(TestCase):
    """시드 말고 다른 쿼리 값에 NUL 을 넣어도 500 이 아니다(400·404 는 괜찮다)."""

    @classmethod
    def setUpTestData(cls):
        for n in range(8):
            Word.objects.create(term=f"w{n}", meaning=f"뜻{n}", category="git", is_reviewed=True)
            Sentence.objects.create(text=f"s {n}", translation=f"문 {n}", category="git", is_reviewed=True)

    def test_no_500_for_nul_in_any_known_query_value(self):
        params = [
            "shuffle", "search", "category", "difficulty", "ordering", "is_exam",
            "exam_subject", "kind", "page", "page_size", "exclude", "item", "level", "scene",
        ]
        urls = [
            WORDS, SENTENCES, f"{WORDS}quiz/", f"{SENTENCES}quiz/",
            "/api/vocab/talk/question/",
        ]
        for url in urls:
            for name in params:
                for value in ["\x00", "git\x00", "\x00\x00 "]:
                    with self.subTest(url=url, param=name, value=repr(value)):
                        res = self.client.get(url, {name: value})
                        self.assertLess(res.status_code, 500)

    def test_no_500_for_nul_in_detail_pk(self):
        for url in [f"{WORDS}%00/", f"{SENTENCES}%00/", f"{WORDS}1%00/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
