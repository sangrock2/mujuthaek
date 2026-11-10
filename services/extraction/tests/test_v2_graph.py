"""V2 그래프(유일한 엔진): 구조 담당 먼저, 나머지 담당은 Send로 동시에, 마무리는 V1과 같은 결합·검증·게시. 유료 호출 없음."""

import json
import threading
from datetime import UTC, datetime

import pytest
from events import raw_event
from helpers import REGIONS
from test_pipeline import answers, run

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake import InMemorySourceReader
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.pipeline import process
from mujuthaek_extraction.v2 import graph
from mujuthaek_platform.events import new_event


def models():
    return NoticeModels(RecordedModel({}, "local"), None, names={"primary": "local"})


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr(graph, "AGENTS", {})
    return graph.AGENTS


def test_section_agents_run_structure_first_then_in_parallel_and_the_notice_is_published(v2):
    recorded = answers()
    seen, lock = [], threading.Lock()

    def fake(spec, state, rt):
        with lock:
            seen.append((spec.name, state.get("structure") is not None, state["document"].lines[0].id))
        return [json.loads(recorded[spec.name][0])], [{"agent": spec.name, "costUsd": 0.0}]

    for name in ("structure", "schedules", "eligibility", "selection", "documents"):
        v2[name] = fake
    outcome = run(raw_event(), models())
    assert outcome.status == "COMPLETED" and outcome.error is None
    assert tools().validate(outcome.event, "events/extraction.completed.v1.json") == []
    assert seen[0] == ("structure", False, "p1.1")  # 구조 담당은 구조 요약 없이 먼저
    assert sorted(name for name, has_structure, _ in seen[1:] if has_structure) == ["documents", "eligibility", "schedules", "selection"]
    assert {c["agent"] for c in outcome.usage["v2"]["calls"]} == {"structure", "schedules", "eligibility", "selection", "documents"}


def test_when_the_structure_step_fails_the_section_agents_are_not_sent(v2):
    # 2026-11-10 코드 검토: 구조 단계가 실패해도 담당을 모두 돌려(결과는 어차피 FAILED) 다시 처리할 때마다 공고 예산을 다 씀. V1은 건너뜀
    seen = []

    def failed_structure(spec, state, rt):
        return [{"quotes": [], "coverage": {s: {"status": "FAILED", "reason": "잘림"} for s in spec.sections}}], [{"agent": spec.name}]

    def worker(spec, state, rt):
        seen.append(spec.name)
        return [], []

    v2["structure"] = failed_structure
    for name in ("schedules", "eligibility", "selection", "documents"):
        v2[name] = worker
    outcome = run(raw_event(), models())
    assert outcome.status == "FAILED" and seen == []


def test_the_job_record_names_the_paid_model_when_agents_ran_even_with_a_local_primary(v2):
    # 2026-11-10 코드 검토: 로컬 AI + 유료 대체 설정에서 담당이 모두 유료로 돌았는데 작업 기록 모델이 늘 「local」이었음
    recorded = answers()
    for name in ("structure", "schedules", "eligibility", "selection", "documents"):
        v2[name] = lambda spec, state, rt: ([json.loads(recorded[spec.name][0])], [{"agent": spec.name, "costUsd": 0.0}])
    names = {"primary": "local", "fallback": "gpt-6-luna"}
    outcome = run(raw_event(), NoticeModels(RecordedModel({}, "local"), None, names=names))
    assert outcome.status == "COMPLETED" and outcome.model_used == "gpt-6-luna"


def test_without_chat_models_the_structure_node_extracts_every_section_the_v1_way(v2):
    # 채팅 모델이 없는 실행(로컬 AI만·녹화·대역)은 담당 에이전트를 돌릴 수 없어, 구조 노드가 V1 방식 추출 전체를 돌리고 담당 없이 마무리로 감
    # (2026-11-10 V1 정해진 단계 그래프를 걷어내며 이 길로 옮김: 그 그래프와 같은 호출·결과)
    recorded = RecordedModel(answers(), "local")
    outcome = run(raw_event(), NoticeModels(recorded, None, names={"primary": "local"}))
    assert [a["call_name"] for a in outcome.attempts] == ["structure", "schedules", "eligibility", "selection", "documents"]
    assert outcome.status == "COMPLETED" and outcome.event["payload"]["reviewStatus"] == "AUTO_PASSED" and "v2" not in outcome.usage


