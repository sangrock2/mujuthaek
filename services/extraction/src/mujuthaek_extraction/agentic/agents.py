"""총괄 에이전트와 하위(섹션) 에이전트의 도구.

총괄은 공고 전체를 맡아 무엇을 먼저 읽을지, 어느 하위 에이전트에 무엇을 맡길지, 다시 맡길지, 언제 끝낼지 정합니다.
하위 에이전트는 맡은 섹션(구조·일정·자격·선정·서류)의 초안을 채웁니다: 기존 섹션 추출기를 부르거나, 원문을 읽고 항목을 직접 넣고 고칩니다.
끝낼 때 총괄은 검증기가 낸 문제 중 원문으로 확인해 문제가 아니라고 본 것을 받아들이고(자동 게시), 확인이 필요한 곳을 보류로 지정합니다.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from mujuthaek_extraction import supply_tables
from mujuthaek_extraction.agentic.draft import COVERAGE, Draft, split_by_owner
from mujuthaek_extraction.agentic.loop import AgentLog, run_loop
from mujuthaek_extraction.extract import ExtractionRun, run_extraction
from mujuthaek_extraction.image_reading import BLOCK_HEAD, image_targets
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext
from mujuthaek_extraction.judgment.pages import PAGE_MARK
from mujuthaek_extraction.model.base import ExtractionModel, ModelRequest, ToolCall, ToolSpec, ToolTurn
from mujuthaek_extraction.repair.tools import RepairTools, _clean_quotes, _error, _object, _parse_item, _shrink, item_refs
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, call_schema, document_ids, structure_summary
from mujuthaek_extraction.verify import VerificationReport

log = logging.getLogger(__name__)

SUPERVISOR_TURNS = 16
WORKER_TURNS = 6  # 10 → 6(2026-11-05: 담당 차례 214번 중 항목을 고친 것은 5번, 나머지는 읽기만)
MAX_DELEGATIONS = 3  # 하위 에이전트 하나를 다시 맡길 수 있는 횟수(비용 상한)
OUTLINE_CHARS = 6_000
# 맡긴 담당이 돌려주는 요약 글자 상한(동시에 넷을 맡겨도 결과가 한 차례 입력으로 적당하게). 2026-11-05 2차 대역 시험: 700자에서
# 담당 요약(1,529자)의 「문제가 아니라고 본 것(근거)」「남은 것」이 잘려 총괄이 판단 근거를 못 받음 → 1,200자, 요약은 그 둘을 앞에
SUMMARY_CHARS = 1_200
WHOLE_RESULTS = frozenset({"outline", "delegate", "delegate_many", "extract_all"})  # 길어도 버리지 않고 그대로 돌려주는 도구 결과(크기는 만들 때 줄임)
# 에이전트 도구 결과 한 번의 글자 상한. 재확인 도구(2,000자)보다 크게(2026-11-05 대역 시험: 검증 문제 목록·추출 결과가 2,000자를 넘어
# 「결과가 너무 깁니다」 오류로 버려짐). 넘으면 긴 글 칸·긴 목록부터 줄이고 오류로 바꾸지 않습니다
RESULT_CHARS = 8_000
ISSUES_SHOWN = 25
# 차례 출력 한도 8,000 → 4,000(2026-11-05 점검): 실측 차례 출력은 100~1,000토큰인데, 공고당 상한은 차례마다 최악 비용(출력 한도 전부)을
# 잡아 두어 동시 담당 넷이면 실제 비용이 적어도 상한이 막혔음
TURN_OUTPUT_TOKENS = 4_000
SESSION_CHARS = 60_000  # 다시 맡긴 담당의 대화를 이어 갈 최대 길이(앞선 차례 글자). 넘으면 새 대화로
WHERE_ISSUES = 12  # 담당 첫 요청에서 원문 위치를 붙여 줄 문제 수
SECTION_HEAD = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\s*\.?|[■□◆◇▶])\s*\S.{0,58}$")
STRING, INTEGER = {"type": "string"}, {"type": "integer"}
QUOTES = {"type": "array", "items": _object({"ref": STRING, "text": STRING})}


SECTION_RULES = re.compile(r"^## 2-\d+\. .*\(`(\w+)`\)")
# 담당 섹션 → 공통 지시에서 남길 섹션 규칙(선정은 조건식·속성 사전이 자격 규칙에 있어 함께)
PROMPT_SECTIONS = {"selectionRules": ("selectionRules", "eligibility")}


def section_prompt(full: str, sections: tuple[str, ...]) -> str:
    """공통 지시에서 「2. 섹션별로 넣을 것」 중 맡은 섹션의 규칙만 남깁니다(원칙·근거 인용·값 작성·누락 규칙은 그대로).
    2026-11-05 점검: 담당·총괄 모두 공통 지시 전체(24,694자)를 받아 차례마다 그만큼 입력(자격 담당에 필요한 것은 약 9,100자)."""
    keep_sections = {k for s in sections for k in PROMPT_SECTIONS.get(s, (s,))}
    out, keep = [], True
    for line in full.split("\n"):
        match = SECTION_RULES.match(line)
        if match:
            keep = match.group(1) in keep_sections
        elif line.startswith("# "):
            keep = True
        if keep:
            out.append(line)
    return "\n".join(out)


def _turns(env_name: str, default: int) -> int:
    value = os.getenv(env_name, "")
    return max(2, int(value)) if value.strip().isdigit() else default


@dataclass
class Decision:
    accept: list[dict[str, str]] = field(default_factory=list)  # 받아들인 검증기 문제 (code, target, reason)
    hold: list[dict[str, str]] = field(default_factory=list)  # 총괄이 보류로 지정한 위치 (target, reason)
    note: str = ""


@dataclass
class Env:
    """공고 1건을 처리하는 동안 에이전트들이 함께 쓰는 상태입니다."""

    rules: FieldRules
    material: ExtractionMaterial
    context: TrustedContext
    model: ExtractionModel
    evaluate: Callable[[list[dict[str, Any]]], VerificationReport | None]
    read_images: Callable[[ExtractionMaterial, TrustedContext], tuple[ExtractionMaterial, TrustedContext, ExtractionRun | None]]
    # 기존 섹션 추출기를 주어진 호출들에 동시에(구조 요약이 있으면 구조 호출 없이). 지금 흐름과 같은 병렬 설정
    extract_all: Callable[[tuple[CallSpec, ...], dict[str, Any] | None], ExtractionRun]
    workers: dict[str, CallSpec]
    draft: Draft
    run: ExtractionRun = field(default_factory=ExtractionRun)
    logs: list[AgentLog] = field(default_factory=list)
    image_run: ExtractionRun | None = None
    decision: Decision | None = None
    decision_dropped: list[dict[str, Any]] = field(default_factory=list)  # 결정 중 근거가 확인되지 않아 버린 것(기록)
    delegations: dict[str, int] = field(default_factory=dict)
    stagger: float = 0.0  # 동시에 맡길 때 담당을 내보내는 간격(초, 설정 EXTRACTION_PARALLEL_STAGGER_SECONDS)
    progress: Callable[[], dict[str, Any]] = lambda: {}  # noqa: E731 — 도구 결과마다 붙일 진행 사실(쓴 비용·남은 상한·뽑아 둔 담당)
    # 담당 대화(요청 바탕, 쌓인 차례, 다음 차례 번호): 같은 담당을 다시 맡기면 이어 갑니다(새 대화는 공통 지시 캐시 쓰기를 다시 하고 읽은 것을 잃음)
    sessions: dict[str, tuple[ModelRequest, list[ToolTurn], int]] = field(default_factory=dict)
    # 코드가 주소마다 만든 위치: 담당에게 주는 구조 요약에서 뺍니다(지금 흐름과 같게, 큰 공고에서 수백 곳)
    hidden_locations: set[str] = field(default_factory=set)
    _reader: RepairTools | None = None

    @property
    def reader(self) -> RepairTools:
        if self._reader is None:
            self._reader = RepairTools(self.material, lambda item, quotes: [])
        return self._reader

    def replace_material(self, material: ExtractionMaterial, context: TrustedContext) -> None:
        self.material, self.context, self._reader = material, context, None
        self.draft.document_id = material.text_document_id

    def structure(self) -> dict[str, Any] | None:
        """구조 담당 조각들(공고·위치 조각 + 코드가 표에서 옮긴 공급 조각)을 합친 구조 요약. 뒤 담당이 scope ID로 씁니다."""
        owned = self.draft.parts.get(self.draft.owners.get("notice", ""), [])
        notice = next((p for p in owned if p.get("notice") is not None), None)
        if notice is None:
            return None
        groups = [g for p in owned for g in p.get("supplyGroups") or []]
        summary = structure_summary({**notice, "supplyGroups": groups})
        if summary and self.hidden_locations:
            summary["locations"] = [loc for loc in summary.get("locations") or [] if loc.get("id") not in self.hidden_locations]
        return summary

    def note_extraction(self, run: ExtractionRun) -> None:
        """추출기가 뒤 호출에 넘긴 구조 요약에 없는 위치(코드가 주소마다 만든 위치)를 기억해 담당 요약에서 뺍니다."""
        if run.structure is None:
            return
        shown = {loc.get("id") for loc in run.structure.get("locations") or []}
        self.hidden_locations |= {i for i in self.draft.structure_ids() if i not in shown} - {g for g in self._group_ids()}

    def _group_ids(self) -> set[str]:
        owned = self.draft.parts.get(self.draft.owners.get("supplyGroups", ""), [])
        return {g.get("id") for p in owned for g in p.get("supplyGroups") or [] if isinstance(g, dict)}


def fit(result: dict[str, Any], limit: int) -> str:
    """결과를 limit자 안의 JSON으로: 긴 글 칸을 줄이고, 그래도 길면 긴 목록 뒤를 잘라 truncated를 붙입니다. 오류로 바꾸지 않습니다
    (일이 이미 끝났는데 결과를 버리면 에이전트가 같은 일을 다시 함)."""
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= limit:
        return text
    shrunk = json.loads(text)
    for budget in (600, 300, 120):
        _shrink(shrunk, budget)
        text = json.dumps({**shrunk, "truncated": True}, ensure_ascii=False)
        if len(text) <= limit:
            return text
    while len(text) > limit and _cut_longest_list(shrunk):
        text = json.dumps({**shrunk, "truncated": True}, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit]


def _cut_longest_list(node: Any) -> bool:
    """가장 긴 목록의 뒤 절반을 잘라 냅니다. 자를 목록이 없으면 False."""
    lists: list[list[Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            lists.append(value)
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(node)
    longest = max((x for x in lists if len(x) > 1), key=lambda x: len(json.dumps(x, ensure_ascii=False)), default=None)
    if longest is None:
        return False
    del longest[(len(longest) + 1) // 2 :]
    return True


def _with_progress(text: str, progress: dict[str, Any]) -> str:
    """도구 결과에 진행 사실을 붙입니다. 순서를 정해 주지 않고, 쓴 비용·남은 상한·이미 뽑은 섹션을 보고 에이전트가 중복·낭비를 스스로 피하게 합니다."""
    if not progress:
        return text
    try:
        value = json.loads(text)
    except ValueError:
        return text
    return json.dumps({**value, "progress": progress}, ensure_ascii=False) if isinstance(value, dict) else text


def workers_of(rules: FieldRules) -> dict[str, CallSpec]:
    """하위 에이전트 = 섹션 호출(큰 공고용으로 나눈 호출을 늘 씀: 자격·선정·서류를 따로)."""
    split = dict(rules.split_calls)
    return {call.name: call for parent in rules.calls for call in split.get(parent.name, (parent,))}


# ── 함께 쓰는 읽기 도구 ───────────────────────────────────────────────────────────────────────────────


READ_SPECS = (
    ToolSpec("outline", "공고 원문의 차례: 문서·쪽 수, 절 제목(쪽), 공급·가격 표 후보(표 번호·열 제목·행 수), 글자 없는 그림 쪽.", _object({})),
    ToolSpec("search_source", "원문에서 낱말·숫자(2~60자)로 구간을 찾습니다. 공백·표 칸 구분(|)은 무시합니다.", _object({"query": STRING, "limit": INTEGER})),
    ToolSpec(
        "read_page",
        "원문 한 쪽을 읽습니다. from_char는 쪽 안 위치(search_source의 pageChar, 처음이면 0). 긴 쪽은 next_char로 이어 읽습니다.",
        _object({"page": INTEGER, "from_char": INTEGER}),
    ),
    ToolSpec(
        "read_table",
        "outline의 표 하나를 행 단위로 읽습니다(from_row부터 count행, 원문 줄 그대로).",
        _object({"table": STRING, "from_row": INTEGER, "count": INTEGER}),
    ),
    ToolSpec("check_quote", "인용문이 원문에 글자 그대로 있는지 확인합니다. 없으면 가장 비슷한 원문 줄을 보여 줍니다.", _object({"quote": STRING})),
)


READ_TOOLS = frozenset(spec.name for spec in READ_SPECS)


class Reading:
    env: Env

    def _outline(self) -> dict[str, Any]:
        text = self.env.material.text
        pages = PAGE_MARK.findall(text)
        headings, page = [], None
        for line in text.split("\n"):
            mark = PAGE_MARK.match(line)
            if mark:
                page = int(mark.group(1))
            elif SECTION_HEAD.match(line):
                headings.append(f"{page}쪽 {line.strip()}")
        tables = [
            {"table": t.label, "page": t.page, "columns": [c[:30] for c in t.columns[:10]], "rows": len(t.rows), "section": t.section[-60:]}
            for t in supply_tables.candidates(self.env.material)
        ]
        images = [f"{name} {number}쪽" for _, name, _, number in image_targets(self.env.material)]
        result = {
            "documents": [d.get("name") for d in self.env.context.documents],
            "pages": len(pages),
            "chars": len(text),
            "headings": headings[:80],
            "supplyTables": tables,
            "pictureOnlyPages": images,
            "picturesTranscribed": BLOCK_HEAD in text,
        }
        dumped = json.dumps(result, ensure_ascii=False)
        while len(dumped) > OUTLINE_CHARS and result["headings"]:
            result["headings"] = result["headings"][: len(result["headings"]) * 2 // 3]
            dumped = json.dumps({**result, "truncated": True}, ensure_ascii=False)
        return json.loads(dumped)

    def _search_source(self, query: str, limit: int) -> dict[str, Any]:
        return self.env.reader._search_source(query, limit)

    def _read_page(self, page: int, from_char: int) -> dict[str, Any]:
        return self.env.reader._read_page(page, from_char)

    def _check_quote(self, quote: str) -> dict[str, Any]:
        return self.env.reader._check_quote(quote)

    def _read_table(self, table: str, from_row: int, count: int) -> dict[str, Any]:
        found = next((t for t in supply_tables.candidates(self.env.material) if t.label == table), None)
        if found is None:
            return {"error": "NO_SUCH_TABLE", "message": "outline의 supplyTables에 있는 표 번호를 씁니다."}
        start, count = max(0, int(from_row or 0)), max(1, min(int(count or 20), 40))
        rows = [supply_tables._row_line(r) for r in found.rows[start : start + count]]
        return {"table": table, "columns": list(found.columns), "from_row": start, "rows": rows, "total": len(found.rows)}

    def run(self, call: ToolCall) -> str:
        handler = getattr(self, "_" + call.name, None)
        if call.name not in {s.name for s in self.specs} or handler is None:
            return _error("UNKNOWN_TOOL", f"없는 도구입니다: {call.name[:40]}")
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            return _error("BAD_ARGUMENTS", "도구 입력이 JSON이 아닙니다.")
        try:
            result = handler(**args) if isinstance(args, dict) else None
        except TypeError:
            return _error("BAD_ARGUMENTS", "도구 입력 칸이 맞지 않습니다.")
        except Exception as error:  # 도구 하나의 오류로 공고 처리 전체가 멈추지 않게(2026-11-05 점검: 숫자 칸에 글자가 오면 ValueError로 중단)
            log.warning("에이전트 도구 오류", extra={"tool": call.name, "error": f"{type(error).__name__}: {str(error)[:200]}"})
            return _error("TOOL_ERROR", f"도구를 실행하지 못했습니다({type(error).__name__}). 입력을 고쳐 다시 부릅니다.")
        if result is None:
            return _error("BAD_ARGUMENTS", "도구 입력은 객체여야 합니다.")
        # 차례·맡기기 결과는 「너무 길다」 오류로 바꾸지 않습니다: 맡긴 일은 이미 끝났고 비용도 들었는데 결과를 버리면 총괄이 같은 일을 다시 맡김
        # (2026-11-05 gh-809: 동시에 맡긴 담당 4개의 결과가 길어 버려지고 다시 맡겨 공고당 상한에 닿음). 길이는 결과를 만들 때 줄입니다
        text = json.dumps(result, ensure_ascii=False) if call.name in WHOLE_RESULTS else fit(result, RESULT_CHARS)
        # 진행 사실은 초안을 바꾸거나 검사하는 도구에만 붙입니다(읽기 결과마다 붙이면 같은 글이 차례에 여러 번 쌓임, 2026-11-05 대역 시험)
        return _with_progress(text, self.env.progress()) if call.name not in READ_TOOLS else text


def _issue_section(candidate: dict[str, Any], target: str) -> str | None:
    """문제 위치가 속한 섹션. 섹션 범위(/quality/coverage/섹션)·누락 기록(/quality/missingFields/n)도 그 섹션으로 봅니다
    (2026-11-05 점검: 담당이 「가격표 행이 어느 공급 묶음에도 없음」 같은 섹션 단위 문제를 못 봤음)."""
    parts = target.split(" ", 1)[0].lstrip("/").split("/")
    if parts[:2] == ["quality", "coverage"] and len(parts) >= 3:
        return parts[2]
    if parts[:2] == ["quality", "missingFields"] and len(parts) >= 3 and parts[2].isdigit():
        entries = candidate["quality"]["missingFields"]
        index = int(parts[2])
        return entries[index]["target"].lstrip("/").split("/", 1)[0] if index < len(entries) else None
    return parts[0] or None


def issues_view(report: VerificationReport | None, sections: tuple[str, ...] | None = None) -> dict[str, Any]:
    """검증기 결과를 에이전트가 볼 모양으로: 남은 문제(코드·위치·설명)와 검증기가 낼 상태. sections가 있으면 그 섹션 문제만."""
    if report is None:
        return {"assembled": False, "message": "결합하지 못했습니다: 공고 기본 정보(notice)가 없거나 근거가 없습니다."}
    quality = report.candidate["quality"]
    issues = [
        *quality["reviewIssues"],
        *({"code": f"CONTRACT_{e.split(' ', 1)[0]}", "target": e.partition(" ")[2].split(":")[0], "description": e} for e in report.contract_errors),
    ]
    if sections:
        issues = [i for i in issues if _issue_section(report.candidate, i["target"]) in sections]
    shown = [{"code": i["code"], "target": i["target"], "description": i["description"][:220]} for i in issues[:ISSUES_SHOWN]]
    by_section: dict[str, int] = {}
    for issue in issues:
        section = _issue_section(report.candidate, issue["target"]) or "notice"
        by_section[section] = by_section.get(section, 0) + 1
    return {
        "assembled": True,
        "verifierStatus": quality["verification"]["status"],
        # 섹션별 남은 문제 수(2026-11-05 대역 시험: 문제가 0개인 담당에게도 「처음 뽑기」를 맡겨 쪽 9개를 다 읽음 — 판단에 쓸 사실로 알림)
        "issuesBySection": by_section,
        "issues": shown,
        "issueCount": len(issues),
        "notes": len(quality["notes"]),
        "coverage": {k: v["status"] for k, v in quality["coverage"].items()},
    }


# ── 하위 에이전트 ─────────────────────────────────────────────────────────────────────────────────────

WORKER_INSTRUCTIONS = """# 할 일 (하위 에이전트)
「맡은 섹션」의 작업 초안을 원문에 맞게 고칩니다. 「남은 문제」는 지금 초안에 검증기를 돌린 결과입니다(다시 check하지 않아도 됩니다).
- upsert_item·remove_item·set_coverage: 원문을 읽고 항목을 직접 넣고·고치고·빼고, 섹션 상태를 정합니다. 문제 항목의 인용 위치부터 read_page로 읽습니다.
- extract_section: 맡은 섹션을 기존 추출기로 처음부터 다시 뽑습니다(초안의 이 섹션을 바꿈). 모델 호출 1번(약 $0.004, 40~60초).
- check: 고친 뒤 맡은 섹션에 남은 문제를 다시 봅니다.
- done: 끝냅니다. summary는 남은 것 → 원문으로 확인해 문제가 아니라고 본 것(근거 쪽·인용) → 고친 것 순서로 짧게 적습니다(길면 뒤가 잘림).
  총괄 에이전트가 이것을 읽고 다음을 정합니다.
