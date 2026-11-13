"""구글 버튼의 신분 토큰(credential)으로 로그인하는 길.

화면 아래 계정 창(FedCM)으로 로그인하면 페이지를 떠나지 않아, 코드 대신
구글이 브라우저에 준 신분 토큰이 온다. 구글을 실제로 부르지 않고 확인 주소
(tokeninfo)의 응답을 흉내 낸다.

막아야 하는 것:
- 다른 사이트용으로 발급된 토큰(aud 가 다름)으로 들어오기
- 새어 나간 토큰을 다시 보내기(nonce 가 다름)
- 이메일이 확인되지 않은 구글 계정으로 남의 주소 계정에 붙기
"""

import hashlib
from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from .google import GoogleAuthError, verify_google_credential

User = get_user_model()

GOOGLE_URL = "/api/accounts/google/"
CLIENT_ID = "devvoca-test.apps.googleusercontent.com"
# 화면이 쿠키에 두고 백엔드에 보내는 비밀값. 구글 토큰 안에는 그 sha256 이 든다.
NONCE = "nonce-1f2e3d"
HASHED = hashlib.sha256(NONCE.encode()).hexdigest()
CONSENT = {"terms_agreed": True, "disclosure_agreed": True, "age_confirmed": True}


def tokeninfo(**over):
    """tokeninfo 가 돌려주는 모양. 참거짓은 글자로 온다."""
    body = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "fedcm@example.com",
        "email_verified": "true",
        "name": "구글사용자",
        "picture": "https://lh3.googleusercontent.com/a/x",
        "nonce": HASHED,
        "exp": "4102444800",
    }
    body.update(over)
    return body


def patch_tokeninfo(status_code=200, body=None, error=None):
    patcher = mock.patch("apps.accounts.google.httpx.Client")
    client = patcher.start()
    ctx = client.return_value.__enter__.return_value
    if error is not None:
        ctx.post.side_effect = error
    else:
        ctx.post.return_value = mock.Mock(
            status_code=status_code,
            json=lambda: tokeninfo() if body is None else body,
        )
    return patcher, ctx


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class VerifyCredentialTest(TestCase):
    def check(self, status_code=200, body=None, error=None, nonce=NONCE):
        patcher, ctx = patch_tokeninfo(status_code, body, error)
        try:
            return verify_google_credential("header.payload.sig", nonce), ctx
        finally:
            patcher.stop()

    def test_returns_same_shape_as_code_login(self):
        info, ctx = self.check()
        self.assertEqual(
            info,
            {
                "email": "fedcm@example.com",
                "name": "구글사용자",
                "picture": "https://lh3.googleusercontent.com/a/x",
            },
        )
        # 토큰은 구글 확인 주소로, 주소가 아니라 본문에 실어 보낸다.
        url = ctx.post.call_args.args[0]
        self.assertEqual(url, "https://oauth2.googleapis.com/tokeninfo")
        self.assertEqual(ctx.post.call_args.kwargs["data"], {"id_token": "header.payload.sig"})

    def test_accepts_issuer_without_scheme(self):
        info, _ = self.check(body=tokeninfo(iss="accounts.google.com"))
        self.assertEqual(info["email"], "fedcm@example.com")

    def test_rejects(self):
        cases = {
            "다른 사이트용 토큰": dict(body=tokeninfo(aud="other.apps.googleusercontent.com")),
            "구글이 아닌 발급자": dict(body=tokeninfo(iss="https://evil.example")),
            "nonce 가 다름": dict(body=tokeninfo(nonce="other")),
            # 토큰은 누구나 읽는다. 안의 nonce(해시)를 그대로 보내도 통과하면 안 된다.
            "새어 나간 토큰의 nonce 를 그대로 보냄": dict(nonce=HASHED),
            "한글 비밀값": dict(nonce="논스"),
            "토큰 nonce 가 한글": dict(body=tokeninfo(nonce="논스")),
            "이메일이 글자가 아님": dict(body=tokeninfo(email=123)),
            "토큰에 nonce 가 없음": dict(body={k: v for k, v in tokeninfo().items() if k != "nonce"}),
            "보낸 nonce 가 비었음": dict(nonce=""),
            "이메일 미확인": dict(body=tokeninfo(email_verified="false")),
            "이메일 없음": dict(body=tokeninfo(email="")),
            "서명·만료가 틀려 400": dict(status_code=400),
            "응답이 JSON 객체가 아님": dict(body=["x"]),
            "구글에 연결 못 함": dict(error=httpx.ConnectError("down")),
        }
        for name, kwargs in cases.items():
            with self.subTest(name), self.assertRaises(GoogleAuthError):
                self.check(**kwargs)

    def test_rejects_picture_that_is_not_https(self):
        info, _ = self.check(body=tokeninfo(picture="javascript:alert(1)"))
        self.assertEqual(info["picture"], "")

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_requires_client_id(self):
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("t", NONCE)


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class CredentialLoginViewTest(TestCase):
    def setUp(self):
        # 구글 제한은 통이 하나라 앞 테스트의 횟수가 이어진다.
        cache.clear()

    def post(self, **body):
        return self.client.post(GOOGLE_URL, body, content_type="application/json")

    def patch_verify(self, email="fedcm@example.com"):
        return mock.patch(
            "apps.accounts.views.verify_google_credential",
            return_value={"email": email, "name": "구글사용자", "picture": ""},
        )

    def test_new_account_with_consent(self):
        with self.patch_verify() as verify:
            res = self.post(credential=" tok ", nonce=" n1 ", **CONSENT)
        self.assertEqual(res.status_code, 201)
        self.assertIn("token", res.json())
        self.assertTrue(User.objects.filter(email="fedcm@example.com").exists())
        # 앞뒤 공백은 떼고 넘긴다.
        verify.assert_called_once_with("tok", "n1")

    def test_new_account_without_consent_is_not_created(self):
        with self.patch_verify():
            res = self.post(credential="tok", nonce="n1")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {"code": "consent_required"})
        self.assertFalse(User.objects.filter(email="fedcm@example.com").exists())

    def test_existing_account_logs_in_without_consent(self):
        User.objects.create_user(email="fedcm@example.com", password="pw-8821-devvoca")
        with self.patch_verify("FedCM@Example.com"):
            res = self.post(credential="tok", nonce="n1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.filter(email="fedcm@example.com").count(), 1)

    def test_missing_or_bad_fields_are_400_without_calling_google(self):
        for body in (
            {"credential": "tok"},
            {"credential": "tok", "nonce": ""},
            {"credential": "", "nonce": "n1"},
            {"credential": 3, "nonce": "n1"},
            {"credential": "tok", "nonce": ["n1"]},
        ):
            with self.subTest(body=body), self.patch_verify() as verify:
                res = self.post(**body)
                self.assertEqual(res.status_code, 400)
                verify.assert_not_called()

    def test_google_refusal_becomes_400(self):
        with mock.patch(
            "apps.accounts.views.verify_google_credential",
            side_effect=GoogleAuthError("구글 로그인을 확인하지 못했습니다."),
        ):
            res = self.post(credential="tok", nonce="n1", **CONSENT)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_code_path_still_works(self):
        """구글 스크립트를 못 쓰는 브라우저는 지금처럼 코드로 온다."""
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "code@example.com", "name": "", "picture": ""},
        ) as fetch:
            res = self.post(code="c", redirect_uri="http://localhost/cb", **CONSENT)
        self.assertEqual(res.status_code, 201)
        fetch.assert_called_once_with("c", "http://localhost/cb")
