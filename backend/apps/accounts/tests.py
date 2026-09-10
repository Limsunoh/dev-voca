"""계정 테스트.

핵심은 세 가지다. 비밀번호가 해시되어 저장되는가, 남의 정보를 볼 수 없는가,
실패했을 때 그 응답만으로 가입 여부를 알아낼 수 없는가.
"""

import io
import os
import unicodedata
import uuid
from datetime import timedelta
from importlib import import_module
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DatabaseError, connection, migrations
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .google import GoogleAuthError, fetch_google_user
from .mail import MailNotConfigured
from .models import (
    AVATAR_PHOTO,
    AVATAR_PHOTO_MAX_BYTES,
    AVATAR_PHOTO_SIZE,
    DISPLAY_NAME_MAX,
    AvatarPhotoError,
    free_display_name,
    name_taken,
    shrink_avatar_photo,
)
from .throttles import EmailRateThrottle, GoogleRateThrottle

# 마이그레이션 모듈은 이름이 숫자로 시작해 평범한 import 가 안 된다.
# 함수만 꺼내지 않고 모듈째 잡아둔다 - 함수가 operations 에 실제로 걸려
# 있는지도 봐야 하기 때문이다. 이번 사고가 정확히 "동작하는 코드는 있는데
# 그것을 실행하는 배선이 없다" 였다.
cache_table_migration = import_module(
    "apps.accounts.migrations.0002_throttle_cache_table"
)
create_cache_table = cache_table_migration.create_cache_table

User = get_user_model()

SIGNUP_URL = "/api/accounts/signup/"
LOGIN_URL = "/api/accounts/login/"
LOGOUT_URL = "/api/accounts/logout/"
ME_URL = "/api/accounts/me/"
GOOGLE_URL = "/api/accounts/google/"
EMAIL_CHANGE_URL = "/api/accounts/email-change/"
EMAIL_CHANGE_CONFIRM_URL = "/api/accounts/email-change/confirm/"
PHOTO_URL = "/api/accounts/photo/"

# 구글이 코드를 발급할 때 쓴 주소. 확인 요청에 같이 보내야 한다.
REDIRECT_URI = "http://localhost:3000/api/auth/google/callback"

# 검사기를 통과하는 비밀번호. 짧거나 흔하면 가입 자체가 막힌다.
PASSWORD = "devvoca-pass-8821"


class SignUpTest(TestCase):
    def signup(self, **body):
        payload = {"email": "a@example.com", "password": PASSWORD, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def test_creates_user_and_returns_token(self):
        res = self.signup()

        self.assertEqual(res.status_code, 201)
        self.assertIn("token", res.json())
        self.assertEqual(res.json()["user"]["email"], "a@example.com")

    def test_password_is_hashed(self):
        """평문으로 저장되면 DB 가 새는 순간 모든 계정이 넘어간다."""
        self.signup()

        user = User.objects.get(email="a@example.com")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_password_never_appears_in_response(self):
        """비밀번호 값도, 그 해시도 응답에 실리면 안 된다.

        예전에는 본문에 "password" 라는 글자가 있는지만 봤다. 그 방식은
        has_password(비밀번호를 쓸 수 있는 계정인가) 같은 **값이 아닌**
        필드가 생기자 곧바로 걸렸다 - 새는 것이 없는데도 빨개진다.

        반대로 느슨하기도 했다. 응답이 해시를 pw 나 secret 같은 다른
        이름으로 실어 보내면 그 검사는 통과한다. 막으려는 것은 이름이
        아니라 값이므로, 평문과 해시를 직접 찾는다.
        """
        res = self.signup()
        body = res.content.decode()

        self.assertNotIn(PASSWORD, body)

        # 해시도 빠져나가면 안 된다. 오프라인에서 깨볼 수 있고, 같은
        # 비밀번호를 쓰는 다른 계정까지 위험해진다.
        stored = User.objects.get(email="a@example.com").password
        self.assertNotIn(stored, body)

        # 해시 앞부분(알고리즘 이름)만 새도 안 된다. 통째로 비교하면
        # 잘려 실린 경우를 놓친다.
        self.assertNotIn(stored[:20], body)

    def test_rejects_duplicate_email(self):
        self.signup()

        res = self.signup()

        self.assertEqual(res.status_code, 400)

    def test_rejects_duplicate_email_ignoring_case(self):
        """도메인은 대소문자를 구분하지 않는다. 같은 사람이 두 계정을 갖게 된다."""
        self.signup()

        res = self.signup(email="A@Example.com")

        self.assertEqual(res.status_code, 400)

    def test_rejects_weak_password(self):
        """짧거나 숫자뿐인 비밀번호를 막는다."""
        for weak in ("1234", "password", "aaaaaaaa"):
            with self.subTest(password=weak):
                res = self.signup(password=weak)
                self.assertEqual(res.status_code, 400)

    def test_rejects_password_similar_to_email(self):
        """이메일을 그대로 비밀번호로 쓰면 막는다.

        Django 의 유사성 검사기는 사용자 정보를 받아야 동작한다. 안 넘기면
        그 검사만 조용히 건너뛰어, 이메일과 똑같은 비밀번호가 통과한다.
        """
        res = self.signup(email="kimdev@example.com", password="kimdev@example.com")

        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.json())

    def test_rejects_too_long_email(self):
        """이메일 검사기는 320자까지 통과시키는데 DB 칸은 254자다.

        그 사이 길이가 들어오면 검증은 지나가고 DB 가 거절해 500 이 난다.
        SQLite 는 길이를 안 지켜서 이 테스트만으로는 재현되지 않지만,
        시리얼라이저가 먼저 막는지는 확인할 수 있다.
        """
        res = self.signup(email="a" * 250 + "@example.com")

        self.assertEqual(res.status_code, 400)

    def test_rejects_invalid_email(self):
        res = self.signup(email="이메일아님")

        self.assertEqual(res.status_code, 400)

    def test_new_user_is_not_staff(self):
        """가입만으로 검수 권한이 생기면 안 된다."""
        self.signup()

        user = User.objects.get(email="a@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class LoginTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def login(self, **body):
        payload = {"email": "a@example.com", "password": PASSWORD, **body}
        return self.client.post(LOGIN_URL, payload, content_type="application/json")

    def test_returns_token(self):
        res = self.login()

        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.json())

    def test_rejects_wrong_password(self):
        res = self.login(password="틀린비밀번호")

        self.assertEqual(res.status_code, 400)

    def test_does_not_reveal_whether_email_exists(self):
        """실패 사유가 갈리면 그 응답만으로 가입 여부를 알아낼 수 있다."""
        wrong_password = self.login(password="틀린비밀번호")
        no_such_user = self.login(email="nobody@example.com")

        self.assertEqual(wrong_password.status_code, no_such_user.status_code)
        self.assertEqual(wrong_password.json(), no_such_user.json())

    def test_inactive_user_cannot_login(self):
        """정지된 계정이 로그인되면 정지가 의미를 잃는다."""
        self.user.is_active = False
        self.user.save()

        res = self.login()

        self.assertEqual(res.status_code, 400)

    def test_login_ignores_email_case(self):
        """대문자로 가입한 사람이 소문자로 로그인해도 들어와야 한다.

        저장은 소문자로 내리는데 조회가 정확히 일치를 요구하면, 대문자가
        섞인 행이 하나라도 있을 때 그 계정은 영영 못 들어간다. 사용자는
        비밀번호가 틀렸다고만 듣고 이유를 알 수 없다.
        """
        User.objects.create_user(email="Mixed@Example.com", password=PASSWORD)

        for typed in ("Mixed@Example.com", "mixed@example.com", "MIXED@EXAMPLE.COM"):
            with self.subTest(email=typed):
                res = self.login(email=typed)
                self.assertEqual(res.status_code, 200)

    def test_same_token_on_repeat_login(self):
        """로그인할 때마다 토큰이 새로 생기면 다른 기기가 로그아웃된다."""
        first = self.login().json()["token"]
        second = self.login().json()["token"]

        self.assertEqual(first, second)


class MeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="a@example.com", password=PASSWORD, display_name="테스터"
        )
        cls.other = User.objects.create_user(email="b@example.com", password=PASSWORD)
        cls.token = Token.objects.create(user=cls.user)

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_returns_own_info(self):
        res = self.client.get(ME_URL, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "a@example.com")

    def test_requires_token(self):
        res = self.client.get(ME_URL)

        self.assertEqual(res.status_code, 401)

    def test_rejects_forged_token(self):
        res = self.client.get(ME_URL, HTTP_AUTHORIZATION="Token forged-token-1234")

        self.assertEqual(res.status_code, 401)

    def test_can_update_display_name(self):
        res = self.client.patch(
            ME_URL,
            {"display_name": "새이름"},
            content_type="application/json",
            **self.auth(),
        )

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "새이름")

    def test_cannot_change_email(self):
        """이메일은 로그인 키다. 본인 확인 없이 바꾸면 계정을 넘길 수 있다."""
        self.client.patch(
            ME_URL,
            {"email": "hacker@example.com"},
            content_type="application/json",
            **self.auth(),
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "a@example.com")

    def test_cannot_grant_self_staff(self):
        """스스로 검수 권한을 올리면 미검수 단어를 볼 수 있게 된다."""
        self.client.patch(
            ME_URL,
            {"is_staff": True},
            content_type="application/json",
            **self.auth(),
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def _patch(self, body: dict):
        return self.client.patch(
            ME_URL, body, content_type="application/json", **self.auth()
        )

    def test_name_already_taken_is_rejected(self):
        self.other.display_name = "먼저잡은이름"
        self.other.save()

        res = self._patch({"display_name": "먼저잡은이름"})

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.display_name, "먼저잡은이름")

    def test_name_taken_check_ignores_case(self):
        """대소문자만 바꿔 같은 이름을 또 만들 수 없다.

        허용하면 순위표에서 누가 누구인지 구분이 안 된다.
        """
        self.other.display_name = "Devvoca"
        self.other.save()

        res = self._patch({"display_name": "devvoca"})

        self.assertEqual(res.status_code, 400)

    def test_name_is_trimmed_before_the_taken_check(self):
        """다듬기 전 값으로 중복을 보면 "이름 " 이 통과한다."""
        self.other.display_name = "같은이름"
        self.other.save()

        res = self._patch({"display_name": "  같은이름  "})

        self.assertEqual(res.status_code, 400)

    def test_hidden_characters_cannot_fake_another_name(self):
        """폭 없는 공백을 끼워 남의 이름과 똑같이 보이게 만들 수 없다.

        지우고 나면 같은 이름이 되므로 중복으로 걸린다. 이걸 막지 않으면
        순위표에 똑같이 보이는 두 사람이 생긴다.
        """
        self.other.display_name = "임선오"
        self.other.save()

        # U+200B 폭 없는 공백. 소스에 직접 쓰지 않고 코드포인트로 만든다.
        res = self._patch({"display_name": "임선" + chr(0x200B) + "오"})

        self.assertEqual(res.status_code, 400)

    def test_name_longer_than_the_limit_is_rejected(self):
        """순위표는 이름을 여러 개 늘어놓는 화면이라 길이를 묶어둔다.

        모델의 max_length 에 맡기면 저장할 때 걸려서 500 이 난다.
        """
        res = self._patch({"display_name": "가" * (DISPLAY_NAME_MAX + 1)})

        self.assertEqual(res.status_code, 400)

    def test_name_at_the_limit_is_allowed(self):
        """경계값이 막히면 쓸 수 있는 이름을 못 쓰게 된다."""
        res = self._patch({"display_name": "가" * DISPLAY_NAME_MAX})

        self.assertEqual(res.status_code, 200)

    def test_length_is_counted_after_trimming(self):
        """다듬기 전 값으로 세면 공백 때문에 억울하게 막힌다."""
        res = self._patch({"display_name": "  " + "가" * DISPLAY_NAME_MAX + "  "})

        self.assertEqual(res.status_code, 200)

    def test_blank_name_is_rejected(self):
        """공백만 보내면 이름이 사라진다. save() 가 지어주긴 하지만,
        사용자가 지우려 한 것인지 실수인지 알 수 없으므로 되묻는다."""
        res = self._patch({"display_name": "   "})

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.display_name)

    def test_keeping_own_name_is_allowed(self):
        """자기 이름을 그대로 두고 아바타만 바꾸는 경우가 막히면 안 된다."""
        res = self._patch(
            {"display_name": self.user.display_name, "avatar": "a3"}
        )

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "a3")

    def test_avatar_choice_is_limited(self):
        res = self._patch({"avatar": "../../etc/passwd"})

        self.assertEqual(res.status_code, 400)

    def test_cannot_set_google_picture(self):
        """구글이 주는 값이다. 아무 주소나 넣을 수 있으면 우리 화면을 여는
        것만으로 그 서버에 요청이 나가는 통로가 된다."""
        self._patch({"google_picture": "https://evil.example.com/track.png"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.google_picture, "")

    def test_avatar_display_falls_back_when_there_is_no_photo(self):
        res = self.client.get(ME_URL, **self.auth())

        shown = res.json()["avatar_display"]
        self.assertEqual(shown["type"], "preset")
        self.assertIn(shown["key"], ("a1", "a2", "a3", "a4", "a5", "a6"))


class LogoutTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="a@example.com", password=PASSWORD)

    def test_token_stops_working(self):
        """쿠키만 지우고 토큰을 남기면, 새어나간 토큰이 계속 통한다."""
        token = Token.objects.create(user=self.user)
        auth = {"HTTP_AUTHORIZATION": f"Token {token.key}"}

        res = self.client.post(LOGOUT_URL, **auth)

        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get(ME_URL, **auth).status_code, 401)

    def test_requires_login(self):
        res = self.client.post(LOGOUT_URL)

        self.assertEqual(res.status_code, 401)


class ThrottleTest(TestCase):
    """로그인·가입 시도 제한.

    비율을 여기서 직접 좁힌다. override_settings 로는 안 되는데, DRF 가
    스로틀 인스턴스를 만들 때 설정을 한 번 읽고 굳히기 때문이다.
    """

    def setUp(self):
        # 제한 횟수가 캐시에 쌓여 테스트끼리 영향을 준다.
        cache.clear()

        # rate 는 인스턴스를 만들 때 get_rate() 로 정해진다. 클래스 속성을
        # 덮어써도 생성자가 다시 계산해버리므로 그쪽을 바꾼다.
        patcher = mock.patch.object(
            EmailRateThrottle, "get_rate", return_value="3/min"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, email="a@example.com"):
        return self.client.post(
            LOGIN_URL,
            {"email": email, "password": "틀린비밀번호"},
            content_type="application/json",
        )

    def test_blocks_repeated_login_attempts(self):
        """한 계정의 비밀번호를 무한히 추측할 수 없어야 한다."""
        for _ in range(3):
            self.assertEqual(self.login().status_code, 400)

        self.assertEqual(self.login().status_code, 429)

    def test_counts_per_email_not_per_client(self):
        """한 사람이 막혔다고 다른 사람까지 막히면 안 된다.

        IP 로 세면 모든 요청이 Next 서버 하나로 보여 전원이 한 통에 담긴다.
        그래서 제출된 이메일로 센다.
        """
        for _ in range(3):
            self.login(email="victim@example.com")

        self.assertEqual(self.login(email="other@example.com").status_code, 400)

    def narrow_google_throttle(self):
        """구글 제한을 3회로 좁히고 구글 호출을 막는다.

        막지 않으면 이 머신의 .env 에 키가 있을 때 테스트가 실제로
        구글에 요청을 보낸다. 그러면 통과 이유가 제한이 아니라 구글의
        거절이 되어, 무엇을 확인했는지 알 수 없다.
        """
        rate = mock.patch.object(
            GoogleRateThrottle, "get_rate", return_value="3/min"
        )
        rate.start()
        self.addCleanup(rate.stop)

        google = mock.patch(
            "apps.accounts.views.fetch_google_user",
            side_effect=GoogleAuthError("확인하지 못했습니다."),
        )
        google.start()
        self.addCleanup(google.stop)

    def try_google(self, **extra):
        """구글 로그인을 한 번 시도한다.

        요청마다 코드·주소·브라우저를 다르게 보낸다. 전부 같게 보내면
        그 값들로 통을 나누는 구현도 테스트를 통과한다. 특히 코드로
        나누는 구현이 위험한데, 실제 코드는 매번 달라서 제한이 영영
        안 걸린다.
        """
        self._try_count = getattr(self, "_try_count", 0) + 1
        n = self._try_count

        return self.client.post(
            GOOGLE_URL,
            {"code": f"code-{n}", "redirect_uri": f"{REDIRECT_URI}?v={n}"},
            content_type="application/json",
            REMOTE_ADDR=f"10.0.0.{n}",
            HTTP_USER_AGENT=f"tester/{n}",
            **extra,
        )

    def test_google_throttle_counts_every_account(self):
        """계정별로 세면 계정을 늘려가며 무한히 시도할 수 있다.

        토큰을 붙였다고 아예 안 세는 구현도 있어, 그 경우 계정 하나만
        만들면 제한이 통째로 사라진다.
        """
        self.narrow_google_throttle()

        tokens = []
        for name in ("a", "b"):
            user = User.objects.create_user(
                email=f"{name}@example.com", password=PASSWORD
            )
            tokens.append(Token.objects.create(user=user).key)

        # 계정을 바꿔가며, 중간에 로그인 안 한 채로도 보낸다. 어떻게
        # 나눠 보내도 합쳐서 세야 한다 - 인증 여부로 통을 가르는 구현도
        # 있어서, 토큰 요청만으로는 그것을 잡지 못한다.
        self.try_google(HTTP_AUTHORIZATION=f"Token {tokens[0]}")
        self.try_google(HTTP_AUTHORIZATION=f"Token {tokens[1]}")
        self.try_google()

        res = self.try_google(HTTP_AUTHORIZATION=f"Token {tokens[0]}")

        self.assertEqual(res.status_code, 429)

    def test_google_throttle_ignores_forwarded_header(self):
        """주소를 알려주는 헤더는 아무나 지어낼 수 있다.

        그것으로 통을 나누면 헤더만 바꿔가며 무한히 시도할 수 있다.
        """
        self.narrow_google_throttle()

        for i in range(3):
            self.try_google(HTTP_X_FORWARDED_FOR=f"1.2.3.{i}")

        res = self.try_google(HTTP_X_FORWARDED_FOR="9.9.9.9")

        self.assertEqual(res.status_code, 429)

    def test_case_does_not_bypass(self):
        """대소문자를 바꿔가며 같은 계정을 계속 때릴 수 없어야 한다."""
        for _ in range(3):
            self.login(email="target@example.com")

        res = self.login(email="TARGET@EXAMPLE.COM")

        self.assertEqual(res.status_code, 429)


