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

import copy
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

import openai
from jsonschema import Draft202012Validator, FormatChecker
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphBubbleUp

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, document_ids
from mujuthaek_extraction.v2.agents.cut import CutCallMiddleware, cut_off
from mujuthaek_extraction.v2.agents.prompt import system_prompt
from mujuthaek_extraction.v2.agents.verify import VerifyMiddleware, issue_key
from mujuthaek_extraction.v2.contract import to_part
from mujuthaek_extraction.v2.criteria import Chunk, criteria_chunks
from mujuthaek_extraction.v2.document import DocumentModel
from mujuthaek_extraction.v2.llm.budget import BudgetExceeded, BudgetMiddleware
from mujuthaek_extraction.v2.llm.retry import retry_middleware
from mujuthaek_extraction.v2.tools.typed import shared_tools
from mujuthaek_extraction.v2.tools.write import WRITE_TOOLS, SectionContext, SectionDraft
from mujuthaek_extraction.verify.consistency import CRITERIA_OMISSION, criteria_omission_description, missed_criteria_rows
from mujuthaek_extraction.verify.verifier import DROPPED_VALUE_CODES, NOTE_CODES

log = logging.getLogger(__name__)

MAX_MODEL_CALLS = 8  # 담당 하나의 모델 호출(차례) 상한: 넣기·고치기·끝 + 여유(2026-11-06 세 번째 실행: 6이면 서류 75개 공고가 넣다가 걸림)
# 담당별 상한. 자격은 기준표 행을 예외로 넣고 고치는 차례가 더 듦(2026-11-07 유료 확인 dudc-8934: 8번째 호출에서 항목 13개를 남기고 끊김).
# 저장된 유료 기록 282번 중 상한에 끊긴 담당은 자격뿐이었고, 늘린 두 호출은 앞부분을 캐시로 읽어 한 번에 약 $0.002~0.005.
# 10 → 12(2026-11-09 23건 유료 측정·jbdc-16011 확인: 자격 담당 셋이 10번에 끊겨 자격 섹션 전체가 검수로 감 — 대상 전체 누락을 대상별 조건으로
# 다시 넣다가 끊기고, 근거 위치·형식 거절에 2~4차례를 씀. 거절은 쓰기 도구가 줄이고 남는 끊김에 두 차례를 더 둠)
MODEL_CALLS = {"eligibility": 12}
# 호출 상한 미들웨어(ModelCallLimitMiddleware, exit_behavior="end")가 상한에서 대화를 끝내며 붙이는 답의 머리
CALL_LIMIT_MESSAGE = "Model call limits exceeded"
TRACE_CHARS = 400  # 대화 기록에 남길 도구 인자·결과 앞부분
# 대화 기록에 남길 검증 결과 길이. 앞 800자만 남기면 담당이 어떤 경고를 받고 끝냈는지 알 수 없었음(2026-11-07 유료 확인 jbdc-16011:
# 기준표 메모를 몇 번째 차례에 받았는지 모름). 경고 20개(설명 220자씩)·안내·고치는 법이 다 들어가는 길이
VERIFY_TRACE_CHARS = 8000
DESCRIPTION_CHARS = 220  # 담당에게 보내는 문제 설명 길이
# 섹션 전체 문제(빠진 대상·서류 표 행 등)는 섹션마다 하나라 길게: 빠진 행을 3개까지 적는 설명이 220자에서 잘려 셋째 행이 보이지 않았음
# (2026-11-08 최종 비교 bmc-106: 「원문 자격 기준표에서 조건이 하나도 없는 대상」의 기준값 행 인용이 중간에 끊김)
SECTION_DESCRIPTION_CHARS = 400
PRIME = "prime"
PRIME_OUTPUT_TOKENS = 512
# 메모로 내려가도 담당에게 알리는 것: 값이 빠지거나 근거를 찾지 못함·빠진 항목 의심. 위치는 정했고 값도 남는 메모(근거가 짧거나 여러 곳)와
# 담당이 고칠 수 없는 표시(그림 판독·전환 부호 고침)는 뺌(2026-11-06 네 번째 실행: 세로 글자 표 칸 「청」·「계」 짧은 인용 13개를 세 차례 내내 받음)
NOT_ADDED = "ITEM_NOT_ADDED"  # 넣을 때 거절되어 아직 초안에 없는 항목(검증 미들웨어의 「고칠 것」)
# 해결 에이전트(4단계): 담당이 끝낸 뒤 판단 경고가 남은 항목만 새 대화로 다시 봄. 기본 켬(false로 끔, 2026-11-08 사용자 결정)
RESOLVER = "resolver"
RESOLVER_ENV = "EXTRACTION_V2_RESOLVER"
RESOLVER_CODES = ("CRITERION_NOT_STRUCTURED", "EXCEPTION_SUSPECTED", "CONTRACT_")
RESOLVER_CALLS = 4
# 한꺼번에 도는 해결 담당 수와 출력 한도. 예산은 호출마다 최악 비용(입력 전부·출력 한도 전부)을 미리 잡으므로, 경고 항목을 모두 동시에
# 자격 출력 한도(3.6만)로 부르면 잡아 둔 금액이 공고 상한에 닿음(2026-11-08 유료 확인 dudc-8934: 12개 중 10개가 시작도 못 함, 아직
# 돌던 다른 담당도 막을 수 있음). 항목 하나 고치기 출력은 저장 기록 14번 중 최대 1.12만(dudc 표 행 예외), 보통 2천 아래
RESOLVER_WORKERS = 3
RESOLVER_OUTPUT_TOKENS = 16_000
# 해결 담당 대화 수 상한(담당 하나): 같은 경고 묶음마다 대화 하나, RESOLVER_WORKERS개씩 두 차례. 2026-11-10 유료 확인 jbdc-16011: 경고 항목
# 21·12개를 항목마다 따로 봐 51·25호출($0.136·$0.058, 그 공고 V2 비용의 73%·58%), 채택은 각 1개. 보관된 실행 7개 합계 55항목 중 5개 채택
RESOLVER_RUNS = 6
RESOLVER_GROUP_ITEMS = 20  # 경고 묶음 하나에 담는 항목 수 상한(대화 하나의 출력이 한도 안에 들게)
# 예외 의심 경고(verify/exceptions._suspect)가 가리키는 원문 값: 「기준값 바로 뒤에 다른 기준값(110%, 150%)이 있는데 …」. 기준값마다 글은 다르지만
# 같은 원문 값을 가리키면 같은 경고입니다(2026-11-10 jbdc-16011 두 회차를 다시 결합: 해결 담당이 받는 경고 21·12개 → 묶음 4·4개)
WARNED_VALUES = re.compile(r"다른 기준값\(([^)]*)\)")
# 기준표 담당(자격 담당을 시작하기 전): 큰 자격 기준표(v2/criteria.py)의 행 묶음마다 새 대화가 그 행의 기준만 넣고, 넣은 항목을 자격 담당
# 초안에 합칩니다. 2026-11-10 유료 확인 jbdc-16011: 공급유형×공급방식×맞벌이 소득표 32행을 자격 담당 혼자 넣으며 회차마다 27값·15값만 넣음
TABLE = "criteria_table"
TABLE_ENV = "EXTRACTION_V2_CRITERIA_TABLES"
TABLE_CALLS = 6
TABLE_WORKERS = 3
TABLE_OUTPUT_TOKENS = 16_000
LOST_VALUE_NOTES = (NOTE_CODES | DROPPED_VALUE_CODES) - {
    "IMAGE_TRANSCRIBED_VALUES",
    "CONVERSION_DIRECTION_CORRECTED",
    "AMOUNT_READ_BY_PARTS",
    "EVIDENCE_AMBIGUOUS",
    "EVIDENCE_QUOTE_TOO_SHORT",
}


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
    tables = _tables(spec, draft, state, rt, documents, chat, context.usage) if "eligibility" in spec.sections and tables_on() else []
    calls = MODEL_CALLS.get(spec.name, MAX_MODEL_CALLS)
    limit = ModelCallLimitMiddleware(run_limit=calls, exit_behavior="end")
    model = chat(spec.name, max_output_tokens=spec.max_output_tokens)  # V1 섹션 호출과 같은 출력 한도(첫 차례에 다 넣음)
    verify = VerifyMiddleware(calls)
    if draft.version:
        # 기준표 담당이 넣은 항목: 담당의 첫 차례 전에는 알리지 않되 검증은 미리 해 둠. 그래야 첫 차례가 끝내기뿐이어도 그 결과로 거둠
        # (검증 없이 끝나면 본문 자격 기준이 빠진 채 기준표 항목만으로 다 넣음이 됨)
        verify.seen, verify.issues = draft.version, context.check()
    agent = _agent(model, spec.name, state, documents, [limit, verify, CutCallMiddleware()])
    last: dict[str, Any] = {}
    stopped = None
    try:
        opening = [shared_message(document), HumanMessage(task(spec, state, tables))]
        for snapshot in agent.stream({"messages": opening}, context=context, stream_mode="values"):
            last = snapshot  # 예산 상한으로 멈춰도 그때까지의 대화를 기록하려고 마지막 상태를 둠
    except BudgetExceeded as error:
        stopped = str(error)
        context.usage.append({"agent": spec.name, "stopped": stopped})
    except (openai.APIError, TimeoutError, ConnectionError) as error:
        # 재시도로도 안 된 모델 호출 오류: 그때까지 넣은 항목만 남기고 이 담당 섹션만 사람 확인으로(공고·다른 담당은 계속)
        # 2026-11-06 23건 측정: 담당 하나의 시간 초과가 그래프·공고·측정 전체를 멈춤
        stopped = f"{type(error).__name__}: {error}"[:300]
        context.usage.append({"agent": spec.name, "stopped": stopped})
        log.warning("섹션 담당이 모델 호출 오류로 멈췄습니다", extra={"agent": spec.name, "error": stopped})
    except Exception as error:  # 그 밖의 예상 못 한 오류도 이 담당만 멈춤(결함은 로그의 추적으로 찾음)
        stopped = f"{type(error).__name__}: {error}"[:300]
        context.usage.append({"agent": spec.name, "stopped": stopped})
        log.exception("섹션 담당이 예상 못 한 오류로 멈췄습니다", extra={"agent": spec.name})
    messages = last.get("messages") or []
    final = messages[-1] if messages and isinstance(messages[-1], AIMessage) else None
    if stopped is None and final is not None and not draft.finished:  # 마지막 호출에서 끝내기까지 불렀으면 상한에 닿았어도 끝낸 것
        if str(final.content).startswith(CALL_LIMIT_MESSAGE):
            stopped = f"모델 호출 상한({calls}번)"
        elif cut_off(final):  # 넣기가 아닌 호출·글이 잘려 실행할 호출 없이 끝남(넣기는 CutCallMiddleware가 살림)
            stopped = f"출력 한도({spec.max_output_tokens}토큰)에서 잘림"
        if stopped is not None:
            context.usage.append({"agent": spec.name, "stopped": stopped})
    if stopped is not None and not draft.finished:
        _mark_unfinished(draft, spec.sections, stopped)
    resolver: dict[str, Any] = {}
    if stopped is None and resolver_on():
        resolved, resolver = _resolve(spec, draft, state, rt, documents, chat, context.usage)
        draft = resolved or draft
    trace = {
        "agent": spec.name,
        "turns": _trace(last.get("messages") or []),
        "stopped": stopped,
        **({"tables": tables} if tables else {}),
        **({"resolver": resolver} if resolver else {}),
        "draft": {
            "items": draft.items,
            "coverage": draft.coverage,
            "missing": draft.missing,
            "finished": draft.finished,
            "rejected": {f"{section}/{item_id}": reasons for (section, item_id), reasons in draft.rejected.items()},
        },
    }
    return parts_of(spec, draft, document, documents), context.usage, trace


