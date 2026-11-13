"""지금 쓰이는 DRF 토큰을 기기별 토큰 표(LoginToken)로 옮긴다.

옮기지 않으면 배포하는 순간 로그인해 있던 사람이 모두 로그아웃된다. 쿠키에
든 토큰 값을 새 인증이 못 찾아 401 이 나고, Next 가 그 쿠키를 지운다.
값과 발급 시각을 그대로 옮기므로 쿠키는 손대지 않아도 된다.

ORM(apps.get_model("authtoken", "Token"))이 아니라 SQL 로 옮기는 이유:
그러려면 authtoken 마이그레이션에 dependency 를 걸어야 하는데, 나중에
rest_framework.authtoken 을 INSTALLED_APPS 에서 빼면 그 dependency 때문에
마이그레이션 그래프가 깨진다. 표가 없으면(새로 만든 DB 에서 authtoken 이 아직
안 돌았거나 앱을 뺀 뒤) 옮길 것도 없으니 건너뛴다.

옛 표의 행은 지우지 않는다. Railway 는 새 배포의 migrate 가 도는 동안 옛
코드가 요청을 계속 받는다(DEPLOY.md "배포 확인"). 여기서 지우면 그 사이 옛
코드가 받은 요청이 전부 401 이 되어 그 사람들이 로그아웃된다.

반대로, migrate 가 끝난 뒤 옛 코드가 받은 로그인은 옛 표에만 남는다(처음 로그인한
사람이거나 마침 이 사이에 로그아웃했다 들어온 사람). 그 사람은 새 코드로 넘어가면
한 번 로그아웃된다. 같은 사이 옛 코드가 받은 로그아웃·비밀번호 변경은 옛 표에서만
토큰을 지워서, 옮겨 온 토큰은 새 코드에서 그대로 통한다. 옛 코드가 받은 탈퇴는
자기가 모르는 이 표의 행이 외래 키에 걸려 500 이 된다(새 배포로 넘어간 뒤 다시 하면 된다).
새 배포가 뜨는 몇 초 사이의 일이라 막지 않았다.
"""

from __future__ import annotations

from django.db import migrations


def copy_drf_tokens(apps, schema_editor) -> None:
    connection = schema_editor.connection
    if "authtoken_token" not in connection.introspection.table_names():
        return

    # 이미 옮긴 값은 건너뛴다. 0010 만 되돌렸다가(되돌리기는 아무것도 안 지운다)
    # 다시 적용하면 같은 값이 또 들어가 unique 에 걸리고, migrate 가 실패해 서버가
    # 안 뜬다. 시각은 DB 안에서 그대로 옮겨 시간대 변환을 거치지 않는다.
    schema_editor.execute(
        'INSERT INTO accounts_logintoken ("key", user_id, created) '
        'SELECT t."key", t.user_id, t.created FROM authtoken_token t '
        "WHERE NOT EXISTS ("
        'SELECT 1 FROM accounts_logintoken l WHERE l."key" = t."key")'
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_login_token"),
    ]

    operations = [
        # 되돌리기는 옮긴 행을 남긴다. 0009 까지 되돌리면 표째 사라지고, 0010 만
        # 되돌렸다 다시 적용하면 위 NOT EXISTS 가 겹치는 값을 건너뛴다.
        migrations.RunPython(copy_drf_tokens, migrations.RunPython.noop),
    ]
