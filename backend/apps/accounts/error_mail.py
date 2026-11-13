"""운영에서 처리하지 못한 오류(500)가 나면 운영자에게 짧은 알림 메일을 보낸다.

Django 는 ADMINS 가 있으면 500 마다 AdminEmailHandler 로 메일을 보낸다
(django.utils.log.DEFAULT_LOGGING 의 mail_admins). 그대로 쓰지 않고 이 처리기로
바꾼 이유가 셋이다.

1. 발송량. 그대로 두면 DB 가 죽는 것처럼 모든 요청이 실패할 때 요청마다 한 통씩
   나간다. 메일은 Gmail API 로 나가고(gmail_api.py) Gmail 계정은 하루에 보낼 수
   있는 양이 정해져 있다(무료 계정은 대략 500통). 그 양을 오류 메일이 다 쓰면
   이메일 변경 확인처럼 회원에게 가야 하는 메일이 막힌다. 그래서 같은 오류는 한
   시간에 한 통, 모두 합쳐 한 시간에 5통, 하루 30통까지만 보낸다.
2. 개인정보. Django 의 기본 메일에는 요청 정보 전체(회원 번호, 접속 주소, 브라우저,
   주소의 값들, 폼으로 보낸 값, 오류 메시지)가 들어간다. 오류 메시지에는 "이 이메일은
   이미 있다" 처럼 이메일이 섞이기도 한다. 그래서 이 메일에는 오류 종류, 우리 코드의
   위치, 요청 방식, 영어 경로 이름이 아닌 조각을 가린 주소(masked_path), 시각만
   넣는다(처리방침 2절 사목). 오류
   메시지는 운영 로그에서 본다(아래).
3. 처리한 실패. 메일 발송이 실패하면 뷰가 502 로 답하는데(accounts/views.py),
   Django 는 이것도 ERROR 로 남긴다. 그때 오류 메일을 보내면 이미 실패한 Gmail 을
   한 번 더 기다려, 그 요청이 최악 24초쯤 더 늘어진다(gmail_api.TIMEOUT 주석).
   그래서 예외가 처리되지 않고 올라온 기록(exc_info 가 있는 것)만 보낸다.
   django.security.* 는 요청이 이상해서 400 으로 답한 것이라(너무 많은 칸, 잘못된
   Host 등) 우리가 고칠 서버 오류가 아니므로 뺀다.

운영 로그(Railway)에는 메일과 별도로, 걸러지는 것까지 매번 "[서버 오류]" 한 줄과
예외가 지난 파일·줄·코드를 남긴다. Django 기본 설정은 운영(DEBUG 꺼짐)에서 500 의
추적 내용을 어디에도 쓰지 않아서, 이것이 없으면 걸러진 오류나 운영 데이터에서만 나는
오류는 흔적이 없다.

그 한 줄에는 처리방침 v3 시행일(MESSAGE_FROM)부터 오류 메시지도 싣는다. 종류와 자리만
으로는 "이미 있는 이메일" 인지 "DB 연결이 끊겼다" 인지 몰라 로컬에서 같은 요청을 다시
만들어야 했다. 메시지에 이메일이 섞일 수 있다는 것은 처리방침 2·3·4절에 적었다. 메일에는
계속 넣지 않는다. 메일은 운영자 Gmail 보낸편지함에 30일 남아, 처리방침이 운영 로그에
적은 기간(Railway 7일)과 다르다. 변수 값은 로그에도 싣지 않는다.

세는 곳을 DB 캐시가 아니라 이 프로세스의 메모리에 둔다. 오류가 몰리는 흔한 까닭이
DB 장애라, 세는 곳이 DB 면 그때 거르지 못해 가장 많이 보내게 된다. gunicorn
작업자(Procfile --workers 2)마다 따로 세므로 실제 상한은 작업자 수만큼 곱해지고
(하루 최대 60통), 재시작하면 처음부터 센다.

settings.LOGGING 이 Django 기본 설정을 그대로 복사한 뒤 mail_admins 의 class 만
이것으로 바꾼다. DEBUG 일 때 안 보내는 조건(require_debug_false)과 ERROR 이상만
보내는 조건은 기본 설정 그대로다.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import threading
import time
import traceback
from datetime import date
from logging import LogRecord

from django.conf import settings
from django.core.mail import mail_admins
from django.utils import timezone
from django.utils.log import AdminEmailHandler

# 같은 오류를 다시 알리기까지의 시간과 상한.
WINDOW_SECONDS = 60 * 60
MAX_PER_WINDOW = 5
DAY_SECONDS = 24 * 60 * 60
MAX_PER_DAY = 30

# 알리지 않는 로거 앞부분. 요청이 이상해서 400 으로 답한 것들이다.
SKIP_LOGGER_PREFIX = "django.security."

# 주소에서 그대로 남기는 조각. 영어 소문자로 된 짧은 이름(api, vocab, words)뿐이다.
# 나머지(숫자, 이메일, 한글 이름, 토큰)는 모두 가린다. "가릴 것을 고르는" 쪽으로
# 짜면 새 경로가 이메일이나 이름을 주소로 받는 순간 그대로 메일에 실린다.
KEEP_SEGMENT = re.compile(r"[a-z][a-z_-]{0,23}")

# 그대로 쓰는 요청 방식. 요청 방식은 보내는 쪽이 아무 글자나 넣을 수 있다.
KNOWN_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# 운영 로그에 오류 메시지를 싣기 시작하는 날(한국 시간). 처리방침 14절이 "바꾸면 시행
# 7일 전부터 서비스 화면에 알린다" 고 약속해서, 이 기능을 머지한 날(공고일)부터 7일
# 뒤다. 처리방침 v3 의 시행일이고 14절에 글자로 적혀 있다(legal-pages.test.mts 가
# 견준다). v4 를 v3 시행 전에 공고해 LegalDoc.tsx 의 PRIVACY_CHANGE.effective 는 v4
# 시행일(11-20)이다. 그쪽에 맞춰 이 날짜를 옮기지 않는다.
# ponytail: 날짜로 켜는 문이다. 시행일이 지나면 이 상수와 short_message 의 날짜 비교를
# 지운다. 그때 테스트의 날짜 고정(tests_error_mail.py 의 messages_on/off,
# tests_error_mail_dynamic.py 의 StderrCarriesNoValuesTest.setUp 과 MESSAGE_FROM 을
# 쓰는 아래쪽 절들), legal-pages.test.mts 의 MESSAGE_FROM 대조와 V3_EFFECTIVE·V3_GATES_LIVE,
# LegalDoc.tsx 의 PRIVACY_CHANGE 주석 중 "서버의 날짜 문" 문단도 같이 지운다.
# `grep -rn MESSAGE_FROM` 로 찾는다.
MESSAGE_FROM = date(2026, 11, 19)

# 운영 로그 한 줄에 싣는 오류 메시지의 최대 글자 수. SQL 전체가 든 DB 오류처럼 긴
# 메시지가 Railway 로그 화면을 덮지 않게 자른다.
MESSAGE_LIMIT = 300


def code_place(record: LogRecord) -> str:
    """예외가 지난 마지막 우리 코드 자리(파일:줄). 우리 코드가 없으면 가장 깊은 자리.

    가장 깊은 자리만 쓰면 psycopg·DRF·Django 안에서 난 예외가 어느 뷰에서 났든 같은
    자리가 되어, 서로 다른 버그가 한 묶음으로 가려진다.
    """
    tb = record.exc_info[2] if record.exc_info else None
    root = str(settings.BASE_DIR)
    deepest = ours = ""
    while tb is not None:
        filename = tb.tb_frame.f_code.co_filename
        place = f"{filename}:{tb.tb_lineno}"
        deepest = place
        if filename.startswith(root) and "site-packages" not in filename:
            ours = os.path.relpath(filename, root).replace(os.sep, "/") + f":{tb.tb_lineno}"
        tb = tb.tb_next
    if ours:
        return ours
    # 라이브러리 안에서만 났다. 서버의 설치 경로는 빼고 꼬리만 남긴다.
    if "site-packages" in deepest:
        return deepest.split("site-packages")[-1].lstrip("\\/").replace("\\", "/")
    return os.path.basename(deepest)


def exception_name(record: LogRecord) -> str:
    exc = record.exc_info[1] if record.exc_info else None
    return type(exc).__qualname__ if exc is not None else "오류"


def signature(record: LogRecord) -> str:
    """같은 오류인지 가르는 값. 예외 종류와 우리 코드의 마지막 자리.

    주소에 단어 번호처럼 바뀌는 값이 들어가도 같은 버그는 한 묶음이 된다.
    """
    exc = record.exc_info[1] if record.exc_info else None
    kind = f"{type(exc).__module__}.{type(exc).__qualname__}" if exc is not None else record.name
    raw = f"{kind}@{code_place(record)}"
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def masked_path(record: LogRecord) -> str:
    """요청 주소에서 영어 소문자 이름이 아닌 조각을 모두 ":id" 로 가린다.

    회원·단어 번호, 사진 주소의 UUID, 확인 링크의 토큰, 혹시 주소에 들어온 이메일이나
    이름이 메일에 실리지 않게 한다. 쿼리 문자열은 아예 넣지 않는다.
    """
    request = getattr(record, "request", None)
    path = getattr(request, "path", "") or ""
    parts = [
        part if not part or KEEP_SEGMENT.fullmatch(part) else ":id" for part in path.split("/")
    ]
    return "/".join(parts)


def request_method(record: LogRecord) -> str:
    request = getattr(record, "request", None)
    method = (getattr(request, "method", "") or "").upper()
    return method if method in KNOWN_METHODS else "기타"


def short_message(record: LogRecord) -> str:
    """운영 로그에 싣는 오류 메시지. 한 줄로 펴고 MESSAGE_LIMIT 자에서 자른다.

    시행일 전이면 빈 글자다. 줄바꿈과 제어 문자를 빈칸으로 바꾸는 것은 길이 때문만이
    아니다. 메시지에 요청 값이 들어오면 줄바꿈 뒤에 "[서버 오류] ..." 를 이어 가짜 줄을
    만들거나, 터미널 색·글자 방향을 바꾸는 문자로 로그 화면을 어지럽힐 수 있다.

    이 메시지는 처리방침에 적은 기록이라 7일 남는다. 예외 메시지에 요청 본문을 통째로
    넣지 않는다. 넣으면 비밀번호가 그대로 남는다.
    """
    if timezone.localdate() < MESSAGE_FROM:
        return ""
    exc = record.exc_info[1] if record.exc_info else None
    if exc is None:
        return ""
    try:
        # 수 MB 짜리 메시지를 통째로 펴지 않게 먼저 넉넉히 자른다. 들여쓰기가 많은 SQL
        # 처럼 펴고 나면 300자보다 짧아질 수 있으니, 여기서 잘렸는지를 따로 기억한다.
        full = str(exc)
        raw = full[: MESSAGE_LIMIT * 4]
        cut = len(full) > len(raw)
    except Exception:
        # __str__ 이 터지는 예외도 있다. 여기서 터지면 "[서버 오류]" 줄까지 못 남긴다.
        return "(메시지를 읽지 못함)"
    text = " ".join("".join(c if c.isprintable() else " " for c in raw).split())
    if cut or len(text) > MESSAGE_LIMIT:
        text = text[: MESSAGE_LIMIT - 1] + "…"
    return text


def stack_without_values(record: LogRecord) -> str:
    """예외가 지난 파일·줄·코드만. 오류 메시지와 변수 값은 없다.

    운영 로그(Railway)에 남겨, 같은 오류라 메일이 걸러진 경우나 운영 데이터에서만
    나는 오류도 어느 길로 왔는지 볼 수 있게 한다. 메시지는 "[서버 오류]" 줄에
    따로 싣는다(short_message).
    """
    tb = record.exc_info[2] if record.exc_info else None
    return "".join(traceback.format_tb(tb)) if tb is not None else ""


class ThrottledAdminEmailHandler(AdminEmailHandler):
    """처리하지 못한 예외만, 같은 것은 한 시간에 한 통, 짧은 알림으로 보낸다."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # 셈은 이 잠금으로만 지킨다. 처리기 잠금은 쓰지 않는다(handle 주석).
        self._lock = threading.Lock()
        # 서명 -> 그 서명으로 마지막에 보낸 시각
        self._last_sent: dict[str, float] = {}
        # 하루 동안 보낸 시각들(한 시간 상한도 여기서 센다)
        self._sent_times: list[float] = []

    def should_send(self, record: LogRecord, now: float | None = None) -> bool:
        if record.name.startswith(SKIP_LOGGER_PREFIX):
            return False
        if not (record.exc_info and record.exc_info[1] is not None):
            return False
        now = time.monotonic() if now is None else now
        key = signature(record)
        with self._lock:
            # 지난 것을 치운다. 오래 켜 둔 작업자에서 끝없이 늘지 않게 한다.
            self._sent_times = [t for t in self._sent_times if now - t < DAY_SECONDS]
            self._last_sent = {k: t for k, t in self._last_sent.items() if now - t < WINDOW_SECONDS}
            if key in self._last_sent:
                return False
            if len(self._sent_times) >= MAX_PER_DAY:
                return False
            if sum(1 for t in self._sent_times if now - t < WINDOW_SECONDS) >= MAX_PER_WINDOW:
                return False
            # 보내기 전에 센다. 보내다 실패해도 한 통으로 친다 - Gmail 이 끊겼을 때 같은
            # 오류마다 끊긴 Gmail 을 계속 두드리지 않으려는 것이다.
            self._last_sent[key] = now
            self._sent_times.append(now)
            return True

    def handle(self, record: LogRecord) -> bool | LogRecord:
        """logging.Handler.handle 에서 처리기 잠금만 뺀 것.

        원래 handle 은 emit 전체를 처리기 잠금 안에서 돈다. 여기서는 그 안에 Gmail 발송
        (최악 24초)이 들어간다. gunicorn 을 스레드 방식(--threads)으로 띄우면 같은
        프로세스의 다른 스레드가 500 이나 잘못된 Host(400)를 기록하려다 그동안 기다려,
        그 요청의 응답까지 늦어진다. 셈은 self._lock 이 지키고, 표준 오류에는 한 기록을
        write 한 번으로 쓰므로 처리기 잠금을 잡지 않는다.
        """
        rv = self.filter(record)
        # 파이썬 3.12 부터 거름망이 기록을 바꿔 돌려줄 수 있다(운영은 3.13).
        if isinstance(rv, LogRecord):
            record = rv
        if rv:
            self.emit(record)
        return rv

    def emit(self, record: LogRecord) -> None:
        # 이 안에서 난 예외를 밖으로 내보내지 않는다(로깅 처리기의 관례). 내보내면
        # Django 가 그것을 새 500 으로 다시 기록해 Gmail 을 한 번 더 부른다.
        #
        # 로깅 처리기의 관례인 self.handleError 는 쓰지 않는다. 그것은 이 예외에 이어진
        # 원래 요청 예외의 메시지와, 가리지 않은 원래 주소(기록의 인자)를 표준 오류에
        # 그대로 찍는다. 주소 가리기, 메시지 길이 상한, 시행일 문을 모두 건너뛴다.
        # 그래서 예외 종류 이름 한 줄만 남긴다.
        try:
            self._emit(record)
        except Exception as exc:
            try:
                # 어디서 났는지(파일:줄)는 코드 위치라 값이 아니므로 붙인다. 이 모듈 자체의
                # 버그라면 이것이 없을 때 찾을 길이 없다.
                frames = traceback.extract_tb(exc.__traceback__)
                where = (
                    f" {os.path.basename(frames[-1].filename)}:{frames[-1].lineno}"
                    if frames
                    else ""
                )
                sys.stderr.write(f"[오류 알림 실패] {type(exc).__qualname__}{where}\n")
            except Exception:
                pass

    def _emit(self, record: LogRecord) -> None:
        if record.name.startswith(SKIP_LOGGER_PREFIX):
            return
        if not (record.exc_info and record.exc_info[1] is not None):
            return
        method = request_method(record)
        path = masked_path(record)
        # 운영 로그에는 걸러지는 것까지 매번 남긴다. 시행일부터는 오류 메시지도 싣는다.
        line = f"[서버 오류] {exception_name(record)} {method} {path}"
        message = short_message(record)
        if message:
            line += f" - {message}"
        sys.stderr.write(f"{line}\n{stack_without_values(record)}")
        # 받을 사람이 없으면(로컬·CI) 세지도 않는다.
        if not settings.ADMINS or not self.should_send(record):
            return
        name = exception_name(record)
        place = code_place(record)
        subject = self.format_subject(f"{name} {method} {path}".strip())
        when = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S %Z")
        body = (
            "서버에서 처리하지 못한 오류가 났습니다.\n\n"
            f"종류: {name}\n"
            f"우리 코드의 마지막 위치: {place}\n"
            f"요청: {method} {path}\n"
            f"시각: {when}\n\n"
            "같은 오류는 한 시간 동안 다시 알리지 않습니다.\n"
            "이 메일에는 회원 정보와 오류 메시지를 넣지 않습니다. 같은 시각의 운영 로그\n"
            '(Railway web 서비스)에 "[서버 오류]" 로 시작하는 호출 경로가 있습니다.\n'
        )
        mail_admins(subject, body, fail_silently=True, connection=self.connection())
