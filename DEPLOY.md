# 배포 메모

Railway 기준. 다른 플랫폼도 대부분 같은 값이 필요하다.

## 시작 명령

```
python backend/manage.py migrate --noinput && python backend/manage.py collectstatic --noinput && gunicorn --chdir backend config.wsgi --bind 0.0.0.0:$PORT --workers 2
```

**지금 이 값은 저장소가 아니라 서비스 설정에 있다** - Settings > Deploy >
Custom Start Command. 거기에 값이 있으면 `Procfile` 은 무시된다. 저장소의
`Procfile` 은 같은 내용을 적어두기만 한 것이고, 고쳐도 배포는 안 바뀐다.

현재 값 확인:

```
railway status --json    # serviceInstances ... startCommand
```

**`migrate` 가 그 한 줄 안에 들어 있어야 한다.** 빠지면 마이그레이션이
도는 곳이 하나도 없어진다. 대시보드를 고칠 때 같이 지우기 쉬운 자리다.

### release: 는 쓰지 않는다

`release:` 로 적어둔 것은 실행되지 않았고, 실행되지 않았다는 신호도
없었다. 2026-08-13 에 `release: ... createcachetable` 이 그랬다 - 캐시
테이블이 한 번도 만들어지지 않아 구글 로그인이 배포 직후부터 500 이었다.
조회 API 는 멀쩡해서 배포 후 확인표가 초록이었다.

**배포마다 돌아야 하는 것은 시작 명령 한 줄에 넣거나, 마이그레이션으로
옮긴다.** 마이그레이션 쪽이 낫다 - 대시보드 값은 저장소 밖이라 빠져도
아무도 모른다.

### Procfile 을 고칠 일이 생기면

**주석을 넣지 않는다.** 2026-08-04 에 `#` 줄이 셸 명령으로 넘어가
`command not found` 가 반복됐다. 그때는 Custom Start Command 를 설정하기
전이라 Procfile 이 실제로 읽히고 있었다. 즉 "무시된다" 는 지금 설정
상태에서만 참이고, 설정을 지우면 다시 읽힌다. 설명은 이 파일에 적는다.

`collectstatic` 은 gunicorn 앞, 같은 줄에 둔다. 다른 컨테이너에서 모으면
거기서 만든 staticfiles/ 가 web 으로 전달되지 않는다.

### 레플리카를 늘릴 때

`migrate` 가 시작 명령 안에 있으므로 인스턴스마다 돈다. 2개 이상으로
올리면 동시에 돌아 한쪽이 `already exists` 로 죽을 수 있다(재시작하면
풀리지만 부팅이 한 번 실패한다). 늘릴 거면 그때 `migrate` 를 시작 명령에서
빼고 별도 단계로 옮긴다.

## 환경변수

시작 명령 하나가 마이그레이션부터 gunicorn 까지 다 하므로, 서비스에 한 번
넣으면 된다.

| 변수 | 값 | 없으면 |
|---|---|---|
| `DJANGO_SECRET_KEY` | 랜덤 50자 | 기동 실패 (의도된 가드) |
| `DJANGO_ALLOWED_HOSTS` | `xxx.up.railway.app` (스킴 없이) | 기동 실패 |
| `DJANGO_DEBUG` | `0` | 에러 페이지에 소스 노출 |
| `DATABASE_URL` | PostgreSQL 추가 시 자동 | 로컬 기본값을 침 |

SECRET_KEY 생성:

```
python backend/manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

마이그레이션에도 `ALLOWED_HOSTS` 가 필요한 이유: 마이그레이션은 HTTP 요청을
받지 않지만, Django 가 settings 를 통째로 로드하면서 가드에 걸린다. 즉 이 값이
없으면 gunicorn 이 아니라 그 앞의 `migrate` 에서 멈춘다.

## 배포 후 확인

| 경로 | 기대 |
|---|---|
| `/` | 404 (백엔드에 루트 페이지가 없다. 정상) |
| `/admin/` | 200 |
| `/api/vocab/` | 200 |
| `/api/vocab/words/` | 200 |
| `POST /api/accounts/google/` (본문 `{}`) | **400** |
| `POST /api/accounts/login/` (없는 계정) | **400** |

`/admin/` 이 200 인데 `/api/vocab/words/` 가 500 이면 vocab 마이그레이션이
안 돈 것이다 - 배포 로그의 `migrate` 부분을 본다.

**마지막 두 줄을 빼먹지 않는다.** 위 네 줄은 요청 제한을 거치지 않아
**캐시 테이블이 없어도 전부 200** 이다. 2026-08-13 에 정확히 그래서
초록으로 착각했다. 여기서 500 이 나오면 캐시 테이블을 의심한다.

```
H=https://<호스트>
curl -so /dev/null -w "google %{http_code}\n" -X POST $H/api/accounts/google/ \
  -H "Content-Type: application/json" -d '{}'
curl -so /dev/null -w "login  %{http_code}\n" -X POST $H/api/accounts/login/ \
  -H "Content-Type: application/json" -d '{"email":"nobody@example.com","password":"x"}'
