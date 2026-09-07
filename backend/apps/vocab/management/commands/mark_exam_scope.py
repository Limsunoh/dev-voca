"""이미 있는 단어·문장 중 정처기 출제 범위인 것에 표시를 단다.

사용:
    python manage.py mark_exam_scope --dry-run   # 무엇이 바뀌는지만 본다
    python manage.py mark_exam_scope

**AI 를 부르지 않는다.** 목록이 이 파일 안에 손으로 적혀 있다. 정처기
출제 범위는 시험 주관처가 정하는 것이라 생성으로 만들 성질이 아니고,
"이 단어가 몇 과목이냐" 는 틀리면 수험생이 엉뚱한 과목을 공부하게 된다.

과목은 필기 5과목을 그대로 쓴다. 한 단어가 두 과목에 걸치는 경우가
있는데(예: 트랜잭션은 3과목이지만 4과목 병행 제어에도 나온다) 교재가
주로 다루는 쪽 하나만 적는다 - 화면에서 과목은 훑어보는 축이지 정답을
가리는 축이 아니다.

이 명령은 여러 번 돌려도 안전하다. 이미 표시된 것은 건너뛰고, 목록에
없는 항목의 표시를 지우지도 않는다(Admin 에서 손으로 켠 것을 되돌리면
검수자의 판단을 덮어쓴다).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.vocab.models import LearningItem, Sentence, Word

Subject = LearningItem.ExamSubject

# 과목별 용어. 여기 있는 term 과 정확히 일치하는 단어에만 표시가 붙는다.
#
# 대소문자는 DB 에 든 그대로 적는다 - 약어는 대문자(TCP), 일반 용어는
# 소문자(deadlock)로 저장돼 있어서 한쪽으로 통일하면 안 걸린다.
EXAM_WORDS: dict[str, tuple[str, ...]] = {
    # 1과목 소프트웨어 설계 - 요구사항, 모델링, 설계 패턴, 인터페이스
    Subject.DESIGN: (
        "UML",
        "DFD",
        "ERD",
        "SDLC",
        "WBS",
        "MVC",
        "AOP",
        "OOP",
        "abstraction",
        "encapsulation",
        "polymorphism",
        "inheritance",
        "singleton",
        "coupling",
        "cohesion",
        "use case",
        "prototype",
        "refactoring",
        "design pattern",
    ),
    # 2과목 소프트웨어 개발 - 자료구조, 알고리즘, 테스트, 형상관리
    Subject.DEVELOP: (
        "stack",
        "queue",
        "array",
        "linked list",
        "hash table",
        "binary tree",
        "binary search",
        "BFS",
        "DFS",
        "recursion",
        "greedy",
        "dynamic programming",
        "big O",
        "time complexity",
        "LIFO",
        "FIFO",
        "unit test",
        "integration test",
        "regression test",
        "black box",
        "white box",
        "test case",
        "code coverage",
        "version control",
    ),
    # 3과목 데이터베이스 구축 - 관계형 모델, SQL, 정규화, 트랜잭션
    Subject.DATABASE: (
        "primary key",
        "foreign key",
        "index",
        "normalization",
        "denormalization",
        "transaction",
        "ACID",
        "join",
        "schema",
        "view",
        "trigger",
        "stored procedure",
        "isolation level",
        "deadlock",
        "rollback",
        "commit",
        "cardinality",
        "candidate key",
        "referential integrity",
        "DDL",
        "DML",
        "DCL",
    ),
    # 4과목 프로그래밍 언어 활용 - 운영체제, 네트워크 기초, 언어 특성
    Subject.LANGUAGE: (
        "process",
        "thread",
        "concurrency",
        "parallelism",
        "context switch",
        "mutex",
        "semaphore",
        "scheduling",
        "FCFS",
        "SJF",
        "LRU",
        "paging",
        "virtual memory",
        "kernel",
        "system call",
        "OS",
        "compiler",
        "interpreter",
        "garbage collection",
        "overflow",
        "floating point",
        "pointer",
        "call by value",
        "call by reference",
    ),
    # 5과목 정보시스템 구축 관리 - 네트워크, 보안, 신기술
    Subject.SYSTEM: (
        "TCP",
        "UDP",
        "IP",
        "IPv4",
        "IPv6",
        "OSI",
        "DNS",
        "DHCP",
        "ARP",
        "ICMP",
        "NAT",
        "CIDR",
        "subnet",
        "VLAN",
        "LAN",
        "WAN",
        "P2P",
        "MAC",
        "port",
        "socket",
        "three-way handshake",
        "firewall",
        "encryption",
        "hashing",
        "salt",
        "public key",
        "RSA",
        "AES",
        "MD5",
        "CRC",
        "PKI",
        "CA",
        "authentication",
        "authorization",
        "XSS",
        "SQL injection",
        "CSRF",
        "RAID",
    ),
}

# 문장은 과목을 나누지 않는다. 에러 메시지와 실무 표현이라 "이 문장이
# 3과목이다" 가 성립하지 않는다. 정처기 범위인지만 표시한다.
#
# 지금은 비워둔다 - 문장 380개를 훑어 고르는 것은 이번 범위가 아니다.
EXAM_SENTENCE_SLUGS: tuple[str, ...] = ()


class Command(BaseCommand):
    help = "정처기 출제 범위인 단어·문장에 표시를 답니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 무엇이 바뀔지만 보여줍니다.",
        )

    # 127개를 한 건씩 저장하는 루프다. 중간에 죽으면 절반만 표시된 상태로
    # 남는데, 멱등이라 다시 돌리면 복구되긴 한다. 그래도 한 번에 끝나는
    # 편이 낫다 - 절반만 된 상태에서 화면을 열면 목록이 이상해 보인다.
    @transaction.atomic
    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]

        # 목록에 있는데 DB 에 없는 것을 먼저 알려준다. 오타이거나 아직
        # 만들지 않은 단어인데, 조용히 넘어가면 표시가 안 붙은 것을
        # 나중에 "왜 안 나오지" 로 다시 찾게 된다.
        missing: list[str] = []
        marked = 0
        already = 0

        for subject, terms in EXAM_WORDS.items():
            for term in terms:
                word = Word.objects.filter(term=term).first()
                if word is None:
                    missing.append(f"{subject}:{term}")
                    continue
                if word.is_exam and word.exam_subject == subject:
                    already += 1
                    continue
                if not dry_run:
                    word.is_exam = True
                    word.exam_subject = subject
                    word.save(update_fields=["is_exam", "exam_subject", "updated_at"])
                marked += 1
                self.stdout.write(f"  {subject:9} {term}")

        if EXAM_SENTENCE_SLUGS and not dry_run:
            Sentence.objects.filter(slug__in=EXAM_SENTENCE_SLUGS).update(is_exam=True)

        self.stdout.write("")
        self.stdout.write(f"표시함: {marked}개")
        self.stdout.write(f"이미 표시돼 있음: {already}개")

        if missing:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(f"DB 에 없는 단어 {len(missing)}개 (오타이거나 아직 안 만든 것):")
            )
            for name in missing:
                self.stdout.write(f"  {name}")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("--dry-run 이라 저장하지 않았습니다."))
