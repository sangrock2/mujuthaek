"""AI 출력 형식 → 제공자 Structured Output(엄격 모드)용 스키마 (결정 E5).

엄격 모드는 JSON Schema 일부만 받으므로 조건부 규칙(if/then/not)·길이·범위·형식 제약을 빼고, 모든 필드를 필수로 만들며
원래 선택이던 필드는 null을 허용합니다. 뺀 제약은 결합기가 원래 스키마로 다시 검사합니다(제공자 검사를 믿지 않음).
"""

from __future__ import annotations

import copy
from typing import Any

DROPPED_KEYWORDS = {
    "if",
    "then",
    "else",
    "not",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "uniqueItems",
    "description",
    "$schema",
    "title",
}
SCALAR_ITEMS = {"type": ["string", "number", "boolean"]}


def _convert(node: Any, optional_names: set[str]) -> Any:
    """스키마 조각을 엄격 모드 모양으로 바꾼 사본을 돌려줍니다. 원래 선택이던 필드 이름은 optional_names에 모읍니다."""
    if isinstance(node, list):
        return [_convert(child, optional_names) for child in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in DROPPED_KEYWORDS:
            continue
        if key == "allOf":
            if all(isinstance(rule, dict) and "if" in rule for rule in value):
                continue  # 계약의 allOf는 모두 조건부 규칙입니다
            raise ValueError("조건부 규칙이 아닌 allOf는 변환하지 않습니다")
        if key == "oneOf":
            key = "anyOf"
        if key == "const":
            key, value = "enum", [value]
        if key in ("properties", "$defs"):  # 아래는 필드·정의 이름이므로 키워드로 다루지 않습니다
            out[key] = {name: _convert(child, optional_names) for name, child in value.items()}
        else:
            out[key] = _convert(value, optional_names)
    types = out.get("type")
    if (types == "array" or (isinstance(types, list) and "array" in types)) and "items" not in out:
        out["items"] = SCALAR_ITEMS
    if "properties" in out:
        required = set(node.get("required", []))
        for name, schema in list(out["properties"].items()):
            if name not in required:
                optional_names.add(name)
                out["properties"][name] = {"anyOf": [schema, {"type": "null"}]}
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    return out


MAX_DEPTH = 3  # 재귀 정의(조건식)를 펼칠 단계 수. 더 깊은 조건은 UNSTRUCTURED로 남깁니다(결정 E5)
REF = "#/$defs/"


def _refs(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"][len(REF) :]} if isinstance(node.get("$ref"), str) and node["$ref"].startswith(REF) else set()
        for value in node.values():
            found |= _refs(value)
        return found
    if isinstance(node, list):
        return set().union(*(_refs(v) for v in node)) if node else set()
    return set()


def _reachable(start: set[str], defs: dict[str, Any]) -> set[str]:
    seen, todo = set(), list(start)
    while todo:
        name = todo.pop()
        if name not in seen and name in defs:
            seen.add(name)
            todo.extend(_refs(defs[name]))
    return seen


def _retarget(node: Any, names: set[str], suffix: str | None) -> Any:
    """names를 가리키는 참조를 name+suffix로 바꿉니다. suffix가 None이면 그 참조를 담은 anyOf 선택지를 지웁니다."""
    if isinstance(node, list):
        return [_retarget(v, names, suffix) for v in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key == "$ref" and value[len(REF) :] in names:
            if suffix is None:
                raise LookupError
            out[key] = value + suffix
        elif key in ("anyOf", "oneOf") and suffix is None:
            kept = []
            for option in value:
                try:
                    kept.append(_retarget(option, names, suffix))
                except LookupError:
                    continue
            if not kept:
                raise LookupError
            out[key] = kept
        else:
            out[key] = _retarget(value, names, suffix)
    return out


def _inline(node: Any, copies: dict[str, Any]) -> Any:
    """copies에 있는 정의를 가리키는 참조를 그 내용으로 바꿔 넣습니다."""
    if isinstance(node, list):
        return [_inline(v, copies) for v in node]
    if not isinstance(node, dict):
        return node
    target = node.get("$ref", "")[len(REF) :] if isinstance(node.get("$ref"), str) else None
    if target in copies:
        return copy.deepcopy(copies[target])
    return {k: _inline(v, copies) for k, v in node.items()}


def _unroll(schema: dict[str, Any]) -> dict[str, Any]:
    """쓰지 않는 정의를 빼고, 자기 자신을 다시 가리키는 정의(조건식)는 MAX_DEPTH 단계로 펼쳐 쓰는 자리에 직접 넣습니다.

    엄격 모드는 재귀를 받지 않고, 다른 정의를 참조하는 anyOf를 최상위에 둔 정의도 거부합니다(실측). 펼친 단계는 정의로 두지 않습니다.
    """
    defs = schema.get("$defs", {})
    used = _reachable(_refs({k: v for k, v in schema.items() if k != "$defs"}), defs)
    cyclic = {name for name in used if name in _reachable(_refs(defs[name]), defs)}
    # 가장 깊은 단계는 재귀 선택지를 지우고, 그 위 단계는 아래 단계를 직접 넣어 만듭니다.
    copies = {name: _collapse(_retarget(defs[name], cyclic, None)) for name in cyclic}
    for _ in range(MAX_DEPTH - 1):
        copies = {name: _collapse(_inline(defs[name], copies)) for name in cyclic}
    rest = _collapse(_inline({k: v for k, v in schema.items() if k != "$defs"}, copies))
    new_defs = {name: _collapse(_inline(defs[name], copies)) for name in used if name not in cyclic}
    return {**rest, "$defs": new_defs} if new_defs else rest


def _collapse(node: Any) -> Any:
    if isinstance(node, list):
        return [_collapse(v) for v in node]
    if not isinstance(node, dict):
        return node
    node = {k: _collapse(v) for k, v in node.items()}
    for key in ("anyOf", "oneOf"):
        options = node.get(key)
        if isinstance(options, list) and len(options) == 1:
            merged = {k: v for k, v in node.items() if k != key}
            merged.update(options[0])
            return merged
    return node


def to_strict(schema: dict[str, Any]) -> tuple[dict[str, Any], frozenset[str]]:
    """(엄격 모드 스키마, 원래 선택이던 필드 이름들). 응답에서 이 이름의 null은 drop_null_optionals로 지웁니다."""
    optional: set[str] = set()
    strict = _flatten(_convert(_inline_all(_unroll(copy.deepcopy(schema))), optional))
    return strict, frozenset(optional)


def _inline_all(schema: dict[str, Any]) -> dict[str, Any]:
    """펼친 뒤에는 재귀가 없으므로 모든 정의를 쓰는 자리에 직접 넣고 $defs를 없앱니다.

    엄격 모드는 정의 안에서 anyOf를 거쳐 다른 정의를 겹겹이 참조하는 형태를 거부합니다(실측: 자격 조건 rule 정의).
    """
    defs = schema.get("$defs", {})
    resolved: dict[str, Any] = {}

    def resolve(name: str) -> Any:
        if name not in resolved:
            resolved[name] = _inline(defs[name], {other: resolve(other) for other in _refs(defs[name])})
        return resolved[name]

    body = {k: v for k, v in schema.items() if k != "$defs"}
    return _inline(body, {name: resolve(name) for name in _refs(body)})


def _flatten(node: Any) -> Any:
    """anyOf 안의 anyOf를 한 단계로 펼칩니다. 엄격 모드의 중첩 깊이 제한을 줄입니다."""
    if isinstance(node, list):
        return [_flatten(v) for v in node]
    if not isinstance(node, dict):
        return node
    node = {k: ({n: _flatten(c) for n, c in v.items()} if k in ("properties", "$defs") else _flatten(v)) for k, v in node.items()}
    if isinstance(node.get("anyOf"), list):
        options = []
        for option in node["anyOf"]:
            options.extend(option["anyOf"] if isinstance(option, dict) and set(option) == {"anyOf"} else [option])
        unique = []
        for option in options:
            if option not in unique:
                unique.append(option)
        node["anyOf"] = unique
    return node


def drop_null_optionals(value: Any, optional_names: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {k: drop_null_optionals(v, optional_names) for k, v in value.items() if not (v is None and k in optional_names)}
    if isinstance(value, list):
        return [drop_null_optionals(v, optional_names) for v in value]
    return value


def keep_own(value: Any, schema: dict[str, Any]) -> Any:
    """공유 형식으로 받은 응답에서 이번 호출이 맡은 칸(맨 위·coverage)만 남깁니다. 검사는 호출 형식(output_schema)으로 합니다."""
    if not isinstance(value, dict):
        return value
    own = schema.get("properties", {})
    kept = {k: v for k, v in value.items() if k in own}
    coverage_own = (own.get("coverage") or {}).get("properties")
    if isinstance(kept.get("coverage"), dict) and coverage_own is not None:
        kept["coverage"] = {k: v for k, v in kept["coverage"].items() if k in coverage_own}
    # 맡은 목록 섹션을 null로 비우고 coverage에만 사유를 적은 경우(공유 형식은 섹션이 선택 칸이라 생김) 빈 목록으로 둡니다.
    # 실측 OpenAI LH 제주 든든전세: 공급주택목록이 첨부라 supplyGroups를 null로 → 필수 칸 누락으로 구조 호출을 다시 요청
    covered = kept.get("coverage") if isinstance(kept.get("coverage"), dict) else {}
    for key in schema.get("required", []):
        if key not in kept and (own.get(key) or {}).get("type") == "array" and isinstance(covered.get(key), dict):
            kept[key] = []
    return kept
