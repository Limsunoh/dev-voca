"""대량 생성의 진행 상태, 요청 만들기, 결과 반영, 칸 검사.

Claude API 를 직접 부르지는 않는다. 요청 본문을 만들고 받은 결과를 파일에
반영할 뿐이고, 실제 호출은 bulk_content 명령이 주입받은 클라이언트로 한다.
그래서 이 모듈은 과금 없이 테스트할 수 있다.

작업 폴더(저장소 밖)의 모양:

    <dir>/batches.json         보낸 batch 와 요청마다 담긴 항목 key
    <dir>/usage.json           단계별 토큰과 비용(달러)
    <dir>/existing.json        운영 DB 에 이미 있는 원문(있으면 로컬 DB 대신 쓴다)
    <dir>/<kind>/<stage>.jsonl 단계를 통과한 항목
    <dir>/<kind>/dropped.jsonl 버린 항목과 이유
    <dir>/<kind>/final.jsonl   export 가 만든 최종본

DB 가 아니라 파일에 두는 이유: 운영 DB 에는 API 키가 없고(CODE_INSIGHTS
2026-11-10), 검수를 다 통과한 것만 운영에 넣어야 한다. 중간 산출물이 DB 에
들어가면 검수 대기 목록이 수만 개로 불어나 Admin 에서 고를 수가 없다.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from django.core.exceptions import FieldDoesNotExist

from apps.ai_pipeline.prompts import bulk as prompts
from apps.vocab.models import DailyPhrase, LearningItem, PhraseScene, Sentence, SentenceKind, Word
from apps.vocab.talk import UNCONTRACTED, is_speakable, normalize

# 원문이 들어 있는 칸. 단어만 term 이다.
SOURCE_FIELD = {"word": "term", "sentence": "text", "phrase": "text"}

# 같은 요청을 몇 번까지 다시 보내나. 응답에서 계속 빠지는 항목이 있으면
# 끝없이 다시 보내게 되므로 두 번에서 버린다.
MAX_ATTEMPTS = 2

# 1백만 토큰당 달러(정가). batch 는 이 값의 절반이다. 캐시 쓰기는 5분 TTL
# 기준 입력의 1.25배. 2026-11 기준 값이라 바뀌면 여기만 고친다.
PRICES = {
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.10, "cache_write": 2.5},
}
BATCH_DISCOUNT = 0.5

_HANGUL = re.compile(r"[가-힣]")
# 낱자모(ㄱ·ㅔ). 시범에서 "깨진 자모가 섞인" 한글발음이 재확인까지 갔다.
_JAMO = re.compile(r"[\u1100-\u11ff\u3131-\u318e]")
# 그림 기호. 범위를 손으로 적으면 U+23F0(알람 시계) 같은 것이 빠진다. 유니코드
# 분류 So(기타 기호)와 이모지 변형 선택자로 본다. 한글·영문·IPA 는 So 가 아니다.
_EMOJI_SELECTOR = "\ufe0f"


def _is_symbol(c: str) -> bool:
    return c == _EMOJI_SELECTOR or unicodedata.category(c) == "So"


def _has_emoji(value: str) -> bool:
    return any(_is_symbol(c) for c in value)


# ---------------------------------------------------------------------------
# 원문 정규화와 key
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """중복을 가를 때 쓰는 모양. 대소문자·끝 구두점·공백 차이를 무시한다."""
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    return lowered.rstrip(".!?")


_PHRASE_PUNCT = re.compile(r"[^\w\s'’-]")
_PRONOUN_I = re.compile(r"^I\b")
_LOWER_I = re.compile(r"\bi\b")


def clean_phrase(text: str) -> str:
    """일상 표현을 기존 207개와 같은 모양으로 맞춘다.

    기존 표현은 문장부호가 없고(`can I see the menu`) 첫 글자가 소문자다.
    물음표·쉼표가 남으면 talk.is_speakable 이 기호로 보고 출제에서 뺀다 -
    시범 86개 중 58개가 그렇게 버려졌다. 첫 글자는 대명사 I 만 대문자로 둔다.
    """
    text = re.sub(r"\s+", " ", _PHRASE_PUNCT.sub("", text.replace("’", "'"))).strip()
    first = text.split(" ", 1)[0]
    # 첫 낱말이 약어(TV, OK)면 그대로 둔다. "tV" 로 내리면 is_speakable 의 약어
    # 검사(낱말 전체가 대문자)를 빠져나가 소리로 채점할 수 없는 표현이 남는다.
    # Wi-Fi 처럼 첫 글자 뒤에도 대문자가 있으면 고유한 표기라 그대로 둔다.
    acronym = any(c.isupper() for c in first[1:])
    if text and not _PRONOUN_I.match(text) and not acronym:
        text = text[0].lower() + text[1:]
    # 모델이 대명사를 소문자로 준 경우(can i help). 홀로 선 i 는 영어에서 대명사뿐이다.
    return _LOWER_I.sub("I", text)


def strip_decoration(text: str) -> str:
    """에러 메시지 앞머리의 장식 기호를 뗀다.

    Terraform(U+2502 상자 선), Jest(U+25CF), esbuild(U+2718), ESLint(U+2716),
    Next.js(U+26A0)가 메시지 앞에 기호를 붙인다. 배울 영어가 아니고 한글로 읽을
    수도 없는데, 남겨 두면 칸을 다 채운 뒤에야 이모지 검사로 버려져 그 비용을
    날린다. 앞머리만 떼고, 본문 안의 기호는 칸 검사가 본다.
    """
    i = 0
    while i < len(text) and (text[i].isspace() or _is_symbol(text[i])):
        i += 1
    return text[i:]


def item_key(kind: str, text: str) -> str:
    """원문에서 나오는 key. 같은 원문이면 언제 뽑아도 같은 key 가 된다.

    순번을 쓰지 않는 이유: 같은 문장을 두 주제에서 뽑았을 때 다른 key 가
    되면 중복이 key 로 안 걸린다. 문장 slug(bulk-<key>)도 이 값이라 다시
    넣어도 같은 행을 가리킨다.
    """
    return hashlib.sha1(f"{kind}:{normalize_text(text)}".encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 칸 검사. AI 검수 전에 기계로 걸러지는 것은 여기서 거른다
# ---------------------------------------------------------------------------


def _field_max(model, name: str) -> int | None:
    return model._meta.get_field(name).max_length


def _check_reading(reading: str, problems: list[str]) -> None:
    if not _HANGUL.search(reading):
        problems.append("한글발음에 한글이 없음")
    if _JAMO.search(reading):
        problems.append("한글발음에 낱자모(ㄱ, ㅔ 같은 조각)가 섞임")
    if reading.count("**") < 2 or reading.count("**") % 2:
        problems.append("한글발음의 강세 ** 가 없거나 짝이 안 맞음")
    if len(_parts(reading.replace("**", ""))) != len(_parts(reading)):
        # `**** 유` 처럼 강세 표시만 있는 조각. 화면(alignParts)은 강세를 걷은
        # 수와 안 걷은 수가 다르면 강조를 끈다. 단어도 소리내어 읽기에 나간다.
        problems.append("한글발음에 강세 표시만 있는 조각이 있음")


# 화면(frontend/src/lib/talk-parts.ts 의 alignParts)이 낱말을 가르는 기준.
# 공백만으로 세면 하이픈이 든 한글발음이 검사는 통과하고 화면 강조는 꺼진다.
_PART_SPLIT = re.compile(r"[\s-]+")


def _parts(value: str) -> list[str]:
    return [p for p in _PART_SPLIT.split(value.strip().strip("/")) if p]


def phrase_word_counts(item: dict) -> tuple[int, int, int]:
    """일상 표현의 세 칸 낱말 수. 화면이 세는 방식과 같게 센다.

    text 는 talk.normalize 를 거친다(축약형 하나, 하이픈 둘). 발음기호는
    바깥 슬래시를 벗기고, 한글발음과 함께 공백·하이픈으로 가른다.
    """
    text = len(normalize(item.get("text", "")).split())
    pron = len(_parts(item.get("pronunciation", "")))
    reading = len(_parts(item.get("reading", "")))
    return text, pron, reading


def _screen_mismatch(item: dict) -> str | None:
    """화면(alignParts)이 짝을 못 짓는 이유. 서버 채점 수(normalize)와 따로 본다.

    화면은 원문을 normalize 없이 공백·하이픈으로 가르고, 한글발음은 강세를
    걷어낸 수와 안 걷어낸 수가 같아야 짝을 짓는다. 그래서 `see you_later`
    (채점 3, 화면 2) 처럼 서버 수로는 맞는데 화면에서 어긋나는 것이 있다.
    강세 표시만 있는 조각은 세 종류 모두에 걸리므로 _check_reading 이 본다.
    """
    text = item.get("text", "")
    graded = len(normalize(text).split())
    shown = len(_parts(text))
    if shown != graded:
        return f"화면 낱말 수({shown})와 채점 낱말 수({graded})가 다름"
    return None


def _stress_crosses_parts(reading: str) -> bool:
    """강세 ** 가 낱말 경계를 걸치는가. 걸치면 화면이 낱말 수를 못 맞춘다."""
    return any(part.count("**") % 2 for part in _parts(reading))


def validate(kind: str, item: dict) -> list[str]:
    """DB 에 넣을 수 없거나 화면을 깨뜨리는 것. 빈 목록이면 통과."""
    problems: list[str] = []
    model = {"word": Word, "sentence": Sentence, "phrase": DailyPhrase}[kind]

    required = {
        "word": ["term", "meaning", "pronunciation", "reading", "description", "example", "example_translation"],
        "sentence": ["text", "reading", "translation", "context", "description"],
        "phrase": ["text", "meaning", "pronunciation", "reading"],
    }[kind]
    for name in required:
        value = item.get(name)
        if not isinstance(value, str) or not value.strip():
            # str(None) 은 "None" 이라 비어 있지 않게 보인다. 그대로 넣으면 DB 의
            # NOT NULL 에서 트레이스백으로 끝난다.
            problems.append(f"{name} 이 비어 있음")
    if problems:
        # 뒤의 검사들은 이 칸들이 글자라고 본다. null 이 섞이면 "칸 검사 실패" 대신
        # 트레이스백으로 끝나므로 여기서 멈춘다.
        return problems

    for name, value in item.items():
        if not isinstance(value, str):
            continue
        if _has_emoji(value):
            problems.append(f"{name} 에 이모지")
        try:
            limit = _field_max(model, name)
        except FieldDoesNotExist:
            # key·topic 같은 진행 기록용 칸
            continue
        if limit and len(value) > limit:
            problems.append(f"{name} 이 {limit}자를 넘음({len(value)})")

    if item.get("difficulty") not in (1, 2, 3):
        problems.append("난이도가 1~3 이 아님")

    reading = item.get("reading", "")
    if reading:
        _check_reading(reading, problems)

    pron = item.get("pronunciation", "")
    if kind in ("word", "phrase") and pron:
        if not (pron.startswith("/") and pron.endswith("/") and len(pron) > 2):
            problems.append("발음기호를 슬래시로 한 번 감싸지 않음")
        elif "/" in pron[1:-1]:
            problems.append("발음기호 안에 슬래시가 또 있음")

    if kind == "word":
        if item.get("category") not in LearningItem.Category.values:
            problems.append("분류가 목록에 없음")
        # 개발 용어도 소리내어 읽기(?kind=dev)에 나간다. 낱말이 여럿인 용어는
        # 발음기호와 한글발음의 낱말 수가 같아야 화면이 틀린 낱말을 짚는다.
        # 용어 자체의 낱말 수와는 비교하지 않는다 - 철자로 읽는 약어(API ->
        # /ˌeɪ pi ˈaɪ/)는 원래 발음 쪽이 더 많다(규칙 문서 6).
        if pron and reading and len(_parts(pron)) != len(_parts(reading)):
            problems.append(
                f"발음기호와 한글발음의 낱말 수가 다름 ({len(_parts(pron))}, {len(_parts(reading))})"
            )
        if _stress_crosses_parts(reading):
            problems.append("강세 ** 가 낱말 경계를 걸침")
    elif kind == "sentence":
        if item.get("category", "") not in [*LearningItem.Category.values, ""]:
            problems.append("분류가 목록에 없음")
        if item.get("sentence_kind") not in SentenceKind.values:
            problems.append("문장 종류가 목록에 없음")
    elif kind == "phrase":
        if item.get("scene") not in PhraseScene.values:
            problems.append("상황이 목록에 없음")
        text = item.get("text", "")
        if not is_speakable(text):
            problems.append("소리로 채점할 수 없는 표현(숫자·약어·기호)")
        # café·résumé 는 is_speakable 을 통과하지만 normalize 가 é 를 공백으로
        # 바꿔 낱말이 쪼개진다. 채점이 어긋나므로 영문 글자만 받는다.
        if not text.replace("’", "'").isascii():
            problems.append("표현에 영문 아닌 글자")
        if UNCONTRACTED.search(text.lower()):
            problems.append("풀어 쓴 형태(where is, I am). 축약형으로 적어야 줄여 읽어도 맞는다")
        counts = phrase_word_counts(item)
        if len(set(counts)) != 1:
            problems.append(f"낱말 수가 다름 (표현 {counts[0]}, 발음기호 {counts[1]}, 한글 {counts[2]})")
        mismatch = _screen_mismatch(item)
        if mismatch:
            problems.append(mismatch)
        if _stress_crosses_parts(reading):
            problems.append("강세 ** 가 낱말 경계를 걸침")

    return problems


# ---------------------------------------------------------------------------
# 비용
# ---------------------------------------------------------------------------


def worst_request_cost(stage: str) -> float:
    """요청 하나가 낼 수 있는 가장 큰 비용. 평균을 모를 때 상한 계산에 쓴다.

    출력은 max_tokens 를 다 쓴다고 보고, 입력은 규칙 문서와 항목 25개를
    넉넉히 2만 토큰으로 본다. 평균 대신 0 으로 세면 첫 batch 들이 서로를
    0 으로 보고 상한 없이 나간다.
    """
    cfg = prompts.STAGES[stage]
    return usage_cost(cfg["model"], {"input_tokens": 20_000, "output_tokens": cfg["max_tokens"]})


def usage_cost(model: str, usage: dict) -> float:
    price = PRICES[model]
    total = (
        usage.get("input_tokens", 0) * price["input"]
        + usage.get("output_tokens", 0) * price["output"]
        + usage.get("cache_read_input_tokens", 0) * price["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) * price["cache_write"]
    )
    return total / 1_000_000 * BATCH_DISCOUNT


# ---------------------------------------------------------------------------
# 파일
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict]:
    """한 줄에 하나씩. 쓰다 끊겨 반만 남은 마지막 줄은 건너뛴다.

    마지막 줄만 봐 주는 이유: 그 자리는 프로세스가 죽은 흔적이라 다시
    돌리면 그 항목이 다시 만들어진다. 중간 줄이 깨졌으면 파일이 망가진
    것이라 그대로 터뜨린다.
    """
    if not path.exists():
        return []
    # splitlines 를 쓰지 않는다. U+2028 같은 글자에서도 줄을 잘라, 검수 메모에
    # 그 글자가 섞이면 한 줄이 둘로 갈린다(json.dumps 는 그 글자를 그대로 쓴다).
    #
    # 바이트로 읽어 줄마다 푼다. 한글 글자 중간(3바이트 중 1바이트)에서 끊긴
    # 꼬리가 있으면 파일 전체를 utf-8 로 풀 때 UnicodeDecodeError 가 나서, 그
    # 줄만 건너뛰기 전에 모든 명령이 죽는다.
    lines = [line for line in path.read_bytes().split(b"\n") if line.strip()]
    rows = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line.decode("utf-8-sig")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if i != len(lines) - 1:
                # JSONDecodeError 로 올리면 collect 가 "다음에 다시" 로 넘겨
                # --wait 가 같은 실패를 끝없이 되풀이한다. 사람이 고칠 일이다.
                raise RuntimeError(f"{path} 의 {i + 1}번째 줄이 깨졌습니다: {exc}") from exc
    return rows


def _cut_broken_tail(path: Path) -> None:
    """줄바꿈 없이 끝난 꼬리(쓰다 끊긴 줄)를 잘라 낸다.

    그대로 이어 쓰면 새 줄이 깨진 줄에 붙어 함께 사라지고, 한 번 더 쓰면
    그 줄이 중간 줄이 되어 read_jsonl 이 파일 전체를 못 읽는다. 잘린 항목은
    handled 에서 빠지므로 다음 submit 때 다시 나간다.
    """
    if not path.exists():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    head, _, tail = data.rpartition(b"\n")
    try:
        # 편집기로 고치고 끝 줄바꿈 없이 저장한 파일, 또는 } 와 줄바꿈 사이에서
        # 끊긴 줄은 온전하다. 자르면 이미 반영한 항목이 사라진다.
        json.loads(tail.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        path.write_bytes(head + b"\n" if head else b"")
    else:
        with path.open("ab") as fh:
            fh.write(b"\n")


def append_jsonl(path: Path, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    _cut_broken_tail(path)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 가 깨졌습니다: {exc}") from exc


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    # Windows 에서는 다른 프로세스(백신, 다른 명령이 읽는 중)가 잠깐 잡고 있으면
    # 바꿔치기가 PermissionError 로 실패한다. 1라운드 collect 가 이걸로 한 번 죽었다.
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# 작업 폴더
# ---------------------------------------------------------------------------


@dataclass
class Request:
    custom_id: str
    params: dict[str, Any]
    keys: list[str] = field(default_factory=list)


class Workspace:
    """작업 폴더 하나. 모든 종류가 batches.json·usage.json 을 같이 쓴다.

    비용 상한이 종류를 가리지 않고 걸려야 해서 한 파일에 모은다. 종류마다
    따로 두면 단어 $90 + 문장 $90 이 각자 상한 안이라 둘 다 나간다.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # 경로 -----------------------------------------------------------------

    def path(self, kind: str, name: str) -> Path:
        return self.root / kind / f"{name}.jsonl"

    @property
    def batches_path(self) -> Path:
        return self.root / "batches.json"

    @property
    def usage_path(self) -> Path:
        return self.root / "usage.json"

    # batch 기록 -----------------------------------------------------------

    def batches(self) -> list[dict]:
        return _read_json(self.batches_path, [])

    def save_batches(self, batches: list[dict]) -> None:
        _write_json(self.batches_path, batches)

    def add_batch(
        self,
        batch_id: str,
        kind: str,
        stage: str,
        requests: list[Request],
        effort: str | None = None,
        per_topic: int | None = None,
    ) -> None:
        batches = self.batches()
        record = {
            "id": batch_id,
            "kind": kind,
            "stage": stage,
            "created": datetime.now().isoformat(timespec="seconds"),
            "requests": {r.custom_id: r.keys for r in requests},
            "collected": False,
        }
        if effort:
            # 기다리는 동안 예상 비용을 최악값으로 세게 하는 표시(inflight_estimate)
            record["effort"] = effort
        if per_topic:
            # 후보 뽑기의 항목 수(주제당 후보 수). 비용 평균을 후보 하나 단위로 낸다.
            record["per_topic"] = per_topic
        batches.append(record)
        self.save_batches(batches)

    def inflight_keys(self, kind: str, stage: str) -> set[str]:
        return {
            key
            for b in self.batches()
            if b["kind"] == kind and b["stage"] == stage and not b["collected"]
            for keys in b["requests"].values()
            for key in keys
        }

    def attempts(self, kind: str, stage: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for b in self.batches():
            if b["kind"] == kind and b["stage"] == stage and b["collected"]:
                for keys in b["requests"].values():
                    for key in keys:
                        counts[key] = counts.get(key, 0) + 1
        return counts

    # 비용 -----------------------------------------------------------------

    def usage(self) -> dict:
        return _read_json(self.usage_path, {})

    def add_usage(
        self, kind: str, stage: str, model: str, usage: dict, items: int = 1, effort: str | None = None
    ) -> None:
        """요청 하나의 사용량을 쌓는다.

        생각 깊이를 바꾼 batch 는 칸을 따로 둔다(`word/enrich@low`). 같은 칸에
        더하면 평균이 그쪽으로 끌려가 기본 batch 의 예상이 낮게 나오고 상한이
        샌다. spent() 는 모든 칸을 더하니 쓴 돈에는 빠짐이 없다.
        """
        data = self.usage()
        name = f"{kind}/{stage}" + (f"@{effort}" if effort else "")
        slot = data.setdefault(name, {"requests": 0, "items": 0, "cost": 0.0, "model": model})
        slot["requests"] += 1
        slot["items"] = slot.get("items", 0) + items
        slot["cost"] += usage_cost(model, usage)
        for field_name, value in usage.items():
            slot[field_name] = slot.get(field_name, 0) + (value or 0)
        _write_json(self.usage_path, data)

    def spent(self) -> float:
        return sum(slot["cost"] for slot in self.usage().values())

    def avg_item_cost(self, kind: str, stage: str, effort: str | None = None) -> float | None:
        """그 생각 깊이로 보낸 요청의 항목 하나당 평균 비용(effort 가 없으면 기본).

        요청 단위가 아니라 항목 단위인 이유: 첫 batch 가 꼬리 묶음 하나(항목 3개)
        뿐이면 요청 평균이 25개짜리 요청의 8분의 1로 잡혀 예상이 낮게 나온다.
        후보 뽑기는 주제 하나가 항목 하나다.
        """
        slot = self.usage().get(f"{kind}/{stage}" + (f"@{effort}" if effort else ""))
        if not slot or not slot.get("items"):
            return None
        return slot["cost"] / slot["items"]

    def estimate(self, kind: str, stage: str, keys_per_request: list[int], effort: str | None = None) -> float:
        """요청 묶음의 예상 비용. 그 생각 깊이의 평균을 모르면 요청마다 최악값.

        생각 깊이를 바꾼 batch 는 그 깊이의 칸(`@low`)만 본다. 기본 칸 평균을
        쓰면 low 를 high 로 바꿔 보낼 때 예상이 낮게 나온다.
        """
        per_item = self.avg_item_cost(kind, stage, effort)
        if per_item is None:
            return worst_request_cost(stage) * len(keys_per_request)
        return per_item * sum(keys_per_request)

    def inflight_estimate(self) -> float:
        """아직 결과를 안 받은 batch 의 예상 비용."""
        return sum(
            self.estimate(
                b["kind"],
                b["stage"],
                [b.get("per_topic") or len(k) for k in b["requests"].values()],
                b.get("effort"),
            )
            for b in self.batches()
            if not b["collected"]
        )

    # 항목 -----------------------------------------------------------------

    def items(self, kind: str, stage: str) -> list[dict]:
        return read_jsonl(self.path(kind, stage))

    def dropped(self, kind: str) -> list[dict]:
        return read_jsonl(self.path(kind, "dropped"))

    def handled_keys(self, kind: str, stage: str) -> set[str]:
        """이 단계에서 이미 결론이 난 key(통과했거나 이 단계에서 버렸거나)."""
        done = {i["key"] for i in self.items(kind, stage)}
        done |= {d["key"] for d in self.dropped(kind) if d["stage"] == stage}
        return done

    def drop(self, kind: str, stage: str, rows: list[tuple[str, str, str]]) -> None:
        """rows: (key, 원문, 이유)."""
        append_jsonl(
            self.path(kind, "dropped"),
            ({"key": k, "stage": stage, "text": t, "reason": r} for k, t, r in rows),
        )

    def existing_texts(self, kind: str) -> set[str]:
        """이미 있는 원문(정규화). existing.json 이 있으면 그것(운영 DB 사본)을 쓴다."""
        saved = _read_json(self.root / "existing.json", None)
        if saved is not None and kind in saved:
            # 단어는 [term, 분류] 짝으로 담겨 있다(existing_words 가 분류를 쓴다).
            values = [v[0] if isinstance(v, list) else v for v in saved[kind]]
        elif kind == "word":
            values = Word.objects.values_list("term", flat=True)
        elif kind == "sentence":
            values = Sentence.objects.values_list("text", flat=True)
        else:
            values = DailyPhrase.objects.values_list("text", flat=True)
        return {normalize_text(v) for v in values}

    def existing_words(self) -> list[tuple[str, str]]:
        """이미 있는 단어와 분류. 후보를 뽑을 때 같은 분류의 단어를 빼 달라고 쓴다."""
        saved = _read_json(self.root / "existing.json", None)
        if saved is not None and "word" in saved:
            # 분류 없이 문자열로만 적힌 줄은 분류를 모르니 제외 목록에서 뺀다.
            return [tuple(v) for v in saved["word"] if isinstance(v, list) and len(v) == 2]
        return list(Word.objects.values_list("term", "category"))


# ---------------------------------------------------------------------------
# 요청 만들기
# ---------------------------------------------------------------------------


def _params(stage: str, system: str, user: str, schema: dict) -> dict:
    cfg = prompts.STAGES[stage]
    return {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        # 같은 단계의 요청은 system 이 같다. 규칙 문서가 들어 있어 길기 때문에
        # 캐시해 두면 두 번째 요청부터 그 부분을 10분의 1 값에 읽는다.
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "output_config": {
            "effort": cfg["effort"],
            "format": {"type": "json_schema", "schema": schema},
        },
    }


def brainstorm_requests(
    ws: Workspace, kind: str, per_topic: int, round_no: int, limit: int | None
) -> list[Request]:
    """주제마다 후보를 뽑는 요청. round 가 2 이상이면 앞 라운드 후보를 빼 달라고 한다."""
    collected = ws.items(kind, "brainstorm")
    inflight = ws.inflight_keys(kind, "brainstorm")
    # 응답을 제대로 받은 주제만 끝난 것으로 본다(collect 가 "done" 에 적는다).
    # 잘리거나 실패한 주제는 다시 나가고, MAX_ATTEMPTS 번 실패하면 그만둔다.
    # "done" 이 없는 기록은 이 구분이 생기기 전의 것이라 전부 끝난 것으로 본다.
    done_topics: set[str] = set()
    for b in ws.batches():
        if b["kind"] == kind and b["stage"] == "brainstorm" and b["collected"]:
            if "done" in b:
                done_topics.update(b["done"])
            else:
                done_topics.update(k for keys in b["requests"].values() for k in keys)
    attempts = ws.attempts(kind, "brainstorm")
    by_topic: dict[str, list[str]] = {}
    for item in collected:
        by_topic.setdefault(item["topic_id"], []).append(item[SOURCE_FIELD[kind]])

    # 단어는 같은 분류에 이미 있는 단어도 빼 달라고 한다. 운영 사본이 있으면 그것.
    existing_words: dict[str, list[str]] = {}
    if kind == "word":
        for term, category in ws.existing_words():
            existing_words.setdefault(category, []).append(term)

    system = prompts.BRAINSTORM_SYSTEM
    schema = prompts.BRAINSTORM_SCHEMA
    out: list[Request] = []
    for topic in prompts.topics(kind):
        round_key = f"{topic['id']}#r{round_no}"
        if round_key in done_topics or round_key in inflight:
            continue
        if attempts.get(round_key, 0) >= MAX_ATTEMPTS:
            continue
        exclude = by_topic.get(topic["id"], [])
        if kind == "word":
            exclude = existing_words.get(topic["group"], []) + exclude
        user = prompts.brainstorm_user(kind, topic, per_topic, exclude)
        out.append(Request(f"bs-{len(out)}", _params("brainstorm", system, user, schema), [round_key]))
        if limit and len(out) >= limit:
            break
    return out


def _pending(ws: Workspace, kind: str, stage: str) -> tuple[list[dict], list[dict]]:
    """앞 단계를 통과했지만 이 단계를 아직 안 거친 항목. (보낼 것, 횟수 초과로 버릴 것)"""
    previous = prompts.PREVIOUS[stage]
    source = ws.items(kind, previous)
    if stage == "recheck":
        # 재확인은 검수(1차든 2차든)가 고친 것만 본다(apply_review 의 changed).
        source = [i for i in source if i.get("changed")]
    handled = ws.handled_keys(kind, stage) | ws.inflight_keys(kind, stage)
    attempts = ws.attempts(kind, stage)
    send, give_up = [], []
    for item in source:
        if item["key"] in handled:
            continue
        (give_up if attempts.get(item["key"], 0) >= MAX_ATTEMPTS else send).append(item)
    return send, give_up


# 프롬프트에 넣는 항목 모양. 진행 기록용 칸은 빼서 입력 값을 아낀다.
_HIDDEN = {"topic_id", "changed", "notes"}


def _for_prompt(item: dict) -> str:
    return json.dumps({k: v for k, v in item.items() if k not in _HIDDEN}, ensure_ascii=False)


def stage_requests(ws: Workspace, kind: str, stage: str, limit: int | None) -> list[Request]:
    send, give_up = _pending(ws, kind, stage)
    if give_up:
        ws.drop(kind, stage, [(i["key"], i[SOURCE_FIELD[kind]], "두 번 보내도 응답에 없음") for i in give_up])

    if stage == "enrich":
        system, schema = prompts.enrich_system(kind), prompts.enrich_schema(kind)
        intro = "다음 {n}개 항목의 칸을 채워 주세요. 한 줄이 한 항목입니다.\n\n"
    else:
        system, schema = prompts.review_system(stage, kind), prompts.review_schema(kind)
        intro = "다음 {n}개 항목을 검수해 주세요. 한 줄이 한 항목입니다.\n\n"

    out: list[Request] = []
    for start in range(0, len(send), prompts.CHUNK):
        chunk = send[start : start + prompts.CHUNK]
        user = intro.format(n=len(chunk)) + "\n".join(_for_prompt(i) for i in chunk)
        out.append(
            Request(f"{stage[:6]}-{len(out)}", _params(stage, system, user, schema), [i["key"] for i in chunk])
        )
        if limit and len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# 결과 반영
# ---------------------------------------------------------------------------


class ResultError(RuntimeError):
    """응답 하나를 못 읽었다. 그 요청의 항목은 다음 submit 때 다시 나간다."""


def parse_message(message: Any) -> dict:
    """batch 결과의 message 에서 JSON 을 꺼낸다."""
    if message.stop_reason == "refusal":
        raise ResultError("거부됨")
    if message.stop_reason == "max_tokens":
        raise ResultError("max_tokens 에서 잘림")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResultError(f"JSON 이 아님: {exc}") from exc
    if not isinstance(payload, dict):
        # [] 나 null 이면 뒤의 .get 에서 AttributeError 가 나 collect 가 그 batch
        # 에서 매번 죽는다. 그 요청만 실패로 두고 다음 submit 에 다시 보낸다.
        raise ResultError(f"JSON 객체가 아님: {type(payload).__name__}")
    return payload


def brainstorm_seen(ws: Workspace, kind: str) -> set[str]:
    """중복 검사에 쓰는 원문 집합. batch 하나를 반영하는 동안 한 번만 만든다."""
    return ws.existing_texts(kind) | {
        normalize_text(i[SOURCE_FIELD[kind]]) for i in ws.items(kind, "brainstorm")
    }


def apply_brainstorm(ws: Workspace, kind: str, round_key: str, payload: dict, seen: set[str]) -> int:
    """후보를 정리해 중복을 빼고 저장한다. 저장한 개수를 돌려준다.

    seen 은 호출부가 brainstorm_seen 으로 만들어 넘기고, 여기서 새 후보를
    더해 간다. 같은 batch 의 다른 주제가 같은 말을 뽑아도 한 번만 남는다.
    """
    topic_id = round_key.rsplit("#", 1)[0]
    topic = next((t for t in prompts.topics(kind) if t["id"] == topic_id), None)
    if topic is None:
        raise RuntimeError(
            f"주제 {topic_id} 가 prompts/bulk.py 에 없습니다. 결과를 기다리는 동안 주제 이름을 바꿨다면 되돌리세요."
        )
    limit = _field_max({"word": Word, "sentence": Sentence, "phrase": DailyPhrase}[kind], SOURCE_FIELD[kind])
    rows = []
    for raw in payload.get("items", []):
        text = str(raw).strip()
        if kind == "word":
            text = text.rstrip(".")
        elif kind == "phrase":
            text = clean_phrase(text)
        else:
            text = strip_decoration(text)
        norm = normalize_text(text)
        if not text or norm in seen or (limit and len(text) > limit):
            continue
        seen.add(norm)
        group_field = {"word": "category", "sentence": "sentence_kind", "phrase": "scene"}[kind]
        rows.append(
            {
                "key": item_key(kind, text),
                SOURCE_FIELD[kind]: text,
                group_field: topic["group"],
                "topic": topic["topic"],
                "topic_id": topic_id,
            }
        )
    return append_jsonl(ws.path(kind, "brainstorm"), rows)


def apply_enrich(ws: Workspace, kind: str, base: dict[str, dict], payload: dict) -> tuple[int, int]:
    """채운 항목을 검사해 저장한다. (통과, 버림).

    base 는 이 요청에 담아 보낸 후보(key -> 항목)다. 다른 요청의 key 를
    돌려주면 무시한다.
    """
    src = SOURCE_FIELD[kind]
    passed, dropped = [], []
    base = dict(base)
    for out in payload.get("items", []):
        # 꺼내 쓰는 이유: 같은 key 가 두 번 오면 두 벌이 다음 단계로 넘어가
        # 비용이 두 배가 되고 최종본에 내용이 다른 두 벌이 생긴다. 첫 답만 쓴다.
        source = base.pop(out.get("key"), None)
        if source is None:
            continue
        key = source["key"]
        # 원문과 묶음 값은 우리 것을 쓴다. 모델이 원문을 고쳐 돌려주면 중복
        # 검사가 무너지고, 분류를 바꾸면 주제와 안 맞는다.
        item = {**source, **out, src: source[src]}
        problems = validate(kind, item)
        if problems:
            dropped.append((key, item[src], "; ".join(problems)))
        else:
            passed.append(item)
    append_jsonl(ws.path(kind, "enrich"), passed)
    ws.drop(kind, "enrich", dropped)
    return len(passed), len(dropped)


_GROUP_VALUES = {
    # 문장은 분류가 없어도 된다(빈 값). 단어는 validate 가 빈 분류를 따로 막는다.
    "category": {*LearningItem.Category.values, ""},
    "scene": set(PhraseScene.values),
}


def apply_review(ws: Workspace, kind: str, stage: str, base: dict[str, dict], payload: dict) -> dict[str, int]:
    """검수 결과를 반영한다. 고친 항목은 다시 칸 검사를 거친다.

    base 는 이 요청에 담아 보낸 항목(key -> 항목)이다.
    """
    src = SOURCE_FIELD[kind]
    counts = {"ok": 0, "fix": 0, "drop": 0}
    passed, dropped = [], []
    base = dict(base)
    for review in payload.get("reviews", []):
        # 첫 답만 쓴다. [drop, ok] 처럼 같은 key 가 두 번 오면 버림과 통과에
        # 둘 다 적혀 drop 판정이 뚫린다(apply_enrich 와 같은 이유).
        source = base.pop(review.get("key"), None)
        if source is None:
            continue
        key = source["key"]
        item = dict(source)
        verdict = review.get("verdict")
        note = review.get("note", "")
        item["notes"] = [*item.get("notes", []), f"{stage}: {verdict} {note}".strip()]

        # 모르는 판정(스키마 밖)은 통과로 세지 않는다. 검수가 무엇을 봤는지 모른다.
        if verdict not in ("ok", "fix") or (stage == "recheck" and verdict != "ok"):
            counts["drop"] += 1
            dropped.append((key, item[src], note or "검수에서 버림"))
            continue

        changed = False
        if verdict == "fix":
            for fix in review.get("fixes", []):
                name, value = fix.get("field"), fix.get("value", "")
                if name not in prompts.EDITABLE[kind]:
                    continue
                if name == "difficulty":
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        continue
                if name in _GROUP_VALUES:
                    value = str(value).strip().lower()
                if name in _GROUP_VALUES and value not in _GROUP_VALUES[name]:
                    # 검수가 "Trouble" 처럼 목록에 없는 값으로 옮기면 그 수정만
                    # 버린다. 받아들이면 칸 검사에서 항목 전체가 버려진다.
                    continue
                if item.get(name) != value:
                    item[name] = value
                    changed = True
        problems = validate(kind, item)
        if problems:
            counts["drop"] += 1
            dropped.append((key, item[src], "고친 뒤 칸 검사 실패: " + "; ".join(problems)))
            continue
        counts["fix" if changed else "ok"] += 1
        # 재확인(recheck)의 입력이 되는 표시. 검수가 고친 항목은 1차든 2차든
        # 고친 결과를 아무도 다시 안 보게 되므로 재확인으로 보낸다. "fix" 라고
        # 해 놓고 실제로 바뀐 칸이 없는 것(fixes 가 비었거나 목록 밖 값이라 건너뜀)도
        # 검수가 틀렸다고 본 것이라 재확인으로 보낸다.
        if stage == "recheck":
            item["changed"] = False
        else:
            item["changed"] = bool(item.get("changed")) or changed or verdict == "fix"
        passed.append(item)
    append_jsonl(ws.path(kind, stage), passed)
    ws.drop(kind, stage, dropped)
    return counts


# export 가 붙이고 load 가 확인하는 표시. 중간 단계 파일(enrich.jsonl 등)을
# 잘못 넘겨 AI 검수를 건너뛴 채 넣는 것을 막는다.
FINAL_MARK = "reviewed_twice"


def final_items(ws: Workspace, kind: str) -> list[dict]:
    """두 번 검수를 끝낸 항목. 검수가 고치지 않은 것 + 고친 뒤 재확인을 통과한 것."""
    untouched = [i for i in ws.items(kind, "review_reading") if not i.get("changed")]
    return [{**i, FINAL_MARK: True} for i in untouched + ws.items(kind, "recheck")]
