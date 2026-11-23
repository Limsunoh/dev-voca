"""이미 있는 로그인 토큰의 device 를 그 토큰 값으로 채운다.

이메일 변경 링크의 대조값이 토큰 값에서 device 로 바뀌었다(views._link_device). 배포 전에
보낸 링크는 토큰 값으로 만들어졌으니, 옛 토큰의 device 를 토큰 값과 같게 두어야 그
링크가 계속 맞는다. 0012 가 넣은 무작위 값을 덮는다.

되돌리기는 아무것도 안 한다. 배포 직후(이어 가기가 돌기 전)에는 다시 적용해도 결과가
같다. 이어 가기가 한 번이라도 돈 뒤에 이것만 되돌렸다 다시 적용하면, 이어 받은 토큰마다
device 가 자기 토큰 값으로 덮여 같은 로그인이 갈라진다(대기 중인 이메일 변경 링크가 죽고,
로그아웃이 직전 토큰을 못 지운다). 그때는 다시 적용하지 않는다. unique 에 걸려 migrate 가
멈추는 일(0010 의 WHERE NOT EXISTS 가 막은 것)은 없다.
"""

from django.db import migrations
from django.db.models import F


def device_from_key(apps, schema_editor) -> None:
    LoginToken = apps.get_model("accounts", "LoginToken")
    LoginToken.objects.update(device=F("key"))


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_login_token_device"),
    ]

    operations = [
        migrations.RunPython(device_from_key, migrations.RunPython.noop),
    ]
