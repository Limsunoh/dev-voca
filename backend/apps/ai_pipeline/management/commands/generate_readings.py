"""AI 로 한글 발음을 만들어 검수 대기 상태로 채운다.

사용:
    python manage.py generate_readings --count 20
    python manage.py generate_readings --count 5 --dry-run
    python manage.py generate_readings --kind sentence --count 10
    python manage.py generate_readings --refill        # 이미 채운 것도 다시

generate_words 와 성격이 다르다. 저쪽은 없던 항목을 만들고, 이쪽은 **이미 있는
항목에 칸 하나를 채운다.** 그래서 둘이 다르다:

- 입력에 기존 단어와 발음기호를 넣고, 응답을 단어로 짝지어 되돌린다
- is_reviewed 를 건드리지 않는다. 단어 자체는 이미 검수가 끝났고 발음만
  미검수다. 그 상태를 reading_reviewed 로 따로 나타낸다

표기 규칙은 apps/ai_pipeline/prompts/korean-reading.md 에 있고 프롬프트가 그 파일을 읽는다.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import DatabaseError, transaction

from apps.ai_pipeline.client import (
    ClaudeGenerator,
    ContentGenerator,
    GeneratedItem,
    GenerationError,
)
from apps.ai_pipeline.prompts import reading as prompts
from apps.vocab.models import Sentence, Word

# 한 번에 보내는 최대 항목 수. 프롬프트에 규칙 문서가 통째로 들어가므로
# 배치를 크게 잡을수록 그 비용이 분산된다. 다만 한 응답이 길어지면 뒤쪽
# 품질이 떨어지는 것이 보여 50 을 상한으로 둔다.
MAX_COUNT = 50

READING_MAX = Word._meta.get_field("reading").max_length


class Command(BaseCommand):
    help = "Claude API 로 한글 발음을 만들어 검수 대기 상태로 채웁니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help=f"채울 항목 수 (기본 20, 최대 {MAX_COUNT})",
        )
        parser.add_argument(
            "--kind",
            choices=["word", "sentence"],
            default="word",
            help="무엇을 채울지 (기본 word)",
        )
        parser.add_argument(
            "--refill",
            action="store_true",
            help="이미 발음이 있는 것도 다시 만든다. 검수된 것은 건드리지 않는다",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 결과만 보여준다",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        if not 1 <= count <= MAX_COUNT:
            raise CommandError(f"--count 는 1 이상 {MAX_COUNT} 이하여야 합니다.")

        model = Word if options["kind"] == "word" else Sentence
        targets = self.pick(model, count, refill=options["refill"])
        if not targets:
            self.stdout.write(self.style.WARNING("채울 항목이 없습니다."))
            return

        try:
            generator = self.get_generator()
        except GenerationError as exc:
            # 키 누락 같은 설정 문제. 스택트레이스 대신 안내 문구만.
            raise CommandError(str(exc)) from exc

        label = "단어" if model is Word else "문장"
        self.stdout.write(f"{label} {len(targets)}개의 발음 생성 중...")

        try:
            items = generator.generate(
                system=prompts.system(),
                user=prompts.user([(self.key_of(o), self.ipa_of(o)) for o in targets]),
                schema=prompts.SCHEMA,
                result_key=prompts.RESULT_KEY,
                max_items=len(targets),
            )
        except GenerationError as exc:
            raise CommandError(str(exc)) from exc
        except FileNotFoundError as exc:
            # 규칙 문서가 없다. 규칙 없이 만들면 566개가 제각각이 된다.
            raise CommandError(str(exc)) from exc

        if not items:
            self.stdout.write(self.style.WARNING("생성된 발음이 없습니다."))
            return

        dry_run: bool = options["dry_run"]
        if dry_run:
            self.print_preview(items)

        # dry-run 도 같은 검증을 탄다. 저장 경로와 다른 계산을 하면
        # "20개" 를 보고 실행했는데 12개만 들어가는 일이 생긴다.
        filled, skipped, problems = self.save(
            model, targets, items, commit=not dry_run
        )

        for line in problems:
            self.stdout.write(self.style.WARNING(f"  {line}"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"dry-run: 저장하면 {filled}개가 채워지고 {skipped}개는 건너뜁니다."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"{filled}개 채웠습니다. ({skipped}개 건너뜀)")
        )
        if filled:
            self.stdout.write("Admin 에서 발음을 검수해야 사용자에게 보입니다.")

    def pick(self, model, count: int, *, refill: bool) -> list:
        """채울 대상을 고른다.

        **검수된 발음은 절대 건드리지 않는다.** --refill 이 있어도 마찬가지다 -
        사람이 확인한 것을 AI 가 덮으면 검수라는 절차가 의미를 잃는다.

        visible() 로 좁히지 않는 것은 의도다. 아직 검수 대기 중인 단어도
        언젠가 검수를 통과하므로 발음이 미리 있는 편이 낫다. 사용자 노출
        경로가 아니라 배치 입력이라 검수 게이트의 대상이 아니다.
        """
        qs = model.objects.filter(reading_reviewed=False)
        if not refill:
            qs = qs.filter(reading="")
        return list(qs.order_by("pk")[:count])

    def key_of(self, obj) -> str:
        """프롬프트에 넣고 응답에서 짝을 찾을 때 쓰는 값."""
        return obj.term if isinstance(obj, Word) else obj.text

    def ipa_of(self, obj) -> str:
        """발음기호. 문장에는 없다."""
        return getattr(obj, "pronunciation", "")

    def get_generator(self) -> ContentGenerator:
        """테스트가 가짜 생성기로 갈아끼울 수 있도록 분리했다."""
        return ClaudeGenerator()

    def save(
        self, model, targets: list, items: list[GeneratedItem], *, commit: bool = True
    ) -> tuple[int, int, list[str]]:
        """받은 발음을 짝지어 채운다. (채운 수, 건너뛴 수, 문제 목록)

        **왜 버렸는지 말한다.** 숫자만 주면 "19개 건너뜀" 을 보고도 이유를
        알 길이 없다 - 돈을 쓰고 부른 것이라 그 19개가 왜 버려졌는지가
        다음 실행을 정하는 정보다. load_readings 가 같은 모양이다.

        **응답 순서를 믿지 않는다.** term 으로 짝을 찾는다 - 순서로 맞추면
        AI 가 하나를 빠뜨렸을 때 그 뒤가 전부 한 칸씩 밀려, 엉뚱한 단어에
        엉뚱한 발음이 붙는다. 그건 화면에서 티가 안 나서 검수도 통과한다.

        배치를 하나의 트랜잭션으로 묶지 않는다. 20개 중 19번째가 길이 제약에
        걸리면 앞의 18개까지 롤백되어, API 비용은 나갔는데 저장은 0건이 된다.
        """
        # **같은 이름이 둘이면 하나를 못 채운다.** dict 는 뒤엣것이 앞엣것을
        # 덮으므로 앞의 것이 조용히 사라진다 - 보고에도 안 잡혀서 "1개
        # 채웠습니다" 만 보고 넘어가게 된다. 응답은 이름으로 오므로(AI 가
        # pk 를 모른다) 짝을 못 지을 바에는 아예 빼고 그 사실을 알린다.
        #
        # load_readings 는 pk 로 맞춰서 이 문제가 없다. 그쪽은 사람이 파일을
        # 만들어 pk 를 넣을 수 있기 때문이다.
        seen: dict[str, int] = {}
        for o in targets:
            key = self.key_of(o)
            seen[key] = seen.get(key, 0) + 1

        duplicates = {k for k, n in seen.items() if n > 1}
        if duplicates:
            self.stdout.write(
                self.style.WARNING(
                    f"이름이 겹쳐 {len(duplicates)}개를 건너뜁니다: "
                    + ", ".join(sorted(duplicates)[:5])
                )
            )

        by_key = {
            self.key_of(o): o for o in targets if self.key_of(o) not in duplicates
        }
        filled = skipped = 0
        problems: list[str] = []

        for item in items:
            key = (item.get("term") or "").strip()
            text = (item.get("reading") or "").strip()
            note = (item.get("note") or "").strip()

            obj = by_key.get(key)
            if obj is None:
                problems.append(f"'{key}' 는 보낸 목록에 없습니다.")
                skipped += 1
                continue
            if not text:
                problems.append(f"'{key}' 의 발음이 비어 있습니다.")
                skipped += 1
                continue

            # 길이는 DB 예외에 맡기지 않고 여기서 거른다. 엔진마다 max_length
            # 강제 여부가 달라 DatabaseError 에만 의존하면 결과가 갈린다.
            # Sentence.reading 은 TextField 라 상한이 없다(READING_MAX 는 Word 것).
            if isinstance(obj, Word) and len(text) > READING_MAX:
                problems.append(f"'{key}' 의 발음이 {READING_MAX}자보다 깁니다.")
                skipped += 1
                continue

            if not commit:
                filled += 1
                continue

            try:
                with transaction.atomic():
                    obj.reading = text
                    # 문장에는 설명 칸이 없다. 길어서 화면이 감당 못 한다.
                    fields = ["reading"]
                    if isinstance(obj, Word):
                        obj.reading_note = note
                        fields.append("reading_note")
                    obj.save(update_fields=fields)
                filled += 1
            except DatabaseError as exc:
                problems.append(f"'{key}' 저장 실패: {exc}")
                skipped += 1

        # 응답이 안 온 항목도 건너뛴 것으로 센다. 안 그러면 "20개 중 12개
        # 채움" 이라고만 보고되어 나머지 8개가 어디 갔는지 알 수 없다.
        answered = {(i.get("term") or "").strip() for i in items}
        skipped += sum(1 for k in by_key if k not in answered)

        return filled, skipped, problems

    def print_preview(self, items: list[GeneratedItem]) -> None:
        for item in items:
            self.stdout.write(f"  {item.get('term')} -> {item.get('reading')}")
            if item.get("note"):
                self.stdout.write(f"      {item['note']}")
