"""일일공부 이어 풀기가 빈칸 문제의 원문 문장도 다시 거르는가.

이어 풀기는 저장해 둔 문제를 다시 서명해 준다. 저장한 뒤 검수가 취소될
수 있어 보기를 다시 거르는데(daily_study._hidden_reason), 빈칸 문제는
지문을 따로 문장 하나에서 가져오고 보기는 단어라, 그 문장의 검수가
취소돼도 보기 검사를 통과해 검수 안 된 글이 지문으로 나갔다.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import daily_study
from .models import DailyStudy, StudyLength
from .tests_daily_study import make_user, seed_words


def blank_only(*_args, **_kwargs):
    """출제를 빈칸 문제로 고정한다. 판이 무엇을 낼지 운에 맡기지 않는다."""
    return quiz.make_blank_question(Sentence.objects.visible(), Word.objects.visible())


def situation_only(*_args, **_kwargs):
    """출제를 상황 문제로 고정한다. 지문(정답 문장)이 보기 안에 있는 유형이다."""
    return quiz.make_situation_question(Sentence.objects.visible())


class ResumeBlankSourceTest(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("빈칸원문")
        terms = list(Word.objects.visible().values_list("term", flat=True)[:6])
        for i, term in enumerate(terms):
            Sentence.objects.create(
                text=f"Please run {term} before the release number {i}.",
                translation=f"릴리스 전에 {term} 을 돌려 주세요 {i}",
                context=f"릴리스 준비 {i}",
                is_reviewed=True,
            )

    def _start_on_blank(self) -> tuple[DailyStudy, dict]:
        """빈칸 문제가 저장된 판을 연다. (판, 첫 문제)"""
        with mock.patch.object(daily_study, "make_question", side_effect=blank_only):
            study, _token, question = daily_study.start(self.user, StudyLength.SHORT)
        self.assertEqual(question["kind"], quiz.QuizKind.BLANK)
        study.refresh_from_db()
        return study, question

    def test_the_source_sentence_is_saved_with_the_question(self):
        """저장해 둔 문제에 원문 문장 번호가 있다. 이어 풀 때 다시 보려면 필요하다."""
        study, question = self._start_on_blank()

        source = study.question.get("source_sentence_id")
        self.assertIsInstance(source, int)
        text = Sentence.objects.get(pk=source).text
        # 지문은 그 문장에서 용어 하나를 가린 것이다.
        for part in question["prompt"].split("____"):
            self.assertIn(part, text)

    def test_a_blank_whose_source_was_unreviewed_is_not_handed_out_again(self):
        """원문 문장의 검수가 취소되면 이어 풀기가 그 지문을 다시 내지 않는다."""
        study, question = self._start_on_blank()
        source = study.question["source_sentence_id"]
        Sentence.objects.filter(pk=source).update(is_reviewed=False)

        with mock.patch.object(daily_study, "make_question", side_effect=blank_only):
            resumed = daily_study.resume(study)

        # 검수된 문장이 다섯 남아 있으니 새 빈칸 문제가 나와야 한다. 판이
        # 닫혀 None 이 오면 아래 비교가 아무것도 확인하지 않고 지나간다.
        self.assertIsNotNone(resumed, "새 문제를 못 내고 판이 닫혔다")
        _token, again = resumed
        self.assertNotEqual(again["prompt"], question["prompt"], "검수 취소된 지문을 다시 냈다")
        study.refresh_from_db()
        saved = study.question or {}
        self.assertNotEqual(
            saved.get("source_sentence_id"), source, "검수 취소된 문장이 저장본에 남았다"
        )

    def test_a_still_reviewed_source_keeps_the_same_question(self):
        """원문 문장이 그대로면 같은 문제를 다시 준다(문제 갈아타기를 막는 원래 동작)."""
        study, question = self._start_on_blank()

        _token, again = daily_study.resume(study)

        self.assertEqual(again["prompt"], question["prompt"])

    def test_an_old_saved_blank_without_the_source_is_replaced(self):
        """원문 번호 없이 저장된 옛 빈칸 문제는 확인할 수 없어 새로 낸다."""
        study, question = self._start_on_blank()
        saved = dict(study.question)
        saved.pop("source_sentence_id")
        DailyStudy.objects.filter(pk=study.pk).update(question=saved)
        study.refresh_from_db()

        with mock.patch.object(daily_study, "make_question", side_effect=blank_only):
            resumed = daily_study.resume(study)

        self.assertIsNotNone(resumed)
        study.refresh_from_db()
        self.assertIsInstance(study.question.get("source_sentence_id"), int, "새로 낸 문제에 번호가 없다")

    def test_other_kinds_are_not_affected(self):
        """지문이 보기 안에 있는 유형은 원문 번호가 없어도 그대로 다시 낸다."""
        with mock.patch.object(daily_study, "make_question", side_effect=situation_only):
            study, _token, question = daily_study.start(self.user, StudyLength.SHORT)
        self.assertEqual(question["kind"], quiz.QuizKind.SITUATION)
        study.refresh_from_db()
        self.assertIsNone(study.question["source_sentence_id"])

        _token, again = daily_study.resume(study)

        self.assertEqual(again["prompt"], question["prompt"])

    def test_a_situation_whose_answer_sentence_was_unreviewed_is_replaced(self):
        """상황 문제는 지문=정답 문장이 보기에 있어 보기 검사로 걸린다."""
        with mock.patch.object(daily_study, "make_question", side_effect=situation_only):
            study, _token, question = daily_study.start(self.user, StudyLength.SHORT)
        Sentence.objects.filter(text=question["prompt"]).update(is_reviewed=False)

        with mock.patch.object(daily_study, "make_question", side_effect=situation_only):
            resumed = daily_study.resume(study)

        self.assertIsNotNone(resumed)
        self.assertNotEqual(resumed[1]["prompt"], question["prompt"])
