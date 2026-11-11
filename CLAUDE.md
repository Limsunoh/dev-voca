# devvoca

## 프로젝트 개요

devvoca는 주니어 개발자들이 흔히 보는 개발 영어 용어들과 정보처리기사 및 기본 CS의 영어에 대한 공포를 없애주고, 개발할 때 마주치는 에러에 대한 공포를 줄여주는 학습 어플리케이션이다.

**타겟**
- 1순위: 영어가 약한 주니어/예비 개발자
- 2순위: 정보처리기사 준비생

**지금 있는 기능**
- 익히기: 개발 단어·문장 목록과 상세, 검색
- 문제풀기: 낱개 연습, 90초 한 판, 일일공부, 복습, 오답 노트, 순위표
- 일상영어 소리내어 읽기, 회원(이메일·구글)

**이후 단계 후보**: 원문 아티클 학습, AI 튜터링

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 백엔드 | Python 3.x + Django + Django REST Framework |
| DB | PostgreSQL (로컬은 Docker) |
| 프론트 | Next.js (App Router) + TypeScript |
| AI | Anthropic Claude API (콘텐츠 생성 전용) |
| 모바일 앱 | 이 웹을 TWA(Trusted Web Activity)로 감싸 Google Play 에 낸다. Apple 은 보류. **웹에는 Ionic 을 넣지 않는다** (이유는 `.claude/skills/devvoca-design/SKILL.md`) |
| 패키지 관리 | Python: pip + requirements.txt / JS: npm |
| 배포 | 백엔드·DB Railway, 프론트 Vercel. 절차는 `DEPLOY.md` |

## 확장성 원칙

devvoca 는 단어장에서 시작해 문장과 문제풀기까지 넓혔고, 이후 **원문 아티클, AI 튜터링** 등으로 확장된다. 다음을 염두에 두고 설계한다.

**데이터 모델**
- 학습 콘텐츠는 공통 추상화를 가질 수 있게 설계. 예: 공통 베이스 모델(`LearningItem`) + `item_type` 필드, 또는 각 도메인 모델이 공통 mixin/abstract base를 상속
- 공통 필드 후보: `id`, `created_at`, `updated_at`, `is_reviewed`, `difficulty`, `category`, `source`, `created_by`
- 타입별 고유 필드는 도메인별 모델 또는 JSONField로

**도메인 분리**
- 단어·문장·일상 표현 = `apps/vocab/`, 회원 = `apps/accounts/`. 새 도메인은 `apps/articles/` 처럼 앱을 나눈다
- 학습 기록·점수·순위 같은 **공통 기능은 `apps/learning/`** 에 둔다

**AI 파이프라인 (`apps/ai_pipeline/`)**
- 단어뿐 아니라 어떤 학습 콘텐츠 타입도 생성할 수 있게 일반화 (콘텐츠 타입을 인자로 받음)
- 프롬프트 템플릿은 타입별로 나눈다. 지금은 `prompts/vocab.py`(단어), `prompts/reading.py`(한글 발음) 둘이다
- AI 응답 파싱/검증 로직도 타입별 분리

**프론트엔드**
- 학습 카드/상세 UI는 콘텐츠 타입에 무관한 props 인터페이스로 추상화 가능하게 (예: `<LearningCard type="word|sentence|error" data={...} />`)
- 라우팅: 익히기 `/learn/words`·`/learn/sentences`, 문제풀기 `/test/*`, 오답 노트 `/mistakes`, 순위표 `/board`, 일상영어 `/talk` 등
- API 클라이언트(`lib/api/`)도 도메인별 모듈로 분리

