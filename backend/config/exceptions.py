"""DRF 예외 처리."""

from __future__ import annotations

import math

from rest_framework.exceptions import ErrorDetail, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _wait_text(wait: int | None) -> str:
    """기다릴 시간. 1분을 넘으면 분으로 올려 적는다(가입·로그인 IP 제한은 1시간 단위라
    "3412초" 처럼 나온다). 1분 단위 제한은 DRF 가 올려서 60 이 되므로 60 까지는 초로 둔다."""
    if wait is None:
        return "잠시"
    if wait <= 60:
        return f"{wait}초"
    return f"{math.ceil(wait / 60)}분"


def exception_handler(exc: Exception, context: dict) -> Response | None:
    """시도 제한에 걸렸을 때의 문구만 서비스 말투로 바꾼다.

    DRF 기본 문구는 "요청이 제한되었습니다. 54 초 후에 사용 가능합니다." 다.
    Retry-After 헤더는 exc.wait 으로 만들어지므로 그대로 나간다.
    """
    if isinstance(exc, Throttled):
        when = _wait_text(exc.wait)
        exc.detail = ErrorDetail(
            f"시도가 너무 많습니다. {when} 뒤에 다시 해주세요.",
            code=exc.default_code,
        )
    return drf_exception_handler(exc, context)