def _mark_unfinished(draft: SectionDraft, sections: tuple[str, ...], why: str) -> None:
    """끝내기 전에 멈춘 담당(호출 상한·예산·모델 오류)의 섹션: 넣은 항목은 두고 범위를 PARTIAL로 적어 섹션을 사람 확인으로 보냅니다.
    담당이 범위를 적지 않으면 항목이 있는 섹션은 「다 넣음(EXTRACTED)」이 되어, 넣던 중에 끊긴 항목이 빠진 채 게시됐습니다
    (2026-11-07 유료 확인 dudc-8934: 기준표 가산 행을 예외로 넣다 8번째 호출에서 끊겨 고령자 총자산·자동차 등 13개 항목이 빠짐).
    담당이 PARTIAL·FAILED로 직접 적었으면 그 이유를 두고, 항목이 없는 섹션은 parts_of가 FAILED로 적습니다."""
    for section in sections:
        if draft.items.get(section) and (draft.coverage.get(section) or {}).get("status") not in ("PARTIAL", "FAILED"):
            draft.coverage[section] = {"status": "PARTIAL", "reason": f"담당이 끝내기 전에 멈췄어요({why}). 넣지 못한 항목이 있을 수 있어요."}


def resolver_on() -> bool:
    """해결 담당을 쓸지: 기본 켬, EXTRACTION_V2_RESOLVER=false면 끔."""
    return os.getenv(RESOLVER_ENV, "true").strip().lower() != "false"


