"""쓰기 도구: 섹션 담당이 작업 초안에 항목을 넣고 고칩니다. 넣는 즉시 형식·근거 id를 검사해 그 항목만 「위치: 이유」로 돌려줍니다.

초안은 실행 문맥(SectionContext.draft)에 있고, 담당이 끝나면 v2.contract.to_part로 V1 AI 조각이 됩니다.
초안 전체의 검증(V1 결합·검증기)은 도구가 아니라 검증 미들웨어(v2/agents/verify.py)가 도구를 쓴 차례마다 자동으로 알려 줍니다
(2026-11-06 실제 실행: check 도구를 부르는 데 차례를 쓰고, 진짜 이유(형식 오류로 응답 전체가 버려짐) 대신 「범위 미완료」만 보여 줌).
"""

from __future__ import annotations

import copy
import json
import re
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
    fill_scope,
    quote_text,
    without_evidence,
)
from mujuthaek_extraction.v2.document import DocumentModel

COVERAGE = ("EXTRACTED", "PARTIAL", "NOT_IN_SOURCE", "NOT_APPLICABLE")
JUDGED = ("notice", "eligibility")  # 판정에 쓰여 비울 수 없는 섹션
MISSING_REASONS = ("NOT_IN_SOURCE", "TO_BE_ANNOUNCED", "SOURCE_ATTACHMENT_REQUIRED", "CONFLICT", "UNREADABLE", "NOT_APPLICABLE")
PATCH_HINT = "거절된 항목은 update_item(같은 id, 틀린 칸만)으로 고치면 넣어집니다. 항목 전체를 다시 보내지 않습니다."
RULE_STATUS_CLEARS = {"UNSTRUCTURED": "expression", "STRUCTURED": "reason"}  # 규칙 상태(status)를 바꾸면 계약상 비워야 하는 칸
# 넣은 항목의 고치기가 거절되면 앞 내용이 그대로 남습니다. 저장 기록 401개 담당에서 이런 거절 102번 뒤 3번은 그 항목을 뺐음(2026-11-09 유료 확인
# jbdc-16011: 나이 경계일 경고가 걸린 신생아 자녀 나이를 고치다 형식 거절 두 번 뒤 뺌 → 사람 확인 대신 값이 사라짐)
KEPT_AS_IS = (
    "고치지 않았습니다(항목은 앞 내용 그대로). 오류를 고쳐 다시 부릅니다. 고치지 못해도 항목을 빼지 않습니다(검증 경고가 남으면 그 항목은 사람이 확인)."
)
# 근거를 항목 밖에 적는 실수: 마지막 항목을 근거 없이 닫고 목록에 「evidence:[」 글을 넣은 뒤, 근거 id를 도구 인자 맨 위에 적거나 빠뜨림.
# 맨 위에 적으면 모르는 인자라 호출 전체가, 빠뜨리면 그 항목이 거절됨(2026-11-09 유료 측정·확인: 호출 상한 10번에 끊긴 자격 담당 셋
# jbdc-16011·bmc-75·gbdc-e544가 이 거절에 2~4차례를 씀, LangSmith 원래 인자 6건 중 맨 위 근거 2건·근거 없음 4건)
STRAY_MARK = re.compile(r"\s*evidence\b", re.IGNORECASE)


@dataclass
class SectionDraft:
    """담당 하나의 작업 초안: 섹션별 항목(근거 evidence 포함, 값 있는 칸만), 섹션 상태, 누락 기록."""

    sections: tuple[str, ...]
    items: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: list[dict[str, Any]] = field(default_factory=list)
    version: int = 0  # 바뀔 때마다 1씩(검증 미들웨어가 바뀐 차례에만 다시 검증)
    finished: str | None = None  # finish로 남긴 한두 문장(검증에 새 문제가 나오면 검증 미들웨어가 거둠)
    # 넣을 때 거절되어 초안에 없는 항목 (섹션, id) → 이유. 같은 id를 넣으면 지움. 검증 미들웨어가 「고칠 것」으로 계속 알림
    # (2026-11-06 23건 측정: 첫 차례에 근거 없이 거절된 자산·자동차 기준을 담당이 다시 넣지 않고 「등록했어요」로 끝내 16값이 빠짐)
    rejected: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    # 거절된 항목 그대로 (섹션, id) → 항목. update_item으로 틀린 칸만 고치면 넣습니다(2026-11-07 23건 측정: 거절된 항목을 통째로
    # 다시 보내는 데 출력 토큰의 7%, 자격 담당은 12%를 씀)
    pending: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
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


