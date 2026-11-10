"""공고 1건 처리의 측정 기록: 모델 호출마다 시간·토큰·비용, 단계마다 걸린 시간 (extraction_jobs.usage).

- 호출 기록은 MeteredModel이 남깁니다. 제공자 호출 하나(재시도 한 번 = 한 번)를 time.perf_counter로 잽니다.
- 비용은 응답 사용량과 표준 요율로 계산한 추정입니다(pricing.cost_usd). 다시 쓴 응답(cache hit)은 0입니다.
  예산(cost_usd 칸)은 청구됐을 수 있는 실패를 최악 비용으로 세므로 이 합계와 다를 수 있습니다. cost_usd 칸은 예전 그대로 둡니다.
- 오류는 분류 코드만 남깁니다(ModelError.code). 오류 문구는 제공자가 요청 내용을 되돌려 줄 수 있어 넣지 않습니다.
- 공고 원문·사용자 정보·키는 넣지 않습니다. 병렬 호출(EXTRACTION_PARALLEL_CALLS)에서도 쓸 수 있게 잠금을 둡니다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, ModelResponse
from mujuthaek_extraction.model.pricing import PRICES, cost_usd

FORMAT = 1
TOKEN_KINDS = ("inputTokens", "cachedTokens", "cacheWriteTokens", "outputTokens", "reasoningTokens")
# 처리 단계 이름 (pipeline·extract가 씁니다)
STAGES = ("intake", "image_reading", "supply_tables", "sections", "assemble_verify", "recheck", "quarantine", "publish")


class UsageRecorder:
    """공고 1건의 호출 기록과 단계별 시간을 모읍니다. summary()가 저장할 JSON을 만듭니다."""

    def __init__(self, clock=time.perf_counter):
        self._clock = clock
        self._lock = threading.Lock()
        self._started = clock()
        self._calls: list[dict[str, Any]] = []
        self._sent: dict[str, int] = {}
        self._stages: dict[str, float] = {}
        self._extra: dict[str, Any] = {}  # 호출·단계 밖의 처리 기록(재확인 채택·거절 등). 원문·사용자 정보는 넣지 않습니다

    def next_attempt(self, call_name: str) -> int:
        """같은 호출 이름으로 이 공고에서 몇 번째 보내는 요청인지(일시 오류 재시도·형식 재요청·대체 모델 재추출 포함)."""
        with self._lock:
            self._sent[call_name] = self._sent.get(call_name, 0) + 1
            return self._sent[call_name]

    def add_call(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._calls.append(record)

    def record(self, key: str, value: Any) -> None:
        """처리 기록 하나를 summary()의 key 칸에 남깁니다(재확인 채택·거절 요약 등). 같은 key는 덮어씁니다."""
        with self._lock:
            self._extra[key] = value

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """단계 시간을 더합니다(같은 단계를 여러 번 지나면 합). 예외가 나도 잰 시간은 남깁니다."""
        start = self._clock()
        try:
            yield
        finally:
            elapsed = self._clock() - start
            with self._lock:
                self._stages[name] = self._stages.get(name, 0.0) + elapsed

    def summary(self) -> dict[str, Any]:
        with self._lock:
            calls = [dict(c) for c in self._calls]
            stages = {k: round(v, 3) for k, v in self._stages.items()}
            total = self._clock() - self._started
            extra = dict(self._extra)
        totals: dict[str, Any] = {
            "calls": len(calls),
            "errors": sum(1 for c in calls if c["error"]),
            "cacheHits": sum(1 for c in calls if c["cacheHit"]),
            "callSeconds": round(sum(c["seconds"] for c in calls), 3),
            **{kind: sum(c[kind] or 0 for c in calls) for kind in TOKEN_KINDS},
            "costUsd": round(sum(c["costUsd"] for c in calls), 8),
        }
        return {"format": FORMAT, "totalSeconds": round(total, 3), "stages": stages, "totals": totals, "calls": calls, **extra}


def timed(usage: UsageRecorder | None, name: str):
    """usage가 없으면 아무것도 재지 않는 문맥."""
    return usage.stage(name) if usage is not None else nullcontext()


def log_fields(summary: dict[str, Any] | None) -> dict[str, Any]:
    """작업 로그 한 줄에 넣을 합계(호출 목록 없이). 원문·오류 문구는 없습니다."""
    if not summary:
        return {}
    totals = summary.get("totals") or {}
    return {
        "seconds": summary.get("totalSeconds"),
        "stages": summary.get("stages"),
        "calls": totals.get("calls"),
        "callErrors": totals.get("errors"),
        "cacheHits": totals.get("cacheHits"),
        **{kind: totals.get(kind) for kind in TOKEN_KINDS},
        "estimatedCostUsd": totals.get("costUsd"),
    }


def error_code(error: ModelError) -> str:
    return error.code or ("TRANSIENT" if error.transient else "ERROR")


class MeteredModel:
    """모델 호출 하나마다 기록을 남기는 감싸기. 응답·오류는 그대로 돌려줍니다(결과를 바꾸지 않음).

    label: 기록에 남길 모델 이름(models.names 값). 요율표(PRICES)에 있는 이름이면 사용량으로 비용을 추정합니다."""

    def __init__(self, model: ExtractionModel, usage: UsageRecorder, label: str, clock=time.perf_counter, gate: Any = None):
        """gate: 공고 하나의 모델 호출 동시 상한(EXTRACTION_PARALLEL_CALLS, pipeline.Runtime.gate). V2 담당 호출(BudgetMiddleware)과 함께 씁니다."""
        self.model = model
        self.usage = usage
        self.label = label
        self._clock = clock
        self._gate = gate

    def complete(self, request: ModelRequest) -> ModelResponse:
        attempt = self.usage.next_attempt(request.call_name)
        with self._gate or nullcontext():
            start = self._clock()  # 차례를 기다린 시간은 호출 시간에 넣지 않아요
            try:
                response = self.model.complete(request)
            except ModelError as error:
                self.usage.add_call(self._record(request, attempt, self._clock() - start, None, error))
                raise
            self.usage.add_call(self._record(request, attempt, self._clock() - start, response, None))
        return response

    def _record(self, request: ModelRequest, attempt: int, seconds: float, response: ModelResponse | None, error: ModelError | None) -> dict[str, Any]:
        record: dict[str, Any] = {
            "call": request.call_name,
            "attempt": attempt,
            "model": self.label,
            "seconds": round(seconds, 3),
            **dict.fromkeys(TOKEN_KINDS),
            "stopReason": None,
            "error": None,
            "maybeBilled": False,
            "cacheHit": False,
            "costUsd": 0.0,
        }
        if error is not None:
            record.update(error=error_code(error), maybeBilled=error.maybe_billed)
            return record
        assert response is not None
        record.update(
            inputTokens=response.input_tokens,
            cachedTokens=response.cached_input_tokens,
            cacheWriteTokens=response.cache_write_tokens,
            outputTokens=response.output_tokens,
            reasoningTokens=response.reasoning_tokens,
            stopReason=response.stop_reason.value,
            cacheHit=response.cache_hit,
        )
        if not response.cache_hit and self.label in PRICES:
            record["costUsd"] = round(cost_usd(self.label, response), 8)
        return record
