"""추출 그래프(V2, 유일한 엔진 — pipeline.process가 run_graph로 부름). 흐름은 LangGraph, 에이전트는 노드 안에서 LangChain create_agent로 돕니다.

    intake ─(준비 안 됨·규칙 없음)─▶ END
      └▶ document ─┬▶ plan ──────┬▶ dispatch ─▶ section(일정·자격·선정·서류, 담당마다 Send 병렬) ▶ conclude ▶ END
                   └▶ structure ─┘          └─(채팅 모델 없음)─────────────────────────────────▶ conclude

채팅 모델이 없는 실행(로컬 AI·녹화·대역)은 담당 에이전트를 돌릴 수 없어, 구조 노드가 V1 방식 추출 전체(pipeline.extract_parts: 구조 →
섹션 호출, 대체 모델·병렬 간격 포함)를 돌리고 담당 없이 마무리로 갑니다. 마무리는 V1처럼 모든 섹션을 재확인합니다(2026-11-10: V1 정해진
단계 그래프·에이전트 방식 엔진을 걷어내며 이 길로 옮김 — 노드가 부르던 단계 함수는 그대로).

- document: 원문(그림 쪽은 지금은 V1 그림 판독으로 글자를 붙임, 그림 판독 에이전트로 바꿀 자리) → 문서 모델(줄·표·칸 id)
- plan: 담당 목록과 담당들이 함께 쓰는 도구 섹션을 정하고, 담당들의 같은 앞부분(지시·도구·원문 전체)을 한 번 캐시에 올림(prime).
  구조와 동시에 돌아 시간이 들지 않음. 담당들이 동시에 처음 보내면 저마다 앞부분을 캐시에 올려 쓰기 값을 담당 수만큼 냄.
  계획 에이전트가 표 해석·섹션별 담당 범위를 정할 자리이기도 함
- structure: 공고 기본·위치·공급. 공급·가격 표는 코드가 옮기고(V1 공급표 장치, 열 의미만 AI) 공고·위치는 한 번 호출 — V1과 같은 방식.
  다른 담당이 그 id를 쓰므로 먼저(2026-11-06 첫 실제 실행: 에이전트가 공급 묶음을 손으로 넣다 가격이 거의 다 빠짐).
  공급표가 있는 공고는 열 의미·공고·위치 호출을 담당과 같은 앞부분으로 보냄(v2/agents/structure.py, 끄면 V1 호출 층).
  이때 데우기는 계획이 아니라 구조가 먼저 보냄(캐시는 앞 요청이 끝난 자리에만 남아, 데우기가 끝난 뒤에 보내야 원문을 함께 읽음)
- section: 판단이 많은 나머지 담당이 에이전트로 동시에. 담당이 낸 V1 AI 조각·호출 기록·대화 기록을 리듀서로 합침
- conclude: 구조 단계 섹션(공고·위치·공급)의 문제만 V1 재확인으로 한 번 더 보고(담당 섹션은 담당이 검증 미들웨어로 이미 고침),
  V1과 같은 결합·검증·계약 정리·게시·기록(틀린 값 0을 지키는 결정론 부분은 V1의 검증된 코드).
  2026-11-06 23건 측정: 구조 단계는 V1 방식인데 V1의 재확인이 없어, V1이 재확인으로 되살린 가격·공고 핵심이 V2에서 검수로 감
  (bmc-106·sh-310976 가격 게시 −13씩, sh-310672 공고 전체 검수)

AGENTS(담당 이름 → 실행 함수)에 꽂으면 그것을 씁니다(시험). 꽂힌 것이 없으면 구조는 V1 방식, 나머지는 섹션 에이전트(v2/agents/section.py).
"""

from __future__ import annotations

import dataclasses
import operator
import time
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime as GraphRuntime
from langgraph.types import Send

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.extract import ExtractionRun
from mujuthaek_extraction.method import extraction_method
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, structure_summary
from mujuthaek_extraction.v2.document import DocumentModel
from mujuthaek_extraction.v2.document import build as build_document

STRUCTURE = "structure"
SLEEP: Callable[[float], None] = time.sleep  # 시험에서 바꿔 끼움