class GoogleLoginTest(TestCase):
    """구글 로그인.

    구글을 실제로 부르지 않는다. 네트워크가 필요하고, 코드는 한 번만
    쓸 수 있어 테스트를 반복할 수 없다. 구글에 물어보는 부분만 가짜로
    바꾸고 그 뒤 처리를 확인한다.
    """

    def setUp(self):
        # 구글 제한은 통이 하나라 클래스가 달라도 횟수가 이어진다.
        # 비워두지 않으면 나중에 제한을 낮출 때 엉뚱한 테스트가 깨진다.
        cache.clear()

    def google(self, **body):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **body}
        return self.client.post(
            GOOGLE_URL, payload, content_type="application/json"
        )

    def patch_google(
        self,
        email="new@example.com",
        name="구글사용자",
        picture="https://lh3.googleusercontent.com/a/first",
    ):
        """fetch_google_user 가 돌려주는 것과 같은 모양으로 흉내 낸다.

        키를 빠뜨리면 뷰가 KeyError 로 터진다. 그게 맞다 - 실제 함수는
        세 키를 항상 채우므로, 흉내가 그것과 어긋나면 테스트가 통과해도
        의미가 없다.
        """
        return mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": name, "picture": picture},
        )

    def test_creates_account_on_first_login(self):
        with self.patch_google():
            res = self.google()

        self.assertEqual(res.status_code, 201)
        self.assertIn("token", res.json())
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_uses_google_name(self):
        with self.patch_google(name="홍길동"):
            self.google()

        self.assertEqual(
            User.objects.get(email="new@example.com").display_name, "홍길동"
        )

    def test_taken_google_name_gets_a_number(self):
        """동명이인이라고 가입이 막히면 안 된다.

        구글 이름은 사용자가 고른 것이 아니라 받아온 것이라, 실패하면
        본인이 뭘 잘못했는지 알 수 없다.
        """
        User.objects.create_user(
            email="other@example.com", password=PASSWORD, display_name="홍길동"
        )

        with self.patch_google(name="홍길동"):
            res = self.google()

        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            User.objects.get(email="new@example.com").display_name, "홍길동2"
        )

    def test_stores_google_picture(self):
        with self.patch_google(picture="https://lh3.googleusercontent.com/a/x"):
            self.google()

        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.google_picture, "https://lh3.googleusercontent.com/a/x")
        self.assertEqual(
            user.avatar_display,
            {"type": "photo", "url": "https://lh3.googleusercontent.com/a/x"},
        )

    def test_picture_is_refreshed_on_later_logins(self):
        """구글에서 사진을 바꾸면 옛 주소가 죽어 깨진 그림이 남는다."""
        with self.patch_google(picture="https://lh3.googleusercontent.com/a/old"):
            self.google()
        with self.patch_google(picture="https://lh3.googleusercontent.com/a/new"):
            self.google()

        self.assertEqual(
            User.objects.get(email="new@example.com").google_picture,
            "https://lh3.googleusercontent.com/a/new",
        )

    def test_later_logins_keep_the_name_the_user_chose(self):
        """바꾼 이름이 다음 로그인에 구글 이름으로 되돌아가면 안 된다."""
        with self.patch_google(name="구글이름"):
            self.google()

        user = User.objects.get(email="new@example.com")
        user.display_name = "내가정한이름"
        user.save()

        with self.patch_google(name="구글이름"):
            self.google()

        user.refresh_from_db()
        self.assertEqual(user.display_name, "내가정한이름")

    def test_second_login_reuses_account(self):
        with self.patch_google():
            first = self.google()
        with self.patch_google():
            second = self.google()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_links_to_existing_email_account(self):
        """이메일로 가입한 사람이 구글로 들어와도 같은 계정이어야 한다.

        따로 만들면 학습 기록이 두 계정으로 갈리고, 사용자는 자기 기록이
        어디 갔는지 알 수 없다.
        """
        existing = User.objects.create_user(
            email="both@example.com", password=PASSWORD, display_name="원래이름"
        )

        with self.patch_google(email="both@example.com"):
            res = self.google()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(res.json()["user"]["id"], existing.pk)

    def test_login_does_not_cut_other_devices(self):
        """구글로 들어와도 다른 기기가 끊기지 않는다.

        두 방법을 번갈아 쓰는 사람이 있다. PC 에서 이메일로 들어와 있는데
        폰에서 구글로 들어왔다고 PC 가 로그아웃되면 안 된다.
        """
        user = User.objects.create_user(
            email="both@example.com", password=PASSWORD
        )
        token = Token.objects.create(user=user)

        with self.patch_google(email="both@example.com"):
            self.google()

        self.assertEqual(
            self.client.get(
                ME_URL, HTTP_AUTHORIZATION=f"Token {token.key}"
            ).status_code,
            200,
        )

    def test_created_account_has_no_blank_password(self):
        """만드는 도중에 비밀번호가 빈 값인 상태가 없어야 한다.

        빈 문자열은 "쓸 수 있는 비밀번호" 로 판정돼, 그 상태로 로그인을
        시도하면 400 이 아니라 500 이 난다.
        """
        with self.patch_google():
            self.google()

        user = User.objects.get(email="new@example.com")
        self.assertNotEqual(user.password, "")
        self.assertFalse(user.has_usable_password())

        res = self.client.post(
            LOGIN_URL,
            {"email": "new@example.com", "password": ""},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_existing_display_name_is_kept(self):
        """이미 정한 이름을 구글 이름으로 덮어쓰지 않는다."""
        User.objects.create_user(
            email="both@example.com", password=PASSWORD, display_name="내가정한이름"
        )

        with self.patch_google(email="both@example.com", name="구글이름"):
            self.google()

        self.assertEqual(
            User.objects.get(email="both@example.com").display_name, "내가정한이름"
        )

    def test_email_case_does_not_split_account(self):
        """구글이 대문자 섞인 이메일을 줘도 같은 계정으로 모여야 한다."""
        User.objects.create_user(email="mixed@example.com", password=PASSWORD)

        with self.patch_google(email="Mixed@Example.com"):
            res = self.google()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_new_account_cannot_login_with_password(self):
        """구글로 만든 계정에 빈 비밀번호로 들어올 수 없어야 한다."""
        with self.patch_google():
            self.google()

        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.has_usable_password())

    def test_new_account_is_not_staff(self):
        with self.patch_google():
            self.google()

        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.is_staff)

    def test_inactive_account_is_rejected(self):
        User.objects.create_user(
            email="stopped@example.com", password=PASSWORD, is_active=False
        )

        with self.patch_google(email="stopped@example.com"):
            res = self.google()

        self.assertEqual(res.status_code, 400)

    def test_rejects_missing_code(self):
        for body in ({"code": ""}, {"code": None}, {"code": 123}, {"code": []}):
            with self.subTest(body=body):
                self.assertEqual(self.google(**body).status_code, 400)

    def test_rejects_missing_redirect_uri(self):
        self.assertEqual(self.google(redirect_uri="").status_code, 400)

    def test_rejects_non_object_body(self):
        for body in ("[]", '"문자열"', "123", "null"):
            with self.subTest(body=body):
                res = self.client.post(
                    GOOGLE_URL, body, content_type="application/json"
                )
                self.assertEqual(res.status_code, 400)

    def test_google_failure_becomes_400(self):
        """구글이 거절하면 500 이 아니라 안내가 나가야 한다."""
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            side_effect=GoogleAuthError("구글 로그인을 확인하지 못했습니다."),
        ):
            res = self.google()

        self.assertEqual(res.status_code, 400)
        self.assertIn("구글", res.json()["detail"])


