"""문장 문제 응답의 sentence_kind.

화면은 이 값이 "error" 일 때만 지문을 고정폭으로 그린다. 그래서 틀리면
글꼴이 조용히 바뀔 뿐 아무것도 안 깨진다 - 여기서 못 박는다.

    빈칸 채우기   지문 문장(source_sentence_id)의 kind
    상황 고르기   정답 문장(지문이 그 문장이다)의 kind

두 유형 모두 보기(단어·상황)는 지문과 다른 항목이라, 보기 쪽 문장의
kind 를 실으면 틀린다. 그래서 에러 문장과 실무 표현을 섞어 둔다.
"""

from django.test import TestCase

from .models import Sentence, SentenceKind, Word

QUIZ_URL = "/api/vocab/sentences/quiz/"

TERMS = ("commit", "rebase", "stash", "merge", "cherry")

# (본문, 종류, 상황). 본문마다 단어가 하나씩 들어 있어 빈칸 문제가 된다.
# 상황은 서로 달라야 상황 고르기 보기 넷이 찬다.
SENTENCES = (
    ("fatal: cannot rebase with uncommitted changes", SentenceKind.ERROR, "rebase 가 막힐 때"),
    ("error: failed to push, merge the remote first", SentenceKind.ERROR, "push 가 거절될 때"),
    ("Please stash your changes before you pull.", SentenceKind.PHRASE, "pull 전에 부탁할 때"),
    ("Let's commit this and move on.", SentenceKind.PHRASE, "회의를 마칠 때"),
    ("Can you cherry pick that fix to release?", SentenceKind.PHRASE, "핫픽스를 옮길 때"),
)


def seed_words() -> None:
    for term in TERMS:
        Word.objects.create(
            term=term,
            meaning=f"{term} 뜻",
            description=f"{term} 설명",
            category="git",
            is_reviewed=True,
        )


def seed_sentences(reviewed: bool = True) -> list[Sentence]:
    return [
        Sentence.objects.create(
            text=text,
            translation=f"{text} 해석",
            context=context,
            kind=kind,
            category="git",
            is_reviewed=reviewed,
        )
        for text, kind, context in SENTENCES
    ]


class SentenceKindOnQuizTest(TestCase):
    """GET /api/vocab/sentences/quiz/ 가 지문 문장의 종류를 싣는다."""

    @classmethod
    def setUpTestData(cls):
        seed_words()
        cls.sentences = seed_sentences()

    def ask(self, **params) -> dict:
        res = self.client.get(QUIZ_URL, params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_situation_with_item_carries_that_sentence_kind(self):
        """상황 고르기를 문장으로 정하면 그 문장의 종류가 온다."""
        for sentence in self.sentences:
            body = self.ask(kind="situation", item=sentence.pk)
            self.assertEqual(body["prompt"], sentence.text)
            self.assertEqual(body["sentence_kind"], sentence.kind, sentence.text)

    def test_blank_with_item_carries_the_prompt_sentence_kind(self):
        """빈칸 문제는 정답이 단어라도 지문 문장의 종류가 온다."""
        for sentence in self.sentences:
            body = self.ask(kind="blank", item=sentence.pk)
            self.assertEqual(body["answer_type"], "word")
            self.assertEqual(body["source_sentence_id"], sentence.pk)
            self.assertEqual(body["sentence_kind"], sentence.kind, sentence.text)

    def test_random_questions_match_the_sentence_on_screen(self):
        """유형·문장을 안 정해도 늘 화면에 뜬 문장의 종류와 같다.

        한쪽 값만 나오면(예: 늘 "phrase") 아래 단언이 우연히 통과할 수
        있어, 두 값이 다 나왔는지도 본다.
        """
        by_text = {s.text: s for s in self.sentences}
        by_pk = {s.pk: s for s in self.sentences}
        seen = set()
        for _ in range(40):
            body = self.ask()
            if body["kind"] == "situation":
                expected = by_text[body["prompt"]].kind
            else:
                self.assertEqual(body["kind"], "blank")
                expected = by_pk[body["source_sentence_id"]].kind
            self.assertEqual(body["sentence_kind"], expected, body["prompt"])
            seen.add(body["sentence_kind"])
        self.assertEqual(seen, {SentenceKind.ERROR, SentenceKind.PHRASE})

    def test_value_is_a_known_kind_string(self):
        """화면은 문자열 "error" 와만 비교한다. None·라벨이 오면 조용히 본문체다."""
        for kind in ("blank", "situation"):
            body = self.ask(kind=kind)
            self.assertIsInstance(body["sentence_kind"], str)
            self.assertIn(body["sentence_kind"], SentenceKind.values)


class SentenceKindReviewGateTest(TestCase):
    """검수 안 된 에러 문장이 지문으로 새지 않는다.

    검수된 문장은 전부 실무 표현이다. 응답에 "error" 가 한 번이라도
    오면 미검수 문장이 지문이 된 것이다.
    """

    @classmethod
    def setUpTestData(cls):
        seed_words()
        for sentence in seed_sentences():
            sentence.kind = SentenceKind.PHRASE
            sentence.save(update_fields=["kind"])
        cls.hidden = Sentence.objects.create(
            text="fatal: hidden rebase error that nobody reviewed",
            translation="미검수",
            context="아무도 확인 안 한 상황",
            kind=SentenceKind.ERROR,
            category="git",
            is_reviewed=False,
        )

    def test_unreviewed_error_sentence_never_becomes_the_prompt(self):
        for _ in range(40):
            body = self.client.get(QUIZ_URL).json()
            self.assertNotEqual(body["prompt"], self.hidden.text)
            self.assertNotIn("hidden", body["prompt"])
            self.assertEqual(body["sentence_kind"], SentenceKind.PHRASE)

    def test_unreviewed_item_is_404_not_its_kind(self):
        """번호를 알아도 미검수 문장으로는 문제가 안 나온다."""
        for kind in ("blank", "situation"):
            res = self.client.get(QUIZ_URL, {"kind": kind, "item": self.hidden.pk})
            self.assertEqual(res.status_code, 404, res.content)
            self.assertNotIn("sentence_kind", res.json())
