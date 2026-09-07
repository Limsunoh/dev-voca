"""문장을 더 넣는다. seed_sentences 의 뒤를 잇는 묶음.

사용:
    python manage.py seed_sentences_more --dry-run
    python manage.py seed_sentences_more

**파일을 나눈 이유**: seed_sentences.py 가 이미 1,400줄이 넘는다. 한 파일에
계속 쌓으면 어느 묶음을 언제 넣었는지가 diff 로만 남고, 분류별 균형을 다시
셀 때 전체를 훑어야 한다. 여기는 "무엇이 모자라서 넣었나" 를 위에 적어둔다.

**무엇이 모자랐나** (2026-09-08 실측, 문장 380개 기준)

    실무 표현(phrase)  database 7 · api 10 · debug 12 · frontend 13 · git 13
    에러 메시지(error) review 0

에러 메시지는 분류마다 30~51개인데 실무 표현은 한 자릿수인 분류가 있었다.
문제풀기가 둘을 섞어 내므로 한쪽만 많으면 같은 문장이 자주 돌아온다.
review 에 에러가 없던 것은 "코드 리뷰에서 나오는 에러" 를 린터·CI 출력으로
보면 채울 수 있다 - 리뷰 과정에서 실제로 마주치는 것들이다.

규칙은 seed_sentences 와 같다. slug 는 한 번 정하면 바꾸지 않고,
is_reviewed=True 로 들어간다(사람이 쓴 것이라 검수 대기를 안 거친다).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.vocab.models import Sentence, SentenceKind

E = Sentence.Difficulty.EASY
N = Sentence.Difficulty.NORMAL
H = Sentence.Difficulty.HARD

GIT = Sentence.Category.GIT
REVIEW = Sentence.Category.REVIEW
API = Sentence.Category.API
DB = Sentence.Category.DATABASE
OPS = Sentence.Category.DEVOPS
DEBUG = Sentence.Category.DEBUG
FRONT = Sentence.Category.FRONTEND
CS = Sentence.Category.CS

PHRASE = SentenceKind.PHRASE
ERROR = SentenceKind.ERROR

# (slug, text, translation, kind, category, difficulty, context, description)
SENTENCES: list[tuple[str, str, str, str, str, int, str, str]] = [
    # ---------- 데이터베이스 실무 표현 (7개뿐이었다) ----------
    (
        "db-add-index",
        "Can we add an index on this column? The query is doing a full scan.",
        "이 열에 인덱스를 추가할 수 있을까요? 쿼리가 전체 탐색을 하고 있어요.",
        PHRASE, DB, N,
        "느린 쿼리를 이야기할 때",
        "full scan 은 표를 처음부터 끝까지 훑는다는 뜻이다. 행이 적을 때는 "
        "문제없지만 늘어나면 그대로 느려진다. 인덱스는 조회를 빠르게 하는 대신 "
        "쓰기를 조금 느리게 하므로 무조건 붙이지는 않는다.",
    ),
    (
        "db-n-plus-one",
        "This looks like an N+1; can you use select_related here?",
        "이건 N+1 같은데요, 여기서 select_related 를 쓸 수 있나요?",
        PHRASE, DB, H,
        "리뷰에서 쿼리 문제를 지적할 때",
        "목록 하나를 불러온 뒤 각 행마다 쿼리를 또 날리는 것을 N+1 이라고 한다. "
        "화면에서는 멀쩡해 보이고 데이터가 적을 때는 티도 안 나서, 운영에 올라간 "
        "뒤에 느려진다. ORM 을 쓰면 쉽게 만들어진다.",
    ),
    (
        "db-migration-review",
        "Please double-check this migration before it hits production.",
        "이 마이그레이션이 운영에 올라가기 전에 한 번 더 확인해 주세요.",
        PHRASE, DB, N,
        "스키마 변경을 배포하기 전",
        "hit production 은 '운영에 반영된다' 는 뜻이다. 마이그레이션은 되돌리기 "
        "어렵고 큰 표에서는 잠금이 오래 걸리므로 따로 확인한다.",
    ),
    (
        "db-lock-timeout-talk",
        "The migration timed out because the table was locked.",
        "표가 잠겨 있어서 마이그레이션이 시간 초과됐습니다.",
        PHRASE, DB, H,
        "배포가 중간에 멈췄을 때",
        "스키마를 바꾸려면 그 표를 잠가야 하는데, 다른 트랜잭션이 이미 쓰고 있으면 "
        "기다리다 끝난다. 큰 표는 트래픽이 적은 시간에 하거나 잠금이 짧은 방식을 "
        "고른다.",
    ),
    (
        "db-soft-delete",
        "Should we soft delete this instead of removing the row?",
        "행을 지우는 대신 소프트 삭제로 할까요?",
        PHRASE, DB, N,
        "삭제 방식을 정할 때",
        "실제로 지우지 않고 '지워졌음' 표시만 남기는 것을 soft delete 라고 한다. "
        "되돌릴 수 있고 이력이 남지만, 조회할 때마다 그 표시를 걸러야 해서 한 "
        "곳이라도 빠뜨리면 지운 것이 다시 보인다.",
    ),
    (
        "db-backup-restore",
        "Let's restore from last night's backup on a staging database first.",
        "먼저 스테이징 DB 에 어젯밤 백업을 복원해 봅시다.",
        PHRASE, DB, N,
        "데이터를 되돌려야 할 때",
        "운영에 바로 복원하지 않고 따로 확인하는 절차다. 백업이 실제로 열리는지, "
        "어느 시점까지 들어 있는지는 복원해 봐야 안다.",
    ),
    (
        "db-connection-pool-talk",
        "We're running out of connections; the pool size is too small.",
        "연결이 부족합니다. 풀 크기가 너무 작아요.",
        PHRASE, DB, H,
        "부하가 몰릴 때",
        "DB 연결은 만들 때마다 비용이 들어 미리 몇 개를 만들어 돌려 쓴다. 그 묶음이 "
        "커넥션 풀이다. 크기가 작으면 요청이 줄을 서고, 너무 크면 DB 쪽이 먼저 "
        "버티지 못한다.",
    ),

    # ---------- API 실무 표현 (10개뿐이었다) ----------
    (
        "api-breaking-change",
        "This is a breaking change; we need to version the endpoint.",
        "이건 호환성을 깨는 변경이라 엔드포인트에 버전을 붙여야 합니다.",
        PHRASE, API, H,
        "API 응답 형태를 바꿀 때",
        "이미 쓰고 있는 쪽이 그대로 두면 깨지는 변경을 breaking change 라고 한다. "
        "필드를 지우거나 이름을 바꾸는 것이 대표적이다. 더하는 것은 대개 안전하다.",
    ),
    (
        "api-rate-limited",
        "We're getting rate limited; can we batch these requests?",
        "요청 제한에 걸리고 있어요. 이 요청들을 묶을 수 있을까요?",
        PHRASE, API, N,
        "외부 API 를 자주 부를 때",
        "정해진 시간에 부를 수 있는 횟수를 넘기면 거절당한다. 하나씩 부르던 것을 "
        "한 번에 묶어 보내면 횟수가 줄어든다.",
    ),
    (
        "api-idempotent-retry",
        "Make sure the retry is idempotent, otherwise we'll double charge.",
        "재시도가 멱등인지 확인하세요. 아니면 이중 청구가 납니다.",
        PHRASE, API, H,
        "결제나 주문을 다룰 때",
        "같은 요청을 여러 번 보내도 결과가 한 번 보낸 것과 같으면 멱등이다. "
        "네트워크가 끊기면 성공했는지 모른 채 다시 보내게 되므로, 돈이 걸린 "
        "경로에서는 필수다.",
    ),
    (
        "api-deprecate-notice",
        "This endpoint is deprecated; please migrate by the end of the quarter.",
        "이 엔드포인트는 폐기 예정입니다. 분기 말까지 옮겨 주세요.",
        PHRASE, API, N,
        "옛 API 를 정리할 때",
        "deprecated 는 '아직 되지만 곧 없앤다' 는 뜻이다. 바로 안 지우는 것은 쓰는 "
        "쪽에 옮길 시간을 주기 위해서다.",
    ),
    (
        "api-pagination-ask",
        "Could you paginate this? Returning all rows will time out.",
        "이걸 페이지로 나눠 주실 수 있나요? 전부 반환하면 시간 초과가 납니다.",
        PHRASE, API, N,
        "목록 API 를 설계할 때",
        "행이 늘어나면 한 번에 다 주는 것이 불가능해진다. 처음부터 나눠 주면 나중에 "
        "고칠 일이 없다. 쓰는 쪽 코드가 바뀌므로 나중에 바꾸기가 특히 번거롭다.",
    ),
    (
        "api-mock-first",
        "Let's mock the response first so the frontend isn't blocked.",
        "프론트가 막히지 않게 응답을 먼저 흉내내 둡시다.",
        PHRASE, API, E,
        "백엔드가 아직 준비 안 됐을 때",
        "mock 은 실제 대신 가짜로 만들어 두는 것이다. 형태만 맞으면 양쪽이 동시에 "
        "작업할 수 있다. 대신 실제와 어긋나면 붙일 때 드러난다.",
    ),

    # ---------- 디버깅 실무 표현 (12개뿐이었다) ----------
    (
        "debug-cannot-reproduce",
        "I can't reproduce it locally; does it only happen in production?",
        "로컬에서는 재현이 안 되는데요, 운영에서만 나나요?",
        PHRASE, DEBUG, N,
        "버그 리포트를 받고 처음 물어볼 때",
        "재현이 안 되면 고쳤는지도 알 수 없다. 환경 차이(데이터·설정·부하)를 먼저 "
        "의심한다. 이 질문이 나오면 재현 조건을 더 자세히 적어 주는 것이 가장 빠르다.",
    ),
    (
        "debug-bisect-suggest",
        "Let's bisect to find which commit introduced this.",
        "어느 커밋에서 들어왔는지 이분 탐색으로 찾아봅시다.",
        PHRASE, DEBUG, H,
        "언제부터 깨졌는지 모를 때",
        "정상이던 커밋과 깨진 커밋 사이를 절반씩 좁혀 원인 커밋을 찾는다. git "
        "bisect 가 그 절차를 자동으로 도와준다. 커밋이 작게 나뉘어 있을수록 빨리 "
        "좁혀진다.",
    ),
    (
        "debug-add-logging",
        "Can we add logging around this block? We're flying blind.",
        "이 구간에 로그를 넣을 수 있을까요? 지금은 아무것도 안 보입니다.",
        PHRASE, DEBUG, N,
        "원인을 좁히지 못할 때",
        "fly blind 는 계기 없이 비행한다는 말에서 왔다. 로그가 없으면 추측만 "
        "하게 된다. 다만 개인정보나 비밀값은 로그에 남기지 않는다.",
    ),
    (
        "debug-race-condition",
        "This smells like a race condition; it only fails under load.",
        "이건 경합 문제 같습니다. 부하가 있을 때만 실패해요.",
        PHRASE, DEBUG, H,
        "간헐적으로 실패할 때",
        "smell like 는 '~인 것 같다' 는 뜻으로 확신 전에 쓴다. 순서가 보장되지 "
        "않은 두 작업이 겹칠 때 나는 문제라, 혼자 돌리면 거의 재현되지 않는다.",
    ),
    (
        "debug-revert-first",
        "Let's revert first and investigate after; production is down.",
        "일단 되돌리고 원인은 나중에 봅시다. 운영이 멈춰 있어요.",
        PHRASE, DEBUG, N,
        "장애 대응 중",
        "원인을 찾는 것보다 서비스를 되살리는 것이 먼저라는 판단이다. 되돌린 뒤에 "
        "차분히 보는 편이 낫고, 급한 상태에서 고치면 더 큰 문제를 만든다.",
    ),

    # ---------- 프론트엔드 실무 표현 (13개뿐이었다) ----------
    (
        "front-layout-shift",
        "The image causes a layout shift; can we set explicit dimensions?",
        "이미지 때문에 레이아웃이 밀립니다. 크기를 명시할 수 있을까요?",
        PHRASE, FRONT, N,
        "화면이 덜컹거릴 때",
        "이미지가 늦게 도착하면 그 자리를 모르던 브라우저가 나중에 자리를 만들면서 "
        "아래 내용이 밀린다. 크기를 미리 알려주면 자리를 먼저 잡아둔다.",
    ),
    (
        "front-hydration-mismatch",
        "There's a hydration mismatch; the server and client render differently.",
        "하이드레이션 불일치가 있어요. 서버와 클라이언트가 다르게 그립니다.",
        PHRASE, FRONT, H,
        "SSR 화면이 깜빡일 때",
        "서버가 그린 HTML 과 브라우저가 그린 결과가 다르면 나온다. 시각이나 "
        "무작위 값처럼 매번 달라지는 것을 렌더에 쓰면 생긴다.",
    ),
    (
        "front-a11y-label",
        "This button needs an accessible label; screen readers announce nothing.",
        "이 버튼에는 접근성 라벨이 필요합니다. 스크린리더가 아무것도 안 읽어요.",
        PHRASE, FRONT, N,
        "아이콘만 있는 버튼을 리뷰할 때",
        "그림만 있는 버튼은 눈으로는 알 수 있지만 소리로는 빈 버튼이다. aria-label "
        "이나 화면에 안 보이는 글자를 넣어 이름을 준다.",
    ),
    (
        "front-bundle-size",
        "This library adds 300KB to the bundle; is there a lighter option?",
        "이 라이브러리가 번들에 300KB 를 더합니다. 더 가벼운 선택지가 있을까요?",
        PHRASE, FRONT, N,
        "의존성을 추가하려 할 때",
        "번들이 커지면 첫 화면이 늦게 뜬다. 특히 모바일에서 차이가 크다. 몇 줄이면 "
        "되는 기능에 라이브러리를 넣지 않는지 먼저 본다.",
    ),
    (
        "front-debounce-input",
        "Let's debounce the search input; it fires on every keystroke.",
        "검색 입력에 디바운스를 겁시다. 지금은 키를 칠 때마다 요청이 나갑니다.",
        PHRASE, FRONT, N,
        "입력할 때마다 요청이 나갈 때",
        "마지막 입력 뒤 잠깐 기다렸다 한 번만 보내는 것을 디바운스라고 한다. "
        "요청 수가 줄고 서버 부담도 준다.",
    ),
    (
        "front-mobile-check",
        "Did you check this on mobile? The buttons overlap at 390px.",
        "모바일에서 확인하셨나요? 390px 에서 버튼이 겹칩니다.",
        PHRASE, FRONT, E,
        "좁은 화면을 놓쳤을 때",
        "데스크톱은 여백이 넉넉해 겹침이 안 보인다. 폰 폭에서 먼저 보는 습관이 "
        "이런 것을 막는다.",
    ),

    # ---------- Git 실무 표현 (13개뿐이었다) ----------
    (
        "git-squash-before-merge",
        "Can you squash these commits before merging?",
        "병합 전에 이 커밋들을 하나로 합쳐 주실 수 있나요?",
        PHRASE, GIT, N,
        "커밋이 잘게 나뉘어 있을 때",
        "squash 는 여러 커밋을 하나로 누르는 것이다. '오타 수정' 같은 커밋이 "
        "히스토리에 남지 않게 정리한다. 팀마다 방침이 달라 물어보는 편이 낫다.",
    ),
    (
        "git-force-push-warning",
        "Don't force push to main; other people have pulled it already.",
        "main 에 강제 푸시하지 마세요. 다른 사람들이 이미 받아 갔습니다.",
        PHRASE, GIT, H,
        "히스토리를 고치려 할 때",
        "강제 푸시는 원격의 기록을 덮어쓴다. 남이 이미 받아 간 커밋이 사라지면 "
        "그 사람의 작업이 꼬인다. 자기 브랜치에서만 쓴다.",
    ),
    (
        "git-cherry-pick-hotfix",
        "Cherry-pick that fix onto the release branch too.",
        "그 수정을 릴리스 브랜치에도 따로 가져가 주세요.",
        PHRASE, GIT, N,
        "긴급 수정을 여러 갈래에 반영할 때",
        "cherry-pick 은 커밋 하나만 골라 다른 브랜치에 얹는 것이다. 브랜치 전체를 "
        "합칠 수 없을 때 쓴다.",
    ),
    (
        "git-conflict-resolve",
        "I'll resolve the conflicts and push again.",
        "충돌을 해결하고 다시 푸시하겠습니다.",
        PHRASE, GIT, E,
        "병합 충돌이 났을 때",
        "같은 줄을 양쪽이 고쳤을 때 git 이 어느 쪽을 남길지 못 정해 사람에게 "
        "넘긴다. 양쪽 의도를 다 이해하고 합쳐야 해서 기계가 못 한다.",
    ),
    (
        "git-draft-pr",
        "I opened it as a draft; not ready for review yet.",
        "초안으로 열어뒀습니다. 아직 리뷰받을 준비는 안 됐어요.",
        PHRASE, GIT, E,
        "작업 중인 PR 을 공유할 때",
        "draft 로 열면 진행 상황을 보여주면서 리뷰 요청은 안 한 상태가 된다. "
        "CI 를 미리 돌려보는 용도로도 쓴다.",
    ),

    # ---------- 코드 리뷰에서 마주치는 에러 (0개였다) ----------
    (
        "review-lint-unused-var",
        "error: 'result' is assigned a value but never used  no-unused-vars",
        "오류: 'result' 에 값을 넣었지만 쓰지 않았습니다  no-unused-vars",
        ERROR, REVIEW, E,
        "린터가 PR 에서 막을 때",
        "쓰지 않는 변수는 대개 지우다 만 코드다. 남겨두면 읽는 사람이 '언젠가 "
        "쓰겠지' 하고 넘긴다. 정말 필요하면 이름 앞에 밑줄을 붙여 의도를 밝힌다.",
    ),
    (
        "review-prettier-diff",
        "Code style issues found in the above file. Run Prettier to fix.",
        "위 파일에서 코드 스타일 문제가 발견됐습니다. Prettier 로 고치세요.",
        ERROR, REVIEW, E,
        "포맷 검사가 실패할 때",
        "들여쓰기나 따옴표 같은 것을 도구가 통일한다. 사람이 손으로 맞추지 않고 "
        "명령 한 번으로 고치는 것이 전제라, 이 실패는 대개 실행을 잊은 것이다.",
    ),
    (
        "review-coverage-drop",
        "Coverage decreased from 82.4% to 79.1% in this pull request.",
        "이 PR 에서 커버리지가 82.4% 에서 79.1% 로 떨어졌습니다.",
        ERROR, REVIEW, N,
        "CI 가 커버리지를 확인할 때",
        "새 코드에 테스트가 없으면 비율이 내려간다. 다만 숫자를 채우려고 검증 없는 "
        "테스트를 쓰면 커버리지만 오르고 아무것도 막지 못한다.",
    ),
    (
        "review-required-check",
        "Required status check \"build\" is expected but not reported.",
        "필수 상태 검사 \"build\" 가 필요한데 보고되지 않았습니다.",
        ERROR, REVIEW, N,
        "머지 버튼이 안 눌릴 때",
        "브랜치 보호 규칙이 특정 검사를 요구하는데 그 검사가 아직 안 돌았거나 "
        "이름이 바뀐 경우다. 워크플로 이름과 규칙에 적힌 이름이 같은지 본다.",
    ),
    (
        "review-merge-conflict-block",
        "This branch has conflicts that must be resolved.",
        "이 브랜치에는 해결해야 할 충돌이 있습니다.",
        ERROR, REVIEW, E,
        "PR 화면에서 머지가 막힐 때",
        "내 브랜치를 판 뒤 main 이 같은 곳을 고쳤다는 뜻이다. main 을 내 브랜치로 "
        "가져와 합친 뒤 다시 올린다.",
    ),
    (
        "review-branch-behind",
        "This branch is out-of-date with the base branch.",
        "이 브랜치가 기준 브랜치보다 뒤처져 있습니다.",
        ERROR, REVIEW, N,
        "머지 직전에 막힐 때",
        "충돌은 없지만 최신 상태가 아니라는 뜻이다. 최신 코드와 함께 테스트가 "
        "통과하는지 보려고 막는 설정이다. 기준 브랜치를 가져와 합치면 풀린다.",
    ),
    (
        "review-large-diff",
        "This pull request is too large to review effectively (1,847 lines changed).",
        "이 PR 은 제대로 리뷰하기에 너무 큽니다 (1,847줄 변경).",
        ERROR, REVIEW, N,
        "PR 크기를 경고할 때",
        "크면 리뷰어가 대충 보게 되고 문제도 놓친다. 기능과 리팩터링을 나누거나 "
        "단계별로 쪼개면 각각은 읽을 만해진다.",
    ),
    (
        "review-secret-detected",
        "Secret detected: generic-api-key in config/settings.py:14",
        "비밀값 감지: config/settings.py:14 에 일반 API 키",
        ERROR, REVIEW, H,
        "보안 검사가 커밋을 막을 때",
        "키가 커밋에 들어가면 지워도 히스토리에 남는다. 그 키는 이미 유출된 것으로 "
        "보고 새로 발급받아야 한다. 환경변수로 옮기는 것이 다음 순서다.",
    ),
]


class Command(BaseCommand):
    help = "문장 데이터를 추가로 넣습니다(seed_sentences 의 뒤를 잇는 묶음)."

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

        for row in SENTENCES:
            slug, text, translation, kind, category, difficulty, context, description = row

            if Sentence.objects.filter(slug=slug).exists():
                skipped += 1
                continue

            if not dry_run:
                Sentence.objects.create(
                    slug=slug,
                    text=text,
                    translation=translation,
                    kind=kind,
                    category=category,
                    difficulty=difficulty,
                    context=context,
                    description=description,
                    source="직접 작성",
                    # 사람이 쓴 것은 검수 대기를 안 거친다. seed_sentences 와 같다.
                    is_reviewed=True,
                )
            created += 1
            self.stdout.write(f"  {category:9} {kind:7} {slug}")

        self.stdout.write("")
        self.stdout.write(f"추가: {created}개 / 이미 있어 건너뜀: {skipped}개")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run 이라 저장하지 않았습니다."))