class GoogleFetchTest(TestCase):
    """구글에 물어보는 부분.

    확인되지 않은 이메일을 받으면 그 주소의 진짜 주인 계정으로 들어갈
    수 있다. 그 검사가 실제로 도는지 본다.
    """

    def test_rejects_unverified_email(self):
        with mock.patch("apps.accounts.google.httpx.Client") as client:
            ctx = client.return_value.__enter__.return_value
            ctx.post.return_value = mock.Mock(
                status_code=200, json=lambda: {"access_token": "t"}
            )
            ctx.get.return_value = mock.Mock(
                status_code=200,
                json=lambda: {
                    "email": "someone@example.com",
                    "name": "이름",
                    "email_verified": False,
                },
            )

            with self.assertRaises(GoogleAuthError):
                fetch_google_user("code", REDIRECT_URI)

    def test_rejects_missing_email(self):
        with mock.patch("apps.accounts.google.httpx.Client") as client:
            ctx = client.return_value.__enter__.return_value
            ctx.post.return_value = mock.Mock(
                status_code=200, json=lambda: {"access_token": "t"}
            )
            ctx.get.return_value = mock.Mock(
                status_code=200, json=lambda: {"email_verified": True}
            )

            with self.assertRaises(GoogleAuthError):
                fetch_google_user("code", REDIRECT_URI)

    def test_rejects_when_google_refuses_code(self):
        with mock.patch("apps.accounts.google.httpx.Client") as client:
            ctx = client.return_value.__enter__.return_value
            ctx.post.return_value = mock.Mock(status_code=400)

            with self.assertRaises(GoogleAuthError):
                fetch_google_user("code", REDIRECT_URI)

    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_requires_settings(self):
        """키가 없으면 조용히 실패하지 않고 이유를 알려준다."""
        with self.assertRaises(GoogleAuthError):
            fetch_google_user("code", REDIRECT_URI)


class AdminTest(TestCase):
    """Admin 화면이 뜨는지.

    커스텀 User 모델은 Admin 폼과 어긋나기 쉽다. username 자리가 비어
    있어서, 기본 폼을 그대로 쓰면 필드를 못 찾고 화면이 통째로 죽는다.
    실제로 계정 추가 화면이 그렇게 500 이 났다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password=PASSWORD
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_user_list_opens(self):
        self.assertEqual(self.client.get("/admin/accounts/user/").status_code, 200)

    def test_user_add_form_opens(self):
        self.assertEqual(self.client.get("/admin/accounts/user/add/").status_code, 200)

    def test_user_change_form_opens(self):
        res = self.client.get(f"/admin/accounts/user/{self.admin.pk}/change/")

        self.assertEqual(res.status_code, 200)


class UserModelTest(TestCase):
    def test_email_is_the_login_key(self):
        self.assertEqual(User.USERNAME_FIELD, "email")

    def test_create_superuser(self):
        user = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_superuser_must_be_staff(self):
        """is_staff 가 False 인 슈퍼유저는 Admin 에 못 들어간다."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com", password=PASSWORD, is_staff=False
            )

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_email_is_lowercased_on_any_save(self):
        """매니저를 거치지 않는 저장에도 적용돼야 한다.

        Admin 의 계정 추가 폼은 create_user 를 안 거치고 곧바로 save() 를
        부른다. 매니저에만 두면 그 경로로 대문자가 섞인 행이 들어오고,
        같은 주소가 두 행으로 갈려 로그인이 터진다.
        """
        user = User(email="Mixed.Case@Example.COM")
        user.set_password(PASSWORD)
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.email, "mixed.case@example.com")

    def test_blank_name_is_generated_not_taken_from_email(self):
        """이름을 안 적으면 지어준다. 이메일 앞부분을 쓰면 안 된다.

        예전에는 비어 있을 때 화면에서 이메일 앞부분을 대신 보여줬다.
        순위표에 이름이 뜨기 시작하면 그건 남의 메일 주소 절반을 공개하는
        것이 된다.
        """
        user = User.objects.create_user(email="hong@example.com", password=PASSWORD)

        self.assertNotIn("hong", user.display_name)
        self.assertTrue(user.display_name.startswith("학습자"))
        self.assertEqual(user.name_for_display, user.display_name)


class _SchemaEditorStub:
    """create_cache_table 이 실제로 쓰는 것은 connection.alias 하나뿐이다.

    쓰지도 않을 진짜 schema_editor 를 열 이유가 없어 그 자리만 채운다.

    여기 alias 는 항상 "default" 다. 진짜 마이그레이션에서는
    `migrate --database=<alias>` 로 준 값이 온다. 즉 **이 테스트는 alias 를
    제대로 넘기는지는 검증하지 못한다** - 0002 에서 그 자리를 "default" 로
    하드코딩해도 전부 통과한다. DB 가 하나뿐이라 지금은 실피해가 없다.
    """

    connection = connection


