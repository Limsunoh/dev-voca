"""단어 목록의 알파벳 정렬(?ordering=term).

DB 기본 정렬은 환경마다 달라서(views.ReadableOrdering 참고) 같은 주소가
로컬과 운영에서 다른 순서를 냈다. 여기서는 어느 DB 에서든 "소문자로 바꾼
값의 바이트 순서, 같으면 원래 값의 바이트 순서" 하나로 정렬되는지 본다.

기대값은 파이썬으로 같은 규칙을 계산해 만든다. 테스트 DB 에 다른 단어가
있어도 목록 전체를 모아 비교하므로 영향이 없다.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Word

WORDS_URL = "/api/vocab/words/"

# 대문자 약어, 소문자 단어, 숫자가 낀 것, 띄어쓰기가 낀 것, 대소문자만 다른 짝.
TERMS = [
    "API", "apple", "a11y", "Docker", "codebase", "code review",
    "YAML", "zip", "CPU", "cache", "Go", "go", "HTTP", "http2",
]


def readable(term: str) -> tuple[bytes, bytes]:
    return term.lower().encode("utf-8"), term.encode("utf-8")


def all_terms(client, params: dict) -> list[str]:
    """페이지를 끝까지 넘기며 term 을 모은다."""
    terms, page = [], 1
    while True:
        body = client.get(WORDS_URL, {**params, "page": page}).json()
        terms += [row["term"] for row in body["results"]]
        if not body["next"]:
            return terms
        page += 1


class WordOrderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 페이지 경계(20개)를 넘기려고 같은 규칙의 단어를 더 만든다.
        extra = [f"{'Ab' if n % 2 else 'ab'}{n:02d}" for n in range(12)]
        for n, term in enumerate(TERMS + extra):
            Word.objects.create(
                term=term, meaning=f"뜻{n}", difficulty=(n % 3) + 1, is_reviewed=True
            )

    def test_대소문자를_무시하고_알파벳_순서다(self):
        got = all_terms(self.client, {"ordering": "term"})

        self.assertEqual(got, sorted(got, key=readable))
        # 약어가 소문자 단어보다 전부 앞에 몰리지 않는다.
        self.assertLess(got.index("apple"), got.index("CPU"))
        self.assertLess(got.index("API"), got.index("apple"))

    def test_띄어쓰기는_글자보다_앞이다(self):
        """glibc 는 띄어쓰기를 무시해 codebase 를 앞에 둔다. 환경마다 같아야 한다."""
        got = all_terms(self.client, {"ordering": "term"})

        self.assertLess(got.index("code review"), got.index("codebase"))

    def test_대소문자만_다르면_대문자가_앞이다(self):
        got = all_terms(self.client, {"ordering": "term"})

        self.assertEqual(got.index("Go") + 1, got.index("go"))

    def test_역순(self):
        got = all_terms(self.client, {"ordering": "-term"})

        self.assertEqual(got, sorted(got, key=readable, reverse=True))

    def test_난이도_안에서도_알파벳_순서다(self):
        """"쉬운 것부터"(difficulty,term)의 같은 난이도 안 순서."""
        got = all_terms(self.client, {"ordering": "difficulty,term"})
        level = {w.term: w.difficulty for w in Word.objects.all()}

        self.assertEqual(got, sorted(got, key=lambda t: (level[t], readable(t))))

    def test_정렬을_안_주면_알파벳_순서다(self):
        """기본 정렬(ordering = ["term"])도 같은 규칙을 탄다. 검색 결과가 이 순서다."""
        got = all_terms(self.client, {})

        self.assertEqual(got, sorted(got, key=readable))

    def test_페이지를_넘겨도_겹치거나_빠지지_않는다(self):
        got = all_terms(self.client, {"ordering": "term"})

        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(set(got), set(Word.objects.values_list("term", flat=True)))

    def test_검수자에게는_검수_대기가_앞이고_그_안은_알파벳_순서다(self):
        Word.objects.create(term="Zebra", meaning="얼룩말", is_reviewed=False)
        Word.objects.create(term="alpha", meaning="알파", is_reviewed=False)
        staff = get_user_model().objects.create_user(
            email="staff-order@example.com", password="x-Strong-pass-1", is_staff=True
        )
        self.client.force_login(staff)

        got = all_terms(self.client, {"ordering": "term"})

        self.assertEqual(got[:2], ["alpha", "Zebra"])
        self.assertEqual(got[2:], sorted(got[2:], key=readable))

    def test_없는_필드로는_정렬하지_않는다(self):
        """ordering_fields 밖의 값은 무시한다(기본 정렬로 떨어진다)."""
        got = all_terms(self.client, {"ordering": "meaning"})

        self.assertEqual(got, sorted(got, key=readable))
