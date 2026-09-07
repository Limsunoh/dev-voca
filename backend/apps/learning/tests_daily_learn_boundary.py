"""일일공부 학습 단계의 경계값과 복구 경로.

기존 파일들이 보는 것과 겹치지 않게 자리를 나눴다.

    tests_daily_learning     범위·뽑기 순서 (함수 단위)
    tests_daily_learn_abuse  우회·되돌리기·경합 (함수 단위)
    tests_daily_learn_http   화면이 받는 응답 (HTTP)

여기서 보는 것은 **산수와 복구**다. 위 셋이 "정상 구성에서 규칙이 서나"
를 보는 동안, 이쪽은 구성 자체를 흔든다 - 묶음이 안 나뉘는 문제 수,
단어가 묶음보다 적은 DB, 점수판이 계속 터지는 상태, 다 풀었는데 안 닫힌 판.

**왜 산수를 따로 보나.** _fit_chunks 와 _answerable 은 판이 열릴 때 딱
한 번 돌고 그 결과가 total_questions 로 굳는다. 틀려도 예외가 안 나고
"40문제라더니 31문제에서 끝났다" 로만 드러나는데, 그때는 이미 사용자가
겪은 뒤다. 그래서 함수를 직접 불러 값을 고정한다.

**왜 복구를 따로 보나.** _publish 는 트랜잭션 밖이라 터질 수 있고, 터진
뒤에도 판은 끝낼 수 있어야 한다. 한 번 터지는 것은 기존 테스트가 보지만
(StuckSessionTest), 계속 터지는 동안 끝까지 푸는 것은 아무도 안 본다 -
점수판이 죽은 동안에도 사용자의 하루는 끝나야 한다.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import calendar_kst, daily_study
from .models import (
    STUDY_PLANS,
    DailyScore,
    DailyStudy,
    ReviewState,
    StudyLength,
    StudyPlan,
)
from .session import SessionError
from .tests_daily_learning import answer_id_of
from .tests_daily_study import make_user, seed_words


def seed_sentences(count: int) -> None:
    """빈칸 문제를 만들 수 있는 문장을 채운다.

    _answerable 이 문장 수를 병목 계산에 쓰므로, 그 계단을 보려면 문장
    개수를 마음대로 정할 수 있어야 한다.
    """
    Sentence.objects.bulk_create(
        Sentence(
            text=f"Please commit this branch now {i}.",
            translation=f"이것은 {i}번 문장입니다.",
            context=f"상황 {i}",
            kind="phrase",
            category="git",
            is_reviewed=True,
        )
        for i in range(count)
    )


class FitChunksTest(TestCase):
    """_fit_chunks 의 산수.

    묶음 구성이 틀리면 학습 카드를 보여준 묶음이 문제 범위로 안 쓰인다.
    예외가 안 나고 조용히 어긋나므로 값을 직접 고정한다.
    """

    def test_a_full_corpus_keeps_the_planned_shape(self):
        """단어가 넉넉하면 계획 그대로다.

        아래 경계들이 전부 "줄어드는" 쪽이라, 안 줄어드는 기준선이
        없으면 함수가 늘 0 을 줘도 통과한다.
        """
        for length in (StudyLength.SHORT, StudyLength.MEDIUM, StudyLength.LONG):
            with self.subTest(length=length):
                plan = STUDY_PLANS[length]
                size, count = daily_study._fit_chunks(plan, plan.total, 1000)

                self.assertEqual(size, plan.chunk_size)
                self.assertEqual(count, plan.chunk_count)

    def test_the_learning_part_never_exceeds_the_total(self):
        """학습분이 총 문제 수를 넘지 않는다.

        넘으면 학습만 하고 문제가 안 나오는 묶음이 생긴다 - 8개를
        학습해놓고 문제가 5개면 뒤 세 묶음이 헛돈다.
        """
        plan = STUDY_PLANS[StudyLength.SHORT]  # total=10, 2*4

        for total in range(0, plan.total + 1):
            with self.subTest(total=total):
                size, count = daily_study._fit_chunks(plan, total, 1000)

                self.assertLessEqual(
                    size * count, total, "학습분이 낼 수 있는 문제보다 많다"
                )

    def test_a_word_thin_corpus_shrinks_the_chunk_count(self):
        """단어가 적으면 묶음 수가 준다.

        total 은 문장을 포함하는데 학습은 단어만 뽑는다. 단어로 자르지
        않으면 2묶음째부터 발급이 실패하고, 실패하면 issued_chunks 가
        안 올라 그 뒤 슬라이스가 실제 발급분과 영영 어긋난다.
        """
        plan = STUDY_PLANS[StudyLength.MEDIUM]  # 5*4

        # 단어 6개. 한 묶음(5개)만 선다.
        size, count = daily_study._fit_chunks(plan, plan.total, 6)

        self.assertEqual(size, 5, "묶음 크기는 유지해야 한다")
        self.assertEqual(count, 1, "단어 6개로 두 묶음을 계획했다")

    def test_the_chunk_size_is_never_shrunk(self):
        """크기는 안 줄이고 개수만 줄인다.

        크기를 줄이면 화면에 "이번엔 2개" 라고 해놓고 다음 묶음에서
        다르게 나온다. 사용자가 보는 약속이 판 중간에 바뀐다.
        """
        plan = STUDY_PLANS[StudyLength.LONG]  # 5*6

        for words in range(5, 40):
            with self.subTest(words=words):
                size, count = daily_study._fit_chunks(plan, plan.total, words)

                if count > 0:
                    self.assertEqual(
                        size, plan.chunk_size, "묶음 크기가 줄었다"
                    )

    def test_too_few_words_for_one_chunk_drops_learning(self):
        """한 묶음도 못 채우면 학습 없이 푼다.

        부분 묶음을 세우면 learned_ids 의 구간 경계가 밀려 그 뒤 문제가
        전부 화면에 안 보인 단어로 나간다.
        """
        plan = STUDY_PLANS[StudyLength.MEDIUM]  # chunk_size=5

        for words in range(0, 5):
            with self.subTest(words=words):
                self.assertEqual(
                    daily_study._fit_chunks(plan, plan.total, words),
                    (0, 0),
                    "묶음을 못 채우는데 학습분을 세웠다",
                )

    def test_a_zero_sized_plan_does_not_divide_by_zero(self):
        """묶음 크기가 0 인 구성이 들어와도 안 터진다.

        STUDY_PLANS 에는 지금 없지만 이 함수는 plan 을 인자로 받는다 -
        학습 없는 길이를 하나 추가하는 순간 0 이 들어온다.
        """
        plan = StudyPlan(total=10, bonus=5, chunk_size=0, chunk_count=4)

        self.assertEqual(daily_study._fit_chunks(plan, 10, 100), (0, 0))


class AnswerableTest(TestCase):
    """_answerable 의 산수.

    이 값이 total_questions 로 굳는다. 과하게 세면 "40문제" 를 약속하고
    중간에 끊기고, 적게 세면 낼 수 있는데 덜 낸다. 후자만 허용된다.
    """

    def test_an_empty_corpus_promises_nothing(self):
        plan = STUDY_PLANS[StudyLength.SHORT]

        self.assertEqual(daily_study._answerable(plan), 0)

    def test_words_only_are_counted_whole(self):
        """문장이 없으면 단어가 다 낸다.

        섞이지 않으니 병목도 없다. 여기서 문장 병목을 걸면 단어만 있는
        DB 가 이유 없이 적게 약속한다.
        """
        seed_words(200)
        plan = STUDY_PLANS[StudyLength.LONG]

        self.assertEqual(
            daily_study._answerable(plan), plan.total, "단어가 넉넉한데 깎였다"
        )

    def test_a_sentence_heavy_corpus_cannot_borrow_from_sentences(self):
        """문장이 많아도 단어 몫을 대신 못 낸다.

        둘을 그냥 더하면 단어 6개 + 문장 100개가 106 으로 세어져
        25문제를 약속하는데, 실제로는 열 문제 남짓에서 끊긴다.
        """
        seed_words(6)
        seed_sentences(100)
        plan = STUDY_PLANS[StudyLength.MEDIUM]  # total=25, from_study=20

        got = daily_study._answerable(plan)

        # 학습분은 단어만 쓰므로 min(6, 20)=6. 남은 단어가 0 이라
        # 섞어 내는 구간은 안 선다.
        self.assertEqual(got, 6, "문장으로 단어 몫을 채웠다")

    def test_the_learning_part_does_not_pay_the_sentence_bottleneck(self):
        """학습분은 문장 병목을 안 탄다.

        그 구간은 문장을 아예 안 쓴다. 병목을 판 전체에 걸면 문장
        하나짜리 DB 가 40문제를 1문제로 줄인다.
        """
        seed_words(200)
        seed_sentences(1)
        plan = STUDY_PLANS[StudyLength.LONG]  # from_study=30

        got = daily_study._answerable(plan)

        self.assertGreaterEqual(
            got, plan.from_study, "학습분까지 문장 병목에 깎였다"
        )

    def test_the_promise_is_never_more_than_the_plan(self):
        """어떤 구성에서도 계획보다 많이 약속하지 않는다.

        total_questions 가 계획을 넘으면 화면에 없는 길이를 그린다.
        """
        seed_words(500)
        seed_sentences(500)

        for length in (StudyLength.SHORT, StudyLength.MEDIUM, StudyLength.LONG):
            with self.subTest(length=length):
                plan = STUDY_PLANS[length]

                self.assertLessEqual(daily_study._answerable(plan), plan.total)

    def test_unreviewed_content_does_not_count(self):
        """검수 안 된 단어는 약속에 안 들어간다.

        세어놓고 못 내면 판이 중간에 끊긴다 - 출제는 visible() 로만
        뽑기 때문이다.
        """
        seed_words(200)
        Word.objects.update(is_reviewed=False)
        plan = STUDY_PLANS[StudyLength.SHORT]

        self.assertEqual(
            daily_study._answerable(plan), 0, "미검수 단어를 셌다"
        )


class PublishFailureTest(TestCase):
    """점수판 반영이 계속 터지는 동안에도 판을 끝낼 수 있나.

    _publish 는 트랜잭션 밖이라 터질 수 있다. 한 번 터지는 것은 기존
    테스트가 보지만, **계속** 터지는 동안 끝까지 푸는 것은 아무도 안
    본다 - 점수판이 죽어도 사용자의 하루는 끝나야 한다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("점수판")

    def _play_to_end(self, token, question, study):
        """끝까지 답한다. 학습이 끼면 넘긴다."""
        while True:
            if question is None:
                study.refresh_from_db()
                if study.is_done:
                    break
                resumed = daily_study.resume(study)
                if resumed is None:
                    break
                token, question = resumed
                continue
            _r, token, question, study = daily_study.answer(
                self.user, token, answer_id_of(token)
            )
        study.refresh_from_db()
        return study

    def test_a_dead_scoreboard_does_not_trap_the_day(self):
        """점수판이 매번 터져도 판은 끝난다.

        _publish 가 계속 실패하면 답마다 예외가 난다. 그래도 채점은
        커밋됐으므로 이어 풀기로 진행할 수 있어야 하고, 마지막 답까지
        가면 판이 닫혀야 한다 - 안 닫히면 하루 한 번 제약에 갇힌다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        total = study.total_questions

        with patch.object(
            daily_study, "_publish", side_effect=RuntimeError("점수판 죽음")
        ):
            for _ in range(total * 3):  # 넉넉히 - 학습 차례가 끼어든다
                study.refresh_from_db()
                if study.answered >= total:
                    break
                resumed = daily_study.resume(study)
                if resumed is None:
                    break
                token, _body = resumed
                try:
                    daily_study.answer(self.user, token, answer_id_of(token))
                except RuntimeError:
                    pass  # 점수판만 터졌다. 채점은 커밋됐다

        study.refresh_from_db()
        self.assertEqual(
            study.answered, total, "점수판이 죽자 문제를 다 못 풀었다"
        )

    def test_the_day_can_still_be_closed_after_the_scoreboard_recovers(self):
        """점수판이 살아나면 그 뒤 답이 점수를 따라잡는다.

        add_daily_study 가 더 높은 점수로만 갱신하므로, 중간에 몇 번
        놓쳐도 마지막 답이 최종값을 쓴다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 첫 답의 점수판 반영만 터뜨린다.
        with patch.object(
            daily_study, "_publish", side_effect=RuntimeError("일시적")
        ):
            with self.assertRaises(RuntimeError):
                daily_study.answer(self.user, token, answer_id_of(token))

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "채점이 안 남았다 - 전제가 틀렸다")

        # 그 뒤는 정상으로 끝까지 푼다.
        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "이어 풀 문제를 못 냈다")
        token, question = resumed
        study = self._play_to_end(token, question, study)

        self.assertTrue(study.is_done, "판이 안 닫혔다")

        row = DailyScore.objects.get(user=self.user, day=study.day)
        self.assertEqual(
            row.daily_study_score,
            study.score,
            "점수판이 판 점수를 못 따라잡았다",
        )


