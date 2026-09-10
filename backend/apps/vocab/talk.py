"""소리내어 읽기(일상영어) 출제와 채점.

## 무엇을 재는가 - 먼저 읽을 것

**이 채점기는 발음이 아니라 철자를 잰다.** 브라우저 음성 인식이 음소가
아니라 글자를 돌려주기 때문이다. 그래서 정확히는 "발음이 맞았는가" 가
아니라 **"인식기가 그 단어로 알아들었는가"** 를 잰다.

드러나는 방식이 양쪽이다.

    발음이 맞는데 실패    cash 를 정확히 읽었으나 정답이 cache 일 때
                          (소리는 거의 같고 철자가 다르다. 유사도 0.67)
    발음이 틀린데 통과    인식기가 정답 단어로 추측해버릴 때

진짜 발음 평가는 음소 단위 채점이 필요하고, 그것은 음성을 서버로 보내
전용 API 를 붙여야 한다(비용·저장소·개인정보가 모두 새 문제가 된다).
사용자가 이 한계를 알고 안고 가기로 결정했다(2026-09-10).

**그래서 화면 문구가 "정답/오답" 이 아니라 "잘 읽었어요/다시 해볼까요"
쪽이다.** 판정이 확실하지 않은데 단정하면 신뢰를 잃는다.

## 음성은 서버로 오지 않는다

브라우저가 음성을 텍스트로 바꿔 그 **텍스트만** 보낸다. 음성 파일이
서버에 없으므로 저장소·비용·생체정보 문제가 생기지 않고, Claude API 를
부르지 않으므로 CLAUDE.md 의 "사용자 요청 경로에서 AI 호출 금지" 와도
부딪히지 않는다.

대가로 서버가 알 수 없는 것이 있다. **"소리는 났는데 인식이 실패한 것"
과 "아무 소리도 안 난 것" 을 구분할 수 없다** - 양쪽 다 빈 배열로 온다.
그 구분은 화면이 인식기의 에러 코드로 한다.
"""

from __future__ import annotations

import difflib
import re

from django.core import signing

# 낱말 하나를 통째로 비교할 때 통과로 볼 유사도.
#
# 표본 17건으로 정한 값이고 오판은 0 이었지만 **여유가 좁다.**
#
#     deployed  vs deploy   0.86  통과
#     employ    vs deploy   0.83  실패    <- 0.03 차이
#     catch     vs cache    0.80  실패
#
# 그리고 비율 기반이라 **글자 수에 따라 엄격도가 달라진다.** 한 글자만
# 달랐을 때 통과하는지가 길이로 갈린다.
#
#     3글자 0.67 실패      7글자  0.86 통과
#     4글자 0.75 실패      8글자  0.88 통과
#     5글자 0.80 실패     10글자  0.90 통과
#     6글자 0.83 실패     14글자  0.93 통과
#
# 경계가 정확히 7글자이고, 출제 대상 361개 중 102개(28%)가 7글자 미만이다.
# 즉 짧은 낱말은 사실상 완전일치를 요구하고 긴 낱말은 한 글자를 봐준다.
#
# **의도한 것이다.** git/get, log/lag 처럼 짧을수록 한 글자가 다른 낱말이
# 되므로, 봐주면 틀린 발음이 통과한다. 반대로 꼬리가 붙는 변형은 짧아도
# 통과한다(log/logs 0.86) - 글자를 더하는 것이 바꾸는 것보다 비율을 덜
# 깎기 때문이고, 인식기가 흔히 내는 변형이라 안 막히는 것이 좋다.
#
# 고치려면 실사용 로그를 보고 정해야 한다. 위 표를 보고 "짧은 것이 빡빡
# 하다" 만으로 낮추면 틀린 발음이 통과하기 시작한다.
SIMILARITY = 0.85

# 인식 후보를 몇 개까지 볼지.
#
# 상한을 두는 이유: 후보를 잔뜩 채워 보내 안내 문구를 떠보는 통로가 된다.
# 화면도 maxAlternatives = 5 로 맞춰 보낸다.
MAX_ALTERNATIVES = 5

# 후보 하나의 길이 상한.
#
# 낱말이나 짧은 표현이 올 자리다. 최장 정답이 22글자라 네 배 이상 여유다.
#
# 자르지 않고 400 으로 막는다. 잘라서 채점하면 사용자는 왜 틀렸는지 모른다.
#
# 참고로 이 제한은 계산량 때문이 아니다. difflib 비용은 짧은 쪽에 지배돼
# 실측이 거의 선형이었다(10만자 5개에 71ms). 단어 하나가 올 자리에 10만자가
# 오는 것 자체가 정상 요청이 아니라서 막는다.
MAX_HEARD_LENGTH = 100


