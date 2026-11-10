"""PDF 공고문 → 쪽·표 구조 JSON과 AI에 넘길 글자 (서비스 흐름 3단계: PDF → 텍스트(JSON)).

쪽마다 본문 글자와 표(행·칸)를 나눕니다. 표 영역의 글자는 본문에서 빼서, 칸이 섞인 채로 한 번 더 들어가지 않게 합니다.
본문과 표는 쪽 안에서 위에서 아래 순서를 지킵니다. AI용 글자 모양:

  --- 4쪽 ---
  2. 모집대상 주택
  [표 4-1]
  단지명 | 주택형 | 세대당 계약면적(㎡) | ...
  경암부향 | 39 | 39.95 | 10.59 | ...

글자가 거의 없으면(스캔본) None을 돌려 수집 글자(text)로 대신하게 합니다. 글자 인식(OCR)은 하지 않습니다.
"""

from __future__ import annotations

import hashlib
import io
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from mujuthaek_extraction.intake.xlsx_reader import is_secret_header, redact_secret_values

MIN_CHARS = 200  # collector와 같은 기준: 이보다 적으면 읽기 실패(스캔본 가능성)
FRAME_SHARE = 0.9  # 안에 표를 품은 바깥 표에서 칸 하나가 이만큼 글자를 담으면 테두리 상자로 봅니다
TABLE_COVERAGE = 0.95  # 칸으로 읽은 글자가 표 영역 글자의 이만큼은 돼야 표로 씁니다. 모자라면(칸이 비어 읽힘) 그 영역을 일반 글자로
LOOSE_MAX_SHARE = 0.2  # 표 영역 글자 중 어느 칸에도 안 든 글자(바깥 테두리선이 없는 끝 열)가 이 비율 이하면 표는 쓰고 그 글자는 표 옆 본문으로
COLUMN_MIN_SHARE = 0.2  # 쪽을 좌우로 나눌 때 양쪽 반에 글자가 각각 이만큼은 있어야 합니다
MAX_PAGES = 300  # 이보다 긴 PDF는 앞쪽만 읽습니다(시간·메모리 한도, 검토 2026-10-16). 공고문은 보통 10~60쪽
SHRED_COLUMNS = 30  # 이보다 열이 많고 칸 대부분이 한두 글자인 표는 배치 격자로 봅니다(_shredded)
EMPTY_PAGE_CHARS = 30  # 쪽 번호·워터마크만 있는 쪽(그림으로 된 쪽)으로 보는 글자 수


@dataclass
class PdfPage:
    number: int
    blocks: list[dict[str, Any]] = field(default_factory=list)  # {"type": "text", "text": ...} 또는 {"type": "table", "id": "4-1", "rows": [[칸...]]}
    column: int | None = None  # 모아찍기·2단 쪽을 나눠 읽었을 때 0=왼쪽, 1=오른쪽


