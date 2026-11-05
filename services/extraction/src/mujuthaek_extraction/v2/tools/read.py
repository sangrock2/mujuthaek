"""읽기 도구: 에이전트가 원문 조각을 id와 함께 봅니다. 결과는 짧은 JSON 글자입니다(긴 결과가 차례마다 다시 보내지는 비용을 줄임)."""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from mujuthaek_extraction.v2.context import V2Context

MAX_LINES = 60
MAX_ROWS = 40


@tool
def outline(runtime: ToolRuntime[V2Context, Any]) -> str:
    """원문 차례: 제목 줄(id·글), 표 목록(id·쪽·열 제목·행 수), 글자 없는 그림 쪽."""
    return _dump(runtime.context.document.outline())


@tool
def view_lines(start: str, count: int, runtime: ToolRuntime[V2Context, Any]) -> str:
    """start 줄(id, 예: p3.12)부터 count개 줄을 봅니다(최대 60). 사이에 있는 표는 id·행 수·열 제목만 보입니다."""
    try:
        return _dump({"lines": runtime.context.document.view_lines(start, min(max(count, 1), MAX_LINES))})
    except KeyError:
        return _error("UNKNOWN_ID", f"없는 줄 id입니다: {start}")


@tool
def view_table(table: str, start: int, count: int, runtime: ToolRuntime[V2Context, Any]) -> str:
    """표(id, 예: t4-1)의 행을 칸과 함께 봅니다(행 id 포함, 한 번에 최대 40행). 칸 id는 <행 id>.c<칸 번호(0부터)>입니다."""
    try:
        return _dump(runtime.context.document.view_table(table, max(start, 0), min(max(count, 1), MAX_ROWS)))
    except KeyError:
        return _error("UNKNOWN_ID", f"없는 표 id입니다: {table}")


@tool
def search(query: str, runtime: ToolRuntime[V2Context, Any]) -> str:
    """원문에서 글자를 찾아 줄·표 행 id를 돌려줍니다(공백 무시). 똑같은 글자가 없으면 비슷한 줄을 유사도와 함께 돌려줍니다."""
    return _dump({"hits": runtime.context.document.search(query)})


READ_TOOLS = (outline, view_lines, view_table, search)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(code: str, message: str) -> str:
    return _dump({"error": code, "message": message})
