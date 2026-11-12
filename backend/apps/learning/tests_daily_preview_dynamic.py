"""홈의 오늘의 단어(미리 뽑은 일일공부 첫 묶음)를 깨뜨려 보는 테스트.

tests_daily_preview 가 정한 동작을 한 연결 안에서 본다면, 여기는 그 바깥을 본다.

    - 실제 두 연결에서 홈과 홈, 홈과 시작, 채우기와 채우기가 겹칠 때 묶음이
      하나이고, 시작한 판의 첫 묶음이 저장된 줄의 앞자리와 같은가
    - 자정을 넘겨 시작하면 새날 묶음이고 지난 줄은 지워지는가
    - 길이를 여러 번 바꿔도 앞자리를 지키고 같은 단어가 두 번 안 들어가는가
    - 검수 안 된 단어가 홈(시작 전·시작 뒤)과 첫 묶음에 하나도 안 새는가
    - 콘텐츠가 적어 학습이 꺼지는 DB, 이상한 하루 공부량, 지워진 미리 뽑기 줄,
      회원 탈퇴에서 500 이 안 나고 홈은 날짜 단어로 떨어지는가
    - 응답 모양과 쿼리 수
"""

from __future__ import annotations

import secrets
import threading
import unittest
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.vocab import quiz
from apps.vocab.models import Word

from . import calendar_kst, daily_study
from .models import STUDY_PLANS, DailyPreview, DailyScore, DailyStudy, ReviewState, StudyLength
from .tests_daily_study import START_URL, make_user, seed_words
from .tests_daily_study_edge import _KeepsCacheTable

SHORT = StudyLength.SHORT
MEDIUM = StudyLength.MEDIUM
LONG = StudyLength.LONG

# 홈이 오늘의 단어 한 칸으로 받는 키. 프론트 StudyCard 타입과 맞아야 한다.
CARD_KEYS = {
    "id",
    "term",
    "pronunciation",
    "reading",
    "meaning",
    "description",
    "example",
    "example_translation",
    "category_label",
}


def chunk(length: str) -> int:
    return STUDY_PLANS[length].chunk_size


