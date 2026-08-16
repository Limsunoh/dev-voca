"""순위표 경계 - 깨뜨리려고 쓴 테스트.

tests_leaderboards.py 가 규칙이 지켜지는지를 본다면, 여기는 규칙이
**어디서 갈리는지**를 본다. 겹치는 시나리오는 안 쓴다.

    - 등수 겹침: me.rank 가 rows 의 어떤 rank 와도 같으면 안 된다
    - 목록 경계: 정확히 20등 / 21등 / 동점이 경계에 걸릴 때
    - KST 주 경계: 월요일 0시 정각 직전 1마이크로초, 지난주 일요일 끝
    - total 등가성: 마이너스·null·0 을 섞은 무작위 입력에서 파이썬 == SQL
    - 0점 여럿: 활동일이 다르면 등수가 갈려야 한다
    - 아바타: 프리셋 / 구글 사진만 / 둘 다 없음 / 목록에 없는 값
    - API: 게스트, 빈 순위표, 탈퇴 계정, 잘못된 종류
"""

from __future__ import annotations

import random
import secrets
from datetime import UTC, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from . import calendar_kst, leaderboards
from .models import DailyScore, QuizSession, SessionKind

User = get_user_model()

WEEKLY_URL = "/api/learning/leaderboards/weekly/"
ALL_TIME_URL = "/api/learning/leaderboards/all-time/"
STREAK_URL = "/api/learning/leaderboards/streak/"

PASSWORD = secrets.token_urlsafe(16)


def make_user(name: str) -> User:
    return User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def bulk_users(prefix: str, count: int) -> list:
    """비밀번호 해싱 없이 여럿. 아무도 로그인하지 않는 테스트용."""
    return User.objects.bulk_create(
        User(email=f"{prefix}{i:03d}@example.com", display_name=f"{prefix}{i:03d}")
        for i in range(count)
    )


def finish_round(user, score: int, *, when=None, kind=SessionKind.FREE) -> QuizSession:
    moment = when or timezone.now()
    return QuizSession.objects.create(
        user=user,
        kind=kind,
        token_id=secrets.token_urlsafe(12),
        started_at=moment - timedelta(seconds=90),
        finished_at=moment,
        score=score,
        answered=10,
        correct=max(score, 0),
        skipped=0,
    )


def daily(user, day, *, best=None, study=0) -> DailyScore:
    return DailyScore.objects.create(
        user=user, day=day, best_free_score=best, daily_study_score=study
    )


class BoardConsistencyMixin:
    """어떤 순위표든 항상 참이어야 하는 것.

    등수가 겹치면 화면에 같은 등수가 둘 나온다. 이 검사를 시나리오마다
    다시 쓰면 빠뜨리는 곳이 생기므로 한 곳에 모은다.
    """

    def assertBoardIsSane(self, board, *, expect_me_user=None):
        ranks = [row.rank for row in board.rows]

        self.assertEqual(
            ranks, list(range(1, len(ranks) + 1)), "목록 번호가 1부터 이어지지 않는다"
        )
        self.assertLessEqual(len(ranks), leaderboards.TOP_SIZE, "20명을 넘겼다")

        names = [row.display_name for row in board.rows]
        self.assertEqual(len(names), len(set(names)), "같은 사람이 목록에 두 번 있다")

        marked = [row for row in board.rows if row.is_me]
        self.assertLessEqual(len(marked), 1, "목록에 내 줄 표시가 둘이다")

        if board.me is not None:
            self.assertNotIn(board.me.rank, ranks, "내 등수가 목록 등수와 겹친다")
            self.assertEqual(marked, [], "목록에 있는데 내 줄도 나왔다")
            self.assertGreater(board.me.rank, 0, "등수가 0 이하다")
            self.assertTrue(board.me.is_me, "me 인데 is_me 가 거짓이다")
            if expect_me_user is not None:
                self.assertEqual(board.me.display_name, expect_me_user.display_name)


