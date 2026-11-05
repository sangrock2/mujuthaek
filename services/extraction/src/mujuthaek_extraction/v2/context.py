"""V2 실행 문맥: 공고 하나를 처리하는 동안 에이전트·도구가 함께 쓰는 값.

LangGraph 노드는 Runtime.context로, LangChain 도구는 ToolRuntime.context로 같은 값을 받습니다(상태에 넣지 않아 체크포인트에 저장되지 않음).
"""

from __future__ import annotations

from dataclasses import dataclass

from mujuthaek_extraction.v2.document import DocumentModel


@dataclass
class V2Context:
    document: DocumentModel
