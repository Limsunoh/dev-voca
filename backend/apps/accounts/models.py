"""사용자 계정.

로그인 키를 username 이 아니라 email 로 둔다. 구글 로그인이 주는 것이
이메일이라, username 을 키로 쓰면 "구글에서 온 사람의 username 을 무엇으로
만들 것인가" 라는 문제가 생긴다. 이메일 앞부분을 잘라 쓰면 서로 다른
도메인의 같은 아이디가 부딪히고, 뒤에 숫자를 붙이면 그 숫자가 계속 남는다.

이메일 하나를 키로 두면 이메일 가입과 구글 로그인이 같은 계정으로 모인다.
같은 사람이 두 방법을 번갈아 써도 계정이 갈라지지 않는다.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
import unicodedata
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models, transaction
from django.db.models.functions import Cast, Lower, Random
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.learning.models import StudyLength

from .forbidden_names import name_is_forbidden

# 지금 약관·처리방침의 버전. 동의할 때 이 값을 함께 남긴다. 문서 내용이나 가입
# 체크박스 문구, 보관 국가가 바뀌면 올린다. 그래야 누가 어느 버전에 동의했는지
# 나중에 가릴 수 있다.
#
# v2: 순위표 공개·해외 보관 동의를 체크박스로 따로 받기 시작했다.
# v3: 처리방침에 서버 오류 기록의 오류 메시지를 더했다(2026-11-19 시행). 약관은 그대로다.
#     v3 을 공고한 날(11-12) 낮에 "이메일 로그인·가입 시도를 IP 주소 해시로도 센다" 를 v3 에 더했다.
#     그 배포 전에 v3 으로 동의한 사람은 IP 문구가 없는 v3 을 봤다(terms_agreed_at 로
#     가린다). 둘 다 시행 전이고 IP 세기는 동의가 아니라 부정 이용 방지가 근거라 v4 로
#     나누지 않았다.
# v4: 처리방침에 로그인 토큰을 발급 30일 뒤 지운다고 적었다(2026-11-20 시행). v3 시행(11-19)
#     전에 공고했지만 v3 에 합치지 않았다. 11-12 부터 v3 으로 동의한 사람은 만료 문구가
#     없는 v3 을 봤다. 약관은 그대로다.
# v5: 처리방침에 오류 알림 서비스 Sentry(미국)와 이메일 로그인 시도의 1시간 단위 세기를
#     적었다(2026-11-21 공고, 11-28 시행). Sentry 는 11-20 부터 보내고 있었고 14절에 그
#     날짜를 적었다. 가입 체크박스의 국외 이전 문구는 업체 이름 없이 "미국·싱가포르 등" 이라
#     그대로다. v5 전에 가입한 회원에게 다시 동의를 받지 않고, 처리방침 7절과 홈 알림으로
#     알린다(앱 출시 전, 사용자 결정 11-21).
#     같은 날(11-21) 운영자가 DB 를 매일 백업해 14일 보관한다는 내용을 v5 에 더했다(백업을
#     공고일부터 시작한 것은 사용자 결정 11-21). 그 배포 전에 v5 로 동의한 사람은 백업
#     문구가 없는 v5 를 봤다. terms_agreed_at 가 이 문장이 main 에 들어간 머지 시각(git log)
#     보다 이른 v5 동의가 그들이다. v6 으로 나누지 않은 근거: 시행(11-28) 전이고, 맡기는
#     업체(Railway)와 보관 국가(싱가포르)가 그대로라 가입 체크박스 문구가 바뀌지 않는다.
# v6: 로그인하지 않은 사람의 문제풀기·순위표·소리내어 읽기 요청도 접속 IP 해시로 센다고
#     적었다(2026-11-25 공고, 12-02 시행, 세기는 공고일부터). v5 시행(11-28) 전이지만 v5 에
#     합치지 않고 v6 으로 나눴다(사용자 결정 11-24). v5 의 바뀐 내용은 11-28 시행 그대로다.
#     약관과 가입 체크박스 문구는 그대로다.
TERMS_VERSION = "v6"

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
# 그 목록에 그 칸을 더해야 하고, 안 더하면 순위표에서만 사진이 안 뜨는데
# 화면은 멀쩡해 보여서 한참 뒤에야 드러난다.
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
# 밀어버릴 수 있다. Pillow 로 열기 전에 바이트를 세는 것만으로 막는다.
#
# 5MB 인 이유: 요즘 폰 사진 한 장이 대개 2~5MB 다. 더 낮추면 평범한
# 사진이 거절돼 사용자가 이유를 모른 채 막힌다.
AVATAR_PHOTO_MAX_BYTES = 5 * 1024 * 1024

# 펼쳤을 때의 픽셀 수 상한. 바이트 상한과 따로 있어야 하는 이유는 아래
# shrink_avatar_photo 참고. 잘 압축되는 큰 그림이 바이트 검사를 지나간다.
#
# 모든 형식에 5천만을 먼저 건다. 요즘 폰이 5천만 화소 안쪽이라 평범한 사진은 다
# 통과하고, 그 위는 프로필 사진으로 쓸 이유가 없다. 한 번에 풀리는 보통 JPEG 는
# 줄여서 펼치므로(draft) 상한에 가까운 사진도 메모리를 몇 MB 만 쓴다.
AVATAR_PHOTO_MAX_PIXELS = 50_000_000

# 줄여서 펼치지 못하는 그림의 상한. 무엇이 여기 걸리는지는 shrink_avatar_photo 의
# 크기 검사 주석에 있다. 투명도가 있으면 줄일 때 Pillow 가 원래 크기로 한 벌 더
# 만들고, WebP 는 여는 순간 캔버스를 따로 잡는다.
# 같은 7000x7000 을 줄이는 동안 PNG 는 600MB, WebP 는 800MB 를 썼다(WebP 는 그중
# 400MB 가 여는 데 든다). 작업자 하나가 요청 4개를 함께 받으므로 몇 장이면 서버
# 메모리가 찬다.
#
# 1,600만(4000x4000)이면 폰 화면 갈무리(500만 안쪽)와 1,200만 화소 사진은
# 지나가고, 상한 끝의 그림이 PNG 는 130MB, WebP 는 260MB 남짓을 쓴다.
AVATAR_PHOTO_MAX_PIXELS_UNSCALED = 16_000_000
AVATAR_PHOTO_FORMATS = ("JPEG", "PNG", "WEBP")

# 자동으로 지어주는 이름의 앞부분. 뒤에 네 자리를 붙여 일곱 글자가 된다.
GENERATED_NAME_PREFIX = "학습자"

# 닉네임의 최대 길이.
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
# 모르고 망가뜨린다.
_HIDDEN_CATEGORIES = ("Cf", "Cc")


def _strip_hidden(value: str) -> str:
    return "".join(
        c for c in value if unicodedata.category(c) not in _HIDDEN_CATEGORIES
    )


_SPACES = re.compile(r"\s+")


# 한글 채움 문자와 점자 빈칸. 글자로 분류돼 위의 거름을 지나가는데 화면에서는 빈칸으로
# 보인다. 그대로 두면 이것만으로 된 빈 이름이 순위표에 오르고, 이름 끝에
# 붙여 남의 이름과 다른 문자열을 만들 수 있다. 보이는 대로 공백으로 다룬다.
_BLANK_LOOKING = re.compile("[\u115f\u1160\u3164\uffa0\u2800]")


def normalize_display_name(value: str | None) -> str:
    """닉네임을 비교 가능한 형태로 다듬는다.

    같은 이름으로 보이는데 DB 에서는 다른 문자열인 경우를 없앤다.
    순위표에 남의 이름 행세를 하는 행이 끼는 것을 막는 것이 목적이다.

    NFC 로 모으는 이유: 한글은 "한" 을 완성형 한 글자로도, 자모 셋으로도
    쓸 수 있다. 화면에서는 똑같이 보이는데 문자열로는 다르다. 모으지
    않으면 조합형으로 남의 이름과 같은 줄을 만들 수 있고, 자모가 글자마다
    세 개라 길이도 세 배로 세어져 멀쩡한 이름이 길이 제한에 걸린다.
    """
    spaced = _BLANK_LOOKING.sub(" ", value or "")
    cleaned = _SPACES.sub(" ", _strip_hidden(spaced)).strip()
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

    DB 제약과 같은 함수로 비교한다. 제약은 Lower(display_name) 인데
    파이썬 쪽만 __iexact 를 쓰면 PostgreSQL 에서 갈린다. iexact 는
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
    막히면 안 된다. 동명이인은 흔하고, 사용자는 자기가 뭘 잘못했는지
    알 수 없다.

    빈 문자열을 돌려줄 수 있다. 그 경우 User.save() 가 학습자1234 꼴로
    지어 넣는다. 구글 이름이 금칙어에 걸릴 때도 그렇게 한다. 구글에서
    온 사람은 이름을 입력한 적이 없어서, 막으면 가입할 길이 없다.
    """
    name = shorten_display_name(wanted)
    if not name or name_is_forbidden(name):
        return ""

    if not name_taken(name):
        return name

    for suffix in range(2, 1000):
        # 길이를 넘기면 저장이 안 된다. 붙일 자리를 비워둔다.
        # 자른 자리가 공백일 수 있어 shorten 을 한 번 더 태운다.
        candidate = shorten_display_name(
            f"{name[: DISPLAY_NAME_MAX - len(str(suffix))]}{suffix}"
        )
        # 잘라 낸 자리에서 금칙어가 새로 생길 수 있어 다시 본다.
        if (
            candidate
            and not name_is_forbidden(candidate)
            and not name_taken(candidate)
        ):
            return candidate

    # 같은 이름이 천 명이면 지어주는 쪽으로 넘긴다.
    return ""


