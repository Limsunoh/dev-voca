"""추가 콘텐츠 묶음(seed_words_more / seed_sentences_more)을 깨뜨려 본다.

기존 SeedWordsTest / SeedSentencesTest 는 원래 명령만 돌린다. 새 명령은
`--reset` 이 없고 인자 표면이 달라서, 그쪽에서 확인한 성질이 여기서도
성립한다고 가정할 수 없다. 그래서 같은 질문(멱등·롤백·건너뜀·검수 게이트)을
새 명령에 직접 다시 던진다.

여기서 관심 있는 것은 리스트 내용이 아니라 **통로**다. 리스트 자체의 전수
검사는 tests.py 의 ALL_SEEDED / tests_sentences.py 의 ALL_SEEDED_SENTENCES 가
맡는다.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .management.commands.seed_sentences import SENTENCES as BASE_SENTENCES
from .management.commands.seed_sentences_more import SENTENCES as MORE_SENTENCES
from .management.commands.seed_words import WORDS as BASE_WORDS
from .management.commands.seed_words_more import WORDS as MORE_WORDS
from .models import LearningItem, Sentence, SentenceKind, Word


def run(command: str, *args: str) -> str:
    out = StringIO()
    call_command(command, *args, stdout=out, stderr=out)
    return out.getvalue()


class SeedWordsMoreCommandTest(TestCase):
    """새 단어 명령의 통로."""

    def test_seeds_all_rows_as_reviewed(self):
        """사람이 쓴 묶음이라 바로 노출된다 - 대신 전수 검사가 그 값을 지킨다."""
        run("seed_words_more")

        self.assertEqual(Word.objects.count(), len(MORE_WORDS))
        self.assertEqual(Word.objects.filter(is_reviewed=False).count(), 0)

    def test_is_idempotent(self):
        """두 번 돌려도 중복이 생기지 않는다."""
        run("seed_words_more")
        count = Word.objects.count()

        output = run("seed_words_more")

        self.assertEqual(Word.objects.count(), count)
        self.assertIn("건너뜀: 36개", output)

    def test_dry_run_saves_nothing(self):
        """--dry-run 은 한 건도 저장하면 안 된다."""
        output = run("seed_words_more", "--dry-run")

        self.assertEqual(Word.objects.count(), 0)
        self.assertIn("저장하지 않았습니다", output)

    def test_dry_run_after_real_run_reports_all_skipped(self):
        """이미 들어간 상태에서 --dry-run 은 '전부 있음' 으로 보고한다."""
        run("seed_words_more")

        output = run("seed_words_more", "--dry-run")

        self.assertIn("추가: 0개", output)
        self.assertEqual(Word.objects.count(), len(MORE_WORDS))

    def test_partial_failure_saves_nothing(self):
        """중간에 터지면 앞서 넣은 것까지 전부 롤백한다.

        절반만 들어간 채 남으면 다음 실행이 '이미 있네' 하고 건너뛰어
        빠진 단어가 영영 안 들어온다.
        """
        real_save = Word.save
        calls = {"n": 0}

        def fail_on_third(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("중간 실패")
            return real_save(self, *args, **kwargs)

        with patch.object(Word, "save", fail_on_third):
            with self.assertRaises(RuntimeError):
                run("seed_words_more")

        self.assertEqual(Word.objects.count(), 0, "앞의 2개가 남았다")

    def test_does_not_overwrite_hand_edited_word(self):
        """--reset 이 없으므로 사람이 고친 내용을 건드리면 안 된다."""
        term = MORE_WORDS[0][0]
        Word.objects.create(term=term, meaning="내가 고친 뜻", is_reviewed=True)

        run("seed_words_more")

        self.assertEqual(Word.objects.get(term=term).meaning, "내가 고친 뜻")

    def test_does_not_promote_pending_review(self):
        """검수 대기 단어를 승격시키면 안 된다.

        같은 단어가 AI 로 먼저 들어와 있을 수 있다. 시드가 그걸 True 로
        바꾸면 아무도 승인 안 한 뜻이 그대로 화면에 나간다.
        """
        term = MORE_WORDS[0][0]
        Word.objects.create(
            term=term, meaning="AI 가 만든 뜻", is_reviewed=False, source="AI 생성"
        )

        run("seed_words_more")

        word = Word.objects.get(term=term)
        self.assertFalse(word.is_reviewed, "검수 대기 단어가 승격됐다")
        self.assertEqual(word.meaning, "AI 가 만든 뜻")

    def test_rejects_unknown_option(self):
        """원래 명령에 있는 --reset 을 습관적으로 붙이면 조용히 무시되면 안 된다."""
        with self.assertRaises(CommandError):
            run("seed_words_more", "--reset")

    def test_new_words_carry_no_exam_flag(self):
        """새 단어는 정처기 표시가 없다 - 붙었다면 과목 없이 배지만 뜬다."""
        run("seed_words_more")

        self.assertEqual(Word.objects.filter(is_exam=True).count(), 0)
        self.assertEqual(Word.objects.exclude(exam_subject="").count(), 0)


class SeedSentencesMoreCommandTest(TestCase):
    """새 문장 명령의 통로."""

    def test_seeds_all_rows_as_reviewed(self):
        run("seed_sentences_more")

        self.assertEqual(Sentence.objects.count(), len(MORE_SENTENCES))
        self.assertEqual(Sentence.objects.filter(is_reviewed=False).count(), 0)

    def test_is_idempotent(self):
        run("seed_sentences_more")
        run("seed_sentences_more")

        self.assertEqual(Sentence.objects.count(), len(MORE_SENTENCES))

    def test_dry_run_saves_nothing(self):
        output = run("seed_sentences_more", "--dry-run")

        self.assertEqual(Sentence.objects.count(), 0)
        self.assertIn("저장하지 않았습니다", output)

    def test_partial_failure_saves_nothing(self):
        real_save = Sentence.save
        calls = {"n": 0}

        def fail_on_third(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("중간 실패")
            return real_save(self, *args, **kwargs)

        with patch.object(Sentence, "save", fail_on_third):
            with self.assertRaises(RuntimeError):
                run("seed_sentences_more")

        self.assertEqual(Sentence.objects.count(), 0)

    def test_does_not_overwrite_hand_edited_sentence(self):
        slug = MORE_SENTENCES[0][0]
        Sentence.objects.create(
            slug=slug, text="옛 문장", translation="내가 고친 해석", is_reviewed=True
        )

        run("seed_sentences_more")

        self.assertEqual(
            Sentence.objects.get(slug=slug).translation, "내가 고친 해석"
        )

    def test_does_not_promote_pending_review(self):
        slug = MORE_SENTENCES[0][0]
        Sentence.objects.create(
            slug=slug, text="t", translation="AI 해석", is_reviewed=False
        )

        run("seed_sentences_more")

        self.assertFalse(Sentence.objects.get(slug=slug).is_reviewed)

    def test_rejects_unknown_option(self):
        with self.assertRaises(CommandError):
            run("seed_sentences_more", "--reset")


class SeedOrderIndependenceTest(TestCase):
    """빈 DB 에서 순서를 바꿔 돌려도 결과가 같아야 한다.

    시드는 배포마다 돈다. 순서에 따라 개수가 갈리면 어느 서버는 단어가
    모자란 채로 뜬다.
    """

    def _snapshot(self) -> set[tuple]:
        return set(
            Word.objects.values_list(
                "term", "meaning", "category", "difficulty", "is_reviewed"
            )
        )

    def test_words_order_does_not_change_result(self):
        run("seed_words")
        run("seed_words_more")
        forward = self._snapshot()

        Word.objects.all().delete()
        run("seed_words_more")
        run("seed_words")
        backward = self._snapshot()

        self.assertEqual(forward, backward)
        self.assertEqual(len(forward), len(BASE_WORDS) + len(MORE_WORDS))

    def test_sentences_order_does_not_change_result(self):
        run("seed_sentences")
        run("seed_sentences_more")
        forward = set(Sentence.objects.values_list("slug", "text", "kind"))

        Sentence.objects.all().delete()
        run("seed_sentences_more")
        run("seed_sentences")
        backward = set(Sentence.objects.values_list("slug", "text", "kind"))

        self.assertEqual(forward, backward)

    def test_seed_sentences_does_not_delete_the_new_batch(self):
        """seed_sentences 는 RETIRED_SLUGS 를 지운다. 새 묶음이 걸리면 안 된다.

        나중에 은퇴 목록에 slug 를 넣을 때 새 묶음의 것을 실수로 적으면,
        두 명령을 순서대로 돌리는 것만으로 문장이 조용히 사라진다.
        """
        run("seed_sentences_more")
        count = Sentence.objects.count()

        run("seed_sentences")

        self.assertEqual(
            Sentence.objects.filter(
                slug__in=[s[0] for s in MORE_SENTENCES]
            ).count(),
            count,
            "새 문장이 은퇴 처리로 지워졌다",
        )

    def test_word_and_exam_seeds_do_not_collide(self):
        """세 단어 명령을 다 돌려도 term 충돌로 터지지 않는다."""
        run("seed_words")
        run("seed_exam_words")
        run("seed_words_more")

        terms = list(Word.objects.values_list("term", flat=True))
        self.assertEqual(len(terms), len(set(terms)))

    def test_mark_exam_scope_leaves_new_words_alone(self):
        """정처기 표시 명령이 새 단어에 손대면 안 된다."""
        run("seed_words")
        run("seed_exam_words")
        run("seed_words_more")

        run("mark_exam_scope")

        marked = Word.objects.filter(
            term__in=[w[0] for w in MORE_WORDS], is_exam=True
        )
        self.assertEqual(
            list(marked.values_list("term", flat=True)),
            [],
            "새 단어에 정처기 표시가 붙었다",
        )


class NewContentVisibilityTest(TestCase):
    """새 데이터가 실제 조회 경로에서 보이고, 미검수면 사라지는지."""

    @classmethod
    def setUpTestData(cls):
        run("seed_words")
        run("seed_words_more")
        run("seed_sentences")
        run("seed_sentences_more")
        cls.new_terms = [w[0] for w in MORE_WORDS]
        cls.new_slugs = [s[0] for s in MORE_SENTENCES]

    def test_new_word_is_listed(self):
        term = self.new_terms[0]
        res = self.client.get("/api/vocab/words/", {"search": term})

        self.assertEqual(res.status_code, 200)
        self.assertIn(term, [w["term"] for w in res.json()["results"]])

    def test_new_word_detail_returns_200(self):
        word = Word.objects.get(term=self.new_terms[0])

        res = self.client.get(f"/api/vocab/words/{word.pk}/")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["term"], word.term)

    def test_unreviewing_a_new_word_removes_it_everywhere(self):
        """검수 게이트가 새 데이터에도 그대로 걸린다."""
        word = Word.objects.get(term=self.new_terms[0])
        Word.objects.filter(pk=word.pk).update(is_reviewed=False)

        listed = self.client.get("/api/vocab/words/", {"search": word.term}).json()
        detail = self.client.get(f"/api/vocab/words/{word.pk}/")

        self.assertNotIn(word.term, [w["term"] for w in listed["results"]])
        self.assertEqual(detail.status_code, 404)

    def test_unreviewing_a_new_word_removes_it_from_quiz_pool(self):
        """미검수 단어가 문제로 나오면 검수 게이트가 뚫린 것이다."""
        term = self.new_terms[0]
        Word.objects.filter(term=term).update(is_reviewed=False)

        # 같은 분류만 남기고 나머지를 지워 뽑기 범위를 좁힌다 - 무작위라
        # 안 그러면 몇 번 돌려도 안 걸릴 수 있다.
        word = Word.objects.get(term=term)
        Word.objects.exclude(category=word.category).delete()

        seen: set[str] = set()
        for _ in range(40):
            res = self.client.get("/api/vocab/words/quiz/")
            if res.status_code != 200:
                continue
            body = res.json()
            seen.update(c["text"] for c in body["choices"])
            seen.add(body["prompt"])

        self.assertNotIn(term, seen, "미검수 단어가 문제풀기에 나왔다")

    def test_unreviewing_a_new_sentence_removes_it(self):
        sentence = Sentence.objects.get(slug=self.new_slugs[0])
        Sentence.objects.filter(pk=sentence.pk).update(is_reviewed=False)

        res = self.client.get(f"/api/vocab/sentences/{sentence.pk}/")

        self.assertEqual(res.status_code, 404)

    def test_new_words_are_hidden_by_exam_filter(self):
        """?is_exam=true 로 걸렀을 때 새 단어가 섞이면 안 된다."""
        res = self.client.get(
            "/api/vocab/words/", {"is_exam": "true", "page_size": 100}
        )

        self.assertEqual(res.status_code, 200)
        returned = {w["term"] for w in res.json()["results"]}
        self.assertEqual(returned & set(self.new_terms), set())

    def test_new_words_appear_when_exam_filter_is_off(self):
        res = self.client.get("/api/vocab/words/", {"is_exam": "false"})

        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.json()["count"], 0)

    def test_pagination_boundaries_do_not_crash(self):
        """단어가 600개를 넘으면 뒤 페이지가 실제로 생긴다."""
        for params, expected in [
            ({"page": 1}, 200),
            ({"page": 0}, 404),
            ({"page": 999999}, 404),
            ({"page": "-1"}, 404),
            ({"page": "abc"}, 404),
            ({"page_size": 100000}, 200),
            ({"page_size": 0}, 200),
            ({"page_size": "abc"}, 200),
        ]:
            with self.subTest(params=params):
                res = self.client.get("/api/vocab/words/", params)
                self.assertEqual(res.status_code, expected)
                self.assertLess(res.status_code, 500)

    def test_last_page_is_reachable(self):
        first = self.client.get("/api/vocab/words/").json()
        page_size = len(first["results"])
        last = -(-first["count"] // page_size)

        res = self.client.get("/api/vocab/words/", {"page": last})

        self.assertEqual(res.status_code, 200)
        self.assertGreater(len(res.json()["results"]), 0)

    def test_invalid_category_filter_is_400_not_500(self):
        res = self.client.get("/api/vocab/words/", {"category": "testing"})

        self.assertLess(res.status_code, 500)

    def test_bad_pk_is_404_not_500(self):
        for pk in ["9" * 30, "-1", "abc", "0"]:
            with self.subTest(pk=pk):
                res = self.client.get(f"/api/vocab/words/{pk}/")
                self.assertEqual(res.status_code, 404)


class NewContentReachesQuizTest(TestCase):
    """새 데이터가 문제로 실제로 나오는지."""

    @classmethod
    def setUpTestData(cls):
        run("seed_words")
        run("seed_words_more")
        run("seed_sentences")
        run("seed_sentences_more")

    def test_new_words_can_be_the_answer(self):
        """새 단어만 남겨도 문제가 만들어진다.

        분류가 새 단어만으로 4개를 못 채우면 보기를 못 만들어 조용히
        빈 문제 목록이 돌아온다.
        """
        Word.objects.exclude(term__in=[w[0] for w in MORE_WORDS]).delete()

        res = self.client.get("/api/vocab/words/quiz/")

        self.assertEqual(res.status_code, 200, res.content.decode())
        self.assertEqual(len(res.json()["choices"]), 4)

    def test_new_sentences_can_be_the_answer(self):
        Sentence.objects.exclude(slug__in=[s[0] for s in MORE_SENTENCES]).delete()

        res = self.client.get("/api/vocab/sentences/quiz/")

        self.assertEqual(res.status_code, 200, res.content.decode())
        self.assertEqual(len(res.json()["choices"]), 4)

    def test_new_sentences_all_have_context_for_situation_quiz(self):
        """상황 고르기는 context 가 있어야 낼 수 있다."""
        missing = [s[0] for s in MORE_SENTENCES if not s[6].strip()]

        self.assertEqual(missing, [], "상황이 빈 새 문장이 있다")

    def test_some_new_sentences_can_host_a_blank(self):
        """빈칸 채우기는 문장에 단어가 들어 있어야 낸다.

        전부 못 내면 새 문장은 그 유형에서 영영 안 나온다. 몇 개면
        충분하지만 0 이면 문제다.
        """
        from .quiz import _terms_in

        terms = [
            (pk, t) for pk, t in Word.objects.values_list("pk", "term") if t.strip()
        ]
        hosts = [
            s[0] for s in MORE_SENTENCES if _terms_in(s[1], terms)
        ]

        self.assertGreater(len(hosts), 0, "빈칸을 낼 수 있는 새 문장이 없다")

    def test_situation_quiz_can_use_a_new_sentence(self):
        Sentence.objects.exclude(slug__in=[s[0] for s in MORE_SENTENCES]).delete()

        res = self.client.get("/api/vocab/sentences/quiz/", {"kind": "situation"})

        self.assertEqual(res.status_code, 200, res.content.decode())
        self.assertEqual(res.json()["kind"], "situation")


class NewContentReadingGapTest(TestCase):
    """발음(reading)이 빈 항목이 화면 계약을 깨지 않는지."""

    @classmethod
    def setUpTestData(cls):
        run("seed_words_more")
        run("seed_sentences_more")

    def test_new_words_have_no_reading(self):
        """전제 확인. 87건은 한글 발음 없이 들어온다."""
        self.assertEqual(Word.objects.exclude(reading="").count(), 0)

    def test_list_still_returns_reading_key(self):
        """칸이 비어도 키 자체는 있어야 프론트가 옵셔널 체이닝 없이 읽는다."""
        res = self.client.get("/api/vocab/words/")

        self.assertEqual(res.status_code, 200)
        for item in res.json()["results"]:
            self.assertIn("reading", item)
            self.assertEqual(item["reading"], "")

    def test_detail_returns_empty_reading_not_null(self):
        """null 이 오면 프론트에서 'null' 이 그대로 그려질 수 있다."""
        word = Word.objects.first()

        body = self.client.get(f"/api/vocab/words/{word.pk}/").json()

        self.assertEqual(body["reading"], "")
        self.assertIsNotNone(body["reading"])

    def test_unreviewed_reading_is_not_leaked(self):
        """발음만 미검수인 상태에서 그 칸이 새면 안 된다.

        항목 플래그(is_reviewed)가 아니라 칸 플래그(reading_reviewed)가
        지키는 자리다.
        """
        word = Word.objects.first()
        Word.objects.filter(pk=word.pk).update(
            reading="아무도안본발음", reading_reviewed=False
        )

        body = self.client.get(f"/api/vocab/words/{word.pk}/").json()

        self.assertEqual(body["reading"], "")

    def test_sentence_quiz_explanation_survives_empty_reading(self):
        """해설에 발음이 없어도 채점이 500 을 내면 안 된다."""
        run("seed_words")
        run("seed_sentences")

        quiz = self.client.get("/api/vocab/sentences/quiz/").json()

        res = self.client.post(
            "/api/vocab/sentences/grade/",
            data={"token": quiz["token"], "picked": quiz["choices"][0]["id"]},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200, res.content.decode())
        self.assertIn("correct", res.json())


class SeedListShapeTest(TestCase):
    """리스트 자체의 모양. 전수 검사가 못 보는 자리를 메운다."""

    def test_word_rows_have_exactly_eight_columns(self):
        """칸이 남거나 모자라면 위치 언패킹이 조용히 어긋난다."""
        for row in MORE_WORDS:
            with self.subTest(term=row[0]):
                self.assertEqual(len(row), 8)

    def test_sentence_rows_have_exactly_eight_columns(self):
        for row in MORE_SENTENCES:
            with self.subTest(slug=row[0]):
                self.assertEqual(len(row), 8)

    def test_new_word_categories_are_real_choices(self):
        """분류가 목록에 없으면 시드가 CheckConstraint 로 터진다.

        빈 문자열이 아닌 것만으로는 부족하다 - "testing" 같은 오타는
        strip() 검사를 그냥 통과한 뒤 배포 때 IntegrityError 로 터진다.
        """
        valid = set(LearningItem.Category.values)

        for row in MORE_WORDS:
            with self.subTest(term=row[0]):
                self.assertIn(row[3], valid)

    def test_new_sentence_kinds_are_real_choices(self):
        valid = set(SentenceKind.values)

        for row in MORE_SENTENCES:
            with self.subTest(slug=row[0]):
                self.assertIn(row[3], valid)

    def test_new_slugs_do_not_collide_with_base(self):
        base = {s[0] for s in BASE_SENTENCES}
        new = {s[0] for s in MORE_SENTENCES}

        self.assertEqual(base & new, set())

    def test_new_terms_do_not_collide_with_base(self):
        base = {w[0] for w in BASE_WORDS}
        new = {w[0] for w in MORE_WORDS}

        self.assertEqual(base & new, set())

    def test_new_terms_are_lowercase_or_deliberate(self):
        """대소문자만 다른 같은 말이 두 벌 들어가는 것을 막는다."""
        base = {w[0].lower() for w in BASE_WORDS}
        new = [w[0] for w in MORE_WORDS if w[0].lower() in base]

        self.assertEqual(new, [])

    def test_examples_are_not_the_description(self):
        """예문 칸에 한글 설명이 들어가면 영어 학습이 안 된다."""
        import re

        for row in MORE_WORDS:
            with self.subTest(term=row[0]):
                self.assertIsNone(
                    re.search(r"[가-힣]", row[6]), "예문에 한글이 섞였다"
                )

    def test_sentence_text_is_english(self):
        import re

        for row in MORE_SENTENCES:
            with self.subTest(slug=row[0]):
                self.assertIsNone(re.search(r"[가-힣]", row[1]))

    def test_translations_are_korean(self):
        import re

        for row in MORE_WORDS:
            with self.subTest(term=row[0]):
                self.assertIsNotNone(re.search(r"[가-힣]", row[7]))
        for row in MORE_SENTENCES:
            with self.subTest(slug=row[0]):
                self.assertIsNotNone(re.search(r"[가-힣]", row[2]))


class PronunciationConsistencyTest(TestCase):
    """같은 낱말이 두 항목에 나오면 표기가 같아야 한다.

    "latency" 와 "tail latency" 처럼 구(句)가 낱말을 품는 경우가 있다.
    두 곳의 모음이 다르면 학습자는 같은 말을 두 가지로 외운다. 어느 쪽이
    맞는지는 사람이 정해야 하지만, **갈렸다는 사실**은 기계가 잡을 수 있다.

    강세 기호는 뺀다 - 구에서는 뒷말의 주강세를 2강세로 내리는 것이
    정상이라(`/ˈmɜrdʒ ˌkɑmɪt/`) 그것까지 같기를 요구할 수 없다.

    **모음까지 정당하게 갈리는 경우가 있다.** commit 은 동사 /kəˈmɪt/,
    명사 /ˈkɑmɪt/ 로 강세가 옮기며 첫 모음이 준다. 그런 것은 아래
    목록에 적어 통과시킨다 - 목록에 한 줄 넣는 것이 "사람이 봤다" 는
    신호다. 기계가 못 가르는 자리라 목록 말고는 방법이 없다.
    """

    # (구, 낱말) - 갈리는 것이 맞다고 확인한 짝
    JUSTIFIED = {
        # 동사 /kəˈmɪt/ 가 명사가 되며 /ˈkɑmɪt/. 기존 "merge commit" 도 같다.
        ("signed commit", "commit"),
    }

    def _strip_stress(self, pron: str) -> str:
        import re

        return re.sub(r"[ˈˌ]", "", pron)

    def test_phrase_reuses_the_same_spelling_as_the_standalone_word(self):
        standalone = {
            row[0].lower(): row[1] for row in BASE_WORDS if row[1]
        }

        mismatches = []
        for term, pron, *_ in MORE_WORDS:
            if not pron:
                continue
            parts = term.lower().split()
            segments = pron.strip("/").split()
            if len(parts) < 2 or len(parts) != len(segments):
                continue
            for word, segment in zip(parts, segments):
                if word not in standalone:
                    continue
                if (term.lower(), word) in self.JUSTIFIED:
                    continue
                if self._strip_stress(segment) != self._strip_stress(
                    standalone[word].strip("/")
                ):
                    mismatches.append(
                        f"{term} 의 '{word}' 는 /{segment}/ 인데 "
                        f"단독 표기는 {standalone[word]} 다"
                    )

        self.assertEqual(mismatches, [], "\n".join(mismatches))
