"""로그인 토큰을 지문(sha256)으로 저장한 것을 깨뜨려 보는 테스트.

여기서 보는 것:
- 0016 이 원문을 지문으로 바꿀 때 11-13 전 토큰, 그 토큰을 이어 받은 토큰, 부모가 지워진
  토큰, 새 방식 토큰의 device 가 각각 맞게 되는가. 되돌리면 토큰이 모두 지워지는가
- DB 가 샜을 때: 표의 값(지문, device)을 토큰으로 내밀어도 401 인가. 토큰을 내주는 길마다
  응답으로 받은 원문이 DB 어느 표에도 남지 않는가
- 이어 가기: 응답 유실, 두 단계 벌어짐, 계산이 맞지 않는 latest, 서버 비밀 키 변경, 동시 요청,
  재사용 감지
- 관리자 삭제: 한 줄을 지워도 그 로그인이 통째로 지워져 남은 앞 토큰이 지운 값을 못 되살리는가
- 방어를 빼면 위 테스트가 빨개지는가(구현 파일은 건드리지 않고 mock 으로 뺀다)
"""

from __future__ import annotations

import importlib
import io
import sys
import unittest
from datetime import timedelta
from unittest import mock

from django.apps import apps as global_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts import admin as accounts_admin
from apps.accounts.models import LoginToken, token_digest

from .tests import (
    CONSENT,
    EMAIL_CHANGE_CONFIRM_URL,
    EMAIL_CHANGE_URL,
    GOOGLE_URL,
    LOGIN_URL,
    LOGOUT_URL,
    ME_URL,
    PASSWORD,
    REDIRECT_URI,
    SIGNUP_URL,
)
from .tests_password import NEW_PASSWORD, PASSWORD_URL
from .tests_token_renew_dynamic import DAY, GRACE, RENEW_URL, RenewMixin, _renew, _together, auth

User = get_user_model()

ADMIN_LIST_URL = "/admin/accounts/logintoken/"
MIGRATION_0016 = importlib.import_module("apps.accounts.migrations.0016_login_token_digest_data")

# 무작위 원문 대신 쓰는 값. 진짜 비밀값처럼 보이지 않게 한 글자를 늘어놓는다.
FOREIGN_RAW = "9" * 40


def tables_holding(raw: str) -> list[str]:
    """raw 가 어느 칸에든 들어 있는 표 이름. 행 전체를 글자로 바꿔 찾는다(Postgres)."""
    hits = []
    with connection.cursor() as cursor:
        for table in connection.introspection.table_names(cursor):
            cursor.execute(
                f"SELECT count(*) FROM {connection.ops.quote_name(table)} AS r"
                " WHERE r::text LIKE %s",
                [f"%{raw}%"],
            )
            if cursor.fetchone()[0]:
                hits.append(table)
    return hits


def run_case(case: type, name: str) -> unittest.TestResult:
    result = unittest.TestResult()
    case(name)(result)
    return result


# ---------------------------------------------------------------------------
# 1. 0016 데이터 변환
# ---------------------------------------------------------------------------


