"""쓸 수 없는 이름과 관리자의 사진 삭제.

이름은 순위표에서 다른 회원에게 그대로 보인다. 이메일 가입, 이름 변경, 구글 첫
가입의 세 경로가 같은 규칙을 지키는지, 멀쩡한 이름을 잘못 막지 않는지 본다.

이름에 관한 표본은 일부러 불쾌한 낱말을 그대로 적었다. 거름망이 막아야 하는
입력이 바로 그것이다.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib import admin as django_admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .admin import UserAdmin
from .forbidden_names import name_is_forbidden
from .models import (
    AVATAR_GOOGLE,
    AVATAR_PHOTO,
    DISPLAY_NAME_MAX,
    GENERATED_NAME_PREFIX,
    free_display_name,
    normalize_display_name,
    shorten_display_name,
)
from .tests import (
    CONSENT,
    GOOGLE_URL,
    ME_URL,
    PASSWORD,
    PHOTO_URL,
    REDIRECT_URI,
    SIGNUP_URL,
    _png,
    _upload,
)

User = get_user_model()

FORBIDDEN_MESSAGE = ["쓸 수 없는 이름입니다. 다른 이름을 입력해주세요."]
CHANGELIST_URL = "/admin/accounts/user/"
ACTION = "delete_uploaded_photo"

SHOULD_PASS = """
임선오|김철수|홍길동|학습자1234|학습자9999|배드민턴|badminton|class|bass|pass|Yoshitaka|Shitake|Essex|Sussex
Dickens|Hancock|peacock|cockpit|Scunthorpe|Fukuoka|새끼손가락|새끼고양이|보지마|자지마|보지않아|미친듯이
시발점|시발역|운영자금|운영 자동화|운영자동화봇|관리 자동화|관리자원|관리 자산|운영 자료|node.js|next.js|vue.js
socket.io|kim.dev|asp.net|Three.js|c++dev|C#개발자|백엔드개발자|프론트개발자|주니어개발자|개발자|서버운영|운영체제
데이터관리|DB관리|관리의신|존나이트|존 나이트|시바견|시바|개발새발|새발|텔레비전|텔레파시|카카오|카카오프렌즈|라이언
kim19990101|kim2001|coder2026|0xCAFE|o(n)|root|sudo|padmin|administrative|operators|sextant|assassin
정보처리기사|정처기합격|씨앗|씨름선수|병아리|좋아요|좋은사람|지하철|지리산|창문|창업가|미친개발|섹시|@kim|kim@
다시 발전|도시 발전|역시 발전|역시 발코딩|다시 발견|출시 발표|역시 팔자|아저씨 발표|일병 신입|이병 신동엽|신병 신고|명창 녀석
운영 자바|운영 팀장|운영 진행|품질관리 자격|정보관리 자격|품질관리자격증|시간관리 자기계발|운영 자금
bit chain|Rabbit Chen|rabbitchan|bitchat|bitchecker|보지 마|자지 마|새끼 손가락|미친 코딩|미친 듯이
vb.net|ado.net|Mr. Link|dev@home|root@dev|kube operator|k8s operator|operator|고양이새끼
"""

SHOULD_BLOCK = """
운영자|운 영 자|운.영.자|운 영자|운영 자|관리자|관리자1|관리 자|devvoca|DevVoca|dev voca|dev_voca|Ｄｅｖｖｏｃａ|d.e.v.v.o.c.a|데브보카 공식
devvoca운영자|김관리자|고객센터|공식계정|admin|ADMIN|Admin1|admin_kim|admin_x_y|kim admin|ＡＤＭＩＮ|a.d.m.i.n|administrator
운영자 동현|운영자 동훈|운영자 원빈|운영자 금희|관리자 동현|관리자 원장|관리자 금|운영자 산|관리자동훈|시발 점수|시발 점심|시발 역겨워
admin님|admin팀|Admin계정|공식admin|관\u3164리자|운\u3164영\u3164자|시\uffa0발
씨발|씨 발|시 발|시발|개시발|시발놈|좆|좃같네|개새끼|병신|븅신|지랄|미친놈|ㅅㅂ|ㅆㅂ|ㅂㅅ|ㅄ|fuck|FUCK|f u c k|motherfucker|bitch|asshole
shit|ass|보지|자지|새끼|이새끼|이 새끼|씹새끼|십새끼|존나|미친|씹|sex|porn|섹스|창녀|니애미
abc.com|ABC.COM|x.co.kr|bit.ly|www.abc|http://a|https://b|abc닷컴|me@a.co|a@b.co|op.gg|abc.net|abc.shop|t.me/abc
01012345678|010-1234-5678|010 1234 567|0212345678|02-123-4567|카톡abc|카카오톡|kakaotalk|오픈채팅|오픈톡abc|텔레그램|telegram
"""

# 표본에 없던 입력. 숨은 글자, 호환 글자, 띄워 쓰기, 주소의 변형.
EXTRA_BLOCK = (
    "데브 보카",
    "sys admin",
    "ｓｅｘ",
    "\U0001d41a\U0001d41d\U0001d426\U0001d422\U0001d427",  # 수학 굵은 글꼴의 admin
    "Ⓐdmin",  # 동그라미 A
    "관\u2800리자",  # 점자 빈칸
    "관\u200b리자",  # 폭 없는 공백
    "관\u034f리자",  # 결합 문자
    "관\u00ad리자",  # 줄바꿈 하이픈
    "운\u3000영\u3000자",  # 전각 공백
    "시\u1160발",  # 한글 중성 채움
    "시\u115f발",  # 한글 초성 채움
    "ㅅ ㅂ",
    "ㅅ.ㅂ",
    "ㅆ ㅂ",
    "씨 발놈",
    "개 새끼",
    "새 끼",
    "미친 놈",
    "운영 진",
    "운영 팀",
    "f.u.c.k",
    "F U C K",
    "s h i t",
    "abc．com",
    "naver.com입니다",
    "네이버닷컴",
    "HtTpS:",
    "０１０１２３４５６７８",
    "010.1234.5678",
    "(02)1234567",
    "운영자_원빈",
    "운영자.원빈",
    "운영자-금희",
    "관리자_금희",
    "관리자-원장",
    "운영자(원빈)",
    "운영자·금",
    "관리자-금",
    "시발.점",
    "운영자\u3164원빈",
    "어드민",
    "김어드민",
    "공식 계정",
    "고객 센터",
)

EXTRA_PASS = (
    "sysadmin",
    "badass",
    "F#.net",
    "c#.net",
    "ASP.NET",
    ".NET개발자",
    "Mr.Big",
    "2024년",
    "dev 초보",
    "t.me",
    "010",
    "0",
    "김0",
    "007",
    "1004",
    "00700700",
    "12345678",
    "운영 / 자바",
    "DB관리 / 자바",
    "다시 - 발전",
    "관리 - 자동화",
    "일병 & 신입",
    "dot.net",
)


def _samples(block: str) -> list[str]:
    return [word for line in block.strip().splitlines() for word in line.split("|")]


class NameSampleTest(SimpleTestCase):
    """거름망 자체. 막을 것과 둘 것을 표본으로 못 박는다."""

    def test_막아야_할_표본은_모두_막는다(self):
        for name in [*_samples(SHOULD_BLOCK), *EXTRA_BLOCK]:
            with self.subTest(name):
                self.assertTrue(name_is_forbidden(name))

    def test_금칙어를_품은_정상_낱말은_막지_않는다(self):
        """잘못 막으면 회원은 자기 이름이 왜 안 되는지 알 길이 없다."""
        for name in [*_samples(SHOULD_PASS), *EXTRA_PASS]:
            with self.subTest(name):
                self.assertFalse(name_is_forbidden(name))

    def test_비정상_입력에도_예외가_나지_않는다(self):
        """이름 검사에서 터지면 가입 전체가 500 이 된다."""
        for name in ("", " ", "\u3164", "a" * 5000, "\x00", "\ud800"):
            with self.subTest(repr(name[:4])):
                self.assertIs(name_is_forbidden(name), False)


class SignUpNameTest(TestCase):
    """이메일 가입 경로."""

    def setUp(self):
        cache.clear()

    def signup(self, **body):
        payload = {"email": "a@example.com", "password": PASSWORD, **CONSENT, **body}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def test_금칙어는_400_이고_계정이_안_생긴다(self):
        for name in ("운영자", "ADMIN", "dev voca", "시발", "abc.com", "010-123-4567"):
            with self.subTest(name):
                res = self.signup(display_name=name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
                self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_숨은_글자를_끼워도_막는다(self):
        """다듬기를 거친 뒤의 값을 보는지 경로로 확인한다."""
        for name in ("관\u200b리자", "관\u3164리자", " 운영자 ", "운\u3000영\u3000자"):
            with self.subTest(repr(name)):
                res = self.signup(display_name=name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)

    def test_정상_이름은_금칙어를_품어도_가입된다(self):
        res = self.signup(display_name="운영체제")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="a@example.com").display_name, "운영체제")

    def test_이름을_안_보내면_자동_이름이_된다(self):
        res = self.signup()

        self.assertEqual(res.status_code, 201)
        name = User.objects.get(email="a@example.com").display_name
        self.assertTrue(name.startswith(GENERATED_NAME_PREFIX))
        self.assertFalse(name_is_forbidden(name))

    def test_형식이_틀린_이름은_500_이_아니라_400_이다(self):
        cases = {
            "빈 문자열": "",
            "공백만": "   ",
            "null": None,
            "목록": ["운영자"],
            "객체": {"name": "운영자"},
            "참거짓": True,
            "NUL 문자": "운영\x00자",
            "길이 초과": "가" * (DISPLAY_NAME_MAX + 1),
            "아주 긴 값": "가" * 100000,
        }
        for label, value in cases.items():
            with self.subTest(label):
                res = self.signup(display_name=value)

                self.assertEqual(res.status_code, 400)
                self.assertIn("display_name", res.json())
                self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_금칙어_검사가_중복_검사보다_먼저다(self):
        """이미 쓰는 사람이 있다고 답하면 다른 번호를 붙여 다시 시도하게 된다."""
        User.objects.create_user(
            email="ops@example.com", password=PASSWORD, display_name="운영자"
        )

        res = self.signup(display_name="운영자")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)


class MeNameTest(TestCase):
    """이름 변경 경로. 지금 쓰는 이름을 그대로 보낼 때와 구분한다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="me@example.com", password=PASSWORD, display_name="평범한이름"
        )
        self.token = Token.objects.create(user=self.user)

    def patch(self, body, token=None):
        headers = {"HTTP_AUTHORIZATION": f"Token {token}"} if token else {}
        return self.client.patch(ME_URL, body, content_type="application/json", **headers)

    def patch_me(self, **body):
        return self.patch(body, self.token.key)

    def rename_directly(self, name):
        """관리자 화면에서 정해 준 이름. API 를 거치지 않아 금칙어도 들어간다."""
        self.user.display_name = name
        self.user.save()

    def test_금칙어로_바꾸면_400_이고_이름이_그대로다(self):
        for name in ("관리자", "admin님", "devvoca", "씨 발", "t.me/abc", "01012345678"):
            with self.subTest(name):
                res = self.patch_me(display_name=name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
                self.user.refresh_from_db()
                self.assertEqual(self.user.display_name, "평범한이름")

    def test_금칙어인_지금_이름을_그대로_보내면_통과한다(self):
        """아바타만 바꿔도 화면은 이름을 함께 보낸다. 막으면 아바타도 못 바꾼다."""
        self.rename_directly("운영자")

        res = self.patch_me(display_name="운영자", avatar="a3")

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "운영자")
        self.assertEqual(self.user.avatar, "a3")

    def test_앞뒤_공백만_다른_지금_이름도_같은_이름이다(self):
        self.rename_directly("운영자")

        res = self.patch_me(display_name="  운영자  ")

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "운영자")

    def test_금칙어인_지금_이름에서_다른_금칙어로는_못_바꾼다(self):
        """그대로 보낸 경우만 봐 주는 것이다. 금칙어끼리 옮겨 다닐 수는 없다."""
        self.rename_directly("운영자")

        res = self.patch_me(display_name="관리자")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "운영자")

    def test_대소문자만_바꿔도_금칙어면_막는다(self):
        """글자가 달라졌으면 그대로 보낸 것이 아니다."""
        self.rename_directly("Admin")

        res = self.patch_me(display_name="ADMIN")

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Admin")

    def test_금칙어를_떠난_뒤에는_돌아올_수_없다(self):
        self.rename_directly("운영자")
        self.assertEqual(self.patch_me(display_name="새이름").status_code, 200)

        res = self.patch_me(display_name="운영자")

        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "새이름")

    def test_남이_쓰는_금칙어도_금칙어_안내가_나간다(self):
        User.objects.create_user(
            email="ops@example.com", password=PASSWORD, display_name="운영자"
        )

        res = self.patch_me(display_name="운영자")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)

    def test_이름을_안_보내면_검사하지_않는다(self):
        self.rename_directly("운영자")

        res = self.patch_me(avatar="a2")

        self.assertEqual(res.status_code, 200)

    def test_정상_이름으로는_바꿀_수_있다(self):
        res = self.patch_me(display_name="시발점")

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "시발점")

    def test_로그인하지_않으면_401_이고_바뀌지_않는다(self):
        res = self.patch({"display_name": "운영자"})

        self.assertEqual(res.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "평범한이름")

    def test_형식이_틀린_이름은_500_이_아니라_400_이다(self):
        for label, value in {
            "빈 문자열": "",
            "공백만": "   ",
            "null": None,
            "목록": ["운영자"],
            "NUL 문자": "운영\x00자",
            "길이 초과": "가" * (DISPLAY_NAME_MAX + 1),
        }.items():
            with self.subTest(label):
                res = self.patch_me(display_name=value)

                self.assertEqual(res.status_code, 400)
                self.user.refresh_from_db()
                self.assertEqual(self.user.display_name, "평범한이름")


