"""관리자 회원 폼이 겹치는 이름·이메일을 500 이 아니라 폼 오류로 돌려주는지 본다.

폼의 기본 중복 검사는 다듬기 전의 값을 보고, save() 는 다듬은 값을 저장한다.
둘이 갈라지면 검사를 지난 값이 DB 제약에 걸려 500 이 된다. 그래서 전부
실제 admin 화면에 POST 해서 본다. 폼만 따로 부르면 admin 이 권한에 따라 칸을
빼는 경로를 못 본다.

보이지 않는 글자는 전부 이스케이프로 적는다. 소스에 그대로 두면 편집기나
포매터가 지워도 테스트가 초록으로 남는다.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from .forbidden_names import name_is_forbidden
from .tests import PASSWORD

User = get_user_model()

ADD_URL = "/admin/accounts/user/add/"
LOGIN_URL = "/admin/login/"
TAKEN = "이미 쓰고 있는 이름입니다."

# 다듬으면 사라지거나 공백이 되는 글자.
HIDDEN_CHARS = {
    "폭 없는 공백": "\u200b",
    "폭 없는 비결합자": "\u200c",
    "오른쪽에서 왼쪽 표시": "\u200f",
    "BOM": "\ufeff",
    "소프트 하이픈": "\u00ad",
}
FILLERS = {
    "초성 채움": "\u115f",
    "중성 채움": "\u1160",
    "한글 채움": "\u3164",
    "반각 한글 채움": "\uffa0",
    "점자 빈칸": "\u2800",
}


def change_url(user) -> str:
    return f"/admin/accounts/user/{user.pk}/change/"


class AdminFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password=PASSWORD, display_name="총괄"
        )
        cls.holder = User.objects.create_user(
            email="holder@example.com", password=PASSWORD, display_name="홍길동"
        )
        cls.member = User.objects.create_user(
            email="member@example.com", password=PASSWORD, display_name="원래이름"
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def post_change(self, user, client=None, **changes):
        """변경 화면이 보내는 칸을 그대로 채워 POST 한다."""
        data = {
            "email": user.email,
            "display_name": user.display_name,
            "avatar": "",
            "google_picture": "",
            "is_active": "on",
            **changes,
        }
        return (client or self.client).post(change_url(user), data)

    def post_add(self, client=None, **changes):
        data = {
            "email": "new@example.com",
            "usable_password": "true",
            "password1": PASSWORD,
            "password2": PASSWORD,
            **changes,
        }
        return (client or self.client).post(ADD_URL, data)

    def errors_of(self, res):
        self.assertEqual(res.status_code, 200, "폼이 다시 그려져야 한다")
        return res.context["adminform"].form.errors

    def assertNameTaken(self, res):
        self.assertEqual(self.errors_of(res).get("display_name"), [TAKEN])

    def assertUnchanged(self, user):
        row = User.objects.get(pk=user.pk)
        self.assertEqual((row.email, row.display_name), (user.email, user.display_name))

    def staff(self, *codenames, email="staff@example.com"):
        user = User.objects.create_user(email=email, password=PASSWORD, is_staff=True)
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts", codename__in=codenames
            )
        )
        client = self.client_class()
        client.force_login(user)
        return client


class DisplayNameCollisionTest(AdminFormTestCase):
    def test_끝에_숨은_글자를_붙여_겹치는_이름은_폼_오류다(self):
        for label, char in HIDDEN_CHARS.items():
            with self.subTest(label):
                res = self.post_change(self.member, display_name=f"홍길동{char}")
                self.assertNameTaken(res)
                self.assertUnchanged(self.member)

    def test_한글_채움_문자를_붙여_겹치는_이름은_폼_오류다(self):
        for label, char in FILLERS.items():
            with self.subTest(label):
                res = self.post_change(self.member, display_name=f"홍길동{char}")
                self.assertNameTaken(res)
                self.assertUnchanged(self.member)

    def test_글자_사이_채움_문자는_공백과_겹친다(self):
        User.objects.filter(pk=self.holder.pk).update(display_name="홍 길동")

        res = self.post_change(self.member, display_name="홍\u3164길동")

        self.assertNameTaken(res)
        self.assertUnchanged(self.member)

    def test_연속_공백을_줄이면_겹치는_이름은_폼_오류다(self):
        User.objects.filter(pk=self.holder.pk).update(display_name="홍 길동")

        self.assertNameTaken(self.post_change(self.member, display_name="홍   길동"))

    def test_대소문자만_다른_이름은_폼_오류다(self):
        User.objects.filter(pk=self.holder.pk).update(display_name="DevKim")

        for name in ("devkim", "DEVKIM", "dEvKiM"):
            with self.subTest(name):
                self.assertNameTaken(self.post_change(self.member, display_name=name))
                self.assertUnchanged(self.member)

    def test_조합형_한글로_겹치는_이름은_폼_오류다(self):
        # 완성형 "한글" 과 화면은 같고 문자열은 다르다.
        User.objects.filter(pk=self.holder.pk).update(display_name="한글")

        res = self.post_change(
            self.member, display_name="\u1112\u1161\u11ab\u1100\u1173\u11af"
        )

        self.assertNameTaken(res)

    def test_켈빈_기호로_겹치는_이름은_폼_오류다(self):
        # lower 하면 k 가 된다. DB 제약이 Lower 라 파이썬 쪽도 같아야 한다.
        User.objects.filter(pk=self.holder.pk).update(display_name="kim")

        self.assertNameTaken(self.post_change(self.member, display_name="\u212aim"))

    def test_파이썬과_DB_의_소문자가_갈리는_이름도_500_이_아니다(self):
        # 끝 시그마는 파이썬 lower 와 Postgres lower 가 다를 수 있다.
        # 그러면 clean_display_name 은 지나가고 모델 제약 검사가 잡아야 한다.
        name = "\u0391\u03a3"
        User.objects.filter(pk=self.holder.pk).update(display_name=name)

        res = self.post_change(self.member, display_name=name)

        self.assertTrue(self.errors_of(res), "겹치는 이름이 통과했다")
        self.assertUnchanged(self.member)

    def test_숨은_글자로_12자를_넘기면_길이_오류다(self):
        res = self.post_change(self.member, display_name=f"{'가' * 12}\u200b")

        self.assertIn("display_name", self.errors_of(res))
        self.assertUnchanged(self.member)

    def test_NUL_이_든_이름은_폼_오류다(self):
        res = self.post_change(self.member, display_name="홍길동\x00")

        self.assertIn("display_name", self.errors_of(res))

    def test_이름과_이메일이_같이_겹치면_둘_다_알린다(self):
        res = self.post_change(
            self.member, display_name="홍길동\u200b", email="HOLDER@example.com"
        )

        errors = self.errors_of(res)
        self.assertEqual(errors.get("display_name"), [TAKEN])
        self.assertIn("email", errors)
        self.assertUnchanged(self.member)


class DisplayNameAcceptedTest(AdminFormTestCase):
    def assertSaved(self, res, user, name):
        self.assertEqual(res.status_code, 302)
        self.assertEqual(User.objects.get(pk=user.pk).display_name, name)

    def test_자기_이름을_그대로_저장할_수_있다(self):
        self.assertSaved(self.post_change(self.member), self.member, "원래이름")

    def test_자기_이름의_대소문자를_바꿀_수_있다(self):
        User.objects.filter(pk=self.member.pk).update(display_name="devkim")
        self.member.refresh_from_db()

        res = self.post_change(self.member, display_name="DevKim")

        self.assertSaved(res, self.member, "DevKim")

    def test_자기_이름에_숨은_글자를_붙이면_다듬어_저장한다(self):
        res = self.post_change(self.member, display_name="원래이름\u200b\u3164")

        self.assertSaved(res, self.member, "원래이름")

    def test_겹치지_않는_이름은_다듬어_저장한다(self):
        res = self.post_change(self.member, display_name="새이름\u200f")

        self.assertSaved(res, self.member, "새이름")

    def test_빈_이름이면_자동_이름을_짓는다(self):
        for label, value in (
            ("빈 문자열", ""),
            ("공백만", "   "),
            ("숨은 글자만", "\u200b\u200f"),
            ("채움 문자만", "\u3164\u115f"),
        ):
            with self.subTest(label):
                res = self.post_change(self.member, display_name=value)

                self.assertEqual(res.status_code, 302)
                self.assertRegex(User.objects.get(pk=self.member.pk).display_name, r"^학습자\d+$")

    def test_이름이_비어_있는_옛_행이_있으면_빈_이름은_500_이_아니라_폼_오류다(self):
        # 빈 값끼리도 Lower 제약에 걸린다. save() 까지 가면 IntegrityError 다.
        User.objects.filter(pk=self.holder.pk).update(display_name="")

        res = self.post_change(self.member, display_name="")

        self.assertTrue(self.errors_of(res))
        self.assertUnchanged(self.member)

    def test_금칙어는_운영_계정용이라_저장된다(self):
        for name in ("관리자", "운영자", "admin", "devvoca"):
            with self.subTest(name):
                self.assertTrue(name_is_forbidden(name), "금칙어가 아니면 이 검사는 뜻이 없다")
                self.assertSaved(
                    self.post_change(self.member, display_name=name), self.member, name
                )

    def test_금칙어라도_겹치면_폼_오류다(self):
        User.objects.filter(pk=self.holder.pk).update(display_name="관리자")

        self.assertNameTaken(self.post_change(self.member, display_name="관리자\u200b"))


class EditEmailTest(AdminFormTestCase):
    def test_대소문자만_다른_이메일은_폼_오류다(self):
        for email in ("HOLDER@example.com", "holder@EXAMPLE.COM", "HoLdEr@ExAmPlE.cOm"):
            with self.subTest(email):
                res = self.post_change(self.member, email=email)

                self.assertIn("email", self.errors_of(res))
                self.assertUnchanged(self.member)

    def test_앞뒤_공백이_붙은_대문자_이메일도_폼_오류다(self):
        res = self.post_change(self.member, email="  HOLDER@example.com  ")

        self.assertIn("email", self.errors_of(res))
        self.assertUnchanged(self.member)

    def test_똑같은_이메일은_폼_오류다(self):
        res = self.post_change(self.member, email="holder@example.com")

        self.assertIn("email", self.errors_of(res))

    def test_자기_이메일을_대문자로_저장하면_소문자로_남는다(self):
        res = self.post_change(self.member, email="MEMBER@EXAMPLE.COM")

        self.assertEqual(res.status_code, 302)
        self.assertEqual(User.objects.get(pk=self.member.pk).email, "member@example.com")

    def test_새_이메일은_소문자로_저장한다(self):
        res = self.post_change(self.member, email="Fresh.Name@Example.COM")

        self.assertEqual(res.status_code, 302)
        self.assertEqual(User.objects.get(pk=self.member.pk).email, "fresh.name@example.com")

    def test_잘못된_이메일은_폼_오류다(self):
        for label, email in (
            ("빈 값", ""),
            ("공백만", "   "),
            ("형식 아님", "not-an-email"),
            ("너무 김", f"{'a' * 300}@example.com"),
            ("NUL", "a\x00@example.com"),
        ):
            with self.subTest(label):
                res = self.post_change(self.member, email=email)

                self.assertIn("email", self.errors_of(res))
                self.assertUnchanged(self.member)


class AddFormEmailTest(AdminFormTestCase):
    def test_대소문자만_다른_이메일은_폼_오류다(self):
        before = User.objects.count()

        for email in ("HOLDER@example.com", "holder@EXAMPLE.com", "  Holder@Example.Com "):
            with self.subTest(email):
                self.assertIn("email", self.errors_of(self.post_add(email=email)))
                self.assertEqual(User.objects.count(), before)

    def test_똑같은_이메일은_폼_오류다(self):
        self.assertIn("email", self.errors_of(self.post_add(email="holder@example.com")))

    def test_이메일과_비밀번호가_같이_틀리면_둘_다_알린다(self):
        res = self.post_add(email="HOLDER@example.com", password2=PASSWORD + "x")

        errors = self.errors_of(res)
        self.assertIn("email", errors)
        self.assertIn("password2", errors)

    def test_잘못된_이메일은_폼_오류다(self):
        for email in ("", "not-an-email", f"{'a' * 300}@example.com", "a\x00@example.com"):
            with self.subTest(email=email[:20]):
                self.assertIn("email", self.errors_of(self.post_add(email=email)))

    def test_새_계정은_소문자_이메일과_자동_이름으로_만들어진다(self):
        res = self.post_add(email="New.Person@Example.COM")

        self.assertEqual(res.status_code, 302)
        user = User.objects.get(email="new.person@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertRegex(user.display_name, r"^학습자\d+$")

    def test_비밀번호_없는_계정도_만들_수_있다(self):
        res = self.post_add(usable_password="false", password1="", password2="")

        self.assertEqual(res.status_code, 302)
        self.assertFalse(User.objects.get(email="new@example.com").has_usable_password())


class LegacyEmailTest(AdminFormTestCase):
    """대문자가 섞인 옛 행과 겹치는 주소로 계정을 둘 만들지 않는다.

    글자가 똑같은지만 보면 소문자로 내린 주소가 검사를 지나, 같은 주소의
    계정이 둘 생기고 그 주소의 로그인이 500 이 된다.
    """

    def setUp(self):
        super().setUp()
        User.objects.filter(pk=self.holder.pk).update(email="Legacy@Example.com")

    def test_변경_폼에서_겹치면_폼_오류다(self):
        res = self.post_change(self.member, email="legacy@example.com")

        self.assertIn("email", self.errors_of(res))
        self.assertUnchanged(self.member)

    def test_추가_폼에서_겹치면_폼_오류다(self):
        before = User.objects.count()

        res = self.post_add(email="LEGACY@example.com")

        self.assertIn("email", self.errors_of(res))
        self.assertEqual(User.objects.count(), before)

    def test_옛_행_자신은_소문자로_저장할_수_있다(self):
        legacy = User.objects.get(pk=self.holder.pk)

        res = self.post_change(legacy)

        self.assertEqual(res.status_code, 302)
        legacy.refresh_from_db()
        self.assertEqual(legacy.email, "legacy@example.com")


class PermissionTest(AdminFormTestCase):
    """권한에 따라 admin 이 폼의 칸을 뺀다. 칸이 없어도 폼이 터지면 안 된다."""

    def test_보기_권한만_있으면_화면은_열리고_저장은_403_이다(self):
        client = self.staff("view_user")

        self.assertEqual(client.get(change_url(self.member)).status_code, 200)
        res = self.post_change(self.member, client=client, display_name="바꿈")

        self.assertEqual(res.status_code, 403)
        self.assertUnchanged(self.member)

    def test_보기_권한만_있으면_겹치는_값을_보내도_403_이다(self):
        client = self.staff("view_user")

        res = self.post_change(
            self.member, client=client, display_name="홍길동\u200b", email="HOLDER@example.com"
        )

        self.assertEqual(res.status_code, 403)
        self.assertUnchanged(self.member)

    def test_권한_없는_스태프는_보기도_저장도_403_이다(self):
        client = self.staff()

        self.assertEqual(client.get(change_url(self.member)).status_code, 403)
        self.assertEqual(
            self.post_change(self.member, client=client, display_name="바꿈").status_code, 403
        )
        self.assertUnchanged(self.member)

    def test_변경_권한이_없으면_계정_추가도_403_이다(self):
        # UserAdmin 은 추가에 변경 권한까지 요구한다.
        client = self.staff("add_user", "view_user")
        before = User.objects.count()

        self.assertEqual(self.post_add(client=client).status_code, 403)
        self.assertEqual(User.objects.count(), before)

    def test_변경_권한_스태프가_겹치는_값을_보내면_폼_오류다(self):
        client = self.staff("view_user", "change_user")

        res = self.post_change(
            self.member, client=client, display_name="홍길동\u3164", email="HOLDER@example.com"
        )

        errors = self.errors_of(res)
        self.assertEqual(errors.get("display_name"), [TAKEN])
        self.assertIn("email", errors)
        self.assertUnchanged(self.member)

    def test_추가_변경_권한_스태프가_겹치는_이메일을_보내면_폼_오류다(self):
        client = self.staff("add_user", "view_user", "change_user")

        self.assertIn(
            "email", self.errors_of(self.post_add(client=client, email="HOLDER@example.com"))
        )

    def test_스태프가_아니면_로그인으로_돌려보낸다(self):
        client = self.client_class()
        client.force_login(self.member)

        res = self.post_change(self.holder, client=client, display_name="바꿈")

        self.assertEqual(res.status_code, 302)
        self.assertIn(LOGIN_URL, res["Location"])
        self.assertUnchanged(self.holder)

    def test_로그인_안_하면_로그인으로_돌려보낸다(self):
        res = self.post_change(self.holder, client=self.client_class(), display_name="바꿈")

        self.assertEqual(res.status_code, 302)
        self.assertIn(LOGIN_URL, res["Location"])
        self.assertUnchanged(self.holder)

    def test_없는_회원의_변경_화면은_500_이_아니다(self):
        for pk in ("9" * 30, "abc", "-1", "0"):
            with self.subTest(pk):
                res = self.client.get(f"/admin/accounts/user/{pk}/change/")

                self.assertIn(res.status_code, (302, 404))