@unittest.skipUnless(connection.vendor == "postgresql", "raw SQL 이 Postgres 문법이다")
class DigestMigrationTest(TransactionTestCase):
    """0013 까지 되돌리고 원문 행을 넣은 뒤 끝까지 올린다.

    행 넷(owner):
    - legacy: 11-13 전 토큰. device 가 자기 원문이다(0013).
    - child: legacy 를 이어 받은 토큰. device 가 legacy 원문이다.
    - orphan: 부모가 지워진 토큰. device 가 표에 없는 원문이다.
    - fresh: 새 방식 토큰. device 가 무작위 값이다.
    남의 계정(other)의 11-13 전 토큰도 하나 넣는다.
    """

    LEGACY, CHILD, ORPHAN, FRESH, OTHER = ("a" * 40, "b" * 40, "c" * 40, "e" * 40, "7" * 40)
    DEAD_PARENT = "d" * 40
    FRESH_DEVICE = "f" * 40

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.other = User.objects.create_user(email="other@example.com", password=PASSWORD)

    def migrate(self, target: str | None = None) -> None:
        args = ["accounts", target] if target else ["accounts"]
        call_command("migrate", *args, stdout=io.StringIO(), verbosity=0)

    def insert(self, user, key: str, device: str, age=timedelta(0), delivered=True, replaced_ago=None):
        now = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO accounts_logintoken (key, user_id, created, device, delivered, replaced_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                [key, user.pk, now - age, device, delivered,
                 None if replaced_ago is None else now - replaced_ago],
            )

    def raw_rows(self) -> list[tuple[str, str]]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT key, device FROM accounts_logintoken ORDER BY id")
            return cursor.fetchall()

    def key_column_length(self) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT character_maximum_length FROM information_schema.columns"
                " WHERE table_name = 'accounts_logintoken' AND column_name = 'key'"
            )
            return cursor.fetchone()[0]

    def seed_and_upgrade(self) -> None:
        try:
            self.migrate("0013")
            self.assertEqual(self.key_column_length(), 40)
            # 폰이 legacy 를 이어 받아(child) 쓰기 시작했다. legacy 는 바뀐 지 10분.
            self.insert(self.owner, self.LEGACY, self.LEGACY, age=DAY * 3, replaced_ago=timedelta(minutes=10))
            self.insert(self.owner, self.CHILD, self.LEGACY, age=DAY * 2)
            self.insert(self.owner, self.ORPHAN, self.DEAD_PARENT, age=DAY)
            self.insert(self.owner, self.FRESH, self.FRESH_DEVICE)
            self.insert(self.other, self.OTHER, self.OTHER)
        finally:
            self.migrate()

    def row(self, raw: str) -> LoginToken:
        return LoginToken.objects.get(digest=token_digest(raw))

    def me(self, raw: str) -> int:
        return Client().get(ME_URL, **auth(raw)).status_code

    def test_원문은_지문으로_device_는_부모가_살아_있을_때만_부모_지문으로_바뀐다(self):
        self.seed_and_upgrade()

        self.assertEqual(self.key_column_length(), 64)
        self.assertEqual(LoginToken.objects.count(), 5)
        # key 칸에 원문이 하나도 안 남았다.
        for key, _ in self.raw_rows():
            self.assertEqual(len(key), 64)
        self.assertEqual(self.row(self.LEGACY).device, token_digest(self.LEGACY))
        self.assertEqual(self.row(self.CHILD).device, token_digest(self.LEGACY))
        self.assertEqual(self.row(self.ORPHAN).device, self.DEAD_PARENT)
        self.assertEqual(self.row(self.FRESH).device, self.FRESH_DEVICE)
        self.assertEqual(self.row(self.OTHER).device, token_digest(self.OTHER))
        for raw in (self.LEGACY, self.CHILD, self.ORPHAN, self.FRESH, self.OTHER):
            self.assertEqual(tables_holding(raw), [], raw)

    def test_바꾼_뒤에도_원래_원문으로_인증되고_지문으로는_안_된다(self):
        self.seed_and_upgrade()

        for raw in (self.LEGACY, self.CHILD, self.ORPHAN, self.FRESH, self.OTHER):
            with self.subTest(raw=raw[0]):
                self.assertEqual(self.me(raw), 200)
                self.assertEqual(self.me(token_digest(raw)), 401)

    def test_11_13_전_토큰은_유예가_지나_와도_그_요청만_401_이고_이어_받은_토큰은_산다(self):
        self.seed_and_upgrade()
        LoginToken.objects.filter(digest=token_digest(self.LEGACY)).update(
            replaced_at=timezone.now() - GRACE - timedelta(minutes=1)
        )

        self.assertEqual(self.me(self.LEGACY), 401)

        self.assertEqual(self.me(self.CHILD), 200)
        self.assertEqual(LoginToken.objects.filter(user=self.owner).count(), 4)

    def test_이어_받은_토큰의_다음_토큰도_같은_로그인이고_로그아웃이_그_로그인만_지운다(self):
        self.seed_and_upgrade()

        res = Client().post(RENEW_URL, **auth(self.CHILD))
        self.assertEqual(res.status_code, 200)
        nxt = res.json()["token"]
        self.assertNotEqual(nxt, self.CHILD)
        self.assertEqual(self.row(nxt).device, token_digest(self.LEGACY))

        self.assertEqual(Client().post(LOGOUT_URL, **auth(nxt)).status_code, 204)

        for raw in (self.LEGACY, self.CHILD, nxt):
            self.assertEqual(self.me(raw), 401)
        for raw in (self.ORPHAN, self.FRESH, self.OTHER):
            self.assertEqual(self.me(raw), 200)

    def test_되돌리면_토큰이_모두_지워지고_칸이_40자로_돌아간다(self):
        LoginToken.objects.create(user=self.owner)
        LoginToken.objects.create(user=self.other)
        try:
            self.migrate("0013")
            self.assertEqual(self.raw_rows(), [])
            self.assertEqual(self.key_column_length(), 40)
        finally:
            self.migrate()
        self.assertEqual(LoginToken.objects.count(), 0)

    def test_변환을_한_번_더_돌려도_지문은_다시_바뀌지_않는다(self):
        token = LoginToken.objects.create(user=self.owner)
        before = self.raw_rows()

        MIGRATION_0016.hash_tokens(global_apps, None)

        self.assertEqual(self.raw_rows(), before)
        self.assertEqual(self.me(token.key), 200)


