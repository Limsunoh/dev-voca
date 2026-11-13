"""검색 부분 글자 인덱스(0014_search_trgm)가 검색 결과를 바꾸지 않는지.

인덱스는 빨라지기만 해야 한다. 그래서 같은 데이터와 같은 검색어를 세 가지로
돌려 결과(순서까지 포함한 id 목록, count)를 맞춰 본다.

    인덱스 없음 - 저장점 안에서 trgm 인덱스 8개를 지우고 돌린 뒤 되돌린다(0013 과 같다)
    전체 훑기   - enable_indexscan/bitmapscan/indexonlyscan = off
    인덱스 강제 - enable_seqscan = off

인덱스 강제 모드가 정말 trgm 인덱스를 탔는지는 같은 SQL 의 EXPLAIN 으로 본다.
안 그러면 세 모드가 모두 전체 훑기라 "같다" 가 아무것도 증명하지 못한다.

검수 안 된 쌍둥이(같은 뜻·표기·설명을 가진 hidden 항목)를 모든 검색어에 걸리게
넣어, 어느 모드에서도 일반 사용자에게 안 나오는지 함께 본다. 검수자에게는
나와야 쌍둥이가 실제로 검색어에 걸린다는 것이 확인된다.

마이그레이션은 0013 으로 내렸다가 다시 올려 인덱스·확장이 지워지고 생기는지,
그리고 Django 가 icontains 로 만드는 식과 인덱스 식이 같아 칸마다 인덱스가
쓰이는지를 본다.

Postgres 전용 시나리오에는 skipUnless 를 붙였다. SQLite 에서는 검수 게이트,
마이그레이션 함수의 DB 종류 분기, makemigrations 가 조용한지만 돈다.
"""

import importlib
import unittest

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .models import Sentence, Word
from .views import SentenceViewSet, WordViewSet

WORDS_URL = "/api/vocab/words/"
SENTENCES_URL = "/api/vocab/sentences/"

# 마이그레이션 모듈의 목록을 가져다 쓰지 않고 손으로 적는다. 가져다 쓰면 그 목록이
# 틀려도 테스트가 같이 틀려서 못 잡는다.
TRGM_COLUMNS = [
    ("vocab_word", "term"),
    ("vocab_word", "meaning"),
    ("vocab_word", "aliases"),
    ("vocab_word", "description"),
    ("vocab_sentence", "text"),
    ("vocab_sentence", "translation"),
    ("vocab_sentence", "context"),
    ("vocab_sentence", "description"),
]
TRGM_NAMES = sorted(f"{table}_{column}_trgm" for table, column in TRGM_COLUMNS)

BEFORE = ("vocab", "0013_word_vocab_word_term_lower_idx")
AFTER = ("vocab", "0014_search_trgm")

PG = connection.vendor == "postgresql"

SEQ_ONLY = {
    "enable_seqscan": "on",
    "enable_indexscan": "off",
    "enable_bitmapscan": "off",
    "enable_indexonlyscan": "off",
}
DEFAULTS = {
    "enable_seqscan": "on",
    "enable_indexscan": "on",
    "enable_bitmapscan": "on",
    "enable_indexonlyscan": "on",
}
# 보통 인덱스 훑기를 열어 두면 표가 작아 기본 키나 is_reviewed 인덱스로 돌아간다.
# LIKE 조건을 받을 수 있는 길이 trgm 비트맵만 남게 비트맵 말고는 다 끈다.
INDEX_ONLY = {
    "enable_seqscan": "off",
    "enable_indexscan": "off",
    "enable_bitmapscan": "on",
    "enable_indexonlyscan": "off",
}