def tables_on() -> bool:
    """기준표 담당을 쓸지: 기본 켬, EXTRACTION_V2_CRITERIA_TABLES=false면 끔(자격 담당이 기준표까지 혼자 넣음)."""
    return os.getenv(TABLE_ENV, "true").strip().lower() != "false"


def _resolve(
    spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], chat: Any, usage: list[dict[str, Any]]
) -> tuple[SectionDraft | None, dict[str, Any]]:
    """해결 에이전트(4단계): 담당이 끝낸 초안에서 판단 경고가 남은 항목만, 앞선 대화 없이 같은 앞부분(지시·도구·원문)으로 다시 봅니다.
    고친 초안은 경고가 있던 항목만 바뀌고(빼지 않음) 검증 결과에 새 문제 없이 문제가 줄었을 때만 씁니다(_settled). 모델 호출은 usage에 더합니다.
    2026-11-07 23건 재조립: 남은 검토 이슈 106개 중 53개가 자격의 판단 경고(조건식 없음 31·예외 의심 22)였고, 정답표와 대조하면 대부분
    조건식으로 나타낼 수 있는 기준(「도시근로자 월평균소득 100% 이하」 등, 정답표의 놓친 값)을 담당이 경고를 받고도 첫 판단대로 글로 남긴 것.
    같은 경고(_warned_groups: 코드와 가리키는 원문 값)를 받은 항목들은 한 대화에서 봅니다. 2026-11-10 유료 확인 jbdc-16011: 항목마다 따로 본
    해결 담당 21개 중 채택은 「1인 120%·2인 110%」 예외를 넣은 하나였고, 그 하나로 같은 「110%」를 가리키던 다른 항목 13개의 경고도 풀림
    (해결 담당을 끄고 다시 결합하면 게시 −13). 같은 경고의 다른 13개 대화는 대부분 고치지 않고 끝남.
    묶음 대화를 RESOLVER_WORKERS개씩 동시에 돌리고(항목 3개를 한 대화에서 고쳐 112초가 더해졌던 2026-11-07 dcco-24812처럼 오래 걸리지 않게),
    차례마다 고른 결과(_settled)를 합친 뒤 다시 검증해 경고가 풀린 묶음은 보지 않습니다. 대화는 RESOLVER_RUNS개까지입니다."""
    first = before = _issues(spec, draft, state, rt, documents)
    groups = _warned_groups(before, set())
    if not groups:
        return None, {}
    targets = sum(len(issues) for _, issues in groups)
    current, adopted, tried = draft, False, set()
    runs: dict[str, dict[str, Any]] = {}
    while groups and len(runs) < RESOLVER_RUNS:
        wave = groups[: min(RESOLVER_WORKERS, RESOLVER_RUNS - len(runs))]
        tried |= {signature for signature, _ in wave}
        base, known = current, before

        def one(group: tuple[tuple[str, str], list[dict[str, Any]]]) -> tuple[SectionDraft | None, dict[str, Any], list[dict[str, Any]]]:
            return _resolve_group(spec, base, state, rt, documents, chat, group[1], known)  # noqa: B023 (차례 안에서만 부름)

        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            results = list(pool.map(one, wave))
        merged, taken = _copy(spec, base), []
        for (_, issues), (trial, run, calls) in zip(wave, results, strict=True):
            usage.extend(calls)
            items = list(dict.fromkeys(issue["item"] for issue in issues))
            runs[items[0] if items[0] not in runs else f"{items[0]}#{len(runs)}"] = {**run, "group": items}  # 다음 차례에 다시 든 항목
            if trial is not None and _take(merged, trial, set(items), base):
                taken += items
        after = _issues(spec, merged, state, rt, documents) if taken else known
        if taken and _settled(base, merged, set(taken), known, after):
            current, before, adopted = merged, after, True
        groups = _warned_groups(before, tried)
    record = {"targets": targets, "before": len(first), "after": len(before), "adopted": adopted, "runs": len(runs), "items": runs}
    if groups:  # 대화 상한으로 보지 못한 경고 묶음(그 항목은 사람이 확인)
        record["left"] = [list(dict.fromkeys(issue["item"] for issue in issues)) for _, issues in groups]
    return (current if adopted else None), record


