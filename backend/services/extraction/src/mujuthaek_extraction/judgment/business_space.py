"""사업공간 판정 틀(business-space-judgment.v1) 가공. 코드만 씁니다(공통 뼈대는 frame.py).

- 자격 조건식(원자 조건) → 나이·국적·지역(주소지·사업장)·사업자 등록·영업 경력·업종.
- 문장만 있는 신청 제한(피성년후견인, LH 직원 가족, 세금 체납, 금융 불량거래, 휴업) → 신청 제한 사유(EXCLUDED_STATUS).
  제한 문장에 코드 밖의 사유가 섞였으면 inReview(그 사유는 판정되지 않으므로).
- 우대: 선정 규칙 중 가점(SCORING, 점수 있음)·「우대」 우선순위 → preferences. 그 밖의 선정 규칙은 notes(SELECTION).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_extraction.judgment.common import LIMIT_WORDS, Context, ask_whole, base_fields, status_codes, status_rest, statuses_of
from mujuthaek_extraction.judgment.frame import Criterion, Made, Spec, as_int, bounds, build_frame
from mujuthaek_extraction.judgment.sanity import INVERTED

# 대상 이름·신분 정의 문장 → 틀의 유형 코드(예비사회적기업을 사회적기업보다 먼저 봅니다)
STATUS_WORDS = (
    (re.compile(r"예비\s*사회적\s*기업"), "PRE_SOCIAL_ENTERPRISE"),
    (re.compile(r"사회적\s*협동\s*조합"), "SOCIAL_COOPERATIVE"),
    (re.compile(r"(?<!예비)(?<!예비\s)사회적\s*기업"), "SOCIAL_ENTERPRISE"),
    (re.compile(r"마을\s*기업"), "VILLAGE_ENTERPRISE"),
    (re.compile(r"자활\s*기업"), "SELF_SUFFICIENCY_ENTERPRISE"),
    (re.compile(r"소셜\s*벤처"), "SOCIAL_VENTURE"),
    (re.compile(r"경력\s*단절\s*여성"), "CAREER_BREAK_WOMAN"),
    (re.compile(r"소상공인"), "SMALL_BUSINESS"),
    (re.compile(r"국가\s*유공자|보훈\s*대상자?"), "NATIONAL_MERIT"),
)
EXCLUDED_WORDS = (
    (re.compile(r"피\s*성년\s*후견|피\s*한정\s*후견"), "ADULT_WARD"),
    (re.compile(r"(?:LH|한국토지주택공사)\s*(?:임\s*)?직원"), "LH_EMPLOYEE_FAMILY"),
    (re.compile(r"(?:국세|지방세|세금)[^.]{0,20}체납|체납[^.]{0,10}(?:국세|지방세)"), "TAX_ARREARS"),
    (re.compile(r"(?:금융|신용)[^.]{0,20}(?:불량|연체|채무\s*불이행)|불량\s*거래자"), "CREDIT_DELINQUENT"),
    (re.compile(r"휴업"), "BUSINESS_SUSPENDED"),
)
OTHER_LIMITS = re.compile(r"파산|회생|금고|징역|형의\s*집행|부정|불법|위반|적발|계약\s*(?:해지|해제)|명도|미납|부도|영업\s*정지")
REVISIONS = ((re.compile(r"11\s*차"), 11), (re.compile(r"10\s*차"), 10))


def _atom(ctx: Context, item: dict[str, Any], node: dict[str, Any], quote: str | None, when: date) -> Criterion | None:
    attribute, op, value, subject = node["attribute"], node["operator"], node["value"], node.get("subject")
    span = bounds(node)
    new = lambda: ctx.new_id(item["id"])  # noqa: E731
    if attribute == "AGE_YEARS" and span and subject in ("APPLICANT", "REPRESENTATIVE"):
        if span[0] is not None and span[1] is not None and span[0] > span[1]:
            return ask_whole(ctx, item, quote, INVERTED)  # 거꾸로 된 범위는 틀 읽기가 틀 전체를 거절함
        return {**base_fields(new(), "AGE", quote), "minAge": as_int(span[0]), "maxAge": as_int(span[1])}
    if attribute == "NATIONALITY_CODE" and op in ("EQ", "IN"):
        codes = value if isinstance(value, list) else [value]
        return {**base_fields(new(), "NATIONALITY", quote), "countryCodes": list(dict.fromkeys(codes))}
    if attribute in ("RESIDENCE_REGION_CODE", "BUSINESS_REGION_CODE") and op in ("EQ", "IN"):
        codes = value if isinstance(value, list) else [value]
        basis = "RESIDENCE" if attribute == "RESIDENCE_REGION_CODE" else "BUSINESS_SITE"
        return {**base_fields(new(), "REGION", quote), "basis": basis, "regionCodes": list(dict.fromkeys(codes))}
    if attribute == "BUSINESS_REGISTERED" and op == "EQ" and isinstance(value, bool):
        return {**base_fields(new(), "BUSINESS_REGISTRATION", quote), "require": "REGISTERED" if value else "NOT_REGISTERED", "closedWithinYears": None}
    if attribute == "BUSINESS_AGE_MONTHS" and span and span[0] is not None and span[1] is None and span[0] >= 1:
        return {**base_fields(new(), "BUSINESS_CAREER", quote), "minMonths": int(span[0]), "withinYears": None}
    if attribute == "INDUSTRY_CODE" and op in ("EQ", "IN", "NE", "NOT_IN"):
        codes = [str(c) for c in (value if isinstance(value, list) else [value])]
        name = str((node.get("benchmark") or {}).get("standardName") or "")
        revision = next((number for pattern, number in REVISIONS if pattern.search(name)), None)
        if revision is None or not all(re.fullmatch(r"[0-9]{2,5}", c) for c in codes):
            return None
        return {
            **base_fields(new(), "INDUSTRY", quote),
            "mode": "ONLY" if op in ("EQ", "IN") else "EXCLUDE",
            "revision": revision,
            "codes": list(dict.fromkeys(codes)),
            "maybeCodes": [],
        }
    return None


def _simplify(criterion: Criterion) -> Criterion:
    """「주소지 또는 사업장이 ○○」(같은 지역의 주소지 길과 사업장 길) → 지역 하나(RESIDENCE_OR_BUSINESS_SITE)."""
    options = criterion["options"]
    regions = [o["criteria"][0] for o in options if len(o["criteria"]) == 1 and o["criteria"][0]["kind"] == "REGION"]
    if len(options) == 2 and len(regions) == 2 and {r["basis"] for r in regions} == {"RESIDENCE", "BUSINESS_SITE"}:
        if sorted(regions[0]["regionCodes"]) == sorted(regions[1]["regionCodes"]):
            return {
                **{k: v for k, v in criterion.items() if k != "options"},
                "kind": "REGION",
                "basis": "RESIDENCE_OR_BUSINESS_SITE",
                "regionCodes": regions[0]["regionCodes"],
            }
    return criterion


def _text(ctx: Context, item: dict[str, Any], text: str, reasons: list[str]) -> Made | None:
    """신청 제한 문장 → 신청 제한 사유. 코드에 없는 제한 낱말(파산·형 집행·불법·계약 해지 등)이 함께 있으면 그 사유는 판정되지 않으므로 inReview."""
    if not LIMIT_WORDS.search(text):
        return None
    codes = [code for pattern, code in EXCLUDED_WORDS if pattern.search(text)]
    if not codes:
        return None
    excluded = {**base_fields(ctx.new_id(item["id"]), "EXCLUDED_STATUS", text), "anyOf": codes}
    extra = ["제한 문장에 코드로 옮기지 못한 사유가 함께 있습니다"] if OTHER_LIMITS.search(text) else []
    ctx.flag(excluded, [*reasons, *extra])
    return [excluded], []


SPEC = Spec(
    schema="business-space-judgment.v1",
    atom=_atom,
    statuses_of=lambda name: statuses_of(name, STATUS_WORDS),
    status_codes=lambda text: status_codes(text, STATUS_WORDS),
    status_rest=lambda text: status_rest(text, STATUS_WORDS),
    text=_text,
    simplify=_simplify,
    preferences=True,
    rule_words=(r"중복\s*신청", r"1\s*인\s*1\s*(?:점포|호)"),
    obligation=r"(?:입점|계약|개업)\s*(?:전|후|시)\s*까지.*(?:증명|제출|등록)|입점\s*후",
)


def build_business_space(candidate: dict[str, Any], regions: Any = None, *, approved: bool = False) -> dict[str, Any] | None:
    return build_frame(candidate, regions, SPEC, approved=approved)