def tuck_evidence(document: DocumentModel, items: Any, stray: Any = None) -> tuple[Any, Any, list[str]]:
    """근거를 항목 밖에 적은 실수를 바로잡아 (항목들, 옮기지 못한 맨 위 근거, 바로잡은 내용)을 돌려줍니다. 목록에 낀 「evidence:[」 글은 빼고,
    그 바로 앞 항목(글이 없으면 마지막 항목)에 자기 근거가 없을 때만 맨 위 근거(stray)를 넣습니다. 맨 위 근거도 없으면 「evidence:[」 글이
    있을 때만 그 항목 하위 칸(조건식·예외 등)의 근거를 씁니다(거절된 담당도 그렇게 고침). 원문에 없는 근거 id면 바로잡지 않습니다."""
    if not isinstance(items, list):
        return items, stray, []
    kept: list[Any] = []
    target = None
    for entry in items:
        if isinstance(entry, str) and STRAY_MARK.match(entry):
            target = len(kept) - 1 if kept and isinstance(kept[-1], dict) else target
            continue
        kept.append(entry)
    marked = target is not None
    if target is None and stray is not None and kept and isinstance(kept[-1], dict):
        target = len(kept) - 1
    if target is None or _own_evidence(kept[target]):
        return kept, stray, []
    item = kept[target]
    nested = [ref if isinstance(ref, str) else str(ref.get("id") or "") for ref in evidence_entries(item) if isinstance(ref, str | dict)]
    refs = ([stray] if isinstance(stray, str) else stray) if stray is not None else (list(dict.fromkeys(ref for ref in nested if ref)) if marked else [])
    if not _resolves(document, refs):
        return kept, stray, []
    kept[target] = {**item, "evidence": refs}
    label = item.get("id") or "이"
    if stray is not None:
        return kept, None, [f"{label} 항목: 도구 인자 맨 위에 적은 근거를 항목 안으로 옮겨 넣었습니다"]
    return (
        kept,
        None,
        [f"{label} 항목: 근거가 항목 밖으로 빠져(「evidence:[」) 하위 칸의 근거({', '.join(refs[:5])})를 항목 근거로 넣었습니다(다르면 update_item으로 고침)"],
    )


def _own_evidence(item: dict[str, Any]) -> bool:
    return isinstance(item.get("evidence"), list) and bool(item["evidence"])


def _resolves(document: DocumentModel, refs: Any) -> bool:
    """근거 목록이 비지 않았고 id가 모두 원문에 있는지(part가 있으면 그 조각 안에 있는지까지)."""
    if not isinstance(refs, list) or not refs:
        return False
    try:
        for ref in refs:
            if not isinstance(ref, str | dict):
                return False
            quote_text(document, ref)
    except EvidenceError:
        return False
    return True


def add(context: SectionContext, section: str, items: list[dict[str, Any]], tucked: list[str] | None = None) -> str:
    """섹션별 형식 도구(add_<섹션>, v2/tools/typed.py)가 부르는 넣기: 항목마다 형식·근거를 검사해 맞는 것만 넣고 틀린 것은 「위치: 이유」로.
    tucked는 넣기 전에 바로잡은 근거 위치(tuck_evidence)로, 결과에 함께 알립니다."""
    draft = context.draft
    if section not in draft.sections:
        return _error("NOT_MY_SECTION", f"맡은 섹션은 {', '.join(draft.sections)}입니다.")
    added, failed, kept = [], [], False
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            item = fill_scope(section, fill_original_text(section, item, context.document), context.documents)
        problems = _problems(context, section, item, adding=True)
        item_id = item.get("id") if isinstance(item, dict) else None
        if problems:
            failed.append({"id": item_id, "errors": problems})
            if isinstance(item_id, str) and item_id and draft.find(section, item_id) is None:  # 같은 id가 이미 있으면 빠진 것이 아님
                with draft._lock:
                    draft.rejected[(section, item_id)] = problems[:2]
                    draft.pending[(section, item_id)] = copy.deepcopy(item)
                    draft.version += 1  # 거절만 있는 차례에 finish를 함께 불러도 검증이 다시 보고 알리게
                kept = True
            continue
        with draft._lock:
            # 같은 id 검사는 잠근 뒤 다시 해요: 한 차례의 넣기는 동시에 돌아, 검사 사이에 같은 id가 먼저 들어가면 둘 다 들어갔어요(2026-11-10 재검토)
            duplicate = draft.find(section, item_id) is not None
            if not duplicate:
                draft.items.setdefault(section, []).append(copy.deepcopy(item))
                draft.rejected.pop((section, item_id), None)
                draft.pending.pop((section, item_id), None)
                draft.version += 1
        if duplicate:
            failed.append({"id": item_id, "errors": [f"/id: 이미 있는 id입니다({item_id}). 고치려면 update_item을 씁니다."]})
            continue
        added.append(item.get("id") or section)
    note = {"note": " ".join(tucked) + ". 근거(evidence)는 항목 객체 안에 적습니다."} if tucked else {}
    return _dump({"added": added, "failed": failed, **({"hint": PATCH_HINT} if kept else {}), **note})