def _warned_groups(issues: list[dict[str, Any]], tried: set[tuple[str, str]]) -> list[tuple[tuple[str, str], list[dict[str, Any]]]]:
    """판단 경고가 남은 항목을 같은 경고끼리 묶습니다(이미 본 묶음은 뺌). 항목은 첫 경고의 묶음에 들고, 그 대화에는 항목의 경고를 모두 줍니다.
    큰 묶음부터 봅니다(여러 항목이 같은 원문 값을 가리키면 그 기준을 한 번 넣어 함께 풀리기도 함). 묶음마다 RESOLVER_GROUP_ITEMS개 항목까지."""
    warned = [issue for issue in issues if str(issue.get("code") or "").startswith(RESOLVER_CODES) and issue.get("item")]
    home: dict[str, tuple[str, str]] = {}
    for issue in warned:
        home.setdefault(issue["item"], _signature(issue))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for issue in warned:
        if home[issue["item"]] not in tried:
            groups.setdefault(home[issue["item"]], []).append(issue)
    found = []
    for signature, members in sorted(groups.items(), key=lambda pair: -len({issue["item"] for issue in pair[1]})):
        items = list(dict.fromkeys(issue["item"] for issue in members))[:RESOLVER_GROUP_ITEMS]
        found.append((signature, [issue for issue in members if issue["item"] in items]))
    return found


def _signature(issue: dict[str, Any]) -> tuple[str, str]:
    """같은 경고인지 가르는 열쇠: 코드와, 예외 의심이면 가리키는 원문 값(「110%, 150%」), 아니면 설명 그대로."""
    description = str(issue.get("description") or "")
    values = WARNED_VALUES.search(description)
    return str(issue.get("code")), values.group(1) if values else description


def _copy(spec: CallSpec, draft: SectionDraft) -> SectionDraft:
    return SectionDraft(spec.sections, items=copy.deepcopy(draft.items), coverage=copy.deepcopy(draft.coverage), missing=copy.deepcopy(draft.missing))


def _resolve_group(
    spec: CallSpec,
    draft: SectionDraft,
    state: Any,
    rt: pipeline.Runtime,
    documents: tuple[str, ...],
    chat: Any,
    targets: list[dict[str, Any]],
    before: list[dict[str, Any]],
) -> tuple[SectionDraft | None, dict[str, Any], list[dict[str, Any]]]:
    """같은 경고를 받은 항목들을 새 대화 하나로 봅니다. 그 항목들만 바뀌고 검증 결과에 새 문제 없이 문제가 줄었을 때만 고친 초안을 돌려줍니다."""
    trial = _copy(spec, draft)
    document: DocumentModel = state["document"]
    context = SectionContext(document=document, budget=rt.models.budget, draft=trial, documents=documents)
    context.check = lambda: _issues(spec, trial, state, rt, documents)
    limit = ModelCallLimitMiddleware(run_limit=RESOLVER_CALLS, exit_behavior="end")
    model = chat(RESOLVER, max_output_tokens=min(spec.max_output_tokens, RESOLVER_OUTPUT_TOKENS))
    agent = _agent(model, RESOLVER, state, documents, [limit, VerifyMiddleware(), CutCallMiddleware()])
    last: dict[str, Any] = {}
    stopped = None
    try:
        messages = [shared_message(document), HumanMessage(resolver_task(spec, trial, targets))]
        for snapshot in agent.stream({"messages": messages}, context=context, stream_mode="values"):
            last = snapshot
    except Exception as error:  # 해결 담당이 멈추면 그 항목들은 담당 초안 그대로
        stopped = f"{type(error).__name__}: {error}"[:300]
        log.warning("해결 담당이 멈췄습니다", extra={"agent": spec.name, "error": stopped})
    final = (last.get("messages") or [None])[-1]
    if stopped is None and cut_off(final) and not trial.finished:  # 고치다 잘려 끝남: 고친 것을 쓰지 않음
        stopped = f"출력 한도({min(spec.max_output_tokens, RESOLVER_OUTPUT_TOKENS)}토큰)에서 잘림"
    after = before if stopped else _issues(spec, trial, state, rt, documents)
    adopted = stopped is None and _settled(draft, trial, {issue["item"] for issue in targets}, before, after)
    record = {"targets": len(targets), "after": len(after), "adopted": adopted, "stopped": stopped, "turns": _trace(last.get("messages") or [])}
    return (trial if adopted else None), record, context.usage


def _take(merged: SectionDraft, trial: SectionDraft, items: set[str], draft: SectionDraft) -> bool:
    """고른 해결 담당 하나의 결과(맡은 항목들과 새로 넣은 항목)를 합친 초안에 옮깁니다.
    새 항목 id가 이미 있으면(다른 묶음의 해결 담당이 같은 id로 넣음) 이 결과는 옮기지 않습니다."""
    moves = []
    for section in merged.sections:
        known = {row.get("id") for row in draft.items.get(section, [])}
        present = {row.get("id") for row in merged.items.get(section, [])}
        for row in trial.items.get(section, []):
            if row.get("id") not in items and row.get("id") in known:
                continue
            if row.get("id") not in items and row.get("id") in present:
                return False
            moves.append((section, row))
    for section, row in moves:
        rows = merged.items.setdefault(section, [])
        at = next((i for i, old in enumerate(rows) if old.get("id") == row.get("id")), None)
        if at is None:
            rows.append(copy.deepcopy(row))
        else:
            rows[at] = copy.deepcopy(row)
    return True


