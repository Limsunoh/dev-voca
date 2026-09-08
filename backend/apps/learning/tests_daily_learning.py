"""일일공부의 학습 단계.

지키려는 것은 셋이다.

    - 학습분 문제의 정답은 **방금 본 묶음 안에서만** 나온다
    - 학습 대상은 틀린 것 > 안 본 것 > 오래된 것 순으로 고른다
    - 일일공부에서 틀린 것이 복습 목록에 뜬다

첫 번째가 이 기능의 존재 이유다. 문제만 푸는 것은 아는 것을 확인하는
일이지 배우는 일이 아니다.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Word

from . import daily_study
from .models import ReviewState, StudyLength
from .tests_daily_study import make_user, seed_words


def answer_id_of(token: str) -> int:
    """이 문제의 정답 id.

    토큰에는 정답이 지문(HMAC)으로만 들어 있어(quiz.answer_payload) 그대로
    읽을 수 없다. 보기 넷을 하나씩 넣어보고 맞는 것을 찾는다 - 공격자가
    할 수 있는 것과 같은 일이지만, 여기서는 "무엇이 정답인가" 를 확인하는
    용도다.
    """
    state = daily_study._load(token)["q"]
    for choice_id in state["c"]:
        graded = quiz.resolve_answer(state, choice_id)
        if graded is not None and graded[0]:
            return choice_id
    raise AssertionError("보기 중에 정답이 없다")


class ScopeTest(TestCase):
    """학습분 문제는 방금 본 것에서 나온다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("범위")

    def test_the_first_question_comes_from_the_first_chunk(self):
        """첫 문제의 정답이 첫 묶음 안에 있다.

        여기가 깨지면 화면은 학습 카드를 보여주고 문제는 그것과 무관한
        단어를 낸다 - 사용자는 방금 본 것을 물어볼 줄 알고 틀린다.
        """
        study, token, _question = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        self.assertTrue(study.learned_ids, "학습 단어를 안 뽑았다")
        self.assertIn(
            answer_id_of(token),
            study.learned_ids,
            "첫 문제의 정답이 학습 묶음 밖에서 나왔다",
        )

    def test_every_study_question_stays_in_its_chunk(self):
        """학습분 내내 정답이 그 묶음 안에 있다.

        묶음이 넘어갈 때마다 범위도 넘어가야 한다. 첫 묶음만 맞고 그
        뒤가 전체에서 나오면 첫 문제만 보고는 못 잡는다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        size = study.chunk_size

        for i in range(size * study.chunk_count):
            study.refresh_from_db()
            start = (i // size) * size
            chunk = study.learned_ids[start : start + size]

            self.assertIn(
                answer_id_of(token), chunk, f"{i}번째 문제가 묶음 밖에서 나왔다"
            )

            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)
            if question is None:
                break

    def test_choices_come_from_everywhere_not_just_the_chunk(self):
        """오답 보기는 묶음 밖에서도 온다.

        묶음이 두 개뿐인데 보기까지 좁히면 넷을 못 채워 문제를 아예 못
        만든다. 채운다 해도 넷이 전부 방금 본 단어라 소거법으로 풀린다.
        """
        study, token, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        choice_ids = set(daily_study._load(token)["q"]["c"])

        self.assertGreater(
            len(choice_ids - set(study.learned_ids)),
            0,
            "보기가 전부 학습 묶음 안에서 나왔다",
        )

    def test_questions_past_the_chunks_come_from_everywhere(self):
        """학습분을 지나면 전체에서 낸다.

        마지막 몇 문제는 그날 배운 것 밖에서 나와야 "아는 것만 확인하는
        판" 이 되지 않는다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        from_study = study.chunk_size * study.chunk_count

        # 학습분을 다 푼다.
        for _ in range(from_study):
            if question is None:
                break
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertEqual(study.answered, from_study, "학습분을 다 못 풀었다")
        self.assertIsNotNone(question, "남은 문제가 있는데 안 나왔다")
        # 이 자리부터는 범위를 안 좁힌다.
        self.assertIsNone(daily_study._study_scope(study))


