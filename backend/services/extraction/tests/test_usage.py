"""측정 기록(usage): 호출별 시간·토큰·비용 집계, 단계 시간, 작업 저장. 네트워크·DB 없이 가짜 모델·가짜 연결만 씁니다."""

import io
import json
import logging
from types import SimpleNamespace

import pytest
from test_pipeline import answers, raw_event, run

from mujuthaek_extraction.model import ModelError, ModelRequest, ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.local_ai import LocalChatModel
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel
from mujuthaek_extraction.model.pricing import cost_usd
from mujuthaek_extraction.pipeline import Outcome
from mujuthaek_extraction.store import JobStore
from mujuthaek_extraction.usage import MeteredModel, UsageRecorder, log_fields

REQUEST = ModelRequest("v", "structure", "지시", "원문", "할 일", {"type": "object"}, 100)


class Clock:
    """부를 때마다 정해 둔 만큼 흐르는 시계."""

    def __init__(self, step=0.5):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_metered_calls_record_time_tokens_cost_and_error_codes():
    paid = ModelResponse(
        '{"a": 1}', "gpt-6-luna", StopReason.END, input_tokens=1000, output_tokens=200, cached_input_tokens=600, cache_write_tokens=100, reasoning_tokens=50
    )
    model = RecordedModel({"structure": [ModelError("HTTP 429", transient=True, code="HTTP_429"), paid], "documents": [ModelError("끊김", transient=True)]})
    clock = Clock()
    usage = UsageRecorder(clock=clock)
    metered = MeteredModel(model, usage, "gpt-6-luna", clock=clock)
    with pytest.raises(ModelError):
        metered.complete(REQUEST)
    assert metered.complete(REQUEST) is paid  # 응답은 그대로 돌려줍니다
    with pytest.raises(ModelError):
        metered.complete(ModelRequest("v", "documents", "지시", "원문", "할 일", {}, 100))
    with usage.stage("sections"):
        pass
    summary = usage.summary()
    first, second, third = summary["calls"]
    assert (first["call"], first["attempt"], first["error"], first["costUsd"]) == ("structure", 1, "HTTP_429", 0.0)
    assert (second["attempt"], second["stopReason"], second["error"], second["seconds"]) == (2, "END", None, 0.5)
    assert (second["inputTokens"], second["cachedTokens"], second["cacheWriteTokens"], second["outputTokens"], second["reasoningTokens"]) == (
        1000,
        600,
        100,
        200,
        50,
    )
    assert second["costUsd"] == pytest.approx(cost_usd("gpt-6-luna", paid))
    assert (third["call"], third["attempt"], third["error"]) == ("documents", 1, "TRANSIENT")  # 코드가 없으면 일시·영구만
    totals = summary["totals"]
    assert totals["calls"] == 3 and totals["errors"] == 2 and totals["cacheHits"] == 0 and totals["callSeconds"] == 1.5
    assert (totals["inputTokens"], totals["outputTokens"], totals["reasoningTokens"]) == (1000, 200, 50)
    assert totals["costUsd"] == pytest.approx(cost_usd("gpt-6-luna", paid))
    assert summary["stages"] == {"sections": 0.5} and summary["format"] == 1
    assert "HTTP 429" not in json.dumps(summary, ensure_ascii=False)  # 오류 문구는 남기지 않습니다


def test_unpriced_models_and_cache_hits_cost_nothing():
    hit = ModelResponse("{}", "gpt-6-luna", StopReason.END, input_tokens=0, output_tokens=0, cache_hit=True)
    usage = UsageRecorder()
    MeteredModel(RecordedModel({"structure": [hit]}), usage, "gpt-6-luna").complete(REQUEST)
    MeteredModel(RecordedModel({"structure": ["{}"]}), usage, "local").complete(REQUEST)
    calls = usage.summary()["calls"]
    assert [c["cacheHit"] for c in calls] == [True, False] and [c["costUsd"] for c in calls] == [0.0, 0.0]
    assert [c["attempt"] for c in calls] == [1, 2]  # 대체 모델로 같은 호출을 다시 보내도 같은 이름으로 셉니다


