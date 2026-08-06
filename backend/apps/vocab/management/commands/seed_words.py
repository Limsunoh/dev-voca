"""초기 단어 데이터를 넣는다.

사용:
    python manage.py seed_words          # 없는 것만 추가
    python manage.py seed_words --reset  # 같은 term 이 있으면 내용을 갱신

--reset 은 검수 대기 중인 단어를 건너뛴다. 그것까지 시드 값으로 덮어쓰려면
--reset --force-pending 을 함께 준다. 검수를 기다리던 AI 생성물이 사라지므로
Admin 에서 처리할 수 없을 때만 쓴다.

AI 생성물(generate_words)과 달리 is_reviewed=True 로 들어간다. 근거는
"사람 눈을 거쳤나" 인데, 566개 규모에서 그게 무엇이었는지 적어둔다.

    형식  : tests.py 가 전 항목에 기계적으로 건다. 발음기호 슬래시·장음
            기호 금지·한글 혼입·두 단어 주강세, term 중복·길이·빈 필드.
    내용  : 분야별로 나눠 전수를 읽고 오류 목록을 뽑은 뒤, 지적을 하나씩
            판정해 반영했다. SHA 가 알고리즘인지 출력값인지, big O 가
            정처기에서 무엇을 뜻하는지 같은 판단이 여기서 나왔다.

즉 "PR 에서 diff 를 한 줄씩 읽었다" 가 아니라 "전수 기계 검증 + 분담 내용
검수" 다. 다음에 데이터를 크게 늘릴 때도 같은 수준을 거쳐야 이 True 가
정당하다 - 검수 없이 붓는 통로로 쓰지 말 것.

검수 게이트를 우회해도 된다는 뜻이 아니다. 사용자 조회 경로(views.py)는
여전히 is_reviewed=True 만 내보내고, 런타임에 외부로 들어오는 데이터는
사람이 만들었더라도 항상 False 여야 한다.

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
        "race condition", "/ˈreɪs kənˌdɪʃən/", "순서에 따라 결과가 달라지는 문제", DEBUG, H,
        "둘 이상이 동시에 같은 것을 다루면서 누가 먼저 끝나느냐에 따라 결과가 "
        "달라지는 문제. 대부분은 잘 돌다가 가끔 틀린 값이 나오기 때문에 재현이 "
        "어렵다. 느린 환경에서만 나타나거나 로그를 넣으면 사라지는 것이 "
        "전형적인 증상이다.",
        "It only fails under load, which smells like a race condition.",
        "부하가 걸릴 때만 실패하는데 경쟁 상태로 보입니다.",
    ),
    (
        "regression", "/rɪˈɡreʃən/", "고쳐졌던 것이 다시 깨짐", DEBUG, N,
        "예전에 잘 되던 기능이 다른 변경 때문에 다시 망가지는 것. 이를 막으려고 "
        "회귀 테스트를 돌린다.",
        "The new release introduced a regression in the login flow.",
        "새 릴리스에서 로그인 흐름에 회귀 문제가 생겼습니다.",
    ),
    # ========== 여기부터 2차 추가 ==========
    # ---------- git ----------
    (
        "branch", "/bræntʃ/", "따로 갈라놓은 작업 줄기", GIT, E,
        "본 흐름을 건드리지 않고 따로 작업하려고 갈라낸 줄기. 실제로는 커밋 하나를 "
        "가리키는 이름표에 가깝고, 커밋할 때마다 그 이름표가 앞으로 따라 옮겨간다. "
        "파일을 복사해두는 게 아니라서 만드는 데 비용이 거의 들지 않는다.",
        "Create a branch for this fix instead of working on main.",
        "main 에서 작업하지 말고 이 수정용 브랜치를 만드세요.",
    ),
    (
        "checkout", "/ˈtʃekaʊt/", "작업 위치를 그쪽으로 옮기다", GIT, E,
        "지정한 브랜치나 커밋 상태로 작업 폴더를 바꾸는 것. 커밋하지 않은 변경이 "
        "있으면 막히거나 딸려간다. 브랜치 이동과 파일 되돌리기를 한 명령이 "
        "겸하고 있어 헷갈리기 쉬워서, 지금은 switch 와 restore 로 나뉘어 있다.",
        "Check out the release branch and run the tests there.",
        "릴리스 브랜치로 이동해서 거기서 테스트를 돌려보세요.",
    ),
    (
        "switch", "/swɪtʃ/", "브랜치만 바꾸다", GIT, E,
        "checkout 이 하던 일 중 브랜치 이동만 떼어낸 명령. 파일을 되돌리는 기능이 "
        "없어서 실수로 작업 내용을 날릴 위험이 적다. 파일 되돌리기는 restore 가 맡는다.",
        "Switch to the feature branch before you start.",
        "시작하기 전에 기능 브랜치로 옮기세요.",
    ),
    (
        "clone", "/kloʊn/", "원격 저장소를 통째로 받아오다", GIT, E,
        "원격 저장소를 히스토리까지 함께 내 컴퓨터로 복제하는 것. 단순 다운로드와 "
        "달리 모든 커밋 기록이 같이 오기 때문에 인터넷 없이도 과거 기록을 볼 수 있다. "
        "복제해온 곳은 자동으로 origin 이라는 이름의 원격으로 등록된다.",
        "Clone the repo and check out the develop branch.",
        "저장소를 클론하고 develop 브랜치로 이동하세요.",
    ),
    (
        "fork", "/fɔrk/", "남의 저장소를 내 계정으로 복사하다", GIT, N,
        "다른 사람 저장소를 내 계정 아래에 복사본으로 만드는 것. git 명령이 아니라 "
        "GitHub 같은 서비스의 기능이다. 원본에 쓰기 권한이 없을 때 포크에서 작업하고 "
        "풀 리퀘스트로 원본에 제안하는 방식으로 오픈소스에 기여한다.",
        "Fork the repository and send a pull request from your fork.",
        "저장소를 포크한 뒤 포크에서 풀 리퀘스트를 보내세요.",
    ),
    (
        "pull request", "/ˈpʊl rɪˌkwest/", "내 작업을 합쳐달라는 요청", GIT, E,
        "내 브랜치를 대상 브랜치에 합쳐달라고 올리는 요청. 이름은 요청이지만 실제로는 "
        "리뷰가 오가는 토론 공간이고, 합치기 자체는 승인 뒤에 일어난다. GitLab 에서는 "
        "merge request 라고 부르는데 같은 것이다. 줄여서 PR 이라고 쓴다.",
        "I left a few comments on your pull request.",
        "풀 리퀘스트에 코멘트 몇 개 남겼습니다.",
    ),
    (
        "cherry-pick", "/ˈtʃeri ˌpɪk/", "커밋 하나만 골라 가져오다", GIT, N,
        "다른 브랜치의 커밋 중 필요한 것만 골라 지금 브랜치에 적용하는 것. 원본을 "
        "옮겨오는 게 아니라 같은 변경 내용으로 새 커밋을 만들기 때문에 해시가 달라진다. "
        "나중에 그 브랜치를 통째로 병합하면 같은 변경이 두 번 들어와 충돌이 나기 쉽다.",
        "Cherry-pick that hotfix commit onto the release branch.",
        "그 핫픽스 커밋을 릴리스 브랜치로 체리픽하세요.",
    ),
    (
        "bisect", "/baɪˈsekt/", "이분 탐색으로 문제 커밋 찾기", GIT, H,
        "정상이던 커밋과 고장난 커밋을 알려주면 그 사이를 절반씩 잘라가며 원인 커밋을 "
        "찾아주는 기능. 커밋 1000 개도 열 번 정도만 확인하면 범인이 나온다. "
        "매번 좋음/나쁨을 사람이 알려줘야 하지만, 판정을 스크립트로 넘기면 자동으로 돈다.",
        "I ran git bisect and it pointed at last week's config change.",
        "git bisect 를 돌렸더니 지난주 설정 변경을 지목했습니다.",
    ),
    (
        "worktree", "/ˈwɜrk tri/", "한 저장소를 여러 폴더에서 동시에", GIT, H,
        "같은 저장소를 여러 폴더에 동시에 펼쳐두고 각 폴더에서 다른 브랜치를 보는 기능. "
        "저장소를 여러 번 클론하는 것과 달리 커밋 기록은 하나만 쓴다. 리뷰하면서 "
        "내 작업은 그대로 두고 싶을 때 스태시 대신 쓴다.",
        "Use a worktree so you do not have to stash your changes.",
        "스태시하지 않아도 되게 워크트리를 쓰세요.",
    ),
    (
        "remote", "/rɪˈmoʊt/", "원격 저장소에 붙인 별명", GIT, E,
        "인터넷 어딘가에 있는 저장소 주소에 붙여둔 짧은 이름. origin 이나 upstream 은 "
        "정해진 규칙이 아니라 그냥 관례적으로 쓰는 별명이라 얼마든지 바꿀 수 있다. "
        "원격은 여러 개를 등록해둘 수 있다.",
        "Add the original repo as a second remote named upstream.",
        "원본 저장소를 upstream 이라는 두 번째 원격으로 추가하세요.",
    ),
    (
        "origin", "/ˈɔrɪdʒɪn/", "클론해온 원격의 기본 이름", GIT, E,
        "클론할 때 자동으로 붙는 원격 이름. 특별한 권한이 있는 게 아니라 단지 기본값 "
        "이름일 뿐이고, 내 저장소가 아니라 클론해온 쪽을 가리킨다. 포크에서 작업할 때는 "
        "origin 이 내 포크이고 원본은 보통 upstream 으로 따로 등록한다.",
        "Push to origin, not upstream.",
        "upstream 말고 origin 으로 푸시하세요.",
    ),
    (
        "upstream", "/ˈʌpstrim/", "내가 따라가는 원본 쪽", GIT, N,
        "내 작업의 기준이 되는 위쪽 저장소나 브랜치. 포크 작업에서는 원본 저장소를, "
        "브랜치 설정에서는 내 로컬 브랜치가 짝지어진 원격 브랜치를 가리킨다. "
        "두 뜻이 다르니 문맥을 봐야 한다.",
        "Pull the latest changes from upstream before you continue.",
        "계속하기 전에 upstream 의 최신 변경을 받아오세요.",
    ),
    (
        "fetch", "/fetʃ/", "가져오기만 하고 합치지는 않다", GIT, N,
        "원격의 새 커밋을 내려받되 내 브랜치에는 손대지 않는 것. 받아온 내용은 "
        "origin/main 같은 별도 이름에만 반영되고 내 작업 폴더는 그대로다. "
        "먼저 확인하고 합치고 싶을 때 pull 대신 쓴다.",
        "Fetch first and see what changed before merging.",
        "먼저 페치해서 뭐가 바뀌었는지 보고 병합하세요.",
    ),
    (
        "pull", "/pʊl/", "가져와서 합치기까지", GIT, E,
        "fetch 로 받아온 다음 곧바로 내 브랜치에 합치는 것. 즉 pull 은 fetch 와 merge 를 "
        "한 번에 하는 것이고, 설정에 따라 merge 대신 rebase 로 합치기도 한다. "
        "합치기가 자동으로 일어나므로 충돌은 pull 도중에 터진다.",
        "Pull the latest main before you open the pull request.",
        "풀 리퀘스트를 열기 전에 최신 main 을 받아오세요.",
    ),
    (
        "push", "/pʊʃ/", "내 커밋을 원격에 올리다", GIT, E,
        "로컬에 쌓아둔 커밋을 원격 저장소로 보내는 것. 커밋은 내 컴퓨터에만 남기 때문에 "
        "푸시하기 전까지는 아무도 그 작업을 볼 수 없다. 원격이 내 기록보다 앞서 있으면 "
        "거절당하고, 먼저 받아와서 합쳐야 한다.",
        "Your commit is not pushed yet, so nobody else can see it.",
        "커밋이 아직 푸시되지 않아서 다른 사람은 볼 수 없습니다.",
    ),
    (
        "force push", "/ˈfɔrs ˌpʊʃ/", "원격 기록을 덮어쓰며 올리다", GIT, H,
        "원격이 가진 커밋과 어긋나도 밀어붙여 내 기록으로 바꿔버리는 것. 같은 브랜치를 "
        "보던 사람의 커밋이 사라질 수 있어서 공유 브랜치에서는 사고가 된다. "
        "--force-with-lease 를 쓰면 내가 본 뒤로 원격이 바뀐 경우 거절되어 그나마 안전하다.",
        "Never force push to main; use force-with-lease on your own branch.",
        "main 에는 절대 강제 푸시하지 말고, 본인 브랜치에서만 force-with-lease 를 쓰세요.",
    ),
    (
        "HEAD", "/hed/", "지금 서 있는 커밋", GIT, N,
        "작업 폴더가 현재 어느 커밋을 기준으로 하는지 가리키는 표시. 보통은 브랜치 "
        "이름을 거쳐 커밋을 가리키고, HEAD~1 처럼 써서 그 앞 커밋을 지목할 수 있다. "
        "반드시 대문자로 써야 한다. 소문자는 원칙적으로 다른 이름이라, "
        "맥이나 윈도우에서 우연히 통하다가 리눅스 서버나 CI 에서 실패한다.",
        "Reset to HEAD~1 to undo the last commit.",
        "마지막 커밋을 취소하려면 HEAD~1 로 리셋하세요.",
    ),
    (
        "detached HEAD", "/dɪˈtætʃt ˌhed/", "브랜치 없이 커밋에 서 있는 상태", GIT, H,
        "브랜치를 거치지 않고 특정 커밋을 직접 보고 있는 상태. 여기서 커밋을 쌓아도 "
        "어떤 브랜치에도 매달리지 않아서, 다른 곳으로 이동하는 순간 이름 없이 떠돌다 "
        "결국 청소된다. 계속 쓰려면 그 자리에서 브랜치를 새로 만들면 된다.",
        "You are in detached HEAD state; create a branch to keep these commits.",
        "지금 detached HEAD 상태입니다. 이 커밋들을 남기려면 브랜치를 만드세요.",
    ),
    (
        "staging area", "/ˈsteɪdʒɪŋ ˌeriə/", "커밋에 담을 것을 골라두는 곳", GIT, N,
        "고친 것 중 이번 커밋에 넣을 것만 미리 담아두는 중간 자리. 파일을 고쳤다고 "
        "자동으로 커밋되지 않는 이유가 여기 있다. 한 파일에서 일부 줄만 담을 수도 있어서 "
        "섞여버린 작업을 여러 커밋으로 나눌 때 쓴다. index 라고도 부른다.",
        "Only staged changes go into the commit.",
        "스테이징된 변경만 커밋에 들어갑니다.",
    ),
    (
        "working tree", "/ˈwɜrkɪŋ ˌtri/", "지금 파일이 놓인 실제 폴더", GIT, N,
        "에디터로 열어 실제로 고치고 있는 파일들이 놓인 폴더. 커밋된 내용, 스테이징된 "
        "내용과는 별개의 층이라 git status 가 이 셋을 비교해서 보여준다. "
        "여기서만 고친 내용은 어디에도 기록되지 않아 실수로 되돌리면 복구가 어렵다.",
        "Your working tree is dirty; commit or stash before switching.",
        "작업 폴더에 변경이 남아 있습니다. 이동하기 전에 커밋하거나 스태시하세요.",
    ),
    (
        "untracked", "/ʌnˈtrækt/", "git 이 아직 모르는 파일", GIT, E,
        "저장소 안에 있지만 한 번도 추가된 적이 없어 git 이 관리하지 않는 파일. "
        "커밋해도 딸려가지 않고, 브랜치를 바꿔도 그대로 남는다. 새로 만든 파일이 "
        "PR 에 안 보인다면 대개 이것이다.",
        "The new config file is still untracked.",
        "새 설정 파일이 아직 추적되지 않고 있습니다.",
    ),
    (
        "gitignore", "/ˈɡɪt ɪɡˌnɔr/", "추적하지 않을 파일 목록", GIT, E,
        "저장소에 두되 기록에는 남기지 않을 파일 규칙을 적어두는 파일. 이미 추적 중인 "
        "파일은 여기 적어도 계속 따라온다. 그럴 때는 추적 목록에서 먼저 빼야 한다. "
        "비밀번호가 들어간 파일을 한 번 커밋하면 파일을 지워도 기록에 남는다. "
        "히스토리를 다시 써서 없앨 수는 있지만 이미 클론된 사본에는 그대로 남으므로, "
        "유출된 것으로 보고 값을 새로 발급하는 것이 맞다.",
        "Add the env file to gitignore so it never gets committed.",
        "env 파일이 커밋되지 않게 gitignore 에 추가하세요.",
    ),
    (
        "diff", "/dɪf/", "달라진 줄만 보여주기", GIT, E,
        "두 상태를 비교해 없어진 줄과 생긴 줄만 추려 보여주는 것. 줄 단위로 비교하기 "
        "때문에 한 글자만 고쳐도 그 줄 전체가 바뀐 것으로 나온다. 코드 정렬만 바꿔도 "
        "diff 가 커지는 이유이고, 그래서 포맷 변경은 따로 커밋하는 게 좋다.",
        "The diff is huge because the formatter touched every line.",
        "포매터가 모든 줄을 건드려서 diff 가 아주 큽니다.",
    ),
    (
        "patch", "/pætʃ/", "변경분만 담은 파일", GIT, N,
        "어떤 줄을 어떻게 바꾸라는 내용을 텍스트로 담은 것. 저장소 접근 없이 메일로 "
        "변경을 주고받던 방식에서 왔고, 지금도 리눅스 커널 같은 곳은 이렇게 기여를 받는다. "
        "적용할 기준 코드가 이미 바뀌었으면 적용에 실패한다.",
        "Send the patch as an attachment if you cannot push.",
        "푸시할 수 없으면 패치를 첨부로 보내주세요.",
    ),
    (
        "blame", "/bleɪm/", "줄마다 마지막에 고친 사람 보기", GIT, N,
        "파일의 각 줄이 어느 커밋에서 마지막으로 바뀌었는지 보여주는 기능. 이름과 달리 "
        "책임을 묻는 용도가 아니라 왜 이렇게 됐는지 그 커밋 메시지를 찾아가려고 쓴다. "
        "마지막 변경만 보이므로 들여쓰기만 고친 커밋이 원래 작성자를 가려버리기도 한다.",
        "Run blame on that line to find the original discussion.",
        "그 줄에 blame 을 돌려서 원래 논의를 찾아보세요.",
    ),
    (
        "tag", "/tæɡ/", "특정 커밋에 붙이는 이름표", GIT, E,
        "v1.2.0 처럼 사람이 기억할 이름을 커밋 하나에 붙여두는 것. 브랜치와 달리 "
        "커밋을 쌓아도 따라 움직이지 않고 그 자리에 고정된다. 그래서 릴리스 지점을 "
        "표시하는 데 쓴다. 푸시할 때 자동으로 올라가지 않아 따로 밀어야 한다.",
        "Tag this commit as v2.0.0 and push the tag.",
        "이 커밋에 v2.0.0 태그를 붙이고 태그도 푸시하세요.",
    ),
    (
        "submodule", "/ˈsʌbˌmɑdʒul/", "저장소 안에 끼워 넣은 다른 저장소", GIT, H,
        "다른 저장소를 폴더로 품되, 그 내용이 아니라 어느 커밋을 쓸지만 기록해두는 방식. "
        "그래서 클론만 하면 그 폴더가 비어 있고 따로 받아와야 한다. 안쪽 저장소의 "
        "최신 변경이 자동으로 따라오지 않는 것이 가장 흔한 함정이다.",
        "The submodule folder is empty because it was not initialized.",
        "서브모듈 폴더가 초기화되지 않아 비어 있습니다.",
    ),
    (
        "conflict", "/ˈkɑnflɪkt/", "양쪽이 같은 곳을 고쳐 생긴 충돌", GIT, E,
        "합치려는 두 갈래가 같은 파일의 같은 부분을 다르게 고쳤을 때 생기는 상태. "
        "git 은 어느 쪽이 맞는지 판단하지 않고 양쪽 내용을 파일에 표시한 채 멈춘다. "
        "표시를 지우고 최종 내용을 사람이 정해줘야 진행된다.",
        "Resolve the conflicts in that file and mark them as resolved.",
        "그 파일의 충돌을 해결하고 해결됨으로 표시하세요.",
    ),
    (
        "fast-forward", "/ˌfæst ˈfɔrwərd/", "합치지 않고 앞으로 밀기", GIT, N,
        "합칠 대상이 내 커밋보다 그냥 앞서 있기만 할 때, 새 커밋을 만들지 않고 "
        "브랜치 이름표만 앞으로 옮기는 것. 히스토리가 깔끔해지지만 어디서 합쳤는지 "
        "흔적이 안 남는다. 흔적을 남기고 싶으면 --no-ff 로 병합 커밋을 강제한다.",
        "This merge was a fast-forward, so there is no merge commit.",
        "이번 병합은 fast-forward 여서 병합 커밋이 없습니다.",
    ),
    (
        "amend", "/əˈmend/", "직전 커밋을 고쳐 쓰다", GIT, N,
        "마지막 커밋의 메시지나 내용을 바꾸는 것. 기존 커밋을 수정하는 게 아니라 "
        "새 커밋으로 갈아치우는 것이라 해시가 바뀐다. 이미 푸시한 커밋에 하면 "
        "원격과 어긋나서 강제 푸시가 필요해진다.",
        "Amend the commit instead of adding a fix-typo commit.",
        "오타 수정 커밋을 따로 만들지 말고 커밋을 amend 하세요.",
    ),
    (
        "reset", "/ˌriˈset/", "브랜치 위치를 뒤로 옮기다", GIT, H,
        "브랜치가 가리키는 자리를 지정한 커밋으로 되돌리는 것. 커밋이 즉시 삭제되지는 "
        "않고 reflog 로 한동안 찾을 수 있다. 진짜 위험한 점은 히스토리가 달라져서 "
        "공유 브랜치에 쓰면 남의 기록과 어긋난다는 것이다. --hard 는 작업 폴더까지 "
        "되돌려 저장 안 한 변경을 실제로 날린다.",
        "Reset the branch to the commit before the bad merge.",
        "잘못된 병합 직전 커밋으로 브랜치를 리셋하세요.",
    ),
    (
        "reflog", "/ˈreflɔɡ/", "브랜치가 거쳐온 자리의 기록", GIT, H,
        "HEAD 와 브랜치가 그동안 어디를 가리켰는지 로컬에만 남겨두는 기록. "
        "리셋이나 리베이스로 잃어버린 것처럼 보이는 커밋을 여기서 찾아 되살릴 수 있다. "
        "원격에는 올라가지 않고 일정 기간이 지나면 정리되므로 영구 백업은 아니다.",
        "Check the reflog; the commit is probably still there.",
        "reflog 를 확인해 보세요. 그 커밋은 아마 아직 남아 있습니다.",
    ),
    (
        "hook", "/hʊk/", "특정 시점에 자동으로 실행되는 스크립트", GIT, N,
        "커밋 직전이나 푸시 직전 같은 시점에 자동으로 도는 스크립트. 포맷 검사나 "
        "테스트를 걸어두면 잘못된 커밋을 미리 막을 수 있다. 저장소에 함께 배포되지 "
        "않아 팀원마다 따로 설치해야 하는 것이 함정이다.",
        "The pre-commit hook rejects code that fails the linter.",
        "pre-commit 훅이 린터를 통과하지 못한 코드를 막습니다.",
    ),
    (
        "prune", "/prun/", "사라진 원격 브랜치 정보 치우기", GIT, N,
        "원격에서는 이미 지워졌는데 내 컴퓨터에만 남아 있는 원격 브랜치 표시를 "
        "정리하는 것. 내 로컬 브랜치를 지우는 것이 아니라 원격을 비추던 낡은 그림자만 "
        "치운다. 병합된 브랜치가 계속 목록에 뜨는 이유가 대개 이것이다.",
        "Run fetch with prune to clean up deleted remote branches.",
        "지워진 원격 브랜치를 정리하려면 fetch 에 prune 을 붙여 실행하세요.",
    ),
    (
        "shallow clone", "/ˈʃæloʊ ˌkloʊn/", "최근 기록만 받는 복제", GIT, N,
        "전체 히스토리 대신 최근 몇 개 커밋만 받아오는 복제. 오래된 저장소를 빠르게 "
        "받을 수 있어 CI 에서 많이 쓴다. 과거 기록이 없으니 blame 이나 bisect 가 "
        "제대로 동작하지 않는다.",
        "CI uses a shallow clone, so the full history is not available there.",
        "CI 는 shallow clone 을 쓰기 때문에 거기서는 전체 히스토리를 볼 수 없습니다.",
    ),
    (
        "tracking branch", "/ˈtrækɪŋ ˌbræntʃ/", "원격과 짝지어진 로컬 브랜치", GIT, N,
        "어느 원격 브랜치를 따라갈지 미리 정해둔 로컬 브랜치. 짝이 지어져 있으면 "
        "push 나 pull 을 인자 없이 쓸 수 있고, 몇 커밋 앞서고 뒤처졌는지도 알려준다. "
        "새로 만든 브랜치는 짝이 없어서 첫 푸시에 -u 를 붙여 연결한다.",
        "Set the upstream so this becomes a tracking branch.",
        "이 브랜치가 원격과 연결되도록 upstream 을 설정하세요.",
    ),
    (
        "merge commit", "/ˈmɜrdʒ ˌkɑmɪt/", "부모가 둘인 합치기 커밋", GIT, N,
        "두 갈래를 합칠 때 생기는, 앞선 커밋을 두 개 가진 특별한 커밋. 언제 어디서 "
        "합쳤는지가 기록으로 남는 대신 히스토리가 갈래져 보인다. 되돌릴 때는 어느 쪽을 "
        "기준으로 삼을지 지정해야 해서 일반 커밋보다 손이 더 간다.",
        "Revert the merge commit and specify the mainline parent.",
        "병합 커밋을 되돌리면서 기준이 될 부모를 지정하세요.",
    ),
    (
        "monorepo", "/ˈmɑnoʊˌripoʊ/", "여러 프로젝트를 한 저장소에", GIT, N,
        "서로 다른 서비스나 패키지를 하나의 저장소에 함께 두는 방식. 공통 코드를 "
        "고칠 때 한 번에 반영되고 버전 맞추기가 쉬워지지만, 저장소가 커지고 "
        "CI 에서 바뀐 부분만 골라 빌드하는 장치가 필요해진다.",
        "We moved both services into a monorepo last quarter.",
        "지난 분기에 두 서비스를 모노레포로 합쳤습니다.",
    ),
    (
        "changelog", "/ˈtʃeɪndʒlɔɡ/", "버전별 변경 내역 목록", GIT, E,
        "버전마다 무엇이 바뀌었는지 사람이 읽으라고 정리해둔 문서. 커밋 로그를 그대로 "
        "옮긴 게 아니라 사용자가 알아야 할 것만 추려 적는다. 새 버전으로 올리다 "
        "문제가 생겼을 때 가장 먼저 확인하는 문서다.",
        "Check the changelog before upgrading to the new major version.",
        "새 메이저 버전으로 올리기 전에 체인지로그를 확인하세요.",
    ),
    (
        "semantic versioning", "/sɪˈmæntɪk ˌvɜrʒənɪŋ/", "숫자 세 자리 버전 규칙", GIT, N,
        "버전을 주.부.수 세 자리로 적고 각 자리가 무엇을 뜻하는지 약속해둔 규칙. "
        "맨 앞자리가 오르면 기존 코드가 깨질 수 있다는 신호이고, 맨 뒷자리는 "
        "고치기만 한 것이다. 줄여서 semver 라고 한다.",
        "This is a breaking change, so it needs a major version bump.",
        "이건 호환이 깨지는 변경이라 메이저 버전을 올려야 합니다.",
    ),
    (
        "release", "/rɪˈlis/", "쓸 수 있게 묶어 내놓기", GIT, E,
        "특정 시점의 코드를 버전 이름으로 묶어 사용자에게 내놓는 것. 배포(deploy)가 "
        "서버에 올리는 행위라면 릴리스는 이 버전을 쓰라고 선언하는 쪽에 가깝다. "
        "그래서 배포해두고 나중에 릴리스만 여는 방식도 가능하다.",
        "We cut the release on Friday but rolled it out on Monday.",
        "금요일에 릴리스를 만들고 월요일에 배포했습니다.",
    ),
    (
        "hotfix", "/ˈhɑtfɪks/", "급한 장애를 막는 긴급 수정", GIT, E,
        "운영 중에 터진 문제를 막으려고 정식 절차를 줄여 바로 넣는 수정. 보통 "
        "개발 브랜치를 거치지 않고 운영 브랜치에서 갈라 만든다. 나중에 개발 브랜치에도 "
        "반영하지 않으면 다음 배포에서 문제가 되살아난다.",
        "The hotfix went straight to production; remember to merge it back.",
        "핫픽스가 운영에 바로 나갔습니다. 개발 브랜치에도 반영하는 걸 잊지 마세요.",
    ),
    (
        "restore", "/rɪˈstɔr/", "파일을 저장된 상태로 되돌리다", GIT, N,
        "고치던 파일을 인덱스(스테이징된 내용) 기준으로 되돌리는 명령. 스테이징한 "
        "것이 없으면 결과적으로 마지막 커밋 상태가 된다. 스테이징까지 함께 버리려면 "
        "--staged --worktree 를 같이 줘야 한다. 되돌린 내용은 어디에도 기록되지 "
        "않아 되살릴 방법이 없다는 점이 reset 이나 revert 와 크게 다르다.",
        "Restore that file to discard your local changes.",
        "로컬 변경을 버리려면 그 파일을 restore 하세요.",
    ),
    (
        "commit message", "/kəˈmɪt ˌmesɪdʒ/", "왜 고쳤는지 적는 설명", GIT, E,
        "커밋에 붙이는 설명글. 무엇을 바꿨는지는 diff 를 보면 알 수 있으므로 "
        "왜 바꿨는지를 적는 것이 핵심이다. 첫 줄은 짧게 요약하고 한 줄 띄운 뒤 "
        "자세히 적는 것이 널리 쓰이는 관례다.",
        "Please rewrite the commit message to explain why, not what.",
        "무엇이 아니라 왜인지 설명하도록 커밋 메시지를 다시 써주세요.",
    ),
    (
        "history rewrite", "/ˈhɪstəri ˌriraɪt/", "이미 쌓인 기록을 다시 쓰기", GIT, H,
        "rebase, amend, squash 처럼 기존 커밋을 새 커밋으로 갈아치우는 작업을 통틀어 "
        "부르는 말. 내용이 같아도 해시가 달라지므로 같은 브랜치를 보던 사람에게는 "
        "전혀 다른 기록이 된다. 공유된 브랜치에서 피하라는 조언은 전부 이 얘기다.",
        "Avoid rewriting history on branches other people have pulled.",
        "다른 사람이 받아간 브랜치에서는 히스토리를 다시 쓰지 마세요.",
    ),
    # ---------- 코드 리뷰 / 협업 ----------
    (
        "nit", "/nɪt/", "고쳐도 안 고쳐도 되는 사소한 지적", REVIEW, N,
        "리뷰에서 아주 사소한 의견 앞에 붙이는 표시. 오타나 변수명처럼 취향에 가까운 "
        "얘기라 이것 때문에 승인을 막지는 않겠다는 뜻이다. nitpick 의 줄임말이고 "
        "'nit:' 처럼 코멘트 맨 앞에 붙여 쓴다.",
        "nit: this variable could have a clearer name.",
        "사소한 의견인데, 이 변수명이 더 분명하면 좋겠습니다.",
    ),
    (
        "LGTM", "/ˌel dʒi ti ˈem/", "봤고 괜찮아 보인다", REVIEW, E,
        "Looks Good To Me 의 줄임말로, 승인하면서 남기는 인사말. 철자 그대로 "
        "한 글자씩 읽는다. 코드 전체를 검증했다는 뜻은 아니고 막을 이유가 없다는 "
        "정도의 표현이라서, 큰 변경에는 무엇을 확인했는지 덧붙이는 게 좋다.",
        "LGTM, but let's get a second pair of eyes on the migration.",
        "괜찮아 보입니다. 다만 마이그레이션은 한 명 더 봐주면 좋겠습니다.",
    ),
    (
        "blocking comment", "/ˈblɑkɪŋ ˌkɑment/", "고치기 전엔 못 합친다는 의견", REVIEW, N,
        "해결되기 전에는 병합하면 안 된다고 못박는 리뷰 의견. nit 과 정반대라서 "
        "어느 쪽인지 리뷰어가 분명히 표시해주지 않으면 작성자가 눈치만 보게 된다. "
        "그래서 팀들이 blocking 인지 아닌지 말머리로 붙이는 관례를 만든다.",
        "This is a blocking comment; the query will time out under load.",
        "이건 반드시 고쳐야 합니다. 부하가 걸리면 쿼리가 타임아웃납니다.",
    ),
    (
        "request changes", "/rɪˈkwest ˌtʃeɪndʒɪz/", "수정 요청 상태로 두다", REVIEW, E,
        "리뷰에서 승인 대신 고쳐달라는 상태로 표시하는 것. 코멘트만 남기는 것과 달리 "
        "병합 자체를 막는 경우가 많다. 리뷰어가 자리를 비우면 다른 사람이 승인해도 "
        "풀리지 않아 작업이 멈추므로, 남기고 자리를 뜰 때는 미리 알려주는 게 좋다.",
        "I requested changes on the PR; see the comment about error handling.",
        "PR 에 수정 요청을 남겼습니다. 에러 처리 관련 코멘트를 봐주세요.",
    ),
    (
        "approve", "/əˈpruv/", "합쳐도 좋다고 승인하다", REVIEW, E,
        "리뷰를 마치고 병합해도 된다고 표시하는 것. 승인 뒤에 커밋이 더 올라가면 "
        "설정에 따라 승인이 자동으로 취소되기도 한다. 승인은 코드가 완벽하다는 보증이 "
        "아니라 이 정도면 합쳐서 개선해가자는 합의에 가깝다.",
        "I will approve once the tests are green.",
        "테스트가 통과하면 승인하겠습니다.",
    ),
    (
        "coupling", "/ˈkʌplɪŋ/", "다른 것에 얼마나 얽혀 있는지", REVIEW, H,
        "한 부분이 다른 부분에 얼마나 의존하는지를 가리키는 말. 얽힘이 심하면 "
        "한쪽을 고칠 때 엉뚱한 곳이 깨진다. 의존을 없애는 게 목표가 아니라 "
        "바뀔 일이 많은 것끼리 덜 붙여두는 것이 목표다.",
        "This module is too tightly coupled to the payment provider.",
        "이 모듈이 결제 업체에 지나치게 얽혀 있습니다.",
    ),
    (
        "cohesion", "/koʊˈhiʒən/", "한 덩어리가 한 가지 일만 하는 정도", REVIEW, H,
        "한 모듈 안의 코드들이 얼마나 같은 목적을 향하는지. 결합도와 짝으로 쓰여서 "
        "'응집도는 높게, 결합도는 낮게' 라고 한다. utils 같은 파일이 계속 커지는 것은 "
        "응집도가 낮다는 신호다.",
        "Splitting this file would improve cohesion.",
        "이 파일을 나누면 응집도가 좋아질 것 같습니다.",
    ),
    (
        "technical debt", "/ˈteknɪkl ˌdet/", "나중에 갚기로 하고 미룬 정리", REVIEW, N,
        "당장 빨리 가려고 대충 해둔 부분이 쌓여 나중에 더 큰 비용으로 돌아오는 것. "
        "빚처럼 이자가 붙는다는 비유다. 나쁜 코드와 같은 말이 아니라, 알면서 선택한 "
        "타협도 포함한다. debt 의 b 는 소리 내지 않는다.",
        "We took on some technical debt to hit the deadline.",
        "마감을 맞추려고 기술 부채를 좀 졌습니다.",
    ),
    (
        "code smell", "/ˈkoʊd ˌsmel/", "뭔가 잘못됐다는 냄새", REVIEW, N,
        "당장 동작은 하지만 구조에 문제가 있을 것 같은 징후. 버그가 아니라 신호이기 "
        "때문에 반드시 고쳐야 하는 것은 아니다. 지나치게 긴 함수, 여기저기 복사된 코드, "
        "매개변수가 너무 많은 함수 같은 것들이 대표적이다.",
        "The duplicated validation logic is a code smell.",
        "중복된 검증 로직은 좋지 않은 징후입니다.",
    ),
    (
        "standup", "/ˈstændʌp/", "짧게 서서 하는 진행 공유", REVIEW, E,
        "매일 짧게 진행 상황과 막힌 것을 공유하는 회의. 길어지지 말라고 서서 한다는 "
        "데서 온 이름이다. 보고하는 자리가 아니라 막힌 사람을 찾아내는 자리라서, "
        "논의가 필요하면 따로 시간을 잡는 게 원래 취지다.",
        "I will bring that up at tomorrow's standup.",
        "그건 내일 스탠드업에서 얘기하겠습니다.",
    ),
    (
        "sprint", "/sprɪnt/", "정해진 짧은 작업 기간", REVIEW, E,
        "보통 1~2주로 끊어 그 안에 할 일을 정해두고 진행하는 기간. 더 빨리 일하라는 "
        "뜻이 아니라 계획 단위를 짧게 끊는다는 뜻이다. 기간 중에 일이 추가되면 "
        "무언가를 빼는 것이 원칙이다.",
        "That ticket did not make it into this sprint.",
        "그 티켓은 이번 스프린트에 들어가지 못했습니다.",
    ),
    (
        "backlog", "/ˈbæklɔɡ/", "아직 손대지 않은 할 일 더미", REVIEW, E,
        "언젠가 할 일을 우선순위대로 쌓아둔 목록. 밀린 일이라는 부정적인 뜻이 아니라 "
        "정상적인 대기열이다. 여기 들어갔다는 말은 하겠다는 약속이 아니라 "
        "잊지는 않겠다는 정도에 가깝다.",
        "I moved it to the backlog since it is not urgent.",
        "급하지 않아서 백로그로 옮겨뒀습니다.",
    ),
    (
        "retrospective", "/ˌretrəˈspektɪv/", "끝나고 돌아보는 회고", REVIEW, N,
        "한 주기를 마치고 무엇이 잘됐고 무엇을 바꿀지 이야기하는 자리. 누가 잘못했는지 "
        "찾는 자리가 아니라 다음에 바꿀 것 하나를 정하는 자리다. 줄여서 retro 라고 한다.",
        "Let's discuss the deploy failure at the retrospective.",
        "배포 실패 건은 회고에서 이야기합시다.",
    ),
    (
        "on-call", "/ˈɑn ˌkɔl/", "장애가 나면 받는 당번", REVIEW, N,
        "정해진 기간 동안 장애 알림을 받고 대응하는 당번. 하루 종일 붙어 있으라는 뜻이 "
        "아니라 호출되면 정해진 시간 안에 응답한다는 뜻이다. 인수인계 문서와 "
        "대응 절차가 없으면 당번 개인의 기억에 의존하게 된다.",
        "Who is on-call this week?",
        "이번 주 온콜 당번이 누구인가요?",
    ),
    (
        "postmortem", "/ˌpoʊstˈmɔrtəm/", "장애 후 원인 정리 문서", REVIEW, N,
        "장애가 끝난 뒤 무슨 일이 있었고 왜 그랬는지 정리해 남기는 기록. 시간 순서, "
        "원인, 다시 안 나게 할 조치를 적는다. 원래 부검을 뜻하는 말이라 사후 분석이라는 "
        "느낌이 강하다.",
        "The postmortem is due before the end of the week.",
        "포스트모템은 이번 주 안에 작성해야 합니다.",
    ),
    (
        "blameless", "/ˈbleɪmləs/", "사람을 탓하지 않는", REVIEW, N,
        "장애 분석에서 누가 실수했는지가 아니라 어떤 구조가 그 실수를 가능하게 했는지를 "
        "본다는 원칙. 탓하기 시작하면 사람들이 사실을 숨겨서 원인 파악 자체가 "
        "불가능해지기 때문에 나온 실용적인 규칙이다.",
        "We run blameless postmortems, so focus on the system, not the person.",
        "우리는 blameless 로 회고하니 사람이 아니라 시스템에 집중해주세요.",
    ),
    (
        "ticket", "/ˈtɪkɪt/", "일 하나를 담은 항목", REVIEW, E,
        "할 일이나 버그를 하나씩 등록해 추적하는 항목. issue, task, card 도 거의 같은 "
        "뜻으로 쓰이고 도구에 따라 이름만 다르다. 티켓 번호를 커밋 메시지나 브랜치 "
        "이름에 넣어두면 나중에 왜 고쳤는지 찾기 쉬워진다.",
        "Please file a ticket so we can track it.",
        "추적할 수 있게 티켓을 하나 만들어 주세요.",
    ),
    (
        "scope creep", "/ˈskoʊp ˌkrip/", "슬금슬금 늘어나는 작업 범위", REVIEW, N,
        "처음 정한 범위 밖의 요구가 조금씩 붙어 일이 계속 커지는 현상. 큰 변경 하나가 "
        "아니라 작은 추가가 여러 번 들어와서 알아채기 어려운 것이 특징이다. "
        "리뷰에서도 관련 없는 수정이 섞여 들어오면 이 말을 쓴다.",
        "This PR has some scope creep; can you split out the logging change?",
        "이 PR 은 범위가 좀 넓어졌습니다. 로깅 변경은 따로 빼줄 수 있나요?",
    ),
    (
        "out of scope", "/ˌaʊt əv ˈskoʊp/", "이번 범위 밖", REVIEW, E,
        "지금 하려는 작업의 범위에 들어가지 않는다는 표현. 안 하겠다는 뜻이 아니라 "
        "여기서는 안 다룬다는 뜻이라, 대개 따로 티켓을 만들자는 제안이 뒤따른다. "
        "리뷰 코멘트를 정중히 미룰 때 가장 많이 쓰는 말이다.",
        "Good point, but that is out of scope for this PR.",
        "좋은 지적인데 이번 PR 범위 밖입니다.",
    ),
    (
        "follow-up", "/ˈfɑloʊ ˌʌp/", "나중에 따로 처리할 후속 작업", REVIEW, E,
        "지금은 넘기고 이어서 처리하기로 한 일. 리뷰에서 합의를 빨리 끝내는 대신 "
        "쓰는 장치인데, 티켓으로 남기지 않으면 그대로 잊혀서 기술 부채가 된다.",
        "Let's merge this and handle the refactor in a follow-up.",
        "이건 합치고 리팩터링은 후속 작업으로 처리합시다.",
    ),
    (
        "blocker", "/ˈblɑkər/", "이게 안 풀리면 진행이 멈추는 것", REVIEW, E,
        "다른 일을 시작하거나 끝낼 수 없게 막고 있는 문제. 우선순위가 높다는 뜻이 아니라 "
        "다른 사람의 시간까지 멈춰 세운다는 점이 핵심이다. 스탠드업에서 이 단어가 "
        "나오면 그 자리에서 해결자를 찾는 게 보통이다.",
        "The missing API key is a blocker for the whole team.",
        "API 키가 없는 게 팀 전체의 블로커입니다.",
    ),
    (
        "WIP", "/ˌdʌblju aɪ ˈpi/", "아직 작업 중", REVIEW, E,
        "Work In Progress 의 줄임말로 아직 완성되지 않았다는 표시. PR 제목 앞에 붙여 "
        "리뷰하지 말라는 신호로 쓴다. GitHub 에서는 draft 상태가 같은 역할을 한다. "
        "철자를 하나씩 읽거나 '윕' 이라고도 읽는다.",
        "Marking this as WIP until the migration script is done.",
        "마이그레이션 스크립트가 끝날 때까지 WIP 으로 두겠습니다.",
    ),
    (
        "ETA", "/ˌi ti ˈeɪ/", "언제쯤 될지", REVIEW, E,
        "Estimated Time of Arrival 의 줄임말로, 언제 끝날 것 같냐고 물을 때 쓴다. "
        "약속 날짜가 아니라 지금 아는 정보로 본 예상이라는 뉘앙스가 있다. "
        "철자를 하나씩 읽는다.",
        "What is the ETA on the fix?",
        "수정은 언제쯤 될까요?",
    ),
    (
        "bikeshedding", "/ˈbaɪkˌʃedɪŋ/", "사소한 것에 논의가 쏠리는 일", REVIEW, N,
        "원자로 설계는 어려워 아무도 말을 못 하는데 자전거 보관소 색깔은 다들 의견을 "
        "낸다는 이야기에서 온 말. 리뷰에서 구조 문제는 지나가고 변수명 논쟁만 길어지는 "
        "상황이 딱 이것이다. 사소한 의견은 nit 으로 표시해두면 이걸 줄일 수 있다.",
        "We are bikeshedding; let's decide on the naming offline.",
        "지금 사소한 데 매달리고 있습니다. 이름은 따로 정합시다.",
    ),
    (
        "rubber duck", "/ˈrʌbər ˌdʌk/", "설명하다 스스로 답을 찾기", REVIEW, N,
        "문제를 소리 내어 설명하다 보면 스스로 원인을 깨닫게 되는 현상. 책상 위 "
        "고무 오리에게 코드를 설명한다는 이야기에서 왔다. 남에게 묻기 전에 "
        "글로 정리해보라는 조언이 여기서 나온다.",
        "I figured it out while rubber ducking with a teammate.",
        "팀원에게 설명하다가 원인을 알아냈습니다.",
    ),
    (
        "pair programming", "/ˈper ˌproʊɡræmɪŋ/", "둘이 한 화면을 보며 짜기", REVIEW, N,
        "두 사람이 하나의 코드를 함께 작성하는 방식. 한 명이 치고 한 명이 방향을 보는 "
        "식으로 역할을 나눈다. 속도는 느려 보여도 리뷰와 지식 전달이 동시에 일어나서 "
        "새로 온 사람을 붙일 때 특히 효과가 크다.",
        "Let's pair on this; the legacy part is hard to navigate alone.",
        "이건 같이 봅시다. 레거시 부분은 혼자 보기 어렵습니다.",
    ),
    (
        "onboarding", "/ˈɑnˌbɔrdɪŋ/", "새로 온 사람을 적응시키는 과정", REVIEW, E,
        "새 팀원이 환경을 갖추고 첫 작업을 낼 때까지 돕는 과정. 문서가 낡아 있으면 "
        "그걸 고치는 것을 첫 작업으로 주는 팀이 많은데, 새 사람만이 무엇이 안 적혀 "
        "있는지 알아볼 수 있기 때문이다.",
        "The onboarding doc is out of date; the setup step no longer works.",
        "온보딩 문서가 낡았습니다. 설치 단계가 더 이상 동작하지 않습니다.",
    ),
    (
        "handoff", "/ˈhændɔf/", "다음 사람에게 넘기기", REVIEW, N,
        "작업이나 당번을 다른 사람에게 넘기는 것. 코드만 넘기면 부족하고 어디까지 "
        "확인했는지, 무엇이 아직 확실치 않은지를 같이 넘겨야 한다. 온콜 교대와 "
        "휴가 전 인수인계에서 가장 많이 쓴다.",
        "Write a short handoff note before you go on leave.",
        "휴가 가기 전에 짧은 인수인계 메모를 남겨주세요.",
    ),
    (
        "stakeholder", "/ˈsteɪkˌhoʊldər/", "결과에 이해관계가 걸린 사람", REVIEW, N,
        "그 일의 결과에 영향을 받거나 결정 권한이 있는 사람들. 상급자만 뜻하는 게 "
        "아니라 그 기능을 쓰는 다른 팀도 포함된다. 누가 이해관계자인지 미리 "
        "찾아두지 않으면 다 만든 뒤에 반대가 나온다.",
        "We should loop in the support team; they are stakeholders here.",
        "지원팀도 이해관계자니 논의에 넣어야 합니다.",
    ),
    (
        "action item", "/ˈækʃən ˌaɪtəm/", "회의에서 정해진 할 일", REVIEW, E,
        "논의 끝에 누가 언제까지 무엇을 할지 정한 항목. 담당자가 정해지지 않은 "
        "액션 아이템은 아무도 하지 않는다는 것이 회의에서 반복되는 교훈이다.",
        "Let's capture the action items before we end the call.",
        "통화를 마치기 전에 액션 아이템을 정리합시다.",
    ),
    (
        "spec", "/spek/", "만들 것을 미리 정해둔 문서", REVIEW, E,
        "무엇을 어떻게 만들지 미리 적어둔 명세. specification 의 줄임말이다. "
        "코드보다 앞서 합의를 만드는 게 목적이라, 다 만든 뒤에 쓰는 문서는 "
        "명세가 아니라 설명서에 가깝다.",
        "The behavior does not match the spec; which one is wrong?",
        "동작이 명세와 다릅니다. 어느 쪽이 잘못된 건가요?",
    ),
    (
        "design doc", "/dɪˈzaɪn ˌdɑk/", "어떻게 만들지 정리한 설계 문서", REVIEW, N,
        "코드를 쓰기 전에 접근 방식과 대안, 고른 이유를 적어 리뷰받는 문서. 화면 "
        "디자인 얘기가 아니라 시스템 설계 얘기다. 여기서 반대 의견이 나오는 편이 "
        "다 만든 뒤 갈아엎는 것보다 훨씬 싸다.",
        "Write a short design doc before starting the migration.",
        "마이그레이션 시작 전에 짧은 설계 문서를 써주세요.",
    ),
    (
        "RFC", "/ˌɑr ef ˈsi/", "의견을 구하는 제안서", REVIEW, N,
        "Request For Comments 의 줄임말로, 결정 전에 제안을 공개하고 의견을 받는 문서. "
        "인터넷 표준 문서 이름에서 왔고 지금은 사내 제안에도 널리 쓴다. "
        "이미 정해놓고 형식적으로 돌리면 신뢰를 잃는다.",
        "I posted an RFC for the new auth flow; comments welcome.",
        "새 인증 흐름에 대한 RFC 를 올렸습니다. 의견 주세요.",
    ),
    (
        "MVP", "/ˌem vi ˈpi/", "가치를 확인할 최소한의 결과물", REVIEW, N,
        "Minimum Viable Product 의 줄임말. 기능을 덜 만든 반쪽짜리가 아니라, "
        "이 방향이 맞는지 확인할 수 있는 가장 작은 완성품을 뜻한다. "
        "확인할 질문이 없으면 MVP 가 아니라 그냥 미완성이다.",
        "Let's ship an MVP first and see if anyone uses it.",
        "일단 MVP 를 내보내고 실제로 쓰는지 봅시다.",
    ),
    (
        "dogfooding", "/ˈdɔɡˌfudɪŋ/", "우리가 만든 걸 우리가 먼저 쓰기", REVIEW, N,
        "자기 팀이 만든 제품을 실제 업무에서 직접 써보는 것. 사용자가 겪을 불편을 "
        "가장 빨리 발견하는 방법이다. 사내 사용 환경이 실제 사용자와 너무 다르면 "
        "오히려 문제를 못 볼 수도 있다.",
        "We have been dogfooding the new dashboard for two weeks.",
        "새 대시보드를 2주째 내부에서 직접 쓰고 있습니다.",
    ),
    (
        "definition of done", "/ˌdefɪˈnɪʃn əv ˌdʌn/", "무엇까지 해야 끝인지의 기준", REVIEW, N,
        "어떤 작업을 완료로 부를 수 있는 조건을 팀이 미리 정해둔 것. 테스트, 문서, "
        "배포까지 포함할지 정해두지 않으면 사람마다 완료의 뜻이 달라진다. "
        "'거의 다 됐어요' 가 반복되는 팀은 대개 이 기준이 없다.",
        "By our definition of done, it is not done until the docs are updated.",
        "우리 완료 기준으로는 문서가 갱신돼야 끝난 겁니다.",
    ),
    (
        "story point", "/ˈstɔri ˌpɔɪnt/", "일의 크기를 나타내는 상대 수치", REVIEW, N,
        "작업이 얼마나 큰지를 시간 대신 상대적인 숫자로 매기는 방식. 사람마다 속도가 "
        "달라서 시간 대신 크기를 재자는 취지인데, 포인트를 시간으로 환산해 관리하면 "
        "원래 취지가 사라진다.",
        "We estimated that ticket at five story points.",
        "그 티켓은 5 포인트로 추정했습니다.",
    ),
    (
        "velocity", "/vəˈlɑsəti/", "한 주기에 처리한 작업량", REVIEW, N,
        "한 스프린트에 팀이 실제로 끝낸 작업 크기의 합. 다음 계획을 세우는 참고값이지 "
        "성과 지표가 아니다. 평가에 쓰기 시작하면 추정치가 부풀어 계획 도구로서의 "
        "쓸모가 없어진다.",
        "Our velocity dropped because two people were on-call.",
        "두 명이 온콜이라 이번 주기 처리량이 줄었습니다.",
    ),
    (
        "code freeze", "/ˈkoʊd ˌfriz/", "당분간 변경을 막는 기간", REVIEW, N,
        "릴리스 직전이나 연휴처럼 위험한 시기에 새 변경을 넣지 않기로 한 기간. "
        "일을 멈추는 게 아니라 합치는 것만 미룬다. 긴급 수정은 예외로 두되 "
        "누가 승인하는지 미리 정해둬야 한다.",
        "We are in a code freeze until the release goes out.",
        "릴리스가 나갈 때까지 코드 프리즈 기간입니다.",
    ),
    (
        "kickoff", "/ˈkɪkɔf/", "일을 시작하며 맞추는 자리", REVIEW, E,
        "프로젝트를 시작하면서 목표와 역할, 일정 등을 함께 맞추는 첫 회의. "
        "여기서 정해지지 않은 것은 나중에 훨씬 비싼 논쟁이 된다.",
        "The kickoff is on Monday; please read the spec beforehand.",
        "킥오프는 월요일입니다. 미리 명세를 읽어와 주세요.",
    ),
    (
        "readability", "/ˌridəˈbɪləti/", "남이 읽고 이해하기 쉬운 정도", REVIEW, E,
        "코드를 처음 보는 사람이 얼마나 빨리 이해하는지. 코드는 쓰는 시간보다 읽히는 "
        "시간이 훨씬 길기 때문에 짧은 코드보다 읽히는 코드가 낫다는 말이 여기서 나온다. "
        "리뷰에서 가장 자주 거론되는 기준이다.",
        "The logic is correct, but readability suffers from the nested ternaries.",
        "로직은 맞지만 삼항 연산자가 중첩돼 읽기 어렵습니다.",
    ),
    (
        "maintainability", "/meɪnˌteɪnəˈbɪləti/", "나중에 고치기 쉬운 정도", REVIEW, N,
        "시간이 지나 다른 사람이 이 코드를 바꾸기 얼마나 쉬운지. 지금 동작하는지가 "
        "아니라 6개월 뒤 바꿀 수 있는지를 본다. 지금 당장은 아무 차이가 없어서 "
        "우선순위에서 계속 밀리는 것이 특징이다.",
        "The clever one-liner hurts maintainability.",
        "그 기발한 한 줄짜리 코드는 유지보수를 어렵게 만듭니다.",
    ),
    (
        "legacy code", "/ˈleɡəsi ˌkoʊd/", "손대기 겁나는 오래된 코드", REVIEW, N,
        "오래돼서 아무도 전체를 이해하지 못하는 코드. 나이가 아니라 테스트가 없어서 "
        "고쳤을 때 뭐가 깨지는지 알 수 없는 상태를 가리키는 정의가 널리 쓰인다. "
        "그래서 레거시를 고치는 첫 단계는 대개 테스트를 붙이는 일이다.",
        "We cannot refactor that legacy code without tests first.",
        "테스트 없이는 그 레거시 코드를 리팩터링할 수 없습니다.",
    ),
    (
        "premature optimization", "/ˌpriməˈtʃʊr ˌɑptɪməˌzeɪʃn/", "재보지도 않고 하는 최적화", REVIEW, N,
        "실제로 느린지 측정하지 않은 채 미리 빠르게 만들려다 코드만 복잡해지는 것. "
        "최적화를 하지 말라는 뜻이 아니라 어디가 느린지 먼저 재라는 뜻이다. "
        "대개 병목은 예상과 다른 곳에 있다.",
        "That is premature optimization; profile it before rewriting.",
        "그건 성급한 최적화입니다. 다시 짜기 전에 프로파일링부터 하세요.",
    ),
    (
        "DRY", "/draɪ/", "같은 지식을 두 곳에 두지 않기", REVIEW, N,
        "Don't Repeat Yourself 의 줄임말로 '드라이' 라고 읽는다. 코드 모양이 같으면 "
        "무조건 합치라는 뜻이 아니라, 같은 규칙이 여러 곳에 흩어져 한 곳만 고치면 "
        "어긋나는 상황을 피하라는 뜻이다. 우연히 비슷한 코드를 억지로 합치면 "
        "오히려 결합도만 올라간다.",
        "These two blocks look similar but change for different reasons, so leave them.",
        "두 블록이 비슷해 보여도 바뀌는 이유가 달라서 그대로 두는 게 낫습니다.",
    ),
    (
        "YAGNI", "/ˈjæɡni/", "필요해질 때 만들기", REVIEW, N,
        "You Aren't Gonna Need It 의 줄임말. 나중에 필요할 것 같아 미리 만들어둔 기능은 "
        "대부분 쓰이지 않고 유지보수 부담만 남는다는 경험칙이다. 확장 지점을 미리 "
        "파두는 설계에 대한 반론으로 자주 나온다.",
        "Let's not add that config option yet; YAGNI.",
        "그 설정 옵션은 아직 넣지 맙시다. 필요해지면 그때 하죠.",
    ),
    # ---------- API / 네트워크 ----------
    (
        "status code", "/ˈsteɪtəs ˌkoʊd/", "요청 결과를 알리는 세 자리 숫자", API, E,
        "서버가 응답 맨 앞에 붙여 보내는 세 자리 숫자. 앞자리로 성격이 갈려서 "
        "2로 시작하면 성공, 4는 요청한 쪽 잘못, 5는 서버 잘못이다. "
        "본문에 에러 메시지를 담고도 200 을 돌려주는 API 가 흔한데, "
        "그러면 클라이언트가 실패를 알아채지 못한다.",
        "The endpoint returns a 200 status code even when the request fails.",
        "이 엔드포인트는 요청이 실패해도 200 을 돌려줍니다.",
    ),
    (
        "header", "/ˈhedər/", "본문과 별도로 붙는 부가 정보", API, E,
        "요청과 응답에 본문과 따로 붙어 다니는 이름과 값의 목록. 인증 토큰, 데이터 형식, "
        "캐시 지시 같은 것이 여기 실린다. 이름의 대소문자는 구별하지 않지만 "
        "값은 구별한다는 점이 자주 헷갈리는 부분이다.",
        "Make sure the Authorization header is present on every request.",
        "모든 요청에 Authorization 헤더가 들어가는지 확인하세요.",
    ),
    (
        "cookie", "/ˈkʊki/", "브라우저가 대신 들고 다니는 작은 값", API, N,
        "서버가 브라우저에 저장해두고 이후 요청마다 자동으로 딸려 보내게 하는 값. "
        "자동으로 붙는다는 점이 편하면서 동시에 CSRF 공격이 가능한 이유다. "
        "HttpOnly 를 붙이면 스크립트가 읽지 못해 탈취 위험이 줄어든다.",
        "The session cookie is not set because the domain does not match.",
        "도메인이 맞지 않아 세션 쿠키가 설정되지 않았습니다.",
    ),
    (
        "CORS", "/kɔrz/", "다른 출처 요청을 허용하는 규칙", API, H,
        "브라우저가 다른 주소로 보내는 요청을 막아두고, 서버가 허용한다고 응답 헤더로 "
        "밝힐 때만 결과를 읽게 해주는 장치. 요청 자체는 서버에 도착하는 경우가 많아서 "
        "'요청이 막혔다' 는 표현은 정확하지 않다. 브라우저에서만 적용되므로 "
        "curl 이나 서버끼리의 호출은 아무 문제가 없다. '코어즈' 로 읽는다.",
        "The request fails with a CORS error even though the server returns 200.",
        "서버는 200 을 돌려주는데도 CORS 에러로 실패합니다.",
    ),
    (
        "preflight", "/ˈpriflaɪt/", "본 요청 전에 미리 묻는 확인 요청", API, H,
        "브라우저가 위험할 수 있는 요청을 보내기 전에 OPTIONS 로 먼저 허락을 묻는 것. "
        "그래서 네트워크 탭에 요청이 두 번 찍힌다. 이 확인 요청이 실패하면 본 요청은 "
        "아예 보내지지 않고, 서버 로그에도 남지 않아 원인 찾기가 어렵다.",
        "The preflight request is failing, so the actual POST never goes out.",
        "프리플라이트 요청이 실패해서 실제 POST 는 나가지도 않습니다.",
    ),
    (
        "token", "/ˈtoʊkən/", "신분을 증명하는 문자열", API, E,
        "로그인 뒤 발급받아 이후 요청에 붙이는 증명 문자열. 비밀번호와 달리 "
        "유효 기간이 있고 필요하면 서버가 무효로 만들 수 있다. 유출되면 그 자체로 "
        "본인 행세가 가능하므로 주소창이나 로그에 남기면 안 된다.",
        "The token expired; refresh it and retry the request.",
        "토큰이 만료됐습니다. 갱신하고 요청을 다시 보내세요.",
    ),
    (
        "bearer", "/ˈberər/", "가진 사람이 곧 주인인 방식", API, N,
        "Authorization 헤더에 'Bearer 토큰' 형태로 보내는 방식. bearer 는 소지자라는 "
        "뜻이고, 이름 그대로 그 문자열을 가진 사람이면 누구든 통과한다는 의미다. "
        "추가 확인이 없다는 뜻이라 유출에 특히 약하다.",
        "Send the token as a Bearer token in the Authorization header.",
        "토큰을 Authorization 헤더에 Bearer 방식으로 보내세요.",
    ),
    (
        "JWT", "/ˈdʒɑt/", "서명이 붙은 자체 완결 토큰", API, H,
        "사용자 정보와 서명을 함께 담아 서버가 따로 저장하지 않아도 검증되는 토큰. "
        "암호화가 아니라 서명이라서 내용은 누구나 열어볼 수 있다. 비밀을 담으면 안 된다. "
        "서버에 저장하지 않는 만큼 발급된 토큰을 즉시 무효화하기 어렵다. "
        "보통 '조트' 라고 읽지만 철자 그대로 읽는 사람도 많다.",
        "Do not put personal data in the JWT payload; it is only encoded, not encrypted.",
        "JWT 페이로드에 개인정보를 넣지 마세요. 암호화가 아니라 인코딩일 뿐입니다.",
    ),
    (
        "OAuth", "/ˈoʊɔθ/", "비밀번호 없이 권한만 넘겨주는 방식", API, H,
        "다른 서비스에 내 비밀번호를 주지 않고 특정 권한만 허용해주는 표준. "
        "'구글로 로그인' 뒤에 있는 것이 이것이다. 원래는 인증이 아니라 권한 위임을 "
        "위한 규격이라, 로그인 용도로 쓰려면 그 위에 얹은 OpenID Connect 를 쓴다. "
        "'오쓰' 로 읽는다.",
        "We use OAuth so the app never sees the user's password.",
        "앱이 사용자 비밀번호를 보지 않도록 OAuth 를 씁니다.",
    ),
    (
        "refresh token", "/rɪˈfreʃ ˌtoʊkən/", "새 접근 토큰을 받아오는 열쇠", API, N,
        "수명이 짧은 접근 토큰이 만료됐을 때 다시 로그인하지 않고 새 토큰을 받는 데 "
        "쓰는 토큰. 오래 살기 때문에 유출되면 피해가 크고, 그래서 접근 토큰보다 "
        "훨씬 조심해서 보관한다.",
        "Store the refresh token securely; it lives much longer.",
        "리프레시 토큰은 수명이 훨씬 기니 안전하게 보관하세요.",
    ),
    (
        "session", "/ˈseʃən/", "서버가 기억하는 로그인 상태", API, N,
        "누가 로그인했는지를 서버 쪽에 저장해두고 열쇠만 쿠키로 주는 방식. "
        "서버가 상태를 갖고 있어서 강제 로그아웃이 쉽지만, 서버가 여러 대면 "
        "그 저장소를 공유해야 한다. 토큰 방식과의 진짜 차이가 여기에 있다.",
        "Sessions are stored in Redis so any server can handle the request.",
        "어느 서버가 받아도 되도록 세션을 Redis 에 저장합니다.",
    ),
    (
        "REST", "/rest/", "자원을 주소로 다루는 설계 방식", API, N,
        "데이터를 자원으로 보고 주소로 지목한 뒤 HTTP 메서드로 무엇을 할지 나타내는 "
        "설계 스타일. 정해진 규격이 아니라 원칙 모음이라서 'RESTful' 의 기준은 "
        "팀마다 조금씩 다르다. 실무에서는 대개 주소를 명사로 짓고 동사는 "
        "메서드로 표현한다는 정도로 통한다.",
        "Our REST API exposes users as a collection resource.",
        "우리 REST API 는 사용자를 컬렉션 자원으로 제공합니다.",
    ),
    (
        "GraphQL", "/ˈɡræf ˌkju el/", "필요한 것만 골라 받는 질의 방식", API, H,
        "클라이언트가 필요한 필드를 직접 적어 요청하는 API 방식. 화면마다 엔드포인트를 "
        "새로 만들지 않아도 되지만, 무거운 질의가 들어올 수 있어 깊이나 비용 제한이 "
        "필요하다. 대개 주소 하나로 POST 만 쓰기 때문에 HTTP 캐시를 쓰기 어렵다.",
        "The mobile app moved to GraphQL to avoid over-fetching.",
        "필요 이상으로 데이터를 받는 걸 피하려고 모바일 앱을 GraphQL 로 옮겼습니다.",
    ),
    (
        "rate limit", "/ˈreɪt ˌlɪmɪt/", "정해진 시간에 허용하는 호출 횟수", API, N,
        "일정 시간 안에 보낼 수 있는 요청 수의 상한. 넘으면 보통 429 를 돌려주고 "
        "언제 다시 시도하라는 헤더를 함께 준다. 실패했다고 곧바로 다시 던지면 "
        "한도가 더 오래 풀리지 않는다.",
        "We are hitting the rate limit; back off and retry after a minute.",
        "호출 한도에 걸렸습니다. 잠시 쉬었다가 1분 뒤 다시 시도하세요.",
    ),
    (
        "backoff", "/ˈbækɔf/", "재시도 간격을 점점 늘리기", API, N,
        "실패했을 때 곧바로 다시 보내지 않고 대기 시간을 점점 늘려가며 재시도하는 것. "
        "모두가 같은 간격으로 재시도하면 회복 중인 서버를 다시 무너뜨리기 때문에, "
        "간격에 약간의 무작위를 섞는 방식이 함께 쓰인다.",
        "Add exponential backoff so we do not hammer the service while it recovers.",
        "회복 중인 서비스를 계속 두드리지 않게 지수 백오프를 넣으세요.",
    ),
    (
        "retry", "/ˈritraɪ/", "실패한 요청을 다시 보내기", API, E,
        "실패한 요청을 자동으로 다시 시도하는 것. 문제는 응답을 못 받았을 때 "
        "서버에서 실제로 처리됐는지 알 수 없다는 점이다. 그래서 재시도는 "
        "같은 요청을 여러 번 해도 안전한 작업에만 붙여야 한다.",
        "Only retry requests that are safe to repeat.",
        "여러 번 보내도 안전한 요청에만 재시도를 붙이세요.",
    ),
    (
        "timeout", "/ˈtaɪmaʊt/", "정해둔 시간을 넘겨 끊기", API, E,
        "정해진 시간 안에 응답이 오지 않으면 기다리기를 포기하는 것. 끊긴 쪽에서는 "
        "실패로 보이지만 상대 서버에서는 그대로 처리가 진행 중일 수 있다. "
        "타임아웃을 설정하지 않으면 응답이 없는 상대 하나가 우리 서버 전체를 "
        "붙잡아둘 수 있다.",
        "Set a sane timeout; the default is often no timeout at all.",
        "적절한 타임아웃을 설정하세요. 기본값이 아예 없는 경우가 많습니다.",
    ),
    (
        "circuit breaker", "/ˈsɜrkɪt ˌbreɪkər/", "고장난 곳으로 가는 길을 잠시 끊기", API, H,
        "계속 실패하는 상대에게 요청을 잠시 아예 보내지 않고 즉시 실패로 돌리는 장치. "
        "차단기가 내려가는 것에 빗댄 이름이다. 회복 중인 서비스에 부하를 주지 않으면서 "
        "우리 쪽 스레드가 대기로 묶이는 것도 막는다.",
        "The circuit breaker opened after five consecutive failures.",
        "다섯 번 연속 실패한 뒤 서킷 브레이커가 열렸습니다.",
    ),
    (
        "webhook", "/ˈwebhʊk/", "일이 생기면 서버가 먼저 알려주기", API, N,
        "상태를 물어보러 가는 대신, 사건이 생기면 상대가 내 주소로 요청을 보내주는 방식. "
        "받는 쪽이 서버여야 하고 인터넷에서 접근 가능해야 한다. 같은 알림이 두 번 올 수 "
        "있어서 받는 쪽에서 중복 처리를 막는 장치가 필요하다.",
        "The payment provider sends a webhook when the charge succeeds.",
        "결제 업체가 결제 성공 시 웹훅을 보냅니다.",
    ),
    (
        "polling", "/ˈpoʊlɪŋ/", "주기적으로 계속 물어보기", API, N,
        "변화가 있는지 일정 간격으로 반복해서 물어보는 방식. 구현이 단순하지만 "
        "대부분의 요청이 헛걸음이라 낭비가 크다. 간격을 줄이면 실시간에 가까워지는 "
        "대신 서버 부하가 그만큼 늘어난다.",
        "Polling every second is wasteful; use a webhook instead.",
        "1초마다 폴링하는 건 낭비입니다. 웹훅을 쓰세요.",
    ),
    (
        "WebSocket", "/ˈwebˌsɑkɪt/", "끊지 않고 양방향으로 주고받는 연결", API, N,
        "한 번 연결하면 양쪽이 언제든 먼저 말을 걸 수 있는 통신 방식. HTTP 로 시작해 "
        "중간에 방식을 바꾸는 형태다. 연결을 계속 붙잡고 있어서 서버 자원을 쓰고, "
        "끊겼을 때 다시 붙는 처리를 직접 만들어야 한다.",
        "Chat uses a WebSocket so the server can push new messages.",
        "서버가 새 메시지를 보내줄 수 있게 채팅은 웹소켓을 씁니다.",
    ),
    (
        "endpoint versioning", "/ˈendpɔɪnt ˌvɜrʒənɪŋ/", "API 버전을 나눠 제공하기", API, N,
        "기존 사용자를 깨뜨리지 않으려고 API 를 버전별로 나눠 제공하는 것. "
        "주소에 v1 을 넣는 방식이 가장 흔하다. 버전을 늘리는 건 쉽지만 옛 버전을 "
        "언제 끄느냐가 진짜 어려운 부분이라, 종료 일정을 함께 공지하는 게 원칙이다.",
        "We keep v1 alive for six months after v2 ships.",
        "v2 출시 후 6개월 동안 v1 을 유지합니다.",
    ),
    (
        "breaking change", "/ˈbreɪkɪŋ ˌtʃeɪndʒ/", "쓰던 쪽이 깨지는 변경", API, N,
        "기존 사용자가 코드를 고쳐야만 계속 쓸 수 있게 만드는 변경. 필드를 지우거나 "
        "이름을 바꾸거나 필수 항목을 추가하는 것이 여기 해당한다. 응답에 필드를 "
        "더하는 것은 보통 안전하지만, 없는 필드를 오류로 처리하는 클라이언트가 있으면 "
        "그것도 깨질 수 있다.",
        "Renaming that field is a breaking change for every client.",
        "그 필드 이름을 바꾸는 건 모든 클라이언트에 호환이 깨지는 변경입니다.",
    ),
    (
        "payload size", "/ˈpeɪloʊd ˌsaɪz/", "본문이 차지하는 크기", API, E,
        "요청이나 응답 본문의 크기. 서버나 중간 장비마다 상한이 있어서 넘으면 "
        "413 으로 거절된다. 파일 업로드가 로컬에서는 되는데 배포하면 실패하는 "
        "경우의 흔한 원인이다.",
        "The upload fails because the payload size exceeds the proxy limit.",
        "본문 크기가 프록시 제한을 넘어 업로드가 실패합니다.",
    ),
    (
        "content type", "/ˈkɑntent ˌtaɪp/", "본문이 어떤 형식인지 알리는 표시", API, E,
        "본문의 형식을 알려주는 헤더. application/json 처럼 적는다. 실제 본문 형식과 "
        "다르게 적으면 서버가 파싱에 실패해 400 이 나는데, 에러 메시지가 불친절해서 "
        "원인을 찾기 어렵다. 폼 전송과 JSON 전송을 헷갈릴 때 자주 겪는다.",
        "Set the content type to application/json or the body will not parse.",
        "content type 을 application/json 으로 설정하지 않으면 본문이 파싱되지 않습니다.",
    ),
    (
        "query string", "/ˈkwɪri ˌstrɪŋ/", "주소 뒤 물음표에 붙는 값들", API, E,
        "주소 뒤에 ?key=value 형태로 붙이는 값. 주소의 일부라서 로그와 브라우저 기록에 "
        "그대로 남는다. 그래서 비밀번호나 토큰을 여기에 실으면 안 된다. "
        "특수문자는 인코딩해야 한다.",
        "Pass the filter as a query string parameter instead of a header.",
        "필터는 헤더 말고 쿼리 스트링 파라미터로 넘기세요.",
    ),
    (
        "path parameter", "/ˈpæθ pəˌræmɪtər/", "주소 안에 박히는 값", API, E,
        "/users/42 의 42 처럼 주소 경로 자체에 들어가는 값. 무엇을 가리키는지를 "
        "나타낼 때 쓰고, 어떻게 걸러낼지는 쿼리 스트링에 두는 것이 관례다. "
        "값에 슬래시가 들어가면 경로가 깨지므로 인코딩이 필요하다.",
        "The user id is a path parameter, not a query parameter.",
        "사용자 아이디는 쿼리 파라미터가 아니라 경로 파라미터입니다.",
    ),
    (
        "request body", "/rɪˈkwest ˌbɑdi/", "요청에 실어 보내는 본문", API, E,
        "요청과 함께 보내는 데이터 덩어리. GET 요청에는 본문을 넣어도 중간 장비나 "
        "라이브러리가 조용히 버리는 경우가 있어 실질적으로 쓰지 않는다. "
        "검색 조건이 길어 GET 에 담기 어려우면 POST 로 바꾸는 것이 보통이다.",
        "Send the filters in the request body since the query string is too long.",
        "쿼리 스트링이 너무 길어서 필터는 요청 본문으로 보내세요.",
    ),
    (
        "gateway", "/ˈɡeɪtweɪ/", "요청을 받아 안쪽으로 넘기는 입구", API, N,
        "여러 내부 서비스 앞에 서서 요청을 받아 알맞은 곳으로 넘겨주는 지점. "
        "인증, 호출 제한, 로깅처럼 모든 요청에 공통인 일을 여기서 처리한다. "
        "여기가 죽으면 뒤가 멀쩡해도 전부 접속 불가가 된다.",
        "Auth is handled at the gateway, not in each service.",
        "인증은 각 서비스가 아니라 게이트웨이에서 처리합니다.",
    ),
    (
        "TLS", "/ˌti el ˈes/", "오가는 내용을 암호화하는 규약", API, N,
        "주고받는 내용을 암호화해 중간에서 읽거나 바꾸지 못하게 하는 규약. "
        "HTTPS 의 S 는 Secure 를 뜻하고, 그 Secure 를 실제로 맡는 것이 TLS 다. "
        "예전 이름인 SSL 이 아직 습관적으로 쓰이지만 "
        "지금 실제로 쓰이는 것은 TLS 다.",
        "TLS termination happens at the load balancer.",
        "TLS 종료는 로드 밸런서에서 처리합니다.",
    ),
    (
        "certificate", "/sərˈtɪfɪkət/", "이 서버가 맞다는 증명서", API, N,
        "이 도메인의 서버가 맞다고 제3자가 보증해주는 파일. 유효 기간이 있어서 "
        "갱신을 놓치면 어느 날 갑자기 전체 접속이 막힌다. 브라우저 경고의 "
        "상당수는 만료나 도메인 불일치가 원인이다.",
        "The certificate expired last night, which is why every request fails.",
        "어젯밤 인증서가 만료돼서 모든 요청이 실패하는 겁니다.",
    ),
    (
        "API key", "/ˌeɪ pi ˈaɪ ˌki/", "호출자를 구분하는 발급 키", API, E,
        "누가 호출하는지 구분하려고 발급하는 문자열. 사용자를 인증하기보다 "
        "어떤 앱인지 식별하고 사용량을 재는 용도에 가깝다. 프론트엔드 코드에 "
        "넣으면 누구나 볼 수 있으므로 서버에 두어야 한다.",
        "Never ship the API key in client-side code.",
        "API 키를 클라이언트 코드에 넣어 배포하지 마세요.",
    ),
    (
        "scope", "/skoʊp/", "토큰이 할 수 있는 일의 범위", API, N,
        "발급된 권한이 어디까지 미치는지 정해둔 범위. 읽기만 필요한 곳에 "
        "쓰기까지 열어주면 유출됐을 때 피해가 커진다. 필요한 최소한만 요청하는 것이 "
        "원칙이다.",
        "This token only has read scope, so the update fails.",
        "이 토큰은 읽기 권한만 있어서 수정이 실패합니다.",
    ),
    (
        "CSRF", "/ˌsi es ɑr ˈef/", "남의 로그인 상태를 몰래 빌려 쓰는 공격", API, H,
        "사용자가 로그인해둔 상태를 이용해 다른 사이트가 몰래 요청을 보내게 만드는 공격. "
        "쿠키가 자동으로 따라붙기 때문에 가능하다. 토큰을 헤더에 직접 담는 방식은 "
        "자동으로 붙지 않아 이 공격에 덜 노출된다. '씨서프' 라고 읽기도 한다.",
        "Add a CSRF token to every state-changing form.",
        "상태를 바꾸는 폼마다 CSRF 토큰을 넣으세요.",
    ),
    (
        "redirect", "/ˌridəˈrekt/", "다른 주소로 보내기", API, E,
        "요청한 주소 대신 다른 주소로 가라고 응답하는 것. 3으로 시작하는 상태 코드로 "
        "알린다. 301 은 영구라 브라우저가 캐시해버려서 잘못 설정하면 되돌리기 어렵고, "
        "302 는 임시라 매번 다시 물어본다.",
        "The API returns a 301 redirect, and the client is not following it.",
        "API 가 301 리다이렉트를 주는데 클라이언트가 따라가지 않고 있습니다.",
    ),
    (
        "cache", "/kæʃ/", "자주 쓰는 것을 가까이 두기", API, N,
        "느린 곳에서 가져온 것을 빠른 곳에 잠깐 두고 다음부터 그걸 쓰는 것. "
        "원본이 바뀌었는데 캐시가 남아 있으면 옛 값이 계속 나온다. 그래서 언제 버릴지 "
        "정하는 것이 캐시의 절반이다. 발음은 '캐시'로, cash 와 똑같이 읽는다. "
        "'캐치'가 아니다.",
        "Clear the cache and try again.",
        "캐시를 지우고 다시 시도해보세요.",
    ),
    (
        "ETag", "/ˈitæɡ/", "내용이 바뀌었는지 알려주는 표식", API, H,
        "응답 내용마다 붙는 지문 같은 값. 다음 요청에 이 값을 함께 보내면 서버가 "
        "안 바뀌었을 때 본문 없이 304 만 돌려줘서 전송량을 아낀다. 수정 요청에 쓰면 "
        "내가 본 뒤 남이 먼저 고쳤는지 확인하는 용도로도 쓸 수 있다.",
        "The server returns 304 when the ETag still matches.",
        "ETag 가 그대로면 서버가 304 를 돌려줍니다.",
    ),
    (
        "stateless", "/ˈsteɪtləs/", "이전 요청을 기억하지 않는", API, N,
        "서버가 요청 사이에 아무것도 기억하지 않는 성질. 각 요청이 필요한 정보를 "
        "다 담고 오기 때문에 어느 서버에 붙어도 같은 결과가 나오고, 그래서 서버를 "
        "늘리기 쉽다. 데이터를 저장하지 않는다는 뜻은 아니다.",
        "Keep the service stateless so we can scale it horizontally.",
        "수평 확장이 가능하도록 서비스를 무상태로 유지하세요.",
    ),
    (
        "cursor", "/ˈkɜrsər/", "다음 페이지를 가리키는 위치 표시", API, N,
        "목록을 나눠 줄 때 다음이 어디서부터인지 알려주는 표식. 몇 번째 페이지라고 "
        "세는 방식은 그 사이에 데이터가 추가되면 항목이 밀려 중복되거나 빠지는데, "
        "커서는 위치를 직접 가리키므로 그 문제가 없다.",
        "Pass the cursor from the previous response to get the next page.",
        "다음 페이지를 받으려면 이전 응답의 커서를 넘기세요.",
    ),
    (
        "429", "/ˌfɔr tu ˈnaɪn/", "너무 많이 불렀다는 응답", API, N,
        "정해진 호출 한도를 넘었을 때 돌아오는 상태 코드. 요청이 잘못된 게 아니라 "
        "너무 잦다는 뜻이라, 고칠 것은 내용이 아니라 속도다. 함께 오는 "
        "Retry-After 헤더에 언제 다시 시도하라고 적혀 있는 경우가 많다.",
        "We are getting 429s from the provider during peak hours.",
        "피크 시간대에 업체에서 429 응답이 오고 있습니다.",
    ),
    (
        "401", "/ˌfɔr oʊ ˈwʌn/", "누구인지 모르겠다는 응답", API, N,
        "인증 정보가 없거나 잘못됐을 때 돌아오는 상태 코드. 이름은 Unauthorized 지만 "
        "실제 뜻은 '인증이 안 됐다' 에 가깝다. 로그인은 됐는데 권한이 없는 경우는 "
        "401 이 아니라 403 이다. 이 둘을 뒤바꿔 쓰는 API 가 아주 많다.",
        "You get a 401 when the token is missing or expired.",
        "토큰이 없거나 만료되면 401 이 옵니다.",
    ),
    (
        "403", "/ˌfɔr oʊ ˈθri/", "누군지는 알지만 권한이 없다는 응답", API, N,
        "인증은 됐지만 그 작업을 할 권한이 없을 때 돌아오는 코드. 다시 로그인해도 "
        "해결되지 않는다는 점이 401 과 결정적으로 다르다. 자원의 존재 자체를 숨기려고 "
        "일부러 404 를 돌려주는 설계도 있다.",
        "She is logged in but gets a 403 on the admin page.",
        "로그인은 했는데 관리자 페이지에서 403 이 납니다.",
    ),
    (
        "502", "/ˌfaɪv oʊ ˈtu/", "뒤쪽 서버에서 이상한 답이 왔다는 응답", API, N,
        "앞단 서버가 뒤쪽 서버에 요청을 넘겼는데 제대로 된 응답을 못 받았을 때 나온다. "
        "그래서 대개 앞단이 아니라 뒤쪽 애플리케이션이 죽었거나 재시작 중이라는 신호다. "
        "배포 직후에 잠깐 뜨는 502 는 이 경우가 많다.",
        "We saw 502s for thirty seconds right after the deploy.",
        "배포 직후 30초 동안 502 가 발생했습니다.",
    ),
    (
        "504", "/ˌfaɪv oʊ ˈfɔr/", "뒤쪽 서버가 제때 답하지 않았다는 응답", API, N,
        "앞단 서버가 뒤쪽 응답을 기다리다 시간이 다 돼서 끊었을 때 나온다. "
        "502 와 달리 뒤쪽이 죽은 게 아니라 느린 것이라, 원인은 대개 무거운 쿼리나 "
        "외부 호출 지연이다.",
        "The report endpoint returns 504 because the query takes too long.",
        "쿼리가 너무 오래 걸려서 리포트 엔드포인트가 504 를 냅니다.",
    ),
    (
        "content negotiation", "/ˈkɑntent nɪˌɡoʊʃiˌeɪʃn/", "원하는 형식을 골라 주기", API, H,
        "클라이언트가 Accept 헤더로 원하는 형식을 밝히면 서버가 그에 맞춰 응답 형식을 "
        "고르는 것. JSON 을 기대했는데 HTML 오류 페이지가 오는 상황은 이 협상이 "
        "제대로 되지 않은 경우가 많다.",
        "The server ignored the Accept header and returned HTML.",
        "서버가 Accept 헤더를 무시하고 HTML 을 돌려줬습니다.",
    ),
    (
        "OpenAPI", "/ˈoʊpən ˌeɪ pi ˌaɪ/", "API 생김새를 적어둔 규격 문서", API, N,
        "어떤 주소에 어떤 요청을 보내면 어떤 응답이 오는지를 정해진 형식으로 적은 문서. "
        "이걸로 문서 화면과 클라이언트 코드를 자동으로 만들 수 있다. 예전 이름인 "
        "Swagger 가 아직 도구 이름으로 남아 함께 쓰인다.",
        "Update the OpenAPI spec when you add the new field.",
        "새 필드를 추가하면 OpenAPI 명세도 갱신해주세요.",
    ),
    # ---------- 데이터베이스 ----------
    (
        "schema", "/ˈskimə/", "표의 구조를 정해둔 설계", DB, N,
        "어떤 표에 어떤 칸이 있고 각 칸이 무슨 형식인지 정해둔 구조. 데이터가 아니라 "
        "데이터의 틀이다. 발음은 '스키마'다. 철자만 보고 '셰마' 나 '스케마' 로 읽기 쉬운데, "
        "ch 를 k 소리로 낸다.",
        "The schema change needs a migration before we deploy.",
        "스키마 변경은 배포 전에 마이그레이션이 필요합니다.",
    ),
    (
        "primary key", "/ˈpraɪmeri ˌki/", "행을 하나로 지목하는 값", DB, E,
        "표에서 각 행을 유일하게 가리키는 칸. 값이 겹칠 수 없고 비어 있을 수도 없다. "
        "의미 있는 값을 키로 쓰면 나중에 그 값이 바뀔 때 곤란해져서, 아무 뜻 없는 "
        "번호를 따로 두는 경우가 많다.",
        "Use a surrogate primary key instead of the email address.",
        "이메일 주소 대신 별도의 대리 기본키를 쓰세요.",
    ),
    (
        "foreign key", "/ˈfɔrən ˌki/", "다른 표의 행을 가리키는 값", DB, N,
        "다른 표의 기본키를 가리켜 두 표를 연결하는 칸. 단순히 값을 담는 게 아니라 "
        "가리키는 대상이 실제로 있어야 한다는 규칙까지 붙는다. 그래서 참조된 행은 "
        "그냥 지워지지 않고 오류가 난다.",
        "The delete failed because a foreign key still references that row.",
        "그 행을 아직 외래키가 참조하고 있어서 삭제가 실패했습니다.",
    ),
    (
        "join", "/dʒɔɪn/", "여러 표를 이어 붙여 보기", DB, N,
        "두 표를 공통된 값을 기준으로 이어 하나의 결과로 보는 것. 조건을 빠뜨리면 "
        "모든 조합이 만들어져 결과가 폭발한다. 표를 나눠 저장한 대가를 조회할 때 "
        "치르는 셈이라, 나누는 설계와 성능은 늘 맞바꿈이다.",
        "This join is missing a condition and returns every combination.",
        "이 조인은 조건이 빠져서 모든 조합을 돌려주고 있습니다.",
    ),
    (
        "left join", "/ˈleft ˌdʒɔɪn/", "왼쪽은 남기고 이어 붙이기", DB, N,
        "짝이 없어도 왼쪽 표의 행은 모두 남기는 조인. 짝이 없는 자리는 빈 값으로 "
        "채워진다. 여기에 WHERE 로 오른쪽 칸 조건을 걸면 빈 값이 걸러져 결국 "
        "일반 조인과 같아진다. 이 실수가 아주 흔하다.",
        "That where clause turns your left join into an inner join.",
        "그 where 조건 때문에 left join 이 사실상 inner join 이 됐습니다.",
    ),
    (
        "normalization", "/ˌnɔrmələˈzeɪʃn/", "중복 없게 표를 쪼개기", DB, H,
        "같은 정보가 여러 곳에 중복되지 않도록 표를 나누는 설계 원칙. 한 곳만 고치면 "
        "되니 데이터가 어긋날 일이 줄어든다. 대신 조회할 때 조인이 늘어난다. "
        "정처기에서 1정규형부터 단계별로 자주 나온다.",
        "The table is not normalized; the customer name is duplicated everywhere.",
        "이 테이블은 정규화가 안 돼서 고객 이름이 여기저기 중복돼 있습니다.",
    ),
    (
        "denormalization", "/diˌnɔrmələˈzeɪʃn/", "일부러 중복을 두어 빠르게 하기", DB, H,
        "조회 속도를 위해 일부러 값을 복사해두는 것. 정규화를 몰라서 하는 게 아니라 "
        "알고 되돌리는 선택이다. 대신 원본이 바뀔 때 복사본을 같이 갱신하지 않으면 "
        "값이 어긋난다는 부담을 떠안는다.",
        "We denormalized the counter because the join was too slow.",
        "조인이 너무 느려서 카운터를 비정규화했습니다.",
    ),
    (
        "N+1", "/ˌen plʌs ˈwʌn/", "목록 한 번에 상세를 하나씩 또 조회", DB, H,
        "목록을 한 번 가져온 뒤 각 행마다 관련 데이터를 또 조회해서 쿼리가 행 수만큼 "
        "늘어나는 문제. 코드에는 반복문 한 줄뿐이라 눈에 잘 띄지 않고, 데이터가 적은 "
        "개발 환경에서는 멀쩡하다가 운영에서 터진다. ORM 을 쓸 때 특히 자주 나온다.",
        "This page fires an N+1 query; use eager loading instead.",
        "이 페이지에서 N+1 쿼리가 발생합니다. 즉시 로딩으로 바꾸세요.",
    ),
    (
        "explain", "/ɪkˈspleɪn/", "쿼리를 어떻게 처리할지 보여주기", DB, N,
        "데이터베이스가 이 쿼리를 어떤 순서로 어떻게 처리할 계획인지 보여주는 명령. "
        "느린 쿼리를 고칠 때 추측 대신 근거를 준다. 실제로 실행한 결과가 아니라 "
        "계획이라서, 예상 행 수가 실제와 크게 다를 수 있다.",
        "Run explain on that query before you add another index.",
        "인덱스를 더 추가하기 전에 그 쿼리에 explain 을 돌려보세요.",
    ),
    (
        "full scan", "/ˈfʊl ˌskæn/", "표 전체를 처음부터 훑기", DB, N,
        "인덱스를 쓰지 못해 표의 모든 행을 하나씩 확인하는 것. 행이 적을 때는 오히려 "
        "빠를 수 있어서 무조건 나쁜 것은 아니다. 조건 칸에 함수를 씌우면 인덱스를 "
        "못 쓰게 되어 전체 스캔으로 떨어지는 경우가 흔하다.",
        "Wrapping the column in a function forces a full scan.",
        "칼럼을 함수로 감싸면 전체 스캔이 됩니다.",
    ),
    (
        "connection pool", "/kəˈnekʃən ˌpul/", "미리 열어두고 돌려 쓰는 연결 묶음", DB, N,
        "연결을 매번 새로 만들지 않고 미리 몇 개 열어둔 뒤 빌려주고 돌려받는 방식. "
        "연결 만드는 비용이 커서 쓴다. 개수가 모자라면 요청이 줄을 서다 타임아웃이 나고, "
        "너무 많으면 데이터베이스 쪽이 먼저 무너진다.",
        "The pool is exhausted; connections are not being returned.",
        "커넥션 풀이 고갈됐습니다. 연결이 반환되지 않고 있습니다.",
    ),
    (
        "transaction", "/trænˈzækʃən/", "전부 되거나 전부 안 되게 묶기", DB, N,
        "여러 작업을 하나로 묶어 중간에 실패하면 전부 없던 일로 만드는 단위. "
        "돈을 빼고 넣는 두 작업 사이에 문제가 생겨도 한쪽만 반영되는 일을 막는다. "
        "길게 열어두면 그동안 다른 작업이 기다리게 되므로 짧게 유지해야 한다.",
        "Wrap both updates in a single transaction.",
        "두 갱신을 하나의 트랜잭션으로 묶으세요.",
    ),
    (
        "isolation level", "/ˌaɪsəˈleɪʃn ˌlevl/", "동시 작업끼리 얼마나 가릴지", DB, H,
        "동시에 도는 트랜잭션들이 서로의 중간 상태를 얼마나 볼 수 있는지 정한 단계. "
        "엄격할수록 이상한 값을 볼 일이 줄지만 기다림이 늘어난다. 기본값이 무엇인지는 "
        "데이터베이스마다 달라서, 옮길 때 동작이 달라지는 원인이 되기도 한다.",
        "We raised the isolation level to avoid reading uncommitted rows.",
        "커밋되지 않은 행을 읽지 않도록 격리 수준을 올렸습니다.",
    ),
    (
        "dirty read", "/ˈdɜrti ˌrid/", "아직 확정 안 된 값을 읽기", DB, H,
        "다른 트랜잭션이 고쳤지만 아직 확정하지 않은 값을 읽어버리는 현상. "
        "그 트랜잭션이 취소되면 존재한 적도 없는 값을 본 셈이 된다. "
        "정처기 시험에서 격리 수준 문제와 함께 자주 나온다.",
        "A dirty read can expose data from a transaction that later rolls back.",
        "더티 리드는 나중에 취소될 트랜잭션의 데이터를 보여줄 수 있습니다.",
    ),
    (
        "deadlock", "/ˈdedlɑk/", "서로의 것을 기다리다 멈춤", DB, H,
        "둘 이상이 서로가 쥔 자원을 기다려 아무도 진행하지 못하는 상태. 기다림이 "
        "길어지는 것이 아니라 영원히 안 풀리는 것이 핵심이다. 데이터베이스는 이걸 "
        "감지해 한쪽을 강제로 취소시킨다. 여러 표를 항상 같은 순서로 잠그면 크게 줄어든다.",
        "Two transactions deadlocked and one was rolled back automatically.",
        "두 트랜잭션이 교착 상태에 빠져 하나가 자동으로 롤백됐습니다.",
    ),
    (
        "ACID", "/ˈæsɪd/", "트랜잭션이 지켜야 할 네 가지 성질", DB, H,
        "Atomicity, Consistency, Isolation, Durability "
        "의 앞 글자를 딴 말로 원자성·일관성·고립성·지속성을 뜻한다. "
        "트랜잭션이 믿을 만하려면 갖춰야 "
        "할 성질들이다. '에이시아이디' 가 아니라 '애시드' 로 읽는다. "
        "정처기 단골 문제다.",
        "The database guarantees ACID properties for each transaction.",
        "이 데이터베이스는 각 트랜잭션에 대해 ACID 성질을 보장합니다.",
    ),
    (
        "lock", "/lɑk/", "다른 작업이 못 건드리게 잠그기", DB, N,
        "한 작업이 다루는 동안 다른 작업이 같은 데이터를 바꾸지 못하게 막는 것. "
        "행 하나만 잠글 수도 있고 표 전체가 잠기기도 하는데, 범위가 넓어질수록 "
        "동시에 처리할 수 있는 양이 줄어든다. 갑자기 느려진 서비스의 흔한 원인이다.",
        "That update takes a table lock and blocks everyone else.",
        "그 갱신이 테이블 락을 잡아서 다른 작업을 전부 막고 있습니다.",
    ),
    (
        "optimistic locking", "/ˌɑptɪˈmɪstɪk ˌlɑkɪŋ/", "일단 하고 충돌 났는지 확인", DB, H,
        "미리 잠그지 않고 저장할 때 그 사이 남이 고쳤는지 버전으로 확인하는 방식. "
        "충돌이 드물 때 훨씬 빠르다. 대신 충돌이 나면 실패를 사용자에게 알리고 "
        "다시 시도하게 만들어야 한다.",
        "We use optimistic locking with a version column on that table.",
        "그 테이블은 버전 칼럼을 두고 낙관적 락을 씁니다.",
    ),
    (
        "replication", "/ˌreplɪˈkeɪʃn/", "같은 데이터를 여러 대에 복사해두기", DB, N,
        "한 서버의 데이터를 다른 서버로 계속 복사해두는 것. 읽기를 나눠 받고 장애에 "
        "대비할 수 있다. 복사에는 시간이 걸려서, 방금 저장한 값을 복제본에서 읽으면 "
        "아직 없을 수 있다는 점이 실무의 함정이다.",
        "Read replicas lag behind, so read your own writes from the primary.",
        "복제본은 지연되니 방금 쓴 데이터는 주 서버에서 읽으세요.",
    ),
    (
        "replica", "/ˈreplɪkə/", "복사본 역할을 하는 서버", DB, N,
        "주 서버의 데이터를 복사해 받아 주로 읽기를 담당하는 서버. 쓰기는 보통 "
        "주 서버에서만 받는다. 예전에는 master/slave 라고 불렀지만 지금은 "
        "primary/replica 라는 표현이 표준에 가깝다.",
        "Point the reporting queries at a replica.",
        "리포트용 쿼리는 복제본으로 보내세요.",
    ),
    (
        "sharding", "/ˈʃɑrdɪŋ/", "데이터를 여러 서버에 나눠 담기", DB, H,
        "한 표의 데이터를 기준을 정해 여러 서버에 쪼개 저장하는 것. 복제가 같은 데이터를 "
        "여러 벌 두는 것이라면 이건 서로 다른 조각을 나눠 갖는 것이다. 나누는 기준을 "
        "잘못 잡으면 특정 서버에만 부하가 몰리고, 기준을 나중에 바꾸기가 매우 어렵다.",
        "We shard users by region to spread the write load.",
        "쓰기 부하를 분산하려고 사용자를 지역 기준으로 샤딩합니다.",
    ),
    (
        "partition", "/pɑrˈtɪʃn/", "한 표를 조각으로 나눠 저장", DB, N,
        "큰 표를 날짜 같은 기준으로 여러 조각으로 나눠 관리하는 것. 같은 데이터베이스 "
        "안에서 나눈다는 점이 샤딩과 다르다. 조건에 그 기준이 들어가면 필요한 조각만 "
        "읽어 빨라지고, 오래된 조각을 통째로 지우기도 쉬워진다.",
        "The table is partitioned by month, so old data is easy to drop.",
        "테이블이 월별로 파티션돼 있어서 오래된 데이터를 지우기 쉽습니다.",
    ),
    (
        "cascade", "/kæˈskeɪd/", "따라서 같이 처리되게 하기", DB, N,
        "부모 행이 지워지거나 바뀔 때 그것을 가리키던 자식 행도 함께 처리되도록 하는 설정. "
        "편리하지만 한 줄을 지웠는데 관련 데이터가 연쇄로 사라질 수 있어서, "
        "운영 데이터에는 신중하게 건다.",
        "Deleting the account cascaded and removed all of the orders.",
        "계정을 삭제하니 연쇄로 주문까지 전부 지워졌습니다.",
    ),
    (
        "null", "/nʌl/", "값이 없다는 상태", DB, N,
        "값이 아직 없거나 알 수 없다는 표시. 0 이나 빈 문자열과 다르다. 가장 큰 함정은 "
        "비교가 통하지 않는다는 점이라, null = null 조차 참이 아니고 IS NULL 을 써야 한다. "
        "발음은 '널'이다. '눌'이 아니다.",
        "Use IS NULL; comparing with equals will never match.",
        "IS NULL 을 쓰세요. 등호로 비교하면 절대 일치하지 않습니다.",
    ),
    (
        "unique", "/juˈnik/", "값이 겹치지 않게 하는 제약", DB, E,
        "해당 칸에 같은 값이 두 번 들어가지 못하게 막는 규칙. 코드에서 먼저 확인하고 "
        "넣더라도 동시에 두 요청이 들어오면 뚫리기 때문에, 마지막 방어선은 결국 "
        "데이터베이스 쪽 제약이다. 대부분의 데이터베이스에서 null 은 여러 개 "
        "허용되지만 SQL Server 는 하나만 받아서, 옮길 때 여기서 깨진다.",
        "Add a unique constraint on the email column.",
        "이메일 칼럼에 유니크 제약을 추가하세요.",
    ),
    (
        "group by", "/ˈɡrup ˌbaɪ/", "같은 값끼리 묶어 계산하기", DB, N,
        "지정한 칸의 값이 같은 행끼리 묶고 그 묶음마다 합계나 개수를 내는 것. "
        "묶은 뒤에는 묶음 단위로만 얘기할 수 있어서, 묶는 기준에 없는 칸을 그냥 "
        "꺼내려 하면 오류가 난다.",
        "Group by user id and count the orders per user.",
        "사용자 아이디로 묶어 사용자당 주문 수를 세세요.",
    ),
    (
        "having", "/ˈhævɪŋ/", "묶은 뒤에 거르는 조건", DB, N,
        "그룹으로 묶은 결과에 거는 조건. WHERE 는 묶기 전에 행을 거르고 HAVING 은 "
        "묶은 뒤에 그룹을 거른다. 그래서 합계가 100 을 넘는 그룹만 보고 싶을 때는 "
        "WHERE 로는 되지 않는다.",
        "Use having to filter groups with more than ten orders.",
        "주문이 열 건을 넘는 그룹만 보려면 having 을 쓰세요.",
    ),
    (
        "subquery", "/ˈsʌbˌkwɪri/", "쿼리 안에 들어간 쿼리", DB, N,
        "다른 쿼리 안에 괄호로 들어가는 쿼리. 조건에 쓸 값을 미리 뽑을 때 쓴다. "
        "바깥 행마다 안쪽이 다시 도는 형태로 쓰면 행 수만큼 반복돼 아주 느려질 수 있어서, "
        "그럴 때는 조인으로 바꾸는 편이 낫다.",
        "That correlated subquery runs once per row; rewrite it as a join.",
        "그 상관 서브쿼리는 행마다 실행됩니다. 조인으로 바꾸세요.",
    ),
    (
        "view", "/vju/", "저장해둔 조회 결과의 이름", DB, N,
        "자주 쓰는 쿼리에 이름을 붙여 표처럼 쓰게 만든 것. 데이터를 실제로 담고 있지 "
        "않고 볼 때마다 원래 쿼리가 실행된다. 복잡한 조인을 숨겨주는 대신, "
        "느린 쿼리를 뷰로 감싸도 여전히 느리다.",
        "The view hides the join, but the query underneath is still slow.",
        "뷰가 조인을 감춰줄 뿐 그 아래 쿼리는 여전히 느립니다.",
    ),
    (
        "materialized view", "/məˈtɪriəlaɪzd ˌvju/", "결과를 실제로 저장해둔 뷰", DB, H,
        "쿼리 결과를 실제 데이터로 저장해두는 뷰. 조회는 아주 빨라지지만 원본이 바뀌어도 "
        "자동으로 따라가지 않아 갱신 시점을 정해야 한다. 무거운 집계 화면에 쓴다.",
        "The dashboard reads from a materialized view refreshed every hour.",
        "대시보드는 한 시간마다 갱신되는 구체화 뷰에서 읽습니다.",
    ),
    (
        "stored procedure", "/ˌstɔrd prəˈsidʒər/", "데이터베이스 안에 넣어둔 처리 절차", DB, N,
        "여러 SQL 을 묶어 데이터베이스 쪽에 저장해두고 이름으로 부르는 것. 네트워크를 "
        "덜 오가서 빠를 수 있지만, 로직이 코드 저장소 밖에 있어 버전 관리와 리뷰가 "
        "어려워진다는 점이 오늘날 잘 쓰지 않는 이유다.",
        "That business rule lives in a stored procedure, not in the codebase.",
        "그 업무 규칙은 코드가 아니라 저장 프로시저 안에 있습니다.",
    ),
    (
        "trigger", "/ˈtrɪɡər/", "특정 변경이 생기면 자동 실행", DB, N,
        "행이 추가되거나 바뀔 때 자동으로 도는 처리. 코드 어디에도 호출한 곳이 없어서 "
        "왜 이 값이 바뀌었는지 추적하기가 아주 어렵다. 편리한 만큼 디버깅 비용이 "
        "큰 기능이다.",
        "A trigger is updating that column behind your back.",
        "트리거가 뒤에서 그 칼럼을 갱신하고 있습니다.",
    ),
    (
        "ORM", "/ˌoʊ ɑr ˈem/", "객체와 표를 이어주는 도구", DB, N,
        "코드의 객체와 데이터베이스의 표를 자동으로 연결해주는 도구. SQL 을 직접 쓰지 "
        "않아 편하지만 어떤 쿼리가 나가는지 보이지 않게 만든다. N+1 문제 대부분이 "
        "여기서 시작하므로, 실제로 나가는 쿼리를 볼 줄 아는 것이 중요하다.",
        "Turn on query logging to see what the ORM actually sends.",
        "ORM 이 실제로 무슨 쿼리를 보내는지 쿼리 로깅을 켜서 확인하세요.",
    ),
    (
        "lazy loading", "/ˈleɪzi ˌloʊdɪŋ/", "쓸 때가 되면 그때 불러오기", DB, N,
        "연결된 데이터를 미리 가져오지 않고 실제로 접근하는 순간에 조회하는 방식. "
        "필요 없으면 안 가져와서 좋지만, 반복문 안에서 접근하면 매 바퀴마다 쿼리가 "
        "나가 N+1 이 된다.",
        "Lazy loading inside a loop is what caused the N+1.",
        "반복문 안의 지연 로딩이 N+1 의 원인이었습니다.",
    ),
    (
        "eager loading", "/ˈiɡər ˌloʊdɪŋ/", "필요한 것을 미리 한 번에 가져오기", DB, N,
        "연결된 데이터를 처음 조회할 때 함께 가져오는 방식. 쿼리 수가 줄어 N+1 을 "
        "막는 표준 해법이다. 대신 안 쓸 데이터까지 가져올 수 있어서 무조건 좋은 것은 "
        "아니다.",
        "Add eager loading for the author relation on the list page.",
        "목록 화면에서 작성자 관계를 즉시 로딩으로 가져오세요.",
    ),
    (
        "upsert", "/ˈʌpsɜrt/", "있으면 고치고 없으면 넣기", DB, N,
        "같은 키의 행이 있으면 갱신하고 없으면 새로 넣는 한 번의 작업. update 와 "
        "insert 를 붙여 만든 말이다. 조회 후 분기하는 코드로 흉내내면 동시에 두 요청이 "
        "들어올 때 중복이 생기므로, 데이터베이스가 제공하는 구문을 쓰는 게 안전하다.",
        "Use an upsert so concurrent requests do not create duplicates.",
        "동시 요청이 중복을 만들지 않도록 upsert 를 쓰세요.",
    ),
    (
        "soft delete", "/ˈsɔft dɪˌlit/", "지운 표시만 남기기", DB, N,
        "실제로 행을 지우지 않고 삭제됨 표시만 켜두는 방식. 복구와 이력 추적이 쉬워지지만 "
        "모든 조회에 그 조건을 빠짐없이 넣어야 하고, 하나라도 빠지면 지운 데이터가 "
        "화면에 나타난다. 유니크 제약과도 부딪힌다.",
        "We use soft deletes, so every query must filter deleted rows.",
        "소프트 삭제를 쓰기 때문에 모든 쿼리에서 삭제된 행을 걸러야 합니다.",
    ),
    (
        "dump", "/dʌmp/", "데이터를 파일로 통째로 빼내기", DB, E,
        "데이터베이스 내용을 파일 하나로 뽑아내는 것. 백업이나 다른 환경으로 옮길 때 "
        "쓴다. 크기가 커서 복원에 오래 걸리고, 개인정보가 그대로 들어 있어 "
        "개발 환경으로 옮길 때는 가려야 한다.",
        "Dump the staging database before the migration.",
        "마이그레이션 전에 스테이징 데이터베이스를 덤프해두세요.",
    ),
    (
        "seed", "/sid/", "초기 데이터를 미리 채워 넣기", DB, E,
        "빈 데이터베이스에 기본 데이터를 넣어두는 것. 새로 받은 사람이 바로 화면을 "
        "볼 수 있게 하거나 테스트 기준 데이터를 만들 때 쓴다. 운영 데이터를 그대로 "
        "쓰면 안 된다.",
        "Run the seed command after you create the database.",
        "데이터베이스를 만든 뒤 시드 명령을 실행하세요.",
    ),
    (
        "cardinality", "/ˌkɑrdɪˈnæləti/", "값의 종류가 얼마나 다양한지", DB, H,
        "한 칸에 서로 다른 값이 얼마나 많은지. 성별처럼 종류가 적으면 낮고 이메일처럼 "
        "거의 다 다르면 높다. 종류가 적은 칸에 인덱스를 걸면 걸러지는 양이 적어 "
        "효과가 없는 경우가 많다. 다만 값이 한쪽으로 크게 치우쳐 드문 값을 찾는 "
        "경우에는 종류가 적어도 여전히 효과가 있다.",
        "An index on a low cardinality column rarely helps.",
        "값 종류가 적은 칼럼의 인덱스는 거의 도움이 되지 않습니다.",
    ),
    (
        "collation", "/kəˈleɪʃn/", "문자를 비교하고 정렬하는 규칙", DB, H,
        "문자열을 어떤 순서로 정렬하고 대소문자를 같게 볼지 정한 규칙. 설정에 따라 "
        "같은 검색이 어떤 서버에서는 되고 어떤 서버에서는 안 되는 상황이 생긴다. "
        "한글 정렬 순서가 이상할 때 여기를 의심한다.",
        "The collation makes the comparison case-insensitive.",
        "이 collation 때문에 비교가 대소문자를 구분하지 않습니다.",
    ),
    (
        "auto increment", "/ˈɔtoʊ ˌɪŋkrəmənt/", "번호를 자동으로 하나씩 올리기", DB, E,
        "행을 넣을 때마다 번호를 자동으로 붙여주는 기능. 실패한 삽입도 번호를 소비해서 "
        "중간에 구멍이 생기는데 이건 정상이다. 이 번호가 주소에 그대로 드러나면 "
        "전체 데이터 규모가 외부에 노출된다.",
        "Do not expose the auto increment id in public URLs.",
        "공개 URL 에 자동 증가 아이디를 그대로 노출하지 마세요.",
    ),
    (
        "NoSQL", "/ˌnoʊ ˈsikwl/", "표 구조를 강제하지 않는 저장소", DB, N,
        "행과 열로 된 표 대신 문서나 키-값 형태로 저장하는 데이터베이스들을 묶어 부르는 말. "
        "SQL 을 안 쓴다기보다 관계형 모델을 따르지 않는다는 뜻에 가깝다. "
        "구조가 자유로운 대신 규칙을 애플리케이션이 지켜야 한다.",
        "We store event logs in a NoSQL database.",
        "이벤트 로그는 NoSQL 데이터베이스에 저장합니다.",
    ),
    (
        "eventual consistency", "/ɪˈventʃuəl kənˌsɪstənsi/", "결국에는 같아지는 상태", DB, H,
        "쓴 값이 모든 서버에 즉시 반영되지는 않지만 시간이 지나면 결국 같아지는 방식. "
        "빠르고 잘 견디는 대신, 방금 저장한 값을 바로 읽었을 때 옛 값이 나올 수 있다. "
        "사용자에게 이상해 보이는 버그의 원인이 되기 쉽다.",
        "The counter is eventually consistent, so it may lag a few seconds.",
        "이 카운터는 최종적 일관성이라 몇 초 정도 늦을 수 있습니다.",
    ),
    # ---------- 배포 / 운영 / 인프라 ----------
    (
        "image", "/ˈɪmɪdʒ/", "실행 환경을 통째로 굳혀둔 틀", OPS, N,
        "코드와 필요한 라이브러리, 설정까지 한 덩어리로 굳혀둔 것. 이걸로 컨테이너를 "
        "찍어낸다. 한 번 만들면 바뀌지 않는 것이 핵심이라, 실행 중에 고친 내용은 "
        "다시 만들 때 사라진다. 사진 파일이 아니라 실행 환경의 틀을 뜻한다.",
        "Rebuild the image after you change the dependencies.",
        "의존성을 바꿨으면 이미지를 다시 빌드하세요.",
    ),
    (
        "container", "/kənˈteɪnər/", "격리해서 실행한 하나의 인스턴스", OPS, N,
        "이미지를 실제로 띄운 실행 단위. 자기만의 파일 시스템과 네트워크를 가진 것처럼 "
        "보이지만 커널은 호스트와 공유한다. 그래서 가상 머신보다 가볍다. "
        "지우면 안에서 만든 파일도 함께 사라진다.",
        "The container restarts in a loop because of a config error.",
        "설정 오류 때문에 컨테이너가 계속 재시작되고 있습니다.",
    ),
    (
        "volume", "/ˈvɑljum/", "컨테이너 밖에 남기는 저장 공간", OPS, N,
        "컨테이너가 사라져도 남아야 하는 데이터를 두는 바깥 저장 공간. 컨테이너 안은 "
        "지우면 없어지기 때문에 데이터베이스 파일이나 업로드 파일은 여기에 둔다. "
        "이걸 안 걸어두면 재배포마다 데이터가 초기화된다.",
        "Mount a volume so the database survives a restart.",
        "재시작해도 데이터베이스가 남도록 볼륨을 마운트하세요.",
    ),
    (
        "registry", "/ˈredʒɪstri/", "이미지를 올려두는 보관소", OPS, N,
        "만든 이미지를 올려두고 다른 서버가 받아가게 하는 저장소. 코드 저장소와는 "
        "다른 곳이다. 비공개 저장소는 받아올 때 인증이 필요해서, 인증 설정이 빠지면 "
        "배포 단계에서 이미지를 못 받아 실패한다.",
        "The deploy failed because it could not pull from the registry.",
        "레지스트리에서 이미지를 받아오지 못해 배포가 실패했습니다.",
    ),
    (
        "orchestration", "/ˌɔrkɪˈstreɪʃn/", "여러 컨테이너를 자동으로 관리하기", OPS, H,
        "컨테이너를 어느 서버에 몇 개 띄울지, 죽으면 어떻게 살릴지를 자동으로 관리하는 것. "
        "컨테이너가 몇 개일 때는 필요 없다가 수십 개가 되면 사람이 감당하지 못해 도입한다. "
        "쿠버네티스가 대표적이다.",
        "We moved to container orchestration once we had thirty services.",
        "서비스가 서른 개가 되면서 컨테이너 오케스트레이션을 도입했습니다.",
    ),
    (
        "cluster", "/ˈklʌstər/", "한 덩어리처럼 묶어 쓰는 서버 무리", OPS, N,
        "여러 서버를 묶어 하나처럼 다루는 구성. 어느 서버에서 도는지를 신경 쓰지 않고 "
        "전체 자원을 나눠 쓰게 한다. 한 대가 죽어도 그 위에 있던 작업이 다른 곳에서 "
        "다시 뜨게 만드는 것이 목적이다.",
        "The pod was rescheduled to another node in the cluster.",
        "파드가 클러스터의 다른 노드로 재배치됐습니다.",
    ),
    (
        "node", "/noʊd/", "클러스터를 이루는 서버 한 대", OPS, N,
        "클러스터 안에서 실제로 일을 돌리는 서버 한 대. 물리 서버일 수도 가상 서버일 "
        "수도 있다. 자바스크립트 런타임 이름과 철자가 같아 문맥을 봐야 한다.",
        "One node ran out of memory and its pods were evicted.",
        "노드 한 대의 메모리가 부족해 그 위의 파드들이 쫓겨났습니다.",
    ),
    (
        "pipeline", "/ˈpaɪplaɪn/", "자동으로 이어지는 처리 단계들", OPS, E,
        "코드를 올리면 검사, 빌드, 테스트, 배포가 정해진 순서로 자동 실행되는 흐름. "
        "앞 단계가 실패하면 뒤는 돌지 않는다. 파이프라인이 느리면 사람들이 "
        "확인을 건너뛰기 시작하므로 속도 자체가 품질 문제다.",
        "The pipeline fails at the lint step.",
        "파이프라인이 린트 단계에서 실패합니다.",
    ),
    (
        "artifact", "/ˈɑrtɪfækt/", "빌드가 만들어낸 결과물", OPS, N,
        "빌드 과정에서 나온 실행 파일이나 압축 파일처럼 다음 단계로 넘길 결과물. "
        "각 단계마다 다시 빌드하지 않고 이걸 넘겨 쓴다. 테스트한 것과 배포한 것이 "
        "같은 결과물이어야 한다는 원칙이 여기서 나온다.",
        "Download the build artifact from the previous stage.",
        "이전 단계에서 만든 빌드 결과물을 내려받으세요.",
    ),
    (
        "staging", "/ˈsteɪdʒɪŋ/", "운영 직전에 확인하는 환경", OPS, E,
        "운영과 최대한 비슷하게 만들어 마지막으로 확인하는 환경. 여기서는 되는데 "
        "운영에서 안 되는 이유는 대개 데이터 양이나 설정이 다르기 때문이다. "
        "환경이 다를수록 여기서 통과했다는 사실의 가치가 떨어진다.",
        "It works on staging but fails in production under real load.",
        "스테이징에서는 되는데 실제 부하가 걸리는 운영에서는 실패합니다.",
    ),
    (
        "production", "/prəˈdʌkʃən/", "실제 사용자가 쓰는 환경", OPS, E,
        "진짜 사용자가 접속하는 환경. 줄여서 prod 라고 쓴다. 여기서만 재현되는 문제가 "
        "많은 이유는 데이터 양, 동시 접속, 외부 연동이 다른 환경과 다르기 때문이다. "
        "여기서 직접 손으로 고치면 다음 배포에 그 수정이 사라진다.",
        "Do not hotfix directly on production without a matching commit.",
        "커밋 없이 운영에 직접 핫픽스하지 마세요.",
    ),
    (
        "backward compatible", "/ˈbækwərd kəmˌpætəbl/", "옛 버전도 계속 동작하는", OPS, N,
        "새 버전이 나와도 예전 버전이 그대로 동작하는 성질. 무중단 배포 중에는 옛 코드와 "
        "새 코드가 잠시 함께 도는데, 이때 데이터베이스 변경이 하위 호환이 아니면 "
        "옛 코드가 곧바로 깨진다. 칼럼을 지우기 전에 먼저 쓰지 않게 만드는 "
        "두 단계 배포가 여기서 나온다.",
        "Make the migration backward compatible so the old pods keep working.",
        "옛 파드가 계속 동작하도록 마이그레이션을 하위 호환으로 만드세요.",
    ),
    (
        "blue-green", "/ˌblu ˈɡrin/", "두 벌을 두고 통째로 전환하기", OPS, H,
        "똑같은 환경을 두 벌 준비해두고 새 버전을 한쪽에 올린 뒤 트래픽을 한 번에 "
        "옮기는 방식. 문제가 생기면 다시 옛 쪽으로 돌리면 되니 되돌리기가 아주 빠르다. "
        "전환하는 동안에는 환경이 두 벌이라 그만큼 자원이 더 든다. 되돌릴 일에 "
        "대비해 옛 환경을 한동안 남겨두기도 한다.",
        "We use blue-green deploys so rollback is instant.",
        "즉시 롤백이 가능하도록 블루-그린 배포를 씁니다.",
    ),
    (
        "canary", "/kəˈneri/", "일부에게만 먼저 내보내기", OPS, H,
        "새 버전을 전체가 아니라 소수의 사용자에게만 먼저 보내 문제를 살펴보는 방식. "
        "탄광의 카나리아에서 온 이름이다. 지표를 함께 보지 않으면 그냥 일부만 "
        "느리게 배포하는 것에 지나지 않는다.",
        "The canary showed a spike in errors, so we halted the rollout.",
        "카나리에서 에러가 급증해 배포를 중단했습니다.",
    ),
    (
        "rolling update", "/ˈroʊlɪŋ ˌʌpdeɪt/", "조금씩 갈아 끼우며 교체", OPS, N,
        "서버를 한꺼번에 바꾸지 않고 몇 대씩 차례로 새 버전으로 교체하는 방식. "
        "서비스를 멈추지 않아도 되지만 교체 중에는 옛 버전과 새 버전이 동시에 돌기 때문에, "
        "둘이 같은 데이터를 다뤄도 문제가 없어야 한다.",
        "During a rolling update, both versions run at the same time.",
        "롤링 업데이트 중에는 두 버전이 동시에 돕니다.",
    ),
    (
        "health check", "/ˈhelθ ˌtʃek/", "살아 있는지 주기적으로 확인", OPS, E,
        "서비스가 정상인지 주기적으로 물어보는 것. 응답이 없으면 트래픽을 보내지 않거나 "
        "다시 띄운다. 단순히 프로세스가 떠 있는지만 보면 데이터베이스가 끊긴 상태에서도 "
        "정상으로 나오므로, 실제 의존성까지 확인하도록 만드는 게 좋다.",
        "The health check passes even though the database is unreachable.",
        "데이터베이스에 접속이 안 되는데도 헬스 체크는 통과하고 있습니다.",
    ),
    (
        "graceful shutdown", "/ˈɡreɪsfl ˌʃʌtdaʊn/", "하던 일을 끝내고 종료하기", OPS, H,
        "종료 신호를 받으면 새 요청은 받지 않고 처리 중인 것만 마친 뒤 내려가는 것. "
        "이걸 처리하지 않으면 배포할 때마다 진행 중이던 요청이 잘려 사용자에게 "
        "에러가 나간다. 배포 중 간헐적 오류의 흔한 원인이다.",
        "Handle SIGTERM so in-flight requests can finish.",
        "처리 중인 요청이 끝나도록 종료 신호를 처리하세요.",
    ),
    (
        "zero downtime", "/ˈzɪroʊ ˌdaʊntaɪm/", "멈춤 없이 배포하기", OPS, N,
        "서비스를 멈추지 않고 새 버전으로 바꾸는 것. 배포 방식만으로 되지 않고, "
        "종료 처리와 데이터베이스 변경 순서까지 맞아야 한다. 칼럼을 지우는 변경은 "
        "옛 코드가 아직 그 칼럼을 쓰기 때문에 특히 조심해야 한다.",
        "Zero downtime deploys require backward compatible migrations.",
        "무중단 배포를 하려면 마이그레이션이 하위 호환이어야 합니다.",
    ),
    (
        "feature flag", "/ˈfitʃər ˌflæɡ/", "코드를 켜고 끄는 스위치", OPS, N,
        "배포된 코드를 설정으로 켜고 끌 수 있게 만든 스위치. 배포와 공개를 분리해서, "
        "미완성 기능을 꺼둔 채 합칠 수 있게 한다. 정리하지 않고 쌓이면 분기가 뒤엉켜 "
        "그 자체가 부채가 된다.",
        "Ship it behind a feature flag and enable it for internal users first.",
        "피처 플래그 뒤에 두고 내부 사용자에게만 먼저 켜세요.",
    ),
    (
        "load balancer", "/ˈloʊd ˌbælənsər/", "요청을 여러 서버로 나눠 보내기", OPS, N,
        "들어오는 요청을 여러 서버에 나눠 주는 장치. 부하를 고르게 하고 죽은 서버를 "
        "빼준다. 세션을 각 서버 메모리에 두면 요청마다 다른 서버로 가서 로그인이 "
        "풀리는데, 이게 무상태 설계가 필요한 이유다.",
        "The load balancer stopped routing traffic to the unhealthy instance.",
        "로드 밸런서가 비정상 인스턴스로 트래픽을 보내지 않게 됐습니다.",
    ),
    (
        "reverse proxy", "/rɪˈvɜrs ˌprɑksi/", "앞에 서서 요청을 대신 받는 서버", OPS, N,
        "사용자 요청을 먼저 받아 뒤쪽 서버로 넘겨주는 서버. 일반 프록시가 클라이언트를 "
        "대신한다면 이건 서버 쪽을 대신한다. 암호화 처리, 정적 파일 제공, 압축 같은 "
        "공통 작업을 여기서 맡는다.",
        "Nginx sits in front as a reverse proxy and handles TLS.",
        "Nginx 가 앞단에서 리버스 프록시로 TLS 를 처리합니다.",
    ),
    (
        "CDN", "/ˌsi di ˈen/", "사용자와 가까운 곳에 복사해두기", OPS, N,
        "이미지나 스크립트 같은 파일을 세계 곳곳의 서버에 복사해두고 가까운 곳에서 "
        "내려주는 서비스. 거리가 줄어 빨라진다. 파일을 바꿔도 옛 파일이 계속 나오는 "
        "문제가 있어서, 파일 이름에 해시를 넣어 이름 자체를 바꾸는 방식을 쓴다.",
        "The CDN is still serving the old bundle; purge the cache.",
        "CDN 이 아직 옛 번들을 주고 있습니다. 캐시를 비우세요.",
    ),
    (
        "metric", "/ˈmetrɪk/", "숫자로 재는 상태 지표", OPS, E,
        "응답 시간이나 에러 비율처럼 시간에 따라 재는 숫자. 로그가 개별 사건이라면 "
        "이건 전체 추세다. 평균만 보면 일부 사용자가 겪는 심한 지연이 묻히므로 "
        "상위 백분위를 함께 본다.",
        "Watch the error rate metric during the rollout.",
        "배포 중에 에러율 지표를 지켜보세요.",
    ),
    (
        "tracing", "/ˈtreɪsɪŋ/", "요청 하나가 지나간 길 추적", OPS, H,
        "요청 하나가 여러 서비스를 거치는 경로와 각 구간에 걸린 시간을 이어서 보는 것. "
        "서비스가 여러 개일 때 어디서 느려졌는지 찾는 유일한 방법에 가깝다. "
        "모든 서비스가 같은 추적 아이디를 넘겨야 이어진다.",
        "The trace shows most of the time is spent in the auth service.",
        "트레이스를 보면 대부분의 시간이 인증 서비스에서 쓰이고 있습니다.",
    ),
    (
        "observability", "/əbˌzɜrvəˈbɪləti/", "밖에서 안을 알아볼 수 있는 정도", OPS, H,
        "로그, 지표, 추적을 통해 시스템 안에서 무슨 일이 일어나는지 알 수 있는 정도. "
        "미리 정해둔 것만 보는 모니터링과 달리, 예상 못 한 질문에도 답할 수 있는지를 "
        "따진다. 처음 보는 장애에서 차이가 드러난다.",
        "We have monitoring but poor observability for new failure modes.",
        "모니터링은 있지만 처음 보는 장애 유형에 대한 관측 가능성이 부족합니다.",
    ),
    (
        "alert", "/əˈlɜrt/", "이상하면 사람을 부르는 알림", OPS, E,
        "정해둔 조건을 넘으면 담당자에게 알리는 것. 너무 자주 울리면 사람들이 무시하기 "
        "시작해서 정작 중요한 알림을 놓친다. 그래서 사람이 지금 조치할 수 있는 것만 "
        "알림으로 만드는 게 원칙이다.",
        "Too many noisy alerts and people start ignoring the channel.",
        "쓸데없는 알림이 너무 많으면 사람들이 채널을 무시하게 됩니다.",
    ),
    (
        "SLA", "/ˌes el ˈeɪ/", "지키기로 약속한 서비스 수준", OPS, N,
        "가용성이나 응답 시간을 어느 수준까지 보장하겠다고 사용자와 맺은 약속. "
        "못 지키면 보상 조항이 따르는 계약에 가깝다. 내부 목표인 SLO 와 자주 혼동되는데, "
        "SLA 는 바깥과의 약속이고 SLO 는 우리끼리 정한 목표다.",
        "Our SLA promises 99.9 percent uptime.",
        "우리 SLA 는 99.9 퍼센트 가동률을 약속합니다.",
    ),
    (
        "SLO", "/ˌes el ˈoʊ/", "내부적으로 세운 목표 수준", OPS, H,
        "우리가 지키려고 정한 서비스 수준 목표. 대외 약속보다 조금 빡빡하게 잡아 "
        "여유를 둔다. 목표를 100 퍼센트로 잡지 않는 이유는, 남는 여유만큼 "
        "위험을 감수하고 배포할 수 있기 때문이다.",
        "We are burning through our error budget this month.",
        "이번 달 오류 예산을 빠르게 소진하고 있습니다.",
    ),
    (
        "uptime", "/ˈʌptaɪm/", "정상으로 돌아간 시간 비율", OPS, E,
        "전체 시간 중 서비스가 정상이었던 비율. 숫자 하나 차이가 커서 "
        "99 퍼센트는 한 달에 약 7시간 멈춰도 되는 수준이지만 99.9 퍼센트는 "
        "43분 남짓이다. 뒤에 9 가 하나 붙을 때마다 비용이 크게 뛴다.",
        "Adding another nine to our uptime target is expensive.",
        "가동률 목표에 9 를 하나 더 붙이는 건 비용이 큽니다.",
    ),
    (
        "incident", "/ˈɪnsɪdənt/", "대응이 필요한 장애 상황", OPS, N,
        "사용자에게 영향을 주어 즉시 대응해야 하는 상황. 버그와 달리 원인보다 "
        "복구가 먼저다. 대응 중에는 지휘를 맡는 사람과 기록을 맡는 사람을 나누는 것이 "
        "혼선을 줄이는 데 도움이 된다.",
        "We declared an incident and paged the on-call engineer.",
        "장애를 선언하고 온콜 담당자를 호출했습니다.",
    ),
    (
        "runbook", "/ˈrʌnbʊk/", "상황별 대응 절차 문서", OPS, N,
        "특정 장애가 났을 때 무엇을 어떤 순서로 확인하고 조치할지 적어둔 문서. "
        "새벽에 잠에서 깬 사람이 그대로 따라할 수 있을 만큼 구체적이어야 쓸모가 있다. "
        "알림마다 여기 링크를 걸어두는 팀이 많다.",
        "The alert links to a runbook with the exact recovery steps.",
        "알림에 정확한 복구 절차가 담긴 런북 링크가 걸려 있습니다.",
    ),
    (
        "latency", "/ˈleɪtnsi/", "요청에 응답이 오기까지의 지연", OPS, N,
        "요청을 보내고 응답을 받기까지 걸린 시간. 처리량과 다른 개념이라, "
        "처리량을 늘리려고 요청을 모아 처리하면 오히려 지연은 늘어난다. "
        "평균보다 상위 백분위 값이 실제 사용자 체감에 가깝다.",
        "P99 latency doubled after the last deploy.",
        "지난 배포 이후 상위 1퍼센트 지연 시간이 두 배가 됐습니다.",
    ),
    (
        "throughput", "/ˈθrupʊt/", "일정 시간에 처리한 양", OPS, N,
        "단위 시간에 처리한 요청 수. 지연 시간과 함께 봐야 의미가 있는데, "
        "둘은 서로 맞바꿈 관계인 경우가 많다. 처리량이 한계에 닿으면 대기열이 쌓이면서 "
        "지연이 급격히 나빠진다.",
        "Throughput is fine, but latency spikes at peak hours.",
        "처리량은 괜찮은데 피크 시간대에 지연이 치솟습니다.",
    ),
    (
        "bottleneck", "/ˈbɑtlnek/", "전체 속도를 결정하는 좁은 구간", OPS, N,
        "전체 처리 속도를 붙잡고 있는 가장 느린 구간. 여기가 아닌 곳을 아무리 빠르게 "
        "만들어도 전체는 그대로다. 병 목이 좁아 물이 천천히 나오는 데서 온 비유다.",
        "The database is the bottleneck, not the application server.",
        "병목은 애플리케이션 서버가 아니라 데이터베이스입니다.",
    ),
    (
        "autoscaling", "/ˈɔtoʊˌskeɪlɪŋ/", "부하에 따라 자동으로 늘리고 줄이기", OPS, N,
        "부하에 맞춰 서버 수를 자동으로 조절하는 것. 새 서버가 뜨는 데 시간이 걸려서 "
        "갑자기 몰리는 트래픽에는 늦게 반응한다. 데이터베이스처럼 함께 늘어나지 않는 "
        "부분이 있으면 그쪽이 먼저 무너진다.",
        "Autoscaling kicked in too late to absorb the traffic spike.",
        "오토스케일링이 너무 늦게 동작해 트래픽 급증을 흡수하지 못했습니다.",
    ),
    (
        "horizontal scaling", "/ˌhɔrɪˈzɑntəl ˌskeɪlɪŋ/", "서버 대수를 늘려 감당하기", OPS, N,
        "서버 한 대를 키우는 대신 같은 서버를 여러 대로 늘리는 방식. 한 대가 죽어도 "
        "버틴다는 장점이 있지만, 서비스가 무상태여야 가능하다. 그래서 상태를 어디에 "
        "둘지가 확장의 실제 관건이 된다.",
        "We scale horizontally by adding more instances behind the load balancer.",
        "로드 밸런서 뒤에 인스턴스를 늘리는 방식으로 수평 확장합니다.",
    ),
    (
        "vertical scaling", "/ˈvɜrtɪkl ˌskeɪlɪŋ/", "서버 사양을 키워 감당하기", OPS, N,
        "서버의 CPU 나 메모리를 늘려 처리 능력을 키우는 방식. 코드를 바꾸지 않아도 돼서 "
        "가장 빠른 해법이지만 한 대가 커질 수 있는 한계가 있고, 그 한 대가 죽으면 "
        "전체가 멈춘다.",
        "Vertical scaling bought us time, but we still hit the ceiling.",
        "수직 확장으로 시간을 벌었지만 결국 한계에 부딪혔습니다.",
    ),
    (
        "provisioning", "/prəˈvɪʒənɪŋ/", "쓸 수 있게 준비해두기", OPS, N,
        "서버나 데이터베이스 같은 자원을 만들고 설정해 쓸 수 있는 상태로 만드는 것. "
        "손으로 하면 환경마다 미묘하게 달라지므로, 지금은 대개 코드로 적어 "
        "같은 결과가 나오게 한다.",
        "Provisioning the new environment takes about ten minutes.",
        "새 환경을 준비하는 데 10분 정도 걸립니다.",
    ),
    (
        "infrastructure as code", "/ˈɪnfrəstrʌktʃər əz ˌkoʊd/", "인프라를 코드로 적어 관리", OPS, H,
        "서버 구성을 손으로 만들지 않고 파일로 적어 버전 관리하는 방식. 같은 파일로 "
        "언제든 같은 환경을 다시 만들 수 있고 변경 이력이 남는다. 콘솔에서 손으로 "
        "고치면 코드와 실제가 어긋나는데, 이걸 drift 라고 부른다.",
        "Someone changed it in the console, so the infrastructure has drifted from the code.",
        "누가 콘솔에서 직접 바꿔서 인프라 코드와 실제가 어긋났습니다.",
    ),
    (
        "secret", "/ˈsikrət/", "노출되면 안 되는 설정값", OPS, E,
        "비밀번호나 API 키처럼 코드에 넣으면 안 되는 값. 저장소에 한 번 커밋되면 "
        "지워도 기록에 남기 때문에, 유출됐다면 파일을 지우는 게 아니라 그 값을 "
        "폐기하고 새로 발급받아야 한다.",
        "Rotate the secret; deleting the commit is not enough.",
        "커밋을 지우는 걸로는 부족합니다. 해당 비밀값을 새로 발급하세요.",
    ),
    (
        "cron", "/krɑn/", "정해진 시각에 반복 실행", OPS, N,
        "정해진 시간마다 작업을 자동으로 실행하는 장치. 시간 표기가 분, 시, 일, 월, "
        "요일 순서라 헷갈리기 쉽고, 서버 시간대가 다르면 엉뚱한 시각에 돈다. "
        "앞 작업이 안 끝났는데 다음이 시작되는 겹침도 자주 겪는 문제다.",
        "The cron job runs in UTC, which is why it fired at the wrong hour.",
        "크론 작업이 UTC 로 돌아서 엉뚱한 시각에 실행됐습니다.",
    ),
    (
        "worker", "/ˈwɜrkər/", "뒤에서 일을 처리하는 프로세스", OPS, N,
        "요청에 바로 답하지 않고 대기열에 쌓인 작업을 꺼내 처리하는 프로세스. "
        "메일 발송이나 이미지 변환처럼 오래 걸리는 일을 여기로 넘겨 응답을 빠르게 한다. "
        "워커가 죽으면 화면은 멀쩡한데 처리만 계속 밀린다.",
        "The workers are down, so the queue keeps growing.",
        "워커가 죽어서 대기열이 계속 쌓이고 있습니다.",
    ),
    (
        "quota", "/ˈkwoʊtə/", "쓸 수 있는 양의 상한", OPS, N,
        "계정이나 서비스가 쓸 수 있는 자원의 상한선. 갑자기 배포가 안 되거나 "
        "인스턴스가 안 뜨는 이유가 코드가 아니라 여기에 걸린 경우가 많다. "
        "미리 올려두지 않으면 급할 때 신청부터 해야 한다.",
        "We hit the account quota and cannot launch more instances.",
        "계정 할당량에 걸려서 인스턴스를 더 띄울 수 없습니다.",
    ),
    (
        "retention", "/rɪˈtenʃən/", "얼마나 오래 보관할지", OPS, N,
        "로그나 백업을 며칠 동안 남겨둘지 정한 기간. 길게 잡으면 비용이 늘고 짧게 잡으면 "
        "정작 장애를 분석할 때 그 기간의 로그가 이미 사라져 있다. 이 균형이 "
        "생각보다 자주 문제가 된다.",
        "Log retention is seven days, so last month's data is gone.",
        "로그 보관 기간이 7일이라 지난달 데이터는 없습니다.",
    ),
    (
        "smoke test", "/ˈsmoʊk ˌtest/", "배포 직후 최소한만 확인하기", OPS, N,
        "배포한 뒤 가장 중요한 기능 몇 개만 빠르게 확인하는 검사. 전원을 켰을 때 "
        "연기가 나는지 보던 데서 온 이름이다. 전부를 검증하는 게 아니라 "
        "완전히 망가진 배포를 즉시 잡아내는 것이 목적이다.",
        "Run the smoke tests right after the deploy finishes.",
        "배포가 끝나면 바로 스모크 테스트를 돌리세요.",
    ),
    # ---------- 디버깅 / 테스트 / 에러 ----------
    (
        "unit test", "/ˈjunɪt ˌtest/", "작은 단위 하나만 검사", DEBUG, E,
        "함수나 클래스 하나만 떼어내 확인하는 테스트. 데이터베이스나 네트워크를 쓰지 않아 "
        "빠르고, 실패했을 때 어디가 문제인지 바로 알 수 있다. 대신 조각들이 서로 "
        "잘 맞물리는지는 확인하지 못한다.",
        "The unit tests pass, but the two modules do not work together.",
        "유닛 테스트는 통과하는데 두 모듈이 함께 동작하지 않습니다.",
    ),
    (
        "integration test", "/ˌɪntɪˈɡreɪʃn ˌtest/", "여러 조각이 맞물리는지 검사", DEBUG, N,
        "실제 데이터베이스나 외부 호출까지 포함해 여러 부분이 함께 동작하는지 보는 테스트. "
        "유닛 테스트가 놓치는 연결 부분의 문제를 잡아준다. 느리고 환경에 영향을 받아서 "
        "수를 적게 유지하는 것이 보통이다.",
        "The integration test caught a mismatch in the column type.",
        "통합 테스트가 칼럼 타입이 맞지 않는 문제를 잡아냈습니다.",
    ),
    (
        "end-to-end test", "/ˌend tə ˈend ˌtest/", "사용자처럼 처음부터 끝까지 검사", DEBUG, N,
        "브라우저를 띄워 실제 사용자처럼 화면을 눌러가며 확인하는 테스트. 줄여서 E2E 라고 "
        "쓴다. 진짜 문제를 잡아내지만 느리고 잘 깨져서, 핵심 흐름 몇 개로 좁히는 게 "
        "일반적이다.",
        "Keep the end-to-end suite small; it takes twenty minutes to run.",
        "E2E 테스트는 20분이나 걸리니 개수를 적게 유지하세요.",
    ),
    (
        "mock", "/mɑk/", "제대로 불렸는지까지 확인하는 가짜", DEBUG, N,
        "테스트에서 진짜 대상 대신 세워두는 가짜인데, 정해진 답만 주는 스텁과 달리 "
        "'몇 번 어떤 값으로 불렸는지' 를 검증하는 것이 핵심이다. 외부 결제나 메일 "
        "발송처럼 실제로 부르면 곤란한 것을 대신한다. 너무 많이 쓰면 실제 연동이 "
        "바뀌어도 테스트는 계속 통과해서, 통과가 아무 의미도 없어진다.",
        "We mock the payment gateway so the test does not charge anyone.",
        "실제로 결제되지 않게 결제 게이트웨이를 목으로 대체합니다.",
    ),
    (
        "stub", "/stʌb/", "정해진 답만 돌려주는 가짜", DEBUG, N,
        "미리 정해둔 값을 그대로 돌려주도록 만든 가짜. 호출됐는지까지 확인하는 목과 달리 "
        "그냥 답만 준다. 어떤 응답이 오면 코드가 어떻게 동작하는지 보고 싶을 때 쓴다.",
        "Stub the API client to return a fixed error response.",
        "정해진 에러 응답을 돌려주도록 API 클라이언트를 스텁으로 만드세요.",
    ),
    (
        "fixture", "/ˈfɪkstʃər/", "테스트가 쓸 준비된 데이터", DEBUG, N,
        "테스트를 돌리기 전에 미리 만들어두는 데이터나 상태. 매번 같은 출발점에서 "
        "시작하게 해준다. 테스트끼리 같은 것을 나눠 쓰면서 앞 테스트가 남긴 흔적 때문에 "
        "실행 순서에 따라 결과가 달라지는 일이 자주 생긴다.",
        "The tests share a fixture, so they fail when run in a different order.",
        "테스트들이 픽스처를 공유해서 실행 순서가 바뀌면 실패합니다.",
    ),
    (
        "coverage", "/ˈkʌvərɪdʒ/", "테스트가 훑고 지나간 코드 비율", DEBUG, N,
        "테스트를 돌렸을 때 실제로 실행된 코드의 비율. 세는 방식이 여러 가지라 "
        "줄 단위로 세는 라인 커버리지가 100%여도, 조건 분기의 한쪽만 탔으면 "
        "브랜치 커버리지는 절반일 수 있다. 실행됐다는 뜻일 뿐 제대로 검증했다는 "
        "뜻도 아니다 - 아무것도 확인하지 않는 테스트도 수치는 올린다. "
        "그래서 목표 수치를 강제하면 형식적인 테스트만 늘어난다.",
        "Coverage went up, but none of those new tests assert anything.",
        "커버리지는 올랐지만 새 테스트들이 아무것도 검증하지 않습니다.",
    ),
    (
        "flaky", "/ˈfleɪki/", "됐다 안 됐다 하는", DEBUG, N,
        "코드를 바꾸지 않았는데 어떤 때는 통과하고 어떤 때는 실패하는 테스트. "
        "대개 시간에 의존하거나 실행 순서, 동시 실행 때문에 생긴다. 방치하면 "
        "사람들이 실패를 그냥 다시 돌려버려서 진짜 실패까지 무시하게 된다.",
        "That test is flaky; it fails about one run in ten.",
        "그 테스트는 불안정합니다. 열 번에 한 번쯤 실패합니다.",
    ),
    (
        "assertion", "/əˈsɜrʃən/", "이러해야 한다고 못박는 검사", DEBUG, E,
        "테스트에서 결과가 기대와 같은지 확인하는 문장. 여기서 실패해야 테스트가 "
        "실패한다. 검증문 없이 코드만 실행하는 테스트는 예외가 나지 않는지만 "
        "확인하는 셈이다.",
        "The test runs the function but has no assertion.",
        "이 테스트는 함수를 실행만 하고 검증문이 없습니다.",
    ),
    (
        "breakpoint", "/ˈbreɪkpɔɪnt/", "실행을 멈춰 세우는 지점", DEBUG, E,
        "코드의 특정 줄에서 실행을 멈추고 그 순간의 값을 들여다보게 하는 표시. "
        "출력문을 넣었다 지웠다 하는 것보다 훨씬 빠르다. 조건을 걸어두면 "
        "특정 값일 때만 멈추게 할 수도 있다.",
        "Set a breakpoint inside the loop and inspect the counter.",
        "반복문 안에 브레이크포인트를 걸고 카운터를 확인하세요.",
    ),
    (
        "step over", "/ˈstep ˌoʊvər/", "함수 안으로 들어가지 않고 넘기기", DEBUG, N,
        "디버거에서 다음 줄로 넘어가되 그 줄의 함수 내부로는 들어가지 않는 것. "
        "안까지 따라 들어가는 것은 step into 다. 이미 믿는 라이브러리 호출을 "
        "그냥 지나칠 때 쓴다.",
        "Step over the helper and stop at the return statement.",
        "헬퍼는 건너뛰고 return 문에서 멈추세요.",
    ),
    (
        "watch", "/wɑtʃ/", "값을 등록해두고 계속 들여다보기", DEBUG, N,
        "디버거에서 특정 변수나 식을 등록해두고 실행이 진행되는 동안 값이 어떻게 "
        "바뀌는지 계속 보는 것. 어느 시점에 값이 틀어지는지 좁힐 때 쓴다. "
        "값이 바뀌는 순간 실행을 멈춰 세우는 watchpoint 와는 다르다 - 이건 "
        "멈추지 않고 보기만 한다.",
        "Add a watch on that variable to see when it becomes null.",
        "언제 null 이 되는지 보게 그 변수를 watch 에 추가하세요.",
    ),
    (
        "profiling", "/ˈproʊfaɪlɪŋ/", "어디에 시간이 쓰였는지 재기", DEBUG, H,
        "코드의 어느 부분이 얼마나 시간을 잡아먹는지 실제로 측정하는 것. 느린 원인은 "
        "대개 예상과 다른 곳에 있어서, 추측으로 고치기 전에 먼저 하는 것이 순서다. "
        "측정 자체가 프로그램을 느리게 만든다는 점은 감안해야 한다.",
        "Profiling showed the bottleneck was JSON serialization, not the query.",
        "프로파일링해보니 병목이 쿼리가 아니라 JSON 직렬화였습니다.",
    ),
    (
        "memory leak", "/ˈmeməri ˌlik/", "안 쓰는 메모리가 안 풀리는 문제", DEBUG, H,
        "더 이상 쓰지 않는데도 참조가 남아 회수되지 않고 계속 쌓이는 메모리. "
        "가비지 컬렉션이 있는 언어에서도 어딘가 참조를 붙들고 있으면 똑같이 생긴다. "
        "지우지 않은 이벤트 리스너나 계속 커지는 캐시가 흔한 원인이다.",
        "Memory grows steadily under load, which looks like a leak.",
        "부하가 걸리면 메모리가 계속 늘어나는데 누수로 보입니다.",
    ),
    (
        "null pointer", "/ˈnʌl ˌpɔɪntər/", "없는 것을 쓰려다 나는 에러", DEBUG, E,
        "값이 없는 대상의 속성이나 메서드를 쓰려다 나는 에러. 진짜 문제는 그 줄이 아니라 "
        "왜 거기가 비어 있었는지에 있어서, 그 줄에 방어 코드를 넣는 것으로 끝내면 "
        "원인이 뒤로 밀릴 뿐이다.",
        "The null pointer is a symptom; find out why the lookup returned nothing.",
        "널 포인터는 증상입니다. 조회가 왜 아무것도 못 찾았는지 확인하세요.",
    ),
    (
        "off-by-one", "/ˌɔf baɪ ˈwʌn/", "하나 차이로 어긋나는 실수", DEBUG, N,
        "반복 횟수나 인덱스가 딱 하나 어긋나서 생기는 오류. 마지막 항목이 빠지거나 "
        "범위를 하나 넘어서 접근하는 형태로 나타난다. 시작을 0 으로 세는 것과 "
        "끝을 포함하느냐가 겹쳐서 생기고, 테스트에서 첫 항목과 마지막 항목을 "
        "확인하면 대부분 잡힌다.",
        "Classic off-by-one: the loop skips the last element.",
        "전형적인 하나 차이 오류로, 반복문이 마지막 요소를 건너뜁니다.",
    ),
    (
        "heisenbug", "/ˈhaɪzənbʌɡ/", "관찰하면 사라지는 버그", DEBUG, H,
        "디버거를 붙이거나 로그를 넣으면 재현되지 않는 버그. 관측이 대상을 바꾼다는 "
        "물리학 이야기에서 온 이름이다. 대개 타이밍이나 최적화에 얽혀 있어서, "
        "출력 대신 기록을 남겼다가 나중에 분석하는 방식으로 접근한다.",
        "Adding the log statement made it disappear; it is a heisenbug.",
        "로그를 넣었더니 사라졌습니다. 하이젠버그입니다.",
    ),
    (
        "root cause", "/ˈrut ˌkɔz/", "증상 뒤에 있는 진짜 원인", DEBUG, N,
        "겉으로 드러난 증상이 아니라 그것을 만들어낸 근본 원인. 왜를 몇 번 더 물어야 "
        "나오는 경우가 많다. 증상만 막으면 형태만 바꿔 다시 나타난다.",
        "Restarting fixed the symptom, but we still do not know the root cause.",
        "재시작으로 증상은 사라졌지만 근본 원인은 아직 모릅니다.",
    ),
    (
        "exception", "/ɪkˈsepʃən/", "정상 흐름을 끊는 오류 신호", DEBUG, E,
        "코드가 계속 진행할 수 없을 때 던져 올리는 신호. 반환값으로 오류를 알리는 "
        "방식과 달리 처리하지 않으면 위로 계속 올라가 프로그램이 멈춘다. "
        "예상 가능한 상황까지 예외로 처리하면 흐름이 오히려 읽기 어려워진다.",
        "The exception propagates up until something catches it.",
        "예외는 누군가 잡을 때까지 위로 전파됩니다.",
    ),
    (
        "swallow", "/ˈswɑloʊ/", "예외를 잡고 그냥 넘기기", DEBUG, N,
        "예외를 잡아놓고 아무 처리도 기록도 하지 않고 넘어가는 것. 당장은 에러가 "
        "안 보이지만 문제는 그대로 남아 훨씬 나중에 엉뚱한 곳에서 터진다. "
        "원인을 찾을 단서까지 함께 사라지는 것이 가장 큰 문제다.",
        "This catch block swallows the exception; at least log it.",
        "이 catch 블록이 예외를 삼키고 있습니다. 최소한 로그라도 남기세요.",
    ),
    (
        "finally", "/ˈfaɪnəli/", "성공하든 실패하든 반드시 실행", DEBUG, N,
        "예외가 났든 안 났든 마지막에 반드시 실행되는 블록. 파일이나 연결을 닫는 "
        "정리 작업을 여기에 둔다. 중간에 반환하더라도 실행되기 때문에, "
        "여기서 값을 반환하면 원래 반환값이나 예외가 덮여 사라진다.",
        "Close the connection in a finally block so it always runs.",
        "항상 실행되도록 연결 종료는 finally 블록에 두세요.",
    ),
    (
        "segmentation fault", "/ˌseɡmenˈteɪʃn ˌfɔlt/", "허용되지 않은 메모리 접근", DEBUG, H,
        "프로그램이 접근하면 안 되는 메모리를 건드려 운영체제가 강제로 종료시키는 것. "
        "줄여서 segfault 라고 한다. 문제가 난 지점과 실제 원인이 멀리 떨어져 있는 "
        "경우가 많아 추적이 어렵다. 정처기에서는 메모리 보호와 함께 다룬다.",
        "The process died with a segmentation fault right after startup.",
        "프로세스가 시작 직후 세그멘테이션 폴트로 죽었습니다.",
    ),
    (
        "panic", "/ˈpænɪk/", "복구를 포기하고 즉시 중단", DEBUG, N,
        "더 진행하면 위험하다고 판단해 프로그램이 즉시 멈추는 것. Go 나 Rust 에서 "
        "쓰는 말이다. 예외처럼 붙잡아 계속 진행하라는 용도가 아니라, 있어서는 안 될 "
        "상태에 도달했음을 알리는 쪽에 가깝다.",
        "The service panics on startup when the config file is missing.",
        "설정 파일이 없으면 서비스가 시작 시 패닉으로 종료됩니다.",
    ),
    (
        "lint", "/lɪnt/", "돌리기 전에 문제를 찾아주는 검사", DEBUG, E,
        "코드를 실행하지 않고 훑어서 오류 가능성이나 스타일 문제를 찾아주는 도구. "
        "쓰지 않는 변수나 빠진 반환처럼 사람이 놓치기 쉬운 것을 잡는다. "
        "규칙이 너무 시끄러우면 사람들이 통째로 꺼버리므로 조절이 필요하다.",
        "The lint step is failing on an unused import.",
        "쓰지 않는 import 때문에 린트 단계가 실패하고 있습니다.",
    ),
    (
        "static analysis", "/ˈstætɪk əˌnæləsɪs/", "실행하지 않고 코드를 분석", DEBUG, H,
        "프로그램을 돌리지 않은 채 코드만 보고 문제를 찾아내는 것. 테스트가 실행해본 "
        "경로만 확인하는 것과 달리 실행되지 않는 경로까지 본다. 대신 실제로는 "
        "일어나지 않는 상황까지 경고하는 오탐이 섞인다.",
        "Static analysis flagged a possible null dereference in that branch.",
        "정적 분석이 그 분기에서 널 참조 가능성을 지적했습니다.",
    ),
    (
        "type error", "/ˈtaɪp ˌerər/", "형식이 맞지 않아 나는 오류", DEBUG, E,
        "숫자가 와야 할 자리에 문자열이 오는 것처럼 값의 형식이 맞지 않아 나는 오류. "
        "타입을 미리 검사하는 언어는 실행 전에 잡아주지만, 그렇지 않은 언어에서는 "
        "실제로 그 줄이 실행되는 순간에야 드러난다.",
        "The type error only shows up when that branch actually runs.",
        "그 분기가 실제로 실행될 때만 타입 오류가 드러납니다.",
    ),
    (
        "syntax error", "/ˈsɪntæks ˌerər/", "문법이 틀려 아예 못 읽는 오류", DEBUG, E,
        "괄호가 안 닫혔거나 문법이 어긋나 코드를 해석조차 못 하는 오류. 실행이 "
        "시작되기도 전에 난다. 알려주는 줄 번호는 문제가 드러난 곳이라, "
        "실제 원인은 대개 그 앞줄에 있다.",
        "The syntax error points at line 40, but the missing brace is on line 38.",
        "문법 오류가 40번 줄을 가리키지만 빠진 중괄호는 38번 줄에 있습니다.",
    ),
    (
        "runtime error", "/ˈrʌntaɪm ˌerər/", "실행 도중에 터지는 오류", DEBUG, E,
        "문법은 맞아서 실행은 시작됐는데 도중에 나는 오류. 0 으로 나누거나 없는 값을 "
        "쓰는 경우가 여기 해당한다. 특정 입력에서만 나타나기 때문에 테스트에서 "
        "그 입력을 다루지 않으면 그대로 배포된다.",
        "It compiles fine but throws a runtime error on empty input.",
        "빌드는 되는데 빈 입력이 들어오면 런타임 오류가 납니다.",
    ),
    (
        "silent failure", "/ˈsaɪlənt ˌfeɪljər/", "티 안 나게 실패하기", DEBUG, N,
        "실패했는데 아무 오류도 보이지 않아 성공한 것처럼 보이는 상황. 예외를 삼키거나 "
        "실패해도 기본값을 돌려줄 때 생긴다. 데이터가 조용히 어긋나기 때문에 "
        "터지는 에러보다 훨씬 나쁘다.",
        "The job silently failed for a week before anyone noticed.",
        "그 작업이 일주일 동안 조용히 실패하고 있었는데 아무도 몰랐습니다.",
    ),
    (
        "happy path", "/ˈhæpi ˌpæθ/", "모든 게 잘될 때의 흐름", DEBUG, N,
        "입력도 정상이고 외부 호출도 성공하는, 아무 문제 없는 경우의 흐름. "
        "개발과 시연은 대개 이 경로만 따라간다. 실제 장애는 그 바깥에서 나기 때문에 "
        "실패하는 경우를 함께 만들어보는 것이 중요하다.",
        "We only tested the happy path, so the timeout case was never covered.",
        "정상 흐름만 테스트해서 타임아웃 상황은 다뤄본 적이 없습니다.",
    ),
    (
        "boundary value", "/ˈbaʊndri ˌvælju/", "경계에 딱 걸친 값", DEBUG, N,
        "허용 범위의 맨 처음과 맨 끝, 그리고 그 바로 바깥의 값. 오류는 범위 한가운데가 "
        "아니라 경계에서 나기 때문에 여기를 먼저 시험한다. 정처기 테스트 기법 "
        "문제에 자주 나온다.",
        "Add boundary value cases for zero and the maximum length.",
        "0 과 최대 길이에 대한 경계값 케이스를 추가하세요.",
    ),
    (
        "regression test", "/rɪˈɡreʃən ˌtest/", "바꾼 뒤에도 기존 기능이 멀쩡한지 검사", DEBUG, N,
        "코드를 바꾼 뒤 원래 잘 되던 기능이 여전히 동작하는지 확인하는 테스트. "
        "고친 버그가 다시 나타나지 않는지 보는 것은 그중 한 갈래일 뿐이다. "
        "버그를 고칠 때 먼저 재현 테스트를 만들고 고치면 자연스럽게 하나 생긴다.",
        "Write a regression test that reproduces the bug before fixing it.",
        "고치기 전에 그 버그를 재현하는 회귀 테스트를 먼저 작성하세요.",
    ),
    (
        "snapshot test", "/ˈsnæpʃɑt ˌtest/", "결과를 통째로 저장해 비교", DEBUG, N,
        "출력 결과를 파일로 저장해두고 다음 실행 결과와 통째로 비교하는 테스트. "
        "쉽게 만들 수 있지만 왜 그 결과가 맞는지는 검증하지 않는다. 실패했을 때 "
        "확인 없이 새 결과로 덮어버리면 테스트가 아무 의미도 없어진다.",
        "Do not update the snapshot without reading the diff.",
        "차이를 확인하지 않고 스냅샷을 갱신하지 마세요.",
    ),
    (
        "TDD", "/ˌti di ˈdi/", "테스트를 먼저 쓰고 구현하기", DEBUG, N,
        "실패하는 테스트를 먼저 만들고 그걸 통과시키는 순서로 개발하는 방식. "
        "테스트를 많이 쓰자는 얘기가 아니라, 무엇을 만들지 먼저 정의하게 만드는 "
        "설계 방법에 가깝다.",
        "With TDD you write the failing test first, then make it pass.",
        "TDD 에서는 실패하는 테스트를 먼저 쓰고 그다음에 통과시킵니다.",
    ),
    (
        "load test", "/ˈloʊd ˌtest/", "예상 부하를 걸어보는 시험", DEBUG, N,
        "실제로 예상되는 만큼의 요청을 보내 견디는지 확인하는 시험. 기능이 맞는지가 "
        "아니라 그 규모에서도 되는지를 본다. 운영과 다른 사양에서 재면 숫자를 "
        "그대로 믿을 수 없다.",
        "The load test showed the connection pool is too small.",
        "부하 테스트 결과 커넥션 풀이 너무 작다는 게 드러났습니다.",
    ),
    (
        "stress test", "/ˈstres ˌtest/", "한계를 넘겨 무너지는 지점 보기", DEBUG, H,
        "감당 가능한 수준을 넘겨 밀어붙여 어디서 어떻게 무너지는지 보는 시험. "
        "부하 테스트가 견디는지를 본다면 이건 무너지는 방식을 본다. 무너지더라도 "
        "복구가 되는지가 실제로 중요한 부분이다.",
        "Under stress testing, the service stopped recovering after the spike.",
        "스트레스 테스트에서 급증 이후 서비스가 회복되지 않았습니다.",
    ),
    (
        "verbose", "/vərˈboʊs/", "자세히 다 출력하는", DEBUG, E,
        "실행 과정을 최대한 자세히 출력하게 하는 설정. 문제가 있을 때 명령에 붙여 "
        "무엇이 진행되고 있는지 본다. 발음이 '버보스' 가 아니라 뒤에 강세가 오는 "
        "'버보우스' 에 가깝다.",
        "Run it with the verbose flag to see what it is actually doing.",
        "실제로 뭘 하고 있는지 보려면 verbose 옵션을 붙여 실행하세요.",
    ),
    (
        "reproducible", "/ˌriprəˈdusəbl/", "같은 조건에서 다시 나타나는", DEBUG, N,
        "정해진 절차를 따르면 문제가 다시 나타나는 상태. 여기까지 오면 고치는 것은 "
        "시간 문제라, 버그 처리에서 가장 큰 산은 대개 이 단계다. 어떤 데이터와 "
        "어떤 환경에서였는지까지 적어야 재현이 된다.",
        "We cannot fix it until we have a reproducible case.",
        "재현 가능한 사례가 나오기 전에는 고칠 수 없습니다.",
    ),
    (
        "debug log", "/ˈdibʌɡ ˌlɔɡ/", "진단용으로 남기는 상세 기록", DEBUG, E,
        "문제를 살펴보려고 평소보다 자세히 남기는 기록. 평소에는 꺼두고 필요할 때 "
        "켜는 것이 보통인데, 켜두면 양이 폭증하고 개인정보나 토큰이 그대로 찍힐 수 "
        "있어 조심해야 한다.",
        "Turn on debug logs for that module and reproduce the issue.",
        "그 모듈의 디버그 로그를 켜고 문제를 재현해보세요.",
    ),
    (
        "sanity check", "/ˈsænəti ˌtʃek/", "당연한 것부터 확인하기", DEBUG, E,
        "복잡한 원인을 파기 전에 기본 전제가 맞는지 빠르게 확인하는 것. 서버가 떠 있는지, "
        "보고 있는 환경이 맞는지 같은 것들이다. 오래 헤맨 문제의 상당수가 "
        "여기서 끝난다.",
        "Sanity check first: are you even hitting the right environment?",
        "먼저 기본부터 확인합시다. 지금 보고 있는 환경이 맞나요?",
    ),
    (
        "postcondition", "/ˌpoʊstkənˈdɪʃn/", "끝났을 때 성립해야 할 조건", DEBUG, H,
        "함수가 정상적으로 끝났다면 반드시 참이어야 하는 조건. 반대로 시작할 때 "
        "만족해야 하는 것이 전제 조건이다. 이걸 명시해두면 어느 쪽 책임인지가 "
        "분명해져서 문제 구간을 좁히기 쉬워진다.",
        "The postcondition is that the list is never empty on success.",
        "성공했다면 목록이 비어 있지 않다는 것이 사후 조건입니다.",
    ),
    (
        "core dump", "/ˈkɔr ˌdʌmp/", "죽는 순간의 메모리를 통째로 저장", DEBUG, H,
        "프로그램이 비정상 종료될 때 그 순간의 메모리 상태를 파일로 남긴 것. "
        "재현이 어려운 문제를 나중에 분석할 수 있게 해준다. 메모리에 있던 비밀값까지 "
        "그대로 담기므로 다룰 때 주의가 필요하다.",
        "Enable core dumps so we can analyze the crash afterwards.",
        "나중에 크래시를 분석할 수 있게 코어 덤프를 켜두세요.",
    ),
    (
        "warning", "/ˈwɔrnɪŋ/", "지금은 되지만 문제가 될 신호", DEBUG, E,
        "당장 실패하지는 않지만 문제가 될 수 있다고 알려주는 메시지. 쌓이면 아무도 "
        "읽지 않게 되고, 그 사이에 진짜 중요한 경고가 묻힌다. 그래서 경고를 "
        "오류로 취급해 아예 쌓이지 않게 하는 팀도 많다.",
        "There are 200 warnings in the build, so nobody reads them anymore.",
        "빌드에 경고가 200개라 아무도 읽지 않습니다.",
    ),
    # ---------- 프론트엔드 ----------
    (
        "component", "/kəmˈpoʊnənt/", "화면을 이루는 재사용 조각", FRONT, E,
        "화면의 일부를 독립된 조각으로 만들어 이름을 붙인 것. 같은 모양을 여러 곳에서 "
        "쓰려고 나누기도 하지만, 한 번만 쓰더라도 관심사를 나누려고 쪼개는 경우가 더 많다. "
        "지나치게 잘게 나누면 오히려 흐름을 따라가기 어려워진다.",
        "Extract this into a separate component so we can reuse it.",
        "재사용할 수 있게 이 부분을 별도 컴포넌트로 빼세요.",
    ),
    (
        "props", "/prɑps/", "부모가 자식에게 내려주는 값", FRONT, E,
        "컴포넌트가 바깥에서 받는 입력값. 받은 쪽에서 직접 바꾸지 않는 것이 원칙이라, "
        "값을 바꾸려면 부모에게 알려 부모가 바꾸게 한다. 데이터는 위에서 아래로만 "
        "흐른다는 규칙이 여기서 나온다.",
        "Pass the user id down as a prop instead of reading it again.",
        "다시 조회하지 말고 사용자 아이디를 prop 으로 내려주세요.",
    ),
    (
        "state", "/steɪt/", "컴포넌트가 스스로 들고 있는 값", FRONT, E,
        "컴포넌트 안에서 바뀌는 값. 이 값이 바뀌면 화면이 다시 그려진다. 값을 직접 "
        "고치지 않고 정해진 함수로 바꿔야 변경을 알아채는데, 배열이나 객체를 그 자리에서 "
        "수정하면 바뀐 걸 못 알아채 화면이 그대로인 문제가 자주 생긴다.",
        "The list does not update because you mutated the state array in place.",
        "상태 배열을 직접 수정해서 목록이 갱신되지 않습니다.",
    ),
    (
        "lifecycle", "/ˈlaɪfsaɪkl/", "생겨나고 사라지기까지의 단계", FRONT, N,
        "컴포넌트가 화면에 붙고, 갱신되고, 떨어져 나가는 일련의 단계. 각 시점에 "
        "코드를 끼워 넣을 수 있다. 사라질 때 정리하는 단계를 빠뜨리면 타이머나 "
        "구독이 계속 살아남아 메모리 누수가 된다.",
        "Clean up the subscription when the component unmounts.",
        "컴포넌트가 화면에서 사라질 때 구독을 정리하세요.",
    ),
    (
        "render", "/ˈrendər/", "화면에 그려내기", FRONT, E,
        "데이터를 바탕으로 실제 화면 요소를 만들어내는 과정. 값이 바뀔 때마다 다시 "
        "일어난다. 다시 그렸다고 브라우저 화면 전체가 새로 칠해지는 것은 아니고, "
        "달라진 부분만 반영되는 것이 보통이다.",
        "This component re-renders on every keystroke.",
        "이 컴포넌트가 키를 누를 때마다 다시 렌더링됩니다.",
    ),
    (
        "virtual DOM", "/ˈvɜrtʃuəl ˌdɑm/", "실제 화면 대신 쓰는 가벼운 사본", FRONT, H,
        "실제 화면 구조를 메모리 안의 가벼운 객체로 흉내 내두고, 바뀐 부분만 골라 "
        "진짜 화면에 반영하는 방식. 실제 화면을 건드리는 비용이 크기 때문에 나온 방법이다. "
        "언제나 더 빠른 것은 아니고, 손으로 최소한만 고치는 것보다 느릴 수도 있다.",
        "The virtual DOM diff decides which nodes actually change.",
        "가상 DOM 비교가 실제로 어떤 노드를 바꿀지 결정합니다.",
    ),
    (
        "reconciliation", "/ˌrekənˌsɪliˈeɪʃn/", "무엇이 바뀌었는지 맞춰보기", FRONT, H,
        "이전 화면 구조와 새 구조를 비교해 무엇을 고칠지 정하는 과정. 목록에서는 "
        "각 항목에 붙은 키를 보고 같은 것인지 판단한다. 그래서 키를 순번으로 주면 "
        "항목을 지웠을 때 엉뚱한 것이 남거나 입력값이 뒤섞인다.",
        "Reconciliation uses the key to tell which items are the same.",
        "재조정 과정에서 키를 보고 어떤 항목이 같은지 판단합니다.",
    ),
    (
        "key", "/ki/", "목록 항목을 구분하는 표시", FRONT, N,
        "반복해서 그리는 목록에서 각 항목을 구분하려고 붙이는 값. 순번을 쓰면 항목이 "
        "추가되거나 지워질 때 번호가 밀려서, 지운 항목의 입력값이 다른 항목에 남는 "
        "이상한 현상이 생긴다. 데이터 고유 아이디를 쓰는 것이 정답이다.",
        "Use a stable id as the key, not the array index.",
        "배열 인덱스 말고 안정적인 아이디를 키로 쓰세요.",
    ),
    (
        "SSR", "/ˌes es ˈɑr/", "서버에서 화면을 미리 그려 보내기", FRONT, H,
        "브라우저가 아니라 서버에서 HTML 을 완성해 보내는 방식. 첫 화면이 빨리 보이고 "
        "검색 엔진이 내용을 읽을 수 있다. 대신 서버가 매 요청마다 렌더링해야 해서 "
        "부하가 늘고, 브라우저에만 있는 window 같은 것을 쓰면 서버에서 터진다.",
        "That code breaks under SSR because window does not exist on the server.",
        "서버에는 window 가 없어서 그 코드는 SSR 에서 깨집니다.",
    ),
    (
        "CSR", "/ˌsi es ˈɑr/", "브라우저에서 화면을 그리기", FRONT, N,
        "서버는 거의 빈 HTML 만 주고 브라우저가 스크립트를 받아 화면을 그리는 방식. "
        "화면 전환이 매끄럽지만 첫 화면이 뜰 때까지 흰 화면이 보이고, "
        "스크립트를 실행하지 않는 크롤러에게는 내용이 비어 보인다.",
        "With CSR the page is blank until the bundle loads.",
        "CSR 에서는 번들이 로드될 때까지 페이지가 비어 있습니다.",
    ),
    (
        "hydration", "/haɪˈdreɪʃn/", "서버가 그린 화면에 동작을 붙이기", FRONT, H,
        "서버에서 만든 HTML 을 브라우저가 받은 뒤 이벤트 처리를 연결해 실제로 "
        "움직이게 만드는 과정. 화면은 이미 보이는데 버튼이 안 눌리는 짧은 순간이 "
        "이것 때문이다. 서버와 브라우저가 그린 결과가 다르면 불일치 오류가 난다.",
        "The page renders but stays unresponsive until hydration finishes.",
        "페이지는 보이지만 하이드레이션이 끝날 때까지 반응하지 않습니다.",
    ),
    (
        "bundle", "/ˈbʌndəl/", "여러 파일을 하나로 묶은 결과물", FRONT, E,
        "흩어진 자바스크립트 파일들을 하나로 합쳐 브라우저가 받기 좋게 만든 파일. "
        "요청 수가 줄어드는 대신 파일 하나가 커져서, 첫 화면에 필요 없는 코드까지 "
        "함께 받게 된다. 그래서 나누는 기법이 따로 있다.",
        "The bundle is 3MB, which is why the first load is slow.",
        "번들이 3MB 라서 첫 로딩이 느립니다.",
    ),
    (
        "code splitting", "/ˈkoʊd ˌsplɪtɪŋ/", "필요할 때 나눠 받게 쪼개기", FRONT, N,
        "번들을 여러 조각으로 나눠 지금 필요한 것만 먼저 받게 하는 것. 첫 화면에서 "
        "쓰지 않는 화면의 코드를 나중으로 미룬다. 너무 잘게 나누면 요청이 많아져 "
        "오히려 느려질 수 있다.",
        "Code splitting cut the initial bundle almost in half.",
        "코드 스플리팅으로 초기 번들이 거의 절반으로 줄었습니다.",
    ),
    (
        "tree shaking", "/ˈtri ˌʃeɪkɪŋ/", "안 쓰는 코드를 털어내기", FRONT, H,
        "가져왔지만 실제로 쓰지 않는 코드를 최종 결과물에서 빼는 것. 나무를 흔들어 "
        "마른 잎을 떨어뜨리는 데서 온 이름이다. 어느 코드가 쓰이는지 정적으로 알 수 "
        "있어야 하므로, 불러오는 방식에 따라 전혀 걸러지지 않기도 한다.",
        "Import only what you need so tree shaking can drop the rest.",
        "트리 셰이킹이 나머지를 걸러낼 수 있게 필요한 것만 import 하세요.",
    ),
    (
        "minify", "/ˈmɪnɪfaɪ/", "공백과 이름을 줄여 파일 축소", FRONT, N,
        "공백과 줄바꿈을 없애고 변수명을 짧게 바꿔 파일 크기를 줄이는 것. 동작은 "
        "그대로지만 사람이 읽을 수 없게 된다. 그래서 운영 환경 오류 메시지가 "
        "알아볼 수 없는 형태로 나오고, 소스맵이 필요해진다.",
        "The minified stack trace is useless without a source map.",
        "소스맵 없이는 압축된 스택 트레이스가 쓸모없습니다.",
    ),
    (
        "source map", "/ˈsɔrs ˌmæp/", "압축된 코드를 원본과 이어주는 지도", FRONT, N,
        "변환되고 압축된 코드가 원래 어느 파일 몇 번째 줄이었는지 알려주는 파일. "
        "이게 있어야 운영 환경 오류를 원본 위치로 되짚을 수 있다. 공개해두면 "
        "원본 코드가 그대로 노출되므로 오류 수집 도구에만 올리는 경우가 많다.",
        "Upload the source map to the error tracker, not to the public server.",
        "소스맵은 공개 서버가 아니라 오류 추적 도구에 올리세요.",
    ),
    (
        "transpile", "/trænˈspaɪl/", "새 문법을 옛 문법으로 바꾸기", FRONT, N,
        "최신 문법으로 쓴 코드를 옛 브라우저도 이해하는 형태로 옮기는 것. 문법만 "
        "바꿔줄 뿐 없는 기능을 만들어주지는 않아서, 빠진 기능은 폴리필로 따로 "
        "채워야 한다. 이 둘을 혼동해 옛 브라우저에서 오류가 나는 경우가 많다.",
        "Transpiling does not add missing methods; you still need a polyfill.",
        "트랜스파일은 없는 메서드를 만들어주지 않습니다. 폴리필이 따로 필요합니다.",
    ),
    (
        "polyfill", "/ˈpɑlifɪl/", "없는 기능을 직접 채워 넣기", FRONT, N,
        "옛 환경에 없는 기능을 같은 이름으로 직접 구현해 채워 넣는 코드. 문법 변환과 "
        "달리 실행 시점에 기능 자체를 보태준다. 필요 없는 브라우저에도 전부 실어 보내면 "
        "번들만 무거워진다.",
        "We only load the polyfill for browsers that need it.",
        "필요한 브라우저에만 폴리필을 로드합니다.",
    ),
    (
        "DOM", "/dɑm/", "화면 구조를 다루는 객체 모형", FRONT, E,
        "HTML 문서를 코드에서 다룰 수 있게 나무 구조의 객체로 표현한 것. HTML 문자열 "
        "자체가 아니라 브라우저가 그것을 읽어 만든 구조다. 그래서 스크립트로 바꾼 내용은 "
        "페이지 소스 보기에는 나타나지 않는다. '돔' 으로 읽는다.",
        "Inspect the DOM in devtools; the source view will not show the change.",
        "개발자 도구에서 DOM 을 확인하세요. 소스 보기에는 변경이 안 나옵니다.",
    ),
    (
        "event bubbling", "/ɪˈvent ˌbʌblɪŋ/", "이벤트가 위로 올라가며 전달", FRONT, N,
        "어떤 요소에서 일어난 이벤트가 부모, 그 부모로 차례차례 올라가며 전달되는 것. "
        "안쪽 버튼을 눌렀는데 바깥 영역의 처리까지 함께 실행되는 이유다. "
        "그 전에 위에서 아래로 내려가는 캡처링 단계가 먼저 있고, 대상에 닿은 뒤 "
        "다시 올라오는 것이 버블링이다 - 보통 쓰는 리스너는 올라올 때 동작한다. "
        "필요하면 전파를 멈출 수 있지만, 남용하면 다른 기능이 조용히 동작하지 않게 된다.",
        "The click bubbles up and closes the modal; stop propagation there.",
        "클릭이 위로 전파돼 모달이 닫힙니다. 거기서 전파를 막으세요.",
    ),
    (
        "event delegation", "/ɪˈvent ˌdeləˌɡeɪʃn/", "부모 하나로 자식들 이벤트 처리", FRONT, H,
        "자식마다 처리기를 붙이는 대신 부모에 하나만 붙여 올라오는 이벤트를 받아 "
        "처리하는 방식. 항목이 많아도 처리기가 하나라 가볍고, 나중에 추가된 항목도 "
        "따로 붙이지 않아도 동작한다.",
        "Use event delegation instead of binding a handler to every row.",
        "행마다 핸들러를 붙이지 말고 이벤트 위임을 쓰세요.",
    ),
    (
        "reflow", "/ˈrifloʊ/", "위치와 크기를 다시 계산하기", FRONT, H,
        "요소의 크기나 위치가 바뀌어 브라우저가 배치를 다시 계산하는 것. 비용이 큰 "
        "작업이라 반복문 안에서 크기를 읽고 바꾸기를 반복하면 매 바퀴마다 계산이 "
        "강제로 일어나 눈에 띄게 느려진다.",
        "Setting a style and then reading offsetHeight in the loop forces a reflow every iteration.",
        "반복문 안에서 스타일을 바꾼 뒤 offsetHeight 를 읽으면 매번 리플로우가 강제됩니다.",
    ),
    (
        "repaint", "/ˌriˈpeɪnt/", "색만 다시 칠하기", FRONT, N,
        "배치는 그대로인데 색이나 그림자처럼 겉모습만 바뀌어 다시 그리는 것. "
        "위치 계산을 다시 하는 리플로우보다는 가볍다. 애니메이션을 만들 때 "
        "배치를 건드리지 않는 속성을 고르라는 조언이 여기서 나온다.",
        "Animating color only triggers a repaint, not a reflow.",
        "색을 애니메이션하면 리플로우 없이 리페인트만 발생합니다.",
    ),
    (
        "layout shift", "/ˈleɪaʊt ˌʃɪft/", "읽는 중에 화면이 밀리는 현상", FRONT, N,
        "늦게 로드된 이미지나 광고 때문에 이미 보이던 내용이 아래로 밀리는 현상. "
        "누르려던 버튼이 이동해 엉뚱한 곳을 누르게 만든다. 이미지에 크기를 미리 "
        "지정해 자리를 잡아두면 대부분 막을 수 있다.",
        "Set explicit image dimensions to avoid layout shift.",
        "레이아웃 이동을 막으려면 이미지 크기를 명시하세요.",
    ),
    (
        "viewport", "/ˈvjupɔrt/", "지금 보이는 화면 영역", FRONT, E,
        "브라우저에서 실제로 내용이 보이는 영역. 기기 화면 크기와 같지 않을 수 있고, "
        "모바일에서는 주소창이 접히고 펴지면서 높이가 변한다. 화면 높이를 100퍼센트로 "
        "잡았을 때 모바일에서 잘리는 문제가 여기서 온다.",
        "The full-height section gets cut off in the mobile viewport.",
        "전체 높이 섹션이 모바일 뷰포트에서 잘립니다.",
    ),
    (
        "media query", "/ˈmidiə ˌkwɪri/", "화면 조건에 따라 다른 스타일", FRONT, E,
        "화면 너비 같은 조건에 따라 다른 스타일을 적용하게 하는 규칙. 이걸로 "
        "화면 크기별 대응을 만든다. 기기를 구분하는 게 아니라 조건을 보는 것이라, "
        "작은 창으로 줄인 데스크톱도 모바일 스타일을 받는다.",
        "Add a media query so the sidebar collapses on small screens.",
        "작은 화면에서 사이드바가 접히도록 미디어 쿼리를 추가하세요.",
    ),
    (
        "responsive", "/rɪˈspɑnsɪv/", "화면 크기에 맞게 바뀌는", FRONT, E,
        "화면 크기에 따라 배치가 알아서 맞춰지는 방식. 모바일용 페이지를 따로 만드는 "
        "것과 다르게 하나의 페이지가 여러 크기에 대응한다. 화면이 작아진 만큼 "
        "보여줄 것을 고르는 판단이 실제로는 더 어려운 부분이다.",
        "Make the table responsive; it overflows on mobile.",
        "테이블이 모바일에서 넘칩니다. 반응형으로 만들어주세요.",
    ),
    (
        "specificity", "/ˌspesɪˈfɪsəti/", "어느 스타일이 이길지 정하는 점수", FRONT, H,
        "같은 요소에 여러 스타일 규칙이 걸렸을 때 어느 것이 적용될지 정하는 우선순위. "
        "먼저 명시도로 비교하고, 명시도가 같을 때에만 나중에 쓴 것이 이긴다. "
        "그래서 아래에 덧붙였는데도 안 먹는 일이 생긴다. 스타일이 안 먹는다고 "
        "계속 덧붙이다 보면 아무도 손댈 수 없는 규칙 더미가 된다.",
        "The style is not applied because the other rule has higher specificity.",
        "다른 규칙의 명시도가 더 높아서 이 스타일이 적용되지 않습니다.",
    ),
    (
        "box model", "/ˈbɑks ˌmɑdl/", "요소 크기를 이루는 층 구조", FRONT, N,
        "요소의 내용, 안쪽 여백, 테두리, 바깥 여백이 겹겹이 쌓여 크기를 이루는 구조. "
        "기본 설정에서는 지정한 너비가 내용 부분만 뜻해서, 여백을 주면 전체가 커진다. "
        "이걸 바꾸는 설정을 대부분의 프로젝트가 맨 앞에 넣어둔다.",
        "Set box-sizing to border-box so padding does not change the width.",
        "패딩이 너비를 바꾸지 않도록 box-sizing 을 border-box 로 설정하세요.",
    ),
    (
        "z-index", "/ˈzi ˌɪndeks/", "겹쳤을 때 누가 위로 올지", FRONT, H,
        "요소들이 겹칠 때 앞뒤 순서를 정하는 값. 숫자가 크면 무조건 위로 오는 게 아니라, "
        "부모가 만든 층 안에서만 비교된다. 그래서 9999 를 줘도 모달이 뒤에 깔리는 "
        "일이 생기고, 이때 봐야 할 것은 숫자가 아니라 부모다.",
        "The modal is behind the header even with a huge z-index.",
        "z-index 를 크게 줬는데도 모달이 헤더 뒤에 있습니다.",
    ),
    (
        "flexbox", "/ˈfleksbɑks/", "한 축을 따라 배치하는 방식", FRONT, N,
        "요소들을 가로나 세로 한 축으로 늘어놓고 남는 공간을 나눠주는 배치 방식. "
        "가운데 정렬처럼 예전에 까다롭던 것이 쉬워졌다. wrap 을 주면 여러 줄이 "
        "되지만 각 줄을 따로 다룰 뿐이라, 행과 열을 함께 맞춰야 하는 배치에는 "
        "그리드가 더 맞는다.",
        "Use flexbox for the toolbar; it is a single row.",
        "툴바는 한 줄이니 flexbox 를 쓰세요.",
    ),
    (
        "grid", "/ɡrɪd/", "행과 열로 짜는 배치 방식", FRONT, N,
        "가로줄과 세로줄을 함께 정의해 격자 위에 요소를 놓는 배치 방식. 두 방향을 "
        "동시에 다룬다는 점이 flexbox 와의 결정적인 차이다. 전체 페이지 골격을 "
        "잡을 때 특히 잘 맞는다.",
        "The page layout uses grid, and the cards inside use flexbox.",
        "페이지 레이아웃은 그리드를, 안쪽 카드는 flexbox 를 씁니다.",
    ),
    (
        "accessibility", "/əkˌsesəˈbɪləti/", "누구나 쓸 수 있게 만들기", FRONT, N,
        "시각이나 조작에 제약이 있는 사람도 쓸 수 있도록 만드는 것. 줄여서 a11y 라고 "
        "쓴다. 화면 낭독기가 읽을 수 있는 구조와 키보드만으로 조작 가능한 흐름이 "
        "핵심이고, 대부분은 의미에 맞는 태그를 쓰는 것만으로 크게 좋아진다.",
        "Buttons made from divs break keyboard accessibility.",
        "div 로 만든 버튼은 키보드 접근성을 해칩니다.",
    ),
    (
        "semantic HTML", "/sɪˈmæntɪk ˌeɪtʃ ti em ˌel/", "의미에 맞는 태그 쓰기", FRONT, N,
        "생김새가 아니라 역할에 맞는 태그를 쓰는 것. 버튼은 button, 제목은 heading 을 "
        "쓰는 식이다. 화면 낭독기와 검색 엔진이 구조를 이해하고, 키보드 조작이나 "
        "기본 동작을 따로 만들지 않아도 된다.",
        "Use a real button element instead of a clickable div.",
        "클릭 가능한 div 말고 실제 button 요소를 쓰세요.",
    ),
    (
        "ARIA", "/ˈɑriə/", "보조 기술에 역할을 알려주는 속성", FRONT, H,
        "화면 낭독기에게 이 요소가 무엇이고 어떤 상태인지 알려주는 속성 모음. "
        "의미에 맞는 태그로 해결되면 굳이 쓰지 않는 것이 원칙이고, 잘못 붙이면 "
        "아예 없느니만 못하다. '아리아' 로 읽는다.",
        "Do not add ARIA roles to elements that already have the right semantics.",
        "이미 의미가 맞는 요소에 ARIA 역할을 덧붙이지 마세요.",
    ),
    (
        "controlled component", "/kənˈtroʊld kəmˌpoʊnənt/", "입력값을 코드가 쥐고 있는 방식", FRONT, H,
        "입력 필드의 값을 브라우저가 아니라 상태가 들고 있고, 입력이 있을 때마다 "
        "상태를 갱신해 다시 내려주는 방식. 검증이나 초기화가 쉬워지지만 매 입력마다 "
        "다시 그려서 폼이 크면 느려질 수 있다.",
        "The input is a controlled component, so the value comes from state.",
        "이 입력은 제어 컴포넌트라 값이 상태에서 옵니다.",
    ),
    (
        "prop drilling", "/ˈprɑp ˌdrɪlɪŋ/", "값을 여러 층 아래로 계속 넘기기", FRONT, N,
        "깊은 곳에 있는 컴포넌트에 값을 주려고 중간 컴포넌트들이 쓰지도 않는 값을 "
        "계속 받아 넘기는 상황. 중간 단계가 불필요하게 얽히고, 값 하나를 추가할 때마다 "
        "여러 파일을 고쳐야 한다. 공유 저장소나 컨텍스트로 푼다.",
        "This prop is drilled through four levels; move it into context.",
        "이 prop 이 네 단계를 거쳐 내려갑니다. 컨텍스트로 옮기세요.",
    ),
    (
        "memoization", "/ˌmemoʊɪˈzeɪʃn/", "계산 결과를 기억해 재사용", FRONT, H,
        "같은 입력에 대한 계산 결과를 저장해두고 다음에 그대로 쓰는 것. 무거운 계산이나 "
        "불필요한 다시 그리기를 줄인다. 비교하는 비용과 기억하는 비용이 있어서 "
        "가벼운 계산에 붙이면 오히려 손해다.",
        "Memoize the filtered list; it is recalculated on every render.",
        "필터링된 목록이 렌더링마다 다시 계산됩니다. 메모이제이션하세요.",
    ),
    (
        "debounce", "/dɪˈbaʊns/", "잠잠해진 뒤에 한 번만 실행", FRONT, N,
        "이벤트가 연달아 일어날 때 마지막 이후 일정 시간 조용해지면 그때 한 번만 "
        "실행하는 것. 검색어를 칠 때마다 요청을 보내지 않게 할 때 쓴다. 정해진 간격마다 "
        "한 번씩 실행하는 방식과는 다른 동작이다.",
        "Debounce the search input so we do not fire a request per keystroke.",
        "키 입력마다 요청이 나가지 않게 검색 입력에 디바운스를 거세요.",
    ),
    (
        "SPA", "/ˌes pi ˈeɪ/", "한 페이지 안에서 화면을 바꾸는 앱", FRONT, N,
        "페이지를 새로 불러오지 않고 필요한 부분만 바꿔가며 화면을 전환하는 방식. "
        "전환이 매끄럽지만 주소 관리, 뒤로가기, 스크롤 위치 복원 같은 것을 "
        "직접 처리해야 한다.",
        "In an SPA you have to handle the back button yourself.",
        "SPA 에서는 뒤로가기 동작을 직접 처리해야 합니다.",
    ),
    (
        "client-side routing", "/ˈklaɪənt saɪd ˌrutɪŋ/", "서버를 거치지 않고 화면 전환", FRONT, N,
        "링크를 눌러도 서버에 요청하지 않고 브라우저에서 주소만 바꿔 화면을 갈아 끼우는 것. "
        "그 주소를 새로고침하면 서버가 그 경로를 모르기 때문에 404 가 나는데, "
        "서버에서 모든 경로를 같은 파일로 보내주도록 설정해야 한다.",
        "Refreshing a nested route returns 404 unless the server falls back to index.",
        "서버가 index 로 넘겨주지 않으면 중첩 경로를 새로고침할 때 404 가 납니다.",
    ),
    (
        "localStorage", "/ˈloʊkl ˌstɔrɪdʒ/", "브라우저에 남는 간단한 저장소", FRONT, N,
        "브라우저에 문자열을 저장해두고 창을 닫아도 남게 하는 공간. 쿠키와 달리 "
        "요청에 자동으로 딸려가지 않는다. 스크립트로 읽을 수 있어서 토큰을 넣어두면 "
        "XSS 가 났을 때 그대로 탈취된다.",
        "Do not keep the access token in localStorage.",
        "액세스 토큰을 localStorage 에 두지 마세요.",
    ),
    (
        "event loop", "/ɪˈvent ˌlup/", "할 일을 차례로 꺼내 실행하는 구조", FRONT, H,
        "자바스크립트가 한 번에 하나씩만 처리하면서도 여러 일을 다루는 방식. 대기열에서 "
        "할 일을 꺼내 실행하고, 끝나면 다음을 꺼낸다. 그래서 무거운 계산 하나가 "
        "돌고 있으면 그동안 클릭도 애니메이션도 전부 멈춘다.",
        "That heavy loop blocks the event loop and freezes the UI.",
        "그 무거운 반복문이 이벤트 루프를 막아 화면이 멈춥니다.",
    ),
    (
        "promise", "/ˈprɑmɪs/", "나중에 올 결과를 담는 그릇", FRONT, N,
        "아직 끝나지 않은 작업의 결과를 나중에 받겠다고 약속하는 객체. 결과가 오면 "
        "성공이나 실패로 정해진다. 실패를 처리하지 않으면 사라지는 게 아니라 "
        "처리되지 않은 거부로 따로 보고되는데, 문제가 난 자리와 멀리 떨어져 나타나서 "
        "원인을 찾기 어렵다. 브라우저에서는 콘솔 오류로만 남지만, 요즘 Node 는 "
        "기본 설정에서 프로세스를 아예 종료시킨다.",
        "This promise rejection is unhandled, so Node kills the process.",
        "이 프로미스의 실패가 처리되지 않아 Node 가 프로세스를 종료시킵니다.",
    ),
    (
        "CSP", "/ˌsi es ˈpi/", "어떤 스크립트를 허용할지 정한 규칙", FRONT, H,
        "브라우저에게 어느 출처의 스크립트와 스타일만 실행하라고 알려주는 정책. "
        "XSS 가 나더라도 공격 스크립트가 실행되지 못하게 막는 마지막 방어선이다. "
        "느슨하게 열어두면 있으나 마나 한 설정이 된다.",
        "The inline script is blocked by our CSP.",
        "CSP 정책 때문에 인라인 스크립트가 차단됐습니다.",
    ),
    (
        "service worker", "/ˈsɜrvɪs ˌwɜrkər/", "페이지 뒤에서 도는 중계 스크립트", FRONT, H,
        "페이지와 별개로 백그라운드에서 돌며 네트워크 요청을 가로챌 수 있는 스크립트. "
        "오프라인 지원이나 캐시에 쓴다. 스크립트 자체는 쉴 때 종료되지만 등록과 캐시는 "
        "남기 때문에, 낡은 것이 옛 파일을 계속 내줘 새 배포가 반영되지 않는 문제가 흔하다.",
        "Users still see the old version because the service worker cached it.",
        "서비스 워커가 캐시해둬서 사용자에게 아직 옛 버전이 보입니다.",
    ),
    # ---------- CS 기초 / 정보처리기사 ----------
    (
        "stack", "/stæk/", "마지막에 넣은 것을 먼저 꺼내는 구조", CS, E,
        "쌓아 올린 접시처럼 맨 위에서만 넣고 빼는 자료 구조. 함수 호출이 이 방식으로 "
        "관리되기 때문에, 재귀가 너무 깊어지면 이 공간이 넘쳐 프로그램이 죽는다. "
        "에러 메시지에 나오는 스택 트레이스가 바로 이 쌓인 순서다.",
        "The recursion never terminates and blows the stack.",
        "재귀가 끝나지 않아 스택이 넘칩니다.",
    ),
    (
        "queue", "/kju/", "먼저 넣은 것을 먼저 꺼내는 구조", CS, E,
        "줄 서기처럼 먼저 들어온 것이 먼저 나가는 자료 구조. 작업 대기열이나 "
        "요청 처리 순서에 쓴다. 발음이 함정인데 '큐' 한 음절로 읽고 뒤의 네 글자는 "
        "소리 내지 않는다.",
        "Jobs are pulled off the queue in the order they arrived.",
        "작업은 들어온 순서대로 큐에서 꺼내집니다.",
    ),
    (
        "hash table", "/ˈhæʃ ˌteɪbl/", "키로 바로 찾아가는 저장 구조", CS, N,
        "키를 숫자로 바꿔 저장 위치를 바로 계산해내는 구조. 그래서 개수가 늘어도 "
        "찾는 속도가 거의 그대로다. 서로 다른 키가 같은 자리로 가는 충돌이 생길 수 "
        "있고, 이걸 어떻게 처리하느냐가 성능을 좌우한다. 순서는 보장되지 않는다.",
        "Lookups are constant time on average in a hash table.",
        "해시 테이블에서 조회는 평균적으로 상수 시간입니다.",
    ),
    (
        "linked list", "/ˌlɪŋkt ˈlɪst/", "다음 것의 위치를 들고 있는 구조", CS, N,
        "각 항목이 다음 항목의 위치를 가리키며 사슬처럼 이어진 구조. 중간에 끼워 넣거나 "
        "빼기가 쉬운 대신, 몇 번째 것을 보려면 처음부터 따라가야 한다. "
        "배열과의 이 차이가 정처기 단골 비교 문제다.",
        "Insertion is cheap in a linked list, but random access is not.",
        "연결 리스트는 삽입은 싸지만 임의 접근은 그렇지 않습니다.",
    ),
    (
        "array", "/əˈreɪ/", "연속된 자리에 나란히 담는 구조", CS, E,
        "같은 종류의 값을 연속된 메모리에 나란히 두는 구조. 위치를 계산할 수 있어 "
        "몇 번째 값이든 바로 꺼낼 수 있다. 대신 중간에 하나를 끼워 넣으려면 "
        "뒤의 값들을 모두 밀어야 한다.",
        "Array access is constant time because the position is computed directly.",
        "배열 접근은 위치를 바로 계산하므로 상수 시간입니다.",
    ),
    (
        "binary tree", "/ˈbaɪnəri ˌtri/", "자식이 둘 이하인 나무 구조", CS, N,
        "각 노드가 자식을 최대 둘까지 갖는 구조. 왼쪽은 작고 오른쪽은 큰 값으로 "
        "정렬해두면 절반씩 줄여가며 찾을 수 있다. 다만 한쪽으로만 치우쳐 쌓이면 "
        "결국 목록을 하나씩 훑는 것과 같아진다.",
        "An unbalanced binary tree degrades to linear search.",
        "균형이 무너진 이진 트리는 선형 탐색과 다를 바 없어집니다.",
    ),
    (
        "binary search", "/ˈbaɪnəri ˌsɜrtʃ/", "절반씩 줄여가며 찾기", CS, N,
        "정렬된 데이터에서 가운데를 보고 찾는 값이 앞인지 뒤인지 판단해 범위를 "
        "절반씩 줄이는 방법. 반드시 정렬돼 있어야 한다는 전제가 핵심이다. "
        "백만 개도 스무 번 정도면 찾는다.",
        "Binary search only works if the list is already sorted.",
        "이진 탐색은 목록이 이미 정렬돼 있어야만 동작합니다.",
    ),
    (
        "recursion", "/rɪˈkɜrʒən/", "자기 자신을 다시 부르기", CS, N,
        "함수가 자기 자신을 호출해 문제를 더 작은 같은 문제로 줄여가는 방식. "
        "멈추는 조건이 없거나 조건에 닿지 못하면 호출이 계속 쌓여 스택이 넘친다. "
        "나무 구조를 다룰 때 가장 자연스럽다.",
        "Every recursion needs a base case that stops it.",
        "모든 재귀에는 멈추게 하는 종료 조건이 필요합니다.",
    ),
    (
        "time complexity", "/ˈtaɪm kəmˌpleksəti/", "입력이 커질 때 시간이 느는 정도", CS, H,
        "데이터 양이 늘어날 때 걸리는 시간이 어떤 비율로 늘어나는지. 실제 초 단위 시간이 "
        "아니라 증가하는 추세를 본다. 그래서 데이터가 적으면 복잡도가 나쁜 쪽이 "
        "더 빠를 수도 있다. 정처기 필수 개념이다.",
        "The nested loop makes the time complexity quadratic.",
        "중첩 반복문 때문에 시간 복잡도가 제곱이 됩니다.",
    ),
    (
        "big O", "/ˌbɪɡ ˈoʊ/", "증가 추세의 상한을 나타내는 표기", CS, H,
        "입력이 커질 때 걸리는 시간이나 공간이 얼마나 빠르게 늘어나는지의 상한을 나타내는 표기. "
        "상수 배와 낮은 차수는 무시하기 때문에 두 배 빠른 코드도 같은 표기로 묶인다. "
        "엄밀히는 상한 표기라 최악·평균을 따로 밝혀 쓰지만, 정처기를 비롯한 국내 "
        "시험과 실무 관행에서는 보통 최악의 경우를 가리킨다.",
        "Both are O(n), but one is twice as fast in practice.",
        "둘 다 O(n) 이지만 실제로는 하나가 두 배 빠릅니다.",
    ),
    (
        "greedy", "/ˈɡridi/", "매 순간 최선을 고르는 방식", CS, H,
        "지금 이 순간 가장 좋아 보이는 선택을 계속하는 방법. 빠르고 단순하지만 "
        "전체로 봤을 때 최선이라는 보장이 없다. 이 방식이 통하는 문제인지 먼저 "
        "확인해야 한다는 것이 핵심이다.",
        "A greedy approach does not always give the optimal answer.",
        "그리디 방식이 항상 최적해를 주지는 않습니다.",
    ),
    (
        "dynamic programming", "/daɪˈnæmɪk ˌproʊɡræmɪŋ/", "작은 답을 저장해 재사용", CS, H,
        "같은 부분 문제를 여러 번 푸는 대신 답을 저장해두고 다시 쓰는 방법. "
        "이름의 programming 은 프로그래밍이 아니라 계획 수립을 뜻하는 옛 용어에서 왔다. "
        "재귀에 저장을 붙인 형태와 아래에서부터 채워 올리는 형태가 있다.",
        "Use dynamic programming to avoid recomputing the same subproblem.",
        "같은 부분 문제를 다시 계산하지 않도록 동적 계획법을 쓰세요.",
    ),
    (
        "process", "/ˈprɑses/", "따로 실행되는 프로그램 단위", CS, N,
        "운영체제가 자기 메모리 공간을 따로 떼어주는 실행 단위. 서로의 메모리를 "
        "직접 볼 수 없어 하나가 죽어도 다른 쪽은 멀쩡하다. 대신 서로 데이터를 "
        "주고받으려면 별도의 통신 수단이 필요하다.",
        "Each worker runs in its own process, so a crash is isolated.",
        "각 워커가 별도 프로세스로 돌아서 하나가 죽어도 격리됩니다.",
    ),
    (
        "thread", "/θred/", "한 프로그램 안의 실행 갈래", CS, N,
        "한 프로세스 안에서 메모리를 함께 쓰며 나란히 도는 실행 갈래. 전환 비용이 "
        "적고 데이터를 공유하기 쉽지만, 그 공유 때문에 경쟁 상태가 생긴다. "
        "프로세스와의 차이는 정처기 단골 문제다.",
        "Two threads share the same memory, so the counter needs a lock.",
        "두 스레드가 같은 메모리를 공유해서 카운터에 락이 필요합니다.",
    ),
    (
        "concurrency", "/kənˈkɜrənsi/", "여러 일을 번갈아 진행하기", CS, H,
        "여러 작업을 조금씩 번갈아 처리해 동시에 진행되는 것처럼 보이게 하는 것. "
        "실제로 같은 순간에 함께 도는 병렬성과는 다르다. 코어가 하나여도 "
        "동시성은 가능하지만 병렬성은 불가능하다.",
        "Concurrency is about dealing with many things, not doing them at once.",
        "동시성은 여러 일을 다루는 것이지 한꺼번에 실행하는 것이 아닙니다.",
    ),
    (
        "parallelism", "/ˈpærəlelɪzəm/", "진짜로 동시에 실행하기", CS, H,
        "여러 작업이 같은 순간에 실제로 함께 실행되는 것. 코어가 여러 개 있어야 "
        "가능하다. 동시성이 구조에 관한 이야기라면 이건 실행에 관한 이야기다.",
        "True parallelism requires more than one core.",
        "진짜 병렬 처리는 코어가 둘 이상이어야 가능합니다.",
    ),
    (
        "context switch", "/ˈkɑntekst ˌswɪtʃ/", "실행 대상을 바꿔 끼우기", CS, H,
        "지금 돌던 작업의 상태를 저장하고 다른 작업의 상태를 불러와 실행을 넘기는 것. "
        "이 자체가 비용이라, 스레드를 무작정 늘리면 전환에만 시간을 쓰다가 "
        "오히려 느려진다.",
        "Too many threads and the CPU spends its time on context switches.",
        "스레드가 너무 많으면 CPU 가 문맥 교환에만 시간을 씁니다.",
    ),
    (
        "mutex", "/ˈmjuteks/", "한 번에 하나만 들어가게 하는 자물쇠", CS, H,
        "공유 자원에 한 번에 하나만 접근하도록 잠그는 장치. 열쇠가 하나뿐인 화장실에 "
        "가깝다. 들어간 쪽이 반드시 나와야 다음이 들어갈 수 있어서, 예외가 나서 "
        "풀지 못하면 전부 멈춘다.",
        "Always release the mutex, even when an error occurs.",
        "에러가 나더라도 뮤텍스는 반드시 해제해야 합니다.",
    ),
    (
        "semaphore", "/ˈseməfɔr/", "정해진 수만큼만 들여보내는 장치", CS, H,
        "동시에 들어갈 수 있는 수를 정해두고 그만큼만 허용하는 장치. 하나만 허용하면 "
        "뮤텍스와 비슷해지지만, 원래는 여러 개를 허용하는 개수 세기 장치다. "
        "정처기에서 상호 배제와 함께 자주 나온다.",
        "The semaphore limits us to five concurrent connections.",
        "세마포어가 동시 연결을 다섯 개로 제한합니다.",
    ),
    (
        "scheduling", "/ˈskedʒulɪŋ/", "누구를 먼저 실행할지 정하기", CS, H,
        "여러 작업 중 어느 것에 CPU 를 줄지 순서를 정하는 것. 먼저 온 순서, 짧은 것 "
        "먼저, 우선순위 등 방식이 여럿이다. 우선순위 방식에서는 낮은 순위가 계속 "
        "밀려 영영 실행되지 못하는 기아 현상이 생길 수 있다.",
        "The scheduler decides which process runs next.",
        "스케줄러가 다음에 어떤 프로세스를 실행할지 결정합니다.",
    ),
    (
        "virtual memory", "/ˈvɜrtʃuəl ˌmeməri/", "실제보다 큰 메모리처럼 보이게 하기", CS, H,
        "프로그램에게 연속된 넓은 메모리가 있는 것처럼 보여주고, 실제로는 필요한 부분만 "
        "물리 메모리에 올려두는 방식. 부족하면 디스크로 밀어내는데, 이게 잦아지면 "
        "디스크 접근에 시간을 다 써서 극단적으로 느려진다.",
        "The machine started swapping, and everything slowed to a crawl.",
        "머신이 스와핑을 시작하면서 모든 게 극도로 느려졌습니다.",
    ),
    (
        "paging", "/ˈpeɪdʒɪŋ/", "메모리를 같은 크기로 잘라 관리", CS, H,
        "메모리를 일정한 크기의 조각으로 나눠 필요한 조각만 올려 쓰는 방식. "
        "필요한 조각이 올라와 있지 않으면 가져오는 처리가 일어난다. 정처기에서 "
        "교체 알고리즘과 함께 자주 출제된다.",
        "A page fault occurs when the requested page is not in memory.",
        "요청한 페이지가 메모리에 없으면 페이지 폴트가 발생합니다.",
    ),
    (
        "kernel", "/ˈkɜrnl/", "운영체제의 핵심 부분", CS, N,
        "하드웨어를 직접 다루고 자원을 나눠주는 운영체제의 중심. 일반 프로그램은 "
        "여기에 직접 접근하지 못하고 정해진 통로로만 요청한다. 컨테이너가 가벼운 "
        "이유도 이 부분을 호스트와 함께 쓰기 때문이다.",
        "The container shares the host kernel, unlike a virtual machine.",
        "컨테이너는 가상 머신과 달리 호스트 커널을 공유합니다.",
    ),
    (
        "system call", "/ˈsɪstəm ˌkɔl/", "운영체제에 일을 요청하는 통로", CS, H,
        "파일을 읽거나 네트워크를 쓰는 것처럼 프로그램이 직접 할 수 없는 일을 "
        "운영체제에 요청하는 정해진 통로. 일반 함수 호출보다 비용이 커서, "
        "잦은 파일 접근을 모아서 처리하면 눈에 띄게 빨라진다.",
        "Each read is a system call, so buffering makes a big difference.",
        "읽기마다 시스템 콜이 일어나므로 버퍼링이 큰 차이를 만듭니다.",
    ),
    (
        "garbage collection", "/ˈɡɑrbɪdʒ kəˌlekʃən/", "안 쓰는 메모리를 알아서 회수", CS, N,
        "더 이상 참조되지 않는 메모리를 자동으로 찾아 되돌려주는 기능. 직접 해제하지 "
        "않아도 되지만 회수가 도는 동안 잠깐 멈추는 구간이 생긴다. 자동이라고 "
        "누수가 없는 것은 아니고, 어딘가 참조가 남아 있으면 회수되지 않는다.",
        "A long garbage collection pause caused the request timeout.",
        "가비지 컬렉션이 오래 멈추면서 요청이 타임아웃됐습니다.",
    ),
    (
        "TCP", "/ˌti si ˈpi/", "빠짐없이 순서대로 보내는 방식", CS, N,
        "데이터가 빠지거나 순서가 뒤바뀌지 않도록 확인하고 재전송까지 해주는 전송 방식. "
        "믿을 수 있는 대신 확인 절차 때문에 지연이 생긴다. 웹과 대부분의 API 가 "
        "이 위에서 돈다.",
        "TCP guarantees delivery and ordering, at the cost of latency.",
        "TCP 는 지연을 대가로 전달과 순서를 보장합니다.",
    ),
    (
        "UDP", "/ˌju di ˈpi/", "확인 없이 그냥 보내는 방식", CS, N,
        "도착 확인이나 재전송 없이 그냥 보내는 전송 방식. 일부가 없어져도 신경 쓰지 "
        "않아 빠르다. 조금 끊겨도 계속 진행돼야 하는 실시간 영상이나 게임에 쓴다. "
        "정처기에서 TCP 와 비교해 자주 나온다.",
        "Video calls use UDP because a dropped frame is better than a delay.",
        "영상 통화는 지연보다 프레임 손실이 낫기 때문에 UDP 를 씁니다.",
    ),
    (
        "three-way handshake", "/ˌθri weɪ ˈhændʃeɪk/", "세 번 주고받아 연결 맺기", CS, H,
        "TCP 연결을 시작할 때 요청, 응답, 확인의 세 단계를 거치는 절차. 연결마다 "
        "이 왕복이 필요해서 짧은 요청을 많이 보내면 이 비용이 무시할 수 없어진다. "
        "연결을 재사용하는 이유가 여기 있다.",
        "Connection reuse avoids a three-way handshake on every request.",
        "연결을 재사용하면 요청마다 3방향 핸드셰이크를 하지 않아도 됩니다.",
    ),
    (
        "DNS", "/ˌdi en ˈes/", "이름을 주소로 바꿔주는 체계", CS, N,
        "도메인 이름을 실제 서버 주소로 바꿔주는 체계. 결과가 여러 곳에 잠시 저장되기 "
        "때문에, 주소를 바꿔도 옛 주소로 계속 접속하는 시간이 생긴다. "
        "'왜 나만 접속이 되고 남은 안 되는지' 의 흔한 원인이다.",
        "The DNS change has not propagated to every resolver yet.",
        "DNS 변경이 아직 모든 리졸버에 반영되지 않았습니다.",
    ),
    (
        "port", "/pɔrt/", "한 서버 안에서 서비스를 구분하는 번호", CS, E,
        "같은 주소의 서버에서 어떤 프로그램이 받을지 구분하는 번호. 주소가 건물이라면 "
        "이건 호수에 가깝다. 이미 다른 프로그램이 쓰고 있으면 뜨지 않는데, "
        "'주소가 이미 사용 중' 오류가 이것이다.",
        "The server will not start because the port is already in use.",
        "포트가 이미 사용 중이라 서버가 시작되지 않습니다.",
    ),
    (
        "socket", "/ˈsɑkɪt/", "통신의 양 끝을 잡는 창구", CS, N,
        "주소와 포트를 묶어 통신의 한쪽 끝을 나타내는 것. 프로그램은 이걸 통해 "
        "데이터를 주고받는다. 다 쓴 소켓을 닫지 않으면 자원이 쌓여 결국 새 연결을 "
        "만들지 못하게 된다.",
        "We ran out of sockets because connections were never closed.",
        "연결을 닫지 않아서 소켓이 고갈됐습니다.",
    ),
    (
        "subnet", "/ˈsʌbnet/", "네트워크를 나눈 구역", CS, H,
        "큰 네트워크를 작은 구역으로 나눈 것. 어디까지가 같은 구역인지는 마스크로 "
        "정한다. 같은 구역 안에서는 바로 통신하고 밖으로 나갈 때는 라우터를 거친다. "
        "정처기에서 계산 문제로 자주 나온다.",
        "Those two servers are on different subnets, so the traffic has to go through a router.",
        "그 두 서버는 서로 다른 서브넷에 있어서 트래픽이 라우터를 거쳐야 합니다.",
    ),
    (
        "firewall", "/ˈfaɪərwɔl/", "허용된 통신만 통과시키는 벽", CS, N,
        "정해진 규칙에 맞는 통신만 통과시키고 나머지는 막는 장치. 배포한 서버에 "
        "접속이 안 될 때 코드보다 먼저 확인해야 할 곳이다. 막힌 경우 응답 없이 "
        "그냥 멈추는 형태로 나타나는 경우가 많다.",
        "The connection hangs because the firewall drops the packets silently.",
        "방화벽이 패킷을 조용히 버려서 연결이 멈춰 있습니다.",
    ),
    (
        "encryption", "/ɪnˈkrɪpʃən/", "열쇠 없이는 못 읽게 만들기", CS, N,
        "내용을 다시 되돌릴 수 있는 형태로 바꿔 열쇠가 있어야만 읽게 만드는 것. "
        "되돌릴 수 있다는 점이 해시와의 결정적인 차이다. 비밀번호 저장에는 "
        "암호화가 아니라 해시를 쓴다.",
        "Passwords should be hashed, not encrypted.",
        "비밀번호는 암호화가 아니라 해시로 저장해야 합니다.",
    ),
    (
        "hashing", "/ˈhæʃɪŋ/", "되돌릴 수 없게 고정 길이로 바꾸기", CS, N,
        "입력을 정해진 길이의 값으로 바꾸되 원래대로 되돌릴 수 없게 만드는 것. "
        "비밀번호는 이렇게 저장해 유출돼도 원문을 알 수 없게 한다. 같은 입력은 "
        "항상 같은 결과가 나오므로, 소금값을 섞어 미리 계산된 표로 뚫리는 것을 막는다.",
        "Add a salt so identical passwords do not produce the same hash.",
        "같은 비밀번호가 같은 해시가 되지 않도록 솔트를 추가하세요.",
    ),
    (
        "salt", "/sɔlt/", "해시에 섞는 무작위 값", CS, H,
        "비밀번호를 해시하기 전에 붙이는 사용자마다 다른 무작위 값. 같은 비밀번호라도 "
        "결과가 달라져서 미리 계산해둔 대조표로 한 번에 뚫는 공격을 막는다. "
        "비밀이 아니라 함께 저장해도 되는 값이다.",
        "The salt is stored alongside the hash; it does not need to be secret.",
        "솔트는 해시와 함께 저장하며 비밀일 필요가 없습니다.",
    ),
    (
        "public key", "/ˈpʌblɪk ˌki/", "공개해도 되는 쪽 열쇠", CS, H,
        "짝을 이루는 두 열쇠 중 공개하는 쪽. 이걸로 잠근 것은 짝인 비밀 열쇠로만 열 수 "
        "있다. 반대로 비밀 열쇠로 서명한 것은 공개 열쇠로 확인할 수 있어서, "
        "본인이 맞는지 증명하는 데도 쓴다.",
        "Share the public key; never share the private one.",
        "공개키는 공유해도 되지만 개인키는 절대 공유하면 안 됩니다.",
    ),
    (
        "SQL injection", "/ˌes kju ˈel ɪnˌdʒekʃən/", "입력값에 쿼리를 심어 넣는 공격", CS, H,
        "사용자 입력을 쿼리 문자열에 그대로 이어 붙일 때, 입력에 쿼리 조각을 넣어 "
        "의도하지 않은 명령을 실행시키는 공격. 특수문자를 걸러내는 방식은 빠져나갈 "
        "구멍이 많아서, 값을 따로 넘기는 방식으로 막아야 한다. 정처기 보안 단골이다.",
        "Use parameterized queries; escaping input is not enough.",
        "입력을 이스케이프하는 걸로는 부족합니다. 파라미터 바인딩을 쓰세요.",
    ),
    (
        "XSS", "/ˌeks es ˈes/", "남의 페이지에 스크립트를 심는 공격", CS, H,
        "사용자가 입력한 내용이 그대로 화면에 출력될 때, 그 안에 스크립트를 심어 "
        "다른 사용자의 브라우저에서 실행시키는 공격. 쿠키나 토큰을 훔쳐가는 데 쓰인다. "
        "출력할 때 이스케이프하는 것이 기본 방어이고 CSP 가 마지막 방어선이다.",
        "Escape user content on output to prevent XSS.",
        "XSS 를 막으려면 출력할 때 사용자 입력을 이스케이프하세요.",
    ),
    (
        "authentication", "/ɔˌθentɪˈkeɪʃn/", "누구인지 확인하기", CS, N,
        "이 사람이 본인이 맞는지 확인하는 절차. 로그인이 여기 해당한다. "
        "무엇을 할 수 있는지 정하는 인가와는 다른 단계인데, 영어 줄임말이 "
        "둘 다 auth 라서 문서에서 자주 뒤섞인다.",
        "Authentication tells us who you are, not what you can do.",
        "인증은 당신이 누구인지를 알려줄 뿐 무엇을 할 수 있는지는 아닙니다.",
    ),
    (
        "authorization", "/ˌɔθərəˈzeɪʃn/", "무엇을 할 수 있는지 정하기", CS, N,
        "확인된 사용자가 어떤 작업까지 할 수 있는지 판단하는 단계. 로그인은 됐는데 "
        "권한이 없어 막히는 것이 이 단계다. 인증만 확인하고 인가를 빠뜨려서 "
        "남의 데이터가 보이는 사고가 자주 난다.",
        "The endpoint checks authentication but forgets authorization.",
        "이 엔드포인트는 인증만 확인하고 인가는 빠뜨렸습니다.",
    ),
    (
        "compiler", "/kəmˈpaɪlər/", "미리 통째로 번역하는 도구", CS, N,
        "소스 코드 전체를 기계가 실행할 형태로 미리 번역하는 도구. 실행 전에 오류를 "
        "잡아주고 실행이 빠른 대신 고칠 때마다 다시 번역해야 한다. "
        "한 줄씩 그때그때 해석하는 인터프리터와 비교해 출제된다.",
        "The compiler catches type errors before the program ever runs.",
        "컴파일러는 프로그램이 실행되기 전에 타입 오류를 잡아줍니다.",
    ),
    (
        "interpreter", "/ɪnˈtɜrprətər/", "한 줄씩 읽어가며 실행", CS, N,
        "코드를 미리 번역하지 않고 실행하면서 한 줄씩 해석하는 방식. 바로 실행해볼 수 "
        "있어 개발이 빠르지만, 문제가 있는 줄에 실제로 도달해야 오류가 드러난다. "
        "그래서 실행되지 않은 분기의 오타가 배포까지 살아남는다.",
        "The typo survived because the interpreter never reached that branch.",
        "인터프리터가 그 분기에 도달한 적이 없어서 오타가 살아남았습니다.",
    ),
    (
        "abstraction", "/æbˈstrækʃən/", "세부를 감추고 요점만 드러내기", CS, N,
        "복잡한 내부를 감추고 쓰는 쪽에 필요한 것만 드러내는 것. 감춘 만큼 "
        "쓰기 쉬워지지만, 문제가 생겼을 때는 결국 감춰둔 안쪽을 알아야 한다. "
        "잘못 자른 추상화는 오히려 이해를 방해한다.",
        "This abstraction leaks; you still need to know how the cache behaves.",
        "이 추상화는 새고 있습니다. 결국 캐시 동작을 알아야 합니다.",
    ),
    (
        "encapsulation", "/ɪnˌkæpsəˈleɪʃn/", "내부 상태를 감싸 보호하기", CS, N,
        "객체의 내부 값을 밖에서 직접 건드리지 못하게 감싸고 정해진 통로로만 다루게 "
        "하는 것. 값이 어디서 바뀌었는지 추적할 수 있게 해준다. 통로를 만들어놓고 "
        "그냥 값을 그대로 넘겨주기만 하면 감싼 의미가 없다.",
        "Getters that expose the internal list break encapsulation.",
        "내부 리스트를 그대로 내주는 게터는 캡슐화를 깨뜨립니다.",
    ),
    (
        "polymorphism", "/ˌpɑliˈmɔrfɪzəm/", "같은 호출이 대상에 따라 다르게 동작", CS, H,
        "같은 이름으로 불러도 실제 대상이 무엇이냐에 따라 다른 동작이 실행되는 성질. "
        "부르는 쪽은 종류마다 분기할 필요가 없어진다. 조건문이 길게 늘어선 코드를 "
        "정리할 때 쓰는 대표적인 수단이다.",
        "Polymorphism removes the long if-else chain on the type field.",
        "다형성을 쓰면 타입별로 늘어선 if-else 를 없앨 수 있습니다.",
    ),
    (
        "singleton", "/ˈsɪŋɡltən/", "인스턴스를 하나만 두는 패턴", CS, N,
        "그 클래스의 객체가 프로그램 전체에 하나만 있도록 만드는 설계 패턴. "
        "설정이나 연결 관리에 쓴다. 사실상 전역 상태라서 테스트할 때 갈아 끼우기 "
        "어렵고 상태가 테스트 사이에 남는 문제가 있다.",
        "The singleton keeps state between tests and makes them order dependent.",
        "싱글턴이 테스트 사이에 상태를 남겨서 실행 순서에 의존하게 만듭니다.",
    ),
    (
        "MVC", "/ˌem vi ˈsi/", "모델, 뷰, 컨트롤러로 나눈 구조", CS, N,
        "데이터, 화면, 흐름 제어를 세 부분으로 나누는 구조. 화면과 업무 규칙을 "
        "떼어놓는 것이 목적이다. 프레임워크마다 각 부분의 경계가 조금씩 달라서 "
        "같은 이름으로 다른 것을 가리키기도 한다.",
        "The business logic belongs in the model, not in the controller.",
        "업무 로직은 컨트롤러가 아니라 모델에 있어야 합니다.",
    ),
    (
        "ERD", "/ˌi ɑr ˈdi/", "표와 관계를 그린 설계도", CS, N,
        "어떤 데이터 덩어리가 있고 서로 어떻게 연결되는지 그림으로 나타낸 설계도. "
        "표를 만들기 전에 관계를 눈으로 확인하는 데 쓴다. 정처기 실기에서 "
        "관계 표기와 함께 자주 나온다.",
        "Update the ERD before you add the new relation.",
        "새 관계를 추가하기 전에 ERD 를 갱신하세요.",
    ),
    (
        "UTF-8", "/ˌju ti ˌef ˈeɪt/", "글자를 바이트로 바꾸는 표준 방식", CS, N,
        "전 세계 문자를 표현하는 가장 널리 쓰이는 인코딩. 영문은 1바이트, 한글은 "
        "보통 3바이트를 쓴다. 그래서 글자 수와 바이트 수가 달라서, 길이 제한을 "
        "바이트로 잡아둔 칼럼에 한글이 예상보다 적게 들어간다.",
        "Korean text takes three bytes per character in UTF-8.",
        "UTF-8 에서 한글은 글자당 3바이트를 씁니다.",
    ),
    (
        "overflow", "/ˈoʊvərfloʊ/", "표현 범위를 넘어 값이 뒤집힘", CS, H,
        "정해진 크기가 담을 수 있는 최대치를 넘어 값이 엉뚱하게 바뀌는 것. "
        "숫자가 갑자기 음수가 되는 형태로 나타난다. 아이디 칼럼을 작은 정수형으로 "
        "잡아뒀다가 몇 년 뒤 서비스가 멈추는 사고가 이 유형이다.",
        "The counter overflowed and wrapped around to a negative value.",
        "카운터가 오버플로해서 음수로 뒤집혔습니다.",
    ),
    (
        "floating point", "/ˈfloʊtɪŋ ˌpɔɪnt/", "소수를 근삿값으로 다루는 방식", CS, H,
        "소수를 2진수 근삿값으로 저장하는 방식. 그래서 0.1 더하기 0.2 가 0.3 과 "
        "정확히 같지 않다. 버그가 아니라 표현 방식의 한계라서, 돈 계산에는 "
        "이 방식 대신 소수점을 정확히 다루는 타입을 쓴다.",
        "Never use floating point for money; use a decimal type.",
        "돈 계산에 부동소수점을 쓰지 마세요. 소수 전용 타입을 쓰세요.",
    ),
    # ---------- git 줄임말 ----------
    (
        "SHA", "/ʃɑ/", "내용을 지문으로 바꾸는 해시 알고리즘", GIT, N,
        "Secure Hash Algorithm 의 줄임말. 내용을 정해진 길이의 값으로 바꾸는 "
        "알고리즘 계열이다. git 에서 'SHA 알려줘' 라고 하면 알고리즘이 아니라 "
        "그 결과로 나온 커밋 식별값을 뜻한다. 내용이 조금만 달라도 완전히 다른 "
        "값이 나와 사실상 겹치지 않는다. SHA-1 은 40자리이고, git 은 여기서 "
        "SHA-256 으로 옮겨가는 중이다.",
        "Reference the commit by its short SHA in the ticket.",
        "티켓에 짧은 SHA 로 커밋을 참조해 주세요.",
    ),
    (
        "VCS", "/ˌvi si ˈes/", "코드 변경 이력을 관리하는 도구", GIT, E,
        "Version Control System 의 줄임말. 누가 언제 무엇을 왜 바꿨는지 기록하고 "
        "이전 상태로 돌아갈 수 있게 해주는 도구를 통틀어 부른다. 파일 이름 뒤에 "
        "날짜를 붙여 복사해두는 방식이 하던 일을 제대로 해주는 것이다.",
        "Every project should be under version control from day one.",
        "모든 프로젝트는 첫날부터 버전 관리를 받아야 합니다.",
    ),
    (
        "DVCS", "/ˌdi vi si ˈes/", "각자 전체 기록을 갖는 방식", GIT, N,
        "Distributed VCS 의 줄임말. 중앙 서버에만 기록이 있는 방식과 달리 모든 사람이 "
        "전체 히스토리를 갖는다. 그래서 인터넷 없이도 커밋과 로그 조회가 되고, "
        "서버가 날아가도 누군가의 사본으로 복구된다. git 이 여기 속한다.",
        "Because git is a DVCS, you can commit without a network connection.",
        "git 은 분산형이라 네트워크 없이도 커밋할 수 있습니다.",
    ),
    (
        "LFS", "/ˌel ef ˈes/", "큰 파일을 따로 떼어 보관하는 확장", GIT, N,
        "Large File Storage 의 줄임말. 이미지나 영상처럼 큰 파일을 저장소에 직접 넣지 "
        "않고 별도 저장소에 두며 위치만 기록한다. 큰 파일을 그냥 커밋하면 지워도 "
        "히스토리에 영원히 남아 클론이 무거워지므로 미리 설정해두는 편이 낫다.",
        "Set up LFS before you commit the design assets.",
        "디자인 에셋을 커밋하기 전에 LFS 를 설정하세요.",
    ),
    (
        "MR", "/ˌem ˈɑr/", "GitLab 에서 부르는 병합 요청", GIT, E,
        "Merge Request 의 줄임말로, GitHub 의 풀 리퀘스트와 같은 것이다. 이름이 "
        "다를 뿐 기능은 같아서 문서를 옮겨 읽을 때 헷갈릴 필요가 없다. "
        "GitLab 쪽이 실제로 하는 일에 더 가까운 이름이라는 말도 있다.",
        "Open an MR against the develop branch.",
        "develop 브랜치로 MR 을 열어주세요.",
    ),
    (
        "DAG", "/dæɡ/", "되돌아오지 않는 방향 그래프", GIT, H,
        "Directed Acyclic Graph 의 줄임말. 화살표에 방향이 있고 출발점으로 돌아오는 "
        "고리가 없는 구조다. 커밋이 앞선 커밋을 가리키며 쌓이는 git 히스토리가 "
        "이 구조라서, 브랜치가 갈라지고 합쳐져도 순환이 생기지 않는다. "
        "'대그' 로 읽는다.",
        "Commit history forms a DAG, not a straight line.",
        "커밋 히스토리는 직선이 아니라 DAG 를 이룹니다.",
    ),
    (
        "CLA", "/ˌsi el ˈeɪ/", "기여 전에 서명하는 권리 합의서", GIT, N,
        "Contributor License Agreement 의 줄임말. 오픈소스에 코드를 보내기 전에 "
        "그 코드의 사용 권리를 어떻게 할지 미리 합의하는 문서다. 서명하지 않으면 "
        "봇이 자동으로 병합을 막는 저장소가 많다.",
        "The bot is blocking the merge until you sign the CLA.",
        "CLA 에 서명할 때까지 봇이 병합을 막고 있습니다.",
    ),
    (
        "SCM", "/ˌes si ˈem/", "소스 코드와 변경을 관리하는 체계", GIT, N,
        "Source Code Management 의 줄임말. 버전 관리에 더해 브랜치 전략, 릴리스, "
        "접근 권한까지 포함하는 넓은 말이다. 도구 설정 화면에서 저장소 연결 항목의 "
        "이름으로 자주 등장한다.",
        "Configure the SCM connection in the build settings.",
        "빌드 설정에서 SCM 연결을 구성하세요.",
    ),
    # ---------- 코드 리뷰 / 설계 줄임말 ----------
    (
        "DDD", "/ˌdi di ˈdi/", "업무 개념을 중심에 두는 설계", REVIEW, H,
        "Domain-Driven Design 의 줄임말. 기술 구조가 아니라 업무 개념을 중심으로 코드를 "
        "짜고, 기획자와 개발자가 같은 단어를 쓰도록 맞추는 접근이다. 폴더를 도메인별로 "
        "나누는 것만 가리키는 말이 아니라, 이름과 경계를 업무에서 가져온다는 것이 핵심이다.",
        "We split the services along DDD bounded contexts.",
        "DDD 의 바운디드 컨텍스트를 기준으로 서비스를 나눴습니다.",
    ),
    (
        "SOLID", "/ˈsɑlɪd/", "객체 설계 원칙 다섯 개", REVIEW, H,
        "다섯 가지 설계 원칙의 앞 글자를 모아 만든 말. 각각을 따로 외우기보다 "
        "'바꿔야 할 때 얼마나 적게 건드리고 끝나는가' 라는 하나의 질문으로 묶어 보면 "
        "이해가 빠르다. 원칙을 다 지키는 것이 목표가 아니라 변경 비용을 줄이는 것이 목표다.",
        "This refactor makes the class follow the SOLID principles more closely.",
        "이번 리팩터링으로 이 클래스가 SOLID 원칙에 더 가까워집니다.",
    ),
    (
        "SRP", "/ˌes ɑr ˈpi/", "바뀔 이유가 하나뿐이어야 한다", REVIEW, H,
        "Single Responsibility Principle 의 줄임말. 흔히 '한 가지 일만 해야 한다' 로 "
        "알려져 있지만, 원래 표현은 바뀔 이유가 하나여야 한다는 쪽이다. 화면 요구가 "
        "바뀔 때와 계산 규칙이 바뀔 때 같은 파일을 고쳐야 한다면 그게 위반이다.",
        "This class changes for two different reasons, which violates SRP.",
        "이 클래스는 서로 다른 두 이유로 바뀌므로 SRP 를 위반합니다.",
    ),
    (
        "OCP", "/ˌoʊ si ˈpi/", "고치지 말고 덧붙여 확장하기", REVIEW, H,
        "Open-Closed Principle 의 줄임말. 기능을 늘릴 때 기존 코드를 뜯어고치는 대신 "
        "새 코드를 더하는 쪽으로 만들자는 원칙이다. 결제 수단을 하나 추가할 때마다 "
        "거대한 조건문을 또 고쳐야 한다면 이 원칙과 멀어져 있는 것이다.",
        "Adding a new payment type should not require touching this switch statement.",
        "결제 수단을 추가할 때 이 분기문을 건드려야 한다면 문제가 있습니다.",
    ),
    (
        "LSP", "/ˌel es ˈpi/", "자식이 부모 자리를 대신할 수 있어야 한다", REVIEW, H,
        "Liskov Substitution Principle 의 줄임말. 부모 타입을 쓰던 자리에 자식을 넣어도 "
        "동작이 깨지지 않아야 한다는 원칙이다. 상속받아 놓고 특정 메서드에서 "
        "예외를 던지게 만들면 이 원칙이 깨지고, 쓰는 쪽이 타입을 확인하기 시작한다.",
        "The subclass throws on that method, so it is not a proper substitute.",
        "이 하위 클래스는 그 메서드에서 예외를 던지므로 대체할 수 없습니다.",
    ),
    (
        "ISP", "/ˌaɪ es ˈpi/", "쓰지도 않을 것을 강요하지 않기", REVIEW, H,
        "Interface Segregation Principle 의 줄임말. 큰 인터페이스 하나를 강요하기보다 "
        "필요한 만큼 잘게 나누자는 원칙이다. 구현할 때 쓸 일 없는 메서드를 빈 채로 "
        "두게 된다면 인터페이스가 너무 크다는 신호다.",
        "Split that interface; half of the implementations leave those methods empty.",
        "그 인터페이스를 나누세요. 구현체 절반이 그 메서드를 비워두고 있습니다.",
    ),
    (
        "DIP", "/dɪp/", "구체적인 것 말고 약속에 기대기", REVIEW, H,
        "Dependency Inversion Principle 의 줄임말. 상위 로직이 특정 구현이 아니라 "
        "약속된 인터페이스에 기대게 만드는 원칙이다. 그래야 테스트에서 가짜로 갈아 "
        "끼울 수 있다. 뒤에 나오는 DI 는 이 원칙을 실제로 적용하는 방법 중 하나다.",
        "Depend on the repository interface, not on the concrete database class.",
        "구체적인 데이터베이스 클래스가 아니라 저장소 인터페이스에 의존하세요.",
    ),
    (
        "DI", "/ˌdi ˈaɪ/", "필요한 것을 밖에서 넣어주기", REVIEW, N,
        "Dependency Injection 의 줄임말. 객체가 필요한 것을 스스로 만들지 않고 "
        "바깥에서 받아 쓰게 하는 방식이다. 테스트에서 가짜로 바꿔 끼우기 쉬워지는 것이 "
        "가장 큰 실익이다. 프레임워크가 있어야만 되는 것은 아니고, 생성자 인자로 "
        "넘기는 것만으로도 성립한다.",
        "Inject the client through the constructor so we can swap it in tests.",
        "테스트에서 교체할 수 있도록 클라이언트를 생성자로 주입하세요.",
    ),
    (
        "IoC", "/ˌaɪ oʊ ˈsi/", "흐름의 주도권을 넘기기", REVIEW, H,
        "Inversion of Control 의 줄임말. 내 코드가 라이브러리를 부르는 대신 "
        "프레임워크가 내 코드를 불러주는 구조로 뒤집는 것을 말한다. DI 는 이 개념을 "
        "의존성에 적용한 한 갈래라서, 두 말이 자주 같이 나오지만 범위가 다르다.",
        "The framework calls your handler; that is inversion of control.",
        "프레임워크가 여러분의 핸들러를 호출합니다. 그게 제어의 역전입니다.",
    ),
    (
        "CQRS", "/ˌsi kju ɑr ˈes/", "읽기와 쓰기 경로를 갈라놓기", REVIEW, H,
        "Command Query Responsibility Segregation 의 줄임말. 데이터를 바꾸는 경로와 "
        "읽는 경로를 아예 다른 모델로 분리하는 방식이다. 읽기 부하가 압도적으로 클 때 "
        "각각을 따로 최적화할 수 있다. 대신 두 모델의 동기화 부담이 생긴다.",
        "We adopted CQRS because the read load is a hundred times the write load.",
        "읽기 부하가 쓰기의 백 배라서 CQRS 를 도입했습니다.",
    ),
    (
        "SOA", "/ˌes oʊ ˈeɪ/", "서비스 단위로 나눈 구조", REVIEW, N,
        "Service-Oriented Architecture 의 줄임말. 시스템을 독립된 서비스들로 나누고 "
        "정해진 규약으로 통신하게 하는 구조다. 마이크로서비스보다 앞서 나온 개념이고 "
        "서비스 크기가 더 큰 편이다.",
        "This is closer to SOA than to microservices.",
        "이건 마이크로서비스보다 SOA 에 가깝습니다.",
    ),
    (
        "KISS", "/kɪs/", "단순하게 유지하기", REVIEW, E,
        "Keep It Simple, Stupid 의 줄임말. 나중에 필요할지 모른다는 이유로 복잡하게 "
        "만들지 말자는 조언이다. 코드를 짧게 쓰라는 뜻이 아니라, 처음 보는 사람이 "
        "따라갈 수 있게 만들라는 뜻에 가깝다.",
        "Let's keep it simple and add the abstraction when we actually need it.",
        "단순하게 가고 추상화는 실제로 필요할 때 추가합시다.",
    ),
    (
        "POC", "/ˌpi oʊ ˈsi/", "되는지만 확인하는 시험 구현", REVIEW, N,
        "Proof of Concept 의 줄임말. 이 방식이 실제로 가능한지 확인하려고 대충 만들어보는 "
        "것이다. 확인이 끝나면 버리는 것이 전제인데, 잘 돌아간다는 이유로 그대로 "
        "운영에 올라가는 일이 자주 생긴다.",
        "That was a POC; do not ship it as is.",
        "그건 개념 검증용이었습니다. 그대로 배포하면 안 됩니다.",
    ),
    (
        "PTAL", "/ˌpi ti eɪ ˈel/", "다시 한번 봐달라는 요청", REVIEW, N,
        "Please Take Another Look 의 줄임말. 리뷰 지적을 반영한 뒤 리뷰어에게 다시 "
        "봐달라고 남기는 짧은 말이다. 무엇을 고쳤는지 한 줄 덧붙이면 리뷰어가 "
        "다시 처음부터 읽지 않아도 된다.",
        "Addressed all the comments, PTAL.",
        "코멘트 모두 반영했습니다. 다시 한번 봐주세요.",
    ),
    (
        "TL;DR", "/ˌti el ˌdi ˈɑr/", "길어서 안 읽을 사람을 위한 요약", REVIEW, E,
        "Too Long; Didn't Read 의 줄임말. 긴 글 맨 앞에 결론을 한두 줄로 적어둘 때 쓴다. "
        "무례한 표현이 아니라 배려에 가까워서, 긴 설계 문서나 장애 보고서에는 "
        "붙여주는 것이 좋다.",
        "TL;DR: the deploy failed because of an expired certificate.",
        "요약하면, 인증서 만료 때문에 배포가 실패했습니다.",
    ),
    (
        "FYI", "/ˌef waɪ ˈaɪ/", "참고만 하라는 공유", REVIEW, E,
        "For Your Information 의 줄임말. 지금 당장 무언가 해달라는 요청이 아니라 "
        "알아두라고 공유할 때 붙인다. 조치가 필요하면 이 표현 대신 무엇을 언제까지 "
        "해달라고 분명히 적는 편이 낫다.",
        "FYI, the staging database will be down for an hour tonight.",
        "참고로 오늘 밤 한 시간 동안 스테이징 데이터베이스가 내려갑니다.",
    ),
    (
        "OKR", "/ˌoʊ keɪ ˈɑr/", "목표와 그 달성 지표", REVIEW, N,
        "Objectives and Key Results 의 줄임말. 이루려는 목표 하나에 그것이 이뤄졌는지 "
        "판단할 숫자 몇 개를 붙이는 방식이다. 할 일 목록이 아니라 결과를 적는 것이 "
        "핵심이라, 무엇을 하겠다가 아니라 무엇이 달라지겠다로 써야 한다.",
        "That reads like a task list, not an OKR.",
        "그건 OKR 이 아니라 할 일 목록처럼 읽힙니다.",
    ),
    (
        "KPI", "/ˌkeɪ pi ˈaɪ/", "성과를 재는 핵심 지표", REVIEW, N,
        "Key Performance Indicator 의 줄임말. 잘 되고 있는지 판단하려고 정해둔 지표다. "
        "재기 쉬운 것을 지표로 삼으면 사람들이 그 숫자만 올리는 쪽으로 움직이기 때문에, "
        "무엇을 재느냐가 곧 무엇을 하게 되느냐가 된다.",
        "Pick a KPI that actually reflects user value.",
        "실제 사용자 가치를 반영하는 KPI 를 고르세요.",
    ),
    (
        "PRD", "/ˌpi ɑr ˈdi/", "무엇을 왜 만드는지 적은 기획 문서", REVIEW, N,
        "Product Requirements Document 의 줄임말. 어떤 문제를 누구를 위해 푸는지와 "
        "성공 기준을 적는다. 어떻게 만들지를 적는 설계 문서와는 다른 문서라, "
        "여기에 기술 구현이 들어차면 대개 논의가 엉킨다.",
        "The PRD says what and why; the design doc says how.",
        "PRD 는 무엇과 왜를, 설계 문서는 어떻게를 다룹니다.",
    ),
    (
        "WIP limit", "/ˈwɪp ˌlɪmɪt/", "동시에 진행할 일의 상한", REVIEW, N,
        "한 번에 진행 중인 작업 수를 정해둔 상한. 시작한 일이 많을수록 전환 비용이 "
        "커지고 아무것도 끝나지 않기 때문에 둔다. 상한에 걸리면 새 일을 시작하는 대신 "
        "이미 진행 중인 것을 끝내러 가는 것이 규칙이다.",
        "We hit the WIP limit, so finish something before starting a new ticket.",
        "WIP 상한에 걸렸습니다. 새 티켓을 시작하기 전에 하나를 끝내세요.",
    ),
    # ---------- API / 네트워크 줄임말 ----------
    (
        "API", "/ˌeɪ pi ˈaɪ/", "프로그램끼리 주고받기로 한 약속", API, E,
        "Application Programming Interface 의 줄임말. 어떤 요청을 보내면 어떤 응답이 "
        "온다고 미리 정해둔 창구다. 웹 주소로 부르는 것만 가리키는 말이 아니라, "
        "라이브러리가 제공하는 함수 목록도 API 다.",
        "The API contract has not changed, only the implementation.",
        "구현만 바뀌었고 API 규약은 그대로입니다.",
    ),
    (
        "TTL", "/ˌti ti ˈel/", "유효한 시간이 다하면 버리기", API, N,
        "Time To Live 의 줄임말. 캐시나 DNS 기록이 얼마 동안 유효한지를 정한 값이다. "
        "짧게 잡으면 변경이 빨리 반영되는 대신 조회가 잦아지고, 길게 잡으면 그 반대다. "
        "네트워크 패킷에서는 시간이 아니라 거쳐갈 수 있는 홉 수를 뜻해서 뜻이 다르다.",
        "Lower the TTL a day before you change the DNS record.",
        "DNS 레코드를 바꾸기 하루 전에 TTL 을 낮춰두세요.",
    ),
    (
        "SSE", "/ˌes es ˈi/", "서버가 한 방향으로 계속 보내주기", API, N,
        "Server-Sent Events 의 줄임말. 연결을 열어두고 서버가 클라이언트로만 계속 "
        "데이터를 보내는 방식이다. 웹소켓과 달리 한 방향이고 일반 HTTP 위에서 돌아 "
        "설정이 간단하며 끊기면 브라우저가 알아서 다시 붙는다. AI 응답이 한 글자씩 "
        "나오는 화면이 대개 이 방식이다.",
        "The streaming endpoint uses SSE, so the client only receives.",
        "스트리밍 엔드포인트는 SSE 라 클라이언트는 받기만 합니다.",
    ),
    (
        "SSO", "/ˌes es ˈoʊ/", "한 번 로그인해 여러 서비스 쓰기", API, N,
        "Single Sign-On 의 줄임말. 한 곳에서 로그인하면 연결된 다른 서비스에도 "
        "따로 로그인하지 않고 들어가는 방식이다. 편한 만큼 그 한 계정이 뚫리면 "
        "전부 뚫리기 때문에 다중 인증을 함께 거는 경우가 많다.",
        "All internal tools are behind SSO.",
        "사내 도구는 전부 SSO 뒤에 있습니다.",
    ),
    (
        "OIDC", "/ˌoʊ aɪ di ˈsi/", "OAuth 위에 얹은 로그인 규격", API, H,
        "OpenID Connect 의 줄임말. OAuth 가 권한 위임을 위한 규격이라 로그인 용도로는 "
        "부족한데, 그 위에 '누구인지' 를 담은 토큰을 더한 것이 이것이다. "
        "'구글로 로그인' 을 제대로 구현하려면 OAuth 만으로는 안 되고 이쪽이 필요하다.",
        "Use OIDC for login; plain OAuth does not tell you who the user is.",
        "로그인에는 OIDC 를 쓰세요. 순수 OAuth 만으로는 사용자가 누구인지 알 수 없습니다.",
    ),
    (
        "SAML", "/ˈsæml/", "기업 환경에서 쓰는 인증 정보 교환 규격", API, H,
        "Security Assertion Markup Language 의 줄임말. XML 로 인증 정보를 주고받는 "
        "오래된 표준으로 기업용 SSO 에서 여전히 널리 쓰인다. 요즘 서비스는 OIDC 를 "
        "쓰지만, 고객사가 SAML 을 요구하는 경우가 많아 둘 다 지원하게 된다. "
        "'새믈' 로 읽는다.",
        "The enterprise customer requires SAML, not OIDC.",
        "그 기업 고객은 OIDC 가 아니라 SAML 을 요구합니다.",
    ),
    (
        "MFA", "/ˌem ef ˈeɪ/", "서로 다른 종류로 두 번 이상 확인", API, N,
        "Multi-Factor Authentication 의 줄임말. 아는 것, 가진 것, 자기 자신 중 "
        "서로 다른 종류를 둘 이상 확인하는 방식이다. 비밀번호를 두 개 묻는 것은 "
        "같은 종류라서 여기 해당하지 않는다.",
        "Enable MFA on every account with production access.",
        "운영 접근 권한이 있는 모든 계정에 MFA 를 켜세요.",
    ),
    (
        "TOTP", "/ˌti oʊ ti ˈpi/", "시간에 맞춰 바뀌는 일회용 번호", API, H,
        "Time-based One-Time Password 의 줄임말. 공유한 비밀값과 현재 시각으로 계산해 "
        "보통 30초마다 바뀌는 숫자다. 서버와 기기의 시계가 어긋나면 맞는 번호를 "
        "넣어도 실패하는데, 인증 앱이 갑자기 안 되는 흔한 원인이다.",
        "The TOTP code keeps failing because the device clock has drifted.",
        "기기 시계가 어긋나서 TOTP 코드가 계속 실패합니다.",
    ),
    (
        "RBAC", "/ˈɑrbæk/", "역할을 통해 권한을 주는 방식", API, N,
        "Role-Based Access Control 의 줄임말. 사람마다 권한을 붙이지 않고 역할을 만들어 "
        "권한을 묶은 뒤 사람에게 역할을 주는 방식이다. 사람이 늘어나도 관리가 무너지지 "
        "않는다. 역할이 지나치게 잘게 늘어나면 원래 이점이 사라진다.",
        "Move that permission onto the role instead of the individual user.",
        "그 권한은 개별 사용자가 아니라 역할에 붙이세요.",
    ),
    (
        "ACL", "/ˌeɪ si ˈel/", "누가 무엇을 할 수 있는지 적은 목록", API, N,
        "Access Control List 의 줄임말. 자원마다 누구에게 어떤 동작을 허용할지 나열해둔 "
        "목록이다. 역할 기반 방식이 사람 쪽에서 묶는다면 이건 자원 쪽에서 나열한다. "
        "세밀하게 지정할 수 있는 대신 자원이 많아지면 관리가 어려워진다.",
        "The bucket ACL still allows public read.",
        "그 버킷 ACL 이 아직 공개 읽기를 허용하고 있습니다.",
    ),
    (
        "CRUD", "/krʌd/", "만들고 읽고 고치고 지우기", API, E,
        "Create, Read, Update, Delete 의 앞 글자. 데이터를 다루는 기본 네 가지 동작이다. "
        "'크러드' 로 읽는다. 화면이나 API 를 설계할 때 이 넷이 다 필요한지 먼저 "
        "따져보면 만들 것이 줄어드는 경우가 많다.",
        "This screen only needs read, not full CRUD.",
        "이 화면은 전체 CRUD 가 아니라 읽기만 있으면 됩니다.",
    ),
    (
        "HTTP", "/ˌeɪtʃ ti ti ˈpi/", "웹에서 요청과 응답을 주고받는 규약", API, E,
        "HyperText Transfer Protocol 의 줄임말. 어떤 형식으로 요청하고 응답할지 정해둔 "
        "약속이다. 요청 하나가 끝나면 서버가 아무것도 기억하지 않기 때문에, "
        "로그인 상태를 유지하려면 쿠키나 토큰 같은 장치가 따로 필요해진다.",
        "HTTP is stateless, so the server does not remember the previous request.",
        "HTTP 는 무상태라 서버가 이전 요청을 기억하지 않습니다.",
    ),
    (
        "HTTPS", "/ˌeɪtʃ ti ti pi ˈes/", "암호화를 입힌 HTTP", API, E,
        "HTTP 위에 TLS 를 씌워 내용을 암호화한 것. 중간에서 읽거나 바꾸지 못하게 막고 "
        "접속한 서버가 진짜인지도 확인해준다. 다만 어느 사이트에 접속했는지 자체를 "
        "완전히 숨기지는 못한다.",
        "Redirect all HTTP traffic to HTTPS at the load balancer.",
        "로드 밸런서에서 모든 HTTP 트래픽을 HTTPS 로 넘기세요.",
    ),
    (
        "URL", "/ˌju ɑr ˈel/", "자원이 어디 있는지 나타내는 주소", API, E,
        "Uniform Resource Locator 의 줄임말. 어떤 방식으로 어디에 접속해 무엇을 가져올지 "
        "한 줄에 담은 주소다. 뒤에 나오는 URI 의 한 종류이고, 위치를 알려준다는 점이 "
        "특징이다.",
        "Include the full URL in the bug report.",
        "버그 리포트에 전체 URL 을 넣어주세요.",
    ),
    (
        "URI", "/ˌju ɑr ˈaɪ/", "자원을 가리키는 식별자 전체", API, N,
        "Uniform Resource Identifier 의 줄임말. 자원을 식별하는 문자열을 통틀어 부르는 "
        "넓은 말이고, 그중 위치까지 알려주는 것이 URL 이다. 명세 문서는 URI 라고 "
        "쓰는 경우가 많아서 두 말이 섞여 보인다.",
        "The spec says URI, but in practice everyone writes a URL.",
        "명세에는 URI 라고 적혀 있지만 실제로는 다들 URL 을 씁니다.",
    ),
    (
        "JSON", "/ˈdʒeɪsɑn/", "데이터를 주고받는 가장 흔한 형식", API, E,
        "JavaScript Object Notation 의 줄임말. 이름과 값을 짝지어 적는 가벼운 형식으로 "
        "대부분의 API 가 이걸 쓴다. 주석을 넣을 수 없고 마지막 항목 뒤에 쉼표를 두면 "
        "오류가 나는데, 설정 파일에서 자주 걸리는 부분이다. '제이슨' 으로 읽는다.",
        "The request failed because of a trailing comma in the JSON.",
        "JSON 마지막에 쉼표가 남아 있어서 요청이 실패했습니다.",
    ),
    (
        "XML", "/ˌeks em ˈel/", "태그로 감싸 구조를 나타내는 형식", API, N,
        "Extensible Markup Language 의 줄임말. 여는 태그와 닫는 태그로 감싸 데이터를 "
        "표현한다. JSON 보다 무겁지만 스키마 검증이나 서명 같은 기능이 잘 갖춰져 있어 "
        "금융이나 기업 연동에서는 여전히 현역이다.",
        "The legacy partner API still speaks XML.",
        "그 오래된 파트너 API 는 아직 XML 을 씁니다.",
    ),
    (
        "YAML", "/ˈjæml/", "들여쓰기로 구조를 나타내는 설정 형식", API, N,
        "YAML Ain't Markup Language 의 줄임말. 자기 이름을 자기가 부정하는 "
        "재귀 약어인데, 처음에는 Yet Another Markup Language 였다가 바뀌었다. "
        "사람이 읽고 쓰기 편하게 만든 설정 파일 형식. 들여쓰기로 구조를 표현해서 "
        "공백 한 칸 차이로 의미가 달라지고 탭을 쓰면 오류가 난다. 따옴표 없는 yes 나 "
        "no 가 참거짓으로 해석되는 것도 유명한 함정이다. '야믈' 로 읽는다.",
        "The YAML broke because a tab slipped into the indentation.",
        "들여쓰기에 탭이 섞여서 YAML 이 깨졌습니다.",
    ),
    (
        "MIME", "/maɪm/", "내용의 종류를 나타내는 표기 체계", API, N,
        "파일이나 본문이 어떤 종류인지 application/json 처럼 두 단계로 나타내는 체계. "
        "원래 메일 첨부를 위해 만들어졌지만 지금은 웹 전반에서 쓴다. 브라우저는 이 "
        "표기를 보고 파일을 보여줄지 내려받을지 정한다. '마임' 으로 읽는다.",
        "The browser downloads the file because the MIME type is wrong.",
        "MIME 타입이 잘못돼서 브라우저가 파일을 내려받아 버립니다.",
    ),
    (
        "gRPC", "/ˌdʒi ɑr pi ˈsi/", "빠른 서버 간 호출 규격", API, H,
        "구글이 만든 원격 호출 방식. HTTP/2 위에서 돌고 데이터를 사람이 읽는 글자가 "
        "아니라 압축된 바이너리로 주고받아 빠르다. 대신 브라우저에서 직접 부르기 "
        "어려워서 주로 서버끼리의 내부 통신에 쓴다.",
        "Internal services talk over gRPC; the public API stays REST.",
        "내부 서비스끼리는 gRPC 로 통신하고 외부 API 는 REST 를 유지합니다.",
    ),
    (
        "RPC", "/ˌɑr pi ˈsi/", "남의 서버 함수를 부르듯 호출", API, N,
        "Remote Procedure Call 의 줄임말. 다른 서버의 기능을 마치 내 함수처럼 이름으로 "
        "부르는 방식이다. 자원을 주소로 지목하는 REST 와 발상이 다르다. 네트워크는 "
        "언제든 실패한다는 점이 함수 호출과 결정적으로 다르므로 그 처리가 필요하다.",
        "This endpoint is really an RPC call dressed up as REST.",
        "이 엔드포인트는 사실 REST 로 포장한 RPC 호출입니다.",
    ),
    (
        "SOAP", "/soʊp/", "XML 로 규격을 엄격히 정한 옛 방식", API, N,
        "XML 로 메시지를 주고받으며 형식을 엄격하게 정해둔 오래된 웹 서비스 규격. "
        "무겁지만 규칙이 명확해서 공공기관이나 금융권 연동에서 아직 만나게 된다. "
        "'솝' 으로 읽는다.",
        "The government API is SOAP, so we need an XML client.",
        "그 공공 API 는 SOAP 이라 XML 클라이언트가 필요합니다.",
    ),
    (
        "QPS", "/ˌkju pi ˈes/", "초당 처리하는 요청 수", API, N,
        "Queries Per Second 의 줄임말. 1초에 몇 건을 처리하는지 나타낸다. "
        "평균만 보면 특정 시각에 몰리는 부하가 가려지므로 최고치를 함께 봐야 하고, "
        "호출 한도나 용량 계획을 얘기할 때 기준이 되는 숫자다.",
        "We need to handle 500 QPS at peak.",
        "피크 시간에 초당 500건을 처리해야 합니다.",
    ),
    (
        "CRLF", "/ˌsi ɑr el ˈef/", "줄바꿈을 나타내는 두 글자", API, N,
        "Carriage Return, Line Feed 를 붙여 부르는 말로 윈도우식 줄바꿈이다. "
        "리눅스와 맥은 LF 하나만 쓰기 때문에, 같은 파일이 운영체제에 따라 전부 "
        "바뀐 것처럼 보이는 diff 가 여기서 나온다. HTTP 헤더 구분자이기도 하다.",
        "The whole file shows as changed because of CRLF line endings.",
        "CRLF 줄바꿈 때문에 파일 전체가 변경된 것으로 표시됩니다.",
    ),
    # ---------- 데이터베이스 줄임말 ----------
    (
        "SQL", "/ˈsikwl/", "데이터베이스에 묻는 언어", DB, E,
        "Structured Query Language 의 줄임말. 데이터를 어떻게 가져올지가 아니라 "
        "무엇을 원하는지 적으면 데이터베이스가 방법을 정한다. '시퀄' 로 읽는 사람과 "
        "철자 그대로 '에스큐엘' 로 읽는 사람이 섞여 있고 둘 다 통용된다.",
        "Write it in raw SQL; the ORM query is unreadable here.",
        "여기서는 ORM 쿼리가 읽기 어려우니 SQL 로 직접 쓰세요.",
    ),
    (
        "DBMS", "/ˌdi bi em ˈes/", "데이터베이스를 관리하는 소프트웨어", DB, E,
        "Database Management System 의 줄임말. 데이터 자체가 아니라 그것을 저장하고 "
        "찾아주고 여러 사람이 동시에 써도 안 꼬이게 관리하는 프로그램을 가리킨다. "
        "MySQL 이나 PostgreSQL 이 여기 해당한다. 정처기 기본 용어다.",
        "Which DBMS are we standardizing on?",
        "어떤 DBMS 로 통일할까요?",
    ),
    (
        "RDBMS", "/ˌɑr di bi em ˈes/", "표와 관계로 저장하는 데이터베이스", DB, N,
        "Relational DBMS 의 줄임말. 데이터를 행과 열의 표로 두고 표끼리 관계를 맺는 "
        "방식이다. 정해진 구조와 제약을 강제해 데이터가 어긋나는 것을 막아주는 것이 "
        "가장 큰 장점이다.",
        "We chose an RDBMS because the data has strong relationships.",
        "데이터 간 관계가 강해서 RDBMS 를 골랐습니다.",
    ),
    (
        "DDL", "/ˌdi di ˈel/", "구조를 만들고 바꾸는 명령", DB, N,
        "Data Definition Language 의 줄임말. 표를 만들고 칼럼을 더하는 것처럼 구조를 "
        "다루는 명령이다. MySQL 같은 곳에서는 이 명령이 암묵적으로 커밋을 일으켜 "
        "트랜잭션 안에서도 되돌릴 수 없다는 점이 실무의 함정이다.",
        "That DDL statement cannot be rolled back on MySQL.",
        "MySQL 에서는 그 DDL 문을 롤백할 수 없습니다.",
    ),
    (
        "DML", "/ˌdi em ˈel/", "데이터를 넣고 고치고 지우는 명령", DB, N,
        "Data Manipulation Language 의 줄임말. 구조가 아니라 안에 든 데이터를 다루는 "
        "명령이다. 트랜잭션 안에서 되돌릴 수 있다는 점이 DDL 과 다르고, "
        "정처기에서 이 구분을 자주 묻는다.",
        "Wrap the DML in a transaction so you can roll it back.",
        "롤백할 수 있게 DML 을 트랜잭션으로 감싸세요.",
    ),
    (
        "DCL", "/ˌdi si ˈel/", "권한을 주고 거두는 명령", DB, N,
        "Data Control Language 의 줄임말. 누구에게 어떤 권한을 줄지 다루는 명령이다. "
        "애플리케이션 계정에 모든 권한을 주는 것이 편해서 그렇게 두는 경우가 많은데, "
        "사고가 났을 때 피해 범위를 결정하는 것이 결국 이 설정이다.",
        "The application account has more privileges than it needs.",
        "애플리케이션 계정이 필요 이상의 권한을 갖고 있습니다.",
    ),
    (
        "PK", "/ˌpi ˈkeɪ/", "기본키를 줄여 부르는 말", DB, E,
        "Primary Key 의 줄임말. 설계 문서나 ERD 에서 칼럼 옆에 표시로 붙는다. "
        "말로 할 때도 '피케이' 라고 그냥 쓴다.",
        "Which column is the PK on this table?",
        "이 테이블의 PK 는 어느 칼럼인가요?",
    ),
    (
        "FK", "/ˌef ˈkeɪ/", "외래키를 줄여 부르는 말", DB, E,
        "Foreign Key 의 줄임말. 다른 표를 가리키는 칼럼에 붙는 표시다. "
        "제약을 실제로 걸지 않고 그냥 값만 넣어두는 경우도 많은데, "
        "그러면 가리키는 대상이 없는 데이터가 조용히 쌓인다.",
        "There is no FK constraint here, just a column holding an id.",
        "여기엔 FK 제약이 없고 아이디만 담긴 칼럼이 있습니다.",
    ),
    (
        "WAL", "/wɔl/", "바꾸기 전에 기록부터 남기기", DB, H,
        "Write-Ahead Log 의 줄임말. 데이터 파일을 고치기 전에 무엇을 바꿀지 로그에 "
        "먼저 적어두는 방식이다. 그래서 도중에 전원이 나가도 이 기록을 보고 복구할 수 "
        "있다. 복제와 특정 시점 복원도 이 기록을 재생해 이뤄진다. '월' 로 읽는다.",
        "Point-in-time recovery replays the WAL up to the chosen timestamp.",
        "특정 시점 복구는 지정한 시각까지 WAL 을 재생합니다.",
    ),
    (
        "MVCC", "/ˌem vi si ˈsi/", "버전을 여러 벌 두어 읽기를 막지 않기", DB, H,
        "Multi-Version Concurrency Control 의 줄임말. 값을 덮어쓰지 않고 새 버전을 "
        "만들어 두어서, 읽는 쪽은 옛 버전을 보고 쓰는 쪽은 새로 쓴다. 읽기와 쓰기가 "
        "서로를 기다리지 않아도 되는 이유다. 대신 옛 버전이 쌓이므로 청소가 필요하다.",
        "Readers do not block writers thanks to MVCC.",
        "MVCC 덕분에 읽기가 쓰기를 막지 않습니다.",
    ),
    (
        "CTE", "/ˌsi ti ˈi/", "쿼리 앞에 이름 붙여 떼어둔 조각", DB, N,
        "Common Table Expression 의 줄임말. WITH 로 시작해 쿼리 일부에 이름을 붙여 "
        "떼어두는 것이다. 겹겹이 쌓인 서브쿼리를 위에서 아래로 읽히게 만들어준다. "
        "자기 자신을 참조해 계층 구조를 따라가는 재귀 형태도 쓸 수 있다.",
        "Rewrite those nested subqueries as a CTE.",
        "중첩된 서브쿼리를 CTE 로 다시 쓰세요.",
    ),
    (
        "OLTP", "/ˌoʊ el ti ˈpi/", "짧은 처리를 많이 다루는 용도", DB, H,
        "Online Transaction Processing 의 줄임말. 주문 넣기나 로그인처럼 작은 읽기와 "
        "쓰기가 아주 많이 일어나는 업무를 가리킨다. 서비스 데이터베이스가 여기 해당하고, "
        "여기에 무거운 통계 쿼리를 돌리면 서비스 전체가 느려진다.",
        "Do not run analytics queries against the OLTP database.",
        "OLTP 데이터베이스에 분석 쿼리를 돌리지 마세요.",
    ),
    (
        "OLAP", "/ˈoʊlæp/", "큰 데이터를 모아 분석하는 용도", DB, H,
        "Online Analytical Processing 의 줄임말. 오랜 기간 데이터를 모아 합계와 추이를 "
        "내는 용도다. 한 번에 아주 많은 행을 읽으므로 저장 방식부터 다르게 설계한다. "
        "'오랩' 으로 읽는다.",
        "Move the reporting workload to an OLAP store.",
        "리포트 작업은 OLAP 저장소로 옮기세요.",
    ),
    (
        "ETL", "/ˌi ti ˈel/", "뽑아 바꿔 옮기는 데이터 이동", DB, N,
        "Extract, Transform, Load 의 줄임말. 여러 곳의 데이터를 뽑아 형식을 맞춘 뒤 "
        "분석용 저장소에 넣는 과정이다. 순서를 바꿔 먼저 넣고 나중에 변환하는 방식은 "
        "ELT 라고 따로 부른다.",
        "The nightly ETL job failed, so today's dashboard is empty.",
        "야간 ETL 작업이 실패해서 오늘 대시보드가 비어 있습니다.",
    ),
    (
        "BLOB", "/blɑb/", "형식을 따지지 않고 담는 큰 덩어리", DB, N,
        "Binary Large Object 의 줄임말. 이미지나 파일처럼 큰 이진 데이터를 그대로 담는 "
        "칼럼 타입이다. 데이터베이스에 파일을 직접 넣으면 백업과 복제가 무거워져서, "
        "파일은 따로 저장하고 주소만 담는 방식이 일반적이다.",
        "Store the file in object storage and keep only the path in the database.",
        "파일은 오브젝트 스토리지에 두고 데이터베이스에는 경로만 저장하세요.",
    ),
    (
        "UUID", "/ˌju ju aɪ ˈdi/", "겹치지 않게 만든 긴 식별자", DB, N,
        "Universally Unique Identifier 의 줄임말. 중앙에서 번호를 매기지 않아도 "
        "겹치지 않게 만들어지는 128비트 식별자다. 순서가 없어서 기본키로 쓰면 "
        "인덱스가 여기저기 흩어지는데, 시간 순서를 담은 최신 버전은 이 문제를 줄였다.",
        "Random UUIDs as primary keys fragment the index.",
        "무작위 UUID 를 기본키로 쓰면 인덱스가 단편화됩니다.",
    ),
    (
        "CAP", "/kæp/", "분단 상황에서 둘 중 하나를 고르기", DB, H,
        "일관성·가용성·분단 내성 셋 중 둘만 고를 수 있다고 흔히 소개되지만 "
        "정확하지 않다. 네트워크 분단은 "
        "고르는 것이 아니라 언젠가 일어나는 일이라, 실제 선택은 '분단이 났을 때 "
        "일관성과 가용성 중 무엇을 포기하느냐' 다. 정처기에도 나온다.",
        "Under a network partition, this system favors availability over consistency.",
        "네트워크 분단 시 이 시스템은 일관성보다 가용성을 택합니다.",
    ),
    (
        "BASE", "/beɪs/", "느슨하게 결국 맞춰가는 방식", DB, H,
        "Basically Available, Soft state, Eventually consistent 의 앞 글자. "
        "ACID 와 대비되는 개념으로 NoSQL 쪽에서 쓴다. 지금 당장 정확히 맞지 않아도 "
        "결국 맞아진다면 괜찮다는 태도다. 산성인 ACID 와 염기인 BASE 로 말장난을 한 이름이다.",
        "That store follows BASE semantics, not ACID.",
        "그 저장소는 ACID 가 아니라 BASE 방식을 따릅니다.",
    ),
    # ---------- 배포 / 운영 줄임말 ----------
    (
        "CI", "/ˌsi ˈaɪ/", "합칠 때마다 자동으로 검증하기", OPS, E,
        "Continuous Integration 의 줄임말. 코드를 자주 합치고 그때마다 빌드와 테스트를 "
        "자동으로 돌려 문제를 일찍 발견하는 방식이다. 도구를 쓰는 것 자체가 아니라 "
        "자주 합친다는 습관이 핵심이라, 브랜치를 몇 주씩 묵히면 도구가 있어도 의미가 없다.",
        "CI runs on every push to the branch.",
        "브랜치에 푸시할 때마다 CI 가 돕니다.",
    ),
    (
        "CD", "/ˌsi ˈdi/", "검증된 것을 자동으로 내보내기", OPS, N,
        "Continuous Delivery 또는 Continuous Deployment 의 줄임말. 앞의 것은 언제든 "
        "배포 가능한 상태로 만들어두되 버튼은 사람이 누르고, 뒤의 것은 통과하면 "
        "자동으로 운영까지 나간다. 같은 약자라 어느 쪽인지 문맥으로 구분해야 한다.",
        "We have continuous delivery, but the final deploy is still manual.",
        "지속적 제공까지는 되지만 최종 배포는 아직 수동입니다.",
    ),
    (
        "IaC", "/ˌaɪ eɪ ˈsi/", "infrastructure as code 의 줄임말", OPS, N,
        "Infrastructure as Code 를 줄여 쓴 말. 문서와 채팅에서는 거의 이 형태로만 "
        "쓴다. 철자를 하나씩 '아이에이씨' 로 읽고, 개념 자체는 풀어 쓴 "
        "항목을 따로 보면 된다.",
        "Every environment change goes through IaC, not the console.",
        "모든 환경 변경은 콘솔이 아니라 IaC 를 거칩니다.",
    ),
    (
        "VM", "/ˌvi ˈem/", "가상으로 만든 컴퓨터 한 대", OPS, E,
        "Virtual Machine 의 줄임말. 한 물리 서버 위에 운영체제까지 통째로 얹어 만든 "
        "가상의 컴퓨터다. 컨테이너는 커널을 호스트와 함께 쓰지만 이건 자기 운영체제를 "
        "따로 갖기 때문에 무겁고 뜨는 데 시간이 걸린다.",
        "A VM boots in minutes; a container starts in seconds.",
        "VM 은 부팅에 몇 분이 걸리지만 컨테이너는 몇 초면 뜹니다.",
    ),
    (
        "K8s", "/keɪts/", "쿠버네티스를 줄여 쓴 표기", OPS, N,
        "Kubernetes 의 첫 글자 K 와 끝 글자 s 사이 여덟 글자를 숫자 8 로 줄인 표기. "
        "컨테이너를 어디에 몇 개 띄우고 죽으면 어떻게 살릴지 자동으로 관리하는 도구다. "
        "'케이츠' 로 읽거나 그냥 쿠버네티스라고 읽는다.",
        "We run everything on K8s now.",
        "이제 전부 쿠버네티스 위에서 돌립니다.",
    ),
    (
        "IaaS", "/ˈaɪ æs/", "서버와 네트워크만 빌려 쓰기", OPS, N,
        "Infrastructure as a Service 의 줄임말. 서버, 저장소, 네트워크 같은 밑바탕만 "
        "빌리고 운영체제 위쪽은 직접 관리하는 형태다. 자유도가 가장 높은 대신 "
        "관리할 것도 가장 많다. 정처기 클라우드 문제에 세 형태가 함께 나온다.",
        "With IaaS you still patch the operating system yourself.",
        "IaaS 에서는 운영체제 패치를 직접 해야 합니다.",
    ),
    (
        "PaaS", "/pæs/", "코드만 올리면 나머지는 맡기기", OPS, N,
        "Platform as a Service 의 줄임말. 서버 관리는 맡기고 애플리케이션 코드만 "
        "올리면 되는 형태다. 빠르게 시작할 수 있지만 제공되는 방식 밖으로 나가기 "
        "어렵고, 규모가 커지면 비용이 가파르게 오르는 경우가 많다.",
        "We started on PaaS and moved off when the bill grew.",
        "PaaS 로 시작했다가 비용이 커져서 옮겼습니다.",
    ),
    (
        "SaaS", "/sæs/", "완성된 소프트웨어를 구독해 쓰기", OPS, E,
        "Software as a Service 의 줄임말. 설치 없이 웹으로 접속해 쓰는 완성된 서비스다. "
        "쓰는 입장에서는 관리할 것이 없지만 데이터가 남의 서버에 있으므로, "
        "내보내기가 되는지와 어느 지역에 저장되는지는 확인해야 한다.",
        "Check the data export options before we commit to that SaaS.",
        "그 SaaS 를 도입하기 전에 데이터 내보내기 방법을 확인하세요.",
    ),
    (
        "VPN", "/ˌvi pi ˈen/", "암호화된 통로로 내부망에 접속", OPS, N,
        "Virtual Private Network 의 줄임말. 공용 인터넷 위에 암호화된 통로를 만들어 "
        "마치 내부망에 있는 것처럼 접속하게 해준다. 사내 자원에 붙을 때 쓴다. "
        "이게 없으면 서버가 멀쩡해도 접속 자체가 되지 않는다.",
        "You need to be on the VPN to reach the internal dashboard.",
        "내부 대시보드에 접속하려면 VPN 에 연결해야 합니다.",
    ),
    (
        "WAF", "/wæf/", "공격성 요청을 앞에서 걸러내는 방화벽", OPS, N,
        "Web Application Firewall 의 줄임말. 요청 내용을 보고 공격으로 보이는 패턴을 "
        "차단한다. 코드를 고치기 전 급한 불을 끌 때 유용하지만 근본 대책은 아니고, "
        "정상 요청을 막아버리는 오탐도 생긴다. '와프' 로 읽는다.",
        "The WAF is blocking legitimate requests with long payloads.",
        "본문이 긴 정상 요청을 WAF 가 막고 있습니다.",
    ),
    (
        "RPO", "/ˌɑr pi ˈoʊ/", "얼마까지 잃어도 되는지", OPS, H,
        "Recovery Point Objective 의 줄임말. 장애가 났을 때 데이터를 어느 시점까지 "
        "되살릴지, 즉 최대 몇 분치의 데이터 손실을 감수할지 정한 목표다. "
        "이 값이 백업 주기를 결정한다.",
        "An RPO of five minutes means we back up at least that often.",
        "RPO 가 5분이면 최소 그 주기로 백업해야 합니다.",
    ),
    (
        "RTO", "/ˌɑr ti ˈoʊ/", "얼마 안에 복구할지", OPS, H,
        "Recovery Time Objective 의 줄임말. 장애 발생부터 정상 복구까지 허용되는 시간 "
        "목표다. 데이터 손실 범위를 정하는 RPO 와 짝을 이루고, 둘을 헷갈려 쓰는 경우가 "
        "많다. 하나는 시점이고 하나는 시간이다.",
        "Our RTO is one hour, so a full restore from tape will not work.",
        "RTO 가 한 시간이라 테이프 전체 복원으로는 맞출 수 없습니다.",
    ),
    (
        "MTTR", "/ˌem ti ti ˈɑr/", "고장 나면 평균 얼마 만에 고치는지", OPS, N,
        "Mean Time To Repair 또는 Recovery 의 줄임말. 확장형이 갈리는데 "
        "정처기 같은 시험은 전통적인 Repair 를 쓰고, 요즘 현업에서는 Recovery 를 "
        "많이 쓴다. 장애가 시작돼 복구될 때까지 걸린 시간의 평균이다. 고장이 아예 "
        "안 나게 하는 것보다 빨리 복구하는 쪽에 투자하는 것이 대개 더 현실적이라, "
        "요즘은 이 지표를 더 중요하게 본다.",
        "Improving MTTR matters more than chasing zero incidents.",
        "무장애를 좇는 것보다 MTTR 을 줄이는 게 더 중요합니다.",
    ),
    (
        "MTBF", "/ˌem ti bi ˈef/", "고장과 고장 사이 평균 시간", OPS, H,
        "Mean Time Between Failures 의 줄임말. 한 번 고장 나고 다음 고장까지 얼마나 "
        "버티는지의 평균이다. 이 값이 길수록 안정적이라는 뜻이고, 복구 속도를 재는 "
        "MTTR 과 함께 가용성을 계산하는 데 쓴다. 정처기에 나온다.",
        "Availability is derived from MTBF and MTTR together.",
        "가용성은 MTBF 와 MTTR 을 함께 써서 구합니다.",
    ),
    (
        "SRE", "/ˌes ɑr ˈi/", "운영을 엔지니어링으로 푸는 역할", OPS, N,
        "Site Reliability Engineering 의 줄임말. 서비스 안정성을 사람의 수작업이 아니라 "
        "코드와 지표로 다루는 접근이자 그 일을 하는 직무다. 반복 작업을 자동화해 "
        "없애는 것을 명시적인 목표로 둔다는 점이 일반 운영과 다르다.",
        "The SRE team owns the error budget policy.",
        "오류 예산 정책은 SRE 팀이 담당합니다.",
    ),
    (
        "APM", "/ˌeɪ pi ˈem/", "애플리케이션 성능을 들여다보는 도구", OPS, N,
        "Application Performance Monitoring 의 줄임말. 어떤 요청이 어디서 얼마나 "
        "시간을 쓰는지 코드 수준까지 보여주는 도구다. 서버 자원 지표만으로는 알 수 없는 "
        "느린 쿼리나 외부 호출 지연을 찾아낸다.",
        "The APM trace shows the slow query on the checkout endpoint.",
        "APM 트레이스에 결제 엔드포인트의 느린 쿼리가 보입니다.",
    ),
    (
        "SSH", "/ˌes es ˈeɪtʃ/", "암호화된 원격 접속 방식", OPS, E,
        "Secure Shell 의 줄임말. 원격 서버에 안전하게 접속해 명령을 실행하는 방식으로 "
        "기본 포트는 22 다. 비밀번호보다 열쇠 파일로 접속하는 것이 안전하고, "
        "개인 열쇠는 절대 서버나 저장소에 올리면 안 된다.",
        "Add your public key to the server and disable password login.",
        "서버에 공개키를 등록하고 비밀번호 로그인은 끄세요.",
    ),
    (
        "PID", "/ˌpi aɪ ˈdi/", "실행 중인 프로세스에 붙은 번호", OPS, N,
        "Process ID 의 줄임말. 운영체제가 실행 중인 프로세스마다 붙이는 번호다. "
        "포트가 이미 사용 중일 때 누가 쓰고 있는지 찾아 종료시킬 때 이 번호를 쓴다. "
        "컨테이너 안에서는 주 프로세스가 1번을 갖는다.",
        "Find the PID holding port 8000 and kill it.",
        "8000 포트를 잡고 있는 PID 를 찾아 종료하세요.",
    ),
    (
        "IOPS", "/ˈaɪɑps/", "초당 디스크 입출력 횟수", OPS, H,
        "Input/Output Operations Per Second 의 줄임말. 저장 장치가 1초에 몇 번 읽고 쓸 수 "
        "있는지를 나타낸다. 클라우드 디스크는 이 값에 상한이 걸려 있어서, 용량이 남아도 "
        "여기에 막혀 데이터베이스가 느려지는 일이 흔하다. '아이옵스' 로 읽는다.",
        "The database is slow because we hit the disk IOPS limit.",
        "디스크 IOPS 한도에 걸려서 데이터베이스가 느립니다.",
    ),
    (
        "HA", "/ˌeɪtʃ ˈeɪ/", "한 대가 죽어도 계속 도는 구성", OPS, N,
        "High Availability 의 줄임말. 장애가 나도 서비스가 이어지도록 여분을 두는 구성이다. "
        "핵심은 단일 장애점을 없애는 것인데, 서버를 두 대로 늘려놓고도 데이터베이스가 "
        "한 대라면 아무 의미가 없다.",
        "The setup is not HA; the database is still a single point of failure.",
        "이 구성은 HA 가 아닙니다. 데이터베이스가 여전히 단일 장애점입니다.",
    ),
    (
        "DR", "/ˌdi ˈɑr/", "큰 재해에 대비한 복구 계획", OPS, H,
        "Disaster Recovery 의 줄임말. 지역 전체가 마비되는 수준의 사고에 대비해 다른 곳에 "
        "복구 수단을 두는 것이다. 계획을 세워두는 것보다 실제로 한 번 전환해보는 것이 "
        "중요한데, 해보면 문서에 없던 단계가 반드시 나온다.",
        "We run a DR drill twice a year.",
        "1년에 두 번 재해 복구 훈련을 합니다.",
    ),
    # ---------- 디버깅 / 테스트 줄임말 ----------
    (
        "QA", "/ˌkju ˈeɪ/", "품질을 확인하고 지키는 활동", DEBUG, E,
        "Quality Assurance 의 줄임말. 만들어진 것을 확인하는 활동과 그 담당자를 함께 "
        "가리킨다. 개발이 끝난 뒤 검사하는 단계로만 두면 발견이 늦어져서, "
        "요구사항을 정할 때부터 참여하는 편이 실제로는 훨씬 싸다.",
        "QA found the issue on the staging environment.",
        "QA 가 스테이징 환경에서 그 문제를 발견했습니다.",
    ),
    (
        "UAT", "/ˌju eɪ ˈti/", "실제 사용자가 확인하는 최종 검수", DEBUG, N,
        "User Acceptance Testing 의 줄임말. 개발자가 아니라 실제로 그 기능을 쓸 사람이 "
        "요구한 대로 되는지 확인하는 단계다. 동작이 맞는지가 아니라 원하던 것이 맞는지를 "
        "본다는 점이 다른 테스트와 구별된다.",
        "UAT starts Monday; the business team will run through the scenarios.",
        "월요일부터 UAT 를 시작해 현업 팀이 시나리오를 확인합니다.",
    ),
    (
        "BDD", "/ˌbi di ˈdi/", "행동을 문장으로 적고 검증하기", DEBUG, H,
        "Behavior-Driven Development 의 줄임말. '어떤 상황에서 무엇을 하면 어떻게 된다' 는 "
        "형식의 문장으로 기대 동작을 적고 그대로 테스트를 만든다. 개발자가 아닌 사람도 "
        "읽을 수 있게 하는 것이 목적이라, 그 사람들이 안 읽으면 손만 더 가는 형식이 된다.",
        "Write the scenario in BDD style so the product owner can review it.",
        "기획자가 검토할 수 있게 시나리오를 BDD 형식으로 쓰세요.",
    ),
    (
        "RCA", "/ˌɑr si ˈeɪ/", "원인을 끝까지 파고드는 분석", DEBUG, N,
        "Root Cause Analysis 의 줄임말. 증상에서 멈추지 않고 왜를 반복해 물으며 "
        "진짜 원인까지 내려가는 절차다. 대개 하나가 아니라 여러 원인이 겹쳐 있어서, "
        "하나만 찾고 끝내면 형태를 바꿔 다시 나타난다.",
        "The RCA is attached to the incident ticket.",
        "장애 티켓에 원인 분석이 첨부돼 있습니다.",
    ),
    (
        "NPE", "/ˌen pi ˈi/", "널 값을 쓰려다 난 예외", DEBUG, E,
        "Null Pointer Exception 의 줄임말. 값이 없는 대상의 기능을 쓰려다 나는 예외로, "
        "자바 계열 로그에서 가장 흔하게 보인다. 그 줄을 방어하는 것으로 끝내면 "
        "왜 비어 있었는지가 그대로 남아 다른 곳에서 다시 터진다.",
        "The log is full of NPEs from that mapper.",
        "로그가 그 매퍼에서 나온 NPE 로 가득합니다.",
    ),
    (
        "OOM", "/ˌoʊ oʊ ˈem/", "메모리가 모자라 강제 종료됨", DEBUG, N,
        "Out Of Memory 의 줄임말. 쓸 메모리가 없는 상황인데, 누가 끝내느냐에 따라 "
        "증상이 다르다. 운영체제가 죽이면(OOM killer) 앱 로그에 아무것도 안 남고 "
        "그냥 끊긴 것처럼 보여 시스템 로그를 봐야 한다. 반대로 JVM 처럼 런타임이 "
        "먼저 알아채면 OutOfMemoryError 가 앱 로그에 스택 트레이스와 함께 찍힌다.",
        "The container was OOM killed; there is nothing in the app log.",
        "컨테이너가 OOM 으로 강제 종료됐습니다. 앱 로그에는 아무것도 없습니다.",
    ),
    (
        "EOF", "/ˌi oʊ ˈef/", "읽을 것이 더 없다는 표시", DEBUG, N,
        "End Of File 의 줄임말. 파일이나 연결에서 더 읽을 데이터가 없음을 나타낸다. "
        "예상치 못한 지점에서 이 오류가 나면 파일이 잘렸거나 상대가 연결을 먼저 "
        "끊었다는 뜻이라, 파싱 문제가 아니라 전송 문제인 경우가 많다.",
        "Unexpected EOF usually means the connection was closed early.",
        "예상치 못한 EOF 는 대개 연결이 먼저 끊겼다는 뜻입니다.",
    ),
    (
        "SIGTERM", "/ˈsɪɡtɜrm/", "정리하고 내려가라는 종료 신호", DEBUG, N,
        "프로세스에게 종료를 요청하는 신호. 프로그램이 이 신호를 받아 하던 일을 마치고 "
        "정리한 뒤 내려갈 수 있다. 배포할 때 먼저 이 신호가 오고, 정해진 시간 안에 "
        "안 내려가면 더 강한 신호가 뒤따른다.",
        "The process ignores SIGTERM, so it gets killed after the grace period.",
        "이 프로세스가 SIGTERM 을 무시해서 유예 시간 뒤에 강제 종료됩니다.",
    ),
    (
        "SIGKILL", "/ˈsɪɡkɪl/", "붙잡을 수 없는 즉시 종료 신호", DEBUG, N,
        "프로세스를 즉시 끝내는 신호. 프로그램이 이 신호를 받아 처리할 방법이 아예 없어서 "
        "정리 작업도 못 하고 그 자리에서 끝난다. 그래서 처리 중이던 요청이나 "
        "저장하지 못한 데이터는 그대로 사라진다.",
        "SIGKILL cannot be caught, so nothing gets cleaned up.",
        "SIGKILL 은 가로챌 수 없어서 아무 정리도 되지 않습니다.",
    ),
    (
        "REPL", "/ˈrepəl/", "한 줄씩 쳐서 바로 결과 보는 환경", DEBUG, N,
        "Read-Eval-Print Loop 의 줄임말. 코드를 한 줄 입력하면 바로 실행해 결과를 "
        "보여주는 대화형 환경이다. 파이썬 셸이나 브라우저 콘솔이 여기 해당한다. "
        "가설을 빨리 확인하는 데 파일을 만들어 실행하는 것보다 훨씬 빠르다. '레플' 로 읽는다.",
        "Try it in the REPL before you put it in the script.",
        "스크립트에 넣기 전에 REPL 에서 먼저 해보세요.",
    ),
    (
        "MRE", "/ˌem ɑr ˈi/", "문제만 남긴 최소 재현 코드", DEBUG, N,
        "Minimal Reproducible Example 의 줄임말. 문제를 그대로 재현하되 관련 없는 부분을 "
        "전부 걷어낸 짧은 코드다. 이걸 만드는 과정에서 원인을 스스로 찾는 경우가 많아서, "
        "질문하기 전에 만들어보라는 조언이 여기서 나온다.",
        "Please attach an MRE; the full project is too large to debug.",
        "최소 재현 코드를 첨부해 주세요. 전체 프로젝트는 너무 커서 보기 어렵습니다.",
    ),
    # ---------- 프론트엔드 줄임말 ----------
    (
        "HTML", "/ˌeɪtʃ ti em ˈel/", "문서의 구조를 나타내는 표기 언어", FRONT, E,
        "HyperText Markup Language 의 줄임말. 태그로 감싸 이건 제목, 이건 목록이라고 "
        "구조를 나타낸다. 프로그래밍 언어가 아니라 표기 언어라서 조건이나 반복이 없다. "
        "생김새는 CSS 가, 동작은 자바스크립트가 맡는다.",
        "Fix the HTML structure first; the styling problem follows from it.",
        "HTML 구조부터 고치세요. 스타일 문제는 거기서 비롯됩니다.",
    ),
    (
        "CSS", "/ˌsi es ˈes/", "생김새를 정하는 스타일 언어", FRONT, E,
        "Cascading Style Sheets 의 줄임말. 요소가 어떻게 보일지 정한다. 이름의 앞부분은 "
        "여러 규칙이 겹칠 때 위에서 아래로 흘러내리며 우선순위가 정해진다는 뜻이라, "
        "스타일이 안 먹는 문제의 절반은 이 규칙을 몰라서 생긴다.",
        "The CSS is not applied because a more specific rule wins.",
        "더 구체적인 규칙이 이겨서 이 CSS 가 적용되지 않습니다.",
    ),
    (
        "SVG", "/ˌes vi ˈdʒi/", "수식으로 그려 확대해도 안 깨지는 이미지", FRONT, N,
        "Scalable Vector Graphics 의 줄임말. 점의 색을 나열하는 대신 선과 도형을 좌표로 "
        "기술해서 아무리 확대해도 깨지지 않는다. 텍스트 파일이라 코드에서 색을 바꾸거나 "
        "애니메이션을 줄 수 있는 것이 큰 장점이다. 아이콘과 로고에 쓴다.",
        "Use SVG for the logo so it stays sharp on high-density screens.",
        "고해상도 화면에서도 선명하도록 로고는 SVG 를 쓰세요.",
    ),
    (
        "SEO", "/ˌes i ˈoʊ/", "검색에 잘 걸리게 만드는 일", FRONT, N,
        "Search Engine Optimization 의 줄임말. 검색 결과에 잘 노출되도록 페이지를 "
        "다듬는 것이다. 요령보다 의미에 맞는 태그, 적절한 제목, 빠른 로딩 같은 기본이 "
        "훨씬 크게 작용한다. 스크립트로만 그리는 화면은 여기서 불리해진다.",
        "Client-side only rendering hurts SEO on content pages.",
        "콘텐츠 페이지를 클라이언트에서만 렌더링하면 SEO 에 불리합니다.",
    ),
    (
        "LCP", "/ˌel si ˈpi/", "가장 큰 요소가 보이기까지의 시간", FRONT, H,
        "Largest Contentful Paint 의 줄임말. 화면에서 가장 큰 이미지나 텍스트 덩어리가 "
        "그려질 때까지 걸린 시간이다. 사용자가 '이제 떴다' 고 느끼는 시점에 가장 가까운 "
        "지표라서 구글이 핵심 지표로 쓴다. 대개 이미지 최적화로 크게 개선된다.",
        "The hero image is what makes our LCP so slow.",
        "히어로 이미지 때문에 LCP 가 느립니다.",
    ),
    (
        "CLS", "/ˌsi el ˈes/", "화면이 밀린 정도를 나타낸 점수", FRONT, H,
        "Cumulative Layout Shift 의 줄임말. 로딩 도중 내용이 얼마나 밀렸는지를 누적해 "
        "점수로 나타낸다. 값이 클수록 읽던 위치가 자주 흔들렸다는 뜻이다. "
        "이미지와 광고 자리에 크기를 미리 잡아두면 대부분 잡힌다.",
        "Reserving space for the banner brought our CLS down.",
        "배너 자리를 미리 잡아뒀더니 CLS 가 내려갔습니다.",
    ),
    (
        "INP", "/ˌaɪ en ˈpi/", "눌렀을 때 반응하기까지의 지연", FRONT, H,
        "Interaction to Next Paint 의 줄임말. 사용자가 누른 뒤 화면이 실제로 반응해 "
        "다시 그려지기까지 걸린 시간이다. 2024년에 첫 입력 지연을 재던 FID 를 대신해 "
        "핵심 지표가 됐고, 첫 입력만이 아니라 전체 상호작용을 본다는 점이 다르다.",
        "Long tasks on the main thread are what push our INP up.",
        "메인 스레드의 긴 작업 때문에 INP 가 올라갑니다.",
    ),
    (
        "FCP", "/ˌef si ˈpi/", "뭐라도 처음 그려진 시점", FRONT, N,
        "First Contentful Paint 의 줄임말. 빈 화면에서 벗어나 처음으로 무언가 그려진 "
        "시점이다. 사용자가 반응할 수 있게 됐다는 뜻은 아니라서, 이 값만 좋고 "
        "실제로는 아무것도 눌리지 않는 상태일 수 있다.",
        "FCP looks fine, but the page is not usable until much later.",
        "FCP 는 괜찮아 보이지만 한참 뒤에야 실제로 쓸 수 있습니다.",
    ),
    (
        "TTFB", "/ˌti ti ef ˈbi/", "첫 바이트가 도착하기까지의 시간", FRONT, N,
        "Time To First Byte 의 줄임말. 요청을 보내고 응답의 첫 조각이 도착할 때까지의 "
        "시간이다. 이 값이 크면 원인이 프론트가 아니라 서버나 네트워크 쪽에 있다는 "
        "신호라, 화면 최적화를 아무리 해도 나아지지 않는다.",
        "A high TTFB points at the server, not at the bundle size.",
        "TTFB 가 높다면 번들 크기가 아니라 서버 문제입니다.",
    ),
    (
        "PWA", "/ˌpi dʌblju ˈeɪ/", "앱처럼 설치해 쓰는 웹", FRONT, N,
        "Progressive Web App 의 줄임말. 웹 페이지를 홈 화면에 설치하고 오프라인에서도 "
        "일부 동작하게 만든 형태다. 앱 스토어를 거치지 않아도 되는 것이 장점이지만 "
        "기기 기능 접근에는 제약이 있다.",
        "We shipped a PWA instead of building two native apps.",
        "네이티브 앱을 두 개 만드는 대신 PWA 를 출시했습니다.",
    ),
    (
        "WASM", "/ˈwɑzəm/", "브라우저에서 도는 저수준 실행 형식", FRONT, H,
        "WebAssembly 의 줄임말. 다른 언어로 짠 코드를 브라우저에서 빠르게 실행할 수 있게 "
        "만든 이진 형식이다. 자바스크립트를 대체하려는 것이 아니라 무거운 계산을 맡기는 "
        "용도에 가깝다. 화면 요소를 직접 다루려면 결국 자바스크립트를 거쳐야 한다. "
        "'와즘' 으로 읽는다.",
        "The image filter runs in WASM for speed.",
        "속도를 위해 이미지 필터를 WASM 으로 실행합니다.",
    ),
    (
        "JSX", "/ˌdʒeɪ es ˈeks/", "코드 안에 화면 구조를 쓰는 문법", FRONT, N,
        "자바스크립트 안에 HTML 처럼 생긴 구조를 그대로 쓸 수 있게 한 문법 확장. "
        "브라우저가 바로 이해하지 못해서 빌드 단계에서 함수 호출로 바뀐다. "
        "HTML 과 비슷해 보이지만 class 대신 className 을 쓰는 등 이름이 다른 부분이 있다.",
        "JSX compiles down to plain function calls.",
        "JSX 는 결국 평범한 함수 호출로 변환됩니다.",
    ),
    (
        "npm", "/ˌen pi ˈem/", "자바스크립트 패키지 관리 도구", FRONT, E,
        "자바스크립트 패키지 관리 도구이자 그 저장소. 이름을 줄임말로 풀지 않으며 소문자로 쓰는 것이 "
        "관례다. 설치된 정확한 버전은 잠금 파일에 기록되므로 이 파일을 커밋해야 "
        "다른 사람 환경에서 같은 버전이 깔린다.",
        "Commit the lock file so everyone installs the same versions.",
        "모두가 같은 버전을 설치하도록 잠금 파일을 커밋하세요.",
    ),
    (
        "HMR", "/ˌeɪtʃ em ˈɑr/", "새로고침 없이 바뀐 부분만 교체", FRONT, N,
        "Hot Module Replacement 의 줄임말. 코드를 고치면 페이지를 새로 고치지 않고 "
        "바뀐 부분만 갈아 끼워준다. 입력하던 값이나 열어둔 화면 상태가 유지되는 것이 "
        "장점인데, 상태가 꼬였다고 느껴지면 한 번 새로고침해보는 것이 먼저다.",
        "HMR keeps the form state while you tweak the styles.",
        "HMR 덕분에 스타일을 고치는 동안 폼 입력값이 유지됩니다.",
    ),
    (
        "SSG", "/ˌes es ˈdʒi/", "빌드할 때 미리 다 그려두기", FRONT, N,
        "Static Site Generation 의 줄임말. 요청이 올 때가 아니라 빌드 시점에 HTML 을 "
        "미리 만들어두는 방식이다. 서버가 할 일이 없어 가장 빠르고 싸지만, 내용이 바뀌면 "
        "다시 빌드해야 해서 자주 바뀌는 데이터에는 맞지 않는다.",
        "The docs site is SSG, so every deploy rebuilds all pages.",
        "문서 사이트는 SSG 라서 배포할 때마다 전체 페이지를 다시 빌드합니다.",
    ),
    (
        "ISR", "/ˌaɪ es ˈɑr/", "미리 만들어두되 주기적으로 갱신", FRONT, H,
        "Incremental Static Regeneration 의 줄임말. 미리 만들어둔 페이지를 쓰되 정해진 "
        "시간이 지나면 뒤에서 새로 만들어 교체하는 방식이다. 정적인 속도와 어느 정도의 "
        "최신성을 함께 가져가려는 절충안이고, 만료 직후 첫 방문자는 아직 옛 내용을 본다.",
        "With ISR the first visitor after expiry still sees the stale page.",
        "ISR 에서는 만료 직후 첫 방문자가 아직 옛 페이지를 봅니다.",
    ),
    (
        "UI", "/ˌju ˈaɪ/", "사용자가 마주하는 화면과 조작 요소", FRONT, E,
        "User Interface 의 줄임말. 버튼, 입력창, 배치처럼 눈에 보이고 손이 닿는 부분이다. "
        "보기 좋은지의 문제로 좁혀 생각하기 쉽지만, 지금 무엇을 할 수 있는지가 "
        "분명히 드러나는지가 더 중요하다.",
        "The UI does not make it clear that the field is required.",
        "이 UI 는 해당 항목이 필수라는 걸 분명히 보여주지 않습니다.",
    ),
    (
        "UX", "/ˌju ˈeks/", "쓰면서 겪게 되는 경험 전체", FRONT, N,
        "User Experience 의 줄임말. 화면뿐 아니라 얼마나 기다렸는지, 실수했을 때 어떻게 "
        "복구했는지까지 포함한다. 화면을 예쁘게 만드는 것과는 다른 이야기라서, "
        "로딩이 빨라지는 것만으로도 크게 좋아지는 경우가 많다.",
        "Making the error message actionable is a UX fix, not a design change.",
        "에러 메시지를 조치 가능하게 바꾸는 건 디자인이 아니라 UX 개선입니다.",
    ),
    (
        "i18n", "/ˌaɪ ˌeɪtin ˈen/", "여러 언어를 담을 수 있게 만들기", FRONT, N,
        "internationalization 의 첫 글자 i 와 끝 글자 n 사이 열여덟 글자를 숫자로 줄인 "
        "표기. 번역을 하는 것이 아니라 번역할 수 있는 구조로 만드는 작업이다. "
        "문장을 코드에 직접 박아두면 나중에 전부 찾아 고쳐야 한다.",
        "Do not hardcode strings; they need to go through i18n.",
        "문자열을 하드코딩하지 마세요. i18n 을 거쳐야 합니다.",
    ),
    (
        "l10n", "/ˌel ˌten ˈen/", "특정 지역에 맞게 실제로 바꾸기", FRONT, H,
        "localization 을 같은 방식으로 줄인 표기. 구조를 갖추는 i18n 과 달리 실제 번역, "
        "날짜와 통화 표기, 문화에 맞는 표현까지 바꾸는 작업이다. 번역만 하고 "
        "날짜 형식을 그대로 두면 반쪽짜리가 된다.",
        "Translation is only part of l10n; date and currency formats matter too.",
        "번역은 l10n 의 일부일 뿐입니다. 날짜와 통화 형식도 중요합니다.",
    ),
    (
        "a11y", "/ˌeɪ ɪˈlevən ˌwaɪ/", "접근성을 줄여 쓴 표기", FRONT, N,
        "accessibility 의 첫 글자와 끝 글자 사이 열한 글자를 숫자로 줄인 표기. "
        "'에이일레븐와이' 또는 '앨리' 로 읽는다. 채널 이름이나 이슈 라벨에서 "
        "이 형태로 자주 마주친다.",
        "There is an a11y label on that issue.",
        "그 이슈에 접근성 라벨이 붙어 있습니다.",
    ),
    (
        "SPA fallback", "/ˌes pi ˈeɪ ˌfɔlbæk/", "모르는 경로를 첫 화면으로 넘기기", FRONT, H,
        "서버가 알지 못하는 경로로 요청이 오면 404 대신 앱의 시작 파일을 돌려주도록 "
        "해두는 설정. 화면 전환을 브라우저가 맡는 구조에서는 이게 없으면 "
        "중첩된 주소를 새로고침할 때 404 가 난다.",
        "Add an SPA fallback so deep links survive a refresh.",
        "새로고침해도 깊은 링크가 살아남도록 SPA fallback 을 설정하세요.",
    ),
    # ---------- CS / 정보처리기사 줄임말 ----------
    (
        "OSI", "/ˌoʊ es ˈaɪ/", "통신을 일곱 층으로 나눈 참조 모형", CS, H,
        "Open Systems Interconnection 의 줄임말. 통신 과정을 물리, 데이터링크, 네트워크, "
        "전송, 세션, 표현, 응용의 일곱 계층으로 나눈 모형이다. 실제 인터넷은 이 모형이 "
        "아니라 더 단순한 TCP/IP 구조로 돌아가지만, 문제를 어느 층에서 찾을지 "
        "말할 때 공통 언어가 된다. 정처기 필수 암기 항목이다.",
        "That failure is at the network layer, not the application layer.",
        "그 장애는 응용 계층이 아니라 네트워크 계층 문제입니다.",
    ),
    (
        "RAID", "/reɪd/", "디스크를 묶어 안정성이나 속도를 얻기", CS, H,
        "Redundant Array of Independent Disks 의 줄임말(처음에는 Independent 가 "
        "아니라 Inexpensive 였다). 여러 디스크를 묶어 하나처럼 쓰는 방식. "
        "0 은 나눠 담아 빠르지만 하나만 고장 나도 "
        "전부 잃고, 1 은 똑같이 복사해 안전한 대신 용량이 절반이 된다. 5 는 패리티를 "
        "분산해 한 대까지 견딘다. 백업을 대신하지는 못한다는 점이 중요하다. '레이드' 로 읽는다.",
        "RAID protects against disk failure, not against deleting the wrong file.",
        "RAID 는 디스크 고장을 막아줄 뿐 잘못 지운 파일까지 막아주지는 않습니다.",
    ),
    (
        "CPU", "/ˌsi pi ˈju/", "계산을 담당하는 중앙 장치", CS, E,
        "Central Processing Unit 의 줄임말. 명령을 하나씩 꺼내 해석하고 실행하는 부품이다. "
        "사용률이 100퍼센트라고 무조건 문제인 것은 아니고, 대기 없이 일하는 중일 수도 있다. "
        "정작 느린 원인이 입출력 대기인 경우가 더 많다.",
        "The CPU is idle; the process is waiting on disk.",
        "CPU 는 놀고 있고 프로세스는 디스크를 기다리는 중입니다.",
    ),
    (
        "GPU", "/ˌdʒi pi ˈju/", "같은 계산을 대량으로 병렬 처리", CS, N,
        "Graphics Processing Unit 의 줄임말. 원래 화면을 그리려고 만들어졌지만, 단순한 "
        "계산을 수천 개씩 동시에 처리하는 구조라 지금은 기계학습에도 쓴다. "
        "복잡한 분기가 많은 일반 코드는 오히려 CPU 가 빠르다.",
        "Training runs on the GPU; the preprocessing stays on the CPU.",
        "학습은 GPU 에서 돌고 전처리는 CPU 에 남습니다.",
    ),
    (
        "RAM", "/ræm/", "전원이 꺼지면 사라지는 작업 공간", CS, E,
        "Random Access Memory 의 줄임말. 프로그램이 실행되는 동안 데이터를 올려두는 "
        "빠른 공간이고 전원이 끊기면 내용이 사라진다. 어느 위치든 같은 속도로 접근할 수 "
        "있어서 임의 접근이라는 이름이 붙었다.",
        "The dataset does not fit in RAM, so it spills to disk.",
        "데이터셋이 RAM 에 다 들어가지 않아 디스크로 넘칩니다.",
    ),
    (
        "ROM", "/rɑm/", "지워지지 않게 새겨둔 저장 공간", CS, N,
        "Read Only Memory 의 줄임말. 전원이 꺼져도 내용이 남고 보통은 바꾸지 않는다. "
        "컴퓨터가 켜질 때 가장 먼저 실행되는 코드가 여기 들어 있다. "
        "요즘 것은 특별한 절차로 갱신이 가능해서 완전히 읽기 전용은 아니다.",
        "The boot firmware lives in ROM.",
        "부팅 펌웨어는 ROM 에 들어 있습니다.",
    ),
    (
        "SSD", "/ˌes es ˈdi/", "회전 부품 없는 반도체 저장 장치", CS, E,
        "Solid State Drive 의 줄임말. 원판을 돌려 읽던 방식과 달리 반도체에 저장해서 "
        "임의 위치 접근이 훨씬 빠르다. 데이터베이스 성능이 크게 달라지는 이유다. "
        "쓰기 횟수에 수명 한계가 있다는 점은 여전히 남아 있다.",
        "Moving the database to SSD cut the query time in half.",
        "데이터베이스를 SSD 로 옮겼더니 쿼리 시간이 절반으로 줄었습니다.",
    ),
    (
        "I/O", "/ˌaɪ ˈoʊ/", "바깥과 데이터를 주고받는 일", CS, N,
        "Input/Output 의 줄임말. 디스크를 읽거나 네트워크로 보내는 것처럼 프로그램 밖과 "
        "데이터를 주고받는 작업이다. CPU 계산보다 수천 배 느려서, 여기서 기다리는 동안 "
        "CPU 는 놀고 있게 된다. 비동기 처리가 필요한 이유다.",
        "This is an I/O bound workload, so more CPU cores will not help.",
        "이건 I/O 병목이라 코어를 늘려도 나아지지 않습니다.",
    ),
    (
        "OS", "/ˌoʊ ˈes/", "하드웨어와 프로그램 사이를 중재", CS, E,
        "Operating System 의 줄임말. 메모리와 CPU 를 프로그램들에게 나눠주고 하드웨어를 "
        "대신 다뤄준다. 프로그램은 하드웨어를 직접 만지지 않고 정해진 요청으로만 "
        "부탁하는데, 그래서 한 프로그램이 잘못돼도 전체가 무너지지 않는다.",
        "That behavior depends on the OS, so it differs on Windows.",
        "그 동작은 OS 에 따라 달라서 윈도우에서는 다르게 나옵니다.",
    ),
    (
        "IP", "/ˌaɪ ˈpi/", "네트워크에서 위치를 나타내는 주소 체계", CS, E,
        "Internet Protocol 의 줄임말. 어느 기기로 보낼지 주소로 지정해 데이터를 전달하는 "
        "규약이다. 도착을 보장하지 않고 순서도 지켜주지 않기 때문에, 그 보장은 "
        "위층의 TCP 가 맡는다.",
        "IP alone does not guarantee delivery; TCP adds that.",
        "IP 만으로는 전달이 보장되지 않고 TCP 가 그걸 더해줍니다.",
    ),
    (
        "IPv4", "/ˌaɪ pi ˈvi ˌfɔr/", "점으로 나눈 네 자리 주소 체계", CS, N,
        "숫자 네 덩어리를 점으로 이어 적는 주소 체계로 약 43억 개를 표현한다. "
        "이미 부족해져서 여러 기기가 하나의 공인 주소를 나눠 쓰는 방식이 널리 퍼졌다. "
        "정처기에서 주소 클래스와 함께 나온다.",
        "We are running out of IPv4 addresses in this subnet.",
        "이 서브넷의 IPv4 주소가 부족해지고 있습니다.",
    ),
    (
        "IPv6", "/ˌaɪ pi ˈvi ˌsɪks/", "주소를 훨씬 길게 늘린 체계", CS, N,
        "128비트를 써서 사실상 고갈 걱정이 없는 주소 체계. 콜론으로 나눈 열여섯 진수로 "
        "적는다. 옛 체계와 그대로 호환되지 않아 전환이 느리고, 그래서 두 체계를 "
        "동시에 지원하는 구성이 많다.",
        "The service listens on IPv4 only, so IPv6 clients fail.",
        "서비스가 IPv4 로만 열려 있어서 IPv6 클라이언트는 접속이 안 됩니다.",
    ),
    (
        "CIDR", "/ˈsaɪdər/", "슬래시로 주소 범위를 나타내는 표기", CS, H,
        "Classless Inter-Domain Routing 의 줄임말. 10.0.0.0/24 처럼 슬래시 뒤 숫자로 "
        "앞의 몇 비트가 네트워크인지 나타낸다. /24 는 주소 256개를 뜻하지만 "
        "실제로 기기에 줄 수 있는 것은 254개다 - 맨 앞은 네트워크 주소, 맨 뒤는 "
        "브로드캐스트 주소로 예약돼 있다. 정처기 계산 문제가 여기서 나온다. "
        "방화벽 규칙과 클라우드 네트워크 설정에서 매일 만나는 표기다. '사이더' 로 읽는다.",
        "Allow traffic only from the 10.0.1.0/24 CIDR block.",
        "10.0.1.0/24 대역에서 오는 트래픽만 허용하세요.",
    ),
    (
        "MAC", "/mæk/", "기기 자체에 붙은 하드웨어 주소", CS, N,
        "Media Access Control 주소의 줄임말. 네트워크 장치마다 제조 시점에 붙는 고유 "
        "번호다. IP 주소가 상황에 따라 바뀌는 논리 주소라면 이건 기기에 붙박이로 있다. "
        "같은 네트워크 안에서 실제 전달은 이 주소로 이뤄진다.",
        "The switch forwards frames using the MAC address, not the IP.",
        "스위치는 IP 가 아니라 MAC 주소로 프레임을 전달합니다.",
    ),
    (
        "ARP", "/ɑrp/", "IP 로 하드웨어 주소를 알아내기", CS, H,
        "Address Resolution Protocol 의 줄임말. 같은 네트워크에서 상대의 IP 는 아는데 "
        "실제 전달에 필요한 MAC 주소를 모를 때 물어보는 규약이다. 결과를 잠시 저장해두기 "
        "때문에, 서버를 교체한 직후 잠깐 옛 기기로 가는 현상이 생긴다.",
        "Clear the ARP cache after you swap the network card.",
        "네트워크 카드를 교체한 뒤 ARP 캐시를 비우세요.",
    ),
    (
        "DHCP", "/ˌdi eɪtʃ si ˈpi/", "IP 주소를 자동으로 나눠주는 규약", CS, N,
        "Dynamic Host Configuration Protocol 의 줄임말. 접속한 기기에 IP 주소와 "
        "관련 설정을 자동으로 빌려주는 규약. 빌려주는 기간이 "
        "있어서 만료되면 갱신하는데, 그때 주소가 바뀔 수 있다. 서버처럼 주소가 "
        "고정돼야 하는 기기는 자동 할당 대상에서 빼둔다.",
        "The server should have a static IP, not one from DHCP.",
        "서버는 DHCP 가 아니라 고정 IP 를 써야 합니다.",
    ),
    (
        "ICMP", "/ˌaɪ si em ˈpi/", "네트워크 상태를 알리는 제어용 규약", CS, H,
        "데이터를 나르는 것이 아니라 도달할 수 없다거나 시간이 초과됐다는 소식을 "
        "전하는 규약. ping 과 경로 추적이 이걸 쓴다. 보안상 막아둔 서버가 많아서 "
        "ping 이 안 된다고 서버가 죽은 것은 아니다.",
        "Ping fails because ICMP is blocked, not because the host is down.",
        "호스트가 죽은 게 아니라 ICMP 가 막혀서 ping 이 실패하는 겁니다.",
    ),
    (
        "NAT", "/næt/", "사설 주소를 공인 주소로 바꿔주기", CS, H,
        "Network Address Translation 의 줄임말. 내부에서 쓰는 사설 주소를 하나의 공인 "
        "주소로 바꿔 인터넷과 통신하게 해준다. 주소 부족을 미룬 장치이자, 밖에서 "
        "안으로 먼저 접속할 수 없게 만드는 효과도 있다. '냇' 으로 읽는다.",
        "The container cannot be reached from outside because of NAT.",
        "NAT 때문에 밖에서 그 컨테이너로 접속할 수 없습니다.",
    ),
    (
        "LAN", "/læn/", "한 건물 안 규모의 좁은 네트워크", CS, E,
        "Local Area Network 의 줄임말. 사무실이나 집처럼 좁은 범위를 묶은 네트워크다. "
        "거리가 짧아 빠르고 지연이 적다. 정처기에서 넓은 범위를 뜻하는 WAN 과 "
        "짝으로 나온다. '랜' 으로 읽는다.",
        "Both machines are on the same LAN, so latency is negligible.",
        "두 장비가 같은 LAN 에 있어서 지연은 무시할 수준입니다.",
    ),
    (
        "WAN", "/wɑn/", "지역을 넘어 잇는 넓은 네트워크", CS, N,
        "Wide Area Network 의 줄임말. 도시나 국가를 넘어 떨어진 네트워크들을 잇는다. "
        "거리가 멀어 지연이 커지고, 그래서 같은 코드가 지역 간 통신에서 훨씬 느려진다. "
        "'완' 으로 읽는다.",
        "Cross-region calls go over the WAN, so budget for the latency.",
        "지역 간 호출은 WAN 을 타므로 지연을 감안해야 합니다.",
    ),
    (
        "VLAN", "/ˈvilæn/", "물리 배선과 무관하게 나눈 논리 구역", CS, H,
        "같은 스위치에 꽂혀 있어도 논리적으로 서로 다른 네트워크로 나누는 기술. "
        "선을 다시 깔지 않고도 부서나 용도별로 구역을 분리할 수 있다. "
        "다른 구역끼리 통신하려면 라우터를 거쳐야 한다.",
        "Put the office devices and the servers on separate VLANs.",
        "사무용 기기와 서버를 서로 다른 VLAN 에 두세요.",
    ),
    (
        "FIFO", "/ˈfaɪfoʊ/", "먼저 들어온 것을 먼저 처리", CS, E,
        "First In, First Out 의 줄임말. 큐가 동작하는 방식이자 페이지 교체나 작업 처리 "
        "순서를 말할 때 쓰는 표현이다. 공정해 보이지만 오래 쓰이는 항목까지 순서대로 "
        "밀어내기 때문에 캐시 교체 방식으로는 좋지 않다. '파이포' 로 읽는다.",
        "The queue is FIFO, so the oldest job runs first.",
        "이 큐는 FIFO 라 가장 오래된 작업이 먼저 실행됩니다.",
    ),
    (
        "LIFO", "/ˈlaɪfoʊ/", "나중에 들어온 것을 먼저 처리", CS, E,
        "Last In, First Out 의 줄임말. 스택이 동작하는 방식이다. 함수 호출이 이 순서로 "
        "쌓이고 풀리기 때문에, 가장 나중에 부른 함수가 가장 먼저 끝난다. "
        "'라이포' 로 읽는다.",
        "Function calls unwind in LIFO order.",
        "함수 호출은 LIFO 순서로 풀립니다.",
    ),
    (
        "LRU", "/ˌel ɑr ˈju/", "가장 오래 안 쓴 것부터 버리기", CS, N,
        "Least Recently Used 의 줄임말. 자리가 모자랄 때 가장 오랫동안 쓰이지 않은 항목을 "
        "먼저 내보내는 방식이다. 최근에 쓴 것은 또 쓸 가능성이 높다는 가정에 기댄다. "
        "캐시와 페이지 교체에 널리 쓰이고 정처기 계산 문제로 나온다.",
        "The cache evicts entries using an LRU policy.",
        "이 캐시는 LRU 정책으로 항목을 내보냅니다.",
    ),
    (
        "FCFS", "/ˌef si ef ˈes/", "도착한 순서대로 실행하기", CS, N,
        "First Come, First Served 의 줄임말. CPU 스케줄링에서 먼저 도착한 작업을 먼저 "
        "실행하는 가장 단순한 방식이다. 앞에 아주 긴 작업이 있으면 뒤의 짧은 작업들이 "
        "통째로 기다려야 해서 평균 대기 시간이 나빠진다.",
        "FCFS is simple but makes short jobs wait behind long ones.",
        "FCFS 는 단순하지만 짧은 작업이 긴 작업 뒤에서 기다리게 됩니다.",
    ),
    (
        "SJF", "/ˌes dʒeɪ ˈef/", "짧은 작업을 먼저 실행하기", CS, H,
        "Shortest Job First 의 줄임말. 실행 시간이 짧은 작업을 먼저 처리해 평균 대기 "
        "시간을 최소로 만드는 방식이다. 다만 각 작업이 얼마나 걸릴지 미리 알아야 하고, "
        "긴 작업은 계속 밀려 영영 실행되지 못하는 기아가 생길 수 있다.",
        "SJF minimizes average wait time but can starve long jobs.",
        "SJF 는 평균 대기 시간을 줄이지만 긴 작업이 기아 상태에 빠질 수 있습니다.",
    ),
    (
        "BFS", "/ˌbi ef ˈes/", "가까운 곳부터 넓게 훑기", CS, N,
        "Breadth-First Search 의 줄임말. 출발점에서 가까운 것부터 한 겹씩 넓혀가며 "
        "탐색한다. 간선 비용이 모두 같다면 가장 먼저 도달한 경로가 최단 경로가 된다. "
        "큐를 써서 구현한다.",
        "Use BFS if you need the shortest path in an unweighted graph.",
        "가중치 없는 그래프에서 최단 경로가 필요하면 BFS 를 쓰세요.",
    ),
    (
        "DFS", "/ˌdi ef ˈes/", "한 갈래를 끝까지 파고들기", CS, N,
        "Depth-First Search 의 줄임말. 한 방향으로 끝까지 들어갔다가 막히면 되돌아 나와 "
        "다음 갈래를 본다. 재귀나 스택으로 구현하고, 깊이가 아주 깊으면 스택이 넘칠 수 "
        "있다. 먼저 찾은 경로가 최단이라는 보장은 없다.",
        "DFS found a path, but not the shortest one.",
        "DFS 가 경로를 찾긴 했지만 최단 경로는 아닙니다.",
    ),
    (
        "AES", "/ˌeɪ i ˈes/", "열쇠 하나를 나눠 쓰는 암호화 표준", CS, H,
        "Advanced Encryption Standard 의 줄임말. 잠글 때와 열 때 같은 열쇠를 쓰는 대칭 "
        "방식으로 빠르고 널리 쓰인다. 문제는 그 열쇠를 상대에게 안전하게 전달하는 것이고, "
        "그래서 실제로는 비대칭 방식으로 열쇠를 주고받은 뒤 이걸 쓴다.",
        "The data is encrypted with AES at rest.",
        "저장된 데이터는 AES 로 암호화돼 있습니다.",
    ),
    (
        "RSA", "/ˌɑr es ˈeɪ/", "공개키와 개인키를 쓰는 암호 방식", CS, H,
        "만든 사람 셋의 이름 첫 글자를 딴 비대칭 암호 방식. 공개키로 잠근 것은 개인키로만 "
        "열리고, 그 반대로 서명도 된다. 큰 수를 소인수분해하기 어렵다는 점에 기대고 있어 "
        "대칭 방식보다 느리므로 주로 열쇠 교환과 서명에 쓴다.",
        "RSA is used for the key exchange, not for the bulk data.",
        "RSA 는 대량 데이터가 아니라 키 교환에 씁니다.",
    ),
    (
        "MD5", "/ˌem di ˈfaɪv/", "이제는 안전하지 않은 옛 해시", CS, N,
        "Message Digest Algorithm 5 의 줄임말. 예전에 널리 쓰이던 해시 방식. "
        "서로 다른 입력에서 같은 결과를 일부러 만들어낼 수 "
        "있다는 점이 밝혀져 비밀번호나 서명에 쓰면 안 된다. 파일이 전송 중 깨지지 "
        "않았는지 확인하는 정도의 용도로만 남아 있다.",
        "Do not hash passwords with MD5; use a slow password hash instead.",
        "비밀번호를 MD5 로 해싱하지 마세요. 느린 비밀번호 전용 해시를 쓰세요.",
    ),
    (
        "PKI", "/ˌpi keɪ ˈaɪ/", "공개키를 믿을 수 있게 만드는 체계", CS, H,
        "Public Key Infrastructure 의 줄임말. 공개키가 정말 그 사람의 것인지 보증하고 "
        "인증서를 발급하고 폐기하는 전체 체계다. 열쇠 자체가 아니라 그 열쇠를 "
        "믿을 근거를 만드는 구조라는 점이 핵심이다.",
        "The certificate chain is validated against our internal PKI.",
        "인증서 체인은 사내 PKI 를 기준으로 검증됩니다.",
    ),
    (
        "CA", "/ˌsi ˈeɪ/", "인증서를 발급하고 보증하는 기관", CS, N,
        "Certificate Authority 의 줄임말. 이 인증서가 진짜라고 보증해주는 기관이다. "
        "브라우저는 미리 신뢰하는 기관 목록을 갖고 있어서, 그 목록에 없는 곳이 발급한 "
        "인증서는 경고를 띄운다. 사내에서만 쓰려고 직접 기관을 만들기도 한다.",
        "The browser warns because our internal CA is not trusted by default.",
        "사내 CA 가 기본 신뢰 목록에 없어서 브라우저가 경고를 띄웁니다.",
    ),
    (
        "OOP", "/ˌoʊ oʊ ˈpi/", "객체 단위로 짜는 프로그래밍 방식", CS, N,
        "Object-Oriented Programming 의 줄임말. 데이터와 그 데이터를 다루는 동작을 "
        "한 덩어리로 묶어 다루는 방식이다. 상속을 많이 쓰는 것이 핵심이 아니라 "
        "상태를 감추고 책임을 나누는 것이 핵심이다. 정처기 기본 개념이다.",
        "This is procedural code wearing OOP clothes.",
        "이건 객체지향의 옷을 입은 절차적 코드입니다.",
    ),
    (
        "AOP", "/ˌeɪ oʊ ˈpi/", "공통 처리를 따로 떼어 끼워 넣기", CS, H,
        "Aspect-Oriented Programming 의 줄임말. 로깅이나 트랜잭션처럼 여기저기 반복되는 "
        "처리를 본래 코드에서 떼어내 한 곳에 두고 필요한 지점에 자동으로 끼워 넣는 방식이다. "
        "코드에 호출한 흔적이 없어서 편한 만큼 흐름을 따라가기 어려워진다.",
        "The transaction is applied through AOP, which is why you do not see it here.",
        "트랜잭션이 AOP 로 적용돼서 여기서는 보이지 않는 겁니다.",
    ),
    (
        "JVM", "/ˌdʒeɪ vi ˈem/", "자바 코드를 실행하는 가상 기계", CS, N,
        "Java Virtual Machine 의 줄임말. 자바 코드를 기계어가 아니라 중간 형태로 만든 뒤 "
        "이것이 각 운영체제에서 실행해준다. 한 번 만들면 어디서나 돈다는 말이 여기서 "
        "나왔다. 자바 외의 언어들도 이 위에서 돈다.",
        "Tune the JVM heap size before you blame the code.",
        "코드를 탓하기 전에 JVM 힙 크기를 조정해 보세요.",
    ),
    (
        "IDE", "/ˌaɪ di ˈi/", "편집과 실행과 디버깅을 한곳에서", CS, E,
        "Integrated Development Environment 의 줄임말. 편집기, 빌드, 디버거, 검색을 "
        "하나로 묶은 개발 도구다. 단순 편집기와의 실질적인 차이는 코드의 의미를 알아서 "
        "이름을 한 번에 바꾸거나 정의로 바로 이동할 수 있다는 점이다.",
        "The IDE can rename that symbol across the whole project safely.",
        "IDE 로 프로젝트 전체에서 그 이름을 안전하게 바꿀 수 있습니다.",
    ),
    (
        "ASCII", "/ˈæski/", "영문자를 숫자로 정한 오래된 표", CS, N,
        "American Standard Code for Information Interchange 의 줄임말. 영문자와 기호를 "
        "0에서 127까지의 숫자로 정해둔 표다. 한글은 여기 없어서 다른 인코딩이 필요했고, "
        "그 차이가 글자가 깨지는 문제의 뿌리다. '아스키' 로 읽는다.",
        "The file is plain ASCII, so Korean text will not survive.",
        "이 파일은 순수 ASCII 라 한글은 깨집니다.",
    ),
    (
        "CRC", "/ˌsi ɑr ˈsi/", "전송 중 깨졌는지 검사하는 값", CS, H,
        "Cyclic Redundancy Check 의 줄임말. 데이터로 계산한 값을 함께 보내 받는 쪽에서 "
        "다시 계산해 비교하는 방식이다. 오류를 찾아낼 뿐 고쳐주지는 않는다는 점이 "
        "오류 정정 부호와 다르다. 정처기에서 검출과 정정을 구분해 묻는다.",
        "CRC detects corruption but cannot repair it.",
        "CRC 는 손상을 검출할 뿐 복구하지는 못합니다.",
    ),
    (
        "P2P", "/ˌpi tə ˈpi/", "중앙 서버 없이 직접 주고받기", CS, N,
        "Peer to Peer 의 줄임말. 중앙 서버를 거치지 않고 참여자끼리 직접 데이터를 "
        "주고받는 구조다. 참여자가 많을수록 오히려 빨라질 수 있고 서버 비용이 들지 않지만, "
        "누가 들어오고 나가는지 통제하기 어렵다.",
        "File sharing over P2P scales with the number of peers.",
        "P2P 파일 공유는 참여자가 늘수록 잘 확장됩니다.",
    ),
    (
        "UML", "/ˌju em ˈel/", "설계를 그림으로 표기하는 표준", CS, N,
        "Unified Modeling Language 의 줄임말. 클래스 구조나 동작 흐름을 정해진 기호로 "
        "그리는 표기법이다. 모든 다이어그램을 다 그리는 것이 목적이 아니라 말로 설명하기 "
        "어려운 부분만 골라 그리는 것이 실용적이다. 정처기 실기에 나온다.",
        "Draw a UML sequence diagram for the login flow.",
        "로그인 흐름을 UML 시퀀스 다이어그램으로 그려주세요.",
    ),
    (
        "DFD", "/ˌdi ef ˈdi/", "데이터가 흘러가는 길을 그린 도표", CS, H,
        "Data Flow Diagram 의 줄임말. 데이터가 어디서 들어와 어떤 처리를 거쳐 어디에 "
        "저장되는지를 그린다. 순서를 나타내는 순서도와 달리 흐름과 저장소에 초점을 둔다. "
        "정처기 요구사항 분석 단계에서 나온다.",
        "The DFD shows where the customer data ends up.",
        "DFD 를 보면 고객 데이터가 어디에 저장되는지 알 수 있습니다.",
    ),
    (
        "SDLC", "/ˌes di el ˈsi/", "개발이 거치는 전체 단계", CS, N,
        "Software Development Life Cycle 의 줄임말. 요구 분석, 설계, 구현, 시험, 유지보수로 "
        "이어지는 전체 흐름을 가리킨다. 이 단계들을 한 번에 순서대로 밟는 방식이 폭포수 "
        "모형이고, 짧게 여러 번 도는 방식이 반복형이다. 정처기 필수 항목이다.",
        "Which SDLC model does this project follow?",
        "이 프로젝트는 어떤 개발 생명주기 모형을 따르나요?",
    ),
    (
        "WBS", "/ˌdʌblju bi ˈes/", "할 일을 잘게 쪼개 나눈 구조", CS, N,
        "Work Breakdown Structure 의 줄임말. 프로젝트 전체를 관리 가능한 크기의 작업으로 "
        "계층적으로 쪼갠 것이다. 일정과 담당자를 붙일 수 있을 만큼 잘게 나누는 것이 "
        "기준이다. 정처기 프로젝트 관리 파트에 나온다.",
        "Break the epic down in the WBS before estimating.",
        "추정하기 전에 WBS 에서 큰 작업을 잘게 나누세요.",
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
