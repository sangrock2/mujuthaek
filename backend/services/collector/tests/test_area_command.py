"""area-upload 명령. --skip-upload 경로의 실제 S3 동작은 로컬 MinIO로 확인해요 (없으면 건너뜀):
COLLECTOR_TEST_S3=1 uv run pytest tests/test_area_command.py
"""

import csv
import os
from datetime import date
from pathlib import Path

import pytest

from mujuthaek_collector.area import command, sources
from mujuthaek_collector.area.upload import sha256_of, upload_once
from tests.fakes import MemoryFileStore

MANIFEST = Path(__file__).resolve().parents[1] / "area" / "area_manifest.csv"
ADDRESS_MANIFEST = Path(__file__).resolve().parents[1] / "area" / "area_manifest_address.csv"
BOUNDARY_MANIFEST = Path(__file__).resolve().parents[1] / "area" / "area_manifest_boundary.csv"


class MemoryOutbox:
    """area events.record가 쓰는 만큼만: execute(insert … on conflict do nothing).rowcount"""

    def __init__(self):
        self.events = {}

    def execute(self, sql, params):
        new = params[0] not in self.events
        self.events.setdefault(params[0], params[3].obj)
        return type("Cursor", (), {"rowcount": 1 if new else 0})()


def write_csv(path: Path, lines: int) -> Path:
    path.write_text("정류장번호,정류장명,위도,경도,도시코드,도시명\n" + "1,시청,37.56,126.97,11,서울\n" * lines, encoding="utf-8")
    return path


def test_upload_records_one_event_and_a_second_run_records_nothing(tmp_path):
    files, outbox = MemoryFileStore(), MemoryOutbox()
    path = write_csv(tmp_path / "국토교통부_전국 버스정류장 위치정보_20251031.csv", 3)

    first = command.upload_file(files, outbox, "BUS_STOP", date(2025, 10, 31), path)
    second = command.upload_file(files, outbox, "BUS_STOP", date(2025, 10, 31), path)

    assert (first.uploaded, first.recorded) == (1, 1)
    assert (second.uploaded, second.recorded) == (0, 0)
    [event] = outbox.events.values()
    assert event["payload"] == {
        "source": "BUS_STOP",
        "scope": "ALL",
        "s3Key": "area/BUS_STOP/2025-10-31/bus_stop.csv",
        "sha256": sha256_of(path),
        "dataDate": "2025-10-31",
        "fileName": path.name,
        "rows": 3,
    }


def test_address_entrance_is_uploaded_as_is_and_counts_every_line(tmp_path):
    files, outbox = MemoryFileStore(), MemoryOutbox()
    path = tmp_path / "RNENTDATA_2610_36110.txt"
    path.write_bytes("3611010100|세종|조치원읍\r\n3611010100|세종|조치원읍\r\n".encode("cp949"))

    result = command.upload_file(files, outbox, "ADDRESS_ENTRANCE", date(2026, 9, 30), path, "36110")

    key = "area/ADDRESS_ENTRANCE/2026-09-30/address_entrance_36110.txt"
    assert result.uploaded == 1
    assert files.objects[key] == path.read_bytes()  # 바꾸지 않고 그대로
    [event] = outbox.events.values()
    assert event["payload"]["scope"] == "36"
    assert event["payload"]["s3Key"] == key
    assert event["payload"]["rows"] == 2  # 머리줄이 없어서 빼지 않아요


def test_manifest_records_events_for_files_already_in_s3(tmp_path):
    files, outbox = MemoryFileStore(), MemoryOutbox()
    manifest = tmp_path / "manifest.csv"
    rows = [
        ["BUS_STOP", "ALL", "area/BUS_STOP/2025-10-31/bus_stop.csv", "a" * 64, "2025-10-31", "버스.csv", "3"],
        ["STORES", "강원", "area/STORES/2026-06-30/stores_gangwon.csv", "b" * 64, "2026-06-30", "상가_강원.csv", "7"],
        ["STORES", "경기", "area/STORES/2026-06-30/stores_gyeonggi.csv", "c" * 64, "2026-06-30", "상가_경기.csv", "7"],
    ]
    with manifest.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "scope", "s3Key", "sha256", "dataDate", "fileName", "rows"])
        writer.writerows(rows)
    files.objects = {r[2]: b"" for r in rows}
    files.metadatas = {rows[0][2]: {"sha256": "a" * 64}, rows[1][2]: {"sha256": "b" * 64}, rows[2][2]: {"sha256": "x" * 64}}

    result = command.from_manifest(files, outbox, manifest)

    assert result.recorded == 2
    assert result.problems == ["area/STORES/2026-06-30/stores_gyeonggi.csv: S3의 sha256이 목록과 달라요"]
    assert command.from_manifest(files, outbox, manifest).recorded == 0  # 두 번째는 같은 eventId라 기록 안 함


class ResendOutbox(MemoryOutbox):
    """resend면 이미 있어도 다시 보낼 이벤트로 세요 (published_at = null로 되돌림)"""

    def execute(self, sql, params):
        if "published_at = null" in sql:
            self.events[params[0]] = params[3].obj
            return type("Cursor", (), {"rowcount": 1})()
        return super().execute(sql, params)


