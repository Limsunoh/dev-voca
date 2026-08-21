"""일일공부 경계 - 깨뜨리려고 쓴 테스트.

tests_daily_study.py 가 규칙이 지켜지는지를 본다면, 여기는 규칙이
**어디서 갈리는지**를 본다. 겹치는 시나리오는 안 쓴다.

    - 점수 부풀리기: 같은 순번을 동시에 가져가기, 보기 넷을 한꺼번에,
      마지막 문제에 두 답, 끝난 뒤 답, 남의 토큰으로 내 줄에 답하기
    - 하루 한 번: 동시에 두 번 시작, 끝낸 뒤 다시 시작
    - 점수 규칙: 전부 틀려도 0 밑으로 안 감, 진행 중 규칙 변경 무시,
      DailyScore 와 DailyStudy 가 항상 같은 값
    - API: 게스트, 잘못된 입력 모양, bool choice_id, 없는·망가진·만료 토큰
    - 순위표 연결: 일일공부만 한 날이 꾸준함 점수와 활동일에 들어가나
"""

from __future__ import annotations

import secrets
from uuid import uuid4
from unittest import mock
import threading
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase

from apps.vocab.models import Word

from . import calendar_kst, daily_study, leaderboards
from .models import STUDY_PLANS, DailyScore, DailyStudy, StudyLength
from .session import SessionError
from .tests_daily_study import tomorrow

User = get_user_model()

START_URL = "/api/learning/daily/"
ANSWER_URL = "/api/learning/daily/answer/"
STREAK_URL = "/api/learning/leaderboards/streak/"

PASSWORD = secrets.token_urlsafe(16)


def make_user(name: str) -> User:
    return User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def seed_words(count: int = 120) -> None:
    """문제를 만들 수 있을 만큼 단어를 채운다.

    **RECENT_KEEP(40) 보다 넉넉해야 한다.** 출제가 최근 낸 정답을 후보에서
    빼므로, 단어가 40개 이하면 30분 코스(40문제)가 중간에 후보 고갈로
    끊긴다 - 판은 서버가 닫아주지만 40문제를 약속하고 30문제만 낸다.
    운영 DB 는 검수된 단어가 그보다 훨씬 많다.

    **term 을 호출마다 다르게 짓는다.** Word.term 은 unique 인데,
    TransactionTestCase 는 트랜잭션이 아니라 실제 커밋을 하므로 그 뒤에
    도는 TestCase 가 같은 term 을 또 넣으면 유니크 충돌이다. Postgres 로
    옮기고 나서야 드러났다 - SQLite 에서는 정리 순서가 달라 안 겹쳤다.
    """
    tag = uuid4().hex[:6]
    Word.objects.bulk_create(
        Word(
            term=f"{tag}word{i}",
            meaning=f"뜻{i}",
            description=f"설명{i} 입니다",
            is_reviewed=True,
        )
        for i in range(count)
    )


def answer_wrong(user, token: str, question: dict):
    """정답이 아닌 보기를 골라 답한다. 정답을 알면 그 옆을 고른다."""
    correct_id = _correct_id_of(token)
    picked = next(
        c["id"] for c in question["choices"] if c["id"] != correct_id
    )
    return daily_study.answer(user, token, picked)


def _correct_id_of(token: str) -> int:
    """토큰을 풀어 정답 id 를 알아낸다.

    공격자 시점을 재현하는 도구다. 실제로는 첫 답의 응답이 정답을
    알려주므로 이만큼의 정보는 누구나 얻는다.
    """
    from apps.vocab import quiz

    state = signing.loads(token, salt=daily_study._SALT, max_age=daily_study.TOKEN_MAX_AGE)
    payload = state["q"]
    _, answer_id = quiz.resolve_answer(payload, -1)
    return answer_id


