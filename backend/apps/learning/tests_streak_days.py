"""꾸준함 순위표를 날 수로 매기는 규칙.

계약:
    score   = 하루 점수(total) 가 0 보다 큰 날 수
    entries = 하루 점수 합
    순서    = score 내림 -> entries 내림 -> user pk 오름
    목록은 0일인 사람을 뺀다. 상위 TOP_SIZE 명. 목록 밖이면 me 에 내 줄
    (0일이어도 행이 있으면 나온다)과 목록 번호와 이어지는 등수.
    비활성 사용자는 목록에도, 앞선 사람 수에도 안 들어간다.

기대 순위는 **파이썬으로 따로 계산**해 비교한다. 구현과 같은 쿼리로 기대값을
만들면 둘이 같이 틀려도 초록불이다.
"""

from __future__ import annotations

import random
import secrets
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from . import leaderboards
from .models import DailyScore, QuizSession, SessionKind

User = get_user_model()

STREAK_URL = "/api/learning/leaderboards/streak/"
ALL_TIME_URL = "/api/learning/leaderboards/all-time/"

PASSWORD = secrets.token_urlsafe(16)
DAY0 = date(2026, 1, 1)


def make_user(name: str, *, active: bool = True) -> User:
    user = User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )
    if not active:
        user.is_active = False
        user.save(update_fields=["is_active"])
    return user


def days(user, *totals, start: int = 0) -> None:
    """하루 점수를 날짜순으로 쌓는다. 값은 daily_study_score 로 넣는다."""
    for i, study in enumerate(totals):
        DailyScore.objects.create(
            user=user, day=DAY0 + timedelta(days=start + i), daily_study_score=study
        )


def day(user, offset: int, *, best=None, study=0) -> None:
    DailyScore.objects.create(
        user=user,
        day=DAY0 + timedelta(days=offset),
        best_free_score=best,
        daily_study_score=study,
    )


def expected_order() -> list[tuple[int, int, int]]:
    """(pk, 날 수, 합) 을 파이썬으로 계산해 계약 순서대로. 0일도 포함."""
    stats: dict[int, list[int]] = {}
    for row in DailyScore.objects.select_related("user"):
        if not row.user.is_active:
            continue
        s = stats.setdefault(row.user_id, [0, 0])
        if row.total > 0:
            s[0] += 1
        s[1] += row.total
    return sorted(
        ((pk, n, total) for pk, (n, total) in stats.items()),
        key=lambda t: (-t[1], -t[2], t[0]),
    )


def rank_of(user) -> int:
    for i, (pk, _, _) in enumerate(expected_order()):
        if pk == user.pk:
            return i + 1
    raise AssertionError("기대 순서에 없는 사용자")


