"""학습 점검(복습 거르기·한 판 답 상한·일일공부 오답 유지·그만둔 판의 오답)의 경계.

tests_audit_learning.py 가 기본 흐름을 본다. 여기서는 그 옆자리를 본다.

- 복습: 단어와 문장이 섞이고 id 가 서로 겹칠 때, 판 도중에 내려갈 때, 다시 검수될 때
  세 숫자(개수, 목록, 판의 문제 수)와 오답 노트가 어긋나지 않는가
- 한 판: 60 번째 답까지 받고 61 번째를 거절하는가. 넘기기도 상한에 드는가. 점수는 그대로인가
- 일일공부: 카드에 없던 단어, 같은 id 의 문장, 자정을 넘긴 판
- 그만두기: 같은 답 재전송, 같은 판에서 틀린 뒤 맞히기, 남의 판 토큰, 늦은 정답
"""

from __future__ import annotations

import random
import secrets
from datetime import timedelta
from unittest import mock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.vocab import quiz
from apps.vocab.models import Sentence, Word

from . import daily_study, review, session
from .models import DailyPreview, DailyStudy, ReviewState, StudyLength

PASSWORD = secrets.token_urlsafe(16)

MISTAKES_URL = "/api/learning/mistakes/"
REVIEW_URL = "/api/learning/review/"
ROUND_URL = "/api/learning/rounds/"
ROUND_ANSWER_URL = "/api/learning/rounds/answer/"
ROUND_FINISH_URL = "/api/learning/rounds/finish/"
DAILY_URL = "/api/learning/daily/"
DAILY_ANSWER_URL = "/api/learning/daily/answer/"


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}-{uuid4().hex[:6]}@example.com",
        password=PASSWORD,
        display_name=name,
    )


def seed_words(count: int) -> list[Word]:
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
    return list(Word.objects.filter(term__startswith=tag).order_by("pk"))


def seed_sentences(count: int) -> list[Sentence]:
    tag = uuid4().hex[:6]
    Sentence.objects.bulk_create(
        Sentence(
            text=f"{tag} sentence text {i}",
            translation=f"해석{i}",
            context=f"상황{i}",
            is_reviewed=True,
        )
        for i in range(count)
    )
    return list(Sentence.objects.filter(text__startswith=tag).order_by("pk"))


def answer_of(load, token: str) -> tuple[str, int]:
    """(종류, 정답 id). 테스트만 안다."""
    state = load(token)["q"]
    return state["tt"], quiz.resolve_answer(state, -1)[1]


def wrong_choice(question: dict, answer_id: int) -> int:
    return next(c["id"] for c in question["choices"] if c["id"] != answer_id)


class _ApiMixin:
    def _post(self, url: str, body: dict):
        return self.client.post(url, body, content_type="application/json")

    def _mistakes(self) -> set[tuple[str, int]]:
        rows = self.client.get(MISTAKES_URL).json()["results"]
        return {(r["target_type"], r["target_id"]) for r in rows}

    def _mistake_count(self) -> int:
        return self.client.get(MISTAKES_URL).json()["count"]


# ---- 복습 ----


