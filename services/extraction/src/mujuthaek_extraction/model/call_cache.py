"""성공한 모델 호출 다시 쓰기 (2026-10-20). 같은 요청을 다시 보내야 할 때 저장해 둔 응답을 비용 없이 돌려줍니다.

쓰임: 공고 처리가 중간에 실패해 워커가 다시 처리하거나 같은 원본 버전을 다시 돌릴 때, 이미 성공한 호출은 다시 보내지 않고
실패했거나 바뀐 호출만 보냅니다.

열쇠 = 응답을 정하는 모든 것의 sha256 (canonical JSON)
  - 요청 전부: 호출 이름·프롬프트 버전·공통 지시·원문·호출별 지시·출력 형식·공유 형식·출력 한도·그림(바이트 해시)
  - 모델 쪽: 제공자가 실제로 보낼 요청 본문의 해시(모델 이름·추론 강도·엄격 형식 변환 포함)와 응답을 다듬는 코드의 해시
  PDF·프롬프트·형식·모델·설정·응답 처리 코드 중 하나라도 바뀌면 열쇠가 달라 옛 응답을 쓰지 않습니다.
저장 조건: 정상 종료(END)이고 JSON 객체이며 그 호출의 출력 형식(output_schema)을 통과한 응답만.
  잘린 응답·거부·형식 위반 응답은 저장하지 않아, 다시 처리할 때 새로 받습니다(틀린 답을 굳히지 않음).
저장소 오류(DB 끊김 등)는 추출을 멈추지 않습니다. 없는 것으로 보고 실제로 호출합니다.
보관: purge(days)로 오래된 행을 지웁니다(기본 90일, 설정 EXTRACTION_CALL_CACHE_DAYS). 워커 다시 처리 주기와 retry 명령이 부릅니다.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker

from mujuthaek_extraction.model.base import ExtractionModel, ModelRequest, ModelResponse, StopReason

log = logging.getLogger(__name__)
FORMAT = 1  # 저장 형식·열쇠 규칙을 바꾸면 올립니다(옛 행은 열쇠가 달라 쓰이지 않음)
# 제공자 응답을 다듬는 코드(엄격 형식 null 걷기·공유 형식 칸 거르기). 고치면 같은 요청이라도 옛 응답을 쓰지 않게 열쇠에 넣습니다
_RESPONSE_CODE = ("openai_responses.py", "local_ai.py", "strict_schema.py", "base.py")


@functools.lru_cache(maxsize=1)
def response_code_hash() -> str:
    folder = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in _RESPONSE_CODE:
        # 줄바꿈 방식(체크아웃 설정에 따른 CRLF·LF)만 다른 같은 코드는 같은 해시로 봅니다
        digest.update(name.encode() + b"\0" + (folder / name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_fingerprint(request: ModelRequest) -> dict[str, Any]:
    """요청의 모든 칸. 그림은 바이트 대신 해시로 넣습니다.
    도구·앞선 차례는 있을 때만 넣습니다(도구 없는 기존 호출의 열쇠가 그대로 유지되게). 도구 호출 응답은 JSON 답이 아니라
    reusable이 저장하지 않습니다."""
    tools = {
        "tools": [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in request.tools],
        "turns": [
            {"calls": [[c.call_id, c.name, c.arguments] for c in turn.calls], "results": list(turn.results), **({"note": turn.note} if turn.note else {})}
            for turn in request.turns
        ],
        **({"parallelTools": True} if request.parallel_tools else {}),
    }
    return {
        **({"toolUse": tools} if request.tools or request.turns else {}),
        "callName": request.call_name,
        "promptVersion": request.prompt_version,
        "system": request.system,
        "user": request.user,
        "instructions": request.instructions,
        "outputSchema": request.output_schema,
        "sharedSchema": request.shared_schema,
        "maxOutputTokens": request.max_output_tokens,
        "images": [{"label": i.label, "mediaType": i.media_type, "sha256": hashlib.sha256(i.data).hexdigest()} for i in request.images],
    }


def cache_key(request: ModelRequest, identity: dict[str, Any]) -> str:
    return sha256_text(canonical({"format": FORMAT, "request": request_fingerprint(request), "model": identity}))


def reusable(request: ModelRequest, response: ModelResponse) -> bool:
    """다시 써도 되는 응답인지: 정상 종료 + JSON 객체 + 그 호출의 출력 형식 통과."""
    if response.stop_reason is not StopReason.END or response.cache_hit or response.tool_calls:
        return False
    try:
        value = json.loads(response.raw_text)
    except ValueError:
        return False
    if not isinstance(value, dict):
        return False
    return not any(True for _ in Draft202012Validator(request.output_schema, format_checker=FormatChecker()).iter_errors(value))


def to_record(response: ModelResponse) -> dict[str, Any]:
    return {
        "rawText": response.raw_text,
        "modelId": response.model_id,
        "stopReason": response.stop_reason.value,
        "inputTokens": response.input_tokens,
        "outputTokens": response.output_tokens,
        "cachedInputTokens": response.cached_input_tokens,
        "cacheWriteTokens": response.cache_write_tokens,
        "reasoningTokens": response.reasoning_tokens,
    }


def hit_response(record: dict[str, Any]) -> ModelResponse:
    """저장한 응답을 다시 쓸 때: 글자·모델·종료 사유는 그대로, 이번 사용량(토큰·비용)은 0."""
    return ModelResponse(
        raw_text=record["rawText"],
        model_id=record["modelId"],
        stop_reason=StopReason(record["stopReason"]),
        input_tokens=0,
        output_tokens=0,
        cached_input_tokens=0,
        cache_write_tokens=0,
        usage={"cacheHit": True},
        reasoning_tokens=0,
        cache_hit=True,
    )


class CallCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, model: str, call_name: str, response: dict[str, Any], usage: dict[str, Any] | None) -> None: ...

    def purge(self, older_than_days: int) -> int: ...


class MemoryCallCache:
    """시험용 메모리 저장소. 같은 동작을 PostgresCallCache가 DB 표로 합니다."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self.rows: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.rows.get(key)
            return dict(row["response"]) if row else None

    def put(self, key: str, model: str, call_name: str, response: dict[str, Any], usage: dict[str, Any] | None) -> None:
        with self._lock:
            self.rows.setdefault(key, {"model": model, "callName": call_name, "response": dict(response), "usage": usage, "createdAt": self._clock()})

    def purge(self, older_than_days: int) -> int:
        limit = self._clock() - older_than_days * 86_400
        with self._lock:
            old = [key for key, row in self.rows.items() if row["createdAt"] < limit]
            for key in old:
                del self.rows[key]
        return len(old)


