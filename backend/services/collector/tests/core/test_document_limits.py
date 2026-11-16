"""작은 압축 파일이 압축 해제 과정에서 워커 메모리를 소진하지 않도록 해요."""

import io
import struct
import zipfile

import pytest

from mujuthaek_collector.core.documents import text


def hwpx(entries, compression=zipfile.ZIP_DEFLATED):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=compression) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return out.getvalue()


def declare_size(payload: bytes, size: int) -> bytes:
    """zip의 지역 헤더·중앙 디렉터리에 적힌 압축 해제 크기를 바꿔요. 파일을 만든 사람은 이 값을 마음대로 적을 수 있어요."""
    data = bytearray(payload)
    for signature, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        start = data.find(signature)
        while start >= 0:
            struct.pack_into("<I", data, start + offset, size)
            start = data.find(signature, start + 4)
    return bytes(data)


@pytest.mark.parametrize("compression", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_members_without_bounded_decompression_are_rejected(monkeypatch, compression):
    # 파이썬 zipfile은 BZIP2·LZMA를 출력 상한 없이 푼 뒤 적힌 크기로 잘라요. 크기를 작게 적으면 메타데이터 검사를 통과했어요
    payload = declare_size(hwpx([("Contents/section0.xml", "가" * 200_000)], compression), 1000)
    assert sum(entry.file_size for entry in zipfile.ZipFile(io.BytesIO(payload)).infolist()) == 1000

    def no_decompression(*args, **kwargs):
        raise AssertionError("must reject the compression method before decompressing")

    monkeypatch.setattr(zipfile.ZipFile, "open", no_decompression)
    assert text.extract_text(payload, "hwpx") == (None, "HWPX 읽기 실패 (ValueError)")


def test_actual_decompressed_bytes_are_counted(monkeypatch):
    monkeypatch.setattr(text, "READ_CHUNK", 1024)
    archive = zipfile.ZipFile(io.BytesIO(hwpx([("Contents/section0.xml", "a" * 10_000)])))
    entry = archive.infolist()[0]
    assert len(text._read_member(archive, entry, 10_000)) == 10_000
    with pytest.raises(ValueError, match="limit exceeded"):
        text._read_member(archive, entry, 9_999)


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
