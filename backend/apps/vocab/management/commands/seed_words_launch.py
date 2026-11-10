"""출시 전에 단어를 1,000개 넘게 채운다. seed_words_more 의 뒤를 잇는 묶음.

사용:
    python manage.py seed_words_launch --dry-run
    python manage.py seed_words_launch

무엇이 모자랐나 (2026-11-10, 단어 617개 기준)

    debug 66 · git 66 · database 71 · review 73   (가장 적은 넷)
    frontend 74 · api 77 · devops 80 · cs 110

출시를 앞두고 1,000개를 넘기려고 분류마다 50개 안팎을 더했다(428개).
debug, Docker 처럼 매일 쓰는데 빠져 있던 기본 단어부터 넣었고, 에러 메시지에
그대로 나오는 문구(permission denied 등)와 정처기 필기 용어를 함께 늘렸다.

    git 57 · review 52 · api 55 · database 57 · devops 52 · debug 61 · frontend 56 · cs 38

검수는 seed_words 머리말의 기준을 따르되 사람 대신 AI 가 했다. 형식은
tests.py 의 ALL_SEEDED 가 전 항목에 건다. 내용은 분류별로 AI 가 쓴 초안을
다른 AI 에이전트 넷이 분야별로 전부 읽어 지적 95건(틀림 20, 개선 75)을 냈고,
작업 세션이 하나씩 판정해 93건을 반영했다. 사람이 줄별로 읽지는 않았다.
그래도 검수 대기 없이 바로 노출하는 것은 사용자가 정했다(2026-11-10). 그래서
출처(source)를 "AI 생성(에이전트 검수)" 로 남겨 나중에 골라 다시 볼 수 있게 했다.

넣는 방식은 seed_words_more 와 같다(이미 있는 단어는 건너뛴다). 검색용 한글
표기는 seed_word_aliases, 정처기 과목 표시는 mark_exam_scope 가 따로 채운다.
"""

from __future__ import annotations

from apps.vocab.models import Word

from .seed_words_more import Command as SeedWordsMoreCommand

E = Word.Difficulty.EASY
N = Word.Difficulty.NORMAL
H = Word.Difficulty.HARD

GIT = Word.Category.GIT
REVIEW = Word.Category.REVIEW
API = Word.Category.API
DB = Word.Category.DATABASE
OPS = Word.Category.DEVOPS
DEBUG = Word.Category.DEBUG
FRONT = Word.Category.FRONTEND
CS = Word.Category.CS

