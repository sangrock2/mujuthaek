"""모델 층의 도구 호출: 요청 본문, 응답 해석, 캐시 열쇠, 비용 상한, 도구 지원 확인. 가짜 HTTP·녹화 응답만 씁니다."""

import json

from test_openai_model import FAKE_KEY, FakeHTTP

from mujuthaek_extraction.model import ModelRequest, ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.base import ToolCall, ToolSpec, ToolTurn, supports_tools
from mujuthaek_extraction.model.call_cache import CachedModel, MemoryCallCache, request_fingerprint, reusable
from mujuthaek_extraction.model.fallback import FallbackOnErrorModel
from mujuthaek_extraction.model.local_ai import LocalChatModel
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.usage import MeteredModel, UsageRecorder

SEARCH = ToolSpec(
    "search_source",
    "원문에서 낱말·숫자로 구간을 찾습니다.",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
)
CALL = ToolCall("call_1", "search_source", '{"query": "소득"}')


def request(**extra):
    base = dict(
        prompt_version="v30",
        call_name="repair:eligibility/e1:turn1",
        system="공통 지시",
        user="원문",
        instructions="고칠 항목",
        output_schema={"type": "object"},
        max_output_tokens=2000,
    )
    return ModelRequest(**{**base, **extra})


def test_tool_request_body_requires_a_tool_and_carries_previous_turns():
    model = OpenAIResponsesModel(FAKE_KEY)
    body = model.body(request(tools=(SEARCH,), turns=(ToolTurn((CALL,), ('{"hits": []}',)),)))
    assert [t["name"] for t in body["tools"]] == ["search_source"] and body["tools"][0]["strict"] is True
    assert body["tool_choice"] == "required" and body["parallel_tool_calls"] is False and "text" not in body
    assert [item.get("type") for item in body["input"][1:]] == ["function_call", "function_call_output"]
    assert body["input"][2] == {"type": "function_call_output", "call_id": "call_1", "output": '{"hits": []}'}


def test_forced_tool_keeps_the_tool_list_and_items_share_one_cache_key():
    model = OpenAIResponsesModel(FAKE_KEY)
    plain, forced = model.body(request(tools=(SEARCH,))), model.body(request(tools=(SEARCH,), forced_tool="search_source"))
    assert forced["tools"] == plain["tools"] and forced["tool_choice"] == {"type": "function", "name": "search_source"}
    other_item = model.body(request(tools=(SEARCH,), user="다른 고칠 항목", call_name="repair:eligibility/e2:turn1"))
    assert plain["prompt_cache_key"] == other_item["prompt_cache_key"] and plain["prompt_cache_key"].startswith("repair-")


def test_request_without_tools_is_unchanged():
    body = OpenAIResponsesModel(FAKE_KEY).body(request())
    assert "tools" not in body and body["text"]["format"]["type"] == "json_schema" and len(body["input"]) == 1


def test_function_call_output_becomes_tool_calls():
    payload = {
        "status": "completed",
        "model": "gpt-6-luna",
        "output": [{"type": "function_call", "call_id": "call_9", "name": "search_source", "arguments": '{"query": "무주택"}'}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    model = OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(payload))
    response = model.complete(request(tools=(SEARCH,)))
    assert response.stop_reason is StopReason.END and response.raw_text == ""
    assert response.tool_calls == (ToolCall("call_9", "search_source", '{"query": "무주택"}'),)


def test_cache_key_of_plain_requests_does_not_change_and_tool_answers_are_not_stored():
    assert "toolUse" not in request_fingerprint(request())
    assert request_fingerprint(request(tools=(SEARCH,)))["toolUse"]["tools"][0]["name"] == "search_source"
    tool_answer = ModelResponse("", "m", StopReason.END, tool_calls=(CALL,))
    assert not reusable(request(tools=(SEARCH,)), tool_answer)


def test_budget_counts_tools_and_previous_turns():
    budget = Budget("gpt-6-luna", 1.0)
    turns = (ToolTurn((CALL,), (json.dumps({"text": "가" * 5000}, ensure_ascii=False),)),)
    assert budget.worst_case(request(tools=(SEARCH,), turns=turns)) > budget.worst_case(request())


def test_tool_support_is_found_through_wrappers():
    paid = OpenAIResponsesModel(FAKE_KEY)
    budget = Budget("gpt-6-luna", 1.0)
    wrapped = MeteredModel(CachedModel(BudgetedModel(paid, budget), MemoryCallCache(), paid.cache_identity, "paid"), UsageRecorder(), "paid")
    assert supports_tools(wrapped)
    local = LocalChatModel("http://localhost:1", "local")
    assert not supports_tools(local)
    assert not supports_tools(FallbackOnErrorModel(local, paid))  # 먼저 부르는 쪽이 로컬이면 도구를 쓰지 않음
    assert supports_tools(RecordedModel({}))


def test_recorded_model_replays_tool_calls():
    model = RecordedModel({"repair:x:turn1": [ModelResponse("", "recorded", StopReason.END, tool_calls=(CALL,))]})
    assert model.complete(request(call_name="repair:x:turn1", tools=(SEARCH,))).tool_calls == (CALL,)
