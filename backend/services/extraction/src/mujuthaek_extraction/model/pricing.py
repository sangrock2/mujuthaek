"""모델 사용량 → 예상 비용과 예산 상한 (2-10 비용 집계의 최소 구현).

요율은 확인한 날짜·출처와 함께 둡니다. 청구서 금액이 아니라 응답 사용량과 표준 요율로 계산한 추정입니다.
"""

from __future__ import annotations

import itertools
import json
import threading
from dataclasses import dataclass, field
from typing import Any

from mujuthaek_extraction.model.base import ModelError, ModelRequest, ModelResponse


@dataclass(frozen=True)
class Price:
    input: float  # USD / 100만 토큰 (캐시 아닌 입력)
    cached_input: float
    cache_write: float
    output: float  # 추론 토큰 포함
    checked: str
    long_context_tokens: int | None = None

    def usd(self, input_tokens: int, cached: int, writes: int, output_tokens: int) -> float:
        """사용량 → 비용. input_tokens는 캐시 읽기(cached)·캐시 쓰기(writes)를 포함한 전체 입력입니다(V1 응답·V2 채팅 답이 같이 씀)."""
        plain = max(input_tokens - cached - writes, 0)
        input_factor, output_factor = (2.0, 1.5) if self.long_context_tokens is not None and input_tokens > self.long_context_tokens else (1.0, 1.0)
        return (
            (plain * self.input + cached * self.cached_input + writes * self.cache_write) * input_factor + output_tokens * self.output * output_factor
        ) / 1_000_000

    def worst_usd(self, chars: int, max_output_tokens: int) -> float:
        """보내기 전 최악 비용: 입력 글자 수를 모두 캐시 쓰기 토큰으로(한국어는 대개 토큰 수 ≤ 글자 수), 출력 한도를 모두 씀."""
        input_factor, output_factor = (2.0, 1.5) if self.long_context_tokens is not None and chars > self.long_context_tokens else (1.0, 1.0)
        return (chars * self.cache_write * input_factor + max_output_tokens * self.output * output_factor) / 1_000_000


IMAGE_TOKENS = 3_000  # 그림 한 장의 입력 토큰 상한 추정(쪽 그림 120dpi 기준, 실제보다 넉넉하게)
PRICES = {
    # 공식 모델 문서(2026-11-14): 272K 초과는 전체 입력·캐시 2배, 출력 1.5배예요.
    "gpt-6-luna": Price(
        input=0.10,
        cached_input=0.01,
        cache_write=0.125,
        output=0.50,
        checked="2026-11-14 developers.openai.com/api/docs/models/gpt-6-luna",
        long_context_tokens=272_000,
    ),
}


def cost_usd(model: str, response: ModelResponse) -> float:
    return PRICES[model].usd(response.input_tokens or 0, response.cached_input_tokens or 0, response.cache_write_tokens or 0, response.output_tokens or 0)


