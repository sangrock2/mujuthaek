"""ZIP 형식 문서(HWPX·XLSX)를 열기 전에 끝 레코드와 중앙 디렉터리 머리만 훑어 크기·항목 수를 확인해요.

파이썬 zipfile은 ZipFile을 만드는 순간 중앙 디렉터리를 통째로 읽고 항목마다 ZipInfo를 만들어서,
항목 수 검사를 그 뒤에 하면 이미 늦어요. 30MiB 파일 하나로 메모리를 약 190MiB 썼어요(2026-11-16 보안 감사 4장).
여기서는 끝 레코드(EOCD, ZIP64 포함)를 zipfile과 같은 순서로 찾아 적힌 항목 수·디렉터리 크기를 보고,
디렉터리 머리(46바이트)만 넘겨 가며 실제 항목 수를 세요. 한도를 넘거나 구조가 이상하면 ZipFile을 만들기 전에
ArchiveRejected를 내요.
"""

from __future__ import annotations

import io
import os
import struct
from typing import BinaryIO

_EOCD = struct.Struct("<4s4H2LH")  # 끝 레코드 22바이트(주석 제외)
_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_LOCATOR = struct.Struct("<4sLQL")  # 20바이트
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_EOCD = struct.Struct("<4sQ2H2L4Q")  # 56바이트
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_CENTRAL_SIZE = 46  # 중앙 디렉터리 항목 머리
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_CENTRAL_LENGTHS = struct.Struct("<3H")  # 이름·추가 칸·주석 길이 (머리 28바이트째부터)
_MAX_COMMENT = 0xFFFF
# 항목 하나에 잡는 중앙 디렉터리 바이트. 한글·엑셀 문서의 항목 이름은 짧아서(보통 50바이트 안팎) 넉넉해요
DIRECTORY_BYTES_PER_ENTRY = 512


class ArchiveRejected(ValueError):
    """중앙 디렉터리가 한도를 넘거나 끝 레코드가 이상해서 ZIP을 열지 않았어요."""


def check_zip_bytes(data: bytes, *, max_entries: int, max_directory_bytes: int | None = None) -> int:
    """메모리에 있는 ZIP을 check_zip_file과 같은 방법으로 확인해요."""
    return check_zip_file(io.BytesIO(data), max_entries=max_entries, max_directory_bytes=max_directory_bytes)


def check_zip_path(path: str | os.PathLike[str], *, max_entries: int, max_directory_bytes: int | None = None) -> int:
    """파일로 있는 ZIP을 check_zip_file과 같은 방법으로 확인해요."""
    with open(path, "rb") as source:
        return check_zip_file(source, max_entries=max_entries, max_directory_bytes=max_directory_bytes)


def check_zip_file(source: BinaryIO, *, max_entries: int, max_directory_bytes: int | None = None) -> int:
    """중앙 디렉터리 항목 수를 돌려줘요. 적힌 항목 수·디렉터리 크기나 실제 항목 수가 한도를 넘으면 ArchiveRejected.

    max_directory_bytes를 비우면 항목 수 × DIRECTORY_BYTES_PER_ENTRY예요.
    끝 레코드가 여럿으로 읽힐 수 있으면(ZIP64) 큰 값을 써요.
    """
    if max_entries < 1:
        raise ValueError("max_entries는 1 이상이어야 해요")
    directory_limit = max_entries * DIRECTORY_BYTES_PER_ENTRY if max_directory_bytes is None else max_directory_bytes
    size = source.seek(0, io.SEEK_END)
    if size < _EOCD.size:
        raise ArchiveRejected("ZIP end record is missing")
    tail_start = max(size - _EOCD.size - _MAX_COMMENT, 0)
    source.seek(tail_start)
    tail = source.read(size - tail_start)
    # zipfile과 같은 순서: 주석 없는 끝 레코드를 먼저 보고, 아니면 뒤에서부터 서명을 찾아요
    if tail[-_EOCD.size : -_EOCD.size + 4] == _EOCD_SIGNATURE and tail[-2:] == b"\x00\x00":
        position = len(tail) - _EOCD.size
    else:
        position = tail.rfind(_EOCD_SIGNATURE)
        if position < 0 or position + _EOCD.size > len(tail):
            raise ArchiveRejected("ZIP end record is missing")
    _, _, _, disk_entries, entries, directory_size, _, _ = _EOCD.unpack_from(tail, position)
    end_record_at = tail_start + position
    directory_end = end_record_at

    locator_at = end_record_at - _ZIP64_LOCATOR.size
    if locator_at >= 0:
        source.seek(locator_at)
        locator = source.read(_ZIP64_LOCATOR.size)
        if len(locator) == _ZIP64_LOCATOR.size and locator[:4] == _ZIP64_LOCATOR_SIGNATURE:
            _, disk, relative_offset, disks = _ZIP64_LOCATOR.unpack(locator)
            if disk != 0 or disks > 1:
                raise ArchiveRejected("multi-disk ZIP is not supported")
            record_at = locator_at - _ZIP64_EOCD.size
            # 32비트 칸이 넘침 표시(0xFFFF…)면 ZIP64 값만, 아니면 둘 중 큰 값을 써요
            disk_entries = 0 if disk_entries == 0xFFFF else disk_entries
            entries = 0 if entries == 0xFFFF else entries
            directory_size = 0 if directory_size == 0xFFFFFFFF else directory_size
            found = False
            # 파이썬 버전에 따라 locator 바로 앞이나 locator가 가리키는 곳을 읽어서 둘 다 봐요
            for at in sorted({record_at, relative_offset}):
                if not 0 <= at <= size - _ZIP64_EOCD.size:
                    continue
                source.seek(at)
                record = source.read(_ZIP64_EOCD.size)
                if record[:4] != _ZIP64_EOCD_SIGNATURE:
                    continue
                values = _ZIP64_EOCD.unpack(record)
                disk_entries, entries = max(disk_entries, values[6]), max(entries, values[7])
                directory_size = max(directory_size, values[8])
                if at == record_at:
                    directory_end, found = record_at, True
            if not found:
                raise ArchiveRejected("ZIP64 end record is broken")

    if max(entries, disk_entries) > max_entries:
        raise ArchiveRejected("ZIP declares too many entries")
    if directory_size > directory_limit:
        raise ArchiveRejected("ZIP central directory is too large")
    start = directory_end - directory_size
    if start < 0:
        raise ArchiveRejected("ZIP central directory offset is broken")
    source.seek(start)
    directory = source.read(directory_size)
    count, offset = 0, 0
    while offset < len(directory):  # zipfile도 적힌 크기를 다 쓸 때까지 항목을 읽어요
        if offset + _CENTRAL_SIZE > len(directory) or directory[offset : offset + 4] != _CENTRAL_SIGNATURE:
            raise ArchiveRejected("ZIP central directory is broken")
        name, extra, comment = _CENTRAL_LENGTHS.unpack_from(directory, offset + 28)
        offset += _CENTRAL_SIZE + name + extra + comment
        count += 1
        if count > max_entries:
            raise ArchiveRejected("ZIP has too many entries")
    return count
