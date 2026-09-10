"""사용자 계정.

로그인 키를 username 이 아니라 email 로 둔다. 구글 로그인이 주는 것이
이메일이라, username 을 키로 쓰면 "구글에서 온 사람의 username 을 무엇으로
만들 것인가" 라는 문제가 생긴다 - 이메일 앞부분을 잘라 쓰면 서로 다른
도메인의 같은 아이디가 부딪히고, 뒤에 숫자를 붙이면 그 숫자가 영영 남는다.

이메일 하나를 키로 두면 이메일 가입과 구글 로그인이 같은 계정으로 모인다.
같은 사람이 두 방법을 번갈아 써도 계정이 갈라지지 않는다.
"""

from __future__ import annotations

import io
import re
import secrets
import unicodedata

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

# 화면에 그릴 수 있는 아바타. 실제 그림은 프론트가 SVG 로 들고 있고,
# 여기서는 어느 것을 골랐는지만 저장한다. 이미지 파일을 서버에 두지
# 않는 이유: 배포할 때마다 컨테이너 디스크가 초기화돼 사라진다.
AVATAR_PRESETS = ("a1", "a2", "a3", "a4", "a5", "a6")

# 구글 계정 사진을 쓰겠다는 표시.
AVATAR_GOOGLE = "google"

# 직접 올린 사진을 쓰겠다는 표시. 사진 자체는 avatar_photo 컬럼에 있다.
#
# "무엇을 보여줄지" 를 여기 한 칸에 모아두는 이유: 순위표는 사용자를
# 행마다 조회하지 않고 .values("user__avatar", ...) 로 필요한 칸만 긁어
# 간다(apps/learning/leaderboards.py). 사진 유무를 별도 컬럼으로 두면
# 그 목록에 그 칸을 더해야 하고, 안 더하면 순위표에서만 사진이 조용히
# 안 뜬다 - 화면은 멀쩡해 보여서 한참 뒤에야 드러난다.
AVATAR_PHOTO = "photo"

AVATAR_CHOICES = [
    (AVATAR_PHOTO, "올린 사진"),
    (AVATAR_GOOGLE, "구글 사진"),
] + [(key, f"아바타 {key[1:]}") for key in AVATAR_PRESETS]

# 올린 사진을 줄여서 저장할 한 변의 길이. 화면에서 가장 큰 자리가
# 프로필의 72px 이라 256 이면 3배수까지 선명하다.
#
# 원본을 그대로 넣지 않는 이유: 요즘 폰 사진 한 장이 5MB 다. 그대로
# 넣으면 사용자 행 하나가 그만큼 커지고, User 를 읽는 모든 질의가
# 그 무게를 진다.
AVATAR_PHOTO_SIZE = 256

# 받아줄 업로드 파일의 최대 크기. 상한이 없으면 큰 파일 하나로 메모리를
# 밀어버릴 수 있다 - Pillow 로 열기 전에, 바이트를 세는 것만으로 막는다.
#
# 5MB 인 이유: 요즘 폰 사진 한 장이 대개 2~5MB 다. 더 낮추면 평범한
# 사진이 거절돼 사용자가 이유를 모른 채 막힌다.
AVATAR_PHOTO_MAX_BYTES = 5 * 1024 * 1024

# 펼쳤을 때의 픽셀 수 상한. 바이트 상한과 따로 있어야 하는 이유는 아래
# shrink_avatar_photo 에 적어뒀다 - 잘 압축되는 큰 그림이 바이트 검사를
# 지나간다.
#
# 5천만으로 둔다. 요즘 폰이 5천만 화소 안쪽이라 평범한 사진은 다 통과하고,
# 그 위는 프로필 사진으로 쓸 이유가 없다.
AVATAR_PHOTO_MAX_PIXELS = 50_000_000

# 자동으로 지어주는 이름의 앞부분. 뒤에 네 자리를 붙여 일곱 글자가 된다.
GENERATED_NAME_PREFIX = "학습자"