**확장성 vs 단순함의 균형**
- **MVP를 위해 오버엔지니어링하지 않는다.** "지금 당장 필요 없는 추상화"는 만들지 않는다.
- 단, **"이 자리에 다른 콘텐츠 타입이 들어올 수 있다"는 확장을 막는 설계는 피한다.** (예: 모델/엔드포인트/UI에 "단어"를 하드코딩하지 않기)
- 추후 새 콘텐츠 타입 추가가 **반나절 이상 걸릴 것 같으면 지금 추상화 고려**, 30분 안에 끝날 것 같으면 그때 가서 추상화

## 앱은 이 웹이다 (TWA)

devvoca 는 Google Play 에 먼저 낸다. 앱은 폰의 Chrome 이 `dev-voca.vercel.app` 을 주소창 없이 띄운 것(TWA)이다. 화면, 로그인, 소리내어 읽기가 모두 이 저장소의 웹 코드 그대로 돈다. 그래서 아래를 지킨다.

- **`main` 에 머지하면 앱 사용자에게도 바로 나간다.** Vercel 배포가 곧 앱 업데이트다. 스토어 심사를 거치지 않고, 폰에 옛 화면이 남지도 않는다.
- **웹 주소(origin)를 바꾸면 앱이 깨진다.** 앱은 `frontend/public/.well-known/assetlinks.json` 으로 "이 사이트의 주인" 임을 확인받는데(업로드 키 하나와 Play 앱 서명 키 세 개의 지문, `android/README.md`), 주소가 바뀌면 확인이 풀려 화면 위에 주소창이 뜬다. 쿠키도 주소마다 따로라 모두 한 번 로그아웃된다. Vercel 프로젝트 이름·도메인을 바꾸는 일은 사용자에게 먼저 묻는다.
- **브라우저에 없는 기능이 필요하면 웹 기능부터 찾는다.** 예: 앱 푸시 대신 웹 푸시(service worker).
- **화면 안에 나가는 길이 있어야 한다.** 주소창과 브라우저 뒤로 가기 버튼이 없다. Android 시스템 뒤로 가기만 있다.

**왜 이렇게 정했나**: 8월에는 React Native(Expo)로 화면을 새로 짜기로 했었다. Apple 가이드라인 4.2 가 웹을 감싼 앱을 거절해서다. 11-10 에 Apple 을 보류하면서 그 이유가 사라졌고, 11-11 에 사용자가 "이미 만들어둔걸 왜 안써" 라며 TWA 로 정했다. 계획은 `.claude/plans/2026-11-10-app-release.md` 맨 위 절에 있다.

**Apple 이나 네이티브 앱을 다시 하게 되면** 앱이 Next 를 거치지 않고 Django 를 직접 부른다. 11-10 에 그 전제로 코드를 맞춰 보니 웹만 보고 정한 것이 넷 나왔다. 구글 로그인(Next 서버가 구글 코드를 받는 방식), "IP 기준 제한은 Next 에 둔다" 는 전제, 계정당 토큰 하나, 브라우저 음성 인식이다. 그때는 이 넷부터 다시 본다.

## 폴더 구조

```
devvoca/
├── backend/
│   ├── config/           # settings, urls
│   ├── apps/
│   │   ├── vocab/        # 단어·문장·일상 표현, 문제 출제와 채점
│   │   ├── learning/     # 학습 기록, 일일공부, 복습, 순위
│   │   ├── accounts/     # 회원, 로그인, 계정 삭제
│   │   └── ai_pipeline/  # Claude API 호출 (관리자 전용)
│   └── manage.py
├── frontend/src/
│   ├── app/              # 화면과 api 중계
│   ├── components/
│   └── lib/
├── .venv/                # Python 가상환경 (git 에 없다)
├── requirements.txt
├── DEPLOY.md
└── CLAUDE.md
```

## 개발 환경 명령어

### 백엔드 (Django)

```powershell
# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt

# DB 마이그레이션
python manage.py makemigrations
python manage.py migrate

# 슈퍼유저 생성 (Admin 검수용)
python manage.py createsuperuser

# 개발 서버
python manage.py runserver

# 테스트
python manage.py test
```

### 프론트엔드 (Next.js)

