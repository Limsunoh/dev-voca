"""?item= 으로 정답을 정해 내는 문제.

상세 화면의 "이 단어로 문제 풀기" 가 쓴다. 전에는 이 파라미터가 없어서
그 버튼이 무작위 문제로 보냈다 - 방금 읽은 단어가 아니라 엉뚱한 단어가
나왔다.

정답은 채점을 한 번 불러서 확인한다. 응답에 정답이 없기 때문이다.
"""

from django.test import TestCase

from .models import Sentence
from .tests_sentence_quiz_adversarial import (
    GRADE_URL as SENTENCE_GRADE_URL,
)
from .tests_sentence_quiz_adversarial import (
    QUIZ_URL as SENTENCE_QUIZ_URL,
)
from .tests_sentence_quiz_adversarial import (
    WORD_GRADE_URL,
    WORD_QUIZ_URL,
    QuizFixtureMixin,
)


class QuizItemTest(QuizFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seed()

    def answer(self, grade_url: str, body: dict) -> dict:
        graded = self.client.post(
            grade_url, {"token": body["token"], "picked": -1}, content_type="application/json"
        )
        self.assertEqual(graded.status_code, 200, graded.content)
        return graded.json()

    def test_word_item_is_the_answer(self):
        """무작위라 여러 번 불러도 늘 그 단어가 정답이어야 한다."""
        target = self.words[2]
        for _ in range(8):
            res = self.client.get(WORD_QUIZ_URL, {"item": target.pk})
            self.assertEqual(res.status_code, 200, res.content)
            body = res.json()
            self.assertIn(target.pk, [c["id"] for c in body["choices"]])
            self.assertEqual(self.answer(WORD_GRADE_URL, body)["answer_id"], target.pk)

    def test_word_item_ignores_exclude(self):
        """방금 본 단어로 풀겠다고 온 것이라 exclude 에 있어도 낸다."""
        target = self.words[0]
        res = self.client.get(WORD_QUIZ_URL, {"item": target.pk, "exclude": str(target.pk)})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.answer(WORD_GRADE_URL, res.json())["answer_id"], target.pk)

    def test_sentence_item_is_the_question(self):
        """빈칸이면 그 문장에 뚫고, 상황 고르기면 그 문장이 정답이다."""
        target = self.sentences[1]
        # 문장이 다섯뿐이라 한 번은 우연히 맞을 수 있다. 여러 번 본다.
        for kind in ("blank", "situation") * 4:
            res = self.client.get(SENTENCE_QUIZ_URL, {"item": target.pk, "kind": kind})
            self.assertEqual(res.status_code, 200, (kind, res.content))
            body = res.json()
            if kind == "blank":
                self.assertEqual(body["source_sentence_id"], target.pk)
                self.assertIn("____", body["prompt"])
            else:
                graded = self.answer(SENTENCE_GRADE_URL, body)
                self.assertEqual(graded["answer_id"], target.pk)

    def test_sentence_item_without_kind_uses_that_sentence(self):
        target = self.sentences[3]
        for _ in range(6):
            body = self.client.get(SENTENCE_QUIZ_URL, {"item": target.pk}).json()
            if body["kind"] == "blank":
                self.assertEqual(body["source_sentence_id"], target.pk)
            else:
                self.assertEqual(
                    self.answer(SENTENCE_GRADE_URL, body)["answer_id"], target.pk
                )

    def test_unreviewed_item_is_404_like_missing(self):
        """검수 안 된 번호와 없는 번호를 가르지 않는다. 가르면 번호를 돌려가며
        검수 상태를 알아낼 수 있다."""
        hidden = Sentence.objects.create(
            text="Please squash before you push.",
            translation="합치세요",
            context="합치라고 할 때",
            category="git",
            is_reviewed=False,
        )
        unreviewed = self.client.get(SENTENCE_QUIZ_URL, {"item": hidden.pk})
        missing = self.client.get(SENTENCE_QUIZ_URL, {"item": 999999})
        self.assertEqual(unreviewed.status_code, 404)
        self.assertEqual(unreviewed.json(), missing.json())

        self.words[4].is_reviewed = False
        self.words[4].save(update_fields=["is_reviewed"])
        res = self.client.get(WORD_QUIZ_URL, {"item": self.words[4].pk})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "이 단어로는 지금 문제를 낼 수 없습니다.")

    def test_bad_item_is_400_not_500(self):
        for raw in ("abc", "1,2", "\x00", "9" * 30, "-1", "1.5", "0", "1,abc", "1,", "01"):
            for url in (WORD_QUIZ_URL, SENTENCE_QUIZ_URL):
                res = self.client.get(url, {"item": raw})
                self.assertEqual(res.status_code, 400, (url, raw))

    def test_empty_item_means_no_item(self):
        """?item= 빈 값은 안 준 것과 같다 - 무작위로 낸다."""
        self.assertEqual(self.client.get(WORD_QUIZ_URL, {"item": ""}).status_code, 200)

    def test_item_outside_category_is_404(self):
        """분류와 함께 오면 분류 안에서 찾는다. 다른 분류의 단어면 못 낸다."""
        res = self.client.get(WORD_QUIZ_URL, {"item": self.words[0].pk, "category": "api"})
        self.assertEqual(res.status_code, 404)