@dataclass
class PdfDocument:
    """PDF 한 건을 쪽별 본문·표 블록으로 읽은 결과입니다. 저장용 JSON과 AI에 넘길 글자로 바꿀 수 있습니다."""

    page_count: int
    pages: list[PdfPage]

    def to_json(self) -> dict[str, Any]:
        def plain(block: dict[str, Any]) -> dict[str, Any]:
            # 병합 칸을 채운 행(filled)은 rows와 겹쳐 저장하지 않습니다. 칸 번호(cells)는 남겨 표 행 변환(supply_tables)이 병합을 복원합니다
            return {k: v for k, v in block.items() if k != "filled"}

        return {"pageCount": self.page_count, "pages": [{"page": p.number, "column": p.column, "blocks": [plain(b) for b in p.blocks]} for p in self.pages]}

    def empty_pages(self) -> list[int]:
        """글자가 거의 없는 쪽 번호(스캔·그림 쪽). 문서 전체 글자 수만 보면 쪽마다 쪽 번호만 있는 스캔본을 읽은 것으로 잘못 봅니다."""
        letters: dict[int, int] = {}
        for page in self.pages:
            text = " ".join(b["text"] if b["type"] == "text" else " ".join(" ".join(r) for r in b["rows"]) for b in page.blocks)
            letters[page.number] = letters.get(page.number, 0) + len(re.sub(r"\s|\d", "", text))
        return [number for number, count in sorted(letters.items()) if count < EMPTY_PAGE_CHARS]

    def render(self, labeled: bool = False) -> str:
        """AI에 넘길 글자. labeled=True(구조 방식, 2026-10-17)면 표마다 열 제목 줄을, 숫자가 든 데이터 행마다 바로 아래에
        값마다 열 제목을 붙인 읽기 도움 줄(「  ↳ 26 대학생 — 건설 호수 25 · 금회 모집 예비 자수 11」)을 덧붙입니다.
        표 행(| 줄)은 그대로라 인용·검증은 바뀌지 않습니다. labeled=False는 이전 방식(EXTRACTION_METHOD=legacy)."""
        lines: list[str] = []
        for page in self.pages:
            side = "" if page.column is None else (" 왼쪽" if page.column == 0 else " 오른쪽")
            lines.append(f"--- {page.number}쪽{side} ---")
            for block in page.blocks:
                if block["type"] == "text":
                    lines.append(block["text"])
                    continue
                lines.append(f"[표 {block['id']}]")
                rows = block["rows"]
                if labeled and 2 <= len(rows) <= VERTICAL_MAX_ROWS and all(len(row) == 1 for row in rows):
                    # 칸 하나짜리 세로 표(일정 상자 「모집 공고 / ‘26. 4. 10. / 공사 홈페이지」)는 한 줄로 보여 줍니다. 줄마다 따로 두면 AI가
                    # 칸을 이어 붙여 인용하거나 「| 개별 안내 |」처럼 여러 곳에 있는 짧은 칸만 인용해 근거를 못 정했습니다(실측 2026-10-17 dcco-24788)
                    lines.append("| " + " | ".join(row[0] for row in rows) + " |")
                    continue
                titles = (block.get("columns") or []) if labeled else []
                if titles:
                    lines.append("  [열 제목] " + " | ".join(f"{i + 1}. {t or '-'}" for i, t in enumerate(titles)))
                short = _short_titles(titles)
                for index, row in enumerate(block["rows"]):
                    lines.append("| " + " | ".join(row) + " |")
                    cells = block.get("cells")
                    above = cells[index - 1] if cells and index > 0 else None
                    aid = _row_aid((block.get("filled") or block["rows"])[index], short, cells[index] if cells else None, above) if titles else None
                    if aid:
                        lines.append(aid)
        return "\n".join(lines)


VERTICAL_MAX_ROWS = 6  # 이보다 긴 한 칸짜리 표는 목록이라 줄마다 둡니다
ROW_AID = "  ↳ "  # 읽기 도움 줄 머리. 인용하지 않도록 프롬프트에서 알려 줍니다
UNIT_MARK = re.compile(r"\((?:천원|만원|원|㎡|m2|%|명|호|세대|년|개월)\)|천원|만원")  # 열 제목 속 단위 표시
EMPTY_MARKS = {"-", "−", "–", "—", "×", "X", "x"}  # 값 없음 표시: 행 이름이 아니라 그 열의 값(「현재 공가 수 -」)


def _row_aid(filled: list[str], titles: list[str], cells: list[int] | None = None, above: list[int] | None = None) -> str | None:
    """숫자 칸이 있는 데이터 행 → 「↳ <행 이름> — <열 제목> <값> · …」. 행 이름은 숫자가 아닌 칸(병합으로 위에서 이어받은 칸 포함)."""
    if not any(cell and NUMERIC_VALUE.fullmatch(cell) for cell in filled) or all(cell == titles[i] for i, cell in enumerate(filled) if i < len(titles)):
        return None
    names, values = [], []
    for column, cell in enumerate(filled):
        if not cell:
            continue
        title = titles[column] if column < len(titles) else ""
        same = cells is not None and column > 0 and column < len(cells) and cells[column] >= 0 and cells[column] == cells[column - 1]
        # 위 행에서 세로로 이어진 값(같은 칸 번호)은 다시 쓰지 않습니다: 전환안 둘째 행이 첫 행의 기본 가격을 되풀이해 두 번 넣던 것(시험)
        mine = cells[column] if cells is not None and column < len(cells) else -1
        inherited = above is not None and column < len(above) and mine >= 0 and mine == above[column]
        if (NUMERIC_VALUE.fullmatch(cell) or cell in EMPTY_MARKS) and title:
            if inherited:
                continue
            if same and values:  # 가로로 병합된 한 칸(「합계 13」이 두 열을 덮음): 값은 한 번, 열 제목을 이어 붙입니다
                values[-1] = values[-1].rsplit(" ", 1)[0] + f" + {title} {cell}"
            else:
                values.append(f"{title} {cell}")
        elif cell not in names:
            names.append(cell)
    if not values:
        return None
    return ROW_AID + " ".join(names) + " — " + " · ".join(values)


