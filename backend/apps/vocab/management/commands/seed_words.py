"""초기 단어 데이터를 넣는다.

사용:
    python manage.py seed_words          # 없는 것만 추가
    python manage.py seed_words --reset  # 같은 term 이 있으면 내용을 갱신

--reset 은 검수 대기 중인 단어를 건너뛴다. 그것까지 시드 값으로 덮어쓰려면
--reset --force-pending 을 함께 준다. 검수를 기다리던 AI 생성물이 사라지므로
Admin 에서 처리할 수 없을 때만 쓴다.

AI 생성물(generate_words)과 달리 is_reviewed=True 로 들어간다. 이 데이터는
소스 코드에 리터럴로 박혀 있어 git diff 와 코드 리뷰를 거치므로, Admin 검수를
코드 리뷰가 대신한다. 검수 게이트를 우회해도 된다는 뜻이 아니다 - 사용자
조회 경로(views.py)는 여전히 is_reviewed=True 만 내보낸다.

서비스를 처음 띄웠을 때 빈 화면이 보이지 않게 하는 것이 목적이다.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.vocab.models import Word

E = Word.Difficulty.EASY
N = Word.Difficulty.NORMAL
H = Word.Difficulty.HARD

# 분류도 상수로 받는다. 문자열을 그대로 쓰면 "devpos" 같은 오타가 나도
# 저장은 되고, 화면에서 라벨만 조용히 빈칸으로 나온다.
GIT = Word.Category.GIT
REVIEW = Word.Category.REVIEW
API = Word.Category.API
DB = Word.Category.DATABASE
OPS = Word.Category.DEVOPS
DEBUG = Word.Category.DEBUG
# 아직 이 목록에 쓰인 단어는 없다. 분류와 제약을 먼저 열어둬야
# 프론트엔드·CS 단어를 받았을 때 CheckConstraint 에 걸리지 않는다.
FRONT = Word.Category.FRONTEND
CS = Word.Category.CS

# (term, pronunciation, meaning, category, difficulty, description, example, example_translation)
#
# 발음기호는 IPA(미국식). 개발자만 쓰는 말이라 사전에 없거나 발음이 갈리면
# 빈 문자열로 둔다 - 틀린 발음을 가르치느니 비우는 편이 낫다.
#
# category/difficulty 는 TextChoices/IntegerChoices 라 각각 str/int 로 취급된다.
WORDS: list[tuple[str, str, str, str, int, str, str, str]] = [
    # ---------- git ----------
    (
        "commit", "/kəˈmɪt/", "변경사항을 저장하다", GIT, E,
        "작업한 내용을 하나의 기록으로 묶어 저장하는 것. 저장할 때 남기는 설명을 "
        "커밋 메시지라고 한다.",
        "Commit your changes before switching branches.",
        "브랜치를 바꾸기 전에 변경사항을 커밋하세요.",
    ),
    (
        "merge", "/mɜrdʒ/", "병합하다", GIT, E,
        "두 갈래로 나뉜 작업을 하나로 합치는 것. 같은 줄을 양쪽에서 고쳤으면 "
        "충돌(conflict)이 나고 사람이 골라줘야 한다.",
        "This branch has conflicts that must be resolved before merging.",
        "이 브랜치는 병합하기 전에 해결해야 할 충돌이 있습니다.",
    ),
    (
        "rebase", "/ˌriˈbeɪs/", "기준을 옮기다", GIT, H,
        "내 작업의 출발점을 최신 커밋으로 옮겨 히스토리를 일직선으로 만드는 것. "
        "이미 공유한 브랜치에 하면 남의 기록이 어긋나므로 주의한다.",
        "Rebase onto main before opening a pull request.",
        "풀 리퀘스트를 열기 전에 main 위로 리베이스하세요.",
    ),
    (
        "stash", "/stæʃ/", "잠시 치워두다", GIT, N,
        "아직 커밋하기 애매한 작업을 임시로 빼두는 것. 급한 수정을 먼저 해야 할 때 쓴다.",
        "Stash your work and check out the hotfix branch.",
        "작업을 스태시하고 핫픽스 브랜치로 이동하세요.",
    ),
    (
        "revert", "/rɪˈvɜrt/", "취소하는 커밋을 만들다", GIT, N,
        "이미 저장한 변경을 되돌리는 새 커밋을 쌓는 것. 히스토리를 다시 쓰지 않아 "
        "이미 공유한 브랜치에서도 안전하다. reset 은 히스토리를 옮기므로 "
        "공유된 곳에서는 위험하다.",
        "We reverted the commit that broke the build.",
        "빌드를 깨뜨린 커밋을 되돌렸습니다.",
    ),
    (
        "squash", "/skwɑʃ/", "여러 개를 하나로 합치다", GIT, N,
        "자잘한 커밋 여러 개를 하나로 뭉치는 것. 히스토리를 읽기 쉽게 정리할 때 쓴다.",
        "Squash these five commits into one before merging.",
        "병합 전에 이 다섯 커밋을 하나로 합치세요.",
    ),
    # ---------- 코드 리뷰 ----------
    (
        "refactor", "/riˈfæktər/", "구조를 정리하다", REVIEW, N,
        "동작은 그대로 두고 코드를 읽기 좋게 고치는 것. 기능 변경과 섞지 않는 것이 원칙이다.",
        "This refactor changes no behavior, only structure.",
        "이 리팩터링은 동작을 바꾸지 않고 구조만 바꿉니다.",
    ),
    (
        "deprecated", "/ˈdeprəˌkeɪtɪd/", "더 이상 권장하지 않는", REVIEW, N,
        "아직 동작하지만 곧 사라질 예정이라 새로 쓰면 안 되는 것. 대체할 방법이 "
        "함께 안내되는 경우가 많다.",
        "This method is deprecated; use the new API instead.",
        "이 메서드는 폐기 예정입니다. 새 API 를 사용하세요.",
    ),
    (
        "edge case", "/ˈedʒ ˌkeɪs/", "경계에 놓인 예외적 경우", REVIEW, N,
        "정상 흐름에서 벗어난 예외적 상황. 빈 목록, 0, 음수, 아주 긴 입력처럼 "
        "값의 경계에 놓인 경우들이다. 드물어서가 아니라 경계여서 놓치기 쉽다.",
        "The function works, but it fails on this edge case.",
        "함수는 동작하지만 이 예외 상황에서 실패합니다.",
    ),
    (
        "trade-off", "/ˈtreɪd ˌɔf/", "얻는 대신 잃는 것", REVIEW, N,
        "하나를 얻으려면 다른 하나를 포기해야 하는 관계. 속도와 메모리, 단순함과 "
        "유연함처럼 짝을 이룬다.",
        "There is a trade-off between speed and memory usage.",
        "속도와 메모리 사용량 사이에는 트레이드오프가 있습니다.",
    ),
    (
        "boilerplate", "/ˈbɔɪlərpleɪt/", "매번 반복되는 형식적인 코드", REVIEW, N,
        "내용은 거의 같은데 어디서나 필요해서 계속 쓰게 되는 코드. 줄이는 것이 좋지만 "
        "무리한 추상화보다는 낫다는 의견도 있다.",
        "This framework removes a lot of boilerplate.",
        "이 프레임워크는 반복 코드를 많이 줄여줍니다.",
    ),
    # ---------- API ----------
    (
        "endpoint", "/ˈendpɔɪnt/", "요청을 받는 주소", API, E,
        "서버에서 특정 기능을 담당하는 URL. /api/words/ 처럼 경로와 메서드가 짝을 이룬다.",
        "The endpoint returns a list of words in JSON.",
        "이 엔드포인트는 단어 목록을 JSON 으로 돌려줍니다.",
    ),
    (
        "payload", "/ˈpeɪloʊd/", "실제로 담아 보내는 내용", API, N,
        "요청이나 응답에서 헤더 같은 포장을 뺀 알맹이 데이터.",
        "The request payload must include a valid token.",
        "요청 페이로드에는 유효한 토큰이 포함되어야 합니다.",
    ),
    (
        "idempotent", "/aɪˈdempətənt/", "여러 번 해도 상태가 같은", API, H,
        "같은 요청을 두 번 보내도 서버에 남는 결과가 한 번 보낸 것과 같은 성질. "
        "응답까지 같다는 뜻은 아니다 - 두 번째 삭제 요청이 404 를 돌려줘도 "
        "이미 지워졌다는 점에서는 멱등하다. 재시도가 안전해진다.",
        "PUT should be idempotent, but POST usually is not.",
        "PUT 은 멱등해야 하지만 POST 는 보통 그렇지 않습니다.",
    ),
    (
        "throttle", "/ˈθrɑtəl/", "속도를 제한하다", API, N,
        "짧은 시간에 너무 많은 요청이 오지 않도록 막는 것. 초과하면 429 를 돌려준다.",
        "The API throttles requests to 100 per minute.",
        "이 API 는 요청을 분당 100 건으로 제한합니다.",
    ),
    (
        "pagination", "/ˌpædʒəˈneɪʃən/", "여러 쪽으로 나눠 주기", API, N,
        "결과가 많을 때 한 번에 다 주지 않고 페이지 단위로 나눠 보내는 것. "
        "정렬 기준이 없으면 페이지를 넘길 때 같은 항목이 또 나오거나 빠질 수 있다.",
        "Use pagination when the result set is large.",
        "결과가 많을 때는 페이지네이션을 사용하세요.",
    ),
    (
        "serialize", "/ˈsɪriəlaɪz/", "전송할 수 있는 형태로 바꾸다", API, N,
        "메모리 안의 객체를 JSON 같은 문자열로 변환하는 것. 반대 과정은 역직렬화다.",
        "The serializer converts the model into JSON.",
        "시리얼라이저가 모델을 JSON 으로 변환합니다.",
    ),
    # ---------- 데이터베이스 ----------
    (
        "migration", "/maɪˈɡreɪʃən/", "DB 구조 변경 기록", DB, E,
        "테이블과 컬럼의 변경을 순서대로 적어둔 파일. 실행하면 실제 DB 구조가 바뀐다.",
        "Run the migration before starting the server.",
        "서버를 시작하기 전에 마이그레이션을 실행하세요.",
    ),
    (
        "constraint", "/kənˈstreɪnt/", "지켜야 하는 제약", DB, N,
        "DB 가 강제하는 규칙. 중복 금지(unique), 빈 값 금지(not null) 같은 것들이다.",
        "The unique constraint prevents duplicate emails.",
        "유니크 제약이 이메일 중복을 막습니다.",
    ),
    (
        "index", "/ˈɪndeks/", "빠르게 찾기 위한 색인", DB, N,
        "테이블과 별개로 만드는 찾아보기 구조. 책 뒤의 색인처럼 어느 줄에 있는지 "
        "빨리 알려준다. 조회는 빨라지지만 저장할 때마다 색인도 갱신해야 해 "
        "쓰기는 조금 느려진다.",
        "Adding an index made this query ten times faster.",
        "인덱스를 추가하니 이 쿼리가 열 배 빨라졌습니다.",
    ),
    (
        "rollback", "/ˈroʊlbæk/", "작업 전체를 무르다", DB, N,
        "지금까지 한 변경을 취소하고 시작 전 상태로 되돌리는 것. 에러가 나면 "
        "자동으로 일어나기도 하고, 사람이 직접 시킬 수도 있다. 돈은 빠져나갔는데 "
        "입금이 안 되는 것 같은 절반만 저장된 상태를 막아준다.",
        "The transaction was rolled back after the error.",
        "에러가 발생해 트랜잭션이 롤백되었습니다.",
    ),
    (
        "query", "/ˈkwɛri/", "데이터를 찾는 요청", DB, E,
        "DB 에 무엇을 달라고 보내는 명령. 느린 쿼리 하나가 서비스 전체를 느리게 만들기도 한다.",
        "This query scans the entire table.",
        "이 쿼리는 테이블 전체를 훑습니다.",
    ),
    # ---------- 배포 / 운영 ----------
    (
        "deploy", "/dɪˈplɔɪ/", "배포하다", OPS, E,
        "만든 코드를 실제 서버에 올려 사용자가 쓸 수 있게 하는 것.",
        "We deploy to production every Thursday.",
        "우리는 매주 목요일에 운영 환경으로 배포합니다.",
    ),
    (
        "rollout", "/ˈroʊlaʊt/", "점진적으로 내보내기", OPS, N,
        "새 버전을 한 번에 전부가 아니라 일부 사용자부터 순서대로 적용하는 것.",
        "We are doing a gradual rollout to ten percent of users.",
        "사용자의 10% 에게 점진적으로 배포하고 있습니다.",
    ),
    (
        "environment variable", "/ɪnˈvaɪrənmənt ˌvɛriəbəl/", "환경변수", OPS, E,
        "코드 바깥에서 주입하는 설정값. 비밀번호나 API 키를 코드에 적지 않기 위해 쓴다.",
        "Store the API key in an environment variable, not in the code.",
        "API 키는 코드가 아니라 환경변수에 저장하세요.",
    ),
    (
        "downtime", "/ˈdaʊntaɪm/", "서비스가 멈춘 시간", OPS, N,
        "사용자가 서비스를 쓸 수 없었던 시간. 배포 중에도 멈추지 않게 하는 것을 "
        "무중단 배포라고 한다.",
        "The migration caused two minutes of downtime.",
        "마이그레이션 때문에 2분간 서비스가 중단되었습니다.",
    ),
    (
        "fallback", "/ˈfɔlbæk/", "안 될 때를 위한 대비책", OPS, N,
        "원래 방법이 실패했을 때 대신 쓰는 차선책.",
        "If the cache fails, we fall back to the database.",
        "캐시가 실패하면 데이터베이스로 대체합니다.",
    ),
    # ---------- 디버깅 ----------
    (
        "stack trace", "/ˈstæk ˌtreɪs/", "에러가 난 경로 기록", DEBUG, E,
        "에러가 터진 지점까지 함수가 어떤 순서로 불렸는지 보여주는 목록. "
        "언어마다 출력 순서가 반대라(파이썬은 원인이 맨 아래, 자바스크립트는 맨 위) "
        "한 줄만 보지 말고 전체를 읽어야 한다.",
        "Paste the full stack trace, not just the last line.",
        "마지막 줄만 말고 스택 트레이스 전체를 붙여주세요.",
    ),
    (
        "reproduce", "/ˌriprəˈdus/", "같은 문제를 다시 일으키다", DEBUG, N,
        "버그를 고치기 전에 그 상황을 똑같이 만들어보는 것. 재현되지 않으면 "
        "고쳤는지도 확인할 수 없다.",
        "I cannot reproduce this bug on my machine.",
        "제 컴퓨터에서는 이 버그가 재현되지 않습니다.",
    ),
    (
        "race condition", "/ˈreɪs kənˌdɪʃən/", "순서가 꼬여 생기는 오류", DEBUG, H,
        "두 작업이 동시에 같은 것을 건드릴 때, 어느 쪽이 먼저 끝나느냐에 따라 "
        "결과가 달라지는 문제. 재현이 어려워 찾기 까다롭다.",
        "This bug only appears under load, so it may be a race condition.",
        "이 버그는 부하가 걸릴 때만 나타나므로 경합 상태일 수 있습니다.",
    ),
    (
        "regression", "/rɪˈɡreʃən/", "고쳐졌던 것이 다시 깨짐", DEBUG, N,
        "예전에 잘 되던 기능이 다른 변경 때문에 다시 망가지는 것. 이를 막으려고 "
        "회귀 테스트를 돌린다.",
        "The new release introduced a regression in the login flow.",
        "새 릴리스에서 로그인 흐름에 회귀 문제가 생겼습니다.",
    ),
]


class Command(BaseCommand):
    help = "초기 단어 데이터를 DB 에 넣습니다. 사람이 검수한 데이터라 바로 노출됩니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="같은 단어가 이미 있으면 내용을 갱신합니다.",
        )
        parser.add_argument(
            "--force-pending",
            action="store_true",
            help=(
                "--reset 과 함께 씁니다. 검수 대기 중인 단어까지 덮어씁니다. "
                "기본값은 건너뛰기입니다."
            ),
        )

    # 시드는 전부-아니면-전무로 넣는다. 재실행 비용이 0 이라, 절반만 들어간
    # 상태로 남기느니 통째로 롤백하고 다시 돌리는 편이 낫다.
    # (generate_words 는 반대로 항목별 savepoint 를 쓴다. 거기서는 항목마다
    #  API 비용이 나가서, 하나가 실패했다고 나머지를 버리면 그 돈을 버린다.)
    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        reset: bool = options["reset"]
        force_pending: bool = options["force_pending"]

        # --force-pending 은 --reset 의 동작을 바꾸는 옵션이라 혼자서는 뜻이
        # 없다. 조용히 무시하면 "덮어썼겠지" 하고 넘어가는데, 검수 게이트를
        # 여는 플래그가 의도대로 안 먹었다는 걸 모르는 게 제일 위험하다.
        if force_pending and not reset:
            raise CommandError("--force-pending 은 --reset 과 함께 써야 합니다.")

        created = updated = skipped = 0
        kept_pending: list[str] = []

        # 검수 대기 중인 단어를 한 번에 조회한다. 루프 안에서 항목마다 찾으면
        # 목록이 길어질수록 그대로 쿼리 수가 된다.
        pending_terms: set[str] = set()
        if reset:
            pending_terms = set(
                Word.objects.filter(
                    term__in=[w[0] for w in WORDS], is_reviewed=False
                ).values_list("term", flat=True)
            )

        for term, pron, meaning, category, difficulty, desc, ex, ex_ko in WORDS:
            defaults = {
                "pronunciation": pron,
                "meaning": meaning,
                "category": category,
                "difficulty": difficulty,
                "description": desc,
                "example": ex,
                "example_translation": ex_ko,
                "source": "직접 작성",
                # 이 목록은 소스에 박혀 코드 리뷰를 거친다. Admin 검수와 같은
                # 역할을 리뷰가 대신하므로 True 로 넣는다.
                #
                # 기준은 "누가 썼나" 가 아니라 "사람 눈을 거쳤나" 다.
                # 런타임에 외부(AI 생성·파일 업로드·크롤링)로 들어오는 데이터는
                # 사람이 만들었더라도 항상 False 여야 한다.
                "is_reviewed": True,
            }

            if reset:
                # 검수 대기 중인 단어는 건드리지 않는다. 덮어쓰면 아무도
                # 승인하지 않은 항목이 is_reviewed=True 로 승격되어, 검수
                # 플래그가 "사람이 봤다" 는 의미를 잃는다.
                if term in pending_terms and not force_pending:
                    kept_pending.append(term)
                    skipped += 1
                    continue

                _, was_created = Word.objects.update_or_create(
                    term=term, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            else:
                _, was_created = Word.objects.get_or_create(
                    term=term, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

        parts = [f"{created}개 추가"]
        if updated:
            parts.append(f"{updated}개 갱신")
        if skipped:
            parts.append(f"{skipped}개 건너뜀")

        self.stdout.write(self.style.SUCCESS(", ".join(parts)))

        if kept_pending:
            self.stdout.write(
                self.style.WARNING(
                    f"검수 대기 중이라 건너뛴 {len(kept_pending)}개: "
                    + ", ".join(kept_pending)
                )
            )
            self.stdout.write(
                "Admin 에서 검수하거나, 시드 값으로 덮어쓰려면 --force-pending 을 쓰세요."
            )

        self.stdout.write(f"전체 단어: {Word.objects.count()}개")