class ReviewMixedTargetsTest(_ApiMixin, TestCase):
    """단어와 문장이 섞이고, 보이는 것과 숨은 것과 지운 것이 섞인 목록."""

    def setUp(self):
        cache.clear()
        self.words = seed_words(12)
        self.sentences = seed_sentences(12)
        self.user = make_user("섞임")
        self.client.force_login(self.user)

    def _state(self, target_type: str, target_id: int, **kw) -> ReviewState:
        return ReviewState.objects.create(
            user=self.user, target_type=target_type, target_id=target_id, **kw
        )

    def _due_keys(self) -> list[tuple[str, int]]:
        return [(r.target_type, r.target_id) for r in review.due_of(self.user)]

    def test_three_counts_agree_with_hidden_and_deleted_of_both_kinds(self):
        """GET 의 due, due_of 의 길이, 판을 연 total 이 같고 숨은 줄은 어디에도 없다."""
        w_hidden, w_deleted, w_ok = self.words[0], self.words[1], self.words[2]
        s_hidden, s_deleted, s_ok = self.sentences[0], self.sentences[1], self.sentences[2]

        # 틀린 것이 먼저 정렬되므로 숨은 줄을 모두 틀린 것으로 둔다. 보이는 줄은 오래된 것.
        self._state(quiz.TARGET_WORD, w_hidden.pk, is_wrong=True)
        self._state(quiz.TARGET_WORD, w_deleted.pk, is_wrong=True)
        self._state(quiz.TARGET_SENTENCE, s_hidden.pk, is_wrong=True)
        self._state(quiz.TARGET_SENTENCE, s_deleted.pk, is_wrong=True)
        self._state(quiz.TARGET_WORD, w_ok.pk, is_wrong=True)
        self._state(
            quiz.TARGET_SENTENCE,
            s_ok.pk,
            last_correct_at=timezone.now() - timedelta(days=30),
        )

        Word.objects.filter(pk=w_hidden.pk).update(is_reviewed=False)
        Sentence.objects.filter(pk=s_hidden.pk).update(is_reviewed=False)
        w_deleted.delete()
        s_deleted.delete()

        expected = {(quiz.TARGET_WORD, w_ok.pk), (quiz.TARGET_SENTENCE, s_ok.pk)}
        self.assertEqual(set(self._due_keys()), expected)
        self.assertEqual(review.count_due(self.user), 2)
        self.assertEqual(self.client.get(REVIEW_URL).json()["due"], 2)

        started = self._post(REVIEW_URL, {})
        self.assertEqual(started.status_code, 201)
        self.assertEqual(started.json()["total"], 2)
        self.assertEqual(started.json()["question"]["total"], 2)

        # 오답 노트는 틀린 것만이라 보이는 틀린 단어 하나다. 복습은 그것을 포함한다.
        self.assertEqual(self._mistakes(), {(quiz.TARGET_WORD, w_ok.pk)})
        self.assertLessEqual(self._mistake_count(), review.count_due(self.user))

    def test_same_id_across_kinds_is_judged_by_its_own_table(self):
        """단어 N 이 숨고 문장 N 이 보이면 문장 줄만 남는다. 반대도.

        종류를 안 보고 id 로만 거르면 한쪽이 다른 쪽의 검수 상태를 빌린다.
        """
        Word.objects.all().delete()
        Sentence.objects.all().delete()
        # 같은 pk 를 손으로 맞춘다. 시퀀스와 겹치지 않게 큰 수를 쓴다.
        base = 900_000
        for offset, (w_ok, s_ok) in enumerate([(False, True), (True, False)]):
            pk = base + offset
            Word.objects.create(
                pk=pk, term=f"same{pk}", meaning="뜻", description="설명", is_reviewed=w_ok
            )
            Sentence.objects.create(
                pk=pk, text=f"same {pk}", translation="해석", context="상황", is_reviewed=s_ok
            )
            self._state(quiz.TARGET_WORD, pk, is_wrong=True)
            self._state(quiz.TARGET_SENTENCE, pk, is_wrong=True)

        expected = {(quiz.TARGET_SENTENCE, base), (quiz.TARGET_WORD, base + 1)}
        self.assertEqual(set(self._due_keys()), expected)
        self.assertEqual(review.count_due(self.user), 2)
        self.assertEqual(self._mistakes(), expected)

    def test_hidden_rows_in_front_of_more_than_one_round(self):
        """숨은 틀린 줄이 한 판(20) 넘게 앞을 막아도 뒤의 보이는 줄로 판이 열린다.

        문장 줄로 막는다. 단어로만 막는 시험은 문장 쪽 조건이 빠져도 통과한다.
        """
        many = seed_sentences(review.ROUND_SIZE + 5)
        for one in many:
            self._state(quiz.TARGET_SENTENCE, one.pk, is_wrong=True)
        Sentence.objects.filter(pk__in=[s.pk for s in many]).update(is_reviewed=False)

        visible = self.words[5]
        self._state(
            quiz.TARGET_WORD,
            visible.pk,
            last_correct_at=timezone.now() - timedelta(days=30),
        )

        self.assertEqual(review.count_due(self.user), 1)
        started = self._post(REVIEW_URL, {})
        self.assertEqual(started.status_code, 201, started.content)
        self.assertEqual(started.json()["total"], 1)
        self.assertEqual(
            answer_of(review._load, started.json()["token"]),
            (quiz.TARGET_WORD, visible.pk),
        )

    def test_hidden_mid_round_is_skipped_and_comes_back_when_reviewed_again(self):
        """판 도중에 내려간 줄은 건너뛰고, 다시 검수되면 틀린 상태 그대로 돌아온다.

        거르기는 줄을 지우지 않는다. 지우면 검수를 잠깐 내렸다 올린 것만으로 오답이 사라진다.
        """
        first, second, third = self.words[0], self.words[1], self.words[2]
        for one in (first, second, third):
            self._state(quiz.TARGET_WORD, one.pk, is_wrong=True)

        started = self._post(REVIEW_URL, {}).json()
        self.assertEqual(started["total"], 3)
        token = started["token"]
        _tt, now_id = answer_of(review._load, token)
        order = [tuple(t) for t in review._load(token)["t"]]
        next_id = order[1][1]

        Word.objects.filter(pk=next_id).update(is_reviewed=False)
        self.assertEqual(review.count_due(self.user), 2)

        answered = self._post(
            "/api/learning/review/answer/", {"token": token, "choice_id": now_id}
        )
        self.assertEqual(answered.status_code, 200, answered.content)
        body = answered.json()
        self.assertFalse(body["finished"])
        self.assertEqual(answer_of(review._load, body["token"]), order[2])

        self.assertNotIn((quiz.TARGET_WORD, next_id), self._mistakes())

        Word.objects.filter(pk=next_id).update(is_reviewed=True)
        self.assertIn((quiz.TARGET_WORD, next_id), self._mistakes())
        self.assertIn((quiz.TARGET_WORD, next_id), self._due_keys())

    def test_mistake_note_is_a_subset_of_review(self):
        """오답 노트의 줄은 전부 복습에 있다. 복습에만 있는 것은 오래된 것과 복습 중인 것이다."""
        wrong, stale, half, fresh, hidden = self.words[:5]
        self._state(quiz.TARGET_WORD, wrong.pk, is_wrong=True)
        self._state(
            quiz.TARGET_WORD, stale.pk, last_correct_at=timezone.now() - timedelta(days=8)
        )
        self._state(quiz.TARGET_WORD, half.pk, streak=1, last_correct_at=timezone.now())
        self._state(quiz.TARGET_WORD, fresh.pk, last_correct_at=timezone.now())
        self._state(quiz.TARGET_WORD, hidden.pk, is_wrong=True)
        Word.objects.filter(pk=hidden.pk).update(is_reviewed=False)

        due = set(self._due_keys())
        note = self._mistakes()
        self.assertEqual(note, {(quiz.TARGET_WORD, wrong.pk)})
        self.assertTrue(note <= due)
        self.assertEqual(
            due - note,
            {(quiz.TARGET_WORD, stale.pk), (quiz.TARGET_WORD, half.pk)},
        )
        self.assertEqual(review.count_due(self.user), len(due))


# ---- 한 판 ----


