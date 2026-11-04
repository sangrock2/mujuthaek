"""저장된 응답을 순서대로 돌려주는 모델. 테스트·오프라인 재현용이며 네트워크를 쓰지 않습니다."""

from __future__ import annotations

import threading
from collections import defaultdict, deque

from mujuthaek_extraction.model.base import ModelError, ModelRequest, ModelResponse, StopReason


class RecordedModel:
    """호출 이름별로 정해 둔 응답·오류를 차례로 내주고, 받은 요청을 기록하는 테스트용 모델입니다.
    도구 호출 응답은 ModelResponse(tool_calls=...)로 녹화해 둡니다."""

    supports_tools = True

    def __init__(self, script: dict[str, list[ModelResponse | ModelError | str]], model_id: str = "recorded"):
        """script: 호출 이름 → 그 호출에 차례로 돌려줄 응답(문자열이면 정상 종료 응답)이나 던질 오류."""
        self.model_id = model_id
        self._script = defaultdict(deque, {name: deque(items) for name, items in script.items()})
        self.requests: list[ModelRequest] = []
        self._lock = threading.Lock()  # 병렬 호출(EXTRACTION_PARALLEL_CALLS)에서도 응답을 한 번씩만 내주게

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self._lock:
            self.requests.append(request)
            queue = self._script[request.call_name]
            if not queue:
                raise AssertionError(f"녹화된 응답이 없는 호출입니다: {request.call_name}")
            item = queue.popleft()
        if isinstance(item, ModelError):
            raise item
        if isinstance(item, str):
            return ModelResponse(raw_text=item, model_id=self.model_id, stop_reason=StopReason.END)
        return item
