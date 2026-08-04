"""단어 생성 프롬프트.

콘텐츠 타입마다 파일을 나눈다(vocab / sentence / error ...). 프롬프트를 한 곳에
모아두면 타입이 늘어날 때 서로의 문구를 건드리게 된다.
"""

SYSTEM = """\
당신은 개발 영어 학습 콘텐츠를 만드는 편집자입니다.

대상 독자는 영어가 약한 주니어 개발자와 정보처리기사 준비생입니다.
어려운 영어 설명 대신, 실제 개발 현장에서 그 단어를 언제 마주치는지 알려주세요.

규칙:
- 뜻은 사전식 번역이 아니라 개발 맥락에서 쓰이는 의미로 씁니다.
- 설명은 2~3문장. 그 단어를 어디서 보게 되는지 포함합니다.
- 예문은 실제 코드 리뷰, 커밋 메시지, 에러 메시지, 문서에서 볼 법한 문장으로 씁니다.
- 난이도는 1(쉬움) 2(보통) 3(어려움) 중 하나입니다. 주니어 기준으로 판단합니다.
- 이모지를 쓰지 않습니다.
"""

USER_TEMPLATE = """\
다음 조건으로 개발 영어 단어 {count}개를 만들어 주세요.

분류: {category}
{extra}

이미 등록된 단어라 제외할 것: {existing}
"""

# 응답에서 항목 배열이 들어있는 키. 스키마와 같은 자리에 둬서 함께 바뀌게 한다.
RESULT_KEY = "words"

# 응답 스키마. structured outputs 로 형식을 강제해 파싱 실패를 없앤다.
SCHEMA = {
    "type": "object",
    "properties": {
        "words": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string", "description": "영어 단어. 소문자."},
                    "meaning": {"type": "string", "description": "개발 맥락에서의 한글 뜻."},
                    "description": {"type": "string", "description": "2~3문장 설명."},
                    "example": {"type": "string", "description": "영어 예문 한 문장."},
                    "example_translation": {"type": "string", "description": "예문의 한글 해석."},
                    "difficulty": {"type": "integer", "enum": [1, 2, 3]},
                },
                "required": [
                    "term",
                    "meaning",
                    "description",
                    "example",
                    "example_translation",
                    "difficulty",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["words"],
    "additionalProperties": False,
}


def build_user_prompt(
    count: int,
    category: str,
    existing: list[str],
    extra: str = "",
) -> str:
    """사용자 메시지를 만든다.

    existing 을 넘기는 이유: 같은 단어가 반복 생성되면 unique 제약에 걸려
    저장 단계에서 버려진다. 미리 알려주는 편이 API 호출 값을 아낀다.
    """
    return USER_TEMPLATE.format(
        count=count,
        category=category or "개발 전반",
        extra=extra,
        existing=", ".join(existing) if existing else "(없음)",
    )
