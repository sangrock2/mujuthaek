from datetime import date

from mujuthaek_collector.core.html import body_text, js_args, parse_date, soup, table_grid


def test_table_grid_expands_merged_cells():
    table = soup("<table><tr><th rowspan=2>주택형</th><th colspan=2>임대조건</th></tr><tr><th>보증금</th><th>월임대료</th></tr></table>").table
    assert table_grid(table) == [["주택형", "임대조건", ""], ["", "보증금", "월임대료"]]


def test_body_text_keeps_table_rows_and_joins_split_spans():
    html = "<div><p><span>입주</span><span>자격</span></p><table><tr><td>보증금</td><td>1,000</td></tr></table></div>"
    text = body_text(soup(html).div)
    assert "입주자격" in text
    assert "보증금 | 1,000" in text


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
