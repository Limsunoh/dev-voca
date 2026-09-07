"""단어를 더 넣는다. seed_words 의 뒤를 잇는 묶음.

사용:
    python manage.py seed_words_more --dry-run
    python manage.py seed_words_more

**파일을 나눈 이유**: seed_words.py 가 이미 4,000줄이 넘는다. 한 파일에 계속
쌓으면 어느 묶음을 언제 넣었는지가 diff 로만 남는다. 여기는 "무엇이 모자라서
넣었나" 를 위에 적어둔다.

**무엇이 모자랐나** (2026-09-08 실측, 단어 581개 기준)

    debug 58 · git 60 · frontend 68 — 가장 적은 셋
    cs 107 — 가장 많음

거기에 더해 **콘텐츠 소진 속도**가 문제였다. 946개(단어 566 + 문장 380)면
하루 10판(90초 x 12문제)에 8일, 30분 일일공부로 24일이면 전부 본다. 복습이
틀린 것을 다시 내주긴 하지만 새 것이 안 나오면 지루해진다.

관측·성능 쪽 용어를 특히 늘렸다. 주니어가 장애를 처음 겪을 때 로그와
대시보드에서 마주치는데, 학습 자료에는 잘 안 나오는 말들이다.

규칙은 seed_words 와 같다. 발음기호는 미국식 IPA, 두 단어 구는 주강세 하나.
tests.py 의 ALL_SEEDED 가 이 리스트도 전수 검사한다 - 거기에 이 파일을
등록하지 않으면 검사를 통째로 건너뛴다.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.vocab.models import Word

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
#  example, example_translation)
#
# seed_words 와 열 순서를 맞췄다. tests.py 의 ALL_SEEDED 가 이름을 붙여
# 정규화하지만, 순서까지 같으면 그쪽에 한 덩이를 더할 때 헷갈리지 않는다.
WORDS: list[tuple[str, str, str, str, int, str, str, str]] = [
    # ---------- 디버깅 (58개로 가장 적었다) ----------
    (
        "profiler", "/ˈproʊfaɪlər/", "어디서 시간을 쓰는지 재는 도구",
        DEBUG, N,
        "코드의 어느 부분이 얼마나 오래 걸리는지 측정해 보여주는 도구. 느리다고 "
        "느낀 곳과 실제로 느린 곳이 다른 경우가 많아, 추측으로 고치기 전에 먼저 "
        "돌린다. 재는 동안 자체 비용이 들어 결과가 조금 왜곡되는 것은 감안한다.",
        "The profiler shows most of the time is spent in serialization.",
        "프로파일러를 보면 대부분의 시간을 직렬화에 쓰고 있습니다.",
    ),
    (
        "flame graph", "/ˈfleɪm ˌɡræf/", "호출 깊이를 층으로 쌓아 보여주는 그림",
        DEBUG, H,
        "어떤 함수가 어떤 함수를 불렀는지를 가로 너비로 시간을 나타내며 층층이 "
        "그린 그래프. 넓은 칸이 오래 걸린 곳이다. 숫자 목록보다 어디를 파야 할지 "
        "한눈에 보여서 성능 문제에 자주 쓴다.",
        "The flame graph shows a wide block under the template rendering.",
        "플레임 그래프에서 템플릿 렌더링 아래에 넓은 칸이 보입니다.",
    ),
    (
        "heap dump", "/ˈhip ˌdʌmp/", "그 순간 메모리에 뭐가 있었는지 통째로 뜬 것",
        DEBUG, H,
        "프로그램이 쓰던 메모리 내용을 파일로 떠낸 것. 메모리가 새는 원인을 찾을 때 "
        "무엇이 안 지워지고 쌓였는지 본다. 파일이 수 기가가 되기도 하고 그 안에 "
        "실제 사용자 데이터가 들어 있으므로 다루는 데 주의한다.",
        "Take a heap dump before the process gets killed.",
        "프로세스가 종료되기 전에 힙 덤프를 뜨세요.",
    ),
    (
        "watchpoint", "/ˈwɑtʃˌpɔɪnt/", "값이 바뀌는 순간 멈추게 하기",
        DEBUG, N,
        "특정 줄에서 멈추는 브레이크포인트와 달리, 어떤 변수의 값이 바뀔 때 멈춘다. "
        "'어디선가 이 값이 바뀌는데 어딘지 모르겠다' 는 상황에 쓴다. 그 값을 쓰는 "
        "곳이 많을수록 손으로 찾기 어려워서 이쪽이 빠르다.",
        "Set a watchpoint on that field to see who mutates it.",
        "누가 그 필드를 바꾸는지 보려면 워치포인트를 거세요.",
    ),
    (
        "correlation id", "/ˌkɔrəˈleɪʃən ˌaɪdi/", "요청 하나에 붙여 끝까지 따라가는 번호",
        DEBUG, N,
        "요청이 여러 서비스를 거칠 때 같은 번호를 달아두면, 흩어진 로그에서 그 "
        "요청만 모아 볼 수 있다. 없으면 시각으로 어림잡아 찾게 되는데 트래픽이 "
        "많으면 사실상 불가능하다.",
        "Search the logs by correlation id to trace this request.",
        "이 요청을 추적하려면 correlation id 로 로그를 검색하세요.",
    ),
    (
        "structured logging", "/ˈstrʌktʃərd ˌlɔɡɪŋ/", "기계가 읽게 항목을 나눠 남기기",
        DEBUG, N,
        "문장 한 줄로 남기는 대신 키와 값으로 나눠 남기는 방식. 나중에 조건을 걸어 "
        "찾을 수 있다. '사용자 12번이 3초 걸렸다' 를 문장으로 적으면 검색이 안 되고, "
        "user_id 와 duration 으로 나누면 '3초 넘은 것' 만 골라낼 수 있다.",
        "Switch to structured logging so we can query by user id.",
        "사용자 id 로 조회할 수 있게 구조화 로깅으로 바꿉시다.",
    ),
    (
        "log level", "/ˈlɔɡ ˌlevəl/", "이 로그가 얼마나 중요한지 등급",
        DEBUG, E,
        "debug·info·warning·error 처럼 심각도를 나눠 붙인다. 운영에서는 대개 info "
        "이상만 남겨 양을 줄인다. 전부 error 로 남기면 진짜 문제가 그 사이에 묻히고, "
        "전부 debug 면 디스크가 찬다.",
        "Drop this to debug level; it fires on every request.",
        "이건 debug 레벨로 내리세요. 요청마다 찍힙니다.",
    ),
    (
        "sampling", "/ˈsæmpəlɪŋ/", "전부가 아니라 일부만 골라 보기",
        DEBUG, N,
        "요청을 전부 기록하면 비용과 부하가 커서, 정해진 비율만 남기는 방식. 1% 만 "
        "봐도 전체 경향은 보인다. 대신 드물게 나는 문제는 표본에 안 잡힐 수 있어, "
        "에러는 비율과 무관하게 전부 남기는 설정을 함께 쓴다.",
        "We only trace 1% of requests due to sampling.",
        "샘플링 때문에 요청의 1% 만 추적합니다.",
    ),

    # ---------- 관측·성능 (장애 때 마주치는 말들) ----------
    (
        "tail latency", "/ˈteɪl ˌleɪtnsi/", "느린 쪽 소수가 겪는 지연",
        OPS, H,
        "평균은 멀쩡한데 일부 요청만 아주 느린 경우를 가리킨다. 평균 200ms 여도 "
        "상위 1% 가 5초면 그 사람들은 서비스가 고장 난 것으로 느낀다. 그래서 평균 "
        "대신 p99 같은 값을 본다.",
        "The average looks fine but the tail latency is terrible.",
        "평균은 괜찮아 보이는데 꼬리 지연이 형편없습니다.",
    ),
    (
        "p99", "/ˌpi ˌnaɪnti ˈnaɪn/", "빠른 쪽에서 99% 지점의 응답 시간",
        OPS, N,
        "요청을 빠른 순서로 늘어놓았을 때 99% 지점의 값. '100명 중 99명은 이 시간 "
        "안에 받았다' 는 뜻이다. 평균은 아주 느린 몇 건에 가려지지만 이 값은 안 "
        "가려져서, 실제 체감을 보려면 이쪽을 본다.",
        "Our p99 latency jumped from 300ms to 2s after the deploy.",
        "배포 후 p99 지연이 300ms 에서 2초로 뛰었습니다.",
    ),
    (
        "saturation", "/ˌsætʃəˈreɪʃən/", "여유가 얼마나 남았는지",
        OPS, H,
        "CPU·메모리·연결처럼 한계가 있는 자원이 얼마나 찼는지를 말한다. 100% 에 "
        "가까워지면 조금만 더 들어와도 급격히 느려진다. 에러가 아직 안 나도 이 "
        "값이 높으면 곧 난다는 신호다.",
        "Check saturation first; the CPU has been pinned at 95%.",
        "포화도부터 보세요. CPU 가 95% 에 붙어 있었습니다.",
    ),
    (
        "backpressure", "/ˈbækˌpreʃər/", "못 따라가니 천천히 보내라고 알리기",
        OPS, H,
        "받는 쪽이 처리 속도를 못 따라갈 때 보내는 쪽에 알려 속도를 줄이게 하는 것. "
        "없으면 큐가 계속 쌓이다 메모리가 터진다. 요청을 거절하는 것도 한 방법이라, "
        "느려지는 것과 거절하는 것 중 무엇이 나은지 미리 정해둔다.",
        "Add backpressure so the queue doesn't grow without bound.",
        "큐가 끝없이 자라지 않게 백프레셔를 넣으세요.",
    ),
    (
        "cold start", "/ˈkoʊld ˌstɑrt/", "처음 뜰 때만 느린 것",
        OPS, N,
        "쓰이지 않던 인스턴스가 처음 요청을 받을 때 준비 과정 때문에 느린 현상. "
        "서버리스에서 특히 두드러진다. 평소에는 안 보이다가 트래픽이 없던 새벽에 "
        "들어온 첫 사용자만 겪어서, 재현하려면 일부러 기다려야 한다.",
        "The first request after idle hits a cold start.",
        "쉬고 있다가 들어온 첫 요청은 콜드 스타트를 겪습니다.",
    ),
    (
        "blast radius", "/ˈblæst ˌreɪdiəs/", "터졌을 때 같이 망가지는 범위",
        OPS, H,
        "한 곳이 고장 났을 때 영향이 어디까지 퍼지는지를 말한다. 좁게 만들어두면 "
        "장애가 나도 일부만 멈춘다. 배포를 한 번에 전부 하지 않고 나눠 하는 것도 "
        "이 범위를 줄이려는 것이다.",
        "Deploy to one region first to limit the blast radius.",
        "영향 범위를 줄이려면 한 리전에 먼저 배포하세요.",
    ),
    (
        "error budget", "/ˈerər ˌbʌdʒɪt/", "이만큼은 실패해도 된다고 정해둔 몫",
        OPS, H,
        "목표가 99.9% 면 0.1% 는 실패해도 된다는 뜻이고, 그 0.1% 가 예산이다. "
        "남아 있으면 과감히 배포하고 다 쓰면 안정화에 집중한다. '무조건 안 죽어야 "
        "한다' 대신 숫자로 합의하는 방식이다.",
        "We've burned through the error budget this month.",
        "이번 달 에러 예산을 다 썼습니다.",
    ),
    (
        "toil", "/tɔɪl/", "반복되는데 자동화 안 된 수작업",
        OPS, N,
        "사람이 매번 손으로 해야 하지만 가치는 늘지 않는 일. 서버가 늘 때마다 비례해 "
        "늘어나는 것이 특징이다. 줄이는 것 자체가 목표로 잡히는 이유는, 두면 그 일에 "
        "시간을 다 쓰고 개선할 여력이 없어지기 때문이다.",
        "This weekly cleanup is pure toil; let's automate it.",
        "이 주간 정리 작업은 순전한 수작업입니다. 자동화합시다.",
    ),

    # ---------- Git (60개로 적었다) ----------
    (
        "sparse checkout", "/ˈspɑrs ˌtʃekaʊt/", "저장소의 일부만 받아 쓰기",
        GIT, H,
        "큰 저장소에서 필요한 디렉터리만 작업 폴더에 꺼내는 기능. 모노레포에서 내가 "
        "안 만지는 부분까지 받으면 느리고 자리를 먹는다. 히스토리는 그대로 있고 "
        "파일만 골라 꺼내는 것이라 커밋에는 영향이 없다.",
        "Use sparse checkout so you only pull the packages you need.",
        "필요한 패키지만 받도록 스파스 체크아웃을 쓰세요.",
    ),
    (
        "autosquash", "/ˈɔtoʊˌskwɑʃ/", "고칠 커밋을 표시해두고 한 번에 합치기",
        GIT, H,
        "리뷰 지적을 반영할 때 어느 커밋에 속하는지 미리 표시해두면, 나중에 리베이스가 "
        "알아서 그 자리에 합쳐준다. 손으로 순서를 바꾸는 것보다 실수가 적다. 다만 "
        "이미 올린 커밋을 고치는 것이라 남과 공유 중인 브랜치에서는 조심한다.",
        "Commit with --fixup and let autosquash place it for you.",
        "--fixup 으로 커밋하고 autosquash 가 자리를 잡게 하세요.",
    ),
    (
        "octopus merge", "/ˈɑktəpəs ˌmɜrdʒ/", "셋 이상을 한 번에 합치기",
        GIT, H,
        "브랜치 두 개가 아니라 여러 개를 한 커밋으로 합치는 것. 이름이 문어인 것은 "
        "부모가 여럿이라서다. 충돌이 나면 풀기 매우 어려워서 실무에서는 거의 안 쓰고, "
        "히스토리를 읽다 마주치면 그런 것이 있구나 정도로 알면 된다.",
        "That merge commit has four parents; it's an octopus merge.",
        "그 병합 커밋은 부모가 넷입니다. 옥토퍼스 머지예요.",
    ),
    (
        "orphan branch", "/ˈɔrfən ˌbræntʃ/", "조상이 없는 새 갈래",
        GIT, H,
        "기존 히스토리를 물려받지 않고 빈 상태에서 시작하는 브랜치. 문서 사이트나 "
        "배포 산출물처럼 코드와 이력을 섞고 싶지 않을 때 쓴다. 다른 브랜치와 공통 "
        "조상이 없어서 그냥 합치려 하면 거부당한다.",
        "The docs live on an orphan branch with no shared history.",
        "문서는 공통 히스토리가 없는 고아 브랜치에 있습니다.",
    ),
    (
        "signed commit", "/ˈsaɪnd ˌkɑmɪt/", "내가 만든 것이 맞다고 서명한 커밋",
        GIT, N,
        "커밋에 암호 서명을 붙여 작성자를 증명하는 것. 이름과 이메일은 누구나 자기 "
        "설정에 적을 수 있어서 그것만으로는 증거가 안 된다. 서명이 강제된 저장소에서는 "
        "설정을 안 해두면 푸시가 거부된다.",
        "The repo requires signed commits; set up your GPG key first.",
        "이 저장소는 서명된 커밋을 요구합니다. GPG 키부터 설정하세요.",
    ),
    (
        "rerere", "/ˌriˈrɛrə/", "전에 푼 충돌을 기억했다 다시 써먹기",
        GIT, H,
        "같은 충돌을 다시 만나면 예전에 해결한 방식을 자동으로 적용한다. 이름은 "
        "reuse recorded resolution 의 줄임이다. 긴 브랜치를 여러 번 리베이스할 때 "
        "같은 충돌을 반복해서 푸는 수고를 없애준다.",
        "Turn on rerere so you don't resolve the same conflict twice.",
        "같은 충돌을 두 번 풀지 않게 rerere 를 켜세요.",
    ),

    # ---------- 프론트엔드 (68개) ----------
    (
        "prefetch", "/ˈpriˌfetʃ/", "곧 쓸 것 같아서 미리 받아두기",
        FRONT, N,
        "사용자가 아직 누르지 않았지만 누를 것 같은 페이지의 자원을 미리 받아둔다. "
        "실제로 누르면 이미 와 있어서 즉시 열린다. 안 누르면 받은 것이 낭비되므로 "
        "무엇을 미리 받을지 고르는 것이 중요하다.",
        "Next.js prefetches links that scroll into view.",
        "Next.js 는 화면에 들어온 링크를 미리 받아둡니다.",
    ),
    (
        "preload", "/ˈpriˌloʊd/", "지금 화면에 꼭 필요한 것을 먼저 받게 하기",
        FRONT, N,
        "브라우저가 나중에 발견할 자원을 미리 알려줘 일찍 받게 하는 것. 글꼴이 "
        "대표적이다 - CSS 를 다 읽어야 필요한 줄 알게 되는데, 그때는 이미 늦어 글자가 "
        "한 번 바뀌어 보인다. prefetch 와 달리 지금 화면에 쓰는 것이 대상이다.",
        "Preload the font to avoid a flash of unstyled text.",
        "글자가 번쩍이지 않게 폰트를 프리로드하세요.",
    ),
    (
        "web vitals", "/ˈweb ˌvaɪtəlz/", "사용자 체감을 재는 표준 지표 묶음",
        FRONT, N,
        "화면이 얼마나 빨리 뜨고(LCP), 얼마나 빨리 반응하고(INP), 얼마나 덜 흔들리는지"
        "(CLS)를 재는 지표. 검색 순위에도 반영돼서 성능 이야기의 공통 언어가 됐다. "
        "실험실 측정과 실제 사용자 측정이 다를 수 있어 둘 다 본다.",
        "Our web vitals dropped after adding the chat widget.",
        "채팅 위젯을 넣고 나서 웹 바이탈이 떨어졌습니다.",
    ),
    (
        "above the fold", "/əˌbʌv ðə ˈfoʊld/", "스크롤 없이 처음 보이는 부분",
        FRONT, E,
        "신문을 접었을 때 위에 보이는 면에서 온 말. 여기에 있는 것을 먼저 받게 하고 "
        "나머지는 미루면 첫 화면이 빨리 뜬다. 화면 크기마다 경계가 달라서 폰 기준으로 "
        "정하는 편이 안전하다.",
        "Don't lazy-load this image; it's above the fold.",
        "이 이미지는 지연 로딩하지 마세요. 첫 화면에 보입니다.",
    ),
    (
        "critical path", "/ˈkrɪtɪkəl ˌpæθ/", "화면이 뜨기까지 반드시 거쳐야 하는 길",
        FRONT, H,
        "첫 화면을 그리는 데 꼭 필요한 자원과 그 순서. 이 길에 있는 것이 하나라도 "
        "늦으면 전체가 늦는다. 여기에 없는 것은 나중에 받아도 되므로, 무엇이 이 길에 "
        "있는지 가려내는 것이 성능 작업의 출발점이다.",
        "That script blocks the critical path; load it async.",
        "그 스크립트가 임계 경로를 막습니다. 비동기로 받으세요.",
    ),
    (
        "shadow DOM", "/ˈʃædoʊ ˌdɑm/", "안쪽을 감춰 스타일이 안 새게 만든 영역",
        FRONT, H,
        "컴포넌트 내부를 바깥과 격리해 CSS 와 선택자가 서로 안 닿게 한다. 위젯을 남의 "
        "페이지에 넣을 때 서로 스타일을 망치지 않는다. 대신 바깥에서 안을 꾸미기 어려워 "
        "테마를 입히려면 따로 통로를 열어줘야 한다.",
        "The widget renders in shadow DOM so our CSS won't leak in.",
        "위젯이 섀도 DOM 에 그려져서 우리 CSS 가 안으로 안 샙니다.",
    ),

    # ---------- 데이터베이스·분산 ----------
    (
        "read replica", "/ˈrid ˌreplɪkə/", "읽기 전용으로 복제해둔 DB",
        DB, N,
        "원본의 내용을 따라 복제해두고 조회만 받는 DB. 읽기가 많은 서비스에서 원본의 "
        "부담을 덜어준다. 복제가 조금 늦어서, 방금 저장한 것을 바로 조회하면 아직 "
        "없을 수 있다 - 저장 직후 조회는 원본으로 보내는 이유다.",
        "Point the dashboard queries at a read replica.",
        "대시보드 쿼리는 읽기 복제본으로 보내세요.",
    ),
    (
        "quorum", "/ˈkwɔrəm/", "과반이 동의해야 결정으로 치기",
        CS, H,
        "여러 대가 함께 결정할 때 몇 대 이상이 같은 답을 내야 유효한지를 정한 수. "
        "과반으로 잡으면 서로 다른 두 결정이 동시에 성립할 수 없다. 그래서 홀수 대로 "
        "구성하는 경우가 많다.",
        "Writes need a quorum of three out of five nodes.",
        "쓰기는 다섯 노드 중 셋의 정족수가 필요합니다.",
    ),
    (
        "split brain", "/ˈsplɪt ˌbreɪn/", "끊긴 채 양쪽이 각자 주인 행세하기",
        CS, H,
        "네트워크가 끊겨 서로를 못 보게 된 두 무리가 각각 자기가 정상이라고 여기는 "
        "상태. 양쪽이 따로 쓰기를 받아 데이터가 갈라진다. 정족수를 두는 것이 이걸 "
        "막는 방법이다 - 과반이 안 되는 쪽은 스스로 물러난다.",
        "Without a quorum you risk a split brain during a partition.",
        "정족수가 없으면 네트워크 분단 때 스플릿 브레인이 날 수 있습니다.",
    ),
    (
        "bulkhead", "/ˈbʌlkˌhed/", "칸을 나눠 한 칸만 잠기게 하기",
        CS, H,
        "배의 격벽에서 온 말. 자원을 기능별로 나눠두면 한 기능이 자원을 다 써도 다른 "
        "기능은 살아남는다. 연결 풀을 통째로 공유하면 느린 외부 API 하나가 전체를 "
        "멈추게 하는데, 나눠두면 그 기능만 멈춘다.",
        "Give the export job its own thread pool as a bulkhead.",
        "내보내기 작업에는 격벽으로 전용 스레드 풀을 주세요.",
    ),
    (
        "vacuum", "/ˈvækjuəm/", "지운 자리를 실제로 정리하기",
        DB, H,
        "PostgreSQL 에서 삭제·갱신된 행이 남긴 자리를 회수하는 작업. 지웠다고 바로 "
        "자리가 주는 것이 아니라, 이 작업이 돌아야 재사용된다. 안 돌면 표가 계속 "
        "부풀고 조회가 느려진다. 보통 자동으로 도는데 쓰기가 많으면 못 따라간다.",
        "The table is bloated; autovacuum can't keep up.",
        "표가 부풀었습니다. 오토배큠이 못 따라가고 있어요.",
    ),

    # ---------- API·아키텍처 ----------
    (
        "sticky session", "/ˈstɪki ˌseʃən/", "같은 사용자를 같은 서버로 계속 보내기",
        API, N,
        "로드밸런서가 한 사용자의 요청을 처음 간 서버로 계속 보내는 것. 서버가 세션을 "
        "자기 메모리에 들고 있을 때 필요하다. 대신 그 서버가 죽으면 그 사용자만 "
        "로그아웃되고, 부하도 고르게 안 퍼진다.",
        "Sticky sessions make rolling deploys drop user sessions.",
        "스티키 세션을 쓰면 순차 배포 때 사용자 세션이 끊깁니다.",
    ),
    (
        "chaos engineering", "/ˌkeɪɑs ˌendʒəˈnɪrɪŋ/", "일부러 고장 내 견디는지 보기",
        OPS, H,
        "운영 중인 시스템에 의도적으로 장애를 일으켜 실제로 버티는지 확인하는 방법. "
        "설계상 견딜 것 같다는 것과 실제로 견디는 것은 다르다. 영향 범위를 좁히고 "
        "언제든 멈출 수 있게 준비한 뒤에 한다.",
        "Chaos engineering found that our failover never worked.",
        "카오스 엔지니어링으로 우리 장애 전환이 한 번도 동작하지 않았다는 걸 찾았습니다.",
    ),
    (
        "shift left", "/ˌʃɪft ˈleft/", "확인을 앞 단계로 당기기",
        REVIEW, N,
        "테스트나 보안 점검을 개발 뒤가 아니라 개발 중으로 당기는 것. 늦게 찾을수록 "
        "고치는 비용이 커지기 때문이다. 개발자 컴퓨터에서 린트와 테스트가 도는 것도 "
        "이 방향이다.",
        "Shift left on security so we catch this before review.",
        "리뷰 전에 잡히도록 보안 점검을 앞 단계로 당깁시다.",
    ),
]


class Command(BaseCommand):
    help = "단어 데이터를 추가로 넣습니다(seed_words 의 뒤를 잇는 묶음)."

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

        for row in WORDS:
            (
                term,
                pronunciation,
                meaning,
                category,
                difficulty,
                description,
                example,
                example_translation,
            ) = row

            if Word.objects.filter(term=term).exists():
                skipped += 1
                continue

            if not dry_run:
                Word.objects.create(
                    term=term,
                    pronunciation=pronunciation,
                    meaning=meaning,
                    category=category,
                    difficulty=difficulty,
                    description=description,
                    example=example,
                    example_translation=example_translation,
                    source="직접 작성",
                    # 사람이 쓴 것은 검수 대기를 안 거친다. seed_words 와 같다.
                    is_reviewed=True,
                )
            created += 1
            self.stdout.write(f"  {category:9} {term}")

        self.stdout.write("")
        self.stdout.write(f"추가: {created}개 / 이미 있어 건너뜀: {skipped}개")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run 이라 저장하지 않았습니다."))
