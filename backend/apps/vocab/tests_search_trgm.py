"""검색용 부분 글자 인덱스(migrations/0014_search_trgm)가 실제로 쓰이는가.

인덱스는 모델이 아니라 마이그레이션의 SQL 로 만든다(그 머리말 참고). 그래서
Django 가 대신 지켜 주지 않는 것을 여기서 본다.

  - 검색 칸(search_fields)마다 인덱스가 있다. 칸을 더하고 인덱스를 잊으면
    그 칸 때문에 다시 모든 행을 훑는다.
  - Django 가 icontains 로 만드는 SQL 에 DB 가 이 인덱스를 쓴다. 인덱스 식이
    다르면(LOWER, 다른 칸, 다른 연산자 클래스) 에러 없이 안 쓰인다.
  - 두 글자 검색어도 결과는 맞다(인덱스를 못 쓸 뿐이다).

기대하는 인덱스 이름은 0014 의 목록이 아니라 views 의 search_fields 에서
만든다. 그리고 0014 의 목록이 만든 때 그대로인지 따로 못 박는다
(test_0014_is_frozen). 검색 칸을 더한 사람이 새 마이그레이션 대신 이미 운영에
들어간 0014 를 고쳐 테스트를 통과시키는 길을 막으려는 것이다. 테스트 DB 는
매번 처음부터 만들어 그 차이를 못 보지만, 운영에는 인덱스가 영영 안 생긴다.
"""

import importlib
import unittest

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .models import Sentence, Word
from .views import LearningItemViewSet

migration_0014 = importlib.import_module("apps.vocab.migrations.0014_search_trgm")
# 이름 짓는 규칙만 빌린다. 기대값을 0014 의 목록에서 만들지 않는다(머리말 참고).
index_name = migration_0014.index_name


def _all_subclasses(cls) -> list[type]:
    found = []
    for sub in cls.__subclasses__():
        found += [sub, *_all_subclasses(sub)]
    return found


def _expected_indexes() -> dict[str, list[str]]:
    """표마다 있어야 할 인덱스 이름. 검색 칸을 가진 콘텐츠 화면 전부(손자 클래스 포함)."""
    expected: dict[str, list[str]] = {}
    for view in _all_subclasses(LearningItemViewSet):
        table = view.model._meta.db_table
        names = expected.setdefault(table, [])
        names += [index_name(table, f) for f in view.search_fields if index_name(table, f) not in names]
    return expected


def _existing_indexes() -> dict[str, str]:
    """이름 -> 정의(CREATE INDEX ...)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema()"
        )
        return dict(cursor.fetchall())


class MigrationFrozenTest(TestCase):
    def test_0014_is_frozen(self):
        """0014 는 운영에 들어갔다. 검색 칸을 바꾸면 이걸 고치지 말고 새 마이그레이션을 만든다."""
        self.assertEqual(
            migration_0014.SEARCH_COLUMNS,
            [
                ("vocab_word", "term"),
                ("vocab_word", "meaning"),
                ("vocab_word", "aliases"),
                ("vocab_word", "description"),
                ("vocab_sentence", "text"),
                ("vocab_sentence", "translation"),
                ("vocab_sentence", "context"),
                ("vocab_sentence", "description"),
            ],
        )


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class SearchIndexTest(TestCase):
    def test_every_search_field_has_a_trigram_index(self):
        existing = _existing_indexes()
        expected = _expected_indexes()
        self.assertEqual(set(expected), {"vocab_word", "vocab_sentence"})
        for names in expected.values():
            for name in names:
                self.assertIn(name, existing, f"{name} 인덱스가 없다")
                self.assertIn("gin_trgm_ops", existing[name], name)

    def _fill(self, model, rows):
        """행을 넣고 운영과 같은 상태로 만든다.

        행이 몇 개뿐이면 DB 가 전체 훑기나 검수 여부 인덱스를 더 싸게 본다.
        그래서 수천 개를 넣는다. 또 테스트 DB 는 빈 표에 인덱스를 먼저 만들고
        행을 나중에 넣어서, 새 행이 GIN 인덱스의 대기 목록(pending list)에
        쌓여 DB 가 이 인덱스를 비싸게 보고 안 쓴다. 운영은 이미 있는 행으로
        인덱스를 만들었으니 대기 목록을 비워(gin_clean_pending_list) 맞춘다.
        """
        model.objects.bulk_create(rows, batch_size=1000)
        table = model._meta.db_table
        with connection.cursor() as cursor:
            for name in _expected_indexes()[table]:
                cursor.execute("SELECT gin_clean_pending_list(%s::regclass)", [name])
            cursor.execute(f"ANALYZE {table}")

    def _count_plan(self, path: str) -> str:
        """목록 API 의 개수 세기 쿼리를 seq scan 을 끈 채 EXPLAIN 한다."""
        with CaptureQueriesContext(connection) as ctx:
            response = APIClient().get(path)
        self.assertEqual(response.status_code, 200)
        count_sql = next((q["sql"] for q in ctx.captured_queries if "COUNT(" in q["sql"]), None)
        self.assertIsNotNone(count_sql, "목록 API 가 개수 세기 쿼리를 안 보냈다")
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
            cursor.execute("EXPLAIN " + count_sql)
            return "\n".join(row[0] for row in cursor.fetchall())

    def _assert_all_indexes_used(self, plan: str, table: str):
        """검색은 칸 넷을 OR 로 묶는다. DB 가 OR 을 인덱스로 풀려면 갈래마다
        맞는 인덱스가 있어야 해서(BitmapOr), 넷 다 계획에 나와야 한다."""
        for name in _expected_indexes()[table]:
            self.assertIn(name, plan)

    def test_word_search_uses_the_indexes(self):
        self._fill(
            Word,
            [
                Word(
                    term=f"filler term {i:05d}",
                    meaning=f"채우는 말 {i}",
                    description=f"검색에 안 걸리는 설명 {i}",
                    category="git",
                    is_reviewed=True,
                )
                for i in range(3000)
            ],
        )
        Word.objects.create(
            term="rollback",
            meaning="되돌리기",
            description="배포를 앞 버전으로 되돌린다.",
            category="git",
            is_reviewed=True,
        )
        plan = self._count_plan("/api/vocab/words/?search=rollback")
        self._assert_all_indexes_used(plan, "vocab_word")

    def test_sentence_search_uses_the_indexes(self):
        self._fill(
            Sentence,
            [
                Sentence(
                    text=f"Filler sentence number {i:05d} goes here.",
                    translation=f"채우는 문장 {i}",
                    context="회의할 때",
                    description=f"설명 {i}",
                    category="git",
                    is_reviewed=True,
                )
                for i in range(3000)
            ],
        )
        Sentence.objects.create(
            text="Please rebase before merging.",
            translation="머지하기 전에 리베이스해 주세요.",
            context="코드 리뷰에서",
            description="설명",
            category="git",
            is_reviewed=True,
        )
        plan = self._count_plan("/api/vocab/sentences/?search=rebase")
        self._assert_all_indexes_used(plan, "vocab_sentence")


class SearchResultTest(TestCase):
    def test_short_and_korean_search_still_finds_rows(self):
        """세 글자 미만은 인덱스를 못 쓰지만 결과는 그대로여야 한다."""
        Word.objects.create(
            term="query",
            meaning="쿼리",
            description="DB 에 묻는 말.",
            category="database",
            is_reviewed=True,
        )
        for term in ["쿼리", "qu", "QUERY", "uer"]:
            response = APIClient().get("/api/vocab/words/", {"search": term})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                [row["term"] for row in response.json()["results"]], ["query"], term
            )