# 보여지는 이름의 최대 길이.
#
# 짧게 두는 이유: 순위표는 이름을 한 줄에 여러 개 늘어놓는 화면이다.
# 길면 줄바꿈이 나거나 잘려서, 화면이 이름 길이에 휘둘린다. 좁은 폰에서
# 특히 그렇다.
DISPLAY_NAME_MAX = 12

# 이름에서 서식 문자와 제어 문자를 지운다. 폭 없는 공백처럼 눈에 안 보이는
# 문자를 끼워 넣으면 화면에는 똑같이 보이는데 DB 에서는 다른 문자열이 되고,
# 그대로 두면 순위표에 남의 이름 행세를 하는 행이 생긴다.
#
# 문자를 직접 적지 않고 분류로 거른다. Cf 는 서식, Cc 는 제어 문자다.
# 소스에 그 문자를 그대로 쓰면 편집기에서 안 보여서, 다음 사람이 손대다가
# 조용히 망가뜨린다.
_HIDDEN_CATEGORIES = ("Cf", "Cc")


def _strip_hidden(value: str) -> str:
    return "".join(
        c for c in value if unicodedata.category(c) not in _HIDDEN_CATEGORIES
    )


_SPACES = re.compile(r"\s+")


def normalize_display_name(value: str | None) -> str:
    """보여지는 이름을 비교 가능한 형태로 다듬는다.

    같은 이름으로 보이는데 DB 에서는 다른 문자열인 경우를 없앤다.
    순위표에 남의 이름 행세를 하는 행이 끼는 것을 막는 것이 목적이다.

    NFC 로 모으는 이유: 한글은 "한" 을 완성형 한 글자로도, 자모 셋으로도
    쓸 수 있다. 화면에서는 똑같이 보이는데 문자열로는 다르다. 모으지
    않으면 조합형으로 남의 이름과 같은 줄을 만들 수 있고, 자모가 글자마다
    세 개라 길이도 세 배로 세어져 멀쩡한 이름이 길이 제한에 걸린다.
    """
    cleaned = _SPACES.sub(" ", _strip_hidden(value or "")).strip()
    return unicodedata.normalize("NFC", cleaned)


def shorten_display_name(value: str | None) -> str:
    """다듬고 길이에 맞춘다. 저장 전에 거치는 마지막 관문.

    자른 뒤에 한 번 더 다듬는 이유: 자르는 위치가 공백일 수 있다.
    "abcdefghijk zzz" 를 12자로 자르면 "abcdefghijk " 가 되는데, 그대로
    두면 중복 검사는 통과하고 저장 직전 save() 가 공백을 없애면서 기존
    이름과 부딪힌다. 검사한 값과 저장하는 값이 달라지는 자리다.
    """
    return normalize_display_name(normalize_display_name(value)[:DISPLAY_NAME_MAX])


def name_taken(name: str, exclude_pk: int | None = None) -> bool:
    """이미 쓰고 있는 이름인지 본다.

    DB 제약과 **같은 함수**로 비교한다. 제약은 Lower(display_name) 인데
    파이썬 쪽만 __iexact 를 쓰면 PostgreSQL 에서 갈린다 - iexact 는
    UPPER 로 번역되고, 유니코드에서 upper 와 lower 는 서로의 역이 아니다.
    예를 들어 켈빈 기호는 lower 하면 k 가 되지만 upper 하면 그대로다.
    그러면 파이썬은 "빈 이름" 이라 하고 DB 는 중복이라며 거절해, 사용자는
    이유를 알 수 없는 오류를 받는다.

    이 판정이 필요한 곳이 여럿이라(가입·프로필 수정·구글 로그인·이름
    자동 생성) 한 곳에 둔다. 흩어두면 한 곳만 고쳐지고 나머지는 남는다.
    """
    from django.apps import apps as django_apps

    User = django_apps.get_model("accounts", "User")
    found = User.objects.annotate(_folded=Lower("display_name")).filter(
        _folded=name.lower()
    )
    if exclude_pk is not None:
        found = found.exclude(pk=exclude_pk)
    return found.exists()