class RankOverlapTest(BoardConsistencyMixin, TestCase):
    """동점자를 경계에 몰아넣고 등수가 겹치는 입력을 찾는다."""

    def setUp(self):
        cache.clear()

    def test_exactly_twenty_first_place_when_everyone_ties(self):
        """21명 전원 동점. 21번째가 자기를 21등으로 봐야 한다.

        경계다 - 20명은 목록에 들어가고 한 명만 밖이다. 세는 쪽이 동점자를
        한 명이라도 놓치면 곧바로 20등이 되어 목록과 겹친다.
        """
        now = timezone.now()
        people = bulk_users("동점21_", 21)
        for i, user in enumerate(people):
            finish_round(user, 30, when=now - timedelta(minutes=21 - i))

        board = leaderboards.build(leaderboards.ALL_TIME, user=people[-1])

        self.assertBoardIsSane(board, expect_me_user=people[-1])
        self.assertEqual(board.me.rank, 21)

    def test_the_twentieth_user_is_inside_and_has_no_me_row(self):
        """정확히 20등이면 목록 안이다. me 는 비어야 한다."""
        now = timezone.now()
        people = bulk_users("경계20_", 25)
        for i, user in enumerate(people):
            finish_round(user, 100 - i, when=now - timedelta(minutes=25 - i))

        twentieth = people[19]
        board = leaderboards.build(leaderboards.ALL_TIME, user=twentieth)

        self.assertBoardIsSane(board)
        self.assertIsNone(board.me, "목록 안인데 내 줄이 또 나왔다")
        self.assertTrue(board.rows[19].is_me, "20등이 나인데 표시가 없다")
        self.assertEqual(board.rows[19].rank, 20)

    def test_a_tie_group_straddling_the_cut_does_not_overlap(self):
        """동점 무리가 20/21 경계에 걸칠 때.

        19명이 앞서고 그 뒤 6명이 같은 점수다. 그중 하나는 20등으로 목록
        안, 나머지 다섯은 밖이다. 밖의 다섯이 각자 21~25등이어야 한다.
        """
        now = timezone.now()
        ahead = bulk_users("앞선_", 19)
        for i, user in enumerate(ahead):
            finish_round(user, 90 - i, when=now - timedelta(hours=5))

        tied = bulk_users("걸친_", 6)
        for i, user in enumerate(tied):
            finish_round(user, 10, when=now - timedelta(minutes=6 - i))

        seen = []
        for offset, user in enumerate(tied[1:], start=21):
            board = leaderboards.build(leaderboards.ALL_TIME, user=user)
            self.assertBoardIsSane(board, expect_me_user=user)
            self.assertEqual(board.me.rank, offset, f"{user.display_name} 등수가 틀리다")
            seen.append(board.me.rank)

        self.assertEqual(sorted(seen), [21, 22, 23, 24, 25], "밖의 등수가 겹친다")

    def test_weekly_rank_is_consistent_for_a_tie_outside(self):
        """주간 순위표도 같은 규칙이어야 한다. 종류마다 따로 세지 않는다."""
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())
        people = bulk_users("주간동점_", 24)
        for i, user in enumerate(people):
            finish_round(user, 8, when=monday + timedelta(minutes=i))

        board = leaderboards.build(leaderboards.WEEKLY, user=people[-1])

        self.assertBoardIsSane(board, expect_me_user=people[-1])
        self.assertEqual(board.me.rank, 24)

    def test_every_user_outside_the_top_gets_a_distinct_rank(self):
        """목록 밖 전원의 등수가 서로 달라야 한다.

        한 사람만 확인하면 "우연히 맞은" 경우를 못 거른다. 동점과 서로
        다른 점수를 섞어 30명을 만들고 밖 사람 전부를 본다.
        """
        now = timezone.now()
        people = bulk_users("전수_", 30)
        # 앞 10명은 서로 다른 점수, 뒤 20명은 전부 5점 동점.
        for i, user in enumerate(people):
            score = 50 - i if i < 10 else 5
            finish_round(user, score, when=now - timedelta(minutes=30 - i))

        outside_ranks = []
        for user in people[20:]:
            board = leaderboards.build(leaderboards.ALL_TIME, user=user)
            self.assertBoardIsSane(board, expect_me_user=user)
            outside_ranks.append(board.me.rank)

        self.assertEqual(
            sorted(outside_ranks),
            list(range(21, 31)),
            f"목록 밖 등수가 겹치거나 빠졌다: {outside_ranks}",
        )

    # 꾸준함 전수 검사는 edge2.py 의 StreakRankSweepTest 에 있다. 거기
    # RankAgreementMixin 이 목록 안 사람까지 검사한다 - 여기서 하면
    # 목록 안 20명은 me 가 None 이라 단언이 통째로 스킵된다.


