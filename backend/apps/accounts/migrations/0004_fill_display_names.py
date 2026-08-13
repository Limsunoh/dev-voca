"""보여지는 이름을 채우고, 줄이고, 겹치는 것을 떼어놓는다.

다음 마이그레이션(0005)이 컬럼을 12자로 줄이고 "대소문자 구분 없이 유일"
제약을 건다. 그 전에 지금 있는 행들을 그 규칙에 맞춰둬야 한다. 안 그러면
배포가 거기서 멈추고 컨테이너가 아예 뜨지 않는다.

**순서가 이 파일의 존재 이유다.** 처음에는 길이 축소가 0003 에 들어가
데이터를 자르기 전에 컬럼이 좁아졌다. PostgreSQL 은 그 자리에서
"value too long for type character varying(12)" 로 멈춘다. SQLite 는
max_length 를 강제하지 않아 로컬 테스트가 이걸 못 잡는다 - 이 저장소는
같은 함정을 serializers.py 에도 적어두고 있다.

정리할 것이 셋이다.

- 빈 이름: 예전에는 비어 있으면 화면에서 이메일 앞부분을 대신 보여줬다.
  이제는 순위표에 이름이 뜨므로 메일 주소가 새면 안 된다. 학습자1234 꼴로
  지어 넣는다.
- 긴 이름: 길이 제한이 줄었다. 앞에서 잘라 맞춘다.
- 겹치는 이름: 대소문자만 다른 것도 겹치는 것으로 본다. 먼저 만들어진
  계정이 원래 이름을 갖고, 나중 것에 번호를 붙인다. 가입 순서를 기준으로
  삼는 이유는 그게 유일하게 다툼 없는 기준이라서다.

길이 상수를 models 에서 가져오지 않고 여기 적어둔다. 마이그레이션은
과거의 한 시점을 재현하는 코드라, 지금 모델을 참조하면 나중에 상수가
바뀔 때 이 파일의 동작이 조용히 달라진다.
"""

from __future__ import annotations

import secrets
import unicodedata

from django.db import migrations

PREFIX = "학습자"
MAX_LENGTH = 12
HIDDEN_CATEGORIES = ("Cf", "Cc")


def _clean(value: str) -> str:
    """models.normalize_display_name 과 같은 규칙.

    모델에서 가져오지 않고 복사한다. 마이그레이션은 과거의 한 시점을
    재현하는 코드라, 지금 모델을 참조하면 나중에 규칙이 바뀔 때 이 파일의
    동작이 조용히 달라진다.

    **다만 복사한 이상 같아야 한다.** 여기만 서식 문자 제거와 NFC 를
    빼두면, 마이그레이션은 두 이름을 다르다고 보고 넘어가지만 그 사용자가
    나중에 아무거나 저장하는 순간 save() 가 같은 이름으로 만들어 충돌한다.
    본인은 이름을 건드리지도 않았는데 저장이 거절된다.
    """
    stripped = "".join(
        c for c in value if unicodedata.category(c) not in HIDDEN_CATEGORIES
    )
    return unicodedata.normalize("NFC", " ".join(stripped.split()))


def _taken_key(name: str) -> str:
    # DB 제약이 Lower() 를 쓴다. casefold 는 그보다 넓게 접어서, 여기서
    # 다르다고 본 둘을 DB 가 같다고 막는 경우가 생기지 않는다.
    return name.lower()


def fill_and_dedupe(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    taken: set[str] = set()
    changed = []

    # 가입 순서. date_joined 를 쓰면 같은 시각이 여럿일 때 순서가 흔들린다.
    for user in User.objects.order_by("pk").iterator():
        original = user.display_name or ""
        # 다듬고 자른 뒤 한 번 더 다듬는다. 비교만 하고 저장을 안 하면
        # "  임 선오  " 가 그대로 남아, 나중에 "임 선오" 가 따로 만들어져도
        # 제약이 통과한다. 화면에서는 둘이 똑같이 보인다.
        # 자르는 위치가 공백일 수 있어 두 번 태운다.
        name = _clean(_clean(original)[:MAX_LENGTH])

        if not name or _taken_key(name) in taken:
            name = _pick_free_name(name, taken)

        if name != original:
            user.display_name = name
            changed.append(user)

        taken.add(_taken_key(name))

    if changed:
        # batch_size 를 준다. 없으면 행이 많을 때 거대한 UPDATE 하나가
        # 나가서 DB 가 오래 잠긴다.
        User.objects.bulk_update(changed, ["display_name"], batch_size=500)


def _pick_free_name(base: str, taken: set[str]) -> str:
    """비어 있는 이름을 찾는다.

    이름이 있었으면 뒤에 번호를 붙여 원래 이름을 알아볼 수 있게 하고,
    아예 없었으면 새로 지어준다.
    """
    if base:
        for suffix in range(2, 1000):
            # 길이를 넘기면 저장이 안 된다. 붙일 자리를 비워둔다.
            candidate = _clean(
                _clean(f"{base[: MAX_LENGTH - len(str(suffix))]}{suffix}")[:MAX_LENGTH]
            )
            if candidate and _taken_key(candidate) not in taken:
                return candidate

    # PREFIX(3) + 4자리 = 7자. 제한 안에 들어간다.
    for _ in range(50):
        candidate = f"{PREFIX}{secrets.randbelow(9000) + 1000}"
        if _taken_key(candidate) not in taken:
            return candidate

    # 여기까지 왔다면 4자리가 좁아진 것이다. 자릿수를 늘린다(3 + 7 = 10자).
    while True:
        candidate = f"{PREFIX}{secrets.randbelow(9_000_000) + 1_000_000}"
        if _taken_key(candidate) not in taken:
            return candidate


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_user_avatar_user_google_picture_and_more"),
    ]

    operations = [
        # 되돌릴 때는 아무것도 하지 않는다. 지어준 이름을 도로 비우면
        # 그 계정은 화면에 보여줄 이름이 없어진다.
        migrations.RunPython(fill_and_dedupe, migrations.RunPython.noop),
    ]
