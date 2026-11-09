"""DRF 예외 처리."""

from __future__ import annotations

from rest_framework.exceptions import ErrorDetail, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc: Exception, context: dict) -> Response | None:
    """시도 제한에 걸렸을 때의 문구만 서비스 말투로 바꾼다.

    DRF 기본 문구는 "요청이 제한되었습니다. 54 초 후에 사용 가능합니다." 다.
    Retry-After 헤더는 exc.wait 으로 만들어지므로 그대로 나간다.
    """
    if isinstance(exc, Throttled):
        when = "잠시" if exc.wait is None else f"{exc.wait}초"
        exc.detail = ErrorDetail(
            f"시도가 너무 많습니다. {when} 뒤에 다시 해주세요.",
            code=exc.default_code,
        )
    return drf_exception_handler(exc, context)