def _short_titles(titles: list[str]) -> list[str]:
    """읽기 도움 줄에는 열 제목의 끝부분만: 다른 열과 겹치지 않는 가장 짧은 끝(「계약금」, 겹치면 「임대보증금(천원) › 계」)."""
    parts = [t.split(" › ") if t else [] for t in titles]
    short = []
    for mine in parts:
        for size in range(1, len(mine) + 1):
            tail = mine[-size:]
            if sum(1 for other in parts if other[-size:] == tail) == 1 or size == len(mine):
                # 줄인 끝에 단위가 없으면 단위가 적힌 가장 가까운 윗머리를 붙입니다(「계 (100%)」 → 「임대보증금(천원) › 계 (100%)」).
                # 실측(시험): 단위가 빠진 제목은 금액 단위를 잘못 읽게 할 수 있음
                if not any(UNIT_MARK.search(part) for part in tail):
                    upper = next((part for part in reversed(mine[: len(mine) - size]) if UNIT_MARK.search(part)), None)
                    tail = [upper, *tail] if upper else tail
                short.append(" › ".join(tail))
                break
        else:
            short.append("")
    return short


def _carry_titles(pages: list[PdfPage]) -> None:
    """쪽을 넘어 이어지는 표(다음 쪽 맨 처음 덩어리, 열 수 같음, 머리글 없음)는 앞 표의 열 제목을 이어받습니다."""
    previous: tuple[int, list[str]] | None = None  # 앞 쪽의 맨 끝 덩어리가 열 제목 있는 표면 (쪽, 열 제목)
    for page in pages:
        first = page.blocks[0] if page.blocks else None
        if first and first["type"] == "table" and not first.get("columns") and previous and previous[0] in (page.number, page.number - 1):
            if len(previous[1]) == max((len(r) for r in first["rows"]), default=0):
                first["columns"] = list(previous[1])
        last = page.blocks[-1] if page.blocks else None
        previous = (page.number, last["columns"]) if last and last["type"] == "table" and last.get("columns") else None


# 글자 사이 띄움을 NUL 등 제어 문자로 넣은 PDF(실측: 전북개발공사 「자 동 차」 사이가 NUL). 그대로 두면 AI가 공백으로 옮긴 인용을
# 원문에서 못 찾아 항목이 빠집니다(2026-10-17 jbdc-15560). 줄바꿈·탭 말고는 공백으로 바꿉니다
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(text: str) -> str:
    return CONTROL_CHARS.sub(" ", text)


def _cell(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(str(value))).strip() if value is not None else ""


def _inside(obj: dict[str, Any], boxes: list[tuple[float, float, float, float]]) -> bool:
    x = (obj["x0"] + obj["x1"]) / 2
    y = (obj["top"] + obj["bottom"]) / 2
    return any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in boxes)