def test_manifest_resend_sends_already_recorded_events_again(tmp_path):
    files, outbox = MemoryFileStore(), ResendOutbox()
    manifest = write_manifest(
        tmp_path / "manifest.csv",
        [["BUS_STOP", "ALL", "area/BUS_STOP/2025-10-31/bus_stop.csv", "a" * 64, "2025-10-31", "버스.csv", "3"]],
    )
    files.objects = {"area/BUS_STOP/2025-10-31/bus_stop.csv": b""}
    files.metadatas = {"area/BUS_STOP/2025-10-31/bus_stop.csv": {"sha256": "a" * 64}}

    assert command.from_manifest(files, outbox, manifest).recorded == 1
    assert command.from_manifest(files, outbox, manifest).recorded == 0
    assert command.from_manifest(files, outbox, manifest, resend=True).recorded == 1  # 이미 보낸 것도 다시


def write_manifest(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "scope", "s3Key", "sha256", "dataDate", "fileName", "rows"])
        writer.writerows(rows)
    return path


@pytest.mark.skipif(not os.getenv("COLLECTOR_TEST_S3"), reason="COLLECTOR_TEST_S3가 없어요 (로컬 MinIO 테스트)")
def test_local_minio_skip_upload_records_only_events_and_rejects_a_different_sha(tmp_path):
    from mujuthaek_collector.config import Settings
    from mujuthaek_collector.core.file_store import S3FileStore

    settings = Settings.from_env()
    files = S3FileStore(settings.s3_bucket, settings.s3_endpoint, settings.s3_access_key, settings.s3_secret_key)
    data_date = date(1999, 1, 1)  # 실제 원천과 키가 겹치지 않는 기준일
    bus_key = sources.s3_key("BUS_STOP", data_date)
    store_key = sources.s3_key("STORES", data_date, "제주")
    bus = write_csv(tmp_path / "bus.csv", 3)
    store = tmp_path / "store.csv"
    store.write_text("상가업소번호,상호명\nMA0001,가게\n", encoding="utf-8")
    try:
        # 먼저 올려 둠 (메타데이터 source·data-date·sha256)
        upload_once(files, bus_key, bus, "BUS_STOP", data_date, sha256_of(bus))
        upload_once(files, store_key, store, "STORES", data_date, sha256_of(store))
        manifest = write_manifest(
            tmp_path / "manifest.csv",
            [
                ["BUS_STOP", "ALL", bus_key, sha256_of(bus), data_date.isoformat(), "bus.csv", "3"],
                ["STORES", "제주", store_key, "0" * 64, data_date.isoformat(), "store.csv", "1"],
            ],
        )
        before = {k: files.metadata(k) for k in (bus_key, store_key)}
        outbox = MemoryOutbox()

        result = command.from_manifest(files, outbox, manifest)

        assert (result.uploaded, result.recorded) == (0, 1)
        assert result.problems == [f"{store_key}: S3의 sha256이 목록과 달라요"]
        [event] = outbox.events.values()
        assert event["payload"]["s3Key"] == bus_key
        assert event["payload"]["sha256"] == sha256_of(bus)
        assert {k: files.metadata(k) for k in (bus_key, store_key)} == before  # 올리지 않음
    finally:
        files.delete(bus_key)
        files.delete(store_key)


def test_the_manifest_in_the_repo_follows_the_key_rule():
    # 2026-10-22에 실제로 올린 21개 목록
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 21
    for row in rows:
        assert row["s3Key"] == sources.s3_key(row["source"], date.fromisoformat(row["dataDate"]), row["scope"])


def test_the_address_manifest_in_the_repo_follows_the_key_rule():
    # 2026-10-22에 개발 S3에 올린 도로명주소 출입구 16개 목록
    with ADDRESS_MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 16
    assert {row["scope"] for row in rows} == set(sources.ADDRESS_SCOPES)
    for row in rows:
        assert row["source"] == "ADDRESS_ENTRANCE"
        assert row["s3Key"] == sources.s3_key(row["source"], date.fromisoformat(row["dataDate"]), row["scope"])
        assert row["fileName"] == f"RNENTDATA_2610_{sources.ADDRESS_SCOPES[row['scope']]}.txt"


def test_the_boundary_manifest_records_two_csvs_and_skips_raw_zips():
    # 2026-10-22에 개발 S3에 올린 구역 경계 CSV 2개 + 원본 zip 16개(보관만)
    with BOUNDARY_MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    loadable = [r for r in rows if r["source"] not in sources.ARCHIVE_ONLY]
    assert [(r["source"], r["rows"]) for r in loadable] == [("REGION_BOUNDARY_SIG", "256"), ("REGION_BOUNDARY_EMD", "5067")]
    assert len(rows) - len(loadable) == 16
    for row in loadable:
        assert row["s3Key"] == sources.s3_key(row["source"], date.fromisoformat(row["dataDate"]), row["scope"])

    files, outbox = MemoryFileStore(), MemoryOutbox()
    files.objects = {r["s3Key"]: b"" for r in loadable}
    files.metadatas = {r["s3Key"]: {"sha256": r["sha256"]} for r in loadable}

    result = command.from_manifest(files, outbox, BOUNDARY_MANIFEST)

    assert (result.recorded, result.archived, result.problems) == (2, 16, [])


class RecordingChannel:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda **kwargs: self.calls.append((name, kwargs))


def test_declares_the_api_queue_with_the_same_arguments():
    channel = RecordingChannel()
    command.declare_receiver(channel)
    assert (
        "queue_declare",
        {"queue": "mujuthaek.area.source-ready", "durable": True, "arguments": {"x-dead-letter-exchange": "mujuthaek.dlx"}},
    ) in channel.calls
    assert ("queue_bind", {"queue": "mujuthaek.area.source-ready", "exchange": "mujuthaek.events", "routing_key": "area.source.ready"}) in channel.calls
