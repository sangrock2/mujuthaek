"""출처 코드 칸 → 조건·일정 (AI 없이 규칙으로, benefit-condition-types.draft.md 5장).

지금은 온통청년(youth)만 옮깁니다. 정부24 지원조건(JA 코드)은 실제 수집 자료로 칸 이름을 확인한 뒤 넣습니다(2026-10-25 로컬 수집 DB에
정부24·복지로 자료가 없어 짐작으로 만들지 않음). 그 출처는 AI가 글에서 읽습니다.

zipCd(정책 지역)는 거주 조건으로 옮기지 않습니다(2026-10-25 사용자 결정, 초안 5장과 다름). 온통청년 zipCd는 정책을 시행하는
지역이라 「그 지역 거주」가 아닌 정책(산단 임대주택, 보호자 거주 기숙사, 「거주 또는 재학·재직」)에도 붙어 있습니다. 지역은
source.regionCodes로 보내고, 거주 조건은 AI가 글에 적힌 대로 읽습니다.

규칙으로 만든 조건은 origin RULE, confidence 1, evidence는 그 값이 들어 있는 원문 줄(글에 없으면 「칸 이름: 값」)입니다.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# 온통청년 API 코드(API코드정보.xlsx). 「제한없음」 코드는 줄을 만들지 않습니다
JOB = {
    "0013001": ("EMPLOYMENT", "EMPLOYED"),
    "0013002": ("EMPLOYMENT", "SELF_EMPLOYED"),
    "0013003": ("EMPLOYMENT", "UNEMPLOYED"),
    "0013004": ("EMPLOYMENT", "FREELANCER"),
    "0013005": ("EMPLOYMENT", "DAILY_WORKER"),
    "0013006": ("EMPLOYMENT", "STARTUP"),
    "0013007": ("EMPLOYMENT", "SHORT_TERM"),
    "0013008": ("OCCUPATION", "FARMER"),
    "0013009": ("EMPLOYMENT", "OTHER"),
}
JOB_ANY = "0013010"
SCHOOL = {
    "0049001": "BELOW_HIGH",
    "0049002": "HIGH_ENROLLED",
    "0049003": "HIGH_GRAD_EXPECTED",
    "0049004": "HIGH_GRAD",
    "0049005": "UNIV_ENROLLED",
    "0049006": "UNIV_GRAD_EXPECTED",
    "0049007": "UNIV_GRAD",
    "0049008": "GRADUATE",
    "0049009": "OTHER",
}
SCHOOL_ANY = "0049010"
# 특화 분야: (type, 값). 값이 None이면 OTHER(글만 보여 줌)
SPECIAL = {
    "0014001": ("WORKPLACE", "SME"),
    "0014002": ("OTHER", "여성"),
    "0014003": ("WELFARE_STATUS", "BASIC_LIVELIHOOD"),
    "0014004": ("HOUSEHOLD_TYPE", "SINGLE_PARENT"),
    "0014005": ("SPECIAL_STATUS", "DISABLED"),
    "0014006": ("OCCUPATION", "FARMER"),
    "0014007": ("SPECIAL_STATUS", "SOLDIER"),
    "0014008": ("OTHER", "지역인재"),
    "0014009": ("OTHER", "기타"),
}
SPECIAL_ANY = "0014010"
MARITAL = {"0055001": "MARRIED", "0055002": "SINGLE"}  # 0055003 제한없음
# 원문 칸(rawText)에 보여 줄 한글 이름(온통청년 코드표 이름)
KO = {
    "EMPLOYED": "재직자",
    "SELF_EMPLOYED": "자영업자",
    "UNEMPLOYED": "미취업자",
    "FREELANCER": "프리랜서",
    "DAILY_WORKER": "일용근로자",
    "STARTUP": "(예비)창업자",
    "SHORT_TERM": "단기근로자",
    "FARMER": "영농종사자",
    "OTHER": "기타",
    "BELOW_HIGH": "고졸 미만",
    "HIGH_ENROLLED": "고교 재학",
    "HIGH_GRAD_EXPECTED": "고졸 예정",
    "HIGH_GRAD": "고교 졸업",
    "UNIV_ENROLLED": "대학 재학",
    "UNIV_GRAD_EXPECTED": "대졸 예정",
    "UNIV_GRAD": "대학 졸업",
    "GRADUATE": "석·박사",
    "SME": "중소기업",
    "BASIC_LIVELIHOOD": "기초생활수급자",
    "SINGLE_PARENT": "한부모가정",
    "DISABLED": "장애인",
    "SOLDIER": "군인",
}
INCOME_YEARLY = "0043002"  # 연소득 (0043001 무관, 0043003 기타는 글을 AI가 읽음)
APPLY_ALWAYS = "0057002"  # 신청 기간 구분: 상시
APPLY_CLOSED = "0057003"  # 마감

# 원문 줄(수집기가 text에 넣는 이름)
LABELS = {
    "sprtTrgtMinAge": "지원 대상 최소 연령",
    "sprtTrgtMaxAge": "지원 대상 최대 연령",
    "earnMinAmt": "소득 최소 금액",
    "earnMaxAmt": "소득 최대 금액",
    "aplyYmd": "신청 기간",
    "bizPrdBgngYmd": "사업 시작일",
    "bizPrdEndYmd": "사업 종료일",
}


@dataclass
class RuleResult:
    conditions: list[dict[str, Any]] = field(default_factory=list)
    schedule: dict[str, Any] = field(default_factory=dict)  # 규칙으로 정한 일정 칸만
    income: dict[str, int] = field(default_factory=dict)  # 출처 칸의 연소득 금액(만 원, min·max). 기준(본인·부부)은 모름
    # 출처 칸에서 그대로 옮긴 안내(2026-10-25). 제출 서류 칸은 수집기가 AI에 보내는 글에 없어 규칙으로만 채울 수 있습니다
    documents: list[str] = field(default_factory=list)
    how_to_apply: str | None = None
    contact: str | None = None


def _codes(value: Any) -> list[str]:
    return [c.strip() for c in str(value or "").split(",") if c.strip()]


def _int(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number


def _ymd(value: Any) -> str | None:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) != 8:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return None


def _evidence(text: str, key: str, value: Any) -> str:
    """그 값이 들어 있는 원문 줄. 글에 없으면 출처 칸 이름과 값."""
    label = LABELS.get(key)
    if label:
        for line in (text or "").splitlines():
            if line.strip().startswith(f"{label}:"):
                return line.strip()
    return f"{key}: {value}"


_BULLET = re.compile(r"^[\s□■○●◎ㅇ\-*·•▶]*(?:\d+[.)]\s*)?")


def _clean_text(value: Any) -> str:
    """칸 값의 HTML 문자(&rarr; 등)를 풀고 「-」「.」같은 빈 값은 빈 문자열로."""
    text = html.unescape(str(value or "")).strip()
    return "" if text in ("-", ".", "0") else text


def _split_outside_parens(line: str) -> list[str]:
    """쉼표로 나누되 괄호 안 쉼표(「(받는분, 보내는분)」)는 나누지 않습니다."""
    parts, depth, current = [], 0, ""
    for ch in line:
        depth += ch in "([{"
        depth -= ch in ")]}"
        if ch == "," and depth <= 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return [*parts, current]


def documents_from(value: Any) -> list[str]:
    """제출 서류 칸(sbmsnDcmntCn) → 서류 이름 목록. 줄·번호·쉼표로 나누고, 「□ 공통 제출 서류」같은 머리말과 「※」 안내는 뺍니다."""
    found: list[str] = []
    for raw in _clean_text(value).splitlines():
        line = raw.strip()
        if not line or line.startswith(("□", "■", "※", "[")):
            continue
        for piece in re.split(r"\s+(?=\d+\.\s)", line):
            for part in _split_outside_parens(piece):
                name = _BULLET.sub("", part).split("※")[0].strip(" ,")
                if len(name) >= 2 and not name.startswith("※"):
                    found.append(name)
    return list(dict.fromkeys(found))


def _first_lines(value: Any, limit: int = 200) -> str | None:
    """여러 줄 안내를 한 줄로(머리말 기호 제거, 빈 줄·※ 안내 제외, limit자까지)."""
    lines = [_BULLET.sub("", line).strip() for line in _clean_text(value).splitlines()]
    joined = " / ".join(line for line in lines if line and not line.startswith("※"))
    return joined[:limit].rstrip() or None


def youth_rules(record: dict[str, Any], text: str) -> RuleResult:
    """온통청년 record의 코드 칸 → 조건·일정. 쉼표로 여러 코드면 같은 group(「또는」)."""
    out = RuleResult()
    group = 0

    def add(rows: list[tuple[str, dict[str, Any] | None, str]], evidence: str) -> None:
        nonlocal group
        if not rows:
            return
        group += 1
        for kind, value, raw in rows:
            out.conditions.append(
                {
                    "type": kind,
                    "value": value,
                    "group": group,
                    "known": value is not None,
                    "origin": "RULE",
                    "rawText": raw,
                    "evidence": evidence,
                    "confidence": 1,
                }
            )

    low, high = _int(record.get("sprtTrgtMinAge")), _int(record.get("sprtTrgtMaxAge"))
    if (low or 0) > 0 or (high or 0) > 0:
        value = {k: v for k, v in (("min", low), ("max", high)) if v}
        # 출처 칸에는 만 나이인지 출생연도 기준인지 없어 「만」을 붙이지 않아요(2026-10-26 원문 대조: 출생연도 기준 나이가 「만 19~39세」로 보였음)
        raw = f"{low}~{high}세" if low and high else (f"{low}세 이상" if low else f"{high}세 이하")
        add([("AGE", value, raw)], _evidence(text, "sprtTrgtMaxAge" if high else "sprtTrgtMinAge", high or low))

    if (marital := MARITAL.get(str(record.get("mrgSttsCd") or ""))) is not None:
        add([("MARITAL", {"in": [marital]}, "기혼" if marital == "MARRIED" else "미혼")], f"mrgSttsCd: {record.get('mrgSttsCd')}")

    if str(record.get("earnCndSeCd") or "") == INCOME_YEARLY:
        low, high = _int(record.get("earnMinAmt")), _int(record.get("earnMaxAmt"))
        if (low or 0) > 0 or (high or 0) > 0:
            # 본인 소득인지 부부 합산인지 칸에 없어(2026-10-25 시험: 신생아 특례대출은 부부합산인데 본인으로 나감) 값은 비우고
            # 금액만 남깁니다. AI가 글에서 같은 금액을 기준과 함께 읽으면 조립(build)에서 그 줄로 대신합니다
            out.income = {k: v for k, v in (("min", low), ("max", high)) if v}
            raw = f"연소득 {low}~{high}만 원" if low and high else (f"연소득 {low}만 원 이상" if low else f"연소득 {high}만 원 이하")
            add([("INCOME_AMOUNT", None, raw)], _evidence(text, "earnMaxAmt" if high else "earnMinAmt", high or low))

    jobs = _codes(record.get("jobCd"))
    if jobs and JOB_ANY not in jobs:
        rows: list[tuple[str, dict[str, Any] | None, str]] = []
        employment = [JOB[c][1] for c in jobs if c in JOB and JOB[c][0] == "EMPLOYMENT"]
        if employment:
            rows.append(("EMPLOYMENT", {"in": list(dict.fromkeys(employment))}, "취업 상태: " + ", ".join(KO.get(v, v) for v in employment)))
        if any(JOB.get(c, ("",))[0] == "OCCUPATION" for c in jobs):
            rows.append(("OCCUPATION", {"in": ["FARMER"]}, "영농종사자"))
        add(rows, f"jobCd: {record.get('jobCd')}")

    schools = _codes(record.get("schoolCd"))
    if schools and SCHOOL_ANY not in schools:
        values = list(dict.fromkeys(SCHOOL[c] for c in schools if c in SCHOOL))
        if values:
            add([("EDUCATION", {"in": values}, "학력: " + ", ".join(KO.get(v, v) for v in values))], f"schoolCd: {record.get('schoolCd')}")

    specials = _codes(record.get("sbizCd"))
    if specials and SPECIAL_ANY not in specials:
        rows = []
        merged: dict[str, list[str]] = {}
        for code in specials:
            if code not in SPECIAL:
                continue
            kind, value = SPECIAL[code]
            if kind == "OTHER":
                rows.append(("OTHER", None, f"특화 분야: {value}"))
            else:
                merged.setdefault(kind, []).append(value)
        for kind, values in merged.items():
            value = {"kind": values} if kind == "WORKPLACE" else {"in": list(dict.fromkeys(values))}
            rows.append((kind, value, f"특화 분야: {', '.join(KO.get(v, v) for v in values)}"))
        add(rows, f"sbizCd: {record.get('sbizCd')}")

    # 안내: 제출 서류·신청 방법·문의처(주관 기관). AI 답이 비면 이 값을 씁니다(서류는 이 값이 우선)
    out.documents = documents_from(record.get("sbmsnDcmntCn"))
    out.how_to_apply = _first_lines(record.get("plcyAplyMthdCn"))
    # 문의처는 주관 기관 이름만(담당자 칸은 공무원 실명이 많아 넣지 않음)
    out.contact = _clean_text(record.get("sprvsnInstCdNm")) or None

    # 일정: 신청 기간 「YYYYMMDD ~ YYYYMMDD」, 구분 상시, 사업 기간
    period = str(record.get("aplyYmd") or "")
    days = re.findall(r"\d{8}", period)
    if len(days) == 2:
        out.schedule.update(applyStart=_ymd(days[0]), applyEnd=_ymd(days[1]), rawText=period.strip())
    if str(record.get("aplyPrdSeCd") or "") == APPLY_ALWAYS:
        out.schedule.update(applyAlways=True, rawText=out.schedule.get("rawText") or "상시")
    elif str(record.get("aplyPrdSeCd") or "") in ("0057001", APPLY_CLOSED):
        out.schedule.setdefault("applyAlways", False)
    if (start := _ymd(record.get("bizPrdBgngYmd"))) is not None:
        out.schedule["businessStart"] = start
    if (end := _ymd(record.get("bizPrdEndYmd"))) is not None:
        out.schedule["businessEnd"] = end
    return out


def rules_for(source_code: str, record: dict[str, Any] | None, text: str) -> RuleResult:
    if source_code == "youth" and isinstance(record, dict):
        return youth_rules(record, text)
    return RuleResult()
