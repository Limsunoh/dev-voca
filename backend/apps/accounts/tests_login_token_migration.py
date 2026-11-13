"""0010 이 옛 DRF 토큰을 기기별 토큰 표로 옮기는가.

옮기지 못하면 배포하는 순간 로그인해 있던 사람이 전부 로그아웃된다. 쿠키에 든
값이 그대로 통해야 한다.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token as DrfToken

from apps.accounts.models import LoginToken

from .email_change import make_token
from .tests import EMAIL_CHANGE_CONFIRM_URL, PASSWORD

User = get_user_model()

BEFORE = [("accounts", "0009_login_token")]
AFTER = [("accounts", "0010_copy_drf_tokens")]


def migrate(targets) -> None:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)


class CopyDrfTokensTest(TransactionTestCase):
    def setUp(self):
        migrate(BEFORE)

    def tearDown(self):
        # 다음 테스트가 마지막 마이그레이션 상태를 기대한다.
        migrate(AFTER)

    def test_keys_owners_and_issue_times_carry_over(self):
        issued = timezone.now() - timedelta(days=90)
        old = {}
        for i in range(2):
            user = User.objects.create_user(email=f"moved{i}@example.com", password=PASSWORD)
            token = DrfToken.objects.create(user=user)
            DrfToken.objects.filter(pk=token.pk).update(created=issued)
            old[token.key] = user.pk

        migrate(AFTER)

        moved = {t.key: t for t in LoginToken.objects.all()}
        self.assertEqual(set(moved), set(old))
        for key, user_pk in old.items():
            self.assertEqual(moved[key].user_id, user_pk)
            self.assertEqual(moved[key].created, issued)
            # 옮긴 값이 실제로 로그인에 통한다.
            res = self.client.get("/api/accounts/me/", HTTP_AUTHORIZATION=f"Token {key}")
            self.assertEqual(res.status_code, 200)

    def test_old_rows_are_left_for_the_old_server_during_deploy(self):
        """배포 중 옛 코드가 계속 그 표를 읽는다(0010 머리말)."""
        user = User.objects.create_user(email="stay@example.com", password=PASSWORD)
        DrfToken.objects.create(user=user)

        migrate(AFTER)

        self.assertEqual(DrfToken.objects.filter(user=user).count(), 1)

    def test_email_link_sent_before_deploy_still_works(self):
        """옛 코드는 하나뿐인 DRF 토큰으로 대조값을 만들었다. 옮긴 뒤에도 맞아야 한다."""
        user = User.objects.create_user(email="before@example.com", password=PASSWORD)
        old_key = DrfToken.objects.create(user=user).key
        link = make_token(
            user_id=user.pk,
            current_email=user.email,
            new_email="after@example.com",
            login_token=old_key,
        )

        migrate(AFTER)

        res = self.client.post(
            EMAIL_CHANGE_CONFIRM_URL, {"token": link}, content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "after@example.com")

    def test_undoing_only_0010_and_reapplying_does_not_fail(self):
        """0010 의 되돌리기는 옮긴 행을 남긴다. 다시 적용할 때 같은 값을 또 넣으면 서버가 안 뜬다."""
        user = User.objects.create_user(email="again@example.com", password=PASSWORD)
        DrfToken.objects.create(user=user)
        migrate(AFTER)
        migrate(BEFORE)

        migrate(AFTER)

        self.assertEqual(LoginToken.objects.filter(user=user).count(), 1)