# 검색어. 이름은 실패 메시지에 나온다.
SEARCH_TERMS = [
    ("영어 대소문자 섞임", "sLoWqUeRy"),
    ("영어 대문자", "QUERY"),
    ("영어 1글자", "q"),
    ("영어 2글자", "ab"),
    ("영어 3글자", "abc"),
    ("영어 4글자", "abcd"),
    ("한글 1글자", "쿼"),
    ("한글 2글자", "쿼리"),
    ("한글 3글자", "느린쿼"),
    ("한글 4글자", "데이터베"),
    ("한글 띄어 쓴 두 낱말", "느린 쿼리"),
    ("여러 낱말", "slow query"),
    ("따옴표로 묶은 구", '"slow query"'),
    ("작은따옴표 낀 낱말", "it's"),
    ("짝 안 맞는 따옴표", '"slow'),
    ("큰따옴표 낀 낱말", 'say "hi"'),
    ("퍼센트만", "%"),
    ("퍼센트 낀 말", "100%"),
    ("밑줄만", "_"),
    ("밑줄 낀 말", "snake_case"),
    ("역슬래시만", "\\"),
    ("역슬래시 낀 말", "c:\\path"),
    ("전각 영문", "ＡＢＣ"),
    ("전각 영문 소문자", "ａｂｃ"),
    ("NBSP 낀 말", "non\u00a0breaking"),
    ("결합 문자 e+acute", "cafe\u0301"),
    ("완성형 e-acute", "café"),
    ("독일어 sharp s", "straße"),
    ("독일어 SS", "STRASSE"),
    ("터키어 점 I", "İstanbul"),
    ("그리스어 끝 시그마", "οδος"),
    ("아주 긴 검색어", "slowquery" * 300),
    ("빈 검색어", ""),
    ("공백만", "   "),
    ("쉼표만", ","),
    ("별칭에만 있는 말", "가나다라별칭"),
    ("별칭 두 번째 항목", "커미트"),
    ("설명에만 있는 말", "zebracorn"),
    ("상황에만 있는 말(문장)", "deploypipe"),
    ("해석에만 있는 말(문장)", "해석전용말"),
    ("어디에도 없는 말", "qqqzzzxxx"),
]


def make_word(term: str, meaning: str, reviewed: bool = True, **extra) -> Word:
    fields = {"description": "", "aliases": ""}
    fields.update(extra)
    return Word.objects.create(term=term, meaning=meaning, is_reviewed=reviewed, **fields)


def make_sentence(text: str, translation: str, reviewed: bool = True, **extra) -> Sentence:
    return Sentence.objects.create(text=text, translation=translation, is_reviewed=reviewed, **extra)


# (term, meaning, aliases, description)
WORD_ROWS = [
    ("SlowQuery", "느린 쿼리", "", "slow query 를 찾는 도구"),
    ("slow query log", "느린 쿼리 기록", "슬로 쿼리", ""),
    ("query", "쿼리", "쿼리, 퀘리", "데이터베이스에 묻는 것"),
    ("query plan", "실행 계획", "", "query 를 어떻게 돌릴지"),
    ("commit", "변경 확정", "커밋, 커미트", ""),
    ("a", "한 글자", "", ""),
    ("Ab", "두 글자", "", ""),
    ("abc", "세 글자", "", ""),
    ("ABCD", "네 글자", "", ""),
    ("xabcdx", "가운데 abcd", "", ""),
    ("100% done", "다 끝남", "", "100%"),
    ("100x done", "퍼센트 아님", "", ""),
    ("snake_case", "뱀 표기", "", ""),
    ("snakeXcase", "밑줄 아님", "", ""),
    ("c:\\path\\to", "윈도 경로", "", "역슬래시 \\ 가 든 말"),
    ("it's fine", "괜찮다", "", ""),
    ('say "hi"', "인사하기", "", ""),
    ("ＡＢＣ전각", "전각 글자", "", ""),
    ("non\u00a0breaking space", "줄바꿈 없는 공백", "", ""),
    ("non breaking normal", "보통 공백", "", ""),
    ("cafe\u0301 combining", "결합 문자", "", ""),
    ("café precomposed", "완성형", "", ""),
    ("Straße", "거리", "", ""),
    ("STRASSE", "거리 대문자", "", ""),
    ("İstanbul", "도시", "", ""),
    ("ΟΔΟΣ", "길", "", "οδος"),
    ("database", "데이터베이스", "디비", "데이터를 담는 곳"),
    ("alias only", "무관한 뜻", "가나다라별칭", ""),
    ("description only", "무관한 뜻", "", "zebracorn 은 설명에만"),
    ("slowquery" * 11, "아주 긴 제목", "", ""),
]

