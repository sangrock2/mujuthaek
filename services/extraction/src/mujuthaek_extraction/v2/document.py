"""V2 문서 모델: 공고 원문을 에이전트가 id로 가리키는 조각(줄·표·행·칸)으로 나눕니다.

원문은 V1 입력 해석이 만든 글자(material.text)입니다. 쪽 표시(「--- 3쪽 ---」), 표 표시(「[표 4-1]」), 열 제목 줄, 표 행(「| a | b |」),
첨부 엑셀·그림 판독 묶음(「=== … ===」)을 읽어 id를 붙입니다. 에이전트는 원문 전체를 받지 않고 도구로 필요한 조각만 보고,
값의 근거를 id로 남깁니다. 인용 글은 코드가 id로 원문에서 꺼내므로 원문과 글자가 늘 같습니다(검증기의 원문 대조가 그대로 통과).

id 모양
  줄  p3.12        3쪽 본문 12번째 줄(1부터). 둘째 첨부 PDF부터는 d2.p3.12, 엑셀·그림 판독 묶음은 x1.4 · g1.4
  표  t4-1         V1 표 번호 그대로(둘째 PDF부터 d2.t4-1). 번호 없는 표(엑셀 시트·판독 표)는 <묶음>.t1
  행  t4-1.r3      표의 행(0부터)
  칸  t4-1.r3.c2   그 행의 칸(0부터)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from mujuthaek_extraction.image_reading import image_targets
from mujuthaek_extraction.intake.model import ExtractionMaterial

PAGE = re.compile(r"^--- (\d+)쪽(?: 왼쪽| 오른쪽)? ---$")
TABLE = re.compile(r"^\[표 ([^\]]+)\]$")
SHEET = re.compile(r"^\[엑셀 시트 (.+)\]$")
BLOCK = re.compile(r"^=== (.+) ===$")
TITLES = "  [열 제목] "  # V1 구조 방식이 표 위에 붙이는 열 제목 줄
AID = "  ↳ "  # V1이 표 행 아래 붙이는 읽기 도움 줄(원문이 아님)
TITLE_ITEM = re.compile(r"^\d+\. ?(.*)$")
HEADING = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|[가-하]\s*[.)]|[■□◆◇●○▶▷※◎◈]|[\[<【(]|제\s*\d+\s*[조장절])")
HEADING_CHARS = 60  # 이보다 긴 줄은 제목으로 보지 않습니다
FUZZY_MIN = 80  # 찾기에서 글자가 똑같은 곳이 없을 때 비슷한 줄로 볼 최소 유사도(0~100)


@dataclass(frozen=True)
class Line:
    id: str
    text: str


@dataclass(frozen=True)
class Table:
    id: str
    area: str  # 표가 있는 쪽·묶음(p4 · d2.p3 · x1 · g1)
    lines: tuple[str, ...]  # 원문의 표 행 줄 그대로(「| a | b |」)
    columns: tuple[str, ...] = ()  # V1이 복원한 열 제목(없으면 빈 값)
    caption: str = ""  # 엑셀 시트 이름 등

    @property
    def rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(_cells(line) for line in self.lines)


@dataclass(frozen=True)
class DocumentModel:
    items: tuple[Line | Table, ...]  # 원문 순서(본문 줄과 표가 섞임)
    picture_pages: tuple[str, ...] = ()  # 글자 없는 그림 쪽(p8 · d2.p1)
    source_id: str = "text"  # 원문 글자의 문서 ID(V1 material.text_document_id). 인용의 documentId
    _by_id: dict[str, Line | Table] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {item.id: item for item in self.items})

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(item for item in self.items if isinstance(item, Line))

    @property
    def tables(self) -> tuple[Table, ...]:
        return tuple(item for item in self.items if isinstance(item, Table))

    def text(self, ref: str) -> str:
        """id → 원문 글자(줄·표 전체·행·칸). 없는 id면 KeyError."""
        item = self._by_id.get(ref)
        if isinstance(item, Line):
            return item.text
        if isinstance(item, Table):
            return "\n".join(item.lines)
        table_id, row, column = _split_cell_ref(ref)
        table = self._by_id.get(table_id)
        if not isinstance(table, Table) or row >= len(table.lines):
            raise KeyError(ref)
        if column is None:
            return table.lines[row]
        cells = table.rows[row]
        if column >= len(cells):
            raise KeyError(ref)
        return cells[column]

    def exists(self, ref: str) -> bool:
        try:
            self.text(ref)
        except KeyError:
            return False
        return True

    def outline(self, heading_limit: int = 80) -> dict[str, Any]:
        """차례: 제목 줄, 표(열 제목·행 수·첫 행), 그림 쪽. 계획 에이전트가 처음 보는 글입니다."""
        headings = [{"id": line.id, "text": line.text.strip()} for line in self.lines if _is_heading(line.text)]
        tables = []
        for table in self.tables:
            summary: dict[str, Any] = {"id": table.id, "area": table.area, "rows": len(table.lines)}
            if table.columns:
                summary["columns"] = [c[:30] for c in table.columns[:12]]
            elif table.lines:
                summary["firstRow"] = [c[:30] for c in table.rows[0][:12]]
            if table.caption:
                summary["caption"] = table.caption
            tables.append(summary)
        return {
            "lines": len(self.lines),
            "chars": sum(len(line.text) for line in self.lines),
            "headings": headings[:heading_limit],
            "headingsOmitted": max(0, len(headings) - heading_limit),
            "tables": tables,
            "picturePages": list(self.picture_pages),
        }

    def view_lines(self, start: str, count: int) -> list[dict[str, Any]]:
        """start 줄부터 count개(사이의 표는 id·크기만)."""
        index = next((i for i, item in enumerate(self.items) if item.id == start), None)
        if index is None:
            raise KeyError(start)
        shown: list[dict[str, Any]] = []
        for item in self.items[index:]:
            if len(shown) >= count:
                break
            if isinstance(item, Line):
                shown.append({"id": item.id, "text": item.text})
            else:
                shown.append({"table": item.id, "rows": len(item.lines), "columns": [c[:30] for c in item.columns[:12]]})
        return shown

    def view_table(self, table_id: str, start: int = 0, count: int = 20) -> dict[str, Any]:
        table = self._by_id.get(table_id)
        if not isinstance(table, Table):
            raise KeyError(table_id)
        rows = [{"id": f"{table.id}.r{r}", "cells": list(table.rows[r])} for r in range(max(0, start), min(len(table.lines), max(0, start) + count))]
        return {
            "id": table.id,
            "area": table.area,
            "columns": list(table.columns),
            "rows": rows,
            "total": len(table.lines),
            "more": start + count < len(table.lines),
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """글자가 똑같이 든 줄·표 행(칸 하나에 들면 칸 id도), 없으면 비슷한 줄(유사도 FUZZY_MIN 이상)."""
        needle = _squash(query)
        if not needle:
            return []
        hits: list[dict[str, Any]] = []
        for ref, text, cells in self._searchable():
            if needle in _squash(text):
                hit: dict[str, Any] = {"id": ref, "text": text}
                cell = next((c for c, value in enumerate(cells) if needle in _squash(value)), None)
                if cell is not None:
                    hit["cell"] = f"{ref}.c{cell}"
                hits.append(hit)
                if len(hits) >= limit:
                    return hits
        if hits:
            return hits
        scored = [(fuzz.partial_ratio(needle, _squash(text)), ref, text) for ref, text, _ in self._searchable()]
        return [{"id": ref, "text": text, "similarity": round(score)} for score, ref, text in sorted(scored, reverse=True)[:limit] if score >= FUZZY_MIN]

    def _searchable(self):
        for item in self.items:
            if isinstance(item, Line):
                yield item.id, item.text, ()
            else:
                for r, line in enumerate(item.lines):
                    yield f"{item.id}.r{r}", line, item.rows[r]


def build(material: ExtractionMaterial) -> DocumentModel:
    """V1 입력 해석 결과 → 문서 모델. 그림 쪽은 첨부 PDF에서 찾습니다(V1 그림 판독과 같은 기준)."""
    document = parse(material.text, material.text_document_id)
    pdfs = [file.document_id for file in material.files if file.file_type == "pdf"]
    pages = []
    for document_id, _, _, page in image_targets(material):
        order = pdfs.index(document_id) + 1 if document_id in pdfs else 1
        pages.append(f"p{page}" if order == 1 else f"d{order}.p{page}")
    return DocumentModel(document.items, tuple(pages), document.source_id)


def parse(text: str, source_id: str = "text") -> DocumentModel:
    items: list[Line | Table] = []
    area, document, last_page = "p1", 1, 0
    counters: dict[str, int] = {}
    blocks: dict[str, int] = {}
    table: dict[str, Any] | None = None

    def close() -> None:
        nonlocal table
        if table is not None and table["lines"]:
            items.append(Table(table["id"], table["area"], tuple(table["lines"]), tuple(table["columns"]), table["caption"]))
        table = None

    def unnamed(caption: str = "") -> dict[str, Any]:
        counters[f"{area}.t"] = counters.get(f"{area}.t", 0) + 1
        return {"id": f"{area}.t{counters[f'{area}.t']}", "area": area, "lines": [], "columns": [], "caption": caption}

    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not line.strip():
            close()
            continue
        if page := PAGE.match(line):
            close()
            number = int(page.group(1))
            if number < last_page:  # 쪽 번호가 줄면 다음 첨부 PDF
                document += 1
            last_page = number
            area = f"p{number}" if document == 1 else f"d{document}.p{number}"
            continue
        if block := BLOCK.match(line):
            close()
            kind = "x" if "엑셀" in block.group(1) else "g" if "그림 판독" in block.group(1) else "b"
            blocks[kind] = blocks.get(kind, 0) + 1
            area = f"{kind}{blocks[kind]}"
            continue
        if marker := TABLE.match(line):
            close()
            prefix = "" if document == 1 else f"d{document}."
            table = {"id": f"{prefix}t{marker.group(1)}", "area": area, "lines": [], "columns": [], "caption": ""}
            continue
        if sheet := SHEET.match(line):
            close()
            table = unnamed(sheet.group(1))
            continue
        if line.startswith(TITLES):
            if table is not None:
                table["columns"] = [_title(item) for item in line[len(TITLES) :].split(" | ")]
            continue
        if line.startswith(AID):
            continue
        if _is_row(line):
            if table is None:
                table = unnamed()
            table["lines"].append(line)
            continue
        close()
        counters[area] = counters.get(area, 0) + 1
        items.append(Line(f"{area}.{counters[area]}", line))
    close()
    return DocumentModel(tuple(items), source_id=source_id)


def _is_row(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 2 and stripped.startswith("|") and stripped.endswith("|")


def _cells(line: str) -> tuple[str, ...]:
    inner = line.strip()[1:-1]
    return tuple(cell.strip() for cell in inner.split("|"))


def _title(item: str) -> str:
    match = TITLE_ITEM.match(item.strip())
    title = match.group(1) if match else item.strip()
    return "" if title == "-" else title


def _split_cell_ref(ref: str) -> tuple[str, int, int | None]:
    match = re.fullmatch(r"(.+)\.r(\d+)(?:\.c(\d+))?", ref)
    if not match:
        raise KeyError(ref)
    return match.group(1), int(match.group(2)), int(match.group(3)) if match.group(3) is not None else None


def _is_heading(text: str) -> bool:
    stripped = text.strip()
    return 0 < len(stripped) <= HEADING_CHARS and bool(HEADING.match(stripped))


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)
