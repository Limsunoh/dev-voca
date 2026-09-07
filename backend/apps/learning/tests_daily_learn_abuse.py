"""학습 단계를 우회하거나 악용하는 경로.

화면은 학습 카드를 보여준 뒤 문제로 넘기지만, API 를 직접 치면 그 순서를
건너뛸 수 있다. 건너뛰어도 **문제는 여전히 그 묶음에서 나와야** 한다 -
안 그러면 "방금 본 것으로 낸다" 는 약속이 화면을 우회한 사람에게만
깨지는 것이 아니라, 화면이 느린 순간에도 깨진다.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Word

from . import daily_study
from .models import DailyStudy, ReviewState, StudyLength
from .record import bump_review_states
from .tests_daily_learning import answer_id_of
from .tests_daily_study import make_user, seed_words


class SkipLearningTest(TestCase):
    """학습 화면을 안 보고 바로 답하기."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("우회")

    def test_answering_without_seeing_the_cards_still_stays_in_scope(self):
        """카드를 안 봐도 문제는 묶음 안에서 나온다.

        학습은 순번(step) 체계 밖에 있어 "봤다" 를 서버가 강제하지 않는다.
        대신 문제를 만드는 쪽이 범위를 좁히므로, 건너뛰어도 범위는 지켜진다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 화면을 거치지 않고 바로 답한다.
        for i in range(study.chunk_size * study.chunk_count):
            study.refresh_from_db()
            size = study.chunk_size
            chunk = study.learned_ids[(i // size) * size : (i // size) * size + size]

            self.assertIn(
                answer_id_of(token), chunk, f"{i}번째가 묶음 밖에서 나왔다"
            )

            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)
            if question is None:
                break

    def test_issuing_a_chunk_twice_does_not_grow_the_list(self):
        """issue_chunk 를 여러 번 불러도 학습 목록이 안 부푼다.

        부풀면 묶음 구간이 밀려, 그 뒤 문제가 전부 화면에 안 보인
        단어로 나간다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        before = list(study.learned_ids)

        for _ in range(5):
            daily_study.issue_chunk(study)
            study.refresh_from_db()

        self.assertEqual(study.learned_ids, before, "같은 묶음이 여러 번 쌓였다")

    def test_an_unreviewed_chunk_does_not_trigger_a_reissue(self):
        """뽑아둔 단어가 미검수로 내려가도 새 묶음을 안 뽑는다.

        **여기가 실제로 터졌던 자리다.** "이미 뽑았나" 를 learn_targets 가
        비었는지로 판정했는데, 저기는 visible() 을 거치므로 검수가 취소되면
        빈 목록이 된다. 그러면 GET 마다 새 묶음이 이어붙어, 한 문제도 안
        풀었는데 계획 8개가 새로고침 여섯 번에 14개로 불었다.

        검수 취소는 이 프로젝트에서 실제로 일어나는 동작이다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        Word.objects.filter(pk__in=study.learned_ids).update(is_reviewed=False)

        for _ in range(6):
            study.refresh_from_db()
            daily_study.issue_chunk(study)

        study.refresh_from_db()
        self.assertEqual(
            len(study.learned_ids),
            study.chunk_size,
            f"미검수 뒤 목록이 불었다: {study.learned_ids}",
        )
        self.assertEqual(study.issued_chunks, 1, "묶음 카운터가 어긋났다")

    def test_a_partial_chunk_is_not_saved(self):
        """묶음을 다 못 채우면 저장하지 않는다.

        부분 묶음을 넣으면 learned_ids 의 구간 경계가 밀린다. 한 번
        밀리면 그 판 끝까지 화면에 보인 카드와 다른 단어로 문제가 나가고
        복구되지 않는다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        # 첫 묶음을 푼 것으로 만들고, 남은 후보를 묶음 크기보다 적게 둔다.
        DailyStudy.objects.filter(pk=study.pk).update(answered=study.chunk_size)
        keep = set(study.learned_ids)
        spare = list(
            Word.objects.visible()
            .exclude(pk__in=keep)
            .values_list("pk", flat=True)[: study.chunk_size - 1]
        )
        Word.objects.visible().exclude(pk__in=keep | set(spare)).update(
            is_reviewed=False
        )

        study.refresh_from_db()
        issued = daily_study.issue_chunk(study)

        study.refresh_from_db()
        self.assertEqual(issued, [], "부분 묶음을 내줬다")
        self.assertEqual(
            len(study.learned_ids) % study.chunk_size,
            0,
            f"구간 경계가 밀렸다: {study.learned_ids}",
        )

    def test_resume_does_not_swap_the_question(self):
        """이어 풀기를 반복해도 문제가 안 바뀐다.

        바뀌면 아는 것이 나올 때까지 화면을 새로 열면 되므로 사실상
        만점이다. 학습 단계가 생기면서 resume 이 묶음을 뽑는 경로가
        늘었는데, 그 때문에 이 보호가 뚫리지 않았는지 본다.
        """
        study, _token, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        first = daily_study.resume(study)
        self.assertIsNotNone(first)

        for _ in range(5):
            study.refresh_from_db()
            again = daily_study.resume(study)
            self.assertIsNotNone(again)
            self.assertEqual(
                answer_id_of(again[0]),
                answer_id_of(first[0]),
                "이어 풀기를 반복하니 문제가 바뀌었다",
            )

    def test_a_replayed_token_is_still_refused(self):
        """옛 토큰 재사용은 여전히 막힌다.

        학습을 순번 밖에 뒀는데 그 때문에 순번 보호가 약해지지 않았는지
        본다. 이건 정답 브루트포스를 막는 마지막 방어선이다.
        """
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, token, picked)

        with self.assertRaises(daily_study.SessionError):
            daily_study.answer(self.user, token, picked)


