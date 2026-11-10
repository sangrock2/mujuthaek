"""HTML 읽기 도우미 (BeautifulSoup + lxml). 기관별 파서는 이 함수들만 써서 HTML을 읽어요."""

import copy
import re
import urllib.parse
from datetime import date
from html import unescape

from bs4 import BeautifulSoup, Comment, Tag

BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt"]


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
    grid: list[list[str]] = []
    pending: dict[tuple[int, int], str] = {}
    rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
    for r, tr in enumerate(rows):
        cells: list[str] = []
        c = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            while (r, c) in pending:
                cells.append(pending.pop((r, c)))
                c += 1
            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            value = text_of(cell)
            for k in range(colspan):
                cells.append(value if k == 0 else "")
                for down in range(1, rowspan):
                    pending[(r + down, c + k)] = ""
            c += colspan
        while (r, c) in pending:
            cells.append(pending.pop((r, c)))
            c += 1
        grid.append(cells)
    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def body_text(node: Tag | None) -> str:
    """본문 HTML을 글자로. 표는 안쪽 표부터 '칸 | 칸' 줄로 바꿔 행·열 관계를 살려요.
    한글 문서에서 붙여 넣은 본문은 몇 글자마다 <span>이 끊겨 있어서, 줄 단위 태그만 줄바꿈하고
    나머지 태그는 공백 없이 이어 붙여요."""
    if node is None:
        return ""
    node = copy.copy(node)
    for comment in node.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()  # 주석 처리된 예전 문구는 빼기
    for tag in node.find_all(["script", "style"]):
        tag.decompose()
    while True:
        leaf = next((t for t in node.find_all("table") if t.find("table") is None), None)
        if leaf is None:
            break
        rows = [" | ".join(row) for row in table_grid(leaf) if any(row)]
        leaf.replace_with("\n[표]\n" + "\n".join(rows) + "\n")
    for br in node.find_all("br"):
        br.replace_with("\n")
    for tag in node.find_all(BLOCK_TAGS):
        tag.append("\n")
    text = node.get_text("").replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines() if line.strip())


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
