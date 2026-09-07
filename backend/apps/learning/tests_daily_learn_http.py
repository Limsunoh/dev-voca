"""일일공부 학습 단계를 HTTP 로 직접 친다.

기존 테스트는 daily_study 함수를 직접 부른다. 그것으로는 안 보이는
자리가 있다 - 화면이 실제로 받는 것은 view 가 조립한 응답이고, 거기서
학습 카드(learning)와 문제(question)가 **같은 응답에** 실린다. 둘이
어긋나면 함수 단위로는 다 통과하는데 화면만 깨진다.

여기서 확인하는 것은 넷이다.

    - 응답에 실린 학습 카드와 그 응답에 실린 문제의 정답이 맞물리나
    - 남의 토큰·조작한 토큰·이상한 순서로 쳤을 때 400 이지 500 이 아닌가
    - 검수 안 된 단어가 학습 카드로 새는가 (이 저장소의 최대 결함 유형)
    - 세 길이를 끝까지 다 풀었을 때 점수·보너스·묶음이 약속대로인가

`learning` 이 비어 있는 응답은 "문제를 풀 차례" 라는 뜻이라, 카드가
비었는지만 보면 안 되고 **카드가 있을 때 그 안에 정답이 있는지**를 봐야
한다. 그게 이 기능의 존재 이유다.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import calendar_kst, daily_study
from .models import STUDY_PLANS, DailyScore, DailyStudy, StudyLength
from .tests_daily_study import ANSWER_URL, START_URL, make_user, seed_words


def answer_id_of(token: str) -> int:
    """이 문제의 정답 id. 보기를 하나씩 넣어 찾는다.

    토큰의 정답은 지문(HMAC)이라 그대로 못 읽는다. 공격자가 할 수 있는
    것과 같은 일이지만 여기서는 "무엇이 정답인가" 를 확인하는 용도다.
    """
    state = daily_study._load(token)["q"]
    for choice_id in state["c"]:
        graded = quiz.resolve_answer(state, choice_id)
        if graded is not None and graded[0]:
            return choice_id
    raise AssertionError("보기 중에 정답이 없다")


class HttpFlowTest(TestCase):
    """화면이 실제로 하는 왕복을 그대로 친다."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("http")
        self.client.force_login(self.user)

    def start(self, length=StudyLength.SHORT):
        res = self.client.post(START_URL, {"length": length}, "application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_the_cards_in_a_response_contain_that_response_s_answer(self):
        """한 응답 안에서 카드와 문제가 맞물린다.

        함수 단위 테스트는 learn_targets 와 _next_question 을 따로 부르지만
        화면은 한 응답만 본다. view 가 둘을 조립하는 순서가 틀리면(카드를
        뽑기 전에 문제를 낸다든지) 여기서만 드러난다.
        """
        body = self.start()
        card_ids = [c["id"] for c in body["learning"]]

        self.assertTrue(card_ids, "시작 응답에 학습 카드가 없다")
        self.assertIn(
            answer_id_of(body["token"]),
            card_ids,
            "응답에 실린 카드와 그 응답의 문제가 어긋났다",
        )

    def test_every_chunk_boundary_response_keeps_the_pair(self):
        """묶음이 넘어가는 답의 응답에서도 카드와 문제가 맞물린다.

        시작 응답만 맞고 그 뒤가 어긋나는 것이 있을 수 있다 - 답하기는
        카드와 문제를 다른 함수로 만든다(learn_targets vs _next_question).
        """
        body = self.start()
        token = body["token"]

        for step in range(8):  # SHORT 학습분 8문제
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            data = res.json()
            token = data["token"]
            if token is None:
                break

            if data["learning"]:
                card_ids = [c["id"] for c in data["learning"]]
                self.assertIn(
                    answer_id_of(token),
                    card_ids,
                    f"{step}번째 답 뒤 카드와 문제가 어긋났다",
                )

    def test_a_get_gives_the_same_pair_as_the_start(self):
        """시작 직후 GET 이 같은 카드·같은 문제를 준다.

        화면을 새로 열면 GET 으로 이어 받는다. 거기서 다른 문제가 나오면
        아는 것이 나올 때까지 새로고침하면 되고, 다른 카드가 나오면 방금
        본 것과 문제가 어긋난다.
        """
        started = self.start()

        res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200, res.content)
        resumed = res.json()

        self.assertEqual(
            answer_id_of(started["token"]),
            answer_id_of(resumed["token"]),
            "GET 이 다른 문제를 줬다",
        )
        self.assertEqual(
            [c["id"] for c in started["learning"]],
            [c["id"] for c in resumed["learning"]],
            "GET 이 다른 카드를 줬다",
        )

    def test_repeated_gets_do_not_grow_the_learned_list(self):
        """GET 을 스무 번 쳐도 학습 목록이 안 늘어난다.

        늘어나면 슬라이스 구간이 밀려 화면에 보인 카드가 문제 범위로
        안 쓰인다. 새로고침은 사용자가 아무 생각 없이 하는 동작이라
        여기가 가장 자주 밟히는 자리다.
        """
        self.start()
        study = daily_study.today_of(self.user)
        size = study.chunk_size

        for _ in range(20):
            self.client.get(START_URL)

        study.refresh_from_db()
        self.assertEqual(
            len(study.learned_ids), size, "GET 을 반복하니 학습 목록이 늘었다"
        )
        self.assertEqual(study.issued_chunks, 1, "묶음 수가 늘었다")

    def test_an_unreviewed_chunk_does_not_grow_the_list_on_refresh(self):
        """뽑아둔 묶음이 통째로 미검수로 내려가도 GET 이 새 묶음을 안 붙인다.

        **위 테스트만으로는 못 잡는다.** "이미 뽑았나" 를 카드가 보이는지로
        판정하면 미검수일 때만 오판하므로, 검수가 살아 있는 판에서는 스무
        번을 쳐도 안 늘어난다. 이 게이트를 지키려면 미검수 조건을 함께
        걸어야 한다.
        """
        self.start()
        study = daily_study.today_of(self.user)
        size = study.chunk_size
        Word.objects.filter(pk__in=study.learned_ids).update(is_reviewed=False)

        for _ in range(6):
            self.assertEqual(self.client.get(START_URL).status_code, 200)

        study.refresh_from_db()
        self.assertEqual(
            len(study.learned_ids),
            size,
            "미검수 묶음 때문에 GET 마다 새 묶음이 붙었다",
        )
        self.assertEqual(study.issued_chunks, 1, "묶음 수가 늘었다")

    def test_the_cards_never_include_an_unreviewed_word(self):
        """검수 안 된 단어는 학습 카드로 안 나간다.

        학습 카드는 뜻과 설명을 통째로 보여주는 자리라, 미검수가 새면
        아무도 확인하지 않은 내용을 "배우세요" 라고 내미는 꼴이다.
        목록·검색보다 노출이 더 직접적이다.
        """
        body = self.start(StudyLength.LONG)
        seen = {c["id"] for c in body["learning"]}

        token = body["token"]
        for _ in range(30):
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            )
            data = res.json()
            seen.update(c["id"] for c in data["learning"])
            token = data["token"]
            if token is None:
                break

        hidden = set(
            Word.objects.filter(pk__in=seen, is_reviewed=False).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(hidden, set(), "미검수 단어가 학습 카드로 나갔다")

    def test_a_word_unreviewed_midway_disappears_from_the_cards(self):
        """진행 중에 검수가 취소되면 그 단어는 카드에서 빠진다.

        뽑아둔 id 는 learned_ids 에 남아 있어서, 카드를 그릴 때 다시
        visible() 을 걸지 않으면 그대로 나간다.
        """
        self.start()
        study = daily_study.today_of(self.user)
        victim = study.learned_ids[0]
        Word.objects.filter(pk=victim).update(is_reviewed=False)

        res = self.client.get(START_URL)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertNotIn(
            victim,
            [c["id"] for c in res.json()["learning"]],
            "검수가 취소된 단어가 카드에 남았다",
        )


class TokenAbuseTest(TestCase):
    """남의 토큰, 조작한 토큰, 이상한 값."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("주인")
        self.other = make_user("남")

    def start_as(self, user, length=StudyLength.SHORT):
        self.client.force_login(user)
        res = self.client.post(START_URL, {"length": length}, "application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()

    def test_another_user_cannot_answer_my_question(self):
        """남의 토큰으로 답하면 400 이다.

        토큰이 판 pk 를 담고 있어서 user 를 함께 걸지 않으면 남의 판에
        답이 쌓인다. 하루 한 번이라 피해자는 되돌릴 방법이 없다.
        """
        body = self.start_as(self.user)
        token = body["token"]

        self.client.force_login(self.other)
        res = self.client.post(
            ANSWER_URL,
            {"token": token, "choice_id": answer_id_of(token)},
            "application/json",
        )
        self.assertEqual(res.status_code, 400, res.content)

        study = daily_study.today_of(self.user)
        self.assertEqual(study.answered, 0, "남이 내 판에 답을 쌓았다")

    def test_an_anonymous_request_is_refused(self):
        """로그인 안 하면 조회도 답하기도 막힌다."""
        body = self.start_as(self.user)
        self.client.logout()

        self.assertIn(self.client.get(START_URL).status_code, (401, 403))
        self.assertIn(
            self.client.post(
                ANSWER_URL,
                {"token": body["token"], "choice_id": 1},
                "application/json",
            ).status_code,
            (401, 403),
        )

    def test_a_tampered_token_is_a_400_not_a_500(self):
        """서명을 건드린 토큰은 400 이다.

        500 이면 스택이 새고, 무엇보다 방어가 예외로 우연히 막힌 것이라
        다른 입력에서는 통과할 수 있다.
        """
        body = self.start_as(self.user)
        bad = body["token"][:-3] + "aaa"

        res = self.client.post(
            ANSWER_URL, {"token": bad, "choice_id": 1}, "application/json"
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_junk_tokens_are_400(self):
        """모양이 이상한 토큰들도 400 이다.

        토큰 구조가 배포로 바뀌면 옛 모양이 6시간 동안 들어온다. int()
        가 밖에서 터지면 400 이 아니라 500 이 나간다.
        """
        self.start_as(self.user)
        for bad in ("", "  ", "a", "." * 200, "9" * 500, "eyJ4Ijox.abc.def"):
            res = self.client.post(
                ANSWER_URL, {"token": bad, "choice_id": 1}, "application/json"
            )
            self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

    def test_bad_choice_ids_are_400_not_500(self):
        """보기 id 가 이상해도 400 이다.

        빠뜨림·문자열·bool·음수·거대한 수. bool 은 int 의 하위라
        True 가 1 로 통과하는 자리가 있어 따로 본다.
        """
        body = self.start_as(self.user)
        token = body["token"]

        for bad in (None, "1", True, [], {}, 1.5):
            payload = {"token": token}
            if bad is not None:
                payload["choice_id"] = bad
            res = self.client.post(ANSWER_URL, payload, "application/json")
            self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

        study = daily_study.today_of(self.user)
        self.assertEqual(study.answered, 0, "거절한 답이 쌓였다")

    def test_an_out_of_range_choice_counts_as_wrong_not_an_error(self):
        """보기에 없는 id 는 오답 처리지 에러가 아니다.

        음수·존재하지 않는 pk·자리수가 큰 수. 여기서 500 이 나면 답을
        보내는 것만으로 서버를 흔들 수 있다.
        """
        body = self.start_as(self.user)
        token = body["token"]

        for bad in (-1, 0, 10**12):
            res = self.client.post(
                ANSWER_URL, {"token": token, "choice_id": bad}, "application/json"
            )
            self.assertEqual(res.status_code, 200, f"{bad} 에서 200 이 아니다")
            data = res.json()
            self.assertFalse(data["result"]["correct"], f"{bad} 가 정답 처리됐다")
            token = data["token"]

    def test_a_replayed_token_cannot_farm_points(self):
        """같은 토큰으로 정답을 다시 보내도 점수가 안 오른다.

        첫 답의 응답이 정답을 알려주므로, 옛 토큰에 그 답을 실어 다시
        보내면 확실히 +1 이 된다. 문제 수로 끝나는 규칙이라 절반만
        탐색해도 만점이다.
        """
        body = self.start_as(self.user)
        token = body["token"]
        right = answer_id_of(token)

        first = self.client.post(
            ANSWER_URL, {"token": token, "choice_id": right}, "application/json"
        )
        self.assertEqual(first.status_code, 200, first.content)

        before = daily_study.today_of(self.user).score
        for _ in range(5):
            again = self.client.post(
                ANSWER_URL, {"token": token, "choice_id": right}, "application/json"
            )
            self.assertEqual(again.status_code, 400, again.content)

        self.assertEqual(
            daily_study.today_of(self.user).score, before, "재사용으로 점수가 올랐다"
        )

    def test_starting_twice_is_refused(self):
        """오늘 두 번 시작하면 400 이다.

        열리면 점수가 깎이는 판을 버리고 새로 시작할 수 있다.
        """
        self.start_as(self.user)
        for length in StudyLength.values:
            res = self.client.post(START_URL, {"length": length}, "application/json")
            self.assertEqual(res.status_code, 400, res.content)

        self.assertEqual(
            DailyStudy.objects.filter(user=self.user).count(), 1, "판이 둘이 됐다"
        )

    def test_a_bad_length_is_refused(self):
        """모르는 길이는 400 이고 판이 안 생긴다."""
        self.client.force_login(self.user)
        for bad in ("", " ", "5M", "1h", "x" * 100, 5, None, ["5m"]):
            payload = {} if bad is None else {"length": bad}
            res = self.client.post(START_URL, payload, "application/json")
            self.assertEqual(res.status_code, 400, f"{bad!r} 에서 400 이 아니다")

        self.assertFalse(
            DailyStudy.objects.filter(user=self.user).exists(), "판이 생겼다"
        )


class FullRunTest(TestCase):
    """세 길이를 끝까지 다 푼다."""

    def setUp(self):
        cache.clear()
        seed_words(200)
        self.user = make_user("완주")
        self.client.force_login(self.user)

    def run_to_the_end(self, length):
        """다 풀 때까지 정답만 낸다. 푼 횟수를 돌려준다."""
        res = self.client.post(START_URL, {"length": length}, "application/json")
        self.assertEqual(res.status_code, 201, res.content)
        token = res.json()["token"]

        count = 0
        while token is not None:
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            data = res.json()
            count += 1
            token = data["token"]
            self.assertLess(count, 100, "안 끝난다")
        return count, data

    def test_short_pays_the_full_bonus(self):
        """5분 코스를 다 풀면 문제 수 + 보너스다."""
        plan = STUDY_PLANS[StudyLength.SHORT]
        count, data = self.run_to_the_end(StudyLength.SHORT)

        self.assertEqual(count, plan.total, "약속한 문제 수와 다르다")
        self.assertTrue(data["finished"], "안 끝났다고 나온다")
        self.assertEqual(data["study"]["score"], plan.total + plan.bonus)

    def test_medium_pays_the_full_bonus(self):
        """10분 코스도 같다. 묶음 구성이 달라 따로 본다."""
        plan = STUDY_PLANS[StudyLength.MEDIUM]
        count, data = self.run_to_the_end(StudyLength.MEDIUM)

        self.assertEqual(count, plan.total)
        self.assertEqual(data["study"]["score"], plan.total + plan.bonus)

    def test_long_pays_the_full_bonus(self):
        """30분 코스. 묶음이 6개라 학습분이 가장 길다."""
        plan = STUDY_PLANS[StudyLength.LONG]
        count, data = self.run_to_the_end(StudyLength.LONG)

        self.assertEqual(count, plan.total)
        self.assertEqual(data["study"]["score"], plan.total + plan.bonus)

    def test_the_daily_score_matches_the_study(self):
        """완주 뒤 그날 줄이 판 점수와 같다.

        보너스는 _finish 에서만 더해진다. 중간 _publish 가 남긴 값이
        덮이지 않으면 순위표만 낮게 나온다.
        """
        plan = STUDY_PLANS[StudyLength.SHORT]
        self.run_to_the_end(StudyLength.SHORT)

        row = DailyScore.objects.get(user=self.user, day=calendar_kst.today())
        self.assertEqual(row.daily_study_score, plan.total + plan.bonus)

    def test_answering_after_the_end_is_refused(self):
        """끝난 뒤에 답하면 400 이고 점수가 안 변한다."""
        plan = STUDY_PLANS[StudyLength.SHORT]
        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, "application/json"
        )
        token = res.json()["token"]

        stale = token  # 첫 문제 토큰을 들고 있다가 끝난 뒤 쓴다
        while token is not None:
            data = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            ).json()
            token = data["token"]

        res = self.client.post(
            ANSWER_URL, {"token": stale, "choice_id": 1}, "application/json"
        )
        self.assertEqual(res.status_code, 400, res.content)
        study = daily_study.today_of(self.user)
        self.assertEqual(study.score, plan.total + plan.bonus, "점수가 변했다")

    def test_all_chunks_were_actually_issued(self):
        """완주하면 계획한 묶음을 다 뽑았다.

        중간에 발급이 조용히 실패하면 그 뒤 문제가 전체에서 나온다.
        점수만 보면 안 드러난다.
        """
        self.run_to_the_end(StudyLength.LONG)

        study = daily_study.today_of(self.user)
        self.assertEqual(study.issued_chunks, study.chunk_count, "묶음이 덜 뽑혔다")
        self.assertEqual(
            len(study.learned_ids),
            study.chunk_size * study.chunk_count,
            "학습 목록 길이가 묶음 구성과 안 맞는다",
        )
        self.assertEqual(
            len(set(study.learned_ids)),
            len(study.learned_ids),
            "같은 단어를 두 묶음에서 배웠다",
        )


class ThinContentTest(TestCase):
    """단어가 거의 없을 때."""

    def setUp(self):
        cache.clear()

    def make_words(self, count):
        seed_words(count)

    def test_a_single_word_does_not_500(self):
        """단어 하나뿐이어도 시작이 400 이지 500 이 아니다.

        보기 넷을 못 채우면 문제를 못 만든다. 그때 조용히 터지면 화면이
        빈 채로 멈춘다.
        """
        self.make_words(1)
        user = make_user("한개")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, "application/json"
        )
        self.assertIn(res.status_code, (201, 400), res.content)

    def test_no_words_at_all_is_a_400(self):
        """단어가 0개면 400 이다."""
        user = make_user("빈통")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, "application/json"
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(DailyStudy.objects.filter(user=user).exists())

    def test_fewer_words_than_a_chunk_skips_learning(self):
        """단어가 묶음 크기보다 적으면 학습 없이 푼다.

        부분 묶음을 저장하면 구간 경계가 밀린다. 학습을 끄는 쪽이 낫다.
        """
        self.make_words(5)
        user = make_user("작은통")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, "application/json"
        )
        if res.status_code != 201:
            self.skipTest("이 규모에서는 문제를 못 만든다")

        study = daily_study.today_of(user)
        self.assertLessEqual(
            study.chunk_size * study.chunk_count,
            study.total_questions,
            "학습분이 총 문제 수를 넘었다",
        )
        self.assertLessEqual(
            len(study.learned_ids),
            Word.objects.visible().count(),
            "있는 단어보다 많이 배웠다",
        )

    def test_a_playthrough_on_a_thin_corpus_never_500s(self):
        """단어 12개로 30분 코스를 끝까지 밀어도 500 이 안 난다.

        후보가 도중에 바닥난다. 그때 판을 닫아주지 않으면 사용자는 오늘
        판을 영영 못 끝낸다.
        """
        self.make_words(12)
        user = make_user("얇은통")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.LONG}, "application/json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        token = res.json()["token"]

        for _ in range(60):
            if token is None:
                break
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            )
            self.assertEqual(res.status_code, 200, res.content)
            token = res.json()["token"]

        study = daily_study.today_of(user)
        self.assertTrue(study.is_done, "판이 안 닫혔다")

    def test_the_scope_never_exceeds_the_chunk_size(self):
        """뽑은 묶음 하나가 chunk_size 를 넘지 않는다.

        넘으면 그다음 슬라이스가 밀려 화면에 안 보인 단어로 문제가 나간다.
        """
        self.make_words(60)
        user = make_user("경계")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.MEDIUM}, "application/json"
        )
        token = res.json()["token"]

        for _ in range(25):
            if token is None:
                break
            study = daily_study.today_of(user)
            self.assertEqual(
                len(study.learned_ids),
                study.issued_chunks * study.chunk_size,
                "학습 목록 길이가 뽑은 묶음 수와 안 맞는다",
            )
            res = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            )
            token = res.json()["token"]


class PromisedCountTest(TestCase):
    """약속한 문제 수를 실제로 내는가.

    _answerable() 이 "낼 수 있는 문제 수" 를 단어+문장 개수로 세는데,
    **셀 수 있는 것과 낼 수 있는 것이 다르다.** 그 차이가 벌어지면
    사용자는 25문제를 약속받고 8문제만 풀고 끝난다 - 왜 일찍 끝났는지
    화면에 설명이 없고, 완주 보너스도 못 받는다.
    """

    def setUp(self):
        cache.clear()

    def test_a_word_thin_sentence_heavy_corpus_keeps_its_promise(self):
        """단어가 적고 문장이 많아도 약속한 문제 수를 다 낸다.

        **여기가 실제로 터졌던 자리다.** _answerable() 이 단어와 문장을
        그냥 더해서, 단어 6개 + 문장 100개인 DB 를 106 으로 세고 25문제를
        약속했다. 실제로는 8문제에서 끊겼다 - 화면에 왜 일찍 끝났는지
        설명이 없고 완주 보너스도 안 나갔다.

        두 종류는 서로를 못 채운다. 출제가 종류를 매번 무작위로 고르는데
        단어 차례에 단어 후보가 비어 있으면 거기서 판이 닫히고, 한 종류로
        낼 수 있는 수는 최근 창(RECENT_KEEP) 때문에 그 종류의 개수를 못
        넘는다. 문장이 100개여도 단어 6개가 병목이다.

        지금은 적은 쪽 개수로 약속하므로 6문제를 약속하고 6문제를 낸다.
        """
        seed_words(6)
        for i in range(100):
            Sentence.objects.create(
                text=f"This is sentence number {i} here.",
                translation=f"문장{i}",
                context=f"상황{i}",
                is_reviewed=True,
            )

        user = make_user("약속")
        self.client.force_login(user)
        res = self.client.post(
            START_URL, {"length": StudyLength.MEDIUM}, "application/json"
        )
        self.assertEqual(res.status_code, 201, res.content)

        study = daily_study.today_of(user)
        promised = study.total_questions
        token = res.json()["token"]

        answered = 0
        while token is not None and answered < 60:
            data = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            ).json()
            token = data["token"]
            answered += 1

        study.refresh_from_db()
        self.assertTrue(study.is_done, "판이 안 닫혔다 - 사용자가 못 끝낸다")
        self.assertEqual(
            study.answered,
            promised,
            f"약속({promised})보다 적게 냈다: {study.answered}",
        )
        # 다 풀었으니 완주 보너스가 나가야 한다. 약속을 지켰다는 것이
        # 점수에도 드러나는 자리다.
        self.assertGreater(
            study.score, study.answered, "다 풀었는데 완주 보너스가 안 나갔다"
        )

    def test_a_words_only_corpus_keeps_its_promise(self):
        """단어만 있으면 약속한 문제 수를 다 낸다.

        위 결함이 "콘텐츠가 적으면 원래 그렇다" 가 아니라 **문장이 섞일
        때만** 생기는 것임을 못 박는다. 단어 30개는 30문제를 다 낸다.
        """
        seed_words(30)
        user = make_user("단어만")
        self.client.force_login(user)

        res = self.client.post(
            START_URL, {"length": StudyLength.LONG}, "application/json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        study = daily_study.today_of(user)
        promised = study.total_questions
        token = res.json()["token"]

        answered = 0
        while token is not None and answered < 80:
            data = self.client.post(
                ANSWER_URL,
                {"token": token, "choice_id": answer_id_of(token)},
                "application/json",
            ).json()
            token = data["token"]
            answered += 1

        study.refresh_from_db()
        self.assertEqual(study.answered, promised, "약속한 문제 수를 못 냈다")
        self.assertEqual(
            study.score, promised + study.bonus, "완주했는데 보너스가 안 나왔다"
        )


class MidnightTest(TestCase):
    """자정을 넘길 때."""

    def setUp(self):
        cache.clear()
        seed_words()
        self.user = make_user("자정")
        self.client.force_login(self.user)

    def test_a_token_from_yesterday_cannot_be_answered_today(self):
        """어제 판의 토큰으로 오늘 답할 수 없다.

        정산이 어제 판을 닫으므로 그 토큰은 죽어야 한다. 살아 있으면
        어제 판에 오늘 점수를 더 쌓을 수 있다.
        """
        res = self.client.post(
            START_URL, {"length": StudyLength.SHORT}, "application/json"
        )
        token = res.json()["token"]

        study = daily_study.today_of(self.user)
        yesterday = calendar_kst.today() - timedelta(days=1)
        DailyStudy.objects.filter(pk=study.pk).update(day=yesterday)

        # GET 이 어제 판을 정산해 닫는다
        self.assertEqual(self.client.get(START_URL).status_code, 200)

        res = self.client.post(
            ANSWER_URL, {"token": token, "choice_id": 1}, "application/json"
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_yesterday_s_unfinished_study_does_not_block_today(self):
        """어제 못 끝낸 판이 있어도 오늘 새로 시작할 수 있다.

        정산이 안 돌면 (user, day) 제약이 아니라 "이미 시작했다" 판정에
        걸려 오늘 판을 아예 못 연다.
        """
        self.client.post(START_URL, {"length": StudyLength.SHORT}, "application/json")
        study = daily_study.today_of(self.user)
        yesterday = calendar_kst.today() - timedelta(days=1)
        DailyStudy.objects.filter(pk=study.pk).update(day=yesterday)

        res = self.client.post(
            START_URL, {"length": StudyLength.MEDIUM}, "application/json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(DailyStudy.objects.filter(user=self.user).count(), 2)

    def test_an_unfinished_yesterday_pays_no_bonus(self):
        """어제 판이 정산될 때 완주 보너스는 안 준다."""
        self.client.post(START_URL, {"length": StudyLength.SHORT}, "application/json")
        study = daily_study.today_of(self.user)
        yesterday = calendar_kst.today() - timedelta(days=1)
        DailyStudy.objects.filter(pk=study.pk).update(day=yesterday)

        self.client.get(START_URL)

        study.refresh_from_db()
        self.assertTrue(study.is_done, "정산이 안 됐다")
        self.assertEqual(study.score, 0, "안 푼 판에 보너스가 나갔다")
