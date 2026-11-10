"""하루·월 전체 비용 상한과 비용 장부(2026-10-21): 공고당 상한만으로는 공고 수·버전 수만큼 비용이 열려 있었습니다."""

import threading
from types import SimpleNamespace

import pytest
from test_worker_parts import MemoryStore, bare_processor, raw_event

from mujuthaek_extraction.model import ModelError, ModelRequest, ModelResponse, StopReason
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.pipeline import Outcome


class FakeLedger:
    """DB 장부 대신: 합계와 상한만 흉내 냅니다."""

    def __init__(self, daily=30.0, spent=0.0):
        self.daily, self.spent, self.entries, self.refused = daily, spent, {}, None
        self.run_id = "run-1"

    def reserve(self, model, worst):
        if self.spent + sum(self.entries.values()) + worst > self.daily:
            self.refused = f"하루 비용 상한(${self.daily:.2f})"
            return None
        entry = f"e{len(self.entries)}"
        self.entries[entry] = worst
        return entry

    def settle(self, entry, cost):
        self.entries.pop(entry)
        self.spent += cost

    def release(self, entry):
        self.entries.pop(entry)

    def room(self, worst):
        return None if self.spent + worst <= self.daily else "하루 비용 상한($30.00)"

    def close(self):
        pass


def request():
    return ModelRequest(prompt_version="t", call_name="notice", system="s", user="u" * 100, instructions="", output_schema={}, max_output_tokens=1000)


class Echo:
    def complete(self, req):
        return ModelResponse(raw_text="{}", model_id="gpt-6-luna", stop_reason=StopReason.END, input_tokens=100, output_tokens=10)


def test_global_cap_refuses_call_and_names_the_reason():
    ledger = FakeLedger(daily=0.0001)
    budget = Budget("gpt-6-luna", 0.5, ledger=ledger)
    with pytest.raises(ModelError) as error:
        BudgetedModel(Echo(), budget).complete(request())
    assert error.value.code == "GLOBAL_BUDGET" and "하루 비용 상한" in str(error.value)
    assert budget.refusal and budget.spent_usd == 0


def test_ledger_gets_actual_cost_after_response():
    ledger = FakeLedger()
    budget = Budget("gpt-6-luna", 0.5, ledger=ledger)
    BudgetedModel(Echo(), budget).complete(request())
    assert ledger.entries == {} and ledger.spent == pytest.approx(budget.spent_usd) and ledger.spent > 0


def test_unbilled_failure_releases_the_ledger_entry():
    class Down:
        def complete(self, req):
            raise ModelError("연결 안 됨", transient=True)

    ledger = FakeLedger()
    with pytest.raises(ModelError):
        BudgetedModel(Down(), Budget("gpt-6-luna", 0.5, ledger=ledger)).complete(request())
    assert ledger.entries == {} and ledger.spent == 0


def test_refused_run_is_not_published_and_stays_retryable():
    processor = bare_processor(lambda event: Outcome("COMPLETED"))
    budget = SimpleNamespace(refusal="하루 비용 상한($30.00)")
    from mujuthaek_extraction import worker

    processor.models = SimpleNamespace(for_notice=lambda cache=None, spent_before_usd=0.0, ledger=None: SimpleNamespace(budget=budget))
    processor._process = lambda event, models: Outcome("COMPLETED", event={"eventId": "x"}, cost_usd=0.2)
    outcome = worker.Processor.run(processor, raw_event())
    assert outcome.status == "FAILED" and outcome.event is None and outcome.retryable and outcome.cost_usd == 0.2


def test_no_new_run_starts_when_global_cap_is_near():
    from mujuthaek_extraction.worker import BudgetExhausted

    processor, store = bare_processor(lambda event: Outcome("COMPLETED")), MemoryStore()
    processor.open_ledger = lambda event: FakeLedger(daily=30.0, spent=29.8)  # 공고당 상한 $0.5가 남지 않음
    with pytest.raises(BudgetExhausted):
        processor.handle(store, raw_event())
    assert store.saved == 0


class StartStore(MemoryStore):
    def __init__(self, interrupted=0, published=False):
        super().__init__()
        self.interrupted, self.published, self.starts, self.outcomes, self.processed = interrupted, published, 0, [], []

    def interrupted_runs(self, event_id):
        return self.interrupted

    def record_start(self, event_id):
        self.starts += 1

    def version_published(self, raw_post_id, raw_version):
        return self.published

    def mark_processed(self, event_id, event_type):
        self.processed.append(event_id)

    def save(self, raw_event, outcome, run_id=None):
        self.outcomes.append(outcome)
        return super().save(raw_event, outcome, run_id)


def test_event_interrupted_three_times_is_not_processed_again():
    """저장 전에 프로세스가 죽는 메시지(메모리 부족·PDF 충돌)가 끝없이 다시 와 비용을 쓰지 않게 멈춥니다."""
    calls = []
    processor = bare_processor(lambda event: calls.append(event) or Outcome("COMPLETED"))
    store = StartStore(interrupted=3)
    processor.handle(store, raw_event())
    assert calls == [] and store.outcomes[0].status == "INTERRUPTED" and not store.outcomes[0].retryable
    healthy = StartStore(interrupted=2)
    processor.handle(healthy, raw_event())
    assert len(calls) == 1 and healthy.starts == 1


def test_same_published_version_with_new_event_id_is_skipped():
    calls = []
    processor = bare_processor(lambda event: calls.append(event) or Outcome("COMPLETED"))
    store = StartStore(published=True)
    event = raw_event()
    assert processor.handle(store, event) is None
    assert calls == [] and store.processed == [event["eventId"]]
    event["payload"]["reprocess"] = True  # 일부러 다시 처리하는 경우는 처리합니다
    event["eventId"] = "01929a3e-0000-7000-8000-0000000000e9"
    processor.handle(store, event)
    assert len(calls) == 1


def test_long_retry_keeps_health_beating():
    from mujuthaek_extraction.worker import beating

    beats = []
    health = SimpleNamespace(beat=beats.append)
    done = threading.Event()
    with beating(health, "retry", every=0.01):
        done.wait(0.1)
    assert beats.count("retry") >= 3