def free_display_name(wanted: str | None) -> str:
    """쓰려는 이름이 비어 있지 않으면서 이미 있으면 뒤에 번호를 붙인다.

    구글 로그인이 쓴다. 구글이 준 이름이 이미 있는 이름이라고 해서 가입이
    막히면 안 된다 - 동명이인은 흔하고, 사용자는 자기가 뭘 잘못했는지
    알 수 없다.

    빈 문자열을 돌려줄 수 있다. 그 경우 User.save() 가 학습자1234 꼴로
    지어 넣는다.
    """
    name = shorten_display_name(wanted)
    if not name:
        return ""

    if not name_taken(name):
        return name

    for suffix in range(2, 1000):
        # 길이를 넘기면 저장이 안 된다. 붙일 자리를 비워둔다.
        # 자른 자리가 공백일 수 있어 shorten 을 한 번 더 태운다.
        candidate = shorten_display_name(
            f"{name[: DISPLAY_NAME_MAX - len(str(suffix))]}{suffix}"
        )
        if candidate and not name_taken(candidate):
            return candidate

    # 같은 이름이 천 명이면 지어주는 쪽으로 넘긴다.
    return ""


class AvatarPhotoError(ValueError):
    """올린 파일을 사진으로 못 쓸 때. 뷰가 안내 문구로 바꾼다."""


def shrink_avatar_photo(raw: bytes) -> bytes:
    """올린 사진을 줄여서 WebP 바이트로 바꾼다.

    **확장자와 Content-Type 을 믿지 않는다.** 둘 다 올리는 쪽이 적어
    보내는 값이라, 아무 파일이나 .jpg 로 이름 붙여 보낼 수 있다. Pillow 로
    실제로 열어봐야 사진인지 알 수 있다.

    WebP 로 통일하는 이유:

    - 투명한 PNG 를 JPEG 로 바꾸면 투명한 부분이 **검게** 나온다. 배경을
      흰색으로 깔아 피할 수도 있지만, 크림 바탕(--paper) 위에 흰 네모가
      떠서 그것대로 눈에 띈다. WebP 는 투명도를 그대로 들고 간다.
    - 형식을 원본에 따라 바꾸면(투명하면 PNG, 아니면 JPEG) 내려줄 때
      Content-Type 도 갈라진다. 저장한 형식을 어딘가 또 적어둬야 하고,
      그 칸과 실제 바이트가 어긋나면 그림이 안 뜬다. 한 형식이면 그럴
      자리가 없다.
    - 같은 화질에서 JPEG 보다 작다. DB 에 넣는 바이트라 크기가 곧 비용이다.

    호환성은 문제되지 않는다. WebP 는 2020년부터 모든 주요 브라우저가
    읽는다. 이 앱은 폰 브라우저와 최신 데스크톱을 본다.
    """
    # Pillow 를 함수 안에서 가져온다. 모델 모듈은 마이그레이션과
    # manage.py 가 언제나 읽는데, 사진을 안 만지는 그 경로까지
    # 이미지 라이브러리를 로드할 이유가 없다.
    from PIL import Image, UnidentifiedImageError

    if len(raw) > AVATAR_PHOTO_MAX_BYTES:
        mb = AVATAR_PHOTO_MAX_BYTES // (1024 * 1024)
        raise AvatarPhotoError(f"사진은 {mb}MB 까지 올릴 수 있습니다.")

    if not raw:
        raise AvatarPhotoError("사진 파일이 비어 있습니다.")

    # verify() 를 따로 부르지 않는다. 아래 fit() 이 실제로 픽셀을 읽으므로
    # "머리말만 멀쩡하고 내용이 잘린" 파일은 거기서 OSError 로 걸린다.
    # verify() 를 넣으면 그 뒤 이미지를 못 써서(Pillow 가 그렇게 정했다)
    # 같은 파일을 두 번 열어야 하는데, 얻는 것 없이 일만 두 배가 된다.
    try:
        with Image.open(io.BytesIO(raw)) as image:
            # **픽셀 수를 여기서 본다.** 위의 바이트 상한으로는 못 막는
            # 공격이 있다 - 같은 색으로 채운 큰 그림은 압축이 아주 잘 돼서,
            # 12000x12000(1.4억 픽셀)짜리가 440KB 밖에 안 된다. 5MB 검사를
            # 지나간 뒤 아래에서 실제로 펼치는 순간 0.5GB 를 쓴다.
            #
            # Pillow 에도 같은 방어가 있지만 믿을 수 없다. 기본 한계
            # (8948만)를 넘으면 경고만 내고 그냥 통과시키고, 예외로 막는
            # 것은 그 두 배를 넘을 때다. 즉 1배와 2배 사이가 뚫려 있다.
            #
            # Image.open 은 머리말만 읽으므로 이 시점에는 아직 안 펼쳤다.
            # 여기서 끊어야 메모리를 안 쓴다.
            if image.width * image.height > AVATAR_PHOTO_MAX_PIXELS:
                raise AvatarPhotoError("사진이 너무 큽니다. 다른 사진을 골라주세요.")

            # 폰 사진은 세로로 찍어도 가로 그림 + "돌려서 보라" 는 표시로
            # 저장되는 경우가 많다(EXIF Orientation). 그대로 줄이면 표시가
            # 사라져서 옆으로 누운 사진이 된다.
            from PIL import ImageOps

            image = ImageOps.exif_transpose(image) or image

            # 정사각형으로 자른다. 화면이 아바타를 정사각으로 그리는데
            # (Avatar.tsx 의 object-cover), 원본 비율 그대로 저장하면
            # 브라우저가 자르는 자리와 서버가 아는 크기가 달라진다.
            # 여기서 잘라두면 내려가는 바이트도 그만큼 줄어든다.
            image = ImageOps.fit(
                image,
                (AVATAR_PHOTO_SIZE, AVATAR_PHOTO_SIZE),
                method=Image.Resampling.LANCZOS,
            )

            # 팔레트나 흑백 이미지가 그대로 WebP 로 안 가는 경우가 있다.
            # 투명도를 살린 채 RGBA 로 맞춘다.
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            out = io.BytesIO()
            # quality 82 는 사진에서 눈에 띄는 열화 없이 크기가 확 준다.
            # 256px 짜리라 대개 10~20KB 로 떨어진다.
            image.save(out, format="WEBP", quality=82, method=4)
            return out.getvalue()
    except AvatarPhotoError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        # Pillow 가 스스로 폭탄이라 판단하는 경우(기본 한계의 두 배 초과).
        # Exception 직속이라 위의 셋에 안 걸린다 - 빼면 위의 픽셀 검사에
        # 닿기도 전에 터져서 400 이 아니라 500 이 나간다.
        Image.DecompressionBombError,
    ) as exc:
        # 사진이 아닌 파일, 깨진 파일, Pillow 가 거부하는 형식이 전부
        # 여기로 온다. 원인을 나눠 알려줄 것이 없다 - 사용자가 할 수
        # 있는 일은 어느 쪽이든 "다른 사진을 고른다" 하나다.
        raise AvatarPhotoError("사진 파일을 읽을 수 없습니다.") from exc


