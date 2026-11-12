"""대량 생성 파이프라인 테스트. 실제 API 는 부르지 않는다(가짜 batch 클라이언트)."""

from __future__ import annotations

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
from apps.vocab.models import DailyPhrase, Sentence, Word

PHRASE = {
    "key": "p1",
    "text": "where's the restroom",
    "scene": "asking",
    "topic": "길 묻기",
    "topic_id": "asking:길 묻기",
    "pronunciation": "/wɛrz ðə ˈrɛstruːm/",
    "reading": "웨어rz 더 **레**스트룸",
    "meaning": "화장실이 어디예요",
    "difficulty": 1,
}
WORD = {
    "key": "w1",
    "term": "rebase",
    "category": "git",
    "topic": "브랜치와 병합",
    "topic_id": "git:브랜치와 병합",
    "meaning": "커밋 기준점 옮기기",
    "pronunciation": "/ˈribeɪs/",
    "reading": "**리**베이s",
    "aliases": "리베이스",
    "description": "브랜치의 시작점을 옮긴다.",
    "example": "Please rebase onto main.",
    "example_translation": "main 위로 리베이스해 주세요.",
    "difficulty": 2,
}


def _message(payload: dict, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
    )


class FakeBatches:
    """messages.batches 자리. create 로 받은 요청에 answer(custom_id, params) 로 답한다."""

    def __init__(self, answer):
        self.answer = answer
        self.created: list[list[dict]] = []

    def create(self, requests):
        self.created.append(requests)
        return SimpleNamespace(id=f"b{len(self.created)}")

    def retrieve(self, batch_id):
        return SimpleNamespace(processing_status="ended", request_counts=None)

    def results(self, batch_id):
        requests = self.created[int(batch_id[1:]) - 1]
        for r in requests:
            yield SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(type="succeeded", message=self.answer(r["custom_id"], r["params"])),
            )


class ValidateTest(TestCase):
    def test_phrase_ok(self):
        self.assertEqual(bulk.validate("phrase", PHRASE), [])

    def test_phrase_word_count_mismatch(self):
        bad = dict(PHRASE, reading="웨어rz 더 **레**스트룸 요")
        self.assertTrue(any("낱말 수" in p for p in bulk.validate("phrase", bad)))

    def test_phrase_stress_across_space(self):
        bad = dict(PHRASE, reading="**웨어rz 더** 레스트룸")
        self.assertTrue(any("경계" in p for p in bulk.validate("phrase", bad)))

    def test_phrase_not_speakable(self):
        bad = dict(PHRASE, text="OK see you at 5")
        self.assertTrue(any("채점" in p for p in bulk.validate("phrase", bad)))

    def test_word_needs_slashes_and_stress(self):
        bad = dict(WORD, pronunciation="ˈribeɪs", reading="리베이s")
        problems = bulk.validate("word", bad)
        self.assertTrue(any("슬래시" in p for p in problems))
        self.assertTrue(any("강세" in p for p in problems))

    def test_length_limit_from_model(self):
        bad = dict(WORD, meaning="가" * 201)
        self.assertTrue(any("200자" in p for p in bulk.validate("word", bad)))


