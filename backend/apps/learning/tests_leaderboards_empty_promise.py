"""빈 순위표가 하는 약속이 실제로 맞는가.

순위표가 비었을 때 화면(frontend Leaderboard.tsx 의 EMPTY_TEXT)이 탭마다
다른 말을 한다.

    이번 주·전체  "지금 한 판을 끝내면 ... 1등으로 올라갑니다."
    꾸준함        "오늘 하루 점수를 1점 이상 모으면 1등으로 올라갑니다."
    게스트        "로그인하고" 를 앞에 붙인 같은 조건

화면 문구는 백엔드 규칙을 말로 옮긴 것이라, 규칙이 바뀌면 문구가 거짓이
된다. 여기서는 빈 DB 에서 실제 API 로 판을 돌려 그 약속을 하나씩 본다.
행을 직접 만들지 않는 이유: 판을 끝내는 길(views.RoundFinishView)이
"한 문제도 안 푼 판" 이나 게스트 판을 거르는데, 행을 바로 넣으면 그
거름망을 지나치지 않아 약속이 맞는지 알 수 없다.

    1. 로그인 사용자가 한 판을 끝내면 이번 주·전체 표에 1등으로 오른다.
       다 틀려 음수인 판도 0점으로 오른다.
    2. 다 틀린 판 하나로는 꾸준함이 여전히 빈 표다. 그래서 꾸준함 문구는
       "한 판" 이 아니라 하루 점수로 말한다.
    3. 맞힌 판이나 일일공부로 점수를 얻으면 꾸준함에 오른다.
    4. 게스트가 끝낸 판은 어느 표에도 안 오른다. 그래서 게스트에게는
       로그인을 권한다.
    5. 이번 주 표는 지난주 판으로 채워지지 않는다. 매주 다시 빈다.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz

from . import calendar_kst, daily_study, leaderboards, session
from .models import QuizSession, StudyLength
from .tests import ANSWER_URL, FINISH_URL, START_URL
from .tests_daily_study import drain, seed_words
from .tests_daily_study_edge import _correct_id_of, answer_wrong
from .tests_leaderboards_edge2 import (
    ALL_TIME_URL,
    STREAK_URL,
    WEEKLY_URL,
    finish_round,
    make_user,
)

BEST_BOARDS = (leaderboards.WEEKLY, leaderboards.ALL_TIME)
ALL_BOARDS = leaderboards.KINDS
BOARD_URLS = {
    leaderboards.WEEKLY: WEEKLY_URL,
    leaderboards.ALL_TIME: ALL_TIME_URL,
    leaderboards.STREAK: STREAK_URL,
}

RIGHT = "right"
WRONG = "wrong"
SKIP = "skip"


class EmptyBoardPromiseTest(TestCase):
    """빈 DB 에서 한 사람이 처음 오르는 길."""

    def setUp(self):
        # 스로틀 통이 테스트 사이로 새지 않게 비운다.
        cache.clear()
        seed_words()
        self.user = make_user("첫사람")

    # ---- 도우미 ----

    def play_round(self, moves: list[str]) -> dict:
        """API 로 한 판을 돈다. moves 대로 맞히고 틀리고 넘긴 뒤 끝낸다.

        정답은 판 상태에서 읽는다. 보기를 하나씩 보내 찾는 것은 되돌리기
        방어에 막힌다.
        """
        res = self.client.post(START_URL, {}, content_type="application/json")
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        token, question = data["token"], data["question"]

        for move in moves:
            self.assertIsNotNone(question, "판이 일찍 끝났다")
            if move == SKIP:
                body = {"token": token, "skip": True}
            else:
                _, answer_id = quiz.resolve_answer(session._load(token)["q"], -1)
                if move == RIGHT:
                    picked = answer_id
                else:
                    picked = next(c["id"] for c in question["choices"] if c["id"] != answer_id)
                body = {"token": token, "choice_id": picked}

            res = self.client.post(ANSWER_URL, body, content_type="application/json")
            self.assertEqual(res.status_code, 200, res.content)
            data = res.json()
            token, question = data["token"], data["question"]

        res = self.client.post(FINISH_URL, {"token": token}, content_type="application/json")
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def board(self, kind: str):
        return leaderboards.build(kind, user=self.user)

    def assertOnTopAs(self, kind: str, score: int):
        """이 표의 첫 이름이 나이고 점수가 score 다."""
        board = self.board(kind)
        self.assertEqual(len(board.rows), 1, f"{kind} 에 한 줄이 아니다")
        row = board.rows[0]
        self.assertEqual(row.rank, 1)
        self.assertTrue(row.is_me, f"{kind} 의 첫 줄이 내가 아니다")
        self.assertEqual(row.score, score)
        self.assertIsNone(board.me, "목록 안인데 me 가 따로 왔다")

    def assertEmptyBoard(self, kind: str):
        self.assertEqual(self.board(kind).rows, [], f"{kind} 가 비어 있지 않다")

    # ---- 출발점 ----

    def test_fresh_db_has_three_empty_boards_for_guest_and_member(self):
        """출발점. 판이 하나도 없으면 세 표 모두 비고 me 도 없다."""
        for kind, url in BOARD_URLS.items():
            with self.subTest(kind=kind, who="guest"):
                body = self.client.get(url).json()
                self.assertEqual(body["rows"], [])
                self.assertIsNone(body["me"])

        self.client.force_login(self.user)
        for kind, url in BOARD_URLS.items():
            with self.subTest(kind=kind, who="member"):
                body = self.client.get(url).json()
                self.assertEqual(body["rows"], [])
                self.assertIsNone(body["me"])

    # ---- 이번 주·전체: "지금 한 판을 끝내면" ----

    def test_an_all_wrong_round_puts_me_first_on_both_best_boards(self):
        """다 틀려 음수로 끝난 판도 이번 주·전체에 0점 1등으로 오른다."""
        self.client.force_login(self.user)

        result = self.play_round([WRONG, WRONG])

        self.assertTrue(result["recorded"], "로그인했는데 판이 안 남았다")
        self.assertEqual(result["score"], -2)
        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertOnTopAs(kind, 0)

    def test_an_all_wrong_round_alone_leaves_streak_empty(self):
        """다 틀린 판 하나로는 꾸준함이 여전히 빈 표다.

        꾸준함 문구가 "한 판을 끝내면" 이면 이 사람은 다 풀고도 빈 표를
        본다. 내 줄은 0일로 따로 오지만 목록에는 없다.
        """
        self.client.force_login(self.user)

        self.play_round([WRONG])

        board = self.board(leaderboards.STREAK)
        self.assertEqual(board.rows, [])
        self.assertIsNotNone(board.me, "0일이어도 내 줄은 와야 한다")
        self.assertEqual(board.me.score, 0)

    def test_a_skip_only_round_still_puts_me_on_best_boards(self):
        """넘기기만 하고 끝낸 판도 끝낸 판이다. 0점으로 오른다."""
        self.client.force_login(self.user)

        result = self.play_round([SKIP])

        self.assertTrue(result["recorded"])
        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertOnTopAs(kind, 0)
        self.assertEmptyBoard(leaderboards.STREAK)

    def test_a_round_closed_without_any_answer_is_not_on_any_board(self):
        """한 문제도 안 풀고 닫은 판은 남지 않는다. 문구의 "끝내면" 의 경계다.

        열고 바로 닫기로 행을 쌓는 것을 막는 거름망이다(views.RoundFinishView).
        이 판으로는 빈 표가 그대로다.
        """
        self.client.force_login(self.user)

        result = self.play_round([])

        self.assertFalse(result["recorded"])
        self.assertEqual(QuizSession.objects.count(), 0)
        for kind in ALL_BOARDS:
            with self.subTest(kind=kind):
                self.assertEmptyBoard(kind)

    # ---- 꾸준함: "점수를 얻으면" ----

    def test_a_round_with_a_point_puts_me_first_on_all_three(self):
        """맞힌 판은 세 표 모두에 오른다. 꾸준함은 1일이다."""
        self.client.force_login(self.user)

        result = self.play_round([RIGHT])

        self.assertEqual(result["score"], 1)
        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertOnTopAs(kind, 1)
        self.assertOnTopAs(leaderboards.STREAK, 1)

    def test_finished_daily_study_puts_me_on_streak_only(self):
        """일일공부를 마치면 다 틀려도 완주 보너스로 점수를 얻어 꾸준함에 오른다.

        일일공부는 판이 아니라 이번 주·전체 표는 그대로 빈다. 그 두 표의
        빈 칸 버튼이 일일공부가 아니라 문제풀이(/test/round)로 보내는 이유다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        study = drain(self.user, study, token, question, answer_fn=answer_wrong)

        self.assertTrue(study.is_done)
        self.assertGreater(study.score, 0, "완주 보너스가 없다")
        self.assertOnTopAs(leaderboards.STREAK, 1)
        for kind in BEST_BOARDS:
            with self.subTest(kind=kind):
                self.assertEmptyBoard(kind)

    def test_daily_study_with_a_correct_answer_midway_is_on_streak(self):
        """끝내지 않아도 맞힌 만큼은 점수다. 꾸준함에 오른다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        daily_study.answer(self.user, token, _correct_id_of(token))

        study.refresh_from_db()
        self.assertFalse(study.is_done)
        self.assertEqual(study.score, 1)
        self.assertOnTopAs(leaderboards.STREAK, 1)

    def test_daily_study_quit_after_wrong_answers_leaves_streak_empty(self):
        """다 틀리고 중간에 그만두면 점수가 0 이라 꾸준함은 여전히 빈 표다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        for _ in range(3):
            _, token, question, _s = answer_wrong(self.user, token, question)

        study.refresh_from_db()
        self.assertFalse(study.is_done)
        self.assertEqual(study.score, 0)
        self.assertEmptyBoard(leaderboards.STREAK)

    # ---- 게스트: "로그인하고 문제를 풀면" ----

    def test_a_guest_round_is_on_no_board(self):
        """게스트가 맞혀서 끝낸 판도 어느 표에도 안 오른다."""
        result = self.play_round([RIGHT, WRONG])

        self.assertTrue(result["guest"])
        self.assertFalse(result["recorded"])
        for kind in ALL_BOARDS:
            with self.subTest(kind=kind):
                self.assertEqual(leaderboards.build(kind).rows, [])

    # ---- 이번 주는 매주 다시 빈다 ----

    def test_last_weeks_round_leaves_this_week_empty(self):
        """지난주 판만 있으면 이번 주 표는 비고 전체 표에는 남는다."""
        last_week = calendar_kst.day_begins(calendar_kst.this_week_start()) - timedelta(minutes=1)
        finish_round(self.user, 4, when=last_week)

        self.assertEmptyBoard(leaderboards.WEEKLY)
        self.assertOnTopAs(leaderboards.ALL_TIME, 4)
