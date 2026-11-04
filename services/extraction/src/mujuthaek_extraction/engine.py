"""추출 실행 방식 선택 (2026-11-04, AI 추출 에이전트화 1단계).

EXTRACTION_ENGINE
  graph (기본): 단계 함수를 LangGraph 상태 그래프의 노드로 실행합니다(graph/).
  legacy: pipeline._process가 같은 단계 함수를 차례로 부릅니다. 결과는 graph와 같습니다(test_engine_equivalence).

두 방식의 결과가 같음을 확인해 기본값을 graph로 바꿨습니다(2026-11-04). legacy는 다음 변경에서 지웁니다.
"""

from __future__ import annotations

import os

LEGACY = "legacy"
GRAPH = "graph"
ENGINES = (LEGACY, GRAPH)


def extraction_engine() -> str:
    engine = os.getenv("EXTRACTION_ENGINE", GRAPH)
    if engine not in ENGINES:
        raise ValueError(f"EXTRACTION_ENGINE는 {list(ENGINES)} 중 하나여야 합니다: {engine!r}")
    return engine
