"""모델 호출 재시도(LangChain ModelRetryMiddleware): 일시 오류만 다시 보냅니다.

2026-11-06 23건 측정: 담당 호출 하나가 시간 초과로 실패하자 재시도 없이 그래프·공고·측정 전체가 멈춤. 채팅 모델은 재시도를 미들웨어에
맡기려고 max_retries=0으로 두었는데 그 미들웨어가 없었음. V1(openai_responses)과 같은 기준으로 시간 초과·연결 끊김·408·409·429·5xx만
다시 보내고, 예산 초과·잘못된 요청은 바로 올립니다. 재시도마다 예산 미들웨어가 다시 예약하도록 예산 미들웨어 바깥에 둡니다.
"""

from __future__ import annotations

import openai
from langchain.agents.middleware import ModelRetryMiddleware

from mujuthaek_extraction.model.openai_responses import TRANSIENT_STATUS

RETRIES = 2  # 처음 호출 + 2번
FIRST_DELAY_SECONDS = 2.0  # 시험에서 0으로 바꿈


def transient(error: BaseException) -> bool:
    """다시 보내면 될 수 있는 오류인지(시간 초과·연결 끊김·408·409·429·5xx)."""
    if isinstance(error, openai.APIConnectionError | TimeoutError | ConnectionError):
        return True
    return isinstance(error, openai.APIStatusError) and error.status_code in TRANSIENT_STATUS


def retry_middleware() -> ModelRetryMiddleware:
    """일시 오류를 RETRIES번까지 다시 보내고, 그래도 실패하면 오류를 올립니다(담당 실행이 받아 그때까지의 초안만 남김)."""
    return ModelRetryMiddleware(max_retries=RETRIES, retry_on=transient, on_failure="error", initial_delay=FIRST_DELAY_SECONDS, max_delay=30.0)
