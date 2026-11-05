"""재확인 에이전트 전략 (EXTRACTION_RECHECK_STRATEGY=agent).

다시 볼 항목마다 대화 하나를 열어, AI가 도구(repair/tools.py)를 골라 쓰고 submit_fix로 고친 항목을 냅니다.
- 반복은 이 코드가 합니다: 한 차례 = 모델 호출 한 번(사용량·공고당 비용 상한·장부·캐시를 그대로 지남). 항목당 최대 max_turns() 차례.
- 고친 항목들을 지금 재확인 응답과 같은 모양(섹션 → 항목 목록, 인용 목록)으로 모아 돌려주고, 채택은 recheck.adopt가 정합니다.
- 섹션 전체 문제(빠진 항목 더하기)는 항목 하나를 고치는 일이 아니라서 지금처럼 한 번에 묶어 묻습니다(BatchStrategy).
- 도구를 지원하지 않는 모델(로컬 AI)이면 전부 BatchStrategy로 돌아갑니다.
- 비용 상한에 걸리면 남은 항목은 시작하지 않습니다(처음 값 유지).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from mujuthaek_extraction.assemble.quotes import NormalizedText
from mujuthaek_extraction.extract import CallAttempt, ExtractionRun
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, ToolTurn, supports_tools
from mujuthaek_extraction.recheck import BATCH, RecheckAnswer
from mujuthaek_extraction.repair.tools import FINAL_TOOL, RepairTools, Submission, item_check, item_refs, problem_code
from mujuthaek_extraction.rules.base import FieldRules, call_schema, document_ids, structure_summary
from mujuthaek_extraction.verify import VerificationReport

# 항목 하나에 쓰는 모델 차례 상한(도구 호출 수와 같음: 차례마다 도구 하나). 설정 EXTRACTION_AGENT_MAX_TURNS.
# 8 → 6(2026-11-05): 기록 30여 항목이 대부분 8차례를 다 썼고 그중 2~4차례가 처음 인용 자리 찾기였음 → 그 자리를 미리 찾아 주고 줄임
DEFAULT_MAX_TURNS = 6
TURNS_ENV = "EXTRACTION_AGENT_MAX_TURNS"
LOCATED_QUOTES = 4  # 미리 찾아 보여 줄 처음 인용 수(입력 길이)
TURN_OUTPUT_TOKENS = 8_000  # 차례마다 출력 한도. 마지막 제출에 항목 전체가 들어가므로 여유를 둡니다(추론 토큰 포함)
BUDGET_CODES = frozenset({"BUDGET", "GLOBAL_BUDGET"})
STRATEGY_ENV = "EXTRACTION_RECHECK_STRATEGY"

INSTRUCTIONS = """# 할 일
검증에서 문제가 난 항목 하나를 고칩니다. 아래 「고칠 항목」의 문제 설명은 프로그램 검사기가 낸 것입니다.
도구로 공고 원문을 찾아 읽고 확인한 뒤 submit_fix로 고친 항목을 냅니다. 차례마다 도구 하나를 부릅니다(차례 수는 제한됩니다).

# 규칙
- 근거는 공고 원문뿐입니다. 원문에서 확인하지 못한 값은 만들지 않습니다. 확인하지 못하면 submit_fix의 give_up에 이유를 적습니다(처음 값이 유지됩니다).
- 인용은 원문에 글자 그대로 이어져 나오는 구간입니다. 제출 전에 인용마다 check_quote로 확인합니다.
- item_json에는 바꿀 칸만 적습니다(공통 지시의 출력 형식, 같은 id). 적지 않은 칸은 처음 값 그대로입니다.
  id가 있는 원소의 목록(가격·수량·예외 등)은 바꿀 원소의 id와 바꿀 칸만 적으면 그 원소만 합쳐지고, id 없는 목록은 통째로 바뀝니다.
  항목 전체를 다시 쓰지 않습니다(다른 칸을 깨뜨리기 쉽습니다).
- 「고칠 항목」의 item이 제출할 모양 그대로입니다. 근거는 항목 안의 quoteRefs(ref 목록)로만 가리킵니다.
  인용문 글자는 항목 밖 submit_fix의 quotes(ref·text)에 적습니다. 항목 안에 quotes 칸을 만들거나 quoteRefs에 인용문 글자를 넣지 않습니다.
