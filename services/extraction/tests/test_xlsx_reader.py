"""첨부 엑셀(공급주택목록) → AI 원문. 테스트 안에서 작은 xlsx(zip + XML)를 직접 만들어 씁니다. 네트워크·아카이브 없음."""

import copy
import io
import zipfile

from events import raw_event
from test_pdf_reader import CELLS, attachment, make_pdf

from mujuthaek_extraction.intake import InMemorySourceReader, build_intake
from mujuthaek_extraction.intake.xlsx_reader import AI_MAX_ROWS, read_xlsx

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HEADER = ["연번", "주소", "호", "공동현관 비밀번호", "전용면적", "임대보증금"]


def make_xlsx(rows: list[list[str | float]], sheet: str = "주택목록") -> bytes:
    """글자는 공유 문자열, 숫자는 숫자 칸으로 쓴 1시트 xlsx."""
    shared: list[str] = []
    xml_rows = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{chr(ord('A') + c)}{r}"
            if isinstance(value, str):
                shared.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        sheets = f'<sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets>'
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{REL}">{sheets}</workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{MAIN}">' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    return out.getvalue()


LISTING = [HEADER, [1, "대구광역시 남구 안지랑로3길 7", "105", "1234*", 19.68, 795500], [2, "대구광역시 남구 앞산순환로95길 34", "501", "5678*", 23.4, 947500]]


def test_listing_rows_are_rendered_without_door_passwords():
    listing = read_xlsx(make_xlsx(LISTING))
    assert listing is not None and listing.rows == 3 and not listing.truncated
    assert "[엑셀 시트 주택목록]" in listing.text
    assert "| 1 | 대구광역시 남구 안지랑로3길 7 | 105 | 19.68 | 795500 |" in listing.text  # 숫자는 엑셀 저장값 그대로(소수점 꼬리 없음)
    assert "비밀번호" not in listing.text and "1234*" not in listing.text


def test_unreadable_or_empty_spreadsheet_is_none():
    assert read_xlsx(b"not a zip") is None
    assert read_xlsx(make_xlsx([])) is None


def test_listing_too_large_keeps_only_head_rows():
    rows = [HEADER, *([n, f"주소 {n}", str(n), "0000", 20.0, 1000000] for n in range(AI_MAX_ROWS + 10))]
    listing = read_xlsx(make_xlsx(rows))
    assert listing.truncated and listing.rows == AI_MAX_ROWS + 11
    assert "주소 3" in listing.text and f"주소 {AI_MAX_ROWS}" not in listing.text and "머리 5행만" in listing.text


def test_delivered_listing_is_appended_after_notice_pdf():
    pdf, sheet = make_pdf(CELLS), make_xlsx(LISTING)
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", pdf), attachment("목록.xlsx", sheet)]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": pdf, "raw/x/목록.xlsx": sheet}))
    assert intake.ready and intake.material.text_document_id == "pdf-text"
    text = intake.material.text
    assert text.index("[표 1-1]") < text.index("=== 첨부 엑셀 목록.xlsx ===") and "안지랑로3길 7 | 105" in text
    documents = {d["id"]: d for d in intake.context.documents}
    assert documents["file-2"]["kind"] == "SPREADSHEET" and "엑셀" in documents["pdf-text"]["name"]


def test_without_listing_or_with_old_xls_notice_pdf_alone_is_used():
    pdf = make_pdf(CELLS)
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", pdf), attachment("목록.xls", b"old binary")]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": pdf, "raw/x/목록.xls": b"old binary"}))
    assert intake.ready and "첨부 엑셀" not in intake.material.text
    assert "SPREADSHEET_UNREADABLE" in {i.code for i in intake.issues}


def raw_xlsx(sheet_xml: str, *, styles: str | None = None, extra_sheet: str | None = None) -> bytes:
    """직접 쓴 시트 XML로 만든 xlsx. extra_sheet: 숨긴 두 번째 시트의 XML."""
    sheets = '<sheet name="목록" sheetId="1" r:id="rId1"/>'
    rels = '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
    if extra_sheet:
        sheets += '<sheet name="옛 목록" sheetId="2" state="hidden" r:id="rId2"/>'
        rels += '<Relationship Id="rId2" Target="worksheets/sheet2.xml"/>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>{sheets}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f"<Relationships>{rels}</Relationships>")
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{MAIN}"><sheetData>{sheet_xml}</sheetData></worksheet>')
        if extra_sheet:
            archive.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{MAIN}"><sheetData>{extra_sheet}</sheetData></worksheet>')
        if styles:
            archive.writestr("xl/styles.xml", f'<styleSheet xmlns="{MAIN}">{styles}</styleSheet>')
    return out.getvalue()


def inline(ref, text):
    attr = f' r="{ref}"' if ref else ""
    return f'<c{attr} t="inlineStr"><is><t>{text}</t></is></c>'


def test_odd_or_missing_cell_references_do_not_crash_or_overwrite():
    # 검토 지적: r="$A$1"·소문자는 TypeError로 멈췄고, r이 없는 칸은 모두 A열로 겹쳐 썼음
    row = f'<row r="1">{inline("$A$1", "주소")}{inline("b1", "호")}{inline(None, "보증금")}</row>'
    row += f'<row r="2">{inline(None, "달서구 1")}{inline(None, "301")}<c><v>12000000</v></c></row>'
    listing = read_xlsx(raw_xlsx(row))
    assert "| 주소 | 호 | 보증금 |" in listing.text and "| 달서구 1 | 301 | 12000000 |" in listing.text


