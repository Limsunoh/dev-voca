"""단어·문장·일상 표현을 Message Batches 로 대량 생성하고 두 번 검수한다.

    python manage.py bulk_content status
    python manage.py bulk_content submit --kind word --stage brainstorm --per-topic 50
    python manage.py bulk_content collect [--wait]
    python manage.py bulk_content submit --kind word --stage enrich --max-requests 4
    python manage.py bulk_content submit --kind word --stage review_meaning
    python manage.py bulk_content submit --kind word --stage review_reading
    python manage.py bulk_content submit --kind word --stage recheck
    python manage.py bulk_content export --kind word

단계와 모델은 prompts/bulk.py 에 있다. 결과는 DB 가 아니라 작업 폴더
(--dir 또는 BULK_CONTENT_DIR, 저장소 밖)에 쌓이고, 다 통과한 final.jsonl 을
load_bulk_content 로 넣는다. 넣을 때도 검수 대기(is_reviewed=False)다.

batch 는 일반 호출의 반값이고 결과가 보통 1시간 안에 나온다. submit 은 보내고
바로 끝나며, collect 가 끝난 batch 의 결과를 가져와 파일에 반영한다.

비용 상한(--budget, 기본 BULK_BUDGET_USD 또는 95달러)을 넘을 것 같으면 보내지
않는다. 상한은 지금까지 쓴 돈 + 결과를 기다리는 batch 의 예상 + 이번 예상이다.
예상은 그 단계의 항목당 평균으로 내고, 평균을 모르거나 --effort 로 생각 깊이를
바꾼 batch 는 요청마다 최악값(max_tokens 를 다 쓴다고 보고)으로 센다. 평균을
모르는 단계는 요청 수도 FIRST_RUN_MAX 로 묶는다.

여러 프로세스가 같은 작업 폴더로 collect 를 동시에 돌리면 같은 결과를 두 번
반영할 수 있다. 한 번에 하나만 돌린다.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.ai_pipeline import bulk
from apps.ai_pipeline.prompts import bulk as prompts

# 평균 비용을 모르는 단계의 첫 batch 요청 수 상한.
FIRST_RUN_MAX = 40
POLL_SECONDS = 60
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


class Command(BaseCommand):
    help = "Message Batches 로 학습 콘텐츠를 대량 생성하고 두 번 검수합니다(작업 폴더에 저장)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["status", "submit", "collect", "export"])
        parser.add_argument("--kind", choices=prompts.KINDS)
        parser.add_argument("--stage", choices=list(prompts.STAGES))
        parser.add_argument("--dir", default=os.getenv("BULK_CONTENT_DIR", ""))
        parser.add_argument(
            # 기본값을 글자로 두면 argparse 가 type 으로 바꾸며 잘못된 값을 안내로 막는다.
            "--budget", type=float, default=os.getenv("BULK_BUDGET_USD", "95")
        )
        parser.add_argument("--max-requests", type=int, default=None)
        parser.add_argument("--per-topic", type=int, default=50, help="brainstorm 주제당 후보 수")
        parser.add_argument("--round", type=int, default=1, help="brainstorm 라운드(2부터 앞 후보를 뺀다)")
        parser.add_argument("--wait", action="store_true", help="collect: 모든 batch 가 끝날 때까지 기다린다")
        parser.add_argument(
            "--effort", choices=["low", "medium", "high"], default=None,
            help="submit: 이 batch 만 생각 깊이를 바꾼다(비용과 품질을 견줄 때)",
        )

    # 테스트가 가짜 클라이언트로 바꿔 끼운다. 실제 클라이언트로 테스트를 짜면
    # 그 자리에서 과금된다(client.py 머리 주석과 같은 이유).
    def get_client(self):
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise CommandError("ANTHROPIC_API_KEY 환경변수가 필요합니다. .env 를 확인하세요.")
        import anthropic

        return anthropic.Anthropic(api_key=key)

    def handle(self, *args, **options) -> None:
        if not options["dir"]:
            raise CommandError("작업 폴더가 필요합니다. --dir 또는 BULK_CONTENT_DIR 을 주세요.")
        self.ws = bulk.Workspace(Path(options["dir"]))
        action = options["action"]
        budget = options["budget"]
        if not (math.isfinite(budget) and budget > 0):
            # nan 과의 비교는 늘 거짓이라 상한 검사를 그냥 지나간다.
            raise CommandError(f"--budget(BULK_BUDGET_USD) 은 0 보다 큰 수여야 합니다: {budget}")
        if action in ("submit", "export") and not options["kind"]:
            raise CommandError("--kind 가 필요합니다.")
        getattr(self, f"do_{action}")(options)

    # ------------------------------------------------------------------ submit

    def do_submit(self, options) -> None:
        kind, stage = options["kind"], options["stage"]
        if not stage:
            raise CommandError("--stage 가 필요합니다.")
        limit = options["max_requests"]
        # 그 단계의 기본값을 --effort 로 준 것은 바꾸지 않은 것으로 본다. 따로 세면
        # 그 batch 는 기본 평균에 안 들어가고 매번 최악값으로 셈해진다.
        effort = options["effort"]
        if effort == prompts.STAGES[stage]["effort"]:
            effort = None
        avg = self.ws.avg_item_cost(kind, stage)
        if avg is None:
            limit = min(limit or FIRST_RUN_MAX, FIRST_RUN_MAX)

        if stage == "brainstorm":
            requests = bulk.brainstorm_requests(
                self.ws, kind, options["per_topic"], options["round"], limit
            )
        else:
            requests = bulk.stage_requests(self.ws, kind, stage, limit)
        if effort:
            for r in requests:
                r.params["output_config"]["effort"] = effort
        if not requests:
            self.stdout.write("보낼 것이 없습니다.")
            return

        spent = self.ws.spent()
        waiting = self.ws.inflight_estimate()
        # 후보 뽑기는 주제 하나에 후보 per_topic 개라, 항목을 후보 수로 센다.
        # 주제 수로 세면 --per-topic 을 늘렸을 때 예상이 그만큼 낮게 나온다.
        per_topic = options["per_topic"] if stage == "brainstorm" else None
        sizes = [per_topic or len(r.keys) for r in requests]
        estimate = self.ws.estimate(kind, stage, sizes, effort)
        budget = options["budget"]
        if spent + waiting + estimate > budget:
            raise CommandError(
                f"비용 상한 {budget:.2f}달러를 넘습니다: 쓴 돈 {spent:.2f} + 기다리는 batch "
                f"{waiting:.2f} + 이번 예상 {estimate:.2f}. --max-requests 로 줄이세요."
            )

        batch = self.get_client().messages.batches.create(
            requests=[{"custom_id": r.custom_id, "params": r.params} for r in requests]
        )
        self.ws.add_batch(batch.id, kind, stage, requests, effort=effort, per_topic=per_topic)
        items = sum(len(r.keys) for r in requests)
        rough = avg is None or effort
        guess = f", 예상 {estimate:.2f}달러" + (" (평균을 몰라 최악값으로 셈)" if rough else "")
        self.stdout.write(
            f"보냄: {kind}/{stage} 요청 {len(requests)}개, 항목 {items}개{guess}. batch {batch.id}"
        )

    # ----------------------------------------------------------------- collect

    def do_collect(self, options) -> None:
        import anthropic
        import httpx

        # 결과 스트림이 끊기면 httpx 오류나 잘린 JSON 이 SDK 에 안 감싸이고 그대로
        # 올라온다. 보관 기간이 지난 batch 는 APIError 가 아닌 AnthropicError 다.
        # 이것들만 "다음에 다시" 로 넘기고, 코드 오류는 그대로 터뜨린다.
        retry_later = (anthropic.AnthropicError, httpx.HTTPError, json.JSONDecodeError)
        client = self.get_client()
        while True:
            pending = [b for b in self.ws.batches() if not b["collected"]]
            if not pending:
                self.stdout.write("기다리는 batch 가 없습니다.")
                return
            still = 0
            for record in pending:
                try:
                    remote = client.messages.batches.retrieve(record["id"])
                except retry_later as exc:
                    # 일시 오류(500·연결 끊김)로 기다리던 다른 batch 까지 못 받는 일을
                    # 막는다. SDK 가 이미 두 번 재시도했고, 이 batch 는 다음 collect 에서 다시 본다.
                    still += 1
                    self.stderr.write(f"확인 실패, 다음에 다시: {record['id']} {type(exc).__name__}")
                    continue
                if remote.processing_status != "ended":
                    still += 1
                    counts = remote.request_counts
                    self.stdout.write(
                        f"진행 중: {record['kind']}/{record['stage']} {record['id']} "
                        f"(처리 중 {counts.processing}, 성공 {counts.succeeded})"
                    )
                    continue
                try:
                    self._collect_one(client, record)
                except retry_later as exc:
                    # 결과를 읽다 끊기면 collected 를 안 켜고 다음 collect 에서 다시
                    # 읽는다. 이미 반영한 항목은 _collect_one 이 handled 로 걸러 두 번
                    # 쓰지 않는다(토큰 사용량만 그만큼 겹쳐 세어 비용을 높게 본다).
                    # API 오류만 잡는다. 코드 오류까지 "다음에 다시" 로 덮으면 --wait
                    # 가 60초마다 같은 실패를 되풀이하며 사용량만 쌓는다.
                    still += 1
                    self.stderr.write(f"결과 읽기 실패, 다음에 다시: {record['id']} {type(exc).__name__}: {exc}")
            if not still or not options["wait"]:
                return
            time.sleep(POLL_SECONDS)

    def _collect_one(self, client, record: dict) -> None:
        kind, stage = record["kind"], record["stage"]
        model = prompts.STAGES[stage]["model"]
        if stage == "brainstorm":
            seen = bulk.brainstorm_seen(self.ws, kind)
        else:
            previous = prompts.PREVIOUS[stage]
            handled = self.ws.handled_keys(kind, stage)
            pool = {i["key"]: i for i in self.ws.items(kind, previous) if i["key"] not in handled}

        tally = {"saved": 0, "dropped": 0, "failed": 0, "ok": 0, "fix": 0}
        done_topics: list[str] = []
        for result in client.messages.batches.results(record["id"]):
            keys = record["requests"].get(result.custom_id, [])
            if result.result.type != "succeeded":
                tally["failed"] += 1
                continue
            message = result.result.message
            usage = {name: getattr(message.usage, name, 0) or 0 for name in _USAGE_FIELDS}
            items = record.get("per_topic") or len(keys) or 1
            # 반영하지 못하는 요청도 과금은 됐으니 쓴 돈에는 넣는다.
            self.ws.add_usage(kind, stage, model, usage, items=items, effort=record.get("effort"))
            if not keys:
                # 보낸 기록에 없는 요청. 어느 항목·주제인지 모르니 반영하지 않는다.
                tally["failed"] += 1
                continue
            try:
                payload = bulk.parse_message(message)
            except bulk.ResultError as exc:
                tally["failed"] += 1
                self.stderr.write(f"{result.custom_id}: {exc}")
                continue

            if stage == "brainstorm":
                tally["saved"] += bulk.apply_brainstorm(self.ws, kind, keys[0], payload, seen)
                done_topics.append(keys[0])
            elif stage == "enrich":
                base = {k: pool[k] for k in keys if k in pool}
                saved, dropped = bulk.apply_enrich(self.ws, kind, base, payload)
                tally["saved"] += saved
                tally["dropped"] += dropped
            else:
                base = {k: pool[k] for k in keys if k in pool}
                counts = bulk.apply_review(self.ws, kind, stage, base, payload)
                tally["ok"] += counts["ok"]
                tally["fix"] += counts["fix"]
                tally["dropped"] += counts["drop"]

        # 실패한 요청의 항목은 handled 에 안 들어가므로 다음 submit 때 다시 나간다.
        # 후보 뽑기는 항목이 아니라 주제 단위라, 응답을 받은 주제를 따로 적는다.
        batches = self.ws.batches()
        for b in batches:
            if b["id"] == record["id"]:
                b["collected"] = True
                if stage == "brainstorm":
                    b["done"] = done_topics
        self.ws.save_batches(batches)
        summary = ", ".join(f"{k} {v}" for k, v in tally.items() if v)
        self.stdout.write(f"반영: {kind}/{stage} {record['id']} - {summary or '없음'}")

    # ------------------------------------------------------------------ status

    def do_status(self, options) -> None:
        kinds = [options["kind"]] if options["kind"] else list(prompts.KINDS)
        for kind in kinds:
            line = [f"[{kind}]"]
            for stage in prompts.STAGES:
                line.append(f"{stage} {len(self.ws.items(kind, stage))}")
            dropped = self.ws.dropped(kind)
            line.append(f"버림 {len(dropped)}")
            line.append(f"최종 {len(bulk.final_items(self.ws, kind))}")
            self.stdout.write("  ".join(line))
        waiting = [b for b in self.ws.batches() if not b["collected"]]
        for b in waiting:
            self.stdout.write(f"  기다림: {b['kind']}/{b['stage']} {b['id']} 요청 {len(b['requests'])}")
        for name, slot in sorted(self.ws.usage().items()):
            per_item = slot["cost"] / slot["requests"]
            self.stdout.write(
                f"  {name}: 요청 {slot['requests']}개 {slot['cost']:.2f}달러 "
                f"(요청당 {per_item:.4f}, 입력 {slot.get('input_tokens', 0)} "
                f"캐시읽기 {slot.get('cache_read_input_tokens', 0)} 출력 {slot.get('output_tokens', 0)})"
            )
        self.stdout.write(
            f"쓴 돈 {self.ws.spent():.2f}달러 / 상한 {options['budget']:.2f}달러, "
            f"기다리는 batch 예상 {self.ws.inflight_estimate():.2f}달러"
        )

    # ------------------------------------------------------------------ export

    def do_export(self, options) -> None:
        kind = options["kind"]
        items = bulk.final_items(self.ws, kind)
        path = self.ws.path(kind, "final")
        if path.exists():
            path.unlink()
        bulk.append_jsonl(path, items)
        self.stdout.write(f"{path} 에 {len(items)}개를 썼습니다.")
