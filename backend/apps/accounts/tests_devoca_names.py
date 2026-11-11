"""서비스 이름을 DeVoca 로 바꾼 뒤 이름 거름망과 메일을 실제 경로로 흔들어 본다.

tests_brand_name 이 대표 표본을 보고, 여기서는 그 바깥을 본다.

- 보이지 않는 글자(U+2060, U+FEFF, U+200C/D, U+180E, 점자 빈칸, 반각 한글 채움),
  탭·줄바꿈·전각 공백, 원문자·수학 굵은 글자·로마 숫자처럼 NFKC 로 접히는 글자,
  풀어 쓴 한글 자모로 DeVoca/데보카 를 흉내 내는 이름을 막는다.
- 개발자 별명(devops, vocab_king, advocate, Devocean 등)은 막지 않는다.
- 가입, 이름 변경, 구글 첫 가입의 세 경로가 같은 규칙을 지킨다. 가입과 이름
  변경은 400 과 같은 안내를 주고 아무것도 만들거나 바꾸지 않는다. 구글 첫 가입은
  막지 않고 자동 이름으로 보낸다(구글에서 온 사람은 이름을 입력한 적이 없다).
- 메일에 나오는 이름은 대소문자까지 정확히 DeVoca 다. Devoca, DEVOCA 같은
  오타도 걸린다.

알려진 빈틈(일부러 테스트로 못 박지 않음): 키릴 문자(е, о, с, а), 악센트
(é, ç, 결합 악센트 U+0301), 작은 대문자(ᴅᴇᴠᴏᴄᴀ), 숫자 0 으로 바꾼 DeV0ca,
대소문자를 한 가지로 붙여 쓴 officialdevoca, OFFICIALDEVOCA, TEAMDEVOCA, DeVocateam
은 통과한다(forbidden_names.py 의 _CURRENT_NAME 주석과 같은 목록). 거름망 머리말이 말하는 대로
완벽한 거름망이 아니고, 빠져나간 이름은 관리자 화면에서 바꾼다.
"""

from __future__ import annotations

import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token

from apps.learning.tests_daily_cleanup import PurgeTestBase

from .forbidden_names import name_is_forbidden
from .models import GENERATED_NAME_PREFIX
from .tests import (
    CONSENT,
    EMAIL_CHANGE_URL,
    GOOGLE_URL,
    ME_URL,
    PASSWORD,
    REDIRECT_URI,
    SIGNUP_URL,
)

User = get_user_model()

FORBIDDEN_MESSAGE = ["쓸 수 없는 이름입니다. 다른 이름을 입력해주세요."]

# 화면에서 DeVoca / 데보카 로 읽히는 이름. 보이지 않는 글자는 \u 로 적는다.
IMPERSONATIONS = (
    "De\u2060Voca",  # 단어 결합자
    "De\ufeffVoca",  # BOM
    "De\u200cVoca",  # 폭 없는 비결합자
    "De\u200dVoca",  # 폭 없는 결합자
    "De\u180eVoca",  # 몽골 모음 구분자
    "De\u2800Voca",  # 점자 빈칸
    "De\uffa0Voca",  # 반각 한글 채움
    "De\u115fVoca",  # 한글 초성 채움
    "De\u1160Voca",  # 한글 중성 채움
    "De\u3000Voca",  # 전각 공백
    "De\tVoca",
    "De\nVoca",
    "De\u0332Voca",  # 결합 밑줄
    "Ⓓⓔⓥⓞⓒⓐ",  # 원문자
    "\U0001d403\U0001d41e\U0001d42f\U0001d428\U0001d41c\U0001d41a",  # 수학 굵은 글자
    "Ⅾevoca",  # 로마 숫자 D
    "ⅾevoca",  # 로마 숫자 d
    "dEvOcA",
    "x devoca",  # 앞 낱말과 띄우면 사칭이다
    "1devoca",
    "김devoca",
    "팀DeVoca",
    "DeVoca공식",
    "DeVoca 팀",
    "DeVoca_bot",
    "DeVoca7",
    "\u1103\u1166\u1107\u1169\u110f\u1161",  # 풀어 쓴 자모 데보카
    "데\u200b보카",
    "데\u3164보카",
    "데\uffa0보카",
    "데.보.카",
    "데보카팀",
    "데보카운영",
    "공식 데보카",
    "데보카_매니저",
)

# 옛 이름도 계속 막는다.
OLD_NAMES = (
    "devvoca",
    "dev-voca",
    "DEV-VOCA",
    "Dev Voca",
    "dev\u200bvoca",
    "데브보카",
    "데브 보카",
)