@tool
def update_item(section: str, item_id: str, changes: dict[str, Any], runtime: ToolRuntime[SectionContext, Any]) -> str:
    """넣은 항목이나 넣을 때 거절된 항목을 고칩니다. changes에는 바꿀 칸만 적습니다(객체는 칸마다 합치고 그 밖은 바꿈, evidence를 적으면
    근거를 바꿈). 규칙 상태(status)를 바꾸면 맞지 않게 된 칸(UNSTRUCTURED면 expression, STRUCTURED면 reason)은 비웁니다.
    거절된 항목은 고쳐서 맞으면 넣습니다. notice는 item_id를 비워 둡니다."""
    context = runtime.context
    draft = context.draft
    if section not in draft.sections:
        return _error("NOT_MY_SECTION", f"맡은 섹션은 {', '.join(draft.sections)}입니다.")
    # 한 차례의 도구는 동시에 돌아요. 고칠 항목은 잠근 채 꺼내 두고(base), 쓸 때 그 자리에 아직 같은 항목이 있을 때만 씁니다.
    # 예전엔 자리만 잠금 밖에서 찾아, 같은 차례의 remove_item이 앞 항목을 빼면 다른 항목을 덮어쓰고(e4를 고치는데 e5가 사라짐)
    # 같은 항목을 고치는 두 호출은 둘 다 「고침」으로 답하며 앞 고침이 사라졌어요(2026-11-10 코드 검토·재검토)
    with draft._lock:
        index = draft.find(section, item_id)
        base = draft.items[section][index] if index is not None else None
    if base is None and (section, item_id) in draft.pending:
        return _patch_pending(context, section, item_id, changes)
    if base is None:
        return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다. add_{section}으로 넣습니다.")
    # 고치며 넣은 예외의 비운 원문 글도 넣을 때처럼 근거로 채웁니다(2026-11-07 dudc-8934: 가산 행 예외는 넣은 조건을 고치며 더함)
    merged, lost = _apply(base, changes)
    if lost:
        return _bad_path(lost)
    merged = fill_scope(section, fill_original_text(section, merged, context.document), context.documents)
    problems = _problems(context, section, merged, adding=False)
    if problems:
        return _dump({"error": "BAD_ITEM", "errors": problems, "message": KEPT_AS_IS})
    with draft._lock:
        index = draft.find(section, item_id)
        if index is None or draft.items[section][index] is not base:
            return _error("CHANGED_MEANWHILE", f"같은 차례의 다른 도구가 {section}/{item_id or 'notice'}를 바꾸거나 뺐습니다. 다음 차례에 다시 고칩니다.")
        draft.items[section][index] = merged
        draft.version += 1
    return _dump({"ok": f"{section}/{item_id or 'notice'} 고침"})


