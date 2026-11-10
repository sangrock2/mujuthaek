"""V9 값–인용 대조 (2026-10-16 검토 후 추가): 값이 자기 근거 인용문 안에 실제로 있는지 봅니다.

V2는 인용문이 원문에 있는지만 봅니다. 그래서 인용문은 진짜인데 값을 잘못 옮긴 경우(「만 39세 이하」를 45로)가 자동 완료되었습니다.
여기서는 숫자·날짜 값마다 그 값이 근거 인용문들 중 하나에 나오는지 확인합니다. 나오지 않으면 VALUE_NOT_IN_QUOTE.

- 자격 조건 숫자(나이·소득 비율·금액·개월·인원), 공고일, 일정 날짜, 모집 수, 전용면적, 원문 금액(sourceAmount)
- 숫자 표기 차이는 허용: 쉼표·띄어쓰기("1 ,000,000"), 억·만원 표기(34,500만원 = 345,000,000), 표 단위(천원·만원),
  한글 수("두 자녀"), 년↔개월(2년 = 24개월), 날짜 표기(2026. 8. 10. / 8월 10일 / 8.10~14의 끝날)
- 값이 비었거나 근거가 없는 항목은 다른 검사(CLAIM_UNSUPPORTED)가 다룹니다. 여기서는 판단하지 않습니다.
- 공고일은 자기 인용문에 없어도 원문의 '공고일' 표기가 모두 그 날짜이거나, 원문 표기와 어긋나지 않고 API 공고일과 같으면 표시만 합니다(2026-10-20).
- 판정 섹션(자격·공고일)은 값이 **자기 인용문**에 있어야 합니다. 공급·일정은 AI가 가격 행만 인용하고 면적·수량은 다른 표에서
  가져오는 일이 많아(실측 약 100건 중 200여 건), 자기 인용문에 없으면 **원문 어디에도 없을 때만** 의심합니다(값 자체가 틀린 경우).
- 원문에 숫자로 안 적히는 값: 0(「소유하지 않아야」), 호실 하나의 모집 수 1, 「1인 70%, 2인 60%」 다음의 3인 이상 구간
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_extraction.verify.exceptions import _values as amounts_in
from mujuthaek_extraction.verify.model import Finding, SourceBundle
from mujuthaek_extraction.verify.tables import UNIT_WORDS, Place, columns_of, place_of, unit_of, units_in

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
KOREAN_NUMBERS = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
KOREAN_NUMBER = re.compile(r"(하나|다섯|여섯|일곱|여덟|아홉|한|두|둘|세|셋|네|넷|열)\s*(?:명|자녀|사람|가구|세대|인|개|번|회|살|세)")
ADULT = re.compile(r"성년")  # 「성년자」「미성년자」: 나이 숫자 없이 민법상 19세를 뜻함
TABLE_SCALES = (1, 1_000, 10_000, 1_000_000)  # 표 머리 "(단위: 천원)"·「( 337 )백만원」처럼 단위가 따로 있는 칸
# 숫자 바로 뒤의 단위(괄호 하나는 건너뜀: 「( 4,563 )만원」)
UNIT_AFTER = re.compile(r"\s*\)?\s*(백\s*만\s*원|천\s*만\s*원|천\s*원|만\s*원|억\s*원|원|억|만)")
SHORT_UNITS = {"억": 100_000_000, "만": 10_000, "천만원": 10_000_000}
SCALE_WORDS = {1_000: "천원", 10_000: "만원", 1_000_000: "백만원"}
CHILD_WORDS = r"(?:자녀|출생|출산|아동|미성년|직계\s*비속|손자녀|자식)"
KOREAN_OF = {v: k for k, v in KOREAN_NUMBERS.items() if len(k) == 1}
Cited = list[tuple[str, Place | None]]


# LH 주택형 코드: 전용면적(소수 넷째 자리까지) + 형 문자(supply_tables.TYPE_CODE_AREA와 같음. 검증 모듈이 추출 모듈을 가져오지 않게 따로 둠)
TYPE_CODE_AREA = re.compile(r"\s*0*(\d{1,3}\.\d{2})\d{2}[A-Z]")


def _clean(text: str) -> str:
    return re.sub(r"(?<=\d)\s+(?=[,.]\d)|(?<=[,.])\s+(?=\d)", "", text)


def _numbers(text: str) -> set[float]:
    out = set()
    for token in NUMBER.findall(_clean(text)):
        try:
            out.add(float(token.replace(",", "")))
        except ValueError:
            continue
    out |= {float(KOREAN_NUMBERS[word]) for word in KOREAN_NUMBER.findall(text)}
    return out


def _has_number(texts: list[str], value: float, unit: str | None = None, *, at_least: bool = False, attribute: str | None = None) -> bool:
    if value == 0:
        return True  # 「소유하지 않아야」「없는 자」처럼 0은 숫자로 적히지 않습니다
    numbers = set().union(*(_numbers(t) for t in texts))
    if at_least and unit == "COUNT" and attribute == "HOUSEHOLD_MEMBER_COUNT" and float(value - 1).is_integer():
        # 「50%(1인 70%, 2인 60%)」의 나머지 구간 = 3인 이상. 가구원 수 구간 문장에만 씁니다(2026-10-21 리뷰: 자녀 수에도 적용되어
        # 「자녀 2명 이상」을 3명 이상으로 뽑아도 통과했음)
        if any(re.search(rf"(?<!\d){int(value - 1)}\s*인\s*(?:가구)?\s*\d+(?:\.\d+)?\s*(?:%|퍼센트)", t) for t in texts):
            return True
    candidates = {value}
    if unit == "MONTH" and value % 12 == 0:
        candidates.add(value / 12)  # 2년 = 24개월
    if unit == "KRW":
        if any(abs(a - value) < 0.5 for t in texts for _, a, _ in amounts_in(_clean(t), "KRW")):
            return True
        candidates |= {value / scale for scale in TABLE_SCALES}
    return any(abs(n - c) < 0.005 for n in numbers for c in candidates)


def _krw_found(cited: Cited, value: float) -> bool:
    """금액이 원문에 숫자와 단위가 함께 확인되는지(2026-10-21 리뷰: 「3,708만원」을 3,708,000원으로 뽑아도 통과했음).
    - 단위가 붙은 금액(「3,708만원」「( 4,563 )만원」)은 그 단위로 환산한 값만 인정합니다.
    - 단위가 따로 없는 칸(표의 「37,100」)은 원 단위 그대로이거나, 같은 열 머리글·같은 표 위 단위 표시(「(단위: 만원)」)가 있을 때만 그 단위로 인정합니다."""
    if value == 0:
        return True
    for quote, place in cited:
        q = _clean(quote)
        if any(abs(a - value) < 0.5 for _, a, _ in amounts_in(q, "KRW")):
            return True
        for m in NUMBER.finditer(q):
            try:
                n = float(m[0].replace(",", ""))
            except ValueError:
                continue
            after = UNIT_AFTER.match(q, m.end())
            if after:
                word = unit_of(after[1])
                scale = UNIT_WORDS.get(word) or SHORT_UNITS.get(word)
                if scale and abs(n * scale - value) < 0.5:
                    return True
                continue
            if abs(n - value) < 0.5:
                return True
            for scale, word in SCALE_WORDS.items():
                if abs(n * scale - value) < 0.5 and _unit_confirmed(word, q, place, m[0]):
                    return True
    return False


def _unit_confirmed(word: str, quote: str, place: Place | None, token: str) -> bool:
    """단위 없는 숫자 token의 단위가 word(천원·만원 등)라는 근거: 인용문의 단위 표시, 같은 열 머리글, 같은 표 위 단위 표시."""
    if word in units_in(quote):
        return True
    if place is None:
        return False
    columns = [c for c in columns_of(place, token) if c < len(place.headers)]
    if columns:
        # 열 머리글의 단위가 우선(여러 줄 머리글이면 가장 아래 줄). 같은 값이 여러 칸이면 그 칸들의 단위가 모두 같아야 합니다
        marked = [units_in(place.headers[c])[-1:] for c in columns]
        if all(marked):
            return all(m[0] == word for m in marked)
        if any(marked):
            return False
    return bool(place.units) and place.units[0] == word


def _added_points(texts: list[str], points: float) -> bool:
    """「20%p 가산」「(+10%p)」「10%p」「20% 추가 완화」: 가산 폭 points가 적혀 있는지."""
    shown = re.escape(f"{points:g}")
    return any(
        re.search(rf"(?<![\d.]){shown}\s*%\s*p", t) or re.search(rf"(?<![\d.]){shown}\s*(?:%|퍼센트)[^.%]{{0,20}}(?:가산|추가|완화|상향)", t) for t in texts
    )


def _count_bound(attribute: str, value: float, cited: Cited, operator: str | None = None) -> bool:
    """자녀 수·가구원 수 값이 그 대상의 수로 적혀 있는지(2026-10-21 리뷰: 「3인 이상 2인 이상」에서 가구원 수 3을 자녀 수로 뽑아도
    숫자 3이 있어 통과했음). 문장이면 낱말과 붙어 있어야 하고, 표 줄이면 그 칸의 열 머리글이 그 대상이어야 합니다."""
    if value == 0 or not float(value).is_integer():
        return True
    n = int(value)
    korean = KOREAN_OF.get(n)
    # 한 문장이 근거 둘로 나뉘어 인용되는 일이 많습니다(「70%(1인 90%,」 + 「2인 80%)이하」). 낱말 규칙은 인용을 이어 붙여 봅니다
    joined = (" ".join(re.sub(r"\s+", " ", quote) for quote, _ in cited), None)
    for quote, place in [*cited, joined]:
        q = re.sub(r"\s+", " ", quote)
        if attribute == "CHILD_COUNT":
            patterns = [
                rf"{CHILD_WORDS}[^\d|]{{0,15}}(?<!\d){n}\s*(?:명|인|자녀)",
                rf"(?<!\d){n}\s*(?:명|인)\s*(?:이상\s*)?(?:의\s*)?(?:미성년\S*\s*)?{CHILD_WORDS}",
                rf"(?<!\d){n}\s*자녀",
            ]
            if korean:
                patterns.append(rf"{korean}\s*(?:명|자녀)")
            if n == 1 and operator in ("GTE", None):
                patterns.append(rf"{CHILD_WORDS}\S{{0,2}}\s*(?:가|를|이)?\s*(?:있는|둔|양육)")  # 「자녀가 있는」 = 1명 이상
            header = r"자녀|출생|출산|아동"
        else:
            # 「3인 이상 1인 60%」처럼 칸 구분 없이 붙은 숫자는 가구원 수인지 자녀 수인지 모르므로 낱말·괄호 안 구간·열 머리글로만 인정합니다
            bracket = r"\([^)]*(?<!\d){m}\s*인\s*(?:가구)?\s*(?:는|은)?\s*\d+(?:\.\d+)?\s*(?:%|퍼센트)"
            patterns = [
                rf"(?<!\d){n}\s*인\s*(?:이상\s*)?(?:가구|세대)",
                rf"(?:가구원|세대원)[^.|]{{0,40}}?(?<!\d){n}\s*(?:인|명)",
                bracket.format(m=n),
                rf"(?<!\d){n}\s*인\s*(?:이상\s*)?(?:인\s*)?경우",
                rf"(?<![\d~～∼-]){n}\s*[~～∼-]\s*\d+\s*인\s*(?:이상\s*)?(?:가구|세대)",  # 「3～4인 가구」
                rf"\d+\s*[~～∼-]\s*{n}\s*인\s*(?:이상\s*)?(?:가구|세대)",
            ]
            if n > 1 and operator in ("GTE", "GT"):
                patterns.append(bracket.format(m=n - 1))  # 「50%(1인 70%, 2인 60%)」의 나머지 구간 = 3인 이상
            header = r"가구원|가구|세대원|세대\s*구성원"
        if any(re.search(p, q) for p in patterns):
            return True
        if place is not None and place.row is not None:
            if _bound_in_table(place, n, header):
                return True
            if attribute == "HOUSEHOLD_MEMBER_COUNT" and _size_header(place.row, n):
                return True
    return False


def _bound_in_table(place: Place, n: int, header: str) -> bool:
    """표 줄에서 「n인(이상)」 칸의 열 머리글이 그 대상인지. 이 줄의 칸이 비었으면 위 줄과 합친 칸으로 봅니다."""
    cell_of = re.compile(rf"{n}\s*(?:인|명)\s*(?:이상|이하)?")
    for i in range(min(len(place.row), len(place.headers))):
        if not re.search(header, place.headers[i]):
            continue
        cell = place.row[i].strip()
        if not cell:
            cell = next((r[i].strip() for r in place.above if i < len(r) and r[i].strip()), "")
        if cell_of.fullmatch(cell):
            return True
    return False


def _size_header(row: list[str], n: int) -> bool:
    """「| 기준 | 1인 | 2인 | 3인 |」: 가구원 수를 1인부터 차례로 나열한 머리글 줄(자녀 수 열은 「0인 1인 2인 이상」처럼 0부터)."""
    sizes = [int(m[1]) for c in row if (m := re.fullmatch(r"(\d)\s*인\s*(?:가구|이상|이하)?", c.strip()))]
    return len(sizes) >= 3 and sizes[0] == 1 and sizes == list(range(1, len(sizes) + 1)) and n in sizes


def _has_date(texts: list[str], value: dict[str, str] | None, *, end: bool = False, years: set[int] | None = None) -> bool | None:
    """None: 판단 안 함(값 없음·형식 모름). 월·일만이 아니라 연도도 봅니다(2026-10-21: 「2026. 10. 7.」과 2025-10-07이 통과했음).
    - 원문에 그 월·일이 연도와 함께 적혀 있으면 연도까지 같아야 합니다.
    - 연도 없이 적힌 월·일(「10. 7.~10. 9.」)이면 값의 연도가 years(공고일 연도와 다음 해) 안이어야 합니다. years가 없으면 연도는 보지 않습니다."""
    if not value:
        return None
    try:
        day = date.fromisoformat(value["value"][:10]) if value["precision"] != "MONTH" else None
        month = int(value["value"][5:7])
    except (ValueError, KeyError):
        return None
    text = " ".join(_clean(t) for t in texts)
    if day is None:
        return bool(re.search(rf"(?:\d{{4}}|[’']\d{{2}})\s*[./년]\s*0?{month}(?!\d)|(?<!\d)0?{month}\s*월", text))
    m, d = day.month, day.day
    written = _written_dates(text)
    if day in written:
        return True
    # 연도와 함께 적힌 날짜를 지운 나머지에서 연도 없는 월·일을 찾습니다(「2025. 10. 7.」의 「10. 7.」을 연도 없는 표기로 세지 않게)
    rest = re.sub(_DATE_TEXT, " ", text)
    year_ok = years is None or day.year in years
    if year_ok and re.search(rf"(?<!\d)0?{m}\s*(?:[./-]|월)\s*0?{d}(?!\d)", rest):
        return True
    # 「8. 10.(월) ~ 14.(금)」「10월 1일 10시부터 31일 17시까지」처럼 끝날이 일만 적힌 기간
    return bool(year_ok and end and re.search(rf"(?:[~∼-]|부터)\s*0?{d}(?!\d)\s*(?:\.|일|\(|$)", rest))


has_date = _has_date  # 재확인 채택(recheck._keep_verified_dates)에서도 같은 날짜 확인 규칙을 씁니다


def _written_dates(text: str) -> set[date]:
    """연도까지 적힌 날짜들(「2026. 10. 7.」「2026년 10월 7일」「'26.10.07」)."""
    found = set()
    for m in re.finditer(_DATE_TEXT, text):
        year = int(m["y"]) if m["y"] else 2000 + int(m["yy"])
        try:
            found.add(date(year, int(m["m"]), int(m["d"])))
        except ValueError:
            continue
    return found


_DATE_TEXT = (
    r"(?:(?P<y>\d{4})\s*(?:[./-]|년)\s*|[‘’'`]\s*(?P<yy>\d{2})\s*[./]\s*)"
    r"(?P<m>\d{1,2})\s*(?:[./-]|월)\s*(?P<d>\d{1,2})(?!\d)"
)
# 공고일 표기: 「모집공고일은 2026.10.01.(목)」「(입주자 모집공고일 : 2026. 04. 24.)」「공고일(‘26.04.24.)」
# 표기 바로 뒤의 날짜만 봅니다(「공고일 이후(…)」「공고일로부터 10일」은 보지 않음). 「정정공고일」「최초 공고일」도 함께 모여 서로 다르면 확인하지 않습니다
ANNOUNCED_LABEL = re.compile(r"공고\s*일(?:자)?\s*(?:은|는|인|이|:|：)?\s*[(（]?\s*" + _DATE_TEXT)


def labeled_announcement_dates(texts: list[str]) -> set[date]:
    """원문에서 '공고일' 표기 바로 뒤에 적힌 날짜들(연도까지 있는 것만)."""
    found = set()
    for text in texts:
        for m in ANNOUNCED_LABEL.finditer(_clean(text)):
            year = int(m["y"]) if m["y"] else 2000 + int(m["yy"])
            try:
                found.add(date(year, int(m["m"]), int(m["d"])))
            except ValueError:
                continue
    return found


def _atoms(expression: dict[str, Any] | None, path: str):
    if not expression:
        return
    if expression["kind"] == "ATOMIC":
        yield path, expression
    for i, child in enumerate(expression.get("children") or []):
        yield from _atoms(child, f"{path}/children/{i}")


def _amount_parts(text: str) -> set[str]:
    return {re.sub(r"\D", "", n) for n in NUMBER.findall(_clean(text))}


def check_claims(candidate: dict[str, Any], sources: SourceBundle | None = None, *, api_matched: frozenset[str] = frozenset()) -> list[Finding]:
    """숫자·날짜 값이 근거 인용문(공급·일정은 원문 전체도)에 나오는지 보고, 나오지 않는 값마다 VALUE_NOT_IN_QUOTE를 돌려줍니다.
    api_matched: API 대조에서 값이 정확히 같았던(MATCH) 위치. 공고일 확인에만 씁니다."""
    quotes = {e["id"]: e["quote"] for e in candidate["evidence"]}
    places: dict[str, Place] = {}
    for e in candidate["evidence"]:
        locator = e.get("locator") or {}
        if sources and locator.get("kind") == "TEXT_RANGE" and e.get("sourceId") in sources.texts:
            places[e["id"]] = place_of(sources.texts[e["sourceId"]], int(locator.get("start") or 0))
    whole = ["\n".join(sources.texts.values())] if sources and sources.texts else []
    findings: list[Finding] = []

    def texts(*id_lists: list[str] | None) -> list[str]:
        return [quotes[i] for ids in id_lists if ids for i in ids if i in quotes]

    def cited_places(*id_lists: list[str] | None) -> Cited:
        ids = list(dict.fromkeys(i for ids in id_lists if ids for i in ids if i in quotes))
        return [(quotes[i], places.get(i)) for i in ids]

    def miss(target: str, what: str, value: Any, cited: list[str]) -> None:
        shown = " / ".join(q[:60] for q in cited[:2])
        findings.append(Finding("V9", "VALUE_NOT_IN_QUOTE", target, f"{what} {value}이(가) 근거 인용문에 없습니다 「{shown}」"))

    for e, item in enumerate(candidate["eligibility"]):
        # 기본 조건·예외가 발동하는 조건·예외로 바뀌는 기준을 같은 검사로 봅니다(2026-10-21 리뷰: 예외 값은 대조하지 않았음)
        for path, atom, ids in condition_atoms(item, f"/eligibility/{e}"):
            value, unit = atom.get("value"), atom.get("unit")
            if unit not in ("YEAR", "KRW", "PERCENT", "MONTH", "COUNT"):
                continue
            values = value if isinstance(value, list) else [value]
            cited = texts(*ids)
            if not cited:
                continue
            attribute = atom.get("attribute")
            # 예외로 바뀌는 소득 비율: 원문이 「1인 가구 20%p 가산」처럼 가산 폭만 적었으면 기본 비율 + 가산 폭으로 확인합니다(코드 계산)
            bases = [
                float(a["value"])
                for _, a in _atoms(item["rule"].get("expression"), "")
                if a.get("attribute") == attribute and isinstance(a.get("value"), int | float)
            ]
            for v in values:
                if not isinstance(v, int | float) or isinstance(v, bool):
                    continue
                at_least = atom.get("operator") in ("GTE", "GT")
                if attribute == "AGE_YEARS" and v == 19 and any(ADULT.search(t) for t in cited):
                    continue  # 「성년자」「미성년자는 신청 불가」 = 민법상 19세(프롬프트 규칙). 실측: 매번 걸려 재확인 호출을 씀
                if unit == "KRW":
                    found = _krw_found(cited_places(*ids), float(v))
                elif attribute in ("CHILD_COUNT", "HOUSEHOLD_MEMBER_COUNT"):
                    # 숫자만이 아니라 그 대상의 수로 적혀 있어야 합니다(낱말·괄호 구간·열 머리글, 위 줄과 합친 칸 포함)
                    found = _count_bound(attribute, float(v), cited_places(*ids), atom.get("operator"))
                else:
                    found = _has_number(cited, float(v), unit, at_least=at_least, attribute=attribute)
                    if not found and unit == "PERCENT" and "/effectExpression" in path:
                        found = any(_added_points(cited, float(v) - b) for b in bases if float(v) > b)
                if not found:
                    miss(f"{path}/value", attribute or "값", v, cited)
                    break

    notice = candidate["notice"]
    announced = notice.get("announcedOn")
    cited = texts(notice.get("evidenceIds"))
    if announced and cited and _has_date(cited, {"precision": "DAY", "value": announced}) is False:
        # AI가 공고일 대신 제목 줄을 인용하는 일이 잦습니다(실측 LH 4건, 값은 모두 맞음). 값이 따로 확인되면 표시만 합니다.
        # 원문의 '공고일' 표기가 모두 이 날짜 하나이거나, 원문 표기와 어긋나지 않으면서 같은 공고의 API 공고일과 정확히 같을 때만입니다
        labeled = labeled_announcement_dates(whole)
        try:
            day = date.fromisoformat(announced)
        except ValueError:
            day = None
        if day is not None and labeled == {day}:
            note = f"공고일 {announced}: 근거 인용문에는 없지만 원문의 공고일 표기와 같습니다."
            findings.append(Finding("V9", "VALUE_CONFIRMED_IN_SOURCE", "/notice/announcedOn", note))
        elif day is not None and "/notice/announcedOn" in api_matched and labeled <= {day}:
            note = f"공고일 {announced}: 근거 인용문에는 없지만 같은 공고의 API 공고일과 같습니다."
            findings.append(Finding("V9", "VALUE_CONFIRMED_BY_API", "/notice/announcedOn", note))
        else:
            miss("/notice/announcedOn", "공고일", announced, cited)

    # 연도 없이 적힌 일정의 연도: 공고일 연도와 다음 해(12월 공고의 1월 접수). 공고일을 모르면 연도는 보지 않습니다
    try:
        years = {date.fromisoformat(announced).year + k for k in (0, 1)} if announced else None
    except ValueError:
        years = None
    for s, schedule in enumerate(candidate["schedules"]):
        cited = texts(schedule["evidenceIds"])
        if not cited:
            continue
        for key, is_end in (("startsAt", False), ("endsAt", True)):
            found = _has_date(cited, schedule.get(key), end=is_end, years=years)
            if found is False and _has_date(whole, schedule.get(key), end=is_end, years=years) is not True:
                miss(f"/schedules/{s}/{key}", schedule["rawLabel"], schedule[key]["value"], cited)

    for g, group in enumerate(candidate["supplyGroups"]):
        area = group.get("exclusiveAreaSqm")
        cited = texts(group["evidenceIds"])
        # LH 주택형 코드(「084.9079A」)에서 옮긴 면적은 그 코드가 근거입니다(2026-10-24 여덟 번째 채점: 병합된 주택형 칸 아래 층별 행의
        # 인용에 코드가 없어 맞는 면적 때문에 가격 묶음 13개가 통째로 숨음)
        coded = TYPE_CODE_AREA.match(str(group.get("housingTypeCode") or ""))
        from_code = coded is not None and isinstance(area, int | float) and abs(float(coded[1]) - float(area)) < 0.01
        if isinstance(area, int | float) and cited and not from_code and not _has_number(cited + whole, float(area)):
            miss(f"/supplyGroups/{g}/exclusiveAreaSqm", "전용면적", area, cited)
        for c, count in enumerate(group["counts"]):
            cited = texts(count["evidenceIds"])
            single_unit = group.get("itemKind") == "HOUSING_UNIT" and count.get("value") == 1
            if isinstance(count.get("value"), int) and cited and not single_unit and not _has_number(cited + whole, float(count["value"])):
                miss(f"/supplyGroups/{g}/counts/{c}/value", "모집 수", count["value"], cited)
        for p, price in enumerate(group["prices"]):
            cited = texts(price["evidenceIds"])
            parts = _amount_parts(price.get("sourceAmount") or "") - {""}  # 「42,800 ~49,600」은 두 수 모두
            if parts and cited and not parts <= set().union(*(_amount_parts(t) for t in cited + whole)):
                miss(f"/supplyGroups/{g}/prices/{p}/sourceAmount", price["kind"], price["sourceAmount"], cited)
                continue
            unit = unit_of(str(price.get("sourceUnit") or "")).split("/")[0]
            if parts and UNIT_WORDS.get(unit, 1) > 1 and not _price_unit_ok(price.get("sourceAmount") or "", unit, cited_places(price["evidenceIds"])):
                miss(f"/supplyGroups/{g}/prices/{p}/sourceUnit", f"{price['kind']} 단위", price.get("sourceUnit"), cited)
    return findings


def _price_unit_ok(amount: str, unit: str, cited: Cited) -> bool:
    """원문 금액의 단위(천원·만원 등)가 원문에서 확인되는지(2026-10-21 리뷰: 원 단위 칸을 천원으로 읽어 보증금 100만원이 10억이 됨).
    숫자 바로 뒤에 다른 단위가 붙어 있으면 불일치, 단위가 없는 칸이면 같은 열 머리글이나 같은 표 위 단위 표시가 그 단위여야 합니다."""
    tokens = NUMBER.findall(_clean(amount))
    if not tokens:
        return False
    confirmed = False
    for quote, place in cited:
        q = _clean(quote)
        for token in tokens:
            hits = list(re.finditer(rf"(?<![\d,.]){re.escape(token)}(?![\d,])", q))
            for m in hits:
                after = UNIT_AFTER.match(q, m.end())
                if after:
                    word = unit_of(after[1])
                    if word != unit and SHORT_UNITS.get(word) != UNIT_WORDS.get(unit):
                        return False
                    confirmed = True
                elif _unit_confirmed(unit, q, place, token):
                    confirmed = True
            if not hits and place is not None and place.row is not None and _unit_confirmed(unit, "", place, token):
                confirmed = True  # 위아래로 합친 칸: 이 줄은 비어 있고 같은 표 위 줄의 같은 칸에 값이 있음
    return confirmed


def condition_atoms(item: dict[str, Any], base: str):
    """자격 항목의 모든 원자 조건: (위치, 원자, 근거 ID 목록들). 기본 조건, 예외가 발동하는 조건(when), 예외로 바뀌는 기준(effectExpression)."""
    for path, atom in _atoms(item["rule"].get("expression"), f"{base}/rule/expression"):
        yield path, atom, (atom.get("evidenceIds"), item.get("evidenceIds"))
    for x, exception in enumerate(item.get("exceptions") or []):
        ids = exception.get("evidenceIds")
        for path, atom in _atoms((exception.get("when") or {}).get("expression"), f"{base}/exceptions/{x}/when/expression"):
            yield path, atom, (atom.get("evidenceIds"), ids, item.get("evidenceIds"))
        for path, atom in _atoms(exception.get("effectExpression"), f"{base}/exceptions/{x}/effectExpression"):
            yield path, atom, (atom.get("evidenceIds"), ids, item.get("evidenceIds"))
