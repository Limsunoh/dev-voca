"""구글 버튼 신분 토큰(credential) 경로의 경계와 남용.

tests_google_credential.py 가 기본 거절 목록을 본다. 여기서는 그 바깥을 민다:
뷰를 거쳐 실제 tokeninfo 응답 모양으로 끝까지 가는 경우, 동의 값 위조,
대소문자가 다른 이메일로 기존 계정에 붙기, 두 길(credential·code)이 섞인 요청,
제한(throttle)이 이 길에도 걸리는지.

구글은 부르지 않는다. tokeninfo 응답은 httpx.Client 대역으로 흉내 낸다.
"""

import hashlib
from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from .google import GoogleAuthError, verify_google_credential
from .throttles import GoogleRateThrottle

User = get_user_model()

GOOGLE_URL = "/api/accounts/google/"
CLIENT_ID = "devvoca-test.apps.googleusercontent.com"
# 화면이 보내는 비밀값. 구글 토큰 안에는 그 sha256 이 든다.
NONCE = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
HASHED = hashlib.sha256(NONCE.encode()).hexdigest()
CONSENT = {"terms_agreed": True, "disclosure_agreed": True, "age_confirmed": True}


def tokeninfo(**over):
    """tokeninfo 가 200 으로 돌려주는 몸통. 참거짓은 글자로 온다."""
    body = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "edge@example.com",
        "email_verified": "true",
        "name": "경계사용자",
        "picture": "https://lh3.googleusercontent.com/a/edge",
        "nonce": HASHED,
        "exp": "4102444800",
    }
    body.update(over)
    return body


