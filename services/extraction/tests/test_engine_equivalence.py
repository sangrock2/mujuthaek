"""기존 경로(legacy)와 그래프 경로(graph)가 같은 결과를 내는지 확인합니다 (AI 추출 에이전트화 1단계 완료 기준).

같은 녹화 응답으로 두 방식을 각각 돌려 Outcome 전체를 비교합니다. 걸린 시간처럼 실행마다 달라지는 값만 뺍니다.
"""

import copy
import json
from dataclasses import asdict

import pytest
from helpers import example, to_ai
from test_pipeline import answers, new_event, raw_event, run

from mujuthaek_extraction.engine import extraction_engine
from mujuthaek_extraction.graph import GRAPH
from mujuthaek_extraction.graph.build import _after_recheck
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.verify import VerificationReport

FAKE_QUOTE = "원문에 없는 무주택 문장입니다"


def _broken_answers():
    """자격 조건 하나에 원문에 없는 인용을 섞어 검증 문제가 생기게 합니다(재확인이 불림)."""
    script = answers()
    part = json.loads(script["eligibility"][0])
    part["quotes"].append({"ref": "fake", "documentId": "text", "text": FAKE_QUOTE})
    part["eligibility"][1]["quoteRefs"].append("fake")
    script["eligibility"] = [json.dumps(part, ensure_ascii=False)]
    return script, part


def _recheck_answer(item, quotes):
    return json.dumps({"quotes": quotes, "eligibility": [item], "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}}}, ensure_ascii=False)


def _fixed_recheck():
    script, _ = _broken_answers()
    data = example("housing")
    fixed = json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))
    quote = {"ref": "q1", "documentId": "text", "text": data["evidence"][0]["quote"]}
    script["recheck"] = [_recheck_answer(fixed, [quote])]
    return script


def _unhelpful_recheck():
    script, part = _broken_answers()
    script["recheck"] = [_recheck_answer(part["eligibility"][1], part["quotes"])]
    return script


def _models(name):
    down = ModelError("로컬 AI 연결 실패", transient=False)
    if name == "clean":
        return NoticeModels(RecordedModel(answers(), "local"), None, names={"primary": "local"})
    if name == "fallback":
        local = RecordedModel({call: [down] for call in answers()}, "local")
        return NoticeModels(local, RecordedModel(answers(), "paid"), names={"primary": "local", "fallback": "paid"})
    if name == "all_down":
        return NoticeModels(RecordedModel({call: [down] for call in answers()}), None)
    if name == "recheck_accepted":
        return NoticeModels(RecordedModel(_fixed_recheck()), None)
    if name == "recheck_rejected":
        return NoticeModels(RecordedModel(_unhelpful_recheck()), None)
    return NoticeModels(RecordedModel({}), None)


SCENARIOS = {
    "clean": lambda: raw_event(),
    "fallback": lambda: raw_event(),
    "all_down": lambda: raw_event(),
    "recheck_accepted": lambda: raw_event(),
    "recheck_rejected": lambda: raw_event(),
    "rejected": lambda: raw_event(rawPostId="not-a-uuid"),
    "unsupported": lambda: raw_event(field="BUSINESS_SPACE"),
    "waiting_source": lambda: raw_event(textKey="text/virtual/1/v1.txt"),
}


def _comparable(outcome):
    """실행마다 달라지는 값(걸린 시간)만 빼고 Outcome 전체를 비교할 수 있게 만듭니다."""
    data = asdict(outcome)
    usage = copy.deepcopy(data.pop("usage"))
    usage.pop("totalSeconds", None)
    usage["stages"] = sorted(usage.get("stages", {}))
    usage.get("totals", {}).pop("callSeconds", None)
    for call in usage.get("calls", []):
        call.pop("seconds", None)
    return data, usage


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_graph_engine_gives_the_same_outcome_as_legacy(scenario, monkeypatch):
    results = {}
    for engine in ("legacy", "graph"):
        monkeypatch.setenv("EXTRACTION_ENGINE", engine)
        results[engine] = _comparable(run(SCENARIOS[scenario](), _models(scenario)))
    assert results["graph"] == results["legacy"]


def test_recheck_scenarios_really_recheck(monkeypatch):
    # 위 비교가 재확인 경로를 실제로 지나는지 확인합니다(채택·미채택 둘 다)
    monkeypatch.setenv("EXTRACTION_ENGINE", "graph")
    accepted = run(raw_event(), _models("recheck_accepted"))
    rejected = run(raw_event(), _models("recheck_rejected"))
    assert accepted.usage["recheck"]["accepted"] is True
    assert rejected.usage["recheck"]["accepted"] is False
    assert any(r.startswith("재확인 미채택") for r in rejected.repairs)


def test_contract_errors_route_to_quarantine():
    clean = VerificationReport(candidate={}, findings=[], contract_errors=[])
    broken = VerificationReport(candidate={}, findings=[], contract_errors=["/eligibility/0 오류"])
    assert _after_recheck({"report": clean}) == "annotate"
    assert _after_recheck({"report": broken}) == "quarantine"


def test_graph_has_the_pipeline_nodes_in_order():
    nodes = set(GRAPH.get_graph().nodes)
    assert {"intake", "image_reading", "extract", "assemble_verify", "recheck", "quarantine", "annotate", "publish", "finish"} <= nodes


def test_engine_setting(monkeypatch):
    monkeypatch.delenv("EXTRACTION_ENGINE", raising=False)
    assert extraction_engine() == "graph"
    monkeypatch.setenv("EXTRACTION_ENGINE", "legacy")
    assert extraction_engine() == "legacy"
    monkeypatch.setenv("EXTRACTION_ENGINE", "agent")
    with pytest.raises(ValueError):
        extraction_engine()


def test_new_event_helper_is_shared():
    # 비교가 같은 이벤트 ID·시각을 쓰는지(새로 만드는 값이 결과에 섞이지 않게)
    assert new_event("t", "p", {})["eventId"] == new_event("t", "p", {})["eventId"]
