"""JobStore를 실제 PostgreSQL에서 확인합니다. EXTRACTION_TEST_DB_URL이 있을 때만 돌고, 임시 스키마에 migrations/를 적용해 씁니다.

EXTRACTION_TEST_DB_URL=postgresql://extraction_app:extraction-pass@127.0.0.1:5432/extraction uv run pytest tests/test_store_postgres.py
"""

import json
import os
import uuid
from pathlib import Path

import pytest
from test_pipeline import answers, new_event, raw_event, run
from test_worker_parts import pending_item

from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.pipeline import Outcome
from mujuthaek_extraction.review_api import ReviewService
from mujuthaek_extraction.store import JobStore

DB_URL = os.getenv("EXTRACTION_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="EXTRACTION_TEST_DB_URL이 없어 실제 DB 검사를 건너뜁니다")
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@pytest.fixture
def store():
    import psycopg

    schema = "test_" + uuid.uuid4().hex[:12]
    conn = psycopg.connect(DB_URL, autocommit=True)
    conn.execute(f"create schema {schema}")
    conn.execute(f"set search_path to {schema}")
    for path in sorted(MIGRATIONS.glob("V*.sql")):
        conn.execute(path.read_text(encoding="utf-8"))
    try:
        yield JobStore(conn)
    finally:
        conn.execute(f"drop schema {schema} cascade")
        conn.close()


def count(store, sql):
    return store.conn.execute(sql).fetchone()[0]


def test_completed_job_writes_outbox_and_processed_event_together(store):
    event = raw_event()
    outcome = run(event, NoticeModels(RecordedModel(answers()), None))
    job_id = store.save(event, outcome)
    assert count(store, "select count(*) from outbox") == 1
    assert store.already_processed(event["eventId"])
    assert count(store, "select count(*) from review_queue") == 0
    status, payload = store.conn.execute("select status, payload->'payload'->>'reviewStatus' from extraction_jobs, outbox").fetchone()
    assert (status, payload) == ("COMPLETED", "AUTO_PASSED") and job_id


def test_failed_job_is_not_marked_processed_and_can_be_retried(store):
    event = raw_event()
    store.save(event, Outcome("FAILED", error="모델 연결 실패"))
    assert not store.already_processed(event["eventId"])
    assert [e["eventId"] for e in store.retryable_events()] == [event["eventId"]]
    assert count(store, "select count(*) from outbox") == 0


def test_review_flow_approve_publishes_again(store):
    item = pending_item()
    outcome = Outcome("IN_REVIEW", event=None, candidate=item["candidate"], review_reasons=["EXCEPTION_SUSPECTED /eligibility/2"])
    job_id = store.save(item["rawEvent"], outcome)
    assert [r["jobId"] for r in store.reviews("PENDING")] == [job_id]

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    service = ReviewService(lambda: Session(), new_event)
    status, body = service.approve(job_id, {"note": "확인"})
    assert status == 200 and body["reviewStatus"] == "APPROVED"
    assert count(store, "select count(*) from outbox where payload->'payload'->>'reviewStatus' = 'APPROVED'") == 1
    assert store.review(job_id)["reviewStatus"] == "APPROVED"
    assert service.approve(job_id, {})[0] == 409


def test_partial_job_is_published_and_also_listed_for_optional_review(store):
    from test_worker_parts import partial_item

    item, _ = partial_item()
    outcome = Outcome("PARTIAL", event=None, candidate=item["candidate"])
    job_id = store.save(item["rawEvent"], outcome)
    [listed] = store.reviews("PENDING")
    assert listed["jobId"] == job_id and listed["jobStatus"] == "PARTIAL"
    assert listed["reasons"] == ["EVIDENCE_SCATTERED", "EXCEPTION_SUSPECTED"]


def test_claim_is_exclusive_until_released_or_expired(store):
    post = "01929a3e-0000-7000-8000-000000000001"
    assert store.claim(post, 1, "a", 300)
    assert not store.claim(post, 1, "b", 300)  # 다른 처리는 기한 안에 잡을 수 없음
    assert store.claim(post, 2, "b", 300)  # 다른 원본 버전은 따로
    assert store.renew_claim(post, 1, "a", 300) and not store.renew_claim(post, 1, "b", 300)
    store.release_claim(post, 1, "a")
    assert store.claim(post, 1, "b", 300)
    store.conn.execute("update extraction_claims set expires_at = now() - interval '1 second' where owner = 'b'")
    assert store.claim(post, 1, "c", 300)  # 기한이 지나면(워커가 죽음) 이어받음
    assert not store.renew_claim(post, 1, "b", 300)


def test_same_event_saved_twice_publishes_once(store):
    # 검토 지적: 중복 수신된 같은 이벤트가 작업·아웃박스를 한 번 더 써서 완료 이벤트가 두 번 나가던 것
    from mujuthaek_extraction.store import DuplicateEvent

    event = raw_event()
    outcome = run(event, NoticeModels(RecordedModel(answers()), None))
    store.save(event, outcome)
    with pytest.raises(DuplicateEvent):
        store.save(event, outcome)
    assert count(store, "select count(*) from outbox") == 1
    assert count(store, "select count(*) from extraction_jobs") == 1


def versioned(version):
    import copy

    event = copy.deepcopy(raw_event())
    event["eventId"] = str(uuid.uuid4())
    event["payload"]["version"] = version
    return event


def test_older_version_finishing_after_newer_one_is_not_published(store):
    # 검토 지적: v1이 늦게 끝나거나 다시 처리되면 v2 뒤에 발행되어 옛 자격 조건이 새 것을 덮던 것
    outcome = run(raw_event(), NoticeModels(RecordedModel(answers()), None))
    store.save(versioned(2), outcome)
    old_job = store.save(versioned(1), outcome)
    assert count(store, "select count(*) from outbox") == 1
    status = store.conn.execute("select status from extraction_jobs where id = %s", (old_job,)).fetchone()[0]
    assert status == "SUPERSEDED"


def test_approving_old_version_after_newer_one_published_is_refused(store):
    item = pending_item()
    old = versioned(1) | {"payload": {**item["rawEvent"]["payload"], "version": 1}}
    job_id = store.save(old, Outcome("IN_REVIEW", event=None, candidate=item["candidate"], review_reasons=["X /eligibility/0"]))
    store.save(versioned(2) | {"payload": {**item["rawEvent"]["payload"], "version": 2}}, run(raw_event(), NoticeModels(RecordedModel(answers()), None)))

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    status, body = ReviewService(lambda: Session(), new_event).approve(job_id, {})
    assert status == 409 and "새 버전" in body["error"]
    assert count(store, "select count(*) from outbox") == 1


def test_retry_waits_longer_each_time_and_stops_after_max_attempts(store):
    # 검토 지적: 자료 대기·실패는 사람이 retry를 돌려야만 다시 처리됐고, 횟수 제한·간격도 없었음
    event = raw_event()
    store.save(event, Outcome("WAITING_SOURCE", error="PDF 아직 없음"))
    assert [e["eventId"] for e in store.retryable_events(base_delay_seconds=0)] == [event["eventId"]]
    assert store.retryable_events(base_delay_seconds=3600) == []  # 1시간 기다려야 하는데 방금 처리함
    store.save(event, Outcome("WAITING_SOURCE", error="PDF 아직 없음"))
    store.conn.execute("update extraction_jobs set created_at = now() - interval '90 minutes'")
    assert store.retryable_events(base_delay_seconds=3600) == []  # 2번째라 2시간
    store.conn.execute("update extraction_jobs set created_at = now() - interval '3 hours'")
    assert len(store.retryable_events(base_delay_seconds=3600)) == 1
    assert store.retryable_events(max_attempts=2) == []  # 2번 처리했으면 더 하지 않음


def test_usage_summary_is_saved_with_the_job(store):
    event = raw_event()
    outcome = run(event, NoticeModels(RecordedModel(answers()), None))
    job_id = store.save(event, outcome)
    calls, stages = store.conn.execute("select usage->'totals'->>'calls', usage->'stages' from extraction_jobs where id = %s", (job_id,)).fetchone()
    assert int(calls) == len(outcome.attempts) and "sections" in stages


def test_spent_before_sums_only_unfinished_attempts_of_same_raw_version(store):
    # 다시 처리할 때마다 새 예산이라 실패가 반복되면 상한의 여러 배를 쓸 수 있던 것 (2026-10-20)
    event = raw_event()
    store.save(event, Outcome("FAILED", cost_usd=0.12, error="x"))
    store.save(event, Outcome("FAILED", cost_usd=0.05, error="x"))
    store.save(versioned(2), Outcome("FAILED", cost_usd=0.3, error="x"))  # 다른 버전은 따로
    assert store.spent_before(event) == pytest.approx(0.17)
    assert store.spent_before(versioned(3)) == 0.0


def test_call_cache_table_stores_reuses_and_purges(store):
    from mujuthaek_extraction.model.call_cache import PostgresCallCache

    cache = PostgresCallCache(store.conn)
    cache.put("k1", "gpt-6-luna", "structure", {"rawText": "{}", "modelId": "m", "stopReason": "END"}, {"input_tokens": 3})
    cache.put("k1", "gpt-6-luna", "structure", {"rawText": "다른 값"}, None)  # 같은 열쇠는 처음 것을 둡니다
    assert cache.get("k1")["rawText"] == "{}" and cache.get("없음") is None
    store.conn.execute("update extraction_call_cache set created_at = now() - interval '91 days'")
    cache.put("k2", "local", "documents", {"rawText": "{}"}, None)
    assert cache.purge(90) == 1 and cache.get("k1") is None and cache.get("k2") is not None


def test_startup_judgment_is_saved_once_and_does_not_mark_the_collected_event_processed(store):
    raw = {"eventId": str(uuid.uuid4())}
    event = new_event("extraction.completed", "extraction", {"rawPostId": str(uuid.uuid4())})
    assert store.save_judgment(raw, event) and not store.save_judgment(raw, event)
    assert count(store, "select count(*) from outbox") == 1
    assert not store.already_processed(raw["eventId"])  # 정책 추출이 같은 수집 이벤트를 따로 처리할 수 있게


def test_same_policy_version_is_judged_once_unless_reprocessed(store):
    policy = str(uuid.uuid4())
    first = {"eventId": str(uuid.uuid4()), "payload": {"rawPolicyId": policy, "version": 2}}
    again = {"eventId": str(uuid.uuid4()), "payload": {"rawPolicyId": policy, "version": 2}}
    redo = {"eventId": str(uuid.uuid4()), "payload": {"rawPolicyId": policy, "version": 2, "reprocess": True}}
    assert not store.judged(first)
    assert store.save_judgment(first, new_event("extraction.completed", "extraction", {"rawPostId": policy}))
    assert store.judged(again) and not store.judged(redo)


def test_same_notice_event_delivered_ten_times_is_processed_once_and_reprocess_runs_again(store):
    # 요구 2-01: 같은 raw.notice.collected 10번 → AI 처리 1번·완료 이벤트 1건. 재처리 표시(reprocess=true)는 새 eventId로 오면
    # 같은 원본 버전이어도 다시 처리하고(worker._handle의 version_published 건너뜀), 그 재처리 이벤트도 10번에 1번만 처리합니다
    import copy

    from test_worker_parts import bare_processor

    calls = []

    def ai_run(event):
        calls.append(event["eventId"])
        outcome = run(event, NoticeModels(RecordedModel(answers()), None))
        outcome.event = outcome.event | {"eventId": str(uuid.uuid4())}  # 시험용 new_event는 eventId가 고정이라 아웃박스에서 겹치지 않게
        return outcome

    processor = bare_processor(ai_run)
    event = raw_event()
    for _ in range(10):
        processor.handle(store, copy.deepcopy(event))
    assert calls == [event["eventId"]]
    assert count(store, "select count(*) from outbox") == 1 and count(store, "select count(*) from extraction_jobs") == 1

    resent = versioned(1)  # 수집기가 같은 버전을 새 eventId로 다시 보냄(재처리 표시 없음): AI를 부르지 않음
    processor.handle(store, resent)
    assert len(calls) == 1 and store.already_processed(resent["eventId"])

    redo = versioned(1)
    redo["payload"]["reprocess"] = True
    for _ in range(10):
        processor.handle(store, copy.deepcopy(redo))
    assert calls == [event["eventId"], redo["eventId"]]
    assert count(store, "select count(*) from outbox") == 2


def test_same_policy_event_delivered_ten_times_makes_one_judgment_and_reprocess_runs_again(store):
    # 요구 2-01: 같은 raw.policy.collected 10번 → AI 읽기 1번·판정 틀 이벤트 1건. 같은 정책·버전을 새 eventId로 다시 보내도 읽지 않고,
    # 재처리 표시(reprocess=true)면 새 eventId 하나당 한 번 다시 만듭니다(store._judgment_keys)
    import copy
    import json

    from test_policy_judgment import REGIONS, TOUR_ANSWER, tour

    from mujuthaek_extraction.rules.policy.reading import CALL_NAME
    from mujuthaek_extraction.worker import judge_policy

    model = RecordedModel({CALL_NAME: [json.dumps(TOUR_ANSWER)] * 2})
    payload = tour() | {"rawPolicyId": str(uuid.uuid4()), "version": 3}
    collected = {"eventId": str(uuid.uuid4()), "eventType": "raw.policy.collected", "payload": payload}
    made = [judge_policy(store, copy.deepcopy(collected), model, REGIONS) for _ in range(10)]
    assert sum(1 for m in made if m) == 1 and len(model.requests) == 1
    assert count(store, "select count(*) from outbox") == 1

    resent = collected | {"eventId": str(uuid.uuid4())}
    assert judge_policy(store, resent, model, REGIONS) is None and len(model.requests) == 1

    redo = {"eventId": str(uuid.uuid4()), "eventType": "raw.policy.collected", "payload": payload | {"reprocess": True}}
    made = [judge_policy(store, copy.deepcopy(redo), model, REGIONS) for _ in range(10)]
    assert sum(1 for m in made if m) == 1 and len(model.requests) == 2
    assert count(store, "select count(*) from outbox") == 2


def spend(store, field, usd, *, settled=True, job_id=None, ago="0 seconds"):
    store.conn.execute(
        "insert into extraction_spend (id, run_id, field, job_id, model, reserved_usd, cost_usd, created_at)"
        " values (%s, %s, %s, %s, 'gpt-6-luna', %s, %s, now() - %s::interval)",
        (str(uuid.uuid4()), str(uuid.uuid4()), field, job_id, usd if not settled else usd * 2, usd if settled else None, ago),
    )


def test_monthly_costs_are_counted_per_field_and_served_by_the_review_api(store):
    # 요구 2-10: 분야별 유료 호출 수·비용. 응답 못 받은 호출은 최악 비용, 분야 칸이 없던 옛 줄은 작업 기록의 분야로
    spend(store, "HOUSING", 0.1)
    spend(store, "HOUSING", 0.3, settled=False)
    spend(store, "STARTUP_SUPPORT", 0.05)
    job_id = store.save(raw_event(field="BUSINESS_SPACE"), Outcome("FAILED", error="x"))
    spend(store, None, 0.2, job_id=job_id)
    spend(store, None, 0.01)
    spend(store, "HOUSING", 9.0, ago="70 days")  # 지난달 이전은 빠짐

    costs = store.monthly_costs(budget_usd=1.0)
    assert {f["field"]: (f["paidCalls"], f["costUsd"]) for f in costs["fields"]} == {
        "BUSINESS_SPACE": (1, 0.2),
        "HOUSING": (2, 0.4),
        "STARTUP_SUPPORT": (1, 0.05),
        "UNKNOWN": (1, 0.01),
    }
    assert costs["paidCalls"] == 5 and costs["costUsd"] == pytest.approx(0.66) and costs["budgetRatio"] == pytest.approx(0.66)
    assert store.monthly_costs("2001-01")["fields"] == []

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    service = ReviewService(lambda: Session(), new_event, 1.0)
    status, body = service.costs(None)
    assert status == 200 and body["month"] == costs["month"] and body["budgetUsd"] == 1.0
    assert service.costs("2026-13")[0] == 400


def test_ledger_writes_the_field_and_crossing_80_percent_sends_one_slack_message_per_month(store):
    # 요구 2-10: 월 상한 80%에서 한 번만. 보낸 기록이 DB에 있어 워커를 다시 시작해도(새 CostAlert) 다시 보내지 않음
    import psycopg

    from mujuthaek_extraction.cost_alert import CostAlert
    from mujuthaek_extraction.model.spend import SpendLedger

    schema = store.conn.execute("select current_schema()").fetchone()[0]
    sent = []

    def ledger(alert):
        conn = psycopg.connect(DB_URL, autocommit=True)
        conn.execute(f"set search_path to {schema}")
        return SpendLedger(conn, daily_usd=10, monthly_usd=1.0, scope={"field": "SPACE_RECRUITMENT"}, alert=alert)

    first = ledger(CostAlert(1.0, sent.append))
    first.settle(first.reserve("gpt-6-luna", 0.5), 0.7)
    first.close()  # 70%: 보내지 않음
    assert sent == [] and store.monthly_costs()["fields"] == [{"field": "SPACE_RECRUITMENT", "paidCalls": 1, "costUsd": 0.7}]

    def failing(text):
        raise RuntimeError("슬랙 장애")

    second = ledger(CostAlert(1.0, failing))
    second.settle(second.reserve("gpt-6-luna", 0.1), 0.1)
    second.close()  # 80%를 넘었지만 전송 실패: 기록을 되돌려 다음에 다시 보냄(추출은 계속)
    assert count(store, "select count(*) from extraction_alerts") == 0

    third = ledger(CostAlert(1.0, sent.append))
    third.settle(third.reserve("gpt-6-luna", 0.1), 0.05)
    third.close()
    assert len(sent) == 1 and "SPACE_RECRUITMENT" in sent[0] and "85%" in sent[0]

    for alert in (CostAlert(1.0, sent.append), CostAlert(1.0, sent.append)):  # 다시 시작한 워커·다른 워커
        again = ledger(alert)
        again.settle(again.reserve("gpt-6-luna", 0.01), 0.01)
        again.close()
    assert len(sent) == 1 and count(store, "select count(*) from extraction_alerts") == 1


# ---- 검수 대기 건 대체 (2026-10-23, 검토 의견: 새 버전이 발행되면 옛 대기 건은 SUPERSEDED) ----
def published(reason="x"):
    """발행하는 결과(IN_REVIEW도 발행함). 이벤트 ID는 매번 새로."""
    event = {**new_event("extraction.completed", "extraction", {}), "eventId": str(uuid.uuid4())}
    return Outcome("IN_REVIEW", event=event, candidate=pending_item()["candidate"], review_reasons=[f"{reason} /eligibility/0"])


def held(reason="x"):
    """발행하지 않고 검수 대기열에만 오르는 결과."""
    return Outcome("IN_REVIEW", event=None, candidate=pending_item()["candidate"], review_reasons=[f"{reason} /eligibility/0"])


def session_of(store):
    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    return lambda: Session()


def notice_event(version, raw_post_id=None, **payload):
    event = versioned(version)
    if raw_post_id:
        event["payload"]["rawPostId"] = raw_post_id
    event["payload"].update(payload)
    return event


def review_status(store, job_id):
    return store.conn.execute("select status from review_queue where job_id = %s", (job_id,)).fetchone()[0]


def test_publishing_newer_version_supersedes_older_pending_review(store):
    v1 = store.save(notice_event(1), held("v1"))
    assert [r["jobId"] for r in store.reviews("PENDING")] == [v1]
    v2 = store.save(notice_event(2), published("v2"))

    assert [r["jobId"] for r in store.reviews("PENDING")] == [v2]  # 기본 목록에는 새 버전만
    [old] = store.reviews("SUPERSEDED")
    assert old["jobId"] == v1 and old["decidedAt"] is not None
    assert old["supersededBy"] == {"jobId": v2, "rawPostId": old["rawPostId"], "version": 2}
    assert store.review(v1)["note"] == "v2 발행으로 대체됨" and store.review(v2)["supersededBy"] is None

    service = ReviewService(session_of(store), new_event)
    status, body = service.approve(v1, {})
    assert status == 409 and "v2" in body["error"] and v2 in body["error"] and body["supersededBy"]["version"] == 2
    status, body = service.reject(v1, {"note": "늦은 반려"})
    assert status == 409 and "v2" in body["error"] and "새 버전" in body["error"]
    assert review_status(store, v1) == "SUPERSEDED" and store.review(v1)["note"] == "v2 발행으로 대체됨"
    assert service.list("SUPERSEDED")[0] == 200 and service.list("NOPE")[0] == 400
    # 목록은 limit에서 잘려도 total은 그 상태의 전체 건수(2026-10-25 검토)
    status, body = service.list("SUPERSEDED", "1")
    assert status == 200 and len(body["items"]) <= 1 and body["total"] >= len(body["items"])
    assert service.list("PENDING", "0")[0] == 400 and service.list("PENDING", "x")[0] == 400
    assert count(store, "select count(*) from outbox") == 1  # v2 발행 한 번뿐(대체된 v1은 발행 없음)

    # 여러 번 해도 같음: v3 발행은 v2만 대체하고 이미 대체된 v1의 기록(대체한 버전)은 그대로
    v3 = store.save(notice_event(3), published("v3"))
    assert [r["jobId"] for r in store.reviews("PENDING")] == [v3]
    assert {r["jobId"]: r["supersededBy"]["version"] for r in store.reviews("SUPERSEDED")} == {v1: 2, v2: 3}


def test_same_version_reprocess_or_unpublished_newer_version_does_not_supersede(store):
    v1 = store.save(notice_event(1), held("v1"))
    store.save(notice_event(1, reprocess=True), published("v1 다시"))  # 같은 버전 재처리 발행: 대체 아님
    store.save(notice_event(2), Outcome("FAILED", error="모델 연결 실패"))  # 새 버전이 발행되지 않음
    store.save(notice_event(2), Outcome("INTAKE_REVIEW", review_reasons=["SOURCE_MISMATCH /files/0"]))
    assert review_status(store, v1) == "PENDING"  # v1 승인은 아직 막히지 않았으므로 대기열에 남음
    other = store.save(notice_event(5, str(uuid.uuid4())), published("다른 공고"))
    assert review_status(store, v1) == "PENDING" and review_status(store, other) == "PENDING"


def test_approving_newer_version_supersedes_older_pending_review(store):
    # 새 버전이 발행되지 않은 채 검수에 올랐다가 승인으로 발행되면 그때 옛 대기 건을 대체
    v1 = store.save(notice_event(1), held("v1"))
    v2 = store.save(notice_event(2), held("v2"))
    assert review_status(store, v1) == "PENDING"
    event = {**new_event("extraction.completed", "extraction", {}), "eventId": str(uuid.uuid4())}
    store.approve(v2, pending_item()["candidate"], event, "확인")
    assert review_status(store, v2) == "APPROVED" and review_status(store, v1) == "SUPERSEDED"
    assert store.review(v1)["supersededBy"]["jobId"] == v2


def test_correction_notice_supersedes_pending_reviews_of_the_original_notice(store):
    original = str(uuid.uuid4())
    store.save(notice_event(1, original), Outcome("COMPLETED", event=published().event, candidate=pending_item()["candidate"]))  # 공개된 원 공고
    o1 = store.save(notice_event(2, original), held("원 공고 v2"))
    o2 = store.save(notice_event(3, original), held("원 공고 v3"))
    follow_up = notice_event(1, str(uuid.uuid4()), kind="FOLLOW_UP", supersedesPostId=original)
    store.save(follow_up, published("후속 안내"))
    assert review_status(store, o1) == review_status(store, o2) == "PENDING"  # 후속 안내는 원 공고를 바꾸지 않음

    correction_post = str(uuid.uuid4())
    correction = store.save(notice_event(1, correction_post, kind="CORRECTION", supersedesPostId=original), published("정정"))
    assert review_status(store, o1) == review_status(store, o2) == "SUPERSEDED"
    assert store.review(o2)["supersededBy"] == {"jobId": correction, "rawPostId": correction_post, "version": 1}
    status, body = ReviewService(session_of(store), new_event).approve(o2, {})
    assert status == 409 and "정정공고" in body["error"] and correction_post in body["error"]
    assert review_status(store, correction) == "PENDING"


def test_a_correction_does_not_supersede_the_review_of_an_original_never_published(store):
    # 2026-11-10 재검토: api는 원 공고가 공개돼야 정정을 반영하는데, 검수 대기뿐인 원 공고의 검수를 대체해 승인할 길이 막혀 둘 다 공개되지 않았음
    original = str(uuid.uuid4())
    waiting = store.save(notice_event(1, original), held("원 공고 v1"))
    correction_post = str(uuid.uuid4())
    store.save(notice_event(1, correction_post, kind="CORRECTION", supersedesPostId=original), published("정정"))
    assert review_status(store, waiting) == "PENDING"  # 원 공고를 승인해 공개하면 api가 기다리던 정정을 이어서 반영해요


def test_supersede_and_approve_of_the_same_notice_are_serialized(store):
    # 공고 단위 잠금: 대체하는 트랜잭션이 끝날 때까지 옛 버전 승인은 기다렸다가, 대체된 것을 보고 거절
    import threading
    import time

    import psycopg

    from mujuthaek_extraction.store import _lock_notice, _supersede_pending

    post = str(uuid.uuid4())
    v1 = store.save(notice_event(1, post), held("v1"))
    v2 = store.save(notice_event(2, post), held("v2"))
    schema = store.conn.execute("select current_schema()").fetchone()[0]
    other_conn = psycopg.connect(DB_URL, autocommit=True)
    other_conn.execute(f"set search_path to {schema}")
    other, results = JobStore(other_conn), []

    def approve_old():
        event = {**new_event("extraction.completed", "extraction", {}), "eventId": str(uuid.uuid4())}
        try:
            other.approve(v1, pending_item()["candidate"], event, None)
            results.append("approved")
        except LookupError as error:
            results.append(str(error))

    try:
        with store.conn.transaction(), store.conn.cursor() as cur:
            _lock_notice(cur, post)
            worker = threading.Thread(target=approve_old)
            worker.start()
            time.sleep(0.5)
            assert worker.is_alive()  # 잠금을 기다리는 중
            assert _supersede_pending(cur, v2, post, 2, None) == 1
        worker.join(10)
    finally:
        other_conn.close()
    assert results and "v2" in results[0] and "대체" in results[0]
    assert review_status(store, v1) == "SUPERSEDED" and count(store, "select count(*) from outbox") == 0


def test_migration_supersedes_pending_reviews_already_behind_a_published_version():
    # 이 변경 전에 쌓인 건: 새 버전이 이미 발행된 옛 대기 건(승인은 원래 막힘)을 마이그레이션이 대체 처리
    import psycopg

    schema = "test_" + uuid.uuid4().hex[:12]
    conn = psycopg.connect(DB_URL, autocommit=True)
    conn.execute(f"create schema {schema}")
    conn.execute(f"set search_path to {schema}")
    paths = sorted(MIGRATIONS.glob("V*.sql"))
    target = next(p for p in paths if p.name.startswith("V202610231800__"))
    try:
        for path in paths[: paths.index(target)]:
            conn.execute(path.read_text(encoding="utf-8"))
        post, other = str(uuid.uuid4()), str(uuid.uuid4())
        jobs = {name: str(uuid.uuid4()) for name in ("v1", "v2", "v3", "lone")}
        rows = [(jobs["v1"], post, 1, None), (jobs["v2"], post, 2, str(uuid.uuid4())), (jobs["v3"], post, 3, None), (jobs["lone"], other, 1, None)]
        for job_id, raw_post_id, version, completed in rows:
            conn.execute(
                "insert into extraction_jobs (id, event_id, raw_post_id, raw_version, status, raw_event, completed_event_id)"
                " values (%s, %s, %s, %s, 'IN_REVIEW', '{}', %s)",
                (job_id, str(uuid.uuid4()), raw_post_id, version, completed),
            )
        for name in ("v1", "v3", "lone"):
            conn.execute("insert into review_queue (job_id) values (%s)", (jobs[name],))
        conn.execute(target.read_text(encoding="utf-8"))
        result = dict(conn.execute("select job_id::text, status || ':' || coalesce(superseded_by_version::text, '') from review_queue").fetchall())
        assert result == {jobs["v1"]: "SUPERSEDED:2", jobs["v3"]: "PENDING:", jobs["lone"]: "PENDING:"}
    finally:
        conn.execute(f"drop schema {schema} cascade")
        conn.close()


def test_review_record_and_stats(store):
    """관리자 검수 화면(2026-10-25): 누가·고쳐서 승인했는지 남기고, 그대로 승인·고쳐서 승인·반려 수와 처리 시간 중앙값을 셉니다."""
    from test_worker_parts import pending_item

    def queued(post_suffix):
        item = pending_item()
        event = raw_event() | {"eventId": str(uuid.uuid4())}
        event["payload"] = event["payload"] | {"rawPostId": f"01929a3e-0000-7000-8000-00000000{post_suffix}"}
        item["candidate"]["input"]["rawPostId"] = event["payload"]["rawPostId"]
        for ref in item["candidate"]["sourceReferences"]:
            ref["rawPostId"] = event["payload"]["rawPostId"]
        return store.save(event, Outcome("IN_REVIEW", candidate=item["candidate"], review_reasons=["EXCEPTION_SUSPECTED /eligibility/2"]))

    plain, edited, rejected = queued("0a01"), queued("0a02"), queued("0a03")
    store.conn.execute("update review_queue set created_at = now() - interval '30 minutes'")

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    def fresh_event(*args):
        return new_event(*args) | {"eventId": str(uuid.uuid4())}  # 승인마다 다른 이벤트(시험용 new_event는 ID가 고정)

    service = ReviewService(lambda: Session(), fresh_event)
    assert service.approve(plain, {"reviewer": "admin:1"})[0] == 200
    status, body = service.approve(edited, {"reviewer": "admin:2", "edits": [{"path": "/eligibility/0/description", "value": "가상 설명 고침"}]})
    assert status == 200, body
    assert service.reject(rejected, {"reviewer": "admin:1", "note": "[중복 공고]"})[0] == 200

    detail = store.review(edited)
    assert detail["decidedBy"] == "admin:2" and detail["edited"] is True
    assert detail["edits"][0]["path"] == "/eligibility/0/description" and detail["edits"][0]["after"] == "가상 설명 고침"
    assert detail["queuedAt"] is not None
    assert store.review(plain)["edited"] is False and store.review(rejected)["decidedBy"] == "admin:1"

    stats = store.review_stats(7)
    assert stats["recent"] == {"approved": 1, "editedApproved": 1, "rejected": 1, "medianMinutes": 30}
    assert stats["today"]["approved"] + stats["today"]["editedApproved"] + stats["today"]["rejected"] in (0, 3)  # 한국 자정 직후면 0


def test_review_list_has_earliest_application_end(store):
    """관리자 개요의 「마감이 가까운 검수 대기」: 후보의 신청 일정 중 가장 이른 끝 날짜(2026-10-25)."""
    from test_worker_parts import pending_item

    item = pending_item()
    ends = [s["endsAt"]["value"][:10] for s in item["candidate"]["schedules"] if "APPLICATION" in s["kinds"] and (s.get("endsAt") or {}).get("value")]
    store.save(item["rawEvent"], Outcome("IN_REVIEW", candidate=item["candidate"], review_reasons=[]))
    [listed] = store.reviews("PENDING")
    assert listed["applyEndsOn"] == (min(ends) if ends else None)
    assert ends  # 시험 자료에 신청 마감이 있어야 의미가 있음


def test_published_result_can_be_reopened_for_review_and_fixed_again(store):
    """사용자 제보로 공고 값을 고칠 때(2026-10-25): 발행한 결과를 다시 열고, 앞선 처리 기록은 history로 남기고, 칸별 수정으로 다시 발행합니다."""
    from test_worker_parts import pending_item

    item = pending_item()
    post = item["rawEvent"]["payload"]["rawPostId"]
    job_id = store.save(item["rawEvent"], Outcome("IN_REVIEW", candidate=item["candidate"], review_reasons=["EXCEPTION_SUSPECTED /eligibility/2"]))

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    def fresh_event(*args):
        return new_event(*args) | {"eventId": str(uuid.uuid4())}

    service = ReviewService(lambda: Session(), fresh_event)
    assert store.reopen(post) is None  # 아직 발행 전이면 다시 열 결과가 없음
    assert service.approve(job_id, {"reviewer": "admin:1", "note": "처음 승인"})[0] == 200
    approved_before = store.review_stats(7)["recent"]["approved"]

    status, opened = service.reopen({"rawPostId": post, "reviewer": "admin:2", "note": "공고 제보: 보증금"})
    assert status == 200 and opened == {"jobId": job_id, "reviewStatus": "PENDING", "reopened": True}
    assert service.reopen({"rawPostId": post})[1]["reopened"] is False  # 이미 대기 중
    # 다시 열어도 앞선 승인은 통계에 남아요(기록으로 옮겨져도 셈)
    assert store.review_stats(7)["recent"]["approved"] == approved_before
    detail = store.review(job_id)
    assert detail["reviewStatus"] == "PENDING" and "USER_REPORT" in detail["reasons"]
    # 처리 기록: 다시 열기 전 승인과 다시 열기가 최근 순으로, 처리한 관리자와 함께
    activity = [(x["kind"], x["action"], x["by"]) for x in store.review_activity(30, 10) if x["id"] == job_id]
    assert activity == [("NOTICE", "REOPENED", "admin:2"), ("NOTICE", "APPROVED", "admin:1")]
    assert [(h["reviewStatus"], h["decidedBy"], h["reopenedBy"], h["reopenNote"]) for h in detail["history"]] == [
        ("APPROVED", "admin:1", "admin:2", "공고 제보: 보증금")
    ]

    status, body = service.approve(job_id, {"reviewer": "admin:2", "edits": [{"path": "/eligibility/0/description", "value": "제보로 고친 설명"}]})
    assert status == 200, body
    assert count(store, "select count(*) from outbox where payload->'payload'->>'reviewStatus' = 'APPROVED'") == 2
    assert store.review(job_id)["candidate"]["eligibility"][0]["description"] == "제보로 고친 설명"


def benefit_event(policy, version, *, needs_review, title="가상 청년 월세", **changes):
    """혜택 정제 결과 이벤트(policy.extracted). needs_review면 근거가 원문에 없는 조건을 넣어 확인 필요로 만듭니다."""
    from test_benefit import REGIONS, answer, condition, payload

    from mujuthaek_extraction.benefit.build import build_payload
    from mujuthaek_extraction.benefit.codes import rules_for
    from mujuthaek_extraction.benefit.reading import BenefitReading

    conditions = [condition("HOMELESS", "원문에 없는 문장입니다", basis="PERSON")] if needs_review else []
    data = payload(rawPolicyId=policy, version=version, title=title, **changes)
    built = build_payload(data, BenefitReading(answer(conditions), False, "recorded"), rules_for("youth", data["record"], data["text"]), REGIONS)
    raw = {"eventId": str(uuid.uuid4()), "payload": data}
    return raw, {**new_event("policy.extracted", "extraction", built), "eventId": str(uuid.uuid4())}


def benefit_service(store):
    from contextlib import contextmanager

    @contextmanager
    def session():
        yield store

    return ReviewService(session, lambda kind, producer, body: {**new_event(kind, producer, body), "eventId": str(uuid.uuid4())})


def test_benefit_needing_review_is_saved_listed_and_approved_with_edits(store):
    policy = str(uuid.uuid4())
    raw, event = benefit_event(policy, 1, needs_review=True)
    assert event["payload"]["quality"]["needsReview"] is True
    assert store.save_benefit(raw, event) and not store.save_benefit(raw, event)
    assert count(store, "select count(*) from outbox") == 1 and count(store, "select count(*) from benefit_results") == 1
    [item] = store.benefit_reviews()
    assert (item["rawPolicyId"], item["title"], item["reasons"]) == (policy, "가상 청년 월세", ["EVIDENCE_NOT_FOUND", "NO_DOCUMENT"])
    detail = store.benefit_review(item["reviewId"])
    assert detail["source"]["text"].startswith("제목: 가상 청년") and detail["payload"]["rawPolicyId"] == policy

    service = benefit_service(store)
    status, body = service.benefit_decide(item["reviewId"], "APPROVED", {"edits": [{"path": "/summary", "value": "고친 요약"}], "reviewer": "admin-1"})
    assert status == 200, body
    published = store.conn.execute("select payload->'payload' from outbox order by created_at desc limit 1").fetchone()[0]
    assert published["summary"] == "고친 요약" and published["reprocess"] is True
    assert published["quality"]["needsReview"] is False and published["quality"]["reviewReasons"] == ["NO_DOCUMENT"]
    assert published["quality"]["reviewed"] is True  # 같은 버전이라도 api가 검수 결과로 받아요
    assert store.benefit_review(item["reviewId"])["edits"] == [{"path": "/summary", "before": event["payload"]["summary"], "after": "고친 요약"}]
    # 관리자 개요 처리 통계에 혜택 검수도 들어가요(칸을 고쳤으니 고쳐서 승인)
    assert store.review_stats(7)["recent"]["editedApproved"] == 1
    assert service.benefit_decide(item["reviewId"], "APPROVED", {})[0] == 409
    assert service.benefit_decide(str(uuid.uuid4()), "APPROVED", {})[0] == 404


def test_same_benefit_posted_twice_by_the_source_goes_to_review_as_duplicate(store):
    # 2026-10-28 사용자 결정 A안: 출처에 같은 정책이 번호만 달리 두 번 올라오면(실측 온통청년) 지우지 않고 검수에 「중복 의심」으로 올려요
    first = str(uuid.uuid4())
    store.save_benefit(*benefit_event(first, 1, needs_review=False))
    assert store.benefit_reviews() == []
    second = str(uuid.uuid4())
    store.save_benefit(*benefit_event(second, 1, needs_review=False, title="가상 청년  월세!", policyId="20261021000000000002"))
    [item] = store.benefit_reviews()
    assert item["rawPolicyId"] == second and item["reasons"][-1] == "DUPLICATE_SUSPECTED"
    # 다른 지자체가 같은 이름을 쓰면 중복이 아니에요(기관·지역이 달라야 다른 정책)
    third = str(uuid.uuid4())
    store.save_benefit(*benefit_event(third, 1, needs_review=False, policyId="20261021000000000003", agency="다른군 청년팀", regionCodes=["47250"]))
    assert [i["rawPolicyId"] for i in store.benefit_reviews()] == [second]


def test_benefit_edit_cannot_touch_the_source_or_quality(store):
    raw, event = benefit_event(str(uuid.uuid4()), 1, needs_review=True)
    store.save_benefit(raw, event)
    [item] = store.benefit_reviews()
    status, body = benefit_service(store).benefit_decide(item["reviewId"], "APPROVED", {"edits": [{"path": "/rawPolicyId", "value": "x"}]})
    assert status == 422 and "고칠 수 없는" in body["error"]


def test_reported_benefit_is_reopened_and_rejection_hides_it(store):
    policy = str(uuid.uuid4())
    raw, event = benefit_event(policy, 1, needs_review=False)
    store.save_benefit(raw, event)
    assert store.benefit_reviews() == [] and store.benefit(policy)["title"] == "가상 청년 월세"
    service = benefit_service(store)
    status, opened = service.benefit_reopen({"rawPolicyId": policy, "reviewer": "admin-1", "note": "정책 제보"})
    assert status == 200 and opened["reopened"] is True
    assert service.benefit_reopen({"rawPolicyId": policy})[1] == {"reviewId": opened["reviewId"], "reopened": False}
    [item] = store.benefit_reviews()
    assert item["reported"] is True and "REPORTED" in item["reasons"]
    status, _ = service.benefit_decide(opened["reviewId"], "REJECTED", {"note": "주거 지원 아님", "reviewer": "admin-1"})
    assert status == 200
    assert store.benefit(policy)["relevant"] is False
    published = store.conn.execute("select payload->'payload' from outbox order by created_at desc limit 1").fetchone()[0]
    # 반려 메모는 발행 값에 나가지 않아요(내부 기록에만)
    assert published["relevanceReason"] == "관리자가 확인해 서비스 대상에서 뺐어요"
    assert published["quality"]["reviewed"] is True
    assert "주거 지원 아님" not in json.dumps(published, ensure_ascii=False)
    assert service.benefit_reopen({"rawPolicyId": str(uuid.uuid4())})[0] == 404


def test_reprocessing_keeps_the_review_opened_by_a_report(store):
    """제보로 연 혜택 검수는 같은 정책이 다시 처리돼도 대체되지 않고 새 결과로 갱신돼요(제보가 가리키는 검수 ID 유지, 2026-10-25 검토)."""
    policy = str(uuid.uuid4())
    raw, event = benefit_event(policy, 1, needs_review=False)
    store.save_benefit(raw, event)
    service = benefit_service(store)
    _, opened = service.benefit_reopen({"rawPolicyId": policy, "reviewer": "admin-1", "note": "정책 제보"})
    raw2, event2 = benefit_event(policy, 1, needs_review=True, title="가상 청년 월세 (재처리)")
    store.save_benefit(raw2, event2)
    [item] = store.benefit_reviews()
    assert item["reviewId"] == opened["reviewId"] and item["reported"] is True
    assert "REPORTED" in item["reasons"] and "EVIDENCE_NOT_FOUND" in item["reasons"]
    assert store.benefit_review(item["reviewId"])["payload"]["source"]["title"] == "가상 청년 월세 (재처리)"
    assert store.benefit_reviews("SUPERSEDED") == []


def test_newer_benefit_version_supersedes_the_pending_review_and_blocks_old_approval(store):
    policy = str(uuid.uuid4())
    raw, event = benefit_event(policy, 1, needs_review=True)
    store.save_benefit(raw, event)
    [old] = store.benefit_reviews()
    raw2, event2 = benefit_event(policy, 2, needs_review=False)
    store.save_benefit(raw2, event2)
    assert store.benefit_reviews() == [] and [r["reviewId"] for r in store.benefit_reviews("SUPERSEDED")] == [old["reviewId"]]
    assert benefit_service(store).benefit_decide(old["reviewId"], "APPROVED", {})[0] == 409


def test_review_list_pages_by_cursor_and_filters_by_reason(store):
    # 관리자 검수 무한 스크롤(2026-10-29): 오래된 순으로 limit건씩, 앞 페이지 마지막 건(afterAt·afterId) 다음부터 이어 받아요
    jobs = [store.save(notice_event(1, str(uuid.uuid4())), held(f"r{i}")) for i in range(5)]
    service = ReviewService(session_of(store), new_event)

    status, first = service.list("PENDING", "2")
    assert status == 200 and [i["jobId"] for i in first["items"]] == jobs[:2] and first["hasMore"] and first["total"] == 5
    last = first["items"][-1]
    status, second = service.list("PENDING", "2", None, str(last["queuedAt"]), last["jobId"])
    assert status == 200 and [i["jobId"] for i in second["items"]] == jobs[2:4] and second["hasMore"]
    last = second["items"][-1]
    status, third = service.list("PENDING", "2", None, str(last["queuedAt"]), last["jobId"])
    assert [i["jobId"] for i in third["items"]] == jobs[4:] and not third["hasMore"]

    # 사유: held()는 사람 검수 대기(IN_REVIEW) → MUST. CHECK·FORMAT에는 없어요
    assert service.list("PENDING", None, "MUST")[1]["total"] == 5
    status, check = service.list("PENDING", None, "CHECK")
    assert status == 200 and check["items"] == [] and check["total"] == 0 and not check["hasMore"]


def test_benefit_review_list_pages_by_cursor_and_filters_reported(store):
    policies = [str(uuid.uuid4()) for _ in range(3)]
    for policy in policies:
        store.save_benefit(*benefit_event(policy, 1, needs_review=True, policyId=policy.replace("-", "")[:20]))
    service = benefit_service(store)

    status, first = service.benefit_list("PENDING", "2")
    assert status == 200 and [i["rawPolicyId"] for i in first["items"]] == policies[:2] and first["hasMore"] and first["total"] == 3
    last = first["items"][-1]
    status, rest = service.benefit_list("PENDING", "2", None, str(last["queuedAt"]), last["reviewId"])
    assert [i["rawPolicyId"] for i in rest["items"]] == policies[2:] and not rest["hasMore"]
    assert service.benefit_list("PENDING", None, "true")[1]["total"] == 0
    assert service.benefit_list("PENDING", None, "false")[1]["total"] == 3


def test_review_api_pool_reuses_connections_and_caps_concurrency():
    """검수 API 연결 풀: 동시 요청이 max_size를 넘어도 실패하지 않고 기다렸다 처리하며, 연결은 그 수까지만 열어요."""
    import threading
    from types import SimpleNamespace

    from mujuthaek_extraction.worker import pooled_store_session, review_pool

    pool = review_pool(SimpleNamespace(db_url=DB_URL, review_db_pool=2))
    seen, errors = set(), []

    def one():
        try:
            with pooled_store_session(pool) as s:
                seen.add(s.conn.info.backend_pid)
                assert s.conn.autocommit
                s.conn.execute("select pg_sleep(0.2)")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    try:
        threads = [threading.Thread(target=one) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert 1 <= len(seen) <= 2  # 연결 두 개를 돌려 써요
    finally:
        pool.close()


def test_extraction_stats_count_notices_by_last_job_and_sum_costs_in_the_period(store):
    """관리자 「추출 비용·품질」(2026-11-11): 공고(원본·버전)는 기간의 마지막 작업 상태로, 비용은 다시 처리한 작업까지 더해 셉니다."""
    from test_trace_view import usage

    def saved(post_suffix, status, cost, **extra):
        event = raw_event() | {"eventId": str(uuid.uuid4())}
        event["payload"] = event["payload"] | {"rawPostId": f"01929a3e-0000-7000-8000-00000000{post_suffix}"}
        return store.save(event, Outcome(status, cost_usd=cost, **extra))

    saved("0b01", "FAILED", 0.02)
    first = saved("0b01", "COMPLETED", 0.05, usage=usage())  # 실패 뒤 다시 처리해 게시
    saved("0b02", "PARTIAL", 0.03)
    saved("0b03", "IN_REVIEW", 0.01)
    old = saved("0b04", "COMPLETED", 0.5)
    store.conn.execute("update extraction_jobs set created_at = now() - interval '20 days' where id = %s", (old,))

    stats = store.extraction_stats(7)
    assert stats["notices"] == 3 and stats["jobs"] == 4 and stats["costUsd"] == pytest.approx(0.11)
    assert stats["costPerNotice"] == {"avgUsd": pytest.approx(0.0367), "maxUsd": pytest.approx(0.07)}
    groups = {g["group"]: g["notices"] for g in stats["statuses"]["groups"]}
    assert groups == {"AUTO": 1, "PARTIAL": 1, "REVIEW": 1, "FAILED": 0, "OTHER": 0}
    assert stats["statuses"]["publishedWithoutReviewRatio"] == pytest.approx(0.6667)
    assert len(stats["daily"]) == 7 and stats["daily"][-1]["jobs"] == 4 and stats["daily"][-1]["notices"] == 3
    assert stats["topJobs"][0]["jobId"] == first and stats["topJobs"][0]["costUsd"] == pytest.approx(0.05)
    assert stats["usage"]["jobs"] == 4 and stats["usage"]["v2Jobs"] == 1 and stats["usage"]["truncated"] is False
    assert stats["usage"]["resolver"]["adopted"] == 1

    month = store.extraction_stats(30)
    assert month["notices"] == 4 and month["topJobs"][0]["jobId"] == old

    class Session:
        def __enter__(self):
            return store

        def __exit__(self, *exc):
            return False

    service = ReviewService(lambda: Session(), new_event)
    status, body = service.extraction_stats("7")
    assert status == 200 and body["notices"] == 3
    assert service.extraction_stats("91")[0] == 400
