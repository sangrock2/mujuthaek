"""HTML 읽기 도우미 (BeautifulSoup + lxml). 기관별 파서는 이 함수들만 써서 HTML을 읽어요."""

import re
import urllib.parse
from collections.abc import Callable, Collection, Iterator
from datetime import date
from html import unescape
from typing import Any

from bs4 import BeautifulSoup, CData, NavigableString, Tag

BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt"]
DROPPED_TAGS = ("script", "style")  # 본문 글자에서 통째로 빼는 태그


def soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup, "lxml")


def text_of(node: Tag | None) -> str:
    """태그 안의 글자를 한 줄로 (공백 정리)."""
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ")).replace("\xa0", " ").strip()


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, unescape(href.strip()))


def query_of(url: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(unescape(url)).query))


def js_args(script: str, func: str) -> list[str] | None:
    """onclick="setView('123')" 같은 스크립트 호출에서 인자를 꺼내요."""
    found = re.search(re.escape(func) + r"\s*\(([^)]*)\)", script or "")
    if not found:
        return None
    return [a.strip().strip("'\"") for a in found.group(1).split(",")]


def table_grid(table: Tag) -> list[list[str]]:
    """표를 격자로. 합쳐진 칸(colspan·rowspan)은 펼쳐서 첫 칸에만 값을 두고 나머지는 빈 칸으로 둬요.
    PDF 표(pdfplumber)와 같은 모양이 돼서 두 줄 머리글·세로 병합 처리를 같은 함수로 할 수 있어요."""
    rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
    return _grid([tr.find_all(["td", "th"], recursive=False) for tr in rows], text_of)


def _grid(rows: list[list[Tag]], value: Callable[[Tag], Any]) -> list[list[Any]]:
    """table_grid의 격자 만들기. rows는 줄마다 칸(td·th) 태그, value는 칸 하나의 값이에요
    (body_text는 안쪽 표를 품은 칸 조각을 넘겨요)."""
    grid: list[list[Any]] = []
    pending: dict[tuple[int, int], str] = {}
    for r, row in enumerate(rows):
        cells: list[Any] = []
        c = 0
        for cell in row:
            while (r, c) in pending:
                cells.append(pending.pop((r, c)))
                c += 1
            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            text = value(cell)
            for k in range(colspan):
                cells.append(text if k == 0 else "")
                for down in range(1, rowspan):
                    pending[(r + down, c + k)] = ""
            c += colspan
        while (r, c) in pending:
            cells.append(pending.pop((r, c)))
            c += 1
        grid.append(cells)
    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def string_kinds(tag: Tag) -> Collection[type]:
    """tag.get_text()가 읽는 글자 종류 (bs4 규칙). 보통 NavigableString·CData이고 <template>·<rt> 같은 태그는 자기 종류만 읽어요.
    주석·스크립트 글자는 어느 쪽에도 없어요."""
    kinds = tag.interesting_string_types
    if kinds is None:
        return (NavigableString, CData)
    return (kinds,) if isinstance(kinds, type) else kinds


def body_text(node: Tag | None, skip: Collection[int] = ()) -> str:
    """본문 HTML을 글자로. 표는 안쪽 표부터 '칸 | 칸' 줄로 바꿔 행·열 관계를 살려요.
    한글 문서에서 붙여 넣은 본문은 몇 글자마다 <span>이 끊겨 있어서, 줄 단위 태그만 줄바꿈하고
    나머지 태그는 공백 없이 이어 붙여요. 주석·스크립트·스타일은 빼요.
    skip은 없는 셈 칠 태그의 id예요 (main_text가 지운 메뉴·하단).

    트리를 고치지 않고 한 번만 훑어요. 예전엔 표를 하나 바꿀 때마다 표를 처음부터 다시 찾고, 태그를 하나씩 떼어 내고 붙여서
    표·<br>·주석이 수천 개이거나 깊게 겹친 화면(외부 HTML, 한글 문서 변환본)에서 수 초~수십 초씩 멈췄어요.
    안쪽 표는 글자로 펼치지 않고 바깥 칸이 그대로 품고 있다가 마지막에 한 번만 펼쳐요."""
    if node is None:
        return ""
    tables: dict[int, list[list[Any]]] = {}
    for table in reversed(node.find_all("table")):  # 앞에서부터 찾은 표를 거꾸로 돌면 안쪽 표가 바깥 표보다 먼저예요
        rows = [[c for c in tr.find_all(["td", "th"], recursive=False) if id(c) not in skip] for tr in _table_rows(table, skip)]
        grid = _grid(rows, lambda cell: _cell_parts(cell, tables, skip))
        tables[id(table)] = [row for row in grid if any(row)]
    text = "".join(_pieces(node, tables, skip)).replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines() if line.strip())


