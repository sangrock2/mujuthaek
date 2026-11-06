"""섹션별 형식 도구 add_<섹션>: 도구 정의(JSON 스키마)로 그 섹션의 항목 형식을 그대로 보여 줍니다.

2026-11-06 첫 실제 실행: 자유 형식 add_items로는 모델이 지시문 글만 보고 칸을 짐작해 형식 검사에서 거절되고 다시 시도하다
담당마다 호출 상한(10번)을 다 썼음(자격 담당 출력 7천 토큰에 항목 0개). V1은 출력 형식을 모델에 강제했던 것과 같은 효과를 도구 정의로 냅니다.
- V1 섹션 형식을 펼치고(재귀 3단계) 참조를 풀어 한 덩어리로(V1 엄격 모드 변환과 같은 펼치기)
- null을 허용하는 칸·목록 칸은 생략 가능(코드가 채움 → 출력이 짧음), 조건부 규칙(if/then)은 빼고 결합기가 원래 형식으로 다시 검사
- 인용 ref(quoteRefs) 대신 근거(evidence): 항목에는 필수, 하위 객체에는 선택(없으면 위 근거를 이어받음)
- 원문 문장(originalText)은 선택: 비우면 코드가 첫 근거의 원문으로 채움(옮겨 적다 글자가 달라지는 일 방지)

담당들은 맡은 섹션이 달라도 같은 도구 목록(모든 담당 섹션의 add 도구)을 받습니다. 지시·도구·원문이 같은 앞부분이라 한 번 캐시에 올린 것을
모든 담당이 다시 읽습니다(2026-11-06 두 번째 실제 실행: 담당마다 도구가 달라 앞부분 2~3만 토큰을 담당마다 따로 캐시에 올림).
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool

from mujuthaek_extraction.model.strict_schema import _inline_all, _unroll
from mujuthaek_extraction.rules.base import call_schema
from mujuthaek_extraction.v2.tools.write import SectionContext, add

EVIDENCE = {
    "type": "array",
    "minItems": 1,
    "description": "근거: 원문 조각 id(p3.12 · t4-1.r3.c2) 또는 {id, part(그 조각 안의 일부 글자 그대로)}",
    "items": {
        "anyOf": [
            {"type": "string"},
            {"type": "object", "properties": {"id": {"type": "string"}, "part": {"type": "string"}}, "required": ["id", "part"], "additionalProperties": False},
        ]
    },
}
DROPPED = ("if", "then", "else", "not")
ORIGINAL_TEXT = "원문 문장 그대로. 비우면 첫 근거의 원문으로 채웁니다"


@lru_cache(maxsize=64)
def item_schema(section: str, documents: tuple[str, ...]) -> dict[str, Any]:
    schema = _inline_all(_unroll(copy.deepcopy(call_schema((section,), list(documents)))))
    node = schema["properties"][section]
    return _relax(node if section == "notice" else node["items"], top=True)


def add_tool(section: str, documents: tuple[str, ...]) -> StructuredTool:
    """add_<섹션>: 항목들을 넣습니다(notice는 항목 하나). 넣는 즉시 형식·근거를 검사해 틀린 항목만 「위치: 이유」로 돌려줍니다."""
    item = item_schema(section, documents)
    if section == "notice":

        def run_notice(item: dict[str, Any], runtime: ToolRuntime[SectionContext, Any]) -> str:
            return add(runtime.context, section, [item])

        schema = {"type": "object", "properties": {"item": item}, "required": ["item"]}
        return StructuredTool.from_function(func=run_notice, name="add_notice", description="공고(notice) 항목 하나를 넣습니다.", args_schema=schema)

    def run(items: list[dict[str, Any]], runtime: ToolRuntime[SectionContext, Any]) -> str:
        return add(runtime.context, section, items)

    schema = {"type": "object", "properties": {"items": {"type": "array", "items": item}}, "required": ["items"]}
    description = (
        f"{section} 항목을 넣습니다(맡은 항목을 한 차례에 다: 호출 하나에 50개 안팎까지, 더 많으면 같은 차례에 여러 번). "
        "값이 있는 칸만 적고 근거 evidence를 붙입니다."
    )
    return StructuredTool.from_function(func=run, name=f"add_{section}", description=description, args_schema=schema)


def shared_tools(sections: tuple[str, ...], documents: tuple[str, ...]) -> list[StructuredTool]:
    """모든 담당 섹션의 add 도구(순서 고정). 담당은 맡은 섹션 것만 쓰고, 다른 섹션에 넣으면 add가 NOT_MY_SECTION으로 거절합니다."""
    return [add_tool(section, documents) for section in sections]


def _relax(node: Any, top: bool = False) -> Any:
    if isinstance(node, list):
        return [_relax(child) for child in node]
    if not isinstance(node, dict):
        return node
    node = {k: v for k, v in node.items() if k not in DROPPED}
    if "allOf" in node:
        node["allOf"] = [entry for entry in (_relax(e) for e in node["allOf"]) if entry]
        if not node["allOf"]:
            del node["allOf"]
    properties = node.get("properties")
    if isinstance(properties, dict):
        properties = {name: _relax(child) for name, child in properties.items() if name != "quoteRefs"}
        had_refs = "quoteRefs" in node["properties"]
        if had_refs:
            properties["evidence"] = EVIDENCE
        required = [name for name in node.get("required", []) if name in properties and not _optional(properties[name])]
        if had_refs and top:
            required.append("evidence")
        if top and "originalText" in properties:
            properties["originalText"] = {**properties["originalText"], "description": ORIGINAL_TEXT}
            required = [name for name in required if name != "originalText"]
        node["properties"], node["required"] = properties, required
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            node[key] = _relax(node[key])
    for key in ("anyOf", "oneOf"):
        if isinstance(node.get(key), list):
            node[key] = [_relax(child) for child in node[key]]
    return node


def _optional(node: dict[str, Any]) -> bool:
    """생략해도 코드가 채우는 칸: null을 허용하거나 목록."""
    kinds = _kinds(node)
    return "null" in kinds or kinds == {"array"}


def _kinds(node: Any) -> set[str]:
    if not isinstance(node, dict):
        return set()
    found: set[str] = set()
    kind = node.get("type")
    if isinstance(kind, str):
        found.add(kind)
    elif isinstance(kind, list):
        found.update(kind)
    for key in ("anyOf", "oneOf"):
        for child in node.get(key, []):
            found |= _kinds(child)
    if node.get("const", 0) is None or None in (node.get("enum") or []):
        found.add("null")
    return found