class TokeninfoMixin:
    """tokeninfo 를 대역으로 둔다. 각 테스트가 끝나면 자동으로 걷는다."""

    def fake_tokeninfo(self, status_code=200, body=None):
        patcher = mock.patch("apps.accounts.google.httpx.Client")
        client = patcher.start()
        self.addCleanup(patcher.stop)
        ctx = client.return_value.__enter__.return_value
        ctx.post.return_value = mock.Mock(
            status_code=status_code,
            json=lambda: tokeninfo() if body is None else body,
        )
        return ctx


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class VerifyCredentialEdgeTest(TokeninfoMixin, TestCase):
    def test_expired_token_response_is_rejected(self):
        """만료된 토큰은 tokeninfo 가 400 과 error_description 으로 답한다."""
        self.fake_tokeninfo(
            400, {"error": "invalid_token", "error_description": "Token expired"}
        )
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("h.p.s", NONCE)

    def test_server_error_from_google_is_rejected(self):
        self.fake_tokeninfo(503, {})
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("h.p.s", NONCE)

    def test_json_parse_failure_is_rejected(self):
        ctx = self.fake_tokeninfo()
        ctx.post.return_value = mock.Mock(
            status_code=200, json=mock.Mock(side_effect=ValueError("html"))
        )
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("h.p.s", NONCE)

    def test_timeout_is_rejected(self):
        ctx = self.fake_tokeninfo()
        ctx.post.side_effect = httpx.ReadTimeout("slow")
        with self.assertRaises(GoogleAuthError):
            verify_google_credential("h.p.s", NONCE)

    def test_aud_must_match_exactly(self):
        """대소문자·공백·앞뒤 덧붙임이 다른 aud 도 남의 것이다."""
        for aud in (
            CLIENT_ID.upper(),
            f" {CLIENT_ID}",
            f"{CLIENT_ID}.evil",
            "",
            None,
            [CLIENT_ID],
        ):
            with self.subTest(aud=aud):
                self.fake_tokeninfo(body=tokeninfo(aud=aud))
                with self.assertRaises(GoogleAuthError):
                    verify_google_credential("h.p.s", NONCE)

    def test_issuer_variants_are_rejected(self):
        for iss in ("http://accounts.google.com", "accounts.google.com.evil", "", None):
            with self.subTest(iss=iss):
                self.fake_tokeninfo(body=tokeninfo(iss=iss))
                with self.assertRaises(GoogleAuthError):
                    verify_google_credential("h.p.s", NONCE)

    def test_nonce_variants_are_rejected(self):
        """토큰의 nonce 와 한 글자라도 다르거나 글자가 아니면 거절."""
        for token_nonce in (HASHED.upper(), HASHED[:-1], HASHED + "0", 12345, None, ""):
            with self.subTest(token_nonce=token_nonce):
                self.fake_tokeninfo(body=tokeninfo(nonce=token_nonce))
                with self.assertRaises(GoogleAuthError):
                    verify_google_credential("h.p.s", NONCE)

    def test_email_verified_only_true_values(self):
        """tokeninfo 는 "true"/"false" 로 준다. 그 밖의 참 같은 값은 받지 않는다."""
        for value in ("false", "1", "yes", "True", "", None):
            with self.subTest(value=value):
                self.fake_tokeninfo(body=tokeninfo(email_verified=value))
                with self.assertRaises(GoogleAuthError):
                    verify_google_credential("h.p.s", NONCE)
        self.fake_tokeninfo(body=tokeninfo(email_verified=True))
        self.assertEqual(verify_google_credential("h.p.s", NONCE)["email"], "edge@example.com")

    def test_missing_name_and_picture_become_empty(self):
        body = {k: v for k, v in tokeninfo().items() if k not in ("name", "picture")}
        self.fake_tokeninfo(body=body)
        info = verify_google_credential("h.p.s", NONCE)
        self.assertEqual((info["name"], info["picture"]), ("", ""))


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class CredentialViewEdgeTest(TokeninfoMixin, TestCase):
    def setUp(self):
        # 구글 제한은 통이 하나라 앞 테스트의 횟수가 이어진다.
        cache.clear()

    def post(self, **body):
        return self.client.post(GOOGLE_URL, body, content_type="application/json")

    def test_end_to_end_new_account_through_tokeninfo(self):
        """뷰 -> verify_google_credential -> tokeninfo 대역까지 끝까지 간다."""
        ctx = self.fake_tokeninfo()
        res = self.post(credential="h.p.s", nonce=NONCE, **CONSENT)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ctx.post.call_args.kwargs["data"], {"id_token": "h.p.s"})
        user = User.objects.get(email="edge@example.com")
        self.assertIsNotNone(user.terms_agreed_at)
        self.assertFalse(user.has_usable_password())

    def test_replayed_token_with_its_own_nonce_gets_no_login(self):
        """새어 나간 토큰 몸통의 nonce(해시)를 그대로 보내도 기존 계정에 못 들어온다.

        토큰은 암호화돼 있지 않아 nonce 는 누구나 읽는다. 비밀값을 모르면 막혀야 한다.
        뷰를 거쳐도 500 이 아니라 400 이다(한글 값 포함).
        """
        User.objects.create_user(email="edge@example.com", password="pw-edge-7731")
        self.client.raise_request_exception = False
        for nonce in (HASHED, "논스", HASHED.upper()):
            with self.subTest(nonce=nonce):
                self.fake_tokeninfo()
                res = self.post(credential="leaked.jwt", nonce=nonce)
                self.assertEqual(res.status_code, 400)
                self.assertNotIn("token", res.json())
        # 토큰 쪽 nonce 가 한글이어도 500 이 아니다.
        self.fake_tokeninfo(body=tokeninfo(nonce="논스"))
        self.assertEqual(self.post(credential="leaked.jwt", nonce=NONCE).status_code, 400)
        # 대조군: 진짜 비밀값이면 들어온다.
        self.fake_tokeninfo()
        self.assertEqual(self.post(credential="leaked.jwt", nonce=NONCE).status_code, 200)

    def test_end_to_end_rejections_create_nothing(self):
        cases = {
            "다른 aud": tokeninfo(aud="other.apps.googleusercontent.com"),
            "다른 nonce": tokeninfo(nonce="ffff"),
            "nonce 없음": {k: v for k, v in tokeninfo().items() if k != "nonce"},
            "미확인 이메일": tokeninfo(email_verified="false"),
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.fake_tokeninfo(body=body)
                res = self.post(credential="h.p.s", nonce=NONCE, **CONSENT)
                self.assertEqual(res.status_code, 400)
                self.assertNotIn("token", res.json())
        self.fake_tokeninfo(400, {"error_description": "Token expired"})
        res = self.post(credential="h.p.s", nonce=NONCE, **CONSENT)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_uppercase_email_attaches_to_existing_account(self):
        """구글이 대문자 섞인 주소를 줘도 기존 계정에 붙는다. 둘로 갈리지 않는다."""
        user = User.objects.create_user(email="edge@example.com", password="pw-edge-7731")
        before = user.terms_agreed_at
        self.fake_tokeninfo(body=tokeninfo(email="EDGE@Example.COM"))
        res = self.post(credential="h.p.s", nonce=NONCE, **CONSENT)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        user.refresh_from_db()
        # 붙기만 한다. 동의 시각을 새로 덮지 않는다.
        self.assertEqual(user.terms_agreed_at, before)

    def test_forged_consent_values_do_not_create_account(self):
        """정확히 true 세 개가 아니면 새 계정을 만들지 않는다."""
        forged = (
            {"terms_agreed": "true", "disclosure_agreed": "true", "age_confirmed": "true"},
            {"terms_agreed": 1, "disclosure_agreed": 1, "age_confirmed": 1},
            {"terms_agreed": True, "disclosure_agreed": True},
            {"terms_agreed": True, "disclosure_agreed": True, "age_confirmed": "1"},
            {"consent": True},
        )
        for extra in forged:
            with self.subTest(extra=extra):
                self.fake_tokeninfo()
                res = self.post(credential="h.p.s", nonce=NONCE, **extra)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json(), {"code": "consent_required"})
        self.assertFalse(User.objects.exists())

    def test_inactive_account_is_refused(self):
        User.objects.create_user(email="edge@example.com", password="pw-edge-7731", is_active=False)
        self.fake_tokeninfo()
        res = self.post(credential="h.p.s", nonce=NONCE)
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())

    def test_credential_key_wins_over_code_and_never_falls_back(self):
        """credential 칸이 있으면 그 길만 탄다. 비었다고 code 길로 새지 않는다."""
        with (
            mock.patch("apps.accounts.views.fetch_google_user") as fetch,
            mock.patch("apps.accounts.views.verify_google_credential") as verify,
        ):
            for credential in (None, "", "   "):
                with self.subTest(credential=credential):
                    res = self.post(
                        credential=credential,
                        nonce=NONCE,
                        code="c",
                        redirect_uri="http://localhost/cb",
                        **CONSENT,
                    )
                    self.assertEqual(res.status_code, 400)
            fetch.assert_not_called()
            verify.assert_not_called()

    def test_whitespace_only_nonce_is_400_without_google(self):
        with mock.patch("apps.accounts.views.verify_google_credential") as verify:
            res = self.post(credential="h.p.s", nonce="   ")
        self.assertEqual(res.status_code, 400)
        verify.assert_not_called()

    def test_non_dict_body_is_400(self):
        res = self.client.post(GOOGLE_URL, ["credential"], content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_throttle_applies_to_credential_path(self):
        """신분 토큰 길도 같은 한 통(GoogleRateThrottle)으로 센다."""
        with (
            mock.patch.object(GoogleRateThrottle, "get_rate", return_value="3/min"),
            mock.patch(
                "apps.accounts.views.verify_google_credential",
                side_effect=GoogleAuthError("확인하지 못했습니다."),
            ) as verify,
        ):
            codes = [
                self.client.post(
                    GOOGLE_URL,
                    {"credential": f"t{i}", "nonce": f"n{i}"},
                    content_type="application/json",
                    REMOTE_ADDR=f"10.1.0.{i}",
                ).status_code
                for i in range(4)
            ]
        self.assertEqual(codes, [400, 400, 400, 429])
        # 막힌 넷째는 구글을 부르지 않았다.
        self.assertEqual(verify.call_count, 3)
