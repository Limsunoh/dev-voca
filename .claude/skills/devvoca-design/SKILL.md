---
name: devvoca-design
description: devvoca 프론트엔드의 화면을 만들거나 고칠 때 사용한다. 홈·단어 목록·문장 목록·상세 화면의 디자인 방향, 팔레트·폰트 현황, 의존성 추가 기준, 어떤 디자인 스킬을 어느 화면에 쓸지, 커밋 전 qa 검증을 무엇으로 채울지를 담는다. 공통 지식(참조 소스 판정 기준, AI 티 신호, 스킬 교통정리)은 전역 design-references 스킬에 있으니 그쪽을 먼저 본다.
---

# devvoca 디자인

전역 `design-references` 스킬의 공통 규칙 위에 devvoca 사정을 얹는다.

## 지금 상태 (2026-08-06 실측)

| 항목 | 값 |
|---|---|
| 스택 | Next.js 16.2.12 + React 19.2.4 + Tailwind v4 |
| 런타임 의존성 | `next`, `react`, `react-dom` **셋뿐** |
| 폰트 | Geist / Geist Mono (`next/font/google`) |
| 팔레트 | Tailwind `slate` 계열 + 흑백. 커스텀 토큰 없음 |
| 다크 모드 | `prefers-color-scheme` 기반. 토글 없음 |
| 디자인 토큰 | `globals.css`에 `--background` / `--foreground` 두 개뿐 |

`npx impeccable detect`를 데스크톱·모바일 양쪽으로 돌렸을 때 결정론적 규칙 59개에서 **0건**이 나왔다. 지금 UI는 절제돼 있고 "AI 티"의 전형(보라 그라데이션·과한 그림자·저대비)은 없다. 밋밋함을 고친다면 없애는 작업이 아니라 **더하는 작업**이다.

## 화면 유형이 섞여 있다

이게 스킬 선택의 전부다.

| 화면 | 유형 | 무엇이 중요한가 |
|---|---|---|
| `/` (홈) | **Persuade** | 한 장짜리 랜딩. 지금 제목 + 문단 + 버튼 2개가 전부라 가장 밋밋한 곳 |
| `/learn/words`, `/learn/sentences` | **Operate** | 검색·필터·페이지네이션. 훑어보기와 일관성이 표현보다 앞선다 |
| `/learn/words/[id]`, `/learn/sentences/[id]` | **Read** | 뜻·발음·예문을 읽는 화면. 읽기 편한 구조가 먼저 |

그래서:

- **홈에만** `design-taste-frontend`를 쓴다. 이 스킬은 스스로 "대시보드·데이터 테이블·다단계 제품 UI 아님"이라고 못 박고 있어서 목록 화면에 부르면 안 맞는 조언이 나온다. 85KB짜리라 컨텍스트도 크게 잡아먹는다.
- **목록·상세에는** `impeccable`을 쓴다. Operate/Read를 정면으로 다루는 쪽이다. `critique`, `layout`, `typeset`, `adapt` 위주.
- 팔레트·폰트 후보를 **찾을 때만** `ui-ux-pro-max`. 예: `py ~/.claude/skills/ui-ux-pro-max/scripts/search.py "learning app education vocabulary" --domain color`

## 의존성은 셋에서 늘리지 않는 걸 기본으로

`next`/`react`/`react-dom` 셋뿐인 상태가 devvoca의 자산이다. 배포가 가볍고 업그레이드가 단순하다. 늘리려면 근거를 남긴다.

- 장식 목적으로 런타임 패키지를 넣지 않는다. `@splinetool/runtime`(6.5MB)이나 `framer-motion`(4.6MB)은 현재 앱 전체보다 무겁다.
- 애니메이션이 필요하면 CSS transition과 `@keyframes`를 먼저 쓴다. Tailwind v4에 이미 있다.
- 이미지 자산(예: Shapefest의 512px 렌더)은 런타임 비용이 0이라 판단 기준이 다르다. 이쪽이 먼저다.
- shadcn/ui를 깔지 않았다. Vengeance UI 같은 MIT 컴포넌트를 참고할 때 `@/lib/utils`의 `cn`이 필요하면 그 5줄만 직접 쓰고, CLI 설치는 하지 않는다.

