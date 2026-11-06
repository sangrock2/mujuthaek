"""V2 그래프(EXTRACTION_ENGINE=v2): 구조 담당 먼저, 나머지 담당은 Send로 동시에, 마무리는 V1과 같은 결합·검증·게시. 유료 호출 없음."""

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
    monkeypatch.setenv("EXTRACTION_ENGINE", "v2")
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


def test_structure_is_extracted_the_v1_way_and_without_chat_models_the_other_workers_do_nothing(v2):
    # 구조(공고·위치·공급)는 V1 방식(공급표 코드 + 한 번 호출). 채팅 모델이 없는 실행(로컬 AI·녹화)에서는 섹션 에이전트가 돌지 않음
    recorded = RecordedModel(answers(), "local")
    outcome = run(raw_event(), NoticeModels(recorded, None, names={"primary": "local"}))
    assert [r.call_name for r in recorded.requests] == ["structure"]
    assert outcome.candidate["notice"]["title"] and outcome.usage["v2"]["calls"] == [] and outcome.status != "COMPLETED"


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
