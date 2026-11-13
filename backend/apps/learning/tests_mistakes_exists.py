"""오답 노트가 "보여줄 수 있는 대상" 을 EXISTS 로 거르는가.

`views_history._visible_targets` 가 `IN (SELECT id ...)` 둘을 OR 로 묶던
때는, 단어·문장이 수십만 개가 되면 Postgres 가 틀린 항목마다 id 목록을
처음부터 훑어 오답 노트가 11초를 넘었다(2026-11-13 측정). EXISTS 로 바꾼
모양을 누가 IN 으로 되돌리지 않게 SQL 모양을 지킨다.

거르는 결과(검수 안 된 것·지워진 것이 빠지고, 종류와 id 가 짝지어지고,
개수가 맞는다)는 tests_mistakes.py 가 본다.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .tests_mistakes import make_user, make_word, mark

URL = "/api/learning/mistakes/"


class MistakesVisibilityQueryTest(TestCase):
    def test_visibility_is_checked_with_exists_not_in(self):
        user = make_user("exists")
        self.client.force_login(user)
        mark(user, make_word(), wrong=True)

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)

        count_sql = next(
            (q["sql"] for q in ctx.captured_queries if "learning_reviewstate" in q["sql"] and "COUNT" in q["sql"]),
            None,
        )
        self.assertIsNotNone(count_sql, "오답 노트가 개수 세기 쿼리를 안 보냈다")
        self.assertIn("EXISTS", count_sql)
        self.assertNotIn('"target_id" IN (SELECT', count_sql)
