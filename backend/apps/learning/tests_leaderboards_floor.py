"""순위표의 음수 바닥 - 최고 한 판이 음수여도 순위표에서는 0점으로 본다.

지키는 것.

    1. 최고 한 판이 음수인 사람은 이번 주·전체 순위표에 0점으로 나오고
       줄이 사라지지 않는다. 양수 판이 하나라도 있으면 그 점수다.
    2. 0점으로 올려진 음수는 실제 0점과 동점이다. first_at, 그 다음
       user 로 갈린다.
    3. 목록 밖 내 등수(HAVING 으로 세는 경로)가 목록 번호와 같은 값을 본다.
    4. 판 기록·내 기록의 점수는 음수 그대로다.
    5. 꾸준함 순위표는 영향이 없다.

이번 주 판은 이번 주 첫 시각에서 잰다. timezone.now() 에서 빼면 월요일
새벽에 지난주로 넘어가 이번 주 순위표에서 빠진다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from . import calendar_kst, leaderboards, record
from .models import DailyScore, QuizSession, SessionKind
from .tests_leaderboards_edge2 import (
    ALL_TIME_URL,
    STREAK_URL,
    WEEKLY_URL,
    RankAgreementMixin,
    bulk_users,
    daily,
    finish_round,
    make_user,
)

BEST_BOARDS = (leaderboards.WEEKLY, leaderboards.ALL_TIME)
BEST_URLS = (WEEKLY_URL, ALL_TIME_URL)
HISTORY_URL = "/api/learning/history/"


def this_week(minutes: int):
    """이번 주 첫 시각에서 minutes 분 뒤. 작을수록 먼저 끝낸 판이다."""
    begins = calendar_kst.day_begins(calendar_kst.this_week_start())
    return begins + timedelta(minutes=minutes)


def last_week():
    """이번 주 순위표 창의 바로 바깥."""
    return calendar_kst.day_begins(calendar_kst.this_week_start()) - timedelta(hours=1)


def scores_of(board) -> list[int]:
    return [row.score for row in board.rows]


def names_of(board) -> list[str]:
    return [row.display_name for row in board.rows]


class FloorCase(RankAgreementMixin, TestCase):
    """스로틀 통이 테스트 사이로 새지 않게 비운다."""

    def setUp(self):
        cache.clear()


class NegativeBestRoundTest(FloorCase):
    """바닥이 어디까지 올리고 어디부터 안 올리는가."""

    def test_only_negative_rounds_show_as_zero_on_both_boards(self):
        """음수만 낸 사람은 0점으로 줄이 남는다. 판 수는 음수 판까지 센다."""
        user = make_user("음수만")
        finish_round(user, -5, when=this_week(1))
        finish_round(user, -9, when=this_week(2))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=user)

                self.assertEqual(len(board.rows), 1, "음수라고 줄이 사라졌다")
                row = board.rows[0]
                self.assertEqual(row.score, 0)
                self.assertEqual(row.rank, 1)
                self.assertEqual(row.entries, 2, "판 수가 깎였다")
                self.assertTrue(row.is_me)
                self.assertIsNone(board.me)

    def test_api_response_for_guest_has_no_negative_score(self):
        """화면이 받는 값이 0 이다. 게스트도 음수를 보지 못한다."""
        user = make_user("응답음수")
        finish_round(user, -30, when=this_week(1))

        for url in BEST_URLS:
            with self.subTest(url=url):
                res = self.client.get(url)

                self.assertEqual(res.status_code, 200)
                body = res.json()
                self.assertEqual([row["score"] for row in body["rows"]], [0])
                self.assertIsNone(body["me"])

    def test_api_me_row_outside_top_is_zero(self):
        """목록 밖 me 줄도 화면에 0 으로 간다."""
        for i, other in enumerate(bulk_users("상위_", leaderboards.TOP_SIZE)):
            finish_round(other, 10 + i, when=this_week(1))
        loser = make_user("밖의음수")
        finish_round(loser, -30, when=this_week(2))

        self.client.force_login(loser)
        for url in BEST_URLS:
            with self.subTest(url=url):
                me = self.client.get(url).json()["me"]

                self.assertEqual(me["score"], 0)
                self.assertEqual(me["rank"], leaderboards.TOP_SIZE + 1)
                self.assertTrue(me["is_me"])

    def test_a_positive_round_is_kept_as_is(self):
        """양수 판이 하나라도 있으면 그 점수다. 음수에 끌려 내려가지 않는다."""
        user = make_user("섞인사람")
        finish_round(user, -5, when=this_week(1))
        finish_round(user, 3, when=this_week(2))
        finish_round(user, -9, when=this_week(3))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertEqual(scores_of(leaderboards.build(kind)), [3])

    def test_a_true_zero_round_stays_zero(self):
        user = make_user("진짜영점")
        finish_round(user, 0, when=this_week(1))
        finish_round(user, -2, when=this_week(2))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertEqual(scores_of(leaderboards.build(kind)), [0])

    def test_the_floor_does_not_conjure_a_row_for_someone_without_rounds(self):
        """바닥이 '판이 없는 사람' 까지 0점으로 올리면 안 된다."""
        nobody = make_user("판없음")
        daily_only = make_user("일일공부만")
        finish_round(daily_only, -5, when=this_week(1), kind=SessionKind.DAILY)

        for kind in BEST_BOARDS:
            for user in (nobody, daily_only):
                with self.subTest(kind=kind, user=user.display_name):
                    board = leaderboards.build(kind, user=user)
                    self.assertEqual(board.rows, [])
                    self.assertIsNone(board.me)

    def test_last_week_negative_is_outside_the_weekly_window(self):
        """지난주 음수 판은 이번 주 줄을 만들지 않는다. 전체에는 0 으로 있다."""
        user = make_user("지난주음수")
        finish_round(user, -5, when=last_week())

        self.assertEqual(leaderboards.build(leaderboards.WEEKLY).rows, [])
        self.assertEqual(scores_of(leaderboards.build(leaderboards.ALL_TIME)), [0])

    def test_last_week_positive_does_not_lift_this_week(self):
        """창마다 따로 올린다. 이번 주가 음수면 이번 주는 0, 전체는 지난주 점수."""
        user = make_user("지난주양수")
        finish_round(user, 50, when=last_week())
        finish_round(user, -5, when=this_week(1))

        self.assertEqual(scores_of(leaderboards.build(leaderboards.WEEKLY)), [0])
        self.assertEqual(scores_of(leaderboards.build(leaderboards.ALL_TIME)), [50])

    def test_inactive_negative_user_is_still_hidden(self):
        """바닥이 비활성 계정 필터를 지나치면 탈퇴자가 0점으로 돌아온다."""
        user = make_user("탈퇴음수")
        finish_round(user, -5, when=this_week(1))
        user.is_active = False
        user.save(update_fields=["is_active"])

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertEqual(leaderboards.build(kind).rows, [])


class FloorTieBreakTest(FloorCase):
    """음수와 실제 0점의 동점. first_at, 그 다음 user."""

    def build_both(self):
        return [leaderboards.build(kind) for kind in BEST_BOARDS]

    def test_earlier_negative_beats_later_true_zero(self):
        early = make_user("먼저음수")
        late = make_user("나중영점")
        finish_round(early, -5, when=this_week(1))
        finish_round(late, 0, when=this_week(2))

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(names_of(board), ["먼저음수", "나중영점"])
                self.assertEqual(scores_of(board), [0, 0])

    def test_earlier_true_zero_beats_later_negative(self):
        early = make_user("먼저영점")
        late = make_user("나중음수")
        finish_round(early, 0, when=this_week(1))
        finish_round(late, -5, when=this_week(2))

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(names_of(board), ["먼저영점", "나중음수"])

    def test_deeper_negative_is_not_ranked_lower_than_shallow_negative(self):
        """-99 와 -1 은 같은 0점이다. 원래 값의 크기로 순서가 갈리면 안 된다."""
        deep = make_user("깊은음수")
        shallow = make_user("얕은음수")
        finish_round(deep, -99, when=this_week(1))
        finish_round(shallow, -1, when=this_week(2))

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(names_of(board), ["깊은음수", "얕은음수"])

    def test_same_first_at_falls_to_user_either_way_round(self):
        """시각까지 같으면 pk 가 작은 쪽. 음수와 0 어느 쪽이 먼저 가입했든 같다."""
        moment = this_week(1)
        low_negative = make_user("앞번호음수")
        high_zero = make_user("뒷번호영점")
        low_zero = make_user("앞번호영점")
        high_negative = make_user("뒷번호음수")

        finish_round(low_negative, -5, when=moment)
        finish_round(high_zero, 0, when=moment)
        finish_round(low_zero, 0, when=moment)
        finish_round(high_negative, -5, when=moment)

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(
                    names_of(board),
                    ["앞번호음수", "뒷번호영점", "앞번호영점", "뒷번호음수"],
                )

    def test_first_at_counts_the_negative_round_too(self):
        """첫 판 시각은 음수 판까지 본다. 먼저 음수를 낸 뒤 0 을 낸 사람이 앞이다."""
        starter = make_user("음수로시작")
        other = make_user("중간영점")
        finish_round(starter, -9, when=this_week(1))
        finish_round(starter, 0, when=this_week(10))
        finish_round(other, 0, when=this_week(5))

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(names_of(board), ["음수로시작", "중간영점"])

    def test_one_point_beats_an_earlier_floor(self):
        """바닥은 동점만 만든다. 1점은 먼저 끝낸 음수보다 위다."""
        floored = make_user("먼저낸음수")
        scorer = make_user("늦은일점")
        finish_round(floored, -5, when=this_week(1))
        finish_round(scorer, 1, when=this_week(100))

        for board in self.build_both():
            with self.subTest(kind=board.kind):
                self.assertEqual(names_of(board), ["늦은일점", "먼저낸음수"])
                self.assertEqual(scores_of(board), [1, 0])


class FloorOutsideTopTest(FloorCase):
    """목록 밖의 0점 동점자. 내 등수를 HAVING 으로 세는 경로."""

    def mixed_group(self, count: int) -> list:
        """음수와 실제 0점을 번갈아 끝낸 사람들. 앞사람일수록 먼저 끝냈다."""
        people = bulk_users("바닥_", count)
        for i, user in enumerate(people):
            finish_round(user, 0 if i % 2 else -(i + 1), when=this_week(i + 1))
        return people

    def test_every_rank_matches_list_order_past_top(self):
        """번호가 뭉치거나 어긋나면 안 된다. 목록 안팎이 한 번호열이다."""
        count = leaderboards.TOP_SIZE + 7
        people = self.mixed_group(count)

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                ranks = self.ranks_of(kind, people)

                self.assertRanksFormASequence(ranks, f" ({kind})")
                self.assertEqual(
                    [ranks[user.pk] for user in people], list(range(1, count + 1))
                )

    def test_in_list_people_agree_with_the_having_count(self):
        """목록에 있는 사람도 세기 쿼리로 재면 같은 번호여야 한다."""
        people = self.mixed_group(10)

        for kind in BEST_BOARDS:
            for position, user in enumerate(people, start=1):
                with self.subTest(kind=kind, position=position):
                    item, ahead = leaderboards._my_standing(kind, user)

                    self.assertEqual(item["score"], 0)
                    self.assertEqual(ahead + 1, position)

    def test_negative_outside_top_counts_true_zeros_ahead(self):
        """음수인 내 줄의 동점 무리에 실제 0점이 들어온다."""
        zeros = bulk_users("영점_", leaderboards.TOP_SIZE + 5)
        for i, user in enumerate(zeros):
            finish_round(user, 0, when=this_week(i + 1))
        loser = make_user("중간음수")
        finish_round(loser, -7, when=this_week(leaderboards.TOP_SIZE + 2) + timedelta(seconds=30))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=loser)

                self.assertEqual(board.me.score, 0)
                self.assertEqual(board.me.rank, leaderboards.TOP_SIZE + 3)

    def test_true_zero_outside_top_counts_negatives_ahead(self):
        """반대 방향. 내가 실제 0점이면 먼저 낸 음수들이 앞이다."""
        negatives = bulk_users("음수_", leaderboards.TOP_SIZE + 5)
        for i, user in enumerate(negatives):
            finish_round(user, -(i + 1), when=this_week(i + 1))
        zero = make_user("늦은영점")
        finish_round(zero, 0, when=this_week(1000))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=zero)

                self.assertEqual(board.me.rank, leaderboards.TOP_SIZE + 6)

    def test_positives_stay_above_an_early_floor_outside_top(self):
        """먼저 끝낸 음수라도 나중에 양수를 낸 사람 앞에 못 간다."""
        scorers = bulk_users("양수_", leaderboards.TOP_SIZE + 3)
        for i, user in enumerate(scorers):
            finish_round(user, 1, when=this_week(100 + i))
        loser = make_user("맨먼저음수")
        finish_round(loser, -5, when=this_week(1))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=loser)

                self.assertEqual(board.me.rank, leaderboards.TOP_SIZE + 4)

    def test_same_moment_floor_group_is_numbered_by_user(self):
        """점수·first_at 이 전부 같은 무리는 user 로만 갈린다. 번호가 뭉치면 안 된다."""
        people = bulk_users("동시_", leaderboards.TOP_SIZE + 5)
        moment = this_week(1)
        for i, user in enumerate(people):
            finish_round(user, 0 if i % 2 else -3, when=moment)

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                ranks = self.ranks_of(kind, people)

                self.assertRanksFormASequence(ranks, f" ({kind})")
                self.assertEqual(
                    [ranks[user.pk] for user in sorted(people, key=lambda u: u.pk)],
                    list(range(1, len(people) + 1)),
                )


class AllNegativeBoardTest(FloorCase):
    """전원이 음수인 순위표."""

    def test_everyone_is_zero_and_ordered_by_who_finished_first(self):
        people = bulk_users("전원음수_", leaderboards.TOP_SIZE + 4)
        for i, user in enumerate(people):
            # 먼저 끝낸 사람일수록 점수를 낮게 둔다. 원래 값으로 정렬하면
            # 순서가 정확히 뒤집혀서 바로 드러난다.
            finish_round(user, -(100 - i), when=this_week(i + 1))

        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind)

                self.assertEqual(len(board.rows), leaderboards.TOP_SIZE)
                self.assertEqual(set(scores_of(board)), {0})
                self.assertEqual(
                    names_of(board),
                    [user.display_name for user in people[: leaderboards.TOP_SIZE]],
                )
                self.assertEqual(
                    [row.rank for row in board.rows],
                    list(range(1, leaderboards.TOP_SIZE + 1)),
                )

                ranks = self.ranks_of(kind, people)
                self.assertEqual(
                    [ranks[user.pk] for user in people],
                    list(range(1, len(people) + 1)),
                )

    def test_all_negative_board_over_http(self):
        people = bulk_users("응답전원_", 3)
        for i, user in enumerate(people):
            finish_round(user, -(i + 1), when=this_week(i + 1))

        for url in BEST_URLS:
            with self.subTest(url=url):
                rows = self.client.get(url).json()["rows"]

                self.assertEqual([row["score"] for row in rows], [0, 0, 0])
                self.assertEqual([row["rank"] for row in rows], [1, 2, 3])


class RecordsKeepTheRealScoreTest(FloorCase):
    """바뀌는 것은 순위표뿐이다. 판 기록과 내 기록은 음수 그대로다."""

    def save_negative_round(self, user, score: int, token: str):
        started = timezone.now() - timedelta(seconds=90)
        return record.save_round(
            user,
            {
                "kind": SessionKind.FREE,
                "token_id": token,
                "started_at": started,
                "score": score,
                "answered": 5,
                "correct": 0,
                "skipped": 0,
                "answers": [],
            },
        )

    def test_round_row_keeps_the_negative_score(self):
        """순위표를 만들어도 판 기록이 고쳐지지 않는다."""
        user = make_user("기록음수")
        saved = self.save_negative_round(user, -5, secrets.token_urlsafe(12))

        self.assertEqual(saved.score, -5)
        for kind in BEST_BOARDS:
            leaderboards.build(kind, user=user)

        saved.refresh_from_db()
        self.assertEqual(saved.score, -5)
        self.assertEqual(QuizSession.objects.get(pk=saved.pk).score, -5)

    def test_daily_row_keeps_the_negative_best(self):
        """하루 줄의 최고 판도 음수다. 합계만 0 밑으로 안 내려간다."""
        user = make_user("하루음수")
        self.save_negative_round(user, -5, secrets.token_urlsafe(12))
        self.save_negative_round(user, -9, secrets.token_urlsafe(12))

        row = DailyScore.objects.get(user=user)
        self.assertEqual(row.best_free_score, -5)
        self.assertEqual(row.total, 0)

    def test_history_screen_shows_the_negative_score(self):
        """내 기록 화면에는 낸 점수 그대로 간다."""
        user = make_user("내기록음수")
        self.save_negative_round(user, -5, secrets.token_urlsafe(12))

        self.client.force_login(user)
        body = self.client.get(HISTORY_URL).json()

        self.assertEqual([item["score"] for item in body["rounds"]], [-5])
        self.assertIn(-5, [day["best_round"] for day in body["days"]])
        self.assertEqual({day["total"] for day in body["days"]}, {0})


class StreakIsUnaffectedTest(FloorCase):
    """꾸준함은 하루 줄을 보므로 한 판 바닥과 무관하다."""

    def test_negative_only_days_are_not_counted(self):
        user = make_user("음수날만")
        today = calendar_kst.today()
        daily(user, today, best=-5)
        daily(user, today - timedelta(days=1), best=-9)

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(board.rows, [], "0일인 사람이 목록에 올랐다")
        self.assertEqual(board.me.score, 0)
        self.assertEqual(board.me.entries, 0)

    def test_a_negative_round_does_not_create_a_streak_row(self):
        """판 기록만 있고 하루 줄이 없으면 꾸준함에는 아무것도 안 나온다."""
        user = make_user("판만음수")
        finish_round(user, -5, when=this_week(1))

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(board.rows, [])
        self.assertIsNone(board.me)

    def test_negative_best_still_subtracts_from_the_day_total(self):
        """하루 합은 음수 판까지 더한 뒤 자른다. 판을 먼저 0 으로 올리면 합이 부푼다."""
        user = make_user("일일로만회")
        daily(user, calendar_kst.today(), best=-5, study=10)

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(scores_of(board), [1])
        self.assertEqual(board.rows[0].entries, 5)

    def test_streak_api_is_not_floored_into_rows(self):
        user = make_user("응답꾸준")
        daily(user, calendar_kst.today(), best=-5)

        body = self.client.get(STREAK_URL).json()

        self.assertEqual(body["rows"], [])
