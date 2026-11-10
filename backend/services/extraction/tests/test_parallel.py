"""구조 호출 뒤 섹션 호출 병렬 실행(EXTRACTION_PARALLEL_CALLS)과 예산 동시성. 녹화 응답·가짜 모델만 씁니다(네트워크 없음)."""

import json
import threading
import time

import pytest
from helpers import ai_part, every_call, example, source_for
from test_pipeline import answers, raw_event, run

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.extract import run_extraction
from mujuthaek_extraction.model import ModelError, ModelRequest, ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.pipeline import process
from mujuthaek_extraction.rules.housing_notice import RULES

DELAY = 0.2


class SlowModel:
    """녹화 응답을 내주기 전에 DELAY초 기다리고, 동시에 처리 중인 호출 수의 최댓값을 잽니다."""

    def __init__(self, script, delay=DELAY):
        self.inner, self.delay = RecordedModel(script), delay
        self.lock, self.active, self.most = threading.Lock(), 0, 0

    @property
    def requests(self):
        return self.inner.requests

    def complete(self, request):
        with self.lock:
            self.active += 1
            self.most = max(self.most, self.active)
        try:
            time.sleep(self.delay)
            return self.inner.complete(request)
        finally:
            with self.lock:
                self.active -= 1


def script_for(data, **overrides):
    script = {call.name: [json.dumps(ai_part(data, call.sections), ensure_ascii=False)] for call in every_call(RULES)}
    return script | overrides


def material():
    return source_for("housing", example("housing")).material


def call_names():
    return [call.name for call in RULES.calls_for(material())]


def timed_run(script, parallel, **kwargs):
    model = SlowModel(script, **kwargs)
    start = time.perf_counter()
    result = run_extraction(RULES, material(), model, parallel=parallel, sleep=lambda seconds: None)
    return result, model, time.perf_counter() - start


def same_run(a, b):
    assert a.parts == b.parts and a.attempts == b.attempts and a.failed_calls == b.failed_calls and a.raw_responses == b.raw_responses


def test_section_calls_run_together_after_structure_and_result_is_identical():
    data = example("housing")
    names = call_names()
    assert names[0] == "structure" and len(names) >= 5  # 구조 + 섹션 호출 4개 이상(큰 공고 나눠 부르기)
    sequential, slow, sequential_seconds = timed_run(script_for(data), parallel=1)
    together, fast, together_seconds = timed_run(script_for(data), parallel=4)
    rest = len(names) - 1
    assert sequential_seconds >= DELAY * len(names)
    assert together_seconds < DELAY * (len(names) - rest + 2)  # 구조 1번 + 나머지가 한 번에 (여유 1번)
    assert slow.most == 1 and fast.most == min(4, rest)
    assert fast.requests[0].call_name == "structure" and {r.call_name for r in fast.requests[1:]} == set(names[1:])
    same_run(sequential, together)
    source = source_for("housing", data)
    first = json.dumps(assemble(sequential.parts, source).candidate, ensure_ascii=False, sort_keys=True)
    assert first == json.dumps(assemble(together.parts, source).candidate, ensure_ascii=False, sort_keys=True)


def test_one_parallel_call_keeps_old_request_order():
    _, model, _ = timed_run(script_for(example("housing")), parallel=1, delay=0)
    assert [r.call_name for r in model.requests] == call_names()


def test_retries_repairs_and_truncation_behave_the_same_in_parallel():
    data = example("housing")
    names = call_names()
    good = script_for(data)

    def script():
        cut = ModelResponse('{"quotes": [', "m", StopReason.MAX_TOKENS)
        return good | {
            names[1]: ["{잘못된 JSON", *good[names[1]]],  # 형식 재요청
            names[2]: [ModelError("HTTP 503", transient=True), *good[names[2]]],  # 일시 오류 재시도
            names[3]: [cut, *good[names[3]]],  # 잘림 재요청
            names[4]: [ModelError("HTTP 400", transient=False)],  # 실패 → 그 섹션만 FAILED
        }

    sequential, _, _ = timed_run(script(), parallel=1, delay=0.01)
    together, _, _ = timed_run(script(), parallel=4, delay=0.01)
    same_run(sequential, together)
    assert [name for name, _ in together.failed_calls] == [names[4]]
    assert [a.repair for a in together.attempts if a.call_name == names[1]] == [False, True]