## 모바일 앱 — React Native (Expo), 단 착수는 API 다음

앱으로 하려는 것은 1일 1학습 푸시, 학습 루틴(단어 → 문장 → 문제풀이), 문제풀이 속도·점수, 전 유저 랭킹, 스트릭이다.

**프레임워크는 React Native (Expo) 로 간다.** 후보였던 Ionic + Capacitor 는 접었다. 두 방식의 차이는 무엇이 화면을 그리느냐다.

| 방식 | 화면을 그리는 주체 |
|---|---|
| Ionic + Capacitor | WebView. HTML/CSS 를 브라우저 엔진이 그린다 |
| React Native | iOS `UIView` / Android `View`. 네이티브 위젯으로 변환된다 |

Ionic 의 장점은 웹 자산(CSS·컴포넌트) 재사용인데, 앱과 웹은 UI 를 공유하지 않기로 했으니 그 장점이 사라진다. 반면 단점은 남는다 — Apple 가이드라인 4.2 는 2026 년 현재 WebView 래퍼를 사실상 거절하고, 푸시 같은 API 몇 개를 붙이는 것으로는 부족하다고 명시한다. 네이티브 UI 로 컴파일되는 React Native 는 이 문제를 피한다. React 지식도 그대로 이어진다.

`@ionic/cli` 가 전역에 설치돼 있지만 쓰지 않는다.

**다만 착수 순서는 앱이 먼저가 아니다.** 위 다섯 가지 중 클라이언트가 필요한 건 푸시 하나뿐이고, 점수·속도 측정·랭킹·스트릭은 전부 백엔드 기능이라 웹에서도 똑같이 동작한다. **학습 기록·점수 API 를 먼저 만들고 웹에서 굴려본 뒤 앱에 착수한다.** 그때는 API 가 완성돼 있어 RN 은 붙이기만 하면 된다.

**웹에 Ionic 컴포넌트를 넣지 않는다.** 이건 별개로 확정이다. 취향 문제가 아니라 맞물리지 않는다.

| 항목 | 확인한 내용 (2026-08-13) |
|---|---|
| 지원 프레임워크 | Ionic 공식 문서는 Angular/React/Vue 만 든다. **Next.js 는 없다** |
| 라우터 | `@ionic/react-router` 가 `react-router` 를 요구한다. 우리는 App Router 를 쓴다 |
| 렌더링 | `IonApp` 은 클라이언트 전용이다. 단어·문장 목록은 **서버 컴포넌트**로 Django API 를 호출한다 |
| 용량 | `@ionic/core` 19.5MB + `ionicons` 5.9MB. 현재 런타임 의존성 총 3개 |

Ionic 팀이 만든 Next.js 스타터조차 `next export` 로 SPA 를 뽑고 라우팅을 react-router 에 넘긴다. SSR 을 쓰지 않는다. 즉 Ionic 도입은 UI 라이브러리 추가가 아니라 **렌더링 구조 교체**다.

**그래서 웹 화면을 만들 때 앱을 이렇게 고려한다.** 아래 넷은 클라이언트를 무엇으로 정하든 유효하다.

- **앱과 공유하는 것은 API 계약이지 컴포넌트가 아니다.** 화면 로직을 `lib/api/` 아래 순수 함수로 밀어두면 앱에서 그대로 재사용된다. 컴포넌트에 fetch 를 박으면 앱에서 다시 쓴다
- **모바일 폭(390x844)에서 먼저 성립해야 한다.** 앱이 나올 화면이면 폰이 기준이다. 데스크톱은 넓어진 경우다
- **터치 대상은 44px 이상.** 앱으로 옮겼을 때 그대로 쓰는 치수다. 필터 칩·페이지네이션 버튼이 자주 걸린다
- **웹 전용 상호작용에 기능을 걸지 않는다.** hover 로만 드러나는 정보, 우클릭 메뉴 같은 것. 터치에는 hover 가 없다

### 학습 기록·점수를 만들 때 (MVP 외, 착수 시 참고)