def normalize(said: str) -> str:
    """비교하기 전에 다듬는다.

    인식기가 대소문자·구두점을 제멋대로 준다. "Cache." 와 "cache" 를
    다르다고 판정하면 제대로 읽은 사람이 계속 실패한다.

    낱말 사이 공백은 남긴다 - 표현은 낱말 단위로 채점하므로 그 경계가
    필요하다.
    """
    lowered = said.lower().strip()
    # **아포스트로피는 공백이 아니라 삭제다.** 축약형이 한 낱말이기
    # 때문이다 - 공백으로 바꾸면 "what's" 가 두 조각이 되어 낱말 수가
    # 어긋나고, wrong_at 이 자리를 못 짚는다(None 으로 떨어진다).
    #
    # 없애면 "what's up" 과 "whats up" 이 같은 두 낱말이 되어, 인식기가
    # 아포스트로피를 빼고 적어도 자리까지 정확히 나온다. 곧은 따옴표와
    # 둥근 따옴표를 다 본다 - 인식기가 둥근 것을 주는 경우가 있다.
    lowered = re.sub(r"['’]", "", lowered)
    # 나머지 기호는 공백으로. 하이픈이 여기 걸린다 - blue-green 을
    # "blue green" 으로 읽는 것이 정상이고 인식기도 그렇게 준다.
    stripped = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


def _flat(said: str) -> str:
    """공백까지 없앤 형태. 낱말 경계만 다른 경우를 보는 데 쓴다."""
    return normalize(said).replace(" ", "")


def _close(said: str, answer: str) -> bool:
    """낱말 하나가 정답에 가까운가."""
    a, b = _flat(said), _flat(answer)
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIMILARITY


def grade_one(said: str, answer: str) -> tuple[bool, list[int] | None]:
    """인식 결과 하나를 정답과 견준다.

    돌려주는 것:
        통과했는가
        어긋난 낱말의 자리(0부터). 자리를 짚을 수 없으면 None

    **낱말 수를 먼저 본다.** 통째로 비교하면 낱말이 빠져도 통과한다 -
    "How was your weekend" 에 "Hows your weekend" 를 대면 0.94 다. 표현
    연습에서 낱말을 빼먹고 통과하면 안 된다.

    낱말 수가 다르면 공백을 없애고 **완전히 같은지만** 본다. 살리려는
    것이 인식기가 낱말 경계를 다르게 잡은 경우인데(restroom -> "rest
    room", "thank you" -> thankyou), 그건 공백을 없애면 글자가 똑같아진다.

    여기에 유사도 문턱을 두면 안 된다. 0.95 로 열어봤더니 **관사가 빠진
    것이 통과했다** - "can I get a refill" 에 "can I get refill" 이
    0.963 이다. 한 글자짜리 낱말은 공백을 없앤 뒤 비율을 거의 안 깎는다.
    완전 일치가 더 좁으면서 살리려던 것을 다 살린다(아홉 경우로 확인).

    잃는 것 하나: 낱말 경계가 어긋나면서 동시에 오인식이 난 경우
    ("rest rooms")는 어느 경로로도 안 걸린다. 드물고, 놓치는 편이 관사
    빠진 것을 통과시키는 것보다 낫다 - 낱말을 빼먹고 통과하는 것이 더
    나쁜 실패라는 원칙을 따른다.
    """
    said_words = normalize(said).split()
    answer_words = normalize(answer).split()

    if len(said_words) != len(answer_words):
        # 낱말 경계만 다른 경우만 살린다. 자리는 짚을 수 없다 - 경계가
        # 어긋난 상태라 몇 번째가 문제인지 정할 방법이 없다.
        # "Hows your weekend" 가 was 를 뺀 것인지 How was 를 뭉친 것인지
        # 개수만으로는 모른다.
        return (_flat(said) == _flat(answer)), None

    wrong = [
        i
        for i, (heard_word, answer_word) in enumerate(zip(said_words, answer_words))
        if not _close(heard_word, answer_word)
    ]
    return (not wrong), wrong


