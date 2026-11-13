"""검색이 쓸 부분 글자 인덱스(pg_trgm).

검색(views 의 SearchFilter)은 칸마다 UPPER(칸) LIKE UPPER('%말%') 로 묻는다.
보통 인덱스로는 가운데 글자를 못 찾아 모든 행을 훑는다. 2026-11-13 운영
규모(단어 3,503, 문장 5,366)에서 단어 검색 22~28ms, 문장 검색 33ms 였다.
pg_trgm 의 GIN 인덱스는 글을 세 글자씩 쪼갠 조각으로 찾아, 세 글자 이상이면서
걸리는 행이 적은 검색어를 7~10ms 로 줄인다. 두 글자 검색어("쿼리", "db")와
대부분의 행에 들어 있는 낱말("error")에는 DB 가 그대로 전체 훑기를 고른다.
한글도 세 글자 조각으로 잘린다(운영 DB 의 LC_CTYPE 이 en_US.utf8, 11-13 확인).

모델(Meta.indexes)에 적지 않고 여기서 SQL 로 만든다. GIN 과 gin_trgm_ops 는
Postgres 전용이라 모델에 적으면 SQLite 로 돌리는 모드(USE_SQLITE)의 migrate
가 깨진다. 그래서 확장 설치와 인덱스를 Postgres 일 때만 만들고, Django 의
모델 상태는 이 인덱스를 모른다(makemigrations 가 지우려 들지 않는다).
Django 의 TrigramExtension 을 쓰지 않는 이유도 같다. 되돌릴 때 DB 종류를 안
보고 pg_extension 을 조회해 SQLite 에서 실패한다.

인덱스 식은 Django 가 icontains 로 만드는 UPPER("칸"::text) 와 같아야 쓰인다.
varchar 칸은 UPPER 에 들어갈 때 text 로 바뀌므로 UPPER("칸") 으로 만들면 같은
식이 된다.

표가 작아(수천 행) 쓰기를 잠깐 막는 보통 CREATE INDEX 로 만든다. 1초도 안
걸린다. CONCURRENTLY 는 마이그레이션의 트랜잭션 안에서 쓸 수 없다. 같은 이름의
인덱스가 이미 있으면 식이 달라도 넘어가지 않도록 IF NOT EXISTS 를 붙이지
않는다. 실패하면 트랜잭션째 되돌아가 0013 상태로 남는다.

되돌리면 인덱스와 확장을 지운다. 이 마이그레이션 전에 다른 이유로 확장을
설치해 두었어도 지운다(Django 의 CreateExtension 과 같다). 이 마이그레이션 밖에서
pg_trgm 에 기대는 것이 있으면 CASCADE 를 안 붙여서 되돌리기가 실패한다. 남의
것을 조용히 지우는 것보다 낫다.

운영 DB(Postgres 18.6)의 접속 계정은 superuser 라 확장을 설치할 수 있다
(11-13 읽기로 확인, 그때 pg_trgm 은 설치돼 있지 않았다).
"""

from django.db import migrations

# (표, 칸). 이 마이그레이션이 만든 때(2026-11-13)의 WordViewSet.search_fields,
# SentenceViewSet.search_fields 다.
#
# 운영에 적용된 뒤에는 이 목록을 고치지 않는다. 고쳐도 운영은 이 마이그레이션을
# 다시 돌리지 않아 인덱스가 생기지 않는다. 검색 칸을 바꾸면 새 마이그레이션을
# 만들고 이름은 같은 규칙(index_name)으로 짓는다. tests_search_trgm 이 views 의
# search_fields 에서 이름을 만들어 DB 에 있는지 본다.
SEARCH_COLUMNS = [
    ("vocab_word", "term"),
    ("vocab_word", "meaning"),
    ("vocab_word", "aliases"),
    ("vocab_word", "description"),
    ("vocab_sentence", "text"),
    ("vocab_sentence", "translation"),
    ("vocab_sentence", "context"),
    ("vocab_sentence", "description"),
]


def index_name(table: str, column: str) -> str:
    return f"{table}_{column}_trgm"


def create(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, column in SEARCH_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX "{index_name(table, column)}" '
            f'ON "{table}" USING gin (UPPER("{column}") gin_trgm_ops)'
        )


def drop(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, column in SEARCH_COLUMNS:
        schema_editor.execute(f'DROP INDEX IF EXISTS "{index_name(table, column)}"')
    schema_editor.execute("DROP EXTENSION IF EXISTS pg_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("vocab", "0013_word_vocab_word_term_lower_idx"),
    ]

    operations = [
        migrations.RunPython(create, drop),
    ]
