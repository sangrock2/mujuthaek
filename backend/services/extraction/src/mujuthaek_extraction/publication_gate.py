"""초기 표본 확인 뒤 검증된 결과를 발행해요. 부분 통과는 보류 항목을 제외한 기존 게시 흐름을 유지해요."""

from __future__ import annotations

import os
from typing import Any

from psycopg.types.json import Jsonb

from mujuthaek_platform import outbox

MODES = {"legacy", "manual", "verified"}
INITIAL_REVIEW = "운영 초기 표본 확인 전 공개 보류"
VERIFICATION_REVIEW = "공고 전체 검수가 필요해 공개 보류"


class PublicationGate:
    def __init__(self, mode: str | None = None):
        self.mode = mode if mode is not None else os.getenv("EXTRACTION_PUBLICATION_MODE", "legacy")
        if self.mode not in MODES:
            raise ValueError("EXTRACTION_PUBLICATION_MODE는 legacy·manual·verified 중 하나여야 합니다")

    def allows(self, event: dict[str, Any]) -> bool:
        if self.mode == "legacy":
            return True
        payload = event.get("payload") or {}
        if event.get("eventType") == "extraction.completed":
            status = payload.get("reviewStatus")
            return status == "APPROVED" or (self.mode == "verified" and status in {"AUTO_PASSED", "PARTIALLY_PASSED"})
        if event.get("eventType") == "policy.extracted":
            quality = payload.get("quality") or {}
            return quality.get("reviewed") is True or (self.mode == "verified" and quality.get("needsReview") is False)
        return False

    @property
    def reason(self) -> str:
        return INITIAL_REVIEW if self.mode == "manual" else VERIFICATION_REVIEW

    def enqueue(self, cur, event: dict[str, Any], *, job_id: str | None = None) -> bool:
        if self.allows(event):
            outbox.add(cur, event)
            return True
        cur.execute(
            "insert into publication_holds (event_id, event_type, envelope, reason, job_id) values (%s, %s, %s, %s, %s) on conflict do nothing",
            (event["eventId"], event["eventType"], Jsonb(event), self.reason, job_id),
        )
        return False

    def release(self, conn, *, limit: int = 100) -> int:
        """verified 전환 후 승인 가능한 보류본만 같은 트랜잭션으로 발행해요. 다시 실행해도 중복 발행하지 않아요."""
        if self.mode != "verified":
            raise ValueError("초기 표본 확인 후 verified 모드에서만 보류본을 발행할 수 있습니다")
        if not 1 <= limit <= 1000:
            raise ValueError("한 번에 발행할 보류본 수는 1~1000이어야 합니다")
        sent = 0
        with conn.transaction(), conn.cursor() as cur:
            rows = cur.execute(
                "select event_id, envelope, job_id from publication_holds where released_at is null and ("
                "(event_type = 'extraction.completed' and envelope->'payload'->>'reviewStatus' in ('AUTO_PASSED', 'PARTIALLY_PASSED', 'APPROVED')) or "
                "(event_type = 'policy.extracted' and (envelope->'payload'->'quality'->>'reviewed' = 'true' or "
                "envelope->'payload'->'quality'->>'needsReview' = 'false'))) "
                "order by created_at, event_id limit %s for update skip locked",
                (limit,),
            ).fetchall()
            for event_id, event, job_id in rows:
                if sent >= limit:
                    break
                if not self.allows(event):
                    continue
                outbox.add(cur, event)
                cur.execute("update publication_holds set released_at = now() where event_id = %s", (event_id,))
                if job_id is not None:
                    cur.execute(
                        "update extraction_jobs set status = %s, completed_event_id = %s where id = %s and status = 'IN_REVIEW'",
                        ("PARTIAL" if event["payload"]["reviewStatus"] == "PARTIALLY_PASSED" else "COMPLETED", event_id, job_id),
                    )
                sent += 1
        return sent
