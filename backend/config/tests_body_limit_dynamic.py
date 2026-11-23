"""요청 본문 상한(config/body_limit.py)을 실제 WSGI 경로로 깨뜨려 본다.

tests_body_limit 은 미들웨어 함수와 머리만 큰 요청을 본다. 여기서는
  - 진짜 큰 multipart 파일을 보내도 본문을 한 바이트도 읽지 않고, 임시 파일도 만들지 않는다.
  - Content-Length 를 int() 가 읽는 이상한 꼴(+, 공백, 밑줄, 전각 숫자)로 적어도 413 이다.
    미들웨어와 Django 가 같은 int() 로 읽으므로, 미들웨어가 0 으로 보고 Django 는 크게 읽는
    틈이 없다.
  - int() 가 못 읽는 값이면 Django 도 본문을 비어 있는 것으로 봐 아무것도 읽지 않는다.
  - 상한 바로 아래의 사진 업로드는 413 이 아니다(뷰까지 간다).
"""

from __future__ import annotations

import io
from unittest import mock

from apps.accounts.models import AVATAR_PHOTO_MAX_BYTES, LoginToken
from apps.accounts.tests import PHOTO_URL
from apps.learning.tests_mistakes import make_user
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.core.handlers.wsgi import WSGIHandler
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from django.test import TestCase

from config.body_limit import MAX_BODY_BYTES


class CountingInput(io.RawIOBase):
    """wsgi.input 대역. 읽힌 바이트 수를 센다. 내용은 끝없는 'x' 다."""

    def __init__(self) -> None:
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        size = 64 * 1024 if size is None or size < 0 else size
        self.bytes_read += size
        return b"x" * size

    def readline(self, size: int = -1) -> bytes:
        return self.read(size if size and size > 0 else 1024)


class RealWsgiCase(TestCase):
    """테스트 클라이언트를 거치지 않고 WSGIHandler 에 environ 을 직접 넣는다."""

    def setUp(self) -> None:
        cache.clear()
        self.user = make_user("업로더")
        self.key = LoginToken.objects.create(user=self.user).key

    def call(self, content_length: str, path: str = PHOTO_URL) -> tuple[int, CountingInput]:
        stream = CountingInput()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": path,
            "SCRIPT_NAME": "",
            "QUERY_STRING": "",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "CONTENT_TYPE": "multipart/form-data; boundary=BoUnDaRy",
            "CONTENT_LENGTH": content_length,
            "HTTP_AUTHORIZATION": f"Token {self.key}",
            "wsgi.input": stream,
            "wsgi.url_scheme": "http",
            "wsgi.errors": io.StringIO(),
            "wsgi.version": (1, 0),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }
        statuses: list[str] = []
        # 요청이 끝나면 DB 연결을 닫는 신호를 잠시 뗀다. 테스트 클라이언트도 같은 일을 한다
        # (django.test.client.ClientHandler). 안 떼면 TestCase 의 트랜잭션 연결이 닫힌다.
        request_started.disconnect(close_old_connections)
        request_finished.disconnect(close_old_connections)
        try:
            response = WSGIHandler()(environ, lambda status, headers, *a: statuses.append(status))
            response.close()
        finally:
            request_started.connect(close_old_connections)
            request_finished.connect(close_old_connections)
        return int(statuses[0].split()[0]), stream


class OversizedBodyIsNeverReadTest(RealWsgiCase):
    def test_상한을_넘는_multipart_는_한_바이트도_안_읽고_413(self):
        with mock.patch.object(TemporaryFileUploadHandler, "new_file") as new_file:
            status, stream = self.call(str(MAX_BODY_BYTES + 1))

        self.assertEqual(status, 413)
        self.assertEqual(stream.bytes_read, 0)
        new_file.assert_not_called()

    def test_int_가_읽는_이상한_꼴도_413(self):
        """미들웨어가 0 으로 보고 Django 는 크게 읽으면 상한이 뚫린다. 둘 다 int() 라 같아야 한다."""
        big = MAX_BODY_BYTES + 1
        fullwidth = str(big).translate(str.maketrans("0123456789", "０１２３４５６７８９"))
        for value in (f"+{big}", f" {big} ", f"{big:_}", fullwidth, "9" * 30):
            with self.subTest(value=value):
                status, stream = self.call(value)
                self.assertEqual(status, 413)
                self.assertEqual(stream.bytes_read, 0)

    def test_int_가_못_읽는_값이면_Django_도_본문을_안_읽는다(self):
        """미들웨어가 넘겨 보내는 값. 그때 Django 가 본문을 읽으면 상한 없이 받는 길이 된다."""
        for value in ("", "abc", "1e9", "0x7fffffff", "-1"):
            with self.subTest(value=value):
                status, stream = self.call(value)
                self.assertEqual(status, 400)
                self.assertEqual(stream.bytes_read, 0)

    def test_대조군_상한_아래면_본문을_실제로_읽는다(self):
        """이게 0 이면 위 테스트들의 '0 바이트' 는 대역이 안 불린 것일 뿐이다."""
        status, stream = self.call("100")
        self.assertEqual(status, 400)
        self.assertGreater(stream.bytes_read, 0)


class OversizedUploadThroughClientTest(TestCase):
    """테스트 클라이언트로 진짜 큰 파일을 실어 보낸다. 파서가 아예 불리지 않아야 한다."""

    def setUp(self) -> None:
        cache.clear()
        self.user = make_user("큰사진")
        self.key = LoginToken.objects.create(user=self.user).key

    def upload(self, size: int):
        photo = SimpleUploadedFile("big.png", b"\x89PNG" + b"\0" * (size - 4), "image/png")
        return self.client.post(
            PHOTO_URL, {"photo": photo}, HTTP_AUTHORIZATION=f"Token {self.key}"
        )

    def test_큰_파일은_파서도_임시_파일도_안_거친다(self):
        with (
            mock.patch("django.http.request.MultiPartParser") as parser,
            mock.patch.object(TemporaryFileUploadHandler, "new_file") as new_file,
        ):
            res = self.upload(MAX_BODY_BYTES + 1)

        self.assertEqual(res.status_code, 413)
        parser.assert_not_called()
        new_file.assert_not_called()

    def test_로그인_없이도_413_이고_401_보다_먼저다(self):
        photo = SimpleUploadedFile("big.png", b"\0" * (MAX_BODY_BYTES + 1), "image/png")
        res = self.client.post(PHOTO_URL, {"photo": photo})
        self.assertEqual(res.status_code, 413)

    def test_사진_상한_크기의_업로드는_뷰까지_간다(self):
        """본문 상한이 사진 상한을 잘라 먹으면 정상 사용자가 413 을 본다."""
        res = self.upload(AVATAR_PHOTO_MAX_BYTES)
        self.assertNotEqual(res.status_code, 413)
        self.assertEqual(res.status_code, 400, res.content[:200])