# (text, translation, context, description)
SENTENCE_ROWS = [
    ("The slow query took ten seconds.", "느린 쿼리가 10초 걸렸다.", "", ""),
    ("Run the SlowQuery report.", "느린쿼리 보고서를 돌려라.", "", ""),
    ("abc is not abcd", "세 글자와 네 글자", "", ""),
    ("Progress: 100% done", "진행 다 끝남", "", ""),
    ("Use snake_case here.", "여기는 뱀 표기", "", ""),
    ("Path is c:\\path\\to\\file", "윈도 경로", "", ""),
    ("It's fine, say \"hi\".", "괜찮아, 인사해.", "", ""),
    ("ＡＢＣ full width", "전각", "", ""),
    ("non\u00a0breaking here", "줄바꿈 없는 공백", "", ""),
    ("cafe\u0301 and café", "결합과 완성형", "", ""),
    ("Straße STRASSE", "거리", "", ""),
    ("İstanbul ΟΔΟΣ", "도시와 길", "", ""),
    ("Connect to the database.", "데이터베이스에 붙어라.", "DB 접속할 때", ""),
    ("Context only sentence.", "무관한 해석", "deploypipe 가 멈췄을 때", ""),
    ("Translation only sentence.", "해석전용말 이 들어 있다", "", ""),
    ("Description only sentence.", "무관한 해석", "", "zebracorn 설명"),
    ("slowquery" * 300, "아주 긴 문장", "", ""),
]


class TrgmFixtureMixin:
    """단어·문장과 검수 안 된 쌍둥이, 페이지를 넘기게 하는 채움 행."""

    @classmethod
    def setUpTestData(cls):
        cls.hidden_word_ids = set()
        cls.hidden_sentence_ids = set()
        for term, meaning, aliases, description in WORD_ROWS:
            make_word(term, meaning, aliases=aliases, description=description)
            hidden = make_word(
                f"zz hidden {term}"[:100], meaning, reviewed=False,
                aliases=aliases, description=description,
            )
            cls.hidden_word_ids.add(hidden.id)
        for text, translation, context, description in SENTENCE_ROWS:
            make_sentence(text, translation, context=context, description=description)
            hidden = make_sentence(
                f"hidden {text}", translation, reviewed=False,
                context=context, description=description,
            )
            cls.hidden_sentence_ids.add(hidden.id)
        # "query" 가 여러 페이지에 걸치게 설명에만 query 가 든 행을 채운다.
        for n in range(45):
            make_word(f"filler {n:03d}", "채움 단어", description=f"filler about query {n}")
            make_sentence(f"Filler sentence {n:03d}.", "채움 문장", description="query 이야기")
        reviewer = get_user_model().objects.create_user(
            email="trgm-reviewer@example.com", is_staff=True,
        )
        cls.reviewer = reviewer
        # 통계가 없으면 is_reviewed 비트맵이 trgm 보다 싸 보인다. 운영처럼 통계를 채운다.
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("ANALYZE vocab_word")
                cursor.execute("ANALYZE vocab_sentence")

    def snapshot(self, url: str, term: str) -> dict:
        """검색 결과를 페이지 끝까지 모은다. LIKE 가 든 SQL 도 함께 돌려준다."""
        ids, count, page, sqls = [], None, 1, []
        while True:
            with CaptureQueriesContext(connection) as ctx:
                res = self.client.get(url, {"search": term, "page": page})
            self.assertEqual(res.status_code, 200, (url, term, page, res.content[:300]))
            sqls += [q["sql"] for q in ctx.captured_queries if "LIKE" in q["sql"]]
            body = res.json()
            if count is None:
                count = body["count"]
            self.assertEqual(body["count"], count, "페이지마다 count 가 다르다")
            ids += [row["id"] for row in body["results"]]
            if not body["next"]:
                break
            page += 1
        self.assertEqual(len(ids), count, (url, term, "count 와 실제 행 수가 다르다"))
        self.assertEqual(len(ids), len(set(ids)), (url, term, "페이지 사이에 중복 행"))
        return {"ids": ids, "count": count, "sqls": sqls}


def set_planner(settings: dict) -> None:
    with connection.cursor() as cursor:
        for name, value in settings.items():
            cursor.execute(f"SET LOCAL {name} = {value}")