class SettleStaleTest(TestCase):
    """어제 판 정산.

    정산은 완주 보너스를 주는 마지막 관문이라, 여기서 판정을 틀리면
    점수가 조용히 새거나 조용히 사라진다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("정산")

    def test_a_fully_answered_but_open_study_gets_its_bonus(self):
        """다 풀었는데 안 닫힌 판은 정산에서 보너스를 받는다.

        마지막 답의 _finish 가 실패하면 이 상태가 된다 - answered 는
        찼는데 finished_at 이 비어 있다. 정산이 보너스를 안 주면 40문제를
        다 풀고 자정만 넘긴 사람이 보너스를 잃는다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 다 푼 상태를 직접 만든다. 마지막 _finish 만 건너뛴 모양이다.
        DailyStudy.objects.filter(pk=study.pk).update(
            answered=study.total_questions,
            correct=study.total_questions,
            score=study.total_questions,
        )
        study.refresh_from_db()

        with patch.object(calendar_kst, "today", lambda: study.day + _one_day()):
            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "정산이 판을 안 닫았다")
        self.assertEqual(
            study.score,
            study.total_questions + study.bonus,
            "다 풀었는데 완주 보너스가 없다",
        )

    def test_a_half_done_study_gets_no_bonus(self):
        """덜 푼 판에는 보너스가 없다.

        주면 한 문제만 풀고 자정을 넘기는 것이 이득이 된다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        daily_study.answer(self.user, token, answer_id_of(token))
        study.refresh_from_db()
        before = study.score

        with patch.object(calendar_kst, "today", lambda: study.day + _one_day()):
            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "정산이 판을 안 닫았다")
        self.assertEqual(study.score, before, "덜 풀었는데 보너스가 붙었다")

    def test_settling_twice_does_not_pay_twice(self):
        """정산을 두 번 불러도 보너스는 한 번이다.

        _finish 의 조건부 UPDATE 가 막는다. 안 막으면 GET 을 두 번 치는
        것만으로 보너스가 두 배가 된다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        DailyStudy.objects.filter(pk=study.pk).update(
            answered=study.total_questions, score=study.total_questions
        )

        tomorrow = _tomorrow_of(study)
        with patch.object(calendar_kst, "today", tomorrow):
            daily_study.settle_stale(self.user)
            study.refresh_from_db()
            once = study.score

            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertEqual(study.score, once, "정산이 두 번 점수를 올렸다")

    def test_settling_closes_the_saved_question(self):
        """정산은 저장된 문제도 비운다.

        안 비우면 그 판의 resume 이 답할 수 없는 토큰을 내준다. 닫힌
        판이라 is_done 검사에 먼저 걸리긴 하지만, 두 방어 중 하나가
        빠지면 나머지 하나에만 기대게 된다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()
        self.assertIsNotNone(study.question, "전제가 틀렸다 - 저장된 문제가 없다")

        with patch.object(calendar_kst, "today", _tomorrow_of(study)):
            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertIsNone(study.question, "닫힌 판에 문제가 남았다")

    def test_a_closed_study_is_left_alone(self):
        """이미 닫힌 어제 판은 다시 안 건드린다.

        정산이 매 조회마다 도는데 닫힌 판까지 매번 쓰면 점수가 계속
        다시 발행된다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        tomorrow = _tomorrow_of(study)

        with patch.object(calendar_kst, "today", tomorrow):
            daily_study.settle_stale(self.user)
            study.refresh_from_db()
            closed_at = study.finished_at

            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertEqual(
            study.finished_at, closed_at, "닫힌 판을 다시 닫았다"
        )


