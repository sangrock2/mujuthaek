"""추출 그래프 조립.

    intake ─(준비 안 됨·규칙 없음)─▶ END
      └▶ image_reading ▶ extract ▶ assemble_verify ─(결합 실패)─▶ END
                                       └▶ recheck ─(계약 오류)─▶ quarantine ─┐
                                              └────────────────────────────▶ annotate ▶ publish ▶ finish ▶ END

노드는 pipeline의 단계 함수를 부르기만 합니다. outcome이 생긴 노드 다음은 END입니다.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime as GraphRuntime

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.graph.state import ExtractionState
from mujuthaek_extraction.method import extraction_method
from mujuthaek_extraction.pipeline import Outcome, Runtime

Context = GraphRuntime[Runtime]


def intake(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    result = pipeline.read_intake(state["raw_event"], state["method"], runtime.context)
    if not result.ready:
        return {"outcome": pipeline.not_ready_outcome(result)}
    rules = pipeline.RULES_BY_METHOD[state["method"]].get(result.raw.field)
    if rules is None:
        return {"outcome": pipeline.unsupported_outcome(result.raw.field)}
    return {"intake": result, "rules": rules}


def image_reading(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    material, context, image_run = pipeline.read_images(state["intake"].material, state["intake"].context, runtime.context)
    return {"material": material, "context": context, "image_run": image_run}


def extract(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    return {"extracted": pipeline.extract_parts(state["rules"], state["material"], runtime.context)}


def assemble_verify(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    rt = runtime.context
    first = pipeline.first_report(state["extracted"], state["material"], state["context"], rt)
    if first is None:
        return {"outcome": pipeline.extraction_failed_outcome(state["extracted"], state["image_run"], state["material"], rt)}
    return {"first": first}


def recheck(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    result, repairs = pipeline.recheck_step(state["rules"], state["material"], state["context"], state["extracted"], state["first"], runtime.context)
    return {"recheck": result, "report": result.report, "repairs": repairs, "quarantine_actions": []}


def quarantine(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    report, actions = pipeline.quarantine_step(state["report"], state["recheck"], state["material"], state["context"], runtime.context)
    return {"report": report, "quarantine_actions": actions, "repairs": [*state["repairs"], *actions]}


def annotate(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    pipeline.note_changes(state["report"], state["extracted"], state["recheck"], state["quarantine_actions"])
    return {}


def publish(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    return {"publication": pipeline.publish_step(state["report"], state["raw_event"], state["material"], runtime.context)}


def finish(state: ExtractionState, runtime: Context) -> dict[str, Any]:
    outcome = pipeline.finish(
        state["raw_event"],
        state["report"],
        state["recheck"],
        state["publication"],
        state["extracted"],
        state["image_run"],
        state["repairs"],
        state["material"],
        runtime.context,
    )
    return {"outcome": outcome}


def _done_or(next_node: str):
    def route(state: ExtractionState) -> str:
        return END if "outcome" in state else next_node

    return route


def _after_recheck(state: ExtractionState) -> str:
    return "quarantine" if state["report"].contract_errors else "annotate"


def build() -> Any:
    graph = StateGraph(ExtractionState, context_schema=Runtime)
    for node in (intake, image_reading, extract, assemble_verify, recheck, quarantine, annotate, publish, finish):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _done_or("image_reading"), ["image_reading", END])
    graph.add_edge("image_reading", "extract")
    graph.add_edge("extract", "assemble_verify")
    graph.add_conditional_edges("assemble_verify", _done_or("recheck"), ["recheck", END])
    graph.add_conditional_edges("recheck", _after_recheck, ["quarantine", "annotate"])
    graph.add_edge("quarantine", "annotate")
    graph.add_edge("annotate", "publish")
    graph.add_edge("publish", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


GRAPH = build()


def run_graph(raw_event: dict[str, Any], rt: Runtime, method: str | None = None) -> Outcome:
    state = GRAPH.invoke({"raw_event": raw_event, "method": method or extraction_method()}, context=rt)
    return state["outcome"]