# (term, pronunciation, meaning, category, difficulty, description,
#  example, example_translation) - seed_words_more 와 열 순서가 같다.
WORDS: list[tuple[str, str, str, str, int, str, str, str]] = [
    # ---------- 버전 관리 ----------
    (
        "abort", "/əˈbɔrt/", "하던 병합이나 리베이스를 취소하다",
        GIT, N,
        "병합이나 리베이스 도중 충돌이 너무 꼬였을 때 시작하기 전 상태로 돌아가는 것. git merge --abort 나 git "
        "rebase --abort 처럼 쓴다. 충돌을 반쯤 풀다가도 쓸 수 있지만, 그때까지 푼 내용은 사라진다.",
        "If the rebase gets messy, just abort and start over.",
        "리베이스가 꼬이면 그냥 취소하고 처음부터 다시 하세요.",
    ),
    (
        "ahead", "/əˈhed/", "원격에 아직 안 올린 내 커밋이 있는",
        GIT, N,
        "git status 가 Your branch is ahead 라고 하면 내 브랜치에 아직 원격으로 올리지 않은 커밋이 있다는 "
        "뜻이다. 뒤에 붙는 숫자가 그 개수다. 이 상태로 다른 컴퓨터에서 작업하면 그 커밋이 보이지 않으니 push 를 잊지 않는다.",
        "Your branch is ahead of origin/main by 2 commits.",
        "내 브랜치가 origin/main 보다 커밋 2개 앞서 있습니다.",
    ),
    (
        "assignee", "/əˌsaɪˈni/", "이슈나 PR 을 맡은 담당자",
        GIT, N,
        "이슈나 PR 을 처리하기로 정해진 사람으로, 여러 명을 지정할 수도 있다. 리뷰를 해주는 사람인 reviewer 와는 다르다. "
        "담당자 없이 열린 이슈는 아무도 안 보고 있다는 뜻일 때가 많아서, 맡을 거라면 자기 이름을 걸어둔다.",
        "Set yourself as the assignee if you're taking this one.",
        "이거 맡으실 거면 담당자에 본인을 지정해 주세요.",
    ),
    (
        "atomic commit", "/əˈtɑmɪk ˌkɑmɪt/", "한 가지 변경만 담은 커밋",
        GIT, N,
        "커밋 하나에 논리적으로 한 가지 일만 담는 습관. 버그 수정과 이름 바꾸기를 한 커밋에 섞으면 문제가 생겼을 때 수정만 되돌릴 수 "
        "없다. 파일 개수가 적다는 뜻이 아니라, 되돌려도 다른 기능이 깨지지 않는 단위라는 뜻이다.",
        "Make each change an atomic commit so we can revert the fix alone.",
        "수정만 따로 되돌릴 수 있게 변경마다 커밋을 하나씩 나눠 주세요.",
    ),
    (
        "auto-merge", "/ˈɔtoʊ ˌmɜrdʒ/", "조건이 채워지면 저절로 합쳐지게 걸어두기",
        GIT, N,
        "필수 검사와 승인이 다 채워지는 순간 PR 이 자동으로 병합되도록 미리 걸어두는 기능. 검사가 끝나길 지켜보지 않아도 된다. "
        "걸어둔 뒤 새 커밋을 올리면 그 커밋까지 함께 합쳐지니, 마무리가 안 됐으면 걸지 않는다.",
        "I enabled auto-merge, so it will land when CI passes.",
        "자동 병합을 켜뒀으니 CI 가 통과하면 합쳐질 거예요.",
    ),
    (
        "backport", "/ˈbækˌpɔrt/", "새 버전의 수정을 옛 버전에도 옮겨 넣기",
        GIT, H,
        "main 에 들어간 버그 수정을 이미 나가 있는 옛 버전의 릴리스 브랜치에도 옮겨 적용하는 것. 보통 해당 커밋을 체리픽해서 "
        "옮긴다. 옛 버전 쪽 코드가 많이 달라 그대로 안 붙으면 손으로 다시 짜야 할 때도 있다.",
        "Can we backport this security fix to the 2.x line?",
        "이 보안 수정을 2.x 버전에도 옮겨 넣을 수 있을까요?",
    ),
    (
        "bare repository", "/ˈber rɪˌpɑzəˌtɔri/", "작업 폴더 없이 기록만 담은 저장소",
        GIT, H,
        "파일을 꺼내 놓은 작업 폴더 없이 .git 안의 기록만 있는 저장소. 서버에서 여러 사람의 push 를 받는 용도로 쓴다. 작업 "
        "폴더가 있는 일반 저장소에는 지금 체크아웃된 브랜치로 push 할 수 없어서, 중앙 저장소는 이렇게 만든다.",
        "Create a bare repository on the server for everyone to push to.",
        "모두가 푸시할 수 있게 서버에 베어 저장소를 만드세요.",
    ),
    (
        "base branch", "/ˈbeɪs ˌbræntʃ/", "PR 을 합쳐 넣을 대상 브랜치",
        GIT, N,
        "PR 에서 내 변경을 받아들일 쪽 브랜치로, 보통 main 이다. 내 브랜치는 head 또는 compare 라고 부르고, "
        "GitLab 에서는 target branch 라고 한다. 잘못 고르면 남의 커밋까지 변경 목록에 잔뜩 섞여 보인다.",
        "Change the base branch to develop before you merge.",
        "병합하기 전에 대상 브랜치를 develop 으로 바꿔 주세요.",
    ),
    (
        "baseline", "/ˈbeɪsˌlaɪn/", "변경을 재는 기준으로 확정해 둔 상태",
        GIT, N,
        "검토를 마치고 공식으로 확정한 산출물의 한 시점으로, 이후 변경은 이것을 기준으로 승인받아 반영한다. 정처기 형상 관리에서 "
        "기준선이라는 이름으로 나온다. 실무에서는 성능을 비교할 때 기준으로 삼는 측정값도 같은 말로 부른다.",
        "We froze the design as the baseline for this release.",
        "이번 릴리스의 기준선으로 설계를 확정했습니다.",
    ),
    (
        "behind", "/bɪˈhaɪnd/", "원격에 내가 아직 안 받은 커밋이 있는",
        GIT, N,
        "원격 브랜치의 새 커밋을 아직 내 브랜치에 합치지 않았다는 뜻이다. 마지막 fetch 기준이라, fetch 를 안 했으면 원격에 "
        "새 커밋이 있어도 뜨지 않는다. 이 상태로 push 하면 거부되니 먼저 pull 한다. ahead 와 같이 뜨면 갈라진 것이다.",
        "Your branch is behind origin/main, so pull before you push.",
        "브랜치가 origin/main 보다 뒤처져 있으니 push 하기 전에 pull 하세요.",
    ),
    (
        "branching strategy", "/ˈbræntʃɪŋ ˌstrætədʒi/", "브랜치를 어떻게 나누고 합칠지 정한 팀 규칙",
        GIT, N,
        "어떤 브랜치를 언제 만들고 어디로 합칠지 팀이 정한 방식. Git Flow, GitHub Flow, 트렁크 기반 개발이 "
        "대표적이다. 정답이 있는 게 아니라 배포 주기와 팀 크기에 맞춰 고르고, 바꾸려면 팀 전체가 같이 바꿔야 한다.",
        "Our branching strategy is simple: short branches off main.",
        "저희 브랜치 전략은 단순합니다. main 에서 짧은 브랜치를 따는 거예요.",
    ),
    (
        "bump", "/bʌmp/", "버전 숫자를 하나 올리다",
        GIT, N,
        "버전 번호를 올리는 것을 가볍게 이르는 말. 내 프로젝트 버전을 올릴 때도, 가져다 쓰는 라이브러리 버전을 올릴 때도 쓴다. 커밋 "
        "메시지나 봇이 연 PR 제목에서 자주 보이고, 메이저 버전을 올리는 경우는 호환이 깨질 수 있으니 체인지로그를 같이 본다.",
        "Bump the version to 1.4.0 before tagging.",
        "태그를 달기 전에 버전을 1.4.0 으로 올려 주세요.",
    ),
    (
        "change control", "/ˈtʃeɪndʒ kənˌtroʊl/", "변경 요청을 검토해 승인된 것만 반영하는 절차",
        GIT, H,
        "확정된 기준선을 바꾸려면 요청을 올리고 영향과 비용을 검토해 승인된 것만 반영하는 절차. 정처기 형상 관리 절차 중 형상 통제에 "
        "해당한다. 아무나 바로 고치지 못하게 막는 대신 느려지기 때문에, 바뀌면 위험한 운영 시스템에 주로 건다.",
        "Any schema change in production must go through change control.",
        "운영 환경의 스키마 변경은 모두 변경 통제 절차를 거쳐야 합니다.",
    ),
    (
        "check-in", "/ˈtʃek ˌɪn/", "고친 파일을 저장소에 다시 반영하기",
        GIT, N,
        "작업한 파일을 저장소에 다시 올려 반영하는 것으로, 꺼내오는 체크아웃의 반대다. 정처기 형상 관리 도구의 기능으로 체크아웃, "
        "커밋과 함께 나온다. Git 에는 이런 이름의 명령이 따로 없고 commit 과 push 가 그 역할을 한다.",
        "Each check-in to SVN starts a new build.",
        "SVN 에 체크인할 때마다 새 빌드가 돕니다.",
    ),
    (
        "code owner", "/ˈkoʊd ˌoʊnər/", "그 경로의 코드를 책임지고 리뷰하는 사람",
        GIT, N,
        "CODEOWNERS 파일에 경로별로 지정해둔 책임자. 그 경로를 건드린 PR 이 열리면 자동으로 리뷰어로 지정되고, 설정에 따라 "
        "그 사람의 승인이 있어야 병합된다. 코드를 처음 쓴 사람이 아니라 지금 책임지는 사람이다.",
        "Ask the code owner of the payments folder to approve this.",
        "결제 폴더 담당자에게 승인을 부탁하세요.",
    ),
    (
        "conflict marker", "/ˈkɑnflɪkt ˌmɑrkər/", "충돌 난 곳에 Git 이 끼워 넣는 표시 줄",
        GIT, N,
        "충돌이 나면 Git 이 파일 안에 <<<<<<<, =======, >>>>>>> 줄로 양쪽 내용을 갈라 적어둔다. 병합할 때는 "
        "위가 내 쪽, 아래가 합치려는 쪽이고, 리베이스할 때는 반대다. 정리한 뒤 이 표시 줄을 지우지 않고 커밋하는 실수가 흔하다.",
        "You left a conflict marker in the config file.",
        "설정 파일에 충돌 표시가 남아 있어요.",
    ),
    (
        "contributor", "/kənˈtrɪbjətər/", "프로젝트에 코드나 문서를 보탠 사람",
        GIT, E,
        "저장소에 커밋이나 PR, 문서, 이슈로 기여한 사람. 쓰기 권한이 없어도 포크에서 PR 을 보내 병합되면 기여자가 된다. 오탈자 "
        "하나를 고친 것도 기여로 치니, 처음 오픈소스를 할 때 문서부터 시작하는 사람이 많다.",
        "Every contributor must sign the CLA before we can merge.",
        "병합하려면 모든 기여자가 CLA 에 서명해야 합니다.",
    ),
    (
        "Conventional Commits", "/kənˈvenʃənəl ˌkɑmɪts/", "커밋 메시지 앞에 feat·fix 같은 종류를 붙이는 규칙",
        GIT, N,
        "커밋 메시지를 feat, fix, docs 같은 종류로 시작하게 정한 공개 규칙. 형식이 정해져 있어서 도구가 메시지를 읽고 "
        "체인지로그를 만들거나 버전을 몇 번째 자리까지 올릴지 정할 수 있다. 팀마다 쓰는 종류 이름이 조금씩 다르니 저장소 안내를 먼저 "
        "본다.",
        "We follow Conventional Commits, so start the message with fix: or feat:.",
        "저희는 Conventional Commits 를 따르니 메시지를 fix: 나 feat: 로 시작해 주세요.",
    ),
    (
        "default branch", "/dɪˈfɔlt ˌbræntʃ/", "저장소를 열면 처음 보이는 기본 브랜치",
        GIT, E,
        "클론하면 처음 체크아웃되고 PR 의 대상으로 기본 선택되는 브랜치. GitHub 는 2020년부터 새 저장소를 main 으로 "
        "만들지만, 로컬의 git init 은 Git 버전과 설정에 따라 master 로 만들기도 한다. 이름이 어긋나 push 가 "
        "실패하는 일이 흔하다.",
        "The default branch was renamed from master to main.",
        "기본 브랜치 이름이 master 에서 main 으로 바뀌었습니다.",
    ),
    (
        "discard", "/dɪˈskɑrd/", "커밋 안 한 변경을 버리다",
        GIT, E,
        "아직 커밋하지 않은 수정 내용을 지우고 마지막 커밋 상태로 돌리는 것. 에디터의 Discard Changes 버튼이 이 일을 "
        "한다. 커밋도 스태시도 안 한 내용은 Git 에 기록이 없어서 한 번 버리면 reflog 로도 되찾기 어렵다.",
        "Discard your local edits and pull again.",
        "로컬에서 고친 것을 버리고 다시 pull 하세요.",
    ),
    (
        "diverge", "/daɪˈvɜrdʒ/", "로컬과 원격이 서로 다른 커밋으로 갈라지다",
        GIT, N,
        "같은 브랜치인데 로컬과 원격에 각자 상대에게 없는 커밋이 쌓인 상태가 되는 것. 한쪽이 다른 쪽을 그대로 따라잡을 수 없어서 "
        "병합할지 리베이스할지 정해야 한다. 원격 브랜치를 누가 강제 푸시로 덮어썼을 때도 이렇게 된다.",
        "When local and remote diverge, Git asks you to merge or rebase.",
        "로컬과 원격이 갈라지면 Git 이 병합할지 리베이스할지 묻습니다.",
    ),
    (
        "downstream", "/ˈdaʊnˌstrim/", "내 것을 가져다 쓰는 아래쪽",
        GIT, N,
        "upstream 의 반대로, 내 저장소나 코드를 받아다 쓰는 쪽을 말한다. 원본 저장소 입장에서는 포크들이, 라이브러리 입장에서는 "
        "그것을 쓰는 프로젝트가 이쪽이다. 원본에서 고친 것은 받아 쓰는 쪽이 직접 가져가야 반영된다.",
        "This breaking change will hit every downstream project.",
        "이 호환성 깨지는 변경은 이걸 가져다 쓰는 모든 프로젝트에 영향을 줍니다.",
    ),
    (
        "draft PR", "/ˌdræft ˌpi ˈɑr/", "아직 덜 됐다고 표시해 연 PR",
        GIT, E,
        "작업 중임을 표시한 채 열어둔 PR. 병합 버튼이 막히고 코드 오너에게 자동으로 리뷰 요청이 가지도 않는다. 방향을 일찍 "
        "보여주거나 CI 결과를 미리 보려고 쓰고, 다 되면 Ready for review 로 바꾼다.",
        "I opened a draft PR so you can check the direction early.",
        "방향을 일찍 봐주실 수 있게 드래프트 PR 을 열었습니다.",
    ),
    (
        "feature branch", "/ˈfitʃər ˌbræntʃ/", "기능 하나를 만들려고 따로 낸 브랜치",
        GIT, E,
        "기능 하나나 수정 하나를 위해 기본 브랜치에서 갈라낸 짧은 브랜치. 작업이 끝나면 PR 로 합치고 지운다. 오래 끌수록 기본 "
        "브랜치와 멀어져 충돌이 커지니, 큰 기능도 작게 나눠 여러 번에 걸쳐 빨리 합치는 편이 낫다.",
        "Create a feature branch for the login page.",
        "로그인 화면 작업용 기능 브랜치를 만드세요.",
    ),
    (
        "feature request", "/ˈfitʃər rɪˌkwest/", "새 기능을 만들어 달라는 요청",
        GIT, E,
        "버그가 아니라 없는 기능을 추가해 달라는 이슈. 많은 저장소가 버그 신고와 양식을 나눠 두고, 무엇을 하고 싶은지와 왜 필요한지를 "
        "적게 한다. 원하는 해결책보다 지금 겪고 있는 문제를 구체적으로 적어야 더 나은 방법이 나온다.",
        "Please file this as a feature request, not a bug.",
        "이건 버그 말고 기능 요청으로 올려 주세요.",
    ),
    (
        "force-with-lease", "/ˈfɔrs wɪð ˌlis/", "그사이 남이 올린 게 없을 때만 덮어쓰는 강제 푸시",
        GIT, H,
        "강제 푸시를 하되, 마지막으로 fetch 한 뒤 원격에 다른 커밋이 올라왔으면 거부하는 옵션. 그냥 강제 푸시는 그 커밋을 경고 "
        "없이 지운다. 에디터가 뒤에서 자동으로 fetch 하면 기준이 새로 잡혀 이 보호가 사라지니, 푸시 전에 원격을 한 번 본다.",
        "After rebasing, push with --force-with-lease instead of a plain --force.",
        "리베이스한 뒤에는 그냥 강제로 밀지 말고 --force-with-lease 로 푸시하세요.",
    ),
    (
        "Git", "/ɡɪt/", "가장 널리 쓰는 분산 버전 관리 도구",
        GIT, E,
        "코드의 변경 이력을 커밋 단위로 기록하는 분산 버전 관리 도구. 리눅스 커널을 만든 리누스 토르발스가 2005년에 만들었다. "
        "GitHub 는 Git 저장소를 올려두는 서비스이고 Git 자체는 내 컴퓨터에서 도는 프로그램이라, 둘은 같은 것이 아니다.",
        "We moved the old project from SVN to Git last year.",
        "작년에 예전 프로젝트를 SVN 에서 Git 으로 옮겼습니다.",
    ),
    (
        "Git Flow", "/ˈɡɪt ˌfloʊ/", "main·develop 에 기능·출시·긴급 수정 브랜치를 더한 전략",
        GIT, N,
        "늘 남는 main 과 develop 두 브랜치에, 기능용 feature, 출시 준비용 release, 긴급 수정용 hotfix 를 "
        "더해 쓰는 브랜치 전략. 정해진 날에 버전을 내는 제품에 맞고, 하루에도 여러 번 배포하는 웹 서비스에는 무겁다는 평이 많다.",
        "We dropped Git Flow because release branches slowed us down.",
        "릴리스 브랜치 때문에 느려져서 Git Flow 를 그만뒀습니다.",
    ),
    (
        "gitkeep", "/ˈɡɪtˌkip/", "빈 폴더를 올리려고 넣어두는 빈 파일",
        GIT, N,
        "Git 은 파일만 기록하고 빈 폴더는 기록하지 않는다. 그래서 폴더 구조를 남기고 싶을 때 .gitkeep 이라는 빈 파일을 "
        "넣어둔다. Git 이 정한 기능이 아니라 이름만 정한 관례라서 다른 이름이어도 동작은 같다.",
        "Add a .gitkeep so the empty logs folder gets committed.",
        "빈 logs 폴더도 커밋되게 .gitkeep 을 넣어 주세요.",
    ),
    (
        "good first issue", "/ˌɡʊd ˌfɜrst ˈɪʃu/", "처음 기여하는 사람에게 맞는 쉬운 이슈",
        GIT, E,
        "오픈소스 저장소가 처음 오는 기여자에게 권하는 이슈에 붙이는 라벨. 범위가 작고 코드 전체를 몰라도 고칠 수 있는 것을 고른다. "
        "시작하기 전에 댓글로 맡겠다고 먼저 남겨야 다른 사람과 같은 일을 겹쳐서 하지 않는다.",
        "Pick a good first issue if you want to start contributing.",
        "기여를 시작해 보고 싶으면 good first issue 라벨이 붙은 걸 골라 보세요.",
    ),
    (
        "hunk", "/hʌŋk/", "diff 에서 바뀐 줄이 모인 한 덩어리",
        GIT, H,
        "diff 를 볼 때 @@ 표시로 시작하는, 바뀐 줄과 그 주변 몇 줄을 묶은 덩어리. git add -p 로 한 파일에서 원하는 "
        "덩어리만 골라 담을 수 있다. 섞여버린 수정을 여러 커밋으로 나눌 때 이 단위로 고른다.",
        "Stage only the first hunk and leave the debug print out.",
        "첫 번째 덩어리만 스테이징하고 디버그 출력은 빼세요.",
    ),
    (
        "imperative mood", "/ɪmˈperətɪv ˌmud/", "동사 원형으로 시작하는 명령문 꼴",
        GIT, H,
        "영어 문장을 동사 원형으로 시작하는 명령문 꼴. 커밋 메시지 제목은 Added 나 Fixes 대신 Add, Fix 처럼 이 꼴로 "
        "쓰는 것이 Git 의 관례다. 이 커밋을 적용하면 무엇을 하는지 적는다고 생각하면 자연스럽게 나온다.",
        "Write the subject line in the imperative mood, like Add login page.",
        "제목 줄은 Add login page 처럼 명령문으로 쓰세요.",
    ),
    (
        "incoming change", "/ˈɪnˌkʌmɪŋ ˌtʃeɪndʒ/", "충돌에서 합치려고 들어오는 쪽 변경",
        GIT, N,
        "충돌 화면에서 상대 브랜치에서 들어오는 내용을 말하고, 지금 내 브랜치에 있던 쪽은 current change 라고 부른다. "
        "리베이스할 때는 두 쪽이 병합 때와 뒤바뀌어 보여서, 이름만 보고 고르면 내 작업을 버리기 쉽다.",
        "Accept the incoming change here; their version is newer.",
        "여기는 들어오는 쪽 변경을 받으세요. 그쪽이 더 최신이에요.",
    ),
    (
        "init", "/ɪˈnɪt/", "지금 폴더를 새 저장소로 만들다",
        GIT, E,
        "initialize 의 줄임말로, git init 은 지금 폴더에 .git 디렉터리를 만들어 버전 관리를 시작한다. 이미 저장소인 "
        "폴더의 하위 폴더에서 또 하면 저장소 안에 저장소가 생겨 헷갈린다. 남의 프로젝트를 받을 때는 init 이 아니라 clone 을 "
        "쓴다.",
        "Run git init in the new folder before your first commit.",
        "첫 커밋 전에 새 폴더에서 git init 을 실행하세요.",
    ),
    (
        "initial commit", "/ɪˈnɪʃəl ˌkɑmɪt/", "저장소의 맨 첫 커밋",
        GIT, E,
        "저장소를 만들고 처음 남기는 커밋으로, 부모 커밋이 없어 이력의 맨 처음이 된다. 메시지를 그대로 Initial commit "
        "이라고 적는 관례가 있다. 처음부터 빌드 산출물이나 비밀값을 넣으면 나중에 지워도 이력에 남으니 gitignore 를 먼저 "
        "만든다.",
        "The initial commit only has the README and a gitignore.",
        "첫 커밋에는 README 와 gitignore 만 있습니다.",
    ),
    (
        "issue", "/ˈɪʃu/", "할 일이나 버그를 저장소에 적어 올린 글",
        GIT, E,
        "버그, 기능 요청, 질문을 저장소에 글로 남겨 번호를 붙여 관리하는 것. 커밋이나 PR 에 Fixes #12 처럼 적어두면 병합될 "
        "때 그 번호의 글이 자동으로 닫힌다. 일상 영어의 문제라는 뜻과 겹쳐 쓰여서 문맥으로 구분한다.",
        "Open an issue first so we can discuss the bug.",
        "버그를 논의할 수 있게 이슈부터 열어 주세요.",
    ),
    (
        "label", "/ˈleɪbəl/", "이슈나 PR 에 붙이는 분류 꼬리표",
        GIT, E,
        "bug, enhancement, documentation 처럼 이슈와 PR 에 붙여 종류나 상태를 나누는 꼬리표. 하나에 여러 개 "
        "붙일 수 있고, 꼬리표로 걸러 보거나 자동화를 걸 수 있다. 팀이 쓰는 목록을 먼저 보고 비슷한 것을 새로 만들지 않는다.",
        "Add the bug label so it shows up in triage.",
        "분류할 때 보이게 bug 라벨을 붙여 주세요.",
    ),
    (
        "linear history", "/ˈlɪniər ˌhɪstəri/", "갈래 없이 한 줄로 이어진 커밋 기록",
        GIT, H,
        "병합 커밋 없이 커밋이 한 줄로만 이어진 히스토리. 읽기 쉽고 bisect 로 문제 커밋을 찾기도 편하다. 저장소 설정이 이를 "
        "강제하면 PR 을 병합 커밋으로 합칠 수 없고, 리베이스나 스쿼시 방식으로만 합쳐야 해서 병합 버튼 일부가 막힌다.",
        "The main branch requires a linear history, so squash before merging.",
        "main 브랜치는 한 줄 히스토리를 요구하니 병합 전에 스쿼시하세요.",
    ),
    (
        "maintainer", "/meɪnˈteɪnər/", "프로젝트를 관리하고 병합을 결정하는 사람",
        GIT, E,
        "저장소에 쓰기 권한이 있고 PR 을 받아줄지, 이슈를 어떻게 처리할지, 언제 릴리스할지 정하는 사람. 오픈소스에서는 대개 시간을 "
        "쪼개 일하는 사람들이라 답이 늦을 수 있다. 재촉하기보다 재현 방법을 정리해 두는 편이 빨리 받아들여진다.",
        "A maintainer needs to approve before this can be merged.",
        "병합하려면 메인테이너의 승인이 필요합니다.",
    ),
    (
        "merge base", "/ˈmɜrdʒ ˌbeɪs/", "두 브랜치가 갈라진 공통 조상 커밋",
        GIT, H,
        "두 브랜치가 마지막으로 같았던 커밋, 즉 갈라지기 직전의 공통 조상. 병합은 이 커밋과 양쪽 끝을 비교해 이뤄지고, PR 의 변경 "
        "목록도 이 지점부터 계산된다. 기준 브랜치를 오래 안 받으면 이 지점이 멀어져 충돌이 커진다.",
        "Find the merge base to see where the two branches split.",
        "두 브랜치가 어디서 갈라졌는지 보려면 merge base 를 찾아보세요.",
    ),
    (
        "merge queue", "/ˈmɜrdʒ ˌkju/", "승인된 PR 을 차례로 검사해 합치는 대기열",
        GIT, H,
        "승인된 PR 을 바로 합치지 않고 줄을 세운 뒤, 앞의 PR 들과 합친 상태로 다시 검사해 통과한 것만 합치는 기능. 각자는 "
        "통과했는데 합치고 나니 main 이 깨지는 일을 막는다. GitLab 에서는 merge train 이라고 부른다.",
        "Add your PR to the merge queue once it's approved.",
        "승인되면 PR 을 병합 대기열에 넣으세요.",
    ),
    (
        "open source", "/ˌoʊpən ˈsɔrs/", "누구나 코드를 보고 고쳐 쓸 수 있게 공개한 것",
        GIT, E,
        "소스 코드를 공개해 누구나 보고, 고치고, 다시 배포할 수 있게 한 소프트웨어. 공짜라는 뜻이 아니라 라이선스가 허락한 범위 "
        "안에서 쓸 수 있다는 뜻이다. 라이선스에 따라 내 코드도 공개해야 할 수 있으니 회사 코드에 넣기 전에 확인한다.",
        "We use an open source library for PDF parsing.",
        "PDF 파싱에 오픈소스 라이브러리를 씁니다.",
    ),
    (
        "pathspec", "/ˈpæθˌspek/", "명령이 다룰 파일 경로를 가리키는 표기",
        GIT, H,
        "git add 나 checkout 에 넘기는 파일 경로나 패턴을 말한다. pathspec did not match any "
        "files 라는 에러는 그 경로가 없거나 오타가 났다는 뜻이고, 브랜치 이름을 잘못 적었을 때도 Git 이 그것을 파일로 보고 이 "
        "에러를 낸다.",
        "Git says the pathspec did not match, so check the file name.",
        "pathspec 이 맞지 않는다고 하니 파일 이름을 확인하세요.",
    ),
    (
        "personal access token", "/ˌpɜrsənəl ˈækses ˌtoʊkən/", "비밀번호 대신 쓰는 개인용 접근 토큰",
        GIT, N,
        "GitHub 에 HTTPS 로 push 할 때 계정 비밀번호 대신 넣는 긴 문자열. 2021년부터 비밀번호 인증이 막혀서, "
        "비밀번호를 넣었는데 인증에 실패하면 대개 이것을 만들어야 한다. 비밀번호처럼 다뤄야 하고 권한과 만료일은 필요한 만큼만 잡는다.",
        "Use a personal access token instead of your password when pushing.",
        "푸시할 때 비밀번호 대신 개인용 액세스 토큰을 쓰세요.",
    ),
    (
        "protected branch", "/prəˈtektɪd ˌbræntʃ/", "바로 푸시하거나 지울 수 없게 막은 브랜치",
        GIT, N,
        "직접 푸시, 강제 푸시, 삭제를 막고 PR 과 승인, 검사 통과를 거쳐야만 바뀌게 설정한 브랜치. 보통 main 에 건다. "
        "관리자도 막히게 설정할 수 있어서, 급해도 우회하지 말고 PR 을 올리라는 뜻으로 받아들인다.",
        "You can't push to main directly; it's a protected branch.",
        "main 은 보호된 브랜치라 직접 푸시할 수 없어요.",
    ),
    (
        "README", "/ˈridˌmi/", "저장소에서 처음 읽으라고 둔 안내 문서",
        GIT, E,
        "저장소 맨 위에 두는 안내 파일로, 무엇을 하는 프로젝트인지와 설치, 실행 방법을 적는다. GitHub 는 저장소 첫 화면에 이 "
        "파일을 그대로 보여준다. 실행 방법이 바뀌었으면 여기도 같이 고쳐야 다음 사람이 헤매지 않는다.",
        "Update the README with the new setup steps.",
        "새 설치 순서로 README 를 고쳐 주세요.",
    ),
    (
        "refspec", "/ˈrefˌspek/", "로컬과 원격의 어느 이름끼리 맞출지 적는 표기",
        GIT, H,
        "push 나 fetch 때 내 쪽 어떤 이름을 원격의 어떤 이름에 맞출지 적는 표기. src refspec main does "
        "not match any 라는 에러는 대개 보내려는 브랜치가 아직 없거나, 커밋이 하나도 없거나, 이름을 틀렸다는 뜻이다.",
        "The push failed with a refspec error because the branch had no commits.",
        "브랜치에 커밋이 없어서 push 가 refspec 에러로 실패했습니다.",
    ),
    (
        "repository", "/rɪˈpɑzəˌtɔri/", "코드와 그 변경 이력을 담아두는 저장소",
        GIT, E,
        "프로젝트의 파일과 지금까지의 모든 커밋 기록을 함께 담은 단위. 줄여서 repo 라고 많이 부른다. 내 컴퓨터에 있는 로컬 "
        "저장소와 GitHub 같은 서버에 있는 원격 저장소가 따로 있고, 둘은 push 와 pull 을 해야 맞춰진다.",
        "Clone the repository and run the setup script.",
        "저장소를 클론한 뒤 설정 스크립트를 실행하세요.",
    ),
    (
        "resolve", "/rɪˈzɑlv/", "충돌이나 코멘트 논의를 해결하다",
        GIT, E,
        "충돌을 정리해 최종 내용을 정하는 것, 또는 PR 의 코멘트 논의를 끝났다고 표시하는 것을 말한다. 충돌은 파일을 고친 뒤 git "
        "add 까지 해야 해결로 친다. 남이 연 코멘트를 내가 닫아도 되는지는 팀 관례를 따른다.",
        "Please resolve the merge conflict in settings.py.",
        "settings.py 의 병합 충돌을 해결해 주세요.",
    ),
    (
        "SSH key", "/ˌes es ˈeɪtʃ ˌki/", "비밀번호 없이 접속하려고 만든 키 한 쌍",
        GIT, E,
        "공개키와 개인키 한 쌍으로, 공개키를 GitHub 같은 곳에 등록해두면 비밀번호 없이 push 와 clone 이 된다. "
        "Permission denied 에러에 publickey 가 붙어 나오면 대개 키를 등록하지 않았거나 다른 키를 쓰고 있다는 "
        "뜻이다. 개인키 파일은 절대 남에게 주거나 커밋하지 않는다.",
        "Add your SSH key to GitHub before you clone the repo.",
        "저장소를 클론하기 전에 SSH 키를 GitHub 에 등록하세요.",
    ),
    (
        "stacked PR", "/ˌstækt ˌpi ˈɑr/", "앞 PR 위에 이어 쌓아 올린 PR",
        GIT, H,
        "큰 작업을 여러 PR 로 나누되, 다음 PR 이 앞 PR 의 브랜치에서 갈라져 나오게 쌓는 방식. 리뷰어는 작은 단위로 나눠 읽을 "
        "수 있다. 앞 PR 이 고쳐지면 뒤 PR 들을 차례로 리베이스해야 해서 손이 많이 간다.",
        "This is a stacked PR, so please review #41 first.",
        "앞 PR 위에 쌓은 PR 이라 #41 부터 리뷰해 주세요.",
    ),
    (
        "stale branch", "/ˈsteɪl ˌbræntʃ/", "오래 손대지 않고 방치된 브랜치",
        GIT, N,
        "오랫동안 새 커밋이 없는 브랜치. GitHub 는 석 달 넘게 커밋이 없으면 이렇게 분류해 따로 보여준다. 이미 합친 것은 지워도 "
        "되지만, 안 합친 것은 아직 남은 작업이 있는지 브랜치를 만든 사람에게 먼저 확인한 뒤 지운다.",
        "This stale branch hasn't had a commit since March.",
        "이 방치된 브랜치는 3월 이후로 커밋이 없습니다.",
    ),
    (
        "status check", "/ˈsteɪtəs ˌtʃek/", "PR 에 붙는 자동 검사 결과",
        GIT, N,
        "CI 가 PR 의 커밋마다 돌린 테스트나 린트 결과를 초록 체크나 빨간 X 로 보여주는 것. 저장소에서 필수로 정한 검사가 "
        "통과하지 않으면 병합 버튼이 막힌다. 내 코드와 상관없어 보여도 빨간불이면 내용부터 확인한다.",
        "The status check is still red, so we can't merge yet.",
        "상태 검사가 아직 빨간불이라 병합할 수 없습니다.",
    ),
    (
        "SVN", "/ˌes vi ˈen/", "중앙 서버 한 곳에 기록을 모으는 버전 관리 도구",
        GIT, N,
        "Subversion 의 줄임말로, 모든 이력을 중앙 서버 한 곳에 두는 방식의 버전 관리 도구. 커밋하면 바로 서버에 올라가서 "
        "Git 처럼 내 컴퓨터에 먼저 쌓아둘 수 없다. 오래된 사내 프로젝트에서 아직 쓰고, 정처기에서는 형상 관리 도구로 나온다.",
        "The old billing code is still in SVN.",
        "예전 결제 코드는 아직 SVN 에 있습니다.",
    ),
    (
        "three-way merge", "/ˌθri weɪ ˈmɜrdʒ/", "공통 조상까지 셋을 비교해 합치기",
        GIT, H,
        "두 브랜치의 끝과 둘이 갈라진 공통 조상을 함께 비교해 합치는 방식. 조상과 비교하면 어느 쪽이 무엇을 바꿨는지 알 수 있어서, "
        "한쪽만 고친 줄은 자동으로 합쳐진다. 같은 줄을 양쪽이 다르게 고친 경우만 충돌로 남는다.",
        "Git did a three-way merge because both branches had new commits.",
        "양쪽 브랜치에 새 커밋이 있어서 Git 이 3-way 병합을 했습니다.",
    ),
    (
        "trunk-based development", "/ˈtrʌŋk ˌbeɪst dɪˌveləpmənt/", "모두가 main 하나에 작게 자주 합치는 방식",
        GIT, H,
        "오래 가는 브랜치를 두지 않고 모두가 trunk, 즉 main 하나에 하루 한 번 이상 작게 합치는 방식. 충돌이 작고 배포가 "
        "잦은 팀에 맞는다. 덜 만든 기능은 브랜치에 묵혀두는 대신 기능 플래그로 숨긴 채 합친다.",
        "With trunk-based development, nobody keeps a branch open for weeks.",
        "트렁크 기반 개발에서는 누구도 브랜치를 몇 주씩 열어두지 않습니다.",
    ),
    (
        "wontfix", "/ˌwoʊntˈfɪks/", "고치지 않기로 하고 닫는다는 표시",
        GIT, N,
        "won't fix 를 붙여 쓴 말로, 문제는 맞지만 고치지 않기로 했다는 뜻의 라벨이다. 의도한 동작이거나, 고치는 비용이 너무 "
        "크거나, 프로젝트 방향과 맞지 않을 때 붙인다. 무시당했다고 받아들이기 쉬운데 대개 이유가 댓글에 적혀 있다.",
        "The maintainer closed it as wontfix because it's intended behavior.",
        "의도된 동작이라 메인테이너가 wontfix 로 닫았습니다.",
    ),
    # ---------- 코드 리뷰 ----------
    (
        "acceptance criteria", "/əkˈseptəns kraɪˌtɪriə/", "티켓마다 따로 정해 둔 완료 확인 조건",
        REVIEW, N,
        "이 작업이 끝났다고 볼 수 있는 구체적인 조건 목록. 티켓을 시작하기 전에 적어 두면 만드는 사람과 확인하는 사람이 같은 기준으로 "
        "본다. 팀 전체의 공통 기준인 definition of done 과 달리 티켓마다 따로 정한다.",
        "The acceptance criteria say the export must include deleted users.",
        "완료 조건에 따르면 내보내기에 탈퇴한 사용자도 포함돼야 합니다.",
    ),
    (
        "agile", "/ˈædʒəl/", "짧게 만들고 자주 고쳐 가는 개발 방식",
        REVIEW, E,
        "긴 계획을 한 번에 세우는 대신 짧은 주기로 만들고 보여 주고 고치기를 되풀이하는 개발 방식을 통틀어 부르는 말. 스크럼과 XP "
        "가 대표적이다. 문서와 계획을 안 한다는 뜻이 아니라 변화에 대응하는 것을 더 중요하게 본다는 뜻이다.",
        "We follow an agile process with two-week sprints.",
        "우리는 2주 단위 스프린트로 애자일하게 진행합니다.",
    ),
    (
        "anti-pattern", "/ˈæntiˌpætərn/", "흔히 쓰지만 결국 문제를 낳는 방식",
        REVIEW, N,
        "처음엔 그럴듯해 보여 자주 쓰이지만 나중에 문제를 일으키는 것으로 알려진 해법. 그냥 나쁜 코드와 달리 많은 사람이 되풀이해 "
        "빠지는 함정이라 이름이 붙어 있다. 리뷰에서 이 말을 들으면 더 나은 대안도 대개 함께 알려져 있다.",
        "Catching every exception and ignoring it is an anti-pattern.",
        "모든 예외를 잡아서 무시하는 건 안티 패턴입니다.",
    ),
    (
        "ASAP", "/ˌeɪ es eɪ ˈpi/", "가능한 한 빨리",
        REVIEW, E,
        "As Soon As Possible 의 줄임말. 한 글자씩 읽거나 '에이샙' 처럼 붙여 읽는다. 급하다는 것은 전해지지만 "
        "언제까지인지는 안 알려 줘서 받는 쪽이 결국 다시 묻게 된다. 정말 급하면 시각을 함께 적는 편이 낫다.",
        "Can you look at the login bug ASAP? Users are locked out.",
        "로그인 버그 최대한 빨리 봐 줄 수 있나요? 사용자들이 로그인을 못 하고 있어요.",
    ),
    (
        "bandwidth", "/ˈbændˌwɪdθ/", "네트워크 대역폭, 또는 일을 더 맡을 여유",
        REVIEW, H,
        "원래는 네트워크가 한 번에 보낼 수 있는 양인 대역폭을 뜻한다. 회의나 메신저에서는 사람이 일을 더 맡을 시간과 여력을 가리킨다. "
        "I don't have the bandwidth 는 하기 싫다기보다 지금 맡은 일이 많다는 정중한 거절이다.",
        "I don't have the bandwidth this sprint; can someone else take it?",
        "이번 스프린트엔 여유가 없어요. 다른 분이 맡아 주실 수 있나요?",
    ),
    (
        "burndown chart", "/ˈbɜrnˌdaʊn ˌtʃɑrt/", "남은 일이 줄어드는 모습을 그린 그래프",
        REVIEW, N,
        "스프린트 동안 남은 작업량을 날짜별로 이어 그린 그래프. 이상적인 선보다 위에 있으면 일정이 밀리고 있다는 뜻이고, 중간에 일이 "
        "추가되면 선이 다시 올라간다. 정처기에서는 스크럼에서 진행 상황을 확인하는 도구로 나온다.",
        "The burndown chart is flat, so we're probably blocked on something.",
        "번다운 차트가 평평한 걸 보니 뭔가에 막혀 있는 것 같습니다.",
    ),
    (
        "circle back", "/ˌsɜrkəl ˈbæk/", "나중에 다시 이야기하다",
        REVIEW, H,
        "지금 결론을 내지 않고 나중에 그 주제로 다시 돌아오자는 표현. 회의에서 시간이 모자라거나 정보가 더 필요할 때 쓴다. 다시 안 "
        "하겠다는 말을 돌려서 할 때도 쓰인다. 누가 언제 다시 꺼낼지 정해 두지 않으면 그대로 묻히기 쉽다.",
        "Let's circle back on the caching question once we have numbers.",
        "수치가 나오면 캐싱 문제는 다시 이야기합시다.",
    ),
    (
        "code review", "/ˈkoʊd rɪˌvju/", "남이 짠 코드를 읽고 의견을 주는 일",
        REVIEW, E,
        "합치기 전에 다른 사람이 변경 내용을 읽고 문제나 개선점을 짚는 과정. 버그를 잡는 것만큼 팀이 코드를 함께 알게 되는 데 의미가 "
        "있다. 사람을 평가하는 자리가 아니라 코드를 보는 자리라서, 지적을 받았다고 위축될 필요는 없다.",
        "Every change needs a code review before it goes to main.",
        "모든 변경은 main 에 들어가기 전에 코드 리뷰를 받아야 합니다.",
    ),
    (
        "cyclomatic complexity", "/ˌsaɪkləˌmætɪk kəmˈpleksəti/", "코드 안 갈림길 수로 잰 복잡도",
        REVIEW, H,
        "함수 안에서 if, for 같은 분기로 생기는 독립적인 실행 경로의 수. 값이 클수록 이해하기도 테스트하기도 어렵다. 정처기에서는 "
        "맥케이브 순환 복잡도라는 이름으로, 제어 흐름 그래프를 주고 값을 계산하게 하는 문제가 나온다.",
        "The linter flags any function whose cyclomatic complexity is above ten.",
        "린터는 순환 복잡도가 10 을 넘는 함수를 모두 경고합니다.",
    ),
    (
        "dead code", "/ˌded ˈkoʊd/", "실행될 일이 없는 코드",
        REVIEW, E,
        "어디서도 부르지 않거나 조건상 절대 닿지 않는 코드. 지우기 겁나서 남겨 두면 읽는 사람이 아직 쓰이는 코드인 줄 알고 시간을 "
        "쓴다. 지운 코드도 버전 관리 기록에 남아 있어 필요하면 되살릴 수 있으니 미련 없이 지우는 것이 보통이다.",
        "This branch is dead code since the flag was removed last month.",
        "지난달 플래그를 지운 뒤로 이 분기는 실행될 일이 없는 코드입니다.",
    ),
    (
        "early return", "/ˌɜrli rɪˈtɜrn/", "조건이 안 맞으면 함수를 먼저 빠져나가기",
        REVIEW, N,
        "예외적인 경우를 함수 맨 앞에서 처리하고 바로 return 해서 본 로직의 들여쓰기를 줄이는 방식. if 안에 if 가 겹겹이 "
        "쌓인 코드에 리뷰어가 흔히 제안한다. 이렇게 앞에 두는 검사를 guard clause 라고도 부른다.",
        "Use an early return here so the main logic isn't nested three levels deep.",
        "본 로직이 세 겹으로 들여쓰기되지 않게 여기서 먼저 return 하세요.",
    ),
    (
        "EOD", "/ˌi oʊ ˈdi/", "오늘 업무가 끝날 때까지",
        REVIEW, N,
        "End Of Day 의 줄임말로, 그날 업무가 끝나기 전까지라는 뜻이다. by EOD 처럼 기한을 말할 때 쓴다. 시간대가 다른 "
        "팀과 일할 때는 누구의 하루 끝인지 헷갈리므로 몇 시인지와 시간대를 함께 적는 편이 안전하다.",
        "I'll have the PR ready for review by EOD.",
        "오늘 퇴근 전까지 리뷰할 수 있게 PR 을 올려 두겠습니다.",
    ),
    (
        "epic", "/ˈepɪk/", "여러 작업을 묶은 큰 단위의 일",
        REVIEW, N,
        "스프린트 하나로 끝나지 않는 큰 일을 묶어 부르는 단위. 이슈 관리 도구에서 에픽 아래에 스토리나 티켓을 달아 전체 진행률을 "
        "본다. 에픽 하나가 끝나는 데 몇 달씩 걸리기도 한다. 일상 영어에서는 서사시나 대단하다는 뜻이라 처음 보면 헷갈린다.",
        "Link this ticket to the payments epic so we can track progress.",
        "진행 상황을 볼 수 있게 이 티켓을 결제 에픽에 연결하세요.",
    ),
    (
        "escalate", "/ˈeskəˌleɪt/", "더 권한 있는 사람에게 문제를 올리다",
        REVIEW, N,
        "혼자 풀 수 없거나 정해진 시간 안에 안 풀리는 문제를 더 권한 있는 사람이나 담당 팀에 넘기는 것. 장애 대응과 고객 문의에서 "
        "자주 쓴다. 남에게 떠넘기는 것이 아니라 절차라서, 오래 붙잡고 있기보다 일찍 올리는 편이 낫다.",
        "If the vendor doesn't reply in an hour, escalate to the team lead.",
        "업체가 한 시간 안에 답이 없으면 팀장에게 올리세요.",
    ),
    (
        "estimate", "/ˈestəmət/", "일이 얼마나 걸릴지 어림한 값",
        REVIEW, E,
        "작업이 얼마나 걸릴지 지금 아는 만큼으로 어림한 값. 약속한 마감과는 다르고, 새 정보가 들어오면 바뀌는 것이 정상이다. 같은 "
        "철자를 '어림하다' 라는 동사로도 쓰는데, 이때는 끝소리가 달라져 '에스티메이트' 로 읽는다.",
        "Give me a rough estimate for the export feature.",
        "내보내기 기능이 얼마나 걸릴지 대략 어림해 주세요.",
    ),
    (
        "fan-in", "/ˈfæn ˌɪn/", "이 모듈을 호출하는 상위 모듈의 수",
        REVIEW, H,
        "어떤 모듈을 호출하거나 가져다 쓰는 상위 모듈의 수. 많을수록 재사용이 잘 된다는 뜻이지만 그만큼 바뀌면 영향받는 곳도 많아 "
        "신중하게 고쳐야 한다. 정처기에서는 구조도를 주고 팬인과 팬아웃을 직접 세게 하는 문제가 나온다.",
        "The logger has a high fan-in, so test changes to it carefully.",
        "로거는 부르는 곳이 많으니 바꿀 때 꼼꼼히 테스트하세요.",
    ),
    (
        "fan-out", "/ˈfæn ˌaʊt/", "이 모듈이 호출하는 하위 모듈의 수",
        REVIEW, H,
        "어떤 모듈이 직접 호출하는 하위 모듈의 수. 너무 많으면 그 모듈이 여러 곳에 기대며 일을 많이 떠안고 있다는 뜻이라 쪼갤지 "
        "검토한다. 정처기에서는 팬인은 높이고 팬아웃은 낮추는 것이 좋은 설계라고 배우며 둘을 함께 묻는다.",
        "This service has a fan-out of twelve; split it up.",
        "이 서비스는 직접 부르는 모듈이 열둘이나 됩니다. 나눠 주세요.",
    ),
    (
        "Gantt chart", "/ˈɡænt ˌtʃɑrt/", "작업 기간을 막대로 그린 일정표",
        REVIEW, N,
        "작업마다 시작과 끝을 가로 막대로 그려 일정과 겹치는 기간을 한눈에 보는 표. 어떤 일이 다른 일이 끝나기를 기다리는지 보기 "
        "좋다. 계획을 세울 때는 편하지만, 일정이 자주 바뀌는 프로젝트에서는 고치지 않으면 금방 실제와 어긋난다.",
        "Put the migration and the API work on the Gantt chart to see overlaps.",
        "겹치는 기간을 보려면 마이그레이션과 API 작업을 간트 차트에 올리세요.",
    ),
    (
        "hardcode", "/ˈhɑrdˌkoʊd/", "바뀔 값을 코드에 직접 박아 넣다",
        REVIEW, E,
        "주소, 비밀번호, 설정값처럼 환경마다 달라질 값을 코드 안에 그대로 적는 것. 운영 서버로 옮길 때마다 코드를 고쳐야 하고, "
        "비밀키라면 저장소에 그대로 드러난다. 리뷰에서는 대개 hardcoded 라는 꼴로 지적받는다.",
        "Don't hardcode the API URL; read it from the environment.",
        "API 주소를 코드에 박지 말고 환경 변수에서 읽으세요.",
    ),
    (
        "heads-up", "/ˈhedz ˌʌp/", "곧 있을 일을 미리 알려 두는 말",
        REVIEW, N,
        "곧 일어날 일을 미리 알려 대비하게 하는 짧은 공지. Just a heads-up 으로 시작하는 메시지가 흔하다. FYI 가 그냥 "
        "참고하라는 공유라면, 이쪽은 당신 일에 영향이 있으니 미리 준비하라는 뉘앙스가 더 강하다.",
        "Heads-up: the staging DB will be reset at 6 p.m. today.",
        "미리 알려 드립니다. 오늘 오후 6시에 스테이징 DB 를 초기화합니다.",
    ),
    (
        "idiomatic", "/ˌɪdiəˈmætɪk/", "그 언어다운 자연스러운 방식의",
        REVIEW, H,
        "문법상 맞는 것을 넘어 그 언어 사용자들이 보통 쓰는 방식에 맞는다는 뜻. 파이썬에서 인덱스로 도는 for 문 대신 "
        "enumerate 를 쓰는 식이다. 리뷰에서 not idiomatic 이라는 말은 틀렸다는 게 아니라 낯설게 읽힌다는 뜻이다.",
        "A list comprehension is more idiomatic here than a manual loop.",
        "여기서는 직접 도는 반복문보다 리스트 컴프리헨션이 파이썬다운 방식입니다.",
    ),
    (
        "IMO", "/ˌaɪ em ˈoʊ/", "내 생각에는",
        REVIEW, E,
        "In My Opinion 의 줄임말. 리뷰에서 정답이 아니라 개인 의견이라는 것을 밝혀 말투를 누그러뜨린다. 더 겸손하게 쓰는 "
        "IMHO 도 같은 뜻이다. 이 표시가 붙은 의견에는 근거를 대고 반대해도 실례가 아니다.",
        "IMO this helper belongs in the utils module, not the view.",
        "제 생각엔 이 헬퍼는 뷰가 아니라 utils 모듈에 있는 게 맞아요.",
    ),
    (
        "information hiding", "/ˌɪnfərˈmeɪʃən ˌhaɪdɪŋ/", "모듈끼리 서로의 내부를 몰라도 되게 숨기기",
        REVIEW, H,
        "모듈이 내부 동작은 감추고 정해진 인터페이스만 밖에 보여 주는 설계 원칙. 내부를 바꿔도 쓰는 쪽은 고칠 필요가 없다. 캡슐화가 "
        "이를 구현하는 수단이라 둘을 같은 말처럼 쓰기도 한다. 정처기 1과목에서 설계 원리로 나온다.",
        "Information hiding lets us swap the storage backend without touching callers.",
        "정보 은닉 덕분에 호출하는 쪽을 건드리지 않고 저장소를 바꿀 수 있습니다.",
    ),
    (
        "inspection", "/ɪnˈspekʃən/", "역할을 나눠 형식을 갖춰 하는 검토",
        REVIEW, N,
        "진행자, 기록자처럼 역할을 정하고 체크리스트에 따라 결함을 찾는 가장 형식적인 검토 방식. 준비부터 사후 확인까지 절차가 정해져 "
        "있다. 정처기에서는 워크스루, 동료 검토와 함께 요구사항과 코드를 검토하는 방법으로 묶여 나온다.",
        "The safety module goes through a formal inspection every release.",
        "안전 모듈은 릴리스마다 정식 인스펙션을 거칩니다.",
    ),
    (
        "magic number", "/ˌmædʒɪk ˈnʌmbər/", "뜻을 설명 없이 박아 넣은 숫자",
        REVIEW, E,
        "코드 중간에 이유를 알 수 없는 숫자가 그대로 쓰인 것. 86400 이 하루를 초로 바꾼 값이라는 것을 읽는 사람이 직접 계산해야 "
        "한다. 이름 붙인 상수로 빼면 뜻이 드러나고, 값을 바꿀 때도 한 곳만 고치면 된다.",
        "Replace this magic number with a named constant like MAX_RETRIES.",
        "이 매직 넘버는 MAX_RETRIES 같은 이름 붙은 상수로 바꿔 주세요.",
    ),
    (
        "milestone", "/ˈmaɪlˌstoʊn/", "중간 목표 지점",
        REVIEW, E,
        "프로젝트 중간에 여기까지 되면 한 단계를 넘었다고 정해 둔 지점. GitHub 에서는 이슈를 묶어 진행률을 보는 기능 이름이기도 "
        "하다. 날짜만 정하는 것이 아니라 그때까지 무엇이 끝나 있어야 하는지를 함께 정해야 의미가 있다.",
        "Let's move the search ticket to the next milestone.",
        "검색 티켓은 다음 마일스톤으로 옮깁시다.",
    ),
    (
        "naming convention", "/ˈneɪmɪŋ kənˌvenʃən/", "이름 짓는 방식에 대한 약속",
        REVIEW, E,
        "변수, 함수, 파일 이름을 어떤 꼴로 지을지 팀이 정한 규칙. 파이썬은 snake_case, 자바스크립트는 camelCase 처럼 "
        "언어마다 관례가 다르다. 어느 쪽이 옳으냐보다 한 코드베이스 안에서 섞이지 않는 것이 중요하다.",
        "Follow the naming convention: components use PascalCase.",
        "이름 규칙을 따라 주세요. 컴포넌트는 PascalCase 로 씁니다.",
    ),
    (
        "non-functional requirement", "/ˌnɑnˈfʌŋkʃənəl rɪˌkwaɪərmənt/", "속도나 보안처럼 얼마나 잘 해야 하는지에 대한 요구",
        REVIEW, H,
        "시스템이 무엇을 하느냐가 아니라 얼마나 빠르고 안전하고 안정적으로 해야 하느냐를 정한 요구사항. 응답 시간, 동시 접속자 수, "
        "가용성 같은 것이다. 기능 목록에 안 보여서 놓치기 쉽고, 나중에 맞추려면 구조부터 바꿔야 할 때가 많다.",
        "Page load under two seconds is a non-functional requirement.",
        "페이지가 2초 안에 열려야 한다는 건 비기능 요구사항입니다.",
    ),
    (
        "OOO", "/ˌoʊ oʊ ˈoʊ/", "자리 비움, 휴가 중",
        REVIEW, N,
        "사무실에 없다는 뜻의 영어 세 낱말을 줄인 말. 휴가나 외근으로 연락이 어렵다는 표시로 메신저 상태나 캘린더에 적어 둔다. 이 "
        "표시를 봤다면 급한 일은 대신 봐 줄 사람을 찾는 것이 예의다. 말할 때는 줄이지 않고 풀어 읽기도 한다.",
        "I'm OOO on Friday, so please ask Mina about the deploy.",
        "금요일엔 자리에 없으니 배포 건은 미나에게 물어봐 주세요.",
    ),
    (
        "over-engineering", "/ˌoʊvər ˌendʒəˈnɪrɪŋ/", "필요 이상으로 복잡하게 만들기",
        REVIEW, N,
        "지금 문제에 비해 지나치게 일반화하거나 확장성을 미리 챙겨 구조를 복잡하게 만드는 것. 아직 오지 않은 요구에 대비하느라 정작 "
        "지금 코드가 읽고 고치기 어려워진다. YAGNI 와 KISS 가 이것을 경계하는 원칙이다.",
        "A plugin system for two exporters feels like over-engineering.",
        "내보내기 기능 두 개에 플러그인 구조는 과한 설계 같습니다.",
    ),
    (
        "P0", "/ˌpi ˈzɪroʊ/", "가장 먼저 처리해야 하는 최우선 등급",
        REVIEW, N,
        "이슈 우선순위를 P0, P1, P2 처럼 숫자로 매길 때 가장 급한 등급. 숫자가 작을수록 급하다. 보통 서비스가 멈췄거나 "
        "데이터가 잘못되는 수준이라 다른 일을 모두 멈추고 처리한다. 팀에 따라 P1 부터 세기도 한다.",
        "Checkout is down for everyone; this is a P0.",
        "모든 사용자가 결제를 못 하고 있습니다. 최우선 건입니다.",
    ),
    (
        "product owner", "/ˈprɑdəkt ˌoʊnər/", "무엇을 먼저 만들지 정하는 책임자",
        REVIEW, N,
        "스크럼에서 백로그의 우선순위를 정하고 무엇을 만들지 최종 판단하는 역할. 줄여서 PO 라고 부른다. 어떻게 만들지 지시하는 사람이 "
        "아니라 무엇을 왜 만드는지를 책임진다. 요구가 애매하거나 우선순위가 부딪히면 먼저 물어볼 사람이다.",
        "Ask the product owner whether this edge case matters for launch.",
        "이 예외 상황이 출시에 중요한지 PO 에게 물어보세요.",
    ),
    (
        "rationale", "/ˌræʃəˈnæl/", "그렇게 결정한 이유",
        REVIEW, H,
        "어떤 선택을 한 근거와 이유. PR 설명이나 설계 문서에 따로 칸을 두는 경우가 많다. 무엇을 바꿨는지는 코드에 남지만 왜 "
        "그랬는지는 적어 두지 않으면 사라진다. 철자가 비슷한 rational 은 합리적이라는 형용사다.",
        "Add the rationale to the PR description so reviewers know why.",
        "리뷰어가 이유를 알 수 있게 PR 설명에 근거를 적어 주세요.",
    ),
    (
        "requirement", "/rɪˈkwaɪərmənt/", "시스템이 갖춰야 할 조건",
        REVIEW, E,
        "만들 시스템이 해야 하는 일이나 지켜야 할 조건. 무엇을 하는지 적은 기능 요구사항과 속도, 보안처럼 얼마나 잘 해야 하는지 적은 "
        "비기능 요구사항으로 나눈다. 정처기 1과목이 이 내용으로 시작하고, 실무에서는 요구사항이 애매해서 생기는 재작업이 많다.",
        "This requirement is vague; what counts as fast enough?",
        "이 요구사항은 애매합니다. 어느 정도면 충분히 빠른 건가요?",
    ),
    (
        "roadmap", "/ˈroʊdˌmæp/", "앞으로 무엇을 언제 할지 그린 계획",
        REVIEW, E,
        "제품이나 기술을 앞으로 어떤 순서로 키워 갈지 큰 줄기를 정리한 계획. 분기나 반기 단위로 그리는 경우가 많다. 꼭 지켜야 할 "
        "일정표라기보다 팀이 같은 방향을 보게 하는 문서라서, 상황이 바뀌면 순서도 자주 바뀐다.",
        "Offline mode is on the roadmap for next quarter.",
        "오프라인 모드는 다음 분기 로드맵에 들어 있습니다.",
    ),
    (
        "rubber stamp", "/ˌrʌbər ˈstæmp/", "제대로 안 보고 형식적으로 하는 승인",
        REVIEW, H,
        "내용을 확인하지 않고 도장 찍듯 승인만 해 주는 것. 리뷰가 절차로만 남으면 이렇게 된다. 큰 PR 일수록 읽기 힘들어 이렇게 "
        "넘어가기 쉬워서 PR 을 작게 나누라는 말이 나온다. 동사로 쓸 때는 rubber-stamp 처럼 하이픈을 넣기도 한다.",
        "I don't want a rubber stamp; please check the migration carefully.",
        "형식적인 승인 말고 마이그레이션을 꼼꼼히 봐 주세요.",
    ),
    (
        "scrum", "/skrʌm/", "스프린트를 되풀이하며 일하는 애자일 방식",
        REVIEW, N,
        "보통 2~4주 길이의 스프린트를 반복하며 계획, 매일 스탠드업, 리뷰, 회고를 정해진 순서로 하는 애자일 방식. 제품 책임자, "
        "스크럼 마스터, 개발팀이라는 세 역할이 정해져 있다. 정처기 1과목에서 XP 와 함께 자주 나온다.",
        "Our team uses scrum, so planning happens every other Monday.",
        "우리 팀은 스크럼으로 일해서 2주마다 월요일에 계획 회의를 합니다.",
    ),
    (
        "separation of concerns", "/ˌsepəˌreɪʃən əv kənˈsɜrnz/", "하는 일별로 코드를 나눠 두는 원칙",
        REVIEW, H,
        "화면 표시, 업무 규칙, 데이터 저장처럼 성격이 다른 일을 서로 다른 모듈이 맡게 나누는 원칙. 한 부분을 고칠 때 다른 부분을 "
        "몰라도 되게 하는 것이 목적이다. 화면과 로직을 나누는 MVC 가 이 원칙을 따른 대표적인 예다.",
        "Moving the SQL out of the template improves separation of concerns.",
        "SQL 을 템플릿 밖으로 빼면 관심사가 더 잘 나뉩니다.",
    ),
    (
        "ship", "/ʃɪp/", "만든 것을 사용자에게 내보내다",
        REVIEW, N,
        "기능이나 제품을 완성해 실제 사용자가 쓰게 내보내는 것. 물건을 배에 실어 보낸다는 뜻에서 왔다. 배포와 비슷하지만 서버 작업보다 "
        "사용자에게 전달했다는 결과에 초점이 있다. Ship it 은 이 정도면 됐으니 내보내자는 승인의 말로도 쓴다.",
        "Let's ship the basic version first and improve it next sprint.",
        "기본 버전을 먼저 내보내고 다음 스프린트에 다듬읍시다.",
    ),
    (
        "side effect", "/ˈsaɪd ɪˌfekt/", "값을 돌려주는 것 말고 바깥을 바꾸는 일",
        REVIEW, N,
        "함수가 값을 돌려주는 것 외에 전역 변수 수정, 파일 쓰기, 네트워크 호출처럼 바깥 상태를 바꾸는 것. 그 자체가 나쁜 것이 "
        "아니라 숨어 있을 때가 문제다. 이름만 보면 조회인 함수가 저장까지 하면 리뷰에서 지적받는다.",
        "getUser shouldn't have a side effect like updating last_seen.",
        "getUser 가 last_seen 을 갱신하는 식으로 바깥을 바꾸면 안 됩니다.",
    ),
    (
        "sign-off", "/ˈsaɪn ˌɔf/", "책임자가 다음 단계로 가도 된다고 확인해 줌",
        REVIEW, N,
        "다음 단계로 넘어가도 좋다고 책임자가 공식적으로 확인해 주는 것. 기획, 디자인, QA 처럼 담당자별로 따로 받는다. 리뷰의 "
        "approve 보다 무게가 있어서, 받은 뒤에 내용을 바꾸면 다시 받아야 하는 경우가 많다.",
        "We need sign-off from the design team before we release this.",
        "출시하기 전에 디자인팀 승인을 받아야 합니다.",
    ),
    (
        "single source of truth", "/ˌsɪŋɡəl ˌsɔrs əv ˈtruθ/", "어느 값이 맞는지 가릴 때 기준이 되는 단 한 곳",
        REVIEW, N,
        "같은 데이터나 설정을 여러 곳에 따로 두지 않고 한 곳을 기준으로 삼는 원칙. 두 군데 두면 언젠가 한쪽만 고쳐져서 어느 쪽이 "
        "맞는지 알 수 없게 된다. 복사본이 필요하면 기준에서 읽어 오게 만든다. 줄여서 SSOT 라고도 쓴다.",
        "Make the database the single source of truth for prices, not the cache.",
        "가격은 캐시가 아니라 데이터베이스를 유일한 기준으로 삼으세요.",
    ),
    (
        "spaghetti code", "/spəˈɡeti ˌkoʊd/", "흐름이 마구 얽혀 따라가기 힘든 코드",
        REVIEW, E,
        "분기와 호출이 국수 가락처럼 엉켜 실행 흐름을 따라가기 어려운 코드. 한 곳을 고치면 엉뚱한 곳이 깨진다. 처음부터 그렇게 "
        "짜기보다 급한 수정이 오래 쌓여서 생기는 경우가 많다. 정처기에서는 외계인 코드와 함께 나쁜 코드의 예로 나온다.",
        "The checkout module turned into spaghetti code after years of hotfixes.",
        "결제 모듈은 몇 년간 급한 수정이 쌓이면서 스파게티 코드가 됐습니다.",
    ),
    (
        "spike", "/spaɪk/", "모르는 것을 알아보려고 짧게 해 보는 조사 작업",
        REVIEW, H,
        "기술적으로 될지, 얼마나 걸릴지 모를 때 기간을 정해 두고 시험 삼아 해 보는 작업. 결과물은 완성 코드가 아니라 판단과 "
        "추정이다. 정처기에서는 XP 에서 위험을 줄이려고 따로 만드는 간단한 프로그램으로 나온다. 그래프가 치솟는 spike 와 헷갈리기 "
        "쉽다.",
        "Let's do a two-day spike on WebSocket support before estimating.",
        "추정하기 전에 WebSocket 지원을 이틀 동안 시험 삼아 조사해 봅시다.",
    ),
    (
        "TBD", "/ˌti bi ˈdi/", "아직 안 정해짐",
        REVIEW, E,
        "To Be Determined 의 줄임말. 문서나 일정표에서 아직 결정하지 않은 칸에 채워 둔다. 빈칸으로 두면 빠뜨린 것인지 "
        "미정인지 알 수 없어서 이렇게 적는다. 누가 언제 정할지 함께 적어 두지 않으면 그대로 남기 쉽다.",
        "The release date is TBD until QA finishes testing.",
        "QA 테스트가 끝날 때까지 출시일은 미정입니다.",
    ),
    (
        "TODO", "/təˈdu/", "나중에 할 일을 코드에 남긴 표시",
        REVIEW, E,
        "코드 주석 맨 앞에 붙여 아직 덜 된 부분을 표시한다. 편집기와 린트가 이 표시를 모아 보여 준다. 알려진 버그라면 FIXME 를 "
        "쓴다. 이유와 티켓 번호 없이 남긴 TODO 는 아무도 안 건드린 채 몇 년씩 남는 경우가 많다.",
        "Leave a TODO with the ticket number so we don't forget it.",
        "잊지 않게 티켓 번호를 적어서 TODO 를 남겨 두세요.",
    ),
    (
        "typo", "/ˈtaɪpoʊ/", "글자를 잘못 친 것, 오타",
        REVIEW, E,
        "typographical error 의 줄임말. 리뷰에서 가장 흔한 지적 가운데 하나다. 주석이나 문서의 오타는 읽기 불편한 "
        "정도지만, 변수명이나 설정 키의 오타는 실제 버그가 된다. 코멘트 앞에 'typo:' 를 붙여 사소한 지적임을 알리기도 한다.",
        "There's a typo in the env var name, so it never loads.",
        "환경 변수 이름에 오타가 있어서 값이 한 번도 안 읽힙니다.",
    ),
    (
        "user story", "/ˈjuzər ˌstɔri/", "사용자 입장에서 짧게 적은 요구",
        REVIEW, N,
        "사용자로서 무엇을 하고 싶다, 왜냐하면 하는 꼴로 사용자가 원하는 것을 짧게 적은 요구사항. 기능 목록보다 누가 왜 쓰는지가 "
        "드러나서 우선순위를 정하기 쉽다. 정처기에서는 XP 개발 과정의 첫 단계로 나온다. 줄여서 스토리라고만 부르기도 한다.",
        "Each user story should fit in one sprint.",
        "사용자 스토리 하나는 스프린트 한 번 안에 끝나야 합니다.",
    ),
    (
        "walkthrough", "/ˈwɔkˌθru/", "작성자가 이끌며 함께 훑어보는 검토",
        REVIEW, N,
        "작성자가 코드나 문서를 설명하고 참여자들이 따라가며 문제를 찾는 검토 방식. 자료를 회의 전에 나눠 각자 훑어본 뒤 짧은 회의로 "
        "오류를 일찍 잡는다. 인스펙션보다 형식이 가볍고, 정처기에서는 둘을 견주는 문제로 자주 나온다.",
        "Let's do a quick walkthrough of the new auth flow before merging.",
        "병합하기 전에 새 인증 흐름을 같이 한번 훑어봅시다.",
    ),
    (
        "waterfall", "/ˈwɔtərˌfɔl/", "단계를 차례로 한 번씩만 거치는 개발 방식",
        REVIEW, N,
        "요구 분석, 설계, 구현, 테스트를 폭포가 떨어지듯 순서대로 한 번씩 거치는 개발 방식. 앞 단계가 끝나야 다음으로 가서 관리는 "
        "쉽지만, 뒤늦게 요구가 바뀌면 되돌아가기 어렵다. 정처기에서는 폭포수 모형이라고 부른다.",
        "The client wants a fixed spec up front, which is basically waterfall.",
        "고객이 처음부터 명세를 고정하길 원하는데, 사실상 폭포수 방식입니다.",
    ),
    (
        "WDYT", "/ˌdʌblju di waɪ ˈti/", "어떻게 생각하세요?",
        REVIEW, N,
        "What Do You Think 의 줄임말. 리뷰나 메신저에서 제안을 던지고 상대 의견을 물을 때 문장 끝에 붙인다. 지시가 "
        "아니라 함께 정하자는 뜻이라서 받은 쪽은 다른 의견을 내도 된다. 글에서만 쓰고 말할 때는 풀어서 말한다.",
        "We could cache this per user instead. WDYT?",
        "이건 사용자별로 캐시하는 방법도 있을 것 같아요. 어떻게 생각하세요?",
    ),
    (
        "XP", "/ˌeks ˈpi/", "짝 프로그래밍과 테스트를 중시하는 애자일 방식",
        REVIEW, H,
        "Extreme Programming 의 줄임말. 짝 프로그래밍, 테스트 먼저 작성하기, 작은 릴리스, 리팩터링처럼 좋다고 알려진 "
        "실천을 극단까지 밀어붙이는 애자일 방식이다. 정처기 1과목에서 핵심 가치와 실천 항목을 묻는 문제가 자주 나온다.",
        "Our team borrowed test-first habits from XP.",
        "우리 팀은 XP 에서 테스트를 먼저 쓰는 습관을 가져왔습니다.",
    ),
    # ---------- API ----------
    (
        "200", "/ˌtu ˈhʌndrəd/", "요청이 성공했다는 응답",
        API, E,
        "요청을 정상적으로 처리했다는 상태 코드. 가장 흔하지만, 실패 내용을 본문에 적어 놓고 200 으로 돌려주는 API 도 있어서 "
        "상태 코드만 보고 안심하면 안 된다. 새로 만든 경우는 201, 돌려줄 내용이 없으면 204 가 더 정확하다.",
        "The health check returns 200 even when the database is down.",
        "DB 가 죽어 있어도 헬스 체크는 200 을 돌려줍니다.",
    ),
    (
        "201", "/ˌtu oʊ ˈwʌn/", "새 자원을 만들었다는 응답",
        API, N,
        "요청이 성공해 새 자원이 생겼다는 상태 코드. 주로 POST 로 무언가를 만든 뒤 돌려주고, 새 자원의 주소를 Location "
        "헤더에 함께 담는 것이 관례다. 테스트에서 200 을 기대했다가 201 이 와서 실패하는 일이 흔하다.",
        "Creating a comment should return 201, not 200.",
        "댓글을 만들면 200 이 아니라 201 을 돌려줘야 합니다.",
    ),
    (
        "204", "/ˌtu oʊ ˈfɔr/", "성공했지만 돌려줄 내용이 없다는 응답",
        API, N,
        "요청은 성공했지만 응답 본문이 비어 있다는 상태 코드. 삭제나 설정 저장처럼 결과로 보여줄 것이 없을 때 쓴다. 본문이 없는데 "
        "클라이언트가 무조건 JSON 으로 파싱하려 들면 에러가 나므로 이 경우를 따로 처리한다.",
        "The client crashes because it parses JSON from a 204 response.",
        "클라이언트가 204 응답에서 JSON 을 파싱하려다 죽습니다.",
    ),
    (
        "304", "/ˌθri oʊ ˈfɔr/", "바뀐 게 없으니 갖고 있던 것을 쓰라는 응답",
        API, N,
        "브라우저가 가진 사본이 아직 최신이라 다시 받을 필요가 없다는 상태 코드. ETag 나 수정 시각을 함께 보내 물었을 때 돌아오며 "
        "본문이 없다. 개발자 도구에서 보고 에러로 오해하기 쉽지만 캐시가 제대로 동작한다는 뜻이다.",
        "Most of these requests are 304, so the cache is working.",
        "이 요청들은 대부분 304 라서 캐시가 잘 동작하고 있습니다.",
    ),
    (
        "400", "/ˌfɔr ˈhʌndrəd/", "요청 형식이 잘못됐다는 응답",
        API, E,
        "서버가 요청을 이해할 수 없거나 값이 규칙에 맞지 않을 때 돌려주는 상태 코드. 필수 값이 빠졌거나 JSON 이 깨졌을 때 자주 "
        "본다. 서버가 아니라 보낸 쪽이 고칠 문제라는 뜻이라, 어느 필드가 틀렸는지 응답 본문에 적어 주는 것이 좋다.",
        "The API returns 400 because the email field is missing.",
        "email 필드가 빠져서 API 가 400 을 돌려줍니다.",
    ),
    (
        "404", "/ˌfɔr oʊ ˈfɔr/", "찾는 것이 없다는 응답",
        API, E,
        "요청한 주소나 자원이 없을 때 돌려주는 상태 코드. 주소 오타나 끝에 붙은 슬래시 하나 차이로도 생기니 주소부터 확인한다. 권한 "
        "없는 사람에게 자원이 있다는 사실 자체를 숨기려고 403 대신 404 를 일부러 돌려주기도 한다.",
        "I get a 404 because the URL is missing the version prefix.",
        "URL 에 버전 접두어가 빠져서 404 가 납니다.",
    ),
    (
        "409", "/ˌfɔr oʊ ˈnaɪn/", "지금 상태와 부딪혀 처리할 수 없다는 응답",
        API, N,
        "요청 자체는 올바르지만 서버의 현재 상태와 충돌해 처리할 수 없다는 상태 코드. 이미 있는 이메일로 가입하거나, 다른 사람이 먼저 "
        "고친 데이터를 옛 버전 기준으로 덮어쓰려 할 때 쓴다. 최신 상태를 다시 조회한 뒤 재시도해야 한다.",
        "Return 409 when the username is already taken.",
        "아이디가 이미 쓰이고 있으면 409 를 돌려주세요.",
    ),
    (
        "422", "/ˌfɔr tu ˈtu/", "형식은 맞지만 내용이 규칙에 어긋난다는 응답",
        API, H,
        "요청 형식은 읽을 수 있지만 값이 업무 규칙에 맞지 않아 처리할 수 없다는 상태 코드. 날짜는 제대로 적었는데 종료일이 시작일보다 "
        "앞선 경우가 예다. 이런 검증 실패를 400 으로 돌려주는 프레임워크도 많아서 팀마다 어느 쪽을 쓸지 정해 둔다.",
        "The body is valid JSON, but the API still returns 422.",
        "본문은 올바른 JSON 인데도 API 가 422 를 돌려줍니다.",
    ),
    (
        "500", "/ˌfaɪv ˈhʌndrəd/", "서버 안에서 에러가 났다는 응답",
        API, E,
        "서버 코드에서 예상하지 못한 예외가 나서 요청을 처리하지 못했다는 상태 코드. 보낸 쪽이 아니라 서버가 고칠 문제라 같은 요청을 "
        "다시 보내도 대개 소용이 없다. 사용자에게는 자세한 원인을 숨기고, 개발자는 서버 로그와 스택 트레이스에서 원인을 찾는다.",
        "The endpoint returns 500 when the list is empty.",
        "목록이 비어 있으면 그 엔드포인트가 500 을 돌려줍니다.",
    ),
    (
        "503", "/ˌfaɪv oʊ ˈθri/", "서버가 지금은 요청을 받을 수 없다는 응답",
        API, N,
        "서버가 과부하나 점검 때문에 잠시 요청을 처리할 수 없다는 상태 코드. 코드에 버그가 있다는 500 과 달리 잠시 뒤에는 될 수 "
        "있다는 뜻이다. 함께 오는 Retry-After 헤더가 있으면 그만큼 기다렸다가 다시 시도한다.",
        "We return 503 during the maintenance window.",
        "점검 시간에는 503 을 돌려줍니다.",
    ),
    (
        "access token", "/ˈækses ˌtoʊkən/", "API 를 부를 때 내미는, 수명이 짧은 출입증",
        API, N,
        "로그인한 뒤 받는 값으로, API 를 부를 때마다 함께 보내 누구인지 증명한다. 탈취돼도 피해가 작도록 수명을 몇 분에서 몇 "
        "시간으로 짧게 두고, 만료되면 리프레시 토큰으로 새로 받는다. 브라우저 저장소에 둘지 쿠키에 둘지가 보안 논의의 단골 주제다.",
        "The access token expires after fifteen minutes.",
        "액세스 토큰은 15분 뒤에 만료됩니다.",
    ),
    (
        "base URL", "/ˈbeɪs ˌju ɑr ˌel/", "API 주소들의 공통 앞부분",
        API, E,
        "모든 API 주소 앞에 공통으로 붙는 부분으로, https://api.example.com/v1 같은 값이다. 개발, 스테이징, "
        "운영마다 달라서 코드에 박지 않고 환경 변수로 둔다. 끝에 슬래시를 넣느냐에 따라 경로가 겹치거나 빠지는 실수가 잦다.",
        "Set the base URL in the env file, not in the code.",
        "base URL 은 코드가 아니라 env 파일에 설정하세요.",
    ),
    (
        "Base64", "/ˌbeɪs ˌsɪksti ˈfɔr/", "이진 데이터를 글자로 바꾸는 인코딩",
        API, N,
        "이미지 같은 이진 데이터를 영문자와 숫자 등 64가지 글자로만 바꿔 텍스트처럼 다룰 수 있게 하는 방식. JSON 에 파일을 "
        "담거나 Basic 인증 헤더를 만들 때 쓴다. 누구나 되돌릴 수 있어 암호화가 아니고, 크기도 원본보다 3분의 1쯤 커진다.",
        "The avatar is sent as a Base64 string in the JSON body.",
        "프로필 사진은 JSON 본문에 Base64 문자열로 담겨 옵니다.",
    ),
    (
        "basic auth", "/ˈbeɪsɪk ˌɔθ/", "아이디와 비밀번호를 헤더에 실어 보내는 인증",
        API, N,
        "아이디와 비밀번호를 콜론으로 이어 Base64 로 바꾼 뒤 Authorization 헤더에 담아 보내는 가장 단순한 인증 방식. "
        "Base64 는 누구나 되돌릴 수 있어 암호화가 아니므로 반드시 HTTPS 위에서만 쓴다. 내부 도구나 테스트 서버를 잠깐 막을 "
        "때 흔히 본다.",
        "The staging server is protected with basic auth.",
        "스테이징 서버는 basic auth 로 막혀 있습니다.",
    ),
    (
        "BFF", "/ˌbi ef ˈef/", "화면 종류마다 따로 두는 전용 백엔드",
        API, H,
        "Backend For Frontend 의 줄임말로, 웹과 앱처럼 화면마다 필요한 데이터를 맞춰 주는 중간 서버를 따로 두는 방식. "
        "여러 서비스를 대신 불러 한 번에 묶어 주니 화면 쪽 코드가 단순해진다. 일상 영어의 절친과 철자가 같아 문맥으로 구분한다.",
        "The mobile BFF merges three service calls into one response.",
        "모바일 BFF 가 서비스 세 곳의 호출을 응답 하나로 합칩니다.",
    ),
    (
        "Cache-Control", "/ˈkæʃ kənˌtroʊl/", "응답을 얼마나 오래 저장해도 되는지 정하는 헤더",
        API, N,
        "응답을 브라우저나 중간 서버가 저장해도 되는지, 얼마 동안 써도 되는지 알려주는 HTTP 헤더. max-age 로 기간을 정하고 "
        "no-store 로 저장을 아예 막는다. no-cache 는 저장하지 말라는 뜻이 아니라 쓰기 전에 매번 확인하라는 뜻이라 자주 "
        "헷갈린다.",
        "Add a Cache-Control header so the CDN keeps the image for a day.",
        "CDN 이 이미지를 하루 동안 보관하도록 Cache-Control 헤더를 붙이세요.",
    ),
    (
        "callback URL", "/ˈkɔlˌbæk ˌju ɑr ˌel/", "일이 끝나면 결과를 받을 내 쪽 주소",
        API, N,
        "외부 서비스에 미리 알려 두고, 작업이 끝나면 그쪽이 결과를 보내거나 사용자를 돌려보낼 내 쪽 주소. OAuth 로그인 뒤 돌아올 "
        "주소나 결제 완료 알림을 받을 주소가 예다. 등록해 둔 값과 한 글자라도 다르면 요청이 거절된다.",
        "Login fails because the callback URL does not match the registered one.",
        "콜백 URL 이 등록된 값과 달라서 로그인이 실패합니다.",
    ),
    (
        "credential", "/krəˈdenʃəl/", "내가 누구인지 증명하는 정보",
        API, N,
        "비밀번호, API 키, 토큰, 인증서처럼 신원을 증명하는 정보를 묶어 부르는 말. 보통 복수형 credentials 로 쓰이고, "
        "로그인 실패 메시지의 invalid credentials 가 이것이다. 코드나 저장소에 그대로 적으면 유출되므로 비밀 관리 도구에 "
        "둔다.",
        "Rotate the leaked credential right away.",
        "유출된 인증 정보는 바로 교체하세요.",
    ),
    (
        "curl", "/kɜrl/", "터미널에서 HTTP 요청을 보내는 도구",
        API, E,
        "명령줄에서 주소로 요청을 보내고 응답을 출력하는 도구. API 문서의 예시가 대개 curl 명령으로 적혀 있고, 브라우저 없이 "
        "서버만 따로 확인할 때 쓴다. -v 를 붙이면 헤더까지 보여서 CORS 나 리다이렉트 문제를 가를 때 쓸모가 있다.",
        "Can you share the curl command that reproduces the error?",
        "에러가 재현되는 curl 명령을 공유해 줄 수 있나요?",
    ),
    (
        "DELETE", "/dɪˈlit/", "자원을 지울 때 쓰는 요청 방식",
        API, E,
        "지정한 주소의 자원을 지우는 HTTP 메서드. 성공하면 보통 본문 없이 204 를 돌려준다. 이미 지워진 것을 다시 지우면 404 "
        "가 올 수 있지만 서버에 남는 상태는 같으므로 멱등하다고 본다. 실제로는 행을 지우지 않고 삭제 표시만 하는 경우도 많다.",
        "A DELETE on this endpoint removes the user and their posts.",
        "이 엔드포인트에 DELETE 를 보내면 사용자와 그 글이 함께 지워집니다.",
    ),
    (
        "deserialize", "/diˈsɪriəˌlaɪz/", "받은 문자열을 다시 객체로 되돌리다",
        API, N,
        "JSON 같은 문자열을 프로그램이 다룰 수 있는 객체로 되돌리는 일로, serialize 의 반대 과정이다. 받은 데이터를 믿고 "
        "그대로 객체로 만들면 원치 않는 코드가 실행되는 취약점이 생길 수 있어, 형식이 정해진 데이터만 받아 검증한 뒤 쓴다.",
        "We deserialize the request body into a typed object.",
        "요청 본문을 타입이 정해진 객체로 역직렬화합니다.",
    ),
    (
        "DTO", "/ˌdi ti ˈoʊ/", "계층 사이에 데이터를 실어 나르는 객체",
        API, N,
        "Data Transfer Object 의 줄임말로, 계층이나 서비스 사이에 데이터를 넘길 때 쓰는 단순한 객체. DB 모델을 "
        "그대로 응답으로 내보내면 비밀번호 같은 필드가 새어 나갈 수 있어, 내보낼 필드만 담은 DTO 를 따로 만든다. 로직 없이 값만 "
        "담는 것이 원칙이다.",
        "Map the entity to a DTO before returning it.",
        "엔티티를 돌려주기 전에 DTO 로 바꾸세요.",
    ),
    (
        "GET", "/ɡet/", "데이터를 조회할 때 쓰는 요청 방식",
        API, E,
        "서버에서 데이터를 읽어 올 때 쓰는 HTTP 메서드. 서버의 상태를 바꾸면 안 되고, 보낼 값은 본문이 아니라 쿼리 스트링에 "
        "싣는다. 브라우저와 프록시가 캐시하거나 미리 불러올 수 있어서, GET 으로 삭제 같은 일을 하게 만들면 사고가 난다.",
        "This endpoint should be a GET since it only reads data.",
        "데이터를 읽기만 하니 이 엔드포인트는 GET 이어야 합니다.",
    ),
    (
        "HATEOAS", "", "응답에 다음에 할 수 있는 동작의 링크를 담는 방식",
        API, H,
        "REST 응답 안에 그 자원으로 다음에 할 수 있는 동작의 링크를 함께 담는 방식. 클라이언트가 주소를 외우지 않고 응답을 "
        "따라가게 하자는 생각이다. REST 를 엄격히 따질 때 자주 언급되지만 실제 서비스에서 끝까지 지키는 경우는 드물다.",
        "Our API skips HATEOAS and documents the URLs instead.",
        "우리 API 는 HATEOAS 를 쓰지 않고 URL 을 문서로 정리합니다.",
    ),
    (
        "HMAC", "/ˈeɪtʃ ˌmæk/", "비밀 키로 만든 위조 방지 서명값",
        API, H,
        "메시지와 비밀 키를 함께 해시해 만든 값으로, 내용이 바뀌지 않았고 키를 아는 쪽이 보냈다는 것을 확인할 때 쓴다. 웹훅을 받으면 "
        "헤더의 서명과 직접 계산한 값을 비교하는 것이 대표적이다. 비교할 때는 시간 차로 정보가 새지 않게 상수 시간 비교 함수를 쓴다.",
        "Verify the HMAC signature before processing the webhook.",
        "웹훅을 처리하기 전에 HMAC 서명을 검증하세요.",
    ),
    (
        "HTTP method", "/ˌeɪtʃ ti ti ˈpi ˌmeθəd/", "요청이 무엇을 하려는지 나타내는 동사",
        API, E,
        "GET, POST, PUT, DELETE 처럼 요청 맨 앞에 붙어 무엇을 하려는지 알려주는 말. 같은 주소라도 메서드에 따라 "
        "조회가 되기도 하고 삭제가 되기도 한다. 405 에러는 그 주소가 해당 메서드를 받지 않는다는 뜻이다.",
        "Check the HTTP method first; this route only accepts POST.",
        "먼저 HTTP 메서드를 확인하세요. 이 경로는 POST 만 받습니다.",
    ),
    (
        "HttpOnly", "/ˌeɪtʃ ti ti pi ˈoʊnli/", "스크립트가 쿠키를 못 읽게 막는 설정",
        API, N,
        "쿠키에 붙이는 속성으로, 브라우저의 자바스크립트가 그 쿠키를 읽지 못하게 막는다. XSS 로 악성 스크립트가 실행돼도 세션 쿠키를 "
        "빼 가지 못한다. 쿠키가 요청에 실려 가는 것까지 막지는 않으므로 CSRF 대책은 따로 필요하다.",
        "Mark the session cookie as HttpOnly.",
        "세션 쿠키에 HttpOnly 를 붙이세요.",
    ),
    (
        "IDOR", "", "ID 만 바꿔 남의 데이터를 보는 취약점",
        API, H,
        "요청에 든 ID 값만 바꾸면 남의 데이터를 볼 수 있는 취약점. /orders/101 을 /orders/102 로 바꿨는데 다른 "
        "사람 주문이 보이는 경우다. 로그인 여부만 확인하고 그 데이터의 주인인지 확인하는 것을 빠뜨려서 생긴다.",
        "Changing the order ID in the URL exposes an IDOR bug.",
        "URL 의 주문 ID 만 바꿔도 IDOR 버그가 드러납니다.",
    ),
    (
        "input validation", "/ˈɪnpʊt ˌvæləˌdeɪʃən/", "들어온 값이 규칙에 맞는지 확인하는 것",
        API, N,
        "사용자가 보낸 값의 형식과 길이, 범위가 맞는지 처리하기 전에 확인하는 일. 화면에서 이미 막았더라도 요청은 얼마든지 직접 만들어 "
        "보낼 수 있어서 서버에서 다시 해야 한다. 정처기 시큐어 코딩에서는 보안 약점의 첫 번째 분류로 나온다.",
        "Client checks are not enough; add input validation on the server.",
        "화면 쪽 검사만으로는 부족합니다. 서버에도 입력값 검증을 넣으세요.",
    ),
    (
        "login", "/ˈlɔɡɪn/", "아이디와 비밀번호 등을 넣고 서비스에 들어가는 것",
        API, E,
        "사용자가 누구인지 확인받고 서비스에 들어가는 일. 붙여 쓴 login 은 명사나 형용사이고, 동사로 쓸 때는 log in 처럼 "
        "띄어 쓰는 것이 바른 영어다. 로그인 API 는 비밀번호를 마구 대입하는 공격의 표적이 되기 쉬워 시도 횟수 제한을 함께 둔다.",
        "The login endpoint allows five attempts per minute.",
        "로그인 엔드포인트는 1분에 다섯 번까지만 시도할 수 있습니다.",
    ),
    (
        "long polling", "/ˈlɔŋ ˌpoʊlɪŋ/", "새 소식이 생길 때까지 응답을 붙잡아 두는 방식",
        API, N,
        "클라이언트가 요청을 보내면 서버가 새 데이터가 생길 때까지 응답을 미뤘다가 보내는 방식. 받자마자 다시 요청해 실시간에 가깝게 "
        "만든다. 일정 간격으로 묻는 폴링보다 헛걸음이 적지만, 열린 연결이 많아지면 서버 자원을 붙잡는다.",
        "We fall back to long polling when WebSocket is blocked.",
        "WebSocket 이 막히면 롱 폴링으로 대신합니다.",
    ),
    (
        "middleware", "/ˈmɪdəlˌwer/", "프로그램 사이에 끼어 요청을 중계하거나 공통 일을 하는 소프트웨어",
        API, N,
        "요청이 처리 함수에 닿기 전후로 늘 거쳐 가는 코드. 로그인 확인, 로그 남기기, CORS 헤더 붙이기처럼 매번 반복할 일을 "
        "한곳에 모으며, 등록 순서에 따라 결과가 달라진다. 정처기에서는 운영체제와 응용 프로그램 사이를 잇는 소프트웨어라는 더 넓은 "
        "뜻으로 나온다.",
        "The auth middleware rejects the request before it reaches the view.",
        "인증 미들웨어가 요청이 뷰에 닿기 전에 막습니다.",
    ),
    (
        "multipart", "/ˈmʌltiˌpɑrt/", "파일과 값을 여러 덩어리로 나눠 보내는 형식",
        API, N,
        "요청 본문 하나를 경계 문자열로 여러 부분으로 나눠 파일과 일반 값을 함께 보내는 형식. 파일 업로드에 쓰이며 "
        "Content-Type 은 multipart/form-data 다. 이 헤더를 손으로 적으면 경계 값이 빠져 서버가 못 읽으니 "
        "라이브러리에 맡긴다.",
        "Upload the file as multipart form data, not JSON.",
        "파일은 JSON 이 아니라 multipart 폼 데이터로 올리세요.",
    ),
    (
        "nonce", "/nɑns/", "한 번만 쓰고 버리는 임의의 값",
        API, H,
        "'이번 한 번' 을 뜻하는 영어 단어로, 흔히 number used once 로 풀어 기억하는 한 번만 쓰는 임의의 값. 같은 "
        "요청을 다시 보내는 공격을 막거나, CSP 에서 실행을 허용할 스크립트를 표시할 때 쓴다. 매번 새로 만들어야 의미가 있고, "
        "고정값을 쓰면 없는 것과 같다.",
        "Each webhook includes a nonce so we can reject duplicates.",
        "웹훅마다 nonce 가 들어 있어서 중복을 걸러낼 수 있습니다.",
    ),
    (
        "over-fetching", "/ˌoʊvərˈfetʃɪŋ/", "필요한 것보다 많은 데이터를 받아 오는 것",
        API, H,
        "화면에는 이름 하나만 필요한데 API 가 사용자 정보를 통째로 돌려주는 것처럼, 쓰지도 않을 데이터까지 받아 오는 상황. "
        "모바일에서는 전송량과 속도에 바로 영향을 준다. 반대로 모자라서 여러 번 불러야 하는 상황은 under-fetching 이라 "
        "한다.",
        "GraphQL helps us avoid over-fetching on the profile screen.",
        "GraphQL 덕분에 프로필 화면에서 쓰지도 않을 데이터를 받아 오지 않습니다.",
    ),
    (
        "permission", "/pərˈmɪʃən/", "글 삭제처럼 동작 하나하나에 주어진 권한",
        API, E,
        "사용자가 어떤 자원에 무엇을 할 수 있는지 정한 허락. 로그인했다고 모든 것을 할 수 있는 것은 아니어서, 글을 고치려면 "
        "작성자인지 따로 확인해야 한다. 로그인은 됐는데 권한이 없을 때는 401 이 아니라 403 을 돌려준다.",
        "Only admins have permission to delete posts.",
        "글 삭제 권한은 관리자에게만 있습니다.",
    ),
    (
        "PKCE", "/ˈpɪksi/", "가로챈 인가 코드를 못 쓰게 막는 OAuth 장치",
        API, H,
        "모바일 앱이나 SPA 처럼 비밀 키를 숨길 수 없는 클라이언트가 OAuth 로그인을 안전하게 하도록 덧붙이는 절차. 시작할 때 "
        "만든 임의의 값을 마지막에 다시 내밀게 해서, 중간에 인가 코드를 가로챈 쪽은 토큰을 못 받는다. 픽시라고 읽는다.",
        "Enable PKCE for the mobile login flow.",
        "모바일 로그인 흐름에는 PKCE 를 켜세요.",
    ),
    (
        "POST", "/poʊst/", "새 데이터를 보내 만들 때 쓰는 요청 방식",
        API, E,
        "본문에 데이터를 실어 서버에 보내는 HTTP 메서드. 주로 새 항목을 만들 때 쓰고, 다른 메서드에 딱 맞지 않는 동작에도 쓴다. "
        "멱등하지 않아서 같은 요청을 두 번 보내면 주문이 두 건 생길 수 있다는 점을 늘 염두에 둔다.",
        "Send a POST to /orders with the cart items in the body.",
        "장바구니 항목을 본문에 담아 /orders 로 POST 를 보내세요.",
    ),
    (
        "pub/sub", "/ˈpʌb ˌsʌb/", "주제를 사이에 두고 메시지를 올리고 받아 가는 방식",
        API, H,
        "publish 와 subscribe 를 줄인 말로, 보내는 쪽은 주제에 메시지를 올리기만 하고 그 주제를 구독한 쪽이 각자 받아 "
        "가는 방식. 보내는 쪽이 누가 받는지 몰라도 되니 서비스끼리 덜 엮인다. 받는 쪽이 꺼져 있을 때 메시지가 남는지는 도구마다 달라 "
        "확인한다.",
        "We moved notifications to pub/sub to keep the order service simple.",
        "주문 서비스를 단순하게 두려고 알림을 pub/sub 으로 옮겼습니다.",
    ),
    (
        "PUT", "/pʊt/", "자원을 통째로 바꿀 때 쓰는 요청 방식",
        API, E,
        "지정한 주소의 자원을 보낸 내용으로 통째로 갈아 끼우는 HTTP 메서드. 빠뜨린 필드는 비워지는 것이 원칙이라, 바뀐 값만 보내면 "
        "나머지가 사라질 수 있다. 일부만 고칠 때는 PATCH 를 쓴다. 여러 번 보내도 결과가 같은 멱등한 메서드다.",
        "Use PUT only when the client sends the whole object.",
        "클라이언트가 객체 전체를 보낼 때만 PUT 을 쓰세요.",
    ),
    (
        "Referer", "/rɪˈfɜrər/", "어느 페이지에서 넘어왔는지 알려주는 헤더",
        API, H,
        "요청이 어느 페이지에서 시작됐는지 담아 보내는 HTTP 헤더. 영어 단어 referrer 를 표준 문서에 잘못 적은 철자가 그대로 "
        "굳어서 r 이 하나 빠져 있다. 주소에 토큰이 들어 있으면 이 헤더를 타고 외부 사이트로 새어 나갈 수 있다.",
        "The Referer header leaks the reset token to the analytics script.",
        "Referer 헤더 때문에 비밀번호 재설정 토큰이 분석 스크립트로 새어 나갑니다.",
    ),
    (
        "replay attack", "/ˈriˌpleɪ əˌtæk/", "가로챈 요청을 그대로 다시 보내는 공격",
        API, H,
        "정상적으로 오간 요청을 가로채 내용을 바꾸지 않고 다시 보내는 공격. 서명이 올바르니 서버는 진짜 요청으로 믿고, 결제나 "
        "송금이라면 두 번 처리된다. 요청에 시각과 nonce 를 넣어 두고, 오래됐거나 이미 쓴 요청은 거절하는 방식으로 막는다.",
        "Check the timestamp on each webhook to block a replay attack.",
        "재전송 공격을 막으려면 웹훅마다 타임스탬프를 확인하세요.",
    ),
    (
        "request", "/rɪˈkwest/", "클라이언트가 서버에 보내는 부탁",
        API, E,
        "클라이언트가 서버에 무언가를 해 달라고 보내는 메시지. 메서드와 주소, 헤더, 본문으로 이루어진다. 요청 하나에 응답 하나가 "
        "돌아오는 것이 HTTP 의 기본 구조이고, 로그에서 문제를 좁힐 때도 요청 하나하나를 단위로 나눠 본다.",
        "Each request takes about two seconds on staging.",
        "스테이징에서는 요청마다 2초 정도 걸립니다.",
    ),
    (
        "resource", "/ˈrisɔrs/", "API 주소 하나가 가리키는 대상",
        API, N,
        "REST 에서 주소 하나가 가리키는 대상. 사용자, 주문, 댓글처럼 명사로 이름 짓고, 목록은 /users, 하나는 "
        "/users/3 처럼 가리킨다. 무엇을 할지는 주소가 아니라 메서드로 나타내므로, /getUser 처럼 주소에 동사를 넣으면 이 "
        "원칙에서 벗어난 설계로 본다.",
        "Name each resource with a plural noun, like /users.",
        "리소스 이름은 /users 처럼 복수 명사로 지으세요.",
    ),
    (
        "response", "/rɪˈspɑns/", "서버가 요청에 돌려주는 답",
        API, E,
        "서버가 요청을 처리하고 돌려주는 메시지. 상태 코드와 헤더, 본문으로 이루어진다. 본문만 보고 판단하기 쉽지만 실패 이유나 캐시 "
        "정보가 상태 코드와 헤더에 담긴 경우가 많아 함께 봐야 한다. 정해진 시간 안에 오지 않으면 타임아웃으로 처리한다.",
        "The response is missing the total count field.",
        "응답에 전체 개수 필드가 빠져 있습니다.",
    ),
    (
        "route", "/raʊt/", "어떤 주소를 어느 코드가 처리할지 이은 규칙",
        API, N,
        "요청 주소와 메서드를 보고 어느 함수가 처리할지 이어 둔 규칙. 새 API 를 만들면 처리 함수와 함께 라우트도 등록해야 하고, "
        "빠뜨리면 404 가 난다. 비슷한 주소의 라우트가 여럿이면 먼저 적힌 것이 요청을 가로채는 일이 있어 순서를 확인한다.",
        "I added the view but forgot to register the route.",
        "뷰는 만들었는데 라우트 등록을 깜빡했습니다.",
    ),
    (
        "sanitize", "/ˈsænəˌtaɪz/", "위험한 부분을 걸러 내 안전하게 만들다",
        API, N,
        "들어온 값에서 스크립트 태그 같은 위험한 부분을 지우거나 바꿔 안전하게 만드는 일. 형식이 틀리면 거절하는 검증과 달리, "
        "받아들이되 해가 없게 다듬는다. 직접 만든 정규식으로 하면 빈틈이 생기기 쉬워 검증된 라이브러리를 쓴다.",
        "Sanitize the HTML before saving the comment.",
        "댓글을 저장하기 전에 HTML 을 정제하세요.",
    ),
    (
        "SDK", "/ˌes di ˈkeɪ/", "서비스를 코드에서 쉽게 쓰게 묶어 준 도구 모음",
        API, N,
        "서비스나 플랫폼을 코드에서 쓰기 쉽게 만든 라이브러리와 도구 묶음. 결제나 클라우드 API 를 직접 HTTP 로 부르는 대신 "
        "SDK 의 함수를 쓰면 인증과 재시도를 대신 처리해 준다. 버전을 올리면 동작이 바뀌기도 해서 변경 기록을 확인한다.",
        "Use the official SDK instead of calling the REST API directly.",
        "REST API 를 직접 부르지 말고 공식 SDK 를 쓰세요.",
    ),
    (
        "session hijacking", "/ˈseʃən ˌhaɪdʒækɪŋ/", "남의 세션을 가로채 그 사람인 척하는 공격",
        API, H,
        "로그인한 사용자의 세션 ID 나 쿠키를 훔쳐 비밀번호 없이 그 사람으로 행세하는 공격. 쿠키에 HttpOnly 와 Secure 를 "
        "붙여 훔치기 어렵게 만든다. 정처기에서는 TCP 연결의 순서 번호를 가로채 끼어드는 TCP 세션 하이재킹으로 주로 나온다.",
        "Setting HttpOnly on the cookie makes session hijacking harder.",
        "쿠키에 HttpOnly 를 붙이면 세션 하이재킹이 어려워집니다.",
    ),
    (
        "SSRF", "/ˌes es ɑr ˈef/", "서버를 속여 내부 주소로 요청을 보내게 하는 공격",
        API, H,
        "서버가 사용자가 준 URL 로 요청을 보내는 기능을 악용해, 밖에서는 닿지 않는 내부 서버나 클라우드 설정 주소를 부르게 만드는 "
        "공격. URL 로 이미지 가져오기나 웹훅 주소 등록 기능에서 자주 생긴다. 허용한 주소만 부를 수 있게 막는다.",
        "The image import feature is vulnerable to SSRF.",
        "이미지 가져오기 기능에 SSRF 취약점이 있습니다.",
    ),
    (
        "streaming", "/ˈstrimɪŋ/", "다 만들기 전부터 조금씩 흘려보내는 방식",
        API, N,
        "응답을 한꺼번에 만들어 보내지 않고 준비되는 대로 조각조각 보내는 방식. 큰 파일을 내려받거나 AI 답변이 한 글자씩 나타나는 "
        "화면이 예다. 중간의 프록시가 응답을 모아 두었다가 보내면 효과가 사라지므로 버퍼링 설정을 확인한다.",
        "Enable streaming so users see the first rows right away.",
        "사용자가 첫 줄부터 바로 볼 수 있게 스트리밍을 켜세요.",
    ),
    (
        "trailing slash", "/ˈtreɪlɪŋ ˌslæʃ/", "주소 맨 끝에 붙은 빗금",
        API, N,
        "/users/ 처럼 주소 맨 끝에 붙은 슬래시. 서버에 따라 있을 때와 없을 때를 다른 주소로 봐서 404 가 나거나 리다이렉트가 "
        "끼어든다. 리다이렉트를 거치면서 POST 본문이 사라지는 일도 있어 팀 안에서 한 가지로 정해 둔다.",
        "The POST fails because the URL has no trailing slash.",
        "URL 끝에 슬래시가 없어서 POST 가 실패합니다.",
    ),
    (
        "URL encoding", "/ˌju ɑr ˈel ɪnˌkoʊdɪŋ/", "주소에 못 쓰는 글자를 % 와 16진수로 바꾸기",
        API, N,
        "주소에 그대로 넣을 수 없는 한글이나 공백, & 같은 글자를 %EC%95%88 처럼 바꿔 적는 방식으로, 퍼센트 인코딩이라고도 "
        "한다. 빼먹으면 & 뒤가 다른 파라미터로 잘리고, 두 번 하면 %25 가 섞여 글자가 깨진다.",
        "Korean search terms break because we skip URL encoding.",
        "URL 인코딩을 빼먹어서 한글 검색어가 깨집니다.",
    ),
    (
        "user agent", "/ˈjuzər ˌeɪdʒənt/", "요청을 보낸 브라우저나 앱을 알려주는 값",
        API, N,
        "요청을 보낸 브라우저나 앱, 도구가 무엇인지 적힌 문자열로 User-Agent 헤더에 실린다. 로그에서 봇이나 오래된 브라우저를 "
        "가려낼 때 쓴다. 클라이언트가 마음대로 바꿀 수 있는 값이라 보안 판단의 근거로 삼으면 안 된다.",
        "Most of the spike comes from a single user agent.",
        "급증한 요청 대부분이 유저 에이전트 하나에서 왔습니다.",
    ),
    (
        "X-Forwarded-For", "/ˌeks ˈfɔrwərdɪd ˌfɔr/", "프록시를 거치기 전 원래 클라이언트 IP 를 담는 헤더",
        API, H,
        "로드 밸런서나 프록시를 거치면 서버에는 그 장비의 IP 만 보이므로, 처음 요청한 쪽의 IP 를 담아 넘겨주는 헤더. 프록시를 "
        "여러 번 거치면 IP 가 쉼표로 이어 붙는다. 클라이언트가 직접 써 넣을 수도 있어서, 믿을 수 있는 프록시가 붙인 값만 써야 "
        "한다.",
        "Read the client IP from X-Forwarded-For, not the socket address.",
        "클라이언트 IP 는 소켓 주소가 아니라 X-Forwarded-For 에서 읽으세요.",
    ),
    # ---------- 데이터베이스 ----------
    (
        "1NF", "/ˌwʌn en ˈef/", "한 칸에 값을 하나씩만 넣은 정규화 첫 단계",
        DB, N,
        "모든 칸에 더 쪼갤 수 없는 값 하나만 들어가게 만든 상태로, 정규화의 첫 단계다. 태그를 쉼표로 이어 한 칸에 넣으면 이것을 "
        "어긴 것이고, 특정 태그로 검색하거나 조인하기가 어려워진다. 정처기에서는 원자값이라는 말로 묻는다.",
        "Storing comma-separated tag ids breaks 1NF.",
        "태그 id 를 쉼표로 이어 저장하면 제1정규형을 어깁니다.",
    ),
    (
        "aggregate function", "/ˈæɡrɪɡət ˌfʌŋkʃən/", "여러 행을 묶어 값 하나로 계산하는 함수",
        DB, E,
        "COUNT, SUM, AVG, MAX 처럼 여러 행을 받아 값 하나를 돌려주는 함수. group by 와 함께 쓰면 묶음마다 "
        "하나씩 계산한다. COUNT(*) 를 뺀 대부분은 NULL 을 건너뛰어서, 평균이 예상과 다르면 빈 값이 빠졌는지 확인한다.",
        "Wrap it in an aggregate function or add it to the group by.",
        "집계 함수로 감싸거나 group by 에 넣으세요.",
    ),
    (
        "anomaly", "/əˈnɑməli/", "정규화가 덜 돼 생기는 삽입·삭제·갱신 문제",
        DB, H,
        "중복이 많은 표에서 데이터를 넣거나 지우거나 고칠 때 생기는 문제. 고객 주소를 주문마다 적어 두면 한 곳만 고쳐 값이 엇갈리는 "
        "갱신 이상이, 마지막 주문을 지우면 고객 정보까지 사라지는 삭제 이상이 생긴다. 정처기에서는 삽입, 삭제, 갱신 세 가지를 구분해 "
        "묻는다.",
        "Duplicating the address in every order leads to an update anomaly.",
        "주문마다 주소를 중복 저장하면 갱신 이상이 생깁니다.",
    ),
    (
        "attribute", "/ˈætrɪˌbjut/", "개체가 가진 성질 하나, 표의 열에 해당",
        DB, N,
        "개체를 설명하는 성질 하나로, 회원이라면 이름과 이메일이 여기에 든다. 관계형 모델에서는 열을 이렇게 부르고, 정처기에서는 속성의 "
        "개수를 차수라고 부른다. HTML 태그의 속성도 같은 단어라서 어느 맥락인지 보고 구분한다.",
        "Email is an attribute of the user, not a separate entity.",
        "이메일은 사용자의 속성이지 별도 엔티티가 아닙니다.",
    ),
    (
        "autocommit", "/ˌɔtoʊkəˈmɪt/", "쿼리마다 바로 확정하는 모드",
        DB, E,
        "쿼리 하나가 끝날 때마다 자동으로 커밋하는 동작. 많은 드라이버와 프레임워크가 기본으로 켜 두어서, 여러 쿼리를 묶으려면 "
        "트랜잭션을 직접 시작해야 한다. 반대로 이게 꺼진 도구에서 수정만 하고 커밋을 잊으면 다른 연결에서는 안 보인다.",
        "Autocommit is on, so each statement is saved immediately.",
        "오토커밋이 켜져 있어서 문장마다 바로 저장됩니다.",
    ),
    (
        "B-tree", "/ˈbi ˌtri/", "대부분의 인덱스가 쓰는 균형 잡힌 트리 구조",
        DB, N,
        "자식을 여러 개 갖는 트리를 늘 높이가 고르게 유지해서, 데이터가 많아도 몇 번만 내려가면 값을 찾는 구조. 데이터베이스가 "
        "인덱스를 만들 때 기본으로 쓰는 방식이다. 이진 트리와 이름이 비슷하지만 B 는 binary 의 약자가 아니다.",
        "Postgres creates a B-tree index by default.",
        "Postgres 는 기본으로 B-트리 인덱스를 만듭니다.",
    ),
    (
        "BCNF", "/ˌbi si en ˈef/", "모든 결정자가 후보키인 정규형",
        DB, H,
        "3정규형보다 한 단계 엄격하게, 다른 속성을 결정하는 칸이 전부 후보키여야 하는 정규형. 이름은 만든 두 사람인 보이스와 코드에서 "
        "왔다. 실무에서는 3정규형까지만 맞추는 경우가 많지만 정처기에서는 단계 순서를 자주 묻는다.",
        "The table is in 3NF but not in BCNF yet.",
        "이 테이블은 3정규형이지만 아직 BCNF 는 아닙니다.",
    ),
    (
        "bulk insert", "/ˈbʌlk ˌɪnsɜrt/", "여러 행을 쿼리 한 번에 넣기",
        DB, E,
        "행을 하나씩 넣는 대신 수백, 수천 개를 쿼리 한 번에 넣는 것. 데이터베이스와 오가는 횟수가 줄어 훨씬 빠르다. 다만 ORM 에 "
        "따라 저장할 때 도는 훅이나 시그널이 실행되지 않아서, 거기에 걸린 로직이 조용히 빠질 수 있다.",
        "Switch to a bulk insert; saving rows one by one takes minutes.",
        "벌크 인서트로 바꾸세요. 한 행씩 저장하면 몇 분이 걸립니다.",
    ),
    (
        "checkpoint", "/ˈtʃekˌpɔɪnt/", "메모리의 변경을 디스크에 확정해 두는 시점",
        DB, N,
        "메모리에만 있던 변경 내용을 디스크에 써서, 장애가 나면 그 시점 이후의 로그만 다시 적용하면 되게 하는 지점. 너무 자주 하면 "
        "디스크 쓰기가 몰리고 너무 드물면 복구가 오래 걸린다. 정처기에서는 회복 기법의 검사점으로 나온다.",
        "Recovery was fast because a checkpoint ran just before the crash.",
        "장애 직전에 체크포인트가 돌아서 복구가 빨랐습니다.",
    ),
    (
        "clustered index", "/ˈklʌstərd ˌɪndeks/", "행을 인덱스 순서대로 저장한 인덱스",
        DB, H,
        "표의 실제 행을 인덱스 키 순서대로 저장하는 인덱스로, 표 하나에 하나만 둘 수 있다. MySQL InnoDB 에서는 기본키가 곧 "
        "이것이라 범위 조회가 빠르다. 대신 UUID v4 처럼 무작위 값을 기본키로 쓰면 삽입마다 중간에 끼워 넣느라 느려진다.",
        "In InnoDB, the primary key is the clustered index.",
        "InnoDB 에서는 기본키가 곧 클러스터드 인덱스입니다.",
    ),
    (
        "coalesce", "/ˌkoʊəˈles/", "앞에서부터 NULL 이 아닌 첫 값을 고르는 함수",
        DB, N,
        "인자를 차례로 보다가 NULL 이 아닌 첫 값을 돌려주는 SQL 함수. 빈 값 대신 0 이나 기본 문구를 보여줄 때 쓰고, "
        "대부분의 데이터베이스에서 같은 이름으로 쓸 수 있다. 영어 단어 자체가 낯설어 읽기부터 막히는데, 여러 갈래가 합쳐져 하나가 "
        "된다는 뜻에서 왔다.",
        "Use coalesce so the total shows 0 instead of null.",
        "합계가 null 대신 0 으로 나오게 coalesce 를 쓰세요.",
    ),
    (
        "column", "/ˈkɑləm/", "같은 종류 값이 모인 세로 칸을 SQL 에서 부르는 말",
        DB, E,
        "표의 세로 칸으로, 이메일이나 가입일처럼 모든 행이 같은 종류의 값을 가진다. 칸마다 자료형과 제약이 정해지고, 필드라고도 "
        "부른다. 큰 표에 기본값 없는 NOT NULL 칸을 추가하면 마이그레이션이 실패하거나 오래 걸리니 조심한다.",
        "Add a nullable column first, then backfill it.",
        "먼저 null 을 허용하는 칼럼을 추가하고, 그다음 값을 채우세요.",
    ),
    (
        "composite index", "/kəmˈpɑzɪt ˌɪndeks/", "여러 칸을 순서대로 묶어 만든 인덱스",
        DB, N,
        "두 개 이상의 칸을 정해진 순서로 묶은 인덱스. 앞쪽 칸부터 조건에 써야 효과가 있어서, user_id 와 날짜를 묶은 인덱스는 "
        "user_id 조건 없이 날짜만 걸면 잘 안 쓰인다. 어떤 칸을 앞에 둘지는 자주 쓰는 조건을 보고 정한다.",
        "Put user_id first in the composite index; we always filter by it.",
        "복합 인덱스에서 user_id 를 앞에 두세요. 항상 그걸로 거릅니다.",
    ),
    (
        "concurrency control", "/kənˈkɜrənsi kənˌtroʊl/", "동시에 도는 트랜잭션이 서로 망치지 않게 하는 장치",
        DB, N,
        "여러 트랜잭션이 같은 데이터를 동시에 건드려도, 하나씩 차례로 실행한 것과 같은 결과가 나오도록 조율하는 기법. 락, 타임스탬프, "
        "MVCC 가 대표적인 방법이다. 정처기에서는 이것이 없을 때 생기는 갱신 분실 같은 문제와 함께 묻는다.",
        "Without proper concurrency control, two refunds could both succeed.",
        "병행 제어가 제대로 없으면 환불 두 건이 둘 다 처리될 수 있습니다.",
    ),
    (
        "connection string", "/kəˈnekʃən ˌstrɪŋ/", "데이터베이스 접속 정보를 한 줄로 적은 문자열",
        DB, E,
        "주소, 포트, 데이터베이스 이름, 사용자, 비밀번호를 한 줄로 이어 쓴 접속 정보. postgres:// 로 시작하는 "
        "DATABASE_URL 이 대표적이다. 비밀번호가 들어 있어서 코드나 로그에 그대로 남기면 안 되고 환경 변수로 넘긴다.",
        "Never log the connection string; it contains the password.",
        "접속 문자열은 로그에 남기지 마세요. 비밀번호가 들어 있습니다.",
    ),
    (
        "covering index", "/ˈkʌvərɪŋ ˌɪndeks/", "필요한 칸이 다 있어 표를 안 읽어도 되는 인덱스",
        DB, H,
        "쿼리가 쓰는 칸이 모두 인덱스 안에 들어 있어, 표 본체를 읽지 않고 인덱스만으로 답하는 경우. 실행 계획에 Index Only "
        "Scan 이나 Using index 로 나온다. SELECT * 를 쓰면 이 이점을 잃기 쉬워서 필요한 칸만 고르라는 리뷰가 "
        "붙는다.",
        "With a covering index, the query never touches the table.",
        "커버링 인덱스가 있으면 쿼리가 테이블을 아예 읽지 않습니다.",
    ),
    (
        "data warehouse", "/ˈdeɪtə ˌwerhaʊs/", "분석용으로 여러 곳의 데이터를 모아 둔 저장소",
        DB, N,
        "서비스 데이터베이스와 따로, 여러 시스템의 데이터를 모아 분석하기 좋게 정리한 저장소. 무거운 집계를 운영 데이터베이스에서 돌리지 "
        "않으려고 둔다. 보통 하루나 한 시간 단위로 채워져서 실시간 숫자와 조금 다를 수 있다.",
        "Run that report against the data warehouse, not production.",
        "그 리포트는 운영 DB 가 아니라 데이터 웨어하우스에서 돌리세요.",
    ),
    (
        "distinct", "/dɪˈstɪŋkt/", "겹치는 행을 하나만 남기기",
        DB, E,
        "조회 결과에서 완전히 같은 행이 여러 번 나오면 하나만 남기는 키워드. 조인 뒤 결과가 부풀었을 때 급하게 붙이기 쉬운데, 그러면 "
        "중복이 왜 생겼는지가 가려진다. 데이터가 많으면 정렬이나 해시 작업이 붙어 느려지기도 한다.",
        "Using distinct here hides the real problem, which is the duplicate join.",
        "여기서 distinct 를 쓰면 진짜 문제인 중복 조인이 가려집니다.",
    ),
    (
        "document database", "/ˈdɑkjəmənt ˌdeɪtəˌbeɪs/", "JSON 같은 문서 단위로 저장하는 데이터베이스",
        DB, N,
        "행과 열 대신 JSON 과 비슷한 문서를 통째로 저장하는 데이터베이스. 문서마다 모양이 달라도 되어 처음에는 편하지만, 같은 "
        "정보를 여러 문서에 복사해 두는 일이 많아 고칠 때 빠뜨리기 쉽다. MongoDB 가 대표적이다.",
        "A document database fits this, since each form has different fields.",
        "양식마다 항목이 달라서 문서형 데이터베이스가 잘 맞습니다.",
    ),
    (
        "entity", "/ˈentəti/", "데이터로 관리하려는 대상 하나",
        DB, E,
        "회원, 주문, 상품처럼 저장하고 관리할 가치가 있는 대상. 설계 단계에서 무엇을 개체로 볼지 정하면 보통 그것이 표 하나가 되고, "
        "개체의 성질은 칸이 된다. ORM 에서는 표와 연결된 클래스를 이 이름으로 부르기도 해서 업무에서도 자주 듣는다.",
        "In the ERD, each entity usually becomes one table.",
        "ERD 에서 엔티티 하나는 보통 테이블 하나가 됩니다.",
    ),
    (
        "entity integrity", "/ˈentəti ɪnˌteɡrəti/", "기본키는 비거나 겹치면 안 된다는 규칙",
        DB, N,
        "기본키를 이루는 칸에는 NULL 이 올 수 없고 값이 겹쳐서도 안 된다는 규칙. 행을 구별하는 값이 비거나 같으면 어느 행을 "
        "가리키는지 알 수 없기 때문이다. 데이터베이스가 기본키 제약으로 알아서 지켜 주며, 정처기에서는 외래키 쪽 규칙인 참조 무결성과 "
        "짝지어 묻는다.",
        "A null primary key would violate entity integrity.",
        "기본키가 null 이면 개체 무결성을 어기게 됩니다.",
    ),
    (
        "exclusive lock", "/ɪkˈsklusɪv ˌlɑk/", "다른 트랜잭션이 어떤 락도 못 걸게 막는 락",
        DB, N,
        "데이터를 고치는 트랜잭션이 거는 락으로, 걸려 있는 동안 다른 트랜잭션은 같은 데이터에 공유 락도 배타 락도 걸 수 없다. "
        "교재에서는 읽기까지 막는다고 배우지만, MVCC 를 쓰는 데이터베이스에서는 락 없이 읽는 일반 조회는 막히지 않는다.",
        "The update holds an exclusive lock until the transaction commits.",
        "그 수정은 트랜잭션이 커밋될 때까지 배타 락을 잡고 있습니다.",
    ),
    (
        "execution plan", "/ˌeksɪˈkjuʃən ˌplæn/", "쿼리를 어떤 순서와 방법으로 처리할지 세운 계획",
        DB, N,
        "데이터베이스는 쿼리를 받으면 인덱스를 쓸지, 어떤 순서로 조인할지 정한 계획을 먼저 세운다. explain 으로 이 계획을 볼 수 "
        "있고, 느린 쿼리는 대개 여기서 전체 스캔이나 잘못된 조인 순서로 드러난다. 같은 쿼리도 데이터 양이 바뀌면 계획이 달라진다.",
        "The execution plan changed after the table grew, and now it skips the index.",
        "테이블이 커지자 실행 계획이 바뀌어서 이제 인덱스를 건너뜁니다.",
    ),
    (
        "functional dependency", "/ˈfʌŋkʃənəl dɪˌpendənsi/", "한 칸 값이 정해지면 다른 칸 값도 정해지는 관계",
        DB, H,
        "어떤 속성 값을 알면 다른 속성 값이 하나로 정해지는 관계로, 학번을 알면 이름이 정해지는 식이다. 정규화의 각 단계가 이 관계를 "
        "기준으로 표를 나눈다. 정처기에서는 X 가 Y 를 결정한다고 읽고 X 를 결정자라 부른다.",
        "Since email determines name, there is a functional dependency between them.",
        "이메일이 이름을 결정하니 둘 사이에 함수 종속이 있습니다.",
    ),
    (
        "grant", "/ɡrænt/", "사용자에게 권한을 주는 SQL 명령",
        DB, E,
        "어떤 사용자나 역할에게 표를 읽거나 고칠 권한을 주는 DCL 명령. 운영 데이터베이스에서는 앱 계정에 필요한 권한만 주고, 표를 "
        "지우는 권한은 따로 둔다. 새 표를 만든 뒤 권한을 안 줘서 permission denied 가 나는 일이 흔하다.",
        "Ask the DBA to grant read access on the analytics schema.",
        "DBA 에게 analytics 스키마의 읽기 권한을 달라고 요청하세요.",
    ),
    (
        "graph database", "/ˈɡræf ˌdeɪtəˌbeɪs/", "점과 연결선으로 관계를 저장하는 데이터베이스",
        DB, N,
        "데이터를 노드와 그 사이를 잇는 관계로 저장하는 데이터베이스. 친구의 친구나 추천, 사기 거래 탐지처럼 연결을 여러 번 따라가는 "
        "조회가 빠르다. 관계형 데이터베이스로 같은 일을 하면 단계마다 조인이 겹겹이 쌓여 금방 느려진다.",
        "Friend recommendations are easier to query in a graph database.",
        "친구 추천은 그래프 데이터베이스에서 조회하기가 더 쉽습니다.",
    ),
    (
        "in-memory database", "/ˌɪn ˈmeməri ˌdeɪtəˌbeɪs/", "데이터를 디스크가 아닌 메모리에 두는 데이터베이스",
        DB, E,
        "데이터를 주로 메모리에 올려 두고 읽고 쓰는 데이터베이스로, 디스크를 거치지 않아 아주 빠르다. 캐시나 순위표처럼 빨라야 하는 "
        "곳에 쓴다. 재시작하면 데이터가 날아갈 수 있어서 디스크에 남기는 설정을 켰는지 꼭 확인한다.",
        "We keep the leaderboard in an in-memory database for speed.",
        "속도 때문에 순위표는 인메모리 데이터베이스에 둡니다.",
    ),
    (
        "inner join", "/ˈɪnər ˌdʒɔɪn/", "양쪽에 짝이 있는 행만 이어 붙이기",
        DB, E,
        "두 표에서 조건이 맞는 짝이 양쪽에 다 있는 행만 남기는 조인. 그냥 JOIN 이라고만 써도 이것으로 동작한다. 짝이 없는 행은 "
        "소리 없이 빠지므로, 건수가 예상보다 적으면 left join 이 필요했던 것은 아닌지 본다.",
        "An inner join drops users who have no orders yet.",
        "inner join 이라 아직 주문이 없는 사용자는 빠집니다.",
    ),
    (
        "key-value store", "/ˌki ˈvælju ˌstɔr/", "키 하나로 값을 넣고 꺼내는 단순한 저장소",
        DB, E,
        "키 하나에 값 하나를 짝지어 저장하는 가장 단순한 NoSQL 형태. 키로 꺼내는 것은 아주 빠르지만, 값 안의 내용으로 검색하거나 "
        "다른 데이터와 조인하는 일은 못 한다. 세션, 캐시, 설정값처럼 키만 알면 되는 데이터에 쓴다.",
        "Sessions live in a key-value store, not in Postgres.",
        "세션은 Postgres 가 아니라 키-값 저장소에 둡니다.",
    ),
    (
        "lock granularity", "/ˈlɑk ɡrænjəˌlerəti/", "락을 얼마나 큰 단위로 거는지",
        DB, H,
        "락을 표 전체에 걸지, 페이지나 행 하나에 걸지 정한 크기. 단위가 클수록 관리는 쉽지만 동시에 처리할 수 있는 양이 줄고, "
        "작을수록 그 반대다. 정처기에서 로킹 단위가 크면 병행성이 낮아진다는 문장으로 자주 나온다.",
        "Finer lock granularity lets more requests run in parallel.",
        "락을 더 잘게 걸면 더 많은 요청이 동시에 돌 수 있습니다.",
    ),
    (
        "lost update", "/ˈlɔst ˌʌpdeɪt/", "동시에 고치다 한쪽 수정이 사라지는 현상",
        DB, N,
        "두 트랜잭션이 같은 값을 읽고 각자 고쳐 쓰면서, 나중에 쓴 쪽이 먼저 쓴 수정을 덮어 버리는 현상. 재고를 읽고 1을 빼서 다시 "
        "저장하는 코드에서 흔히 생긴다. 정처기에서는 병행 제어를 안 했을 때 생기는 대표 문제로 나온다.",
        "Read-modify-write without a lock caused a lost update on stock.",
        "락 없이 읽고 고쳐 쓰다 보니 재고에서 갱신 분실이 생겼습니다.",
    ),
    (
        "many-to-many", "/ˌmeni tə ˈmeni/", "양쪽이 서로 여러 개와 이어지는 관계",
        DB, E,
        "학생 한 명이 여러 강의를 듣고 강의 하나에도 여러 학생이 있는 식의 관계. 관계형 데이터베이스는 이것을 바로 담지 못해 양쪽 "
        "키를 들고 있는 중간 표를 하나 더 만든다. ORM 이 그 표를 알아서 만들어 주므로, 칸을 추가할 일이 생기면 직접 정의해야 "
        "한다.",
        "Tags and posts have a many-to-many relationship, so we need a join table.",
        "태그와 게시글은 다대다 관계라 중간 테이블이 필요합니다.",
    ),
    (
        "order by", "/ˈɔrdər ˌbaɪ/", "결과를 어떤 순서로 줄 세울지 정하는 SQL 절",
        DB, E,
        "조회 결과를 특정 칸 기준으로 오름차순이나 내림차순으로 정렬하는 절. 적지 않으면 데이터베이스는 순서를 약속하지 않아서, 어제와 "
        "오늘 결과 순서가 달라질 수 있다. 페이지를 나눠 보여줄 때 빠뜨리면 같은 행이 두 페이지에 나오기도 한다.",
        "Add an order by on created_at, or the page order is random.",
        "created_at 기준으로 order by 를 넣으세요. 안 그러면 페이지 순서가 제멋대로입니다.",
    ),
    (
        "outer join", "/ˈaʊtər ˌdʒɔɪn/", "left·right·full 을 통틀어, 짝 없는 행도 남기는 조인",
        DB, N,
        "조건에 맞는 짝이 없어도 한쪽이나 양쪽 표의 행을 남기고, 비는 칸은 NULL 로 채우는 조인. 어느 쪽을 남기느냐에 따라 "
        "left, right, full 로 나뉜다. 남은 행의 NULL 을 WHERE 에서 걸러 버려 결과가 inner join 과 "
        "같아지는 실수가 흔하다.",
        "We need an outer join so customers without orders still show up.",
        "주문이 없는 고객도 나오도록 outer join 이 필요합니다.",
    ),
    (
        "partial dependency", "/ˈpɑrʃəl dɪˌpendənsi/", "복합 키의 일부에만 기대는 종속",
        DB, H,
        "기본키가 여러 칸으로 이뤄졌을 때, 어떤 칸이 키 전체가 아니라 그 일부에만 종속된 상태. 주문번호와 상품번호를 묶은 키에서 "
        "상품명이 상품번호만 보고 정해지는 식이다. 같은 상품명이 여러 행에 반복 저장되므로, 이것을 없애도록 표를 나누면 2정규형이 "
        "된다.",
        "Product name has a partial dependency on the composite key, so split the table.",
        "상품명이 복합 키의 일부에만 종속되니 테이블을 나누세요.",
    ),
    (
        "pessimistic locking", "/ˌpesəˈmɪstɪk ˌlɑkɪŋ/", "충돌할 거라 보고 먼저 잠그고 시작하기",
        DB, N,
        "다른 사람이 같은 데이터를 고칠 거라고 가정하고, 읽는 순간부터 락을 걸어 두는 방식. SELECT ... FOR UPDATE 가 "
        "대표적이다. 충돌이 잦은 재고나 잔액에 맞지만, 락을 오래 잡고 있으면 다른 요청이 줄줄이 기다린다.",
        "Use pessimistic locking on the balance row to prevent double spending.",
        "이중 결제를 막으려면 잔액 행에 비관적 락을 거세요.",
    ),
    (
        "phantom read", "/ˈfæntəm ˌrid/", "같은 조회를 다시 하니 없던 행이 생기는 현상",
        DB, H,
        "한 트랜잭션에서 같은 조건으로 두 번 조회했는데, 그사이 다른 트랜잭션이 행을 넣어 처음에 없던 행이 나타나는 현상. 이미 있던 "
        "행의 값이 바뀌는 것과는 구분한다. 어느 격리 수준에서 막히는지가 데이터베이스마다 달라서 문서를 확인해야 한다.",
        "A phantom read appeared because another job inserted rows mid-report.",
        "리포트 도중 다른 작업이 행을 넣어서 팬텀 리드가 생겼습니다.",
    ),
    (
        "point-in-time recovery", "/ˌpɔɪnt ɪn ˈtaɪm rɪˌkʌvəri/", "원하는 시각의 상태로 데이터를 되돌리기",
        DB, H,
        "백업에 그 뒤의 변경 로그를 차례로 다시 적용해서, 원하는 시각 직전의 상태로 되살리는 복구 방식. 실수로 표를 지운 경우 지우기 "
        "1분 전으로 돌아갈 수 있다. 로그를 계속 보관해야 쓸 수 있으니 설정이 켜져 있는지 미리 확인한다.",
        "Use point-in-time recovery to restore the database to 14:02.",
        "특정 시점 복구로 데이터베이스를 14시 2분 상태로 되돌리세요.",
    ),
    (
        "prepared statement", "/prɪˈperd ˌsteɪtmənt/", "값 자리를 비워 두고 미리 준비한 쿼리",
        DB, N,
        "쿼리 모양을 먼저 보내 두고 값은 나중에 따로 넘기는 방식. 값이 쿼리 문장에 섞이지 않아서 SQL 인젝션을 막는 기본 수단이고, "
        "같은 쿼리를 반복할 때 준비 비용도 줄인다. 문자열을 이어 붙여 쿼리를 만드는 코드는 리뷰에서 바로 지적받는다.",
        "Never concatenate user input; use a prepared statement instead.",
        "사용자 입력을 이어 붙이지 말고 prepared statement 를 쓰세요.",
    ),
    (
        "relation", "/rɪˈleɪʃən/", "관계형 모델에서 표를 부르는 말",
        DB, N,
        "관계형 모델에서 행과 열로 이뤄진 표 하나를 부르는 이름. 개체 사이의 연결을 뜻하는 relationship 과는 다르다. "
        "PostgreSQL 이 relation does not exist 라고 하면 그런 표가 없다는 뜻이라, 마이그레이션을 안 "
        "돌렸는지부터 본다.",
        "If Postgres says relation \"users\" does not exist, migrate never ran.",
        "Postgres 가 relation \"users\" does not exist 라고 하면 migrate 를 안 돌린 겁니다.",
    ),
    (
        "relational algebra", "/rɪˈleɪʃənəl ˌældʒəbrə/", "결과를 얻는 절차를 연산자로 적는 이론",
        DB, H,
        "표를 입력받아 표를 내놓는 연산으로 질의를 표현하는 이론. 셀렉트, 프로젝트, 조인, 디비전 같은 연산자가 있고 SQL 이 그 "
        "위에 만들어졌다. 정처기에서는 시그마와 파이 같은 기호의 뜻과, 무엇을 원하는지만 적는 관계 해석과의 차이를 자주 묻는다.",
        "Relational algebra shows why the planner can reorder inner joins.",
        "관계 대수를 알면 플래너가 inner join 순서를 바꿔도 되는 이유가 보입니다.",
    ),
    (
        "replication lag", "/ˌreplɪˈkeɪʃn ˌlæɡ/", "복제본이 원본을 못 따라가고 늦는 정도",
        DB, N,
        "원본에 쓴 데이터가 복제본에 반영되기까지 걸리는 시간으로, 평소엔 짧아도 쓰기가 몰리면 크게 늘어난다. 읽기를 복제본으로 보내면 "
        "방금 저장한 글이 목록에 안 보이는 식의 문제가 생긴다. 저장 직후 다시 읽는 화면은 원본에서 읽게 하는 것이 흔한 해결법이다.",
        "The new comment is missing because of replication lag.",
        "복제 지연 때문에 새 댓글이 안 보입니다.",
    ),
    (
        "revoke", "/rɪˈvoʊk/", "줬던 권한을 거두는 SQL 명령",
        DB, N,
        "GRANT 로 줬던 권한을 다시 빼앗는 DCL 명령. 퇴사자 계정이나 더 이상 안 쓰는 서비스 계정을 정리할 때 쓰고, 권한 "
        "점검에서 남는 권한을 걷어 낼 때도 쓴다. 인증 쪽에서는 토큰을 무효로 만든다는 뜻으로도 쓰여서, 어느 맥락인지 보고 읽는다.",
        "We should revoke write access from the reporting user.",
        "리포팅 계정의 쓰기 권한은 회수해야 합니다.",
    ),
    (
        "row", "/roʊ/", "데이터 한 건인 가로 한 줄을 SQL 에서 부르는 말",
        DB, E,
        "표에 들어 있는 데이터 한 건으로, 사용자 표라면 사용자 한 명이 한 줄이고 레코드라고도 부른다. 수정이나 삭제 쿼리를 돌리면 몇 "
        "줄이 바뀌었는지가 찍히므로 이 숫자가 예상과 맞는지 꼭 본다. WHERE 를 빠뜨리면 이 숫자가 표 전체 행 수로 나온다.",
        "This update should touch exactly one row.",
        "이 수정은 정확히 한 행만 바꿔야 합니다.",
    ),
    (
        "savepoint", "/ˈseɪvˌpɔɪnt/", "트랜잭션 중간에 찍어 두는 되돌림 지점",
        DB, N,
        "트랜잭션 안에 이름 붙인 지점을 만들어, 실패하면 처음이 아니라 그 지점까지만 되돌리게 하는 기능. 긴 작업 중 일부만 다시 하고 "
        "싶을 때 쓴다. ORM 이 중첩 트랜잭션을 흉내 낼 때 안에서 이것을 쓰므로 쿼리 로그에서 자주 보인다.",
        "The ORM creates a savepoint for each nested atomic block.",
        "ORM 은 안쪽 atomic 블록마다 세이브포인트를 만듭니다.",
    ),
    (
        "selectivity", "/sɪˌlekˈtɪvəti/", "조건이 행을 얼마나 많이 걸러 내는지",
        DB, H,
        "조건에 맞는 행이 전체에서 차지하는 비율. 맞는 행이 적게 남는 조건일수록 선택도가 좋다고 하고, 그럴수록 인덱스가 효과를 본다. "
        "걸리는 행이 많은 조건이면 데이터베이스가 일부러 인덱스를 버리고 전체를 읽기도 한다.",
        "That filter has poor selectivity, so the index is ignored.",
        "그 조건은 걸러지는 게 거의 없어서 인덱스가 무시됩니다.",
    ),
    (
        "slow query", "/ˈsloʊ ˌkwɛri/", "정해 둔 시간보다 오래 걸린 쿼리",
        DB, E,
        "기준 시간보다 오래 걸린 쿼리로, 데이터베이스가 따로 기록해 두게 설정할 수 있다. 서비스가 느려지면 이 기록부터 열어 어떤 "
        "쿼리가 범인인지 찾는다. 한 번 아주 오래 걸린 쿼리보다 조금 느린데 자주 도는 쿼리가 더 큰 문제일 때가 많다.",
        "Check the slow query log before blaming the network.",
        "네트워크 탓을 하기 전에 슬로 쿼리 로그부터 보세요.",
    ),
    (
        "super key", "/ˈsupər ˌki/", "군더더기 칸이 섞여도 행을 구별만 하면 되는 키",
        DB, H,
        "칸 하나 또는 여러 칸을 묶어 행을 유일하게 구별할 수 있으면 이렇게 부른다. 꼭 필요하지 않은 칸이 섞여 있어도 되고, 거기서 "
        "군더더기를 뺀 최소 묶음이 후보키다. 정처기에서는 유일성은 있고 최소성은 없는 키로 정리한다.",
        "Email plus name is a super key, but email alone is enough.",
        "이메일과 이름을 묶으면 슈퍼키지만 이메일 하나로 충분합니다.",
    ),
    (
        "surrogate key", "/ˈsɜrəɡət ˌki/", "업무상 뜻 없이 행 구별용으로만 붙인 키",
        DB, N,
        "업무 데이터와 상관없이 행을 구별하려고만 붙인 키로, 자동 증가 번호나 UUID 가 대표적이다. 이메일처럼 뜻이 있는 값은 바뀔 "
        "수 있어서 기본키로 쓰기 불안하다. 대신 실제 값이 겹치지 않게 하려면 그 칸에 따로 unique 를 건다. 정처기의 "
        "대체키(alternate key)와는 다른 말이다.",
        "Use a surrogate key like an auto-increment id, since emails can change.",
        "이메일은 바뀔 수 있으니 자동 증가 id 같은 대리 키를 쓰세요.",
    ),
    (
        "table", "/ˈteɪbl/", "행과 열로 데이터를 담는 표를 SQL 에서 부르는 말",
        DB, E,
        "관계형 데이터베이스에서 데이터를 담는 기본 단위로, 행은 한 건이고 열은 항목 하나다. 모델 클래스 하나가 보통 표 하나가 된다. "
        "이름을 단수로 할지 복수로 할지는 팀마다 달라서, 새로 만들 때는 기존 이름부터 본다.",
        "Which table stores the user's quiz history?",
        "사용자의 퀴즈 기록은 어느 테이블에 저장되나요?",
    ),
    (
        "transitive dependency", "/ˈtrænsətɪv dɪˌpendənsi/", "다른 칸을 거쳐 간접적으로 정해지는 종속",
        DB, H,
        "A 가 B 를 정하고 B 가 C 를 정해서, 결국 C 가 A 에 간접적으로 종속된 상태. 주문 표에 고객 번호와 고객 주소를 함께 "
        "두면 주소가 고객 번호를 거쳐 정해지고, 주소가 바뀔 때 주문 행을 전부 고쳐야 한다. 이것을 없애면 3정규형이 된다.",
        "Storing the city name in orders creates a transitive dependency through the customer.",
        "주문에 도시 이름을 넣으면 고객을 거친 이행 종속이 생깁니다.",
    ),
    (
        "truncate", "/ˈtrʌŋkeɪt/", "표의 행을 한꺼번에 비우는 명령",
        DB, N,
        "표 구조는 남기고 안의 행을 전부 지우는 명령. 한 줄씩 지우는 DELETE 보다 훨씬 빠르지만, 데이터베이스에 따라 되돌릴 수 "
        "없고 행마다 도는 트리거도 실행되지 않는다. 문자열을 잘라낸다는 뜻으로도 쓰여서 value truncated 경고는 값이 잘렸다는 "
        "말이다.",
        "Don't truncate the orders table in staging; other teams use that data.",
        "스테이징의 orders 테이블을 비우지 마세요. 다른 팀이 그 데이터를 씁니다.",
    ),
    (
        "tuple", "/ˈtupəl/", "관계형 모델에서 행을 부르는 말",
        DB, N,
        "릴레이션에 들어 있는 행 하나를 관계형 모델에서 부르는 이름으로, 정처기에서는 튜플의 개수를 카디널리티라고 한다. "
        "PostgreSQL 은 내부에서 행의 버전 하나하나를 이렇게 불러 로그와 문서에 자주 나온다. 파이썬의 고칠 수 없는 묶음 "
        "자료형도 같은 이름이니 맥락으로 구분한다.",
        "Each update in Postgres writes a new tuple instead of changing the row in place.",
        "Postgres 는 수정할 때마다 행을 그 자리에서 고치지 않고 새 튜플을 씁니다.",
    ),
    (
        "two-phase locking", "/ˌtu ˈfeɪz ˌlɑkɪŋ/", "락을 얻는 단계와 푸는 단계를 나누는 규칙",
        DB, H,
        "트랜잭션이 락을 얻기만 하는 단계와 풀기만 하는 단계를 나눠, 하나라도 풀기 시작하면 새 락을 더 얻지 못하게 하는 규약. 이렇게 "
        "하면 차례로 실행한 것과 같은 결과가 보장된다. 대신 교착 상태는 막지 못한다는 점을 정처기에서 자주 묻는다.",
        "Two-phase locking guarantees serializability but can still deadlock.",
        "2단계 로킹은 직렬 가능성을 보장하지만 교착 상태는 여전히 생길 수 있습니다.",
    ),
    (
        "union", "/ˈjunjən/", "두 조회 결과를 위아래로 이어 붙이기",
        DB, N,
        "칸 구성이 같은 두 SELECT 결과를 하나로 합치는 집합 연산자. 그냥 쓰면 중복을 지우느라 추가 작업이 들고, UNION "
        "ALL 은 중복을 그대로 둔 채 붙여서 더 빠르다. 옆으로 붙이는 조인과 헷갈리지 않게 위아래로 붙인다고 기억한다.",
        "Use union all instead; we don't need to remove duplicates.",
        "union all 을 쓰세요. 중복을 지울 필요가 없습니다.",
    ),
    (
        "vector database", "/ˈvektər ˌdeɪtəˌbeɪs/", "숫자 배열로 바꾼 데이터를 비슷한 순으로 찾는 저장소",
        DB, N,
        "글이나 이미지를 임베딩이라는 숫자 배열로 바꿔 저장하고, 의미가 가까운 것을 찾아 주는 데이터베이스. AI 검색이나 챗봇이 관련 "
        "문서를 찾아올 때 쓴다. 정확히 같은 값을 찾는 게 아니라 비슷한 순으로 돌려주므로 결과가 근사치다.",
        "We store document embeddings in a vector database for semantic search.",
        "의미 검색을 위해 문서 임베딩을 벡터 데이터베이스에 저장합니다.",
    ),
    (
        "window function", "/ˈwɪndoʊ ˌfʌŋkʃən/", "행을 줄이지 않고 묶음별로 계산하는 함수",
        DB, H,
        "ROW_NUMBER, RANK 처럼 OVER 절과 함께 쓰는 함수. group by 는 묶음을 한 행으로 줄이지만, 이것은 행을 "
        "그대로 두고 각 행 옆에 순위나 누적합을 붙인다. WHERE 에는 바로 못 써서, 사용자별 최근 주문 하나만 남기려면 서브쿼리나 "
        "CTE 로 한 번 감싼 뒤 순위로 거른다.",
        "A window function can rank orders per user without a subquery.",
        "윈도우 함수를 쓰면 서브쿼리 없이 사용자별로 주문 순위를 매길 수 있습니다.",
    ),
    # ---------- 배포·운영 ----------
    (
        "alert fatigue", "/əˈlɜrt fəˌtiɡ/", "알림이 너무 많아 무뎌지는 현상",
        OPS, H,
        "쓸모없는 알림이 너무 자주 와서 사람들이 알림을 무시하게 되는 상태. 그러다 정작 진짜 장애 알림까지 놓치게 된다. 받아도 할 "
        "일이 없는 알림은 지우거나 등급을 낮추고, 사람을 깨우는 알림은 바로 행동이 필요한 것만 남긴다.",
        "Muting the noisy checks helped the team recover from alert fatigue.",
        "시끄러운 검사를 꺼 두니 팀이 알림 피로에서 벗어났습니다.",
    ),
    (
        "availability zone", "/əˌveɪləˈbɪləti ˌzoʊn/", "한 리전 안에서 서로 떨어진 데이터센터 묶음",
        OPS, N,
        "한 리전 안에는 전기와 네트워크를 따로 쓰는 데이터센터 묶음이 여럿 있는데, 그 하나하나를 말한다. 줄여서 AZ 라고 부른다. "
        "서버를 두 곳 이상에 나눠 두면 한 곳이 정전되거나 끊겨도 서비스가 이어진다. 대신 영역 사이를 오가는 통신에는 요금이 붙기도 "
        "한다.",
        "Only one availability zone went down, so traffic moved to the others.",
        "가용 영역 한 곳만 멈춰서 트래픽이 나머지 영역으로 넘어갔습니다.",
    ),
    (
        "backup", "/ˈbækˌʌp/", "잃을 때를 대비해 데이터를 따로 복사해 두기",
        OPS, E,
        "데이터가 지워지거나 망가질 때를 대비해 다른 곳에 복사해 두는 것, 또는 그 사본. 같은 서버 같은 디스크에 두면 함께 날아가니 "
        "위치를 나눈다. 되살려 본 적 없는 백업은 실제로 쓸 수 있는지 모르므로 주기적으로 복원을 시험한다.",
        "Take a backup before running the migration on production.",
        "운영에서 마이그레이션을 돌리기 전에 백업부터 뜨세요.",
    ),
    (
        "base image", "/ˈbeɪs ˌɪmɪdʒ/", "내 이미지를 그 위에 쌓아 올리는 출발 이미지",
        OPS, N,
        "Dockerfile 의 FROM 줄에 적는, 내 이미지가 그 위에 만들어지는 이미지. 운영체제와 언어 런타임이 미리 들어 있다. "
        "무엇을 고르냐에 따라 이미지 크기와 취약점 수가 크게 달라지고, latest 태그를 쓰면 어느 날 내용이 갑자기 바뀐다.",
        "Switch to a slim base image to cut the size in half.",
        "크기를 반으로 줄이려면 slim 베이스 이미지로 바꾸세요.",
    ),
    (
        "build", "/bɪld/", "소스 코드를 실행할 수 있는 결과물로 만들기",
        OPS, E,
        "소스 코드를 컴파일하거나 묶어서 배포할 수 있는 형태로 만드는 과정, 또는 그 결과물. CI 파이프라인의 한 단계라 여기서 깨지면 "
        "배포까지 가지 못한다. 개발 서버에서는 잘 되는데 빌드만 실패하면 타입 오류나 빠진 환경 변수를 먼저 의심한다.",
        "The build is failing on main, so please hold your merges.",
        "main 빌드가 깨져 있으니 머지는 잠시 멈춰 주세요.",
    ),
    (
        "cloud", "/klaʊd/", "남의 서버를 인터넷으로 빌려 쓰는 방식",
        OPS, E,
        "서버와 저장소, DB 를 직접 사지 않고 업체에서 인터넷으로 빌려 쓰고 쓴 만큼 내는 방식. 몇 분 만에 서버를 늘리거나 줄일 수 "
        "있다. 편한 만큼 켜 두고 잊은 자원에도 요금이 계속 나가니, 다 쓴 테스트 서버는 바로 지운다.",
        "We moved the database from our own server to the cloud last year.",
        "작년에 DB 를 자체 서버에서 클라우드로 옮겼습니다.",
    ),
    (
        "configuration drift", "/kənˌfɪɡjəˈreɪʃən ˌdrɪft/", "실제 서버 설정이 코드에 적힌 것과 어긋나는 현상",
        OPS, H,
        "누군가 서버에 들어가 손으로 바꾼 설정이 쌓여, 코드로 적어 둔 설정과 실제 서버가 조금씩 어긋나는 현상. 같은 줄 알았던 서버 "
        "두 대가 다르게 동작하는 원인이 된다. 설정은 코드로만 바꾸고 주기적으로 차이를 검사해서 막는다.",
        "Staging works but production fails; I suspect configuration drift.",
        "스테이징은 되는데 운영은 안 되네요. 설정이 어긋난 것 같습니다.",
    ),
    (
        "crash loop", "/ˈkræʃ ˌlup/", "켜지자마자 죽고 다시 켜지기를 반복하는 상태",
        OPS, N,
        "프로그램이 시작하자마자 죽고, 재시작 설정 때문에 다시 켜졌다 또 죽기를 되풀이하는 상태. 쿠버네티스에서는 "
        "CrashLoopBackOff 로 보인다. 겉으로는 서버가 떠 있는 것처럼 보여 며칠씩 모르고 지나가기도 하니 재시작 횟수를 함께 "
        "본다.",
        "The container is in a crash loop because DATABASE_URL is missing.",
        "DATABASE_URL 이 없어서 컨테이너가 죽었다 살아나기를 반복하고 있습니다.",
    ),
    (
        "CVE", "/ˌsi vi ˈi/", "공개된 보안 취약점마다 붙는 공용 번호",
        OPS, N,
        "Common Vulnerabilities and Exposures 의 줄임말. 알려진 보안 취약점마다 CVE-2021-44228 "
        "처럼 연도와 일련번호로 붙이는 공용 번호다. 의존성 검사 도구가 이 번호로 경고를 띄우는데, 번호가 떴다고 우리 코드가 그 기능을 "
        "쓰는지는 따로 확인해야 한다.",
        "The scanner flagged a critical CVE in our image library.",
        "스캐너가 이미지 처리 라이브러리에서 심각한 CVE 를 찾았습니다.",
    ),
    (
        "daemon", "/ˈdimən/", "운영체제와 함께 늘 떠 있으며 요청을 받는 서비스 프로그램",
        OPS, N,
        "화면 없이 백그라운드에서 계속 실행되며 요청을 받아 처리하는 프로그램. Docker 명령이 데몬에 연결할 수 없다며 실패하면 대개 "
        "Docker 자체가 안 켜져 있는 것이다. sshd 처럼 이름 끝에 붙은 d 가 데몬을 뜻하는 경우가 많다.",
        "Cannot connect to the Docker daemon. Is Docker running?",
        "Docker 데몬에 연결할 수 없습니다. Docker 가 실행 중인가요?",
    ),
    (
        "dashboard", "/ˈdæʃˌbɔrd/", "주요 지표를 그래프로 한 화면에 모은 페이지",
        OPS, E,
        "요청 수, 에러율, 응답 시간 같은 지표를 그래프로 한 화면에 모아 둔 페이지. 장애가 나면 가장 먼저 여는 곳이다. 그래프가 "
        "너무 많으면 정작 무엇을 봐야 할지 모르게 되니, 장애 때 실제로 보는 몇 개만 앞에 둔다.",
        "Check the dashboard; the error rate started climbing at 2:10.",
        "대시보드를 보세요. 2시 10분부터 에러율이 오르기 시작했습니다.",
    ),
    (
        "dead letter queue", "/ˈded ˌletər ˌkju/", "끝내 처리 못 한 메시지를 따로 모아 두는 큐",
        OPS, H,
        "여러 번 다시 시도해도 처리에 실패한 메시지를 버리지 않고 옮겨 두는 별도의 큐. 원래 큐가 같은 메시지에 막혀 멈추지 않게 "
        "하면서, 실패한 것은 나중에 원인을 보고 다시 넣을 수 있다. 쌓이기만 하고 아무도 안 보면 조용히 데이터를 잃는 것과 같다.",
        "Three failed messages ended up in the dead letter queue overnight.",
        "밤사이 실패한 메시지 세 개가 데드 레터 큐로 빠졌습니다.",
    ),
    (
        "DevOps", "/ˈdevˌɑps/", "개발과 운영을 합쳐 자주 작게 배포하는 문화",
        OPS, E,
        "개발자와 운영자가 따로 일하던 방식을 합쳐, 자동화로 자주 작게 배포하고 운영 문제도 함께 책임지는 문화. 직무 이름으로도 쓰여서 "
        "데브옵스 엔지니어라고 하면 대개 CI/CD 와 인프라를 맡는 사람이다. 도구 이름이 아니라 일하는 방식을 가리킨다.",
        "Ask the DevOps team to add a staging database.",
        "스테이징 DB 추가는 데브옵스 팀에 요청하세요.",
    ),
    (
        "DNS propagation", "/ˌdi en ˌes ˌprɑpəˈɡeɪʃən/", "바꾼 DNS 설정이 곳곳에 퍼지기까지의 과정",
        OPS, H,
        "도메인이 가리키는 주소를 바꿔도 곳곳의 DNS 서버가 예전 값을 캐시해 두고 있어서, 새 값이 모두에게 보이기까지 걸리는 과정. "
        "몇 분에서 길게는 이틀이 걸린다. 나는 새 사이트가 보이는데 동료는 옛 사이트를 보는 이유가 이것이라, 바꾸기 전에 TTL 을 "
        "낮춰 둔다.",
        "Some users still reach the old server; DNS propagation can take hours.",
        "아직 옛 서버로 가는 사용자가 있습니다. DNS 전파는 몇 시간 걸리기도 해요.",
    ),
    (
        "Docker", "/ˈdɑkər/", "앱을 이미지로 묶어 컨테이너로 띄우는 도구",
        OPS, E,
        "앱과 실행에 필요한 것을 이미지 하나로 묶고, 그 이미지를 컨테이너로 띄우는 도구. 내 컴퓨터에서는 되는데 서버에서는 안 되는 "
        "문제를 줄여준다. 컨테이너 기술 자체를 부르는 이름처럼 쓰이지만, 컨테이너는 다른 도구로도 띄울 수 있다.",
        "Run the database with Docker so everyone uses the same version.",
        "모두 같은 버전을 쓰도록 DB 는 도커로 띄우세요.",
    ),
    (
        "end of life", "/ˌend əv ˈlaɪf/", "더 이상 업데이트와 보안 수정이 안 나오는 지원 종료",
        OPS, N,
        "만든 쪽이 그 버전에 더 이상 업데이트와 보안 수정을 내지 않는 시점. 줄여서 EOL 이라고 쓴다. 당장 멈추지는 않아 미루기 "
        "쉽지만, 그 뒤에 나온 취약점은 고쳐지지 않고 배포 플랫폼이 어느 날 빌드를 거부하기도 한다.",
        "Node 16 reached end of life, so we need to upgrade the build image.",
        "Node 16 지원이 끝나서 빌드 이미지를 올려야 합니다.",
    ),
    (
        "ephemeral", "/ɪˈfemərəl/", "잠깐 있다가 사라져 남지 않는",
        OPS, H,
        "잠깐 존재하다 없어지는 것을 말한다. 컨테이너나 서버리스의 디스크가 대표적이라, 재시작하거나 새로 배포하면 거기 저장한 파일은 "
        "사라진다. 업로드 파일을 서버 디스크에 두었다가 배포 뒤에 전부 날아가는 일이 흔한 이유다.",
        "The container filesystem is ephemeral, so write uploads to object storage.",
        "컨테이너 파일 시스템은 금방 사라지니 업로드는 오브젝트 스토리지에 쓰세요.",
    ),
    (
        "failover", "/ˈfeɪlˌoʊvər/", "주 서버가 죽으면 예비 서버로 넘기기",
        OPS, N,
        "주 서버나 DB 가 고장 나면 미리 대기시켜 둔 예비 쪽이 일을 넘겨받는 것. 자동이면 몇 초에서 몇 분 안에 끝난다. 넘어가는 "
        "순간 연결이 끊기고 막 쓴 데이터가 빠질 수 있어서, 앱이 다시 접속할 수 있는지 미리 시험해 본다.",
        "The primary went down, and failover to the standby took 40 seconds.",
        "주 DB 가 죽었고, 대기 서버로 넘어가는 데 40초가 걸렸습니다.",
    ),
    (
        "GitOps", "/ˈɡɪtˌɑps/", "Git 에 적힌 대로 서버 상태를 자동으로 맞추는 방식",
        OPS, H,
        "배포 설정을 Git 저장소에 두고, 저장소가 바뀌면 도구가 실제 서버 상태를 그 내용에 맞추는 방식. 무엇이 언제 왜 바뀌었는지가 "
        "커밋으로 남고, 되돌리기도 커밋 하나로 끝난다. 서버에서 손으로 고친 것은 도구가 다시 Git 내용으로 덮어쓴다.",
        "With GitOps, merging this PR deploys the new config automatically.",
        "GitOps 방식이라 이 PR 을 머지하면 새 설정이 자동으로 배포됩니다.",
    ),
    (
        "graceful degradation", "/ˌɡreɪsfəl ˌdeɡrəˈdeɪʃən/", "일부가 고장 나도 핵심 기능은 살려 두기",
        OPS, H,
        "어느 부분이 고장 나면 서비스 전체를 멈추는 대신 덜 중요한 기능만 끄고 핵심은 계속 돌게 하는 설계. 추천 기능이 죽어도 상품 "
        "목록과 결제는 계속 되게 하는 식이다. 무엇을 포기할지는 장애가 나기 전에 정해 두어야 한다.",
        "Graceful degradation means we still show recent items when search is down.",
        "검색이 죽어도 최근 항목은 계속 보여 주는 식으로 기능을 줄여 버티는 겁니다.",
    ),
    (
        "heartbeat", "/ˈhɑrtˌbit/", "살아 있다고 스스로 일정 간격마다 보내는 신호",
        OPS, N,
        "프로그램이 정해진 간격으로 아직 살아 있다는 신호를 보내는 것. 신호가 일정 시간 끊기면 죽은 것으로 보고 알림을 보내거나 다른 "
        "쪽으로 일을 넘긴다. 바깥에서 물어보는 헬스 체크와 달리 안에서 스스로 보낸다는 점이 다르다.",
        "The worker stopped sending a heartbeat ten minutes ago.",
        "워커가 10분 전부터 하트비트를 안 보내고 있습니다.",
    ),
    (
        "hosting", "/ˈhoʊstɪŋ/", "내 서비스를 서버에 올려 인터넷에 공개하기",
        OPS, E,
        "내 웹사이트나 앱을 다른 사람이 접속할 수 있게 서버에 올려 두는 것, 또는 그 서버를 빌려주는 서비스. 요즘은 저장소를 연결하면 "
        "빌드와 배포까지 알아서 해 주는 곳이 많다. 무료 요금제는 한동안 안 쓰면 잠들어 첫 접속이 느리기도 하다.",
        "We use separate hosting for the frontend and the API.",
        "프론트엔드와 API 는 호스팅을 따로 씁니다.",
    ),
    (
        "hypervisor", "/ˈhaɪpərˌvaɪzər/", "한 컴퓨터에서 가상 머신 여러 대를 돌려 주는 소프트웨어",
        OPS, H,
        "물리 서버 한 대의 CPU 와 메모리를 나눠 여러 가상 머신을 동시에 돌리게 해 주는 소프트웨어. 클라우드에서 빌리는 서버도 "
        "대부분 이 위에서 돈다. 가상 머신마다 운영체제를 통째로 갖는다는 점에서, 운영체제를 함께 쓰는 컨테이너와 다르다.",
        "The hypervisor splits one physical host into twelve VMs.",
        "하이퍼바이저가 물리 서버 한 대를 가상 머신 12대로 나눕니다.",
    ),
    (
        "IAM", "", "누가 어떤 클라우드 자원을 쓸 수 있는지 정하는 권한 관리",
        OPS, N,
        "Identity and Access Management 의 줄임말. 클라우드에서 사람과 서버마다 어떤 자원에 무슨 일을 할 수 "
        "있는지 정한다. AccessDenied 에러는 대부분 여기서 나온다. 귀찮다고 관리자 권한을 통째로 주면 키 하나가 새는 순간 "
        "계정 전체가 넘어간다.",
        "The deploy failed with AccessDenied; check the IAM policy.",
        "배포가 AccessDenied 로 실패했습니다. IAM 정책을 확인하세요.",
    ),
    (
        "IDS", "/ˌaɪ di ˈes/", "침입 시도를 찾아내 알려 주는 보안 시스템",
        OPS, H,
        "Intrusion Detection System 의 줄임말. 네트워크나 서버의 활동을 지켜보다 공격처럼 보이는 패턴을 찾으면 "
        "알린다. 찾아서 알리기만 하고 막지는 않는다는 점이 차단까지 하는 IPS 와 다르다. 오탐이 많으면 알림이 무시되기 쉽다.",
        "The IDS flagged repeated SSH login attempts from a single address.",
        "IDS 가 한 주소에서 반복된 SSH 로그인 시도를 잡아냈습니다.",
    ),
    (
        "least privilege", "/ˌlist ˈprɪvəlɪdʒ/", "일에 꼭 필요한 만큼만 권한을 주는 원칙",
        OPS, N,
        "사람이든 프로그램이든 일하는 데 필요한 만큼만 권한을 주는 원칙. 키가 새거나 계정이 털려도 피해가 그 권한 안에서 멈춘다. "
        "처음에 넓게 주고 나중에 줄이자고 하면 대개 안 줄어들어서, 좁게 시작하고 필요할 때 넓힌다.",
        "Following the principle of least privilege, the CI token can only push images.",
        "최소 권한 원칙에 따라 CI 토큰은 이미지 푸시만 할 수 있습니다.",
    ),
    (
        "liveness probe", "/ˈlaɪvnəs ˌproʊb/", "멈춘 컨테이너를 찾아 재시작시키는 검사",
        OPS, H,
        "쿠버네티스가 컨테이너가 아직 제대로 살아 있는지 주기적으로 묻는 검사. 실패하면 그 컨테이너를 죽이고 다시 띄운다. 기준을 너무 "
        "빡빡하게 잡으면 잠깐 바쁜 것뿐인 앱까지 계속 재시작돼서 오히려 장애를 키운다. 앱이 처음 뜨는 시간도 감안해 첫 검사를 늦춰 "
        "둔다.",
        "The liveness probe timeout is too short, so pods restart under load.",
        "라이브니스 프로브 제한 시간이 너무 짧아서 부하가 걸리면 파드가 재시작됩니다.",
    ),
    (
        "localhost", "/ˈloʊkəlˌhoʊst/", "지금 쓰고 있는 내 컴퓨터를 가리키는 주소",
        OPS, E,
        "네트워크에서 자기 자신을 가리키는 이름으로, 숫자 주소로는 127.0.0.1 이다. 개발 서버를 띄우면 localhost:3000 "
        "처럼 열린다. 컨테이너 안에서는 이 이름이 내 컴퓨터가 아니라 그 컨테이너 자신을 가리켜서, DB 에 못 붙는 흔한 원인이 된다.",
        "Inside the container, localhost points to the container itself.",
        "컨테이너 안에서 localhost 는 컨테이너 자신을 가리킵니다.",
    ),
    (
        "LTS", "/ˌel ti ˈes/", "몇 년 동안 보안 수정을 약속한 안정 버전",
        OPS, E,
        "Long Term Support 의 줄임말. 몇 년 동안 버그와 보안 수정을 계속 내 주기로 약속한 버전이다. Node.js 나 "
        "Ubuntu 를 설치할 때 LTS 와 최신판 중에서 고르게 되는데, 운영 서버에는 새 기능보다 오래 지원받는 쪽이 중요해서 대개 "
        "LTS 를 고른다.",
        "Pin the runtime to the current LTS release, not the latest one.",
        "런타임은 최신판 말고 현재 LTS 버전으로 고정하세요.",
    ),
    (
        "maintenance window", "/ˈmeɪntənəns ˌwɪndoʊ/", "점검 작업을 하기로 미리 공지한 시간대",
        OPS, N,
        "서비스를 잠깐 멈추거나 위험한 작업을 해도 되도록 미리 공지해 둔 시간대. 사용자가 적은 새벽이나 주말에 잡는 경우가 많다. 시간 "
        "안에 못 끝낼 때 어디서 멈추고 되돌릴지도 미리 정해 두어야 시간이 넘쳐도 허둥대지 않는다.",
        "The DB upgrade is scheduled for Sunday's maintenance window.",
        "DB 업그레이드는 일요일 점검 시간에 잡혀 있습니다.",
    ),
    (
        "manifest", "/ˈmænəˌfest/", "무엇을 어떻게 띄울지 적어 둔 설정 파일",
        OPS, N,
        "무엇을 어떻게 구성할지 목록처럼 적어 둔 파일. 쿠버네티스에서는 배포할 대상과 원하는 상태를 적은 YAML 파일을 말하고, "
        "쿠버네티스가 실제 상태를 그 내용에 맞춘다. 웹 앱의 manifest.json 이나 안드로이드 앱의 설정 파일처럼 앱 정보를 적은 "
        "파일도 같은 이름으로 부른다.",
        "Change the replica count in the manifest, not directly on the cluster.",
        "레플리카 수는 클러스터에서 직접 말고 매니페스트에서 바꾸세요.",
    ),
    (
        "message queue", "/ˈmesɪdʒ ˌkju/", "할 일을 쌓아 두고 차례로 꺼내 처리하게 하는 시스템",
        OPS, N,
        "보내는 쪽이 할 일을 넣어 두면 받는 쪽이 자기 속도로 꺼내 처리하게 해 주는 시스템. 메일 발송처럼 오래 걸리는 일을 요청 "
        "처리에서 떼어 낼 때 쓴다. 받는 쪽이 느리면 에러 없이 조용히 쌓이기만 하니 쌓인 개수를 지켜본다.",
        "Push the email job to the message queue instead of sending it inline.",
        "메일은 요청 안에서 바로 보내지 말고 메시지 큐에 넣으세요.",
    ),
    (
        "mitigation", "/ˌmɪtəˈɡeɪʃən/", "장애가 났을 때 사용자 피해부터 줄이는 조치",
        OPS, N,
        "장애의 원인을 다 고치기 전에 일단 사용자 피해부터 줄이려고 하는 조치. 배포 되돌리기, 기능 끄기, 서버 늘리기가 흔하다. 상황 "
        "공유에서 mitigated 는 급한 불은 껐다는 뜻이지 원인이 해결됐다는 뜻은 아니다.",
        "The rollback was only a mitigation; we still don't know the root cause.",
        "롤백으로 급한 불만 껐을 뿐, 근본 원인은 아직 모릅니다.",
    ),
    (
        "monitoring", "/ˈmɑnɪtərɪŋ/", "시스템 상태 수치를 계속 모으며 지켜보는 일",
        OPS, E,
        "서버와 서비스의 상태 수치를 계속 모으고, 정해 둔 기준을 넘으면 알림을 보내는 일. 사용자가 먼저 장애를 알려 오는 상황을 막는 "
        "것이 목적이다. 미리 정한 것만 지켜보므로, 예상 못 한 문제를 파고드는 관측 가능성과는 결이 조금 다르다.",
        "We had no monitoring on the worker, so nobody noticed it died.",
        "워커에 모니터링이 없어서 죽은 걸 아무도 몰랐습니다.",
    ),
    (
        "noisy neighbor", "/ˌnɔɪzi ˈneɪbər/", "같은 서버를 쓰는 남 때문에 내 성능이 떨어지는 문제",
        OPS, H,
        "물리 서버 한 대를 여러 고객이나 서비스가 나눠 쓸 때, 한쪽이 CPU 나 디스크를 몰아 써서 다른 쪽이 느려지는 현상. 내 "
        "코드는 그대로인데 특정 시간에만 느려지면 의심해 볼 만하다. 자원 상한을 걸거나 전용 서버로 옮겨 피한다.",
        "The latency spikes match another tenant's batch job, a classic noisy neighbor.",
        "지연이 튀는 시간이 다른 고객의 배치 작업과 겹칩니다. 전형적인 노이지 네이버 문제예요.",
    ),
    (
        "object storage", "/ˈɑbdʒekt ˌstɔrɪdʒ/", "파일을 키로 통째로 넣고 꺼내는 저장소",
        OPS, N,
        "이미지나 백업 파일을 폴더 경로 대신 키로 저장하고 URL 로 꺼내 쓰는 저장소. 용량 걱정이 거의 없고 값이 싸서 사용자 업로드 "
        "파일을 둔다. 디스크처럼 파일 일부만 고칠 수는 없고, 바꾸려면 통째로 다시 올려야 한다.",
        "Store user uploads in object storage, not on the server disk.",
        "사용자 업로드 파일은 서버 디스크 말고 오브젝트 스토리지에 두세요.",
    ),
    (
        "on-premises", "/ˌɑn ˈpremɪsɪz/", "회사가 직접 가진 서버에서 운영하는 방식",
        OPS, N,
        "클라우드를 빌리지 않고 회사 건물이나 데이터센터에 자기 서버를 두고 운영하는 방식. 줄여서 온프렘이라고 많이 부른다. 데이터를 "
        "밖에 두기 어려운 금융이나 공공 쪽에서 많고, 클라우드와 섞어 쓰는 하이브리드 구성도 흔하다.",
        "The bank runs everything on-premises, so managed cloud services are off the table.",
        "그 은행은 전부 자체 서버에서 운영해서 클라우드 관리형 서비스는 쓸 수 없습니다.",
    ),
    (
        "outage", "/ˈaʊtɪdʒ/", "서비스를 아예 쓸 수 없게 된 장애",
        OPS, E,
        "서비스 전체나 큰 기능이 멈춰 사용자가 쓸 수 없는 상황. 느려지기만 한 것은 성능 저하라고 따로 부르는 경우가 많다. 클라우드 "
        "업체에 문제가 생기면 우리 코드가 멀쩡해도 멈출 수 있어서, 업체 상태 페이지도 함께 확인한다.",
        "Yesterday's outage lasted 45 minutes and blocked all logins.",
        "어제 장애는 45분 동안 이어졌고 로그인이 전부 막혔습니다.",
    ),
    (
        "pod", "/pɑd/", "쿠버네티스가 띄우는 가장 작은 실행 단위",
        OPS, N,
        "쿠버네티스에서 컨테이너 하나 또는 몇 개를 묶어 함께 띄우는 단위. 같은 파드 안의 컨테이너는 네트워크와 저장 공간을 나눠 쓴다. "
        "파드는 언제든 죽고 새로 뜰 수 있어서 파드의 IP 나 내부 파일에 기대면 안 된다.",
        "The pod was evicted because the node ran out of memory.",
        "노드 메모리가 부족해서 파드가 쫓겨났습니다.",
    ),
    (
        "readiness probe", "/ˈredinəs ˌproʊb/", "요청을 받을 준비가 됐는지 확인하는 검사",
        OPS, H,
        "쿠버네티스가 컨테이너에 요청을 보내도 되는지 주기적으로 묻는 검사. 실패하면 컨테이너를 죽이지 않고 트래픽만 빼 둔다. 앱이 뜨는 "
        "데 시간이 걸리는데 이 검사가 없으면, 준비 전인 컨테이너로 요청이 가서 배포 때마다 잠깐씩 에러가 난다.",
        "Add a readiness probe so traffic waits until the app finishes loading.",
        "앱이 다 뜰 때까지 트래픽이 기다리도록 레디니스 프로브를 추가하세요.",
    ),
    (
        "region", "/ˈridʒən/", "클라우드 데이터센터를 지역별로 묶은 단위",
        OPS, E,
        "클라우드 업체가 서울, 도쿄처럼 지역별로 묶어 둔 데이터센터 단위. 사용자와 가까운 곳을 고르면 응답이 빨라진다. 리전마다 요금과 "
        "쓸 수 있는 서비스가 다르고, 콘솔에 다른 리전이 선택돼 있어 만든 자원이 안 보인다고 헤매는 일이 흔하다.",
        "The bucket is in another region, so it doesn't show up here.",
        "버킷이 다른 리전에 있어서 여기서는 안 보입니다.",
    ),
    (
        "runner", "/ˈrʌnər/", "CI 작업을 받아 실제로 돌리는 기계",
        OPS, N,
        "CI 파이프라인에 적힌 빌드와 테스트를 받아 실제로 실행하는 서버나 프로세스. 서비스가 빌려주는 것을 쓰거나 회사 서버에 직접 "
        "설치한다. 내 컴퓨터에서는 통과하는데 CI 에서만 깨지면 러너의 운영체제나 버전이 달라서인 경우가 많다.",
        "The job is stuck in the queue because no runner is available.",
        "쓸 수 있는 러너가 없어서 작업이 대기열에 멈춰 있습니다.",
    ),
    (
        "security group", "/sɪˈkjʊrəti ˌɡrup/", "클라우드 서버마다 거는 접속 허용 규칙",
        OPS, N,
        "클라우드에서 서버나 DB 앞에 두는 가상 방화벽 규칙 묶음으로, 어떤 주소에서 어떤 포트로 들어올 수 있는지 정한다. 연결이 시간 "
        "초과로 끊기면 코드보다 이 규칙을 먼저 의심한다. 편하자고 모든 주소를 열어 두면 그대로 공격 통로가 된다.",
        "Port 5432 is blocked; add an inbound rule to the security group.",
        "5432 포트가 막혀 있습니다. 보안 그룹에 인바운드 규칙을 추가하세요.",
    ),
    (
        "serverless", "/ˈsɜrvərləs/", "요청이 올 때만 코드를 실행하고 쓴 만큼 내는 방식",
        OPS, N,
        "서버를 직접 띄워 관리하지 않고, 함수나 앱을 올려 두면 요청이 올 때만 플랫폼이 실행해 주는 방식. 서버가 없다는 뜻이 아니라 "
        "내가 관리하지 않는다는 뜻이다. 쓴 만큼만 내지만 오래 쉬다 들어온 첫 요청은 콜드 스타트로 느리다.",
        "We moved the image resizer to serverless functions.",
        "이미지 리사이저를 서버리스 함수로 옮겼습니다.",
    ),
    (
        "sidecar", "/ˈsaɪdˌkɑr/", "본 컨테이너 옆에 붙어 보조 일을 맡는 컨테이너",
        OPS, H,
        "앱 컨테이너 옆에 함께 띄워 로그 수집, 프록시, 인증서 갱신 같은 보조 일을 맡기는 컨테이너. 앱 코드를 고치지 않고 기능을 "
        "붙일 수 있고, 이름은 오토바이 옆에 붙는 좌석에서 왔다. 보조 컨테이너지만 사이드카만 죽어도 파드 전체가 비정상으로 보일 수 "
        "있다.",
        "A sidecar ships the app logs to our log server.",
        "사이드카가 앱 로그를 로그 서버로 보냅니다.",
    ),
    (
        "single point of failure", "/ˌsɪŋɡəl ˌpɔɪnt əv ˈfeɪljər/", "그것 하나만 고장 나도 전체가 멈추는 지점",
        OPS, N,
        "예비가 없어서 고장 나면 서비스 전체가 멈추는 부품이나 서버. 줄여서 SPOF 라고 쓴다. 앱 서버를 여러 대 둬도 DB 나 로드 "
        "밸런서가 한 대뿐이면 거기가 이 지점이 되므로, 요청이 지나는 길 전체를 처음부터 끝까지 살펴본다.",
        "That one cache server is a single point of failure for the whole site.",
        "그 캐시 서버 한 대가 사이트 전체의 단일 장애점입니다.",
    ),
    (
        "SLI", "/ˌes el ˈaɪ/", "서비스 수준을 재는 실제 측정값",
        OPS, N,
        "Service Level Indicator 의 줄임말. 성공한 요청 비율이나 응답 시간처럼 실제로 재는 값이다. 이 값으로 내부 "
        "목표인 SLO 를 세우고, 사용자와 약속하는 것이 SLA 다. 셋이 헷갈리면 재는 값, 목표, 약속 순서로 기억한다.",
        "Our main SLI is the share of requests answered within 300ms.",
        "주요 SLI 는 300ms 안에 응답한 요청의 비율입니다.",
    ),
    (
        "snapshot", "/ˈsnæpˌʃɑt/", "디스크나 DB 를 어느 순간 그대로 떠 둔 것",
        OPS, E,
        "디스크나 DB 를 특정 시점 그대로 찍어 저장한 것. 업그레이드처럼 위험한 작업 직전에 떠 두면, 문제가 생겼을 때 그 시점으로 "
        "되돌릴 수 있다. 찍은 뒤에 들어온 데이터는 들어 있지 않아서 되돌리면 그만큼은 잃는다.",
        "Take a snapshot of the volume before resizing it.",
        "볼륨 크기를 바꾸기 전에 스냅샷을 떠 두세요.",
    ),
    (
        "status page", "/ˈsteɪtəs ˌpeɪdʒ/", "서비스가 정상인지 사용자에게 알리는 공개 페이지",
        OPS, N,
        "서비스가 지금 정상인지, 어떤 장애가 진행 중인지를 사용자에게 알리는 공개 페이지. 문의가 몰리기 전에 먼저 알리려고 둔다. 우리 "
        "서비스가 기대고 있는 클라우드나 결제 업체가 이상할 때도 그쪽 상태 페이지부터 확인한다.",
        "Post an update on the status page every 30 minutes.",
        "상태 페이지에 30분마다 진행 상황을 올려 주세요.",
    ),
    (
        "VPC", "/ˌvi pi ˈsi/", "클라우드 안에 따로 떼어 둔 나만의 네트워크",
        OPS, N,
        "Virtual Private Cloud 의 줄임말. 클라우드 안에 다른 고객과 분리된 내 네트워크 영역을 만든다. 서브넷과 "
        "라우팅을 정해 DB 는 바깥에서 못 들어오게 숨긴다. 서버끼리 연결이 안 될 때는 둘이 서로 다른 VPC 나 서브넷에 있는 경우가 "
        "많다.",
        "The database sits in a private subnet inside the VPC.",
        "DB 는 VPC 안의 프라이빗 서브넷에 있습니다.",
    ),
    (
        "vulnerability", "/ˌvʌlnərəˈbɪləti/", "공격자가 파고들 수 있는 보안 약점",
        OPS, N,
        "공격자가 이용해 권한을 얻거나 데이터를 빼낼 수 있는 코드나 설정의 약점. 내가 쓴 코드뿐 아니라 설치한 라이브러리에서도 계속 "
        "발견된다. 경고가 떴다고 모두 급한 것은 아니니, 심각도와 우리가 그 기능을 실제로 쓰는지를 보고 순서를 정한다.",
        "npm audit found a high-severity vulnerability in one of our dependencies.",
        "npm audit 가 의존성 하나에서 심각도 높은 취약점을 찾았습니다.",
    ),
    (
        "zero-day", "/ˈzɪroʊ ˌdeɪ/", "패치가 나오기 전에 이미 악용되는 취약점",
        OPS, N,
        "만든 쪽이 알기 전이나 고칠 패치를 내기 전에 이미 공격에 쓰이는 취약점. 대응할 시간이 0일이라는 뜻에서 온 이름이다. "
        "업데이트로는 아직 못 막으니 방화벽 규칙이나 기능 끄기 같은 임시 조치로 버티며 패치를 기다린다.",
        "Attackers are already exploiting this zero-day in the wild.",
        "공격자들이 이미 이 제로데이 취약점을 실제로 악용하고 있습니다.",
    ),
    # ---------- 디버깅 ----------
    (
        "address already in use", "/ˌædres ɔlˌredi ɪn ˈjus/", "그 포트를 이미 다른 프로그램이 쓰는 중",
        DEBUG, N,
        "서버를 띄우려는 포트를 다른 프로그램이 이미 쓰고 있다는 에러. 앞서 띄운 개발 서버를 제대로 끄지 않고 다시 띄울 때 가장 "
        "흔하다. 그 포트를 쓰는 프로세스를 찾아 끄거나 다른 포트 번호로 띄운다. 맥과 리눅스에서는 lsof 명령으로 그 포트를 잡은 "
        "프로세스를 찾을 수 있다.",
        "The server will not start: address already in use on port 8000.",
        "8000번 포트를 이미 쓰고 있어서 서버가 안 뜹니다.",
    ),
    (
        "benchmark", "/ˈbentʃˌmɑrk/", "같은 조건에서 성능을 재어 비교하기",
        DEBUG, N,
        "정해진 조건에서 코드나 시스템의 속도를 재서 비교하는 것, 또는 그 측정용 테스트. 바꾸기 전과 후를 같은 기계와 같은 데이터로 "
        "재야 의미가 있다. 한 번만 재면 우연이 섞이므로 여러 번 돌려 평균이나 중앙값을 본다.",
        "Run the benchmark again on the same machine before comparing.",
        "비교하기 전에 같은 기계에서 벤치마크를 다시 돌려 보세요.",
    ),
    (
        "beta test", "/ˈbeɪtə ˌtest/", "출시 전에 일부 사용자에게 미리 풀어 써 보게 하기",
        DEBUG, E,
        "정식 출시 전에 실제 사용자 일부에게 제품을 써 보게 하고 문제를 모으는 테스트. 개발한 곳 안에서 먼저 써 보는 알파 테스트 "
        "다음 단계다. 정처기에서는 인수 테스트의 한 종류로 나오고, 개발자 없이 실제 사용 환경에서 한다는 점이 알파 테스트와의 차이다.",
        "We will open a beta test to fifty users next week.",
        "다음 주에 사용자 50명에게 베타 테스트를 엽니다.",
    ),
    (
        "branch coverage", "/ˈbræntʃ ˌkʌvərɪdʒ/", "조건의 참·거짓 갈래를 다 지났는지 재는 비율",
        DEBUG, H,
        "if 같은 조건에서 참으로 가는 길과 거짓으로 가는 길을 테스트가 각각 지났는지 재는 비율. else 없는 if 의 조건이 한 "
        "번도 거짓이 된 적 없으면, 줄 단위 커버리지는 100% 여도 이 값은 낮게 나온다. 정처기에서는 결정 커버리지라고도 부른다.",
        "Line coverage is high, but branch coverage is only 60 percent.",
        "라인 커버리지는 높은데 브랜치 커버리지는 60%밖에 안 됩니다.",
    ),
    (
        "bug", "/bʌɡ/", "프로그램의 잘못된 동작이나 그 원인",
        DEBUG, E,
        "코드가 의도와 다르게 동작하는 결함을 두루 부르는 말이다. 이슈 트래커에서는 기능 요청과 구분하려고 bug 라벨을 붙인다. "
        "사용자가 기대와 다르다고 느끼는 것이 모두 버그는 아니어서, 원래 그렇게 설계한 동작이면 by design 이라고 답하기도 한다.",
        "Is this a bug, or is it working as intended?",
        "이거 버그인가요, 아니면 원래 이렇게 동작하는 건가요?",
    ),
    (
        "call stack", "/ˈkɔl ˌstæk/", "지금까지 불린 함수들이 쌓인 순서",
        DEBUG, N,
        "현재 실행 중인 함수가 어떤 함수들을 거쳐 불렸는지 쌓여 있는 목록. 디버거에서 멈추면 이 목록을 따라 올라가며 값이 어디서 잘못 "
        "들어왔는지 찾는다. 에러가 났을 때 이 목록을 그대로 찍어 낸 것이 스택 트레이스다.",
        "Walk up the call stack to see who passed the empty list.",
        "콜 스택을 따라 올라가서 누가 빈 리스트를 넘겼는지 보세요.",
    ),
    (
        "catch", "/kætʃ/", "던져진 예외를 받아서 처리하다",
        DEBUG, E,
        "실행 중에 던져진 예외를 받아 프로그램이 죽지 않게 처리하는 것. try 블록 안에서 난 예외를 catch 블록이 받는다. 잡아 "
        "놓고 아무것도 안 하면 오류가 감춰지므로, 처리할 방법이 없으면 차라리 잡지 않고 위로 보내는 편이 낫다.",
        "Only catch the exceptions you know how to handle.",
        "처리 방법을 아는 예외만 잡으세요.",
    ),
    (
        "circular import", "/ˈsɜrkjələr ˌɪmpɔrt/", "두 모듈이 서로를 불러오는 꼬인 구조, 또는 그 때문에 나는 에러",
        DEBUG, H,
        "A 모듈이 B 를 불러오고 B 도 다시 A 를 불러와서, 어느 쪽도 먼저 준비되지 못해 나는 에러. 파이썬에서는 partially "
        "initialized module 이라는 메시지로 보이는 일이 많다. 함수 안에서 불러오거나 공통 부분을 다른 모듈로 빼서 고리를 "
        "끊는다.",
        "Moving the import inside the function fixed the circular import.",
        "import 를 함수 안으로 옮겼더니 순환 import 문제가 풀렸습니다.",
    ),
    (
        "command not found", "/kəˌmænd ˌnɑt ˈfaʊnd/", "입력한 명령을 찾을 수 없음",
        DEBUG, E,
        "터미널에 친 명령의 프로그램을 찾지 못했다는 에러. 설치하지 않았거나, 설치는 했지만 PATH 에 그 위치가 없거나, 가상환경을 "
        "켜지 않았을 때 나고, 생각보다 오타도 많다. 윈도우에서는 is not recognized 로 시작하는 문장으로 나온다.",
        "I get command not found after installing the CLI globally.",
        "CLI 를 전역으로 설치했는데도 명령을 찾을 수 없다고 나옵니다.",
    ),
    (
        "connection refused", "/kəˌnekʃən rɪˈfjuzd/", "상대 쪽에서 연결을 받지 않음",
        DEBUG, N,
        "주소까지는 찾아갔지만 그 포트에서 연결을 받아 주는 프로그램이 없다는 에러. 대개 서버나 데이터베이스가 아직 안 떴거나 포트 "
        "번호가 틀렸을 때다. 한참 기다리다 끊기는 timeout 과는 원인이 달라서, 먼저 상대 서버가 떠 있는지부터 본다.",
        "Django shows connection refused because Postgres is not running yet.",
        "Postgres 가 아직 안 떠서 Django 가 연결 거부 에러를 띄웁니다.",
    ),
    (
        "crash", "/kræʃ/", "프로그램이 갑자기 죽어 꺼지는 것",
        DEBUG, E,
        "처리하지 못한 오류 때문에 프로그램이 실행 도중 갑자기 종료되는 것. 서버라면 프로세스가 죽고, 앱이라면 화면이 꺼지며 홈으로 "
        "튕긴다. 꺼지지 않고 멈춘 채 반응만 없는 것은 크래시가 아니라 행이라고 따로 부른다. 크래시가 나면 마지막 로그와 종료 코드부터 "
        "본다.",
        "The app started to crash after we upgraded the image library.",
        "이미지 라이브러리를 올린 뒤로 앱이 죽기 시작했습니다.",
    ),
    (
        "debug", "/diˈbʌɡ/", "버그의 원인을 찾아 고치다",
        DEBUG, E,
        "프로그램이 예상과 다르게 동작할 때 원인을 찾아내고 고치는 일 전체를 말한다. 로그를 찍어 보는 것도, 디버거로 한 줄씩 따라가는 "
        "것도 모두 여기에 든다. 고치는 것보다 원인을 찾는 데 시간이 훨씬 많이 든다는 것을 알아 두면 덜 조급해진다.",
        "I spent the whole morning trying to debug this login issue.",
        "이 로그인 문제를 디버깅하느라 오전을 통째로 썼어요.",
    ),
    (
        "debugger", "/diˈbʌɡər/", "코드를 멈춰 놓고 한 줄씩 살펴보는 도구",
        DEBUG, E,
        "실행 중인 프로그램을 원하는 지점에서 멈추고 변수 값과 호출 경로를 들여다보게 해 주는 도구. print 를 여러 번 넣었다 빼는 "
        "것보다 빠를 때가 많다. 파이썬은 pdb 가 기본으로 들어 있고, 브라우저는 개발자 도구 안에 있다.",
        "Attach the debugger and check what the variable holds at that line.",
        "디버거를 붙여서 그 줄에서 변수에 뭐가 들어 있는지 확인해 보세요.",
    ),
    (
        "defect", "/ˈdifekt/", "기대와 다르게 만들어진 결함",
        DEBUG, N,
        "요구사항이나 설계와 다르게 만들어져 고쳐야 하는 부분. 일상에서는 bug 와 거의 같은 뜻으로 쓰지만, 품질 관리나 정처기에서는 "
        "사람의 실수인 error, 코드에 남은 결함인 defect, 실행 중에 드러난 실패인 failure 를 구분한다.",
        "QA found one defect in the checkout flow before release.",
        "QA 가 출시 전에 결제 흐름에서 결함 하나를 찾았습니다.",
    ),
    (
        "duplicate", "/ˈduplɪkət/", "이미 있는 것과 똑같은 중복",
        DEBUG, E,
        "같은 것이 둘 이상 있다는 뜻. 데이터베이스의 duplicate key 에러는 유일해야 하는 값을 한 번 더 넣으려 했다는 "
        "것이다. 이슈 트래커에서 이미 올라온 문제와 같은 이슈를 닫을 때도 duplicate 라고 표시한다.",
        "Close this issue as a duplicate of the login bug ticket.",
        "이 이슈는 로그인 버그 티켓과 중복이라 닫아 주세요.",
    ),
    (
        "equivalence partitioning", "/ɪˈkwɪvələns pɑrˌtɪʃənɪŋ/", "결과가 같은 입력끼리 묶어 대표값만 시험",
        DEBUG, H,
        "입력값을 같은 결과가 나올 무리로 나누고, 무리마다 대표값 하나씩만 시험하는 블랙박스 테스트 기법. 나이 입력이라면 음수, 0부터 "
        "13, 14 이상처럼 나눈다. 경계값 분석과 함께 쓰는 경우가 많고, 정처기 블랙박스 기법 문제의 단골이다.",
        "Equivalence partitioning cut our date tests from forty cases to five.",
        "동등 분할로 날짜 테스트를 40개에서 5개로 줄였습니다.",
    ),
    (
        "error", "/ˈerər/", "하려던 일이 잘못돼 실패한 것, 또는 그 메시지",
        DEBUG, E,
        "프로그램이 하려던 일을 끝내지 못했을 때 내는 신호나 그 메시지. 경고와 달리 그대로 두면 기능이 동작하지 않는다. 에러 "
        "메시지에는 무엇이 왜 안 됐는지가 대개 한 줄로 적혀 있으니, 번역기에 넣기 전에 먼저 그 한 줄을 끝까지 읽어 본다.",
        "The page loads, but the console shows an error on every click.",
        "페이지는 뜨는데 클릭할 때마다 콘솔에 에러가 찍힙니다.",
    ),
    (
        "exit code", "/ˈeɡzɪt ˌkoʊd/", "프로그램이 끝나며 남기는 성공·실패 번호",
        DEBUG, N,
        "프로그램이 끝날 때 운영체제에 돌려주는 숫자. 0 이면 성공이고 그 밖의 숫자는 실패를 뜻한다. CI 는 이 값만 보고 단계의 "
        "성공과 실패를 판단하므로, 에러를 출력만 하고 0 으로 끝내면 실패가 초록불로 지나간다.",
        "The script prints an error but still returns exit code 0.",
        "스크립트가 에러를 찍고도 종료 코드는 0 을 돌려줍니다.",
    ),
    (
        "expected behavior", "/ɪkˈspektɪd bɪˌheɪvjər/", "원래 이렇게 동작해야 한다는 모습",
        DEBUG, E,
        "버그 리포트에 적는 항목으로, 원래 어떻게 동작해야 하는지를 쓴다. 실제로 일어난 일을 적는 actual behavior 와 짝을 "
        "이룬다. 두 칸을 나란히 써야 읽는 사람이 무엇이 문제인지 바로 알 수 있고, 둘의 차이가 곧 고칠 내용이 된다.",
        "Please add the expected behavior and steps to reproduce to the issue.",
        "이슈에 원래 기대한 동작과 재현 방법을 적어 주세요.",
    ),
    (
        "fail fast", "/ˌfeɪl ˈfæst/", "문제가 보이면 바로 멈추고 알리기",
        DEBUG, H,
        "잘못된 입력이나 설정을 발견하면 대충 넘어가지 말고 그 자리에서 바로 실패시키는 원칙. 일찍 멈추면 원인 가까운 곳에서 에러가 "
        "나서 찾기 쉽다. 테스트 도구의 fail fast 옵션은 첫 실패가 나오면 나머지 실행을 멈춘다.",
        "We fail fast at startup if the API key is missing.",
        "API 키가 없으면 시작할 때 바로 실패하게 합니다.",
    ),
    (
        "false negative", "/ˌfɔls ˈneɡətɪv/", "문제가 있는데 없다고 잘못 통과시킴",
        DEBUG, N,
        "실제로 문제가 있는데 도구가 괜찮다고 통과시키는 것. 아무것도 확인하지 않는 테스트가 초록불을 내는 경우가 대표적이다. 잘못된 "
        "경고는 귀찮기라도 하지만 이쪽은 눈에 띄지 않아서 더 위험하다. 테스트를 새로 쓰면 코드를 일부러 망가뜨려 보고 정말 실패하는지 "
        "확인해 둔다.",
        "That test is a false negative; it passes even when the code is broken.",
        "그 테스트는 코드가 망가져도 통과해서 문제를 못 잡습니다.",
    ),
    (
        "false positive", "/ˌfɔls ˈpɑzətɪv/", "문제가 없는데 있다고 잘못 알림",
        DEBUG, N,
        "실제로는 문제가 없는데 도구가 문제가 있다고 알리는 것. 린터 경고, 보안 스캐너, 모니터링 알림에서 자주 쓰고 우리말로는 "
        "오탐이라고 한다. 이런 잘못된 경고가 많아지면 사람들이 알림을 무시하게 되어 진짜 문제까지 놓친다.",
        "The scanner flagged a test key, but it is a false positive.",
        "스캐너가 테스트용 키를 잡았는데 이건 오탐입니다.",
    ),
    (
        "fatal", "/ˈfeɪtəl/", "더는 진행할 수 없는 치명적인",
        DEBUG, N,
        "복구할 수 없어서 프로그램이나 명령이 그 자리에서 멈춘다는 뜻. 로그 등급에서는 error 보다 위다. git 의 fatal: "
        "not a git repository 처럼 명령 자체가 실행되지 못했을 때 앞에 붙는다. 무섭게 보여도 폴더를 잘못 잡은 것 같은 "
        "단순한 원인일 때가 많다.",
        "Git says fatal because you are outside the repository folder.",
        "저장소 폴더 밖에 있어서 git 이 fatal 을 띄우는 거예요.",
    ),
    (
        "hang", "/hæŋ/", "죽지도 않고 멈춰서 반응이 없는 상태",
        DEBUG, N,
        "프로그램이 꺼지지는 않았는데 아무 반응도 하지 않고 멈춰 있는 상태. 무한 루프, 교착 상태, 끝나지 않는 네트워크 대기가 흔한 "
        "원인이다. 에러 로그가 남지 않아서 크래시보다 원인을 찾기 어려운 경우가 많다. 멈춘 순간의 스택을 떠 보면 어디서 기다리고 "
        "있는지 보인다.",
        "The tests hang forever when the database container is not running.",
        "데이터베이스 컨테이너가 안 떠 있으면 테스트가 끝없이 멈춰 있습니다.",
    ),
    (
        "hot path", "/ˈhɑt ˌpæθ/", "가장 자주 실행되는 코드 경로",
        DEBUG, H,
        "요청마다, 반복마다 실행되어 전체 성능을 좌우하는 코드 경로. 여기서는 작은 낭비도 수백만 번 곱해진다. 반대로 거의 안 불리는 "
        "코드를 아무리 빠르게 해도 체감은 없으므로, 최적화는 이 경로를 찾는 데서 시작하고, 그 경로는 추측이 아니라 프로파일러로 "
        "찾는다.",
        "Avoid database calls on the hot path; cache the settings instead.",
        "가장 자주 도는 경로에서는 DB 호출을 피하고 설정을 캐시하세요.",
    ),
    (
        "illegal", "/ɪˈliɡəl/", "언어나 프로그램이 허용하지 않는(불법이 아님)",
        DEBUG, N,
        "에러 메시지에서는 법을 어겼다는 뜻이 아니라 언어나 프로그램의 규칙상 허용되지 않는다는 뜻이다. "
        "IllegalArgumentException 은 받을 수 없는 값이 인자로 들어왔다는 것이고, illegal character 는 "
        "그 자리에 쓸 수 없는 글자가 섞였다는 것이다.",
        "The compiler reports an illegal character on line 12.",
        "컴파일러가 12번째 줄에 쓸 수 없는 문자가 있다고 알려 줍니다.",
    ),
    (
        "index out of range", "/ˌɪndeks ˌaʊt əv ˈreɪndʒ/", "목록에 없는 위치의 값을 꺼내려 함",
        DEBUG, E,
        "리스트나 배열에서 있지도 않은 위치의 값을 꺼내려 할 때 나는 에러. 길이가 3 이면 마지막 인덱스는 2 인데 3 을 꺼내는 "
        "식이다. 빈 리스트에서 첫 번째 값을 꺼낼 때도 똑같이 나므로, 결과가 비어 있을 수 있는지부터 확인한다.",
        "The script throws index out of range when the search result is empty.",
        "검색 결과가 비어 있으면 스크립트에서 인덱스 범위 초과 에러가 납니다.",
    ),
    (
        "infinite loop", "/ˈɪnfənət ˌlup/", "끝나지 않고 계속 도는 반복문",
        DEBUG, E,
        "종료 조건이 끝내 참이 되지 않아 영원히 반복되는 루프. CPU 사용률이 100% 에 붙어 있거나 화면이 굳으면 의심해 본다. "
        "반복 변수를 늘리는 줄을 빠뜨리거나 조건의 부등호를 반대로 쓰는 실수에서 자주 생기고, while 문에서 특히 흔하다.",
        "The worker is stuck in an infinite loop and pinning the CPU.",
        "워커가 무한 루프에 빠져서 CPU 를 꽉 잡고 있습니다.",
    ),
    (
        "instrumentation", "/ˌɪnstrəmenˈteɪʃən/", "측정하려고 코드에 재는 장치를 넣는 것",
        DEBUG, H,
        "실행 시간, 호출 횟수, 에러 수 같은 값을 재기 위해 코드에 측정 장치를 넣는 것. 직접 코드를 추가하기도 하고 라이브러리가 "
        "자동으로 넣어 주기도 한다. 이것이 있어야 대시보드의 지표와 요청 추적 데이터가 나온다.",
        "Add instrumentation to the checkout service so we can see slow calls.",
        "느린 호출을 볼 수 있게 결제 서비스에 계측 코드를 넣으세요.",
    ),
    (
        "intermittent", "/ˌɪntərˈmɪtənt/", "증상이 늘 아니라 가끔씩만 나타나는",
        DEBUG, H,
        "늘 일어나는 것이 아니라 불규칙하게 가끔 일어난다는 뜻. intermittent failure 는 같은 조건에서도 어떤 때만 "
        "실패하는 문제를 말한다. 재현이 어려워 원인을 찾기 힘들고, 대개 타이밍이나 네트워크, 동시 실행과 관련이 있다.",
        "Users report intermittent timeouts on the upload page.",
        "업로드 페이지에서 간헐적으로 시간 초과가 난다는 제보가 있습니다.",
    ),
    (
        "invalid", "/ɪnˈvælɪd/", "형식이나 값이 규칙에 맞지 않는",
        DEBUG, E,
        "값이 정해진 형식이나 규칙을 지키지 않았다는 뜻으로, 에러 메시지에 가장 자주 나오는 말 중 하나다. invalid syntax, "
        "invalid argument 처럼 무엇이 틀렸는지가 뒤에 붙는다. 값이 아예 없다는 것이 아니라 있긴 한데 틀렸다는 뜻이다.",
        "The request failed with an invalid date format in the body.",
        "본문의 날짜 형식이 잘못돼서 요청이 실패했습니다.",
    ),
    (
        "log", "/lɔɡ/", "프로그램이 실행하며 남기는 기록",
        DEBUG, E,
        "프로그램이 언제 무엇을 했는지 시간 순서대로 남기는 기록. 장애가 나면 가장 먼저 보는 곳이다. 동사로도 써서 이 값을 기록으로 "
        "남기라는 말을 log this value 라고 한다. 비밀번호나 토큰이 그대로 찍히지 않게 조심한다.",
        "Check the server log around 3 a.m. when the job failed.",
        "작업이 실패한 새벽 3시 무렵 서버 로그를 확인해 보세요.",
    ),
    (
        "log rotation", "/ˈlɔɡ roʊˌteɪʃən/", "로그 파일을 주기적으로 나누고 지우기",
        DEBUG, N,
        "로그 파일이 끝없이 커지지 않도록 일정 크기나 기간마다 새 파일로 바꾸고, 오래된 파일은 압축하거나 지우는 것. 설정하지 않으면 "
        "어느 날 디스크가 가득 차서 서버가 멈춘다. 지운 파일에 필요한 기록이 있을 수 있으니 보관 기간은 미리 정해 둔다.",
        "Set up log rotation before the disk fills up again.",
        "디스크가 또 차기 전에 로그 로테이션을 설정하세요.",
    ),
    (
        "malformed", "/mælˈfɔrmd/", "형식이 깨져서 읽을 수 없는",
        DEBUG, H,
        "데이터의 구조가 깨져서 해석 자체를 할 수 없다는 뜻. 괄호가 하나 빠진 JSON 이나 규칙에 맞지 않는 요청이 대표적이다. "
        "invalid 가 읽을 수는 있지만 값이 틀렸다는 쪽이라면, malformed 는 읽는 단계에서 이미 막혔다는 쪽에 가깝다.",
        "The webhook sent malformed JSON, so the parser rejected it.",
        "웹훅이 깨진 JSON 을 보내서 파서가 거부했습니다.",
    ),
    (
        "mismatch", "/ˈmɪsˌmætʃ/", "서로 맞아야 할 두 값이 다름",
        DEBUG, N,
        "짝이 맞아야 하는 두 가지가 서로 다르다는 뜻. type mismatch 는 기대한 자료형과 실제 자료형이 다를 때, "
        "version mismatch 는 함께 써야 하는 두 프로그램의 버전이 다를 때 나온다. 메시지에 expected 와 got 이 "
        "같이 찍히면 둘을 나란히 놓고 비교한다.",
        "The deploy failed because of a schema mismatch between staging and production.",
        "스테이징과 운영의 스키마가 달라서 배포가 실패했습니다.",
    ),
    (
        "monkey patch", "/ˈmʌŋki ˌpætʃ/", "실행 중에 기존 코드를 바꿔 끼우기",
        DEBUG, H,
        "원래 코드를 고치지 않고 실행 중에 함수나 속성을 다른 것으로 바꿔 끼우는 기법. 테스트에서 시간이나 외부 호출을 가짜로 바꿀 때 "
        "자주 쓴다. 운영 코드에서 쓰면 어디서 동작이 바뀌었는지 추적하기 어려워진다. pytest 에는 이 용도로 monkeypatch "
        "라는 도구가 따로 있다.",
        "We monkey patch the clock so the test always sees the same date.",
        "테스트가 항상 같은 날짜를 보도록 시계를 몽키 패치합니다.",
    ),
    (
        "no such file or directory", "/ˌnoʊ ˌsʌtʃ ˌfaɪl ɔr dəˈrektəri/", "그 경로에 파일이나 폴더가 없음",
        DEBUG, E,
        "지정한 경로에 파일이나 폴더가 없다는 에러로, 코드에서는 ENOENT 라는 이름으로도 나온다. 경로 오타보다 현재 작업 폴더가 "
        "생각과 달라서 상대 경로가 엉뚱한 곳을 가리키는 경우가 더 흔하다. 절대 경로를 찍어 보면 금방 드러난다.",
        "CI fails with no such file or directory because the path is relative.",
        "경로가 상대 경로라서 CI 에서 파일이 없다는 에러가 납니다.",
    ),
    (
        "overhead", "/ˈoʊvərˌhed/", "본래 일 외에 덤으로 드는 비용",
        DEBUG, N,
        "원래 하려는 일 말고 그 일을 하기 위해 추가로 드는 시간이나 메모리. 로그를 남기거나 함수를 한 겹 감싸는 것에도 이런 비용이 "
        "붙는다. 대부분 무시할 만큼 작지만, 가장 자주 도는 코드에서는 쌓여서 눈에 띄는 차이가 된다.",
        "The tracing overhead is under one percent, so keep it on.",
        "추적에 드는 추가 비용이 1% 도 안 되니 켜 두세요.",
    ),
    (
        "permission denied", "/pərˌmɪʃən dɪˈnaɪd/", "권한이 없어서 거절됨",
        DEBUG, E,
        "파일을 읽거나 쓰거나 실행할 권한이 없어서 운영체제가 막았다는 에러. 스크립트에 실행 권한이 없거나, 다른 사용자가 만든 폴더에 "
        "쓰려 할 때 자주 본다. 무작정 sudo 를 붙이면 일단 넘어가도 나중에 파일 주인이 꼬이므로 왜 막혔는지부터 확인한다.",
        "Running the deploy script gives permission denied on the logs folder.",
        "배포 스크립트를 실행하면 logs 폴더에서 권한 거부 에러가 납니다.",
    ),
    (
        "print debugging", "/ˈprɪnt diˌbʌɡɪŋ/", "출력문을 넣어 값을 찍어 보는 디버깅",
        DEBUG, E,
        "의심 가는 곳에 print 나 console.log 를 넣어 값과 실행 순서를 찍어 보는 가장 단순한 디버깅 방식. 준비가 필요 "
        "없어 누구나 처음 쓰는 방법이고 실제로도 자주 통한다. 다만 다 고친 뒤 지우는 것을 잊고 그대로 커밋하는 일이 흔하다.",
        "Print debugging was enough to find the wrong loop index.",
        "출력문 몇 줄 찍어 보는 것만으로 잘못된 반복 인덱스를 찾았어요.",
    ),
    (
        "propagate", "/ˈprɑpəˌɡeɪt/", "예외나 변경이 다른 곳으로 퍼져 전해지다",
        DEBUG, H,
        "처리되지 않은 예외가 호출한 함수를 따라 위로 계속 올라가는 것을 말한다. 설정이나 데이터 변경이 다른 곳까지 퍼지는 것에도 같은 "
        "말을 쓴다. 에러가 엉뚱한 곳에서 보인다면 아래에서 올라온 예외일 수 있으니 처음 던져진 곳을 찾아본다.",
        "Let the error propagate to the view so it returns a 400.",
        "에러가 뷰까지 올라가게 둬서 400 을 돌려주게 하세요.",
    ),
    (
        "redact", "/rɪˈdækt/", "민감한 부분을 가려서 남기다",
        DEBUG, H,
        "로그나 문서에서 비밀번호, 토큰, 개인정보 같은 민감한 부분을 가리거나 지우는 것. 에러 로그를 이슈나 채팅에 붙이기 전에 꼭 "
        "거친다. 로그 설정에서 특정 필드를 자동으로 가리게 해 두면 실수로 새는 일을 줄일 수 있다.",
        "Please redact the API token before pasting the log here.",
        "여기 로그를 붙이기 전에 API 토큰은 가려 주세요.",
    ),
    (
        "severity", "/səˈverəti/", "문제가 얼마나 심각한지 나타내는 등급",
        DEBUG, N,
        "버그나 장애가 서비스에 끼치는 영향이 얼마나 큰지 나타내는 등급. 얼마나 빨리 고칠지를 뜻하는 우선순위와는 다르다. 심각하지만 "
        "거의 아무도 겪지 않는 문제는 우선순위가 낮을 수 있고, 가벼워도 모두가 매일 보는 문제는 먼저 고치기도 한다.",
        "Mark it as high severity; checkout is down for all users.",
        "높은 심각도로 표시해 주세요. 모든 사용자가 결제를 못 하고 있어요.",
    ),
    (
        "stack overflow", "/ˈstæk ˌoʊvərfloʊ/", "함수 호출이 너무 깊어 스택이 넘치는 에러",
        DEBUG, N,
        "함수가 함수를 부르는 깊이가 정해진 스택 공간을 넘어서 프로그램이 죽는 에러. 대개 끝나는 조건이 없는 재귀가 원인이다. 질문 "
        "사이트 이름으로 더 유명하지만 에러 메시지에서는 이 뜻이고, 자바스크립트에서는 Maximum call stack size "
        "exceeded 로 나타난다.",
        "A missing base case caused a stack overflow in the tree walker.",
        "종료 조건을 빠뜨려서 트리 순회 코드에서 스택 오버플로가 났습니다.",
    ),
    (
        "stderr", "", "에러 메시지가 나가는 출력 통로",
        DEBUG, N,
        "프로그램이 에러와 경고를 내보내는 출력 통로로, 일반 결과가 나가는 stdout 과 따로 있다. 출력을 파일로 넘겼는데 에러 "
        "메시지만 화면에 계속 남는다면 이쪽으로 나왔기 때문이다. 둘을 한 파일로 받으려면 명령 끝에 2>&1 을 붙인다.",
        "Warnings go to stderr, so they do not show up in the output file.",
        "경고는 표준 에러로 나가서 출력 파일에는 안 남습니다.",
    ),
    (
        "step into", "/ˈstep ˌɪntu/", "디버거에서 함수 안으로 들어가 따라가기",
        DEBUG, N,
        "디버거에서 지금 줄의 함수 호출 안으로 들어가 그 함수의 첫 줄부터 한 줄씩 따라가는 동작. 그 함수 안에 문제가 있다고 의심될 "
        "때 쓴다. 라이브러리 함수까지 들어가면 길을 잃기 쉬워서, 내 코드가 아니면 step over 로 넘기는 편이 낫다.",
        "Step into the save method to see where the value changes.",
        "값이 어디서 바뀌는지 보려면 save 메서드 안으로 들어가 보세요.",
    ),
    (
        "system test", "/ˈsɪstəm ˌtest/", "완성된 시스템 전체를 요구사항대로 검사",
        DEBUG, N,
        "모든 부분을 합친 완성된 시스템이 요구사항대로 동작하는지 확인하는 테스트. 단위, 통합 테스트 다음이고 사용자가 확인하는 인수 "
        "테스트 전에 한다. 기능뿐 아니라 성능, 보안처럼 기능이 아닌 요구사항도 이 단계에서 본다.",
        "We start the system test once all modules are deployed to staging.",
        "모든 모듈이 스테이징에 배포되면 시스템 테스트를 시작합니다.",
    ),
    (
        "tail", "/teɪl/", "로그 끝부분을 실시간으로 따라 보다",
        DEBUG, N,
        "파일의 마지막 몇 줄을 보여 주는 명령에서 온 말로, 로그에 새 줄이 쌓이는 것을 실시간으로 지켜본다는 뜻으로 쓴다. tail "
        "-f 를 켜 둔 채 문제를 재현하면 그 순간 찍히는 로그를 바로 볼 수 있다. 너무 빨리 올라가면 grep 으로 원하는 줄만 걸러 "
        "함께 본다.",
        "Tail the app logs while you click the button.",
        "버튼을 누르는 동안 앱 로그를 실시간으로 보세요.",
    ),
    (
        "teardown", "/ˈterˌdaʊn/", "테스트가 끝난 뒤 뒷정리하는 단계",
        DEBUG, N,
        "테스트가 끝난 뒤 만든 파일, 데이터, 연결을 치워서 다음 테스트에 영향이 없게 하는 단계. 준비하는 setup 과 짝을 이룬다. "
        "정리를 빠뜨리면 혼자 돌릴 때는 통과하던 테스트가 함께 돌릴 때만 깨지는 일이 생긴다.",
        "Delete the temp directory in teardown so later tests start clean.",
        "뒤의 테스트가 깨끗하게 시작하도록 정리 단계에서 임시 폴더를 지우세요.",
    ),
    (
        "test double", "/ˈtest ˌdʌbəl/", "테스트에서 진짜 대신 쓰는 가짜들의 총칭",
        DEBUG, H,
        "테스트할 때 진짜 의존 대상을 대신하는 가짜 객체를 통틀어 부르는 말로, 영화의 대역 배우에서 왔다. 정해진 값만 돌려주는 "
        "stub, 호출을 검증하는 mock, 간단히 실제처럼 동작하는 fake 가 모두 여기에 속한다. 흔히 전부 mock 이라고 "
        "부르지만 엄밀히는 이쪽이 상위 개념이다.",
        "Use a test double for the payment client instead of the real API.",
        "실제 API 대신 결제 클라이언트용 테스트 대역을 쓰세요.",
    ),
    (
        "test harness", "/ˈtest ˌhɑrnɪs/", "테스트를 돌리려고 갖춘 도구와 코드 묶음",
        DEBUG, H,
        "테스트 대상을 실행하고 결과를 확인하려고 갖춘 도구와 코드 전체. 아직 없는 하위 모듈을 대신하는 스텁, 대상을 호출하는 "
        "드라이버, 테스트 케이스와 스크립트가 여기에 든다. 정처기에서는 이 구성 요소를 설명과 짝지어 묻는 문제가 자주 나온다.",
        "We built a small test harness that replays recorded requests.",
        "녹화해 둔 요청을 다시 보내는 작은 테스트 하네스를 만들었습니다.",
    ),
    (
        "test oracle", "/ˈtest ˌɔrəkəl/", "테스트 결과가 맞는지 판단하는 기준",
        DEBUG, H,
        "테스트를 돌린 결과가 맞는지 틀린지를 판정하는 기준. 기대값을 미리 적어 둔 표일 수도 있고, 이전 버전의 결과나 다른 계산 "
        "방법일 수도 있다. 데이터베이스 제품 이름과는 상관없는 말이다. 정처기에서는 참, 샘플링, 추정, 일관성 검사 오라클로 나눠 "
        "묻는다.",
        "The old report output serves as our test oracle for the rewrite.",
        "다시 짠 코드의 정답 기준으로 예전 리포트 출력을 씁니다.",
    ),
    (
        "test pyramid", "/ˈtest ˌpɪrəmɪd/", "단위 테스트를 가장 많이 두라는 테스트 비율 모델",
        DEBUG, N,
        "빠르고 싼 단위 테스트를 가장 많이, 통합 테스트를 그다음, 느리고 비싼 E2E 테스트를 가장 적게 두라는 그림. 거꾸로 E2E "
        "위주로 쌓으면 테스트가 느리고 자주 깨져서 결국 아무도 결과를 믿지 않게 된다. 화면을 직접 누르는 테스트는 꼭 지켜야 할 "
        "흐름에만 둔다.",
        "Our test pyramid is upside down; we have more E2E tests than unit tests.",
        "우리 테스트 피라미드는 거꾸로예요. E2E 테스트가 단위 테스트보다 많아요.",
    ),
    (
        "test suite", "/ˈtest ˌswit/", "함께 돌리는 테스트 묶음",
        DEBUG, N,
        "여러 테스트를 한데 묶어 한 번에 돌리는 단위. 보통 프로젝트 전체 테스트나 한 모듈의 테스트를 가리킨다. 전체 묶음이 오래 "
        "걸리면 사람들이 덜 돌리게 되므로 느린 테스트를 따로 빼서 관리하기도 한다. 정처기에서는 테스트 하네스의 구성 요소로 나온다.",
        "The full test suite takes twelve minutes on CI.",
        "CI 에서 전체 테스트를 돌리는 데 12분이 걸립니다.",
    ),
    (
        "throw", "/θroʊ/", "예외를 일부러 일으켜 위로 넘기다",
        DEBUG, E,
        "더 진행할 수 없는 상황을 만났을 때 예외를 만들어 호출한 쪽으로 넘기는 것. 자바와 자바스크립트는 throw, 파이썬은 "
        "raise 라고 쓰지만 뜻은 같다. 넘어온 예외를 받아서 처리하는 쪽의 동작은 catch 라고 부른다.",
        "The parser should throw if the date format is wrong.",
        "날짜 형식이 틀리면 파서가 예외를 던져야 합니다.",
    ),
    (
        "timestamp", "/ˈtaɪmˌstæmp/", "언제 일어났는지 찍어 둔 시각",
        DEBUG, E,
        "어떤 일이 일어난 날짜와 시각을 기록한 값. 로그 한 줄마다 붙어 있어서 장애 시각 앞뒤를 좁혀 볼 때 기준이 된다. 서버마다 "
        "시간대가 다르면 같은 사건도 몇 시간씩 어긋나 보이므로 보통 UTC 로 남기고 읽을 때 바꿔 본다.",
        "The timestamp is in UTC, so add nine hours for Seoul time.",
        "타임스탬프가 UTC 라서 서울 시간으로 보려면 아홉 시간을 더하세요.",
    ),
    (
        "triage", "/triˈɑʒ/", "들어온 이슈를 급한 순서로 분류하기",
        DEBUG, H,
        "쌓인 버그와 이슈를 보고 얼마나 심각한지, 누가 맡을지, 언제 고칠지를 정해 나누는 일. 응급실에서 환자를 위급한 순서로 나누는 "
        "말에서 왔다. 모든 이슈를 바로 고치려 들기보다 먼저 분류해야 중요한 것을 놓치지 않는다.",
        "We triage new issues every Monday morning.",
        "새로 들어온 이슈는 매주 월요일 아침에 분류합니다.",
    ),
    (
        "troubleshoot", "/ˈtrʌbəlˌʃut/", "설치·설정·네트워크까지 문제 원인을 좁혀 해결하다",
        DEBUG, N,
        "문제가 생겼을 때 원인 후보를 하나씩 확인해 좁혀 가며 해결하는 것. 코드 버그뿐 아니라 설치, 네트워크, 설정 문제까지 넓게 "
        "쓴다. 문서의 Troubleshooting 절에는 자주 겪는 증상과 해결법이 모여 있으니 검색하기 전에 먼저 본다.",
        "Can you help me troubleshoot why the build is so slow?",
        "빌드가 왜 이렇게 느린지 원인 찾는 것 좀 도와줄 수 있어요?",
    ),
    (
        "unhandled", "/ʌnˈhændəld/", "아무 데서도 처리하지 않은",
        DEBUG, N,
        "예외나 에러를 어디서도 잡아 처리하지 않았다는 뜻으로 에러 메시지에 자주 나온다. 자바스크립트의 Unhandled Promise "
        "Rejection 은 실패한 비동기 작업에 catch 를 달지 않았다는 뜻인데, Node 15 부터는 경고로 끝나지 않고 "
        "프로세스가 그대로 종료된다. 비슷한 뜻으로 uncaught 도 쓴다.",
        "The worker crashed on an unhandled promise rejection from fetch.",
        "fetch 에서 난 프로미스 거부를 아무도 처리하지 않아 워커가 죽었습니다.",
    ),
    (
        "unresolved", "/ˌʌnrɪˈzɑlvd/", "무엇을 가리키는지 찾지 못한",
        DEBUG, N,
        "코드에 적힌 이름이 무엇을 가리키는지 찾지 못했다는 뜻. 에디터의 unresolved import 는 패키지를 설치하지 않았거나 "
        "가상환경을 잘못 골랐을 때 자주 뜬다. 이슈나 리뷰 댓글에서는 아직 해결되지 않았다는 뜻으로도 쓴다.",
        "The editor marks the import as unresolved because the venv is not selected.",
        "가상환경이 선택되지 않아서 에디터가 그 import 를 찾을 수 없다고 표시합니다.",
    ),
    (
        "workaround", "/ˈwɜrkəˌraʊnd/", "근본 해결 전에 임시로 피해 가는 방법",
        DEBUG, N,
        "문제의 원인을 고치지 못한 채 일단 증상을 피해 가는 임시 방법. 당장 서비스를 살리는 데는 유용하지만 그대로 굳어 버리기 "
        "쉬워서, 이슈를 남겨 언제 걷어 낼지 적어 둔다. 코드에도 왜 이렇게 했는지 주석을 남겨야 다음 사람이 함부로 지우지 않는다.",
        "This is a workaround until the library fixes the upstream bug.",
        "라이브러리 쪽에서 버그를 고칠 때까지 쓰는 임시방편입니다.",
    ),
    # ---------- 프론트엔드 ----------
    (
        "alt text", "/ˈɔlt ˌtekst/", "이미지를 못 볼 때 대신 읽어 주는 설명 글",
        FRONT, E,
        "img 태그의 alt 속성에 적는 이미지 설명. 화면 낭독기가 소리로 읽고, 이미지가 깨졌을 때 그 자리에 보인다. 장식용 "
        "이미지는 빈 값으로 두어 건너뛰게 하고, 파일 이름이나 이미지라는 말을 그대로 넣는 것은 도움이 안 된다.",
        "The logo needs alt text, but the background pattern doesn't.",
        "로고에는 대체 텍스트가 필요하지만 배경 무늬에는 필요 없습니다.",
    ),
    (
        "arrow function", "/ˈæroʊ ˌfʌŋkʃən/", "=> 로 짧게 쓰는 자바스크립트 함수",
        FRONT, E,
        "function 키워드 대신 화살표로 쓰는 함수 문법. 짧아서 콜백과 컴포넌트에 많이 쓴다. 일반 함수와 달리 자기만의 this "
        "를 갖지 않고 바깥의 this 를 그대로 쓰기 때문에, 객체의 메서드로 쓰면 this 가 기대와 다르게 나온다.",
        "This callback is short enough to write as an arrow function.",
        "이 콜백은 화살표 함수로 써도 될 만큼 짧습니다.",
    ),
    (
        "async/await", "/ˌeɪsɪŋk əˈweɪt/", "비동기 작업을 순서대로 쓰게 해 주는 문법",
        FRONT, N,
        "Promise 를 then 으로 줄줄이 잇는 대신 await 로 결과를 기다리며 위에서 아래로 쓰게 해 준다. await 는 "
        "async 함수 안에서만 쓸 수 있다. 서로 상관없는 요청을 하나씩 await 하면 차례로 기다리느라 느려지므로, 그럴 때는 "
        "Promise.all 로 함께 보낸다.",
        "Rewrite these nested callbacks with async/await.",
        "중첩된 콜백을 async/await 로 다시 써 주세요.",
    ),
    (
        "cache busting", "/ˈkæʃ ˌbʌstɪŋ/", "파일 이름을 바꿔 브라우저가 새 파일을 받게 하기",
        FRONT, H,
        "app.3f9a1c.js 처럼 내용이 바뀔 때마다 파일 이름에 해시를 붙여, 브라우저가 옛 캐시 대신 새 파일을 받게 하는 방법. "
        "이름이 바뀌니 파일은 아주 오래 캐시해도 안전하다. 다만 해시가 없는 index.html 까지 길게 캐시하면 새 배포가 안 "
        "보인다.",
        "Cache busting is off, so users keep getting the old CSS.",
        "캐시 버스팅이 꺼져 있어서 사용자들이 계속 예전 CSS 를 받습니다.",
    ),
    (
        "chunk", "/tʃʌŋk/", "빌드 결과를 나눈 자바스크립트 파일 조각",
        FRONT, N,
        "코드 분할로 쪼개진 자바스크립트 파일 하나하나. 사용자가 그 화면으로 갈 때 필요한 조각만 받는다. 배포 직후 예전 화면을 열어 "
        "둔 사용자가 다른 화면으로 이동하면, 이미 지워진 옛 조각을 찾다가 ChunkLoadError 가 나기도 한다.",
        "The admin page is split into its own chunk.",
        "관리자 페이지는 따로 청크로 나뉘어 있습니다.",
    ),
    (
        "contrast ratio", "/ˈkɑntræst ˌreɪʃoʊ/", "글자색과 바탕색의 밝기 차이를 잰 비율",
        FRONT, N,
        "글자가 바탕에서 얼마나 또렷이 보이는지를 1:1 부터 21:1 까지의 비율로 나타낸 값. 접근성 기준은 보통 글자에 4.5:1 "
        "이상을 요구한다. 디자인 시안에서는 예뻐 보이던 연회색 글자가 이 기준에 못 미쳐 고쳐지는 일이 많다.",
        "The gray caption doesn't meet the minimum contrast ratio on white.",
        "흰 바탕 위 회색 설명 글이 명암비 기준에 못 미칩니다.",
    ),
    (
        "CSS variable", "/ˌsi es ˈes ˌveriəbəl/", "CSS 안에서 값에 이름을 붙여 재사용하는 것",
        FRONT, N,
        "--color-primary 처럼 하이픈 두 개로 시작하는 이름에 값을 담아 두고 var() 로 꺼내 쓴다. 정식 이름은 "
        "custom property 다. 빌드할 때 사라지는 전처리기 변수와 달리 브라우저에서 살아 있어, 다크 모드처럼 실행 중에 값을 "
        "바꿔 테마를 바꿀 수 있다.",
        "Replace the hard-coded hex with the CSS variable for the brand color.",
        "직접 적은 색상값을 브랜드 색 CSS 변수로 바꿔 주세요.",
    ),
    (
        "dark mode", "/ˈdɑrk ˌmoʊd/", "어두운 바탕에 밝은 글자로 바꾼 화면",
        FRONT, E,
        "운영체제나 앱 설정에 맞춰 바탕을 어둡게 바꾸는 화면 테마. CSS 에서는 사용자의 설정을 읽어 색을 바꾼다. 색을 단순히 "
        "뒤집으면 그림자나 강조색이 어색해지므로, 색을 변수로 묶어 두고 테마별로 값을 따로 정하는 것이 보통이다.",
        "The error text is unreadable in dark mode.",
        "다크 모드에서 에러 문구가 안 보입니다.",
    ),
    (
        "dependency array", "/dɪˈpendənsi əˌreɪ/", "useEffect 가 언제 다시 돌지 정하는 배열",
        FRONT, N,
        "useEffect 나 useMemo 의 두 번째 인자로 넘기는 배열. 안에 적은 값이 바뀔 때만 다시 실행된다. 쓰는 값을 "
        "빠뜨리면 예전 값을 계속 보게 되고, 매번 새로 만들어지는 객체를 넣으면 렌더링마다 실행되어 무한 반복에 빠지기도 한다.",
        "Add userId to the dependency array or the effect won't rerun.",
        "userId 를 의존성 배열에 넣지 않으면 이펙트가 다시 안 돕니다.",
    ),
    (
        "derived state", "/dɪˈraɪvd ˌsteɪt/", "다른 상태에서 계산해 낼 수 있는 값",
        FRONT, H,
        "목록과 검색어가 있으면 걸러진 목록은 계산으로 얻을 수 있는데, 이런 값을 말한다. 이것을 따로 상태로 만들어 두면 원래 값이 "
        "바뀔 때마다 함께 맞춰 줘야 하고, 하나를 빠뜨리면 화면이 어긋난다. 상태로 두지 말고 렌더링할 때 계산하는 것이 원칙이다.",
        "The total is derived state; compute it instead of storing it.",
        "합계는 파생 상태예요. 저장하지 말고 계산하세요.",
    ),
    (
        "destructuring", "/diˈstrʌktʃərɪŋ/", "객체나 배열에서 값을 꺼내 바로 변수에 담는 문법",
        FRONT, N,
        "const { name, age } = user 처럼 필요한 값만 골라 한 줄로 변수에 담는다. 컴포넌트에서 props 를 받을 "
        "때 거의 늘 쓴다. 꺼내려는 값이 없으면 에러 대신 undefined 가 들어가므로, 기본값을 함께 적어 두면 안전하다.",
        "Use destructuring to pull out only the props you need.",
        "구조 분해로 필요한 props 만 꺼내 쓰세요.",
    ),
    (
        "dev server", "/ˈdev ˌsɜrvər/", "개발하면서 띄워 보는 로컬 서버",
        FRONT, E,
        "npm run dev 처럼 내 컴퓨터에서 띄워 코드를 고치면 바로 화면에 반영되게 해 주는 서버. 빨리 보여주려고 최적화를 "
        "건너뛰기 때문에 속도나 동작이 운영 빌드와 다를 수 있다. 성능을 재거나 최종 확인을 할 때는 빌드한 결과로 본다.",
        "Restart the dev server after changing the env file.",
        "env 파일을 바꿨으면 개발 서버를 다시 띄우세요.",
    ),
    (
        "DevTools", "/ˈdevˌtulz/", "브라우저에 들어 있는 개발자 도구",
        FRONT, E,
        "F12 를 누르면 열리는 브라우저 내장 도구. 요소의 스타일을 바로 고쳐 보고, 콘솔 에러와 네트워크 요청을 확인하고, 폰 화면 "
        "크기로 바꿔 볼 수 있다. 여기서 고친 스타일은 새로고침하면 사라지므로 맞는 값을 찾으면 코드에 옮겨 적어야 한다.",
        "Open DevTools and check the failed request in the Network tab.",
        "개발자 도구를 열고 네트워크 탭에서 실패한 요청을 확인하세요.",
    ),
    (
        "element", "/ˈeləmənt/", "태그 하나로 만들어진 DOM 의 한 조각",
        FRONT, E,
        "div 나 button 처럼 태그로 만든 화면의 한 조각. 브라우저는 이 요소들을 부모와 자식으로 이어 DOM 이라는 나무 "
        "모양으로 들고 있다. 태그는 코드에 적은 글자이고 요소는 그걸 읽어 만든 실제 객체라서, 스크립트로 바꾸는 대상은 요소다.",
        "The close button element is hidden behind the header.",
        "닫기 버튼 요소가 헤더 뒤에 가려져 있습니다.",
    ),
    (
        "ES module", "/ˌi ˈes ˌmɑdʒul/", "import 와 export 로 파일을 나누는 표준 모듈 방식",
        FRONT, N,
        "자바스크립트 표준이 정한 모듈 방식으로 import 와 export 를 쓴다. Node 에서 오래 쓰던 require 방식과 "
        "섞으면 Cannot use import statement outside a module 같은 에러가 난다. 무엇을 가져다 쓰는지 "
        "미리 알 수 있어 번들러가 안 쓰는 코드를 덜어낼 수 있다.",
        "This package ships only as an ES module, so require won't work.",
        "이 패키지는 ES 모듈로만 나와서 require 로는 안 됩니다.",
    ),
    (
        "event listener", "/ɪˈvent ˌlɪsənər/", "이벤트가 일어나면 실행되도록 걸어 둔 함수",
        FRONT, N,
        "클릭, 입력, 스크롤 같은 일이 생기면 부르도록 요소에 등록해 둔 함수. addEventListener 로 건다. 화면에서 "
        "사라지는 컴포넌트에서 걸어 둔 것을 떼지 않으면 계속 남아 같은 일이 여러 번 실행되거나 메모리가 샌다.",
        "Remove the scroll event listener when the component unmounts.",
        "컴포넌트가 사라질 때 스크롤 이벤트 리스너를 떼어 주세요.",
    ),
    (
        "focus ring", "/ˈfoʊkəs ˌrɪŋ/", "키보드로 고른 요소에 그려지는 테두리",
        FRONT, N,
        "Tab 키로 이동할 때 지금 어느 버튼에 있는지 보여주는 테두리. 마우스로 누를 때 보기 싫다고 outline 을 없애 버리면 "
        "키보드 사용자는 위치를 잃는다. 없애지 말고 :focus-visible 로 키보드로 왔을 때만 보이게 하는 것이 요즘 방식이다.",
        "Don't remove the focus ring; use focus-visible instead.",
        "포커스 링을 없애지 말고 focus-visible 을 쓰세요.",
    ),
    (
        "focus trap", "/ˈfoʊkəs ˌtræp/", "키보드 포커스가 창 밖으로 못 나가게 가두기",
        FRONT, H,
        "모달이 열려 있는 동안 Tab 키를 눌러도 포커스가 창 안에서만 돌게 하는 것. 이게 없으면 키보드 사용자가 보이지 않는 뒤쪽 "
        "화면으로 빠져나가 길을 잃는다. 창을 닫을 때는 열기 전에 누르던 버튼으로 포커스를 돌려줘야 한다.",
        "The dialog needs a focus trap; Tab escapes to the page behind.",
        "대화상자에 포커스 트랩이 필요해요. Tab 을 누르면 뒤 페이지로 빠져나갑니다.",
    ),
    (
        "global state", "/ˈɡloʊbəl ˌsteɪt/", "여러 화면이 함께 꺼내 쓰는 상태",
        FRONT, N,
        "로그인한 사용자나 테마처럼 앱 곳곳에서 필요한 값을 한 곳에 두고 어디서든 읽게 한 상태. props 를 여러 단계 내려보내는 "
        "수고를 덜어 준다. 무엇이든 여기에 넣으면 어디서 바뀌었는지 추적하기 어려우므로, 한 화면에서만 쓰는 값은 그 컴포넌트에 둔다.",
        "The theme lives in global state so every page can read it.",
        "테마는 전역 상태에 있어서 어느 페이지든 읽을 수 있습니다.",
    ),
    (
        "hard refresh", "/ˈhɑrd rɪˌfreʃ/", "캐시를 무시하고 페이지를 새로 받기",
        FRONT, E,
        "브라우저가 저장해 둔 파일을 쓰지 않고 서버에서 전부 다시 받아 새로고침하는 것. 윈도우에서는 Ctrl+Shift+R 이다. "
        "배포했는데 화면이 안 바뀐다는 말이 나오면 먼저 해 보게 하지만, 사용자에게 매번 시킬 수는 없으니 근본 해결은 캐시 설정 "
        "쪽이다.",
        "Do a hard refresh; you're still seeing the old bundle.",
        "강력 새로고침 해 보세요. 아직 예전 번들을 보고 계세요.",
    ),
    (
        "hoisting", "/ˈhɔɪstɪŋ/", "선언이 코드 맨 위로 끌어올려진 것처럼 동작하는 것",
        FRONT, H,
        "자바스크립트가 실행 전에 변수와 함수 선언을 먼저 훑어 두기 때문에, 선언보다 위에서 써도 에러가 안 나는 것처럼 보이는 현상. "
        "var 는 undefined 로 읽히고, let 과 const 는 선언 전에 읽으면 에러가 난다. 실제로 코드가 옮겨지는 것은 "
        "아니다.",
        "This works only because of hoisting; move the function up.",
        "호이스팅 덕분에 돌아가는 거예요. 함수를 위로 옮기세요.",
    ),
    (
        "iframe", "/ˈaɪˌfreɪm/", "페이지 안에 다른 페이지를 끼워 넣는 태그",
        FRONT, N,
        "유튜브 영상이나 지도, 결제창처럼 다른 사이트의 화면을 내 페이지 안에 창처럼 넣는다. 출처가 다르면 안과 밖은 보안상 서로의 "
        "내용을 마음대로 읽지 못한다. 높이가 내용에 맞춰 저절로 늘지 않아 잘려 보이는 문제가 흔하다.",
        "The payment form loads inside an iframe from the provider.",
        "결제 폼은 결제사에서 주는 아이프레임 안에 뜹니다.",
    ),
    (
        "lifting state up", "/ˌlɪftɪŋ ˌsteɪt ˈʌp/", "형제끼리 나눌 상태를 공통 부모로 옮기기",
        FRONT, N,
        "두 컴포넌트가 같은 값을 알아야 할 때, 그 상태를 둘의 가장 가까운 공통 부모로 올리고 props 로 내려 주는 것. React "
        "공식 문서가 권하는 기본 해법이다. 너무 위까지 올리면 상관없는 컴포넌트까지 다시 그려지므로 필요한 만큼만 올린다.",
        "Try lifting state up to the parent instead of syncing two states.",
        "상태 두 개를 맞추지 말고 부모로 끌어올려 보세요.",
    ),
    (
        "main thread", "/ˈmeɪn ˌθred/", "화면 그리기와 스크립트를 함께 맡는 단 하나의 실행 흐름",
        FRONT, N,
        "브라우저에서 자바스크립트 실행, 스타일 계산, 화면 그리기를 모두 맡는 하나의 실행 흐름. 여기서 무거운 계산을 오래 돌리면 "
        "그동안 클릭도 스크롤도 반응하지 않는다. 오래 걸리는 일은 잘게 나누거나 web worker 로 넘긴다.",
        "Parsing this JSON blocks the main thread for two seconds.",
        "이 JSON 을 파싱하느라 메인 스레드가 2초 동안 막힙니다.",
    ),
    (
        "margin", "/ˈmɑrdʒɪn/", "요소 테두리 바깥쪽 여백",
        FRONT, E,
        "요소와 주변 요소 사이를 벌리는 바깥 여백. 위아래로 붙은 두 요소의 margin 은 더해지지 않고 큰 쪽 하나로 겹치는 경우가 "
        "있어, 간격이 생각보다 좁게 나오면 이것부터 의심한다. 배경색은 margin 까지 칠해지지 않는다.",
        "Remove the bottom margin on the last list item.",
        "목록 마지막 항목의 아래 마진을 없애 주세요.",
    ),
    (
        "microtask", "/ˈmaɪkroʊˌtæsk/", "지금 코드가 끝나자마자 먼저 처리되는 대기열 작업",
        FRONT, H,
        "Promise 의 then 이나 await 뒤의 코드가 들어가는 대기열. 지금 실행 중인 코드가 끝나면 setTimeout 같은 "
        "일반 작업보다 먼저 전부 비운다. 그래서 setTimeout 0 보다 Promise 가 먼저 찍히고, 이 대기열을 끝없이 채우면 "
        "화면이 멈춘다.",
        "The promise callback runs as a microtask before the timeout.",
        "프로미스 콜백은 마이크로태스크라서 타임아웃보다 먼저 실행됩니다.",
    ),
    (
        "mockup", "/ˈmɑkˌʌp/", "색과 글꼴까지 입혀 실제처럼 만든 정적 화면 시안",
        FRONT, N,
        "와이어프레임에 색, 글꼴, 이미지를 입혀 완성된 화면처럼 보이게 만든 시안. 겉모습은 실제와 같지만 눌러도 동작하지 않는다는 점이 "
        "프로토타입과 다르다. 정보처리기사 UI 설계 도구 문제에서 와이어프레임, 프로토타입과의 차이를 자주 묻는다.",
        "The mockup uses a font we don't have a license for.",
        "목업에 쓴 글꼴은 우리한테 라이선스가 없어요.",
    ),
    (
        "modal", "/ˈmoʊdəl/", "화면 위에 떠서 뒤를 막는 창",
        FRONT, E,
        "현재 화면 위에 띄워 사용자가 닫기 전까지 뒤쪽을 못 누르게 하는 창. 확인이나 입력처럼 꼭 답을 받아야 할 때 쓴다. 남발하면 "
        "흐름을 끊고, 포커스를 창 안에 가두고 Esc 로 닫히게 하지 않으면 키보드 사용자가 길을 잃는다.",
        "Close the modal when the user presses Escape.",
        "사용자가 Esc 를 누르면 모달을 닫아 주세요.",
    ),
    (
        "nullish coalescing", "/ˈnʌlɪʃ koʊəˌlesɪŋ/", "null 이나 undefined 일 때만 기본값을 쓰는 ?? 연산자",
        FRONT, H,
        "a ?? b 는 a 가 null 이나 undefined 일 때만 b 를 쓴다. 비슷하게 쓰던 || 는 0 이나 빈 문자열까지 없는 "
        "값으로 보고 기본값으로 바꿔 버려, 점수 0 점이 기본값으로 덮이는 버그를 만든다. 0 이 의미 있는 값이면 이쪽을 쓴다.",
        "Use nullish coalescing so a score of zero isn't replaced.",
        "0점이 기본값으로 바뀌지 않게 널 병합 연산자를 쓰세요.",
    ),
    (
        "optimistic update", "/ˌɑptəˈmɪstɪk ˌʌpdeɪt/", "서버 응답 전에 성공했다고 보고 화면부터 바꾸기",
        FRONT, H,
        "좋아요 버튼처럼 대부분 성공하는 요청은 응답을 기다리지 않고 화면을 먼저 바꿔 빠르게 느끼게 한다. 요청이 실패하면 바꾼 화면을 "
        "원래대로 되돌리고 알려줘야 하는데, 이 되돌리기를 빠뜨리면 저장 안 된 것이 저장된 것처럼 보인다.",
        "Use an optimistic update so the bookmark icon fills instantly.",
        "북마크 아이콘이 바로 채워지도록 낙관적 업데이트를 쓰세요.",
    ),
    (
        "optional chaining", "/ˈɑpʃənəl ˌtʃeɪnɪŋ/", "값이 없으면 멈추고 undefined 를 주는 ?. 문법",
        FRONT, N,
        "user?.profile?.name 처럼 쓰면 중간 값이 null 이나 undefined 일 때 에러를 내지 않고 "
        "undefined 를 돌려준다. 응답이 오기 전의 데이터를 읽다 터지는 에러를 줄여 준다. 다만 있어야 할 값이 없는 진짜 "
        "버그까지 조용히 숨길 수 있어 아무 데나 붙이지 않는다.",
        "Use optional chaining here; the address can be missing.",
        "주소가 없을 수 있으니 여기엔 옵셔널 체이닝을 쓰세요.",
    ),
    (
        "padding", "/ˈpædɪŋ/", "요소 테두리 안쪽 여백",
        FRONT, E,
        "테두리와 안의 내용 사이를 띄우는 안쪽 여백. margin 과 달리 배경색이 이 영역까지 칠해지고, 클릭할 수 있는 범위도 "
        "넓어진다. 너비를 정해 둔 요소에 padding 을 더하면 전체가 넓어질 수 있어 box-sizing 설정을 함께 확인한다.",
        "Increase the padding so the button is easier to tap.",
        "버튼을 누르기 쉽게 패딩을 키워 주세요.",
    ),
    (
        "placeholder", "/ˈpleɪsˌhoʊldər/", "입력칸이 비었을 때 흐리게 보이는 안내 글",
        FRONT, E,
        "입력칸에 아무것도 없을 때 보여주는 예시 글. 글자를 치면 사라지므로 이름표 대신 쓰면 무엇을 적는 칸이었는지 잊게 되고, 화면 "
        "낭독기가 읽지 않는 경우도 있다. 칸의 이름은 label 로 따로 달고 이것은 예시로만 쓴다.",
        "Don't use the placeholder as a label for the email field.",
        "이메일 칸의 이름표로 플레이스홀더를 쓰지 마세요.",
    ),
    (
        "preventDefault", "/prɪˌvent dɪˈfɔlt/", "브라우저의 기본 동작을 막는 메서드",
        FRONT, N,
        "폼을 제출하면 페이지가 새로고침되고 링크를 누르면 이동하는 것처럼 브라우저가 원래 하던 동작을 멈춘다. 이벤트가 부모로 퍼지는 "
        "것을 막는 stopPropagation 과 자주 헷갈리는데, 둘은 막는 대상이 다르다. 필요하면 둘을 함께 부른다.",
        "Call preventDefault so the form doesn't reload the page.",
        "폼이 페이지를 새로고침하지 않도록 preventDefault 를 호출하세요.",
    ),
    (
        "pseudo-class", "/ˈsudoʊ ˌklæs/", "마우스를 올렸을 때처럼 상태에 따라 고르는 CSS 선택자",
        FRONT, N,
        ":hover, :focus, :disabled 처럼 요소가 어떤 상태일 때만 스타일을 입히는 선택자로, 콜론 하나로 쓴다. 콜론 "
        "두 개인 ::before 같은 가상 요소와 헷갈리는데, 가상 요소는 상태가 아니라 없는 요소를 새로 만들어 꾸미는 것이다.",
        "Add a focus pseudo-class style for keyboard users.",
        "키보드 사용자를 위해 focus 가상 클래스 스타일을 넣어 주세요.",
    ),
    (
        "re-render", "/ˌriˈrendər/", "바뀐 값으로 화면을 다시 그리기",
        FRONT, N,
        "상태나 props 가 바뀌어 컴포넌트를 다시 실행하고 화면을 새로 그리는 것. 부모가 다시 그려지면 자식도 따라 다시 그려지는 "
        "것이 React 의 기본이다. 대부분은 빨라서 문제가 없으니, 실제로 느려진 것을 확인한 뒤에 줄이는 작업을 한다.",
        "Typing in the search box makes the whole list re-render.",
        "검색창에 입력할 때마다 목록 전체가 다시 렌더링됩니다.",
    ),
    (
        "render-blocking", "/ˈrendər ˌblɑkɪŋ/", "다 받기 전까지 화면을 못 그리게 막는",
        FRONT, H,
        "head 에 넣은 CSS 와 일반 script 처럼, 브라우저가 다 받고 처리하기 전에는 화면을 그리지 않는 자원을 가리킨다. "
        "많을수록 첫 화면이 늦게 뜬다. 스크립트는 defer 나 async 를 붙이고, 첫 화면에 필요 없는 CSS 는 나중에 받게 "
        "한다.",
        "Lighthouse flags this stylesheet as render-blocking.",
        "라이트하우스가 이 스타일시트를 렌더링 차단 리소스로 표시합니다.",
    ),
    (
        "safe area", "/ˈseɪf ˌeriə/", "노치와 홈 표시줄에 가리지 않는 화면 영역",
        FRONT, N,
        "폰의 노치, 둥근 모서리, 아래쪽 홈 표시줄을 뺀 나머지 안전한 영역. CSS 에서는 "
        "env(safe-area-inset-bottom) 같은 값으로 그만큼 띄운다. 이를 무시하면 하단 탭바나 버튼이 홈 표시줄과 겹쳐 "
        "누르기 어려워진다.",
        "On iPhone, the tab bar needs padding for the bottom safe area.",
        "아이폰에서는 탭바 아래에 세이프 에어리어만큼 여백을 줘야 합니다.",
    ),
    (
        "same-origin policy", "/ˌseɪm ˈɔrədʒɪn ˌpɑləsi/", "출처가 다른 곳의 응답을 못 읽게 막는 브라우저 규칙",
        FRONT, H,
        "프로토콜, 도메인, 포트가 모두 같아야 같은 출처로 보고, 다르면 스크립트가 응답을 읽지 못하게 막는 브라우저의 기본 보안 규칙. "
        "CORS 는 서버가 허락해 이 규칙에 예외를 여는 장치다. 서버끼리 보내는 요청이나 curl 에는 이 규칙이 없어서 거기서는 잘 "
        "된다.",
        "The same-origin policy blocks the script from reading that response.",
        "동일 출처 정책 때문에 스크립트가 그 응답을 읽지 못합니다.",
    ),
    (
        "screen reader", "/ˈskrin ˌridər/", "화면 내용을 소리로 읽어 주는 프로그램",
        FRONT, E,
        "눈이 불편한 사람이 화면의 글과 버튼을 소리로 듣게 해 주는 보조 기술. 아이폰의 VoiceOver, 안드로이드의 TalkBack "
        "이 대표적이다. 눈으로 보기에 버튼이어도 div 로 만들면 버튼으로 읽히지 않아, 의미에 맞는 태그를 쓰는 것이 출발점이다.",
        "The screen reader announces this icon as just 'button'.",
        "화면 낭독기가 이 아이콘을 그냥 '버튼' 이라고만 읽습니다.",
    ),
    (
        "selector", "/səˈlektər/", "스타일을 입힐 요소를 고르는 규칙",
        FRONT, E,
        ".card 나 #header 처럼 CSS 가 어떤 요소에 적용될지 가리키는 부분. 자바스크립트에서 요소를 찾을 때도 같은 문법을 "
        "쓴다. 길고 구체적으로 쓸수록 우선순위가 높아져 나중에 덮어쓰기 어려우므로, 짧은 클래스 하나로 고르는 편이 관리하기 쉽다.",
        "This selector is too specific; just use a class.",
        "이 선택자는 너무 구체적이에요. 클래스 하나면 됩니다.",
    ),
    (
        "server component", "/ˈsɜrvər kəmˌpoʊnənt/", "서버에서만 실행되고 결과만 보내는 컴포넌트",
        FRONT, H,
        "서버에서 미리 실행되고 그 결과만 브라우저로 보내는 React 컴포넌트로, Next.js App Router 에서는 기본값이다. "
        "코드를 브라우저로 안 보내 가볍지만 useState 나 onClick 은 쓸 수 없어, 그런 부분은 use client 를 단 "
        "파일로 떼어 낸다.",
        "Fetch the words in a server component, not in useEffect.",
        "단어 목록은 useEffect 말고 서버 컴포넌트에서 가져오세요.",
    ),
    (
        "sessionStorage", "/ˈseʃən ˌstɔrɪdʒ/", "탭을 닫으면 지워지는 브라우저 저장소",
        FRONT, N,
        "localStorage 처럼 브라우저에 키와 값을 저장하지만 그 탭을 닫으면 사라진다. 같은 사이트를 새 탭으로 열어도 공유되지 "
        "않는다. 자바스크립트로 누구나 읽을 수 있으므로 로그인 토큰 같은 민감한 값을 두기에 안전한 곳은 아니다.",
        "Keep the quiz progress in sessionStorage so a refresh doesn't lose it.",
        "새로고침해도 안 날아가게 문제 풀이 진행 상황을 세션 스토리지에 두세요.",
    ),
    (
        "skeleton screen", "/ˈskelətən ˌskrin/", "로딩 중에 내용 자리를 회색 틀로 보여주는 화면",
        FRONT, N,
        "데이터가 오기 전에 글과 이미지가 놓일 자리를 회색 상자로 먼저 그려 두는 로딩 방식. 빙글 도는 표시보다 기다림이 짧게 "
        "느껴지고, 내용이 들어와도 배치가 덜 흔들린다. 틀의 크기가 실제 내용과 많이 다르면 오히려 화면이 출렁인다.",
        "Show a skeleton screen instead of a spinner on the word list.",
        "단어 목록에는 스피너 대신 스켈레톤 화면을 보여 주세요.",
    ),
    (
        "spread operator", "/ˈspred ˌɑpəreɪtər/", "배열이나 객체를 ... 으로 펼쳐 복사하는 문법",
        FRONT, N,
        "점 세 개를 앞에 붙여 배열이나 객체의 내용을 펼친다. 상태를 바꿀 때 원본을 건드리지 않고 새 객체를 만드는 데 많이 쓴다. "
        "바깥 한 겹만 복사하므로 안쪽 객체는 원본과 같은 것을 가리켜, 안쪽을 고치면 원본도 함께 바뀐다.",
        "Copy the state with the spread operator before changing it.",
        "바꾸기 전에 스프레드 연산자로 상태를 복사하세요.",
    ),
    (
        "stacking context", "/ˈstækɪŋ ˌkɑntekst/", "z-index 가 비교되는 하나의 층 묶음",
        FRONT, H,
        "z-index 는 같은 묶음 안에서만 비교되는데, 그 묶음을 말한다. 부모에 transform 을 주거나 opacity 를 1 "
        "미만으로 두면 새 묶음이 생겨, 자식의 z-index 를 아무리 키워도 바깥 요소 위로 못 올라간다. 9999 로 올려도 안 될 "
        "때 원인이 대개 이것이다.",
        "The transform creates a new stacking context, so z-index won't help.",
        "transform 이 새 쌓임 맥락을 만들어서 z-index 로는 안 됩니다.",
    ),
    (
        "stale closure", "/ˈsteɪl ˌkloʊʒər/", "함수가 예전 값을 붙든 채 계속 쓰는 문제",
        FRONT, H,
        "함수가 만들어질 때의 변수를 기억하는 성질 때문에, 값이 바뀐 뒤에도 옛 값을 보는 버그. React 에서 setInterval "
        "이나 이벤트 핸들러 안의 상태가 계속 처음 값으로 보이면 대개 이것이다. 의존성 배열을 채우거나 함수형 업데이트로 고친다.",
        "The counter is stuck at one because of a stale closure.",
        "오래된 클로저 때문에 카운터가 1 에서 멈춰 있습니다.",
    ),
    (
        "template literal", "/ˈtemplət ˌlɪtərəl/", "백틱으로 감싸 변수를 끼워 넣는 문자열",
        FRONT, N,
        "따옴표 대신 백틱으로 감싸고 그 안에 ${name} 처럼 값을 끼워 넣는 문자열. 더하기로 이어 붙이는 것보다 읽기 쉽고 여러 "
        "줄도 그대로 쓸 수 있다. 다만 사용자가 입력한 값을 그대로 넣어 HTML 이나 SQL 을 만들면 공격에 뚫린다.",
        "Build the URL with a template literal instead of string concatenation.",
        "URL 은 문자열을 더하지 말고 템플릿 리터럴로 만드세요.",
    ),
    (
        "toast", "/toʊst/", "잠깐 떴다 사라지는 작은 알림",
        FRONT, E,
        "저장했다는 식의 짧은 결과를 화면 구석에 몇 초 보여주고 스스로 사라지는 알림. 토스터에서 빵이 튀어 오르는 모양에서 온 "
        "이름이다. 금방 사라지므로 사용자가 꼭 읽고 행동해야 하는 에러는 화면에 남는 안내로 보여주는 것이 맞다.",
        "Show a toast after the word is saved.",
        "단어가 저장되면 토스트를 띄워 주세요.",
    ),
    (
        "touch target", "/ˈtʌtʃ ˌtɑrɡɪt/", "손가락으로 누를 수 있는 범위",
        FRONT, N,
        "버튼이나 링크에서 손가락이 닿으면 실제로 눌리는 영역. 아이콘이 작아도 이 영역은 가로세로 44에서 48픽셀 정도로 넉넉히 잡도록 "
        "권한다. 보이는 크기를 키우지 않아도 padding 으로 누르는 범위만 넓히면 디자인을 덜 바꾸고 해결된다.",
        "The close icon's touch target is too small on phones.",
        "폰에서 닫기 아이콘의 터치 영역이 너무 작습니다.",
    ),
    (
        "truthy", "/ˈtruθi/", "조건문에서 참으로 취급되는 값",
        FRONT, N,
        "true 가 아니어도 if 문에 넣으면 참으로 통과하는 값. false, 0, 빈 문자열, null, undefined, NaN "
        "같은 몇 가지만 거짓 쪽인 falsy 이고 나머지는 전부 여기에 든다. React 에서 개수 && 목록으로 쓰면 0 은 falsy "
        "라 목록 대신 0 이 화면에 찍히는 실수가 흔하다.",
        "An empty array is truthy, so this check always passes.",
        "빈 배열은 truthy 라서 이 검사는 항상 통과합니다.",
    ),
    (
        "undefined", "/ˌʌndɪˈfaɪnd/", "값이 아직 정해지지 않았다는 자바스크립트 값",
        FRONT, E,
        "변수를 만들고 값을 안 넣었거나 객체에 없는 속성을 읽을 때 나오는 값. 일부러 비워 둔다는 뜻의 null 과 구분한다. "
        "Cannot read properties of undefined 는 API 응답이 오기 전에 그 안을 읽으려 할 때 자주 나는 "
        "에러다.",
        "The user is undefined until the profile request finishes.",
        "프로필 요청이 끝나기 전까지 user 는 undefined 입니다.",
    ),
    (
        "vanilla JS", "/vəˌnɪlə ˌdʒeɪ ˈes/", "라이브러리 없이 쓰는 순수 자바스크립트",
        FRONT, E,
        "React 같은 프레임워크나 라이브러리를 쓰지 않고 브라우저가 기본으로 주는 기능만으로 짠 자바스크립트. 아무것도 안 얹은 바닐라 "
        "아이스크림에서 온 말이다. 낮춰 부르는 말이 아니고, 작은 기능은 이쪽이 더 가볍고 빠르다.",
        "This widget is small enough to write in vanilla JS.",
        "이 위젯은 바닐라 JS 로 짜도 될 만큼 작습니다.",
    ),
    (
        "virtual scrolling", "/ˈvɜrtʃuəl ˌskroʊlɪŋ/", "화면에 보이는 줄만 그려 긴 목록을 가볍게 하기",
        FRONT, H,
        "수천 줄짜리 목록에서 지금 보이는 몇십 줄만 실제로 그리고, 스크롤하면 그 자리에 다른 내용을 바꿔 끼우는 방식. 한꺼번에 다 "
        "그리면 메모리와 렌더링이 버거워 스크롤이 끊긴다. 대신 안 그려진 줄은 브라우저의 찾기 기능으로 못 찾는다.",
        "Use virtual scrolling for the 5,000-word list.",
        "5천 개짜리 단어 목록에는 가상 스크롤을 쓰세요.",
    ),
    (
        "web worker", "/ˈweb ˌwɜrkər/", "무거운 계산을 화면과 따로 돌리는 백그라운드 스크립트",
        FRONT, H,
        "메인 스레드와 따로 도는 자바스크립트 실행 환경. 큰 파일 처리나 복잡한 계산을 맡기면 그동안 화면이 멈추지 않는다. DOM 에 "
        "손댈 수 없고 메인 쪽과는 메시지로만 주고받는다. 오프라인과 캐시를 맡는 service worker 와는 목적이 다르다.",
        "Move the image resizing into a web worker.",
        "이미지 크기 조절은 웹 워커로 옮기세요.",
    ),
    (
        "wireframe", "/ˈwaɪərˌfreɪm/", "선과 상자로만 그린 화면 뼈대",
        FRONT, N,
        "색이나 그림 없이 어디에 무엇이 놓이는지만 선과 상자로 그린 초기 화면 설계도. 구조를 빨리 합의하려고 만든다. 정보처리기사 UI "
        "설계에서 목업, 스토리보드, 프로토타입과 함께 나오며, 그중 가장 단순하고 손이 덜 가는 단계다.",
        "Let's agree on the wireframe before anyone writes CSS.",
        "누가 CSS 를 쓰기 전에 와이어프레임부터 합의합시다.",
    ),
    # ---------- CS 기초 ----------
    (
        "algorithm", "/ˈælɡəˌrɪðəm/", "문제를 푸는 순서를 정해 둔 절차",
        CS, E,
        "어떤 입력을 받아 원하는 결과를 내기까지의 단계를 순서대로 정한 것. 같은 문제도 푸는 방법에 따라 속도가 크게 달라서, 코딩 "
        "테스트와 정처기 모두 얼마나 빨리 끝나는지를 함께 묻는다. 거창한 것만 가리키는 말이 아니라 정렬 한 줄도 알고리즘이다.",
        "This algorithm gets too slow once the list passes ten thousand items.",
        "이 알고리즘은 목록이 만 개를 넘으면 너무 느려집니다.",
    ),
    (
        "asynchronous", "/eɪˈsɪŋkrənəs/", "끝날 때까지 기다리지 않고 다음 일을 하는 방식",
        CS, N,
        "오래 걸리는 작업을 맡겨 두고 결과를 기다리지 않은 채 다음 코드를 먼저 실행하는 방식. 네트워크 요청이나 파일 읽기처럼 기다리는 "
        "시간이 긴 일에 쓴다. 코드에 적힌 순서와 실제로 끝나는 순서가 달라서, 결과를 쓰기 전에 끝났는지 확인해야 한다.",
        "The email is sent in an asynchronous task so the page loads fast.",
        "페이지가 빨리 뜨도록 이메일은 비동기 작업으로 보냅니다.",
    ),
    (
        "bubble sort", "/ˈbʌbəl ˌsɔrt/", "이웃한 둘을 비교해 바꾸기를 되풀이하는 정렬",
        CS, N,
        "옆에 있는 두 값을 비교해 순서가 틀리면 바꾸는 일을 끝까지 되풀이하는 정렬. 한 바퀴 돌 때마다 가장 큰 값이 맨 뒤로 "
        "밀려난다. 이해하기 쉬운 대신 느려서 실무에서는 쓰지 않고, 정처기에서는 몇 번째 바퀴의 결과를 묻는다.",
        "Nobody uses bubble sort in production, but it shows up in interviews.",
        "실서비스에서 버블 정렬을 쓰는 사람은 없지만 면접에는 나옵니다.",
    ),
    (
        "callback", "/ˈkɔlˌbæk/", "나중에 불러 달라고 넘겨 두는 함수",
        CS, N,
        "다른 함수에 인자로 넘겨서, 일이 끝나거나 어떤 일이 생겼을 때 대신 불러 달라고 맡기는 함수. 이벤트 처리와 비동기 작업에서 "
        "흔히 쓴다. 콜백 안에 콜백이 겹겹이 들어가면 읽기 어려워져서 요즘은 promise 나 async 로 바꿔 쓴다.",
        "Pass a callback that runs after the upload finishes.",
        "업로드가 끝나면 실행될 콜백을 넘기세요.",
    ),
    (
        "class", "/klæs/", "객체를 찍어 내는 설계도",
        CS, E,
        "어떤 데이터와 동작을 가진 객체를 만들지 정해 둔 틀. 클래스 하나로 객체를 여러 개 만들 수 있고, 그렇게 만든 하나하나를 "
        "인스턴스라고 부른다. HTML 태그에 붙이는 class 속성과는 철자만 같고 다른 말이다.",
        "Move the parsing logic into a separate class.",
        "파싱 로직은 별도 클래스로 옮기세요.",
    ),
    (
        "closure", "/ˈkloʊʒər/", "만들어질 때의 바깥 변수를 기억하는 함수",
        CS, H,
        "함수 안에서 만든 함수가 바깥 함수의 변수를 계속 붙잡고 있는 것. 바깥 함수가 끝난 뒤에도 그 변수를 쓸 수 있다. 반복문 "
        "안에서 만든 클로저들이 모두 마지막 값만 보는 버그가 흔해서, 리뷰에서 자주 짚는 자리다.",
        "The closure captures the loop variable, so every handler sees the last value.",
        "클로저가 반복문 변수를 붙잡아서 모든 핸들러가 마지막 값을 봅니다.",
    ),
    (
        "critical section", "/ˌkrɪtɪkəl ˈsekʃən/", "여러 스레드가 함께 쓰는 데이터를 건드리는 코드 부분",
        CS, H,
        "여러 스레드가 함께 쓰는 데이터를 건드리는 코드 부분. 둘이 동시에 들어가면 값이 꼬이므로 락이나 세마포어로 한 번에 하나만 "
        "들어가게 막는다. 이 구역을 짧게 잡을수록 다른 스레드가 기다리는 시간이 줄어 전체가 빨라진다.",
        "Keep the critical section small; don't call the API while holding the lock.",
        "임계 구역은 짧게 잡으세요. 락을 쥔 채로 API 를 부르지 마세요.",
    ),
    (
        "data structure", "/ˈdeɪtə ˌstrʌktʃər/", "데이터를 담고 꺼내는 방식을 정한 틀",
        CS, E,
        "배열·리스트·스택·트리처럼 데이터를 어떤 모양으로 저장할지 정한 것. 무엇을 고르느냐에 따라 찾기는 빠른데 넣기는 느린 식으로 "
        "장단점이 갈린다. 알고리즘과 짝으로 다니며, 정처기에서는 선형 구조와 비선형 구조로 나눠 묻는다.",
        "Picking the right data structure made this lookup a hundred times faster.",
        "자료구조를 제대로 고르니 이 조회가 백 배 빨라졌습니다.",
    ),
    (
        "DDoS", "/ˈdiˌdɑs/", "여러 곳에서 한꺼번에 요청을 퍼부어 서비스를 마비시키는 공격",
        CS, N,
        "수많은 컴퓨터를 동원해 한 서버에 요청을 쏟아부어 정상 사용자가 접속하지 못하게 만드는 공격. 한 곳에서 보내면 막기 쉬워서 "
        "감염된 기기 여러 대를 쓴다. 갑자기 트래픽이 몰렸다고 다 공격은 아니어서, 이벤트로 사람이 몰린 것과 구분해야 한다.",
        "The traffic spike looked like a DDoS, but it was our marketing email.",
        "트래픽이 치솟아 디도스인 줄 알았는데 우리 마케팅 메일 때문이었습니다.",
    ),
    (
        "digital signature", "/ˌdɪdʒɪtəl ˈsɪɡnətʃər/", "누가 보냈고 바뀌지 않았음을 증명하는 서명",
        CS, H,
        "보낸 사람이 자기 개인키로 서명하고 받는 사람이 공개키로 확인해서, 보낸 사람이 맞는지와 내용이 바뀌지 않았는지를 따지는 방법. "
        "내용을 숨기는 암호화와는 목적이 다르다. 설치 파일과 인증서가 이걸로 진짜임을 증명한다.",
        "The installer failed because its digital signature could not be verified.",
        "설치 파일의 전자 서명을 확인할 수 없어 설치가 실패했습니다.",
    ),
    (
        "divide and conquer", "/dɪˌvaɪd ən ˈkɑŋkər/", "문제를 작게 쪼개 풀고 답을 합치는 방법",
        CS, N,
        "큰 문제를 같은 모양의 작은 문제로 나눠 각각 풀고, 그 답을 합쳐 전체 답을 만드는 설계 방법. 퀵 정렬과 합병 정렬, 이진 "
        "탐색이 이 방식이다. 쪼갠 문제들이 서로 겹쳐 같은 계산을 되풀이하게 되면 동적 계획법이 더 맞다.",
        "Merge sort is a classic divide and conquer algorithm.",
        "합병 정렬은 대표적인 분할 정복 알고리즘입니다.",
    ),
    (
        "fragmentation", "/ˌfræɡmənˈteɪʃən/", "빈 메모리가 잘게 흩어져 쓰기 어려운 상태",
        CS, H,
        "남은 메모리를 다 합치면 충분한데 조각조각 흩어져 있어 큰 덩어리를 못 잡는 상태. 할당한 칸 안에 남는 낭비는 내부 단편화, 칸 "
        "사이의 빈틈은 외부 단편화라고 해서 정처기에서 둘을 구분해 묻는다. 디스크와 DB 인덱스에서도 같은 말을 쓴다.",
        "Memory fragmentation keeps the process growing even though usage is flat.",
        "메모리 단편화 때문에 사용량은 그대로인데 프로세스 크기가 계속 커집니다.",
    ),
    (
        "function", "/ˈfʌŋkʃən/", "입력을 받아 일을 하고 결과를 돌려주는 코드 묶음",
        CS, E,
        "자주 쓰는 동작을 한 덩어리로 묶어 이름을 붙인 것. 같은 코드를 여러 곳에 복사하는 대신 함수를 불러 쓴다. 클래스 안에 들어 "
        "있으면 보통 메서드라고 부르는데, 하는 일은 같다. 한 함수가 여러 일을 하면 나누라는 리뷰를 받는다.",
        "This function does three things; please split it up.",
        "이 함수가 세 가지 일을 하네요. 나눠 주세요.",
    ),
    (
        "graph", "/ɡræf/", "점과 그 사이를 잇는 선으로 관계를 나타낸 구조",
        CS, N,
        "정점과 간선으로 무엇이 무엇과 이어져 있는지를 나타내는 비선형 자료구조. 지도 길찾기, SNS 친구 관계, 패키지 사이의 의존성이 "
        "모두 그래프로 표현된다. 차트를 뜻하는 그래프와 철자가 같아서 문맥을 보고 구분해야 한다.",
        "Model the service dependencies as a graph and check for cycles.",
        "서비스 의존 관계를 그래프로 만들고 순환이 있는지 확인하세요.",
    ),
    (
        "hash collision", "/ˈhæʃ kəˌlɪʒən/", "서로 다른 입력이 같은 해시 값을 갖는 일",
        CS, H,
        "해시 함수가 서로 다른 두 입력에 같은 값을 내는 것. 나올 수 있는 값의 수가 정해져 있어 완전히 피할 수는 없고, 해시 "
        "테이블은 같은 칸에 줄줄이 달거나 다른 빈칸을 찾아 처리한다. 정처기에서는 그 해결 방법으로 체이닝과 개방 주소법을 묻는다.",
        "Two keys landed in the same bucket because of a hash collision.",
        "해시 충돌 때문에 두 키가 같은 버킷에 들어갔습니다.",
    ),
    (
        "heap", "/hip/", "가장 작거나 큰 값이 늘 맨 위에 오는 트리",
        CS, N,
        "부모가 자식보다 늘 작거나 크도록 유지해서 최솟값이나 최댓값을 바로 꺼낼 수 있는 트리 구조. 우선순위 큐를 만들 때 쓰고 "
        "정처기에서는 힙 정렬로 나온다. 'heap out of memory' 의 힙은 이름만 같은 메모리 영역이다.",
        "Use a heap to always pop the job with the earliest deadline.",
        "마감이 가장 이른 작업을 늘 먼저 꺼내려면 힙을 쓰세요.",
    ),
    (
        "instance", "/ˈɪnstəns/", "클래스로 실제로 만들어 낸 객체 하나",
        CS, N,
        "설계도인 클래스로 만들어 낸 실물 하나하나. 같은 클래스에서 나왔어도 인스턴스마다 자기 값을 따로 가져서, 하나를 고쳐도 다른 "
        "것은 그대로다. 클라우드에서 서버 한 대를 인스턴스라고 부르는 것도 같은 틀에서 찍어 낸 하나라는 뜻에서 왔다.",
        "Each request creates a new instance of the handler.",
        "요청마다 핸들러 인스턴스가 새로 만들어집니다.",
    ),
    (
        "interface", "/ˈɪntərˌfeɪs/", "서로 맞물리는 부분이 지키기로 한 모양",
        CS, N,
        "두 부분이 서로를 어떻게 부르고 무엇을 주고받을지 정해 둔 경계. 코드에서는 구현 없이 메서드 목록만 정한 타입을 말하고, 시스템 "
        "사이에서는 데이터를 주고받는 방식을 말한다. 정처기 1과목에는 시스템 간 인터페이스 설계가 따로 나온다.",
        "Both payment providers implement the same interface.",
        "두 결제사 모듈이 같은 인터페이스를 구현합니다.",
    ),
    (
        "interrupt", "/ˈɪntəˌrʌpt/", "하던 일을 멈추고 급한 일부터 처리하라는 신호",
        CS, N,
        "키보드 입력이나 타이머처럼 급한 일이 생겼을 때 CPU 에게 지금 하던 일을 잠깐 멈추라고 알리는 신호. CPU 는 그 일을 "
        "처리한 뒤 하던 곳으로 돌아온다. 터미널에서 Ctrl+C 를 누르면 파이썬이 내는 키보드 인터럽트 에러도 같은 말에서 왔다.",
        "The script stopped because it received an interrupt signal.",
        "인터럽트 신호를 받아서 스크립트가 멈췄습니다.",
    ),
    (
        "method", "/ˈmeθəd/", "클래스 안에 들어 있는 함수",
        CS, E,
        "객체가 할 수 있는 동작을 클래스 안에 정의한 함수. 함수와 하는 일은 같지만 객체에 붙어 있어서 그 객체가 가진 데이터를 바로 "
        "꺼내 쓸 수 있다. HTTP 의 GET·POST 도 메서드라고 부르니 문맥으로 구분한다.",
        "Make this method private; nothing outside the class calls it.",
        "이 메서드는 private 으로 바꾸세요. 클래스 밖에서 부르는 곳이 없습니다.",
    ),
    (
        "overloading", "/ˌoʊvərˈloʊdɪŋ/", "같은 이름의 함수를 입력만 다르게 여러 개 두기",
        CS, N,
        "이름은 같고 매개변수의 개수나 타입만 다른 메서드를 여러 개 정의하는 것. 부르는 쪽이 넘긴 값의 개수와 타입을 보고 맞는 것이 "
        "골라지며, 파이썬처럼 지원하지 않는 언어도 있다. 부모의 메서드를 덮어쓰는 오버라이딩과 헷갈리기 쉬워 정처기에 단골로 나온다.",
        "Python has no method overloading, so use default arguments instead.",
        "파이썬에는 메서드 오버로딩이 없으니 기본 인자를 쓰세요.",
    ),
    (
        "overriding", "/ˌoʊvərˈraɪdɪŋ/", "부모 클래스의 메서드를 자식이 다시 정의하기",
        CS, N,
        "상속받은 메서드를 자식 클래스에서 같은 이름과 형태로 새로 정의해 동작을 바꾸는 것. 이름이 같아도 입력이 다르면 오버로딩이다. "
        "이름을 잘못 쓰면 에러 없이 새 메서드가 하나 더 생길 뿐이라, Java 에서는 @Override 를 붙여 실수를 잡는다.",
        "Overriding save here skips the validation in the parent class.",
        "여기서 save 를 오버라이딩하면 부모 클래스의 검증을 건너뛰게 됩니다.",
    ),
    (
        "packet", "/ˈpækɪt/", "네트워크로 보내려고 잘게 나눈 데이터 조각",
        CS, E,
        "보낼 데이터를 일정한 크기로 쪼개고 주소 같은 정보를 붙인 단위. 조각마다 다른 길로 가서 도착 순서가 뒤섞이기도 해서 받는 쪽이 "
        "다시 맞춘다. 일부가 중간에 사라지는 것을 패킷 손실이라 하며, 네트워크가 불안정할 때 자주 본다.",
        "We saw packet loss between the app server and the database.",
        "앱 서버와 데이터베이스 사이에서 패킷 손실이 보였습니다.",
    ),
    (
        "page fault", "/ˈpeɪdʒ ˌfɔlt/", "필요한 페이지가 메모리에 없어 디스크에서 가져오는 일",
        CS, N,
        "프로그램이 찾는 메모리 페이지가 실제 메모리에 없어 디스크에서 읽어 와야 하는 상황. 에러가 아니라 가상 메모리의 정상 동작이지만 "
        "너무 잦으면 크게 느려진다. 정처기에서는 교체 기법별로 페이지 부재가 몇 번 나는지 세는 문제로 나온다.",
        "The page fault rate spiked once the server started swapping.",
        "서버가 스왑을 쓰기 시작하자 페이지 폴트 비율이 치솟았습니다.",
    ),
    (
        "parameter", "/pəˈræmɪtər/", "함수가 받기로 정해 둔 입력 이름",
        CS, E,
        "함수를 정의할 때 괄호 안에 적어 두는 이름. 함수를 부를 때 실제로 넘기는 값은 인자라고 해서 구분하지만, 현업에서는 둘을 섞어 "
        "쓰는 경우가 많다. 개수가 너무 많아지면 객체 하나로 묶어서 넘기라는 리뷰를 자주 받는다.",
        "Add a timeout parameter with a default of five seconds.",
        "기본값이 5초인 timeout 매개변수를 추가하세요.",
    ),
    (
        "PCB", "/ˌpi si ˈbi/", "운영체제가 프로세스마다 정보를 적어 두는 표",
        CS, H,
        "Process Control Block 의 줄임말. 프로세스의 상태, 다음에 실행할 위치, 쓰고 있는 자원 같은 정보를 담아 "
        "두고, 문맥 교환 때 여기에 저장했다가 다시 꺼내 이어서 실행한다. 정처기에서는 PCB 에 들어가는 항목을 고르는 문제로 나온다.",
        "On a context switch, the kernel saves the registers into the PCB.",
        "문맥 교환 때 커널은 레지스터 값을 PCB 에 저장합니다.",
    ),
    (
        "preemptive", "/priˈemptɪv/", "실행 중인 작업에서 CPU 를 빼앗아 올 수 있는",
        CS, H,
        "운영체제가 실행 중인 작업을 강제로 멈추고 다른 작업에 CPU 를 넘길 수 있는 방식을 말한다. 급한 작업에 빨리 응답할 수 있는 "
        "대신 전환 비용이 든다. 정처기에서는 라운드 로빈 같은 선점형과 FCFS 같은 비선점형을 나눠 묻는다.",
        "Linux uses preemptive scheduling, so one busy loop cannot freeze the system.",
        "리눅스는 선점형 스케줄링을 써서 바쁜 루프 하나가 시스템을 멈추지 못합니다.",
    ),
    (
        "protocol", "/ˈproʊtəˌkɔl/", "통신할 때 서로 지키기로 한 약속",
        CS, E,
        "두 컴퓨터가 데이터를 주고받을 때 형식과 순서를 미리 맞춰 둔 규칙. HTTP·TCP·SMTP 가 모두 프로토콜이다. 한쪽만 "
        "버전을 올리면 서로 말이 안 통한다. 정처기에서는 프로토콜의 세 요소인 구문·의미·타이밍을 묻는다.",
        "The client and server disagree on the protocol version.",
        "클라이언트와 서버의 프로토콜 버전이 맞지 않습니다.",
    ),
    (
        "quicksort", "/ˈkwɪkˌsɔrt/", "기준값보다 작은 쪽과 큰 쪽으로 나눠 가며 정렬하기",
        CS, N,
        "기준값 하나를 골라 그보다 작은 값은 왼쪽, 큰 값은 오른쪽으로 보낸 뒤 양쪽을 같은 방법으로 정렬한다. 평균적으로 빨라 많이 "
        "쓰지만 기준값을 계속 나쁘게 고르면 크게 느려진다. 정처기에서는 평균과 최악의 시간 복잡도를 묻는다.",
        "The library uses quicksort, so equal items may change order.",
        "라이브러리가 퀵소트를 써서 값이 같은 항목은 순서가 바뀔 수 있습니다.",
    ),
    (
        "round robin", "/ˌraʊnd ˈrɑbɪn/", "돌아가며 정해진 시간만큼씩 차례를 주는 방식",
        CS, N,
        "여러 작업에 같은 길이의 시간을 차례로 나눠 주고, 시간이 다 되면 다음 작업으로 넘기는 방식. 정처기에서는 CPU 스케줄링 "
        "기법으로 나오고, 실무에서는 로드 밸런서가 서버마다 요청을 돌아가며 보내는 방식으로 마주친다.",
        "The load balancer uses round robin to spread requests across servers.",
        "로드 밸런서는 라운드 로빈으로 요청을 서버들에 고르게 나눕니다.",
    ),
    (
        "router", "/ˈraʊtər/", "패킷이 갈 길을 골라 다른 네트워크로 넘기는 장비",
        CS, N,
        "네트워크와 네트워크 사이에서 목적지를 보고 패킷을 어느 쪽으로 보낼지 정하는 장비. 집에서 쓰는 공유기도 라우터의 한 종류다. 웹 "
        "프레임워크에서 말하는 라우터는 주소에 맞는 화면이나 함수를 고르는 코드라서 뜻이 다르다.",
        "Packets are dropped at the router between the two subnets.",
        "두 서브넷 사이의 라우터에서 패킷이 버려지고 있습니다.",
    ),
    (
        "shell", "/ʃel/", "입력한 명령을 해석해 운영체제에 넘기는 프로그램",
        CS, E,
        "터미널에 명령을 치면 그걸 해석해 운영체제에 넘겨주는 프로그램. bash·zsh·파워셸이 모두 셸이고, 설정 파일도 셸마다 따로 "
        "있다. 터미널은 창이고 셸은 그 안에서 명령을 해석하는 쪽이라, 둘은 같은 것이 아니다.",
        "Restart your shell so the new PATH takes effect.",
        "새 PATH 가 적용되게 셸을 다시 시작하세요.",
    ),
    (
        "spoofing", "/ˈspufɪŋ/", "남인 척 주소나 정보를 꾸며 속이는 공격",
        CS, H,
        "보내는 쪽의 IP 주소, 이메일 주소, MAC 주소 같은 것을 남의 것으로 꾸며 상대를 속이는 공격. 믿을 만한 곳에서 온 것처럼 "
        "보이게 해서 접근을 얻거나 정보를 빼낸다. 정처기에서는 IP·ARP·DNS 스푸핑을 나눠 묻는다.",
        "SPF and DKIM records protect our domain from email spoofing.",
        "SPF 와 DKIM 레코드가 우리 도메인을 이메일 스푸핑으로부터 막아 줍니다.",
    ),
    (
        "starvation", "/stɑrˈveɪʃən/", "순서가 계속 밀려 끝내 실행되지 못하는 상태",
        CS, H,
        "우선순위가 낮은 작업이 계속 뒤로 밀려 자원을 영영 받지 못하는 상태. 짧은 작업부터 처리하는 방식에서 긴 작업이 이렇게 되기 "
        "쉽다. 정처기에서는 기다린 시간만큼 우선순위를 올려 주는 에이징이 해결책으로 함께 나온다.",
        "Low-priority jobs suffer starvation when the queue never empties.",
        "큐가 비지 않으면 우선순위가 낮은 작업은 기아 상태에 빠집니다.",
    ),
    (
        "symmetric key", "/sɪˌmetrɪk ˈki/", "잠그고 여는 키가 같은 암호 방식을 통틀어 부르는 말",
        CS, H,
        "암호화와 복호화에 같은 키 하나를 쓰는 방식으로 AES 가 대표적이다. 빠르지만 그 키를 상대에게 안전하게 건네기가 어려워서, "
        "HTTPS 는 공개키 방식으로 대칭키를 안전하게 정한 뒤 실제 데이터는 대칭키로 암호화한다.",
        "AES uses a symmetric key, so both sides must share it securely.",
        "AES 는 대칭키를 쓰므로 양쪽이 그 키를 안전하게 나눠 가져야 합니다.",
    ),
    (
        "thrashing", "/ˈθræʃɪŋ/", "페이지 교체만 하느라 정작 일을 못 하는 상태",
        CS, H,
        "메모리가 모자라 페이지를 디스크와 계속 주고받느라 CPU 가 실제 작업은 거의 못 하는 상태. 프로그램을 더 띄울수록 일은 줄고 "
        "디스크만 바빠져 오히려 느려진다. 정처기에서는 워킹 셋과 페이지 부재 빈도가 해결책으로 함께 나온다.",
        "The node was thrashing, so even ssh took a minute to respond.",
        "그 노드가 스래싱 상태라 ssh 응답에도 1분이 걸렸습니다.",
    ),
    (
        "traversal", "/trəˈvɜrsəl/", "트리나 그래프의 모든 칸을 한 번씩 방문하기",
        CS, N,
        "자료구조의 모든 노드를 정해진 순서로 한 번씩 거치는 것. 트리에서는 루트를 언제 방문하느냐에 따라 전위·중위·후위로 나뉘고, "
        "정처기에서 방문 순서를 직접 적어 보는 문제로 자주 나온다. 그래프에서는 BFS 와 DFS 가 대표적이다.",
        "The traversal visits each node once, so it runs in linear time.",
        "순회가 노드를 한 번씩만 방문하니 선형 시간에 끝납니다.",
    ),
    (
        "variable", "/ˈvɛriəbəl/", "값을 담아 두고 이름으로 부르는 칸",
        CS, E,
        "값에 이름을 붙여 저장해 두고 나중에 그 이름으로 꺼내 쓰는 것. 이름만 보고 무엇이 들었는지 알 수 있게 짓는 것이 리뷰에서 "
        "가장 자주 받는 지적 중 하나다. 정처기에서는 변수 이름을 짓는 규칙과 자료형이 함께 나온다.",
        "Rename this variable to something clearer than tmp.",
        "이 변수 이름을 tmp 보다 알아보기 쉬운 걸로 바꿔 주세요.",
    ),
]


class Command(SeedWordsMoreCommand):
    help = "출시 전 보강 단어를 넣습니다(seed_words_more 의 뒤를 잇는 묶음)."
    words = WORDS
    source = "AI 생성(에이전트 검수)"
