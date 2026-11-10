"""주거 판정 틀(housing-judgment.v1) 가공. 코드만 씁니다(공통 뼈대는 frame.py).

- 자격 조건식(원자 조건) → 나이·무주택·소득·총자산·자동차·혼인·자녀·청약통장·거주지.
- 소득 가산: 예외 「가구원 수 n인이면 m%」(구조), 원문 「100%(1인 120%, 2인 110%)」, 설명 「1인가구는 20%p 가산」(원문 인용에
  같은 값이 있을 때만 확정). 공고 어딘가에 가산 낱말이 있는데 못 읽으면 그 소득 조건은 inReview(가산을 빼면 1·2인 가구가 불충족).
- 문장만 있는 「서울특별시에 주민등록된 …」은 거주지 코드(지역표), 그 밖의 문장 규칙은 frame.py.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_extraction.judgment.common import STATUS_WORDS, Context, ask_whole, base_fields, status_codes, status_rest, statuses_of
from mujuthaek_extraction.judgment.frame import Criterion, Made, Spec, as_int, as_number, bounds, build_frame
from mujuthaek_extraction.judgment.readback import mismatch as readback_mismatch
from mujuthaek_extraction.judgment.sanity import INVERTED

STANDARDS = (  # 앞에서부터 먼저 맞는 것(「도시근로자 가구원수별 가구당 월평균소득」은 가구원수별)
    (re.compile(r"중위\s*소득"), "MEDIAN_INCOME"),
    (re.compile(r"도시\s*근로자.*가구원\s*수\s*별"), "URBAN_WORKER_INCOME"),
    (re.compile(r"도시\s*근로자.*가구당"), "URBAN_WORKER_AVERAGE_INCOME"),
)
RELAXED_LIMIT = re.compile(r"(?:출생|신생아)[^.]{0,40}?\d[\d,.]*\s*(?:억|만)\s*원")
STRICT_INCOME = "원문은 소득 기준 「미만」인데 틀의 percent는 「이하」만 나타냅니다(기준값과 같은 소득은 원문상 불충족)"
RELATIVE_YEAR = {"전년도": -1, "당해연도": 0, "당해년도": 0, "금년도": 0}


def _atom(ctx: Context, item: dict[str, Any], node: dict[str, Any], quote: str | None, when: date) -> Criterion | None:
    attribute, op, value, subject = node["attribute"], node["operator"], node["value"], node.get("subject")
    span = bounds(node)
    if attribute == "AGE_YEARS" and span and subject == "APPLICANT":
        if OTHER_PERSON_AGE.search(f"{item.get('originalText') or ''} {quote or ''}"):
            # 「65세 이상의 직계존속을 부양」: 신청자가 아니라 가족의 나이(실측: 신청자 65세 이상으로 들어감, 2026-10-21)
            return ask_whole(ctx, item, quote, "원문의 나이가 신청자가 아닌 가족의 나이일 수 있습니다")
        if span[0] is not None and span[1] is not None and span[0] > span[1]:
            return ask_whole(ctx, item, quote, INVERTED)  # 「BETWEEN [39, 19]」: 거꾸로 된 범위는 틀 읽기가 틀 전체를 거절함
        return {**base_fields(ctx.new_id(item["id"]), "AGE", quote), "minAge": as_int(span[0]), "maxAge": as_int(span[1])}
    if attribute == "HOMELESS" and op == "EQ" and value is True and subject in ("APPLICANT", "HOUSEHOLD"):
        return {**base_fields(ctx.new_id(item["id"]), "HOMELESS", quote), "scope": subject, "minYears": None}
    if attribute == "INCOME_BENCHMARK_PERCENT" and span and span[0] is None and span[1] is not None:
        if op != "LT":
            return _income(ctx, item, node, quote, when, span[1])
        # 소득 비율은 소수가 될 수 있어 「100% 미만」을 「99% 이하」로 바꾸면 99.5%가 떨어집니다. 원문 값을 두고 확인 필요로 둡니다
        income = _income(ctx, item, node, quote, when, value)
        if income is not None:
            ctx.flag(income, [STRICT_INCOME])
        return income
    if attribute in ("TOTAL_ASSETS_KRW", "CAR_ASSETS_KRW") and span and span[0] is None and span[1] is not None:
        if attribute == "TOTAL_ASSETS_KRW" and subject not in ("APPLICANT", "HOUSEHOLD"):
            return None
        criterion = base_fields(ctx.new_id(item["id"]), "ASSET" if attribute == "TOTAL_ASSETS_KRW" else "CAR", quote)
        if attribute == "TOTAL_ASSETS_KRW":
            criterion["basis"] = subject
        return criterion | {"maxWon": int(span[1]), "overrides": []}
    if attribute == "MARITAL_STATUS" and op == "EQ" and value in ("UNMARRIED", "MARRIED"):
        return {
            **base_fields(ctx.new_id(item["id"]), "MARRIAGE", quote),
            "require": "NOT_MARRIED" if value == "UNMARRIED" else "MARRIED",
            "maxYears": None,
            "allowEngaged": value == "MARRIED" and _engaged(item),
        }
    if attribute == "MARRIAGE_MONTHS" and span and span[0] is None and span[1] is not None and span[1] % 12 == 0:
        return {
            **base_fields(ctx.new_id(item["id"]), "MARRIAGE", quote),
            "require": "MARRIED",
            "maxYears": int(span[1]) // 12,
            "allowEngaged": _engaged(item),
        }
    if attribute == "CHILD_COUNT" and span and span[1] is None:
        text = f"{item.get('originalText') or ''} {quote or ''}"
        count, youngest = as_int(span[0]), _youngest_age(text)
        if CHILD_AGE.search(text) and ((count or 0) >= 2 or youngest is None):
            # 「6세 이하 자녀 2명 이상」(그 나이의 자녀 수)과 「자녀 2명 이상, 막내 6세 이하」는 다른 조건인데 틀의 칸(minCount·youngestMaxAge)으로는
            # 같은 값이 됩니다. 「미성년 자녀 2명 이상」은 나이 없이 「자녀 2명 이상」이 되어 성인 자녀도 셌음(2026-10-21 리뷰·실측 10곳)
            return ask_whole(ctx, item, quote, "나이 제한이 붙은 자녀 수는 틀의 칸(자녀 수·막내 나이)으로 정확히 담을 수 없습니다")
        return {
            **base_fields(ctx.new_id(item["id"]), "CHILDREN", quote),
            "minCount": count,
            "youngestMaxAge": youngest,
            "includeUnborn": "태아" in text,
        }
    if attribute == "YOUNGEST_CHILD_AGE_YEARS" and span and span[0] is None and span[1] is not None:
        # 「6세 이하 자녀를 둔」(2026-11-09 새 속성): 그 나이 이하의 자녀가 있어야 함 = 자녀 1명 이상·막내 나이 상한. 태아 포함은 원문 글로
        text = f"{item.get('originalText') or ''} {quote or ''}"
        return {
            **base_fields(ctx.new_id(item["id"]), "CHILDREN", quote),
            "minCount": 1,
            "youngestMaxAge": as_int(span[1]),
            "includeUnborn": "태아" in text,
        }
    if attribute in ("SAVINGS_ACCOUNT_EXISTS", "SAVINGS_MONTHS", "SAVINGS_PAYMENT_COUNT", "SAVINGS_BALANCE_KRW"):
        if attribute == "SAVINGS_ACCOUNT_EXISTS" and not (op == "EQ" and value is True):
            return None
        if attribute != "SAVINGS_ACCOUNT_EXISTS" and not (span and span[1] is None):
            return None
        low = as_int(span[0]) if span else None
        return {
            **base_fields(ctx.new_id(item["id"]), "SAVINGS", quote),
            "minMonths": low if attribute == "SAVINGS_MONTHS" else None,
            "minPayments": low if attribute == "SAVINGS_PAYMENT_COUNT" else None,
            "minBalanceWon": low if attribute == "SAVINGS_BALANCE_KRW" else None,
        }
    if attribute == "RESIDENCE_REGION_CODE" and op in ("EQ", "IN"):
        codes = value if isinstance(value, list) else [value]
        residence = {**base_fields(ctx.new_id(item["id"]), "RESIDENCE", quote), "regionCodes": list(dict.fromkeys(codes)), "minMonths": None}
        missing = _unreflected(item, f"{item.get('originalText') or ''}")
        if missing:
            # 「부산광역시에 거주하는 무주택세대구성원인 성년자」: 이 항목의 조건식은 거주지뿐인데 문장에 다른 조건이 있음(2026-10-21 리뷰 4)
            ctx.flag(residence, [f"원문 문장의 다른 조건({', '.join(missing)})이 이 항목의 조건식에 없습니다"])
        return residence
    if attribute == "NATIONALITY_CODE" and op == "EQ" and value == "KR":
        nationality = {**base_fields(ctx.new_id(item["id"]), "ASK", quote), "question": "대한민국 국적인가요?", "metWhen": "YES"}
        if re.search(r"[가-힣]{2,}", NATIONALITY_FILLER.sub("", f"{item.get('originalText') or ''}")):
            # 「내국인 직원에 한함(대표이사는 입주 불가)」: 국적만 묻고 직원·대표이사 조건을 버렸음(2026-10-21 실측 gh-811)
            ctx.flag(nationality, ["원문 문장에 국적 말고 다른 조건이 있는데 이 항목의 조건식은 국적뿐입니다"])
        return nationality
    return None


def _merge(criteria: list[Criterion]) -> list[Criterion]:
    """「혼인 중」과 「혼인 n년 이내」가 한 항목에 같이 오면 혼인 조건 하나로 합칩니다."""
    marriages = [c for c in criteria if c["kind"] == "MARRIAGE" and c["require"] == "MARRIED"]
    if len(marriages) != 2:
        return criteria
    keep, other = (marriages[0], marriages[1]) if marriages[1]["maxYears"] is None else (marriages[1], marriages[0])
    keep["allowEngaged"] = keep["allowEngaged"] or other["allowEngaged"]
    return [c for c in criteria if c is not other]


def _income(ctx: Context, item: dict[str, Any], node: dict[str, Any], quote: str | None, when: date, percent: float) -> Criterion | None:
    benchmark = node.get("benchmark") or {}
    name = str(benchmark.get("standardName") or "")
    standard = next((value for pattern, value in STANDARDS if pattern.search(name)), None)
    if standard is None:
        return None
    year = benchmark.get("referenceYear")
    if not isinstance(year, int):
        offset = RELATIVE_YEAR.get(str(benchmark.get("referenceVersion") or "").strip())
        year = when.year + offset if offset is not None else None
    if year is None:
        return None
    scope = str(benchmark.get("householdScope") or "")
    if "부모" in scope:
        basis = "APPLICANT_AND_PARENTS"
    elif re.search(r"세대원\s*(?:인\s*)?신청자.*본인|세대주.*세대.*세대원.*본인", scope):
        basis = "HOUSEHOLD_IF_HEAD"
    elif node.get("subject") in ("APPLICANT", "HOUSEHOLD"):
        basis = node["subject"]
    else:
        return None
    criterion = {
        **base_fields(ctx.new_id(item["id"]), "INCOME", quote),
        "basis": basis,
        "standard": standard,
        "year": year,
        "percent": as_number(percent),
        "bonuses": [],
        "bonusCombine": "SUM",
        "printedTable": [],
    }
    criterion["_bonusKeys"] = sorted(_bonus_keys(f"{item.get('originalText') or ''} {item.get('description') or ''}"))
    bonuses, unread = _bonuses(f"{item.get('originalText') or ''}", percent)
    if not bonuses and not unread:
        # 원문 인용에는 기준 비율만 있고 가산은 설명에만 있는 경우(실측 LH 강원: 「1인가구는 20%p, 2인가구는 10%p 가산」).
        # 설명은 AI 문장이라 공고 근거 인용에 같은 가구원 수·%가 있을 때만 확정하고, 없으면 넣되 inReview입니다
        bonuses, unread = _added_points(str(item.get("description") or ""))
        if bonuses and not all(ctx.quoted(rf"{b['when']['min']}\s*인[^%]{{0,20}}?{b['addPercent']:g}\s*%") for b in bonuses):
            ctx.flag(criterion, ["소득 가산을 공고 설명에서 읽었고 원문 인용에서 같은 값을 찾지 못했습니다"])
    criterion["bonuses"] = bonuses
    if unread or (not bonuses and ctx.mentions_bonus(item)):
        ctx.flag(criterion, [UNREAD_BONUS])
    return criterion


UNREAD_BONUS = "소득 가산 문구를 코드로 다 읽지 못했습니다(가산을 빼면 1·2인 가구 판정이 달라질 수 있음)"
BONUS_UNCHECKED = "가구원 수별 소득 기준을 예외 원문에서 같은 가구원 수·값으로 확인하지 못했습니다"


def _bonus_keys(text: str) -> set[tuple[str, int]]:
    """원문이 말하는 가산 항목(가구원 수별·맞벌이·출생 자녀). 예외로 받은 가산이 이것을 모두 덮어야 「가산을 못 읽음」을 풉니다(2026-10-21 리뷰:
    1인 가산 하나만 받아도 「가산」이 들어간 사유를 모두 지워 2인 가산 문제도 사라졌음)."""
    keys = {("HH", int(m)) for m in re.findall(r"(?<!\d)([1-9])\s*인\s*(?:가구|인\s*경우)?\s*(?:는|은|의\s*경우|경우)?\s*[:：]?\s*\d+(?:\.\d+)?\s*%", text)}
    keys |= {("HH", int(m)) for m in re.findall(r"가구원\s*수?\s*(?:가|이)?\s*([1-9])\s*(?:인|명)", text)}
    if "맞벌이" in text:
        keys.add(("DUAL", 0))
    if re.search(r"출생|출산|신생아", text):
        keys.add(("BIRTH", 0))
    return keys


ADDED_POINTS = re.compile(r"(?P<size>[1-9])\s*인\s*가구(?:는|은)?\s*(?P<value>\d+(?:\.\d+)?)\s*%\s*p")


def _added_points(text: str) -> tuple[list[dict[str, Any]], bool]:
    """「1인가구는 20%p, 2인가구는 10%p 가산」 → 가구원 수별 가산 %p. (가산 목록, 가산 낱말이 있는데 못 읽은 것이 있는지)."""
    found: list[dict[str, Any]] = []
    for match in ADDED_POINTS.finditer(text):
        size = int(match.group("size"))
        when = {"factor": "HOUSEHOLD_SIZE", "min": size, "max": size, "since": None, "countRule": None}
        if any(b["when"] == when for b in found):
            return [], True
        found.append({"when": when, "addPercent": as_number(float(match.group("value")))})
    leftover = ADDED_POINTS.sub("", text)
    return found, bool(re.search(r"맞벌이|신생아|출생\s*자녀|자녀\s*수", leftover)) or (not found and "가산" in text)


# 「100%(1인 120%, 2인 110%)」「120%(맞벌이)」: 기준 비율 뒤 괄호 안의 가구원 수·맞벌이별 비율(절대값)
BONUS_PART = re.compile(
    r"(?:(?P<size>[1-9])\s*인\s*(?:가구)?|(?P<dual>맞벌이(?:\s*부부)?)(?:\s*(?:의\s*)?경우)?)\s*(?:는|은)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?:%|퍼센트)"
)


def _bonuses(text: str, percent: float) -> tuple[list[dict[str, Any]], bool]:
    """원문의 가구원 수·맞벌이별 비율을 가산 %p로. (가산 목록, 가산 낱말이 있는데 못 읽은 것이 있는지)."""
    found: list[dict[str, Any]] = []
    for match in BONUS_PART.finditer(text):
        add = float(match.group("value")) - percent
        if add <= 0:
            return [], True
        if match.group("size"):
            size = int(match.group("size"))
            when = {"factor": "HOUSEHOLD_SIZE", "min": size, "max": size, "since": None, "countRule": None}
        else:
            when = {"factor": "DUAL_INCOME", "min": None, "max": None, "since": None, "countRule": None}
        if any(b["when"] == when for b in found):
            return [], True
        found.append({"when": when, "addPercent": as_number(add)})
    leftover = BONUS_PART.sub("", text)
    return found, bool(re.search(r"가산|신생아|출생\s*자녀|자녀\s*수", leftover))


def _absorb(base: list[Criterion], exception: dict[str, Any]) -> bool:
    """「가구원 수가 n인이면 소득 기준 m%」 교체를 소득 조건의 가구원 수 가산으로 옮기면 True(그 조건에 더함)."""
    incomes = [c for c in base if c["kind"] == "INCOME"]
    if len(incomes) != 1:
        return False
    income = incomes[0]
    effect, condition = exception.get("effectExpression") or {}, (exception.get("when") or {}).get("expression") or {}
    if exception["effect"] != "REPLACE" or effect.get("kind") != "ATOMIC" or condition.get("kind") != "ATOMIC":
        return False
    if effect.get("attribute") != "INCOME_BENCHMARK_PERCENT" or effect.get("operator") not in ("LTE", "LT"):
        return False
    if condition.get("attribute") != "HOUSEHOLD_MEMBER_COUNT" or income["percent"] is None:
        return False
    span = bounds(condition)
    value = effect["value"]
    if not span or span[0] is None or not isinstance(value, int | float) or value <= income["percent"]:
        return False
    if span[1] is not None and span[0] > span[1]:
        return False  # 거꾸로 된 가구원 수 범위는 가산으로 옮기지 않음(예외를 옮기지 못한 것으로 남아 확인 필요)
    sizes = {"factor": "HOUSEHOLD_SIZE", "min": as_int(span[0]), "max": as_int(span[1]), "since": None, "countRule": None}
    add = as_number(value - income["percent"])
    # 예외 원문에 그 가구원 수와 값(기준 비율 또는 가산 %p)이 함께 있어야 확정합니다(리뷰 2026-10-22: 2인 +20%p를 1인 값으로 잘못 뽑아도 통과)
    seen = re.search(rf"{sizes['min']}\s*인[^%\d]{{0,25}}?(?:{value:g}|{add:g})\s*%", str(exception.get("originalText") or ""))
    if any(b["when"] == sizes for b in income["bonuses"]):
        return any(b["when"] == sizes and b["addPercent"] == add for b in income["bonuses"])
    income["bonuses"].append({"when": sizes, "addPercent": add})
    if not seen:
        _add_reason(income, BONUS_UNCHECKED)
        return True
    # 「가산을 못 읽음」은 원문이 말한 가산 항목을 모두 받았을 때만 풉니다. 다른 사유는 그대로 둡니다
    expected = {tuple(k) for k in income.get("_bonusKeys") or []}
    covered = {("HH", b["when"]["min"]) for b in income["bonuses"] if b["when"]["factor"] == "HOUSEHOLD_SIZE" and b["when"]["min"] == b["when"]["max"]}
    reasons = [r for r in (income.get("reviewReason") or "").split("; ") if r]
    if UNREAD_BONUS in reasons and expected and expected <= covered:
        reasons.remove(UNREAD_BONUS)
        income["reviewReason"], income["inReview"] = "; ".join(reasons) or None, bool(reasons)
    if effect["operator"] == "LT":
        _add_reason(income, STRICT_INCOME)
    return True


def _add_reason(criterion: Criterion, reason: str) -> None:
    """Context 없이 검수 사유를 더합니다(_absorb는 Spec 호출 모양상 Context를 받지 않음)."""
    criterion["inReview"] = True
    criterion["reviewReason"] = "; ".join(dict.fromkeys([*filter(None, (criterion.get("reviewReason") or "").split("; ")), reason]))


def _extra(item: dict[str, Any], made: list[Criterion]) -> list[str]:
    text = f"{item.get('originalText') or ''} {item.get('description') or ''}"
    if any(c["kind"] in ("ASSET", "CAR") for c in made) and RELAXED_LIMIT.search(text):
        return ["출생 자녀에 따른 한도 완화 문구가 있는데 예외로 받지 못했습니다"]
    return []


# 거주지 뒤에 남으면 안 되는 말(다른 조건·예외·대상)
RESIDENCE_REST = re.compile(r"\d|무주택|소득|자산|자녀|혼인|신혼|청년|대학|고령|장애|수급|등\b|및|또는|이상|이하|미만|초과|단[,\s]|다만|제외|불가|외국인|가능")
SIMPLE_RESIDENCE = re.compile(
    r"^(?P<region>(?:\S+(?:특별시|광역시|특별자치시|특별자치도|도))(?:\s*\S+(?:시|군|구))?)\s*에\s*(?:주민등록(?:이|을|이\s*되어)?\s*(?:등재|되어|된|한)?|거주)"
)


def _text(ctx: Context, item: dict[str, Any], text: str, reasons: list[str]) -> Made | None:
    """「서울특별시에 주민등록된 …」처럼 지역 하나에 사는 사람만 되는 문장 → 거주지. 「또는」「연접」·소득 근거지·대학 소재지가 섞이면 하지 않습니다."""
    if ctx.regions is None or re.search(r"또는|연접|인근|소득\s*근거지|대학|직장|근무", text):
        return None
    match = SIMPLE_RESIDENCE.match(text)
    if not match:
        return None
    found = ctx.regions.lookup(match.group("region"))
    if not found.code or found.level not in ("SIDO", "SIGUNGU"):
        return None
    if RESIDENCE_REST.search(text[match.end() :]):
        # 「서울특별시에 거주하는 만 19세 이상 39세 이하 무주택자」: 거주지만 읽고 나이·무주택을 버린 채 성공으로 처리했음(2026-10-21 리뷰).
        # 거주지 말고 다른 조건이 남으면 문장 전체를 질문으로 둡니다
        return [ask_whole(ctx, item, text, "거주지와 다른 조건(나이·무주택 등)이 한 문장에 있어 거주지만 떼어 낼 수 없습니다")], []
    residence = {**base_fields(ctx.new_id(item["id"]), "RESIDENCE", text), "regionCodes": [found.code], "minMonths": None}
    ctx.flag(residence, reasons)
    return [residence], []


# 국적 문장에서 국적 말고는 뜻이 없는 말
NATIONALITY_FILLER = re.compile(
    r"외국인|내국인|국적자?|대한민국|재외\s*국민|신청인|계약자|신청자|신청|청약|입주|공급|불가(?:합니다|함|능)?|가능(?:합니다)?|한(?:함|합니다|정)|법인|단|및|또는|"
    r"경우|에게|에는|에|은|는|의|이|가|도|[()\[\],.※:·\s]"
)
# 문장에 있는데 조건식에 없으면 안 되는 조건: (낱말, 조건식 속성)
REFLECTED = (
    (re.compile(r"무주택"), {"HOMELESS"}, "무주택"),
    (re.compile(r"\d+\s*세|성년"), {"AGE_YEARS"}, "나이"),
    (re.compile(r"소득"), {"INCOME_BENCHMARK_PERCENT", "MONTHLY_INCOME_KRW"}, "소득"),
    (re.compile(r"자산"), {"TOTAL_ASSETS_KRW", "CAR_ASSETS_KRW"}, "자산"),
)


def _unreflected(item: dict[str, Any], text: str) -> list[str]:
    """거주지 문장에서 거주지 말고 나오는 조건 중 이 항목의 조건식에 없는 것."""
    match = re.search(r"거주|주민등록", text)
    if not match:
        return []
    rest = text[match.end() :]
    attributes = {a.get("attribute") for a in _atoms_of(item["rule"].get("expression"))}
    return [name for pattern, needs, name in REFLECTED if pattern.search(rest) and not attributes & needs]


def _atoms_of(node: dict[str, Any] | None):
    if not node:
        return
    if node.get("kind") == "ATOMIC":
        yield node
    for child in node.get("children") or []:
        yield from _atoms_of(child)


def _engaged(item: dict[str, Any]) -> bool:
    words = " ".join([*((item.get("scope") or {}).get("targetGroups") or []), item.get("appliesTo") or "", item.get("originalText") or ""])
    return "예비신혼" in words or "예비 신혼" in words


CHILD_AGE = re.compile(r"미성년|성년|\d+\s*세\s*(?:이하|미만)")
# 신청자가 아닌 사람의 나이: 「65세 이상의 직계존속」「만 6세 이하 자녀」「배우자가 만 39세 이하」
OTHER_PERSON_AGE = re.compile(
    r"\d+\s*세\s*(?:이상|이하|미만|초과)?\s*(?:\([^)]*\)\s*)?(?:인\s*|의\s*)?(?:직계\s*존속|부모|노부모|조부모|자녀|손자녀|배우자|세대원|형제|피부양)"
    r"|(?:직계\s*존속|부모|노부모|조부모|자녀|배우자|세대원)\S{0,3}\s*(?:나이|연령|만\s*\d+\s*세)"
)


def _youngest_age(text: str) -> int | None:
    """「6세 이하 자녀」「만 7세 미만」「미성년 자녀」(민법상 19세 미만 → 18세 이하) → 막내 나이 상한."""
    match = re.search(r"(?:만\s*)?(\d+)\s*세\s*이하", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:만\s*)?(\d+)\s*세\s*미만", text)
    if match:
        return int(match.group(1)) - 1
    return 18 if "미성년" in text else None


# 맞벌이·가구원 수 말고 다른 조건이 섞인 예외(자녀·출산, 「2인 가구 제외」)는 기본 기준과 같은지 코드로 따지지 않습니다
COVER_OTHER = re.compile(r"출산|출생|자녀|신생아|태아|제외|아닌|외에|미만|초과|이상")


def _covered(base: list[Criterion], exception: dict[str, Any], replaced: list[Criterion]) -> bool:
    """「맞벌이 2인 가구는 소득 130%」처럼 예외가 바꾼 소득 기준이 기본 소득 조건의 가산(맞벌이 20%p + 2인 10%p)과 같으면 True.
    같은 사람에게 같은 기준이라 선택지를 두면 판정은 같고 질문만 늘어납니다(2026-10-22 실측 28개 선택지)."""
    incomes = [c for c in base if c["kind"] == "INCOME"]
    if len(incomes) != 1 or len(replaced) != 1 or replaced[0]["kind"] != "INCOME":
        return False
    income, other = incomes[0], replaced[0]
    if income["percent"] is None or other["percent"] is None or other["bonuses"] or income["bonusCombine"] != "SUM":
        return False
    if any(income[k] != other[k] for k in ("basis", "standard", "year")):
        return False
    text = " ".join(str(exception.get(k) or "") for k in ("description", "originalText"))
    text += " " + str((exception.get("when") or {}).get("reason") or "")
    if COVER_OTHER.search(text):
        return False
    dual = "맞벌이" in text
    sizes = {int(n) for n in re.findall(r"([1-9])\s*인", text)}
    if len(sizes) > 1 or not (dual or sizes):
        return False
    size = next(iter(sizes), None)
    add = 0.0
    for bonus in income["bonuses"]:
        when = bonus["when"]
        if when["factor"] == "DUAL_INCOME" and dual:
            add += bonus["addPercent"]
        elif when["factor"] == "HOUSEHOLD_SIZE" and size is not None and when["min"] is not None:
            if when["min"] <= size <= (when["max"] if when["max"] is not None else size):
                add += bonus["addPercent"]
        elif when["factor"] not in ("DUAL_INCOME", "HOUSEHOLD_SIZE"):
            return False  # 출산자녀 같은 다른 가산이 기본 기준에 있으면 따지지 않음
    has_dual = any(b["when"]["factor"] == "DUAL_INCOME" for b in income["bonuses"])
    has_size = size is None or any(b["when"]["factor"] == "HOUSEHOLD_SIZE" and b["when"]["min"] == size for b in income["bonuses"])
    return (not dual or has_dual) and has_size and income["percent"] + add == other["percent"]


SPEC = Spec(
    schema="housing-judgment.v1",
    atom=_atom,
    statuses_of=lambda name: statuses_of(name, STATUS_WORDS),
    status_codes=lambda text: status_codes(text, STATUS_WORDS),
    status_rest=lambda text: status_rest(text, STATUS_WORDS),
    text=_text,
    automatic=frozenset({"AGE", "RESIDENCE", "HOMELESS", "INCOME", "ASSET", "CAR"}),
    readback=readback_mismatch,
    absorb=_absorb,
    covered=_covered,
    extra_reasons=_extra,
    merge=_merge,
    copy_selection_notes=False,
)


def build_housing(candidate: dict[str, Any], regions: Any = None, *, approved: bool = False) -> dict[str, Any] | None:
    return build_frame(candidate, regions, SPEC, approved=approved)
