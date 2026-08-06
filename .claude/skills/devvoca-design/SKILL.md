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
py ~/.claude/hooks/record_verification.py qa --agent impeccable --note 'impeccable audit + detect 데스크톱/모바일, 결과 N건'
```

`impeccable`의 훅 기능(`/impeccable hooks on`)은 **켜지 않는다.** devvoca에는 `check_verification` 훅이 있어서 "코드를 고치면 정적 검증부터 다시"를 강제한다. UI 파일 편집마다 탐지기가 자동으로 끼어들면 검증 지문이 계속 무효화된다. 수동으로만 부른다.
