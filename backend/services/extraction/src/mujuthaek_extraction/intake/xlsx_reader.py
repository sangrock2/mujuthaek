"""첨부 엑셀(xlsx) → AI에 넘길 표 글자. 매입·전세임대의 공급주택목록(주소·호·면적·보증금)이 주로 엑셀로 옵니다.

엑셀이 있으면 그 목록을 그대로 원문에 붙여 AI가 호실별 공급 묶음으로 옮기게 하고, 없으면 지금처럼 공고문 PDF에서 읽습니다.
xlsx는 zip 안의 XML이라 표준 라이브러리로 읽습니다(의존성 추가 없음). 수식은 저장된 계산 값을 씁니다. 옛 xls(바이너리)는 읽지 않습니다.
- 공동현관·세대 비밀번호 열은 AI에 넘기지 않습니다(실측: 경북개발공사 목록에 들어 있음).
- 날짜 서식 칸은 날짜(2025-01-21)로 씁니다(엑셀은 45678 같은 일련번호로 저장). 숨긴 시트는 읽지 않습니다.
- 셀 주소가 없거나($A$1·소문자) 이상한 칸은 앞 칸 다음 열로 둡니다. 읽다 생긴 어떤 오류든 None(공고문에서 읽음)으로 돌려줍니다.
- 값이 있는 행이 AI_MAX_ROWS(또는 글자가 AI_MAX_CHARS)를 넘으면(실측: 대구도시공사 2,580호) 머리 몇 행과 전체 행 수만 넘깁니다.
  그때 공급 묶음은 공고문의 주택형별 표로 만들고, 주택별 목록은 원본 첨부를 보게 합니다.
- 주택별 공급 묶음은 AI가 행을 옮겨 적지 않고 공급표 해석기(supply_tables)가 시트 행(sheets)을 코드로 옮깁니다. AI는 열 의미만 답합니다.
  예전에는 200행이 넘으면 머리 행만 넘겨 큰 목록을 쓰지 못했습니다(실측 2026-10-20 LH 98건 중 엑셀 15건, 그중 8건: 233~570행).
AI용 글자 모양(PDF 표와 같은 칸 구분):

  [엑셀 시트 공급주택목록]
  | 연번 | 주소 | 호수 | 전용면적 | 임대보증금 |
  | 1 | 대구 달서구 ... | 301 | 39.6 | 12000000 |
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from xml.etree import ElementTree

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 압축 폭탄 방지
MAX_ROWS = 10_000  # 시트당 읽는 한도
AI_MAX_ROWS = 3_000  # 원문에 붙이는 행 한도(파일 전체). 넘으면 머리 행만. 실측 최대 570행·8.4만 자(2026-10-20)
AI_MAX_CHARS = 400_000  # 원문에 붙이는 글자 한도(입력은 원문 캐시로 읽혀 싸지만 모델 입력 한도 안에 두려고)
HEAD_ROWS = 5
# 출입 비밀번호 머리글. 기관마다 이름이 달라 넓게 봅니다(검토 2026-10-16: "출입번호"·"도어락"은 못 찾았음)
SECRET_HEADER = re.compile(r"비밀\s*번호|비번|공동\s*현관|현관\s*(?:번호|키)|출입\s*(?:번호|코드|비밀)|도어\s*락|도어\s*(?:번호|코드)|세대\s*키")
# 표로 못 읽은 글자 안의 "비밀번호 : 1234#" 같은 값(가림 표시로 바꿈)
SECRET_VALUE = re.compile(r"((?:비밀\s*번호|비번|현관\s*번호|출입\s*(?:번호|코드)|도어\s*락(?:\s*번호)?)\s*[:：]?\s*)[0-9*#()문\-\s]{3,}")


SECRET_HEADER_MAX_CHARS = 20  # 머리글 칸 길이 한도. 긴 안내문 칸(「1층 공동현관 주출입구 …」)을 비밀번호 열로 보면 그 글 전체가 빠집니다


def is_secret_header(cell: str) -> bool:
    """비밀번호 열의 머리글 칸인지. 짧은 칸만 봅니다(실측: 부산 행복주택 입주 유의사항이 한 칸으로 읽힌 표가 통째로 빠졌음)."""
    return len(cell) <= SECRET_HEADER_MAX_CHARS and bool(SECRET_HEADER.search(cell)) and "/" not in cell


def redact_secret_values(text: str) -> str:
    return SECRET_VALUE.sub(lambda m: m[1] + "(가림) ", text)


COLUMN = re.compile(r"\$?([A-Za-z]{1,3})")
# 엑셀 기본 날짜 서식 번호(14~22 날짜·시각, 27~36·50~58 한중일 날짜, 45~47 시각)
DATE_FORMATS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
EXCEL_EPOCH = date(1899, 12, 30)


def _hidden_columns(sheet: ElementTree.Element) -> set[int]:
    """숨긴 열(<cols><col min max hidden="1">, 1부터 센 번호)의 0부터 센 번호."""
    hidden: set[int] = set()
    for col in sheet.iterfind("m:cols/m:col", NS):
        if col.get("hidden") in ("1", "true") and (col.get("min") or "").isdigit() and (col.get("max") or "").isdigit():
            hidden.update(range(int(col.get("min")) - 1, min(int(col.get("max")), 16384)))
    return hidden


def _column_index(ref: str | None, fallback: int) -> int:
    match = COLUMN.match(ref or "")
    if not match:
        return fallback
    index = 0
    for letter in match[1].upper():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


PERCENT_FORMATS = {9, 10}
MERGE_REPEAT_COLUMNS = 6  # 이 열 수 이하로 가로 병합된 칸만 값을 되풀이합니다


@dataclass(frozen=True)
class _Styles:
    dates: frozenset[int] = frozenset()  # 날짜 서식인 셀 스타일 번호(cellXfs의 순서)
    percents: frozenset[int] = frozenset()  # % 서식(0.7을 70%로 보여 주는 칸)


def _styles(archive: zipfile.ZipFile) -> _Styles:
    """styles.xml에서 날짜·% 서식인 셀 스타일 번호를 모읍니다. 파일이 없으면 빈 서식표를 돌려줍니다."""
    if "xl/styles.xml" not in archive.namelist():
        return _Styles()
    root = ElementTree.fromstring(archive.read("xl/styles.xml"))
    custom_dates, custom_percents = set(), set()
    for fmt in root.iterfind("m:numFmts/m:numFmt", NS):
        code = re.sub(r'"[^"]*"|\[[^]]*]|\\.', "", fmt.get("formatCode") or "").lower()  # 따옴표 글자·[색]·이스케이프 제외
        fmt_id = int(fmt.get("numFmtId") or -1)
        if re.search(r"[yd]", code):  # 연·일이 있으면 날짜 서식 (월 m만 있으면 분과 헷갈려 보지 않음)
            custom_dates.add(fmt_id)
        elif "%" in code:
            custom_percents.add(fmt_id)
    dates, percents = set(), set()
    for index, xf in enumerate(root.iterfind("m:cellXfs/m:xf", NS)):
        fmt_id = int(xf.get("numFmtId") or 0)
        if fmt_id in DATE_FORMATS or fmt_id in custom_dates:
            dates.add(index)
        elif fmt_id in PERCENT_FORMATS or fmt_id in custom_percents:
            percents.add(index)
    return _Styles(frozenset(dates), frozenset(percents))


NO_STYLES = _Styles()


def _merged_ranges(sheet: ElementTree.Element) -> list[tuple[int, int, int, int]]:
    """병합 셀 범위 (첫 행, 첫 열, 끝 행, 끝 열). 행 번호는 엑셀 번호(1부터)."""
    out = []
    for merge in sheet.iterfind("m:mergeCells/m:mergeCell", NS):
        corners = (merge.get("ref") or "").split(":")
        points = [re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", corner) for corner in corners]
        if len(points) == 2 and all(points):
            (c1, r1), (c2, r2) = [(_column_index(p[1], 0), int(p[2])) for p in points]
            out.append((r1, c1, r2, c2))
    return out


def _number(text: str) -> str:
    """엑셀이 저장한 숫자(12000000.0, 39.600000000000001)를 사람이 보는 모양에 가깝게 씁니다."""
    try:
        value = float(text)
    except ValueError:
        return text
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _text(node: ElementTree.Element | None) -> str:
    return "".join(t.text or "" for t in node.iter(f"{{{NS['m']}}}t")) if node is not None else ""


def _cell(cell: ElementTree.Element, shared: list[str], styles: _Styles = NO_STYLES) -> str:
    """셀 하나를 화면에 보이는 모양의 글자로 바꿉니다(공유 문자열·날짜·% 서식 반영, 공백은 한 칸으로)."""
    kind = cell.get("t")
    if kind == "inlineStr":
        value = _text(cell.find("m:is", NS))
    else:
        raw = cell.findtext("m:v", default="", namespaces=NS)
        if kind == "s":
            value = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
        elif kind in ("str", "e", "b"):
            value = raw
        elif raw and (cell.get("s") or "").isdigit() and int(cell.get("s")) in styles.dates:
            try:
                value = (EXCEL_EPOCH + timedelta(days=int(float(raw)))).isoformat()
            except (ValueError, OverflowError):
                value = _number(raw)
        elif raw and (cell.get("s") or "").isdigit() and int(cell.get("s")) in styles.percents:
            try:
                value = _number(str(round(float(raw) * 100, 6))) + "%"  # 엑셀은 70%를 0.7로 저장합니다
            except ValueError:
                value = _number(raw)
        else:
            value = _number(raw) if raw else ""
    return re.sub(r"\s+", " ", value).strip()


def _sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(시트 이름, zip 안 경로) — 통합 문서에 적힌 순서대로."""
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for sheet in workbook.iterfind("m:sheets/m:sheet", NS):
        if sheet.get("state") in ("hidden", "veryHidden"):
            continue  # 숨긴 시트(옛 목록·계산용)는 AI에 넘기지 않습니다
        target = targets.get(sheet.get(REL_NS), "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        out.append((sheet.get("name") or "", path))
    return out


@dataclass(frozen=True)
class XlsxList:
    text: str  # AI에 넘길 글자
    rows: int  # 값이 있는 행 수(머리 행 포함)
    truncated: bool  # AI_MAX_ROWS·AI_MAX_CHARS를 넘어 머리 행만 넘김
    sheets: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()  # (시트 이름, 원문에 붙인 행들). 잘리면 비움(근거로 찾을 수 없으므로)
    hidden: int = 0  # 넘기지 않은 숨긴 행·열 수(값이 있는 것만)
    hidden_rows: int = 0  # 그중 숨긴 행 수. 있으면 접수가 사람 확인을 남김(숨긴 열만이면 남기지 않음)


HEADER_SCAN = 10  # 시트 맨 위 몇 행에서 머리 행을 찾을지(제목·안내 행이 먼저 올 수 있음)
HEADER_DEPTH = 3  # 묶음 제목 줄(「주택정보」「임대조건」) 아래 칸 이름 줄까지
HEADER_WORD = re.compile(r"주소|소재지|주택|호|동|면적|보증금|임대료|월세|공급|모집")
NUMERIC_CELL = re.compile(r"[-+]?[\d,]+(?:\.\d+)?\s*(?:원|만원|천원|㎡|%|호|세대)?")
TITLE_LINE = "  [열 제목] "  # verify/consistency.TITLE_LINE·pdf_reader와 같은 줄: 검증이 맨 위 제목·안내 행을 열 제목으로 읽지 않게


def _header_like(row: list[str]) -> bool:
    return sum(1 for c in row if c) >= 3 and not any(NUMERIC_CELL.fullmatch(c) for c in row if c)


def _header_rows(rows: list[list[str]]) -> tuple[int, int] | None:
    """머리 행 범위 (시작, 끝 다음). 맨 위 제목·안내 줄(칸 1~2개) 다음, 칸 이름이 셋 이상이고 주택·금액 낱말이 있는 첫 줄부터
    숫자 없는 줄이 이어지는 데까지(최대 3줄). 실측(2026-10-26 LH 청년 매입임대 주택목록): 제목 「…청년…」·안내 「…공가 추가…」
    줄 다음에 「주택정보」「수급자 등」 묶음 줄과 칸 이름 줄이 있어요. 열 제목 줄이 없으면 검증(V6)이 제목·안내 글을 열 제목으로 읽어
    모든 열을 "청년"·"공가" 열로 보던 오탐이 났어요(37행 보류)."""
    for start, row in enumerate(rows[:HEADER_SCAN]):
        if _header_like(row) and any(HEADER_WORD.search(c) for c in row):
            end = start + 1
            while end < len(rows) and end - start < HEADER_DEPTH and _header_like(rows[end]):
                end += 1
            return start, end
    return None


def _title_line(rows: list[list[str]], start: int, end: int) -> str:
    """머리 행들을 칸마다 위아래로 이어 붙인 열 제목 줄 (「  [열 제목] 1. 순번 | 2. 지자체 지역본부 | …」)."""
    width = max(len(r) for r in rows[start:end])
    titles = []
    for i in range(width):
        parts: list[str] = []
        for row in rows[start:end]:
            cell = row[i] if i < len(row) else ""
            if cell and cell not in parts:
                parts.append(cell)
        titles.append(" ".join(parts) or "-")
    return TITLE_LINE + " | ".join(f"{i + 1}. {t}" for i, t in enumerate(titles))


def read_xlsx(data: bytes) -> XlsxList | None:
    """시트마다 [엑셀 시트 이름] 다음에 표 행을 적은 글자. 읽을 수 없거나 값이 하나도 없으면 None."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            return None
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [_text(item) for item in root.iterfind("m:si", NS)]
        styles = _styles(archive)
        sheets: list[tuple[str, list[list[str]], int]] = []
        hidden_total = hidden_row_total = 0
        for name, path in _sheets(archive):
            if path not in archive.namelist():
                continue
            sheet = ElementTree.fromstring(archive.read(path))
            by_number: dict[int, dict[int, str]] = {}
            counted, number, uncached = 0, 0, 0
            # 숨긴 행(필터로 가린 행 포함)·열은 넘기지 않아요: 기관이 이번 공고가 아닌 호실을 지우지 않고 숨긴 채 첨부하면, 숨긴 호실이
            # 보증금·임대료와 함께 공급 묶음으로 게시됐어요(2026-11-10 코드 검토). 숨긴 것이 있으면 접수가 사람 확인을 남깁니다
            hidden_columns = _hidden_columns(sheet)
            hidden_rows, hidden_values = 0, set()
            hidden_cells: dict[int, dict[int, str]] = {}  # 숨긴 행의 값: 넘기지 않지만 병합 칸의 값이 거기 있으면 보이는 행에 채움
            for row in sheet.iterfind("m:sheetData/m:row", NS):
                number = int(row.get("r")) if (row.get("r") or "").isdigit() else number + 1
                cells: dict[int, str] = {}
                column = 0
                for cell in row.iterfind("m:c", NS):
                    column = _column_index(cell.get("r"), column)
                    value = _cell(cell, shared, styles)
                    if value and column in hidden_columns:
                        hidden_values.add(column)
                    elif value:
                        cells[column] = value
                    elif cell.find("m:f", NS) is not None:
                        uncached += 1  # 수식만 있고 저장된 계산값이 없는 칸: 빈칸처럼 보이지만 값이 없는 것이 아닙니다
                    column += 1
                if cells and row.get("hidden") in ("1", "true"):
                    hidden_rows += 1
                    hidden_cells[number] = cells
                    continue
                if cells:
                    counted += 1
                    if len(by_number) < MAX_ROWS:  # 읽어 두는 행은 한도까지, 행 수는 끝까지 셉니다
                        by_number[number] = cells
            # 병합 셀: 값은 왼쪽 위 칸에만 있으므로 범위 안의 다른 칸에도 채웁니다(단지명이 여러 호실 행에 병합된 목록 — 검토 2026-10-16)
            # 가로로는 좁은 병합(머리글 "1순위"가 세 열에 걸침)만 채웁니다. 한 줄 전체에 걸친 제목을 열 수만큼 되풀이하면 잡음입니다.
            for r1, c1, r2, c2 in _merged_ranges(sheet):
                # 병합 범위의 첫 행이 숨긴 행이어도 그 값(단지명 등)은 보이는 행의 것이에요(재검토: 보이는 행에서 빠졌음)
                value = (by_number.get(r1) or hidden_cells.get(r1) or {}).get(c1)
                if value:
                    last_column = c2 if c2 - c1 < MERGE_REPEAT_COLUMNS else c1
                    for r in range(r1, r2 + 1):
                        if r in by_number:
                            for c in range(c1, last_column + 1):
                                by_number[r].setdefault(c, value)
            hidden_total += hidden_rows + len(hidden_values)
            hidden_row_total += hidden_rows
            rows = [by_number[n] for n in sorted(by_number)]
            if not rows:
                continue
            secret = {column for cells in rows[:10] for column, value in cells.items() if is_secret_header(value)}
            # 값이 없는 열·비밀번호 열·숨긴 열(병합 칸 채우기로 들어온 값도)은 뺍니다
            used = sorted({column for cells in rows for column in cells} - secret - hidden_columns)
            sheets.append((name, [[cells.get(column, "") for column in used] for cells in rows], counted, uncached))
        total = sum(sheet[2] for sheet in sheets)
        if not total:
            return None
        full = sum(len(" | ".join(row)) + 4 for _, rows, _, _ in sheets for row in rows)
        truncated = total > AI_MAX_ROWS or full > AI_MAX_CHARS
        lines: list[str] = []
        for name, rows, counted, uncached in sheets:
            lines.append(f"[엑셀 시트 {name}]")
            shown = rows[:HEAD_ROWS] if truncated else rows
            header = _header_rows(shown)
            for index, row in enumerate(shown):
                lines.append("| " + " | ".join(row) + " |")
                if header and index == header[1] - 1:
                    lines.append(_title_line(shown, *header))
            if uncached:  # 설계 검토(2026-10-17): 수식과 저장값을 구분. 계산되지 않은 수식 칸을 '미기재'로 읽지 않게 알립니다
                note = f"(이 시트에는 저장된 계산값이 없는 수식 칸이 {uncached}개 있어 빈칸으로 보입니다."
                lines.append(note + " 그 값은 원문에 없는 것이 아니라 읽지 못한 것입니다.)")
            if truncated:
                lines.append(f"(이 시트는 모두 {counted}행입니다. 주택이 너무 많아 머리 {len(shown)}행만 보입니다.)")
        if hidden_total:
            lines.append(f"(숨긴 행·열 {hidden_total}개는 이번 공급 목록이 아닐 수 있어 넘기지 않았습니다.)")
        shown_sheets = () if truncated else tuple((name, tuple(tuple(row) for row in rows)) for name, rows, _, _ in sheets)
        return XlsxList("\n".join(lines), total, truncated, shown_sheets, hidden_total, hidden_row_total)
    except Exception:  # 깨진 zip·암호·지원 안 하는 압축(Deflate64)·이상한 XML 등: 공고문에서 읽도록 None
        return None