class ThrottleCacheTableTest(TransactionTestCase):
    """캐시 테이블이 없으면 무엇이 죽고 무엇이 멀쩡해 보이는지 고정한다.

    2026-08-13 에 이 테이블이 프로덕션에 없어서 가입·로그인·구글 로그인이
    500 이었다. 그때 배포 후 확인표에는 조회 경로만 있어서 전부 초록이었고,
    사용자가 로그인이 안 된다고 알려주고 나서야 드러났다.

    여기서 고정하는 것:
    - 어느 경로가 이 사고를 감지하고 어느 경로가 못 하는가 (DEPLOY.md 확인표의 근거)
    - create_cache_table 이 설정된 테이블을 만드는가
    - 그 함수가 operations 에 실제로 걸려 있는가

    세 번째가 빠지면 이번 사고를 그대로 반복한다. 동작하는 코드가 있어도
    그것을 실행하는 배선이 없으면 아무 일도 일어나지 않는데, 함수를 직접
    부르는 테스트는 그 차이를 못 본다.

    **여전히 검증하지 않는 것**: 프로덕션에 실제로 적용됐는지. 그건 배포 후
    확인표로만 안다. 그리고 동시 실행(레플리카 경합)도 아니다 - 아래는
    순차 재실행만 본다.

    TransactionTestCase 인 이유: 테이블을 지웠다 만드는 DDL 이라 트랜잭션
    안에서 굴리면 뒤 테스트로 샌다.
    """

    def setUp(self):
        self.table = settings.CACHES["default"]["LOCATION"]

    def tearDown(self):
        """다음 테스트가 빈 채로 시작하지 않도록 되돌린다.

        검증 대상인 create_cache_table 을 안 쓰고 관리 명령을 직접 부른다.
        대상 함수가 고장 났을 때 복구까지 같이 고장 나면, 실패가 엉뚱한
        테스트에서 터져 원인을 못 찾는다.
        """
        call_command("createcachetable", verbosity=0)

    def _table_exists(self) -> bool:
        return self.table in connection.introspection.table_names()

    def _drop_table(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE %s" % connection.ops.quote_name(self.table))

    def test_the_function_is_wired_into_operations(self):
        """0002 의 operations 가 비면 함수가 멀쩡해도 테이블은 안 생긴다.

        아래 테스트들은 함수를 직접 부르므로 이 경우를 못 잡는다. 이번
        사고의 자리가 정확히 여기였다 - `release:` 줄에 명령은 적혀 있었고,
        그 줄을 실행하는 쪽이 없었다.
        """
        operations = cache_table_migration.Migration.operations

        self.assertEqual(len(operations), 1)
        self.assertIs(operations[0].code, create_cache_table)

    def test_the_function_creates_the_configured_table(self):
        self._drop_table()
        self.assertFalse(self._table_exists())

        create_cache_table(None, _SchemaEditorStub())

        self.assertTrue(self._table_exists())

    def test_running_it_twice_is_safe(self):
        """이미 있는 테이블 위에서 다시 돌아도 괜찮아야 한다.

        프로덕션이 실제로 그 상태였다 - 급한 대로 손으로 만들어두고
        마이그레이션은 그다음 배포에 처음 적용됐다.

        동시 실행은 다른 이야기다. 여기서는 순차 재실행만 본다.
        """
        create_cache_table(None, _SchemaEditorStub())
        create_cache_table(None, _SchemaEditorStub())

        self.assertTrue(self._table_exists())

    def test_auth_paths_break_and_the_rest_looks_fine(self):
        """DEPLOY.md 확인표가 이 결과에 기대고 있다.

        조회 경로는 요청 제한을 안 거쳐서 테이블이 없어도 200 이다.
        me/ 도 마찬가지다 - 요청 제한이 아예 안 붙어 있고, 붙어 있더라도
        권한 검사가 먼저라 거기까지 가지 않는다. 즉 **이 셋만 보면 사고를
        못 잡는다.** 확인표에 로그인·구글이 있어야 하는 이유다.

        DatabaseError 로 잡는 이유: 없는 테이블에 대한 예외가 엔진마다
        다르다. SQLite 는 OperationalError, PostgreSQL 은 ProgrammingError 고
        둘은 상속 관계가 아닌 형제다. 한쪽으로 적으면 다른 엔진에서 깨진다.
        """
        self._drop_table()

        self.assertEqual(self.client.get("/api/vocab/words/").status_code, 200)
        self.assertEqual(self.client.get(ME_URL).status_code, 401)

        # 본문은 DEPLOY.md 가 시키는 것과 같아야 한다. 다르면 문서가 썩는다.
        for url, body in (
            (GOOGLE_URL, {}),
            (LOGIN_URL, {"email": "nobody@example.com", "password": "x"}),
        ):
            with self.subTest(url=url), self.assertRaises(DatabaseError):
                self.client.post(url, body, content_type="application/json")

    def test_login_without_email_does_not_touch_the_cache(self):
        """확인용 요청에 email 을 꼭 넣어야 하는 이유.

        캐시 키를 이메일로 만들기 때문에, 이메일이 없으면 키가 None 이 되고
        요청 제한은 캐시를 건드리지 않고 통과한다. 그 상태로는 400 이 나와도
        아무것도 확인하지 못한 것이다.

        이 테스트만으로는 "이메일이 없어서" 와 "요청 제한이 아예 없어서" 를
        구분하지 못한다. 제한이 붙어 있다는 것은 ThrottleTest 가 본다.
        """
        self._drop_table()

        response = self.client.post(
            LOGIN_URL, {"password": "x"}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)


class DisplayNameMigrationOrderTest(TestCase):
    """이름 길이를 줄이는 순서를 고정한다.

    처음에는 컬럼 축소가 데이터 정리보다 앞에 있었다. PostgreSQL 은 그
    자리에서 "value too long" 으로 멈추고 컨테이너가 아예 안 뜬다.
    SQLite 는 max_length 를 강제하지 않아 테스트가 통과해버린다 - 즉
    실행해보는 것만으로는 이 순서를 지킬 수 없다.

    그래서 실행이 아니라 마이그레이션의 모양을 본다. 누가 순서를 되돌리면
    엔진과 무관하게 여기서 걸린다.
    """

    def _operations_of(self, name: str):
        module = import_module(f"apps.accounts.migrations.{name}")
        return module.Migration.operations

    def _alters_display_name_length(self, operations) -> list[int]:
        return [
            i
            for i, op in enumerate(operations)
            if isinstance(op, migrations.AlterField)
            and op.name == "display_name"
            and op.field.max_length == DISPLAY_NAME_MAX
        ]

    def test_the_column_shrinks_after_the_data_is_cleaned(self):
        names = [m.name for m in MigrationLoader(None).disk_migrations.values()
                 if m.app_label == "accounts"]

        cleanup = next(n for n in names if "fill_display_names" in n)
        shrink = next(
            n for n in names if self._alters_display_name_length(self._operations_of(n))
        )

        self.assertLess(
            cleanup, shrink,
            "데이터를 자르기 전에 컬럼이 좁아지면 PostgreSQL 배포가 멈춘다",
        )

    def test_the_constraint_comes_after_the_shrink(self):
        """같은 파일 안에서도 순서가 있다. 제약이 먼저면 12자로 못 줄인다."""
        operations = self._operations_of("0005_alter_user_display_name_and_more")

        shrink_at = self._alters_display_name_length(operations)[0]
        constraint_at = next(
            i for i, op in enumerate(operations)
            if isinstance(op, migrations.AddConstraint)
        )

        self.assertLess(shrink_at, constraint_at)


class DisplayNameRulesTest(TestCase):
    """이름 규칙이 모든 경로에서 같은지 본다.

    가입·프로필 수정·구글 로그인이 각자 다른 판정을 쓰면, 한쪽에서 되는
    이름이 다른 쪽에서 안 되거나 엉뚱한 안내가 나간다.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD, display_name="임선오"
        )

    def signup(self, **body):
        payload = {"email": "new@example.com", "password": PASSWORD, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def test_signup_says_the_name_is_taken_not_the_email(self):
        """이름이 겹쳤는데 "이미 가입된 이메일" 이 뜨면, 사용자는 멀쩡한
        이메일을 바꿔가며 계속 실패한다."""
        res = self.signup(display_name="임선오")

        self.assertEqual(res.status_code, 400)
        self.assertIn("display_name", res.json())
        self.assertNotIn("email", res.json())

    def test_signup_trims_the_name(self):
        res = self.signup(display_name="  새이름  ")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            User.objects.get(email="new@example.com").display_name, "새이름"
        )

    def test_signup_counts_length_after_trimming(self):
        """다듬기 전 값으로 세면 공백 때문에 억울하게 막힌다."""
        res = self.signup(display_name="  " + "가" * DISPLAY_NAME_MAX + "  ")

        self.assertEqual(res.status_code, 201)

    def test_signup_rejects_a_name_over_the_limit(self):
        res = self.signup(display_name="가" * (DISPLAY_NAME_MAX + 1))

        self.assertEqual(res.status_code, 400)

    def test_combining_jamo_cannot_impersonate(self):
        """한글은 같은 글자를 완성형으로도 자모 조합으로도 쓸 수 있다.

        모아주지 않으면 화면에서 구별할 수 없는 두 이름이 생긴다.
        """
        # "임선오" 를 자모로 푼 것. 소스에 붙여넣지 않고 여기서 만든다.
        decomposed = unicodedata.normalize("NFD", "임선오")
        self.assertNotEqual(decomposed, "임선오")

        res = self.signup(display_name=decomposed)

        self.assertEqual(res.status_code, 400)

    def test_combining_jamo_does_not_inflate_the_length(self):
        """자모는 글자당 셋이라, 모으지 않으면 네 글자가 12자로 세어진다."""
        res = self.signup(display_name=unicodedata.normalize("NFD", "가나다라"))

        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            User.objects.get(email="new@example.com").display_name, "가나다라"
        )

    def test_truncating_does_not_leave_a_trailing_space(self):
        """자르는 위치가 공백이면 검사한 값과 저장되는 값이 달라진다.

        그대로 두면 중복 검사는 통과하고, 저장 직전 정리에서 기존 이름과
        부딪혀 구글 로그인이 500 이 된다.
        """
        User.objects.create_user(
            email="x@example.com", password=PASSWORD, display_name="abcdefghijk"
        )

        picked = free_display_name("abcdefghijk zzz")

        self.assertEqual(picked, picked.strip())
        self.assertNotEqual(picked.lower(), "abcdefghijk")

    def test_taken_check_uses_the_same_folding_as_the_database(self):
        """파이썬은 upper, DB 는 lower 로 접으면 판정이 갈린다.

        갈리면 파이썬은 통과시키고 DB 가 거절해, 사용자는 이유를 알 수 없는
        오류를 받는다. 켈빈 기호가 그 예다 - lower 하면 k 가 된다.
        """
        User.objects.create_user(
            email="k@example.com", password=PASSWORD, display_name="kelvin"
        )

        self.assertTrue(name_taken("Kelvin"))


class EmailChangeTest(TestCase):
    """이메일 변경. 확인 링크를 눌러야 바뀐다.

    여기서 봐야 할 것은 "바꿀 수 있는가" 가 아니라 **"바꿀 수 없어야 할 때
    막히는가"** 다. 이메일은 로그인 키라, 뚫리면 계정이 통째로 넘어간다.
    """

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="old@example.com", password=PASSWORD, display_name="주인"
        )
        self.token = Token.objects.create(user=self.user)

    def request_change(self, **body):
        payload = {
            "new_email": "new@example.com",
            "current_password": PASSWORD,
            **body,
        }
        return self.client.post(
            EMAIL_CHANGE_URL,
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def confirm(self, token):
        return self.client.post(
            EMAIL_CHANGE_CONFIRM_URL,
            {"token": token},
            content_type="application/json",
        )

    def issued_token(self):
        """신청을 한 번 하고 메일에 실린 토큰을 꺼낸다."""
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            self.request_change()
        body = sent.call_args.kwargs["body"]
        # 링크의 마지막 조각이 토큰이다.
        return body.split("/profile/email/")[1].split()[0]

    def test_신청만으로는_주소가_안_바뀐다(self):
        """확인 전에 바뀌면 링크를 두는 의미가 없다."""
        with mock.patch("apps.accounts.views.send_account_mail"):
            res = self.request_change()

        self.assertEqual(res.status_code, 202)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_확인_메일은_새_주소로_간다(self):
        """옛 주소로 가면 새 주소의 주인임을 증명하지 못한다."""
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            self.request_change()

        self.assertEqual(sent.call_args.kwargs["to"], "new@example.com")

    def test_링크를_누르면_바뀐다(self):
        res = self.confirm(self.issued_token())

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_비밀번호가_틀리면_메일이_안_나간다(self):
        """자리를 비운 사이 남이 제 주소로 변경을 걸어두는 것을 막는다.

        링크는 새 주소의 주인임만 증명한다. 화면 앞의 사람이 계정 주인인지는
        비밀번호가 증명한다.
        """
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(current_password="틀린비밀번호")

        self.assertEqual(res.status_code, 400)
        sent.assert_not_called()

    def test_로그인_없이는_신청할_수_없다(self):
        res = self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": "x@example.com", "current_password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_이미_가입된_주소로는_못_바꾼다(self):
        User.objects.create_user(
            email="taken@example.com", password=PASSWORD, display_name="선점"
        )
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(new_email="taken@example.com")

        self.assertEqual(res.status_code, 400)
        sent.assert_not_called()

    def test_신청_뒤_남이_그_주소로_가입하면_거절된다(self):
        """토큰이 유효해도 쓰는 시점에 다시 봐야 한다.

        안 보면 save 가 IntegrityError 로 500 이 난다.
        """
        token = self.issued_token()
        User.objects.create_user(
            email="new@example.com", password=PASSWORD, display_name="새치기"
        )

        res = self.confirm(token)

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_묵혀둔_링크로_주소를_되돌릴_수_없다(self):
        """a→b 링크를 받아두고 a→c 로 바꾼 뒤 b 링크를 누르는 경우.

        막지 않으면 사용자가 바꾼 적 없는 주소로 계정이 옮겨간다. 그것도
        나중에야 안다.
        """
        stale = self.issued_token()

        # 그 사이 다른 주소로 바꾼다.
        self.user.email = "other@example.com"
        self.user.save(update_fields=["email"])

        res = self.confirm(stale)

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "other@example.com")

    def test_같은_링크를_두_번_쓸_수_없다(self):
        token = self.issued_token()
        self.assertEqual(self.confirm(token).status_code, 200)

        # 두 번째는 옛 주소가 안 맞아 걸린다.
        self.assertEqual(self.confirm(token).status_code, 400)

    def test_손댄_토큰은_거절된다(self):
        token = self.issued_token()

        self.assertEqual(self.confirm(token + "x").status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_만료된_링크는_거절된다(self):
        token = self.issued_token()

        # 수명을 0 으로 두면 방금 만든 토큰도 만료로 읽힌다.
        with mock.patch("apps.accounts.email_change.TOKEN_MAX_AGE", 0):
            res = self.confirm(token)

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_바꾸면_다른_기기의_토큰이_끊긴다(self):
        """이메일이 바뀌는 것은 계정 주인이 바뀔 수 있는 사건이다."""
        other_device = Token.objects.create(
            user=User.objects.create_user(
                email="zzz@example.com", password=PASSWORD, display_name="남"
            )
        )
        old_key = self.token.key

        res = self.confirm(self.issued_token())

        self.assertEqual(res.status_code, 200)
        # 옛 토큰은 사라진다.
        self.assertFalse(Token.objects.filter(key=old_key).exists())
        # 새 토큰을 받아 링크를 누른 기기는 이어서 쓴다.
        self.assertTrue(res.json()["token"])
        # 남의 토큰까지 지우면 안 된다.
        self.assertTrue(Token.objects.filter(key=other_device.key).exists())

    def test_지금_쓰는_주소로는_못_바꾼다(self):
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.request_change(new_email="old@example.com")

        self.assertEqual(res.status_code, 400)
        sent.assert_not_called()

    def test_구글_전용_계정은_비밀번호를_먼저_설정하라고_안내한다(self):
        """비밀번호가 없는 계정에 "비밀번호가 틀렸다" 고만 하면 안 된다.

        사용자는 만든 적 없는 비밀번호를 계속 찾게 된다.
        """
        google_user = User.objects.create_user(
            email="g@example.com", password=None, display_name="구글"
        )
        google_token = Token.objects.create(user=google_user)

        res = self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": "gnew@example.com", "current_password": "무엇이든"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {google_token.key}",
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("비밀번호", str(res.json()))

    def test_메일이_안_나가면_실패로_알린다(self):
        """조용히 성공으로 넘기면 사용자는 오지 않을 메일을 기다린다."""
        with mock.patch(
            "apps.accounts.views.send_account_mail",
            side_effect=MailNotConfigured("설정 없음"),
        ):
            res = self.request_change()

        self.assertEqual(res.status_code, 503)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")

    def test_정지된_계정은_링크로_되살아나지_않는다(self):
        """확인 경로가 새 토큰을 발급하므로 여기서 막아야 한다.

        정지 직전에 신청해둔 링크가 24시간 살아 있다. 그것을 누르면
        이메일이 바뀌고 새 토큰이 나가, 관리자가 끊은 계정이 되살아난다.
        기존 토큰을 지우는 것으로는 못 막는다 - 이 경로가 새로 내준다.
        """
        token = self.issued_token()

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        res = self.confirm(token)

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "old@example.com")
        self.assertNotIn("token", res.json())

    def test_저장이_부딪혀도_500_이_아니다(self):
        """검사와 저장 사이에 남이 그 주소를 가져간 경우.

        위쪽 exists() 검사를 통과한 뒤 save() 에서 부딪히는 창이다. 그
        자리를 savepoint 로 감싸지 않으면, 잡아서 400 을 돌려주려 해도
        바깥 atomic 이 깨져 500 이 된다.

        검사를 건너뛰게 만들어 그 창을 강제로 연다.
        """
        token = self.issued_token()
        User.objects.create_user(
            email="new@example.com", password=PASSWORD, display_name="새치기"
        )

        # exists() 검사만 통과시키고 save() 는 실제 DB 제약에 부딪히게 둔다.
        with mock.patch.object(
            User.objects, "filter", side_effect=lambda *a, **k: _NeverExists()
        ):
            res = self.confirm(token)

        self.assertEqual(res.status_code, 400)
        self.assertIn("이미 가입된", str(res.json()))


class _NeverExists:
    """exists() 가 항상 False 인 가짜 queryset.

    "검사는 통과했는데 저장에서 부딪히는" 창을 만들기 위한 것이다.
    exclude 도 자기 자신을 돌려줘 체이닝을 받아낸다.
    """

    def exists(self):
        return False

    def exclude(self, *args, **kwargs):
        return self

    def delete(self):
        return (0, {})


class EmailChangeThrottleScopeTest(TestCase):
    """신청과 확인이 서로 다른 통을 쓰는지.

    합쳐두면 아무나 확인 엔드포인트에 쓰레기를 던져 통을 태우는 것만으로
    **모두의 이메일 변경 신청**을 막을 수 있다. 확인 쪽은 로그인이 없어
    통 하나를 전원이 나눠 쓰기 때문이다.
    """

    def setUp(self):
        cache.clear()

    def test_신청과_확인이_다른_통을_쓴다(self):
        from .throttles import EmailChangeConfirmThrottle, EmailChangeThrottle

        self.assertNotEqual(
            EmailChangeThrottle.scope, EmailChangeConfirmThrottle.scope
        )

    def test_확인_쪽_통이_더_넉넉하다(self):
        """좁게 잡으면 그 통이 전원을 막는 스위치가 된다.

        **운영 값을 읽는다.** settings 는 테스트로 돌 때 두 통을 다
        2000/min 으로 올리므로(다른 통들과 같은 방식), 실행 중 값을 보면
        둘이 같아 아무것도 검증하지 못한다. sys.argv 를 잠시 비워 settings
        모듈을 운영 조건으로 다시 읽는다.
        """
        import importlib
        import sys

        real_argv = sys.argv
        sys.argv = ["gunicorn"]
        try:
            prod = importlib.reload(
                importlib.import_module("config.settings")
            ).REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        finally:
            sys.argv = real_argv
            # 다른 테스트가 실행 중 값을 보므로 되돌려 놓는다.
            importlib.reload(importlib.import_module("config.settings"))

        def per_min(scope):
            return int(prod[scope].partition("/")[0])

        self.assertGreater(
            per_min("email_change_confirm"), per_min("email_change")
        )

    def test_익명_신청은_세지_않는다(self):
        """401 로 끝날 요청이 통을 채우면 그것이 전원을 막는다."""
        from rest_framework.test import APIRequestFactory

        from .throttles import EmailChangeThrottle

        request = APIRequestFactory().post(EMAIL_CHANGE_URL)
        request.user = None

        self.assertIsNone(EmailChangeThrottle().get_cache_key(request, None))
def _png(size=(600, 400), mode="RGB", color=(200, 80, 40)):
    """테스트용 이미지 바이트. 실제 Pillow 가 만든 진짜 파일이다."""
    from PIL import Image

    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format="PNG")
    return out.getvalue()


def _big_png():
    """상한을 넘는 **진짜 사진**.

    사진이 아닌 바이트를 늘려 쓰면 안 된다. 그건 상한을 지워도 "사진
    파일을 읽을 수 없습니다" 로 거절되므로, 테스트는 통과하는데 정작
    상한은 검사되지 않는다. 실제로 그렇게 짰다가 상한 두 곳을 모두
    지워도 117개가 다 초록이었다.

    잡음으로 채우는 이유: PNG 는 무손실 압축이라 단색으로 만들면 아무리
    크게 잡아도 몇 KB 로 줄어든다. 잡음은 압축이 안 먹어서 픽셀 수만큼
    커진다.
    """
    from PIL import Image

    side = 1600
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    out = io.BytesIO()
    image.save(out, format="PNG")
    assert len(out.getvalue()) > AVATAR_PHOTO_MAX_BYTES
    return out.getvalue()


def _upload(data, name="photo.png", content_type="image/png"):
    return SimpleUploadedFile(name, data, content_type=content_type)


class AvatarPhotoShrinkTest(TestCase):
    """줄이는 함수 자체. 뷰를 거치지 않고 본다."""

    def test_shrinks_to_square_webp(self):
        out = shrink_avatar_photo(_png(size=(1200, 800)))

        from PIL import Image

        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (AVATAR_PHOTO_SIZE, AVATAR_PHOTO_SIZE))

    def test_result_is_much_smaller(self):
        """원본을 그대로 넣지 않는다는 것을 값으로 확인한다.

        크기를 안 줄이면 행 하나가 폰 사진만큼 커진다. 그것을 막는 것이
        이 함수의 존재 이유라 여기서 못 박는다.
        """
        raw = _png(size=(2000, 2000))
        out = shrink_avatar_photo(raw)

        self.assertLess(len(out), len(raw))
        # 256px WebP 는 넉넉히 잡아도 이 아래다.
        self.assertLess(len(out), 100 * 1024)

    def test_keeps_transparency(self):
        """투명한 PNG 의 투명한 부분이 검게 안 변한다.

        JPEG 로 저장했으면 여기가 깨진다. 형식을 WebP 로 정한 이유가
        이것이라, 형식을 바꾸려는 사람이 이 테스트를 만나게 둔다.
        """
        from PIL import Image

        source = io.BytesIO()
        Image.new("RGBA", (400, 400), (255, 0, 0, 0)).save(source, format="PNG")

        out = shrink_avatar_photo(source.getvalue())

        with Image.open(io.BytesIO(out)) as image:
            self.assertEqual(image.mode, "RGBA")
            # 가운데 점이 투명한 채로 남아 있어야 한다.
            self.assertEqual(image.convert("RGBA").getpixel((128, 128))[3], 0)

    def test_rejects_non_image(self):
        """확장자만 사진인 파일을 막는다.

        Content-Type 이나 이름을 믿으면 아무 파일이나 통과한다.
        """
        with self.assertRaises(AvatarPhotoError):
            shrink_avatar_photo(b"this is not a picture, just bytes" * 100)

    def test_rejects_truncated_image(self):
        """머리말만 멀쩡하고 내용이 잘린 파일도 막는다."""
        raw = _png()
        with self.assertRaises(AvatarPhotoError):
            shrink_avatar_photo(raw[: len(raw) // 3])

    def test_rejects_empty(self):
        with self.assertRaises(AvatarPhotoError):
            shrink_avatar_photo(b"")

    def test_rejects_oversized(self):
        """상한을 넘으면 Pillow 로 열기 전에 막는다.

        열 수 있는 진짜 사진으로 본다. 사진이 아닌 바이트로 보면 상한이
        없어도 "읽을 수 없다" 로 거절돼, 상한을 지워도 테스트가 통과한다.
        """
        with self.assertRaises(AvatarPhotoError) as caught:
            shrink_avatar_photo(_big_png())

        self.assertIn("MB", str(caught.exception))


class AvatarPhotoUploadTest(TestCase):
    """올리기·지우기 API."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="p@example.com", password=PASSWORD, display_name="사진사"
        )
        self.token = Token.objects.create(user=self.user)

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_upload_saves_and_selects_photo(self):
        res = self.client.post(PHOTO_URL, {"photo": _upload(_png())}, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar_photo)
        self.assertEqual(self.user.avatar, AVATAR_PHOTO)
        self.assertIsNotNone(self.user.avatar_photo_at)
        self.assertIsNotNone(self.user.avatar_photo_key)
        # 무엇을 그릴지도 사진으로 바뀌어 있어야 한다. 이것이 안 바뀌면
        # 사진은 올라갔는데 화면은 그대로다.
        self.assertEqual(res.json()["avatar_display"]["type"], "photo")

    def test_upload_requires_login(self):
        res = self.client.post(PHOTO_URL, {"photo": _upload(_png())})

        self.assertEqual(res.status_code, 401)

    def test_upload_rejects_non_image(self):
        evil = _upload(b"not an image at all", name="evil.jpg", content_type="image/jpeg")

        res = self.client.post(PHOTO_URL, {"photo": evil}, **self.auth())

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_photo)

    def test_upload_rejects_oversized(self):
        """상한을 넘는 파일은 안내와 함께 거절된다.

        여기도 진짜 사진이어야 한다(_big_png 주석 참고).
        """
        res = self.client.post(
            PHOTO_URL, {"photo": _upload(_big_png(), name="big.png")}, **self.auth()
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("MB", str(res.json()))
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_photo)

    def test_upload_stores_shrunk_bytes(self):
        """DB 에 들어간 것이 원본이 아니라 줄인 것인지 본다."""
        raw = _png(size=(1600, 1600))

        self.client.post(PHOTO_URL, {"photo": _upload(raw)}, **self.auth())

        self.user.refresh_from_db()
        self.assertLess(len(bytes(self.user.avatar_photo)), len(raw))

    def test_delete_reverts_to_avatar(self):
        """지우면 사진도 선택도 사라진다.

        선택을 안 비우면 avatar 가 photo 인 채로 남아, 사용자가 예전에
        골라둔 아바타가 아니라 계정 고정 아바타가 나온다.
        """
        self.client.post(PHOTO_URL, {"photo": _upload(_png())}, **self.auth())

        res = self.client.delete(PHOTO_URL, **self.auth())

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.avatar_photo)
        self.assertIsNone(self.user.avatar_photo_at)
        self.assertIsNone(self.user.avatar_photo_key)
        self.assertEqual(self.user.avatar, "")
        self.assertEqual(res.json()["avatar_display"]["type"], "preset")

    def test_delete_keeps_chosen_preset(self):
        """아바타를 골라둔 사람이 사진을 지워도 그 아바타는 남는다."""
        self.client.post(PHOTO_URL, {"photo": _upload(_png())}, **self.auth())
        self.user.refresh_from_db()
        self.user.avatar = "a4"
        self.user.save(update_fields=["avatar"])

        self.client.delete(PHOTO_URL, **self.auth())

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "a4")

    def test_delete_requires_login(self):
        res = self.client.delete(PHOTO_URL)

        self.assertEqual(res.status_code, 401)

    def test_can_switch_back_to_preset_with_photo_kept(self):
        """사진을 남긴 채 아바타로 바꿨다가 다시 사진으로 돌아올 수 있다.

        한 번 올리면 못 돌아가는 상태를 막는 것이 요구사항이다.
        """
        self.client.post(PHOTO_URL, {"photo": _upload(_png())}, **self.auth())

        self.client.patch(
            ME_URL, {"avatar": "a2"}, content_type="application/json", **self.auth()
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar_photo)

        res = self.client.patch(
            ME_URL,
            {"avatar": AVATAR_PHOTO},
            content_type="application/json",
            **self.auth(),
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["avatar_display"]["type"], "photo")

    def test_cannot_select_photo_without_one(self):
        """사진이 없는데 올린 사진을 고르면 막힌다."""
        res = self.client.patch(
            ME_URL,
            {"avatar": AVATAR_PHOTO},
            content_type="application/json",
            **self.auth(),
        )

        self.assertEqual(res.status_code, 400)

    def test_me_does_not_carry_photo_bytes(self):
        """/me/ 응답에 그림 바이트가 실리지 않는다.

        이 응답은 화면을 그릴 때마다 불린다. base64 로 실으면 매번 수십
        KB 가 오간다. 주소만 나가는지 본다.
        """
        self.client.post(PHOTO_URL, {"photo": _upload(_png())}, **self.auth())

        res = self.client.get(ME_URL, **self.auth())

        body = res.json()
        self.assertNotIn("avatar_photo", body)
        self.assertNotIn("avatar_photo_key", body)
        self.assertTrue(body["uploaded_photo"].startswith("/api/accounts/photo/"))
        # 응답 전체가 작아야 한다. 그림이 섞이면 이 선을 훌쩍 넘는다.
        self.assertLess(len(res.content), 2000)