def test_providers_report_reasoning_and_cached_tokens():
    def openai_opener(request, timeout):
        answer = {
            "status": "completed",
            "model": "gpt-6-luna",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
            "usage": {"input_tokens": 10, "output_tokens": 7, "input_tokens_details": {"cached_tokens": 4}, "output_tokens_details": {"reasoning_tokens": 5}},
        }
        return io.BytesIO(json.dumps(answer).encode())

    response = OpenAIResponsesModel("test-key-not-real", opener=openai_opener).complete(REQUEST)
    assert (response.cached_input_tokens, response.reasoning_tokens) == (4, 5)

    def local_opener(request, timeout):
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "prompt_tokens_details": {"cached_tokens": 8},
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}], "usage": usage}).encode())

    response = LocalChatModel("http://localhost:1/v1", opener=local_opener).complete(REQUEST)
    assert (response.cached_input_tokens, response.reasoning_tokens) == (8, 2)

    def bare_opener(request, timeout):  # 사용량 칸이 없으면 비워 둡니다
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}).encode())

    response = LocalChatModel("http://localhost:1/v1", opener=bare_opener).complete(REQUEST)
    assert (response.input_tokens, response.cached_input_tokens, response.reasoning_tokens) == (None, None, None)


def test_pipeline_outcome_carries_usage_without_changing_result():
    model = RecordedModel(answers(), "local")
    outcome = run(raw_event(), NoticeModels(model, None, names={"primary": "local"}))
    assert outcome.status == "COMPLETED"
    usage = outcome.usage
    assert [c["call"] for c in usage["calls"]] == [a["call_name"] for a in outcome.attempts]
    assert all(c["model"] == "local" and c["error"] is None for c in usage["calls"])
    assert {"intake", "image_reading", "sections", "assemble_verify", "recheck", "publish"} <= set(usage["stages"])
    assert usage["totalSeconds"] >= sum(usage["stages"].values()) - 0.01
    assert usage["totals"]["calls"] == len(model.requests)


def test_failed_outcome_still_has_usage():
    down = ModelError("로컬 AI 연결 실패", transient=False, code="CONNECTION")
    outcome = run(raw_event(), NoticeModels(RecordedModel({"structure": [down]}), None, names={"primary": "local"}))
    assert outcome.status == "FAILED"
    assert [(c["call"], c["error"]) for c in outcome.usage["calls"]] == [("structure", "CONNECTION")]


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        self.conn.executed.append((sql, params))
        self._row = ("claimed",) if sql.startswith("insert into processed_events") else None
        return self

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    """JobStore가 쓰는 만큼만 흉내 내는 psycopg 연결."""

    def __init__(self):
        self.autocommit, self.executed = False, []

    def transaction(self):
        return FakeCursor(self)

    def cursor(self):
        return FakeCursor(self)

    def execute(self, sql, params=()):
        return FakeCursor(self).execute(sql, params)


def test_store_writes_usage_column():
    conn = FakeConn()
    summary = {"format": 1, "totalSeconds": 1.0, "stages": {"sections": 0.9}, "totals": {"calls": 1}, "calls": []}
    JobStore(conn).save(raw_event(), Outcome("FAILED", error="x", usage=summary))
    sql, params = next((s, p) for s, p in conn.executed if s.startswith("insert into extraction_jobs"))
    columns = sql.split("(", 1)[1].split(")", 1)[0].replace(" ", "").split(",")
    assert params[columns.index("usage")].obj == summary


def test_job_log_line_has_usage_totals(caplog):
    from mujuthaek_extraction.worker import Processor

    class Store:
        def already_processed(self, event_id):
            return False

        def save(self, raw_event, outcome, run_id=None):
            return "job-1"

        def version_published(self, raw_post_id, raw_version):
            return False

        def interrupted_runs(self, event_id):
            return 0

        def record_start(self, event_id):
            pass

    processor = Processor.__new__(Processor)
    summary = UsageRecorder().summary()
    summary["totals"].update(calls=5, inputTokens=1234, costUsd=0.01)
    processor.settings = SimpleNamespace(db_url=None, model_mode="recorded", notice_budget_usd=0.5)  # 비용 장부 없음
    processor.run = lambda raw_event, store=None, ledger=None: Outcome("COMPLETED", usage=summary)
    with caplog.at_level(logging.INFO, logger="mujuthaek_extraction.worker"):
        processor._handle(Store(), raw_event(), "e-1")
    [record] = [r for r in caplog.records if r.getMessage() == "작업 저장"]
    assert (record.calls, record.inputTokens, record.estimatedCostUsd) == (5, 1234, 0.01)
    assert set(log_fields(summary)) <= set(vars(record))
