"""AI 재확인·자동 수정 (2026-10-15~16 결정: 사람 검수 전에 AI 재확인을 먼저 거칩니다).

검증에서 문제가 난 항목을 섹션과 상관없이 모아(사람 확인 이슈 + 계약 오류, 최대 MAX_ITEMS개) 문제 설명과 함께 AI에 한 번 더 보여 주고,
고친 항목을 같은 id 자리에 바꿔 넣습니다. 근거를 못 찾아 빠진 자격 조건도 함께 보냅니다.
고친 결과로 다시 결합·검증해서 나빠진 것 없이 좋아졌을 때만 채택하고, 아니면 처음 결과를 그대로 씁니다.
나빠졌는지는 개수가 아니라 (코드, 항목)별로 봅니다. 한 항목을 고치며 다른 항목에 새 문제가 생기면 채택하지 않습니다(2026-10-20).
근거(인용) 문제만 보낸 자격 조건은 조건의 뜻(대상·종류·조건식·예외)이 바뀌면 그 항목만 처음 것을 그대로 둡니다.
일정은 처음 답의 시작·끝 날짜가 근거 인용문으로 확인되는데 재확인 답이 그 날짜를 비우거나 근거에 없는 시각을 붙이면 그 일정만 처음 것을 둡니다.
응답 전체를 합쳐 나아지지 않으면 섹션마다 따로 합쳐 봅니다(2026-10-24). 다른 섹션이 나빠졌다고 나아진 섹션(빠진 서류 추가 등)까지 버리지 않고,
그 섹션만 합쳤을 때 어디에도 새 문제가 없고 그 섹션 문제가 줄었을 때만 받습니다.
인용문 일부를 찾지 못해 접수 시각·장소 등 세부 값이 지워진 일정도 다시 봅니다(인용을 고치면 값을 되찾을 수 있음).
합쳐진 서류(같은 이름·제출 시점의 서류가 남아 있음)는 빠진 항목으로 보내지 않습니다(재확인 상한을 차지하지 않게).
표시 메모 가운데 RECHECK_NOTE_CODES(서류 표 행 누락 의심)는 사람 확인 이슈가 아니지만 재확인에 보내고, 줄었는지도 함께 셉니다.
오류 종류마다 따로 처리하지 않습니다. 검사기가 준 오류 문구를 그대로 AI에 전달합니다. 표시만 하는 notes는 보내지 않습니다(비용).
AI 응답의 자기 보고로 통과되는 경로는 없습니다(채택 판단은 같은 검증기가 합니다).
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from mujuthaek_extraction.assemble.ai_output import SECTIONS
from mujuthaek_extraction.assemble.details import CLEARED, KST, document_name_key, times_in
from mujuthaek_extraction.assemble.quotes import normalize
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.extract import ExtractionRun, run_extraction, schema_errors
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ExtractionModel
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, structure_summary
from mujuthaek_extraction.verify.claims import has_date
from mujuthaek_extraction.verify.consistency import DOCUMENT_OMISSION, omitted_document_rows
from mujuthaek_extraction.verify.model import VerificationReport

NOTICE_FIELD = re.compile(r"\s/notice(?:/([A-Za-z]+))?")  # 문제 설명 「코드 /notice/announcedOn: …」의 칸 이름
MAX_ITEMS = 8  # 한 번에 다시 볼 항목 수 (응답 크기·비용 상한)
MAX_TARGET_CHARS = 40_000  # 다시 볼 항목 글자 수 상한. 호실별 가격 묶음 8개가 한 줄 45만 자가 되어 모델이 읽지 못함(실측 2026-10-18 LH 익산 행복주택)
LIST_SECTIONS = tuple(s for s in SECTIONS if s != "notice")
DROPPED_PROBLEM = (
    "ITEM_DROPPED_NO_EVIDENCE: 인용문을 원문에서 찾지 못해 이 항목이 결과에서 빠졌습니다. 원문에 글자 그대로 이어져 나오는 구간으로 다시 인용합니다."
)
DETAIL_LOST_PROBLEM = (
    "DETAIL_UNVERIFIED_CLEARED: 근거 인용문에서 확인할 수 없는 세부 값(접수 방법·시각·장소·쉬는 시각·제외 요일 등)을 지웠습니다. "
    "그 값이 적힌 원문 줄을 글자 그대로(표 번호·[열 제목] 표시 없이, 한 줄 안에서) 다시 인용하고 값을 돌려줍니다. 지운 값: "
)
UNVERIFIED_MARK = "근거 인용문에서 확인하지 못해"  # details.clear의 설명(근거로 확인 못 해 지운 값)
REF_PREFIX = "r-"  # 재확인 응답의 인용 참조가 처음 응답과 겹치지 않게
ITEM_PATH = re.compile(r"^/([A-Za-z]+)(?:/(\d+))?")
COVERAGE_PATH = re.compile(r"^/quality/coverage/([A-Za-z]+)$")
# 근거(인용) 위치 문제. 이것만 보낸 자격 조건은 인용만 고쳐야 하고 조건의 뜻은 그대로여야 합니다
# (실측 2026-10-20: 인용을 고치며 AGE_YEARS GTE 19를 LTE 19로 뒤집은 응답이 이슈 1→0으로 채택되어 통과됨)
EVIDENCE_ONLY_CODES = frozenset(
    {
        "EVIDENCE_QUOTE_NOT_FOUND",
        "EVIDENCE_SCATTERED",
        "EVIDENCE_AMBIGUOUS",
        "EVIDENCE_QUOTE_TOO_SHORT",
        "EVIDENCE_LOCATOR_MISMATCH",
        "EVIDENCE_LOCATOR_OUT_OF_RANGE",
        "EVIDENCE_LOCATOR_KIND_MISMATCH",
        "EVIDENCE_SOURCE_UNKNOWN",
        "EVIDENCE_SOURCE_UNAVAILABLE",
        "EVIDENCE_SOURCE_UNSUPPORTED",
        "CLAIM_UNSUPPORTED",
        "ORIGINAL_TEXT_NOT_FOUND",
        "ITEM_DROPPED_NO_EVIDENCE",
    }
)
# AI 재확인으로 보내지 않는 이슈: 공급표 금액 빈칸(SUPPLY_PRICE_MISSING)은 코드가 공고문 글을 이미 찾아봤고, 표 칸이 비어 있어
# AI가 다시 읽어도 근거 있는 값을 더 얻기 어렵습니다. 이 이슈만으로 유료 재확인 호출이 늘지 않게 사람 확인으로 둡니다
# 대상 한정 요금표의 대상 미정·표 제목의 주택형 여럿·병합 칸 수량(2026-10-24)도 코드가 표에서 정한 보류라 AI 재확인에 보내지 않습니다
# 전환안 방향을 숫자로도 정할 수 없음(2026-10-24)도 코드가 표 숫자로 정한 보류입니다
NO_RECHECK_CODES = frozenset(
    {"SUPPLY_PRICE_MISSING", "PRICE_SCOPE_UNCERTAIN", "SUPPLY_TYPE_AMBIGUOUS", "COUNT_MERGED_AMBIGUOUS", "CONVERSION_DIRECTION_UNCERTAIN"}
)
# 화면 메모(verifier.NOTE_CODES)지만 AI 재확인에 보내는 것: 원문 서류 표 행을 어느 서류도 인용하지 않음(2026-10-23).
# 누락이라 사람 확인으로 막지는 않지만, 재확인이 서류 섹션 전체를 다시 읽어 빠진 서류를 더할 수 있습니다
RECHECK_NOTE_CODES = frozenset({DOCUMENT_OMISSION})
# 뜻 비교에서 빼는 글 칸(설명·인용 참조). 나머지(대상·종류·조건식·단위·기준표·예외)는 그대로 같아야 합니다
TEXT_KEYS = frozenset({"quoteRefs", "basis", "description", "originalText", "reason", "appliesTo"})
INSTRUCTIONS = """검증에서 아래 항목에 문제가 발견되었습니다. 원문 전체를 다시 확인해 각 항목을 고친 뒤 같은 섹션·같은 id로 돌려줍니다.
- 문제 설명(코드와 위치)은 프로그램 검사기가 낸 것입니다. 설명한 규칙에 맞게 고칩니다. 규칙은 공통 지시를 따릅니다.
- 예외 누락 의심이면 원문의 가산·완화 기준을 exceptions에 적고 그 표를 인용합니다.
  확인해 보니 이 조건의 예외가 아니면(다른 대상·다른 기준의 값) 조건을 그대로 돌려줍니다.
