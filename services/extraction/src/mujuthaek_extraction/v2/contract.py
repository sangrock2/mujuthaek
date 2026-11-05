"""V2 작업 항목 → V1 AI 조각(섹션 출력 형식). 결합·검증·게시는 V1의 검증된 코드(evaluate_parts 이후)를 그대로 씁니다.

에이전트는 의미 있는 칸과 근거(evidence)만 넘깁니다. 이 모듈이
- 계약 형식에서 빠진 칸을 채우고(null을 허용하는 칸은 null, 목록은 빈 목록),
- 근거 id로 원문 인용을 만들어 quotes·quoteRefs를 붙이고(인용은 늘 원문 그대로),
- 섹션 형식으로 검사해 오류를 「위치: 이유」로 돌려줍니다.

근거 한 개는 id(「p3.12」·「t4-1.r3.c2」) 또는 {"id": id, "part": 그 조각 안의 일부 글자}입니다. 한 줄에 값이 여럿이면 part로 좁힙니다.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from mujuthaek_extraction.rules.base import call_schema
from mujuthaek_extraction.v2.document import DocumentModel

LIST_SECTIONS = ("locations", "supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "guidance")


class EvidenceError(ValueError):
    """근거 id가 없거나 part가 그 조각에 없습니다."""


def quote_text(document: DocumentModel, evidence: str | dict[str, Any]) -> str:
    """근거 하나 → 인용 글(원문 그대로)."""
    ref, part = (evidence, None) if isinstance(evidence, str) else (str(evidence.get("id", "")), evidence.get("part"))
    try:
        text = document.text(ref)
    except KeyError as error:
        raise EvidenceError(f"없는 근거 id입니다: {ref}") from error
    if part:
        if part not in text:
            raise EvidenceError(f"{ref}에 「{str(part)[:40]}」 글자가 없습니다")
        return part
    return text


def complete(section: str, item: dict[str, Any], documents: tuple[str, ...]) -> dict[str, Any]:
    """빠진 필수 칸 채우기: null을 허용하면 null, 목록이면 빈 목록. 그 밖(문자열·객체 등 값이 꼭 필요한 칸)은 비워 검사에서 알립니다."""
    schema, defs = _item_schema(section, documents)
    return _fill(copy.deepcopy(item), schema, defs)


def errors(section: str, item: dict[str, Any], documents: tuple[str, ...], limit: int = 5) -> list[str]:
    """채운 항목이 섹션 형식에 맞는지. 「위치: 이유」 최대 limit개."""
    validator = _validator(section, documents)
    part = {"quotes": [], section: item if section == "notice" else [item], "coverage": {section: {"status": "EXTRACTED", "reason": None}}, "missingFields": []}
    skip = 1 if section == "notice" else 2
    found = []
    for error in validator.iter_errors(part):
        leaf = best_match(error.context) if error.context else error
        path = "/".join(str(x) for x in list(leaf.absolute_path)[skip:])
        if path.startswith("quoteRefs"):
            continue  # 근거는 to_part가 붙임
        found.append(f"/{path}: {leaf.message[:240]}")
    return found[:limit]


def to_part(
    section: str,
    items: list[dict[str, Any]],
    document: DocumentModel,
    documents: tuple[str, ...],
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """항목들(각각 evidence 칸) → V1 AI 조각. 같은 인용 글은 ref 하나를 같이 씁니다."""
    refs: dict[str, str] = {}
    built = []
    for item in items:
        evidence = item.get("evidence") or []
        body = complete(section, {k: v for k, v in item.items() if k != "evidence"}, documents)
        body["quoteRefs"] = [refs.setdefault(text, f"q{len(refs) + 1}") for text in dict.fromkeys(quote_text(document, e) for e in evidence)]
        built.append(body)
    part: dict[str, Any] = {
        "quotes": [{"ref": ref, "text": text} for text, ref in refs.items()],
        section: built[0] if section == "notice" and built else built if section != "notice" else None,
        "coverage": {section: coverage or {"status": "EXTRACTED", "reason": None}},
        "missingFields": [],
    }
    return part


@lru_cache(maxsize=64)
def _section_schema(section: str, documents: tuple[str, ...]) -> dict[str, Any]:
    return call_schema((section,), list(documents))


@lru_cache(maxsize=64)
def _validator(section: str, documents: tuple[str, ...]) -> Draft202012Validator:
    return Draft202012Validator(_section_schema(section, documents))


def _item_schema(section: str, documents: tuple[str, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = _section_schema(section, documents)
    defs = schema.get("$defs", {})
    node = schema["properties"][section]
    node = node.get("items", node) if section != "notice" else node
    return _resolve(node, defs), defs


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return node


def _fill(value: Any, schema: dict[str, Any], defs: dict[str, Any]) -> Any:
    schema = _resolve(schema, defs)
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        for name in schema.get("required", []):
            if name in value:
                continue
            prop = _resolve(schema["properties"].get(name, {}), defs)
            if _allows_null(prop, defs):
                value[name] = None
            elif _types(prop, defs) == {"array"}:
                value[name] = []
        for name, child in value.items():
            if name in schema["properties"]:
                value[name] = _fill(child, _object_branch(schema["properties"][name], defs, child), defs)
    elif isinstance(value, list) and "items" in schema:
        return [_fill(child, _object_branch(schema["items"], defs, child), defs) for child in value]
    return value


def _object_branch(schema: Any, defs: dict[str, Any], value: Any) -> dict[str, Any]:
    """anyOf·oneOf 가운데 값에 맞는 갈래. 객체는 구분 칸(const·enum, 예: 조건식 kind)이 맞는 갈래 중 칸이 가장 많이 겹치는 것
    (조건식처럼 갈래마다 필수 칸이 다른 재귀 형식에서 첫 갈래를 고르면 다른 갈래의 칸을 채움). 검사는 errors가 합니다."""
    schema = _resolve(schema, defs)
    branches = list(_branches(schema, defs))
    if isinstance(value, list):
        return next((b for b in branches if "items" in b), schema)
    if not isinstance(value, dict):
        return schema
    fitting = [b for b in branches if "properties" in b and _discriminators_match(b, defs, value)]
    return max(fitting, key=lambda b: len(set(value) & set(b["properties"])), default=schema)


def _branches(schema: dict[str, Any], defs: dict[str, Any]):
    found = False
    for key in ("anyOf", "oneOf"):
        for branch in schema.get(key, []):
            found = True
            yield from _branches(_resolve(branch, defs), defs)
    if not found:
        yield schema


def _discriminators_match(branch: dict[str, Any], defs: dict[str, Any], value: dict[str, Any]) -> bool:
    for name, prop in branch["properties"].items():
        prop = _resolve(prop, defs)
        allowed = [prop["const"]] if "const" in prop else prop.get("enum")
        if name in value and allowed is not None and value[name] not in allowed:
            return False
    return True


def _types(schema: dict[str, Any], defs: dict[str, Any]) -> set[str]:
    schema = _resolve(schema, defs)
    found: set[str] = set()
    kind = schema.get("type")
    if isinstance(kind, str):
        found.add(kind)
    elif isinstance(kind, list):
        found.update(kind)
    for key in ("anyOf", "oneOf"):
        for branch in schema.get(key, []):
            found |= _types(branch, defs)
    if "const" in schema and schema["const"] is None or None in (schema.get("enum") or []):
        found.add("null")
    return found


def _allows_null(schema: dict[str, Any], defs: dict[str, Any]) -> bool:
    return "null" in _types(schema, defs)