class HugeTieGroupTest(BoardConsistencyMixin, TestCase):
    """동점 무리가 클 때.

    한때 동점자를 한도만큼 꺼내 그 안에서 자리를 찾았고, 그래서 한도를
    넘는 사람들이 전부 같은 등수로 뭉쳤다. 지금은 세기만 하므로 규모와
    무관해야 한다.
    """

    def setUp(self):
        cache.clear()

    def _tied_crowd(self, count: int, *, score: int = 25):
        """전원 동점. 인덱스가 작을수록 먼저 달성했다(= 등수가 앞)."""
        now = timezone.now()
        people = bulk_users("거대동점_", count)
        for i, user in enumerate(people):
            finish_round(user, score, when=now - timedelta(minutes=count * 2 - i))
        return people

    def test_sixty_tied_users_still_rank_correctly(self):
        """60명 동점. 예전 한도였던 자리를 고정해 둔다."""
        people = self._tied_crowd(60)

        board = leaderboards.build(leaderboards.ALL_TIME, user=people[-1])

        self.assertBoardIsSane(board, expect_me_user=people[-1])
        self.assertEqual(board.me.rank, 60)

    def test_a_tie_group_over_fetch_size_still_ranks_the_last_user(self):
        """61명 동점. 61번째가 61등이어야 한다.

        예전 한도(60) 바로 위다. 동점자를 꺼내 세던 시절에는 여기서부터
        잘려나간 사람 전원이 같은 등수로 뭉쳤다.
        """
        count = 61
        people = self._tied_crowd(count)

        board = leaderboards.build(leaderboards.ALL_TIME, user=people[-1])

        self.assertBoardIsSane(board, expect_me_user=people[-1])
        self.assertEqual(board.me.rank, count, "동점 무리가 잘려 등수가 무너졌다")

    def test_everyone_outside_a_huge_tie_group_keeps_a_distinct_rank(self):
        """동점 100명. 목록 밖 전원이 서로 다른 등수여야 한다."""
        people = self._tied_crowd(100)

        ranks = []
        for index in (20, 40, 59, 60, 61, 75, 99):
            user = people[index]
            board = leaderboards.build(leaderboards.ALL_TIME, user=user)
            self.assertBoardIsSane(board, expect_me_user=user)
            ranks.append((index, board.me.rank))

        self.assertEqual(
            ranks,
            [(i, i + 1) for i, _ in ranks],
            f"동점 무리에서 등수가 무너진다: {ranks}",
        )

    def test_users_beyond_the_slice_do_not_share_one_rank(self):
        """슬라이스 밖 사람들이 전부 같은 등수로 뭉치면 안 된다.

        등수가 조금 부정확한 것과 다르다. 61등부터 100등까지가 전원
        '61등' 을 보면, 40명이 서로를 앞질렀는지 알 수 없어 순위표가
        동기를 못 준다 - 더 잘해도 숫자가 안 움직인다.
        """
        people = self._tied_crowd(100)

        # _tied_crowd 는 인덱스가 작을수록 먼저 달성했다 = 앞 등수.
        picked = (61, 70, 80, 99)
        ranks = [
            leaderboards.build(leaderboards.ALL_TIME, user=people[i]).me.rank
            for i in picked
        ]

        self.assertEqual(
            ranks,
            [i + 1 for i in picked],
            f"슬라이스 밖 등수가 어긋난다: {ranks}",
        )

    def test_a_huge_tie_after_leaders_does_not_collapse(self):
        """앞선 사람 19명 + 동점 80명. 잘린 동점자가 20등으로 계산되면 안 된다.

        전원 동점일 때만 나는 문제가 아니다. 앞선 사람이 있으면 무너진
        등수가 1 이 아니라 20 이 되어, 목록 마지막 줄과 겹친다.
        """
        now = timezone.now()
        leaders = bulk_users("선두_", 19)
        for i, user in enumerate(leaders):
            finish_round(user, 90 - i, when=now - timedelta(hours=10))

        tied = bulk_users("무리_", 80)
        for i, user in enumerate(tied):
            finish_round(user, 7, when=now - timedelta(minutes=200 - i))

        last = tied[-1]
        board = leaderboards.build(leaderboards.ALL_TIME, user=last)

        self.assertBoardIsSane(board, expect_me_user=last)
        self.assertEqual(board.me.rank, 99, "잘린 동점자가 목록 등수로 무너졌다")

    def test_weekly_has_the_same_tie_group_limit(self):
        """주간도 같은 경로를 쓴다. 한쪽만 고치면 다른 쪽이 남는다."""
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())
        count = 65
        people = bulk_users("주간거대_", count)
        for i, user in enumerate(people):
            finish_round(user, 9, when=monday + timedelta(minutes=i))

        board = leaderboards.build(leaderboards.WEEKLY, user=people[-1])

        self.assertBoardIsSane(board, expect_me_user=people[-1])
        self.assertEqual(board.me.rank, count)

    def test_the_earliest_achiever_is_listed_first_in_a_huge_tie(self):
        """동점 무리가 커도 '먼저 달성한 쪽이 위' 가 지켜져야 한다.

        한때 목록을 pk 순으로 잘라낸 뒤 그 안에서만 시각으로 다시 세웠다.
        pk 순서와 달성 순서가 반대면 **진짜 1등이 아예 안 꺼내져** 목록에서
        사라졌다 - 내 줄이 아니라 목록 자체가 틀리는 종류다.
        """
        now = timezone.now()
        count = 61
        people = bulk_users("역순_", count)
        # pk 가 클수록 먼저 달성했다. 진짜 1등은 마지막 사람이다.
        for i, user in enumerate(people):
            finish_round(user, 25, when=now - timedelta(minutes=i + 1))

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(
            board.rows[0].display_name,
            people[-1].display_name,
            "가장 먼저 달성한 사람이 1등이 아니다 - 동점 무리가 잘렸다",
        )


