"""대량 생성의 가장자리 경우. 한 줄 설명이 지켜야 할 동작이다."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.ai_pipeline import bulk
from apps.ai_pipeline.management.commands.bulk_content import Command as BulkCommand
from apps.ai_pipeline.tests_bulk import PHRASE, WORD, _message
from apps.ai_pipeline.tests_bulk_dynamic import ScriptedBatches, _align, _phrase
from apps.vocab.models import Word
from apps.vocab.talk import is_speakable


class BulkEdgeCaseTest(TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.ws = bulk.Workspace(self.dir)

    def call(self, fake, *args):
        client = SimpleNamespace(messages=SimpleNamespace(batches=fake))
        with mock.patch.object(BulkCommand, "get_client", return_value=client):
            call_command("bulk_content", *args, "--dir", str(self.dir), stdout=StringIO(), stderr=StringIO())

    def test_tail_cut_inside_korean_char_is_skipped(self):
        """마지막 줄이 한글 글자 중간에서 끊겨도 그 줄만 건너뛰고 나머지를 읽는다."""
        p = self.ws.path("phrase", "enrich")
        p.parent.mkdir(parents=True, exist_ok=True)
        good = (json.dumps(PHRASE, ensure_ascii=False) + "\n").encode()
        tail = json.dumps(dict(PHRASE, key="p2"), ensure_ascii=False).encode()
        p.write_bytes(good + tail[: tail.index("화".encode()) + 1])
        self.assertEqual([i["key"] for i in self.ws.items("phrase", "enrich")], ["p1"])

    def test_leading_acronym_keeps_case_and_stays_unspeakable(self):
        """약어로 시작하는 표현(TV is broken)은 첫 글자를 내리지 않아 약어 검사에 걸린다."""
        cleaned = bulk.clean_phrase("TV is broken")
        self.assertFalse(is_speakable(cleaned), cleaned)

    def test_symbols_outside_old_emoji_ranges_are_caught(self):
        """범위 밖 이모지 U+23F0(알람 시계), U+231B(모래시계)도 칸 검사에 걸린다."""
        for ch in ("\u23f0", "\u231b"):
            with self.subTest(ch=ch):
                self.assertNotEqual(bulk.validate("phrase", dict(PHRASE, meaning="곧 가요 " + ch)), [])

    def test_phrase_passing_validate_also_aligns_on_screen(self):
        """칸 검사를 통과한 표현은 화면(alignParts)에서도 짝이 지어진다."""
        cases = [
            ("see you_later", "/si ju ˈleɪtər/", "씨 유 **레**이러r"),
            ("see you later", "/si ju ˈleɪtər/", "**** 유 **레**이러r"),
        ]
        for text, pron, reading in cases:
            with self.subTest(text=text, reading=reading):
                item = _phrase(text, pronunciation=pron, reading=reading)
                if bulk.validate("phrase", item) == []:
                    self.assertTrue(_align(text, pron, reading))

    def test_null_field_is_rejected_before_db(self):
        """null 칸은 칸 검사에서 걸러져 DB 오류 없이 0개가 들어간다."""
        path = self.dir / "w.jsonl"
        path.write_text(json.dumps({**WORD, "meaning": None, bulk.FINAL_MARK: True}) + "\n", encoding="utf-8")
        call_command("load_bulk_content", "word", str(path), stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Word.objects.count(), 0)

    def test_non_object_answer_fails_request_but_closes_batch(self):
        """응답이 객체가 아닌 JSON([])이면 그 요청만 실패로 두고 batch 는 닫힌다."""
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [PHRASE])
        msg = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="[]")],
                              usage=_message({}).usage)
        fake = ScriptedBatches(lambda c, p: msg)
        self.call(fake, "submit", "--kind", "phrase", "--stage", "review_meaning")
        self.call(fake, "collect")
        self.assertTrue(self.ws.batches()[0]["collected"])

    def test_unknown_custom_id_in_brainstorm_is_ignored(self):
        """후보 뽑기 결과에 기록에 없는 custom_id 가 와도 collect 가 죽지 않는다."""
        fake = ScriptedBatches(lambda c, p: _message({"items": ["see you later"]}))
        self.call(fake, "submit", "--kind", "phrase", "--stage", "brainstorm", "--max-requests", "1")
        fake.created[0][0]["custom_id"] = "bs-unknown"
        self.call(fake, "collect")

    def test_nan_budget_is_refused(self):
        """--budget nan 은 상한 비교를 늘 거짓으로 만들므로 받지 않는다."""
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [PHRASE])
        self.ws.add_usage("phrase", "review_meaning", "claude-sonnet-5-5", {"output_tokens": 100_000_000})
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        with self.assertRaises(CommandError):
            self.call(fake, "submit", "--kind", "phrase", "--stage", "review_meaning", "--budget", "nan")

    def test_unknown_verdict_is_not_counted_as_ok(self):
        """ok/fix/drop 이 아닌 판정은 통과로 세지 않는다."""
        counts = bulk.apply_review(self.ws, "phrase", "review_reading", {"p1": PHRASE},
                                   {"reviews": [{"key": "p1", "verdict": "unsure", "note": "", "fixes": []}]})
        self.assertEqual(counts["ok"], 0)

    def test_null_difficulty_fix_is_skipped(self):
        """난이도를 null 로 고치라는 답은 그 수정만 건너뛴다."""
        bulk.apply_review(self.ws, "phrase", "review_meaning", {"p1": PHRASE}, {"reviews": [
            {"key": "p1", "verdict": "fix", "note": "", "fixes": [{"field": "difficulty", "value": None}]}]})
