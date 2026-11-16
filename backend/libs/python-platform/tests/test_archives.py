import io
import struct
import zipfile

import pytest

from mujuthaek_platform.archives import ArchiveRejected, check_zip_bytes, check_zip_path


def make_zip(count: int, name: str = "Contents/section{}.xml") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(count):
            archive.writestr(name.format(index), b"x")
    return buffer.getvalue()


def end_record(data: bytes) -> tuple[int, tuple]:
    at = data.rfind(b"PK\x05\x06")
    return at, struct.unpack_from("<4s4H2LH", data, at)


def with_declared(data: bytes, entries: int) -> bytes:
    """끝 레코드에 적힌 항목 수만 바꿔요(실제 디렉터리는 그대로)."""
    at, (sig, disk, cd_disk, _, _, size, offset, comment) = end_record(data)
    return (
        data[:at]
        + struct.pack("<4s4H2LH", sig, disk, cd_disk, entries, entries, size, offset, comment)
        + data[at + 22 :]
    )


def as_zip64(data: bytes, entries: int | None = None, directory_size: int | None = None) -> bytes:
    """끝 레코드 앞에 ZIP64 끝 레코드·locator를 넣고 32비트 칸은 0xFFFF…로 채워요."""
    at, (_, _, _, count, _, size, offset, _) = end_record(data)
    entries = count if entries is None else entries
    directory_size = size if directory_size is None else directory_size
    record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, entries, entries, directory_size, offset)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, at, 1)
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return data[:at] + record + locator + end


def test_counts_entries_of_normal_archive():
    data = make_zip(5)
    assert check_zip_bytes(data, max_entries=10) == 5
    assert len(zipfile.ZipFile(io.BytesIO(data)).infolist()) == 5


def test_archive_with_comment_is_read_like_zipfile():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.xml", b"x")
        archive.comment = b"z" * 300
    assert check_zip_bytes(buffer.getvalue(), max_entries=4) == 1


def test_declared_entry_count_over_limit_is_rejected_before_zipfile():
    with pytest.raises(ArchiveRejected, match="declares too many"):
        check_zip_bytes(with_declared(make_zip(3), 5000), max_entries=2048)


def test_real_entries_are_counted_even_when_end_record_understates_them():
    data = with_declared(make_zip(60), 1)  # 적힌 수는 1이지만 zipfile은 디렉터리 끝까지 60개를 읽어요
    with pytest.raises(ArchiveRejected, match="too many entries"):
        check_zip_bytes(data, max_entries=50, max_directory_bytes=1 << 20)


def test_large_central_directory_is_rejected():
    with pytest.raises(ArchiveRejected, match="too large"):
        check_zip_bytes(
            make_zip(40, "a-long-entry-name-" + "n" * 200 + "{}.xml"), max_entries=40, max_directory_bytes=4096
        )


def test_zip64_end_record_values_are_used():
    data = as_zip64(make_zip(3))
    assert len(zipfile.ZipFile(io.BytesIO(data)).infolist()) == 3  # 만든 ZIP64가 zipfile에서도 열리는지
    assert check_zip_bytes(data, max_entries=10) == 3
    with pytest.raises(ArchiveRejected, match="declares too many"):
        check_zip_bytes(as_zip64(make_zip(3), entries=10**9), max_entries=2048)
    with pytest.raises(ArchiveRejected, match="too large"):
        check_zip_bytes(as_zip64(make_zip(3), directory_size=10**9), max_entries=2048)


def test_broken_or_truncated_archives_are_rejected():
    data = make_zip(2)
    for broken in (b"", b"not a zip at all", data[:-30], data.replace(b"PK\x01\x02", b"PK\x01\x03")):
        with pytest.raises(ArchiveRejected):
            check_zip_bytes(broken, max_entries=10)


def test_path_variant(tmp_path):
    path = tmp_path / "doc.hwpx"
    path.write_bytes(make_zip(2))
    assert check_zip_path(path, max_entries=2) == 2
    with pytest.raises(ArchiveRejected):
        check_zip_path(path, max_entries=1)