class DayCountScoreTest(TestCase):
    """score 는 날 수, entries 는 합이다."""

    def setUp(self):
        cache.clear()

    def test_many_small_days_beat_few_big_days(self):
        """나흘에 조금씩 한 사람이 이틀 몰아친 사람보다 위."""
        steady = make_user("steady")
        days(steady, 1, 1, 1, 1)
        burst = make_user("burst")
        days(burst, 50, 50)

        rows = leaderboards.build(leaderboards.STREAK).rows

        self.assertEqual([r.display_name for r in rows], ["steady", "burst"])
        self.assertEqual((rows[0].score, rows[0].entries), (4, 4))
        self.assertEqual((rows[1].score, rows[1].entries), (2, 100))

    def test_same_days_more_points_wins(self):
        """날 수가 같으면 합이 큰 쪽이 위. pk 가 먼저여도 뒤집힌다."""
        low = make_user("low")
        days(low, 1, 1, 1)
        high = make_user("high")
        days(high, 5, 5, 5)

        rows = leaderboards.build(leaderboards.STREAK).rows

        self.assertEqual([r.display_name for r in rows], ["high", "low"])

    def test_same_days_same_sum_lower_pk_first(self):
        """날 수·합이 같으면 먼저 가입한(pk 작은) 쪽이 위."""
        first = make_user("first")
        days(first, 2, 3)
        second = make_user("second")
        days(second, 4, 1)

        rows = leaderboards.build(leaderboards.STREAK).rows

        self.assertEqual([r.display_name for r in rows], ["first", "second"])
        self.assertEqual([r.rank for r in rows], [1, 2])

    def test_cancelled_day_is_not_counted(self):
        """best=5, study=-5 인 날은 total 0 이라 날 수에 안 들어간다."""
        cheat = make_user("cheat")
        day(cheat, 0, best=1)
        for offset in range(1, 6):
            day(cheat, offset, best=5, study=-5)
        honest = make_user("honest")
        day(honest, 0, best=1)
        day(honest, 1, best=1)

        rows = leaderboards.build(leaderboards.STREAK).rows

        self.assertEqual([r.display_name for r in rows], ["honest", "cheat"])
        self.assertEqual((rows[1].score, rows[1].entries), (1, 1))

    def test_negative_day_counts_zero_and_does_not_subtract(self):
        """마이너스 날은 날 수 0, 합에서도 빼지 않는다(0 으로 잘린다)."""
        user = make_user("neg")
        day(user, 0, best=4)
        day(user, 1, best=-9)
        day(user, 2, best=-3, study=1)

        row = leaderboards.build(leaderboards.STREAK).rows[0]

        self.assertEqual((row.score, row.entries), (1, 4))

    def test_null_best_with_study_only_counts(self):
        """best_free_score=None 에 일일공부만 있는 날도 하루다."""
        user = make_user("studyonly")
        day(user, 0, best=None, study=3)
        day(user, 1, best=None, study=2)
        day(user, 2, best=None, study=0)

        row = leaderboards.build(leaderboards.STREAK).rows[0]

        self.assertEqual((row.score, row.entries), (2, 5))

    def test_zero_day_users_are_not_listed(self):
        """행은 있지만 점수가 남은 날이 없는 사람은 목록에 없다."""
        ghost = make_user("ghost")
        day(ghost, 0, best=0)
        day(ghost, 1, best=-2)
        day(ghost, 2, best=None)
        real = make_user("real")
        days(real, 1)

        rows = leaderboards.build(leaderboards.STREAK).rows

        self.assertEqual([r.display_name for r in rows], ["real"])

    def test_api_body_carries_days_and_sum(self):
        """HTTP 응답도 score=날 수, entries=합."""
        user = make_user("api")
        days(user, 3, 0, 7)

        body = self.client.get(STREAK_URL).json()

        self.assertEqual(body["kind"], "streak")
        self.assertEqual(
            (body["rows"][0]["score"], body["rows"][0]["entries"]), (2, 10)
        )


class InactiveTest(TestCase):
    """비활성 사용자는 목록에도 앞선 사람 수에도 없다."""

    def setUp(self):
        cache.clear()

    def test_inactive_is_hidden_and_not_counted_ahead(self):
        gone = make_user("gone", active=False)
        days(gone, 9, 9, 9, 9, 9)
        fillers = [make_user(f"f{i:02d}") for i in range(leaderboards.TOP_SIZE)]
        for u in fillers:
            days(u, 1, 1)
        me = make_user("me")
        days(me, 1)

        board = leaderboards.build(leaderboards.STREAK, me)

        self.assertNotIn("gone", [r.display_name for r in board.rows])
        self.assertEqual(len(board.rows), leaderboards.TOP_SIZE)
        # 비활성을 세면 22 가 된다.
        self.assertEqual(board.me.rank, leaderboards.TOP_SIZE + 1)

    def test_inactive_me_gets_no_row(self):
        me = make_user("me", active=False)
        days(me, 3)

        self.assertIsNone(leaderboards.build(leaderboards.STREAK, me).me)


