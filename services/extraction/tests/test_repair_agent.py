"""재확인 에이전트: 녹화한 차례(도구 호출)로 고치기·버려짐·포기·상한·비용·회복·대체를 확인합니다. 네트워크·유료 호출 없음."""

import json

import pytest
from helpers import example, to_ai
from test_recheck import answer, setup

from mujuthaek_extraction.model import ModelError, ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.base import ToolCall
from mujuthaek_extraction.recheck import recheck_problems
from mujuthaek_extraction.repair.agent import AGENT, MAX_TURNS, recheck_strategy
from mujuthaek_extraction.rules.housing_notice import RULES


def turn(name, **args):
    return ModelResponse(
        "", "recorded", StopReason.END, input_tokens=100, output_tokens=20, tool_calls=(ToolCall("c", name, json.dumps(args, ensure_ascii=False)),)
    )


def fixed_item(data):
    return json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))


def script(item_id, *turns):
    return {f"repair:eligibility/{item_id}:turn{n}": [t] for n, t in enumerate(turns, start=1)}


def run_agent(model):
    data, source, parts, evaluate = setup()
    return recheck_problems(RULES, source.material, model, parts, evaluate, strategy=AGENT), data, parts


def test_agent_finds_the_quote_and_its_fix_is_adopted_by_the_verifier():
    data, *_ = setup()
    item_id, quote = data["eligibility"][1]["id"], data["evidence"][0]["quote"]
    model = RecordedModel(
        script(
            item_id,
            turn("search_source", query=quote[:12], limit=3),
            turn("check_quote", quote=quote),
            turn("submit_fix", item_json=json.dumps(fixed_item(data), ensure_ascii=False), quotes=[{"ref": "q1", "text": quote}], give_up=""),
        )
    )
    result, _, _ = run_agent(model)
    assert result.accepted and result.report.passed
    log = result.agent["items"][0]
    expected = {"target": f"eligibility/{item_id}", "turns": 3, "tools": {"search_source": 1, "check_quote": 1, "submit_fix": 1}}
    assert log == {**expected, "outcome": "SUBMITTED", "returned": 0}
    assert result.summary()["agent"] == result.agent
    # 둘째 차례 요청에 앞선 차례(도구 호출과 결과·남은 차례)가 붙고, 도구 목록이 함께 갑니다
    second = model.requests[1]
    first_result = json.loads(second.turns[0].results[0])
    assert len(second.turns) == 1 and first_result["total"] >= 1 and first_result["turnsLeft"] == MAX_TURNS - 1
    assert {t.name for t in second.tools} == {"search_source", "read_page", "check_quote", "validate_item", "submit_fix"}


def test_worse_fix_is_sent_back_once_then_not_adopted():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    worse = {**fixed_item(data), "quoteRefs": ["x"]}
    bad = turn("submit_fix", item_json=json.dumps(worse), quotes=[{"ref": "x", "text": "원문에 없는 글"}], give_up="")
    model = RecordedModel(script(item_id, bad, bad))
    result, _, parts = run_agent(model)
    returned = json.loads(model.requests[1].turns[0].results[0])
    assert returned["received"] is False and returned["error"] == "NEW_PROBLEMS" and returned["problems"]
    assert not result.accepted and result.parts == parts  # 두 번째로 내면 받지만 채택은 검증기가 거절
    assert result.agent["items"][0]["outcome"] == "SUBMITTED" and result.agent["items"][0]["returned"] == 1


def test_only_changed_fields_are_submitted_and_original_quotes_follow():
    data, source, parts, evaluate = setup()
    item_id, quote = data["eligibility"][1]["id"], data["evidence"][0]["quote"]
    # 칸 하나(quoteRefs)만 내도 나머지 칸은 처음 값이고 채택됩니다
    patch = turn("submit_fix", item_json=json.dumps({"quoteRefs": ["n1"]}), quotes=[{"ref": "n1", "text": quote}], give_up="")
    model = RecordedModel(script(item_id, patch))
    result, _, _ = run_agent(model)
    original = parts[0]["eligibility"][1]
    adopted = next(x for x in result.parts[0]["eligibility"] if x["id"] == item_id)
    assert result.accepted and without_refs(adopted) == without_refs(original)  # 인용 참조 이름만 바뀜(처음 인용은 함께 붙음)


def without_refs(node):
    if isinstance(node, dict):
        return {k: without_refs(v) for k, v in node.items() if k != "quoteRefs"}
    if isinstance(node, list):
        return [without_refs(x) for x in node]
    return node


def test_last_turn_allows_only_submit():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    model = RecordedModel(script(item_id, *[turn("search_source", query="무주택", limit=1) for _ in range(MAX_TURNS)]))
    run_agent(model)
    assert [t.name for t in model.requests[-1].tools] == ["submit_fix"]
    assert json.loads(model.requests[-1].turns[-1].results[0])["turnsLeft"] == 1
    assert "마지막" in json.loads(model.requests[-1].turns[-1].results[0])["notice"]


def test_giving_up_keeps_the_first_result():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    model = RecordedModel(script(item_id, turn("submit_fix", item_json="", quotes=[], give_up="원문에서 찾지 못함")))
    result, _, parts = run_agent(model)
    assert not result.accepted and result.parts == parts
    assert result.agent["items"][0]["outcome"] == "GAVE_UP" and ("전체", "에이전트가 고친 항목 없음") in result.rejected


