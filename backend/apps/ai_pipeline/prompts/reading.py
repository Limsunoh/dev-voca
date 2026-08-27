"""한글 발음 표기 프롬프트.

다른 프롬프트(vocab)와 성격이 다르다. 저쪽은 없던 콘텐츠를 만들고, 이쪽은
이미 있는 항목에 칸 하나를 채운다. 그래서 입력에 기존 단어와 발음기호가 함께
들어가고, 응답은 그 단어와 짝이 맞아야 한다.

**표기 규칙은 apps/ai_pipeline/prompts/korean-reading.md 에서 읽어온다.** 여기에 복사해두면 문서와
프롬프트가 갈리고, 그러면 검수 기준과 생성 기준이 서로 다른 말을 하게 된다.
"""

from __future__ import annotations

from pathlib import Path

# 프롬프트 옆에 둔다. 저장소 루트(docs/)에 두면 backend/ 만 담는 배포
# 이미지에서 사라져 그 자리에서 죽는다. WORDS_PROMPT.md 도 같은 자리에 있다.
_RULES = Path(__file__).resolve().parent / "korean-reading.md"


def _rules() -> str:
    """표기 규칙 문서. 없으면 그 사실을 드러낸다.

    조용히 빈 문자열로 넘기면 규칙 없는 프롬프트가 나가고, 566개가 제각각
    적힌 뒤에야 알게 된다.

    캐시하지 않는다. 규칙을 다듬으며 배치를 여러 번 돌리는 것이 이 기능의
    사용 패턴이라, 한 번 읽고 고정하면 고친 규칙이 반영되지 않는다. 파일
    하나 읽는 비용은 API 호출 옆에서 무시할 수 있다.
    """
    if not _RULES.exists():
        raise FileNotFoundError(
            f"표기 규칙 문서를 찾지 못했습니다: {_RULES}\n"
            "apps/ai_pipeline/prompts/korean-reading.md 가 있어야 발음을 생성할 수 있습니다."
        )
    return _RULES.read_text(encoding="utf-8")


SYSTEM_TEMPLATE = """\
당신은 영어 발음을 한글로 옮기는 편집자입니다.

대상 독자는 영어가 약한 주니어 개발자입니다. 발음기호(IPA)를 읽을 줄 모르는
사람이 **한글만 읽어도 통하게** 적는 것이 유일한 목적입니다.

아래 규칙을 그대로 따르세요. 규칙에 없는 판단이 필요하면 "한글만 읽었을 때
원음에 가까운가" 를 기준으로 정하세요.

이모지를 쓰지 않습니다.

---

{rules}
"""

USER_TEMPLATE = """\
다음 {count}개 항목의 한글 발음을 만들어 주세요.

각 항목은 `단어 | 발음기호` 형식입니다. 발음기호가 비어 있으면 일반적인
개발 현장 발음을 기준으로 하세요.

{items}
"""

RESULT_KEY = "readings"

SCHEMA = {
    "type": "object",
    "properties": {
        "readings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "입력으로 준 단어. 그대로 돌려주세요.",
                    },
                    "reading": {
                        "type": "string",
                        "description": (
                            "한글 발음. 강세는 **굵게** 로 감쌉니다. "
                            "한글에 없는 소리(th, f, v, sh, z, 끝의 r, 어두의 l)는 "
                            "영문자를 그대로 씁니다. 예: **th렏**, 리**f액**털r"
                        ),
                    },
                    "note": {
                        "type": "string",
                        "description": (
                            "왜 그렇게 읽는지 한두 문장. 흔히 틀리는 지점을 "
                            "짚습니다. 특별히 설명할 것이 없으면 빈 문자열."
                        ),
                    },
                },
                "required": ["term", "reading", "note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["readings"],
    "additionalProperties": False,
}


def system() -> str:
    """규칙 문서를 넣은 시스템 프롬프트."""
    return SYSTEM_TEMPLATE.format(rules=_rules())


def user(items: list[tuple[str, str]]) -> str:
    """`(단어, 발음기호)` 목록을 프롬프트로.

    발음기호가 비어 있어도 항목을 빼지 않는다 - 개발 용어는 사전에 없는
    것이 많아 그것까지 빼면 채울 수 있는 것이 얼마 안 남는다.
    """
    lines = [f"{term} | {ipa or '(없음)'}" for term, ipa in items]
    return USER_TEMPLATE.format(count=len(items), items="\n".join(lines))