class ReplayTest(TestCase):
    """같은 순번을 두 번 가져갈 수 없다. 이 기능의 핵심 방어다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("되돌리기")

    def test_a_wrong_answer_cannot_be_retried_with_the_leaked_answer(self):
        """틀린 뒤 정답을 알아내 같은 토큰으로 다시 보내면 거절한다.

        이것이 순번을 원자적으로 가져가는 이유 그 자체다. 응답이 정답을
        알려주므로, 막지 않으면 한 번 틀린 문제도 확실히 +1 로 바꿀 수 있다.
        문제 수로 끝나는 규칙이라 절반만 탐색해도 만점이 된다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        result, _, _, _ = answer_wrong(self.user, token, question)
        self.assertFalse(result.correct, "틀리게 답하려 했는데 맞았다")

        leaked = _correct_id_of(token)
        with self.assertRaises(SessionError):
            daily_study.answer(self.user, token, leaked)

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "되돌린 답이 세어졌다")
        self.assertEqual(study.correct, 0, "되돌려서 맞힌 것이 되었다")
        self.assertEqual(study.score, 0, "되돌려서 점수가 올랐다")

    def test_an_old_token_from_several_steps_back_is_refused(self):
        """세 문제 앞의 토큰을 다시 보내도 거절한다.

        바로 직전 것만 막으면 여러 개를 모아뒀다가 쓰는 길이 남는다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)
        stale_token, stale_question = token, question

        for _ in range(3):
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        with self.assertRaises(SessionError):
            daily_study.answer(
                self.user, stale_token, _correct_id_of(stale_token)
            )

    def test_answering_after_the_study_is_done_is_refused(self):
        """끝난 뒤에 남겨둔 토큰을 보내면 거절한다."""
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)

        # 마지막 직전 토큰을 챙겨두고 끝까지 푼다.
        held_token = token
        while question is not None:
            held_token = token
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, held_token, _correct_id_of(held_token))

    def test_the_user_condition_is_what_stops_a_pointed_token(self):
        """토큰이 내 판을 가리켜도 남의 것이면 못 쓴다.

        **user 조건이 실제로 막는 것을 고정한다.** 남의 토큰을 그대로
        쓰는 테스트는 sid 가 남을 가리켜 조회가 빈손이 되므로, user
        조건을 지워도 통과한다 - 그 테스트는 이 가드를 검사하지 않는다.
        여기서는 sid 가 **요청자 판을 정확히 가리키는** 토큰을 만들어,
        남는 방어가 user 하나뿐인 상황을 만든다.

        서명 키가 있어야 만들 수 있는 토큰이라 실제 공격자는 이 자리에
        못 온다. SECRET_KEY 가 새면 세션 위조가 먼저 열리므로 그쪽이
        위협 모델이다. 여기서 고정하는 것은 "가드가 있다" 는 사실이다.
        """
        other = make_user("판주인")
        victim, _, _ = daily_study.start(other, StudyLength.SHORT)
        _, my_token, _ = daily_study.start(self.user, StudyLength.SHORT)

        # 내 토큰의 sid 를 남의 판으로 돌린다. 조회는 그 판을 찾아내지만
        # 소유자가 달라 거절돼야 한다.
        state = signing.loads(
            my_token, salt=daily_study._SALT, max_age=daily_study.TOKEN_MAX_AGE
        )
        state["sid"] = victim.pk
        pointed = signing.dumps(state, salt=daily_study._SALT)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, pointed, _correct_id_of(my_token))

        victim.refresh_from_db()
        self.assertEqual(victim.answered, 0, "남의 판에 답이 들어갔다")

    def test_another_users_token_cannot_be_answered_on_my_row(self):
        """남이 받은 토큰으로 내 줄에 답할 수 없다.

        토큰이 자기 판 번호(sid)를 밝히므로 남의 토큰은 조회 단계에서
        빈손이 된다 - 그 사람 판을 가리키는데 조회는 내 것으로 좁히기
        때문이다. 순번이 겹치는지와 무관하게 막힌다.
        """
        other = make_user("남의토큰")

        daily_study.start(self.user, StudyLength.SHORT)
        _, their_token, _ = daily_study.start(other, StudyLength.SHORT)

        # 남이 먼저 그 문제를 풀어 정답을 알아냈다고 하자.
        leaked = _correct_id_of(their_token)

        # 그 토큰을 내 줄에 그대로 쓴다. 순번(0)이 같아 조건부 UPDATE 를
        # 통과한다 - 토큰에 누구 것인지가 안 들어 있기 때문이다.
        with self.assertRaises(SessionError):
            daily_study.answer(self.user, their_token, leaked)

        study = daily_study.today_of(self.user)
        self.assertEqual(study.answered, 0, "남의 토큰이 내 순번을 소비했다")
        self.assertEqual(study.correct, 0, "남의 토큰으로 맞힌 것이 되었다")

    def test_a_token_signed_with_another_salt_is_refused(self):
        """자유 문제풀이 토큰을 여기에 넣을 수 없다. 서명 용도가 다르다."""
        from . import session as free_session

        forged = signing.dumps({"q": {}, "n": 0}, salt=free_session._SALT)
        daily_study.start(self.user, StudyLength.SHORT)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, forged, 1)

    def test_an_expired_token_is_refused(self):
        """만료된 토큰은 거절한다. 400 이지 500 이 아니다."""
        daily_study.start(self.user, StudyLength.SHORT)
        old = signing.dumps({"q": {}, "n": 0}, salt=daily_study._SALT)

        with patch.object(daily_study, "TOKEN_MAX_AGE", -1):
            with self.assertRaises(SessionError):
                daily_study.answer(self.user, old, 1)

    def test_a_token_without_a_question_is_refused(self):
        """모양은 맞지만 문제가 없는 토큰. 500 이 아니라 SessionError."""
        daily_study.start(self.user, StudyLength.SHORT)
        empty = signing.dumps({"n": 0}, salt=daily_study._SALT)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, empty, 1)

    def test_a_token_whose_step_is_not_a_number_is_refused(self):
        """순번 자리에 문자열을 넣어도 500 이 아니어야 한다."""
        _, token, _ = daily_study.start(self.user, StudyLength.SHORT)
        state = signing.loads(
            token, salt=daily_study._SALT, max_age=daily_study.TOKEN_MAX_AGE
        )
        state["n"] = "0"
        forged = signing.dumps(state, salt=daily_study._SALT, compress=True)

        with self.assertRaises((SessionError, ValueError, TypeError)) as caught:
            daily_study.answer(self.user, forged, 1)

        self.assertIsInstance(
            caught.exception, SessionError, "400 이 아니라 500 이 된다"
        )

    def test_a_huge_step_in_the_token_is_refused(self):
        """순번을 크게 부풀린 토큰. 조건이 안 맞아 거절돼야 한다."""
        _, token, _ = daily_study.start(self.user, StudyLength.SHORT)
        state = signing.loads(
            token, salt=daily_study._SALT, max_age=daily_study.TOKEN_MAX_AGE
        )
        state["n"] = 10**9
        forged = signing.dumps(state, salt=daily_study._SALT, compress=True)

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, forged, 1)


class ScoreRuleTest(TestCase):
    """점수 규칙이 갈리는 자리."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("점수규칙")

    def test_answering_everything_wrong_still_gives_the_bonus_only(self):
        """전부 틀려도 0 밑으로 안 가고, 완주 보너스만 남는다.

        감점이 없다는 규칙이 곧 "매일 와도 손해가 없다" 는 약속이다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)

        while question is not None:
            _, token, question, _ = answer_wrong(self.user, token, question)

        study = daily_study.today_of(self.user)
        total, bonus = STUDY_PLANS[StudyLength.SHORT]

        self.assertEqual(study.correct, 0, "틀리게만 풀었는데 맞은 것이 있다")
        self.assertEqual(study.answered, total)
        self.assertEqual(study.score, bonus, "감점이 있거나 보너스가 빠졌다")

    def test_the_plan_is_frozen_at_start(self):
        """진행 중에 STUDY_PLANS 를 바꿔도 이 판의 규칙은 안 바뀐다.

        문제 수와 보너스를 둘 다 행에 적어두는 이유다. 런타임 표를 보면
        9/10 을 푼 사람이 배포 한 번에 다른 규칙을 받는다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        total, bonus = STUDY_PLANS[StudyLength.SHORT]

        changed = dict(STUDY_PLANS)
        changed[StudyLength.SHORT] = (999, 999)

        with patch.dict(
            "apps.learning.models.STUDY_PLANS", changed, clear=True
        ), patch.dict("apps.learning.daily_study.STUDY_PLANS", changed, clear=True):
            while question is not None:
                picked = question["choices"][0]["id"]
                _, token, question, _study = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertEqual(study.total_questions, total, "문제 수가 바뀌었다")
        self.assertEqual(study.score, study.correct + bonus, "보너스가 바뀌었다")

    def test_the_daily_row_matches_the_study_row(self):
        """DailyScore 와 DailyStudy 가 항상 같은 값이어야 한다.

        순위표가 읽는 것은 DailyScore 인데 화면이 보는 것은 DailyStudy 다.
        두 값이 갈리면 사용자는 자기 점수가 순위에 안 들어갔다고 본다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.MEDIUM)

        while question is not None:
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        study = daily_study.today_of(self.user)
        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())

        self.assertEqual(row.daily_study_score, study.score)

    def test_an_unfinished_study_publishes_progress_without_the_bonus(self):
        """안 끝내도 푼 만큼은 그날 줄에 닿되, 보너스는 안 붙는다.

        "푼 만큼 남는다" 가 순위표까지 참이어야 중간에 그만둔 사람이 0 이
        되지 않는다. 대신 보너스가 미리 나가면 완주하지 않고 완주 점수를
        받는 길이 열린다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(3):
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        study = daily_study.today_of(self.user)
        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())

        self.assertFalse(study.is_done, "아직 끝난 것이 아니다")
        self.assertEqual(row.daily_study_score, study.score, "그날 줄과 갈렸다")
        self.assertLessEqual(
            row.daily_study_score, study.answered, "안 끝났는데 보너스가 붙었다"
        )

    def test_running_out_of_questions_closes_without_the_bonus(self):
        """낼 문제가 떨어지면 닫되 보너스는 안 준다.

        여기서 안 닫으면 오늘 줄이 영영 열린 채 남아 사용자가 다시는
        못 끝낸다. 반대로 보너스를 주면 콘텐츠를 지워 완주를 사는 길이 된다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        picked = question["choices"][0]["id"]
        with patch.object(daily_study, "make_question", return_value=None):
            result, next_token, next_question, _study = daily_study.answer(
                self.user, token, picked
            )

        study.refresh_from_db()
        self.assertIsNone(next_token)
        self.assertIsNone(next_question)
        self.assertTrue(study.is_done, "문제가 떨어졌는데 안 닫혔다")
        self.assertLessEqual(study.score, 1, "완주도 안 했는데 보너스가 붙었다")

        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())
        self.assertEqual(row.daily_study_score, study.score, "그날 줄과 갈렸다")

    def test_starting_again_after_finishing_is_refused(self):
        """끝낸 뒤 다시 시작할 수 없다. 하루 한 번이 곧 상한이다."""
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)
        while question is not None:
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        with self.assertRaises(SessionError):
            daily_study.start(self.user, StudyLength.LONG)

    def test_a_failed_start_does_not_consume_the_day(self):
        """문제를 못 만들어 시작이 실패하면 오늘을 소진하지 않는다.

        행을 먼저 만들고 실패했다면 그 사람은 오늘 아무것도 못 한다.
        """
        with patch.object(daily_study, "make_question", return_value=None):
            with self.assertRaises(SessionError):
                daily_study.start(self.user, StudyLength.SHORT)

        self.assertFalse(
            DailyStudy.objects.filter(user=self.user).exists(), "빈 줄이 남았다"
        )

        study, _, _ = daily_study.start(self.user, StudyLength.SHORT)
        self.assertIsNotNone(study)


class SecondAccountTest(TestCase):
    """두 번째 계정으로 정답을 미리 캐내는 길. 실제 HTTP 경로로 재현한다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.attacker = make_user("공격자")
        self.mule = make_user("미끼")

    def test_a_second_account_cannot_be_used_to_pre_reveal_answers(self):
        """미끼 계정이 먼저 푼 토큰을 내 줄에 실어 만점을 만들 수 없어야 한다.

        토큰에는 순번만 있고 누구 것인지가 없다. 두 계정을 같은 순번에
        두면, 미끼로 한 번 찍어 정답을 응답에서 보고 그 토큰을 그대로 내
        줄에 보내 확실히 +1 을 만든다. 계정 하나만 더 만들면 되고 위조도
        필요 없다.
        """
        attacker = self.client
        attacker.force_login(self.attacker)
        mule = self.client_class()
        mule.force_login(self.mule)

        total, bonus = STUDY_PLANS[StudyLength.SHORT]

        attacker.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )
        mule_data = mule.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()
        token, question = mule_data["token"], mule_data["question"]

        for _ in range(total):
            probe = mule.post(
                ANSWER_URL,
                {"token": token, "choice_id": question["choices"][0]["id"]},
                content_type="application/json",
            ).json()

            # 응답이 정답을 알려준다. 보기 글자와 맞춰 id 를 찾는다.
            leaked = {probe["result"]["answer_text"], probe["result"]["answer_extra"]}
            correct_id = next(
                (c["id"] for c in question["choices"] if c["text"] in leaked),
                question["choices"][0]["id"],
            )

            got = attacker.post(
                ANSWER_URL,
                {"token": token, "choice_id": correct_id},
                content_type="application/json",
            )
            # 400 이어야 한다. "500 만 아니면" 으로 두면 200 으로 점수가
            # 실제로 올라가도 통과한다.
            self.assertEqual(
                got.status_code, 400, "남의 토큰이 거절되지 않았다"
            )

            token, question = probe.get("token"), probe.get("question")
            if question is None:
                break

        # **0 이어야 한다.** 토큰이 노새의 판을 가리키므로 공격자 판은
        # 아예 안 건드려진다. `< total` 로 두면 9/10 을 맞혀도 통과한다.
        row = DailyStudy.objects.get(user=self.attacker)
        self.assertEqual(
            row.answered,
            0,
            f"남의 토큰이 공격자 판을 채웠다. answered={row.answered}/{total}",
        )
        self.assertEqual(row.correct, 0)
        self.assertEqual(row.score, 0)