# ---------------------------------------------------------------------------
# 2. DB 가 샜을 때
# ---------------------------------------------------------------------------


@unittest.skipUnless(connection.vendor == "postgresql", "행을 글자로 바꿔 찾는 SQL 이 Postgres 문법이다")
class RawNeverStoredTest(RenewMixin, TestCase):
    """토큰을 내주는 길마다 응답으로 받은 원문이 DB 어느 표에도 없다."""

    def assert_not_stored(self, raw: str) -> None:
        self.assertRegex(raw, r"^[0-9a-f]{40}$")
        # 찾는 SQL 이 헛돌지 않는지: 지문은 표에 있어야 한다.
        self.assertEqual(tables_holding(token_digest(raw)), ["accounts_logintoken"])
        self.assertEqual(tables_holding(raw), [])
        self.assertEqual(self.me(raw), 200)

    def test_가입(self):
        res = self.client.post(
            SIGNUP_URL, {"email": "new@example.com", "password": PASSWORD, **CONSENT},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assert_not_stored(res.json()["token"])

    def test_로그인(self):
        res = self.client.post(
            LOGIN_URL, {"email": "owner@example.com", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assert_not_stored(res.json()["token"])

    def test_구글_로그인(self):
        with mock.patch(
            "apps.accounts.views.fetch_google_user",
            return_value={"email": "g@example.com", "name": "구글", "picture": ""},
        ):
            res = self.client.post(
                GOOGLE_URL, {"code": "코드", "redirect_uri": REDIRECT_URI, **CONSENT},
                content_type="application/json",
            )
        self.assertEqual(res.status_code, 201, res.content)
        self.assert_not_stored(res.json()["token"])

    def test_비밀번호_변경(self):
        a = self.token()
        res = self.client.post(
            PASSWORD_URL, {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            content_type="application/json", **auth(a.key),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assert_not_stored(res.json()["token"])

    def test_이메일_변경_확인(self):
        a = self.token()
        with mock.patch("apps.accounts.views.send_account_mail") as sent:
            res = self.client.post(
                EMAIL_CHANGE_URL, {"new_email": "moved@example.com", "current_password": PASSWORD},
                content_type="application/json", **auth(a.key),
            )
        self.assertEqual(res.status_code, 202, res.content)
        link = sent.call_args.kwargs["body"].split("/profile/email/")[1].split()[0]

        res = self.client.post(EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json")

        self.assertEqual(res.status_code, 200, res.content)
        self.assert_not_stored(res.json()["token"])

    def test_이어_가기와_이어_준_앞_토큰(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)
        self.assertNotEqual(b, a.key)
        self.assert_not_stored(b)
        self.assert_not_stored(a.key)

    def test_표의_지문과_device_를_토큰으로_내밀면_401_이고_로그인이_안_끊긴다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)
        legacy = self.token(user=self.other)
        LoginToken.objects.filter(pk=legacy.pk).update(device=legacy.digest)

        leaked = list(LoginToken.objects.values_list("digest", "device"))
        for digest, device in leaked:
            for value in (digest, device):
                with self.subTest(value=value[:8]):
                    self.assertEqual(self.me(value), 401)
                    self.assertEqual(self.renew(value).status_code, 401)

        self.assertEqual(LoginToken.objects.count(), 3)
        self.assertEqual(self.me(b), 200)
        self.assertEqual(self.me(legacy.key), 200)

    def test_이상한_헤더는_500_이_아니라_401(self):
        self.token()
        for value in ("a\x00b", "é" * 41, "x" * 10_000, "a" * 39, "A" * 40):
            with self.subTest(value=value[:5]):
                res = Client(raise_request_exception=False).get(ME_URL, HTTP_AUTHORIZATION=f"Token {value}")
                self.assertEqual(res.status_code, 401)

    def test_원문을_대문자로_바꾸면_다른_토큰이다(self):
        a = self.token()
        self.assertEqual(self.me(a.key.upper()), 401)


# ---------------------------------------------------------------------------
# 3. 이어 가기
# ---------------------------------------------------------------------------


class RenewDigestTest(RenewMixin, TestCase):
    """이어 가기가 원문을 다시 계산해 돌려주는 자리들."""

    def test_응답을_잃고_옛_토큰으로_다시_오면_같은_새_토큰이고_행이_안_는다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)

        for _ in range(3):
            self.assertEqual(self.renewed(a.key), b)

        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 2)
        self.assertEqual(self.me(b), 200)

    def test_두_단계_벌어져도_유예_안의_옛_토큰은_가장_새_토큰을_받는다(self):
        a = self.token(age=DAY * 3)
        b = self.renewed(a.key)
        self.assertEqual(self.me(b), 200)  # a 가 방금 바뀐 것으로 적힌다
        LoginToken.objects.filter(digest=token_digest(b)).update(created=timezone.now() - DAY * 2)
        c = self.renewed(b)
        self.assertNotIn(c, (a.key, b))

        self.assertEqual(self.renewed(a.key), c)
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)

    def test_계산이_안_맞는_latest_가_있으면_다음_토큰을_새로_내고_다시_와도_같은_값이다(self):
        a = self.token(age=DAY * 2)
        LoginToken.objects.create(user=self.owner, device=a.device, delivered=False, key=FOREIGN_RAW)

        b = self.renewed(a.key)
        self.assertNotIn(b, (a.key, FOREIGN_RAW))
        self.assertEqual(self.renewed(a.key), b)
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)

        # 새로 낸 쪽이 쓰이면 계산이 안 맞던 토큰도 바뀐 것으로 적힌다.
        self.assertEqual(self.me(b), 200)
        self.assertIsNotNone(self.row(FOREIGN_RAW).replaced_at)
        self.assertIsNotNone(self.row(a.key).replaced_at)

    def test_계산이_안_맞는_latest_를_쓰던_쪽도_계속_이어_간다(self):
        a = self.token(age=DAY * 2)
        LoginToken.objects.create(user=self.owner, device=a.device, delivered=False, key=FOREIGN_RAW)
        LoginToken.objects.filter(digest=token_digest(FOREIGN_RAW)).update(created=timezone.now() - DAY * 2)

        self.assertEqual(self.me(FOREIGN_RAW), 200)
        nxt = self.renewed(FOREIGN_RAW)

        self.assertNotIn(nxt, (a.key, FOREIGN_RAW))
        self.assertEqual(self.me(nxt), 200)

    def test_서버_비밀_키를_바꾸면_새_토큰을_내고_500_이_아니다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)

        with override_settings(SECRET_KEY=settings.SECRET_KEY[::-1]):
            b2 = self.renewed(a.key)
            self.assertNotIn(b2, (a.key, b))
            self.assertEqual(self.renewed(a.key), b2)
            self.assertEqual(self.me(b2), 200)
            self.assertEqual(self.me(b), 200)
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)

    def test_다음_토큰은_서버_비밀_키에_따라_다르다(self):
        """비밀 키를 안 섞으면 옛 토큰을 빼 간 쪽이 서버에 묻지 않고 다음 토큰을 계산한다."""
        got = []
        for secret in (settings.SECRET_KEY, settings.SECRET_KEY[::-1]):
            LoginToken.objects.all().delete()
            a = LoginToken.objects.create(user=self.owner, key="a" * 40)
            self.age(a, DAY * 2)
            with override_settings(SECRET_KEY=secret):
                got.append(self.renewed("a" * 40))
        self.assertNotEqual(got[0], got[1])

    def test_유예가_지난_옛_토큰은_그_로그인을_끊고_다시_와도_되살리지_못한다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)
        self.assertEqual(self.me(b), 200)
        laptop = self.token()
        theirs = self.token(user=self.other)
        self.push_replaced(a.key, GRACE + timedelta(minutes=1))

        self.assertEqual(self.renew(a.key).status_code, 401)

        self.assertFalse(LoginToken.objects.filter(device=a.device).exists())
        self.assertEqual(self.renew(a.key).status_code, 401)
        self.assertEqual(self.me(b), 401)
        self.assertEqual(self.me(laptop.key), 200)
        self.assertEqual(self.me(theirs.key), 200)

    def test_원문_없는_객체로_이어_가기를_부르면_엉뚱한_토큰을_만들지_않고_멈춘다(self):
        a = self.token(age=DAY * 2)
        self.renewed(a.key)
        loaded = LoginToken.objects.get(pk=a.pk)
        self.assertIsNone(loaded.key)

        with self.assertRaises(ValueError):
            loaded.renew()
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 2)

    def test_DB_에서_읽은_객체는_원문이_없다(self):
        a = self.token()
        self.assertIsNone(LoginToken.objects.get(pk=a.pk).key)


