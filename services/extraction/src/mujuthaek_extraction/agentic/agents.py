"""총괄 에이전트와 하위(섹션) 에이전트의 도구.

총괄은 공고 전체를 맡아 무엇을 먼저 읽을지, 어느 하위 에이전트에 무엇을 맡길지, 다시 맡길지, 언제 끝낼지 정합니다.
하위 에이전트는 맡은 섹션(구조·일정·자격·선정·서류)의 초안을 채웁니다: 기존 섹션 추출기를 부르거나, 원문을 읽고 항목을 직접 넣고 고칩니다.
끝낼 때 총괄은 검증기가 낸 문제 중 원문으로 확인해 문제가 아니라고 본 것을 받아들이고(자동 게시), 확인이 필요한 곳을 보류로 지정합니다.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from mujuthaek_extraction import supply_tables
from mujuthaek_extraction.agentic.draft import COVERAGE, Draft
from mujuthaek_extraction.agentic.loop import AgentLog, run_loop
from mujuthaek_extraction.extract import ExtractionRun, run_extraction
from mujuthaek_extraction.image_reading import BLOCK_HEAD, image_targets
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext
from mujuthaek_extraction.judgment.pages import PAGE_MARK
from mujuthaek_extraction.model.base import ExtractionModel, ModelRequest, ToolCall, ToolSpec
from mujuthaek_extraction.repair.tools import RepairTools, _clean_quotes, _error, _limit, _merge, _object, _parse_item
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, call_schema, document_ids, structure_summary
from mujuthaek_extraction.verify import VerificationReport

SUPERVISOR_TURNS = 16
WORKER_TURNS = 10
MAX_DELEGATIONS = 3  # 하위 에이전트 하나를 다시 맡길 수 있는 횟수(비용 상한)
OUTLINE_CHARS = 6_000
ISSUES_SHOWN = 25
TURN_OUTPUT_TOKENS = 8_000
SECTION_HEAD = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\s*\.?|[■□◆◇▶])\s*\S.{0,58}$")
STRING, INTEGER = {"type": "string"}, {"type": "integer"}
QUOTES = {"type": "array", "items": _object({"ref": STRING, "text": STRING})}


def turns(env_name: str, default: int) -> int:
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
    workers: dict[str, CallSpec]
    draft: Draft
    run: ExtractionRun = field(default_factory=ExtractionRun)
    logs: list[AgentLog] = field(default_factory=list)
    image_run: ExtractionRun | None = None
    decision: Decision | None = None
    delegations: dict[str, int] = field(default_factory=dict)
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
        return structure_summary({**notice, "supplyGroups": groups})


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
        if result is None:
            return _error("BAD_ARGUMENTS", "도구 입력은 객체여야 합니다.")
        return json.dumps(result, ensure_ascii=False) if call.name == "outline" else _limit(result)


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
        issues = [i for i in issues if any(i["target"].startswith(f"/{s}") for s in sections)]
    shown = [{"code": i["code"], "target": i["target"], "description": i["description"][:220]} for i in issues[:ISSUES_SHOWN]]
    return {
        "assembled": True,
        "verifierStatus": quality["verification"]["status"],
        "issues": shown,
        "issueCount": len(issues),
        "notes": len(quality["notes"]),
        "coverage": {k: v["status"] for k, v in quality["coverage"].items()},
    }


# ── 하위 에이전트 ─────────────────────────────────────────────────────────────────────────────────────

WORKER_INSTRUCTIONS = """# 할 일 (하위 에이전트)
「맡은 섹션」의 작업 초안을 원문에 맞게 채웁니다. 방법은 스스로 고릅니다.
- extract_section: 기존 섹션 추출기를 한 번 불러 맡은 섹션 전체를 초안에 넣습니다(대량으로 뽑을 때 빠르고 쌈). 공급표 후보가 있으면 표 행은 코드가 옮깁니다.
- upsert_item·remove_item·set_coverage: 원문을 읽고 항목을 직접 넣고·고치고·빼고, 섹션 상태를 정합니다.
- check: 검증기를 돌려 맡은 섹션에 남은 문제를 봅니다. 문제를 보고 고치거나, 원문으로 확인해 문제가 아니면 그대로 둡니다.
- done: 끝냅니다. summary에 무엇을 했고 무엇이 남았는지(원문으로 확인한 내용 포함) 적습니다. 총괄 에이전트가 이것을 읽고 다음을 정합니다.

