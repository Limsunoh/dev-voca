"""계정 테스트.

핵심은 세 가지다. 비밀번호가 해시되어 저장되는가, 남의 정보를 볼 수 없는가,
실패했을 때 그 응답만으로 가입 여부를 알아낼 수 없는가.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token

from .throttles import EmailRateThrottle

User = get_user_model()

SIGNUP_URL = "/api/accounts/signup/"
LOGIN_URL = "/api/accounts/login/"
LOGOUT_URL = "/api/accounts/logout/"
ME_URL = "/api/accounts/me/"

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

    def test_case_does_not_bypass(self):
        """대소문자를 바꿔가며 같은 계정을 계속 때릴 수 없어야 한다."""
        for _ in range(3):
            self.login(email="target@example.com")

        res = self.login(email="TARGET@EXAMPLE.COM")

        self.assertEqual(res.status_code, 429)


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