def explain(sql: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN " + sql)
        return "\n".join(row[0] for row in cursor.fetchall())


class _Rollback(Exception):
    pass


def without_trgm_indexes(fn):
    """trgm 인덱스를 지운 상태(0013 과 같은 상태)에서 fn 을 돌리고 되돌린다."""
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                for name in TRGM_NAMES:
                    cursor.execute(f'DROP INDEX IF EXISTS "{name}"')
            result = fn()
            raise _Rollback(result)
    except _Rollback as rolled_back:
        return rolled_back.args[0]


def with_only_trgm_indexes(fn):
    """trgm 인덱스만 탈 수 있게 해 두고 fn 을 돌린 뒤 되돌린다.

    표가 작으면 비트맵만 열어 둬도 is_reviewed 인덱스 비트맵이 더 싸서 trgm 을 안
    탄다. 그래서 저장점 안에서 제약이 아닌 다른 인덱스를 지운다. 기본 키·유일 제약
    인덱스는 남지만 UPPER(칸) LIKE 를 받을 수 없어 비트맵 후보가 못 된다.
    """
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT i.relname FROM pg_index x "
                    "JOIN pg_class i ON i.oid = x.indexrelid "
                    "JOIN pg_class t ON t.oid = x.indrelid "
                    "WHERE t.relname IN ('vocab_word', 'vocab_sentence') "
                    "AND i.relname NOT LIKE %s "
                    "AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = x.indexrelid)",
                    ["%\\_trgm"],
                )
                for (name,) in cursor.fetchall():
                    cursor.execute(f'DROP INDEX "{name}"')
            set_planner(INDEX_ONLY)
            result = fn()
            raise _Rollback(result)
    except _Rollback as rolled_back:
        return rolled_back.args[0]


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class SearchSameWithOrWithoutIndexTests(TrgmFixtureMixin, TestCase):
    """같은 검색어는 인덱스가 있든 없든, 어떤 계획을 고르든 같은 결과를 낸다."""

    def compare_modes(self, url: str, viewer=None) -> None:
        if viewer is not None:
            self.client.force_login(viewer)
        for label, term in SEARCH_TERMS:
            with self.subTest(url=url, case=label):
                set_planner(DEFAULTS)
                baseline = without_trgm_indexes(lambda: self.snapshot(url, term))
                set_planner(SEQ_ONLY)
                seq = self.snapshot(url, term)
                forced = with_only_trgm_indexes(lambda: self.snapshot(url, term))
                self.assertEqual(seq["count"], baseline["count"], "전체 훑기 count 가 인덱스 없을 때와 다르다")
                self.assertEqual(forced["count"], baseline["count"], "인덱스 강제 count 가 인덱스 없을 때와 다르다")
                self.assertEqual(seq["ids"], baseline["ids"], "전체 훑기 결과·순서가 인덱스 없을 때와 다르다")
                self.assertEqual(forced["ids"], baseline["ids"], "인덱스 강제 결과·순서가 인덱스 없을 때와 다르다")

    def test_words_anonymous(self):
        """단어 목록, 비로그인: 세 모드의 결과·순서·count 가 같다."""
        self.compare_modes(WORDS_URL)

    def test_sentences_anonymous(self):
        """문장 목록, 비로그인: 세 모드의 결과·순서·count 가 같다."""
        self.compare_modes(SENTENCES_URL)

    def test_words_reviewer(self):
        """단어 목록, 검수자(검수 대기 앞정렬이 붙는 경로): 세 모드가 같다."""
        self.compare_modes(WORDS_URL, self.reviewer)

    def test_sentences_reviewer(self):
        """문장 목록, 검수자: 세 모드가 같다."""
        self.compare_modes(SENTENCES_URL, self.reviewer)

    def test_forced_mode_really_uses_every_trgm_index(self):
        """인덱스 강제 모드에서 목록 SQL 과 count SQL 이 그 표의 trgm 인덱스 넷을 모두 탄다.

        이게 안 되면 위 비교는 세 번 다 전체 훑기를 비교한 셈이다.
        """
        for url, table in ((WORDS_URL, "vocab_word"), (SENTENCES_URL, "vocab_sentence")):
            expected = [f"{t}_{c}_trgm" for t, c in TRGM_COLUMNS if t == table]
            for term in ("slowq", "데이터베", "slow query"):
                with self.subTest(url=url, term=term):
                    plans = with_only_trgm_indexes(
                        lambda: [explain(sql) for sql in self.snapshot(url, term)["sqls"]]
                    )
                    self.assertGreaterEqual(len(plans), 2, "count 와 목록 SQL 이 모두 잡혀야 한다")
                    for plan in plans:
                        for name in expected:
                            self.assertIn(name, plan, plan)

    def test_seq_mode_uses_no_trgm_index(self):
        """전체 훑기 모드에서는 trgm 인덱스가 계획에 없다(비교 기준이 진짜 전체 훑기인지)."""
        set_planner(SEQ_ONLY)
        snap = self.snapshot(WORDS_URL, "slowq")
        for sql in snap["sqls"]:
            self.assertNotIn("_trgm", explain(sql))

    def test_rank_order_kept_under_forced_index(self):
        """인덱스 강제에서도 제목 일치 > 제목 앞부분 > 제목 포함 > 뜻 포함 > 나머지 순서가 그대로다."""
        ids = with_only_trgm_indexes(lambda: self.snapshot(WORDS_URL, "query")["ids"])
        terms = [Word.objects.get(id=i).term for i in ids]
        # 제목 일치, 제목 앞부분("query plan"), 제목 포함(나머지는 term ABC), 그 뒤 설명만 걸린 채움 행
        self.assertEqual(terms[:2], ["query", "query plan"])
        self.assertEqual(terms[2:5], ["slow query log", "SlowQuery", "slowquery" * 11])
        self.assertTrue(all(t.startswith("filler") for t in terms[5:]), terms)
        # 별칭 두 번째 항목은 제목 일치와 같은 순위
        first = with_only_trgm_indexes(lambda: self.snapshot(WORDS_URL, "커미트")["ids"])[0]
        self.assertEqual(Word.objects.get(id=first).term, "commit")


