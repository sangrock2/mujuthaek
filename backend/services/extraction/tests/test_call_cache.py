"""성공한 호출 다시 쓰기(call_cache)와 원본 버전 단위 누적 예산. 메모리 저장소·녹화 응답·가짜 연결만 씁니다(네트워크 없음)."""

import dataclasses
import json
from pathlib import Path

import pytest
from helpers import ai_part, example, source_for
from test_pipeline import answers, raw_event, run

from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.extract import run_extraction
from mujuthaek_extraction.model import ModelError, ModelImage, ModelRequest, ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.call_cache import CachedModel, MemoryCallCache, cache_key, response_code_hash
from mujuthaek_extraction.model.factory import ModelFactory, NoticeModels
from mujuthaek_extraction.model.local_ai import LocalChatModel
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.rules.housing_notice import RULES as SPLIT_RULES
from mujuthaek_extraction.store import JobStore

RULES = dataclasses.replace(SPLIT_RULES, large_text_chars=None)
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": False}
REQUEST = ModelRequest("v", "structure", "지시", "원문", "할 일", SCHEMA, 100)
IDENTITY = {"provider": "test"}


def settings(**overrides):
    base = dict(db_url="", rabbitmq_url="", s3_endpoint=None, s3_bucket="b", s3_access_key=None, s3_secret_key=None, env_file=Path("없는.env"))
    return Settings(**(base | overrides))


def cached(script, cache=None):
    inner = RecordedModel(script, "gpt-6-luna")
    return inner, CachedModel(inner, cache if cache is not None else MemoryCallCache(), lambda request: IDENTITY, "gpt-6-luna")


# ---------- 열쇠 ----------


def test_key_changes_with_anything_that_decides_the_answer():
    base = cache_key(REQUEST, IDENTITY)
    assert cache_key(dataclasses.replace(REQUEST), dict(IDENTITY)) == base  # 같은 내용이면 같은 열쇠
    image = ModelImage("그림 1", "image/png", b"png-1")
    variants = [
        dataclasses.replace(REQUEST, user="원문 (바뀐 PDF)"),
        dataclasses.replace(REQUEST, system="지시 v2"),
        dataclasses.replace(REQUEST, instructions="할 일 + 이전 응답 오류"),
        dataclasses.replace(REQUEST, output_schema={**SCHEMA, "required": []}),
        dataclasses.replace(REQUEST, shared_schema={"type": "object"}),
        dataclasses.replace(REQUEST, max_output_tokens=200),
        dataclasses.replace(REQUEST, call_name="documents"),
        dataclasses.replace(REQUEST, prompt_version="v2"),
        dataclasses.replace(REQUEST, images=(image,)),
    ]
    keys = {cache_key(v, IDENTITY) for v in variants}
    assert len(keys) == len(variants) and base not in keys
    assert cache_key(dataclasses.replace(REQUEST, images=(dataclasses.replace(image, data=b"png-2"),)), IDENTITY) != cache_key(variants[-1], IDENTITY)
    assert cache_key(REQUEST, {"provider": "test", "effort": "low"}) != base


def test_provider_identity_follows_model_settings_and_has_no_key():
    medium = OpenAIResponsesModel("sk-test-not-real", reasoning_effort="medium").cache_identity(REQUEST)
    low = OpenAIResponsesModel("sk-test-not-real", reasoning_effort="low").cache_identity(REQUEST)
    other = OpenAIResponsesModel("sk-test-not-real", model="gpt-6-other").cache_identity(REQUEST)
    light = OpenAIResponsesModel("sk-test-not-real", light_calls=frozenset({"structure"})).cache_identity(REQUEST)
    assert len({json.dumps(i, sort_keys=True) for i in (medium, low, other)}) == 3
    assert light == low  # 가벼운 호출 강도(low)로 보내는 본문이 같으면 같은 답으로 봅니다
    assert medium == OpenAIResponsesModel("sk-another-not-real").cache_identity(REQUEST)  # 키는 열쇠에 들어가지 않습니다
    assert "sk-test" not in json.dumps(medium) and medium["code"] == response_code_hash()
    assert LocalChatModel("http://a/v1", "qwen").cache_identity(REQUEST) != LocalChatModel("http://a/v1", "llama").cache_identity(REQUEST)


# ---------- 저장·다시 쓰기 ----------