def test_failed_structure_sends_no_section_calls():
    data = example("housing")
    result, model, _ = timed_run(script_for(data, structure=[ModelError("HTTP 400", transient=False)]), parallel=4, delay=0)
    assert [r.call_name for r in model.requests] == ["structure"]
    assert [name for name, _ in result.failed_calls] == call_names()


def test_unexpected_error_in_a_parallel_call_is_raised():
    class Boom(SlowModel):
        def complete(self, request):
            if request.call_name == call_names()[2]:
                raise RuntimeError("결함")
            return super().complete(request)

    model = Boom(script_for(example("housing")), delay=0)
    with pytest.raises(RuntimeError, match="결함"):
        run_extraction(RULES, material(), model, parallel=4)


def test_pipeline_outcome_is_the_same_with_parallel_calls():
    def outcome(parallel):
        from datetime import UTC, datetime

        from test_pipeline import REGIONS, new_event

        from mujuthaek_extraction.intake import InMemorySourceReader

        models = NoticeModels(RecordedModel(answers(), "local"), None, names={"primary": "local"})
        clock = lambda: datetime(2026, 10, 15, tzinfo=UTC)  # noqa: E731
        return process(
            raw_event(),
            models=models,
            reader=InMemorySourceReader(),
            regions=REGIONS,
            clock=clock,
            new_event=new_event,
            require_pdf=False,
            parallel_calls=parallel,
        )

    one, four = outcome(1), outcome(4)
    assert one.status == four.status == "COMPLETED"
    assert json.dumps(one.event, sort_keys=True, ensure_ascii=False) == json.dumps(four.event, sort_keys=True, ensure_ascii=False)
    assert (one.attempts, one.responses, one.candidate) == (four.attempts, four.responses, four.candidate)
    assert run(raw_event(), NoticeModels(RecordedModel(answers()), None)).status == "COMPLETED"  # 기본은 하나씩


# ---------- 예산 동시성 ----------


REQUEST = ModelRequest("v", "schedules", "s" * 2000, "u" * 2000, "i", {"type": "object"}, 8_000)


