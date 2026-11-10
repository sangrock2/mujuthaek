"""공고문 원본에서 글자를 뽑아요. 표는 행·열을 '칸 | 칸'으로 살려서 AI 추출 단계가 표를 읽을 수 있게 해요."""

import re
import tempfile
import zipfile
from html import unescape
from pathlib import Path

from mujuthaek_collector.core.documents.hwp import hwp_to_html, hwp_to_plain_text
from mujuthaek_collector.core.html import body_text, soup

MIN_CHARS = 200  # 이보다 글자가 적으면 읽기 실패로 봐요 (스캔본 PDF 등)


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
    with zipfile.ZipFile(path) as archive:
        sections = sorted(n for n in archive.namelist() if re.match(r"Contents/section\d+\.xml", n))
        xml = "".join(archive.read(n).decode("utf-8", errors="replace") for n in sections)

    def table_to_text(match: re.Match) -> str:
        rows = []
        for row in re.findall(r"<hp:tr\b[\s\S]*?</hp:tr>", match.group(0)):
            cells = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cell))).strip() for cell in re.findall(r"<hp:tc\b[\s\S]*?</hp:tc>", row)]
            rows.append(" | ".join(cells))
        return "\n[표]\n" + "\n".join(rows) + "\n"

    xml = re.sub(r"<hp:tbl\b[\s\S]*?</hp:tbl>", table_to_text, xml)
    xml = re.sub(r"</hp:p>", "\n", xml)
    text = re.sub(r"[ \t]+", " ", unescape(re.sub(r"<[^>]+>", "", xml)))
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
