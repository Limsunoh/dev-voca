"""Claude API 클라이언트.

**이 모듈은 관리자 배치에서만 호출한다.** View·Serializer·시그널에서 부르면
사용자 요청마다 API 비용이 나가고 응답이 수십 초로 늘어난다(CLAUDE.md 금지사항).

테스트가 실제 API 를 때리지 않도록 클라이언트를 주입 가능하게 만들었다.
개발기 .env 에는 진짜 키가 있어서, mock 없이 테스트를 짜면 그 자리에서 과금된다.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

# 생성 결과 한 건. 저장은 호출부(management command)가 한다.
GeneratedItem = dict[str, Any]


class ContentGenerator(Protocol):
    """생성기 인터페이스.

    테스트는 이 프로토콜을 만족하는 가짜를 넘긴다. 실제 구현은
    ClaudeGenerator 하나뿐이지만, 이 경계가 있어야 과금 없이 테스트할 수 있다.
    """

    def generate(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        result_key: str,
        max_items: int,
    ) -> list[GeneratedItem]: ...


class GenerationError(RuntimeError):
    """생성 실패. 호출부가 사람이 읽을 문구로 바꿔 보여준다."""


class ClaudeGenerator:
    """Anthropic API 로 학습 콘텐츠를 생성한다."""

    # 콘텐츠 생성은 판단이 필요한 작업이라 Opus 를 쓴다.
    MODEL = "claude-opus-5"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise GenerationError(
                "ANTHROPIC_API_KEY 환경변수가 필요합니다. .env 를 확인하세요."
            )
        # 임포트를 여기 두는 이유: 키 없이 이 모듈을 임포트만 하는 경우
        # (예: Django 가 앱을 로드할 때) 패키지가 없어도 깨지지 않게 한다.
        import anthropic

        self._client = anthropic.Anthropic(api_key=key)
        self._model = model or self.MODEL

    def generate(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        result_key: str,
        max_items: int,
    ) -> list[GeneratedItem]:
        """스키마에 맞는 항목 목록을 받아온다.

        structured outputs 로 응답 형식을 강제한다. 자유 텍스트를 파싱하면
        형식이 조금만 달라도 깨지는데, 배치가 밤중에 도는 상황에서는
        그 실패가 다음 날 아침에야 드러난다.

        result_key 는 스키마에서 항목 배열이 들어있는 키다. 여기에 "words" 를
        박아두면 나중에 문장 생성이 {"sentences": [...]} 를 돌려줄 때 조용히
        빈 결과가 되어 "생성된 것이 없습니다" 로 끝난다.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as exc:
            # 예외 타입까지 남긴다. 이 메시지는 CommandError 로 감싸져
            # 스택트레이스 없이 출력되므로, 여기서 안 남기면 어디에도 안 남는다.
            raise GenerationError(
                f"Claude API 호출에 실패했습니다: {type(exc).__name__}: {exc}"
            ) from exc

        # 안전장치가 거부로 끝낸 경우. content 를 읽기 전에 확인해야 한다.
        if response.stop_reason == "refusal":
            raise GenerationError("요청이 거부되었습니다. 프롬프트를 확인하세요.")

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            raise GenerationError("빈 응답을 받았습니다.")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GenerationError(f"응답을 JSON 으로 읽지 못했습니다: {exc}") from exc

        # 키가 없는 경우와 목록이 아닌 경우를 한 검사로 묶는다. 둘로 나누면
        # 앞의 검사를 지워도 뒤가 잡아내서, 어느 쪽이 실제로 막고 있는지
        # 테스트로 구분할 수 없다.
        items = payload.get(result_key)
        if not isinstance(items, list):
            raise GenerationError(
                f"응답의 '{result_key}' 가 목록이 아닙니다. 스키마와 맞지 않습니다."
            )

        return items[:max_items]