class RenewExistingNextTest(RenewMixin, TestCase):
    """계산이 안 맞는 latest 갈래를 한 번 탄 뒤 latest 가 또 바뀌어도, 이미 만든 다음 토큰을 돌려준다.

    이 갈래는 이 토큰의 다음 토큰(next)을 만든다. next 가 이미 있는데 또 만들면 지문이 겹쳐
    500 이 나고, latest 가 그대로라 그 뒤 이어 가기마다 500 이다.
    """

    def safe_renew(self, key: str) -> tuple[int, str | None]:
        res = Client(raise_request_exception=False).post(RENEW_URL, **auth(key))
        token = res.json().get("token") if res.status_code == 200 else None
        return res.status_code, token

    def test_서버_비밀_키를_바꿨다_되돌려도_이미_있는_다음_토큰을_돌려준다(self):
        a = self.token(age=DAY * 2)
        b = self.renewed(a.key)
        with override_settings(SECRET_KEY=settings.SECRET_KEY[::-1]):
            b2 = self.renewed(a.key)
            self.assertNotEqual(b2, b)

        self.assertEqual(self.safe_renew(a.key), (200, b))
        self.assertEqual(self.safe_renew(a.key), (200, b))
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)
        self.assertEqual(self.me(b), 200)

    def test_계산이_안_맞는_latest_가_지금보다_뒤에_만들어졌어도_두_번째_이어_가기가_된다(self):
        a = self.token(age=DAY * 2)
        LoginToken.objects.create(
            user=self.owner, device=a.device, delivered=False, key=FOREIGN_RAW,
            created=timezone.now() + timedelta(hours=1),
        )

        status, b = self.safe_renew(a.key)
        self.assertEqual(status, 200)
        self.assertNotIn(b, (a.key, FOREIGN_RAW))

        self.assertEqual(self.safe_renew(a.key), (200, b))
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)

    def test_배포_전_무작위_토큰이_쓰이고_이어진_뒤_유예_안의_옛_토큰이_와도_이미_있는_다음_토큰이다(self):
        # 배포 전: A 가 무작위 R 로 이어 받았다(아직 안 쓰임).
        a = self.token(age=DAY * 3)
        LoginToken.objects.create(
            user=self.owner, device=a.device, delivered=False, key=FOREIGN_RAW,
            created=timezone.now() - DAY * 2,
        )
        # 배포 뒤: 응답을 잃은 A 가 다시 와서 B 를 받는다.
        status, b = self.safe_renew(a.key)
        self.assertEqual(status, 200)
        self.assertNotIn(b, (a.key, FOREIGN_RAW))
        # 쿠키에는 R 이 들어가 있었다. R 이 쓰여 A 가 바뀐 것으로 적히고(유예 시작), R 은 하루가
        # 지나 S 로 이어 받는다. latest 는 B 보다 새 S 다.
        self.assertEqual(self.me(FOREIGN_RAW), 200)
        self.assertIsNotNone(self.row(a.key).replaced_at)
        status, s = self.safe_renew(FOREIGN_RAW)
        self.assertEqual(status, 200)
        self.assertNotIn(s, (a.key, b, FOREIGN_RAW))

        # 유예 안의 A: S 는 A 에서 계산되지 않고 A 의 다음 토큰 B 는 이미 있다.
        self.assertEqual(self.safe_renew(a.key), (200, b))
        self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 4)


