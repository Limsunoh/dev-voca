# devvoca 단어 데이터 작성 요청

아래 명세대로 **개발 영어 단어 데이터**를 만들어 주세요. 코드는 필요 없고 데이터만 있으면 됩니다.

---

## 서비스 소개

**devvoca** 는 개발할 때 마주치는 영어를 익히는 학습 서비스입니다.

**타겟**
- 1순위: 영어가 약한 주니어 / 예비 개발자
- 2순위: 정보처리기사(정처기) 준비생

**목적**: 개발 영어와 에러 메시지에 대한 공포를 없애는 것. 단어를 외우게 하는 게 아니라 "아, 이런 뜻이었구나" 하고 넘어가게 만드는 것이 목표입니다.

---

## 출력 형식

파이썬 튜플 리스트로 주세요. 각 항목은 **8개 필드**입니다.

```python
(
    "term",                    # 영어 단어 (소문자, 최대 100자)
    "/ˈprəʊnʌnsɪeɪʃn/",        # 발음기호 (IPA, 슬래시 포함, 최대 100자)
    "한글 뜻",                  # 짧은 뜻 (최대 200자, 실제로는 10~20자 권장)
    CATEGORY,                  # 아래 분류 상수 중 하나
    DIFFICULTY,                # E / N / H
    "설명",                     # 2~4문장, 150자 내외. 가장 중요합니다 (아래 참고)
    "English example sentence.",   # 실무에서 실제로 쓰이는 영어 예문
    "예문 한글 해석",
),
```

### 발음기호 규칙

**IPA(국제음성기호)로, 영국식이 아니라 미국식 발음**을 기준으로 주세요. 개발 현장에서 쓰는 발음이 미국식에 가깝습니다.

- 슬래시로 감쌉니다: `/kəˈmɪt/`
- 강세 표시를 반드시 넣습니다: `ˈ`(1강세), `ˌ`(2강세)
- 두 단어 이상이면 띄어서: `edge case` → `/ˈedʒ ˌkeɪs/`
- **장음 기호 `ː` 를 쓰지 마세요.** 미국식에는 음소적 장음이 없습니다.
  `/skwɑːʃ/` 가 아니라 `/skwɑʃ/`, `/ˌriːˈbeɪs/` 가 아니라 `/ˌriˈbeɪs/`.
  r 소리도 `ɜr`, `ər`, `ɑr` 로 씁니다(`ɜːr` 은 영국식과 미국식을 섞은 표기).
- **음절 자음에 `ə` 를 넣어주세요.** `/ˈneɪʃn/` 보다 `/ˈneɪʃən/`,
  `/ˈθrɑtl/` 보다 `/ˈθrɑtəl/` 이 읽기 쉽습니다. 타겟이 IPA 를 처음 봅니다.
- **두 단어 이상이면 주강세는 하나만.** 앞 단어에 `ˈ`, 뒤 단어에 `ˌ` 를 씁니다.
  예: `/ˈedʒ ˌkeɪs/`, `/ˈstæk ˌtreɪs/`. 양쪽 다 `ˈ` 를 주지 마세요.
- **병기 금지.** `"/ˈtuːpl/ 또는 /ˈtʌpl/"` 처럼 두 개를 적으면 화면에 "또는" 이
  그대로 나갑니다. 가장 널리 쓰이는 하나만 적고, 발음이 갈린다는 사실은
  설명 필드에 문장으로 적으세요.
- **확신이 없으면 빈 문자열 `""`.** 개발자만 쓰는 말이라 사전에 없거나 현장
  발음이 갈리는데 어느 쪽이 우세한지 모르겠으면 비웁니다. 틀린 발음을
  가르치는 것보다 없는 편이 낫습니다. 화면은 그 자리를 그냥 비웁니다.

**IPA 를 못 읽는 사람이 이 서비스의 타겟입니다.** 그래서 철자와 발음이
어긋나는 단어는 **설명 필드 마지막 문장에 한글로 함정을 적어주세요.** 선택이
아니라 의무입니다. `/kæʃ/` 를 읽을 수 있는 주니어는 많지 않습니다.

```
"...(설명) 발음은 '캐시'다. cash 와 똑같이 읽고, '캐치'가 아니다."
```

**발음이 함정인 단어는 설명에도 적어주세요.** 이 서비스 타겟이 영어가 약한 사람이라, 철자와 발음이 어긋나는 단어는 그 자체가 학습 포인트입니다.

아래는 함정의 예시입니다(출력 형식이 아니라 어떤 단어를 짚어야 하는지의 예).

| 단어 | 발음 | 함정 |
|---|---|---|
| `cache` | `/kæʃ/` | "캐시"지 "캐치"가 아니다 |
| `queue` | `/kjuː/` | "큐" 한 음절. 뒤 4글자는 안 읽는다 |
| `null` | `/nʌl/` | "널"이지 "눌"이 아니다 |
| `tuple` | `/ˈtuːpl/` | "투플". 미국에서 "터플"로도 읽지만 하나만 적는다 |
| `schema` | `/ˈskiːmə/` | "스키마". "셰마"가 아니다 |
| `suite` | `/swiːt/` | "스위트". "수트"가 아니다 |