# 출제 대상에서 빼는 것을 판정한다.
#
# **약어·숫자·기호는 소리로 채점할 수 없다.** 음성 인식이 음소가 아니라
# 글자를 돌려주기 때문이다. ACL 을 정확히 "에이 씨 엘" 로 읽어도 결과가
# "ACL"·"A C L"·"acl" 중 무엇일지 제각각이고, 401 은 "four oh one" 으로
# 올 수도 "401" 로 올 수도 있다. 문자열로 비교하면 **제대로 읽은 사람을
# 틀렸다고 판정한다.** 발음 연습에서 그건 최악이다 - 자기가 틀린 줄 알고
# 같은 것을 반복한다.
#
# 개발 용어 566개 중 205개가 여기 걸려 361개가 남는다.
#
# **이 규칙은 세 번 고쳐졌다. 고쳐진 이유를 적어둔다.**
#
#   1차: 낱말 전체가 대문자인지만 봤다 -> `API key` 가 통과했다.
#        일부 낱말만 약어인 것을 놓쳤다(7개).
#   2차: 낱말 단위로 봤지만 "2글자 이상 대문자" 로 뒀다 -> `I/O`·`big O`
#        가 통과했다. 구분자로 쪼개면 낱개 대문자 한 글자가 된다.
#   3차: 낱말이 여러 개면 1글자 대문자도 약어로 본다. 지금 이 규칙.
#
# **두 번 다 규칙을 읽어서가 아니라 통과 목록을 눈으로 봐서 잡혔다.**
# 그래서 놓쳤던 표본이 테스트에 박혀 있다(tests_talk.py). 규칙을 고치려면
# 그 테스트를 먼저 보라.
#
# 앞으로 걸릴 축이 하나 더 있다. **철자와 발음이 갈리는 도구 이름**이다 -
# kubectl("cube control")·nginx("engine x")·sudo("pseudo") 는 소문자
# 낱말이라 이 그물에 안 걸리는데, 제대로 읽어도 인식기가 소리 나는 대로
# 적어서 유사도가 무너진다. 지금 풀에는 없다. 나오면 규칙을 늘리지 말고
# 아래 목록에 이름을 적는 편이 싸다.
_MANUAL_EXCLUDE: frozenset[str] = frozenset()

# 한 글자인데 철자로 읽지 않고 낱말로 읽는 것.
#
# 아래 규칙이 "낱말이 여러 개면 1글자 대문자도 약어" 로 보는데, 그것은
# `big O`("빅 오")·`I/O`("아이 오") 를 잡으려고 넣은 조건이다. 그런데
# 일상 표현의 **대명사 I** 가 같은 모양이라 함께 걸린다 - "I am lost",
# "I would like to order" 처럼 60개 중 10개가 여기 걸렸다.
#
# I 는 철자를 읽는 것이 아니라 낱말 "아이" 로 읽으므로 인식 결과가
# 흔들리지 않는다.
#
# **관사 A 는 넣지 않는다.** 같은 성질이라 처음에는 함께 넣었는데, 지금
# 표현 60개 중 홀로 선 A 가 있는 것이 하나도 없다. 반면 넣으면 `plan A`·
# `grade A`·`A record` 가 통과하는데, 그것들은 `plan B`·`big O` 와 같은
# 부류라 제외되어야 한다. 쓰지도 않으면서 구멍만 여는 셈이다.
#
# 홀로 선 A 가 필요한 표현이 생기면 그때 넣고 테스트를 함께 붙인다.
#
# **이 예외가 big O 를 되살리지 않는 것을 확인했다** - O 는 목록에
# 없으므로 여전히 제외된다.
_READ_AS_WORD = frozenset({"I"})

_HAS_DIGIT = re.compile(r"\d")
# 낱말 구분자로 쓰는 것 외의 기호. 하이픈과 슬래시는 낱말을 나누는 데
# 쓰므로 여기서 빼고, 아래 낱말 검사가 각 조각을 본다.
#
# **아포스트로피도 뺀다.** 축약형("what's up"·"how's it going")이 일상
# 영어의 큰 몫인데, 막으면 검수를 해도 출제가 안 되고 관리자는 이유를
# 모른다. normalize 가 아포스트로피를 없애 한 낱말로 다루므로 채점도 된다.
_HAS_SYMBOL = re.compile(r"[^\w\s\-/'’]")
_WORD_SPLIT = re.compile(r"[\s\-/]+")
_LETTERS = re.compile(r"[^A-Za-z]")


