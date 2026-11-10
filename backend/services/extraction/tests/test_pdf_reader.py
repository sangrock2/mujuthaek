"""PDF → 쪽·표 구조. 테스트 안에서 작은 PDF(본문 + 격자선 표)를 직접 만들어 씁니다. 네트워크·아카이브 없음."""

import copy
import hashlib

from events import raw_event

from mujuthaek_extraction.intake import InMemorySourceReader, build_intake
from mujuthaek_extraction.intake.pdf_reader import _without_secrets, read_pdf

BODY = "Rental notice for test housing. Applicants must be homeless households. " * 4


def make_pdf(
    cells: list[list[str]], body: str = BODY, frame: bool = False, bold_title: str = "", side: str = "", open_edge: bool = False, shadow_title: str = ""
) -> bytes:
    """본문 + 아래쪽 격자 표가 있는 1쪽 PDF (Helvetica, ASCII만). frame: 쪽 전체 테두리, bold_title: 같은 글자를 겹쳐 찍은 제목,
    open_edge: 왼쪽 바깥 세로선을 머리 행에만 그어 데이터 행 첫 열 글자가 어느 칸에도 안 들게 함."""
    lines = [body[i : i + 80] for i in range(0, len(body), 80)]
    ops = [f"BT /F1 9 Tf 40 {770 - 12 * n} Td ({line}) Tj ET" for n, line in enumerate(lines)]
    if frame:
        ops.append("20 20 m 592 20 l S 20 785 m 592 785 l S 20 20 m 20 785 l S 592 20 m 592 785 l S")
    if side:  # 표와 같은 높이, 표 오른쪽의 안내문
        ops.append(f"BT /F1 9 Tf 420 585 Td ({side}) Tj ET")
    for dx in (0, 0.2, 0.4) if bold_title else ():
        ops.append(f"BT /F1 14 Tf {40 + dx} 782 Td ({bold_title}) Tj ET")
    if shadow_title:  # 회색 그림자 위에 검은 글자를 1.08pt 어긋나게 (실측 부산도시공사 공고 제목, 23pt)
        ops.append(f"0.75 g BT /F1 23 Tf 41.08 700 Td ({shadow_title}) Tj ET 0 g")
        ops.append(f"BT /F1 23 Tf 40 701.08 Td ({shadow_title}) Tj ET")
    left, top, width, height = 40, 600, 120, 20
    rows, cols = len(cells), len(cells[0])
    for r in range(rows + 1):
        y = top - r * height
        ops.append(f"{left} {y} m {left + cols * width} {y} l S")
    for c in range(cols + 1):
        x = left + c * width
        bottom = top - (height if open_edge and c == 0 else rows * height)
        ops.append(f"{x} {top} m {x} {bottom} l S")
    for r, row in enumerate(cells):
        for c, text in enumerate(row):
            ops.append(f"BT /F1 10 Tf {left + c * width + 5} {top - (r + 1) * height + 6} Td ({text}) Tj ET")
    stream = "\n".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body_bytes in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


CELLS = [["Type", "Deposit", "Rent"], ["39A", "9,330", "82,630"]]


def _file_fields(name: str) -> dict:
    """계약의 첨부 칸: 파일 형식·역할·S3 경로(raw/…)."""
    file_type = name.rsplit(".", 1)[-1].lower()
    role = "UNIT_LIST" if file_type.startswith("xls") else "NOTICE_DOC"
    return {"fileType": file_type, "role": role, "s3Key": f"raw/x/{name}"}


def attachment(name: str, data: bytes) -> dict:
    return {"name": name, "downloadUrl": f"https://example.org/{name}", "sha256": hashlib.sha256(data).hexdigest(), **_file_fields(name)}


