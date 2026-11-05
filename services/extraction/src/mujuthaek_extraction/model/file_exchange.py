"""파일 교환 모델(EXTRACTION_MODEL_MODE=standin): 요청을 파일로 쓰고 답 파일을 기다립니다. 유료 API 비용 없이 흐름을 시험합니다(2026-11-05).

쓰임: 에이전트 방식의 흐름 결함(도구 오용·중복·버려지는 결과·형식 오류·예외)을 찾는 시험. 답은 대역 에이전트가 요청 파일을 읽고
답 파일을 한 번 써서 냅니다(요청 읽기·답 쓰기 외의 보조 도구는 쓰지 않음). 운영 모델과 행동이 달라 성능 수치(재현율·비용)로 쓰지 않습니다.

요청 파일 <폴더>/<번호>-<호출>.request.json
  call: 호출 이름 · system/user/instructions: 공통 지시·원문·호출 지시 · images: 그림 파일 경로
  도구 요청이면 tools(이름·설명·입력 형식)·toolChoice(required 또는 반드시 부를 도구)·parallelTools·turns(앞선 도구 호출·결과·덧붙인 글)
  도구 요청이 아니면 outputSchema(답 JSON 형식)
  answerPath·answerFormat: 답을 쓸 곳과 모양
답 파일(answerPath)  도구 요청: {"tool_calls": [{"name": "...", "arguments": {...}}]}  /  그 밖: {"text": "<출력 형식에 맞는 JSON 글자>"}
"""

from __future__ import annotations

import itertools
import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mujuthaek_extraction.model.base import ModelError, ModelRequest, ModelResponse, StopReason, ToolCall

SAFE = re.compile(r"[^0-9A-Za-z가-힣_.-]+")
TOOL_FORMAT = '{"tool_calls": [{"name": "<도구 이름>", "arguments": {<그 도구 입력 형식에 맞는 값>}}]}'
TEXT_FORMAT = '{"json": {<outputSchema에 맞는 JSON 객체를 그대로>}}'


class FileExchangeModel:
    supports_tools = True

    def __init__(self, folder: Path, *, timeout_seconds: float = 3_600, poll_seconds: float = 1.0, sleep: Callable[[float], None] = time.sleep):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._sleep = sleep
        self._numbers = itertools.count(1)
        self._lock = threading.Lock()

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self._lock:
            number = next(self._numbers)
        stem = f"{number:04d}-{SAFE.sub('_', request.call_name)[:60]}"
        answer = self.folder / f"{stem}.answer.json"
        images = []
        for index, image in enumerate(request.images, start=1):
            path = self.folder / f"{stem}-image{index}.png"
            path.write_bytes(image.data)
            images.append(str(path))
        body: dict[str, Any] = {
            "call": request.call_name,
            "system": request.system,
            "user": request.user,
            "instructions": request.instructions,
            "images": images,
            "answerPath": str(answer),
        }
        if request.tools:
            body.update(
                tools=[{"name": t.name, "description": t.description, "parameters": t.parameters} for t in request.tools],
                toolChoice=request.forced_tool or "required",
                parallelTools=request.parallel_tools,
                turns=[
                    {"calls": [{"name": c.name, "arguments": c.arguments} for c in turn.calls], "results": list(turn.results), "note": turn.note}
                    for turn in request.turns
                ],
                answerFormat=TOOL_FORMAT,
            )
        else:
            body.update(outputSchema=request.output_schema, answerFormat=TEXT_FORMAT)
        (self.folder / f"{stem}.request.md").write_text(_markdown(body), encoding="utf-8")  # 대역이 읽는 글(긴 줄 없이)
        temporary = self.folder / f"{stem}.request.tmp"
        temporary.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(self.folder / f"{stem}.request.json")  # 다 쓴 뒤에 보이게(대역이 반쯤 쓴 요청을 읽지 않게)
        deadline = time.monotonic() + self.timeout_seconds
        while not answer.exists():
            if time.monotonic() > deadline:
                raise ModelError(f"대역 답을 기다리다 시간이 지났습니다: {stem}", transient=False, code="STANDIN_TIMEOUT")
            self._sleep(self.poll_seconds)
        return _response(answer, number, bool(request.tools))

    def cache_identity(self, request: ModelRequest) -> dict[str, Any]:
        return {"provider": "standin"}


