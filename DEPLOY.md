# 배포 메모

Railway 기준. 다른 플랫폼도 대부분 같은 값이 필요하다.

## Procfile

```
release: python backend/manage.py migrate --noinput
web: python backend/manage.py collectstatic --noinput && gunicorn ...
```

**주석을 넣지 않는다.** Railway 는 Procfile 의 `#` 줄을 명령으로 넘겨서,
한글 주석이 그대로 셸에 전달돼 `command not found` 가 반복된다.
설명이 필요하면 이 파일에 적는다.

- `release` - 배포마다 1회, web 이 뜨기 전에 실행. 되돌릴 수 없는 DB 변경은 여기.
- `web` - collectstatic 을 gunicorn 앞에 둔다. release 는 별도 컨테이너라
  거기서 모은 staticfiles/ 가 web 으로 전달되지 않는다.

## 환경변수

`release` 와 `web` **양쪽 다** 필요하다. Railway 의 Shared Variables 를 쓰면
한 번만 넣어도 된다.

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

`release` 에도 `ALLOWED_HOSTS` 가 필요한 이유: 마이그레이션은 HTTP 요청을
받지 않지만, Django 가 settings 를 통째로 로드하면서 가드에 걸린다.

## 배포 후 확인

| 경로 | 기대 |
|---|---|
| `/` | 404 (백엔드에 루트 페이지가 없다. 정상) |
| `/admin/` | 200 |
| `/api/vocab/` | 200 |
| `/api/vocab/words/` | 200 |

`/admin/` 이 200 인데 `/api/vocab/words/` 가 500 이면 vocab 마이그레이션이
안 돈 것이다 - `release` 로그를 본다.

## 아직 안 한 것

- HSTS (`SECURE_HSTS_SECONDS`) - 도메인 확정 후 짧은 값부터 켠다.
  브라우저가 기억해버려 되돌리기 어렵다.
- 레이트리밋 - 공개 API 이므로 `AnonRateThrottle` 검토.
- 프론트엔드 - Vercel 배포 시 `CORS_ALLOWED_ORIGINS` 에 도메인 추가.
- `ANTHROPIC_API_KEY` - AI 생성을 서버에서 돌릴 때만 필요. 로컬에서 돌려도 된다.
