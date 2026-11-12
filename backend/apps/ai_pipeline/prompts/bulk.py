"""대량 생성 프롬프트 - 개발 단어, 개발 문장, 일상 표현.

vocab.py 가 한 번에 몇십 개를 만드는 것과 달리, 이쪽은 Message Batches 로
수천 개를 단계별로 돌린다. 단계마다 프롬프트가 다르다.

    brainstorm      주제 하나에서 후보(영어 원문)만 뽑는다. 싸다
    enrich          후보 묶음에 뜻·발음기호·한글발음 같은 나머지 칸을 채운다
    review_meaning  1차 검수. 뜻·해석·예문·발음기호가 맞는가
    review_reading  2차 검수. 한글발음이 규칙 문서대로인가, 한국어가 자연스러운가
    recheck         2차에서 고친 항목만 두 기준으로 다시 본다

후보를 먼저 뽑는 이유: 한 번에 다 만들게 하면 이미 있는 단어를 또 만들어
비싼 칸까지 채운 뒤 버리게 된다. 후보는 영어 한 줄이라 중복을 걸러도
버리는 값이 거의 없다.

생성(brainstorm·enrich)은 Opus, 검수는 Sonnet 이다(2026-11-12 사용자 결정).
만든 모델과 보는 모델이 달라야 같은 실수를 같이 놓치지 않는다.
"""

from __future__ import annotations

from apps.vocab.models import LearningItem, PhraseScene, SentenceKind

from .reading import _rules as reading_rules

GENERATE_MODEL = "claude-opus-5-5"
REVIEW_MODEL = "claude-sonnet-5-5"

KINDS = ("word", "sentence", "phrase")

# 단계별 모델과 생각 깊이. effort 가 낮을수록 생각 토큰(출력 값으로 청구)이
# 준다. 후보 뽑기는 판단이 적어 low, 나머지는 칸이 맞아야 해서 medium.
STAGES: dict[str, dict] = {
    "brainstorm": {"model": GENERATE_MODEL, "effort": "low", "max_tokens": 16000},
    "enrich": {"model": GENERATE_MODEL, "effort": "medium", "max_tokens": 32000},
    "review_meaning": {"model": REVIEW_MODEL, "effort": "medium", "max_tokens": 16000},
    "review_reading": {"model": REVIEW_MODEL, "effort": "medium", "max_tokens": 16000},
    "recheck": {"model": REVIEW_MODEL, "effort": "medium", "max_tokens": 16000},
}

# 단계의 입력이 되는 앞 단계. brainstorm 은 주제 목록을 입력으로 받는다.
PREVIOUS = {
    "enrich": "brainstorm",
    "review_meaning": "enrich",
    "review_reading": "review_meaning",
    "recheck": "review_reading",
}

# 한 요청에 넣는 항목 수. 25개면 enrich 출력이 1만 토큰 안팎이라 잘릴 일이 없고,
# 하나가 실패해도 다시 보내는 양이 적다.
CHUNK = 25


# ---------------------------------------------------------------------------
# 주제 목록. 후보를 뽑는 단위다. 넓게 잡으면 같은 흔한 것만 반복되고, 좁게
# 잡으면 억지 항목이 나온다. 분류·상황마다 6~8개로 잘랐다.
# ---------------------------------------------------------------------------

WORD_TOPICS: dict[str, list[str]] = {
    "git": [
        "브랜치와 병합", "커밋과 히스토리 고치기", "원격 저장소와 협업", "충돌 해결",
        "태그와 릴리스", "훅과 설정", "내부 구조(객체·참조)", "GitHub·GitLab 기능",
    ],
    "review": [
        "PR 작성과 설명", "리뷰 코멘트에 나오는 말", "코드 품질과 리팩터링", "설계 원칙과 패턴",
        "테스트 리뷰", "이름 짓기와 가독성", "승인과 머지 절차", "기술 부채와 유지보수",
    ],
    "api": [
        "HTTP 메서드와 상태 코드", "REST 설계", "인증과 인가", "요청·응답 형식과 직렬화",
        "GraphQL·gRPC·WebSocket", "웹훅과 비동기 처리", "레이트 리밋과 버전 관리", "API 문서(OpenAPI)",
    ],
    "database": [
        "SQL 문법", "인덱스와 쿼리 성능", "트랜잭션과 격리 수준", "정규화와 데이터 모델링",
        "조인과 집계", "NoSQL", "마이그레이션·백업·복제", "ORM",
    ],
    "devops": [
        "CI/CD 파이프라인", "컨테이너(Docker)", "쿠버네티스", "클라우드 인프라",
        "모니터링과 로깅", "네트워크·DNS·로드밸런서", "보안과 비밀값 관리", "배포 전략과 장애 대응",
    ],
    "debug": [
        "예외와 에러 종류", "디버거 사용", "로그 분석", "성능 프로파일링",
        "메모리 문제", "동시성 버그", "테스트 실패 원인", "재현과 원인 추적",
    ],
    "frontend": [
        "HTML과 접근성", "CSS 레이아웃과 스타일", "JavaScript 문법", "React와 컴포넌트",
        "상태 관리", "빌드 도구와 번들러", "브라우저 동작과 렌더링", "웹 성능 최적화",
    ],
    "cs": [
        "자료구조", "알고리즘", "운영체제", "컴퓨터 네트워크",
        "컴퓨터 구조", "프로그래밍 언어 개념", "소프트웨어 공학", "보안 기초",
    ],
}