```powershell
cd frontend
npm install
npm run dev      # 개발 서버
npm run build    # 프로덕션 빌드
npm run lint
```

### Docker (PostgreSQL)

```powershell
docker compose up -d   # DB 기동
docker compose down    # DB 중지
```

## 코딩 컨벤션

**Python / Django**
- PEP 8, 들여쓰기 4칸
- Django 앱은 `apps/` 하위에 도메인별로 분리
- 모델명: 단수형 (`Word`, `User`), DB 테이블명은 Django 기본 규칙 따름
- View: 가능하면 DRF의 `ViewSet` 또는 `APIView`. 함수형은 단순 케이스에만.
- Serializer는 도메인 단위로 분리
- 타입 힌트 적극 사용

**TypeScript / Next.js**
- 들여쓰기 2칸
- 컴포넌트: PascalCase, 훅: `useXxx`
- 파일: 컴포넌트는 PascalCase, 그 외는 kebab-case
- 클라이언트 컴포넌트는 `'use client'` 명시
- API 호출은 `lib/api/` 하위에 모듈화
- 런타임 의존성은 `next`/`react`/`react-dom` 셋. 늘리려면 `.claude/skills/devvoca-design/SKILL.md` 의 기준을 먼저 통과시킨다

**화면(UI) 작업을 시작하기 전에** `.claude/skills/devvoca-design/SKILL.md` 를 읽는다. 화면마다 성격이 달라 쓰는 도구가 다르고(홈은 랜딩, 목록·상세는 제품 화면), 발음기호 타이포처럼 이미 코드에 반영돼 있어 깨뜨리기 쉬운 제약이 있다. 팔레트·폰트 선정 → 작성 → 검사 → 검증 기록까지 4단계 절차가 그 문서에 있다.

**공통**
- 커밋 메시지: `feat: ...`, `fix: ...`, `refactor: ...`, `docs: ...`, `chore: ...`
- 환경 변수는 `.env` (절대 커밋 금지), 키 이름은 `SCREAMING_SNAKE_CASE`
- 비밀키/API 키는 코드에 절대 하드코딩 금지
- 누가 보더라고 쉽게 볼수 있도록 가독성있는 코드 작성 
- class, f(x) 등 상속 잘 활용할 수 있도록 코드 작성

## AI 콘텐츠 생성 파이프라인 규칙

devvoca의 AI 사용은 **콘텐츠 제작 도구**로만 사용한다. 사용자 요청 경로에 절대 두지 않는다.

**올바른 흐름**
```
관리자 단어 입력 → Claude API 호출 (1회) → AI 응답 검수 (Django Admin) → DB 저장
                                                                    ↓
사용자 검색 요청 ─────────────────────────────────────────→ DB 조회만 (API 호출 X)
```

**규칙**
1. Claude API 호출 코드는 `apps/ai_pipeline/` 안에만 존재 (관리자/배치 전용)
2. View/Serializer/사용자 요청 핸들러에서 직접 Claude API를 호출하지 않는다
3. AI 생성 결과는 `is_reviewed=False` 상태로 저장되고, Admin 검수 후 `True`로 바뀐다
4. 검수 안 된 단어는 사용자에게 노출하지 않는다 (`is_reviewed=True` 필터 필수)
5. API 키는 환경변수 `ANTHROPIC_API_KEY`에서만 읽는다

## 금지 사항

- **사용자 요청 경로에서 Claude API 직접 호출 금지** (비용 폭발 + 응답 지연)
- **검수되지 않은 AI 결과를 일반 사용자에게 노출 금지**
- `.env`, API 키, 비밀번호를 커밋 금지
- `--no-verify`로 pre-commit hook 우회 금지
- 게임/대용량 더미 데이터를 레포에 커밋 금지
- 마이그레이션 파일을 손으로 편집 금지 (`makemigrations`로 재생성)
- `python manage.py migrate --fake` 같은 우회 명령은 사용자 확인 후에만