- 새 인용은 n1, n2처럼 새 ref로 적습니다. 「고칠 항목」의 quotes에 있는 처음 인용 ref는 그대로 둬도 됩니다.
- item_json은 올바른 JSON 객체 글자입니다(따옴표·괄호를 닫습니다).
- 문제가 근거(인용)만이면 인용(quoteRefs)만 고치고 조건의 뜻(대상·종류·조건식·예외)은 바꾸지 않습니다.
- 제출 전에 validate_item으로 남은 문제를 확인합니다. 제출한 항목에 처음에 없던 문제가 생기면 한 번 되돌려 받으니 고치거나 포기합니다.
  처음부터 있던 문제가 남아도 원문에 맞으면 그대로 냅니다(채택은 프로그램이 정합니다).
- 「처음 인용의 원문 위치」에 처음 인용이 원문 몇 쪽 어디(pageChar)에 있는지와 앞뒤 글이 있습니다. 그 근처의 일이면 search_source 없이
  read_page(쪽, pageChar)나 check_quote로 바로 갑니다.
  확인이 끝났으면 validate_item을 건너뛰고 바로 submit_fix해도 됩니다(새 문제가 생기면 한 번 되돌려 받습니다).
- 도구 결과의 turnsLeft는 남은 차례입니다. 같은 검색을 되풀이하지 말고, 남은 차례가 적으면 제출하거나 포기합니다. 마지막 차례에는 submit_fix만 쓸 수 있습니다.

