import time
from datetime import date

import pytest

from mujuthaek_collector.core import html as html_tools
from mujuthaek_collector.core.html import body_text, js_args, parse_date, soup, table_grid


def test_table_grid_expands_merged_cells():
    table = soup("<table><tr><th rowspan=2>주택형</th><th colspan=2>임대조건</th></tr><tr><th>보증금</th><th>월임대료</th></tr></table>").table
    assert table_grid(table) == [["주택형", "임대조건", ""], ["", "보증금", "월임대료"]]


def test_table_grid_does_not_allocate_nonexistent_future_rows(monkeypatch):
    monkeypatch.setattr(html_tools, "MAX_TABLE_CELLS", 2)
    table = soup('<table><tr><td rowspan="99999" colspan="2">안내</td></tr></table>').table
    assert table_grid(table) == [["안내", ""]]


def test_table_grid_rejects_span_before_reading_cell_text():
    table = soup('<table><tr><td colspan="99999">안내</td></tr></table>').table
    with pytest.raises(ValueError, match="column limit"):
        table_grid(table)


def test_body_text_has_document_wide_cell_budget(monkeypatch):
    monkeypatch.setattr(html_tools, "MAX_TABLE_CELLS", 3)
    table = '<table><tr><td colspan="2">안내</td></tr></table>'
    with pytest.raises(ValueError, match="cell budget"):
        body_text(soup("<div>" + table * 2 + "</div>").div)


def test_body_text_keeps_table_rows_and_joins_split_spans():
    html = "<div><p><span>입주</span><span>자격</span></p><table><tr><td>보증금</td><td>1,000</td></tr></table></div>"
    text = body_text(soup(html).div)
    assert "입주자격" in text
    assert "보증금 | 1,000" in text


NOTICE_BODY = """<div class="view">
  <p><span>입주</span><span>자격</span> 안내</p>
  <!-- 예전 문구: 2025년 기준 -->
  <script>var x = 1;</script>
  <table>
    <tr><th rowspan="2">주택형</th><th colspan="2">임대조건</th></tr>
    <tr><th>보증금</th><th>월임대료</th></tr>
    <tr><td>36A</td><td>15,000,000</td><td>120,000<br>(관리비 별도)</td></tr>
    <tr><td>비고</td><td colspan="2"><table><tr><td>소득</td><td>70% 이하</td></tr><tr><td>자산</td><td>3억 3,700만원</td></tr></table></td></tr>
  </table>
  <div>접수 기간: 2026. 10. 19. ~ 10. 27.<br>문의: 1600-1004</div>
</div>"""


def test_body_text_output_is_unchanged_by_the_single_pass_rewrite():
    """2026-11-16 M-6: 트리를 고쳐 가며 표를 하나씩 바꾸던 예전 구현과 글자가 같아야 해요 (예전 구현으로 만든 기대값)."""
    assert body_text(soup(NOTICE_BODY).div) == (
        "입주자격 안내\n"
        "[표]\n"
        "주택형 | 임대조건 |\n"
        "| 보증금 | 월임대료\n"
        "36A | 15,000,000 | 120,000 (관리비 별도)\n"
        "비고 | [표] 소득 | 70% 이하 자산 | 3억 3,700만원 |\n"
        "접수 기간: 2026. 10. 19. ~ 10. 27.\n"
        "문의: 1600-1004"
    )
    node = soup(NOTICE_BODY).div
    before = str(node)
    body_text(node)
    assert str(node) == before  # 받은 트리를 고치지 않아요


def test_body_text_stays_linear_on_hostile_html():
    """2026-11-16 M-6: 외부 HTML·한글 문서 변환본의 표·<br>·주석 수천 개, 깊은 중첩에 몇 초~몇십 초씩 멈췄어요
    (형제 표 2천 개 1.1초, <br> 2만 개 10초, 주석 4만 개 20초, 중첩 <div> 8천 개 2.7초)."""
    pages = {
        "sibling tables": "<div>" + "<table><tr><td>x</td></tr></table>" * 2000 + "</div>",
        "nested tables": "<div>" + "<table><tr><td>x" * 400 + "</td></tr></table>" * 400 + "</div>",
        "breaks": "<div>" + "x<br>" * 20000 + "</div>",
        "comments and scripts": "<div>" + "x<!--c--><script>1</script>" * 20000 + "</div>",
        "nested divs": "<div>" + "<div>x" * 8000 + "</div>" * 8000 + "</div>",
    }
    for name, html in pages.items():
        node = soup(html).div
        started = time.perf_counter()
        text = body_text(node)
        assert time.perf_counter() - started < 1, name
        assert text
    assert body_text(soup(pages["sibling tables"]).div).count("[표]") == 2000
    assert body_text(soup(pages["nested tables"]).div) == "[표]\n" + " [표] ".join(["x"] * 400)


def test_js_args_and_dates():
    assert js_args("HHBbs.DownFile('/umca', 'BBS_4', 'FILE_1', '0')", "HHBbs.DownFile") == ["/umca", "BBS_4", "FILE_1", "0"]
    assert parse_date("2026.10.08") == date(2026, 10, 8)
    assert parse_date("26. 10. 8.") == date(2026, 10, 8)
    assert parse_date("2026년 10월 8일") == date(2026, 10, 8)


def test_extracted_text_drops_nul(monkeypatch):
    """서울·경기·울산 공고문 PDF 글자에 NUL이 섞여 DB 저장이 실패했어요 (2026-10-19)."""
    from mujuthaek_collector.core.documents import text

    monkeypatch.setattr(text, "pdf_text", lambda path: ("공고\x00문 글자", "PDF 텍스트·표"))
    assert text.extract_text(b"%PDF", "pdf") == ("공고문 글자", "PDF 텍스트·표")
