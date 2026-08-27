"""손으로 적은 한글 발음을 파일에서 읽어 채운다.

사용:
    python manage.py load_readings 파일.json
    python manage.py load_readings 파일.json --kind sentence
    python manage.py load_readings 파일.json --dry-run

generate_readings 와 짝이다. 저쪽은 Claude API 로 만들고 이쪽은 이미 만들어진
것을 넣는다. 표기 규칙(prompts/korean-reading.md)을 아는 사람이나 모델이
직접 적었을 때 쓴다 - API 키 없이도 채울 수 있고, 규칙을 만든 쪽이 적으므로
일관성이 높다.

파일 형식은 `[{"pk": 1, "reading": "**캐**sh", "note": "..."}]`.

**pk 로 짝을 맞춘다.** 단어로 맞추면 같은 철자가 둘 있을 때 엉뚱한 곳에
들어가고, 순서로 맞추면 하나만 빠져도 그 뒤가 전부 밀린다.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError, transaction

from apps.vocab.models import Sentence, Word

READING_MAX = Word._meta.get_field("reading").max_length


class Command(BaseCommand):
    help = "파일에 적어둔 한글 발음을 검수 대기 상태로 채웁니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path", help="발음이 담긴 JSON 파일")
        parser.add_argument(
            "--kind",
            choices=["word", "sentence"],
            default="word",
            help="무엇을 채울지 (기본 word)",
        )
        parser.add_argument(
            "--reviewed",
            action="store_true",
            help=(
                "검수까지 완료로 표시한다. prompts/korean-reading.md 의 규칙을 "
                "보고 사람이 직접 적은 경우에만 쓴다"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 결과만 보여준다",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"파일이 없습니다: {path}")

        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON 을 읽지 못했습니다: {exc}") from exc

        if not isinstance(rows, list):
            raise CommandError("파일은 항목 배열이어야 합니다.")

        model = Word if options["kind"] == "word" else Sentence
        filled, skipped, problems = self.save(
            model,
            rows,
            commit=not options["dry_run"],
            reviewed=options["reviewed"],
        )

        for line in problems:
            self.stdout.write(self.style.WARNING(f"  {line}"))

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"dry-run: 저장하면 {filled}개가 채워지고 {skipped}개는 건너뜁니다."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"{filled}개 채웠습니다. ({skipped}개 건너뜀)")
        )
        if not filled:
            return

        if options["reviewed"]:
            # **검수 단계를 건너뛴 것을 알린다.** 지금까지는 --reviewed 가
            # 아닐 때만 안내가 나가서, 게이트를 뚫는 쪽이 더 조용했다.
            # 방향이 반대다 - 나중에 이 593건을 보고 "사람이 봤나 밀었나"
            # 를 되짚을 때 이 줄이 유일한 단서다.
            self.stdout.write(
                self.style.WARNING(
                    f"{filled}개를 검수 완료로 표시했습니다. Admin 검수를 "
                    "건너뛴 것이니 규칙대로 적은 것이 맞는지 확인하세요."
                )
            )
        else:
            self.stdout.write("Admin 에서 발음을 검수해야 사용자에게 보입니다.")

    def save(
        self, model, rows: list, *, commit: bool, reviewed: bool
    ) -> tuple[int, int, list[str]]:
        """(채운 수, 건너뛴 수, 문제 목록)

        **검수된 것은 덮지 않는다.** 사람이 확인한 것을 배치가 덮으면 검수라는
        절차가 의미를 잃는다. --reviewed 로 다시 돌려도 마찬가지다.
        """
        filled = skipped = 0
        problems: list[str] = []

        # **행 하나하나를 믿지 않는다.** 이 파일은 사람이나 모델이 손으로
        # 만든 것이라 원소가 dict 가 아니거나(null, 문자열), 값의 타입이
        # 어긋나는 일이 흔하다. 파일 최상위가 list 인지만 보고 넘어가면
        # 한 항목의 오타가 AttributeError 로 명령 전체를 죽여, 앞서 정상
        # 처리될 수 있었던 것까지 저장 안 된다.
        usable = [r for r in rows if isinstance(r, dict)]
        broken = len(rows) - len(usable)
        if broken:
            problems.append(f"항목 {broken}개가 객체가 아니라 건너뜁니다.")
            skipped += broken

        # pk 를 한 번에 끌어와 항목마다 쿼리하지 않는다.
        #
        # isinstance 가 아니라 type() 을 쓰는 이유: 파이썬에서 bool 은 int 의
        # 하위라 isinstance(True, int) 가 참이고, dict 에서도 True 가 1 과
        # 같은 자리를 집는다. 그대로 두면 {"pk": true} 가 pk=1 인 단어에
        # 엉뚱한 발음을 조용히 심는다 - 에러도 경고도 안 뜬다.
        wanted = [r["pk"] for r in usable if type(r.get("pk")) is int]
        found = {o.pk: o for o in model.objects.filter(pk__in=wanted)}

        for row in usable:
            pk = row.get("pk")
            # 문자열이 아닌 값은 .strip() 에서 죽는다. 숫자·배열·객체가
            # 전부 truthy 라 `or ""` 로는 못 막는다.
            raw = row.get("reading")
            text = raw.strip() if isinstance(raw, str) else ""
            raw_note = row.get("note")
            note = raw_note.strip() if isinstance(raw_note, str) else ""

            obj = found.get(pk) if type(pk) is int else None
            if obj is None:
                problems.append(f"pk={pk} 를 찾지 못했습니다.")
                skipped += 1
                continue

            if not text:
                # 발음을 비워둔 것은 의도일 수 있다(갈리는 용어). 문제로 세지
                # 않고 조용히 건너뛴다.
                skipped += 1
                continue

            if obj.reading_reviewed:
                problems.append(f"pk={pk} 는 이미 검수됐습니다. 건너뜁니다.")
                skipped += 1
                continue

            # 길이는 DB 예외에 맡기지 않고 여기서 거른다. 엔진마다 max_length
            # 강제 여부가 달라 결과가 갈린다. Sentence.reading 은 TextField 라
            # 상한이 없다(READING_MAX 는 Word 것).
            if isinstance(obj, Word) and len(text) > READING_MAX:
                problems.append(f"pk={pk} 발음이 {READING_MAX}자를 넘습니다.")
                skipped += 1
                continue

            if not commit:
                filled += 1
                continue

            try:
                with transaction.atomic():
                    obj.reading = text
                    fields = ["reading"]
                    # 문장에는 설명 칸이 없다. 길어서 화면이 감당 못 한다.
                    if isinstance(obj, Word):
                        obj.reading_note = note
                        fields.append("reading_note")
                    if reviewed:
                        obj.reading_reviewed = True
                        fields.append("reading_reviewed")
                    obj.save(update_fields=fields)
                filled += 1
            except DatabaseError as exc:
                problems.append(f"pk={pk} 저장 실패: {exc}")
                skipped += 1

        return filled, skipped, problems
