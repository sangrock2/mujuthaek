"""V5 예외 누락 의심: 원문에 있는 가산·완화 기준을 AI가 빠뜨렸는지 좁게 찾습니다.

검증기의 다른 검사는 "AI가 적은 값이 원문에 있는가"만 봅니다. 이 검사는 반대 방향인 "원문에 있는 기준을 빠뜨렸는가"를 봅니다.
사람 검수를 늘리지 않도록 키워드가 아니라 기준값 자체를 기준으로 삼습니다.

- 대상: 예외가 비어 있는 STRUCTURED 자격 조건의 금액(KRW)·비율(PERCENT) 기준값
- 원문에서 그 기준값이 나오는 곳마다 바로 뒤(표의 다음 행 정도)에 같은 단위의 다른 기준값이 있는지 봅니다.
- 기준값과 비슷한 크기(0.7~1.5배)만 셉니다. 1억원·34,500만원처럼 다른 기준(주택가격·총자산)의 값은 걸리지 않습니다.
- 다른 자격 조건이나 예외가 이미 쓰는 값(예: 3순위 총자산 25,100만원)은 빠진 것이 아니므로 셈하지 않습니다.
예: 「자동차가액 0명(기준) 4,542만원 / 1명 4,996만원 / 2명 5,451만원」 → 4,542만원 조건에 예외가 없으면 의심.
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_extraction.assemble.values import to_krw
from mujuthaek_extraction.verify.model import Finding, SourceBundle

# "1억 6천만원"처럼 억이 앞에 붙은 표기도 한 금액으로 읽습니다("6천만원"으로 잘라 읽지 않게).
# 「3억3,700만 원」처럼 단위와 '원' 사이를 띄운 표기, 「2억4천5백만원」처럼 천·백이 섞인 표기도 읽습니다
# (실측: SH 총자산 기준이 V9 오탐으로 검수에 가던 것, 2026-10-16).
AMOUNT = re.compile(r"(?:\d[\d,]*억\s*)?(?:\d+[천백십])*\d[\d,]*(?:\.\d+)?\s*(?:(?:억|천만|백만|십만|만|천)\s*)?원")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
AFTER_CHARS = 120  # 기준값 뒤로 볼 글자 수 (표 2~3행)
RATIO = (0.7, 1.5)
SNIPPET_CHARS = 100
# 「100% 우선공급 (70%)」처럼 기준값 뒤의 비율이 공급 물량 몫이면 가산 기준이 아닙니다(실측: 전북개발공사 분양 공고)
ALLOCATION = re.compile(r"우선\s*공급|일반\s*공급|공급\s*(?:비율|물량)|물량|(?:주택|세대|호)\s*수의")
RANGE_TABLE = "초과"  # 구간표(○○% 초과 ○○% 이하) 표시. 가산·완화 표는 "1명 4,996만원"처럼 값만 나열합니다


def _values(text: str, unit: str) -> list[tuple[int, float, str]]:
    """(위치, 값, 원문 표기). 금액은 원 단위, 비율은 % 숫자."""
    out = []
    if unit == "KRW":
        for m in AMOUNT.finditer(text):
            krw = to_krw(re.sub(r"\s", "", m[0]), None).amount_krw
            if krw is not None:
                out.append((m.start(), float(krw), m[0]))
    elif unit == "PERCENT":
        out = [(m.start(), float(m[1]), m[0]) for m in PERCENT.finditer(text)]
    return out


def _atoms(expression: dict[str, Any] | None):
    if not expression:
        return
    if expression["kind"] == "ATOMIC":
        yield expression
    for child in expression.get("children") or []:
        yield from _atoms(child)


def _suspect(atoms: list[dict[str, Any]], known: set[float], sources: SourceBundle) -> str | None:
    """기준값 바로 뒤에 비슷한 크기의 다른 기준값이 있으면 그 설명을, 없으면 None을 돌려줍니다. known: 이미 조건식에 쓰인 값.

    기준값이 여러 곳에 나오면 다른 값이 가장 많이 붙어 있는 곳(가산 표일 가능성이 높은 곳)을 보여 줍니다.
    """
    best: tuple[int, str, int, list[tuple[int, str]]] | None = None
    for atom in atoms:
        base = float(atom["value"])
        for text in sources.texts.values():
            found = _values(text, atom["unit"])
            for pos, value, _ in found:
                if value != base:
                    continue
                if RANGE_TABLE in text[pos : pos + AFTER_CHARS]:
                    # "70%이하까지 | 73.5%초과 77%이하 …"는 재계약 임대료 할증 구간표라 가산 기준이 아닙니다
                    # (실측: 대구도시공사 매입임대, LH 국민임대 — 할증표 때문에 소득 기준마다 예외 누락 의심이 붙음)
                    continue
                nearby = [
                    (p, raw)
                    for p, v, raw in found
                    if pos < p <= pos + AFTER_CHARS and v not in known and RATIO[0] <= v / base <= RATIO[1] and not ALLOCATION.search(text[pos:p])
                ]
                if nearby and (best is None or len(nearby) > best[0]):
                    best = (len(nearby), text, pos, nearby)
    if best is None:
        return None
    _, text, pos, nearby = best
    others = ", ".join(dict.fromkeys(raw for _, raw in nearby))
    last, raw = nearby[-1]
    snippet = " ".join(text[pos : last + len(raw)].split())[:SNIPPET_CHARS]
    return f"기준값 바로 뒤에 다른 기준값({others})이 있는데 예외로 넣지 않았습니다. 가산·완화 기준이 빠졌는지 확인하세요 「{snippet}」"


TIER_ATTRIBUTES = {"INCOME_BENCHMARK_PERCENT", "MONTHLY_INCOME_KRW", "TOTAL_ASSETS_KRW", "CAR_ASSETS_KRW"}
TIER_SPLITTERS = {"HOUSEHOLD_MEMBER_COUNT", "CHILD_COUNT", "TARGET_GROUP_CODE", "MARITAL_STATUS"}


def _scope_key(item: dict[str, Any]) -> tuple[Any, ...]:
    scope = item.get("scope") or {}
    return (scope.get("level"), tuple(sorted(scope.get("supplyGroupIds") or [])), tuple(sorted(scope.get("targetGroups") or [])))


def check_unconditioned_tiers(candidate: dict[str, Any]) -> list[Finding]:
    """같은 대상(scope)의 같은 기준(소득·자산)을 값만 다르게 조건 여러 개로 나란히 둔 경우.

    자격 조건은 모두 함께(AND) 적용되므로 「1인 120% / 2인 110% / 3인 이상 100%」를 가구원 수 조건 없이 따로 적으면
    모든 가구에 가장 낮은 값이 적용됩니다(실측 2026-10-17: 인천 행복주택 4계층 소득이 이렇게 자동 게시됨).
    가구원 수·자녀 수 조건이 조건식에 들어 있으면 의도한 구간이므로 걸지 않습니다.
    """
    seen: dict[tuple[Any, ...], list[tuple[int, float]]] = {}
    for index, item in enumerate(candidate["eligibility"]):
        rule = item["rule"]
        if rule["status"] != "STRUCTURED":
            continue
        atoms = list(_atoms(rule["expression"]))
        if any(a.get("attribute") in TIER_SPLITTERS for a in atoms):
            continue
        for atom in atoms:
            if atom.get("attribute") in TIER_ATTRIBUTES and isinstance(atom.get("value"), int | float):
                seen.setdefault((*_scope_key(item), atom["attribute"], atom.get("operator")), []).append((index, float(atom["value"])))
    findings = []
    for (*_, attribute, _operator), entries in seen.items():
        if len({value for _, value in entries}) < 2:
            continue
        values = ", ".join(dict.fromkeys(f"{value:,.0f}" if value.is_integer() else f"{value:g}" for _, value in entries))
        for index, _ in entries:
            findings.append(
                Finding(
                    "V5",
                    "TIER_CONDITION_MISSING",
                    f"/eligibility/{index}",
                    f"같은 대상의 {attribute} 기준이 값만 다르게({values}) 여러 조건으로 나뉘어 있고 가구원 수·자녀 수 조건이 없습니다. "
                    "모든 조건이 함께 적용되어 가장 낮은 값이 모든 가구에 적용됩니다",
                )
            )
    return findings


# 재계약·계약 갱신 때의 기준(실측 2026-10-17 경북 매입임대: 「재계약 시 소득 105% 이하」가 신청 자격으로 자동 게시됨)
RENEWAL = re.compile(r"재계약|계약\s*갱신|갱신\s*계약")


def check_renewal_criteria(candidate: dict[str, Any]) -> list[Finding]:
    """재계약·계약 갱신 때 적용하는 기준을 신청 자격 조건으로 넣은 경우. 자격 조건은 모두 함께 적용되므로
    재계약 기준이 신청 기준보다 엄격하면 자격이 되는 신청자를 탈락으로 판정합니다. 적용 대상·기준 시점에 재계약이 적혔거나,
    원문 인용이 재계약 문장이고 신청 이야기가 없을 때만 겁니다(신청 자격 문장 안의 「재계약」 언급은 걸지 않음)."""
    findings = []
    for index, item in enumerate(candidate["eligibility"]):
        when = f"{item.get('appliesTo') or ''} {item.get('referenceTime') or ''}"
        text = item.get("originalText") or ""
        if RENEWAL.search(when) or (RENEWAL.search(text) and "신청" not in text):
            findings.append(
                Finding(
                    "V5",
                    "RENEWAL_CRITERION_IN_ELIGIBILITY",
                    f"/eligibility/{index}",
                    "재계약·계약 갱신 때의 기준이 신청 자격 조건으로 들어 있습니다. 신청자 판정에 함께 적용되면 결과가 틀어지므로 확인이 필요합니다",
                )
            )
    return findings


# 자격의 소득·자산 기준은 상한이라, 하한(「130% 초과」)은 대개 단계별 선정의 소득 구간입니다. 2026-11-07 유료 확인(jbdc-16011):
# 「(2단계) 추첨공급 : 부부 모두 소득이 있는 신청자 중 … 130% 초과 200% 이하인 분 * 1단계 낙첨자를 포함」을 다자녀 추첨공급의 자격 하한으로 옮겨
# 게시 — 1단계 낙첨자(외벌이 120% 이하)를 불가로 판정함. 같은 모양 하한 6개(신혼부부·생애최초 2·3단계)는 다른 이슈로 보류됐을 뿐이었음.
# 하한이 맞는 공급(소득 구간별 공급)도 있어 고치지 않고 그 조건만 사람 확인으로 보냅니다. 23건 저장 결과(V1·V2)에는 하한이 없었음
LOWER_BOUND_ATTRIBUTES = {"INCOME_BENCHMARK_PERCENT", "MONTHLY_INCOME_KRW", "TOTAL_ASSETS_KRW", "CAR_ASSETS_KRW"}
LOWER_WORDS = {"GT": "초과", "GTE": "이상", "LT": "이상", "LTE": "초과"}  # NOT 안의 미만·이하는 이상·초과


def _lower_bounds(expression: dict[str, Any] | None, negated: bool = False):
    """조건식의 소득·자산 하한 (원자, 하한 값, 「초과」·「이상」): 초과·이상, 범위(BETWEEN)의 아래 끝, NOT 안의 미만·이하."""
    if not expression:
        return
    if expression.get("kind") == "ATOMIC":
        operator, value = expression.get("operator"), expression.get("value")
        if expression.get("attribute") not in LOWER_BOUND_ATTRIBUTES:
            return
        if operator in (("LT", "LTE") if negated else ("GT", "GTE")) and isinstance(value, int | float):
            yield expression, value, LOWER_WORDS[operator]
        elif operator == "BETWEEN" and not negated and isinstance(value, list) and value and isinstance(value[0], int | float) and value[0] > 0:
            yield expression, value[0], "이상"
        return
    for child in expression.get("children") or []:
        yield from _lower_bounds(child, negated != (expression.get("kind") == "NOT"))


def check_lower_bounds(candidate: dict[str, Any]) -> list[Finding]:
    """자격 조건(기본 조건식·예외의 바뀐 기준)에 소득·자산 하한이 있는 경우. 예외의 발동 조건(when)은 기준이 아니라 보지 않습니다."""
    findings = []
    for index, item in enumerate(candidate["eligibility"]):
        expressions = [(item.get("rule") or {}).get("expression"), *(e.get("effectExpression") for e in item.get("exceptions") or [])]
        found = [bound for expression in expressions for bound in _lower_bounds(expression)]
        if not found:
            continue
        shown = ", ".join(f"{value:g}%" if atom.get("unit") == "PERCENT" else f"{value:,.0f}원" for atom, value, _ in found[:2])
        words = found[0][2]
        findings.append(
            Finding(
                "V5",
                "LOWER_BOUND_IN_ELIGIBILITY",
                f"/eligibility/{index}",
                f"자격 기준에 하한({shown} {words})이 있습니다. 단계별 선정의 소득 구간(「100% 초과 130% 이하」, 앞 단계 낙첨자 포함)이면 "
                "그보다 낮은 신청자도 대상이라 자격 하한이 아닙니다. 원문 확인이 필요합니다",
            )
        )
    return findings


def check_missing_exceptions(candidate: dict[str, Any], sources: SourceBundle) -> list[Finding]:
    """V5 검사를 모두 돌립니다: 구간 조건 누락, 재계약 기준, 자격 하한, 그리고 구조화된 금액·비율 조건마다 빠진 가산·완화 기준 의심."""
    findings = check_unconditioned_tiers(candidate) + check_renewal_criteria(candidate) + check_lower_bounds(candidate)
    # 다른 자격 조건(예: 3순위 총자산 25,100만원)이 이미 쓰는 기준값은 빠진 예외가 아닙니다
    known = {float(a["value"]) for item in candidate["eligibility"] for a in _atoms(item["rule"]["expression"]) if isinstance(a["value"], int | float)}
    for item in candidate["eligibility"]:
        for exception in item["exceptions"]:
            for key in ("when", "effectExpression"):
                node = exception.get(key) or {}
                expression = node.get("expression") if key == "when" else node
                known |= {float(a["value"]) for a in _atoms(expression) if isinstance(a["value"], int | float)}
    for index, item in enumerate(candidate["eligibility"]):
        rule = item["rule"]
        # 예외가 이미 있는 조건도 봅니다. 남은 값(known에 없는 값)이 있으면 가산 구간 일부가 빠진 것입니다
        # (실측 2026-10-16 시험: 출산가구 자산 가산 3억7,900만·4억1,300만원 중 일부, 1인 130% 소득 구간이 빠진 채 완료)
        if rule["status"] != "STRUCTURED":
            continue
        atoms = [a for a in _atoms(rule["expression"]) if a["unit"] in ("KRW", "PERCENT") and isinstance(a["value"], int | float)]
        description = _suspect(atoms, known, sources)
        if description:
            findings.append(Finding("V5", "EXCEPTION_SUSPECTED", f"/eligibility/{index}", description))
    return findings
