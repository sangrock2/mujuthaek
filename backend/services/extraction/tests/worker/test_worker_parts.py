"""로컬 AI 연결·모델 선택·검수 API 동작. 네트워크·DB 없이 가짜 연결과 가짜 저장소를 씁니다."""

import io
import json
import urllib.error
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import ModelError, ModelRequest, RecordedModel
from mujuthaek_extraction.model.factory import ModelFactory, NoticeModels
from mujuthaek_extraction.model.local_ai import LocalChatModel
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.pipeline import Outcome
from mujuthaek_extraction.review_api import ReviewService
from tests.worker.test_pipeline import answers, new_event, raw_event, run

REQUEST = ModelRequest("v", "structure", "지시", "원문", "할 일", {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}, 100)


def settings(**overrides):
    base = dict(db_url="", rabbitmq_url="", s3_endpoint=None, s3_bucket="b", s3_access_key=None, s3_secret_key=None, env_file=Path("없는.env"))
    return Settings(**(base | overrides))


# ---------- 로컬 AI ----------


def test_local_ai_without_address_fails_fast():
    with pytest.raises(ModelError, match="LOCAL_AI_URL"):
        LocalChatModel(None).complete(REQUEST)


def test_local_ai_parses_openai_compatible_answer():
    sent = {}

    def opener(request, timeout):
        sent.update(url=request.full_url, body=json.loads(request.data))
        choice = {"finish_reason": "stop", "message": {"content": '{"a": "값"}'}}
        answer = {"model": "qwen", "choices": [choice], "usage": {"prompt_tokens": 10, "completion_tokens": 3}}
        return io.BytesIO(json.dumps(answer).encode())

    response = LocalChatModel("http://localhost:11434/v1/", "qwen", opener=opener).complete(REQUEST)
    assert sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert sent["body"]["response_format"]["type"] == "json_schema" and sent["body"]["messages"][0]["content"] == "지시"
    assert json.loads(response.raw_text) == {"a": "값"} and response.input_tokens == 10 and response.model_id == "qwen"


def test_local_ai_connection_failure_is_skipped_for_a_while():
    calls, now = [], [100.0]

    def opener(request, timeout):
        calls.append(1)
        raise urllib.error.URLError("refused")

    model = LocalChatModel("http://localhost:1/v1", opener=opener, clock=lambda: now[0], down_seconds=60)
    for _ in range(3):
        with pytest.raises(ModelError):
            model.complete(REQUEST)
    assert len(calls) == 1  # 연결 실패 뒤 60초 동안은 다시 연결하지 않음
    now[0] += 61
    with pytest.raises(ModelError):
        model.complete(REQUEST)
    assert len(calls) == 2


# ---------- 모델 선택 ----------


