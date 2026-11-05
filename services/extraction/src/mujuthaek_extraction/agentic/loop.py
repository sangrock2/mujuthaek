"""도구 호출 반복: 모델 호출 한 번 = 한 차례, 차례마다 도구 하나. 총괄·하위 에이전트가 함께 씁니다.

반복은 이 코드가 합니다(모델 층의 비용 예약·사용량·호출 캐시를 그대로 지남). 마지막 차례에는 끝내기 도구만 부르게 합니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from mujuthaek_extraction.extract import ExtractionRun
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, ToolCall, ToolSpec, ToolTurn
from mujuthaek_extraction.repair.agent import BUDGET_CODES, _attempt

RECORD_CHARS = 600  # 작업 기록에 남길 도구 결과 앞부분


class Toolbox(Protocol):
    specs: tuple[ToolSpec, ...]
    finish_tool: str
    done: bool

    def run(self, call: ToolCall) -> str: ...


@dataclass
class AgentLog:
    """에이전트 하나의 기록(작업 기록 usage.agentic): 차례 수, 부른 도구 순서, 결말."""

    name: str
    turns: int = 0
    steps: list[str] = field(default_factory=list)
    outcome: str = ""  # DONE · TURN_LIMIT · NO_TOOL_CALL · MODEL_ERROR · BUDGET

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "turns": self.turns, "steps": self.steps, "outcome": self.outcome}


def run_loop(model: ExtractionModel, base: ModelRequest, toolbox: Toolbox, limit: int, run: ExtractionRun, log: AgentLog) -> None:
    turns: list[ToolTurn] = []
    log.outcome = "TURN_LIMIT"
    for turn in range(1, limit + 1):
        name = f"{base.call_name}:turn{turn}"
        final = turn == limit
        request = replace(base, call_name=name, turns=tuple(turns), tools=toolbox.specs, forced_tool=toolbox.finish_tool if final else None)
        try:
            response = model.complete(request)
        except ModelError as error:
            run.attempts.append(_attempt(request, None, error))
            run.failed_calls.append((name, str(error)))
            log.outcome = "BUDGET" if error.code in BUDGET_CODES else "MODEL_ERROR"
            return
        run.attempts.append(_attempt(request, response, None))
        log.turns = turn
        if not response.tool_calls:
            log.outcome = "NO_TOOL_CALL"
            return
        results = []
        for call in response.tool_calls:
            log.steps.append(call.name)
            result = toolbox.run(call) if not final or call.name == toolbox.finish_tool else _refuse(toolbox.finish_tool)
            results.append(_with_turns_left(result, limit - turn))
        run.raw_responses.append(
            (
                name,
                json.dumps(
                    {
                        "toolCalls": [{"name": c.name, "arguments": c.arguments[:RECORD_CHARS]} for c in response.tool_calls],
                        "results": [r[:RECORD_CHARS] for r in results],
                    },
                    ensure_ascii=False,
                ),
            )
        )
        turns.append(ToolTurn(response.tool_calls, tuple(results)))
        if toolbox.done:
            log.outcome = "DONE"
            return


def _refuse(finish_tool: str) -> str:
    return json.dumps({"error": "FINAL_TURN", "message": f"마지막 차례입니다. {finish_tool}로 끝냅니다."}, ensure_ascii=False)


def _with_turns_left(result: str, left: int) -> str:
    try:
        value = json.loads(result)
    except ValueError:
        return result
    if not isinstance(value, dict):
        return result
    value["turnsLeft"] = left
    if left == 1:
        value["notice"] = "다음 차례가 마지막입니다. 다음에는 끝내기 도구를 부릅니다."
    return json.dumps(value, ensure_ascii=False)