class _Helpers:
    def set_length(self, length: str) -> None:
        self.user.daily_length = length
        self.user.save(update_fields=["daily_length"])

    def home(self, client=None) -> list[int]:
        res = (client or self.client).get(START_URL)
        self.assertEqual(res.status_code, 200, res.content)
        return [w["id"] for w in res.json()["today_words"]]

    def start(self, length: str = SHORT) -> list[int]:
        res = self.client.post(START_URL, {"length": length}, content_type="application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return [w["id"] for w in res.json()["learning"]]

    def stored(self) -> list[int]:
        return DailyPreview.objects.get(user=self.user, day=calendar_kst.today()).word_ids


class DynamicCase(_Helpers, TestCase):
    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("깨기")
        self.set_length(SHORT)
        self.client.force_login(self.user)


# ---- 검수 게이트 ----------------------------------------------------------


class ReviewGateTest(DynamicCase):
    """검수 안 된 단어가 홈과 첫 묶음에 새지 않는다."""

    def test_unreviewed_words_are_never_picked_into_the_preview(self):
        # 검수 안 된 단어를 잔뜩 깔아 둔다. 뽑기가 visible() 을 안 거치면 섞인다.
        hidden = Word.objects.bulk_create(
            Word(term=f"hidden{i}", meaning="숨김", description="숨김", is_reviewed=False)
            for i in range(300)
        )
        hidden_ids = {w.pk for w in hidden}
        self.set_length(LONG)
        shown = self.home()
        self.assertEqual(len(shown), chunk(LONG))
        self.assertFalse(hidden_ids & set(shown))
        self.assertFalse(hidden_ids & set(self.stored()))

    def test_whole_preview_unreviewed_is_fully_refilled(self):
        self.set_length(MEDIUM)
        shown = self.home()
        Word.objects.filter(pk__in=shown).update(is_reviewed=False)
        again = self.home()
        self.assertEqual(len(again), chunk(MEDIUM))
        self.assertFalse(set(shown) & set(again))
        started = self.start(MEDIUM)
        self.assertEqual(started, again)

    def test_learned_word_unreviewed_after_start_leaves_home(self):
        self.home()
        learned = self.start()
        Word.objects.filter(pk=learned[0]).update(is_reviewed=False)
        after = self.home()
        self.assertNotIn(learned[0], after)
        self.assertEqual(after, learned[1:])

    def test_unreviewed_between_home_and_start_is_not_in_first_chunk(self):
        shown = self.home()
        Word.objects.filter(pk=shown[1]).update(is_reviewed=False)
        started = self.start()
        self.assertNotIn(shown[1], started)
        self.assertEqual(len(started), chunk(SHORT))
        self.assertEqual(started[0], shown[0])

    def test_no_visible_words_at_all_gives_empty_and_200(self):
        Word.objects.update(is_reviewed=False)
        self.assertEqual(self.home(), [])
        self.assertFalse(DailyPreview.objects.exists())


# ---- 시작 / 시작 아님 -----------------------------------------------------


class NotStartingTest(DynamicCase):
    def test_many_home_opens_with_length_changes_never_start(self):
        for length in (SHORT, LONG, MEDIUM, SHORT, LONG):
            self.set_length(length)
            self.home()
        self.assertFalse(DailyStudy.objects.exists())
        self.assertFalse(DailyScore.objects.exists())
        body = self.client.get(START_URL).json()
        self.assertIsNone(body["today"])
        self.assertIsNone(body["token"])
        self.assertEqual(body["learning"], [])
        self.start(LONG)

    def test_second_chunk_does_not_repeat_the_preview(self):
        """미리 뽑은 묶음이 첫 묶음보다 길어도(5개 저장, 2개 묶음) 다음 묶음은 배운 것을 빼고 고른다."""
        self.set_length(MEDIUM)
        self.home()
        self.set_length(SHORT)
        self.home()
        study, _token, _q = daily_study.start(self.user, SHORT)
        first = list(study.learned_ids)
        DailyStudy.objects.filter(pk=study.pk).update(answered=chunk(SHORT))
        study.refresh_from_db()
        daily_study.issue_chunk(study)
        study.refresh_from_db()
        second = study.learned_ids[len(first):]
        self.assertEqual(len(second), chunk(SHORT))
        self.assertFalse(set(first) & set(second))

    def test_start_after_preview_row_deleted_still_works(self):
        self.home()
        DailyPreview.objects.all().delete()
        started = self.start()
        self.assertEqual(len(started), chunk(SHORT))
        self.assertEqual(self.stored()[: len(started)], started)

    def test_preview_row_deleted_after_start_home_still_shows_learned(self):
        self.home()
        learned = self.start()
        DailyPreview.objects.all().delete()
        self.assertEqual(self.home(), learned)
        self.assertFalse(DailyPreview.objects.exists(), "시작한 뒤 홈이 미리 뽑기 줄을 다시 만들었다")

    def test_wrong_words_come_first_in_the_preview(self):
        wrong = list(Word.objects.visible().order_by("-pk").values_list("pk", flat=True)[: chunk(SHORT)])
        for pk in wrong:
            ReviewState.objects.create(user=self.user, target_type=quiz.TARGET_WORD, target_id=pk, is_wrong=True)
        self.assertEqual(sorted(self.home()), sorted(wrong))


class LengthChurnTest(DynamicCase):
    def test_switching_many_times_keeps_the_front_and_no_duplicates(self):
        order = [SHORT, LONG, SHORT, MEDIUM, SHORT, LONG, MEDIUM]
        first = None
        for length in order:
            self.set_length(length)
            got = self.home()
            self.assertEqual(len(got), chunk(length))
            self.assertEqual(len(set(got)), len(got), f"{length} 에서 같은 단어가 두 번")
            if first is None:
                first = got
            self.assertEqual(got[: len(first)], first[: len(got)], f"{length} 에서 앞자리가 바뀌었다")
        stored = self.stored()
        self.assertEqual(len(set(stored)), len(stored))
        self.assertEqual(self.start(MEDIUM), stored[: chunk(MEDIUM)])

    def test_weird_daily_length_values_give_empty_not_500(self):
        for value in ("", "99m", "  ", "10M", "x" * 8):
            type(self.user).objects.filter(pk=self.user.pk).update(daily_length=value)
            self.assertEqual(self.home(), [], repr(value))
        self.assertFalse(DailyPreview.objects.exists())


# ---- 콘텐츠가 적은 DB -----------------------------------------------------


class ThinContentTest(_Helpers, TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("적은")
        self.set_length(MEDIUM)
        self.client.force_login(self.user)

    def test_too_few_words_for_a_chunk_gives_date_words_and_no_row(self):
        seed_words(4)  # 10분 묶음 5개를 못 채운다 -> 학습 없는 판
        _total, size, _count = daily_study._fit_plan(STUDY_PLANS[MEDIUM])
        self.assertEqual(size, 0)
        self.assertEqual(self.home(), [])
        self.assertFalse(DailyPreview.objects.exists())
        res = self.client.post(START_URL, {"length": MEDIUM}, content_type="application/json")
        # 문제를 낼 수 있으면 학습 없이 열리고, 없으면 400. 어느 쪽이든 500 은 아니다.
        self.assertIn(res.status_code, (201, 400), res.content)
        if res.status_code == 201:
            self.assertEqual(res.json()["learning"], [])

    def test_just_enough_words_home_equals_first_chunk(self):
        seed_words(12)
        _total, size, _count = daily_study._fit_plan(STUDY_PLANS[MEDIUM])
        shown = self.home()
        self.assertEqual(len(shown), size)
        if size:
            self.assertEqual(self.start(MEDIUM), shown)


# ---- 날짜 경계 ------------------------------------------------------------


class MidnightTest(DynamicCase):
    def test_home_before_midnight_start_after_uses_new_day(self):
        yesterday_words = self.home()
        tomorrow = calendar_kst.today() + timedelta(days=1)
        with mock.patch.object(calendar_kst, "today", lambda: tomorrow):
            started = self.start()
            self.assertEqual(DailyStudy.objects.get(user=self.user).day, tomorrow)
            rows = list(DailyPreview.objects.filter(user=self.user).values_list("day", "word_ids"))
        self.assertEqual([d for d, _ in rows], [tomorrow])
        self.assertEqual(rows[0][1][: len(started)], started)
        self.assertTrue(yesterday_words)

    def test_started_yesterday_home_today_is_a_fresh_preview(self):
        self.home()
        learned = self.start()
        tomorrow = calendar_kst.today() + timedelta(days=1)
        with mock.patch.object(calendar_kst, "today", lambda: tomorrow):
            res = self.client.get(START_URL)
            self.assertEqual(res.status_code, 200)
            body = res.json()
            self.assertIsNone(body["today"])
            shown = [w["id"] for w in body["today_words"]]
            self.assertEqual(len(shown), chunk(SHORT))
            self.assertEqual(self.start(), shown)
        self.assertTrue(learned)


# ---- 회원 탈퇴 ------------------------------------------------------------


class AccountDeleteTest(DynamicCase):
    def test_deleting_user_removes_preview_rows(self):
        self.home()
        self.assertTrue(DailyPreview.objects.filter(user=self.user).exists())
        self.user.delete()
        self.assertFalse(DailyPreview.objects.exists())


# ---- 응답 모양 / 인가 / 쿼리 ----------------------------------------------


class ResponseShapeTest(DynamicCase):
    def test_today_words_items_match_the_card_shape(self):
        body = self.client.get(START_URL).json()
        self.assertIn("today_words", body)
        self.assertTrue(body["today_words"])
        for item in body["today_words"]:
            self.assertEqual(set(item), CARD_KEYS)

    def test_anonymous_gets_401_and_no_row(self):
        self.client.logout()
        res = self.client.get(START_URL)
        self.assertIn(res.status_code, (401, 403))
        self.assertFalse(DailyPreview.objects.exists())

    def test_today_of_failing_inside_today_words_keeps_200(self):
        with mock.patch.object(daily_study, "_fit_plan", side_effect=RuntimeError("boom")):
            with self.assertLogs("apps.learning.views", level="ERROR"):
                res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["today_words"], [])

    def test_reopen_query_count_is_small_and_flat(self):
        self.home()
        with CaptureQueriesContext(connection) as small:
            self.home()
        self.set_length(LONG)
        self.home()
        with CaptureQueriesContext(connection) as big:
            self.home()
        # 묶음 크기와 무관해야 한다(단어마다 쿼리가 늘면 N+1).
        self.assertEqual(len(small), len(big), [q["sql"] for q in big.captured_queries])
        self.assertLessEqual(len(big), 20, [q["sql"] for q in big.captured_queries])


# ---- 실제 두 연결 ---------------------------------------------------------


def _run_threads(*calls):
    """calls 를 각자의 스레드(= 각자의 DB 연결)에서 동시에 돌린다.

    결과는 ("ok", 값) 또는 ("err", 예외).
    """
    results = [None] * len(calls)
    gate = threading.Barrier(len(calls))

    def one(index, fn):
        try:
            gate.wait(timeout=10)
            results[index] = ("ok", fn())
        except Exception as exc:  # 무엇이 났는지 그대로 본다
            results[index] = ("err", exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=one, args=(i, fn)) for i, fn in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class RealRaceTest(_KeepsCacheTable, _Helpers, TransactionTestCase):
    ROUNDS = 5

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user(f"경합{secrets.token_hex(3)}")
        self.set_length(SHORT)

    def _client(self):
        client = Client()
        client.force_login(self.user)
        return client

    def test_many_homes_at_once_make_one_row_and_agree(self):
        for _ in range(self.ROUNDS):
            DailyPreview.objects.all().delete()
            clients = [self._client() for _ in range(6)]
            results = _run_threads(*[(lambda c=c: self.home(c)) for c in clients])
            self.assertTrue(all(r[0] == "ok" for r in results), results)
            seen = {tuple(r[1]) for r in results}
            self.assertEqual(len(seen), 1, f"홈마다 다른 묶음: {seen}")
            self.assertEqual(DailyPreview.objects.filter(user=self.user).count(), 1)
            self.assertEqual(list(seen.pop()), self.stored())

    def test_home_and_start_at_once(self):
        """홈과 시작이 겹쳐도 판은 하나이고 첫 묶음은 저장된 줄의 앞자리다."""
        for _ in range(self.ROUNDS):
            DailyStudy.objects.all().delete()
            DailyPreview.objects.all().delete()
            home_client, start_client = self._client(), self._client()

            def start():
                res = start_client.post(START_URL, {"length": MEDIUM}, content_type="application/json")
                return res.status_code, [w["id"] for w in res.json().get("learning", [])]

            results = _run_threads(lambda: self.home(home_client), start)
            self.assertTrue(all(r[0] == "ok" for r in results), results)
            shown = results[0][1]
            status, learned = results[1][1]
            self.assertEqual(status, 201)
            self.assertEqual(len(learned), chunk(MEDIUM), "시작한 판의 첫 묶음이 덜 찼다")
            self.assertEqual(DailyStudy.objects.filter(user=self.user).count(), 1)
            self.assertEqual(self.stored()[: chunk(MEDIUM)], learned)
            # 홈이 시작 전에 봤으면 2개(앞자리), 시작 뒤에 봤으면 배운 단어 그대로다.
            self.assertIn(shown, (learned[: chunk(SHORT)], learned))

    def test_mixed_size_fills_at_once(self):
        """검수 해제로 빈자리가 생긴 줄을 5분 홈과 10분·30분 시작이 동시에 채운다."""
        for _ in range(self.ROUNDS):
            DailyPreview.objects.all().delete()
            Word.objects.update(is_reviewed=True)
            base = daily_study.preview_words(self.user.pk, calendar_kst.today(), chunk(SHORT))
            Word.objects.filter(pk=base[0].pk).update(is_reviewed=False)
            sizes = [chunk(SHORT), chunk(MEDIUM), chunk(SHORT), chunk(LONG)]
            day = calendar_kst.today()
            results = _run_threads(
                *[(lambda s=s: [w.pk for w in daily_study.preview_words(self.user.pk, day, s)]) for s in sizes]
            )
            self.assertTrue(all(r[0] == "ok" for r in results), results)
            final = self.stored()
            self.assertEqual(len(set(final)), len(final), "같은 단어가 두 번 저장됐다")
            self.assertNotIn(base[0].pk, final)
            for size, (_ok, got) in zip(sizes, results):
                self.assertEqual(len(got), size, f"{size} 개를 원했는데 {len(got)} 개")
                self.assertEqual(got, final[:size], "돌려준 묶음이 저장된 줄과 다르다")
                self.assertEqual(got[0], base[1].pk, "남은 앞자리가 밀렸다")

    def test_double_start_at_once_one_study(self):
        for _ in range(self.ROUNDS):
            DailyStudy.objects.all().delete()
            DailyPreview.objects.all().delete()
            shown = self.home(self._client())
            a, b = self._client(), self._client()
            results = _run_threads(
                *[
                    (lambda c=c: c.post(START_URL, {"length": SHORT}, content_type="application/json").status_code)
                    for c in (a, b)
                ]
            )
            codes = sorted(r[1] for r in results)
            self.assertEqual(codes, [201, 400], results)
            study = DailyStudy.objects.get(user=self.user)
            self.assertEqual(study.learned_ids[: len(shown)], shown)
