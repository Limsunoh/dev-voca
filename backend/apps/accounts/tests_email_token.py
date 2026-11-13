"""이메일 변경 링크의 토큰.

토큰은 서명만 했을 뿐 암호화하지 않아서 base64 를 풀면 그대로 읽힌다. 그 안에
지금 이메일이 보이지 않아야 하고, 대조값으로 바꾼 뒤에도 묵은 링크를 거절하는
동작은 그대로여야 한다.
"""

from __future__ import annotations

import hashlib
import json
import threading
import unittest
import zlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.db import connection, connections
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.accounts.models import LoginToken

from .email_change import _SALT, email_mark, make_token, read_token
from .tests import (
    EMAIL_CHANGE_CONFIRM_URL,
    EMAIL_CHANGE_URL,
    GOOGLE_URL,
    LOGIN_URL,
    LOGOUT_URL,
    ME_URL,
    PASSWORD,
    REDIRECT_URI,
)
from .tests_password import PASSWORD_URL

User = get_user_model()

OLD = "owner.name@example.com"
NEW = "next@example.com"
THIRD = "third@example.com"
LOGIN = "login-token-only-for-this-test"


def decoded_payload(token: str) -> str:
    """토큰에서 누구나 풀어 볼 수 있는 앞부분을 글자로 되돌린다."""
    head = token.split(":")[0]
    compressed = head.startswith(".")
    raw = signing.b64_decode(head[1:].encode() if compressed else head.encode())
    return (zlib.decompress(raw) if compressed else raw).decode()


class EmailChangeFlowMixin:
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email=OLD, password=PASSWORD, display_name="주인"
        )
        self.token = LoginToken.objects.create(user=self.user)

    def request_change(self, new_email=NEW, **body):
        payload = {"new_email": new_email, "current_password": PASSWORD, **body}
        return self.client.post(
            EMAIL_CHANGE_URL,
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def confirm(self, token):
        return self.client.post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": token}, content_type="application/json"
        )

    def issue(self, new_email=NEW):
        """신청을 한 번 하고 메일 본문과 그 안의 토큰을 돌려준다."""
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(new_email)
        self.assertEqual(res.status_code, 202)
        body = sent.call_args.kwargs["body"]
        return body, body.split("/profile/email/")[1].split()[0]

    def issued_token(self, new_email=NEW):
        return self.issue(new_email)[1]

    def signed(self, payload):
        return signing.dumps(payload, salt=_SALT)

    def assert_rejected(self, res, email=OLD):
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, email)


class TokenPayloadTest(EmailChangeFlowMixin, TestCase):
    """메일로 나간 토큰에서 무엇이 읽히는가."""

    def test_풀어_봐도_지금_이메일이_안_보인다(self):
        payload = decoded_payload(self.issued_token())

        self.assertNotIn(OLD, payload)
        self.assertNotIn(OLD.split("@")[0], payload)
        self.assertNotIn(OLD.upper(), payload.upper())

    def test_새_이메일은_남는다(self):
        """바꿀 때 그 값이 있어야 하고, 링크를 받는 본인의 주소다."""
        data = json.loads(decoded_payload(self.issued_token()))

        self.assertEqual(data["n"], NEW)
        self.assertEqual(data["u"], self.user.pk)

    def test_메일_본문에도_지금_이메일이_없다(self):
        body, _ = self.issue()

        self.assertNotIn(OLD, body)
        self.assertNotIn(OLD.split("@")[0], body)

    def test_대조값은_흔한_해시가_아니다(self):
        """그냥 해시면 흔한 주소를 넣어 보는 것만으로 알아낼 수 있다."""
        mark = json.loads(decoded_payload(self.issued_token()))["o"]

        self.assertEqual(mark, email_mark(OLD, self.token.key))
        self.assertRegex(mark, r"^[0-9a-f]{64}$")
        self.assertNotIn(
            mark,
            {
                hashlib.sha256(OLD.encode()).hexdigest(),
                hashlib.sha256(f"{_SALT}{OLD}".encode()).hexdigest(),
                hashlib.sha1(OLD.encode()).hexdigest(),
                hashlib.md5(OLD.encode()).hexdigest(),
            },
        )

    def test_대조값은_서버_키가_달라지면_달라진다(self):
        with override_settings(SECRET_KEY="another-key-only-for-this-test"):
            other = email_mark(OLD, LOGIN)

        self.assertNotEqual(email_mark(OLD, LOGIN), other)


