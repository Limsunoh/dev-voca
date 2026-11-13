"""서비스 이름을 바꾼 뒤에도 지켜야 할 것. devvoca -> dev-voca -> DeVoca(2026-11-11).

메일은 회원이 받아 보는 글이라 화면과 이름이 달라지면 사칭 메일처럼 읽힌다.
두 계정 메일(이메일 변경 확인, 휴면 삭제 안내)을 실제 경로로 만들게 해서
locmem 함에 쌓인 것을 본다. build_* 함수만 부르면 views 나 purge 가 다른
문구를 쓰게 바뀌어도 모른다.

이름 거름망은 지금 이름 DeVoca 와 그 변형으로 운영자를 흉내 내는 것을 막는지
본다. 화면에 "DeVoca" 가 나오므로 이 표기가 가장 그럴듯한 사칭이다. 옛 이름
dev-voca 도 계속 막는다.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import LoginToken
from apps.learning.tests_daily_cleanup import PurgeTestBase

from .forbidden_names import name_is_forbidden
from .tests import CONSENT, EMAIL_CHANGE_URL, PASSWORD, SIGNUP_URL

User = get_user_model()

BRAND_PREFIX = "[DeVoca]"
FORBIDDEN_MESSAGE = ["쓸 수 없는 이름입니다. 다른 이름을 입력해주세요."]

# 하이픈 자리에 올 수 있는 글자들. 화면에서는 모두 비슷한 가로줄로 보인다.
HYPHEN_LOOKALIKES = (
    "-",  # 하이픈-마이너스
    "‐",  # 하이픈
    "‑",  # 줄바꿈 없는 하이픈
    "‒",  # 숫자 대시
    "–",  # en dash
    "—",  # em dash
    "−",  # 빼기 기호
    "﹣",  # 작은 하이픈
    "－",  # 전각 하이픈
    "\u00ad",  # 줄바꿈 하이픈(보이지 않음)
)


class BrandMailAssertions:
    """메일 한 통이 새 이름으로 나갔는지."""

    def assert_branded(self, message) -> None:
        self.assertTrue(
            message.subject.startswith(BRAND_PREFIX),
            f"제목이 {BRAND_PREFIX} 로 시작하지 않는다: {message.subject}",
        )
        self.assertIn("DeVoca", message.body)
        for text in (message.subject, message.body):
            # 옛 표기는 대소문자를 바꾼 것(DevVoca, Dev-Voca)도 남으면 안 된다.
            # 웹 주소 dev-voca.vercel.app 은 이름이 아니라 그대로다.
            folded = text.casefold().replace("dev-voca.vercel.app", "")
            self.assertNotIn("devvoca", folded)
            self.assertNotIn("dev-voca", folded)


class EmailChangeMailBrandTest(BrandMailAssertions, TestCase):
    """이메일 변경 확인 메일. 신청 화면에서 실제로 보내게 한다."""

    def setUp(self):
        cache.clear()
        # 테스트 러너의 locmem 은 "정말 나가는 백엔드" 가 아니라서 그대로 두면
        # 503 이 난다. 판정만 바꿔 locmem 함에 쌓이게 한다.
        patcher = mock.patch("apps.accounts.mail._really_sends", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.user = User.objects.create_user(
            email="old@example.com", password=PASSWORD, display_name="주인"
        )
        self.token = LoginToken.objects.create(user=self.user)

    def test_확인_메일_제목과_본문이_새_이름이다(self):
        res = self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": "new@example.com", "current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(res.status_code, 202)
        self.assertEqual(len(django_mail.outbox), 1)
        message = django_mail.outbox[0]
        self.assertEqual(message.to, ["new@example.com"])
        self.assert_branded(message)
        self.assertIn("/profile/email/", message.body)


class PurgeNoticeMailBrandTest(BrandMailAssertions, PurgeTestBase):
    """휴면 삭제 안내 메일. 정기 정리 명령으로 실제로 보내게 한다."""

    def test_안내_메일_제목과_본문이_새_이름이다(self):
        user = self.member("sleepy", seen_days_ago=340)

        self.apply()

        self.assertEqual(self.recipients(), [user.email])
        message = django_mail.outbox[0]
        self.assert_branded(message)
        self.assertIn("30일", message.subject)


class BrandNameImpersonationTest(SimpleTestCase):
    """서비스 이름과 그 변형으로 운영자를 흉내 내는 이름을 막는다."""

    def test_지금_이름과_그_변형을_막는다(self):
        for name in (
            "DeVoca",
            "devoca",
            "DEVOCA",
            "De Voca",
            "De.Voca",
            "d-e-v-o-c-a",
            "ｄｅｖｏｃａ",
            "De\u200bVoca",
            "De\u00adVoca",
            "De\u3164Voca",
            "DeVoca 공식",
            "DeVoca운영자",
            "공식DeVoca",
            "official devoca",
            "OfficialDeVoca",
            "TeamDeVoca",
            "DeVocaTeam",
            "DeVoca_official",
            "DEVOCAteam",
            "kim_devoca",
            "DeVoca123",
            "데보카",
            "데 보 카",
            "공식데보카",
        ):
            with self.subTest(name=name):
                self.assertTrue(name_is_forbidden(name))

    def test_devoca_를_품은_평범한_이름은_막지_않는다(self):
        """다른 낱말에 붙어 devoca 가 되는 이름. 단어장 앱이라 vocab 이 흔하다."""
        for name in (
            "codevocab",
            "CodeVocab",
            "code vocab",
            "code_vocal",
            "MadeVocal",
            "dev_ocaml",
            "Dev Ocampo",
            "devocalize",
            "de vocab",
            "DEV_OCAML",
            "DEVOCALIZE",
        ):
            with self.subTest(name=name):
                self.assertFalse(name_is_forbidden(name))

    def test_하이픈_닮은_글자를_넣은_표기를_모두_막는다(self):
        for dash in HYPHEN_LOOKALIKES:
            for name in (f"dev{dash}voca", f"Dev{dash}Voca", f"DEV{dash}VOCA"):
                with self.subTest(name=name, code=f"U+{ord(dash):04X}"):
                    self.assertTrue(name_is_forbidden(name))

    def test_옛_표기_dev_voca_에_말을_덧붙여도_막는다(self):
        for name in (
            "Dev-Voca 공식",
            "dev-voca운영자",
            "dev-voca 팀",
            "공식dev-voca",
            "dev - voca",
            "d-e-v-v-o-c-a",
            "dev-voca123",
            "ｄｅｖ－ｖｏｃａ",
            "dev\u200b-\u200bvoca",
            "dev-\u3164voca",
            "데브-보카",
        ):
            with self.subTest(name=name):
                self.assertTrue(name_is_forbidden(name))

    def test_이름의_일부만_같은_정상_이름은_막지_않는다(self):
        """dev 나 voca 하나만 들어간 개발자 별명까지 막으면 안 된다."""
        for name in ("dev", "voca", "dev-ops", "devops", "vocab-king", "dev-vo", "voc-dev"):
            with self.subTest(name=name):
                self.assertFalse(name_is_forbidden(name))


class SignUpBrandNameTest(TestCase):
    """가입 경로에서도 서비스 이름이 400 으로 막히고 계정이 안 생긴다."""

    def setUp(self):
        cache.clear()

    def test_서비스_이름으로_가입하면_400(self):
        names = (
            "DeVoca",
            "DeVoca 공식",
            "데보카",
            "dev-voca",
            "Dev-Voca 공식",
            "dev‐voca",
            "dev–voca",
        )
        for number, name in enumerate(names):
            # 주소를 따로 둔다. 하나가 뚫려 계정이 생기면 다음 시도가 "이미 쓰는
            # 주소" 로 막혀 거름망이 막은 것처럼 보이기 때문이다.
            email = f"brand{number}@example.com"
            with self.subTest(name=name):
                res = self.client.post(
                    SIGNUP_URL,
                    {
                        "email": email,
                        "password": PASSWORD,
                        "display_name": name,
                        **CONSENT,
                    },
                    content_type="application/json",
                )

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json().get("display_name"), FORBIDDEN_MESSAGE)
                self.assertFalse(User.objects.filter(email=email).exists())
