"""에이전트 방식 추출 그래프(EXTRACTION_ENGINE=agent).

    intake ─(준비 안 됨·규칙 없음)─▶ END
      └▶ agent(총괄 에이전트가 순서·방법을 정하고 하위 에이전트에 섹션을 맡김) ▶ conclude(결합·검증·결정 적용·발행) ▶ END

그림 판독·섹션 추출·다시 고치기는 고정 단계가 아니라 에이전트가 고르는 도구입니다(agentic/agents.py).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from mujuthaek_extraction.agentic.agents import run_supervisor
from mujuthaek_extraction.agentic.engine import conclude, make_env
from mujuthaek_extraction.graph.build import Context, _done_or, intake
from mujuthaek_extraction.graph.state import ExtractionState
from mujuthaek_extraction.pipeline import Runtime


def agent(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    env = make_env(state["rules"], state["intake"], runtime.context)
    run_supervisor(env)
    return {"agent_env": env}


def finish(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    return {"outcome": conclude(state["agent_env"], state["raw_event"], runtime.context)}


def build() -> Any:
    graph = StateGraph(ExtractionState, context_schema=Runtime)
    for node in (intake, agent, finish):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _done_or("agent"), ["agent", END])
    graph.add_edge("agent", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


AGENT_GRAPH = build()
