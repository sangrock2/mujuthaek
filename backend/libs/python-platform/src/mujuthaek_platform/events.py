"""이벤트 봉투. 프로그램 사이(collector·extraction·api)로 오가는 모든 이벤트가 같은 모양이에요.

{
  "eventId": "UUID v7",              받는 쪽이 processed_events로 한 번만 처리할 때 쓰는 키
  "eventType": "raw.notice.collected",  RabbitMQ 라우팅 키이기도 해요
  "schemaVersion": 1,                contracts/events/<eventType>.v<schemaVersion>.json
  "occurredAt": "2026-10-15T01:23:45.678Z",
  "producer": "collector",
  "payload": { ... }                 이벤트마다 다른 내용 (스키마 참고)
}
"""

from datetime import UTC, datetime
from typing import Any

from mujuthaek_platform.ids import uuid7


def new_event(event_type: str, producer: str, payload: dict[str, Any], schema_version: int = 1) -> dict[str, Any]:
    return {
        "eventId": str(uuid7()),
        "eventType": event_type,
        "schemaVersion": schema_version,
        "occurredAt": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "producer": producer,
        "payload": payload,
    }
