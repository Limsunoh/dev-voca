"""요청 본문 크기 상한.

Django 는 파일 첨부(multipart)의 파일 부분을 DATA_UPLOAD_MAX_MEMORY_SIZE(2.5MB)로 세지
않는다. 그 값은 메모리에 올리는 폼 값만 센다. 파일은 크기와 상관없이 임시 파일로 디스크에
받아 둔 뒤에야 뷰가 거절할 수 있다. 그래서 상한이 없으면 로그인 없이 수 GB 를 보내 웹
작업자를 묶고 디스크를 채울 수 있었다. 본문을 읽는 곳이 뷰 앞에도 있다. Admin 로그인
화면은 CSRF 검사가 본문을 읽고, DRF 화면은 request.data 를 읽는 순간 받는다.

Content-Length 만 보면 된다. Django 는 Content-Length 만큼만 읽고, 그 머리가 없거나
숫자가 아니면 본문을 비어 있는 것으로 본다(django.core.handlers.wsgi.WSGIRequest 의
LimitedStream).

가장 큰 정상 요청은 프로필 사진이다(AVATAR_PHOTO_MAX_BYTES 5MB + multipart 경계).
사진 상한을 올리면 이 값도 같이 올린다. tests_body_limit 이 둘을 견준다.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

MAX_BODY_BYTES = 6 * 1024 * 1024


def body_limit_middleware(
    get_response: Callable[[HttpRequest], HttpResponse],
) -> Callable[[HttpRequest], HttpResponse]:
    def middleware(request: HttpRequest) -> HttpResponse:
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            return HttpResponse(
                "요청이 너무 큽니다.",
                status=413,
                content_type="text/plain; charset=utf-8",
            )
        return get_response(request)

    return middleware