@tool
def remove_item(section: str, item_id: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """넣은 항목을 뺍니다(원문에 없거나 다른 섹션 몫인 항목)."""
    draft = runtime.context.draft
    with draft._lock:  # 자리는 잠근 뒤 찾아요(같은 차례의 다른 도구가 목록을 바꿀 수 있음, update_item 참고)
        index = draft.find(section, item_id) if section in draft.sections else None
        if index is None:
            return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다.")
        draft.items[section].pop(index)
        draft.version += 1
    return _dump({"ok": f"{section}/{item_id} 뺌"})


@tool
def set_coverage(section: str, status: str, reason: str, runtime: ToolRuntime[SectionContext, Any]) -> str:
    """섹션 상태: PARTIAL(원문에 있는데 못 넣은 것이 있음, reason에 무엇) · NOT_IN_SOURCE(섹션 내용이 원문에 없음) ·
    NOT_APPLICABLE(해당 없음) · EXTRACTED(reason은 빈 글). 항목을 넣은 섹션은 부르지 않아도 EXTRACTED입니다."""
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


def _patch_pending(context: SectionContext, section: str, item_id: str, changes: Any) -> str:
    """넣을 때 거절된 항목을 바꿀 칸만 고쳐, 맞으면 넣습니다. 아직 틀리면 고친 채로 남겨 두고 이유를 돌려줍니다."""
    draft = context.draft
    with draft._lock:  # update_item과 같이: 꺼낸 거절 항목이 쓸 때도 그대로일 때만 씀
        base = draft.pending.get((section, item_id))
    if base is None:
        return _error("UNKNOWN_ITEM", f"{section}에 {item_id} 항목이 없습니다. add_{section}으로 넣습니다.")
    merged, lost = _apply(base, changes)
    if lost:
        return _bad_path(lost)
    merged = fill_scope(section, fill_original_text(section, merged, context.document), context.documents)
    problems = _problems(context, section, merged, adding=True)
    with draft._lock:
        if draft.pending.get((section, item_id)) is not base:
            return _error("CHANGED_MEANWHILE", f"같은 차례의 다른 도구가 {section}/{item_id}를 바꾸거나 넣었습니다. 다음 차례에 다시 고칩니다.")
        if problems:
            draft.pending[(section, item_id)] = merged
            draft.rejected[(section, item_id)] = problems[:2]
        else:
            draft.items.setdefault(section, []).append(merged)
            draft.pending.pop((section, item_id), None)
            draft.rejected.pop((section, item_id), None)
        draft.version += 1
    if problems:
        return _dump({"error": "BAD_ITEM", "errors": problems, "message": "아직 넣지 않았습니다. 남은 칸을 update_item으로 고칩니다."})
    return _dump({"ok": f"{section}/{item_id} 고쳐 넣음"})


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
    texts = _original_text_problems(context.document, section, item)
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return [_no_own_evidence(item), *texts][:5]
    found = []
    for entry in evidence_entries(item):  # 하위 항목(가격·예외 등)의 근거까지
        try:
            quote_text(context.document, entry)
        except EvidenceError as error:
            found.append(f"/evidence: {error}")
    found += texts
    body = complete(section, without_evidence(item), context.documents)
    found += errors(section, body, context.documents)
    return found[:5]


def _original_text_problems(document: DocumentModel, section: str, item: dict[str, Any]) -> list[str]:
    """원문 문장 칸(originalText)이 원문 그대로인지: 항목 칸과 하위 칸(예외 등) 모두, V1 검증기와 같은 기준으로.
    하위 칸은 어느 하위 항목(id)의 어떤 글인지와 가장 비슷한 원문 줄을 함께 알립니다(2026-11-06 5건 재측정 bmc-72: 원문 한 줄
    「- 출생자녀별 가산비율 : 1명 10%p, 2명 이상 20%p」를 예외 둘로 나누며 가운데를 뺀 「- 출생자녀별 가산비율 : 2명 이상 20%p」를 적음.
    넣을 때는 하위 칸을 보지 않았고, 검증 결과는 「exceptions/3」 순번만 알려 담당이 다른 예외를 고친 뒤 그만둠 → 소득·자산 기준이 사람 확인으로)."""
    found = []
    for pointer, node in _original_texts(item):
        text = node["originalText"]
        if not text.strip() or document.verbatim(text) or (not pointer and section not in ORIGINAL_TEXT_SECTIONS):
            continue
        if not pointer:
            found.append(
                f"/originalText: 원문에 그대로 있는 글이 아닙니다{_closest(document, text)}. "
                "원문 글자 그대로 적거나 비워 둡니다(비우면 첫 근거의 원문으로 채움)"
            )
            continue
        named = f"({node['id']})" if isinstance(node.get("id"), str) and node["id"] else ""
        empty = "(예외는 근거를 붙이고 비워 두면 그 근거의 원문으로 채움)" if pointer.startswith("/exceptions/") else ""
        found.append(
            f"{pointer}/originalText{named}: 「{text[:80]}」는 원문에 이어진 글자 그대로 있지 않습니다{_closest(document, text)}. "
            f"원문 글자를 빼거나 바꾸지 말고, 원문에서 이어진 부분(한 줄의 일부만 써도 됨)이나 그 줄 전체를 적습니다{empty}"
        )
    return found


def _original_texts(value: Any, pointer: str = ""):
    """(항목 안 위치, originalText가 있는 객체). 항목 자체는 위치가 빈 글."""
    if isinstance(value, dict):
        if isinstance(value.get("originalText"), str):
            yield pointer, value
        for key, child in value.items():
            if key != "evidence":
                yield from _original_texts(child, f"{pointer}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _original_texts(child, f"{pointer}/{index}")


def _closest(document: DocumentModel, text: str) -> str:
    near = document.closest(text)
    return f"(가장 비슷한 원문 {near['id']} 「{near['text'].strip()[:80]}」)" if near else ""


def _no_own_evidence(item: dict[str, Any]) -> str:
    """항목 자체 근거가 빈 거절 이유. 하위 칸(조건식·예외·가격 등)에만 근거를 붙였으면 그 id를 함께 보여 줍니다
    (2026-11-06 5건 재측정 bmc-106: 「근거 id를 1개 이상 붙입니다」만 두 번 받은 자격 담당이 어느 칸인지 몰라
    성년·무주택·소득·자산·자동차 기준이 거절된 채 끝남)."""
    nested = [ref for ref in dict.fromkeys(e if isinstance(e, str) else str(e.get("id") or "") for e in evidence_entries(item)) if ref]
    cited = f"(하위 칸에 붙인 근거: {', '.join(nested[:5])})" if nested else ""
    return f"/evidence: 항목 자체의 evidence 칸이 비었습니다. 조건식·예외 같은 하위 칸의 evidence와 따로, 항목 전체의 근거 id를 1개 이상 넣습니다{cited}."


def _apply(base: dict[str, Any], changes: Any) -> tuple[dict[str, Any], str | None]:
    """고칠 칸(changes)을 항목에 씁니다. 칸 이름 열쇠는 _merge로 합치고, 「exceptions/2/originalText」처럼 항목 안 위치를 적은 열쇠는 그 위치만 바꿉니다.
    따라갈 수 없는 위치가 있으면 아무것도 바꾸지 않고 그 위치를 돌려줍니다.
    2026-11-08 최종 비교 bmc-106: 거절된 소득·자산·자동차 조건을 고치며 검증 결과가 알린 위치(/exceptions/2/originalText)를 열쇠로 적었는데,
    칸 이름으로만 읽어 엉뚱한 칸이 생기고 그대로 거절됨(저장된 실행들에서 이렇게 고친 9번이 모두 실패)."""
    changes = changes if isinstance(changes, dict) else {}
    merged = copy.deepcopy(_merge(base, {key: value for key, value in changes.items() if "/" not in key}))
    for key, value in changes.items():
        if "/" in key:
            lost = _set(merged, [token for token in key.split("/") if token], value)
            if lost:
                return base, lost
    return merged, None


def _set(item: dict[str, Any], tokens: list[str], value: Any) -> str | None:
    """항목 안 위치(토큰들)의 값을 바꿉니다. 객체 칸은 _merge처럼 합치고, 목록 순번은 그 원소를 합치며 목록 길이와 같은 순번이나 「-」는
    끝에 더합니다. 따라갈 수 없으면 그 위치를 돌려줍니다."""
    node: Any = item
    for depth, token in enumerate(tokens[:-1]):
        node = node.get(token) if isinstance(node, dict) else node[int(token)] if _index(node, token) else None
        if not isinstance(node, dict | list):
            return "/" + "/".join(tokens[: depth + 1])
    last = tokens[-1] if tokens else ""
    if isinstance(node, dict) and last:
        node.update(_merge(node, {last: value}))
        return None
    if isinstance(node, list) and (last == "-" or (last.isdigit() and int(last) == len(node))):
        node.append(copy.deepcopy(value))
        return None
    if isinstance(node, list) and _index(node, last):
        node[int(last)] = _merge(node[int(last)], value)
        return None
    return "/" + "/".join(tokens)


def _index(node: Any, token: str) -> bool:
    return isinstance(node, list) and token.isdigit() and int(token) < len(node)


def _bad_path(where: str) -> str:
    return _error(
        "BAD_PATH", f"고칠 위치 {where}가 항목에 없습니다. 아무것도 바꾸지 않았습니다. 칸 이름이나 항목 안 위치(예: exceptions/0/originalText)를 적습니다."
    )


def _merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            merged[key] = value if key == "evidence" else _merge(base.get(key), value)
        # 상태를 바꾸며 맞지 않게 된 칸을 적지 않으면 앞 값이 남아 형식 오류로 거절됨: 계약대로 비웁니다
        # (2026-11-07 3건 표본: 조건을 「글로 남김」으로 바꾸며 조건식을 지우지 않아 거절 5번, 고치는 차례가 늘어남)
        stale = RULE_STATUS_CLEARS.get(patch["status"]) if isinstance(patch.get("status"), str) else None
        if stale and stale in merged and stale not in patch:
            merged[stale] = None
        return merged
    return copy.deepcopy(patch)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(code: str, message: str) -> str:
    return _dump({"error": code, "message": message})
