"""V2 추출 그래프(EXTRACTION_ENGINE=v2). 흐름은 LangGraph, 에이전트는 노드 안에서 LangChain create_agent로 돕니다.

    intake ─(준비 안 됨·규칙 없음)─▶ END
      └▶ document ─┬▶ plan ──────┬▶ dispatch ─▶ section(일정·자격·선정·서류, 담당마다 Send 병렬) ▶ conclude ▶ END
                   └▶ structure ─┘

- document: 원문(그림 쪽은 지금은 V1 그림 판독으로 글자를 붙임, 그림 판독 에이전트로 바꿀 자리) → 문서 모델(줄·표·칸 id)
- plan: 담당 목록과 담당들이 함께 쓰는 도구 섹션을 정하고, 담당들의 같은 앞부분(지시·도구·원문 전체)을 한 번 캐시에 올림(prime).
  구조와 동시에 돌아 시간이 들지 않음. 담당들이 동시에 처음 보내면 저마다 앞부분을 캐시에 올려 쓰기 값을 담당 수만큼 냄.
  계획 에이전트가 표 해석·섹션별 담당 범위를 정할 자리이기도 함
- structure: 공고 기본·위치·공급. 공급·가격 표는 코드가 옮기고(V1 공급표 장치, 열 의미만 AI) 공고·위치는 한 번 호출 — V1과 같은 방식.
  다른 담당이 그 id를 쓰므로 먼저(2026-11-06 첫 실제 실행: 에이전트가 공급 묶음을 손으로 넣다 가격이 거의 다 빠짐)
- section: 판단이 많은 나머지 담당이 에이전트로 동시에. 담당이 낸 V1 AI 조각·호출 기록·대화 기록을 리듀서로 합침
- conclude: V1과 같은 결합·검증·계약 정리·게시·기록(틀린 값 0을 지키는 결정론 부분은 V1의 검증된 코드)

AGENTS(담당 이름 → 실행 함수)에 꽂으면 그것을 씁니다(시험). 꽂힌 것이 없으면 구조는 V1 방식, 나머지는 섹션 에이전트(v2/agents/section.py).
"""

from __future__ import annotations

import dataclasses
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
    context: Any  # V1 TrustedContext(그림 판독 뒤 문서 기록 — 판독 글을 붙인 원문의 해시)
    image_run: ExtractionRun | None
    structure_run: ExtractionRun | None  # 구조(V1 방식) 호출 기록
    document: DocumentModel
    plan: dict[str, Any]
    structure: dict[str, Any] | None  # 구조가 낸 id·이름 요약(뒤 담당이 참조)
    worker: str  # Send로 넘기는 담당 이름
    parts: Annotated[list[dict[str, Any]], operator.add]
    usage: Annotated[list[dict[str, Any]], operator.add]
    traces: Annotated[list[dict[str, Any]], operator.add]  # 담당 대화 기록(도구 호출·결과 앞부분)
    outcome: pipeline.Outcome


# 담당 실행 함수: (담당 호출 정의, 상태, 실행 환경) → (V1 AI 조각들, 모델 호출 기록[, 대화 기록])
SectionAgent = Callable[[CallSpec, V2State, pipeline.Runtime], tuple[Any, ...]]
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
    # 판독이 돌려준 문서 기록을 씁니다(2026-11-06: 원래 기록으로 검증해 그림 공고의 근거 55개가 모두 해시 불일치)
    material, context, image_run = pipeline.read_images(state["intake"].material, state["intake"].context, runtime.context)
    return {"material": material, "context": context, "image_run": image_run, "document": build_document(material), "parts": [], "usage": [], "traces": []}


def plan(state: V2State, runtime: Context) -> dict[str, Any]:
    named = workers(state["rules"])
    planned = {"workers": list(named), "sections": [section for name, spec in named.items() if name != STRUCTURE for section in spec.sections]}
    from mujuthaek_extraction.v2.agents.section import prime  # 담당 공통 앞부분 캐시 데우기(LangChain)

    return {"plan": planned, "usage": prime({**state, "plan": planned}, runtime.context)}


def structure(state: V2State, runtime: Context) -> dict[str, Any]:
    spec = workers(state["rules"])[STRUCTURE]
    if STRUCTURE in AGENTS:
        parts, usage, trace = _unpack(AGENTS[STRUCTURE](spec, state, runtime.context))
        return {"parts": parts, "usage": usage, "traces": trace, "structure": structure_summary(parts[0]) if parts else None}
    only = dataclasses.replace(state["rules"], calls=(spec,), split_calls=(), large_text_chars=None)
    run = pipeline.extract_parts(only, state["material"], runtime.context).run
    summary = run.structure or (structure_summary(run.parts[0]) if run.parts else None)
    return {"parts": list(run.parts), "structure": summary, "structure_run": run}


def dispatch(state: V2State, runtime: Context) -> dict[str, Any]:
    """계획(캐시 데우기)과 구조가 모두 끝나기를 기다리는 자리. 담당은 구조 id와 데운 캐시를 함께 씁니다."""
    return {}


def fan_out(state: V2State) -> list[Send]:
    names = [name for name in state["plan"]["workers"] if name != STRUCTURE]
    return [Send("section", {**state, "worker": name, "parts": state.get("parts") or [], "usage": [], "traces": []}) for name in names]


def section(state: V2State, runtime: Context) -> dict[str, Any]:
    spec = workers(state["rules"])[state["worker"]]
    agent = AGENTS.get(spec.name)
    if agent is None:
        from mujuthaek_extraction.v2.agents.section import run_section  # 섹션 담당 에이전트(LangChain)

        agent = run_section
    parts, usage, trace = _unpack(agent(spec, state, runtime.context))
    return {"parts": parts, "usage": usage, "traces": trace}


def conclude(state: V2State, runtime: Context) -> dict[str, Any]:
    rt = runtime.context
    material, context = state["material"], state["context"]
    base = state.get("structure_run") or ExtractionRun()
    run = ExtractionRun(
        parts=list(state.get("parts") or []),
        attempts=list(base.attempts),
        failed_calls=list(base.failed_calls),
        raw_responses=list(base.raw_responses),
        structure=state.get("structure"),
    )
    extracted = pipeline.Extracted(run, None, rt.models.names.get("primary", "primary"), rt.models.primary)
    rt.usage.record("v2", {"calls": state.get("usage") or [], "workers": state["plan"]["workers"], "traces": state.get("traces") or []})
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


def _unpack(result: tuple[Any, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    parts, usage = result[0], result[1]
    trace = [result[2]] if len(result) > 2 and result[2] else []
    return parts, usage, trace


def _done_or(next_node: str):
    def route(state: V2State) -> str:
        return END if "outcome" in state else next_node

    return route


def build() -> Any:
    graph = StateGraph(V2State)  # 실행 환경(pipeline.Runtime)은 문맥으로 넘기되 형식은 주지 않음(예산 장부의 잠금을 Pydantic 형식으로 만들지 않게)
    for node in (intake, document, plan, structure, dispatch, section, conclude):
        graph.add_node(node.__name__, node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _done_or("document"), ["document", END])
    graph.add_edge("document", "plan")
    graph.add_edge("document", "structure")
    graph.add_edge(["plan", "structure"], "dispatch")
    graph.add_conditional_edges("dispatch", fan_out, ["section"])
    graph.add_edge("section", "conclude")
    graph.add_edge("conclude", END)
    return graph.compile()


V2_GRAPH = build()