def test_section_agents_start_one_parallel_stagger_apart_like_v1_section_calls(v2, monkeypatch):
    # 한꺼번에 첫 호출을 보내면 하나는 데워 둔 캐시를 못 읽음(V1 섹션 호출과 같은 현상) → V1과 같은 간격으로 차례로 출발
    recorded, waits = answers(), []
    monkeypatch.setattr(graph, "SLEEP", waits.append)
    for name in ("structure", "schedules", "eligibility", "selection", "documents"):
        v2[name] = lambda spec, state, rt: ([json.loads(recorded[spec.name][0])], [])
    clock = lambda: datetime(2026, 10, 15, tzinfo=UTC)  # noqa: E731
    outcome = process(
        raw_event(), models=models(), reader=InMemorySourceReader(), regions=REGIONS, clock=clock, new_event=new_event, require_pdf=False, parallel_stagger=1.5
    )
    assert outcome.status == "COMPLETED" and sorted(waits) == [0.0, 1.5, 3.0, 4.5]


def test_conclude_rechecks_the_structure_sections_the_v1_way_and_leaves_agent_sections_to_the_agents(v2):
    # 2026-11-06 23건 측정: 구조 단계는 V1 방식인데 V1의 재확인이 없어, V1이 재확인으로 되살린 가격·공고 핵심이 V2에서 검수로 감
    recorded = answers()
    clean = json.loads(recorded["structure"][0])
    structure, eligibility = json.loads(recorded["structure"][0]), json.loads(recorded["eligibility"][0])
    structure["supplyGroups"][0]["prices"][1]["sourceAmount"] = "120000"  # 인용에 없는 월임대료(원문은 100000원)
    eligibility["quotes"].append({"ref": "fake", "documentId": "text", "text": "원문에 없는 무주택 문장입니다"})
    eligibility["eligibility"][1]["quoteRefs"].append("fake")
    broken = {"structure": structure, "eligibility": eligibility}
    for name in ("structure", "schedules", "eligibility", "selection", "documents"):
        v2[name] = lambda spec, state, rt: ([broken.get(spec.name) or json.loads(recorded[spec.name][0])], [])
    fixed = {"quotes": clean["quotes"], "supplyGroups": [clean["supplyGroups"][0]], "coverage": {"supplyGroups": {"status": "EXTRACTED", "reason": None}}}
    model = RecordedModel({"recheck": [json.dumps(fixed, ensure_ascii=False)]}, "local")
    outcome = run(raw_event(), NoticeModels(model, None, names={"primary": "local"}))
    group, condition = clean["supplyGroups"][0]["id"], eligibility["eligibility"][1]["id"]
    assert [r.call_name for r in model.requests] == ["recheck"]
    assert group in model.requests[0].instructions and condition not in model.requests[0].instructions  # 담당 섹션 문제는 담당 몫
    assert outcome.usage["recheck"]["accepted"] and outcome.usage["recheck"]["rechecked"] == [f"supplyGroups/{group}"]
    targets = [issue["target"] for issue in outcome.candidate["quality"]["reviewIssues"]]
    assert not any(t.startswith("/supplyGroups") for t in targets) and "/eligibility/1" in targets
    rent = next(p for p in outcome.candidate["supplyGroups"][0]["prices"] if p["kind"] == "MONTHLY_RENT")
    assert rent["amountKrw"] == 100000


def test_section_agents_follow_the_parallel_calls_setting(v2, monkeypatch):
    # 2026-11-10 코드 검토: V2는 EXTRACTION_PARALLEL_CALLS를 읽지 않아 1로 두어도 담당이 모두 동시에 돌았음(429·예산 예약 충돌)
    import time

    recorded = answers()
    monkeypatch.setattr(graph, "SLEEP", lambda seconds: None)
    clock = lambda: datetime(2026, 10, 15, tzinfo=UTC)  # noqa: E731

    def busiest(parallel):
        active, peak, lock = [0], [0], threading.Lock()

        def fake(spec, state, rt):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return [json.loads(recorded[spec.name][0])], []

        for name in ("structure", "schedules", "eligibility", "selection", "documents"):
            v2[name] = fake
        outcome = process(
            raw_event(),
            models=models(),
            reader=InMemorySourceReader(),
            regions=REGIONS,
            clock=clock,
            new_event=new_event,
            require_pdf=False,
            parallel_calls=parallel,
        )
        assert outcome.status == "COMPLETED"
        return peak[0]

    assert busiest(1) == 1
    assert busiest(4) > 1