def test_tables_are_kept_as_rows_and_removed_from_body():
    document = read_pdf(make_pdf(CELLS))
    assert document is not None and document.page_count == 1
    blocks = document.pages[0].blocks
    assert [b["type"] for b in blocks] == ["text", "table"]  # 위에서 아래 순서
    assert blocks[1]["rows"] == CELLS and blocks[1]["id"] == "1-1"
    assert "9,330" not in blocks[0]["text"]  # 표 글자는 본문에 섞이지 않음
    rendered = document.render()
    assert "--- 1쪽 ---" in rendered and "[표 1-1]" in rendered and "39A | 9,330 | 82,630" in rendered


def test_pdf_without_text_is_unreadable():
    assert read_pdf(make_pdf([["", ""], ["", ""]], body="")) is None
    assert read_pdf(b"not a pdf") is None


def test_delivered_pdf_becomes_extraction_text():
    data = make_pdf(CELLS)
    event = raw_event()
    event = copy.deepcopy(event)
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": data}))
    assert intake.ready
    assert intake.material.text_document_id == "pdf-text" and "[표 1-1]" in intake.material.text
    documents = {d["id"]: d for d in intake.context.documents}
    assert documents["file-1"]["pageCount"] == 1 and documents["pdf-text"]["kind"] == "TEXT"
    assert intake.material.pdf_pages[0]["pages"][0]["blocks"][1]["rows"] == CELLS


def test_scanned_pdf_falls_back_to_collector_text():
    data = make_pdf([["", ""], ["", ""]], body="")
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("scan.pdf", data)]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/scan.pdf": data}))
    assert intake.ready and intake.material.text_document_id == "text"
    assert "PDF_TEXT_UNREADABLE" in {i.code for i in intake.issues}


def test_page_frame_box_is_not_used_as_table():
    # 쪽 전체 테두리가 표로 읽혀도 안쪽 진짜 표를 씁니다 (부산연지자이2차 실측)
    document = read_pdf(make_pdf(CELLS, frame=True))
    tables = [b for b in document.pages[0].blocks if b["type"] == "table"]
    assert [t["rows"] for t in tables] == [CELLS]
    assert "Rental notice" in document.render()


def test_overprinted_bold_title_is_read_once():
    document = read_pdf(make_pdf(CELLS, bold_title="Gunsan Notice"))
    assert "Gunsan Notice" in document.render() and "GGG" not in document.render()


def two_column_pdf(left: list[str], right: list[str]) -> bytes:
    """한 장에 2쪽을 나란히 찍은 가로 PDF (모아찍기). 왼쪽·오른쪽 줄이 같은 높이에 있습니다."""
    ops = []
    for n, (a, b) in enumerate(zip(left, right, strict=True)):
        y = 560 - 14 * n
        ops.append(f"BT /F1 10 Tf 40 {y} Td ({a}) Tj ET")
        ops.append(f"BT /F1 10 Tf 440 {y} Td ({b}) Tj ET")
    stream = "\n".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body_bytes in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_two_up_sheet_is_read_left_then_right():
    # 모아찍기: 그대로 읽으면 왼쪽·오른쪽 줄이 번갈아 섞임 (익산인화 행복주택 실측)
    left = [f"Student rule {n} must hold for students" for n in range(12)]
    right = [f"Youth rule {n} must hold for youth" for n in range(12)]
    document = read_pdf(two_column_pdf(left, right))
    assert [(p.number, p.column) for p in document.pages] == [(1, 0), (1, 1)]
    rendered = document.render()
    assert rendered.index("Student rule 11") < rendered.index("--- 1쪽 오른쪽 ---") < rendered.index("Youth rule 0")
    assert "Student rule 0 must hold for students\nStudent rule 1" in rendered


def test_door_password_columns_are_dropped_from_tables():
    # 경북개발공사 공급주택목록 표 실측: 공동현관·세대 비밀번호 열이 있음
    rows = [["호", "공동현관 비밀번호", "세대 비밀번호", "임대보증금"], ["302", "4680", "4680*", "1,000,000"]]
    assert _without_secrets(rows) == [["호", "임대보증금"], ["302", "1,000,000"]]
    assert _without_secrets(CELLS) == CELLS


