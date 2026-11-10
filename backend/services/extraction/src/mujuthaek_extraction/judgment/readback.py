"""두 방법 일치(2026-10-21 결정): 자동 판정하는 큰 조건의 값을 코드가 원문(조건의 quote)에서 따로 읽어, AI가 뽑은 값과 같을 때만 확정합니다.

AI는 한 문장에 숫자가 여럿이면 다른 숫자를 고르거나 옮기다 틀릴 수 있습니다. 코드가 같은 원문에서 그 종류의 값을 딱 하나로 읽고
그 값이 틀의 값과 같으면 확정, 못 읽거나 여럿이거나 다르면 이유를 돌려줘 확인 필요로 둡니다.
- 나이: 「만 19세 이상」「39세 이하」「19~39세」「성년자」(가족의 나이 「65세 이상의 직계존속」은 뺌)
- 소득: 괄호 밖의 「N% 이하·이내·미만」(괄호 안 「1인 90%」는 가구원 수 가산이라 뺌)
- 총자산·자동차: 단위가 붙은 금액(「34,500만원」「( 4,542 )만원」「345,000,000원」)을 앞말로 나눔(「자동차」가 앞에 있으면 자동차)
- 무주택: 「무주택」 낱말
- 거주지: 원문의 시·도·시군구 이름을 지역표로 찾은 코드에 틀의 코드가 있는지
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_extraction.assemble.values import to_krw

OTHER_PERSON = r"(?:\s*\([^)]*\))?\s*(?:인\s*|의\s*)?(?:직계\s*존속|부모|노부모|조부모|자녀|손자녀|배우자|세대원|형제|피부양|아동)"
AGE_RANGE = re.compile(r"(?:만\s*)?(\d{1,3})\s*세?\s*[~∼～-]\s*(?:만\s*)?(\d{1,3})\s*세")
AGE_BOUND = re.compile(r"(?:만\s*)?(\d{1,3})\s*세\s*(이상|이하|미만|초과)")
ADULT = re.compile(r"(?<!미)성년")
PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|퍼센트)\s*(?:\([^)]*\)\s*)?(이하|이내|미만)")
# 「34,500만원」「( 4,542 )만원」「345,000,000원」「3억 4,500만원」「2억4천5백만원」「49,960천원」
AMOUNT = re.compile(r"(?:\d[\d,]*\s*억\s*)?(?:\(\s*)?(?:\d+\s*[천백십]\s*)*(?:\d[\d,]*(?:\.\d+)?)?(?:\s*\))?\s*(?:천만|백만|십만|만|천)?\s*원")
# 금액 앞의 항목 이름: 가장 가까운 것이 그 금액의 종류
LABEL = re.compile(r"(?P<car>자동차|차량)|(?P<asset>총\s*자산|자산)")
HOMELESS_WORDS = re.compile(r"무주택|주택[^.]{0,15}?소유하(?:지|고\s*있지)\s*(?:않|아니)")
# 무주택을 요구하지 않는 문장(「무주택자가 아니어도 신청 가능」「주택 소유 여부와 관계없이」, 리뷰 2026-10-22)
HOMELESS_WAIVED = re.compile(r"아니(?:어|여)도|관계\s*없|무관|불문|따지지\s*않|(?:신청|청약)\s*(?:이\s*)?가능|(?:도|이상도)\s*가능")
# 지역 이름 뒤에 붙으면 그 지역은 신청 지역이 아님(「경상남도 김해시 거주자는 제외」)
REGION_EXCLUDED = re.compile(r"^[^,.;]{0,15}?(?:제외|불가|제한|안\s*됩니다)")
NO_CAR = re.compile(r"(?:자동차|차량)[^.]{0,25}?소유하(?:지|고\s*있지)\s*(?:않|아니)|차량\s*미소유")
PERCENT_PLAIN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|퍼센트)\s*(이하|이내|미만)")
LIMIT = re.compile(r"불가|(?:하|되|받)(?:실|을|ㄹ)?\s*수\s*없|할\s*수\s*없|될\s*수\s*없|제외")
ASIDE = re.compile(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）")


def ages(text: str) -> tuple[int | None, int | None] | None:
    """원문의 신청자 나이 범위(하한, 상한). 서로 다른 하한·상한이 둘 이상이거나 나이가 없으면 None."""
    lows, highs = set(), set()
    # 「미성년자(19세 미만)는 신청할 수 없습니다」: 금지 문장은 방향이 반대(19세 미만 불가 = 19세 이상)
    limit = bool(LIMIT.search(ASIDE.sub(" ", text)))  # 괄호 안 「(단, 외국인 신청불가)」는 이 문장의 방향이 아님
    for m in AGE_RANGE.finditer(text):
        if not re.match(OTHER_PERSON, text[m.end() :]):
            lows.add(int(m[1]))
            highs.add(int(m[2]))
    rest = AGE_RANGE.sub(" ", text)
    for m in AGE_BOUND.finditer(rest):
        if re.match(OTHER_PERSON, rest[m.end() :]):
            continue  # 「65세 이상의 직계존속」: 가족의 나이
        value, way = int(m[1]), m[2]
        if limit:
            way = {"이상": "미만", "초과": "이하", "이하": "초과", "미만": "이상"}[way]
        if way == "이상":
            lows.add(value)
        elif way == "초과":
            lows.add(value + 1)
        elif way == "이하":
            highs.add(value)
        else:
            highs.add(value - 1)
    if ADULT.search(text) and not lows and not limit:
        lows.add(19)
    if len(lows) > 1 or len(highs) > 1 or not (lows or highs):
        return None
    return (next(iter(lows)) if lows else None, next(iter(highs)) if highs else None)


def _without_brackets(text: str) -> str:
    """괄호 안 부연을 안쪽부터 지웁니다(「100% (【완화조건】120%(2순위)) 이하」 → 「100% 이하」)."""
    previous = None
    while previous != text:
        previous, text = text, re.sub(r"\([^()]*\)|【[^【】]*】|\[[^\[\]]*\]", "", text)
    return text


def percents(text: str) -> set[float]:
    """괄호 밖의 「N% 이하·이내·미만」 기준 비율들."""
    return {float(m[1]) for m in PERCENT_PLAIN.finditer(_without_brackets(text))}


def percents_anywhere(text: str) -> set[float]:
    return {float(m) for m in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|퍼센트)", text)}


def amounts(text: str) -> dict[str, set[int]]:
    """단위가 붙은 금액을 총자산(ASSET)·자동차(CAR)로 나눕니다. 금액 바로 앞 25자 안에 「자동차」가 있으면 자동차."""
    found: dict[str, set[int]] = {"ASSET": set(), "CAR": set(), "ANY": set()}
    for m in AMOUNT.finditer(text):
        written = re.sub(r"[\s()]", "", m[0])
        if not re.search(r"\d", written):
            continue
        krw = to_krw(written, None).amount_krw
        if krw is None:
            continue
        labels = list(LABEL.finditer(text, 0, m.start()))
        if not LABEL.search(text):
            found["ANY"].add(krw)  # 항목 이름이 없는 문장(「4,542만원 이하 일 것」): 금액이 하나뿐일 때만 그 조건의 값으로 봄
        else:
            found["CAR" if labels and labels[-1]["car"] else "ASSET"].add(krw)
    return found


def mismatch(criterion: dict[str, Any], regions: Any = None) -> str | None:
    """코드가 원문에서 읽은 값이 틀의 값과 다르거나 하나로 읽히지 않으면 그 이유, 같으면 None."""
    kind, text = criterion["kind"], str(criterion.get("quote") or "")
    unread = "코드가 원문에서 같은 값을 하나로 읽지 못해 AI 값과 대조할 수 없습니다"
    if not text:
        return "원문 문장이 없어 AI 값과 대조할 수 없습니다"
    if kind == "AGE":
        read = ages(text)
        if read is None:
            return unread
        return None if read == (criterion.get("minAge"), criterion.get("maxAge")) else f"원문에서 코드가 읽은 나이({read})가 AI 값과 다릅니다"
    if kind == "INCOME":
        if re.search(r"\d+(?:\.\d+)?\s*(?:%|퍼센트)\s*(?:초과|이상)", _without_brackets(text)):
            return unread  # 「50% 초과 70% 이하」: 틀의 소득 칸은 상한만이라 하한이 빠짐(리뷰 2026-10-22)
        read = percents(text)
        if len(read) != 1 or float(criterion["percent"]) in percents_anywhere(text) - read:
            return unread  # 괄호 안 「맞벌이 90%」 같은 다른 기준이 AI 값이면 어느 쪽인지 코드로 못 정함
        return None if read == {float(criterion["percent"])} else f"원문에서 코드가 읽은 소득 비율({read.pop():g}%)이 AI 값과 다릅니다"
    if kind == "CAR" and NO_CAR.search(text):
        return None if criterion["maxWon"] == 0 else "원문은 자동차를 소유하지 않아야 하는데 AI 값이 0원이 아닙니다"
    if kind in ("ASSET", "CAR"):
        found = amounts(text)
        read = found[kind] or found["ANY"]
        if len(read) != 1:
            return unread
        return None if read == {criterion["maxWon"]} else f"원문에서 코드가 읽은 금액({read.pop():,}원)이 AI 값과 다릅니다"
    if kind == "HOMELESS":
        if HOMELESS_WAIVED.search(text):
            return "원문이 무주택을 요구하지 않는 문장일 수 있어 AI 값과 대조할 수 없습니다"
        return None if HOMELESS_WORDS.search(text) else "원문 문장에 무주택 표현이 없어 AI 값과 대조할 수 없습니다"
    if kind == "RESIDENCE":
        if regions is None:
            return "지역표가 없어 거주 지역을 대조할 수 없습니다"
        # 괄호 안 부연과 뒤에 「제외·불가」가 붙은 지역은 빼고 모읍니다(리뷰 2026-10-22: 「부산 거주자(김해 거주자는 제외)」의 김해도 맞다고 봄)
        plain = _without_brackets(text)
        names = [
            m.group(0)
            for m in re.finditer(r"[가-힣]+(?:특별자치시|특별자치도|특별시|광역시|도|시|군|구)", plain)
            if not REGION_EXCLUDED.match(plain[m.end() :])
        ]
        codes = {regions.lookup(name).code for name in names} - {None}
        return None if set(criterion.get("regionCodes") or []) <= codes and codes else "원문에서 코드가 읽은 지역이 AI 값과 다릅니다"
    return None
