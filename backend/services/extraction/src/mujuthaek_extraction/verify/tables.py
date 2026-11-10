"""값이 놓인 자리(같은 표·같은 열 머리글, 표 위 단위 표시)를 원문에서 찾습니다 (2026-10-21 리뷰 대응).

검증이 「원문에 그 숫자가 있는가」만 보면 단위·대상을 잘못 붙인 값(3,708만원 → 3,708,000원, 「3인 이상 2인 이상」의 3을 자녀 수로)이
통과합니다. 여기서는 근거 위치를 원문에서 찾아, 그 값이 들어 있는 표의 열 머리글과 표 위 단위 표시를 돌려줍니다.
- 표 줄: 「| … | … |」 꼴(PDF 표를 글로 옮긴 모양). 근거 위치가 표 줄 안이면 같은 표(이어진 표 줄)의 위쪽 줄에서 같은 칸 번호의 글자를 머리글로 봅니다.
- 단위 표시: 「(단위: 천원)」「단위 : 만원」 또는 머리글 칸의 「(천원)」. 표 바로 위 3줄과 표 머리글에서만 찾습니다(같은 표의 근거).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

UNIT_WORDS = {"원": 1, "천원": 1_000, "만원": 10_000, "백만원": 1_000_000, "억원": 100_000_000}
# 「(단위: 천원)」「[단위 : ㎡, 천원]」「임대보증금(천원)」
UNIT_MARK = re.compile(r"단위\s*[:：]?\s*\(?\s*(?:[^)\]\n,]{0,8},\s*)?(백\s*만\s*원|천\s*원|만\s*원|원)|\(\s*(백\s*만\s*원|천\s*원|만\s*원|원)\s*\)")
ABOVE_LINES = 3
PLAIN_LOOKBACK = 400  # 표가 아닌 글: 바로 앞 몇 줄 안의 단위 표시만
# 쪽을 넘어 이어진 표 사이의 줄: 쪽 번호(「- 3 -」「--- 4쪽 ---」), 표 번호(「[표 4-1]」), 빈 줄
PAGE_GAP = re.compile(r"\s*(?:-\s*\d+\s*-|---\s*\d+\s*쪽\s*---|\[표\s*[\d-]+\]|\[열\s*제목\].*|주택관리번호.*)?\s*")
PAGE_GAP_LINES = 6
TABLE_FILLER = re.compile(r"\s*(?:---\s*\d+\s*쪽|↳|\[열\s*제목\])")
VALUE_CELL = re.compile(r"[\d,.\s%~∼()-]+\s*(?:원|인|명|세|호|㎡|%)?\s*(?:이상|이하|미만|초과)?")


def unit_of(word: str) -> str:
    return re.sub(r"\s+", "", word)


@dataclass(frozen=True)
class Place:
    row: list[str] | None  # 근거가 표 줄이면 그 줄의 칸들
    headers: list[str]  # 칸 번호별 머리글(표가 아니면 빈 목록)
    units: tuple[str, ...]  # 표 위(표가 아니면 앞 글)의 단위 표시. 가까운 것이 앞
    above: tuple[tuple[str, ...], ...] = ()  # 같은 표의 위쪽 값 줄들(가까운 것이 앞). 위아래로 합친 칸의 값을 찾을 때


def _cells(line: str) -> list[str] | None:
    """표 줄의 칸들. 줄바꿈으로 앞 「|」가 떨어진 줄(「경암부향 | 39 | … |」)도 끝이 「|」이고 칸이 셋 이상이면 표 줄로 봅니다."""
    stripped = line.strip()
    if stripped.count("|") < 2 or not (stripped.startswith("|") or (stripped.endswith("|") and stripped.count("|") >= 3)):
        return None
    return [c.strip() for c in stripped.strip("|").split("|")]


def units_in(text: str) -> list[str]:
    return [unit_of(m.group(1) or m.group(2)) for m in UNIT_MARK.finditer(text)]


def place_of(text: str, start: int) -> Place:
    """원문 text의 start 위치가 놓인 자리."""
    lines = text.split("\n")
    index = text.count("\n", 0, max(0, start))  # start가 놓인 줄 번호
    row = _cells(lines[index]) if lines else None
    if row is None:
        before = text[max(0, start - PLAIN_LOOKBACK) : start]
        return Place(None, [], tuple(reversed(units_in(before))))
    return _table_place(lines, index, row, follow=2)


def _table_place(lines: list[str], index: int, row: list[str], *, follow: int) -> Place:
    top = index
    # 같은 표: 표 줄, 쪽 표시, 표를 글로 옮길 때 끼우는 줄(행 설명 「↳ …」, 「[열 제목] …」)
    while top > 0 and (_cells(lines[top - 1]) is not None or TABLE_FILLER.match(lines[top - 1])):
        top -= 1
    headers = [""] * len(row)
    rows_above = []
    above_own = [False] * len(row)  # 위 머리글 줄에 그 칸의 글자가 있었는지(아래 빈 칸은 위아래 병합)
    for line in lines[top:index]:
        cells = _cells(line)
        # 값 칸(「1인」「70%」「237,000,000」)이 있는 줄은 값 줄이라 머리글로 쓰지 않습니다
        if cells is not None and len(cells) == len(row) and any(VALUE_CELL.fullmatch(c) for c in cells if c):
            rows_above.append(tuple(cells))
            continue
        if cells is None or len(cells) != len(row):
            continue
        for i, cell in enumerate(_spanned(cells, above_own)):
            if re.search(r"[가-힣]", cell):
                headers[i] = f"{headers[i]} {cell}".strip()
        above_own = [own or bool(cell) for own, cell in zip(above_own, cells, strict=True)]
    above = "\n".join(lines[max(0, top - ABOVE_LINES) : top])
    # 표 전체의 단위는 표 위 표시만. 열 머리글의 단위(「임대보증금(천원)」)는 그 열에만 씁니다(claims._unit_confirmed)
    units = tuple(reversed(units_in(above)))
    if follow > 0 and (not units or not any(headers)):
        # 쪽을 넘어 이어진 표(실측 광주선운2 분양가 표: 「[단위 : 천원]」은 앞 쪽 표 위에만 있음). 쪽 표시·표 번호만 사이에 두고
        # 바로 앞에 머리글이 같은 표가 있으면 그 표의 단위를 씁니다
        gap = top
        while gap > 0 and top - gap < PAGE_GAP_LINES and PAGE_GAP.fullmatch(lines[gap - 1]):
            gap -= 1
        if gap < top and gap > 0:
            previous = _cells(lines[gap - 1])
            back = gap - 1
            while previous is None and back > 0 and TABLE_FILLER.match(lines[back]):
                back -= 1
                previous = _cells(lines[back])
            if previous is not None and len(previous) == len(row):
                earlier = _table_place(lines, back, previous, follow=follow - 1)
                if not any(headers):
                    # 머리글 없이 빈 줄·쪽 표시 뒤에 이어진 행들(실측 광주선운2 55A-1 블록): 칸 수가 같은 바로 앞 표의 이어짐
                    headers, units = earlier.headers, units or earlier.units
                elif earlier.headers == headers and not units:
                    units = earlier.units
    return Place(row, headers, units, tuple(reversed(rows_above)))


def _spanned(cells: list[str], above_own: list[bool]) -> list[str]:
    """병합된 머리글(「①일반형 임대보증금(천원) |  |  |」): 빈 칸은 왼쪽 머리글이 옆으로 걸친 칸으로 봅니다.
    위 머리글 줄에 그 칸의 글자가 있으면 위아래로 합친 칸이라 왼쪽 것을 채우지 않습니다(실측: 「월 임대료 (원)」이 옆 「보증금 (천원)」 열에 섞임)."""
    out, last = [], ""
    for cell, own in zip(cells, above_own, strict=True):
        if cell:
            last = cell
            out.append(cell)
        else:
            out.append("" if own else last)
    return out


def columns_of(place: Place, token: str) -> list[int]:
    """표 줄에서 token과 같은 칸 번호들(같은 칸이 없으면 token이 든 칸들). 이 줄에 없으면 위아래로 합친 칸:
    이 줄에서 빈 칸인데 같은 표 위쪽 줄의 같은 칸이 token인 곳(가장 가까운 줄)."""
    if place.row is None:
        return []
    plain = re.sub(r"\s+", "", token)
    if not plain:
        return []
    exact = [i for i, cell in enumerate(place.row) if plain == re.sub(r"\s+", "", cell)]
    if exact:
        return exact
    found = [i for i, cell in enumerate(place.row) if plain in re.sub(r"\s+", "", cell)]
    if found:
        return found
    for cells in place.above:
        merged = [i for i, cell in enumerate(cells) if i < len(place.row) and not place.row[i] and plain == re.sub(r"\s+", "", cell)]
        if merged:
            return merged
    return []


def column_of(place: Place, token: str) -> int | None:
    """표 줄에서 token이 든 칸 번호(없거나 여러 칸이면 None)."""
    if place.row is None:
        return None
    plain = re.sub(r"\s+", "", token)
    exact = [i for i, cell in enumerate(place.row) if plain and plain == re.sub(r"\s+", "", cell)]
    if len(exact) == 1:
        return exact[0]
    found = [i for i, cell in enumerate(place.row) if plain and plain in re.sub(r"\s+", "", cell)]
    return found[0] if len(found) == 1 else None