class SearchReviewGateTests(TrgmFixtureMixin, TestCase):
    """검수 안 된 항목은 어느 검색어로도 일반 사용자에게 안 나온다(모든 DB)."""

    def gate_check(self, forced: bool = False) -> None:
        for label, term in SEARCH_TERMS:
            for url, hidden in ((WORDS_URL, self.hidden_word_ids), (SENTENCES_URL, self.hidden_sentence_ids)):
                with self.subTest(case=label, url=url):
                    if forced:
                        ids = set(with_only_trgm_indexes(lambda: self.snapshot(url, term)["ids"]))
                    else:
                        ids = set(self.snapshot(url, term)["ids"])
                    self.assertFalse(ids & hidden, f"검수 안 된 항목이 새었다: {sorted(ids & hidden)}")

    def test_anonymous_never_sees_unreviewed(self):
        """비로그인: 기본 계획에서 검수 안 된 쌍둥이가 안 나온다."""
        self.gate_check()

    def test_normal_user_never_sees_unreviewed(self):
        """일반 로그인 사용자도 같다."""
        user = get_user_model().objects.create_user(email="trgm-normal@example.com")
        self.client.force_login(user)
        self.gate_check()

    @unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
    def test_anonymous_never_sees_unreviewed_under_forced_index(self):
        """인덱스 강제 계획에서도 검수 필터가 빠지지 않는다."""
        self.gate_check(forced=True)

    def test_twins_really_match(self):
        """쌍둥이가 실제로 검색어에 걸린다(검수자에게는 보인다) - 위 검사가 헛돌지 않는다."""
        self.client.force_login(self.reviewer)
        for term in ("쿼리", "slow", "가나다라별칭", "zebracorn", "100%", "snake_case", "\\"):
            ids = set(self.snapshot(WORDS_URL, term)["ids"])
            self.assertTrue(ids & self.hidden_word_ids, term)
        for term in ("deploypipe", "해석전용말", "zebracorn", "ＡＢＣ"):
            ids = set(self.snapshot(SENTENCES_URL, term)["ids"])
            self.assertTrue(ids & self.hidden_sentence_ids, term)