@unittest.skipUnless(connection.vendor == "postgresql", "동시성은 Postgres 에서만 뜻이 있다")
class RenewDigestConcurrencyTest(RenewMixin, TransactionTestCase):
    """동시에 몰려도 돌려준 원문이 모두 같고, 그 원문으로 인증된다."""

    def test_응답_유실_뒤_옛_토큰_넷이_동시에_와도_같은_새_토큰이다(self):
        for _ in range(3):
            a = self.token(age=DAY * 2)
            b = self.renewed(a.key)

            results = _together(*[_renew(a.key)] * 4)

            self.assertEqual([s for s, _ in results], [200] * 4, results)
            self.assertEqual({body["token"] for _, body in results}, {b})
            self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 2)

    def test_계산이_안_맞는_latest_가_있을_때_넷이_동시에_와도_새_토큰은_하나다(self):
        for i in range(3):
            a = self.token(age=DAY * 2)
            LoginToken.objects.create(
                user=self.owner, device=a.device, delivered=False, key=str(i) * 40
            )

            results = _together(*[_renew(a.key)] * 4)

            self.assertEqual([s for s, _ in results], [200] * 4, results)
            tokens = {body["token"] for _, body in results}
            self.assertEqual(len(tokens), 1, tokens)
            self.assertEqual(LoginToken.objects.filter(device=a.device).count(), 3)
            self.assertEqual(Client().get(ME_URL, **auth(tokens.pop())).status_code, 200)


