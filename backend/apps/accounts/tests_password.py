"""비밀번호 변경과 최초 설정 테스트.

tests.py 가 아니라 별 파일로 둔다. 그 파일이 이미 1180줄이고, 지금 세
세션이 accounts 앱을 나눠 고치는 중이라 같은 파일 끝에 덧붙이면 합칠 때
서로의 블록이 겹친다.

핵심은 넷이다. 현재 비밀번호 없이 바꿀 수 없는가, 구글로만 가입한 사람이
처음 설정할 수 있는가, 다른 기기가 끊기는가, 지금 기기가 살아남는가.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token

from .throttles import PasswordChangeThrottle

User = get_user_model()

LOGIN_URL = "/api/accounts/login/"
ME_URL = "/api/accounts/me/"
PASSWORD_URL = "/api/accounts/password/"

# 테스트용 비밀번호. 문자열을 자리마다 적지 않고 이름으로 둔다.
#
# 비밀 스캐너(GitGuardian)가 대소문자와 숫자와 기호를 섞은 문자열을
# 비밀번호 자리에서 보면 진짜 자격증명으로
# 보고 CI 를 막는다. 실제로 이 파일 때문에 PR 한 번이 빨개졌다. 값 자체는
# 테스트에서 만든 계정의 것이라 새어도 잃을 것이 없지만, 스캐너가 매번
# 걸면 진짜 유출이 왔을 때 그 경고를 무시하게 된다.
#
# tests.py 도 같은 이유로 PASSWORD 상수 하나를 쓴다.
OLD_PASSWORD = "devvoca-old-4417"
NEW_PASSWORD = "devvoca-new-9032"
FIRST_PASSWORD = "devvoca-first-2258"
OTHER_A = "devvoca-aaa-6614"
OTHER_B = "devvoca-bbb-7725"


class PasswordChangeTest(TestCase):
    """비밀번호를 이미 가진 사람이 바꾼다."""

    def setUp(self):
        # 시도 제한이 캐시에 남아 다음 테스트로 새는 것을 막는다. 요율은
        # 테스트에서 풀려 있지만 통은 실제로 채워진다.
        cache.clear()
        self.user = User.objects.create_user(
            email="owner@example.com",
            password=OLD_PASSWORD,
            display_name="주인",
        )
        self.token = Token.objects.create(user=self.user)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_password_changes_and_is_hashed(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # 평문이 그대로 들어가지 않았는가.
        self.assertNotEqual(self.user.password, NEW_PASSWORD)
        # 바꾼 것이지 처음 설정한 것이 아니다.
        self.assertIs(res.json()["created"], False)

    def test_wrong_current_password_is_refused(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": "NotTheOne1!", "new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_current_password_is_required(self):
        """빠뜨리면 막는다.

        로그인된 화면을 잠깐 빌린 사람이 비밀번호를 갈아치우고 주인을
        밀어내는 것을 막는 자리다.
        """
        res = self.client.post(
            PASSWORD_URL,
            {"new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_anonymous_cannot_change(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 401)

    def test_weak_password_is_refused(self):
        """가입과 같은 검사기를 태운다."""
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": "1234"},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD_PASSWORD))

    def test_password_similar_to_email_is_refused(self):
        """사용자 정보를 검사기에 넘기고 있는가.

        안 넘기면 이 검사만 조용히 건너뛴다. SignUpSerializer 가 같은
        이유로 validate() 에서 user 를 넘긴다.
        """
        res = self.client.post(
            PASSWORD_URL,
            {
                "current_password": OLD_PASSWORD,
                "new_password": "owner@example.com",
            },
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.json())

    def test_same_password_is_refused(self):
        """같은 값으로 바꾸면 막는다.

        통과시키면 다른 기기 토큰만 끊고 비밀번호는 그대로다. 화면은
        성공으로 보이는데 바꾼 이유가 해결되지 않는다.
        """
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": OLD_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.json())

    def test_other_devices_are_signed_out_and_this_one_survives(self):
        """다른 기기는 끊고 지금 기기는 남는다.

        이 테스트가 이 기능의 핵심이다. 토큰을 안 끊으면 비밀번호를 바꾼
        이유(누가 들어와 있다)가 해결되지 않고, 지금 기기까지 끊으면
        바꾸자마자 로그인 화면으로 튕겨 성공했는지 알 수 없다.

        DRF 토큰은 사용자당 하나라 다른 기기 몫을 따로 만들 수 없다.
        그래서 "지금 토큰이 무효가 되었는가" 로 확인한다 - 다른 기기가
        들고 있는 것이 바로 이 값이다.
        """
        old_key = self.token.key

        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 200)

        new_key = res.json()["token"]
        # 새 토큰을 받았고 옛 값과 다르다. 같으면 다른 기기가 안 끊긴다.
        self.assertNotEqual(new_key, old_key)
        self.assertFalse(Token.objects.filter(key=old_key).exists())
        # 옛 토큰으로는 이제 못 들어온다 - 다른 기기가 이 상태가 된다.
        stale = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {old_key}")
        self.assertEqual(stale.status_code, 401)
        # 새 토큰은 바로 쓸 수 있다 - 지금 기기가 이 값으로 쿠키를 갱신한다.
        fresh = self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Token {new_key}")
        self.assertEqual(fresh.status_code, 200)
        # 지우지 않고 만들었다면 둘이 남는다.
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def test_new_password_actually_logs_in(self):
        """바꾼 비밀번호로 로그인되는가.

        set_password 를 안 거치고 저장하면 해시가 아닌 값이 들어가서,
        DB 에는 새 값이 보이는데 로그인은 안 된다.
        """
        self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        res = self.client.post(
            LOGIN_URL,
            {"email": "owner@example.com", "password": NEW_PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        old = self.client.post(
            LOGIN_URL,
            {"email": "owner@example.com", "password": OLD_PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(old.status_code, 400)

    def test_response_never_carries_the_password(self):
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        body = res.content.decode()
        self.assertNotIn(NEW_PASSWORD, body)
        self.assertNotIn(OLD_PASSWORD, body)
        self.assertNotIn("password", res.json()["user"])


class PasswordFirstTimeTest(TestCase):
    """구글로만 가입한 사람이 비밀번호를 처음 설정한다.

    이 분기가 없으면 구글 사용자는 영영 비밀번호를 만들 수 없다. 현재
    비밀번호를 요구받는데 댈 수 있는 값이 없기 때문이다.
    """

    def setUp(self):
        cache.clear()
        # 구글 로그인이 만드는 것과 같은 모양. 못 쓰는 비밀번호가 들어가
        # has_usable_password() 가 False 다.
        self.user = User.objects.create_user(
            email="google@example.com",
            password=None,
            display_name="구글사용자",
        )
        self.token = Token.objects.create(user=self.user)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_the_fixture_really_has_no_usable_password(self):
        """전제 확인.

        create_user(password=None) 이 실제로 못 쓰는 비밀번호를 넣는지
        먼저 본다. 이것이 깨지면 아래 테스트들이 다른 것을 재게 된다.
        """
        self.assertFalse(self.user.has_usable_password())

    def test_sets_password_without_current(self):
        res = self.client.post(
            PASSWORD_URL,
            {"new_password": FIRST_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 200)
        # 처음 설정한 것이라고 알려준다. 화면 문구가 이 값으로 갈린다.
        self.assertIs(res.json()["created"], True)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(FIRST_PASSWORD))
        self.assertTrue(self.user.has_usable_password())

    def test_can_log_in_with_email_after_setting(self):
        """설정한 뒤 이메일 로그인이 열리는가.

        구글로만 들어오던 사람이 이제 비밀번호로도 들어올 수 있어야
        설정한 의미가 있다.
        """
        self.client.post(
            PASSWORD_URL,
            {"new_password": FIRST_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        res = self.client.post(
            LOGIN_URL,
            {"email": "google@example.com", "password": FIRST_PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

    def test_sending_a_current_password_is_refused(self):
        """없는 비밀번호를 확인해달라고 오면 막는다.

        조용히 무시하면 화면이 잘못된 칸을 계속 보여주고, 통과시키면
        아무 값이나 적어도 되는 칸이 된다.
        """
        res = self.client.post(
            PASSWORD_URL,
            {"current_password": "anything", "new_password": FIRST_PASSWORD},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("current_password", res.json())

    def test_weak_password_is_refused_here_too(self):
        res = self.client.post(
            PASSWORD_URL,
            {"new_password": "1234"},
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(res.status_code, 400)
        self.assertIn("new_password", res.json())


class PasswordChangeThrottleTest(TestCase):
    """시도 제한이 계정별로 걸리는가.

    이 통로는 현재 비밀번호가 맞는지 응답으로 알려주므로 로그인과 성질이
    같다. 제한이 없으면 로그인 제한을 우회해 여기로 추측을 던질 수 있다.
    """

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(
            email="a@example.com", password=OTHER_A, display_name="에이"
        )
        self.b = User.objects.create_user(
            email="b@example.com", password=OTHER_B, display_name="비이"
        )

    def test_key_is_per_account(self):
        """다른 계정은 다른 통에 담긴다.

        통이 하나뿐이면 아무나 한도를 태워 전원의 비밀번호 변경을 막는다.
        """
        throttle = PasswordChangeThrottle()

        class _Req:
            def __init__(self, user):
                self.user = user

        key_a = throttle.get_cache_key(_Req(self.a), None)
        key_b = throttle.get_cache_key(_Req(self.b), None)

        self.assertIsNotNone(key_a)
        self.assertNotEqual(key_a, key_b)
        self.assertIn(f"u{self.a.pk}", key_a)

    def test_anonymous_is_not_counted(self):
        """인증 없는 요청은 세지 않는다.

        401 로 끝나는 요청을 한 통에 담으면 그것이 전원을 막는 스위치가
        된다. None 을 주면 DRF 가 제한을 건너뛴다.
        """
        throttle = PasswordChangeThrottle()

        class _Anon:
            is_authenticated = False

        class _Req:
            user = _Anon()

        self.assertIsNone(throttle.get_cache_key(_Req(), None))

    def test_repeated_guesses_fill_the_bucket(self):
        """반복해서 찔러보면 막힌다.

        요율이 테스트에서 풀려 있어(rate 의 sys.argv 분기) 실제 요청으로는
        429 를 볼 수 없다. 통이 채워지는지를 직접 확인한다.
        """
        throttle = PasswordChangeThrottle()
        # 운영 요율 자리에 작은 값을 넣어 잰다.
        throttle.rate = "3/min"
        throttle.num_requests, throttle.duration = throttle.parse_rate(throttle.rate)

        class _Req:
            def __init__(self, user):
                self.user = user

        req = _Req(self.a)
        allowed = [throttle.allow_request(req, None) for _ in range(4)]

        # 앞의 셋은 통과하고 넷째가 막힌다.
        self.assertEqual(allowed[:3], [True, True, True])
        self.assertFalse(allowed[3])
