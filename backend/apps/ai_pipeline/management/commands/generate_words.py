"""AI 로 단어를 생성해 검수 대기 상태로 저장한다.

사용:
    python manage.py generate_words --count 20 --category git
    python manage.py generate_words --count 5 --dry-run

생성된 단어는 is_reviewed=False 로 들어가므로 사용자에게 바로 노출되지 않는다.
Admin 에서 확인하고 검수 완료로 바꿔야 API 에 나타난다(CLAUDE.md 검수 워크플로우).
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
from apps.ai_pipeline.prompts import vocab
from apps.vocab.models import Word

# 모델이 아는 길이 제한을 그대로 쓴다. 여기에 숫자를 다시 적으면 모델을
# 고쳤을 때 조용히 어긋난다.
TERM_MAX = Word._meta.get_field("term").max_length
MEANING_MAX = Word._meta.get_field("meaning").max_length


class Command(BaseCommand):
    help = "Claude API 로 개발 영어 단어를 생성해 검수 대기 상태로 저장합니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count", type=int, default=10, help="생성할 단어 수 (기본 10, 최대 50)"
        )
        parser.add_argument(
            "--category", default="", help="분류 (예: git, api, devops). 비우면 개발 전반"
        )
        parser.add_argument(
            "--extra", default="", help="프롬프트에 덧붙일 추가 조건"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 생성 결과만 출력합니다.",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        category: str = options["category"]

        if not 1 <= count <= 50:
            raise CommandError("--count 는 1 이상 50 이하여야 합니다.")

        try:
            generator = self.get_generator()
        except GenerationError as exc:
            # 키 누락 같은 설정 문제. 스택트레이스 대신 안내 문구만 보여준다.
            raise CommandError(str(exc)) from exc

        # 이미 있는 단어를 알려줘 중복 생성을 줄인다. term 이 unique 라
        # 중복이 오면 저장 단계에서 버려지고, 그만큼 API 비용이 낭비된다.
        #
        # visible() 을 쓰지 않는 것은 의도다. 중복 방지가 목적이므로 검수 대기
        # 중인 단어도 포함해야 한다 - 안 그러면 검수를 기다리는 단어를 매번
        # 다시 생성한다. 사용자 노출 경로가 아니라 프롬프트 입력이라 검수
        # 게이트의 대상이 아니다.
        #
        # 최신 200개만 넣는 것은 프롬프트 길이와의 타협이다. 단어가 그보다
        # 많아지면 오래된 단어는 목록에서 빠져 중복 생성될 수 있다. 전체를
        # 넣으면 확실하지만 프롬프트가 계속 길어져 매 호출 비용이 오른다.
        # 단어가 수천 개가 되면 --category 로 좁혀 부르는 편이 낫다.
        existing = list(
            Word.objects.order_by("-created_at").values_list("term", flat=True)[:200]
        )

        self.stdout.write(f"단어 {count}개 생성 중... (분류: {category or '개발 전반'})")

        try:
            items = generator.generate(
                system=vocab.SYSTEM,
                user=vocab.build_user_prompt(
                    count=count,
                    category=category,
                    existing=existing,
                    extra=options["extra"],
                ),
                schema=vocab.SCHEMA,
                result_key=vocab.RESULT_KEY,
                max_items=count,
            )
        except GenerationError as exc:
            raise CommandError(str(exc)) from exc

        if not items:
            self.stdout.write(self.style.WARNING("생성된 단어가 없습니다."))
            return

        dry_run: bool = options["dry_run"]
        if dry_run:
            self.print_preview(items)

        # dry-run 도 같은 검증을 탄다. 저장 경로와 다른 계산을 하면
        # "20개 생성됨" 을 보고 실행했는데 12개만 저장되는 일이 생긴다.
        created, skipped = self.save(items, category, commit=not dry_run)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"dry-run: 저장하면 {created}개가 들어가고 {skipped}개는 건너뜁니다."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"{created}개 저장했습니다. ({skipped}개 건너뜀)")
        )
        if created:
            self.stdout.write("Admin 에서 검수해야 사용자에게 보입니다.")

    def get_generator(self) -> ContentGenerator:
        """테스트가 가짜 생성기로 갈아끼울 수 있도록 분리했다."""
        return ClaudeGenerator()

    def save(
        self, items: list[GeneratedItem], category: str, *, commit: bool = True
    ) -> tuple[int, int]:
        """검수 대기 상태로 저장한다. 이미 있는 단어는 건너뛴다.

        commit=False 면 검증만 하고 DB 에 쓰지 않는다(dry-run). 같은 코드를
        타야 dry-run 이 예고한 건수와 실제 저장 건수가 일치한다.

        배치 전체를 하나의 트랜잭션으로 묶지 않는다. 20개 중 19번째가 길이
        제약에 걸리면 앞의 18개까지 롤백되어, API 비용은 나갔는데 저장은 0건이
        된다. 항목마다 savepoint 를 두어 실패한 것만 버린다.
        """
        created = skipped = 0

        for item in items:
            term = (item.get("term") or "").strip()
            meaning = (item.get("meaning") or "").strip()
            if not term or not meaning:
                skipped += 1
                continue

            # 길이는 DB 예외에 맡기지 않고 여기서 거른다. sqlite 는 max_length 를
            # 강제하지 않아, DatabaseError 에만 의존하면 같은 코드가 엔진에 따라
            # 다르게 동작한다(sqlite 는 150자 term 을 그대로 저장한다).
            if len(term) > TERM_MAX or len(meaning) > MEANING_MAX:
                skipped += 1
                continue

            difficulty = item.get("difficulty")
            if difficulty not in (1, 2, 3):
                difficulty = Word.Difficulty.NORMAL

            if not commit:
                # 저장하지 않고 결과만 센다. 중복 판정은 그대로 해야
                # 예고 건수가 실제와 맞는다.
                if Word.objects.filter(term=term).exists():
                    skipped += 1
                else:
                    created += 1
                continue

            try:
                # 항목마다 savepoint. 여기서 실패해도 앞서 저장한 것은 남는다.
                with transaction.atomic():
                    # get_or_create 로 경합을 DB 에 맡긴다. exists() 로 미리
                    # 확인하면 같은 배치를 두 번 돌릴 때 그 사이에 끼어들 수 있다.
                    _, was_created = Word.objects.get_or_create(
                        term=term,
                        defaults={
                            "meaning": meaning,
                            "description": (item.get("description") or "").strip(),
                            "example": (item.get("example") or "").strip(),
                            "example_translation": (
                                item.get("example_translation") or ""
                            ).strip(),
                            "difficulty": difficulty,
                            "category": category,
                            "source": "AI 생성",
                            # 검수 전 상태. 이 값을 True 로 바꾸지 않는다.
                            "is_reviewed": False,
                        },
                    )
            except DatabaseError:
                # 길이 초과(max_length), 제약 위반 등. 한 건 때문에 배치를
                # 버리지 않는다. sqlite 는 길이를 강제하지 않아 이 경로가
                # PostgreSQL 에서만 드러난다.
                skipped += 1
                continue

            if was_created:
                created += 1
            else:
                skipped += 1

        return created, skipped

    def print_preview(self, items: list[dict]) -> None:
        for item in items:
            self.stdout.write("")
            self.stdout.write(f"  {item.get('term')} - {item.get('meaning')}")
            if item.get("example"):
                self.stdout.write(f"    {item['example']}")
