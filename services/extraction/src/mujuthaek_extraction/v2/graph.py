"""V2 추출 그래프(EXTRACTION_ENGINE=v2). 흐름은 LangGraph, 에이전트는 노드 안에서 LangChain create_agent로 돕니다.

    intake ─(준비 안 됨·규칙 없음)─▶ END
      └▶ document ▶ plan ▶ structure ─▶ section(일정·자격·선정·서류, 담당마다 Send 병렬) ▶ conclude ▶ END

- document: 원문(그림 쪽은 지금은 V1 그림 판독으로 글자를 붙임, 5단계에서 그림 판독 에이전트로) → 문서 모델(줄·표·칸 id)
- plan: 계획 에이전트가 표 해석·섹션별 담당 범위를 정함(2단계). 지금은 담당 목록만
- structure: 공고 기본·위치·공급. 다른 담당이 그 id를 쓰므로 먼저
- section: 나머지 담당이 동시에. 담당이 낸 V1 AI 조각을 parts에 더함(리듀서)
- conclude: V1과 같은 결합·검증·계약 정리·게시·기록(틀린 값 0을 지키는 결정론 부분은 V1의 검증된 코드)

담당은 섹션 에이전트(v2/agents/section.py)이고, AGENTS(담당 이름 → 실행 함수)에 꽂으면 그것을 씁니다(시험).
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime as GraphRuntime
from langgraph.types import Send

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.extract import ExtractionRun
from mujuthaek_extraction.recheck import RecheckResult
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, structure_summary
from mujuthaek_extraction.v2.document import DocumentModel
from mujuthaek_extraction.v2.document import build as build_document

STRUCTURE = "structure"


class V2State(TypedDict, total=False):
    raw_event: dict[str, Any]
    method: str
    intake: Any  # V1 IntakeResult
    rules: FieldRules
    material: Any  # V1 ExtractionMaterial(그림 판독 글자 포함)
    image_run: ExtractionRun | None
    document: DocumentModel
    plan: dict[str, Any]
    structure: dict[str, Any] | None  # 구조 담당이 낸 id·이름 요약(뒤 담당이 참조)
    worker: str  # Send로 넘기는 담당 이름
    parts: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[list[dict[str, Any]], operator.add]
    outcome: pipeline.Outcome


# 담당 실행 함수: (담당 호출 정의, 상태, 실행 환경) → (V1 AI 조각들, 모델 호출 기록)
SectionAgent = Callable[[CallSpec, V2State, pipeline.Runtime], tuple[list[dict[str, Any]], list[dict[str, Any]]]]
AGENTS: dict[str, SectionAgent] = {}

Context = GraphRuntime[pipeline.Runtime]


def intake(state: V2State, runtime: Context) -> dict[str, Any]:
    result = pipeline.read_intake(state["raw_event"], state["method"], runtime.context)
    if not result.ready:
        return {"outcome": pipeline.not_ready_outcome(result)}
    rules = pipeline.RULES_BY_METHOD[state["method"]].get(result.raw.field)
    if rules is None:
        return {"outcome": pipeline.unsupported_outcome(result.raw.field)}
    return {"intake": result, "rules": rules}


def document(state: V2State, runtime: Context) -> dict[str, Any]:
    material, _, image_run = pipeline.read_images(state["intake"].material, state["intake"].context, runtime.context)
    return {"material": material, "image_run": image_run, "document": build_document(material), "parts": [], "usage": []}


def plan(state: V2State, runtime: Context) -> dict[str, Any]:
    return {"plan": {"workers": list(workers(state["rules"]))}}


def structure(state: V2State, runtime: Context) -> dict[str, Any]:
    spec = workers(state["rules"])[STRUCTURE]
    parts, usage = _run(spec, state, runtime.context)
    return {"parts": parts, "usage": usage, "structure": structure_summary(parts[0]) if parts else None}


def fan_out(state: V2State) -> list[Send]:
    names = [name for name in state["plan"]["workers"] if name != STRUCTURE]
    return [Send("section", {**state, "worker": name, "parts": [], "usage": []}) for name in names]


def section(state: V2State, runtime: Context) -> dict[str, Any]:
    spec = workers(state["rules"])[state["worker"]]
    parts, usage = _run(spec, state, runtime.context)
    return {"parts": parts, "usage": usage}


def conclude(state: V2State, runtime: Context) -> dict[str, Any]:
    rt = runtime.context
    material, context = state["material"], state["intake"].context
    parts = state.get("parts") or []
    run = ExtractionRun(parts=list(parts))
    extracted = pipeline.Extracted(run, None, rt.models.names.get("primary", "primary"), rt.models.primary)
    rt.usage.record("v2", {"calls": state.get("usage") or [], "workers": state["plan"]["workers"]})
    report = pipeline.evaluate_parts(run.parts, material, context, rt)
    if report is None:
        return {"outcome": pipeline.extraction_failed_outcome(extracted, state.get("image_run"), material, rt)}
    recheck = RecheckResult(run.parts, report, [], False, None)
    repairs: list[str] = []
    if report.contract_errors:
        report, actions = pipeline.quarantine_step(report, recheck, material, context, rt)
        repairs += actions
        pipeline.note_changes(report, extracted, recheck, actions)
    publication = pipeline.publish_step(report, state["raw_event"], material, rt)
    outcome = pipeline.finish(state["raw_event"], report, recheck, publication, extracted, state.get("image_run"), repairs, material, rt)
    return {"outcome": outcome}


def workers(rules: FieldRules) -> dict[str, CallSpec]:
    """섹션 담당 = V1 섹션 호출(큰 공고용으로 나눈 호출을 늘 씀: 자격·선정·서류를 따로)."""
    split = dict(rules.split_calls)
    return {call.name: call for parent in rules.calls for call in split.get(parent.name, (parent,))}


def _run(spec: CallSpec, state: V2State, rt: pipeline.Runtime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    agent = AGENTS.get(spec.name)
    if agent is None:
        from mujuthaek_extraction.v2.agents.section import run_section  # 섹션 담당 에이전트(LangChain)

        agent = run_section
    return agent(spec, state, rt)


def _done_or(next_node: str):
    def route(state: V2State) -> str:
        return END if "outcome" in state else next_node

    return route


def build() -> Any:
    graph = StateGraph(V2State)  # 실행 환경(pipeline.Runtime)은 문맥으로 넘기되 형식은 주지 않음(예산 장부의 잠금을 Pydantic 형식으로 만들지 않게)
    for node in (intake, document, plan, structure, section, conclude):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _done_or("document"), ["document", END])
    graph.add_edge("document", "plan")
    graph.add_edge("plan", "structure")
    graph.add_conditional_edges("structure", fan_out, ["section"])
    graph.add_edge("section", "conclude")
    graph.add_edge("conclude", END)
    return graph.compile()


V2_GRAPH = build()