class PickOrderTest(TestCase):
    """학습 대상 선별 순서."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("선별")

    def test_a_wrong_word_comes_first(self):
        """틀린 것이 먼저 나온다. 지금 모르는 것이 그것이다."""
        target = Word.objects.visible().first()
        ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=target.pk,
            is_wrong=True,
        )

        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        self.assertIn(target.pk, study.learned_ids, "틀린 것이 안 나왔다")

    def test_a_recently_correct_word_is_not_picked(self):
        """방금 맞힌 것은 안 고른다. 아는 것을 다시 보여줄 이유가 없다."""
        words = list(Word.objects.visible()[:3])
        fresh = words[0]
        ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=fresh.pk,
            is_wrong=False,
            last_correct_at=timezone.now(),
        )

        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        first_chunk = study.learned_ids[: study.chunk_size]
        self.assertNotIn(fresh.pk, first_chunk, "방금 맞힌 것이 첫 묶음에 들어갔다")

    def test_the_same_word_is_not_learned_twice_in_one_study(self):
        """한 판에서 같은 단어를 두 번 학습하지 않는다.

        앞 묶음에서 본 단어가 다음 묶음에 또 나오면 복습이 아니라
        버그로 읽힌다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(study.chunk_size * study.chunk_count):
            if question is None:
                break
            picked = question["choices"][0]["id"]
            _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertEqual(
            len(study.learned_ids),
            len(set(study.learned_ids)),
            f"같은 단어가 두 번 나왔다: {study.learned_ids}",
        )


class ReviewLinkTest(TestCase):
    """일일공부 답이 복습에 반영된다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("복습연동")

    def test_a_wrong_answer_shows_up_in_review(self):
        """틀리면 복습 목록에 뜬다.

        이게 없으면 하루의 주 활동에서 틀린 것이 복습으로 안 이어진다.
        자유 문제풀이만 복습을 채우는데, 일일공부만 하는 사람이 많다.
        """
        from .tests_daily_study_edge import answer_wrong

        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        target_id = answer_id_of(token)

        answer_wrong(self.user, token, question)

        row = ReviewState.objects.get(
            user=self.user, target_type=quiz.TARGET_WORD, target_id=target_id
        )
        self.assertTrue(row.is_wrong, "틀렸는데 복습에 안 뜬다")

    def test_a_correct_answer_does_not_graduate_it_from_review(self):
        """맞혀도 streak 은 안 오른다.

        **streak 은 "복습에서 맞힌 횟수" 다.** 일일공부가 이걸 올리면
        복습을 한 번도 안 한 단어가 졸업해버려, 복습 목록이 조용히 빈다.
        """
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        target_id = answer_id_of(token)

        daily_study.answer(self.user, token, target_id)

        row = ReviewState.objects.get(
            user=self.user, target_type=quiz.TARGET_WORD, target_id=target_id
        )
        self.assertEqual(row.streak, 0, "일일공부가 복습 연속을 올렸다")
        self.assertFalse(row.is_wrong)
        self.assertIsNotNone(row.last_correct_at, "맞힌 시각이 안 남았다")

    def test_an_old_wrong_word_returns_to_the_study(self):
        """오래전에 본 것이 학습에 다시 나온다."""
        target = Word.objects.visible().first()
        now = timezone.now()

        ReviewState.objects.create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=target.pk,
            is_wrong=False,
            last_correct_at=now - timedelta(days=365),
        )
        # 나머지를 전부 최근에 맞힌 것으로 만들어 "오래된 것" 만 남긴다.
        ReviewState.objects.bulk_create(
            ReviewState(
                user=self.user,
                target_type=quiz.TARGET_WORD,
                target_id=w.pk,
                is_wrong=False,
                last_correct_at=now,
            )
            for w in Word.objects.visible().exclude(pk=target.pk)
        )

        study, _t, _q = daily_study.start(self.user, StudyLength.SHORT)

        study.refresh_from_db()
        self.assertIn(target.pk, study.learned_ids, "오래된 것이 학습에 안 나왔다")


class OldStudyTest(TestCase):
    """이 기능 전에 시작한 판."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("옛판")

    def test_a_study_without_chunks_still_works(self):
        """chunk_size=0 인 판은 학습 없이 옛 방식으로 끝난다.

        배포 시점에 오늘 판을 푸는 중인 사람이 이 상태다. 마이그레이션이
        기본값 0 을 넣으므로 여기서 안 깨져야 한다.
        """
        study, _token, _question = daily_study.start(self.user, StudyLength.SHORT)
        study.chunk_size = 0
        study.chunk_count = 0
        study.learned_ids = []
        study.save(update_fields=["chunk_size", "chunk_count", "learned_ids"])

        self.assertEqual(daily_study.learn_targets(study), [])
        self.assertFalse(daily_study.is_chunk_start(study))

        # 이어 풀 수 있어야 한다.
        study.refresh_from_db()
        self.assertIsNotNone(daily_study.resume(study), "옛 판을 이어 풀지 못한다")
