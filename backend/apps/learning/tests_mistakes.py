"""오답 노트.

**복습과 목록이 다르다.** 복습은 "지금 볼 것" 이라 틀린 것에 더해 오래된
것까지 내지만, 오답 노트는 마지막에 틀린 것만이다. 그 차이가 이 파일이
지키는 첫 번째 것이다.

두 번째는 검수 게이트다. 틀린 기록이 쌓인 뒤에 단어가 미검수로 돌아갈 수
있고, 그때 그 내용이 목록으로 새면 안 된다.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, SentenceKind, Word

from . import daily_study, record, review, session
from .models import ReviewState
from .views_history import MistakesThrottle

PASSWORD = secrets.token_urlsafe(16)
URL = "/api/learning/mistakes/"


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}@example.com", password=PASSWORD, display_name=name
    )


def make_word(reviewed: bool = True) -> Word:
    tag = uuid4().hex[:8]
    return Word.objects.create(
        term=f"{tag}",
        meaning=f"뜻 {tag}",
        description="설명입니다",
        is_reviewed=reviewed,
    )


def make_sentence(reviewed: bool = True) -> Sentence:
    tag = uuid4().hex[:8]
    return Sentence.objects.create(
        text=f"This is {tag}.",
        translation=f"해석 {tag}",
        kind=SentenceKind.PHRASE,
        is_reviewed=reviewed,
    )


def mark(user, target, *, wrong: bool, streak: int = 0) -> ReviewState:
    """그 사람이 그 항목을 틀렸다(또는 맞혔다)고 기록한다."""
    kind = "word" if isinstance(target, Word) else "sentence"
    return ReviewState.objects.create(
        user=user,
        target_type=kind,
        target_id=target.pk,
        is_wrong=wrong,
        streak=streak,
        last_correct_at=None if wrong else timezone.now(),
    )


class MistakesListTest(TestCase):
    def setUp(self):
        self.user = make_user("오답")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()

        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_has_a_rate_limit(self):
        """한도를 넘으면 429 다.

        테스트에서는 한도를 크게 열어 두므로(settings 와 같은 관용구),
        여기서만 둘로 줄여 세 번째가 막히는지 본다. throttle_classes 를
        빼면 세 번째도 200 이 나와 빨개진다.
        """
        with mock.patch.object(MistakesThrottle, "rate", "2/min"):
            codes = [self.client.get(URL).status_code for _ in range(3)]

        self.assertEqual(codes, [200, 200, 429])

    def test_shows_only_wrong_ones(self):
        """맞힌 것은 안 나온다. 이 화면의 이름이 그것이다."""
        wrong = make_word()
        right = make_word()
        mark(self.user, wrong, wrong=True)
        mark(self.user, right, wrong=False, streak=1)

        rows = self.client.get(URL).json()["results"]

        self.assertEqual([r["text"] for r in rows], [wrong.term])

    def test_does_not_show_other_peoples_mistakes(self):
        mine = make_word()
        theirs = make_word()
        mark(self.user, mine, wrong=True)
        mark(make_user("남"), theirs, wrong=True)

        rows = self.client.get(URL).json()["results"]

        self.assertEqual([r["text"] for r in rows], [mine.term])

    def test_later_rows_come_first(self):
        """나중에 쌓인 줄이 위에 온다."""
        first_word, second_word = make_word(), make_word()
        mark(self.user, first_word, wrong=True)
        mark(self.user, second_word, wrong=True)

        rows = self.client.get(URL).json()["results"]

        self.assertEqual(
            [r["text"] for r in rows], [second_word.term, first_word.term]
        )

    def test_row_carries_exactly_these_fields(self):
        """한 줄에 담기는 칸을 통째로 못 박는다.

        빼 둔 칸이 둘 있다. 이름 하나만 확인하면 다른 이름으로 다시
        들어와도 통과하므로, 칸 전체를 본다.

        - **틀린 날짜.** 한동안 `updated_at` 을 "마지막에 틀린 때" 로
          내보냈는데 거짓이었다. 자유 문제풀이와 일일공부는 `bulk_update`
          로 줄을 고치고, 그 경로는 `auto_now` 를 안 돌린다(아래 테스트가
          그 사실을 못 박는다). 틀린 값을 보여주느니 안 보내는 것이 낫다.
        - **"몇 번 더 맞히면 빠지나".** 이 목록은 어디서든 한 번 맞히면
          빠지므로 줄마다 다를 값이 없다. 화면이 머리말에 한 번만 적는다.
        """
        mark(self.user, make_word(), wrong=True)

        row = self.client.get(URL).json()["results"][0]

        self.assertEqual(
            set(row), {"id", "target_type", "target_id", "text", "meaning"}
        )

    def test_free_quiz_path_does_not_move_updated_at(self):
        """`bulk_update` 는 `auto_now` 를 안 돌린다 - 정렬 근거로 못 쓴다.

        이 테스트가 없으면 누군가 "최근순으로 바꾸자" 며 `-updated_at` 을
        되돌려 놓고, 복습으로만 확인해서 통과했다고 믿는다. 자유
        문제풀이·일일공부가 쓰는 경로로 직접 눌러 본다.
        """
        word = make_word()
        row = mark(self.user, word, wrong=True)
        past = timezone.now() - timedelta(days=30)
        ReviewState.objects.filter(pk=row.pk).update(updated_at=past)

        record.bump_review_states(self.user, {("word", word.pk): False})

        after = ReviewState.objects.get(pk=row.pk).updated_at
        self.assertEqual(
            after.date(),
            past.date(),
            "bulk_update 가 updated_at 을 움직였다면 정렬 근거를 다시 봐야 한다",
        )

    def test_one_correct_answer_anywhere_removes_it(self):
        """화면 머리말의 약속 - "어디서든 다시 한 번 맞히면 빠진다".

        한때 머리말이 "복습에서 연속으로 맞히면" 이라고 했는데 사실이
        아니었다. 연속 두 번은 복습의 졸업 조건이고, 이 목록은 마지막 답이
        맞으면 그 자리에서 빠진다. 복습을 안 거치는 자유 문제풀이 경로로
        확인한다 - 거기서도 빠져야 머리말이 맞다.
        """
        word = make_word()
        mark(self.user, word, wrong=True)
        self.assertEqual(self.client.get(URL).json()["count"], 1)

        record.bump_review_states(self.user, {("word", word.pk): True})

        self.assertEqual(self.client.get(URL).json()["count"], 0)

    def test_sentence_rows_carry_text_and_translation(self):
        sentence = make_sentence()
        mark(self.user, sentence, wrong=True)

        row = self.client.get(URL).json()["results"][0]

        self.assertEqual(row["target_type"], "sentence")
        self.assertEqual(row["text"], sentence.text)
        self.assertEqual(row["meaning"], sentence.translation)


    def test_row_points_at_the_target(self):
        """화면이 상세로 보내려면 종류와 id 가 있어야 한다."""
        word = make_word()
        mark(self.user, word, wrong=True)

        row = self.client.get(URL).json()["results"][0]

        self.assertEqual(row["target_type"], "word")
        self.assertEqual(row["target_id"], word.pk)


class MistakesGateTest(TestCase):
    """검수 안 된 것이 새지 않는지.

    틀린 기록이 쌓인 **뒤에** 검수가 취소될 수 있다. 그때 그 줄만 본문이
    없는데, 게이트를 안 걸면 검수 취소된 내용이 그대로 나간다.
    """

    def setUp(self):
        self.user = make_user("게이트")
        self.client.force_login(self.user)

    def test_unreviewed_word_is_hidden(self):
        word = make_word(reviewed=True)
        mark(self.user, word, wrong=True)
        # 검수를 취소한다. 기록은 이미 쌓여 있다.
        Word.objects.filter(pk=word.pk).update(is_reviewed=False)

        rows = self.client.get(URL).json()["results"]

        self.assertEqual(rows, [])

    def test_unreviewed_sentence_is_hidden(self):
        sentence = make_sentence(reviewed=True)
        mark(self.user, sentence, wrong=True)
        Sentence.objects.filter(pk=sentence.pk).update(is_reviewed=False)

        self.assertEqual(self.client.get(URL).json()["results"], [])

    def test_deleted_target_is_hidden(self):
        """지워진 항목의 줄은 고아로 남는다. 그것도 안 보여준다."""
        word = make_word()
        mark(self.user, word, wrong=True)
        word.delete()

        self.assertEqual(self.client.get(URL).json()["results"], [])

    def test_count_matches_what_is_shown(self):
        """센 개수와 뜨는 줄 수가 같아야 한다.

        가려질 줄을 페이지로 자른 **뒤에** 빼면 둘이 어긋난다. 실제로 그렇게
        짰다가 단어 둘을 미검수로 돌리니 "22개" 라고 적힌 화면에 18줄만
        떴다. 마지막 페이지가 통째로 비는 경우도 생긴다.
        """
        for _ in range(5):
            mark(self.user, make_word(), wrong=True)
        hidden = make_word()
        mark(self.user, hidden, wrong=True)
        Word.objects.filter(pk=hidden.pk).update(is_reviewed=False)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 5)
        self.assertEqual(len(body["results"]), 5)

    def test_last_page_is_not_empty(self):
        """가려진 줄이 많아도 마지막 페이지가 비지 않는다."""
        # 21줄을 만들고 그중 둘을 가린다. 자른 뒤에 빼는 방식이면
        # 19줄이 남아 2페이지가 비어 버린다.
        for _ in range(19):
            mark(self.user, make_word(), wrong=True)
        for _ in range(2):
            hidden = make_word()
            mark(self.user, hidden, wrong=True)
            Word.objects.filter(pk=hidden.pk).update(is_reviewed=False)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 19)
        # 19개면 한 페이지에 다 들어간다. 다음 페이지가 없어야 한다.
        self.assertIsNone(body["next"])

    def test_hidden_rows_do_not_leave_holes(self):
        """가려진 줄이 섞여도 나머지는 정상으로 나온다."""
        ok_word = make_word()
        gone_word = make_word()
        mark(self.user, ok_word, wrong=True)
        mark(self.user, gone_word, wrong=True)
        Word.objects.filter(pk=gone_word.pk).update(is_reviewed=False)

        rows = self.client.get(URL).json()["results"]

        self.assertEqual([r["text"] for r in rows], [ok_word.term])


class MistakesPagingTest(TestCase):
    def setUp(self):
        self.user = make_user("페이지")
        self.client.force_login(self.user)

    def test_pages_like_the_other_lists(self):
        """기존 목록과 같은 방식(DRF 페이지네이션)이어야 화면이 그대로 쓴다."""
        for _ in range(25):
            mark(self.user, make_word(), wrong=True)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 25)
        self.assertEqual(len(body["results"]), 20)
        self.assertIsNotNone(body["next"])

    def test_second_page(self):
        for _ in range(25):
            mark(self.user, make_word(), wrong=True)

        body = self.client.get(URL, {"page": 2}).json()

        self.assertEqual(len(body["results"]), 5)
        self.assertIsNone(body["next"])

    def test_query_count_does_not_grow_with_rows(self):
        """줄이 늘어도 질의 수가 그대로여야 한다.

        **지키려는 것은 "정확히 몇 번" 이 아니라 "줄 수와 무관하다" 이다.**
        절대값만 박아두면 미들웨어가 하나 늘어도 이 테스트가 빨개지고,
        반대로 줄마다 조회하도록 되돌려도 고정 데이터에서는 숫자만 고쳐
        통과시킬 수 있다. 그래서 두 번 재서 **같은지**를 본다.
        """
        for _ in range(5):
            mark(self.user, make_word(), wrong=True)
        for _ in range(5):
            mark(self.user, make_sentence(), wrong=True)

        with CaptureQueriesContext(connection) as small:
            self.client.get(URL)

        # 줄을 두 배로 늘린다.
        for _ in range(5):
            mark(self.user, make_word(), wrong=True)
        for _ in range(5):
            mark(self.user, make_sentence(), wrong=True)

        with CaptureQueriesContext(connection) as big:
            self.client.get(URL)

        self.assertEqual(len(small), len(big))


class MistakesGateEdgeTest(TestCase):
    """검수 게이트의 가장자리. 위 MistakesGateTest 가 못 보는 자리다.

    위 클래스는 개수를 단어로만 센다. 문장 쪽 개수와, 종류가 다른데 id 가
    같은 경우는 거기서 안 걸린다 - 게이트가 종류를 무시하고 id 만 보면
    숨긴 단어가 같은 번호의 문장 덕에 개수에 남는다.
    """

    def setUp(self):
        self.user = make_user("게이트끝")
        self.client.force_login(self.user)

    def test_unreviewed_sentence_leaves_the_count(self):
        """문장을 미검수로 돌리면 줄과 개수가 **함께** 준다.

        단어로만 세어 두면 문장 쪽 하위 질의가 빠져도 모른다 - 그러면 줄은
        _serialize 가 걸러 안 보이는데 개수만 남아 "3개" 에 2줄이 뜬다.
        """
        shown = [make_sentence() for _ in range(2)]
        hidden = make_sentence()
        for one in [*shown, hidden]:
            mark(self.user, one, wrong=True)
        Sentence.objects.filter(pk=hidden.pk).update(is_reviewed=False)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 2)
        self.assertEqual(
            sorted(r["text"] for r in body["results"]),
            sorted(s.text for s in shown),
        )

    def test_deleted_sentence_leaves_the_count(self):
        sentence = make_sentence()
        mark(self.user, sentence, wrong=True)
        sentence.delete()

        body = self.client.get(URL).json()

        self.assertEqual((body["count"], body["results"]), (0, []))

    def test_gate_does_not_mix_up_a_word_and_a_sentence_with_the_same_id(self):
        """번호가 같은 단어와 문장. 숨긴 쪽만 빠져야 한다.

        ReviewState 는 대상을 FK 로 안 묶어서 종류와 id 를 **함께** 봐야
        한다. id 만 보는 게이트면 미검수 단어가 같은 번호의 검수된 문장
        덕에 개수에 남는다(본문은 단어 표를 따로 보니 줄은 안 뜨고 개수만
        어긋난다).
        """
        word = make_word(reviewed=False)
        sentence = Sentence.objects.create(
            pk=word.pk,
            text="Same id sentence.",
            translation="같은 번호 문장",
            kind=SentenceKind.PHRASE,
            is_reviewed=True,
        )
        mark(self.user, word, wrong=True)
        mark(self.user, sentence, wrong=True)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 1)
        self.assertEqual(
            [(r["target_type"], r["text"]) for r in body["results"]],
            [("sentence", sentence.text)],
        )

    def test_body_lookup_has_its_own_gate(self):
        """질의와 본문 조회 사이에 검수가 취소되는 틈. 두 번째 게이트다.

        주 게이트(_visible_targets)가 살아 있으면 이 틈은 테스트로 못
        만든다. 그래서 주 게이트를 비워 틈을 흉내낸다 - 본문 조회에서
        visible() 을 빼면 여기서 미검수 뜻이 그대로 나간다.
        """
        word = make_word()
        sentence = make_sentence()
        mark(self.user, word, wrong=True)
        mark(self.user, sentence, wrong=True)
        Word.objects.filter(pk=word.pk).update(is_reviewed=False)
        Sentence.objects.filter(pk=sentence.pk).update(is_reviewed=False)

        with mock.patch(
            "apps.learning.views_history._visible_targets", return_value=Q()
        ):
            rows = self.client.get(URL).json()["results"]

        self.assertEqual(rows, [])

    def test_unreviewed_rows_on_a_later_page_do_not_leak(self):
        """2페이지로 밀릴 줄도 게이트를 지난다.

        첫 페이지만 보는 테스트로는 "페이지를 자른 뒤에만 게이트를 건다"
        같은 실수를 못 잡는다. 가린 줄은 pk 가 가장 작아 21번째, 즉
        2페이지 몫이다 - 가려졌으면 2페이지가 아예 없어야 한다.
        """
        hidden = make_word()
        mark(self.user, hidden, wrong=True)
        for _ in range(20):
            mark(self.user, make_word(), wrong=True)
        Word.objects.filter(pk=hidden.pk).update(is_reviewed=False)

        first = self.client.get(URL).json()

        self.assertEqual(first["count"], 20)
        self.assertIsNone(first["next"])
        self.assertEqual(self.client.get(URL, {"page": 2}).status_code, 404)


class MistakesOwnershipTest(TestCase):
    """남의 기록. 같은 단어를 두 사람이 다르게 풀었을 때다."""

    def setUp(self):
        self.me = make_user("나")
        self.other = make_user("너")

    def _count_of(self, user) -> int:
        self.client.force_login(user)
        return self.client.get(URL).json()["count"]

    def test_the_same_word_follows_each_persons_last_answer(self):
        """나는 맞혔고 너는 틀렸다 - 너에게만 뜬다.

        user 조건이 빠지면 남의 오답이 섞이는데, 단어가 같으면 text 로는
        누구 줄인지 가려지지 않는다. 개수로 본다.
        """
        word = make_word()
        mark(self.me, word, wrong=False, streak=1)
        mark(self.other, word, wrong=True)
        for _ in range(3):
            mark(self.other, make_word(), wrong=True)

        self.assertEqual(self._count_of(self.me), 0)
        self.assertEqual(self._count_of(self.other), 4)


def answer_of(load, token: str) -> tuple[str, int]:
    """(종류, 정답 id). 사용자는 알 수 없지만 테스트는 알아야 한다.

    세 경로(자유 문제풀이·일일공부·복습)가 토큰 서명만 다르고 문제 모양은
    같다. 풀 함수만 받아 한 곳에서 꺼낸다.
    """
    state = load(token)["q"]
    return state["tt"], quiz.resolve_answer(state, -1)[1]


def seed_words(count: int) -> None:
    """문제를 낼 만큼 단어를 채운다. 일일공부는 40개 넘게 필요하다."""
    tag = uuid4().hex[:6]
    Word.objects.bulk_create(
        Word(
            term=f"{tag}w{i}",
            meaning=f"뜻{i}",
            description=f"설명{i} 입니다",
            is_reviewed=True,
        )
        for i in range(count)
    )


class OneCorrectAnswerAnywhereTest(TestCase):
    """머리말의 약속 "어디서든 다시 한 번 맞히면 빠진다" 를 세 경로로 본다.

    위 test_one_correct_answer_anywhere_removes_it 는 record 함수를 직접
    부른다. 여기서는 화면이 실제로 부르는 API 로 맞힌다 - 뷰가 복습 쓰기를
    빼먹는 경로가 생기면 저쪽은 초록인 채로 약속이 깨진다.

    무엇이 나올지는 서버가 고르므로, 문제를 받은 **뒤에** 그 정답을 틀린
    것으로 심고 API 로 맞힌다.
    """

    def setUp(self):
        cache.clear()
        seed_words(120)
        self.user = make_user("세경로")
        self.client.force_login(self.user)

    def _post(self, url: str, body: dict):
        return self.client.post(url, body, content_type="application/json")

    def _plant_wrong(self, target_type: str, target_id: int) -> None:
        ReviewState.objects.create(
            user=self.user, target_type=target_type, target_id=target_id, is_wrong=True
        )
        self.assertEqual(self.client.get(URL).json()["count"], 1)

    def test_free_round(self):
        """자유 문제풀이. 복습 쓰기는 판을 **닫을 때** 일어난다."""
        token = self._post("/api/learning/rounds/", {}).json()["token"]
        tt, aid = answer_of(session._load, token)
        self._plant_wrong(tt, aid)

        answered = self._post(
            "/api/learning/rounds/answer/", {"token": token, "choice_id": aid}
        ).json()
        self.assertTrue(answered["result"]["correct"])
        finished = self._post(
            "/api/learning/rounds/finish/", {"token": answered["token"]}
        ).json()
        self.assertTrue(finished["recorded"])

        self.assertEqual(self.client.get(URL).json()["count"], 0)

    def test_free_round_miss_puts_it_in(self):
        """반대 방향. 자유 문제풀이에서 틀리면 들어온다."""
        started = self._post("/api/learning/rounds/", {}).json()
        tt, aid = answer_of(session._load, started["token"])
        wrong = next(c["id"] for c in started["question"]["choices"] if c["id"] != aid)

        answered = self._post(
            "/api/learning/rounds/answer/",
            {"token": started["token"], "choice_id": wrong},
        ).json()
        self._post("/api/learning/rounds/finish/", {"token": answered["token"]})

        rows = self.client.get(URL).json()["results"]
        self.assertEqual(
            [(r["target_type"], r["target_id"]) for r in rows], [(tt, aid)]
        )

    def test_daily_study(self):
        """일일공부. 끝내기가 없고 답마다 쓴다. 학습 차례면 넘긴다."""
        data = self._post("/api/learning/daily/", {"length": "5m"}).json()
        for _ in range(10):
            if data.get("question") is not None:
                break
            data = self.client.get("/api/learning/daily/").json()
        self.assertIsNotNone(data.get("question"), "문제까지 못 갔다")

        tt, aid = answer_of(daily_study._load, data["token"])
        self._plant_wrong(tt, aid)

        answered = self._post(
            "/api/learning/daily/answer/", {"token": data["token"], "choice_id": aid}
        )
        self.assertEqual(answered.status_code, 200)
        self.assertTrue(answered.json()["result"]["correct"])

        self.assertEqual(self.client.get(URL).json()["count"], 0)

    def test_review_needs_only_one_even_before_graduating(self):
        """복습. 한 번 맞히면 졸업 전이어도 여기서는 빠진다.

        복습 목록에는 아직 남아 있어야 한다(연속 두 번이 졸업). 머리말의
        "복습에는 더 많을 수 있다" 가 이 차이다.
        """
        word = make_word()
        mark(self.user, word, wrong=True)

        token = self._post("/api/learning/review/", {}).json()["token"]
        self.assertEqual(answer_of(review._load, token), ("word", word.pk))

        answered = self._post(
            "/api/learning/review/answer/", {"token": token, "choice_id": word.pk}
        ).json()
        self.assertFalse(answered["result"]["graduated"])

        self.assertEqual(self.client.get(URL).json()["count"], 0)
        self.assertEqual(self.client.get("/api/learning/review/").json()["due"], 1)


class MistakesPagingEdgeTest(TestCase):
    """페이지 경계. 화면이 404 를 받아 첫 페이지로 보내는 근거가 여기다."""

    def setUp(self):
        self.user = make_user("경계")
        self.client.force_login(self.user)

    def _fill(self, n: int) -> None:
        for _ in range(n):
            mark(self.user, make_word(), wrong=True)

    def _page(self, page):
        return self.client.get(URL, {"page": page})

    def test_row_boundaries(self):
        """21·40·41줄. 한 줄이 넘칠 때만 페이지가 는다."""
        self._fill(21)
        self.assertEqual(len(self._page(2).json()["results"]), 1)

        self._fill(19)  # 40
        self.assertEqual(len(self._page(2).json()["results"]), 20)
        self.assertEqual(self._page(3).status_code, 404)

        self._fill(1)  # 41
        self.assertEqual(len(self._page(3).json()["results"]), 1)

    def test_bad_page_numbers_are_404_not_500(self):
        """손으로 고친 주소. 404 여야 화면이 첫 페이지로 보낸다.

        500 이 나면 화면은 "불러오지 못했습니다" 를 띄운다 - 서버 장애로
        읽힌다.
        """
        self._fill(3)
        for page in ("0", "-1", "abc", "99999", "1.5", "9" * 30):
            with self.subTest(page=page):
                self.assertEqual(self._page(page).status_code, 404)

    def test_empty_first_page_is_200(self):
        """빈 목록의 첫 페이지는 404 가 아니다.

        화면은 "페이지 번호 없이 404" 를 주소가 없는 것으로 읽는다. 빈
        목록이 404 를 주면 새로 온 사람이 전부 "불러오지 못했습니다" 를 본다.
        """
        for params in ({}, {"page": 1}):
            with self.subTest(params=params):
                got = self.client.get(URL, params)
                self.assertEqual(got.status_code, 200)
                self.assertEqual(got.json()["count"], 0)

    def test_page_size_cannot_be_raised(self):
        """page_size 를 붙여도 20줄이다.

        한 번에 전부 끌어가는 길이 열리면 분당 60 한도가 비용 상한 노릇을
        못 한다.
        """
        self._fill(25)

        body = self.client.get(URL, {"page_size": 1000}).json()

        self.assertEqual(len(body["results"]), 20)


class MistakesMethodAndThrottleTest(TestCase):
    def setUp(self):
        self.user = make_user("한도")
        self.client.force_login(self.user)

    def test_only_get(self):
        """읽기만 하는 자리다. 쓰기 메서드는 405."""
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(URL).status_code, 405)

    def test_rate_limit_is_per_account(self):
        """한 사람이 한도를 다 써도 다른 사람은 열린다.

        통이 하나면 한 계정이 분당 60번을 태워 모두의 오답 노트를 막는다.
        """
        other = make_user("다른한도")
        with mock.patch.object(MistakesThrottle, "rate", "2/min"):
            for _ in range(2):
                self.client.get(URL)
            self.assertEqual(self.client.get(URL).status_code, 429)

            self.client.force_login(other)
            self.assertEqual(self.client.get(URL).status_code, 200)
