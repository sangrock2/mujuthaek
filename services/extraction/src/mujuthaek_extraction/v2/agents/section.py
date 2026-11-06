"""섹션 담당 에이전트(LangChain create_agent): 원문 전체를 보고 맡은 섹션 항목을 섹션별 형식 도구로 넣고, 검증 미들웨어가 알려 주는
문제를 고친 뒤 끝냅니다(「넣기 → 고치기 → 끝」 3차례 안팎).

담당 하나 = V1 섹션 호출 하나(일정·자격·선정·서류). 결과는 V1 AI 조각이라 결합·검증·게시는 V1 코드가 그대로 합니다.
프롬프트 캐시: 같은 공고의 담당들은 지시·도구 목록·첫 메시지(원문 전체)가 같아 앞부분을 함께 씁니다. 담당마다 다른 할 일은 둘째 메시지.
담당들이 동시에 처음 보내면 저마다 앞부분을 캐시에 올려 쓰기 값을 담당 수만큼 내므로, 그래프가 담당을 띄우기 전에 prime이 한 번 올립니다.
담당의 대화(도구 호출·결과 앞부분)와 마지막 초안은 작업 기록에 남깁니다(실행을 다시 사지 않고 무엇을 넣었는지 확인).

2026-11-06 두 번째 실제 실행: 원문 차례만 주고 골라 읽게 했더니 담당당 9.3차례(12개 중 7개가 상한 10번에 걸림), 입력 토큰이 V1의 10배,
항목은 V1보다 적었음(서류 50 vs 75 등) → 원문 전체를 주고 읽기 도구를 없앰.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, document_ids
from mujuthaek_extraction.v2.agents.prompt import system_prompt
from mujuthaek_extraction.v2.agents.verify import VerifyMiddleware
from mujuthaek_extraction.v2.contract import to_part
from mujuthaek_extraction.v2.document import DocumentModel
from mujuthaek_extraction.v2.llm.budget import BudgetExceeded, BudgetMiddleware
from mujuthaek_extraction.v2.tools.typed import shared_tools
from mujuthaek_extraction.v2.tools.write import WRITE_TOOLS, SectionContext, SectionDraft
from mujuthaek_extraction.verify.verifier import DROPPED_VALUE_CODES, NOTE_CODES

MAX_MODEL_CALLS = 8  # 담당 하나의 모델 호출(차례) 상한: 넣기·고치기·끝 + 여유(2026-11-06 세 번째 실행: 6이면 서류 75개 공고가 넣다가 걸림)
TRACE_CHARS = 400  # 대화 기록에 남길 도구 인자·결과 앞부분
PRIME = "prime"
PRIME_TASK = "# 준비 호출\n담당들이 같은 앞부분(지시·도구·원문)을 다시 읽도록 캐시에 올리는 호출입니다. 도구를 부르지 말고 「준비」라고만 답합니다."
PRIME_OUTPUT_TOKENS = 512
# 메모로 내려가도 담당에게 알리는 것: 값이 빠지거나 근거 위치를 못 정함(그림 판독 표시·전환 부호 고침처럼 담당이 고칠 수 없는 것은 뺌)
LOST_VALUE_NOTES = (NOTE_CODES | DROPPED_VALUE_CODES) - {"IMAGE_TRANSCRIBED_VALUES", "CONVERSION_DIRECTION_CORRECTED"}


def run_section(spec: CallSpec, state: Any, rt: pipeline.Runtime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """담당 하나를 돌려 (V1 AI 조각들, 모델 호출 기록, 대화 기록)을 돌려줍니다. 채팅 모델이 없는 실행(로컬 AI·녹화)이면 아무것도 하지 않습니다."""
    chat = getattr(rt.models, "chat", None)
    if chat is None:
        return [], [], {}
    document: DocumentModel = state["document"]
    documents = tuple(document_ids(state["material"]))
    draft = SectionDraft(spec.sections)
    context = SectionContext(document=document, budget=rt.models.budget, draft=draft, documents=documents)
    context.check = lambda: _issues(spec, draft, state, rt, documents)
    limit = ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end")
    model = chat(spec.name, max_output_tokens=spec.max_output_tokens)  # V1 섹션 호출과 같은 출력 한도(첫 차례에 다 넣음)
    agent = _agent(model, spec.name, state, documents, [limit, VerifyMiddleware()])
    last: dict[str, Any] = {}
    stopped = None
    try:
        for snapshot in agent.stream({"messages": [shared_message(document), HumanMessage(task(spec, state))]}, context=context, stream_mode="values"):
            last = snapshot  # 예산 상한으로 멈춰도 그때까지의 대화를 기록하려고 마지막 상태를 둠
    except BudgetExceeded as error:
        stopped = str(error)
        context.usage.append({"agent": spec.name, "stopped": stopped})
    trace = {
        "agent": spec.name,
        "turns": _trace(last.get("messages") or []),
        "stopped": stopped,
        "draft": {"items": draft.items, "coverage": draft.coverage, "missing": draft.missing},
    }
    return parts_of(spec, draft, document, documents), context.usage, trace


def prime(state: Any, rt: pipeline.Runtime) -> list[dict[str, Any]]:
    """담당들의 같은 앞부분(지시·도구·원문)을 한 번 캐시에 올립니다. 짧게 답하는 호출 하나라 쓰기 값 한 번과 출력 몇 토큰만 듭니다.
    실패해도 담당은 그대로 돕니다(캐시만 못 씀)."""
    chat = getattr(rt.models, "chat", None)
    if chat is None:
        return []
    document: DocumentModel = state["document"]
    documents = tuple(document_ids(state["material"]))
    context = SectionContext(document=document, budget=rt.models.budget, documents=documents)
    model = chat(PRIME, max_output_tokens=PRIME_OUTPUT_TOKENS)  # 추론 강도도 담당과 같게(다르면 앞부분이 도구 정의 다음부터 달라짐)
    agent = _agent(model, PRIME, state, documents, [ModelCallLimitMiddleware(run_limit=1, exit_behavior="end")])
    try:
        agent.invoke({"messages": [shared_message(document), HumanMessage(PRIME_TASK)]}, context=context)
    except Exception as error:  # 캐시 데우기는 할 수 있는 만큼만: 실패를 기록하고 넘어감
        context.usage.append({"agent": PRIME, "stopped": f"{type(error).__name__}: {error}"[:300]})
    return context.usage


def shared_message(document: DocumentModel) -> HumanMessage:
    """모든 담당의 첫 메시지(원문 전체). 글자가 같아야 앞부분 캐시를 같이 씁니다."""
    return HumanMessage(f"# 원문(조각마다 id. 근거는 이 id로 가리킵니다)\n{document.render()}")


def task(spec: CallSpec, state: Any) -> str:
    lines = [f"# 이번 담당: {spec.name}", f"맡은 섹션: {', '.join(spec.sections)}", spec.instructions]
    if state.get("structure"):
        lines += ["# 구조 요약(위치·공급 id. 다른 섹션이 가리킬 때 이 id만 씀)", json.dumps(state["structure"], ensure_ascii=False)]
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


def _agent(model: Any, name: str, state: Any, documents: tuple[str, ...], middleware: list[AgentMiddleware]) -> Any:
    rules: FieldRules = state["rules"]
    return create_agent(
        model,
        tools=[*shared_tools(tuple(state["plan"]["sections"]), documents), *WRITE_TOOLS],
        system_prompt=system_prompt(rules),
        middleware=[BudgetMiddleware(name), *middleware],
        context_schema=SectionContext,
        name=name,
    )


def _issues(spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...]) -> list[dict[str, Any]]:
    """구조 조각 + 지금 초안을 V1 결합·검증에 넣어 이 담당 섹션의 문제만. 결합기가 형식이 틀려 버리는 것(항목·응답 전체)은
    결합기와 같은 형식 검사로 먼저 알립니다(검토 이슈에는 「범위 미완료」로만 남아 이유가 안 보임).
    판정 섹션 밖(일정·선정·서류 등)의 근거 문제는 검증기가 검토 이슈가 아닌 메모로 내리고 그 항목을 뺍니다(verifier.NOTE_CODES).
    그 메모도 알립니다(2026-11-06 세 번째 실제 실행: 결합기가 가점 5행을 「근거를 확인하지 못한 항목」으로 뺐는데 담당은 「문제 없음」을 받음)."""
    mine = parts_of(spec, draft, state["document"], documents)
    found = _format_problems(mine, draft)
    report = pipeline.evaluate_parts([*(state.get("parts") or []), *mine], state["material"], state["context"], rt)
    if report is None:
        return [*found, {"code": "NOT_ASSEMBLED", "target": "/notice", "description": "공고 기본 정보(notice)가 없어 결합하지 못했어요."}]
    candidate = report.candidate
    quality = candidate["quality"]
    notes = [n for n in quality.get("notes") or [] if isinstance(n, dict) and n.get("code") in LOST_VALUE_NOTES]
    for issue in [*quality["reviewIssues"], *notes]:
        if any(_belongs(issue["target"], section) for section in spec.sections):
            found.append({"code": issue["code"], "target": issue["target"], **_item_of(candidate, issue["target"]), "description": issue["description"][:220]})
    return found


def _format_problems(parts: list[dict[str, Any]], draft: SectionDraft) -> list[dict[str, Any]]:
    found = []
    for part in parts:
        for error in _validator().iter_errors(part):
            path = list(error.absolute_path)
            entry: dict[str, Any] = {"code": "FORMAT_INVALID", "target": "/" + "/".join(str(p) for p in path)}
            if len(path) >= 2 and isinstance(path[1], int) and path[0] in draft.items and path[1] < len(draft.items[path[0]]):
                entry["item"] = draft.items[path[0]][path[1]].get("id")
            entry["description"] = f"결합기가 이 형식 오류로 {'응답 전체를' if path[:1] in ([], ['quotes']) else '이 항목을'} 버립니다: {error.message[:200]}"
            found.append(entry)
    return found


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(ai_output.schema(), format_checker=FormatChecker())  # 결합기(assembler.merge)와 같은 검사


def _item_of(candidate: dict[str, Any], target: str) -> dict[str, Any]:
    """「/selectionRules/3/rule」 → 그 항목의 id(담당이 넣을 때 쓴 id로 고칠 항목을 찾게)."""
    tokens = target.strip("/").split("/")
    if len(tokens) >= 2 and tokens[1].isdigit():
        rows = candidate.get(tokens[0])
        if isinstance(rows, list) and int(tokens[1]) < len(rows) and isinstance(rows[int(tokens[1])], dict) and rows[int(tokens[1])].get("id"):
            return {"item": rows[int(tokens[1])]["id"]}
    return {}


def _belongs(target: str, section: str) -> bool:
    return target == f"/{section}" or target.startswith(f"/{section}/") or target.endswith(f"/coverage/{section}")


def _trace(messages: list[Any]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, AIMessage):
            calls = [{"name": c["name"], "args": json.dumps(c.get("args", {}), ensure_ascii=False)[:TRACE_CHARS]} for c in message.tool_calls]
            text = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
            turns.append({"calls": calls, "text": text[:200], "results": []})
        elif isinstance(message, ToolMessage) and turns:
            content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
            turns[-1]["results"].append({"name": message.name, "result": content[:TRACE_CHARS]})
        elif isinstance(message, HumanMessage) and turns:  # 검증 미들웨어가 넣은 검증 결과
            turns[-1]["verify"] = str(message.content)[: TRACE_CHARS * 2]
    return turns