@unittest.skipUnless(connection.vendor == "postgresql", "Postgres 전용")
class TrgmMigrationTests(TestCase):
    """0013 으로 내렸다 0014 로 올리기. TestCase 의 트랜잭션이 끝나면 DDL 도 되돌아간다."""

    def trgm_indexes(self) -> dict:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexname LIKE %s",
                ["%\\_trgm"],
            )
            return dict(cursor.fetchall())

    def has_extension(self) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            return cursor.fetchone() is not None

    def migrate_to(self, target) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([target])

    def assert_installed(self) -> None:
        indexes = self.trgm_indexes()
        self.assertEqual(sorted(indexes), TRGM_NAMES)
        self.assertTrue(self.has_extension())
        for table, column in TRGM_COLUMNS:
            definition = indexes[f"{table}_{column}_trgm"].lower()
            self.assertIn(f"on public.{table} using gin (upper(", definition)
            self.assertIn(column, definition)
            self.assertIn("gin_trgm_ops", definition)

    def test_down_then_up(self):
        """적용된 상태 -> 0013(인덱스·확장 없음) -> 0014(8개) -> 다시 0013 -> 0014."""
        self.assert_installed()
        for _ in range(2):
            self.migrate_to(BEFORE)
            self.assertEqual(self.trgm_indexes(), {})
            self.assertFalse(self.has_extension())
            self.migrate_to(AFTER)
            self.assert_installed()

    def test_every_column_index_matches_django_icontains(self):
        """칸마다 Django 가 icontains 로 만든 SQL 이 그 칸의 인덱스를 쓴다(식이 같다)."""
        models = {"vocab_word": Word, "vocab_sentence": Sentence}
        for table, column in TRGM_COLUMNS:
            with self.subTest(column=f"{table}.{column}"):
                qs = models[table].objects.filter(**{f"{column}__icontains": "abcd"})
                sql, params = qs.query.get_compiler(using="default").as_sql()
                set_planner(INDEX_ONLY)
                with connection.cursor() as cursor:
                    cursor.execute("EXPLAIN " + sql, params)
                    plan = "\n".join(row[0] for row in cursor.fetchall())
                self.assertIn(f"{table}_{column}_trgm", plan, plan)


class _FakeEditor:
    def __init__(self, vendor: str):
        self.connection = type("C", (), {"vendor": vendor})()
        self.sql: list[str] = []

    def execute(self, sql, params=()):
        self.sql.append(sql)


class TrgmMigrationVendorBranchTests(TestCase):
    """마이그레이션 함수가 DB 종류에 따라 갈리는지(모든 DB에서 돈다)."""

    def setUp(self):
        self.module = importlib.import_module("apps.vocab.migrations.0014_search_trgm")

    def test_sqlite_does_nothing(self):
        """SQLite 면 올리기·내리기 모두 SQL 을 하나도 내지 않는다."""
        for fn in (self.module.create, self.module.drop):
            editor = _FakeEditor("sqlite")
            fn(None, editor)
            self.assertEqual(editor.sql, [])

    def test_postgres_sql_shape(self):
        """Postgres 면 확장 하나와 인덱스 8개를 만들고, 내리면 8개와 확장을 지운다."""
        editor = _FakeEditor("postgresql")
        self.module.create(None, editor)
        self.assertEqual(editor.sql[0], "CREATE EXTENSION IF NOT EXISTS pg_trgm")
        self.assertEqual(len(editor.sql), 9)
        for (table, column), sql in zip(TRGM_COLUMNS, editor.sql[1:]):
            self.assertEqual(
                sql,
                f'CREATE INDEX "{table}_{column}_trgm" ON "{table}" '
                f'USING gin (UPPER("{column}") gin_trgm_ops)',
            )
        editor = _FakeEditor("postgresql")
        self.module.drop(None, editor)
        self.assertEqual(len(editor.sql), 9)
        self.assertEqual(editor.sql[-1], "DROP EXTENSION IF EXISTS pg_trgm")

    def test_makemigrations_is_quiet(self):
        """모델 상태는 이 인덱스를 몰라 makemigrations 가 새 마이그레이션을 만들지 않는다."""
        call_command("makemigrations", "vocab", "--check", "--dry-run", verbosity=0)

    def test_index_list_matches_view_search_fields(self):
        """인덱스를 만든 칸이 지금 views 의 search_fields 와 같다."""
        self.assertEqual(
            [c for t, c in TRGM_COLUMNS if t == "vocab_word"], WordViewSet.search_fields
        )
        self.assertEqual(
            [c for t, c in TRGM_COLUMNS if t == "vocab_sentence"], SentenceViewSet.search_fields
        )
