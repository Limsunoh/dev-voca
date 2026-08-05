"""초기 문장 데이터를 넣는다.

사용:
    python manage.py seed_sentences          # 없는 것만 추가
    python manage.py seed_sentences --reset  # 같은 문장이 있으면 내용을 갱신

--reset 은 검수 대기 중인 문장을 건너뛴다. 그것까지 시드 값으로 덮어쓰려면
--reset --force-pending 을 함께 준다.

seed_words 와 같은 규칙으로 동작한다(is_reviewed=True 로 들어가는 근거,
검수 대기 보호, 전부-아니면-전무). 자세한 이유는 그쪽 주석에 있다.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
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

PHRASE = SentenceKind.PHRASE
ERROR = SentenceKind.ERROR

# (slug, text, translation, kind, category, difficulty, context, description)
#
# slug 는 "이미 넣은 항목" 을 찾는 키다. text 를 키로 쓰면, 같은 문장을 다른
# 상황으로 하나 더 넣은 상태에서 --reset 이 MultipleObjectsReturned 로 터진다
# (모델이 그 중복을 일부러 허용한다).
#
# 한 번 정한 slug 는 바꾸지 않는다. 바꾸면 시드가 같은 문장을 새 항목으로
# 다시 넣어 중복이 생긴다. 문장 본문을 고치는 것은 자유다.
SENTENCES: list[tuple[str, str, str, str, str, int, str, str]] = [
    # ---------- 리뷰에서 자주 보는 표현 ----------
    (
        "review-rebase-request",
        "Could you rebase this onto main before merging?",
        "병합 전에 main 위로 리베이스해 주시겠어요?",
        PHRASE, GIT, N, "PR 리뷰 코멘트",
        "Could you...? 는 부탁처럼 보이지만 리뷰에서는 사실상 요청 사항이다. "
        "거절이 아니라 '하고 나서 다시 알려달라' 는 뜻으로 읽으면 된다.",
    ),
    (
        "review-lgtm-nits",
        "LGTM, but leaving a few nits.",
        "괜찮아 보여요. 다만 사소한 것 몇 개 남깁니다.",
        PHRASE, REVIEW, N, "승인하면서 남기는 코멘트",
        "LGTM 은 Looks Good To Me. nit 은 nitpick 의 준말로 고쳐도 되고 "
        "안 고쳐도 되는 사소한 지적이다. 대개 승인까지 함께 누른다는 뜻이라 "
        "고칠지 말지는 작성자가 정한다. 팀에 따라 다르니 승인 여부는 확인하자.",
    ),
    (
        "review-add-test",
        "Can you add a test that covers this edge case?",
        "이 예외 상황을 다루는 테스트를 추가해 주실 수 있나요?",
        PHRASE, REVIEW, E, "리뷰에서 테스트를 요청할 때",
        "cover 는 '테스트가 그 경우를 확인한다' 는 뜻이다. 코드 커버리지의 "
        "cover 와 같은 말.",
    ),
    (
        "review-out-of-scope",
        "This looks out of scope for this PR.",
        "이건 이 PR 범위를 벗어난 것 같습니다.",
        PHRASE, REVIEW, N, "관련 없는 변경이 섞였을 때",
        "고치지 말라는 게 아니라 '따로 PR 을 내라' 는 뜻이다. 한 PR 에 "
        "여러 목적이 섞이면 리뷰도 되돌리기도 어려워진다.",
    ),
    (
        "review-nice-catch",
        "Nice catch, I missed that.",
        "잘 찾으셨네요. 제가 놓쳤습니다.",
        PHRASE, REVIEW, E, "지적을 받아들일 때",
        "리뷰어가 문제를 발견했을 때 작성자가 인정하며 쓰는 표현. "
        "catch 는 '잡아냈다' 는 뜻.",
    ),
    (
        "review-feel-free-ignore",
        "Feel free to ignore, just a suggestion.",
        "무시하셔도 됩니다. 그냥 제안이에요.",
        PHRASE, REVIEW, N, "강제성 없는 의견을 낼 때",
        "리뷰 코멘트가 전부 반영 필수는 아니다. 이 문장이 붙으면 "
        "판단은 작성자에게 맡긴다는 뜻이다.",
    ),
    (
        "review-another-look",
        "I'll take another look after the changes.",
        "수정 후에 다시 보겠습니다.",
        PHRASE, REVIEW, E, "재리뷰를 약속할 때",
        "take a look 은 '살펴보다'. 리뷰가 아직 안 끝났다는 신호라, "
        "고치고 나서 리뷰어에게 알려주는 것이 좋다.",
    ),
    (
        "review-breaking-change",
        "This is a breaking change, so we need a migration plan.",
        "이건 기존 동작을 깨는 변경이라 마이그레이션 계획이 필요합니다.",
        PHRASE, OPS, H, "호환성을 깨는 변경을 논의할 때",
        "breaking change 는 쓰던 쪽 코드를 고쳐야 하는 변경이다. "
        "API 응답 형태를 바꾸거나 필드를 없애는 경우가 대표적이다.",
    ),
    # ---------- 이슈 / 배포 ----------
    (
        "issue-cannot-reproduce",
        "I cannot reproduce this on my machine.",
        "제 환경에서는 재현이 안 됩니다.",
        PHRASE, DEBUG, N, "버그 리포트에 답할 때",
        "reproduce 는 같은 문제를 다시 일으켜 보는 것. 재현이 안 되면 "
        "환경 차이(OS, 버전, 데이터)를 먼저 의심한다.",
    ),
    (
        "ops-revert-for-now",
        "Reverting for now until we figure out the root cause.",
        "근본 원인을 찾을 때까지 일단 되돌립니다.",
        PHRASE, OPS, N, "장애 대응 중",
        "for now 는 '일단은'. 고치는 것보다 되돌리는 게 빠를 때 "
        "서비스를 먼저 살리고 원인은 나중에 찾는다.",
    ),
    (
        "ops-blocked-on",
        "This is blocked on the API change landing first.",
        "API 변경이 먼저 들어가야 진행할 수 있습니다.",
        PHRASE, API, H, "작업 순서를 조율할 때",
        "blocked on 은 '무엇 때문에 막혀 있다'. land 는 변경이 실제로 "
        "머지되어 반영되는 것을 말한다.",
    ),
    (
        "ops-heads-up-deploy",
        "Heads up: deploying to production in 10 minutes.",
        "알려드립니다. 10분 뒤 운영 환경에 배포합니다.",
        PHRASE, OPS, E, "배포 전 공지",
        "Heads up 은 '미리 알려둔다'. 배포 직후 이상이 생기면 원인을 "
        "빨리 좁힐 수 있도록 팀에 공유하는 관행이다.",
    ),
    # ---------- 에러 메시지: git ----------
    (
        "git-unrelated-histories",
        "fatal: refusing to merge unrelated histories",
        "치명적 오류: 관련 없는 히스토리 병합을 거부합니다",
        ERROR, GIT, H, "따로 시작한 저장소를 합칠 때",
        "두 저장소가 공통 조상 커밋을 하나도 공유하지 않을 때 나온다. "
        "정말 합치려는 게 맞으면 --allow-unrelated-histories 를 붙인다. "
        "대개는 clone 대신 init 을 해버린 실수라 그것부터 확인한다.",
    ),
    (
        "git-failed-push",
        "error: failed to push some refs to 'origin'",
        "오류: 일부 참조를 origin 으로 푸시하지 못했습니다",
        ERROR, GIT, N, "push 가 거부될 때",
        "원격에 내가 아직 안 받은 커밋이 있다는 뜻이다. pull 로 받아 "
        "합친 뒤 다시 push 한다. force push 로 밀어버리면 남의 커밋이 사라진다.",
    ),
    (
        "git-commit-or-stash",
        "Please commit your changes or stash them before you switch branches.",
        "브랜치를 바꾸기 전에 변경사항을 커밋하거나 스태시하세요.",
        ERROR, GIT, E, "작업 중 브랜치를 옮기려 할 때",
        "저장 안 된 변경이 있으면 브랜치를 옮길 때 덮어써질 수 있어 "
        "git 이 먼저 막는다. 커밋하기 애매하면 stash 를 쓴다.",
    ),
    (
        "git-merge-conflict",
        "CONFLICT (content): Merge conflict in src/app.py",
        "충돌(내용): src/app.py 에서 병합 충돌이 발생했습니다",
        ERROR, GIT, N, "병합 중 같은 줄을 양쪽에서 고쳤을 때",
        "양쪽 변경 중 무엇을 남길지 git 이 판단할 수 없다는 뜻이다. "
        "파일을 열면 <<<<<<< 와 >>>>>>> 사이에 양쪽 내용이 들어 있다. "
        "직접 고르고 그 표시들을 지운 뒤 커밋한다.",
    ),
    (
        "git-detached-head",
        "detached HEAD state",
        "분리된 HEAD 상태",
        ERROR, GIT, H, "커밋 해시로 직접 체크아웃했을 때",
        "브랜치가 아니라 특정 커밋을 보고 있는 상태다. 여기서 커밋하면 "
        "어느 브랜치에도 안 붙어 나중에 찾기 어렵다. 작업할 거면 "
        "먼저 브랜치를 만든다.",
    ),
    # ---------- 에러 메시지: 파이썬 / DB ----------
    (
        "py-module-not-found",
        "ModuleNotFoundError: No module named 'requests'",
        "모듈을 찾을 수 없음: 'requests' 라는 모듈이 없습니다",
        ERROR, DEBUG, E, "임포트가 실패할 때",
        "설치가 안 됐거나, 설치는 됐는데 다른 가상환경에 들어 있다. "
        "pip install 전에 지금 활성화된 환경이 맞는지부터 확인한다.",
    ),
    (
        "py-nonetype-subscript",
        "TypeError: 'NoneType' object is not subscriptable",
        "타입 오류: None 객체는 인덱싱할 수 없습니다",
        ERROR, DEBUG, N, "None 에 [] 를 쓸 때",
        "값이 있을 줄 알았는데 None 이 왔다는 뜻이다. 대개 앞쪽에서 "
        "조회가 실패했거나 함수가 return 을 빠뜨렸다. 에러 난 줄이 아니라 "
        "그 값을 만든 곳을 봐야 한다.",
    ),
    (
        "db-unique-constraint",
        "IntegrityError: UNIQUE constraint failed: vocab_word.term",
        "무결성 오류: vocab_word.term 의 유니크 제약을 위반했습니다",
        ERROR, DB, N, "중복된 값을 저장하려 할 때",
        "이미 있는 값을 또 넣으려 했다는 뜻이다. DB 가 막아준 것이라 "
        "데이터는 안전하다. 저장 전에 존재 여부를 확인하거나 "
        "get_or_create 를 쓴다.",
    ),
    (
        "db-unapplied-migration",
        "You have 1 unapplied migration(s).",
        "적용되지 않은 마이그레이션이 1개 있습니다.",
        ERROR, DB, E, "서버 시작 시 경고",
        "모델은 바뀌었는데 DB 구조는 아직 그대로다. migrate 를 돌리면 "
        "된다. 이걸 무시하면 없는 컬럼을 찾다가 런타임에 터진다.",
    ),
    (
        "db-cannot-connect",
        "django.db.utils.OperationalError: could not connect to server",
        "DB 동작 오류: 서버에 연결할 수 없습니다",
        ERROR, DB, N, "DB 가 안 떠 있거나 주소가 틀렸을 때",
        "코드 문제가 아니라 연결 문제다. DB 가 실행 중인지, 포트와 "
        "호스트가 맞는지, 방화벽에 막히지 않았는지 순서대로 본다.",
    ),
    # ---------- 에러 메시지: 웹 / API ----------
    (
        "api-cors-missing-header",
        "CORS policy: No 'Access-Control-Allow-Origin' header is present",
        "CORS 정책: Access-Control-Allow-Origin 헤더가 없습니다",
        ERROR, API, H, "브라우저에서 다른 도메인 API 를 부를 때",
        "브라우저가 막은 것이라 서버 로그에는 정상으로 찍힌다. "
        "서버가 이 도메인을 허용하도록 설정해야 풀린다. "
        "프론트 코드를 아무리 고쳐도 해결되지 않는다.",
    ),
    (
        "api-401",
        "401 Unauthorized",
        "401 인증 안 됨",
        ERROR, API, E, "인증 없이 보호된 자원을 요청할 때",
        "'누구인지 모르겠다' 는 뜻이다. 로그인이 안 됐거나 토큰이 "
        "만료됐다. 누구인지는 알지만 권한이 없는 경우는 403 이다.",
    ),
    (
        "api-429",
        "429 Too Many Requests",
        "429 요청이 너무 많음",
        ERROR, API, N, "짧은 시간에 요청을 많이 보냈을 때",
        "속도 제한에 걸렸다는 뜻이다. Retry-After 헤더에 얼마나 "
        "기다리라는지 들어 있는 경우가 많다. 바로 재시도하면 더 오래 막힌다.",
    ),
    (
        "ops-502",
        "502 Bad Gateway",
        "502 게이트웨이 오류",
        ERROR, OPS, N, "앞단 서버가 뒷단 응답을 못 받았을 때",
        "nginx 같은 앞단은 살아 있는데 실제 앱이 죽었거나 아직 안 떴다는 "
        "신호다. 앱은 살아 있는데 응답이 너무 늦어 앞단이 끊는 경우도 있다. "
        "배포 직후에 잠깐 뜨는 건 흔하지만, 계속되면 앱 로그부터 본다.",
    ),
    (
        "ops-port-in-use",
        "Port 3000 is already in use",
        "3000번 포트가 이미 사용 중입니다",
        ERROR, OPS, E, "서버를 두 번 띄우려 할 때",
        "앞서 띄운 프로세스가 아직 살아 있다는 뜻이다. 그걸 끄거나 "
        "다른 포트로 띄운다. 터미널을 닫아도 프로세스는 남는 경우가 있다.",
    ),
]


class Command(BaseCommand):
    help = "초기 문장 데이터를 넣습니다."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="같은 문장이 이미 있으면 내용을 갱신합니다.",
        )
        parser.add_argument(
            "--force-pending",
            action="store_true",
            help=(
                "--reset 과 함께 씁니다. 검수 대기 중인 문장까지 덮어씁니다. "
                "기본값은 건너뛰기입니다."
            ),
        )

    # 시드는 전부-아니면-전무로 넣는다. 재실행 비용이 0 이라, 절반만 들어간
    # 상태로 남기느니 통째로 롤백하고 다시 돌리는 편이 낫다.
    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        reset: bool = options["reset"]
        force_pending: bool = options["force_pending"]

        if force_pending and not reset:
            raise CommandError("--force-pending 은 --reset 과 함께 써야 합니다.")

        created = updated = skipped = 0
        kept_pending: list[str] = []

        # 검수 대기 중인 문장을 한 번에 조회한다. 루프 안에서 항목마다 찾으면
        # 목록이 길어질수록 그대로 쿼리 수가 된다.
        pending_slugs: set[str] = set()
        if reset:
            pending_slugs = set(
                Sentence.objects.filter(
                    slug__in=[s[0] for s in SENTENCES], is_reviewed=False
                ).values_list("slug", flat=True)
            )

        for slug, text, translation, kind, category, difficulty, context, desc in SENTENCES:
            defaults = {
                "text": text,
                "translation": translation,
                "kind": kind,
                "category": category,
                "difficulty": difficulty,
                "context": context,
                "description": desc,
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
                # 검수 대기 중인 문장은 건드리지 않는다. 덮어쓰면 아무도
                # 승인하지 않은 항목이 is_reviewed=True 로 승격되어, 검수
                # 플래그가 "사람이 봤다" 는 의미를 잃는다.
                if slug in pending_slugs and not force_pending:
                    kept_pending.append(text)
                    skipped += 1
                    continue

                _, was_created = Sentence.objects.update_or_create(
                    slug=slug, defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            else:
                _, was_created = Sentence.objects.get_or_create(
                    slug=slug, defaults=defaults
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
                    f"검수 대기 중이라 건너뛴 문장 {len(kept_pending)}개:"
                )
            )
            for text in kept_pending:
                head = text if len(text) <= 60 else f"{text[:60]}..."
                self.stdout.write(f"  {head}")
            self.stdout.write(
                "Admin 에서 검수하거나, 시드 값으로 덮어쓰려면 "
                "--force-pending 을 쓰세요."
            )

        self.stdout.write(f"전체 문장: {Sentence.objects.count()}개")