class ScopeIntegrityTest(TestCase):
    """범위 계산이 어긋나는 경계."""

    def setUp(self):
        cache.clear()
        self.user = make_user("경계")

    def test_a_tiny_corpus_falls_back_to_the_whole_pool(self):
        """단어가 아주 적으면 학습 없이 전체에서 낸다.

        묶음을 만들 수 없는 판인데, 여기서 판이 통째로 끝나면 사용자는
        "왜 시작하자마자 끝났지" 를 본다.
        """
        Word.objects.bulk_create(
            Word(term=f"tiny{i}", meaning=f"뜻{i}", description=f"설명{i}", is_reviewed=True)
            for i in range(5)
        )

        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        self.assertIsNotNone(question, "문제를 못 만들었다")
        # 5개뿐이라 총 문제 수가 줄고, 묶음이 서는지 아닌지는 그 결과다.
        self.assertLessEqual(
            study.chunk_size * study.chunk_count,
            study.total_questions,
            "학습분이 총 문제 수를 넘는다",
        )

    def test_a_deleted_word_does_not_break_the_scope(self):
        """학습한 단어가 지워져도 판이 안 깨진다.

        검수가 취소되거나 항목이 지워지는 것은 이 프로젝트에서 실제로
        일어난다. 그때 범위가 빈 목록이 되면 문제를 못 만드는데, 전체에서
        내는 폴백이 그것을 받는다.
        """
        seed_words()
        study, _token, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        Word.objects.filter(pk__in=study.learned_ids).update(is_reviewed=False)

        # 이어 풀 수 있어야 한다.
        study.refresh_from_db()
        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "학습 단어가 사라지자 판이 막혔다")

    def test_the_scope_moves_with_the_chunk(self):
        """묶음이 넘어가면 범위도 넘어간다."""
        seed_words()
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        first = daily_study._study_scope(study)
        self.assertEqual(first, study.learned_ids[: study.chunk_size])

        # 한 묶음을 다 푼 것으로 만든다.
        DailyStudy.objects.filter(pk=study.pk).update(answered=study.chunk_size)
        study.refresh_from_db()
        daily_study.issue_chunk(study)
        study.refresh_from_db()

        second = daily_study._study_scope(study)
        self.assertNotEqual(first, second, "묶음이 넘어갔는데 범위가 그대로다")
        self.assertEqual(
            len(set(first) & set(second)), 0, "두 묶음이 겹친다"
        )

    def test_choices_are_never_all_from_the_chunk(self):
        """보기 넷이 전부 학습 묶음에서 나오지 않는다.

        전부 방금 본 단어면 소거법으로 풀린다. 묶음이 2개일 때는 넷을
        채울 수도 없다.
        """
        seed_words()
        _study, token, _q = daily_study.start(self.user, StudyLength.SHORT)

        state = daily_study._load(token)["q"]
        self.assertEqual(len(state["c"]), quiz.CHOICE_COUNT)


