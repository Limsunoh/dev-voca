"""계정 테스트.

핵심은 세 가지다. 비밀번호가 해시되어 저장되는가, 남의 정보를 볼 수 없는가,
실패했을 때 그 응답만으로 가입 여부를 알아낼 수 없는가.
"""

from importlib import import_module
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token

from .google import GoogleAuthError, fetch_google_user
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
        res = self.signup()

        self.assertNotIn("password", res.content.decode())

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

    def patch_google(self, email="new@example.com", name="구글사용자"):
        return mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": email, "name": name},
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

    def test_display_name_falls_back_to_email(self):
        user = User.objects.create_user(email="hong@example.com", password=PASSWORD)

        self.assertEqual(user.name_for_display, "hong")


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
