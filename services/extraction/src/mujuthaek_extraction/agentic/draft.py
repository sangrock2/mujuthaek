"""작업 초안: 에이전트가 채우고 고치는 공고 추출 결과(AI 출력 형식 조각들).

조각은 하위 에이전트(호출 이름)마다 하나 이상입니다(구조 추출은 공고·위치 조각과 코드가 표에서 옮긴 공급 조각 둘을 냄).
extract_section은 그 담당의 조각들을 통째로 바꾸고, upsert·remove는 항목 하나를 고칩니다.
결합·검증(pipeline.evaluate_parts)은 as_parts()로 지금 흐름과 같은 조각 목록을 받아 돌립니다. 구조 조각(notice가 있는 조각)이 맨 앞입니다.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from mujuthaek_extraction.repair.tools import _merge, item_refs

LIST_SECTIONS = ("locations", "supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "guidance")
COVERAGE = ("EXTRACTED", "PARTIAL", "NOT_IN_SOURCE", "NOT_APPLICABLE")


@dataclass
class Draft:
    owners: dict[str, str]  # 섹션 → 맡은 하위 에이전트(호출 이름)
    document_id: str
    parts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _refs: int = 0

    def put_parts(self, owner: str, parts: list[dict[str, Any]]) -> None:
        """extract_section 결과로 그 하위 에이전트의 조각들을 통째로 바꿉니다."""
        self.parts[owner] = copy.deepcopy(parts)

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

    def upsert(self, section: str, item: dict[str, Any], quotes: list[dict[str, str]]) -> str:
        """항목 하나를 넣거나(같은 id가 없으면) 고칩니다(칸마다 덮어씀, id 있는 목록은 id별로 합침). 인용 ref는 겹치지 않게 바꿉니다."""
        part = self._part(section)
        renamed = {}
        for quote in quotes:
            self._refs += 1
            renamed[quote["ref"]] = f"a{self._refs}"
            part["quotes"].append({"ref": renamed[quote["ref"]], "documentId": self.document_id, "text": quote["text"]})
        item = _rename_refs(item, renamed)
        if section == "notice":
            part["notice"] = _merge(part.get("notice"), item) if isinstance(part.get("notice"), dict) else item
            return "notice"
        items = part[section]
        found = next((i for i, x in enumerate(items) if isinstance(x, dict) and x.get("id") == item.get("id")), None)
        if found is None:
            items.append(item)
            return f"{section}/{item.get('id')} 추가"
        items[found] = _merge(items[found], item)
        return f"{section}/{item.get('id')} 고침"

    def remove(self, section: str, item_id: str) -> bool:
        part = self._holder(section)
        items = part.get(section) if part else None
        if not isinstance(items, list):
            return False
        kept = [x for x in items if not (isinstance(x, dict) and x.get("id") == item_id)]
        part[section] = kept
        return len(kept) < len(items)

    def set_coverage(self, section: str, status: str, reason: str | None) -> None:
        part = self._part(section)
        part["coverage"][section] = {"status": status, "reason": reason or None}
        if status in ("NOT_IN_SOURCE", "NOT_APPLICABLE") and section != "notice":
            part[section] = []

    def item(self, section: str, item_id: str | None) -> dict[str, Any] | None:
        part = self._holder(section)
        if not part:
            return None
        if section == "notice":
            return part.get("notice")
        return next((x for x in part.get(section) or [] if isinstance(x, dict) and x.get("id") == item_id), None)

    def quotes_of(self, section: str, item: dict[str, Any]) -> list[dict[str, str]]:
        part = self._holder(section) or {}
        texts = {q["ref"]: q["text"] for q in part.get("quotes") or [] if isinstance(q, dict)}
        return [{"ref": ref, "text": texts[ref]} for ref in item_refs(item) if ref in texts]

    def as_parts(self) -> list[dict[str, Any]]:
        """결합기에 줄 조각 목록(notice가 있는 조각을 맨 앞에)."""
        parts = [copy.deepcopy(p) for owned in self.parts.values() for p in owned]
        return sorted(parts, key=lambda p: 0 if p.get("notice") is not None else 1)

    def summary(self, sections: tuple[str, ...] | None = None) -> dict[str, Any]:
        """섹션마다 항목 수·id(앞 30개)·범위 상태. 에이전트가 초안을 다시 읽지 않고 상태를 보게 합니다."""
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


def _rename_refs(node: Any, renamed: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: ([renamed.get(r, r) for r in v] if k == "quoteRefs" and isinstance(v, list) else _rename_refs(v, renamed)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rename_refs(x, renamed) for x in node]
    return node