- 인용문을 원문에서 찾지 못했다면 원문에 글자 그대로 이어져 나오는 구간으로 다시 인용합니다. 표 칸이 섞여 있으면 칸마다 따로 짧게 인용합니다.
- 가구원 수 구간이 조건 없이 나뉘었다는 문제(TIER_CONDITION_MISSING)면 각 조건식을 「그 가구원 수가 아니거나 기준값 이하」로 고칩니다.
  예: 2인 110%는 ANY[NOT(HOUSEHOLD_MEMBER_COUNT EQ 2), INCOME_BENCHMARK_PERCENT LTE 110],
  3인 이상 100%는 ANY[HOUSEHOLD_MEMBER_COUNT LT 3, INCOME_BENCHMARK_PERCENT LTE 100].
- 재계약 기준이 자격에 들어 있다는 문제(RENEWAL_CRITERION_IN_ELIGIBILITY)면 원문을 확인해, 신청할 때의 기준이면 originalText를 신청 기준 문장으로 고치고,
  정말 재계약·갱신 때의 기준이면 그 조건을 그대로 돌려줍니다(사람이 확인합니다).
- 범위를 확정하지 못했다고 표시한 항목(UNRESOLVED_SCOPE)은 원문에서 적용 범위를 확인해 확정합니다. 정말 정할 수 없으면 그대로 둡니다.
- 가격표 금액을 넣지 않았다는 문제면 그 행의 빠진 칸을 계층(scope.targetGroups)·요금안(pricePlanId)별 가격으로 더해 그 공급 묶음 전체를 돌려줍니다.
  수량 종류가 열 제목과 다르다는 문제면 열 제목에 맞는 kind로 고칩니다(건설 호수 TOTAL_HOUSING, 대기 중 예비자 WAITLIST, 금회 모집 OFFERED).
- 수량 묶음(parentCountId·aggregationRole·aggregationComplete)이 맞지 않으면, 원문에 전체와 구성 수량이 함께 있을 때만 묶고 아니면 STANDALONE으로 둡니다.
- id가 null이고 existingIds가 있는 항목은 섹션 전체에 대한 문제입니다(원문에 있는데 빠진 항목).
  원문에서 그 섹션을 끝까지 다시 읽고 빠진 항목만 새 id로 넣습니다. existingIds에 있는 항목은 다시 넣지 않습니다.
  다 넣었으면 그 섹션 coverage를 EXTRACTED로, 아직 남았으면 PARTIAL과 남은 내용을 적습니다.