class EmailMarkTest(SimpleTestCase):
    def test_대소문자와_무관하다(self):
        self.assertEqual(email_mark("A.B@Example.COM", LOGIN), email_mark("a.b@example.com", LOGIN))

    def test_주소가_다르면_값이_다르다(self):
        self.assertNotEqual(email_mark("a@example.com", LOGIN), email_mark("b@example.com", LOGIN))

    def test_로그인_토큰이_다르면_값이_다르다(self):
        self.assertNotEqual(email_mark(OLD, "first"), email_mark(OLD, "second"))

    def test_토큰이_없을_때의_값은_있을_때와_다르다(self):
        """같으면 로그아웃으로 토큰이 사라진 뒤에 묵은 링크가 다시 맞아떨어진다."""
        self.assertNotEqual(email_mark(OLD, ""), email_mark(OLD, LOGIN))

    def test_읽을_때_세_값이_나온다(self):
        token = make_token(
            user_id=7, current_email=OLD, new_email="N@Example.com", login_token=LOGIN
        )

        self.assertEqual(read_token(token), (7, email_mark(OLD, LOGIN), "n@example.com"))


class TokenConfirmTest(EmailChangeFlowMixin, TestCase):
    """링크를 눌렀을 때의 판정."""

    def token_keys(self):
        return set(LoginToken.objects.filter(user=self.user).values_list("key", flat=True))

    def test_정상_변경(self):
        res = self.confirm(self.issued_token())

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)

    def test_같은_링크를_두_번_쓰면_두_번째는_거절된다(self):
        token = self.issued_token()
        self.assertEqual(self.confirm(token).status_code, 200)

        self.assert_rejected(self.confirm(token), NEW)

    def test_c_로_바꾼_뒤_묵은_b_링크는_거절된다(self):
        """그대로 받으면 나중에 바꾼 주소가 모르는 사이 되돌아간다."""
        stale = self.issued_token(NEW)
        self.assertEqual(self.confirm(self.issued_token(THIRD)).status_code, 200)
        before = self.token_keys()

        self.assert_rejected(self.confirm(stale), THIRD)
        self.assertEqual(self.token_keys(), before)

    def test_관리자가_주소를_바꾼_뒤의_묵은_링크도_거절된다(self):
        stale = self.issued_token()
        User.objects.filter(pk=self.user.pk).update(email=THIRD)

        self.assert_rejected(self.confirm(stale), THIRD)

    def test_새_주소를_대문자로_신청해도_소문자로_저장된다(self):
        res = self.confirm(self.issued_token("Next.Mail@Example.COM"))

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "next.mail@example.com")

    def test_지금_주소에_대문자가_있어도_링크가_통한다(self):
        """save 를 안 거친 옛 행이 있어도 사용자가 이유 없이 실패하면 안 된다."""
        User.objects.filter(pk=self.user.pk).update(email="Owner.Name@Example.com")

        res = self.confirm(self.issued_token())

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)

    def test_신청과_확인_사이에_대소문자만_달라져도_통한다(self):
        token = self.issued_token()
        User.objects.filter(pk=self.user.pk).update(email=OLD.upper())

        self.assertEqual(self.confirm(token).status_code, 200)

    def test_대문자_주소로_만든_토큰도_같은_대조값이다(self):
        token = make_token(
            user_id=self.user.pk,
            current_email=OLD.upper(),
            new_email=NEW,
            login_token=self.token.key,
        )

        self.assertEqual(self.confirm(token).status_code, 200)

    def test_옛_형식_토큰은_500_없이_거절된다(self):
        """배포 전에 나간 링크. o 에 이메일 원문이 든다."""
        res = self.confirm(self.signed({"u": self.user.pk, "o": OLD, "n": NEW}))

        self.assert_rejected(res)

    def test_모양이_다른_토큰은_500_없이_거절된다(self):
        mark = email_mark(OLD, self.token.key)
        pk = self.user.pk
        cases = {
            "키 없음": {},
            "o 없음": {"u": pk, "n": NEW},
            "n 없음": {"u": pk, "o": mark},
            "u 없음": {"o": mark, "n": NEW},
            "u 문자": {"u": "abc", "o": mark, "n": NEW},
            "u null": {"u": None, "o": mark, "n": NEW},
            "u 목록": {"u": [1], "o": mark, "n": NEW},
            "o null": {"u": pk, "o": None, "n": NEW},
            "o 숫자": {"u": pk, "o": 1, "n": NEW},
            "o 객체": {"u": pk, "o": {"a": 1}, "n": NEW},
            "o 빈 값": {"u": pk, "o": "", "n": NEW},
            "u 음수": {"u": -1, "o": mark, "n": NEW},
            "u 범위 초과": {"u": 10**40, "o": mark, "n": NEW},
            "목록": [1, 2, 3],
            "문자열": "abc",
            "숫자": 7,
            "null": None,
        }
        for label, payload in cases.items():
            with self.subTest(label):
                self.assert_rejected(self.confirm(self.signed(payload)))

    def test_토큰을_고치거나_형식이_틀리면_거절된다(self):
        good = self.issued_token()
        other_salt = signing.dumps(
            {"u": self.user.pk, "o": email_mark(OLD, self.token.key), "n": NEW}, salt="x"
        )
        cases = {
            "서명 변조": good[:-2] + ("aa" if not good.endswith("aa") else "bb"),
            "본문 변조": "A" + good[1:],
            "다른 솔트": other_salt,
            "쓰레기": "!!!not-a-token!!!",
            "매우 긴 값": "a" * 100000,
            "공백만": "   ",
            "빈 값": "",
            "숫자": 123,
            "null": None,
            "목록": ["a"],
            "NUL 문자": "a\x00b",
        }
        for label, value in cases.items():
            with self.subTest(label):
                self.assert_rejected(self.confirm(value))

    def test_본문이_JSON_객체가_아니면_거절된다(self):
        res = self.client.post(
            EMAIL_CHANGE_CONFIRM_URL, json.dumps(["a"]), content_type="application/json"
        )

        self.assert_rejected(res)

    def test_대조값을_알아도_서명_없이는_새_주소를_못_바꾼다(self):
        """풀어 볼 수 있어도 고치면 서명이 깨진다."""
        rest = self.issued_token().split(":", 1)[1]
        forged = signing.b64_encode(
            json.dumps(
                {"u": self.user.pk, "o": email_mark(OLD, self.token.key), "n": THIRD}
            ).encode()
        ).decode()

        self.assert_rejected(self.confirm(f"{forged}:{rest}"))

    def test_없어진_회원의_링크는_거절된다(self):
        token = self.issued_token()
        self.user.delete()

        res = self.confirm(token)

        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email=NEW).exists())

    def test_정지된_회원의_링크는_거절된다(self):
        token = self.issued_token()
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        self.assert_rejected(self.confirm(token))

    def test_그_사이_새_주소가_가입되면_거절된다(self):
        token = self.issued_token()
        User.objects.create_user(email=NEW, password=PASSWORD)

        self.assert_rejected(self.confirm(token))

    def test_만료된_링크는_거절된다(self):
        token = self.issued_token()

        with mock.patch("apps.accounts.email_change.TOKEN_MAX_AGE", -1):
            res = self.confirm(token)

        self.assert_rejected(res)