class RoundAnswerCapTest(_ApiMixin, TestCase):
    """한 판은 답 60 개까지. 넘기기도 그 안에 든다."""

    CAP = 60

    def setUp(self):
        cache.clear()
        seed_words(120)
        self.user = make_user("상한")
        self.client.force_login(self.user)

    def test_sixty_including_skips_ends_the_round_and_score_unchanged(self):
        started = self._post(ROUND_URL, {}).json()
        token, question = started["token"], started["question"]

        correct = wrong = skipped = 0
        # 같은 단어가 판 안에서 다시 나올 수 있다(최근 40개만 피한다). 끝내기는 마지막 결과를 쓴다.
        last: dict[tuple[str, int], bool] = {}
        for i in range(self.CAP):
            tt, aid = answer_of(session._load, token)
            if i < session.MAX_SKIPS:
                body = {"token": token, "skip": True}
                skipped += 1
            elif i % 2:
                body = {"token": token, "choice_id": aid}
                correct += 1
                last[(tt, aid)] = True
            else:
                body = {"token": token, "choice_id": wrong_choice(question, aid)}
                wrong += 1
                last[(tt, aid)] = False
            res = self._post(ROUND_ANSWER_URL, body)
            self.assertEqual(res.status_code, 200, f"{i + 1} 번째 답: {res.content!r}")
            data = res.json()
            token, question = data["token"], data["question"]
            if i < self.CAP - 1:
                self.assertIsNotNone(question, f"{i + 1} 번째 답 뒤에 문제가 끊겼다")
            else:
                # 상한에 닿은 답이 판을 끝낸다. 다음 문제를 내면 그 답이 거절돼 화면이 멈춘다.
                self.assertIsNone(question)
                self.assertTrue(data["finished"])

        self.assertEqual(len(session._load(token)["a"]), self.CAP)

        # 끝난 판 토큰으로 더 답하면 거절된다(낼 문제가 없다).
        refused = self._post(ROUND_ANSWER_URL, {"token": token, "choice_id": 1})
        self.assertEqual(refused.status_code, 400)

        # 거절된 답은 순번을 안 태운다. 같은 토큰으로 닫을 수 있다.
        finished = self._post(ROUND_FINISH_URL, {"token": token})
        self.assertEqual(finished.status_code, 200, finished.content)
        body = finished.json()
        self.assertEqual(body["answered"], self.CAP)
        self.assertEqual(body["correct"], correct)
        self.assertEqual(body["skipped"], skipped)
        self.assertEqual(
            body["score"],
            correct * session.SCORE_IN_TIME + wrong * session.SCORE_WRONG,
        )
        self.assertTrue(body["recorded"])

        # 끝내기가 같은 답을 다시 반영해도 오답 노트는 마지막에 틀린 것 그대로다.
        # 화면은 20개씩 나누므로 줄은 DB 에서, 개수는 화면에서 본다.
        expected = {key for key, ok in last.items() if not ok}
        in_db = set(
            ReviewState.objects.filter(user=self.user, is_wrong=True).values_list(
                "target_type", "target_id"
            )
        )
        self.assertEqual(in_db, expected)
        self.assertEqual(self._mistake_count(), len(expected))


# ---- 일일공부 ----


class DailyKeepWrongEdgeTest(_ApiMixin, TestCase):
    """카드로 본 단어만 맞혀도 남는다. 그 밖은 맞히면 빠진다."""

    def setUp(self):
        cache.clear()
        seed_words(120)
        self.user = make_user("일일")
        self.client.force_login(self.user)

    def _open(self) -> dict:
        data = self._post(DAILY_URL, {"length": "5m"}).json()
        for _ in range(10):
            if data.get("question") is not None:
                return data
            data = self.client.get(DAILY_URL).json()
        self.fail("문제까지 못 갔다")

    def _study(self) -> DailyStudy:
        return DailyStudy.objects.get(user=self.user)

    def _to_rest_section(self) -> str:
        """학습분(묶음 2개 x 4)을 모두 맞혀 지나간다. 남은 차례의 토큰을 돌려준다."""
        token = self._open()["token"]
        study = self._study()
        learning = study.chunk_size * study.chunk_count
        for _ in range(learning):
            _tt, aid = answer_of(daily_study._load, token)
            res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
            self.assertEqual(res.status_code, 200, res.content)
            token = res.json()["token"]
        self.assertIsNone(daily_study._now_chunk(self._study()))
        return token

    def _plant_wrong(self, target_type: str, target_id: int) -> None:
        ReviewState.objects.update_or_create(
            user=self.user,
            target_type=target_type,
            target_id=target_id,
            defaults={"is_wrong": True, "streak": 0},
        )

    def _keep_learned_ids_away_from(self, answer_id: int) -> None:
        """남은 차례의 정답이 우연히 오늘 카드 단어면 다른 id 로 바꿔 끼운다. 길이는 지킨다."""
        study = self._study()
        if answer_id in study.learned_ids:
            spare = (
                Word.objects.visible()
                .exclude(pk__in=[*study.learned_ids, answer_id])
                .values_list("pk", flat=True)
                .first()
            )
            study.learned_ids = [spare if pk == answer_id else pk for pk in study.learned_ids]
            study.save(update_fields=["learned_ids"])

    def test_word_not_on_todays_cards_is_cleared_when_answered_right(self):
        """시험 차례(학습분 뒤)에 나온, 카드에 없던 틀린 단어는 맞히면 빠진다."""
        token = self._to_rest_section()
        tt, aid = answer_of(daily_study._load, token)
        self.assertEqual(tt, quiz.TARGET_WORD)
        self._keep_learned_ids_away_from(aid)
        self._plant_wrong(tt, aid)

        res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
        self.assertTrue(res.json()["result"]["correct"])

        row = ReviewState.objects.get(user=self.user, target_type=tt, target_id=aid)
        self.assertFalse(row.is_wrong)
        self.assertIsNotNone(row.last_correct_at)
        self.assertNotIn((tt, aid), self._mistakes())

    def test_sentence_with_the_same_id_as_a_card_word_is_cleared(self):
        """문장 문제의 정답 id 가 오늘 카드 단어 id 와 같아도 문장은 맞히면 빠진다.

        keep_wrong 이 종류를 안 보고 id 만 보면 이 문장이 오답에 남는다.
        """
        seed_sentences(12)
        real_choice = random.choice

        def situation_first(seq):
            if seq == quiz.QuizKind.ALL:
                return quiz.QuizKind.SITUATION
            return real_choice(seq)

        with mock.patch.object(session.random, "choice", side_effect=situation_first):
            token = self._to_rest_section()

        tt, sid = answer_of(daily_study._load, token)
        self.assertEqual(tt, quiz.TARGET_SENTENCE)

        # 오늘 카드 단어 하나의 자리에 문장 id 와 같은 수를 넣는다. 학습분이 끝나 그 목록은
        # 이제 keep_wrong 판정에만 쓰인다.
        study = self._study()
        study.learned_ids = [sid, *study.learned_ids[1:]]
        study.save(update_fields=["learned_ids"])
        self._plant_wrong(tt, sid)

        res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": sid})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["result"]["correct"])
        self.assertFalse(
            ReviewState.objects.get(user=self.user, target_type=tt, target_id=sid).is_wrong
        )

    def test_card_word_still_kept_after_midnight(self):
        """어제 시작한 판을 자정 뒤에 이어 풀어도 그 판의 카드 단어는 맞혀도 남는다."""
        token = self._open()["token"]
        tt, aid = answer_of(daily_study._load, token)
        self.assertIn(aid, self._study().learned_ids)
        self._plant_wrong(tt, aid)
        before = ReviewState.objects.get(user=self.user, target_type=tt, target_id=aid)

        DailyStudy.objects.filter(user=self.user).update(
            day=self._study().day - timedelta(days=1)
        )

        res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["result"]["correct"])

        after = ReviewState.objects.get(pk=before.pk)
        self.assertTrue(after.is_wrong)
        self.assertEqual(after.last_correct_at, before.last_correct_at)
        self.assertIn((tt, aid), self._mistakes())


