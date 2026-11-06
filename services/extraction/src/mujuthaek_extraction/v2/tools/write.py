"""쓰기 도구: 섹션 담당이 작업 초안에 항목을 넣고 고칩니다. 넣는 즉시 형식·근거 id를 검사해 그 항목만 「위치: 이유」로 돌려줍니다.

초안은 실행 문맥(SectionContext.draft)에 있고, 담당이 끝나면 v2.contract.to_part로 V1 AI 조각이 됩니다.
초안 전체의 검증(V1 결합·검증기)은 도구가 아니라 검증 미들웨어(v2/agents/verify.py)가 도구를 쓴 차례마다 자동으로 알려 줍니다
(2026-11-06 실제 실행: check 도구를 부르는 데 차례를 쓰고, 진짜 이유(형식 오류로 응답 전체가 버려짐) 대신 「범위 미완료」만 보여 줌).
"""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import SkipValidation

from mujuthaek_extraction.v2.context import V2Context
from mujuthaek_extraction.v2.contract import (
    ORIGINAL_TEXT_SECTIONS,
    EvidenceError,
    complete,
    errors,
    evidence_entries,
    fill_original_text,
    quote_text,
    without_evidence,
)

COVERAGE = ("EXTRACTED", "PARTIAL", "NOT_IN_SOURCE", "NOT_APPLICABLE")
JUDGED = ("notice", "eligibility")  # 판정에 쓰여 비울 수 없는 섹션
MISSING_REASONS = ("NOT_IN_SOURCE", "TO_BE_ANNOUNCED", "SOURCE_ATTACHMENT_REQUIRED", "CONFLICT", "UNREADABLE", "NOT_APPLICABLE")


@dataclass
class SectionDraft:
    """담당 하나의 작업 초안: 섹션별 항목(근거 evidence 포함, 값 있는 칸만), 섹션 상태, 누락 기록."""

    sections: tuple[str, ...]
    items: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: list[dict[str, Any]] = field(default_factory=list)
    version: int = 0  # 바뀔 때마다 1씩(검증 미들웨어가 바뀐 차례에만 다시 검증)
    finished: str | None = None  # finish로 남긴 한두 문장(검증에 새 문제가 나오면 검증 미들웨어가 거둠)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def find(self, section: str, item_id: str | None) -> int | None:
        rows = self.items.get(section, [])
        if section == "notice":
            return 0 if rows else None
        return next((i for i, row in enumerate(rows) if row.get("id") == item_id), None)

    def missing_for(self, section: str) -> list[dict[str, Any]]:
        """누락 기록 → V1 missingFields(target은 조각 안의 JSON Pointer)."""
        found = []
        for entry in self.missing:
            if entry["section"] != section:
                continue
            index = self.find(section, entry["id"])
            if index is None:
                continue
            base = f"/{section}" if section == "notice" else f"/{section}/{index}"
            found.append({"target": f"{base}/{entry['field'].strip('/')}", "reason": entry["reason"], "description": entry["description"]})
        return found


@dataclass
class SectionContext(V2Context):
    draft: SkipValidation[SectionDraft | None] = None
    documents: tuple[str, ...] = ()
    check: SkipValidation[Callable[[], list[dict[str, Any]]] | None] = None  # 지금 초안을 V1 결합·검증기로 본 이 담당 섹션의 문제(검증 미들웨어가 부름)


def add(context: SectionContext, section: str, items: list[dict[str, Any]]) -> str:
    """섹션별 형식 도구(add_<섹션>, v2/tools/typed.py)가 부르는 넣기: 항목마다 형식·근거를 검사해 맞는 것만 넣고 틀린 것은 「위치: 이유」로."""
    draft = context.draft
    if section not in draft.sections:
        return _error("NOT_MY_SECTION", f"맡은 섹션은 {', '.join(draft.sections)}입니다.")
    added, failed = [], []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            item = fill_original_text(section, item, context.document)
        problems = _problems(context, section, item, adding=True)
        if problems:
            failed.append({"id": item.get("id") if isinstance(item, dict) else None, "errors": problems})
            continue
        with draft._lock:
            draft.items.setdefault(section, []).append(copy.deepcopy(item))
            draft.version += 1
        added.append(item.get("id") or section)
    return _dump({"added": added, "failed": failed})


@tool
def update_item(section: str, item_id: str, changes: dict[str, Any], runtime: ToolRuntime[SectionContext, Any]) -> str:
    """넣은 항목을 고칩니다. changes에는 바꿀 칸만 적습니다(객체는 칸마다 합치고 그 밖은 바꿈, evidence를 적으면 근거를 바꿈).
    notice는 item_id를 비워 둡니다."""
    context = runtime.context
    draft = context.draft
    if section not in draft.sections:
        return _error("NOT_MY_SECTION", f"맡은 섹션은 {', '.join(draft.sections)}입니다.")
    index = draft.find(section, item_id)
    if index is None:
        return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다. add_{section}으로 넣습니다.")
    merged = _merge(draft.items[section][index], changes if isinstance(changes, dict) else {})
    problems = _problems(context, section, merged, adding=False)
    if problems:
        return _dump({"error": "BAD_ITEM", "errors": problems})
    with draft._lock:
        draft.items[section][index] = merged
        draft.version += 1
    return _dump({"ok": f"{section}/{item_id or 'notice'} 고침"})