def _letters(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def _contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return outer != inner and outer[0] <= inner[0] + 1 and outer[1] <= inner[1] + 1 and outer[2] >= inner[2] - 1 and outer[3] >= inner[3] - 1


# 값 칸: 「9,330」「(+)5,000」「-1,100」「7/8」(공가/전체 호수)「39㎡」「20%」
NUMERIC_VALUE = re.compile(r"(?:\(\s*[+\-−]\s*\)\s*|[+\-−])?\(?\d[\d,.\s]*\)?(?:\s*/\s*\d[\d,.]*)?\s*(?:원|천원|만원|%|㎡|세대|호|명|개월|년|점)?")
MAX_HEADER_ROWS = 4


def _spans(table: Any, raw: list[list[Any]]) -> tuple[list[list[str]], list[list[int]]]:
    """병합 칸을 채운 칸 글자: 빈 자리(None)를 그 자리를 덮는 실제 칸의 글자로. pdfplumber는 병합 칸의 첫 자리에만 글자를 주고
    나머지 자리는 None으로 둡니다(가로·세로 모두). 칸 좌표로 덮는 칸을 찾으므로 가로 병합과 세로 병합을 가리지 않습니다.
    둘째 값은 자리마다 덮는 칸의 번호(-1은 없음): 가로로 병합된 한 칸을 읽기 도움 줄에 한 번만 쓰려고 씁니다."""
    origin: dict[tuple[float, ...], str] = {}
    number: dict[tuple[float, ...], int] = {}
    for r, row in enumerate(table.rows):
        for c, box in enumerate(row.cells):
            if box is not None and r < len(raw) and c < len(raw[r]):
                origin[tuple(box)] = _cell(raw[r][c])
                number.setdefault(tuple(box), len(number))
    # 행·열 상자는 병합 칸만큼 늘어나 있어(실측: 세로 병합 「21」이 있는 행의 상자가 아래 두 행까지 덮음) 중심점이 다른 칸을 가리킵니다.
    # 열은 그 열에서 가장 좁은 실제 칸, 행은 그 행에서 가장 낮은 실제 칸으로 격자 자리를 정합니다
    width = len(table.columns)
    xs: list[tuple[float, float] | None] = [None] * width
    for row in table.rows:
        for c, box in enumerate(row.cells[:width]):
            if box is not None and (xs[c] is None or box[2] - box[0] < xs[c][1] - xs[c][0]):
                xs[c] = (box[0], box[2])
    filled, ids = [], []
    for row in table.rows:
        real = [box for box in row.cells if box is not None]
        shortest = min(real, key=lambda b: b[3] - b[1]) if real else row.bbox
        y = (shortest[1] + shortest[3]) / 2
        line, line_ids = [], []
        for c in range(width):
            box = row.cells[c] if c < len(row.cells) else None
            if box is not None:
                line.append(origin.get(tuple(box), ""))
                line_ids.append(number.get(tuple(box), -1))
                continue
            span = xs[c] or (table.columns[c].bbox[0], table.columns[c].bbox[2])
            x = (span[0] + span[1]) / 2
            cover = next((cell for cell in origin if cell[0] <= x <= cell[2] and cell[1] <= y <= cell[3]), None)
            line.append(origin[cover] if cover else "")
            line_ids.append(number[cover] if cover else -1)
        filled.append(line)
        ids.append(line_ids)
    return filled, ids


def _column_titles(filled: list[list[str]]) -> list[str]:
    """표 위쪽 머리글 행들(숫자만 든 칸이 없는 행, 최대 4행)에서 열마다 제목을 이어 붙입니다(「임대조건 › 임대보증금(천원) › 계」).
    머리글 행이 없거나(이어진 표의 다음 쪽) 데이터 행이 없으면 빈 목록."""
    # 머리글 = 첫 숫자 행 위의 행들(1~4행). 숫자 행이 없는 표(용어 설명표 등)는 머리글이 아니라 내용이라 제목을 붙이지 않습니다
    # (실측: 자산 종류 설명표의 첫 4행이 「소득 › 기타 소득 › 일반 자산」 제목으로 붙던 것)
    first_numeric = next((i for i, row in enumerate(filled) if any(cell and NUMERIC_VALUE.fullmatch(cell) for cell in row)), None)
    if first_numeric is None or not 1 <= first_numeric <= MAX_HEADER_ROWS:
        return []
    header = filled[:first_numeric]
    titles = []
    for c in range(max(len(row) for row in filled)):
        parts: list[str] = []
        for row in header:
            text = row[c] if c < len(row) else ""
            if text and text not in parts:
                parts.append(text)
        titles.append(" › ".join(parts))
    return titles if any(titles) else []


def _reliable_tables(page: Any) -> list[tuple[Any, ...]]:
    """믿을 수 있는 표만 (표, 행들, 병합 칸을 채운 행들, 열 제목). 칸이 영역 글자를 다 담지 못한 표는 뺍니다.
    표 안에 표가 있을 때: 바깥 표가 테두리 상자면(_is_frame) 안쪽 표를 쓰고, 진짜 표면 바깥 표를 씁니다.
    실측: 쪽 전체를 두른 테두리가 큰 표 하나로 읽혀 가격표 45행이 한 덩어리 글자가 됨(부산연지자이2차 2쪽)."""
    found = []
    visible = [ch for ch in page.chars if ch["text"].strip()]  # 표마다 쪽 전체 글자를 다시 거르지 않도록 한 번만 (결과는 같음)
    for table in page.find_tables():
        raw = table.extract()
        keep = [i for i, row in enumerate(raw) if any(c not in (None, "") for c in row)]
        rows = [[_cell(c) for c in raw[i]] for i in keep]
        chars = [ch for ch in visible if _inside(ch, [table.bbox])]
        inside = len(chars)
        captured = sum(_letters(cell) for row in rows for cell in row)
        if not rows or not inside or _shredded(rows):
            continue
        exclude = [table.bbox]
        if captured / inside < TABLE_COVERAGE:
            # 데이터 행에만 바깥 세로선이 없는 표(머리글에만 테두리): 표 양 끝에 세로선을 그어 다시 읽습니다
            # (실측: LH 대전 영구임대 2쪽 형별 공급계획 표의 단지명·난방 열이 표 밖 글자로 빠져 가격표가 안 붙음)
            again = _with_outer_edges(page, table)
            if again is not None:
                again_raw = again.extract()
                again_keep = [i for i, row in enumerate(again_raw) if any(c not in (None, "") for c in row)]
                again_rows = [[_cell(c) for c in again_raw[i]] for i in again_keep]
                again_captured = sum(_letters(cell) for row in again_rows for cell in row)
                if again_rows and again_captured / inside >= TABLE_COVERAGE and not _shredded(again_rows):
                    table, raw, keep, rows, captured = again, again_raw, again_keep, again_rows, again_captured
        if captured / inside < TABLE_COVERAGE:
            # 끝 열에 바깥 테두리선이 없어 그 열 글자가 어느 칸에도 안 든 표(실측: 부산도시공사 109 3쪽 모집대상 주택 표의 연번·난방 열,
            # 0.89로 표 전체가 본문 글자가 됨). 칸 안 글자 기준으로 다시 재고, 칸 밖 글자는 표 옆 본문으로 남깁니다
            boxes = [tuple(box) for box in getattr(table, "cells", None) or []]
            loose = sum(1 for ch in chars if not _inside(ch, boxes))
            in_cells = inside - loose
            if not boxes or not in_cells or loose / inside > LOOSE_MAX_SHARE or captured / in_cells < TABLE_COVERAGE:
                continue
            exclude = boxes
        try:
            spans, span_ids = _spans(table, raw)
            filled, cells = [spans[i] for i in keep], [span_ids[i] for i in keep]
        except (AttributeError, IndexError, TypeError):  # 칸 좌표가 없는 표: 병합 정보 없이 씁니다
            filled, cells = rows, [list(range(len(row))) for row in rows]
        _spread_stacked(rows, filled, cells)
        found.append((table, rows, filled, cells, _column_titles(filled), exclude))
    frames = {id(t) for t, rows, *_ in found if _is_frame(rows) and any(_contains(t.bbox, o[0].bbox) for o in found)}
    kept = []
    for item in found:
        table = item[0]
        if id(table) in frames:
            continue  # 테두리 상자: 안쪽 표를 쓰고, 나머지 영역은 본문 글자로
        if any(id(o[0]) not in frames and _contains(o[0].bbox, table.bbox) for o in found):
            continue  # 진짜 표 안의 작은 표: 바깥 표의 칸에 이미 들어 있음
        kept.append(item)
    return sorted(kept, key=lambda tr: tr[0].bbox[1])


STACKED_AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+")


def _spread_stacked(rows: list[list[str]], filled: list[list[str]], cells: list[list[int]]) -> None:
    """한 열의 행 구분선이 없어 그 열 금액이 첫 칸 하나에 몰리고 아래 칸이 모두 빈 표를 행마다 나눕니다.
    금액 개수가 그 칸부터 표 끝까지의 행 수와 **정확히 같을 때만** 나눕니다(다르면 어느 행 값인지 몰라 그대로 둠).
    실측(LH 청주지북 공공분양 3쪽): 잔금 열의 25행 금액이 「212,620 215,690 … 253,050」 한 칸으로 읽혀 잔금 30개가 빠짐."""
    for c in range(max((len(row) for row in rows), default=0)):
        for r, row in enumerate(rows):
            value = row[c] if c < len(row) else ""
            amounts = STACKED_AMOUNT.findall(value)
            if len(amounts) < 3 or STACKED_AMOUNT.sub("", value).strip():
                continue  # 금액만 여러 개 든 칸만 봅니다
            below = rows[r + 1 :]
            if len(amounts) != 1 + len(below) or any(c < len(other) and other[c] for other in below):
                continue
            for offset, amount in enumerate(amounts):
                target = r + offset
                if c < len(rows[target]):
                    rows[target][c] = amount
                if target < len(filled) and c < len(filled[target]):
                    filled[target][c] = amount
                if target < len(cells) and c < len(cells[target]):
                    cells[target][c] = -1  # 나눈 칸은 병합 칸이 아닙니다
            break


def _with_outer_edges(page: Any, table: Any) -> Any | None:
    """표 상자 양 끝에 세로선을 더해 그 상자 안에서 표를 다시 찾습니다. 상자를 거의 다 덮는 표가 없으면 None."""
    x0, top, x1, bottom = table.bbox
    try:
        found = page.crop(table.bbox).find_tables(table_settings={"explicit_vertical_lines": [x0, x1]})
    except (ValueError, TypeError):
        return None
    best = max(found, key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]), default=None)
    if best is None:
        return None
    area = (best.bbox[2] - best.bbox[0]) * (best.bbox[3] - best.bbox[1])
    return best if area >= 0.9 * (x1 - x0) * (bottom - top) else None