# ---- 그만두기(한 판 도중의 오답) ----


class RoundQuitEdgeTest(_ApiMixin, TestCase):
    """한 판의 틀린 답은 답할 때 남는다. 그 곁의 경우들."""

    def setUp(self):
        cache.clear()
        self.words = seed_words(60)
        self.user = make_user("그만")
        self.client.force_login(self.user)

    def _start(self) -> dict:
        return self._post(ROUND_URL, {}).json()

    def test_resent_same_wrong_answer_returns_first_reply_and_one_row(self):
        """응답이 끊겨 같은 틀린 답을 다시 보내도 처음 응답이 오고 줄은 하나다."""
        started = self._start()
        tt, aid = answer_of(session._load, started["token"])
        body = {"token": started["token"], "choice_id": wrong_choice(started["question"], aid)}

        first = self._post(ROUND_ANSWER_URL, body)
        again = self._post(ROUND_ANSWER_URL, body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["token"], first.json()["token"])

        rows = ReviewState.objects.filter(user=self.user)
        self.assertEqual([(r.target_type, r.target_id, r.is_wrong) for r in rows], [(tt, aid, True)])

        # 다른 보기로 다시 보내면 거절되고 아무것도 안 바뀐다.
        other = next(
            c["id"]
            for c in started["question"]["choices"]
            if c["id"] not in (aid, body["choice_id"])
        )
        refused = self._post(ROUND_ANSWER_URL, {"token": started["token"], "choice_id": other})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(ReviewState.objects.filter(user=self.user).count(), 1)

    def test_wrong_then_right_in_the_same_round_and_finish_keeps_the_last(self):
        """같은 판에서 틀린 뒤 맞히고 끝내면 마지막 결과(맞음)가 남는다. 안 끝내면 틀림이 남는다."""
        target = self.words[0]

        def same_word(*_a, **_k):
            return quiz.make_for_word(target, Word.objects.visible())

        with mock.patch.object(session, "make_question", side_effect=same_word):
            started = self._start()
            token, question = started["token"], started["question"]
            self.assertEqual(answer_of(session._load, token), (quiz.TARGET_WORD, target.pk))

            miss = self._post(
                ROUND_ANSWER_URL,
                {"token": token, "choice_id": wrong_choice(question, target.pk)},
            ).json()
            self.assertIn((quiz.TARGET_WORD, target.pk), self._mistakes())

            hit = self._post(
                ROUND_ANSWER_URL, {"token": miss["token"], "choice_id": target.pk}
            ).json()
            self.assertTrue(hit["result"]["correct"])
            # 맞힌 답은 끝내기 전에는 안 남는다.
            self.assertIn((quiz.TARGET_WORD, target.pk), self._mistakes())

        finished = self._post(ROUND_FINISH_URL, {"token": hit["token"]}).json()
        self.assertTrue(finished["recorded"])
        row = ReviewState.objects.get(user=self.user, target_type=quiz.TARGET_WORD, target_id=target.pk)
        self.assertFalse(row.is_wrong)
        self.assertNotIn((quiz.TARGET_WORD, target.pk), self._mistakes())

    def test_finishing_with_an_older_token_is_refused_and_the_wrong_stays(self):
        """틀린 뒤 그 앞 토큰으로 닫아 오답을 지우려 해도 거절되고 오답은 남는다."""
        started = self._start()
        tt, aid = answer_of(session._load, started["token"])
        self._post(
            ROUND_ANSWER_URL,
            {"token": started["token"], "choice_id": wrong_choice(started["question"], aid)},
        )

        stale = self._post(ROUND_FINISH_URL, {"token": started["token"]})
        self.assertEqual(stale.status_code, 400)
        self.assertIn((tt, aid), self._mistakes())

    def test_someone_elses_round_token_writes_only_to_the_answerer(self):
        """판 토큰은 계정에 안 묶인다. 남의 토큰으로 틀리면 답한 사람의 오답 노트에만 들어간다."""
        owner = self.user
        started = self._start()
        tt, aid = answer_of(session._load, started["token"])

        other = make_user("남")
        self.client.force_login(other)
        res = self._post(
            ROUND_ANSWER_URL,
            {"token": started["token"], "choice_id": wrong_choice(started["question"], aid)},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._mistakes(), {(tt, aid)})

        self.assertFalse(ReviewState.objects.filter(user=owner).exists())

        # 주인이 같은 토큰으로 다른 답을 내면 순번이 이미 가져가져 거절된다.
        self.client.force_login(owner)
        refused = self._post(ROUND_ANSWER_URL, {"token": started["token"], "choice_id": aid})
        self.assertEqual(refused.status_code, 400)
        self.assertFalse(ReviewState.objects.filter(user=owner).exists())

    def test_late_correct_answer_writes_nothing_mid_round(self):
        """제한 시간을 넘겨 맞힌 답(0점)은 틀린 것이 아니다. 도중에는 아무것도 안 남는다."""
        started = self._start()
        tt, aid = answer_of(session._load, started["token"])
        later = timezone.now() + timedelta(seconds=30)

        with mock.patch.object(session.timezone, "now", return_value=later):
            res = self._post(ROUND_ANSWER_URL, {"token": started["token"], "choice_id": aid})
        self.assertEqual(res.status_code, 200, res.content)
        result = res.json()["result"]
        self.assertTrue(result["correct"])
        self.assertFalse(result["in_time"])
        self.assertFalse(ReviewState.objects.filter(user=self.user).exists())

    def test_wrong_answer_on_a_word_hidden_mid_round_stays_out_of_sight(self):
        """문제를 받은 뒤 검수가 내려간 단어를 틀리면 줄은 남되 오답 노트와 복습에는 안 보인다."""
        started = self._start()
        tt, aid = answer_of(session._load, started["token"])
        Word.objects.filter(pk=aid).update(is_reviewed=False)

        res = self._post(
            ROUND_ANSWER_URL,
            {"token": started["token"], "choice_id": wrong_choice(started["question"], aid)},
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["result"]["answer_text"], "")

        self.assertTrue(
            ReviewState.objects.filter(user=self.user, target_id=aid, is_wrong=True).exists()
        )
        self.assertNotIn((tt, aid), self._mistakes())
        self.assertEqual(review.count_due(self.user), 0)


