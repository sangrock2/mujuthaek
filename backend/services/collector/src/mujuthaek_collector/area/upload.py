"""원천 파일을 S3 area/에 올려요. 객체 메타데이터 키는 source, data-date, sha256이에요 (2026-10-22에 올린 21개와 같은 이름)."""

import hashlib
from datetime import date
from pathlib import Path

from mujuthaek_collector.core.file_store import CONTENT_TYPES, FileStore


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_once(files: FileStore, key: str, path: Path, source: str, data_date: date, sha256: str) -> bool:
    """같은 키에 같은 sha256이 이미 있으면 올리지 않고 False, 올렸으면 True."""
    existing = files.metadata(key)
    if existing is not None and existing.get("sha256") == sha256:
        return False
    metadata = {"source": source, "data-date": data_date.isoformat(), "sha256": sha256}
    # .txt(도로명주소)는 CP949라 charset 없이 text/plain
    content_type = "text/plain" if key.endswith(".txt") else CONTENT_TYPES["csv"]
    files.put_file(key, path, content_type, metadata)
    return True
