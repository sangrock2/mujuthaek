"""정책 수집 이벤트(raw.policy.collected). 형식은 contracts/events/raw.policy.collected.v1.json이에요.

공고 이벤트(raw.notice.collected)와 같은 봉투·아웃박스를 써요. extraction이 받아서 정책 추출 규칙(지원 대상, 자격 조건,
지원 내용, 신청 기간·방법)을 돌리고, api benefit 모듈이 정제(같은 정책 합치기, 지역 코드, 대상 태그)를 해요.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from mujuthaek_collector.core.publisher import MAX_TEXT_CHARS, PRODUCER
from mujuthaek_platform.events import new_event

EVENT_TYPE = "raw.policy.collected"


def build_policy_event(
    *,
    raw_policy_id: UUID,
    version: int,
    source_code: str,
    provider: str,
    field: str,
    policy_id: str,
    title: str,
    agency: str | None,
    region_scope: str,
    region_names: list[str],
    region_codes: list[str],
    categories: list[str],
    detail_url: str | None,
    apply_url: str | None,
    source_modified_at: str | None,
    full_text: str,
    text_key: str | None,
    record: dict[str, Any],
    files: list[dict[str, Any]],
    has_document: bool = False,
    has_origin_text: bool = False,
    document_status: str = "NO_SOURCE",
    origin_status: str = "NO_SOURCE",
    reprocess: bool = False,
) -> dict[str, Any]:
    payload = {
        "rawPolicyId": str(raw_policy_id),
        "version": version,
        "sourceCode": source_code,
        "provider": provider,
        "field": field,
        "policyId": policy_id,
        "title": title,
        "agency": agency,
        "regionScope": region_scope,
        "regionNames": region_names,
        "regionCodes": region_codes,
        "categories": categories,
        "detailUrl": detail_url,
        "applyUrl": apply_url,
        "sourceModifiedAt": source_modified_at,
        "text": full_text[:MAX_TEXT_CHARS],
        "textKey": text_key,
        "record": record,
        "hasDocument": has_document,
        "hasOriginText": has_origin_text,
        "documentStatus": document_status,
        "originStatus": origin_status,
        "files": files,
        "reprocess": reprocess,
    }
    return new_event(EVENT_TYPE, PRODUCER, payload)