class ReviewStateWriteTest(TestCase):
    """복습 진행이 일일공부에 밀려 사라지는가."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습")

    def test_a_correct_answer_does_not_write_streak_back(self):
        """맞힌 답은 streak 을 되쓰지 않는다.

        bulk_update 는 필드 목록에 있는 값을 **읽은 시점 그대로** 쓴다.
        맞았을 때 streak 을 안 바꾸니 "그대로 두는 것" 처럼 보이지만,
        읽기와 쓰기 사이에 복습이 올린 값이 있으면 낡은 값으로 되돌린다.

        일일공부가 이 함수를 답 하나마다 부르면서 그 창이 25배로
        넓어졌다 - 자유 문제풀이는 판이 끝날 때 한 번이라 안 띄었다.
        복습 2회로 졸업하는 규칙(GRADUATE_STREAK)이라 1회가 사라지면
        사용자는 졸업에 영영 못 닿는다.

        창을 실제로 열려면 함수가 DB 를 읽은 **뒤** 복습이 끼어들어야
        한다. 스레드로는 그 지점을 못 맞히므로 bulk_update 를 감싸
        직전에 복습을 끼워 넣는다 - 이것이 그 순간이다.
        """
        word = Word.objects.visible().first()
        row = ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=word.pk,
            streak=0,
        )

        real = ReviewState.objects.bulk_update

        def slip_in(objs, fields, **kwargs):
            # 함수가 streak=0 을 읽어둔 상태다. 여기서 복습이 1 로 올린다.
            ReviewState.objects.filter(pk=row.pk, streak=0).update(streak=1)
            return real(objs, fields, **kwargs)

        with patch.object(ReviewState.objects, "bulk_update", slip_in):
            bump_review_states(self.user, {(quiz.TARGET_WORD, word.pk): True})

        row.refresh_from_db()
        self.assertEqual(row.streak, 1, "복습에서 맞힌 것이 사라졌다")

    def test_a_wrong_answer_still_breaks_the_streak(self):
        """틀린 답은 여전히 연속을 끊는다.

        위 수정으로 맞은 줄에서 streak 을 뺐는데, 틀린 줄에서까지
        빠지면 복습 1회 + 오답 + 복습 1회 로 "연속" 아닌 두 번에
        졸업한다.
        """
        word = Word.objects.visible().first()
        row = ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=word.pk,
            streak=1,
        )

        bump_review_states(self.user, {(quiz.TARGET_WORD, word.pk): False})

        row.refresh_from_db()
        self.assertEqual(row.streak, 0, "틀렸는데 연속이 안 끊겼다")
        self.assertTrue(row.is_wrong)


class ChunkWriteTest(TestCase):
    """묶음 저장이 다른 쓰기와 겹칠 때."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("동시")

    def test_a_full_save_does_not_resurrect_an_old_list(self):
        """진행 중인 판을 통째로 save() 해도 학습 목록이 안 되살아난다.

        issue_chunk 가 인메모리 learned_ids 에 이어붙여 쓰면, issued_chunks
        만 조건부로 막히고 리스트는 read-modify-write 그대로다. Admin 이
        진행 중인 판을 열어 저장만 해도(ModelAdmin 은 full save 다) 낡은
        리스트가 되살아나 구간 경계가 밀리고, 화면에 보인 카드와 다른
        단어로 문제가 나간다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()
        first = list(study.learned_ids)

        # 두 번째 묶음을 뽑을 자리로 옮긴다. 이 인스턴스는 아직
        # learned_ids=first 를 들고 있다.
        DailyStudy.objects.filter(pk=study.pk).update(answered=study.chunk_size)
        study.answered = study.chunk_size

        # _pick_for_study 가 도는 동안(ReviewState 조회 + order_by("?")
        # 세 번, 수십 ms) DB 쪽 learned_ids 가 늘어나는 순간을 만든다.
        # 다른 요청이 묶음을 넣었거나, 관리 화면이 손댄 경우다. 이때
        # 인메모리 값으로 이어붙이면 그 사이에 늘어난 것이 통째로 날아간다.
        real = daily_study._pick_for_study
        meanwhile = [-1, -2]

        def grow_meanwhile(s):
            picked = real(s)
            DailyStudy.objects.filter(pk=s.pk).update(
                learned_ids=list(first) + meanwhile
            )
            return picked

        with patch.object(daily_study, "_pick_for_study", grow_meanwhile):
            daily_study.issue_chunk(study)

        study.refresh_from_db()
        self.assertEqual(
            study.learned_ids[: study.chunk_size],
            first,
            f"첫 묶음이 덮여 사라졌다: {study.learned_ids}",
        )
        self.assertEqual(
            study.learned_ids[study.chunk_size : study.chunk_size * 2],
            meanwhile,
            f"그 사이에 들어온 묶음이 날아갔다: {study.learned_ids}",
        )


class ScoreboardLockTest(TestCase):
    """점수판 반영이 트랜잭션 안에 들어갔나."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("점수판")

    def test_taking_a_step_does_not_touch_the_scoreboard(self):
        """순번 소비가 점수판을 안 건드린다.

        DailyScore 는 (user, day) 유일 인덱스를 잡는다. _take_step 이
        그것까지 하면, 채점을 감싼 트랜잭션이 복습 갱신이 끝날 때까지
        그 락을 쥔다 - 답하기와 어제 판 정산이 겹치는 자정 언저리가
        그 조합이고, daily_study 첫머리(settle_stale)가 그 교착을 이미
        관측해 적어뒀다.

        그래서 점수판은 호출부가 트랜잭션 밖에서 쓴다. 여기서는
        _take_step 이 그 일을 안 하는 것만 못 박는다 - 트랜잭션 경계는
        TestCase 가 전체를 감싸고 있어 안에서는 구분할 수 없다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        seen: list[int] = []
        real = daily_study.add_daily_study

        def watch(*args, **kwargs):
            seen.append(1)
            return real(*args, **kwargs)

        with patch.object(daily_study, "add_daily_study", watch):
            daily_study._take_step(study, study.step, 1, True)

        self.assertEqual(
            seen, [], "_take_step 이 점수판을 썼다 - 유일 인덱스 락이 트랜잭션에 들어간다"
        )

    def test_answering_still_publishes_the_score(self):
        """그래도 답할 때마다 점수판에 옮긴다.

        위에서 _take_step 을 비웠으니 호출부가 그 일을 이어받았는지
        확인한다. 안 옮기면 중간에 그만둔 사람이 순위표에서 0 이다.
        """
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        seen: list[int] = []
        real = daily_study.add_daily_study

        def watch(*args, **kwargs):
            seen.append(1)
            return real(*args, **kwargs)

        with patch.object(daily_study, "add_daily_study", watch):
            daily_study.answer(self.user, token, question["choices"][0]["id"])

        self.assertEqual(len(seen), 1, "답했는데 점수판에 안 옮겼다")

    def test_a_failed_review_write_rolls_back_the_score(self):
        """복습 갱신이 실패하면 채점도 되돌린다.

        따로 커밋하면 점수만 오르고 그 답은 복습에 영영 안 뜬다 -
        순번은 이미 소비돼서 재시도도 "이미 처리한 답입니다" 로 막힌다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        before = study.answered

        def boom(*_a, **_k):
            raise RuntimeError("복습 쓰기 실패")

        with patch.object(daily_study, "bump_review_states", boom):
            with self.assertRaises(RuntimeError):
                daily_study.answer(self.user, token, question["choices"][0]["id"])

        study.refresh_from_db()
        self.assertEqual(
            study.answered, before, "복습이 실패했는데 채점이 남았다"
        )


