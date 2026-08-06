# devvoca 문장 데이터 작성 요청

아래 명세대로 **개발 영어 문장 데이터**를 만들어 주세요. 코드는 필요 없고 데이터만 있으면 됩니다.

---

## 서비스 소개

**devvoca** 는 개발할 때 마주치는 영어를 익히는 학습 서비스입니다.

**타겟**
- 1순위: 영어가 약한 주니어 / 예비 개발자
- 2순위: 정보처리기사(정처기) 준비생

**목적**: 개발 영어와 에러 메시지에 대한 공포를 없애는 것. 단어를 다 외워도 문장이 안 읽히는 지점이 따로 있습니다. 리뷰 코멘트의 돌려 말하는 표현, 에러 메시지의 관용구 같은 것들.

단어는 이미 566개가 들어가 있고, 이번에 채울 것은 문장입니다.

---

## 출력 형식

파이썬 튜플 리스트로 주세요. 각 항목은 **8개 필드**입니다.

```python
(
    "review-rebase-request",   # slug - 아래 규칙 참고
    "Could you rebase this onto main before merging?",   # 영어 문장
    "병합 전에 main 위로 리베이스해 주시겠어요?",         # 한글 해석
    PHRASE,                    # 종류: PHRASE 또는 ERROR
    GIT,                       # 분류 상수
    N,                         # 난이도: E / N / H
    "PR 리뷰 코멘트",           # 어디서 나오는 문장인지 (최대 200자)
    "설명",                     # 2~4문장, 150자 내외. 가장 중요합니다
),
```

### slug 규칙

시드가 "이미 넣은 항목" 을 찾는 키입니다. 문장 본문(`text`)을 키로 쓰지 않는 이유는, 같은 문장이 다른 상황에서 나오는 것을 모델이 일부러 허용하기 때문입니다.

- 영어 소문자와 하이픈만. 예: `review-rebase-request`, `git-detached-head`
- **분야 접두사를 붙입니다**: `review-`, `git-`, `api-`, `db-`, `ops-`, `py-`, `js-`, `issue-`, `cs-`
- 최대 100자, 서로 겹치면 안 됩니다
- 한 번 정한 slug 는 바꾸지 않는다는 전제로 씁니다

### 종류 (kind)

| 상수 | 값 | 무엇 |
|---|---|---|
| `PHRASE` | phrase | 사람이 쓰는 실무 표현 - 리뷰 코멘트, 이슈, 슬랙, 문서 |
| `ERROR` | error | 터미널·콘솔에 찍히는 에러 메시지 원문 |

### 분류 상수

| 상수 | 값 | 범위 |
|---|---|---|
| `GIT` | git | 버전 관리 |
| `REVIEW` | review | 코드 리뷰, 협업, 온보딩 |
| `API` | api | API, 네트워크, HTTP |
| `DB` | database | 데이터베이스 |
| `OPS` | devops | 배포, 운영, 인프라 |
| `DEBUG` | debug | 디버깅, 테스트, 에러 |
| `FRONT` | frontend | 프론트엔드 |
| `CS` | cs | CS 기초 / 정처기 |

`FRONT` 와 `CS` 는 단어에는 이미 있고 문장에는 아직 없는 분류입니다. 채워주세요.

### 난이도

- `E` — 문장 구조가 단순하고 단어도 쉬움. `Port 3000 is already in use`
- `N` — 관용 표현이 하나쯤 섞임. `LGTM, but leaving a few nits.`
- `H` — 돌려 말하거나 배경 지식이 필요함. `fatal: refusing to merge unrelated histories`

---

## 설명 필드가 핵심입니다

**해석을 다시 풀어 쓰는 것은 쓸모가 없습니다.** 이미 한글 해석 필드가 있습니다.

설명에는 **그 문장의 함정**을 적어야 합니다.

### PHRASE 라면

- 문자 그대로가 아닌 뜻. 영어권 개발 문화에서 이 문장이 실제로 무엇을 요구하는지
- 답할 때 주의할 점
- 비슷한 표현과의 온도 차이

### ERROR 라면

- 이 에러가 실제로 무엇을 말하는지 (에러 문구와 실제 원인이 다른 경우가 많습니다)
- 초보가 흔히 오해하는 지점
- 어디를 먼저 봐야 하는지

### 좋은 예 (실제 반영된 것들)

```python
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
    "api-cors-missing-header",
    "CORS policy: No 'Access-Control-Allow-Origin' header is present",
    "CORS 정책: Access-Control-Allow-Origin 헤더가 없습니다",
    ERROR, API, H, "브라우저에서 다른 도메인 API 를 부를 때",
    "브라우저가 막은 것이라 서버 로그에는 정상으로 찍힌다. "
    "서버가 이 도메인을 허용하도록 설정해야 풀린다. "
    "프론트 코드를 아무리 고쳐도 해결되지 않는다.",
),
(
    "git-unrelated-histories",
    "fatal: refusing to merge unrelated histories",
    "치명적 오류: 관련 없는 히스토리 병합을 거부합니다",
    ERROR, GIT, H, "따로 시작한 저장소를 합칠 때",
    "두 저장소가 공통 조상 커밋을 하나도 공유하지 않을 때 나온다. "
    "정말 합치려는 게 맞으면 --allow-unrelated-histories 를 붙인다. "
    "대개는 clone 대신 init 을 해버린 실수라 그것부터 확인한다.",
),
```

### 나쁜 예

```python
# 해석을 다시 풀어 쓴 것 - 함정이 없다
("...", "Please commit your changes.", "변경사항을 커밋해주세요.",
 PHRASE, GIT, E, "...", "변경사항을 커밋하라는 뜻이다.")

# 교과서 문장 - 실무에서 이렇게 안 쓴다
("...", "I am deploying the code to the server.", "나는 서버에 코드를 배포한다.", ...)

# 에러 문구를 만들어낸 것 - 실제로 이렇게 안 찍힌다
("...", "Error: Something went wrong with the database", "...", ERROR, DB, ...)
```