class AvatarPhotoFileTest(TestCase):
    """그림을 내려주는 엔드포인트."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="f@example.com", password=PASSWORD, display_name="주인"
        )
        self.token = Token.objects.create(user=self.user)
        self.client.post(
            PHOTO_URL,
            {"photo": _upload(_png())},
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )
        self.user.refresh_from_db()
        self.url = f"/api/accounts/photo/{self.user.avatar_photo_key}/"

    def test_serves_webp_without_login(self):
        """로그인 없이 열린다. 순위표가 남의 아바타를 그린다."""
        res = self.client.get(self.url)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/webp")
        self.assertTrue(res.content.startswith(b"RIFF"))

    def test_address_is_not_the_user_id(self):
        """주소에 pk 가 안 들어간다.

        pk 면 1번부터 눌러보는 것만으로 사진 올린 계정을 전부 훑을 수
        있다. 그것을 막으려고 UUID 로 둔 것이라, 주소 형태가 도로
        연번이 되면 방어가 사라진다.
        """
        self.assertNotIn(f"/{self.user.pk}/", self.user.avatar_photo_url)
        self.assertIn(str(self.user.avatar_photo_key), self.user.avatar_photo_url)

    def test_user_id_in_the_address_does_not_work(self):
        """pk 를 넣어 부르면 안 열린다."""
        res = self.client.get(f"/api/accounts/photo/{self.user.pk}/")

        self.assertEqual(res.status_code, 404)

    def test_old_address_dies_when_photo_changes(self):
        """사진을 바꾸면 옛 주소가 죽는다.

        값을 고정하면 옛 주소를 아는 사람이 바뀐 사진도 계속 본다.
        """
        old_url = self.url

        self.client.post(
            PHOTO_URL,
            {"photo": _upload(_png(color=(10, 200, 90)))},
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.user.refresh_from_db()
        self.assertNotEqual(
            f"/api/accounts/photo/{self.user.avatar_photo_key}/", old_url
        )
        self.assertEqual(self.client.get(old_url).status_code, 404)

    def test_repeats_are_not_resent(self):
        """같은 그림을 두 번 내려보내지 않는다."""
        first = self.client.get(self.url)

        again = self.client.get(self.url, HTTP_IF_NONE_MATCH=first["ETag"])

        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")

    def test_etag_follows_the_timestamp(self):
        """ETag 가 올린 시각을 따라간다.

        사진을 바꾸면 주소 자체가 달라지므로(avatar_photo_key) 캐시는
        그쪽에서 이미 깨진다. 여기서 보는 것은 **같은 주소**에서 내용이
        달라지는 경우다 - 값이 안 따라오면 304 를 잘못 내보낸다.
        """
        first = self.client.get(self.url)["ETag"]

        # 시각이 초 단위라 같은 초에 두 번 올리면 값이 같다. 직접 옮긴다.
        self.user.avatar_photo_at = self.user.avatar_photo_at + timedelta(seconds=5)
        self.user.save(update_fields=["avatar_photo_at"])

        self.assertNotEqual(self.client.get(self.url)["ETag"], first)

    def test_unknown_key_is_404(self):
        res = self.client.get(f"/api/accounts/photo/{uuid.uuid4()}/")

        self.assertEqual(res.status_code, 404)

    def test_malformed_key_is_404(self):
        """UUID 가 아닌 값은 경로에서 걸러진다."""
        res = self.client.get("/api/accounts/photo/999999/")

        self.assertEqual(res.status_code, 404)

    def test_key_is_gone_after_delete(self):
        """지우면 주소 값도 사라져 그 주소가 죽는다."""
        old_url = self.url

        self.client.delete(PHOTO_URL, HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.user.refresh_from_db()
        self.assertIsNone(self.user.avatar_photo_key)
        self.assertEqual(self.client.get(old_url).status_code, 404)

    def test_inactive_user_photo_is_hidden(self):
        """탈퇴한 계정의 사진은 주소로도 안 열린다.

        순위표에서는 사라졌는데 주소로는 계속 열리면 지운 것이 아니다.
        """
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_dead_token_still_gets_the_image(self):
        """쿠키에 죽은 토큰이 있어도 그림은 온다.

        인증을 켜두면 여기서 401 이 나고, 화면은 그림만 안 뜬다.
        """
        res = self.client.get(self.url, HTTP_AUTHORIZATION="Token dead-token-9999")

        self.assertEqual(res.status_code, 200)


class AvatarDisplayPhotoTest(TestCase):
    """무엇을 그릴지 정하는 규칙에 사진이 끼어든 뒤."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="d@example.com", password=PASSWORD, display_name="규칙"
        )

    def _give_photo(self):
        self.user.avatar_photo = b"x"
        self.user.avatar_photo_key = uuid.uuid4()
        self.user.avatar_photo_at = timezone.now()
        self.user.save(
            update_fields=["avatar_photo", "avatar_photo_key", "avatar_photo_at"]
        )

    def test_photo_wins_over_google_when_nothing_chosen(self):
        """아무것도 안 골랐으면 올린 사진이 구글 사진보다 앞선다."""
        self.user.google_picture = "https://example.com/g.png"
        self.user.save(update_fields=["google_picture"])
        self._give_photo()

        shown = self.user.avatar_display

        self.assertEqual(shown["type"], "photo")
        self.assertIn("/api/accounts/photo/", shown["url"])

    def test_chosen_preset_wins_over_photo(self):
        """아바타를 골라뒀으면 사진이 있어도 그 아바타가 나온다."""
        self._give_photo()
        self.user.avatar = "a5"
        self.user.save(update_fields=["avatar"])

        self.assertEqual(self.user.avatar_display, {"type": "preset", "key": "a5"})

    def test_falls_back_when_photo_is_gone(self):
        """사진을 고른 채 사진이 없어져도 화면이 비지 않는다."""
        self.user.avatar = AVATAR_PHOTO
        self.user.save(update_fields=["avatar"])

        self.assertEqual(self.user.avatar_display["type"], "preset")

    def test_url_changes_when_photo_changes(self):
        """사진을 바꾸면 주소도 바뀐다. 안 바뀌면 옛 그림이 남는다."""
        self._give_photo()
        first = self.user.avatar_display["url"]

        self._give_photo()

        self.assertNotEqual(self.user.avatar_display["url"], first)