def test_turn_limit_stops_the_conversation():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    model = RecordedModel(script(item_id, *[turn("search_source", query="무주택", limit=1) for _ in range(MAX_TURNS)]))
    result, _, _ = run_agent(model)
    log = result.agent["items"][0]
    assert log == {"target": f"eligibility/{item_id}", "turns": MAX_TURNS, "tools": {"search_source": MAX_TURNS}, "outcome": "TURN_LIMIT", "returned": 0}
    assert not result.accepted


def test_budget_refusal_stops_without_an_answer():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    refused = ModelError("공고당 비용 상한", transient=False, code="BUDGET")
    result, _, _ = run_agent(RecordedModel(script(item_id, refused)))
    assert result.agent["items"][0]["outcome"] == "BUDGET" and not result.accepted


def test_tool_errors_are_returned_and_the_agent_can_recover():
    data, *_ = setup()
    item_id, quote = data["eligibility"][1]["id"], data["evidence"][0]["quote"]
    model = RecordedModel(
        script(
            item_id,
            turn("drop_table"),
            turn("submit_fix", item_json=json.dumps(fixed_item(data), ensure_ascii=False), quotes=[{"ref": "q1", "text": quote}], give_up=""),
        )
    )
    result, _, _ = run_agent(model)
    assert json.loads(model.requests[1].turns[0].results[0])["error"] == "UNKNOWN_TOOL"
    assert result.accepted


def test_model_without_tools_falls_back_to_the_batch_recheck():
    class LocalOnly:
        supports_tools = False

        def __init__(self, inner):
            self.inner = inner

        def complete(self, request):
            return self.inner.complete(request)

    data, *_ = setup()
    quote = data["evidence"][0]["quote"]
    batch = RecordedModel({"recheck": [answer(fixed_item(data), [{"ref": "q1", "documentId": "text1", "text": quote}])]})
    result, _, _ = run_agent(LocalOnly(batch))
    assert result.accepted and result.agent is None and [r.call_name for r in batch.requests] == ["recheck"]


def test_strategy_setting(monkeypatch):
    monkeypatch.delenv("EXTRACTION_RECHECK_STRATEGY", raising=False)
    assert recheck_strategy() == "batch"
    monkeypatch.setenv("EXTRACTION_RECHECK_STRATEGY", "agent")
    assert recheck_strategy() == "agent"
    monkeypatch.setenv("EXTRACTION_RECHECK_STRATEGY", "auto")
    with pytest.raises(ValueError):
        recheck_strategy()


def test_pipeline_uses_the_agent_when_set(monkeypatch):
    from test_graph import _broken_answers
    from test_pipeline import raw_event, run

    from mujuthaek_extraction.model.factory import NoticeModels

    data = example("housing")
    item_id, quote = data["eligibility"][1]["id"], data["evidence"][0]["quote"]
    calls, _ = _broken_answers()
    fix = turn("submit_fix", item_json=json.dumps(fixed_item(data), ensure_ascii=False), quotes=[{"ref": "q1", "text": quote}], give_up="")
    calls[f"repair:eligibility/{item_id}:turn1"] = [fix]
    monkeypatch.setenv("EXTRACTION_RECHECK_STRATEGY", "agent")
    outcome = run(raw_event(), NoticeModels(RecordedModel(calls), None))
    assert outcome.status == "COMPLETED" and outcome.usage["recheck"]["accepted"] is True
    assert outcome.usage["recheck"]["agent"]["items"][0]["outcome"] == "SUBMITTED"
    assert any(a["call_name"] == f"repair:eligibility/{item_id}:turn1" for a in outcome.attempts)


def test_agent_sees_the_item_in_the_shape_it_submits():
    data, *_ = setup()
    item_id = data["eligibility"][1]["id"]
    model = RecordedModel(script(item_id, turn("submit_fix", item_json="", quotes=[], give_up="확인 못 함")))
    _, _, parts = run_agent(model)
    shown = json.loads(model.requests[0].user)["고칠 항목"]
    assert shown["item"] == parts[0]["eligibility"][1]  # 처음 항목 그대로(근거는 quoteRefs)
    assert {q["ref"] for q in shown["quotes"]} >= set(parts[0]["eligibility"][1]["quoteRefs"]) - {"fake"}
    assert "quotes" not in shown["item"]


def test_hybrid_runs_the_agent_only_on_what_batch_left(monkeypatch):
    from test_graph import _broken_answers
    from test_pipeline import raw_event, run

    from mujuthaek_extraction.model.factory import NoticeModels

    data = example("housing")
    item_id, quote = data["eligibility"][1]["id"], data["evidence"][0]["quote"]
    calls, part = _broken_answers()
    calls["recheck"] = [answer(part["eligibility"][1], part["quotes"])]  # 묶음 재확인은 못 고침
    calls[f"repair:eligibility/{item_id}:turn1"] = [
        turn("submit_fix", item_json=json.dumps({"quoteRefs": ["n1"]}), quotes=[{"ref": "n1", "text": quote}], give_up="")
    ]
    monkeypatch.setenv("EXTRACTION_RECHECK_STRATEGY", "hybrid")
    outcome = run(raw_event(), NoticeModels(RecordedModel(calls), None))
    recheck = outcome.usage["recheck"]
    assert outcome.status == "COMPLETED" and recheck["accepted"] is True and recheck["adoptedSections"] == ["2:전체"]
    assert [a["call_name"] for a in outcome.attempts][-2:] == ["recheck", f"repair:eligibility/{item_id}:turn1"]