---

## 반드시 지킬 것

**1. 틀린 내용을 쓰지 마세요.** 이게 가장 중요합니다.

단어 데이터에서 실제로 있었던 사고 - `revert` 설명에 "기록을 지우지 않아 reset 과 다르다" 라고 썼는데 **틀렸습니다**. `git reset` 도 커밋을 지우지 않습니다(reflog 에 남습니다). 흔한 오해를 그대로 옮겨 적은 것이었고 리뷰 세 번째에야 걸렸습니다.

확신이 없으면 그 항목을 빼세요. 그럴듯하게 틀린 것보다 없는 게 낫습니다.

**2. 에러 메시지는 실제 문구여야 합니다.**

`ERROR` 항목의 `text` 는 **터미널에 그대로 찍히는 원문**이어야 합니다. 기억으로 재구성하지 마세요. 대소문자, 따옴표, 콜론 위치까지 실제와 같아야 사용자가 검색해서 찾습니다.

확실하지 않으면 그 에러는 넣지 마세요.

**3. PHRASE 는 실제로 쓰이는 문장이어야 합니다.**

이슈 트래커, PR 코멘트, 슬랙, 문서에서 그대로 나올 법한 문장. 문법 교재 예문은 안 됩니다.

**4. 같은 문장을 여러 번 주지 마세요.**

`text` 가 겹치는 것은 모델이 허용하지만(같은 문장이 다른 상황에서 나올 수 있어서), 프롬프트 응답 안에서 중복은 피해주세요. `slug` 는 절대 겹치면 안 됩니다.

**5. 이모지를 쓰지 마세요.**

**6. 이미 있는 27개는 빼주세요.**

```
review-rebase-request, review-lgtm-nits, review-add-test, review-out-of-scope,
review-nice-catch, review-feel-free-ignore, review-another-look,
review-breaking-change, issue-cannot-reproduce, ops-revert-for-now,
ops-blocked-on, ops-heads-up-deploy, git-unrelated-histories, git-failed-push,
git-commit-or-stash, git-merge-conflict, git-detached-head,
py-module-not-found, py-nonetype-subscript, db-unique-constraint,
db-unapplied-migration, db-cannot-connect, api-cors-missing-header,
api-401, api-429, ops-502, ops-port-in-use
```

---

## 요청 수량

**분류별로 30개 이상, 총 250개 이상**을 목표로 해주세요.

| 분류 | 지금 | 목표 |
|---|---|---|
| `GIT` | 6 | 40+ |
| `REVIEW` | 8 | 40+ |
| `API` | 4 | 35+ |
| `DB` | 3 | 30+ |
| `OPS` | 4 | 35+ |
| `DEBUG` | 0 | 35+ |
| `FRONT` | 0 | 35+ (신규) |
| `CS` | 0 | 25+ (신규) |

**PHRASE 와 ERROR 비율은 4:6 정도**로 해주세요. 에러 메시지가 이 서비스의 차별점입니다.

한 번에 다 못 주면 분류별로 나눠서 여러 번 줘도 됩니다. **양보다 정확성이 우선**입니다.

### 분류별 참고

**GIT** — 에러: `fatal: not a git repository`, `error: pathspec ... did not match`, `Your branch is ahead of 'origin/main' by N commits`, `warning: LF will be replaced by CRLF`, rebase 충돌 관련. 표현: force push 논의, 브랜치 전략 제안, cherry-pick 요청

**REVIEW** — 승인/보류 표현, 완곡한 거절, 리팩터 제안, 온보딩 대화, 스프린트·회고에서 나오는 말. `Just a nit`, `Consider extracting this`, `Can we ship this behind a flag?`

**API** — 에러: HTTP 상태코드 응답 본문, `Unexpected token < in JSON at position 0`, `net::ERR_CONNECTION_REFUSED`, timeout. 표현: 스펙 합의, 버저닝 논의, 레이트리밋 안내

**DB** — 에러: `deadlock detected`, `duplicate key value violates unique constraint`, `relation "..." does not exist`, `too many connections`, 마이그레이션 충돌. 표현: 인덱스 추가 제안, 스키마 변경 논의

**OPS** — 에러: 컨테이너 종료 코드, `no space left on device`, `connection refused`, 헬스체크 실패, `ImagePullBackOff`. 표현: 배포 공지, 롤백 결정, 온콜 인수인계

**DEBUG** — 에러: `Segmentation fault (core dumped)`, `Maximum call stack size exceeded`, `RecursionError`, 테스트 실패 출력, `AssertionError`. 표현: 재현 요청, 로그 요청, 원인 추정

**FRONT** — 에러: `Hydration failed because the initial UI does not match`, `Cannot read properties of undefined (reading '...')`, `Warning: Each child in a list should have a unique "key" prop`, 빌드 에러. 표현: 컴포넌트 분리 제안, 접근성 지적

**CS** — 정처기 준비생을 염두에 두고. 알고리즘·자료구조·OS·네트워크 개념을 설명하는 영어 문장. 교재나 문서에서 나오는 정의 문장. `The time complexity of this operation is O(log n).` 같은 것

---

## 참고: 이 데이터가 들어가는 곳

`backend/apps/vocab/management/commands/seed_sentences.py` 의 `SENTENCES` 리스트입니다.
받아서 검수한 뒤 넣을 것이므로 파이썬 문법이 정확할 필요는 없습니다.
다만 위 8개 필드 순서는 지켜주세요.
