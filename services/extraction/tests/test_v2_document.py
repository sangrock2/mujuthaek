"""V2 문서 모델: 원문 글자 → 줄·표·행·칸 id, id → 원문 글자(인용이 원문과 늘 같음), 담당 첫 메시지에 넣는 원문 전체(id 포함)."""

import pytest
from events import raw_event
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from test_pdf_reader import CELLS, attachment, make_pdf

from mujuthaek_extraction.intake import InMemorySourceReader, build_intake
from mujuthaek_extraction.v2.document import build, parse

TEXT = "\n".join(
    [
        "공고 제목 줄",
        "--- 1쪽 ---",
        "1. 신청자격",
        "■ 소득 : 150% 이하",
        "[표 1-1]",
        "  [열 제목] 1. 구분 | 2. 보증금 | 3. -",
        "| 기준 | 14,202,000 | 105,200 |",
        "  ↳ 기준 — 보증금 14,202,000",
        "| 110%이하 | 15,622,000 |  |",
        "다음 본문",
        "--- 2쪽 ---",
        "2. 일정",
        "--- 1쪽 ---",
        "둘째 문서 줄",
        "[표 1-1]",
        "| a | b |",
        "=== 첨부 엑셀 목록.xlsx ===",
        "[엑셀 시트 공급]",
        "| 동 | 호 |",
        "| 101 | 1001 |",
        "=== 그림 판독 3쪽 ===",
        "| 1인 | 3,432,027 |",
        "판독 끝",
    ]
)


def test_ids_follow_pages_tables_rows_and_cells_and_point_back_to_the_exact_source():
    doc = parse(TEXT)
    assert [line.id for line in doc.lines] == ["p1.1", "p1.2", "p1.3", "p1.4", "p2.1", "d2.p1.1", "g1.1"]
    assert [table.id for table in doc.tables] == ["t1-1", "d2.t1-1", "x1.t1", "g1.t1"]
    first = doc.tables[0]
    assert first.columns == ("구분", "보증금", "") and len(first.lines) == 2  # 읽기 도움 줄(↳)은 원문이 아님
    assert doc.text("p1.3") == "■ 소득 : 150% 이하"
    assert doc.text("t1-1.r0") == "| 기준 | 14,202,000 | 105,200 |"
    assert doc.text("t1-1.r1.c1") == "15,622,000" and doc.text("t1-1.r1.c2") == ""
    assert doc.tables[2].caption == "공급" and doc.text("x1.t1.r1.c1") == "1001"
    # 인용 글은 id로 꺼내므로 원문에 그대로 있음(검증기의 원문 대조가 통과)
    pieces = [line.text for line in doc.lines] + [row for table in doc.tables for row in table.lines]
    pieces += [cell for table in doc.tables for row in table.rows for cell in row if cell]
    assert all(piece in TEXT for piece in pieces)
    with pytest.raises(KeyError):
        doc.text("t1-1.r9")
    assert not doc.exists("p9.1") and doc.exists("g1.t1.r0.c1")


def test_the_whole_source_is_rendered_with_ids_and_empty_cells_are_left_out():
    doc = parse(TEXT)
    text = doc.render()
    assert text.splitlines()[:6] == [
        "[p1]",
        "p1.1 공고 제목 줄",
        "p1.2 1. 신청자격",
        "p1.3 ■ 소득 : 150% 이하",
        "[표 t1-1] 열: c0=구분 | c1=보증금",
        "t1-1.r0 c0=기준 | c1=14,202,000 | c2=105,200",
    ]
    lines = text.splitlines()
    assert "t1-1.r1 c0=110%이하 | c1=15,622,000" in lines  # 빈 칸(c2)은 적지 않아 근거로 가리키지 않음
    assert lines[lines.index("[x1 첨부 엑셀 목록.xlsx]") + 1] == "[표 x1.t1] 공급" and "[g1 그림 판독 3쪽]" in lines
    assert lines[lines.index("[d2.p1]") + 1] == "d2.p1.1 둘째 문서 줄"
    assert "↳" not in text and "[열 제목]" not in text  # 프로그램이 붙인 읽기 도움 줄은 원문이 아님
    # 원문 문장 대조는 V1 검증기와 같은 정규화(공백·표 칸 구분자 무시)
    assert doc.contains("■ 소득: 150%이하") and doc.contains("기준 14,202,000") and not doc.contains("없는 문장")
    hit = doc.search("14,202,000")[0]
    assert hit["id"] == "t1-1.r0" and hit["cell"] == "t1-1.r0.c1"
    assert doc.search("신청 자격")[0]["id"] == "p1.2"  # 공백은 무시
    near = doc.search("소득 150%이하")  # 똑같은 글자가 없으면 비슷한 줄
    assert near[0]["id"] == "p1.3" and near[0]["similarity"] >= 80


