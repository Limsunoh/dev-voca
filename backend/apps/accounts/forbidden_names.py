"""쓸 수 없는 이름.

이름은 순위표에서 다른 회원에게 그대로 보인다. 욕설, 운영자 행세, 광고용
주소와 연락처를 이메일 가입, 이름 변경, 구글 첫 가입에서 거른다.

완벽한 거름망이 아니다. 글자를 조금만 바꿔도 빠져나가므로 약관에는 거름망에
걸린 이름만 바뀐다고 썼고, 모두 걸러진다고 쓰지 않았다. 빠져나간 이름은 관리자 화면에서 바꾼다. 그래서
애매하면 통과시키는 쪽으로 둔다. 잘못 막으면 회원은 자기 이름이 왜 안 되는지
알 길이 없다.
"""

from __future__ import annotations

import re
import unicodedata

# 한글 채움 문자. 글자로 분류돼 구분자로 안 잡히는데 화면에서는 빈칸으로
# 보여서, 금칙어 사이에 끼우면 그대로 통과한다. 보이는 대로 공백으로 다룬다.
# NFKC 뒤에는 이 둘만 남는다.
_FILLERS = re.compile("[\u115f\u1160]")


def _normalize(value: str) -> str:
    """전각 글자를 반각으로, 한글 채움 문자를 공백으로. 대소문자는 둔다."""
    return _FILLERS.sub(" ", unicodedata.normalize("NFKC", value))


def _fold(value: str) -> str:
    """전각 글자와 대소문자 차이를 없앤다. ＡＤＭＩＮ 이 admin 과 같아진다."""
    return _normalize(value).casefold()


# 이름 어디에 들어 있어도 막는 말.
_ANYWHERE = tuple(
    _fold(word)
    for word in (
        # 운영자 행세
        "운영자 운영진 운영팀 관리자 어드민 "
        # 연락처로 부르는 말
        "카톡 카카오톡 kakaotalk 오픈채팅 오픈톡 텔레그램 telegram "
        # 욕설
        "씨발 씨빨 씨팔 시팔 쓰발 시발 좆 좃 개새끼 개색끼 개세끼 개섀끼 씹새 십새끼 "
        "병신 븅신 지랄 미친놈 미친년 썅 창녀 느금마 니애미 엠창 섹스 "
        "ㅅㅂ ㅆㅂ ㅂㅅ ㅄ ㅈㄹ ㅈㄴ fuck asshole nigger nigga"
    ).split()
)

# 띄어 써도 뜻이 같은 말. 이것만은 "dev voca", "공식 계정" 처럼 낱말 사이를
# 띄워도 막는다. 서비스 이름은 옛 이름 devvoca(dev-voca 도 여기 걸린다)와
# 데브보카, 지금 이름의 한글 표기 데보카 다.
_EVEN_SPACED = ("devvoca", "데브보카", "데보카", "공식계정", "고객센터")

# 지금 이름 DeVoca. 위처럼 구분자를 다 지우고 찾으면 "code vocab" 이 "codevocab"
# 이 되어 devoca 를 품는다. 단어장 앱이라 vocab 이 든 별명이 흔하다. 그래서
# 낱말 하나로 떨어져 있을 때만 막는다. 대소문자를 살린 값에서 본다.
# - 앞: 영문자가 없거나, 소문자 바로 뒤의 대문자 D. OfficialDeVoca 는 막고
#   CodeVocab, codevocab 은 둔다.
# - 뒤: 끝 글자 a 와 대소문자가 같은 영문자가 붙지 않아야 한다. DeVocaTeam,
#   DEVOCAteam 은 막고 dev_ocaml, devocalize, DEV_OCAML, DEVOCALIZE 는 둔다.
# 같은 대소문자로 붙여 쓴 사칭은 빠져나간다: officialdevoca, OFFICIALDEVOCA,
# TEAMDEVOCA, DeVocateam. 막으려면 낱말 목록이 있어야 해서 두었다.
_CURRENT_NAME = re.compile(
    r"(?:(?<![A-Za-z])[Dd]|(?<=[a-z])D)(?i:[\W_]*e[\W_]*v[\W_]*o[\W_]*c[\W_]*a)"
    r"(?:(?<=a)(?![a-z])|(?<=A)(?![A-Z]))"
)