- 맡은 섹션에는 아래 항목만 넣습니다(목록이면 고친 항목·추가한 항목만). 다른 항목은 다시 추출하지 않습니다.
  그 밖의 coverage는 맡은 섹션마다 EXTRACTED로 적습니다."""


@dataclass
class RecheckResult:
    parts: list[dict[str, Any]]  # 채택한 응답 조각들 (재확인을 채택하지 않았으면 처음 것)
    report: VerificationReport
    rechecked: list[str]  # 다시 본 항목 ("섹션/id")
    accepted: bool
    run: ExtractionRun | None  # 재확인 호출 기록 (사용량·비용)
    adopted_sections: tuple[str, ...] = ()  # 섹션별로 채택한 경우 그 섹션들(응답 전체를 채택했으면 빈 값)
    # 채택하지 않은 범위와 이유(2026-10-24 세 번째 채점: 어느 섹션을 왜 버렸는지 결과에 없어 평가에서 추정해야 했음).
    # (「전체」 또는 섹션 이름, 이유: 새로 생긴 (코드, 위치) 목록이나 「줄어든 문제 없음」)
    rejected: tuple[tuple[str, str], ...] = ()
    agent: dict[str, Any] | None = None  # 재확인 에이전트의 항목별 기록(차례·도구·결말). 묶음 재확인이면 None

    def summary(self) -> dict[str, Any] | None:
        """작업 기록(usage)·로그에 남길 재확인 요약. 다시 본 항목이 없으면 None."""
        if not self.rechecked:
            return None
        summary = {
            "rechecked": list(self.rechecked),
            "accepted": self.accepted,
            "adoptedSections": list(self.adopted_sections),
            "rejected": [{"scope": scope, "reason": reason} for scope, reason in self.rejected],
        }
        return {**summary, "agent": self.agent} if self.agent is not None else summary


def _item_key(candidate: dict[str, Any], pointer: str) -> tuple[str, str | None] | None:
    """검수 이슈·계약 오류 위치 → 고칠 항목 (섹션, id). notice는 id 없이. 항목을 정할 수 없으면 None."""
    coverage = COVERAGE_PATH.match(pointer)
    if coverage:  # 섹션 전체 문제(AI가 스스로 PARTIAL로 적음): 빠진 항목을 추가로 받습니다
        return (coverage[1], None) if coverage[1] in LIST_SECTIONS else None
    # 수량 규칙 오류는 그 수량의 실제 위치(/notice/counts/i, /supplyGroups/g/counts/j)로 옵니다: 아래 ITEM_PATH가 공고·공급 항목으로 찾습니다
    if pointer.startswith("/quality/missingFields/"):  # 미해결 누락: 그 누락이 가리키는 항목
        try:
            entry = tools().resolve(candidate, pointer.split(" ")[0])
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        return _item_key(candidate, entry["target"])
    match = ITEM_PATH.match(pointer)
    if not match:
        return None
    section, index = match[1], match[2]
    if section == "notice":
        return ("notice", None)
    if section in LIST_SECTIONS and index is not None and int(index) < len(candidate[section]):
        return (section, candidate[section][int(index)]["id"])
    return None


def _rechecked_notes(candidate: dict[str, Any]) -> list[dict[str, str]]:
    return [note for note in candidate["quality"]["notes"] if note.get("code") in RECHECK_NOTE_CODES]


def _lost_details(candidate: dict[str, Any]) -> dict[str, list[str]]:
    """세부 값이 근거 인용문으로 확인되지 않아 지워진 일정 → 지운 값 설명들.
    지운 값 메모는 일정 섹션(/schedules)을 가리키고 설명에 「이름(id):」로 일정을 적습니다(details.clear).
    예전엔 같은 일정의 인용문 일부를 원문에서 찾지 못했을(EVIDENCE_QUOTE_NOT_FOUND) 때만 보냈는데, 2026-10-24 세 번째 채점에서
    지워진 맞는 값(「12~13시」 점심시간, 인용에 「현장」 낱말이 없어 지운 유일한 접수 방법 ONSITE)은 모두 인용을 찾은 일정이라
    재확인에 가지 않았습니다. 인용을 찾았어도 값이 적힌 다른 줄을 인용하면 되찾을 수 있어 함께 보냅니다.
    「연속 구간이라 접수 시각을 비움」처럼 근거와 맞지 않아 지운 값(UNVERIFIED_MARK 없음)은 보내지 않습니다(다시 받아도 또 지움)."""
    quality = candidate["quality"]
    ids = [s.get("id") for s in candidate.get("schedules") or [] if isinstance(s, dict) and s.get("id")]
    lost: dict[str, list[str]] = {}
    for entry in [*quality["reviewIssues"], *quality["notes"]]:
        if entry.get("code") != CLEARED or entry.get("target") != "/schedules" or UNVERIFIED_MARK not in entry.get("description", ""):
            continue
        for schedule_id in ids:
            if f"({schedule_id}):" in entry["description"]:
                lost.setdefault(schedule_id, []).append(entry["description"].split(": ", 1)[-1])
    return lost


def _represented(section: str, item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """빠진 것처럼 보이는 서류가 같은 이름·제출 시점의 서류로 남아 있는지(같은 서류를 합쳐 id가 사라진 경우, details.merge_documents)."""
    if section != "requiredDocuments":
        return False
    key = (document_name_key(item.get("name")), normalize(str(item.get("submissionTime") or "")))
    return bool(key[0]) and any(
        (document_name_key(d.get("name")), normalize(str(d.get("submissionTime") or ""))) == key for d in candidate.get("requiredDocuments") or []
    )


def problem_items(report: VerificationReport) -> dict[tuple[str, str | None], list[str]]:
    candidate = report.candidate
    problems: dict[tuple[str, str | None], list[str]] = {}
    for issue in [*candidate["quality"]["reviewIssues"], *_rechecked_notes(candidate)]:
        if issue["code"] in NO_RECHECK_CODES:
            continue
        key = _item_key(candidate, issue["target"])
        if key:
            problems.setdefault(key, []).append(f"{issue['code']} {issue['target']}: {issue['description']}")
    for error in report.contract_errors:
        code, _, pointer = error.partition(" ")
        key = _item_key(candidate, pointer)
        if key:
            problems.setdefault(key, []).append(f"{code} {pointer}")
    for schedule_id, cleared in _lost_details(candidate).items():
        problems.setdefault(("schedules", schedule_id), []).append(DETAIL_LOST_PROBLEM + " / ".join(cleared))
    return problems


def _location(candidate: dict[str, Any], pointer: str) -> tuple[str, str | None]:
    """문제 위치 → (섹션, 항목 id). 순서가 바뀌어도 같은 항목이 같은 키가 되게 id로 봅니다. 항목을 정할 수 없으면 (섹션, 위치 그대로)."""
    key = _item_key(candidate, pointer)
    if key is not None:
        return key
    match = ITEM_PATH.match(pointer)
    return (match[1] if match else "", pointer)


def _problem_keys(report: VerificationReport) -> tuple[Counter, Counter]:
    """(계약 오류, 사람 확인 이슈)를 (코드, 위치)별로 셉니다. 표시만 하는 notes는 재확인에 보내는 것(RECHECK_NOTE_CODES)만 셉니다.
    서류 표 행 누락 의심은 빠진 행 수만큼 세어, 재확인이 일부 행만 채워도 줄어든 것으로 봅니다."""
    candidate = report.candidate
    errors = Counter((error.partition(" ")[0], _location(candidate, error.partition(" ")[2])) for error in report.contract_errors)
    issues = Counter((issue["code"], _location(candidate, issue["target"])) for issue in candidate["quality"]["reviewIssues"])
    for note in _rechecked_notes(candidate):
        issues[(note["code"], _location(candidate, note["target"]))] += omitted_document_rows(note["description"])
    for schedule_id, cleared in _lost_details(candidate).items():  # 세부 값을 되찾으면 줄어든 것으로 봅니다
        issues[(CLEARED, ("schedules", schedule_id))] += len(cleared)
    return errors, issues


def rejection_reason(first: VerificationReport, second: VerificationReport, sections: list[str], limit: int = 6) -> str:
    """채택하지 않은 이유: 새로 생기거나 늘어난 (코드, 위치) 목록, 없으면 다시 본 섹션의 문제가 줄지 않았다는 말."""
    grown = []
    for before, after in zip(_problem_keys(first), _problem_keys(second), strict=True):
        grown += [f"{code} {location[0]}/{location[1]}" for code, location in (after - before)]
    if grown:
        more = f" 외 {len(grown) - limit}건" if len(grown) > limit else ""
        return "새 문제: " + ", ".join(sorted(grown)[:limit]) + more
    return f"다시 본 섹션({', '.join(sections)})의 문제가 줄지 않음"


def _broken_sections(part: dict[str, Any], schema: dict[str, Any]) -> set[str] | None:
    """형식 위반이 있는 섹션 이름들. 섹션 밖(인용 목록·맨 위)에 위반이 있으면 None(응답 전체를 믿을 수 없음)."""
    from jsonschema import Draft202012Validator, FormatChecker

    broken: set[str] = set()
    for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(part):
        path = list(error.absolute_path)
        head = str(path[0]) if path else ""
        if head == "coverage" and len(path) > 1:
            head = str(path[1])
        if head not in SECTIONS:
            return None
        broken.add(head)
    return broken


# 값 개수(2026-10-24 다섯 번째 채점: 재확인 답이 병합 칸 계약금 3개를 빼고 돌아왔는데 문제 수만 보고 채택해 맞는 값이 지워짐)
def _value_counts(report: VerificationReport) -> dict[str, int]:
    candidate = report.candidate
    counts = {f"supplyGroups/{g.get('id')}": len(g.get("prices") or []) + len(g.get("counts") or []) for g in candidate.get("supplyGroups") or []}
    counts["requiredDocuments"] = len(candidate.get("requiredDocuments") or [])
    counts["schedules"] = len(candidate.get("schedules") or [])
    return counts


def _lost_values(first: VerificationReport, second: VerificationReport) -> list[str]:
    """재확인 뒤 가격·수량·서류·일정 개수가 줄어든 곳. 문제가 줄어도 맞는 값을 지운 답일 수 있어 받지 않습니다."""
    before, after = _value_counts(first), _value_counts(second)
    return [key for key, count in before.items() if key in after and after[key] < count]


def _rejection(first: VerificationReport, second: VerificationReport, sections: list[str]) -> str:
    lost = _lost_values(first, second)
    if lost and _improved(first, second, sections):
        return "값이 줄어듦: " + ", ".join(lost[:4])
    return rejection_reason(first, second, sections)


def _improved(first: VerificationReport, second: VerificationReport, sections: list[str]) -> bool:
    """채택 조건: 어느 (코드, 위치)도 새로 생기거나 늘지 않고, 다시 본 섹션의 문제가 하나 이상 줄었을 때.
    개수만 비교하면 한 항목을 고치며 다른 항목에 새 문제를 만든 응답도 채택될 수 있습니다."""
    resolved = False
    for before, after in zip(_problem_keys(first), _problem_keys(second), strict=True):
        if after - before:  # 처음에 없던(또는 더 많아진) 문제
            return False
        resolved = resolved or any(location[0] in sections for _, location in before - after)
    return resolved


def _meaning(node: Any) -> Any:
    """자격 조건의 뜻만 남깁니다(설명·인용 참조 제외). ALL·ANY 자식 순서는 뜻이 아니므로 정렬합니다."""
    if isinstance(node, dict):
        out = {k: _meaning(v) for k, v in node.items() if k not in TEXT_KEYS}
        if out.get("kind") in ("ALL", "ANY") and isinstance(out.get("children"), list):
            out["children"] = sorted(out["children"], key=lambda c: json.dumps(c, ensure_ascii=False, sort_keys=True))
        if isinstance(out.get("scope"), dict):
            out["scope"] = {k: v for k, v in out["scope"].items() if k != "resolution"}
        return out
    if isinstance(node, list):
        return [_meaning(x) for x in node]
    return node


def _keep_meaning(parts: list[dict[str, Any]], answer: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    """근거 문제만 보낸(또는 보내지 않은) 자격 조건인데 응답에서 뜻(대상·종류·조건식·예외)이 바뀌었으면 그 항목을 응답에서 뺍니다.
    빼면 합칠 때 처음 항목이 그대로 남고(이슈도 남아 사람이 확인), 다른 항목의 수정은 같은 채택 기준으로 따로 판단됩니다.
    값·조건 문제(VALUE_NOT_IN_QUOTE, 계약 오류 등)를 보낸 항목은 뜻을 고치는 것이 목적이므로 여기서 막지 않습니다."""
    index = _part_with(parts, "eligibility")
    if index is None or not isinstance(answer.get("eligibility"), list):
        return answer
    original = {item.get("id"): item for item in parts[index]["eligibility"] if isinstance(item, dict)}
    sent = {t["id"]: t["problems"] for t in targets if t["section"] == "eligibility" and t["id"] is not None}
    # 보내지 않은 항목을 돌려준 경우도 뜻은 바뀌면 안 됩니다(맡기지 않은 항목)
    evidence_only = {item_id for item_id in original if all(p.split(" ", 1)[0].rstrip(":") in EVIDENCE_ONLY_CODES for p in sent.get(item_id, []))}
    kept = [
        item
        for item in answer["eligibility"]
        if not (isinstance(item, dict) and item.get("id") in evidence_only and item.get("id") in original and _meaning(item) != _meaning(original[item["id"]]))
    ]
    return answer if len(kept) == len(answer["eligibility"]) else {**answer, "eligibility": kept}


def _moment(value: Any) -> tuple[str, int | None] | None:
    """일정 시작·끝 값 → (날짜, 시각(분) 또는 None). 형식을 모르면 None."""
    if not isinstance(value, dict) or not isinstance(value.get("value"), str):
        return None
    if value.get("precision") != "MINUTE":
        return value["value"][:10], None
    try:
        moment = datetime.fromisoformat(value["value"]).astimezone(KST)
    except ValueError:
        return None
    return moment.date().isoformat(), moment.hour * 60 + moment.minute


def _keep_verified_dates(parts: list[dict[str, Any]], answer: dict[str, Any]) -> dict[str, Any]:
    """처음 답의 일정 시작·끝 날짜가 그 일정의 근거 인용문에서 확인되는데, 재확인 답이 그 칸을 비우거나 근거 인용문에 없는 시각을 붙이면
    그 일정을 응답에서 뺍니다(처음 일정이 그대로 남음). 2026-10-23 시험 채점: 처음 답이 근거대로 적은 마감일을, 다른 문제를 줄인
    재확인 답이 비워 둔 채 채택되어 마감일이 사라졌음. 확인된 값을 근거 없이 잃지 않게 합니다."""
    index = _part_with(parts, "schedules")
    if index is None or not isinstance(answer.get("schedules"), list):
        return answer
    first_quotes = {q["ref"]: q["text"] for q in parts[index].get("quotes") or [] if isinstance(q, dict)}
    new_quotes = {q["ref"]: q["text"] for q in answer.get("quotes") or [] if isinstance(q, dict)}
    original = {item.get("id"): item for item in parts[index]["schedules"] if isinstance(item, dict)}

    def lost(item: dict[str, Any]) -> bool:
        before = original.get(item.get("id"))
        if before is None:
            return False
        before_texts = [first_quotes.get(r, "") for r in before.get("quoteRefs") or []]
        after_text = "\n".join(new_quotes.get(r, "") for r in item.get("quoteRefs") or [] if isinstance(r, str))
        for key in ("startsAt", "endsAt"):
            old, new = before.get(key), item.get(key)
            if old is None or not has_date(before_texts, old, end=key == "endsAt"):
                continue  # 처음 값이 없거나 근거로 확인되지 않으면 재확인 답을 막지 않습니다
            if new is None:
                return True
            moment = _moment(new)
            if moment is not None and moment[1] is not None and moment[1] not in times_in(after_text):
                return True  # 근거에 없는 시각을 붙임
        return False

    kept = [item for item in answer["schedules"] if not (isinstance(item, dict) and lost(item))]
    return answer if len(kept) == len(answer["schedules"]) else {**answer, "schedules": kept}


def _with_quotes(item: Any, quotes: dict[str, str]) -> Any:
    """AI에게 다시 보여 줄 때 인용 참조 대신 인용문을 그대로 넣습니다."""
    if isinstance(item, dict):
        return {k: _with_quotes(v, quotes) for k, v in item.items() if k != "quoteRefs"} | (
            {"quotes": [quotes.get(r, r) for r in item["quoteRefs"]]} if "quoteRefs" in item else {}
        )
    if isinstance(item, list):
        return [_with_quotes(x, quotes) for x in item]
    return item


def _rename_refs(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: ([REF_PREFIX + r for r in v] if k == "quoteRefs" else _rename_refs(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rename_refs(x) for x in node]
    return node


def _part_with(parts: list[dict[str, Any]], section: str) -> int | None:
    return next((i for i, p in enumerate(parts) if isinstance(p, dict) and section in p), None)


def sent_scope(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """재확인에 보낸 범위: 목록 섹션은 보낸 항목 id, 공고 기본 정보는 문제가 난 칸 이름(칸을 정할 수 없으면 None = 전체)."""
    items: dict[str, set[str]] = {}
    notice_fields: set[str] | None = set()
    for target in targets:
        if target["section"] == "notice":
            for problem in target["problems"]:
                match = NOTICE_FIELD.search(problem)
                if match is None or match[1] is None:
                    notice_fields = None
                elif notice_fields is not None:
                    notice_fields.add(match[1])
        elif target["id"] is not None:
            items.setdefault(target["section"], set()).add(target["id"])
    return {"items": items, "notice": notice_fields if any(t["section"] == "notice" for t in targets) else set()}


def merge_recheck(
    parts: list[dict[str, Any]], recheck_part: dict[str, Any], add_sections: tuple[str, ...] = (), sent: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """고친 항목만 같은 섹션·같은 id 자리에 바꿔 넣습니다. 처음에 없던 id는 섹션 전체를 다시 본 경우(add_sections)에만 뒤에 붙입니다.
    그 섹션의 범위 상태는 새 항목을 하나라도 받았을 때만 재확인 응답 것으로 바꿉니다(AI가 "다 넣었다"고 적기만 해서 통과되지 않게).
    sent(sent_scope): 보낸 항목만 바꾸고, 공고 기본 정보는 문제가 난 칸만 바꿉니다(2026-10-21 검토: 보내지 않은 일정·가격이 응답에 섞여
    다른 값으로 바뀌어도 메모만 생기면 채택될 수 있었음). None이면 응답의 모든 항목을 받습니다(이전 동작)."""
    merged = copy.deepcopy(parts)
    quotes = [{**q, "ref": REF_PREFIX + q["ref"]} for q in recheck_part.get("quotes") or []]
    touched: set[int] = set()
    for section in SECTIONS:
        if section not in recheck_part:
            continue
        index = _part_with(merged, section)
        if index is None:
            continue
        target = merged[index]
        if section == "notice":
            if isinstance(recheck_part["notice"], dict):
                answer = _rename_refs(recheck_part["notice"])
                fields = None if sent is None else sent["notice"]
                if fields is None:
                    target["notice"] = answer
                else:  # 문제가 난 칸(과 그 근거 참조)만
                    keep = {**target["notice"], **{k: v for k, v in answer.items() if k in fields or k == "quoteRefs"}}
                    if fields:
                        target["notice"] = keep
                touched.add(index)
            continue
        allowed = None if sent is None else sent["items"].get(section, set())
        fixed = {
            item["id"]: _rename_refs(item)
            for item in recheck_part.get(section) or []
            if isinstance(item, dict) and "id" in item and (allowed is None or item["id"] in allowed or section in add_sections)
        }
        replace = fixed if allowed is None else {k: v for k, v in fixed.items() if k in allowed}
        if replace:
            target[section] = [replace.get(item["id"], item) for item in target[section]]
            touched.add(index)
        if section in add_sections:
            existing = {item.get("id") for item in target[section] if isinstance(item, dict)}
            added = [item for item_id, item in fixed.items() if item_id not in existing]
            if added:
                target[section] = [*target[section], *added]
                new_coverage = (recheck_part.get("coverage") or {}).get(section)
                if isinstance(target.get("coverage"), dict) and isinstance(new_coverage, dict):
                    target["coverage"][section] = new_coverage
                touched.add(index)
    for index in touched:
        merged[index]["quotes"] = [*(merged[index].get("quotes") or []), *quotes]
    return merged


# 항목 문제를 보낼 섹션 순서(2026-10-24 네 번째 채점: 자격 세부 항목 6개가 자리 8개를 늘 먼저 차지해, 화면에 보이는 일정의 지워진
# 접수 시각이 재확인을 받지 못함). 섹션 전체 문제 다음에 항목 문제를 이 순서로 섹션마다 하나씩 번갈아 넣습니다
RECHECK_SECTION_ORDER = ("schedules", "supplyGroups", "requiredDocuments", "notice", "eligibility")


def ordered_problems(problems: dict[tuple[str, str | None], list[str]]) -> list[tuple[tuple[str, str | None], list[str]]]:
    """재확인에 보낼 순서. 섹션 전체 문제(빠진 항목 추가)를 먼저 둬 항목 문제가 많아도 상한(MAX_ITEMS)에 밀려 빠지지 않게 하고,
    항목 문제는 RECHECK_SECTION_ORDER 순서로 섹션마다 하나씩 번갈아 둡니다(한 섹션이 자리를 모두 차지하지 않게)."""
    whole = [kv for kv in problems.items() if kv[0][1] is None and kv[0][0] != "notice"]
    by_section: dict[str, list[tuple[tuple[str, str | None], list[str]]]] = {}
    for kv in problems.items():
        if kv not in whole:
            by_section.setdefault(kv[0][0], []).append(kv)
    rank = {name: n for n, name in enumerate(RECHECK_SECTION_ORDER)}
    queues = [by_section[name] for name in sorted(by_section, key=lambda name: rank.get(name, len(rank)))]
    items: list[tuple[tuple[str, str | None], list[str]]] = []
    while any(queues):
        for queue in queues:
            if queue:
                items.append(queue.pop(0))
    return whole + items


def select_targets(parts: list[dict[str, Any]], first: VerificationReport) -> tuple[list[dict[str, Any]], list[str]]:
    """다시 볼 항목(최대 MAX_ITEMS개, 합쳐 MAX_TARGET_CHARS자)과 그 섹션들을 고릅니다. 검증 문제 항목과 근거를 못 찾아 빠진 항목입니다."""
    problems = problem_items(first)
    # 근거를 못 찾아 아예 빠진 항목도 섹션과 상관없이 다시 봅니다 (가격·공급 같은 필수 데이터가 조용히 빠지지 않게).
    # 빠지면 이슈가 목록 전체를 가리켜 위에서 찾을 수 없습니다. 자격 조건을 먼저 봅니다.
    for section in ("eligibility", *[s for s in LIST_SECTIONS if s != "eligibility"]):
        index = _part_with(parts, section)
        if index is None or not isinstance(parts[index].get(section), list):
            continue
        kept = {item["id"] for item in first.candidate[section]}
        for item in parts[index].get(section) or []:
            if isinstance(item, dict) and item.get("id") not in kept and not _represented(section, item, first.candidate):
                problems.setdefault((section, item.get("id")), []).append(DROPPED_PROBLEM)

    targets, sections, used = [], [], 0
    for (section, item_id), descriptions in ordered_problems(problems):
        if len(targets) >= MAX_ITEMS:
            break
        index = _part_with(parts, section)
        if index is None:
            continue
        part = parts[index]
        quotes = {q["ref"]: q["text"] for q in part.get("quotes") or [] if isinstance(q, dict)}
        if section == "notice":
            item = part["notice"]
        elif item_id is None:  # 섹션 전체: 지금 있는 항목 id와 AI가 적은 범위 사유만 보냅니다(목록 전체를 다시 보내지 않음, 비용)
            item = {"existingIds": [x.get("id") for x in part.get(section) or [] if isinstance(x, dict)], "coverage": (part.get("coverage") or {}).get(section)}
        else:
            item = next((x for x in part.get(section) or [] if isinstance(x, dict) and x.get("id") == item_id), None)
            if item is None:
                continue
        target = {"section": section, "id": item_id, "item": _with_quotes(item, quotes), "problems": descriptions}
        size = len(json.dumps(target, ensure_ascii=False))
        if used + size > MAX_TARGET_CHARS:
            continue  # 상한을 넘으면 이 항목은 이번에 보내지 않습니다(검수 이슈로 그대로 남음). 더 작은 다음 항목은 봅니다
        used += size
        targets.append(target)
        if section not in sections:
            sections.append(section)
    return targets, sections


@dataclass
class RecheckAnswer:
    """재확인 답 받기의 결과입니다. response가 None이면 받을 답이 없어(호출 실패·형식 위반) 처음 결과를 그대로 씁니다.
    형식 위반 섹션을 뺐으면 targets·sections도 줄어든 것이고, rejected에 뺀 이유를 담습니다."""

    response: dict[str, Any] | None
    run: ExtractionRun | None
    targets: list[dict[str, Any]]
    sections: list[str]
    rejected: tuple[tuple[str, str], ...] = ()
    agent: dict[str, Any] | None = None  # 답을 받은 과정의 기록(에이전트 전략만)


class RecheckStrategy(Protocol):
    """다시 볼 항목의 고친 답을 받는 방법입니다. 받은 답을 채택할지는 전략이 아니라 adopt(같은 검증기)가 정합니다.
    evaluate는 답을 내기 전에 스스로 확인할 때만 씁니다(에이전트의 validate_item). 채택 판단에는 쓰지 않습니다."""

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
    ) -> RecheckAnswer: ...


class BatchStrategy:
    """다시 볼 항목을 한 번의 호출로 묶어 묻습니다(2026-10-15부터의 방식)."""

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
        call = CallSpec(
            name="recheck",
            sections=tuple(s for s in SECTIONS if s in sections),
            instructions=INSTRUCTIONS
            + "\n\n# 다시 확인할 항목\n"
            + json.dumps(targets, ensure_ascii=False, indent=1),  # 줄 단위로(한 줄이 너무 길면 모델이 읽지 못함)
            uses_structure=True,
            max_output_tokens=48_000,  # 실측: 큰 공고(인천 4358)에서 24,000토큰으로 잘림(내용 6.7만 자, 반복 아님). 정상 종료 최대 14,261
        )
        one_call = FieldRules(rules.field, rules.prompt_version, rules.prompt_path, (call,))
        run = run_extraction(one_call, material, model, structure=structure_summary(parts[0]), **run_options)
        if run.failed_calls:
            reason = "재확인 호출 실패: " + "; ".join(why for _, why in run.failed_calls)
            return RecheckAnswer(None, run, targets, sections, (("전체", reason),))
        # 수정 호출 뒤에도 형식 위반이 남은 응답(extract가 첫 응답을 살려 넘김)은 고친 결과가 아니므로 섞지 않습니다(검토 2026-10-16)
        schema = one_call.build_request(call, material, structure_summary(parts[0])).output_schema
        response = run.parts[0]
        if schema_errors(response, schema) is None:
            return RecheckAnswer(response, run, targets, sections)
        # 형식 위반이 있는 섹션만 빼고 나머지 섹션은 시험합니다(2026-10-24 다섯 번째 채점: 재확인 5건 중 2건이 일부 형식 위반으로 통째 버려짐).
        # 인용 목록처럼 섹션 밖 칸이 틀렸으면 모두 버립니다
        broken = _broken_sections(response, schema)
        if broken is None or not set(sections) - broken:
            return RecheckAnswer(None, run, targets, sections, (("전체", "재확인 응답 형식 위반"),))
        kept = [section for section in sections if section not in broken]
        return RecheckAnswer(
            {key: value for key, value in response.items() if key not in broken},
            run,
            [t for t in targets if t["section"] not in broken],
            kept,
            tuple((section, "재확인 응답 형식 위반") for section in sections if section in broken),
        )


BATCH = BatchStrategy()


def recheck_problems(
    rules: FieldRules,
    material: ExtractionMaterial,
    model: ExtractionModel,
    parts: list[dict[str, Any]],
    evaluate: Callable[[list[dict[str, Any]]], VerificationReport],
    strategy: RecheckStrategy = BATCH,
    **run_options: Any,
) -> RecheckResult:
    """evaluate: 응답 조각들 → 결합·검증 결과. 처음 결과와 재확인 결과를 같은 함수로 판단합니다.
    순서: 다시 볼 항목 고르기(select_targets) → 고친 답 받기(strategy) → 채택 판단(adopt)."""
    first = evaluate(parts)
    targets, sections = select_targets(parts, first)
    if not targets:
        return RecheckResult(parts, first, [], False, None)
    rechecked = [f"{t['section']}/{t['id']}" if t["id"] else t["section"] for t in targets]
    answer = strategy.answer(rules, material, model, parts, targets, sections, evaluate=evaluate, **run_options)
    if answer.response is None:
        result = RecheckResult(parts, first, rechecked, False, answer.run, rejected=answer.rejected)
    else:
        result = adopt(parts, first, answer, rechecked, evaluate)
    result.agent = answer.agent
    return result


def recheck_rounds(
    rules: FieldRules,
    material: ExtractionMaterial,
    model: ExtractionModel,
    parts: list[dict[str, Any]],
    evaluate: Callable[[list[dict[str, Any]]], VerificationReport],
    strategies: tuple[RecheckStrategy, ...],
    **run_options: Any,
) -> RecheckResult:
    """재확인을 여러 라운드로: 앞 라운드에서 채택한 결과 위에서 남은 문제만 다음 전략으로 다시 봅니다(2026-11-05).
    실측(공고 4건): 묶음 재확인은 일정·자격처럼 한 번에 고칠 수 있는 항목을, 에이전트는 묶음이 못 고친 항목 일부를 고쳤습니다.
    라운드마다 채택은 같은 검증기(adopt)가 정하므로, 뒤 라운드가 앞 라운드에서 받은 것을 나쁘게 바꿀 수 없습니다."""
    current: RecheckResult | None = None
    rechecked: list[str] = []
    adopted: list[str] = []
    rejected: list[tuple[str, str]] = []
    run = ExtractionRun()
    accepted = False
    agent = None
    for number, strategy in enumerate(strategies, start=1):
        result = recheck_problems(rules, material, model, current.parts if current else parts, evaluate, strategy=strategy, **run_options)
        if current is None:
            current = result
        if result.run is not None:
            run.attempts += result.run.attempts
            run.raw_responses += result.run.raw_responses
            run.failed_calls += result.run.failed_calls
        rechecked += [r for r in result.rechecked if r not in rechecked]
        if result.accepted:
            accepted = True
            adopted += [f"{number}:{a}" for a in result.adopted_sections] or [f"{number}:전체"]
            current = result
        rejected += [(f"{number}:{scope}", reason) for scope, reason in result.rejected]
        agent = result.agent or agent
        if not result.rechecked:
            break  # 남은 문제가 없으면 다음 라운드를 부르지 않습니다
    assert current is not None
    return RecheckResult(current.parts, current.report, rechecked, accepted, run if run.attempts else None, tuple(adopted), tuple(rejected), agent)


def adopt(
    parts: list[dict[str, Any]],
    first: VerificationReport,
    answer: RecheckAnswer,
    rechecked: list[str],
    evaluate: Callable[[list[dict[str, Any]]], VerificationReport],
) -> RecheckResult:
    """받은 답을 합쳐 다시 검증하고, 나빠진 것 없이 나아졌을 때만 받습니다(전체 → 섹션별 → 항목별 순서로 시험).
    채택은 이 함수만 정합니다. 답을 낸 쪽(AI)의 자기 보고로 통과되는 경로는 없습니다."""
    targets, sections, run, format_rejected = answer.targets, answer.sections, answer.run, list(answer.rejected)
    fixed = _keep_verified_dates(parts, _keep_meaning(parts, answer.response, targets))
    whole = tuple(t["section"] for t in targets if t["id"] is None and t["section"] != "notice")
    sent = sent_scope(targets)
    merged = merge_recheck(parts, fixed, whole, sent)
    second = evaluate(merged)
    if _improved(first, second, sections) and not _lost_values(first, second):
        return RecheckResult(merged, second, rechecked, True, run, rejected=tuple(format_rejected))
    rejected = [*format_rejected, ("전체", _rejection(first, second, sections))]
    # 섹션마다 따로: 그 섹션만 합쳐 어디에도 새 문제가 없고 그 섹션 문제가 줄면 받고, 받은 결과 위에 다음 섹션을 봅니다.
    # 거절된 섹션은 다른 섹션을 받은 뒤 한 번 더 봅니다(2026-10-24 다섯 번째 채점: 공고 칸 답이 자격 섹션의 문제 때문에 거절됐는데,
    # 이어서 자격 섹션을 받은 뒤 다시 보지 않아 공고 전체가 검수로 감)
    current, report, adopted = parts, first, []
    waiting = list(sections)
    for _ in range(2):
        still: list[str] = []
        reasons: dict[str, str] = {}
        for section in waiting:
            if section not in fixed:
                reasons[section] = "재확인 응답에 그 섹션이 없음"
                continue
            only = {key: value for key, value in fixed.items() if key not in SECTIONS or key == section}
            trial = merge_recheck(current, only, tuple(s for s in whole if s == section), sent)
            trial_report = evaluate(trial)
            if _improved(report, trial_report, [section]) and not _lost_values(report, trial_report):
                current, report = trial, trial_report
                adopted.append(section)
            else:
                still.append(section)
                reasons[section] = _rejection(report, trial_report, [section])
        if not still or len(still) == len(waiting) or not adopted:
            waiting = still
            break
        waiting = still
    rejected += [(section, reasons[section]) for section in waiting if section in reasons]
    # 섹션째 거절된 섹션은 항목마다 따로 봅니다(2026-10-24 일곱 번째 채점: 재확인 답이 빠진 서류 4개를 원문 인용으로 맞게 되살렸는데,
    # 같은 섹션의 다른 항목 문제가 줄지 않아 섹션째 버려짐). 항목 하나만 합쳐 어디에도 새 문제가 없고 문제가 줄며 값이 줄지 않으면 받습니다
    for section in waiting:
        if section == "notice" or not isinstance(fixed.get(section), list):
            continue
        existing = {item.get("id") for part in current if isinstance(part.get(section), list) for item in part[section] if isinstance(item, dict)}
        wanted = sent["items"].get(section, set())
        for item in fixed[section]:
            if not isinstance(item, dict) or "id" not in item:
                continue
            added = section in whole and item["id"] not in existing
            if item["id"] not in wanted and not added:
                continue
            only = {key: value for key, value in fixed.items() if key not in SECTIONS} | {section: [item]}
            single = {"items": {section: {item["id"]}}, "notice": set()}
            trial = merge_recheck(current, only, (section,) if added else (), single)
            trial_report = evaluate(trial)
            if _improved(report, trial_report, [section]) and not _lost_values(report, trial_report):
                current, report = trial, trial_report
                adopted.append(f"{section}/{item['id']}")
    if adopted:
        return RecheckResult(current, report, rechecked, True, run, tuple(adopted), tuple(rejected))
    return RecheckResult(parts, first, rechecked, False, run, rejected=tuple(rejected))


def _leaves(value: Any, path: str = ""):
    """값이 있는 끝 칸(글자·숫자·참거짓)의 위치와 값. 근거 참조(quoteRefs·evidenceIds 등)는 바뀌어도 값이 사라진 게 아니라 뺍니다."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("quoteRefs", "evidenceIds", "quotes", "id"):
                continue
            yield from _leaves(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, f"{path}/{index}")
    elif value is not None and value != "":
        yield path, value


