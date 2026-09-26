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
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Word

from . import daily_study, session
from .models import STUDY_PLANS, ReviewState, StudyLength, StudyPlan
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


class NoBackToBackTest(TestCase):
    """학습분에서 같은 단어를 연달아 내지 않는다.

    화면은 답하자마자 다음 문제 위에 "앞 문제 · 오답 · SLA" 로 정답을
    보여준다. 바로 다음 문제가 또 SLA 면 그 줄이 답이 되고, 일일공부 점수는
    순위표에 들어간다. 묶음 안에서 같은 단어가 다시 나오는 것은 괜찮지만
    바로 다음은 안 된다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.pair = list(
            Word.objects.visible().exclude(description="").values_list("pk", flat=True)[:2]
        )

    def test_the_word_just_asked_is_not_asked_again(self):
        """두 단어 묶음에서 방금 낸 것을 빼면 남은 하나만 나온다.

        무작위라 한 번만 보면 우연히 맞는다. 옛 코드는 매번 반반이라 20번
        연속 통과할 확률이 백만분의 일이다.
        """
        first, second = self.pair
        for _ in range(20):
            made = session.make_question([first], [], word_ids=self.pair)
            self.assertIsNotNone(made)
            self.assertEqual(made.answer_id, second, "방금 낸 단어를 또 냈다")

    def test_a_one_word_chunk_still_asks_that_word(self):
        """묶음이 한 단어뿐이면 뺄 수 없다. 빼면 전체 폴백으로 떨어져
        학습 안 한 단어가 학습분 문제로 나간다 - 그보다는 같은 단어가 낫다."""
        only = self.pair[0]
        made = session.make_question([only], [], word_ids=[only])

        self.assertIsNotNone(made, "한 단어 묶음에서 문제를 못 냈다")
        self.assertEqual(made.answer_id, only)


# 학습 범위로 못 내고 전체에서 냈을 때 _next_question 이 남기는 로그의 머리.
FALLBACK_LOG = "학습 범위로 문제를 못 만들어"


def repeats_of(seen: list[int]) -> list[int]:
    """바로 앞과 같은 정답이 나온 자리들."""
    return [i for i in range(1, len(seen)) if seen[i] == seen[i - 1]]


class NoBackToBackPlayTest(TestCase):
    """판을 끝까지 풀어 보며 연달아 같은 정답이 없는지 본다.

    무작위 출제라 한 판만 보면 우연히 통과한다. 옛 코드는 두 단어 묶음의
    둘째 문제가 반반으로 같은 단어였으니, 여러 판을 돌리면 확실히 걸린다.

    "전체 폴백으로 떨어지는 조건이 늘지 않았나" 도 함께 본다. 앞 정답을
    빼는 바람에 후보가 비어 전체에서 내면, 화면에 보인 카드와 무관한
    단어가 학습분 문제로 나간다 - 연달아 같은 단어보다 나쁜 결과다.
    """

    def setUp(self):
        cache.clear()

    def play(self, user, length, between=None):
        """학습분을 끝까지 풀고 (정답 목록, 전체 폴백 횟수, 판) 을 준다.

        between 을 주면 답과 답 사이에 부른다(새로고침 흉내). 그것이
        돌려주는 토큰으로 이어 푼다.
        """
        with mock.patch.object(daily_study.logger, "info") as info:
            study, token, question = daily_study.start(user, length)
            from_study = study.chunk_size * study.chunk_count
            seen = []
            for _ in range(from_study):
                if question is None:
                    break
                if between is not None:
                    token, question = between(study, token, question)
                study.refresh_from_db()
                start = (study.answered // study.chunk_size) * study.chunk_size
                chunk = study.learned_ids[start : start + study.chunk_size]
                seen.append(answer_id_of(token))
                self.assertIn(seen[-1], chunk, "학습분 정답이 묶음 밖에서 나왔다")
                picked = question["choices"][0]["id"]
                _, token, question, study = daily_study.answer(user, token, picked)

        fallbacks = [c for c in info.call_args_list if FALLBACK_LOG in str(c.args[0])]
        return seen, len(fallbacks), study

    def test_every_length_over_many_plays(self):
        """세 길이 모두 열 판씩 풀어도 학습분에서 연달아 같은 정답이 없다."""
        seed_words()
        for length in StudyLength.values:
            for n in range(10):
                with self.subTest(length=length, play=n):
                    user = make_user(f"여러판{length}{n}")
                    seen, fallbacks, study = self.play(user, length)
                    self.assertEqual(
                        len(seen),
                        study.chunk_size * study.chunk_count,
                        "학습분을 다 못 풀었다",
                    )
                    self.assertEqual(repeats_of(seen), [], f"연달아 같은 정답: {seen}")
                    self.assertEqual(fallbacks, 0, "학습분에서 전체 폴백이 돌았다")

    def test_two_word_chunks_on_a_small_db(self):
        """단어가 적고 묶음이 두 개짜리여도 연달아 같은 정답이 없다.

        두 단어 묶음은 "앞 정답을 빼면 남는 것이 하나" 인 가장 빡빡한 경우다.
        세 길이의 묶음 크기를 모두 2 로 줄이고 단어를 12개만 둔다.
        """
        seed_words(count=12)
        small = {
            length: StudyPlan(
                total=plan.total,
                bonus=plan.bonus,
                chunk_size=2,
                chunk_count=plan.chunk_count,
            )
            for length, plan in STUDY_PLANS.items()
        }
        with mock.patch.dict(STUDY_PLANS, small):
            for length in StudyLength.values:
                for n in range(5):
                    with self.subTest(length=length, play=n):
                        user = make_user(f"작은{length}{n}")
                        seen, fallbacks, study = self.play(user, length)
                        self.assertEqual(study.chunk_size, 2)
                        self.assertGreater(len(seen), 0, "학습분이 없다")
                        self.assertEqual(repeats_of(seen), [], f"연달아 같은 정답: {seen}")
                        self.assertEqual(fallbacks, 0, "학습분에서 전체 폴백이 돌았다")

    def test_refreshing_between_answers_keeps_the_same_question(self):
        """답 사이에 새로고침해도 저장된 문제가 그대로 다시 나온다.

        다시 뽑으면 연달아 같은 정답을 피하는 판정이 새로고침 한 번에
        풀린다(resume 은 최근 목록 없이 뽑는다). 저장분을 다시 서명하는
        한 그 길로 안 간다.
        """
        seed_words()

        def refresh(study, token, question):
            study.refresh_from_db()
            again = daily_study.resume(study)
            self.assertIsNotNone(again, "이어 풀 문제가 없다")
            new_token, new_question = again
            self.assertEqual(
                answer_id_of(new_token), answer_id_of(token), "새로고침에 정답이 바뀌었다"
            )
            self.assertEqual(
                new_question["choices"], question["choices"], "새로고침에 보기가 바뀌었다"
            )
            return new_token, new_question

        for length in StudyLength.values:
            with self.subTest(length=length):
                user = make_user(f"새로{length}")
                seen, fallbacks, _study = self.play(user, length, refresh)
                self.assertEqual(repeats_of(seen), [], f"연달아 같은 정답: {seen}")
                self.assertEqual(fallbacks, 0)

    def test_words_without_description_do_not_break_the_chunk(self):
        """설명 없는 단어만 든 묶음도 끊기지 않고 전체 폴백도 없다.

        설명 문제 유형은 그 단어로 못 만들지만 다른 유형이 남는다. 앞 정답을
        뺀 뒤에도 유형을 다 훑으므로 후보가 하나만 남아도 문제가 선다.
        """
        seed_words()
        Word.objects.update(description="")
        for length in StudyLength.values:
            with self.subTest(length=length):
                user = make_user(f"설명없음{length}")
                seen, fallbacks, study = self.play(user, length)
                self.assertEqual(len(seen), study.chunk_size * study.chunk_count)
                self.assertEqual(repeats_of(seen), [], f"연달아 같은 정답: {seen}")
                self.assertEqual(fallbacks, 0, "설명 없는 묶음에서 전체 폴백이 돌았다")

    def test_older_answers_in_the_chunk_can_come_back(self):
        """빼는 것은 바로 앞 정답 하나뿐이다. 그 전 것은 다시 나올 수 있다.

        다섯 단어 묶음에서 셋이 검수 취소되면 남은 둘로 다섯 문제를 낸다.
        최근 목록을 통째로 빼면 셋째 문제에서 둘 다 빠져 빼지 않는 쪽으로
        떨어지고, 반반으로 연달아 같은 단어가 나온다. 하나만 빼면 둘이
        번갈아 나온다.
        """
        seed_words()
        for n in range(6):
            with self.subTest(play=n):
                user = make_user(f"번갈아{n}")
                study, token, question = daily_study.start(user, StudyLength.MEDIUM)
                study.refresh_from_db()
                first = answer_id_of(token)
                chunk = study.learned_ids[: study.chunk_size]
                others = [pk for pk in chunk if pk != first]
                Word.objects.filter(pk__in=others[:3]).update(is_reviewed=False)

                seen = [first]
                for _ in range(study.chunk_size - 1):
                    picked = question["choices"][0]["id"]
                    _, token, question, study = daily_study.answer(user, token, picked)
                    seen.append(answer_id_of(token))

                self.assertEqual(set(seen), {first, others[3]}, f"남은 둘 밖에서 나왔다: {seen}")
                self.assertEqual(repeats_of(seen), [], f"연달아 같은 정답: {seen}")
                Word.objects.filter(pk__in=others[:3]).update(is_reviewed=True)

    def test_a_chunk_left_with_one_visible_word_keeps_asking_it(self):
        """묶음 두 단어 중 하나가 검수 취소되면 남은 하나를 연달아 낸다.

        뺄 수 없는 경우다. 여기서 전체로 떨어지면 학습 안 한 단어가
        학습분 문제로 나간다 - 연달아 같은 단어가 그보다 낫다는 것이
        이 기능의 판단이다. 전체 폴백은 이전처럼 한 단어도 안 남았을 때만.
        """
        seed_words()
        user = make_user("하나남음")
        with mock.patch.object(daily_study.logger, "info") as info:
            study, token, _q = daily_study.start(user, StudyLength.SHORT)
            study.refresh_from_db()
            first = answer_id_of(token)
            other = next(pk for pk in study.learned_ids[:2] if pk != first)
            Word.objects.filter(pk=other).update(is_reviewed=False)

            _, token, question, _s = daily_study.answer(user, token, first)

        self.assertIsNotNone(question, "문제가 끊겼다")
        self.assertEqual(answer_id_of(token), first, "남은 한 단어 대신 다른 것을 냈다")
        self.assertFalse(
            [c for c in info.call_args_list if FALLBACK_LOG in str(c.args[0])],
            "남은 단어가 있는데 전체 폴백이 돌았다",
        )

    def test_a_chunk_with_no_visible_word_falls_back_to_everything(self):
        """묶음 단어가 전부 검수 취소되면 전체에서 낸다. 판은 안 끊긴다.

        이 경우의 폴백은 이번 변경 전부터 있었다. 새로 낸 문제의 보기와
        정답이 모두 검수된 단어여야 한다.
        """
        seed_words()
        user = make_user("전부취소")
        study, token, _q = daily_study.start(user, StudyLength.SHORT)
        study.refresh_from_db()
        chunk = study.learned_ids[:2]
        Word.objects.filter(pk__in=chunk).update(is_reviewed=False)

        _, token, question, _s = daily_study.answer(user, token, None)

        self.assertIsNotNone(question, "문제가 끊겼다")
        ids = [c["id"] for c in question["choices"]]
        self.assertEqual(
            Word.objects.visible().filter(pk__in=ids).count(), len(ids), "미검수 보기가 나왔다"
        )
        self.assertNotIn(answer_id_of(token), chunk)

    def test_only_the_last_answer_is_excluded(self):
        """최근 목록의 맨 앞 하나만 뺀다.

        두 단어 묶음에 최근이 [a, b] 면 b 가 나와야 한다. 둘 다 빼면 후보가
        비어 빼지 않는 쪽으로 떨어지고, 반반으로 방금 낸 a 가 또 나온다.
        """
        seed_words()
        a, b = Word.objects.visible().values_list("pk", flat=True)[:2]
        for _ in range(20):
            made = session.make_question([a, b], [], word_ids=[a, b])
            self.assertEqual(made.answer_id, b, "바로 앞 정답 a 를 또 냈다")