def test_text_beside_table_is_kept():
    # 검토 지적: 표와 같은 높이의 표 밖 글자는 위·아래 띠에 들지 않아 통째로 빠졌음
    rendered = read_pdf(make_pdf([["Type", "Deposit"], ["39A", "9,330"], ["46B", "9,990"]], side="Deposit can be converted")).render()
    assert "Deposit can be converted" in rendered
    assert rendered.index("[표 1-1]") < rendered.index("Deposit can be converted")


def test_table_with_open_outer_edge_is_reread_with_the_edge_column():
    # 실측: 부산도시공사 109 3쪽 모집대상 주택 표 — 연번 열에 바깥 세로선이 없어 칸 밖 글자 때문에 표 전체가 본문 글자가 됐음.
    # 실측 LH 대전 영구임대: 데이터 행에만 바깥 세로선이 없어 단지명 열이 표 밖 글자로 빠짐 → 양 끝 세로선을 더해 다시 읽습니다
    cells = [["No", "Type", "Households", "Recruit"], ["1", "39A", "143", "28"], ["2", "34", "114", "11"], ["3", "45A", "34", "5"]]
    document = read_pdf(make_pdf(cells, open_edge=True))
    tables = [b for b in document.pages[0].blocks if b["type"] == "table"]
    assert tables and tables[0]["rows"][1] == ["1", "39A", "143", "28"]
    rendered = document.render()
    assert "[표 1-1]" in rendered and "\n1\n" not in rendered and "\n2\n" not in rendered  # 연번이 표 밖 글자로 되풀이되지 않음


def test_scanned_pages_with_only_page_numbers_are_counted_per_page():
    # 검토 지적: 문서 전체 200자 기준이라, 쪽마다 쪽 번호만 있는 스캔본도 "읽힘"으로 봤음
    from mujuthaek_extraction.intake.pdf_reader import PdfDocument, PdfPage

    pages = [PdfPage(n, [{"type": "text", "text": f"- {n} -"}]) for n in range(1, 9)]
    pages[0].blocks = [{"type": "text", "text": BODY}]
    assert PdfDocument(8, pages).empty_pages() == [2, 3, 4, 5, 6, 7, 8]


def test_password_column_is_stripped_on_table_continued_next_page():
    # 검토 지적: 쪽을 넘어 이어진 표의 둘째 쪽에는 머리글이 없어 비밀번호 열이 그대로 남았음
    from mujuthaek_extraction.intake.pdf_reader import PdfPage, _strip_secrets

    first = PdfPage(3, [{"type": "table", "id": "3-1", "rows": [["호", "세대 비밀번호", "보증금"], ["301", "1234*", "1,000,000"]]}])
    second = PdfPage(4, [{"type": "table", "id": "4-1", "rows": [["302", "5678*", "1,000,000"]]}])
    other = PdfPage(5, [{"type": "text", "text": BODY}, {"type": "table", "id": "5-1", "rows": [["39A", "16", "9,330"]]}])
    _strip_secrets([first, second, other])
    assert second.blocks[0]["rows"] == [["302", "1,000,000"]]
    assert other.blocks[1]["rows"] == [["39A", "16", "9,330"]]  # 이어진 표가 아니면 건드리지 않음


def test_one_unreadable_pdf_among_several_forces_review():
    # 검토 지적: 스캔본 공고 + 읽히는 신청서 PDF면 신청서만으로 추출하고 사람 확인을 강제하지 않았음
    readable, scanned = make_pdf(CELLS), make_pdf([["", ""], ["", ""]], body="")
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", scanned), attachment("form.pdf", readable)]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": scanned, "raw/x/form.pdf": readable}))
    assert intake.ready and intake.material.text_document_id == "pdf-text"
    assert "PDF_TEXT_UNREADABLE" in {code for code, _ in intake.context.forced_review}