# 위의 말을 품고 있지만 뜻이 다른 낱말. 찾기 전에 먼저 지운다.
_HARMLESS = (
    "시발점",
    "시발역",
    "운영자금",
    "운영자동화",
    "운영자원",
    "운영자산",
    "운영자료",
    "관리자금",
    "관리자동화",
    "관리자원",
    "관리자산",
    "관리자료",
    "관리자격",
)

# 다른 낱말 안에 흔히 들어 있어 어디서나 찾으면 안 되는 말. badminton 의
# admin, class 의 ass, yoshitaka 의 shit, bitchat 의 bitch 가 그렇다.
#
# 영어는 낱말 하나가 같으면 막는다. 한글은 이름 전체가 같을 때만 막는다.
# 띄어쓰기로 낱말을 가르면 "새끼 손가락", "보지 마", "미친 코딩" 이 걸린다.
_WHOLE_WORDS = frozenset(
    _fold(word)
    for word in (
        "admin administrator bitch shit ass cunt dick cock pussy slut sex porn "
        "보지 자지 존나 새끼 이새끼 미친 씹"
    ).split()
)

# 숫자나 한글이 붙어도 영어 낱말은 따로 본다. admin1, admin님 도 admin 이다.
_LATIN_WORDS = re.compile(r"[a-z]+")

# 주소와 이메일. 끝자리 목록에 io, dev, app, ai, me 를 넣지 않은 것은 개발자
# 별명과 겹쳐서다(socket.io, kim.dev). 같은 이유로 asp.net 등은 뺀다. 점 뒤가
# 없는 root@dev 같은 프롬프트 꼴도 이메일로 보지 않는다.
_ADDRESS = re.compile(
    r"https?:|www\.|닷컴|\bt\.me/|\w@\w+\.\w"
    r"|\w\.(?:com|org|kr|xyz|shop|site|link|ly|gg"
    r"|(?<!\basp\.)(?<!\bvb\.)(?<!\bado\.)(?<!\bdot\.)net)(?![a-z0-9])"
)

# 0 으로 시작하는 전화번호. 구분자를 다 뺀 값에서 찾는다. 8자리 생년월일
# (kim19990101)은 0 으로 시작하지 않아 걸리지 않는다.
_PHONE = re.compile(r"(?<!\d)0\d{8,10}(?!\d)")

_ALL_SEPARATORS = re.compile(r"[\W_]+")
_PUNCTUATION = re.compile(r"[^\w\s]|_")

# 한 글자 조각 옆의 공백만 없앤다. "운 영 자" 는 붙이고 "다시 발전" 은 둔다.
# 공백을 다 지우면 없던 낱말이 생겨 멀쩡한 이름이 막히고("시발"), 예외 낱말이
# 잘못 지워져 사칭이 빠져나간다("운영자 원빈" 의 "운영자원").
_SPREAD_SPACE = re.compile(r"(?<!\w\w)\s+|\s+(?!\w\w)")


def _close_gaps(value: str) -> str:
    """문장부호를 지우고 한 글자씩 띄운 공백을 붙인다.

    문장부호를 지우면 공백이 두 칸이 될 수 있어 한 칸으로 모은다. 안 그러면
    "다시 - 발전" 이 "다시발전" 으로 붙는다.
    """
    return _SPREAD_SPACE.sub("", " ".join(_PUNCTUATION.sub("", value).split()))


def name_is_forbidden(name: str) -> bool:
    """이름으로 쓸 수 없으면 True."""
    folded = _fold(name)
    squeezed = _ALL_SEPARATORS.sub("", folded)

    if {_close_gaps(folded), *_LATIN_WORDS.findall(folded)} & _WHOLE_WORDS:
        return True
    if _ADDRESS.search(folded) or _PHONE.search(squeezed):
        return True
    if any(word in squeezed for word in _EVEN_SPACED):
        return True
    if _CURRENT_NAME.search(_normalize(name)):
        return True

    # 구분자를 없애기 전에 지운다. 없앤 뒤에 지우면 "관리자 금", "운영자.원빈" 이
    # 예외 낱말로 바뀌어 빠져나간다.
    for word in _HARMLESS:
        folded = folded.replace(word, "")
    text = _close_gaps(folded)
    return any(word in text for word in _ANYWHERE)