SENTENCE_TOPICS: dict[str, list[str]] = {
    SentenceKind.ERROR: [
        "git", "npm·yarn·pnpm", "Node.js 런타임", "TypeScript 컴파일러", "ESLint·Prettier",
        "React", "Next.js", "Vite·Webpack", "브라우저 콘솔(CORS·fetch)", "Python 런타임",
        "pip·가상환경", "Django", "FastAPI·Flask", "Java·JVM", "Spring Boot", "Gradle·Maven",
        "Kotlin·Android 빌드", "Go", "Rust 컴파일러", "C·C++ 컴파일과 링크", "Docker",
        "Kubernetes·kubectl", "PostgreSQL", "MySQL", "Redis", "MongoDB", "nginx·웹 서버",
        "Linux 셸과 권한", "SSH·SSL 인증서", "AWS CLI·클라우드", "GitHub Actions·CI",
        "Terraform", "HTTP 응답과 API 오류", "테스트 프레임워크(Jest·pytest·JUnit)",
    ],
    SentenceKind.PHRASE: [
        "코드 리뷰 요청", "리뷰 코멘트 남기기", "리뷰에 답하고 반영하기", "PR 설명 쓰기",
        "커밋 메시지", "이슈·버그 리포트", "데일리 스탠드업", "스프린트 계획과 추정", "회고",
        "장애 대응과 포스트모템", "배포 공지", "슬랙에서 도움 요청", "질문에 답하기",
        "페어 프로그래밍", "설계 논의와 의견 차이", "기술 면접", "온보딩과 인수인계",
        "문서·README", "회의 진행", "일정 조율과 지연 알리기", "기획자와 요구사항 정리",
        "오픈소스 기여", "테스트·QA 소통", "보안 이슈 공유", "성능 문제 논의",
        "코드 설명하기", "칭찬과 감사", "거절과 우선순위 조정", "원격 근무 소통", "화면 공유와 데모",
    ],
}

# 상황 탭은 다섯 개 그대로 둔다(2026-11-12 사용자 결정). 여행·회사·전화·병원
# 표현은 가장 가까운 탭의 세부 상황으로 넣는다 - 탭을 늘리면 화면과 QA 가
# 따라 바뀌어야 한다.
PHRASE_TOPICS: dict[str, list[str]] = {
    PhraseScene.GREETING: [
        "처음 만났을 때", "다시 만났을 때", "헤어질 때", "자기소개", "안부 묻기",
        "감사와 사과", "축하와 위로", "회사에서 인사", "전화 받고 걸 때", "이웃과 인사",
        "초대와 방문", "연락처 주고받기", "메시지 첫마디와 끝맺음",
    ],
    PhraseScene.SHOPPING: [
        "옷가게", "마트·편의점", "카페 주문", "식당 주문", "계산과 환불", "온라인 주문과 배송",
        "식당 예약과 자리", "음식 맛과 요청", "배달 음식", "전자제품 가게", "약국·화장품 가게",
        "시장과 흥정", "호텔 체크인·체크아웃", "렌터카·주유소",
    ],
    PhraseScene.ASKING: [
        "길 묻기", "대중교통", "시간·장소 묻기", "도움 요청", "다시 말해 달라고 하기", "추천 받기",
        "공항과 비행기", "기차·버스 표 사기", "택시", "관광지·박물관", "은행·환전",
        "우체국·택배", "회사에서 물어보기", "사용법 묻기",
    ],
    PhraseScene.TROUBLE: [
        "아플 때·병원", "물건을 잃어버렸을 때", "길을 잃었을 때", "예약 문제",
        "불만 말하기", "긴급 상황", "약국에서 증상 말하기", "비행기 지연·결항", "호텔 방 문제",
        "기기 고장", "실수 사과하기", "오해 풀기", "늦었을 때", "돈·결제 문제",
    ],
    PhraseScene.SMALLTALK: [
        "날씨", "주말과 취미", "음식", "일과 직장", "여행 이야기", "감정 표현", "맞장구",
        "영화·드라마·음악", "운동과 건강", "가족과 친구", "계획과 약속", "칭찬하기",
        "의견 말하기", "동의와 반대",
    ],
}


