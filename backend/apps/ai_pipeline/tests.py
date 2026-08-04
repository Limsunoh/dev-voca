"""AI 파이프라인 테스트.

실제 Claude API 를 호출하지 않는다. 개발기 .env 에는 진짜 키가 있어서,
mock 없이 테스트를 짜면 그 자리에서 과금된다.
"""

from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.ai_pipeline.client import GenerationError
from apps.ai_pipeline.prompts import vocab
from apps.vocab.models import Word


class FakeGenerator:
    """테스트용 생성기. 실제 API 를 부르지 않는다."""

    def __init__(self, items: list[dict] | None = None, error: str | None = None):
        self.items = items if items is not None else []
        self.error = error
        self.calls: list[dict] = []

    def generate(self, *, system, user, schema, result_key, max_items):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "result_key": result_key,
                "max_items": max_items,
            }
        )
        if self.error:
            raise GenerationError(self.error)
        return self.items[:max_items]


def make_item(term: str, **overrides) -> dict:
    item = {
        "term": term,
        "meaning": f"{term} 의 뜻",
        "description": "설명",
        "example": f"We {term} every day.",
        "example_translation": "우리는 매일 그렇게 한다.",
        "difficulty": 2,
    }
    item.update(overrides)
    return item


def run_command(generator, *args, **kwargs) -> str:
    """가짜 생성기를 주입해 커맨드를 실행하고 출력을 돌려준다."""
    out = StringIO()
    with patch(
        "apps.ai_pipeline.management.commands.generate_words.Command.get_generator",
        return_value=generator,
    ):
        call_command("generate_words", *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


class GenerateWordsTest(TestCase):
    # --- 검수 게이트 (가장 중요) ---

    def test_generated_words_are_not_reviewed(self):
        """AI 생성물은 검수 전 상태로 저장되어야 한다.

        True 로 들어가면 아무도 확인하지 않은 문장이 그대로 사용자에게 나간다.
        """
        run_command(FakeGenerator([make_item("deploy")]), "--count", "1")

        word = Word.objects.get(term="deploy")
        self.assertFalse(word.is_reviewed)

    def test_generated_words_are_hidden_from_users(self):
        """생성 직후에는 사용자 조회 경로에 나오지 않는다."""
        run_command(FakeGenerator([make_item("rebase")]), "--count", "1")

        self.assertEqual(Word.objects.visible().count(), 0)
        self.assertEqual(Word.objects.count(), 1)

    def test_source_is_marked_as_ai(self):
        """출처가 남아야 나중에 AI 생성분만 골라볼 수 있다."""
        run_command(FakeGenerator([make_item("merge")]), "--count", "1")

        self.assertEqual(Word.objects.get(term="merge").source, "AI 생성")

    # --- 저장 ---

    def test_saves_all_fields(self):
        item = make_item("idempotent", difficulty=3)
        run_command(FakeGenerator([item]), "--count", "1", "--category", "api")

        word = Word.objects.get(term="idempotent")
        self.assertEqual(word.meaning, "idempotent 의 뜻")
        self.assertEqual(word.example, "We idempotent every day.")
        self.assertEqual(word.difficulty, 3)
        self.assertEqual(word.category, "api")

    def test_duplicate_term_is_skipped(self):
        """이미 있는 단어는 건너뛴다. 기존 내용을 덮어쓰지 않는다."""
        Word.objects.create(term="commit", meaning="원래 뜻", is_reviewed=True)

        output = run_command(FakeGenerator([make_item("commit")]), "--count", "1")

        word = Word.objects.get(term="commit")
        self.assertEqual(word.meaning, "원래 뜻")
        self.assertTrue(word.is_reviewed)
        self.assertIn("1개 건너뜀", output)

    def test_blank_term_or_meaning_is_skipped(self):
        items = [
            make_item("valid"),
            make_item("", meaning="뜻만 있음"),
            make_item("meaningless", meaning="   "),
        ]

        run_command(FakeGenerator(items), "--count", "3")

        self.assertEqual([w.term for w in Word.objects.all()], ["valid"])

    def test_too_long_field_is_skipped_not_fatal(self):
        """길이 초과 한 건이 배치 전체를 무너뜨리면 안 된다.

        term 은 max_length=100. 이걸 그대로 저장하면 PostgreSQL 이 DataError 를
        내고, 배치를 한 트랜잭션으로 묶었다면 앞서 저장한 것까지 롤백된다.
        """
        items = [
            make_item("normal-one"),
            make_item("x" * 150),
            make_item("normal-two"),
        ]

        output = run_command(FakeGenerator(items), "--count", "3")

        saved = sorted(w.term for w in Word.objects.all())
        self.assertEqual(saved, ["normal-one", "normal-two"])
        self.assertIn("2개 저장", output)

    def test_too_long_meaning_is_skipped(self):
        """meaning 은 max_length=200."""
        run_command(
            FakeGenerator([make_item("longmeaning", meaning="가" * 250)]), "--count", "1"
        )

        self.assertEqual(Word.objects.count(), 0)

    def test_invalid_difficulty_falls_back(self):
        """스키마 밖의 난이도가 와도 저장이 깨지지 않는다."""
        run_command(FakeGenerator([make_item("odd", difficulty=99)]), "--count", "1")

        self.assertEqual(Word.objects.get(term="odd").difficulty, Word.Difficulty.NORMAL)

    def test_whitespace_is_stripped(self):
        run_command(FakeGenerator([make_item("  spaced  ")]), "--count", "1")

        self.assertTrue(Word.objects.filter(term="spaced").exists())

    # --- dry-run ---

    def test_dry_run_saves_nothing(self):
        output = run_command(
            FakeGenerator([make_item("preview")]), "--count", "1", "--dry-run"
        )

        self.assertEqual(Word.objects.count(), 0)
        self.assertIn("preview", output)
        self.assertIn("dry-run", output)

    def test_dry_run_predicts_actual_result(self):
        """dry-run 이 예고한 건수가 실제 저장 결과와 같아야 한다.

        검증을 건너뛰면 "3개 생성됨" 을 보고 실행했는데 1개만 저장되는 일이 생긴다.
        """
        Word.objects.create(term="existing", meaning="이미 있음")
        items = [
            make_item("brand-new"),
            make_item("existing"),  # 중복
            make_item("x" * 150),  # 길이 초과
        ]

        preview = run_command(FakeGenerator(items), "--count", "3", "--dry-run")

        self.assertIn("1개가 들어가고 2개는 건너뜁니다", preview)
        self.assertEqual(Word.objects.count(), 1)  # 저장 안 됨

        # 실제로 돌리면 예고대로여야 한다
        actual = run_command(FakeGenerator(items), "--count", "3")

        self.assertIn("1개 저장했습니다. (2개 건너뜀)", actual)

    # --- 입력 검증 ---

    def test_count_out_of_range_is_rejected(self):
        for bad in ("0", "-1", "51"):
            with self.subTest(count=bad):
                with self.assertRaises(CommandError):
                    run_command(FakeGenerator(), "--count", bad)

    def test_generation_error_becomes_command_error(self):
        """API 실패가 스택트레이스가 아니라 읽을 수 있는 메시지로 나온다."""
        with self.assertRaises(CommandError) as ctx:
            run_command(FakeGenerator(error="키가 없습니다"), "--count", "1")

        self.assertIn("키가 없습니다", str(ctx.exception))

    def test_missing_key_shows_message_not_traceback(self):
        """키가 없을 때 스택트레이스 대신 안내 문구가 나와야 한다."""
        out = StringIO()
        with patch(
            "apps.ai_pipeline.management.commands.generate_words.Command.get_generator",
            side_effect=GenerationError("ANTHROPIC_API_KEY 환경변수가 필요합니다."),
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command("generate_words", "--count", "1", stdout=out)

        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_empty_result_is_reported(self):
        output = run_command(FakeGenerator([]), "--count", "5")

        self.assertIn("생성된 단어가 없습니다", output)
        self.assertEqual(Word.objects.count(), 0)

    # --- 프롬프트 ---

    def test_existing_terms_are_sent_to_avoid_duplicates(self):
        Word.objects.create(term="already-here", meaning="기존")
        generator = FakeGenerator([make_item("new-one")])

        run_command(generator, "--count", "1")

        self.assertIn("already-here", generator.calls[0]["user"])

    def test_count_is_passed_through(self):
        generator = FakeGenerator([make_item(f"w{i}") for i in range(10)])

        run_command(generator, "--count", "3")

        self.assertEqual(generator.calls[0]["max_items"], 3)
        self.assertEqual(Word.objects.count(), 3)


class PromptTest(TestCase):
    def test_schema_requires_all_content_fields(self):
        """스키마가 느슨하면 필드가 빠진 응답이 그대로 저장된다."""
        required = vocab.SCHEMA["properties"]["words"]["items"]["required"]

        for field in ("term", "meaning", "description", "example", "difficulty"):
            self.assertIn(field, required)

    def test_prompt_includes_category_and_existing(self):
        prompt = vocab.build_user_prompt(
            count=5, category="git", existing=["commit", "merge"]
        )

        self.assertIn("5", prompt)
        self.assertIn("git", prompt)
        self.assertIn("commit", prompt)

    def test_prompt_handles_empty_existing(self):
        prompt = vocab.build_user_prompt(count=3, category="", existing=[])

        self.assertIn("개발 전반", prompt)
        self.assertIn("(없음)", prompt)


def make_response(text: str, stop_reason: str = "end_turn"):
    """Claude API 응답을 흉내낸다. 실제 SDK 객체가 아니라 필요한 속성만 갖춘다."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(stop_reason=stop_reason, content=[block])


def make_generator(response) -> "ClaudeGenerator":
    """SDK 클라이언트만 가짜로 바꾼 실제 ClaudeGenerator.

    generate() 본문(응답 파싱, 거부 처리, 키 검사)을 실제로 실행시키기 위한 것이다.
    FakeGenerator 는 프로토콜만 만족할 뿐 이 로직을 대신 검증하지 못한다.
    """
    from apps.ai_pipeline.client import ClaudeGenerator

    generator = ClaudeGenerator(api_key="test-key-not-real")
    generator._client = MagicMock()
    generator._client.messages.create.return_value = response
    return generator


class ClaudeGeneratorParsingTest(TestCase):
    """generate() 의 응답 파싱. 실제 API 는 부르지 않는다(SDK 를 mock 으로 대체)."""

    def call(self, generator, result_key: str = "words", max_items: int = 10):
        return generator.generate(
            system="s", user="u", schema={}, result_key=result_key, max_items=max_items
        )

    def test_parses_valid_response(self):
        response = make_response(json.dumps({"words": [make_item("deploy")]}))

        items = self.call(make_generator(response))

        self.assertEqual(items[0]["term"], "deploy")

    def test_refusal_raises_before_reading_content(self):
        """거부 응답은 content 를 읽기 전에 걸러야 한다."""
        response = make_response("", stop_reason="refusal")

        with self.assertRaises(GenerationError) as ctx:
            self.call(make_generator(response))

        self.assertIn("거부", str(ctx.exception))

    def test_broken_json_raises(self):
        response = make_response("{not json")

        with self.assertRaises(GenerationError) as ctx:
            self.call(make_generator(response))

        self.assertIn("JSON", str(ctx.exception))

    def test_empty_text_raises(self):
        with self.assertRaises(GenerationError):
            self.call(make_generator(make_response("")))

    def test_missing_result_key_raises(self):
        """스키마와 다른 키가 오면 조용히 빈 결과가 되면 안 된다."""
        response = make_response(json.dumps({"sentences": [make_item("x")]}))

        with self.assertRaises(GenerationError) as ctx:
            self.call(make_generator(response))

        self.assertIn("words", str(ctx.exception))

    def test_non_list_result_raises(self):
        response = make_response(json.dumps({"words": "문자열"}))

        with self.assertRaises(GenerationError):
            self.call(make_generator(response))

    def test_result_key_is_configurable(self):
        """문장·에러 메시지가 다른 키를 써도 동작해야 한다."""
        response = make_response(json.dumps({"sentences": [{"text": "hello"}]}))

        items = self.call(make_generator(response), result_key="sentences")

        self.assertEqual(items[0]["text"], "hello")

    def test_max_items_truncates(self):
        response = make_response(
            json.dumps({"words": [make_item(f"w{i}") for i in range(10)]})
        )

        items = self.call(make_generator(response), max_items=3)

        self.assertEqual(len(items), 3)

    def test_sdk_error_includes_exception_type(self):
        """원본 예외 타입이 메시지에 남아야 원인을 추적할 수 있다."""
        generator = make_generator(make_response("{}"))
        generator._client.messages.create.side_effect = ValueError("bad param")

        with self.assertRaises(GenerationError) as ctx:
            self.call(generator)

        self.assertIn("ValueError", str(ctx.exception))


class ClientSafetyTest(TestCase):
    def test_missing_api_key_raises_readable_error(self):
        """키가 없으면 SDK 예외가 아니라 안내 메시지가 나와야 한다."""
        from apps.ai_pipeline.client import ClaudeGenerator

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            with self.assertRaises(GenerationError) as ctx:
                ClaudeGenerator()

        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
