"""로컬 AI 연결 (결정 C12: 기본 모델). OpenAI 호환 /chat/completions를 쓰는 서버(Ollama·vLLM·llama.cpp 등)를 가정합니다.

로컬 AI 규격은 구축할 때 확정합니다. 지금은 가장 흔한 OpenAI 호환 형식으로 두고, 바뀌면 이 파일만 고칩니다.
- 주소가 없거나 연결이 안 되면 ModelError를 내서 FallbackOnErrorModel이 바로 유료 API로 넘기게 합니다.
- 연결 실패 뒤 잠시(down_seconds) 로컬 AI를 건너뛰어, 호출마다 연결 대기 시간을 다시 쓰지 않게 합니다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from mujuthaek_extraction.model.base import ModelError, ModelRequest, ModelResponse, StopReason
from mujuthaek_extraction.model.call_cache import canonical, response_code_hash, sha256_text
from mujuthaek_extraction.model.strict_schema import drop_null_optionals, to_strict


class LocalChatModel:
    """OpenAI 호환 /chat/completions 로컬 AI 서버에 엄격 JSON 스키마로 요청하는 추출 모델입니다."""

    supports_tools = False  # 도구 호출은 아직 보내지 않습니다(재확인은 한 번에 묶어 묻기로 돌아감)

    def __init__(
        self,
        base_url: str | None,
        model: str = "local",
        timeout_seconds: float = 900,
        down_seconds: float = 60,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.down_seconds = down_seconds
        self._opener = opener
        self._clock = clock
        self._down_until = 0.0
        self._optional_names: dict[str, frozenset[str]] = {}

    def __repr__(self) -> str:
        return f"LocalChatModel(base_url={self.base_url!r}, model={self.model!r})"

    def body(self, request: ModelRequest) -> dict[str, Any]:
        strict, optional = to_strict(request.output_schema)
        self._optional_names[request.call_name] = optional
        return {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user + "\n\n" + request.instructions},
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": f"extraction_{request.call_name}", "strict": True, "schema": strict}},
        }

    def cache_identity(self, request: ModelRequest) -> dict[str, Any]:
        """호출 캐시 열쇠 재료(call_cache): 서버 주소·모델과 실제로 보낼 요청 본문의 해시, 응답 처리 코드 해시."""
        return {"provider": "local-chat", "url": self.base_url, "body": sha256_text(canonical(self.body(request))), "code": response_code_hash()}

    def complete(self, request: ModelRequest) -> ModelResponse:
        """요청을 로컬 AI에 보내 응답을 돌려줍니다. 실패는 모두 영구 ModelError이고, 연결 실패면 down_seconds 동안 건너뜁니다."""
        if not self.base_url:
            raise ModelError("로컬 AI 주소(LOCAL_AI_URL)가 설정되지 않았습니다.", transient=False, code="NOT_CONFIGURED")
        if self._clock() < self._down_until:
            raise ModelError("로컬 AI가 최근 연결되지 않아 잠시 건너뜁니다.", transient=False, code="SKIPPED_DOWN")
        http_request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(self.body(request), ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(http_request, timeout=self.timeout_seconds) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise ModelError(f"로컬 AI HTTP {error.code}", transient=False, code=f"HTTP_{error.code}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            self._down_until = self._clock() + self.down_seconds
            raise ModelError(f"로컬 AI 연결 실패: {type(error).__name__}", transient=False, code="CONNECTION") from None
        except ValueError:
            raise ModelError("로컬 AI 응답이 JSON이 아닙니다.", transient=False, code="BAD_JSON") from None
        return self.parse(request, result)

    def parse(self, request: ModelRequest, result: dict[str, Any]) -> ModelResponse:
        """chat/completions 응답을 ModelResponse로 바꿉니다. 정상 종료면 엄격 모드가 채운 선택 칸의 null을 걷어 냅니다."""
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish = choice.get("finish_reason")
        if message.get("refusal"):
            stop = StopReason.REFUSED
        elif finish == "length":
            stop = StopReason.MAX_TOKENS
        elif finish == "stop":
            stop = StopReason.END
        else:
            stop = StopReason.OTHER
        raw_text = message.get("content") or ""
        if stop is StopReason.END:
            try:
                raw_text = json.dumps(drop_null_optionals(json.loads(raw_text), self._optional_names.get(request.call_name, frozenset())), ensure_ascii=False)
            except ValueError:
                pass  # 실행기가 JSON 오류로 처리합니다
        usage = result.get("usage") or {}
        return ModelResponse(
            raw_text=raw_text,
            model_id=result.get("model") or self.model,
            stop_reason=stop,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            usage=usage,
            reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        )
