"""홈의 오늘의 단어 = 오늘 일일공부 첫 묶음 (11-12 사용자 결정, 안 A).

지키려는 것:

    - 홈(GET /daily/)을 열면 첫 묶음을 미리 뽑아 today_words 로 준다
    - 홈을 연 것만으로 "시작" 이 아니다. DailyStudy·DailyScore 가 안 생기고
      시작은 막히지 않는다
    - 시작하면 정확히 그 단어로 첫 묶음이 나온다
    - 시작한 뒤에는 오늘 배운 단어다
    - 묶음은 하루 한 줄이다. 다시 열어도, 동시에 열어도 같다
    - 하루 공부량을 바꾸면 앞을 지키고 모자라면 채운다. 검수가 취소된 단어는
      빼고 채운다
    - 실패해도 GET /daily/ 는 산다(홈은 날짜 단어로 떨어진다)
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.vocab.models import Word

from . import calendar_kst, daily_study
from .models import STUDY_PLANS, DailyPreview, DailyScore, DailyStudy, StudyLength
from .tests_daily_study import START_URL, make_user, seed_words

SHORT = StudyLength.SHORT
MEDIUM = StudyLength.MEDIUM


class PreviewTestCase(TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("미리보기")
        self.set_length(SHORT)
        self.client.force_login(self.user)

    def set_length(self, length: str) -> None:
        self.user.daily_length = length
        self.user.save(update_fields=["daily_length"])

    def home(self) -> list[int]:
        """홈이 받는 오늘의 단어 id."""
        res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200)
        return [w["id"] for w in res.json()["today_words"]]

    def start(self, length: str = SHORT) -> dict:
        res = self.client.post(START_URL, {"length": length}, content_type="application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()


class BeforeStartTest(PreviewTestCase):
    def test_home_shows_first_chunk_size_words(self):
        words = self.home()
        self.assertEqual(len(words), STUDY_PLANS[SHORT].chunk_size)
        self.assertEqual(Word.objects.visible().filter(pk__in=words).count(), len(words))

    def test_opening_home_is_not_starting(self):
        self.home()
        self.assertFalse(DailyStudy.objects.filter(user=self.user).exists())
        self.assertFalse(DailyScore.objects.filter(user=self.user).exists())
        body = self.client.get(START_URL).json()
        self.assertIsNone(body["today"])
        # 시작이 "이미 시작했습니다" 로 막히지 않는다.
        self.start()

    def test_reopening_gives_the_same_words(self):
        first = self.home()
        self.assertEqual(self.home(), first)
        self.assertEqual(self.home(), first)
        self.assertEqual(DailyPreview.objects.filter(user=self.user).count(), 1)

    def test_not_chosen_length_gives_nothing(self):
        """하루 공부량을 안 골랐으면 빈 목록이다. 홈은 날짜 단어로 그린다."""
        self.set_length("")
        self.assertEqual(self.home(), [])
        self.assertFalse(DailyPreview.objects.exists())

    def test_each_person_gets_their_own(self):
        mine = self.home()
        other = make_user("다른사람")
        other.daily_length = SHORT
        other.save(update_fields=["daily_length"])
        self.client.force_login(other)
        self.home()
        self.assertEqual(DailyPreview.objects.count(), 2)
        self.client.force_login(self.user)
        self.assertEqual(self.home(), mine)


class StartUsesPreviewTest(PreviewTestCase):
    def test_first_chunk_is_exactly_the_home_words(self):
        shown = self.home()
        started = self.start()
        self.assertEqual([w["id"] for w in started["learning"]], shown)
        study = DailyStudy.objects.get(user=self.user)
        self.assertEqual(study.learned_ids[: len(shown)], shown)

    def test_start_without_opening_home_still_works(self):
        started = self.start()
        self.assertEqual(len(started["learning"]), STUDY_PLANS[SHORT].chunk_size)
        self.assertEqual(DailyPreview.objects.filter(user=self.user).count(), 1)

    def test_after_start_home_shows_learned_words(self):
        shown = self.home()
        self.start()
        self.assertEqual(self.home(), shown)

    def test_after_finishing_home_shows_all_learned_words(self):
        from .tests_daily_study import drain

        self.home()
        study, token, question = daily_study.start(self.user, SHORT)
        study = drain(self.user, study, token, question)
        self.assertTrue(study.is_done)
        learned = list(study.learned_ids)
        self.assertEqual(len(learned), STUDY_PLANS[SHORT].from_study)
        self.assertEqual(self.home(), learned)


class LengthChangeTest(PreviewTestCase):
    def test_bigger_chunk_keeps_the_front_and_fills(self):
        small = self.home()  # 5분: 2개
        self.set_length(MEDIUM)  # 10분: 5개
        big = self.home()
        self.assertEqual(len(big), STUDY_PLANS[MEDIUM].chunk_size)
        self.assertEqual(big[: len(small)], small)
        self.assertEqual(len(set(big)), len(big), "같은 단어가 두 번 들어갔다")
        started = self.start(MEDIUM)
        self.assertEqual([w["id"] for w in started["learning"]], big)

    def test_smaller_chunk_takes_from_the_front(self):
        self.set_length(MEDIUM)
        big = self.home()
        self.set_length(SHORT)
        self.assertEqual(self.home(), big[: STUDY_PLANS[SHORT].chunk_size])

    def test_today_only_other_length_starts_from_the_same_front(self):
        """홈은 5분으로 봤는데 '오늘만 다른 길이로' 10분을 시작한 경우."""
        small = self.home()
        started = self.start(MEDIUM)
        learned = [w["id"] for w in started["learning"]]
        self.assertEqual(len(learned), STUDY_PLANS[MEDIUM].chunk_size)
        self.assertEqual(learned[: len(small)], small)


class UnreviewedTest(PreviewTestCase):
    def test_unreviewed_word_is_dropped_and_refilled(self):
        shown = self.home()
        Word.objects.filter(pk=shown[0]).update(is_reviewed=False)
        again = self.home()
        self.assertNotIn(shown[0], again)
        self.assertEqual(len(again), len(shown))
        self.assertEqual(again[0], shown[1], "남은 것은 순서를 지킨다")
        # 시작도 채운 목록 그대로다.
        started = self.start()
        self.assertEqual([w["id"] for w in started["learning"]], again)

    def test_unreviewed_word_beyond_the_chunk_is_dropped_too(self):
        """묶음 밖(뒤쪽)에 있던 단어가 해제돼도 저장에서 빠진다. 다시 검수돼도 원래 자리로는 안 돌아온다."""
        self.set_length(MEDIUM)
        stored = self.home()
        self.set_length(SHORT)
        Word.objects.filter(pk=stored[3]).update(is_reviewed=False)
        self.assertEqual(self.home(), stored[:2], "앞 두 개는 그대로다")
        self.assertNotIn(stored[3], DailyPreview.objects.get(user=self.user).word_ids)
        Word.objects.filter(pk=stored[3]).update(is_reviewed=True)
        self.set_length(MEDIUM)
        # 빈 다섯째 자리는 새로 채운다. 그 후보로 stored[3] 이 다시 뽑힐 수는
        # 있지만 원래 자리(넷째)로 돌아와 순서를 밀지는 않는다.
        got = self.home()
        self.assertEqual(len(got), STUDY_PLANS[MEDIUM].chunk_size)
        self.assertEqual(got[:4], [stored[0], stored[1], stored[2], stored[4]])

    def test_filled_chunk_stays_when_the_word_comes_back(self):
        shown = self.home()
        Word.objects.filter(pk=shown[0]).update(is_reviewed=False)
        again = self.home()
        Word.objects.filter(pk=shown[0]).update(is_reviewed=True)
        self.assertEqual(self.home(), again, "다시 보이게 돼도 이미 채운 묶음은 안 바뀐다")


class RaceTest(PreviewTestCase):
    def test_two_requests_creating_at_once_end_with_one_row(self):
        """먼저 확인할 때는 없었는데 그 사이 다른 요청이 줄을 만들어 둔 경우."""
        others = list(
            Word.objects.visible().order_by("-pk").values_list("pk", flat=True)[: STUDY_PLANS[SHORT].chunk_size]
        )
        real_pick = daily_study._pick_words

        def pick_then_lose(user_id, size, seen):
            picked = real_pick(user_id, size, seen)
            DailyPreview.objects.create(user_id=user_id, day=calendar_kst.today(), word_ids=others)
            return picked

        with mock.patch.object(daily_study, "_pick_words", side_effect=pick_then_lose):
            got = daily_study.preview_words(self.user.pk, calendar_kst.today(), STUDY_PLANS[SHORT].chunk_size)

        self.assertEqual([w.pk for w in got], others, "진 쪽은 이긴 쪽 묶음을 써야 한다")
        self.assertEqual(DailyPreview.objects.filter(user=self.user).count(), 1)

    def test_two_requests_filling_at_once_keep_the_winner(self):
        shown = self.home()
        Word.objects.filter(pk=shown[0]).update(is_reviewed=False)
        row = DailyPreview.objects.get(user=self.user)
        winner = [shown[1], *Word.objects.visible().exclude(pk__in=shown).values_list("pk", flat=True)[:1]]
        real_pick = daily_study._pick_words

        def pick_then_lose(user_id, size, seen):
            picked = real_pick(user_id, size, seen)
            DailyPreview.objects.filter(pk=row.pk).update(word_ids=winner)
            return picked

        with mock.patch.object(daily_study, "_pick_words", side_effect=pick_then_lose):
            got = daily_study.preview_words(self.user.pk, calendar_kst.today(), STUDY_PLANS[SHORT].chunk_size)

        self.assertEqual([w.pk for w in got], winner)
        row.refresh_from_db()
        self.assertEqual(row.word_ids, winner)


    def test_loser_refills_when_the_winner_filled_a_smaller_chunk(self):
        """5분 홈과 10분 시작이 겹쳐 5분 쪽이 이기면, 10분 쪽은 모자란 만큼 다시 채운다.

        그냥 자르기만 하면 시작한 판이 첫 묶음을 못 채워 그날 학습이 꺼진다.
        """
        shown = self.home()
        Word.objects.filter(pk=shown[0]).update(is_reviewed=False)
        row = DailyPreview.objects.get(user=self.user)
        small = [shown[1], *Word.objects.visible().exclude(pk__in=shown).values_list("pk", flat=True)[:1]]
        real_pick = daily_study._pick_words
        raced = []

        def pick_then_lose(user_id, size, seen):
            picked = real_pick(user_id, size, seen)
            if not raced:
                raced.append(True)
                DailyPreview.objects.filter(pk=row.pk).update(word_ids=small)
            return picked

        size = STUDY_PLANS[MEDIUM].chunk_size
        with mock.patch.object(daily_study, "_pick_words", side_effect=pick_then_lose):
            got = daily_study.preview_words(self.user.pk, calendar_kst.today(), size)

        self.assertEqual(len(got), size)
        self.assertEqual([w.pk for w in got][:2], small, "이긴 쪽 앞자리는 지킨다")
        row.refresh_from_db()
        self.assertEqual(row.word_ids, [w.pk for w in got])


class QuietTest(PreviewTestCase):
    def test_reopening_does_not_write(self):
        self.home()
        with CaptureQueriesContext(connection) as ctx:
            self.home()
        writes = [q["sql"] for q in ctx.captured_queries if "learning_dailypreview" in q["sql"] and not q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertEqual(writes, [], "바뀐 것이 없는데 고쳐 썼다")

    def test_cannot_fill_and_nothing_changed_does_not_write(self):
        """콘텐츠가 모자라 못 채우는 상태에서 다시 열어도 같은 값을 매번 쓰지 않는다."""
        self.home()
        with mock.patch.object(daily_study, "_pick_words", return_value=[]):
            Word.objects.filter(pk=DailyPreview.objects.get(user=self.user).word_ids[0]).update(is_reviewed=False)
            self.home()  # 빠진 단어를 저장에서 지운다(한 번은 쓴다)
            with CaptureQueriesContext(connection) as ctx:
                self.home()
        writes = [q["sql"] for q in ctx.captured_queries if "learning_dailypreview" in q["sql"] and not q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertEqual(writes, [])


class DayTest(PreviewTestCase):
    def test_new_day_new_words_and_old_row_goes(self):
        today_words = self.home()
        day_after = calendar_kst.today() + timedelta(days=1)
        with mock.patch.object(calendar_kst, "today", lambda: day_after):
            self.home()
        rows = list(DailyPreview.objects.filter(user=self.user).values_list("day", flat=True))
        self.assertEqual(rows, [day_after], "지난날 줄이 남았다")
        self.assertTrue(today_words)


class FailureTest(PreviewTestCase):
    def test_status_survives_a_failing_preview(self):
        with mock.patch.object(daily_study, "preview_words", side_effect=RuntimeError("boom")):
            with self.assertLogs("apps.learning.views", level="ERROR"):
                res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["today_words"], [])
        self.assertIn("lengths", body)

    def test_a_study_without_learning_gives_nothing(self):
        """학습 단계가 생기기 전 판(chunk_size 0)이면 빈 목록 - 홈은 날짜 단어."""
        DailyStudy.objects.create(
            user=self.user,
            day=calendar_kst.today(),
            length=SHORT,
            total_questions=10,
            chunk_size=0,
            chunk_count=0,
        )
        self.assertEqual(self.home(), [])