# 규칙
- 근거는 공고 원문뿐입니다. 원문에서 확인하지 못한 값은 만들지 않습니다.
- 항목은 공통 지시의 출력 형식 그대로(같은 칸 이름, 같은 id 규칙)이고, 근거는 quoteRefs로 가리킵니다. 인용문 글자는 upsert_item의 quotes(ref·text)에 적습니다.
- 인용은 원문에 글자 그대로 이어져 나오는 구간입니다. 넣기 전에 check_quote로 확인합니다.
- upsert_item의 item_json은 고칠 때 바꿀 칸만 적어도 됩니다(같은 id의 나머지 칸은 그대로). 새 항목은 모든 칸을 적습니다.
- 「총괄 지시」가 있으면 그것을 먼저 합니다. 이미 초안이 있으면 처음부터 다시 뽑지 말고 필요한 곳만 고칩니다.
- 차례 수가 제한됩니다(도구 결과의 turnsLeft). 마지막 차례에는 done만 부를 수 있습니다."""


class WorkerTools(Reading):
    finish_tool = "done"

    def __init__(self, env: Env, name: str):
        self.env, self.name, self.spec = env, name, env.workers[name]
        self.sections = self.spec.sections
        self.done = False
        self.result = ""
        section = {"enum": list(self.sections)}
        self.specs = (
            *READ_SPECS,
            ToolSpec("extract_section", "기존 섹션 추출기를 불러 맡은 섹션 전체를 초안에 넣습니다(초안의 이 섹션을 바꿈).", _object({})),
            ToolSpec(
                "upsert_item",
                "항목 하나를 넣거나 고칩니다. notice는 객체 하나입니다. quotes는 새로 쓴 인용(ref·text).",
                _object({"section": section, "item_json": STRING, "quotes": QUOTES}),
            ),
            ToolSpec("remove_item", "항목 하나를 뺍니다(원문에 없거나 중복).", _object({"section": section, "item_id": STRING, "reason": STRING})),
            ToolSpec(
                "set_coverage",
                "섹션 상태: EXTRACTED 다 뽑음, PARTIAL 일부, NOT_IN_SOURCE 원문에 없음, NOT_APPLICABLE 해당 없음.",
                _object({"section": section, "status": {"enum": list(COVERAGE)}, "reason": STRING}),
            ),
            ToolSpec("check", "검증기를 돌려 맡은 섹션에 남은 문제를 봅니다.", _object({})),
            ToolSpec("done", "끝냅니다. summary에 한 일과 남은 일을 적습니다.", _object({"summary": STRING})),
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
        self.env.draft.put_parts(self.name, parts)  # 구조 추출은 공고·위치 조각과 코드가 표에서 옮긴 공급 조각 둘을 냄
        return {"ok": True, "draft": self.env.draft.summary(self.sections)}

    def _upsert_item(self, section: str, item_json: str, quotes: list[dict[str, str]]) -> dict[str, Any]:
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
        errors = self._format_errors(section, item)
        if errors:  # 형식이 틀린 항목은 결합할 때 빠지므로 넣기 전에 돌려줍니다(2026-11-05 첫 실행: 손으로 넣은 공급 묶음이 모두 빠짐)
            return {"error": "BAD_FORMAT", "message": "공통 지시의 출력 형식에 맞지 않습니다.", "errors": errors}
        return {"ok": self.env.draft.upsert(section, item, _clean_quotes(quotes))}

    def _format_errors(self, section: str, item: dict[str, Any]) -> list[str]:
        """고친 결과(같은 id의 지금 항목에 합친 것)가 그 섹션 출력 형식에 맞는지. 틀린 곳 최대 5개."""
        current = self.env.draft.item(section, None if section == "notice" else item.get("id"))
        merged = _merge(current, item) if isinstance(current, dict) else item
        part = {
            "quotes": [],
            section: merged if section == "notice" else [merged],
            "coverage": {section: {"status": "EXTRACTED", "reason": None}},
            "missingFields": [],
        }
        validator = Draft202012Validator(call_schema((section,), document_ids(self.env.material)))
        return [
            f"/{'/'.join(str(x) for x in list(e.absolute_path)[2 if section != 'notice' else 1 :])}: {e.message[:160]}" for e in validator.iter_errors(part)
        ][:5]

    def _remove_item(self, section: str, item_id: str, reason: str) -> dict[str, Any]:
        return {"removed": section in self.sections and self.env.draft.remove(section, item_id)}

    def _set_coverage(self, section: str, status: str, reason: str) -> dict[str, Any]:
        if section not in self.sections or status not in COVERAGE:
            return {"error": "BAD_ARGUMENTS", "message": "맡은 섹션과 정해진 상태만 씁니다."}
        self.env.draft.set_coverage(section, status, reason)
        return {"ok": True}

    def _check(self) -> dict[str, Any]:
        return issues_view(self.env.evaluate(self.env.draft.as_parts()), self.sections)

    def _done(self, summary: str) -> dict[str, Any]:
        self.done, self.result = True, summary.strip()[:1_500]
        return {"received": True}


def run_worker(env: Env, name: str, brief: str) -> dict[str, Any]:
    tools = WorkerTools(env, name)
    log = AgentLog(f"worker:{name}")
    env.logs.append(log)
    context = {
        "맡은 섹션": list(tools.sections),
        "총괄 지시": brief,
        "지금 초안": env.draft.summary(tools.sections),
        "이미 추출한 구조 (scope·locationId에는 이 ID만 사용)": env.structure(),
    }
    base = ModelRequest(
        prompt_version=f"{env.rules.field}/{env.rules.prompt_version}/agentic-worker",
        call_name=f"agentic:{name}",
        system=env.rules.system_prompt(),
        user=json.dumps(context, ensure_ascii=False, indent=1),
        instructions=WORKER_INSTRUCTIONS,
        output_schema=call_schema(tools.sections, document_ids(env.material)),
        max_output_tokens=TURN_OUTPUT_TOKENS,
    )
    run_loop(env.model, base, tools, turns("EXTRACTION_AGENTIC_WORKER_TURNS", WORKER_TURNS), env.run, log)
    return {"worker": name, "outcome": log.outcome, "turns": log.turns, "summary": tools.result, "draft": env.draft.summary(tools.sections)}


# ── 총괄 에이전트 ─────────────────────────────────────────────────────────────────────────────────────

SUPERVISOR_INSTRUCTIONS = """# 할 일 (총괄 에이전트)
공고 하나의 추출을 맡습니다. 결과는 작업 초안이고, finish로 끝내면 그대로 게시 준비가 됩니다. 순서·방법은 스스로 정합니다.
- outline·search_source·read_page·read_table로 공고를 파악합니다.
- read_images: 글자 없는 그림 쪽(가격표 등이 그림인 경우)의 글자를 옮겨 원문 끝에 붙입니다. outline의 pictureOnlyPages가 있을 때 판단해서 씁니다.
- delegate: 하위 에이전트(섹션 담당)에 일을 맡깁니다. brief에 무엇을 할지(처음 뽑기, 특정 문제 고치기, 빠진 표 행 더하기 등) 구체적으로 적습니다.
  구조 담당(notice·위치·공급)이 먼저여야 다른 담당이 그 ID를 씁니다. 같은 담당은 최대 3번까지 맡길 수 있습니다.
