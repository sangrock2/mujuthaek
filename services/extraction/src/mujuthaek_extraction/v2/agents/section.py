"""섹션 담당 에이전트(LangChain create_agent): 원문 차례를 보고 맡은 섹션 부분만 읽어 항목을 도구로 넣고, 검증기로 확인한 뒤 끝냅니다.

담당 하나 = V1 섹션 호출 하나(구조·일정·자격·선정·서류). 결과는 V1 AI 조각이라 결합·검증·게시는 V1 코드가 그대로 합니다.
모든 담당이 같은 지시·같은 도구를 써서 같은 공고 안에서 앞부분이 프롬프트 캐시를 함께 탑니다(담당마다 다른 할 일은 첫 메시지로).
"""

from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import HumanMessage

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.rules.base import CallSpec, document_ids
from mujuthaek_extraction.v2.agents.prompt import system_prompt
from mujuthaek_extraction.v2.contract import to_part
from mujuthaek_extraction.v2.document import DocumentModel
from mujuthaek_extraction.v2.llm.budget import BudgetExceeded, BudgetMiddleware
from mujuthaek_extraction.v2.tools.read import READ_TOOLS
from mujuthaek_extraction.v2.tools.write import WRITE_TOOLS, SectionContext, SectionDraft

MAX_MODEL_CALLS = 10  # 담당 하나의 모델 호출(차례) 상한
TOOLS = (*READ_TOOLS, *WRITE_TOOLS)


def run_section(spec: CallSpec, state: Any, rt: pipeline.Runtime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """담당 하나를 돌려 (V1 AI 조각들, 모델 호출 기록)을 돌려줍니다. 채팅 모델이 없는 실행(로컬 AI·녹화)이면 아무것도 하지 않습니다."""
    chat = getattr(rt.models, "chat", None)
    if chat is None:
        return [], []
    document: DocumentModel = state["document"]
    documents = tuple(document_ids(state["material"]))
    draft = SectionDraft(spec.sections)
    context = SectionContext(document=document, budget=rt.models.budget, draft=draft, documents=documents)
    context.check = lambda: _issues(spec, draft, state, rt, documents)
    agent = create_agent(
        chat(spec.name),
        tools=list(TOOLS),
        system_prompt=system_prompt(state["rules"]),
        middleware=[BudgetMiddleware(spec.name), ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end")],
        context_schema=SectionContext,
        name=spec.name,
    )
    try:
        agent.invoke({"messages": [HumanMessage(task(spec, state))]}, context=context)
    except BudgetExceeded as error:
        context.usage.append({"agent": spec.name, "stopped": str(error)})
    return parts_of(spec, draft, document, documents), context.usage


def task(spec: CallSpec, state: Any) -> str:
    lines = [f"# 이번 담당: {spec.name}", f"맡은 섹션: {', '.join(spec.sections)}", spec.instructions]
    if state.get("structure"):
        lines += ["# 구조 요약(위치·공급 id. 다른 섹션이 가리킬 때 이 id만 씀)", json.dumps(state["structure"], ensure_ascii=False)]
    lines += ["# 원문 차례(제목 줄·표·그림 쪽)", json.dumps(state["document"].outline(), ensure_ascii=False)]
    return "\n".join(lines)


def parts_of(spec: CallSpec, draft: SectionDraft, document: DocumentModel, documents: tuple[str, ...]) -> list[dict[str, Any]]:
    parts = []
    for section in spec.sections:
        items = draft.items.get(section, [])
        coverage = draft.coverage.get(section) or (
            {"status": "EXTRACTED", "reason": None} if items else {"status": "FAILED", "reason": "담당이 항목을 넣지 못했어요."}
        )
        parts.append(to_part(section, items, document, documents, coverage, draft.missing_for(section)))
    return parts


def _issues(spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...]) -> list[dict[str, Any]]:
    """앞 담당들의 조각 + 지금 초안을 V1 결합·검증에 넣어 이 담당 섹션의 문제만."""
    parts = [*(state.get("parts") or []), *parts_of(spec, draft, state["document"], documents)]
    report = pipeline.evaluate_parts(parts, state["material"], state["intake"].context, rt)
    if report is None:
        return [{"code": "NOT_ASSEMBLED", "target": "/notice", "description": "공고 기본 정보(notice)가 없어 결합하지 못했어요."}]
    mine = [i for i in report.candidate["quality"]["reviewIssues"] if any(_belongs(i["target"], s) for s in spec.sections)]
    return [{"code": i["code"], "target": i["target"], "description": i["description"][:220]} for i in mine]


def _belongs(target: str, section: str) -> bool:
    return target == f"/{section}" or target.startswith(f"/{section}/") or target.endswith(f"/coverage/{section}")