### 분류 상수

| 상수 | 값 | 범위 |
|---|---|---|
| `GIT` | git | 버전 관리 |
| `REVIEW` | review | 코드 리뷰, 협업, 온보딩 |
| `API` | api | API, 네트워크, HTTP |
| `DB` | database | 데이터베이스 |
| `OPS` | devops | 배포, 운영, 인프라 |
| `DEBUG` | debug | 디버깅, 테스트, 에러 |
| `FRONT` | frontend | **신규** 프론트엔드 |
| `CS` | cs | **신규** CS 기초 / 정처기 |

`FRONT` 와 `CS` 는 새로 추가할 분류입니다. 화면 라벨은 기존 규칙(한글 병기)에
맞춰 이렇게 쓸 예정이니 참고만 하세요.

```
FRONT = "frontend", "프론트엔드(Frontend)"
CS    = "cs",       "CS 기초(Computer Science)"
```

### term 표기 규칙

- 일반 단어는 소문자: `commit`, `edge case`
- **고유명사·약어는 관례 표기를 따릅니다**: `TCP/IP`, `DNS`, `XSS`,
  `SQL injection`, `REST`, `JSON`. 이걸 소문자로 쓰면 안 됩니다.
- **같은 단어를 두 분류에 중복해서 주지 마세요.** `term` 이 유니크라
  나중 것이 앞의 것을 덮어씁니다. `deadlock` 은 DB 와 CS 양쪽에 어울리는데,
  더 맞는 쪽 하나에만 넣으세요. (`queue`, `cache`, `index` 도 마찬가지)

### 난이도 상수

- `E` (쉬움) — 신입도 아는 단어. commit, deploy, error
- `N` (보통) — 1~2년차가 아는 단어. idempotent 는 아니고 pagination 정도
- `H` (어려움) — 개념 자체가 어렵거나 자주 오해받는 것. idempotent, race condition

---

## 설명 필드가 핵심입니다

**단순 번역 반복은 쓸모가 없습니다.** 사전에 있는 내용을 다시 쓰지 마세요.

각 단어의 **함정**을 짚어야 합니다:
- 초보가 흔히 오해하는 지점
- 비슷한 단어와의 실제 차이
- 실무에서 이걸 몰라서 시간을 날리는 상황

### 좋은 예 (실제 반영된 것들)

```python
(
    "idempotent", "/aɪˈdempətənt/", "여러 번 해도 상태가 같은", API, H,
    "같은 요청을 두 번 보내도 서버에 남는 결과가 한 번 보낸 것과 같은 성질. "
    "응답까지 같다는 뜻은 아니다 - 두 번째 삭제 요청이 404 를 돌려줘도 "
    "이미 지워졌다는 점에서는 멱등하다. 재시도가 안전해진다.",
    "PUT should be idempotent, but POST usually is not.",
    "PUT 은 멱등해야 하지만 POST 는 보통 그렇지 않습니다.",
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
    "edge case", "/ˈedʒ ˌkeɪs/", "경계에 놓인 예외적 경우", REVIEW, N,
    "정상 흐름에서 벗어난 예외적 상황. 빈 목록, 0, 음수, 아주 긴 입력처럼 "
    "값의 경계에 놓인 경우들이다. 드물어서가 아니라 경계여서 놓치기 쉽다.",
    "The function works, but it fails on this edge case.",
    "함수는 동작하지만 이 예외 상황에서 실패합니다.",
),
```

발음이 함정인 단어는 이렇게:

```python
(
    "cache", "/kæʃ/", "자주 쓰는 것을 가까이 두기", API, N,
    "느린 곳에서 가져온 것을 빠른 곳에 잠깐 보관해두고 다음부터 그걸 쓰는 것. "
    "원본이 바뀌었는데 캐시가 남아 있으면 옛 값이 계속 나온다 - 그래서 "
    "언제 버릴지 정하는 게 캐시의 절반이다. "
    "발음은 '캐시'다. cash 와 똑같이 읽고, '캐치'가 아니다.",
    "Clear the cache and try again.",
    "캐시를 지우고 다시 시도해보세요.",
),
```

### 나쁜 예

```python
# 사전 정의만 반복 - 함정이 없다
("cache", "/kæʃ/", "캐시", API, N, "자주 쓰는 데이터를 임시로 저장해두는 것.", ...)

# 이미 알아야 이해되는 순환 설명
("mutex", "/ˈmjuːteks/", "뮤텍스", CS, H, "상호 배제를 위한 동기화 객체.", ...)

# 예문이 교과서 냄새
("deploy", "/dɪˈplɔɪ/", "배포하다", OPS, E, "...", "I deploy the code.", "나는 코드를 배포한다.")
```

---

## 반드시 지킬 것

**1. 틀린 내용을 쓰지 마세요.** 이게 가장 중요합니다.

실제로 있었던 사고: `revert` 설명에 "기록을 지우지 않아 reset 과 다르다" 라고 썼는데 **틀렸습니다**. `git reset` 도 커밋을 지우지 않습니다(reflog 에 남습니다). 실제 차이는 히스토리를 다시 쓰느냐이고, 그래서 공유 브랜치에서 reset 이 위험한 것입니다. 리뷰 세 번째에야 걸렸습니다.