class AuthQueryWeightTest(TestCase):
    """인증이 사진 바이트를 끌고 오지 않는지.

    models.py 의 avatar_photo 주석이 "어느 질의에도 안 실어서 푼다" 고
    적어뒀는데, 그 불변식이 실제로 서는지 보는 자리다.

    **응답 크기로는 못 잡는다.** 이미 있는 test_me_does_not_carry_photo_bytes
    는 JSON 이 작은지만 보는데, 직렬화에서 빠져도 DB 에서 앱까지는 이미
    실려온 뒤다. 그래서 질의문 자체를 본다.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="weight@example.com", password=PASSWORD, display_name="무게"
        )
        self.token = Token.objects.create(user=self.user)

    def test_인증_질의가_사진_칸을_안_읽는다(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(
                ME_URL, HTTP_AUTHORIZATION=f"Token {self.token.key}"
            )
        self.assertEqual(res.status_code, 200)

        auth_queries = [
            q["sql"] for q in ctx.captured_queries if "authtoken_token" in q["sql"]
        ]
        self.assertTrue(auth_queries, "토큰 조회 질의를 못 찾았다")

        # **부분일치로 보면 안 된다.** avatar_photo_key 와 avatar_photo_at
        # 은 읽어도 되는 칸인데 이름이 avatar_photo 로 시작해서 함께 걸린다.
        # 따옴표까지 붙여 그 칸 하나만 본다.
        for sql in auth_queries:
            self.assertNotIn(
                '"avatar_photo"',
                sql,
                "인증 질의가 사진 바이트를 읽는다. 로그인한 사람의 모든 "
                "요청이 그 무게를 진다.",
            )

    def test_사진이_있어도_마찬가지다(self):
        """빈 칸이라 안 읽히는 것처럼 보이는 경우를 배제한다."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.user.avatar_photo = b"x" * 5000
        self.user.save(update_fields=["avatar_photo"])

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {self.token.key}")

        for q in ctx.captured_queries:
            if "authtoken_token" in q["sql"]:
                self.assertNotIn('"avatar_photo"', q["sql"])