def test_password_headers_are_found_by_other_names_but_long_notes_are_kept():
    # 검토 지적: "출입번호"·"도어락"은 못 찾았음 / 보정 중 발견: 「1층 공동현관 주출입구」가 든 긴 안내 칸이 통째로 빠지던 것
    assert _without_secrets([["호", "출입번호", "보증금"], ["301", "#4680", "1,000,000"]]) == [["호", "보증금"], ["301", "1,000,000"]]
    note = "- 방범용 CCTV는 주차장, 1층 승강기 홀, 1층 공동현관 주출입구 등에 설치되어 있습니다."
    assert _without_secrets([[note]]) == [[note]]
    assert _without_secrets([["옵션", "도어락 / 초인종"], ["", "설치"]]) == [["옵션", "도어락 / 초인종"], ["", "설치"]]


def test_password_values_in_plain_text_are_masked():
    from mujuthaek_extraction.intake.pdf_reader import PdfPage, _strip_secrets

    page = PdfPage(1, [{"type": "text", "text": "공동현관 비밀번호 : 1234# 이며 비밀번호는 계약 후 안내합니다. 보증금 1,000,000원"}])
    _strip_secrets([page])
    text = page.blocks[0]["text"]
    assert "1234#" not in text and "(가림)" in text and "1,000,000원" in text and "계약 후 안내" in text


def test_very_long_pdf_is_read_up_to_the_limit_and_sent_to_review(monkeypatch):
    from mujuthaek_extraction.intake import adapter, pdf_reader

    monkeypatch.setattr(pdf_reader, "MAX_PAGES", 0)  # 시험에서는 한도를 0쪽으로: 1쪽 PDF도 "너무 긴" PDF
    monkeypatch.setattr(adapter, "MAX_PAGES", 0)
    assert pdf_reader.read_pdf(make_pdf(CELLS)) is None  # 0쪽만 읽으면 글자가 없음
    monkeypatch.setattr(pdf_reader, "MAX_PAGES", 1)
    data = make_pdf(CELLS)
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    intake = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": data}))
    assert "PDF_TOO_LONG" in {code for code, _ in intake.context.forced_review}


def test_layout_grid_with_one_or_two_letter_cells_is_not_a_table():
    # 실측(인천도시공사 10년 분양전환·전북개발공사 분양): 쪽 배치 격자가 열 70~100개 표로 읽혀 문장이 「| 신청 | 자 | 의 당 |」처럼 쪼개짐
    from mujuthaek_extraction.intake.pdf_reader import _shredded

    shredded = [["", "신청", "자", "의 당", "첨자", "확", "정", "후", "무주", "택여", "부", *[""] * 30]]
    assert _shredded(shredded)
    prices = [["주택형", *[f"{n:,}" for n in range(9_000_000, 9_000_000 + 40 * 1000, 1000)]]]  # 열이 많아도 숫자 칸은 길어서 표로 둡니다
    assert not _shredded(prices)
    assert not _shredded([["구분", "1인", "2인"], ["소득", "70%", "60%"]])