def is_speakable(text: str) -> bool:
    """소리로 채점할 수 있는 항목인가."""
    if text in _MANUAL_EXCLUDE:
        return False
    if _HAS_DIGIT.search(text) or _HAS_SYMBOL.search(text):
        return False

    words = _WORD_SPLIT.split(text)
    for word in words:
        letters = _LETTERS.sub("", word)
        if not letters:
            continue
        # 낱말로 읽는 한 글자(대명사 I, 관사 A)는 넘어간다. 위 주석 참고.
        if letters in _READ_AS_WORD:
            continue
        # 낱말이 전부 대문자면 철자로 읽는 약어다.
        #
        # 낱말이 하나뿐일 때만 2글자 이상을 요구한다. 여러 낱말이면
        # 1글자짜리도 약어로 본다 - `I/O` 의 I·O, `big O` 의 O 가 그렇다.
        # 이 조건이 없으면 그 둘이 통과한다(2차 정정 사유).
        if letters.isupper() and (len(letters) >= 2 or len(words) > 1):
            return False
    return True


# 토큰 소금. quiz 와 다른 값을 쓴다.
#
# 같은 소금을 쓰면 문제풀기 토큰을 여기로, 여기 토큰을 문제풀기로 보낼 수
# 있다. 서명이 유효하니 통과하고, 그다음은 각자 알맹이를 자기 방식으로
# 해석해 엉뚱한 것을 정답이라고 판정한다 - 실제로 단어·문장 채점에서
# 같은 소금을 공유해 그런 구멍이 났던 자리다(views.py 의 WordViewSet.grade
# 가 answer_type 을 검사하는 이유).
_SALT = "vocab.talk.answer"

# 토큰 유효 시간(초). quiz 와 같은 30분.
#
# 발음 연습은 한 항목을 여러 번 시도하므로 짧으면 중간에 끊긴다.
TOKEN_MAX_AGE = 30 * 60

# 무엇을 읽는 문제인가. 채점할 때 어느 표에서 정답을 찾을지 정한다.
#
# 이 값이 토큰에 없으면 id 가 같은 엉뚱한 행을 정답이라고 띄운다 -
# quiz.py 가 answer_type 을 담는 것과 같은 이유다.
KIND_WORD = "word"
KIND_PHRASE = "phrase"


def sign(item_id: int, kind: str) -> str:
    """채점 정보를 토큰으로 만든다.

    **정답 텍스트를 담지 않고 id 만 담는다.** signing.dumps 는 위조를
    막을 뿐 내용을 숨기지 않아서, base64 로 풀면 담은 것이 그대로 보인다.
    정답 텍스트를 담으면 마이크를 켜지 않고도 답을 읽을 수 있다.

    quiz.py 는 정답 id 조차 지문(HMAC)으로 바꿔 담는데, 여기는 그럴 필요가
    없다. 그쪽은 보기 넷 중 무엇이 정답인지를 감춰야 하지만, 여기는 애초에
    보기가 없다 - id 를 알아도 그 단어가 무엇인지는 모른다.

    **다만 id 를 알면 목록 API 로 그 항목을 조회할 수 있다.** 발음 연습에서
    답을 미리 보는 것은 시험이 아니라 연습이라 손실이 작고, 감추려면
    지문을 쓰고 후보를 대조해야 하는데 여기는 대조할 후보가 없다.
    점수·순위표에 안 들어가는 것이 이 판단의 근거다 - 나중에 점수를
    붙이면 이 자리를 다시 봐야 한다.
    """
    return signing.dumps({"i": item_id, "k": kind}, salt=_SALT)


def unsign(token: str) -> tuple[int, str] | None:
    """토큰에서 (항목 id, 종류). 위조·만료·형식 오류면 None.

    예외를 삼키고 None 을 주는 이유: 여기서 올라가면 500 이 된다.
    토큰이 상한 것은 서버 잘못이 아니라 오래된 화면이 보낸 것이라,
    사용자에게 "새 문제를 받아주세요" 로 안내해야 한다.
    """
    try:
        payload = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    item_id, kind = payload.get("i"), payload.get("k")
    # bool 을 빼는 이유는 quiz.py 와 같다 - 파이썬에서 True 는 int 라
    # id 1 번으로 처리된다.
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        return None
    if kind not in (KIND_WORD, KIND_PHRASE):
        # 모르는 종류면 어느 표를 볼지 정할 수 없다. 단어로 떨어뜨리면
        # 표현 토큰이 단어 표에서 채점된다.
        return None

    return item_id, kind


