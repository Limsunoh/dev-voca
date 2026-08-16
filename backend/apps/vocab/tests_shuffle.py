"""목록 섞기(?shuffle=)와 난이도 목록 API 테스트.

섞기는 "목록을 열 때마다 다른 항목이 보이게" 하려는 기능이라, 확인해야 할
것이 셋이다.

1. 같은 시드면 항상 같은 순서다 (아니면 페이지 넘기기가 깨진다)
2. 시드가 다르면 순서가 달라진다 (아니면 섞이지 않은 것이다)
3. 섞어도 필터와 검수 게이트가 그대로 걸린다 (제일 중요하다)
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Sentence, Word

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"


def ids(response):
    return [item["id"] for item in response.json()["results"]]


class ShuffleOrderTest(TestCase):
    """섞은 순서의 성질."""

    @classmethod
    def setUpTestData(cls):
        # 40개를 만든다. 페이지 크기가 20 이라 페이지 경계를 넘겨봐야 한다.
        # 한 페이지 안에서만 보면 우연히 같은 순서가 나와도 통과해버린다.
        for n in range(40):
            Word.objects.create(
                term=f"term{n:03d}",
                meaning=f"뜻{n}",
                category="git" if n % 2 == 0 else "api",
                difficulty=(n % 3) + 1,
                is_reviewed=True,
            )

    def test_같은_시드는_항상_같은_순서를_준다(self):
        first = self.client.get(WORDS_URL, {"shuffle": "seed-a"})
        second = self.client.get(WORDS_URL, {"shuffle": "seed-a"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(ids(first), ids(second))

    def test_시드가_다르면_순서가_달라진다(self):
        a = ids(self.client.get(WORDS_URL, {"shuffle": "seed-a"}))
        b = ids(self.client.get(WORDS_URL, {"shuffle": "seed-b"}))

        self.assertNotEqual(a, b)

    def test_시드가_달라도_전체_항목은_그대로다(self):
        """순서만 달라야 한다. 빠지거나 늘어나면 안 된다.

        1페이지끼리 비교하면 안 된다 - 순서가 다르니 앞 20개에 담기는 항목
        자체가 달라지는 게 정상이다. 두 페이지를 모아서 봐야 한다.
        """

        def everything(seed):
            first = ids(self.client.get(WORDS_URL, {"shuffle": seed}))
            second = ids(self.client.get(WORDS_URL, {"shuffle": seed, "page": 2}))
            return sorted(first + second)

        self.assertEqual(everything("seed-a"), everything("seed-b"))
        self.assertEqual(len(everything("seed-a")), 40)

    def test_섞으면_기본_정렬과_달라진다(self):
        plain = ids(self.client.get(WORDS_URL))
        shuffled = ids(self.client.get(WORDS_URL, {"shuffle": "seed-a"}))

        self.assertNotEqual(plain, shuffled)

    def test_같은_시드로_페이지를_넘기면_겹치거나_빠지지_않는다(self):
        page1 = ids(self.client.get(WORDS_URL, {"shuffle": "seed-a"}))
        page2 = ids(self.client.get(WORDS_URL, {"shuffle": "seed-a", "page": 2}))

        self.assertEqual(len(page1), 20)
        self.assertEqual(len(page2), 20)
        # 이게 깨지면 1페이지에서 본 단어를 2페이지에서 또 만난다.
        self.assertEqual(set(page1) & set(page2), set())
        self.assertEqual(len(set(page1) | set(page2)), 40)

    def test_시드가_비어_있으면_섞지_않는다(self):
        plain = ids(self.client.get(WORDS_URL))

        self.assertEqual(ids(self.client.get(WORDS_URL, {"shuffle": ""})), plain)
        self.assertEqual(ids(self.client.get(WORDS_URL, {"shuffle": "   "})), plain)

    def test_아주_긴_시드도_받아준다(self):
        """길이를 잘라 쓰므로 터지지 않아야 한다."""
        response = self.client.get(WORDS_URL, {"shuffle": "x" * 5000})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(ids(response)), 20)

    def test_시드는_64자까지만_쓴다(self):
        """자르는 동작 자체를 잠근다.

        길이 제한을 지워도 위 테스트는 통과한다(DB 가 긴 문자열을 그냥
        받는다). 65번째 글자만 다른 두 시드가 같은 순서를 주는지 봐야
        실제로 잘리고 있는지 알 수 있다.
        """
        a = ids(self.client.get(WORDS_URL, {"shuffle": "x" * 64 + "a"}))
        b = ids(self.client.get(WORDS_URL, {"shuffle": "x" * 64 + "b"}))

        self.assertEqual(a, b)

    def test_ordering_을_함께_주면_섞지_않는다(self):
        """사용자가 고른 정렬을 섞기가 덮으면 안 된다."""
        ordered = ids(self.client.get(WORDS_URL, {"ordering": "term"}))
        both = ids(
            self.client.get(WORDS_URL, {"ordering": "term", "shuffle": "seed-a"})
        )

        self.assertEqual(ordered, both)

    def test_따옴표가_든_시드로_쿼리가_깨지지_않는다(self):
        response = self.client.get(WORDS_URL, {"shuffle": "a' OR 1=1 --"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 40)

    def test_문장도_같은_방식으로_섞인다(self):
        for n in range(5):
            Sentence.objects.create(
                text=f"sentence {n}",
                translation=f"문장 {n}",
                category="git",
                is_reviewed=True,
            )

        a = ids(self.client.get(SENTENCES_URL, {"shuffle": "s1"}))
        b = ids(self.client.get(SENTENCES_URL, {"shuffle": "s1"}))

        self.assertEqual(a, b)


class ShuffleWithFilterTest(TestCase):
    """섞어도 필터가 그대로 걸리는지. 여기가 깨지면 조용히 틀린 목록이 나간다."""

    @classmethod
    def setUpTestData(cls):
        for n in range(30):
            Word.objects.create(
                term=f"w{n:03d}",
                meaning=f"뜻{n}",
                category="git" if n < 15 else "api",
                difficulty=(n % 3) + 1,
                is_reviewed=True,
            )
        # 미검수. 섞기가 검수 게이트를 뚫는지 보려고 둔다.
        Word.objects.create(term="hidden", meaning="숨김", is_reviewed=False)

    def test_섞어도_분류_필터가_걸린다(self):
        response = self.client.get(WORDS_URL, {"shuffle": "s", "category": "git"})

        self.assertEqual(response.json()["count"], 15)
        for item in response.json()["results"]:
            self.assertEqual(item["category"], "git")

    def test_섞어도_난이도_필터가_걸린다(self):
        response = self.client.get(WORDS_URL, {"shuffle": "s", "difficulty": 3})

        self.assertEqual(response.json()["count"], 10)
        for item in response.json()["results"]:
            self.assertEqual(item["difficulty"], 3)

    def test_분류와_난이도를_같이_걸어도_동작한다(self):
        response = self.client.get(
            WORDS_URL, {"shuffle": "s", "category": "git", "difficulty": 1}
        )

        results = response.json()["results"]
        self.assertTrue(results)
        for item in results:
            self.assertEqual(item["category"], "git")
            self.assertEqual(item["difficulty"], 1)

    def test_섞어도_미검수_단어는_안_나온다(self):
        """섞기가 검수 게이트를 뚫으면 안 된다."""
        terms = set()
        # 시드를 여러 개 돌려 어느 순서에서도 안 새는지 본다.
        for seed in ("a", "b", "c", "d", "e"):
            response = self.client.get(WORDS_URL, {"shuffle": seed})
            self.assertEqual(response.json()["count"], 30)
            terms |= {item["term"] for item in response.json()["results"]}

        self.assertNotIn("hidden", terms)

    def test_검수자에게는_섞어도_검수_대기가_앞에_온다(self):
        """filter_queryset 에서 유일하게 갈라지는 분기다.

        섞기를 검수자 정렬보다 뒤로 옮기면 검수 대기가 목록 전체에 흩어지고,
        일반 사용자 화면은 멀쩡해서 아무도 모른다. 여기서 잠근다.
        """
        staff = get_user_model().objects.create_user(
            email="staff@example.com", password="pw1234!x", is_staff=True
        )
        self.client.force_login(staff)

        response = self.client.get(WORDS_URL, {"shuffle": "seed-a"})

        self.assertEqual(response.status_code, 200)
        terms = [item["term"] for item in response.json()["results"]]
        # 검수자에게는 미검수도 보이고, 그게 맨 앞이어야 한다.
        self.assertEqual(terms[0], "hidden")
        self.assertEqual(response.json()["count"], 31)

    def test_섞어도_검색어가_걸린다(self):
        response = self.client.get(WORDS_URL, {"shuffle": "s", "search": "w00"})

        self.assertTrue(response.json()["count"] > 0)
        for item in response.json()["results"]:
            self.assertTrue("w00" in item["term"])


class DifficultyChoicesTest(TestCase):
    """난이도 목록 API. 화면의 정렬 버튼을 이걸로 만든다."""

    def test_단어_난이도_목록을_준다(self):
        response = self.client.get(f"{WORDS_URL}difficulties/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"value": "1", "label": "쉬움"},
                {"value": "2", "label": "보통"},
                {"value": "3", "label": "어려움"},
            ],
        )

    def test_문장도_같은_난이도_목록을_준다(self):
        """단어와 문장이 같은 척도를 쓴다. 갈리면 화면이 헷갈린다."""
        words = self.client.get(f"{WORDS_URL}difficulties/").json()
        sentences = self.client.get(f"{SENTENCES_URL}difficulties/").json()

        self.assertEqual(words, sentences)

    def test_값을_그대로_필터에_쓸_수_있다(self):
        """내려준 value 로 필터가 실제로 걸려야 한다."""
        Word.objects.create(term="easy", meaning="쉬운", difficulty=1, is_reviewed=True)
        Word.objects.create(term="hard", meaning="어려운", difficulty=3, is_reviewed=True)

        options = self.client.get(f"{WORDS_URL}difficulties/").json()
        easy = next(o for o in options if o["label"] == "쉬움")

        response = self.client.get(WORDS_URL, {"difficulty": easy["value"]})

        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["term"], "easy")

    def test_로그인_없이_볼_수_있다(self):
        """정렬 버튼은 로그인 전에도 보여야 한다."""
        self.assertEqual(
            self.client.get(f"{WORDS_URL}difficulties/").status_code, 200
        )

    def test_난이도_목록은_쓰기가_안_된다(self):
        user = get_user_model().objects.create_user(
            email="who@example.com", password="pw1234!x"
        )
        self.client.force_login(user)

        response = self.client.post(f"{WORDS_URL}difficulties/", {})

        self.assertIn(response.status_code, (403, 405))
