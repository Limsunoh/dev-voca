"""bulk_content 가 만든 final.jsonl 을 검수 대기 상태로 DB 에 넣는다.

    python manage.py load_bulk_content word path/to/final.jsonl [--dry-run]
    base64 -di < x.b64 | python manage.py load_bulk_content phrase -

운영에는 API 키를 두지 않으므로 생성은 로컬에서 하고 파일만 옮긴다
(CODE_INSIGHTS 2026-11-10 "운영 DB 에 파일을 넣거나..."). 그래서 이 명령은
API 를 부르지 않는다.

넣는 것은 모두 is_reviewed=False(단어·문장은 reading_reviewed=False 도)다.
AI 검수를 두 번 거쳤어도 사용자 노출 여부는 관리자가 Admin 의 일괄 작업으로
정한다(CLAUDE.md 검수 규칙).

이미 있는 원문은 건너뛴다. 단어·일상 표현은 대소문자를 무시하고 원문으로,
문장은 slug(bulk-<key>)와 원문으로 본다. 그래서 같은 파일을 두 번 돌려도
두 벌 생기지 않는다.
"""

from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.ai_pipeline import bulk
from apps.vocab.models import DailyPhrase, Sentence, Word

SOURCE = "AI 생성(일괄)"


def _word(item: dict) -> Word:
    return Word(
        term=item["term"],
        pronunciation=item["pronunciation"],
        reading=item["reading"],
        reading_reviewed=False,
        meaning=item["meaning"],
        aliases=item.get("aliases", ""),
        description=item["description"],
        example=item["example"],
        example_translation=item["example_translation"],
        difficulty=item["difficulty"],
        category=item["category"],
        source=SOURCE,
        is_reviewed=False,
    )


def _sentence(item: dict) -> Sentence:
    return Sentence(
        slug=f"bulk-{item['key']}",
        text=item["text"],
        reading=item["reading"],
        reading_reviewed=False,
        translation=item["translation"],
        kind=item["sentence_kind"],
        context=item["context"],
        description=item["description"],
        category=item.get("category", ""),
        difficulty=item["difficulty"],
        source=SOURCE,
        is_reviewed=False,
    )


def _phrase(item: dict) -> DailyPhrase:
    return DailyPhrase(
        text=item["text"],
        scene=item["scene"],
        pronunciation=item["pronunciation"],
        reading=item["reading"],
        meaning=item["meaning"],
        difficulty=item["difficulty"],
        source=SOURCE,
        is_reviewed=False,
    )


BUILD = {"word": _word, "sentence": _sentence, "phrase": _phrase}


class Command(BaseCommand):
    help = "bulk_content 의 final.jsonl 을 검수 대기 상태로 넣습니다. 파일 대신 - 면 표준 입력."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("kind", choices=list(BUILD))
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        kind = options["kind"]
        if options["path"] == "-":
            # 바이트로 읽어 utf-8 로 푼다. 한국어 Windows 에서 파이프로 넣으면
            # sys.stdin 이 cp949 로 풀어 한글이 깨진다. -sig 가 BOM 도 벗긴다.
            lines = sys.stdin.buffer.read().decode("utf-8-sig").split("\n")
        else:
            try:
                # utf-8-sig: 메모장 같은 편집기가 붙이는 BOM 을 벗긴다.
                with open(options["path"], encoding="utf-8-sig") as fh:
                    lines = fh.read().split("\n")
            except OSError as exc:
                raise CommandError(f"파일을 열지 못했습니다: {exc}") from exc
        try:
            items = [json.loads(line) for line in lines if line.strip()]
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON 줄을 읽지 못했습니다: {exc}") from exc
        if not all(isinstance(item, dict) for item in items):
            raise CommandError("한 줄이 객체({...})가 아닙니다. bulk_content export 가 만든 파일인지 확인하세요.")
        # 중간 단계 파일(enrich.jsonl 등)을 넘기면 AI 검수 두 번을 건너뛴 채
        # 들어간다. Admin 에서는 출처가 같아 구분할 수 없으니 여기서 막는다.
        unmarked = sum(1 for item in items if not item.get(bulk.FINAL_MARK))
        if unmarked:
            raise CommandError(
                f"검수 2회 표시가 없는 줄이 {unmarked}개 있습니다. bulk_content export 가 만든 final.jsonl 만 넣습니다."
            )

        existing = self._existing(kind)
        rows, skipped, invalid = [], 0, []
        for item in items:
            source = item.get(bulk.SOURCE_FIELD[kind], "")
            norm = bulk.normalize_text(source)
            if norm in existing or (kind == "sentence" and f"bulk-{item.get('key')}" in existing):
                skipped += 1
                continue
            problems = bulk.validate(kind, item)
            if problems:
                invalid.append(f"{source}: {'; '.join(problems)}")
                continue
            existing.add(norm)
            rows.append(BUILD[kind](item))

        for line in invalid[:20]:
            self.stderr.write(f"건너뜀(칸 검사): {line}")
        verb = "넣을" if options["dry_run"] else "넣은"
        if not options["dry_run"] and rows:
            model = type(rows[0])
            with transaction.atomic():
                model.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(
            f"{kind}: {verb} 것 {len(rows)}개, 이미 있어 건너뜀 {skipped}개, 칸 검사 실패 {len(invalid)}개"
        )

    def _existing(self, kind: str) -> set[str]:
        if kind == "word":
            return {bulk.normalize_text(t) for t in Word.objects.values_list("term", flat=True)}
        if kind == "phrase":
            return {bulk.normalize_text(t) for t in DailyPhrase.objects.values_list("text", flat=True)}
        texts = {bulk.normalize_text(t) for t in Sentence.objects.values_list("text", flat=True)}
        slugs = set(Sentence.objects.exclude(slug="").values_list("slug", flat=True))
        return texts | slugs
