"""V2 구조 단계(공급표 열 의미, 공고·위치)를 섹션 담당과 같은 앞부분으로 부릅니다(EXTRACTION_V2_SHARED_STRUCTURE, 기본 켬).

V1 방식 구조 단계는 [V1 지시·원문 글] 앞부분을 따로 캐시에 올려, 공고마다 원문을 두 번(V1 앞부분·담당 앞부분) 캐시에 썼습니다
(2026-11-09 23건 운영 조건 비용: V2 $1.055로 V1보다 +17.9%, 차이 대부분이 담당 앞부분 데우기 $0.134. 공급표 열 묻기가 V1 앞부분을 쓰는 데 $0.148).
여기서는 데우기(prime)를 먼저 보내 [도구·V2 지시·id 붙은 원문] 앞부분을 캐시에 올리고, 열 의미 묻기와 공고·위치 호출은 그 앞부분 뒤에 할 일
메시지만 붙여 보냅니다. OpenAI 캐시는 앞 요청이 끝난 메시지 자리에만 남으므로(같은 원문 뒤에 다른 할 일이 붙은 요청끼리는 원문을 함께 읽지 못함)
데우기가 먼저 끝나야 합니다. 앞부분이 같으려면 도구 목록도 담당과 같아야 해서, 도구는 그대로 두고 이 호출에서만 부르지 못하게 하고(tool_choice none)
답은 JSON 글로 받습니다(엄격 출력 형식은 앞부분 앞에 붙어 캐시를 가름).
- 공급·가격 표는 V1과 같이 코드가 옮기고(supply_tables) AI는 열 의미만 답합니다. 답은 V1과 같은 형식(MAPPING_SCHEMA)으로 검사합니다.
- 공고·위치 항목은 담당과 같은 넣기 검사(write.add: 형식·근거 id)를 거쳐 V1 AI 조각이 되고(contract.to_part), 코드 조각과 V1처럼 합칩니다.
- 공급표 후보가 없거나, 코드가 수량을 옮기지 못했거나(구조 호출이 수량 묶음을 만들어야 함), 열 의미·공고를 받지 못하면 V1 방식으로 돌아갑니다.
  데우기는 이미 보냈으므로 담당은 그대로 캐시를 읽습니다.
- 끝 단계(conclude)의 V1 재확인은 그대로 둡니다(구조 섹션에 문제가 있을 때만 돌고, 그때는 V1 앞부분을 새로 씀).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import logging
import os
import re
from types import SimpleNamespace
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage

from mujuthaek_extraction import extract, format_memory, pipeline, supply_tables
from mujuthaek_extraction.assemble.quotes import MIN_QUOTE_CHARS, normalize
from mujuthaek_extraction.model.fallback import FallbackOnErrorModel
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, document_ids, structure_summary
from mujuthaek_extraction.v2.agents import section
from mujuthaek_extraction.v2.agents.cut import cut_off
from mujuthaek_extraction.v2.agents.prompt import V1_STRUCTURE_PARTS
from mujuthaek_extraction.v2.contract import EvidenceError, joined_text, located_text
from mujuthaek_extraction.v2.tools.typed import item_schema
from mujuthaek_extraction.v2.tools.write import SectionContext, SectionDraft, add, report_missing, set_coverage, tuck_evidence

log = logging.getLogger(__name__)

SHARED_ENV = "EXTRACTION_V2_SHARED_STRUCTURE"
MAPPING = supply_tables.CALL_NAME  # 호출 기록·응답 대기 한도는 V1 열 의미 호출과 같은 이름으로
STRUCTURE = "structure"
SECTIONS = ("notice", "locations")  # 공급 묶음은 코드가 표에서 옮김(supply_tables.has_counts)
# 공고·위치만 담는 출력 한도. V1 구조 호출 한도(6.4만)는 공급 묶음까지 담던 것이고, 2026-11-09 23건 V1 구조 출력은 추론 포함 최대 6,413토큰
OUTPUT_TOKENS = 16_000
REPAIRS = 1  # JSON·형식·근거 문제를 알려 고친 답을 한 번 더 받음
NULLABLE_COLUMN_KEYS = ("countKind", "priceKind", "unit", "plan", "priceStage", "targetGroup")
V2_TABLE_ID = re.compile(r"^(?:d(\d+)\.)?t(.+)$")  # 원문 메시지의 표 id(t4-1·d2.t3-1)
IMAGE_REF = re.compile(r"^g\d+\.")  # 그림 판독 묶음 조각 id(g1.3·g1.t1.r2, v2/document.py)
# V1 공통 지시 공급 절의 수량 규칙(OFFERED·TOTAL_HOUSING·RESERVE·WAITLIST 정의). V2 지시는 공급 절을 통째로 빼므로 공고 전체 수량(notice.counts)을
# 적는 이 호출에는 따로 넣습니다(2026-11-10 23건 유료 확인 gh-801: 예비입주자만 모집하는 공고의 「금회 모집 예비자 수」 280을 RESERVE로 적음,
# V1 구조 호출은 이 규칙대로 OFFERED)
V1_COUNT_RULES = re.compile(r"^### 수량\(`counts`\)\n.*?(?=^#{1,3} )", re.M | re.S)
COUNT_RULES_NOTE = "아래 수량 규칙(공통 지시 공급 절)은 공고 전체 수량(notice.counts)에 씁니다. 공급 묶음의 수량은 프로그램이 표에서 옮겼습니다."

MAPPING_ANSWER = """
# 답하는 법(이 담당만)
- 도구를 부르지 않고 JSON 객체 하나만 답합니다(앞뒤 설명 없이). 형식(JSON 스키마): {schema}
- 표 번호 「4-1」은 원문 메시지의 [표 t4-1]입니다(첨부 PDF가 여럿이면 「1:4-1」 = [표 t4-1], 「2:3-1」 = [표 d2.t3-1]).
  table에는 위 「표 번호」를 그대로 씁니다.