class MidnightTest(TestCase):
    """자정을 넘긴 판. open_of 가 날짜가 아니라 '안 끝난 것' 으로 찾는다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("자정")

    def _open_yesterday(self) -> tuple[DailyStudy, str, dict]:
        """어제 시작해 아직 안 끝난 판을 만든다.

        판은 손대지 않는다 - 자정은 day 가 아니라 시계가 넘긴다. 부른
        쪽이 tomorrow() 로 감싸 "다음 날" 을 만든다.
        """
        return daily_study.start(self.user, StudyLength.SHORT)

    def test_a_study_started_yesterday_can_still_be_answered(self):
        """23:50 에 시작한 판이 자정에 죽으면 안 된다.

        날짜로 찾으면 토큰이 통째로 무효가 되고, 그 판은 열린 채 남아
        점수가 DailyScore 에 영영 안 닿는다.
        """
        study, token, question = self._open_yesterday()

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "자정을 넘기니 답이 안 쌓인다")

    def test_the_score_lands_on_the_day_it_started(self):
        """자정을 넘겨 끝내도 점수는 **시작한 날**에 붙는다.

        끝낸 날로 세면 어제 안 한 사람이 오늘 이틀치를 받는다.
        """
        study, token, question = self._open_yesterday()
        yesterday = study.day
        next_day = tomorrow()

        with mock.patch.object(calendar_kst, "today", next_day):
            while question is not None:
                picked = question["choices"][0]["id"]
                _, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertTrue(study.is_done)
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=yesterday).daily_study_score,
            study.score,
        )
        self.assertFalse(
            DailyScore.objects.filter(user=self.user, day=next_day())
            .exclude(daily_study_score=0)
            .exists(),
            "끝낸 날에도 점수가 붙어 이틀치가 됐다",
        )

    def test_yesterdays_open_study_does_not_block_todays_start(self):
        """어제 판이 열려 있어도 오늘은 새로 시작할 수 있다."""
        self._open_yesterday()
        next_day = tomorrow()

        with mock.patch.object(calendar_kst, "today", next_day):
            study, _, _ = daily_study.start(self.user, StudyLength.SHORT)

        self.assertEqual(study.day, next_day())
        self.assertEqual(DailyStudy.objects.filter(user=self.user).count(), 2)

    def test_starting_today_does_not_let_yesterdays_token_score_today(self):
        """어제 토큰으로 오늘 판을 채울 수 없다.

        **순번만으로는 못 막는다.** 오늘 판을 막 시작하면 순번이 0 이고
        어제 토큰의 순번도 0 이라 그대로 통과한다 - 어제 문제의 답이
        오늘 판에 세어진다. 어제 토큰을 저장해뒀다가 정답을 아는 문제로
        넣을 수 있다.

        토큰이 자기 판을 밝히는 것이 이걸 막는다. 게다가 오늘 시작할 때
        어제 판이 정산돼 닫히므로 그 토큰은 갈 곳이 없다.
        """
        _, old_token, _ = self._open_yesterday()

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            today_study, _, _ = daily_study.start(self.user, StudyLength.SHORT)

            with self.assertRaises(SessionError):
                daily_study.answer(self.user, old_token, _correct_id_of(old_token))

        today_study.refresh_from_db()
        self.assertEqual(today_study.answered, 0, "어제 토큰이 오늘 판을 채웠다")


class ApiEdgeTest(TestCase):
    """엔드포인트에 이상한 값을 넣는다. 400 이지 500 이 아니어야 한다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("api경계")
        self.client.force_login(self.user)

    def _start(self) -> dict:
        return self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()

    def test_a_guest_cannot_answer(self):
        """답하기도 로그인이 필요하다."""
        self.client.logout()

        res = self.client.post(
            ANSWER_URL,
            {"token": "x", "choice_id": 1},
            content_type="application/json",
        )

        self.assertIn(res.status_code, (401, 403))

    def test_a_bool_choice_id_is_refused(self):
        """True 는 int 의 하위형이라 1 로 통과할 수 있다."""
        data = self._start()

        res = self.client.post(
            ANSWER_URL,
            {"token": data["token"], "choice_id": True},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            DailyStudy.objects.get(user=self.user).answered, 0, "순번이 소비됐다"
        )

    def test_odd_choice_id_shapes_are_refused(self):
        """문자열·소수·null·리스트·거대한 수 어느 것도 500 을 내면 안 된다."""
        data = self._start()
        token = data["token"]

        for bad in ["1", 1.5, None, [1], {"id": 1}, "9" * 30]:
            with self.subTest(choice_id=bad):
                res = self.client.post(
                    ANSWER_URL,
                    {"token": token, "choice_id": bad},
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

        self.assertEqual(
            DailyStudy.objects.get(user=self.user).answered, 0, "순번이 소비됐다"
        )

    def test_a_negative_choice_id_is_graded_as_wrong_not_crashed(self):
        """음수 id 는 그냥 틀린 답이다. 골라둔 보기 중에 없기 때문이다."""
        data = self._start()

        res = self.client.post(
            ANSWER_URL,
            {"token": data["token"], "choice_id": -12345},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["result"]["correct"])

    def test_odd_token_shapes_are_refused(self):
        """토큰 자리에 이상한 값이 와도 400."""
        self._start()

        for bad in ["", None, 123, [], "not-a-token", "a.b.c"]:
            with self.subTest(token=bad):
                res = self.client.post(
                    ANSWER_URL,
                    {"token": bad, "choice_id": 1},
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

    def test_odd_length_shapes_are_refused(self):
        """길이 자리에 이상한 값이 와도 400 이고 줄이 안 생긴다."""
        for bad in [None, 5, "", "   ", ["5m"], "5M", "5m ", "x" * 200]:
            with self.subTest(length=bad):
                res = self.client.post(
                    START_URL, {"length": bad}, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

        self.assertFalse(
            DailyStudy.objects.filter(user=self.user).exists(), "줄이 생겼다"
        )

    def test_answering_before_starting_is_refused(self):
        """시작하지 않았는데 답하면 400."""
        res = self.client.post(
            ANSWER_URL,
            {"token": "whatever", "choice_id": 1},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 400)

    def test_the_get_shows_todays_row_after_starting(self):
        """시작한 뒤 GET 은 진행 중인 줄을 보여준다."""
        self._start()

        body = self.client.get(START_URL).json()

        self.assertIsNotNone(body["today"])
        self.assertFalse(body["today"]["done"])
        self.assertEqual(body["today"]["answered"], 0)

    def test_a_finished_row_stays_visible_on_the_get(self):
        """끝낸 뒤에도 GET 으로 결과를 본다. 시작은 막히지만 조회는 열린다."""
        data = self._start()
        token = data["token"]
        question = data["question"]

        while question is not None:
            picked = question["choices"][0]["id"]
            body = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": picked},
                content_type="application/json",
            ).json()
            token, question = body.get("token"), body.get("question")

        today = self.client.get(START_URL).json()["today"]

        self.assertTrue(today["done"])
        self.assertEqual(today["answered"], today["total"])


class StreakLinkTest(TestCase):
    """3-2 순위표와의 연결."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("꾸준함연결")

    def _run(self, length: str = StudyLength.SHORT) -> DailyStudy:
        _, token, question = daily_study.start(self.user, length)
        while question is not None:
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)
        return daily_study.today_of(self.user)

    def test_a_daily_study_only_day_counts_as_an_active_day(self):
        """자유 문제풀이를 한 판도 안 해도 일일공부만으로 활동일이 된다.

        활동일은 그날 총점이 0보다 큰지로 센다. 일일공부 점수를 안 보면
        매일 공부만 한 사람의 꾸준함이 0일로 나온다.
        """
        study = self._run()

        rows = leaderboards.build(leaderboards.STREAK).rows
        mine = [row for row in rows if row.display_name == self.user.display_name]

        self.assertEqual(len(mine), 1, "꾸준함 순위표에 안 들어갔다")
        self.assertEqual(mine[0].score, study.score, "점수가 다르다")
        self.assertEqual(mine[0].entries, 1, "활동일로 안 세어졌다")

    def test_the_python_total_and_the_sql_total_agree(self):
        """DailyScore.total 과 순위표 SQL 이 같은 값을 내야 한다.

        같은 식이 두 곳에 있어서 한쪽만 고치면 화면과 순위가 어긋난다.
        """
        self._run()

        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())
        rows = leaderboards.build(leaderboards.STREAK).rows
        mine = next(r for r in rows if r.display_name == self.user.display_name)

        self.assertEqual(mine.score, row.total)

    def test_the_streak_api_shows_a_daily_study_only_user(self):
        """API 로도 보인다. 화면이 읽는 경로다."""
        self._run()

        body = self.client.get(STREAK_URL).json()
        names = [row["display_name"] for row in body["rows"]]

        self.assertIn(self.user.display_name, names)


class _KeepsCacheTable:
    """TransactionTestCase 뒤에도 캐시 표가 남게 한다.

    **Postgres 에서만 드러난다.** TransactionTestCase 는 테스트가 끝날
    때 flush 를 부르고, flush 는 post_migrate 를 쏜다. 그 신호를 받은
    쪽이 throttle_cache 를 없앤다 - 이 표는 마이그레이션이 아니라
    createcachetable 로 만들어지므로 아무도 다시 만들지 않는다.

    그러면 뒤따르는 테스트가 setUp 의 cache.clear() 에서 통째로 죽는다.
    SQLite 에서는 안 났고 운영은 Postgres 라, 여기 맞춘다.

    **복구를 _fixture_teardown 에 건다.** 파괴가 테스트 메서드마다
    일어나므로 tearDownClass 로는 늦다 - 같은 클래스의 두 번째 테스트가
    이미 죽은 뒤다. accounts.ThrottleCacheTableTest 가 tearDown 에서
    같은 일을 하고 있어 단위를 그쪽에 맞췄다.
    """

    def _fixture_teardown(self):
        super()._fixture_teardown()
        # 이미 있으면 조용히 넘어간다.
        call_command("createcachetable", verbosity=0)


class ConcurrencyTest(_KeepsCacheTable, TransactionTestCase):
    """동시에 온 요청. 읽고 나서 쓰면 여기서 드러난다.

    TransactionTestCase 를 쓰는 이유: 스레드마다 다른 커넥션을 쓰는데
    TestCase 의 바깥 트랜잭션 안에서는 서로의 행이 안 보인다.
    """

    reset_sequences = True

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("동시성")

    @staticmethod
    def _run_together(func, args_list):
        """같은 순간에 여러 요청을 보낸다. 결과 목록을 순서대로 돌려준다."""
        results = [None] * len(args_list)
        barrier = threading.Barrier(len(args_list))

        def one(index, args):
            barrier.wait()
            try:
                results[index] = ("ok", func(*args))
            except Exception as exc:  # 무엇이 났는지 그대로 본다
                results[index] = ("err", exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=one, args=(i, args))
            for i, args in enumerate(args_list)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        return results

    def test_starting_twice_at_once_makes_one_row(self):
        """동시에 두 번 시작해도 줄은 하나다. 유일 제약이 막는다."""
        results = self._run_together(
            daily_study.start,
            [(self.user, StudyLength.SHORT), (self.user, StudyLength.LONG)],
        )

        ok = [r for r in results if r[0] == "ok"]
        errs = [r[1] for r in results if r[0] == "err"]

        self.assertEqual(len(ok), 1, f"둘 다 시작됐다: {results}")
        self.assertEqual(DailyStudy.objects.filter(user=self.user).count(), 1)
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs), f"500 이 났다: {errs}"
        )

    def test_all_four_choices_at_once_consume_only_one_step(self):
        """같은 토큰에 보기 넷을 한꺼번에 보내도 순번은 하나만 소비된다.

        읽고 나서 쓰면 넷이 전부 통과하고, 그중 하나는 반드시 맞는다 -
        정답을 몰라도 문제마다 +1 이 되어 만점이 확정된다.
        """
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)
        choice_ids = [c["id"] for c in question["choices"]]

        results = self._run_together(
            daily_study.answer, [(self.user, token, cid) for cid in choice_ids]
        )

        ok = [r for r in results if r[0] == "ok"]
        study = daily_study.today_of(self.user)

        self.assertEqual(len(ok), 1, f"여러 답이 통과했다: {results}")
        self.assertEqual(study.answered, 1, "순번이 여러 번 소비됐다")
        self.assertLessEqual(study.correct, 1, "맞은 것이 부풀었다")

    def test_the_same_token_sent_twice_at_once_counts_once(self):
        """같은 토큰·같은 답을 동시에 두 번 보내도 한 번만 센다."""
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)
        picked = question["choices"][0]["id"]

        self._run_together(
            daily_study.answer,
            [(self.user, token, picked), (self.user, token, picked)],
        )

        study = daily_study.today_of(self.user)
        self.assertEqual(study.answered, 1)
        self.assertLessEqual(study.score, 1)

    def test_two_answers_on_the_last_question_do_not_double_the_bonus(self):
        """마지막 문제에 두 답이 겹쳐도 문제 수를 넘지 않고 보너스는 한 번.

        answered 가 total 을 넘으면 그만큼 점수가 늘고, 닫기가 두 번 돌면
        보너스가 두 번 붙는다. 조건부 UPDATE 의 두 조건이 각각 막는다.
        """
        total, bonus = STUDY_PLANS[StudyLength.SHORT]
        _, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(total - 1):
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        self.assertIsNotNone(question, "마지막 문제 전에 끝났다")
        picked = question["choices"][0]["id"]

        self._run_together(
            daily_study.answer,
            [(self.user, token, picked), (self.user, token, picked)],
        )

        study = daily_study.today_of(self.user)
        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())

        self.assertEqual(study.answered, total, "문제 수를 넘겼다")
        self.assertTrue(study.is_done)
        self.assertEqual(study.score, study.correct + bonus, "보너스가 두 번 붙었다")
        self.assertEqual(row.daily_study_score, study.score, "그날 줄과 갈렸다")

    def test_the_daily_row_is_written_once_when_two_finish_at_once(self):
        """닫기가 동시에 두 번 불려도 그날 줄은 한 값만 갖는다.

        _finish 가 UPDATE 반환값을 안 보면 진 쪽도 add_daily_study 를 불러
        DailyScore 가 DailyStudy 와 다른 값을 갖는다.
        """
        total = STUDY_PLANS[StudyLength.SHORT][0]
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(total - 1):
            picked = question["choices"][0]["id"]
            _, token, question, _study = daily_study.answer(self.user, token, picked)

        picked = question["choices"][0]["id"]
        daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self._run_together(daily_study._finish, [(study,), (study,)])

        study.refresh_from_db()
        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())

        self.assertEqual(
            row.daily_study_score, study.score, "닫기가 두 번 돌아 값이 갈렸다"
        )


def days_ahead(n: int):
    """n 일 뒤로 간 시계.

    tomorrow() 와 같은 뜻이되 며칠이든 밀 수 있다. day 를 고치지 않고
    시계만 미는 이유는 tomorrow() 의 설명과 같다.
    """
    target = calendar_kst.today() + timedelta(days=n)
    return lambda: target


def answer_n(user, length, count: int):
    """count 문제만 풀고 나간다. (판, 그동안 얻은 점수).

    맞고 틀림이 무작위라 점수를 상수로 두면 안 된다. 실제로 받은
    점수를 세어 돌려준다.
    """
    study, token, question = daily_study.start(user, length)
    earned = 0
    for _ in range(count):
        picked = question["choices"][0]["id"]
        result, token, question, _s = daily_study.answer(user, token, picked)
        earned += result.score
    study.refresh_from_db()
    return study, earned


class SkippedDaysTest(TestCase):
    """며칠 안 들어온 사람. settle_stale 이 여기를 책임진다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("건너뜀")

    def test_a_three_day_old_open_study_settles_onto_its_own_day(self):
        """사흘 전 판을 오늘 정산해도 점수는 그날 줄에 붙는다.

        오늘 날짜로 붙으면 공부하지 않은 날에 꾸준함 점수가 생겨
        활동일이 부풀고 스트릭이 공짜로 이어진다.
        """
        study, earned = answer_n(self.user, StudyLength.SHORT, 3)
        started_day = study.day

        with mock.patch.object(calendar_kst, "today", days_ahead(3)):
            daily_study.settle_stale(self.user)
            today = calendar_kst.today()

        study.refresh_from_db()
        self.assertTrue(study.is_done, "사흘 전 판이 안 닫혔다")
        self.assertIsNone(
            DailyScore.objects.filter(user=self.user, day=today).first(),
            "사흘 전 점수가 오늘 날짜에 붙었다",
        )
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=started_day).daily_study_score,
            earned,
        )

    def test_every_stale_study_is_settled_not_just_the_latest(self):
        """열린 판이 여럿이면 전부 닫는다.

        "가장 최근 하나" 만 집으면 며칠 연속 열어두고 안 끝낸 사람의
        오래된 판이 영영 열린 채 남아 그날 점수가 순위표에 안 간다.
        """
        recent, _earned = answer_n(self.user, StudyLength.SHORT, 2)
        older = DailyStudy.objects.create(
            user=self.user,
            day=recent.day - timedelta(days=5),
            length=StudyLength.SHORT,
            total_questions=10,
            bonus=5,
            answered=3,
            correct=3,
            score=3,
            step=3,
        )

        with mock.patch.object(calendar_kst, "today", days_ahead(1)):
            daily_study.settle_stale(self.user)

        recent.refresh_from_db()
        older.refresh_from_db()
        self.assertTrue(recent.is_done, "최근 열린 판이 안 닫혔다")
        self.assertTrue(older.is_done, "더 오래된 열린 판이 안 닫혔다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=older.day).daily_study_score,
            3,
            "오래된 판 점수가 그날 줄에 안 갔다",
        )

    def test_settle_stale_is_idempotent(self):
        """여러 번 정산해도 점수가 늘지 않는다. GET 이 매번 부른다."""
        study, earned = answer_n(self.user, StudyLength.SHORT, 4)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            for _ in range(5):
                daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertEqual(study.score, earned, "정산을 반복하니 점수가 늘었다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            earned,
        )

    def test_settling_does_not_touch_another_users_open_study(self):
        """정산은 자기 판만 닫는다."""
        other = make_user("남의판")
        theirs, _earned = answer_n(other, StudyLength.SHORT, 2)
        answer_n(self.user, StudyLength.SHORT, 2)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)

        theirs.refresh_from_db()
        self.assertFalse(theirs.is_done, "남의 판이 닫혔다")

    def test_a_completed_but_unclosed_study_gets_its_bonus_on_settle(self):
        """다 풀고 자정만 넘긴 판은 정산 때 완주 보너스를 받는다."""
        total, bonus = STUDY_PLANS[StudyLength.SHORT]
        stuck = DailyStudy.objects.create(
            user=self.user,
            day=calendar_kst.today() - timedelta(days=1),
            length=StudyLength.SHORT,
            total_questions=total,
            bonus=bonus,
            answered=total,
            correct=total,
            score=total,
            step=total,
        )

        daily_study.settle_stale(self.user)

        stuck.refresh_from_db()
        self.assertTrue(stuck.is_done)
        self.assertEqual(stuck.score, total + bonus, "완주했는데 보너스가 없다")

    def test_only_one_open_study_can_exist_after_starting_today(self):
        """어제 판이 열린 채 오늘 시작해도 열린 판은 하나다."""
        answer_n(self.user, StudyLength.SHORT, 2)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.start(self.user, StudyLength.SHORT)
            open_count = DailyStudy.objects.filter(
                user=self.user, finished_at__isnull=True
            ).count()

        self.assertEqual(open_count, 1, "열린 판이 둘 이상이다")


