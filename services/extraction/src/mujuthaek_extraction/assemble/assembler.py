"""AI 출력(ai-output) + intake 신뢰 문맥 → extracted-notice v1 후보.

- 인용문 → 위치는 프로그램이 계산합니다(quotes.py). 근거가 하나도 확인되지 않은 항목은 후보에서 빼고 이슈로 남깁니다.
- 금액·지역 코드는 원문을 그대로 두고 계산값만 붙입니다(values.py, regions.py). 계산할 수 없으면 null + 누락 사유.
- 검증 상태는 NOT_RUN으로 두고 검증 모듈이 채웁니다. 시계·UUID·네트워크·AI 호출이 없습니다.
- AI 응답 원문은 job 기록에 보관하는 것을 전제로 하며, 여기서는 후보와 이슈만 만듭니다.
"""

from __future__ import annotations

import copy
import dataclasses
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.assemble.coerce import COERCIBLE, coerce_item
from mujuthaek_extraction.assemble.coverage import DROPPED_INVALID, DROPPED_NO_EVIDENCE
from mujuthaek_extraction.assemble.details import check_details
from mujuthaek_extraction.assemble.missing_prices import fill_missing_prices
from mujuthaek_extraction.assemble.quotes import (
    NormalizedText,
    QuoteResolution,
    QuoteStatus,
    choose_by_target_groups,
    choose_near,
    find_in_order,
    normalize,
    quote_in_unit_row,
    resolve_item_quotes,
    split_joined_quote,
    strip_markers,
)
from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.assemble.slips import fix_format_slips
from mujuthaek_extraction.assemble.values import range_krw, to_krw
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext

SECTIONS = ai_output.SECTIONS
# 원소 하나를 빼도 나머지 의미가 바뀌지 않는 목록. 조건식(children·exceptions) 안의 항목은 여기 없으므로 그 조건 전체를 뺍니다.
# 날짜만 적힌 인용: 「2026. 03. 24.」「2026.3.24」「2026년 3월 24일」「'26.03.24.(화)」
BARE_DATE = re.compile(r"[’'`]?\d{2,4}\s*[.년-]\s*\d{1,2}\s*[.월-]\s*\d{1,2}\s*[.일]?\s*(?:\([월화수목금토일]\))?")
RECORD_ARRAYS = {"locations", "schedules", "supplyGroups", "eligibility", "selectionRules", "requiredDocuments", "guidance", "counts", "prices"}
NULLABLE_OBJECTS = {"leaseTerm"}  # 근거가 없으면 null + 누락 사유로 둡니다
# 검수 이슈에 보여 줄 항목 이름 (앞 칸 우선)
LABEL_KEYS = ("name", "title", "complexName", "unitLabel", "rawLabel", "originalText", "description", "address", "id")
LABEL_CHARS = 40
QUOTE_CHARS = 80
# 소득 기준 연도를 공고일 기준으로만 적은 표현 → 공고일 연도에 더할 값
RELATIVE_YEARS = (("전년도", -1), ("전년", -1), ("당해연도", 0), ("당해년도", 0), ("금년도", 0))
# 흩어진 낱말로 찾은 근거(find_scattered)를 검수로 보낼 위치: 판정·선정·금액·일정에 쓰는 값이라 낱말 순서가 바뀌면 뜻이 뒤집힐 수 있습니다
SCATTER_REVIEW_SECTIONS = {"eligibility", "selectionRules", "schedules"}
SCATTER_REVIEW_SUPPLY = {"prices", "counts"}
# 모집 단계(예비·최초·우선 입주자)는 수량 종류(OFFERED·RESERVE·WAITLIST)로 나타내지 신청 대상이 아닙니다(2026-11-07 23건 대조: 공고 수량
# 「OFFERED 280 [예비입주자]」「RESERVE 15 [예비 입주자]」처럼 대상 칸에 적혀 공고 전체 모집 수가 대상을 한정한 수로 보임 — V2 4건·V1 5건)
STAGE_TARGET = re.compile(r"^(?:(?P<reserve>예비\s*입주자|예비자)|(?P<first>(?:최초|우선)\s*입주자))$")


def _relative_years(text: Any) -> dict[int, str]:
    """글에 있는 상대 연도 표현: 공고일 연도에 더할 값 → 처음 찾은 표현(「전년도」가 「전년」보다 앞)."""
    found: dict[int, str] = {}
    for word, offset in RELATIVE_YEARS:
        if isinstance(text, str) and word in text:
            found.setdefault(offset, word)
    return found


def _scatter_needs_review(tokens: list[str | int]) -> bool:
    """흩어진 낱말로 찾은 근거를 검수 이슈로 남길 위치인지: 자격 조건(예외 포함)·선정 규칙·일정·공급 묶음의 가격·수량."""
    if not tokens:
        return False
    if tokens[0] in SCATTER_REVIEW_SECTIONS:
        return True
    return tokens[0] == "supplyGroups" and any(t in SCATTER_REVIEW_SUPPLY for t in tokens)


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _shift_missing(part: dict[str, Any], section: str, removed: set[int]) -> None:
    """빼낸 항목에 맞춰 누락 기록(missingFields)의 위치를 고칩니다: 빼낸 항목을 가리키던 기록은 지우고, 뒤쪽 항목은 앞당깁니다.
    예전엔 그대로 두어 기록이 "없는 칸"으로 버려지거나 다른 항목을 가리켰습니다(검토 2026-10-16)."""
    entries = part.get("missingFields")
    if not isinstance(entries, list):
        return
    prefix = re.compile(rf"^/{re.escape(section)}/(\d+)(?=/|$)")
    kept = []
    for entry in entries:
        target = entry.get("target") if isinstance(entry, dict) else None
        match = prefix.match(target) if isinstance(target, str) else None
        if match is None:
            kept.append(entry)
            continue
        index = int(match[1])
        if index in removed:
            continue
        shifted = index - sum(1 for r in removed if r < index)
        kept.append({**entry, "target": f"/{section}/{shifted}{target[match.end() :]}"})
    part["missingFields"] = kept


def _label(node: dict[str, Any]) -> str:
    """검수자가 어떤 항목인지 알아볼 이름: 서류명·제목·원문 표현 순으로 찾고, 없으면 id."""
    for key in LABEL_KEYS:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return _short(value, LABEL_CHARS)
    return "이름 없는 항목"


