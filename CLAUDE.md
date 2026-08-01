# devvoca

## 프로젝트 개요

devvoca는 주니어 개발자들이 흔히 보는 개발 영어 용어들과 정보처리기사 및 기본 CS의 영어에 대한 공포를 없애주고, 개발할 때 마주치는 에러에 대한 공포를 줄여주는 학습 어플리케이션이다.

**타겟**
- 1순위: 영어가 약한 주니어/예비 개발자
- 2순위: 정보처리기사 준비생

**MVP 범위**
- 용어/단어장: 한↔영, 뜻, 예문 CRUD + 검색
- 이후 단계 후보: 원문 아티클 학습, 에러 메시지 사전, AI 튜터링

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 백엔드 | Python 3.x + Django + Django REST Framework |
| DB | PostgreSQL (로컬은 Docker) |
| 프론트 | Next.js (App Router) + TypeScript |
| AI | Anthropic Claude API (콘텐츠 생성 전용) |
| 패키지 관리 | Python: pip + requirements.txt / JS: npm 또는 pnpm |
| 배포 | 미정 (후보: 백엔드 Railway, 프론트 Vercel) |

## 확장성 원칙

devvoca의 MVP는 단어장이지만, 이후 **문장/구문, 에러 메시지, 원문 아티클, AI 튜터링** 등으로 확장된다. 처음부터 다음을 염두에 두고 설계한다.

**데이터 모델**
- 학습 콘텐츠는 공통 추상화를 가질 수 있게 설계. 예: 공통 베이스 모델(`LearningItem`) + `item_type` 필드, 또는 각 도메인 모델이 공통 mixin/abstract base를 상속
- 공통 필드 후보: `id`, `created_at`, `updated_at`, `is_reviewed`, `difficulty`, `category`, `source`, `created_by`
- 타입별 고유 필드는 도메인별 모델 또는 JSONField로

**도메인 분리**
- 단어장 = `apps/vocab/`, 이후 추가될 도메인도 같은 패턴: `apps/sentences/`, `apps/errors/`, `apps/articles/`
- 검색/태그/즐겨찾기/학습기록 등 **공통 기능은 `apps/learning/` 같은 코어 앱**으로 분리 가능하도록 의식하며 작성

**AI 파이프라인 (`apps/ai_pipeline/`)**
- 단어뿐 아니라 어떤 학습 콘텐츠 타입도 생성할 수 있게 일반화 (콘텐츠 타입을 인자로 받음)
- 프롬프트 템플릿은 타입별 분리: `prompts/vocab.py`, `prompts/sentence.py`, `prompts/error.py` 등
- AI 응답 파싱/검증 로직도 타입별 분리

**프론트엔드**
- 학습 카드/상세 UI는 콘텐츠 타입에 무관한 props 인터페이스로 추상화 가능하게 (예: `<LearningCard type="word|sentence|error" data={...} />`)
- 라우팅: `/vocab`, `/sentences`, `/errors` 등 도메인별 경로
- API 클라이언트(`lib/api/`)도 도메인별 모듈로 분리

**확장성 vs 단순함의 균형**
- **MVP를 위해 오버엔지니어링하지 않는다.** "지금 당장 필요 없는 추상화"는 만들지 않는다.
- 단, **"이 자리에 다른 콘텐츠 타입이 들어올 수 있다"는 확장을 막는 설계는 피한다.** (예: 모델/엔드포인트/UI에 "단어"를 하드코딩하지 않기)
- 추후 새 콘텐츠 타입 추가가 **반나절 이상 걸릴 것 같으면 지금 추상화 고려**, 30분 안에 끝날 것 같으면 그때 가서 추상화

## 폴더 구조 (계획)

```
devvoca/
├── backend/              # Django 프로젝트 (예정)
│   ├── config/           # settings, urls
│   ├── apps/
│   │   ├── vocab/        # 단어장 도메인
│   │   ├── accounts/     # 사용자/인증
│   │   └── ai_pipeline/  # Claude API 호출 (관리자 전용)
│   └── manage.py
├── frontend/             # Next.js (예정)
│   ├── app/
│   ├── components/
│   └── lib/
├── .venv/                # Python 가상환경
├── requirements.txt
└── CLAUDE.md
```

> 현재는 `.venv/`만 존재. Django/Next.js 프로젝트는 아직 시작 전.

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

### 프론트엔드 (Next.js, 추후 생성)

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

## 작업 진행 방식 (Claude Code에게)

1. 새로운 기능 작업 전, 먼저 **간단한 계획(2~5줄)**을 제시하고 사용자 확인을 받는다
2. 큰 변경은 Plan 모드를 활용한다
3. MVP 범위(단어장)를 벗어나는 제안은 **"MVP 외 제안"이라고 명시**하고 진행 여부를 묻는다
4. 한 번에 너무 많은 파일을 생성하지 않는다. 작은 단위로 컨펌 받으며 진행
5. 설치/명령 실행 전, 무엇을 왜 실행하는지 한 줄 요약
6. 사용자는 Claude Code 초보임. 새 개념 처음 사용 시 한 줄 설명 추가
7. 한국어로 응답

## 용어

- 정처기 = 정보처리기사 (한국 IT 자격증)
- 검수 = AI가 생성한 단어 데이터를 관리자가 확인/수정하는 과정