def test_concurrent_calls_cannot_jointly_exceed_the_limit():
    worst = Budget("gpt-6-luna", 1.0).worst_case(REQUEST)
    budget = Budget("gpt-6-luna", limit_usd=worst * 3.5)
    entered, lock, start = [], threading.Lock(), threading.Barrier(20)

    class Slow:
        def complete(self, request):
            with lock:
                entered.append(1)
            time.sleep(0.2)
            # 최악에 가까운 실제 사용량 (입력 전부 캐시 쓰기 + 출력 한도 전부)
            return ModelResponse("{}", "gpt-6-luna", StopReason.END, input_tokens=4001, cache_write_tokens=4001, output_tokens=8_000)

    model = BudgetedModel(Slow(), budget)
    refused = []

    def call():
        start.wait()
        try:
            model.complete(REQUEST)
        except ModelError as error:
            refused.append(error.code)

    threads = [threading.Thread(target=call) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(entered) == 3 and refused == ["BUDGET"] * 17  # 확인만 하고 잡아 두지 않으면 20개가 모두 나갑니다
    assert budget.spent_usd <= budget.limit_usd and len(budget.calls) == 3


def test_released_and_billed_failures_settle_reservations():
    worst = Budget("gpt-6-luna", 1.0).worst_case(REQUEST)

    class Fails:
        def __init__(self, billed):
            self.billed = billed

        def complete(self, request):
            raise ModelError("실패", transient=True, maybe_billed=self.billed)

    budget = Budget("gpt-6-luna", limit_usd=worst * 2.5)
    with pytest.raises(ModelError):
        BudgetedModel(Fails(False), budget).complete(REQUEST)
    assert budget.spent_usd == 0 and budget.allow(REQUEST)  # 청구되지 않은 실패는 잡아 둔 것을 풉니다
    with pytest.raises(ModelError):
        BudgetedModel(Fails(True), budget).complete(REQUEST)
    assert budget.spent_usd == pytest.approx(worst) and budget.calls == [pytest.approx(worst)]


def test_recorded_model_hands_out_each_answer_once_across_threads():
    model = RecordedModel({"x": [str(i) for i in range(200)]})
    request = ModelRequest("v", "x", "", "", "", {}, 1)
    got, lock = [], threading.Lock()

    def take():
        for _ in range(50):
            text = model.complete(request).raw_text
            with lock:
                got.append(text)

    threads = [threading.Thread(target=take) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(got, key=int) == [str(i) for i in range(200)] and len(model.requests) == 200


def test_parallel_setting(monkeypatch):
    monkeypatch.setenv("EXTRACTION_PARALLEL_CALLS", "1")
    assert Settings.from_env().parallel_calls == 1
    monkeypatch.delenv("EXTRACTION_PARALLEL_CALLS")
    assert Settings.from_env().parallel_calls == 4


# ---------- 병렬 호출 간격(EXTRACTION_PARALLEL_STAGGER_SECONDS) ----------


class ArrivalModel(SlowModel):
    """도착한(처리를 시작한) 순서대로 호출 이름을 적습니다. 응답은 DELAY 뒤에 내줍니다."""

    def __init__(self, script, delay):
        super().__init__(script, delay)
        self.arrived = []

    def complete(self, request):
        with self.lock:
            self.arrived.append(request.call_name)
        return super().complete(request)


class LaunchClock:
    """가짜 sleep: 실제로 기다리지 않고, 기다릴 때마다 그때까지 모델에 도착한 호출 이름을 적습니다.
    다음 호출은 sleep이 끝난 뒤에야 내보내므로, 앞서 내보낸 호출이 도착할 때까지만(최대 5초) 기다려 순서를 확정합니다."""

    def __init__(self, model):
        self.model, self.waits = model, []

    def __call__(self, seconds):
        expected = 2 + len(self.waits)  # 구조 호출 + 지금까지 내보낸 섹션 호출
        deadline = time.monotonic() + 5
        while len(self.model.arrived) < expected and time.monotonic() < deadline:
            time.sleep(0.001)
        with self.model.lock:
            self.waits.append((seconds, list(self.model.arrived)))


def staggered_run(stagger, parallel=4):
    model = ArrivalModel(script_for(example("housing")), delay=0.2)
    clock = LaunchClock(model)
    result = run_extraction(RULES, material(), model, parallel=parallel, stagger=stagger, sleep=clock)
    return result, model, clock


def test_section_calls_are_launched_one_stagger_apart_in_call_order():
    names = call_names()
    result, model, clock = staggered_run(1.5)
    # 섹션 호출 사이마다 한 번씩 1.5초를 기다리고, 기다릴 때마다 앞 호출까지만 나가 있습니다(호출 순서대로)
    assert [seconds for seconds, _ in clock.waits] == [1.5] * (len(names) - 2)
    for number, (_, started) in enumerate(clock.waits, start=2):
        assert started == names[:number]
    assert model.arrived == names
    assert model.most == min(4, len(names) - 1)  # 응답을 기다리지 않고 내보내므로 여전히 함께 처리됩니다
    same_run(result, staggered_run(0)[0])  # 간격이 있어도 결과는 같습니다
    same_run(result, timed_run(script_for(example("housing")), parallel=1, delay=0)[0])


def test_no_stagger_or_sequential_calls_never_wait():
    assert staggered_run(0)[2].waits == []
    assert staggered_run(1.5, parallel=1)[2].waits == []  # 하나씩 부를 때는 간격을 두지 않습니다


def test_stagger_setting_and_pipeline_pass_through(monkeypatch):
    monkeypatch.delenv("EXTRACTION_PARALLEL_STAGGER_SECONDS", raising=False)
    assert Settings.from_env().parallel_stagger_seconds == 1.5
    monkeypatch.setenv("EXTRACTION_PARALLEL_STAGGER_SECONDS", "0")
    assert Settings.from_env().parallel_stagger_seconds == 0.0

    from datetime import UTC, datetime

    from test_pipeline import REGIONS, new_event

    from mujuthaek_extraction import extract
    from mujuthaek_extraction.intake import InMemorySourceReader

    waits = []
    monkeypatch.setattr(extract.time, "sleep", waits.append)  # 실제로 기다리지 않습니다
    models = NoticeModels(RecordedModel(answers(), "local"), None, names={"primary": "local"})
    outcome = process(
        raw_event(),
        models=models,
        reader=InMemorySourceReader(),
        regions=REGIONS,
        clock=lambda: datetime(2026, 10, 15, tzinfo=UTC),
        new_event=new_event,
        require_pdf=False,
        parallel_calls=4,
        parallel_stagger=0.75,
    )
    assert outcome.status == "COMPLETED" and waits and set(waits) == {0.75}
