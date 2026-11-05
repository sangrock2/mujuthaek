"""설정 → 공고 1건에 쓸 모델 묶음 (결정 C12).

auto (기본): primary = 로컬 AI, fallback = 유료 API(gpt-6-luna, 공고당 비용 상한)
  - 로컬 AI 호출이 실패(주소 없음·연결 안 됨)하면 그 호출만 바로 유료 API로 (FallbackOnErrorModel)
  - 로컬 AI 결과가 부족(실패 호출·계약 위반)하면 공고 전체를 유료 API로 다시 (extract_with_fallback)
  - LOCAL_AI_URL이 없으면(로컬 AI 구축 전) 유료 API를 바로 씁니다
  - 유료 API 키가 없으면 fallback 없이 로컬 AI만 씁니다(로컬도 안 되면 추출 실패로 기록)
recorded: 녹화 응답 재생(가짜 추출기). 유료 호출 없음

호출 캐시(call_cache, 설정 EXTRACTION_CALL_CACHE): 저장소를 받으면 로컬 AI와 유료 API를 CachedModel로 감쌉니다.
  유료 API는 예산 바깥을 감싸 다시 쓴 응답은 예산을 쓰지 않습니다. 녹화 재생은 감싸지 않습니다.
예산은 같은 원본 버전의 앞선 처리가 쓴 비용(spent_before)부터 셉니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, ModelResponse, StopReason
from mujuthaek_extraction.model.call_cache import CachedModel, CallCache
from mujuthaek_extraction.model.file_exchange import FileExchangeModel
from mujuthaek_extraction.model.local_ai import LocalChatModel
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel
from mujuthaek_extraction.model.runaway import runaway


class UnavailableModel:
    """쓸 수 있는 모델이 없을 때. 호출하면 항상 실패합니다."""

    def __init__(self, reason: str):
        self.reason = reason

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise ModelError(self.reason, transient=False, code="UNAVAILABLE")


class ReplayModel:
    """녹화 응답 재생 (EXTRACTION_MODEL_MODE=recorded). 폴더의 <호출 이름>.json(응답 문자열 목록)에서 첫 응답을 매번 돌려줍니다."""

    def __init__(self, folder: Path):
        self.answers: dict[str, str] = {}
        for path in folder.glob("*.json"):
            items = json.loads(path.read_text(encoding="utf-8"))
            if items:
                self.answers[path.stem] = items[0] if isinstance(items[0], str) else json.dumps(items[0], ensure_ascii=False)

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.call_name not in self.answers:
            raise ModelError(f"녹화 응답이 없는 호출입니다: {request.call_name}", transient=False, code="NO_RECORDING")
        return ModelResponse(raw_text=self.answers[request.call_name], model_id="recorded", stop_reason=StopReason.END)


# V2 호출 한 번의 기본 출력 상한(생각 토큰 포함). 섹션 담당은 원문 전체를 보고 첫 차례에 맡은 항목을 다 넣으므로
# V1 섹션 호출의 출력 한도(CallSpec.max_output_tokens, 실측 최대의 약 1.3배)를 그대로 씁니다(잘리면 그 차례 도구 호출을 통째로 잃음)
V2_OUTPUT_TOKENS = 16_000


@dataclass
class NoticeModels:
    primary: ExtractionModel
    fallback: ExtractionModel | None
    budget: Budget | None = None  # 유료 API 비용 (공고 1건)
    names: dict[str, str] = field(default_factory=dict)
    # V2 에이전트 모델(LangChain): 담당 이름 → 채팅 모델. 같은 공고의 담당들은 프롬프트 캐시 열쇠를 함께 씀. 없으면 V2 에이전트를 돌리지 않음
    chat: Any = None


class ModelFactory:
    """설정에 맞는 모델(로컬 AI·유료 API·녹화 재생)을 한 번 만들어 두고, 공고마다 쓸 모델 묶음을 내줍니다."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._local = LocalChatModel(settings.local_ai_url, settings.local_ai_model)  # 연결 실패 기억을 공고 사이에 유지합니다
        self._paid: OpenAIResponsesModel | None = None
        if settings.model_mode == "auto":
            key = settings.openai_api_key()
            if key:
                self._paid = OpenAIResponsesModel(
                    key,
                    model=settings.openai_model,
                    reasoning_effort=settings.openai_effort,
                    shared_schema=settings.openai_shared_schema,
                    light_calls=frozenset(settings.openai_light_calls),
                    light_effort=settings.openai_light_effort,
                    stream=settings.openai_stream,
                    runaway_check=runaway,
                )
        self._replay = ReplayModel(settings.recorded_dir) if settings.model_mode == "recorded" and settings.recorded_dir else None
        self._standin = (
            FileExchangeModel(settings.standin_dir, replay=settings.standin_replay_dir) if settings.model_mode == "standin" and settings.standin_dir else None
        )

    def describe(self) -> str:
        """로그용 요약. 키는 넣지 않습니다."""
        if self.settings.model_mode == "recorded":
            return f"recorded({self.settings.recorded_dir})"
        if self.settings.model_mode == "standin":
            return f"standin({self.settings.standin_dir})"
        local = self.settings.local_ai_url or "없음"
        paid = self.settings.openai_model if self._paid else "키 없음"
        return f"auto(로컬 AI {local} → 유료 {paid}, 공고당 ${self.settings.notice_budget_usd:.2f})"

    def for_notice(self, cache: CallCache | None = None, spent_before_usd: float = 0.0, ledger: Any = None) -> NoticeModels:
        """cache: 성공한 호출을 다시 쓸 저장소(설정이 꺼져 있으면 쓰지 않음). spent_before_usd: 같은 원본 버전의 앞선 처리가 쓴 유료 비용.
        ledger: DB 비용 장부(model/spend.py). 있으면 하루·월 전체 상한도 지킵니다."""
        if self.settings.model_mode == "recorded":
            model = self._replay or UnavailableModel("EXTRACTION_RECORDED_DIR가 없습니다.")
            return NoticeModels(model, None, names={"primary": "recorded"})
        if self.settings.model_mode == "standin":
            model = self._standin or UnavailableModel("EXTRACTION_STANDIN_DIR가 없습니다.")
            return NoticeModels(model, None, names={"primary": "standin"})
        cache = cache if self.settings.call_cache else None
        local: ExtractionModel = self._local
        if cache is not None and self.settings.local_ai_url:
            local = CachedModel(self._local, cache, self._local.cache_identity, "local")
        if self._paid is None:
            return NoticeModels(local, None, names={"primary": "local"})
        budget = Budget(self.settings.openai_model, self.settings.notice_budget_usd, prior_usd=spent_before_usd, ledger=ledger)
        paid: ExtractionModel = BudgetedModel(self._paid, budget)
        if cache is not None:  # 예산 바깥: 다시 쓴 응답은 예산을 쓰지 않습니다
            paid = CachedModel(paid, cache, self._paid.cache_identity, self.settings.openai_model)
        chat = self._chat_models(cache)
        if not self.settings.local_ai_url:  # 로컬 AI가 아직 없으면 유료 API를 바로 씁니다 (같은 모델로 두 번 추출하지 않게)
            return NoticeModels(paid, None, budget, {"primary": self.settings.openai_model}, chat)
        return NoticeModels(local, paid, budget, {"primary": "local", "fallback": self.settings.openai_model}, chat)

    def _chat_models(self, cache: CallCache | None = None):
        """V2 담당별 채팅 모델(LangChain ChatOpenAI). 공고 하나의 담당들이 같은 프롬프트 캐시 열쇠를 씁니다(공통 지시·도구·원문이 같은 앞부분).
        light: 기계적인 호출(캐시 데우기)은 낮은 추론 강도로. 평가용 파일 저장소(FileCallCache)를 받으면 V2 채팅 답도 그 아래 v2-chat에 두고
        같은 요청을 다시 사지 않습니다."""
        import uuid

        key = f"v2-{uuid.uuid4().hex[:16]}"
        folder = getattr(cache, "folder", None)
        saved: list[Any] = []

        def chat(agent: str, *, light: bool = False, max_output_tokens: int | None = None) -> Any:
            # V2 담당을 실제로 부를 때만 LangChain을 가져옵니다
            from mujuthaek_extraction.v2.llm.cache import FileLLMCache
            from mujuthaek_extraction.v2.llm.models import chat_model

            if folder is not None and not saved:
                saved.append(FileLLMCache(Path(folder) / "v2-chat"))
            return chat_model(
                self.settings,
                effort=self.settings.openai_light_effort if light else None,
                cache_key=key,
                max_output_tokens=max_output_tokens or V2_OUTPUT_TOKENS,
                cache=saved[0] if saved else None,
            )

        return chat
