"""AI 출력 형식(ai-output v1) — extraction 내부 형식이며 팀 공유 계약이 아닙니다.

손으로 따로 적지 않고 계약 스키마에서 만듭니다. 계약이 바뀌면 AI 출력 형식도 같이 바뀝니다.
- 근거: evidenceIds → quoteRefs (맨 위 quotes[]의 ref). 위치는 결합기가 계산합니다.
- 계산값 제외: 가격 amountKrw, 위치 regionCode, 공고 전체 신청 방법 applicationChannels(신청 일정에서 계산).
  원문 sourceAmount·sourceUnit·region은 그대로 받습니다.
- 프로그램 전용 정의(근거 위치, 문서, 원본 참조, 검증, 품질 보고서 등) 제외.
- 섹션별 호출(결정 E2)을 위해 모든 섹션과 coverage 항목은 선택입니다.
"""

from __future__ import annotations

import copy
from functools import cache
from typing import Any

from mujuthaek_extraction.contracts import tools

VERSION = "1"
SECTIONS = ("notice", "locations", "schedules", "supplyGroups", "eligibility", "selectionRules", "requiredDocuments", "guidance")
# 코드가 만든 조각(공급표 옮기기)이 결합기에 넘기는 검수 이슈 목록: [{"supplyGroupId", "code", "description"}].
# AI 출력 칸이 아니므로 결합기가 형식 검사 전에 꺼냅니다(2026-10-23: 나누지 못한 두 금액 칸을 조용히 버리지 않게)
CODE_ISSUES = "_reviewIssues"
PROGRAM_ONLY_DEFS = {
    "evidence",
    "locator",
    "issue",
    "fieldAssessment",
    "document",
    "sourceReference",
    "comparisonField",
    "apiComparison",
    "verification",
    "quality",
    "applicationSummary",
    "areaSummary",
}
COMPUTED_PROPERTIES = {"price": {"amountKrw", "amountRangeKrw"}, "location": {"regionCode"}, "notice": {"applicationChannels"}}
QUOTE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ref", "documentId", "text"],
    "properties": {
        "ref": {"type": "string", "pattern": r"^\S+$"},
        "documentId": {"type": "string", "minLength": 1},
        "text": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "unitRow": {"type": "integer", "minimum": 0},
    },
}


def _drop(node: Any, names: set[str]) -> None:
    if isinstance(node, dict):
        for name in names:
            node.get("properties", {}).pop(name, None)
        if isinstance(node.get("required"), list):
            node["required"] = [x for x in node["required"] if x not in names]
        for child in node.values():
            _drop(child, names)
    elif isinstance(node, list):
        for child in node:
            _drop(child, names)


def _rewrite(node: Any, ids: tuple[str, ...]) -> Any:
    """계약 스키마 사이의 참조를 문서 안 참조(#/$defs/)로 바꾸고 evidenceIds를 quoteRefs로 바꾼 사본을 돌려줍니다."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref":
                for schema_id in ids:
                    value = value.replace(f"{schema_id}#/$defs/", "#/$defs/")
                if not value.startswith("#/$defs/"):
                    raise ValueError(f"AI 출력 형식으로 바꿀 수 없는 참조입니다: {value}")
            elif key == "properties":
                value = {("quoteRefs" if k == "evidenceIds" else k): v for k, v in value.items()}
            elif key == "required" and isinstance(value, list):
                value = ["quoteRefs" if k == "evidenceIds" else k for k in value]
            out[key] = _rewrite(value, ids)
        return out
    if isinstance(node, list):
        return [_rewrite(child, ids) for child in node]
    return node


@cache
def schema() -> dict[str, Any]:
    """계약 스키마에서 프로그램 전용 정의와 계산값을 뺀 AI 출력 JSON 스키마를 만들어 돌려줍니다(한 번만 만들고 재사용)."""
    schemas = tools().SCHEMAS
    common = schemas["schemas/notice-common.v1.json"]
    eligibility = schemas["schemas/eligibility.v1.json"]
    extracted = schemas["schemas/extracted-notice.v1.json"]
    ids = (common["$id"], eligibility["$id"])

    defs: dict[str, Any] = {}
    for source in (common, eligibility):
        for name, definition in source["$defs"].items():
            if name in PROGRAM_ONLY_DEFS:
                continue
            if name in defs:
                raise ValueError(f"계약 정의 이름이 겹칩니다: {name}")
            defs[name] = copy.deepcopy(definition)
    for name, properties in COMPUTED_PROPERTIES.items():
        _drop(defs[name], properties)
    coverage = copy.deepcopy(defs["coverage"])
    coverage.pop("required", None)
    defs["sectionCoverage"] = coverage
    defs["quote"] = QUOTE

    properties: dict[str, Any] = {"quotes": {"type": "array", "items": {"$ref": "#/$defs/quote"}}}
    properties |= {section: copy.deepcopy(extracted["properties"][section]) for section in SECTIONS}
    properties["coverage"] = {"$ref": "#/$defs/sectionCoverage"}
    properties["missingFields"] = {"type": "array", "items": {"$ref": "#/$defs/missing"}}
    root = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"extraction ai-output v{VERSION}",
        "type": "object",
        "additionalProperties": False,
        "required": ["quotes"],
        "properties": properties,
        "$defs": defs,
    }
    return _rewrite(root, ids)