def clean_heard(raw: object) -> list[str] | None:
    """화면이 보낸 인식 후보를 다듬는다. 형식이 틀리면 None.

    빈 목록은 정상이다 - 아무 소리도 안 났거나 인식이 실패한 경우이고,
    그것도 채점 결과("안 들렸다")가 있어야 한다. 400 으로 막으면 화면이
    그 상태를 그릴 수 없다.

    길이 초과는 자르지 않고 None(400)이다. 잘라서 채점하면 사용자는
    왜 틀렸는지 모른다.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None

    # **빈 문자열을 먼저 걷어내고 그다음에 상한을 적용한다.** 순서가
    # 중요하다 - 슬라이스를 먼저 하면 앞에 온 빈 값이 실제 후보를 밀어낸다.
    #
    #     ["", "", "", "", "", "cache"] -> 앞 다섯만 보고 전부 버려서
    #     결과가 빈 목록이 되고, 채점이 "소리가 안 들렸어요" 로 나간다.
    #
    # 사용자는 cache 를 정확히 읽었는데 원인 모르는 안내를 받는다. 인식기가
    # 빈 결과를 배열에 담는 경우가 있어서 실재하는 입력이다.
    #
    # 길이·형식 검사는 걷어내기 전에 전부 본다. 상한 뒤로 밀린 것에 이상한
    # 값이 있어도 막아야 한다 - 슬라이스 뒤에만 검사하면 여섯 번째에
    # 10만자를 넣어 검사를 건너뛸 수 있다.
    cleaned: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        if len(item) > MAX_HEARD_LENGTH:
            return None
        if item.strip():
            cleaned.append(item)

    # 상한을 넘는 것은 버린다. 후보를 잔뜩 채워 보내 안내를 떠보는 통로가
    # 되는 것을 막는다.
    return cleaned[:MAX_ALTERNATIVES]


def grade(heard: list[str], answer: str) -> dict:
    """인식 후보들을 채점해 화면이 쓸 모양으로 돌려준다.

    **통과 판정은 1등 후보만 본다.** 후보 전체를 보면 "잘 읽었는데 1등이
    엉뚱한 경우" 와 "잘못 읽었는데 2등에 정답이 뜬 경우" 가 구분되지
    않는다 - 둘 다 "정답이 아래 후보에 있다" 는 같은 모양이다. 규칙 넷을
    시험했는데 전부 두 건씩 오판했다.

        ["cash","cache"]      정답 cache    잘 읽음        1등만=실패
        ["employ","deploy"]   정답 deploy   잘못 읽음      1등만=실패

    신뢰도로 가르는 것도 안 된다 - Chrome 에 SpeechRecognitionAlternative
    프로토타입이 노출되지 않아 그 값이 실제로 오는지 실측할 수 없다.

    발음 연습에서는 **틀린 발음을 통과시키는 쪽이 더 나쁜 실패**라 좁게
    잡았다. 2등 이하는 판정에 안 쓰고 near 안내에만 쓴다.
    """
    if not heard:
        # 서버는 "소리가 안 났다" 와 "인식이 실패했다" 를 구분할 수 없다.
        # 텍스트만 오기 때문이다. 화면이 인식기 에러 코드로 가른다.
        return {
            "ok": False,
            "reason": "not_heard",
            "heard": [],
            "answer": answer,
            "near": None,
            "wrong_at": None,
        }

    ok, wrong_at = grade_one(heard[0], answer)

    # 2등 이하에 정답이 있으면 알려준다. "cash 로 들렸어요. 혹시 cache 를
    # 말하셨나요?" 를 그릴 수 있다 - 인식이 애매했다는 것을 사용자가 알면
    # 같은 발음을 반복하지 않는다.
    #
    # 통과했으면 볼 필요가 없다.
    near = None
    if not ok:
        for candidate in heard[1:]:
            if grade_one(candidate, answer)[0]:
                # 인식기 표기가 아니라 정답 표기를 준다. 사용자가 배워야
                # 할 철자여야 한다.
                near = answer
                break

    return {
        "ok": ok,
        "reason": "pass" if ok else "mismatch",
        # 정규화한 값을 준다. 화면은 원문을 자기가 들고 있다 - "Cache." 를
        # "cache" 로 바꿔 보여주면 사용자가 자기가 말한 것과 다르게 느낀다.
        "heard": [normalize(said) for said in heard],
        "answer": answer,
        "near": near,
        # 어긋난 낱말의 자리. [] 는 통과(어긋난 자리 없음), None 은 낱말
        # 수가 달라 자리를 짚을 수 없다는 뜻이다. **둘을 뭉치면 안 된다** -
        # 화면이 "통과" 와 "실패인데 못 짚음" 을 구분할 수 없어진다.
        "wrong_at": wrong_at,
    }


# 화면이 갈래를 고르는 쿼리 값. 없으면 일상 표현이 기본이다.
#
# 탭 이름이 "일상영어" 라 그쪽이 기본이어야 한다. 개발 용어는 명시적으로
# 골라야 나온다.
KIND_DEV = "dev"