## 커밋 전 검증 5단계

전역 훅(`check_verification.py` + `check_verification_on_stop.py`)이 강제한다. **`.py`/`.html`/`.js`/`.css`/`.ts`/`.tsx`/`.mts`/`.mjs` 를 하나라도 건드리면** commit·push 와 **턴 종료**가 막힌다(문서·설정만 바꾼 변경은 대상 아님).

**목록을 기억으로 재구성하지 말고** 아래 명령으로 읽는다:
```
py ~/.claude/hooks/record_verification.py --show
```

| 단계 | devvoca 에서 무엇으로 채우나 |
|---|---|
| `static` | `.claude/agents/static-verifier.md` 서브에이전트 |
| `dynamic` | `.claude/agents/dynamic-tester.md` 서브에이전트 |
| `review_plugin` | `pr-review-toolkit:code-reviewer` 플러그인 에이전트 |
| `review_skill` | `.claude/agents/devvoca-reviewer.md` (전역 code-reviewer 스킬 대신 — 도메인 규칙을 안다) |
| `qa` | UI 를 건드린 변경이면 `impeccable` 로 채운다 — 절차는 `.claude/skills/devvoca-design/SKILL.md`. 백엔드·프론트 무관한 변경이면 `--skip` |

**화면 QA 는 앱 화면으로 본다. 데스크톱 크기는 보지 않는다.** devvoca 는 이 웹을 감싼 앱(TWA)으로 출시한다. 사람들은 폰에서 본다.

| 크기 | 용도 |
|---|---|
| 390 x 844 | 기준 폰 (iPhone) |
| 375 x 667 | 작은 iPhone(SE). 세로가 짧아 버튼과 탭바가 겹치기 쉽다 |
| 412 x 915 | 큰 안드로이드 폰. 폭이 넓어 배치가 벌어지는지 본다 |
| 360 x 840 | 갤럭시 Z 폴드 7·폴드 8 Ultra 접은 화면. 폭이 가장 좁아 줄바꿈과 넘침이 먼저 깨진다 |
| 416 x 657 | 폴드 8 접은 화면. 폭은 넓고 세로가 짧아 버튼과 탭바가 겹치기 쉽다 |
| 984 x 1092 | 폴드 7 펼친 화면 |
| 1128 x 1252 | 폴드 8 Ultra 펼친 화면 |
| 1224 x 924 | 폴드 8 펼친 화면. 가로가 더 길다. 폰 화면이 늘어나 배치가 벌어지거나 탭바와 본문 폭이 어긋나는지 본다 |

펼친 화면 셋(984, 1128, 1224)은 `deviceScaleFactor: 2`, 나머지는 `3` 으로 연다. 폴드 크기는 실제 기기에서 잰 값이 아니다. 해상도를 접은 화면은 배율 3, 펼친 화면은 배율 2 로 나눈 값이라 재 보고 다르면 고친다.

창 크기만 줄이면(`browser_resize`) 앱 화면이 아니다. 데스크톱 브라우저의 스크롤바가 폭을 차지해 줄바꿈이 실제 폰과 달라지고 터치도 꺼져 있다. 모바일 에뮬레이션으로 연다.

```js
// mcp__playwright__browser_run_code_unsafe
const ctx = await page.context().browser().newContext({
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  deviceScaleFactor: 3,
});
const phone = await ctx.newPage();
```

viewport 만 바꿔 여덟 크기를 모두 본다. 크기마다 스크린샷을 찍어 배치, 줄바꿈, 하단 탭바에 가리는 곳을 눈으로 확인한다. QA 를 서브에이전트에 맡길 때도 **프롬프트에 여덟 크기와 에뮬레이션을 명시**한다.

