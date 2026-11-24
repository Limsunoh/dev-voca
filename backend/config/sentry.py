"""운영에서 난 오류를 Sentry 로 보낸다.

SENTRY_DSN 이 있을 때만 켠다(Railway 의 web 과 cleanup). 로컬과 CI 에는 없어서 꺼진다.
Gmail 오류 메일(apps/accounts/error_mail.py)은 그대로 둔다. Sentry 가 막혀도 그쪽 알림은 온다.

보내는 것은 오류 종류, 메시지, 호출 경로(파일·줄·코드), 가린 요청 주소, 요청 방식, 브라우저
이름(User-Agent)이다. 보내지 않는 것과 이유:

- SQL 에 넣은 값. 회원 이메일처럼 개인정보가 실린다. 로그인 토큰은 지문(sha256)으로 바꿔
  조회해서 실려도 로그인에는 못 쓴다(2026-11-25 전에는 원문으로 조회했다).
  data_collection 을 넘기면 SDK 가 빠진 칸을 "수집" 으로 채우므로(database_query_data 기본
  True) 아래에서 하나도 빼지 않고 끈다.
- 변수 값. 기본값은 호출 경로마다 지역 변수를 싣는다. 비밀번호를 받은 뷰에서 나면 그대로 간다.
- 요청 헤더. Next 가 붙이는 X-Next-Relay 는 비밀값(RELAY_SECRET)이고 X-Next-Client-Ip 는
  사용자 IP 다. SDK 의 민감 이름 목록은 표준 이름뿐이라 이 둘을 모른다. User-Agent 만 남긴다.
- 주소의 번호·토큰. 이메일 변경 확인처럼 경로에 토큰이 들어가는 주소가 있다. 오류 메일과
  같은 규칙(mask_path)으로 가리고 쿼리 문자열은 버린다.
- 요청 본문, 쿠키, 사용자 정보와 IP.

수집을 끄는 것(data_collection)과 나가기 직전에 지우는 것(scrub)을 둘 다 둔다. data_collection 을
쓰면 SDK 기본 거름망(EventScrubber)은 꺼지고 다시 켤 수도 없어서, 그 몫을 scrub 이 한다.

django.security.* (잘못된 Host 등으로 400 을 준 기록)는 보내지 않는다. 봇이 하루에도 수십 번
만들고 우리가 고칠 오류가 아니다. 오류 메일도 같은 이유로 뺀다.

성능 측정(traces_sample_rate)은 켜지 않는다. 무료 요금제 한도를 오류에만 쓴다.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from sentry_sdk.integrations.logging import ignore_logger

# 요청 헤더 중 남기는 것. 어느 기기·브라우저에서 났는지만 본다.
KEEP_HEADERS = {"user-agent"}


def scrub(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Sentry 로 나가기 직전의 오류에서 위 머리 주석의 값들을 지운다."""
    # settings 를 읽는 중에 앱 모듈을 불러오지 않게 여기서 가져온다.
    from apps.accounts.error_mail import mask_path

    request = event.get("request")
    if isinstance(request, dict):
        for key in ("cookies", "data", "query_string", "env"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in KEEP_HEADERS}
        url = request.get("url")
        if isinstance(url, str):
            parts = urlsplit(url)
            request["url"] = urlunsplit((parts.scheme, parts.netloc, mask_path(parts.path), "", ""))
    event.pop("user", None)

    # SQL 기록은 문장만 남기고 넣은 값(db.params)은 버린다.
    crumbs = event.get("breadcrumbs")
    values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
    for crumb in values if isinstance(values, list) else []:
        if isinstance(crumb, dict) and crumb.get("category") == "query":
            crumb.pop("data", None)
    return event


def init() -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    ignore_logger("django.security.*")
    sentry_sdk.init(
        dsn=dsn,
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "allowlist", "terms": ["user-agent"]}},
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "database_query_data": False,
            "queues": False,
            "graphql": {"document": False, "variables": False},
            "gen_ai": {"inputs": False, "outputs": False},
            "stack_frame_variables": False,
        },
        include_local_variables=False,
        before_send=scrub,
        # Railway 가 배포마다 넣어 준다. 어느 커밋에서 났는지 Sentry 화면에 나온다.
        release=os.getenv("RAILWAY_GIT_COMMIT_SHA") or None,
        # Railway 밖(로컬 .env 에 DSN 을 넣은 경우)에서 보낸 것은 운영과 섞이지 않게 local 로 단다.
        environment=os.getenv("RAILWAY_ENVIRONMENT_NAME") or "local",
    )