# ---------------------------------------------------------------------------
# 4. 관리자 삭제
# ---------------------------------------------------------------------------


class AdminDeleteWholeLoginTest(RenewMixin, TestCase):
    """한 줄을 지워도 그 로그인(device)을 통째로 지운다."""

    def setUp(self):
        super().setUp()
        self.a = self.token(age=DAY * 2)
        self.b = self.renewed(self.a.key)
        self.assertEqual(self.me(self.b), 200)
        self.laptop = self.token()
        self.theirs = self.token(user=self.other)
        self.root = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
        self.admin = Client()
        self.admin.force_login(self.root)

    def delete_one(self, raw: str):
        pk = self.row(raw).pk
        return self.admin.post(f"{ADMIN_LIST_URL}{pk}/delete/", {"post": "yes"})

    def delete_selected(self, *raws: str):
        pks = [self.row(raw).pk for raw in raws]
        return self.admin.post(
            ADMIN_LIST_URL, {"action": "delete_selected", "_selected_action": pks, "post": "yes"}
        )

    def assert_login_gone_and_not_revived(self) -> None:
        self.assertFalse(LoginToken.objects.filter(device=self.a.device).exists())
        self.assertEqual(self.renew(self.a.key).status_code, 401)
        self.assertEqual(self.me(self.b), 401)
        self.assertFalse(LoginToken.objects.filter(digest=token_digest(self.b)).exists())

    def test_가장_새_줄을_지우면_남은_앞_토큰이_지운_값을_못_되살린다(self):
        res = self.delete_one(self.b)

        self.assertEqual(res.status_code, 302)
        self.assert_login_gone_and_not_revived()
        self.assertEqual(self.me(self.laptop.key), 200)
        self.assertEqual(self.me(self.theirs.key), 200)

    def test_앞_줄을_지워도_그_로그인이_통째로_지워진다(self):
        self.assertEqual(self.delete_one(self.a.key).status_code, 302)

        self.assert_login_gone_and_not_revived()
        self.assertEqual(self.me(self.laptop.key), 200)

    def test_일괄_삭제도_고른_줄의_로그인만_통째로_지운다(self):
        res = self.delete_selected(self.b, self.theirs.key)

        self.assertEqual(res.status_code, 302)
        self.assert_login_gone_and_not_revived()
        self.assertEqual(self.me(self.theirs.key), 401)
        self.assertEqual(self.me(self.laptop.key), 200)
        self.assertEqual(LoginToken.objects.count(), 1)

    def test_같은_로그인의_두_줄을_함께_골라도_된다(self):
        res = self.delete_selected(self.a.key, self.b)

        self.assertEqual(res.status_code, 302)
        self.assert_login_gone_and_not_revived()
        self.assertEqual(LoginToken.objects.count(), 2)

    def test_없는_번호를_지우려_해도_500_이_아니다(self):
        admin = Client(raise_request_exception=False)
        admin.force_login(self.root)
        for pk in ("9" * 30, "abc", "-1"):
            with self.subTest(pk=pk):
                res = admin.post(f"{ADMIN_LIST_URL}{pk}/delete/", {"post": "yes"})
                self.assertIn(res.status_code, (302, 404))
        self.assertEqual(LoginToken.objects.count(), 4)

    def test_상세_화면에서_저장해도_지문이_바뀌지_않는다(self):
        row = self.row(self.laptop.key)
        res = self.admin.post(f"{ADMIN_LIST_URL}{row.pk}/change/", {"_save": "Save"})

        self.assertIn(res.status_code, (200, 302))
        self.assertEqual(self.row(self.laptop.key).pk, row.pk)
        self.assertEqual(self.me(self.laptop.key), 200)

    def test_옛_칸_이름이나_지문으로_거르는_주소는_500_이_아니다(self):
        admin = Client(raise_request_exception=False)
        admin.force_login(self.root)
        for lookup in ("key__startswith", "key", "digest__startswith", "digest"):
            with self.subTest(lookup=lookup):
                res = admin.get(ADMIN_LIST_URL, {lookup: self.row(self.b).digest[:4]})
                self.assertIn(res.status_code, (302, 400))