- column은 위 [열 제목]에 붙은 번호(1부터)입니다. 원문 메시지 표의 칸 번호는 0부터라 열 1이 c0, 열 2가 c1입니다.
- 값이 없는 칸(complex·countKind·priceKind·unit·plan·priceStage·targetGroup)은 null로 둡니다."""

STRUCTURE_ANSWER = """
# 답하는 법(이 담당만)
도구를 부르지 않고 JSON 객체 하나만 답합니다(앞뒤 설명 없이):
{"notice": 공고 항목, "locations": [위치 항목, …], "coverage": {섹션: {"status": …, "reason": …}},
 "missing": [{"section": …, "id": …, "field": …, "reason": …, "description": …}]}
- 항목 형식은 아래 notice·locations 형식(add_notice·add_locations 도구의 입력 형식과 같음)이고, 근거는 공통 지시 3장대로 원문 조각 id(evidence)로 붙입니다.
  값이 있는 칸만 적습니다(null·빈 목록은 프로그램이 채움). notice 항목 자체의 evidence에는 공고 제목·기관·공고일이 적힌 원문 줄을 붙입니다
  (수량 같은 하위 항목의 evidence와 따로).
- coverage(위 지시의 coverage)는 원문에 있는데 넣지 못한 위치가 있을 때(PARTIAL, reason에 무엇)와 원문에 위치가 없을 때(locations
  NOT_IN_SOURCE)만 적습니다. notice는 비울 수 없습니다.
- missing(위 지시의 missingFields)은 판정·화면에 필요한데 원문에 없어 비운 칸입니다. field는 항목 안 칸 경로(예: announcedOn), reason은
  NOT_IN_SOURCE · TO_BE_ANNOUNCED · SOURCE_ATTACHMENT_REQUIRED · CONFLICT · UNREADABLE · NOT_APPLICABLE, id는 위치 id(notice는 null),
  description은 '~해요' 체 한 문장.