class UserManager(BaseUserManager):
    """이메일로 계정을 만드는 매니저.

    기본 UserManager 는 username 을 필수로 받는다. 로그인 키를 바꿨으므로
    생성 경로도 함께 바꿔야 createsuperuser 와 테스트가 동작한다.
    """

    use_in_migrations = True

    def get_by_natural_key(self, email: str):
        """로그인할 때 계정을 찾는 경로.

        기본 구현은 정확히 일치하는 이메일만 찾는다. 저장할 때는 소문자로
        내리므로 보통은 맞아떨어지지만, 옛 데이터나 다른 경로로 대문자가
        섞여 들어간 행이 하나라도 있으면 그 계정은 영영 로그인할 수 없다.
        읽기와 쓰기가 같은 규칙을 보도록 여기서 맞춘다.
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": email})

    def _create_user(self, email: str, password: str | None, **extra) -> User:
        if not email:
            raise ValueError("이메일은 필수입니다.")

        # 통째로 소문자로 내린다. normalize_email 은 도메인만 낮추는데,
        # 그러면 Foo@x.com 으로 가입한 사람이 foo@x.com 으로 로그인할 때
        # 실패한다 - 로그인은 정확히 일치하는 이메일을 찾기 때문이다.
        # 본인 계정에 못 들어가면서 이유도 알 수 없는 상태가 된다.
        #
        # 규격상 @ 앞은 대소문자를 구분할 수 있지만 실제로 그렇게 쓰는
        # 메일 서버는 사실상 없다. 구글 로그인이 주는 이메일과도 여기서
        # 맞춰져야 계정이 갈라지지 않는다.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        # 여기서 막지 않으면 is_staff=False 인 "슈퍼유저" 가 만들어져
        # Admin 에 로그인하지 못하는 상태가 된다.
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("슈퍼유저는 is_staff 와 is_superuser 가 True 여야 합니다.")

        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """이메일로 로그인하는 사용자.

    AbstractUser 를 상속해 권한·그룹·is_staff 같은 Django 기본 기능을 그대로
    쓴다. 검수 권한 판정(apps.vocab.views.can_review)이 is_staff 와
    is_active 를 보므로 그 구조를 유지해야 한다.
    """

    # username 을 없애지 않고 비운다. Django 내부와 서드파티가 이 필드를
    # 참조하는 곳이 있어, 지우면 예상 못 한 곳에서 터진다.
    username = None

    email = models.EmailField("이메일", unique=True)

    # 화면과 순위표에 보여줄 이름. 비워두면 save() 가 지어 넣으므로
    # 실제로 빈 값이 저장되는 일은 없다. blank=True 는 "입력을 비워도
    # 된다" 는 뜻이고, 유일성은 아래 Meta.constraints 가 본다.
    display_name = models.CharField(
        "보여지는 이름", max_length=DISPLAY_NAME_MAX, blank=True
    )

    # 구글이 준 계정 사진 주소. 로그인할 때마다 갱신한다 - 구글에서 사진을
    # 바꾸면 옛 주소가 죽기 때문이다. 오래 안 들어오면 깨질 수 있어서,
    # 화면은 그림이 안 뜰 때 기본 아바타로 떨어지게 그린다.
    google_picture = models.URLField("구글 사진 주소", max_length=500, blank=True)

    # 무엇을 보여줄지 고른 값. 비어 있으면 자동으로 정한다
    # (구글 사진이 있으면 그것, 없으면 계정마다 고정된 아바타 하나).
    avatar = models.CharField(
        "아바타", max_length=10, blank=True, choices=AVATAR_CHOICES
    )

    # 직접 올린 사진. 줄여서 WebP 로 바꾼 바이트가 통째로 들어간다.
    #
    # 파일이 아니라 DB 에 두는 이유: 배포할 때마다 컨테이너 디스크가
    # 초기화된다. 실제로 Railway 볼륨이 지워져 데이터가 날아간 적이 있다.
    # 외부 스토리지를 붙이면 그건 그것대로 계정·요금·장애 지점이 하나 는다.
    #
    # 줄인 뒤라 한 장이 대개 10~20KB 다. 그래서 행이 무거워지는 걱정보다
    # **읽히는 자리** 가 문제인데, 그건 avatar_photo 를 어느 질의에도
    # 안 실어서 푼다 - UserSerializer 는 이 칸을 내보내지 않고, 사진은
    # 별도 엔드포인트(PhotoView)가 이 칸만 골라 읽는다.
    avatar_photo = models.BinaryField("올린 사진", null=True, blank=True, editable=False)

    # 사진 주소에 쓰는 값. 사진을 올릴 때마다 새로 만든다.
    #
    # **pk 를 주소로 쓰지 않는 이유**: pk 는 연번이라 1번부터 눌러보면
    # 사진 올린 계정을 전부 훑을 수 있다. 순위표도 이름과 그림을 같이
    # 보여주지만 그쪽은 상위 몇 줄이고 페이지를 넘겨야 한다 - 같은 정보라도
    # 전원을 한 번에 긁는 것과는 비용이 다르고, 얼굴 사진은 그 차이가
    # 중요한 종류다.
    #
    # **바꿀 때마다 새로 만드는 이유**: 값을 고정하면 옛 주소를 아는 사람이
    # 바뀐 사진도 계속 본다. 새 값이면 옛 주소는 그 자리에서 404 가 된다.
    # 캐시가 깨지는 것은 덤이다 - 주소 자체가 달라지므로 ?v= 같은 꼬리표를
    # 따로 붙일 필요가 없다.
    #
    # 사진이 없으면 None 이다. unique 를 걸지 않는 이유: 사진 없는 행이
    # 여럿이면 NULL 이 여러 개가 되는데, 그 처리가 DB 엔진마다 다르다.
    # 충돌 확률이 사실상 0 인 값이라 제약으로 지킬 것이 없다.
    avatar_photo_key = models.UUIDField(
        "사진 주소 값",
        null=True,
        blank=True,
        editable=False,
        # 사진을 내려주는 자리가 이 칸으로 행을 찾는다. 인덱스가 없으면
        # 그림 요청마다 표를 통째로 훑는데, 순위표 한 화면이 스무 장을
        # 동시에 부르므로 그게 한 화면에 스무 번이다.
        #
        # unique 는 안 건다. 사진 없는 계정이 대부분이라 이 칸이 거의 다
        # NULL 이고, NULL 중복을 엔진마다 다르게 다룬다. 인덱스는 그것과
        # 무관하게 찾는 비용만 줄인다.
        db_index=True,
    )

    # 사진을 마지막으로 바꾼 시각. ETag 로 쓴다 - 같은 그림을 다시
    # 내려받지 않게 한다.
    #
    # 캐시 깨기는 이 값이 아니라 위의 avatar_photo_key 가 한다. 주소가
    # 통째로 바뀌기 때문이다.
    #
    # 사진을 지우면 None 으로 되돌린다.
    avatar_photo_at = models.DateTimeField("사진 올린 시각", null=True, blank=True)

    # 가입일은 AbstractUser 의 date_joined 를 그대로 쓴다. 따로 만들면
    # 컬럼이 둘이 되고, Admin 은 이쪽을 Django 기본 기능은 저쪽을 보게 된다.

    USERNAME_FIELD = "email"
    # createsuperuser 가 추가로 물어볼 항목. 이메일은 USERNAME_FIELD 라
    # 자동으로 묻고, 여기 또 넣으면 두 번 묻는다.
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "사용자"
        verbose_name_plural = "사용자"
        constraints = [
            # 대소문자를 구분하지 않고 막는다. "임선오" 와 "IMSUNOH" 가
            # 따로 존재할 수 있으면 순위표에서 누가 누구인지 구분이 안 된다.
            # 이메일과 같은 방식이다.
            models.UniqueConstraint(
                Lower("display_name"),
                name="accounts_user_display_name_ci_unique",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        """이메일과 보여지는 이름을 저장 직전에 정리한다.

        매니저가 아니라 여기서 하는 이유: Admin 의 계정 추가 폼은
        create_user 를 거치지 않고 곧바로 save() 를 부른다. 매니저에만
        두면 그 경로로 정리되지 않은 값이 들어온다.

        이름을 여기서 지어 넣으므로, 어느 경로로 만들어도 빈 이름이
        저장되지 않는다. 예전에는 비어 있으면 화면에서 이메일 앞부분을
        대신 보여줬는데, 그러면 순위표에 남의 메일 주소 절반이 뜬다.
        """
        # 통째로 소문자로 내리는 이유는 매니저 쪽 주석에 적어뒀다.
        self.email = self.email.lower()

        self.display_name = shorten_display_name(self.display_name)
        if not self.display_name:
            self.display_name = self._generate_display_name()

        super().save(*args, **kwargs)

    def _generate_display_name(self) -> str:
        """비어 있을 때 지어주는 이름. 학습자1234 꼴.

        이미 쓰는 이름을 피해서 뽑는다. 그래도 부딪히면(뽑는 사이 다른
        요청이 같은 번호로 먼저 들어오면) DB 의 유일성 제약이 막고,
        가입 경로가 그 오류를 안내 문구로 바꾼다.
        """
        for _ in range(20):
            candidate = f"{GENERATED_NAME_PREFIX}{secrets.randbelow(9000) + 1000}"
            if not name_taken(candidate, exclude_pk=self.pk):
                return candidate

        # 스무 번을 내리 부딪혔다면 4자리가 좁아진 것이다. 자릿수를 늘려
        # 계속 쓸 수 있게 한다 - 여기서 포기하면 가입이 막힌다.
        return f"{GENERATED_NAME_PREFIX}{secrets.randbelow(9_000_000) + 1_000_000}"

    def __str__(self) -> str:
        return self.email

    @property
    def name_for_display(self) -> str:
        """화면에 쓸 이름.

        save() 가 항상 채우므로 보통은 display_name 그대로다. 뒤의 값은
        마이그레이션 전에 만들어진 행처럼 비어 있는 경우를 위한 것이다.
        이메일을 쓰지 않는 이유: 화면에 메일 주소 앞부분이 노출된다.
        """
        return self.display_name or GENERATED_NAME_PREFIX

    @property
    def has_avatar_photo(self) -> bool:
        """올린 사진이 있나.

        avatar_photo 를 읽지 않고 주소 값만 본다. 바이트를 안 건드려야
        순위표처럼 사용자 스무 명을 훑는 자리에서 그림 스무 장을
        같이 끌고 오지 않는다.
        """
        return self.avatar_photo_key is not None

    @property
    def avatar_photo_url(self) -> str:
        """올린 사진을 내려주는 주소.

        바이트를 JSON 에 싣지 않고 주소만 내려주는 이유: /api/accounts/me/
        는 화면을 그릴 때마다 불린다(머리말이 이름과 그림을 그린다).
        base64 로 싣으면 그 응답이 매번 수십 KB 가 되고, 캐시도 못 한다 -
        JSON 안에 들어간 그림은 브라우저 이미지 캐시를 못 탄다.

        주소가 pk 가 아니라 avatar_photo_key 인 이유는 그 필드 주석에 있다.
        꼬리표(?v=)를 안 붙이는 것도 거기 적었다 - 사진을 바꾸면 이 값이
        새로 만들어져 주소가 통째로 달라진다.
        """
        return f"/api/accounts/photo/{self.avatar_photo_key}/"

    @property
    def avatar_display(self) -> dict[str, str]:
        """화면이 그릴 것.

        {"type": "photo", "url": ...} 이거나 {"type": "preset", "key": "a3"}.
        고른 값이 없으면 여기서 정한다 - 올린 사진이 있으면 그것, 다음이
        구글 사진, 없으면 계정마다 고정된 아바타 하나. 고정이라 새로고침할
        때마다 그림이 바뀌지 않는다.

        올린 사진을 구글 사진보다 앞에 두는 이유: 직접 올린 쪽이 나중에
        한 행동이고, 더 뚜렷한 의사표시다.

        **순위표는 이 property 를 가짜 User 로 부른다**
        (apps/learning/leaderboards.py 의 _row). .values() 로 긁은 칸만
        채워 넣으므로, 여기서 보는 필드가 늘면 그쪽 목록에도 더해야 한다.
        안 더하면 순위표 줄에서만 다른 그림이 뜬다 - 화면이 비지 않아서
        한참 뒤에야 드러난다. 지금은 avatar_photo_key 가 그 목록에 있다.
        """
        if self.avatar == AVATAR_PHOTO and self.has_avatar_photo:
            return {"type": "photo", "url": self.avatar_photo_url}

        if self.avatar in AVATAR_PRESETS:
            return {"type": "preset", "key": self.avatar}

        # 아무것도 안 고른 상태. 올린 사진이 있으면 그것이 기본이다.
        # (avatar == AVATAR_PHOTO 인 경우는 위에서 이미 잡았다.)
        if self.avatar == "" and self.has_avatar_photo:
            return {"type": "photo", "url": self.avatar_photo_url}

        if self.google_picture and self.avatar in ("", AVATAR_GOOGLE):
            return {"type": "photo", "url": self.google_picture}

        # 구글 사진이나 올린 사진을 고른 채로 그것이 없어진 경우도 여기로 온다.
        return {"type": "preset", "key": AVATAR_PRESETS[(self.pk or 0) % len(AVATAR_PRESETS)]}
