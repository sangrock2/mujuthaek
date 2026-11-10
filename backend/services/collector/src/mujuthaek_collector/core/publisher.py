"""수집 이벤트(raw.notice.collected) 만들기. 형식은 contracts/events/raw.notice.collected.v1.json이에요.

이벤트는 storage.save_version이 저장과 같은 트랜잭션에서 아웃박스에 적고, 발행기(relay)가 RabbitMQ로 보내요.
"""

from datetime import date
from typing import Any
from uuid import UUID

from mujuthaek_platform.events import new_event

EVENT_TYPE = "raw.notice.collected"
PRODUCER = "collector"
MAX_TEXT_CHARS = 200_000  # 이보다 길면 앞부분만 이벤트에 넣고 전체는 S3(textKey)에 둬요


def build_collected_event(
    *,
    raw_post_id: UUID,
    version: int,
    source_code: str,
    provider: str,
    kind: str,
    title: str,
    posted_on: date | None,
    detail_url: str | None,
    parent_post_id: UUID | None,
    full_text: str,
    text_key: str | None,
    files: list[dict[str, Any]],
    region_code: str | None = None,
    reprocess: bool = False,
) -> dict[str, Any]:
    payload = {
        "rawPostId": str(raw_post_id),
        "version": version,
        "sourceCode": source_code,
        "provider": provider,
        "regionCode": region_code,
        "field": "HOUSING",
        "kind": kind,
        "title": title,
        "postedOn": posted_on.isoformat() if posted_on else None,
        "detailUrl": detail_url,
        "supersedesPostId": str(parent_post_id) if parent_post_id else None,
        "text": full_text[:MAX_TEXT_CHARS],
        "textKey": text_key,
        "units": [],  # 호별 임대조건은 extraction이 원본(files의 UNIT_LIST·NOTICE_DOC)에서 읽어요
        "files": [
            {
                "name": f["name"],
                "fileType": f["file_type"],
                "role": f["role"],
                "s3Key": f["s3_key"],
                "downloadUrl": f["download_url"],
                "sha256": f["file_hash"],
            }
            for f in files
        ],
        "reprocess": reprocess,
    }
    return new_event(EVENT_TYPE, PRODUCER, payload)