확신이 없으면 그 단어를 빼세요. 그럴듯하게 틀린 것보다 없는 게 낫습니다.

**2. 한글 뜻이 서로 겹치면 안 됩니다.**

`revert`("되돌리다") 와 `rollback`("되돌리기") 이 사실상 같은 뜻이라 구별이 안 됐던 적이 있습니다. 지금은 "취소하는 커밋을 만들다" / "작업 전체를 무르다" 로 갈랐습니다.

**3. 예문은 실무 문장이어야 합니다.**

이슈 트래커, PR 코멘트, 문서, 에러 메시지에서 그대로 나올 법한 문장. "I deploy the code" 같은 교과서 문장은 안 됩니다.

**4. 이모지를 쓰지 마세요.** 설명·예문 어디에도 넣지 마세요.

**5. 이미 있는 단어는 빼세요.** 아래 31개는 이미 들어가 있습니다.

```
boilerplate, commit, constraint, deploy, deprecated, downtime, edge case,
endpoint, environment variable, fallback, idempotent, index, merge,
migration, pagination, payload, query, race condition, rebase, refactor,
regression, reproduce, revert, rollback, rollout, serialize, squash,
stack trace, stash, throttle, trade-off
```

---

## 요청 수량

**분류별로 최소 40~50개씩, 총 350개 이상**을 목표로 해주세요. 더 많으면 더 좋습니다.

| 분류 | 지금 | 목표 |
|---|---|---|
| `GIT` | 6 | 40+ |
| `REVIEW` | 5 | 40+ (협업·온보딩 용어 포함) |
| `API` | 6 | 40+ |
| `DB` | 5 | 40+ |
| `OPS` | 5 | 40+ |
| `DEBUG` | 4 | 40+ |
| `FRONT` | 0 | 40+ (신규) |
| `CS` | 0 | 40+ (신규, 정처기 비중 높게) |

한 번에 다 못 주면 분류별로 나눠서 여러 번 줘도 됩니다. **양보다 정확성이 우선**이니, 확신 없는 항목은 넣지 마세요.

### 분류별 참고

**GIT** — 브랜치 전략(cherry-pick, bisect, worktree), 원격(upstream, fetch vs pull), 협업(fork, submodule)

**REVIEW** — 코드 품질(coupling, cohesion, technical debt), 협업(standup, sprint, backlog, retrospective, on-call, blameless postmortem), 리뷰 관행(nit, LGTM, blocking comment)

**API** — HTTP(status code, header, cookie, CORS), 인증(token, OAuth, JWT, session), 설계(REST, GraphQL, versioning, rate limit, webhook)

**DB** — 관계(foreign key, join, normalization), 성능(N+1, explain, connection pool), 트랜잭션(isolation level, deadlock, ACID), NoSQL 기초

**OPS** — 컨테이너(image, container, orchestration), CI/CD(pipeline, artifact, staging), 관측(metric, tracing, alert, SLA), 인프라(load balancer, reverse proxy, CDN)

**DEBUG** — 테스트(unit test, mock, fixture, coverage, flaky), 진단(breakpoint, profiling, memory leak), 에러 유형(null pointer, off-by-one, race condition)

**FRONT** — 컴포넌트(props, state, lifecycle), 렌더링(SSR, CSR, hydration, virtual DOM), 빌드(bundle, tree shaking, minify, source map), 브라우저(DOM, event bubbling, reflow)

**CS** — 정처기 빈출 위주. 자료구조(stack, queue, hash table, binary tree), 알고리즘(recursion, greedy, dynamic programming, time complexity), OS(process vs thread, deadlock, scheduling, virtual memory), 네트워크(TCP/IP, DNS, subnet, port), 보안(encryption, hashing, SQL injection, XSS)

---

## 출력 예시

이런 형태로 주시면 그대로 쓸 수 있습니다.

```python
# ---------- 프론트엔드 ----------
(
    "hydration", "/haɪˈdreɪʃn/", "서버가 그린 화면에 동작을 붙이기", FRONT, H,
    "서버에서 만든 HTML 을 브라우저가 받은 뒤, 거기에 이벤트 핸들러를 "
    "연결해 살아 움직이게 만드는 과정. 화면은 이미 보이는데 버튼이 안 눌리는 "
    "짧은 순간이 이것 때문이다. 서버와 클라이언트가 그린 결과가 다르면 "
    "hydration mismatch 에러가 난다.",
    "The page renders but stays unresponsive until hydration finishes.",
    "페이지는 보이지만 하이드레이션이 끝날 때까지 반응하지 않습니다.",
),
```

---

## 참고: 이 데이터가 들어가는 곳

`backend/apps/vocab/management/commands/seed_words.py` 의 `WORDS` 리스트입니다.
제가 받아서 검수한 뒤 넣을 것이므로, 파이썬 문법이 정확할 필요는 없습니다.
다만 위 8개 필드 순서는 지켜주세요.
