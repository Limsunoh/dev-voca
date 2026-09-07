"""정처기 출제 범위 중 비어 있던 용어를 채운다.

사용:
    python manage.py seed_exam_words --dry-run
    python manage.py seed_exam_words

**AI 로 만들지 않았다.** mark_exam_scope 가 "DB 에 없다" 고 알려준 15개를
손으로 썼다. 정처기 용어는 교재마다 쓰는 말이 정해져 있어서(예: 4정규형이
아니라 BCNF), 생성한 뒤 그걸 검수하는 것보다 처음부터 맞게 쓰는 편이 빠르다.

그래서 is_reviewed=True 로 바로 들어간다. seed_words 와 같은 규칙이다 -
사람이 쓴 것은 검수 대기를 거치지 않는다. AI 가 만든 것만 False 로 들어와
Admin 검수를 기다린다(CLAUDE.md 의 검수 워크플로우).

여러 번 돌려도 안전하다. term 이 unique 라 이미 있으면 건너뛴다.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.vocab.models import LearningItem, Word

Subject = LearningItem.ExamSubject
Category = LearningItem.Category

# (term, pronunciation, meaning, description, example, example_translation,
#  difficulty, category, exam_subject)
#
# 발음기호는 IPA 다. 화면이 고정폭 없이 lang="en-US" 로 그린다(모델 주석 참고).
EXAM_WORDS: tuple[tuple, ...] = (
    # ---- 1과목 소프트웨어 설계 ----
    (
        "inheritance",
        "/ɪnˈherɪtəns/",
        "위의 것을 물려받아 확장하기",
        "이미 있는 클래스의 기능을 물려받아 새 클래스를 만드는 것. 같은 코드를 다시 쓰지 "
        "않아도 되지만, 부모를 고치면 자식이 전부 영향을 받는다. 물려받을 것이 없는데 "
        "코드를 줄이려고 상속하면 관계가 꼬이므로, 그럴 때는 가져다 쓰는 편이 낫다.",
        "This class inherits the retry logic from the base client.",
        "이 클래스는 기반 클라이언트에서 재시도 로직을 물려받습니다.",
        1,
        Category.CS,
        Subject.DESIGN,
    ),
    (
        "use case",
        "/ˈjus ˌkeɪs/",
        "사용자가 시스템으로 하는 일 하나",
        "사용자가 시스템을 써서 목적을 이루는 과정을 하나의 단위로 적은 것. 화면이나 버튼이 "
        "아니라 '무엇을 하려는가' 로 적는다. 정처기에서 액터와 함께 그림으로 그리는 문제가 "
        "자주 나온다. 기능 목록과 헷갈리기 쉬운데, 기능은 시스템 쪽 말이고 이건 사용자 쪽 말이다.",
        "Each use case should describe one goal the user wants to achieve.",
        "각 유스케이스는 사용자가 이루려는 목적 하나를 적어야 합니다.",
        2,
        Category.CS,
        Subject.DESIGN,
    ),
    (
        "prototype",
        "/ˈproʊtətaɪp/",
        "확인해보려고 먼저 만든 것",
        "요구사항이 맞는지 보려고 미리 간단히 만들어보는 것. 화면만 있고 안은 비어 있어도 "
        "된다. 목적이 '확인' 이라 버리는 것이 전제인데, 잘 만들어졌다는 이유로 그대로 "
        "제품이 되면 임시로 짠 코드가 그대로 남는다.",
        "We built a prototype first to check the flow with the client.",
        "흐름을 고객과 확인하려고 프로토타입을 먼저 만들었습니다.",
        1,
        Category.CS,
        Subject.DESIGN,
    ),
    (
        "refactoring",
        "/ˌriˈfæktərɪŋ/",
        "동작은 그대로 두고 구조만 고치기",
        "밖에서 보는 동작을 바꾸지 않으면서 코드 안쪽을 정리하는 것. 기능 추가와 섞으면 "
        "문제가 생겼을 때 어느 쪽 때문인지 알 수 없으므로 나눠서 한다. 테스트가 있어야 "
        "동작이 그대로인지 확인할 수 있어서, 보통 테스트를 먼저 채우고 시작한다.",
        "This commit is pure refactoring; no behavior should change.",
        "이 커밋은 순수 리팩터링이라 동작이 바뀌면 안 됩니다.",
        2,
        Category.REVIEW,
        Subject.DESIGN,
    ),
    (
        "design pattern",
        "/dɪˈzaɪn ˌpætərn/",
        "자주 나오는 문제의 정해진 풀이",
        "설계에서 반복되는 문제에 대해 이미 정리된 해결 방식. 이름이 붙어 있어 '싱글턴으로 "
        "가자' 한마디로 통한다. 정처기에서 생성·구조·행위 세 갈래로 나눠 묻는다. 패턴을 "
        "쓰는 것 자체가 목적이 되면 간단한 코드가 괜히 복잡해진다.",
        "We applied the observer pattern so the panels update independently.",
        "패널이 각자 갱신되도록 옵서버 패턴을 적용했습니다.",
        2,
        Category.CS,
        Subject.DESIGN,
    ),
    # ---- 2과목 소프트웨어 개발 ----
    (
        "black box",
        "/ˈblæk ˌbɑks/",
        "속을 안 보고 입력과 출력만 보기",
        "내부 구현을 모르는 채로 입력을 넣고 결과가 맞는지만 확인하는 시험 방식. 사용자가 "
        "겪는 것과 같은 관점이라 요구사항을 잘 지켰는지 보기 좋다. 대신 안 타는 코드가 "
        "있어도 모른다. 정처기에서 동치 분할, 경계값 분석이 이쪽 기법으로 나온다.",
        "These are black box tests; they only touch the public API.",
        "이건 블랙박스 테스트라 공개 API 만 건드립니다.",
        2,
        Category.CS,
        Subject.DEVELOP,
    ),
    (
        "white box",
        "/ˈwaɪt ˌbɑks/",
        "코드 안을 보며 경로를 따라가기",
        "내부 코드를 보고 어느 갈래까지 실행되는지 확인하는 시험 방식. 조건문마다 참과 "
        "거짓을 다 지나가게 만드는 식이다. 빠뜨린 경로를 찾는 데 강하지만, 코드가 바뀌면 "
        "시험도 같이 고쳐야 한다. 정처기에서 구문·조건·결정 커버리지로 묻는다.",
        "White box testing revealed a branch that was never executed.",
        "화이트박스 테스트에서 한 번도 실행되지 않는 갈래가 드러났습니다.",
        2,
        Category.CS,
        Subject.DEVELOP,
    ),
    (
        "test case",
        "/ˈtest ˌkeɪs/",
        "무엇을 넣어 무엇을 기대하는지 적은 것",
        "어떤 입력을 주고 어떤 결과를 기대하는지 하나로 적어둔 것. 기대값이 없으면 실행만 "
        "하고 통과 여부를 판단할 수 없다. 하나에 여러 가지를 확인하면 실패했을 때 무엇이 "
        "깨졌는지 알기 어려우므로, 하나에 하나만 본다.",
        "Add a test case for the empty input; it currently throws.",
        "빈 입력에 대한 테스트 케이스를 추가하세요. 지금은 예외가 납니다.",
        1,
        Category.CS,
        Subject.DEVELOP,
    ),
    (
        "code coverage",
        "/ˌkoʊd ˈkʌvərɪdʒ/",
        "테스트가 지나간 코드의 비율",
        "시험을 돌렸을 때 실제로 실행된 코드가 얼마나 되는지 재는 값. 낮으면 안 본 곳이 "
        "많다는 뜻이라 쓸모가 있지만, 높다고 잘 만든 시험은 아니다. 실행만 하고 결과를 "
        "확인하지 않아도 숫자는 올라간다. 목표 수치를 정해두면 그 숫자를 맞추는 시험이 생긴다.",
        "Coverage went up but the new tests assert nothing.",
        "커버리지는 올랐는데 새 테스트가 아무것도 검증하지 않습니다.",
        2,
        Category.CS,
        Subject.DEVELOP,
    ),
    (
        "version control",
        "/ˈvɜrʒən kənˌtroʊl/",
        "바뀐 내력을 남기며 관리하기",
        "언제 누가 무엇을 바꿨는지 기록하면서 코드를 관리하는 것. 되돌릴 수 있고 여러 "
        "사람이 같은 파일을 만져도 합칠 수 있다. 정처기에서 형상 관리라는 이름으로 나오고, "
        "여기에 문서와 산출물까지 포함해 다룬다.",
        "Generated files should not be tracked by version control.",
        "생성된 파일은 형상 관리 대상에 넣지 않아야 합니다.",
        1,
        Category.GIT,
        Subject.DEVELOP,
    ),
    # ---- 3과목 데이터베이스 구축 ----
    (
        "candidate key",
        "/ˈkændɪdət ki/",
        "기본키가 될 수 있는 후보",
        "행 하나를 유일하게 가리킬 수 있으면서 더 줄이면 그 성질을 잃는 열의 묶음. 이 중 "
        "하나를 골라 기본키로 삼고 나머지는 대체키가 된다. 정처기에서 유일성과 최소성 두 "
        "조건으로 묻는다 - 유일하기만 하면 후보가 아니라 슈퍼키다.",
        "Both the email and the employee number are candidate keys here.",
        "여기서는 이메일과 사번 둘 다 후보키입니다.",
        3,
        Category.DATABASE,
        Subject.DATABASE,
    ),
    (
        "referential integrity",
        "/ˌrefəˈrenʃəl ɪnˌtegrəti/",
        "가리키는 대상이 실제로 있게 지키기",
        "외래키가 가리키는 행이 반드시 존재하도록 지키는 규칙. 없는 부서를 가리키는 직원 "
        "행이 생기지 않게 막는다. 부모를 지울 때 자식을 어떻게 할지 함께 정해야 하는데, "
        "그걸 안 정하면 지우는 쪽에서 막히거나 자식이 통째로 사라진다.",
        "The delete failed because of a referential integrity constraint.",
        "참조 무결성 제약 때문에 삭제가 실패했습니다.",
        3,
        Category.DATABASE,
        Subject.DATABASE,
    ),
    # ---- 4과목 프로그래밍 언어 활용 ----
    (
        "pointer",
        "/ˈpɔɪntər/",
        "값이 아니라 값이 있는 자리를 가리키기",
        "데이터 자체가 아니라 그 데이터가 놓인 메모리 위치를 담는 변수. 큰 값을 복사하지 "
        "않고 넘길 수 있다. 가리키던 자리가 이미 없어졌는데 그대로 쓰면 엉뚱한 값을 읽거나 "
        "프로그램이 죽는다. 정처기에서 C 언어 문제로 자주 나온다.",
        "The pointer is dangling after the object goes out of scope.",
        "객체가 유효 범위를 벗어난 뒤라 포인터가 허공을 가리킵니다.",
        3,
        Category.CS,
        Subject.LANGUAGE,
    ),
    (
        "call by value",
        "/ˈkɔl baɪ ˌvælju/",
        "값을 복사해 넘기기",
        "함수에 값을 넘길 때 복사본을 만들어 넘기는 방식. 함수 안에서 아무리 바꿔도 부른 "
        "쪽의 원래 값은 그대로다. 안전한 대신 큰 데이터는 복사 비용이 든다. 정처기에서 "
        "참조 호출과 짝으로 나와, 실행 결과를 손으로 따라가는 문제가 나온다.",
        "Java passes primitives by value, so the swap has no effect.",
        "자바는 기본형을 값으로 넘기므로 이 교환은 아무 효과가 없습니다.",
        2,
        Category.CS,
        Subject.LANGUAGE,
    ),
    (
        "call by reference",
        "/kɔl baɪ ˈrefərəns/",
        "자리를 넘겨 원본을 고치게 하기",
        "값을 복사하지 않고 원본이 있는 자리를 넘기는 방식. 함수 안에서 바꾸면 부른 쪽의 "
        "값도 같이 바뀐다. 큰 데이터를 복사하지 않아 빠르지만, 어디서 값이 바뀌었는지 "
        "쫓기 어려워진다. 값 호출과 함께 정처기 단골 문제다.",
        "Passing by reference here means the caller's list is modified.",
        "여기서 참조로 넘기면 호출한 쪽의 리스트가 바뀝니다.",
        2,
        Category.CS,
        Subject.LANGUAGE,
    ),
)


class Command(BaseCommand):
    help = "정처기 범위에서 비어 있던 용어를 채웁니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="저장하지 않고 무엇이 들어갈지만 보여줍니다.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]

        created = 0
        skipped = 0

        for row in EXAM_WORDS:
            (
                term,
                pronunciation,
                meaning,
                description,
                example,
                example_translation,
                difficulty,
                category,
                subject,
            ) = row

            if Word.objects.filter(term=term).exists():
                skipped += 1
                continue

            if not dry_run:
                Word.objects.create(
                    term=term,
                    pronunciation=pronunciation,
                    meaning=meaning,
                    description=description,
                    example=example,
                    example_translation=example_translation,
                    difficulty=difficulty,
                    category=category,
                    is_exam=True,
                    exam_subject=subject,
                    source="직접 작성",
                    # 사람이 쓴 것은 검수 대기를 거치지 않는다. 위 독스트링 참고.
                    is_reviewed=True,
                )
            created += 1
            self.stdout.write(f"  {subject:9} {term}")

        self.stdout.write("")
        self.stdout.write(f"추가: {created}개 / 이미 있어 건너뜀: {skipped}개")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run 이라 저장하지 않았습니다."))
