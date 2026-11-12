"""대량 생성 파이프라인의 경계 테스트. 실제 API 는 부르지 않는다.

tests_bulk.py 가 한 바퀴를 도는 것을 본다면, 여기서는 그 바퀴가 깨지기 쉬운
자리를 본다: 결과를 두 번 읽거나 읽다 끊길 때, 응답이 이상한 모양일 때,
비용 상한을 넘기는 길, 칸 검사가 화면과 같은 기준인지, 넣을 때 검수 대기로만
들어가는지.

작업 폴더는 모두 tempfile 로 만든 임시 폴더다. 가짜 batch 클라이언트는
Command.get_client 를 바꿔 끼운다.
"""

from __future__ import annotations

import json
import re
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from apps.ai_pipeline import bulk
from apps.ai_pipeline.management.commands.bulk_content import FIRST_RUN_MAX
from apps.ai_pipeline.management.commands.bulk_content import Command as BulkCommand
from apps.ai_pipeline.prompts import bulk as prompts
from apps.ai_pipeline.tests_bulk import PHRASE, WORD, _message
from apps.vocab.models import DailyPhrase, Sentence, Word

SENTENCE = {
    "key": "s1",
    "text": "Could you take a look at this PR?",
    "sentence_kind": "phrase",
    "reading": "**쿠**쥬 테잌 어 **룩** 앹 디s 피 **알**",
    "translation": "이 PR 좀 봐 줄래요?",
    "context": "리뷰를 부탁할 때",
    "description": "정중한 부탁",
    "category": "review",
    "difficulty": 1,
}


def _phrase(text: str, **extra) -> dict:
    """PHRASE 모양에 원문과 key 만 바꾼 항목."""
    return {**PHRASE, "key": bulk.item_key("phrase", text), "text": text, **extra}


def _failed(kind: str):
    """succeeded 가 아닌 결과(errored·expired·canceled)."""
    return SimpleNamespace(type=kind)


class ScriptedBatches:
    """messages.batches 자리. 요청마다 answer(custom_id, params) 가 돌려준 것을 결과로 준다.

    answer 가 SimpleNamespace(type=...) 를 돌려주면 succeeded 가 아닌 결과로 본다.
    break_after 를 주면 results 를 처음 읽을 때 그만큼 내준 뒤 연결이 끊긴다.
    retrieve_error 에 든 batch id 는 확인 단계에서 끊긴다.
    """

    def __init__(self, answer, break_after: int | None = None):
        self.answer = answer
        self.break_after = break_after
        self.created: list[list[dict]] = []
        self.reads: dict[str, int] = {}
        self.retrieve_error: set[str] = set()

    def create(self, requests):
        self.created.append(requests)
        return SimpleNamespace(id=f"b{len(self.created)}")

    def retrieve(self, batch_id):
        if batch_id in self.retrieve_error:
            raise httpx.ConnectError("connection refused")
        return SimpleNamespace(processing_status="ended", request_counts=None)

    def results(self, batch_id):
        self.reads[batch_id] = self.reads.get(batch_id, 0) + 1
        first_read = self.reads[batch_id] == 1
        requests = self.created[int(batch_id[1:]) - 1]
        for n, r in enumerate(requests):
            if first_read and self.break_after is not None and n == self.break_after:
                raise httpx.ReadError("stream cut")
            answer = self.answer(r["custom_id"], r["params"])
            if isinstance(answer, SimpleNamespace) and hasattr(answer, "type") and not hasattr(answer, "content"):
                result = answer
            else:
                result = SimpleNamespace(type="succeeded", message=answer)
            yield SimpleNamespace(custom_id=r["custom_id"], result=result)