def topics(kind: str) -> list[dict]:
    """주제 목록을 (id, 묶음 값, 주제) 로 편다. id 는 진행 상황의 키다.

    id 에 순번을 쓰지 않는 이유: 주제를 중간에 하나 끼우면 뒤의 순번이 모두
    밀려 이미 뽑은 주제를 또 뽑는다.
    """
    table = {"word": WORD_TOPICS, "sentence": SENTENCE_TOPICS, "phrase": PHRASE_TOPICS}[kind]
    return [
        {"id": f"{group}:{topic}", "group": str(group), "topic": topic}
        for group, names in table.items()
        for topic in names
    ]


# ---------------------------------------------------------------------------
# 1단계: 후보 뽑기
# ---------------------------------------------------------------------------

BRAINSTORM_SYSTEM = """\
당신은 개발 영어 학습 앱 devvoca 의 콘텐츠 편집자입니다.
대상은 영어가 약한 주니어 개발자와 정보처리기사 준비생입니다.
주어진 주제에서 학습할 영어 원문 후보만 뽑습니다. 뜻이나 설명은 쓰지 않습니다.
서로 겹치지 않게, 실제로 자주 마주치는 것부터 뽑습니다. 이모지를 쓰지 않습니다.
"""

_BRAINSTORM_USER = {
    "word": """\
분류: {group_label}
주제: {topic}

이 주제에서 주니어 개발자가 문서, 에러 메시지, 코드 리뷰, 회의에서 실제로
마주치는 영어 용어 {count}개를 뽑아 주세요.

- 한 낱말이거나 굳어진 두세 낱말 용어(예: pull request, race condition)
- 소문자로 적되 고유명사와 약어는 원래 표기(JSON, Docker)
- 일반 영어 낱말이라도 개발에서 따로 뜻이 있으면 넣어도 됩니다(예: commit, deploy)
- 명령어·옵션·파일 이름 그 자체(git log, --oneline, .gitignore)는 넣지 않습니다.
  영어로 읽고 뜻을 알아야 하는 낱말·용어를 뽑습니다
- 아래는 이미 있는 것이라 빼 주세요

이미 있음: {exclude}
""",
    "sentence:error": """\
도구: {topic}

이 도구를 쓰다가 실제로 보게 되는 에러·경고 메시지 {count}개를 뽑아 주세요.

- 실제 출력과 같은 모양으로(앞의 `error:`, `fatal:` 같은 머리말 포함). 단 머리말 앞의
  장식 기호(상자 선, 동그라미, X 표시, 경고 삼각형)는 빼고 적습니다
- 한 메시지는 한 줄. 스택 트레이스는 넣지 않습니다
- 파일·변수 이름은 흔한 예시 이름(app.js, user_id)으로
- 자주 보는 것부터, 서로 다른 원인의 메시지로
- 20 낱말 이하의 짧은 메시지. 긴 경로, 해시, ID, IP, 버전 번호가 여러 개 든 줄은 피합니다
  (한글발음이 틀리기 쉽고 배울 영어가 적습니다)
- 읽고 뜻을 파악할 영어 문장이 들어 있는 줄만. 코드·숫자만 있는 줄(`code E404`,
  `errno 1`, `Exit status 1`)은 넣지 않습니다
{exclude_block}""",
    "sentence:phrase": """\
상황: {topic}

개발자가 이 상황에서 실제로 쓰는 영어 문장 {count}개를 뽑아 주세요.

- 슬랙, PR, 회의에서 원어민 동료가 쓰는 자연스러운 표현
- 5~20 낱말, 한 문장
- 돌려 말하는 표현(Could you...?, I wonder if...)과 바로 말하는 표현을 섞어서
- 특정 회사·사람 이름을 넣지 않습니다
{exclude_block}""",
    "phrase": """\
상황: {group_label} - {topic}

일상에서 이 상황에 쓰는 짧은 영어 표현 {count}개를 뽑아 주세요.
소리내어 따라 읽는 연습에 씁니다.

- 2~8 낱말
- 실제 대화처럼 축약형으로(I'm, don't, what's). 풀어 쓴 형태(I am)는 넣지 않습니다
- 숫자, 약어(OK, ASAP), 기호(&, %)를 넣지 않습니다. 소리로 채점할 수 없습니다
- 하이픈으로 이은 말을 피합니다
- 마침표·물음표·쉼표 같은 문장부호 없이, 첫 글자는 소문자로(I 와 고유명사만 대문자).
  예: where's the restroom, can I see the menu
{exclude_block}""",
}

