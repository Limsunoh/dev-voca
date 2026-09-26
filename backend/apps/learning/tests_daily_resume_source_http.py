"""일일공부 이어 풀기가 지문의 원천을 다시 거르는가 - HTTP 로 친다.

tests_daily_resume_source 는 daily_study.resume 을 직접 부른다. 화면은
GET /api/learning/daily/ 로 이어 풀기를 받으므로, view 가 조립한 응답에
검수가 취소된 글이 실리는지를 여기서 본다.

유형마다 지문이 어디서 오는지가 다르다.

    빈칸        원문 문장 하나 (보기는 단어라 보기 검사로 안 걸린다)
    상황        정답 문장 (보기 안에 있다)
    뜻·단어·설명 정답 단어 (보기 안에 있다)

빈칸은 저장해 둔 source_sentence_id 로, 나머지는 보기 검사로 걸러야 한다.
출제 유형을 운에 맡기지 않으려고 daily_study.make_question 을 고정한다.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import daily_study
from .models import DailyStudy, StudyLength
from .tests_daily_study import ANSWER_URL, START_URL, make_user, seed_words


class _Forced:
    """daily_study.make_question 대역. self.kind 유형으로만 낸다.

    못 만들면 None 을 낸다 - 폴백으로 다른 유형을 내면 "빈칸이 다시
    나오지 않았다" 가 우연인지 방어인지 구분이 안 된다.
    """

    def __init__(self, kind: str):
        self.kind = kind

    def __call__(self, *_args, **_kwargs):
        words = Word.objects.visible()
        sentences = Sentence.objects.visible()
        if self.kind == quiz.QuizKind.BLANK:
            return quiz.make_blank_question(sentences, words)
        if self.kind == quiz.QuizKind.SITUATION:
            return quiz.make_situation_question(sentences)
        return quiz.make_question(words, self.kind)


class _HttpBase(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("원문http")
        self.client.force_login(self.user)
        terms = list(Word.objects.visible().values_list("term", flat=True)[:6])
        for i, term in enumerate(terms):
            Sentence.objects.create(
                text=f"Please run {term} before the release number {i}.",
                translation=f"릴리스 전에 {term} 을 돌려 주세요 {i}",
                context=f"릴리스 준비할 때 {i}",
                is_reviewed=True,
            )
        self.forced = _Forced(quiz.QuizKind.BLANK)
        patcher = mock.patch.object(daily_study, "make_question", side_effect=self.forced)
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self) -> dict:
        res = self.client.post(START_URL, {"length": StudyLength.SHORT}, "application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def get(self) -> dict:
        res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def saved(self) -> dict:
        return DailyStudy.objects.get(user=self.user).question or {}

    def assert_blank_source_visible(self, body: dict) -> None:
        """응답의 빈칸 지문이 지금 검수된 문장에서 나왔는가."""
        question = body["question"]
        if question is None or question["kind"] != quiz.QuizKind.BLANK:
            return
        parts = [p for p in question["prompt"].split("____") if p.strip()]
        sources = [
            s for s in Sentence.objects.all() if all(p in s.text for p in parts)
        ]
        self.assertTrue(sources, "지문의 원문 문장을 못 찾았다")
        for s in sources:
            self.assertTrue(s.is_reviewed, f"검수 안 된 문장이 지문으로 나갔다: {s.text}")


class BlankSourceHttpTest(_HttpBase):
    """빈칸 문제의 원문 문장."""

    def test_unreviewed_source_is_not_served_by_get(self):
        """시작 뒤 원문 문장 검수 취소 -> GET 이 그 지문을 안 준다."""
        first = self.start()
        self.assertEqual(first["question"]["kind"], quiz.QuizKind.BLANK)
        source = self.saved()["source_sentence_id"]
        Sentence.objects.filter(pk=source).update(is_reviewed=False)

        body = self.get()

        self.assertIsNotNone(body["question"])
        self.assertNotEqual(body["question"]["prompt"], first["question"]["prompt"])
        self.assert_blank_source_visible(body)
        self.assertNotEqual(self.saved()["source_sentence_id"], source)

    def test_deleted_source_is_not_served_by_get(self):
        """원문 문장을 지워도 GET 이 200 이고 그 지문을 안 준다."""
        first = self.start()
        source = self.saved()["source_sentence_id"]
        Sentence.objects.filter(pk=source).delete()

        body = self.get()

        self.assertIsNotNone(body["question"])
        self.assertNotEqual(body["question"]["prompt"], first["question"]["prompt"])
        self.assert_blank_source_visible(body)

    def test_the_replacement_can_be_answered(self):
        """갈아 낸 문제의 토큰으로 실제로 답할 수 있다(순번이 어긋나지 않았다)."""
        self.start()
        Sentence.objects.filter(pk=self.saved()["source_sentence_id"]).update(
            is_reviewed=False
        )
        body = self.get()

        res = self.client.post(
            ANSWER_URL,
            {"token": body["token"], "choice_id": body["question"]["choices"][0]["id"]},
            "application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_no_sentence_left_closes_the_study(self):
        """문장이 전부 검수 취소돼 빈칸을 못 내면 판이 닫히고 문제는 없다."""
        self.start()
        Sentence.objects.update(is_reviewed=False)

        body = self.get()

        self.assertIsNone(body["question"])
        self.assertIsNone(body["token"])
        self.assertEqual(body["learning"], [])
        self.assertTrue(body["today"]["done"])

    def test_repeated_gets_keep_the_same_question(self):
        """원문이 그대로면 GET 을 여러 번 해도 같은 문제다(갈아타기 방어)."""
        first = self.start()
        prompts = {self.get()["question"]["prompt"] for _ in range(6)}
        self.assertEqual(prompts, {first["question"]["prompt"]})

    def test_unreview_then_rereview_before_get_keeps_the_question(self):
        """GET 전에 다시 검수되면 원래 문제가 그대로 나간다."""
        first = self.start()
        source = self.saved()["source_sentence_id"]
        Sentence.objects.filter(pk=source).update(is_reviewed=False)
        Sentence.objects.filter(pk=source).update(is_reviewed=True)

        self.assertEqual(self.get()["question"]["prompt"], first["question"]["prompt"])

    def test_after_replacement_repeated_gets_are_pinned(self):
        """갈아 낸 뒤에는 원래 문장이 다시 검수돼도 새 문제로 고정된다.

        옛 문제로 되돌아가거나 GET 마다 바뀌면 순번 소비 없이 문제를
        고르는 길이 열린다.
        """
        self.start()
        source = self.saved()["source_sentence_id"]
        Sentence.objects.filter(pk=source).update(is_reviewed=False)
        replaced = self.get()["question"]["prompt"]
        Sentence.objects.filter(pk=source).update(is_reviewed=True)

        prompts = {self.get()["question"]["prompt"] for _ in range(5)}
        self.assertEqual(prompts, {replaced})

    def test_answer_saves_the_source_of_the_next_blank(self):
        """답한 뒤 다음 빈칸 문제 저장에도 원문 번호가 들어가고, GET 이 그걸 거른다."""
        first = self.start()
        res = self.client.post(
            ANSWER_URL,
            {"token": first["token"], "choice_id": first["question"]["choices"][0]["id"]},
            "application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        nxt = res.json()["question"]
        self.assertEqual(nxt["kind"], quiz.QuizKind.BLANK)

        source = self.saved()["source_sentence_id"]
        self.assertIsInstance(source, int)
        text = Sentence.objects.get(pk=source).text
        for part in nxt["prompt"].split("____"):
            self.assertIn(part, text)

        Sentence.objects.filter(pk=source).update(is_reviewed=False)
        body = self.get()
        self.assertNotEqual(body["question"]["prompt"], nxt["prompt"])
        self.assert_blank_source_visible(body)

    def test_word_question_saves_no_source(self):
        """빈칸이 아닌 문제는 원문 번호가 None 이다(잘못된 문장을 가리키지 않는다)."""
        self.forced.kind = quiz.QuizKind.MEANING
        self.start()
        self.assertIsNone(self.saved()["source_sentence_id"])


class LegacySavedHttpTest(_HttpBase):
    """source_sentence_id 없이, 또는 망가진 채 저장된 문제."""

    def _rewrite_source(self, **change) -> None:
        study = DailyStudy.objects.get(user=self.user)
        saved = dict(study.question)
        saved.pop("source_sentence_id", None)
        saved.update(change)
        DailyStudy.objects.filter(pk=study.pk).update(question=saved)

    def test_legacy_blank_is_replaced(self):
        """번호 없는 옛 빈칸 문제는 새로 내고, 새 저장본에는 번호가 있다."""
        self.start()
        self._rewrite_source()

        body = self.get()

        self.assertIsNotNone(body["question"])
        self.assertIsInstance(self.saved().get("source_sentence_id"), int)
        self.assert_blank_source_visible(body)

    def test_legacy_blank_is_pinned_after_replacement(self):
        """옛 빈칸을 한 번 갈아 낸 뒤로는 GET 마다 같다."""
        self.start()
        self._rewrite_source()
        prompts = {self.get()["question"]["prompt"] for _ in range(4)}
        self.assertEqual(len(prompts), 1)

    def test_corrupt_source_values_do_not_500(self):
        """번호 칸이 이상한 값이어도 500 이 아니고 새로 낸다."""
        for bad in ["12", True, 3.0, -1, 0, int("9" * 30), [1], {"id": 1}, None]:
            with self.subTest(bad=bad):
                DailyStudy.objects.filter(user=self.user).delete()
                self.start()
                self._rewrite_source(source_sentence_id=bad)

                body = self.get()

                self.assertIsNotNone(body["question"])
                self.assertIsInstance(self.saved().get("source_sentence_id"), int)
                self.assertTrue(
                    Sentence.objects.visible()
                    .filter(pk=self.saved()["source_sentence_id"])
                    .exists()
                )

    def test_source_pointing_to_another_reviewed_sentence_is_kept(self):
        """번호가 가리키는 문장이 검수돼 있으면 그대로 낸다(값이 서버만 쓰는 칸이라)."""
        first = self.start()
        other = Sentence.objects.exclude(pk=self.saved()["source_sentence_id"]).first()
        self._rewrite_source(source_sentence_id=other.pk)
        self.assertEqual(self.get()["question"]["prompt"], first["question"]["prompt"])

    def test_legacy_word_question_is_kept(self):
        """번호 없는 옛 단어 문제는 확인할 원문이 없으니 그대로 낸다."""
        self.forced.kind = quiz.QuizKind.TERM
        first = self.start()
        self._rewrite_source()
        self.assertEqual(self.get()["question"]["prompt"], first["question"]["prompt"])

    def test_legacy_situation_question_is_kept(self):
        """번호 없는 옛 상황 문제도 그대로 낸다."""
        self.forced.kind = quiz.QuizKind.SITUATION
        first = self.start()
        self.assertEqual(first["question"]["kind"], quiz.QuizKind.SITUATION)
        self._rewrite_source()
        self.assertEqual(self.get()["question"]["prompt"], first["question"]["prompt"])


class OtherKindsRegressionHttpTest(_HttpBase):
    """빈칸 외 유형에서 지문 원천의 검수 취소가 여전히 걸린다."""

    def _answer_id(self, token: str) -> int:
        state = daily_study._load(token)["q"]
        for cid in state["c"]:
            graded = quiz.resolve_answer(state, cid)
            if graded is not None and graded[0]:
                return cid
        raise AssertionError("정답이 없다")

    def test_word_kinds_drop_an_unreviewed_answer_word(self):
        """뜻·단어·설명 문제: 정답 단어 검수 취소 -> GET 이 그 지문을 안 준다."""
        for kind in quiz.QuizKind.WORD_KINDS:
            with self.subTest(kind=kind):
                DailyStudy.objects.filter(user=self.user).delete()
                Word.objects.update(is_reviewed=True)
                self.forced.kind = kind
                first = self.start()
                answer = self._answer_id(first["token"])
                Word.objects.filter(pk=answer).update(is_reviewed=False)

                body = self.get()

                self.assertNotEqual(body["question"]["prompt"], first["question"]["prompt"])
                ids = [c["id"] for c in body["question"]["choices"]]
                self.assertNotIn(answer, ids)

    def test_situation_drops_an_unreviewed_answer_sentence(self):
        """상황 문제: 정답 문장 검수 취소 -> GET 이 그 지문을 안 준다."""
        self.forced.kind = quiz.QuizKind.SITUATION
        first = self.start()
        answer = self._answer_id(first["token"])
        Sentence.objects.filter(pk=answer).update(is_reviewed=False)

        body = self.get()

        self.assertIsNotNone(body["question"])
        self.assertNotEqual(body["question"]["prompt"], first["question"]["prompt"])
        self.assertNotIn(answer, [c["id"] for c in body["question"]["choices"]])

    def test_situation_drops_an_unreviewed_distractor(self):
        """상황 문제: 오답 보기 문장 검수 취소도 걸린다(보기 검사 회귀)."""
        self.forced.kind = quiz.QuizKind.SITUATION
        first = self.start()
        answer = self._answer_id(first["token"])
        wrong = next(c["id"] for c in first["question"]["choices"] if c["id"] != answer)
        Sentence.objects.filter(pk=wrong).update(is_reviewed=False)

        body = self.get()

        self.assertIsNotNone(body["question"])
        self.assertNotIn(wrong, [c["id"] for c in body["question"]["choices"]])

    def test_blank_drops_an_unreviewed_choice_word(self):
        """빈칸 문제: 보기 단어 검수 취소는 전처럼 걸린다(원문 검사가 앞 검사를 안 가린다)."""
        first = self.start()
        wrong = first["question"]["choices"][0]["id"]
        Word.objects.filter(pk=wrong).update(is_reviewed=False)

        body = self.get()

        self.assertNotIn(wrong, [c["id"] for c in body["question"]["choices"]])
