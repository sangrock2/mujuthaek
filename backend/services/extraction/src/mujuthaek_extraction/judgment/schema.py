"""판정 틀 검사: 판정 담당이 준 JSON Schema 원본(contracts/schemas)과, 스키마로 못 잡는 ID 유일성·뜻 규칙(judgment/sanity.py)."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from mujuthaek_extraction.contracts import contracts_dir
from mujuthaek_extraction.judgment.sanity import semantic_errors

SCHEMAS = {
    "housing-judgment.v1": "housing-judgment.v1.json",
    "business-space-judgment.v1": "business-space-judgment.v1.json",
    "startup-support-judgment.v1": "startup-support-judgment.v1.json",
}


@cache
def _validator(name: str) -> Draft202012Validator:
    path = contracts_dir() / "schemas" / SCHEMAS[name]
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker())


def _ids(node: Any) -> list[str]:
    """group·조건(ANY_OF 안 포함)·우대의 id. 안내(notes)에는 id가 없습니다."""
    if isinstance(node, dict):
        own = [node["id"]] if isinstance(node.get("id"), str) else []
        return own + [i for key, value in node.items() if key != "notes" for i in _ids(value)]
    if isinstance(node, list):
        return [i for value in node for i in _ids(value)]
    return []


def frame_errors(frame: dict[str, Any]) -> list[str]:
    """틀 스키마 위반, 겹친 ID, 틀 읽기가 거절하는 뜻 위반(거꾸로 된 범위·공백뿐인 글자 등). 값은 메시지에 넣지 않고 위치만 적습니다."""
    name = frame.get("schema")
    if name not in SCHEMAS:
        return [f"알 수 없는 틀: {name!r}"]
    errors = [f"/{'/'.join(str(p) for p in e.absolute_path)}: {e.validator}" for e in _validator(name).iter_errors(frame)]
    ids = _ids({k: v for k, v in frame.items() if k != "notes"})
    errors += [f"겹친 id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return errors + semantic_errors(frame)
