"""V2 그래프(EXTRACTION_ENGINE=v2): 구조 담당 먼저, 나머지 담당은 Send로 동시에, 마무리는 V1과 같은 결합·검증·게시. 유료 호출 없음."""

import json
import threading

import pytest
from events import raw_event
from test_pipeline import answers, run

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.v2 import graph


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