**왜 이렇게 정했나**: 2026-11-09 사용자 지적. 앱으로 출시한다고 여러 번 말했는데 세션들이 넓은 데스크톱 화면까지 웹으로 보고 있었다. 앱 화면으로 봐야 배치와 구성, 줄바꿈이 제대로 보인다.

기록:
```
py ~/.claude/hooks/record_verification.py static --agent static-verifier --note '...'
py ~/.claude/hooks/record_verification.py qa --agent impeccable --note 'detect 390x844·360x840·1224x924 각 1회, N건. 앱 화면 여덟 크기 모바일 에뮬레이션 스크린샷 확인'
py ~/.claude/hooks/record_verification.py qa --skip --note 'UI 변경 없음 - 백엔드만'
```

**코드를 고치면 지문이 무효가 되어 정적 검증부터 다시** 돌려야 한다. 이건 버그가 아니라 "검증한 뒤 몰래 수정" 을 막는 설계다.

## 커밋부터 머지까지

**전역 규칙과 `feature-flow` 스킬에는 "commit·push·PR 전에 사용자에게 묻는다" 고 적혀 있지만 이 저장소에는 적용하지 않는다.** 세션은 작업을 받으면 아래 순서를 끝까지 진행하고 결과만 보고한다. 병렬 세션도 같다.

1. feature 브랜치에서 구현한다. 병렬 세션이면 자기 worktree 에서 한다.
2. 위의 검증 5단계를 마친다.
3. 커밋 메시지와 PR 본문을 `prose-reviewer` 에게 읽힌 뒤 commit·push·PR 을 올린다.
4. `gh pr checks <번호> --watch` 로 모든 체크가 끝나길 기다린다.
5. 전부 초록이면 `gh pr merge <번호> --auto --merge` 를 실행한다. 보고에 PR 링크와 머지 여부를 적는다.

체크가 하나라도 빨가면 병합하지 않는다. 무엇이 잡혔는지 확인해 사용자에게 먼저 보이고, 고칠 수 있으면 같은 브랜치에 고쳐 올린다.

**머지되면 Vercel 이 `main` 을 운영 화면에 바로 배포한다.** 사람이 보는 단계가 따로 없으므로 위 검사가 마지막 관문이다.

사용자에게 먼저 묻는 경우:

- 사용자가 "이건 내가 머지" 라고 한 PR, 계획 문서가 판단 대기로 둔 PR
- 강제 push, 데이터 삭제처럼 되돌리기 어려운 일
- 운영 DB, 배포 설정, 요금이 드는 변경

GitHub 쪽 설정(`main` 보호 규칙): 필수 검사는 `test`·`frontend`·`GitGuardian Security Checks`, 최신 `main` 기준 통과, 관리자 우회 불가, 사람의 승인은 요구하지 않는다. 앞 PR 이 머지돼 뒤처진 PR 은 세션이 `gh pr update-branch <번호>` 로 올린다.

**왜 이렇게 정했나**: 세션 셋이 PR 을 동시에 올리는 저장소라, 사용자가 PR 마다 들어가 승인하고 머지하면 PR 수만큼 기다림이 늘어난다(2026-09-24, 09-27 에 사용자가 정함). GitGuardian 은 2026-11-09 에 필수로 올렸다. #118 이 GitGuardian 경고를 단 채 머지된 뒤다.

## 코드 구조는 grep 말고 그래프에 묻는다

`graphify-out/graph.json` 에 이 저장소의 **3142 노드 / 5695 엣지** 지도가 있다.
"무엇이 무엇을 부르는가" 는 여기서 답이 나온다. 토큰 비용 0(로컬 AST)이고
질문 하나에 몇 초다.

```
graphify explain "app/page.tsx"        # 이 파일이 무엇을 import 하고 누가 부르나
graphify explain "DailyStudy"          # 이 모델을 누가 쓰나
graphify path "QuizBoard.tsx" "Word"   # 둘 사이가 어떻게 이어지나
graphify query "복습 점수는 어디서 계산되나"
```