@dataclass(frozen=True)
class AssemblyInput:
    context: TrustedContext
    material: ExtractionMaterial
    regions: RegionCodeTable | None = None
    default_sido: str | None = None  # 출처가 한 시도뿐일 때 (예: SH → 서울특별시)


@dataclass
class AssemblyResult:
    candidate: dict[str, Any] | None
    issues: list[dict[str, str]] = field(default_factory=list)  # 후보의 quality.reviewIssues와 같음
    notes: list[str] = field(default_factory=list)  # 완료를 막지 않는 참고 메모 (job 기록용)
    contract_errors: list[str] = field(default_factory=list)


def _pointer(tokens: list[str | int]) -> str:
    return "".join("/" + str(t).replace("~", "~0").replace("/", "~1") for t in tokens)


# AI가 「합계·총수가 원문에 따로 없어 적지 않음」을 이유로 공고 기본 정보를 PARTIAL로 적은 경우(원문에 없는 값이지 덜 뽑은 것이 아님)
TOTAL_NOT_WRITTEN = re.compile(r"(?:합계|합산|총\s*(?:모집|공급|세대|호|수))[^.]{0,40}(?:없|적혀\s*있지\s*않|기재되지\s*않|나와\s*있지\s*않)")


def _total_not_written(entry: dict[str, Any]) -> bool:
    return entry.get("status") == "PARTIAL" and bool(TOTAL_NOT_WRITTEN.search(str(entry.get("reason") or "")))


def _walk(value: Any, tokens: list[str | int]):
    if isinstance(value, dict):
        yield tokens, value
        for key, child in value.items():
            yield from _walk(child, [*tokens, key])
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, [*tokens, index])


def _get(root: Any, tokens: list[str | int]) -> Any:
    for token in tokens:
        root = root[token]
    return root


def _stage_only(count: dict[str, Any], siblings: list[dict[str, Any]]) -> str | None:
    """수량의 대상이 모집 단계뿐이고 그 단계가 수량 종류와 맞으면 그 단계 이름(비울 것), 아니면 None.
    예비자는 RESERVE·WAITLIST, 또는 같은 자리에 다른 OFFERED가 없는 OFFERED(예비입주자만 모집하는 공고는 예비자 수가 OFFERED)일 때,
    최초·우선 입주자는 OFFERED일 때만입니다. 비우면 같은 종류의 대상 없는 수량과 겹치는 경우도 두지 않습니다."""
    scope = count.get("scope")
    groups = scope.get("targetGroups") if isinstance(scope, dict) else None
    stages = [STAGE_TARGET.match(" ".join(str(g).split())) for g in groups or []]
    if not stages or not all(stages):
        return None
    kind, others = count.get("kind"), [o for o in siblings if o is not count]
    reserve, first = any(m["reserve"] for m in stages), any(m["first"] for m in stages)
    if reserve == first or (first and kind != "OFFERED"):
        return None
    if reserve and kind not in ("RESERVE", "WAITLIST") and (kind != "OFFERED" or any(o.get("kind") == "OFFERED" for o in others)):
        return None
    if any(o.get("kind") == kind and not (o.get("scope") or {}).get("targetGroups") for o in others):
        return None
    return ", ".join(map(str, groups or []))


