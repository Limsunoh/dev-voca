"""배포 확인 주소 /healthz.

Railway 는 서비스 설정의 Healthcheck Path 가 있으면, 새 배포를 띄운 뒤 그 주소가
200 을 줄 때까지 옛 배포로 계속 요청을 보낸다. 이 경로가 없을 때는 새 컨테이너가
켜지자마자 옛 것을 내려서, migrate·collectstatic·gunicorn 이 뜨는 동안(11-11 배포
에서 3.5초) 들어온 요청이 실패했다.

뷰가 아니라 미들웨어 맨 앞에 두는 이유: Railway 는 이 요청을 http 로, Host 를
healthcheck.railway.app 으로 보낸다. 뒤에 있는 SecurityMiddleware 는 운영에서 http
요청을 https 로 돌리며(301) 그 전에 Host 를 ALLOWED_HOSTS 와 맞춰 본다. 그 Host 는
목록에 없으니 400 이 되고, 목록에 넣어도 301 이라 둘 다 200 이 아니다. 그래서 둘보다
앞에서 답한다. 다른 주소는 그대로 지나간다.

DB 는 보지 않는다. 시작 명령에서 migrate 가 gunicorn 보다 먼저 돌아서, DB 에 못
붙으면 이 주소가 불리기 전에 배포가 실패한다.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

HEALTHZ_PATH = "/healthz"


def healthz_middleware(
    get_response: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    def middleware(request: HttpRequest) -> HttpResponse:
        if request.path == HEALTHZ_PATH:
            return HttpResponse("ok", content_type="text/plain")
        return get_response(request)

    return middleware