# ---- 학습 묶음의 틀린 단어 몫 ----


def quota_of(size: int) -> int:
    return max(1, size // 2)


class PickWordsQuotaEdgeTest(TestCase):
    """_pick_words: 틀린 것은 절반까지 먼저, 안 본 것과 오래된 것 다음, 모자라면 남은 틀린 것."""

    def setUp(self):
        cache.clear()
        self.user = make_user("몫")

    def _state(self, ids, *, wrong: bool, days_ago: int | None = None) -> None:
        last = None if days_ago is None else timezone.now() - timedelta(days=days_ago)
        ReviewState.objects.bulk_create(
            ReviewState(
                user=self.user,
                target_type=quiz.TARGET_WORD,
                target_id=pk,
                is_wrong=wrong,
                last_correct_at=last,
            )
            for pk in ids
        )

    def _pick(self, size: int, seen=()) -> list[int]:
        ids = [w.pk for w in daily_study._pick_words(self.user.pk, size, set(seen))]
        self.assertEqual(len(ids), len(set(ids)), f"겹쳐 뽑았다: {ids}")
        return ids

    def test_no_wrong_words_unseen_first_then_oldest(self):
        """틀린 것이 0 이면 안 본 것 다음 오래된 순서다. 남는 틀린 것 채우기가 끼지 않는다."""
        words = seed_words(13)
        unseen, old = words[:3], words[3:]
        for i, w in enumerate(old):
            self._state([w.pk], wrong=False, days_ago=100 - i)

        picked = self._pick(5)
        self.assertEqual(set(picked[:3]), {w.pk for w in unseen})
        self.assertEqual(picked[3:], [old[0].pk, old[1].pk])

    def test_single_wrong_word_is_always_in_for_every_size(self):
        """틀린 것이 하나면 묶음 크기가 1 이든 5 든 반드시 들어간다."""
        words = seed_words(20)
        self._state([words[7].pk], wrong=True)
        for size in (1, 2, 3, 5):
            with self.subTest(size=size):
                picked = self._pick(size)
                self.assertEqual(len(picked), size)
                self.assertIn(words[7].pk, picked)

    def test_many_wrong_words_take_exactly_the_quota_for_every_size(self):
        """틀린 것이 넉넉하면 묶음마다 정확히 max(1, size//2) 개다."""
        words = seed_words(60)
        wrong = {w.pk for w in words[:30]}
        self._state(wrong, wrong=True)
        for size in (1, 2, 3, 4, 5, 6):
            with self.subTest(size=size):
                picked = self._pick(size)
                self.assertEqual(len(picked), size)
                self.assertEqual(len(wrong & set(picked)), quota_of(size))

    def test_wrong_words_with_an_old_correct_time_do_not_take_the_old_slots(self):
        """한때 맞혔다가 다시 틀린 단어(마지막 맞힌 때가 오래됨)가 오래된 것 자리로 새지 않는다.

        안 본 것이 없고, 틀린 것이 오래된 것보다 더 오래전에 맞힌 것일 때 걸린다.
        """
        words = seed_words(20)
        wrong, old = words[:10], words[10:]
        self._state([w.pk for w in wrong], wrong=True, days_ago=60)
        self._state([w.pk for w in old], wrong=False, days_ago=30)

        picked = set(self._pick(5))
        self.assertEqual(len(picked & {w.pk for w in wrong}), 2)
        self.assertEqual(len(picked & {w.pk for w in old}), 3)

    def test_old_words_come_before_the_spare_wrong_ones(self):
        """안 본 것 하나, 오래된 것 하나뿐이면 그 둘을 넣고 나머지 세 자리만 틀린 것으로 채운다."""
        words = seed_words(12)
        wrong, unseen, old = words[:10], words[10], words[11]
        self._state([w.pk for w in wrong], wrong=True)
        self._state([old.pk], wrong=False, days_ago=40)

        picked = set(self._pick(5))
        self.assertIn(unseen.pk, picked)
        self.assertIn(old.pk, picked)
        self.assertEqual(len(picked & {w.pk for w in wrong}), 3)

    def test_hidden_and_seen_wrong_words_are_never_picked_even_as_spare(self):
        """검수가 내려간 틀린 단어와 이번 판에 이미 본 틀린 단어는 몫에도, 남는 자리 채우기에도 안 든다."""
        words = seed_words(8)
        hidden, seen, ok = words[:3], words[3:5], words[5:]
        self._state([w.pk for w in words], wrong=True)
        Word.objects.filter(pk__in=[w.pk for w in hidden]).update(is_reviewed=False)

        picked = self._pick(5, seen={w.pk for w in seen})
        self.assertEqual(set(picked), {w.pk for w in ok})

    def test_fewer_words_than_the_chunk_returns_what_there_is(self):
        """단어가 묶음보다 적으면 있는 만큼만, 겹치지 않게 준다. 하나도 안 틀려도, 하나만, 전부 틀려도."""
        words = seed_words(3)
        ids = {w.pk for w in words}
        self.assertEqual(set(self._pick(5)), ids)

        self._state([words[0].pk], wrong=True)
        self.assertEqual(set(self._pick(5)), ids)

        self._state([w.pk for w in words[1:]], wrong=True)
        self.assertEqual(set(self._pick(5)), ids)


class DailyChunkWrongCountTest(_ApiMixin, TestCase):
    """실제 일일공부에서 묶음마다 틀린 단어가 몇 개 들어가는가. 길이 셋 모두."""

    def setUp(self):
        cache.clear()
        self.words = seed_words(200)

    def _user_with_wrong(self, wrong_ids):
        # 표시 이름은 대소문자 무시 유일이라 subTest 마다 다르게 준다.
        user = make_user(f"묶음{uuid4().hex[:6]}")
        ReviewState.objects.bulk_create(
            ReviewState(user=user, target_type=quiz.TARGET_WORD, target_id=pk, is_wrong=True)
            for pk in wrong_ids
        )
        self.client.force_login(user)
        return user

    def _walk_learning(self, user, length: str) -> DailyStudy:
        """학습분을 모두 맞혀 지나간다. 지나간 판을 돌려준다."""
        res = self._post(DAILY_URL, {"length": length})
        self.assertEqual(res.status_code, 201, res.content)
        token = res.json()["token"]
        study = DailyStudy.objects.get(user=user)
        while daily_study._now_chunk(study) is not None:
            _tt, aid = answer_of(daily_study._load, token)
            res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
            self.assertEqual(res.status_code, 200, res.content)
            token = res.json()["token"]
            self.assertIsNotNone(token)
            study.refresh_from_db()
        return study

    def _chunks(self, study: DailyStudy) -> list[list[int]]:
        size = study.chunk_size
        ids = study.learned_ids
        return [ids[i : i + size] for i in range(0, len(ids), size)]

    def test_many_wrong_words_each_chunk_holds_exactly_the_quota(self):
        """틀린 단어가 넉넉해도 묶음마다 절반(짧은 판은 1, 중간·긴 판은 2)만 들어간다."""
        wrong = {w.pk for w in self.words[:80]}
        for length in (StudyLength.SHORT, StudyLength.MEDIUM, StudyLength.LONG):
            with self.subTest(length=length):
                plan = daily_study.plan_of(length)
                user = self._user_with_wrong(wrong)
                study = self._walk_learning(user, length)
                self.assertEqual(
                    (study.chunk_size, study.chunk_count), (plan.chunk_size, plan.chunk_count)
                )
                chunks = self._chunks(study)
                self.assertEqual(len(chunks), plan.chunk_count)
                self.assertEqual(len(set(study.learned_ids)), len(study.learned_ids))
                for i, chunk in enumerate(chunks):
                    self.assertEqual(len(chunk), plan.chunk_size)
                    self.assertEqual(
                        len(wrong & set(chunk)), quota_of(plan.chunk_size), f"{i} 번째 묶음 {chunk}"
                    )
                # 카드 직후 맞힌 틀린 단어는 그대로 남는다.
                seen_wrong = wrong & set(study.learned_ids)
                self.assertEqual(
                    ReviewState.objects.filter(
                        user=user, target_id__in=seen_wrong, is_wrong=True
                    ).count(),
                    len(seen_wrong),
                )

    def test_single_wrong_word_lands_in_the_first_chunk(self):
        """틀린 단어가 하나면 길이와 무관하게 첫 묶음(오늘의 단어)에 들어간다."""
        target = self.words[42].pk
        for length in (StudyLength.SHORT, StudyLength.MEDIUM, StudyLength.LONG):
            with self.subTest(length=length):
                user = self._user_with_wrong([target])
                study = self._walk_learning(user, length)
                chunks = self._chunks(study)
                self.assertIn(target, chunks[0])
                self.assertEqual(study.learned_ids.count(target), 1)

    def test_tiny_database_all_wrong_still_fills_whole_chunks(self):
        """단어가 12 개뿐이고 모두 틀린 것이면 중간 판은 묶음 둘(5+5)을 겹치지 않게 다 틀린 것으로 채운다."""
        keep = [w.pk for w in self.words[:12]]
        Word.objects.exclude(pk__in=keep).delete()
        user = self._user_with_wrong(keep)
        study = self._walk_learning(user, StudyLength.MEDIUM)

        self.assertEqual((study.chunk_size, study.chunk_count), (5, 2))
        chunks = self._chunks(study)
        self.assertEqual([len(c) for c in chunks], [5, 5])
        self.assertEqual(len(set(study.learned_ids)), 10)
        self.assertTrue(set(study.learned_ids) <= set(keep))

    def test_tiny_database_cannot_fill_a_second_chunk(self):
        """단어가 7 개면 중간 판은 묶음 하나만 계획한다. 틀린 것 넷이어도 몫 둘 + 안 본 셋 = 다섯."""
        Word.objects.exclude(pk__in=[w.pk for w in self.words[:7]]).delete()
        wrong = {w.pk for w in self.words[:4]}
        user = self._user_with_wrong(wrong)
        study = self._walk_learning(user, StudyLength.MEDIUM)

        self.assertEqual((study.chunk_size, study.chunk_count), (5, 1))
        self.assertEqual(len(study.learned_ids), 5)
        self.assertEqual(len(wrong & set(study.learned_ids)), 2)


class DailyPreviewQuotaTest(_ApiMixin, TestCase):
    """오늘의 단어(시작 전 GET /daily/ 의 today_words)도 같은 몫을 지킨다."""

    def setUp(self):
        cache.clear()
        self.words = seed_words(80)
        self.wrong = {w.pk for w in self.words[:40]}
        self.user = make_user("미리")
        ReviewState.objects.bulk_create(
            ReviewState(user=self.user, target_type=quiz.TARGET_WORD, target_id=pk, is_wrong=True)
            for pk in self.wrong
        )
        self.client.force_login(self.user)

    def _set_length(self, length: str) -> None:
        self.user.daily_length = length
        self.user.save(update_fields=["daily_length"])

    def _today_words(self) -> list[int]:
        res = self.client.get(DAILY_URL)
        self.assertEqual(res.status_code, 200, res.content)
        return [w["id"] for w in res.json()["today_words"]]

    def test_preview_holds_the_quota_and_becomes_the_first_chunk(self):
        """짧은·중간 판의 오늘의 단어는 몫(1, 2)만큼 틀린 것을 담고, 시작하면 그대로 첫 묶음이다."""
        for length in (StudyLength.SHORT, StudyLength.MEDIUM):
            with self.subTest(length=length):
                DailyStudy.objects.filter(user=self.user).delete()
                DailyPreview.objects.filter(user=self.user).delete()
                self._set_length(length)
                size = daily_study.plan_of(length).chunk_size
                preview = self._today_words()
                self.assertEqual(len(preview), size)
                self.assertEqual(len(self.wrong & set(preview)), quota_of(size))

                started = self._post(DAILY_URL, {"length": length}).json()
                self.assertEqual([w["id"] for w in started["learning"]], preview)

    def test_growing_from_short_to_medium_keeps_the_quota(self):
        """5분(2개)으로 미리 뽑은 뒤 10분(5개)으로 바꾸면 앞 둘을 지키고 채워도 틀린 것은 둘이다."""
        self._set_length(StudyLength.SHORT)
        short = self._today_words()
        self._set_length(StudyLength.MEDIUM)
        medium = self._today_words()
        self.assertEqual(medium[:2], short)
        self.assertEqual(len(medium), 5)
        self.assertEqual(len(self.wrong & set(medium)), 2)

    def test_hidden_wrong_words_never_reach_the_preview(self):
        """틀린 단어가 전부 검수에서 내려가면 오늘의 단어와 학습 카드에 하나도 안 나온다."""
        Word.objects.filter(pk__in=self.wrong).update(is_reviewed=False)
        self._set_length(StudyLength.MEDIUM)
        preview = self._today_words()
        self.assertEqual(len(preview), 5)
        self.assertFalse(self.wrong & set(preview))

        started = self._post(DAILY_URL, {"length": StudyLength.MEDIUM}).json()
        self.assertFalse(self.wrong & {w["id"] for w in started["learning"]})

    def test_preview_word_hidden_after_picking_is_refilled_within_the_quota(self):
        """미리 뽑은 틀린 단어가 내려가면 빠지고, 채운 자리에 들어오는 틀린 것도 몫 안이다."""
        self._set_length(StudyLength.MEDIUM)
        preview = self._today_words()
        dropped = [pk for pk in preview if pk in self.wrong]
        Word.objects.filter(pk__in=dropped).update(is_reviewed=False)

        again = self._today_words()
        self.assertEqual(len(again), 5)
        self.assertFalse(set(dropped) & set(again))
        self.assertLessEqual(len(self.wrong & set(again)), 2)


# ---- 일일공부 keep_wrong: 이어 하기, 묶음 끝, 자정 ----


class DailyKeepWrongResumeTest(_ApiMixin, TestCase):
    """keep_wrong 은 지금 묶음의 카드 단어만. 이어 하기·묶음 마지막 문제·자정 뒤에도."""

    def setUp(self):
        cache.clear()
        seed_words(120)
        self.user = make_user("이어")
        self.client.force_login(self.user)

    def _study(self) -> DailyStudy:
        return DailyStudy.objects.get(user=self.user)

    def _plant_wrong(self, target_id: int) -> ReviewState:
        row, _ = ReviewState.objects.update_or_create(
            user=self.user,
            target_type=quiz.TARGET_WORD,
            target_id=target_id,
            defaults={"is_wrong": True, "streak": 0, "last_correct_at": None},
        )
        return row

    def _answer_right(self, token: str) -> dict:
        _tt, aid = answer_of(daily_study._load, token)
        res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["result"]["correct"])
        return res.json()

    def _is_wrong(self, target_id: int) -> bool:
        return ReviewState.objects.get(
            user=self.user, target_type=quiz.TARGET_WORD, target_id=target_id
        ).is_wrong

    def test_resumed_token_still_keeps_the_card_word(self):
        """나갔다 들어와(GET /daily/) 받은 토큰으로 카드 단어를 맞혀도 오답에 남는다."""
        self._post(DAILY_URL, {"length": StudyLength.SHORT})
        token = self.client.get(DAILY_URL).json()["token"]
        tt, aid = answer_of(daily_study._load, token)
        self.assertEqual(tt, quiz.TARGET_WORD)
        self.assertIn(aid, self._study().learned_ids)
        self._plant_wrong(aid)

        self._answer_right(token)
        self.assertTrue(self._is_wrong(aid))
        self.assertIn((tt, aid), self._mistakes())

    def test_resume_after_the_saved_answer_was_hidden_keeps_the_new_card_word(self):
        """저장된 문제의 정답이 내려가 이어 하기가 새로 낸 문제도 묶음 안이라 맞혀도 남는다."""
        opened = self._post(DAILY_URL, {"length": StudyLength.MEDIUM}).json()
        _tt, first = answer_of(daily_study._load, opened["token"])
        Word.objects.filter(pk=first).update(is_reviewed=False)

        token = self.client.get(DAILY_URL).json()["token"]
        _tt, aid = answer_of(daily_study._load, token)
        self.assertNotEqual(aid, first)
        self.assertIn(aid, daily_study._study_scope(self._study()))
        self._plant_wrong(aid)

        self._answer_right(token)
        self.assertTrue(self._is_wrong(aid))

    def test_last_question_of_a_chunk_is_judged_by_its_own_chunk(self):
        """묶음의 마지막 문제는 답하는 순간 순번이 다음 묶음으로 넘어가도 지금 묶음 기준으로 남는다."""
        token = self._post(DAILY_URL, {"length": StudyLength.SHORT}).json()["token"]
        token = self._answer_right(token)["token"]  # 첫 묶음의 첫 문제

        study = self._study()
        self.assertEqual(study.answered, study.chunk_size - 1)
        _tt, aid = answer_of(daily_study._load, token)
        self.assertIn(aid, study.learned_ids[: study.chunk_size])
        self._plant_wrong(aid)

        self._answer_right(token)
        self.assertTrue(self._is_wrong(aid))

    def test_last_question_of_the_learning_part_still_keeps(self):
        """학습분의 맨 마지막 문제(뒤에 묶음이 없다)도 카드 직후라 맞혀도 남는다."""
        token = self._post(DAILY_URL, {"length": StudyLength.SHORT}).json()["token"]
        study = self._study()
        for _ in range(study.chunk_size * study.chunk_count - 1):
            token = self._answer_right(token)["token"]

        _tt, aid = answer_of(daily_study._load, token)
        self.assertIn(aid, daily_study._study_scope(self._study()))
        self._plant_wrong(aid)
        self._answer_right(token)
        self.assertTrue(self._is_wrong(aid))
        self.assertIsNone(daily_study._now_chunk(self._study()))

    def test_after_midnight_a_card_word_asked_in_the_rest_part_is_cleared(self):
        """어제 판을 자정 뒤에 이어 풀 때, 학습분 뒤 전체에서 나온 문제가 어제 카드 단어여도 맞히면 빠진다."""
        token = self._post(DAILY_URL, {"length": StudyLength.SHORT}).json()["token"]
        study = self._study()
        for _ in range(study.chunk_size * study.chunk_count):
            token = self._answer_right(token)["token"]

        tt, aid = answer_of(daily_study._load, token)
        self.assertEqual(tt, quiz.TARGET_WORD)
        study = self._study()
        if aid not in study.learned_ids:
            study.learned_ids = [aid, *study.learned_ids[1:]]
        study.day = study.day - timedelta(days=1)
        study.save(update_fields=["learned_ids", "day"])
        self._plant_wrong(aid)

        self._answer_right(token)
        self.assertFalse(self._is_wrong(aid))
        self.assertNotIn((quiz.TARGET_WORD, aid), self._mistakes())

    def test_replayed_old_token_changes_nothing(self):
        """이미 쓴 토큰으로 다시 맞혀도 거절되고 오답 줄은 손대지 않는다."""
        token = self._post(DAILY_URL, {"length": StudyLength.SHORT}).json()["token"]
        self._answer_right(token)
        _tt, aid = answer_of(daily_study._load, token)
        row = self._plant_wrong(aid)

        res = self._post(DAILY_ANSWER_URL, {"token": token, "choice_id": aid})
        self.assertEqual(res.status_code, 400)
        after = ReviewState.objects.get(pk=row.pk)
        self.assertTrue(after.is_wrong)
        self.assertIsNone(after.last_correct_at)