class AvatarPhotoBombTest(TestCase):
    """압축이 잘 되는 큰 그림을 막는지.

    바이트 상한만으로는 안 막힌다. 같은 색으로 채운 12000x12000 은 픽셀이
    1.4억인데 PNG 로 440KB 밖에 안 돼서 5MB 검사를 지나간다. 그대로 펼치면
    0.5GB 를 쓴다.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="bomb@example.com", password=PASSWORD, display_name="폭탄"
        )
        self.token = Token.objects.create(user=self.user)

    def _png(self, w, h):
        import io as _io

        from PIL import Image

        buf = _io.BytesIO()
        Image.new("RGB", (w, h), (10, 20, 30)).save(buf, "PNG")
        return buf.getvalue()

    def _upload(self, data):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(
            "/api/accounts/photo/",
            {"photo": SimpleUploadedFile("x.png", data, content_type="image/png")},
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def test_픽셀이_많으면_거절한다(self):
        """Pillow 가 경고만 내고 통과시키는 구간(한계의 1~2배)."""
        data = self._png(12000, 12000)

        # 바이트 상한은 통과하는 크기라야 이 테스트가 의미가 있다.
        self.assertLess(len(data), AVATAR_PHOTO_MAX_BYTES)

        res = self._upload(data)

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.avatar_photo_key)

    def test_평범한_사진은_통과한다(self):
        """상한이 실제 사진까지 막으면 안 된다."""
        res = self._upload(self._png(1200, 900))

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.avatar_photo_key)
