"""공고문 원본에서 글자를 뽑아요. 표는 행·열을 '칸 | 칸'으로 살려서 AI 추출 단계가 표를 읽을 수 있게 해요."""

import re
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from mujuthaek_collector.core.documents.hwp import hwp_to_html, hwp_to_plain_text
from mujuthaek_collector.core.html import body_text, soup
from mujuthaek_platform.archives import check_zip_path

MIN_CHARS = 200  # 이보다 글자가 적으면 읽기 실패로 봐요 (스캔본 PDF 등)
MAX_HWPX_BYTES = 50 * 1024 * 1024  # 다운로드 크기와 별도로 압축을 푼 XML의 합을 제한해요
MAX_HWPX_ENTRIES = 2048
# 한글 문서가 쓰는 압축만 받아요. 파이썬 zipfile은 BZIP2·LZMA 항목을 크기 상한 없이 통째로 푼 뒤 zip에 적힌 크기로 잘라서,
# 크기를 작게 적은 588바이트 파일 하나로 수백 MB를 썼어요(2026-11-16 보안 감사 H-6)
SAFE_COMPRESSION = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
READ_CHUNK = 64 * 1024
MAX_XML_NODES = 500_000
MAX_XML_DEPTH = 128


class _HwpxText:
    """XML 콜백으로 문서를 한 번만 읽어요. DTD·엔티티 선언과 과도한 노드/중첩은 거절합니다."""

    def __init__(self, node_limit: int):
        self.node_limit = node_limit
        self.nodes = self.depth = 0
        self.parts: list[list[str]] = [[]]
        self.rows: list[int] = []

    def start(self, tag: str, attrs: dict[str, str]) -> None:
        self.nodes += 1
        self.depth += 1
        if self.nodes > self.node_limit or self.depth > MAX_XML_DEPTH:
            raise ValueError("HWPX XML structure limit exceeded")
        name = tag.rsplit("}", 1)[-1]
        if name == "tbl":
            self.parts[-1].append("\n[표]\n")
        elif name == "tr":
            self.rows.append(0)
        elif name == "tc":
            if self.rows:
                if self.rows[-1]:
                    self.parts[-1].append(" | ")
                self.rows[-1] += 1
            self.parts.append([])

    def end(self, tag: str) -> None:
        name = tag.rsplit("}", 1)[-1]
        if name == "tc":
            cell = self.parts.pop()
            self.parts[-1].append(" ".join("".join(cell).split()))
        elif name == "tr":
            self.rows.pop()
            self.parts[-1].append("\n")
        elif name in {"tbl", "p"}:
            self.parts[-1].append("\n")
        self.depth -= 1

    def data(self, value: str) -> None:
        self.parts[-1].append(value)

    def doctype(self, *args) -> None:
        raise ValueError("HWPX DTD is not allowed")

    def close(self) -> str:
        return "".join(self.parts[0])


def _hwpx_section(data: bytes, remaining_nodes: int) -> tuple[str, int]:
    xml = data.decode("utf-8", errors="replace").lstrip("\ufeff")
    if xml.startswith("<?xml"):
        declaration, separator, xml = xml.partition("?>")
        if not separator or len(declaration) > 256:
            raise ValueError("Invalid HWPX XML declaration")
    # 실제 HWPX는 namespace를 선언합니다. 예전의 namespace 없는 hp:p 조각도 같은 XML 처리로 읽어요.
    target = _HwpxText(remaining_nodes)
    parser = ElementTree.XMLParser(target=target)
    parser.feed('<section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">')
    parser.feed(xml)
    parser.feed("</section>")
    return parser.close(), target.nodes


def _read_member(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, limit: int) -> bytes:
    """zip 항목 하나를 조금씩 풀며 실제로 나온 바이트를 세요. zip에 적힌 크기는 공격자가 고칠 수 있어서 믿지 않아요."""
    if entry.compress_type not in SAFE_COMPRESSION:
        raise ValueError("HWPX member uses an unsupported compression method")
    chunks, size = [], 0
    with archive.open(entry) as source:
        while chunk := source.read(READ_CHUNK):
            size += len(chunk)
            if size > limit:
                raise ValueError("HWPX decompression limit exceeded")
            chunks.append(chunk)
    return b"".join(chunks)


def _table_lines(rows: list[list[str | None]]) -> str:
    return "\n".join(" | ".join(re.sub(r"\s+", " ", cell or "").strip() for cell in row) for row in rows if any(row))


def pdf_text(path: Path) -> tuple[str | None, str]:
    import pdfplumber

    parts = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            parts.append(f"--- {number}쪽 ---\n{page.extract_text() or ''}")
            for table in page.extract_tables() or []:
                parts.append("[표]\n" + _table_lines(table))
    text = "\n".join(parts)
    if len(re.sub(r"\s|---\s*\d+쪽\s*---", "", text)) < MIN_CHARS:
        return None, "PDF에 글자가 거의 없음 (스캔본 가능성)"
    return text, "PDF 텍스트·표"


def hwpx_text(path: Path) -> tuple[str | None, str]:
    # ZipFile은 만들 때 중앙 디렉터리를 통째로 읽어서, 끝 레코드로 항목 수·디렉터리 크기를 먼저 봐요(2026-11-16 보안 감사 4장)
    check_zip_path(path, max_entries=MAX_HWPX_ENTRIES)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_HWPX_ENTRIES or sum(entry.file_size for entry in entries) > MAX_HWPX_BYTES:
            raise ValueError("HWPX decompression limit exceeded")
        sections = sorted((entry for entry in entries if re.fullmatch(r"Contents/section\d+\.xml", entry.filename)), key=lambda entry: entry.filename)
        parts, remaining, remaining_nodes = [], MAX_HWPX_BYTES, MAX_XML_NODES
        for entry in sections:
            data = _read_member(archive, entry, remaining)
            remaining -= len(data)
            value, nodes = _hwpx_section(data, remaining_nodes)
            remaining_nodes -= nodes
            parts.append(value)
    text = re.sub(r"[ \t]+", " ", "".join(parts))
    return (text, "HWPX 텍스트·표") if len(text.strip()) >= MIN_CHARS else (None, "HWPX에서 글자를 거의 찾지 못함")


def hwp_text(path: Path) -> tuple[str | None, str]:
    html, error = hwp_to_html(path)
    if html:
        text = body_text(soup(html).body or soup(html))
        if len(text.strip()) >= MIN_CHARS:
            return text, "HWP 텍스트·표"
    text, fallback_error = hwp_to_plain_text(path)
    if text:
        return text, "HWP 텍스트 (표 구조 없음)"
    return None, f"HWP 변환 실패: {fallback_error or error}"


def extract_text(data: bytes, ext: str) -> tuple[str | None, str]:
    """(텍스트, 상태). 실패하면 텍스트는 None이고 상태에 이유가 들어가요."""
    readers = {"pdf": pdf_text, "hwpx": hwpx_text, "hwp": hwp_text}
    if ext not in readers:
        return None, f"{ext or '알 수 없는'} 형식은 읽지 않음"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"source.{ext}"
        path.write_bytes(data)
        try:
            text, status = readers[ext](path)
        except Exception as error:  # noqa: BLE001 — 손상된 파일 등은 '읽지 못함'으로 기록하고 넘어감
            return None, f"{ext.upper()} 읽기 실패 ({type(error).__name__})"
    # PDF에서 뽑은 글자에 NUL(\x00)이 섞이는 일이 있어요. PostgreSQL text 칸은 NUL을 받지 않아 지워요
    return (text.replace("\x00", "") if text else text), status
