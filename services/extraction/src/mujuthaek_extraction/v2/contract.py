"""V2 작업 항목 → V1 AI 조각(섹션 출력 형식). 결합·검증·게시는 V1의 검증된 코드(evaluate_parts 이후)를 그대로 씁니다.

에이전트는 의미 있는 칸과 근거(evidence)만 넘깁니다. 이 모듈이
- 계약 형식에서 빠진 칸을 채우고(null을 허용하는 칸은 null, 목록은 빈 목록),
- 근거 id로 원문 인용을 만들어 quotes·quoteRefs를 붙이고(인용은 늘 원문 그대로),
- 섹션 형식으로 검사해 오류를 「위치: 이유」로 돌려줍니다.

근거 한 개는 id(「p3.12」·「t4-1.r3.c2」) 또는 {"id": id, "part": 그 조각 안의 일부 글자}입니다. 한 줄에 값이 여럿이면 part로 좁힙니다.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from mujuthaek_extraction.assemble.quotes import MIN_QUOTE_CHARS, normalize
from mujuthaek_extraction.rules.base import call_schema
from mujuthaek_extraction.v2.document import DocumentModel

LIST_SECTIONS = ("locations", "supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "guidance")
CELL_REF = re.compile(r"(.+\.r\d+)\.c\d+")
ORIGINAL_TEXT_SECTIONS = ("eligibility", "selectionRules")  # 항목에 원문 문장 칸(originalText)이 꼭 있는 섹션


class EvidenceError(ValueError):
    """근거 id가 없거나 part가 그 조각에 없습니다."""


def quote_text(document: DocumentModel, evidence: str | dict[str, Any]) -> str:
    """근거 하나 → 인용 글(원문 그대로). 빈 칸은 근거가 아닙니다(2026-11-06 실제 실행: 합쳐진 빈 칸을 가리킨 근거가 빈 인용이 되어
    결합기가 그 담당 응답 전체를 버림 — 선정 규칙 21개가 0개로)."""
    ref, part = (evidence, None) if isinstance(evidence, str) else (str(evidence.get("id", "")), evidence.get("part"))
    try:
        text = document.text(ref)
    except KeyError as error:
        raise EvidenceError(f"없는 근거 id입니다: {ref}") from error
    if part:
        if part not in text:
            raise EvidenceError(f"{ref}에 「{str(part)[:40]}」 글자가 없습니다")
        text = part
    if not text.strip():
        raise EvidenceError(f"{ref}는 빈 칸입니다(합쳐진 칸). 글자가 있는 칸이나 행을 가리킵니다")
    return text


def located_text(document: DocumentModel, evidence: str | dict[str, Any]) -> str:
    """근거 하나 → V1 결합기에 넘길 인용 글. 결합기는 인용 글을 원문에서 다시 찾아 위치를 정하므로(V1 방식) 원문에 한 곳만 있고 너무 짧지 않은
    가장 작은 범위를 넘깁니다: 그대로 쓸 수 없으면 칸·일부 글자 → 그 행·줄로 넓힘. 넓힌 글에도 값은 그대로 들어 있어 값 대조는 같습니다.
    2026-11-06 세 번째 실제 실행: 가점표 칸 글자(「50점」은 원문 4곳, 「0점」은 40곳)를 그대로 넘겨 결합기가 위치를 못 정하고 가점 5행을 뺌."""
    text = quote_text(document, evidence)
    if _distinct(document, text):
        return text
    ref = evidence if isinstance(evidence, str) else str(evidence.get("id", ""))
    cell = CELL_REF.fullmatch(ref)
    wider = document.text(cell.group(1)) if cell else document.text(ref)  # 칸 → 그 행, 일부 글자 → 그 줄·행 전체
    return wider if wider.strip() else text


def _distinct(document: DocumentModel, text: str) -> bool:
    return len(normalize(text)) >= MIN_QUOTE_CHARS and document.occurrences(text) == 1


def source_sentence(document: DocumentModel, evidence: str | dict[str, Any]) -> str:
    """근거 하나 → 사람이 읽을 원문 문장(표 행은 칸 구분자 없이 칸 글자를 이음). originalText를 비운 항목에 채웁니다.
    V1 검증기는 공백·칸 구분자를 무시하고 원문과 대조하므로 이은 글도 원문 그대로로 확인됩니다."""
    text = quote_text(document, evidence)
    if text.strip().startswith("|") and text.strip().endswith("|"):
        return " ".join(cell.strip() for cell in text.strip()[1:-1].split("|") if cell.strip())
    return text.strip()


def fill_original_text(section: str, item: dict[str, Any], document: DocumentModel) -> dict[str, Any]:
    """원문 문장 칸(originalText)이 있는 섹션에서 비워 둔 항목은 첫 근거의 원문으로 채웁니다(모델이 옮겨 적다 글자가 달라지는 일 방지:
    2026-11-06 실제 실행의 ORIGINAL_TEXT_NOT_FOUND). 근거가 틀렸으면 그대로 둡니다(넣기 검사가 근거 오류로 알림)."""
    if section not in ORIGINAL_TEXT_SECTIONS or (isinstance(item.get("originalText"), str) and item["originalText"].strip()):
        return item
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return item
    try:
        return {**item, "originalText": source_sentence(document, evidence[0])}
    except EvidenceError:
        return item


def complete(section: str, item: dict[str, Any], documents: tuple[str, ...]) -> dict[str, Any]:
    """빠진 필수 칸 채우기: null을 허용하면 null, 목록이면 빈 목록. 그 밖(문자열·객체 등 값이 꼭 필요한 칸)은 비워 검사에서 알립니다."""
    schema, defs = _item_schema(section, documents)
    return _fill(copy.deepcopy(item), schema, defs)


def errors(section: str, item: dict[str, Any], documents: tuple[str, ...], limit: int = 5) -> list[str]:
    """채운 항목이 섹션 형식에 맞는지. 「위치: 이유」 최대 limit개."""
    validator = _validator(section, documents)
    item = _placeholder_refs(item)  # 하위 객체의 quoteRefs는 to_part가 채우므로(위 근거 이어받기) 빈 목록 때문에 객체 전체가 틀린 것으로 보이지 않게
    part = {"quotes": [], section: item if section == "notice" else [item], "coverage": {section: {"status": "EXTRACTED", "reason": None}}, "missingFields": []}
    skip = 1 if section == "notice" else 2
    found = []
    for error in validator.iter_errors(part):
        leaf = best_match(error.context) if error.context else error
        path = "/".join(str(x) for x in list(leaf.absolute_path)[skip:])
        if "quoteRefs" in path.split("/"):
            continue  # 근거는 to_part가 붙임(하위 항목은 위 근거를 이어받음)
        found.append(f"/{path}: {_reason(validator.schema, leaf)}")
    return found[:limit]


def _reason(root: dict[str, Any], leaf: Any) -> str:
    """조건부 규칙(if/then) 오류는 조건을 풀어 씁니다. 2026-11-06 실제 실행: 「endsAt: None should not be valid under {'type': 'null'}」만
    보고 담당이 「endStatus가 FIXED이면 마감일이 필요하다」를 몰라 같은 항목을 두 번 더 거절당함(형식 도구는 if/then을 보여 주지 않음)."""
    path = list(leaf.absolute_schema_path)
    if "then" in path:
        at = len(path) - 1 - path[::-1].index("then")
        node = _walk(root, path[:at])
        condition = _condition(node.get("if")) if isinstance(node, dict) else None
        if condition:
            return f"{condition}이면 {_consequence(leaf)}"[:240]
    return leaf.message[:240]


def _walk(root: dict[str, Any], path: list[Any]) -> Any:
    node: Any = root
    for key in path:
        while isinstance(node, dict) and "$ref" in node and key != "$ref":
            node = _resolve(node, root.get("$defs", {}))
        if key == "$ref":
            continue
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return None
    return _resolve(node, root.get("$defs", {}))


def _condition(schema: Any) -> str | None:
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        return None
    parts = []
    for name, prop in schema["properties"].items():
        if not isinstance(prop, dict):
            continue
        if "const" in prop:
            parts.append(f"{name}가 {prop['const']}")
        elif "enum" in prop:
            parts.append(f"{name}가 {'·'.join(str(v) for v in prop['enum'])} 중 하나")
        elif isinstance(prop.get("not"), dict) and "const" in prop["not"]:
            parts.append(f"{name}가 {prop['not']['const']}가 아니")
    return " 그리고 ".join(parts) or None


def _consequence(leaf: Any) -> str:
    value = leaf.validator_value
    if leaf.validator == "not" and isinstance(value, dict) and value.get("type") == "null":
        return "이 칸을 비울 수 없습니다(값이 필요함)"
    if leaf.validator == "required":
        return leaf.message.replace(" is a required property", " 칸이 필요합니다")
    if leaf.validator == "const":
        return f"값은 {value}이어야 합니다"
    if leaf.validator == "enum":
        return f"값은 {', '.join(str(v) for v in value)} 중 하나여야 합니다"
    if leaf.validator == "minItems":
        return f"{value}개 이상 넣어야 합니다"
    if leaf.validator == "type":
        return f"{value} 형식이어야 합니다"
    return leaf.message


def to_part(
    section: str,
    items: list[dict[str, Any]],
    document: DocumentModel,
    documents: tuple[str, ...],
    coverage: dict[str, Any] | None = None,
    missing: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """항목들(각각 evidence 칸) → V1 AI 조각. 같은 인용 글은 ref 하나를 같이 씁니다.
    하위 항목(모집 수·가격·예외 등 quoteRefs가 있는 객체)은 자기 evidence가 있으면 그것을, 없으면 위 항목의 근거를 이어받습니다
    (그 값이 위 근거에 없으면 검증기가 「값이 인용에 없음」으로 알려 에이전트가 하위 근거를 붙임)."""
    refs: dict[str, str] = {}

    def ref_of(entry: str | dict[str, Any]) -> str:
        return refs.setdefault(located_text(document, entry), f"q{len(refs) + 1}")

    built = []
    for item in items:
        body = complete(section, without_evidence(item), documents)
        _attach(body, item, [], ref_of)
        built.append(body)
    _unique_inner_ids(built)
    part: dict[str, Any] = {
        "quotes": [{"ref": ref, "documentId": document.source_id, "text": text} for text, ref in refs.items()],
        section: built[0] if section == "notice" and built else built if section != "notice" else None,
        "coverage": {section: coverage or {"status": "EXTRACTED", "reason": None}},
        "missingFields": list(missing or []),
    }
    return part


def _unique_inner_ids(items: list[dict[str, Any]]) -> None:
    """항목 안 하위 항목(예외 등)의 id가 다른 id와 겹치면 위 항목 id를 앞에 붙입니다. id는 공고 안에서 하나여야 하는데(계약 DUPLICATE_ID)
    V1 결합기는 항목 id 겹침만 풂. 2026-11-06 다섯 번째 실제 실행: 청년·고령자 소득 조건의 자녀 가산 예외에 같은 id를 붙여, 고치지 못한 쪽
    조건이 조건식을 잃고(격리) 사람 확인으로 감."""
    seen = {item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}
    for item in items:
        if not isinstance(item, dict):
            continue
        for node in _inner_objects(item):
            if not isinstance(node.get("id"), str) or node["id"] not in seen:
                if isinstance(node.get("id"), str):
                    seen.add(node["id"])
                continue
            new_id, count = f"{item.get('id')}.{node['id']}", 2
            while new_id in seen:
                new_id, count = f"{item.get('id')}.{node['id']}.{count}", count + 1
            node["id"] = new_id
            seen.add(new_id)


def _inner_objects(value: Any):
    for child in value.values() if isinstance(value, dict) else value if isinstance(value, list) else []:
        if isinstance(child, dict):
            yield child
        if isinstance(child, dict | list):
            yield from _inner_objects(child)


def _placeholder_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (v or ["q1"]) if k == "quoteRefs" and isinstance(v, list) else _placeholder_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_placeholder_refs(v) for v in value]
    return value


def without_evidence(value: Any) -> Any:
    """evidence 칸을 모든 깊이에서 뺀 값(형식 검사·채우기용)."""
    if isinstance(value, dict):
        return {k: without_evidence(v) for k, v in value.items() if k != "evidence"}
    if isinstance(value, list):
        return [without_evidence(v) for v in value]
    return value


def evidence_entries(value: Any) -> list[str | dict[str, Any]]:
    """모든 깊이의 근거들(쓰기 도구가 id가 다 있는지 확인)."""
    found: list[str | dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "evidence" and isinstance(child, list):
                found += child
            else:
                found += evidence_entries(child)
    elif isinstance(value, list):
        for child in value:
            found += evidence_entries(child)
    return found


def _attach(body: Any, original: Any, inherited: list[str], ref_of: Callable[[str | dict[str, Any]], str]) -> None:
    if isinstance(body, dict) and isinstance(original, dict):
        own = original.get("evidence")
        mine = list(dict.fromkeys(ref_of(e) for e in own)) if isinstance(own, list) and own else inherited
        if "quoteRefs" in body:
            body["quoteRefs"] = mine
        for key, child in body.items():
            if key != "quoteRefs" and key in original:
                _attach(child, original[key], mine, ref_of)
    elif isinstance(body, list) and isinstance(original, list):
        for child, source in zip(body, original, strict=False):
            _attach(child, source, inherited, ref_of)


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