# 구분자를 지우면 devoca 근처가 되지만 평범한 개발자 별명.
ORDINARY = (
    "dev",
    "voca",
    "devops",
    "vocab-king",
    "vocab_king",
    "avocado",
    "advocate",
    "advocacy",
    "codevocab",
    "codevocal",
    "code vocab",
    "made vocal",
    "kimdev",
    "devkim",
    "devlog",
    "dev123",
    "voca123",
    "dev ocean",
    "Devocean",
    "devour",
    "devotion",
    "devolution",
    "redevelop",
    "deco",
    "devo",
    "devon",
    "jsdev",
    "edvoca",
    "vocadev",
    "Ted Evocation",
    "데브",
    "보카",
    "데이터",
    "데보션",
    "개발자보카",
    "토익보카",
    "데브옵스",
)


# 낱말 사이 경계로 떨어진 DeVoca. 대소문자 경계(소문자 뒤 대문자 D, DeVoca 뒤
# 대문자), 숫자, 밑줄, 한글, 다른 문자(키릴), 보이지 않는 글자, 전각 글자를
# 앞뒤에 붙여 본다.
CAMEL_IMPERSONATIONS = (
    "officialDeVoca",
    "OfficialDEVOCA",
    "officialDEVOCA",
    "OfficialDevoca",
    "DeVocaOfficial",
    "DEVOCA_TEAM",
    "TEAM_DEVOCA",
    "DEVOCA123",
    "123DEVOCA",
    "김DeVoca",
    "DeVoca김",
    "ДDeVoca",  # 키릴 대문자 De 앞
    "DeVocaД",  # 키릴 대문자 De 뒤
    "Official\u200bDeVoca",
    "DeVoca\u200bteam",
    "Official\u2060devoca",
    "Official\u3164DeVoca",
    "DeVoca\uffa0team",
    "ＯｆｆｉｃｉａｌＤｅＶｏｃａ",  # 전각 OfficialDeVoca
    "ＴｅａｍＤｅＶｏｃａ",  # 전각 TeamDeVoca
    "ＤｅＶｏｃａＴｅａｍ",  # 전각 DeVocaTeam
    "Official De Voca",
    "DeVoca's",
    # 끝 글자 a 와 대소문자가 다른 글자가 붙으면 낱말이 끊긴 것이다.
    "DEVOCAteam",
    "DeVocaTeam",
    "DeVoca123",
)

# 대소문자를 섞었지만 devoca 앞이나 뒤에 소문자가 붙어 다른 낱말이 되는 이름.
CAMEL_ORDINARY = (
    "CoDevocab",
    "ReDeVocab",
    "DeVocab",
    "DeVocal",
    "DevOcaml",
    "Dev_Ocaml",
    "IndieDevOcaml",
    "DevOcean",
    "Devocalize",
    "CodeVocab123",
    "CodeVocab김",
    "Code\u200bVocab",
    "codevocab\u200b",
    "ＣｏｄｅＶｏｃａｂ",  # 전각 CodeVocab
    "AdVocate",
    "EvocaTeam",
    "dev_ocaml",
    # 모두 대문자로 쓴 vocab, vocal, ocaml. 끝 A 뒤에 대문자가 이어지면 한 낱말이다.
    "DEVOCAB",
    "DEVOCAL",
    "DEVOCALIZE",
    "DEV_OCAML",
    "DE VOCAB",
)


class DevocaFilterEdgeTest(SimpleTestCase):
    """거름망 함수 하나만 본다."""

    def test_보이지_않는_글자와_접히는_글자로_흉내_낸_지금_이름을_막는다(self):
        for name in IMPERSONATIONS:
            with self.subTest(name=ascii(name)):
                self.assertTrue(name_is_forbidden(name))

    def test_옛_이름도_막는다(self):
        for name in OLD_NAMES:
            with self.subTest(name=ascii(name)):
                self.assertTrue(name_is_forbidden(name))

    def test_평범한_개발자_별명은_막지_않는다(self):
        for name in ORDINARY:
            with self.subTest(name=name):
                self.assertFalse(name_is_forbidden(name))

    def test_대소문자_숫자_한글_보이지_않는_글자로_경계를_만든_DeVoca_를_막는다(self):
        for name in CAMEL_IMPERSONATIONS:
            with self.subTest(name=ascii(name)):
                self.assertTrue(name_is_forbidden(name))

    def test_소문자가_붙어_다른_낱말이_되는_대소문자_섞인_이름은_막지_않는다(self):
        for name in CAMEL_ORDINARY:
            with self.subTest(name=ascii(name)):
                self.assertFalse(name_is_forbidden(name))


