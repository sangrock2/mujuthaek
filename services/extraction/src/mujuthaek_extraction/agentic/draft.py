"""작업 초안: 에이전트가 채우고 고치는 공고 추출 결과(AI 출력 형식 조각들).

조각은 하위 에이전트(호출 이름)마다 하나 이상입니다(구조 추출은 공고·위치 조각과 코드가 표에서 옮긴 공급 조각 둘을 냄).
extract_section은 그 담당의 조각들을 통째로 바꾸고, upsert·remove는 항목 하나를 고칩니다.
결합·검증(pipeline.evaluate_parts)은 as_parts()로 지금 흐름과 같은 조각 목록을 받아 돌립니다. 구조 조각(notice가 있는 조각)이 맨 앞입니다.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Any

from mujuthaek_extraction.repair.tools import _id_list, item_refs

LIST_SECTIONS = ("locations", "supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "guidance")
COVERAGE = ("EXTRACTED", "PARTIAL", "NOT_IN_SOURCE", "NOT_APPLICABLE")


@dataclass
class Draft:
    owners: dict[str, str]  # 섹션 → 맡은 하위 에이전트(호출 이름)
    document_id: str
    parts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _refs: int = 0
    # 동시 담당(delegate_many)이 함께 읽고 씁니다. 한 담당이 초안 전체를 사본으로 읽는 동안 다른 담당이 새 조각을 넣으면
    # 「dictionary changed size」로 처리 전체가 멈출 수 있어(2026-11-05 점검) 읽기·쓰기를 모두 잠금 안에서 합니다
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False, compare=False)

    def put_parts(self, owner: str, parts: list[dict[str, Any]]) -> None:
        """extract_section 결과로 그 하위 에이전트의 조각들을 통째로 바꿉니다."""
        with self._lock:
            self.parts[owner] = copy.deepcopy(parts)

    def filled(self) -> set[str]:
        """조각이 있는 담당들."""
        with self._lock:
            return {owner for owner, owned in self.parts.items() if owned}

    def _holder(self, section: str) -> dict[str, Any] | None:
        """그 섹션을 담은 조각(없으면 None)."""
        return next((p for p in self.parts.get(self.owners.get(section, ""), []) if section in p), None)

    def _part(self, section: str) -> dict[str, Any]:
        part = self._holder(section)
        if part is not None:
            return part
        owned = self.parts.setdefault(self.owners[section], [])
        if not owned:
            owned.append({"quotes": [], "coverage": {}, "missingFields": []})
        part = owned[0]
        if section not in part:
            part[section] = None if section == "notice" else []
            part.setdefault("coverage", {})[section] = {"status": "EXTRACTED", "reason": None}
        return part

    def quote_refs(self, section: str) -> set[str]:
        """그 섹션 조각에 있는 인용 ref들."""
        with self._lock:
            part = self._holder(section) or {}
            return {q["ref"] for q in part.get("quotes") or [] if isinstance(q, dict) and "ref" in q}

    def upsert(self, section: str, item: dict[str, Any], quotes: list[dict[str, str]], replace_refs: bool = False) -> str:
        """항목 하나를 넣거나(같은 id가 없으면) 고칩니다(칸마다 덮어씀, id 있는 목록은 id별로 합침). 인용 ref는 겹치지 않게 바꿉니다.
        quoteRefs는 기본으로 있던 것에 더합니다(replace_refs면 바꿈). 2026-11-05 대역 시험: 설명 칸 근거만 더하려고 quoteRefs에 새 ref
        하나를 적었더니 목록을 통째로 바꿔 서류 이름의 근거가 사라졌음. 틀린 근거를 고칠 때만 바꿉니다."""
        with self._lock:
            return self._upsert(section, item, quotes, replace_refs)

    def preview(self, section: str, item: dict[str, Any], replace_refs: bool = False) -> dict[str, Any]:
        """upsert하면 될 항목(같은 id의 지금 항목에 합친 것)을 미리 봅니다(초안은 바꾸지 않음)."""
        with self._lock:
            current = self.item(section, None if section == "notice" else item.get("id"))
        return merge_item(current, item, replace_refs) if isinstance(current, dict) else item

    def _upsert(self, section: str, item: dict[str, Any], quotes: list[dict[str, str]], replace_refs: bool) -> str:
        part = self._part(section)
        renamed = {}
        for quote in quotes:
            self._refs += 1
            renamed[quote["ref"]] = f"a{self._refs}"
            part["quotes"].append({"ref": renamed[quote["ref"]], "documentId": self.document_id, "text": quote["text"]})
        item = _rename_refs(item, renamed)
        if section == "notice":
            part["notice"] = merge_item(part.get("notice"), item, replace_refs) if isinstance(part.get("notice"), dict) else item
            return "notice"
        items = part[section]
        found = next((i for i, x in enumerate(items) if isinstance(x, dict) and x.get("id") == item.get("id")), None)
        if found is None:
            items.append(item)
            return f"{section}/{item.get('id')} 추가"
        items[found] = merge_item(items[found], item, replace_refs)
        return f"{section}/{item.get('id')} 고침"

    def remove(self, section: str, item_id: str) -> bool:
        with self._lock:
            return self._remove(section, item_id)

    def _remove(self, section: str, item_id: str) -> bool:
        part = self._holder(section)
        items = part.get(section) if part else None
        if not isinstance(items, list):
            return False
        kept = [x for x in items if not (isinstance(x, dict) and x.get("id") == item_id)]
        part[section] = kept
        return len(kept) < len(items)

    def set_coverage(self, section: str, status: str, reason: str | None) -> None:
        with self._lock:
            self._set_coverage(section, status, reason)

    def _set_coverage(self, section: str, status: str, reason: str | None) -> None:
        part = self._part(section)
        part["coverage"][section] = {"status": status, "reason": reason or None}
        if status in ("NOT_IN_SOURCE", "NOT_APPLICABLE") and section != "notice":
            part[section] = []

    def item(self, section: str, item_id: str | None) -> dict[str, Any] | None:
        """그 항목의 사본(없으면 None)."""
        with self._lock:
            part = self._holder(section)
            if not part:
                return None
            if section == "notice":
                return copy.deepcopy(part.get("notice"))
            return copy.deepcopy(next((x for x in part.get(section) or [] if isinstance(x, dict) and x.get("id") == item_id), None))

    def quotes_of(self, section: str, item: dict[str, Any]) -> list[dict[str, str]]:
        with self._lock:
            part = self._holder(section) or {}
            texts = {q["ref"]: q["text"] for q in part.get("quotes") or [] if isinstance(q, dict)}
        return [{"ref": ref, "text": texts[ref]} for ref in item_refs(item) if ref in texts]

    def as_parts(self) -> list[dict[str, Any]]:
        """결합기에 줄 조각 목록(notice가 있는 조각을 맨 앞에)."""
        with self._lock:
            parts = [copy.deepcopy(p) for owned in self.parts.values() for p in owned]
        return sorted(parts, key=lambda p: 0 if p.get("notice") is not None else 1)

    def summary(self, sections: tuple[str, ...] | None = None) -> dict[str, Any]:
        """섹션마다 항목 수·id(앞 30개)·범위 상태. 에이전트가 초안을 다시 읽지 않고 상태를 보게 합니다."""
        with self._lock:
            return self._summary(sections)

    def _summary(self, sections: tuple[str, ...] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for section in self.owners:
            if sections and section not in sections:
                continue
            part = self._holder(section)
            if not part:
                out[section] = "비어 있음"
                continue
            value = part[section]
            coverage = (part.get("coverage") or {}).get(section)
            if section == "notice":
                out[section] = {"filled": isinstance(value, dict), "coverage": coverage}
            else:
                ids = [x.get("id") for x in value or [] if isinstance(x, dict)]
                out[section] = {"count": len(ids), "ids": ids[:30], "coverage": coverage}
        return out

    def counts(self) -> dict[str, Any]:
        """섹션마다 항목 수만(id 목록 없이). 결과 크기를 작게 두려고 씁니다."""
        with self._lock:
            summary = self._summary(None)
        return {k: (v["count"] if isinstance(v, dict) and "count" in v else v) for k, v in summary.items()}

    def structure_ids(self) -> set[str]:
        """초안의 위치·공급 묶음 ID."""
        with self._lock:
            return {
                x["id"]
                for owned in self.parts.values()
                for part in owned
                for section in ("locations", "supplyGroups")
                for x in part.get(section) or []
                if isinstance(x, dict) and isinstance(x.get("id"), str)
            }

    def referencing(self, ids: set[str], skip_owner: str) -> list[str]:
        """다른 담당의 항목 중 ids를 가리키는 것(「섹션/id」). 구조를 다시 뽑아 ID가 사라졌을 때 알리려고 씁니다."""
        found: list[str] = []
        with self._lock:
            for owner, owned in self.parts.items():
                if owner == skip_owner:
                    continue
                for part in owned:
                    for section in self.owners:
                        items = part.get(section)
                        for item in items if isinstance(items, list) else []:
                            if isinstance(item, dict) and _referenced(item) & ids:
                                found.append(f"{section}/{item.get('id')}")
        return found


def merge_item(base: Any, patch: Any, replace_refs: bool = False) -> Any:
    """고칠 칸만 적은 조각을 지금 항목에 합칩니다(repair.tools._merge와 같은 규칙: 객체는 칸마다, id 있는 목록은 id별로, 그 밖은 바꿈).
    다른 점: quoteRefs는 있던 것에 더합니다(replace_refs면 바꿈)."""
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for key, value in patch.items():
            if key == "quoteRefs" and not replace_refs and isinstance(value, list) and isinstance(base.get(key), list):
                out[key] = list(dict.fromkeys([*base[key], *value]))
            else:
                out[key] = merge_item(base.get(key), value, replace_refs)
        return out
    if _id_list(base) and _id_list(patch):
        patches = {item["id"]: item for item in patch}
        merged = [merge_item(item, patches[item["id"]], replace_refs) if item["id"] in patches else item for item in base]
        known = {item["id"] for item in base}
        return [*merged, *(item for item in patch if item["id"] not in known)]
    return patch


REF_KEYS = ("locationId", "locationIds", "supplyGroupIds", "parentLocationId")


def _referenced(node: Any) -> set[str]:
    """항목 안에서 위치·공급 묶음 ID를 가리키는 값들(범위 scope 포함)."""
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in REF_KEYS:
                out |= {v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str)}
            else:
                out |= _referenced(value)
    elif isinstance(node, list):
        for value in node:
            out |= _referenced(value)
    return out


def _rename_refs(node: Any, renamed: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: ([renamed.get(r, r) for r in v] if k == "quoteRefs" and isinstance(v, list) else _rename_refs(v, renamed)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rename_refs(x, renamed) for x in node]
    return node


def split_by_owner(part: dict[str, Any], owners: dict[str, str]) -> dict[str, dict[str, Any]]:
    """여러 담당의 섹션을 함께 담은 조각(작은 공고의 자격·선정·서류 한 호출)을 담당별 조각으로 나눕니다.
    인용 목록은 모두 함께 둡니다(결합기는 조각 안에서만 ref를 찾음). 누락 기록·범위 상태는 그 섹션 담당에게."""
    by_owner: dict[str, list[str]] = {}
    for section in owners:
        if section in part:
            by_owner.setdefault(owners[section], []).append(section)
    if len(by_owner) <= 1:
        return {owner: part for owner in by_owner}
    out = {}
    for owner, sections in by_owner.items():
        piece = {k: v for k, v in part.items() if k not in owners or k in sections}
        piece["coverage"] = {k: v for k, v in (part.get("coverage") or {}).items() if k in sections}
        piece["missingFields"] = [m for m in part.get("missingFields") or [] if str(m.get("target", "")).lstrip("/").split("/", 1)[0] in sections]
        out[owner] = copy.deepcopy(piece)
    return out