**언제 쓰나** - 파일을 고치기 전에 "이걸 누가 쓰나" 를 물을 때, 기능이
있는지 없는지 확인할 때, 어디에 붙일지 자리를 찾을 때.

**왜 이 규칙이 있나**: 2026-09-06 에 홈 화면을 고치겠다며 `learning` 앱이
없다고 단정했다. 있었다. `DailyCard` 가 이미 홈에 렌더되는 것도 못 봤다 -
`{user && ...}` 안에 있어서 게스트로 본 화면에는 안 떴는데, 그것을 "기능이
없다" 로 읽었다. 둘 다 `grep` 으로 파일 몇 개만 보고 내린 결론이었고,
`graphify explain "app/page.tsx"` 한 줄이면 36개 연결이 다 나왔다.

**코드를 바꾼 뒤에는 갱신한다.** 안 하면 지도가 옛 코드를 가리킨다.

```
graphify . --update --code-only --no-viz   # 증분, API 키 불필요
graphify cluster-only .                    # 리포트까지 다시
```

`--code-only` 를 빼면 문서·이미지까지 훑느라 LLM API 키를 요구한다.
구조를 물으려는 것이면 코드만으로 충분하다.

GRAPH_REPORT.md 머리에 `Built from commit:` 이 적혀 있다. `git rev-parse HEAD`
와 다르면 지도가 낡은 것이다.

## `.claude/CODE_INSIGHTS.md` 를 먼저 읽는다 (조건 없음)

**기능 작업을 시작할 때 무조건 읽는다.** 전역 지침은 "관련 있을 때만" 이지만
이 프로젝트에서는 그 예외를 적용하지 않는다 - 그 파일에는 배포·스키마 함정만
있는 게 아니라 **작업 방식 교훈**(형제 grep, QA 를 어떤 서버로 하나, 검증
에이전트를 어떻게 띄우나, 지난 PR 이 왜 오래 걸렸나)이 쌓여 있고, 그건 어떤
작업이든 걸린다.

```
grep -n "^## " .claude/CODE_INSIGHTS.md      # 목록부터. 27개라 통독은 비싸다
```

제목을 훑고 이번 작업에 걸릴 것만 펼쳐 읽는다. **맨 아래 "작업 시간 기록"
절은 매번 읽는다** - 직전 PR 들이 무엇에 시간을 먹었는지가 거기 있다.

**왜 조건을 없앴나**: 2026-08-26 복습 프론트 작업에서 228분이 걸렸는데, 그중
40분(HMR 때문에 dev 서버에서 버튼이 안 먹는 것)과 검증 2라운드(한 곳을 고치며
같은 파일의 형제를 안 본 것)가 **이미 이 파일에 적혀 있던 함정**이었다. 그
세션은 파일에 쓰기만 두 번 하고 한 번도 안 읽었다. "관련 있을 때만" 이라는
조건이 판단을 요구하고, 바쁠 때 그 판단은 늘 "무관" 쪽으로 떨어진다.

## 작업 진행 방식 (Claude Code에게)

1. 새로운 기능 작업 전, 먼저 **간단한 계획(2~5줄)**을 제시하고 사용자 확인을 받는다
2. 큰 변경은 Plan 모드를 활용한다
3. 지금 있는 기능을 벗어나는 제안은 **"범위 밖 제안"이라고 명시**하고 진행 여부를 묻는다
4. 한 번에 너무 많은 파일을 생성하지 않는다. 작은 단위로 컨펌 받으며 진행
5. 설치/명령 실행 전, 무엇을 왜 실행하는지 한 줄 요약
6. 사용자는 Claude Code 초보임. 새 개념 처음 사용 시 한 줄 설명 추가
7. 한국어로 응답

## 용어

- 정처기 = 정보처리기사 (한국 IT 자격증)
- 검수 = AI가 생성한 단어 데이터를 관리자가 확인/수정하는 과정