def resolver_task(spec: CallSpec, draft: SectionDraft, targets: list[dict[str, Any]]) -> str:
    rows = {row.get("id"): row for section in draft.sections for row in draft.items.get(section, [])}
    lines = [
        f"# 해결 담당: {spec.name}",
        "섹션 담당이 끝낸 초안에 아래 경고가 남았습니다. 경고마다 원문을 다시 보고, 공통 지시(조건식 쓰는 법)대로 나타낼 수 있으면 고칩니다.",
        "- 기준값이 대상군·가구원 수·자녀 수에 따라 달라진다는 것만으로는 글로 남길 이유가 아닙니다.",
        "  기본 기준은 조건식, 달라지는 경우는 exceptions(REPLACE)로 넣고, 순위·계층마다 기준이 다르면 계층마다 조건을 따로 둡니다",
        "  (원래 항목은 update_item으로 고치고 나머지는 add_<섹션>으로).",
        "- 원문상 속성 사전으로 나타낼 수 없거나 이미 맞으면 그대로 둡니다. 경고를 없애려고 항목을 빼거나 원문에 없는 값을 넣지 않습니다.",
        "- 경고가 없는 항목·섹션 상태는 바꾸지 않습니다(바뀌면 고친 것을 쓰지 않음). 끝나면 finish를 부릅니다.",
        "## 경고가 남은 항목",
    ]
    warned_items = list(dict.fromkeys(issue["item"] for issue in targets))
    if len(warned_items) > 1:
        lines.insert(
            -1,
            f"- 아래 항목 {len(warned_items)}개는 같은 경고(같은 원문 값)를 받았습니다. 그 원문 기준이 실제로 적용되는 항목만 고치고, "
            "적용되지 않는 항목은 그대로 둡니다(모든 항목에 같은 예외를 넣지 않습니다).",
        )
    for item_id in warned_items:
        warned = [f"{issue['code']}: {issue['description']}" for issue in targets if issue["item"] == item_id]
        lines.append(json.dumps({"id": item_id, "경고": warned, "항목": rows.get(item_id)}, ensure_ascii=False))
    return "\n".join(lines)


def _settled(draft: SectionDraft, trial: SectionDraft, warned: set[str], before: list[dict[str, Any]], after: list[dict[str, Any]]) -> bool:
    """해결 담당의 초안을 쓸지: 경고가 있던 항목만 바뀌고(뺀 항목 없음, 새 항목은 됨) 섹션 상태가 그대로이며, 검증 결과에 새 문제가 없고 줄었을 때."""
    for section in draft.sections:
        old = {row.get("id"): row for row in draft.items.get(section, [])}
        new = {row.get("id"): row for row in trial.items.get(section, [])}
        if set(old) - set(new) or any(new[item_id] != row for item_id, row in old.items() if item_id not in warned):
            return False
    if trial.coverage != draft.coverage:
        return False
    return {issue_key(issue) for issue in after} <= {issue_key(issue) for issue in before} and len(after) < len(before)


def prime(state: Any, rt: pipeline.Runtime) -> list[dict[str, Any]]:
    """담당들의 같은 앞부분(지시·도구·원문)을 한 번 캐시에 올립니다. 요청은 원문 메시지에서 끝냅니다: OpenAI 캐시는 앞 요청이 끝난 곳까지를
    다시 쓰므로, 원문 뒤에 「준비」 같은 메시지를 더 붙이면 담당은 지시·도구까지만 캐시에서 읽음(2026-11-06 네 번째 실제 실행: 4.24만 중 3.21만).
    답은 버리고 도구도 실행하지 않습니다(출력 상한이 작아 몇백 토큰). 실패해도 담당은 그대로 돕니다(캐시만 못 씀).
    평가용 파일 저장소에 같은 요청의 답이 있어도 늘 보냅니다(cached=False): 저장된 답을 꺼내면 OpenAI에 원문에서 끝나는 요청이 없어, 맡은 일이
    서로 다른 담당·해결 담당은 지시·도구까지만 캐시에서 읽음(2026-11-08 다시 재기: 해결 담당 첫 호출 7번이 1.9만만 읽고 원문 4~9만 토큰을 다시 씀)."""
    chat = getattr(rt.models, "chat", None)
    if chat is None:
        return []
    document: DocumentModel = state["document"]
    documents = tuple(document_ids(state["material"]))
    context = SectionContext(document=document, budget=rt.models.budget, documents=documents)
    # 추론 강도도 담당과 같게(다르면 앞부분이 도구 정의 다음부터 달라짐)
    model = chat(PRIME, max_output_tokens=PRIME_OUTPUT_TOKENS, cached=False)
    agent = _agent(model, PRIME, state, documents, [StopAfterModel()])
    try:
        agent.invoke({"messages": [shared_message(document)]}, context=context)
    except Exception as error:  # 캐시 데우기는 할 수 있는 만큼만: 실패를 기록하고 넘어감
        context.usage.append({"agent": PRIME, "stopped": f"{type(error).__name__}: {error}"[:300]})
    return context.usage


class ToolErrorMiddleware(AgentMiddleware):
    """도구 실행 중 예상 못 한 오류를 그 도구 호출의 오류 답으로 돌려줍니다(담당은 계속 일하고 다음 차례에 고침).
    도구 실행기는 인자 형식 오류 말고는 오류를 그대로 올려 담당·공고 처리 전체가 멈춥니다(2026-11-06 23건 측정)."""

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as error:
            call = request.tool_call
            log.warning("도구 호출이 오류로 끝났습니다", extra={"tool": call.get("name"), "error": f"{type(error).__name__}: {error}"[:200]})
            content = json.dumps({"error": "TOOL_FAILED", "message": f"{type(error).__name__}: {error}"[:300]}, ensure_ascii=False)
            return ToolMessage(content=content, tool_call_id=call["id"], name=call.get("name"), status="error")


class StopAfterModel(AgentMiddleware):
    """모델 답을 받으면 도구를 실행하지 않고 끝냅니다(캐시 데우기)."""

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return {"jump_to": "end"}


def shared_message(document: DocumentModel) -> HumanMessage:
    """모든 담당의 첫 메시지(원문 전체). 글자가 같아야 앞부분 캐시를 같이 씁니다."""
    return HumanMessage(f"# 원문(조각마다 id. 근거는 이 id로 가리킵니다)\n{document.render()}")


