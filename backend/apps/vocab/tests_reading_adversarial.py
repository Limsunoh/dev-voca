"""한글 발음 기능을 깨뜨려보는 테스트.

구현자의 테스트와 별개로 작성했다. 목적은 통과 확인이 아니라 새는 곳 찾기다.

세 갈래로 본다:
    1. 검수 게이트 - reading_reviewed=False 인 발음이 사용자 경로로 새는가
    2. load_readings - 이상한 입력을 먹였을 때 500 대신 제대로 거르는가
    3. 경계 - 길이, 빈 값, 잘못된 pk, 중복 pk
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Sentence, SentenceKind, Word

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"
QUIZ_URL = "/api/vocab/words/quiz/"
GRADE_URL = "/api/vocab/words/grade/"

# 미검수 발음에 심어두는 표식. 응답 본문 어디에도 나오면 안 된다.
LEAK = "리크표식zzz"


class ReadingGateTest(TestCase):
    """검수 안 된 발음이 사용자 조회 경로로 새는지.

    이 기능의 핵심 방어다. 단어 자체는 검수가 끝났는데 발음만 미검수인
    상태를 만들어 다섯 경로를 전부 두드린다. 항목 단위 is_reviewed 로는
    이 상태를 못 막으므로 필드 단위 게이트가 유일한 방어다.
    """

    @classmethod
    def setUpTestData(cls):
        # 단어 자체는 검수 완료. 발음만 미검수 - 배치로 채운 직후의 상태다.
        cls.word = Word.objects.create(
            term="cache",
            meaning="캐시",
            description="자주 쓰는 것을 가까이 둔다",
            example="Clear the cache.",
            category="cs",
            is_reviewed=True,
            reading=f"**캐**{LEAK}",
            reading_note=f"설명{LEAK}",
            reading_reviewed=False,
        )
        cls.sentence = Sentence.objects.create(
            text="Could you take another look?",
            translation="다시 봐주시겠어요?",
            kind=SentenceKind.PHRASE,
            category=Sentence.Category.REVIEW,
            is_reviewed=True,
            reading=f"쿠쥬{LEAK}",
            reading_reviewed=False,
        )
        cls.staff = get_user_model().objects.create_user(
            email="reader-staff@example.com", password="x", is_staff=True
        )
        cls.superuser = get_user_model().objects.create_superuser(
            email="reader-super@example.com", password="x"
        )

    def assertNoLeak(self, res, where: str):
        self.assertNotIn(LEAK, res.content.decode(), f"미검수 발음이 {where} 로 샜다")

    # --- 다섯 경로 ---

    def test_word_list_hides_unreviewed_reading(self):
        res = self.client.get(WORDS_URL)

        self.assertEqual(res.json()["results"][0]["reading"], "")
        self.assertNoLeak(res, "단어 목록")

    def test_word_detail_hides_unreviewed_reading(self):
        res = self.client.get(f"{WORDS_URL}{self.word.pk}/")

        body = res.json()
        self.assertEqual(body["reading"], "")
        self.assertEqual(body["reading_note"], "")
        self.assertNoLeak(res, "단어 상세")

    def test_sentence_list_hides_unreviewed_reading(self):
        res = self.client.get(SENTENCES_URL)

        self.assertEqual(res.json()["results"][0]["reading"], "")
        self.assertNoLeak(res, "문장 목록")

    def test_sentence_detail_hides_unreviewed_reading(self):
        res = self.client.get(f"{SENTENCES_URL}{self.sentence.pk}/")

        self.assertEqual(res.json()["reading"], "")
        self.assertNoLeak(res, "문장 상세")

    def test_quiz_grade_hides_unreviewed_reading(self):
        """퀴즈 해설은 로그인 없이 되는 경로다. 여기가 제일 위험하다."""
        # 보기 4개를 채울 만큼 단어를 만든다. 전부 발음이 미검수다.
        for i in range(6):
            Word.objects.create(
                term=f"quizword{i}",
                meaning=f"뜻{i}",
                description=f"설명{i}",
                category="cs",
                is_reviewed=True,
                reading=f"발음{i}{LEAK}",
                reading_note=f"노트{i}{LEAK}",
                reading_reviewed=False,
            )

        for _ in range(10):
            q = self.client.get(QUIZ_URL).json()
            res = self.client.post(
                GRADE_URL,
                {"token": q["token"], "picked": q["choices"][0]["id"]},
                content_type="application/json",
            )
            self.assertEqual(res.json()["word"]["reading"], "")
            self.assertNoLeak(res, "퀴즈 해설")

    # --- 검색·필터·정렬로 우회 시도 ---

    def test_search_does_not_reveal_unreviewed_reading(self):
        """발음 문자열로 검색해도 발음은 안 나온다."""
        res = self.client.get(WORDS_URL, {"search": "cache"})

        self.assertNoLeak(res, "단어 검색")

    def test_shuffle_does_not_reveal_unreviewed_reading(self):
        """섞기 경로도 같은 시리얼라이저를 타는지."""
        res = self.client.get(WORDS_URL, {"shuffle": "seed1"})

        self.assertNoLeak(res, "섞은 목록")

    def test_staff_also_does_not_see_unreviewed_reading_in_api(self):
        """검수자에게도 API 로는 안 나간다.

        발음 검수는 Admin 에서 한다. API 에 미검수 발음을 흘리면 그 응답을
        쓰는 화면이 늘어날 때마다 게이트를 다시 확인해야 한다.
        """
        self.client.force_login(self.staff)

        for url in (WORDS_URL, f"{WORDS_URL}{self.word.pk}/", SENTENCES_URL):
            with self.subTest(url=url):
                self.assertNoLeak(self.client.get(url), f"검수자 {url}")

    def test_superuser_also_does_not_see_unreviewed_reading_in_api(self):
        self.client.force_login(self.superuser)

        self.assertNoLeak(self.client.get(WORDS_URL), "슈퍼유저 목록")

    # --- 게이트가 과하지 않은지 (반대 방향) ---

    def test_reviewed_reading_is_served_on_every_path(self):
        """검수된 발음은 다섯 경로 모두에서 나와야 한다.

        게이트가 전부 막아버리면 기능 자체가 죽는데 위 테스트들은 통과한다.
        """
        Word.objects.filter(pk=self.word.pk).update(
            reading="**캐**시", reading_note="앞에 힘", reading_reviewed=True
        )
        Sentence.objects.filter(pk=self.sentence.pk).update(
            reading="쿠쥬 테잌", reading_reviewed=True
        )

        listed = self.client.get(WORDS_URL).json()["results"][0]
        detail = self.client.get(f"{WORDS_URL}{self.word.pk}/").json()
        s_listed = self.client.get(SENTENCES_URL).json()["results"][0]
        s_detail = self.client.get(f"{SENTENCES_URL}{self.sentence.pk}/").json()

        self.assertEqual(listed["reading"], "**캐**시")
        self.assertEqual(detail["reading"], "**캐**시")
        self.assertEqual(detail["reading_note"], "앞에 힘")
        self.assertEqual(s_listed["reading"], "쿠쥬 테잌")
        self.assertEqual(s_detail["reading"], "쿠쥬 테잌")

    def test_reviewed_reading_reaches_quiz_explanation(self):
        """퀴즈 해설에도 검수된 발음은 나온다."""
        for i in range(6):
            Word.objects.create(
                term=f"okword{i}",
                meaning=f"뜻{i}",
                description=f"설명{i}",
                category="cs",
                is_reviewed=True,
                reading=f"발음{i}",
                reading_reviewed=True,
            )
        Word.objects.filter(pk=self.word.pk).delete()
        Sentence.objects.all().delete()

        q = self.client.get(QUIZ_URL).json()
        body = self.client.post(
            GRADE_URL,
            {"token": q["token"], "picked": q["choices"][0]["id"]},
            content_type="application/json",
        ).json()

        self.assertTrue(body["word"]["reading"].startswith("발음"))

    # --- 쓰기 경로 ---

    def test_api_cannot_flip_reading_reviewed(self):
        """API 로 검수 플래그를 켤 수 없어야 한다.

        켤 수 있으면 게이트를 우회해 아무도 확인하지 않은 발음을 내보낼 수 있다.
        """
        self.client.force_login(self.staff)

        self.client.patch(
            f"{WORDS_URL}{self.word.pk}/",
            {"reading": "덮어쓰기", "reading_reviewed": True, "reading_note": "덮"},
            content_type="application/json",
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, f"**캐**{LEAK}")
        self.assertFalse(self.word.reading_reviewed)

    def test_api_create_cannot_set_reading(self):
        """생성할 때도 발음을 못 심는다."""
        self.client.force_login(self.staff)

        res = self.client.post(
            WORDS_URL,
            {
                "term": "brandnewterm",
                "meaning": "새 단어",
                "category": "cs",
                "reading": "심은발음",
                "reading_reviewed": True,
            },
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 201)
        created = Word.objects.get(term="brandnewterm")
        self.assertEqual(created.reading, "")
        self.assertFalse(created.reading_reviewed)

    def test_sentence_api_cannot_set_reading(self):
        self.client.force_login(self.staff)

        res = self.client.post(
            SENTENCES_URL,
            {
                "text": "Brand new sentence here.",
                "translation": "새 문장",
                "kind": SentenceKind.PHRASE,
                "category": Sentence.Category.REVIEW,
                "reading": "심은발음",
                "reading_reviewed": True,
            },
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 201)
        created = Sentence.objects.get(text="Brand new sentence here.")
        self.assertEqual(created.reading, "")
        self.assertFalse(created.reading_reviewed)

    def test_editing_term_resets_reading_review(self):
        """철자를 고치면 발음도 다시 검수받아야 한다.

        검수는 "사람이 이 내용을 확인했다"는 뜻이다. term 이 cache 에서
        queue 로 바뀌면 "**캐**시" 는 아무도 확인한 적 없는 발음이 된다.

        is_reviewed 는 되돌아가지만 그것만으로는 못 막는다 - Admin 에서
        바뀐 내용을 검수해 다시 True 로 올리는 순간 옛 철자의 발음이
        새 철자에 붙어 나간다. 검수자는 발음 칸이 이미 검수 완료라
        의심할 이유가 없다.
        """
        Word.objects.filter(pk=self.word.pk).update(
            reading="**캐**시", reading_note="앞에 힘", reading_reviewed=True
        )
        self.client.force_login(self.staff)

        self.client.patch(
            f"{WORDS_URL}{self.word.pk}/",
            {"term": "queue", "meaning": "대기열"},
            content_type="application/json",
        )

        self.word.refresh_from_db()
        self.assertFalse(self.word.is_reviewed)
        self.assertFalse(
            self.word.reading_reviewed,
            "철자가 바뀌었는데 발음 검수가 그대로 남았다",
        )

    def test_stale_reading_does_not_resurface_after_rereview(self):
        """위 상황에서 항목을 다시 검수하면 낡은 발음이 사용자에게 나간다."""
        Word.objects.filter(pk=self.word.pk).update(
            reading="**캐**시", reading_note="앞에 힘", reading_reviewed=True
        )
        self.client.force_login(self.staff)
        self.client.patch(
            f"{WORDS_URL}{self.word.pk}/",
            {"term": "queue", "meaning": "대기열"},
            content_type="application/json",
        )
        # Admin 에서 바뀐 내용을 확인하고 항목 검수만 다시 올린다.
        Word.objects.filter(pk=self.word.pk).update(is_reviewed=True)
        self.client.logout()

        body = self.client.get(f"{WORDS_URL}{self.word.pk}/").json()

        self.assertEqual(body["term"], "queue")
        self.assertNotEqual(
            body["reading"], "**캐**시", "queue 에 cache 의 발음이 붙어 나갔다"
        )

    def test_editing_sentence_text_resets_reading_review(self):
        """문장도 같다. 본문이 바뀌면 발음이 안 맞는다."""
        Sentence.objects.filter(pk=self.sentence.pk).update(
            reading="쿠쥬 테잌", reading_reviewed=True
        )
        self.client.force_login(self.staff)

        self.client.patch(
            f"{SENTENCES_URL}{self.sentence.pk}/",
            {"text": "Totally different sentence here."},
            content_type="application/json",
        )

        self.sentence.refresh_from_db()
        self.assertFalse(
            self.sentence.reading_reviewed,
            "본문이 바뀌었는데 발음 검수가 그대로 남았다",
        )

    def test_editing_only_difficulty_keeps_reading_review(self):
        """난이도·분류는 내용이 아니다. 이때까지 발음 검수를 되돌리면 과하다."""
        Word.objects.filter(pk=self.word.pk).update(
            reading="**캐**시", reading_reviewed=True
        )
        self.client.force_login(self.staff)

        self.client.patch(
            f"{WORDS_URL}{self.word.pk}/",
            {"difficulty": Word.Difficulty.HARD},
            content_type="application/json",
        )

        self.word.refresh_from_db()
        self.assertTrue(self.word.reading_reviewed)


class ReadingFieldBoundaryTest(TestCase):
    """모델·시리얼라이저 경계."""

    def test_word_reading_max_length_is_enforced_by_db(self):
        """max_length 를 넘기면 DB 가 거절한다(Postgres).

        엔진마다 다르므로 실패해도 코드 결함이 아니다. 여기서는 관리 명령이
        길이를 미리 거르는 이유를 고정하는 의미가 있다.
        """
        from django.core.exceptions import ValidationError

        word = Word(term="toolongreading", meaning="뜻", reading="가" * 121)
        with self.assertRaises(ValidationError):
            word.full_clean()

    def test_sentence_reading_has_no_length_cap(self):
        """문장 발음은 TextField 다. 긴 에러 메시지를 감당해야 한다."""
        long_reading = "가" * 5000
        s = Sentence.objects.create(
            text="x" * 5000,
            translation="긴 문장",
            kind=SentenceKind.ERROR,
            reading=long_reading,
            reading_reviewed=True,
            is_reviewed=True,
        )

        res = self.client.get(f"{SENTENCES_URL}{s.pk}/")

        self.assertEqual(len(res.json()["reading"]), 5000)

    def test_blank_reading_serializes_as_empty_string_not_null(self):
        """빈 발음이 null 로 나가면 프론트가 터진다."""
        word = Word.objects.create(
            term="noreading", meaning="뜻", is_reviewed=True, reading_reviewed=True
        )

        body = self.client.get(f"{WORDS_URL}{word.pk}/").json()

        self.assertEqual(body["reading"], "")
        self.assertEqual(body["reading_note"], "")
        self.assertIsNotNone(body["reading"])

    def test_reading_defaults_are_unreviewed_and_blank(self):
        word = Word.objects.create(term="freshword", meaning="뜻")
        sentence = Sentence.objects.create(
            text="fresh sentence", translation="새", kind=SentenceKind.PHRASE
        )

        self.assertEqual(word.reading, "")
        self.assertEqual(word.reading_note, "")
        self.assertFalse(word.reading_reviewed)
        self.assertFalse(sentence.reading_reviewed)

    def test_reading_survives_special_characters(self):
        """별표·따옴표·태그가 들어가도 저장·조회가 된다(HTML 이스케이프는 프론트 몫)."""
        raw = '**강**<script>alert("x")</script>'
        word = Word.objects.create(
            term="xssword",
            meaning="뜻",
            is_reviewed=True,
            reading=raw,
            reading_reviewed=True,
        )

        body = self.client.get(f"{WORDS_URL}{word.pk}/").json()

        self.assertEqual(body["reading"], raw)


class LoadReadingsTest(TestCase):
    """load_readings 관리 명령을 실제로 돌린다."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.word = Word.objects.create(
            term="cache", meaning="캐시", category="cs", is_reviewed=True
        )
        self.sentence = Sentence.objects.create(
            text="Could you take another look?",
            translation="다시 봐주시겠어요?",
            kind=SentenceKind.PHRASE,
            is_reviewed=True,
        )

    def write(self, payload, *, raw: str | None = None) -> str:
        path = Path(self.tmp.name) / "readings.json"
        path.write_text(
            raw if raw is not None else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def run_load(self, payload=None, *args, raw: str | None = None) -> str:
        out = StringIO()
        call_command("load_readings", self.write(payload, raw=raw), *args, stdout=out)
        return out.getvalue()

    # --- 정상 경로 ---

    def test_fills_reading_as_pending_review(self):
        """채운 발음은 미검수 상태로 들어간다. 바로 노출되면 안 된다."""
        self.run_load([{"pk": self.word.pk, "reading": "**캐**시", "note": "앞에 힘"}])

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "**캐**시")
        self.assertEqual(self.word.reading_note, "앞에 힘")
        self.assertFalse(self.word.reading_reviewed, "적재한 발음이 바로 검수됐다")
        self.assertEqual(self.client.get(f"{WORDS_URL}{self.word.pk}/").json()["reading"], "")

    def test_reviewed_flag_marks_as_reviewed(self):
        self.run_load(
            [{"pk": self.word.pk, "reading": "**캐**시"}], "--reviewed"
        )

        self.word.refresh_from_db()
        self.assertTrue(self.word.reading_reviewed)

    def test_unmark_in_admin_then_reload_replaces_reviewed_reading(self):
        """고쳐서 다시 넣기(fixtures/README.md) 세 단계가 실제로 돈다.

        검수된 발음은 다시 넣어도 안 바뀌고, Admin 에서 검수를 푼 줄만 새
        발음으로 바뀐다. 바뀐 발음은 다시 검수하기 전까지 안 나간다.
        Admin 을 실제로 POST 해서 동작이 등록돼 있는지도 같이 본다.
        """
        self.sentence.reading = "옛 발음"
        self.sentence.reading_reviewed = True
        self.sentence.save()
        payload = [{"pk": self.sentence.pk, "reading": "새 발음"}]

        self.run_load(payload, "--kind", "sentence")
        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "옛 발음", "검수된 발음을 덮었다")

        admin_user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="AdminPass2026!x"
        )
        self.client.force_login(admin_user)

        # README 가 안내하는 거르기 주소. 고친 줄만 보여야 전체 선택이 안전하다.
        Sentence.objects.create(text="Ship it.", translation="배포해.", is_reviewed=True)
        listed = self.client.get(f"/admin/vocab/sentence/?id__in={self.sentence.pk}")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(list(listed.context["cl"].result_list), [self.sentence])

        self.client.post(
            "/admin/vocab/sentence/",
            {"action": "unmark_reading_reviewed", "_selected_action": [self.sentence.pk]},
        )
        self.sentence.refresh_from_db()
        self.assertFalse(self.sentence.reading_reviewed, "Admin 에서 검수가 안 풀렸다")

        # 단어 쪽도 같은 동작이 등록돼 있는지. 본문은 같지만 actions 목록에서
        # 이름을 빠뜨리는 실수는 이쪽에서만 난다.
        self.word.reading_reviewed = True
        self.word.save()
        self.client.post(
            "/admin/vocab/word/",
            {"action": "unmark_reading_reviewed", "_selected_action": [self.word.pk]},
        )
        self.word.refresh_from_db()
        self.assertFalse(self.word.reading_reviewed, "단어 Admin 에서 검수가 안 풀렸다")

        self.run_load(payload, "--kind", "sentence")
        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "새 발음")
        self.assertFalse(self.sentence.reading_reviewed, "새 발음이 확인 없이 검수됐다")
        self.assertEqual(
            self.client.get(f"{SENTENCES_URL}{self.sentence.pk}/").json()["reading"], ""
        )

    def test_sentence_kind_fills_sentences(self):
        self.run_load(
            [{"pk": self.sentence.pk, "reading": "쿠쥬 테잌"}], "--kind", "sentence"
        )

        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "쿠쥬 테잌")

    def test_sentence_pk_does_not_touch_word_with_same_pk(self):
        """--kind 를 잘못 주면 같은 pk 의 다른 모델을 건드리는지."""
        # 같은 pk 를 갖도록 강제로 맞추기 어려우니, 단어 pk 로 sentence 를 돌린다.
        out = self.run_load(
            [{"pk": self.word.pk, "reading": "잘못된대상"}], "--kind", "sentence"
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "", "kind=sentence 인데 단어가 바뀌었다")
        # 우연히 같은 pk 의 문장이 있으면 거기 들어간다 - 그건 pk 대응의 성질이다.

    # --- 이상한 입력 ---

    def test_missing_file_is_command_error(self):
        with self.assertRaises(CommandError):
            call_command("load_readings", str(Path(self.tmp.name) / "nope.json"))

    def test_invalid_json_is_command_error_not_traceback(self):
        with self.assertRaises(CommandError):
            self.run_load(raw="{이건 JSON 이 아니다")

    def test_non_list_json_is_rejected(self):
        for raw in ('{"pk": 1}', '"문자열"', "42", "null", "true"):
            with self.subTest(raw=raw):
                with self.assertRaises(CommandError):
                    self.run_load(raw=raw)

    def test_empty_list_is_a_no_op(self):
        out = self.run_load([])

        self.assertIn("0개", out)
        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "")

    def test_unknown_pk_is_reported_and_skipped(self):
        out = self.run_load([{"pk": 999999999, "reading": "유령"}])

        self.assertIn("999999999", out)
        self.assertIn("1개 건너뜀", out)

    def test_huge_pk_does_not_blow_up(self):
        """bigint 범위를 넘는 pk. pk__in 에 그대로 넣으면 DB 가 거절해 500 이 난다."""
        out = self.run_load([{"pk": int("9" * 30), "reading": "거대"}])

        self.assertIn("건너뜀", out)

    def test_negative_and_zero_pk_are_skipped(self):
        out = self.run_load(
            [{"pk": -1, "reading": "음수"}, {"pk": 0, "reading": "영"}]
        )

        self.assertIn("2개 건너뜀", out)

    def test_non_integer_pk_is_skipped(self):
        """문자열·실수·None·dict 가 pk 자리에 와도 죽지 않아야 한다."""
        out = self.run_load(
            [
                {"pk": "1", "reading": "문자열pk"},
                {"pk": 1.5, "reading": "실수pk"},
                {"pk": None, "reading": "널pk"},
                {"pk": [1], "reading": "리스트pk"},
                {"pk": {"a": 1}, "reading": "딕트pk"},
                {"reading": "pk없음"},
            ]
        )

        self.assertIn("6개 건너뜀", out)
        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "")

    def test_true_as_pk_does_not_fill_an_unrelated_word(self):
        """파이썬에서 True 는 int 1 이다. isinstance(True, int) 가 True 라
        pk__in 에 그대로 들어가고, pk=1 인 단어가 있으면 엉뚱한 곳이 채워진다.
        """
        # pk=1 이 실제로 있어야 이 구멍이 드러난다. 테스트 DB 는 시퀀스가
        # 높은 값에서 시작해 우연히 비어 있을 뿐이고, 운영 DB 에는 있다.
        Word.objects.create(pk=1, term="pkonevictim", meaning="희생양")

        self.run_load([{"pk": True, "reading": "불리언pk"}])

        self.assertEqual(
            Word.objects.get(pk=1).reading,
            "",
            "True 가 pk=1 로 처리돼 엉뚱한 단어가 채워졌다",
        )

    def test_duplicate_pk_last_one_wins_without_error(self):
        """같은 pk 가 두 번 나오면 죽지 않고 마지막 값이 남는다."""
        out = self.run_load(
            [
                {"pk": self.word.pk, "reading": "첫번째"},
                {"pk": self.word.pk, "reading": "두번째"},
            ]
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "두번째")

    def test_empty_reading_is_skipped_silently(self):
        """빈 발음은 의도일 수 있다(갈리는 용어). 덮지 않는다."""
        Word.objects.filter(pk=self.word.pk).update(reading="기존발음")

        out = self.run_load(
            [
                {"pk": self.word.pk, "reading": ""},
                {"pk": self.word.pk, "reading": "   "},
                {"pk": self.word.pk, "reading": None},
                {"pk": self.word.pk},
            ]
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "기존발음", "빈 값이 기존 발음을 지웠다")
        self.assertIn("4개 건너뜀", out)

    def test_non_string_reading_does_not_crash(self):
        """숫자·리스트가 reading 자리에 와도 500 이 아니어야 한다."""
        out = self.run_load(
            [
                {"pk": self.word.pk, "reading": 123},
                {"pk": self.word.pk, "reading": ["a"]},
                {"pk": self.word.pk, "reading": {"a": 1}},
            ]
        )

        self.word.refresh_from_db()
        # 무엇이 저장됐든 최소한 죽지 않았고 길이 제한을 넘지 않았다
        self.assertLessEqual(len(self.word.reading), 120)

    def test_row_that_is_not_a_dict_does_not_crash(self):
        """배열 안에 문자열·숫자·null 이 섞여 있을 때."""
        out = self.run_load(["문자열", 42, None, [1, 2]])

        self.assertIn("건너뜀", out)

    def test_over_length_reading_is_rejected_not_truncated(self):
        """120자를 넘는 발음은 거절한다. 잘라서 넣으면 틀린 발음을 가르친다."""
        out = self.run_load([{"pk": self.word.pk, "reading": "가" * 121}])

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "", "길이 초과가 저장됐다")
        self.assertIn("120", out)

    def test_exactly_max_length_is_accepted(self):
        """경계값 120자는 통과해야 한다."""
        self.run_load([{"pk": self.word.pk, "reading": "가" * 120}])

        self.word.refresh_from_db()
        self.assertEqual(len(self.word.reading), 120)

    def test_long_sentence_reading_is_accepted(self):
        """문장은 TextField 라 120자 제한을 걸면 안 된다."""
        self.run_load(
            [{"pk": self.sentence.pk, "reading": "가" * 500}],
            "--kind",
            "sentence",
        )

        self.sentence.refresh_from_db()
        self.assertEqual(len(self.sentence.reading), 500)

    # --- 검수된 것을 덮지 않는다 ---

    def test_reviewed_reading_is_never_overwritten(self):
        """사람이 확인한 발음을 배치가 덮으면 검수 절차가 의미를 잃는다."""
        Word.objects.filter(pk=self.word.pk).update(
            reading="사람이적음", reading_note="사람노트", reading_reviewed=True
        )

        out = self.run_load(
            [{"pk": self.word.pk, "reading": "배치가덮음", "note": "배치노트"}]
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "사람이적음", "검수된 발음이 덮였다")
        self.assertEqual(self.word.reading_note, "사람노트")
        self.assertIn("이미 검수", out)

    def test_reviewed_flag_does_not_bypass_the_overwrite_guard(self):
        """--reviewed 로 다시 돌려도 검수된 것은 안 덮는다."""
        Word.objects.filter(pk=self.word.pk).update(
            reading="사람이적음", reading_reviewed=True
        )

        self.run_load(
            [{"pk": self.word.pk, "reading": "배치가덮음"}], "--reviewed"
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "사람이적음")

    def test_reviewed_sentence_is_never_overwritten(self):
        Sentence.objects.filter(pk=self.sentence.pk).update(
            reading="사람이적음", reading_reviewed=True
        )

        self.run_load(
            [{"pk": self.sentence.pk, "reading": "배치가덮음"}], "--kind", "sentence"
        )

        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "사람이적음")

    def test_unreviewed_reading_can_be_refilled(self):
        """미검수 발음은 고쳐 넣을 수 있어야 한다. 가드가 과하면 안 된다."""
        Word.objects.filter(pk=self.word.pk).update(
            reading="첫시도", reading_reviewed=False
        )

        self.run_load([{"pk": self.word.pk, "reading": "고친것"}])

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "고친것")

    # --- dry-run ---

    def test_dry_run_saves_nothing(self):
        out = self.run_load(
            [{"pk": self.word.pk, "reading": "**캐**시"}], "--dry-run"
        )

        self.word.refresh_from_db()
        self.assertEqual(self.word.reading, "", "dry-run 이 저장했다")
        self.assertIn("dry-run", out)

    def test_dry_run_count_matches_real_run(self):
        """예고한 건수와 실제 저장 건수가 같아야 한다.

        어긋나면 dry-run 을 보고 판단할 수 없다.
        """
        Word.objects.filter(pk=self.word.pk).update(reading_reviewed=False)
        reviewed = Word.objects.create(
            term="alreadyreviewed",
            meaning="뜻",
            reading="사람이적음",
            reading_reviewed=True,
        )
        rows = [
            {"pk": self.word.pk, "reading": "채워짐"},
            {"pk": reviewed.pk, "reading": "덮으면안됨"},
            {"pk": 999999999, "reading": "없는pk"},
            {"pk": self.word.pk, "reading": ""},
        ]

        dry = self.run_load(rows, "--dry-run")
        real = self.run_load(rows)

        import re

        dry_filled = int(re.search(r"저장하면 (\d+)개", dry).group(1))
        dry_skipped = int(re.search(r"(\d+)개는 건너뜁니다", dry).group(1))
        real_filled = int(re.search(r"(\d+)개 채웠습니다", real).group(1))
        real_skipped = int(re.search(r"\((\d+)개 건너뜀", real).group(1))

        self.assertEqual(dry_filled, real_filled, "dry-run 예고와 실제 저장이 다르다")
        self.assertEqual(dry_skipped, real_skipped)

    def test_dry_run_does_not_leak_into_api(self):
        self.run_load([{"pk": self.word.pk, "reading": "미저장"}], "--dry-run")

        res = self.client.get(f"{WORDS_URL}{self.word.pk}/")

        self.assertNotIn("미저장", res.content.decode())

    # --- 대량 / 성능 ---

    def test_large_batch_uses_bounded_queries(self):
        """200건을 넣을 때 항목마다 SELECT 하지 않는지."""
        words = [
            Word.objects.create(term=f"bulk{i}", meaning=f"뜻{i}") for i in range(50)
        ]
        rows = [{"pk": w.pk, "reading": f"발음{i}"} for i, w in enumerate(words)]

        with self.assertNumQueries(1 + 50 * 3):
            # 1: 대상 조회. 항목마다 savepoint/UPDATE/release = 3
            self.run_load(rows)

        self.assertEqual(
            Word.objects.exclude(reading="").count(), 50
        )


