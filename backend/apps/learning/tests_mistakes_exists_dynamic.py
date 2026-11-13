"""오답 노트의 "보여줄 수 있는 대상" 조건을 IN 하위 질의에서 EXISTS 로 바꾼 것.

결과는 바뀌면 안 된다. 그래서 옛 조건(`IN (SELECT id ...)` 둘을 OR 로 묶은
것)을 이 파일에 그대로 옮겨 두고, 같은 데이터에서 새 조건과 줄 id, 순서,
개수, 페이지 나눔이 같은지 비교한다.

데이터는 일부러 지저분하게 만든다. 단어와 문장이 섞이고, 검수가 풀리고,
대상이 지워지고, 같은 id 가 단어 표와 문장 표에 동시에 있고, 대상 종류
칸에 word/sentence 가 아닌 값이 들어 있다.
"""

from __future__ import annotations

import random
import secrets
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase

from apps.vocab.models import Sentence, SentenceKind, Word
from apps.vocab.quiz import TARGET_SENTENCE, TARGET_WORD

from .models import ReviewState
from .views_history import _visible_targets

URL = "/api/learning/mistakes/"
PAGE_SIZE = 20


def _old_visible_targets() -> Q:
    """origin/main 의 옛 구현을 그대로 옮긴 것. 비교 기준이다."""
    return Q(
        target_type=TARGET_WORD,
        target_id__in=Word.objects.visible().values("pk"),
    ) | Q(
        target_type=TARGET_SENTENCE,
        target_id__in=Sentence.objects.visible().values("pk"),
    )


def make_user(name: str):
    return get_user_model().objects.create_user(
        email=f"{name}-{uuid4().hex[:6]}@example.com",
        password=secrets.token_urlsafe(16),
        display_name=f"{name}{uuid4().hex[:4]}",
    )


def make_word(reviewed: bool = True, pk: int | None = None) -> Word:
    tag = uuid4().hex[:10]
    return Word.objects.create(
        pk=pk,
        term=f"w{tag}",
        meaning=f"뜻 {tag}",
        description="설명",
        is_reviewed=reviewed,
    )


def make_sentence(reviewed: bool = True, pk: int | None = None) -> Sentence:
    tag = uuid4().hex[:10]
    return Sentence.objects.create(
        pk=pk,
        text=f"This is {tag}.",
        translation=f"해석 {tag}",
        kind=SentenceKind.PHRASE,
        is_reviewed=reviewed,
    )


def mark(user, target_type: str, target_id: int, wrong: bool = True) -> ReviewState:
    return ReviewState.objects.create(
        user=user, target_type=target_type, target_id=target_id, is_wrong=wrong
    )


