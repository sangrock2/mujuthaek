"""예산 미들웨어(LangChain AgentMiddleware): 모델 호출마다 보내기 전에 최악 비용을 공고 장부에 잡아 두고, 넘으면 보내지 않습니다.
받은 뒤에는 실제 사용량(usage_metadata)으로 정산하고 차례 기록(에이전트·시간·토큰·비용)을 남깁니다.

장부는 V1과 같은 Budget(model/pricing.py)입니다. 공고당 상한·병렬 호출·DB 하루·월 상한을 그대로 지킵니다.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from mujuthaek_extraction.model.pricing import IMAGE_TOKENS, PRICES

DEFAULT_MAX_OUTPUT_TOKENS = 4_000
CACHE_HIT = "v2CacheHit"  # 파일 캐시에서 꺼낸 답 표시(비용 0)


class BudgetExceeded(RuntimeError):
    """공고 예산 상한에 닿아 모델을 부르지 않았습니다."""


def maybe_billed(error: BaseException) -> bool:
    """실패한 호출이 청구됐을 수 있는지(V1 ModelError.maybe_billed와 같은 기준). 오류 응답(429·4xx·5xx)과 연결하지 못한 경우는
    청구되지 않아 예약을 풉니다. 시간 초과·끊긴 응답·모르는 오류는 청구됐을 수 있다고 봅니다. 예전엔 모두 최악 비용으로 세어,
    동시 호출이 429를 받고 재시도하면 청구 없는 가짜 비용이 공고 상한·하루 장부를 채웠어요(2026-11-10 코드 검토)."""
    flagged = getattr(error, "maybe_billed", None)
    if isinstance(flagged, bool):
        return flagged
    if isinstance(getattr(error, "status_code", None), int):  # openai.APIStatusError: 제공자가 오류로 답함
        return False
    connect = (httpx.ConnectError, httpx.ConnectTimeout)
    return not isinstance(error, connect) and not isinstance(error.__cause__ or error.__context__, connect)


class BudgetMiddleware(AgentMiddleware):
    def __init__(self, agent: str, max_output_tokens: int | None = None):
        super().__init__()
        self.agent = agent
        self.max_output_tokens = max_output_tokens

    def wrap_model_call(self, request, handler):
        context = request.runtime.context
        gate = getattr(context, "calls", None)
        if gate is None:
            return self._call(request, handler, context)
        with gate:  # 공고 하나의 동시 호출 상한(재시도 사이 쉬는 동안은 잡지 않음: 재시도 미들웨어가 이 바깥)
            return self._call(request, handler, context)

    def _call(self, request, handler, context):
        budget = getattr(context, "budget", None)
        if budget is None:
            response = handler(request)
            _from_cache(_ai_message(response))
            return response
        limit = self.max_output_tokens or getattr(request.model, "max_tokens", None) or DEFAULT_MAX_OUTPUT_TOKENS
        worst = worst_case_usd(request, budget.model, limit)
        ticket = budget.reserve_usd(worst)
        if ticket is None:
            raise BudgetExceeded(f"{self.agent}: 공고 예산 상한(${budget.limit_usd:.2f})에 닿아 부르지 않았습니다")
        started = time.monotonic()
        try:
            response = handler(request)
        except Exception as error:
            billed = maybe_billed(error)
            if billed:
                budget.settle_worst(ticket)  # 보낸 뒤 실패: 청구됐을 수 있음
            else:
                budget.release(ticket)
            record = getattr(context, "usage", None)
            if record is not None:  # 실패한 시도도 기록(재시도·비용 추정을 작업 기록에서 보게)
                seconds = round(time.monotonic() - started, 3)
                spent = round(worst if billed else 0.0, 8)
                record.append({"agent": self.agent, "seconds": seconds, "error": f"{type(error).__name__}: {error}"[:200], "maybeBilledUsd": spent})
            raise
        message = _ai_message(response)
        usage = (message.usage_metadata or {}) if message is not None else {}
        hit = _from_cache(message)
        cost = 0.0 if hit else cost_usd(budget.model, usage)
        budget.settle_usd(ticket, cost)
        record = getattr(context, "usage", None)
        if record is not None:
            record.append(
                {
                    "agent": self.agent,
                    "seconds": round(time.monotonic() - started, 3),
                    "inputTokens": usage.get("input_tokens", 0),
                    "cachedTokens": (usage.get("input_token_details") or {}).get("cache_read", 0),
                    "outputTokens": usage.get("output_tokens", 0),
                    "reasoningTokens": (usage.get("output_token_details") or {}).get("reasoning", 0),
                    "costUsd": round(cost, 8),
                    "cacheHit": hit,
                }
            )
        return response


def worst_case_usd(request: Any, model: str, max_output_tokens: int) -> float:
    """입력 전부를 캐시 쓰기로, 출력 한도 전부를 쓴다고 보고 셉니다(V1 Budget.worst_case와 같은 기준: 글자 수 ≥ 토큰 수)."""
    price = PRICES[model]
    chars = sum(_chars(message) for message in request.messages)
    if request.system_message is not None:
        chars += _chars(request.system_message)
    if request.tools:
        chars += sum(len(json.dumps(convert_to_openai_tool(tool), ensure_ascii=False)) for tool in request.tools)
    return (chars * price.cache_write + max_output_tokens * price.output) / 1_000_000


def cost_usd(model: str, usage: dict[str, Any]) -> float:
    price = PRICES[model]
    details = usage.get("input_token_details") or {}
    total = usage.get("input_tokens", 0)
    cached = details.get("cache_read", 0)
    writes = details.get("cache_creation", 0)
    plain = max(total - cached - writes, 0)
    return (plain * price.input + cached * price.cached_input + writes * price.cache_write + usage.get("output_tokens", 0) * price.output) / 1_000_000


def _chars(message: BaseMessage) -> int:
    content = message.content
    if isinstance(content, str):
        size = len(content)
    else:
        size = sum(
            IMAGE_TOKENS if isinstance(block, dict) and block.get("type") in ("image", "image_url") else len(json.dumps(block, ensure_ascii=False))
            for block in content
        )
    calls = getattr(message, "tool_calls", None) or []
    return size + sum(len(json.dumps(call.get("args", {}), ensure_ascii=False)) + len(call.get("name", "")) for call in calls)


def _from_cache(message: AIMessage | None) -> bool:
    """파일 캐시에서 꺼낸 답이면 캐시가 바꾼 곳(우리 표시, LangChain이 usage_metadata에 더하는 total_cost 0)을 지우고 True.
    이 답은 다음 차례 요청에 그대로 들어가므로, 남겨 두면 요청이 처음 실행 때와 달라 다음 차례부터 캐시가 맞지 않습니다
    (2026-11-06 5건 재측정: 담당마다 첫 차례만 다시 쓰고 나머지 차례는 모두 다시 삼)."""
    if message is None or not message.response_metadata.pop(CACHE_HIT, False):
        return False
    if message.usage_metadata:
        message.usage_metadata.pop("total_cost", None)
    return True


def _ai_message(response: Any) -> AIMessage | None:
    if isinstance(response, AIMessage):
        return response
    result = getattr(response, "result", None) or []
    return next((m for m in result if isinstance(m, AIMessage)), None)
