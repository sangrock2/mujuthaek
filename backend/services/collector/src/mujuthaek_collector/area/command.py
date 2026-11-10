"""area-upload 명령: 원천 파일을 S3 area/에 올리고 area.source.ready를 아웃박스에 기록해요. 발행은 relay가 해요.

area-upload --source BUS_STOP --data-date 2025-10-31 --file 버스정류장.csv
area-upload --source STORES --scope 강원 --data-date 2026-06-30 --file 상가_강원.csv
area-upload --source SUBWAY_STATION --data-date 2026-06-18 --file 역사정보.xlsx   (엑셀은 UTF-8 CSV로 바꿔서 올려요)
area-upload --source ADDRESS_ENTRANCE --scope 36110 --data-date 2026-09-30 --file RNENTDATA_2610_36110.txt   (원본 그대로)
area-upload --manifest area/area_manifest.csv --skip-upload   (이미 S3에 있는 파일: sha256 메타데이터만 확인하고 이벤트만)
area-upload --manifest area/area_manifest_boundary.csv --skip-upload   (구역 경계 CSV 2개. 원본 zip 줄(REGION_BOUNDARY_RAW)은 건너뜀)
area-upload --manifest area/area_manifest_address.csv --skip-upload --resend   (이미 보낸 요청도 다시 보내기: 빠진 적재 다시 요청)
"""

import csv
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from mujuthaek_collector.area import events, sources
from mujuthaek_collector.area.excel import xlsx_to_csv
from mujuthaek_collector.area.upload import sha256_of, upload_once
from mujuthaek_collector.core.file_store import FileStore

# 받는 쪽(api area)의 큐. api가 같은 설정으로 만들지만, api가 한 번도 뜨지 않은 브로커에서는 큐가 없어서
# 발행기(mandatory)가 거절당하고 같은 묶음의 공고 이벤트까지 막혀요. 그래서 기록하기 전에 같은 설정으로 만들어 둬요.
QUEUE = "mujuthaek.area.source-ready"
DLX = "mujuthaek.dlx"


@dataclass
class Result:
    uploaded: int = 0
    recorded: int = 0
    archived: int = 0  # 목록에서 보관만 하는 원본이라 건너뛴 줄
    problems: list[str] = field(default_factory=list)


def upload_file(files: FileStore, conn, source: str, data_date: date, path: Path, scope: str | None = None, resend: bool = False) -> Result:
    """파일 하나를 올리고 이벤트를 기록해요. 같은 파일이면 올리지도, 다시 기록하지도 않아요 (resend면 이벤트는 다시 보내요)."""
    scope = sources.check_scope(source, scope)
    key = sources.s3_key(source, data_date, scope)
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = path
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            csv_path = Path(tmp) / sources.file_name(source, scope)
            xlsx_to_csv(path, csv_path)
        sha = sha256_of(csv_path)
        result = Result(uploaded=int(upload_once(files, key, csv_path, source, data_date, sha)))
        rows = _rows(csv_path, header=not sources.headerless(source))
        event = events.ready_event(source, scope, key, sha, data_date, path.name, rows)
    result.recorded = int(events.record(conn, event, resend))
    return result


def from_manifest(files: FileStore, conn, manifest: Path, resend: bool = False) -> Result:
    """이미 S3에 올린 파일 목록(원천, 범위, S3 키, sha256, 기준일, 원본 이름, 줄 수)으로 이벤트만 기록해요.
    S3 객체가 없거나 sha256 메타데이터가 다르면 그 줄은 건너뛰고 problems에 남겨요.
    보관만 하는 원본(sources.ARCHIVE_ONLY, 예: 구역의 도형 zip)은 적재 대상이 아니라 세기만 하고 건너뛰어요.
    resend면 이미 기록한 이벤트도 다시 보내요 (빠진 적재 다시 요청, infra/deploy/README.md)."""
    result = Result()
    with manifest.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            source, key, sha = row["source"], row["s3Key"], row["sha256"]
            if source in sources.ARCHIVE_ONLY:
                result.archived += 1
                continue
            data_date = date.fromisoformat(row["dataDate"])
            scope = sources.check_scope(source, row["scope"])
            if key != sources.s3_key(source, data_date, scope):
                result.problems.append(f"{key}: 키 규칙과 달라요 ({sources.s3_key(source, data_date, scope)})")
                continue
            metadata = files.metadata(key)
            if metadata is None:
                result.problems.append(f"{key}: S3에 없어요")
                continue
            if metadata.get("sha256") != sha:
                result.problems.append(f"{key}: S3의 sha256이 목록과 달라요")
                continue
            rows = int(row["rows"]) if row.get("rows") else None
            event = events.ready_event(source, scope, key, sha, data_date, row.get("fileName") or None, rows)
            result.recorded += int(events.record(conn, event, resend))
    return result


def declare_receiver(channel) -> None:
    """api area 모듈과 같은 설정의 큐·실패 큐·바인딩 (이미 있으면 그대로)."""
    from mujuthaek_platform.outbox import EXCHANGE

    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DLX, exchange_type="topic", durable=True)
    channel.queue_declare(queue=QUEUE + ".dlq", durable=True)
    channel.queue_bind(queue=QUEUE + ".dlq", exchange=DLX, routing_key=events.EVENT_TYPE)
    channel.queue_declare(queue=QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX})
    channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=events.EVENT_TYPE)


def _rows(path: Path, header: bool = True) -> int:
    """파일 줄 수(머리줄이 있으면 빼고). 확인용이라 칸 안 줄바꿈 때문에 레코드 수와 다를 수 있어요."""
    with path.open("rb") as f:
        lines = sum(1 for _ in f)
    return max(lines - 1, 0) if header else lines
