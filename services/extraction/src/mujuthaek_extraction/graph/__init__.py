"""추출 단계를 LangGraph 상태 그래프로 실행합니다 (EXTRACTION_ENGINE=graph).

노드는 pipeline의 단계 함수를 그대로 부르므로 결과는 기존 경로(_process)와 같습니다.
모델·리더·코드표처럼 처리 내내 같은 값은 상태가 아니라 실행 문맥(pipeline.Runtime)으로 넘깁니다.
"""

from mujuthaek_extraction.graph.build import GRAPH, run_graph

__all__ = ["GRAPH", "run_graph"]
