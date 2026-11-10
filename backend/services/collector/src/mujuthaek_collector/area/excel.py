"""지하철역 원천(철도산업정보센터 "전체_도시철도역사정보")은 엑셀이라 UTF-8 CSV로 바꿔서 올려요.

- 값이 하나도 없는 줄은 건너뛰어요
- 날짜 칸은 YYYY-MM-DD 글자로
- 칸 안의 줄바꿈은 따옴표로 감싸 그대로 둬요. 그래서 파일 줄 수가 레코드 수보다 많을 수 있어요
"""

import csv
from pathlib import Path


def xlsx_to_csv(source: Path, target: Path) -> int:
    """첫 시트를 CSV로 쓰고, 머리줄을 뺀 레코드 수를 돌려줘요."""
    from openpyxl import load_workbook

    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        rows = 0
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in workbook.active.iter_rows(values_only=True):
                if row is None or all(v is None for v in row):
                    continue
                writer.writerow([_cell(v) for v in row])
                rows += 1
        return max(rows - 1, 0)
    finally:
        workbook.close()


def _cell(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)
