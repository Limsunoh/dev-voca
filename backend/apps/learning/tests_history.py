"""내 학습 기록.

지키는 것 셋.

1. **하루 점수가 꾸준함 순위표와 같다.** 같은 표(DailyScore)를 같은
   규칙(total)으로 읽는다. 어긋나면 순위표의 "며칠" 과 이 화면의 칸 수가
   다르게 나온다.
2. **날짜는 한국 날짜다.** 새벽에 끝낸 판이 전날로 붙지 않는다.
3. **내 것만.**
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from . import calendar_kst, session
from .models import DailyScore, QuizSession, SessionKind
from .tests_mistakes import answer_of, seed_words
from .views_history import HISTORY_DAYS, HISTORY_ROUNDS, HistoryThrottle, MistakesThrottle

PASSWORD = secrets.token_urlsafe(16)
URL = "/api/learning/history/"


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def daily(user, day, *, best=None, study=0) -> DailyScore:
    return DailyScore.objects.create(
        user=user, day=day, best_free_score=best, daily_study_score=study
    )


def round_at(user, finished_at: datetime, *, score=5, kind=SessionKind.FREE) -> QuizSession:
    return QuizSession.objects.create(
        user=user,
        kind=kind,
        token_id=uuid4().hex,
        started_at=finished_at - timedelta(seconds=90),
        finished_at=finished_at,
        score=score,
        answered=10,
        correct=7,
    )


def freeze_today(case: TestCase):
    """오늘을 고정한다.

    테스트는 setUp 에서, 뷰는 요청 때 오늘을 따로 구한다. 그 사이에 한국
    자정을 넘기면 둘이 하루 어긋나 빨개진다(월말에만 터지던 e682448 과 같은
    종류). 둘이 같은 값을 보게 묶는다.
    """
    today = calendar_kst.today()
    patcher = mock.patch.object(calendar_kst, "today", return_value=today)
    patcher.start()
    case.addCleanup(patcher.stop)
    return today


class HistoryDaysTest(TestCase):
    def setUp(self):
        self.user = make_user("기록")
        self.client.force_login(self.user)
        self.today = freeze_today(self)

    def test_requires_login(self):
        self.client.logout()

        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_always_fourteen_days_oldest_first_ending_today(self):
        """안 한 날도 칸이 있다. 빠진 날을 화면이 메우게 하지 않는다."""
        days = self.client.get(URL).json()["days"]

        self.assertEqual(len(days), HISTORY_DAYS)
        self.assertEqual(days[-1]["day"], self.today.isoformat())
        self.assertEqual(
            days[0]["day"], (self.today - timedelta(days=HISTORY_DAYS - 1)).isoformat()
        )
        self.assertTrue(all(d["total"] == 0 for d in days))
        # 줄이 아예 없는 날도 판은 null 이다. 0 이면 화면이 "0점" 이라고 읽는다.
        self.assertTrue(all(d["best_round"] is None for d in days))

    def test_day_total_matches_the_streak_board_rule(self):
        """꾸준함 순위표와 같은 값 - DailyScore.total 그대로.

        마이너스 판만 한 날은 0 으로 잘린다. 여기서 따로 더하면 -3 이
        나와 순위표와 어긋난다.
        """
        # 기대값을 숫자로 적는다. DailyScore.total 을 불러 비교하면 뷰가 쓰는
        # 것과 같은 코드를 양쪽에서 부르는 셈이라, total 이 틀려도 같이 틀려
        # 절대 빨개지지 않는다.
        cases = [
            (0, dict(best=12, study=5), 17),
            (1, dict(best=-3, study=0), 0),
            (2, dict(best=None, study=8), 8),
        ]
        for back, kwargs, _ in cases:
            daily(self.user, self.today - timedelta(days=back), **kwargs)

        by_day = {d["day"]: d for d in self.client.get(URL).json()["days"]}

        for back, _, expected in cases:
            day = (self.today - timedelta(days=back)).isoformat()
            with self.subTest(back=back):
                self.assertEqual(by_day[day]["total"], expected)

    def test_a_day_without_a_round_says_null_not_zero(self):
        """판을 안 한 날의 best_round 는 null 이다. 0 은 "0점 판" 으로 읽힌다."""
        daily(self.user, self.today, best=None, study=6)

        today = self.client.get(URL).json()["days"][-1]

        self.assertIsNone(today["best_round"])
        self.assertEqual(today["daily_study"], 6)

    def test_a_zero_point_study_day_is_recorded_not_empty(self):
        """일일공부를 다 틀린 날은 "0점" 이지 "안 함" 이 아니다.

        일일공부는 감점이 없어 다 틀려도 그날 줄만 생기고 두 칸이 null·0 이다.
        안 한 날과 똑같이 보여서, 화면이 두 칸으로 짐작하면 "안 함" 으로
        읽었다. 줄이 있다는 사실을 따로 보낸다.
        """
        daily(self.user, self.today, best=None, study=0)

        days = self.client.get(URL).json()["days"]

        self.assertEqual(days[-1]["total"], 0)
        self.assertTrue(days[-1]["recorded"], "공부한 날을 안 한 날로 보냈다")
        self.assertFalse(days[-2]["recorded"], "줄이 없는 날을 공부한 날로 보냈다")

    def test_window_edges(self):
        """창의 첫날은 들어가고, 그 하루 전은 안 들어간다.

        첫날에 데이터를 넣어야 경계가 지켜진다. 창 밖 날만 보면 필터를
        `day__gt` 로 잘못 바꿔도(첫날이 늘 0 이 된다) 통과한다 - 뷰가 칸을
        창 안 날짜로만 만들어서, 창 밖 날은 필터가 어떻든 안 보인다.
        """
        first = self.today - timedelta(days=HISTORY_DAYS - 1)
        daily(self.user, first, best=7)
        daily(self.user, first - timedelta(days=1), best=99)

        days = self.client.get(URL).json()["days"]

        self.assertEqual(days[0]["day"], first.isoformat())
        self.assertEqual(days[0]["total"], 7)
        self.assertNotIn(99, [d["total"] for d in days])

    def test_other_peoples_days_are_not_mine(self):
        daily(make_user("남"), self.today, best=40)

        self.assertEqual(self.client.get(URL).json()["days"][-1]["total"], 0)


class HistoryRoundsTest(TestCase):
    def setUp(self):
        self.user = make_user("판기록")
        self.client.force_login(self.user)
        self.today = freeze_today(self)
        self.now = calendar_kst.day_begins(self.today) + timedelta(hours=12)

    def test_newest_first_and_capped(self):
        for i in range(HISTORY_ROUNDS + 3):
            round_at(self.user, self.now - timedelta(hours=i), score=i)

        rounds = self.client.get(URL).json()["rounds"]

        self.assertEqual(len(rounds), HISTORY_ROUNDS)
        self.assertEqual([r["score"] for r in rounds], list(range(HISTORY_ROUNDS)))

    def test_only_free_rounds(self):
        """일일공부 판은 하루 점수로 들어가고 목록에는 안 나온다."""
        round_at(self.user, self.now, score=3, kind=SessionKind.FREE)
        round_at(self.user, self.now, score=9, kind=SessionKind.DAILY)

        rounds = self.client.get(URL).json()["rounds"]

        self.assertEqual([r["score"] for r in rounds], [3])

    def test_round_day_is_korean_date(self):
        """한국 새벽 1시에 끝낸 판은 그날이다. UTC 로 자르면 전날이 된다."""
        kst_day = self.today
        one_am = calendar_kst.day_begins(kst_day) + timedelta(hours=1)
        round_at(self.user, one_am)

        row = self.client.get(URL).json()["rounds"][0]

        self.assertEqual(row["day"], kst_day.isoformat())
        # 대조군. 같은 시각을 UTC 날짜로 자르면 전날이다 - 그래서 이 값이
        # 헛돌지 않는다. 서버가 UTC 로 자르면 위 단언이 빨개진다.
        self.assertEqual(
            one_am.astimezone(timezone.utc).date(), kst_day - timedelta(days=1)
        )

    def test_row_carries_exactly_these_fields(self):
        round_at(self.user, self.now)

        row = self.client.get(URL).json()["rounds"][0]

        self.assertEqual(set(row), {"day", "score", "answered", "correct"})

    def test_other_peoples_rounds_are_not_mine(self):
        round_at(make_user("남판"), self.now)

        self.assertEqual(self.client.get(URL).json()["rounds"], [])


class HistoryCostTest(TestCase):
    def setUp(self):
        self.user = make_user("비용")
        self.client.force_login(self.user)

    def test_query_count_does_not_grow_with_data(self):
        """판과 날이 늘어도 질의 수가 같다."""
        today = freeze_today(self)
        now = calendar_kst.day_begins(today) + timedelta(hours=12)
        for i in range(3):
            daily(self.user, today - timedelta(days=i), best=i)
            round_at(self.user, now - timedelta(hours=i))

        with CaptureQueriesContext(connection) as small:
            self.client.get(URL)

        for i in range(3, 12):
            daily(self.user, today - timedelta(days=i), best=i)
            round_at(self.user, now - timedelta(hours=i))

        with CaptureQueriesContext(connection) as big:
            self.client.get(URL)

        self.assertEqual(len(small), len(big))

    def test_has_its_own_rate_limit_bucket(self):
        """오답 노트와 통이 다르다. 한쪽이 막혀도 다른 쪽은 열린다."""
        with mock.patch.object(HistoryThrottle, "rate", "1/min"), mock.patch.object(
            MistakesThrottle, "rate", "1/min"
        ):
            first = self.client.get(URL).status_code
            second = self.client.get(URL).status_code
            mistakes = self.client.get("/api/learning/mistakes/").status_code

        self.assertEqual((first, second, mistakes), (200, 429, 200))

    def test_the_61st_call_is_refused_but_only_for_that_account(self):
        """분당 60. 61번째는 429 이고, 그 통은 계정마다 따로다.

        한 통을 모두가 쓰면 누군가 내정보를 연타한 것으로 다른 사람의
        학습 기록까지 "불러오지 못했습니다" 가 된다.
        """
        cache.clear()
        with mock.patch.object(HistoryThrottle, "rate", "60/min"):
            codes = [self.client.get(URL).status_code for _ in range(61)]
            self.client.force_login(make_user("옆사람"))
            neighbour = self.client.get(URL).status_code

        self.assertEqual(codes[:60], [200] * 60)
        self.assertEqual(codes[60], 429)
        self.assertEqual(neighbour, 200)

    def test_read_only(self):
        """읽기 전용이라 GET 만 받는다. 쓰기 메서드는 405 이지 500 이 아니다."""
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(URL).status_code, 405)

    def test_a_dead_token_is_401_not_someone_elses_history(self):
        self.client.logout()

        res = self.client.get(URL, HTTP_AUTHORIZATION="Token deadbeefdeadbeef")

        self.assertEqual(res.status_code, 401)


class HistoryTodayTest(TestCase):
    """오늘을 서버가 한국 날짜로 정하는지.

    위 테스트들은 freeze_today 로 calendar_kst.today 를 고정한다. 그러면
    뷰가 calendar_kst 를 건너뛰고 `timezone.now().date()`(UTC) 로 오늘을
    구해도 초록이다 - 고정한 함수를 아예 안 부르니까. 그래서 여기서는
    **시계**를 한국 새벽으로 돌린다. UTC 로는 아직 전날이고 전달이다.
    """

    # 3월 1일 00:30 KST = 2월 28일 15:30 UTC. 날짜도 달도 갈린다.
    DAWN_DAY = date(2026, 3, 1)

    def setUp(self):
        self.user = make_user("새벽")
        self.client.force_login(self.user)
        self.dawn = calendar_kst.day_begins(self.DAWN_DAY) + timedelta(minutes=30)
        # 진짜 timezone.now 처럼 UTC 로 준다. 한국 시간대가 붙은 값을 주면
        # `.date()` 가 그대로 한국 날짜를 내서, UTC 로 오늘을 구하는 뷰도
        # 통과한다(실제로 그렇게 헛돌았다).
        patcher = mock.patch(
            "django.utils.timezone.now", return_value=self.dawn.astimezone(timezone.utc)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_last_cell_is_the_korean_today_at_dawn(self):
        daily(self.user, self.DAWN_DAY, best=4)
        round_at(self.user, self.dawn, score=4)

        body = self.client.get(URL).json()

        self.assertEqual(body["days"][-1]["day"], "2026-03-01")
        self.assertEqual(body["days"][-1]["total"], 4)
        self.assertEqual(body["days"][0]["day"], "2026-02-16")
        self.assertEqual(body["rounds"][0]["day"], "2026-03-01")


def play(client, at: datetime, answers: list[bool]) -> dict:
    """화면이 부르는 API 로 판 하나를 돌고 끝낸다. `at` 에 끝낸 것으로 친다.

    시계만 돌린다. 판 토큰의 서명 수명은 time.time 으로 재서 영향이 없고,
    마감·기록 시각은 timezone.now 라 판 전체가 같은 순간에 일어난 것이 된다
    (전부 제한 시간 안의 답이다).
    """
    with mock.patch("django.utils.timezone.now", return_value=at.astimezone(timezone.utc)):
        body = client.post(
            "/api/learning/rounds/", {}, content_type="application/json"
        ).json()
        token, question = body["token"], body["question"]
        for correct in answers:
            _, aid = answer_of(session._load, token)
            pick = aid if correct else next(
                c["id"] for c in question["choices"] if c["id"] != aid
            )
            answered = client.post(
                "/api/learning/rounds/answer/",
                {"token": token, "choice_id": pick},
                content_type="application/json",
            ).json()
            token, question = answered["token"], answered.get("question")
        return client.post(
            "/api/learning/rounds/finish/",
            {"token": token},
            content_type="application/json",
        ).json()


class HistoryByApiTest(TestCase):
    """판을 실제 API 로 풀어 쌓은 뒤 기록을 본다.

    위 테스트들은 DailyScore 를 손으로 심는다. 그러면 "판을 끝내면 어느
    날 칸에 붙나" 는 record 와 이 뷰가 **각자** 날짜를 구하는 것이라,
    둘이 다른 규칙으로 갈려도 손으로 심은 쪽은 모른다.
    """

    STREAK_URL = "/api/learning/leaderboards/streak/"

    def setUp(self):
        cache.clear()
        seed_words(60)
        self.user = make_user("실제로푼사람")
        self.client.force_login(self.user)
        self.today = freeze_today(self)

    def at(self, back: int, *, hours: float = 12) -> datetime:
        """오늘에서 back 일 전, 한국 시각 hours 시."""
        return calendar_kst.day_begins(self.today - timedelta(days=back)) + timedelta(
            hours=hours
        )

    def test_scored_days_match_the_streak_board(self):
        """꾸준함 순위표 내 줄의 "며칠" 과 점수 있는 칸 수가 같다.

        순위표는 전 기간을 센다. 그래서 판을 전부 14일 안에 둔다 - 그래야
        둘이 같은 것을 세는 상황이 된다. 0점 판, 마이너스 판, 한 날 두 판을
        섞는다. 앞의 둘은 행은 생기지만 "며칠" 에는 안 들어가야 한다.
        """
        self.assertEqual(play(self.client, self.at(0), [True, True])["score"], 2)
        play(self.client, self.at(0, hours=13), [True])  # 같은 날 낮은 판
        self.assertEqual(play(self.client, self.at(1), [False])["score"], -1)
        self.assertEqual(play(self.client, self.at(5), [True, False])["score"], 0)
        play(self.client, self.at(HISTORY_DAYS - 1), [True])  # 창의 첫날

        body = self.client.get(URL).json()
        me = next(r for r in self.client.get(self.STREAK_URL).json()["rows"] if r["is_me"])

        self.assertEqual(sum(d["total"] > 0 for d in body["days"]), me["entries"])
        self.assertEqual(sum(d["total"] for d in body["days"]), me["score"])
        # 마이너스 판만 한 날: 칸은 0 이지만 판은 있었다(null 이 아니다).
        self.assertEqual(
            (body["days"][-2]["total"], body["days"][-2]["best_round"]), (0, -1)
        )
        # 판 목록은 잘리지 않은 점수를 그대로 싣는다.
        self.assertIn(-1, [r["score"] for r in body["rounds"]])

    def test_a_round_lands_on_the_korean_day_it_ended(self):
        """자정 경계. 한국 자정과 UTC 자정(= 한국 오전 9시) 양쪽을 찌른다.

        (끝낸 시각, 붙어야 할 날이 오늘에서 며칠 전인지). 판 목록의 날짜와
        칸의 날짜가 같은 날을 가리켜야 한다 - 한쪽만 UTC 로 자르면 판은
        어제인데 칸은 오늘이 칠해진다.
        """
        second = timedelta(seconds=1)
        utc_midnight = datetime.combine(self.today, datetime.min.time(), timezone.utc)
        cases = [
            (self.at(1, hours=0) - second, 2),  # 그저께 23:59:59 KST
            (self.at(1, hours=0), 1),  # 어제 00:00:00 KST
            (utc_midnight - second, 0),  # 오늘 08:59:59 KST
            (utc_midnight, 0),  # 오늘 09:00:00 KST
        ]
        for when, _ in cases:
            play(self.client, when, [True])

        body = self.client.get(URL).json()
        by_day = {d["day"]: d["total"] for d in body["days"]}
        # 판 목록은 늦게 끝난 것부터라 cases 의 거꾸로다.
        round_days = [r["day"] for r in reversed(body["rounds"])]

        for (when, back), round_day in zip(cases, round_days):
            expected = (self.today - timedelta(days=back)).isoformat()
            with self.subTest(when=when.isoformat()):
                self.assertEqual(round_day, expected)
                self.assertEqual(by_day[expected], 1)

    def test_window_starts_at_korean_midnight_of_the_first_day(self):
        """창의 첫날 00:00 KST 에 끝낸 판은 들어가고, 1초 전 판은 안 들어간다."""
        first_begins = self.at(HISTORY_DAYS - 1, hours=0)
        play(self.client, first_begins - timedelta(seconds=1), [True, True])
        play(self.client, first_begins, [True])

        days = self.client.get(URL).json()["days"]

        self.assertEqual(days[0]["total"], 1)
        self.assertEqual(sum(d["total"] for d in days), 1)

    def test_two_accounts_playing_side_by_side_do_not_mix(self):
        """같은 시각에 번갈아 풀어도 각자 제 판만 본다."""
        other = self.client_class()
        other.force_login(make_user("옆자리"))

        play(self.client, self.at(0), [True])
        play(other, self.at(0), [True, True, True])
        play(self.client, self.at(0, hours=13), [False])

        mine = self.client.get(URL).json()
        theirs = other.get(URL).json()

        self.assertEqual([r["score"] for r in mine["rounds"]], [-1, 1])
        self.assertEqual([r["score"] for r in theirs["rounds"]], [3])
        self.assertEqual((mine["days"][-1]["total"], theirs["days"][-1]["total"]), (1, 3))