@unittest.skipUnless(connection.vendor == "postgresql", "행 잠금이 있어야 뜻이 있다")
class TokenConfirmRaceTest(TransactionTestCase):
    """링크를 동시에 눌렀을 때. 대조와 저장이 잠금 안에 있는가."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=OLD, password=PASSWORD)
        self.token = LoginToken.objects.create(user=self.user)

    def token_for(self, new_email):
        return make_token(
            user_id=self.user.pk,
            current_email=OLD,
            new_email=new_email,
            login_token=self.token.key,
        )

    def confirm_together(self, *tokens):
        barrier = threading.Barrier(len(tokens))
        statuses = []
        lock = threading.Lock()

        def press(token):
            try:
                barrier.wait(timeout=10)
                res = Client(raise_request_exception=False).post(
                    EMAIL_CHANGE_CONFIRM_URL,
                    {"token": token},
                    content_type="application/json",
                )
                with lock:
                    statuses.append(res.status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=press, args=(t,)) for t in tokens]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return sorted(statuses)

    def test_같은_링크를_동시에_눌러도_한_번만_성공한다(self):
        token = self.token_for(NEW)

        self.assertEqual(self.confirm_together(token, token), [200, 400])
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)

    def test_다른_두_링크를_동시에_눌러도_하나만_성공한다(self):
        """둘 다 지나가면 주소 하나가 사용자 모르게 덮인다."""
        self.assertEqual(
            self.confirm_together(self.token_for(NEW), self.token_for(THIRD)), [200, 400]
        )
        self.user.refresh_from_db()
        self.assertIn(self.user.email, (NEW, THIRD))
        self.assertEqual(LoginToken.objects.filter(user=self.user).count(), 1)


class LinkInvalidationTest(EmailChangeFlowMixin, TestCase):
    """변경이 끝나거나 신청한 기기의 로그인이 끝나면 그 전에 보낸 링크는 죽는다."""

    def complete(self, link):
        """링크로 변경을 끝낸다. 변경 뒤에는 로그인 토큰이 새것이 된다."""
        res = self.confirm(link)
        self.assertEqual(res.status_code, 200)
        self.token = LoginToken.objects.get(user=self.user)
        self.assertEqual(res.json()["token"], self.token.key)

    def round_trip(self):
        """a -> b -> a 를 끝내고 처음 보낸 a -> b 링크를 돌려준다."""
        first = self.issued_token(NEW)
        self.complete(first)
        self.complete(self.issued_token(OLD))
        return first

    def me_status(self, key):
        return self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {key}").status_code

    def login(self):
        return self.client.post(
            LOGIN_URL,
            {"email": OLD, "password": PASSWORD},
            content_type="application/json",
        )

    def logout(self):
        return self.client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_a_b_뒤_b_a_로_돌아오면_처음_링크는_거절된다(self):
        """주소만 대조하면 다시 맞아떨어져 링크를 가진 사람이 계정을 옮길 수 있다."""
        first = self.round_trip()

        self.assert_rejected(self.confirm(first))

    def test_왕복을_두_번_해도_앞선_링크는_모두_거절된다(self):
        links = []
        for _ in range(2):
            links.append(self.issued_token(NEW))
            self.complete(links[-1])
            links.append(self.issued_token(OLD))
            self.complete(links[-1])

        for index, link in enumerate(links):
            with self.subTest(index):
                self.assert_rejected(self.confirm(link))

    def test_왕복_뒤에_새로_받은_링크는_통한다(self):
        """죽여야 할 것은 옛 링크뿐이다. 다시 바꾸는 길까지 막히면 안 된다."""
        self.round_trip()

        self.assertEqual(self.confirm(self.issued_token(NEW)).status_code, 200)

    def test_거절된_링크는_로그인을_끊지_않는다(self):
        """옛 링크를 가진 사람이 눌러 볼 때마다 주인이 로그아웃되면 안 된다."""
        first = self.round_trip()

        self.assert_rejected(self.confirm(first))

        self.assertEqual(LoginToken.objects.get(user=self.user).key, self.token.key)
        self.assertEqual(self.me_status(self.token.key), 200)

    def test_a_b_와_a_c_를_함께_받아_b_를_쓰면_c_링크는_거절된다(self):
        to_b = self.issued_token(NEW)
        to_c = self.issued_token(THIRD)

        self.complete(to_b)

        self.assert_rejected(self.confirm(to_c), NEW)

    def test_a_b_와_a_c_를_함께_받아_c_를_쓰면_b_링크는_거절된다(self):
        to_b = self.issued_token(NEW)
        to_c = self.issued_token(THIRD)

        self.complete(to_c)

        self.assert_rejected(self.confirm(to_b), THIRD)

    def test_함께_받은_링크는_주소가_돌아와도_거절된다(self):
        to_b = self.issued_token(NEW)
        to_c = self.issued_token(THIRD)
        self.complete(to_b)
        self.complete(self.issued_token(OLD))

        self.assert_rejected(self.confirm(to_c))
        self.assert_rejected(self.confirm(to_b))

    def test_로그아웃하면_대기_중인_링크는_거절된다(self):
        link = self.issued_token()
        self.assertEqual(self.logout().status_code, 204)

        self.assert_rejected(self.confirm(link))
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_로그아웃_뒤_다시_로그인해도_링크는_거절된다(self):
        """다시 로그인하면 토큰이 새것이다. 메일의 안내와 같은 동작이다."""
        link = self.issued_token()
        self.logout()
        self.assertEqual(self.login().status_code, 200)

        self.assert_rejected(self.confirm(link))

    def test_비밀번호를_바꾸면_대기_중인_링크는_거절된다(self):
        link = self.issued_token()
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": PASSWORD + "x"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.json()["token"], self.token.key)

        self.assert_rejected(self.confirm(link))

    def test_비밀번호_변경에_실패하면_링크는_살아_있다(self):
        link = self.issued_token()
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": PASSWORD + "x", "new_password": PASSWORD + "y"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )
        self.assertEqual(res.status_code, 400)

        self.assertEqual(self.confirm(link).status_code, 200)

    def test_다른_기기에서_로그인해도_링크는_살아_있다(self):
        """새 기기는 새 토큰을 받지만 링크는 신청한 기기의 토큰에 묶여 있다.

        새 로그인으로 링크가 죽으면 사용자는 이유를 알 수 없다.
        """
        link = self.issued_token()

        res = self.login()

        self.assertNotEqual(res.json()["token"], self.token.key)
        self.assertEqual(self.confirm(link).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)

    def test_구글로_다시_로그인해도_링크는_살아_있다(self):
        link = self.issued_token()
        info = {"email": OLD, "name": "주인", "picture": "https://lh3.googleusercontent.com/a/new"}

        with mock.patch("apps.accounts.views.fetch_google_user", return_value=info):
            res = self.client.post(
                GOOGLE_URL,
                {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI},
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.json()["token"], self.token.key)
        self.assertEqual(self.confirm(link).status_code, 200)

    def test_나중에_로그인한_기기가_로그아웃해도_링크는_살아_있다(self):
        link = self.issued_token()
        later = self.login().json()["token"]

        res = self.client.post(LOGOUT_URL, HTTP_AUTHORIZATION=f"Token {later}")

        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.confirm(link).status_code, 200)

    def test_나중에_로그인한_기기에서_신청해도_링크가_통한다(self):
        self.login()
        self.token = LoginToken.objects.filter(user=self.user).latest("pk")

        self.assertEqual(self.confirm(self.issued_token()).status_code, 200)

    def test_신청한_기기가_로그아웃하면_다른_기기가_남아_있어도_링크는_거절된다(self):
        """처리방침이 "로그아웃하면 대기 중인 링크는 무효" 라고 적고 있다."""
        first = self.token
        self.login()
        self.token = LoginToken.objects.filter(user=self.user).latest("pk")
        link = self.issued_token()

        self.assertEqual(self.logout().status_code, 204)

        self.assert_rejected(self.confirm(link))
        self.assertTrue(LoginToken.objects.filter(pk=first.pk).exists())

    def test_로그인_없이_다른_기기에서_링크를_열_수_있다(self):
        """메일은 로그인하지 않은 폰에서 열 수 있다. 토큰 자체가 증거다."""
        link = self.issued_token()

        res = Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)
        self.assertEqual(self.me_status(self.token.key), 401)
        self.assertEqual(self.me_status(res.json()["token"]), 200)

    def test_메일_본문에_링크가_죽는_경우를_안내한다(self):
        body, link = self.issue()

        self.assertIn(f"/profile/email/{link}", body)
        self.assertIn("하루가 지나면", body)
        self.assertIn("로그아웃하거나 비밀번호를 바꿔도 쓸 수 없게", body)
        self.assertIn("다시 신청해주세요", body)


class SessionUserEmailChangeTest(TestCase):
    """로그인 토큰이 없는 세션 사용자. 관리자 화면으로만 로그인한 계정이다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email=OLD, password=PASSWORD)
        self.session = Client()
        self.session.force_login(self.user)

    def request_change(self, new_email=NEW, password=PASSWORD):
        return self.session.post(
            EMAIL_CHANGE_URL,
            {"new_email": new_email, "current_password": password},
            content_type="application/json",
        )

    def issued_token(self, new_email=NEW):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(new_email)
        self.assertEqual(res.status_code, 202)
        return sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

    def confirm(self, link):
        return Client().post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )

    def complete(self, link):
        self.assertEqual(self.confirm(link).status_code, 200)

    def drop_tokens(self):
        """관리자 화면에서 이 계정의 토큰을 지운 경우.

        세션으로 로그아웃하면 지울 토큰이 없어 아무것도 안 지운다(LogoutView).
        토큰이 다 없어지는 길은 이것뿐이다.
        """
        LoginToken.objects.filter(user=self.user).delete()

    def assert_rejected(self, res, email=OLD):
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("token", res.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, email)

    def test_신청하면_로그인_토큰이_만들어지고_링크가_통한다(self):
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

        link = self.issued_token()

        self.assertTrue(LoginToken.objects.filter(user=self.user).exists())
        self.complete(link)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, NEW)

    def test_신청이_거절되면_토큰을_만들지_않는다(self):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(password=PASSWORD + "x")

        self.assertEqual(res.status_code, 400)
        sent.assert_not_called()
        self.assertFalse(LoginToken.objects.filter(user=self.user).exists())

    def test_세션으로_로그아웃해도_토큰은_그대로다(self):
        self.issued_token()

        self.assertEqual(self.session.post(LOGOUT_URL).status_code, 204)

        self.assertTrue(LoginToken.objects.filter(user=self.user).exists())

    def test_토큰이_없어지면_링크는_거절된다(self):
        """신청 때 빈 값을 섞었다면 토큰이 없어진 지금 다시 맞아떨어진다."""
        link = self.issued_token()
        self.drop_tokens()

        self.assert_rejected(self.confirm(link))

    def test_a_b_a_뒤에_토큰이_없어져도_옛_링크는_거절된다(self):
        first = self.issued_token(NEW)
        self.complete(first)
        back = self.issued_token(OLD)
        self.complete(back)
        self.drop_tokens()

        self.assert_rejected(self.confirm(first))
        self.assert_rejected(self.confirm(back))


