"""V2 모델: LangChain ChatOpenAI(Responses API). 키는 설정(환경 변수·.env)에서 읽고 출력하지 않습니다."""

from __future__ import annotations

from langchain_core.caches import BaseCache
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from mujuthaek_extraction.config import Settings

TIMEOUT_SECONDS = 180


def chat_model(
    settings: Settings,
    *,
    effort: str | None = None,
    max_output_tokens: int = 4_000,
    cache_key: str | None = None,
    cache: BaseCache | None = None,
) -> ChatOpenAI:
    """effort: 추론 강도(기본은 설정값). 기계적인 차례는 낮게, 판단이 큰 에이전트만 높게 둡니다.
    cache_key: OpenAI 프롬프트 캐시 열쇠(같은 공고·같은 에이전트의 차례들이 같은 앞부분을 다시 읽게).
    재시도는 모델 층이 아니라 LangGraph RetryPolicy·미들웨어가 맡습니다(max_retries=0, 예산 장부가 재시도마다 다시 예약)."""
    key = settings.openai_api_key()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=SecretStr(key) if key else None,
        use_responses_api=True,
        reasoning={"effort": effort or settings.openai_effort},
        max_tokens=max_output_tokens,
        store=False,
        timeout=TIMEOUT_SECONDS,
        max_retries=0,
        stream_usage=True,
        model_kwargs={"prompt_cache_key": cache_key} if cache_key else {},
        cache=cache,
    )
