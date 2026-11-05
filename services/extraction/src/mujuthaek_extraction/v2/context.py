"""V2 실행 문맥: 공고 하나를 처리하는 동안 에이전트·도구가 함께 쓰는 값.

LangGraph 노드는 Runtime.context로, LangChain 도구·미들웨어는 ToolRuntime.context·request.runtime.context로 같은 값을 받습니다
(상태에 넣지 않아 체크포인트에 저장되지 않음).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import SkipValidation

from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.v2.document import DocumentModel


@dataclass
class V2Context:
    document: DocumentModel
    budget: SkipValidation[Budget | None] = None  # 공고 예산 장부(V1과 같은 장부). 없으면 예산을 보지 않음(시험)
    usage: list[dict[str, Any]] = field(default_factory=list)  # 모델 호출 기록(에이전트·시간·토큰·비용)