class WeekBoundaryTest(TestCase):
    """KST 주 경계. 하루가 아니라 1마이크로초 차이를 본다."""

    def setUp(self):
        cache.clear()

    def test_one_microsecond_before_monday_is_last_week(self):
        """월요일 0시 정각 직전은 지난주다."""
        user = make_user("직전사람")
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())
        finish_round(user, 42, when=monday - timedelta(microseconds=1))

        weekly = leaderboards.build(leaderboards.WEEKLY, user=user)

        self.assertEqual(weekly.rows, [], "1마이크로초 앞선 판이 이번 주에 들어왔다")
        self.assertIsNone(weekly.me, "이번 주 기록이 없는데 내 줄이 나왔다")

    def test_last_sunday_end_of_day_is_last_week(self):
        """지난주 일요일 23:59:59 (KST) 는 이번 주가 아니다."""
        user = make_user("일요일사람")
        monday = calendar_kst.this_week_start()
        sunday_end = calendar_kst.day_begins(monday) - timedelta(seconds=1)
        finish_round(user, 77, when=sunday_end)

        self.assertEqual(leaderboards.build(leaderboards.WEEKLY).rows, [])
        self.assertEqual(len(leaderboards.build(leaderboards.ALL_TIME).rows), 1)

    def test_a_round_finished_at_kst_midnight_utc_offset_counts(self):
        """UTC 로 보면 지난주(일요일 15시)지만 KST 로는 월요일 0시다.

        서버가 UTC 로 날짜를 세면 이 판이 빠진다. 밤에 푼 사람이 억울하게
        순위표에서 사라지는 그 버그다.
        """
        user = make_user("자정사람")
        monday = calendar_kst.this_week_start()
        moment = calendar_kst.day_begins(monday)

        self.assertEqual(
            moment.astimezone(UTC).weekday(), 6, "픽스처가 의도한 시각이 아니다"
        )
        finish_round(user, 15, when=moment)

        board = leaderboards.build(leaderboards.WEEKLY, user=user)

        self.assertEqual(len(board.rows), 1, "KST 월요일 0시 판이 빠졌다")
        self.assertEqual(board.rows[0].score, 15)

    def test_only_this_weeks_best_counts_for_weekly(self):
        """지난주에 더 높은 점수가 있어도 주간은 이번 주 최고만 본다."""
        user = make_user("지난주가높은사람")
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())
        finish_round(user, 99, when=monday - timedelta(days=2))
        finish_round(user, 3, when=monday + timedelta(hours=1))

        weekly = leaderboards.build(leaderboards.WEEKLY)
        all_time = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(weekly.rows[0].score, 3, "지난주 점수가 주간에 섞였다")
        self.assertEqual(weekly.rows[0].entries, 1, "지난주 판을 판 수에 셌다")
        self.assertEqual(all_time.rows[0].score, 99)


