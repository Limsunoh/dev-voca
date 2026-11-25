"""순위표가 상위 목록을 10초 기억하는 동작(leaderboards.build 의 _cached_top).

테스트 설정은 기억하지 않는다(settings 의 CACHES["boards"] 가 테스트에서 DummyCache). 여기서만
메모리 캐시로 바꿔 시험한다(vocab/tests_list_count.py 와 같은 방법).

사용자가 받아들인 것은 "다른 사람의 점수만 최대 10초 늦음" 하나다. 그 밖은 예전처럼 즉시여야
한다.

    - 내 점수·판 수가 바뀌면 바로 보인다(목록 안이든, 밖에서 20등 안으로 들어오든).
    - 목록 밖이면 내 등수가 지금 값이다.
    - 이름·그림은 누구 것이든 지금 값이다.
    - 탈퇴(삭제)·비활성이 된 사람은 바로 빠진다.
    - 주가 바뀌면 지난주 기억을 쓰지 않는다.

맨 앞의 GuestDelayTest 는 "기억이 실제로 쓰인다" 를 먼저 못 박는다. 그게 없으면 나머지는 기억이
꺼진 채로도 통과해 아무것도 지키지 못한다.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import caches
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from . import calendar_kst, leaderboards
from .leaderboards import ALL_TIME, STREAK, WEEKLY
from .models import QuizSession
from .tests_leaderboards_edge3 import bulk_users, daily, finish_round, make_user

REMEMBER = {
    **settings.CACHES,
    "boards": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "board-top-test",
        "TIMEOUT": 10,
    },
}


def names(board) -> list[str]:
    return [row.display_name for row in board.rows]


def ranks(board) -> list[int]:
    return [row.rank for row in board.rows]


class BoardCacheBase(TestCase):
    def setUp(self):
        caches["boards"].clear()
        self.addCleanup(caches["boards"].clear)


@override_settings(CACHES=REMEMBER)
class GuestDelayTest(BoardCacheBase):
    """게스트는 기억한 목록을 쓴다. 다른 사람 점수가 늦는 것은 받아들인 동작이다."""

    def test_guest_sees_remembered_order_until_cache_expires(self):
        """기억이 살아 있으면 새 점수가 안 보이고, 10초가 지나면 보인다."""
        a = make_user("가람")
        finish_round(a, 100)
        self.assertEqual(names(leaderboards.build(ALL_TIME)), ["가람"])

        b = make_user("나래")
        finish_round(b, 200)
        self.assertEqual(names(leaderboards.build(ALL_TIME)), ["가람"], "기억이 쓰이지 않는다")

        later = timezone.now().timestamp() + 11
        with mock.patch("django.core.cache.backends.locmem.time.time", return_value=later):
            self.assertEqual(names(leaderboards.build(ALL_TIME)), ["나래", "가람"])

    def test_remembered_guest_board_reads_people_only(self):
        """기억이 있으면 게스트 요청은 사람 20명 읽기 한 번뿐이다(집계를 다시 돌리지 않는다)."""
        for i, user in enumerate(bulk_users("쿼리_", 5)):
            finish_round(user, 50 + i)
        leaderboards.build(ALL_TIME)

        with CaptureQueriesContext(connection) as ctx:
            leaderboards.build(ALL_TIME)
        self.assertEqual(len(ctx.captured_queries), 1, [q["sql"] for q in ctx.captured_queries])

    def test_is_me_is_not_shared_through_the_cache(self):
        """A 가 채운 기억을 게스트와 B 가 써도 내 줄 표시는 각자 것이다."""
        a, b = make_user("표시A"), make_user("표시B")
        finish_round(a, 90)
        finish_round(b, 80)

        board_a = leaderboards.build(ALL_TIME, user=a)
        guest = leaderboards.build(ALL_TIME)
        board_b = leaderboards.build(ALL_TIME, user=b)

        self.assertEqual([r.is_me for r in board_a.rows], [True, False])
        self.assertEqual([r.is_me for r in guest.rows], [False, False])
        self.assertEqual([r.is_me for r in board_b.rows], [False, True])


@override_settings(CACHES=REMEMBER)
class MyRecordIsNeverLateTest(BoardCacheBase):
    """로그인한 사람의 기록은 기억과 상관없이 바로 반영된다."""

    def test_my_new_best_inside_the_list_shows_at_once(self):
        me, other = make_user("나"), make_user("남")
        finish_round(me, 100)
        finish_round(other, 150)
        self.assertEqual(names(leaderboards.build(ALL_TIME, user=me)), ["남", "나"])

        finish_round(me, 300)
        board = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual(names(board), ["나", "남"])
        self.assertEqual(board.rows[0].score, 300)
        self.assertTrue(board.rows[0].is_me)
        self.assertIsNone(board.me)

    def test_my_entries_change_shows_at_once(self):
        """최고점은 그대로인데 판 수만 늘어도 바로 보인다."""
        me = make_user("판수")
        finish_round(me, 100)
        self.assertEqual(leaderboards.build(ALL_TIME, user=me).rows[0].entries, 1)

        finish_round(me, 10)
        board = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual((board.rows[0].score, board.rows[0].entries), (100, 2))

    def test_weekly_board_also_updates_my_row_at_once(self):
        me = make_user("주간나")
        finish_round(me, 40)
        leaderboards.build(WEEKLY, user=me)
        finish_round(me, 70)
        board = leaderboards.build(WEEKLY, user=me)
        self.assertEqual((board.rows[0].score, board.rows[0].entries), (70, 2))

    def test_my_streak_change_shows_at_once(self):
        me = make_user("꾸준나")
        today = calendar_kst.today()
        daily(me, today - timedelta(days=1), best=5)
        self.assertEqual(leaderboards.build(STREAK, user=me).rows[0].score, 1)

        daily(me, today, best=7)
        board = leaderboards.build(STREAK, user=me)
        self.assertEqual((board.rows[0].score, board.rows[0].entries), (2, 12))

    def test_climbing_from_outside_into_top_20_shows_at_once(self):
        """21등이던 내가 1등이 되면 목록에 바로 나오고 me 줄은 비운다."""
        for i, user in enumerate(bulk_users("상위_", 20)):
            finish_round(user, 200 - i)
        me = make_user("올라감")
        finish_round(me, 1)

        before = leaderboards.build(ALL_TIME, user=me)
        self.assertFalse(any(r.is_me for r in before.rows))
        self.assertEqual(before.me.rank, 21)

        finish_round(me, 500)
        after = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual(after.rows[0].display_name, "올라감")
        self.assertTrue(after.rows[0].is_me)
        self.assertEqual(ranks(after), list(range(1, 21)))
        self.assertIsNone(after.me)

    def test_first_record_ever_that_lands_in_top_shows_at_once(self):
        """기억할 때 기록이 아예 없던 사람이 처음 한 판을 끝내도 바로 보인다."""
        finish_round(make_user("먼저"), 10)
        me = make_user("처음")
        self.assertIsNone(leaderboards.build(ALL_TIME, user=me).me)

        finish_round(me, 5)
        board = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual(names(board), ["먼저", "처음"])
        self.assertTrue(board.rows[1].is_me)

    def test_my_rank_outside_the_list_is_current(self):
        """목록 밖이면 me 의 등수는 지금 값이다. 기억한 목록 밖에서 나를 앞지른 사람도 센다."""
        crowd = bulk_users("배경_", 24)
        for i, user in enumerate(crowd):
            finish_round(user, 300 - i)
        me = make_user("밖의나")
        finish_round(me, 250)  # 300..277 중 250 보다 큰 것 24명 -> 25등
        self.assertEqual(leaderboards.build(ALL_TIME, user=me).me.rank, 25)

        # 나보다 아래였던 사람은 없으니, 새 사람이 나를 앞질러도 목록 밖이다.
        finish_round(make_user("추월"), 260)
        board = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual(board.me.rank, 26)
        self.assertTrue(board.me.is_me)

    def test_leaving_the_list_is_reflected_for_me(self):
        """목록 안에서 내 기록이 사라지면(판이 지워짐) 내 줄이 목록에서 빠진다."""
        me, other = make_user("사라짐"), make_user("남음")
        finish_round(me, 100)
        finish_round(other, 50)
        leaderboards.build(ALL_TIME, user=me)

        QuizSession.objects.filter(user=me).delete()
        board = leaderboards.build(ALL_TIME, user=me)
        self.assertEqual(names(board), ["남음"])
        self.assertIsNone(board.me)

    def test_zero_day_streak_user_does_not_rebuild_every_time(self):
        """꾸준함 0일인 사람은 목록에 못 드니 "20등 안인데 목록에 없다" 로 보면 안 된다."""
        finish_round(make_user("판만"), 10)
        daily(make_user("하루"), calendar_kst.today(), best=3)
        me = make_user("영일")
        daily(me, calendar_kst.today(), best=0)

        first = leaderboards.build(STREAK, user=me)
        self.assertEqual(first.me.score, 0)

        with mock.patch.object(
            leaderboards, "_cached_top", wraps=leaderboards._cached_top
        ) as spy:
            board = leaderboards.build(STREAK, user=me)
        self.assertEqual(names(board), ["하루"])
        self.assertEqual(board.me.score, 0)
        self.assertFalse(
            any(call.kwargs.get("refresh") for call in spy.call_args_list),
            "0일 사용자가 순위표를 열 때마다 목록을 새로 만든다",
        )


@override_settings(CACHES=REMEMBER)
class PeopleAreAlwaysCurrentTest(BoardCacheBase):
    """이름·그림·탈퇴는 기억과 상관없이 지금 값이다."""

    def setUp(self):
        super().setUp()
        self.star = make_user("별")
        self.other = make_user("달")
        finish_round(self.star, 100)
        finish_round(self.other, 50)
        leaderboards.build(ALL_TIME)  # 기억을 채운다

    def assert_star_avatar(self, board, expected: dict) -> None:
        row = next(r for r in board.rows if r.score == 100)
        self.assertEqual(row.avatar, expected)

    def test_new_nickname_shows_to_guest_and_others(self):
        self.star.display_name = "새별"
        self.star.save()
        self.assertEqual(names(leaderboards.build(ALL_TIME)), ["새별", "달"])
        self.assertEqual(names(leaderboards.build(ALL_TIME, user=self.other)), ["새별", "달"])

    def test_my_own_new_nickname_shows_to_me(self):
        self.star.display_name = "내새이름"
        self.star.save()
        self.assertEqual(leaderboards.build(ALL_TIME, user=self.star).rows[0].display_name, "내새이름")

    def test_my_new_nickname_outside_the_list_shows_in_me_row(self):
        """목록 밖이라 me 줄로 나오는 사람도 이름이 지금 값이다."""
        for i, user in enumerate(bulk_users("앞줄_", 20)):
            finish_round(user, 500 - i)
        me = make_user("뒤줄")
        finish_round(me, 1)
        self.assertEqual(leaderboards.build(ALL_TIME, user=me).me.display_name, "뒤줄")
        me.display_name = "뒤줄새이름"
        me.save()
        self.assertEqual(leaderboards.build(ALL_TIME, user=me).me.display_name, "뒤줄새이름")

    def test_preset_avatar_change_shows(self):
        type(self.star).objects.filter(pk=self.star.pk).update(avatar="a4")
        self.assert_star_avatar(leaderboards.build(ALL_TIME), {"type": "preset", "key": "a4"})

    def test_google_picture_added_and_removed_shows(self):
        url = "https://lh3.googleusercontent.com/a/sample-picture"
        type(self.star).objects.filter(pk=self.star.pk).update(avatar="", google_picture=url)
        self.assert_star_avatar(leaderboards.build(ALL_TIME), {"type": "photo", "url": url})

        type(self.star).objects.filter(pk=self.star.pk).update(google_picture="")
        board = leaderboards.build(ALL_TIME)
        row = next(r for r in board.rows if r.score == 100)
        self.assertEqual(row.avatar["type"], "preset", "지운 구글 사진이 남아 있다")

    def test_uploaded_photo_key_change_shows(self):
        key = uuid.UUID(int=12345)
        type(self.star).objects.filter(pk=self.star.pk).update(avatar="photo", avatar_photo_key=key)
        board = leaderboards.build(ALL_TIME)
        row = next(r for r in board.rows if r.score == 100)
        self.assertEqual(row.avatar["type"], "photo")
        self.assertIn(str(key), row.avatar["url"])

    def test_deleted_user_disappears_at_once(self):
        self.star.delete()
        board = leaderboards.build(ALL_TIME)
        self.assertEqual(names(board), ["달"])
        self.assertEqual(ranks(board), [1])

    def test_deactivated_user_disappears_at_once(self):
        type(self.star).objects.filter(pk=self.star.pk).update(is_active=False)
        for viewer in (None, self.other):
            board = leaderboards.build(ALL_TIME, user=viewer)
            self.assertEqual(names(board), ["달"])
            self.assertEqual(ranks(board), [1])

    def test_departed_user_frees_the_slot_for_the_21st(self):
        """20명 꽉 찬 목록에서 한 명이 빠지면, 빈 자리를 21등이 바로 채운다."""
        caches["boards"].clear()
        crowd = bulk_users("꽉_", 21)
        for i, user in enumerate(crowd):
            finish_round(user, 1000 - i)
        self.assertNotIn("꽉_020", names(leaderboards.build(ALL_TIME)))

        crowd[0].delete()
        board = leaderboards.build(ALL_TIME)
        self.assertNotIn("꽉_000", names(board))
        self.assertIn("꽉_020", names(board))
        self.assertEqual(ranks(board), list(range(1, 21)))


@override_settings(CACHES=REMEMBER)
class WeekChangeTest(BoardCacheBase):
    def test_new_week_does_not_use_last_weeks_memory(self):
        last_week_player = make_user("지난주")
        finish_round(last_week_player, 100)
        board = leaderboards.build(WEEKLY)
        self.assertEqual(names(board), ["지난주"])

        next_week = calendar_kst.today() + timedelta(days=7)
        with mock.patch.object(calendar_kst, "today", return_value=next_week):
            board = leaderboards.build(WEEKLY)
        self.assertEqual(names(board), [], "지난주 기억이 새 주에 나온다")
        self.assertEqual(board.period_start, calendar_kst.week_start(next_week))

    def test_all_time_board_is_not_reset_by_week(self):
        """전체 기간은 주와 상관없다. 주가 바뀌어도 기록이 남아 있다."""
        finish_round(make_user("오래"), 100)
        leaderboards.build(ALL_TIME)
        next_week = calendar_kst.today() + timedelta(days=7)
        with mock.patch.object(calendar_kst, "today", return_value=next_week):
            self.assertEqual(names(leaderboards.build(ALL_TIME)), ["오래"])


@override_settings(CACHES=REMEMBER)
class HttpBoardTest(BoardCacheBase):
    """HTTP 로 받아도 같은 규칙이다. 기억이 응답 모양을 바꾸지 않는다."""

    def test_response_shape_and_my_update_through_http(self):
        me = make_user("응답")
        finish_round(make_user("배경"), 80)
        finish_round(me, 50)
        self.client.force_login(me)

        first = self.client.get("/api/learning/leaderboards/all-time/").json()
        self.assertEqual([r["display_name"] for r in first["rows"]], ["배경", "응답"])

        finish_round(me, 90)
        second = self.client.get("/api/learning/leaderboards/all-time/").json()
        self.assertEqual([r["display_name"] for r in second["rows"]], ["응답", "배경"])
        self.assertEqual(set(second["rows"][0]), {"rank", "display_name", "avatar", "score", "entries", "is_me"})
        self.assertIsNone(second["me"])
