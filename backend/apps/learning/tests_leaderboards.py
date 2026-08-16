"""순위표 세 가지.

지키려는 것은 넷이다.

    - 최고점 2종은 사용자별 **한 판**만 센다. 여러 판을 더하지 않는다
    - 꾸준함은 DailyScore.total 과 **같은 값**을 낸다(파이썬/SQL 두 곳)
    - 동점이면 먼저 달성한 쪽이 위. 꾸준함은 활동한 날이 많은 쪽이 위
    - 상위 20명. 내가 밖이면 내 줄이 따로 붙는다

세 번째가 특히 잘 깨진다. 정렬 규칙은 눈에 안 보이고, 틀려도 화면은
멀쩡해 보인다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
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


def finish_round(user, score: int, *, when=None, kind=SessionKind.FREE) -> QuizSession:
    """끝난 판 하나를 남긴다. 순위표가 이걸 읽는다."""
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


class BestRoundTest(TestCase):
    """최고점 2종. 사용자별 한 판만 센다."""

    def setUp(self):
        cache.clear()

    def test_only_the_best_round_counts(self):
        """여러 판을 더하면 많이 한 사람이 이긴다. 그건 이 순위표가 아니다."""
        heavy = make_user("많이한사람")
        for score in (3, 5, 4):
            finish_round(heavy, score)

        light = make_user("한판한사람")
        finish_round(light, 7)

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(board.rows[0].display_name, "한판한사람")
        self.assertEqual(board.rows[0].score, 7)
        # 많이 한 사람은 5점(최고 한 판)이지 12점(합)이 아니다.
        self.assertEqual(board.rows[1].score, 5)

    def test_a_tie_puts_the_earlier_finish_first(self):
        """동점이면 먼저 달성한 쪽이 위.

        늦게 온 사람이 앞사람을 밀어내려면 더 잘해야 한다.
        """
        now = timezone.now()
        late = make_user("늦게한사람")
        finish_round(late, 10, when=now)

        early = make_user("먼저한사람")
        finish_round(early, 10, when=now - timedelta(hours=3))

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(
            [row.display_name for row in board.rows], ["먼저한사람", "늦게한사람"]
        )

    def test_a_tie_is_broken_by_the_first_round_not_the_best_one(self):
        """알려진 절충. 동점을 **첫 판 시각**으로 가른다.

        규칙은 "먼저 달성한 사람이 위" 인데, 실제로 보는 값은 그 사람의
        첫 판이다. 그래서 오래 한 사람이 나중에 동점을 만들어도 이긴다 -
        신규는 동점으로는 못 올라간다.

        고칠 수 있게 되면 **이 테스트가 빨간불이 된다.** 그때 기대값을
        뒤집고 이 설명을 지우면 된다. 지금 이걸 안 적어두면 픽스처가
        전부 1인 1판이라 아무도 차이를 모른다.
        """
        now = timezone.now()

        veteran = make_user("오래한사람")
        finish_round(veteran, 1, when=now - timedelta(days=365))
        finish_round(veteran, 50, when=now)

        newcomer = make_user("신규")
        finish_round(newcomer, 50, when=now - timedelta(days=2))

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(
            [row.display_name for row in board.rows],
            ["오래한사람", "신규"],
            "절충이 바뀌었다 - 독스트링과 ponytail 주석을 같이 고칠 것",
        )

    def test_daily_study_rounds_are_not_counted(self):
        """일일공부는 자유 문제풀이 순위표에 안 들어간다."""
        user = make_user("공부만한사람")
        finish_round(user, 50, kind=SessionKind.DAILY)

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(board.rows, [])


class WeeklyWindowTest(TestCase):
    """이번 주 순위표. 주 경계가 하루만 어긋나도 순위가 뒤집힌다."""

    def setUp(self):
        cache.clear()

    def test_last_week_does_not_count(self):
        user = make_user("지난주사람")
        monday = calendar_kst.this_week_start()
        # 이번 주 월요일 자정보다 1초 전 = 지난주 일요일
        just_before = calendar_kst.day_begins(monday) - timedelta(seconds=1)
        finish_round(user, 99, when=just_before)

        weekly = leaderboards.build(leaderboards.WEEKLY)
        all_time = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(weekly.rows, [], "지난주 판이 이번 주에 들어왔다")
        self.assertEqual(len(all_time.rows), 1, "전체 순위표에는 있어야 한다")

    def test_monday_midnight_counts_as_this_week(self):
        """월요일 0시 정각은 이번 주다. 경계는 포함이다."""
        user = make_user("월요일사람")
        monday = calendar_kst.this_week_start()
        finish_round(user, 30, when=calendar_kst.day_begins(monday))

        board = leaderboards.build(leaderboards.WEEKLY)

        self.assertEqual(len(board.rows), 1)

    def test_period_is_monday_to_sunday(self):
        board = leaderboards.build(leaderboards.WEEKLY)

        self.assertEqual(board.period_start.weekday(), 0, "월요일이 아니다")
        self.assertEqual(board.period_end.weekday(), 6, "일요일이 아니다")
        self.assertEqual((board.period_end - board.period_start).days, 6)


class StreakTest(TestCase):
    """꾸준함. 하루 점수를 전부 더한 값."""

    def setUp(self):
        cache.clear()

    def test_sql_sum_matches_the_python_property(self):
        """SQL 로 다시 쓴 식이 DailyScore.total 과 같은 값을 내야 한다.

        같은 규칙이 파이썬과 SQL 두 곳에 있다. 한쪽만 고치면 화면 숫자와
        순위가 어긋난다. 마이너스가 섞인 날을 넣어 0 으로 자르는 부분까지
        본다 - 거기가 두 식이 갈리기 가장 쉬운 자리다.
        """
        user = make_user("섞인사람")
        today = calendar_kst.today()
        rows = [
            daily(user, today, best=5, study=3),      # 8
            daily(user, today - timedelta(days=1), best=-4, study=1),  # 0 으로 잘림
            daily(user, today - timedelta(days=2), best=None, study=2),  # 2
            daily(user, today - timedelta(days=3), best=-2, study=0),  # 0 으로 잘림
        ]
        expected = sum(row.total for row in rows)

        board = leaderboards.build(leaderboards.STREAK)

        self.assertEqual(board.rows[0].score, expected)
        self.assertEqual(expected, 10, "픽스처가 의도한 값이 아니다")

    def test_a_wasted_day_is_not_an_active_day(self):
        """점수가 안 남은 날은 활동일로 안 센다.

        판을 열기만 해도 그 날 행이 생긴다. 행 수로 세면 망친 날도
        활동일이 되어, 같은 점수라면 **더 많이 망친 쪽이 위**로 온다.
        꾸준함이 아니라 "행을 많이 만든 사람" 이 이기는 순위표가 된다.
        """
        today = calendar_kst.today()

        steady = make_user("사흘꾸준")
        for i in range(3):
            daily(steady, today - timedelta(days=i), best=4)

        wasteful = make_user("이틀에망친날들")
        daily(wasteful, today, best=6)
        daily(wasteful, today - timedelta(days=1), best=6)
        # 점수가 안 남은 날들. 행은 생기지만 활동일은 아니다.
        for i in range(2, 6):
            daily(wasteful, today - timedelta(days=i), best=-5)

        board = leaderboards.build(leaderboards.STREAK)

        self.assertEqual(board.rows[0].score, board.rows[1].score, "동점이 아니다")
        self.assertEqual(board.rows[0].display_name, "사흘꾸준")
        self.assertEqual(board.rows[1].entries, 2, "망친 날을 활동일로 셌다")

    def test_a_cancelled_out_day_is_not_an_active_day(self):
        """서로 상쇄되어 총점 0인 날도 활동일이 아니다.

        best=5, study=-5 인 날은 두 칸 중 하나가 양수라, 칸을 따로 보면
        활동일로 세어진다. 그러면 **점수를 1점도 안 준 날**을 여럿 쌓아
        동점자를 이길 수 있다 - 위 테스트가 막으려는 것과 같은 구멍이
        다른 입력으로 열린다.
        """
        today = calendar_kst.today()

        steady = make_user("사흘한사람")
        for d in range(3):
            daily(steady, today - timedelta(days=d), best=4)

        padded = make_user("상쇄날쌓은사람")
        for d in range(3):
            daily(padded, today - timedelta(days=d), best=4)
        daily(padded, today - timedelta(days=3), best=5, study=-5)
        daily(padded, today - timedelta(days=4), best=3, study=-3)

        board = leaderboards.build(leaderboards.STREAK)
        entries = {row.display_name: row.entries for row in board.rows}

        self.assertEqual(entries["상쇄날쌓은사람"], 3, "상쇄된 날을 활동일로 셌다")
        self.assertEqual(board.rows[0].display_name, "사흘한사람", "동점 순서가 뒤집혔다")

    def test_my_row_shows_up_even_with_no_points(self):
        """0점이어도 내 순위는 나온다.

        목록에서는 0점을 빼지만 "내가 몇 등인가" 는 다른 질문이다. 매일
        들어와 전부 마이너스로 끝낸 사람에게 "기록이 없습니다" 라고 하면
        안 된다.
        """
        today = calendar_kst.today()

        for i in range(3):
            scorer = make_user(f"점수낸사람{i}")
            daily(scorer, today, best=10 - i)

        struggler = make_user("계속망친사람")
        for i in range(4):
            daily(struggler, today - timedelta(days=i), best=-3)

        board = leaderboards.build(leaderboards.STREAK, user=struggler)

        self.assertEqual(len(board.rows), 3, "0점이 목록에 들어갔다")
        self.assertIsNotNone(board.me, "기록이 있는데 없다고 한다")
        self.assertEqual(board.me.score, 0)
        self.assertEqual(board.me.entries, 0, "점수 안 남은 날을 활동일로 셌다")
        self.assertEqual(board.me.rank, 4, "점수 있는 사람들 뒤여야 한다")

    def test_zero_score_users_do_not_all_share_one_rank(self):
        """0점끼리도 순서가 있어야 한다.

        목록은 0점을 빼지만 세는 쿼리에서까지 빼면 0점 가지가 죽어
        **활동일이 달라도 전부 같은 등수**가 된다. 목록에 안 보이는
        사람들이라 눈에 안 띈다.
        """
        today = calendar_kst.today()
        scorer = make_user("점수낸사람")
        daily(scorer, today, best=10)

        many_days = make_user("사흘나온사람")
        for d in range(3):
            daily(many_days, today - timedelta(days=d), best=-1)

        one_day = make_user("하루나온사람")
        daily(one_day, today, best=-1)

        first = leaderboards.build(leaderboards.STREAK, user=many_days)
        second = leaderboards.build(leaderboards.STREAK, user=one_day)

        self.assertEqual(first.me.score, 0)
        self.assertEqual(second.me.score, 0)
        self.assertNotEqual(first.me.rank, second.me.rank, "0점끼리 등수가 같다")
        self.assertLess(first.me.rank, second.me.rank, "더 나온 쪽이 뒤에 있다")

    def test_my_streak_rank_follows_the_list_order(self):
        """꾸준함도 목록 밖 등수가 목록 순서와 이어져야 한다.

        점수가 같으면 활동한 날이 많은 쪽이 앞이다. 내 줄을 셀 때 그
        기준을 안 쓰면 목록과 등수 규칙이 갈린다.
        """
        today = calendar_kst.today()
        people = User.objects.bulk_create(
            User(email=f"꾸준{i:02d}@example.com", display_name=f"꾸준{i:02d}")
            for i in range(25)
        )

        # 전원 12점 동점. 앞 22명은 사흘(4+4+4), 뒤 3명은 이틀(6+6).
        # 활동일이 많은 쪽이 앞이므로 사흘 22명이 1~22등, 이틀 3명이
        # 23~25등이다. 그 안에서는 pk 오름차순.
        for i, user in enumerate(people):
            if i < 22:
                for d in range(3):
                    daily(user, today - timedelta(days=d), best=4)
            else:
                for d in range(2):
                    daily(user, today - timedelta(days=d), best=6)

        last = people[-1]

        board = leaderboards.build(leaderboards.STREAK, user=last)

        self.assertEqual(board.rows[0].entries, 3, "사흘 쪽이 위가 아니다")
        self.assertEqual(board.me.rank, 25, "목록 순서와 등수가 어긋난다")

    def test_a_tie_puts_the_more_active_first(self):
        """동점이면 활동한 날이 많은 쪽이 위.

        같은 점수를 더 여러 날에 걸쳐 쌓았다는 뜻이다. 순위표 이름이
        '꾸준함' 인 이상 그쪽이 위여야 한다.
        """
        today = calendar_kst.today()

        spread = make_user("사흘에걸쳐")
        for i, points in enumerate((4, 4, 4)):
            daily(spread, today - timedelta(days=i), best=points)

        burst = make_user("이틀에몰아")
        daily(burst, today, best=6)
        daily(burst, today - timedelta(days=1), best=6)

        board = leaderboards.build(leaderboards.STREAK)

        self.assertEqual(board.rows[0].score, board.rows[1].score, "동점이 아니다")
        self.assertEqual(board.rows[0].display_name, "사흘에걸쳐")
        self.assertEqual(board.rows[0].entries, 3)


class TopAndMeTest(TestCase):
    """상위 20명 + 내 순위."""

    def setUp(self):
        cache.clear()

    def _crowd(self, count: int) -> list:
        """점수가 다른 사람 여럿. 1등이 가장 높다.

        create_user 를 안 쓴다. 사람마다 비밀번호를 해싱하느라 수십 명만
        만들어도 테스트가 분 단위로 늘어지는데, 여기서는 아무도 로그인하지
        않는다.
        """
        people = User.objects.bulk_create(
            User(email=f"사람{i:02d}@example.com", display_name=f"사람{i:02d}")
            for i in range(count)
        )
        return [(user, count - i) for i, user in enumerate(people)]

    def test_only_twenty_rows(self):
        for user, score in self._crowd(25):
            finish_round(user, score)

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(len(board.rows), leaderboards.TOP_SIZE)
        self.assertEqual(board.rows[0].rank, 1)
        self.assertEqual(board.rows[-1].rank, leaderboards.TOP_SIZE)

    def test_my_row_is_added_when_i_am_outside(self):
        """21등 밖이면 내 줄이 따로 붙는다.

        순위권 밖 사람도 자기 위치를 알아야 한다. 모르면 다시 안 온다.
        """
        people = self._crowd(25)
        for user, score in people:
            finish_round(user, score)

        last_user = people[-1][0]
        board = leaderboards.build(leaderboards.ALL_TIME, user=last_user)

        self.assertIsNotNone(board.me, "내 줄이 없다")
        self.assertEqual(board.me.rank, 25)
        self.assertTrue(board.me.is_me, "내 줄인데 is_me 가 거짓이다")
        self.assertEqual(board.me.display_name, last_user.display_name)

    def test_my_row_is_not_duplicated_when_i_am_inside(self):
        """목록 안이면 me 를 비운다. 두 번 그리면 자기가 둘인 줄 안다."""
        people = self._crowd(25)
        for user, score in people:
            finish_round(user, score)

        top_user = people[0][0]
        board = leaderboards.build(leaderboards.ALL_TIME, user=top_user)

        self.assertIsNone(board.me)
        self.assertTrue(board.rows[0].is_me, "목록의 내 줄에 표시가 없다")

    def test_a_user_with_no_record_has_no_row(self):
        """기록이 없으면 내 줄도 없다. 0등이라고 보여주면 안 된다."""
        for user, score in self._crowd(3):
            finish_round(user, score)

        newcomer = make_user("방금온사람")
        board = leaderboards.build(leaderboards.ALL_TIME, user=newcomer)

        self.assertIsNone(board.me)

    def test_my_rank_is_right_even_far_outside(self):
        """목록 밖 순위를 따로 세는 경로. 잘라낸 뒤에도 맞아야 한다.

        상위 20명만 꺼내므로 61등은 그 안에 없다. 세는 쿼리가 틀리면
        엉뚱한 등수가 나가는데, 화면은 그냥 그 숫자를 그린다.
        """
        people = self._crowd(70)
        for user, score in people:
            finish_round(user, score)

        # _crowd 는 1등이 가장 높다. 61번째 사람이 61등이다.
        me = people[60][0]
        board = leaderboards.build(leaderboards.ALL_TIME, user=me)

        self.assertEqual(board.me.rank, 61)
        self.assertTrue(board.me.is_me)

    def test_my_rank_uses_the_same_rule_as_the_list(self):
        """동점자가 많아도 내 등수가 목록과 같은 규칙이어야 한다.

        목록은 동점이어도 1,2,3 으로 번호를 매긴다. 내 줄에서 동점자를
        안 세면 규칙이 갈린다 - 같은 점수 여럿이 목록 앞자리를 채우고
        있을 때 목록 밖 동점자가 자기를 한참 앞 등수로 본다. 화면에
        같은 등수가 둘 나온다.
        """
        now = timezone.now()
        top = make_user("혼자높은사람")
        finish_round(top, 100, when=now - timedelta(days=1))

        # 50점 동점 25명. 먼저 끝낸 순서대로 2등부터 매겨져야 한다.
        tied = User.objects.bulk_create(
            User(email=f"동점{i:02d}@example.com", display_name=f"동점{i:02d}")
            for i in range(25)
        )
        for i, user in enumerate(tied):
            finish_round(user, 50, when=now - timedelta(minutes=25 - i))

        # 목록은 20명까지. 가장 늦게 끝낸 사람이 목록 밖이다.
        latest = tied[-1]
        board = leaderboards.build(leaderboards.ALL_TIME, user=latest)

        listed = [row.rank for row in board.rows]
        self.assertEqual(listed, list(range(1, 21)), "목록 번호가 어긋난다")
        self.assertIsNotNone(board.me, "내 줄이 없다")
        self.assertEqual(board.me.rank, 26, "동점자를 안 세서 등수가 앞당겨졌다")

    def test_a_huge_tie_gives_everyone_a_distinct_rank(self):
        """동점자가 아무리 많아도 등수가 한 값으로 뭉치면 안 된다.

        동점자를 꺼내와 그 안에서 내 자리를 찾는 방식은 꺼내는 양에 한도가
        생기고, 그 밖의 사람들이 전부 같은 등수를 본다. 더 잘해도 숫자가
        안 움직이면 순위표가 동기를 못 준다.

        pk 와 달성 순서를 반대로 둔다 - pk 순으로 자르거나 세면 진짜 1등이
        맨 뒤로 간다.
        """
        now = timezone.now()
        crowd = User.objects.bulk_create(
            User(email=f"떼{i:03d}@example.com", display_name=f"떼{i:03d}")
            for i in range(100)
        )
        for i, user in enumerate(crowd):
            finish_round(user, 50, when=now - timedelta(minutes=i + 1))

        # 인덱스가 클수록 먼저 달성 = 앞 등수.
        ranks = [
            leaderboards.build(leaderboards.ALL_TIME, user=crowd[i]).me.rank
            for i in (0, 20, 40)
        ]

        self.assertEqual(ranks, [100, 80, 60], "등수가 뭉쳤다")

        first = leaderboards.build(leaderboards.ALL_TIME, user=crowd[-1])
        self.assertEqual(
            first.rows[0].display_name, crowd[-1].display_name, "먼저 달성한 사람이 1등이 아니다"
        )
        self.assertIsNone(first.me, "1등인데 목록 밖으로 나갔다")

    def test_a_board_does_not_scale_with_users(self):
        """사람이 늘어도 DB 에서 꺼내는 양이 그대로여야 한다.

        상위 20명만 필요한데 전 사용자를 파이썬으로 끌어오면 사람이
        늘수록 조용히 느려진다. 화면은 멀쩡해서 아무도 모른다.

        쿼리 **수**만 세면 못 잡는다. 전량을 끌어와도 쿼리는 한 번이다.
        SQL 에 LIMIT 이 실제로 붙었는지를 본다.
        """
        people = self._crowd(60)
        for user, score in people:
            finish_round(user, score)
            daily(user, calendar_kst.today(), best=score)

        # 목록 밖 사용자로도 본다. user 없이 부르면 내 순위 경로가
        # 통째로 안 돌아 그쪽 회귀를 못 잡는다.
        outsider = people[-1][0]

        for kind in leaderboards.KINDS:
            with self.subTest(kind=kind):
                with CaptureQueriesContext(connection) as caught:
                    leaderboards.build(kind, user=outsider)

                # **사람 수만큼 커지는 조회**에는 LIMIT 이 있어야 한다.
                # 아래 둘은 사람 수와 무관하므로 뺀다.
                #
                #   COUNT(...)   - 몇 명인지만 돌려준다
                #   user_id = N  - 내 줄 하나, 또는 이미 잘린 목록의 쌍
                #
                # any() 로 "하나라도 있으면 통과" 하면 안 된다 - 목록
                # 쿼리에는 늘 LIMIT 이 있어서, 내 순위 경로가 전량을
                # 훑도록 회귀해도 초록불이 된다.
                unbounded = [
                    q["sql"]
                    for q in caught.captured_queries
                    if "GROUP BY" in q["sql"]
                    and not q["sql"].startswith("SELECT COUNT")
                    and "user_id" not in q["sql"].split("WHERE")[-1]
                ]
                self.assertTrue(unbounded, "집계 쿼리가 없다")
                for sql in unbounded:
                    self.assertIn(
                        "LIMIT", sql, f"{kind}: 전 사용자를 끌어온다 - {sql[:120]}"
                    )


class VisibilityTest(TestCase):
    """순위표에 나가면 안 되는 것."""

    def setUp(self):
        cache.clear()

    def test_inactive_users_are_hidden(self):
        """탈퇴(비활성) 계정은 순위표에 안 나온다."""
        gone = make_user("떠난사람")
        finish_round(gone, 99)
        User.objects.filter(pk=gone.pk).update(is_active=False)

        stayed = make_user("남은사람")
        finish_round(stayed, 5)

        board = leaderboards.build(leaderboards.ALL_TIME)

        names = [row.display_name for row in board.rows]
        self.assertEqual(names, ["남은사람"])

    def test_an_empty_display_name_is_replaced(self):
        """이름이 비면 대신 채운다. 순위표는 모르는 사람에게 보이는 화면이다."""
        nameless = make_user("이름있음")
        User.objects.filter(pk=nameless.pk).update(display_name="")
        finish_round(nameless, 10)

        board = leaderboards.build(leaderboards.ALL_TIME)

        self.assertTrue(board.rows[0].display_name.strip(), "빈 줄이 나갔다")
        self.assertIn("학습자", board.rows[0].display_name)


class LeaderboardApiTest(TestCase):
    """API 세 개."""

    def setUp(self):
        cache.clear()

    def test_a_guest_can_read_all_three(self):
        """로그인 전에도 보여야 한다. 안 보이면 가입할 이유가 안 생긴다.

        빈 순위표로 확인하면 안 된다 - 아무것도 없어서 me 가 비는 것과
        게스트라서 비는 것이 구분되지 않는다. 남의 기록을 넣어두고 본다.
        """
        someone = make_user("이미있는사람")
        finish_round(someone, 10)
        daily(someone, calendar_kst.today(), best=10)

        for url in (WEEKLY_URL, ALL_TIME_URL, STREAK_URL):
            with self.subTest(url=url):
                res = self.client.get(url)

                self.assertEqual(res.status_code, 200)
                self.assertEqual(len(res.json()["rows"]), 1, "남의 줄이 안 보인다")
                self.assertIsNone(res.json()["me"], "게스트에게 내 줄이 나갔다")
                self.assertFalse(
                    res.json()["rows"][0]["is_me"], "게스트인데 내 줄이라고 한다"
                )

    def test_the_response_never_carries_a_primary_key(self):
        """응답에 사용자 pk 가 없어야 한다.

        pk 는 순차라 **가장 큰 값이 대략 가입자 수**다. 순위표는 로그인
        없이 보이므로 그대로 두면 누구나 규모를 셀 수 있고, 며칠 지켜보면
        가입 속도까지 나온다. 화면이 알아야 할 것은 "이게 나인가" 뿐이라
        is_me 로 내보낸다.
        """
        me = make_user("확인할사람")
        finish_round(me, 7)
        daily(me, calendar_kst.today(), best=7)
        self.client.force_login(me)

        for url in (WEEKLY_URL, ALL_TIME_URL, STREAK_URL):
            with self.subTest(url=url):
                row = self.client.get(url).json()["rows"][0]

                self.assertNotIn("user_id", row, "pk 가 응답에 나갔다")
                self.assertTrue(row["is_me"], "내 줄인데 표시가 없다")
                # pk 가 값으로도 안 새는지. 이름·아바타·점수만 나가야 한다.
                self.assertEqual(
                    set(row),
                    {"rank", "display_name", "avatar", "score", "entries", "is_me"},
                    "응답 필드가 바뀌었다 - 프론트 계약이다",
                )

    def test_only_my_row_is_marked(self):
        """내 줄에만 표시가 붙는다. 여럿에 붙으면 화면이 여러 줄을 강조한다."""
        others = [make_user(f"남{i}") for i in range(3)]
        for user, score in zip(others, (30, 20, 10)):
            finish_round(user, score)

        me = make_user("나")
        finish_round(me, 15)
        self.client.force_login(me)

        rows = self.client.get(ALL_TIME_URL).json()["rows"]
        marked = [row for row in rows if row["is_me"]]

        self.assertEqual(len(marked), 1, "표시가 하나가 아니다")
        self.assertEqual(marked[0]["display_name"], "나")
        self.assertEqual(marked[0]["score"], 15)

    def test_weekly_carries_the_period(self):
        """기간이 실제 이번 주여야 한다. 키만 있으면 화면이 엉뚱한 날짜를 그린다."""
        period = self.client.get(WEEKLY_URL).json()["period"]

        monday = calendar_kst.this_week_start()
        self.assertEqual(period["start"], monday.isoformat())
        self.assertEqual(period["end"], (monday + timedelta(days=6)).isoformat())

    def test_all_time_has_no_period(self):
        """전체 기간은 시작·끝이 없다. 빈 값을 보내면 화면이 그리려 든다."""
        self.assertNotIn("period", self.client.get(ALL_TIME_URL).json())

    def test_rows_carry_what_the_screen_draws(self):
        """화면이 그리는 값이 다 들어 있어야 한다. 키만 보면 안 된다 -
        entries 가 늘 0 이어도, 아바타가 늘 빈 문자열이어도 통과해버린다.
        """
        user = make_user("화면사람")
        User.objects.filter(pk=user.pk).update(avatar="a3")
        for score in (12, 7, 9):
            finish_round(user, score)

        row = self.client.get(ALL_TIME_URL).json()["rows"][0]

        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["display_name"], "화면사람")
        self.assertEqual(row["score"], 12, "최고 한 판이 아니다")
        self.assertEqual(row["entries"], 3, "판 수를 안 센다")
        self.assertEqual(row["avatar"], {"type": "preset", "key": "a3"})

    def test_a_google_photo_is_not_leaked_when_unused(self):
        """구글 사진을 안 쓰기로 한 사람의 사진 주소는 안 나간다.

        순위표는 로그인 안 해도 보이는 화면이다. 두 칸으로 내보내면
        아바타를 고른 사람의 사진 주소까지 상위 20명분이 한 번에 나간다 -
        본인이 화면에서 내린 선택이 API 에서 무시되는 셈이다.
        """
        user = make_user("아바타고른사람")
        User.objects.filter(pk=user.pk).update(
            avatar="a2", google_picture="https://lh3.example/photo.jpg"
        )
        finish_round(user, 5)

        body = self.client.get(ALL_TIME_URL).content.decode()

        self.assertNotIn("lh3.example", body, "안 쓰는 구글 사진 주소가 나갔다")
        self.assertEqual(
            self.client.get(ALL_TIME_URL).json()["rows"][0]["avatar"],
            {"type": "preset", "key": "a2"},
        )