- 차례마다 비용이 듭니다(읽기만 하는 차례 포함, 1번 약 $0.0004). 한 차례에 도구 여럿을 부를 수 있습니다(쪽 여러 개 읽기 등).
- 「남은 문제」의 where는 그 항목 근거가 원문 어디에 있는지(쪽·pageChar·앞뒤 글)입니다.

# 규칙
- 근거는 공고 원문뿐입니다. 원문에서 확인하지 못한 값은 만들지 않습니다.
- 항목은 공통 지시의 출력 형식 그대로(같은 칸 이름, 같은 id 규칙)이고, 근거는 quoteRefs로 가리킵니다. 인용문 글자는 upsert_item의 quotes(ref·text)에 적습니다.
- 인용은 원문에 글자 그대로 이어져 나오는 구간입니다. upsert_item이 인용을 확인해 원문에 없는 것만 돌려주므로, 넣기 전에 하나씩
  check_quote하지 않습니다(돌려받은 인용을 고칠 때 씁니다).
- upsert_item의 item_json은 고칠 때 바꿀 칸만 적어도 됩니다(같은 id의 나머지 칸은 그대로). 새 항목은 모든 칸을 적습니다.
- 「총괄 지시」가 있으면 그것을 먼저 합니다. 이미 초안이 있으면 처음부터 다시 뽑지 말고 필요한 곳만 고칩니다.
- 차례 수가 제한됩니다(도구 결과의 turnsLeft). 마지막 차례에는 done만 부를 수 있습니다."""


def _explain(error: Any, skip: int) -> str:
    """형식 오류를 「위치: 이유」로. 항목 전체 글자를 앞에 붙이지 않고, 여러 형식 중 하나·조건부 형식이면 가장 가까운 하위 오류를 씁니다
    (2026-11-05 대역 시험: 오류가 항목 글자로 시작해 160자에서 잘려 이유가 안 보이자, 담당이 선정 항목 종류를 SCORING에서 OTHER로 바꿔 통과시킴)."""
    leaf = best_match(error.context) if error.context else error
    path = "/".join(str(x) for x in list(leaf.absolute_path)[skip:])
    message = leaf.message
    shown = repr(leaf.instance)
    if len(shown) > 40 and message.startswith(shown):
        message = "이 값" + message[len(shown) :]
    return f"/{path}: {message[:240]}"


JUDGED_SECTIONS = ("notice", "eligibility")


class WorkerTools(Reading):
    finish_tool = "done"

    def __init__(self, env: Env, name: str):
        self.env, self.name, self.spec = env, name, env.workers[name]
        self.sections = self.spec.sections
        self.done = False
        self.result = ""
        section = {"enum": list(self.sections)}
        self.specs = (
            *(s for s in READ_SPECS if s.name != "outline"),  # 차례는 총괄이 봄(담당 첫 차례마다 outline을 불러 비용만 듦)
            ToolSpec("extract_section", "기존 섹션 추출기를 불러 맡은 섹션 전체를 초안에 넣습니다(초안의 이 섹션을 바꿈).", _object({})),
            ToolSpec(
                "upsert_item",
                "항목 하나를 넣거나 고칩니다. notice는 객체 하나입니다. quotes는 새로 쓴 인용(ref·text). quoteRefs는 있던 근거에 더해지고, "
                "틀린 근거를 바꿀 때만 replace_quote_refs를 true로 둡니다.",
                _object({"section": section, "item_json": STRING, "quotes": QUOTES, "replace_quote_refs": {"type": "boolean"}}),
            ),
            ToolSpec("remove_item", "항목 하나를 뺍니다(원문에 없거나 중복).", _object({"section": section, "item_id": STRING, "reason": STRING})),
            ToolSpec(
                "set_coverage",
                "섹션 상태: EXTRACTED 다 뽑음, PARTIAL 일부, NOT_IN_SOURCE 원문에 없음, NOT_APPLICABLE 해당 없음.",
                _object({"section": section, "status": {"enum": list(COVERAGE)}, "reason": STRING}),
            ),
            ToolSpec("check", "검증기를 돌려 맡은 섹션에 남은 문제를 봅니다.", _object({})),
            ToolSpec("done", "끝냅니다. summary에 남은 일, 문제가 아니라고 본 것(근거), 한 일 순서로 적습니다.", _object({"summary": STRING})),
        )

    def _extract_section(self) -> dict[str, Any]:
        structure = self.env.structure()
        if self.spec.uses_structure and structure is None:
            return {"error": "NO_STRUCTURE", "message": "구조(공고 기본 정보·위치·공급)가 아직 없습니다. 총괄에게 done으로 알립니다."}
        rules = dataclasses.replace(self.env.rules, calls=(self.spec,), split_calls=(), large_text_chars=None)
        run = run_extraction(rules, self.env.material, self.env.model, structure=structure if self.spec.uses_structure else None)
        self.env.run.attempts += run.attempts
        self.env.run.raw_responses += run.raw_responses
        self.env.run.failed_calls += run.failed_calls
        parts = [p for p in run.parts if isinstance(p, dict) and any(s in p for s in self.sections)]
        if not parts or run.failed_calls:
            return {"error": "EXTRACT_FAILED", "message": "; ".join(r for _, r in run.failed_calls)[:300] or "응답이 없습니다."}
        before = self.env.draft.structure_ids() if "notice" in self.sections else set()
        self.env.draft.put_parts(self.name, parts)  # 구조 추출은 공고·위치 조각과 코드가 표에서 옮긴 공급 조각 둘을 냄
        if "notice" in self.sections:
            self.env.note_extraction(run)
        result: dict[str, Any] = {"ok": True, "draft": self.env.draft.summary(self.sections)}
        gone = before - self.env.draft.structure_ids()
        dependents = self.env.draft.referencing(gone, self.name) if gone else []
        if dependents:  # 다시 뽑아 사라진 ID를 다른 섹션이 가리킴(2026-11-05 점검: 알리지 않으면 계약 정리로 그 항목들이 빠짐)
            result["removedIds"] = sorted(gone)[:20]
            result["dependentItems"] = dependents[:20]
            result["message"] = "다시 뽑아 위치·공급 ID가 바뀌었습니다. dependentItems는 사라진 ID를 가리킵니다(그 담당이 고쳐야 함)."
        return result

    def _upsert_item(self, section: str, item_json: str, quotes: list[dict[str, str]], replace_quote_refs: bool = False) -> dict[str, Any]:
        if section not in self.sections:
            return {"error": "NOT_MY_SECTION", "message": f"맡은 섹션은 {', '.join(self.sections)}입니다."}
        item = _parse_item(item_json)
        if isinstance(item, str):
            return {"error": "BAD_ITEM", "message": item}
        if section != "notice" and not isinstance(item.get("id"), str):
            return {"error": "BAD_ITEM", "message": "항목에는 id가 있어야 합니다."}
        missing = [q["text"][:60] for q in _clean_quotes(quotes) if not self.env.reader._check_quote(q["text"]).get("found")]
        if missing:
            return {"error": "QUOTE_NOT_FOUND", "message": "원문에 없는 인용이 있습니다. check_quote로 고칩니다.", "quotes": missing}
        merged = self.env.draft.preview(section, item, bool(replace_quote_refs))
        errors = self._format_errors(section, merged)
        if errors:  # 형식이 틀린 항목은 결합할 때 빠지므로 넣기 전에 돌려줍니다(2026-11-05 첫 실행: 손으로 넣은 공급 묶음이 모두 빠짐)
            return {"error": "BAD_FORMAT", "message": "공통 지시의 출력 형식에 맞지 않습니다.", "errors": errors}
        known = self.env.draft.quote_refs(section) | {q["ref"] for q in _clean_quotes(quotes)}
        dangling = [ref for ref in item_refs(merged) if ref not in known]
        if dangling:  # 없는 인용을 가리키면 결합할 때 근거 없음으로 빠집니다(2026-11-05 점검)
            message = "quoteRefs가 가리키는 인용이 없습니다. quotes에 그 ref의 원문을 함께 냅니다."
            return {"error": "UNKNOWN_QUOTE_REF", "message": message, "refs": dangling[:10]}
        return {"ok": self.env.draft.upsert(section, item, _clean_quotes(quotes), bool(replace_quote_refs))}

    def _format_errors(self, section: str, merged: dict[str, Any]) -> list[str]:
        """고친 결과(같은 id의 지금 항목에 합친 것)가 그 섹션 출력 형식에 맞는지. 틀린 곳 최대 5개."""
        part = {
            "quotes": [],
            section: merged if section == "notice" else [merged],
            "coverage": {section: {"status": "EXTRACTED", "reason": None}},
            "missingFields": [],
        }
        validator = Draft202012Validator(call_schema((section,), document_ids(self.env.material)))
        skip = 2 if section != "notice" else 1
        return [_explain(e, skip) for e in validator.iter_errors(part)][:5]

    def _remove_item(self, section: str, item_id: str, reason: str) -> dict[str, Any]:
        return {"removed": section in self.sections and self.env.draft.remove(section, item_id)}

    def _set_coverage(self, section: str, status: str, reason: str) -> dict[str, Any]:
        if section not in self.sections or status not in COVERAGE:
            return {"error": "BAD_ARGUMENTS", "message": "맡은 섹션과 정해진 상태만 씁니다."}
        if section in JUDGED_SECTIONS and status in ("NOT_IN_SOURCE", "NOT_APPLICABLE"):
            # 판정에 쓰는 섹션을 비우면 「조건 없음 = 누구나 지원 가능」이 될 수 있어(2026-11-05 점검) 에이전트는 비우지 못합니다
            return {"error": "NOT_ALLOWED", "message": f"{section}은 판정에 쓰여 비울 수 없습니다. 원문에 없으면 그대로 두고 총괄이 보류합니다."}
        self.env.draft.set_coverage(section, status, reason)
        return {"ok": True}

    def _check(self) -> dict[str, Any]:
        return issues_view(self.env.evaluate(self.env.draft.as_parts()), self.sections)

    def _done(self, summary: str) -> dict[str, Any]:
        self.done, self.result = True, summary.strip()[:1_500]
        return {"received": True}


def _where(env: Env, report: VerificationReport | None, target: str) -> dict[str, Any] | None:
    """문제 항목의 첫 근거가 원문 어디에 있는지(쪽·쪽 안 위치·앞뒤 글). 담당이 찾는 차례를 쓰지 않게 코드가 미리 찾습니다(#17 locate와 같은 방식)."""
    if report is None:
        return None
    parts = target.split(" ", 1)[0].lstrip("/").split("/")
    candidate = report.candidate
    if len(parts) < 2 or parts[0] not in candidate or not parts[1].isdigit():
        return None
    items = candidate[parts[0]]
    index = int(parts[1])
    if not isinstance(items, list) or index >= len(items):
        return None
    ids = items[index].get("evidenceIds") or []
    evidence = next((e for e in candidate.get("evidence") or [] if e["id"] in ids and e["locator"]["kind"] == "TEXT_RANGE"), None)
    if evidence is None:
        return None
    return env.reader._hit(evidence["locator"]["start"], evidence["locator"]["end"])


def _worker_context(env: Env, sections: tuple[str, ...], brief: str) -> dict[str, Any]:
    report = env.evaluate(env.draft.as_parts())
    issues = issues_view(report, sections).get("issues", [])
    for issue in issues[:WHERE_ISSUES]:
        where = _where(env, report, issue["target"])
        if where:
            issue["where"] = where
    return {
        "맡은 섹션": list(sections),
        "총괄 지시": brief,
        "남은 문제": issues,  # 첫 차례를 check·찾기에 쓰지 않게 코드가 미리(문제 항목의 근거 위치 포함)
        "지금 초안": env.draft.summary(sections),
        "이미 추출한 구조 (scope·locationId에는 이 ID만 사용)": env.structure(),
    }


def run_worker(env: Env, name: str, brief: str) -> dict[str, Any]:
    tools = WorkerTools(env, name)
    log = AgentLog(f"worker:{name}")
    env.logs.append(log)
    context = _worker_context(env, tools.sections, brief)
    session = env.sessions.get(name)
    if session is not None and session[1] and sum(len(r) for t in session[1] for r in t.results) < SESSION_CHARS:
        # 같은 담당을 다시 맡김: 앞선 대화에 새 지시를 덧붙여 이어 갑니다(공통 지시 캐시를 다시 쓰지 않고, 앞서 읽은 것을 기억)
        base, previous, first = session
        note = "# 다시 맡김\n" + json.dumps(context, ensure_ascii=False, indent=1)
        turns = [*previous[:-1], ToolTurn(previous[-1].calls, previous[-1].results, note)] if previous else []
    else:
        base = ModelRequest(
            prompt_version=f"{env.rules.field}/{env.rules.prompt_version}/agentic-worker",
            call_name=f"agentic:{name}",
            system=section_prompt(env.rules.system_prompt(), tools.sections),
            user=json.dumps(context, ensure_ascii=False, indent=1),
            instructions=WORKER_INSTRUCTIONS,
            output_schema=call_schema(tools.sections, document_ids(env.material)),
            max_output_tokens=TURN_OUTPUT_TOKENS,
            parallel_tools=True,
        )
        turns, first = [], 1
    turns = run_loop(env.model, base, tools, _turns("EXTRACTION_AGENTIC_WORKER_TURNS", WORKER_TURNS), env.run, log, turns=turns, first=first)
    env.sessions[name] = (base, turns, first + log.turns)
    counts = {k: v["count"] if isinstance(v, dict) and "count" in v else v for k, v in env.draft.summary(tools.sections).items()}
    return {"worker": name, "outcome": log.outcome, "turns": log.turns, "summary": _cut(tools.result, SUMMARY_CHARS), "draft": counts}


def _cut(text: str, limit: int) -> str:
    """길면 자르고 잘렸다고 적습니다(잘린 줄 모르면 총괄이 요약을 다 받은 줄 앎)."""
    return text if len(text) <= limit else text[: limit - 6] + "…(줄임)"


# ── 총괄 에이전트 ─────────────────────────────────────────────────────────────────────────────────────

SUPERVISOR_INSTRUCTIONS = """# 할 일 (총괄 에이전트)
공고 하나의 추출을 맡습니다. 결과는 작업 초안이고, finish로 끝내면 그대로 게시 준비가 됩니다. 순서·방법은 스스로 정합니다.
- 「원문 차례」(outline 결과)는 처음 요청에 있습니다. 필요하면 search_source·read_page·read_table로 더 읽습니다.
- extract_all: 기존 섹션 추출기를 모든 섹션에 동시에 돌려 초안을 채웁니다(초안을 바꿈). 모델 호출 3~5번을 동시에(약 $0.02, 1~2분).
- 그림 쪽(pictureOnlyPages)의 글자는 read_images를 하기 전에는 원문에 없습니다(약 $0.004, 20~40초).
- 비용·시간 참고: 담당을 처음 부를 때 약 $0.002, 그 뒤 담당·총괄 차례 1번 약 $0.0004·5~15초. 공고당 비용 상한이 있습니다.
  한 차례에 도구 여럿을 부를 수 있습니다. 같은 담당을 다시 맡기면 그 담당의 앞선 대화를 이어 갑니다.
- read_images: 글자 없는 그림 쪽(가격표 등이 그림인 경우)의 글자를 옮겨 원문 끝에 붙입니다. outline의 pictureOnlyPages가 있을 때 판단해서 씁니다.
- delegate: 하위 에이전트(섹션 담당)에 일을 맡깁니다. brief에 무엇을 할지(처음 뽑기, 특정 문제 고치기, 빠진 표 행 더하기 등) 구체적으로 적습니다.
  구조 담당(notice·위치·공급)이 먼저여야 다른 담당이 그 ID를 씁니다. 같은 담당은 최대 3번까지 맡길 수 있습니다.
- delegate_many: 서로 기대지 않는 담당 여럿을 동시에 맡깁니다(하나씩 맡길 때보다 시간이 줄어듦).
- check_all: 초안 전체에 검증기를 돌려 남은 문제를 봅니다.
- finish: 끝냅니다. 검증기 문제 중 원문으로 확인해 문제가 아니라고 판단한 것은 accept에(code·target을 check_all 결과 그대로, reason에 판단,
  quote에 확인한 원문 구간 그대로 — 프로그램이 원문에 있는지·값 문제면 그 값이 quote에 있는지 확인하고, 맞지 않으면 한 번 돌려보냄),
  확인이 필요한 곳은 hold에 적습니다. accept한 값은 사람 확인 없이 게시되므로 원문으로 확인한 것만 넣습니다. 남긴 문제는 그 범위만 보류됩니다.
  IMAGE_READING_DISAGREES(그림을 두 번 읽은 글자가 다름)는 원문 그림과 맞춰야 해서 받아들일 수 없습니다.

# 규칙
- 근거는 공고 원문뿐입니다. 서비스 목표는 「게시된 값 중 틀린 값 0」이고, 누락은 보류·검수로 보내는 편이 틀린 값보다 낫습니다.
- 차례 수와 비용이 제한됩니다(도구 결과의 turnsLeft). 마지막 차례에는 finish만 부를 수 있습니다."""


class SupervisorTools(Reading):
    finish_tool = "finish"

    def __init__(self, env: Env):
        self.env = env
        self.done = False
        self.final = False  # 마지막 차례(run_loop가 알려 줌): 결정 오류를 돌려보내지 않고 맞는 것만 받습니다
        self.returned = False  # 결정 오류를 한 번 돌려보냈는지
        target = _object({"code": STRING, "target": STRING, "reason": STRING, "quote": STRING})
        self.specs = (
            *READ_SPECS,
            ToolSpec("extract_all", "기존 섹션 추출기를 모든 섹션에 동시에 돌려 초안을 채웁니다(초안을 바꿈).", _object({})),
            ToolSpec("read_images", "글자 없는 그림 쪽을 그림으로 읽어 글자를 원문 끝에 붙입니다(한 번만).", _object({})),
            ToolSpec(
                "delegate", "하위 에이전트에 일을 맡기고 결과(요약·초안 상태)를 받습니다.", _object({"worker": {"enum": list(env.workers)}, "brief": STRING})
            ),
            ToolSpec(
                "delegate_many",
                "서로 기대지 않는 담당 여럿에 동시에 일을 맡깁니다(구조가 생긴 뒤 일정·자격·선정·서류처럼). 결과는 담당마다 delegate와 같습니다.",
                _object({"tasks": {"type": "array", "items": _object({"worker": {"enum": list(env.workers)}, "brief": STRING})}}),
            ),
            ToolSpec("check_all", "초안 전체에 검증기를 돌려 남은 문제와 검증기가 낼 상태를 봅니다.", _object({})),
            ToolSpec(
                "finish",
                "끝냅니다. accept: 받아들인 검증기 문제(code·target·reason·quote — quote는 확인한 원문 구간 그대로), hold: 보류할 위치(target·reason).",
                _object(
                    {
                        "accept": {"type": "array", "items": target},
                        "hold": {"type": "array", "items": _object({"target": STRING, "reason": STRING})},
                        "note": STRING,
                    }
                ),
            ),
        )

    def _read_images(self) -> dict[str, Any]:
        if self.env.image_run is not None or BLOCK_HEAD in self.env.material.text:
            return {"error": "ALREADY_READ", "message": "그림은 이미 읽었습니다."}
        material, context, image_run = self.env.read_images(self.env.material, self.env.context)
        self.env.image_run = image_run or ExtractionRun()
        if material is self.env.material:
            return {"ok": False, "message": "옮긴 글자가 없습니다(그림 쪽이 없거나 판독 실패)."}
        before = len(self.env.material.text)
        self.env.replace_material(material, context)
        return {"ok": True, "addedChars": len(material.text) - before, "supplyTables": self._outline()["supplyTables"]}

    def _delegate(self, worker: str, brief: str) -> dict[str, Any]:
        if worker not in self.env.workers:
            return {"error": "NO_SUCH_WORKER", "message": f"하위 에이전트는 {', '.join(self.env.workers)}입니다."}
        used = self.env.delegations.get(worker, 0)
        if used >= MAX_DELEGATIONS:
            return {"error": "DELEGATION_LIMIT", "message": f"{worker}는 이미 {used}번 맡겼습니다."}
        self.env.delegations[worker] = used + 1
        return run_worker(self.env, worker, brief)

    def _delegate_many(self, tasks: list[dict[str, str]]) -> dict[str, Any]:
        """서로 기대지 않는 담당 여럿을 동시에 돌립니다(2026-11-05 첫 비교: 하나씩 맡겨 공고당 약 7분, 기존 방식의 2~3배).
        담당마다 초안 조각이 따로라 서로 덮어쓰지 않습니다. 구조를 쓰는 담당은 구조가 있어야 합니다."""
        tasks = [t for t in tasks or [] if isinstance(t, dict)]
        unknown = [t.get("worker") for t in tasks if t.get("worker") not in self.env.workers]
        if not tasks or unknown or len({t["worker"] for t in tasks}) < len(tasks):
            return {"error": "BAD_TASKS", "message": f"담당은 {', '.join(self.env.workers)} 중에서 한 번씩만 적습니다."}
        if self.env.structure() is None and any(self.env.workers[t["worker"]].uses_structure for t in tasks):
            return {"error": "NO_STRUCTURE", "message": "구조 담당을 먼저 delegate로 맡깁니다."}
        over = [t["worker"] for t in tasks if self.env.delegations.get(t["worker"], 0) >= MAX_DELEGATIONS]
        if over:
            return {"error": "DELEGATION_LIMIT", "message": f"이미 {MAX_DELEGATIONS}번 맡긴 담당: {', '.join(over)}"}
        for t in tasks:
            self.env.delegations[t["worker"]] = self.env.delegations.get(t["worker"], 0) + 1
        with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="agentic-worker") as pool:
            futures = []
            for index, task in enumerate(tasks):
                if index and self.env.stagger > 0:
                    time.sleep(self.env.stagger)  # 같은 앞부분(공통 지시) 캐시를 첫 담당이 쓴 뒤 읽게 간격을 둡니다(extract 병렬 호출과 같은 이유)
                futures.append(pool.submit(run_worker, self.env, task["worker"], str(task.get("brief") or "")))
            return {"results": [f.result() for f in futures]}

    def _extract_all(self) -> dict[str, Any]:
        # 이미 초안에 있는 섹션의 호출은 건너뜁니다(2026-11-05 jbdc: 담당이 각자 뽑은 뒤 또 불러 구조 3번·나머지 2번씩 같은 추출)
        calls = self.env.rules.calls_for(self.env.material)
        filled = self.env.draft.filled()
        missing = tuple(c for c in calls if not all(self.env.draft.owners.get(s) in filled for s in c.sections))
        skipped = [c.name for c in calls if c not in missing]
        if not missing:
            return {"skipped": skipped, "message": "모든 섹션이 이미 초안에 있습니다. 다시 뽑으려면 그 담당의 extract_section을 씁니다."}
        structure = None if missing[0] is calls[0] else self.env.structure()
        if structure is None and missing[0] is not calls[0]:
            missing = (calls[0], *missing)  # 구조가 없으면 구조부터(뒤 호출이 그 ID를 씀)
        run = self.env.extract_all(missing, structure)
        self.env.run.attempts += run.attempts
        self.env.run.raw_responses += run.raw_responses
        self.env.run.failed_calls += run.failed_calls
        owned: dict[str, list[dict[str, Any]]] = {}
        for part in run.parts:  # 조각마다 그 섹션 담당에게(구조 추출의 공급 조각은 구조 담당, 여러 담당 섹션을 함께 담은 조각은 나눔)
            if isinstance(part, dict):
                for owner, piece in split_by_owner(part, self.env.draft.owners).items():
                    owned.setdefault(owner, []).append(piece)
        for owner, parts in owned.items():
            if owner not in filled:  # 합쳐진 호출을 다시 돌려도 이미 있던 담당 몫(담당이 고친 것)은 덮어쓰지 않습니다(2026-11-05 점검)
                self.env.draft.put_parts(owner, parts)
        self.env.note_extraction(run)  # 초안에 넣은 뒤(코드가 만든 위치를 초안에서 찾음)
        failed = [f"{name}: {reason[:120]}" for name, reason in run.failed_calls]
        view = issues_view(self.env.evaluate(self.env.draft.as_parts()))
        return {
            "extracted": [c.name for c in missing],
            "skipped": skipped,
            "failedCalls": failed,
            "draft": self.env.draft.counts(),
            "verifierStatus": view.get("verifierStatus"),
            "issuesBySection": view.get("issuesBySection", {}),
        }

    def _check_all(self) -> dict[str, Any]:
        return issues_view(self.env.evaluate(self.env.draft.as_parts()))

    def _finish(self, accept: list[dict[str, str]], hold: list[dict[str, str]], note: str) -> dict[str, Any]:
        def clean(rows: Any, keys: tuple[str, ...]) -> list[dict[str, str]]:
            return [{k: str(r.get(k, ""))[:300] for k in keys} for r in rows or [] if isinstance(r, dict)]

        accept, hold = clean(accept, ("code", "target", "reason", "quote")), clean(hold, ("target", "reason"))
        problems = decision_problems(self.env, accept, hold)
        if problems and not self.returned and not self.final:
            # 결정 오류를 조용히 버리지 않고 한 번 돌려보내 고치게 합니다(2026-11-05 점검, 재확인 submit_fix 되돌리기와 같은 방식)
            self.returned = True
            return {"received": False, "error": "DECISION_PROBLEMS", "problems": problems[:15], "message": "고쳐서 다시 finish합니다(맞는 것만 남겨도 됨)."}
        bad_accepts = {p["index"] for p in problems if p["kind"] == "accept"}
        bad_holds = {p["index"] for p in problems if p["kind"] == "hold"}
        self.env.decision = Decision(
            [a for i, a in enumerate(accept) if i not in bad_accepts], [h for i, h in enumerate(hold) if i not in bad_holds], (note or "")[:1_000]
        )
        self.env.decision_dropped = problems
        self.done = True
        return {"received": True, **({"dropped": len(problems)} if problems else {})}