- 형식·근거가 틀려 넣지 못한 항목은 이유를 알려 드립니다. 그때는 고친 항목만 같은 형식으로 다시 답합니다."""

FIX_JSON = "답을 쓸 수 없습니다: {problem}\n같은 형식의 JSON 하나로 처음부터 다시 답합니다."
FIX_ITEMS = "# 넣지 못한 것\n{problems}\n고친 항목만 같은 형식의 JSON 하나로 다시 답합니다(넣어진 항목은 다시 보내지 않음). 원문상 고칠 수 없으면 {{}}."
NOT_ADDED = "넣지 못한 위치가 있어요(근거·형식 오류)."


class AnswerInText(AgentMiddleware):
    """도구 목록은 담당과 같게 두고(앞부분 캐시) 이 호출에서만 도구를 부르지 못하게 합니다. OpenAI 안내: 도구 정의를 빼는 대신 tool_choice none."""

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return handler(request.override(tool_choice="none"))


def shared_on() -> bool:
    """구조 단계를 담당 앞부분으로 부를지: 기본 켬, EXTRACTION_V2_SHARED_STRUCTURE=false면 V1 방식."""
    return os.getenv(SHARED_ENV, "true").strip().lower() != "false"


def shares(state: Any, rt: pipeline.Runtime) -> bool:
    """이 공고의 구조 단계를 담당 앞부분으로 부르는지: 켜져 있고 채팅 모델이 있고 공급표 후보가 있을 때(V1 구조 방식이 공급표를 쓰는 조건과 같음).
    그래프의 계획(데우기를 맡을지)과 구조 노드가 같은 답을 냅니다."""
    material = state["material"]
    return (
        shared_on()
        and getattr(rt.models, "chat", None) is not None
        and state["rules"].supply_tables
        and bool(material.pdf_pages or getattr(material, "sheets", ()))
        and bool(supply_tables.candidates(material))
    )


def run_structure(spec: CallSpec, state: Any, rt: pipeline.Runtime) -> dict[str, Any]:
    """데우기 → 공급표 열 의미 → 공고·위치. 받으면 그래프 상태(parts·structure·recheck_model·usage·traces)를, 받지 못하면 usage·traces만
    돌려줍니다(그래프가 V1 방식으로). state에는 계획(plan: 담당 도구 섹션)이 있어야 합니다."""
    usage = section.prime(state, rt)
    traces: list[dict[str, Any]] = []
    try:
        built = _build(spec, state, rt, usage, traces)
    except Exception as error:  # 예산 상한·모델 오류 등: 구조는 공고 전체가 기대므로 멈추지 않고 V1 방식으로
        usage.append({"agent": STRUCTURE, "stopped": f"{type(error).__name__}: {error}"[:300]})
        log.warning("구조 단계를 V1 방식으로 돌립니다", extra={"error": f"{type(error).__name__}: {error}"[:300]})
        built = None
    if built is None:
        return {"usage": usage, "traces": traces}
    parts, summary = built
    models = rt.models
    recheck_model = FallbackOnErrorModel(models.primary, models.fallback) if models.fallback is not None else models.primary
    return {"parts": parts, "structure": summary, "recheck_model": recheck_model, "usage": usage, "traces": traces}


def _build(spec: CallSpec, state: Any, rt: pipeline.Runtime, usage: list[dict[str, Any]], traces: list[dict[str, Any]]):
    material = state["material"]
    documents = tuple(document_ids(material))
    with rt.usage.stage(MAPPING):
        mapped = _mapping(spec, state, rt, documents, usage, traces)
    if mapped is None:
        return None
    tables, mapping = mapped
    remembered = format_memory.observe(state["intake"].raw.source_code, (tables, mapping))  # V1과 같은 기관 기억 그림자 모드
    if remembered is not None:
        rt.usage.record("formatMemory", remembered)
    table_part = extract.code_supply_part(material, tables, mapping)
    if table_part is None or not supply_tables.has_counts(table_part):
        return None
    with rt.usage.stage(STRUCTURE):
        draft = _notice_and_locations(spec, state, rt, documents, supply_tables.structure_note(table_part), usage, traces)
    if draft is None:
        return None
    # 공고는 판정에 쓰여 근거 위치를 못 정한 항목 하나로 공고 전체가 사람 확인으로 가므로 여러 곳에 있는 근거에 이웃 행을 붙임(contract.anchor_text)
    part = _combine(section.parts_of(dataclasses.replace(spec, sections=SECTIONS), draft, state["document"], documents, anchors=True))
    # 이 뒤는 V1 구조 호출(extract.run_extraction)과 같음: 코드 위치·인용을 구조 조각으로 옮기고 표의 단지 이름을 위치에 잇습니다
    made = supply_tables.merge_into_structure(table_part, part)
    supply_tables.link_locations(table_part, part.get("locations") or [])
    shown = [loc for loc in part.get("locations") or [] if not (isinstance(loc, dict) and loc.get("id") in made)]
    return [part, table_part], structure_summary({**part, "locations": shown, "supplyGroups": table_part["supplyGroups"]})


def _mapping(spec: CallSpec, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], usage: list[dict[str, Any]], traces: list[dict[str, Any]]):
    """공급표 열 의미 (표들, 답). 형식에 맞는 답을 받지 못하거나 답이 출력 한도에서 잘리면 None(V1 방식이 잘린 답 살리기까지 함)."""
    material = state["material"]
    tables = supply_tables.candidates(material)
    request = supply_tables.mapping_request(state["rules"].build_request(spec, material), tables)
    task = request.instructions + MAPPING_ANSWER.format(schema=json.dumps(supply_tables.MAPPING_SCHEMA, ensure_ascii=False, separators=(",", ":")))
    messages: list[Any] = [section.shared_message(state["document"]), HumanMessage(task)]
    mapping, problem = None, "답이 없습니다."
    for turn in range(REPAIRS + 1):
        messages = _ask(MAPPING, state, rt, documents, messages, request.max_output_tokens, usage)
        text = _reply(messages)
        if text is None:
            break
        mapping, problem = _read_mapping(text, [table.label for table in tables])
        if problem is None or turn == REPAIRS:
            break
        messages = [*messages, HumanMessage(FIX_JSON.format(problem=problem))]
    traces.append({"agent": MAPPING, "turns": section._trace(messages), "problem": problem})
    return (tables, mapping) if problem is None else None


def _read_mapping(text: str, labels: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    """열 의미 답 글 → (답, 문제). 엄격 출력 형식이 아니라 생략한 null 칸은 채우고, 원문 메시지의 표 id로 적은 표 번호는 V1 표 번호로 바꿉니다."""
    try:
        value = _json(text)
    except ValueError as error:
        return None, f"JSON으로 읽을 수 없습니다({str(error)[:200]})"
    for table in value.get("tables") or [] if isinstance(value, dict) and isinstance(value.get("tables"), list) else []:
        if not isinstance(table, dict):
            continue
        table.setdefault("complex", None)
        if isinstance(table.get("table"), str):
            table["table"] = _v1_label(table["table"], labels)
        for column in table.get("columns") or [] if isinstance(table.get("columns"), list) else []:
            if isinstance(column, dict):
                for key in NULLABLE_COLUMN_KEYS:
                    column.setdefault(key, None)
    problem = extract.schema_errors(value, supply_tables.MAPPING_SCHEMA)
    return (value, None) if problem is None else (None, problem)


def _v1_label(label: str, labels: list[str]) -> str:
    """「t4-1」·「d2.t3-1」처럼 원문 메시지의 표 id로 적은 표 번호 → V1 표 번호(「4-1」, 첨부가 여럿이면 「1:4-1」·「2:3-1」). 모르면 그대로."""
    found = V2_TABLE_ID.match(label.strip())
    if label in labels or found is None:
        return label
    document, rest = found.group(1) or "1", found.group(2)
    return next((name for name in (rest, f"{document}:{rest}") if name in labels), label)


def _notice_and_locations(
    spec: CallSpec, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], note: str, usage: list[dict[str, Any]], traces: list[dict[str, Any]]
) -> SectionDraft | None:
    """공고·위치 초안. 답의 항목은 담당 넣기와 같은 검사로 넣고, 넣지 못한 것을 알려 한 번 더 받습니다. 공고를 넣지 못하면 None(V1 방식으로)."""
    draft = SectionDraft(SECTIONS)
    context = SectionContext(document=state["document"], budget=rt.models.budget, draft=draft, documents=documents)
    messages: list[Any] = [section.shared_message(state["document"]), HumanMessage(structure_task(spec, state["rules"], note, documents))]
    problems = ["답이 없습니다."]
    for turn in range(REPAIRS + 1):
        messages = _ask(STRUCTURE, state, rt, documents, messages, OUTPUT_TOKENS, usage)
        text = _reply(messages)
        if text is None:
            break
        try:
            problems = _apply(context, _json(text))
        except ValueError as error:
            problems = [f"JSON으로 읽을 수 없습니다({str(error)[:200]})"]
        if draft.find("notice", None) is None and not any(p.startswith("notice") for p in problems):
            problems.append("notice: 공고 항목이 없습니다.")
        if not problems or turn == REPAIRS:
            break
        messages = [*messages, HumanMessage(FIX_ITEMS.format(problems="\n".join(f"- {p}" for p in problems)))]
    traces.append({"agent": STRUCTURE, "turns": section._trace(messages), "problems": problems, "draft": {"items": draft.items, "coverage": draft.coverage}})
    if draft.find("notice", None) is None:
        return None
    for name in dict.fromkeys(name for name, _ in draft.rejected):  # 고쳐 받지 못한 항목은 조용히 빠지지 않게 그 섹션을 사람 확인으로
        if (draft.coverage.get(name) or {}).get("status") not in ("PARTIAL", "FAILED"):
            draft.coverage[name] = {"status": "PARTIAL", "reason": NOT_ADDED}
    _text_evidence_first(draft.items["notice"], state["document"])
    return draft


def _text_evidence_first(node: Any, document: Any) -> None:
    """공고 항목(하위 항목 포함)의 근거에 쓸 만한 원문 글자 근거가 함께 있으면, 공고 전체를 사람 확인으로 보내는 근거는 뺍니다:
    그림 판독 글자 근거(g…, EVIDENCE_FROM_IMAGE)와 앞뒤 줄과 이어도 너무 짧은 줄(EVIDENCE_QUOTE_TOO_SHORT). 뺀 근거에만 있던 값은 검증기가
    「값이 인용에 없음」으로 막아 틀린 값이 생기지 않습니다. 2026-11-10 23건 유료 확인: sh-311005 본문에도 있는 정보에 표지 그림 판독 줄(g1.*)을
    함께 근거로 씀, sh-310672 12쪽의 떨어진 조각 줄 「06」(원문 4곳)을 근거로 씀 — 둘 다 공고 전체가 검수로 감."""
    if isinstance(node, list):
        for child in node:
            _text_evidence_first(child, document)
    elif isinstance(node, dict):
        evidence = node.get("evidence")
        if isinstance(evidence, list):
            kept = [e for e in evidence if not _weak_evidence(e, document)]
            if kept and len(kept) < len(evidence):
                node["evidence"] = kept
        for key, child in node.items():
            if key != "evidence":
                _text_evidence_first(child, document)


def _weak_evidence(entry: Any, document: Any) -> bool:
    ref = entry if isinstance(entry, str) else str((entry or {}).get("id", ""))
    if IMAGE_REF.match(ref):
        return True
    try:
        text = located_text(document, entry)
    except EvidenceError:
        return False  # 없는 id는 넣기 검사가 이미 거절함
    return len(normalize(text)) < MIN_QUOTE_CHARS and joined_text(document, entry) is None


def structure_task(spec: CallSpec, rules: FieldRules, note: str, documents: tuple[str, ...]) -> str:
    """공고·위치 할 일: V1 구조 호출 지시와 공급표 메모, V2 공통 지시에서 뺀 위치 절·수량 규칙, 답 형식."""
    system = rules.system_prompt()
    locations = "".join(part for part in V1_STRUCTURE_PARTS.findall(system) if "(`locations`)" in part.split("\n", 1)[0])
    counts = V1_COUNT_RULES.search(system)
    count_rules = [COUNT_RULES_NOTE, counts.group(0).rstrip()] if counts else []
    schemas = [f"## {name} 형식\n{json.dumps(item_schema(name, documents), ensure_ascii=False, separators=(',', ':'))}" for name in SECTIONS]
    head = [f"# 이번 담당: {STRUCTURE}", f"맡은 섹션: {', '.join(SECTIONS)}", spec.instructions, note, locations.rstrip()]
    return "\n".join([*head, *count_rules, STRUCTURE_ANSWER, *schemas])


def _apply(context: SectionContext, answer: Any) -> list[str]:
    """JSON 답의 항목·섹션 상태·누락 기록을 담당의 넣기·상태·누락 도구와 같은 검사로 초안에 넣고, 넣지 못한 것을 「위치: 이유」로 돌려줍니다."""
    if not isinstance(answer, dict):
        return ["답은 JSON 객체여야 합니다."]
    problems = []
    for name in SECTIONS:
        if name not in answer:
            continue
        if name != "notice" and not isinstance(answer[name], list):
            problems.append(f"{name}: 항목 목록이어야 합니다.")
            continue
        items, _, _ = tuck_evidence(context.document, [answer[name]] if name == "notice" else answer[name])
        result = json.loads(add(context, name, items))
        for failed in result.get("failed") or []:
            where = name if name == "notice" or not failed.get("id") else f"{name} {failed['id']}"
            problems.append(f"{where}: {'; '.join(failed['errors'][:2])}")
    runtime = SimpleNamespace(context=context)
    coverage = answer.get("coverage")
    for name, entry in coverage.items() if isinstance(coverage, dict) else ():
        if name in SECTIONS and isinstance(entry, dict):  # 다른 섹션(공급 묶음 등)의 상태는 코드가 정함
            done = json.loads(set_coverage.func(str(name), str(entry.get("status")), str(entry.get("reason") or ""), runtime=runtime))
            if "error" in done:
                problems.append(f"coverage {name}: {done['message']}")
    missing = answer.get("missing")
    for entry in missing if isinstance(missing, list) else ():
        if isinstance(entry, dict):
            fields = (str(entry.get(key) or "") for key in ("section", "id", "field", "reason", "description"))
            name, item_id, field, reason, description = fields
            done = json.loads(report_missing.func(name, item_id or None, field, reason, description, runtime=runtime))
            if "error" in done:
                problems.append(f"missing {name} {item_id or ''} {field}: {done['message']}".replace("  ", " "))
    return problems


def _combine(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """섹션마다 만든 조각(contract.to_part: 인용 ref가 조각마다 q1부터) → 구조 조각 하나. 인용 ref 앞에 섹션 이름을 붙여 겹치지 않게 합니다."""
    combined: dict[str, Any] = {"quotes": [], "coverage": {}, "missingFields": []}
    for name, part in zip(SECTIONS, parts, strict=True):
        rename = {quote["ref"]: f"{name}-{quote['ref']}" for quote in part["quotes"]}
        combined["quotes"] += [{**quote, "ref": rename[quote["ref"]]} for quote in part["quotes"]]
        body = copy.deepcopy(part[name])
        extract._rename_quote_refs(body, rename)
        combined[name] = body
        combined["coverage"].update(part.get("coverage") or {})
        combined["missingFields"] += part.get("missingFields") or []
    return combined


def _ask(
    name: str, state: Any, rt: pipeline.Runtime, documents: tuple[str, ...], messages: list[Any], max_output_tokens: int, usage: list[dict[str, Any]]
) -> list[Any]:
    """담당 앞부분(도구 목록·V2 지시·원문 메시지) 그대로 messages를 보내 답까지 붙은 대화를 돌려줍니다. 호출 기록은 usage에 더합니다."""
    context = SectionContext(document=state["document"], budget=rt.models.budget, documents=documents)
    model = rt.models.chat(name, max_output_tokens=max_output_tokens)
    agent = section._agent(model, name, state, documents, [section.StopAfterModel(), AnswerInText()])
    try:
        return agent.invoke({"messages": messages}, context=context)["messages"]
    finally:
        usage.extend(context.usage)


def _reply(messages: list[Any]) -> str | None:
    """마지막 답의 글. 답이 없거나 출력 한도에서 잘렸으면 None."""
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or cut_off(last):
        return None
    return last.text


def _json(text: str) -> Any:
    """답 글 → JSON 값. 코드 블록 표시·앞 설명은 건너뜁니다. 읽지 못하면 ValueError."""
    body = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = body.find("{")
    if start < 0:
        raise ValueError("JSON 객체가 없습니다")
    value, _ = json.JSONDecoder().raw_decode(body, start)
    return value
