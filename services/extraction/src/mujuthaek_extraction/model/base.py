"""추출 모델 호출 인터페이스. 제공자 구현은 이 Protocol을 따르며, 이 패키지는 어떤 제공자에도 의존하지 않습니다.

모델 선택·유료 호출 범위는 별도 결정(E1) 후 제공자 구현을 추가합니다. 테스트·오프라인 실행은 RecordedModel을 씁니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class StopReason(Enum):
    END = "END"  # 정상 종료
    MAX_TOKENS = "MAX_TOKENS"  # 출력 한도로 잘림
    RUNAWAY = "RUNAWAY"  # 받는 도중 반복 폭주를 보고 끊음(스트리밍 호출). 잘림처럼 처리합니다
    REFUSED = "REFUSED"  # 제공자가 응답을 거부함
    OTHER = "OTHER"


@dataclass(frozen=True)
class ModelImage:
    """요청에 붙이는 그림(PDF 쪽을 그린 PNG 등). 그림을 받는 모델만 씁니다(image_reading)."""

    label: str  # 요청 글자에서 이 그림을 가리키는 이름 (예: "그림 1")
    media_type: str
    data: bytes


@dataclass(frozen=True)
class ToolSpec:
    """모델에 알려 주는 도구 하나(2026-11-04, 재확인 에이전트). 실행은 모델이 아니라 우리 코드가 합니다."""

    name: str
    description: str  # 모델이 언제 쓰는지 고르는 근거. 한두 문장으로
    parameters: dict[str, Any]  # 입력 JSON 스키마(엄격 형식으로 바꿔 보냄)


@dataclass(frozen=True)
class ToolCall:
    """모델이 요청한 도구 호출. arguments는 모델이 쓴 JSON 글자 그대로입니다(우리 쪽에서 형식을 검사)."""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolTurn:
    """앞선 차례 하나: 모델의 도구 호출들과 우리가 돌려준 결과(같은 순서, JSON 글자)."""

    calls: tuple[ToolCall, ...]
    results: tuple[str, ...]


@dataclass(frozen=True)
class ModelRequest:
    prompt_version: str
    call_name: str
    system: str  # 모든 호출에 같은 공통 지시 (캐시 앞부분)
    user: str  # 원문·호별 표 (같은 공고의 호출끼리 같음, 캐시 앞부분)
    instructions: str  # 호출마다 다른 지시·구조 요약·재요청 사유 (캐시 뒷부분)
    output_schema: dict[str, Any]  # 제공자 어댑터가 Structured Output 제약에 맞게 바꿔 보낼 수 있습니다(결정 E5)
    max_output_tokens: int
    images: tuple[ModelImage, ...] = ()
    # 같은 공고의 모든 호출이 함께 쓰는 출력 형식(맡은 섹션만 채움). 제공자 출력 형식이 프롬프트 앞에 붙는 경우 호출마다 형식이 달라
    # 원문 캐시가 깨지므로(실측 OpenAI: 캐시 읽기 0건), 어댑터가 켜져 있으면 이것을 보냅니다. 응답 검사는 output_schema로 합니다
    shared_schema: dict[str, Any] | None = None
    # 도구를 쓰는 요청(재확인 에이전트). tools가 있으면 모델은 답 대신 도구 호출을 돌려주고(ModelResponse.tool_calls),
    # 다음 요청에 앞선 차례(turns)를 붙여 이어 갑니다. 반복은 모델 층이 아니라 부르는 쪽이 하므로 한 차례가 complete() 한 번입니다
    tools: tuple[ToolSpec, ...] = ()
    turns: tuple[ToolTurn, ...] = ()

    def tool_chars(self) -> int:
        """도구 설명·앞선 차례가 입력에 더하는 글자 수(비용 상한 계산용)."""
        specs = sum(len(t.name) + len(t.description) + len(json.dumps(t.parameters, ensure_ascii=False)) for t in self.tools)
        turns = sum(len(c.name) + len(c.arguments) for turn in self.turns for c in turn.calls) + sum(len(r) for turn in self.turns for r in turn.results)
        return specs + turns


@dataclass(frozen=True)
class ModelResponse:
    raw_text: str
    model_id: str
    stop_reason: StopReason
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    usage: dict[str, Any] | None = None  # 제공자가 준 사용량 원본 (job 기록용)
    reasoning_tokens: int | None = None  # 출력 토큰 중 추론 토큰 (제공자가 주면)
    cache_hit: bool = False  # 이전에 받은 같은 요청의 응답을 다시 씀 (call_cache, 비용 0)
    tool_calls: tuple[ToolCall, ...] = ()  # 도구를 쓰는 요청에서 모델이 요청한 호출(있으면 raw_text는 비어 있을 수 있음)


class ModelError(Exception):
    """제공자 호출 실패. transient=True면 제한 재시도 대상입니다(네트워크·한도 초과·일시 장애).
    maybe_billed=True: 요청이 제공자에 닿은 뒤 실패해(응답 대기 중 시간 초과·응답이 중간에 끊김) 비용이 청구됐을 수 있습니다.
    code: 측정 기록(usage)에 남길 분류 코드(예: HTTP_429, TIMEOUT, BUDGET). 오류 문구는 기록에 넣지 않습니다."""

    def __init__(self, message: str, *, transient: bool, maybe_billed: bool = False, code: str | None = None):
        super().__init__(message)
        self.transient = transient
        self.maybe_billed = maybe_billed
        self.code = code


class ExtractionModel(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


def supports_tools(model: Any) -> bool:
    """감싼 모델(사용량·예산·캐시·대체)을 따라가 실제 제공자가 도구 호출을 지원하는지 봅니다.
    제공자는 클래스 속성 supports_tools로 알립니다. 대체 감싸기(FallbackOnErrorModel)는 먼저 부르는 쪽(primary)을 봅니다."""
    for _ in range(10):  # 감싸기는 몇 겹뿐입니다
        flag = getattr(type(model), "supports_tools", None)
        if isinstance(flag, bool):
            return flag
        inner = getattr(model, "primary", None) or getattr(model, "model", None)
        if inner is None or isinstance(inner, str):
            return False
        model = inner
    return False