def test_successful_answer_is_reused_without_calling_or_costing():
    first = ModelResponse('{"a": "값"}', "gpt-6-luna", StopReason.END, input_tokens=900, output_tokens=40, cached_input_tokens=100)
    inner, model = cached({"structure": [first]})
    assert model.complete(REQUEST) is first
    again = model.complete(REQUEST)
    assert len(inner.requests) == 1  # 두 번째는 보내지 않음
    assert (again.raw_text, again.model_id, again.stop_reason, again.cache_hit) == (first.raw_text, "gpt-6-luna", StopReason.END, True)
    assert (again.input_tokens, again.output_tokens, again.cached_input_tokens, again.reasoning_tokens) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "answer",
    [
        ModelResponse('{"a": "잘림', "m", StopReason.MAX_TOKENS),
        ModelResponse("{}", "m", StopReason.REFUSED),
        ModelResponse("JSON 아님", "m", StopReason.END),
        ModelResponse("[1]", "m", StopReason.END),
        ModelResponse('{"b": "형식 위반"}', "m", StopReason.END),
    ],
    ids=["max-tokens", "refused", "not-json", "not-object", "schema-invalid"],
)
def test_incomplete_or_invalid_answers_are_not_stored(answer):
    inner, model = cached({"structure": [answer, '{"a": "다시 받은 답"}']})
    model.complete(REQUEST)
    assert json.loads(model.complete(REQUEST).raw_text) == {"a": "다시 받은 답"}  # 다시 처리하면 새로 받습니다
    assert len(inner.requests) == 2


def test_errors_are_not_stored_and_propagate():
    inner, model = cached({"structure": [ModelError("HTTP 500", transient=True), '{"a": "x"}']})
    with pytest.raises(ModelError):
        model.complete(REQUEST)
    assert model.complete(REQUEST).cache_hit is False and len(inner.requests) == 2


def test_broken_store_does_not_stop_extraction():
    class Broken:
        def get(self, key):
            raise OSError("DB 끊김")

        def put(self, *args):
            raise OSError("DB 끊김")

    inner, model = cached({"structure": ['{"a": "x"}', '{"a": "x"}']}, Broken())
    assert model.complete(REQUEST).raw_text == '{"a": "x"}' and model.complete(REQUEST).cache_hit is False
    assert len(inner.requests) == 2


def test_purge_removes_only_old_rows():
    now = [1_000_000.0]
    cache = MemoryCallCache(clock=lambda: now[0])
    cache.put("old", "m", "structure", {"rawText": "{}"}, None)
    now[0] += 91 * 86_400
    cache.put("new", "m", "structure", {"rawText": "{}"}, None)
    assert cache.purge(90) == 1 and set(cache.rows) == {"new"}


# ---------- 다시 처리할 때 ----------


def script_for(data):
    return {call.name: [json.dumps(ai_part(data, call.sections), ensure_ascii=False)] for call in RULES.calls}


def test_retry_after_partial_failure_resends_only_the_failed_call():
    data = example("housing")
    material = source_for("housing", data).material
    script = script_for(data)
    cache = MemoryCallCache()
    names = [call.name for call in RULES.calls]
    failing = names[1]
    first_inner, first_model = cached({**script, failing: [ModelError("HTTP 400", transient=False)]}, cache)
    first = run_extraction(RULES, material, first_model)
    assert [name for name, _ in first.failed_calls] == [failing]

    second_inner, second_model = cached(script_for(data), cache)
    second = run_extraction(RULES, material, second_model)
    assert [r.call_name for r in second_inner.requests] == [failing]  # 성공했던 호출은 보내지 않음
    assert second.failed_calls == []
    fresh = run_extraction(RULES, material, RecordedModel(script_for(data)))
    assert second.parts == fresh.parts  # 다시 쓴 응답으로 만든 결과가 새로 받은 결과와 같음
    assert [a.input_tokens for a in second.attempts if a.call_name != failing] == [0] * (len(names) - 1)


def test_changed_source_text_never_reuses_old_answers():
    data = example("housing")
    material = source_for("housing", data).material
    cache = MemoryCallCache()
    run_extraction(RULES, material, cached(script_for(data), cache)[1])
    inner, model = cached(script_for(data), cache)
    run_extraction(RULES, dataclasses.replace(material, text=material.text + "\n정정 공고: 접수 기간 연장"), model)
    assert [r.call_name for r in inner.requests] == [call.name for call in RULES.calls]


# ---------- 모델 묶음 ----------


def test_factory_wraps_paid_model_outside_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    factory = ModelFactory(settings(local_ai_url="http://localhost:11434/v1"))
    models = factory.for_notice(cache=MemoryCallCache())
    assert isinstance(models.primary, CachedModel) and isinstance(models.primary.model, LocalChatModel)
    assert isinstance(models.fallback, CachedModel) and isinstance(models.fallback.model, BudgetedModel)
    assert models.fallback.model.budget is models.budget
    off = ModelFactory(settings(local_ai_url="http://localhost:11434/v1", call_cache=False)).for_notice(cache=MemoryCallCache())
    assert isinstance(off.primary, LocalChatModel) and isinstance(off.fallback, BudgetedModel)  # 끄면 이전과 같음
    no_local = ModelFactory(settings()).for_notice(cache=MemoryCallCache())
    assert isinstance(no_local.primary, CachedModel) and no_local.fallback is None


def test_cache_hit_does_not_use_budget():
    budget = Budget("gpt-6-luna", 0.5)
    paid = ModelResponse('{"a": "x"}', "gpt-6-luna", StopReason.END, input_tokens=10_000, output_tokens=1_000)
    cache = MemoryCallCache()
    inner = RecordedModel({"structure": [paid]})
    model = CachedModel(BudgetedModel(inner, budget), cache, lambda request: IDENTITY, "gpt-6-luna")
    model.complete(REQUEST)
    spent = budget.spent_usd
    assert spent > 0 and model.complete(REQUEST).cache_hit and budget.spent_usd == spent


