"""문제 출제.

정답 하나와 오답 셋을 골라 문제 하나를 만든다.

출제를 백엔드에서 하는 이유:
    - 오답을 프론트에서 뽑으려면 566개를 통째로 받아야 한다.
    - 정답을 응답에 담아 보내면 사용자가 개발자도구로 미리 본다.
      채점은 별도 요청(grade)으로 받는다.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import random
import re
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.db.models import QuerySet

from .models import Sentence, Word

# 정답이 무엇을 가리키는지. 채점한 뒤 무엇을 보여줄지 정하는 데 쓴다.
TARGET_WORD = "word"
TARGET_SENTENCE = "sentence"

# 보기 개수. 4지선다.
CHOICE_COUNT = 4

# 서명 용도 구분자. 다른 곳에서 만든 서명을 여기서 풀지 못하게 막는다.
# 값을 바꾸면 이미 발급된 토큰이 전부 무효가 된다(풀던 문제가 깨진다).
_SALT = "vocab.quiz.answer"

# 토큰 유효 시간(초). 한 문제를 푸는 데 30분이면 넉넉하다.
# 무제한으로 두면 어제 받은 토큰으로 오늘도 채점된다.
TOKEN_MAX_AGE = 30 * 60


def _fingerprint(answer_id: int, nonce: str) -> str:
    """정답 id 를 되돌릴 수 없는 값으로 바꾼다.

    문제마다 다른 nonce 를 섞기 때문에, 같은 단어라도 문제가 다르면
    지문이 달라진다. nonce 가 없으면 "정답이 42인 문제" 의 지문이 항상
    같아서, 한 번 알아낸 값을 계속 대조할 수 있다.
    """
    msg = f"{answer_id}:{nonce}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def answer_payload(answer_id: int, choice_ids: list[int]) -> dict:
    """문제 하나의 채점 정보. 서명하기 전의 알맹이다.

    정답 id 를 그대로 담지 않는다. signing.dumps 는 위조를 막을 뿐
    내용을 숨기지 않아서, base64 로 풀면 값이 그대로 보인다.

    담는 것:
        a - 정답의 지문(HMAC). 되돌릴 수 없다
        n - 문제마다 다른 값. 같은 정답이라도 지문이 달라진다
        c - 보기 id 넷. 채점 후 정답을 찾는 데 쓴다

    보기 id 는 어차피 응답에 그대로 나가 있으므로 담아도 새는 정보가 없다.
    그 넷 중 무엇이 정답인지가 감춰지면 된다.

    서명과 분리해 둔 이유: 판(세션)은 이 알맹이를 자기 토큰 안에 넣어
    한 번만 서명한다. 토큰 안에 토큰을 넣으면 길이가 배로 늘어난다.
    """
    # random 이 아니라 secrets 를 쓴다. random 은 Mersenne Twister 라
    # 출력을 충분히 모으면 다음 값을 예측할 수 있다.
    nonce = secrets.token_urlsafe(16)
    return {
        "a": _fingerprint(answer_id, nonce),
        "n": nonce,
        # 정렬해서 담는다. 화면에 보이는 보기 순서와 토큰 안의 순서가
        # 같으면 "몇 번째에 담긴 것이 정답" 같은 단서가 생길 수 있다.
        "c": sorted(choice_ids),
    }


def sign_question(answer_id: int, choice_ids: list[int]) -> str:
    """채점 정보를 그 자체로 하나의 토큰으로 만든다.

    문제를 하나씩 내주는 옛 경로(vocab 의 quiz/grade)가 쓴다.
    """
    return signing.dumps(answer_payload(answer_id, choice_ids), salt=_SALT)


def resolve_answer(payload: dict, picked_id: int) -> tuple[bool, int] | None:
    """(정답 여부, 정답 id). 알맹이가 망가졌으면 None.

    정답 id 는 보기 넷을 하나씩 대조해 찾는다. 지문에서 직접 꺼낼 수는
    없지만 후보가 넷뿐이라 금방 찾는다.
    """
    if not _valid_payload(payload):
        return None

    expected, nonce, choices = payload["a"], payload["n"], payload["c"]

    for cid in choices:
        # 타이밍 공격을 막는다. == 는 앞에서부터 비교해 다른 위치가 드러난다.
        if hmac.compare_digest(expected, _fingerprint(cid, nonce)):
            return cid == picked_id, cid

    # 알맹이는 정상인데 보기 중에 정답이 없다. 만들 수 없는 상태다.
    return None


def grade_answer(token: str, picked_id: int) -> tuple[bool, int] | None:
    """(정답 여부, 정답 id) 를 돌려준다. 토큰이 위조·만료면 None.

    실패를 예외로 올리지 않는 이유: 사용자가 보내는 값이라 잘못된 토큰이
    정상 경로다. 여기서 터뜨리면 500 이 되고, 호출부는 400 으로 답해야 한다.

    한계: 토큰은 유효 시간 안에서 몇 번이든 다시 채점할 수 있고, 채점은
    맞든 틀리든 정답을 알려준다. 즉 한 번만 불러도 정답을 알 수 있다.
    이 경로는 점수를 저장하지 않아 속여봐야 본인 화면 숫자만 바뀐다.
    점수가 걸린 판은 apps.learning 의 세션을 쓴다 - 거기서는 문제를
    하나씩만 내주고, 판 토큰이 다음 문제로 넘어가면서 앞 문제는 닫힌다.
    """
    payload = _load(token)
    if payload is None:
        return None
    return resolve_answer(payload, picked_id)


def _valid_payload(payload: object) -> bool:
    """채점 정보의 모양을 본다.

    서명이 유효해도 모양까지 맞다는 보장은 없다. SECRET_KEY 를 가진
    쪽(우리 코드)이 잘못 만들었을 수도 있고, 옛 형식의 토큰이 남아
    있을 수도 있다. 여기서 안 걸러내면 대조하는 자리에서 터진다.
    """
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("a"), str):
        return False
    if not isinstance(payload.get("n"), str):
        return False
    choices = payload.get("c")
    if not isinstance(choices, list) or not choices:
        return False
    return all(isinstance(cid, int) and not isinstance(cid, bool) for cid in choices)


def _load(token: str) -> dict | None:
    try:
        payload = signing.loads(token, salt=_SALT, max_age=TOKEN_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return None
    return payload if _valid_payload(payload) else None


class QuizKind:
    """문제 유형.

    화면에서 유형별로 묻는 말이 달라지므로 값을 프론트에도 내려준다.
    """

    MEANING = "meaning"  # 단어를 보여주고 뜻 고르기
    TERM = "term"  # 뜻을 보여주고 단어 고르기
    DESCRIPTION = "description"  # 설명을 보여주고 단어 고르기
    BLANK = "blank"  # 문장에서 용어를 가리고 맞히기
    SITUATION = "situation"  # 문장을 보여주고 나오는 상황 고르기

    WORD_KINDS = (MEANING, TERM, DESCRIPTION)
    SENTENCE_KINDS = (BLANK, SITUATION)
    ALL = WORD_KINDS + SENTENCE_KINDS

    LABELS = {
        MEANING: "뜻 고르기",
        TERM: "단어 고르기",
        DESCRIPTION: "설명 보고 맞히기",
        BLANK: "빈칸 채우기",
        SITUATION: "상황 고르기",
    }

    QUESTIONS = {
        MEANING: "이 단어의 뜻은?",
        TERM: "이 뜻에 해당하는 단어는?",
        DESCRIPTION: "이 설명에 해당하는 단어는?",
        BLANK: "빈칸에 들어갈 말은?",
        SITUATION: "이 말이 나오는 상황은?",
    }

    # 정답이 무엇을 가리키는지. 빈칸 문제는 문장을 보여주지만 답은 단어다.
    TARGETS = {
        MEANING: TARGET_WORD,
        TERM: TARGET_WORD,
        DESCRIPTION: TARGET_WORD,
        BLANK: TARGET_WORD,
        SITUATION: TARGET_SENTENCE,
    }


# 유형별 제한 시간(ms). 이 안에 맞히면 +1, 지나서 맞히면 0.
#
# 기준은 유형 이름이 아니라 **읽을 것의 길이**다. 지문이 단어 하나면 3초,
# 한 줄짜리 문장이면 7초. 설명 문제는 단어를 묻지만 지문이 문장이라
# 문장 쪽에 넣는다 - 3초로 두면 지문을 다 읽기도 전에 시간이 끝난다.
TIME_LIMITS_MS = {
    QuizKind.MEANING: 3000,
    QuizKind.TERM: 3000,
    QuizKind.DESCRIPTION: 7000,
    QuizKind.BLANK: 7000,
    QuizKind.SITUATION: 7000,
}


@dataclass
class Choice:
    """보기 하나."""

    id: int
    text: str


@dataclass
class Question:
    """문제 하나."""

    kind: str
    kind_label: str
    question: str
    prompt: str
    choices: list[Choice]
    answer_id: int
    category: str
    category_label: str

    # 정답 id 가 무엇의 id 인지. 채점 뒤 무엇을 보여줄지 여기서 갈린다.
    # 빈칸 문제는 문장을 보여주지만 답은 단어라 word 다.
    answer_type: str = TARGET_WORD

    # 이 안에 맞히면 +1, 지나서 맞히면 0. 화면이 막대로 그린다.
    time_limit_ms: int = 3000

    # 빈칸 문제를 낸 문장. 같은 문장을 연달아 내지 않으려고 들고 있다.
    # 정답(단어)과 다른 값이라 exclude 에 섞어 쓸 수 없다.
    source_sentence_id: int | None = None


def _pick_distractors(answer: Word, pool: QuerySet[Word], count: int) -> list[Word]:
    """오답 후보를 고른다.

    같은 분류에서 먼저 뽑는다. 아무 데서나 뽑으면 git 단어 문제에 DB 용어가
    섞여 답이 뻔해진다. 같은 분류가 모자라면 나머지로 채운다.
    """
    picked = list(
        pool.filter(category=answer.category)
        .exclude(pk=answer.pk)
        .order_by("?")[:count]
    )

    if len(picked) < count:
        # 분류가 작아서 모자란 경우. 이미 고른 것과 정답을 빼고 채운다.
        used = {answer.pk, *(w.pk for w in picked)}
        rest = list(pool.exclude(pk__in=used).order_by("?")[: count - len(picked)])
        picked.extend(rest)

    return picked


def _mask_term(description: str, term: str) -> str:
    """설명 안에 들어 있는 단어를 가린다.

    설명 문제는 설명을 보고 단어를 맞히는 것인데, 설명이 "API 는 ..." 처럼
    시작하면 답이 지문에 그대로 있다. 566개 중 25개가 그랬다 - 약어일수록
    설명에서 풀어 쓰다 보니 자연스럽게 섞인다.

    대소문자를 무시하는 이유: "REST" 를 설명에서 "Rest" 로 적은 경우가 있다.

    파생어까지 함께 가린다. "nit" 의 설명에 "nitpick 의 줄임말" 이 있으면
    단어만 정확히 맞춰서는 못 가린다. term 으로 시작하는 낱말은 통째로
    지운다 - nitpick, specification, RESTful, watchpoint 가 그런 경우다.
    반대쪽(term 이 낱말 중간에 있는 forget, Rapid)은 답과 무관하므로
    건드리지 않는다.

    약어는 원형도 가린다. "API" 의 설명이 "Application Programming
    Interface 의 줄임말" 로 시작하면, 단어를 가려도 머리글자만 읽으면
    답이 나온다. 566개 중 112개가 이런 모양이다.

    여러 낱말로 된 단어는 낱말별로도 가린다. "pull request" 를 통째로
    가려도 "merge request 라고도 부른다" 가 남으면 답이 보인다.

    해설은 가리지 않는다. 채점이 끝난 뒤에는 설명 원문을 그대로
    보여주므로 "무엇의 줄임말인가" 라는 학습 내용은 그대로 남는다.
    """
    if not term:
        return description

    # 단어 경계를 봐야 한다. 그냥 찾아 바꾸면 "GET" 이 "forget" 안까지
    # 가려서 "for____" 가 되고, 가려진 자리 모양이 오히려 힌트가 된다.
    #
    # \b 대신 (?<!\w) 를 쓰는 이유: term 이 "C++" 나 ".NET" 처럼 기호로
    # 시작하면 \b 의 판정이 뒤집힌다.
    # re.escape 는 그런 기호를 정규식 메타문자로 해석하지 않게 막는다.
    #
    # 뒤쪽은 \w* 로 열어둔다. 낱말 시작이 term 과 같으면 나머지 글자까지
    # 함께 지워야 "____pick" 처럼 파생어 꼬리가 남지 않는다.
    pattern = rf"(?<!\w){re.escape(term)}\w*"
    masked = re.sub(pattern, "____", description, flags=re.IGNORECASE)

    # isupper() 로 보면 안 된다. 모든 글자가 대문자여야 참이라
    # IaaS, PaaS, SaaS, IoC, npm 처럼 소문자가 섞인 약어가 다 빠진다.
    # 대문자가 둘 이상이면 약어로 본다.
    if " " not in term and sum(c.isupper() for c in term) >= 2:
        masked = _mask_expansion(masked, term)

    # 네 글자 이상만 보는 이유: "big O" 의 "big" 처럼 짧은 낱말은 설명
    # 어디에나 나와서, 가리면 문장을 읽을 수 없게 된다.
    if " " in term:
        for word in term.split():
            if len(word) >= 4:
                masked = re.sub(
                    rf"(?<!\w){re.escape(word)}\w*",
                    "____",
                    masked,
                    flags=re.IGNORECASE,
                )

    return masked


# 대문자로 시작하는 낱말이 둘 이상 이어진 덩어리. 약어의 원형은 대개
# 이 모양이다 - "Application Programming Interface" 나 "Role-Based
# Access Control" 처럼 하이픈으로 이어지기도 한다.
#
# 중간 낱말의 첫 글자를 소문자까지 허용하는 이유: "Proof of Concept"
# 처럼 연결어가 소문자인 원형이 있다. 시작과 끝은 대문자로 묶어
# 평범한 영어 문장이 통째로 걸리는 것을 막는다.
#
# 쉼표도 구분자로 본다: "Create, Read, Update, Delete" 처럼 나열로
# 적은 원형이 있다.
_SEP = r"(?:[ -]|,\s*)"
# 낱말 안에는 아포스트로피가 올 수 있다. "Don't Repeat Yourself"(DRY) 처럼
# 축약형이 들어간 원형이 있어, 여기서 끊기면 머리글자가 어긋난다.
_LETTERS = r"[A-Za-z]['’A-Za-z]*"
_EXPANSION = re.compile(
    rf"[A-Z]['’A-Za-z]*(?:{_SEP}{_LETTERS})*{_SEP}[A-Z]['’A-Za-z]*"
)


def _mask_expansion(description: str, term: str) -> str:
    """약어의 원형을 가린다. 머리글자가 약어와 같은 덩어리만 지운다.

    "SQL" 의 설명에 "Structured Query Language" 가 있으면 가리고,
    "Git Bash" 처럼 머리글자가 다른 덩어리는 그대로 둔다.

    머리글자를 두 가지로 세는 이유: 약어가 연결어를 빼고 만들어지는 경우가
    있다. "Redundant Array of Independent Disks" 는 of 를 빼야 RAID 가 되고,
    "Proof of Concept" 는 of 를 넣어야 POC 가 된다. 둘 중 하나라도 맞으면
    원형으로 본다.
    """

    def replace(match: re.Match) -> str:
        # 정규식이 "쉼표 뒤 임의 공백" 을 구분자로 보므로 여기서도 같아야
        # 한다. \s 를 빼면 줄바꿈이 낱말 앞에 붙어 머리글자가 어긋나고,
        # 마스킹이 조용히 안 걸린다.
        words = [w for w in re.split(r"[\s,-]+", match.group()) if w]
        all_initials = "".join(w[0] for w in words)
        # 소문자로 시작하는 낱말(of, and, the ...)을 뺀 머리글자
        major_initials = "".join(w[0] for w in words if w[0].isupper())

        target = term.upper()
        if all_initials.upper() == target or major_initials.upper() == target:
            return "____"
        return match.group()

    return _EXPANSION.sub(replace, description)


def _build(kind: str, answer: Word, distractors: list[Word]) -> Question:
    """유형에 맞춰 지문과 보기를 만든다."""
    if kind == QuizKind.MEANING:
        prompt = answer.term
        options = [Choice(w.pk, w.meaning) for w in [answer, *distractors]]
    elif kind == QuizKind.TERM:
        prompt = answer.meaning
        options = [Choice(w.pk, w.term) for w in [answer, *distractors]]
    else:
        prompt = _mask_term(answer.description, answer.term)
        options = [Choice(w.pk, w.term) for w in [answer, *distractors]]

    random.shuffle(options)

    return Question(
        kind=kind,
        kind_label=QuizKind.LABELS[kind],
        question=QuizKind.QUESTIONS[kind],
        prompt=prompt,
        choices=options,
        answer_id=answer.pk,
        category=answer.category,
        category_label=answer.get_category_display(),
        answer_type=QuizKind.TARGETS[kind],
        time_limit_ms=TIME_LIMITS_MS[kind],
    )


def make_question(
    pool: QuerySet[Word],
    kind: str | None = None,
    exclude_ids: list[int] | None = None,
) -> Question | None:
    """문제 하나를 만든다. 만들 수 없으면 None.

    kind 를 주지 않으면 매번 무작위로 고른다 - 같은 유형이 이어지면
    답을 외우지 않고 패턴을 외우게 된다.

    exclude_ids 는 방금 낸 문제를 다시 내지 않기 위한 것이다. 정답에만
    적용한다 - 오답 보기까지 빼면 최근 푼 만큼 보기 후보가 줄어드는데,
    같은 단어가 오답으로 다시 나오는 건 문제가 되지 않는다.
    """
    # WORD_KINDS 로 좁힌다. 이 함수는 단어만 만들 수 있는데, ALL 에는
    # 문장 유형(blank/situation)도 들어 있다. 그대로 두면 지문은 단어
    # 설명인데 묻는 말은 "이 말이 나오는 상황은?" 이 되고, 정답 종류가
    # sentence 로 붙어 나중에 엉뚱한 문장을 정답이라고 보여준다.
    kind = kind if kind in QuizKind.WORD_KINDS else random.choice(QuizKind.WORD_KINDS)

    candidates = pool.exclude(pk__in=exclude_ids) if exclude_ids else pool

    # 설명 문제는 설명이 있는 단어만 낼 수 있다.
    if kind == QuizKind.DESCRIPTION:
        candidates = candidates.exclude(description="")

    answer = candidates.order_by("?").first()
    if answer is None:
        return None

    distractors = _pick_distractors(answer, pool, CHOICE_COUNT - 1)
    if len(distractors) < CHOICE_COUNT - 1:
        # 보기를 채울 만큼 단어가 없다. 문제를 못 만든다.
        return None

    return _build(kind, answer, distractors)


# 빈칸 자리에 넣는 표시. 화면이 이 문자열을 찾아 칸으로 그린다.
BLANK_MARK = "____"

# 빈칸을 뚫고도 읽을 말이 남았는지 볼 때 쓴다.
_HAS_LETTER = re.compile(r"[A-Za-z]")


# 문장에서 용어를 찾을 때 쓰는 경계. 앞뒤가 알파벳이면 다른 단어의 일부다.
# "for" 가 "format" 안에서 잡히면 엉뚱한 자리에 빈칸이 뚫린다.
#
# 캐시가 필요한 이유: 한 문장을 검사할 때 단어 수만큼(566회) 부른다.
# 파이썬 re 모듈의 자체 캐시는 512개라 단어가 그보다 많으면 매번 밀려나
# 한 번도 안 맞는다. 컴파일을 다시 하느라 문장 하나에 174ms 가 들었다.
@functools.lru_cache(maxsize=2048)
def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE
    )


# 빈칸을 뚫을 때 쓰는 패턴. 찾기용(_term_pattern)과 달리 **뒤에 붙은 글자까지**
# 함께 지운다. 낱말이 정확히 같은 자리만 지우면 파생어가 답을 그대로 보여준다.
# 시드 380개 중 5개가 그랬다:
#   "IndexError: list ____ out of range"        (정답 index)
#   "RecursionError: maximum ____ depth ..."    (정답 recursion)
#   "____.decoder.JSONDecodeError: ..."         (정답 JSON)
# 설명 문제 쪽 _mask_term 이 이미 같은 이유로 \w* 를 쓰고 있다.
#
# 앞쪽은 열지 않는다. "for" 가 "format" 안에서 잡히면 엉뚱한 자리가 뚫린다.
@functools.lru_cache(maxsize=2048)
def _blank_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z]){re.escape(term)}\w*", re.IGNORECASE)


def _blank_out(text: str, term: str) -> str | None:
    """문장에서 용어가 나오는 자리를 모두 빈칸으로 바꾼다.

    못 찾거나, 다 지우고 나면 읽을 말이 안 남으면 None.
    호출부가 다른 문장으로 넘어간다.

    처음 하나만 바꾸지 않는 이유: 같은 용어가 두 번 나오는 문장에서 한쪽만
    지우면 남은 쪽이 정답을 그대로 보여준다. 실제 문장 12개가 그랬다.
    예: "____ prematurely closed connection ... from upstream"
    """
    replaced, count = _blank_pattern(term).subn(BLANK_MARK, text)
    if not count:
        return None

    # 문장이 용어 하나로만 이뤄져 있으면 단서가 없다. 예: 문장이 "upstream"
    if not _HAS_LETTER.search(replaced.replace(BLANK_MARK, " ")):
        return None

    return replaced


def _terms_in(text: str, terms: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """문장 안에 실제로 들어 있는 단어들.

    단어 566개를 전부 훑는다. 쿼리로는 "이 문장에 포함된 단어" 를 물을 수
    없어서(방향이 반대다) 파이썬에서 본다. 정규식은 위에서 캐시한다.
    """
    return [(pk, term) for pk, term in terms if _term_pattern(term).search(text)]


def make_blank_question(
    sentences: QuerySet[Sentence],
    words: QuerySet[Word],
    exclude_sentence_ids: list[int] | None = None,
) -> Question | None:
    """문장에서 용어 하나를 가리고 맞히는 문제.

    만들 수 없으면 None - 호출부가 다른 유형으로 넘어간다. 단어가 안 들어
    있는 문장이 절반쯤(2026-08 기준 380개 중 162개) 되기 때문에 실패가
    예외가 아니라 정상 흐름이다.
    """
    pool = sentences.exclude(pk__in=exclude_sentence_ids or [])

    # (id, term) 만 가져온다. 문장마다 다시 부르지 않으려고 한 번만 읽는다.
    terms = [(pk, t.strip()) for pk, t in words.values_list("pk", "term") if t.strip()]
    if not terms:
        return None

    # 몇 개만 뽑아 그중 되는 것을 쓴다. 전부 훑으면 매 요청마다 380개를
    # 스캔하게 되고, 안 되는 문장이 절반이라 몇 번만 시도해도 충분히 걸린다.
    for sentence in pool.order_by("?")[:12]:
        found = _terms_in(sentence.text, terms)
        if not found:
            continue

        # 여러 개면 가장 긴 것을 고른다. "out of scope" 와 "scope" 가 같이
        # 잡히면 긴 쪽이 더 배울 것이 많고, 짧은 쪽은 긴 것 안에 들어 있어
        # 빈칸을 뚫으면 남은 조각이 단서가 된다.
        answer_id, term = max(found, key=lambda pair: len(pair[1]))

        prompt = _blank_out(sentence.text, term)
        if prompt is None:
            continue

        answer = words.filter(pk=answer_id).first()
        if answer is None:
            continue

        distractors = _pick_distractors(answer, words, CHOICE_COUNT - 1)
        if len(distractors) < CHOICE_COUNT - 1:
            return None

        options = [Choice(w.pk, w.term) for w in [answer, *distractors]]
        random.shuffle(options)

        return Question(
            kind=QuizKind.BLANK,
            kind_label=QuizKind.LABELS[QuizKind.BLANK],
            question=QuizKind.QUESTIONS[QuizKind.BLANK],
            prompt=prompt,
            choices=options,
            answer_id=answer.pk,
            category=answer.category,
            category_label=answer.get_category_display(),
            answer_type=QuizKind.TARGETS[QuizKind.BLANK],
            time_limit_ms=TIME_LIMITS_MS[QuizKind.BLANK],
            source_sentence_id=sentence.pk,
        )

    return None


def make_situation_question(
    sentences: QuerySet[Sentence],
    exclude_ids: list[int] | None = None,
) -> Question | None:
    """문장을 보여주고 그 말이 나오는 상황을 고르는 문제."""
    pool = sentences.exclude(context="")
    candidates = pool.exclude(pk__in=exclude_ids or [])

    answer = candidates.order_by("?").first()
    if answer is None:
        return None

    # 같은 상황 글자를 쓰는 문장이 있다(2026-08 기준 380개 중 149개가
    # 남과 상황을 공유하고, 한 상황에 최대 14개). 정답과 겹치는 것만
    # 빼면 **오답끼리 겹치는 것**이 남아 보기 둘이 똑같아 보인다.
    # 그러면 4지선다가 사실상 2지선다가 되어 찍기 확률이 두 배가 된다.
    #
    # 쿼리로는 "서로 다른 상황 셋" 을 뽑을 수 없어(DISTINCT ON 은 정렬을
    # 고정해야 해서 무작위와 섞이지 않는다) 넉넉히 받아 파이썬에서 고른다.
    others = (
        pool.exclude(pk=answer.pk)
        .exclude(context=answer.context)
        .order_by("?")[: (CHOICE_COUNT - 1) * 5]
    )

    distractors: list[Sentence] = []
    seen = {answer.context}
    for one in others:
        if one.context in seen:
            continue
        seen.add(one.context)
        distractors.append(one)
        if len(distractors) == CHOICE_COUNT - 1:
            break

    if len(distractors) < CHOICE_COUNT - 1:
        return None

    options = [Choice(s.pk, s.context) for s in [answer, *distractors]]
    random.shuffle(options)

    return Question(
        kind=QuizKind.SITUATION,
        kind_label=QuizKind.LABELS[QuizKind.SITUATION],
        question=QuizKind.QUESTIONS[QuizKind.SITUATION],
        prompt=answer.text,
        choices=options,
        answer_id=answer.pk,
        category=answer.category,
        category_label=answer.get_category_display(),
        answer_type=QuizKind.TARGETS[QuizKind.SITUATION],
        time_limit_ms=TIME_LIMITS_MS[QuizKind.SITUATION],
    )
