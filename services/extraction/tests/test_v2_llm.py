"""V2 모델 층: 보내기 전 예산 예약(넘으면 부르지 않음)·실제 사용량 정산·호출 기록, 파일 캐시(다시 쓴 답은 비용 0), 모델 설정. 유료 호출 없음."""

import dataclasses
import os

import httpx
import openai
import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from test_v2_document import TEXT, ToolCallingFake

from mujuthaek_extraction.config import TRACING_ENV_NAMES, Settings
from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.v2.context import V2Context
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.llm import retry
from mujuthaek_extraction.v2.llm.budget import BudgetExceeded, BudgetMiddleware, cost_usd
from mujuthaek_extraction.v2.llm.cache import FileLLMCache
from mujuthaek_extraction.v2.llm.models import chat_model

USAGE = {
    "input_tokens": 10_000,
    "output_tokens": 500,
    "total_tokens": 10_500,
    "input_token_details": {"cache_read": 8_000},
    "output_token_details": {"reasoning": 200},
}


def agent_with(model, budget):
    agent = create_agent(model, tools=[], middleware=[BudgetMiddleware("planner")], context_schema=V2Context)
    context = V2Context(document=parse(TEXT), budget=budget)
    return agent, context


def test_actual_usage_is_charged_and_recorded_after_the_reservation():
    budget = Budget(model="gpt-6-luna", limit_usd=0.5)
    agent, context = agent_with(ToolCallingFake(messages=iter([AIMessage(content="끝", usage_metadata=USAGE)])), budget)
    agent.invoke({"messages": [HumanMessage("계획")]}, context=context)
    expected = (2_000 * 0.10 + 8_000 * 0.01 + 500 * 0.50) / 1_000_000  # 캐시 읽기는 싼 요율
    assert budget.spent_usd == pytest.approx(expected) and budget.charged_usd() == pytest.approx(expected)  # 잡아 둔 최악 비용은 풀림
    record = context.usage[0]
    assert record["agent"] == "planner" and record["cachedTokens"] == 8_000 and record["reasoningTokens"] == 200 and record["cacheHit"] is False
    assert cost_usd("gpt-6-luna", USAGE) == pytest.approx(expected)


def test_a_call_that_could_pass_the_notice_cap_is_not_sent():
    model = ToolCallingFake(messages=iter([AIMessage(content="부르면 안 됨", usage_metadata=USAGE)]))
    agent, context = agent_with(model, Budget(model="gpt-6-luna", limit_usd=0.000_001))
    with pytest.raises(BudgetExceeded):
        agent.invoke({"messages": [HumanMessage("계획")]}, context=context)
    assert next(model.messages).content == "부르면 안 됨" and context.usage == []  # 모델의 답은 쓰이지 않음


class CountingModel(BaseChatModel):
    """부른 횟수를 세는 가짜 모델(캐시가 두 번째 호출을 막는지 보려고)."""

    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "counting"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=f"답 {self.calls}", usage_metadata=USAGE))])


def test_cached_answers_are_reused_for_the_same_request_and_cost_nothing(tmp_path):
    model = CountingModel(cache=FileLLMCache(tmp_path))
    budget = Budget(model="gpt-6-luna", limit_usd=0.5)
    first, context = agent_with(model, budget)
    first.invoke({"messages": [HumanMessage("같은 요청")]}, context=context)
    spent = budget.spent_usd
    again = CountingModel(cache=FileLLMCache(tmp_path))  # 다음 실행(새 프로세스처럼)
    second, context2 = agent_with(again, budget)
    result = second.invoke({"messages": [HumanMessage("같은 요청")]}, context=context2)
    assert again.calls == 0 and result["messages"][-1].content == "답 1"
    assert budget.spent_usd == pytest.approx(spent) and context2.usage[0]["cacheHit"] is True and context2.usage[0]["costUsd"] == 0
    second.invoke({"messages": [HumanMessage("다른 요청")]}, context=context2)
    assert again.calls == 1


def test_chat_model_uses_the_responses_api_without_storing_or_retrying(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = dataclasses.replace(Settings.from_env(), openai_model="gpt-6-luna", openai_effort="medium")
    model = chat_model(settings, effort="low", max_output_tokens=1_500, cache_key="notice-abc")
    assert model.model_name == "gpt-6-luna" and model.use_responses_api is True and model.store is False and model.max_retries == 0
    assert model.reasoning == {"effort": "low"} and model.max_tokens == 1_500 and model.model_kwargs == {"prompt_cache_key": "notice-abc"}


def test_langsmith_settings_in_env_file_are_handed_to_the_environment_without_overriding(tmp_path, monkeypatch):
    # LangChain·LangGraph는 추적 설정을 환경 변수로만 읽음 → .env의 LANGSMITH_*를 넘김(이미 있는 값은 그대로, 시험은 conftest가 꺼 둠)
    for name in TRACING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_PROJECT", "already-set")
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-test\nLANGSMITH_TRACING=true\nLANGSMITH_API_KEY=lsv2_pt_test\nLANGSMITH_PROJECT=from-file\n", encoding="utf-8")
    settings = dataclasses.replace(Settings.from_env(), env_file=env)
    assert settings.export_tracing() == ["LANGSMITH_TRACING", "LANGSMITH_API_KEY"]
    assert os.environ["LANGSMITH_TRACING"] == "true" and os.environ["LANGSMITH_PROJECT"] == "already-set"
    assert settings.export_tracing() == []  # 두 번째부터는 넘길 것이 없음


class FlakyFake(ToolCallingFake):
    """처음 몇 번은 시간 초과, 그다음은 준비한 답."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.__dict__.setdefault("failures", 0) < self.__dict__.get("fail_times", 1):
            self.__dict__["failures"] += 1
            raise openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_transient_model_errors_are_retried_and_each_attempt_is_budgeted_and_recorded(monkeypatch):
    # 2026-11-06 23건 측정: 시간 초과 한 번에 측정 전체가 멈춤 → 일시 오류만 다시 보냄(예산 초과·잘못된 요청은 아님)
    monkeypatch.setattr(retry, "FIRST_DELAY_SECONDS", 0.0)
    model = FlakyFake(messages=iter([AIMessage(content="끝", usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})]))
    context = V2Context(document=parse(TEXT), budget=Budget("gpt-6-luna", 0.5))
    agent = create_agent(model, tools=[], middleware=[retry.retry_middleware(), BudgetMiddleware("schedules")], context_schema=V2Context)
    result = agent.invoke({"messages": [HumanMessage("일정")]}, context=context)
    assert result["messages"][-1].content == "끝"
    assert [("error" in r, r["agent"]) for r in context.usage] == [(True, "schedules"), (False, "schedules")]
    assert context.usage[0]["error"].startswith("APITimeoutError") and context.usage[0]["maybeBilledUsd"] > 0
    req = httpx.Request("POST", "https://x")
    assert retry.transient(openai.RateLimitError("x", response=httpx.Response(429, request=req), body=None))
    assert not retry.transient(openai.BadRequestError("x", response=httpx.Response(400, request=req), body=None))
    assert not retry.transient(BudgetExceeded("상한"))
