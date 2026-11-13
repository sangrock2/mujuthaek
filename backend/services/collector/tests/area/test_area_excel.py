import csv
from datetime import datetime

from openpyxl import Workbook

from mujuthaek_collector.area.excel import xlsx_to_csv


def test_subway_excel_becomes_utf8_csv(tmp_path):
    book = Workbook()
    sheet = book.active
    sheet.append(["역번호", "역사명", "역사도로명주소", "데이터기준일자"])
    sheet.append(["D004", "신사", "서울특별시 강남구 강남대로 620-2", datetime(2026, 6, 18)])
    sheet.append([None, None, None, None])  # 빈 줄은 건너뛰어요
    sheet.append(["150", "서울역", "서울특별시 중구\n세종대로 2", datetime(2026, 6, 18)])  # 칸 안 줄바꿈
    source = tmp_path / "subway.xlsx"
    book.save(source)

    target = tmp_path / "subway_station.csv"
    records = xlsx_to_csv(source, target)

    text = target.read_text(encoding="utf-8")
    assert records == 2
    assert len(text.splitlines()) == 4  # 줄 수(머리줄 포함 4)와 레코드 수(2)가 달라요 — 칸 안 줄바꿈 때문
    rows = list(csv.reader(target.open(encoding="utf-8", newline="")))
    assert rows[1] == ["D004", "신사", "서울특별시 강남구 강남대로 620-2", "2026-06-18"]
    assert rows[2][2] == "서울특별시 중구\n세종대로 2"