@dataclass
class Budget:
    """호출 전에 최악의 비용(입력 전부 캐시 쓰기 + 출력 한도 전부)을 더해도 상한 안일 때만 호출합니다.

    prior_usd: 같은 원본 버전의 앞선 처리(실패해 다시 처리하는 경우)가 이미 쓴 비용(2026-10-20). 상한은 처리 횟수와 상관없이
    원본 버전 하나에 걸립니다. 예전엔 다시 처리할 때마다 새 예산이라 6번 처리하면 상한의 6배까지 쓸 수 있었습니다.
    spent_usd는 이번 처리에서 쓴 비용만입니다(작업 기록 cost_usd, 앞선 비용을 두 번 세지 않게).

    병렬 호출(2026-10-20): 확인과 동시에 최악 비용을 잡아 두고(reserve) 응답이 오면 실제 비용으로 바꿉니다(settle).
    확인과 잡아 두기를 한 잠금 안에서 하므로, 동시에 나간 호출들이 함께 상한을 넘을 수 없습니다.

    ledger(2026-10-21): DB 비용 장부(model/spend.py). 있으면 호출마다 장부에도 최악 비용을 적고 하루·월 전체 상한을 함께 지킵니다.
    전체 상한에 걸리면 refusal에 이유가 남습니다."""

    model: str
    limit_usd: float
    spent_usd: float = 0.0
    calls: list[float] = field(default_factory=list)
    prior_usd: float = 0.0
    ledger: Any = None
    refusal: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)
    _held: dict[int, float] = field(default_factory=dict, init=False, repr=False, compare=False)  # 응답을 기다리는 호출의 최악 비용
    _tickets: itertools.count = field(default_factory=itertools.count, init=False, repr=False, compare=False)
    _entries: dict[int, str] = field(default_factory=dict, init=False, repr=False, compare=False)  # 표 → 장부 ID

    def worst_case(self, request: ModelRequest) -> float:
        # 토큰 수를 모르므로 글자 수를 상한으로 씁니다(한국어는 대개 토큰 수 ≤ 글자 수).
        chars = len(request.system) + len(request.user) + len(request.instructions) + IMAGE_TOKENS * len(request.images)
        # 출력 형식(JSON 스키마)도 입력으로 함께 보냅니다. 공유 형식을 쓰면 더 큰 쪽이 가므로 둘 중 큰 것을 셉니다(검토 2026-10-20)
        chars += max((len(json.dumps(s, ensure_ascii=False)) for s in (request.output_schema, request.shared_schema) if s), default=0)
        chars += request.tool_chars()  # 도구 설명과 앞선 차례(도구 호출·결과)도 입력으로 갑니다
        return PRICES[self.model].worst_usd(chars, request.max_output_tokens)

    def _fits(self, worst: float) -> bool:
        held = sum(self._held.values()) if self._held else 0.0  # 잡아 둔 것이 없으면 정확히 0 (순서대로 부를 때 이전과 같은 계산)
        return self.prior_usd + self.spent_usd + held + worst <= self.limit_usd

    def allow(self, request: ModelRequest) -> bool:
        with self._lock:
            return self._fits(self.worst_case(request))

    def reserve(self, request: ModelRequest) -> int | None:
        """상한 안이면 최악 비용을 잡아 두고 표를 돌려줍니다. 넘으면 None."""
        return self.reserve_usd(self.worst_case(request))

    def reserve_usd(self, worst: float) -> int | None:
        """최악 비용(USD)을 직접 받아 잡아 둡니다(V2 LangChain 미들웨어가 요청 모양과 상관없이 씀)."""
        with self._lock:
            if not self._fits(worst):
                return None
            entry = None
            if self.ledger is not None:
                entry = self.ledger.reserve(self.model, worst)
                if entry is None:
                    self.refusal = self.ledger.refused
                    return None
            ticket = next(self._tickets)
            self._held[ticket] = worst
            if entry is not None:
                self._entries[ticket] = entry
            return ticket

    def settle(self, ticket: int, response: ModelResponse) -> float:
        """잡아 둔 비용을 풀고 실제 사용량 비용을 더합니다."""
        return self.settle_usd(ticket, cost_usd(self.model, response))

    def settle_usd(self, ticket: int, cost: float) -> float:
        """잡아 둔 비용을 풀고 실제 비용(USD)을 더합니다."""
        with self._lock:
            self._held.pop(ticket, None)
            self.spent_usd += cost
            self.calls.append(cost)
            entry = self._entries.pop(ticket, None)
        if entry is not None:
            self.ledger.settle(entry, cost)
        return cost

    def settle_worst(self, ticket: int) -> float:
        """청구됐을 수 있는 실패: 잡아 둔 최악 비용을 그대로 씁니다."""
        with self._lock:
            cost = self._held.pop(ticket, 0.0)
            self.spent_usd += cost
            self.calls.append(cost)
            entry = self._entries.pop(ticket, None)
        if entry is not None:
            self.ledger.settle(entry, cost)
        return cost

    def release(self, ticket: int) -> None:
        """청구되지 않은 실패: 잡아 둔 비용을 풉니다."""
        with self._lock:
            self._held.pop(ticket, None)
            entry = self._entries.pop(ticket, None)
        if entry is not None:
            self.ledger.release(entry)

    def charged_usd(self) -> float:
        """이번 처리에서 쓴 비용 + 아직 응답을 기다리는 호출의 최악 비용. 예외로 처리가 중단될 때 작업 기록에 남길 값입니다
        (끝나지 않은 호출은 청구됐을 수 있어 최악 비용으로 셉니다)."""
        with self._lock:
            return self.spent_usd + sum(self._held.values())

    def record(self, response: ModelResponse) -> float:
        cost = cost_usd(self.model, response)
        with self._lock:
            self.spent_usd += cost
            self.calls.append(cost)
        return cost


class BudgetedModel:
    """실제 사용량으로 Budget.spent_usd를 누적하는 감싸기. 상한을 넘을 호출은 보내지 않고 ModelError를 냅니다."""

    def __init__(self, model, budget: Budget):
        self.model = model
        self.budget = budget

    def complete(self, request: ModelRequest) -> ModelResponse:
        ticket = self.budget.reserve(request)
        if ticket is None and self.budget.refusal:
            raise ModelError(f"전체 {self.budget.refusal}을 넘을 수 있어 호출하지 않았습니다.", transient=False, code="GLOBAL_BUDGET")
        if ticket is None:
            raise ModelError(f"공고당 비용 상한(${self.budget.limit_usd:.2f})을 넘을 수 있어 호출하지 않았습니다.", transient=False, code="BUDGET")
        try:
            response = self.model.complete(request)
        except ModelError as error:
            if error.maybe_billed:
                # 시간 초과·끊긴 응답은 청구됐을 수 있어 최악 비용으로 셉니다. 예전엔 성공한 호출만 세어,
                # 큰 호출이 시간 초과로 세 번 재시도되면 공고 하나가 상한의 세 배까지 쓸 수 있었습니다(검토 2026-10-16)
                self.budget.settle_worst(ticket)
            else:
                self.budget.release(ticket)
            raise
        except BaseException:
            self.budget.release(ticket)
            raise
        self.budget.settle(ticket, response)
        return response
