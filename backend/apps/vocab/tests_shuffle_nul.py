"""섞기 시드(?shuffle=)에 NUL 이 들어와도 500 이 나지 않는다.

시드는 DRF 검증을 거치지 않고 SQL 까지 가는 유일한 쿼리 값이다. PostgreSQL
글자 칸은 NUL 을 담지 못해 ?shuffle=%00 이 500 이었다. 주소를 손으로 고쳐야
닿는 자리라 사용자 피해는 없었지만 Sentry 에 오류로 쌓인다.
"""

from django.test import TestCase

from .models import Sentence, Word

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"


def ids(response):
    return [item["id"] for item in response.json()["results"]]


class ShuffleNulTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        for n in range(30):
            Word.objects.create(term=f"term{n:03d}", meaning=f"뜻{n}", is_reviewed=True)
            Sentence.objects.create(
                text=f"sentence {n}", translation=f"문장 {n}", is_reviewed=True
            )

    def test_NUL_만_있는_시드는_섞지_않은_목록과_같다(self):
        plain = self.client.get(WORDS_URL)
        nul = self.client.get(WORDS_URL, {"shuffle": "\x00"})

        self.assertEqual(nul.status_code, 200)
        self.assertEqual(ids(nul), ids(plain))

    def test_NUL_을_뺀_나머지_글자로_섞는다(self):
        clean = self.client.get(WORDS_URL, {"shuffle": "seed-a"})
        dirty = self.client.get(WORDS_URL, {"shuffle": "se\x00ed-a\x00"})

        self.assertEqual(dirty.status_code, 200)
        self.assertEqual(ids(dirty), ids(clean))

    def test_문장_목록도_같다(self):
        clean = self.client.get(SENTENCES_URL, {"shuffle": "seed-a"})
        dirty = self.client.get(SENTENCES_URL, {"shuffle": "\x00seed-a"})

        self.assertEqual(dirty.status_code, 200)
        self.assertEqual(ids(dirty), ids(clean))