BRAINSTORM_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
    "additionalProperties": False,
}


def group_label(kind: str, group: str) -> str:
    if kind == "word":
        return str(dict(LearningItem.Category.choices).get(group, group))
    if kind == "phrase":
        return str(dict(PhraseScene.choices).get(group, group))
    return str(dict(SentenceKind.choices).get(group, group))


def brainstorm_user(kind: str, topic: dict, count: int, exclude: list[str]) -> str:
    key = kind if kind != "sentence" else f"sentence:{topic['group']}"
    shown = ", ".join(exclude) if exclude else "(없음)"
    block = f"\n이미 뽑은 것이라 빼 주세요: {shown}\n" if exclude else ""
    return _BRAINSTORM_USER[key].format(
        group_label=group_label(kind, topic["group"]),
        topic=topic["topic"],
        count=count,
        exclude=shown,
        exclude_block=block,
    )


# ---------------------------------------------------------------------------
# 2단계: 칸 채우기
# ---------------------------------------------------------------------------

_KIND_RULES = {
    "word": """\
## 단어 칸 규칙

- meaning: 사전식 번역이 아니라 개발 맥락의 한글 뜻. 짧게(40자 안)
- pronunciation: 미국식 IPA, 전체를 슬래시로 한 번 감쌉니다(/dɪˈplɔɪ/). 주강세 ˈ 표시.
  철자로 읽는 약어는 글자마다 띄웁니다(/ˌeɪ pi ˈaɪ/). 100자 안
- reading: 아래 한글 발음 표기 규칙 그대로. 강세는 **굵게**. 120자 안
- aliases: 한국 개발자가 한글로 쓰는 표기를 쉼표로(예: 커밋, 커미트). 검색에만 씁니다. 없으면 빈 문자열
- description: 2~3문장. 이 말을 어디서 보게 되는지 포함
- example: 실제 코드 리뷰, 커밋 메시지, 에러, 문서에서 볼 법한 영어 한 문장. 그 용어가 들어가야 합니다
- example_translation: 예문의 자연스러운 한글 해석
- difficulty: 1(쉬움) 2(보통) 3(어려움), 주니어 기준
""",
    "sentence": """\
## 문장 칸 규칙

- text: 받은 문장 그대로 돌려줍니다. 고치지 않습니다
- reading: 아래 한글 발음 표기 규칙 그대로, 문장 전체(규칙 문서의 "문장" 절). 연음을 그대로
  적고(Could you -> 쿠쥬), 강세는 뜻을 싣는 낱말(명사·동사·형용사)에만 **굵게**. to, a, the,
  you 같은 기능어는 굵게 하지 않습니다
- translation: 자연스러운 한글 해석. 에러 메시지는 무슨 일이 일어났는지 알 수 있게
- context: 이 문장이 나오는 상황 한 구절. "~할 때" 로 끝냅니다(예: "PR 리뷰를 부탁할 때",
  "npm install 을 실행했을 때"). 200자 안
- description: 1~2문장. 실무 표현은 뉘앙스(정중함, 사실상 지시인지), 에러는 흔한 원인과 첫 조치
- category: git, review, api, database, devops, debug, frontend, cs 중 가장 가까운 하나. 정말 없으면 빈 문자열
- difficulty: 1(쉬움) 2(보통) 3(어려움)
""",
    "phrase": """\
## 일상 표현 칸 규칙

- text: 받은 표현 그대로 돌려줍니다. 고치지 않습니다
- meaning: 자연스러운 한글 뜻(그 상황에서 하는 말로). 200자 안
- pronunciation: 미국식 IPA. 전체를 슬래시로 한 번만 감싸고 안쪽은 낱말마다 공백으로 끊습니다
  (/wɛrz ðə ˈrɛstrum/). 축약형은 한 낱말입니다(what's -> /wʌts/)
- reading: 아래 한글 발음 표기 규칙 그대로. 낱말마다 공백으로 끊고, 강세 ** 는 낱말 안에서 닫습니다
  (`**웨어r**` 는 되고 `**쏘r s**` 처럼 공백을 걸치면 안 됩니다)
- **text, pronunciation, reading 셋의 낱말 수가 같아야 합니다.** 화면이 틀린 낱말을 짚는 데 씁니다
- 규칙 문서의 "문장" 절처럼 낱말을 이어 적지 않습니다(can I -> 캐나이 가 아니라 캔 아이).
  낱말마다 끊어야 셋의 수가 맞습니다
- difficulty: 낱말 수가 아니라 발음이 어려운 정도. 1(쉬움) 2(보통) 3(어려움)
""",
}