def test_places_of_a_quote_are_counted_like_the_assembler_including_reading_aid_lines():
    doc = parse(TEXT)
    assert doc.occurrences("14,202,000") == 2  # 표 행 + V1 읽기 도움 줄(↳ 기준 — 보증금 14,202,000): 결합기는 두 곳을 찾음
    assert doc.occurrences("| 기준 | 14,202,000 | 105,200 |") == 1 and doc.occurrences("없는 글") == 0


def test_original_text_is_checked_like_the_v1_verifier_and_a_cut_text_points_to_its_line():
    doc = parse(TEXT)
    assert doc.verbatim("■ 소득 : 150%  이하") and doc.verbatim("[표 1-1] | 기준 | 14,202,000 |")  # 공백·표 번호 표시는 무시
    assert not doc.verbatim("■ 소득 : 이하")  # 가운데를 뺀 글은 원문 그대로가 아님
    assert doc.closest("■ 소득 : 이하") == {"id": "p1.3", "text": "■ 소득 : 150% 이하"} and doc.closest("전혀 다른 글") is None


def test_document_from_a_real_pdf_keeps_v1_table_numbers():
    data = make_pdf(CELLS)
    event = raw_event()
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    material = build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": data})).material
    doc = build(material)
    table = next(t for t in doc.tables if t.id == "t1-1")
    assert all(doc.text(f"t1-1.r{r}") in material.text for r in range(len(table.lines)))
    assert doc.picture_pages == ()


def test_picture_pages_are_numbered_by_the_pdfs_whose_text_is_in_the_source(monkeypatch):
    # 2026-11-10 재검토: 글자를 못 읽은 PDF(스캔본)가 앞에 있으면 첨부 PDF 전체로 번호를 세어, 안내의 그림 쪽이 다른 문서(p1)나 없는 id(d2.p1)를 가리켰음
    import mujuthaek_extraction.image_reading as image_reading

    scan, readable = make_pdf([["a"]], body="x"), make_pdf(CELLS)  # 글자가 적은 PDF는 읽지 못한 것으로 빠짐
    monkeypatch.setattr(image_reading, "image_pages", lambda data: {scan: [(1, None)], readable: [(1, None)]}.get(data, []))
    files = [("scan.pdf", scan), ("notice.pdf", readable)]
    event = raw_event()
    event["payload"]["files"] = [attachment(name, data) for name, data in files]
    material = build_intake(event, InMemorySourceReader(files={f"raw/x/{name}": data for name, data in files})).material
    assert build(material).picture_pages == ("p1",)  # 원문의 첫 PDF(notice.pdf) 1쪽. 스캔본 쪽은 근거로 쓸 수 없어 뺌


class ToolCallingFake(GenericFakeChatModel):
    """녹화한 답(도구 호출 포함)을 차례로 내는 가짜 모델. create_agent가 도구를 묶을 수 있게 bind_tools는 그대로 돌려줍니다."""

    def bind_tools(self, tools, **kwargs):
        return self


def test_a_one_page_pdf_followed_by_another_pdf_gives_the_second_its_own_ids():
    # 2026-11-10 코드 검토: 쪽 번호가 줄 때만 다음 첨부로 봐서, 1쪽짜리 정정공고 뒤 공고문의 [표 1-1]이 같은 id(t1-1)가 되어
    # 앞 표 인용이 뒤 표 글자로 풀렸음
    text = "\n".join(
        [
            "=== 첨부 정정공고.pdf ===",
            "--- 1쪽 ---",
            "[표 1-1]",
            "| 청년 | 100% |",
            "=== 첨부 공고문.pdf ===",
            "--- 1쪽 ---",
            "[표 1-1]",
            "| 보증금 | 2억 5,400만원 |",
        ]
    )
    doc = parse(text)
    assert [table.id for table in doc.tables] == ["t1-1", "d2.t1-1"]