class SignUpDevocaTest(TestCase):
    """이메일 가입. 막힌 이름은 400 이고 계정이 안 생긴다."""

    def setUp(self):
        cache.clear()

    def signup(self, email, name):
        return self.client.post(
            SIGNUP_URL,
            {"email": email, "password": PASSWORD, "display_name": name, **CONSENT},
            content_type="application/json",
        )

    def test_흉내_낸_이름으로_가입하면_400_이고_계정이_없다(self):
        names = ("De\u2060Voca", "De\uffa0Voca", "Ⓓⓔⓥⓞⓒⓐ", "데\u3164보카", "팀DeVoca")
        for number, name in enumerate(names):
            # 주소를 따로 둔다. 하나가 뚫리면 다음 시도가 "이미 가입된 주소" 로
            # 막혀 거름망이 막은 것처럼 보인다.
            email = f"dyn{number}@example.com"
            with self.subTest(name=ascii(name)):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json().get("display_name"), FORBIDDEN_MESSAGE)
                self.assertFalse(User.objects.filter(email=email).exists())
        self.assertEqual(User.objects.count(), 0)

    def test_devoca_를_품은_평범한_이름으로는_가입된다(self):
        for number, name in enumerate(("codevocab", "advocate", "Devocean")):
            email = f"ok{number}@example.com"
            with self.subTest(name=name):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 201, res.content)
                self.assertEqual(User.objects.get(email=email).display_name, name)

    def test_대소문자_경계로_붙인_DeVoca_로_가입하면_400_이고_계정이_없다(self):
        for number, name in enumerate(("TeamDeVoca", "DeVocaTeam", "myDEVOCA", "DEVOCAteam")):
            email = f"camel{number}@example.com"
            with self.subTest(name=name):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json().get("display_name"), FORBIDDEN_MESSAGE)
                self.assertFalse(User.objects.filter(email=email).exists())

    def test_OfficialDeVoca_는_길이에서_먼저_막힌다(self):
        """14자라 거름망 전에 길이 제한(12자)에 걸린다."""
        for number, name in enumerate(("OfficialDeVoca", "Official\u200bDeVoca")):
            email = f"long{number}@example.com"
            with self.subTest(name=ascii(name)):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 400)
                self.assertNotEqual(res.json().get("display_name"), FORBIDDEN_MESSAGE)
                self.assertIn("12", res.json()["display_name"][0])
                self.assertFalse(User.objects.filter(email=email).exists())

    def test_dev_ocaml_과_DevOcaml_로는_가입된다(self):
        for number, name in enumerate(("dev_ocaml", "DevOcaml", "CoDevocab")):
            email = f"ocaml{number}@example.com"
            with self.subTest(name=name):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 201, res.content)
                self.assertEqual(User.objects.get(email=email).display_name, name)

    def test_모두_대문자인_DEV_OCAML_과_DEVOCAB_로는_가입된다(self):
        """이름 중복은 대소문자를 안 가려서 dev_ocaml 과 다른 테스트에 둔다."""
        for number, name in enumerate(("DEV_OCAML", "DEVOCAB")):
            email = f"caps{number}@example.com"
            with self.subTest(name=name):
                res = self.signup(email, name)

                self.assertEqual(res.status_code, 201, res.content)
                self.assertEqual(User.objects.get(email=email).display_name, name)