class PipelineTest(TestCase):
    """후보 -> 채우기 -> 1차 -> 2차 -> 재확인 -> 내보내기 -> 넣기를 가짜 응답으로 한 바퀴."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        Word.objects.create(term="commit", meaning="커밋", category="git", is_reviewed=True)

    def run_cmd(self, *args, answer):
        fake = FakeBatches(answer)
        client = SimpleNamespace(messages=SimpleNamespace(batches=fake))
        with mock.patch.object(BulkCommand, "get_client", return_value=client):
            out = StringIO()
            call_command("bulk_content", *args, "--dir", str(self.dir), stdout=out, stderr=StringIO())
            call_command("bulk_content", "collect", "--dir", str(self.dir), stdout=out, stderr=StringIO())
        return fake, out.getvalue()

    def test_full_round_trip_for_words(self):
        # 1) 후보: 이미 있는 commit 과 대소문자만 다른 Rebase 중복은 빠진다
        def brainstorm(cid, params):
            return _message({"items": ["Commit", "rebase", "Rebase", "cherry-pick"]})

        fake, _ = self.run_cmd("submit", "--kind", "word", "--stage", "brainstorm", "--max-requests", "1",
                               answer=brainstorm)
        prompt = fake.created[0][0]["params"]["messages"][0]["content"]
        self.assertIn("commit", prompt)  # 같은 분류의 기존 단어를 빼 달라고 한다
        terms = [i["term"] for i in bulk.Workspace(self.dir).items("word", "brainstorm")]
        self.assertEqual(terms, ["rebase", "cherry-pick"])

        ws = bulk.Workspace(self.dir)
        keys = {i["term"]: i["key"] for i in ws.items("word", "brainstorm")}

        # 2) 채우기: cherry-pick 은 발음기호 슬래시가 없어 칸 검사에서 버려진다
        def enrich(cid, params):
            return _message({"items": [
                dict(WORD, key=keys["rebase"], term="REBASE"),  # 원문을 바꿔 와도 우리 원문을 쓴다
                dict(WORD, key=keys["cherry-pick"], term="cherry-pick", pronunciation="tʃɛri pɪk"),
            ]})

        self.run_cmd("submit", "--kind", "word", "--stage", "enrich", answer=enrich)
        enriched = ws.items("word", "enrich")
        self.assertEqual([i["term"] for i in enriched], ["rebase"])
        self.assertEqual(ws.dropped("word")[0]["stage"], "enrich")

        # 3) 1차: 고침
        def review1(cid, params):
            self.assertEqual(params["model"], "claude-sonnet-5-5")
            return _message({"reviews": [{"key": keys["rebase"], "verdict": "fix", "note": "뜻 보강",
                                          "fixes": [{"field": "meaning", "value": "브랜치 기준점 옮기기"}]}]})

        self.run_cmd("submit", "--kind", "word", "--stage", "review_meaning", answer=review1)
        self.assertEqual(ws.items("word", "review_meaning")[0]["meaning"], "브랜치 기준점 옮기기")

        # 4) 2차: 한글발음을 고침 -> changed 표시 -> 재확인 대상
        def review2(cid, params):
            return _message({"reviews": [{"key": keys["rebase"], "verdict": "fix", "note": "강세",
                                          "fixes": [{"field": "reading", "value": "**뤼**베이s"}]}]})

        self.run_cmd("submit", "--kind", "word", "--stage", "review_reading", answer=review2)
        self.assertTrue(ws.items("word", "review_reading")[0]["changed"])
        self.assertEqual(bulk.final_items(ws, "word"), [])  # 재확인 전에는 최종본에 없다

        def recheck(cid, params):
            return _message({"reviews": [{"key": keys["rebase"], "verdict": "ok", "note": "", "fixes": []}]})

        self.run_cmd("submit", "--kind", "word", "--stage", "recheck", answer=recheck)
        final = bulk.final_items(ws, "word")
        self.assertEqual([(i["term"], i["reading"]) for i in final], [("rebase", "**뤼**베이s")])

        # 5) 내보내기 -> 넣기: 검수 대기로 들어가고 두 번 넣어도 한 벌
        call_command("bulk_content", "export", "--kind", "word", "--dir", str(self.dir), stdout=StringIO())
        path = ws.path("word", "final")
        for _ in range(2):
            call_command("load_bulk_content", "word", str(path), stdout=StringIO(), stderr=StringIO())
        word = Word.objects.get(term="rebase")
        self.assertFalse(word.is_reviewed)
        self.assertFalse(word.reading_reviewed)
        self.assertEqual(Word.objects.filter(term__iexact="rebase").count(), 1)

    def test_recheck_turns_fix_into_drop(self):
        ws = bulk.Workspace(self.dir)
        bulk.append_jsonl(ws.path("phrase", "review_reading"), [dict(PHRASE, changed=True)])

        def recheck(cid, params):
            return _message({"reviews": [{"key": "p1", "verdict": "fix", "note": "아직 틀림",
                                          "fixes": [{"field": "meaning", "value": "x"}]}]})

        self.run_cmd("submit", "--kind", "phrase", "--stage", "recheck", answer=recheck)
        self.assertEqual(ws.items("phrase", "recheck"), [])
        self.assertEqual(ws.dropped("phrase")[0]["stage"], "recheck")

    def test_missing_answer_is_retried_then_dropped(self):
        ws = bulk.Workspace(self.dir)
        bulk.append_jsonl(ws.path("phrase", "enrich"), [PHRASE])

        def silent(cid, params):
            return _message({"reviews": []})

        for _ in range(bulk.MAX_ATTEMPTS):
            fake, _ = self.run_cmd("submit", "--kind", "phrase", "--stage", "review_meaning", answer=silent)
            self.assertEqual(len(fake.created), 1)
        fake, out = self.run_cmd("submit", "--kind", "phrase", "--stage", "review_meaning", answer=silent)
        self.assertEqual(fake.created, [])
        self.assertIn("응답에 없음", ws.dropped("phrase")[0]["reason"])

    def test_budget_blocks_submit(self):
        ws = bulk.Workspace(self.dir)
        ws.add_usage("phrase", "review_meaning", "claude-sonnet-5-5",
                     {"input_tokens": 0, "output_tokens": 10_000_000})  # 50달러
        bulk.append_jsonl(ws.path("phrase", "enrich"), [PHRASE])
        with self.assertRaises(CommandError):
            self.run_cmd("submit", "--kind", "phrase", "--stage", "review_meaning", "--budget", "40",
                         answer=lambda c, p: _message({"reviews": []}))

    def test_truncated_answer_keeps_items_for_retry(self):
        ws = bulk.Workspace(self.dir)
        bulk.append_jsonl(ws.path("phrase", "enrich"), [PHRASE])
        self.run_cmd("submit", "--kind", "phrase", "--stage", "review_meaning",
                     answer=lambda c, p: _message({}, stop_reason="max_tokens"))
        send, _ = bulk._pending(ws, "phrase", "review_meaning")
        self.assertEqual([i["key"] for i in send], ["p1"])


class LoadTest(TestCase):
    def test_sentence_and_phrase_load_as_unreviewed(self):
        folder = Path(tempfile.mkdtemp())
        sentence = {
            "key": "s1", "text": "Could you take a look at this PR?", "sentence_kind": "phrase",
            "reading": "**쿠**쥬 테잌 어 **룩** 앹 디s 피 **알**", "translation": "이 PR 좀 봐 줄래요?",
            "context": "리뷰를 부탁할 때", "description": "정중한 부탁", "category": "review", "difficulty": 1,
        }
        mark = {bulk.FINAL_MARK: True}
        (folder / "s.jsonl").write_text(json.dumps({**sentence, **mark}, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "p.jsonl").write_text(json.dumps({**PHRASE, **mark}, ensure_ascii=False) + "\n", encoding="utf-8")
        call_command("load_bulk_content", "sentence", str(folder / "s.jsonl"), stdout=StringIO())
        call_command("load_bulk_content", "phrase", str(folder / "p.jsonl"), stdout=StringIO())
        s = Sentence.objects.get(slug="bulk-s1")
        self.assertFalse(s.is_reviewed or s.reading_reviewed)
        self.assertFalse(DailyPhrase.objects.get(text=PHRASE["text"]).is_reviewed)

    def test_dry_run_writes_nothing(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "w.jsonl").write_text(json.dumps({**WORD, bulk.FINAL_MARK: True}, ensure_ascii=False) + "\n", encoding="utf-8")
        call_command("load_bulk_content", "word", str(folder / "w.jsonl"), "--dry-run", stdout=StringIO())
        self.assertFalse(Word.objects.filter(term="rebase").exists())


class CleanPhraseTest(TestCase):
    def test_matches_existing_style(self):
        # 기존 207개처럼 문장부호 없이, 첫 글자는 대명사 I 만 대문자
        self.assertEqual(bulk.clean_phrase("Where have you been?"), "where have you been")
        self.assertEqual(bulk.clean_phrase("Sorry, I forgot your name."), "sorry I forgot your name")
        self.assertEqual(bulk.clean_phrase("I'm new here."), "I'm new here")
        self.assertEqual(bulk.clean_phrase("It's nice  to meet you!"), "it's nice to meet you")
        self.assertTrue(bulk.validate("phrase", dict(PHRASE, text=bulk.clean_phrase("Where's the restroom?"))) == [])


class EdgeCaseTest(TestCase):
    """대명사·중복 답·최악값 예상·실패한 주제·여러 낱말 용어·낱자모·넣기 거부."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.ws = bulk.Workspace(self.dir)

    def test_pronoun_I_stays_upper(self):
        self.assertEqual(bulk.clean_phrase("I need help."), "I need help")
        self.assertEqual(bulk.clean_phrase("Is this seat taken?"), "is this seat taken")
        self.assertEqual(bulk.clean_phrase("I’m lost"), "I'm lost")

    def test_duplicate_key_keeps_first_answer(self):
        base = {"p1": PHRASE}
        counts = bulk.apply_review(self.ws, "phrase", "review_meaning", base, {"reviews": [
            {"key": "p1", "verdict": "drop", "note": "x", "fixes": []},
            {"key": "p1", "verdict": "ok", "note": "", "fixes": []},
        ]})
        self.assertEqual(counts["drop"], 1)
        self.assertEqual(self.ws.items("phrase", "review_meaning"), [])

    def test_unknown_average_uses_worst_case(self):
        # 평균을 모르는 단계의 기다리는 batch 도 0 이 아니라 최악값으로 센다
        req = bulk.Request("x", {}, ["k"])
        self.ws.add_batch("b1", "word", "enrich", [req])
        self.assertGreater(self.ws.inflight_estimate(), 0.1)

    def test_failed_brainstorm_topic_is_retried(self):
        topic = bulk.prompts.topics("phrase")[0]
        round_key = f"{topic['id']}#r1"
        batches = [{"id": "b1", "kind": "phrase", "stage": "brainstorm", "created": "",
                    "requests": {"bs-0": [round_key]}, "collected": True, "done": []}]
        self.ws.save_batches(batches)
        again = bulk.brainstorm_requests(self.ws, "phrase", 10, 1, 1)
        self.assertEqual(again[0].keys, [round_key])

    def test_multiword_term_checks_parts(self):
        bad = dict(WORD, term="pull request", pronunciation="/pʊl rɪˈkwɛst/", reading="**풀 리**퀘스트")
        self.assertTrue(any("경계" in p for p in bulk.validate("word", bad)))
        acronym = dict(WORD, term="API", pronunciation="/ˌeɪ pi ˈaɪ/", reading="에이 피 **아이**")
        self.assertEqual(bulk.validate("word", acronym), [])

    def test_jamo_in_reading(self):
        bad = dict(PHRASE, reading="웨어rz ㄷ **레**스트룸")
        self.assertTrue(any("낱자모" in p for p in bulk.validate("phrase", bad)))

    def test_load_refuses_unreviewed_file(self):
        path = self.dir / "enrich.jsonl"
        bulk.append_jsonl(path, [WORD])
        with self.assertRaises(CommandError):
            call_command("load_bulk_content", "word", str(path), stdout=StringIO())