# ---- 한 판: 상한 직전 ----


class RoundCapEdgeTest(_ApiMixin, TestCase):
    """60 번째 답이 넘기기일 때, 넘기기를 다 쓴 때, 같은 답을 다시 보낼 때."""

    CAP = 60

    def setUp(self):
        cache.clear()
        self.words = seed_words(60)
        self.user = make_user("직전")
        self.client.force_login(self.user)

    def _token_with(self, answered: int, skips: int = 0) -> tuple[str, dict]:
        """이미 answered 개를 (맞힌 것으로) 받은 판 토큰과 그 판의 지금 문제."""
        started = self._post(ROUND_URL, {}).json()
        state = session._load(started["token"])
        fill = self.words[-1].pk
        state["a"] = [["meaning", quiz.TARGET_WORD, fill, 1, 0, 1000, 1]] * answered
        state["sk"] = skips
        return session._sign(state), started["question"]

    def test_fifty_ninth_answer_still_gets_a_question(self):
        """상한 하나 앞(59 번째)의 답 뒤에는 아직 문제가 나온다."""
        token, _q = self._token_with(self.CAP - 2)
        _tt, aid = answer_of(session._load, token)
        data = self._post(ROUND_ANSWER_URL, {"token": token, "choice_id": aid}).json()
        self.assertIsNotNone(data["question"])
        self.assertFalse(data["finished"])

    def test_skip_as_the_sixtieth_answer_ends_the_round(self):
        """60 번째 답이 넘기기여도 판이 끝나고, 오답 노트에는 아무것도 안 남는다."""
        token, _q = self._token_with(self.CAP - 1)
        res = self._post(ROUND_ANSWER_URL, {"token": token, "skip": True})
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["result"]["skipped"])
        self.assertIsNone(data["question"])
        self.assertTrue(data["finished"])
        self.assertFalse(ReviewState.objects.filter(user=self.user).exists())

        more = self._post(ROUND_ANSWER_URL, {"token": data["token"], "skip": True})
        self.assertEqual(more.status_code, 400)

        finished = self._post(ROUND_FINISH_URL, {"token": data["token"]})
        self.assertEqual(finished.status_code, 200, finished.content)
        self.assertEqual(finished.json()["answered"], self.CAP)
        self.assertEqual(finished.json()["skipped"], 1)

    def test_skip_refused_when_skips_are_used_up_then_a_real_answer_ends(self):
        """넘기기를 다 쓴 판의 60 번째 넘기기는 거절되고, 같은 토큰으로 낸 진짜 답이 판을 끝낸다."""
        token, _q = self._token_with(self.CAP - 1, skips=session.MAX_SKIPS)
        refused = self._post(ROUND_ANSWER_URL, {"token": token, "skip": True})
        self.assertEqual(refused.status_code, 400)

        _tt, aid = answer_of(session._load, token)
        data = self._post(ROUND_ANSWER_URL, {"token": token, "choice_id": aid}).json()
        self.assertIsNone(data["question"])
        self.assertTrue(data["finished"])

    def test_resent_sixtieth_wrong_answer_gives_the_same_finished_reply(self):
        """끝내는 답(틀림)을 다시 보내면 같은 응답이 오고 오답은 하나다."""
        token, question = self._token_with(self.CAP - 1)
        tt, aid = answer_of(session._load, token)
        body = {"token": token, "choice_id": wrong_choice(question, aid)}

        first = self._post(ROUND_ANSWER_URL, body).json()
        again = self._post(ROUND_ANSWER_URL, body).json()
        self.assertEqual(again, first)
        self.assertTrue(first["finished"])
        self.assertEqual(self._mistakes(), {(tt, aid)})
