"""요청 본문 크기 상한(config/body_limit.py).

계약:
  - Content-Length 가 MAX_BODY_BYTES 를 넘으면 본문을 읽기 전에 413 이다. 로그인 없이 부르는
    채점 API 와, CSRF 검사가 본문을 먼저 읽는 Admin 로그인 화면도 같다.
  - 머리가 없거나 숫자가 아니면 그대로 넘긴다. Django 도 그때는 본문을 비어 있는 것으로 본다.
  - 가장 큰 정상 요청(프로필 사진 상한 + multipart 경계)이 상한 안에 들어간다.
"""

from __future__ import annotations

from apps.accounts.models import AVATAR_PHOTO_MAX_BYTES
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from config.body_limit import MAX_BODY_BYTES, body_limit_middleware

# multipart 경계와 다른 폼 칸 몫. 사진 하나 올리는 요청에서 수백 바이트면 되지만 넉넉히 둔다.
MULTIPART_ROOM = 64 * 1024


class BodyLimitMiddlewareTest(SimpleTestCase):
    def setUp(self) -> None:
        self.middleware = body_limit_middleware(lambda request: HttpResponse("ok"))

    def status_for(self, content_length: str | None) -> int:
        request = RequestFactory().post("/api/vocab/words/grade/")
        if content_length is None:
            request.META.pop("CONTENT_LENGTH", None)
        else:
            request.META["CONTENT_LENGTH"] = content_length
        return self.middleware(request).status_code

    def test_상한을_넘으면_413(self):
        self.assertEqual(self.status_for(str(MAX_BODY_BYTES + 1)), 413)
        self.assertEqual(self.status_for(str(10**12)), 413)

    def test_상한까지는_넘긴다(self):
        self.assertEqual(self.status_for(str(MAX_BODY_BYTES)), 200)
        self.assertEqual(self.status_for("0"), 200)

    def test_머리가_없거나_숫자가_아니면_넘긴다(self):
        for value in (None, "", "abc", "1e9", "-1"):
            with self.subTest(value=value):
                self.assertEqual(self.status_for(value), 200)

    def test_사진_상한이_본문_상한_안에_들어간다(self):
        # 사진 상한을 올리면 여기가 먼저 깨진다. 본문 상한도 같이 올린다.
        self.assertLess(AVATAR_PHOTO_MAX_BYTES + MULTIPART_ROOM, MAX_BODY_BYTES)


class BodyLimitWiringTest(TestCase):
    """미들웨어 목록에 실제로 걸려 있는지 본다. 본문은 보내지 않고 머리만 크게 적는다."""

    def test_로그인_없이_부르는_채점_API_는_413(self):
        res = self.client.generic(
            "POST",
            "/api/vocab/words/grade/",
            b"{}",
            content_type="application/json",
            CONTENT_LENGTH=str(MAX_BODY_BYTES + 1),
        )
        self.assertEqual(res.status_code, 413)
        # SecurityMiddleware 뒤에 있어 413 에도 보안 머리가 붙는다.
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")

    def test_Admin_로그인도_CSRF_검사보다_먼저_413(self):
        res = self.client.generic(
            "POST",
            "/admin/login/",
            b"username=a",
            content_type="application/x-www-form-urlencoded",
            CONTENT_LENGTH=str(MAX_BODY_BYTES + 1),
        )
        self.assertEqual(res.status_code, 413)