class CostAndFileTest(TestCase):
    def setUp(self):
        self.ws = bulk.Workspace(Path(tempfile.mkdtemp()))

    def test_effort_batch_does_not_lower_default_average(self):
        # low 로 보낸 batch 의 싼 비용이 기본 batch 의 평균으로 섞이면 예상이 낮아 상한이 샌다
        self.ws.add_usage("word", "enrich", "claude-opus-5-5", {"output_tokens": 1000}, items=25, effort="low")
        self.assertIsNone(self.ws.avg_item_cost("word", "enrich"))
        self.assertGreater(self.ws.estimate("word", "enrich", [25]), 0.1)  # 최악값
        self.assertGreater(self.ws.spent(), 0)  # 쓴 돈에는 들어간다

    def test_estimate_is_per_item(self):
        # 꼬리 묶음(항목 1개) 하나로 잰 평균이 25개짜리 요청을 싸게 보이게 하지 않는다
        self.ws.add_usage("word", "recheck", "claude-sonnet-5-5", {"output_tokens": 1000}, items=1)
        one = self.ws.estimate("word", "recheck", [1])
        self.assertAlmostEqual(self.ws.estimate("word", "recheck", [25]), one * 25)

    def test_append_after_broken_tail(self):
        path = self.ws.path("word", "enrich")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "a"}\n{"key": "b", "te', encoding="utf-8")
        bulk.append_jsonl(path, [{"key": "c"}])
        bulk.append_jsonl(path, [{"key": "d"}])
        self.assertEqual([r["key"] for r in bulk.read_jsonl(path)], ["a", "c", "d"])


class ReviewCanFixGroupTest(TestCase):
    def test_review_can_move_phrase_to_other_scene(self):
        ws = bulk.Workspace(Path(tempfile.mkdtemp()))
        bulk.apply_review(ws, "phrase", "review_meaning", {"p1": PHRASE}, {"reviews": [
            {"key": "p1", "verdict": "fix", "note": "", "fixes": [{"field": "scene", "value": "trouble"}]},
        ]})
        self.assertEqual(ws.items("phrase", "review_meaning")[0]["scene"], "trouble")

    def test_lowercase_pronoun_is_raised(self):
        self.assertEqual(bulk.clean_phrase("can i help you"), "can I help you")


class FileAndReviewEdgeTest(TestCase):
    def setUp(self):
        self.ws = bulk.Workspace(Path(tempfile.mkdtemp()))

    def test_complete_tail_without_newline_is_kept(self):
        path = self.ws.path("word", "enrich")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "a"}\n{"key": "b"}', encoding="utf-8")
        bulk.append_jsonl(path, [{"key": "c"}])
        self.assertEqual([r["key"] for r in bulk.read_jsonl(path)], ["a", "b", "c"])

    def test_line_separator_in_note_does_not_split_row(self):
        path = self.ws.path("word", "dropped")
        bulk.append_jsonl(path, [{"key": "a", "reason": "x\u2028y"}, {"key": "b", "reason": ""}])
        self.assertEqual([r["key"] for r in bulk.read_jsonl(path)], ["a", "b"])

    def test_broken_middle_line_is_not_json_error(self):
        # collect 가 JSONDecodeError 를 "다음에 다시" 로 넘기므로 다른 오류로 올라와야 한다
        path = self.ws.path("word", "enrich")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"key": "a"}\n{"key": \n{"key": "c"}\n', encoding="utf-8")
        with self.assertRaises(RuntimeError):
            bulk.read_jsonl(path)

    def test_unknown_scene_fix_is_skipped_not_dropped(self):
        bulk.apply_review(self.ws, "phrase", "review_meaning", {"p1": PHRASE}, {"reviews": [
            {"key": "p1", "verdict": "fix", "note": "", "fixes": [{"field": "scene", "value": "problem"}]},
        ]})
        self.assertEqual(self.ws.items("phrase", "review_meaning")[0]["scene"], "asking")

    def test_brainstorm_estimate_scales_with_per_topic(self):
        self.ws.add_usage("word", "brainstorm", "claude-opus-5-5", {"output_tokens": 1000}, items=50)
        self.assertAlmostEqual(
            self.ws.estimate("word", "brainstorm", [200]), self.ws.estimate("word", "brainstorm", [50]) * 4
        )


class ContractAndRecheckTest(TestCase):
    def setUp(self):
        self.ws = bulk.Workspace(Path(tempfile.mkdtemp()))

    def test_uncontracted_phrase_is_rejected(self):
        # 사람이 where's 로 줄여 읽으면 낱말 수가 어긋나 맞게 읽어도 오답이 된다
        bad = dict(PHRASE, text="where is the restroom", pronunciation="/wɛr ɪz ðə ˈrɛstrum/",
                   reading="웨어r 이z 더 **레**스트룸")
        self.assertTrue(any("풀어 쓴" in p for p in bulk.validate("phrase", bad)))

    def test_fix_without_change_goes_to_recheck(self):
        bulk.apply_review(self.ws, "phrase", "review_reading", {"p1": PHRASE}, {"reviews": [
            {"key": "p1", "verdict": "fix", "note": "틀림", "fixes": []},
        ]})
        self.assertTrue(self.ws.items("phrase", "review_reading")[0]["changed"])
        self.assertEqual(bulk.final_items(self.ws, "phrase"), [])

    def test_first_review_fix_is_rechecked(self):
        bulk.apply_review(self.ws, "phrase", "review_meaning", {"p1": PHRASE}, {"reviews": [
            {"key": "p1", "verdict": "fix", "note": "", "fixes": [{"field": "meaning", "value": "화장실 어디예요"}]},
        ]})
        item = self.ws.items("phrase", "review_meaning")[0]
        bulk.apply_review(self.ws, "phrase", "review_reading", {"p1": item}, {"reviews": [
            {"key": "p1", "verdict": "ok", "note": "", "fixes": []},
        ]})
        self.assertTrue(self.ws.items("phrase", "review_reading")[0]["changed"])

    def test_error_decoration_is_stripped(self):
        self.assertEqual(bulk.strip_decoration("\u2502 Error: Invalid reference"), "Error: Invalid reference")
        self.assertEqual(bulk.strip_decoration("\u2718 [ERROR] Could not resolve"), "[ERROR] Could not resolve")
        self.assertEqual(bulk.strip_decoration("fatal: not a git repository"), "fatal: not a git repository")

    def test_phrase_admin_can_mark_reviewed(self):
        # 대량 생성분 수천 개를 한 번에 승인할 수단. change 권한이 있어야 보인다.
        from django.contrib.admin.sites import site
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from apps.vocab.admin import DailyPhraseAdmin

        request = RequestFactory().get("/admin/vocab/dailyphrase/")
        request.user = get_user_model().objects.create_superuser("bulkadmin@example.com")
        self.assertIn("mark_reviewed", DailyPhraseAdmin(DailyPhrase, site).get_actions(request))