class StuckSessionTest(TestCase):
    """채점 뒤 다음 문제를 못 심었을 때 빠져나올 수 있나."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("갇힘")

    def test_a_crash_after_scoring_does_not_lock_the_day(self):
        """채점 커밋 뒤 터져도 이어 풀 수 있다.

        **여기가 실제로 터졌던 자리다.** 채점과 복습을 트랜잭션으로 묶고
        점수판 반영을 커밋 뒤로 빼면서, 커밋과 "다음 문제 심기" 사이에
        실패 지점이 생겼다. 거기서 터지면 DB 의 step 은 올라갔는데
        저장된 문제는 옛 순번이라, resume 이 그것을 다시 서명해 주고
        _take_step 이 영원히 거절한다.

        화면을 새로 열어도 계속 "이미 처리한 답입니다" 만 나오고, 하루
        한 번 제약이라 다시 시작할 수도 없다. 그 사람의 오늘이 끝난다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 채점은 되고 그 뒤 점수판 반영에서 터지게 한다.
        with patch.object(daily_study, "_publish", side_effect=RuntimeError("펑")):
            with self.assertRaises(RuntimeError):
                daily_study.answer(self.user, token, question["choices"][0]["id"])

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "채점이 안 남았다 - 전제가 틀렸다")

        # 이어 풀기가 살아 있어야 한다.
        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "이어 풀 문제를 못 냈다 - 갇혔다")

        # 그 문제로 실제로 답이 되어야 한다.
        next_token, _body = resumed
        _r, _t, _q, study = daily_study.answer(
            self.user, next_token, answer_id_of(next_token)
        )
        study.refresh_from_db()
        self.assertEqual(study.answered, 2, "이어 푼 답이 안 세어졌다")

    def test_a_stale_saved_question_is_replaced(self):
        """순번이 어긋난 저장 문제는 새로 뽑는다.

        위 상황을 직접 만든다. 저장된 문제의 순번만 뒤로 돌려도 같은
        교착이 나야 한다.
        """
        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)
        study.refresh_from_db()

        saved = dict(study.question)
        saved["state"] = {**saved["state"], "n": study.step + 5}
        DailyStudy.objects.filter(pk=study.pk).update(question=saved)
        study.refresh_from_db()

        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "순번이 어긋나자 문제를 못 냈다")

        token, _body = resumed
        state = daily_study._load(token)
        self.assertEqual(
            state["n"], study.step, "옛 순번을 그대로 다시 내줬다"
        )