class AvatarPhotoError(ValueError):
    """올린 파일을 사진으로 못 쓸 때. 뷰가 안내 문구로 바꾼다."""


def _jpeg_decodes_in_one_pass(raw: bytes) -> bool:
    """libjpeg 가 원래 크기만큼의 중간 저장 공간(계수 버퍼) 없이 한 번에 풀 수 있는 JPEG 인가.

    순차 JPEG(SOF0·SOF1)이고 첫 스캔이 모든 색 성분을 담고 있을 때만 그렇다. 프로그레시브
    이거나, 성분을 스캔마다 나눠 담았거나, 무손실 같은 다른 방식이면 libjpeg 는 원래 크기만큼
    계수를 다 들고 있어야 해서 줄여 펼쳐도(draft) 메모리가 줄지 않는다. libjpeg 가 가르는 조건보다
    조금 좁게 본다. 산술 부호화 순차(SOF9)는 한 번에 풀리지만 폰 사진에 나오지 않아 낮은 상한으로
    보낸다.

    파일 앞부분의 표지(마커)를 길이대로 건너뛰며 읽는다. 폰 사진은 EXIF 안에 작은 JPEG 를
    품고 있어서, 바이트를 찾는 식으로 읽으면 그 안의 표지가 먼저 걸린다. 모양이 이상하면
    아니라고 본다(낮은 상한을 쓴다).

    SOF 가 둘이면 뒤의 것으로 판정한다. libjpeg 는 그런 파일을 펼치기 전에 거절하므로
    메모리 문제는 없다(tests_jpeg_one_pass_dynamic).
    """
    i, components = 2, None
    try:
        while True:
            if raw[i] != 0xFF:
                return False
            marker = raw[i + 1]
            if marker == 0xFF:  # 표지 앞의 채움 바이트
                i += 1
                continue
            if marker == 0xDA:  # 첫 스캔 시작. 길이 다음 바이트가 이 스캔에 든 성분 수다.
                return components is not None and raw[i + 4] == components
            # 프레임 시작(SOF). 같은 대역의 C4(허프만표)·C8(예약)·CC(DAC)는 SOF 가 아니다.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                if marker not in (0xC0, 0xC1):
                    return False
                components = raw[i + 9]  # 길이·정밀도·높이·너비 다음 바이트가 성분 수다
            # 길이를 가진 표지만 건너뛴다(APPn, 주석, 양자화표, 허프만표, DRI, DAC).
            # RSTn·FF00 처럼 길이 없는 표지를 길이대로 읽으면 실제 해석기와 읽는 자리가
            # 갈라져, 주석 안에 숨긴 가짜 스캔 표지에 속는다. 정상 사진의 첫 스캔 앞에는
            # 나오지 않으므로 모르는 표지는 아니라고 본다.
            elif not (0xE0 <= marker <= 0xEF or marker in (0xFE, 0xDB, 0xC4, 0xDD, 0xCC)):
                return False
            i += 2 + int.from_bytes(raw[i + 2 : i + 4], "big")
    except IndexError:
        return False