# 받아들이기에 값이 그 인용에 있는지까지 확인하는 문제(값–근거 대조 문제)
VALUE_CODES = frozenset({"VALUE_NOT_IN_QUOTE", "VALUE_POSITION_SUSPECTED", "CLAIM_UNSUPPORTED"})
DIGITS = re.compile(r"\d")


def decision_problems(env: Env, accept: list[dict[str, str]], hold: list[dict[str, str]]) -> list[dict[str, Any]]:
    """총괄 결정의 잘못: 지금 없는 문제·받아들일 수 없는 문제·원문에 없는 인용·인용에 없는 값(받아들이기), 보류할 수 없는 위치(보류).
    받아들이기는 공개 판단을 에이전트에게 맡기되(사용자 결정 2026-11-05), 근거가 확인된 것만 받습니다."""
    from mujuthaek_extraction.agentic.engine import UNACCEPTABLE, _pointer  # engine이 이 모듈을 가져다 써서 실행할 때 가져옵니다
    from mujuthaek_extraction.contracts import tools as contract_tools

    report = env.evaluate(env.draft.as_parts())
    if report is None:
        return []
    candidate = report.candidate
    current = {(i["code"], i["target"]) for i in candidate["quality"]["reviewIssues"]}
    problems: list[dict[str, Any]] = []
    for index, row in enumerate(accept):
        code, target, quote = row["code"], row["target"], row.get("quote", "").strip()
        reason = None
        if (code, target) not in current:
            reason = "check_all 결과에 없는 문제입니다(code·target을 그대로 적습니다)."
        elif code in UNACCEPTABLE:
            reason = "원문 그림과 맞춰야 하는 문제라 받아들일 수 없습니다."
        elif not quote or not env.reader._check_quote(quote).get("found"):
            reason = "quote가 원문에 글자 그대로 있어야 합니다(check_quote로 확인)."
        elif code in VALUE_CODES:
            try:
                value = contract_tools().resolve(candidate, target)
            except (KeyError, IndexError, TypeError, ValueError):
                value = None
            digits = "".join(DIGITS.findall(str(value))) if isinstance(value, int | float) else ""
            if digits and digits not in "".join(DIGITS.findall(quote)):
                reason = f"값 {value}이(가) quote에 없습니다. 그 값이 적힌 원문 구간을 quote로 냅니다."
        if reason:
            problems.append({"kind": "accept", "index": index, "code": code, "target": target, "message": reason})
    for index, row in enumerate(hold):
        if _pointer(candidate, row["target"]) is None:
            problems.append(
                {"kind": "hold", "index": index, "target": row["target"], "message": "보류할 수 있는 위치가 아닙니다(예: /eligibility/3, /supplyGroups)."}
            )
    return problems


def run_supervisor(env: Env) -> None:
    tools = SupervisorTools(env)
    log = AgentLog("supervisor")
    env.logs.append(log)
    context = {
        "하위 에이전트": {name: list(spec.sections) for name, spec in env.workers.items()},
        "원문 차례": tools._outline(),  # 첫 차례를 outline에 쓰지 않게 코드가 미리
        "지금 초안": env.draft.summary(),
    }
    base = ModelRequest(
        prompt_version=f"{env.rules.field}/{env.rules.prompt_version}/agentic-supervisor",
        call_name="agentic:supervisor",
        system=section_prompt(env.rules.system_prompt(), ()),  # 총괄은 항목을 쓰지 않아 섹션 규칙을 뺌
        user=json.dumps(context, ensure_ascii=False, indent=1),
        instructions=SUPERVISOR_INSTRUCTIONS,
        output_schema=call_schema(("notice",), document_ids(env.material)),  # 도구 요청이라 쓰이지 않음(요청 형식상 필요)
        max_output_tokens=TURN_OUTPUT_TOKENS,
        parallel_tools=True,
    )
    run_loop(env.model, base, tools, _turns("EXTRACTION_AGENTIC_SUPERVISOR_TURNS", SUPERVISOR_TURNS), env.run, log)
