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
FRONT = Sentence.Category.FRONTEND
CS = Sentence.Category.CS

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
#
# slug 접두사와 category 는 다른 축이다. 접두사는 이 파일에서 어느 섹션에
# 있는지(java-, js-, front-)를 나타내고, category 는 학습자가 화면에서 고르는
# 문제 영역이다. 그래서 java-maven-compilation-error 가 devops 이고
# js-npm-eresolve-peer 도 devops 인 것이 정상이다 - 접두사를 category 에
# 맞추려고 slug 를 바꾸면 위 규칙을 어기게 된다.
#
# context 는 "어디서 보이는가"(예: Spring Boot 시작 로그)라 category 와
# 일치하지 않아도 된다. 같은 화면에 나와도 DB 설정 문제는 database 다.
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
        "error: failed to push some refs to 'https://github.com/acme/demo.git'",
        "오류: 일부 참조를 'https://github.com/acme/demo.git' 으로 푸시하지 못했습니다",
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
        "You are in 'detached HEAD' state.",
        "지금 '분리된 HEAD' 상태입니다.",
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
    # CORS 는 아래 확장분의 api-cors-blocked-policy / api-cors-preflight-failed /
    # front-cors-xhr-blocked 세 항목이 각각 다른 상황을 담고 있다.
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
        "Error: listen EADDRINUSE: address already in use :::3000",
        "오류: 3000번 포트를 열 수 없습니다. 이미 사용 중입니다",
        ERROR, OPS, E, "서버를 두 번 띄우려 할 때",
        "앞서 띄운 프로세스가 아직 살아 있다는 뜻이다. 그걸 끄거나 "
        "다른 포트로 띄운다. 터미널을 닫아도 프로세스는 남는 경우가 있다. "
        "EADDRINUSE 는 주소가 이미 쓰이고 있다는 운영체제의 응답이다.",
    ),

    # ---------- 아래는 2차 확장분 ----------
    # ---------- git 표현 ----------
    (
        "git-force-push-with-lease",
        "Please use --force-with-lease instead of --force.",
        "--force 말고 --force-with-lease 를 써 주세요.",
        PHRASE, GIT, H, "강제 푸시를 논의하는 리뷰 코멘트",
        "둘 다 원격을 덮어쓰지만 --force-with-lease 는 내가 마지막으로 본 뒤 원격이 "
        "바뀌었으면 거절한다. 남의 커밋을 지우는 사고를 막아주므로 사실상 강제 푸시의 "
        "기본값으로 쓰라는 요청이다.",
    ),
    (
        "git-dont-force-push-shared",
        "Heads up: don't force push to the shared branch.",
        "알려드립니다. 공유 브랜치에는 강제 푸시하지 마세요.",
        PHRASE, GIT, N, "팀 채널 공지",
        "Heads up 은 '미리 알려둔다' 는 뜻으로 경고보다는 부드럽지만 지켜달라는 "
        "말이다. 이미 사고가 났을 때가 아니라 사고를 막으려고 미리 던지는 표현이라 "
        "따로 사과할 필요는 없다.",
    ),
    (
        "git-cherry-pick-request",
        "Can you cherry-pick that commit onto the release branch?",
        "그 커밋을 릴리스 브랜치로 체리픽해 주실 수 있나요?",
        PHRASE, GIT, N, "핫픽스를 릴리스에 반영할 때",
        "브랜치 전체가 아니라 커밋 하나만 가져가달라는 요청이다. 원본을 옮기는 게 "
        "아니라 같은 변경으로 새 커밋을 만드는 것이라 해시가 달라진다.",
    ),
    (
        "git-squash-request",
        "Could you squash these into a single commit before merging?",
        "병합 전에 이것들을 커밋 하나로 합쳐 주실 수 있나요?",
        PHRASE, GIT, N, "PR 리뷰 코멘트",
        "fix typo 같은 커밋이 여러 개 쌓였을 때 나오는 말이다. 작업을 다시 하라는 "
        "뜻이 아니라 히스토리를 정리해달라는 요청이고, 대개 GitHub 의 Squash and "
        "merge 버튼으로도 해결된다.",
    ),
    (
        "git-needs-rebase-conflicts",
        "This needs a rebase, it has conflicts with main.",
        "이건 리베이스가 필요합니다. main 과 충돌이 있어요.",
        PHRASE, GIT, N, "PR 이 오래 열려 있을 때",
        "충돌을 리뷰어가 대신 풀어주지 않는다는 신호다. 작성자가 main 을 받아와 "
        "충돌을 해결하고 다시 올려야 리뷰가 이어진다.",
    ),
    (
        "git-split-into-commits",
        "Can you split this into smaller, self-contained commits?",
        "이걸 각각 독립적인 작은 커밋들로 나눠 주실 수 있나요?",
        PHRASE, GIT, H, "변경이 큰 PR 을 받았을 때",
        "self-contained 는 커밋 하나만 봐도 말이 되고 그 지점에서 빌드가 깨지지 "
        "않는다는 뜻이다. 파일 단위로 쪼개라는 게 아니라 의미 단위로 쪼개라는 말이다.",
    ),
    (
        "git-history-rewritten-reset",
        "I rewrote the history, so you'll need to reset your local branch.",
        "히스토리를 다시 썼으니 로컬 브랜치를 리셋해야 합니다.",
        PHRASE, GIT, H, "리베이스 후 팀에 공지할 때",
        "같은 브랜치를 보던 사람에게는 커밋 해시가 전부 달라졌다는 뜻이다. "
        "그냥 pull 하면 같은 변경이 두 벌로 합쳐지므로, 로컬을 원격에 맞춰 "
        "리셋하라는 안내다.",
    ),
    (
        "git-committed-to-main-by-mistake",
        "I accidentally committed straight to main, moving it to a branch now.",
        "실수로 main 에 바로 커밋했습니다. 지금 브랜치로 옮기고 있어요.",
        PHRASE, GIT, N, "실수를 알릴 때",
        "straight to 는 '거치지 않고 바로' 라는 뜻이다. 아직 푸시 전이면 브랜치를 "
        "만들어 옮기면 되고, 이미 푸시했다면 되돌리는 방식을 팀과 상의하는 편이 안전하다.",
    ),
    (
        "git-tag-and-cut-release",
        "Let's tag this as v2.1.0 and cut the release.",
        "이걸 v2.1.0 으로 태그하고 릴리스를 냅시다.",
        PHRASE, GIT, N, "릴리스 준비 대화",
        "cut a release 는 '릴리스를 만들어 낸다' 는 관용 표현이다. 자르는 것이 아니라 "
        "그 시점을 잘라 하나의 버전으로 확정한다는 어감이다.",
    ),
    (
        "git-bisect-suggestion",
        "Try bisecting between the last good tag and HEAD.",
        "마지막으로 정상이던 태그와 HEAD 사이를 이분 탐색해 보세요.",
        PHRASE, GIT, H, "언제부터 깨졌는지 모를 때",
        "언제부터 깨졌는지 모를 때 커밋 범위를 절반씩 줄여 원인 커밋을 찾으라는 "
        "제안이다. good 과 bad 지점만 알려주면 git 이 나머지를 좁혀준다.",
    ),
    (
        "git-open-against-develop",
        "Please open this against develop, not main.",
        "이건 main 이 아니라 develop 을 대상으로 열어주세요.",
        PHRASE, GIT, E, "PR 대상 브랜치가 잘못됐을 때",
        "open A against B 는 'B 를 대상으로 A 를 연다' 는 뜻이다. PR 을 닫고 다시 "
        "만들 필요 없이 base 브랜치만 바꾸면 되는 경우가 대부분이다.",
    ),
    (
        "git-stale-branch-cleanup",
        "These branches are stale, I'm going to prune them.",
        "이 브랜치들은 오래 방치돼서 정리하겠습니다.",
        PHRASE, GIT, N, "브랜치 정리 공지",
        "stale 은 '오래돼 쓸모없어진' 이라는 뜻이다. 병합된 브랜치를 지우는 것이라 "
        "커밋 자체가 사라지지는 않지만, 아직 작업 중인 브랜치가 있으면 미리 말해야 한다.",
    ),

    # ---------- git 에러 ----------
    (
        "git-not-a-repository",
        "fatal: not a git repository (or any of the parent directories): .git",
        "치명적 오류: git 저장소가 아닙니다(상위 디렉터리에도 없음): .git",
        ERROR, GIT, E, "git 명령을 아무 폴더에서 실행했을 때",
        "명령이 틀린 게 아니라 지금 위치가 저장소 안이 아니라는 뜻이다. "
        "상위 폴더까지 올라가며 .git 을 찾았는데 없었다는 말이라, "
        "cd 를 잘못했거나 clone 이 실패한 경우가 대부분이다.",
    ),
    (
        "git-pathspec-did-not-match",
        "error: pathspec 'develop' did not match any file(s) known to git",
        "오류: 'develop' 이 git 이 아는 어떤 파일과도 일치하지 않습니다",
        ERROR, GIT, N, "존재하지 않는 브랜치로 checkout 할 때",
        "브랜치를 찾다 실패했는데 파일 얘기가 나오는 이유는, checkout 이 브랜치 이동과 "
        "파일 복원을 겸하기 때문이다. 원격에만 있는 브랜치라면 먼저 fetch 하거나 "
        "-b 로 새로 만들어야 한다.",
    ),
    (
        "git-src-refspec-no-match",
        "error: src refspec main does not match any",
        "오류: src refspec main 이 아무것도 가리키지 않습니다",
        ERROR, GIT, H, "커밋 없이 push 했거나 브랜치 이름이 다를 때",
        "보내려는 브랜치가 로컬에 없다는 뜻이다. 커밋을 한 번도 안 했거나 "
        "기본 브랜치가 master 인데 main 으로 밀고 있는 경우가 대부분이다. "
        "git branch 로 실제 이름을 먼저 확인한다.",
    ),
    (
        "git-nothing-to-commit",
        "nothing to commit, working tree clean",
        "커밋할 것이 없습니다. 작업 폴더가 깨끗합니다",
        ERROR, GIT, E, "git status 나 commit 을 실행했을 때",
        "에러가 아니라 바뀐 것이 없다는 안내다. 분명히 고쳤는데 이게 나온다면 "
        "다른 폴더를 보고 있거나, 그 파일이 .gitignore 로 제외돼 있을 가능성이 높다.",
    ),
    (
        "git-ambiguous-argument",
        "fatal: ambiguous argument 'HEAD~5': unknown revision or path not in the working tree.",
        "치명적 오류: 모호한 인자 'HEAD~5': 알 수 없는 리비전이거나 작업 트리에 없는 경로입니다",
        ERROR, GIT, N, "존재하지 않는 커밋이나 브랜치를 지정했을 때",
        "이 이름이 커밋인지 파일 경로인지 판단할 수 없다는 뜻이다. 커밋이 5개보다 "
        "적거나 오타인 경우가 많다. 파일 이름이 확실하면 -- 를 앞에 붙여 경로임을 "
        "알려주면 된다.",
    ),
    (
        "git-branch-already-exists",
        "fatal: a branch named 'feature/login' already exists",
        "치명적 오류: 'feature/login' 이라는 브랜치가 이미 있습니다",
        ERROR, GIT, E, "같은 이름으로 브랜치를 또 만들 때",
        "그 브랜치로 옮기고 싶었다면 -b 를 빼고 checkout 이나 switch 만 하면 된다. "
        "옛 것을 버리고 새로 만들려면 먼저 지워야 하는데, 아직 병합 안 된 커밋이 "
        "있으면 git 이 한 번 더 막아준다.",
    ),
    (
        "git-no-push-destination",
        "fatal: No configured push destination.",
        "치명적 오류: 설정된 푸시 대상이 없습니다",
        ERROR, GIT, N, "원격을 등록하지 않고 push 할 때",
        "어디로 보낼지 모르겠다는 뜻이다. init 으로 시작해 아직 원격을 연결하지 "
        "않았을 때 나온다. git remote add origin <주소> 로 대상을 먼저 등록한다.",
    ),
    (
        "git-untracked-would-be-overwritten",
        "error: The following untracked working tree files would be overwritten by checkout:",
        "오류: 다음 추적되지 않는 작업 트리 파일들이 checkout 으로 덮어써집니다:",
        ERROR, GIT, H, "브랜치를 옮기려는데 같은 이름의 새 파일이 있을 때",
        "옮겨갈 브랜치에 같은 이름의 파일이 있는데 지금 폴더의 그 파일은 git 이 "
        "모르는 상태라, 덮어쓰면 복구할 수 없어 멈춘 것이다. 그 파일을 옮기거나 "
        "지우면 진행된다. 기본 stash 는 추적되지 않는 파일을 담지 않아 소용없고, "
        "-u 를 붙이면 함께 치워져 해결된다.",
    ),
    (
        "git-push-rejected-fetch-first",
        "! [rejected]        main -> main (fetch first)",
        "! [거부됨]        main -> main (먼저 fetch 하세요)",
        ERROR, GIT, N, "원격이 앞서 있는데 push 할 때",
        "내가 마지막으로 받아온 뒤 다른 사람이 먼저 푸시했다는 뜻이다. "
        "강제로 밀면 그 사람 커밋이 사라지므로, pull 로 받아 합친 뒤 다시 푸시하는 것이 "
        "정답이다.",
    ),
    (
        "git-cannot-pull-with-rebase",
        "error: cannot pull with rebase: You have unstaged changes.",
        "오류: 리베이스로 pull 할 수 없습니다: 스테이징되지 않은 변경이 있습니다",
        ERROR, GIT, N, "고치던 파일이 남은 채 pull 할 때",
        "리베이스는 작업 폴더가 깨끗해야 시작할 수 있다. 커밋하거나 stash 로 "
        "잠시 치워두면 진행된다. 뒤이어 나오는 Please commit or stash them 이 "
        "그 안내다.",
    ),
    (
        "git-automatic-merge-failed",
        "Automatic merge failed; fix conflicts and then commit the result.",
        "자동 병합에 실패했습니다. 충돌을 해결한 뒤 결과를 커밋하세요",
        ERROR, GIT, N, "merge 중 충돌이 났을 때",
        "실패했다는 말에 놀랄 필요는 없다. git 이 자동으로 못 고른 부분만 남겨두고 "
        "멈춘 정상 상태다. 표시를 정리하고 add 한 뒤 커밋하면 병합이 완료된다.",
    ),
    (
        "git-could-not-apply",
        "error: could not apply 9031681... add retry logic",
        "오류: 9031681... add retry logic 을 적용할 수 없습니다",
        ERROR, GIT, H, "리베이스나 체리픽 중 충돌이 났을 때",
        "그 커밋을 새 기준 위에 얹으려다 충돌이 나 멈췄다는 뜻이다. 해결하고 add 한 뒤 "
        "--continue 로 이어가거나, --abort 로 리베이스 전 상태로 되돌린다. "
        "커밋이 사라진 것이 아니다.",
    ),
    (
        "git-local-changes-overwritten",
        "error: Your local changes to the following files would be overwritten by checkout:",
        "오류: 다음 파일들의 로컬 변경이 checkout 으로 덮어써집니다:",
        ERROR, GIT, N, "고치던 파일이 남은 채 브랜치를 옮길 때",
        "앞의 untracked 버전과 달리 이건 git 이 이미 추적 중인 파일이다. "
        "그래서 커밋하거나 stash 하면 바로 해결된다. 실제로 뒤에 그렇게 하라는 "
        "안내가 함께 나온다.",
    ),
    (
        "git-destination-path-exists",
        "fatal: destination path 'myrepo' already exists and is not an empty directory.",
        "치명적 오류: 대상 경로 'myrepo' 가 이미 있고 빈 디렉터리가 아닙니다",
        ERROR, GIT, E, "같은 이름의 폴더가 있는데 clone 할 때",
        "clone 은 빈 폴더에만 받을 수 있다. 이미 받아둔 것이라면 그 안에서 pull 하면 "
        "되고, 정말 새로 받으려면 폴더를 지우거나 clone 뒤에 다른 폴더 이름을 붙인다.",
    ),
    (
        "git-branch-ahead-by-n",
        "Your branch is ahead of 'origin/main' by 3 commits.",
        "브랜치가 'origin/main' 보다 커밋 3개 앞서 있습니다",
        ERROR, GIT, E, "커밋은 했지만 아직 push 하지 않았을 때",
        "에러가 아니라 아직 푸시하지 않은 커밋이 3개 있다는 안내다. 이 상태에서는 "
        "다른 사람이 그 작업을 전혀 볼 수 없다. 반대로 behind 라고 나오면 "
        "받아오지 않은 커밋이 있다는 뜻이다.",
    ),
    (
        "git-no-commits-yet",
        "fatal: your current branch 'main' does not have any commits yet",
        "치명적 오류: 현재 브랜치 'main' 에 아직 커밋이 없습니다",
        ERROR, GIT, E, "커밋 없이 log 를 볼 때",
        "저장소는 만들어졌지만 커밋이 하나도 없다는 뜻이다. init 직후에 흔하다. "
        "파일을 추가하고 첫 커밋을 만들면 사라진다.",
    ),
    (
        "git-lf-will-be-replaced",
        "warning: in the working copy of 'README.md', LF will be replaced by CRLF the next time Git touches it",
        "경고: 'README.md' 작업 사본에서 Git 이 다음에 건드릴 때 LF 가 CRLF 로 바뀝니다",
        ERROR, GIT, H, "윈도우에서 파일을 add 할 때",
        "줄바꿈 문자를 윈도우식으로 바꾸겠다는 안내다. 저장소에는 LF 로 저장되므로 "
        "동작에는 문제가 없다. 다만 팀원마다 설정이 다르면 파일 전체가 바뀐 것처럼 "
        "보이는 diff 가 생기므로 .gitattributes 로 통일하는 것이 좋다.",
    ),
    (
        "git-does-not-appear-repository",
        "fatal: 'upstream' does not appear to be a git repository",
        "치명적 오류: 'upstream' 은 git 저장소가 아닌 것 같습니다",
        ERROR, GIT, N, "등록하지 않은 원격 이름을 쓸 때",
        "그 이름의 원격이 등록돼 있지 않아 주소로 해석하려다 실패한 것이다. "
        "git remote -v 로 실제 등록된 이름을 확인한다. 포크에서 작업할 때 "
        "upstream 을 안 걸어두고 쓰는 경우가 흔하다.",
    ),
    (
        "git-could-not-read-remote",
        "fatal: Could not read from remote repository.",
        "치명적 오류: 원격 저장소에서 읽을 수 없습니다",
        ERROR, GIT, N, "clone 이나 fetch 가 접속 단계에서 실패할 때",
        "주소가 틀렸거나 접근 권한이 없다는 뜻이다. 이 줄만 보면 원인을 알 수 없고 "
        "바로 위에 진짜 이유가 찍혀 있으므로 그쪽을 봐야 한다. "
        "비공개 저장소에 키 없이 접속할 때 가장 흔하다.",
    ),
    (
        "git-already-up-to-date",
        "Already up to date.",
        "이미 최신 상태입니다",
        ERROR, GIT, E, "pull 이나 merge 를 실행했을 때",
        "받아올 것이 없다는 정상 안내다. 원격에 새 커밋이 분명히 있는데 이게 나온다면 "
        "다른 브랜치를 보고 있거나 원격이 다른 곳을 가리키고 있을 가능성이 크다.",
    ),
    (
        "git-everything-up-to-date",
        "Everything up-to-date",
        "모두 최신 상태입니다",
        ERROR, GIT, E, "push 했는데 보낼 커밋이 없을 때",
        "보낼 커밋이 없다는 뜻이다. 커밋을 만들었다고 생각했는데 이게 나오면 "
        "add 만 하고 commit 을 안 했거나, 다른 브랜치에 커밋한 경우다. "
        "위의 Already up to date 와 달리 마침표가 없다.",
    ),
    (
        "git-please-tell-me-who-you-are",
        "*** Please tell me who you are.",
        "*** 당신이 누구인지 알려주세요",
        ERROR, GIT, E, "user.name 과 user.email 없이 커밋할 때",
        "커밋에 작성자를 기록해야 하는데 설정이 없다는 뜻이다. 뒤이어 실행할 "
        "git config 명령을 그대로 알려준다. 새 컴퓨터나 새 컨테이너에서 "
        "처음 커밋할 때 거의 반드시 만난다.",
    ),
    (
        "git-merging-not-possible-unmerged",
        "error: Merging is not possible because you have unmerged files.",
        "오류: 해결되지 않은 파일이 있어 병합할 수 없습니다",
        ERROR, GIT, N, "충돌을 남겨둔 채 다른 명령을 실행할 때",
        "앞선 병합의 충돌이 아직 정리되지 않았다는 뜻이다. 충돌을 해결하고 add 로 "
        "해결됐다고 표시하거나, git merge --abort 로 병합 전으로 되돌려야 다음 작업이 된다.",
    ),
    (
        "git-committing-not-possible-unmerged",
        "error: Committing is not possible because you have unmerged files.",
        "오류: 해결되지 않은 파일이 있어 커밋할 수 없습니다",
        ERROR, GIT, N, "충돌 표시를 지우지 않고 커밋할 때",
        "충돌 난 파일을 고쳤더라도 add 로 해결됐다고 표시하지 않으면 이 상태가 유지된다. "
        "파일을 저장한 것만으로는 git 이 해결 여부를 알 수 없기 때문이다.",
    ),
    (
        "git-exiting-unresolved-conflict",
        "fatal: Exiting because of an unresolved conflict.",
        "치명적 오류: 해결되지 않은 충돌 때문에 종료합니다",
        ERROR, GIT, N, "충돌이 남은 상태에서 커밋을 시도했을 때",
        "위의 unmerged files 안내에 이어 마지막에 붙는 줄이다. 이 줄만 보고 원인을 "
        "찾으려 하기 쉬운데, 실제 정보는 그 위에 나열된 파일 목록에 있다.",
    ),
    (
        "git-partial-commit-during-merge",
        "fatal: cannot do a partial commit during a merge.",
        "치명적 오류: 병합 중에는 일부만 커밋할 수 없습니다",
        ERROR, GIT, H, "병합 중 특정 파일만 지정해 커밋할 때",
        "병합 커밋은 그 시점의 상태 전체를 담아야 해서 일부 파일만 골라 커밋할 수 없다. "
        "파일 이름을 빼고 git commit 만 실행하면 된다.",
    ),
    (
        "git-could-not-read-username",
        "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
        "치명적 오류: 'https://github.com' 의 사용자 이름을 읽을 수 없습니다: 터미널 입력이 비활성화됨",
        ERROR, GIT, H, "CI 나 스크립트에서 비공개 저장소에 접근할 때",
        "인증 정보를 물어보려 했는데 입력받을 터미널이 없다는 뜻이다. 사람이 없는 "
        "환경에서 대화형 입력을 기대해 생기는 문제라, 토큰이나 배포 키를 미리 "
        "설정해두는 것이 해법이다.",
    ),

    # ---------- 리뷰 / 협업 표현 ----------
    (
        "review-consider-extracting",
        "Consider extracting this into a helper.",
        "이걸 헬퍼 함수로 빼는 걸 고려해 보세요.",
        PHRASE, REVIEW, N, "긴 함수를 지적할 때",
        "Consider 로 시작하면 강제가 아니라 제안이다. 다만 리뷰어가 같은 제안을 "
        "두 번 하면 사실상 요청으로 바뀌므로, 안 고칠 거라면 이유를 한 줄 남기는 것이 좋다.",
    ),
    (
        "review-ship-behind-flag",
        "Can we ship this behind a feature flag?",
        "이걸 피처 플래그 뒤에 두고 배포할 수 있을까요?",
        PHRASE, REVIEW, H, "위험한 변경을 논의할 때",
        "배포는 하되 기능은 꺼둔 채로 내보내자는 제안이다. 반대가 아니라 "
        "되돌리기 쉽게 만들자는 뜻이라, 거절로 읽지 않아도 된다.",
    ),
    (
        "review-not-blocking",
        "Not blocking, but I'd prefer the other approach.",
        "막을 정도는 아니지만 저는 다른 방식이 더 좋습니다.",
        PHRASE, REVIEW, H, "의견은 있지만 승인하는 코멘트",
        "Not blocking 은 이것 때문에 병합을 막지는 않겠다는 명시적 표시다. "
        "리뷰어가 자기 의견의 무게를 스스로 낮춰 알려주는 것이라, "
        "판단은 작성자에게 넘어간다.",
    ),
    (
        "review-blocking-comment",
        "This one is blocking for me.",
        "이건 제 기준에서 반드시 고쳐야 합니다.",
        PHRASE, REVIEW, N, "반드시 수정이 필요한 지적",
        "위의 Not blocking 과 정반대다. 취향이 아니라 고치지 않으면 승인하지 않겠다는 "
        "뜻이므로, 동의하지 않으면 그냥 넘기지 말고 근거를 들어 논의해야 한다.",
    ),
    (
        "review-can-you-elaborate",
        "Can you elaborate on why you chose this approach?",
        "왜 이 방식을 고르셨는지 좀 더 설명해 주실 수 있나요?",
        PHRASE, REVIEW, N, "설계 의도를 물을 때",
        "elaborate 는 '자세히 풀어 말하다' 라는 뜻이다. 비난이 아니라 정말 배경을 "
        "모르는 경우가 많다. 코드를 고치기보다 PR 설명에 이유를 적어주는 것이 "
        "대개 더 나은 답이다.",
    ),
    (
        "review-i-might-be-missing",
        "I might be missing something, but wouldn't this loop run twice?",
        "제가 뭘 놓쳤을 수도 있는데, 이 반복문이 두 번 도는 것 아닌가요?",
        PHRASE, REVIEW, H, "버그를 조심스럽게 지적할 때",
        "영어권 리뷰에서 지적을 부드럽게 만드는 전형적인 완충 표현이다. "
        "정말 자신 없어서 하는 말이 아니라 상대 체면을 세워주는 관용구에 가까우므로, "
        "내용은 진지하게 받아들이는 편이 맞다.",
    ),
    (
        "review-lets-take-this-offline",
        "Let's take this offline.",
        "이건 따로 이야기합시다.",
        PHRASE, REVIEW, H, "논의가 길어질 때",
        "인터넷을 끊자는 말이 아니라 이 스레드 말고 다른 자리에서 얘기하자는 뜻이다. "
        "회의나 통화로 옮기자는 제안이고, 논의를 덮자는 뜻은 아니다.",
    ),
    (
        "review-circling-back",
        "Just circling back on this.",
        "이 건 다시 확인차 여쭙습니다.",
        PHRASE, REVIEW, N, "답이 없는 스레드를 다시 올릴 때",
        "재촉하는 말을 부드럽게 하는 표현이다. 며칠 지난 요청을 다시 꺼낼 때 쓰고, "
        "받는 쪽에서는 사실상 '아직 기다리고 있다' 는 뜻으로 읽으면 된다.",
    ),
    (
        "review-any-updates",
        "Any updates on this?",
        "이 건 진행 상황이 있나요?",
        PHRASE, REVIEW, E, "멈춘 작업을 확인할 때",
        "짧지만 재촉의 뉘앙스가 있다. 아직 못 했다면 언제쯤 하겠다고 답하는 것이 "
        "무응답보다 훨씬 낫다. 대답 없이 두면 다음 메시지는 더 직접적으로 온다.",
    ),
    (
        "review-gentle-ping",
        "Gentle ping on this PR.",
        "이 PR 관련해서 가볍게 한 번 더 알려드립니다.",
        PHRASE, REVIEW, N, "리뷰를 재촉할 때",
        "ping 은 상대를 한 번 건드려 알린다는 뜻이다. gentle 을 붙여 재촉의 강도를 "
        "낮춘 것이라 무례한 표현이 아니다. 반대로 이게 두세 번 반복되면 급하다는 신호다.",
    ),
    (
        "review-no-rush",
        "No rush, whenever you get a chance.",
        "급하지 않으니 시간 되실 때 봐주세요.",
        PHRASE, REVIEW, E, "부탁하면서 부담을 덜어줄 때",
        "정말 급하지 않다는 뜻으로 받아들여도 되지만, 며칠씩 방치해도 된다는 뜻은 "
        "아니다. 언제까지 필요한지 궁금하면 그냥 물어보는 편이 낫다.",
    ),
    (
        "review-nit-naming",
        "Nit: could we rename this to something more descriptive?",
        "사소한 의견인데, 좀 더 설명적인 이름으로 바꿀 수 있을까요?",
        PHRASE, REVIEW, E, "변수명을 지적할 때",
        "Nit 이 앞에 붙으면 안 고쳐도 승인은 한다는 뜻이다. descriptive 는 "
        "'무엇인지 설명해주는' 이라는 뜻으로, data 나 temp 같은 이름을 지적할 때 쓴다.",
    ),
    (
        "review-happy-to-pair",
        "Happy to pair on this if it helps.",
        "도움이 된다면 같이 봐드릴 수 있습니다.",
        PHRASE, REVIEW, N, "막힌 사람을 돕겠다고 할 때",
        "Happy to 는 '기꺼이 하겠다' 는 뜻이다. 형식적인 인사가 아니라 실제 제안이므로, "
        "필요하면 시간을 잡자고 답하는 것이 자연스럽다.",
    ),
    (
        "review-do-we-need-this",
        "Do we actually need this right now?",
        "이게 지금 정말 필요한가요?",
        PHRASE, REVIEW, H, "과한 구현을 지적할 때",
        "질문 형태지만 사실상 '지금은 빼자' 는 제안이다. 나중에 필요할 것 같아 미리 "
        "만든 부분을 지적할 때 쓰고, 뒤에 YAGNI 라는 말이 따라오기도 한다.",
    ),
    (
        "review-what-happens-if",
        "What happens if the list is empty here?",
        "여기서 목록이 비어 있으면 어떻게 되나요?",
        PHRASE, REVIEW, N, "예외 상황을 물을 때",
        "리뷰어가 이미 문제를 발견했지만 작성자가 직접 확인하도록 질문으로 던지는 "
        "전형적인 방식이다. 답만 적기보다 그 경우를 다루는 테스트를 추가하면 "
        "논의가 한 번에 끝난다.",
    ),
    (
        "review-is-this-covered",
        "Is this path covered by a test?",
        "이 경로는 테스트로 확인되나요?",
        PHRASE, REVIEW, E, "테스트 여부를 확인할 때",
        "covered 는 테스트가 그 코드 경로를 실제로 실행한다는 뜻이다. 실행만 되고 "
        "아무것도 검증하지 않는 테스트는 여기 해당하지 않는다.",
    ),
    (
        "review-lgtm-with-minor",
        "LGTM with minor comments.",
        "괜찮아 보입니다. 사소한 코멘트 몇 개 있습니다.",
        PHRASE, REVIEW, E, "승인하면서 남기는 요약",
        "승인은 이미 눌렀고 남은 것은 참고 사항이라는 뜻이다. 고치고 다시 리뷰를 "
        "요청할 필요 없이 반영 여부만 정하면 된다.",
    ),
    (
        "review-stamp",
        "Stamping this so you're not blocked.",
        "막히지 않으시게 승인 눌러둡니다.",
        PHRASE, REVIEW, H, "급한 PR 을 승인할 때",
        "stamp 는 도장을 찍듯 형식적으로 승인한다는 뜻이다. 깊이 보지 않았다는 "
        "솔직한 표시이기도 해서, 중요한 변경이라면 다른 리뷰어를 한 명 더 "
        "붙이는 것이 안전하다.",
    ),
    (
        "review-defer-to-you",
        "I'll defer to you on this one.",
        "이 건은 판단을 맡기겠습니다.",
        PHRASE, REVIEW, H, "의견 차이를 정리할 때",
        "defer to 는 '상대의 판단을 따르겠다' 는 뜻이다. 설득당했다는 뜻일 수도 있고 "
        "그 영역의 담당자를 존중한다는 뜻일 수도 있는데, 어느 쪽이든 논의를 "
        "여기서 끝내자는 신호다.",
    ),
    (
        "review-strong-opinions-loosely-held",
        "Strong opinions, loosely held.",
        "의견은 분명하지만 고집하지는 않습니다.",
        PHRASE, REVIEW, H, "의견을 내면서 여지를 둘 때",
        "이렇게 생각하지만 더 나은 근거가 있으면 바로 바꾸겠다는 뜻이다. "
        "토론을 열어두려는 표현이라, 반박해도 무례가 되지 않는다.",
    ),
    (
        "review-out-of-band",
        "Let's handle that out of band.",
        "그건 이 흐름 밖에서 따로 처리합시다.",
        PHRASE, REVIEW, H, "본 논의에서 벗어난 항목을 미룰 때",
        "out of band 는 원래 통신 용어로 본 채널이 아닌 다른 경로를 뜻한다. "
        "지금 이 PR 이나 회의의 흐름과 분리해서 처리하자는 말이다.",
    ),
    (
        "review-good-first-issue",
        "This would be a good first issue for someone new.",
        "이건 새로 오신 분이 처음 맡기 좋은 이슈입니다.",
        PHRASE, REVIEW, E, "온보딩용 작업을 고를 때",
        "오픈소스에서는 라벨 이름이기도 하다. 쉬운 일이라는 뜻보다 코드베이스를 "
        "익히기 좋은 범위라는 뜻에 가깝다.",
    ),
    (
        "review-onboarding-doc-stale",
        "The setup steps are stale, feel free to update them as you go.",
        "설치 절차가 낡았습니다. 진행하면서 자유롭게 갱신해 주세요.",
        PHRASE, REVIEW, N, "온보딩 중 문서 문제를 만났을 때",
        "as you go 는 '따로 시간 내지 말고 하는 김에' 라는 뜻이다. 새로 온 사람만 "
        "무엇이 안 적혀 있는지 알아볼 수 있어서 많은 팀이 이걸 첫 작업으로 준다.",
    ),
    (
        "review-ramp-up",
        "Take your first week to ramp up, no deliverables expected.",
        "첫 주는 적응하는 데 쓰세요. 산출물은 기대하지 않습니다.",
        PHRASE, REVIEW, N, "새 팀원에게 하는 안내",
        "ramp up 은 속도를 올리기 전에 익히는 기간을 뜻한다. 예의상 하는 말이 아니라 "
        "실제 기대치를 낮춰주는 안내이므로 그대로 받아들여도 된다.",
    ),
    (
        "review-bandwidth",
        "I don't have the bandwidth for this sprint.",
        "이번 스프린트에는 여력이 없습니다.",
        PHRASE, REVIEW, N, "일을 더 받기 어려울 때",
        "bandwidth 는 네트워크 용어를 빌려 쓴 것으로 처리할 여력을 뜻한다. "
        "능력이 아니라 시간이 없다는 뜻이라, 거절할 때 흔히 쓰는 완곡한 표현이다.",
    ),
    (
        "review-punt-to-next-sprint",
        "Let's punt this to the next sprint.",
        "이건 다음 스프린트로 미룹시다.",
        PHRASE, REVIEW, H, "우선순위를 조정할 때",
        "punt 는 미식축구에서 공을 차 넘기는 것에서 온 말로 '일단 미룬다' 는 뜻이다. "
        "취소가 아니라 연기이지만, 미룬 것을 티켓으로 남기지 않으면 그대로 잊힌다.",
    ),
    (
        "review-scope-down",
        "Can we scope this down to just the API change?",
        "이걸 API 변경만으로 범위를 줄일 수 있을까요?",
        PHRASE, REVIEW, N, "작업이 너무 커졌을 때",
        "scope down 은 범위를 좁힌다는 뜻이다. 하지 말자는 게 아니라 일단 낼 수 있는 "
        "크기로 자르자는 제안이라, 나머지는 후속 작업으로 남기는 것이 보통이다.",
    ),
    (
        "review-two-approvals",
        "This needs two approvals before it can be merged.",
        "병합하려면 승인 두 개가 필요합니다.",
        PHRASE, REVIEW, E, "병합 규칙을 안내할 때",
        "저장소 설정으로 강제된 규칙이라 사람이 봐준다고 풀리지 않는다. "
        "리뷰어가 한 명뿐이면 다른 사람을 직접 지정해 요청해야 진행된다.",
    ),
    (
        "review-self-merge",
        "Please don't self-merge without a review.",
        "리뷰 없이 본인이 직접 병합하지 마세요.",
        PHRASE, REVIEW, N, "병합 규칙을 상기시킬 때",
        "self-merge 는 자기 PR 을 스스로 병합하는 것이다. 기록이 안 남아서가 아니라 "
        "아무도 그 코드를 보지 않은 채 들어가기 때문에 막는 것이다. "
        "급할 때는 승인 한 개라도 받고 병합하는 편이 낫다.",
    ),
    (
        "review-revert-first-debug-later",
        "Let's revert first and debug afterwards.",
        "일단 되돌리고 원인은 나중에 봅시다.",
        PHRASE, REVIEW, N, "운영 장애 대응 중",
        "장애 대응의 기본 순서를 말한 것이다. 원인을 찾는 동안 사용자가 계속 "
        "피해를 보기 때문에, 먼저 멈추고 나중에 분석하는 것이 원칙이다.",
    ),
    (
        "review-retro-action-item",
        "Let's turn that into an action item for the retro.",
        "그건 회고 액션 아이템으로 만듭시다.",
        PHRASE, REVIEW, N, "회고에서 논의를 정리할 때",
        "action item 은 담당자와 기한이 붙은 할 일이다. 담당자를 정하지 않은 채 "
        "끝나면 아무도 하지 않는다는 것이 회고에서 반복되는 교훈이다.",
    ),
    (
        "review-blameless",
        "This is a blameless postmortem, so let's focus on the system.",
        "이건 책임을 묻지 않는 회고이니 시스템에 집중합시다.",
        PHRASE, REVIEW, H, "장애 회고를 시작할 때",
        "누가 실수했는지가 아니라 어떤 구조가 그 실수를 가능하게 했는지를 보자는 "
        "원칙이다. 탓하기 시작하면 사람들이 사실을 숨겨 원인 파악 자체가 "
        "불가능해지기 때문에 나온 실용적인 규칙이다.",
    ),
    (
        "review-i-own-that",
        "That one's on me, I'll fix it.",
        "그건 제 잘못입니다. 제가 고치겠습니다.",
        PHRASE, REVIEW, N, "실수를 인정할 때",
        "on me 는 '내 책임이다' 라는 뜻이다. 자책하는 표현이 아니라 담당을 분명히 "
        "하는 말이라, 영어권 팀에서는 오히려 신뢰를 얻는 표현으로 통한다.",
    ),
    (
        "review-wontfix",
        "Closing this as wontfix.",
        "고치지 않기로 하고 닫겠습니다.",
        PHRASE, REVIEW, N, "이슈를 닫을 때",
        "wontfix 는 버그가 아니라는 뜻이 아니라 알고 있지만 고치지 않기로 했다는 "
        "뜻이다. 이유를 적어두지 않으면 같은 이슈가 몇 달 뒤 다시 올라온다.",
    ),
    (
        "review-needs-more-context",
        "Could you add some context to the PR description?",
        "PR 설명에 배경을 좀 더 적어주실 수 있나요?",
        PHRASE, REVIEW, E, "PR 설명이 비어 있을 때",
        "무엇을 바꿨는지는 diff 로 알 수 있으니 왜 바꿨는지를 적어달라는 뜻이다. "
        "리뷰 속도에 가장 크게 영향을 주는 부분이기도 하다.",
    ),
    (
        "review-rubber-stamp-warning",
        "I'd rather not rubber-stamp a change this large.",
        "이만큼 큰 변경을 그냥 통과시키고 싶지는 않습니다.",
        PHRASE, REVIEW, H, "큰 PR 을 받았을 때",
        "rubber-stamp 는 내용을 보지 않고 도장만 찍는다는 뜻이다. 거절이 아니라 "
        "제대로 보려면 시간이 걸리거나 PR 을 나눠달라는 요청이다.",
    ),
    (
        "review-following-up-async",
        "I'll follow up async so we don't block the standup.",
        "스탠드업을 지연시키지 않게 따로 이어서 얘기하겠습니다.",
        PHRASE, REVIEW, H, "회의가 길어질 때",
        "async 는 '실시간으로 모이지 않고' 라는 뜻으로, 슬랙이나 문서로 이어가겠다는 "
        "말이다. 논의를 미루는 것이 아니라 모두의 시간을 아끼려는 조치다.",
    ),
    (
        "review-happy-path-only",
        "This only covers the happy path.",
        "이건 정상 흐름만 다루고 있습니다.",
        PHRASE, REVIEW, N, "예외 처리가 없을 때",
        "happy path 는 모든 것이 잘 풀릴 때의 흐름이다. 실패했을 때, 비어 있을 때, "
        "시간이 초과됐을 때를 다루지 않았다는 지적이다.",
    ),

    # ---------- API / 네트워크 표현 ----------
    (
        "api-lock-down-contract",
        "Can we lock down the response schema before you start?",
        "시작하기 전에 응답 스키마를 확정할 수 있을까요?",
        PHRASE, API, N, "프론트와 백엔드가 스펙을 맞출 때",
        "lock down 은 '더 이상 바뀌지 않게 확정한다' 는 뜻이다. 양쪽이 동시에 "
        "작업하려면 형태부터 고정해야 해서 나오는 요청이고, 이후 변경은 "
        "합의를 거치자는 의미도 포함한다.",
    ),
    (
        "api-deprecate-with-sunset",
        "We'll deprecate v1 and sunset it at the end of the quarter.",
        "v1 을 폐기 예정으로 두고 분기 말에 종료하겠습니다.",
        PHRASE, API, H, "API 버전 종료를 공지할 때",
        "deprecate 는 '아직 되지만 쓰지 말라' 는 표시이고, sunset 은 실제로 끄는 것이다. "
        "이 둘을 한 문장에 쓰는 이유는 지금 당장 끄는 게 아니라는 점을 분명히 하기 위해서다.",
    ),
    (
        "api-backwards-compatible-add",
        "Adding a field is backwards compatible, removing one is not.",
        "필드를 추가하는 건 하위 호환이지만 제거하는 건 아닙니다.",
        PHRASE, API, N, "API 변경 범위를 논의할 때",
        "쓰는 쪽이 모르는 필드를 무시한다는 전제 위의 이야기다. 없는 필드를 오류로 "
        "처리하는 엄격한 클라이언트가 있으면 추가도 깨질 수 있으니 그 전제를 확인해야 한다.",
    ),
    (
        "api-rate-limit-notice",
        "You're hitting our rate limit, please back off and retry.",
        "호출 한도에 걸리고 있습니다. 잠시 쉬었다가 재시도해 주세요.",
        PHRASE, API, N, "API 제공자가 보내는 안내",
        "요청 내용이 잘못된 게 아니라 너무 잦다는 뜻이다. 실패했다고 곧바로 다시 "
        "던지면 한도가 더 오래 풀리지 않으므로, 간격을 늘려가며 재시도해야 한다.",
    ),
    (
        "api-idempotency-key",
        "Send an idempotency key so retries don't double-charge.",
        "재시도가 이중 결제되지 않게 멱등 키를 보내주세요.",
        PHRASE, API, H, "결제 연동을 논의할 때",
        "응답을 못 받았을 때 서버에서 처리됐는지 알 수 없다는 문제를 푸는 방법이다. "
        "같은 키로 다시 보내면 서버가 이미 처리한 요청임을 알아보고 한 번만 반영한다.",
    ),
    (
        "api-pass-through-error",
        "Don't swallow the upstream error, pass it through.",
        "상위 서비스 에러를 삼키지 말고 그대로 전달하세요.",
        PHRASE, API, H, "에러 처리 방식을 지적할 때",
        "swallow 는 예외를 잡고 아무 처리도 기록도 하지 않는 것이다. 여기서는 "
        "500 으로 뭉개지 말고 원래 상태 코드와 이유를 그대로 넘기라는 요청이다.",
    ),
    (
        "api-contract-test",
        "We should add a contract test so this doesn't drift.",
        "이게 어긋나지 않도록 계약 테스트를 추가해야 합니다.",
        PHRASE, API, H, "서비스 간 연동을 논의할 때",
        "drift 는 양쪽 구현이 시간이 지나며 조금씩 어긋나는 것을 말한다. "
        "계약 테스트는 합의한 요청과 응답 형태를 양쪽에서 자동으로 확인하게 만드는 장치다.",
    ),
    (
        "api-is-this-public",
        "Is this endpoint public or internal only?",
        "이 엔드포인트는 공개인가요, 내부 전용인가요?",
        PHRASE, API, E, "새 엔드포인트를 리뷰할 때",
        "인증과 호출 한도, 그리고 앞으로 마음대로 바꿔도 되는지가 전부 이 답에 달려 "
        "있어서 리뷰에서 가장 먼저 나오는 질문 중 하나다.",
    ),

    # ---------- API / 네트워크 에러 ----------
    (
        "api-cors-blocked-policy",
        "Access to fetch at 'https://api.example.com/data' from origin 'http://localhost:3000' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.",
        "출처 'http://localhost:3000' 에서 'https://api.example.com/data' 로의 fetch 가 CORS 정책에 의해 차단되었습니다: 요청한 자원에 Access-Control-Allow-Origin 헤더가 없습니다.",
        ERROR, API, H, "브라우저 콘솔",
        "브라우저가 응답을 읽지 못하게 막은 것이고 요청 자체는 서버에 도착한 경우가 많다. "
        "그래서 서버 로그에는 200 으로 남는다. 프론트 코드로는 풀 수 없고 서버가 "
        "이 출처를 허용해야 한다. fetch 대신 script, image 등 요청 종류에 따라 "
        "앞부분 단어가 바뀐다.",
    ),
    (
        "api-cors-preflight-failed",
        "Response to preflight request doesn't pass access control check: No 'Access-Control-Allow-Origin' header is present on the requested resource.",
        "프리플라이트 요청에 대한 응답이 접근 제어 검사를 통과하지 못했습니다: 요청한 자원에 Access-Control-Allow-Origin 헤더가 없습니다.",
        ERROR, API, H, "브라우저 콘솔",
        "본 요청 전에 브라우저가 먼저 보낸 OPTIONS 요청이 막혔다는 뜻이다. "
        "이 단계에서 실패하면 본 요청은 아예 나가지 않아 서버 로그에도 남지 않는다. "
        "서버가 OPTIONS 를 제대로 처리하는지부터 확인해야 한다.",
    ),
    (
        "api-err-connection-refused",
        "net::ERR_CONNECTION_REFUSED",
        "net::ERR_CONNECTION_REFUSED (연결이 거부됨)",
        ERROR, API, E, "브라우저 콘솔",
        "주소까지는 찾았는데 그 포트에서 아무도 듣고 있지 않다는 뜻이다. "
        "서버가 안 떠 있거나 포트를 잘못 적은 경우다. CORS 문제와 헷갈리기 쉬운데, "
        "이건 아예 연결이 안 된 것이라 성격이 전혀 다르다.",
    ),
    (
        "api-err-name-not-resolved",
        "net::ERR_NAME_NOT_RESOLVED",
        "net::ERR_NAME_NOT_RESOLVED (이름을 확인할 수 없음)",
        ERROR, API, E, "브라우저 콘솔",
        "도메인 이름을 주소로 바꾸는 단계에서 실패했다는 뜻이다. 오타이거나 "
        "DNS 설정이 아직 퍼지지 않았거나, 사내망에서만 도는 주소를 밖에서 부른 경우다. "
        "서버 문제가 아니라 이름 조회 문제다.",
    ),
    (
        "api-failed-to-fetch",
        "Uncaught (in promise) TypeError: Failed to fetch",
        "처리되지 않은 오류(프로미스): TypeError: fetch 실패",
        ERROR, API, H, "브라우저 콘솔",
        "가장 정보가 없는 에러 중 하나다. 네트워크 단절, CORS 차단, 잘못된 주소가 "
        "전부 같은 문구로 나온다. 브라우저가 보안상 이유를 알려주지 않기 때문이라, "
        "네트워크 탭에서 실제 요청이 어떻게 됐는지를 봐야 한다.",
    ),
    (
        "api-mixed-content-blocked",
        "Mixed Content: The page at 'https://example.com/' was loaded over HTTPS, but requested an insecure resource 'http://example.com/api/data'. This request has been blocked; the content must be served over HTTPS.",
        "혼합 콘텐츠: 'https://example.com/' 페이지는 HTTPS 로 로드되었지만 안전하지 않은 자원 'http://example.com/api/data' 를 요청했습니다. 이 요청은 차단되었으며 콘텐츠는 HTTPS 로 제공되어야 합니다.",
        ERROR, API, N, "브라우저 콘솔",
        "HTTPS 페이지 안에서 HTTP 자원을 부를 때 브라우저가 막는다. 코드에 주소를 "
        "http 로 하드코딩해뒀거나 옛 CDN 주소가 남아 있는 경우가 대부분이다. "
        "로컬에서는 HTTP 로 열어서 보이지 않다가 배포 후에 드러난다.",
    ),
    (
        "api-curl-connection-refused",
        "curl: (7) Failed to connect to 127.0.0.1 port 8000 after 0 ms: Couldn't connect to server",
        "curl: (7) 127.0.0.1 의 8000 포트 연결에 실패했습니다(0ms 경과): 서버에 연결할 수 없음",
        ERROR, API, E, "터미널에서 curl 로 확인할 때",
        "괄호 안 7 은 curl 의 연결 실패 코드다. 서버가 안 떠 있거나 다른 포트에서 "
        "돌고 있다는 뜻이다. 예전 curl 은 뒤가 Connection refused 로 끝났으므로 "
        "검색할 때는 앞의 (7) 로 찾는 편이 낫다.",
    ),
    (
        "api-curl-could-not-resolve",
        "curl: (6) Could not resolve host: api.example.com",
        "curl: (6) 호스트를 확인할 수 없습니다: api.example.com",
        ERROR, API, E, "터미널에서 curl 로 확인할 때",
        "도메인 이름을 주소로 바꾸지 못했다는 뜻이다. 오타이거나, 컨테이너 안에서 "
        "호스트 이름을 부를 때 그 이름이 그 네트워크에 없는 경우가 흔하다. "
        "서버 상태와는 무관한 단계에서 실패한 것이다.",
    ),
    (
        "api-ssl-cert-verify-failed",
        "ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate",
        "SSL 인증서 검증 오류: 인증서 검증 실패: 로컬 발급자 인증서를 가져올 수 없습니다",
        ERROR, API, H, "파이썬에서 HTTPS 요청을 보낼 때",
        "서버 인증서가 가짜라는 뜻이 아니라, 그 인증서를 보증하는 상위 인증서를 "
        "이쪽에서 찾지 못했다는 뜻이다. 검증을 끄는 것이 아니라 신뢰 인증서 묶음을 "
        "설치하는 것이 올바른 해결이다. 사내 프록시 환경에서 특히 자주 만난다.",
    ),
    (
        "api-max-retries-exceeded",
        "requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /api/users",
        "연결 오류: HTTPConnectionPool(host='localhost', port=8000): /api/users 로 최대 재시도 횟수를 초과했습니다",
        ERROR, API, N, "파이썬 requests 로 호출할 때",
        "재시도를 많이 해서 난 문제가 아니라 아예 연결이 안 됐다는 뜻이다. "
        "진짜 원인은 이 줄이 아니라 그 아래 괄호 안에 붙는 원인 문구에 있으므로 "
        "끝까지 읽어야 한다.",
    ),
    (
        "api-json-unexpected-token-html",
        "SyntaxError: Unexpected token '<', \"<!DOCTYPE \"... is not valid JSON",
        "구문 오류: 예기치 않은 토큰 '<', \"<!DOCTYPE \"... 는 올바른 JSON 이 아닙니다",
        ERROR, API, H, "응답을 JSON 으로 파싱할 때",
        "JSON 을 기대했는데 HTML 이 왔다는 뜻이다. 대개 404 페이지나 로그인 화면, "
        "에러 페이지를 받은 것이라 진짜 문제는 파싱이 아니라 요청 주소나 인증에 있다. "
        "예전 브라우저와 Node 는 Unexpected token < in JSON at position 0 으로 찍었다.",
    ),
    (
        "api-json-unexpected-end",
        "SyntaxError: Unexpected end of JSON input",
        "구문 오류: JSON 입력이 예기치 않게 끝났습니다",
        ERROR, API, N, "빈 응답을 JSON 으로 파싱할 때",
        "본문이 비어 있는데 파싱을 시도했다는 뜻이다. 204 응답이나 본문 없는 리다이렉트, "
        "혹은 연결이 중간에 끊긴 경우다. 파싱 전에 본문이 있는지 확인하는 것이 해법이다.",
    ),
    (
        "api-json-decode-expecting-value",
        "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        "JSON 디코드 오류: 값이 필요합니다: 1행 1열 (문자 0)",
        ERROR, API, N, "파이썬에서 응답을 파싱할 때",
        "위 자바스크립트 쪽과 같은 상황의 파이썬 판이다. 첫 글자부터 JSON 이 아니라는 "
        "뜻이라 응답이 비었거나 HTML 이다. response.text 를 먼저 찍어보면 "
        "원인이 바로 보인다.",
    ),
    (
        "api-drf-no-credentials",
        "{\"detail\":\"Authentication credentials were not provided.\"}",
        "{\"detail\":\"인증 자격 증명이 제공되지 않았습니다.\"}",
        ERROR, API, N, "Django REST Framework 응답 본문",
        "토큰이나 세션이 아예 오지 않았다는 뜻이다. 로그인은 했는데 이게 나오면 헤더 "
        "이름이 틀렸거나 다른 출처로 요청해 쿠키가 함께 가지 않은 경우다. 같은 본문이 "
        "401 로도 403 으로도 나가는데, 인증 방식이 세션뿐이면 403 이 된다.",
    ),
    (
        "api-drf-permission-denied",
        "{\"detail\":\"You do not have permission to perform this action.\"}",
        "{\"detail\":\"이 작업을 수행할 권한이 없습니다.\"}",
        ERROR, API, N, "Django REST Framework 응답 본문",
        "누구인지는 확인됐지만 권한이 없다는 뜻으로 403 과 함께 온다. 위의 "
        "자격 증명 없음과 달리 다시 로그인해도 해결되지 않는다. 역할과 권한 설정을 봐야 한다.",
    ),
    (
        "api-method-not-allowed",
        "{\"detail\":\"Method \\\"GET\\\" not allowed.\"}",
        "{\"detail\":\"\\\"GET\\\" 메서드는 허용되지 않습니다.\"}",
        ERROR, API, N, "Django REST Framework 응답 본문",
        "주소는 맞는데 그 메서드를 지원하지 않는다는 뜻이다. 404 와 헷갈리기 쉬운데 "
        "이건 자원을 찾았다는 뜻이라, 라우팅은 정상이고 메서드만 잘못됐다는 좋은 단서다.",
    ),
    (
        "api-gateway-time-out",
        "504 Gateway Time-out",
        "504 게이트웨이 시간 초과",
        ERROR, API, N, "nginx 가 돌려주는 에러 페이지",
        "앞단 서버가 뒤쪽 응답을 기다리다 끊었다는 뜻이다. 뒤쪽이 죽은 것이 아니라 "
        "느린 것이므로 무거운 쿼리나 외부 호출 지연을 봐야 한다. "
        "nginx 는 Time-out 을 이렇게 하이픈으로 적는다.",
    ),
    (
        "api-request-entity-too-large",
        "413 Request Entity Too Large",
        "413 요청 본문이 너무 큼",
        ERROR, API, N, "파일 업로드가 실패할 때",
        "애플리케이션이 아니라 앞단 서버가 먼저 막은 경우가 많다. 로컬에서는 되는데 "
        "배포하면 업로드가 실패하는 전형적인 원인이고, nginx 라면 "
        "client_max_body_size 를 올려야 한다.",
    ),
    (
        "api-nginx-upstream-closed",
        "upstream prematurely closed connection while reading response header from upstream",
        "응답 헤더를 읽는 중 상위 서버가 연결을 미리 닫았습니다",
        ERROR, API, H, "nginx 에러 로그",
        "뒤쪽 애플리케이션이 응답을 다 주기 전에 죽었거나 연결을 끊었다는 뜻이다. "
        "사용자에게는 502 로 보인다. nginx 설정이 아니라 애플리케이션 로그를 봐야 하고, "
        "메모리 부족으로 프로세스가 죽은 경우가 흔하다.",
    ),
    (
        "api-nginx-connect-refused-upstream",
        "connect() failed (111: Connection refused) while connecting to upstream",
        "상위 서버에 연결하는 중 connect() 실패 (111: 연결 거부됨)",
        ERROR, API, N, "nginx 에러 로그",
        "뒤쪽 애플리케이션이 아예 떠 있지 않다는 뜻이다. 111 은 리눅스의 연결 거부 "
        "번호다. 배포 중 잠깐 나는 것은 정상일 수 있지만 계속 난다면 "
        "애플리케이션이 뜨지 못한 것이다.",
    ),
    (
        "api-nginx-body-too-large",
        "client intended to send too large body: 20971520 bytes",
        "클라이언트가 너무 큰 본문을 보내려 했습니다: 20971520 바이트",
        ERROR, API, N, "nginx 에러 로그",
        "위의 413 이 나올 때 서버 쪽에 남는 실제 로그다. 사용자 화면만 보면 원인을 "
        "알 수 없는데 이 줄에는 실제 크기가 바이트로 찍히므로 한도를 얼마로 "
        "올려야 하는지 바로 알 수 있다.",
    ),
    (
        "api-fetch-failed-node",
        "TypeError: fetch failed",
        "타입 오류: fetch 실패",
        ERROR, API, H, "Node.js 서버 로그",
        "브라우저 쪽 Failed to fetch 와 비슷해 보이지만 Node 에서는 진짜 원인이 "
        "cause 에 따로 담긴다. 그 안에 ECONNREFUSED 나 ENOTFOUND 같은 코드가 있으므로 "
        "에러 객체 전체를 찍어봐야 원인이 나온다.",
    ),
    (
        "api-econnrefused",
        "connect ECONNREFUSED 127.0.0.1:5432",
        "연결 거부됨 127.0.0.1:5432",
        ERROR, API, E, "Node.js 서버 로그",
        "그 주소와 포트에서 아무도 듣고 있지 않다는 뜻이다. 포트 번호가 원인을 "
        "알려주는 가장 좋은 단서라, 5432 라면 데이터베이스, 6379 라면 캐시가 "
        "안 떠 있는 것이다.",
    ),
    (
        "api-enotfound",
        "getaddrinfo ENOTFOUND api.example.com",
        "주소 조회 실패: api.example.com 을 찾을 수 없습니다",
        ERROR, API, N, "Node.js 서버 로그",
        "이름을 주소로 바꾸는 단계에서 실패했다는 뜻이다. 도커 컴포즈에서 서비스 "
        "이름을 잘못 적었거나, 컨테이너가 같은 네트워크에 없을 때 흔하다. "
        "연결 거부와 달리 아직 접속을 시도조차 못 한 상태다.",
    ),
    (
        "api-etimedout",
        "connect ETIMEDOUT",
        "연결 시간 초과",
        ERROR, API, N, "Node.js 서버 로그",
        "연결 거부와 달리 상대가 아무 응답도 하지 않아 기다리다 끊긴 것이다. "
        "거부는 즉시 오지만 이건 시간이 걸린다. 방화벽이 패킷을 조용히 버리는 경우가 "
        "대표적인 원인이다.",
    ),
    (
        "api-drf-throttled",
        "{\"detail\":\"Request was throttled. Expected available in 59 seconds.\"}",
        "{\"detail\":\"요청이 제한되었습니다. 59초 뒤에 가능할 것으로 예상됩니다.\"}",
        ERROR, API, N, "Django REST Framework 응답 본문",
        "호출 한도에 걸렸다는 뜻으로 429 와 함께 온다. 요청 내용이 잘못된 게 아니라 "
        "너무 잦다는 뜻이라 고칠 것은 코드가 아니라 호출 속도다. 몇 초 뒤에 되는지까지 "
        "알려주므로 그 값을 그대로 재시도 간격으로 쓰면 된다.",
    ),
    (
        "api-content-type-not-supported",
        "{\"detail\":\"Unsupported media type \\\"text/plain\\\" in request.\"}",
        "{\"detail\":\"요청에 지원되지 않는 미디어 타입 \\\"text/plain\\\" 이 있습니다.\"}",
        ERROR, API, N, "Django REST Framework 응답 본문",
        "본문 형식을 알리는 Content-Type 헤더가 서버가 받는 형식과 다르다는 뜻이다. "
        "JSON 을 보내면서 헤더를 빠뜨린 경우가 대부분이라, 본문 내용이 아니라 "
        "헤더를 먼저 확인해야 한다.",
    ),

    # ---------- 데이터베이스 표현 ----------
    (
        "db-add-index-suggestion",
        "This query would benefit from an index on user_id.",
        "이 쿼리는 user_id 에 인덱스를 걸면 나아질 겁니다.",
        PHRASE, DB, N, "느린 쿼리를 리뷰할 때",
        "benefit from 은 '그렇게 하면 좋아진다' 는 제안형 표현이다. 조회는 빨라지지만 "
        "쓰기가 조금 느려지므로, 실제로 걸기 전에 실행 계획으로 효과를 확인하자는 "
        "말이 뒤따르는 경우가 많다.",
    ),
    (
        "db-backfill-plan",
        "How are we backfilling the existing rows?",
        "기존 행들은 어떻게 채워 넣을 예정인가요?",
        PHRASE, DB, H, "칼럼 추가 마이그레이션을 리뷰할 때",
        "backfill 은 새로 만든 칼럼을 기존 데이터에 소급해 채우는 작업이다. "
        "행이 많으면 한 번에 갱신하다 테이블이 잠기므로 나눠서 돌리는 계획을 "
        "묻는 질문이다.",
    ),
    (
        "db-online-migration",
        "Can we make this migration online so we don't lock the table?",
        "테이블이 잠기지 않게 이 마이그레이션을 무중단으로 할 수 있을까요?",
        PHRASE, DB, H, "스키마 변경을 논의할 때",
        "online 은 서비스를 멈추지 않고 진행한다는 뜻이다. 칼럼 추가는 대개 괜찮지만 "
        "타입 변경이나 인덱스 생성은 오래 잠글 수 있어서 나오는 질문이다.",
    ),
    (
        "db-n-plus-one-flag",
        "This looks like an N+1, can we prefetch the related rows?",
        "이건 N+1 같습니다. 연관된 행들을 미리 가져올 수 있을까요?",
        PHRASE, DB, H, "목록 화면 코드를 리뷰할 때",
        "코드에는 반복문 한 줄뿐이라 눈에 잘 안 띄고, 데이터가 적은 개발 환경에서는 "
        "멀쩡하다가 운영에서 터진다. 쿼리 로그를 켜서 실제 나가는 쿼리 수를 "
        "세어보면 바로 확인된다.",
    ),
    (
        "db-two-step-column-drop",
        "Let's stop writing to that column first, then drop it next release.",
        "먼저 그 칼럼에 쓰기를 멈추고 다음 릴리스에 지웁시다.",
        PHRASE, DB, H, "칼럼 삭제를 계획할 때",
        "무중단 배포 중에는 옛 코드와 새 코드가 잠시 함께 돌기 때문에, 칼럼을 바로 "
        "지우면 옛 코드가 깨진다. 그래서 삭제는 항상 두 단계로 나눠 진행한다.",
    ),
    (
        "db-restore-from-backup",
        "Do we have a backup we can restore from?",
        "복원할 수 있는 백업이 있나요?",
        PHRASE, DB, N, "데이터 사고가 났을 때",
        "장애 대응에서 가장 먼저 나오는 질문이다. 백업이 있느냐보다 실제로 복원해본 "
        "적이 있느냐가 중요한데, 한 번도 복원해보지 않은 백업은 없는 것과 다르지 않다.",
    ),

    # ---------- 데이터베이스 에러 ----------
    (
        "db-relation-does-not-exist",
        "ERROR:  relation \"customers\" does not exist",
        "오류: \"customers\" 릴레이션이 존재하지 않습니다",
        ERROR, DB, N, "PostgreSQL 에서 쿼리를 실행할 때",
        "relation 은 여기서 테이블이나 뷰를 뜻한다. 마이그레이션을 안 돌렸거나, "
        "다른 스키마나 다른 데이터베이스에 접속한 경우가 대부분이다. "
        "PostgreSQL 은 ERROR 뒤에 공백을 두 칸 넣는다.",
    ),
    (
        "db-column-does-not-exist",
        "ERROR:  column \"created_at\" does not exist",
        "오류: \"created_at\" 칼럼이 존재하지 않습니다",
        ERROR, DB, N, "PostgreSQL 에서 쿼리를 실행할 때",
        "테이블은 찾았는데 칼럼이 없다는 뜻이다. 오타이거나 마이그레이션이 일부만 "
        "반영된 상태다. 문자열에 따옴표를 잘못 써서 값이 칼럼 이름으로 해석된 "
        "경우에도 이 에러가 나온다.",
    ),
    (
        "db-null-value-not-null-constraint",
        "ERROR:  null value in column \"email\" of relation \"users\" violates not-null constraint",
        "오류: \"users\" 릴레이션의 \"email\" 칼럼에 들어간 null 값이 not-null 제약을 위반합니다",
        ERROR, DB, E, "PostgreSQL 에 데이터를 넣을 때",
        "필수 칼럼을 빼고 넣었다는 뜻이다. 코드에서 값을 안 넣은 경우도 있지만, "
        "기본값 없이 NOT NULL 칼럼을 추가하는 마이그레이션이 기존 행 때문에 "
        "실패하는 경우도 흔하다.",
    ),
    (
        "db-value-too-long",
        "ERROR:  value too long for type character varying(20)",
        "오류: character varying(20) 타입에 비해 값이 너무 깁니다",
        ERROR, DB, E, "PostgreSQL 에 데이터를 넣을 때",
        "칼럼 길이 제한을 넘었다는 뜻이다. 이 길이는 바이트가 아니라 글자 수 기준이라 "
        "한글도 한 글자로 센다. 다만 인덱스 키 길이 제한은 바이트로 걸리는 경우가 있어 "
        "둘을 같은 기준으로 생각하면 안 된다.",
    ),
    (
        "db-foreign-key-insert-violation",
        "ERROR:  insert or update on table \"orders\" violates foreign key constraint \"orders_user_id_fkey\"",
        "오류: \"orders\" 테이블의 삽입이나 갱신이 외래키 제약 \"orders_user_id_fkey\" 를 위반합니다",
        ERROR, DB, N, "PostgreSQL 에 데이터를 넣을 때",
        "가리키려는 부모 행이 없다는 뜻이다. 아래에 붙는 DETAIL 줄에 어떤 값이 "
        "없는지 정확히 나오므로 그쪽을 봐야 한다. 부모를 만들기 전에 자식을 먼저 "
        "넣은 순서 문제가 대부분이다.",
    ),
    (
        "db-foreign-key-delete-violation",
        "ERROR:  update or delete on table \"users\" violates foreign key constraint \"orders_user_id_fkey\" on table \"orders\"",
        "오류: \"users\" 테이블의 갱신이나 삭제가 \"orders\" 테이블의 외래키 제약 \"orders_user_id_fkey\" 를 위반합니다",
        ERROR, DB, N, "PostgreSQL 에서 행을 지울 때",
        "지우려는 행을 아직 다른 테이블이 참조하고 있다는 뜻이다. 위의 삽입 위반과 "
        "방향이 반대라 헷갈리기 쉬운데, on table 이 두 번 나오면 이쪽이다. "
        "자식을 먼저 정리하거나 삭제 동작을 설정해야 한다.",
    ),
    (
        "db-deadlock-detected",
        "ERROR:  deadlock detected",
        "오류: 교착 상태가 감지되었습니다",
        ERROR, DB, H, "PostgreSQL 에서 동시에 갱신할 때",
        "둘이 서로가 쥔 행을 기다려 아무도 진행하지 못하는 상태다. 데이터베이스가 "
        "감지해 한쪽을 강제로 취소시키므로 서비스가 멈추지는 않는다. "
        "여러 행을 항상 같은 순서로 갱신하도록 바꾸면 크게 줄어든다.",
    ),
    (
        "db-statement-timeout",
        "ERROR:  canceling statement due to statement timeout",
        "오류: 구문 제한 시간 초과로 쿼리를 취소합니다",
        ERROR, DB, N, "무거운 쿼리를 실행할 때",
        "쿼리가 틀린 게 아니라 정해둔 시간을 넘겨 데이터베이스가 끊은 것이다. "
        "제한 시간을 늘리기 전에 실행 계획을 먼저 보는 것이 순서다. "
        "제한이 없으면 느린 쿼리 하나가 커넥션을 계속 붙잡는다.",
    ),
    (
        "db-transaction-aborted",
        "ERROR:  current transaction is aborted, commands ignored until end of transaction block",
        "오류: 현재 트랜잭션이 중단되었습니다. 트랜잭션 블록이 끝날 때까지 명령이 무시됩니다",
        ERROR, DB, H, "트랜잭션 안에서 쿼리가 실패한 뒤",
        "진짜 원인은 이 줄이 아니라 그 앞에서 실패한 쿼리다. 한 번 실패한 트랜잭션 "
        "안에서는 이후 모든 명령이 이 메시지를 뱉으므로, 로그를 위로 거슬러 올라가 "
        "첫 번째 에러를 찾아야 한다.",
    ),
    (
        "db-column-reference-ambiguous",
        "ERROR:  column reference \"id\" is ambiguous",
        "오류: 칼럼 참조 \"id\" 가 모호합니다",
        ERROR, DB, N, "조인 쿼리를 실행할 때",
        "조인한 두 테이블에 같은 이름의 칼럼이 있어 어느 쪽인지 알 수 없다는 뜻이다. "
        "테이블 별칭을 붙여 users.id 처럼 지정하면 해결된다.",
    ),
    (
        "db-must-appear-in-group-by",
        "ERROR:  column \"users.age\" must appear in the GROUP BY clause or be used in an aggregate function",
        "오류: \"users.age\" 칼럼은 GROUP BY 절에 있거나 집계 함수 안에서 쓰여야 합니다",
        ERROR, DB, H, "집계 쿼리를 실행할 때",
        "묶은 뒤에는 묶음 단위로만 이야기할 수 있는데, 묶는 기준에 없는 칼럼을 "
        "그냥 꺼내려 했다는 뜻이다. MySQL 은 설정에 따라 이걸 조용히 허용해서 "
        "옮겨올 때 처음 만나는 경우가 많다.",
    ),
    (
        "db-invalid-input-syntax-integer",
        "ERROR:  invalid input syntax for type integer: \"abc\"",
        "오류: integer 타입에 대한 잘못된 입력 구문: \"abc\"",
        ERROR, DB, E, "숫자 칼럼에 문자열을 넣을 때",
        "숫자 칼럼에 숫자로 바꿀 수 없는 값이 들어갔다는 뜻이다. 사용자 입력을 "
        "그대로 조건에 넣었거나, 빈 문자열을 숫자로 보내는 경우가 흔하다.",
    ),
    (
        "db-too-many-clients",
        "FATAL:  sorry, too many clients already",
        "치명적 오류: 죄송합니다, 이미 클라이언트가 너무 많습니다",
        ERROR, DB, H, "PostgreSQL 접속이 갑자기 실패할 때",
        "허용된 동시 접속 수를 다 썼다는 뜻이다. 접속을 늘리기보다 커넥션 풀이 "
        "연결을 제대로 반환하는지 먼저 봐야 한다. 애플리케이션 인스턴스를 늘렸을 때 "
        "풀 크기까지 함께 늘어나 터지는 경우가 대표적이다.",
    ),
    (
        "db-psql-connection-refused",
        "psql: error: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused",
        "psql: 오류: \"127.0.0.1\" 서버의 5432 포트 연결에 실패했습니다: 연결이 거부되었습니다",
        ERROR, DB, E, "psql 로 접속을 시도할 때",
        "데이터베이스가 안 떠 있거나 다른 포트에서 돌고 있다는 뜻이다. "
        "비밀번호가 틀렸을 때와는 전혀 다른 단계의 문제라, 계정 설정을 뒤지기 전에 "
        "서버가 실제로 실행 중인지부터 확인해야 한다.",
    ),
    (
        "db-mysql-duplicate-entry",
        "ERROR 1062 (23000): Duplicate entry 'user@example.com' for key 'users.email'",
        "오류 1062 (23000): 키 'users.email' 에 대한 중복 항목 'user@example.com'",
        ERROR, DB, N, "MySQL 에 데이터를 넣을 때",
        "유니크 제약에 걸렸다는 뜻이다. 코드에서 미리 조회해 확인하더라도 동시에 두 "
        "요청이 들어오면 뚫리므로, 이 에러를 잡아 처리하는 편이 안전하다. "
        "MySQL 8.0.19 부터 키 이름 앞에 테이블 이름이 붙는다.",
    ),
    (
        "db-mysql-too-many-connections",
        "ERROR 1040 (08004): Too many connections",
        "오류 1040 (08004): 연결이 너무 많습니다",
        ERROR, DB, H, "MySQL 접속이 갑자기 실패할 때",
        "PostgreSQL 의 too many clients 와 같은 상황이다. MySQL 은 관리자용으로 "
        "한 자리를 자동으로 남겨두므로, 조사에 쓸 계정에 CONNECTION_ADMIN 권한이 "
        "있는지 미리 확인해두면 이 상황에서 접속할 수 있다.",
    ),
    (
        "db-mysql-lock-wait-timeout",
        "ERROR 1205 (HY000): Lock wait timeout exceeded; try restarting transaction",
        "오류 1205 (HY000): 잠금 대기 시간을 초과했습니다. 트랜잭션을 다시 시작해 보세요",
        ERROR, DB, H, "MySQL 에서 갱신이 오래 걸릴 때",
        "교착 상태와 달리 상대가 계속 잠금을 쥐고 있어 기다리다 끊긴 것이다. "
        "커밋하지 않고 열어둔 트랜잭션이 원인인 경우가 많아서, 재시도보다 "
        "그 긴 트랜잭션을 찾는 것이 근본 해결이다.",
    ),
    (
        "db-mysql-deadlock-found",
        "ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction",
        "오류 1213 (40001): 잠금을 얻으려는 중 교착 상태가 발견되었습니다. 트랜잭션을 다시 시작해 보세요",
        ERROR, DB, H, "MySQL 에서 동시에 갱신할 때",
        "메시지가 재시작을 권하는 이유는 교착 상태가 드물게 일어나는 정상적인 현상이라 "
        "다시 시도하면 대개 성공하기 때문이다. 자주 난다면 갱신 순서를 통일해야 한다.",
    ),
    (
        "db-mysql-child-row-fk",
        "ERROR 1452 (23000): Cannot add or update a child row: a foreign key constraint fails",
        "오류 1452 (23000): 자식 행을 추가하거나 갱신할 수 없습니다: 외래키 제약이 실패했습니다",
        ERROR, DB, N, "MySQL 에 데이터를 넣을 때",
        "가리키려는 부모 행이 없다는 뜻이다. 뒤에 괄호로 어떤 제약인지 붙는다. "
        "부모를 지울 때 나는 1451 과 번호가 붙어 있어 헷갈리는데, "
        "child 가 나오면 넣는 쪽 문제다.",
    ),
    (
        "db-mysql-table-doesnt-exist",
        "ERROR 1146 (42S02): Table 'shop.orders' doesn't exist",
        "오류 1146 (42S02): 'shop.orders' 테이블이 존재하지 않습니다",
        ERROR, DB, E, "MySQL 에서 쿼리를 실행할 때",
        "따옴표 안에 데이터베이스 이름과 테이블 이름이 점으로 이어져 나오므로, "
        "어느 데이터베이스를 보고 있었는지까지 알 수 있다. 접속한 데이터베이스가 "
        "예상과 다른 경우를 여기서 잡아낼 수 있다.",
    ),
    (
        "db-mysql-incorrect-string-value",
        "ERROR 1366 (HY000): Incorrect string value: '\\xF0\\x9F\\x98\\x80' for column 'name' at row 1",
        "오류 1366 (HY000): 1행 'name' 칼럼에 잘못된 문자열 값: '\\xF0\\x9F\\x98\\x80'",
        ERROR, DB, H, "MySQL 에 4바이트 문자를 넣을 때",
        "칼럼 인코딩이 utf8mb3 인데 4바이트를 쓰는 문자가 들어왔다는 뜻이다. "
        "MySQL 의 utf8 은 3바이트까지만 담는 반쪽짜리라 utf8mb4 로 바꿔야 한다. "
        "설정에 따라 에러가 아니라 경고로 나가며 값이 잘려 저장되기도 한다.",
    ),
    (
        "db-django-relation-not-exist",
        "django.db.utils.ProgrammingError: relation \"users_profile\" does not exist",
        "django.db.utils.ProgrammingError: \"users_profile\" 릴레이션이 존재하지 않습니다",
        ERROR, DB, N, "Django 애플리케이션 로그",
        "모델은 있는데 실제 테이블이 없다는 뜻이다. 마이그레이션 파일을 만들고 "
        "적용까지 했는지 확인해야 한다. 배포에서 마이그레이션 단계를 빠뜨렸을 때 "
        "가장 흔하게 만난다.",
    ),
    (
        "db-django-conflicting-migrations",
        "CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph: (0003_add_email, 0003_add_phone in users).",
        "명령 오류: 충돌하는 마이그레이션이 감지되었습니다. 마이그레이션 그래프에 리프 노드가 여러 개입니다: (users 앱의 0003_add_email, 0003_add_phone).",
        ERROR, DB, H, "여러 사람이 각자 마이그레이션을 만들었을 때",
        "같은 시점에서 갈라진 마이그레이션이 두 개라 순서를 정할 수 없다는 뜻이다. "
        "브랜치를 병합할 때 자주 난다. makemigrations --merge 로 합치는 파일을 "
        "만들어주면 해결된다.",
    ),
    (
        "db-sqlite-database-is-locked",
        "sqlite3.OperationalError: database is locked",
        "sqlite3.OperationalError: 데이터베이스가 잠겨 있습니다",
        ERROR, DB, N, "SQLite 를 여러 프로세스에서 쓸 때",
        "SQLite 는 파일 하나를 쓰기 때문에 동시에 쓰는 것에 약하다. 코드 버그가 아니라 "
        "구조적 한계라, 개발 환경에서는 넘어가도 운영에서 이 에러가 난다면 "
        "다른 데이터베이스를 쓸 때가 된 것이다.",
    ),
    (
        "db-connection-pool-timeout",
        "sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00",
        "sqlalchemy.exc.TimeoutError: 크기 5, 오버플로 10 인 QueuePool 한도에 도달해 연결이 시간 초과되었습니다(제한 30.00초)",
        ERROR, DB, H, "파이썬 애플리케이션 로그",
        "커넥션 풀에서 빌릴 연결이 없어 기다리다 끊긴 것이다. 풀을 키우기 전에 "
        "연결이 반환되지 않는 곳을 찾아야 한다. 세션을 닫지 않거나 오래 걸리는 "
        "외부 호출을 트랜잭션 안에 둔 경우가 대표적이다.",
    ),

    # ---------- 배포 / 운영 표현 ----------
    (
        "ops-rolling-out-gradually",
        "We're rolling this out to 10% of traffic first.",
        "먼저 트래픽의 10퍼센트에만 배포합니다.",
        PHRASE, OPS, N, "배포 공지",
        "전체가 아니라 일부에게만 먼저 내보낸다는 뜻이다. 지표를 함께 보지 않으면 "
        "그냥 느리게 배포하는 것에 지나지 않으므로, 무엇을 보고 판단할지가 "
        "함께 언급되는 것이 보통이다.",
    ),
    (
        "ops-freeze-until-release",
        "We're in a code freeze until the release goes out.",
        "릴리스가 나갈 때까지 코드 프리즈 기간입니다.",
        PHRASE, OPS, N, "릴리스 직전 공지",
        "작업을 멈추라는 게 아니라 합치는 것만 미루라는 뜻이다. 긴급 수정은 예외지만 "
        "누가 승인하는지 미리 정해두지 않으면 그 예외가 프리즈를 무의미하게 만든다.",
    ),
    (
        "ops-paging-the-oncall",
        "I'm paging the on-call, this is affecting production.",
        "온콜 담당자를 호출합니다. 운영에 영향이 있습니다.",
        PHRASE, OPS, N, "장애 대응 시작",
        "page 는 호출기에서 온 말로 자고 있어도 깨우는 알림을 뜻한다. 슬랙에 글을 "
        "남기는 것과 무게가 다르므로, 사용자에게 실제 영향이 있을 때만 쓴다.",
    ),
    (
        "ops-handover-note",
        "Handing over: the alert is still firing but the impact is contained.",
        "인수인계합니다. 알림은 계속 울리지만 영향 범위는 통제되고 있습니다.",
        PHRASE, OPS, H, "온콜 교대할 때",
        "contained 는 '더 번지지는 않는다' 는 뜻이지 해결됐다는 뜻이 아니다. "
        "인수인계에서는 어디까지 확인했고 무엇이 아직 불확실한지를 함께 넘겨야 "
        "다음 사람이 처음부터 다시 파지 않는다.",
    ),
    (
        "ops-mitigated-not-resolved",
        "Mitigated, not resolved. Root cause still unknown.",
        "완화되었을 뿐 해결된 것은 아닙니다. 근본 원인은 아직 모릅니다.",
        PHRASE, OPS, H, "장애 상황 공유",
        "mitigate 는 피해를 줄여 급한 불을 껐다는 뜻이고 resolve 는 원인을 없앴다는 "
        "뜻이다. 재시작으로 증상만 사라진 상태를 해결됐다고 보고하면 같은 장애가 "
        "곧 다시 온다.",
    ),
    (
        "ops-rollback-decision",
        "Let's roll back and investigate on a copy.",
        "일단 되돌리고 사본에서 조사합시다.",
        PHRASE, OPS, N, "장애 대응 중 결정",
        "운영에서 원인을 파느라 시간을 쓰는 대신 먼저 피해를 멈추자는 판단이다. "
        "다만 데이터베이스 구조가 이미 바뀌었으면 코드만 되돌릴 수 없으므로 "
        "그 확인이 함께 필요하다.",
    ),
    (
        "ops-blast-radius",
        "What's the blast radius if this goes wrong?",
        "이게 잘못되면 영향 범위가 어디까지인가요?",
        PHRASE, OPS, H, "위험한 변경을 검토할 때",
        "blast radius 는 폭발 반경이라는 뜻으로 실패했을 때 영향을 받는 범위를 "
        "가리킨다. 확률이 아니라 범위를 묻는 질문이라, '드물게 일어난다' 는 답은 "
        "이 질문의 답이 아니다.",
    ),
    (
        "ops-scale-up-before-event",
        "Let's scale up ahead of the event, not during it.",
        "행사 도중이 아니라 시작 전에 미리 늘려둡시다.",
        PHRASE, OPS, N, "트래픽이 몰릴 일정을 준비할 때",
        "자동 확장은 새 서버가 뜨는 데 시간이 걸려 갑자기 몰리는 트래픽에는 늦게 "
        "반응한다. 예정된 부하는 미리 늘려두는 것이 정석이라는 이야기다.",
    ),
    (
        "ops-runbook-link",
        "The alert links to a runbook with the exact steps.",
        "이 알림에는 정확한 절차가 담긴 런북 링크가 걸려 있습니다.",
        PHRASE, OPS, N, "온콜 안내",
        "런북은 새벽에 잠에서 깬 사람이 그대로 따라할 수 있을 만큼 구체적이어야 "
        "쓸모가 있다. 알림마다 링크를 걸어두는 이유는 그 순간 문서를 찾아다니지 "
        "않게 하기 위해서다.",
    ),
    (
        "ops-toil-automation",
        "This is toil, let's automate it away.",
        "이건 반복 노동이니 자동화해서 없앱시다.",
        PHRASE, OPS, H, "운영 부담을 논의할 때",
        "toil 은 가치를 만들지 않으면서 규모에 비례해 늘어나는 수작업을 뜻한다. "
        "SRE 에서 쓰는 용어로, 힘든 일이라는 뜻이 아니라 자동화 대상이라는 "
        "분류에 가깝다.",
    ),

    # ---------- 배포 / 운영 에러 ----------
    (
        "ops-no-space-left",
        "no space left on device",
        "장치에 남은 공간이 없습니다",
        ERROR, OPS, E, "빌드나 배포가 갑자기 실패할 때",
        "디스크가 찼다는 뜻인데, 용량이 아니라 파일 수 한도에 걸린 경우도 같은 "
        "문구가 나온다. 도커를 쓴다면 대개 오래된 이미지와 빌드 캐시가 원인이라 "
        "정리하면 바로 풀린다.",
    ),
    (
        "ops-port-already-allocated",
        "Bind for 0.0.0.0:8080 failed: port is already allocated",
        "0.0.0.0:8080 바인딩 실패: 포트가 이미 할당되어 있습니다",
        ERROR, OPS, E, "docker run 이나 docker compose up 실행 시",
        "그 포트를 이미 다른 컨테이너나 프로세스가 쓰고 있다는 뜻이다. "
        "앞서 띄운 컨테이너가 멈추지 않고 남아 있는 경우가 대부분이라, "
        "docker ps 로 먼저 확인한다.",
    ),
    (
        "ops-container-name-in-use",
        "Conflict. The container name \"/my-app\" is already in use by container",
        "충돌. 컨테이너 이름 \"/my-app\" 을 이미 다른 컨테이너가 쓰고 있습니다",
        ERROR, OPS, E, "같은 이름으로 컨테이너를 또 만들 때",
        "이름은 살아 있는 컨테이너뿐 아니라 멈춘 컨테이너도 차지한다. "
        "그래서 실행 중인 것이 없어도 이 에러가 나며, 멈춘 컨테이너를 지우거나 "
        "실행할 때 --rm 을 붙여두면 반복되지 않는다.",
    ),
    (
        "ops-exec-format-error",
        "exec /usr/bin/sh: exec format error",
        "exec /usr/bin/sh: 실행 파일 형식 오류",
        ERROR, OPS, H, "컨테이너가 즉시 종료될 때",
        "이미지의 CPU 아키텍처가 서버와 다르다는 뜻이다. 애플 실리콘 맥에서 빌드한 "
        "arm64 이미지를 amd64 서버에 올렸을 때 대표적으로 난다. "
        "빌드할 때 대상 플랫폼을 지정하면 해결된다.",
    ),
    (
        "ops-cannot-connect-daemon",
        "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
        "unix:///var/run/docker.sock 의 도커 데몬에 연결할 수 없습니다. 도커 데몬이 실행 중인가요?",
        ERROR, OPS, E, "docker 명령을 실행할 때",
        "명령이 틀린 게 아니라 도커 자체가 안 떠 있다는 뜻이다. 데스크톱 앱을 켜지 "
        "않았거나, 리눅스에서 현재 계정이 도커 그룹에 없어 소켓에 접근하지 못하는 "
        "경우가 대부분이다.",
    ),
    (
        "ops-pull-access-denied",
        "Error response from daemon: pull access denied for myimage, repository does not exist or may require 'docker login'",
        "데몬 응답 오류: myimage 에 대한 pull 권한이 없습니다. 저장소가 없거나 'docker login' 이 필요할 수 있습니다",
        ERROR, OPS, N, "이미지를 받아올 때",
        "저장소가 없는 경우와 권한이 없는 경우를 하나의 문구로 묶어 알려준다. "
        "비공개 저장소의 존재 여부를 외부에 노출하지 않으려는 것이라, "
        "이름 오타와 로그인 누락을 둘 다 확인해야 한다.",
    ),
    (
        "ops-imagepullbackoff",
        "ImagePullBackOff",
        "ImagePullBackOff (이미지 받아오기 실패 후 대기)",
        ERROR, OPS, N, "kubectl get pods 의 STATUS 칸",
        "이미지를 받지 못해 재시도를 점점 늦추며 기다리는 상태다. 태그 오타나 "
        "비공개 저장소 인증 누락이 원인인 경우가 대부분이다. 실제 이유는 이 단어가 "
        "아니라 kubectl describe pod 의 이벤트 목록에 있다.",
    ),
    (
        "ops-crashloopbackoff",
        "CrashLoopBackOff",
        "CrashLoopBackOff (반복 종료 후 대기)",
        ERROR, OPS, N, "kubectl get pods 의 STATUS 칸",
        "컨테이너가 뜨자마자 죽기를 반복해 쿠버네티스가 재시작 간격을 늘린 상태다. "
        "이미지 문제가 아니라 애플리케이션이 시작에 실패한 것이므로 "
        "kubectl logs 로 그 안의 에러를 봐야 한다.",
    ),
    (
        "ops-backoff-restarting",
        "Back-off restarting failed container",
        "실패한 컨테이너 재시작을 지연시킵니다",
        ERROR, OPS, N, "kubectl describe pod 의 Events",
        "위의 CrashLoopBackOff 와 짝을 이루는 이벤트다. 이 줄 자체에는 원인이 없고, "
        "왜 죽었는지는 컨테이너 로그에 있다. 최근 쿠버네티스는 뒤에 파드 이름이 "
        "함께 붙어 나온다.",
    ),
    (
        "ops-oomkilled",
        "OOMKilled",
        "OOMKilled (메모리 부족으로 강제 종료됨)",
        ERROR, OPS, N, "kubectl describe pod 의 Last State",
        "메모리 한도를 넘어 강제 종료됐다는 뜻이다. 종료 코드는 137 로 찍힌다. "
        "애플리케이션 로그에는 아무것도 남지 않고 그냥 끊긴 것처럼 보이는 것이 "
        "특징이라, 코드에서 원인을 찾다 시간을 버리기 쉽다.",
    ),
    (
        "ops-insufficient-cpu",
        "0/3 nodes are available: 3 Insufficient cpu.",
        "3개 노드 중 0개 사용 가능: 3개 노드의 CPU 부족.",
        ERROR, OPS, H, "파드가 Pending 상태로 멈춰 있을 때",
        "요청한 자원을 줄 수 있는 노드가 없어 배치되지 못했다는 뜻이다. "
        "실제 사용량이 아니라 요청량 기준으로 계산하므로, 실제로는 여유가 있어도 "
        "요청값을 크게 잡아두면 이 상태가 된다.",
    ),
    (
        "ops-liveness-probe-failed",
        "Liveness probe failed: HTTP probe failed with statuscode: 500",
        "라이브니스 프로브 실패: HTTP 프로브가 상태 코드 500 으로 실패했습니다",
        ERROR, OPS, H, "kubectl describe pod 의 Events",
        "살아 있는지 확인하는 요청이 실패해 쿠버네티스가 컨테이너를 재시작한다는 "
        "뜻이다. 확인 경로가 데이터베이스까지 검사하도록 만들어두면, 일시적인 "
        "데이터베이스 지연에 애플리케이션이 통째로 재시작되는 문제가 생긴다.",
    ),
    (
        "ops-kubectl-connection-refused",
        "The connection to the server localhost:8080 was refused - did you specify the right host or port?",
        "서버 localhost:8080 연결이 거부되었습니다. 올바른 호스트와 포트를 지정했나요?",
        ERROR, OPS, N, "kubectl 명령을 실행할 때",
        "클러스터가 죽은 게 아니라 접속 설정을 찾지 못해 기본값으로 시도한 것이다. "
        "kubeconfig 파일이 없거나 컨텍스트가 선택되지 않은 경우가 대부분이라, "
        "localhost:8080 이라는 주소 자체가 단서다.",
    ),
    (
        "ops-nginx-bind-failed",
        "nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)",
        "nginx: [emerg] 0.0.0.0:80 바인딩 실패 (98: 주소가 이미 사용 중)",
        ERROR, OPS, N, "nginx 를 시작할 때",
        "80 포트를 이미 다른 프로세스가 쓰고 있다는 뜻이다. 98 은 리눅스의 "
        "주소 사용 중 번호다. 앞서 실행한 nginx 가 완전히 종료되지 않았거나 "
        "다른 웹 서버가 떠 있는 경우가 흔하다.",
    ),
    (
        "ops-command-not-found",
        "bash: kubectl: command not found",
        "bash: kubectl: 명령을 찾을 수 없습니다",
        ERROR, OPS, E, "터미널에서 명령을 실행할 때",
        "설치가 안 됐거나 설치는 됐는데 PATH 에 없다는 뜻이다. 스크립트 안에서 나면 "
        "앞에 스크립트 이름과 줄 번호가 붙고, 대화형 셸에서는 붙지 않는다. "
        "which 로 실제 위치를 확인하는 것이 먼저다.",
    ),
    (
        "ops-permission-denied-script",
        "bash: ./deploy.sh: Permission denied",
        "bash: ./deploy.sh: 권한이 거부되었습니다",
        ERROR, OPS, E, "스크립트를 실행할 때",
        "파일은 있는데 실행 권한이 없다는 뜻이다. chmod +x 로 권한을 주면 된다. "
        "git 은 실행 권한을 기록하므로, 저장소에 넣을 때 권한까지 커밋해두면 "
        "다른 사람이 같은 문제를 겪지 않는다.",
    ),
    (
        "ops-killed",
        "Killed",
        "강제 종료됨",
        ERROR, OPS, H, "명령이 아무 설명 없이 끝날 때",
        "메모리가 부족해 운영체제가 프로세스를 강제로 끝냈을 때 셸이 남기는 한 단어다. "
        "정보가 이것뿐이라 원인을 알 수 없어 보이지만, dmesg 나 시스템 로그에 "
        "어떤 프로세스가 얼마를 쓰다 죽었는지 자세히 남는다.",
    ),
    (
        "ops-host-key-verification-failed",
        "Host key verification failed.",
        "호스트 키 검증에 실패했습니다.",
        ERROR, OPS, N, "ssh 접속이 실패할 때",
        "이 줄만 보면 원인을 알 수 없고 그 위에 진짜 이유가 있다. 처음 접속하는 "
        "서버라 확인을 거부한 경우일 수도, 키가 바뀌어 경고가 뜬 경우일 수도 있다. "
        "서버를 새로 만들어 IP 를 재사용할 때 자주 만난다.",
    ),
    (
        "ops-remote-host-changed",
        "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!",
        "경고: 원격 호스트 식별 정보가 변경되었습니다!",
        ERROR, OPS, H, "ssh 접속을 시도할 때",
        "전에 접속하던 서버와 키가 다르다는 경고다. 정말 중간자 공격일 수도 있지만 "
        "실무에서는 서버를 새로 만들어 같은 주소를 다시 쓰는 경우가 훨씬 많다. "
        "known_hosts 에서 해당 줄만 지우면 되는데, 왜 바뀌었는지는 확인해야 한다.",
    ),
    (
        "ops-nginx-service-failed",
        "Job for nginx.service failed because the control process exited with error code.",
        "제어 프로세스가 오류 코드로 종료되어 nginx.service 작업이 실패했습니다.",
        ERROR, OPS, N, "systemctl 로 서비스를 시작할 때",
        "이 줄에는 원인이 없고 뒤이어 journalctl 을 보라는 안내가 붙는다. "
        "설정 파일 문법 오류나 포트 충돌이 대부분이라, nginx 라면 "
        "nginx -t 로 설정을 먼저 검사하는 것이 빠르다.",
    ),
    (
        "ops-errno-no-space-left",
        "OSError: [Errno 28] No space left on device: '/tmp/build'",
        "OS 오류: [Errno 28] 장치에 남은 공간이 없습니다: '/tmp/build'",
        ERROR, OPS, N, "파이썬이나 빌드 도구가 파일을 쓸 때",
        "위의 짧은 형태와 같은 원인인데 파이썬은 errno 번호와 경로까지 함께 보여준다. "
        "28 은 공간 부족 번호다. 루트 파티션이 아니라 임시 폴더나 별도 볼륨만 찬 "
        "경우가 많으므로 df 로 파티션별 사용량을 봐야 한다.",
    ),
    (
        "ops-readiness-probe-failed",
        "Readiness probe failed: Get \"http://10.1.2.3:8080/healthz\": dial tcp 10.1.2.3:8080: connect: connection refused",
        "레디니스 프로브 실패: \"http://10.1.2.3:8080/healthz\" 요청 실패: 10.1.2.3:8080 연결 거부됨",
        ERROR, OPS, H, "kubectl describe pod 의 Events",
        "아직 요청을 받을 준비가 안 됐다는 뜻이다. 라이브니스와 달리 재시작시키지 "
        "않고 트래픽만 보내지 않는다. 애플리케이션이 뜨는 데 시간이 걸리는 것이라면 "
        "확인 시작을 늦추는 설정으로 해결한다.",
    ),
    (
        "ops-exit-code-oom",
        "exited with code 137",
        "코드 137 로 종료됨",
        ERROR, OPS, H, "컨테이너 로그나 CI 출력",
        "137 은 128 에 강제 종료 신호 번호 9 를 더한 값이라 누군가 프로세스를 강제로 "
        "끝냈다는 뜻이다. 메모리 한도 초과가 흔하지만 docker stop 의 유예 시간이 "
        "지났거나 작업이 취소된 경우도 같은 값이 나오므로, OOMKilled 표시를 따로 "
        "확인해야 구분된다.",
    ),
    (
        "ops-certificate-expired",
        "curl: (60) SSL certificate problem: certificate has expired",
        "curl: (60) SSL 인증서 문제: 인증서가 만료되었습니다",
        ERROR, OPS, N, "터미널에서 HTTPS 주소를 호출할 때",
        "코드를 하나도 바꾸지 않았는데 어느 날 갑자기 전부 실패하는 대표적인 원인이다. "
        "인증서 갱신을 놓친 것이므로 애플리케이션에서 찾을 것이 없다. 예방은 자동 갱신을 "
        "걸어두는 것이고, 만료일 알림은 그 자동 갱신이 조용히 멈췄을 때를 대비한 "
        "이중 안전장치다.",
    ),
    (
        "ops-connection-timed-out",
        "ssh: connect to host 10.0.1.20 port 22: Connection timed out",
        "ssh: 호스트 10.0.1.20 의 22번 포트 연결 시간 초과",
        ERROR, OPS, N, "ssh 접속을 시도할 때",
        "연결 거부와 다르다. 거부는 즉시 오지만 이건 한참 기다린 뒤 난다. "
        "방화벽이나 보안 그룹이 패킷을 조용히 버리는 경우가 대표적이라, "
        "서버 상태보다 네트워크 규칙을 먼저 확인한다.",
    ),
    (
        "ops-git-authentication-failed",
        "fatal: Authentication failed for 'https://github.com/acme/private-repo.git/'",
        "치명적 오류: 'https://github.com/acme/private-repo.git/' 인증에 실패했습니다",
        ERROR, OPS, N, "CI 파이프라인 로그",
        "토큰이 만료됐거나 권한 범위가 부족하다는 뜻이다. 비밀번호 대신 토큰을 "
        "쓰도록 바뀐 뒤로는 대부분 토큰 만료가 원인이다. 주소 끝에 슬래시가 "
        "붙어 나오는 것이 git 의 출력 형식이다.",
    ),
    (
        "ops-npm-error-not-found",
        "npm error code E404",
        "npm 오류 코드 E404",
        ERROR, OPS, E, "npm install 실행 시",
        "패키지를 저장소에서 찾지 못했다는 뜻이다. 이름 오타이거나 비공개 패키지에 "
        "인증 없이 접근한 경우다. 접두사는 npm 버전에 따라 npm ERR! 로 나오기도 한다. "
        "옛 글이 다른 표기를 써도 같은 에러다.",
    ),

    # ---------- 디버깅 / 테스트 표현 ----------
    (
        "debug-repro-steps-request",
        "Can you share the exact steps to reproduce?",
        "재현하는 정확한 절차를 공유해 주실 수 있나요?",
        PHRASE, DEBUG, E, "버그 리포트에 답할 때",
        "안 믿는다는 뜻이 아니라 같은 상태를 만들지 못하면 고칠 수 없다는 뜻이다. "
        "어떤 계정, 어떤 데이터, 어떤 순서였는지까지 적어야 재현이 되고, "
        "여기까지 오면 고치는 것은 대개 시간 문제다.",
    ),
    (
        "debug-minimal-repro",
        "Could you trim it down to a minimal reproducible example?",
        "최소 재현 예제로 줄여 주실 수 있나요?",
        PHRASE, DEBUG, N, "코드가 너무 길 때",
        "관련 없는 부분을 걷어내고 문제만 남긴 짧은 코드를 달라는 뜻이다. "
        "줄이는 과정에서 원인을 스스로 찾는 경우가 많아서, 오픈소스에서는 "
        "이걸 요청 조건으로 두는 곳도 많다.",
    ),
    (
        "debug-can-you-attach-logs",
        "Can you attach the full stack trace, not just the last line?",
        "마지막 줄만 말고 전체 스택 트레이스를 첨부해 주실 수 있나요?",
        PHRASE, DEBUG, N, "에러 보고를 받았을 때",
        "마지막 줄은 문제가 드러난 곳일 뿐 원인이 있는 곳이 아니다. 어디서 시작해 "
        "어디를 거쳐 왔는지가 위쪽 줄에 있으므로 전체가 필요하다.",
    ),
    (
        "debug-works-on-my-machine",
        "It works on my machine, so it's probably environment-specific.",
        "제 컴퓨터에서는 되니 환경 문제일 가능성이 큽니다.",
        PHRASE, DEBUG, N, "재현이 안 될 때",
        "농담처럼 쓰이지만 진지하게 쓰면 환경 차이를 좁혀보자는 제안이다. "
        "버전, 운영체제, 설정값, 데이터 양 중 무엇이 다른지를 하나씩 맞춰가는 것이 "
        "다음 단계다.",
    ),
    (
        "debug-gut-feeling",
        "My hunch is the cache, but I haven't confirmed it yet.",
        "제 감으로는 캐시 같은데 아직 확인은 못 했습니다.",
        PHRASE, DEBUG, N, "원인을 추정할 때",
        "hunch 는 근거는 약하지만 짚이는 데가 있다는 뜻이다. 확인 전이라고 밝히는 "
        "것이 중요한데, 추정이 사실처럼 퍼지면 다른 사람이 엉뚱한 곳을 파게 된다.",
    ),
    (
        "debug-narrow-it-down",
        "Let's narrow it down by disabling the cache first.",
        "먼저 캐시를 꺼서 범위를 좁혀 봅시다.",
        PHRASE, DEBUG, E, "원인을 찾아갈 때",
        "narrow down 은 후보를 줄여간다는 뜻이다. 한 번에 여러 가지를 바꾸면 무엇이 "
        "효과가 있었는지 알 수 없으므로 하나씩 끄고 확인하는 것이 원칙이다.",
    ),
    (
        "debug-flaky-test",
        "That test is flaky, it fails about one run in ten.",
        "그 테스트는 불안정합니다. 열 번에 한 번쯤 실패해요.",
        PHRASE, DEBUG, N, "CI 실패를 이야기할 때",
        "코드를 안 바꿨는데 될 때도 있고 안 될 때도 있다는 뜻이다. 방치하면 사람들이 "
        "실패를 그냥 다시 돌려버려서 진짜 실패까지 무시하게 되는 것이 진짜 문제다.",
    ),
    (
        "debug-add-more-logging",
        "Let's add logging around that call and wait for it to happen again.",
        "그 호출 주변에 로그를 추가하고 다시 발생하기를 기다립시다.",
        PHRASE, DEBUG, N, "재현이 안 되는 문제를 다룰 때",
        "지금 못 잡을 문제를 다음에는 잡을 수 있게 준비하자는 뜻이다. 드물게 나는 "
        "문제에 쓰는 현실적인 방법이고, 무엇을 남길지 미리 정해두지 않으면 "
        "다음에도 정보가 부족하다.",
    ),

    # ---------- 디버깅 / 에러 ----------
    (
        "debug-attribute-error-nonetype",
        "AttributeError: 'NoneType' object has no attribute 'get'",
        "속성 오류: 'NoneType' 객체에는 'get' 속성이 없습니다",
        ERROR, DEBUG, E, "파이썬 실행 중",
        "값이 있을 줄 알았던 자리가 비어 있었다는 뜻이다. 진짜 문제는 그 줄이 아니라 "
        "왜 None 이 왔는지에 있어서, 그 줄에 방어 코드를 넣고 끝내면 원인이 뒤로 밀린다. "
        "함수가 조용히 None 을 돌려주는 경로부터 찾아야 한다.",
    ),
    (
        "debug-index-out-of-range",
        "IndexError: list index out of range",
        "인덱스 오류: 리스트 인덱스가 범위를 벗어났습니다",
        ERROR, DEBUG, E, "파이썬 실행 중",
        "리스트에 없는 위치를 꺼내려 했다는 뜻이다. 목록이 빈 경우를 다루지 않은 "
        "것이 가장 흔하고, 반복 범위를 하나 잘못 잡은 경우가 그다음이다.",
    ),
    (
        "debug-key-error",
        "KeyError: 'user_id'",
        "키 오류: 'user_id'",
        ERROR, DEBUG, E, "파이썬에서 딕셔너리를 다룰 때",
        "그 키가 없다는 뜻이다. 외부 응답을 다룰 때는 필드가 항상 온다고 가정하면 "
        "안 되고, 없어도 되는 값이라면 get 으로 꺼내 기본값을 주는 편이 안전하다.",
    ),
    (
        "debug-invalid-literal-int",
        "ValueError: invalid literal for int() with base 10: 'abc'",
        "값 오류: 10진수 int() 에 대한 잘못된 리터럴: 'abc'",
        ERROR, DEBUG, E, "파이썬에서 문자열을 숫자로 바꿀 때",
        "숫자로 바꿀 수 없는 문자열이라는 뜻이다. 따옴표 안에 실제 값이 그대로 "
        "찍히므로 무엇이 들어왔는지 바로 알 수 있다. 빈 문자열일 때는 "
        "따옴표 두 개만 보인다.",
    ),
    (
        "debug-unsupported-operand",
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        "타입 오류: + 연산자가 'int' 와 'str' 타입을 지원하지 않습니다",
        ERROR, DEBUG, E, "파이썬 실행 중",
        "숫자와 문자열을 더하려 했다는 뜻이다. 입력값이나 환경 변수는 문자열로 오기 "
        "때문에, 숫자처럼 보여도 숫자가 아닌 경우가 많다. 순서를 바꾸면 문구가 "
        "can only concatenate str 로 달라져 다른 에러처럼 보이지만 같은 문제다.",
    ),
    (
        "debug-unbound-local",
        "UnboundLocalError: cannot access local variable 'count' where it is not associated with a value",
        "언바운드 로컬 오류: 값이 할당되지 않은 지역 변수 'count' 에 접근할 수 없습니다",
        ERROR, DEBUG, H, "파이썬 실행 중",
        "함수 안에서 그 이름에 값을 넣는 코드가 있으면, 파이썬은 그 이름을 통째로 "
        "지역 변수로 본다. 그래서 바깥에 같은 이름이 있어도 할당 전에 읽으면 이 에러가 난다. "
        "3.10 이하는 local variable 'count' referenced before assignment 로 찍혔다.",
    ),
    (
        "debug-recursion-error",
        "RecursionError: maximum recursion depth exceeded",
        "재귀 오류: 최대 재귀 깊이를 초과했습니다",
        ERROR, DEBUG, N, "파이썬 실행 중",
        "재귀가 멈추지 않았다는 뜻이다. 종료 조건이 없거나, 있어도 그 조건에 "
        "닿지 못하는 경우다. 한계를 늘리는 함수가 있지만 그건 문제를 미루는 것이고 "
        "결국 프로세스가 죽는다.",
    ),
    (
        "debug-indentation-error",
        "IndentationError: unexpected indent",
        "들여쓰기 오류: 예상치 못한 들여쓰기",
        ERROR, DEBUG, E, "파이썬 파일을 실행할 때",
        "들여쓰기가 앞줄과 맞지 않는다는 뜻이다. 파이썬은 들여쓰기가 문법이라 "
        "공백 하나 차이로도 난다. 코드를 복사해 붙였을 때 가장 흔하다.",
    ),
    (
        "debug-tab-error",
        "TabError: inconsistent use of tabs and spaces in indentation",
        "탭 오류: 들여쓰기에 탭과 공백이 섞여 있습니다",
        ERROR, DEBUG, N, "파이썬 파일을 실행할 때",
        "탭과 공백을 섞어 썼다는 뜻이다. 화면에서는 똑같이 보여서 눈으로 찾기 아주 "
        "어렵다. 에디터에서 공백 문자를 보이게 켜거나 자동 정리 도구를 쓰는 것이 "
        "확실한 해법이다.",
    ),
    (
        "debug-unicode-decode-error",
        "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte",
        "유니코드 디코드 오류: 'utf-8' 코덱이 0번 위치의 0xff 바이트를 디코드할 수 없습니다: 잘못된 시작 바이트",
        ERROR, DEBUG, H, "파일이나 응답을 읽을 때",
        "UTF-8 이 아닌 파일을 UTF-8 로 읽으려 했다는 뜻이다. 윈도우에서 저장한 "
        "CSV 나 이진 파일을 텍스트로 열었을 때 흔하다. 인코딩을 지정해 열거나 "
        "이진 모드로 읽어야 한다.",
    ),
    (
        "debug-object-not-json-serializable",
        "TypeError: Object of type datetime is not JSON serializable",
        "타입 오류: datetime 타입 객체는 JSON 으로 직렬화할 수 없습니다",
        ERROR, DEBUG, N, "파이썬에서 JSON 으로 바꿀 때",
        "날짜나 소수 같은 타입은 JSON 에 그대로 담을 수 없다는 뜻이다. 문자열로 "
        "바꿔주는 규칙을 직접 지정해야 한다. 응답을 만들 때 마지막 단계에서 "
        "터지는 경우가 많다.",
    ),
    (
        "debug-missing-positional-arg",
        "TypeError: create_user() missing 1 required positional argument: 'email'",
        "타입 오류: create_user() 에 필수 위치 인자 'email' 이 빠졌습니다",
        ERROR, DEBUG, E, "파이썬 실행 중",
        "함수가 요구하는 인자를 덜 넘겼다는 뜻이다. 어떤 이름의 인자가 빠졌는지까지 "
        "알려주므로 정보가 충분하다. 메서드에서 self 를 잘못 다뤘을 때도 "
        "인자 수가 어긋나 이 형태로 나온다.",
    ),
    (
        "debug-int-not-callable",
        "TypeError: 'int' object is not callable",
        "타입 오류: 'int' 객체는 호출할 수 없습니다",
        ERROR, DEBUG, N, "파이썬 실행 중",
        "함수처럼 괄호를 붙여 불렀는데 그 이름이 함수가 아니라는 뜻이다. "
        "list 나 sum 같은 내장 이름을 변수로 덮어쓴 경우가 대표적이라, "
        "그 이름을 어디서 대입했는지 찾는 것이 빠르다.",
    ),
    (
        "debug-cannot-read-properties",
        "TypeError: Cannot read properties of undefined (reading 'name')",
        "타입 오류: undefined 의 속성을 읽을 수 없습니다 ('name' 읽기)",
        ERROR, DEBUG, E, "자바스크립트 실행 중",
        "값이 없는 대상에서 속성을 꺼내려 했다는 뜻이다. 괄호 안에 어떤 속성을 "
        "읽으려 했는지 나와서 위치를 좁히기 쉽다. 옛 브라우저는 "
        "Cannot read property 'name' of undefined 로 찍었다.",
    ),
    (
        "debug-not-a-function",
        "TypeError: data.map is not a function",
        "타입 오류: data.map 은 함수가 아닙니다",
        ERROR, DEBUG, N, "자바스크립트 실행 중",
        "배열인 줄 알았던 값이 배열이 아니라는 뜻이다. API 응답이 배열이 아니라 "
        "객체로 감싸여 오거나, 에러 응답이 와서 형태가 다른 경우가 대부분이다. "
        "그 값을 그대로 찍어보면 바로 확인된다.",
    ),
    (
        "debug-x-is-not-defined",
        "ReferenceError: config is not defined",
        "참조 오류: config 가 정의되지 않았습니다",
        ERROR, DEBUG, E, "자바스크립트 실행 중",
        "그런 이름이 아예 없다는 뜻이다. 오타이거나 import 를 빠뜨린 경우다. "
        "값이 비어 있다는 뜻의 undefined 와는 다른 문제라, "
        "이건 이름 자체가 존재하지 않는다는 말이다.",
    ),
    (
        "debug-max-call-stack",
        "RangeError: Maximum call stack size exceeded",
        "범위 오류: 최대 호출 스택 크기를 초과했습니다",
        ERROR, DEBUG, N, "자바스크립트 실행 중",
        "파이썬의 재귀 오류에 해당한다. 직접 재귀를 쓰지 않았어도, 서로를 부르는 "
        "두 함수나 이벤트가 자기 자신을 다시 일으키는 구조에서도 난다.",
    ),
    (
        "debug-heap-out-of-memory",
        "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory",
        "치명적 오류: 힙 한도에 도달해 할당에 실패했습니다 - 자바스크립트 힙 메모리 부족",
        ERROR, DEBUG, H, "Node.js 빌드나 실행 중",
        "Node 가 쓸 수 있는 메모리 한도를 넘었다는 뜻이다. 큰 프로젝트를 빌드할 때 "
        "흔하다. 한도를 늘리는 옵션으로 넘길 수 있지만, 데이터를 한 번에 다 "
        "메모리에 올리는 코드가 원인인 경우도 많다. 옛 Node 는 "
        "Ineffective mark-compacts near heap limit 으로 시작했다.",
    ),
    (
        "debug-cannot-find-module",
        "Error: Cannot find module 'express'",
        "오류: 'express' 모듈을 찾을 수 없습니다",
        ERROR, DEBUG, E, "Node.js 실행 중",
        "설치가 안 됐거나 다른 폴더에서 실행 중이라는 뜻이다. 컨테이너에서는 "
        "빌드할 때는 설치했는데 실행 이미지에 복사되지 않은 경우가 흔하다. "
        "직접 만든 파일 경로라면 대소문자도 확인해야 한다.",
    ),
    (
        "debug-require-not-defined-esm",
        "ReferenceError: require is not defined in ES module scope, you can use import instead",
        "참조 오류: ES 모듈 범위에서는 require 가 정의되지 않습니다. import 를 쓸 수 있습니다",
        ERROR, DEBUG, H, "Node.js 실행 중",
        "package.json 에 type 이 module 로 되어 있어 그 파일이 ES 모듈로 해석됐다는 "
        "뜻이다. 코드가 틀린 게 아니라 모듈 방식이 섞인 것이라, 파일 확장자를 "
        ".cjs 로 바꾸거나 import 문법으로 통일해야 한다.",
    ),
    (
        "debug-circular-structure-json",
        "TypeError: Converting circular structure to JSON",
        "타입 오류: 순환 구조를 JSON 으로 변환하려 했습니다",
        ERROR, DEBUG, H, "자바스크립트에서 JSON 으로 바꿀 때",
        "객체가 자기 자신을 다시 참조해 끝없이 파고들게 된다는 뜻이다. "
        "요청 객체나 DOM 요소를 통째로 로그에 찍으려 할 때 자주 난다. "
        "필요한 필드만 골라 담으면 해결된다.",
    ),
    (
        "debug-assignment-to-constant",
        "TypeError: Assignment to constant variable.",
        "타입 오류: 상수 변수에 대입했습니다.",
        ERROR, DEBUG, E, "자바스크립트 실행 중",
        "const 로 선언한 이름에 다시 대입했다는 뜻이다. 다만 const 는 그 이름이 "
        "가리키는 대상을 못 바꾸게 할 뿐이라, 배열에 항목을 넣거나 객체 속성을 "
        "고치는 것은 막지 않는다.",
    ),
    (
        "debug-segmentation-fault",
        "Segmentation fault (core dumped)",
        "세그멘테이션 오류 (코어 덤프됨)",
        ERROR, DEBUG, H, "컴파일된 프로그램이 죽을 때",
        "접근하면 안 되는 메모리를 건드려 운영체제가 강제 종료시켰다는 뜻이다. "
        "문제가 드러난 지점과 실제 원인이 멀리 떨어져 있는 경우가 많다. "
        "파이썬에서 이게 나면 대개 C 로 짜인 확장 라이브러리 쪽 문제다.",
    ),
    (
        "debug-pytest-assert-fail",
        "E       assert 200 == 404",
        "E       assert 200 == 404",
        ERROR, DEBUG, E, "pytest 실행 출력",
        "pytest 가 assert 문을 분석해 양쪽의 실제 값을 대신 보여준 것이라 메시지를 "
        "따로 적지 않아도 된다. 어느 쪽이 기대값인지는 정해진 규칙이 아니라 "
        "작성자가 쓴 순서일 뿐이다. 맨 앞의 E 는 실패한 줄이라는 표시다.",
    ),
    (
        "debug-pytest-failed-summary",
        "FAILED tests/test_user.py::test_create_user - AssertionError",
        "실패 tests/test_user.py::test_create_user - AssertionError",
        ERROR, DEBUG, E, "pytest 실행 출력 맨 아래",
        "실행이 끝난 뒤 실패한 테스트만 모아 보여주는 요약 줄이다. 파일과 함수 "
        "이름을 그대로 복사해 그 테스트만 다시 돌릴 수 있다. "
        "출력이 길 때 여기부터 보면 빠르다.",
    ),
    (
        "debug-jest-exceeded-timeout",
        "Exceeded timeout of 5000 ms for a test.",
        "테스트 제한 시간 5000ms 를 초과했습니다.",
        ERROR, DEBUG, N, "Jest 테스트 실행 중",
        "비동기 테스트가 시간 안에 끝나지 않았다는 뜻이다. 코드가 느린 게 아니라 "
        "await 를 빠뜨렸거나 프로미스를 돌려주지 않은 경우가 대부분이라, "
        "제한 시간만 늘리면 그만큼 더 기다렸다가 똑같이 실패한다.",
    ),
    (
        "debug-jest-did-not-exit",
        "Jest did not exit one second after the test run has completed.",
        "테스트 실행이 끝난 뒤 1초가 지나도 Jest 가 종료되지 않았습니다.",
        ERROR, DEBUG, H, "Jest 테스트가 끝난 뒤",
        "테스트는 통과했지만 정리되지 않은 것이 남아 프로세스가 안 끝난다는 뜻이다. "
        "닫지 않은 데이터베이스 연결이나 타이머가 원인이다. CI 에서 테스트가 "
        "영원히 안 끝나는 문제의 주요 원인이기도 하다.",
    ),
    (
        "debug-module-not-found-jest",
        "Cannot find module './utils' from 'src/app.test.js'",
        "'src/app.test.js' 에서 './utils' 모듈을 찾을 수 없습니다",
        ERROR, DEBUG, N, "Jest 테스트 실행 중",
        "어느 파일에서 무엇을 찾다 실패했는지 둘 다 나온다. 경로 별칭을 쓰는 "
        "프로젝트에서 Jest 설정에만 그 별칭을 등록하지 않은 경우가 흔하다. "
        "빌드는 되는데 테스트만 깨진다면 이쪽을 의심한다.",
    ),
    (
        "debug-deprecation-warning",
        "DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).",
        "폐기 경고: datetime.datetime.utcnow() 는 폐기되었으며 향후 버전에서 제거될 예정입니다. UTC 시각은 시간대 정보를 가진 객체로 표현하세요: datetime.datetime.now(datetime.UTC).",
        ERROR, DEBUG, N, "파이썬 3.12 이상에서 실행할 때",
        "지금은 동작하지만 앞으로 사라진다는 예고다. utcnow 가 돌려주는 값에 "
        "시간대 정보가 없어 UTC 인지 알 수 없다는 것이 폐기 이유다. "
        "경고를 무시해도 당장은 문제가 없어 쌓이기 쉬운데, 버전을 올릴 때 한꺼번에 터진다.",
    ),
    (
        "debug-address-already-in-use",
        "OSError: [Errno 98] Address already in use",
        "OS 오류: [Errno 98] 주소가 이미 사용 중입니다",
        ERROR, DEBUG, E, "개발 서버를 시작할 때",
        "그 포트를 이미 다른 프로세스가 쓰고 있다는 뜻이다. 앞서 띄운 서버가 제대로 "
        "종료되지 않고 남아 있는 경우가 대부분이다. 98 은 리눅스의 주소 사용 중 번호다.",
    ),

    # ---------- 프론트엔드 표현 ----------
    (
        "front-extract-component",
        "This component is doing too much, can we split it?",
        "이 컴포넌트가 너무 많은 일을 합니다. 나눌 수 있을까요?",
        PHRASE, FRONT, E, "컴포넌트 리뷰 코멘트",
        "재사용을 위해서가 아니라 읽기 어려워서 나누자는 제안인 경우가 많다. "
        "화면 조각으로 자르는 것보다 데이터 가져오기와 보여주기를 분리하는 쪽이 "
        "대개 더 효과가 크다.",
    ),
    (
        "front-lift-state-up",
        "Let's lift this state up to the parent.",
        "이 상태를 부모로 끌어올립시다.",
        PHRASE, FRONT, N, "상태 관리를 논의할 때",
        "lift up 은 상태를 더 위쪽 컴포넌트로 옮긴다는 뜻이다. 형제 컴포넌트끼리 "
        "같은 값을 봐야 할 때 쓰는 기본 해법이고, 너무 위로 올리면 "
        "관련 없는 곳까지 다시 그려지므로 정도가 중요하다.",
    ),
    (
        "front-prop-drilling-flag",
        "This prop is drilled through four levels, let's use context.",
        "이 prop 이 네 단계를 거쳐 내려갑니다. 컨텍스트를 씁시다.",
        PHRASE, FRONT, H, "컴포넌트 구조를 리뷰할 때",
        "중간 컴포넌트들이 쓰지도 않는 값을 계속 받아 넘긴다는 지적이다. "
        "다만 컨텍스트도 공짜가 아니라 값이 바뀌면 구독하는 곳이 전부 다시 그려지므로, "
        "두세 단계 정도면 그냥 두는 편이 낫다.",
    ),
    (
        "front-memo-only-if-needed",
        "Let's not memoize this until we measure it.",
        "측정하기 전에는 메모이제이션하지 맙시다.",
        PHRASE, FRONT, H, "성능 최적화를 논의할 때",
        "비교하고 기억하는 것도 비용이라 가벼운 계산에 붙이면 오히려 손해다. "
        "느린지 재보지도 않고 미리 최적화하지 말자는 원칙을 프론트에 적용한 말이다.",
    ),
    (
        "front-div-should-be-button",
        "This div should be a button for keyboard users.",
        "키보드 사용자를 위해 이 div 는 button 이어야 합니다.",
        PHRASE, FRONT, N, "접근성 지적",
        "div 에 클릭 이벤트만 붙이면 마우스로는 되지만 탭으로 이동하거나 "
        "엔터로 누를 수 없다. 실제 button 을 쓰면 그 동작이 전부 따라온다는 것이 "
        "이 지적의 핵심이다.",
    ),
    (
        "front-alt-text",
        "The image needs alt text, or an empty alt if it's decorative.",
        "이미지에 대체 텍스트가 필요합니다. 장식용이면 빈 alt 를 넣으세요.",
        PHRASE, FRONT, N, "접근성 지적",
        "alt 를 아예 빼는 것과 빈 값으로 두는 것은 다르다. 빼면 화면 낭독기가 "
        "파일 이름을 읽어버리고, 빈 값으로 두면 장식이라고 판단해 건너뛴다.",
    ),
    (
        "front-loading-state",
        "What does this look like while it's loading?",
        "로딩 중일 때는 어떻게 보이나요?",
        PHRASE, FRONT, E, "화면 구현을 리뷰할 때",
        "데이터가 오기 전 상태를 다루지 않으면 빈 화면이나 깨진 배치가 잠깐 보인다. "
        "로딩과 에러, 빈 목록 세 가지를 함께 묻는 것이 리뷰의 기본 점검 항목이다.",
    ),
    (
        "front-bundle-size-concern",
        "That library adds 200KB to the bundle, is it worth it?",
        "그 라이브러리는 번들을 200KB 늘립니다. 그만한 가치가 있나요?",
        PHRASE, FRONT, N, "의존성 추가를 리뷰할 때",
        "기능이 아니라 비용을 묻는 질문이다. 첫 화면에 필요 없다면 나중에 불러오도록 "
        "나누는 것이 대안이라, 빼자는 결론으로 갈 필요는 없다.",
    ),

    # ---------- 프론트엔드 에러 ----------
    (
        "front-key-prop-warning",
        "Warning: Each child in a list should have a unique \"key\" prop.",
        "경고: 목록의 각 자식은 고유한 \"key\" prop 을 가져야 합니다.",
        ERROR, FRONT, N, "React 개발 모드 콘솔",
        "화면은 그려지므로 무시하기 쉬운데, 항목을 지우거나 순서를 바꿀 때 엉뚱한 "
        "항목이 남거나 입력값이 뒤섞이는 버그로 이어진다. 배열 인덱스가 아니라 "
        "데이터 고유 아이디를 써야 한다. React 19 부터는 앞의 Warning: 이 사라졌다.",
    ),
    (
        "front-hydration-failed",
        "Hydration failed because the initial UI does not match what was rendered on the server.",
        "서버에서 렌더링된 결과와 초기 UI 가 일치하지 않아 하이드레이션에 실패했습니다.",
        ERROR, FRONT, H, "React 18 또는 Next.js 콘솔",
        "서버가 그린 HTML 과 브라우저가 그린 결과가 다르다는 뜻이다. 날짜나 난수처럼 "
        "매번 달라지는 값, window 를 보고 분기하는 코드가 대표적인 원인이다. "
        "React 19 는 문구가 완전히 바뀌어 the server rendered HTML didn't match the client 로 나온다.",
    ),
    (
        "front-text-content-mismatch",
        "Warning: Text content did not match. Server: \"3\" Client: \"4\"",
        "경고: 텍스트 내용이 일치하지 않습니다. 서버: \"3\" 클라이언트: \"4\"",
        ERROR, FRONT, H, "React 18 개발 모드 콘솔",
        "어느 값이 어긋났는지 양쪽을 나란히 보여주므로 원인을 찾기 가장 좋은 형태다. "
        "시각이나 상대 시간 표시가 서버와 브라우저에서 다르게 계산돼 나는 경우가 많다. "
        "React 19 에서는 이 메시지 자체가 제거됐다.",
    ),
    (
        "front-cannot-update-while-rendering",
        "Warning: Cannot update a component (`Parent`) while rendering a different component (`Child`).",
        "경고: 다른 컴포넌트(`Child`) 를 렌더링하는 중에 컴포넌트(`Parent`) 를 갱신할 수 없습니다.",
        ERROR, FRONT, H, "React 개발 모드 콘솔",
        "그리는 도중에 다른 컴포넌트의 상태를 바꿨다는 뜻이다. 대개 이벤트 핸들러를 "
        "넘겨야 할 자리에 함수를 즉시 호출해버린 실수다. 괄호를 빼고 함수 자체를 "
        "넘기면 해결되는 경우가 많다.",
    ),
    (
        "front-maximum-update-depth",
        "Maximum update depth exceeded. This can happen when a component calls setState inside useEffect, but useEffect either doesn't have a dependency array, or one of the dependencies changes on every render.",
        "최대 갱신 깊이를 초과했습니다. useEffect 안에서 setState 를 호출하는데 의존성 배열이 없거나 의존성 중 하나가 렌더링마다 바뀔 때 발생할 수 있습니다.",
        ERROR, FRONT, H, "React 콘솔",
        "상태 변경이 다시 렌더링을 일으키고 그것이 또 상태를 바꾸는 무한 고리다. "
        "메시지가 원인까지 친절하게 알려주는 드문 경우다. 의존성 배열에 매번 새로 "
        "만들어지는 객체나 배열이 들어 있는지부터 확인한다.",
    ),
    (
        "front-objects-not-valid-child",
        "Objects are not valid as a React child (found: object with keys {name, email}).",
        "객체는 React 자식으로 사용할 수 없습니다 (발견: {name, email} 키를 가진 객체).",
        ERROR, FRONT, N, "React 콘솔",
        "화면에 그리려는 자리에 객체를 그대로 넣었다는 뜻이다. 어떤 키를 가진 "
        "객체인지 알려주므로 어떤 데이터인지 바로 알 수 있다. 문자열로 바꾸거나 "
        "필요한 필드를 꺼내 넣어야 한다.",
    ),
    (
        "front-rendered-more-hooks",
        "Rendered more hooks than during the previous render.",
        "이전 렌더링보다 더 많은 훅이 실행되었습니다.",
        ERROR, FRONT, H, "React 콘솔",
        "훅을 조건문이나 반복문 안에서 불렀다는 뜻이다. React 는 훅을 이름이 아니라 "
        "호출 순서로 구분하기 때문에, 렌더링마다 개수가 달라지면 어느 상태가 "
        "어느 훅의 것인지 알 수 없게 된다. 조건은 훅 안쪽으로 옮겨야 한다.",
    ),
    (
        "front-invalid-hook-call",
        "Invalid hook call. Hooks can only be called inside of the body of a function component.",
        "잘못된 훅 호출입니다. 훅은 함수 컴포넌트 본문 안에서만 호출할 수 있습니다.",
        ERROR, FRONT, H, "React 콘솔",
        "규칙을 어긴 경우도 있지만, React 사본이 두 개 설치돼 있어 나는 경우가 "
        "의외로 많다. 메시지가 아래에 세 가지 가능성을 나열해주는 이유가 그것이다. "
        "직접 만든 라이브러리를 연결해 쓸 때 특히 자주 만난다.",
    ),
    (
        "front-react-hook-called-conditionally",
        "React Hook \"useEffect\" is called conditionally. React Hooks must be called in the exact same order in every component render.",
        "React 훅 \"useEffect\" 가 조건부로 호출됩니다. React 훅은 매 렌더링에서 정확히 같은 순서로 호출되어야 합니다.",
        ERROR, FRONT, N, "ESLint 검사 출력",
        "실행 전에 린터가 잡아주는 형태다. 위의 런타임 에러와 원인은 같지만 이쪽은 "
        "코드를 돌리기도 전에 나온다. 조건에 따라 일찍 return 하는 코드가 훅보다 "
        "앞에 있는 경우가 대부분이다.",
    ),
    (
        "front-window-is-not-defined",
        "ReferenceError: window is not defined",
        "참조 오류: window 가 정의되지 않았습니다",
        ERROR, FRONT, H, "Next.js 서버 렌더링 중",
        "서버에는 브라우저 객체가 없다는 뜻이다. 로컬에서 화면을 열 때는 "
        "브라우저에서만 실행돼 안 보이다가 빌드나 배포에서 터진다. "
        "그 코드를 마운트 이후로 옮기거나 브라우저에서만 불러오도록 나눠야 한다.",
    ),
    (
        "front-prerender-error",
        "Error occurred prerendering page \"/about\". Read more: https://nextjs.org/docs/messages/prerender-error",
        "\"/about\" 페이지를 사전 렌더링하는 중 오류가 발생했습니다. 자세한 내용: https://nextjs.org/docs/messages/prerender-error",
        ERROR, FRONT, N, "Next.js 빌드 로그",
        "어느 페이지에서 났는지 알려주는 감싸는 메시지일 뿐 원인은 그 아래에 있다. "
        "빌드 시점에 실행되는 코드라 브라우저 전용 객체나 외부 API 호출이 "
        "원인인 경우가 많다.",
    ),
    (
        "front-module-not-found-webpack",
        "Module not found: Error: Can't resolve './components/Header' in '/app/src'",
        "모듈을 찾을 수 없습니다: 오류: '/app/src' 에서 './components/Header' 를 확인할 수 없습니다",
        ERROR, FRONT, E, "webpack 빌드 중",
        "어디서 무엇을 찾다 실패했는지 둘 다 나온다. 맥에서는 되는데 리눅스 CI 에서만 "
        "깨진다면 대소문자 문제다. 맥의 파일 시스템은 대소문자를 구분하지 않기 때문이다.",
    ),
    (
        "front-vite-failed-to-resolve",
        "Failed to resolve import \"./utils/format\" from \"src/main.js\". Does the file exist?",
        "\"src/main.js\" 에서 \"./utils/format\" import 를 확인하지 못했습니다. 파일이 존재하나요?",
        ERROR, FRONT, E, "Vite 개발 서버 실행 중",
        "webpack 쪽과 같은 상황인데 Vite 는 큰따옴표를 쓰고 파일 존재 여부를 되묻는다. "
        "이 문구는 개발 서버 전용이고, 빌드에서는 Rollup 이 대신 "
        "Could not resolve 로 찍는다.",
    ),
    (
        "front-uncaught-syntaxerror-unexpected-token",
        "Uncaught SyntaxError: Unexpected token '<'",
        "처리되지 않은 구문 오류: 예기치 않은 토큰 '<'",
        ERROR, FRONT, H, "브라우저 콘솔",
        "자바스크립트 파일을 요청했는데 HTML 이 돌아왔다는 뜻이다. 정적 파일 경로가 "
        "틀려 404 페이지를 받아온 경우가 대부분이라, 코드가 아니라 배포 경로 설정을 "
        "봐야 한다.",
    ),
    (
        "front-css-not-loading-mime",
        "Refused to apply style from 'https://example.com/app.css' because its MIME type ('text/html') is not a supported stylesheet MIME type",
        "'https://example.com/app.css' 의 MIME 타입('text/html')이 지원되는 스타일시트 형식이 아니어서 스타일 적용이 거부되었습니다",
        ERROR, FRONT, H, "브라우저 콘솔",
        "위의 구문 오류와 같은 원인의 CSS 판이다. CSS 를 요청했는데 HTML 이 왔다는 뜻이라 "
        "파일이 없어서 404 페이지가 온 것이다. 스타일이 전혀 안 먹을 때 이 줄이 있는지 "
        "먼저 확인하면 빠르다.",
    ),
    (
        "front-not-a-function-map",
        "TypeError: items.map is not a function",
        "타입 오류: items.map 은 함수가 아닙니다",
        ERROR, FRONT, N, "브라우저 콘솔",
        "배열이 올 자리에 다른 것이 왔다는 뜻이다. 초기값을 빈 배열이 아니라 "
        "null 이나 undefined 로 둔 채 첫 렌더링에서 그리려 할 때 가장 흔하다. "
        "초기값을 빈 배열로 두면 대부분 사라진다.",
    ),
    (
        "front-cannot-read-props-of-null",
        "TypeError: Cannot read properties of null (reading 'value')",
        "타입 오류: null 의 속성을 읽을 수 없습니다 ('value' 읽기)",
        ERROR, FRONT, E, "브라우저 콘솔",
        "요소를 찾지 못한 채 그 값을 읽으려 했다는 뜻이다. 선택자가 틀렸거나, "
        "스크립트가 화면보다 먼저 실행돼 아직 그 요소가 없는 경우다. "
        "undefined 가 아니라 null 이라는 점이 대개 요소 조회 실패라는 단서다.",
    ),
    (
        "front-hooks-exhaustive-deps",
        "React Hook useEffect has a missing dependency: 'userId'. Either include it or remove the dependency array.",
        "React 훅 useEffect 에 'userId' 의존성이 빠졌습니다. 추가하거나 의존성 배열을 제거하세요.",
        ERROR, FRONT, N, "ESLint 검사 출력",
        "안에서 쓰는 값이 의존성 배열에 없다는 뜻이다. 그냥 넣으면 무한 반복이 되는 "
        "경우가 있어서 사람들이 경고를 끄곤 하는데, 그건 대개 그 값이 렌더링마다 "
        "새로 만들어진다는 신호라 그쪽을 고쳐야 한다.",
    ),
    (
        "front-uncontrolled-to-controlled",
        "Warning: A component is changing an uncontrolled input to be controlled.",
        "경고: 컴포넌트가 비제어 입력을 제어 입력으로 바꾸고 있습니다.",
        ERROR, FRONT, H, "React 개발 모드 콘솔",
        "입력의 value 가 처음에는 undefined 였다가 나중에 값이 들어왔다는 뜻이다. "
        "데이터를 비동기로 가져와 채울 때 흔하다. 초기값을 빈 문자열로 두면 해결된다.",
    ),
    (
        "front-cors-xhr-blocked",
        "Access to XMLHttpRequest at 'https://api.example.com/upload' from origin 'http://localhost:5173' has been blocked by CORS policy",
        "출처 'http://localhost:5173' 에서 'https://api.example.com/upload' 로의 XMLHttpRequest 가 CORS 정책에 의해 차단되었습니다",
        ERROR, FRONT, H, "브라우저 콘솔",
        "요청 종류에 따라 앞부분 단어가 fetch 가 아니라 XMLHttpRequest 로 나온다. "
        "axios 처럼 내부적으로 XHR 을 쓰는 라이브러리에서 이 형태를 본다. "
        "원인과 해법은 fetch 쪽과 같다.",
    ),
    (
        "front-chunk-load-error",
        "ChunkLoadError: Loading chunk 42 failed.",
        "청크 로드 오류: 청크 42 로딩에 실패했습니다.",
        ERROR, FRONT, H, "브라우저 콘솔",
        "코드를 나눠 나중에 받아오는 조각을 가져오지 못했다는 뜻이다. 사용자가 "
        "페이지를 열어둔 사이에 새 버전이 배포돼 옛 파일 이름이 사라진 경우가 "
        "대표적이다. 이 에러를 잡아 새로고침을 안내하는 것이 흔한 대응이다.",
    ),
    (
        "front-favicon-not-found",
        "GET http://localhost:3000/favicon.ico 404 (Not Found)",
        "GET http://localhost:3000/favicon.ico 404 (찾을 수 없음)",
        ERROR, FRONT, E, "브라우저 콘솔",
        "브라우저가 자동으로 아이콘 파일을 요청했는데 없다는 뜻이다. 기능에는 아무 "
        "영향이 없어서 무시해도 되는 대표적인 콘솔 메시지다. 다른 문제를 찾는 중에 "
        "이걸 원인으로 오해하지 않는 것이 중요하다.",
    ),
    (
        "front-uncaught-in-promise-typeerror",
        "Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'data')",
        "처리되지 않은 오류(프로미스): 타입 오류: undefined 의 속성을 읽을 수 없습니다 ('data' 읽기)",
        ERROR, FRONT, N, "브라우저 콘솔",
        "비동기 처리 안에서 난 에러를 아무도 잡지 않았다는 뜻이다. 앞의 "
        "in promise 가 붙으면 try 로 감싸도 안 잡히는 위치일 수 있으니 "
        "then 뒤의 catch 나 async 함수 안쪽을 확인해야 한다.",
    ),
    (
        "front-eslint-no-unused-vars",
        "'response' is assigned a value but never used  no-unused-vars",
        "'response' 에 값이 할당되었지만 사용되지 않습니다  no-unused-vars",
        ERROR, FRONT, E, "ESLint 검사 출력",
        "쓰지 않는 변수가 있다는 뜻이다. 지우면 되는 사소한 지적처럼 보이지만, "
        "결과를 받아놓고 안 쓰는 것이라면 로직이 빠진 신호일 수 있어 한 번은 "
        "확인해볼 가치가 있다.",
    ),
    (
        "front-ts-possibly-undefined",
        "TS2532: Object is possibly 'undefined'.",
        "TS2532: 객체가 'undefined' 일 수 있습니다.",
        ERROR, FRONT, N, "TypeScript 컴파일 중",
        "값이 없을 수도 있는데 확인 없이 썼다는 뜻이다. 느낌표로 강제로 넘길 수 있지만 "
        "그건 검사를 끈 것일 뿐 런타임 에러를 막아주지 않는다. 없을 때 어떻게 할지 "
        "코드로 적는 것이 맞는 대응이다.",
    ),
    (
        "front-ts-not-assignable",
        "TS2322: Type 'string' is not assignable to type 'number'.",
        "TS2322: 'string' 타입을 'number' 타입에 할당할 수 없습니다.",
        ERROR, FRONT, E, "TypeScript 컴파일 중",
        "왼쪽이 넣으려는 값의 타입이고 오른쪽이 받는 쪽의 타입이다. 순서를 반대로 "
        "읽으면 원인을 엉뚱하게 짚게 되므로 방향을 정확히 보는 것이 중요하다.",
    ),
    (
        "front-npm-eresolve",
        "npm error ERESOLVE unable to resolve dependency tree",
        "npm 오류 ERESOLVE 의존성 트리를 해결할 수 없습니다",
        ERROR, FRONT, H, "npm install 실행 시",
        "peer 의존성이 서로 부딪혀 설치할 조합을 못 찾았다는 뜻이다. "
        "리액트처럼 버전을 크게 올린 직후에 자주 본다. 이 줄 아래에 무엇과 무엇이 "
        "부딪히는지 나오므로 그 부분부터 읽는다.",
    ),

    # ---------- CS 기초 / 정보처리기사 ----------
    (
        "cs-time-complexity-log-n",
        "The time complexity of this operation is O(log n).",
        "이 연산의 시간 복잡도는 O(log n) 입니다.",
        PHRASE, CS, N, "알고리즘 설명 문서",
        "O 는 big O 라고 읽고 log n 은 log of n 이라고 읽는다. 실제 걸리는 시간이 "
        "아니라 입력이 커질 때 늘어나는 추세의 상한을 나타낸다는 점이 핵심이다.",
    ),
    (
        "cs-binary-search-sorted",
        "Binary search requires the array to be sorted beforehand.",
        "이진 탐색은 배열이 미리 정렬되어 있어야 합니다.",
        PHRASE, CS, E, "자료구조 교재",
        "beforehand 는 '미리, 사전에' 라는 뜻이다. 이 전제를 빼먹으면 알고리즘은 "
        "에러 없이 돌면서 틀린 답을 준다. 정처기에서 전제 조건을 묻는 문제로 자주 나온다.",
    ),
    (
        "cs-stack-lifo",
        "A stack follows the last-in, first-out principle.",
        "스택은 후입선출 원칙을 따릅니다.",
        PHRASE, CS, E, "자료구조 교재",
        "follow the principle 은 '그 원칙을 따른다' 는 정형 표현이다. 시험에서는 "
        "LIFO 라는 약자로 더 자주 나오고, 함수 호출이 이 방식으로 쌓이고 풀린다.",
    ),
    (
        "cs-queue-fifo",
        "Elements are dequeued in the order they were enqueued.",
        "요소는 넣은 순서대로 꺼내집니다.",
        PHRASE, CS, N, "자료구조 교재",
        "enqueue 와 dequeue 는 큐에 넣고 빼는 동작을 가리키는 전용 동사다. "
        "일반 영어 단어가 아니라 자료구조 용어이므로 사전에서 찾기보다 짝으로 외우는 편이 낫다.",
    ),
    (
        "cs-hash-collision",
        "When two keys hash to the same bucket, a collision occurs.",
        "두 키가 같은 버킷으로 해싱되면 충돌이 발생합니다.",
        PHRASE, CS, N, "자료구조 교재",
        "hash 가 동사로 쓰여 '해시값으로 바뀌어 어디로 간다' 는 뜻이 된다. "
        "충돌은 설계가 잘못돼서가 아니라 필연적으로 생기는 것이라, "
        "어떻게 처리하느냐가 성능을 좌우한다.",
    ),
    (
        "cs-recursion-base-case",
        "Every recursive function must have a base case to terminate.",
        "모든 재귀 함수에는 종료를 위한 기저 조건이 있어야 합니다.",
        PHRASE, CS, E, "알고리즘 교재",
        "base case 는 더 이상 자기를 부르지 않고 값을 돌려주는 조건이다. "
        "이게 없거나 닿지 못하면 스택이 넘쳐 프로그램이 죽는다.",
    ),
    (
        "cs-greedy-not-optimal",
        "A greedy algorithm does not always yield the optimal solution.",
        "탐욕 알고리즘이 항상 최적해를 주는 것은 아닙니다.",
        PHRASE, CS, H, "알고리즘 교재",
        "yield 는 여기서 '내놓다, 산출하다' 라는 뜻이다. not always 는 '항상 그런 것은 "
        "아니다' 로 부분 부정이라, 아예 안 된다는 뜻으로 읽으면 안 된다.",
    ),
    (
        "cs-dp-overlapping-subproblems",
        "Dynamic programming applies when subproblems overlap.",
        "동적 계획법은 부분 문제가 겹칠 때 적용됩니다.",
        PHRASE, CS, H, "알고리즘 교재",
        "apply 가 자동사로 쓰여 '적용된다, 해당된다' 는 뜻이 된다. 부분 문제가 "
        "겹치지 않으면 저장해둘 이유가 없어 분할 정복으로 충분하다는 것이 이 문장의 요지다.",
    ),
    (
        "cs-process-vs-thread",
        "Threads within a process share the same memory space.",
        "한 프로세스 안의 스레드들은 같은 메모리 공간을 공유합니다.",
        PHRASE, CS, N, "운영체제 교재",
        "정처기에서 프로세스와 스레드를 비교할 때 핵심이 되는 문장이다. "
        "공유하기 때문에 데이터를 주고받기 쉽고, 같은 이유로 경쟁 상태가 생긴다.",
    ),
    (
        "cs-mutual-exclusion",
        "A mutex ensures mutual exclusion for the critical section.",
        "뮤텍스는 임계 구역에 대한 상호 배제를 보장합니다.",
        PHRASE, CS, H, "운영체제 교재",
        "critical section 은 임계 구역, mutual exclusion 은 상호 배제로 번역된다. "
        "ensure 는 '보장한다' 는 뜻으로 기술 문서에서 아주 자주 쓰인다.",
    ),
    (
        "cs-deadlock-four-conditions",
        "Deadlock occurs only when all four conditions hold simultaneously.",
        "교착 상태는 네 가지 조건이 동시에 성립할 때만 발생합니다.",
        PHRASE, CS, H, "운영체제 교재",
        "hold 가 '성립하다' 라는 뜻으로 쓰였다. 조건 중 하나만 깨면 교착 상태를 "
        "막을 수 있다는 것이 예방 기법의 근거이고, 정처기 단골 문제다.",
    ),
    (
        "cs-context-switch-overhead",
        "Context switching introduces overhead that reduces throughput.",
        "문맥 교환은 처리량을 떨어뜨리는 부하를 발생시킵니다.",
        PHRASE, CS, H, "운영체제 교재",
        "introduce 가 '새로 발생시킨다' 는 뜻으로 쓰였다. 소개한다는 뜻이 아니다. "
        "스레드를 무작정 늘리면 오히려 느려지는 이유를 설명할 때 나오는 문장이다.",
    ),
    (
        "cs-page-fault",
        "A page fault occurs when the requested page is not in main memory.",
        "요청한 페이지가 주기억장치에 없으면 페이지 폴트가 발생합니다.",
        PHRASE, CS, H, "운영체제 교재",
        "fault 는 오류가 아니라 '없어서 가져와야 하는 상황' 을 뜻한다. 정상 동작의 "
        "일부이며, 이것이 지나치게 잦아지는 상태를 스래싱이라고 따로 부른다.",
    ),
    (
        "cs-virtual-memory",
        "Virtual memory allows a process to use more memory than is physically available.",
        "가상 메모리는 프로세스가 물리적으로 존재하는 것보다 많은 메모리를 쓸 수 있게 합니다.",
        PHRASE, CS, N, "운영체제 교재",
        "allow A to B 는 'A 가 B 할 수 있게 한다' 는 구조다. than is available 처럼 "
        "than 뒤에 주어가 생략되는 형태는 기술 문서에서 흔하다.",
    ),
    (
        "cs-scheduling-starvation",
        "Low-priority processes may starve under priority scheduling.",
        "우선순위 스케줄링에서는 낮은 우선순위 프로세스가 기아 상태에 빠질 수 있습니다.",
        PHRASE, CS, H, "운영체제 교재",
        "starve 는 굶는다는 뜻으로, 순서가 계속 밀려 영영 실행되지 못하는 상태를 "
        "가리킨다. 기다리는 시간에 따라 우선순위를 올려주는 방식으로 해결한다.",
    ),
    (
        "cs-tcp-reliable",
        "TCP guarantees reliable, ordered delivery of a byte stream.",
        "TCP 는 바이트 스트림의 신뢰성 있고 순서가 보장된 전달을 보장합니다.",
        PHRASE, CS, N, "네트워크 교재",
        "reliable 과 ordered 두 가지를 나란히 든 것이 핵심이다. 빠지지 않는다는 것과 "
        "순서가 지켜진다는 것은 별개의 보장이고, UDP 는 둘 다 하지 않는다.",
    ),
    (
        "cs-three-way-handshake",
        "A TCP connection is established through a three-way handshake.",
        "TCP 연결은 3방향 핸드셰이크를 통해 수립됩니다.",
        PHRASE, CS, N, "네트워크 교재",
        "establish 는 연결을 '수립한다' 는 뜻의 정형 동사다. 세 단계는 SYN, SYN-ACK, "
        "ACK 순서이고, 정처기에서 순서를 묻는 문제로 나온다.",
    ),
    (
        "cs-osi-seven-layers",
        "The OSI model divides network communication into seven layers.",
        "OSI 모델은 네트워크 통신을 일곱 계층으로 나눕니다.",
        PHRASE, CS, N, "네트워크 교재",
        "divide A into B 는 'A 를 B 로 나눈다' 는 구조다. 실제 인터넷은 더 단순한 "
        "TCP/IP 구조로 도는데도 이 모델을 배우는 이유는, 문제를 어느 층에서 찾을지 "
        "말할 때 공통 언어가 되기 때문이다.",
    ),
    (
        "cs-dns-resolves",
        "DNS resolves a domain name to an IP address.",
        "DNS 는 도메인 이름을 IP 주소로 변환합니다.",
        PHRASE, CS, E, "네트워크 교재",
        "resolve A to B 는 'A 를 확인해 B 로 바꾼다' 는 뜻이다. 에러 메시지에서 "
        "could not resolve host 로 자주 만나므로 이 동사를 알아두면 도움이 된다.",
    ),
    (
        "cs-subnet-mask",
        "The subnet mask determines which portion of the address identifies the network.",
        "서브넷 마스크는 주소의 어느 부분이 네트워크를 식별하는지 결정합니다.",
        PHRASE, CS, H, "네트워크 교재",
        "determine 은 '결정한다', identify 는 '식별한다' 는 뜻으로 둘 다 기술 문서의 "
        "기본 동사다. 정처기에서 서브넷 계산 문제로 자주 출제된다.",
    ),
    (
        "cs-symmetric-vs-asymmetric",
        "Symmetric encryption uses the same key for both encryption and decryption.",
        "대칭 암호화는 암호화와 복호화에 같은 키를 사용합니다.",
        PHRASE, CS, N, "보안 교재",
        "encryption 은 암호화, decryption 은 복호화다. 반대말이 en- 과 de- 접두사로 "
        "갈린다는 점을 알아두면 비슷한 단어들을 함께 익힐 수 있다.",
    ),
    (
        "cs-hashing-one-way",
        "Hashing is a one-way function; the original value cannot be recovered.",
        "해싱은 단방향 함수이므로 원래 값을 복원할 수 없습니다.",
        PHRASE, CS, N, "보안 교재",
        "one-way 는 되돌릴 수 없다는 뜻이고, 이것이 암호화와의 결정적인 차이다. "
        "비밀번호를 암호화가 아니라 해시로 저장하는 이유가 여기 있다.",
    ),
    (
        "cs-sql-injection-prevention",
        "Parameterized queries prevent SQL injection by separating code from data.",
        "매개변수화된 쿼리는 코드와 데이터를 분리해 SQL 삽입을 방지합니다.",
        PHRASE, CS, H, "보안 교재",
        "prevent A by B 는 'B 함으로써 A 를 막는다' 는 구조다. 특수문자를 걸러내는 "
        "방식은 빠져나갈 구멍이 많아서, 근본 해법은 값을 코드와 아예 분리하는 것이다.",
    ),
    (
        "cs-normalization-redundancy",
        "Normalization reduces data redundancy and improves data integrity.",
        "정규화는 데이터 중복을 줄이고 무결성을 향상시킵니다.",
        PHRASE, CS, N, "데이터베이스 교재",
        "redundancy 는 중복, integrity 는 무결성으로 정처기 필수 용어다. "
        "정규화의 목적을 묻는 문제의 답이 대개 이 문장 그대로다.",
    ),
    (
        "cs-acid-properties",
        "A transaction must satisfy the ACID properties to be considered reliable.",
        "트랜잭션이 신뢰할 수 있으려면 ACID 속성을 만족해야 합니다.",
        PHRASE, CS, H, "데이터베이스 교재",
        "satisfy 는 조건을 '만족한다' 는 뜻이고 property 는 성질을 뜻한다. "
        "ACID 는 원자성, 일관성, 고립성, 지속성의 앞 글자이며 '애시드' 로 읽는다.",
    ),
    (
        "cs-cohesion-coupling-goal",
        "Aim for high cohesion and low coupling.",
        "높은 응집도와 낮은 결합도를 목표로 하세요.",
        PHRASE, CS, N, "소프트웨어 공학 교재",
        "aim for 는 '~를 목표로 하다' 라는 뜻이다. 정처기에서 모듈화 원칙으로 나오고 "
        "실무 코드 리뷰에서도 같은 표현을 그대로 쓴다.",
    ),

    # ---------- Java 런타임 에러 ----------
    (
        "java-npe-helpful-field",
        "Exception in thread \"main\" java.lang.NullPointerException: Cannot invoke \"String.length()\" because \"T.s\" is null",
        "메인 스레드 예외: 널 포인터 예외: \"T.s\" 가 null 이라 \"String.length()\" 를 호출할 수 없습니다",
        ERROR, DEBUG, E, "자바 실행 중",
        "자바 15 부터 어느 값이 null 이었는지까지 기본으로 알려준다. 14 에 들어왔지만 "
        "그때는 옵션을 켜야 했다. 예전에는 줄 번호만 나와서 한 줄에 여러 호출이 있으면 "
        "어느 것이 null 인지 찾아야 했다. "
        "because 뒤가 진짜 정보이므로 그 부분을 봐야 한다.",
    ),
    (
        "java-npe-return-value",
        "Exception in thread \"main\" java.lang.NullPointerException: Cannot invoke \"String.trim()\" because the return value of \"java.util.Map.get(Object)\" is null",
        "메인 스레드 예외: 널 포인터 예외: \"java.util.Map.get(Object)\" 의 반환값이 null 이라 \"String.trim()\" 을 호출할 수 없습니다",
        ERROR, DEBUG, N, "자바 실행 중",
        "Map 에서 찾은 값이 없어 null 이 돌아왔다는 뜻이다. 키가 없는 것이지 Map 이 "
        "null 인 것이 아니라는 점이 중요하다. getOrDefault 를 쓰거나 없을 때의 처리를 "
        "따로 적어야 한다.",
    ),
    (
        "java-class-cast-exception",
        "Exception in thread \"main\" java.lang.ClassCastException: class java.lang.String cannot be cast to class java.lang.Integer",
        "메인 스레드 예외: 클래스 캐스트 예외: java.lang.String 을 java.lang.Integer 로 변환할 수 없습니다",
        ERROR, DEBUG, N, "자바 실행 중",
        "실제 타입과 다른 타입으로 강제 변환했다는 뜻이다. 제네릭 없이 쓰는 옛 컬렉션이나 "
        "Object 로 받아온 값을 다룰 때 난다. 뒤에 두 클래스가 어느 모듈의 어느 로더에 "
        "속하는지도 함께 나오는데, 같은 이름인데 로더가 다르면 그것도 원인이 된다.",
    ),
    (
        "java-array-index-out-of-bounds",
        "Exception in thread \"main\" java.lang.ArrayIndexOutOfBoundsException: Index 5 out of bounds for length 3",
        "메인 스레드 예외: 배열 인덱스 범위 초과 예외: 길이 3 인 배열에서 인덱스 5",
        ERROR, DEBUG, E, "자바 실행 중",
        "요청한 인덱스와 실제 길이를 둘 다 보여주므로 얼마나 벗어났는지 바로 알 수 있다. "
        "반복 조건을 부등호로 잘못 잡은 하나 차이 실수가 가장 흔한 원인이다.",
    ),
    (
        "java-number-format-exception",
        "Exception in thread \"main\" java.lang.NumberFormatException: For input string: \"abc\"",
        "메인 스레드 예외: 숫자 형식 예외: 입력 문자열 \"abc\"",
        ERROR, DEBUG, E, "문자열을 숫자로 바꿀 때",
        "따옴표 안에 실제로 들어온 값이 그대로 찍힌다. 빈 문자열이면 따옴표 두 개만 "
        "보이고, 공백이 섞였을 때도 실패하므로 앞뒤 공백을 먼저 지우는 것이 좋다.",
    ),
    (
        "java-arithmetic-divide-by-zero",
        "Exception in thread \"main\" java.lang.ArithmeticException: / by zero",
        "메인 스레드 예외: 산술 예외: 0 으로 나눔",
        ERROR, DEBUG, E, "자바 실행 중",
        "정수를 0 으로 나눴다는 뜻이다. 실수형은 예외 대신 Infinity 나 NaN 을 돌려주기 "
        "때문에 조용히 넘어가는데, 그편이 오히려 찾기 어려운 버그가 된다.",
    ),
    (
        "java-concurrent-modification",
        "Exception in thread \"main\" java.util.ConcurrentModificationException",
        "메인 스레드 예외: 동시 수정 예외",
        ERROR, DEBUG, H, "컬렉션을 순회하면서 수정할 때",
        "이름과 달리 멀티스레드와 상관없이 한 스레드에서도 난다. 반복문으로 돌면서 "
        "목록에서 항목을 지우면 바로 이것이다. Iterator 의 remove 를 쓰거나 "
        "removeIf 로 바꾸면 해결된다. 메시지에 아무 설명이 없는 것이 특징이다.",
    ),
    (
        "java-stack-overflow-error",
        "Exception in thread \"main\" java.lang.StackOverflowError",
        "메인 스레드 예외: 스택 오버플로 오류",
        ERROR, DEBUG, N, "자바 실행 중",
        "재귀가 멈추지 않았다는 뜻이다. Exception 이 아니라 Error 라 잡아서 넘기면 안 된다. "
        "스택 트레이스에 같은 메서드가 수천 번 반복돼 나오므로 어느 함수인지는 쉽게 보인다.",
    ),
    (
        "java-out-of-memory-heap",
        "Exception in thread \"main\" java.lang.OutOfMemoryError: Java heap space",
        "메인 스레드 예외: 메모리 부족 오류: 자바 힙 공간",
        ERROR, DEBUG, H, "자바 애플리케이션 로그",
        "힙이 부족하다는 뜻이다. -Xmx 로 늘릴 수 있지만 대개는 한 번에 너무 많은 행을 "
        "가져오거나 캐시가 계속 커지는 코드가 원인이다. 컨테이너에서는 컨테이너 한도와 "
        "힙 설정을 함께 맞추지 않으면 힙이 남았는데도 OOMKilled 로 죽는다.",
    ),
    (
        "java-unsupported-operation",
        "Exception in thread \"main\" java.lang.UnsupportedOperationException",
        "메인 스레드 예외: 지원되지 않는 연산 예외",
        ERROR, DEBUG, N, "리스트를 수정할 때",
        "List.of 나 Arrays.asList 로 만든 목록은 크기를 바꿀 수 없다는 뜻이다. "
        "메시지가 비어 있어 원인을 알기 어려운데, 수정하려는 컬렉션이 어떻게 만들어졌는지 "
        "거슬러 올라가면 대부분 여기서 끝난다.",
    ),
    (
        "java-no-such-element-optional",
        "Exception in thread \"main\" java.util.NoSuchElementException: No value present",
        "메인 스레드 예외: 요소 없음 예외: 값이 없습니다",
        ERROR, DEBUG, N, "Optional 을 다룰 때",
        "값이 없는 Optional 에 get 을 불렀다는 뜻이다. null 검사를 안 하려고 Optional 을 "
        "썼는데 get 을 그냥 부르면 결국 같은 문제가 된다. orElse 나 orElseThrow 로 "
        "없을 때의 처리를 적어야 한다.",
    ),
    (
        "java-datetime-parse-exception",
        "Exception in thread \"main\" java.time.format.DateTimeParseException: Text '2024-13-01' could not be parsed: Invalid value for MonthOfYear (valid values 1 - 12): 13",
        "메인 스레드 예외: 날짜 파싱 예외: '2024-13-01' 을 파싱할 수 없습니다: MonthOfYear 값이 잘못됨(유효 범위 1 - 12): 13",
        ERROR, DEBUG, N, "문자열을 날짜로 바꿀 때",
        "형식은 맞는데 값이 범위를 벗어났다는 뜻이다. 어떤 항목이 어느 범위를 벗어났는지까지 "
        "알려준다. 형식 자체가 다르면 could not be parsed at index 뒤에 위치가 찍히므로 "
        "메시지 형태로 두 경우를 구분할 수 있다.",
    ),
    (
        "java-could-not-find-main-class",
        "Error: Could not find or load main class NoSuchClass",
        "오류: NoSuchClass 메인 클래스를 찾거나 로드할 수 없습니다",
        ERROR, DEBUG, E, "java 명령으로 실행할 때",
        "클래스 경로에서 그 클래스를 못 찾았다는 뜻이다. 파일 이름이 아니라 클래스 이름을 "
        "줘야 하고 .class 를 붙이면 안 된다. 패키지가 있으면 전체 이름으로 불러야 하며, "
        "바로 아래에 ClassNotFoundException 이 원인으로 붙어 나온다.",
    ),
    (
        "java-main-method-not-found",
        "Error: Main method not found in class M, please define the main method as:",
        "오류: 클래스 M 에서 main 메서드를 찾을 수 없습니다. 다음과 같이 정의하세요:",
        ERROR, DEBUG, E, "java 명령으로 실행할 때",
        "클래스는 찾았는데 시작점이 없다는 뜻이다. 이름을 잘못 적었거나 인자를 String[] 이 "
        "아니게 적은 경우다. static 만 빠뜨렸다면 문구가 달라서 "
        "Main method is not static in class 로 나온다. 뒤에 올바른 서명을 그대로 보여준다.",
    ),
    (
        "java-unsupported-class-version",
        "java.lang.UnsupportedClassVersionError: Hello has been compiled by a more recent version of the Java Runtime (class file version 65.0), this version of the Java Runtime only recognizes class file versions up to 61.0",
        "지원되지 않는 클래스 버전 오류: Hello 가 더 최신 자바 런타임(클래스 파일 버전 65.0)으로 컴파일되었지만, 현재 런타임은 61.0 까지만 인식합니다",
        ERROR, DEBUG, H, "빌드 환경과 실행 환경의 자바 버전이 다를 때",
        "컴파일한 자바가 실행하는 자바보다 최신이라는 뜻이다. 숫자에서 44 를 빼면 자바 "
        "버전이 되어 65 는 자바 21, 61 은 자바 17 이다. 즉 21 로 빌드해 17 에서 "
        "실행한 상황이다. 도커 이미지의 자바 버전과 빌드 설정이 어긋난 경우가 대부분이다.",
    ),
    (
        "java-compile-incompatible-types",
        "error: incompatible types: String cannot be converted to int",
        "오류: 호환되지 않는 타입: String 을 int 로 변환할 수 없습니다",
        ERROR, DEBUG, E, "javac 컴파일 중",
        "왼쪽이 넣으려는 값의 타입이고 오른쪽이 받는 쪽이다. 방향을 반대로 읽으면 "
        "엉뚱한 곳을 고치게 된다. 아래에 문제가 된 줄과 캐럿 표시로 위치까지 찍힌다.",
    ),
    (
        "java-compile-cannot-find-symbol",
        "error: cannot find symbol",
        "오류: 심볼을 찾을 수 없습니다",
        ERROR, DEBUG, E, "javac 컴파일 중",
        "그 이름을 못 찾겠다는 뜻이다. 오타, import 누락, 오타 난 메서드 이름이 대부분이다. "
        "이 줄만으로는 정보가 없고 바로 아래 symbol 과 location 줄에 무엇을 어디서 "
        "찾았는지 나오므로 그쪽을 봐야 한다.",
    ),
    (
        "java-compile-semicolon-expected",
        "error: ';' expected",
        "오류: ';' 가 필요합니다",
        ERROR, DEBUG, E, "javac 컴파일 중",
        "세미콜론이 빠졌다는 뜻인데, 알려주는 위치는 컴파일러가 이상하다고 느낀 지점이라 "
        "실제로 빠진 곳은 그 앞줄인 경우가 많다. 첫 번째 에러만 고치고 다시 컴파일하면 "
        "뒤따르던 에러가 한꺼번에 사라지는 일이 흔하다.",
    ),
    (
        "java-compile-class-file-name-mismatch",
        "error: class Other is public, should be declared in a file named Other.java",
        "오류: Other 클래스가 public 이므로 Other.java 라는 파일에 선언되어야 합니다",
        ERROR, DEBUG, E, "javac 컴파일 중",
        "public 클래스는 파일 이름과 클래스 이름이 같아야 한다는 자바 규칙이다. "
        "파일을 복사해 만들면서 클래스 이름만 바꾼 경우에 난다. IDE 없이 "
        "직접 컴파일할 때 처음 만나게 되는 규칙이다.",
    ),
    (
        "java-caused-by-hint",
        "Scroll down to the Caused by section, that's where the real error is.",
        "Caused by 부분까지 내려가 보세요. 진짜 에러는 거기 있습니다.",
        PHRASE, DEBUG, N, "긴 자바 스택 트레이스를 함께 볼 때",
        "자바 예외는 감싸고 또 감싸며 올라오기 때문에 맨 위 예외는 대개 껍데기다. "
        "Caused by 가 여러 번 나오면 가장 아래 것이 원인에 가장 가깝다.",
    ),
    (
        "java-dont-swallow-exception",
        "Please don't catch and ignore this, at least log it.",
        "이걸 잡아놓고 무시하지 마세요. 최소한 로그라도 남겨주세요.",
        PHRASE, DEBUG, N, "자바 코드 리뷰",
        "빈 catch 블록을 지적하는 표현이다. 당장은 에러가 안 보이지만 문제는 그대로 남아 "
        "훨씬 나중에 엉뚱한 곳에서 터진다. 원인을 찾을 단서까지 함께 사라지는 것이 "
        "가장 큰 손해다.",
    ),
    (
        "java-return-optional",
        "Return an Optional here instead of null.",
        "여기서는 null 말고 Optional 을 반환하세요.",
        PHRASE, DEBUG, N, "자바 코드 리뷰",
        "값이 없을 수 있다는 사실을 타입으로 드러내라는 제안이다. 다만 필드나 "
        "메서드 인자에는 쓰지 않는 것이 관례라, 반환값에만 쓰라는 뜻으로 읽어야 한다.",
    ),

    # ---------- Spring Boot ----------
    (
        "java-spring-application-failed-to-start",
        "APPLICATION FAILED TO START",
        "애플리케이션 시작에 실패했습니다",
        ERROR, OPS, E, "Spring Boot 시작 로그",
        "별표로 둘러싼 상자 안에 나오는 제목이다. 스택 트레이스보다 이 아래의 "
        "Description 과 Action 두 줄이 훨씬 유용하다. Spring Boot 가 흔한 실패를 "
        "미리 분석해 사람이 읽을 수 있는 형태로 정리해준 것이다.",
    ),
    (
        "java-spring-port-in-use",
        "Web server failed to start. Port 8080 was already in use.",
        "웹 서버 시작에 실패했습니다. 포트 8080 이 이미 사용 중입니다.",
        ERROR, OPS, E, "Spring Boot 시작 로그의 Description",
        "앞서 띄운 애플리케이션이 완전히 종료되지 않은 경우가 대부분이다. "
        "바로 아래 Action 에 포트를 바꾸거나 그 프로세스를 찾아 끄라는 안내가 나온다. "
        "설정으로 바꾸려면 server.port 를 지정한다.",
    ),
    (
        "java-spring-datasource-url",
        "Failed to configure a DataSource: 'url' attribute is not specified and no embedded datasource could be configured.",
        "DataSource 구성에 실패했습니다: 'url' 속성이 지정되지 않았고 내장 데이터소스도 구성할 수 없습니다.",
        ERROR, DB, N, "Spring Boot 시작 로그의 Description",
        "데이터베이스 관련 의존성은 있는데 접속 주소가 없다는 뜻이다. 설정 파일이 "
        "안 읽혔거나 프로파일이 활성화되지 않은 경우가 많다. 뒤이어 나오는 "
        "Reason 줄에 드라이버를 못 찾았다는 더 구체적인 이유가 붙는다.",
    ),
    (
        "java-spring-bean-not-found",
        "Parameter 0 of constructor in com.example.MyService required a bean of type 'com.example.MyRepository' that could not be found.",
        "com.example.MyService 생성자의 0번 파라미터가 'com.example.MyRepository' 타입 빈을 요구하지만 찾을 수 없습니다.",
        ERROR, OPS, N, "Spring Boot 시작 로그의 Description",
        "어느 클래스의 몇 번째 인자가 무엇을 필요로 하는지 정확히 알려준다. "
        "어노테이션을 빠뜨렸거나, 그 클래스가 스캔 대상 패키지 밖에 있는 경우가 대부분이다. "
        "필드 주입이면 앞부분이 Field 로 시작한다.",
    ),
    (
        "java-spring-circular-reference",
        "The dependencies of some of the beans in the application context form a cycle:",
        "애플리케이션 컨텍스트의 일부 빈 의존성이 순환을 이룹니다:",
        ERROR, OPS, H, "Spring Boot 시작 로그의 Description",
        "A 가 B 를 필요로 하고 B 가 다시 A 를 필요로 한다는 뜻이다. 아래에 상자 그림으로 "
        "고리를 그려 보여준다. 설정으로 허용할 수 있지만 그건 구조 문제를 덮는 것이라, "
        "중간에 인터페이스를 두거나 책임을 나누는 편이 맞다.",
    ),
    (
        "java-spring-no-static-resource",
        "No static resource api/users.",
        "정적 리소스 api/users 를 찾을 수 없습니다.",
        ERROR, API, H, "Spring Boot 3 에서 없는 주소를 호출할 때",
        "매핑된 컨트롤러가 없어 정적 파일로 찾아보다 실패했다는 뜻이다. 경로 맨 앞에 "
        "슬래시가 없는 것이 특징이다. Spring Boot 2 는 기본적으로 흰 화면과 함께 "
        "No mapping for GET /api/users 라는 경고 로그만 남겼기 때문에, "
        "옛 자료를 그대로 검색하면 안 나온다.",
    ),
    (
        "java-spring-method-not-supported",
        "Request method 'POST' is not supported",
        "요청 메서드 'POST' 는 지원되지 않습니다",
        ERROR, API, N, "Spring MVC 에서 405 응답이 나갈 때",
        "주소는 맞는데 그 메서드로는 받지 않는다는 뜻이다. 자원을 찾았다는 뜻이라 "
        "라우팅은 정상이라는 좋은 단서다. Spring 5 는 is 없이 "
        "Request method 'POST' not supported 로 찍혔다.",
    ),
    (
        "java-spring-required-body-missing",
        "Required request body is missing",
        "필수 요청 본문이 없습니다",
        ERROR, API, N, "Spring MVC 컨트롤러 호출 시",
        "본문을 기대하는 메서드에 본문 없이 요청이 왔다는 뜻이다. Content-Type 을 "
        "빠뜨려 본문이 파싱되지 않은 경우도 여기 해당하므로, 헤더를 먼저 확인하는 것이 "
        "빠르다. 뒤에 어느 메서드였는지 서명이 붙어 나온다.",
    ),
    (
        "java-spring-validation-failed",
        "Validation failed for argument [0] in public void com.example.UserController.create(com.example.UserDto)",
        "com.example.UserController.create 의 0번 인자 검증에 실패했습니다",
        ERROR, API, H, "@Valid 검증이 실패할 때",
        "어느 컨트롤러의 몇 번째 인자인지 알려주고, 뒤에 Field error in object 로 시작하는 "
        "항목별 상세가 이어진다. 실제로 무엇이 잘못됐는지는 맨 끝 default message 에 "
        "있으므로 길다고 건너뛰면 안 된다.",
    ),
    (
        "java-spring-ambiguous-mapping",
        "Ambiguous mapping. Cannot map",
        "모호한 매핑입니다. 매핑할 수 없습니다",
        ERROR, API, N, "Spring Boot 시작이 실패할 때",
        "같은 주소와 메서드 조합을 두 컨트롤러가 동시에 맡고 있다는 뜻이다. "
        "뒤에 충돌하는 두 메서드 이름이 함께 나온다. 복사해 만든 컨트롤러에서 "
        "경로를 바꾸지 않았을 때 흔하다.",
    ),
    (
        "java-spring-profile-check",
        "Which profile is this running with? The config looks like dev.",
        "이거 어떤 프로파일로 실행 중인가요? 설정이 dev 처럼 보입니다.",
        PHRASE, API, N, "Spring 설정 문제를 진단할 때",
        "환경별 설정 파일 중 어느 것이 적용됐는지 묻는 질문이다. 시작 로그에서 "
        "The following 1 profile is active 처럼 개수가 끼어든 줄을 찾으면 되고, "
        "운영에서 나는 설정 문제의 상당수가 여기서 끝난다.",
    ),

    # ---------- JPA / Hibernate ----------
    (
        "java-hibernate-lazy-initialization",
        "failed to lazily initialize a collection of role: com.example.Order.items: could not initialize proxy - no Session",
        "com.example.Order.items 컬렉션의 지연 초기화에 실패했습니다: 프록시를 초기화할 수 없습니다 - 세션 없음",
        ERROR, DB, H, "JPA 엔티티를 트랜잭션 밖에서 다룰 때",
        "지연 로딩으로 미뤄둔 데이터를 가져오려 했는데 세션이 이미 닫혔다는 뜻이다. "
        "트랜잭션이 끝난 뒤 컨트롤러나 뷰에서 연관 데이터를 건드릴 때 난다. "
        "필요한 데이터를 트랜잭션 안에서 미리 가져오거나 fetch join 을 쓰는 것이 정석이다.",
    ),
    (
        "java-hibernate-detached-entity",
        "detached entity passed to persist: com.example.Order",
        "분리된 엔티티가 persist 로 전달되었습니다: com.example.Order",
        ERROR, DB, H, "JPA 로 저장할 때",
        "이미 식별자를 가진 엔티티를 새로 저장하려 했다는 뜻이다. persist 는 새 엔티티용이고 "
        "기존 것을 반영하려면 merge 를 쓰거나, 조회해온 엔티티를 트랜잭션 안에서 "
        "고치는 방식으로 바꿔야 한다.",
    ),
    (
        "java-hibernate-schema-validation",
        "Schema-validation: missing table [users]",
        "스키마 검증: 테이블 [users] 가 없습니다",
        ERROR, DB, N, "Spring Boot 시작 로그",
        "엔티티가 기대하는 테이블이 실제 데이터베이스에 없다는 뜻이다. "
        "마이그레이션을 안 돌렸거나 다른 데이터베이스에 붙은 경우다. "
        "칼럼이 없을 때는 missing column 으로 나오므로 어디까지 맞는지 알 수 있다.",
    ),
    (
        "java-hibernate-sessionfactory",
        "[PersistenceUnit: default] Unable to build Hibernate SessionFactory",
        "[PersistenceUnit: default] Hibernate SessionFactory 를 만들 수 없습니다",
        ERROR, DB, H, "Spring Boot 시작 로그",
        "이 줄 자체에는 원인이 없고 감싸는 껍데기다. 진짜 이유는 아래 Caused by 에 있는 "
        "스키마 검증 실패나 매핑 오류다. 이 줄만 검색하면 원인이 제각각이라 "
        "도움이 안 되는 대표적인 메시지다.",
    ),
    (
        "java-jpa-fetch-join-suggestion",
        "This will fire an N+1, use a fetch join here.",
        "이건 N+1 을 일으킵니다. 여기서는 fetch join 을 쓰세요.",
        PHRASE, DB, H, "JPA 코드 리뷰",
        "지연 로딩된 연관 데이터를 반복문에서 건드리면 행마다 쿼리가 나간다는 지적이다. "
        "fetch join 은 한 번의 쿼리로 함께 가져오게 한다. 다만 여러 컬렉션을 동시에 "
        "fetch join 하면 결과가 곱해지므로 하나씩 적용해야 한다.",
    ),

    # ---------- Maven / Gradle ----------
    (
        "java-maven-build-failure",
        "[INFO] BUILD FAILURE",
        "[INFO] 빌드 실패",
        ERROR, OPS, E, "Maven 빌드 출력",
        "빌드가 실패했다는 요약 줄이다. 원인은 그 위에 [ERROR] 로 시작하는 줄들에 있다. "
        "출력이 길 때는 [ERROR] 로 필터링해서 보면 빠르다.",
    ),
    (
        "java-maven-could-not-resolve-dependencies",
        "Could not resolve dependencies for project com.example:demo:jar:1.0-SNAPSHOT",
        "com.example:demo:jar:1.0-SNAPSHOT 프로젝트의 의존성을 확인할 수 없습니다",
        ERROR, OPS, N, "Maven 빌드 출력",
        "선언한 라이브러리를 저장소에서 못 받았다는 뜻이다. 버전 오타, 사내 저장소 인증 누락, "
        "네트워크 차단이 흔한 원인이다. 뒤에 어떤 아티팩트를 어느 저장소에서 찾았는지까지 "
        "나오므로 그 부분이 진짜 단서다.",
    ),
    (
        "java-maven-no-compiler-provided",
        "No compiler is provided in this environment. Perhaps you are running on a JRE rather than a JDK?",
        "이 환경에는 컴파일러가 없습니다. JDK 가 아니라 JRE 에서 실행 중인 것 아닌가요?",
        ERROR, OPS, H, "Maven 컴파일 중",
        "실행만 가능한 JRE 로는 컴파일을 못 한다는 뜻이다. JAVA_HOME 이 JRE 를 가리키고 "
        "있는 경우가 대부분이라, 자바가 설치돼 있는지가 아니라 JAVA_HOME 이 어디를 "
        "가리키는지를 확인해야 한다.",
    ),
    (
        "java-maven-non-resolvable-parent-pom",
        "Non-resolvable parent POM",
        "부모 POM 을 확인할 수 없습니다",
        ERROR, OPS, N, "Maven 빌드 출력",
        "상속받는 부모 설정 파일을 못 찾았다는 뜻이다. Spring Boot 프로젝트에서 부모 버전을 "
        "잘못 적었을 때 자주 난다. 끝에 붙는 relativePath 안내는 거의 항상 따라오므로 "
        "단서가 아니고, 가운데 콜론 뒤의 이유를 봐야 저장소 문제인지 경로 문제인지 갈린다.",
    ),
    (
        "java-maven-compilation-error",
        "[ERROR] COMPILATION ERROR :",
        "[ERROR] 컴파일 오류 :",
        ERROR, OPS, E, "Maven 빌드 출력",
        "이 줄 아래로 실제 컴파일 에러들이 나열된다. 콜론 앞에 공백이 하나 있는 것이 "
        "maven-compiler-plugin 의 출력 형식이라, 검색할 때 그대로 붙여넣으면 잘 걸린다.",
    ),
    (
        "java-gradle-could-not-find-artifact",
        "Could not find com.example:missing-lib:1.2.3.",
        "com.example:missing-lib:1.2.3 을 찾을 수 없습니다.",
        ERROR, OPS, N, "Gradle 빌드 출력",
        "선언한 라이브러리를 어느 저장소에서도 못 찾았다는 뜻이다. 아래 "
        "Searched in the following locations 에 실제로 어디를 뒤졌는지 나오므로, "
        "저장소를 아예 등록하지 않은 것인지 버전이 없는 것인지 구분할 수 있다.",
    ),
    (
        "java-gradle-execution-failed-task",
        "Execution failed for task ':compileJava'.",
        "':compileJava' 작업 실행에 실패했습니다.",
        ERROR, OPS, E, "Gradle 빌드 출력",
        "어느 단계에서 실패했는지 알려주는 줄이다. 원인은 바로 아래 꺾쇠로 들여쓴 줄에 "
        "있고, 그 아래로 더 들어갈수록 구체적이다. 가장 안쪽 줄이 진짜 이유다.",
    ),
    (
        "java-gradle-could-not-resolve-configuration",
        "Could not resolve all files for configuration ':compileClasspath'.",
        "':compileClasspath' 구성의 모든 파일을 확인할 수 없습니다.",
        ERROR, OPS, N, "Gradle 빌드 출력",
        "컴파일에 필요한 라이브러리를 다 모으지 못했다는 뜻이다. dependencies 대신 "
        "files 라고 나오면 파일을 받는 단계에서 실패한 것이다. "
        "구성 이름이 runtimeClasspath 면 실행 시점 의존성 쪽 문제다.",
    ),
    (
        "java-gradle-compilation-failed",
        "Compilation failed; see the compiler output below.",
        "컴파일에 실패했습니다. 아래 컴파일러 출력을 확인하세요.",
        ERROR, OPS, E, "Gradle 빌드 출력",
        "자바 컴파일 자체가 실패했다는 뜻이다. Gradle 버전과 컴파일 방식에 따라 "
        "see the compiler error output for details. 라는 다른 문구가 나오기도 하는데 "
        "같은 상황이다.",
    ),
    (
        "java-bump-parent-version",
        "Let's bump the Spring Boot version in the parent pom first.",
        "먼저 부모 pom 의 Spring Boot 버전을 올립시다.",
        PHRASE, OPS, N, "의존성 업그레이드를 논의할 때",
        "bump 는 버전을 한 단계 올린다는 뜻으로 널리 쓰인다. Spring Boot 는 부모에서 "
        "라이브러리 버전을 한꺼번에 관리하므로, 개별 라이브러리를 따로 올리기보다 "
        "부모 버전을 올리는 것이 정석이다.",
    ),

    # ---------- Next.js ----------
    (
        "js-next-use-client-hook",
        "You're importing a component that needs `useState`. This React Hook only works in a Client Component. To fix, mark the file (or its parent) with the `\"use client\"` directive.",
        "`useState` 가 필요한 컴포넌트를 임포트하고 있습니다. 이 React 훅은 클라이언트 컴포넌트에서만 동작합니다. 해당 파일이나 상위 파일에 `\"use client\"` 지시문을 추가하세요.",
        ERROR, FRONT, N, "Next.js App Router 빌드 중",
        "App Router 에서는 파일이 기본적으로 서버 컴포넌트라 상태나 이벤트를 쓸 수 없다. "
        "파일 맨 위에 use client 한 줄을 넣으면 되지만, 그 파일이 임포트하는 것들이 "
        "전부 클라이언트 번들에 딸려 들어간다. 그래서 가능한 한 아래쪽 컴포넌트에만 "
        "붙이는 것이 좋다. children 으로 넘겨받는 것은 서버 컴포넌트로 남는다.",
    ),
    (
        "js-next-event-handlers-cannot-be-passed",
        "Error: Event handlers cannot be passed to Client Component props.",
        "오류: 이벤트 핸들러를 클라이언트 컴포넌트의 prop 으로 전달할 수 없습니다.",
        ERROR, FRONT, H, "Next.js App Router 빌드 중",
        "서버 컴포넌트에서 만든 함수는 직렬화할 수 없어 클라이언트로 넘길 수 없다는 뜻이다. "
        "onClick 을 쓰는 버튼을 별도 클라이언트 컴포넌트로 분리하면 해결된다. "
        "use server 를 붙인 서버 액션은 예외라서 이 경계를 넘어갈 수 있다.",
    ),
    (
        "js-next-module-not-found-fs",
        "Module not found: Can't resolve 'fs'",
        "모듈을 찾을 수 없습니다: 'fs' 를 확인할 수 없습니다",
        ERROR, FRONT, N, "Next.js 빌드 중",
        "브라우저에는 파일 시스템 모듈이 없다는 뜻이다. 서버 전용 코드가 클라이언트 "
        "번들에 딸려 들어간 것이라, 어디서 그 모듈을 타고 들어왔는지 "
        "Import trace 부분을 따라가야 원인이 나온다.",
    ),
    (
        "js-next-usesearchparams-suspense",
        "useSearchParams() should be wrapped in a suspense boundary at page \"/\". Read more: https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout",
        "\"/\" 페이지에서 useSearchParams() 는 서스펜스 경계로 감싸야 합니다.",
        ERROR, FRONT, H, "Next.js 빌드 중",
        "이 훅을 쓰면 그 부분은 미리 그려둘 수 없어서 브라우저에서 그려야 한다. "
        "감싸주지 않으면 페이지 전체가 사전 렌더링에서 빠지므로 Next 가 막는다. "
        "Suspense 로 감싸면 그 안쪽만 브라우저에서 그려진다.",
    ),
    (
        "js-next-missing-generate-static-params",
        "Page \"/blog/[slug]\" is missing \"generateStaticParams()\" so it cannot be used with \"output: export\" config.",
        "\"/blog/[slug]\" 페이지에 \"generateStaticParams()\" 가 없어 \"output: export\" 설정과 함께 쓸 수 없습니다.",
        ERROR, FRONT, H, "Next.js 정적 내보내기 빌드 중",
        "전부 미리 만들어두는 방식이라 어떤 slug 들이 있는지 빌드 시점에 알려줘야 한다는 "
        "뜻이다. 그 목록을 돌려주는 함수를 추가하거나, 정적 내보내기를 포기하고 "
        "서버에서 그리는 방식으로 바꿔야 한다.",
    ),
    (
        "js-next-sync-params",
        "Error: Route \"/u/[id]\" used `params.id`. `params` should be awaited before using its properties.",
        "오류: \"/u/[id]\" 경로에서 `params.id` 를 사용했습니다. `params` 는 속성을 쓰기 전에 await 해야 합니다.",
        ERROR, FRONT, H, "Next.js 15 개발 서버 로그",
        "Next 15 부터 params 와 searchParams 가 Promise 로 바뀌었다는 뜻이다. "
        "당장은 경고만 뜨고 동작하지만 폐기 예정이라 버전을 올리면 막힌다. "
        "함수를 async 로 바꾸고 await 를 붙이면 된다. Next 14 코드를 그대로 올렸을 때 "
        "만나는 대표적인 문구다.",
    ),
    (
        "js-next-check-server-component",
        "Is this a Server Component? If so, it can't use useEffect.",
        "이거 서버 컴포넌트인가요? 그렇다면 useEffect 를 쓸 수 없습니다.",
        PHRASE, FRONT, N, "Next.js App Router 코드 리뷰",
        "App Router 에서 가장 자주 나오는 리뷰 질문이다. 파일 맨 위에 use client 가 "
        "있는지부터 확인하자는 뜻이고, 데이터를 가져오는 것이 목적이라면 애초에 "
        "서버 컴포넌트에서 직접 가져오는 편이 낫다는 제안이 따라오기도 한다.",
    ),
    (
        "js-next-move-fetch-to-server",
        "We can fetch this on the server and skip the loading state entirely.",
        "이건 서버에서 가져오면 로딩 상태 자체가 필요 없어집니다.",
        PHRASE, FRONT, H, "Next.js App Router 코드 리뷰",
        "서버 컴포넌트에서 데이터를 가져오면 화면이 이미 채워진 채로 오기 때문에 "
        "로딩 처리와 그로 인한 화면 흔들림이 사라진다는 뜻이다. App Router 로 "
        "옮기는 이유 중 가장 실질적인 부분이다.",
    ),

    # ---------- TypeScript ----------
    (
        "js-ts-possibly-undefined-strict",
        "error TS18048: 'o.a' is possibly 'undefined'.",
        "오류 TS18048: 'o.a' 가 'undefined' 일 수 있습니다.",
        ERROR, FRONT, N, "TypeScript 컴파일 중",
        "선택적 속성을 확인 없이 파고들었다는 뜻이다. 옵셔널 체이닝을 쓰거나 "
        "먼저 있는지 확인하면 된다. 느낌표로 넘기는 것은 검사만 끄는 것이라 "
        "런타임 에러는 그대로 남는다.",
    ),
    (
        "js-ts-expected-arguments",
        "error TS2554: Expected 1 arguments, but got 2.",
        "오류 TS2554: 인자 1개가 필요한데 2개를 받았습니다.",
        ERROR, FRONT, E, "TypeScript 컴파일 중",
        "함수에 넘긴 인자 수가 맞지 않는다는 뜻이다. 자바스크립트는 남는 인자를 그냥 "
        "무시하고 넘어가는데 TypeScript 는 잡아준다. 인자를 하나 줄이거나 늘리는 "
        "리팩터링을 하고 호출부를 다 못 고쳤을 때 이 에러가 한꺼번에 쏟아진다.",
    ),
    (
        "js-ts-object-literal-unknown-property",
        "error TS2353: Object literal may only specify known properties, and 'extra' does not exist in type 'P'.",
        "오류 TS2353: 객체 리터럴에는 알려진 속성만 쓸 수 있는데 'extra' 는 'P' 타입에 없습니다.",
        ERROR, FRONT, N, "TypeScript 컴파일 중",
        "객체를 그 자리에서 바로 만들어 넣을 때만 이 검사가 돈다. 같은 객체를 변수에 "
        "담았다가 넘기면 통과하는데, 이 차이를 초과 속성 검사라고 부른다. "
        "오타 난 속성 이름을 잡아주는 것이 원래 목적이다.",
    ),
    (
        "js-ts-cannot-find-module",
        "error TS2307: Cannot find module './missing' or its corresponding type declarations.",
        "오류 TS2307: './missing' 모듈이나 해당 타입 선언을 찾을 수 없습니다.",
        ERROR, FRONT, N, "TypeScript 컴파일 중",
        "파일 자체가 없는 경우와, 파일은 있는데 타입 선언이 없는 경우 둘 다 이 메시지가 "
        "나온다. 외부 라이브러리라면 @types 패키지를 따로 설치해야 하는 경우가 많다. "
        "경로 별칭을 쓴다면 tsconfig 의 paths 설정도 확인한다.",
    ),

    # ---------- Node.js / Express ----------
    (
        "js-express-headers-already-sent",
        "Error [ERR_HTTP_HEADERS_SENT]: Cannot set headers after they are sent to the client",
        "오류 [ERR_HTTP_HEADERS_SENT]: 클라이언트에 응답을 보낸 뒤에는 헤더를 설정할 수 없습니다",
        ERROR, API, H, "Express 서버 로그",
        "한 요청에 응답을 두 번 보냈다는 뜻이다. 조건 분기 뒤에 return 을 빠뜨려 "
        "아래 코드까지 실행된 경우가 대부분이다. 응답을 보낸 곳마다 return 을 붙이면 "
        "대개 사라진다.",
    ),
    (
        "js-express-path-to-regexp-missing-param",
        "TypeError: Missing parameter name at 1: https://git.new/pathToRegexpError",
        "타입 오류: 1 번 위치에 파라미터 이름이 없습니다: https://git.new/pathToRegexpError",
        ERROR, API, H, "Express 5 서버 시작 시",
        "경로에 콜론만 있고 이름이 없다는 뜻이다. 숫자는 문제가 난 위치라 경로마다 "
        "달라지고, 뒤에 붙는 주소는 설명 문서 링크다. Express 5 로 올리면서 경로 "
        "문법이 엄격해져 예전에는 통하던 표현이 막힌다. 와일드카드 표기도 바뀌었으니 "
        "업그레이드 후 서버가 아예 안 뜨면 라우트 경로부터 확인한다.",
    ),
    (
        "js-node-esm-module-not-found",
        "Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/app/nope.js' imported from /app/index.mjs",
        "오류 [ERR_MODULE_NOT_FOUND]: /app/index.mjs 에서 임포트한 '/app/nope.js' 모듈을 찾을 수 없습니다",
        ERROR, API, N, "Node.js ESM 실행 중",
        "ES 모듈에서는 상대 경로에 확장자를 반드시 붙여야 한다. require 를 쓸 때는 "
        "생략해도 알아서 찾아줬기 때문에 옮겨오면서 자주 걸린다. "
        "TypeScript 로 짜면서 .js 확장자를 안 붙인 경우가 대표적이다.",
    ),
    (
        "js-node-import-attribute-missing",
        "TypeError [ERR_IMPORT_ATTRIBUTE_MISSING]: Module \"file:///app/data.json\" needs an import attribute of \"type: json\"",
        "타입 오류 [ERR_IMPORT_ATTRIBUTE_MISSING]: \"file:///app/data.json\" 모듈에는 \"type: json\" 임포트 속성이 필요합니다",
        ERROR, API, H, "Node.js ESM 실행 중",
        "ES 모듈에서 JSON 을 불러오려면 형식을 명시해야 한다는 뜻이다. "
        "with { type: 'json' } 을 붙이면 된다. require 로는 그냥 됐던 일이라 "
        "모듈 방식을 바꿀 때 걸리는 항목이다.",
    ),
    (
        "js-mongoose-validation-failed",
        "ValidationError: User validation failed: email: Path `email` is required.",
        "검증 오류: User 검증 실패: email: `email` 경로는 필수입니다.",
        ERROR, DB, N, "Mongoose 로 저장할 때",
        "스키마에 필수로 지정한 필드가 비어 있다는 뜻이다. 어느 모델의 어느 경로인지 "
        "정확히 알려준다. 여러 항목이 동시에 실패하면 쉼표로 이어 한 줄에 다 나온다.",
    ),
    (
        "js-mongoose-buffering-timed-out",
        "Operation `users.insertOne()` buffering timed out after 10000ms",
        "`users.insertOne()` 작업이 10000ms 뒤에 버퍼링 시간 초과되었습니다",
        ERROR, DB, H, "Mongoose 애플리케이션 로그",
        "쿼리가 느린 게 아니라 데이터베이스에 아예 연결되지 않았다는 뜻이다. "
        "Mongoose 는 연결 전 명령을 잠시 모아뒀다가 연결되면 보내는데, 그 대기가 "
        "끝난 것이다. 쿼리를 고칠 게 아니라 접속 문자열과 네트워크를 봐야 한다.",
    ),
    (
        "js-mongoose-overwrite-model",
        "OverwriteModelError: Cannot overwrite `User` model once compiled.",
        "모델 덮어쓰기 오류: 이미 컴파일된 `User` 모델을 덮어쓸 수 없습니다.",
        ERROR, DB, H, "Mongoose 애플리케이션 로그",
        "같은 이름으로 모델을 두 번 정의했다는 뜻이다. 개발 서버가 파일을 다시 불러오는 "
        "환경에서 자주 나므로 코드가 틀린 게 아닐 수 있다. 이미 있으면 그것을 쓰도록 "
        "감싸두는 것이 흔한 대응이다.",
    ),
    (
        "js-vue-v-if-missing-expression",
        "SyntaxError: v-if/v-else-if is missing expression.",
        "구문 오류: v-if/v-else-if 에 표현식이 없습니다.",
        ERROR, FRONT, E, "Vue 템플릿 컴파일 중",
        "지시어만 쓰고 조건식을 빠뜨렸다는 뜻이다. Vue 는 템플릿을 빌드 시점에 "
        "함수로 바꾸기 때문에 이런 실수를 실행 전에 잡아준다.",
    ),
    (
        "js-npm-eresolve-peer",
        "npm error ERESOLVE could not resolve",
        "npm 오류 ERESOLVE 해결할 수 없습니다",
        ERROR, OPS, H, "npm install 실행 시",
        "unable to resolve dependency tree 와 같은 ERESOLVE 실패인데, 이 머리말은 "
        "npm 이 어느 조합을 시도했는지까지 보여줄 때 나온다. 아래 Found / Could not "
        "resolve 목록이 실제 정보다. "
        "--legacy-peer-deps 로 넘기면 설치는 되지만 충돌은 그대로 남는다.",
    ),
    (
        "js-node-version-mismatch",
        "npm error code EBADENGINE",
        "npm 오류 코드 EBADENGINE",
        ERROR, OPS, N, "npm install 실행 시",
        "패키지가 요구하는 Node 버전과 지금 버전이 다르다는 뜻이다. 아래 "
        "npm error engine Unsupported engine 줄에 요구 버전과 현재 버전이 나란히 나온다. "
        "로컬은 되는데 CI 에서만 깨지는 문제의 흔한 원인이라, .nvmrc 나 engines 로 "
        "버전을 고정해두는 것이 예방책이다. Yarn 은 같은 상황을 "
        "The engine \"node\" is incompatible with this module 로 알린다.",
    ),
    (
        "js-lockfile-conflict",
        "Please regenerate the lock file instead of resolving the conflict by hand.",
        "잠금 파일 충돌은 손으로 풀지 말고 다시 생성해 주세요.",
        PHRASE, OPS, N, "잠금 파일 충돌이 났을 때",
        "잠금 파일은 사람이 읽으라고 만든 것이 아니라 도구가 관리하는 파일이다. "
        "충돌 표시를 손으로 지우면 실제 설치되는 버전과 어긋날 수 있어서, "
        "지우고 다시 설치해 새로 만드는 것이 안전하다.",
    ),
    (
        "js-pin-the-version",
        "Let's pin this dependency instead of using a caret range.",
        "캐럿 범위 말고 이 의존성 버전을 고정합시다.",
        PHRASE, OPS, N, "의존성 관리를 논의할 때",
        "pin 은 버전을 하나로 못박는다는 뜻이고, caret 은 ^1.2.3 처럼 위쪽 버전을 "
        "허용하는 표기다. 잠금 파일이 있으면 대개 충분하지만, 라이브러리를 배포하는 "
        "쪽이라면 범위를 어떻게 열어둘지가 중요한 결정이 된다.",
    ),
    (
        "js-tree-shaking-import",
        "Import only what you need so the bundler can tree-shake the rest.",
        "번들러가 나머지를 걷어낼 수 있게 필요한 것만 임포트하세요.",
        PHRASE, FRONT, N, "번들 크기를 리뷰할 때",
        "라이브러리 전체를 통째로 가져오면 안 쓰는 코드까지 번들에 들어간다는 지적이다. "
        "다만 어느 코드가 쓰이는지 정적으로 알 수 있어야 걷어낼 수 있어서, "
        "라이브러리가 그 방식을 지원하는지도 함께 봐야 한다.",
    ),
    (
        "js-avoid-default-export",
        "Prefer named exports here so the import name stays consistent.",
        "임포트 이름이 일관되게 유지되도록 여기서는 이름 있는 내보내기를 쓰세요.",
        PHRASE, FRONT, N, "모듈 구조를 리뷰할 때",
        "기본 내보내기는 가져오는 쪽에서 아무 이름이나 붙일 수 있어 같은 것이 파일마다 "
        "다른 이름으로 불리게 된다. 자동 완성과 이름 일괄 변경이 잘 동작하는 것도 "
        "이름 있는 내보내기 쪽이다.",
    ),
    (
        "js-strict-mode-suggestion",
        "Can we turn on strict mode for this package first?",
        "이 패키지부터 strict 모드를 켜볼 수 있을까요?",
        PHRASE, FRONT, H, "TypeScript 설정을 논의할 때",
        "한 번에 전체를 켜면 에러가 수백 개 나오므로 범위를 좁혀 시작하자는 제안이다. "
        "strict 는 여러 검사를 묶은 스위치라, 개별 항목부터 하나씩 켜는 방식도 "
        "같은 취지의 대안이다.",
    ),

]

# 목록에서 뺀 항목의 slug.
#
# 위 목록에서 지우기만 하면 DB 에 있던 행은 그대로 남는다. 시드는 추가와
# 갱신만 하고 삭제는 하지 않기 때문이다. 소스에서 사라져 관리 대상에서도
# 빠진 채 사용자에게 계속 보이는 상태가 된다.
#
# 여기 적으면 시드를 돌릴 때 함께 지운다. 한 번 배포해 정리되고 나면
# 이 목록에서도 빼도 된다.
RETIRED_SLUGS = [
    # 다른 CORS 항목(api-cors-blocked-policy)의 부분 문자열이라 따로
    # 가르칠 내용이 없었다.
    "api-cors-missing-header",
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

        # 목록에서 뺀 항목을 지운다. 이걸 안 하면 소스에서 사라진 문장이
        # DB 에는 남아 사용자에게 계속 보인다.
        retired, _ = Sentence.objects.filter(slug__in=RETIRED_SLUGS).delete()

        parts = [f"{created}개 추가"]
        if updated:
            parts.append(f"{updated}개 갱신")
        if skipped:
            parts.append(f"{skipped}개 건너뜀")
        if retired:
            parts.append(f"{retired}개 삭제")
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