def test_default_mode_is_local_then_paid(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    models = ModelFactory(settings(local_ai_url="http://localhost:11434/v1")).for_notice()
    assert isinstance(models.primary, LocalChatModel) and isinstance(models.fallback, BudgetedModel)
    assert models.names == {"primary": "local", "fallback": "gpt-6-luna"} and models.budget.limit_usd == 0.5


def test_without_local_address_paid_model_is_used_directly(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    models = ModelFactory(settings()).for_notice()
    assert isinstance(models.primary, BudgetedModel) and models.fallback is None and models.names == {"primary": "gpt-6-luna"}


def test_legacy_method_is_refused_at_start_when_paid_agents_would_run(monkeypatch):
    # 2026-11-10 코드 검토: 유료 키가 있으면 V2 담당이 도는데 V2 지시를 v10(legacy)으로 만들 수 없어, 모든 공고가 비용을 쓰고 실패했음
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    with pytest.raises(ValueError, match="legacy"):
        ModelFactory(settings(extraction_method="legacy"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert ModelFactory(settings(extraction_method="legacy")).for_notice().chat is None  # 유료 키가 없으면(V1 길) 그대로


def test_without_paid_key_only_local_is_used(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    models = ModelFactory(settings()).for_notice()
    assert isinstance(models.primary, LocalChatModel) and models.fallback is None


def test_recorded_mode_replays_saved_answers(tmp_path):
    for name, items in answers().items():
        (tmp_path / f"{name}.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    models = ModelFactory(settings(model_mode="recorded", recorded_dir=tmp_path)).for_notice()
    assert run(raw_event(), models).status == "COMPLETED"
    assert run(raw_event(), models).status == "COMPLETED"  # 공고마다 같은 응답을 다시 씁니다


def test_paid_call_over_budget_is_refused():
    paid = RecordedModel({"structure": ['{"a": "x"}']})
    guarded = BudgetedModel(paid, Budget("gpt-6-luna", 0.000001))
    with pytest.raises(ModelError, match="비용 상한"):
        guarded.complete(REQUEST)
    assert paid.requests == []


# ---------- 검수 API ----------


class FakeStore:
    def __init__(self, item):
        self.item, self.approved, self.rejected = item, None, None

    def reviews(self, status, limit=50, reason=None, after=None):
        return ([self.item] if self.item and self.item["reviewStatus"] == status else [])[:limit]

    def review_count(self, status, reason=None):
        return len(self.reviews(status))

    def review(self, job_id):
        return self.item

    def approve(self, job_id, candidate, event, note, **record):
        self.approved = (candidate, event, note)
        self.record = record
        self.item["reviewStatus"] = "APPROVED"

    def reject(self, job_id, note, reviewer=None):
        if self.item["reviewStatus"] != "PENDING":
            raise LookupError("대기 중인 검수가 아닙니다.")
        self.rejected = note
        self.record = {"reviewer": reviewer}

    def review_stats(self, days):
        return {"days": days}

    def review_activity(self, days, limit):
        return [{"days": days, "limit": limit}]

    def reopen(self, raw_post_id, reviewer=None, note=None):
        self.reopened = (raw_post_id, reviewer, note)
        return None if raw_post_id.endswith("0000") else {"jobId": "job", "reviewStatus": "PENDING", "reopened": True}


def service_with(item):
    store = FakeStore(item)

    @contextmanager
    def session():
        yield store

    return ReviewService(session, new_event), store


def pending_item():
    outcome = run(raw_event(), NoticeModels(RecordedModel(answers()), None))
    candidate = outcome.candidate
    candidate["quality"]["reviewIssues"].append({"code": "EXCEPTION_SUSPECTED", "target": "/eligibility/2", "description": "가산 기준 확인"})
    candidate["quality"]["verification"]["status"] = "REVIEW_REQUIRED"  # 검수 대기열의 후보는 검증을 통과하지 못한 것
    return {"jobId": "01929a3e-0000-7000-8000-00000000j0b1", "reviewStatus": "PENDING", "candidate": candidate, "rawEvent": raw_event(), "reasons": []}


def test_approve_republishes_approved_event_that_matches_contract():
    service, store = service_with(pending_item())
    status, body = service.approve("job", {"note": "원문 7쪽 확인"})
    assert status == 200 and body["reviewStatus"] == "APPROVED"
    candidate, event, note = store.approved
    assert note == "원문 7쪽 확인" and event["payload"]["reviewStatus"] == "APPROVED"
    assert all(not c["inReview"] for c in event["payload"]["conditions"])
    assert tools().validate(event, "events/extraction.completed.v1.json") == []


def test_approving_a_superseded_review_names_the_newer_version():
    # 같은 공고의 새 버전이 발행되어 대체된 건(store.py 검수 대기 건 대체). 실제 DB 판은 test_store_postgres
    item = pending_item() | {"reviewStatus": "SUPERSEDED", "rawPostId": "01929a3e-0000-7000-8000-000000000001"}
    item["supersededBy"] = {"jobId": "01929a3e-0000-7000-8000-0000000000b2", "rawPostId": item["rawPostId"], "version": 2}
    service, store = service_with(item)
    status, body = service.approve("job", {})
    assert status == 409 and "v2" in body["error"] and body["supersededBy"]["version"] == 2 and store.approved is None
    assert service.list("SUPERSEDED") == (200, {"items": [item], "total": 1, "hasMore": False})
    assert service.list("PENDING") == (200, {"items": [], "total": 0, "hasMore": False})


def partial_item():
    """부분 게시된 작업: 보류 항목(자격 조건 하나·접수 일정 하나)이 있는 후보."""
    item = pending_item()
    candidate = item["candidate"]
    application = next(i for i, s in enumerate(candidate["schedules"]) if "APPLICATION" in s["kinds"])
    candidate["quality"]["heldItems"] = [
        {"target": "/eligibility/2", "extent": "ITEM", "codes": ["EXCEPTION_SUSPECTED"], "description": "가산 기준 확인"},
        {"target": f"/schedules/{application}", "extent": "ITEM", "codes": ["EVIDENCE_SCATTERED"], "description": "원문 확인 필요"},
    ]
    candidate["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
    return item, candidate["schedules"][application]["id"]


def test_partially_published_notice_can_be_approved():
    # 예전엔 승인용 사본에서 보류 목록을 찾다 KeyError로 멈췄고, 고쳐도 상세에 보류 목록이 남아 계약 위반(EVENT_HELD_ITEMS_CONFLICT)이었음
    item, schedule_id = partial_item()
    service, store = service_with(item)
    status, body = service.approve("job", {"note": "보류 항목 원문 확인"})
    assert status == 200, body
    candidate, event, _ = store.approved
    payload = event["payload"]
    assert tools().validate(event, "events/extraction.completed.v1.json") == []
    assert payload["reviewStatus"] == "APPROVED" and "heldItems" not in payload
    assert "heldItems" not in payload["notice"]["quality"]
    assert payload["notice"]["quality"]["reviewIssues"]  # 자동 검증 기록은 상세에 남김
    assert all(not c["inReview"] for c in payload["conditions"])
    assert any(w["scheduleId"] == schedule_id for w in payload["applicationWindows"])  # 사람이 확인한 일정은 다시 내보냄
    assert candidate["quality"]["heldItems"]  # 작업 기록의 후보는 받은 그대로


def test_old_stored_candidate_is_upgraded_before_approval():
    # 2026-10-23 이전 저장본(일정 새 칸 없음, 자유 글자 신청 방법)도 승인할 수 있어야 합니다
    item = pending_item()
    candidate = item["candidate"]
    for schedule in candidate["schedules"]:
        for key in ("places", "applicationEmail", "dailyHours", "breaks", "excludedDays", "timeNote"):
            schedule.pop(key, None)
        schedule["channels"] = ["온라인 신청"] if "APPLICATION" in schedule["kinds"] else []
    for document in candidate["requiredDocuments"]:
        for key in ("group", "copies", "issuer"):
            document.pop(key, None)
    candidate["notice"].pop("applicationChannels", None)
    service, store = service_with(item)
    status, body = service.approve("job", {})
    assert status == 200, body
    approved, event, _ = store.approved
    assert tools().validate(event, "events/extraction.completed.v1.json") == []
    assert approved["notice"]["applicationChannels"] == ["ONLINE"]


def test_approve_with_broken_candidate_is_refused():
    service, store = service_with(pending_item())
    status, body = service.approve("job", {"candidate": {"schemaVersion": "1.0.0"}})
    assert status == 422 and store.approved is None


def test_cannot_approve_twice_or_without_result():
    service, _ = service_with(pending_item())
    assert service.approve("job", {})[0] == 200
    assert service.approve("job", {})[0] == 409
    no_result = pending_item() | {"candidate": None}
    assert service_with(no_result)[0].approve("job", {})[0] == 409


def test_list_rejects_unknown_status():
    service, _ = service_with(pending_item())
    assert service.list("DONE")[0] == 400
    assert len(service.list("PENDING")[1]["items"]) == 1


def test_approve_refuses_candidate_of_another_notice():
    # 검토 지적: 승인할 후보가 다른 공고(rawPostId)를 가리켜도 그대로 발행되던 것
    import copy

    item = pending_item()
    other = copy.deepcopy(item["candidate"])
    other["input"]["rawPostId"] = "01929a3e-0000-7000-8000-0000000000ff"
    for reference in other["sourceReferences"]:
        reference["rawPostId"] = "01929a3e-0000-7000-8000-0000000000ff"
    service, store = service_with(item)
    status, body = service.approve("job", {"candidate": other})
    assert status == 422 and "원본" in body["error"] and store.approved is None


def http_server(token=None):
    import threading

    from mujuthaek_extraction.review_api import serve

    service, store = service_with(pending_item())
    server = serve(service, "127.0.0.1", 0, token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, store


def call(server, method, path, body=None, headers=None):
    import json as _json
    import urllib.error
    import urllib.request

    data = None if body is None else (body if isinstance(body, bytes) else _json.dumps(body).encode())
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


JOB = "/reviews/01929a3e-0000-7000-8000-000000000001"


def test_review_api_requires_token_when_configured():
    server, store = http_server(token="s3cret")
    try:
        assert call(server, "GET", "/health") == 200  # 상태 확인은 열어 둠
        assert call(server, "GET", "/reviews") == 401
        assert call(server, "POST", JOB + "/approve", {}) == 401 and store.approved is None
        assert call(server, "GET", "/reviews", headers={"Authorization": "Bearer wrong"}) == 401
        assert call(server, "GET", "/reviews", headers={"Authorization": "Bearer s3cret"}) == 200
    finally:
        server.shutdown()


def test_review_api_without_token_accepts_only_this_computer():
    from types import SimpleNamespace

    from mujuthaek_extraction.review_api import handler_for

    handler = handler_for(service_with(pending_item())[0])
    assert handler._allowed(SimpleNamespace(headers={}, client_address=("127.0.0.1", 5000)))
    assert not handler._allowed(SimpleNamespace(headers={}, client_address=("10.0.0.7", 5000)))


def test_review_api_rejects_bad_requests_with_400_not_dropped_connection():
    server, store = http_server()
    try:
        assert call(server, "GET", "/reviews/------------------------------------") == 400
        assert call(server, "POST", JOB + "/reject", {"note": {"not": "text"}}) == 400
        assert call(server, "POST", JOB + "/reject", b"{}", headers={"Content-Length": "abc"}) == 400
        assert store.rejected is None
    finally:
        server.shutdown()


def bare_processor(run):
    import threading

    from mujuthaek_extraction.worker import Processor

    processor = Processor.__new__(Processor)
    processor._running, processor._running_lock = {}, threading.Lock()
    processor.settings = SimpleNamespace(db_url=None, model_mode="recorded", notice_budget_usd=0.5)  # 비용 장부 없음
    processor.run = lambda raw_event, store=None, ledger=None: run(raw_event)
    return processor


class MemoryStore:
    def __init__(self):
        self.done, self.saved = set(), 0
        self.claims, self.claim_lock = {}, __import__("threading").Lock()

    def claim(self, raw_post_id, raw_version, owner, lease_seconds):
        with self.claim_lock:
            holder = self.claims.get((raw_post_id, raw_version))
            if holder not in (None, owner):
                return False
            self.claims[(raw_post_id, raw_version)] = owner
            return True

    def renew_claim(self, raw_post_id, raw_version, owner, lease_seconds):
        return self.claims.get((raw_post_id, raw_version)) == owner

    def release_claim(self, raw_post_id, raw_version, owner):
        with self.claim_lock:
            if self.claims.get((raw_post_id, raw_version)) == owner:
                del self.claims[(raw_post_id, raw_version)]

    def already_processed(self, event_id):
        return event_id in self.done

    def save(self, raw_event, outcome, run_id=None):
        self.saved += 1
        self.done.add(raw_event["eventId"])
        return "job"

    def version_published(self, raw_post_id, raw_version):
        return False

    def interrupted_runs(self, event_id):
        return 0

    def record_start(self, event_id):
        pass


def test_redelivered_event_waits_for_running_one_instead_of_paying_again():
    # 검토 지적: 큐 연결이 끊겨 같은 메시지가 다시 오면 두 스레드가 같은 공고를 동시에 처리(AI 비용 두 번·발행 두 번)
    import threading
    import time

    calls = []

    def slow_run(raw_event):
        calls.append(raw_event["eventId"])
        time.sleep(0.2)
        return Outcome("COMPLETED")

    processor, store = bare_processor(slow_run), MemoryStore()
    event = {"eventId": "01929a3e-0000-7000-8000-0000000000aa"}
    threads = [threading.Thread(target=processor.handle, args=(store, event)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert calls == [event["eventId"]] and store.saved == 1


def test_same_event_delivered_ten_times_runs_once():
    # 요구 2-01(DB 없이 도는 판): 같은 이벤트 10번 → 처리 1번. 실제 DB 판은 test_store_postgres
    calls = []
    processor, store = bare_processor(lambda raw_event: calls.append(raw_event["eventId"]) or Outcome("COMPLETED")), MemoryStore()
    for _ in range(10):
        processor.handle(store, {"eventId": "01929a3e-0000-7000-8000-0000000000ab"})
    assert len(calls) == 1 and store.saved == 1


def test_duplicate_found_at_save_is_skipped_quietly():
    from mujuthaek_extraction.store import DuplicateEvent

    class RacingStore(MemoryStore):
        def save(self, raw_event, outcome, run_id=None):
            raise DuplicateEvent(raw_event["eventId"])

    processor = bare_processor(lambda raw_event: Outcome("COMPLETED"))
    assert processor.handle(RacingStore(), {"eventId": "01929a3e-0000-7000-8000-0000000000bb"}) is None


def test_database_errors_are_requeued_not_sent_to_dlq():
    import psycopg

    from mujuthaek_extraction.worker import _db_errors

    assert issubclass(psycopg.OperationalError, _db_errors()) and not issubclass(ValueError, _db_errors())


def test_timed_out_call_counts_toward_budget_so_retries_cannot_triple_spend():
    # 검토 지적: 성공한 호출만 비용으로 세어, 시간 초과로 세 번 재시도된 큰 호출이 상한의 세 배까지 쓸 수 있었음
    from mujuthaek_extraction.model.base import ModelError, ModelRequest
    from mujuthaek_extraction.model.pricing import Budget, BudgetedModel

    class TimesOut:
        def complete(self, request):
            raise ModelError("연결 실패: TimeoutError", transient=True, maybe_billed=True)

    request = ModelRequest(
        call_name="structure", prompt_version="v", system="s" * 1000, user="u" * 1000, instructions="i", output_schema={}, max_output_tokens=64_000
    )
    budget = Budget("gpt-6-luna", limit_usd=budget_limit_for_two(request))
    model = BudgetedModel(TimesOut(), budget)
    for _ in range(2):
        with pytest.raises(ModelError):
            model.complete(request)
    with pytest.raises(ModelError, match="상한"):
        model.complete(request)  # 앞의 두 번을 셌으므로 세 번째는 보내지 않음


def budget_limit_for_two(request):
    from mujuthaek_extraction.model.pricing import Budget

    return Budget("gpt-6-luna", 1.0).worst_case(request) * 2.5


def test_cut_off_or_non_json_response_is_a_model_error_not_a_crash():
    import http.client

    from mujuthaek_extraction.model.base import ModelError, ModelRequest
    from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel

    request = ModelRequest(
        call_name="structure", prompt_version="v", system="s", user="u", instructions="i", output_schema={"type": "object"}, max_output_tokens=10
    )

    class Broken(io.BytesIO):
        def __init__(self, failure):
            super().__init__()
            self.failure = failure

        def read(self, *args):
            if self.failure is not None:
                raise self.failure
            return b"<html>not json</html>"

    for failure in (http.client.IncompleteRead(b"{"), None):
        model = OpenAIResponsesModel(api_key="test-key", opener=lambda req, timeout, failure=failure: Broken(failure))
        with pytest.raises(ModelError) as error:
            model.complete(request)
        assert error.value.transient and error.value.maybe_billed


def test_s3_missing_key_waits_but_access_problems_fail_loudly():
    # 검토 지적: 권한·인증 오류도 "아직 없음"으로 숨겨, 운영 설정이 잘못돼도 모든 공고가 조용히 자료 대기에 머물렀음
    from mujuthaek_extraction.s3_reader import S3SourceReader

    class ClientError(Exception):
        def __init__(self, code):
            self.response = {"Error": {"Code": code}}

    class Client:
        def __init__(self, error):
            self.error = error

        def get_object(self, Bucket, Key):  # noqa: N803 - boto3 이름 그대로
            raise self.error

    assert S3SourceReader("b", None, None, None, client=Client(ClientError("NoSuchKey"))).read_file("k") is None
    with pytest.raises(ClientError):
        S3SourceReader("b", None, None, None, client=Client(ClientError("AccessDenied"))).read_file("k")

    class Body:
        def read(self, amount=-1):  # boto3 StreamingBody처럼 읽을 길이를 받음
            return "﻿공고".encode()

    class Ok:
        def get_object(self, Bucket, Key):  # noqa: N803
            return {"Body": Body()}

    assert S3SourceReader("b", None, None, None, client=Ok()).read_text("k") == "공고"  # BOM은 떼어 냄


def test_production_refuses_to_start_on_development_defaults(monkeypatch):
    for name in ("DB_URL", "RABBITMQ_URL", "S3_BUCKET", "S3_ENDPOINT", "EXTRACTION_REVIEW_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EXTRACTION_ENV", "production")
    with pytest.raises(ValueError, match="DB_URL"):
        Settings.from_env()
    for name, value in (("DB_URL", "postgresql://x"), ("RABBITMQ_URL", "amqp://x"), ("S3_BUCKET", "b"), ("S3_ENDPOINT", ""), ("EXTRACTION_REVIEW_TOKEN", "t")):
        monkeypatch.setenv(name, value)
    assert Settings.from_env().review_token == "t"


def test_health_reports_stopped_worker_parts():
    # 검토 지적: /health가 검수 API 스레드만 봐서 큐 소비가 멈춰도 정상으로 보였음
    from mujuthaek_extraction.health import Health

    now = [0.0]
    health = Health({"consumer": 120, "relay": 120}, clock=lambda: now[0])
    assert health.report()[0]  # 시작 직후는 기다려 줌
    now[0] = 130
    ok, parts = health.report()
    assert not ok and parts == {"consumer": "no signal", "relay": "no signal"}
    health.beat("consumer")
    health.beat("relay")
    assert health.report() == (True, {"consumer": "ok", "relay": "ok"})
    now[0] = 260
    health.beat("relay")
    ok, parts = health.report()
    assert not ok and parts["consumer"].startswith("stale") and parts["relay"] == "ok"


def test_health_endpoint_returns_503_when_a_part_is_down():
    import threading

    from mujuthaek_extraction.health import Health
    from mujuthaek_extraction.review_api import serve

    now = [500.0]
    health = Health({"consumer": 120}, clock=lambda: now[0])
    health.started = 0
    server = serve(service_with(pending_item())[0], "127.0.0.1", 0, None, health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert call(server, "GET", "/health") == 503
        health.beat("consumer")
        assert call(server, "GET", "/health") == 200
    finally:
        server.shutdown()


def test_s3_objects_over_the_size_limit_are_refused():
    from mujuthaek_extraction import s3_reader
    from mujuthaek_extraction.s3_reader import S3SourceReader, SourceTooLarge

    class Body:
        def __init__(self, size):
            self.size = size

        def read(self, amount=-1):
            return b"x" * (self.size if amount < 0 else min(self.size, amount))

    class Client:
        def __init__(self, length, size):
            self.length, self.size = length, size

        def get_object(self, Bucket, Key):  # noqa: N803
            return {"ContentLength": self.length, "Body": Body(self.size)}

    limit = s3_reader.MAX_OBJECT_BYTES
    with pytest.raises(SourceTooLarge):
        S3SourceReader("b", None, None, None, client=Client(limit + 1, 10)).read_file("k")  # 길이만 보고 거절
    with pytest.raises(SourceTooLarge):
        S3SourceReader("b", None, None, None, client=Client(None, limit + 5)).read_file("k")  # 길이를 몰라도 한도까지만 읽고 거절
    assert S3SourceReader("b", None, None, None, client=Client(10, 10)).read_file("k") == b"x" * 10


# ---------- 큐 선언 ----------


def test_policy_events_get_a_waiting_queue_so_collector_relay_is_not_blocked():
    # raw.policy.collected를 받을 큐가 없으면 collector 발행기(mandatory)가 거절당해 같은 묶음의 공고 이벤트까지 막힙니다
    from mujuthaek_extraction import worker

    calls = []

    class Channel:
        def __getattr__(self, name):
            return lambda **kwargs: calls.append((name, kwargs))

    worker.declare(Channel())
    bindings = {(c["queue"], c["routing_key"]) for name, c in calls if name == "queue_bind" and c.get("exchange") == worker.EXCHANGE}
    # 정책 이벤트는 공용 정책 큐 하나로 받아 판정 틀을 만듭니다(다른 담당은 발행만 함, 2026-10-23). 전용 큐는 더 만들지 않습니다
    assert bindings == {
        ("mujuthaek.raw.collected", "raw.notice.collected"),
        ("mujuthaek.raw.policy", "raw.policy.collected"),
        ("mujuthaek.policy.extracted", "policy.extracted"),  # 혜택 결과: 받는 쪽이 생기기 전까지 보관(없으면 아웃박스가 막힘)
    }
    # 혜택 결과 큐는 api가 받을 큐라 api 큐 규칙(실패 큐 연결 + .dlq)과 같은 인자로 선언합니다(2026-10-25 검토)
    assert ("queue_declare", {"queue": "mujuthaek.policy.extracted", "durable": True, "arguments": {"x-dead-letter-exchange": "mujuthaek.dlx"}}) in calls
    assert ("queue_declare", {"queue": "mujuthaek.policy.extracted.dlq", "durable": True}) in calls
    # 이미 있는 큐와 인자가 달라 거절당하지 않게 인자 없이 선언합니다
    assert ("queue_declare", {"queue": "mujuthaek.raw.policy", "durable": True}) in calls
    assert ("queue_declare", {"queue": "mujuthaek.raw.policy.dlq", "durable": True}) in calls


def test_failed_policy_message_is_moved_to_dlq_then_acked():
    # 정책 큐에는 dead-letter 인자가 없어 reject하면 메시지가 사라집니다. .dlq로 옮긴 뒤에만 ack합니다
    from mujuthaek_extraction import worker

    calls = []

    class Channel:
        def __getattr__(self, name):
            return lambda *args, **kwargs: calls.append((name, args, kwargs))

    import pika

    original = pika.BasicProperties(content_type="application/json", delivery_mode=2, headers={"trace": "t1"})
    worker.finish_policy(Channel(), 7, "dlq", b'{"eventId": "x"}', original, "AI_FAILED:INVALID_JSON")
    assert [c[0] for c in calls] == ["basic_publish", "basic_ack"]
    published = calls[0][2]
    assert {k: published[k] for k in ("exchange", "routing_key", "body")} == {
        "exchange": "",
        "routing_key": "mujuthaek.raw.policy.dlq",
        "body": b'{"eventId": "x"}',
    }
    # 실패 이유를 헤더로 남깁니다(원래 헤더·속성은 그대로)
    props = published["properties"]
    assert props.content_type == "application/json"
    assert props.headers["trace"] == "t1"
    assert props.headers["x-error-reason"] == "AI_FAILED:INVALID_JSON"
    assert props.headers["x-failed-at"].endswith("+00:00")
    assert original.headers == {"trace": "t1"}
    calls.clear()
    worker.finish_policy(Channel(), 8, "requeue", b"{}")
    assert calls == [("basic_nack", (8,), {"requeue": True})]
    calls.clear()
    worker.finish_policy(Channel(), 9, "ack", b"{}")
    assert calls == [("basic_ack", (9,), {})]

    class Broken(Channel):
        def basic_publish(self, **kwargs):
            raise OSError("연결 끊김")

    calls.clear()
    with pytest.raises(OSError):
        worker.finish_policy(Broken(), 10, "dlq", b"{}")
    assert calls == []  # 옮기지 못했으면 ack하지 않음(연결이 끊긴 뒤 다시 옴)


def test_judge_message_notes_why_a_policy_goes_to_dlq(monkeypatch):
    from mujuthaek_extraction import worker

    class Processor:
        def open_ledger(self, _raw_event):
            raise RuntimeError("S3 끊김")

    why: list[str] = []
    settings = type("S", (), {"benefit_enabled": False, "notice_budget_usd": 1.0})()
    raw = {"eventId": "e1", "payload": {"field": "STARTUP_SUPPORT", "rawPolicyId": "p1", "version": 1}}
    assert worker.judge_message(settings, Processor(), raw, worker.RetryCounter(), why) == "dlq"
    assert why == ["ERROR:RuntimeError"]


def test_replay_dlq_moves_messages_back_until_limit_or_empty():
    from types import SimpleNamespace

    from mujuthaek_extraction import worker

    class Channel:
        def __init__(self, bodies):
            self.bodies, self.calls = list(bodies), []

        def basic_get(self, queue, auto_ack):
            self.calls.append(("get", queue))
            if not self.bodies:
                return None, None, None
            return SimpleNamespace(delivery_tag=len(self.calls)), "props", self.bodies.pop(0)

        def basic_publish(self, **kwargs):
            self.calls.append(("publish", kwargs["routing_key"], kwargs["body"]))

        def basic_ack(self, tag):
            self.calls.append(("ack", tag))

    dlq, queue = worker.DLQ_TARGETS["policy"]
    assert (dlq, queue) == ("mujuthaek.raw.policy.dlq", "mujuthaek.raw.policy")
    channel = Channel([b"a", b"b", b"c"])
    assert worker.replay_dlq(channel, dlq, queue, limit=2) == 2  # 한도까지만
    assert [c for c in channel.calls if c[0] == "publish"] == [("publish", queue, b"a"), ("publish", queue, b"b")]
    assert worker.replay_dlq(channel, dlq, queue, limit=10) == 1  # 남은 것만, 비면 멈춤
    assert worker.DLQ_TARGETS["notice"] == ("mujuthaek.raw.collected.dlq", "mujuthaek.raw.collected")


def test_unexpected_error_keeps_cost_already_spent(monkeypatch):
    # 검토 지적(2026-10-20): 호출 뒤 예상 못 한 예외가 나면 이미 쓴 비용이 $0으로 기록돼, 다시 처리할 때 누적 예산에서 빠졌음
    from types import SimpleNamespace

    from mujuthaek_extraction import worker
    from mujuthaek_extraction.model.factory import NoticeModels
    from mujuthaek_extraction.model.pricing import Budget

    budget = Budget("gpt-6-luna", 0.5)
    models = NoticeModels(None, None, budget, {"primary": "test"})

    def broken_process(raw_event, **kwargs):
        budget.spent_usd += 0.12  # 호출 두어 번 뒤
        budget._held[99] = 0.03  # 끝나지 않은 호출(청구됐을 수 있음)
        raise KeyError("결합 중 결함")

    monkeypatch.setattr(worker, "process", broken_process)
    processor = worker.Processor.__new__(worker.Processor)
    processor.settings = SimpleNamespace(require_pdf=False, extraction_method="sections", parallel_calls=1, parallel_stagger_seconds=0)
    processor.models = SimpleNamespace(for_notice=lambda cache=None, spent_before_usd=0.0, ledger=None: models)
    processor.reader = processor.regions = None

    outcome = processor.run({"eventId": "e-1"})

    assert outcome.status == "FAILED" and "KeyError" in outcome.error
    assert outcome.cost_usd == pytest.approx(0.15)


def test_same_raw_version_with_another_event_id_is_not_processed_twice():
    # 검토 지적(2026-10-20): 다시 처리 이벤트처럼 eventId가 다른 같은 원본 버전은 프로세스 안 중복 방지(_running)에 걸리지 않아
    # 두 처리가 각자 앞선 비용 0을 읽고 예산을 따로 썼음 → DB 처리권으로 한 번에 하나만
    import threading

    from mujuthaek_extraction.worker import ClaimBusy

    started, release = threading.Event(), threading.Event()

    def slow_run(raw_event):
        started.set()
        release.wait(5)
        return Outcome("COMPLETED")

    processor, store = bare_processor(slow_run), MemoryStore()
    first, second = raw_event(), raw_event()
    second["eventId"] = "01929a3e-0000-7000-8000-0000000000e2"
    assert first["payload"]["rawPostId"] == second["payload"]["rawPostId"]
    worker_thread = threading.Thread(target=processor.handle, args=(store, first))
    worker_thread.start()
    assert started.wait(5)
    with pytest.raises(ClaimBusy):
        processor.handle(store, second)
    release.set()
    worker_thread.join(5)
    assert store.claims == {}  # 끝나면 풂
    processor.handle(store, second)  # 앞 처리가 끝나면 처리할 수 있음
    assert store.saved == 2


def test_claim_is_released_even_when_saving_fails():
    from mujuthaek_extraction.worker import claimed

    store = MemoryStore()
    with pytest.raises(RuntimeError), claimed(store, raw_event()):
        assert store.claims
        raise RuntimeError("저장 실패")
    assert store.claims == {}


# ---------- 정책 판정 메시지 결정 ----------


def policy_message_setup(monkeypatch, outcomes):
    """judge_policy가 outcomes 차례대로 예외를 내거나(예외 객체) 값을 돌려주게 하고, 잠자기·DB를 끈 judge_message 실행기."""
    from mujuthaek_extraction import worker

    calls = []

    def fake_judge(store, raw_event, model, regions):
        calls.append(raw_event["eventId"])
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @contextmanager
    def no_store(_settings):
        yield None

    opened = []
    monkeypatch.setattr(worker, "judge_policy", fake_judge)
    monkeypatch.setattr(worker, "store_session", no_store)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    processor = SimpleNamespace(
        open_ledger=lambda raw_event: opened.append(raw_event) or None,
        models=SimpleNamespace(for_notice=lambda ledger=None: SimpleNamespace(primary="model", fallback=None)),
        regions=None,
    )
    retries = worker.RetryCounter(limit=3)
    policy = {"field": "STARTUP_SUPPORT", "rawPolicyId": "01a16146-b9b3-704f-8da4-54c2dcfa1999", "version": 2}

    def handle(event_id, **payload):
        return worker.judge_message(SimpleNamespace(notice_budget_usd=0.5), processor, {"eventId": event_id, "payload": policy | payload}, retries)

    return handle, calls, opened


def test_permanent_ai_failure_without_frame_goes_to_dlq_not_ack(monkeypatch):
    # 리뷰 2026-10-22: 영구 오류로 AI 틀도 규칙 틀도 없으면 None이 돌아와 ack되고 아무 기록도 남지 않았음
    from mujuthaek_extraction import worker

    handle, calls, _ = policy_message_setup(monkeypatch, [worker.AiFailed("BAD_SHAPE"), "event-id", None])
    assert handle("e-1") == "dlq"
    assert handle("e-2") == "ack" and handle("e-3") == "ack"  # 만들었거나(값) 보낼 것이 없는(None, 예: 이미 처리) 경우는 ack


def test_repeated_temporary_ai_failures_end_in_dlq_instead_of_looping(monkeypatch):
    # 5xx가 계속되면 같은 메시지가 끝없이 큐를 돌았음: 같은 정책 버전이 limit번 연속 실패하면 .dlq로
    from mujuthaek_extraction import worker

    fail = worker.AiUnavailable
    handle, calls, _ = policy_message_setup(monkeypatch, [fail("HTTP_503"), fail("HTTP_503"), fail("HTTP_503"), fail("HTTP_503"), "id", fail("HTTP_503")])
    assert [handle("e-1"), handle("e-1")] == ["requeue", "requeue"]
    assert handle("e-2") == "dlq"  # eventId가 달라도(재발행) 같은 정책 버전이면 이어 셈
    assert handle("e-1") == "requeue"  # .dlq로 보낸 뒤에는 처음부터
    assert handle("e-1") == "ack"
    assert handle("e-1") == "requeue"  # 성공하면 셈을 지움
    assert len(calls) == 6


def test_benefit_policy_is_acked_before_opening_the_ledger(monkeypatch):
    handle, calls, opened = policy_message_setup(monkeypatch, [])
    assert handle("e-1", field="BENEFIT") == "ack" and calls == [] and opened == []


# ---------- 관리자 검수 화면: 칸별 수정·처리 기록·통계 (2026-10-25) ----------


def test_field_edits_are_applied_recorded_and_published():
    service, store = service_with(pending_item())
    before = store.item["candidate"]["eligibility"][0]["description"]
    edits = [{"path": "/eligibility/0/description", "value": "가상 설명을 고침"}]
    status, body = service.approve("job", {"edits": edits, "reviewer": "admin:7", "note": "원문 3쪽"})
    assert status == 200, body
    candidate, event, note = store.approved
    assert candidate["eligibility"][0]["description"] == "가상 설명을 고침"
    assert event["payload"]["notice"]["eligibility"][0]["description"] == "가상 설명을 고침"
    assert store.record == {
        "reviewer": "admin:7",
        "edited": True,
        "edits": [{"path": "/eligibility/0/description", "before": before, "after": "가상 설명을 고침"}],
    }
    assert store.item["candidate"]["eligibility"][0]["description"] == before  # 저장된 원래 후보는 그대로(사본을 고침)


def test_plain_approval_is_recorded_as_not_edited():
    service, store = service_with(pending_item())
    assert service.approve("job", {"reviewer": "admin:7"})[0] == 200
    assert store.record == {"reviewer": "admin:7", "edited": False, "edits": None}


@pytest.mark.parametrize(
    ("edits", "message"),
    [
        ([{"path": "/input/rawPostId", "value": "x"}], "고칠 수 없는"),
        ([{"path": "/quality/heldItems", "value": []}], "고칠 수 없는"),
        ([{"path": "/eligibility/99/description", "value": "x"}], "칸이 없습니다"),
        ([{"path": "/eligibility/0/newField", "value": "x"}], "새 칸은"),
        ([{"path": "eligibility/0", "value": "x"}], "JSON Pointer"),
        ([{"path": "/eligibility/0/description"}], "{path, value}"),
        ([], "한 개 이상"),
    ],
)
def test_bad_field_edits_are_refused(edits, message):
    service, store = service_with(pending_item())
    status, body = service.approve("job", {"edits": edits})
    assert status == 422 and message in body["error"] and store.approved is None


def test_edit_that_breaks_the_contract_is_refused():
    service, store = service_with(pending_item())
    status, body = service.approve("job", {"edits": [{"path": "/eligibility/0/category", "value": "없는 분류"}]})
    assert status == 422 and store.approved is None


def test_candidate_and_edits_together_are_refused():
    item = pending_item()
    service, store = service_with(item)
    status, _ = service.approve("job", {"candidate": item["candidate"], "edits": [{"path": "/eligibility/0/description", "value": "x"}]})
    assert status == 422 and store.approved is None


def test_reject_records_reviewer():
    service, store = service_with(pending_item())
    assert service.reject("job", {"note": "[중복 공고]", "reviewer": "admin:7"})[0] == 200
    assert store.rejected == "[중복 공고]" and store.record == {"reviewer": "admin:7"}


def test_stats_days_are_checked():
    service, _ = service_with(pending_item())
    assert service.stats(None) == (200, {"days": 7})
    assert service.stats("30") == (200, {"days": 30})
    assert service.stats("0")[0] == 400 and service.stats("x")[0] == 400 and service.stats("91")[0] == 400


def test_activity_days_and_limit_are_checked():
    service, _ = service_with(pending_item())
    assert service.activity(None, None) == (200, {"items": [{"days": 30, "limit": 300}]})
    assert service.activity("7", "50") == (200, {"items": [{"days": 7, "limit": 50}]})
    assert service.activity("0", None)[0] == 400 and service.activity("91", None)[0] == 400 and service.activity("x", None)[0] == 400
    assert service.activity(None, "0")[0] == 400 and service.activity(None, "1001")[0] == 400


def test_reopen_checks_the_raw_post_id_and_reports_missing_results():
    service, store = service_with(pending_item())
    assert service.reopen({"rawPostId": "x"})[0] == 400
    status, body = service.reopen({"rawPostId": "01929a3e-0000-7000-8000-000000000001", "reviewer": "admin:7", "note": "공고 제보"})
    assert status == 200 and body["reopened"] is True
    assert store.reopened == ("01929a3e-0000-7000-8000-000000000001", "admin:7", "공고 제보")
    assert service.reopen({"rawPostId": "01929a3e-0000-7000-8000-000000000000"})[0] == 404


def test_review_api_reads_a_chunked_body():
    # 2026-10-25 로컬 실제 흐름: api 서버(Java RestClient)가 길이 없이 조각 전송으로 보내 메모·수정이 빈 본문으로 읽혀 400이 됐습니다
    import socket

    server, store = http_server()
    try:
        body = '{"note": "조각 전송 메모"}'.encode()
        chunks = b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body)
        request = (
            f"POST {JOB}/reject HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        ).encode() + chunks
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as conn:
            conn.sendall(request)
            reply = conn.recv(4096).decode("utf-8", "replace")
        assert reply.startswith("HTTP/1.0 200") or reply.startswith("HTTP/1.1 200"), reply[:80]
        assert store.rejected == "조각 전송 메모"
    finally:
        server.shutdown()
