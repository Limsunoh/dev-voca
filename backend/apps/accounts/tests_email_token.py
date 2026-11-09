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
from rest_framework.authtoken.models import Token

from .email_change import _SALT, email_mark, make_token, read_token
from .tests import EMAIL_CHANGE_CONFIRM_URL, EMAIL_CHANGE_URL, PASSWORD

User = get_user_model()

OLD = "owner.name@example.com"
NEW = "next@example.com"
THIRD = "third@example.com"


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
        self.token = Token.objects.create(user=self.user)

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

        self.assertEqual(mark, email_mark(OLD))
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
            other = email_mark(OLD)

        self.assertNotEqual(email_mark(OLD), other)


class EmailMarkTest(SimpleTestCase):
    def test_대소문자와_무관하다(self):
        self.assertEqual(email_mark("A.B@Example.COM"), email_mark("a.b@example.com"))

    def test_주소가_다르면_값이_다르다(self):
        self.assertNotEqual(email_mark("a@example.com"), email_mark("b@example.com"))

    def test_읽을_때_세_값이_나온다(self):
        token = make_token(user_id=7, current_email=OLD, new_email="N@Example.com")

        self.assertEqual(read_token(token), (7, email_mark(OLD), "n@example.com"))


class TokenConfirmTest(EmailChangeFlowMixin, TestCase):
    """링크를 눌렀을 때의 판정."""

    def token_keys(self):
        return set(Token.objects.filter(user=self.user).values_list("key", flat=True))

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
        token = make_token(user_id=self.user.pk, current_email=OLD.upper(), new_email=NEW)

        self.assertEqual(self.confirm(token).status_code, 200)

    def test_옛_형식_토큰은_500_없이_거절된다(self):
        """배포 전에 나간 링크. o 에 이메일 원문이 든다."""
        res = self.confirm(self.signed({"u": self.user.pk, "o": OLD, "n": NEW}))

        self.assert_rejected(res)

    def test_모양이_다른_토큰은_500_없이_거절된다(self):
        mark = email_mark(OLD)
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
        other_salt = signing.dumps({"u": self.user.pk, "o": email_mark(OLD), "n": NEW}, salt="x")
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
            json.dumps({"u": self.user.pk, "o": email_mark(OLD), "n": THIRD}).encode()
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

    def token_for(self, new_email):
        return make_token(user_id=self.user.pk, current_email=OLD, new_email=new_email)

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
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)
