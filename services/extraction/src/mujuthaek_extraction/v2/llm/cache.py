"""같은 요청 다시 쓰기(LangChain BaseCache): 성공한 모델 답을 파일로 두고, 요청(메시지·도구·모델 설정)이 완전히 같으면 비용 없이 다시 씁니다.

평가용입니다(같은 공고를 고친 코드로 다시 돌릴 때 바뀌지 않은 차례는 다시 사지 않음). 꺼낸 답에는 표시를 붙여 예산 미들웨어가 비용 0으로 셉니다.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.messages import message_to_dict, messages_from_dict
from langchain_core.outputs import ChatGeneration

from mujuthaek_extraction.v2.llm.budget import CACHE_HIT


class FileLLMCache(BaseCache):
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        path = self._path(prompt, llm_string)
        if not path.exists():
            return None
        generations = []
        for saved in json.loads(path.read_text(encoding="utf-8")):
            message = messages_from_dict([saved["message"]])[0]
            message.response_metadata = {**message.response_metadata, CACHE_HIT: True}
            generations.append(ChatGeneration(message=message, generation_info=saved.get("generationInfo")))
        return generations

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        path = self._path(prompt, llm_string)
        with self._lock:
            if not path.exists():  # 같은 열쇠는 처음 답을 둡니다
                temporary = path.with_suffix(".tmp")
                saved = [{"message": message_to_dict(g.message), "generationInfo": g.generation_info} for g in return_val if isinstance(g, ChatGeneration)]
                temporary.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)

    def clear(self, **kwargs: Any) -> None:
        for path in self.folder.glob("*.json"):
            path.unlink()

    def _path(self, prompt: str, llm_string: str) -> Path:
        key = hashlib.sha256(json.dumps([prompt, llm_string], ensure_ascii=False).encode("utf-8")).hexdigest()
        return self.folder / f"{key}.json"
