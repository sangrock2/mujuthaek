"""V2 문서 모델: 공고 원문을 에이전트가 id로 가리키는 조각(줄·표·행·칸)으로 나눕니다.

원문은 V1 입력 해석이 만든 글자(material.text)입니다. 쪽 표시(「--- 3쪽 ---」), 표 표시(「[표 4-1]」), 열 제목 줄, 표 행(「| a | b |」),
첨부 엑셀·그림 판독 묶음(「=== … ===」)을 읽어 id를 붙입니다. 담당들은 원문 전체를 id와 함께(render) 첫 메시지로 받고,
값의 근거를 id로 남깁니다. 인용 글은 코드가 id로 원문에서 꺼내므로 원문과 글자가 늘 같습니다(검증기의 원문 대조가 그대로 통과).

2026-11-06 두 번째 실제 실행: 차례(제목 목록)만 주고 도구로 골라 읽게 했더니 담당마다 읽는 차례가 9번 안팎 들고(차례마다 지시·도구 정의
2~3만 토큰을 다시 보냄) 덜 읽어 V1보다 항목이 적었음. 그래서 원문 전체를 같은 앞부분으로 주고 프롬프트 캐시로 다시 읽음.

id 모양
  줄  p3.12        3쪽 본문 12번째 줄(1부터). 둘째 첨부 PDF부터는 d2.p3.12, 엑셀·그림 판독 묶음은 x1.4 · g1.4
  표  t4-1         V1 표 번호 그대로(둘째 PDF부터 d2.t4-1). 번호 없는 표(엑셀 시트·판독 표)는 <묶음>.t1
  행  t4-1.r3      표의 행(0부터)
  칸  t4-1.r3.c2   그 행의 칸(0부터)
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from rapidfuzz import fuzz
from rapidfuzz.distance import LCSseq

from mujuthaek_extraction.assemble.quotes import NormalizedText, find_scattered, normalize, strip_markers
from mujuthaek_extraction.image_reading import image_targets
from mujuthaek_extraction.intake.model import ExtractionMaterial

PAGE = re.compile(r"^--- (\d+)쪽(?: 왼쪽| 오른쪽)? ---$")
TABLE = re.compile(r"^\[표 ([^\]]+)\]$")
SHEET = re.compile(r"^\[엑셀 시트 (.+)\]$")
BLOCK = re.compile(r"^=== (.+) ===$")
TITLES = "  [열 제목] "  # V1 구조 방식이 표 위에 붙이는 열 제목 줄
AID = "  ↳ "  # V1이 표 행 아래 붙이는 읽기 도움 줄(원문이 아님)
TITLE_ITEM = re.compile(r"^\d+\. ?(.*)$")
FUZZY_MIN = 80  # 찾기에서 글자가 똑같은 곳이 없을 때 비슷한 줄로 볼 최소 유사도(0~100)


@dataclass(frozen=True)
class Line:
    id: str
    text: str


@dataclass(frozen=True)
class Table:
    id: str
    area: str  # 표가 있는 쪽·묶음(p4 · d2.p3 · x1 · g1)
    lines: tuple[str, ...]  # 원문의 표 행 줄 그대로(「| a | b |」)
    columns: tuple[str, ...] = ()  # V1이 복원한 열 제목(없으면 빈 값)
    caption: str = ""  # 엑셀 시트 이름 등

    @property
    def rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(_cells(line) for line in self.lines)


@dataclass(frozen=True)
class DocumentModel:
    items: tuple[Line | Table, ...]  # 원문 순서(본문 줄과 표가 섞임)
    picture_pages: tuple[str, ...] = ()  # 글자 없는 그림 쪽(p8 · d2.p1)
    source_id: str = "text"  # 원문 글자의 문서 ID(V1 material.text_document_id). 인용의 documentId
    blocks: tuple[tuple[str, str], ...] = ()  # 묶음 id → 원래 이름(x1 → 「첨부 엑셀 목록.xlsx」, g1 → 「그림 판독 3쪽」)
    _by_id: dict[str, Line | Table] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {item.id: item for item in self.items})

    @property
    def lines(self) -> tuple[Line, ...]:
        return tuple(item for item in self.items if isinstance(item, Line))

    @property
    def tables(self) -> tuple[Table, ...]:
        return tuple(item for item in self.items if isinstance(item, Table))

    def text(self, ref: str) -> str:
        """id → 원문 글자(줄·표 전체·행·칸). 없는 id면 KeyError."""
        item = self._by_id.get(ref)
        if isinstance(item, Line):
            return item.text
        if isinstance(item, Table):
            return "\n".join(item.lines)
        table_id, row, column = _split_cell_ref(ref)
        table = self._by_id.get(table_id)
        if not isinstance(table, Table) or row >= len(table.lines):
            raise KeyError(ref)
        if column is None:
            return table.lines[row]
        cells = table.rows[row]
        if column >= len(cells):
            raise KeyError(ref)
        return cells[column]

    def exists(self, ref: str) -> bool:
        try:
            self.text(ref)
        except KeyError:
            return False
        return True

    def contains(self, text: str) -> bool:
        """원문 어딘가에 그 글이 그대로 있는지(공백·표 칸 구분자는 무시, V1 검증기의 originalText 대조와 같은 정규화)."""
        return bool(normalize(text)) and normalize(text) in self._normalized

    def verbatim(self, text: str) -> bool:
        """원문 문장 칸(originalText)으로 받을 글인지: V1 검증기의 대조(ORIGINAL_TEXT_NOT_FOUND)와 같은 기준입니다. 표시 글자(쪽·표 번호)를 빼고
        이어진 글로 있거나, 순서도·칸 없는 표처럼 글자 순서가 뒤섞인 곳이면 낱말이 가까이 모여 있습니다."""
        return self.contains(strip_markers(text)) or bool(find_scattered(self._index, text))

    def occurrences(self, text: str) -> int:
        """같은 정규화로 원문에 그 글이 몇 곳 있는지(V1 결합기가 인용 글로 위치를 찾을 때 한 곳이어야 위치가 정해짐)."""
        needle = normalize(text)
        return self._normalized.count(needle) if needle else 0

    @cached_property
    def _normalized(self) -> str:
        return normalize(self._joined)

    @cached_property
    def _index(self) -> NormalizedText:
        return NormalizedText(self._joined)

    @cached_property
    def _joined(self) -> str:
        return "\n".join(item.text if isinstance(item, Line) else "\n".join(item.lines) for item in self.items)

    def render(self) -> str:
        """담당 첫 메시지에 넣는 원문 전체. 줄은 「p3.12 글」, 표는 머리(「[표 t4-1] 열: c0=구분 | c1=보증금」) 아래 행마다
        「t4-1.r0 c0=기준 | c1=14,202,000」. 빈 칸(합쳐진 칸)은 적지 않아 근거로 가리키지 않게 합니다(2026-11-06: 빈 칸 근거가 빈 인용이 되어
        결합기가 담당 응답 전체를 버림). 쪽·묶음이 바뀌면 「[p3]」·「[g1 그림 판독 3쪽]」을 붙입니다."""
        names = dict(self.blocks)
        out: list[str] = []
        area = None
        for item in self.items:
            here = item.area if isinstance(item, Table) else item.id.rsplit(".", 1)[0]
            if here != area:
                area = here
                out.append(f"[{here} {names[here]}]" if here in names else f"[{here}]")
            if isinstance(item, Line):
                out.append(f"{item.id} {item.text}")
                continue
            head = f"[표 {item.id}]" + (f" {item.caption}" if item.caption else "")
            if any(item.columns):
                head += " 열: " + " | ".join(f"c{c}={title}" for c, title in enumerate(item.columns) if title)
            out.append(head)
            for r, cells in enumerate(item.rows):
                out.append(" ".join([f"{item.id}.r{r}", " | ".join(f"c{c}={value}" for c, value in enumerate(cells) if value)]).rstrip())
        if self.picture_pages:
            out.append(f"[글자 없는 그림 쪽: {', '.join(self.picture_pages)}. 판독한 글은 g 묶음에 있습니다]")
        return "\n".join(out)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """글자가 똑같이 든 줄·표 행(칸 하나에 들면 칸 id도), 없으면 비슷한 줄(유사도 FUZZY_MIN 이상)."""
        needle = _squash(query)
        if not needle:
            return []
        hits: list[dict[str, Any]] = []
        for ref, text, cells in self._searchable():
            if needle in _squash(text):
                hit: dict[str, Any] = {"id": ref, "text": text}
                cell = next((c for c, value in enumerate(cells) if needle in _squash(value)), None)
                if cell is not None:
                    hit["cell"] = f"{ref}.c{cell}"
                hits.append(hit)
                if len(hits) >= limit:
                    return hits
        if hits:
            return hits
        scored = [(fuzz.partial_ratio(needle, _squash(text)), ref, text) for ref, text, _ in self._searchable()]
        return [{"id": ref, "text": text, "similarity": round(score)} for score, ref, text in sorted(scored, reverse=True)[:limit] if score >= FUZZY_MIN]

    def closest(self, text: str) -> dict[str, str] | None:
        """원문에 그대로 없는 글과 가장 비슷한 줄·표 행: 그 글의 글자가 순서대로 가장 많이 든 줄, 같으면 남는 글자가 적은 줄(같은 줄이 여럿이면 앞의 것).
        원문 줄의 가운데를 빼고 적은 글은 글자 유사도·낱말 겹침으로는 못 찾기도 함(2026-11-06: 띄어쓰기가 붙은 PDF 줄
        「※ 1인가구는20%p, 2인가구는10%p가산적용한금액」 → 「1인가구는 20%p 가산적용한 금액」). 글자의 80% 이상이 든 줄이 없으면 None."""
        needle = normalize(text)
        best, found = (0.0, 0.0), None
        for ref, line, _ in self._searchable() if needle else ():
            hay = normalize(line)
            common = LCSseq.similarity(needle, hay)
            score = (common / len(needle), common / max(len(hay), 1))
            if score > best:
                best, found = score, {"id": ref, "text": line}
        return found if best[0] >= FUZZY_MIN / 100 else None

    def _searchable(self):
        for item in self.items:
            if isinstance(item, Line):
                yield item.id, item.text, ()
            else:
                for r, line in enumerate(item.lines):
                    yield f"{item.id}.r{r}", line, item.rows[r]


def build(material: ExtractionMaterial) -> DocumentModel:
    """V1 입력 해석 결과 → 문서 모델. 그림 쪽은 첨부 PDF에서 찾습니다(V1 그림 판독과 같은 기준)."""
    document = parse(material.text, material.text_document_id)
    pdfs = [file.document_id for file in material.files if file.file_type == "pdf"]
    pages = []
    for document_id, _, _, page in image_targets(material):
        order = pdfs.index(document_id) + 1 if document_id in pdfs else 1
        pages.append(f"p{page}" if order == 1 else f"d{order}.p{page}")
    return dataclasses.replace(document, picture_pages=tuple(pages))


def parse(text: str, source_id: str = "text") -> DocumentModel:
    items: list[Line | Table] = []
    area, document, last_page = "p1", 1, 0
    counters: dict[str, int] = {}
    blocks: dict[str, int] = {}
    names: list[tuple[str, str]] = []
    table: dict[str, Any] | None = None

    def close() -> None:
        nonlocal table
        if table is not None and table["lines"]:
            items.append(Table(table["id"], table["area"], tuple(table["lines"]), tuple(table["columns"]), table["caption"]))
        table = None

    def unnamed(caption: str = "") -> dict[str, Any]:
        counters[f"{area}.t"] = counters.get(f"{area}.t", 0) + 1
        return {"id": f"{area}.t{counters[f'{area}.t']}", "area": area, "lines": [], "columns": [], "caption": caption}

    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not line.strip():
            close()
            continue
        if page := PAGE.match(line):
            close()
            number = int(page.group(1))
            if number < last_page:  # 쪽 번호가 줄면 다음 첨부 PDF
                document += 1
            last_page = number
            area = f"p{number}" if document == 1 else f"d{document}.p{number}"
            continue
        if block := BLOCK.match(line):
            close()
            kind = "x" if "엑셀" in block.group(1) else "g" if "그림 판독" in block.group(1) else "b"
            blocks[kind] = blocks.get(kind, 0) + 1
            area = f"{kind}{blocks[kind]}"
            names.append((area, block.group(1)))
            continue
        if marker := TABLE.match(line):
            close()
            prefix = "" if document == 1 else f"d{document}."
            table = {"id": f"{prefix}t{marker.group(1)}", "area": area, "lines": [], "columns": [], "caption": ""}
            continue
        if sheet := SHEET.match(line):
            close()
            table = unnamed(sheet.group(1))
            continue
        if line.startswith(TITLES):
            if table is not None:
                table["columns"] = [_title(item) for item in line[len(TITLES) :].split(" | ")]
            continue
        if line.startswith(AID):
            continue
        if _is_row(line):
            if table is None:
                table = unnamed()
            table["lines"].append(line)
            continue
        close()
        counters[area] = counters.get(area, 0) + 1
        items.append(Line(f"{area}.{counters[area]}", line))
    close()
    return DocumentModel(tuple(items), source_id=source_id, blocks=tuple(names))


def _is_row(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 2 and stripped.startswith("|") and stripped.endswith("|")


def _cells(line: str) -> tuple[str, ...]:
    inner = line.strip()[1:-1]
    return tuple(cell.strip() for cell in inner.split("|"))


def _title(item: str) -> str:
    match = TITLE_ITEM.match(item.strip())
    title = match.group(1) if match else item.strip()
    return "" if title == "-" else title


def _split_cell_ref(ref: str) -> tuple[str, int, int | None]:
    match = re.fullmatch(r"(.+)\.r(\d+)(?:\.c(\d+))?", ref)
    if not match:
        raise KeyError(ref)
    return match.group(1), int(match.group(2)), int(match.group(3)) if match.group(3) is not None else None


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)