ENRICH_SYSTEM_TEMPLATE = """\
당신은 개발 영어 학습 앱 devvoca 의 콘텐츠 편집자입니다.
대상은 영어가 약한 주니어 개발자와 정보처리기사 준비생입니다.
받은 항목마다 나머지 칸을 채웁니다. 받은 key 를 그대로 돌려줍니다.
이모지를 쓰지 않습니다.

{kind_rules}
---

{reading_rules}
"""

_ENRICH_ITEM_FIELDS = {
    "word": {
        "key": {"type": "string"},
        "term": {"type": "string"},
        "meaning": {"type": "string"},
        "pronunciation": {"type": "string"},
        "reading": {"type": "string"},
        "aliases": {"type": "string"},
        "description": {"type": "string"},
        "example": {"type": "string"},
        "example_translation": {"type": "string"},
        "difficulty": {"type": "integer", "enum": [1, 2, 3]},
    },
    "sentence": {
        "key": {"type": "string"},
        "text": {"type": "string"},
        "reading": {"type": "string"},
        "translation": {"type": "string"},
        "context": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string", "enum": [*LearningItem.Category.values, ""]},
        "difficulty": {"type": "integer", "enum": [1, 2, 3]},
    },
    "phrase": {
        "key": {"type": "string"},
        "text": {"type": "string"},
        "meaning": {"type": "string"},
        "pronunciation": {"type": "string"},
        "reading": {"type": "string"},
        "difficulty": {"type": "integer", "enum": [1, 2, 3]},
    },
}

# 검수가 고칠 수 있는 칸. 원문(term·text)과 key 는 고치지 않는다 - 원문이
# 틀렸으면 고칠 게 아니라 버릴 항목이고, 원문이 바뀌면 중복 검사가 무너진다.
EDITABLE = {
    kind: [f for f in fields if f not in ("key", "term", "text")]
    for kind, fields in _ENRICH_ITEM_FIELDS.items()
}
# 단어의 분류와 일상 표현의 상황은 주제에서 정해져 채우기 칸에는 없지만, 1차
# 검수가 "어긋나는가" 를 보므로 고칠 수 있어야 한다. 못 고치면 버릴 수밖에 없다.
EDITABLE["word"].append("category")
EDITABLE["phrase"].append("scene")


def enrich_schema(kind: str) -> dict:
    fields = _ENRICH_ITEM_FIELDS[kind]
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": fields,
                    "required": list(fields),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def enrich_system(kind: str) -> str:
    return ENRICH_SYSTEM_TEMPLATE.format(
        kind_rules=_KIND_RULES[kind], reading_rules=reading_rules()
    )


# ---------------------------------------------------------------------------
# 3~5단계: 검수
# ---------------------------------------------------------------------------