def merged_table_pdf() -> bytes:
    """병합 칸이 있는 표: 머리글 2행(「Type」·「Built」 세로 병합, 「Deposit」 가로 병합), 데이터 3행(「39A」 세로 병합)."""
    grid = [  # 칸마다 영역 이름. 같은 이름이 이어지면 병합
        ["type", "dep", "dep", "built"],
        ["type", "total", "rent", "built"],
        ["39a", "d1", "r1", "b1"],
        ["39a", "d2", "r2", "b2"],
        ["46b", "d3", "r3", "b3"],
    ]
    texts = {"type": "Type", "dep": "Deposit", "built": "Built units", "total": "Total", "rent": "Rent", "39a": "39A", "46b": "46B"}
    texts |= {"d1": "9,330", "r1": "82,630", "b1": "25", "d2": "10,100", "r2": "90,000", "b2": "25", "d3": "12,000", "r3": "99,500", "b3": "7"}
    left, top, width, height = 40, 600, 110, 20
    ops = [f"BT /F1 9 Tf 40 {770 - 12 * n} Td ({BODY[n * 80 : n * 80 + 80]}) Tj ET" for n in range(4)]
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            x, y = left + c * width, top - r * height
            if r == 0 or grid[r - 1][c] != grid[r][c]:
                ops.append(f"{x} {y} m {x + width} {y} l S")
            if c == 0 or grid[r][c - 1] != grid[r][c]:
                ops.append(f"{x} {y} m {x} {y - height} l S")
    ops.append(f"{left} {top - rows * height} m {left + cols * width} {top - rows * height} l S")
    ops.append(f"{left + cols * width} {top} m {left + cols * width} {top - rows * height} l S")
    placed = set()
    for r in range(rows):
        for c in range(cols):
            name = grid[r][c]
            if name not in placed:
                placed.add(name)
                ops.append(f"BT /F1 10 Tf {left + c * width + 5} {top - (r + 1) * height + 6} Td ({texts[name]}) Tj ET")
    stream = "\n".join(ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body_bytes in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_merged_headers_become_column_titles_and_rows_get_reading_aids():
    # 구조 방식(2026-10-17): 병합 칸 때문에 AI가 「25」가 건설 호수인지 모집 수인지 칸을 세어 추측하던 것
    document = read_pdf(merged_table_pdf())
    [table] = [b for b in document.pages[0].blocks if b["type"] == "table"]
    assert table["columns"] == ["Type", "Deposit › Total", "Deposit › Rent", "Built units"]
    labeled = document.render(labeled=True)
    assert "  [열 제목] 1. Type | 2. Deposit › Total | 3. Deposit › Rent | 4. Built units" in labeled
    assert "  ↳ 39A — Total 9,330 · Rent 82,630 · Built units 25" in labeled
    assert "  ↳ 39A — Total 10,100 · Rent 90,000" in labeled  # 세로 병합: 행 이름 「39A」는 이어받고, 위 행과 같은 칸의 값(25)은 다시 쓰지 않음
    assert "  ↳ 46B — Total 12,000 · Rent 99,500 · Built units 7" in labeled
    plain = document.render()
    assert "↳" not in plain and "[열 제목]" not in plain  # 이전 방식(legacy) 글자는 그대로
    assert [line for line in labeled.split("\n") if not line.startswith("  ")] == plain.split("\n")  # 표 행·본문은 바뀌지 않음
    stored = document.to_json()["pages"][0]["blocks"][-1]
    assert "filled" not in stored and len(stored["cells"]) == len(stored["rows"])  # 칸 번호로 병합을 복원할 수 있게 남김


def test_table_reading_aid_is_added_only_when_asked():
    # 롤백 스위치(method.py): legacy는 2026-10-17 이전 글자 모양, structured(기본)는 표 행마다 읽기 도움 줄(↳)
    data = merged_table_pdf()
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    reader = InMemorySourceReader(files={"raw/x/notice.pdf": data})
    assert "↳" in build_intake(event, reader, table_labels=True).material.text
    assert "↳" not in build_intake(event, reader).material.text


def test_reading_aid_writes_a_cell_merged_across_columns_once_and_keeps_signed_values():
    from mujuthaek_extraction.intake.pdf_reader import _column_titles, _row_aid

    titles = ["단지", "일반공급", "우선공급", "보증금 증감"]
    # 「합계 13」이 일반·우선 두 열을 덮는 한 칸(칸 번호 같음) → 값 한 번
    assert _row_aid(["합 계", "13", "13", ""], titles, [0, 1, 1, 2]) == "  ↳ 합 계 — 일반공급 + 우선공급 13"
    assert _row_aid(["신정", "6", "2", "(+)5,000"], titles, [3, 4, 5, 6]) == "  ↳ 신정 — 일반공급 6 · 우선공급 2 · 보증금 증감 (+)5,000"
    # 숫자 행이 없는 설명표는 첫 행들을 머리글로 보지 않습니다
    assert _column_titles([["소득", "이자소득", "예금 이자"], ["", "연금소득", "연금"], ["기타 소득", "공적이전", "수당"]]) == []


def test_control_characters_between_letters_become_spaces():
    # 실측(전북개발공사 jbdc-15560): 「■\x00자\x00동\x00차」처럼 글자 사이가 NUL이라 AI가 공백으로 옮긴 인용을 원문에서 못 찾았음
    from mujuthaek_extraction.intake.pdf_reader import _cell, _clean

    assert _clean("■\x00자\x00동\x00차 : 4,542만원") == "■ 자 동 차 : 4,542만원" and _cell("자\x00동\x0b차") == "자 동 차"


def test_single_column_box_tables_render_as_one_row_in_structured_mode():
    # 실측(dcco-24788): 일정 상자 「모집 공고 / ‘26. 4. 10. / 공사 홈페이지」가 줄마다 표 행으로 나와 AI가 칸을 이어 인용하거나 짧은 칸만 인용함
    from mujuthaek_extraction.intake.pdf_reader import PdfDocument, PdfPage

    box = {"type": "table", "id": "1-2", "rows": [["모집 공고"], ["‘26. 4. 10."], ["공사 홈페이지"]], "filled": None, "cells": None, "columns": []}
    document = PdfDocument(1, [PdfPage(1, [box])])
    assert "| 모집 공고 | ‘26. 4. 10. | 공사 홈페이지 |" in document.render(labeled=True)
    assert "| 모집 공고 |\n| ‘26. 4. 10. |" in document.render()  # 이전 방식은 그대로


def test_amounts_stacked_in_one_cell_are_spread_only_when_the_count_matches():
    # 실측(LH 청주지북 3쪽): 잔금 열의 행 구분선이 없어 25행 금액이 첫 칸 하나에 몰리고 아래 칸은 모두 빔
    from mujuthaek_extraction.intake.pdf_reader import _spread_stacked

    rows = [["55B", "1층", "288,620", "212,620 215,690 221,830"], ["", "2층", "291,690", ""], ["", "3층", "297,830", ""]]
    filled = [list(r) for r in rows]
    cells = [[0, 1, 2, 3], [0, 4, 5, 3], [0, 6, 7, 3]]
    _spread_stacked(rows, filled, cells)
    assert [r[3] for r in rows] == ["212,620", "215,690", "221,830"] and [r[3] for r in filled] == ["212,620", "215,690", "221,830"]
    assert [r[3] for r in cells] == [-1, -1, -1]

    for value in ("212,620 215,690", "212,620 215,690 221,830 227,970"):  # 개수가 다르면 어느 행 값인지 몰라 그대로 둡니다
        rows = [["55B", "1층", "288,620", value], ["", "2층", "291,690", ""], ["", "3층", "297,830", ""]]
        _spread_stacked(rows, [list(r) for r in rows], [[0, 1, 2, 3]] * 3)
        assert rows[0][3] == value
    rows = [["55B", "212,620 215,690 221,830"], ["", "9,000"], ["", ""]]  # 아래 칸에 값이 있으면 그대로
    _spread_stacked(rows, [list(r) for r in rows], [[0, 1]] * 3)
    assert rows[0][1] == "212,620 215,690 221,830"


def test_shadowed_title_is_read_once_but_real_double_letters_stay():
    """그림자 글씨(같은 글자를 1.08pt 어긋나게 회색으로 한 번 더): 글자 크기에 비례한 거리로 하나로 읽어요. 실제로 이어 쓴 같은 글자는 그대로."""
    document = read_pdf(make_pdf(CELLS, shadow_title="2026 Rental 11 Book"))
    text = document.render()
    assert "2026 Rental 11 Book" in text
    assert "22002266" not in text and "RReennttaall" not in text