class SettlingGetTest(TestCase):
    """GET 이 쓰기를 하게 됐다. 연타·게스트."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("겟연타")
        self.client.force_login(self.user)

    def test_repeated_get_does_not_republish_the_score(self):
        """GET 을 연타해도 어제 점수가 여러 번 발행되지 않는다."""
        study, earned = answer_n(self.user, StudyLength.SHORT, 4)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            for _ in range(10):
                self.assertEqual(self.client.get(START_URL).status_code, 200)

        study.refresh_from_db()
        self.assertEqual(study.score, earned, "점수가 부풀었다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            earned,
            "그날 줄이 부풀었다",
        )
        self.assertEqual(
            DailyScore.objects.filter(user=self.user).count(),
            1,
            "GET 이 오늘 날짜 줄까지 만들었다",
        )

    def test_get_after_settling_shows_no_today_row(self):
        """어제 판이 닫힌 뒤 GET 은 오늘 줄이 없다고 말한다.

        어제 판을 today 로 내려주면 화면이 이어서 풀기를 그리는데
        이어 풀 토큰이 없다 - 서버가 약속하지 않은 것을 화면이 약속한다.
        """
        answer_n(self.user, StudyLength.SHORT, 2)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            body = self.client.get(START_URL).json()

        self.assertIsNone(body["today"], "어제 판이 오늘로 보인다")

    def test_get_never_creates_a_study_row(self):
        """조회만 하는 GET 이 판을 만들어 하루를 태우면 안 된다."""
        for _ in range(5):
            self.assertEqual(self.client.get(START_URL).status_code, 200)
        self.assertEqual(DailyStudy.objects.count(), 0)

    def test_a_guest_cannot_trigger_the_settling_get(self):
        """쓰기를 하는 GET 이므로 로그인 없이는 못 부른다."""
        self.client.logout()
        self.assertIn(self.client.get(START_URL).status_code, (401, 403))


class ReviewGateTest(TestCase):
    """검수 안 된 콘텐츠가 문제로 새면 안 된다(CLAUDE.md 검수 규칙)."""

    def setUp(self):
        cache.clear()
        self.user = make_user("검수게이트")

    def test_only_unreviewed_words_are_not_enough_to_start(self):
        """검수 안 된 단어뿐이면 문제를 못 만들어 시작이 거절된다."""
        Word.objects.bulk_create(
            Word(
                term=f"u{i}",
                meaning=f"뜻{i}",
                description=f"설명{i} 입니다",
                is_reviewed=False,
            )
            for i in range(30)
        )
        with self.assertRaises(SessionError):
            daily_study.start(self.user, StudyLength.SHORT)
        self.assertEqual(DailyStudy.objects.count(), 0, "하루가 태워졌다")

    def test_unreviewed_words_never_appear_in_a_question(self):
        """검수 안 된 단어가 문제·보기 어디에도 안 나온다.

        한 판을 끝까지 돌며 문제·지문·보기 전부를 모아 확인한다.
        정답으로도 오답 보기로도 새면 안 된다.
        """
        seed_words(10)
        Word.objects.bulk_create(
            Word(
                term=f"secret{i}",
                meaning=f"비밀뜻{i}",
                description=f"숨긴설명{i} 입니다",
                is_reviewed=False,
            )
            for i in range(10)
        )
        hidden = list(
            Word.objects.filter(is_reviewed=False).values_list(
                "term", "meaning", "description"
            )
        )

        _study, token, question = daily_study.start(self.user, StudyLength.LONG)
        seen = []
        while question is not None:
            seen.append(str(question.get("question") or ""))
            seen.append(str(question.get("prompt") or ""))
            for choice in question["choices"]:
                seen.extend(str(value) for value in choice.values())
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        blob = "\n".join(seen)
        for term, meaning, description in hidden:
            self.assertNotIn(term, blob, f"검수 안 된 단어 {term} 이 노출됐다")
            self.assertNotIn(meaning, blob, f"검수 안 된 뜻 {meaning} 이 노출됐다")
            self.assertNotIn(description, blob, "검수 안 된 설명이 노출됐다")


class PlanCeilingTest(TestCase):
    """길이별 상한과 경계 순간."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("상한")

    def test_the_score_never_exceeds_the_plan_ceiling(self):
        """어떤 길이든 점수는 문제 수 + 보너스를 못 넘는다."""
        for length in StudyLength.values:
            with self.subTest(length=length):
                DailyStudy.objects.all().delete()
                DailyScore.objects.all().delete()
                total, bonus = STUDY_PLANS[length]

                study, token, question = daily_study.start(self.user, length)
                while question is not None:
                    picked = question["choices"][0]["id"]
                    _r, token, question, _s = daily_study.answer(
                        self.user, token, picked
                    )

                study.refresh_from_db()
                self.assertEqual(study.answered, total)
                self.assertLessEqual(study.score, total + bonus, "상한을 넘었다")

    def test_the_progress_counter_matches_the_answers_so_far(self):
        """문제마다 answered 가 정확히 지금까지 푼 개수여야 한다."""
        total, _bonus = STUDY_PLANS[StudyLength.SHORT]
        _study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for i in range(total):
            self.assertIsNotNone(question, f"{i}번째에서 문제가 끊겼다")
            self.assertEqual(question["answered"], i, "진행 표시가 어긋난다")
            self.assertEqual(question["total"], total)
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        self.assertIsNone(question, "마지막 문제 뒤에도 문제가 나온다")
        self.assertIsNone(token, "끝났는데 토큰이 나온다")


