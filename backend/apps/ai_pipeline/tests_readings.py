"""generate_readings 테스트.

generate_words 와 같은 이유로 실제 API 를 안 부른다 - 개발기 .env 에 진짜
키가 있어서 mock 없이 짜면 그 자리에서 과금된다. 이 명령은 특히 그렇다:
한 번에 최대 50개를 보내고 프롬프트에 규칙 문서가 통째로 들어간다.

**짝짓기를 집중해서 본다.** 이 명령은 응답을 term 으로 짝짓는데(AI 는 pk 를
모른다), 잘못 짝지으면 엉뚱한 단어에 엉뚱한 발음이 붙는다. 그건 화면에서
티가 안 나서 검수도 통과한다 - save() 주석이 경고하는 자리다.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.vocab.models import Sentence, Word

from .tests import FakeGenerator


def run(generator, *args, **kwargs) -> str:
    """가짜 생성기를 주입해 실행하고 출력을 돌려준다."""
    out = StringIO()
    with patch(
        "apps.ai_pipeline.management.commands.generate_readings."
        "Command.get_generator",
        return_value=generator,
    ):
        call_command("generate_readings", *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


def reading_of(term: str, text: str, note: str = "") -> dict:
    return {"term": term, "reading": text, "note": note}


class GenerateReadingsTest(TestCase):
    """AI 로 발음을 채운다."""

    def setUp(self):
        self.deploy = Word.objects.create(
            term="deploy", pronunciation="/dɪˈplɔɪ/", meaning="배포하다"
        )
        self.cache = Word.objects.create(
            term="cache", pronunciation="/kæʃ/", meaning="임시 저장"
        )

    # --- 검수 게이트 ---

    def test_generated_reading_is_not_reviewed(self):
        """AI 가 만든 발음은 검수 전 상태로 들어간다.

        True 로 들어가면 아무도 확인하지 않은 표기가 그대로 화면에 뜬다.
        이 기능에서 가장 중요한 규칙이다.
        """
        run(FakeGenerator([reading_of("deploy", "드**플로이**")]), "--count", "1")

        self.deploy.refresh_from_db()
        self.assertEqual(self.deploy.reading, "드**플로이**")
        self.assertFalse(self.deploy.reading_reviewed)

    def test_it_does_not_touch_the_word_review_flag(self):
        """단어 검수 상태는 안 건드린다.

        발음을 채웠다고 단어가 미검수로 돌아가면, 배치 한 번에 566개가
        화면에서 사라진다.
        """
        self.deploy.is_reviewed = True
        self.deploy.save(update_fields=["is_reviewed"])

        run(FakeGenerator([reading_of("deploy", "드**플로이**")]), "--count", "1")

        self.deploy.refresh_from_db()
        self.assertTrue(self.deploy.is_reviewed)

    def test_reviewed_reading_is_never_a_target(self):
        """검수된 발음은 --refill 로도 안 덮는다.

        사람이 확인한 것을 AI 가 덮으면 검수라는 절차가 의미를 잃는다.
        """
        self.deploy.reading = "사람이 적은 것"
        self.deploy.reading_reviewed = True
        self.deploy.save(update_fields=["reading", "reading_reviewed"])

        fake = FakeGenerator([reading_of("deploy", "AI 가 적은 것")])
        run(fake, "--count", "50", "--refill")

        self.deploy.refresh_from_db()
        self.assertEqual(self.deploy.reading, "사람이 적은 것")
        # 프롬프트에도 안 실려야 한다. 실리면 그만큼 돈이 샌다.
        self.assertNotIn("deploy", fake.calls[0]["user"])

    # --- 짝짓기 (이 명령의 핵심 위험) ---

    def test_answers_are_matched_by_term_not_by_order(self):
        """응답 순서가 바뀌어도 제 단어에 붙는다.

        순서로 맞추면 AI 가 하나를 빠뜨렸을 때 그 뒤가 전부 한 칸씩 밀린다.
        """
        run(
            FakeGenerator(
                [
                    reading_of("cache", "**캐**sh"),
                    reading_of("deploy", "드**플로이**"),
                ]
            ),
            "--count", "2",
        )

        self.deploy.refresh_from_db()
        self.cache.refresh_from_db()
        self.assertEqual(self.deploy.reading, "드**플로이**")
        self.assertEqual(self.cache.reading, "**캐**sh")

    def test_a_missing_answer_does_not_shift_the_others(self):
        """AI 가 가운데를 빠뜨려도 나머지가 안 밀린다."""
        middle = Word.objects.create(term="merge", pronunciation="/mɜrdʒ/", meaning="합치다")

        run(
            FakeGenerator(
                [
                    reading_of("cache", "**캐**sh"),
                    reading_of("deploy", "드**플로이**"),
                ]
            ),
            "--count", "3",
        )

        middle.refresh_from_db()
        self.deploy.refresh_from_db()
        self.assertEqual(middle.reading, "", "빠뜨린 것에 남의 발음이 붙었다")
        self.assertEqual(self.deploy.reading, "드**플로이**")

    def test_an_answer_for_something_we_did_not_send_is_ignored(self):
        """안 보낸 단어가 와도 무시한다."""
        outsider = Word.objects.create(term="ghost", meaning="유령")

        run(
            FakeGenerator(
                [
                    reading_of("ghost", "**고우s트**"),
                    reading_of("deploy", "드**플로이**"),
                ]
            ),
            "--count", "1",
        )

        outsider.refresh_from_db()
        self.assertEqual(outsider.reading, "", "안 보낸 단어가 채워졌다")

    def test_duplicate_names_are_skipped_and_reported(self):
        """이름이 겹치면 건너뛰고 그 사실을 알린다.

        term 으로 짝을 찾으므로 같은 이름이 둘이면 어느 쪽인지 알 수 없다.
        조용히 하나만 채우면 나머지가 어디 갔는지 모른 채 넘어간다.

        Word.term 은 unique 라 문장에서만 일어난다.
        """
        Sentence.objects.create(text="Ship it.", translation="배포해.")
        Sentence.objects.create(text="Ship it.", translation="올려.")

        out = run(
            FakeGenerator([{"term": "Ship it.", "reading": "**sh잎** 잍", "note": ""}]),
            "--kind", "sentence", "--count", "50",
        )

        self.assertIn("이름이 겹쳐", out)
        self.assertEqual(Sentence.objects.exclude(reading="").count(), 0)

    # --- dry-run 이 실제와 맞는가 ---

    def test_dry_run_saves_nothing(self):
        run(
            FakeGenerator([reading_of("deploy", "드**플로이**")]),
            "--count", "1", "--dry-run",
        )

        self.deploy.refresh_from_db()
        self.assertEqual(self.deploy.reading, "")

    def test_dry_run_count_matches_the_real_run(self):
        """예고한 건수와 실제 저장 건수가 같다.

        다르면 "20개" 를 보고 실행했는데 12개만 들어간다. 같은 코드를 타는
        것으로 그것을 보장하는데, 그 보장이 실제로 서는지 본다.
        """
        items = [
            reading_of("deploy", "드**플로이**"),
            reading_of("cache", "가" * 200),  # 길이 초과라 버려진다
        ]

        preview = run(FakeGenerator(list(items)), "--count", "2", "--dry-run")
        real = run(FakeGenerator(list(items)), "--count", "2")

        self.assertIn("1개가 채워지고", preview)
        self.assertIn("1개 채웠습니다", real)

    # --- 실패해도 조용하지 않다 ---

    def test_too_long_reading_is_reported_not_swallowed(self):
        """길이를 넘겨 버린 것은 왜 버렸는지 알려준다.

        숫자만 주면 "19개 건너뜀" 을 보고도 이유를 알 길이 없다.
        """
        out = run(FakeGenerator([reading_of("deploy", "가" * 200)]), "--count", "1")

        self.deploy.refresh_from_db()
        self.assertEqual(self.deploy.reading, "")
        self.assertIn("deploy", out)
        self.assertIn("깁니다", out)

    def test_empty_reading_is_skipped(self):
        run(FakeGenerator([reading_of("deploy", "  ")]), "--count", "1")

        self.deploy.refresh_from_db()
        self.assertEqual(self.deploy.reading, "")

    def test_api_failure_is_a_command_error_not_a_traceback(self):
        with self.assertRaises(CommandError):
            run(FakeGenerator(error="한도 초과"), "--count", "1")

    def test_nothing_to_fill_is_not_an_error(self):
        """다 채워져 있으면 조용히 끝난다."""
        Word.objects.update(reading="이미 있음")

        out = run(FakeGenerator([]), "--count", "10")

        self.assertIn("채울 항목이 없습니다", out)

    def test_count_out_of_range_is_rejected(self):
        with self.assertRaises(CommandError):
            run(FakeGenerator([]), "--count", "0")
        with self.assertRaises(CommandError):
            run(FakeGenerator([]), "--count", "51")

    # --- 프롬프트 ---

    def test_the_rules_document_is_sent(self):
        """표기 규칙이 프롬프트에 실린다.

        안 실리면 AI 가 제멋대로 적고, 566개가 제각각 된 뒤에야 안다.
        """
        fake = FakeGenerator([reading_of("deploy", "드**플로이**")])
        run(fake, "--count", "1")

        system = fake.calls[0]["system"]
        self.assertIn("한글만 읽어도 통해야", system)
        self.assertIn("약어는 발음기호가 갈라준다", system)

    def test_the_ipa_is_sent_with_each_word(self):
        """발음기호를 함께 보낸다. 그게 없으면 AI 가 철자로 추측한다."""
        fake = FakeGenerator([reading_of("deploy", "드**플로이**")])
        run(fake, "--count", "1")

        self.assertIn("/dɪˈplɔɪ/", fake.calls[0]["user"])


class GenerateReadingsSentenceTest(TestCase):
    """문장도 같은 명령으로 채운다."""

    def setUp(self):
        self.sentence = Sentence.objects.create(
            text="Could you rebase this?", translation="리베이스 해줄래?"
        )

    def test_it_fills_sentences(self):
        run(
            FakeGenerator(
                [{"term": "Could you rebase this?", "reading": "**쿠**쥬 리**베이s** 디s?", "note": ""}]
            ),
            "--kind", "sentence", "--count", "1",
        )

        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, "**쿠**쥬 리**베이s** 디s?")
        self.assertFalse(self.sentence.reading_reviewed)

    def test_a_long_sentence_reading_is_not_cut(self):
        """문장 발음에는 길이 상한이 없다. 단어 상한(120)을 적용하면 안 된다."""
        long_one = "가" * 300

        run(
            FakeGenerator([{"term": "Could you rebase this?", "reading": long_one, "note": ""}]),
            "--kind", "sentence", "--count", "1",
        )

        self.sentence.refresh_from_db()
        self.assertEqual(self.sentence.reading, long_one)