class PostgresCallCache:
    """extraction_call_cache 표 (migrations/V202610201010). autocommit 연결을 받습니다(psycopg 3 연결은 여러 스레드가 함께 써도 됩니다)."""

    def __init__(self, conn):
        self.conn = conn

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute("select response from extraction_call_cache where key = %s", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, call_name: str, response: dict[str, Any], usage: dict[str, Any] | None) -> None:
        from psycopg.types.json import Jsonb

        self.conn.execute(
            "insert into extraction_call_cache (key, model, call_name, response, usage) values (%s, %s, %s, %s, %s) on conflict (key) do nothing",
            (key, model, call_name, Jsonb(response), Jsonb(usage) if usage is not None else None),
        )

    def purge(self, older_than_days: int) -> int:
        cur = self.conn.execute("delete from extraction_call_cache where created_at < now() - make_interval(days => %s)", (older_than_days,))
        return cur.rowcount


class CachedModel:
    """성공한 호출을 저장해 두고 같은 요청이면 저장한 응답을 돌려주는 감싸기.

    유료 모델은 예산(BudgetedModel) 바깥을 감쌉니다: 다시 쓴 응답은 예산을 쓰지 않습니다.
    identity: 감싼 제공자의 열쇠 재료(모델 설정·실제 요청 본문 해시). 제공자마다 cache_identity를 둡니다."""

    def __init__(self, model: ExtractionModel, cache: CallCache, identity: Callable[[ModelRequest], dict[str, Any]], label: str):
        self.model = model
        self.cache = cache
        self.identity = identity
        self.label = label

    def complete(self, request: ModelRequest) -> ModelResponse:
        key = cache_key(request, self.identity(request))
        try:
            stored = self.cache.get(key)
        except Exception as error:  # 저장소 장애는 추출을 멈추지 않습니다
            log.warning("호출 캐시를 읽지 못해 실제로 호출합니다", extra={"call": request.call_name, "error": type(error).__name__})
            stored = None
        if stored is not None:
            return hit_response(stored)
        response = self.model.complete(request)
        if reusable(request, response):
            try:
                self.cache.put(key, self.label, request.call_name, to_record(response), response.usage)
            except Exception as error:
                log.warning("호출 캐시에 저장하지 못했습니다", extra={"call": request.call_name, "error": type(error).__name__})
        return response