def test_date_cells_become_dates_and_hidden_sheets_are_skipped():
    styles = '<numFmts count="1"><numFmt numFmtId="176" formatCode="yyyy&quot;년&quot; m&quot;월&quot; d&quot;일&quot;"/></numFmts>'
    styles += '<cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="176"/></cellXfs>'
    row = f'<row r="1">{inline("A1", "입주일")}<c r="B1" s="1"><v>45678</v></c><c r="C1" s="2"><v>45679</v></c><c r="D1" s="0"><v>45678</v></c></row>'
    hidden = f'<row r="1">{inline("A1", "지난 목록")}</row>'
    listing = read_xlsx(raw_xlsx(row, styles=styles, extra_sheet=hidden))
    assert "| 입주일 | 2025-01-21 | 2025-01-22 | 45678 |" in listing.text  # 날짜 서식만 날짜로
    assert "지난 목록" not in listing.text and "옛 목록" not in listing.text


def test_encrypted_or_unsupported_zip_is_unreadable_not_crashing(monkeypatch):
    import mujuthaek_extraction.intake.xlsx_reader as reader

    def broken(*args, **kwargs):
        raise NotImplementedError("That compression method is not supported")

    monkeypatch.setattr(reader.zipfile.ZipFile, "read", broken)
    assert read_xlsx(make_xlsx(LISTING)) is None


def test_merged_cells_repeat_their_value_and_percent_cells_show_percent():
    # 검토 지적: 병합 셀은 왼쪽 위 칸에만 값이 있어 아래 호실 행의 단지명이 비었고, % 서식 칸은 0.7로 나왔음
    rows = f'<row r="1">{inline("A1", "단지")}{inline("B1", "호")}{inline("C1", "소득 기준")}</row>'
    rows += f'<row r="2">{inline("A2", "로얄")}{inline("B2", "301")}<c r="C2" s="1"><v>0.7</v></c></row>'
    rows += f'<row r="3">{inline("B3", "302")}<c r="C3" s="1"><v>1.2</v></c></row>'
    sheet = rows + '</sheetData><mergeCells><mergeCell ref="A2:A3"/></mergeCells><sheetData>'
    styles = '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="9"/></cellXfs>'
    listing = read_xlsx(raw_xlsx(sheet, styles=styles))
    assert "| 로얄 | 301 | 70% |" in listing.text and "| 로얄 | 302 | 120% |" in listing.text


def test_formula_cells_without_saved_values_are_flagged_not_treated_as_blank():
    # 설계 검토(2026-10-17): 수식과 저장값을 구분합니다. 계산값이 저장되지 않은 수식 칸은 「원문에 없음」이 아니라 「읽지 못함」
    row = f'<row r="1">{inline("A1", "주소")}{inline("B1", "보증금")}{inline("C1", "월세")}</row>'
    row += f'<row r="2">{inline("A2", "달서구 1")}<c r="B2"><f>C2*100</f><v>12000000</v></c><c r="C2"><f>B2/100</f></c></row>'
    listing = read_xlsx(raw_xlsx(row))
    assert "| 달서구 1 | 12000000 | |" in listing.text or "| 달서구 1 | 12000000 |" in listing.text  # 저장값이 있는 수식은 그 값
    assert "계산값이 없는 수식 칸이 1개" in listing.text


def test_column_title_line_follows_header_rows_below_title_and_notice_lines():
    """실측(2026-10-26 LH 청년 매입임대 주택목록): 맨 위 제목·안내 줄 다음 묶음 줄과 칸 이름 줄. 열 제목 줄이 없으면 검증(V6)이
    제목 「…청년…」을 열 제목으로 읽어 모든 가격을 "청년" 열로 보고 보류했어요."""
    rows = [
        ["경기북부 청년 매입임대주택 공급대상 주택목록"],
        ["* 주택목록은 해당주택 공가 추가 등으로 변경될 수 있습니다."],
        ["순번", "주택정보", "", "수급자 등", "그 외"],
        ["순번", "주소", "호", "임대보증금", "임대보증금"],
        [1, "경기도 김포시 김포한강10로133번길 126", "214", 1000000, 2000000],
    ]
    lines = read_xlsx(make_xlsx(rows)).text.splitlines()
    title = lines.index("  [열 제목] 1. 순번 | 2. 주택정보 주소 | 3. 호 | 4. 수급자 등 임대보증금 | 5. 그 외 임대보증금")
    assert lines[title - 1].startswith("| 순번 | 주소 |") and lines[title + 1].startswith("| 1 |")


def test_no_title_line_when_no_header_row_is_found():
    listing = read_xlsx(make_xlsx([[1, "가", 3], [2, "나", 4]]))
    assert "[열 제목]" not in listing.text


def test_hidden_rows_and_columns_are_not_handed_over_and_are_counted():
    # 2026-11-10 코드 검토: 이번 공고가 아닌 호실을 지우지 않고 숨긴(필터로 가린) 목록을 첨부하면 숨긴 호실이 공급 묶음으로 게시됐음
    rows = f'<row r="1">{inline("A1", "호")}{inline("B1", "보증금")}{inline("C1", "이전 보증금")}</row>'
    rows += f'<row r="2">{inline("A2", "301")}<c r="B2"><v>12000000</v></c><c r="C2"><v>11000000</v></c></row>'
    rows += f'<row r="3" hidden="1">{inline("A3", "302")}<c r="B3"><v>13000000</v></c></row>'
    sheet = rows + '</sheetData><cols><col min="3" max="3" hidden="1"/></cols><sheetData>'
    listing = read_xlsx(raw_xlsx(sheet))
    assert "| 301 | 12000000 |" in listing.text and "302" not in listing.text and "이전 보증금" not in listing.text
    assert listing.hidden == 2 and "숨긴 행·열 2개" in listing.text
    assert read_xlsx(raw_xlsx(f'<row r="1">{inline("A1", "호")}</row>')).hidden == 0