# 도구를 쓰는 순서 예
(처음 인용 위치를 보고) 필요하면 read_page로 앞뒤를 읽고 → check_quote로 새 인용을 확인하고 → submit_fix.
처음 인용 근처에 답이 없을 때만 search_source로 다른 위치를 찾습니다."""


STRATEGIES = ("batch", "agent", "hybrid")  # hybrid: 묶음 재확인 뒤 남은 문제만 에이전트로(recheck.recheck_rounds)


def max_turns() -> int:
    value = os.getenv(TURNS_ENV, "")
    return max(2, int(value)) if value.strip().isdigit() else DEFAULT_MAX_TURNS


def recheck_strategy() -> str:
    strategy = os.getenv(STRATEGY_ENV, "batch")
    if strategy not in STRATEGIES:
        raise ValueError(f"{STRATEGY_ENV}는 {'·'.join(STRATEGIES)} 중 하나여야 합니다: {strategy!r}")
    return strategy


@dataclass
class ItemLog:
    """항목 하나를 고친 기록(작업 기록 usage.recheck.agent)."""

    target: str
    turns: int = 0
    tools: dict[str, int] = field(default_factory=dict)
    outcome: str = ""  # SUBMITTED · GAVE_UP · TURN_LIMIT · NO_TOOL_CALL · MODEL_ERROR · BUDGET · NOT_STARTED
    returned: int = 0  # 처음에 없던 문제가 생겨 돌려보낸 제출 수

    def summary(self) -> dict[str, Any]:
        return {"target": self.target, "turns": self.turns, "tools": dict(self.tools), "outcome": self.outcome, "returned": self.returned}


class AgentStrategy:
    """항목마다 도구를 쓰는 재확인. 고친 답의 채택은 recheck.adopt가 정합니다."""

    def answer(
        self,
        rules: FieldRules,
        material: ExtractionMaterial,
        model: ExtractionModel,
        parts: list[dict[str, Any]],
        targets: list[dict[str, Any]],
        sections: list[str],
        evaluate: Callable[[list[dict[str, Any]]], VerificationReport | None] | None = None,
        **run_options: Any,
    ) -> RecheckAnswer:
        if evaluate is None or not supports_tools(model):
            return BATCH.answer(rules, material, model, parts, targets, sections, **run_options)
        items = [t for t in targets if t["id"] is not None or t["section"] == "notice"]
        whole = [t for t in targets if t not in items]
        run, logs = ExtractionRun(), []
        index = NormalizedText(material.text)  # 원문 색인은 공고의 항목끼리 함께 씁니다
        response: dict[str, Any] = {"quotes": []}
        stop_all = False
        for number, target in enumerate(items, start=1):
            log = ItemLog(f"{target['section']}/{target['id']}" if target["id"] else target["section"])
            logs.append(log)
            if stop_all:
                log.outcome = "NOT_STARTED"
                continue
            submission = self._repair(rules, material, model, parts, target, evaluate, run, log, index)
            stop_all = log.outcome == "BUDGET"
            if submission is not None and submission.item is not None:
                _add(response, target, submission, f"a{number}-", material.text_document_id)
        rejected: tuple[tuple[str, str], ...] = ()
        if whole:  # 섹션 전체 문제는 지금처럼 한 번에 묶어 묻습니다
            batch = BATCH.answer(rules, material, model, parts, whole, [s for s in sections if any(t["section"] == s for t in whole)], **run_options)
            if batch.run is not None:
                run.attempts += batch.run.attempts
                run.raw_responses += batch.run.raw_responses
                run.failed_calls += batch.run.failed_calls
            rejected = batch.rejected
            if batch.response is not None:
                _combine(response, batch.response)
        agent = {"items": [log.summary() for log in logs]}
        if not any(key != "quotes" for key in response):
            return RecheckAnswer(None, run, targets, sections, (*rejected, ("전체", "에이전트가 고친 항목 없음")), agent=agent)
        return RecheckAnswer(response, run, targets, sections, rejected, agent=agent)

    def _repair(
        self,
        rules: FieldRules,
        material: ExtractionMaterial,
        model: ExtractionModel,
        parts: list[dict[str, Any]],
        target: dict[str, Any],
        evaluate: Callable[[list[dict[str, Any]]], VerificationReport | None],
        run: ExtractionRun,
        log: ItemLog,
        index: NormalizedText | None = None,
    ) -> Submission | None:
        section, item_id = target["section"], target["id"]
        base_item, base_quotes = _original(parts, section, item_id)
        tools = RepairTools(
            material,
            item_check(parts, evaluate, section, item_id, material.text_document_id),
            base_item=base_item,
            base_quotes=base_quotes,
            known_codes=frozenset(problem_code(p) for p in target["problems"]),
            index=index,
        )
        first_quotes = [{"ref": ref, "text": base_quotes[ref]} for ref in item_refs(base_item) if ref in base_quotes] if isinstance(base_item, dict) else []
        context = {
            "고칠 항목": _target_view(target, base_item, base_quotes),
            "처음 인용의 원문 위치": tools.locate(first_quotes[:LOCATED_QUOTES]),
            "이미 추출한 구조 (scope·locationId에는 이 ID만 사용)": structure_summary(parts[0]),
        }
        base = ModelRequest(
            prompt_version=f"{rules.field}/{rules.prompt_version}/repair",
            call_name="",
            system=rules.system_prompt(),
            user=json.dumps(context, ensure_ascii=False, indent=1),
            instructions=INSTRUCTIONS,
            output_schema=call_schema((section,), document_ids(material)),
            max_output_tokens=TURN_OUTPUT_TOKENS,
            tools=tools.specs,
        )
        turns: list[ToolTurn] = []
        log.outcome = "TURN_LIMIT"
        limit = max_turns()
        for turn in range(1, limit + 1):
            name = f"repair:{log.target}:turn{turn}"
            tools.final = turn == limit  # 마지막 차례는 제출(또는 포기)만 할 수 있습니다. 도구 목록은 그대로(입력 캐시 유지), 부를 도구만 정합니다
            request = replace(base, call_name=name, turns=tuple(turns), forced_tool=FINAL_TOOL if tools.final else None)
            try:
                response = model.complete(request)
            except ModelError as error:
                run.attempts.append(_attempt(request, None, error))
                run.failed_calls.append((name, str(error)))
                log.outcome = "BUDGET" if error.code in BUDGET_CODES else "MODEL_ERROR"
                break
            run.attempts.append(_attempt(request, response, None))
            log.turns = turn
            if not response.tool_calls:
                log.outcome = "NO_TOOL_CALL"
                break
            results = tuple(_with_turns_left(tools.run(call), limit - turn) for call in response.tool_calls)
            calls = [{"name": c.name, "arguments": c.arguments} for c in response.tool_calls]
            # 도구 결과도 앞부분만 남깁니다(왜 돌려보냈는지·무엇을 찾았는지 다시 돌리지 않고 보려고). 원문 조각이라 길이를 줄입니다
            record = {"toolCalls": calls, "results": [r[:600] for r in results]}
            run.raw_responses.append((name, json.dumps(record, ensure_ascii=False)))
            turns.append(ToolTurn(response.tool_calls, results))
            if tools.submission is not None:
                log.outcome = "GAVE_UP" if tools.submission.item is None else "SUBMITTED"
                break
        log.tools = dict(tools.calls)
        log.returned = tools.rejected_submissions
        return tools.submission


def _original(parts: list[dict[str, Any]], section: str, item_id: str | None) -> tuple[Any, dict[str, str]]:
    """처음 추출한 항목(AI 출력 형식)과 그 조각의 인용 목록(ref → 글). 제출 조각을 합칠 바탕입니다."""
    for part in parts:
        if not isinstance(part, dict) or section not in part:
            continue
        quotes = {q["ref"]: q["text"] for q in part.get("quotes") or [] if isinstance(q, dict) and "ref" in q and "text" in q}
        if section == "notice":
            return part.get("notice"), quotes
        item = next((x for x in part.get(section) or [] if isinstance(x, dict) and x.get("id") == item_id), None)
        return item, quotes
    return None, {}


def _target_view(target: dict[str, Any], base_item: Any, base_quotes: dict[str, str]) -> dict[str, Any]:
    """에이전트에게 보여 줄 고칠 항목: 제출할 때와 같은 모양(AI 출력 형식, 근거는 quoteRefs)과 그 ref의 인용문을 따로 둡니다.
    묶음 재확인처럼 인용문을 항목 안에 끼워 보여 주면, 에이전트가 그 모양을 따라 항목 안에 quotes 칸을 만들어 형식이 깨졌습니다(2026-11-05 실측)."""
    if not isinstance(base_item, dict):
        return target  # 처음 항목을 찾지 못하면 묶음 재확인과 같은 모양으로
    refs = item_refs(base_item)
    return {
        "section": target["section"],
        "id": target["id"],
        "problems": target["problems"],
        "item": base_item,
        "quotes": [{"ref": ref, "text": base_quotes[ref]} for ref in refs if ref in base_quotes],
    }


def _with_turns_left(result: str, left: int) -> str:
    """도구 결과에 남은 차례를 붙입니다(남은 차례가 적으면 제출을 서두르게)."""
    try:
        value = json.loads(result)
    except ValueError:
        return result
    if not isinstance(value, dict):
        return result
    value["turnsLeft"] = left
    if left == 1:
        value["notice"] = "다음 차례가 마지막입니다. 다음에는 submit_fix로 내거나 give_up에 이유를 적습니다."
    return json.dumps(value, ensure_ascii=False)


def _attempt(request: ModelRequest, response: Any, error: ModelError | None) -> CallAttempt:
    return CallAttempt(
        call_name=request.call_name,
        prompt_version=request.prompt_version,
        repair=False,
        model_id=getattr(response, "model_id", None),
        stop_reason=response.stop_reason.value if response is not None else None,
        input_tokens=getattr(response, "input_tokens", None),
        output_tokens=getattr(response, "output_tokens", None),
        cached_input_tokens=getattr(response, "cached_input_tokens", None),
        error=(error.code or "ERROR") if error is not None else None,
        cache_write_tokens=getattr(response, "cache_write_tokens", None),
    )


def _add(response: dict[str, Any], target: dict[str, Any], submission: Submission, prefix: str, document_id: str) -> None:
    """제출한 항목을 재확인 응답 모양에 더합니다. 항목끼리 인용 ref가 겹치지 않게 앞에 항목 번호를 붙입니다."""
    renamed = {q["ref"]: prefix + q["ref"] for q in submission.quotes}
    response["quotes"] += [{"ref": renamed[q["ref"]], "documentId": document_id, "text": q["text"]} for q in submission.quotes]
    item = _rename(submission.item, renamed)
    if target["section"] == "notice":
        response["notice"] = item
    else:
        response.setdefault(target["section"], []).append(item)


def _rename(node: Any, renamed: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: ([renamed.get(r, r) for r in v] if k == "quoteRefs" and isinstance(v, list) else _rename(v, renamed)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rename(x, renamed) for x in node]
    return node


def _combine(response: dict[str, Any], other: dict[str, Any]) -> None:
    """묶음 재확인 응답을 더합니다(섹션 전체 문제). 인용 ref는 앞에 b-를 붙여 에이전트 인용과 겹치지 않게 합니다."""
    renamed = {q["ref"]: "b-" + q["ref"] for q in other.get("quotes") or [] if isinstance(q, dict) and "ref" in q}
    response["quotes"] += [{**q, "ref": renamed[q["ref"]]} for q in other.get("quotes") or [] if isinstance(q, dict) and "ref" in q]
    for key, value in other.items():
        if key == "quotes":
            continue
        if isinstance(value, list):
            response.setdefault(key, []).extend(_rename(value, renamed))
        else:
            response[key] = _rename(value, renamed)


AGENT = AgentStrategy()