class VisibleTargetsEquivalenceTest(TestCase):
    """같은 데이터에서 옛 조건과 새 조건이 같은 줄을 고르는지."""

    def _ids(self, q: Q, **filters) -> list[int]:
        return list(
            ReviewState.objects.filter(**filters)
            .filter(q)
            .order_by("-pk")
            .values_list("pk", flat=True)
        )

    def assertSame(self, **filters) -> list[int]:
        old = self._ids(_old_visible_targets(), **filters)
        new = self._ids(_visible_targets(), **filters)
        self.assertEqual(new, old)
        # 부정(exclude)도 같아야 한다. NULL 이 끼면 NOT IN 과 NOT EXISTS 가
        # 갈리는 자리라 함께 본다.
        old_ex = list(
            ReviewState.objects.filter(**filters)
            .exclude(_old_visible_targets())
            .order_by("-pk")
            .values_list("pk", flat=True)
        )
        new_ex = list(
            ReviewState.objects.filter(**filters)
            .exclude(_visible_targets())
            .order_by("-pk")
            .values_list("pk", flat=True)
        )
        self.assertEqual(new_ex, old_ex)
        return new

    def test_same_id_in_both_tables_follows_target_type(self):
        """같은 id 가 단어·문장 양쪽에 있으면 종류 칸이 어느 표를 볼지 정한다.

        종류 조건을 빼먹으면 검수 안 된 문장 줄이 같은 id 의 검수된 단어
        덕에 살아난다.
        """
        user = make_user("양쪽")
        base = 7_000_000
        # (단어 검수, 문장 검수)
        combos = [(True, False), (False, True), (True, True), (False, False)]
        expect = []
        for i, (w_ok, s_ok) in enumerate(combos):
            pk = base + i
            make_word(reviewed=w_ok, pk=pk)
            make_sentence(reviewed=s_ok, pk=pk)
            w_row = mark(user, TARGET_WORD, pk)
            s_row = mark(user, TARGET_SENTENCE, pk)
            if w_ok:
                expect.append(w_row.pk)
            if s_ok:
                expect.append(s_row.pk)

        got = self.assertSame(user=user, is_wrong=True)

        self.assertEqual(sorted(got), sorted(expect))

    def test_unknown_target_type_never_matches(self):
        """종류 칸에 word/sentence 가 아닌 값이 있으면 어느 표가 검수했든 빠진다."""
        user = make_user("이상한종류")
        w = make_word()
        s = make_sentence()
        for kind in ["Word", "SENTENCE", "", "words", "error", "word ", " sentence"]:
            mark(user, kind, w.pk)
            mark(user, kind, s.pk)
        ok = mark(user, TARGET_WORD, w.pk)

        got = self.assertSame(user=user, is_wrong=True)

        self.assertEqual(got, [ok.pk])

    def test_unreviewed_deleted_and_huge_ids_drop_out(self):
        """검수가 풀린 것, 지워진 것, 표에 없는 큰 id 는 빠진다."""
        user = make_user("빠짐")
        keep_w = make_word()
        keep_s = make_sentence()
        unrev_w = make_word()
        unrev_s = make_sentence()
        gone_w = make_word()
        gone_s = make_sentence()
        rows = {
            "keep_w": mark(user, TARGET_WORD, keep_w.pk),
            "keep_s": mark(user, TARGET_SENTENCE, keep_s.pk),
        }
        mark(user, TARGET_WORD, unrev_w.pk)
        mark(user, TARGET_SENTENCE, unrev_s.pk)
        mark(user, TARGET_WORD, gone_w.pk)
        mark(user, TARGET_SENTENCE, gone_s.pk)
        mark(user, TARGET_WORD, 2**63 - 1)
        mark(user, TARGET_SENTENCE, 2**63 - 1)
        mark(user, TARGET_WORD, 0)

        # 기록이 쌓인 뒤에 검수를 풀고 지운다.
        Word.objects.filter(pk=unrev_w.pk).update(is_reviewed=False)
        Sentence.objects.filter(pk=unrev_s.pk).update(is_reviewed=False)
        gone_w.delete()
        gone_s.delete()

        got = self.assertSame(user=user, is_wrong=True)

        self.assertEqual(sorted(got), sorted(r.pk for r in rows.values()))

    def test_randomized_mixed_data_matches_old(self):
        """무작위로 섞은 데이터에서 사람마다, 그리고 표 전체로 옛 조건과 같다."""
        rng = random.Random(20261113)
        words = [make_word(reviewed=rng.random() < 0.6) for _ in range(40)]
        sentences = [make_sentence(reviewed=rng.random() < 0.6) for _ in range(40)]
        users = [make_user(f"u{i}") for i in range(4)]
        kinds = [TARGET_WORD, TARGET_SENTENCE, "error", ""]
        seen = set()
        for _ in range(400):
            user = rng.choice(users)
            kind = rng.choices(kinds, weights=[45, 45, 5, 5])[0]
            pool = rng.choice([words, sentences])
            target_id = rng.choice(pool).pk if rng.random() < 0.9 else 10**9
            key = (user.pk, kind, target_id)
            if key in seen:
                continue
            seen.add(key)
            mark(user, kind, target_id, wrong=rng.random() < 0.7)

        for w in rng.sample(words, 5):
            w.delete()
        for s in rng.sample(sentences, 5):
            Sentence.objects.filter(pk=s.pk).update(is_reviewed=not s.is_reviewed)

        total = 0
        for user in users:
            total += len(self.assertSame(user=user, is_wrong=True))
            self.assertSame(user=user)
        self.assertSame()
        # 비교가 빈 목록끼리 같아서 통과한 것이 아님을 확인한다.
        self.assertGreater(total, 20)

    def test_query_uses_exists_not_in_subquery(self):
        """속도 개선의 핵심. IN 하위 질의로 되돌아가면 큰 표에서 다시 느려진다."""
        sql = str(ReviewState.objects.filter(_visible_targets()).query).upper()

        self.assertEqual(sql.count("EXISTS"), 2)
        self.assertNotIn("IN (SELECT", sql)