class TopBoundaryTest(TestCase):
    """20명 경계에서 내 등수가 목록 번호와 겹치거나 빠지지 않는다."""

    def setUp(self):
        cache.clear()
        # 20명 모두 3일. 합은 다르게 해서 합이 순위를 가르게 한다.
        self.top = []
        for i in range(leaderboards.TOP_SIZE):
            u = make_user(f"t{i:02d}")
            days(u, 10 + i, 10, 10)
            self.top.append(u)

    def test_twentieth_is_in_rows_and_me_is_none(self):
        """합이 가장 작은 3일짜리(20등)는 목록 안이고 me 는 비어 있다."""
        last = self.top[0]  # 합 30, 가장 작음

        board = leaderboards.build(leaderboards.STREAK, last)

        self.assertIsNone(board.me)
        self.assertEqual(board.rows[-1].display_name, "t00")
        self.assertEqual(board.rows[-1].rank, 20)
        self.assertTrue(board.rows[-1].is_me)

    def test_same_days_smaller_sum_is_21st(self):
        """3일이지만 합이 모두보다 작으면 21등. 20등과 겹치면 안 된다."""
        me = make_user("me")
        days(me, 1, 1, 1)

        board = leaderboards.build(leaderboards.STREAK, me)

        self.assertEqual(board.rows[-1].rank, 20)
        self.assertNotIn("me", [r.display_name for r in board.rows])
        self.assertEqual(board.me.rank, 21)
        self.assertEqual((board.me.score, board.me.entries), (3, 3))

    def test_same_days_same_sum_as_20th_but_higher_pk_is_21st(self):
        """20등과 날 수·합이 같아도 pk 가 크면 21등."""
        me = make_user("me")
        days(me, 10, 10, 10)  # t00 과 같은 (3, 30)

        board = leaderboards.build(leaderboards.STREAK, me)

        self.assertEqual(board.rows[-1].display_name, "t00")
        self.assertEqual(board.me.rank, 21)

    def test_more_days_small_sum_pushes_into_top(self):
        """4일이면 합이 작아도 1등. 20등이던 사람이 목록 밖으로 밀린다."""
        me = make_user("me")
        days(me, 1, 1, 1, 1)

        board = leaderboards.build(leaderboards.STREAK, me)
        self.assertEqual(board.rows[0].display_name, "me")
        self.assertIsNone(board.me)

        pushed = leaderboards.build(leaderboards.STREAK, self.top[0])
        self.assertEqual(pushed.me.rank, 21)

    def test_zero_day_me_ranks_after_all_scored(self):
        """0일인 나는 목록에 없지만 me 로 나오고, 점수 가진 사람 뒤다."""
        me = make_user("me")
        day(me, 0, best=-4)

        board = leaderboards.build(leaderboards.STREAK, me)

        self.assertEqual(board.me.rank, 21)
        self.assertEqual((board.me.score, board.me.entries), (0, 0))

    def test_zero_day_users_rank_by_pk_among_themselves(self):
        """0일끼리는 pk 순으로 21, 22, 23 - 같은 등수로 뭉치지 않는다."""
        zeros = [make_user(f"z{i}") for i in range(3)]
        for u in zeros:
            day(u, 0, best=5, study=-5)

        ranks = [leaderboards.build(leaderboards.STREAK, u).me.rank for u in zeros]

        self.assertEqual(ranks, [21, 22, 23])

    def test_no_rows_means_no_me(self):
        """행이 하나도 없는 사람은 me 가 없다."""
        me = make_user("me")

        self.assertIsNone(leaderboards.build(leaderboards.STREAK, me).me)


class RandomAgreementTest(TestCase):
    """무작위 데이터에서 목록과 me 등수가 파이썬 계산과 항상 같다."""

    def setUp(self):
        cache.clear()

    def test_rows_and_every_me_rank_match_python(self):
        rng = random.Random(20260926)
        users = []
        for i in range(30):
            u = make_user(f"r{i:02d}", active=rng.random() > 0.1)
            users.append(u)
            for offset in range(rng.randint(0, 6)):
                best = rng.choice([None, -5, -1, 0, 1, 3, 5, 8])
                study = rng.choice([-5, 0, 0, 1, 2, 5])
                day(u, offset, best=best, study=study)

        expected = expected_order()
        listed = [t for t in expected if t[1] > 0][: leaderboards.TOP_SIZE]

        board = leaderboards.build(leaderboards.STREAK)
        got = [(r.score, r.entries) for r in board.rows]
        self.assertEqual(got, [(n, s) for _, n, s in listed])
        self.assertEqual([r.rank for r in board.rows], list(range(1, len(listed) + 1)))

        listed_pks = {pk for pk, _, _ in listed}
        for u in users:
            if not u.is_active or not DailyScore.objects.filter(user=u).exists():
                continue
            b = leaderboards.build(leaderboards.STREAK, u)
            with self.subTest(user=u.display_name):
                if u.pk in listed_pks:
                    self.assertIsNone(b.me)
                else:
                    self.assertEqual(b.me.rank, rank_of(u))


class OtherBoardsUnchangedTest(TestCase):
    """최고점 순위표는 그대로: score=최고 한 판, entries=판 수."""

    def setUp(self):
        cache.clear()

    def test_all_time_is_best_round_and_round_count(self):
        from django.utils import timezone

        user = make_user("rounds")
        for score in (3, 9, 4):
            now = timezone.now()
            QuizSession.objects.create(
                user=user,
                kind=SessionKind.FREE,
                token_id=secrets.token_urlsafe(12),
                started_at=now - timedelta(seconds=60),
                finished_at=now,
                score=score,
                answered=10,
                correct=score,
                skipped=0,
            )
        # 꾸준함 재료가 섞여도 최고점 순위표는 안 흔들린다.
        days(user, 5, 5, 5, 5)

        row = self.client.get(ALL_TIME_URL).json()["rows"][0]

        self.assertEqual((row["score"], row["entries"]), (9, 3))