def task(spec: CallSpec, state: Any, tables: list[dict[str, Any]] | tuple[()] = ()) -> str:
    lines = [f"# 이번 담당: {spec.name}", f"맡은 섹션: {', '.join(spec.sections)}", spec.instructions]
    if state.get("structure"):
        lines += ["# 구조 요약(위치·공급 id. 다른 섹션이 가리킬 때 이 id만 씀)", json.dumps(state["structure"], ensure_ascii=False)]
    if tables:
        lines.append(table_note(tables))
    return "\n".join(lines)


def _tables(
    spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], chat: Any, usage: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """기준표 담당: 큰 자격 기준표의 행 묶음(v2/criteria.py)마다 새 대화가 그 행의 기준만 넣고, 넣은 항목을 담당 초안에 합칩니다(id 앞에 표 id).
    묶음 TABLE_WORKERS개씩 동시에. 끝내지 못한 묶음(호출 상한·오류)도 넣은 항목은 합치고, 남은 행은 자격 담당 할 일 글로 알립니다(table_note).
    자격 담당과 같은 앞부분(지시·도구·원문)이라 캐시를 같이 읽습니다. 모델 호출은 usage에 더하고 묶음마다 기록을 돌려줍니다.
    기준표를 찾다 오류가 나면 기준표 담당 없이 자격 담당이 지금처럼 넣습니다(돕는 단계가 자격 추출을 멈추지 않게)."""
    try:
        chunks = criteria_chunks(state["document"])
    except Exception:
        log.exception("기준표를 나누지 못했습니다(기준표 담당 없이 진행)", extra={"agent": TABLE})
        return []
    if not chunks:
        return []
    with ThreadPoolExecutor(max_workers=min(len(chunks), TABLE_WORKERS)) as pool:
        runs = list(pool.map(lambda chunk: _run_table(spec, chunk, state, rt, documents, chat), chunks))
    records = []
    for chunk, (helper, record, calls) in zip(chunks, runs, strict=True):
        usage.extend(calls)
        merged, refused = _merge_table(draft, helper, chunk)
        record = {**record, "items": [item["id"] for item in merged], "brief": [_brief(item) for item in merged]}
        records.append({**record, "refused": refused} if refused else record)
    return records


def _run_table(
    spec: CallSpec, chunk: Chunk, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], chat: Any
) -> tuple[SectionDraft, dict[str, Any], list[dict[str, Any]]]:
    helper = SectionDraft(spec.sections)
    document: DocumentModel = state["document"]
    context = SectionContext(document=document, budget=rt.models.budget, draft=helper, documents=documents)
    context.check = lambda: _table_issues(spec, helper, state, rt, documents, chunk)
    limit = ModelCallLimitMiddleware(run_limit=TABLE_CALLS, exit_behavior="end")
    output = min(spec.max_output_tokens, TABLE_OUTPUT_TOKENS)
    last: dict[str, Any] = {}
    stopped = None
    try:
        model = chat(spec.name, max_output_tokens=output)  # 응답 대기 한도는 자격 담당과 같게
        agent = _agent(model, TABLE, state, documents, [limit, VerifyMiddleware(TABLE_CALLS), CutCallMiddleware()])
        for snapshot in agent.stream({"messages": [shared_message(document), HumanMessage(table_task(chunk))]}, context=context, stream_mode="values"):
            last = snapshot
    except Exception as error:  # 기준표 담당이 멈추면 넣은 항목만 남기고 남은 행은 자격 담당이 넣음
        stopped = f"{type(error).__name__}: {error}"[:300]
        log.warning("기준표 담당이 멈췄습니다", extra={"agent": TABLE, "error": stopped})
    final = (last.get("messages") or [None])[-1]
    if stopped is None and not helper.finished and isinstance(final, AIMessage):
        if str(final.content).startswith(CALL_LIMIT_MESSAGE):
            stopped = f"모델 호출 상한({TABLE_CALLS}번)"
        elif cut_off(final):
            stopped = f"출력 한도({output}토큰)에서 잘림"
    record = {"table": chunk.table, "rows": chunk.label, "groups": list(chunk.groups), "stopped": stopped, "turns": _trace(last.get("messages") or [])}
    # 담당이 끝냈어도 섹션을 PARTIAL·FAILED로 적었으면 맡은 행을 다 넣지 못한 것: 자격 담당에게 남은 행을 넘김(table_note)
    partial = [entry.get("reason") or entry.get("status") for entry in helper.coverage.values() if entry.get("status") in ("PARTIAL", "FAILED")]
    if partial:
        record["partial"] = "; ".join(str(reason) for reason in partial)
    return helper, record, context.usage


def _merge_table(draft: SectionDraft, helper: SectionDraft, chunk: Chunk) -> tuple[list[dict[str, Any]], list[str]]:
    """기준표 담당이 넣은 항목을 담당 초안에 옮기고 (옮긴 항목, 넣을 때 거절된 채 남은 항목 id)를 돌려줍니다. id는 표 id로 시작하게 하고
    (「t10-1-…」) 겹치면 뒤에 번호를 붙입니다. 누락 기록도 바뀐 id로 옮깁니다. 거절된 항목은 담당 초안의 「넣지 못한 항목」으로 옮겨
    자격 담당이 검증 결과에서 「고칠 것」으로 받게 합니다(옮기지 않으면 그 행이 알림 없이 빠짐)."""
    prefix = f"{chunk.table}-"
    renamed: dict[str, str] = {}
    merged: list[dict[str, Any]] = []
    refused: list[str] = []

    def new_id(section: str, old: str) -> str:
        base = old if old.startswith(prefix) else f"{prefix}{old}"
        item_id, number = base, 2
        while draft.find(section, item_id) is not None or (section, item_id) in draft.pending:
            item_id, number = f"{base}-{number}", number + 1
        return item_id

    with draft._lock:
        for section in draft.sections:
            for row in helper.items.get(section, []):
                item = copy.deepcopy(row)
                renamed[row["id"]] = item["id"] = new_id(section, row["id"])
                draft.items.setdefault(section, []).append(item)
                merged.append(item)
        for (section, old), pending in helper.pending.items():
            item_id = new_id(section, old)
            draft.pending[(section, item_id)] = {**copy.deepcopy(pending), "id": item_id}
            draft.rejected[(section, item_id)] = list(helper.rejected.get((section, old)) or ["넣을 때 거절됨"])
            refused.append(item_id)
        draft.missing += [{**entry, "id": renamed[entry["id"]]} for entry in helper.missing if entry["id"] in renamed]
        if merged or refused:
            draft.version += 1
    return merged, refused