ADMIN_WORDS = "/admin/vocab/word/"
ADMIN_SENTENCES = "/admin/vocab/sentence/"

# (Admin 목록 주소, 모델, 동작 이름, 건드리는 칸, 동작 전 값)
# 동작 여섯 개. 동작 전 값의 반대가 되면 실행된 것이다.
REVIEW_ACTIONS = [
    (ADMIN_WORDS, Word, "mark_reviewed", "is_reviewed", False),
    (ADMIN_WORDS, Word, "mark_reading_reviewed", "reading_reviewed", False),
    (ADMIN_WORDS, Word, "unmark_reading_reviewed", "reading_reviewed", True),
    (ADMIN_SENTENCES, Sentence, "mark_reviewed", "is_reviewed", False),
    (ADMIN_SENTENCES, Sentence, "mark_reading_reviewed", "reading_reviewed", False),
    (ADMIN_SENTENCES, Sentence, "unmark_reading_reviewed", "reading_reviewed", True),
]


class ReviewActionPermissionTest(TestCase):
    """Admin 검수 동작 여섯 개를 누가 돌릴 수 있는지.

    검수 게이트는 결국 이 동작들에 걸려 있다. 권한이 모자란 계정이 POST 를
    직접 보내도 값이 안 바뀌어야 하고, 수정 권한이 있으면 바뀌어야 한다 -
    뒤쪽이 없으면 "아무도 못 돌린다" 도 통과해 버린다.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission

        User = get_user_model()

        def staff(email: str, *codenames: str, is_staff: bool = True):
            user = User.objects.create_user(email=email, password="x", is_staff=is_staff)
            if codenames:
                user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
            return user

        cls.non_staff = staff("plain@example.com", "change_word", "change_sentence", is_staff=False)
        cls.no_perm = staff("noperm@example.com")
        cls.view_only = staff("view@example.com", "view_word", "view_sentence")
        cls.add_delete = staff(
            "adddel@example.com",
            "add_word", "delete_word", "add_sentence", "delete_sentence",
        )
        cls.changer = staff("change@example.com", "change_word", "change_sentence")
        cls.superuser = User.objects.create_superuser(email="root@example.com", password="x")

    def post_action(self, url: str, model, action: str, field: str, before: bool):
        """대상 하나를 동작 전 값으로 만들고 동작을 POST 한다. (응답, 동작 뒤 값)"""
        if model is Word:
            obj = Word.objects.create(term=f"t-{action}", meaning="뜻")
        else:
            obj = Sentence.objects.create(text=f"s-{action}", translation="뜻")
        setattr(obj, field, before)
        obj.save()
        res = self.client.post(url, {"action": action, "_selected_action": [obj.pk]})
        obj.refresh_from_db()
        return res, getattr(obj, field)

    def assertBlocked(self, user):
        for url, model, action, field, before in REVIEW_ACTIONS:
            with self.subTest(url=url, action=action):
                if user is not None:
                    self.client.force_login(user)
                res, after = self.post_action(url, model, action, field, before)
                self.assertLess(res.status_code, 500)
                self.assertEqual(after, before, f"권한 없이 {action} 가 실행됐다")

    def assertAllowed(self, user):
        self.client.force_login(user)
        for url, model, action, field, before in REVIEW_ACTIONS:
            with self.subTest(url=url, action=action):
                res, after = self.post_action(url, model, action, field, before)
                self.assertEqual(res.status_code, 302)
                self.assertEqual(after, not before, f"{action} 가 실행되지 않았다")

    def test_anonymous_is_blocked(self):
        self.assertBlocked(None)

    def test_non_staff_with_change_permission_is_blocked(self):
        """권한이 있어도 staff 가 아니면 Admin 에 못 들어온다."""
        self.assertBlocked(self.non_staff)

    def test_staff_without_permissions_is_blocked(self):
        self.assertBlocked(self.no_perm)

    def test_view_only_staff_is_blocked(self):
        self.assertBlocked(self.view_only)

    def test_add_and_delete_without_change_is_blocked(self):
        """추가·삭제 권한은 수정 권한이 아니다."""
        self.assertBlocked(self.add_delete)

    def test_change_permission_runs_all_six(self):
        self.assertAllowed(self.changer)

    def test_superuser_runs_all_six(self):
        self.assertAllowed(self.superuser)

    def test_view_only_staff_does_not_see_the_actions(self):
        """보기만 하는 계정의 목록에는 동작 이름이 아예 안 나온다.

        목록이 비면 Django 가 동작 칸 자체를 안 그려 이 검사가 헛돈다.
        그래서 줄을 하나씩 만들어 둔다.
        """
        Word.objects.create(term="cache", meaning="캐시")
        Sentence.objects.create(text="Ship it.", translation="배포해.")
        self.client.force_login(self.view_only)
        for url in (ADMIN_WORDS, ADMIN_SENTENCES):
            with self.subTest(url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                form = res.context["action_form"]
                offered = {name for name, _ in form.fields["action"].choices} if form else set()
                for name in ("mark_reviewed", "mark_reading_reviewed", "unmark_reading_reviewed"):
                    self.assertNotIn(name, offered)

        # 같은 목록을 수정 권한으로 보면 여섯 동작이 다 보인다 - 위 검사가
        # 동작 칸을 실제로 읽고 있다는 증거다.
        self.client.force_login(self.changer)
        form = self.client.get(ADMIN_WORDS).context["action_form"]
        self.assertIn("unmark_reading_reviewed", {n for n, _ in form.fields["action"].choices})

    def test_view_only_staff_cannot_toggle_through_list_editable(self):
        """목록에서 바로 고치는 칸(list_editable)으로 우회하지 못한다."""
        sentence = Sentence.objects.create(text="Ship it.", translation="배포해.")
        self.client.force_login(self.view_only)
        res = self.client.post(
            ADMIN_SENTENCES,
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-0-id": str(sentence.pk),
                "form-0-is_reviewed": "on",
                "form-0-reading_reviewed": "on",
                "_save": "Save",
            },
        )
        sentence.refresh_from_db()
        self.assertLess(res.status_code, 500)
        self.assertFalse(sentence.is_reviewed, "보기 권한으로 목록에서 검수가 켜졌다")
        self.assertFalse(sentence.reading_reviewed)


class AdminIdInFilterTest(TestCase):
    """README 의 거르기 주소(?id__in=)에 이상한 값을 줬을 때.

    이 주소로 거른 뒤 "전체 선택" 하고 검수를 푸는 것이 절차다. 값이
    이상해서 거르기가 조용히 빠지면 전체 선택이 모든 줄을 잡는다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            email="root@example.com", password="x"
        )
        cls.target = Sentence.objects.create(
            text="Ship it.", translation="배포해.", reading="싶 잍", reading_reviewed=True
        )
        cls.other = Sentence.objects.create(
            text="Roll it back.", translation="되돌려.", reading="롤 잍", reading_reviewed=True
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def listed(self, value: str):
        res = self.client.get(ADMIN_SENTENCES, {"id__in": value})
        self.assertLess(res.status_code, 500, f"id__in={value[:40]!r} 에서 500")
        return res

    def test_matching_pk_lists_only_that_row(self):
        res = self.listed(str(self.target.pk))
        self.assertEqual(list(res.context["cl"].result_list), [self.target])

    def test_missing_pk_lists_nothing(self):
        res = self.listed("999999")
        self.assertEqual(list(res.context["cl"].result_list), [])

    def test_odd_values_do_not_500(self):
        for value in ("", "abc", f"{self.target.pk},abc", "-1", "9" * 30, ",,,", "1.5"):
            with self.subTest(value=value):
                res = self.listed(value)
                if res.status_code == 200:
                    # 거르기가 빠져 전체가 나오면 전체 선택이 모든 줄을 잡는다.
                    self.assertNotIn(self.other, list(res.context["cl"].result_list))

    def test_many_pks(self):
        pks = ",".join(str(i) for i in range(1, 3001))
        res = self.listed(f"{pks},{self.target.pk}")
        self.assertIn(self.target, list(res.context["cl"].result_list))

    def unmark_across(self, query: str):
        """거른 목록에서 전체 선택(select_across) 뒤 발음 검수 취소."""
        return self.client.post(
            f"{ADMIN_SENTENCES}?{query}",
            {
                "action": "unmark_reading_reviewed",
                "select_across": "1",
                "index": "0",
                "_selected_action": [self.target.pk],
            },
        )

    def test_select_across_touches_only_filtered_rows(self):
        """거른 목록에서 전체 선택으로 검수를 풀면 거른 줄만 풀린다."""
        self.unmark_across(f"id__in={self.target.pk}")

        self.target.refresh_from_db()
        self.other.refresh_from_db()
        self.assertFalse(self.target.reading_reviewed)
        self.assertTrue(self.other.reading_reviewed, "거르지 않은 줄의 검수까지 풀렸다")

    def test_select_across_with_bad_filter_touches_nothing(self):
        """거르기 값이 잘못되면 동작이 전체로 번지지 않는다."""
        for value in ("", "abc", "9" * 30):
            with self.subTest(value=value):
                res = self.unmark_across(f"id__in={value}")
                self.assertLess(res.status_code, 500)
                self.other.refresh_from_db()
                self.assertTrue(self.other.reading_reviewed, f"id__in={value!r} 로 전체가 풀렸다")


class ReloadAfterUnmarkTest(TestCase):
    """fixtures/README.md "고쳐서 다시 넣기" 의 경계.

    A: 검수됐다가 Admin 에서 푼 줄. B: 아직 검수된 줄. C: 처음부터 발음
    검수가 안 된 줄. 파일에는 셋 다 들어 있다.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        def make(text: str, reviewed: bool) -> Sentence:
            return Sentence.objects.create(
                text=text,
                translation="뜻",
                is_reviewed=True,
                reading=f"옛 {text}",
                reading_reviewed=reviewed,
            )

        self.a = make("Ship it.", False)
        self.b = make("Roll it back.", True)
        self.c = make("Try again.", False)
        self.path = Path(self.tmp.name) / "readings.json"
        self.path.write_text(
            json.dumps(
                [{"pk": s.pk, "reading": f"새 {s.pk}"} for s in (self.a, self.b, self.c)],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def load(self, *args: str) -> str:
        out = StringIO()
        call_command(
            "load_readings", str(self.path), "--kind", "sentence", *args, stdout=out
        )
        return out.getvalue()

    def test_dry_run_counts_unmarked_and_originally_unreviewed(self):
        """dry-run 건수에 원래 미검수였던 C 도 들어간다(README 가 경고하는 경우)."""
        out = self.load("--dry-run")

        self.assertIn("저장하면 2개가 채워지고 1개는 건너뜁니다", out)
        self.assertIn(f"pk={self.b.pk} 는 이미 검수됐습니다", out)
        for s in (self.a, self.b, self.c):
            s.refresh_from_db()
            self.assertTrue(s.reading.startswith("옛 "), "dry-run 이 저장했다")

    def test_real_run_matches_dry_run_and_overwrites_c_too(self):
        self.load()
        for s in (self.a, self.b, self.c):
            s.refresh_from_db()
        self.assertEqual(self.a.reading, f"새 {self.a.pk}")
        self.assertEqual(self.c.reading, f"새 {self.c.pk}", "C 도 같이 덮인다")
        self.assertEqual(self.b.reading, "옛 Roll it back.", "검수된 B 를 덮었다")
        self.assertFalse(self.a.reading_reviewed)
        self.assertFalse(self.c.reading_reviewed)

    def test_reloaded_reading_stays_hidden_until_reviewed(self):
        """새로 넣은 발음은 목록·상세·검색 어디에도 안 나간다."""
        self.load()
        a_new = f"새 {self.a.pk}"

        for url in (
            SENTENCES_URL,
            f"{SENTENCES_URL}{self.a.pk}/",
            f"{SENTENCES_URL}?search=Ship",
        ):
            with self.subTest(url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertNotIn(a_new, res.content.decode(), f"미검수 새 발음이 {url} 로 샜다")

        # B 는 검수된 옛 발음이 그대로 나간다 - 게이트가 전부 막는 것이 아니다.
        self.assertEqual(
            self.client.get(f"{SENTENCES_URL}{self.b.pk}/").json()["reading"], "옛 Roll it back."
        )

    def test_reviewed_flag_does_not_publish_an_unreviewed_sentence(self):
        """--reviewed 로 발음 검수가 켜져도, 문장 자체가 미검수면 어디에도 안 나간다."""
        hidden = Sentence.objects.create(text="Hidden zzq.", translation="숨김", is_reviewed=False)
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        rows.append({"pk": hidden.pk, "reading": "숨김발음zzq"})
        self.path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

        self.load("--reviewed")

        hidden.refresh_from_db()
        self.assertTrue(hidden.reading_reviewed)
        self.assertEqual(self.client.get(f"{SENTENCES_URL}{hidden.pk}/").status_code, 404)
        for url in (SENTENCES_URL, f"{SENTENCES_URL}?search=zzq"):
            with self.subTest(url):
                body = self.client.get(url).content.decode()
                self.assertNotIn("zzq", body, f"미검수 문장이 {url} 로 샜다")

    def test_reviewed_flag_publishes_without_review_but_keeps_b(self):
        """--reviewed 를 붙이면 바로 나간다(README 가 붙이지 말라는 이유). B 는 여전히 안 덮는다."""
        out = self.load("--reviewed")

        self.assertIn("검수 완료로 표시했습니다", out)
        self.assertEqual(
            self.client.get(f"{SENTENCES_URL}{self.a.pk}/").json()["reading"], f"새 {self.a.pk}"
        )
        self.b.refresh_from_db()
        self.assertEqual(self.b.reading, "옛 Roll it back.")