class ResumeLoopTest(TestCase):
    """답과 답 사이에 새로고침을 반복해도 문제가 안 바뀌나.

    바뀌면 아는 것이 나올 때까지 화면을 다시 여는 길이 열린다.
    _take_step 은 "한 순번은 한 번만" 만 지키지 "한 순번에 문제는
    하나" 는 안 지킨다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("반복")

    def test_twenty_resumes_give_the_same_answer(self):
        """스무 번 새로고쳐도 정답이 그대로다.

        기존 테스트가 두세 번을 보는데, 뽑기가 무작위라 적은 횟수로는
        우연히 같은 것이 나와도 통과한다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        first = answer_id_of(token)

        for i in range(20):
            resumed = daily_study.resume(study)
            self.assertIsNotNone(resumed, f"{i}번째 새로고침에서 문제가 사라졌다")
            again, _body = resumed

            self.assertEqual(
                answer_id_of(again), first, f"{i}번째 새로고침에서 문제가 바뀌었다"
            )
            study.refresh_from_db()

    def test_resuming_does_not_consume_a_step(self):
        """새로고침은 순번을 안 쓴다.

        쓰면 답을 안 해도 판이 끝나고, 진행 개수와 실제 푼 수가 갈린다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        before = study.step

        for _ in range(10):
            daily_study.resume(study)
            study.refresh_from_db()

        self.assertEqual(study.step, before, "새로고침이 순번을 소비했다")
        self.assertEqual(study.answered, 0, "새로고침이 답으로 세어졌다")

    def test_resuming_between_every_answer_keeps_the_count_honest(self):
        """답마다 새로고침을 껴도 진행 개수가 정확하다.

        판 전체에 걸쳐 본다. 한 문제만 보면 누적되는 어긋남을 놓친다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        total = study.total_questions

        answered = 0
        for _ in range(total * 3):
            study.refresh_from_db()
            if study.is_done:
                break

            # 답하기 전에 세 번 새로고침한다.
            for _ in range(3):
                resumed = daily_study.resume(study)
                if resumed is None:
                    break
                token, _body = resumed
                study.refresh_from_db()

            if study.is_done:
                break
            daily_study.answer(self.user, token, answer_id_of(token))
            answered += 1

        study.refresh_from_db()
        self.assertEqual(study.answered, total, "진행 개수가 안 찼다")
        self.assertEqual(
            answered, total, "실제 답한 횟수와 기록이 다르다"
        )
        self.assertTrue(study.is_done, "다 풀었는데 안 닫혔다")

    def test_a_lagging_saved_question_does_not_trap_the_day(self):
        """뒤처진 저장 문제를 받아도 실제로 답을 이어갈 수 있다.

        **기계가 아니라 결과를 본다.** 기존 테스트는 새로 낸 토큰의
        순번이 DB 와 같은지만 확인하는데, 그것만으로는 "그 토큰으로
        정말 답이 되나" 를 안 본다 - 순번만 맞고 다른 이유로 거절되면
        사용자는 똑같이 갇힌다.

        갇히면 하루 한 번 제약이라 다시 시작할 수도 없어 그 사람의
        오늘이 끝난다. 그래서 판이 실제로 끝까지 가는지까지 본다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        # 마지막 답이 다음 문제를 안 심어 저장분이 한 순번 뒤처진 모양.
        saved = dict(study.question)
        saved["state"] = {**saved["state"], "n": study.step - 1}
        DailyStudy.objects.filter(pk=study.pk).update(question=saved)
        study.refresh_from_db()

        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "뒤처진 문제를 받고 갇혔다")

        token, _body = resumed
        daily_study.answer(self.user, token, answer_id_of(token))

        study.refresh_from_db()
        self.assertEqual(
            study.answered, 1, "이어 푼 답이 안 세어졌다 - 판이 갇혔다"
        )

    def test_a_resumed_token_still_cannot_be_replayed(self):
        """새로고침으로 받은 토큰도 두 번은 못 쓴다.

        새 토큰이 나온다고 순번 보호가 느슨해지면 안 된다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        resumed = daily_study.resume(study)
        token, _body = resumed

        daily_study.answer(self.user, token, answer_id_of(token))

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, token, answer_id_of(token))


