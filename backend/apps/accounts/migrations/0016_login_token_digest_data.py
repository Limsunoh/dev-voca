"""이미 있는 로그인 토큰을 원문 대신 지문(sha256)으로 바꾼다.

토큰 원문이 DB 에 있으면 DB 나 백업 파일을 본 사람이 그 값으로 바로 로그인한다. 있던 토큰도
같은 계산으로 바꾸므로, 쿠키에 든 원문으로 인증하면 그대로 맞는다. 로그인한 사람은
로그아웃되지 않는다.

11-13 전 토큰은 device 에도 토큰 원문이 들어 있다(0013). 그 토큰을 이어 받은 토큰도 같은
device 를 물려받았다. device 가 아직 표에 있는 토큰의 원문이면 같이 지문으로 바꾼다.
- 그 토큰 자신의 지문과 같아지므로, 인증이 "11-13 전 토큰" 을 가르는 조건(device 가 자기
  지문과 같은가)이 그대로 맞는다.
- 이어 받은 토큰도 같은 값으로 바뀌어 한 로그인의 device 가 갈라지지 않는다.
- 원래 토큰이 이미 지워졌으면 device 를 그대로 둔다. 죽은 토큰의 원문이라 로그인에 못 쓴다.
- device 가 바뀐 기기에서 배포 전 24시간 안에 신청한 이메일 변경 링크는 대조값이 달라져
  거절된다. 다시 신청하면 된다.

계산은 apps.accounts.models.token_digest 와 같아야 한다. 마이그레이션은 그 함수가 나중에
바뀌어도 지금 계산으로 돌아야 해서 따로 적는다.

이미 지문인 행(64자)은 건드리지 않는다. 두 번 바꾸면 그 토큰이 죽는다.

되돌리면 토큰을 모두 지운다. 지문에서 원문을 되살릴 수 없고, 0015 를 되돌려 칸을 40자로
줄이려면 64자 값이 없어야 한다. 모두 다시 로그인한다.
"""

import hashlib

from django.db import migrations

RAW_LENGTH = 40


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_tokens(apps, schema_editor) -> None:
    LoginToken = apps.get_model("accounts", "LoginToken")
    rows = list(LoginToken.objects.values_list("pk", "digest", "device"))
    raw_keys = {key for _, key, _ in rows if len(key) == RAW_LENGTH}
    for pk, key, device in rows:
        if len(key) != RAW_LENGTH:
            continue
        LoginToken.objects.filter(pk=pk).update(
            digest=_digest(key),
            device=_digest(device) if device in raw_keys else device,
        )


def drop_tokens(apps, schema_editor) -> None:
    apps.get_model("accounts", "LoginToken").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_login_token_digest_length"),
    ]

    operations = [
        migrations.RunPython(hash_tokens, drop_tokens),
    ]