class TotalEquivalenceTest(TestCase):
    """DailyScore.total (파이썬) 과 SQL 합이 같은 값을 내는지.

    같은 규칙이 두 곳에 있다. 손으로 고른 몇 개가 아니라 무작위 입력으로
    본다 - 마이너스·null·0 을 섞으면 두 식이 갈리는 자리가 드러난다.
    """

    def setUp(self):
        cache.clear()

    def test_random_days_match_the_python_property(self):
        rng = random.Random(20260816)
        today = calendar_kst.today()

        for round_index in range(5):
            with self.subTest(round=round_index):
                DailyScore.objects.all().delete()
                User.objects.filter(email__startswith="무작위").delete()

                user = User.objects.create(
                    email=f"무작위{round_index}@example.com",
                    display_name=f"무작위{round_index}",
                )
                rows = []
                for d in range(30):
                    best = rng.choice([None, -9, -5, -1, 0, 1, 7, 40])
                    study = rng.choice([-6, -1, 0, 2, 9])
                    rows.append(
                        daily(user, today - timedelta(days=d), best=best, study=study)
                    )

                expected = sum(row.total for row in rows)
                # 활동일도 total 기준이다. 두 칸을 따로 보면 상쇄되어 0인
                # 날(best=5, study=-5)이 활동일로 세어진다.
                active_days = sum(1 for row in rows if row.total > 0)

                board = leaderboards.build(leaderboards.STREAK, user=user)
                mine = board.rows[0] if board.rows else board.me

                self.assertIsNotNone(mine, "행이 30개인데 줄이 없다")
                self.assertEqual(mine.score, expected, "SQL 합이 파이썬 합과 다르다")
                self.assertEqual(mine.entries, active_days, "활동일 셈이 다르다")

    def test_a_day_that_is_only_negative_contributes_zero(self):
        """하루가 통째로 마이너스여도 누적이 줄지 않는다.

        SQL 쪽에서 0 으로 자르는 부분이 빠지면 열심히 한 날 점수가 깎인다.
        """
        user = make_user("한날망친사람")
        today = calendar_kst.today()
        daily(user, today, best=20, study=0)
        daily(user, today - timedelta(days=1), best=-50, study=-50)

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(board.rows[0].score, 20, "마이너스 날이 누적을 깎았다")
        self.assertEqual(board.rows[0].entries, 1)

    def test_a_null_best_with_study_points_is_not_lost(self):
        """best_free_score 가 null 인 날의 일일공부 점수가 사라지면 안 된다.

        SQL 에서 null + 2 는 2 가 아니라 null 이다. Coalesce 가 빠지면
        그 날이 합계에서 통째로 빠진다.
        """
        user = make_user("공부만한날사람")
        today = calendar_kst.today()
        for d in range(4):
            daily(user, today - timedelta(days=d), best=None, study=5)

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(board.rows[0].score, 20, "null 인 날이 합계에서 빠졌다")
        self.assertEqual(board.rows[0].entries, 4, "공부만 한 날이 활동일이 아니다")


class ZeroScoreOrderingTest(BoardConsistencyMixin, TestCase):
    """0점 사용자 여럿. 목록에는 안 보이지만 등수는 갈려야 한다."""

    def setUp(self):
        cache.clear()

    def test_zero_score_users_are_ordered_among_themselves(self):
        """0점 다섯 명. 전부 활동일 0 이면 pk 순으로 갈린다."""
        today = calendar_kst.today()
        scorer = make_user("유일한점수자")
        daily(scorer, today, best=10)

        zeros = bulk_users("영점_", 5)
        for i, user in enumerate(zeros):
            for d in range(i + 1):
                daily(user, today - timedelta(days=d), best=-2)

        ranks = []
        for user in zeros:
            board = leaderboards.build(leaderboards.STREAK, user=user)
            self.assertBoardIsSane(board, expect_me_user=user)
            self.assertEqual(board.me.score, 0)
            self.assertEqual(board.me.entries, 0, "마이너스 날을 활동일로 셌다")
            ranks.append(board.me.rank)

        self.assertEqual(len(set(ranks)), len(ranks), f"0점끼리 등수가 겹친다: {ranks}")
        self.assertEqual(sorted(ranks), list(range(2, 7)), "0점 등수가 이어지지 않는다")

    def test_a_zero_score_user_never_enters_the_list(self):
        """0점은 목록에 안 들어간다. 사람이 적어 자리가 남아도 마찬가지."""
        today = calendar_kst.today()
        zero = make_user("영점혼자")
        daily(zero, today, best=0, study=0)

        board = leaderboards.build(leaderboards.STREAK, user=zero)

        self.assertEqual(board.rows, [], "0점이 목록에 들어갔다")
        self.assertIsNotNone(board.me, "기록이 있는데 내 줄이 없다")
        self.assertEqual(board.me.rank, 1, "혼자면 1등이어야 한다")
        self.assertEqual(board.me.score, 0)

    def test_a_user_with_no_daily_rows_has_no_streak_row(self):
        """행이 하나도 없으면 내 줄도 없다. 0등을 만들면 안 된다."""
        today = calendar_kst.today()
        daily(make_user("있는사람"), today, best=5)

        board = leaderboards.build(leaderboards.STREAK, user=make_user("아무것도없는사람"))

        self.assertIsNone(board.me)