class BulkCase(TestCase):
    """임시 작업 폴더와 가짜 클라이언트로 명령을 부르는 공통 셋업."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.ws = bulk.Workspace(self.dir)

    def call(self, fake: ScriptedBatches, *args) -> tuple[str, str]:
        client = SimpleNamespace(messages=SimpleNamespace(batches=fake))
        out, err = StringIO(), StringIO()
        with mock.patch.object(BulkCommand, "get_client", return_value=client):
            call_command("bulk_content", *args, "--dir", str(self.dir), stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def submit(self, fake, kind, stage, *extra) -> tuple[str, str]:
        return self.call(fake, "submit", "--kind", kind, "--stage", stage, *extra)

    def collect(self, fake) -> tuple[str, str]:
        return self.call(fake, "collect")

    def keys(self, kind: str, stage: str) -> list[str]:
        return [i["key"] for i in self.ws.items(kind, stage)]


# ---------------------------------------------------------------------------
# 결과 반영: 두 번 읽기, 읽다 끊기기, 이상한 응답
# ---------------------------------------------------------------------------


class CollectReplayTest(BulkCase):
    def setUp(self):
        super().setUp()
        # review_meaning 요청 두 개(25 + 1)가 나가게 enrich 를 26개 둔다. 발음 칸이
        # 세 낱말이라 원문도 세 낱말이어야 칸 검사를 통과한다.
        self.items = [_phrase(f"where's the {chr(97 + i // 26)}{chr(97 + i % 26)}") for i in range(26)]
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), self.items)

    @staticmethod
    def ok_all(cid, params):
        lines = params["messages"][0]["content"].split("\n\n", 1)[1].splitlines()
        keys = [json.loads(line)["key"] for line in lines]
        return _message({"reviews": [{"key": k, "verdict": "ok", "note": "", "fixes": []} for k in keys]})

    def test_collect_twice_does_not_apply_twice(self):
        """collect 를 두 번 돌려도 같은 결과가 두 번 쓰이지 않는다."""
        fake = ScriptedBatches(self.ok_all)
        self.submit(fake, "phrase", "review_meaning")
        self.collect(fake)
        out, _ = self.collect(fake)
        self.assertIn("기다리는 batch 가 없습니다", out)
        self.assertEqual(len(self.keys("phrase", "review_meaning")), 26)
        self.assertEqual(fake.reads, {"b1": 1})

    def test_stream_cut_midway_is_reread_without_duplicates(self):
        """결과를 읽다 끊기면 batch 를 안 닫고, 다시 읽을 때 이미 쓴 항목은 건너뛴다."""
        fake = ScriptedBatches(self.ok_all, break_after=1)
        self.submit(fake, "phrase", "review_meaning")
        _, err = self.collect(fake)
        self.assertIn("결과 읽기 실패, 다음에 다시", err)
        self.assertFalse(self.ws.batches()[0]["collected"])
        self.assertEqual(len(self.keys("phrase", "review_meaning")), 25)  # 첫 요청만 반영

        # 끊긴 batch 의 항목은 결과를 기다리는 중이라 다시 보내지 않는다.
        resend = ScriptedBatches(self.ok_all)
        out, _ = self.submit(resend, "phrase", "review_meaning")
        self.assertEqual(resend.created, [])

        self.collect(fake)
        keys = self.keys("phrase", "review_meaning")
        self.assertEqual(len(keys), 26)
        self.assertEqual(len(set(keys)), 26)
        self.assertTrue(self.ws.batches()[0]["collected"])

    def test_retrieve_failure_does_not_block_other_batches(self):
        """한 batch 를 확인하다 끊겨도 기다리던 다른 batch 는 반영된다."""
        fake = ScriptedBatches(self.ok_all)
        self.submit(fake, "phrase", "review_meaning", "--max-requests", "1")
        self.submit(fake, "phrase", "review_meaning")
        fake.retrieve_error.add("b1")
        _, err = self.collect(fake)
        self.assertIn("확인 실패, 다음에 다시: b1", err)
        state = {b["id"]: b["collected"] for b in self.ws.batches()}
        self.assertEqual(state, {"b1": False, "b2": True})
        fake.retrieve_error.clear()
        self.collect(fake)
        self.assertEqual(len(set(self.keys("phrase", "review_meaning"))), 26)


class OddAnswerTest(BulkCase):
    def setUp(self):
        super().setUp()
        self.a, self.b, self.c = _phrase("where's the bank"), _phrase("where's the park"), _phrase("where's the gym")
        bulk.append_jsonl(self.ws.path("phrase", "brainstorm"), [self.a, self.b, self.c])

    def test_enrich_duplicate_unknown_and_missing_keys(self):
        """같은 key 두 번은 첫 답만, 요청에 없는 key 는 무시, 빠진 key 는 다음에 다시."""
        def answer(cid, params):
            return _message({"items": [
                dict(self.a, meaning="은행이 어디예요"),
                dict(self.a, meaning="두 번째 답"),
                dict(self.a, key="not-in-request", text="hello there"),
                dict(self.b, reading="웨어z 더"),  # 낱말 수가 안 맞아 버린다
            ]})

        fake = ScriptedBatches(answer)
        self.submit(fake, "phrase", "enrich")
        self.collect(fake)
        enriched = self.ws.items("phrase", "enrich")
        self.assertEqual([(i["key"], i["meaning"]) for i in enriched], [(self.a["key"], "은행이 어디예요")])
        self.assertEqual([d["key"] for d in self.ws.dropped("phrase")], [self.b["key"]])
        send, _ = bulk._pending(self.ws, "phrase", "enrich")
        self.assertEqual([i["key"] for i in send], [self.c["key"]])

    def test_enrich_cannot_change_source_text_or_group(self):
        """모델이 원문을 고쳐 돌려줘도 우리 원문이 남는다."""
        def answer(cid, params):
            return _message({"items": [dict(self.a, text="Where is the BANK?")]})

        fake = ScriptedBatches(answer)
        self.submit(fake, "phrase", "enrich")
        self.collect(fake)
        item = self.ws.items("phrase", "enrich")[0]
        self.assertEqual(item["text"], "where's the bank")
        self.assertEqual(item["scene"], "asking")

    def test_refusal_non_json_errored_expired_all_retry(self):
        """거부, JSON 아님 은 실패로 세고 다시 나가며, 두 번 실패하면 버린다."""
        answers = iter([
            _message({}, stop_reason="refusal"),
            SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="not json")],
                            usage=_message({}).usage),
        ])
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [self.a])
        fake = ScriptedBatches(lambda c, p: next(answers))
        # 요청 하나씩 세 번 보내 각 실패를 따로 겪게 한다. 두 번째부터는 MAX_ATTEMPTS 에 걸린다.
        self.submit(fake, "phrase", "review_meaning")
        _, err = self.collect(fake)
        self.assertIn("거부됨", err)
        self.assertEqual(bulk._pending(self.ws, "phrase", "review_meaning")[0][0]["key"], self.a["key"])
        self.submit(fake, "phrase", "review_meaning")
        _, err = self.collect(fake)
        self.assertIn("JSON 이 아님", err)
        # 두 번 실패했으니 세 번째 submit 은 보내지 않고 버린다.
        third = ScriptedBatches(lambda c, p: _failed("expired"))
        out, _ = self.submit(third, "phrase", "review_meaning")
        self.assertEqual(third.created, [])
        self.assertIn("보낼 것이 없습니다", out)
        self.assertEqual(self.ws.dropped("phrase")[0]["stage"], "review_meaning")
        self.assertEqual(self.ws.items("phrase", "review_meaning"), [])

    def test_failed_results_do_not_count_usage(self):
        """errored·expired 는 사용량에 안 들어가고 batch 는 닫힌다."""
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [self.a])
        fake = ScriptedBatches(lambda c, p: _failed("expired"))
        self.submit(fake, "phrase", "review_meaning")
        out, _ = self.collect(fake)
        self.assertIn("failed 1", out)
        self.assertEqual(self.ws.spent(), 0)
        self.assertTrue(self.ws.batches()[0]["collected"])

    def test_review_fix_outside_editable_is_ignored(self):
        """검수가 원문·key 를 고치려 해도 안 바뀐다. 난이도는 숫자로 바뀐다."""
        out = bulk.apply_review(self.ws, "phrase", "review_meaning", {self.a["key"]: self.a}, {"reviews": [
            {"key": self.a["key"], "verdict": "fix", "note": "", "fixes": [
                {"field": "text", "value": "something else"},
                {"field": "key", "value": "zzz"},
                {"field": "difficulty", "value": "3"},
                {"field": "difficulty", "value": "어려움"},
            ]},
        ]})
        self.assertEqual(out["fix"], 1)
        item = self.ws.items("phrase", "review_meaning")[0]
        self.assertEqual((item["text"], item["key"], item["difficulty"]), (self.a["text"], self.a["key"], 3))

    def test_review_fix_that_breaks_fields_is_dropped(self):
        """고친 값이 칸 검사를 못 넘으면 통과가 아니라 버림이다."""
        out = bulk.apply_review(self.ws, "phrase", "review_reading", {self.a["key"]: self.a}, {"reviews": [
            {"key": self.a["key"], "verdict": "fix", "note": "", "fixes": [
                {"field": "reading", "value": "**웨어z 더** 뱅크"},
            ]},
        ]})
        self.assertEqual(out, {"ok": 0, "fix": 0, "drop": 1})
        self.assertEqual(bulk.final_items(self.ws, "phrase"), [])


# ---------------------------------------------------------------------------
# 후보 뽑기
# ---------------------------------------------------------------------------


class BrainstormTest(BulkCase):
    def test_same_candidate_from_two_topics_in_one_batch_is_kept_once(self):
        """한 batch 의 두 주제가 같은 후보를 내도 한 번만 남는다."""
        fake = ScriptedBatches(lambda c, p: _message({"items": ["Nice to meet you!", "nice to meet you"]}))
        self.submit(fake, "phrase", "brainstorm", "--max-requests", "2")
        self.collect(fake)
        texts = [i["text"] for i in self.ws.items("phrase", "brainstorm")]
        self.assertEqual(texts, ["nice to meet you"])

    def test_existing_copy_excludes_and_replaces_local_db(self):
        """existing.json(운영 사본)에 있는 것은 빠지고, 그게 있으면 로컬 DB 는 안 본다."""
        DailyPhrase.objects.create(text="thank you so much", pronunciation="/x/", reading="**땡**큐",
                                   meaning="고마워요", is_reviewed=True)
        (self.dir / "existing.json").write_text(json.dumps({"phrase": ["Where's the restroom?"]}), encoding="utf-8")
        fake = ScriptedBatches(lambda c, p: _message({"items": ["where's the restroom", "Thank you so much."]}))
        self.submit(fake, "phrase", "brainstorm", "--max-requests", "1")
        self.collect(fake)
        self.assertEqual([i["text"] for i in self.ws.items("phrase", "brainstorm")], ["thank you so much"])

    def test_failed_topic_retries_then_stops(self):
        """잘린 주제는 다시 나가고, MAX_ATTEMPTS 번 실패하면 다음 주제로 넘어간다."""
        first = prompts.topics("phrase")[0]["id"] + "#r1"
        fake = ScriptedBatches(lambda c, p: _message({}, stop_reason="max_tokens"))
        sent = []
        for _ in range(bulk.MAX_ATTEMPTS + 1):
            self.submit(fake, "phrase", "brainstorm", "--max-requests", "1")
            sent.append(self.ws.batches()[-1]["requests"]["bs-0"][0])
            self.collect(fake)
        self.assertEqual(sent[: bulk.MAX_ATTEMPTS], [first] * bulk.MAX_ATTEMPTS)
        self.assertNotEqual(sent[-1], first)

    def test_stream_cut_in_brainstorm_does_not_duplicate_candidates(self):
        """후보 뽑기 결과를 읽다 끊겨 다시 읽어도 후보가 두 벌 생기지 않고 주제는 끝난 것으로 남는다."""
        def answer(cid, params):
            return _message({"items": [f"good morning {cid}", "how are you doing"]})

        fake = ScriptedBatches(answer, break_after=1)
        self.submit(fake, "phrase", "brainstorm", "--max-requests", "2")
        self.collect(fake)
        self.collect(fake)
        texts = [i["text"] for i in self.ws.items("phrase", "brainstorm")]
        self.assertEqual(sorted(texts), ["good morning bs-0", "good morning bs-1", "how are you doing"])
        done = self.ws.batches()[0]["done"]
        self.assertEqual(len(done), 2)
        again = ScriptedBatches(answer)
        self.submit(again, "phrase", "brainstorm", "--max-requests", "2")
        sent = {k for r in again.created[0] for k in self.ws.batches()[-1]["requests"][r["custom_id"]]}
        self.assertFalse(sent & set(done))

    def test_too_long_candidate_is_skipped(self):
        """원문 칸 길이(DailyPhrase.text 120자)를 넘는 후보는 저장하지 않는다."""
        fake = ScriptedBatches(lambda c, p: _message({"items": ["word " * 30, "see you later"]}))
        self.submit(fake, "phrase", "brainstorm", "--max-requests", "1")
        self.collect(fake)
        self.assertEqual([i["text"] for i in self.ws.items("phrase", "brainstorm")], ["see you later"])


# ---------------------------------------------------------------------------
# 비용 상한
# ---------------------------------------------------------------------------


class BudgetTest(BulkCase):
    def _inflight(self, batch_id: str, stage: str, n_requests: int, effort: str | None = None) -> None:
        reqs = [bulk.Request(f"r{i}", {}, [f"{batch_id}-{i}"]) for i in range(n_requests)]
        self.ws.add_batch(batch_id, "word", stage, reqs, effort=effort)

    def test_usage_cost_applies_batch_discount(self):
        """100만 토큰당 정가의 절반. 캐시 읽기·쓰기도 각자 값으로 센다."""
        cost = bulk.usage_cost("claude-opus-5-5", {
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
        })
        self.assertAlmostEqual(cost, (4.0 + 20.0 + 0.20 + 5.0) / 2)
        self.assertAlmostEqual(bulk.worst_request_cost("enrich"), (20_000 * 4 + 32_000 * 20) / 1e6 / 2)

    def test_several_waiting_batches_add_up(self):
        """기다리는 batch 가 여럿이면 모두 더해서 상한을 본다."""
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [PHRASE])
        enrich, review = bulk.worst_request_cost("enrich"), bulk.worst_request_cost("review_meaning")
        budget = str(round(2 * enrich + review / 2, 4))  # 하나만 기다리면 통과, 둘이면 넘는다
        self._inflight("x1", "enrich", 1)
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        self.submit(fake, "phrase", "review_meaning", "--budget", budget)
        self.assertEqual(len(fake.created), 1)

        self.ws.save_batches([b for b in self.ws.batches() if b["id"] == "x1"])
        self._inflight("x2", "enrich", 1)
        blocked = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        with self.assertRaisesMessage(CommandError, "비용 상한"):
            self.submit(blocked, "phrase", "review_meaning", "--budget", budget)
        self.assertEqual(blocked.created, [])
        self.assertEqual([b["id"] for b in self.ws.batches()], ["x1", "x2"])  # 막힌 batch 는 기록되지 않는다

    def test_effort_batch_is_counted_at_worst_case(self):
        """평균을 알아도 --effort 로 보내면 최악값으로 센다. 기다리는 동안에도."""
        self.ws.add_usage("phrase", "review_meaning", "claude-sonnet-5-5", {"output_tokens": 100}, items=25)
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [PHRASE])
        budget = str(bulk.worst_request_cost("review_meaning") / 2)
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        with self.assertRaisesMessage(CommandError, "비용 상한"):
            self.submit(fake, "phrase", "review_meaning", "--effort", "low", "--budget", budget)
        self.submit(fake, "phrase", "review_meaning", "--budget", budget)  # 평균으로는 통과
        self.assertEqual(len(fake.created), 1)

        self._inflight("e1", "enrich", 1, effort="low")
        self.ws.add_usage("word", "enrich", "claude-opus-5-5", {"output_tokens": 10}, items=25)
        self.assertGreaterEqual(self.ws.inflight_estimate(), bulk.worst_request_cost("enrich"))

    def test_first_run_is_capped(self):
        """평균을 모르는 단계는 --max-requests 를 크게 줘도 FIRST_RUN_MAX 개까지만 보낸다."""
        n = prompts.CHUNK * (FIRST_RUN_MAX + 2)
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [_phrase(f"p {i}", key=f"k{i}") for i in range(n)])
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        self.submit(fake, "phrase", "review_meaning", "--max-requests", "100", "--budget", "1000")
        self.assertEqual(len(fake.created[0]), FIRST_RUN_MAX)

    def test_restart_after_usage_uses_average(self):
        """평균을 알게 된 뒤에는 상한이 풀려 남은 요청을 다 보낼 수 있다(예상은 평균으로)."""
        n = prompts.CHUNK * (FIRST_RUN_MAX + 2)
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [_phrase(f"p {i}", key=f"k{i}") for i in range(n)])
        self.ws.add_usage("phrase", "review_meaning", "claude-sonnet-5-5", {"output_tokens": 100}, items=25)
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        out, _ = self.submit(fake, "phrase", "review_meaning", "--budget", "1000")
        self.assertEqual(len(fake.created[0]), FIRST_RUN_MAX + 2)
        self.assertNotIn("최악값", out)

    def test_status_reports_spent_and_waiting(self):
        """status 는 쓴 돈과 기다리는 batch 의 예상을 보인다."""
        self._inflight("w1", "enrich", 2)
        self.ws.add_usage("word", "brainstorm", "claude-opus-5-5", {"output_tokens": 1_000_000}, items=1)
        out, _ = self.call(ScriptedBatches(None), "status")
        self.assertIn("쓴 돈 10.00달러", out)
        self.assertIn(f"기다리는 batch 예상 {2 * bulk.worst_request_cost('enrich'):.2f}달러", out)


# ---------------------------------------------------------------------------
# 칸 검사: 화면(talk-parts.ts)과 같은 기준인가
# ---------------------------------------------------------------------------


def _split_words(text: str) -> list[str]:
    """frontend/src/lib/talk-parts.ts splitWords 를 그대로 옮긴 것."""
    return [p for p in re.split(r"[\s-]+", text) if p]


def _align(term: str, pronunciation: str, reading: str) -> bool:
    """talk-parts.ts alignParts 가 null 이 아닌가(강조할 수 있는가)."""
    words = _split_words(term)
    ipas = _split_words(re.sub(r"/+$", "", re.sub(r"^/+", "", pronunciation.strip())))
    reading_words = _split_words(reading)
    reading_count = len(_split_words(reading.replace("**", "")))
    if len(words) < 2 or not ipas or not reading_words:
        return False
    return len(words) == len(ipas) == reading_count == len(reading_words)


class PhraseCountParityTest(TestCase):
    CASES = [
        ("where's the restroom", "/wɛrz ðə ˈrɛstruːm/", "웨어rz 더 **레**스트룸"),
        ("I'd love to", "/aɪd ˈlʌv tu/", "아이d **러**v 투"),
        ("check-in please", "/ˈtʃɛk ɪn pliz/", "**체**크 인 플리z"),
        ("what's up", "/wʌts ˈʌp/", "왓츠 **업**"),
        ("can I get a refund", "/kæn aɪ ɡɛt ə ˈrifʌnd/", "캔 아이 겟 어 **리**펀d"),
        ("see you later", "/si ju ˈleɪtər/", "씨-유 **레**이러r"),
    ]

    def test_valid_phrase_is_alignable_on_screen(self):
        """칸 검사를 통과한 표현은 화면도 낱말 단위로 짝지을 수 있다."""
        for text, pron, reading in self.CASES:
            with self.subTest(text=text):
                item = _phrase(text, pronunciation=pron, reading=reading)
                self.assertEqual(bulk.validate("phrase", item), [])
                self.assertTrue(_align(text, pron, reading))

    def test_misaligned_phrase_is_rejected(self):
        """화면이 짝짓지 못하는 표현은 칸 검사에서 걸린다."""
        bad = [
            ("check-in please", "/ˈtʃɛkɪn pliz/", "**체**킨 플리z"),  # 하이픈이 둘로 갈라 표현만 3
            ("what's up", "/wʌts ˈʌp/", "왓 츠 **업**"),
        ]
        for text, pron, reading in bad:
            with self.subTest(reading=reading):
                self.assertFalse(_align(text, pron, reading))
                self.assertNotEqual(bulk.validate("phrase", _phrase(text, pronunciation=pron, reading=reading)), [])

    def test_stress_across_boundary_is_rejected_even_when_counts_match(self):
        """낱말 수는 맞아도 강세가 공백·하이픈을 걸치면 버린다(화면은 개수만 봐서 못 거른다)."""
        for reading in ("씨 **유 레**이러r", "씨 **유-레**이러r"):
            with self.subTest(reading=reading):
                item = _phrase("see you later", pronunciation="/si ju ˈleɪtər/", reading=reading)
                self.assertTrue(any("경계" in p for p in bulk.validate("phrase", item)))


class ValidateEdgeTest(TestCase):
    def assertProblem(self, kind: str, item: dict, fragment: str) -> None:
        problems = bulk.validate(kind, item)
        self.assertTrue(any(fragment in p for p in problems), problems)

    def test_model_max_length_per_kind(self):
        """길이 상한은 각 모델의 max_length 를 따른다."""
        self.assertProblem("phrase", dict(PHRASE, meaning="가" * 201), "200자")
        self.assertProblem("word", dict(WORD, reading="**리**" + "베" * 120), "120자")
        self.assertProblem("word", dict(WORD, term="a" * 101), "100자")
        self.assertProblem("sentence", dict(SENTENCE, context="가" * 201), "200자")
        self.assertEqual(bulk.validate("word", dict(WORD, meaning="가" * 200)), [])

    def test_required_fields_blank_or_whitespace(self):
        for name in ("meaning", "pronunciation", "reading"):
            with self.subTest(name=name):
                self.assertProblem("phrase", dict(PHRASE, **{name: "   "}), "비어 있음")
        self.assertProblem("sentence", {k: v for k, v in SENTENCE.items() if k != "translation"}, "비어 있음")

    def test_choices_and_difficulty(self):
        self.assertProblem("word", dict(WORD, category="misc"), "분류")
        self.assertProblem("sentence", dict(SENTENCE, sentence_kind="warning"), "문장 종류")
        self.assertProblem("phrase", dict(PHRASE, scene="travel"), "상황")
        for bad in (0, 4, "2", None):
            with self.subTest(difficulty=bad):
                self.assertProblem("phrase", dict(PHRASE, difficulty=bad), "난이도")

    def test_emoji_and_jamo(self):
        self.assertProblem("word", dict(WORD, meaning="커밋 \U0001F600"), "이모지")
        self.assertProblem("sentence", dict(SENTENCE, description="좋아요 \u2705"), "이모지")
        self.assertProblem("word", dict(WORD, reading="**리**베이ㅅ"), "낱자모")
        self.assertProblem("word", dict(WORD, reading="**리**베이ᄉ"), "낱자모")

    def test_stress_markers(self):
        self.assertProblem("word", dict(WORD, reading="리베이s"), "강세")
        self.assertProblem("word", dict(WORD, reading="**리**베**이s"), "강세")
        self.assertProblem("word", dict(WORD, reading="rebase"), "한글이 없음")

    def test_pronunciation_slashes(self):
        for pron in ("/ˈribeɪs", "ˈribeɪs/", "//", "/ˈri/beɪs/"):
            with self.subTest(pron=pron):
                self.assertProblem("word", dict(WORD, pronunciation=pron), "슬래시")

    def test_multiword_terms_and_spelled_acronyms(self):
        """여러 낱말 용어는 발음기호·한글발음 낱말 수를 맞추고, 철자로 읽는 약어는 원문과 안 맞아도 된다."""
        ok = dict(WORD, term="race condition", pronunciation="/reɪs kənˈdɪʃən/", reading="레이s 컨**디**션")
        self.assertEqual(bulk.validate("word", ok), [])
        self.assertProblem("word", dict(ok, reading="레이s컨**디**션"), "낱말 수")
        hyphen = dict(WORD, term="end-to-end", pronunciation="/ˈɛnd tə ˈɛnd/", reading="**엔**d-투-엔d")
        self.assertEqual(bulk.validate("word", hyphen), [])
        acronym = dict(WORD, term="JSON", pronunciation="/ˈdʒeɪsən/", reading="**제**이슨")
        self.assertEqual(bulk.validate("word", acronym), [])

    def test_phrase_needs_speakable_ascii_text(self):
        self.assertProblem("phrase", _phrase("see you at 5", pronunciation="/si ju æt faɪv/",
                                             reading="씨 유 앳 **파**이v"), "채점")
        self.assertProblem("phrase", _phrase("one café please", pronunciation="/wʌn kæˈfeɪ pliz/",
                                             reading="원 캐**페**이 플리z"), "영문 아닌")


class CleanPhraseEdgeTest(TestCase):
    def test_punctuation_and_spacing(self):
        self.assertEqual(bulk.clean_phrase("  Hey,   how's it going?! "), "hey how's it going")
        self.assertEqual(bulk.clean_phrase("Well... I don't know."), "well I don't know")
        self.assertEqual(bulk.clean_phrase("Excuse me — where's the exit?"), "excuse me where's the exit")

    def test_pronoun_i_only(self):
        self.assertEqual(bulk.clean_phrase("i think i'm lost"), "I think I'm lost")
        self.assertEqual(bulk.clean_phrase("It is what it is"), "it is what it is")
        self.assertEqual(bulk.clean_phrase("Is it far"), "is it far")
        self.assertEqual(bulk.clean_phrase("Hi, I'll be there"), "hi I'll be there")
        self.assertEqual(bulk.clean_phrase("this is a wifi spot"), "this is a wifi spot")

    def test_empty_after_cleaning(self):
        self.assertEqual(bulk.clean_phrase("?!..."), "")

    def test_cleaned_output_is_speakable(self):
        """정리 뒤 남은 모양이 출제 검사(is_speakable)에 기호로 걸리지 않는다."""
        from apps.vocab.talk import is_speakable

        for raw in ("Where's the restroom?", "Sorry, I'm late!", "Could you say that again?"):
            with self.subTest(raw=raw):
                self.assertTrue(is_speakable(bulk.clean_phrase(raw)))


# ---------------------------------------------------------------------------
# 파일
# ---------------------------------------------------------------------------


class JsonlFileTest(BulkCase):
    def test_broken_middle_line_raises(self):
        """중간 줄이 깨졌으면 조용히 넘기지 않는다."""
        path = self.ws.path("word", "enrich")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "a"}\n{"key": \n{"key": "c"}\n', encoding="utf-8")
        with self.assertRaises(RuntimeError):
            bulk.read_jsonl(path)

    def test_broken_work_file_is_not_retried_as_api_error(self):
        """작업 파일이 깨진 것은 API 오류처럼 "다음에 다시" 로 넘기지 않고 멈춘다(--wait 무한 반복 방지)."""
        bulk.append_jsonl(self.ws.path("phrase", "enrich"), [PHRASE])
        fake = ScriptedBatches(lambda c, p: _message({"reviews": []}))
        self.submit(fake, "phrase", "review_meaning")
        path = self.ws.path("phrase", "enrich")
        path.write_text('{"key": \n' + path.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.collect(fake)

        path.write_text(json.dumps(PHRASE, ensure_ascii=False) + "\n", encoding="utf-8")
        self.ws.save_batches([])
        (self.dir / "existing.json").write_text("{broken", encoding="utf-8")
        brainstorm = ScriptedBatches(lambda c, p: _message({"items": []}))
        self.submit(brainstorm, "phrase", "brainstorm", "--max-requests", "1")
        with self.assertRaises(RuntimeError):
            self.collect(brainstorm)

    def test_broken_tail_with_only_one_line(self):
        """첫 줄부터 쓰다 끊긴 파일도 이어 쓰면 새 줄만 남는다."""
        path = self.ws.path("word", "enrich")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "a", "te', encoding="utf-8")
        self.assertEqual(bulk.read_jsonl(path), [])
        bulk.append_jsonl(path, [{"key": "b"}])
        self.assertEqual(bulk.read_jsonl(path), [{"key": "b"}])

    def test_export_twice_overwrites(self):
        """export 를 두 번 돌려도 최종본이 두 벌 쌓이지 않는다. 재확인 전 항목은 빠진다."""
        bulk.append_jsonl(self.ws.path("phrase", "review_reading"), [
            dict(PHRASE, changed=False), _phrase("see you soon", changed=True),
        ])
        for _ in range(2):
            self.call(ScriptedBatches(None), "export", "--kind", "phrase")
        final = bulk.read_jsonl(self.ws.path("phrase", "final"))
        self.assertEqual([i["key"] for i in final], [PHRASE["key"]])
        self.assertTrue(final[0][bulk.FINAL_MARK])

    def test_commands_need_dir_and_kind(self):
        with self.assertRaisesMessage(CommandError, "작업 폴더"):
            with mock.patch.dict("os.environ", {"BULK_CONTENT_DIR": ""}):
                call_command("bulk_content", "status", "--dir", "", stdout=StringIO())
        with self.assertRaisesMessage(CommandError, "--kind"):
            self.call(ScriptedBatches(None), "submit", "--stage", "enrich")
        with self.assertRaisesMessage(CommandError, "--stage"):
            self.call(ScriptedBatches(None), "submit", "--kind", "word")


# ---------------------------------------------------------------------------
# 넣기: 항상 검수 대기로, 반쯤 들어가지 않게
# ---------------------------------------------------------------------------


class LoadEdgeTest(TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def write(self, name: str, rows: list[dict], *, mark: bool = True, bom: bool = False) -> Path:
        path = self.dir / name
        body = "".join(json.dumps({**r, **({bulk.FINAL_MARK: True} if mark else {})}, ensure_ascii=False) + "\n"
                       for r in rows)
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + body.encode("utf-8"))
        return path

    def load(self, kind: str, path: str, *extra) -> str:
        out = StringIO()
        call_command("load_bulk_content", kind, path, *extra, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_one_unmarked_line_blocks_whole_file(self):
        """표시 없는 줄이 하나라도 있으면 아무것도 넣지 않는다."""
        path = self.dir / "mixed.jsonl"
        path.write_text(
            json.dumps({**WORD, bulk.FINAL_MARK: True}, ensure_ascii=False) + "\n"
            + json.dumps(dict(WORD, term="squash"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesMessage(CommandError, "검수 2회 표시"):
            self.load("word", str(path))
        self.assertEqual(Word.objects.count(), 0)

    def test_reviewed_flags_in_file_are_ignored(self):
        """파일에 is_reviewed=True 가 들어 있어도 검수 대기로 들어간다."""
        path = self.write("w.jsonl", [dict(WORD, is_reviewed=True, reading_reviewed=True)])
        self.load("word", str(path))
        word = Word.objects.get(term="rebase")
        self.assertFalse(word.is_reviewed)
        self.assertFalse(word.reading_reviewed)
        self.assertEqual(word.source, "AI 생성(일괄)")

    def test_bom_file_and_stdin(self):
        """BOM 붙은 파일과 표준 입력(바이트, BOM, 한글)을 모두 읽는다."""
        path = self.write("p.jsonl", [PHRASE], bom=True)
        self.load("phrase", str(path))
        self.assertFalse(DailyPhrase.objects.get(text=PHRASE["text"]).is_reviewed)

        data = b"\xef\xbb\xbf" + self.write("s.jsonl", [SENTENCE]).read_bytes()
        with mock.patch("sys.stdin", SimpleNamespace(buffer=BytesIO(data))):
            self.load("sentence", "-")
        sentence = Sentence.objects.get(slug="bulk-s1")
        self.assertEqual(sentence.translation, SENTENCE["translation"])
        self.assertFalse(sentence.is_reviewed or sentence.reading_reviewed)

    def test_existing_source_different_case_is_skipped(self):
        """이미 있는 원문은 대소문자·끝 구두점이 달라도 건너뛴다."""
        Word.objects.create(term="Rebase", meaning="x", category="git", is_reviewed=True)
        DailyPhrase.objects.create(text="Where's the restroom?", pronunciation="/x/", reading="**x**",
                                   meaning="x", is_reviewed=True)
        Sentence.objects.create(text="could you take a look at this pr", translation="x", is_reviewed=True)
        self.assertIn("이미 있어 건너뜀 1개", self.load("word", str(self.write("w.jsonl", [WORD]))))
        self.assertIn("이미 있어 건너뜀 1개", self.load("phrase", str(self.write("p.jsonl", [PHRASE]))))
        self.assertIn("이미 있어 건너뜀 1개", self.load("sentence", str(self.write("s.jsonl", [SENTENCE]))))
        self.assertEqual(Word.objects.count(), 1)
        self.assertEqual(Sentence.objects.count(), 1)

    def test_same_file_twice_and_duplicates_inside_file(self):
        """같은 파일 두 번, 파일 안의 대소문자만 다른 두 줄 모두 한 벌만 들어간다."""
        path = self.write("w.jsonl", [WORD, dict(WORD, key="w2", term="REBASE")])
        self.assertIn("넣은 것 1개", self.load("word", str(path)))
        self.assertIn("넣은 것 0개", self.load("word", str(path)))
        self.assertEqual(Word.objects.count(), 1)

        s = self.write("s.jsonl", [SENTENCE, dict(SENTENCE, text="Could you take a look at this PR")])
        self.load("sentence", str(s))
        self.load("sentence", str(s))
        self.assertEqual(Sentence.objects.count(), 1)

    def test_invalid_lines_skipped_rest_loaded(self):
        """칸 검사에 걸린 줄만 빠지고 나머지는 들어간다."""
        path = self.write("w.jsonl", [WORD, dict(WORD, key="w2", term="squash", category="nope")])
        out = self.load("word", str(path))
        self.assertIn("넣은 것 1개", out)
        self.assertIn("칸 검사 실패 1개", out)
        self.assertFalse(Word.objects.filter(term="squash").exists())

    def test_db_error_mid_insert_rolls_back_everything(self):
        """넣는 도중 DB 오류가 나면 반쯤 들어간 채로 남지 않는다."""
        path = self.write("w.jsonl", [WORD, dict(WORD, key="w2", term="squash")])

        def half_then_fail(rows, batch_size=None):
            rows[0].save()
            raise IntegrityError("simulated")

        with mock.patch.object(Word.objects, "bulk_create", side_effect=half_then_fail):
            with self.assertRaises(IntegrityError):
                self.load("word", str(path))
        self.assertEqual(Word.objects.count(), 0)

    def test_wrong_kind_inserts_nothing(self):
        """단어 파일을 일상 표현으로 넣으면 하나도 안 들어간다."""
        out = self.load("phrase", str(self.write("w.jsonl", [WORD])))
        self.assertIn("넣은 것 0개", out)
        self.assertEqual(DailyPhrase.objects.count(), 0)

    def test_bad_input_is_command_error(self):
        with self.assertRaisesMessage(CommandError, "파일을 열지"):
            self.load("word", str(self.dir / "missing.jsonl"))
        bad = self.dir / "bad.jsonl"
        bad.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "JSON 줄"):
            self.load("word", str(bad))
        arr = self.dir / "arr.jsonl"
        arr.write_text("[1, 2]\n", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "객체"):
            self.load("word", str(arr))

    def test_dry_run_then_real(self):
        path = str(self.write("p.jsonl", [PHRASE]))
        self.assertIn("넣을 것 1개", self.load("phrase", path, "--dry-run"))
        self.assertEqual(DailyPhrase.objects.count(), 0)
        self.assertIn("넣은 것 1개", self.load("phrase", path))


class LoadedItemsStayHiddenTest(TestCase):
    """넣은 항목이 사용자 조회 경로(목록·검색·상세·소리내어 읽기)에 하나도 안 나온다."""

    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        mark = {bulk.FINAL_MARK: True}
        for kind, row in (("word", WORD), ("sentence", SENTENCE), ("phrase", PHRASE)):
            path = folder / f"{kind}.jsonl"
            path.write_text(json.dumps({**row, **mark}, ensure_ascii=False) + "\n", encoding="utf-8")
            call_command("load_bulk_content", kind, str(path), stdout=StringIO())
        self.word = Word.objects.get(term="rebase")
        self.sentence = Sentence.objects.get(slug="bulk-s1")

    def test_word_hidden(self):
        listed = self.client.get("/api/vocab/words/", {"search": "rebase"}).json()["results"]
        self.assertNotIn("rebase", [w["term"] for w in listed])
        self.assertNotIn("rebase", [w["term"] for w in self.client.get("/api/vocab/words/").json()["results"]])
        self.assertEqual(self.client.get(f"/api/vocab/words/{self.word.pk}/").status_code, 404)

    def test_sentence_hidden(self):
        listed = self.client.get("/api/vocab/sentences/").json()["results"]
        self.assertNotIn(self.sentence.pk, [s["id"] for s in listed])
        self.assertEqual(self.client.get(f"/api/vocab/sentences/{self.sentence.pk}/").status_code, 404)

    def test_talk_does_not_serve_loaded_items(self):
        for kind in ("dev", "daily"):
            with self.subTest(kind=kind):
                res = self.client.get("/api/vocab/talk/question/", {"kind": kind})
                body = res.json() if res.status_code == 200 else {}
                self.assertNotIn(body.get("term"), ("rebase", PHRASE["text"]))