@tool
def remove_item(section: str, item_id: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """넣은 항목을 뺍니다(원문에 없거나 다른 섹션 몫인 항목)."""
    draft = runtime.context.draft
    index = draft.find(section, item_id) if section in draft.sections else None
    if index is None:
        return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다.")
    with draft._lock:
        draft.items[section].pop(index)
        draft.version += 1
    return _dump({"ok": f"{section}/{item_id} 뺌"})


@tool
def set_coverage(section: str, status: str, reason: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """섹션 상태: EXTRACTED(원문 항목을 다 넣음, reason은 빈 글) · PARTIAL(원문에 있는데 못 넣은 것이 있음, reason에 무엇) ·
    NOT_IN_SOURCE(섹션 내용이 원문에 없음) · NOT_APPLICABLE(해당 없음)."""
    draft = runtime.context.draft
    if section not in draft.sections:
        return _error("NOT_MY_SECTION", f"맡은 섹션은 {', '.join(draft.sections)}입니다.")
    if status not in COVERAGE:
        return _error("BAD_STATUS", f"status는 {', '.join(COVERAGE)} 중 하나입니다.")
    if section in JUDGED and status in ("NOT_IN_SOURCE", "NOT_APPLICABLE"):
        return _error("NOT_ALLOWED", f"{section}은 판정에 쓰여 비울 수 없습니다. 원문에서 찾지 못했으면 PARTIAL로 이유를 적습니다.")
    if status != "EXTRACTED" and not reason.strip():
        return _error("REASON_REQUIRED", "EXTRACTED가 아니면 reason을 적습니다.")
    with draft._lock:
        draft.coverage[section] = {"status": status, "reason": None if status == "EXTRACTED" else reason.strip()}
        draft.version += 1
    return _dump({"ok": f"{section} {status}"})


@tool
def report_missing(section: str, item_id: str, field: str, reason: str, description: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """판정·화면에 필요한 값을 원문에서 찾지 못해 비워 둔 칸을 적습니다. field는 항목 안의 칸 경로(예: rule/expression/value),
    reason은 NOT_IN_SOURCE · TO_BE_ANNOUNCED · SOURCE_ATTACHMENT_REQUIRED · CONFLICT · UNREADABLE · NOT_APPLICABLE, description은 '~해요' 체 한 문장."""
    draft = runtime.context.draft
    if section not in draft.sections or draft.find(section, item_id) is None:
        return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다.")
    if reason not in MISSING_REASONS:
        return _error("BAD_REASON", f"reason은 {', '.join(MISSING_REASONS)} 중 하나입니다.")
    with draft._lock:
        draft.missing.append({"section": section, "id": item_id, "field": field, "reason": reason, "description": description})
        draft.version += 1
    return _dump({"ok": "적음"})


@tool
def finish(summary: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """맡은 섹션을 다 넣고 고쳤으면 부릅니다. 마지막 넣기·고치기와 같은 차례에 함께 부르면 차례가 줄어듭니다: 그 차례의 도구가 실행된 뒤
    검증에 새 문제가 없으면 그대로 끝나고, 새 문제가 있으면 검증 결과로 알려 줍니다. summary는 넣은 것·남은 문제 한두 문장."""
    draft = runtime.context.draft
    with draft._lock:
        draft.finished = summary.strip() or "끝"
    return _dump({"ok": "끝냄(검증에 새 문제가 있으면 알려 줌)"})


WRITE_TOOLS = (update_item, remove_item, set_coverage, report_missing, finish)  # 넣기는 섹션별 형식 도구(add_<섹션>, typed.py)


def _problems(context: SectionContext, section: str, item: Any, adding: bool) -> list[str]:
    if not isinstance(item, dict):
        return ["항목은 객체여야 합니다."]
    draft = context.draft
    if section != "notice":
        if not isinstance(item.get("id"), str) or not item["id"]:
            return ["/id: 항목 id가 필요합니다."]
        if adding and draft.find(section, item["id"]) is not None:
            return [f"/id: 이미 있는 id입니다({item['id']}). 고치려면 update_item을 씁니다."]
    elif adding and draft.find(section, None) is not None:
        return ["notice는 하나뿐입니다. 고치려면 update_item을 씁니다."]
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return ["/evidence: 근거 id를 1개 이상 붙입니다."]
    found = []
    for entry in evidence_entries(item):  # 하위 항목(가격·예외 등)의 근거까지
        try:
            quote_text(context.document, entry)
        except EvidenceError as error:
            found.append(f"/evidence: {error}")
    original = item.get("originalText")
    if section in ORIGINAL_TEXT_SECTIONS and isinstance(original, str) and original.strip() and not context.document.contains(original):
        found.append("/originalText: 원문에 그대로 있는 글이 아닙니다. 원문 글자 그대로 적거나 비워 둡니다(비우면 첫 근거의 원문으로 채움)")
    body = complete(section, without_evidence(item), context.documents)
    found += errors(section, body, context.documents)
    return found[:5]


def _merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            merged[key] = value if key == "evidence" else _merge(base.get(key), value)
        return merged
    return copy.deepcopy(patch)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(code: str, message: str) -> str:
    return _dump({"error": code, "message": message})