class CrossFeatureTokenTest(TestCase):
    """자유 문제풀이와 토큰이 섞이면 안 된다. 소금이 다르다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("토큰교차")
        self.client.force_login(self.user)

    def _daily_token(self) -> str:
        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )
        return res.json()["token"]

    def test_a_free_round_token_cannot_answer_a_daily_study(self):
        """자유 문제풀이 토큰으로 일일공부에 답할 수 없다."""
        from . import session

        free_token, _question = session.start()
        self._daily_token()

        res = self.client.post(
            ANSWER_URL,
            {"token": free_token, "choice_id": 1},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400, "다른 기능 토큰이 통과했다")
        self.assertEqual(DailyStudy.objects.get().answered, 0, "판이 진행됐다")

    def test_a_daily_token_cannot_answer_a_free_round(self):
        """반대 방향도 막혀야 한다."""
        token = self._daily_token()
        res = self.client.post(
            "/api/learning/rounds/answer/",
            {"token": token, "choice_id": 1},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400, "일일공부 토큰이 자유 판에 통과했다")

    def test_a_token_pointing_at_another_users_study_is_refused(self):
        """토큰 안의 sid 를 남의 판으로 바꿔치기해도 못 답한다."""
        victim = make_user("표적")
        theirs, _token, _question = daily_study.start(victim, StudyLength.SHORT)

        token = self._daily_token()
        state = signing.loads(
            token, salt=daily_study._SALT, max_age=daily_study.TOKEN_MAX_AGE
        )
        state["sid"] = theirs.pk
        forged = signing.dumps(state, salt=daily_study._SALT, compress=True)

        res = self.client.post(
            ANSWER_URL,
            {"token": forged, "choice_id": 1},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400, "남의 판에 답했다")
        theirs.refresh_from_db()
        self.assertEqual(theirs.answered, 0, "남의 판이 진행됐다")


class OddBodyTest(TestCase):
    """이상한 입력. 400 이어야지 500 이면 안 된다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("이상입력2")
        self.client.force_login(self.user)

    def _token(self) -> str:
        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        )
        return res.json()["token"]

    def test_huge_and_odd_choice_ids_are_refused_or_graded_wrong(self):
        """거대한 수·음수를 보내도 500 이 아니고 정답도 아니다."""
        for picked in [-1, 0, -(10**18), 10**18, int("9" * 30)]:
            with self.subTest(picked=picked):
                DailyStudy.objects.all().delete()
                DailyScore.objects.all().delete()
                token = self._token()
                res = self.client.post(
                    ANSWER_URL,
                    {"token": token, "choice_id": picked},
                    content_type="application/json",
                )
                self.assertIn(
                    res.status_code, (200, 400), f"500 이 났다: {res.content}"
                )
                if res.status_code == 200:
                    self.assertFalse(
                        res.json()["result"]["correct"], "없는 보기가 정답이 됐다"
                    )

    def test_odd_length_values_are_refused(self):
        """공백·대소문자·전각·아주 긴 문자열·타입 불일치를 다 거절한다."""
        odd = [
            "5m ",
            " 5m",
            "5M",
            "",
            " ",
            "1h",
            "5m" * 500,
            "５m",
            None,
            5,
            [],
            {},
            True,
        ]
        for length in odd:
            with self.subTest(length=length):
                res = self.client.post(
                    START_URL, {"length": length}, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400, f"{length!r} 이 통과했다")
                self.assertEqual(DailyStudy.objects.count(), 0, "하루가 태워졌다")

    def test_a_json_body_that_is_not_an_object_is_refused(self):
        """본문이 객체가 아니어도 500 이 아니다."""
        for body in ["[]", '"x"', "5", "null"]:
            with self.subTest(body=body):
                res = self.client.post(
                    START_URL, body, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400, f"{body} 가 통과했다")

    def test_a_missing_choice_id_is_refused(self):
        token = self._token()
        res = self.client.post(
            ANSWER_URL, {"token": token}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)


