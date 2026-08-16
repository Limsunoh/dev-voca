"""순위표 3차 - 새로 생긴 표면을 깨뜨리려고 쓴 테스트.

tests_leaderboards.py 는 규칙을, tests_leaderboards_edge.py 는 경계를 본다.
여기는 그 둘이 안 건드린 **세 자리**를 판다.

    1. 스로틀 통 분리 - 순위표별 / 로그인별 / 게스트와 회원 사이
    2. first_at 절충 - 판을 여러 번 한 사람이 섞였을 때 목록과 me.rank 가
       서로 어긋나는지. 절충 자체는 알려진 것이고, **둘이 갈리는 것**이
       진짜 결함이다
    3. ahead 의 3중 OR - 점수와 first_at 이 완전히 같은 무리에서 등수가
       뭉치거나 겹치는지

절충(첫 판 시각으로 동점을 가르는 것)은 결함으로 보지 않는다. 목록과 내
등수가 **같은 절충**을 쓰는 한 화면은 일관된다. 여기서 잡으려는 것은
"한쪽만 절충을 쓰는" 경우다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from . import calendar_kst, leaderboards
from .models import DailyScore, QuizSession, SessionKind
from .throttles import LeaderboardThrottle

User = get_user_model()

WEEKLY_URL = "/api/learning/leaderboards/weekly/"
ALL_TIME_URL = "/api/learning/leaderboards/all-time/"
STREAK_URL = "/api/learning/leaderboards/streak/"
BOARD_URLS = (WEEKLY_URL, ALL_TIME_URL, STREAK_URL)

PASSWORD = secrets.token_urlsafe(16)

# 스로틀을 실제로 채워보려면 한도가 낮아야 한다. 테스트 설정은 5000/분이라
# 그대로는 통을 못 채운다.
TIGHT = "3/min"


def tighten(rate: str):
    """순위표 한도를 낮춘다.

    **override_settings 로는 안 된다.** DRF 의 SimpleRateThrottle 은
    THROTTLE_RATES 를 import 시점에 클래스 속성으로 굳혀서, 설정을 나중에
    바꿔도 안 읽는다(settings.py 의 DEFAULT_THROTTLE_RATES 주석이 말하는
    그 성질이다). 그래서 클래스 속성을 직접 갈아끼운다.

    이미 만들어진 인스턴스는 걱정 안 해도 된다. DRF 가 요청마다
    get_throttles() 로 새로 만들고 __init__ 이 THROTTLE_RATES 를 다시
    읽는다.
    """
    return patch.dict(
        LeaderboardThrottle.THROTTLE_RATES, {"leaderboard": rate}
    )


def make_user(name: str) -> User:
    return User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def bulk_users(prefix: str, count: int) -> list:
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


class RankAgreementMixin:
    """목록과 내 등수가 **같은 순서**를 말하는지 본다.

    edge.py 의 assertBoardIsSane 은 "겹치지 않는지" 를 본다. 여기는 한 발
    더 나아가, 전원의 등수를 모아 1..N 이 되는지와 순서가 목록과 이어지는지를
    본다 - 겹치지 않아도 순서가 뒤바뀔 수 있다.
    """

    def ranks_of(self, kind: str, people: list) -> dict[int, int]:
        """전원의 등수. 목록 안이면 목록에서, 밖이면 me 에서 가져온다.

        내 줄은 **is_me 로 찾는다.** 응답에 pk 가 없으므로 그것이 화면이
        쓰는 유일한 방법이고, 여기서도 같은 것을 쓴다.
        """
        found: dict[int, int] = {}
        for user in people:
            board = leaderboards.build(kind, user=user)
            mine_in_list = [row for row in board.rows if row.is_me]

            self.assertLessEqual(
                len(mine_in_list), 1, f"{user.display_name}: 목록에 내 줄이 둘이다"
            )

            if mine_in_list:
                self.assertIsNone(
                    board.me, f"{user.display_name}: 목록 안인데 내 줄도 나왔다"
                )
                found[user.pk] = mine_in_list[0].rank
                continue

            self.assertIsNotNone(board.me, f"{user.display_name}: 줄이 아예 없다")
            self.assertTrue(board.me.is_me, f"{user.display_name}: me 인데 is_me 가 거짓")
            self.assertNotIn(
                board.me.rank,
                [row.rank for row in board.rows],
                f"{user.display_name}: 내 등수가 목록 등수와 겹친다",
            )
            found[user.pk] = board.me.rank

        return found

    def assertRanksFormASequence(self, ranks: dict[int, int], note: str = ""):
        values = sorted(ranks.values())
        self.assertEqual(
            values,
            list(range(1, len(values) + 1)),
            f"등수가 1..{len(values)} 가 아니다{note}: {values}",
        )


class ThrottleBucketTest(TestCase):
    """스로틀 통이 순위표별·계정별로 갈리는지.

    통이 공용이면 화면 한 번 여는 것(셋을 동시에 부른다)이 한도 3회를
    쓴다. 반대로 갈라놨다고 믿고 한도를 낮췄는데 실제로 안 갈렸으면
    사용자가 새로고침 두 번에 429 를 본다.
    """

    def setUp(self):
        cache.clear()

    def burn(self, url: str, times: int) -> list[int]:
        return [self.client.get(url).status_code for _ in range(times)]

    def test_burning_one_board_leaves_the_other_two_open(self):
        """weekly 를 한도까지 태워도 all_time / streak 는 열려 있어야 한다.

        통이 하나면 여기서 나머지 둘이 곧바로 429 가 된다.

        로그인해서 본다. 게스트 통은 배수(20)가 곱해져 한도가 흐려진다 -
        여기서 재는 것은 배수가 아니라 **통이 갈렸는지**다.
        """
        self.client.force_login(make_user("한판만태운사람"))

        with tighten(TIGHT):
            self.assertEqual(self.burn(WEEKLY_URL, 3), [200, 200, 200])
            self.assertEqual(
                self.client.get(WEEKLY_URL).status_code, 429, "한도가 안 걸렸다"
            )

            self.assertEqual(
                self.client.get(ALL_TIME_URL).status_code, 200, "통이 섞였다"
            )
            self.assertEqual(
                self.client.get(STREAK_URL).status_code, 200, "통이 섞였다"
            )

    def test_each_board_has_its_own_budget(self):
        """셋을 각각 한도까지 태울 수 있어야 한다.

        화면이 셋을 한꺼번에 부른다. 통이 공용이면 실제 한도가 1/3 이 된다 -
        첫 순위표에서 다 쓰고 나머지 둘은 첫 요청부터 429 다.
        """
        self.client.force_login(make_user("셋다태운사람"))

        with tighten(TIGHT):
            for url in BOARD_URLS:
                with self.subTest(url=url):
                    self.assertEqual(
                        self.burn(url, 3), [200, 200, 200], f"{url}: 몫이 깎였다"
                    )

            for url in BOARD_URLS:
                with self.subTest(url=url, phase="after"):
                    self.assertEqual(self.client.get(url).status_code, 429)

    def test_two_logged_in_users_do_not_share_a_bucket(self):
        """한 사람이 한도를 다 써도 다른 사람은 안 막힌다.

        통이 계정별이 아니면 아무나 전원을 막을 수 있는 스위치를 쥔다.
        """
        first = make_user("스로틀갑")
        second = make_user("스로틀을")

        with tighten(TIGHT):
            self.client.force_login(first)
            self.assertEqual(self.burn(ALL_TIME_URL, 3), [200, 200, 200])
            self.assertEqual(self.client.get(ALL_TIME_URL).status_code, 429)

            self.client.force_login(second)
            self.assertEqual(
                self.client.get(ALL_TIME_URL).status_code,
                200,
                "다른 계정이 남의 한도에 막혔다",
            )

    def test_a_logged_in_user_is_not_blocked_by_the_guest_bucket(self):
        """게스트가 통을 다 태워도 로그인한 사람은 들어갈 수 있어야 한다.

        게스트 통은 공용이라 누구든 태울 수 있다. 그것이 회원까지 막으면
        스크립트 하나로 전 사용자가 순위표를 못 본다.
        """
        member = make_user("회원")

        with tighten(TIGHT):
            # 게스트 통은 배수(20)만큼 크다. 3 * 20 = 60 을 다 태운다.
            statuses = self.burn(ALL_TIME_URL, 61)
            self.assertEqual(statuses[-1], 429, "게스트 통이 안 찼다")

            self.client.force_login(member)
            self.assertEqual(
                self.client.get(ALL_TIME_URL).status_code,
                200,
                "게스트 통이 회원까지 막았다",
            )

    def test_a_logged_out_user_does_not_inherit_their_own_bucket(self):
        """로그아웃하면 게스트 통으로 넘어간다. 계정 통이 게스트를 막지 않는다."""
        user = make_user("나갔다들어온사람")

        with tighten(TIGHT):
            self.client.force_login(user)
            self.assertEqual(self.burn(STREAK_URL, 3), [200, 200, 200])
            self.assertEqual(self.client.get(STREAK_URL).status_code, 429)

            self.client.logout()
            self.assertEqual(
                self.client.get(STREAK_URL).status_code,
                200,
                "계정 통이 게스트 통과 섞였다",
            )

    def test_the_guest_bucket_is_wider_than_a_members(self):
        """게스트 통은 배수(20)만큼 크다.

        게스트는 나눌 키가 없어 다 함께 쓴다. 통이 회원과 같은 크기면
        방문자 몇 명만 들어와도 전원이 막힌다.
        """
        with tighten(TIGHT):
            # 회원 한도는 3. 게스트는 3 * 20 = 60 이어야 한다.
            statuses = self.burn(WEEKLY_URL, 61)

            self.assertEqual(statuses[:3], [200, 200, 200])
            self.assertEqual(statuses[59], 200, "게스트 통이 회원 통만큼 좁다")
            self.assertEqual(statuses[60], 429, "게스트 통에 한도가 없다")

    def test_throttling_does_not_leak_across_boards_for_a_member(self):
        """로그인 상태에서도 순위표별로 통이 갈린다.

        게스트에서만 갈리고 회원은 공용이면, 정작 자주 보는 쪽이 막힌다.
        """
        user = make_user("회원세판")

        with tighten(TIGHT):
            self.client.force_login(user)
            self.burn(WEEKLY_URL, 4)

            self.assertEqual(self.client.get(WEEKLY_URL).status_code, 429)
            self.assertEqual(self.client.get(ALL_TIME_URL).status_code, 200)
            self.assertEqual(self.client.get(STREAK_URL).status_code, 200)

    def test_a_throttled_board_is_not_a_server_error(self):
        """한도를 넘으면 429 다. 500 이면 안 되고 본문도 읽을 수 있어야 한다."""
        self.client.force_login(make_user("429볼사람"))

        with tighten(TIGHT):
            self.burn(ALL_TIME_URL, 4)
            res = self.client.get(ALL_TIME_URL)

            self.assertEqual(res.status_code, 429)
            self.assertIn("detail", res.json())


class FirstAtWithManyRoundsTest(RankAgreementMixin, TestCase):
    """판을 여러 번 한 사람이 섞였을 때.

    1인 1판이면 첫 판 = 최고점 판이라 절충이 안 드러난다. 여기서는
    사용자마다 판 수를 다르게 두어 first_at 과 "최고점을 낸 판" 을 갈라둔다.

    보는 것은 절충의 옳고 그름이 아니라 **목록과 me.rank 의 일치**다.
    """

    def setUp(self):
        cache.clear()

    def test_list_order_and_my_rank_agree_when_everyone_has_many_rounds(self):
        """전원이 여러 판을 했을 때 목록과 내 등수가 같은 순서를 말해야 한다.

        목록은 first_at 으로 정렬하고 세는 쪽이 최고점 판 시각을 쓰면
        (또는 그 반대면) 여기서 곧바로 갈린다.
        """
        now = timezone.now()
        people = bulk_users("여러판_", 26)

        for i, user in enumerate(people):
            # 첫 판 시각은 i 가 클수록 늦다. 최고점 판은 그 반대 순서로
            # 만든다 - 두 기준이 어긋나야 절충이 드러난다.
            first = now - timedelta(days=30) + timedelta(minutes=i)
            finish_round(user, 1, when=first)
            finish_round(user, 40, when=now - timedelta(minutes=i + 1))
            finish_round(user, 12, when=now - timedelta(hours=2))

        ranks = self.ranks_of(leaderboards.ALL_TIME, people)

        self.assertRanksFormASequence(ranks, " (목록과 내 등수가 갈렸다)")
        # 절충대로라면 첫 판이 이른 순 = pk 오름차순이다.
        self.assertEqual(
            [pk for pk, _ in sorted(ranks.items(), key=lambda kv: kv[1])],
            [user.pk for user in people],
            "정렬 기준이 목록과 세기에서 다르다",
        )

    def test_a_user_with_many_rounds_reports_the_best_score_and_all_entries(self):
        """여러 판을 해도 점수는 최고 한 판, 판 수는 전부여야 한다.

        목록 안과 목록 밖(me) 양쪽에서 같은 값이 나와야 한다 - 두 경로가
        다른 집계를 쓰면 여기서 갈린다.
        """
        now = timezone.now()
        # 목록을 채워 나를 밖으로 밀어낸다.
        for i, other in enumerate(bulk_users("채움_", 22)):
            finish_round(other, 500 - i, when=now - timedelta(hours=3))

        me = make_user("여러판한나")
        for offset, score in enumerate((4, 17, -2, 9, 17)):
            finish_round(me, score, when=now - timedelta(minutes=offset))

        board = leaderboards.build(leaderboards.ALL_TIME, user=me)

        self.assertIsNotNone(board.me, "여러 판을 했는데 줄이 없다")
        self.assertEqual(board.me.score, 17, "최고 한 판이 아니다")
        self.assertEqual(board.me.entries, 5, "판 수가 안 맞는다")

    def test_the_same_user_never_appears_twice_even_with_many_rounds(self):
        """판이 여러 개여도 목록에 한 줄이다. GROUP BY 가 풀리면 도배된다."""
        now = timezone.now()
        hog = make_user("도배할사람")
        for i in range(30):
            finish_round(hog, 50 - i, when=now - timedelta(minutes=i))

        others = bulk_users("평범_", 3)
        for user in others:
            finish_round(user, 10, when=now)

        board = leaderboards.build(leaderboards.ALL_TIME)

        names = [row.display_name for row in board.rows]
        self.assertEqual(len(names), len(set(names)), "같은 사람이 목록에 여러 번 있다")
        self.assertEqual(len(names), 4, "사용자 수와 줄 수가 다르다")
        self.assertEqual(board.rows[0].entries, 30)

    def test_weekly_first_at_is_clipped_to_this_week(self):
        """주간의 first_at 은 이번 주 안에서 잡혀야 한다.

        지난주 판이 first_at 에 섞이면, 오래 한 사람이 주간에서도 영구히
        위를 차지한다 - 주간 순위표를 주마다 리셋하는 의미가 사라진다.
        """
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())

        veteran = make_user("지난주부터")
        finish_round(veteran, 3, when=monday - timedelta(days=10))
        # 이번 주에는 늦게 왔다.
        finish_round(veteran, 20, when=monday + timedelta(days=3))

        newcomer = make_user("이번주월요일")
        finish_round(newcomer, 20, when=monday + timedelta(minutes=5))

        weekly = leaderboards.build(leaderboards.WEEKLY)
        all_time = leaderboards.build(leaderboards.ALL_TIME)

        self.assertEqual(
            [row.display_name for row in weekly.rows],
            ["이번주월요일", "지난주부터"],
            "주간에 지난주 first_at 이 섞였다",
        )
        self.assertEqual(weekly.rows[1].entries, 1, "지난주 판을 주간 판 수에 셌다")
        # 전체 기간에서는 반대다 - 지난주부터 한 사람의 첫 판이 더 이르다.
        self.assertEqual(
            [row.display_name for row in all_time.rows],
            ["지난주부터", "이번주월요일"],
            "전체 기간의 first_at 이 이번 주로 잘렸다",
        )

    def test_my_weekly_rank_uses_the_clipped_first_at_too(self):
        """목록 밖 내 등수도 잘린 first_at 으로 세야 한다.

        목록만 잘리고 세는 쪽이 전 기간 first_at 을 쓰면 등수가 어긋난다.
        """
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())
        people = bulk_users("주간여러판_", 24)

        for i, user in enumerate(people):
            # 지난주 판. 이번 주 순서와 반대로 둔다.
            finish_round(user, 99, when=monday - timedelta(days=3, minutes=i))
            finish_round(user, 15, when=monday + timedelta(minutes=i))

        ranks = self.ranks_of(leaderboards.WEEKLY, people)

        self.assertRanksFormASequence(ranks, " (주간)")
        self.assertEqual(
            ranks[people[-1].pk], 24, "이번 주 첫 판 순서와 등수가 어긋난다"
        )

    def test_a_negative_best_round_still_gets_a_rank(self):
        """전부 마이너스로 끝낸 사람도 최고점 순위표에 줄이 있다.

        꾸준함과 달리 여기는 0 이하를 안 거른다. 끝까지 푼 사람에게
        "기록이 없습니다" 라고 하면 안 된다.
        """
        now = timezone.now()
        for i, other in enumerate(bulk_users("양수_", 21)):
            finish_round(other, 30 - i, when=now - timedelta(hours=1))

        loser = make_user("마이너스만")
        finish_round(loser, -5, when=now)
        finish_round(loser, -9, when=now - timedelta(minutes=1))

        board = leaderboards.build(leaderboards.ALL_TIME, user=loser)

        self.assertIsNotNone(board.me, "마이너스라고 줄이 사라졌다")
        self.assertEqual(board.me.score, -5, "최고 한 판이 아니다")
        self.assertEqual(board.me.rank, 22)


class IdenticalTieTest(RankAgreementMixin, TestCase):
    """점수도 first_at 도 완전히 같은 무리.

    3중 OR 의 마지막 가지(user__lt)만 남는 자리다. 그 가지가 없거나
    조건이 어긋나면 전원이 같은 등수로 뭉친다.
    """

    def setUp(self):
        cache.clear()

    def test_users_with_the_same_score_and_time_get_distinct_ranks(self):
        """점수와 시각이 완전히 같은 25명. 등수는 25개여야 한다."""
        moment = timezone.now() - timedelta(hours=1)
        people = bulk_users("완전동점_", 25)
        for user in people:
            finish_round(user, 42, when=moment)

        ranks = self.ranks_of(leaderboards.ALL_TIME, people)

        self.assertEqual(
            len(set(ranks.values())), 25, f"완전 동점자 등수가 뭉쳤다: {ranks}"
        )
        self.assertRanksFormASequence(ranks, " (완전 동점)")

    def test_identical_ties_break_by_pk_in_both_paths(self):
        """완전 동점은 pk 오름차순으로 갈린다. 목록과 세기가 같은 규칙이어야 한다."""
        moment = timezone.now() - timedelta(hours=2)
        people = bulk_users("pk갈림_", 23)
        for user in people:
            finish_round(user, 7, when=moment)

        ranks = self.ranks_of(leaderboards.ALL_TIME, people)

        by_rank = [pk for pk, _ in sorted(ranks.items(), key=lambda kv: kv[1])]
        self.assertEqual(
            by_rank, sorted(by_rank), "완전 동점에서 pk 순서가 목록과 다르다"
        )

    def test_identical_ties_mixed_with_distinct_ones(self):
        """완전 동점 무리와 서로 다른 시각이 섞였을 때.

        가지 하나만 맞고 나머지가 틀려도 한쪽 무리에서는 통과한다.
        섞어야 세 가지가 다 돈다.
        """
        now = timezone.now()
        same_time = now - timedelta(hours=5)

        identical = bulk_users("같은시각_", 12)
        for user in identical:
            finish_round(user, 30, when=same_time)

        staggered = bulk_users("다른시각_", 12)
        for i, user in enumerate(staggered):
            # 위 무리보다 늦게 시작. 점수는 같다.
            finish_round(user, 30, when=same_time + timedelta(minutes=i + 1))

        ranks = self.ranks_of(leaderboards.ALL_TIME, identical + staggered)

        self.assertRanksFormASequence(ranks, " (섞인 동점)")
        # 같은 시각 무리가 전부 앞이다.
        worst_identical = max(ranks[u.pk] for u in identical)
        best_staggered = min(ranks[u.pk] for u in staggered)
        self.assertLess(
            worst_identical, best_staggered, "먼저 달성한 무리가 뒤로 갔다"
        )

    def test_streak_users_identical_in_score_and_days_get_distinct_ranks(self):
        """꾸준함도 점수·활동일이 완전히 같으면 pk 로 갈려야 한다."""
        today = calendar_kst.today()
        people = bulk_users("꾸준완전_", 24)
        for user in people:
            for d in range(3):
                daily(user, today - timedelta(days=d), best=5)

        ranks = self.ranks_of(leaderboards.STREAK, people)

        self.assertEqual(
            len(set(ranks.values())), 24, f"꾸준함 완전 동점이 뭉쳤다: {ranks}"
        )
        self.assertRanksFormASequence(ranks, " (꾸준함 완전 동점)")
        by_rank = [pk for pk, _ in sorted(ranks.items(), key=lambda kv: kv[1])]
        self.assertEqual(by_rank, sorted(by_rank), "pk 순서가 목록과 다르다")

    def test_the_first_listed_user_is_never_outranked_by_a_me_row(self):
        """목록 1등보다 앞선 me 가 나오면 안 된다. rank=0 이나 1 중복이 그것이다."""
        moment = timezone.now()
        people = bulk_users("1등검사_", 30)
        for user in people:
            finish_round(user, 11, when=moment)

        for user in people:
            board = leaderboards.build(leaderboards.ALL_TIME, user=user)
            if board.me is None:
                continue
            with self.subTest(user=user.display_name):
                self.assertGreater(board.me.rank, 1, "목록 밖인데 1등이라고 한다")
                # me 가 있다는 것은 목록 밖이라는 뜻이다. 목록 어디에도
                # 내 줄이 있으면 안 된다.
                self.assertFalse(
                    any(row.is_me for row in board.rows),
                    "목록 안인데 me 도 나왔다",
                )


class StreakAheadBranchTest(RankAgreementMixin, TestCase):
    """_streak_ahead 의 세 가지를 각각 태운다.

    score__gt / (score=, entries__gt) / (score=, entries=, user__lt).
    가지 하나가 죽어도 다른 입력에서는 안 드러난다.
    """

    def setUp(self):
        cache.clear()

    def test_all_three_branches_together(self):
        """점수·활동일·pk 가 골고루 다른 무리에서 전원 등수가 이어져야 한다."""
        today = calendar_kst.today()
        people = bulk_users("가지_", 27)

        for i, user in enumerate(people):
            # 점수는 세 덩이, 그 안에서 활동일이 갈리고, 또 그 안은 pk.
            group = i // 9
            spread = 3 if (i % 9) < 5 else 1
            points = (30 - group * 10) // spread
            for d in range(spread):
                daily(user, today - timedelta(days=d), best=points)

        ranks = self.ranks_of(leaderboards.STREAK, people)

        self.assertRanksFormASequence(ranks, " (꾸준함 3가지)")

    def test_a_zero_score_user_is_behind_everyone_scored(self):
        """0점인 나는 점수 있는 사람 전원 뒤여야 한다.

        목록은 0점을 빼지만 세는 쪽은 안 뺀다. 그 비대칭이 어긋나면 0점이
        목록 사람들 사이 등수를 받는다.
        """
        today = calendar_kst.today()
        scorers = bulk_users("점수있음_", 23)
        for i, user in enumerate(scorers):
            daily(user, today, best=50 - i)

        zero = make_user("영점인나")
        for d in range(6):
            daily(zero, today - timedelta(days=d), best=-4)

        board = leaderboards.build(leaderboards.STREAK, user=zero)

        self.assertEqual(board.me.score, 0)
        self.assertEqual(
            board.me.rank, 24, "0점이 점수 있는 사람 사이로 들어갔다"
        )

    def test_a_cancelled_day_is_not_an_active_day(self):
        """상쇄되어 총점 0인 날은 활동일이 아니다.

        best=5, study=-5 인 날은 두 칸 중 하나가 양수라 칸을 따로 보면
        활동일이 된다. 그러면 **점수를 안 준 날**로 등수를 살 수 있다.
        활동일 판정도 하루 총점으로 해야 한다.
        """
        today = calendar_kst.today()
        scorer = make_user("유일점수")
        daily(scorer, today, best=99)

        # 상쇄된 날 둘. 총점 0이고 활동일도 0이어야 한다.
        cancelled = make_user("상쇄된사람")
        daily(cancelled, today, best=5, study=-5)
        daily(cancelled, today - timedelta(days=1), best=3, study=-3)

        # 전부 마이너스. 역시 총점 0, 활동일 0.
        blank = make_user("전부마이너스")
        for d in range(4):
            daily(blank, today - timedelta(days=d), best=-1)

        first = leaderboards.build(leaderboards.STREAK, user=cancelled)
        second = leaderboards.build(leaderboards.STREAK, user=blank)

        self.assertEqual(first.me.score, 0)
        self.assertEqual(second.me.score, 0)
        self.assertEqual(first.me.entries, 0, "상쇄된 날을 활동일로 셌다")
        self.assertEqual(second.me.entries, 0)
        # 활동일이 같으니 pk 순. 먼저 가입한 쪽이 앞이다.
        self.assertLess(first.me.rank, second.me.rank)

    def test_the_python_total_matches_when_days_cancel_out(self):
        """상쇄되는 날에서도 파이썬 total 과 SQL 합이 같아야 한다."""
        user = make_user("상쇄검사")
        today = calendar_kst.today()
        rows = [
            daily(user, today, best=5, study=-5),          # 0
            daily(user, today - timedelta(days=1), best=-5, study=5),  # 0
            daily(user, today - timedelta(days=2), best=0, study=0),   # 0
            daily(user, today - timedelta(days=3), best=7, study=-3),  # 4
        ]
        expected = sum(row.total for row in rows)

        board = leaderboards.build(leaderboards.STREAK, user=user)

        self.assertEqual(expected, 4, "픽스처가 의도한 값이 아니다")
        self.assertEqual(board.rows[0].score, expected, "SQL 합이 다르다")

    def test_daily_rows_of_inactive_users_do_not_shift_zero_ranks(self):
        """비활성 계정은 0점 무리 안에서도 등수를 밀면 안 된다.

        세는 쿼리는 0점을 안 거르므로, 여기가 비활성 필터가 빠지기 쉬운
        자리다 - 목록에 안 보이는 사람들이라 눈에 안 띈다.
        """
        today = calendar_kst.today()
        gone = bulk_users("떠난영점_", 5)
        for user in gone:
            for d in range(3):
                daily(user, today - timedelta(days=d), best=-2)
        User.objects.filter(pk__in=[u.pk for u in gone]).update(is_active=False)

        me = make_user("남은영점")
        daily(me, today, best=-2)

        board = leaderboards.build(leaderboards.STREAK, user=me)

        self.assertEqual(board.rows, [], "0점이 목록에 들어갔다")
        self.assertEqual(
            board.me.rank, 1, "탈퇴 계정이 0점 등수를 밀었다"
        )


class ApiShapeTest(TestCase):
    """응답 모양. 화면이 그대로 그리는 값이다."""

    def setUp(self):
        cache.clear()

    def test_me_row_carries_every_field_the_rows_do(self):
        """me 와 rows 의 키가 같아야 한다. 화면이 같은 컴포넌트로 그린다."""
        for i, other in enumerate(bulk_users("모양채움_", 21)):
            finish_round(other, 100 - i)

        me = make_user("모양나")
        finish_round(me, 1)
        self.client.force_login(me)

        body = self.client.get(ALL_TIME_URL).json()

        self.assertIsNotNone(body["me"])
        self.assertEqual(
            set(body["me"].keys()),
            set(body["rows"][0].keys()),
            "me 와 rows 의 모양이 다르다",
        )

    def test_all_three_boards_share_one_row_shape(self):
        """세 순위표가 같은 모양을 낸다. 화면이 하나의 컴포넌트로 그린다."""
        user = make_user("세판다한사람")
        finish_round(user, 8)
        daily(user, calendar_kst.today(), best=8)

        shapes = []
        for url in BOARD_URLS:
            rows = self.client.get(url).json()["rows"]
            self.assertEqual(len(rows), 1, f"{url}: 줄이 없다")
            shapes.append(tuple(sorted(rows[0].keys())))

        self.assertEqual(len(set(shapes)), 1, f"순위표마다 모양이 다르다: {shapes}")

    def test_no_email_or_password_field_leaks(self):
        """이메일·비밀번호 해시가 응답에 있으면 안 된다. 게스트도 보는 화면이다."""
        user = make_user("유출검사")
        finish_round(user, 5)
        daily(user, calendar_kst.today(), best=5)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).content.decode()

                self.assertNotIn("example.com", body, "이메일이 나갔다")
                self.assertNotIn("pbkdf2", body, "비밀번호 해시가 나갔다")
                self.assertNotIn("is_staff", body)

    def test_a_photo_avatar_survives_to_the_response(self):
        """구글 사진을 쓰는 사람은 사진이 나가야 한다. 무조건 감추면 그것도 틀리다."""
        user = make_user("구글쓰는사람")
        User.objects.filter(pk=user.pk).update(
            avatar="google", google_picture="https://lh3.example/used.jpg"
        )
        finish_round(user, 5)

        row = self.client.get(ALL_TIME_URL).json()["rows"][0]

        self.assertEqual(
            row["avatar"], {"type": "photo", "url": "https://lh3.example/used.jpg"}
        )

    def test_unsafe_methods_are_rejected(self):
        """읽기 전용이다. 쓰기 메서드가 500 이나 200 이면 안 된다."""
        for url in BOARD_URLS:
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(url=url, method=method):
                    res = getattr(self.client, method)(url)
                    self.assertEqual(res.status_code, 405, f"{method} 가 통과했다")

    def test_query_parameters_are_ignored_not_crashed(self):
        """쿼리스트링을 붙여도 200 이어야 한다. 페이지네이션이 없는 화면이다."""
        user = make_user("쿼리사람")
        finish_round(user, 5)

        for query in (
            "?page=0",
            "?page=999999",
            "?page_size=100000",
            "?kind=streak",
            "?limit=-1",
            "?user=" + "9" * 30,
            "?rows[]=1",
        ):
            with self.subTest(query=query):
                res = self.client.get(ALL_TIME_URL + query)

                self.assertEqual(res.status_code, 200, f"{query} 에서 깨졌다")
                self.assertEqual(len(res.json()["rows"]), 1, f"{query} 가 목록을 바꿨다")

    def test_the_period_dates_are_iso_strings(self):
        """기간이 날짜 문자열이어야 한다. 화면이 그대로 파싱한다."""
        period = self.client.get(WEEKLY_URL).json()["period"]

        monday = calendar_kst.this_week_start()
        self.assertEqual(period["start"], monday.isoformat())
        self.assertEqual(period["end"], calendar_kst.week_end(monday).isoformat())


class BoardKindWiringTest(TestCase):
    """URL 과 board_kind 의 연결. 셋이 서로 다른 것을 봐야 한다."""

    def setUp(self):
        cache.clear()

    def test_each_url_returns_its_own_kind(self):
        """kind 값이 URL 과 맞아야 한다. 뒤바뀌면 화면 제목과 내용이 갈린다."""
        expected = {
            WEEKLY_URL: leaderboards.WEEKLY,
            ALL_TIME_URL: leaderboards.ALL_TIME,
            STREAK_URL: leaderboards.STREAK,
        }
        for url, kind in expected.items():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).json()["kind"], kind)

    def test_the_three_boards_read_different_sources(self):
        """셋이 같은 데이터를 보면 안 된다.

        weekly 는 이번 주 판, all_time 은 전 기간 판, streak 는 DailyScore.
        한 뷰가 다른 board_kind 로 잘못 이어져 있으면 여기서 드러난다.
        """
        monday = calendar_kst.day_begins(calendar_kst.this_week_start())

        old = make_user("지난주만")
        finish_round(old, 77, when=monday - timedelta(days=5))

        now_user = make_user("이번주만")
        finish_round(now_user, 11, when=monday + timedelta(hours=1))

        streaker = make_user("꾸준만")
        daily(streaker, calendar_kst.today(), best=33)

        weekly = self.client.get(WEEKLY_URL).json()["rows"]
        all_time = self.client.get(ALL_TIME_URL).json()["rows"]
        streak = self.client.get(STREAK_URL).json()["rows"]

        self.assertEqual([r["display_name"] for r in weekly], ["이번주만"])
        self.assertEqual(
            sorted(r["display_name"] for r in all_time), ["이번주만", "지난주만"]
        )
        self.assertEqual([r["display_name"] for r in streak], ["꾸준만"])

    def test_a_view_without_board_kind_fails_loudly(self):
        """board_kind 를 빠뜨린 뷰는 조용히 넘어가면 안 된다.

        throttles 가 getattr 기본값을 안 주는 이유가 이것이다 - 빈 문자열로
        삼키면 그런 뷰들이 통 하나를 같이 쓴다.
        """
        from rest_framework.test import APIRequestFactory

        from .throttles import LeaderboardThrottle
        from .views import LeaderboardView

        class Broken(LeaderboardView):
            pass

        request = APIRequestFactory().get(ALL_TIME_URL)
        request.user = None

        with self.assertRaises(AttributeError):
            LeaderboardThrottle().get_cache_key(request, Broken())


class StreakRankSweepTest(RankAgreementMixin, TestCase):
    """꾸준함 전수 검사.

    edge.py 에 있던 것을 옮겼다. 거기서는 목록 안 20명이 me 가 None 이라
    단언이 통째로 스킵됐다 - RankAgreementMixin 은 목록 안이면 목록에서
    등수를 집으므로 전원이 실제로 검사된다.
    """

    def setUp(self):
        cache.clear()

    def test_every_rank_is_distinct_across_the_list_and_my_row(self):
        today = calendar_kst.today()
        people = bulk_users("꾸준전수_", 26)

        # 전원 12점 동점. 활동일이 3일 또는 2일로 갈려 순서를 정한다.
        for i, user in enumerate(people):
            if i % 2 == 0:
                for d in range(3):
                    daily(user, today - timedelta(days=d), best=4)
            else:
                for d in range(2):
                    daily(user, today - timedelta(days=d), best=6)

        ranks = self.ranks_of(leaderboards.STREAK, people)

        self.assertEqual(len(ranks), 26, "빠진 사람이 있다")
        self.assertRanksFormASequence(ranks, " (꾸준함 26명 동점)")

        # 활동일 3일인 사람들이 앞이어야 한다.
        top_half = {people[i].pk for i in range(0, 26, 2)}
        for pk, rank in ranks.items():
            if pk in top_half:
                self.assertLessEqual(rank, 13, "활동일이 많은 쪽이 뒤로 갔다")
