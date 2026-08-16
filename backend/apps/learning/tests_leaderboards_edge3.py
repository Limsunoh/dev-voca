"""순위표 4차 - user_id 를 is_me 로 바꾼 뒤 생긴 자리.

앞의 세 파일은 **등수와 정렬**을 본다. 여기는 "이 줄이 나인가" 라는
새 표시 하나만 판다. 지키려는 것은 둘이다.

    1. 표시가 정확한가 - 로그인한 사람에게 정확히 한 줄, 게스트에게 0 줄
    2. pk 가 정말 안 나가는가 - 키 이름뿐 아니라 **값으로도**

둘째가 특히 놓치기 쉽다. `assertNotIn("user_id", row)` 는 키만 본다.
pk 를 다른 이름으로 담거나 rank/score 자리에 섞어 내보내도 통과한다.
가입자 수를 숨기려고 한 변경이므로 **본문 어디에도 그 숫자가 없어야**
의미가 있다.

셋째로, 표시는 요청마다 새로 붙어야 한다. A 가 본 응답을 B 가 그대로
받으면 B 의 화면에 A 의 줄이 강조된다 - 순위표는 로그인 없이도 보이는
캐시하기 좋은 화면이라 실수하기 쉬운 자리다.
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

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
BOARD_URLS = (WEEKLY_URL, ALL_TIME_URL, STREAK_URL)

# 화면이 그리는 한 줄의 전부. 늘어나면 프론트 계약이 바뀐 것이고,
# pk 가 새로 끼어들었을 수도 있다.
ROW_FIELDS = {"rank", "display_name", "avatar", "score", "entries", "is_me"}

PASSWORD = secrets.token_urlsafe(16)


def make_user(name: str) -> User:
    return User.objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def bulk_users(prefix: str, count: int) -> list:
    """목록을 채울 사람들. 표시가 붙으면 안 되는 배경이라 로그인은 안 한다."""
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


def record_everywhere(user, score: int) -> None:
    """세 순위표 모두에 한 줄이 생기게 한다.

    최고점 2종은 판을, 꾸준함은 하루 줄을 읽는다. 한쪽만 넣으면 순위표
    셋 중 하나에서만 검사가 성립해 나머지 둘은 빈 목록을 통과시킨다.
    """
    finish_round(user, score)
    daily(user, calendar_kst.today(), best=score)


class IsMeMarkTest(TestCase):
    """표시가 정확히 한 줄에만 붙는가."""

    def setUp(self):
        cache.clear()

    def test_a_guest_sees_no_marked_row_anywhere(self):
        """게스트에게는 표시가 하나도 없어야 한다.

        빈 순위표로 확인하면 안 된다 - 줄이 없어서 표시가 없는 것과
        게스트라서 없는 것이 구분되지 않는다. 여러 줄을 채워두고 본다.
        """
        for i, name in enumerate(("갑", "을", "병", "정")):
            record_everywhere(make_user(name), 40 - i)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertEqual(len(body["rows"]), 4, "남의 줄이 안 보인다")
                self.assertEqual(
                    [row["is_me"] for row in body["rows"]],
                    [False] * 4,
                    "게스트인데 내 줄이 있다고 한다",
                )
                self.assertIsNone(body["me"], "게스트에게 내 줄이 나갔다")

    def test_exactly_one_row_is_marked_inside_the_top(self):
        """목록 안에 있으면 딱 한 줄에만 표시가 붙는다."""
        others = [make_user(f"안쪽남{i}") for i in range(4)]
        for i, other in enumerate(others):
            record_everywhere(other, 50 - i)

        me = make_user("안쪽나")
        record_everywhere(me, 25)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()
                marked = [row for row in body["rows"] if row["is_me"]]

                self.assertEqual(len(marked), 1, "표시가 하나가 아니다")
                self.assertEqual(marked[0]["display_name"], "안쪽나")
                self.assertEqual(marked[0]["score"], 25, "남의 줄에 표시가 붙었다")
                self.assertIsNone(body["me"], "목록 안인데 내 줄이 또 나왔다")

    def test_outside_the_top_only_the_me_row_is_marked(self):
        """목록 밖이면 me 만 표시가 붙고 rows 에는 하나도 없다.

        rows 에까지 붙으면 화면이 남의 줄을 내 줄로 강조한다. 목록에 내가
        없다는 판정(_me_outside_top)도 같은 표시를 보고 하므로, 여기가
        틀리면 내 줄이 아예 안 나오거나 두 번 나온다.
        """
        for i, user in enumerate(bulk_users("밖채우기_", 22)):
            record_everywhere(user, 200 - i)

        me = make_user("밖의나")
        record_everywhere(me, 1)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertEqual(len(body["rows"]), leaderboards.TOP_SIZE)
                self.assertEqual(
                    [row["is_me"] for row in body["rows"]],
                    [False] * leaderboards.TOP_SIZE,
                    "목록 밖인데 목록 줄에 표시가 붙었다",
                )
                self.assertIsNotNone(body["me"], "로그인했는데 내 줄이 없다")
                self.assertTrue(body["me"]["is_me"], "내 줄인데 표시가 거짓이다")
                self.assertEqual(body["me"]["display_name"], "밖의나")

    def test_a_logged_in_user_without_records_gets_no_mark(self):
        """기록이 없으면 me 도 없고 표시도 없다. 0등짜리 줄을 만들지 않는다."""
        for i, name in enumerate(("기록남1", "기록남2")):
            record_everywhere(make_user(name), 10 - i)

        newbie = make_user("갓가입한사람")
        self.client.force_login(newbie)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertIsNone(body["me"], "기록 없는 사람에게 줄이 나갔다")
                self.assertNotIn(
                    True,
                    [row["is_me"] for row in body["rows"]],
                    "남의 줄이 내 줄로 표시됐다",
                )

    def test_an_inactive_account_gets_no_mark_even_with_records(self):
        """비활성 계정은 목록에서 빠지므로 표시도 없어야 한다.

        빠진 사람에게 표시를 붙이려면 목록 밖 계산이 도는데, 그 결과가
        me 로 나가면 "목록에서 뺀 사람의 등수" 를 알려주는 셈이 된다.
        """
        active = make_user("남은사람")
        record_everywhere(active, 30)

        me = make_user("떠난나")
        record_everywhere(me, 20)
        self.client.force_login(me)
        User.objects.filter(pk=me.pk).update(is_active=False)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertIsNone(body["me"], "비활성 계정에 내 줄이 나갔다")
                self.assertNotIn(
                    "떠난나",
                    [row["display_name"] for row in body["rows"]],
                    "비활성 계정이 목록에 나왔다",
                )
                self.assertNotIn(
                    True,
                    [row["is_me"] for row in body["rows"]],
                    "비활성인데 표시가 붙었다",
                )

    def test_the_mark_follows_identity_not_a_similar_name(self):
        """이름이 비슷해도 표시는 내 줄에만 붙는다.

        같은 이름은 DB 제약(display_name 대소문자 무시 유일)이 막으므로
        만들 수 없다. 대신 한 글자만 다른 이름을 붙여 **이름 문자열로
        내 줄을 찾는 구현**을 잡는다 - 부분 일치나 접두사 비교를 쓰면
        여기서 둘 다에 표시가 붙는다.
        """
        lookalike = make_user("나비슷한사람")
        record_everywhere(lookalike, 40)

        me = make_user("나")
        record_everywhere(me, 10)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                rows = self.client.get(url).json()["rows"]
                marked = [row for row in rows if row["is_me"]]

                self.assertEqual(len(marked), 1, "비슷한 이름에 표시가 같이 붙었다")
                self.assertEqual(marked[0]["score"], 10, "남의 줄에 붙었다")


class PrimaryKeyNeverLeaksTest(TestCase):
    """pk 가 값으로도 안 나가는가.

    키 이름만 보면 부족하다. pk 를 숨긴 이유가 "가장 큰 값이 대략 가입자
    수" 라서이므로, 본문에 그 숫자가 어떤 형태로든 있으면 목적이 깨진다.
    """

    def setUp(self):
        cache.clear()

    def test_the_row_shape_is_exactly_the_contract(self):
        """줄에 있는 칸이 정확히 여섯 개. 늘면 프론트 계약이 바뀐 것이다."""
        me = make_user("계약사람")
        record_everywhere(me, 9)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertEqual(
                    set(body["rows"][0]), ROW_FIELDS, "rows 의 칸이 바뀌었다"
                )

    def test_the_me_row_shape_matches_the_rows(self):
        """me 도 같은 모양이어야 한다. 화면이 같은 컴포넌트로 그린다.

        rows 만 검사하면 me 에 pk 가 남아 있어도 통과한다 - me 는 다른
        경로(_me_outside_top)로 만들어지므로 따로 봐야 한다.
        """
        for i, user in enumerate(bulk_users("me모양_", 21)):
            record_everywhere(user, 300 - i)

        me = make_user("me모양나")
        record_everywhere(me, 2)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).json()

                self.assertIsNotNone(body["me"], "목록 밖인데 내 줄이 없다")
                self.assertEqual(set(body["me"]), ROW_FIELDS, "me 의 칸이 다르다")

    def test_no_pk_value_appears_anywhere_in_the_body(self):
        """본문 어디에도 사용자 pk 숫자가 없어야 한다.

        **pk 를 직접 큰 값으로 만든다.** 시퀀스에 맡기면 이 테스트를 단독
        실행할 때 pk 가 1~5 가 되어 rank 1~5 와 겹친다 - 구현이 멀쩡해도
        실패하고, 전체 실행 때는 pk 가 커서 항상 통과한다. 실행 순서가
        결과를 정하는 테스트는 아무것도 안 지킨다.
        """
        people = User.objects.bulk_create(
            User(pk=900_000 + i, email=f"pk사람{i}@example.com", display_name=f"pk사람{i}")
            for i in range(5)
        )
        for i, person in enumerate(people):
            record_everywhere(person, 50 - i)

        viewer = people[-1]
        self.client.force_login(viewer)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).content.decode()
                numbers = _all_numbers(json.loads(body))

                # 진짜 검사를 **먼저** 한다. 전제 검사를 앞에 두면 pk 가
                # 실제로 샜을 때 그 값이 numbers 의 최대가 되어, 원인이
                # "픽스처가 무너졌다" 로 잘못 표시된다.
                for person in people:
                    self.assertNotIn(
                        person.pk,
                        numbers,
                        f"pk {person.pk} 가 응답 숫자에 들어 있다: {body}",
                    )

                # 그 다음 전제. pk 가 응답 숫자 범위 안이면 위 검사가
                # 참·거짓과 무관하게 의미를 잃는다.
                self.assertGreater(
                    min(person.pk for person in people),
                    max(numbers),
                    "픽스처가 무너졌다 - pk 가 응답 숫자와 겹칠 수 있다",
                )

    def test_no_email_appears_in_the_body(self):
        """pk 대신 이메일이 새면 더 나쁘다. 순위표는 로그인 없이 보인다."""
        me = make_user("메일사람")
        record_everywhere(me, 3)
        self.client.force_login(me)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                body = self.client.get(url).content.decode()

                self.assertNotIn(me.email, body, "이메일이 응답에 나갔다")
                self.assertNotIn("example.com", body, "메일 도메인이 나갔다")
                # "@" 만 찾으면 안 된다. 이름에 @ 를 쓰는 사람이 있으면
                # 아무것도 안 샜는데 빨간불이 된다.


def _all_numbers(value) -> list[int]:
    """응답에 들어 있는 모든 정수. 어느 칸에 숨었든 찾아낸다.

    키 이름을 믿지 않는다. pk 가 rank 나 entries 자리에 섞여 나가도
    잡으려는 것이다.
    """
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, dict):
        return [n for item in value.values() for n in _all_numbers(item)]
    if isinstance(value, list):
        return [n for item in value for n in _all_numbers(item)]
    return []


class AccountSwitchTest(TestCase):
    """계정을 바꾸면 표시도 따라 옮겨가는가.

    같은 클라이언트로 A -> 로그아웃 -> B 를 거친다. 응답을 캐시하거나
    표시를 어딘가에 눌러두면 여기서 드러난다.
    """

    def setUp(self):
        cache.clear()
        self.alice = make_user("앨리스")
        self.bob = make_user("밥")
        record_everywhere(self.alice, 30)
        record_everywhere(self.bob, 20)

    def marked_name(self, url: str) -> str | None:
        body = self.client.get(url).json()
        marked = [row for row in body["rows"] if row["is_me"]]
        self.assertLessEqual(len(marked), 1, "표시가 여러 줄에 붙었다")
        return marked[0]["display_name"] if marked else None

    def test_the_board_shows_a_changed_profile(self):
        """프로필을 바꾸면 순위표가 바로 따라간다.

        _row 는 조회 결과로 임시 User 를 만들어 accounts 의 이름·아바타
        규칙을 빌린다. 그 임시 User 에 값을 제대로 안 담으면 프로필에서
        바꾼 것이 순위표에만 안 나오고, 사용자는 "왜 여기만 옛날 그림이지"
        를 겪는다.

        표시(is_me)가 이름 기준인지는 여기서 못 잡는다 - 로그인한 사람의
        이름은 어떻게 바꿔도 자기 줄과 같기 때문이다. 그쪽은
        test_the_mark_follows_identity_not_a_similar_name 이 본다.
        """
        self.client.force_login(self.alice)

        for url in BOARD_URLS:
            with self.subTest(url=url, phase="before"):
                self.assertEqual(self.marked_name(url), "앨리스")

        User.objects.filter(pk=self.alice.pk).update(
            display_name="앨리스가바꾼이름", avatar="a5"
        )

        for url in BOARD_URLS:
            with self.subTest(url=url, phase="after"):
                body = self.client.get(url).json()
                marked = [row for row in body["rows"] if row["is_me"]]

                self.assertEqual(len(marked), 1, "표시를 잃었거나 둘에 붙었다")
                self.assertEqual(
                    marked[0]["display_name"], "앨리스가바꾼이름", "바꾼 이름이 안 나온다"
                )
                self.assertEqual(
                    marked[0]["avatar"],
                    {"type": "preset", "key": "a5"},
                    "아바타를 바꿨는데 안 따라온다",
                )

    def test_the_mark_moves_when_the_account_changes(self):
        """A 로 보면 A 줄, B 로 보면 B 줄에 표시가 붙는다."""
        for url in BOARD_URLS:
            with self.subTest(url=url):
                self.client.force_login(self.alice)
                self.assertEqual(self.marked_name(url), "앨리스")

                self.client.logout()
                self.assertIsNone(self.marked_name(url), "로그아웃했는데 표시가 남았다")

                self.client.force_login(self.bob)
                self.assertEqual(
                    self.marked_name(url), "밥", "앞사람의 표시가 그대로 왔다"
                )

    def test_two_clients_see_different_marks_for_the_same_board(self):
        """두 사람이 같은 순위표를 봐도 각자 자기 줄만 표시된다.

        응답을 통째로 캐시하면 먼저 부른 쪽 표시가 뒤에 온 사람에게 간다.
        같은 순위표를 연달아 부르는 것이 핵심이라 클라이언트를 둘 쓴다.
        """
        from django.test import Client

        alice_client, bob_client = Client(), Client()
        alice_client.force_login(self.alice)
        bob_client.force_login(self.bob)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                alice_rows = alice_client.get(url).json()["rows"]
                bob_rows = bob_client.get(url).json()["rows"]

                self.assertEqual(
                    [row["display_name"] for row in alice_rows if row["is_me"]],
                    ["앨리스"],
                )
                self.assertEqual(
                    [row["display_name"] for row in bob_rows if row["is_me"]],
                    ["밥"],
                )

    def test_the_rest_of_the_board_is_identical_between_viewers(self):
        """보는 사람이 달라도 표시 말고는 같은 목록이어야 한다.

        표시를 붙이는 과정에서 정렬이나 줄 수가 바뀌면 사람마다 다른
        순위표를 보게 된다.
        """
        from django.test import Client

        guest = Client()
        member = Client()
        member.force_login(self.alice)

        for url in BOARD_URLS:
            with self.subTest(url=url):
                guest_rows = guest.get(url).json()["rows"]
                member_rows = member.get(url).json()["rows"]

                self.assertEqual(
                    [_without_mark(row) for row in guest_rows],
                    [_without_mark(row) for row in member_rows],
                    "보는 사람에 따라 목록이 달라졌다",
                )


def _without_mark(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "is_me"}


class BuildLevelMarkTest(TestCase):
    """API 를 거치지 않고 build() 를 직접. 뷰가 가리는 것을 본다."""

    def setUp(self):
        cache.clear()

    def test_build_without_a_user_marks_nothing(self):
        """user 를 아예 안 넘기면(게스트) 어느 줄도 내 줄이 아니다."""
        for i in range(3):
            record_everywhere(make_user(f"무인자{i}"), 10 - i)

        for kind in leaderboards.KINDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind)

                self.assertEqual([row.is_me for row in board.rows], [False] * 3)
                self.assertIsNone(board.me)

    def test_an_anonymous_user_object_marks_nothing(self):
        """AnonymousUser 를 넘겨도 마찬가지다.

        뷰는 게스트에게 None 이 아니라 AnonymousUser 를 준다. 그 pk 는
        None 인데, 그것을 그대로 비교에 쓰면 "pk 가 None 인 줄" 과 맞아
        떨어질 여지가 생긴다.
        """
        from django.contrib.auth.models import AnonymousUser

        for i in range(3):
            record_everywhere(make_user(f"익명{i}"), 10 - i)

        for kind in leaderboards.KINDS:
            with self.subTest(kind=kind):
                board = leaderboards.build(kind, user=AnonymousUser())

                self.assertEqual([row.is_me for row in board.rows], [False] * 3)
                self.assertIsNone(board.me)

    def test_building_a_row_without_me_pk_fails_loudly(self):
        """_row 는 me_pk 를 반드시 받아야 한다.

        기본값을 두면 새 호출부가 빠뜨렸을 때 조용히 "내 줄 없음" 이 된다.
        화면에서는 강조가 안 되는 것으로만 보여, 순위표는 멀쩡한데 내 줄만
        안 빛나는 상태로 오래 남는다. 여기서 터져야 그때 잡힌다.
        """
        item = {
            "user": 1,
            "user__display_name": "아무개",
            "user__avatar": "",
            "user__google_picture": "",
            "score": 5,
            "entries": 1,
        }

        # 메시지에 me_pk 가 있어야 한다. 그냥 TypeError 를 보면 오타나
        # 시그니처 변경 같은 다른 이유로도 통과한다.
        with self.assertRaisesRegex(TypeError, "me_pk"):
            leaderboards._row(1, item)

        # 넘기면 정상이어야 한다. 위가 "항상 터진다" 로 통과하는 것을 막는다.
        self.assertFalse(leaderboards._row(1, item, me_pk=None).is_me)

    def test_the_row_dataclass_defaults_to_not_me(self):
        """기본값이 False 여야 한다. True 면 새 줄을 만들 때마다 표시가 붙는다."""
        row = leaderboards.Row(rank=1, display_name="아무개", avatar={}, score=1, entries=1)

        self.assertFalse(row.is_me)

    def test_marking_is_consistent_between_the_top_and_my_row(self):
        """목록 안이면 rows 에만, 밖이면 me 에만. 둘 다이거나 둘 다 아닌 경우가 없다."""
        crowd = [make_user(f"일관{i:02d}") for i in range(25)]
        for i, user in enumerate(crowd):
            record_everywhere(user, 500 - i)

        for kind in leaderboards.KINDS:
            for user in (crowd[0], crowd[10], crowd[19], crowd[20], crowd[24]):
                with self.subTest(kind=kind, name=user.display_name):
                    board = leaderboards.build(kind, user=user)
                    in_list = [row for row in board.rows if row.is_me]

                    self.assertEqual(
                        len(in_list) + (1 if board.me else 0),
                        1,
                        "내 줄이 없거나 둘이다",
                    )
                    if board.me is not None:
                        self.assertTrue(board.me.is_me, "me 인데 표시가 거짓이다")
                        self.assertEqual(
                            board.me.display_name, user.display_name, "남의 줄이 me 로 왔다"
                        )
                    else:
                        self.assertEqual(
                            in_list[0].display_name,
                            user.display_name,
                            "남의 줄에 표시가 붙었다",
                        )
