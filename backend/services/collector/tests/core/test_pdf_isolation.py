import sys
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from mujuthaek_collector.core.documents import text


def test_concurrent_jobs_share_one_pdf_memory_budget(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def run(*args, **kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(3)
        return SimpleNamespace(returncode=0, stdout=b'[null, "bounded"]')

    monkeypatch.setattr(text, "run_converter", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(text.pdf_text, tmp_path / "one.pdf")
        assert entered.wait(3)
        second = pool.submit(text.pdf_text, tmp_path / "two.pdf")
        assert len(calls) == 1
        release.set()
        assert first.result() == second.result() == (None, "bounded")
    assert len(calls) == 2


def pdf_document(stream: bytes, *, compressed=False) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + (b" /Filter /FlateDecode" if compressed else b"") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def test_real_pdf_worker_preserves_text_and_removes_nul():
    payload = pdf_document(b"BT /F1 10 Tf 20 700 Td (" + b"Synthetic notice text " * 12 + b") Tj ET")
    value, status = text.extract_text(payload, "pdf")
    assert value and "Synthetic notice text" in value and "\x00" not in value
    assert status == "PDF 텍스트·표"


@pytest.mark.skipif(sys.platform != "linux", reason="Production PDF memory limits use Linux rlimits")
def test_small_compressed_pdf_cannot_exhaust_parent_memory():
    compressor = zlib.compressobj()
    pieces = [compressor.compress(b" " * (1024 * 1024)) for _ in range(192)]
    pieces.append(compressor.flush())
    payload = pdf_document(b"".join(pieces), compressed=True)
    assert len(payload) < 256 * 1024
    value, status = text.extract_text(payload, "pdf")
    assert value is None and "한도 초과" in status
    # 부모는 계속 살아 있고 다음 정상 문서를 처리할 수 있어야 해요.
    assert text.extract_text(pdf_document(b"BT /F1 10 Tf (" + b"Safe notice " * 30 + b") Tj ET"), "pdf")[0]


def test_pdf_page_cache_is_closed_even_on_text_failure(monkeypatch, tmp_path):
    closed = []

    def fail():
        raise ValueError("synthetic parser failure")

    page = SimpleNamespace(extract_text=fail, close=lambda: closed.append(True))

    class PDF:
        pages = [page]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    import pdfplumber

    monkeypatch.setattr(pdfplumber, "open", lambda path: PDF())
    with pytest.raises(ValueError, match="synthetic"):
        text._pdf_text(tmp_path / "source.pdf")
    assert closed == [True]
