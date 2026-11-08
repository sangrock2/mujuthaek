"""출력 한도에서 잘린 넣기 호출 살리기(LangChain AgentMiddleware.wrap_model_call·wrap_tool_call).

2026-11-08 최종 비교 dcco-24804: 서류 담당이 서류 54개를 넣기 호출 하나(인자 5만 자)에 담다가 출력 한도(21,000토큰)에서 잘림. 잘린 인자는
JSON이 아니라 LangChain이 실행할 수 없는 호출(invalid_tool_calls)로 두고, 실행할 호출이 없으니 담당이 첫 차례에서 끝나 서류 0개(섹션 FAILED)가 됨.
이미 낸 출력 2.1만 토큰도 버려짐.
- 잘린 넣기(add_<섹션>)는 인자에서 끝까지 온 항목만 꺼내 그 항목으로 부른 호출로 바꿉니다(다음 차례 대화에 남는 호출 인자도 꺼낸 항목만).
  넣기 결과에 잘렸다는 것과 남은 항목을 이어서 넣으라는 안내를 붙여, 담당이 다음 차례에 나머지를 넣습니다.
- 다른 도구 호출이 잘렸으면 바꾸지 않습니다(LangChain이 다음 요청에 그 호출의 오류 답을 붙임). 실행할 호출이 하나도 없으면 담당이 끝나고,
  끝내기 전에 잘려 멈춘 담당의 섹션은 run_section이 사람 확인(PARTIAL)으로 보냅니다.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

ITEMS_START = re.compile(r'\s*\{\s*"items"\s*:\s*\[')  # 넣기 도구 인자의 앞({"items": [)


def cut_off(message: Any) -> bool:
    """출력 한도에서 잘린 답인지(Responses API status incomplete, 이유 max_output_tokens)."""
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("status") == "incomplete" and (meta.get("incomplete_details") or {}).get("reason") == "max_output_tokens"


def complete_items(arguments: str) -> list[Any] | None:
    """잘린 넣기 인자(「{"items": [항목, …, 잘린 항목」)에서 끝까지 온 항목들. 넣기 인자 모양이 아니면 None."""
    start = ITEMS_START.match(arguments)
    if start is None:
        return None
    decoder = json.JSONDecoder()
    items: list[Any] = []
    index = start.end()
    while True:
        while index < len(arguments) and arguments[index] in " \t\r\n,":
            index += 1
        if index >= len(arguments) or arguments[index] == "]":
            return items
        try:
            item, index = decoder.raw_decode(arguments, index)
        except json.JSONDecodeError:
            return items
        items.append(item)


class CutCallMiddleware(AgentMiddleware):
    def __init__(self) -> None:
        super().__init__()
        self.cut: dict[str, str] = {}  # 살린 호출 id → 넣기 결과에 붙일 안내

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        response = handler(request)
        message = response if isinstance(response, AIMessage) else next((m for m in response.result if isinstance(m, AIMessage)), None)
        if message is None or not cut_off(message):
            return response
        fixed = self._salvage(message)
        if fixed is message:
            return response
        if isinstance(response, AIMessage):
            return fixed
        return dataclasses.replace(response, result=[fixed if m is message else m for m in response.result])

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        result = handler(request)
        notice = self.cut.get(request.tool_call.get("id"))
        if notice is None or not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        try:
            body = json.loads(result.content)
        except json.JSONDecodeError:
            body = None
        content = json.dumps({**body, "cut": notice}, ensure_ascii=False) if isinstance(body, dict) else f"{result.content}\n{notice}"
        return result.model_copy(update={"content": content})

    def _salvage(self, message: AIMessage) -> AIMessage:
        calls, invalid, rewritten = list(message.tool_calls), [], {}
        for call in message.invalid_tool_calls:
            name = call.get("name") or ""
            items = complete_items(call.get("args") or "") if name.startswith("add_") else None
            if items is None or not call.get("id"):
                invalid.append(call)
                continue
            args = {"items": items}
            calls.append({"name": name, "args": args, "id": call["id"], "type": "tool_call"})
            rewritten[call["id"]] = json.dumps(args, ensure_ascii=False, separators=(",", ":"))  # 모델이 쓴 모양대로 짧게(다음 차례 입력)
            self.cut[call["id"]] = _notice(name, items)
        if not rewritten:
            return message
        content = message.content
        if isinstance(content, list):  # Responses API는 답 내용의 호출 블록을 다음 요청에 그대로 보내므로 그 인자도 함께 바꿈
            content = [
                {**block, "arguments": rewritten[block["call_id"]], "status": "completed"}
                if isinstance(block, dict) and block.get("type") == "function_call" and block.get("call_id") in rewritten
                else block
                for block in content
            ]
        return message.model_copy(update={"content": content, "tool_calls": calls, "invalid_tool_calls": invalid})


def _notice(name: str, items: list[Any]) -> str:
    last = next((item.get("id") for item in reversed(items) if isinstance(item, dict) and item.get("id")), None)
    got = f"끝까지 온 앞 항목 {len(items)}개(마지막 {last})만 넣기에 썼습니다" if items else "항목을 하나도 받지 못했습니다"
    return (
        f"응답이 출력 한도에서 잘려 이 호출은 {got}. 잘린 뒤 항목은 받지 않았으니 {name}으로 이어서 넣습니다(이미 넣은 항목은 다시 보내지 않음). "
        "한 차례 출력에도 한도가 있으니 남은 항목이 많으면 이번 차례에 넣을 만큼만 넣고 나머지는 다음 차례에 넣습니다."
    )