# ---------------------------------------------------------------------------
# 5. 방어를 빼면 무는가
# ---------------------------------------------------------------------------


class DigestSabotageTest(TestCase):
    """방어를 일부러 빼면 위 테스트가 빨개지는가. 구현 파일은 건드리지 않는다."""

    def failures(self, case: type, name: str) -> int:
        result = run_case(case, name)
        self.assertEqual(result.errors, [])
        return len(result.failures)

    @unittest.skipUnless(connection.vendor == "postgresql", "RawNeverStoredTest 가 Postgres 전용이다")
    def test_지문을_원문_그대로_두면_DB_누출_테스트가_잡는다(self):
        def identity(key):
            return key

        with mock.patch("apps.accounts.models.token_digest", identity), mock.patch(
            "apps.accounts.authentication.token_digest", identity
        ):
            for name in (
                "test_로그인",
                "test_이어_가기와_이어_준_앞_토큰",
                "test_표의_지문과_device_를_토큰으로_내밀면_401_이고_로그인이_안_끊긴다",
            ):
                with self.subTest(name=name):
                    # subTest 마다 하나씩 세므로 1 이상이다.
                    self.assertGreaterEqual(self.failures(RawNeverStoredTest, name), 1)

    def test_관리자가_한_줄만_지우면_되살아남_테스트가_잡는다(self):
        with mock.patch.object(
            accounts_admin.LoginTokenAdmin, "delete_model", lambda self, request, obj: obj.delete()
        ):
            self.assertEqual(
                self.failures(
                    AdminDeleteWholeLoginTest,
                    "test_가장_새_줄을_지우면_남은_앞_토큰이_지운_값을_못_되살린다",
                ),
                1,
            )

    def test_일괄_삭제가_고른_줄만_지우면_테스트가_잡는다(self):
        with mock.patch.object(
            accounts_admin.LoginTokenAdmin,
            "delete_queryset",
            lambda self, request, queryset: queryset.delete(),
        ):
            self.assertEqual(
                self.failures(AdminDeleteWholeLoginTest, "test_일괄_삭제도_고른_줄의_로그인만_통째로_지운다"),
                1,
            )

    def test_비밀_키를_안_섞으면_테스트가_잡는다(self):
        import hashlib

        with mock.patch(
            "apps.accounts.models._next_login_token_key",
            lambda key: hashlib.sha256(("next" + key).encode()).hexdigest()[:40],
        ):
            self.assertEqual(
                self.failures(RenewDigestTest, "test_다음_토큰은_서버_비밀_키에_따라_다르다"), 1
            )

    def test_되살린_원문을_안_채우면_응답_유실_테스트가_잡는다(self):
        with mock.patch.object(LoginToken, "_renewed_as", lambda self, latest: latest):
            self.assertEqual(
                self.failures(
                    RenewDigestTest, "test_응답을_잃고_옛_토큰으로_다시_오면_같은_새_토큰이고_행이_안_는다"
                ),
                1,
            )

    def test_이미_있는_다음_토큰을_안_찾으면_테스트가_잡는다(self):
        """renew 가 다음 토큰이 이미 있는지 보지 않고 바로 만들게 한다.

        renew 안에서 user·device·digest 를 함께 걸러 찾는 곳은 그 확인 하나뿐이라, 그 조회만
        빈 결과로 바꾼다.
        """
        real_filter = LoginToken.objects.filter

        def blind_filter(*args, **kwargs):
            if "digest" in kwargs and "device" in kwargs:
                return LoginToken.objects.none()
            return real_filter(*args, **kwargs)

        names = (
            "test_서버_비밀_키를_바꿨다_되돌려도_이미_있는_다음_토큰을_돌려준다",
            "test_계산이_안_맞는_latest_가_지금보다_뒤에_만들어졌어도_두_번째_이어_가기가_된다",
            "test_배포_전_무작위_토큰이_쓰이고_이어진_뒤_유예_안의_옛_토큰이_와도_이미_있는_다음_토큰이다",
        )
        with mock.patch.object(LoginToken.objects, "filter", side_effect=blind_filter):
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(self.failures(RenewExistingNextTest, name), 1)

    def test_인증이_원문을_안_실으면_이어_가기_테스트가_잡는다(self):
        """인증이 request.auth.key 를 안 채우면 이어 가기가 원문을 계산할 수 없다."""
        from apps.accounts.authentication import SlimTokenAuthentication

        real = SlimTokenAuthentication.authenticate_credentials

        def without_key(self, key):
            user, token = real(self, key)
            token.key = None
            return user, token

        with mock.patch.object(SlimTokenAuthentication, "authenticate_credentials", without_key):
            result = run_case(
                RenewDigestTest, "test_응답을_잃고_옛_토큰으로_다시_오면_같은_새_토큰이고_행이_안_는다"
            )
        self.assertEqual(len(result.failures) + len(result.errors), 1)