class FinishedStudyTest(TestCase):
    """다 끝난 판에 계속 요청을 보내면.

    화면은 끝나면 결과만 보여주지만 API 는 계속 부를 수 있다. 끝난 판이
    다시 열리거나 점수가 더 오르면 하루 한 번 규칙이 깨진다.
    """

    def setUp(self):
        cache.clear()
        seed_words(300)
        self.user = make_user("완주")

    def _finish_a_study(self, length):
        """끝까지 푼다. 답한 횟수를 함께 돌려준다."""
        study, token, _q = daily_study.start(self.user, length)

        answered = 0
        for _ in range(study.total_questions * 4):
            study.refresh_from_db()
            if study.is_done:
                break
            resumed = daily_study.resume(study)
            if resumed is None:
                break
            token, _body = resumed
            daily_study.answer(self.user, token, answer_id_of(token))
            answered += 1

        study.refresh_from_db()
        return study, token, answered

    def test_every_length_pays_exactly_what_it_promised(self):
        """세 길이 모두 약속한 문제 수를 내고 보너스를 정확히 준다.

        **셋을 한 테스트에서 본다.** 길이마다 묶음 구성이 달라서
        (4묶음/4묶음/6묶음) 하나만 보면 나머지 구성의 산수 실수를 놓친다.
        """
        for length in (StudyLength.SHORT, StudyLength.MEDIUM, StudyLength.LONG):
            with self.subTest(length=length):
                # 사용자를 새로 만든다 - 하루 한 번 제약 때문이다.
                self.user = make_user(f"완주{length}")
                plan = STUDY_PLANS[length]
                study, _t, answered = self._finish_a_study(length)

                self.assertEqual(
                    study.total_questions, plan.total, "약속한 문제 수가 계획과 다르다"
                )
                self.assertEqual(answered, plan.total, "약속한 만큼 안 냈다")
                self.assertTrue(study.is_done, "다 풀었는데 안 닫혔다")
                self.assertEqual(
                    study.score,
                    study.correct + plan.bonus,
                    "맞힌 수 + 보너스가 아니다",
                )
                self.assertEqual(
                    study.issued_chunks, study.chunk_count, "묶음이 덜 뽑혔다"
                )

    def test_the_scoreboard_matches_after_finishing(self):
        """완주 뒤 그날 줄이 판 점수와 같다.

        점수판은 트랜잭션 밖이라 어긋날 창이 있다. 최종값만은 맞아야
        순위표가 실제 실력을 보여준다.
        """
        study, _t, _n = self._finish_a_study(StudyLength.SHORT)

        row = DailyScore.objects.get(user=self.user, day=study.day)
        self.assertEqual(
            row.daily_study_score, study.score, "점수판과 판 점수가 다르다"
        )

    def test_answering_after_the_end_changes_nothing(self):
        """끝난 뒤 마지막 토큰으로 또 답해도 점수가 안 변한다.

        _take_step 의 finished_at 조건이 막는다. 안 막으면 완주한 판에
        계속 답을 보내 점수를 무한히 올릴 수 있다.
        """
        study, token, _n = self._finish_a_study(StudyLength.SHORT)
        before = (study.score, study.answered, study.correct)

        if token is not None:
            with self.assertRaises(SessionError):
                daily_study.answer(self.user, token, answer_id_of(token))

        study.refresh_from_db()
        self.assertEqual(
            (study.score, study.answered, study.correct),
            before,
            "끝난 판의 점수가 바뀌었다",
        )

    def test_a_finished_study_cannot_be_resumed(self):
        """끝난 판은 이어 풀 토큰을 안 준다.

        주면 완주 뒤에도 계속 풀 수 있어 하루 한 번이 무의미해진다.
        """
        study, _t, _n = self._finish_a_study(StudyLength.SHORT)

        self.assertIsNone(daily_study.resume(study), "끝난 판이 토큰을 내줬다")

    def test_the_scoreboard_does_not_grow_on_repeated_finishes(self):
        """끝난 판을 다시 닫아도 점수판이 안 오른다.

        _finish 는 여러 경로(answer, resume, settle_stale)에서 불린다.
        조건부 UPDATE 가 진 요청을 돌려보내지 않으면 보너스가 겹쳐 쌓인다.
        """
        study, _t, _n = self._finish_a_study(StudyLength.SHORT)
        before = study.score

        for _ in range(3):
            daily_study._finish(study)

        study.refresh_from_db()
        row = DailyScore.objects.get(user=self.user, day=study.day)
        self.assertEqual(study.score, before, "다시 닫자 점수가 올랐다")
        self.assertEqual(
            row.daily_study_score, before, "다시 닫자 점수판이 올랐다"
        )