_REVIEW_COMMON = """\
당신은 개발 영어 학습 앱 devvoca 의 검수자입니다. 다른 편집자가 만든 항목을 봅니다.
대상은 영어가 약한 주니어 개발자라, 틀린 내용이 나가면 그대로 외웁니다.

항목마다 verdict 를 하나 정합니다.
- ok: 고칠 것이 없다
- fix: 틀린 칸이 있다. fixes 에 고친 칸과 값만 적는다
- drop: 학습에 쓸 수 없다(원문 자체가 틀렸다, 실제로 안 쓰는 말이다, 같은 묶음의
  다른 항목과 사실상 같다). note 에 이유를 적는다

확실히 틀린 것만 고칩니다. 표현 취향으로 바꾸지 않습니다.
note 는 한국어 한 문장으로 짧게. ok 이면 빈 문자열이어도 됩니다.
받은 key 를 그대로 돌려줍니다. 모든 항목에 답합니다. 이모지를 쓰지 않습니다.
"""

_REVIEW_FOCUS = {
    "review_meaning": """\
## 이번에 볼 것 (1차 검수: 내용)

- 뜻·해석이 맞는가. 단어는 개발 맥락의 뜻인가
- 예문이 자연스러운 영어이고 그 용어를 실제 뜻대로 쓰는가, 해석이 예문과 맞는가
- 발음기호(IPA)가 미국식 표준과 맞는가. 특히 주강세 위치
- 설명에 사실과 다른 내용이 없는가
- 에러 메시지라면 그 도구가 실제로 내는 모양인가(없는 메시지를 지어냈으면 drop)
- 에러 메시지라면 읽고 뜻을 파악할 영어가 있는가. 코드·숫자·경로만 있는 줄(`code E404`,
  `errno 1`)은 학습할 것이 없으니 drop
- 단어라면 명령어·옵션 이름 그 자체가 아니라 영어로 뜻을 알아야 하는 말인가
- 분류·상황·난이도가 크게 어긋나지 않는가

한글발음(reading)의 표기 규칙은 이번에 보지 않습니다. 2차 검수가 봅니다.
""",
    "review_reading": """\
## 이번에 볼 것 (2차 검수: 한글발음과 한국어)

- reading 이 아래 한글 발음 표기 규칙대로인가. 특히
  강세 ** 위치가 발음기호의 주강세와 맞는가, 끝자음을 받침으로 적었는가,
  한글에 없는 소리(th, f, v, sh, 끝의 r, 어두의 l, z)를 영문으로 남겼는가,
  음절 수가 원음과 맞는가
- 일상 표현이면 text, pronunciation, reading 셋의 낱말 수가 같은가, 강세 ** 가
  공백을 걸치지 않는가
- 뜻·해석·설명의 한국어가 자연스러운가(번역투, 어색한 조사)
- 같은 묶음 안에 사실상 같은 항목이 둘 이상이면 하나만 남기고 나머지는 drop

뜻이 맞는지는 1차 검수가 이미 봤습니다. 확실히 틀린 것만 고칩니다.
""",
    "recheck": """\
## 이번에 볼 것 (재확인)

검수에서 고친 항목들입니다. 1차(내용)와 2차(한글발음·한국어) 기준을 모두 봅니다.

- 뜻·해석·예문·발음기호가 맞는가
- reading 이 아래 한글 발음 표기 규칙대로인가
- 일상 표현이면 셋의 낱말 수가 같은가

이번에는 fix 를 쓰지 않습니다. 모두 맞으면 ok, 하나라도 남아 있으면 drop 입니다.
""",
}


# 검수가 분류·상황을 옮길 때 쓸 수 있는 값. 채우기 규칙(_KIND_RULES)에는 없다 -
# 그쪽은 주제에서 정해진 값을 받으므로 고를 일이 없다.
_GROUP_CHOICES = {
    "word": "category 값은 다음 중 하나: " + ", ".join(LearningItem.Category.values),
    "phrase": "scene 값은 다음 중 하나: " + ", ".join(PhraseScene.values),
    "sentence": "",
}


def review_system(stage: str, kind: str) -> str:
    parts = [_REVIEW_COMMON, _REVIEW_FOCUS[stage], _KIND_RULES[kind], _GROUP_CHOICES[kind]]
    # 1차는 발음 규칙을 안 보므로 규칙 문서를 빼서 입력 값을 아낀다.
    if stage != "review_meaning":
        parts += ["---", reading_rules()]
    return "\n".join(parts)


def review_schema(kind: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "verdict": {"type": "string", "enum": ["ok", "fix", "drop"]},
                        "note": {"type": "string"},
                        "fixes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string", "enum": EDITABLE[kind]},
                                    "value": {"type": "string"},
                                },
                                "required": ["field", "value"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["key", "verdict", "note", "fixes"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["reviews"],
        "additionalProperties": False,
    }