```

**본문을 저렇게 맞춰야 하는 이유**가 있다. 이 두 줄이 확인하는 것은 딱
하나 - throttle 이 캐시 테이블에 접근하는 데 성공했다(500 이 아니다).
그런데 throttle 은 캐시 키를 못 만들면 캐시를 안 건드리고 그냥 통과한다.

- `login/` 은 이메일로 키를 만든다. **`email` 이 없으면 키가 `None` 이라
  캐시를 아예 안 친다** - 400 이 나와도 아무것도 검증하지 않은 것이다.
  없는 계정으로 보내면 400 이면서 캐시는 확실히 친다.
- `google/` 은 본문과 무관한 고정 키를 쓰므로 `{}` 로 충분하다. 그리고
  `{}` 면 코드 검사에서 먼저 400 이라 **구글로 실제 요청이 나가지 않는다.**
  `{"code":"x"}` 처럼 보내면 매번 구글에 실패 요청을 보내게 되고, 그때는
  키가 없거나 네트워크가 막혀도 똑같이 400 이라 의미를 읽을 수 없다.

**이 두 줄은 구글 로그인이 실제로 되는지는 증명하지 않는다.** 키가 비어
있어도 400 이다. 로그인이 되는지는 브라우저로 한 번 해봐야 안다.

## 계정 기능 첫 배포 (한 번만)

로그인 키를 username 에서 email 로 바꾸면서 사용자 모델을 갈아끼웠다
(`AUTH_USER_MODEL = "accounts.User"`). 이미 만들어진 DB 에는 **그냥
배포하면 마이그레이션이 시작하자마자 실패한다.**

```
django.db.migrations.exceptions.InconsistentMigrationHistory:
Migration admin.0001_initial is applied before its dependency
accounts.0001_initial on database 'default'.
```

Django 의 admin 앱이 사용자 모델에 의존하는데, 그 의존 대상이 바뀌면서
"admin 이 accounts 보다 먼저 적용됐다" 는 상태가 되기 때문이다. 코드로는
못 고치고 DB 쪽에서 풀어야 한다.

테스트는 매번 빈 DB 를 새로 만들어서 이 문제를 잡지 못한다.

### 순서가 중요하다

시작 명령의 `migrate` 가 gunicorn 앞에서 돈다. 즉 **DB 를 손보기 전에
배포하면 거기서 멈춰 컨테이너가 아예 뜨지 않는다.**

그리고 컨테이너가 못 뜨면 Railway 는 이전 이미지를 계속 서빙하므로,
그 상태에서 `railway ssh` 로 들어가면 **accounts 앱이 없는 옛 코드**에
붙는다. 거기서 `migrate` 를 쳐도 이 오류는 재현조차 안 되니 헷갈리지 말 것.

**DB 를 먼저 정리하고, 그다음 배포한다.**

### 방법 1: DB 를 비우고 다시 만든다 (권장)

계정이 아직 없고 단어·문장은 시드로 복원되므로 이쪽이 짧다.

**먼저 확인할 것**: 시드는 검수를 마친 항목만 넣는다. Admin 에서
`/admin/vocab/word/?is_reviewed__exact=0` 이 비어 있는지 보고, 검수 대기
중인 것이 있으면 그건 이 방법으로 사라지고 되돌릴 수 없다.

`flush` 로는 안 된다 — 테이블 구조와 `django_migrations` 기록이 남아
같은 오류가 이어진다. 스키마를 통째로 지운다.

```
railway connect Postgres
```

이 명령은 로컬에 `psql` 이 깔려 있어야 동작한다. 없으면 Railway
대시보드 > Postgres 서비스 > Data 탭의 쿼리 창에서 같은 SQL 을 친다.
```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

그 뒤 배포하면 `migrate` 가 처음부터 돈다. 이어서:

```
railway ssh --service web "python backend/manage.py seed_words"
railway ssh --service web "python backend/manage.py seed_sentences"
railway ssh --service web
# 붙은 뒤 셸에서: python backend/manage.py createsuperuser
```

### 방법 2: 데이터를 살린다

단어·문장을 다시 넣기 싫을 때. admin 관련만 걷어내고 다시 만들게 한다.

```
railway connect Postgres
```

이 명령은 로컬에 `psql` 이 깔려 있어야 동작한다. 없으면 Railway
대시보드 > Postgres 서비스 > Data 탭의 쿼리 창에서 같은 SQL 을 친다.
```sql
-- 테이블을 지운다. 외래키만 떼면 이후 migrate 가 만들 스키마와 어긋나고,
-- 테이블을 남긴 채 마이그레이션 기록만 지우면 "이미 존재한다" 로 터진다.
DROP TABLE django_admin_log;
DELETE FROM django_migrations WHERE app='admin';
```

그 뒤 배포하면 accounts 가 먼저 적용되고, admin 이 뒤따르며
`django_admin_log` 를 `accounts_user` 참조로 새로 만든다.

옛 `auth_user` 계정은 넘어오지 않으므로 슈퍼유저를 다시 만든다.

```
railway ssh --service web
# 붙은 뒤 셸에서: python backend/manage.py createsuperuser
```