class MeNameDevocaTest(TestCase):
    """이름 변경. 막힌 이름은 400 이고 이름이 그대로다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="me@example.com", password=PASSWORD, display_name="평범한이름"
        )
        self.token = Token.objects.create(user=self.user)

    def patch_me(self, **body):
        return self.client.patch(
            ME_URL,
            body,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

    def test_흉내_낸_이름으로_바꾸면_400_이고_이름이_그대로다(self):
        for name in ("DeVoca", "De\u200dVoca", "데보카", "데\uffa0보카", "dev-voca"):
            with self.subTest(name=ascii(name)):
                res = self.patch_me(display_name=name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
                self.user.refresh_from_db()
                self.assertEqual(self.user.display_name, "평범한이름")

    def test_대소문자_경계로_붙인_DeVoca_로_바꾸면_400_이고_이름이_그대로다(self):
        for name in ("TeamDeVoca", "DeVocaTeam", "myDEVOCA"):
            with self.subTest(name=ascii(name)):
                res = self.patch_me(display_name=name)

                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
                self.user.refresh_from_db()
                self.assertEqual(self.user.display_name, "평범한이름")

    def test_dev_ocaml_로는_바꿀_수_있다(self):
        for name in ("dev_ocaml", "DevOcaml"):
            with self.subTest(name=name):
                res = self.patch_me(display_name=name)

                self.assertEqual(res.status_code, 200, res.content)
                self.user.refresh_from_db()
                self.assertEqual(self.user.display_name, name)

    def test_이름을_바꾸기_전에_DeVoca_였던_회원은_그_이름을_그대로_보낼_수_있다(self):
        """옛 규칙에서는 DeVoca 가 통과했다. 아바타만 바꾸는 저장이 막히면 안 된다."""
        User.objects.filter(pk=self.user.pk).update(display_name="DeVoca")

        res = self.patch_me(display_name="DeVoca", avatar="a3")

        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "a3")

    def test_DeVoca_였던_회원도_대소문자를_바꾸면_막힌다(self):
        User.objects.filter(pk=self.user.pk).update(display_name="DeVoca")

        res = self.patch_me(display_name="DEVOCA")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["display_name"], FORBIDDEN_MESSAGE)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "DeVoca")


class GoogleDevocaTest(TestCase):
    """구글 첫 가입. 막힌 이름이면 가입은 되고 자동 이름이 붙는다."""

    def setUp(self):
        cache.clear()

    def google(self, name, email):
        payload = {"code": "구글이-준-코드", "redirect_uri": REDIRECT_URI, **CONSENT}
        info = {"email": email, "name": name, "picture": "https://lh3.googleusercontent.com/a/x"}
        with mock.patch("apps.accounts.views.fetch_google_user", return_value=info):
            return self.client.post(GOOGLE_URL, payload, content_type="application/json")

    def test_DeVoca_류_구글_이름은_자동_이름으로_가입된다(self):
        for number, name in enumerate(("DeVoca", "De\u200bVoca", "데보카", "DeVoca 공식")):
            email = f"g{number}@example.com"
            with self.subTest(name=ascii(name)):
                res = self.google(name, email)

                self.assertEqual(res.status_code, 201)
                stored = User.objects.get(email=email).display_name
                self.assertTrue(stored.startswith(GENERATED_NAME_PREFIX), stored)
                self.assertNotIn("devoca", stored.casefold())

    def test_대소문자_경계로_붙인_DeVoca_구글_이름은_자동_이름이_된다(self):
        for number, name in enumerate(("TeamDeVoca", "DeVocaTeam", "myDEVOCA")):
            email = f"gc{number}@example.com"
            with self.subTest(name=name):
                res = self.google(name, email)

                self.assertEqual(res.status_code, 201)
                stored = User.objects.get(email=email).display_name
                self.assertTrue(stored.startswith(GENERATED_NAME_PREFIX), stored)

    def test_OfficialDeVoca_구글_이름은_12자로_잘려_DeVoca_가_남지_않는다(self):
        res = self.google("OfficialDeVoca", "g-long@example.com")

        self.assertEqual(res.status_code, 201)
        stored = User.objects.get(email="g-long@example.com").display_name
        self.assertEqual(stored, "OfficialDeVo")

    def test_dev_ocaml_구글_이름은_그대로_쓴다(self):
        for number, name in enumerate(("dev_ocaml", "DevOcaml")):
            email = f"go{number}@example.com"
            with self.subTest(name=name):
                res = self.google(name, email)

                self.assertEqual(res.status_code, 201)
                self.assertEqual(User.objects.get(email=email).display_name, name)

    def test_평범한_구글_이름은_그대로_쓴다(self):
        res = self.google("codevocab", "g-ok@example.com")

        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="g-ok@example.com").display_name, "codevocab")


# 대소문자를 무시하고 찾은 서비스 이름. 찾은 것은 모두 정확히 DeVoca 여야 한다.
ANY_CASE_NAME = re.compile(r"de[\s\-]?voca", re.IGNORECASE)


class ExactNameInMailAssertions:
    def assert_exact_name(self, message):
        for text in (message.subject, message.body):
            # 웹 주소 dev-voca.vercel.app 은 이름이 아니다.
            found = ANY_CASE_NAME.findall(text.replace("dev-voca.vercel.app", ""))
            self.assertTrue(found, text)
            self.assertEqual(set(found), {"DeVoca"}, text)
        self.assertTrue(message.subject.startswith("[DeVoca] "), message.subject)


class EmailChangeMailExactNameTest(ExactNameInMailAssertions, TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("apps.accounts.mail._really_sends", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = User.objects.create_user(
            email="old@example.com", password=PASSWORD, display_name="주인"
        )
        self.token = Token.objects.create(user=self.user)

    def test_확인_메일의_이름이_정확히_DeVoca_다(self):
        res = self.client.post(
            EMAIL_CHANGE_URL,
            {"new_email": "new@example.com", "current_password": PASSWORD},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.token.key}",
        )

        self.assertEqual(res.status_code, 202)
        self.assertEqual(len(django_mail.outbox), 1)
        self.assert_exact_name(django_mail.outbox[0])


class PurgeNoticeMailExactNameTest(ExactNameInMailAssertions, PurgeTestBase):
    def test_휴면_안내_메일의_이름이_정확히_DeVoca_다(self):
        self.member("sleepy", seen_days_ago=340)

        self.apply()

        self.assertEqual(len(django_mail.outbox), 1)
        self.assert_exact_name(django_mail.outbox[0])