class AvatarLeakTest(TestCase):
    """아바타. 순위표는 로그인 안 해도 보이는 화면이다."""

    def setUp(self):
        cache.clear()

    def _row_for(self, user):
        finish_round(user, 5)
        return leaderboards.build(leaderboards.ALL_TIME).rows[0]

    def test_a_google_only_user_gets_the_photo(self):
        """아바타를 안 고르고 구글 사진만 있으면 그 사진을 쓴다."""
        user = make_user("구글만")
        User.objects.filter(pk=user.pk).update(
            avatar="", google_picture="https://lh3.example/only.jpg"
        )

        row = self._row_for(user)

        self.assertEqual(
            row.avatar, {"type": "photo", "url": "https://lh3.example/only.jpg"}
        )

    def test_a_user_with_nothing_gets_a_stable_preset(self):
        """아바타도 사진도 없으면 계정마다 고정된 프리셋이 나온다.

        고정이 아니면 새로고침할 때마다 그림이 바뀐다. 두 번 불러 같은지 본다.
        """
        user = make_user("아무것도안고른사람")
        User.objects.filter(pk=user.pk).update(avatar="", google_picture="")
        finish_round(user, 5)

        first = leaderboards.build(leaderboards.ALL_TIME).rows[0].avatar
        second = leaderboards.build(leaderboards.ALL_TIME).rows[0].avatar

        self.assertEqual(first["type"], "preset")
        self.assertIn(first["key"], ("a1", "a2", "a3", "a4", "a5", "a6"))
        self.assertEqual(first, second, "부를 때마다 아바타가 바뀐다")

    def test_choosing_google_without_a_photo_falls_back(self):
        """구글 사진을 고른 채로 사진이 없어져도 빈 줄이 안 나간다."""
        user = make_user("사진사라진사람")
        User.objects.filter(pk=user.pk).update(avatar="google", google_picture="")

        row = self._row_for(user)

        self.assertEqual(row.avatar["type"], "preset")
        self.assertTrue(row.avatar.get("key"), "빈 아바타가 나갔다")

    def test_an_unknown_avatar_value_does_not_leak_a_photo(self):
        """목록에 없는 아바타 값이 들어 있어도 사진 주소가 새면 안 된다.

        DB 를 직접 고치면 choices 는 안 막는다. 그때 프리셋 판정이 실패한
        김에 사진 가지로 흘러가면, 프리셋을 고른 셈인 사람의 사진이 나간다.
        """
        user = make_user("이상한값")
        User.objects.filter(pk=user.pk).update(
            avatar="a99", google_picture="https://lh3.example/hidden.jpg"
        )
        finish_round(user, 5)

        body = self.client.get(ALL_TIME_URL).content.decode()

        self.assertNotIn("lh3.example", body, "안 쓰는 구글 사진 주소가 나갔다")

    def test_the_me_row_uses_the_same_avatar_rule_as_the_list(self):
        """내 줄과 목록이 같은 규칙을 쓴다. 한쪽만 두 칸으로 내보내면 샌다."""
        for i, user in enumerate(bulk_users("아바타채우기_", 22)):
            finish_round(user, 100 - i)

        outsider = make_user("밖에있는사람")
        User.objects.filter(pk=outsider.pk).update(
            avatar="a4", google_picture="https://lh3.example/outsider.jpg"
        )
        finish_round(outsider, 1)

        board = leaderboards.build(leaderboards.ALL_TIME, user=outsider)
        body = self.client.get(ALL_TIME_URL).content.decode()

        self.assertEqual(board.me.avatar, {"type": "preset", "key": "a4"})
        self.assertNotIn("lh3.example", body, "내 줄로 사진 주소가 나갔다")


