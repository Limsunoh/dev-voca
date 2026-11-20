"""처리방침 v5 로 올린 뒤 가입 동의 기록을 깨뜨려 보는 테스트.

  - 이메일 가입, 구글 코드 가입, 구글 신분 토큰(계정 창) 가입 셋 모두 동의 기록의 버전이
    화면 문서(LegalDoc.tsx 의 DOC_VERSION)와 같다. v5 동안은 글자 "v5" 로도 못 박는다.
  - 요청 본문에 버전을 실어 보내도 서버 값이 이긴다.
  - v4 로 가입한 사람이 다시 로그인해도 v5 로 올라가지 않는다(v5 에 동의한 적이 없다).

DOC_VERSION 을 읽는 doc_version() 은 tests_token_expiry_dynamic.py 의 것을 쓴다.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from .models import TERMS_VERSION
from .tests import CONSENT, GOOGLE_URL, LOGIN_URL, PASSWORD, REDIRECT_URI, SIGNUP_URL
from .tests_token_expiry_dynamic import doc_version

User = get_user_model()

CLIENT_ID = "devvoca-test.apps.googleusercontent.com"
GOOGLE_INFO = {"email": "v5-google@example.com", "name": "구글오",
               "picture": ""}


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class PrivacyV5ConsentTest(TestCase):
    def setUp(self):
        # 가입·구글 제한 횟수가 앞 테스트에서 이어지지 않게 한다.
        cache.clear()

    def post(self, url: str, body: dict):
        return self.client.post(url, body, content_type="application/json")

    def google_code(self, **body):
        with mock.patch("apps.accounts.views.fetch_google_user", return_value=GOOGLE_INFO):
            return self.post(GOOGLE_URL, {"code": "c1", "redirect_uri": REDIRECT_URI, **body})

    def google_credential(self, **body):
        with mock.patch("apps.accounts.views.verify_google_credential", return_value=GOOGLE_INFO):
            return self.post(GOOGLE_URL, {"credential": "tok", "nonce": "n1", **body})

    def test_서버_버전이_화면_문서_버전과_같다(self):
        self.assertEqual(TERMS_VERSION, doc_version())

    def test_v5_동안은_글자로도_v5다(self):
        if doc_version() != "v5":
            self.skipTest("v5 가 아니다. 다음 개정 때 이 테스트를 지운다.")
        self.assertEqual(TERMS_VERSION, "v5")

    def test_세_가입_길_모두_화면_문서_버전으로_남긴다(self):
        res = self.post(SIGNUP_URL, {"email": "v5-mail@example.com", "password": PASSWORD, **CONSENT})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="v5-mail@example.com").terms_version, doc_version())

        for name, signup in (("code", self.google_code), ("credential", self.google_credential)):
            with self.subTest(name):
                User.objects.filter(email=GOOGLE_INFO["email"]).delete()
                cache.clear()
                res = signup(**CONSENT)
                self.assertEqual(res.status_code, 201, res.content)
                user = User.objects.get(email=GOOGLE_INFO["email"])
                self.assertEqual(user.terms_version, doc_version())
                self.assertIsNotNone(user.terms_agreed_at)

    def test_본문에_실은_버전은_무시한다(self):
        forged = {"terms_version": "v6", "terms_agreed_at": "2000-01-01T00:00:00Z"}
        res = self.post(SIGNUP_URL, {"email": "forge@example.com", "password": PASSWORD,
                                     **CONSENT, **forged})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="forge@example.com").terms_version, doc_version())

        res = self.google_credential(**CONSENT, **forged)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email=GOOGLE_INFO["email"]).terms_version, doc_version())

    def test_v4_로_가입한_사람은_다시_로그인해도_v4_다(self):
        User.objects.create_user(email=GOOGLE_INFO["email"], password=PASSWORD, terms_version="v4")

        res = self.post(LOGIN_URL, {"email": GOOGLE_INFO["email"], "password": PASSWORD})
        self.assertEqual(res.status_code, 200)
        res = self.google_credential(**CONSENT)
        self.assertEqual(res.status_code, 200)
        res = self.google_code(**CONSENT)
        self.assertEqual(res.status_code, 200)

        self.assertEqual(User.objects.get(email=GOOGLE_INFO["email"]).terms_version, "v4")