class V2State(TypedDict, total=False):
    raw_event: dict[str, Any]
    method: str
    intake: Any  # V1 IntakeResult
    rules: FieldRules
    material: Any  # V1 ExtractionMaterial(그림 판독 글자 포함)
    context: Any  # V1 TrustedContext(그림 판독 뒤 문서 기록 — 판독 글을 붙인 원문의 해시)
    image_run: ExtractionRun | None
    structure_run: ExtractionRun | None  # 구조(V1 방식) 호출 기록
    structure_first_run: ExtractionRun | None  # 구조(V1 방식)가 대체 모델로 넘어갔을 때 처음 모델의 기록
    structure_model: str | None  # 구조(V1 방식)를 낸 모델 이름(대체로 넘어갔으면 그 모델)
    recheck_model: Any  # 구조 단계 재확인 모델(V1 extract_parts가 고른 것: 대체 모델로 넘어갔으면 그 모델)
    extracted: Any  # 채팅 모델이 없어 V1 방식으로 모든 섹션을 뽑은 결과(pipeline.Extracted). 있으면 담당 없이 마무리
    document: DocumentModel
    plan: dict[str, Any]
    structure: dict[str, Any] | None  # 구조가 낸 id·이름 요약(뒤 담당이 참조)
    worker: str  # Send로 넘기는 담당 이름
    order: int  # 담당이 출발하는 차례(0부터). 병렬 간격만큼 늦게 출발
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
    planned = planned_for(state["rules"])
    if _shared_structure(state, runtime.context):
        return {"plan": planned}  # 데우기는 구조가 열 의미 묻기 앞에 보냄
    from mujuthaek_extraction.v2.agents.section import prime  # 담당 공통 앞부분 캐시 데우기(LangChain)

    return {"plan": planned, "usage": prime({**state, "plan": planned}, runtime.context)}


def planned_for(rules: FieldRules) -> dict[str, Any]:
    """담당 목록과 담당들이 함께 쓰는 도구 섹션(구조 단계 섹션은 빼고). 구조 단계가 담당 앞부분을 쓸 때도 같은 도구 목록이어야 합니다."""
    named = workers(rules)
    return {"workers": list(named), "sections": [section for name, spec in named.items() if name != STRUCTURE for section in spec.sections]}


def structure(state: V2State, runtime: Context) -> dict[str, Any]:
    spec = workers(state["rules"])[STRUCTURE]
    if STRUCTURE in AGENTS:
        parts, usage, trace = _unpack(AGENTS[STRUCTURE](spec, state, runtime.context))
        return {"parts": parts, "usage": usage, "traces": trace, "structure": structure_summary(parts[0]) if parts else None}
    if getattr(runtime.context.models, "chat", None) is None:  # 담당을 돌릴 수 없는 실행: V1 방식으로 모든 섹션을 뽑고 담당 없이 마무리로
        extracted = pipeline.extract_parts(state["rules"], state["material"], runtime.context, source=state["intake"].raw.source_code)
        return {**_v1_state(extracted), "extracted": extracted}
    shared: dict[str, Any] = {}
    if _shared_structure(state, runtime.context):
        from mujuthaek_extraction.v2.agents.structure import run_structure  # 담당 앞부분으로 부르는 구조 단계(LangChain)

        shared = run_structure(spec, {**state, "plan": planned_for(state["rules"])}, runtime.context)
        if "parts" in shared:
            return shared
    only = dataclasses.replace(state["rules"], calls=(spec,), split_calls=(), large_text_chars=None)
    extracted = pipeline.extract_parts(only, state["material"], runtime.context, source=state["intake"].raw.source_code)
    fallback = {"usage": shared.get("usage") or [], "traces": shared.get("traces") or []}  # 담당 앞부분으로 받지 못한 시도의 기록
    return {**_v1_state(extracted), **fallback}


def _v1_state(extracted: pipeline.Extracted) -> dict[str, Any]:
    """V1 방식 추출 결과 → 그래프 상태(조각·구조 요약·호출 기록·재확인 모델)."""
    run = extracted.run
    summary = run.structure or (structure_summary(run.parts[0]) if run.parts else None)
    return {
        "parts": list(run.parts),
        "structure": summary,
        "structure_run": run,
        "structure_first_run": extracted.first_run,
        "structure_model": extracted.model_used,
        "recheck_model": extracted.recheck_model,
    }


def _shared_structure(state: V2State, rt: pipeline.Runtime) -> bool:
    """구조 단계를 담당 앞부분으로 부르는지(꽂은 구조 담당이 없을 때만). 계획 노드와 구조 노드가 같은 답을 내야 데우기를 한 번만 보냅니다."""
    from mujuthaek_extraction.v2.agents.structure import shares

    return STRUCTURE not in AGENTS and shares(state, rt)


def dispatch(state: V2State, runtime: Context) -> dict[str, Any]:
    """계획(캐시 데우기)과 구조가 모두 끝나기를 기다리는 자리. 담당은 구조 id와 데운 캐시를 함께 씁니다."""
    return {}


