"""extraction DB 저장 (psycopg 3). 작업 기록·검수 대기열·아웃박스·processed_events를 한 트랜잭션으로 씁니다.

중복 처리 방지: 끝난 처리(다시 하지 않을 상태)만 processed_events에 넣습니다. WAITING_SOURCE·FAILED는 넣지 않아 다시 처리할 수 있습니다.
processed_events를 **트랜잭션 맨 앞에서** 넣고, 이미 있으면(같은 이벤트를 다른 처리가 먼저 끝냄) 아무것도 쓰지 않고 DuplicateEvent를 냅니다.
예전에는 맨 끝에 on conflict do nothing으로 넣어, 중복 수신된 같은 이벤트가 작업·아웃박스를 한 번 더 써서 완료 이벤트가 두 번 나갔습니다(검토 2026-10-16).

버전 순서: 같은 원본(rawPostId)은 공고 단위 잠금(pg_advisory_xact_lock)으로 줄 세우고, 더 새 버전이 이미 발행됐으면
늦게 끝난 옛 버전 결과는 발행하지 않고 SUPERSEDED로 남깁니다. 검수 승인도 같은 이유로 막습니다(옛 자격 조건이 새 것을 덮지 않게).

검수 대기 건 대체(2026-10-23, 검토 의견, migrations/V202610231800__extraction_review_superseded.sql):
  새 버전의 결과를 **발행할 때**(save의 COMPLETED·PARTIAL·IN_REVIEW, 검수 승인) 같은 원본의 더 낮은 버전 PENDING 검수를 SUPERSEDED로 바꿉니다.
  발행 여부를 기준으로 한 까닭: 옛 버전 승인을 막는 기준(_newer_published)과 같아야 '승인은 막혔는데 대기열에는 남은' 건이 생기지 않습니다.
  발행하지 않는 결과(INTAKE_REVIEW·WAITING_SOURCE·FAILED 등)는 옛 버전 승인이 아직 가능하므로 대체하지 않습니다(다시 처리해 발행되면 그때 대체).
  같은 버전을 다시 처리한 것은 대체하지 않습니다(버전이 더 높을 때만).
  정정공고: 수집 이벤트의 kind가 CORRECTION이고 supersedesPostId가 원 공고를 가리키면, 정정공고를 발행할 때 원 공고의 PENDING 검수(모든 버전)도 대체합니다.
  단 원 공고가 공개된 적(COMPLETED·PARTIAL·APPROVED 작업)이 있을 때만입니다: api는 원 공고가 공개돼야 정정을 반영하는데(PARENT_NOT_PUBLISHED),
  검수 대기뿐인 원 공고의 검수를 대체하면 승인할 길이 막혀 원 공고·정정 둘 다 영영 공개되지 않았어요(2026-11-10 재검토).
  후속 안내(FOLLOW_UP)는 원 공고의 자격 조건을 바꾸지 않아 대체하지 않습니다.
  대체는 새 결과 저장·발행과 같은 트랜잭션의 UPDATE(status = 'PENDING' 조건)라 여러 번 해도 같고, 공고 단위 잠금을
  원본·원 공고 ID 순서대로 잡아 같은 공고의 승인·반려와 차례로 처리됩니다(먼저 대체되면 승인·반려는 대체한 버전을 알려 주며 거절).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from mujuthaek_extraction import extraction_stats
from mujuthaek_extraction.cost_alert import monthly_costs
from mujuthaek_extraction.intake.adapter import PDF_TEXT_DOCUMENT_ID, TEXT_LED_NAME
from mujuthaek_extraction.pipeline import Outcome
from mujuthaek_extraction.verify.verifier import DROPPED_VALUE_CODES
from mujuthaek_platform import outbox
from mujuthaek_platform.ids import uuid7

log = logging.getLogger(__name__)
REVIEW_STATUSES = {"IN_REVIEW", "INTAKE_REVIEW"}
COMPLETED = "COMPLETED"  # 모두 통과해 발행. 버린 값 표시가 있으면 검수 대기열에도 넣습니다(공개 유지)
PARTIAL = "PARTIAL"  # 부분 게시: 이미 발행했고, 보류 항목은 사람이 확인해 승인할 수 있게 검수 목록에도 넣습니다(게시를 막지 않음)
SUPERSEDED = "SUPERSEDED"
JUDGMENT_NAMESPACE = uuid.UUID("5b0c8f9e-2f0a-4f41-9d7e-3f1c2a6b9d10")  # 창업지원 판정 틀 처리 기록 ID를 만드는 이름공간(고정값)


def _judgment_keys(raw_event: dict[str, Any], *, with_version: bool) -> list[str]:
    """판정 틀 처리 기록 ID: 수집 eventId에서 하나, with_version이면 정책·버전에서 하나 더(재처리 이벤트는 버전 기록을 보지 않음)."""
    keys = []
    source = _uuid_or_none(raw_event.get("eventId"))
    if source:
        keys.append(str(uuid.uuid5(JUDGMENT_NAMESPACE, source)))
    payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
    policy, version = _uuid_or_none(payload.get("rawPolicyId")), payload.get("version")
    if with_version and policy and isinstance(version, int) and not payload.get("reprocess"):
        keys.append(str(uuid.uuid5(JUDGMENT_NAMESPACE, f"{policy}/v{version}")))
    return keys


def _claim_judgment(cur, raw_event: dict[str, Any]) -> bool:
    """정책 수집 이벤트의 처리 기록을 남깁니다. 같은 수집 이벤트를 이미 처리했으면 False(판정 틀·혜택 정제 공통)."""
    keys = _judgment_keys(raw_event, with_version=False)
    if keys:
        claimed = cur.execute(
            "insert into processed_events (event_id, event_type) values (%s, %s) on conflict do nothing returning event_id",
            (keys[0], "startup-judgment"),
        ).fetchone()
        if claimed is None:
            return False
    for key in _judgment_keys(raw_event, with_version=True)[len(keys) :]:  # 정책·버전 기록(재처리로 다시 와도 오류 없이)
        cur.execute("insert into processed_events (event_id, event_type) values (%s, %s) on conflict do nothing", (key, "startup-judgment"))
    return True


def _insert_benefit_result(cur, event: dict[str, Any], origin: str, source_payload: Any) -> str:
    payload = event["payload"]
    result_id = str(uuid7())
    cur.execute(
        "insert into benefit_results (id, raw_policy_id, raw_version, source_code, policy_id, title, event_id, payload, source_payload, origin)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            result_id,
            payload["rawPolicyId"],
            payload["version"],
            payload["sourceCode"],
            payload["policyId"],
            payload["source"]["title"],
            event["eventId"],
            Jsonb(payload),
            Jsonb(source_payload) if isinstance(source_payload, dict) else None,
            origin,
        ),
    )
    return result_id


def _refresh_reported_review(cur, result_id: str, payload: dict[str, Any]) -> bool:
    """같은 정책에 회원 제보로 연(opened_by가 있는) 대기 검수가 있으면, 대체하지 않고 그 검수를 새 결과로 갱신합니다.
    api의 제보는 이 검수 ID를 가리키므로 ID가 바뀌면 처리 중이던 제보가 끊겨요(2026-10-25 검토). 사유는 앞선 것과 새 것을 합칩니다."""
    row = cur.execute(
        "select id, reasons from benefit_reviews where raw_policy_id = %s and status = 'PENDING' and opened_by is not null order by created_at desc limit 1",
        (payload["rawPolicyId"],),
    ).fetchone()
    if row is None:
        return False
    reasons = list(dict.fromkeys([*(row[1] or []), *payload["quality"]["reviewReasons"]]))
    cur.execute(
        "update benefit_reviews set result_id = %s, raw_version = %s, reasons = %s where id = %s",
        (result_id, payload["version"], Jsonb(reasons), row[0]),
    )
    cur.execute(  # 제보 검수 말고 남은 대기 건은 쓸모가 없음
        "update benefit_reviews set status = 'SUPERSEDED', decided_at = now() where raw_policy_id = %s and status = 'PENDING' and id <> %s",
        (payload["rawPolicyId"], row[0]),
    )
    return True


# 같은 출처에 같은 정책이 또 있음(중복 의심, 2026-10-28 사용자 결정 A안). 출처에 같은 사업이 두 번 올라오는 일이 있어 검수에 올려요(지우지 않음)
DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
_NORMALIZED = "regexp_replace(lower({}), '[[:space:][:punct:]·ㆍ「」『』]', '', 'g')"


def _duplicate_benefit(cur, payload: dict[str, Any]) -> bool:
    """같은 출처 · 다른 정책 번호 · 같은 제목(띄어쓰기·기호 무시) · 같은 기관 · 같은 지역 코드인 결과가 이미 있는지.
    지자체마다 같은 이름(「청년 월세 지원」)을 쓰는 일이 많아 기관과 지역까지 같아야 중복으로 봅니다."""
    source = payload.get("source") or {}
    row = cur.execute(
        "select 1 from benefit_results where source_code = %s and policy_id <> %s"
        f" and {_NORMALIZED.format('title')} = {_NORMALIZED.format('%s')}"
        " and coalesce(payload->'source'->>'agency', '') = %s"
        " and array(select jsonb_array_elements_text(coalesce(payload->'source'->'regionCodes', '[]')) order by 1) = %s::text[]"
        " limit 1",
        (payload["sourceCode"], payload["policyId"], source.get("title") or "", source.get("agency") or "", sorted(source.get("regionCodes") or [])),
    ).fetchone()
    return row is not None


def _open_benefit_review(cur, result_id: str, payload: dict[str, Any], reasons: list[str], opened_by: str | None, note: str | None) -> str:
    """같은 정책의 앞선 대기 건을 대체(SUPERSEDED)하고 새 대기 건을 엽니다."""
    cur.execute(
        "update benefit_reviews set status = 'SUPERSEDED', decided_at = now() where raw_policy_id = %s and status = 'PENDING'",
        (payload["rawPolicyId"],),
    )
    review_id = str(uuid7())
    cur.execute(
        "insert into benefit_reviews (id, result_id, raw_policy_id, raw_version, reasons, opened_by, note) values (%s, %s, %s, %s, %s, %s, %s)",
        (review_id, result_id, payload["rawPolicyId"], payload["version"], Jsonb(reasons), opened_by, note),
    )
    return review_id


class DuplicateEvent(Exception):
    """같은 이벤트를 다른 처리가 이미 끝냈습니다. 아무것도 저장하지 않았습니다."""


def _lock_notice(cur, *raw_post_ids: str | None) -> None:
    """공고 단위 잠금. 여러 개면 ID 순서대로 잡아 서로 기다리다 멈추지 않게 합니다(정정공고는 자기 원본과 원 공고 둘)."""
    for raw_post_id in sorted({str(i) for i in raw_post_ids if i}):
        cur.execute("select pg_advisory_xact_lock(hashtext(%s))", (raw_post_id,))


def _corrected_post(payload: dict[str, Any]) -> str | None:
    """정정공고(kind CORRECTION)가 고친 원 공고의 rawPostId. 정정공고가 아니거나 자기 자신을 가리키면 None."""
    if payload.get("kind") != "CORRECTION":
        return None
    target = _uuid_or_none(payload.get("supersedesPostId"))
    return target if target and target != _uuid_or_none(payload.get("rawPostId")) else None


_SUPERSEDE_SQL = (
    "update review_queue r set status = 'SUPERSEDED', decided_at = now(), note = %(note)s, superseded_by_job_id = %(job)s,"
    " superseded_by_raw_post_id = %(post)s, superseded_by_version = %(version)s"
    " from extraction_jobs j where j.id = r.job_id and r.status = 'PENDING' and j.raw_post_id = %(target)s and j.id <> %(job)s"
    " and (%(below)s::int is null or j.raw_version < %(below)s::int)"
)


# 정정공고가 원 공고 검수를 대체하는 조건: 원 공고가 공개된 적이 있음(위 모듈 설명)
_SUPERSEDE_CORRECTED_SQL = _SUPERSEDE_SQL + (
    " and exists (select 1 from extraction_jobs p where p.raw_post_id = %(target)s and p.status in ('COMPLETED', 'PARTIAL', 'APPROVED'))"
)


def _supersede_pending(cur, job_id: str, raw_post_id: str | None, raw_version: Any, corrected_post: str | None) -> int:
    """job_id가 발행한 결과로 의미가 없어진 PENDING 검수를 SUPERSEDED로 바꾸고 바꾼 수를 돌려줍니다. 발행과 같은 트랜잭션에서 부릅니다.
    같은 원본의 더 낮은 버전, 정정공고면 원 공고의 모든 버전이 대상입니다."""
    if not raw_post_id or not isinstance(raw_version, int):
        return 0
    common = {"job": job_id, "post": raw_post_id, "version": raw_version}
    cur.execute(_SUPERSEDE_SQL, {**common, "target": raw_post_id, "below": raw_version, "note": f"v{raw_version} 발행으로 대체됨"})
    count = cur.rowcount
    if corrected_post:
        note = f"정정공고({raw_post_id} v{raw_version}) 발행으로 대체됨"
        cur.execute(_SUPERSEDE_CORRECTED_SQL, {**common, "target": corrected_post, "below": None, "note": note})
        count += cur.rowcount
    if count:
        log.info("이전 검수 대기 건을 대체됨으로 정리", extra={"jobId": job_id, "rawPostId": raw_post_id, "rawVersion": raw_version, "superseded": count})
    return count


def superseded_message(review_post_id: Any, by_post_id: Any, by_version: Any, by_job_id: Any) -> str:
    """대체된 검수를 승인·반려하려 할 때 알려 줄 문구(대체한 버전·작업)."""
    if by_post_id is not None and str(by_post_id) != str(review_post_id):
        return f"정정공고({by_post_id} v{by_version}, 작업 {by_job_id})가 발행되어 대체된 검수입니다. 정정공고를 검수하세요."
    return f"v{by_version}(작업 {by_job_id})이 발행되어 대체된 검수입니다. 새 버전을 검수하세요."


def _not_pending(cur, job_id: str) -> LookupError:
    """승인·반려할 수 없는 까닭. 대체된 건이면 대체한 버전을 알려 줍니다."""
    row = cur.execute(
        "select r.status, j.raw_post_id, r.superseded_by_raw_post_id, r.superseded_by_version, r.superseded_by_job_id"
        " from review_queue r join extraction_jobs j on j.id = r.job_id where r.job_id = %s",
        (job_id,),
    ).fetchone()
    if row and row[0] == SUPERSEDED:
        return LookupError(superseded_message(*row[1:]))
    return LookupError("대기 중인 검수가 아닙니다.")


def _superseded_by(job_id: Any, raw_post_id: Any, version: Any) -> dict[str, Any] | None:
    """대체한 작업·공고·버전(대체되지 않았으면 None)."""
    if job_id is None:
        return None
    return {"jobId": str(job_id), "rawPostId": str(raw_post_id) if raw_post_id else None, "version": version}


# 관리자 검수 사유 → 작업 상태 (api AdminReviewService.reason과 같은 규칙: 사람 검수 대기 MUST, 원본 자료 문제 FORMAT, 그 밖 CHECK)
REVIEW_REASON_SQL = {
    "MUST": "j.status = 'IN_REVIEW'",
    "FORMAT": "j.status = 'INTAKE_REVIEW'",
    "CHECK": "j.status not in ('IN_REVIEW', 'INTAKE_REVIEW')",
}


def _review_filter(status: str, reason: str | None, after: tuple[str, str] | None) -> tuple[str, tuple[Any, ...]]:
    """공고 검수 목록·건수의 조건(review_queue r, extraction_jobs j)."""
    where, params = "r.status = %s", (status,)
    if reason is not None:
        where += " and " + REVIEW_REASON_SQL[reason]
    if after is not None:
        where += " and (r.created_at, r.job_id) > (%s::timestamptz, %s::uuid)"
        params += after
    return where, params


def _benefit_review_filter(status: str, reported: bool | None, after: tuple[str, str] | None) -> tuple[str, tuple[Any, ...]]:
    """혜택 검수 목록·건수의 조건(benefit_reviews v)."""
    where, params = "v.status = %s", (status,)
    if reported is not None:
        where += " and (v.opened_by is not null) = %s"
        params += (reported,)
    if after is not None:
        where += " and (v.created_at, v.id) > (%s::timestamptz, %s::uuid)"
        params += after
    return where, params


def _newer_published(cur, raw_post_id: str | None, raw_version: Any) -> bool:
    if not raw_post_id or not isinstance(raw_version, int):
        return False
    row = cur.execute(
        "select 1 from extraction_jobs where raw_post_id = %s and raw_version > %s and completed_event_id is not null limit 1",
        (raw_post_id, raw_version),
    ).fetchone()
    return row is not None


def _held_reasons(candidate: dict[str, Any] | None) -> list[str]:
    """부분 게시에서 보류한 항목의 사유 코드(검수 목록에 보여 줄 값)."""
    held = ((candidate or {}).get("quality") or {}).get("heldItems") or []
    return sorted({code for item in held for code in item.get("codes", [])})


def _dropped_reasons(candidate: dict[str, Any] | None) -> list[str]:
    """AI·원본 값을 비우거나 빼거나 바꾼 표시(verifier.DROPPED_VALUE_CODES)를 「코드 위치」로. 메모(notes)·검수 이슈 어디에 있든 셉니다."""
    quality = (candidate or {}).get("quality") or {}
    found = [i for i in [*(quality.get("notes") or []), *(quality.get("reviewIssues") or [])] if i.get("code") in DROPPED_VALUE_CODES]
    return sorted({f"{i['code']} {i.get('target', '')}".strip() for i in found})


def _payload(raw_event: dict[str, Any]) -> dict[str, Any]:
    payload = raw_event.get("payload")
    return payload if isinstance(payload, dict) else {}


def _uuid_or_none(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


class JobStore:
    """extraction DB에 작업 기록·검수 대기열·아웃박스를 읽고 쓰는 저장소입니다."""

    def __init__(self, conn):
        conn.autocommit = True  # 묶음 쓰기는 with conn.transaction()으로만 합니다 (읽기가 트랜잭션을 열어 두지 않게)
        self.conn = conn

    def already_processed(self, event_id: str) -> bool:
        return self.conn.execute("select 1 from processed_events where event_id = %s", (event_id,)).fetchone() is not None

    def save(self, raw_event: dict[str, Any], outcome: Outcome, run_id: str | None = None) -> str:
        """처리 결과를 저장하고 작업 ID를 돌려줍니다. 발행할 이벤트는 같은 트랜잭션에서 아웃박스에 넣습니다.
        run_id: 이 처리의 비용 장부 ID(model/spend.py). 장부의 비용 줄에 작업 ID를 적어, 저장된 처리의 비용으로 표시합니다."""
        job_id = str(uuid7())
        payload = _payload(raw_event)
        event_id = _uuid_or_none(raw_event.get("eventId"))
        raw_post_id = _uuid_or_none(payload.get("rawPostId"))
        raw_version = payload.get("version") if isinstance(payload.get("version"), int) else None
        status, event, error = outcome.status, outcome.event, outcome.error
        corrected_post = _corrected_post(payload)
        with self.conn.transaction(), self.conn.cursor() as cur:
            _lock_notice(cur, raw_post_id, corrected_post)
            if event_id and not outcome.retryable:
                claimed = cur.execute(
                    "insert into processed_events (event_id, event_type) values (%s, %s) on conflict do nothing returning event_id",
                    (event_id, raw_event.get("eventType") or "unknown"),
                ).fetchone()
                if claimed is None:
                    raise DuplicateEvent(event_id)  # 트랜잭션을 되돌려 작업·아웃박스를 쓰지 않습니다
            if event and _newer_published(cur, raw_post_id, raw_version):
                status, event, error = SUPERSEDED, None, f"더 새 버전이 이미 발행되어 v{raw_version} 결과는 발행하지 않았습니다."
            cur.execute(
                "insert into extraction_jobs (id, event_id, raw_post_id, raw_version, source_code, field, status, model_used, cost_usd,"
                " attempts, ai_responses, pdf_pages, candidate, raw_event, completed_event_id, error, usage)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    job_id,
                    event_id or job_id,  # 형식이 잘못돼 eventId가 없으면 작업 ID로 대신 남깁니다
                    raw_post_id,
                    raw_version,
                    payload.get("sourceCode") if isinstance(payload.get("sourceCode"), str) else None,
                    payload.get("field") if isinstance(payload.get("field"), str) else None,
                    status,
                    outcome.model_used,
                    round(outcome.cost_usd, 4),
                    Jsonb(outcome.attempts),
                    Jsonb(outcome.responses),
                    Jsonb(outcome.pdf_pages),
                    Jsonb(outcome.candidate) if outcome.candidate is not None else None,
                    Jsonb(raw_event),
                    event["eventId"] if event else None,
                    error,
                    Jsonb(outcome.usage),
                ),
            )
            if event:
                outbox.add(cur, event)
            if run_id:
                cur.execute("update extraction_spend set job_id = %s where run_id = %s", (job_id, run_id))
            if status in REVIEW_STATUSES:
                cur.execute("insert into review_queue (job_id, reasons) values (%s, %s)", (job_id, Jsonb(outcome.review_reasons)))
            elif status in (PARTIAL, COMPLETED) and (held := _held_reasons(outcome.candidate) + _dropped_reasons(outcome.candidate)):
                # 보류 항목, 또는 버리거나 바꾼 값이 있으면 공개는 유지하고 사람이 확인하게 검수 대기열에 넣습니다(2026-10-26 공통 검사)
                cur.execute("insert into review_queue (job_id, reasons) values (%s, %s)", (job_id, Jsonb(held)))
            if event:  # 이 버전을 발행함: 옛 버전·정정 전 공고의 대기 검수는 대체됨
                _supersede_pending(cur, job_id, raw_post_id, raw_version, corrected_post)
        return job_id

    def judged(self, raw_event: dict[str, Any]) -> bool:
        """이 수집 이벤트, 또는 같은 정책·버전(재처리가 아니면)으로 판정 틀 이벤트를 이미 넣었는지. AI를 다시 부르지 않게 처리 전에 봅니다
        (리뷰 2026-10-22: 수집기가 같은 버전을 새 eventId로 다시 보내면 AI를 또 불렀음. 공고의 version_published와 같은 규칙)."""
        return any(self.already_processed(key) for key in _judgment_keys(raw_event, with_version=True))

    def save_judgment(self, raw_event: dict[str, Any], event: dict[str, Any]) -> bool:
        """정책 판정 틀 이벤트를 아웃박스에 넣습니다(AI 작업이 아니라 작업 기록은 없음). 같은 수집 이벤트로 이미 넣었으면 False.
        처리 기록은 수집 eventId에서 만든 별도 ID로 남겨, 같은 수집 이벤트를 정책 추출이 따로 처리하는 것과 겹치지 않게 합니다."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            if not _claim_judgment(cur, raw_event):
                return False
            outbox.add(cur, event)
        return True

    # ---- 혜택 정제 결과·검수 (2026-10-25, migrations/V202610251700__extraction_benefit_results_reviews.sql) ----
    def save_benefit(self, raw_event: dict[str, Any], event: dict[str, Any]) -> bool:
        """policy.extracted를 아웃박스에 넣고 결과를 쌓습니다. 확인 필요(needsReview)면 검수 대기로 올리고, 같은 정책의 앞선 대기 건은 대체합니다.
        같은 수집 이벤트로 이미 넣었으면 False(판정 틀과 같은 처리 기록 규칙)."""
        payload = event["payload"]
        with self.conn.transaction(), self.conn.cursor() as cur:
            if not _claim_judgment(cur, raw_event):
                return False
            _lock_notice(cur, payload["rawPolicyId"])
            outbox.add(cur, event)
            result_id = _insert_benefit_result(cur, event, "EXTRACTED", raw_event.get("payload"))
            if _refresh_reported_review(cur, result_id, payload):
                pass  # 제보로 연 검수는 대체하지 않고 새 결과로 갱신해 제보와의 연결을 지켜요
            elif payload["quality"]["needsReview"] or _duplicate_benefit(cur, payload):
                # 중복 의심이면 확인 필요 사유에 더해 검수에 올려요(검수 없이 나갈 결과도 올림)
                duplicate = [DUPLICATE_SUSPECTED] if _duplicate_benefit(cur, payload) else []
                _open_benefit_review(cur, result_id, payload, [*payload["quality"]["reviewReasons"], *duplicate], None, None)
            else:  # 새 결과가 검수 없이 나갔으면 같은 정책의 앞선 대기 건은 쓸모가 없음
                cur.execute(
                    "update benefit_reviews set status = 'SUPERSEDED', decided_at = now() where raw_policy_id = %s and status = 'PENDING'",
                    (payload["rawPolicyId"],),
                )
        return True

    def benefit_review_count(self, status: str = "PENDING", reported: bool | None = None) -> int:
        """그 상태의 혜택 검수 전체 건수(목록은 limit에서 잘리므로 따로 셉니다, 2026-10-25 검토). reported면 정책 제보로 다시 연 건만(false면 그 밖)."""
        where, params = _benefit_review_filter(status, reported, None)
        return int(self.conn.execute(f"select count(*) from benefit_reviews v where {where}", params).fetchone()[0])

    def benefit_reviews(
        self, status: str = "PENDING", limit: int = 50, reported: bool | None = None, after: tuple[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """혜택 검수 목록(오래된 것부터, 같은 시각이면 검수 ID 순). applyEndsOn은 결과의 신청 마감일, reported는 정책 제보로 다시 연 건인지.
        after는 (queuedAt, reviewId) — 이 건 다음부터 이어 받아요(관리자 검수 무한 스크롤, 2026-10-29)."""
        where, params = _benefit_review_filter(status, reported, after)
        rows = self.conn.execute(
            "select v.id, v.raw_policy_id, v.raw_version, r.source_code, r.policy_id, r.title, v.status, v.reasons, v.created_at, v.decided_at,"
            " r.list_apply_end, r.list_relevant, v.opened_by is not null"
            f" from benefit_reviews v join benefit_results r on r.id = v.result_id where {where} order by v.created_at, v.id limit %s",
            (*params, limit),
        ).fetchall()
        keys = ("reviewId", "rawPolicyId", "rawVersion", "sourceCode", "policyId", "title", "reviewStatus", "reasons", "queuedAt", "decidedAt")
        keys += ("applyEndsOn", "relevant", "reported")
        return [{k: (str(v) if k in ("reviewId", "rawPolicyId") else v) for k, v in zip(keys, row, strict=True)} for row in rows]

    def benefit_review(self, review_id: str) -> dict[str, Any] | None:
        """혜택 검수 상세: 결과 payload(조건·지원·일정·근거)와 받은 원본 payload(원문, 다시 발행한 결과면 그 정책의 가장 새 원본)."""
        row = self.conn.execute(
            "select v.id, v.raw_policy_id, v.raw_version, v.status, v.reasons, v.note, v.opened_by, v.created_at, v.decided_at, v.decided_by, v.edits,"
            " r.payload, coalesce(r.source_payload, (select o.source_payload from benefit_results o where o.raw_policy_id = r.raw_policy_id"
            " and o.source_payload is not null order by o.created_at desc limit 1)), r.event_id"
            " from benefit_reviews v join benefit_results r on r.id = v.result_id where v.id = %s",
            (review_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ("reviewId", "rawPolicyId", "rawVersion", "reviewStatus", "reasons", "note", "openedBy", "queuedAt", "decidedAt", "decidedBy", "edits")
        keys += ("payload", "source", "eventId")
        item = dict(zip(keys, row, strict=True))
        for key in ("reviewId", "rawPolicyId", "eventId"):
            item[key] = str(item[key])
        return item

    def decide_benefit(
        self,
        review_id: str,
        decision: str,
        event: dict[str, Any],
        note: str | None,
        reviewer: str | None,
        edits: list[dict[str, Any]] | None = None,
    ) -> None:
        """대기 중인 혜택 검수를 승인(APPROVED)·반려(REJECTED)하고 고친 결과 이벤트를 발행합니다. 대기 건이 아니거나
        더 새 버전 결과가 이미 나갔으면 LookupError(트랜잭션째 되돌림)."""
        payload = event["payload"]
        with self.conn.transaction(), self.conn.cursor() as cur:
            _lock_notice(cur, payload["rawPolicyId"])
            row = cur.execute("select raw_policy_id, raw_version, status from benefit_reviews where id = %s for update", (review_id,)).fetchone()
            if row is None or row[2] != "PENDING":
                raise LookupError(f"대기 중인 검수가 아닙니다({row[2] if row else '없음'}).")
            newer = cur.execute("select 1 from benefit_results where raw_policy_id = %s and raw_version > %s limit 1", (str(row[0]), row[1])).fetchone()
            if newer:
                raise LookupError(f"더 새 버전 결과가 이미 나가 v{row[1]} 검수는 처리할 수 없습니다.")
            outbox.add(cur, event)
            result_id = _insert_benefit_result(cur, event, decision, None)
            cur.execute(
                "update benefit_reviews set status = %s, note = %s, decided_at = now(), decided_by = %s, edits = %s, published_result_id = %s where id = %s",
                (decision, note, reviewer, Jsonb(edits) if edits is not None else None, result_id, review_id),
            )

    def reopen_benefit(self, raw_policy_id: str, reviewer: str | None, note: str | None) -> dict[str, Any] | None:
        """그 정책의 가장 새 결과를 검수 대기로 다시 엽니다(정책 제보로 값을 고칠 때). 이미 대기 건이 있으면 그것을 돌려줍니다.
        결과가 없으면 None."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            _lock_notice(cur, raw_policy_id)
            pending = cur.execute("select id from benefit_reviews where raw_policy_id = %s and status = 'PENDING'", (raw_policy_id,)).fetchone()
            if pending:
                return {"reviewId": str(pending[0]), "reopened": False}
            latest = cur.execute(
                "select id, payload from benefit_results where raw_policy_id = %s order by created_at desc limit 1", (raw_policy_id,)
            ).fetchone()
            if latest is None:
                return None
            reasons = list(dict.fromkeys([*latest[1]["quality"].get("reviewReasons", []), "REPORTED"]))
            review_id = _open_benefit_review(cur, str(latest[0]), latest[1], reasons, reviewer, note)
        return {"reviewId": review_id, "reopened": True}

    def benefit(self, raw_policy_id: str) -> dict[str, Any] | None:
        """그 정책의 가장 새 결과 요약(정책 제보가 들어온 정책이 있는지 볼 때). 없으면 None."""
        row = self.conn.execute(
            "select raw_policy_id, raw_version, source_code, policy_id, title, (payload->>'relevant')::boolean, payload->>'field'"
            " from benefit_results where raw_policy_id = %s order by created_at desc limit 1",
            (raw_policy_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ("rawPolicyId", "rawVersion", "sourceCode", "policyId", "title", "relevant", "field")
        return {k: (str(v) if k == "rawPolicyId" else v) for k, v in zip(keys, row, strict=True)}

    # ---- 원본 버전 처리권 (migrations/V202610201200__extraction_claims.sql) ----
    def claim(self, raw_post_id: str, raw_version: int, owner: str, lease_seconds: float) -> bool:
        """처리권을 잡습니다. 아무도 없거나 기한이 지났으면 잡고 True, 다른 처리가 기한 안에 잡고 있으면 False."""
        row = self.conn.execute(
            "insert into extraction_claims (raw_post_id, raw_version, owner, expires_at)"
            " values (%s, %s, %s, now() + make_interval(secs => %s))"
            " on conflict (raw_post_id, raw_version) do update set owner = excluded.owner, expires_at = excluded.expires_at, created_at = now()"
            " where extraction_claims.expires_at < now() or extraction_claims.owner = excluded.owner"
            " returning owner",
            (raw_post_id, raw_version, owner, lease_seconds),
        ).fetchone()
        return row is not None

    def renew_claim(self, raw_post_id: str, raw_version: int, owner: str, lease_seconds: float) -> bool:
        """처리 중에 기한을 늘립니다. 이미 다른 처리에 넘어갔으면 False."""
        updated = self.conn.execute(
            "update extraction_claims set expires_at = now() + make_interval(secs => %s) where raw_post_id = %s and raw_version = %s and owner = %s",
            (lease_seconds, raw_post_id, raw_version, owner),
        ).rowcount
        return updated == 1

    def release_claim(self, raw_post_id: str, raw_version: int, owner: str) -> None:
        self.conn.execute("delete from extraction_claims where raw_post_id = %s and raw_version = %s and owner = %s", (raw_post_id, raw_version, owner))

    # ---- 검수 ----
    def review_count(self, status: str = "PENDING", reason: str | None = None) -> int:
        """그 상태의 공고 검수 전체 건수(목록은 limit에서 잘리므로 따로 셉니다, 2026-10-25 검토). reason은 MUST·CHECK·FORMAT(REVIEW_REASON_SQL)."""
        where, params = _review_filter(status, reason, None)
        return int(self.conn.execute(f"select count(*) from review_queue r join extraction_jobs j on j.id = r.job_id where {where}", params).fetchone()[0])

    def reviews(self, status: str = "PENDING", limit: int = 50, reason: str | None = None, after: tuple[str, str] | None = None) -> list[dict[str, Any]]:
        """그 상태의 검수 목록(오래된 것부터, 같은 시각이면 작업 ID 순). 기본 PENDING에는 대체된(SUPERSEDED) 건이 없습니다.
        applyEndsOn은 후보의 신청(APPLICATION) 일정 중 가장 이른 끝 날짜예요(관리자 개요의 「마감이 가까운 검수 대기」, 2026-10-25).
        reason은 관리자 사유(MUST·CHECK·FORMAT), after는 (queuedAt, jobId) — 이 건 다음부터 이어 받아요(관리자 검수 무한 스크롤, 2026-10-29)."""
        where, params = _review_filter(status, reason, after)
        rows = self.conn.execute(
            # 제목·원문 제목·신청 마감일은 저장할 때 채워 둔 칸에서 읽어요(건마다 큰 JSON을 풀지 않게, V202610301300)
            "select j.id, j.raw_post_id, j.raw_version, j.source_code, j.status, r.status, r.reasons, r.created_at, j.list_title,"
            " j.list_source_title, r.decided_at, j.list_apply_ends_on,"
            " r.superseded_by_job_id, r.superseded_by_raw_post_id, r.superseded_by_version"
            f" from review_queue r join extraction_jobs j on j.id = r.job_id where {where} order by r.created_at, r.job_id limit %s",
            (*params, limit),
        ).fetchall()
        keys = ("jobId", "rawPostId", "rawVersion", "sourceCode", "jobStatus", "reviewStatus", "reasons", "queuedAt", "title", "sourceTitle", "decidedAt")
        keys += ("applyEndsOn",)
        items = []
        for row in rows:
            item = {k: (str(v) if k in ("jobId", "rawPostId") and v else v) for k, v in zip(keys, row[:12], strict=True)}
            items.append(item | {"supersededBy": _superseded_by(*row[12:])})
        return items

    def review(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "select j.id, j.status, r.status, r.reasons, r.note, j.candidate, j.raw_event, j.error, j.model_used, j.cost_usd, j.raw_post_id,"
            " r.decided_at, r.created_at, r.decided_by, r.edited, r.edits, r.superseded_by_job_id, r.superseded_by_raw_post_id, r.superseded_by_version"
            " from review_queue r join extraction_jobs j on j.id = r.job_id where j.id = %s",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ("jobId", "jobStatus", "reviewStatus", "reasons", "note", "candidate", "rawEvent", "error", "modelUsed", "costUsd", "rawPostId", "decidedAt")
        keys += ("queuedAt", "decidedBy", "edited", "edits")
        item = dict(zip(keys, row[:16], strict=True))
        item["jobId"] = str(item["jobId"])
        item["rawPostId"] = str(item["rawPostId"]) if item["rawPostId"] else None
        item["costUsd"] = float(item["costUsd"])
        item["supersededBy"] = _superseded_by(*row[16:])
        item["history"] = self.review_history(item["jobId"])
        return item

    def job_usage(self, job_id: str) -> dict[str, Any] | None:
        """작업 하나의 측정 기록(관리자 「추출 과정 보기」). 검수 대기에 오르지 않은 작업도 볼 수 있게 작업 표에서 바로 읽습니다."""
        # pdfs·textLed: 근거 id를 원문 PDF 쪽으로 여는 대응표가 기록에 없는 예전 작업용(trace_view). PDF 구조는 크니 차례·이름·쪽 수만 꺼내요
        row = self.conn.execute(
            "select id, status, raw_post_id, model_used, cost_usd, usage,"
            " (select coalesce(jsonb_agg(jsonb_build_object('id', p->'documentId', 'name', p->'name', 'pageCount', p->'pageCount')), '[]'::jsonb)"
            "  from jsonb_array_elements(case when jsonb_typeof(pdf_pages) = 'array' then pdf_pages else '[]'::jsonb end) p),"
            " exists (select 1 from jsonb_array_elements(case when jsonb_typeof(candidate->'documents') = 'array' then candidate->'documents'"
            "  else '[]'::jsonb end) d where d->>'id' = %s and d->>'name' like %s)"
            " from extraction_jobs where id = %s",
            (PDF_TEXT_DOCUMENT_ID, TEXT_LED_NAME + "%", job_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "jobId": str(row[0]),
            "jobStatus": row[1],
            "rawPostId": str(row[2]) if row[2] else None,
            "modelUsed": row[3],
            "costUsd": float(row[4] or 0),
            "usage": row[5],
            "pdfs": row[6] or [],
            "textLed": bool(row[7]),
        }

    def job_files(self, job_id: str) -> list[dict[str, Any]] | None:
        """작업 원본(수집 이벤트)의 첨부 위치: [{documentId, name, fileType, s3Key, sha256}]. 관리자 원문 PDF 보기에서 api가 이 위치로 S3를
        읽어요(문서 ID file-N = files[N-1], intake/adapter.py). 작업이 없으면 None."""
        row = self.conn.execute("select raw_event from extraction_jobs where id = %s", (job_id,)).fetchone()
        if row is None:
            return None
        payload = (row[0] or {}).get("payload") if isinstance(row[0], dict) else None
        files = (payload or {}).get("files") if isinstance(payload, dict) else None
        return [
            {
                "documentId": f"file-{index + 1}",
                "name": file.get("name"),
                "fileType": file.get("fileType"),
                "s3Key": file.get("s3Key"),
                "sha256": file.get("sha256"),
            }
            for index, file in enumerate(files if isinstance(files, list) else [])
            if isinstance(file, dict)
        ]

    def approve(
        self,
        job_id: str,
        candidate: dict[str, Any],
        event: dict[str, Any],
        note: str | None,
        reviewer: str | None = None,
        edited: bool = False,
        edits: list[dict[str, Any]] | None = None,
    ) -> None:
        """대기 중인 검수를 승인하고 고친 후보와 발행할 이벤트를 한 트랜잭션으로 저장합니다.
        reviewer·edited·edits는 처리 기록(관리자 화면, 2026-10-25)입니다. edits는 칸별 수정 [{path, before, after}].
        더 새 버전이 이미 발행됐거나 대기 중인 검수가 아니면 LookupError를 냅니다."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            job = cur.execute("select raw_post_id, raw_version, raw_event->'payload' from extraction_jobs where id = %s", (job_id,)).fetchone()
            raw_post_id = str(job[0]) if job and job[0] else None
            corrected_post = _corrected_post(job[2] if job and isinstance(job[2], dict) else {})
            _lock_notice(cur, raw_post_id, corrected_post)
            cur.execute(
                "update review_queue set status = 'APPROVED', note = %s, decided_at = now(), decided_by = %s, edited = %s, edits = %s"
                " where job_id = %s and status = 'PENDING'",
                (note, reviewer, edited, Jsonb(edits) if edits is not None else None, job_id),
            )
            if cur.rowcount != 1:
                raise _not_pending(cur, job_id)  # 대체된 건이면 대체한 버전을 알려 줌
            if job and _newer_published(cur, raw_post_id, job[1]):  # 아직 대체되지 않은 옛 버전(예외로 트랜잭션째 되돌림)
                raise LookupError(f"더 새 버전이 이미 발행되어 v{job[1]} 결과는 승인할 수 없습니다. 새 버전을 검수하세요.")
            cur.execute(
                "update extraction_jobs set status = 'APPROVED', candidate = %s, completed_event_id = %s, updated_at = now() where id = %s",
                (Jsonb(candidate), event["eventId"], job_id),
            )
            outbox.add(cur, event)
            _supersede_pending(cur, job_id, raw_post_id, job[1] if job else None, corrected_post)  # 승인으로 이 버전을 발행함

    def reject(self, job_id: str, note: str | None, reviewer: str | None = None) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "update review_queue set status = 'REJECTED', note = %s, decided_at = now(), decided_by = %s where job_id = %s and status = 'PENDING'",
                (note, reviewer, job_id),
            )
            if cur.rowcount != 1:
                raise _not_pending(cur, job_id)

    def reopen(self, raw_post_id: str, reviewer: str | None = None, note: str | None = None) -> dict[str, Any] | None:
        """그 원본의 가장 새로 발행한 결과를 검수 대기로 다시 엽니다(관리자 화면: 사용자 제보로 공고 값을 고칠 때, 2026-10-25).
        이미 대기 중이면 그대로 돌려줍니다. 앞선 처리 기록은 review_history로 옮깁니다. 발행한 결과가 없으면 None."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            job = cur.execute(
                "select id from extraction_jobs where raw_post_id = %s and completed_event_id is not null and candidate is not null"
                " order by raw_version desc, updated_at desc limit 1 for update",
                (raw_post_id,),
            ).fetchone()
            if job is None:
                return None
            job_id = job[0]
            row = cur.execute("select status from review_queue where job_id = %s for update", (job_id,)).fetchone()
            if row is not None and row[0] == "PENDING":
                return {"jobId": str(job_id), "reviewStatus": "PENDING", "reopened": False}
            if row is None:
                cur.execute("insert into review_queue (job_id, reasons) values (%s, %s)", (job_id, Jsonb(["USER_REPORT"])))
            else:
                cur.execute(
                    "insert into review_history (job_id, status, reasons, note, created_at, decided_at, decided_by, edited, edits, reopened_by, reopen_note)"
                    " select job_id, status, reasons, note, created_at, decided_at, decided_by, edited, edits, %s, %s from review_queue where job_id = %s",
                    (reviewer, note, job_id),
                )
                cur.execute(
                    "update review_queue set status = 'PENDING',"
                    " reasons = (case when reasons ? 'USER_REPORT' then reasons else reasons || '[\"USER_REPORT\"]'::jsonb end),"
                    " note = null, created_at = now(), decided_at = null, decided_by = null, edited = false, edits = null,"
                    " superseded_by_job_id = null, superseded_by_raw_post_id = null, superseded_by_version = null where job_id = %s",
                    (job_id,),
                )
            return {"jobId": str(job_id), "reviewStatus": "PENDING", "reopened": True}

    def review_history(self, job_id: str) -> list[dict[str, Any]]:
        """다시 열기 전의 처리 기록(오래된 것부터)."""
        rows = self.conn.execute(
            "select status, note, decided_at, decided_by, edited, edits, archived_at, reopened_by, reopen_note"
            " from review_history where job_id = %s order by id",
            (job_id,),
        ).fetchall()
        keys = ("reviewStatus", "note", "decidedAt", "decidedBy", "edited", "edits", "reopenedAt", "reopenedBy", "reopenNote")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def review_stats(self, days: int = 7) -> dict[str, Any]:
        """관리자 개요의 처리 통계: 최근 days일과 오늘(한국 시간)의 그대로 승인·고쳐서 승인·반려 수와, 들어와서 처리되기까지 걸린 시간의 중앙값(분).
        대체(SUPERSEDED)는 사람이 처리한 것이 아니라 세지 않습니다. 제보로 다시 열어 review_history로 옮긴 앞선 처리도 셉니다
        (2026-10-25 검토: 예전엔 다시 열면 그 전 승인·반려가 통계에서 사라졌음). 혜택 정책 검수(benefit_reviews)의 처리도 같이 셉니다
        (2026-10-26: 관리자 개요가 공고 검수만 세어 혜택 승인이 빠졌음). 혜택은 칸별 수정(edits)이 있으면 고쳐서 승인입니다."""

        def counts(since_sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
            row = self.conn.execute(
                "select count(*) filter (where status = 'APPROVED' and not edited), count(*) filter (where status = 'APPROVED' and edited),"
                " count(*) filter (where status = 'REJECTED'),"
                " percentile_cont(0.5) within group (order by extract(epoch from decided_at - created_at))"
                " from (select status, edited, created_at, decided_at from review_queue"
                " union all select status, edited, created_at, decided_at from review_history"
                " union all select status, coalesce(jsonb_typeof(edits) = 'array' and jsonb_array_length(edits) > 0, false),"
                " created_at, decided_at from benefit_reviews) d"
                f" where status in ('APPROVED', 'REJECTED') and decided_at >= {since_sql}",
                params,
            ).fetchone()
            median = None if row[3] is None else round(float(row[3]) / 60)
            return {"approved": row[0], "editedApproved": row[1], "rejected": row[2], "medianMinutes": median}

        recent = counts("now() - make_interval(days => %s)", (days,))
        today = counts("(date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul')", ())
        return {"days": days, "recent": recent, "today": today}

    def review_activity(self, days: int = 30, limit: int = 300) -> list[dict[str, Any]]:
        """관리자 「처리 기록」: 최근 days일 검수 처리(승인·고쳐서 승인·반려)와 다시 열기를 최근 순으로.
        공고 검수(review_queue, 제보로 다시 열어 review_history로 옮긴 앞선 처리 포함)와 혜택 검수(benefit_reviews)를 같이 봐요.
        대체(SUPERSEDED)는 사람이 처리한 게 아니라 뺍니다. who는 api 서버가 보낸 처리한 관리자(로그인 계정 ID)."""
        rows = self.conn.execute(
            "select kind, id, title, action, at, who, note from ("
            # 공고 검수 처리 (지금 상태)
            " select 'NOTICE' kind, j.id::text id, coalesce(j.list_title, j.list_source_title) title,"
            " case when r.status = 'REJECTED' then 'REJECTED' when r.edited then 'EDITED_APPROVED' else 'APPROVED' end action,"
            " r.decided_at at, r.decided_by who, r.note note"
            " from review_queue r join extraction_jobs j on j.id = r.job_id"
            " where r.status in ('APPROVED', 'REJECTED') and r.decided_at is not null"
            # 다시 열기 전에 했던 처리
            " union all select 'NOTICE', j.id::text, coalesce(j.list_title, j.list_source_title),"
            " case when h.status = 'REJECTED' then 'REJECTED' when h.edited then 'EDITED_APPROVED' else 'APPROVED' end,"
            " h.decided_at, h.decided_by, h.note"
            " from review_history h join extraction_jobs j on j.id = h.job_id"
            " where h.status in ('APPROVED', 'REJECTED') and h.decided_at is not null"
            # 다시 열기
            " union all select 'NOTICE', j.id::text, coalesce(j.list_title, j.list_source_title),"
            " 'REOPENED', h.archived_at, h.reopened_by, h.reopen_note"
            " from review_history h join extraction_jobs j on j.id = h.job_id where h.reopened_by is not null"
            # 혜택 검수 처리
            " union all select 'BENEFIT', v.id::text, r.title,"
            " case when v.status = 'REJECTED' then 'REJECTED'"
            " when jsonb_typeof(v.edits) = 'array' and jsonb_array_length(v.edits) > 0 then 'EDITED_APPROVED' else 'APPROVED' end,"
            " v.decided_at, v.decided_by, v.note"
            " from benefit_reviews v join benefit_results r on r.id = v.result_id"
            " where v.status in ('APPROVED', 'REJECTED') and v.decided_at is not null"
            # 혜택 검수 다시 열기 (정책 제보)
            " union all select 'BENEFIT', v.id::text, r.title, 'REOPENED', v.created_at, v.opened_by, null"
            " from benefit_reviews v join benefit_results r on r.id = v.result_id where v.opened_by is not null"
            ") a where at >= now() - make_interval(days => %s) order by at desc, id limit %s",
            (days, limit),
        ).fetchall()
        keys = ("kind", "id", "title", "action", "at", "by", "note")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    # ---- 비용 ----
    def monthly_costs(self, month: str | None = None, budget_usd: float | None = None) -> dict[str, Any]:
        """그 달의 분야별 유료 AI 호출 수·비용(cost_alert.monthly_costs)."""
        return monthly_costs(self.conn, month, budget_usd)

    def extraction_stats(self, days: int) -> dict[str, Any]:
        """관리자 「추출 비용·품질」: 최근 days일(한국 시간)의 처리 공고·상태·비용·담당별 비중·멈춤 (extraction_stats.collect)."""
        return extraction_stats.collect(self.conn, days)

    # ---- 다시 처리 ----
    def spent_before(self, raw_event: dict[str, Any]) -> float:
        """같은 원본 버전(rawPostId + version)의 앞선 처리 중 다시 처리 대상(FAILED·WAITING_SOURCE)으로 끝난 것들이 쓴 유료 비용.
        원본 ID나 버전이 없으면 같은 eventId로 셉니다. 끝난 처리(완료·검수 등) 뒤 일부러 다시 돌리는 경우는 새 예산입니다."""
        payload = _payload(raw_event)
        raw_post_id = _uuid_or_none(payload.get("rawPostId"))
        raw_version = payload.get("version") if isinstance(payload.get("version"), int) else None
        if raw_post_id and raw_version is not None:
            where, params = "raw_post_id = %s and raw_version = %s", (raw_post_id, raw_version)
        elif event_id := _uuid_or_none(raw_event.get("eventId")):
            where, params = "event_id = %s", (event_id,)
        else:
            return 0.0
        row = self.conn.execute(
            f"select coalesce(sum(cost_usd), 0) from extraction_jobs where {where} and status in ('FAILED', 'WAITING_SOURCE')", params
        ).fetchone()
        # 저장 전에 중단된 처리(프로세스 종료 등)의 비용: 작업 기록이 없어 위 합계에 빠지므로 비용 장부에서 셉니다(2026-10-21).
        # 응답을 못 받은 호출은 최악 비용으로 셉니다
        orphan = self.conn.execute(
            f"select coalesce(sum(coalesce(cost_usd, reserved_usd)), 0) from extraction_spend where {where} and job_id is null", params
        ).fetchone()
        return (float(row[0]) if row else 0.0) + (float(orphan[0]) if orphan else 0.0)

    # ---- 중단 반복·같은 버전 다시 받음 (2026-10-21) ----
    def record_start(self, event_id: str) -> None:
        """처리를 시작했다고 적습니다. 저장 전에 중단되면 시작 횟수가 작업 수보다 많아집니다."""
        self.conn.execute("insert into extraction_starts (event_id) values (%s)", (event_id,))

    def interrupted_runs(self, event_id: str) -> int:
        """이 이벤트를 시작했는데 결과를 저장하지 못한 횟수(프로세스 종료·메모리 부족 등)."""
        row = self.conn.execute(
            "select (select count(*) from extraction_starts where event_id = %s) - (select count(*) from extraction_jobs where event_id = %s)",
            (event_id, event_id),
        ).fetchone()
        return max(int(row[0]), 0) if row else 0

    def version_published(self, raw_post_id: str, raw_version: int) -> bool:
        """같은 원본 버전의 결과를 이미 발행했는지(다른 eventId로 같은 버전이 다시 온 경우를 걸러 비용을 다시 쓰지 않게)."""
        row = self.conn.execute(
            "select 1 from extraction_jobs where raw_post_id = %s and raw_version = %s and completed_event_id is not null limit 1",
            (raw_post_id, raw_version),
        ).fetchone()
        return row is not None

    def mark_processed(self, event_id: str, event_type: str) -> None:
        self.conn.execute("insert into processed_events (event_id, event_type) values (%s, %s) on conflict do nothing", (event_id, event_type))

    def retryable_events(self, limit: int = 20, max_attempts: int | None = None, base_delay_seconds: float = 0) -> list[dict[str, Any]]:
        """마지막 처리가 WAITING_SOURCE·FAILED이고 아직 끝나지 않은(processed_events에 없는) 이벤트. 오래 기다린 것부터.

        max_attempts: 이만큼 처리한 이벤트는 더 하지 않습니다(계속 실패하는 공고에 비용이 계속 들지 않게).
        base_delay_seconds: 마지막 처리 뒤 base × 2^(처리 횟수-1)초가 지난 것만(5분 → 10분 → 20분 …).
        예전엔 표 전체(raw_event 포함)를 읽고 행마다 조회해 느렸고, 순서도 eventId 순이라 한도 20이 임의였습니다."""
        rows = self.conn.execute(
            "select raw_event from ("
            " select distinct on (event_id) event_id, status, raw_event, created_at,"
            " count(*) over (partition by event_id) as attempts"
            " from extraction_jobs order by event_id, created_at desc"
            ") last where status in ('WAITING_SOURCE', 'FAILED')"
            " and not exists (select 1 from processed_events p where p.event_id = last.event_id)"
            " and (%s::int is null or attempts < %s::int)"
            " and created_at <= now() - make_interval(secs => %s * power(2, attempts - 1))"
            " order by created_at limit %s",
            (max_attempts, max_attempts, base_delay_seconds, limit),
        ).fetchall()
        return [row[0] for row in rows]