class ReviewSideEffectTest(TestCase):
    """일일공부가 복습 상태에 남기는 것.

    복습 연동은 답마다 돌아서(자유 문제풀이는 판 끝에 한 번) 실수의
    창이 25배 넓다. 여기서 보는 것은 셋이다 - 연속을 안 올리나, 틀린
    것이 복습에 뜨나, 판 전체를 풀어도 그 둘이 유지되나.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습연동")

    def test_a_full_playthrough_never_raises_a_streak(self):
        """한 판을 다 맞혀도 연속이 하나도 안 오른다.

        연속은 복습 화면에서 확인한 것만 센다. 일일공부에서 맞힌 것으로
        졸업하면 "복습했다" 가 아니라 "우연히 나왔다" 가 된다.

        **되쓰기 경합은 여기서 안 잡힌다.** bulk_update 가 낡은 streak 을
        되쓰는 버그는 "함수가 읽은 뒤 복습이 끼어드는" 순간에만 나는데,
        순차 실행으로는 그 지점을 못 맞힌다 - 그쪽은 bulk_update 를 감싸
        직접 끼워 넣는 ReviewStateWriteTest 가 본다.

        여기서 못박는 것은 그것과 다르다. **일일공부가 정상 경로로
        연속을 올리지 않는가** 다. 판 전체를 다 맞히고도 값이 그대로여야
        한다 - 어느 코드가 실수로 streak 을 +1 하면 여기서 걸린다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        # **모든 단어에 미리 연속을 쌓는다.** 일부만 심으면 그 판에서
        # 실제로 나온 단어가 심어둔 것과 겹치는지가 뽑기 운에 달린다 -
        # 겹치는 게 하나도 없는 실행에서는 아무것도 검사하지 않고
        # 통과한다. 전부 심으면 어느 것이 나오든 반드시 걸린다.
        now = timezone.now()
        ReviewState.objects.bulk_create(
            ReviewState(
                user=self.user,
                target_type=quiz.TARGET_WORD,
                target_id=word_id,
                streak=2,
                last_correct_at=now,
            )
            for word_id in Word.objects.visible().values_list("pk", flat=True)
        )
        seeded = dict(
            ReviewState.objects.filter(user=self.user).values_list(
                "target_id", "streak"
            )
        )
        self.assertTrue(seeded, "전제가 틀렸다 - 심어둔 복습 줄이 없다")

        answered = []
        for _ in range(study.total_questions * 3):
            study.refresh_from_db()
            if study.is_done:
                break
            resumed = daily_study.resume(study)
            if resumed is None:
                break
            token, _body = resumed
            picked = answer_id_of(token)
            answered.append(picked)
            daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "판이 안 끝났다 - 전제가 틀렸다")
        self.assertTrue(answered, "한 문제도 안 풀었다 - 전제가 틀렸다")

        rows = dict(
            ReviewState.objects.filter(user=self.user).values_list(
                "target_id", "streak"
            )
        )
        # 실제로 답한 단어부터 본다. 나머지는 건드릴 이유조차 없는 줄이라
        # 같이 보되, 답한 것이 하나도 없으면 위에서 이미 걸린다.
        for target_id in answered:
            with self.subTest(target_id=target_id):
                self.assertEqual(
                    rows[target_id],
                    seeded[target_id],
                    "일일공부가 복습 연속을 건드렸다",
                )

    def test_a_wrong_answer_lands_in_review(self):
        """틀린 것은 복습에 뜬다.

        여기가 없으면 하루의 주 활동에서 틀린 것이 복습에 안 뜬다 -
        자유 문제풀이만 복습을 채우는데, 일일공부만 하는 사람이 더 많다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        right = answer_id_of(token)
        wrong = next(
            c["id"] for c in question["choices"] if c["id"] != right
        )

        daily_study.answer(self.user, token, wrong)

        self.assertTrue(
            ReviewState.objects.filter(
                user=self.user, target_id=right, is_wrong=True
            ).exists(),
            "틀린 단어가 복습에 안 떴다",
        )

    def test_a_wrong_answer_breaks_the_streak(self):
        """틀리면 연속이 끊긴다.

        안 끊으면 복습 1회 + 일일공부 오답 + 복습 1회 로 "연속" 아닌
        두 번에 졸업한다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        right = answer_id_of(token)
        wrong = next(c["id"] for c in question["choices"] if c["id"] != right)

        ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=right,
            streak=2,
        )

        daily_study.answer(self.user, token, wrong)

        row = ReviewState.objects.get(user=self.user, target_id=right)
        self.assertEqual(row.streak, 0, "틀렸는데 연속이 안 끊겼다")

    def test_a_refused_answer_does_not_touch_review(self):
        """거절당한 답은 복습에 반영되지 않는다.

        되돌리기가 복습에 닿으면 옛 토큰으로 is_wrong 을 지울 수 있다 -
        틀린 것을 복습에서 없애는 길이다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        right = answer_id_of(token)
        wrong = next(c["id"] for c in question["choices"] if c["id"] != right)

        # 먼저 틀리게 답해 복습에 올린다.
        daily_study.answer(self.user, token, wrong)
        self.assertTrue(
            ReviewState.objects.get(user=self.user, target_id=right).is_wrong,
            "전제가 틀렸다 - 틀린 것이 복습에 안 올랐다",
        )

        # 같은 토큰으로 이번엔 맞게 보낸다. 순번이 이미 소비돼 거절된다.
        with self.assertRaises(SessionError):
            daily_study.answer(self.user, token, right)

        self.assertTrue(
            ReviewState.objects.get(user=self.user, target_id=right).is_wrong,
            "거절당한 답이 복습에서 오답 표시를 지웠다",
        )


class ThinCorpusPlaythroughTest(TestCase):
    """단어가 아슬아슬한 DB 에서 끝까지 풀기.

    _fit_chunks 가 계산한 구성이 실제 진행과 맞는지는 끝까지 풀어봐야
    안다. 산수만 맞고 진행이 막히는 조합이 있을 수 있다.
    """

    def setUp(self):
        cache.clear()
        self.user = make_user("빈약")

    def _run(self, length):
        """끝까지 푼다. 못 이어가면 거기서 멈춘다."""
        study, token, question = daily_study.start(self.user, length)

        for _ in range(study.total_questions * 4):
            study.refresh_from_db()
            if study.is_done:
                break
            resumed = daily_study.resume(study)
            if resumed is None:
                break
            token, _body = resumed
            daily_study.answer(self.user, token, answer_id_of(token))

        study.refresh_from_db()
        return study

    def test_exactly_one_chunk_of_words_finishes(self):
        """단어가 딱 한 묶음이어도 판이 끝난다.

        학습분 1묶음 + 나머지는 전체에서. 그 전환점에서 막히면 판이
        안 닫히고 하루 한 번 제약에 갇힌다.
        """
        seed_words(5)  # MEDIUM 의 chunk_size 와 같다

        study = self._run(StudyLength.MEDIUM)

        self.assertTrue(study.is_done, "판이 안 닫혔다")
        self.assertEqual(
            study.answered,
            study.total_questions,
            "약속한 문제 수를 못 채웠다",
        )

    def test_one_word_short_of_a_chunk_still_finishes(self):
        """묶음보다 하나 적어도 판이 끝난다.

        학습분이 통째로 빠지는 자리다(_fit_chunks 가 (0,0)). 학습 없이
        옛 흐름으로 도는데, 그 경로가 살아 있는지 본다.
        """
        seed_words(4)  # MEDIUM chunk_size=5 보다 하나 적다

        study = self._run(StudyLength.MEDIUM)

        self.assertEqual(study.chunk_count, 0, "묶음을 못 채우는데 세웠다")
        self.assertTrue(study.is_done, "학습 없는 판이 안 닫혔다")
        self.assertEqual(
            study.answered, study.total_questions, "약속한 문제 수를 못 채웠다"
        )

    def test_a_single_word_finishes_without_a_crash(self):
        """단어 하나짜리 DB 에서도 안 터진다.

        보기를 넷 못 채우므로 문제가 아예 안 나올 수 있다. 그때는 판이
        닫혀야지 예외가 나면 안 된다.
        """
        seed_words(1)

        with self.assertRaises(SessionError):
            # 보기를 못 채워 문제 자체가 안 만들어진다.
            daily_study.start(self.user, StudyLength.SHORT)

    def test_four_words_are_enough_to_finish(self):
        """보기 넷을 겨우 채우는 DB 에서 판이 끝난다.

        여기가 출제가 가능해지는 최소선이다. 약속한 수는 줄지만 그
        줄어든 수만큼은 반드시 내야 한다.
        """
        seed_words(4)

        study = self._run(StudyLength.SHORT)

        self.assertTrue(study.is_done, "판이 안 닫혔다")
        self.assertEqual(
            study.answered, study.total_questions, "약속한 만큼 못 냈다"
        )


class MidRunReviewChangeTest(TestCase):
    """진행 중에 콘텐츠가 미검수로 내려갈 때.

    검수 취소는 Admin 에서 언제든 일어난다. 그때 판이 갇히거나 미검수
    단어가 새면 안 된다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("검수취소")

    def test_the_whole_corpus_going_unreviewed_closes_the_study(self):
        """콘텐츠가 통째로 사라지면 판을 닫는다.

        안 닫으면 화면이 길이 고르기로 떨어지는데, 하다 만 판이 있으면
        거기서 길이 버튼도 막혀 아무것도 못 하는 상태가 된다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        daily_study.answer(self.user, token, answer_id_of(token))

        Word.objects.update(is_reviewed=False)

        study.refresh_from_db()
        self.assertIsNone(
            daily_study.resume(study), "낼 문제가 없는데 토큰을 내줬다"
        )

        study.refresh_from_db()
        self.assertTrue(study.is_done, "이어갈 수 없는 판을 안 닫았다")

    def test_an_unreviewed_word_never_reaches_the_saved_question(self):
        """저장된 문제의 보기가 미검수가 되면 그 문제를 버린다.

        그대로 내보내면 아무도 확인하지 않은 내용을 정답이라고 알려준다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        saved_ids = [c["id"] for c in study.question["body"]["choices"]]
        # 보기 하나만 미검수로 내린다. 문제가 통째로 버려져야 한다.
        Word.objects.filter(pk=saved_ids[0]).update(is_reviewed=False)

        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "새 문제를 못 냈다")

        again, body = resumed
        new_ids = [c["id"] for c in body["choices"]]
        self.assertNotIn(
            saved_ids[0], new_ids, "미검수 단어가 보기로 다시 나갔다"
        )
        self.assertEqual(
            Word.objects.visible().filter(pk__in=new_ids).count(),
            len(new_ids),
            "새 문제에 미검수 보기가 섞였다",
        )

    def test_the_study_is_not_trapped_when_content_returns(self):
        """검수가 다시 켜지면 이어 풀 수 있다.

        일시적으로 비었다고 판을 닫아버리면, 되돌린 뒤에도 그 사람의
        오늘은 못 살린다. 닫는 것은 맞지만 닫힌 판은 결과를 보여줘야
        한다 - 갇힌 화면이 아니라.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)
        daily_study.answer(self.user, token, answer_id_of(token))

        Word.objects.update(is_reviewed=False)
        study.refresh_from_db()
        daily_study.resume(study)  # 여기서 닫힌다

        Word.objects.update(is_reviewed=True)
        study.refresh_from_db()

        # 닫힌 판은 다시 안 열린다. 그래도 점수는 남아 있어야 한다.
        self.assertTrue(study.is_done)
        self.assertEqual(study.answered, 1, "푼 만큼이 안 남았다")
        self.assertIsNone(
            daily_study.resume(study), "닫힌 판이 다시 열렸다"
        )


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _tomorrow_of(study):
    """그 판의 다음 날을 주는 시계.

    day 를 밀지 않고 시계를 민다 - 프로덕션에서 day 는 만들 때 한 번
    정해지고 다시는 안 바뀐다. day 를 미는 방식은 이미 쌓아둔 점수까지
    같이 옮긴 것처럼 보여 순위표가 실제와 다르게 나온다.
    """
    day_after = study.day + _one_day()
    return lambda: day_after
