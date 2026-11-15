"""작은 압축 파일이 압축 해제 과정에서 워커 메모리를 소진하지 않도록 해요."""

import io
import zipfile

from mujuthaek_collector.core.documents import text


def hwpx(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return out.getvalue()


def test_compressed_xml_is_rejected_before_reading(monkeypatch):
    monkeypatch.setattr(text, "MAX_HWPX_BYTES", 1024)
    payload = hwpx([("Contents/section0.xml", "가" * 4000)])
    assert len(payload) < 1024

    def no_decompression(*args, **kwargs):
        raise AssertionError("must reject from metadata before opening a member")

    monkeypatch.setattr(zipfile.ZipFile, "open", no_decompression)
    assert text.extract_text(payload, "hwpx") == (None, "HWPX 읽기 실패 (ValueError)")


def test_entry_count_is_bounded(monkeypatch):
    monkeypatch.setattr(text, "MAX_HWPX_ENTRIES", 2)
    payload = hwpx([(f"Contents/section{n}.xml", "") for n in range(3)])
    assert text.extract_text(payload, "hwpx")[0] is None


def test_regular_hwpx_still_extracts_text():
    payload = hwpx([("Contents/section0.xml", "<hp:p>" + "주거 공고문 " * 100 + "</hp:p>")])
    value, status = text.extract_text(payload, "hwpx")
    assert "주거 공고문" in value
    assert status == "HWPX 텍스트·표"