class InactiveUserTest(BoardConsistencyMixin, TestCase):
    """비활성 계정. 목록에서 빠지면 세는 쪽에서도 빠져야 한다."""

    def setUp(self):
        cache.clear()

    def test_an_inactive_user_is_not_counted_ahead_of_me(self):
        """탈퇴한 사람이 나보다 위여도 내 등수를 밀면 안 된다.

        목록에서는 빠지는데 세는 쿼리에 남아 있으면 내 등수만 뒤로 밀린다 -
        목록 마지막이 3등인데 내가 5등이 되는 식이다.
        """
        now = timezone.now()
        gone = bulk_users("떠난_", 3)
        for user in gone:
            finish_round(user, 90, when=now - timedelta(hours=1))
        User.objects.filter(pk__in=[u.pk for u in gone]).update(is_active=False)

        stayed = bulk_users("남은_", 2)
        for i, user in enumerate(stayed):
            finish_round(user, 10 - i, when=now)

        me = make_user("나")
        finish_round(me, 1, when=now)

        board = leaderboards.build(leaderboards.ALL_TIME, user=me)

        self.assertEqual(len(board.rows), 3, "탈퇴 계정이 목록에 있다")
        self.assertIsNone(board.me, "목록 안인데 내 줄이 나왔다")
        self.assertTrue(board.rows[-1].is_me, "마지막 줄이 나인데 표시가 없다")
        self.assertEqual(board.rows[-1].rank, 3, "탈퇴 계정이 내 등수를 밀었다")

    def test_an_inactive_user_is_not_counted_in_my_rank_outside_the_list(self):
        """목록 밖에서도 마찬가지.

        위 테스트는 내가 목록 안이라 세는 쿼리(_best_round_ahead)를 안 탄다.
        목록을 채워 나를 밖으로 밀어야 그 경로가 돈다.
        """
        now = timezone.now()

        crowd = bulk_users("무리_", leaderboards.TOP_SIZE)
        for i, user in enumerate(crowd):
            finish_round(user, 100 - i, when=now)

        gone = bulk_users("밖떠난_", 3)
        for user in gone:
            finish_round(user, 50, when=now - timedelta(hours=1))
        User.objects.filter(pk__in=[u.pk for u in gone]).update(is_active=False)

        me = make_user("밖의나")
        finish_round(me, 1, when=now)

        board = leaderboards.build(leaderboards.ALL_TIME, user=me)

        self.assertIsNotNone(board.me, "목록 밖인데 내 줄이 없다")
        self.assertEqual(
            board.me.rank,
            leaderboards.TOP_SIZE + 1,
            "탈퇴 계정이 내 앞에 세어졌다",
        )

    def test_an_inactive_user_does_not_shift_streak_ranks(self):
        """꾸준함에서도 마찬가지.

        내가 **목록 밖**이어야 세는 쿼리(_streak_ahead)가 돈다. 목록 안이면
        그 경로를 안 타서, 세는 쪽이 비활성을 걸러내는지 확인이 안 된다.
        """
        today = calendar_kst.today()

        # 목록을 채운다. 내가 밖으로 밀려야 한다.
        crowd = bulk_users("꾸준무리_", leaderboards.TOP_SIZE)
        for i, user in enumerate(crowd):
            daily(user, today, best=100 - i)

        # 비활성 3명. 점수가 높아 세어지면 내 등수가 밀린다.
        for i in range(3):
            gone = make_user(f"꾸준떠남{i}")
            for d in range(5):
                daily(gone, today - timedelta(days=d), best=50)
            User.objects.filter(pk=gone.pk).update(is_active=False)

        me = make_user("꾸준나")
        daily(me, today, best=1)

        board = leaderboards.build(leaderboards.STREAK, user=me)

        self.assertEqual(len(board.rows), leaderboards.TOP_SIZE)
        self.assertIsNotNone(board.me, "목록 밖인데 내 줄이 없다")
        self.assertEqual(
            board.me.rank,
            leaderboards.TOP_SIZE + 1,
            "비활성 계정이 내 앞에 세어졌다",
        )

    def test_my_own_row_is_hidden_when_i_am_inactive(self):
        """내가 비활성이면 내 줄도 안 나온다. 목록에서 뺀 사람의 등수를
        따로 계산해 주면 뺀 의미가 없다."""
        active = make_user("활성사람")
        finish_round(active, 50)

        me = make_user("비활성나")
        finish_round(me, 5)
        User.objects.filter(pk=me.pk).update(is_active=False)
        me.refresh_from_db()

        board = leaderboards.build(leaderboards.ALL_TIME, user=me)

        self.assertEqual(
            [row.display_name for row in board.rows], [active.display_name]
        )
        self.assertIsNone(board.me, "비활성 계정에 내 줄이 나갔다")


class KindArgumentTest(TestCase):
    """종류 인자. 오타가 조용히 통과하면 안 된다."""

    def setUp(self):
        cache.clear()

    def test_an_unknown_kind_raises(self):
        for bad in ("", "WEEKLY", "all-time", "streaks", None, 0):
            with self.subTest(kind=bad):
                with self.assertRaises(ValueError):
                    leaderboards.build(bad)

    def test_all_three_kinds_work_on_an_empty_database(self):
        """아무 기록도 없을 때 빈 순위표가 나와야 한다. 500 이 아니다."""
        user = make_user("첫사용자")
        for kind in leaderboards.KINDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=user)

                self.assertEqual(board.rows, [])
                self.assertIsNone(board.me)