class _Assembler:
    """AI 출력 조각을 합쳐 근거 위치·계산값을 붙인 extracted-notice 후보와 검수 이슈를 만드는 한 번 쓰는 작업 객체입니다."""

    def __init__(self, parts: list[Any], source: AssemblyInput):
        self.parts = parts
        self.source = source
        self.issues: list[tuple[list[str | int], str, str]] = []  # (원래 경로, 코드, 설명)
        self.notes: list[str] = []
        self.sections: dict[str, Any] = {}
        self.coverage: dict[str, dict[str, Any]] = {}
        self.missing: list[dict[str, Any]] = []  # 원래 경로 기준 (AI 보고, 비운 항목)
        self.computed_missing: list[dict[str, Any]] = []  # 항목을 뺀 뒤 경로 기준 (금액·지역 계산)
        self.computed_filled: set[str] = set()  # 결합기가 원문 근거로 채운 칸 (항목을 뺀 뒤 경로). AI 누락 기록은 해소된 것으로 봅니다
        self.computed_issues: list[dict[str, str]] = []  # 항목을 뺀 뒤 경로 기준의 이슈 (금액 빈칸 채우기)
        self.quotes: dict[str, dict[str, Any]] = {}
        self.removed: dict[tuple, set[int]] = defaultdict(set)  # 원래 배열 경로 → 뺀 원래 순번
        self.nulled: list[list[str | int]] = []

    def issue(self, tokens: list[str | int], code: str, description: str) -> None:
        self.issues.append((tokens, code, description))

    # 1. 응답 조각을 검사하고 합칩니다 (섹션별 호출, 결정 E2)
    def merge(self) -> None:
        validator = Draft202012Validator(ai_output.schema(), format_checker=FormatChecker())
        failed = {"status": "FAILED", "reason": "AI 응답 형식이 맞지 않습니다."}
        code_issues: list[dict[str, Any]] = []
        for number, part in enumerate(self.parts):
            if not isinstance(part, dict):
                self.issue([], "AI_OUTPUT_INVALID", f"{number}번째 응답이 객체가 아닙니다.")
                continue
            part = copy.deepcopy(part)
            code_issues += [i for i in part.pop(ai_output.CODE_ISSUES, None) or [] if isinstance(i, dict)]
            part = self.salvage(number, self.repair(number, part), validator)
            broken: set[str] = set()
            for error in validator.iter_errors(part):
                top = error.absolute_path[0] if error.absolute_path else None
                broken.add(top if isinstance(top, str) else "")
            if "" in broken or "quotes" in broken:
                self.issue([], "AI_OUTPUT_INVALID", f"{number}번째 응답의 형식이 맞지 않아 전체를 사용하지 않습니다.")
                for section in SECTIONS:
                    if section in part and section not in self.sections:  # 앞 응답에서 이미 받은 섹션의 범위 상태는 그대로 둡니다
                        self.coverage.setdefault(section, dict(failed))
                continue
            for quote in part.get("quotes", []):
                self.quotes[f"{number}:{quote['ref']}"] = quote
            reported = part.get("coverage", {}) if "coverage" not in broken else {}
            adopted: set[str] = set()  # 이 응답에서 받아들인 섹션
            for section in SECTIONS:
                if section in broken and section in part:
                    self.issue([section], "AI_OUTPUT_INVALID", f"{number}번째 응답의 {section} 형식이 맞지 않아 사용하지 않습니다.")
                    # 앞 응답에서 이미 제대로 받은 섹션이면 그 범위 상태(AI가 적은 PARTIAL 사유 포함)를 FAILED로 덮지 않습니다(검토 2026-10-20)
                    if section not in self.sections:
                        self.coverage[section] = dict(failed)
                elif section in part:
                    if section in self.sections:
                        self.issue([section], "SECTION_DUPLICATED", f"{section}이 여러 응답에 있어 처음 것만 사용합니다.")
                        continue
                    value = copy.deepcopy(part[section])
                    for _, node in _walk(value, []):
                        if "quoteRefs" in node:
                            node["quoteRefs"] = [f"{number}:{ref}" for ref in node["quoteRefs"]]
                    self.sections[section] = value
                    adopted.add(section)
                    if section in reported:
                        self.coverage[section] = dict(reported[section])
                        if section == "notice" and _total_not_written(reported[section]):
                            # 공고 전체 합계가 원문에 따로 없어 적지 않은 것은 덜 뽑은 것이 아닙니다(원문에 없는 값). 공고 기본 정보 PARTIAL은
                            # 공고 전체 검수가 되므로(2026-10-24 일곱 번째 채점: 「주택형별 모집호수는 있지만 공고 전체 합계는 따로 없어」로
                            # 맞는 공고가 통째로 비공개) 메모만 남기고 다 뽑은 것으로 봅니다
                            self.notes.append(
                                f"/notice: AI가 「{reported[section].get('reason')}」로 일부라고 적었지만 원문에 없는 합계라 다 뽑은 것으로 봤어요"
                            )
                            self.coverage[section] = {"status": "EXTRACTED", "reason": None}
                    elif self.coverage.get(section, {}).get("status") == "FAILED":  # 앞 응답이 깨져 남긴 FAILED는 이 응답 내용과 맞지 않습니다
                        del self.coverage[section]
                elif section in reported and reported[section]["status"] in {"NOT_IN_SOURCE", "NOT_APPLICABLE", "FAILED"}:
                    self.coverage.setdefault(section, dict(reported[section]))
            if "missingFields" not in broken:
                for entry in part.get("missingFields", []):
                    # 이 응답에서 받아들이지 않은 섹션(중복·형식 오류·다른 응답이 맡은 섹션)을 가리키는 누락 기록은
                    # 다른 응답의 항목에 잘못 붙어 엉뚱한 MISSING_FIELD_HAS_VALUE를 만들므로 뺍니다(검토 2026-10-20)
                    section = entry["target"].lstrip("/").split("/", 1)[0]
                    if section in SECTIONS and section not in adopted:
                        self.notes.append(
                            f"{entry['target']}: {number}번째 응답에서 받아들이지 않은 섹션을 가리키는 누락 기록이라 뺐습니다 ({entry['description']})"
                        )
                        continue
                    self.missing.append(copy.deepcopy(entry))
        # 코드 조각의 검수 이슈: 가리키는 공급 묶음 자리로(묶음을 못 찾으면 공급 섹션)
        groups = self.sections.get("supplyGroups")
        positions = {g.get("id"): i for i, g in enumerate(groups) if isinstance(g, dict)} if isinstance(groups, list) else {}
        # field가 있으면(수량만 애매함 counts, 가격만 애매함 prices) 그 칸을 가리켜 그 칸만 보류합니다(2026-10-24, verifier.held_target)
        for entry in code_issues:
            at = positions.get(entry.get("supplyGroupId"))
            field = entry.get("field") if entry.get("field") in ("counts", "prices") else None
            tokens: list[str | int] = ["supplyGroups", at, *([field] if field else [])] if at is not None else ["supplyGroups"]
            self.issue(tokens, str(entry.get("code")), str(entry.get("description")))

    def repair(self, number: int, part: dict[str, Any]) -> dict[str, Any]:
        """뜻이 분명한 형식 실수를 고쳐 항목이 빠지지 않게 합니다(실측 2026-10-17 OpenAI dcco-24788).
        - 같은 응답 안에서 id가 겹치면(가점표 행마다 같은 id) 뒤 항목에 「.2」「.3」을 붙입니다. 예전에는 DUPLICATE_ID로 7행이 빠졌습니다.
          다른 항목이 id로 가리키는 섹션(공급 묶음·위치)은 고치지 않습니다.
        - 하루짜리 일정(공고일·발표일)을 endStatus FIXED로 적고 endsAt을 비우면 시작값을 종료값으로 씁니다. 예전에는 형식 오류로 빠졌습니다.
          시작이 시각(MINUTE)·월(MONTH)이면 복사하지 않고 끝을 「원문에 없음」(NOT_IN_SOURCE)으로 둡니다: 「14:00 이후 발표」가
          「14:00~14:00」으로 보였습니다(2026-10-23). 날짜(DAY)만 있는 하루짜리 일정만 시작값을 끝으로 씁니다."""
        for section in ("schedules", "selectionRules", "requiredDocuments", "guidance", "eligibility"):
            items = part.get(section)
            if not isinstance(items, list):
                continue
            seen: dict[str, int] = {}
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                count = seen.get(item["id"], 0) + 1
                seen[item["id"]] = count
                if count > 1:
                    new_id = f"{item['id']}.{count}"
                    while new_id in seen:
                        count += 1
                        new_id = f"{item['id']}.{count}"
                    seen[new_id] = 1
                    self.issue([section], "AI_OUTPUT_ID_RENAMED", f"{number}번째 응답의 겹친 id {item['id']}를 {new_id}로 바꿨습니다: {_label(item)}")
                    item["id"] = new_id
        for item in part.get("schedules") or []:
            if isinstance(item, dict) and item.get("endStatus") == "FIXED" and item.get("endsAt") is None and isinstance(item.get("startsAt"), dict):
                if item["startsAt"].get("precision") == "DAY":
                    item["endsAt"] = copy.deepcopy(item["startsAt"])
                elif item.get("endCondition") is None:  # 시각(MINUTE)·월(MONTH)
                    item["endStatus"] = "NOT_IN_SOURCE"
                    self.issue(["schedules"], "AI_OUTPUT_VALUE_CHANGED", f"끝 날짜가 없어 끝 상태를 FIXED에서 NOT_IN_SOURCE로 바꿨습니다: {_label(item)}")
        fix_format_slips(part)  # 엄격 모드가 채운 빈 사유·추첨 순서 번호 등(slips.py). 예전엔 가점표 12행이 형식 오류로 빠졌습니다
        # 소득 기준 연도가 항목 원문에 「전년도」「당해연도」처럼 공고일 기준으로만 있으면 버전에 그 원문 표현을 적습니다. 연도·버전이 둘 다 비면
        # 계약 검사(INCOMPLETE_INCOME_BENCHMARK)에 걸려 소득 조건이 통째로 빠졌습니다(실측 2026-10-17 dcco-24788).
        # 연도는 여기서 넣지 않고 fill_benchmark_years가 같은 표현과 공고일로 계산합니다. 뜻이 다른 표현이 함께 있으면 고르지 않습니다.
        for section in ("eligibility", "selectionRules"):
            for item in part.get(section) or []:
                if not isinstance(item, dict):
                    continue
                found = _relative_years(f"{item.get('originalText') or ''} {item.get('description') or ''}")
                if len(found) != 1:
                    continue
                [word] = found.values()
                for _, node in _walk(item, []):
                    benchmark = node.get("benchmark") if node.get("attribute") == "INCOME_BENCHMARK_PERCENT" else None
                    if isinstance(benchmark, dict) and benchmark.get("referenceYear") is None and not benchmark.get("referenceVersion"):
                        benchmark["referenceVersion"] = word
        return part

    def salvage(self, number: int, part: dict[str, Any], validator: Draft202012Validator) -> dict[str, Any]:
        """형식 오류가 난 곳만 빼서 섹션을 살립니다 (2026-10-16 항목 격리). 예전에는 오류 하나로 섹션 전체(예: 자격 조건 12개)를 버렸습니다.
        자격 조건의 예외 하나가 틀리면 그 예외만 빼고(조건은 사람 확인), 그 밖에는 틀린 항목만 뺍니다.
        일정·서류는 틀린 칸만 안전한 값으로 바꿔 항목을 남깁니다(coerce.py, 2026-10-23). 일정의 종류·날짜·범위처럼 뜻이 있는 칸을 바꿨으면
        보류(AI_OUTPUT_ITEM_COERCED → 화면 「확인 필요」), 접수 장소·시각 같은 덧붙인 칸만 비웠으면 표시 메모입니다. 바꿔도 틀리면 뺍니다."""
        coerced: dict[int, tuple[str, dict[str, Any], list[str], bool]] = {}  # 항목 객체 id → (섹션, 항목, 바꾼 칸, 뜻 있는 칸을 바꿨는지)
        for _ in range(4):
            items: dict[str, set[int]] = defaultdict(set)
            exceptions: dict[int, set[int]] = defaultdict(set)
            errors: dict[tuple[str, int], list[Any]] = defaultdict(list)
            for error in validator.iter_errors(part):
                path = list(error.absolute_path)
                if len(path) < 2 or path[0] not in SECTIONS or path[0] == "notice" or not isinstance(path[1], int):
                    continue
                if path[0] == "eligibility" and len(path) >= 4 and path[2] == "exceptions" and isinstance(path[3], int):
                    exceptions[path[1]].add(path[3])
                else:
                    items[path[0]].add(path[1])
                    errors[(path[0], path[1])].append(error)
            if not items and not exceptions:
                break
            for section in COERCIBLE:
                for index in sorted(items.get(section, set())):
                    item = part[section][index]
                    if id(item) in coerced or not isinstance(item, dict):
                        continue  # 이미 한 번 바꿨는데도 틀리면 아래에서 뺍니다
                    fixed = coerce_item(section, item, errors[(section, index)], part)
                    if fixed is not None:
                        coerced[id(item)] = (section, item, *fixed)
                        items[section].discard(index)
                if section in items and not items[section]:
                    del items[section]
            for index, positions in exceptions.items():
                if index in items["eligibility"]:
                    continue
                condition = part["eligibility"][index]
                for position in sorted(positions, reverse=True):
                    del condition["exceptions"][position]
                condition["exceptionsStatus"] = "NOT_REVIEWED"
                shift = sum(1 for removed in items["eligibility"] if removed < index)
                self.issue(
                    ["eligibility", index - shift],
                    "AI_OUTPUT_ITEM_DROPPED",
                    f"{_label(condition)}: 형식이 맞지 않는 예외 {len(positions)}개를 뺐습니다. 원문의 예외를 확인해야 합니다",
                )
            for section, indexes in items.items():
                for index in indexes:
                    coerced.pop(id(part[section][index]), None)
                labels = [_label(part[section][i]) for i in sorted(indexes) if isinstance(part[section][i], dict)]
                for index in sorted(indexes, reverse=True):
                    del part[section][index]
                _shift_missing(part, section, indexes)
                self.issue([section], "AI_OUTPUT_ITEM_DROPPED", f"{number}번째 응답에서 형식이 맞지 않는 항목 {len(indexes)}개를 뺐습니다: {', '.join(labels)}")
                # AI가 이미 PARTIAL로 적었으면 그 사유(무엇이 빠졌는지)를 덮어쓰지 않습니다
                coverage = part.get("coverage") if isinstance(part.get("coverage"), dict) else {}
                if isinstance(coverage.get(section), dict) and coverage[section].get("status") == "EXTRACTED":
                    coverage[section] = {"status": "PARTIAL", "reason": DROPPED_INVALID}
        for section, item, fields, meaningful in coerced.values():
            index = next(i for i, x in enumerate(part[section]) if x is item)
            names = ", ".join(fields)
            if meaningful:
                self.issue(
                    [section, index],
                    "AI_OUTPUT_ITEM_COERCED",
                    f"{number}번째 응답의 {_label(item)}: 형식이 맞지 않는 칸({names})을 안전한 값으로 바꿨어요. 원문 확인 전까지 쓰지 않아요",
                )
            else:  # 일정 항목을 가리키면 그 일정이 접수 기간에서 빠지므로 섹션을 가리킵니다(details.py와 같음)
                target = [section] if section == "schedules" else [section, index]
                self.issue(target, "AI_OUTPUT_FIELD_CLEARED", f"{number}번째 응답의 {_label(item)}: 형식이 맞지 않는 칸({names})을 비웠어요")
        return part

    # 2. 인용문 → 근거 위치
    def resolve_evidence(self) -> list[dict[str, Any]]:
        material = self.source.material
        documents = {d["id"]: d for d in self.source.context.documents}
        index = NormalizedText(material.text)
        evidence: list[dict[str, Any]] = []
        keys: dict[tuple, str] = {}

        def evidence_id(source_id: str, locator: dict[str, Any], quote: str) -> str:
            key = (source_id, tuple(sorted(locator.items())))
            if key not in keys:
                keys[key] = f"ev-{len(keys) + 1}"
                evidence.append({"id": keys[key], "sourceId": source_id, "locator": locator, "quote": quote})
            return keys[key]

        for section in SECTIONS:
            previous: tuple[int, int] | None = None  # 같은 섹션에서 바로 앞 항목의 근거 위치
            for tokens, node in list(_walk(self.sections.get(section), [section])):
                if "quoteRefs" not in node:
                    continue
                ids: list[str] = []
                text_quotes: list[dict[str, Any]] = []
                not_found: list[str] = []
                for ref in node.pop("quoteRefs"):
                    quote = self.quotes.get(ref)
                    if quote is None:
                        self.issue(tokens, "QUOTE_REF_UNKNOWN", f"없는 인용 참조입니다: {ref.split(':', 1)[1]}")
                    elif quote["documentId"] == material.text_document_id:
                        text_quotes.append(quote)
                    elif quote["documentId"] == material.units_document_id and material.units_document_id in documents:
                        row = quote.get("unitRow")
                        if row is not None and row < len(material.units) and quote_in_unit_row(material.units[row], quote["text"]):
                            ids.append(evidence_id(material.units_document_id, {"kind": "UNIT_ROW", "pointer": f"/{row}"}, quote["text"]))
                        else:
                            not_found.append(f"호별 표 {row}번 행 「{_short(quote['text'], QUOTE_CHARS)}」")
                    elif quote["documentId"] in documents:
                        self.issue(tokens, "EVIDENCE_SOURCE_UNSUPPORTED", f"{quote['documentId']} 문서 근거는 아직 위치를 계산하지 않습니다.")
                    else:
                        self.issue(tokens, "EVIDENCE_SOURCE_UNKNOWN", f"전달되지 않은 문서입니다: {quote['documentId']}")
                split_quotes = []
                for quote in text_quotes:  # 이어 붙인 인용은 원문에 있는 조각들로 나눠 각각 근거로 씁니다(quotes.split_joined_quote)
                    parts = split_joined_quote(material.text, quote["text"], index)
                    if parts:
                        self.notes.append(f"{_pointer(tokens)}: 원문의 두 곳 이상을 이어 쓴 인용을 조각 {len(parts)}개로 나눠 근거로 썼습니다.")
                    split_quotes += [{**quote, "text": part} for part in parts] if parts else [quote]
                text_quotes = split_quotes
                resolutions = resolve_item_quotes(material.text, [q["text"] for q in text_quotes], index)
                groups = self._target_groups(tokens)
                resolutions = [choose_by_target_groups(material.text, r, groups) for r in resolutions]
                # 짧은 칸 글자(「보훈대상자」「참전유공자」)가 원문 여러 곳에 있으면 바로 앞 항목 근거에 가장 가까운 곳을 고릅니다.
                # 배점표·서류표의 행은 차례로 이어져 있습니다(실측 2026-10-18 LH 강릉 영구임대: 가점 8행이 위치를 못 정해 빠짐)
                resolutions = [choose_near(r, previous) for r in resolutions]
                if tokens and tokens[0] == "schedules":
                    # 날짜만 있는 인용(공고문 끝의 「2026. 03. 24.」)은 원문 여러 곳에 같은 날짜가 있어도 값이 같으므로 첫 위치를 씁니다.
                    # 예전엔 위치를 못 정해 공고일 일정이 통째로 빠졌습니다(실측 LH 다자녀 전세임대)
                    resolutions = [
                        dataclasses.replace(r, status=QuoteStatus.CHOSEN_FIRST, span=r.candidates[0])
                        if r.status is QuoteStatus.AMBIGUOUS and r.candidates and BARE_DATE.fullmatch(r.quote.strip())
                        else r
                        for r in resolutions
                    ]
                if tokens and tokens[0] == "requiredDocuments":
                    # 서류 이름은 서류표가 원문에 두 번(글자 덩어리·표) 나와도 뜻이 같아 첫 위치를 씁니다.
                    # 예전엔 서류표 첫 행(앞 항목 근거 없음)이 위치를 못 정해 빠졌습니다(실측 청약홈 에코델타: 동의서·등본)
                    resolutions = [
                        dataclasses.replace(r, status=QuoteStatus.CHOSEN_FIRST, span=r.candidates[0])
                        if r.status is QuoteStatus.AMBIGUOUS and r.candidates
                        else r
                        for r in resolutions
                    ]
                if resolutions and all(r.span is None for r in resolutions):  # 다른 근거가 하나라도 있으면 못 찾은 인용은 그대로 검수로
                    resolutions = [self._original_text_fallback(tokens, node, r, index) for r in resolutions]
                for text, resolution in zip([q["text"] for q in text_quotes], resolutions, strict=True):
                    in_order = find_in_order(index, text, resolution.span) if resolution.scattered and resolution.span is not None else None
                    if in_order is not None:  # 순서대로 찾은 범위를 근거 위치로 씁니다
                        resolution = dataclasses.replace(resolution, span=in_order[0])
                    if resolution.span is not None:
                        start, end = resolution.span
                        locator = {"kind": "TEXT_RANGE", "start": start, "end": end}
                        ids.append(evidence_id(material.text_document_id, locator, material.text[start:end]))
                    if in_order is not None:
                        # 낱말 순서가 원문과 같고 짧은 글자만 끼어 있어(표 머리 칸이 문장 사이에 섞여 읽힘) 뜻이 뒤집힐 수 없습니다
                        skipped = ", ".join(f"「{g}」" for g in in_order[1])
                        self.notes.append(f"{_pointer(tokens)}: 인용 낱말 순서는 원문과 같고 사이에 낀 원문 글자 {skipped}만 인용에 없어 근거로 썼습니다.")
                    elif resolution.scattered and resolution.span is not None:
                        # 낱말이 모인 범위로 근거 위치는 정하지만(순서도·칸 없는 표) 낱말 순서는 보지 않습니다.
                        # 「소득 … 단, 자산 초과 시 제외」와 「자산 … 단, 소득 초과 시 제외」처럼 뜻이 뒤집힌 인용도 찾아지므로,
                        # 판정에 쓰는 항목은 자동 통과하지 않게 검수로 보냅니다(검토 2026-10-20)
                        if _scatter_needs_review(tokens):
                            quote_text = _short(text, QUOTE_CHARS)
                            self.issue(
                                tokens,
                                "EVIDENCE_SCATTERED",
                                f"{_label(node)}: 인용문이 원문에 이어진 문장으로 없고 낱말만 흩어져 있어 순서·뜻을 확인해야 합니다 「{quote_text}」",
                            )
                        else:
                            self.notes.append(f"{_pointer(tokens)}: 원문 글자 순서가 뒤섞여(순서도·칸 없는 표) 인용의 낱말들이 모인 범위를 근거로 썼습니다.")
                    if resolution.status is QuoteStatus.CHOSEN_NEAREST:
                        self.notes.append(f"{_pointer(tokens)}: 여러 곳에 있는 인용문 중 같은 항목의 다른 근거와 가장 가까운 곳을 골랐습니다.")
                    elif resolution.status is QuoteStatus.CHOSEN_FIRST:
                        self.notes.append(f"{_pointer(tokens)}: 같은 문장이 {len(resolution.candidates)}곳에 반복되어 첫 위치를 근거로 썼습니다.")
                    elif resolution.status is QuoteStatus.AMBIGUOUS:
                        self.issue(
                            tokens,
                            "EVIDENCE_AMBIGUOUS",
                            f"{_label(node)}: 인용문이 원문 {len(resolution.candidates)}곳에 있어 위치를 정하지 못했습니다 「{_short(text, QUOTE_CHARS)}」",
                        )
                    elif resolution.status is QuoteStatus.NOT_FOUND:
                        not_found.append(f"「{_short(text, QUOTE_CHARS)}」")
                    if resolution.too_short:
                        self.issue(tokens, "EVIDENCE_QUOTE_TOO_SHORT", f"{_label(node)}: 인용문이 너무 짧아 우연히 일치했을 수 있습니다 「{text}」")
                if not_found:  # 한 항목에서 못 찾은 인용문은 이슈 하나로 모읍니다
                    listed = ", ".join(not_found)
                    self.issue(tokens, "EVIDENCE_QUOTE_NOT_FOUND", f"{_label(node)}: 인용문 {len(not_found)}개를 원문에서 찾지 못했습니다 {listed}")
                node["evidenceIds"] = list(dict.fromkeys(ids))
                located = [r.span for r in resolutions if r.span is not None]
                if located:
                    previous = located[-1]
                if not ids:
                    self.mark_unsupported(tokens)
        return evidence

    def _original_text_fallback(self, tokens: list[str | int], node: dict[str, Any], resolution: QuoteResolution, index: NormalizedText) -> QuoteResolution:
        """항목의 인용을 하나도 못 찾거나 위치가 모두 모호할 때, 같은 항목의 originalText가 원문 한 곳에서 찾아지면 그것을 근거로 씁니다.
        실측: 고령자 항목이 originalText는 "① 【완화조건】 소득요건 배제"인데 인용 참조는 청년 부분의 "③ …"를 가리킴."""
        original = node.get("originalText")
        if resolution.status not in (QuoteStatus.AMBIGUOUS, QuoteStatus.NOT_FOUND) or not isinstance(original, str) or not original.strip():
            return resolution
        if normalize(strip_markers(original)) == normalize(strip_markers(resolution.quote)):
            return resolution
        [found] = resolve_item_quotes(self.source.material.text, [original], index)
        if found.status is not QuoteStatus.FOUND or found.too_short:
            return resolution
        self.notes.append(f"{_pointer(tokens)}: 인용 참조 「{_short(resolution.quote, QUOTE_CHARS)}」 대신 항목 원문(originalText)으로 근거 위치를 정했습니다.")
        # originalText도 흩어진 낱말로 찾았을 수 있어 그 표시를 넘깁니다(판정 항목이면 검수 이슈)
        return QuoteResolution(resolution.quote, QuoteStatus.FOUND, found.span, found.candidates, found.exact, False, found.scattered)

    def _target_groups(self, tokens: list[str | int]) -> list[str]:
        """인용이 달린 항목이 속한 목록 항목(자격 조건 등)의 대상 계층 이름."""
        if len(tokens) >= 2 and isinstance(tokens[1], int):
            item = _get(self.sections, tokens[:2])
            if isinstance(item, dict):
                groups = (item.get("scope") or {}).get("targetGroups") or []
                return [g for g in groups if isinstance(g, str) and g.strip()]
        return []

    def mark_unsupported(self, tokens: list[str | int]) -> None:
        for size in range(len(tokens), 0, -1):
            head = tokens[:size]
            if head[-1] in NULLABLE_OBJECTS:
                self.nulled.append(head)
                return
            if isinstance(head[-1], int) and size >= 2 and head[-2] in RECORD_ARRAYS:
                self.removed[tuple(head[:-1])].add(head[-1])
                return
        self.issue(tokens, "ITEM_WITHOUT_EVIDENCE", "근거를 확인하지 못한 공고 기본 정보입니다.")

    # 3. 근거 없는 항목 정리 (깊은 경로부터, 같은 배열은 뒤 순번부터 지워 앞 순번이 밀리지 않게 합니다)
    def drop_unsupported(self) -> None:
        def covered(path: tuple) -> bool:
            """이미 빠지는 상위 항목 안에 있는 경로인지."""
            return any(len(path) > len(a) and path[: len(a)] == a and path[len(a)] in idx for a, idx in list(self.removed.items()))

        for path in [p for p in self.removed if covered(p)]:
            del self.removed[path]
        self.nulled = [p for p in self.nulled if not covered(tuple(p))]
        for tokens in self.nulled:
            label = _label(_get(self.sections, tokens))
            _get(self.sections, tokens[:-1])[tokens[-1]] = None
            self.missing.append({"target": _pointer(tokens), "reason": "NEEDS_REVIEW", "description": "근거를 확인하지 못해 비웠습니다."})
            self.issue(tokens, "ITEM_DROPPED_NO_EVIDENCE", f"{label}: 근거를 확인하지 못해 비웠습니다.")
        for path in sorted(self.removed, key=len, reverse=True):
            array = _get(self.sections, list(path))
            labels = [_label(array[index]) for index in sorted(self.removed[path])]
            for index in sorted(self.removed[path], reverse=True):
                del array[index]
            self.issue(list(path), "ITEM_DROPPED_NO_EVIDENCE", f"근거를 확인하지 못한 항목 {len(labels)}개를 뺐습니다: {', '.join(labels)}")
        for section in {p[0] for p in [*self.removed, *map(tuple, self.nulled)]}:
            if self.coverage.get(section, {}).get("status") in {None, "EXTRACTED"}:
                self.coverage[section] = {"status": "PARTIAL", "reason": DROPPED_NO_EVIDENCE}

    def remap(self, tokens: list[str | int]) -> list[str | int] | None:
        """원래 경로 → 항목을 뺀 뒤의 경로. 빠진 항목 안을 가리키면 None."""
        out: list[str | int] = []
        for depth, token in enumerate(tokens):
            removed = self.removed.get(tuple(tokens[:depth]))
            if removed and isinstance(token, int):
                if token in removed:
                    return None
                token -= sum(1 for r in removed if r < token)
            out.append(token)
        return out

    # 4. 계산값: 금액, 지역 코드
    def fill_missing_prices(self, evidence: list[dict[str, Any]]) -> None:
        """공급표 금액 빈칸을 공고문 글에서 채웁니다(missing_prices.py, 요구 2-06). 채운 칸의 금액 계산 누락과 AI 누락 기록은 해소된 것으로 봅니다."""
        material = self.source.material
        reasons = {}
        for entry in self.missing:  # AI 누락 기록(원래 경로) → 항목을 뺀 뒤 경로
            moved = self.remap([int(t) if t.isdigit() else t for t in entry["target"].lstrip("/").split("/")])
            if moved is not None:
                reasons[_pointer(moved)] = entry["reason"]
        filled = fill_missing_prices(self.sections.get("supplyGroups") or [], material.text, material.text_document_id, evidence, reasons)
        evidence.extend(filled.evidence)
        self.computed_filled.update(filled.filled)
        self.computed_missing = [m for m in self.computed_missing if m["target"] not in filled.filled]
        self.notes.extend(filled.notes)
        self.computed_issues.extend({"code": code, "target": _pointer(tokens), "description": text} for tokens, code, text in filled.issues)

    # 5. 수량 묶음 정리: 묶음 정보(부모·합계 완결)가 맞지 않으면 값은 두고 묶음만 풉니다
    def normalize_counts(self) -> None:
        counts: dict[str, dict[str, Any]] = {}
        where: dict[str, list[str | int]] = {}
        for section in SECTIONS:
            for tokens, node in _walk(self.sections.get(section), [section]):
                siblings = [c for c in node.get("counts") or [] if isinstance(c, dict)]
                for i, count in enumerate(node.get("counts") or []):
                    if isinstance(count, dict) and "id" in count:
                        counts[count["id"]] = count
                        where[count["id"]] = [*tokens, "counts", i]
                        stage = _stage_only(count, siblings)
                        if stage:
                            count["scope"]["targetGroups"] = []
                            text = f"모집 단계(「{stage}」)는 수량 종류({count.get('kind')})로 나타내므로 대상에서 뺐습니다(값은 그대로)"
                            self.issue(where[count["id"]], "AI_OUTPUT_VALUE_CHANGED", text)
        for count_id, count in counts.items():
            parent_id = count.get("parentCountId")
            if parent_id is None:
                continue
            parent = counts.get(parent_id)
            if parent is None or parent_id == count_id or parent.get("aggregationRole") != "TOTAL" or parent.get("kind") != count.get("kind"):
                count["parentCountId"] = None
                if count.get("aggregationRole") == "COMPONENT":
                    count["aggregationRole"] = "STANDALONE"
                self.issue(where[count_id], "AI_OUTPUT_VALUE_CHANGED", f"상위 합계({parent_id})와 맞지 않아 수량 묶음을 풀었습니다(값은 그대로)")
        for count_id, count in counts.items():
            if not count.get("aggregationComplete"):
                continue
            children = [c for c in counts.values() if c.get("parentCountId") == count_id]
            if count.get("aggregationRole") != "TOTAL" or not children or count.get("value") is None or any(c.get("value") is None for c in children):
                count["aggregationComplete"] = False
                self.issue(where[count_id], "AI_OUTPUT_VALUE_CHANGED", "구성 수량이 다 있지 않아 '합계 완결' 표시를 지웠습니다")

    def fill_benchmark_years(self) -> None:
        """소득 기준 연도를 「전년도」「당해연도」처럼 공고일 기준으로만 적었으면 공고일 연도에서 계산하고, 원문 표현은 referenceVersion에 그대로 둡니다.
        기준 이름·버전에서 먼저 찾고, 없으면 그 항목의 원문(originalText·description)에서 찾습니다. 뜻이 다른 표현이 섞여 있으면 계산하지 않습니다.
        실측: 청년 매입임대 "전년도 도시근로자 가구당 월평균소득의 100%" → referenceYear가 비어 조건식이 통째로 격리됨.
        예전엔 repair가 버전에 「전년도」를 적으면 여기서 건너뛰어 연도가 계속 비었습니다(검토 2026-10-20)."""
        announced = str((self.sections.get("notice") or {}).get("announcedOn") or "")
        if not re.match(r"\d{4}-", announced):
            return
        for section in ("eligibility", "selectionRules"):
            for i, item in enumerate(self.sections.get(section) or []):
                if not isinstance(item, dict):
                    continue
                item_text = f"{item.get('originalText') or ''} {item.get('description') or ''}"
                for tokens, node in _walk(item, [section, i]):
                    benchmark = node.get("benchmark") if node.get("kind") == "ATOMIC" else None
                    if not isinstance(benchmark, dict) or benchmark.get("referenceYear") is not None:
                        continue
                    version = benchmark.get("referenceVersion")
                    if version is not None and not _relative_years(version):  # 「2025년 고시」처럼 상대 표현이 아닌 버전은 그대로 둡니다
                        continue
                    name = str(benchmark.get("standardName") or "")
                    found = {**_relative_years(name), **_relative_years(version)}
                    basis = f"기준 이름 '{name}'" if _relative_years(name) else f"버전 '{version}'"
                    if not found:
                        found, basis = _relative_years(item_text), "항목 원문"
                    if len(found) > 1:
                        self.notes.append(f"{_pointer(tokens)}: 소득 기준 연도 표현이 여러 가지({', '.join(found.values())})라 연도를 계산하지 않았습니다")
                        continue
                    if not found:
                        continue
                    [(offset, word)] = found.items()
                    benchmark["referenceYear"] = int(announced[:4]) + offset
                    self.computed_filled.add(f"{_pointer(tokens)}/benchmark/referenceYear")
                    self.notes.append(
                        f"{_pointer(tokens)}: 소득 기준 연도를 {basis}의 「{word}」와 공고일({announced})로 계산했습니다({benchmark['referenceYear']}년)"
                    )

    def compute_values(self) -> None:
        """가격에 원 단위 금액(또는 금액 범위)을, 위치에 법정동코드를 붙입니다. 계산하지 못한 칸은 누락 사유로 남깁니다."""
        for g, group in enumerate(self.sections.get("supplyGroups", [])):
            for p, price in enumerate(group["prices"]):
                result = to_krw(price.get("sourceAmount"), price.get("sourceUnit"))
                price["amountKrw"] = result.amount_krw
                span = None if result.amount_krw is not None else range_krw(price.get("sourceAmount"), price.get("sourceUnit"))
                if span is not None:  # 원문이 「1,200만~1,500만」처럼 범위로만 적은 금액(계약 amountRangeKrw)
                    price["amountRangeKrw"] = {"min": span[0], "max": span[1]}
                elif result.amount_krw is None:
                    target = f"/supplyGroups/{g}/prices/{p}/amountKrw"
                    self.computed_missing.append({"target": target, "reason": "NEEDS_REVIEW", "description": result.reason})
        for i, location in enumerate(self.sections.get("locations", [])):
            if self.source.regions is None:
                match_code, note = None, "지역 코드표가 없습니다."
            else:
                match = self.source.regions.lookup(location.get("region"), self.source.default_sido, location.get("address"))
                match_code, note = match.code, match.note
            location["regionCode"] = match_code
            if match_code is None:
                self.computed_missing.append({"target": f"/locations/{i}/regionCode", "reason": "NEEDS_REVIEW", "description": note})
            elif note:
                self.notes.append(f"/locations/{i}/regionCode: {note}")

    def build(self) -> AssemblyResult:
        """합치기·근거 위치·정리·계산 단계를 차례로 돌려 후보를 만듭니다. 공고 기본 정보에 근거가 없으면 후보 없이 이슈만 돌려줍니다."""
        self.merge()
        if "notice" not in self.sections:
            reason = self.coverage.get("notice", {}).get("reason") or "AI 응답에 공고 기본 정보가 없습니다."
            self.issue(["notice"], "NOTICE_NOT_EXTRACTED", reason)
            return self.result(None)
        evidence = self.resolve_evidence()
        self.drop_unsupported()
        if not self.sections["notice"].get("evidenceIds"):
            return self.result(None)
        self.compute_values()
        self.fill_missing_prices(evidence)
        self.normalize_counts()
        self.fill_benchmark_years()

        context = self.source.context
        sections = {s: self.sections.get(s, []) for s in SECTIONS}
        if sections["notice"]["field"] not in (None, context.input["field"]):
            self.issue(["notice", "field"], "INPUT_FIELD_MISMATCH", "AI가 읽은 분야가 수집 분야와 다릅니다.")
        coverage = {s: self.coverage.get(s, {"status": "NOT_ATTEMPTED", "reason": "AI 응답에 이 섹션이 없습니다."}) for s in SECTIONS}
        missing = []
        for entry in self.missing:
            tokens = [int(t) if t.isdigit() else t for t in entry["target"].lstrip("/").split("/")]
            moved = self.remap(tokens)
            if moved is None:
                continue
            try:
                value = tools().resolve(sections, _pointer(moved))
            except (KeyError, IndexError, TypeError, ValueError):
                # AI가 없는 칸을 가리킨 누락 기록: 가리킬 값이 없으니 버리고 메모만 남깁니다
                self.notes.append(f"{entry['target']}: 없는 칸을 가리키는 누락 기록이라 뺐습니다 ({entry['description']})")
                continue
            if _pointer(moved) in self.computed_filled:
                # 실측(일괄 75건 중 8건): AI가 소득 기준 연도를 누락으로 보고 → 결합기가 공고일로 채움 → 모순으로 검수에 가던 것
                self.notes.append(f"{entry['target']}: AI 누락 기록을 결합기가 채운 값으로 해소했습니다 ({entry['description']})")
                continue
            if value is not None and value != []:
                # AI가 '누락'이라 하고 값도 채운 모순: 누락 기록은 빼고 검수 사유로 남깁니다
                self.issue(tokens, "MISSING_FIELD_HAS_VALUE", f"AI가 누락이라고 보고했지만 값이 있습니다: {entry['description']}")
                continue
            missing.append({**entry, "target": _pointer(moved)})
        missing.extend(self.computed_missing)
        candidate = {
            "schemaVersion": "1.0.0",
            "target": "NOTICE",
            "input": dict(context.input),
            "sourceReferences": [dict(r) for r in context.source_references],
            "documents": [dict(d) for d in context.documents],
            **sections,
            "evidence": evidence,
            "quality": {
                "coverage": coverage,
                "missingFields": list({m["target"]: m for m in missing}.values()),
                "reviewIssues": [],
                "notes": [],
                "verification": {
                    "status": "NOT_RUN",
                    "sourceStatus": "NOT_RUN",
                    "checkedAt": None,
                    "rulesVersion": None,
                    "apiComparison": {"status": context.api_comparison_status, "referenceSha256": None, "referenceIdentity": None, "fields": []},
                },
            },
        }
        return self.result(candidate)

    def result(self, candidate: dict[str, Any] | None) -> AssemblyResult:
        issues = []
        for tokens, code, description in self.issues:
            moved = self.remap(tokens)
            while moved is None:  # 빠진 항목 안의 이슈는 그 항목이 있던 목록을 가리킵니다
                tokens = tokens[:-1]
                moved = self.remap(tokens)
            issues.append({"code": code, "target": _pointer(moved) or "/", "description": description})
        issues.extend(self.computed_issues)
        result = AssemblyResult(candidate, issues, self.notes)
        if candidate is not None:
            candidate["quality"]["reviewIssues"] = issues
            # 일정 접수 방법·장소·시각과 서류 묶음을 근거로 확인하고 같은 서류를 합칩니다(details.py). 합칠 때 위의 이슈 위치도 맞춥니다
            material = self.source.material
            self.notes.extend(check_details(candidate, material.text, material.text_document_id))
            result.contract_errors = tools().validate(candidate, "schemas/extracted-notice.v1.json")
        return result


def assemble(parts: list[Any], source: AssemblyInput) -> AssemblyResult:
    """parts: 섹션별 호출로 받은 AI 출력 조각들(파싱된 JSON). 인용 참조(ref)는 조각 안에서만 유효합니다."""
    return _Assembler(parts, source).build()