class NormalUseThrottleTest(TestCase):
    """방어 장치가 정상 사용을 막으면 안 된다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("스로틀")
        self.client.force_login(self.user)

    def test_a_full_long_run_over_the_api_is_not_throttled(self):
        """40문제짜리를 빠르게 풀어도 429 가 나면 안 된다.

        하루 한 번이라 중간에 막히면 다시 시작할 수도 없다.
        """
        res = self.client.post(
            START_URL, {"length": StudyLength.LONG}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 201)
        token, question = res.json()["token"], res.json()["question"]

        calls = 1
        while question is not None:
            picked = question["choices"][0]["id"]
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": picked},
                content_type="application/json",
            )
            calls += 1
            self.assertNotEqual(res.status_code, 429, f"{calls}번째 요청이 막혔다")
            self.assertEqual(res.status_code, 200, res.content)
            token, question = res.json()["token"], res.json()["question"]

        self.assertEqual(calls, STUDY_PLANS[StudyLength.LONG][0] + 1)

    def test_answering_has_its_own_bucket_apart_from_starting(self):
        """답하기와 조회·시작이 통을 나눠 쓴다.

        한 통이면 빠르게 푸는 사람이 조회 요청까지 같은 통에서 태워
        판 중간에 갇힌다. 한도는 하루 총량이 아니라 1분 창이다.
        """
        from .throttles import DailyStudyAnswerThrottle, DailyStudyThrottle

        self.assertNotEqual(
            DailyStudyThrottle.scope,
            DailyStudyAnswerThrottle.scope,
            "답하기가 시작과 통을 나눠 쓰지 않는다",
        )


class SettlingConcurrencyTest(_KeepsCacheTable, TransactionTestCase):
    """정산이 동시에 일어날 때. GET 이 정산을 부르므로 실제로 겹친다."""

    reset_sequences = True

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("정산동시")

    @staticmethod
    def _run_together(func, args_list):
        """같은 순간에 여러 요청을 보낸다. ConcurrencyTest 와 같은 방식."""
        results = [None] * len(args_list)
        barrier = threading.Barrier(len(args_list))

        def one(index, args):
            barrier.wait()
            try:
                results[index] = ("ok", func(*args))
            except Exception as exc:
                results[index] = ("err", exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=one, args=(i, args))
            for i, args in enumerate(args_list)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def test_concurrent_settle_publishes_the_score_once(self):
        """동시에 정산해도 점수가 두 번 발행되지 않는다."""
        study, earned = answer_n(self.user, StudyLength.SHORT, 4)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            results = self._run_together(daily_study.settle_stale, [(self.user,)] * 4)

        errs = [r[1] for r in results if r[0] == "err"]
        self.assertFalse(errs, f"정산이 터졌다: {errs}")

        study.refresh_from_db()
        self.assertEqual(study.score, earned, "점수가 두 번 붙었다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            earned,
        )

    def test_concurrent_start_after_a_stale_study_still_makes_one_row(self):
        """어제 판이 열린 채 동시에 두 번 시작해도 오늘 줄은 하나다."""
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            results = self._run_together(
                daily_study.start,
                [(self.user, StudyLength.SHORT), (self.user, StudyLength.LONG)],
            )
            today = calendar_kst.today()

        ok = [r for r in results if r[0] == "ok"]
        errs = [r[1] for r in results if r[0] == "err"]
        self.assertEqual(len(ok), 1, f"둘 다 시작됐다: {results}")
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs), f"500 이 났다: {errs}"
        )
        self.assertEqual(
            DailyStudy.objects.filter(user=self.user, day=today).count(), 1
        )
        study.refresh_from_db()
        self.assertTrue(study.is_done, "어제 판이 안 닫혔다")

    def test_a_settle_racing_an_answer_does_not_double_the_score(self):
        """정산과 답하기가 같은 순간에 와도 점수가 갈리지 않는다.

        자정 직후 한 탭은 답을 보내고 다른 탭은 화면을 새로고침한다.
        """
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        picked = question["choices"][0]["id"]

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            results = self._run_together(
                lambda fn, *args: fn(*args),
                [
                    (daily_study.settle_stale, self.user),
                    (daily_study.answer, self.user, token, picked),
                ],
            )

        errs = [r[1] for r in results if r[0] == "err"]
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs), f"500 이 났다: {errs}"
        )

        study.refresh_from_db()
        self.assertLessEqual(study.answered, 1)
        self.assertLessEqual(study.score, study.answered + study.bonus)
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            study.score,
            "그날 줄과 판의 점수가 갈렸다",
        )

class ThinContentTest(TestCase):
    """콘텐츠가 적을 때 약속을 지키는가."""

    def setUp(self):
        cache.clear()
        self.user = make_user("빈창고")

    def test_the_promise_shrinks_to_what_can_be_asked(self):
        """낼 수 있는 것보다 많이 약속하지 않는다.

        출제가 최근 낸 정답을 후보에서 빼므로(RECENT_KEEP=40), 단어가
        30개면 30문제째에 후보가 바닥난다. 상한이 없으면 40문제를
        약속해놓고 30문제에서 조용히 끝나 - 사용자는 이유를 모른다.

        보너스는 줄이지 않는다. 콘텐츠가 적은 것은 사용자 잘못이 아니다.
        """
        seed_words(count=30)
        total, bonus = STUDY_PLANS[StudyLength.LONG]

        study, token, question = daily_study.start(self.user, StudyLength.LONG)

        self.assertLess(study.total_questions, total, "상한이 안 걸렸다")
        self.assertEqual(study.total_questions, 30)
        self.assertEqual(study.bonus, bonus, "보너스까지 깎였다")

        while question is not None:
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "약속한 만큼 풀었는데 안 끝났다")
        self.assertEqual(
            study.answered, study.total_questions, "약속한 수를 다 못 냈다"
        )
        self.assertEqual(
            study.score, study.correct + bonus, "완주했는데 보너스가 없다"
        )

    def test_a_full_pool_keeps_the_full_promise(self):
        """콘텐츠가 넉넉하면 약속이 그대로다."""
        seed_words(count=120)
        total, _bonus = STUDY_PLANS[StudyLength.LONG]

        study, _, _ = daily_study.start(self.user, StudyLength.LONG)

        self.assertEqual(study.total_questions, total)


# ---------------------------------------------------------------------------
# 재개(resume) - 하다 만 판을 이어 푸는 길.
# ---------------------------------------------------------------------------


class ResumeTest(TestCase):
    """중간에 나갔다 돌아온 사람.

    이 기능이 없으면 25문제짜리를 3문제 풀고 나간 사람은 오늘 판을 영영
    못 끝낸다 - 답하려면 토큰이 필요한데 시작은 하루 한 번 제약에 막힌다.
    열어준 만큼 새는 곳이 없는지를 본다.
    """

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("재개")

    def test_resume_continues_the_same_row_without_resetting_progress(self):
        """이어 풀어도 진행이 처음부터 다시 세어지지 않는다.

        재개가 새 판을 만들거나 순번을 되감으면 여기서 드러난다.
        """
        study, earned = answer_n(self.user, StudyLength.SHORT, 3)

        resumed = daily_study.resume(study)
        self.assertIsNotNone(resumed, "하다 만 판인데 이어 풀 수 없다")
        token, question = resumed

        self.assertEqual(question["answered"], 3, "진행이 되감겼다")
        self.assertEqual(
            DailyStudy.objects.filter(user=self.user).count(), 1, "판이 새로 생겼다"
        )

        result, _, _, _ = daily_study.answer(
            self.user, token, question["choices"][0]["id"]
        )

        study.refresh_from_db()
        self.assertEqual(study.answered, 4, "이어 푼 답이 안 세어졌다")
        self.assertEqual(study.score, earned + result.score, "점수가 어긋났다")

    def test_a_resumed_study_can_be_finished_and_still_gets_the_bonus(self):
        """중간에 나간 사람이 이어 풀어 완주하면 보너스를 받는다.

        이 기능을 만든 이유 그 자체다 - 25문제짜리를 3문제 풀고 나가면
        완주 보너스를 영영 못 받는 것이 원래 문제였다.
        """
        total, bonus = STUDY_PLANS[StudyLength.SHORT]
        study, _earned = answer_n(self.user, StudyLength.SHORT, 2)

        token, question = daily_study.resume(study)
        while question is not None:
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "이어 풀어 다 채웠는데 안 끝났다")
        self.assertEqual(study.answered, total)
        self.assertEqual(study.score, study.correct + bonus, "완주 보너스가 없다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            study.score,
            "점수판이 판과 다르다",
        )

    def test_resume_on_a_finished_study_is_none(self):
        """끝난 판은 이어 풀 수 없다. 안 막으면 하루 한 번이 무너진다."""
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)
        while question is not None:
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        self.assertIsNone(daily_study.resume(study), "끝난 판에 토큰이 나왔다")

    def test_a_resume_token_does_not_replay_an_already_used_step(self):
        """재개 토큰을 받아두고 한 문제 푼 뒤 그 토큰을 쓰면 거절한다.

        재개가 순번 방어를 우회하는지 보는 핵심 테스트다. 토큰의 순번은
        DB 의 step 에서 읽으므로, 받아둔 사이에 순번이 지나가면 안 맞는다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        stale_token, stale_question = daily_study.resume(study)

        # 받아둔 토큰을 쓰기 전에 다른 토큰으로 한 문제를 푼다.
        fresh_token, fresh_question = daily_study.resume(study)
        daily_study.answer(self.user, fresh_token, fresh_question["choices"][0]["id"])

        with self.assertRaises(SessionError):
            daily_study.answer(
                self.user, stale_token, stale_question["choices"][0]["id"]
            )

        study.refresh_from_db()
        self.assertEqual(study.answered, 2, "되돌린 답이 세어졌다")

    def test_two_resume_tokens_only_one_can_be_spent(self):
        """재개 토큰을 두 번 받아 각각으로 답하면 하나만 통과한다.

        둘 다 같은 순번을 담으므로 첫 번째가 그 순번을 가져가면 두 번째는
        조건이 안 맞는다. 안 막으면 재개를 반복해 문제 하나로 여러 번
        +1 을 만들 수 있다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        token_a, question_a = daily_study.resume(study)
        token_b, question_b = daily_study.resume(study)

        daily_study.answer(self.user, token_a, question_a["choices"][0]["id"])

        with self.assertRaises(SessionError):
            daily_study.answer(self.user, token_b, question_b["choices"][0]["id"])

        study.refresh_from_db()
        self.assertEqual(study.answered, 2, "재개 토큰 둘이 다 세어졌다")

    def test_resume_cannot_be_farmed_past_the_promised_count(self):
        """문제가 마음에 안 들 때마다 새로 받아도 기회가 늘지 않는다.

        재개는 새 문제를 주므로 "마음에 안 드는 문제 버리고 다시 받기" 가
        열린다. 그래도 순번이 하나씩만 소비되므로 답할 수 있는 횟수는
        약속한 문제 수 그대로여야 한다.
        """
        total, _bonus = STUDY_PLANS[StudyLength.SHORT]
        daily_study.start(self.user, StudyLength.SHORT)

        spent = 0
        for _ in range(total * 3):
            study = DailyStudy.objects.get(user=self.user)
            resumed = daily_study.resume(study)
            if resumed is None:
                break
            token, question = resumed
            try:
                daily_study.answer(self.user, token, question["choices"][0]["id"])
                spent += 1
            except SessionError:
                break

        study = DailyStudy.objects.get(user=self.user)
        self.assertEqual(spent, total, "약속한 수보다 많이 답했다")
        self.assertEqual(study.answered, total, "약속한 수와 다르게 세어졌다")
        self.assertLessEqual(study.correct, total, "맞힌 수가 문제 수를 넘었다")

    def test_a_resume_token_cannot_be_spent_by_another_account(self):
        """재개 토큰을 남에게 줘도 그 계정은 못 쓴다.

        토큰에는 판 pk 만 있고 누구 것인지가 없다. _study_of_token 이
        user 를 함께 걸지 않으면 남의 판에 답이 들어간다.
        """
        other = make_user("남")
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        token, question = daily_study.resume(study)

        with self.assertRaises(SessionError):
            daily_study.answer(other, token, question["choices"][0]["id"])

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "남이 내 판을 채웠다")

    def test_resume_never_hands_out_unreviewed_content(self):
        """검수 안 된 단어는 이어 풀 문제에 안 나온다.

        저장된 문제가 없어 새로 뽑는 경로(이 칸이 생기기 전에 시작한 판)를
        재현한다. 그쪽이 visible() 을 안 거치면 검수 전 단어가 샌다 -
        CLAUDE.md 의 검수 규칙이 걸리는 자리다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        # 저장된 문제를 지워 "새로 뽑는" 경로로 보낸다.
        DailyStudy.objects.filter(pk=study.pk).update(question=None)
        study.refresh_from_db()

        Word.objects.update(is_reviewed=False)
        secret_term = f"{uuid4().hex[:6]}secret"
        Word.objects.create(
            term=secret_term,
            meaning="검수 안 된 뜻",
            description="검수 안 된 설명 입니다",
            is_reviewed=False,
        )

        self.assertIsNone(
            daily_study.resume(study), "검수 안 된 단어로 문제를 만들어줬다"
        )

    def test_resume_does_not_reveal_unreviewed_words_in_the_saved_question(self):
        """저장해둔 문제를 다시 낼 때도 검수 전 단어가 보기에 안 섞인다.

        저장은 발급 시점의 보기를 그대로 들고 있으므로, 그때 검수됐던
        것만 들어 있어야 한다. 뒤늦게 만든 검수 전 단어가 끼어들면 샌다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        secret_term = f"{uuid4().hex[:6]}secret"
        secret = Word.objects.create(
            term=secret_term,
            meaning="검수 안 된 뜻",
            description="검수 안 된 설명 입니다",
            is_reviewed=False,
        )

        _token, question = daily_study.resume(study)

        shown = [c["text"] for c in question["choices"]]
        self.assertNotIn(secret_term, shown, "검수 안 된 단어가 보기에 나왔다")
        self.assertNotIn(
            secret.pk, [c["id"] for c in question["choices"]], "검수 안 된 id 가 나왔다"
        )

    def test_the_saved_question_moves_on_after_it_is_answered(self):
        """답한 뒤 다시 열면 다음 문제다. 푼 문제가 다시 나오지 않는다.

        저장된 문제를 답한 뒤에도 그대로 두면, 이어 풀기가 이미 답한
        문제를 계속 내놓아 판이 앞으로 못 간다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        before = daily_study.resume(study)[1]
        token = daily_study.resume(study)[0]

        daily_study.answer(self.user, token, before["choices"][0]["id"])

        study.refresh_from_db()
        after = daily_study.resume(study)[1]

        self.assertEqual(after["answered"], 2, "진행이 안 올라갔다")
        self.assertNotEqual(
            [c["id"] for c in after["choices"]],
            [c["id"] for c in before["choices"]],
            "답한 문제가 또 나왔다",
        )

    def test_resume_replays_the_saved_question_instead_of_rerolling(self):
        """이어 풀 때 문제가 매번 바뀌지 않는다.

        새로 뽑아주면 순번을 소비하지 않고 문제만 갈아탈 수 있다 - 아는
        것이 나올 때까지 화면을 다시 열면 되므로 사실상 만점이다.
        _take_step 은 "한 순번은 한 번만 소비된다" 만 지키지 이것까지
        막지 못하므로, 발급한 문제를 저장해두고 그대로 다시 내려준다.
        """
        study, _earned = answer_n(self.user, StudyLength.SHORT, 1)

        first = daily_study.resume(study)[1]
        seen = set()
        for _ in range(8):
            again = daily_study.resume(study)[1]
            seen.add(again["prompt"])
            self.assertEqual(
                [c["id"] for c in again["choices"]],
                [c["id"] for c in first["choices"]],
                "이어 풀 때마다 보기가 바뀐다",
            )

        self.assertEqual(len(seen), 1, f"문제를 갈아탈 수 있다: {seen}")

    def test_resume_does_not_publish_score_twice(self):
        """이어 풀 토큰을 여러 번 받아도 점수판이 부풀지 않는다.

        resume 이 _publish 나 _finish 를 건드리면 여기서 드러난다.
        """
        study, earned = answer_n(self.user, StudyLength.SHORT, 3)

        for _ in range(5):
            daily_study.resume(study)

        study.refresh_from_db()
        self.assertEqual(study.score, earned, "점수가 부풀었다")
        self.assertEqual(
            DailyScore.objects.get(user=self.user, day=study.day).daily_study_score,
            earned,
            "점수판이 부풀었다",
        )
        self.assertEqual(
            DailyScore.objects.filter(user=self.user).count(), 1, "점수 줄이 늘었다"
        )

    def test_resuming_a_settled_study_hands_nothing(self):
        """자정을 넘겨 정산된 판은 재개되지 않는다."""
        study, _earned = answer_n(self.user, StudyLength.SHORT, 2)

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            daily_study.settle_stale(self.user)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "정산됐는데 안 닫혔다")
        self.assertIsNone(daily_study.resume(study), "닫힌 판이 재개됐다")