def shrink_avatar_photo(raw: bytes) -> bytes:
    """올린 사진을 줄여서 WebP 바이트로 바꾼다.

    확장자와 Content-Type 을 믿지 않는다. 둘 다 올리는 쪽이 적어
    보내는 값이라, 아무 파일이나 .jpg 로 이름 붙여 보낼 수 있다. Pillow 로
    실제로 열어봐야 사진인지 알 수 있다.

    WebP 로 통일하는 이유:

    - 투명한 PNG 를 JPEG 로 바꾸면 투명한 부분이 검게 나온다. 배경을
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

    # WebP 는 크기를 열기 전에 본다. Pillow 는 WebP 를 여는 순간(Image.open)
    # 원래 크기의 캔버스를 잡아서, 아래 픽셀 검사는 이미 늦다. 머리말에서
    # 크기를 읽는 것은 Pillow 가 캔버스를 잡기 전에 하는 검사와 같은 함수다
    # (Pillow 13 의 내부 함수라 올릴 때 tests_avatar_photo_memory 가 지켜본다).
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        from PIL.WebPImagePlugin import _get_size as webp_size

        size = webp_size(raw[:30])
        # 크기를 못 읽는 머리말은 받지 않는다. Pillow 는 그때 검사를 건너뛰고
        # 해석기에 그대로 넘긴다.
        if size is None:
            raise AvatarPhotoError("사진 파일을 읽을 수 없습니다.")
        if size[0] * size[1] > AVATAR_PHOTO_MAX_PIXELS_UNSCALED:
            raise AvatarPhotoError("사진이 너무 큽니다. 다른 사진을 골라주세요.")

    # verify() 를 따로 부르지 않는다. 아래 fit() 이 실제로 픽셀을 읽으므로
    # "머리말만 멀쩡하고 내용이 잘린" 파일은 거기서 OSError 로 걸린다.
    # verify() 를 넣으면 그 뒤 이미지를 못 써서(Pillow 가 그렇게 정했다)
    # 같은 파일을 두 번 열어야 하는데, 얻는 것 없이 일만 두 배가 된다.
    try:
        # 폰 사진은 이 셋이다. 나머지 형식은 여는 것부터 막는다. Pillow 취약점은
        # 잘 안 쓰는 형식의 해석기에서 자주 나와서, 열 수 있는 형식을 줄이면 그만큼 덜 걸린다.
        with Image.open(io.BytesIO(raw), formats=AVATAR_PHOTO_FORMATS) as image:
            # 픽셀 수를 여기서 본다. 위의 바이트 상한으로는 못 막는
            # 공격이 있다. 같은 색으로 채운 큰 그림은 압축이 아주 잘 돼서,
            # 12000x12000(1.4억 픽셀)짜리가 440KB 밖에 안 된다. 5MB 검사를
            # 지나간 뒤 아래에서 실제로 펼치는 순간 0.5GB 를 쓴다.
            #
            # Pillow 에도 같은 방어가 있지만 믿을 수 없다. 기본 한계
            # (8948만)를 넘으면 경고만 내고 그냥 통과시키고, 예외로 막는
            # 것은 그 두 배를 넘을 때다. 즉 1배와 2배 사이가 뚫려 있다.
            #
            # Image.open 은 머리말만 읽으므로 이 시점에는 아직 안 펼쳤다.
            # 여기서 끊어야 메모리를 안 쓴다.
            original_pixels = image.width * image.height
            if original_pixels > AVATAR_PHOTO_MAX_PIXELS:
                raise AvatarPhotoError("사진이 너무 큽니다. 다른 사진을 골라주세요.")

            # JPEG(MPO 포함)는 1/2·1/4·1/8 로 줄여서 펼칠 수 있다(draft). 256px 로 줄일
            # 사진을 원래 크기로 펼칠 이유가 없다. 4000x3000 폰 사진 한 장을 줄이는 데
            # 100MB 쓰던 것이 재어 보니 6MB 로 준다. 두 변이 모두 512 이상으로
            # 남게 고르므로 화질은 그대로다. 모드는 건드리지 않는다(None). 다른 형식에서는
            # 아무 일도 안 한다.
            image.draft(None, (AVATAR_PHOTO_SIZE * 2, AVATAR_PHOTO_SIZE * 2))

            # 줄여서 펼치지 못하는 그림은 낮은 상한까지만 받는다. 셋이다.
            # - PNG·WEBP: draft 가 크기를 안 바꾼다.
            # - 짧은 변이 1024 보다 작은 아주 긴 JPEG(49999x1000 같은 것): 배율이 짧은
            #   변으로 정해져 1 이 된다. 폰 파노라마는 짧은 변이 1024 를 넘어 1/2 이하로 준다.
            # - 한 번에 풀지 못하는 JPEG(프로그레시브, 성분을 스캔마다 나눈 것 등): 줄여서
            #   펼쳐도 해석기가 원래 크기의 버퍼를 먼저 잡는다. 5천만 화소 CMYK 가 400MB 를
            #   썼다. 그래서 원래 크기로 본다(_jpeg_decodes_in_one_pass).
            draft_pixels = image.width * image.height  # draft 뒤라 줄인 크기다
            one_pass = image.format in ("JPEG", "MPO") and _jpeg_decodes_in_one_pass(raw)
            decoded = draft_pixels if one_pass else original_pixels
            if decoded > AVATAR_PHOTO_MAX_PIXELS_UNSCALED:
                raise AvatarPhotoError("사진이 너무 큽니다. 다른 사진을 골라주세요.")

            # 폰 사진은 세로로 찍어도 가로 그림 + "돌려서 보라" 는 표시로
            # 저장되는 경우가 많다(EXIF Orientation). 그대로 줄이면 표시가
            # 사라져서 옆으로 누운 사진이 된다.
            #
            # in_place 로 돌린다. 기본값은 돌릴 필요가 없어도 원본을 통째로 복사해서,
            # 펼친 그림이 메모리에 두 벌 생긴다.
            from PIL import ImageOps

            ImageOps.exif_transpose(image, in_place=True)

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
    except UnidentifiedImageError as exc:
        # 사진이 아닌 파일, 받지 않는 형식(GIF, HEIC 등), 머리말부터 깨진 JPG 가 여기로
        # 온다. "읽을 수 없다" 만 보이면 GIF 를 고른 사람은 파일이 깨진 줄 안다.
        raise AvatarPhotoError(
            "JPG, PNG, WEBP 사진만 올릴 수 있습니다. 다른 사진을 골라주세요."
        ) from exc
    except (
        OSError,
        ValueError,
        # Pillow 가 스스로 폭탄이라 판단하는 경우(기본 한계의 두 배 초과).
        # Exception 직속이라 위의 셋에 안 걸린다. 빼면 위의 픽셀 검사에
        # 닿기도 전에 터져서 400 이 아니라 500 이 나간다.
        Image.DecompressionBombError,
    ) as exc:
        # 열리기는 했는데 중간이 깨진 파일과 너무 큰 그림이 여기로 온다.
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
        섞여 들어간 행이 하나라도 있으면 그 계정은 로그인할 수 없다.
        읽기와 쓰기가 같은 규칙을 보도록 여기서 맞춘다.
        """
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": email})

    def _create_user(self, email: str, password: str | None, **extra) -> User:
        if not email:
            raise ValueError("이메일은 필수입니다.")

        # 이메일 전체를 소문자로 내린다. normalize_email 은 도메인만 낮춘다.
        # 이메일 로그인은 대소문자를 무시하고 찾지만(get_by_natural_key),
        # 구글 로그인은 소문자로 내린 이메일과 정확히 일치하는 행을 찾는다
        # (views.GoogleLoginView). 저장값에 대문자가 섞이면 같은 사람의
        # 계정이 둘로 갈라진다.
        #
        # 규격상 @ 앞은 대소문자를 구분할 수 있지만 실제로 그렇게 쓰는
        # 메일 서버는 사실상 없다.
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
        "닉네임", max_length=DISPLAY_NAME_MAX, blank=True
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

    # 직접 올린 사진. 줄여서 WebP 로 바꾼 바이트가 그대로 들어간다.
    #
    # 파일이 아니라 DB 에 두는 이유: 배포할 때마다 컨테이너 디스크가
    # 초기화되고, Railway 볼륨도 지워질 수 있다. 외부 스토리지를 붙이면 그건 그것대로 계정·요금·장애
    # 지점이 하나 는다.
    #
    # 줄인 뒤라 한 장이 대개 10~20KB 다. 그래서 행이 무거워지는 걱정보다
    # 읽히는 자리가 문제인데, 그건 avatar_photo 를 어느 질의에도 안 실어서
    # 푼다. UserSerializer 는 이 칸을 내보내지 않고, 사진은
    # 별도 엔드포인트(views.AvatarPhotoFileView)가 이 칸만 골라 읽는다.
    avatar_photo = models.BinaryField("올린 사진", null=True, blank=True, editable=False)

    # 사진 주소에 쓰는 값. 사진을 올릴 때마다 새로 만든다.
    #
    # pk 를 주소로 쓰지 않는 이유: pk 는 연번이라 1번부터 눌러보면
    # 사진 올린 계정을 전부 훑을 수 있다. 순위표도 이름과 그림을 같이
    # 보여주지만 그쪽은 상위 몇 줄이고 페이지를 넘겨야 한다. 같은 정보라도
    # 전원을 한 번에 긁는 것과는 비용이 다르고, 얼굴 사진은 그 차이가
    # 중요한 종류다.
    #
    # 바꿀 때마다 새로 만드는 이유: 값을 고정하면 옛 주소를 아는 사람이
    # 바뀐 사진도 계속 본다. 새 값이면 옛 주소는 그 자리에서 404 가 된다.
    # 주소 자체가 달라지므로 캐시도 함께 깨져, ?v= 같은 꼬리표를 따로 붙일
    # 필요가 없다.
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
        # 그림 요청마다 표 전체를 훑는데, 순위표 한 화면이 스무 장을
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
    # 바뀌기 때문이다.
    #
    # 사진을 지우면 None 으로 되돌린다.
    avatar_photo_at = models.DateTimeField("사진 올린 시각", null=True, blank=True)

    # 가입할 때 약관·처리방침에 동의한 시각과 그때의 문서 버전.
    # 비어 있으면 가입 동의를 거치지 않은 계정이다. 이 칸이 생기기 전에
    # 가입했거나 관리자가 직접 만든 경우다.
    terms_agreed_at = models.DateTimeField("약관 동의 시각", null=True, blank=True)
    terms_version = models.CharField("동의한 약관 버전", max_length=20, blank=True)

    # 만 14세 이상임을 확인한 시각. 만 14세 미만은 가입을 받지 않는다.
    age_confirmed_at = models.DateTimeField("나이 확인 시각", null=True, blank=True)

    # 마지막으로 서비스를 쓴 날. 1년 미접속 계정을 고르는 기준이다.
    #
    # last_login 으로 고르지 않는 이유: 토큰 로그인은 그 칸을 찍지 않아서
    # 관리자를 뺀 회원은 전부 비어 있다. 그 칸으로는 오래 안 쓴 사람을 가릴
    # 수 없다.
    #
    # 시각이 아니라 날짜인 이유: 하루에 한 번만 기록하면 된다. 요청마다
    # 기록하면 읽기만 하는 요청도 DB 에 쓰기를 일으킨다.
    #
    # 기본값이 오늘인 이유: 비워 두면 이 칸이 생기기 전에 가입한 사람을
    # "오래 안 쓴 사람" 과 구분할 수 없다.
    last_seen_on = models.DateField("마지막 이용일", default=timezone.localdate)

    # 파기 안내 메일을 보낸 시각. 다시 이용하면 비운다.
    purge_notice_sent_at = models.DateTimeField("파기 안내 시각", null=True, blank=True)

    # 하루 공부량. 일일공부가 이 길이로 바로 시작한다. 비어 있으면 아직 안
    # 고른 것이고, 화면이 처음 들어올 때 한 번 묻는다. 그날만 다른 길이로
    # 하는 것은 일일공부 화면에서 고르고, 여기 값은 바뀌지 않는다.
    #
    # db_default 를 둔다. 이 칸을 모르는 코드(배포 중 잠깐 남는 옛 서버, 같은
    # 로컬 DB 를 쓰는 다른 브랜치)가 가입을 넣으면 이 칸이 빠진 INSERT 가 되는데,
    # DB 에 기본값이 없으면 NOT NULL 에 걸려 가입이 실패한다.
    daily_length = models.CharField(
        "하루 공부량",
        max_length=8,
        choices=StudyLength.choices,
        blank=True,
        default="",
        db_default="",
    )

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

    # 비밀번호 로그인을 껐는데 아직 저장하지 않았다. set_unusable_password 는
    # set_password 와 달리 _password 를 남기지 않아 save 가 따로 알아야 한다.
    _password_dropped = False

    def save(self, *args, **kwargs) -> None:
        """이메일과 닉네임을 저장 직전에 정리하고, 비밀번호·이메일이 바뀌었으면 저장 뒤
        그 계정의 로그인을 모두 끊는다(_credentials_changed).

        매니저가 아니라 여기서 하는 이유: Admin 의 계정 추가 폼은
        create_user 를 거치지 않고 곧바로 save() 를 부른다. 매니저에만
        두면 그 경로로 정리되지 않은 값이 들어온다.

        이름을 여기서 지어 넣으므로, 어느 경로로 만들어도 빈 이름이
        저장되지 않는다. 비어 있을 때 화면이 이메일 앞부분을 대신 보여주면
        순위표에 남의 메일 주소 절반이 뜬다.
        """
        # 이메일 전체를 소문자로 내리는 이유는 UserManager._create_user 주석 참고.
        self.email = self.email.lower()

        self.display_name = shorten_display_name(self.display_name)
        if not self.display_name:
            self.display_name = self._generate_display_name()

        fields = kwargs.get("update_fields")
        credentials_changed = self._credentials_changed(fields)

        super().save(*args, **kwargs)

        # 새 토큰은 반드시 이 save 뒤에 낸다. 먼저 내면 여기서 함께 지워진다.
        if credentials_changed:
            LoginToken.end_all(self.pk)
        if fields is None or "password" in fields:
            self._password_dropped = False
        if fields is None or "email" in fields:
            self._loaded_email = self.email

    def _credentials_changed(self, fields) -> bool:
        """이번 저장으로 비밀번호나 이메일이 바뀌는가. 바뀌면 save 가 로그인을 모두 끊는다.

        API 의 변경 화면은 뷰가 따로 끊고 새 토큰을 주지만, Admin 에서 바꾸면 그 길을 안
        타서 옛 토큰이 30일 동안 살아 있었다. 비밀번호가 새어 관리자가 바꿔 준 계정이
        그대로 열려 있게 된다. 뷰가 다시 끊어도 지울 것이 없을 뿐이다.

        fields 는 save 의 update_fields 다. 저장하지 않는 칸은 보지 않는다 - 메모리에서만
        바뀐 이메일로 로그인을 끊지 않는다.

        비밀번호: set_password 는 _password 를 남긴다(Django 가 저장 뒤 비운다). 로그인할
        때 해시를 새로 저장하는 길(check_password)은 그 값을 비운 뒤 저장해 끊지 않는다.
        해시 문자열을 견주지 않는 이유가 그것이다 - 견주면 Django 를 올려 해시 반복 횟수가
        바뀐 날 로그인할 때마다 다른 기기가 다 끊긴다. "비밀번호 로그인 끄기" 는
        set_unusable_password 가 따로 표시한다. 알려진 빈틈: set_password 뒤 다른 칸만
        먼저 저장하면 Django 가 _password 를 비워 그다음 비밀번호 저장에서 놓친다. 그렇게
        저장하는 코드는 없다.

        이메일: DB 에서 읽은 값(from_db, refresh_from_db 가 기억)과 견준다.
        """
        if self._state.adding:
            return False

        if fields is None or "password" in fields:
            if self._password is not None or self._password_dropped:
                return True

        if fields is not None and "email" not in fields:
            return False
        loaded = getattr(self, "_loaded_email", None)
        if loaded is None:
            # 이메일을 빼고 읽은 행(only, defer)에 이메일을 바로 넣은 경우. 비교할 값이
            # 없으니 DB 에서 한 번 읽는다. 이메일을 읽은 뒤였다면 refresh_from_db 가 이미
            # 채워 여기 오지 않는다.
            loaded = type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()
        return loaded is not None and loaded.lower() != self.email

    def set_unusable_password(self) -> None:
        """비밀번호 로그인을 끈다. 저장할 때 그 계정의 로그인도 모두 끊긴다(save).

        Admin 의 비밀번호 화면에서 "비밀번호 로그인 끄기" 를 고르면 이 길로 온다. 계정이
        털려서 관리자가 끄는 경우인데, 끊지 않으면 털어 간 쪽 토큰이 이어 가기로 계속 산다.
        """
        super().set_unusable_password()
        if not self._state.adding:
            self._password_dropped = True

    @classmethod
    def from_db(cls, db, field_names, values):
        """DB 에서 읽은 이메일을 기억한다. save 가 이메일이 바뀌었는지 가른다.

        이메일을 빼고 읽은 행(only, defer)은 기억하지 않는다. 그때 비교하면 처음
        읽는 값과 견주게 되어 바뀌지 않은 이메일을 바뀐 것으로 본다.
        """
        instance = super().from_db(db, field_names, values)
        if "email" in instance.__dict__:
            instance._loaded_email = instance.email
        return instance

    def refresh_from_db(self, using=None, fields=None, from_queryset=None) -> None:
        """다시 읽은 이메일을 기억한다. 안 하면 그 사이 다른 곳에서 바뀐 이메일을 이 객체가
        바꾼 것으로 보고, 이름만 저장해도 로그인을 모두 끊는다.

        이메일을 다시 읽었을 때만 기억한다. 다른 칸만 읽을 때(지연 로드가 그 칸만 부른다)
        덮으면, 메모리에서 바꾼 아직 저장 안 한 이메일을 DB 값으로 착각한다.
        """
        super().refresh_from_db(using=using, fields=fields, from_queryset=from_queryset)
        if (fields is None or "email" in fields) and "email" in self.__dict__:
            self._loaded_email = self.email

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
        # 계속 쓸 수 있게 한다. 여기서 포기하면 가입이 막힌다.
        return f"{GENERATED_NAME_PREFIX}{secrets.randbelow(9_000_000) + 1_000_000}"

    def __str__(self) -> str:
        # 이메일을 돌려주지 않는다. 관리자 작업 기록이 이 글자를 그대로
        # 저장해서(LogEntry.object_repr), 계정을 지워도 주소가 남는다.
        return f"회원 {self.pk}"

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
        base64 로 싣으면 그 응답이 매번 수십 KB 가 되고, 캐시도 못 한다.
        JSON 안에 들어간 그림은 브라우저 이미지 캐시를 못 탄다.

        주소가 pk 가 아니라 avatar_photo_key 인 이유는 그 필드 주석에 있다.
        꼬리표(?v=)를 안 붙이는 이유도 거기 있다. 사진을 바꾸면 이 값이
        새로 만들어져 주소가 달라진다.
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

        순위표는 이 property 를 가짜 User 로 부른다
        (apps/learning/leaderboards.py 의 _row). .values() 로 긁은 칸만
        채워 넣으므로, 여기서 보는 필드가 늘면 그쪽 목록에도 더해야 한다.
        안 더하면 순위표 줄에서만 다른 그림이 뜨는데, 화면이 비지 않아서
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


