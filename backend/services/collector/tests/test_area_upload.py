"""원천 파일 올리기. 실제 S3 동작은 로컬 MinIO로 확인해요 (없으면 건너뜀):
COLLECTOR_TEST_S3=1 uv run pytest tests/test_area_upload.py
"""

import os
import uuid
from datetime import date

import pytest

from mujuthaek_collector.area.upload import sha256_of, upload_once
from tests.fakes import MemoryFileStore

KEY = "area/BUS_STOP/2025-10-31/bus_stop.csv"


def test_uploads_with_metadata_and_skips_the_same_file(tmp_path):
    path = tmp_path / "bus_stop.csv"
    path.write_text("정류장번호,정류장명\n1,시청\n", encoding="utf-8")
    files = MemoryFileStore()
    sha = sha256_of(path)

    assert upload_once(files, KEY, path, "BUS_STOP", date(2025, 10, 31), sha) is True
    assert files.metadatas[KEY] == {"source": "BUS_STOP", "data-date": "2025-10-31", "sha256": sha}
    assert upload_once(files, KEY, path, "BUS_STOP", date(2025, 10, 31), sha) is False

    path.write_text("정류장번호,정류장명\n1,시청\n2,광장\n", encoding="utf-8")
    assert upload_once(files, KEY, path, "BUS_STOP", date(2025, 10, 31), sha256_of(path)) is True


@pytest.mark.skipif(not os.getenv("COLLECTOR_TEST_S3"), reason="COLLECTOR_TEST_S3가 없어요 (로컬 MinIO 테스트)")
def test_local_minio_stream_upload_and_metadata(tmp_path):
    from mujuthaek_collector.config import Settings
    from mujuthaek_collector.core.file_store import S3FileStore

    settings = Settings.from_env()
    files = S3FileStore(settings.s3_bucket, settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key)
    key = f"area/BUS_STOP/2025-10-31/test_{uuid.uuid4().hex}.csv"
    path = tmp_path / "big.csv"
    path.write_bytes(b"a,b\n" + b"1,2\n" * 3_000_000)  # 12MB: boto3 기본 기준(8MB)을 넘어 여러 조각으로 올라가요
    sha = sha256_of(path)
    try:
        assert files.metadata(key) is None
        assert upload_once(files, key, path, "BUS_STOP", date(2025, 10, 31), sha) is True
        assert files.metadata(key) == {"source": "BUS_STOP", "data-date": "2025-10-31", "sha256": sha}
        assert upload_once(files, key, path, "BUS_STOP", date(2025, 10, 31), sha) is False
    finally:
        files.delete(key)