def test_recorded_mode_is_never_cached(tmp_path):
    (tmp_path / "structure.json").write_text(json.dumps(['{"a": "x"}']), encoding="utf-8")
    models = ModelFactory(settings(model_mode="recorded", recorded_dir=tmp_path)).for_notice(cache=MemoryCallCache())
    assert not isinstance(models.primary, CachedModel)


# ---------- 누적 예산 ----------


def test_budget_counts_spend_of_earlier_attempts():
    request = ModelRequest("v", "structure", "s" * 1000, "u" * 1000, "i", SCHEMA, 10_000)
    worst = Budget("gpt-6-luna", 1.0).worst_case(request)
    assert Budget("gpt-6-luna", 0.5, prior_usd=0.5 - worst).allow(request)
    exhausted = Budget("gpt-6-luna", 0.5, prior_usd=0.5 - worst / 2)
    assert not exhausted.allow(request)
    inner = RecordedModel({"structure": ['{"a": "x"}']})
    with pytest.raises(ModelError, match="비용 상한") as error:
        BudgetedModel(inner, exhausted).complete(request)
    assert error.value.code == "BUDGET" and inner.requests == []


def test_retry_with_spent_budget_fails_like_budget_exceeded_and_records_only_its_own_cost(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    models = ModelFactory(settings()).for_notice(spent_before_usd=0.5)
    paid = RecordedModel(answers(), "gpt-6-luna")
    models.primary.model = paid  # 실제 연결 대신 녹화 응답 (예산 감싸기는 그대로)
    outcome = run(raw_event(), models)
    assert outcome.status == "FAILED" and "비용 상한" in outcome.error and paid.requests == []
    assert outcome.cost_usd == 0.0 and models.budget.prior_usd == 0.5
    assert {c["error"] for c in outcome.usage["calls"]} == {"BUDGET"}


def test_spent_before_reads_retryable_jobs_of_same_raw_version():
    class Conn:
        autocommit = False

        def __init__(self):
            self.sql = []

        def execute(self, sql, params=()):
            self.sql.append((sql, params))
            return self

        def fetchone(self):
            # 작업 기록의 다시 처리 대상 비용 + 저장 전에 중단된 처리의 비용(비용 장부, 2026-10-21)
            return (0.01,) if "extraction_spend" in self.sql[-1][0] else (0.1234,)

    conn = Conn()
    event = raw_event()
    assert JobStore(conn).spent_before(event) == 0.1334
    (jobs, params), (orphan, orphan_params) = conn.sql[-2], conn.sql[-1]
    assert "raw_post_id = %s and raw_version = %s" in jobs and "status in ('FAILED', 'WAITING_SOURCE')" in jobs
    assert params == (event["payload"]["rawPostId"], 1)
    assert "extraction_spend" in orphan and "job_id is null" in orphan and orphan_params == params
    JobStore(conn).spent_before({**event, "payload": {}})
    assert "event_id = %s" in conn.sql[-2][0] and conn.sql[-2][1] == (event["eventId"],)
    assert JobStore(conn).spent_before({"payload": {}}) == 0.0


def test_worker_passes_cache_and_prior_spend_to_models(monkeypatch):
    from mujuthaek_extraction import worker
    from mujuthaek_extraction.model.call_cache import PostgresCallCache

    seen = {}

    class Factory:
        def for_notice(self, cache=None, spent_before_usd=0.0, ledger=None):
            seen.update(cache=cache, spent=spent_before_usd)
            return NoticeModels(RecordedModel(answers()), None)

    class Store:
        conn = object()

        def spent_before(self, raw_event):
            return 0.2

    processor = worker.Processor.__new__(worker.Processor)
    processor.models, processor.reader, processor.regions = Factory(), None, None
    processor.settings = settings(require_pdf=False)
    monkeypatch.setattr(worker, "process", lambda raw_event, **kwargs: kwargs["models"])
    processor.run(raw_event(), Store())
    assert isinstance(seen["cache"], PostgresCallCache) and seen["spent"] == 0.2
    processor.run(raw_event())
    assert seen == {"cache": None, "spent": 0.0}


def test_purge_follows_setting():
    from mujuthaek_extraction.worker import purge_call_cache

    class Conn:
        def __init__(self):
            self.sql, self.rowcount = [], 3

        def execute(self, sql, params=()):
            self.sql.append((sql, params))
            return self

    class Store:
        def __init__(self):
            self.conn = Conn()

    store = Store()
    assert purge_call_cache(settings(call_cache_days=30), store) == 3
    assert "delete from extraction_call_cache" in store.conn.sql[0][0] and store.conn.sql[0][1] == (30,)
    off = Store()
    assert purge_call_cache(settings(call_cache=False), off) == 0 and off.conn.sql == []