class GoogleNameTest(TestCase):
    """구글 첫 가입 경로. 막으면 가입할 길이 없으므로 자동 이름으로 보낸다."""

    def setUp(self):
        cache.clear()

    def google(self, name, email="new@example.com", **body):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **CONSENT, **body}
        info = {
            "email": email,
            "name": name,
            "picture": "https://lh3.googleusercontent.com/a/first",
        }
        with mock.patch("apps.accounts.views.fetch_google_user", return_value=info):
            return self.client.post(GOOGLE_URL, payload, content_type="application/json")

    def assert_generated(self, email="new@example.com"):
        name = User.objects.get(email=email).display_name
        self.assertTrue(name.startswith(GENERATED_NAME_PREFIX), name)
        self.assertFalse(name_is_forbidden(name))

    def test_금칙어면_자동_이름으로_가입된다(self):
        names = ("운영자", "admin", "DevVoca", "씨발", "abc.com", "01012345678", " 관 리 자 ", "ＡＤＭＩＮ")
        for index, name in enumerate(names):
            with self.subTest(name):
                email = f"new{index}@example.com"

                res = self.google(name, email=email)

                self.assertEqual(res.status_code, 201)
                self.assert_generated(email)

    def test_응답에도_금칙어가_실리지_않는다(self):
        res = self.google("운영자")

        self.assertNotIn("운영자", res.json()["user"]["display_name"])
        self.assertTrue(res.json()["user"]["display_name"].startswith(GENERATED_NAME_PREFIX))

    def test_정상_이름은_그대로_쓴다(self):
        res = self.google("홍길동")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="new@example.com").display_name, "홍길동")

    def test_금칙어_이름이어도_동의가_없으면_계정이_안_생긴다(self):
        res = self.google("운영자", terms_agreed=False)

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "consent_required")
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_기존_회원의_이름은_구글_이름으로_검사하지_않는다(self):
        """이름을 덮어쓰지 않으므로 다시 로그인할 때 금칙어를 볼 이유가 없다."""
        user = User.objects.create_user(
            email="new@example.com", password=PASSWORD, display_name="내가고른이름"
        )

        res = self.google("운영자")

        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.display_name, "내가고른이름")

    def test_관리자가_정해_준_이름은_다시_로그인해도_유지된다(self):
        user = User.objects.create_user(
            email="new@example.com", password=PASSWORD, display_name="운영자"
        )

        res = self.google("홍길동")

        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.display_name, "운영자")

    def test_잘린_뒤의_값을_검사한다(self):
        """금칙어가 12자 밖으로 잘려 나가면 저장되는 이름에는 없다."""
        kept = "가나다라마바사아자차카타"
        self.assertEqual(len(kept), DISPLAY_NAME_MAX)

        res = self.google(f"{kept} 운영자")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="new@example.com").display_name, kept)

    def test_잘려서_금칙어가_생기면_자동_이름이_된다(self):
        """시발점은 괜찮지만 12자에서 잘리면 시발이 남는다."""
        res = self.google("가나다라마바사아자차시발점")

        self.assertEqual(res.status_code, 201)
        self.assert_generated()

    def test_번호를_붙이다_금칙어가_생기면_그_후보를_건너뛴다(self):
        """시발점 끝을 잘라 번호를 붙이면 시발이 드러난다."""
        name = "아무개아무개아무개시발점"
        self.assertEqual(len(name), DISPLAY_NAME_MAX)
        self.assertFalse(name_is_forbidden(name))
        User.objects.create_user(email="o@example.com", password=PASSWORD, display_name=name)

        picked = free_display_name(name)

        self.assertEqual(picked, "아무개아무개아무개시10")
        self.assertFalse(name_is_forbidden(picked))

    def test_겹치는_정상_이름은_번호가_붙는다(self):
        User.objects.create_user(
            email="o@example.com", password=PASSWORD, display_name="운영체제"
        )

        self.google("운영체제")

        self.assertEqual(User.objects.get(email="new@example.com").display_name, "운영체제2")


