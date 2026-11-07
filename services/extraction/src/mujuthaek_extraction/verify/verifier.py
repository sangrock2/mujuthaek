"""검증 실행과 최종 판정 (설계 5장).

검수 등급: 판정에 쓰지 않는 섹션(서류·일정·공급·위치·선정)의 근거 위치 문제는 quality.notes로 옮겨 자동 처리합니다(화면 표시만).
sourceStatus = PASSED ⇔ notes로 옮기지 않은 V2·V3·V5 문제 없음
status       = PASSED ⇔ V1 통과 ∧ sourceStatus PASSED ∧ API 대조가 MATCHED·NO_COMPARABLE_FIELDS·SKIPPED_NO_API_REFERENCE
                         ∧ 검수 이슈(reviewIssues) 없음 ∧ 공고·자격 섹션 완전 ∧ 그 밖의 섹션은 실패·미시도 없음
PASSED여도 계약의 완료 조건(ready 검사)으로 한 번 더 확인하고, 걸리면 REVIEW_REQUIRED로 되돌립니다.
AI 응답의 자기 보고로 PASSED가 되는 경로는 없습니다. 입력 후보는 바꾸지 않고 새 후보를 돌려줍니다.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from mujuthaek_extraction.assemble.coverage import self_reported_partial
from mujuthaek_extraction.assemble.details import refresh_application_channels
from mujuthaek_extraction.assemble.quarantine import remove_item
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.model import ApiReference
from mujuthaek_extraction.verify.api_compare import compare_api
from mujuthaek_extraction.verify.claims import check_claims
from mujuthaek_extraction.verify.consistency import check_consistency
from mujuthaek_extraction.verify.directions import check_directions
from mujuthaek_extraction.verify.evidence import check_evidence
from mujuthaek_extraction.verify.exceptions import check_missing_exceptions
from mujuthaek_extraction.verify.model import RULES_VERSION, Finding, PdfTextExtractor, SourceBundle, VerificationReport
from mujuthaek_extraction.verify.numbers import check_numbers

SCHEMA = "schemas/extracted-notice.v1.json"
API_OK = {"MATCHED", "NO_COMPARABLE_FIELDS", "SKIPPED_NO_API_REFERENCE"}
# 검수 등급 (2026-10-15 결정: AI 재확인 후에도 남으면 사람 확인은 판정에 영향 주는 것만)
CRITICAL_SECTIONS = {"notice", "eligibility"}
# 근거 위치 문제: 판정에 쓰지 않는 섹션이면 자동 처리(항목 제외·표시)하고 quality.notes로 옮깁니다
NOTE_CODES = {
    "EVIDENCE_QUOTE_NOT_FOUND",
    "EVIDENCE_AMBIGUOUS",
    "EVIDENCE_QUOTE_TOO_SHORT",
    "ITEM_DROPPED_NO_EVIDENCE",
    "CLAIM_UNSUPPORTED",
    "ORIGINAL_TEXT_NOT_FOUND",
    "MISSING_FIELD_HAS_VALUE",
    "AI_OUTPUT_ITEM_DROPPED",
    "ITEM_QUARANTINED",
    # AI가 없는 인용 참조를 적음: 그 참조는 근거로 쓰지 않고, 남은 근거가 없으면 항목이 빠집니다(EVIDENCE_QUOTE_NOT_FOUND와 같은 처리).
    # 실측 LH 신혼·신생아 매입임대: 일정 6개가 빠진 뒤 이 이슈 9개가 /schedules에 남아 일정 섹션 전체가 보류됨(2026-10-20)
    "QUOTE_REF_UNKNOWN",
    # 정답표 없이 하는 검사(V7 수량 합계·V8 누락): 의심이라 판정 섹션에서만 사람 확인
    # 값이 틀렸다는 신호(V6 표 위치 VALUE_POSITION_SUSPECTED, V7 일정 순서·가격 범위·월세가 보증금보다 큼, V9 원문 어디에도 없는 값
    # VALUE_NOT_IN_QUOTE)는 여기 넣지 않습니다(2026-10-21). 공급·일정이어도 메모로 두면 틀린 값이 그대로 게시되므로,
    # 재확인으로 못 고치면 그 항목만 보류합니다(부분 게시). 틀린 값보다 누락이 낫습니다
    "COUNT_TOTAL_SUSPECTED",
    "SECTION_OMISSION_SUSPECTED",
    "SCORING_OMISSION_SUSPECTED",
    "LIST_OMISSION_SUSPECTED",
    "ELIGIBILITY_OMISSION_SUSPECTED",
    "SUPPLY_PRICE_UNATTACHED",
    # 원문 서류 표 행을 어느 서류도 인용하지 않음(consistency, 2026-10-23). 빠진 값이지 틀린 값이 아니라 표시만 하고,
    # AI 재확인에는 보냅니다(recheck.RECHECK_NOTE_CODES: 서류 섹션 전체를 다시 읽어 빠진 서류만 더함)
    "DOCUMENT_OMISSION_SUSPECTED",
    # V9 비교 방향 대조(OPERATOR_MISMATCH)는 넣지 않습니다: 자격 항목에만 걸리고, 방향이 반대면 판정이 뒤집히므로 늘 사람 확인입니다
    # 그림 판독 글자(AI가 옮김)를 근거로 한 공급·일정 등은 표시만. 자격·공고 정보는 EVIDENCE_FROM_IMAGE로 사람 확인
    "IMAGE_TRANSCRIBED_VALUES",
    # 근거에서 확인하지 못한 일정 접수 방법·장소·시각, 서류 부수·발급 기관을 비움(details.py), 형식이 틀린 덧붙인 칸을 비움(coerce.py).
    # 틀린 값은 이미 지웠으므로 표시만 합니다(2026-10-23). 일정의 종류·날짜 등 뜻 있는 칸을 바꾼 AI_OUTPUT_ITEM_COERCED는 넣지 않습니다(보류)
    "DETAIL_UNVERIFIED_CLEARED",
    "AI_OUTPUT_FIELD_CLEARED",
    # 공급표 전환안의 부호와 숫자가 어긋나 숫자(기본 요금 대비 보증금·월세 증감)로 방향을 고침(supply_tables, 2026-10-24). 고친 값이라 표시만
    "CONVERSION_DIRECTION_CORRECTED",
    # 행 이름 칸이 없어 읽지 못한 가격표(supply_tables, 2026-11-07). 빠진 값이지 틀린 값이 아니라 읽은 가격은 게시하고 검수 대기열에만 올립니다
    "SUPPLY_PRICE_TABLE_UNREAD",
}
# 공통 검사(2026-10-26 사용자 결정 「모두 검수, 공개 유지」): AI·원본이 준 값을 비우거나 빼거나 바꾼 표시. 판정 섹션 밖이라 메모로 내려가도,
# 이 코드가 하나라도 있으면 공고는 공개한 채 검수 대기열에 올립니다(store.save). 값을 버리는 새 처리를 만들면 여기 코드 중 하나를 남기세요
DROPPED_VALUE_CODES = {
    "ITEM_DROPPED_NO_EVIDENCE",
    "AI_OUTPUT_ITEM_DROPPED",
    "ITEM_QUARANTINED",
    "DETAIL_UNVERIFIED_CLEARED",
    "AI_OUTPUT_FIELD_CLEARED",
    "AI_OUTPUT_VALUE_CHANGED",
    # 원문 안에서 같은 자격의 판단 기준일이 엇갈림(check_basis_date_conflict). 어느 쪽이 맞는지 원문만으로 못 정해 사람이 봅니다
    "SOURCE_BASIS_DATE_CONFLICT",
    "SUPPLY_PRICE_TABLE_UNREAD",
}
# 비교를 못 했을 뿐 불일치가 아닌 API 대조 결과: 섹션과 상관없이 표시만 (불일치 API_MISMATCH는 사람 확인)
# API_VALUE_NOT_EXTRACTED: API에는 값이 있는데 추출값이 비어 있음(누락). 틀린 값이 아니라 빠진 값이라 공고를 막지 않습니다(2026-10-20)
ALWAYS_NOTE_CODES = {
    "API_TARGET_MISSING",
    "API_SCOPE_AMBIGUOUS",
    "API_MAPPING_MISSING",
    "API_VALUE_NOT_EXTRACTED",
    # 공고일이 근거 인용문에는 없지만 원문의 공고일 표기나 같은 공고의 API 공고일로 값이 확인됨(claims.py). 값은 맞으므로 표시만
    "VALUE_CONFIRMED_IN_SOURCE",
    "VALUE_CONFIRMED_BY_API",
    "INCOME_CRITERION_UNUSED",
    "AI_OUTPUT_ID_RENAMED",
    # AI가 준 값을 프로그램이 더 안전한 쪽으로 바꾸거나 비움(수량 묶음 풀기·참조 정리·재확인 교체로 사라진 값 등, 2026-10-26).
    # 바꾼 값을 숨기지(보류) 않고 메모로 두되, DROPPED_VALUE_CODES라 공고는 검수 대기열에 오릅니다
    "AI_OUTPUT_VALUE_CHANGED",
    "SOURCE_BASIS_DATE_CONFLICT",
}
# INCOME_CRITERION_UNUSED: 소득 기준 일부 누락 의심. 실측 정밀도가 낮아(재계약·완화 표 등) 검수자 화면 메모로만 둡니다(2026-10-16)


SETTLED_REASONS = {"NOT_IN_SOURCE", "NOT_APPLICABLE", "TO_BE_ANNOUNCED"}  # 원문이 없다·해당 없다·추후 통보라고 확인된 빈칸 (계약과 같음)


def is_note(issue: dict[str, str]) -> bool:
    if issue["code"] in ALWAYS_NOTE_CODES:
        return True
    section = issue["target"].lstrip("/").split("/", 1)[0]
    return issue["code"] in NOTE_CODES and section not in CRITICAL_SECTIONS and section != ""


def _gate_findings(result: dict[str, Any], contract: Any, known: list[str], now: str) -> list[Finding]:
    """완료 조건(범위 미확정·미해결 누락·미검토 예외 등)은 PASSED일 때만 검사되어 다른 문제가 다 풀린 뒤에야 드러납니다.
    처음부터 PASSED로 가정해 미리 검사하고, 걸리는 것을 검수 대상에 올려 AI 재확인이 한 번에 고칠 수 있게 합니다."""
    probe = copy.deepcopy(result)
    probe["quality"]["reviewIssues"] = []
    # API 대조는 따로 판정하므로 여기서는 통과 값으로 둡니다(스키마 오류로 의미 검사가 건너뛰어지지 않게)
    neutral_api = {"status": "SKIPPED_NO_API_REFERENCE", "referenceSha256": None, "referenceIdentity": None, "fields": []}
    probe["quality"]["verification"].update(status="PASSED", sourceStatus="PASSED", checkedAt=now, rulesVersion=RULES_VERSION, apiComparison=neutral_api)
    errors = [e for e in contract.validate(probe, SCHEMA) if e not in known and not e.startswith("SCHEMA")]
    return [_error_finding(e) for e in errors]


def check_reported_partial(result: dict[str, Any]) -> list[Finding]:
    """AI가 원문에 있는데 다 옮기지 못했다고 스스로 적은 섹션(PARTIAL). 판정 섹션은 계약 검사가 이미 막으므로 그 밖의 섹션만 봅니다.
    재확인이 빠진 항목을 채우지 못하면 사람 확인으로 갑니다(가점표·일정·서류가 빠진 채 자동 완료되지 않게)."""
    return [
        Finding(
            "V8",
            "COVERAGE_PARTIAL_REPORTED",
            f"/quality/coverage/{section}",
            f"원문에 있는데 다 옮기지 못했다고 적은 섹션입니다: {entry.get('reason') or '사유 없음'}",
        )
        for section, entry in result["quality"]["coverage"].items()
        if section not in CRITICAL_SECTIONS and self_reported_partial(entry)
    ]


# 일본어 가나·한자. 원문에 없는 이 글자가 AI가 쓴 문장에 섞이면(2026-10-26 원문 대조: 「入주개시일」, 「증빙する」, 「수령내역など」)
# 회원 화면에 그대로 보이므로, 그 칸이 든 항목을 보류하고 검수로 보냅니다. 원문에 있는 글자(한자 병기 등)는 잡지 않습니다
FOREIGN_SCRIPT = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
FOREIGN_SCRIPT_SKIP = {"quality", "sourceDocuments", "evidence"}  # 검증 기록·원문 인용(원문 글자 그대로)은 보지 않습니다


def check_foreign_script(result: dict[str, Any], sources: SourceBundle) -> list[Finding]:
    """AI가 쓴 글에 원문에 없는 가나·한자가 섞인 칸. 칸마다 하나씩, 그 칸의 위치를 가리킵니다(항목 단위로 보류)."""
    source = "".join(sources.texts.values())
    findings: list[Finding] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key not in FOREIGN_SCRIPT_SKIP:
                    walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}/{i}")
        elif isinstance(node, str):
            foreign = sorted({c for c in FOREIGN_SCRIPT.findall(node) if c not in source})
            if foreign:
                findings.append(
                    Finding("V2", "AI_TEXT_FOREIGN_SCRIPT", path, f"원문에 없는 외국 문자({''.join(foreign)})가 섞인 글입니다. 한국어로 고쳐 주세요")
                )

    walk({k: v for k, v in result.items() if k not in FOREIGN_SCRIPT_SKIP}, "")
    return findings


# 자격 판단 기준일(「공고일 현재 무주택」, 「신청일 현재 소득」). 같은 자격에 기준일이 둘 이상이면 원문 안 충돌입니다
# (2026-10-26 원문 대조: 「입주자 모집공고일이 입주자격 판단 기준일」과 「신청일 현재 무주택세대구성원」이 한 공고에 같이 있음).
# 서로 다른 자격·항목에 다른 기준일을 쓰는 것(임대조건은 공고일, 중소기업 요건은 신청일)은 충돌이 아닙니다
BASIS_DAY = r"(입주자\s*모집\s*공고일|모집\s*공고일|공고일|청약\s*신청일|신청일|서류\s*접수일|접수일|계약\s*체결일|계약일)"
BASIS_ANCHOR = re.compile(BASIS_DAY + r"\s*(?:\([^)]{0,20}\))?\s*(?:현재|기준)")
BASIS_DAY_WORD = re.compile(BASIS_DAY)
BASIS_CRITERIA = ("무주택", "소득", "자산", "혼인", "거주")
BASIS_ALL = re.compile(r"(입주\s*자격|신청\s*자격)[^.\n]{0,15}(판단|판정)\s*기준일")
BASIS_SENTENCE = re.compile(r"(?<=[.。])\s|\n|•|※|·\s")  # 문장·항목 나누기


def _basis_name(anchor: str) -> str:
    name = re.sub(r"\s", "", anchor)
    for long, short in (("입주자모집공고일", "공고일"), ("모집공고일", "공고일"), ("청약신청일", "신청일"), ("서류접수일", "접수일"), ("계약체결일", "계약일")):
        name = name.replace(long, short)
    return name


def check_basis_date_conflict(result: dict[str, Any], sources: SourceBundle) -> list[Finding]:
    """원문 문장마다 자격(무주택·소득·자산·혼인·거주)과 판단 기준일을 모아, 한 자격에 기준일이 둘 이상이면 메모 하나를 냅니다.
    「입주자격 판단 기준일은 공고일」처럼 자격 전체에 거는 문장은 모든 자격에 셉니다. 자격 조건이 없는 공고는 보지 않습니다."""
    if not result.get("eligibility"):
        return []
    found: dict[str, set[str]] = {}
    for text in sources.texts.values():
        for sentence in BASIS_SENTENCE.split(text):
            whole = BASIS_ALL.search(sentence)
            # 「입주자격 판단 기준일은 모집공고일」처럼 자격 전체를 정하는 문장은 「현재·기준」 없이 날짜 이름만 써요
            anchors = {_basis_name(m.group(1)) for m in (BASIS_DAY_WORD if whole else BASIS_ANCHOR).finditer(sentence)}
            if not anchors:
                continue
            names = list(BASIS_CRITERIA) if whole else [n for n in BASIS_CRITERIA if n in sentence]
            for name in names:
                found.setdefault(name, set()).update(anchors)
    conflicts = {name: sorted(dates) for name, dates in found.items() if len(dates) > 1}
    if not conflicts:
        return []
    text = ", ".join(f"{name}: {'·'.join(dates)}" for name, dates in conflicts.items())
    return [
        Finding(
            "V7",
            "SOURCE_BASIS_DATE_CONFLICT",
            "/eligibility",
            f"원문에서 같은 자격의 판단 기준일이 엇갈립니다({text}). 어느 날짜 기준인지 원문을 확인해 주세요",
        )
    ]


def _dicts(node: Any):
    if isinstance(node, dict):
        yield node
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            yield from _dicts(child)


def drop_unknown_notice_counts(result: dict[str, Any]) -> None:
    """공고 전체 수량(/notice/counts) 가운데 값이 비었고 누락 사유가 미확정(별첨 필요·확인 필요 등)인 항목을 빼고 메모로 남깁니다.
    공고 정보는 판정 섹션이라 계약상 미확정 누락이 있으면 완료할 수 없고, /notice는 보류도 할 수 없어 공고 전체가 검수로 갔습니다
    (실측 LH 든든전세: 모집 인원이 별첨 목록에만 있음). 값이 없는 항목이라 빼도 틀린 값은 게시되지 않습니다(누락 + 메모).
    다른 수량이 상위 수량으로 가리키는 항목은 빼지 않습니다. 결과를 그 자리에서 바꿉니다."""
    quality, counts = result["quality"], result["notice"]["counts"]
    parents = {node.get("parentCountId") for node in _dicts(result) if node.get("parentCountId")}
    for index in reversed(range(len(counts))):
        pointer = f"/notice/counts/{index}"
        missing = (m for m in quality["missingFields"] if isinstance(m, dict) and m.get("target") == pointer + "/value")
        entry = next((m for m in missing if m.get("reason") not in SETTLED_REASONS), None)
        count = counts[index]
        if entry is None or not isinstance(count, dict) or count.get("value") is not None or count.get("id") in parents:
            continue
        remove_item(result, pointer)
        description = f"{entry['description']} (값을 알 수 없어({entry['reason']}) 이 수량 항목을 뺐습니다. 원문 확인 필요)"
        quality["notes"].append({"code": "UNKNOWN_COUNT_DROPPED", "target": "/notice/counts", "description": description})


def _incomplete(section: str, status: str) -> bool:
    return status in ({"PARTIAL", "NOT_ATTEMPTED", "FAILED"} if section in CRITICAL_SECTIONS else {"NOT_ATTEMPTED", "FAILED"})


def _error_finding(error: str) -> Finding:
    code, _, rest = error.partition(" ")
    target = rest.split(":", 1)[0].strip() or "/"
    return Finding("V1", f"CONTRACT_{code}", target if target.startswith("/") else "/", error)


def verify_extraction(
    candidate: dict[str, Any],
    sources: SourceBundle,
    api_reference: ApiReference | None,
    *,
    clock: Callable[[], datetime],
    pdf_text: PdfTextExtractor | None = None,
) -> VerificationReport:
    """후보 사본에 모든 검사를 돌려 검수 이슈·표시 메모를 나누고 PASSED·PARTIALLY_PASSED·REVIEW_REQUIRED를 판정해 돌려줍니다."""
    result = copy.deepcopy(candidate)
    quality = result["quality"]
    quality["verification"] = {
        "status": "NOT_RUN",
        "sourceStatus": "NOT_RUN",
        "checkedAt": None,
        "rulesVersion": None,
        "apiComparison": quality["verification"]["apiComparison"],
    }
    contract = tools()
    refresh_application_channels(result)  # 결합 뒤 항목 격리(quarantine)로 일정이 빠졌을 수 있습니다
    if isinstance(result.get("notice"), dict) and isinstance(result["notice"].get("counts"), list) and isinstance(quality.get("missingFields"), list):
        drop_unknown_notice_counts(result)

    contract_errors = contract.validate(result, SCHEMA)
    findings = [_error_finding(e) for e in contract_errors]
    schema_broken = any(e.startswith("SCHEMA") for e in contract_errors)
    if not schema_broken:
        comparison, api_findings = compare_api(result, api_reference)
        api_matched = frozenset(f["target"] for f in comparison["fields"] if f["status"] == "MATCH")
        source_findings = check_evidence(result, sources, pdf_text) + check_numbers(result, sources) + check_missing_exceptions(result, sources)
        source_findings += check_consistency(result, sources) + check_claims(result, sources, api_matched=api_matched)
        source_findings += (
            check_directions(result) + check_reported_partial(result) + check_foreign_script(result, sources) + check_basis_date_conflict(result, sources)
        )
        findings += source_findings + api_findings + _gate_findings(result, contract, contract_errors, clock().isoformat())
        quality["verification"]["apiComparison"] = comparison
        blocking = [f for f in source_findings if not is_note(f.issue())]
        quality["verification"]["sourceStatus"] = "REVIEW_REQUIRED" if blocking else "PASSED"
    else:
        quality["verification"]["sourceStatus"] = "NOT_RUN"

    existing = {(i["code"], i["target"]) for i in quality["reviewIssues"]}
    for finding in findings:
        if (finding.code, finding.target) not in existing:
            quality["reviewIssues"].append(finding.issue())
            existing.add((finding.code, finding.target))
    narrow_notice_issues(result)
    for entry in quality["missingFields"]:  # 판정에 쓰지 않는 칸의 미확정 값은 표시만 합니다
        section = entry["target"].lstrip("/").split("/", 1)[0]
        if entry["reason"] not in SETTLED_REASONS and section not in CRITICAL_SECTIONS:
            quality["notes"].append({"code": "MISSING_FIELD_NEEDS_REVIEW", "target": entry["target"], "description": entry["description"]})
    quality["notes"] = list({(i["code"], i["target"], i["description"]): i for i in [*quality["notes"], *filter(is_note, quality["reviewIssues"])]}.values())
    quality["reviewIssues"] = [i for i in quality["reviewIssues"] if not is_note(i)]

    passed = (
        not contract_errors
        and quality["verification"]["sourceStatus"] == "PASSED"
        and quality["verification"]["apiComparison"]["status"] in API_OK
        and not quality["reviewIssues"]
        and not any(_incomplete(section, entry["status"]) for section, entry in quality["coverage"].items())
    )
    held = None if passed or schema_broken else hold_plan(result, contract_errors)
    status = "PASSED" if passed else "PARTIALLY_PASSED" if held else "REVIEW_REQUIRED"
    quality["verification"].update(status=status, checkedAt=clock().isoformat(), rulesVersion=RULES_VERSION)
    if held:
        quality["heldItems"] = held

    if status != "REVIEW_REQUIRED":  # 완료 조건(근거 있는 필드 평가, 누락 사유, 미검토 예외 등)을 계약 검사기로 다시 확인합니다
        ready_errors = contract.validate(result, SCHEMA)
        if ready_errors:
            gate = [_error_finding(e) for e in ready_errors]
            findings += gate
            quality["reviewIssues"].extend(f.issue() for f in gate)
            quality["verification"]["status"] = "REVIEW_REQUIRED"
            quality.pop("heldItems", None)
            contract_errors = ready_errors
    return VerificationReport(candidate=result, findings=findings, contract_errors=contract_errors)


# ---- 부분 완료 (2026-10-17 설계 검토: 영향 범위만 보류) ----
# 공고 수천 건을 전부 사람이 볼 수 없으므로, 검수 이슈가 특정 항목·섹션에만 있으면 공고는 게시하고 그 범위만 '원문 확인 필요'로 보류합니다.
# 공고 정체성(제목·기관·분야)·입력·원본 문서·계약 형식 오류는 보류할 수 없어 공고 전체가 검수로 갑니다.
# 공고 기본 정보 중 공고일·공급 유형·설명·대상 계층·공고 전체 수량은 칸 단위로 보류합니다(2026-10-20 결정, 계약 NOTICE_HOLDABLE).
# API 불일치도 그 칸이 보류할 수 있는 곳이면 그 칸만 보류합니다(실측: 남은 공고 전체 검수 7건 중 4건이 API 공고일 불일치, API 쪽이 틀림).
LIST_SECTIONS = ("locations", "supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "guidance")


# 공급 묶음 안에서 칸 단위로 보류하는 곳(2026-10-24 세 번째 채점: 병합 칸 수량만 애매한 묶음을 통째로 보류해 맞는 가격 120값이 숨음).
# 수량(counts)·가격(prices) 칸의 문제는 그 목록만 보류하고 묶음의 주택형·면적·나머지 칸은 게시합니다. 가격은 요금안끼리 짝(보증금·월세)이라
# 가격 하나가 아니라 그 묶음의 가격 목록 전체를 보류합니다. 그 밖의 칸(주택형·면적·범위)은 묶음의 정체라 묶음 전체를 보류합니다
GROUP_FIELD_HOLDS = ("counts", "prices")


# 공고 기본 정보 근거 이슈(2026-10-24 다섯 번째 채점: 대상 계층 「청년」의 근거 인용 「① 청년」이 짧다는 이슈가 노드 /notice를 가리켜
# 보류할 수 없어 공고 전체가 검수로 감 — 맞는 가격 150·서류 66·일정 5가 모두 비공개). 인용이 받치는 칸이 하나로 정해지면 그 칸을 가리키게
# 바꿔 칸만 보류합니다(대상 계층은 판정에 쓰므로 메모로 내리지 않고 보류). 정해지지 않으면 그대로 둡니다(공고 전체 검수)
NOTICE_EVIDENCE_CODES = {"EVIDENCE_QUOTE_TOO_SHORT", "EVIDENCE_QUOTE_NOT_FOUND", "EVIDENCE_AMBIGUOUS", "EVIDENCE_SCATTERED"}
QUOTED = re.compile(r"「([^」]*)」\s*$")


def _flat(text: Any) -> str:
    return "".join(str(text or "").split())


def notice_field_of(notice: dict[str, Any], quote: str) -> str | None:
    """인용이 받치는 공고 칸: 대상 계층 이름이 인용 안에 있으면 targetGroups, 공급 유형 이름이 있으면 supplyType. 둘 다거나 없으면 None."""
    flat = _flat(quote)
    fields = set()
    if any(_flat(group) and _flat(group) in flat for group in notice.get("targetGroups") or []):
        fields.add("targetGroups")
    if _flat(notice.get("supplyType")) and _flat(notice.get("supplyType")) in flat:
        fields.add("supplyType")
    return fields.pop() if len(fields) == 1 else None


def narrow_notice_issues(candidate: dict[str, Any]) -> None:
    notice = candidate.get("notice") if isinstance(candidate.get("notice"), dict) else {}
    for issue in candidate["quality"]["reviewIssues"]:
        if issue.get("target") != "/notice" or issue.get("code") not in NOTICE_EVIDENCE_CODES:
            continue
        quoted = QUOTED.search(issue.get("description") or "")
        field = notice_field_of(notice, quoted[1]) if quoted else None
        if field:
            issue["target"] = f"/notice/{field}"


def held_target(candidate: dict[str, Any], pointer: str) -> tuple[str, str] | None:
    """검수 이슈 위치 → 보류할 (범위, ITEM/SECTION). 보류할 수 없는 위치면 None."""
    pointer = pointer.split(" ", 1)[0]
    parts = pointer.lstrip("/").split("/")
    if pointer.startswith("/quality/coverage/") and len(parts) >= 3 and parts[2] in LIST_SECTIONS:
        return f"/{parts[2]}", "SECTION"
    if pointer.startswith("/quality/missingFields/") and len(parts) >= 3 and parts[2].isdigit():
        entries = candidate["quality"]["missingFields"]
        index = int(parts[2])
        return held_target(candidate, entries[index]["target"]) if index < len(entries) else None
    if parts[0] == "counts" and len(parts) >= 2:  # 수량 규칙 오류(/counts/<수량 id>): 그 수량을 가진 공급 묶음
        for g, group in enumerate(candidate["supplyGroups"]):
            if any(c.get("id") == parts[1] for c in group.get("counts") or []):
                return f"/supplyGroups/{g}", "ITEM"
        return None
    if parts[0] == "notice" and len(parts) >= 2 and parts[1] in tools().NOTICE_HOLDABLE:
        if parts[1] == "counts" and len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) < len(candidate["notice"]["counts"]):
            return f"/notice/counts/{parts[2]}", "ITEM"
        return f"/notice/{parts[1]}", "ITEM"
    if parts[0] in LIST_SECTIONS:
        if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) < len(candidate[parts[0]]):
            if parts[0] == "supplyGroups" and len(parts) >= 3 and parts[2] in GROUP_FIELD_HOLDS:
                return f"/supplyGroups/{parts[1]}/{parts[2]}", "ITEM"
            return f"/{parts[0]}/{parts[1]}", "ITEM"
        return f"/{parts[0]}", "SECTION"
    return None


def hold_plan(candidate: dict[str, Any], contract_errors: list[str]) -> list[dict[str, Any]] | None:
    """모든 검수 이슈·미완 섹션을 보류 범위로 묶을 수 있으면 보류 목록, 하나라도 공고 전체 문제면 None."""
    quality = candidate["quality"]
    comparison = quality["verification"]["apiComparison"]
    if quality["verification"]["sourceStatus"] == "NOT_RUN":
        return None
    if comparison["status"] not in API_OK:
        # 불일치한 칸이 모두 보류할 수 있는 곳일 때만 부분 게시합니다(그 칸의 API_MISMATCH 이슈가 아래에서 보류됨)
        mismatched = [f["target"] for f in comparison["fields"] if f["status"] == "MISMATCH"]
        if comparison["status"] != "MISMATCH" or not mismatched or any(held_target(candidate, t) is None for t in mismatched):
            return None
    if _incomplete("notice", quality["coverage"]["notice"]["status"]):
        return None
    held: dict[str, dict[str, Any]] = {}

    def add(target: str, extent: str, code: str, description: str) -> None:
        entry = held.setdefault(target, {"target": target, "extent": extent, "codes": [], "description": description})
        if code not in entry["codes"]:
            entry["codes"].append(code)

    for issue in quality["reviewIssues"]:
        found = held_target(candidate, issue["target"])
        if found is None:
            return None
        add(*found, issue["code"], "확인 전까지 판정·화면에 쓰지 않습니다(원문 확인 필요)")
    for error in contract_errors:
        code, _, pointer = error.partition(" ")
        found = held_target(candidate, pointer)
        if found is None:
            return None
        add(*found, f"CONTRACT_{code}", "계약 완료 조건을 채우지 못해 확인 전까지 쓰지 않습니다")
    for section, entry in quality["coverage"].items():
        if section != "notice" and _incomplete(section, entry["status"]):
            add(f"/{section}", "SECTION", f"COVERAGE_{entry['status']}", "섹션을 다 추출하지 못해 확인 전까지 쓰지 않습니다")
    if not held:
        return None
    # 넓은 보류(섹션 전체, 항목 전체)가 있으면 그 안의 좁은 보류(항목, 칸)는 넓은 쪽에 합칩니다
    for target in sorted(held, key=len):
        if target not in held:
            continue
        for inner in [t for t in held if t.startswith(target + "/")]:
            held[target]["codes"] = list(dict.fromkeys([*held[target]["codes"], *held.pop(inner)["codes"]]))
    return list(held.values())