def table_task(chunk: Chunk) -> str:
    rows = ", ".join(f"{chunk.table}.r{row}" for row in chunk.rows)
    return "\n".join(
        [
            f"# 이번 담당: 기준표({chunk.label})",
            "맡은 섹션: eligibility",
            f"자격 담당을 돕습니다. 원문 표 {chunk.table}의 아래 행에 적힌 신청 자격 기준만 eligibility 항목으로 넣습니다(공통 지시 2장의 「자격」 절).",
            f"- 맡은 행: {rows}" + (f" (행 대상: {', '.join(chunk.groups)})" if chunk.groups else ""),
            "- 행의 대상(공급유형·계층·공급방식)이 다르면 대상마다 조건을 따로 두고 scope.targetGroups에 원문의 대상 이름을 적습니다.",
            "  한 대상 안에서 맞벌이·가구원 수·자녀 수(출생자녀 수)에 따라 바뀌는 값은 그 조건의 exceptions(REPLACE)로 넣고 그 행을 근거로 인용합니다.",
            "- 맡은 행의 기준(소득 비율·자산 금액 등)은 빠짐없이 조건이나 예외에 넣고, 근거는 그 행·칸 id로 붙입니다. 소득이 비율과 가구원수별 금액으로 "
            "함께 적혀 있으면 공통 지시대로 비율만 조건식으로 쓰고 금액은 basis·description에 적습니다.",
            "- 맡은 행 밖의 기준(다른 표·본문 글)은 넣지 않습니다. 그 기준은 자격 담당이 넣습니다.",
            "- 다 넣고 검증 결과의 문제를 고쳤으면 finish를 부릅니다.",
        ]
    )


def table_note(tables: list[dict[str, Any]]) -> str:
    """자격 담당 할 일 글에 붙이는 기준표 담당 결과: 다 넣은 묶음은 넣은 항목 요약(다시 넣지 않게), 끝내지 못했거나(호출 상한·오류)
    PARTIAL로 끝낸 묶음은 남은 행을 넣으라고, 거절된 채 남은 항목은 고쳐 넣으라고."""
    lines = [
        "# 기준표 담당이 먼저 넣은 것",
        "아래 표 행의 기준은 기준표 담당이 넣어 초안에 있습니다. 같은 기준을 다른 표·글에서 다시 넣지 않고, 검증 결과에 이 항목의 문제가 있으면 "
        "update_item으로 고칩니다.",
    ]
    for record in tables:
        groups = f"({', '.join(record['groups'])})" if record.get("groups") else ""
        why = record.get("stopped") or record.get("partial")
        if why:
            lines.append(
                f"- {record['rows']}{groups}: 기준표 담당이 다 넣지 못했습니다({str(why)[:60]}). 넣은 항목 {len(record['items'])}개 말고 "
                "이 행의 남은 기준은 이 담당이 넣습니다."
            )
        else:
            lines.append(f"- {record['rows']}{groups}: 항목 {len(record['items'])}개")
        if record.get("refused"):
            lines.append(f"  넣을 때 거절된 항목(update_item으로 틀린 칸만 고쳐 넣음): {', '.join(record['refused'])}")
        lines += [f"  {brief}" for brief in record.get("brief") or []]
    return "\n".join(lines)


def _brief(item: dict[str, Any]) -> str:
    """항목 한 줄 요약: id, 대상, 조건식(원자 하나면 속성·연산·값), 예외의 바뀐 기준값."""
    groups = ", ".join((item.get("scope") or {}).get("targetGroups") or []) or "대상 전체"
    rule = item.get("rule") or {}
    expression = rule.get("expression") or {}
    if expression.get("kind") == "ATOMIC":
        shown = f"{expression.get('attribute')} {expression.get('operator')} {expression.get('value')}"
    else:
        shown = str(rule.get("status") or "")
    values = [str((exception.get("effectExpression") or {}).get("value")) for exception in item.get("exceptions") or []]
    return f"{item.get('id')}: {groups} — {shown}" + (f" (예외 {', '.join(values)})" if values else "")


def _table_issues(spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], chunk: Chunk) -> list[dict[str, Any]]:
    """기준표 담당이 받는 검증 결과: 자기 항목의 문제와, 맡은 행 가운데 기준값을 쓰는 조건이 없는 행(다른 기준·다른 표의 누락은 자격 담당 몫)."""
    found, candidate = _checked(spec, draft, state, rt, documents)
    own = {row.get("id") for section in draft.sections for row in draft.items.get(section, [])} | {item_id for _, item_id in draft.rejected}
    kept = [issue for issue in found if issue.get("item") in own]
    if candidate is not None and candidate.get("eligibility"):
        missed, _ = missed_criteria_rows(candidate, state["document"].source, frozenset(chunk.spots))
        if missed:
            description = criteria_omission_description(missed)[:SECTION_DESCRIPTION_CHARS]
            kept.insert(0, {"code": CRITERIA_OMISSION, "target": "/quality/coverage/eligibility", "description": description})
    return kept


def parts_of(spec: CallSpec, draft: SectionDraft, document: DocumentModel, documents: tuple[str, ...], anchors: bool = False) -> list[dict[str, Any]]:
    parts = []
    for section in spec.sections:
        items = draft.items.get(section, [])
        coverage = draft.coverage.get(section) or (
            {"status": "EXTRACTED", "reason": None} if items else {"status": "FAILED", "reason": "담당이 항목을 넣지 못했어요."}
        )
        parts.append(to_part(section, items, document, documents, coverage, draft.missing_for(section), anchors=anchors))
    return parts