class DeleteUploadedPhotoTest(TestCase):
    """약관을 어긴 사진을 지우는 관리자 동작."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="root@example.com", password=PASSWORD
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def member(self, email, *, photo=True, avatar=""):
        user = User.objects.create_user(email=email, password=PASSWORD)
        fields = {"avatar": avatar}
        if photo:
            fields.update(
                avatar_photo=b"photo-bytes",
                avatar_photo_key=uuid.uuid4(),
                avatar_photo_at=timezone.now(),
            )
        User.objects.filter(pk=user.pk).update(**fields)
        return User.objects.get(pk=user.pk)

    def staff(self, *codenames):
        user = User.objects.create_user(
            email=f"staff-{uuid.uuid4().hex[:8]}@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        user.user_permissions.set(
            Permission.objects.filter(
                codename__in=codenames, content_type__app_label="accounts"
            )
        )
        return user

    def run_action(self, client, *members, **extra):
        data = {
            "action": ACTION,
            "index": "0",
            "_selected_action": [m.pk for m in members],
            **extra,
        }
        return client.post(CHANGELIST_URL, data)

    def stored(self, user):
        row = User.objects.get(pk=user.pk)
        photo = bytes(row.avatar_photo) if row.avatar_photo else None
        return photo, row.avatar_photo_key, row.avatar_photo_at, row.avatar

    def logs_for(self, user):
        return LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk),
        )

    def api_delete(self, user):
        token = Token.objects.create(user=user)
        return Client().delete(PHOTO_URL, HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_same_as_my_page(self, *, photo, avatar):
        """같은 상태의 두 회원에게 양쪽을 실행해 결과를 맞대 본다."""
        through_admin = self.member("admin-way@example.com", photo=photo, avatar=avatar)
        through_api = self.member("my-page@example.com", photo=photo, avatar=avatar)

        self.run_action(self.client, through_admin)
        self.assertEqual(self.api_delete(through_api).status_code, 200)

        self.assertEqual(self.stored(through_admin), self.stored(through_api))
        self.assertEqual(
            User.objects.get(pk=through_admin.pk).avatar_display["type"],
            User.objects.get(pk=through_api.pk).avatar_display["type"],
        )

    def test_사진을_고른_회원은_내정보_삭제와_결과가_같다(self):
        self.assert_same_as_my_page(photo=True, avatar=AVATAR_PHOTO)

    def test_자동_상태의_회원은_내정보_삭제와_결과가_같다(self):
        self.assert_same_as_my_page(photo=True, avatar="")

    def test_다른_아바타를_고른_회원은_고른_것이_남는다(self):
        self.assert_same_as_my_page(photo=True, avatar="a3")
        self.assertEqual(User.objects.get(email="admin-way@example.com").avatar, "a3")

    def test_구글_사진을_고른_회원도_고른_것이_남는다(self):
        self.assert_same_as_my_page(photo=True, avatar=AVATAR_GOOGLE)
        self.assertEqual(User.objects.get(email="admin-way@example.com").avatar, AVATAR_GOOGLE)

    def test_사진_없는_회원은_내정보_삭제와_결과가_같다(self):
        self.assert_same_as_my_page(photo=False, avatar="")

    def test_사진_없이_다른_아바타인_회원도_같다(self):
        self.assert_same_as_my_page(photo=False, avatar="a5")

    def test_실제로_올린_사진의_주소가_404_가_된다(self):
        """다른 사람에게 더 보이지 않아야 지운 것이다."""
        user = User.objects.create_user(email="m@example.com", password=PASSWORD)
        token = Token.objects.create(user=user)
        api = Client()
        res = api.post(
            PHOTO_URL,
            {"photo": _upload(_png())},
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        url = user.avatar_photo_url
        self.assertEqual(api.get(url).status_code, 200)

        self.run_action(self.client, user)

        self.assertEqual(api.get(url).status_code, 404)
        user.refresh_from_db()
        self.assertEqual(user.avatar, "")
        self.assertFalse(user.has_avatar_photo)

    def test_지운_회원마다_작업_기록이_남는다(self):
        """되돌릴 수 없으니 이의 제기에 답할 근거가 있어야 한다."""
        first = self.member("a@example.com")
        second = self.member("b@example.com", avatar=AVATAR_PHOTO)

        self.run_action(self.client, first, second)

        for member in (first, second):
            with self.subTest(member.email):
                entry = self.logs_for(member).get()
                self.assertEqual(entry.user, self.superuser)
                self.assertEqual(entry.action_flag, CHANGE)
                self.assertEqual(entry.object_repr, member.email)
                self.assertEqual(entry.get_change_message(), "올린 사진을 지웠습니다.")

    def test_사진_없는_회원에게는_기록이_남지_않는다(self):
        """지운 것이 없는데 지웠다고 남으면 기록을 믿을 수 없다."""
        with_photo = self.member("a@example.com")
        without = self.member("b@example.com", photo=False)

        self.run_action(self.client, with_photo, without)

        self.assertEqual(self.logs_for(with_photo).count(), 1)
        self.assertEqual(self.logs_for(without).count(), 0)

    def test_안내_문구는_실제로_지운_장수를_센다(self):
        with_photo = self.member("a@example.com")
        without = self.member("b@example.com", photo=False)

        res = self.client.post(
            CHANGELIST_URL,
            {"action": ACTION, "index": "0", "_selected_action": [with_photo.pk, without.pk]},
            follow=True,
        )

        self.assertContains(res, "사진 1장을 지웠습니다.")

    def test_다른_회원의_사진은_건드리지_않는다(self):
        target = self.member("a@example.com", avatar=AVATAR_PHOTO)
        bystander = self.member("b@example.com", avatar=AVATAR_PHOTO)
        before = self.stored(bystander)

        self.run_action(self.client, target)

        self.assertEqual(self.stored(bystander), before)
        self.assertEqual(self.logs_for(bystander).count(), 0)

    def test_전체_선택도_같은_규칙으로_지운다(self):
        first = self.member("a@example.com", avatar=AVATAR_PHOTO)
        second = self.member("b@example.com", avatar="a1")

        self.run_action(self.client, first, select_across="1")

        self.assertEqual(self.stored(first)[3], "")
        self.assertFalse(User.objects.get(pk=second.pk).has_avatar_photo)
        self.assertEqual(User.objects.get(pk=second.pk).avatar, "a1")
        self.assertEqual(self.logs_for(second).count(), 1)

    def test_아무도_고르지_않으면_아무_일도_없다(self):
        member = self.member("a@example.com")
        before = self.stored(member)

        res = self.client.post(CHANGELIST_URL, {"action": ACTION, "index": "0"})

        self.assertIn(res.status_code, (200, 302))
        self.assertEqual(self.stored(member), before)
        self.assertEqual(self.logs_for(member).count(), 0)

    def test_사진_바이트를_읽지_않는다(self):
        """한 번에 여러 명을 고르면 사진 칸을 읽는 비용이 그대로 늘어난다."""
        members = [self.member(f"m{i}@example.com") for i in range(3)]
        model_admin = UserAdmin(User, django_admin.site)
        request = RequestFactory().post(CHANGELIST_URL)
        request.user = self.superuser
        queryset = User.objects.filter(pk__in=[m.pk for m in members])

        with mock.patch.object(model_admin, "message_user"):
            with CaptureQueriesContext(connection) as queries:
                model_admin.delete_uploaded_photo(request, queryset)

        selects = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertTrue(selects)
        for sql in selects:
            self.assertNotRegex(sql, r'"avatar_photo"')

    def test_수정_권한이_있는_스태프에게는_보이고_실행된다(self):
        staff = Client()
        staff.force_login(self.staff("view_user", "change_user"))
        member = self.member("a@example.com")

        self.assertContains(staff.get(CHANGELIST_URL), ACTION)
        self.run_action(staff, member)

        self.assertFalse(User.objects.get(pk=member.pk).has_avatar_photo)

    def test_수정_권한이_없는_스태프에게는_안_보인다(self):
        staff = Client()
        staff.force_login(self.staff("view_user"))

        res = staff.get(CHANGELIST_URL)

        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, ACTION)

    def test_수정_권한이_없는_스태프가_직접_보내도_실행되지_않는다(self):
        for codenames in (("view_user",), ("view_user", "delete_user"), ("view_user", "add_user")):
            with self.subTest(codenames):
                staff = Client()
                staff.force_login(self.staff(*codenames))
                member = self.member(f"a-{'-'.join(codenames)}@example.com")
                before = self.stored(member)

                self.run_action(staff, member)

                self.assertEqual(self.stored(member), before)
                self.assertEqual(self.logs_for(member).count(), 0)

    def test_권한이_전혀_없는_스태프는_403_이다(self):
        staff = Client()
        staff.force_login(self.staff())
        member = self.member("a@example.com")
        before = self.stored(member)

        res = self.run_action(staff, member)

        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.stored(member), before)

    def test_일반_회원과_비로그인은_실행하지_못한다(self):
        member = self.member("a@example.com")
        before = self.stored(member)
        plain = Client()
        plain.force_login(User.objects.create_user(email="p@example.com", password=PASSWORD))

        for label, client in {"일반 회원": plain, "비로그인": Client()}.items():
            with self.subTest(label):
                res = self.run_action(client, member)

                self.assertEqual(res.status_code, 302)
                self.assertIn("/login/", res["Location"])
                self.assertEqual(self.stored(member), before)


# 글자로 분류되지만 화면에서는 빈칸으로 보이는 글자들.
BLANK_LOOKING = {
    "U+115F": "\u115f",
    "U+1160": "\u1160",
    "U+3164": "\u3164",
    "U+FFA0": "\uffa0",
    "U+2800": "\u2800",
}
NAME_REQUIRED = ["이름을 입력해주세요."]
NAME_TAKEN = ["이미 쓰고 있는 이름입니다."]


class BlankLookingNormalizeTest(SimpleTestCase):
    """빈칸처럼 보이는 글자를 공백으로 다루는 규칙 자체."""

    def test_빈칸_글자만_있으면_빈_이름이다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(normalize_display_name(char), "")
                self.assertEqual(normalize_display_name(char * 5), "")

    def test_다섯_글자를_섞어도_빈_이름이다(self):
        self.assertEqual(normalize_display_name("".join(BLANK_LOOKING.values())), "")

    def test_다른_공백이나_숨은_글자와_섞여도_빈_이름이다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(normalize_display_name(f" {char}\u200b{char}\u3000"), "")

    def test_앞뒤의_빈칸_글자는_지운다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(normalize_display_name(f"{char}홍길동{char}"), "홍길동")

    def test_사이의_빈칸_글자는_공백_한_칸이_된다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(normalize_display_name(f"홍{char}길동"), "홍 길동")
                self.assertEqual(normalize_display_name(f"홍{char}{char} 길동"), "홍 길동")
                self.assertEqual(normalize_display_name(f"홍{char}\u200b{char}길동"), "홍 길동")

    def test_이웃한_글자와_보통_이름은_건드리지_않는다(self):
        """범위로 넓게 잡으면 실제로 쓰이는 글자까지 지워진다."""
        for name in ("홍길동", "a b", "\u115e", "\u1161", "\u3163", "\u3165", "\uffa1", "\u2801"):
            with self.subTest(ascii(name)):
                self.assertEqual(normalize_display_name(name), name)

    def test_완성형으로_모으는_동작은_그대로다(self):
        self.assertEqual(normalize_display_name("\u1112\u1161\u11ab"), "\ud55c")

    def test_12자로_자른_자리에_공백이_남지_않는다(self):
        """남으면 저장 직전에 값이 달라져 이미 쓰는 이름과 부딪힌다."""
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(shorten_display_name("가" * 11 + char + "나나"), "가" * 11)

    def test_빈칸_글자를_먼저_줄인_뒤에_12자를_센다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.assertEqual(shorten_display_name(char * 30 + "가" * 12), "가" * 12)
                self.assertEqual(shorten_display_name("가" * 12 + char + "나"), "가" * 12)


class BlankLookingNameRouteTest(TestCase):
    """빈칸 글자가 가입, 내정보, 구글 경로에서 공백으로 다뤄지는가."""

    def setUp(self):
        cache.clear()
        self.member = User.objects.create_user(
            email="me@example.com", password=PASSWORD, display_name="평범한이름"
        )
        self.token = Token.objects.create(user=self.member)
        self.owner = User.objects.create_user(
            email="owner@example.com", password=PASSWORD, display_name="주인"
        )

    def signup(self, name, email="a@example.com"):
        payload = {"email": email, "password": PASSWORD, "display_name": name, **CONSENT}
        return self.client.post(SIGNUP_URL, payload, content_type="application/json")

    def patch_me(self, **body):
        return self.client.patch(
            ME_URL,
            body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def google(self, name, email):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **CONSENT}
        info = {"email": email, "name": name, "picture": ""}
        with mock.patch("apps.accounts.views.fetch_google_user", return_value=info):
            return self.client.post(GOOGLE_URL, payload, content_type="application/json")

    def name_of(self, email):
        return User.objects.get(email=email).display_name

    def test_가입_빈칸_글자만이면_400_이고_계정이_안_생긴다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                for name in (char, char * 3, f" {char} "):
                    res = self.signup(name)

                    self.assertEqual(res.status_code, 400)
                    self.assertEqual(res.json()["display_name"], NAME_REQUIRED)
                    self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_내정보_빈칸_글자만이면_400_이고_이름이_그대로다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.patch_me(display_name=char)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], NAME_REQUIRED)
                self.member.refresh_from_db()
                self.assertEqual(self.member.display_name, "평범한이름")

    def test_구글_빈칸_글자만이면_자동_이름으로_가입된다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"g{index}@example.com"

                res = self.google(char, email)

                self.assertEqual(res.status_code, 201)
                self.assertTrue(self.name_of(email).startswith(GENERATED_NAME_PREFIX))

    def test_가입_앞뒤의_빈칸_글자는_지워서_저장한다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"a{index}@example.com"

                res = self.signup(f"{char}새이름{index}{char}", email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(self.name_of(email), f"새이름{index}")

    def test_가입_사이의_빈칸_글자는_공백으로_저장한다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"a{index}@example.com"

                res = self.signup(f"새{char}이름{index}", email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(self.name_of(email), f"새 이름{index}")

    def test_가입_앞이나_끝에_붙여도_기존_이름과_중복이다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                for name in (f"주인{char}", f"{char}주인", f"주인{char}{char}", f"{char}주인{char}"):
                    res = self.signup(name)

                    self.assertEqual(res.status_code, 400)
                    self.assertEqual(res.json()["display_name"], NAME_TAKEN)
                    self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_가입_대소문자가_달라도_끝에_붙이면_중복이다(self):
        User.objects.create_user(
            email="g@example.com", password=PASSWORD, display_name="Gildong"
        )
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.signup(f"gILDONG{char}")

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], NAME_TAKEN)

    def test_가입_사이에_넣으면_띄어_쓴_기존_이름과_중복이다(self):
        User.objects.create_user(
            email="h@example.com", password=PASSWORD, display_name="홍 길동"
        )
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.signup(f"홍{char}길동")

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], NAME_TAKEN)

    def test_가입_빈칸_글자를_끼운_금칙어는_막는다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                for name in (f"운영자{char}", f"{char}운영자", f"관{char}리자"):
                    res = self.signup(name)

                    self.assertEqual(res.status_code, 400)
                    self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)

    def test_내정보_끝에_붙여도_남의_이름과_중복이다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.patch_me(display_name=f"주인{char}")

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], NAME_TAKEN)
                self.member.refresh_from_db()
                self.assertEqual(self.member.display_name, "평범한이름")

    def test_내정보_내_이름_끝에_붙이면_그대로_내_이름이다(self):
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.patch_me(display_name=f"평범한이름{char}")

                self.assertEqual(res.status_code, 200)
                self.member.refresh_from_db()
                self.assertEqual(self.member.display_name, "평범한이름")

    def test_구글_끝에_붙인_이름이_겹치면_번호가_붙는다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"g{index}@example.com"

                res = self.google(f"주인{char}", email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(self.name_of(email), f"주인{index + 2}")

    def test_save_직접_호출_빈칸_글자만이면_자동_이름이다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                user = User.objects.create_user(
                    email=f"s{index}@example.com", password=PASSWORD, display_name=char
                )

                self.assertTrue(user.display_name.startswith(GENERATED_NAME_PREFIX))

    def test_save_직접_호출_끝의_빈칸_글자를_지운다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                self.member.display_name = f"고친이름{index}{char}"
                self.member.save()

                self.member.refresh_from_db()
                self.assertEqual(self.member.display_name, f"고친이름{index}")

    def test_save_직접_호출_끝에_붙여도_DB_제약에_걸린다(self):
        """API 를 거치지 않는 경로. 조용히 같은 이름이 두 줄이 되면 안 된다."""
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                self.member.display_name = f"주인{char}"

                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.member.save()

    def test_save_직접_호출_12자에서_자른_뒤_공백이_없다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                kept = "가" * 11
                user = User.objects.create_user(
                    email=f"s{index}@example.com",
                    password=PASSWORD,
                    display_name=f"{kept}{char}나나",
                )

                self.assertEqual(user.display_name, kept)
                user.delete()

    def test_가입_11자_끝의_빈칸_글자는_길이_안에서_지운다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"a{index}@example.com"
                name = chr(ord("가") + index) * 11

                res = self.signup(f"{name}{char}", email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(self.name_of(email), name)

    def test_가입_12자에_빈칸_글자를_붙이면_길이로_막힌다(self):
        """필드의 글자 수 검사가 다듬기 전 값을 본다. 500 없이 계정도 안 생긴다."""
        for label, char in BLANK_LOOKING.items():
            with self.subTest(label):
                res = self.signup("가" * DISPLAY_NAME_MAX + char)

                self.assertEqual(res.status_code, 400)
                self.assertIn("display_name", res.json())
                self.assertFalse(User.objects.filter(email="a@example.com").exists())

    def test_구글_12자에서_자른_자리의_빈칸_글자도_남지_않는다(self):
        for index, (label, char) in enumerate(BLANK_LOOKING.items()):
            with self.subTest(label):
                email = f"g{index}@example.com"
                name = chr(ord("가") + index) * 11

                res = self.google(f"{name}{char}나나", email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(self.name_of(email), name)

    def test_구글_12자_이름에_붙여도_겹치면_번호가_12자_안에_붙는다(self):
        full = "가" * DISPLAY_NAME_MAX
        User.objects.create_user(email="f@example.com", password=PASSWORD, display_name=full)

        res = self.google(f"{full}\u3164", "g@example.com")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.name_of("g@example.com"), "가" * 11 + "2")