class LeaderboardApiEdgeTest(TestCase):
    """API 경계."""

    def setUp(self):
        cache.clear()

    def test_an_empty_board_returns_a_usable_shape(self):
        """기록이 하나도 없어도 화면이 그릴 수 있는 모양이어야 한다."""
        for url in (WEEKLY_URL, ALL_TIME_URL, STREAK_URL):
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertEqual(body["rows"], [])
                self.assertIsNone(body["me"])
                self.assertIn("kind", body)

    def test_a_logged_in_user_outside_the_top_gets_a_me_row(self):
        """로그인하면 목록 밖이어도 내 줄이 온다."""
        for i, user in enumerate(bulk_users("API채우기_", 22)):
            finish_round(user, 100 - i)

        me = make_user("API밖사람")
        finish_round(me, 1)
        self.client.force_login(me)

        body = self.client.get(ALL_TIME_URL).json()

        self.assertEqual(len(body["rows"]), 20)
        self.assertIsNotNone(body["me"], "로그인했는데 내 줄이 없다")
        self.assertTrue(body["me"]["is_me"], "내 줄인데 is_me 가 거짓이다")
        self.assertNotIn("user_id", body["me"], "pk 가 응답에 나갔다")
        self.assertEqual(body["me"]["rank"], 23)
        self.assertNotIn(
            body["me"]["rank"], [row["rank"] for row in body["rows"]], "등수가 겹친다"
        )

    def test_a_deactivated_user_still_gets_a_readable_board(self):
        """비활성 계정이 세션을 들고 있어도 500 이 아니라 목록이 나온다."""
        other = make_user("정상사람")
        finish_round(other, 10)

        me = make_user("탈퇴한나")
        finish_round(me, 5)
        self.client.force_login(me)
        User.objects.filter(pk=me.pk).update(is_active=False)

        for url in (WEEKLY_URL, ALL_TIME_URL, STREAK_URL):
            with self.subTest(url=url):
                res = self.client.get(url)

                self.assertEqual(res.status_code, 200)
                names = [row["display_name"] for row in res.json()["rows"]]
                self.assertNotIn("탈퇴한나", names, "탈퇴 계정이 목록에 나왔다")

    def test_the_period_is_only_on_weekly(self):
        """기간은 주간에만. 다른 둘에 빈 값이 가면 화면이 그리려 든다."""
        self.assertIn("period", self.client.get(WEEKLY_URL).json())
        self.assertNotIn("period", self.client.get(ALL_TIME_URL).json())
        self.assertNotIn("period", self.client.get(STREAK_URL).json())

    def test_a_guest_sees_the_same_rows_as_a_logged_in_user(self):
        """게스트에게도 남의 줄은 다 보인다. me 만 없다."""
        for i, user in enumerate(bulk_users("게스트비교_", 5)):
            finish_round(user, 20 - i)
            daily(user, calendar_kst.today(), best=20 - i)

        viewer = make_user("보는사람")

        for url in (WEEKLY_URL, ALL_TIME_URL, STREAK_URL):
            with self.subTest(url=url):
                self.client.logout()
                guest = self.client.get(url).json()

                self.client.force_login(viewer)
                member = self.client.get(url).json()

                self.assertIsNone(guest["me"], "게스트에게 내 줄이 나갔다")
                self.assertIsNone(member["me"], "기록 없는 사람에게 줄이 나갔다")
                self.assertEqual(
                    [row["display_name"] for row in guest["rows"]],
                    [row["display_name"] for row in member["rows"]],
                    "로그인 여부로 목록이 달라진다",
                )

    def test_head_and_post_are_handled(self):
        """읽기 전용 엔드포인트다. POST 는 405 여야 하고 500 이면 안 된다.

        HEAD 는 브라우저와 헬스체크가 보낸다. Django 가 GET 으로 처리해
        200 이어야 하는데, 몸통 없이 헤더만 만드는 과정에서 터지는 일이
        있어 같이 본다.
        """
        self.assertEqual(self.client.post(ALL_TIME_URL, {}).status_code, 405)
        self.assertEqual(self.client.get(ALL_TIME_URL).status_code, 200)
        self.assertEqual(self.client.head(ALL_TIME_URL).status_code, 200)


class DailyKindLeakTest(TestCase):
    """일일공부 판이 최고점 순위표에 새는지."""

    def setUp(self):
        cache.clear()

    def test_a_daily_round_does_not_inflate_entries(self):
        """일일공부 판이 판 수에도 안 들어가야 한다.

        점수만 거르고 Count 를 안 거르면 "3판 했다" 가 "10판 했다" 가 된다.
        """
        user = make_user("섞어한사람")
        for score in (5, 8):
            finish_round(user, score)
        for score in (90, 91, 92):
            finish_round(user, score, kind=SessionKind.DAILY)

        row = leaderboards.build(leaderboards.ALL_TIME).rows[0]

        self.assertEqual(row.score, 8, "일일공부 점수가 최고점에 들어갔다")
        self.assertEqual(row.entries, 2, "일일공부 판을 판 수에 셌다")

    def test_a_daily_only_user_has_no_me_row(self):
        """일일공부만 한 사람은 최고점 순위표에 줄이 없다."""
        other = make_user("자유한사람")
        finish_round(other, 5)

        user = make_user("일일만한사람")
        finish_round(user, 99, kind=SessionKind.DAILY)

        board = leaderboards.build(leaderboards.ALL_TIME, user=user)

        self.assertEqual(len(board.rows), 1)
        self.assertIsNone(board.me, "일일공부만 했는데 최고점 줄이 나왔다")