def _response(path: Path, number: int, tools: bool) -> ModelResponse:
    try:
        answer = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ModelError(f"대역 답 파일을 읽지 못했습니다: {error}", transient=False, code="STANDIN_BAD_ANSWER") from error
    if not isinstance(answer, dict):
        raise ModelError("대역 답은 JSON 객체여야 합니다.", transient=False, code="STANDIN_BAD_ANSWER")
    if tools:
        calls = tuple(
            ToolCall(
                f"call_{number}_{index}",
                str(call.get("name")),
                call["arguments"] if isinstance(call.get("arguments"), str) else json.dumps(call.get("arguments") or {}, ensure_ascii=False),
            )
            for index, call in enumerate(answer.get("tool_calls") or [], start=1)
            if isinstance(call, dict)
        )
        return ModelResponse("", "standin", StopReason.END, input_tokens=0, output_tokens=0, tool_calls=calls)
    # 큰 JSON 답을 글자로 한 번 더 감싸면(text) 따옴표 처리 실수가 잦아 객체를 그대로 받습니다(json). text도 받음
    value = answer["json"] if "json" in answer else answer.get("text")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return ModelResponse(text, "standin", StopReason.END, input_tokens=0, output_tokens=0)


def _pretty(text: str) -> str:
    """JSON 글자면 줄을 나눠 보기 좋게(한 줄이 너무 길면 읽기 도구가 자름), 아니면 그대로."""
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        return text


def _markdown(body: dict[str, Any]) -> str:
    """대역 에이전트가 읽는 요청 글. API가 받는 것과 같은 내용을 순서대로 적고 마지막에 답 쓰는 법을 둡니다."""
    out = [
        f"# 요청 {body['call']}",
        "당신은 API 모델 대신 답합니다. 아래 내용만 보고 답을 정해, 맨 끝 「답 쓰는 법」대로 답 파일을 한 번 씁니다. 다른 파일은 읽지 않습니다.",
        "\n## 공통 지시(system)\n",
        body["system"],
        "\n## 원문·문맥(user)\n",
        _pretty(body["user"]),
        "\n## 이번 호출 지시(instructions)\n",
        body["instructions"],
    ]
    if body.get("images"):
        out += ["\n## 그림(파일을 열어 봅니다)\n", *(f"- {path}" for path in body["images"])]
    if "tools" in body:
        out += ["\n## 쓸 수 있는 도구\n", "```json", json.dumps(body["tools"], ensure_ascii=False, indent=1), "```"]
        for number, turn in enumerate(body["turns"], start=1):
            out.append(f"\n## 앞선 차례 {number}\n")
            for call, result in zip(turn["calls"], turn["results"], strict=False):
                out += [f"호출: {call['name']}", "```json", _pretty(call["arguments"]), "```", "결과:", "```json", _pretty(result), "```"]
            if turn.get("note"):
                out += ["\n### 이어서 받은 글\n", _pretty(turn["note"])]
        choice = body["toolChoice"]
        rule = "도구를 하나 이상 부릅니다" if choice == "required" else f"반드시 {choice} 도구를 부릅니다"
        many = "한 번에 여러 도구를 부를 수 있습니다" if body.get("parallelTools") else "도구는 하나만 부릅니다"
        how = f"{rule}. {many}. arguments는 그 도구의 입력 형식(parameters)에 맞는 JSON 객체입니다."
        out += ["\n## 답 쓰는 법\n", how, f"답 파일: {body['answerPath']}", f"모양: {body['answerFormat']}"]
    else:
        out += [
            "\n## 답 형식(outputSchema)\n",
            "```json",
            json.dumps(body["outputSchema"], ensure_ascii=False, indent=1),
            "```",
            "\n## 답 쓰는 법\n",
            "outputSchema에 맞는 JSON 객체 하나를 만들어 json 칸에 그대로 넣습니다(글자로 감싸지 않음).",
            f"답 파일: {body['answerPath']}",
            f"모양: {body['answerFormat']}",
        ]
    return "\n".join(out) + "\n"