- check_all: 초안 전체에 검증기를 돌려 남은 문제를 봅니다.
- finish: 끝냅니다. 검증기 문제 중 원문으로 확인해 문제가 아니라고 판단한 것은 accept에(code·target을 check_all 결과 그대로, reason에 확인한 근거),
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
        target = _object({"code": STRING, "target": STRING, "reason": STRING})
        self.specs = (
            *READ_SPECS,
            ToolSpec("read_images", "글자 없는 그림 쪽을 그림으로 읽어 글자를 원문 끝에 붙입니다(한 번만).", _object({})),
            ToolSpec(
                "delegate", "하위 에이전트에 일을 맡기고 결과(요약·초안 상태)를 받습니다.", _object({"worker": {"enum": list(env.workers)}, "brief": STRING})
            ),
            ToolSpec("check_all", "초안 전체에 검증기를 돌려 남은 문제와 검증기가 낼 상태를 봅니다.", _object({})),
            ToolSpec(
                "finish",
                "끝냅니다. accept: 받아들인 검증기 문제(code·target·reason), hold: 보류할 위치(target·reason).",
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

    def _check_all(self) -> dict[str, Any]:
        return issues_view(self.env.evaluate(self.env.draft.as_parts()))

    def _finish(self, accept: list[dict[str, str]], hold: list[dict[str, str]], note: str) -> dict[str, Any]:
        clean = lambda rows, keys: [{k: str(r.get(k, ""))[:300] for k in keys} for r in rows or [] if isinstance(r, dict)]  # noqa: E731
        self.env.decision = Decision(clean(accept, ("code", "target", "reason")), clean(hold, ("target", "reason")), (note or "")[:1_000])
        self.done = True
        return {"received": True}


def run_supervisor(env: Env) -> None:
    tools = SupervisorTools(env)
    log = AgentLog("supervisor")
    env.logs.append(log)
    context = {"하위 에이전트": {name: list(spec.sections) for name, spec in env.workers.items()}, "지금 초안": env.draft.summary()}
    base = ModelRequest(
        prompt_version=f"{env.rules.field}/{env.rules.prompt_version}/agentic-supervisor",
        call_name="agentic:supervisor",
        system=env.rules.system_prompt(),
        user=json.dumps(context, ensure_ascii=False, indent=1),
        instructions=SUPERVISOR_INSTRUCTIONS,
        output_schema=call_schema(("notice",), document_ids(env.material)),  # 도구 요청이라 쓰이지 않음(요청 형식상 필요)
        max_output_tokens=TURN_OUTPUT_TOKENS,
    )
    run_loop(env.model, base, tools, turns("EXTRACTION_AGENTIC_SUPERVISOR_TURNS", SUPERVISOR_TURNS), env.run, log)