@unittest.skipUnless(connection.vendor == "postgresql", "행 잠금이 있어야 뜻이 있다")
class SessionRequestRaceTest(TransactionTestCase):
    """로그인 토큰이 없는 세션이 동시에 신청할 때."""

    def test_동시에_신청해도_500_없이_토큰은_하나고_링크는_하나만_쓰인다(self):
        cache.clear()
        user = User.objects.create_user(email=OLD, password=PASSWORD)
        clients = [Client(raise_request_exception=False) for _ in range(2)]
        for client in clients:
            client.force_login(user)
        barrier = threading.Barrier(len(clients))
        statuses = []

        def send(client, new_email):
            try:
                barrier.wait(timeout=10)
                res = client.post(
                    EMAIL_CHANGE_URL,
                    {"new_email": new_email, "current_password": PASSWORD},
                    content_type="application/json",
                )
                statuses.append(res.status_code)
            finally:
                connections.close_all()

        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            threads = [
                threading.Thread(target=send, args=(client, email))
                for client, email in zip(clients, (NEW, THIRD), strict=True)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

        self.assertEqual(statuses, [202, 202])
        self.assertEqual(LoginToken.objects.filter(user=user).count(), 1)

        links = [
            call.kwargs["body"].split("/profile/email/")[1].split()[0]
            for call in sent.call_args_list
        ]
        results = [
            Client().post(
                EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
            ).status_code
            for link in links
        ]
        self.assertEqual(results, [200, 400])
