"""기관 기억(V2 6단계) — 그림자 모드: 같은 기관의 같은 모양 공급표(열 제목이 같은 표)에 앞서 받은 열 해석을 기억해 두고,
새로 받은 해석과 같은지만 기록합니다. 기억한 해석을 쓰지는 않습니다(열 해석 호출은 그대로).

기억을 쓰면 열 해석 호출(V1 기준 평균 17초, 구조 호출 앞이라 담당 출발이 늦어짐)을 건너뛸 수 있지만, 잘못 기억하면 그 기관의 공고마다
같은 틀린 값이 되풀이됩니다. 2026-11-07 23건: 같은 기관 앞선 공고와 열 제목이 같은 표가 67개 중 1개뿐이라 평가 자료로는 정할 수 없어
운영에서 적중률(같은 모양을 다시 만난 표)과 일치율(그때 새 해석이 기억과 같았던 표)을 먼저 모읍니다. 일치율이 높을 때만 쓰는 단계로 넘어갑니다.

설정 EXTRACTION_FORMAT_MEMORY_DIR: 기관마다 JSON 파일 하나를 두는 폴더(없으면 꺼짐). 열 해석 지시 버전이 바뀌면 다른 열쇠가 됩니다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from mujuthaek_extraction import supply_tables

ENV = "EXTRACTION_FORMAT_MEMORY_DIR"
_LOCK = threading.Lock()


def signature(table: supply_tables.Table) -> str:
    """표 모양 열쇠: 열 해석 지시 버전 + 공백을 뺀 열 제목들."""
    columns = ["".join((title or "").split()) for title in table.columns]
    return hashlib.sha256(json.dumps([supply_tables.PROMPT_VERSION, columns], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def answer(entry: dict[str, Any]) -> dict[str, Any]:
    """비교할 해석: 표 번호·단지 이름(공고마다 다름)을 빼고, 열은 번호 순으로 값이 있는 칸만."""
    columns = [{k: v for k, v in column.items() if v is not None} for column in entry.get("columns") or [] if isinstance(column, dict)]
    return {
        "role": entry.get("role"),
        "rowUnit": entry.get("rowUnit"),
        "columns": sorted(columns, key=lambda c: (c.get("column") or 0, json.dumps(c, sort_keys=True))),
    }


def observe(source: str | None, mapping: tuple[list[supply_tables.Table], dict[str, Any]] | None) -> dict[str, Any] | None:
    """이번 공고의 열 해석을 기관 기억과 맞춰 보고(쓰지 않음) 기억을 이번 해석으로 갱신합니다. 꺼져 있거나 표가 없으면 None.
    돌려주는 것: 표 수, 기억에 있던 표 수(적중), 그중 해석이 같았던 표 수(일치), 달랐던 표 번호."""
    folder = os.getenv(ENV)
    if not folder or not source or mapping is None:
        return None
    tables, answered = mapping
    by_label = {str(entry.get("table")): entry for entry in answered.get("tables") or [] if isinstance(entry, dict)}
    path = Path(folder) / f"{re.sub(r'[^0-9A-Za-z_-]', '_', source)}.json"
    seen, same, changed, count = 0, 0, [], 0
    with _LOCK:
        memory = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for table in tables:
            entry = by_label.get(table.label)
            if table.continues or entry is None:
                continue
            count += 1
            key, now = signature(table), answer(entry)
            before = memory.get(key)
            if before is not None:
                seen += 1
                if before["answer"] == now:
                    same += 1
                else:
                    changed.append(table.label)
            memory[key] = {"answer": now, "columns": list(table.columns), "seen": (before or {}).get("seen", 0) + 1}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(memory, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return {"tables": count, "remembered": seen, "same": same, "changed": changed}