def fan_out(state: V2State) -> list[Send] | str:
    if state.get("extracted") is not None:
        return "conclude"  # 구조 노드가 V1 방식으로 모든 섹션을 뽑음(채팅 모델 없음)
    if not state.get("structure"):
        # 구조 단계가 실패하면(구조 요약이 없거나 실패 조각뿐) 결과가 어차피 FAILED라 담당을 보내지 않아요(V1과 같음: 「구조 호출이
        # 실패해 실행하지 않았습니다」). 예전엔 담당을 모두 돌려, 다시 처리할 때마다 공고 예산을 다 썼어요(2026-11-10 코드 검토)
        return "conclude"
    names = [name for name in state["plan"]["workers"] if name != STRUCTURE]
    return [
        Send("section", {**state, "worker": name, "order": order, "parts": state.get("parts") or [], "usage": [], "traces": []})
        for order, name in enumerate(names)
    ]


def section(state: V2State, runtime: Context) -> dict[str, Any]:
    # 담당들이 한꺼번에 첫 호출을 보내면 하나는 데워 둔 캐시를 읽지 못합니다(V1 섹션 호출과 같은 현상, extract.py 병렬 간격).
    # 그래서 V1과 같은 간격(설정 EXTRACTION_PARALLEL_STAGGER_SECONDS)을 두고 차례로 출발합니다. 응답은 기다리지 않습니다
    SLEEP(state.get("order", 0) * runtime.context.parallel_stagger)
    spec = workers(state["rules"])[state["worker"]]
    agent = AGENTS.get(spec.name)
    if agent is None:
        from mujuthaek_extraction.v2.agents.section import run_section  # 섹션 담당 에이전트(LangChain)

        agent = run_section
    # 동시 호출 수(EXTRACTION_PARALLEL_CALLS)는 담당 노드가 아니라 모델 호출마다 지켜요(pipeline.Runtime.gate). 노드에서도 잡으면 담당 안의
    # 호출이 같은 세마포어를 기다려 1일 때 멈춰요
    parts, usage, trace = _unpack(agent(spec, state, runtime.context))
    return {"parts": parts, "usage": usage, "traces": trace}


def conclude(state: V2State, runtime: Context) -> dict[str, Any]:
    rt = runtime.context
    material, context = state["material"], state["context"]
    extracted = state.get("extracted")
    scope: tuple[str, ...] | None = None  # V1 방식으로 모든 섹션을 뽑았으면 V1처럼 모든 섹션을 재확인
    if extracted is None:
        base = state.get("structure_run") or ExtractionRun()
        run = ExtractionRun(
            parts=list(state.get("parts") or []),
            attempts=list(base.attempts),
            failed_calls=list(base.failed_calls),
            raw_responses=list(base.raw_responses),
            structure=state.get("structure"),
        )
        # 담당(채팅 모델)이 돌았으면 유료 모델, 아니면 구조를 낸 모델로 적어요. 구조가 대체 모델로 넘어갔으면 처음 모델의 기록도 남겨요.
        # 예전엔 늘 primary(로컬 AI 설정이면 「local」)로 적고 처음 모델의 시도를 버려 작업 기록이 틀렸어요(2026-11-10 코드 검토)
        names = rt.models.names
        paid = names.get("fallback") or names.get("primary", "primary")
        model = paid if state.get("usage") else state.get("structure_model") or names.get("primary", "primary")
        recheck = state.get("recheck_model") or rt.models.primary
        extracted = pipeline.Extracted(run, state.get("structure_first_run"), model, recheck)
        rt.usage.record("v2", {"calls": state.get("usage") or [], "workers": state["plan"]["workers"], "traces": state.get("traces") or []})
        scope = workers(state["rules"])[STRUCTURE].sections
    report = pipeline.first_report(extracted, material, context, rt)
    if report is None:
        return {"outcome": pipeline.extraction_failed_outcome(extracted, state.get("image_run"), material, rt)}
    recheck, repairs = pipeline.recheck_step(state["rules"], material, context, extracted, report, rt, scope=scope)
    report = recheck.report
    actions: list[str] = []
    if report.contract_errors:
        report, actions = pipeline.quarantine_step(report, recheck, material, context, rt)
        repairs += actions
    pipeline.note_changes(report, extracted, recheck, actions)  # 재확인·계약 정리로 처음 값이 사라진 칸은 메모(V1 annotate와 같음)
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
    graph.add_conditional_edges("dispatch", fan_out, ["section", "conclude"])
    graph.add_edge("section", "conclude")
    graph.add_edge("conclude", END)
    return graph.compile()


V2_GRAPH = build()


def run_graph(raw_event: dict[str, Any], rt: pipeline.Runtime, method: str | None = None) -> pipeline.Outcome:
    """공고 1건을 그래프로 처리합니다(pipeline.process가 부름). method가 없으면 설정 EXTRACTION_METHOD."""
    return V2_GRAPH.invoke({"raw_event": raw_event, "method": method or extraction_method()}, context=rt)["outcome"]