class ResumeApiTest(TestCase):
    """재개를 HTTP 경로로. GET 이 토큰을 내려주는 계약을 본다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("재개api")
        self.client.force_login(self.user)

    def _start(self) -> dict:
        return self.client.post(
            START_URL, {"length": StudyLength.SHORT}, content_type="application/json"
        ).json()

    def _answer(self, client, token, choice_id):
        return client.post(
            ANSWER_URL,
            {"token": token, "choice_id": choice_id},
            content_type="application/json",
        )

    def test_a_guest_gets_no_resume_token(self):
        """게스트에게는 조회 자체가 막힌다. 토큰이 샐 자리가 없다."""
        self.client.logout()

        res = self.client.get(START_URL)

        self.assertIn(res.status_code, (401, 403))

    def test_the_get_hands_a_usable_token_when_a_study_is_in_progress(self):
        """하다 만 판이 있으면 GET 이 이어 풀 토큰과 문제를 함께 준다."""
        data = self._start()
        self._answer(
            self.client, data["token"], data["question"]["choices"][0]["id"]
        )

        body = self.client.get(START_URL).json()

        self.assertIsNotNone(body["token"], "이어 풀 토큰이 없다")
        self.assertIsNotNone(body["question"], "이어 풀 문제가 없다")
        self.assertEqual(body["question"]["answered"], 1, "진행이 안 이어졌다")

        res = self._answer(
            self.client, body["token"], body["question"]["choices"][0]["id"]
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["study"]["answered"], 2)

    def test_the_get_hands_no_token_before_starting(self):
        """시작 전에는 토큰이 없다. 있으면 시작 없이 푸는 길이 열린다."""
        body = self.client.get(START_URL).json()

        self.assertIsNone(body["today"])
        self.assertIsNone(body["token"], "시작도 안 했는데 토큰이 나왔다")
        self.assertIsNone(body["question"])

    def test_the_get_hands_no_token_after_finishing(self):
        """끝낸 뒤에는 토큰이 없다. 있으면 하루 한 번을 넘어 계속 푼다."""
        data = self._start()
        token, question = data["token"], data["question"]
        while question is not None:
            body = self._answer(
                self.client, token, question["choices"][0]["id"]
            ).json()
            token, question = body.get("token"), body.get("question")

        body = self.client.get(START_URL).json()

        self.assertTrue(body["today"]["done"])
        self.assertIsNone(body["token"], "끝난 판에 토큰이 나왔다")
        self.assertIsNone(body["question"])

    def test_another_account_cannot_resume_my_study(self):
        """남의 계정으로 조회하면 내 판의 토큰이 안 나온다."""
        self._start()

        stranger = self.client_class()
        stranger.force_login(make_user("남api"))

        body = stranger.get(START_URL).json()

        self.assertIsNone(body["today"], "남의 판이 보인다")
        self.assertIsNone(body["token"], "남의 판 토큰이 나왔다")

    def test_a_resume_token_from_yesterday_cannot_fill_todays_study(self):
        """어제 받아둔 재개 토큰으로 오늘 판을 채울 수 없다.

        자정을 넘기면 어제 판은 정산되어 닫힌다. 그 전에 받아둔 토큰은
        닫힌 판을 가리키므로 거절되어야 한다 - 오늘 판으로 흘러들면
        하루 한 번이 무너진다.
        """
        data = self._start()
        self._answer(
            self.client, data["token"], data["question"]["choices"][0]["id"]
        )

        stale = self.client.get(START_URL).json()
        stale_token = stale["token"]
        stale_choice = stale["question"]["choices"][0]["id"]

        with mock.patch.object(calendar_kst, "today", tomorrow()):
            # 자정을 넘겨 조회하면 어제 판이 정산되고 오늘 판은 아직 없다.
            body = self.client.get(START_URL).json()
            self.assertIsNone(body["today"], "어제 판이 오늘로 보인다")
            self.assertIsNone(body["token"], "정산된 판의 토큰이 나왔다")

            self._start()

            res = self._answer(self.client, stale_token, stale_choice)

            self.assertEqual(res.status_code, 400, "어제 토큰이 통과했다")

            today_study = DailyStudy.objects.get(
                user=self.user, day=calendar_kst.today()
            )
            self.assertEqual(today_study.answered, 0, "어제 토큰이 오늘 판을 채웠다")

    def test_repeated_gets_do_not_inflate_progress(self):
        """조회를 여러 번 해도 진행이 늘지 않는다.

        GET 이 문제를 만들므로 조회가 상태를 바꾸면 여기서 드러난다.
        """
        data = self._start()
        self._answer(
            self.client, data["token"], data["question"]["choices"][0]["id"]
        )

        for _ in range(6):
            res = self.client.get(START_URL)
            self.assertEqual(res.status_code, 200, res.content)

        study = DailyStudy.objects.get(user=self.user)
        self.assertEqual(study.answered, 1, "조회가 진행을 늘렸다")
        self.assertEqual(study.step, 1, "조회가 순번을 소비했다")

    def test_the_get_survives_when_content_ran_out(self):
        """콘텐츠가 사라져도 조회는 200 이다. 500 이면 화면을 못 연다."""
        data = self._start()
        self._answer(
            self.client, data["token"], data["question"]["choices"][0]["id"]
        )

        # 저장된 문제까지 지워 새로 뽑아야 하는 상태로 만든다.
        DailyStudy.objects.filter(user=self.user).update(question=None)
        Word.objects.all().delete()

        res = self.client.get(START_URL)

        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIsNotNone(body["today"], "진행 중인 줄이 사라졌다")
        self.assertIsNone(body["token"], "낼 문제가 없는데 토큰이 나왔다")
        self.assertIsNone(body["question"])


class ResumeConcurrencyTest(_KeepsCacheTable, TransactionTestCase):
    """재개 토큰을 동시에 쓰는 경우. 읽고 나서 쓰면 여기서 드러난다."""

    reset_sequences = True

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("재개동시")

    @staticmethod
    def _run_together(func, args_list):
        """같은 순간에 여러 요청을 보낸다. ConcurrencyTest 와 같은 방식."""
        results = [None] * len(args_list)
        barrier = threading.Barrier(len(args_list))

        def one(index, args):
            barrier.wait()
            try:
                results[index] = ("ok", func(*args))
            except Exception as exc:
                results[index] = ("err", exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=one, args=(i, args))
            for i, args in enumerate(args_list)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return results

    def test_four_resume_tokens_sent_at_once_consume_one_step(self):
        """재개 토큰 넷을 한꺼번에 보내도 순번은 하나만 소비된다.

        각 토큰이 다른 문제를 담으므로 넷 다 통과하면 정답을 몰라도
        하나는 맞는다 - 문제 하나에 네 번의 기회가 생긴다.
        """
        study, _token, _question = daily_study.start(self.user, StudyLength.SHORT)

        tokens = [daily_study.resume(study) for _ in range(4)]
        args = [
            (self.user, token, question["choices"][0]["id"])
            for token, question in tokens
        ]

        results = self._run_together(daily_study.answer, args)

        ok = [r for r in results if r[0] == "ok"]
        errs = [r[1] for r in results if r[0] == "err"]

        self.assertEqual(len(ok), 1, f"둘 이상이 통과했다: {results}")
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs), f"500 이 났다: {errs}"
        )

        study.refresh_from_db()
        self.assertEqual(study.answered, 1, "한 문제에 여러 답이 세어졌다")
        self.assertLessEqual(study.correct, 1, "한 문제로 여러 번 맞혔다")

    def test_concurrent_resume_does_not_change_the_row(self):
        """동시에 재개해도 판이 늘거나 순번이 소비되지 않는다."""
        study, _token, _question = daily_study.start(self.user, StudyLength.SHORT)

        results = self._run_together(daily_study.resume, [(study,)] * 4)

        errs = [r[1] for r in results if r[0] == "err"]
        self.assertFalse(errs, f"재개가 터졌다: {errs}")
        self.assertEqual(
            DailyStudy.objects.filter(user=self.user).count(), 1, "판이 늘었다"
        )

        study.refresh_from_db()
        self.assertEqual(study.answered, 0, "재개가 진행을 늘렸다")
        self.assertEqual(study.step, 0, "재개가 순번을 소비했다")

    def test_resuming_while_the_last_answer_lands_cannot_overfill(self):
        """마지막 답과 재개한 답이 겹쳐도 약속한 수를 넘지 않는다."""
        total, _bonus = STUDY_PLANS[StudyLength.SHORT]
        study, token, question = daily_study.start(self.user, StudyLength.SHORT)

        for _ in range(total - 1):
            picked = question["choices"][0]["id"]
            _r, token, question, _s = daily_study.answer(self.user, token, picked)

        study.refresh_from_db()
        spare_token, spare_question = daily_study.resume(study)

        results = self._run_together(
            daily_study.answer,
            [
                (self.user, token, question["choices"][0]["id"]),
                (self.user, spare_token, spare_question["choices"][0]["id"]),
            ],
        )

        errs = [r[1] for r in results if r[0] == "err"]
        self.assertTrue(
            all(isinstance(e, SessionError) for e in errs), f"500 이 났다: {errs}"
        )

        study.refresh_from_db()
        self.assertEqual(study.answered, total, "약속한 수를 넘겼다")
        self.assertTrue(study.is_done)