def _shredded(rows: list[list[str]]) -> bool:
    """쪽의 배치 격자를 표로 읽어 글자가 한두 자씩 칸에 흩어진 것(「| 신청 | 자 | 의 당 | 첨자 |」). 이런 영역은 일반 글자로 읽습니다.
    실측: 인천도시공사 10년 분양전환 공고 — 열 70여 개 표에 문장이 낱자로 쪼개져 AI가 읽기 어려웠음. 숫자 칸(가격표)은 길어서 걸리지 않습니다."""
    cells = [_letters(cell) for row in rows for cell in row if cell.strip()]
    if max((len(row) for row in rows), default=0) < SHRED_COLUMNS or len(cells) < 6:
        return False
    return sorted(cells)[len(cells) // 2] <= 2


def _is_frame(rows: list[list[str]]) -> bool:
    """칸 하나가 표 글자의 대부분(FRAME_SHARE 이상)을 담으면 표가 아니라 테두리 상자입니다.
    실측: 쪽 테두리 0.93~0.99(부산연지자이 2쪽 0.99), 진짜 표 0.73~0.84(군산 6쪽 무주택·세대구성원 표 0.73)."""
    sizes = [_letters(cell) for row in rows for cell in row]
    return bool(sizes) and max(sizes) / max(sum(sizes), 1) >= FRAME_SHARE


def _column_split(page: Any) -> float | None:
    """가로로 긴 쪽(모아찍기·2단)에서 가운데에 글자·표가 지나가지 않는 세로 빈 줄을 찾습니다. 없으면 None.
    실측: 익산인화 행복주택 공고는 한 장에 2쪽을 나란히 찍어, 그대로 읽으면 왼쪽·오른쪽 줄이 번갈아 섞임."""
    if page.width <= page.height or len(page.chars) < MIN_CHARS:
        return None
    chars = [c for c in page.chars if c["text"].strip()]
    tables = [t.bbox for t in page.find_tables()]
    best, best_balance = None, 0
    for step in range(0, 41):
        x = page.width * (0.40 + step * 0.005)
        if any(c["x0"] < x < c["x1"] for c in chars) or any(b[0] < x < b[2] for b in tables):
            continue
        left = sum(1 for c in chars if c["x1"] <= x)
        balance = min(left, len(chars) - left)
        if balance > best_balance:
            best, best_balance = x, balance
    return best if best is not None and best_balance >= len(chars) * COLUMN_MIN_SHARE else None


def _secret_columns(rows: list[list[str]]) -> set[int]:
    return {column for row in rows[:3] for column, value in enumerate(row) if is_secret_header(value)}


def _without_secrets(rows: list[list[str]], secret: set[int] | None = None) -> list[list[str]]:
    """공동현관·세대 비밀번호 열은 뺍니다(실측: 경북개발공사 공급주택목록 표에 출입 비밀번호가 있음). 머리 3행으로 열을 찾습니다."""
    secret = _secret_columns(rows) if secret is None else secret
    return [[value for column, value in enumerate(row) if column not in secret] for row in rows] if secret else rows


def _strip_secrets(pages: list[PdfPage]) -> None:
    """쪽을 넘어 이어지는 표: 다음 쪽 첫 표에 머리글이 없으면 앞 표에서 찾은 비밀번호 열을 그대로 뺍니다(검토 2026-10-16).
    열 수가 같고 바로 다음 쪽의 첫 표일 때만 이어진 표로 봅니다."""
    previous: tuple[int, int, set[int]] | None = None  # (쪽, 열 수, 비밀번호 열)
    for page in pages:
        for block in page.blocks:  # 표로 못 읽어 글자로 남은 곳의 "비밀번호 : 1234#" (검토 2026-10-16)
            if block["type"] == "text":
                block["text"] = redact_secret_values(block["text"])
        tables = [b for b in page.blocks if b["type"] == "table"]
        for position, block in enumerate(tables):
            rows = block["rows"]
            width = max((len(r) for r in rows), default=0)
            secret = _secret_columns(rows)
            # 이어진 표 = 바로 다음 쪽의 맨 처음 덩어리(위에 본문 없음)이고 열 수가 같은 표
            continued = (
                previous is not None and position == 0 and page.blocks[0] is block and previous[0] in (page.number, page.number - 1) and previous[1] == width
            )
            if not secret and continued:
                secret = previous[2]
            block["rows"] = _without_secrets(rows, secret)
            if "filled" in block:
                block["filled"] = _without_secrets(block["filled"], secret)
                block["cells"] = _without_secrets(block["cells"], secret)
                block["columns"] = [title for column, title in enumerate(block["columns"]) if column not in secret]
            previous = (page.number, width, secret) if secret else None


def _page_blocks(page: Any, number: int, first_table: int = 1) -> list[dict[str, Any]]:
    """쪽(또는 나눈 반쪽) 하나 → 위에서 아래 순서의 본문·표 묶음. 좌표는 원래 쪽 기준이라 page.bbox 안에서만 자릅니다."""
    x0, y0, x1, y1 = page.bbox
    tables = _reliable_tables(page)
    boxes = [box for t in tables for box in t[5]]  # 보통 표 상자, 끝 열 테두리가 없는 표는 칸 상자(_reliable_tables)
    outside = page.filter(lambda obj: obj.get("object_type") != "char" or not _inside(obj, boxes))
    blocks: list[dict[str, Any]] = []
    top = y0
    for offset, (table, rows, filled, cells, columns, _) in enumerate(tables):
        _, table_top, _, table_bottom = table.bbox
        if table_top > top:
            text = _clean(outside.crop((x0, top, x1, min(table_top, y1))).extract_text() or "").strip()
            if text:
                blocks.append({"type": "text", "text": text})
        # 비밀번호 열은 문서 단위로 뺍니다(_strip_secrets). filled·columns는 표 머리글 붙이기(render(labeled=True))용
        blocks.append({"type": "table", "id": f"{number}-{first_table + offset}", "rows": rows, "filled": filled, "cells": cells, "columns": columns})
        # 표와 같은 높이에 있는 표 밖 글자(표 옆 안내문 등). 위·아래 띠만 읽으면 빠지던 것(검토 2026-10-16)
        beside_top = max(top, table_top)
        if table_bottom > beside_top:
            beside = _clean(outside.crop((x0, beside_top, x1, min(table_bottom, y1))).extract_text() or "").strip()
            if beside:
                blocks.append({"type": "text", "text": beside})
        top = max(top, table_bottom)
    if top < y1:
        text = _clean(outside.crop((x0, top, x1, y1)).extract_text() or "").strip()
        if text:
            blocks.append({"type": "text", "text": text})
    return blocks


# 같은 글자를 조금 어긋나게 겹쳐 찍은 굵은 글씨·그림자 글씨: 글자 크기의 이 비율(1pt 이상)까지 떨어진 같은 글자는 하나로 읽습니다.
# 1pt로만 보면 큰 제목의 그림자(23pt 글자를 1.08pt 어긋나게 회색으로 한 번 더)를 놓쳐 「22002266년년 영영구구…」로 읽혔음(2026-10-26).
# 글자 폭(크기의 절반 이상)보다 훨씬 작아 실제로 이어 쓴 같은 글자(「11」「00」)는 합치지 않습니다
OVERPRINT_SHARE = 0.1


def _dedupe_chars(page: Any) -> Any:
    """겹쳐 찍은 같은 글자(같은 글꼴·크기, 가로·세로 모두 허용 거리 안)를 처음 것 하나만 남깁니다. 색은 보지 않습니다(그림자는 회색)."""
    page = page.dedupe_chars()
    seen: dict[tuple, list[dict[str, Any]]] = {}
    drop: set[int] = set()
    for char in page.chars:
        size = float(char.get("size") or 0)
        tolerance = max(1.0, size * OVERPRINT_SHARE)
        x, top = float(char["x0"]), float(char["top"])
        key = (char["text"], char.get("fontname"), round(size, 1))
        cell = (round(x / tolerance), round(top / tolerance))
        near = [
            other
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for other in seen.get((*key, cell[0] + dx, cell[1] + dy), ())
            if abs(float(other["x0"]) - x) <= tolerance and abs(float(other["top"]) - top) <= tolerance
        ]
        if near and char["text"].strip():
            drop.add(id(char))
        else:
            seen.setdefault((*key, *cell), []).append(char)
    if not drop:
        return page
    return page.filter(lambda obj: obj.get("object_type") != "char" or id(obj) not in drop)


def _read_page(page: Any) -> list[PdfPage]:
    page = _dedupe_chars(page)  # 굵게·그림자로 같은 글자를 겹쳐 찍은 제목을 한 번만 읽습니다 (실측: "부부부부산산산…", "22002266년년…")
    split = _column_split(page)
    if split is None:
        return [PdfPage(page.page_number, _page_blocks(page, page.page_number))]
    halves = [page.crop((0, 0, split, page.height)), page.crop((split, 0, page.width, page.height))]
    left = _page_blocks(halves[0], page.page_number)
    tables_left = sum(1 for b in left if b["type"] == "table")
    right = _page_blocks(halves[1], page.page_number, first_table=tables_left + 1)
    return [PdfPage(page.page_number, left, 0), PdfPage(page.page_number, right, 1)]


def read_pdf(data: bytes) -> PdfDocument | None:
    """PDF 바이트 → 쪽·표 구조. 읽을 수 없거나 글자가 거의 없으면 None."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages: list[PdfPage] = []
            for page in pdf.pages[:MAX_PAGES]:
                pages.extend(_read_page(page))
                # 쪽마다 읽은 글자·선 객체 캐시를 바로 놓습니다. 그대로 두면 문서를 닫을 때까지 모든 쪽의 객체가 메모리에 남습니다
                page.close()
            _strip_secrets(pages)
            _carry_titles(pages)
            document = PdfDocument(len(pdf.pages), pages)
    except Exception:  # 손상·암호 PDF는 읽지 못함으로 처리합니다
        return None
    if len(re.sub(r"\s|---\s*\d+쪽[^\n]*?---", "", document.render())) < MIN_CHARS:
        return None
    return document


IMAGE_PAGE_SHARE = 0.25  # 쪽 넓이의 이만큼 이상을 덮는 그림만 셉니다(로고·도장·작은 사진 제외)
IMAGE_TEXT_CHARS = 5  # 그림 위에 이보다 많은 글자가 있으면 배경 그림으로 보고 셈하지 않습니다(글자는 이미 읽힘)


IMAGE_CACHE_SIZE = 32  # 같은 PDF를 여러 단계에서 물어도 한 번만 엽니다. 결과(쪽 번호 몇 개)만 남기고 PDF 바이트는 붙잡지 않습니다
_image_cache: OrderedDict[str, tuple[tuple[int, float], ...]] = OrderedDict()
_image_cache_lock = threading.Lock()


def image_pages(data: bytes) -> tuple[tuple[int, float], ...]:
    """글자 없는 큰 그림이 있는 쪽: (쪽 번호, 그림이 덮는 비율). 글자 인식을 하지 않으므로 그 안의 내용(그림으로 넣은 표 등)은 읽지 못합니다.
    위치도·평면도도 걸리므로 이것만으로 검수에 보내지 않고, 검증기가 추출 결과와 함께 봅니다(verify/consistency.py).
    결과는 바이트의 sha256으로 기억합니다. 바이트 자체를 키로 쓰면 오래 도는 작업자가 PDF 32건을 통째로 붙잡고 있게 됩니다."""
    key = hashlib.sha256(data).hexdigest()
    with _image_cache_lock:
        if key in _image_cache:
            _image_cache.move_to_end(key)
            return _image_cache[key]
    found = _find_image_pages(data)
    with _image_cache_lock:
        _image_cache[key] = found
        _image_cache.move_to_end(key)
        while len(_image_cache) > IMAGE_CACHE_SIZE:
            _image_cache.popitem(last=False)
    return found


def _find_image_pages(data: bytes) -> tuple[tuple[int, float], ...]:
    import pdfplumber

    found: list[tuple[int, float]] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for number, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                area = float(page.width * page.height) or 1.0
                for image in page.images:
                    x0, x1 = max(float(image["x0"]), 0.0), min(float(image["x1"]), float(page.width))
                    top, bottom = max(float(image["top"]), 0.0), min(float(image["bottom"]), float(page.height))
                    share = max(0.0, x1 - x0) * max(0.0, bottom - top) / area
                    if share < IMAGE_PAGE_SHARE:
                        continue
                    inside = sum(1 for c in page.chars if x0 <= c["x0"] <= x1 and top <= c["top"] <= bottom and c["text"].strip())
                    if inside <= IMAGE_TEXT_CHARS:
                        found.append((number, round(share, 2)))
                page.close()  # read_pdf와 같이 쪽 객체 캐시를 바로 놓습니다
    except Exception:  # 읽기 실패는 read_pdf가 따로 처리합니다
        return ()
    return tuple(found)