자리는 `apps/learning/` 이다. CLAUDE.md 확장성 원칙이 학습기록을 코어 앱으로 빼두라고 이미 적어뒀고, 단어·문장 어느 쪽에도 붙지 않는 도메인이라 그 자리가 맞다. 나중에 고치기 비싼 것 넷:

- **점수와 소요 시간은 서버가 계산한다.** 클라이언트가 잰 시간을 받으면 조작된다. 랭킹이 걸리면 반드시 누군가 한다. 서버가 문제를 내준 시각을 기록하고 제출 시각과의 차이로 구한다
- **랭킹은 집계해두고 읽는다.** 전 유저를 매번 정렬하면 유저가 늘자마자 느려진다. 일별 집계 테이블이나 캐시에서 읽는다
- **스트릭의 "1일" 은 KST 로 못 박는다.** UTC 로 두면 밤 9시에 공부한 한국 유저가 다음 날로 카운트된다. 스트릭이 끊기면 유저는 떠난다
- **푸시 발송 시각은 유저마다 다르게 둔다.** 전원 같은 시각에 쏘면 알림 피로가 오고 서버도 그 순간만 몰린다

## 지금 손볼 곳 (실측으로 찾은 것)

1. **`src/app/page.tsx:7`의 `min-h-screen`** — iOS Safari에서 주소창이 접히고 펴질 때 레이아웃이 튄다. `min-h-[100dvh]`로 바꾼다.
2. **`public/` 안 미사용 파일 5개** — `next.svg`, `vercel.svg`, `globe.svg`, `window.svg`, `file.svg`가 `src` 어디에서도 참조되지 않는다. create-next-app 잔해다.
3. **`frontend/README.md`** — create-next-app 기본 문구 그대로다. 진짜 "템플릿 티"는 여기 남아 있다.
4. **Geist 폰트** — impeccable의 "너무 흔해진 폰트" 목록에 Geist가 들어 있다. 탐지기는 `next/font`의 해시 클래스명 때문에 못 잡지만 사람 눈에는 보인다. 홈을 다시 만든다면 폰트가 가장 큰 인상 변화를 만든다. 다만 **한글 본문이 있으므로** 라틴 전용 폰트를 본문에 바로 물리면 한글이 폴백으로 떨어져 어색해진다. 라틴(용어·코드)과 한글(뜻·설명)을 나눠 지정한다.

## 타이포 제약 (코드에 이미 반영돼 있음, 깨뜨리지 말 것)

- **발음기호(IPA)에 고정폭 글꼴을 쓰지 않는다.** 일부 IPA 기호가 고정폭에서 폭이 어긋나거나 깨진다. `LearningCard`의 `aside`가 일부러 `font-mono` 없이 렌더된다.
- **단어·에러 메시지는 고정폭, 사람이 쓴 문장은 가변폭.** `LearningCard`의 `monoTitle` prop이 이 구분을 담당한다. 문장 목록은 `monoTitle={false}`로 넘긴다.
- 발음기호에는 `lang="en-US"`가 붙어 있다. 한글 폰트가 IPA를 잘못 렌더하는 걸 막는다.

## 참조해도 되는 소스

전역 `design-references`의 통과 목록 중 devvoca에 실제로 쓸 만한 것:

- **[Shapefest](https://shapefest.com/)** — 빈 상태(검색 결과 없음, 아직 문장 없음) 일러스트에 쓸 수 있다. 512px 무료, 상업 사용 허용. 이미지 한 장이라 의존성이 늘지 않는다. 다만 3D 클레이 렌더는 지금의 절제된 slate 톤과 결이 다르니, 쓰려면 홈이나 빈 상태처럼 국한된 자리에만 둔다.
- **[Vengeance UI](https://github.com/Ashutoshx7/VengeanceUI)** (MIT) — 검색 모달, 내비게이션 같은 실용 컴포넌트의 **구조를 읽는 용도**. 코드가 전부 공개돼 있다. framer-motion 의존 부분은 걷어내고 마크업과 상태 처리만 참고한다.

나머지(Spline, Getlayers, Animmaster Lib, Skiper UI, Craftwork)는 탈락시켰다. 사유는 전역 스킬에 적어뒀으니 다시 조사하지 않는다.

## 화면 작업 절차

홈을 다시 만들거나 목록·상세를 손볼 때 이 순서로 한다. 순서가 중요한 이유는 2번이 1번의 결정을 재료로 쓰고, 3번은 2번이 끝나야 의미가 있기 때문이다.

### 0. 먼저 확인할 것

- 지금 만지는 화면이 어느 유형인지 (위 표). 이걸 틀리면 1~3번이 전부 어긋난다.
- 이 변경이 홈만 건드리는지, 목록·상세까지 가는지. 범위가 넘어가면 스킬 선택이 달라진다.

### 1. 팔레트와 폰트 후보를 먼저 정한다

화면을 쓰기 전에 색과 글꼴을 정한다. 나중에 정하면 이미 쓴 코드를 다시 고치게 된다.

```powershell
py ~/.claude/skills/ui-ux-pro-max/scripts/search.py "learning app education vocabulary" --domain color --max-results 5
py ~/.claude/skills/ui-ux-pro-max/scripts/search.py "developer learning korean" --domain typography --max-results 5
```

이 스킬은 **추천만 하고 코드를 쓰지 않는다.** 결과 중 하나를 고르는 건 사람이다. 고른 값은 `globals.css` 의 `@theme inline` 에 토큰으로 넣고, 컴포넌트에서는 토큰만 참조한다. 화면마다 hex 를 박으면 나중에 테마를 못 바꾼다.

폰트를 고를 때 **devvoca 고유 제약이 하나 있다.** 화면에 라틴(용어·코드)과 한글(뜻·설명)이 항상 같이 나온다. 라틴 전용 폰트를 본문에 그대로 물리면 한글이 폴백으로 떨어져 두 글자체가 어긋나 보인다. 라틴용과 한글용을 나눠 지정하고, 실제로 단어 목록 화면에서 눈으로 확인한 뒤 확정한다.

### 2. 홈은 design-taste-frontend 를 켠 채로 쓴다

**홈에만 쓴다.** 이 스킬은 본문에서 스스로 "대시보드·데이터 테이블·다단계 제품 UI 아님" 이라고 못 박는다. 목록 화면에 부르면 랜딩 기준의 조언이 나와서 오히려 훑어보기를 방해한다. 85KB 짜리라 컨텍스트도 크게 잡아먹는다.

스킬이 세 다이얼을 묻는데, devvoca 홈의 출발값은 이렇게 잡는다.

- `DESIGN_VARIANCE 6` — 학습 도구지 에이전시 포트폴리오가 아니다. 실험적일 이유가 없다
- `MOTION_INTENSITY 3` — 오래 머물며 읽는 서비스다. 움직임이 많으면 피로해진다
- `VISUAL_DENSITY 3` — 홈은 진입점 한 장이라 비워두는 편이 낫다

목록·상세를 손볼 때는 이 스킬 대신 `impeccable` 을 쓴다. `critique`(위계·명확성), `layout`(여백·리듬), `typeset`(글자 크기), `adapt`(모바일).

### 3. 다 만든 뒤 기계로 한 번, 눈으로 한 번

기계 검사부터. 백엔드까지 띄워야 학습 화면이 뜬다(아래 절 참고).

```bash
npx impeccable detect http://localhost:3000/                    # 홈
npx impeccable detect http://localhost:3000/learn/words          # 목록
npx impeccable detect --viewport 390x844 http://localhost:3000/learn/words   # 모바일
```

**결과가 0건이어도 끝이 아니다.** 탐지기가 구조적으로 못 잡는 게 있다.

- **폰트** — `next/font` 가 해시 클래스명(`geist_a71539c9-module__...`)을 내보내서 `font-family` 문자열이 HTML 에 안 남는다. 폰트 규칙이 통째로 무력화된다
- **`h-screen` / `min-h-screen`** — iOS Safari 주소창 문제를 정규식이 못 잡는다
- **소스 스캔은 얕다** — `detect src` 는 JSX/TSX 에 정규식만 돌린다. URL 스캔이 본체다

그래서 눈으로 볼 것을 정해둔다.

**두 크기를 반드시 다 본다.** 하나만 보고 넘어가지 않는다.

```
mcp__playwright__browser_resize  390 x 844    # 폰
mcp__playwright__browser_resize  1280 x 800   # 데스크톱
```

각각 `browser_take_screenshot` 으로 찍어 **이미지를 직접 열어 본다.** 스냅샷(접근성 트리)만으로는 겹침·넘침이 안 보인다.

데스크톱만 보면 여백이 넉넉해 문제가 묻힌다. 2026-08-12 로그인 화면에서 실제로 그랬다 — 머리말이 두 번 나오고 홈에 불필요한 스크롤이 생겼는데, 데스크톱에서는 둘 다 안 띄었고 모바일로 보자마자 드러났다.

QA 를 서브에이전트에 맡길 때도 **프롬프트에 두 크기를 명시한다.** 안 적으면 데스크톱만 보고 온다.

볼 것:

- 단어 목록에서 **라틴과 한글이 한 줄에 섞였을 때** 어긋나 보이지 않는지
- 발음기호(IPA)가 깨지거나 폭이 어긋나지 않는지
- 모바일 폭에서 필터·페이지네이션이 눌리는지
- 머리말·탭 같은 공통 요소가 **화면마다 중복되지 않는지**
- 세로 높이가 화면을 넘어 불필요한 스크롤이 생기지 않는지
- 다크 모드로 전환했을 때 대비가 무너지지 않는지

`detect` 가 0건이면 "AI 티가 없다" 는 뜻이지 "잘 만들었다" 는 뜻이 아니다. 밋밋함은 탐지기가 잡는 항목이 아니다.

### 4. 검증 기록을 남긴다

UI 를 건드렸으면 `qa` 단계를 실제로 채운다. 결과 건수를 사유에 적어둔다.

```
py ~/.claude/hooks/record_verification.py qa --agent impeccable --note 'detect 데스크톱/모바일 각 1회 N건. 390x844 와 1280x800 스크린샷 확인, 폰트·다크모드 포함'
```

### 하지 말 것

- **런타임 의존성 추가** — 위 "의존성" 절의 기준을 먼저 통과시킨다. 장식 목적이면 넣지 않는다
- **목록·상세에 `design-taste-frontend` 호출** — 맞지 않는 조언이 나온다
- **`/impeccable hooks on`** — `check_verification` 훅과 충돌해 검증 지문이 계속 무효화된다. 수동 호출만
- **탐지기 0건을 근거로 "확인 끝" 이라고 보고** — 위 블라인드스팟 세 가지를 눈으로 본 뒤에 말한다

## 화면을 스캔하려면 백엔드도 띄워야 한다

`/learn/words`는 Django API를 호출하는 서버 컴포넌트라, 백엔드 없이 dev 서버만 띄우면 404가 뜬다. 홈(`/`)만 정적이다.

```powershell
# 1) DB + 백엔드
docker compose up -d
.\.venv\Scripts\Activate.ps1
python backend/manage.py runserver

# 2) 프론트
cd frontend; npm run dev

# 3) 스캔 (데스크톱 / 모바일)
npx impeccable detect http://localhost:3000/learn/words
npx impeccable detect --viewport 390x844 http://localhost:3000/learn/words
```

## 커밋 전 검증의 qa 단계

CLAUDE.md의 검증 5단계 중 `qa`는 "프론트 미구현"을 이유로 계속 `--skip` 상태였다. 이제 화면이 있으니 UI를 건드린 변경에서는 실제로 채운다.

```
py ~/.claude/hooks/record_verification.py qa --agent impeccable --note 'impeccable audit + detect 데스크톱/모바일 N건. 390x844 와 1280x800 스크린샷 확인'
```

`impeccable`의 훅 기능(`/impeccable hooks on`)은 **켜지 않는다.** devvoca에는 `check_verification` 훅이 있어서 "코드를 고치면 정적 검증부터 다시"를 강제한다. UI 파일 편집마다 탐지기가 자동으로 끼어들면 검증 지문이 계속 무효화된다. 수동으로만 부른다.