def _new_login_token_key() -> str:
    """새 로그인 토큰 값. DRF 토큰과 같은 꼴(16진수 40자)이라 옮겨 온 옛 값과 섞여도 된다.

    LoginToken.device 의 기본값으로도 쓴다.

    0009 마이그레이션이 이 이름으로 부른다. 이름을 바꾸거나 지우면 마이그레이션이 깨진다.
    """
    return secrets.token_hex(20)


def token_digest(key: str) -> str:
    """로그인 토큰 원문을 DB 에 두는 값(지문)으로 바꾼다. sha256 16진수 64자.

    비밀번호처럼 일부러 느린 해시를 쓰지 않는다. 비밀번호는 사람이 골라 추측할 수 있어
    느리게 만들어 추측을 막지만, 토큰은 무작위 160비트라 추측할 수 없다. 요청마다
    인증이 부르므로 빨라야 한다.

    0016 마이그레이션이 같은 계산을 따로 적어 두었다. 여기를 바꾸면 DB 에 있는 지문과
    맞지 않아 모두 로그아웃된다.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def _next_login_token_key(key: str) -> str:
    """이어 가기(LoginToken.renew)가 내는 새 토큰 원문. 앞 토큰 원문과 서버 비밀 키로 정한다.

    무작위로 만들지 않는 이유: DB 에는 지문만 있어서, 이미 만든 새 토큰을 한 번 더 돌려줘야
    할 때(동시에 온 이어 가기, 새 토큰을 실은 응답이 끊긴 경우) 원문을 꺼낼 데가 없다.
    앞 토큰 원문으로 다시 계산하면 같은 값이 나온다.

    서버 비밀 키를 섞는 이유: 섞지 않으면 옛 토큰을 빼 간 쪽이 서버에 묻지 않고 새 토큰을
    계산해, 옛 토큰을 다시 내야 걸리는 재사용 감지(SlimTokenAuthentication)를 비켜 간다.
    DB 에는 원문이 없으니 DB 와 비밀 키를 함께 얻어도 계산할 수 없다.

    DJANGO_SECRET_KEY 를 바꾸면 그 전에 이어 받은 토큰은 다시 계산되지 않는다. 그때 renew 는
    다음 토큰을 새로 낸다.

    같은 원문에서는 늘 같은 다음 토큰이 나온다. 그래서 한 로그인의 가장 새 토큰 한 줄만
    지우면, 남은 앞 토큰의 이어 가기가 지운 값을 그대로 되살린다. 관리자 화면이 한 줄이 아니라
    그 로그인(device)을 통째로 지우는 이유다(LoginTokenAdmin).
    """
    return salted_hmac("accounts.LoginToken.renew", key, algorithm="sha256").hexdigest()[:40]


class LoginToken(models.Model):
    """로그인 토큰. 로그인 한 번마다 따로라 기기마다 따로 갖는다.

    DRF 의 Token 을 쓰지 않는 이유: 그쪽은 계정당 하나(OneToOne)라 폰과 PC 가
    같은 토큰을 나눠 가졌다. 한쪽에서 로그아웃하면 그 토큰이 지워져 다른 쪽도
    같이 끊겼다. 0010 마이그레이션이 그때 쓰던 토큰을 이 표로 옮겼다.

    토큰 값을 기본 키로 두지 않는 이유: 관리자 화면 주소가 기본 키로 만들어진다
    (/admin/accounts/logintoken/<pk>/). 토큰이 주소에 들어가면 서버 로그와
    브라우저 기록에 남는다. DRF 가 TokenProxy 를 따로 둔 것도 같은 이유다.

    발급하고 LIFETIME 이 지나면 인증에서 거절하고(SlimTokenAuthentication), 매일
    정리(daily_cleanup)가 지운다. 그 전에도 로그아웃(그 기기 것만)·비밀번호 변경·
    이메일 변경·계정 삭제 때 지운다.
    처리방침 3절의 "로그인 토큰" 보관 기간이 이 동작을 적고 있다. 바꾸려면 그
    문구부터 고친다(시행 7일 전 공지).

    쓰는 동안은 로그인이 이어진다(renew). 발급하고 하루가 지난 토큰으로 이어 가기를
    부르면 새 토큰을 내준다. 같은 로그인에서 이어 받은 토큰은 device 가 같다. 옛 토큰은
    새 토큰이 처음 쓰일 때(mark_delivered) 바뀐 것으로 적히고 REPLACED_GRACE 뒤에 죽는다.
    죽은 옛 토큰도 발급 30일까지는 표에 남는다. 그 사이 그것이 다시 오면 새어 나간 것으로
    보고 그 로그인을 통째로 끊는다(SlimTokenAuthentication). 로그인을 끝낼 때는 end_login,
    end_all 을 쓴다.
    그래서 30일은 "로그인하고 30일" 이 아니라 "30일 동안 안 쓰면" 이 된다. 토큰
    하나하나는 여전히 발급 30일 안에 지워져 처리방침 문구는 그대로 맞다.

    이 표는 비우면 안 된다. 비우면 로그인한 사람이 모두 로그아웃되고, 0010 은 이미
    적용돼 다시 옮기지 않는다. 이 표를 만든 배포 전으로 되돌리지도 않는다
    (DEPLOY.md "배포 확인" 의 회원을 가리키는 표).

    토큰 원문은 DB 에 두지 않고 지문(token_digest)만 둔다. 원문을 두면 DB 나 백업 파일을
    본 사람이 그 값을 쿠키에 넣어 바로 그 사람으로 로그인한다. 비밀번호를 해시로 두는
    것과 같은 이유다. 원문(key)은 발급한 그 객체와, 그 원문으로 인증한 요청의
    객체(request.auth)에만 있다. DB 에서 새로 읽은 객체에는 없다(None).
    """

    # 지문. 칸 이름(db_column)은 원문을 두던 때의 "key" 그대로다. 이 배포 전 코드로
    # 되돌려도 없는 칸을 찾아 500 이 나는 대신, 토큰이 안 맞아 다시 로그인하는 데서 그친다.
    digest = models.CharField(
        "토큰 지문", max_length=64, unique=True, editable=False, db_column="key"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="login_tokens", verbose_name="사용자"
    )
    # auto_now_add 가 아닌 이유: 0010 이 옛 토큰을 옮길 때 원래 발급 시각을 그대로
    # 넣는다. auto_now_add 는 넣은 값을 지금 시각으로 덮는다.
    created = models.DateTimeField("발급 시각", default=timezone.now)
    # 로그인 한 번을 가리키는 값. 이름은 이 표의 다른 말("기기마다 따로")에 맞췄다. 같은
    # 폰에서 다시 로그인하면 새 값이다. 로그인할 때 새로 정하고 renew 가 물려준다.
    # 로그아웃은 이 값이 같은 토큰을 다 지우고, 이메일 변경 링크는 토큰 값이 아니라 이 값에
    # 묶인다(views._link_device). 토큰이 바뀌어도 대기 중인 링크가 살게.
    # 0013 이 11-13 전 토큰에는 토큰 원문을 넣었고, 0016 이 그 값을 토큰과 같은 지문으로
    # 바꿨다. 그래서 길이가 지문과 같은 64자다.
    #
    # db_default 는 이 칸을 모르는 코드가 넣는 행을 위한 것이다. Railway 는 새 배포의
    # migrate 가 끝난 뒤에도 몇 초 동안 옛 코드가 요청을 받는데(0010 머리말), 옛 코드의
    # 로그인이 이 칸 없이 행을 넣다가 NOT NULL 에 걸려 500 이 나지 않게 DB 가 무작위 값을
    # 채운다. Random 은 Postgres 와 SQLite(USE_SQLITE) 둘 다에 있다. ORM 으로 만드는 행은
    # default 가 이긴다.
    device = models.CharField(
        "기기",
        max_length=64,
        default=_new_login_token_key,
        db_default=Cast(Random(), models.CharField()),
        editable=False,
    )
    # renew 가 만든 새 토큰은 받은 쪽이 아직 안 썼다(False). 응답이 중간에 끊겨 쿠키에
    # 못 들어갔을 수 있어서, 처음 쓰일 때까지 옛 토큰을 살려 둔다(mark_delivered).
    # 로그인으로 만든 토큰은 앞 토큰이 없어 처음부터 True 다.
    delivered = models.BooleanField("받음", default=True, db_default=True, editable=False)
    # 같은 로그인의 새 토큰이 처음 쓰인 시각. 이 뒤로 REPLACED_GRACE 동안만 통한다.
    replaced_at = models.DateTimeField("바뀐 시각", null=True, blank=True, editable=False)

    _key: str | None = None

    # 로그인 쿠키(frontend/src/lib/token-cookie.ts 의 TOKEN_MAX_AGE)와 같은 30일.
    # 쿠키보다 짧게 잡으면 로그인해 있는 사람이 끊긴다. 쓰는 동안은 하루마다 새 토큰과
    # 함께 쿠키도 30일짜리로 다시 붙는다(proxy.ts).
    LIFETIME = timedelta(days=30)
    # 이어 가기를 불러도 이보다 어린 토큰은 그대로 돌려준다. 화면은 이동할 때마다
    # 부를 수 있어서, 없으면 요청마다 토큰이 바뀌고 행이 쌓인다. 화면 쪽 값
    # (frontend/src/lib/token-cookie.ts 의 RENEW_AFTER_SECONDS)과 같다.
    RENEW_AFTER = timedelta(days=1)
    # 새 토큰이 쓰이기 시작한 뒤 옛 토큰이 더 통하는 시간. 새 쿠키를 받기 전에 출발한
    # 요청(다른 탭, 화면이 부르는 중계)이 옛 토큰을 싣고 온다.
    REPLACED_GRACE = timedelta(hours=1)

    class Meta:
        verbose_name = "로그인 토큰"
        verbose_name_plural = "로그인 토큰"

    def __str__(self) -> str:
        # 토큰 값을 넣지 않는다. 관리자 작업 기록(LogEntry.object_repr)에 남는다.
        return f"{self.user} 의 로그인"

    @property
    def key(self) -> str | None:
        """토큰 원문. DB 칸이 아니다(클래스 설명 끝 단락).

        속성(property)으로 둔 이유: Django 는 속성이면 create(key=...) 로 받아 준다. 이어
        가기가 정한 원문을 넣어 만들 때 쓴다.
        """
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        self._key = value

    def save(self, *args, **kwargs) -> None:
        # 새 토큰이면 원문을 정하고 지문을 채운다. 원문은 이 객체에만 남아 응답으로 나간다.
        if not self.digest:
            if self.key is None:
                self.key = _new_login_token_key()
            self.digest = token_digest(self.key)
        super().save(*args, **kwargs)

    @classmethod
    def expired(cls) -> models.QuerySet[LoginToken]:
        """발급하고 LIFETIME 이 지난 토큰. 매일 정리가 지운다.

        바뀌고 유예가 지난 옛 토큰은 인증에서는 거절하지만(is_expired) 여기서 고르지
        않는다. 남겨 둬야 그것이 다시 왔을 때 새어 나간 것을 알아본다. 먼저 지우면 그냥
        "없는 토큰" 이 되어, 빼 간 쪽이 이어 받은 토큰이 그대로 산다.
        """
        return cls.objects.filter(created__lt=timezone.now() - cls.LIFETIME)

    @classmethod
    def end_login(cls, user_id: int, device: str) -> None:
        """그 로그인(device)의 토큰을 모두 지운다. 로그아웃과 재사용 감지가 쓴다."""
        with transaction.atomic():
            cls.lock_member(user_id)
            cls.objects.filter(user_id=user_id, device=device).delete()

    @classmethod
    def end_all(cls, user_id: int) -> None:
        """그 계정의 토큰을 모두 지운다. User.save 가 비밀번호·이메일이 바뀌었을 때 부른다.

        비밀번호 변경·이메일 변경 뷰도 부르지만, 그때는 save 가 이미 지운 뒤라 남은 것이
        없다. 뷰의 호출은 "여기서 끊는다" 를 읽는 사람에게 보이려고 둔다.

        뒤이어 내주는 새 토큰은 새 로그인(device)이라 renew 와 겹치지 않는다. 그래서 새
        토큰을 만드는 것까지 이 잠금 안에 둘 필요는 없다.
        """
        with transaction.atomic():
            cls.lock_member(user_id)
            cls.objects.filter(user_id=user_id).delete()

    @staticmethod
    def lock_member(user_id: int) -> User | None:
        """회원 행을 잠근다. 이미 있는 로그인의 토큰을 새로 만들거나 지우는 곳이 먼저 부른다.

        renew 가 새 토큰을 만드는 동안 지우는 쪽의 DELETE 가 먼저 시작되면, 새 토큰이
        지울 대상에서 빠져 살아남는다(Postgres 의 READ COMMITTED). 같은 행을 잠그면
        둘이 차례로 돈다. 계정 삭제(MeView.delete)와 이메일 변경 확인도 회원 행을 먼저
        잠가 순서가 같다. 새 로그인을 만드는 곳(로그인, 가입)은 있는 로그인과 겹치지 않아
        잠그지 않는다.
        """
        return User.objects.select_for_update().only("pk").filter(pk=user_id).first()

    def replaced_past_grace(self) -> bool:
        """새 토큰으로 넘어가고 유예까지 지났나. 이 토큰이 다시 오면 새어 나간 것이다.

        바뀐 지 유예 안이면 False 다. 새 쿠키를 받기 전에 출발한 정상 요청일 수 있다.
        """
        return (
            self.replaced_at is not None
            and self.replaced_at < timezone.now() - self.REPLACED_GRACE
        )

    def is_expired(self) -> bool:
        """인증에서 거절할 토큰인가. 인증이 매 요청 본다(SlimTokenAuthentication)."""
        return self.created < timezone.now() - self.LIFETIME or self.replaced_past_grace()

    def renew(self) -> LoginToken | None:
        """로그인을 이어 갈 토큰. 하루가 지났으면 같은 로그인(device)의 새 토큰을 낸다.

        - 같은 로그인에 이 토큰보다 새 토큰이 이미 있으면 그것을 돌려준다. 이어 가기가
          동시에 둘 왔거나, 새 토큰을 실은 응답이 끊겨 옛 토큰으로 다시 온 경우다. 또
          만들면 쿠키에 못 들어간 토큰이 쌓인다. DB 에는 지문만 있으므로 원문은 이 토큰
          원문에서 다시 계산한다(_next_login_token_key). 계산이 맞지 않으면(토큰을 지문으로
          바꾼 배포 전에 무작위로 만든 새 토큰, 서버 비밀 키를 바꾼 뒤) 이 토큰의 다음 토큰을
          새로 낸다. 돌려주지 못한다고 끊으면 그 응답을 잃었던 사람이 로그아웃된다.
        - 하루가 안 됐으면 이 토큰을 그대로 돌려준다.
        - 그 사이 로그아웃 등으로 지워졌으면 None.

        이 토큰의 원문(key)이 있어야 한다. 인증을 거친 request.auth 에는 있다.

        옛 토큰은 여기서 끝내지 않는다. 새 토큰이 처음 쓰일 때 끝낸다(mark_delivered).
        여기서 끝내면 새 토큰을 실은 응답을 잃은 사람이 옛 토큰만 든 채 로그아웃된다.

        회원 행을 잠그고 본다(lock_member). 안 잠그면 동시에 온 이어 가기 둘이 새 토큰을
        하나씩 만들고, 로그아웃 같은 지우는 쪽과 겹치면 여기서 만든 새 토큰이 살아남는다.
        """
        with transaction.atomic():
            member = self.lock_member(self.user_id)
            if member is None:
                return None
            latest = (
                LoginToken.objects.filter(user_id=self.user_id, device=self.device)
                .order_by("-created", "-pk")
                .first()
            )
            if latest is None:
                return None
            if latest.pk != self.pk:
                renewed = self._renewed_as(latest)
                if renewed is not None:
                    return renewed
                # 이 토큰에서 계산되지 않는 새 토큰이다. 원문을 돌려줄 수 없어 이 토큰의 다음
                # 토큰을 낸다. created 가 더 늦은 쪽이 먼저 쓰이면 다른 쪽이 바뀐 것으로 적힌다
                # (mark_delivered 는 자기보다 created 가 이른 줄만 적는다).
            elif latest.created > timezone.now() - self.RENEW_AFTER:
                return self
            key = _next_login_token_key(self._own_key())
            # 이 토큰이 전에 낸 다음 토큰이 남아 있는데 latest 가 그 뒤 다른 갈래로 바뀌었을 수
            # 있다. 또 만들면 지문이 겹쳐 500 이 나므로 있는 것을 돌려준다. 그것이 이미 바뀐
            # 것으로 적힌 토큰이면 유예 뒤 그 로그인이 끊긴다. 서버 비밀 키를 바꿨다 되돌린
            # 뒤 한 시간 안에 요청이 엇갈려야 생기는 일이라 그대로 둔다.
            made = LoginToken.objects.filter(
                user_id=self.user_id, device=self.device, digest=token_digest(key)
            ).first()
            if made is not None:
                made.key = key
                return made
            return LoginToken.objects.create(
                user_id=self.user_id, device=self.device, delivered=False, key=key
            )

    def _own_key(self) -> str:
        # 원문 없이 계산하면 salted_hmac 이 None 을 "None" 으로 바꿔 엉뚱한 값을 낸다.
        if self.key is None:
            raise ValueError("토큰 원문이 없다. 발급하거나 인증한 객체로 불러야 한다.")
        return self.key

    def _renewed_as(self, latest: LoginToken) -> LoginToken | None:
        """latest 가 이 토큰에서 이어 받은 것이면 원문을 채워 돌려준다. 아니면 None.

        보통은 한 단계 뒤다. 이어 받은 토큰이 하루 넘게 안 쓰이다가 쓰이자마자 또 이어
        받으면, 그 직후 유예 안에 온 이 토큰과 두 단계가 벌어질 수 있다. 이어 받기는 하루에
        한 번이라 발급 30일 안의 단계 수만큼만 본다. renew 의 "계산되지 않는 새 토큰" 갈래는
        하루를 기다리지 않지만, 그 갈래가 30일 안에 서른 번 넘게 엇갈릴 일은 없다.
        """
        key = self._own_key()
        for _ in range(self.LIFETIME // self.RENEW_AFTER + 1):
            key = _next_login_token_key(key)
            if token_digest(key) == latest.digest:
                latest.key = key
                return latest
        return None

    def mark_delivered(self) -> None:
        """renew 가 만든 이 토큰이 처음 쓰였다. 같은 로그인의 앞 토큰들을 바뀐 것으로 적는다.

        인증이 부른다. 받은 쪽이 이 토큰을 들고 왔으니 새 쿠키가 들어간 것이다. 두 요청이
        동시에 와도 replaced_at 이 빈 행만 고치므로 처음 시각이 남는다.
        """
        LoginToken.objects.filter(
            user_id=self.user_id,
            device=self.device,
            created__lt=self.created,
            replaced_at__isnull=True,
        ).update(replaced_at=timezone.now())
        LoginToken.objects.filter(pk=self.pk).update(delivered=True)
        self.delivered = True
