"""원문 금액(sourceAmount + sourceUnit)을 원 단위 정수(amountKrw)로 환산합니다.

원문 값은 고치지 않고 그대로 두며, 이 함수는 계산값만 만듭니다. 정확한 원 단위 정수로 떨어지지 않거나 해석할 수 없으면
None과 사유를 돌려주고 추정하지 않습니다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

UNIT_SCALES = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "십만원": 100_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}
# "1억 2,000만", "3억5천만원"처럼 단위가 섞인 표기. 억·만으로 큰 묶음을 나누고, 묶음 안은 천·백·십으로 읽습니다.
LARGE = re.compile(r"(?:(?P<eok>[^억만]+)억)?(?:(?P<man>[^억만]+)만)?(?P<rest>[^억만]*)")
SMALL = re.compile(r"(?:(?P<cheon>[\d.]*)천)?(?:(?P<baek>[\d.]*)백)?(?:(?P<sip>[\d.]*)십)?(?P<one>[\d.]*)")


@dataclass(frozen=True)
class AmountResult:
    amount_krw: int | None
    reason: str | None  # amount_krw가 None일 때 검수 사유


# 글자만 든 괄호 꼬리말(「(정액)」「(부가세 포함)」). 단위(「(만원)」)·미정 표시는 금액을 바꾸므로 떼지 않습니다
AMOUNT_NOTE = re.compile(r"\s*\(\s*(?![^)]*(?:원|미정))[가-힣][가-힣\s]{0,9}\)\s*$")
TWO_AMOUNTS = re.compile(r"\d[\d,.]*\s+\(?[+\-−]?\)?\s*\d")
# 마침표 뒤 숫자가 꼭 세 자리(「18,400.000」「389.000」)면 자릿수 쉼표를 마침표로 잘못 찍은 것인지 소수점인지 글자만으로 정할 수 없습니다
POINT_OR_COMMA = re.compile(r"\d\.\d{3}(?!\d)")


def _clean(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split()).replace(",", "")


def _decimal(text: str) -> Decimal:
    value = Decimal(text)
    if not value.is_finite() or value < 0:
        raise InvalidOperation
    return value


def _exact_int(value: Decimal) -> int | None:
    return int(value) if value == value.to_integral_value() else None


def _small(text: str) -> Decimal | None:
    """만 미만 묶음: "5천", "2000", "1천2백" → 숫자. 숫자 없이 "천"만 있으면 1천으로 읽습니다."""
    match = SMALL.fullmatch(text)
    if not match or not text:
        return None
    total = Decimal(0)
    for key, scale in (("cheon", 1000), ("baek", 100), ("sip", 10), ("one", 1)):
        digits = match[key]
        if digits is None or (key == "one" and digits == ""):
            continue
        total += (_decimal(digits) if digits else Decimal(1)) * scale
    return total


def to_krw(source_amount: str | None, source_unit: str | None) -> AmountResult:
    """원문 금액과 단위를 원 단위 정수로 환산합니다. 모호하거나 읽을 수 없으면 금액 대신 검수 사유를 담아 돌려줍니다."""
    if source_amount is None or not _clean(source_amount):
        return AmountResult(None, "원문 금액이 없습니다.")
    # 칸 하나에 금액 두 개(「12,614 2,614」: 전환 증액·감액이 위아래로 한 칸)를 붙여 읽으면 126,142,614처럼 엉뚱한 금액이 됩니다
    # (실측 2026-10-18 LH 포항 행복주택: 1,261억 원 보증금이 자동 게시됨). 공백으로 떨어진 숫자가 둘 이상이면 읽지 않습니다
    if TWO_AMOUNTS.search(unicodedata.normalize("NFKC", source_amount)):
        return AmountResult(None, f"금액이 둘 이상 적혀 있습니다: {source_amount!r}")
    # 실측(2026-11-07 23건 대조, jbdc-16011): 계약금 칸 「18,400.000」(보증금 92,000,000 = 18,400,000 + 잔금 73,600,000)을
    # 소수점으로 읽어 계약금 18,400원이 자동 게시됨. 어느 쪽인지 짐작하지 않고 검수로 넘깁니다
    if POINT_OR_COMMA.search("".join(unicodedata.normalize("NFKC", source_amount).split())):
        return AmountResult(None, f"마침표 뒤 숫자가 세 자리라 자릿수 쉼표의 오타인지 소수점인지 모호합니다: {source_amount!r}")
    # 금액 뒤 괄호 꼬리말(「500 (정액)」「1,000(부가세 포함)」)은 금액의 성격을 말할 뿐이라 떼고 읽습니다(2026-10-24 세 번째 채점:
    # 계약금 「500 (정액)」이 환산되지 않아 화면에 계약금 숫자가 없었음). 꼬리말에 숫자가 있으면 다른 금액일 수 있어 떼지 않습니다
    amount = _clean(AMOUNT_NOTE.sub("", unicodedata.normalize("NFKC", source_amount)))
    unit = _clean(source_unit or "")
    # "원/호", "만원/월"처럼 단위 뒤에 붙은 기준(호당·월당)은 금액 환산과 무관해 뗍니다(기준은 billingPeriod·scope로 표현).
    # 실측: 청년 전세임대 지원한도액 "120백만" / "원/호"
    unit = re.sub(r"/[^/]*$", "", unit)
    # 칸에도 열과 같은 단위가 붙은 금액(「100만원」 + 열 단위 「만원」)은 단위를 한 번만 씁니다(2026-11-07 23건 대조 gndc: 보증금 「100만원」·
    # 월세 「7만원」 14개가 해석할 수 없는 표기로 남음). 단위를 뗀 나머지가 숫자뿐일 때만: 「1,000만」 + 「만원」처럼 다른 단위가 겹친 것은 그대로 읽지 않습니다
    if unit in UNIT_SCALES and unit != "원" and amount.endswith(unit) and re.fullmatch(r"[\d.]+", amount[: -len(unit)]):
        amount = amount[: -len(unit)]
    if amount.endswith("원"):  # "1,000만원"처럼 단위가 금액 칸에 붙은 경우
        amount, unit = amount[:-1], "원" if not unit else unit
    try:
        if re.fullmatch(r"[\d.]+", amount):
            if unit not in UNIT_SCALES:
                return AmountResult(None, f"알 수 없는 금액 단위입니다: {source_unit!r}")
            krw = _exact_int(_decimal(amount) * UNIT_SCALES[unit])
        else:
            match = LARGE.fullmatch(amount)
            groups = [(match[key], scale) for key, scale in (("eok", 100_000_000), ("man", 10_000), ("rest", 1))] if match else []
            if not match or unit not in {"", "원"} or not any(text for text, _ in groups):
                return AmountResult(None, f"해석할 수 없는 금액 표기입니다: {source_amount!r}")
            if match["eok"] and not match["man"] and re.search(r"[천백십]", match["rest"] or ""):
                # 「2억5천」은 말로는 대개 2억 5천만(250,000,000)이지만 글자 그대로는 2억 5천(200,005,000)입니다.
                # 어느 쪽인지 짐작하지 않고 검수로 넘깁니다(검토 2026-10-16: 200,005,000으로 조용히 읽던 것)
                return AmountResult(None, f"억 뒤에 '만' 없이 천·백·십이 있어 금액이 모호합니다: {source_amount!r}")
            total = Decimal(0)
            for text, scale in groups:
                if text:
                    value = _small(text)
                    if value is None:
                        return AmountResult(None, f"해석할 수 없는 금액 표기입니다: {source_amount!r}")
                    total += value * scale
            krw = _exact_int(total)
    except InvalidOperation:
        return AmountResult(None, f"숫자가 아닌 금액입니다: {source_amount!r}")
    if krw is None:
        return AmountResult(None, "원 단위 정수로 떨어지지 않습니다.")
    return AmountResult(krw, None)


RANGE = re.compile(r"^\s*(.+?)\s*(?:~|∼|～|〜|-|－)\s*(.+?)\s*$")


def range_krw(source_amount: str | None, source_unit: str | None) -> tuple[int, int] | None:
    """「1,200만~1,500만」「12,000,000 ~ 15,000,000」처럼 범위로만 적은 금액 → (작은 값, 큰 값). 양쪽을 같은 단위로 읽습니다.
    한쪽만 단위가 붙은 「1,200~1,500만원」은 뒤쪽 단위를 앞쪽에도 씁니다. 읽지 못하거나 거꾸로면 None."""
    match = RANGE.match(source_amount or "")
    if not match:
        return None
    low, high = match[1], match[2]
    unit_tail = re.search(r"[^\d.,\s]+$", high)
    if unit_tail and re.fullmatch(r"[\d.,\s]+", low):
        low = low + unit_tail[0]
    first, second = to_krw(low, source_unit).amount_krw, to_krw(high, source_unit).amount_krw
    if first is None or second is None or first > second:
        return None
    return first, second