@unittest.skipUnless(connection.vendor == "postgresql", "raw SQL 이 Postgres 문법이다")
class MigrationSabotageTest(TransactionTestCase):
    """0016 의 계산을 빼면 변환 테스트가 빨개지는가."""

    def test_0016_이_원문을_그대로_두면_변환_테스트가_잡는다(self):
        with mock.patch.object(MIGRATION_0016, "_digest", lambda value: value):
            result = run_case(
                DigestMigrationTest,
                "test_원문은_지문으로_device_는_부모가_살아_있을_때만_부모_지문으로_바뀐다",
            )
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.failures), 1)

    def test_0016_이_device_를_안_바꾸면_11_13_전_토큰_테스트가_잡는다(self):
        """device 를 그대로 두면 11-13 전 토큰을 알아보지 못해 유예가 지난 그 토큰이 폰까지 끊는다."""
        real = MIGRATION_0016._digest
        seen: set = set()

        def digest_key_only(value):
            # hash_tokens 는 한 행에서 key 를 먼저, device 를 다음에 부른다. 행(pk)마다 두 번째
            # 부름(device)은 그대로 돌려준다.
            pk = sys._getframe(1).f_locals["pk"]
            if pk in seen:
                return value
            seen.add(pk)
            return real(value)

        with mock.patch.object(MIGRATION_0016, "_digest", digest_key_only):
            result = run_case(
                DigestMigrationTest,
                "test_11_13_전_토큰은_유예가_지나_와도_그_요청만_401_이고_이어_받은_토큰은_산다",
            )
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.failures), 1)