### 배포 후 확인

`auth_user` 테이블은 고아로 남지만 무해하다. 아래만 확인한다.

| 확인 | 기대 |
|---|---|
| `/admin/` 로그인 | 이메일로 로그인된다 |
| `/admin/accounts/user/add/` | 계정 추가 화면이 뜬다 |
| Admin 에서 단어 수정 후 저장 | 500 이 안 난다(로그 외래키 확인) |
| `/api/vocab/words/` | 200, 566개 |

## 캐시 테이블

로그인·가입·구글 로그인의 시도 횟수를 DB 에 센다. 테이블은 마이그레이션
(`accounts/0002_throttle_cache_table`) 이 만드므로 따로 할 일은 없다.
이미 있으면 그냥 넘어간다.

배포 명령에 `createcachetable` 을 넣지 않고 마이그레이션에 둔 이유:
배포 설정은 저장소 밖에 있어서 빠져도 아무 신호가 없다. 실제로 그렇게
났었다 - `release:` 줄에만 적혀 있었고, 그 줄은 실행되지 않았다.

프로세스 메모리를 쓰지 않는 이유: 워커마다 따로 세서 실제 한도가 워커
수만큼 늘어나고, 재시작하면 0 으로 돌아간다.

테이블이 없으면 조회·문제풀기는 멀쩡하고 **가입·로그인·구글 로그인만**
500 이 난다. 요청 제한이 붙은 뷰가 그 셋뿐이기 때문이다 - 로그아웃과
`me/` 는 제한이 없어서 테이블이 없어도 멀쩡하다. 감지하려면 위
`## 배포 후 확인` 의 마지막 두 줄을 쳐야 한다.

테스트가 대신 봐주지 않는다. Django 테스트 러너가 테스트 DB 에 캐시
테이블을 알아서 만들어주기 때문에, 배포 절차에서 빠져 있어도 로컬은 늘
통과한다. `ThrottleCacheTableTest` 가 "테이블이 없으면 무엇이 죽는지"
까지는 고정하지만, **프로덕션에 실제로 적용됐는지는 확인표로만 안다.**

## 구글 로그인

환경변수가 **양쪽에** 필요하다. 한쪽만 넣으면 버튼은 보이는데 눌러도 안 된다.

| 어디 | 변수 | 왜 |
|---|---|---|
| Railway (백엔드) | `GOOGLE_CLIENT_ID` | 구글에 코드를 확인할 때 |
| Railway (백엔드) | `GOOGLE_CLIENT_SECRET` | 같이 보내야 한다. **프론트에는 넣지 않는다** |
| Vercel (프론트) | `GOOGLE_CLIENT_ID` | 구글 동의 화면 주소를 만들 때 |
| Vercel (프론트) | `APP_ORIGIN` | 아래 참고 |

`APP_ORIGIN` 은 `https://dev-voca.vercel.app` 처럼 스킴을 포함한 주소다.
없으면 요청에서 주소를 유추하는데, 프록시 뒤에서는 https 로 들어온 요청이
앱에는 http 로 보일 수 있다. 그러면 구글이 등록된 주소와 다르다며 거절하고,
사용자에게는 "구글 로그인을 마치지 못했습니다" 만 보여 원인을 찾기 어렵다.

### 구글 콘솔

Google Cloud Console > 사용자 인증 정보 > OAuth 클라이언트 ID(웹 애플리케이션)의
**승인된 리디렉션 URI** 에 아래를 등록한다. 글자 하나라도 다르면 거절당한다.

```
http://localhost:3000/api/auth/google/callback
https://dev-voca.vercel.app/api/auth/google/callback
```

첫 줄은 로컬 개발용이다. 도메인을 바꾸면 여기도 같이 바꾼다.

### 확인

| 확인 | 기대 |
|---|---|
| 로그인 화면의 "구글로 계속하기" | 구글 동의 화면으로 간다 |
| 계정 선택 후 | devvoca 로 돌아오고 머리말에 이름이 뜬다 |
| Admin 의 사용자 목록 | 그 계정이 보이고 비밀번호가 "사용 불가" 다 |

"구글 로그인을 마치지 못했습니다" 가 뜨면 이유는 Vercel 함수 로그에 있다.
`redirect_uri_mismatch` 면 위 URI 등록을, 500 이면 백엔드 로그를 본다.

## 아직 안 한 것

- HSTS (`SECURE_HSTS_SECONDS`) - 도메인 확정 후 짧은 값부터 켠다.
  브라우저가 기억해버려 되돌리기 어렵다.
- 레이트리밋 - 로그인·가입은 이메일 단위로 걸어뒀다. 나머지 조회 경로는
  모든 요청이 Next 서버 하나로 보여 IP 로 셀 수 없으니, 필요해지면
  Next 중계 쪽에 둔다.
- 프론트엔드 - Vercel 배포 시 `CORS_ALLOWED_ORIGINS` 에 도메인 추가.
- `ANTHROPIC_API_KEY` - AI 생성을 서버에서 돌릴 때만 필요. 로컬에서 돌려도 된다.