class MistakesApiTest(TestCase):
    """HTTP 로 본 오답 노트. 페이지 나눔이 옛 조건으로 자른 것과 같은지."""

    def setUp(self):
        self.user = make_user("오답")
        self.client.force_login(self.user)

    def _expected(self) -> list[int]:
        return list(
            ReviewState.objects.filter(user=self.user, is_wrong=True)
            .filter(_old_visible_targets())
            .order_by("-pk")
            .values_list("pk", flat=True)
        )

    def _seed(self, visible: int) -> None:
        """보이는 줄 `visible` 개 사이사이에 안 보여야 할 줄을 끼운다."""
        other = make_user("남")
        for i in range(visible):
            if i % 2:
                target = make_sentence()
                kind = TARGET_SENTENCE
            else:
                target = make_word()
                kind = TARGET_WORD
            mark(self.user, kind, target.pk)
            # 같은 대상을 남이 틀린 기록
            mark(other, kind, target.pk)
            # 미검수 대상
            hidden = make_word(reviewed=False) if i % 2 else make_sentence(False)
            mark(self.user, TARGET_WORD if i % 2 else TARGET_SENTENCE, hidden.pk)
            if i % 3 == 0:
                # 맞힌 것
                right = make_word()
                mark(self.user, TARGET_WORD, right.pk, wrong=False)

    def test_pages_match_old_filter_across_boundary(self):
        """45개면 20, 20, 5 로 나뉘고 각 페이지 id 가 옛 조건으로 자른 것과 같다."""
        self._seed(45)
        expected = self._expected()
        self.assertEqual(len(expected), 45)

        got: list[int] = []
        for page in (1, 2, 3):
            body = self.client.get(URL, {"page": page}).json()
            self.assertEqual(body["count"], 45)
            got.extend(r["id"] for r in body["results"])
            self.assertEqual(
                [r["id"] for r in body["results"]],
                expected[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
            )
        self.assertEqual(got, expected)
        self.assertIsNone(self.client.get(URL, {"page": 3}).json()["next"])

    def test_exactly_one_page_has_no_next(self):
        """딱 20개면 2페이지가 없다. 숨은 줄이 count 에 끼면 빈 2페이지가 생긴다."""
        self._seed(20)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 20)
        self.assertIsNone(body["next"])
        self.assertEqual(self.client.get(URL, {"page": 2}).status_code, 404)

    def test_bad_page_numbers_are_404_not_500(self):
        self._seed(3)
        for page in ("0", "-1", "999999", "abc", "9" * 30):
            with self.subTest(page=page):
                self.assertEqual(self.client.get(URL, {"page": page}).status_code, 404)

    def test_unreviewed_never_leaks_even_with_same_id_word(self):
        """미검수 문장이 같은 id 의 검수된 단어를 빌려 목록에 나오면 안 된다."""
        pk = 8_000_000
        make_word(reviewed=True, pk=pk)
        hidden = make_sentence(reviewed=False, pk=pk)
        mark(self.user, TARGET_SENTENCE, pk)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 0)
        self.assertNotIn(hidden.text, str(body))

    def test_other_users_rows_never_show(self):
        other = make_user("남")
        w = make_word()
        mark(other, TARGET_WORD, w.pk)

        body = self.client.get(URL).json()

        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])

    def test_requires_login(self):
        self.client.logout()

        self.assertIn(self.client.get(URL).status_code, (401, 403))