def lost_by_recheck(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """재확인 답을 채택하며 처음 AI 답의 값 있는 칸이 비거나 없어진 곳(같은 섹션·같은 id 항목, 공고 기본 정보는 칸 단위).
    채택 검사(_lost_values)는 개수만 보므로, 면적·신청 방법·장소처럼 검사가 없는 칸이 조용히 사라질 수 있었습니다(2026-10-26 감사)."""

    def index(parts: list[dict[str, Any]]) -> dict[tuple[str, str], Any]:
        found: dict[tuple[str, str], Any] = {}
        for part in parts:
            for section in SECTIONS:
                value = part.get(section)
                if section == "notice" and isinstance(value, dict):
                    found[("notice", "")] = value
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and "id" in item:
                            found[(section, str(item["id"]))] = item
        return found

    old, new = index(before), index(after)
    lost: list[tuple[str, str]] = []
    for (section, item_id), item in old.items():
        if (section, item_id) not in new:
            continue  # 항목째 빠진 것은 다른 검사(DROPPED_PROBLEM·ITEM_DROPPED_NO_EVIDENCE)가 봅니다
        kept = dict(_leaves(new[(section, item_id)]))
        gone = [path for path, _ in _leaves(item) if path not in kept]
        if gone:
            where = f"/{section}" + (f" {item_id}" if item_id else "")
            lost.append((f"/{section}", f"{where}: 재확인 답으로 바꾸며 처음 값이 사라졌어요({', '.join(gone[:5])}{' …' if len(gone) > 5 else ''})"))
    return lost