def _agent(model: Any, name: str, state: Any, documents: tuple[str, ...], middleware: list[AgentMiddleware]) -> Any:
    rules: FieldRules = state["rules"]
    return create_agent(
        model,
        tools=[*shared_tools(tuple(state["plan"]["sections"]), documents), *WRITE_TOOLS],
        system_prompt=system_prompt(rules),
        # 재시도가 바깥: 다시 보낼 때마다 예산을 다시 예약. 도구 오류는 그 호출의 오류 답으로(담당은 계속)
        middleware=[retry_middleware(), BudgetMiddleware(name), ToolErrorMiddleware(), *middleware],
        context_schema=SectionContext,
        name=name,
    )


def _issues(spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...]) -> list[dict[str, Any]]:
    """구조 조각 + 지금 초안을 V1 결합·검증에 넣어 이 담당 섹션의 문제만. 결합기가 형식이 틀려 버리는 것(항목·응답 전체)은
    결합기와 같은 형식 검사로 먼저 알립니다(검토 이슈에는 「범위 미완료」로만 남아 이유가 안 보임).
    판정 섹션 밖(일정·선정·서류 등)의 근거 문제는 검증기가 검토 이슈가 아닌 메모로 내리고 그 항목을 뺍니다(verifier.NOTE_CODES).
    그 메모도 알립니다(2026-11-06 세 번째 실제 실행: 결합기가 가점 5행을 「근거를 확인하지 못한 항목」으로 뺐는데 담당은 「문제 없음」을 받음)."""
    return _checked(spec, draft, state, rt, documents)[0]


def _checked(
    spec: CallSpec, draft: SectionDraft, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """_issues와 그때 결합한 후보(결합하지 못했으면 None)."""
    mine = parts_of(spec, draft, state["document"], documents)
    found = [*_not_added(draft), *_format_problems(mine, draft)]
    report = pipeline.evaluate_parts([*(state.get("parts") or []), *mine], state["material"], state["context"], rt)
    if report is None:
        return [*found, {"code": "NOT_ASSEMBLED", "target": "/notice", "description": "공고 기본 정보(notice)가 없어 결합하지 못했어요."}], None
    candidate = report.candidate
    quality = candidate["quality"]
    notes = [n for n in quality.get("notes") or [] if isinstance(n, dict) and n.get("code") in LOST_VALUE_NOTES]
    for issue in [*quality["reviewIssues"], *notes]:
        if any(_belongs(issue["target"], section) for section in spec.sections):
            chars = SECTION_DESCRIPTION_CHARS if issue["target"].startswith("/quality/coverage/") else DESCRIPTION_CHARS
            found.append(
                {"code": issue["code"], "target": issue["target"], **_item_of(candidate, issue["target"]), "description": issue["description"][:chars]}
            )
    # 계약 검사 오류: 마지막 계약 정리(quarantine)가 그 조건식을 내리거나 항목을 빼므로 담당이 고칠 수 있을 때 알립니다
    # (2026-11-07 23건 재조립 sh-310976: 담당이 넣은 「도시근로자 월평균소득 70% 이하」 조건식이 기준 연도·버전이 비어
    #  INCOMPLETE_INCOME_BENCHMARK로 원문만 남음 — 검토 이슈가 아니라 계약 오류라 담당은 받지 못했음)
    for error in report.contract_errors:
        code, _, rest = error.partition(" ")
        target = rest.split(":")[0].strip() or "/"
        if any(_belongs(target, section) for section in spec.sections):
            description = f"계약 검사 오류 {code}: 그대로 두면 마지막 계약 정리가 이 조건식을 내리거나 항목을 빼고 사람 확인으로 보냅니다."
            found.append({"code": f"CONTRACT_{code}", "target": target, **_item_of(candidate, target), "description": description})
    return found, candidate


def _not_added(draft: SectionDraft) -> list[dict[str, Any]]:
    """넣을 때 거절되어 아직 초안에 없는 항목. 도구 결과로 한 번 알려도 항목이 많으면 담당이 놓치므로 넣을 때까지 검증 결과에 남깁니다."""
    return [
        {
            "code": NOT_ADDED,
            "target": f"/{section}",
            "item": item_id,
            "description": f"넣을 때 거절되어 초안에 없습니다({'; '.join(reasons)}). update_item(같은 id, 틀린 칸만)으로 고치면 넣어집니다.",
        }
        for (section, item_id), reasons in list(draft.rejected.items())
    ]


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
    """「/selectionRules/3/rule」 → 그 항목의 id(담당이 넣을 때 쓴 id로 고칠 항목을 찾게). 위치가 항목 안 하위 항목(예외 등)이면 그 id도 inner로
    (2026-11-06 5건 재측정 bmc-72: 「/eligibility/20/exceptions/3/originalText」 순번만 받은 담당이 다른 예외를 고침)."""
    tokens = target.strip("/").split("/")
    if len(tokens) >= 2 and tokens[1].isdigit():
        rows = candidate.get(tokens[0])
        if isinstance(rows, list) and int(tokens[1]) < len(rows) and isinstance(rows[int(tokens[1])], dict) and rows[int(tokens[1])].get("id"):
            found = {"item": rows[int(tokens[1])]["id"]}
            node: Any = rows[int(tokens[1])]
            for token in tokens[2:]:
                if isinstance(node, list) and token.isdigit() and int(token) < len(node):
                    node = node[int(token)]
                elif isinstance(node, dict):
                    node = node.get(token)
                else:
                    break
                if isinstance(node, dict) and isinstance(node.get("id"), str) and node["id"]:
                    found["inner"] = node["id"]
            return found
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
            turns[-1]["verify"] = str(message.content)[:VERIFY_TRACE_CHARS]
    return turns