class QuestionSwapRaceTest(TestCase):
    """순번과 저장된 문제가 어긋나지 않나.

    **"같은 순번에 토큰이 둘" 을 막는 것은 이 불변식이 아니다.** 그건
    resume 이 저장된 문제를 다시 서명해 주는 것이 막는다 - 어느 시점에
    읽어도 같은 행을 읽으므로 정답이 같다. 여기서 보는 것은 그보다
    앞단인 "두 값이 같은 것을 가리키나" 이고, 어긋나면 resume 이 저장분을
    버리고 새로 뽑는 경로로 빠져 그 보호 밖으로 나간다.

    **스레드로 창을 노리는 테스트는 두지 않았다.** 창이 수십 ms 라
    타이밍에 따라 들어갈 때도 안 들어갈 때도 있어서, 통과해도 방어를
    증명하지 못하고 실패해도 원인이 코드인지 타이밍인지 안 갈린다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("경합")

    def test_the_saved_question_never_lags_the_step(self):
        """저장된 문제의 순번이 DB 순번보다 뒤처지지 않는다.

        **여기가 실제로 터졌던 자리다.** 순번을 먼저 커밋하고 다음 문제를
        나중에 심으면 그 사이에 창이 생긴다. 창 안에서는 DB 가 step=N+1
        인데 저장된 문제는 n=N 이라, 그때 들어온 새로고침(resume)이
        저장분을 버리고 새로 뽑으면 **같은 순번에 유효한 토큰이 둘**이
        되어 아는 쪽을 골라 답할 수 있다. 안 뽑아주면 그 판이 갇힌다.

        보기를 누르고 응답 전에 새로고침하면 나는 상황이라, 답 하나마다
        창이 하나씩 생긴다.

        창을 없애는 것이 양쪽을 다 막는 유일한 방법이라, 채점과 문제
        심기를 한 트랜잭션에 넣었다. 여기서는 그 결과인 **"두 값이 항상
        같다"** 를 못 박는다 - 창이 다시 열리면 이 불변식이 깨진다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        self.assertEqual(
            study.question["state"]["n"],
            study.step,
            "시작 직후부터 어긋났다",
        )

        # **끝까지 돈다.** 마지막 답은 다음 문제를 안 심으므로 저장 문제가
        # 한 순번 뒤처지는데, 거기서 멈추면 그 자리를 못 본다. 다 푼 판은
        # question 이 비어 있어야 한다 - 남아 있으면 resume 이 그것을 보고
        # 이미 끝난 판에 답할 수 없는 토큰을 내준다.
        i = 0
        while token is not None:
            _r, token, _q, _s = daily_study.answer(
                self.user, token, answer_id_of(token)
            )
            i += 1
            study.refresh_from_db()

            if token is None:
                self.assertIsNone(
                    study.question,
                    f"판이 끝났는데 저장 문제가 남았다: {study.question}",
                )
                break

            self.assertEqual(
                study.question["state"]["n"],
                study.step,
                f"{i}번째 답 뒤에 저장 문제가 순번보다 뒤처졌다 - 창이 열렸다",
            )

        self.assertGreater(i, 1, "판이 너무 일찍 끝나 아무것도 못 봤다")

    def test_a_resume_between_answers_gives_the_same_question(self):
        """답과 답 사이에 새로고침해도 같은 문제가 온다.

        창이 없으면 resume 은 언제 들어오든 저장된 그 문제를 준다.
        여러 번 열어도 정답이 바뀌면 안 된다 - 바뀌면 아는 것이 나올
        때까지 새로 여는 길이 열린다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)

        _r, token, _q2, _s = daily_study.answer(
            self.user, token, answer_id_of(token)
        )
        self.assertIsNotNone(token, "다음 문제가 안 왔다")

        study.refresh_from_db()
        first = answer_id_of(token)
        for _ in range(5):
            fresh = DailyStudy.objects.get(pk=study.pk)
            resumed = daily_study.resume(fresh)
            self.assertIsNotNone(resumed, "이어 풀 문제를 못 냈다")
            self.assertEqual(
                answer_id_of(resumed[0]), first, "새로고침마다 문제가 바뀐다"
            )
