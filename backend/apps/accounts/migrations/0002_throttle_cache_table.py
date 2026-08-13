"""요청 제한이 쓰는 캐시 테이블을 만든다.

DatabaseCache 는 테이블이 있어야 동작하는데, 그 테이블은 모델이 아니라서
평범한 마이그레이션으로는 생기지 않는다. 원래는 배포할 때
`createcachetable` 을 따로 한 번 돌려주게 돼 있다.

그 한 줄을 잊으면 조용히 넘어가지 않는다 - 로그인·가입 요청이 통째로
500 이 된다. 로그인·가입·구글은 누구나 부를 수 있는 뷰라 권한 검사에서
걸리지 않고, 요청 제한이 곧바로 캐시를 친다. 즉 요청의 첫 DB 접근이 이
테이블이다. 실제로 그렇게 났었다(2026-08-13): `createcachetable` 은
Procfile 의 `release:` 줄에만 적혀 있었는데 그 줄이 실행된 흔적이 없고
테이블도 없었다. 배포는 대시보드에 따로 저장된 시작 명령으로 돌고 있었다.
저장소 밖에 있는 절차는 빠져도 아무 신호가 없다는 것이 요점이다.

테스트가 대신 봐주지 않는다. Django 테스트 러너는 테스트 DB 를 만들 때
캐시 테이블을 알아서 만들어주므로, 배포 절차에서 빠져 있어도 로컬은 늘
통과한다. `ThrottleCacheTableTest` 가 "테이블이 없으면 무엇이 죽는지"
까지는 고정하지만, 프로덕션에 실제로 적용됐는지는 배포 후 확인으로만 안다.

그래서 마이그레이션으로 옮긴다. `migrate` 를 부르는 배포라면 테이블이
따라오므로, 배포 절차에 한 줄을 더 적어 넣을 필요가 없어진다.
`migrate` 자체를 안 부르는 배포에서는 여전히 깨진다 - 그 값도 저장소
밖(대시보드)에 있으니 DEPLOY.md 의 `## 시작 명령` 을 함께 본다.
"""

from django.core.management import call_command
from django.db import migrations


def create_cache_table(_apps, schema_editor):
    """settings 의 CACHES 를 보고 필요한 테이블을 만든다.

    테이블 이름을 여기 적지 않는 이유는 지금 두 곳에 같은 문자열을 두지
    않기 위해서다. 다만 **앞으로도 자동으로 따라간다는 뜻은 아니다.**
    RunPython 은 처음 적용될 때 한 번만 돈다. 나중에 CACHES 의 LOCATION 을
    바꾸면 이 마이그레이션은 다시 돌지 않으므로 기존 환경에는 새 테이블이
    생기지 않는다 - 새로 만드는 환경만 새 이름으로 생겨서, 로컬과 CI 는
    초록인데 프로덕션만 500 이 나는 이번과 똑같은 모양이 된다.
    LOCATION 을 바꿀 때는 마이그레이션을 새로 하나 추가한다.

    이미 있으면 아무 일도 하지 않으므로 여러 번 돌아도 괜찮다.
    """
    call_command(
        "createcachetable",
        database=schema_editor.connection.alias,
        verbosity=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # 되돌릴 때는 아무것도 하지 않는다. 캐시 테이블에는 요청 제한
        # 기록만 들어 있어 지울 이유가 없고, 지우면 되돌린 직후 다시
        # 500 이 난다.
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