def _table_rows(table: Tag, skip: Collection[int]) -> list[Tag]:
    """표의 줄(tr), 앞에서부터. 안쪽 표의 줄은 빼요 (안쪽 표는 따로 펼쳐요)."""
    rows: list[Tag] = []
    stack = [iter(table.contents)]
    while stack:
        child = next(stack[-1], None)
        if child is None:
            stack.pop()
        elif isinstance(child, Tag) and child.name != "table" and child.name not in DROPPED_TAGS and id(child) not in skip:
            if child.name == "tr":
                rows.append(child)
            stack.append(iter(child.contents))
    return rows


def _cell_parts(cell: Tag, tables: dict[int, list[list[Any]]], skip: Collection[int]) -> tuple[Any, ...]:
    """text_of(칸)과 같은 글자를 조각으로: 공백을 정리한 글자 덩어리와, 안쪽 표(펼친 줄 목록을 그대로)."""
    kinds = string_kinds(cell)
    parts: list[Any] = []
    stack = [iter(cell.contents)]
    while stack:
        child = next(stack[-1], None)
        if child is None:
            stack.pop()
        elif isinstance(child, Tag):
            if child.name in DROPPED_TAGS or id(child) in skip:
                continue
            if child.name != "table":
                stack.append(iter(child.contents))
            elif NavigableString in kinds:  # 안쪽 표 자리에 넣던 글자도 보통 글자예요
                parts.append(tables[id(child)])
        elif type(child) in kinds and (words := " ".join(child.split())):
            parts.append(words)
    return tuple(parts)


def _words(parts: Collection[Any]) -> list[str]:
    """칸 조각을 글자 덩어리 목록으로. 안쪽 표는 '[표] 칸 | 칸 …' 한 줄로 펼쳐요 (칸 글자는 줄바꿈 없이 한 줄이라서요)."""
    out: list[str] = []
    stack: list[Iterator[Any]] = [iter(parts)]
    while stack:
        part = next(stack[-1], None)
        if part is None:
            stack.pop()
        elif isinstance(part, str):
            out.append(part)
        else:
            stack.append(_inline_table(part))
    return out


def _inline_table(rows: list[list[Any]]) -> Iterator[Any]:
    yield "[표]"
    for row in rows:
        for i, cell in enumerate(row):
            if i:
                yield "|"
            yield from cell  # 빈 칸("")은 아무것도 내지 않아요


def _pieces(root: Tag, tables: dict[int, list[list[Any]]], skip: Collection[int]) -> list[str]:
    """root.get_text("")와 같은 순서의 글자 조각. 표 자리에는 '[표]'와 줄들, <br>과 줄 단위 태그 끝에는 줄바꿈을 넣어요."""
    kinds = string_kinds(root)
    added = NavigableString in kinds  # 넣는 글자(표·줄바꿈)는 보통 글자라, root가 보통 글자를 읽을 때만 보여요
    out: list[str] = []
    stack = [(root, iter(root.contents))]
    while stack:
        tag, children = stack[-1]
        child = next(children, None)
        if child is None:
            stack.pop()
            if stack and added and tag.name in BLOCK_TAGS:
                out.append("\n")
        elif isinstance(child, Tag):
            if child.name in DROPPED_TAGS or id(child) in skip:
                continue
            if child.name == "table":
                if added:
                    lines = (" | ".join(" ".join(_words(cell)) for cell in row) for row in tables[id(child)])
                    out.append("\n[표]\n" + "\n".join(lines) + "\n")
            elif child.name == "br":
                if added:
                    out.append("\n")
            else:
                stack.append((child, iter(child.contents)))
        elif type(child) in kinds:
            out.append(child)
    return out


DATE_PATTERNS = [
    re.compile(r"(?P<y>\d{4})\s*[.\-/년]\s*(?P<m>\d{1,2})\s*[.\-/월]\s*(?P<d>\d{1,2})"),
    re.compile(r"(?<!\d)(?P<y>\d{2})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<d>\d{1,2})"),
]


def parse_date(text: str | None) -> date | None:
    """기관마다 다른 날짜 모양(2026-10-08, 2026.10.08, 2026년 10월 8일, 26. 10. 8.)을 date로."""
    for pattern in DATE_PATTERNS:
        found = pattern.search(text or "")
        if found:
            year = int(found.group("y"))
            year = year + 2000 if year < 100 else year
            try:
                return date(year, int(found.group("m")), int(found.group("d")))
            except ValueError:
                return None
    return None
