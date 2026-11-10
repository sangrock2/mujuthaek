"""정책 공고 AI 읽기(rules/policy/reading.py) → 창업지원·사업공간 판정 틀. 코드만 씁니다.

AI는 중간 형식으로 답하고 이 모듈이 틀의 칸으로 옮깁니다. 확신이 없으면 그 조건은 inReview입니다.
- 근거 문장(quote)이 원문 글에 그대로 없으면 확인 필요
- 나이·연수·날짜·금액·업종 코드·지역 이름이 근거 문장에 없으면 확인 필요(AI가 값을 바꿨을 수 있음). 금액은 단위까지 맞아야 함
- 근거 문장이 범위(「19~39세」)인데 최소·최대 중 하나만 뽑았으면 확인 필요
- 업력 날짜 범위는 공고가 찍은 날짜가 있으면 그대로, 연수만 있으면 기준일에서 틀 문서 규칙대로 계산(기준일이 없으면 질문)
- 틀에 칸이 없는 조건(사업공간 틀의 업력 상한·매출 등)은 근거 문장을 묻는 질문(ASK)
- 최소가 최대보다 큰 나이·매출, 시작일이 끝일보다 뒤인 개업일·폐업일은 근거 문장을 묻는 질문(확인 필요). 틀 읽기가 틀 전체를 거절함
- 근거 문장이나 바로 뒤 주석 줄에 예외 단서(「다만」「단,」「…의 경우 신청 가능」「예외」)가 있으면 확인 필요(틀에 예외 칸이 없음).
  질문(ASK)이면 질문 끝에 그 예외 문장을 붙임
- K-Startup 목록 정보(대상 연령·창업 기간·신청 대상 칸)에만 있고 본문에 없는 근거로 만든 조건은 확인 필요.
  본문 나이와 목록 정보 「대상 연령」이 다르면 확인 필요
- 「N년차 이하」는 「N년 이내」와 경계가 달라(만 N년째를 넣는지) 업력 값을 확정하지 않음
- 대상군 배치 검사(조립 뒤): 예비창업자(사업자 아님) 길이 있는데 공통 조건이 이미 사업 중인 기업을 전제하면(업력·사업자·매출·
  본사·지점 같은 기업 형태) 그 공통 조건은 확인 필요. 예비창업자에게만 해당하는 제외 문장이 다른 신청자에게도 걸려 있거나,
  한 대상군의 제외 문장이 다른 대상군 이름을 말하면 확인 필요
- 길 이름·질문에 내부 코드(NO_RECENT_CLOSURE 같은)를 쓰지 않음. 틀에 없는 유형 코드는 한국어 이름으로 묻는 질문 하나로
- 답 방향: 제외 문장(근거에 제외·불가·결격 같은 낱말이 있거나 원문에서 「제외대상」 같은 제외 머리말 아래)으로 만든 질문이 「예」면
  충족이고 부정 질문(「…하지 않나요?」)이 아니면 확인 필요. 같은 근거 문장의 제외 조건과 방향이 엇갈려도 확인 필요. 뒤집지는 않음
- 질문이 둘로 이어져 있으면(물음표 둘) 첫 질문만 남기고 확인 필요. 예외 문장은 「이 예외로 신청할 수 있으면 '예/아니오'」로 한 방향만
- 같은 근거 문장의 조건이 여럿이면 예외 표시는 예외 문장이 말하는 조건(업력·체납 등)에만. 어느 것도 말하지 않으면 모두에
- 첨부·별도 공고문을 가리키는 근거(「공고문 4page 참조」「별첨」), 자격 자체를 되묻는 말(「입점자격을 충족하는」)·범위 없는 말(「각종」
  「기타 법령」), AI가 정의 없음(defined false)으로 읽은 분야·유형 질문은 확인 필요
- 같은 자리의 같은 질문(근거·질문·방향이 모두 같음)은 한 번만. 같은 근거 문장의 제외 유형(EXCLUDED_STATUS)은 하나로 합침
- 사업공간: 원문에 공고일·기준일이 없으면(AI가 적은 날짜·찍힌 기준일을 확인하지 못한 경우는 빼고) 접수 시작일 → 판정일 순서로 기준일을
  대신 정하고(판정일이 접수 마감 뒤면 마감일), 어느 날짜를 썼는지 안내(OTHER)로 남김. 나이·업력·폐업 기간처럼 기준일에 기대는 조건은
  모두 확인 필요(사용자 결정 2026-10-23, 선택 B)
- 「신청일 기준」「신청일 현재」: 신청하는 날이 사람마다 달라 같은 대체 순서(공고일 → 접수 시작일 → 판정일)의 날짜를 쓰고, 기준일에 기대는
  조건은 확인 필요(사유 「신청일 기준」)
- 대상군이 둘 이상인데 조건이 하나도 없는 대상군(누구나 통과하는 길)은 「〈대상군〉에 해당하나요?」 확인 필요 질문으로 채움. 대상군이
  하나면 원문이 그 대상을 분명히 말할 때만
- 온통청년 나이 제한 여부가 「제한 없음」인데 최소·최대 나이 값이 있으면 버리지 않고 확인 필요 나이로(값이 엇갈림)
- 신청자 지역 근거가 지명 없이 「관내」「관할」이면 기관이 시군구이고 그 시군구가 하나로 정해질 때만 그 시군구로 확정
- 「참여 제한 대상: 붙임파일 참조」처럼 제외·자격 칸이 첨부만 가리키면 확인 필요 질문 하나. 같은 근거의 휴업 제외 유형과 폐업 질문은
  하나로. 기창업 대상군에 사업자 조건이 없고 원문이 사업자 등록을 요구하면(제출 서류로만 짐작하면 확인 필요) 사업자 조건을 더함
- 신청자 지역(REGION)의 근거 문장이 앞으로 둘·옮길 곳(「두고자」「이전 가능」「입주 후」「전입 예정」)이면 지역 요건으로 확정하지
  않음: 택1 길이 아니면 입주 뒤 의무 안내(OBLIGATION)로 옮기고, 택1 길 안이거나 「전입」「이전」만 있으면 확인 필요
- 대상군이 둘 이상이고 한 대상군에 걸린 제외 조건이 대상군을 지목하지 않는 제외 단락의 문장이면 공통으로 옮김(업력·연수 제외는
  그 대상군에 남김, 택1 길 안이면 옮기지 않고 확인 필요)
- 범위 정의는 규칙으로: 법령 조항으로만 정한 범위, 자격 쪽 「… 등」 열린 목록, 「우수한」「유망한」 같은 심사 판단 말은 확인 필요.
  제외 쪽은 예시 목록(「유흥업 등」)이 있으면 확정(AI의 defined false도 제외 쪽 예시 목록이 있으면 따르지 않음)
- 질문이 「모집분야」「제외 업종」처럼 다른 곳을 가리키면 근거 문장의 목록을 질문에 붙임. 대상군을 지목하지 않는 우대는 공통
- 목록 정보에만 있는 나이: AI가 목록 칸으로 만든 나이는 버리고, 본문 나이가 없으면 목록 정보 구간(K-Startup 대상 연령,
  온통청년 지원 대상 최소·최대 연령)으로 확인 필요 나이 하나를 공통에 둠(공고마다 다르게 나오던 것을 하나로)
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from mujuthaek_extraction.assemble.regions import SIDO_NAMES, SIGUNGU_SUFFIX
from mujuthaek_extraction.judgment.sanity import INVERTED, repair
from mujuthaek_extraction.judgment.startup import AGE_BANDS

STARTUP_STATUS = {"SME", "WOMAN", "SMALL_BUSINESS", "VENTURE_COMPANY", "SOCIAL_VENTURE", "DISABLED", "ONE_PERSON_CREATIVE", "STUDENT"}
STARTUP_EXCLUDED = {"CREDIT_DELINQUENT", "TAX_ARREARS", "CLAWBACK_UNPAID", "PROGRAM_SANCTION", "BUSINESS_SUSPENDED", "WAGE_ARREARS", "SUBSIDY_EXCLUDED"}
SPACE_STATUS = {
    "SMALL_BUSINESS",
    "CAREER_BREAK_WOMAN",
    "SOCIAL_ENTERPRISE",
    "PRE_SOCIAL_ENTERPRISE",
    "SOCIAL_COOPERATIVE",
    "VILLAGE_ENTERPRISE",
    "SELF_SUFFICIENCY_ENTERPRISE",
    "SOCIAL_VENTURE",
    "NATIONAL_MERIT",
}
SPACE_EXCLUDED = {"TAX_ARREARS", "CREDIT_DELINQUENT", "BUSINESS_SUSPENDED"}
EXCLUDING_KINDS = {"EXCLUDED_STATUS", "NO_RECENT_CLOSURE", "INDUSTRY_EXCLUDE"}

QUOTE_MISSING = "근거 문장을 공고 글에서 찾지 못했습니다"
VALUE_MISSING = "값이 근거 문장에 없습니다(AI가 값을 바꿨을 수 있음)"
TRUNCATED = "공고 글이 길어 앞부분만 읽었습니다"
NO_REFERENCE = "기준일을 정하지 못해 연수를 개업일 범위로 바꿀 수 없습니다"
NO_REGION = "지역 이름을 법정동 코드로 바꾸지 못했습니다"
RANGE_PART = "근거 문장이 범위이거나 구간이 여럿인데 한쪽 경계만 읽었습니다"
EXCEPTION = "근거 문장이나 바로 뒤 문장에 예외 단서(다만·단·…의 경우 신청 가능)가 있습니다"
META_ONLY = "본문에 없고 목록 정보(대상 연령·창업 기간·신청 대상 칸)에만 있습니다"
META_CONFLICT = "본문 나이와 목록 정보(대상 연령 칸)의 나이가 다릅니다"
YEAR_COUNT = "「N년차」는 「N년 이내」와 경계가 달라(만 N년째를 넣는지) 원문 확인이 필요합니다"
PLACEMENT = "예비창업자(사업자 아님) 대상이 있는데 이 공통 조건은 이미 사업 중인 기업을 전제합니다(대상군 배치 확인 필요)"
SCOPE = "예비창업자에게만 해당할 수 있는 문장인데 다른 신청자에게도 걸려 있습니다(대상군 배치 확인 필요)"
OTHER_GROUP = "근거 문장이 다른 대상군도 말합니다(대상군 범위 확인 필요)"
DIRECTION = "제외 문장으로 만든 질문인데 「예」가 충족으로 되어 있습니다(답 방향 확인 필요)"
DIRECTION_CONFLICT = "같은 근거 문장으로 만든 제외 조건과 답 방향이 반대입니다(답 방향 확인 필요)"
MERGED_QUESTION = "질문 두 개가 하나로 합쳐져 있어 첫 질문만 남겼습니다"
ATTACHED = "근거가 첨부·별도 공고문을 가리켜 본문만으로는 범위를 알 수 없습니다"
UNDEFINED = "질문이 기대는 분야·유형·자격의 범위가 본문에 정의되어 있지 않습니다"
COMMON_EXCLUSION = "대상군을 지목하지 않은 제외 단락의 문장인데 한 대상군에만 걸려 있습니다(대상군 배치 확인 필요)"
# 기준일을 대신 정한 틀: 조건 사유는 「〈왜〉 〈쓴 날짜〉을 기준일로 썼습니다. 이 조건은 기준일에 따라 달라집니다」, 안내는 머리말로 시작
NO_REFERENCE_DATE = "이 조건은 기준일에 따라 달라집니다"
JUDGING_DATE_NOTE = "기준일 안내:"
APPLICATION_DAY = "신청일 기준"
EMPTY_GROUP = "이 대상군의 자격 조건을 본문에서 읽지 못해 누구나 통과하는 길이 됩니다(대상군 범위 확인 필요)"
AGE_FLAG_CONFLICT = "목록 정보의 나이 제한 표시(제한 없음)와 나이 값이 엇갈립니다"
JURISDICTION_UNKNOWN = "「관내」가 어디인지 정하지 못했습니다"
REGISTRATION_FROM_DOCUMENTS = "제출 서류(사업자등록증)로 사업자 등록이 필요하다고 짐작했습니다"
INTENT_REGION = "입주 뒤 의무일 수 있음: 근거 문장이 지금 있는 곳이 아니라 앞으로 둘·옮길 곳을 말합니다"
LAW_SCOPE = "범위가 법령 조항으로만 정해져 있어 본문만으로는 답할 수 없습니다"
OPEN_LIST = "자격 쪽 목록이 「… 등」으로 열려 있어 목록에 없는 분야가 해당하는지 알 수 없습니다"
INCOME_RULE = "소득·자산 기준이 있다고만 적혀 있어 금액을 알 수 없습니다(안내 문장에서 조건으로 옮김)"
EVALUATIVE = "「우수한」「유망한」처럼 심사에서 판단할 말이라 신청자가 스스로 답할 수 없습니다"

# 질문·길 이름에 쓰는 한국어 이름(내부 코드를 그대로 보여 주지 않음)
STATUS_NAMES = {
    "SME": "중소기업",
    "WOMAN": "여성(여성 대표·여성기업)",
    "SMALL_BUSINESS": "소상공인",
    "VENTURE_COMPANY": "벤처기업",
    "SOCIAL_VENTURE": "소셜벤처",
    "DISABLED": "장애인(장애인 대표·장애인기업)",
    "ONE_PERSON_CREATIVE": "1인 창조기업",
    "STUDENT": "대학생·대학원생",
    "SOCIAL_ENTERPRISE": "사회적기업",
    "PRE_SOCIAL_ENTERPRISE": "예비사회적기업",
    "SOCIAL_COOPERATIVE": "사회적협동조합",
    "VILLAGE_ENTERPRISE": "마을기업",
    "SELF_SUFFICIENCY_ENTERPRISE": "자활기업",
    "CAREER_BREAK_WOMAN": "경력단절여성",
    "NATIONAL_MERIT": "국가유공자",
}
EXCLUDED_NAMES = {
    "CREDIT_DELINQUENT": "채무불이행",
    "TAX_ARREARS": "국세·지방세 체납",
    "CLAWBACK_UNPAID": "환수금 미반환",
    "PROGRAM_SANCTION": "정부·창업지원사업 참여제한 제재",
    "BUSINESS_SUSPENDED": "휴업",
    "WAGE_ARREARS": "임금 체불 명단",
    "SUBSIDY_EXCLUDED": "보조사업 수행 배제",
}
KIND_NAMES = {
    "AGE": "나이",
    "REGION": "지역",
    "PRE_FOUNDER": "예비창업자",
    "REGISTERED": "사업자",
    "BUSINESS_AGE": "업력",
    "NO_RECENT_CLOSURE": "최근 폐업 이력 없음",
    "CLOSURE_REQUIRED": "폐업 경험",
    "REVENUE": "매출",
    "INDUSTRY_EXCLUDE": "제외 업종 아님",
    "INDUSTRY_ONLY": "대상 업종",
    "STATUS": "유형",
    "EXCLUDED_STATUS": "제외 대상 아님",
    "OTHER": "기타 조건",
}
# 사업 중인 기업이어야 갖출 수 있는 유형(사람에게 붙는 여성·장애인·대학생·경력단절여성·국가유공자는 빼고)
BUSINESS_STATUS = set(STATUS_NAMES) - {"WOMAN", "DISABLED", "STUDENT", "CAREER_BREAK_WOMAN", "NATIONAL_MERIT"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _quoted(quote: str | None, text: str) -> bool:
    return bool(quote) and len(_norm(quote)) >= 4 and _norm(quote) in _norm(text)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", (text or "").replace(",", "")))


def _has_number(quote: str, value: float | int | None) -> bool:
    if value is None:
        return True
    number = int(value) if float(value).is_integer() else value
    return str(number) in _numbers(quote) or str(value) in (quote or "")


def _has_date(quote: str, value: str | None) -> bool:
    """「2023년 1월 23일」「'23.1.23.」「2023-01-23」 어느 꼴이든 연·월·일 숫자가 근거 문장에 있는지."""
    if not value:
        return True
    try:
        day = date.fromisoformat(value)
    except ValueError:
        return False
    numbers = {n.lstrip("0") or "0" for n in _numbers(quote)}
    year_ok = str(day.year) in numbers or str(day.year % 100) in numbers
    return year_ok and str(day.month) in numbers and str(day.day) in numbers


# 금액 한 덩어리: 숫자(쉼표 자리 구분·소수 허용) + 단위. 단위까지 맞아야 금액으로 셉니다
# (리뷰 2026-10-22: 「1억원」에서 「1」만 보고 1만 원(10000)을 확정했음)
_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(억|천|백|십|만)?\s*(원)?")
_WON_UNITS = {"억": 100000000, "만": 10000, None: 1}


def _amounts(quote: str) -> tuple[list[int], int]:
    """근거 문장의 금액 → (깔끔하게 읽은 원 단위 값들, 읽지 못한 금액 수).
    「1억원」「5,000만 원」「100,000,000원」만 깔끔한 금액이고, 「1억 5천만원」처럼 섞인 표기나 「5천만원」은 읽지 못한 금액입니다."""
    text = unicodedata.normalize("NFKC", quote or "")
    found = list(_AMOUNT.finditer(text))
    clean: list[int] = []
    unclean = 0
    for n, match in enumerate(found):
        number, fraction, unit, won = match.group(1), match.group(2) or "", match.group(3), match.group(4)
        if unit is None and won is None:
            continue  # 「2025년」「3년」 같은 금액 아닌 숫자
        mixed = (unit == "억" and n + 1 < len(found) and found[n + 1].start() == match.end()) or (
            n > 0 and found[n - 1].group(3) == "억" and found[n - 1].end() == match.start()
        )  # 「1억 5000만원」: 억 뒤에 바로 숫자가 이어짐
        if mixed or unit not in _WON_UNITS or (unit is None and fraction):
            unclean += 1
            continue
        value = Decimal(number.replace(",", "") + fraction) * _WON_UNITS[unit]
        if value != value.to_integral_value():
            unclean += 1
            continue
        clean.append(int(value))
    return clean, unclean


def _has_won(quote: str, won: int | None) -> bool:
    """금액이 단위와 함께(「N원」「N만 원」「N억 원」) 근거 문장에 있는지. 섞인 표기(「1억 5천만원」)는 맞다고 보지 않습니다."""
    if won is None:
        return True
    return won in _amounts(quote)[0]


# 한쪽 경계만 뽑았는지 볼 때 쓰는 범위 표현(리뷰 2026-10-22: 「만 19~39세」를 maxAge 39만 뽑아도 확정됐음)
_AGE_DASH = re.compile(r"\d\s*(?:세|살)?\s*[~∼\-–]\s*(?:만\s*)?\d+\s*(?:세|살)")
_WON_DASH = re.compile(r"\d\s*(?:억|천|백|십|만)?\s*(?:원)?\s*[~∼\-–]\s*\d[\d,.]*\s*(?:억|천|백|십|만|원)")
_RANGE_PAIRS = (
    (re.compile(r"이상|초과|부터"), re.compile(r"이하|미만|이내|까지")),
    (re.compile(r"에서"), re.compile(r"까지")),
)


def _half_range(quote: str, low: Any, high: Any, dash: re.Pattern[str], others: bool) -> bool:
    """최소·최대 중 하나만 뽑았는데 근거 문장이 범위(「19~39세」「이상…이하」「부터…까지」)이거나 쓰지 않은 같은 종류 숫자(others)가 있으면 True."""
    if (low is None) == (high is None):
        return False
    text = unicodedata.normalize("NFKC", quote or "")
    return bool(dash.search(text)) or any(a.search(text) and b.search(text) for a, b in _RANGE_PAIRS) or others


def _age_half_range(quote: str, min_age: int | None, max_age: int | None) -> bool:
    used = {v for a in (min_age, max_age) if a is not None for v in (a - 1, a, a + 1)}  # 초과·미만이면 숫자가 하나 다름
    ages = {int(n) for n in re.findall(r"(\d+)\s*(?:세|살)", unicodedata.normalize("NFKC", quote or ""))}
    return _half_range(quote, min_age, max_age, _AGE_DASH, bool(ages - used))


def _won_half_range(quote: str, min_won: int | None, max_won: int | None) -> bool:
    clean, unclean = _amounts(quote)
    return _half_range(quote, min_won, max_won, _WON_DASH, bool(unclean) or any(v not in (min_won, max_won) for v in clean))


# 값의 방향(리뷰 2026-10-22: 「만 40세 이상」을 maxAge 39로, 「3년 이상」을 「3년 이내」로 뽑아도 숫자만 맞아 확정됐음)
UPPER = re.compile(r"이하|미만|이내|까지|지나지\s*않|되지\s*않|안\s*된|[~∼]")
LOWER = re.compile(r"이상|초과|부터|넘|경과|[~∼]")
YEARS_WORDS = {
    "WITHIN": re.compile(r"이내|이하|까지"),
    "UNDER": re.compile(r"미만|지나지\s*않|되지\s*않|안\s*된"),
    "AT_LEAST": re.compile(r"이상|경과|지난"),
    "OVER": re.compile(r"초과|넘"),
}
NO_DIRECTION = "질문 방향(예·아니오 중 어느 답이 충족인지)을 정하지 못했습니다"


# 시도 정식 이름 ↔ 약칭 대응은 지역표(regions.SIDO_NAMES)의 것을 씁니다. 앞 두 글자 비교는 「충청남도」↔「충남」을 놓쳐 공간 위치를 잃었음
# (리뷰 2026-10-23). 「광주」는 경기도 광주시와 구별할 수 없어 광주광역시의 약칭으로 쓰지 않습니다(지역표와 같은 이유).


def _place_named(token: str, plain: str) -> bool:
    """시군구 이하 이름 하나가 근거 문장에 있는지: 이름 전체(「남구」≠「북구」), 시·군은 끝 글자를 뗀 이름도(「고양시」↔「고양」, 두 글자 이상)."""
    if token in plain:
        return True
    return token[-1] in "시군" and len(token) >= 3 and token[:-1] in plain


def region_named(name: str, quote: str) -> bool:
    """지역 이름이 근거 문장에 있는지: 시도는 정식 이름·약칭 어느 쪽이든(「충청남도」↔「충남」, 「서울특별시」↔「서울시」↔「서울」),
    시군구 이하는 이름 전체(시·군은 끝 글자를 뗀 이름도)."""
    tokens = [_norm(t) for t in str(name).split() if t.strip()]
    plain = _norm(quote)
    if not tokens:
        return False
    if tokens[0] in SIDO_NAMES:
        return any(same in plain for same in SIDO_NAMES[tokens[0]]) and all(_place_named(t, plain) for t in tokens[1:])
    return all(_place_named(t, plain) for t in tokens)


def _year_count(quote: str, years: Any) -> bool:
    """「7년차 이하」「7년 차」처럼 햇수를 차수로 적었는지. 「N년 이내」(만 N년째 포함)와 경계가 달라 확정하지 않습니다."""
    if not _sane_years(years):
        return False
    return bool(re.search(rf"(?<!\d){int(years)}\s*년\s*차", unicodedata.normalize("NFKC", quote or "")))


# 예외 단서: 근거 문장 안이나 바로 뒤 주석 줄(※·*·다만·단,)에 있으면 그 조건은 예외가 있음(리뷰 2026-10-23: 틀에 예외 칸이 없어
# 「체납자 제외(다만 분납 중이면 신청 가능)」가 예외 없이 확정됐음)
_EXCEPTION = re.compile(
    r"다만|(?:^|[\s(※*＊,·\-])단\s*[,:：]|예외|제외하지\s*않|경우(?:에는|에도|는|도)?[^\n]{0,40}?(?:신청|지원|입주|참여)\s*(?:이\s*|도\s*)?가능"
)
_ANNOTATION = re.compile(r"^(?:※|\*|＊|\(?\s*다만|\(?\s*단\s*[,:：]|\(?\s*예외)")
_BULLET = re.compile(r"^[\s\-·•⁃ㆍ∙◦▪○●□■◇◆>→]+")


def _clip(text: str, size: int = 120) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= size else text[: size - 1] + "…"


def _short(text: str, size: int) -> str:
    """보여 줄 글을 size 글자 안으로: 괄호 중간에서 끊지 않고, 목록이면 구분 기호에서 끊고 「…」를 붙입니다
    (리뷰 2026-10-23: 길 이름이 「…정보통신(IT」에서 잘렸음)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= size:
        return text
    cut = text[:size]
    if cut.count("(") > cut.count(")") and cut.rfind("(") >= 4:
        cut = cut[: cut.rfind("(")]
    at = max(cut.rfind(","), cut.rfind("·"), cut.rfind("ㆍ"), cut.rfind(" "))
    if at >= size // 2:
        cut = cut[:at]
    return cut.rstrip(" ,·ㆍ/(") + "…"


def _list_of(quote: str | None) -> str | None:
    """근거 문장 안의 나열(괄호 안 목록, 쌍점 뒤 목록, 문장 자체가 목록) 하나. 없으면 None."""
    text = _BULLET.sub("", unicodedata.normalize("NFKC", quote or "")).strip()
    for found in re.finditer(r"\(([^()]{4,})\)", text):
        if _LIST_SEP.search(found.group(1)):
            return found.group(1).strip()
    parts = re.split(r"[:：]", text, maxsplit=1)
    if len(parts) == 2 and _LIST_SEP.search(parts[1]):
        return parts[1].strip()
    return text if len(_LIST_SEP.findall(text)) >= 2 else None


def _continued(quote: str | None, text: str) -> str:
    """근거 문장 + 원문에서 근거 문장이 줄 끝에서 끝나고 바로 다음 줄이 괄호로 시작하면 그 줄(「… 제외 업종」 다음 줄
    「(숙박 및 음식점업, 금융 및 보험업 등)」). 목록이 다음 줄로 넘어간 경우만 봅니다."""
    target = _norm(quote or "")
    if len(target) < 4:
        return quote or ""
    lines = (text or "").splitlines()
    for n, line in enumerate(lines[:-1]):
        flat = _norm(unicodedata.normalize("NFKC", line))
        if flat.endswith(target) and lines[n + 1].strip().startswith(("(", "（")):
            return f"{quote} {lines[n + 1].strip()}"
    return quote or ""


def with_list(question: str, quote: str | None) -> str:
    """「모집분야에 해당하나요?」처럼 다른 곳을 가리키는 질문이면 근거 문장의 목록을 질문 뒤에 붙입니다(질문만 읽고 답할 수 있게).
    목록의 첫 항목이 이미 질문에 있으면 그대로."""
    if not _REFERS.search(question or ""):
        return question
    items = _list_of(quote)
    if not items:
        return question
    first = _norm(_LIST_SEP.split(items)[0])
    if not first or first in _norm(question):
        return question
    return f"{question.rstrip()} (원문 목록: {_short(items, 70)})"


def exception_clause(quote: str | None, text: str) -> str | None:
    """근거 문장의 예외 단서: 근거 문장 안, 같은 줄의 근거 뒤, 바로 다음 주석 줄 순서로 찾아 그 문장을 돌려줍니다. 없으면 None."""
    if not quote:
        return None
    plain = unicodedata.normalize("NFKC", quote)
    if found := _EXCEPTION.search(plain):
        return _clip(plain[max(0, found.start() - 30) :] if found.start() > 30 else plain)
    target = _norm(quote)
    if len(target) < 4:
        return None
    lines = [unicodedata.normalize("NFKC", line) for line in (text or "").splitlines()]
    for n, line in enumerate(lines):
        flat = _norm(line)
        at = flat.find(target)
        if at < 0:
            continue
        rest = flat[at + len(target) :]
        if re.search(r"다만|예외|제외하지않|^\(?단[,:：]", rest):
            return _clip(line)
        following = next((other.strip() for other in lines[n + 1 :] if other.strip()), "")
        bare = _BULLET.sub("", following)
        if following and (_ANNOTATION.match(following) or _ANNOTATION.match(bare)) and _EXCEPTION.search(following):
            return _clip(bare or following)
    return None


# 예외 단서가 무엇을 풀어 주는지: 같은 근거 문장으로 조건을 여러 개 만들었을 때 예외 표시는 그 예외가 말하는 조건에만 붙입니다
# (리뷰 2026-10-23: 「창업 7년 미만 기업(단, 업력 3년 초과는 문의)」의 예외가 같은 문장의 사업자 조건에도 번졌음).
# 예외가 어느 조건도 말하지 않으면 모두에 붙입니다(안전 쪽)
_EXCEPTION_TOPICS = {
    "AGE": re.compile(r"세|나이|연령"),
    "REGION": re.compile(r"거주|주소|주민\s*등록|소재|지역"),
    "PRE_FOUNDER": re.compile(r"예비|사업자\s*등록|미등록"),
    "REGISTERED": re.compile(r"사업자\s*등록|개업|법인\s*설립|개인\s*사업자|법인\s*사업자"),
    "BUSINESS_AGE": re.compile(r"업력|\d+\s*년|개업일|설립일|창업\s*후"),
    "NO_RECENT_CLOSURE": re.compile(r"폐업|재창업"),
    "CLOSURE_REQUIRED": re.compile(r"폐업|재창업"),
    "REVENUE": re.compile(r"매출"),
    "INDUSTRY_EXCLUDE": re.compile(r"업종|업태"),
    "INDUSTRY_ONLY": re.compile(r"업종|업태"),
    "EXCLUDED_STATUS": re.compile(r"체납|세금|납부|채무|신용|회생|파산|워크아웃|휴업|폐업|제재|참여\s*제한|환수|체불|배제"),
}


def _exception_topic(item: dict[str, Any], clause: str) -> bool:
    """예외 문장(예외 단서부터 뒤, 근거 문장 앞부분은 빼고)이 이 조건의 대상을 말하는지."""
    found = _EXCEPTION_TOPICS.get(item["kind"])
    marker = _EXCEPTION.search(clause)
    return bool(found and found.search(clause[marker.start() :] if marker else clause))


# 제외 문장: 근거 문장 안의 제외 낱말, 또는 원문에서 그 문장이 「제외대상」「신청 제외 대상:」 같은 제외 머리말 아래에 있음
# (리뷰 2026-10-23: 「신청일 현재 휴업 또는 폐업인 창업기업」(제외대상 단락)이 「폐업 상태인가요?」 + 「예」면 충족으로 확정됐음)
_EXCLUDE_WORDS = re.compile(
    r"제외(?!\s*하지\s*않)|불가|결격|부적격|금지|(?:신청|지원|입주|참여|선정)\s*(?:을|이)?\s*(?:할\s*수\s*)?없|"
    r"(?:신청|지원|입주|참여)\s*(?:이\s*)?제한(?!\s*(?:이\s*)?없)"
)
_HEAD_MARKS = re.compile(r"^[\s\d.)\]】□■○●◦•▶▷◆◇\-*※\[(【<>ㆍ·‧]*(?:[가-하][.)]\s*)?")
_HEAD_NOUN = re.compile(r"(?:대상|자격|요건|조건|사유|사항|내용|기준|업종)$")
_HEAD_EXCLUDE = re.compile(r"제외|제한|불가|결격")
_HEAD_BARE = re.compile(r"(?:신청|지원|모집|입주|참여|응모|선정)?(?:제외|제한|불가)")  # 「모집 제외」처럼 명사 없이 끝나는 제외 머리말
_LOOK_BACK = 15  # 머리말을 찾는 줄 수


def _heading(text: str) -> str | None:
    """머리말이면 "EXCLUDE"(제외 머리말)·"OTHER"(신청 대상 같은 다른 머리말), 아니면 None. 「신청 제외 대상: …」처럼 쌍점 앞 머리말도 봅니다."""
    body = _HEAD_MARKS.sub("", unicodedata.normalize("NFKC", text)).strip()
    head = _norm(re.split(r"[:：]", body, maxsplit=1)[0])
    if _HEAD_BARE.fullmatch(head):
        return "EXCLUDE"
    if not head or len(head) > 14 or not _HEAD_NOUN.search(head):
        return None
    return "EXCLUDE" if _HEAD_EXCLUDE.search(head) else "OTHER"


def exclusion_heading(quote: str | None, text: str) -> str | None:
    """근거 문장이 원문에서 제외 머리말 아래에 있으면 그 머리말(가장 가까운 머리말이 제외 머리말일 때만). 여러 곳에 있으면 한 곳이라도."""
    target = _norm(quote or "")
    if len(target) < 4:
        return None
    lines = (text or "").splitlines()
    for n, line in enumerate(lines):
        flat = _norm(unicodedata.normalize("NFKC", line))
        at = flat.find(target)
        if at < 0:
            continue
        # 같은 줄 근거 앞(「신청 제외 대상: ‧ …」)부터, 그다음 위 줄들
        before = [flat[:at], *(_norm(unicodedata.normalize("NFKC", lines[k])) for k in range(n - 1, max(-1, n - 1 - _LOOK_BACK), -1))]
        for candidate in before:
            kind = _heading(candidate) if candidate else None
            if kind == "EXCLUDE":
                return re.split(r"[:：]", _HEAD_MARKS.sub("", candidate), maxsplit=1)[0]
            if kind == "OTHER":
                break
    return None


def excluding_quote(quote: str | None, text: str) -> bool:
    """제외 문장인지: 근거 문장에 제외 낱말이 있거나 제외 머리말 아래에 있음."""
    return bool(_EXCLUDE_WORDS.search(unicodedata.normalize("NFKC", quote or ""))) or exclusion_heading(quote, text) is not None


# 「…하지 않나요?」「…이 없나요?」「…이 아닌가요?」처럼 부정으로 묻는 질문은 「예」가 충족이어도 방향이 맞습니다
_NEGATED = re.compile(r"(?:않|아니|아닌|없)[가-힣\s]{0,8}[?？]?\s*$")


def _negated(question: str | None) -> bool:
    return bool(_NEGATED.search(unicodedata.normalize("NFKC", question or "").strip()))


# 첨부·별도 공고문을 가리키는 근거, 자격 자체를 되묻거나 범위가 정해지지 않은 말(리뷰 2026-10-23: 「신산업 창업 분야(공고문 4page 참조)」
# 「입점자격을 충족하는 기업」「각종 법적 제재」가 확정됐음 — 사용자가 본문만으로 답할 수 없음)
_ATTACHED = re.compile(
    r"(?:공고문|붙임|첨부|별첨|별지|별표)\s*(?:\d+\s*)?(?:page|p\.?|쪽|페이지)?\s*(?:참조|참고|확인)|"
    r"\d+\s*(?:page|p\.?|쪽|페이지)\s*(?:참조|참고)|첨부\s*(?:파일|문서|공고)|별첨|붙임\s*\d"
)
_VAGUE = re.compile(r"(?:자격|요건|기준)\s*(?:을|에)?\s*(?:충족|부합|해당)|각종|기타\s*(?:관계\s*)?법령")
_MEMBERSHIP_KINDS = {"OTHER", "STATUS", "INDUSTRY_ONLY", "INDUSTRY_EXCLUDE"}

# 범위 정의를 AI 표시(defined)만이 아니라 규칙으로(리뷰 2026-10-23: 같은 공해 업종 질문이 공고마다 확정·확인 필요로 갈렸고,
# 법령 참조·「… 등」 열린 목록 질문은 확정됐음)
# 법령 조항으로 정한 범위: 「…법에 따른」「…법 시행령에 명기된」「시행령 제4조의」
_LAW = re.compile(
    r"(?:법|법률|시행령|시행규칙|고시)\s*[」』]?\s*(?:제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?\s*(?:의|에)?|에\s*(?:따른|따라|의한|명기된|규정된|정한|해당)|"
    r"에서\s*(?:정한|정하는|규정한|규정하는))"
)
# 예시 목록: 구분 기호로 나열하거나 「… 등」으로 예를 듦(「등록」「등급」은 아님)
_LIST_SEP = re.compile(r"[,，·ㆍ、/]")
_EXAMPLES = re.compile(r"[,，·ㆍ、/]|[가-힣A-Za-z)]\s*등(?:의|을|를|과|이|에)?(?![가-힣])")
# 열린 목록: 구분 기호로 나열하고 「등」으로 끝남(「AI, 전기전자, 콘텐츠 등」)
_OPEN_LIST = re.compile(r"[,，·ㆍ、/][^,，·ㆍ、/\n]{1,30}?\s*등(?:의|을|를|과|이|에)?(?![가-힣])")
# 심사에서 판단할 말
_EVALUATIVE = re.compile(
    r"우수(?:한|하)|유망(?:한|하)|역량\s*(?:이\s*)?(?:있|갖춘|을\s*갖춘)|경쟁력\s*(?:이\s*)?(?:있|갖춘|을\s*갖춘)|혁신적|(?<!부)적합(?:한|하다)|탁월|뛰어난|"
    r"가능성\s*(?:이\s*)?(?:높|있|큰)"
)
# 질문이 다른 곳(목록)을 가리킴
_REFERS = re.compile(r"(?:모집|지원|대상|해당|제외|입주)\s*(?:분야|업종|업태)|아래|다음\s*(?:분야|업종|항목)|위\s*(?:의\s*)?(?:분야|업종)")


def _quote_lines(quote: str | None, text: str) -> str:
    """근거 문장이 들어 있는 원문 줄들(근거 밖 같은 줄의 「(공고문 4page 참조)」까지 보려고)."""
    target = _norm(quote or "")
    if len(target) < 4:
        return ""
    return "\n".join(line for line in (text or "").splitlines() if target in _norm(line))


# K-Startup 목록 정보: API 항목 줄(「대상 연령: …」)과 원문 화면 머리 칸(「대상연령」 다음 줄). 신청 대상 내용(aply_trgt_ctnt)은 본문입니다
META_FIELDS = ("biz_trgt_age", "biz_enyy", "aply_trgt")
YOUTH_AGE_FIELDS = ("sprtTrgtMinAge", "sprtTrgtMaxAge")  # 온통청년 목록 정보(지원 대상 최소·최대 연령, 제한 여부 sprtTrgtAgeLmtYn)
_META_LINE = re.compile(r"^\s*(대상\s*연령|창업\s*기간|신청\s*대상|지원\s*대상\s*최소\s*연령|지원\s*대상\s*최대\s*연령)\s*[:：]\s*(.+)$")
_META_LABEL = re.compile(r"^\s*(?:대상\s*연령|창업\s*기간|신청\s*대상|대상)\s*[:：]?\s*")
_META_HEADS = {"대상연령", "창업기간", "대상"}


class Meta:
    """정책 글의 K-Startup 목록 정보와 그것을 뺀 본문. 목록 칸이 없는 출처(기업마당 등)면 비어 있습니다."""

    def __init__(self, text: str, record: dict[str, Any] | None):
        record = record or {}
        self.values: list[str] = [str(record[f]) for f in META_FIELDS if isinstance(record.get(f), str) and record[f].strip()]
        self.ages: list[str] = [str(record["biz_trgt_age"])] if isinstance(record.get("biz_trgt_age"), str) else []
        self.youth: tuple[int | None, int | None] | None = None
        self.age_lines: list[str] = []  # 목록 정보 나이 줄(원문 그대로)
        self.lines: list[str] = []  # 본문에서 뺀 목록 정보 줄
        self.youth_unflagged: tuple[int | None, int | None] | None = None  # 제한 여부가 「제한 없음」인데 남은 나이 값
        if any(f in record for f in YOUTH_AGE_FIELDS):
            self.values += [str(record[f]) for f in YOUTH_AGE_FIELDS if str(record.get(f) or "").strip()]
            self.youth = _youth_ages(record)
            if str(record.get("sprtTrgtAgeLmtYn") or "").strip().upper() != "Y":
                self.youth_unflagged = _youth_ages(record, flagged=False)
        if not self.values:
            self.body = text or ""
            return
        body: list[str] = []
        head = None
        for line in (text or "").splitlines():
            if head is not None:
                self.lines.append(line)
                self.values.append(line)
                if head == "대상연령":
                    self.ages.append(line)
                    self.age_lines.append(line.strip())
                head = None
                continue
            if found := _META_LINE.match(line):
                self.lines.append(line)
                self.values.append(found.group(2))
                if "연령" in found.group(1):
                    self.age_lines.append(line.strip())
                if _norm(found.group(1)) == "대상연령":
                    self.ages.append(found.group(2))
                continue
            if _norm(line) in _META_HEADS:
                head = _norm(line)
                continue
            body.append(line)
        self.body = "\n".join(body)

    def only(self, quote: str | None) -> bool:
        """근거 문장이 목록 정보 값 안에만 있고 본문에는 없는지."""
        if not self.values or not quote:
            return False
        body = _norm(self.body)
        whole = _norm(unicodedata.normalize("NFKC", quote))
        if len(whole) >= 4 and whole not in body and any(whole in _norm(line) for line in self.lines):
            return True  # 목록 줄 통째(「지원 대상 최소 연령: 15」): 값이 짧은 숫자라 본문의 다른 숫자와 헷갈리지 않게
        target = _norm(_META_LABEL.sub("", unicodedata.normalize("NFKC", quote)))
        return len(target) >= 2 and any(target in _norm(v) for v in self.values) and target not in _norm(self.body)

    def age_range(self) -> tuple[int | None, int | None] | None:
        """목록 정보 「대상 연령」 구간을 합친 (최소, 최대). 칸이 없거나, 모르는 값이거나, 세 구간 모두(제한 없음)거나, 끊긴 구간이면 None.
        온통청년은 지원 대상 최소·최대 연령(제한 여부가 Y일 때만)."""
        if self.youth is not None:
            return self.youth
        ranges = set()
        for raw in self.ages:
            bands = [re.sub(r"\s+", " ", b).strip() for b in raw.split(",") if b.strip()]
            if not bands or any(b not in AGE_BANDS for b in bands):
                return None
            ranges.add(tuple(sorted(bands, key=lambda b: AGE_BANDS[b][0] or 0)))
        if len(ranges) != 1:
            return None
        bands = list(ranges.pop())
        if len(bands) == len(AGE_BANDS):
            return None
        spans = [AGE_BANDS[b] for b in bands]
        if any((low[1] or 0) + 1 != (high[0] or 0) for low, high in zip(spans, spans[1:], strict=False)):
            return None
        return spans[0][0], spans[-1][1]


def _youth_ages(record: dict[str, Any], *, flagged: bool = True) -> tuple[int | None, int | None] | None:
    """온통청년 지원 대상 최소·최대 연령: 제한 여부(sprtTrgtAgeLmtYn)가 Y이고 숫자일 때만(flagged False면 제한 여부를 보지 않음).
    0은 제한 없음, 최대 99세 이상도 위 끝 제한 없음으로 봅니다."""
    if flagged and str(record.get("sprtTrgtAgeLmtYn") or "").strip().upper() != "Y":
        return None
    ages = []
    for field in YOUTH_AGE_FIELDS:
        raw = str(record.get(field) or "").strip()
        if raw and not raw.isdigit():
            return None
        ages.append(int(raw) if raw and int(raw) > 0 else None)
    low, high = ages
    if not flagged and high is not None and high >= 99:
        high = None
    if (low is None and high is None) or (low is not None and high is not None and low > high):
        return None
    return low, high


def _valid_day(value: Any) -> bool:
    if value is None:
        return True
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def _after(start: Any, end: Any) -> bool:
    """시작일이 끝일보다 뒤인지(둘 다 형식이 맞는 날짜일 때만)."""
    return bool(start and end) and date.fromisoformat(str(start)) > date.fromisoformat(str(end))


def _years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 2월 29일이 없는 해
        return day.replace(year=day.year - years, day=28)


def opened_range(reference: date, years: int, rule: str) -> tuple[str | None, str | None]:
    """틀 문서 「업력 날짜 정하는 법」: N년 이내 = N년 전 같은 날~기준일, 미만 = 다음 날부터, 이상 = ~N년 전 같은 날, 초과 = ~전날."""
    back = _years_ago(reference, years)
    if rule == "WITHIN":
        return back.isoformat(), reference.isoformat()
    if rule == "UNDER":
        return (back + timedelta(days=1)).isoformat(), reference.isoformat()
    if rule == "AT_LEAST":
        return None, back.isoformat()
    return None, (back - timedelta(days=1)).isoformat()  # OVER


class _Builder:
    def __init__(self, reading: Any, text: str, regions: Any, *, startup: bool, record: dict[str, Any] | None = None, jurisdiction: str | None = None):
        self.answer, self.text, self.regions, self.startup = reading.answer, text, regions, startup
        self.truncated = reading.truncated
        self.meta = Meta(text, record)
        self.used: set[str] = set()
        self.keys = {g["key"] for g in self.answer["groups"]}
        self.jurisdiction = jurisdiction  # 기관 관할 시군구(10자리, agency_sigungu). 「관내」를 풀 때만
        self.date_reason: str | None = None  # 기준일을 대신 정했거나 「신청일 기준」이면 기준일에 기대는 조건에 붙일 사유

    def new_id(self, base: str) -> str:
        name, n = base, 1
        while name in self.used:
            n += 1
            name = f"{base}-{n}"
        self.used.add(name)
        return name

    def base(self, kind: str, quote: str | None) -> dict[str, Any]:
        made = {"id": self.new_id(kind.lower().replace("_", "-")), "kind": kind, "quote": quote, "page": None, "inReview": False, "reviewReason": None}
        return made | {"asOf": None} if self.startup else made

    @staticmethod
    def flag(criterion: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        reasons = list(dict.fromkeys(r for r in [*(criterion.get("reviewReason") or "").split("; "), *reasons] if r))
        return criterion | {"inReview": bool(reasons), "reviewReason": "; ".join(reasons) or None}

    def ask(self, item: dict[str, Any], quote: str, reasons: list[str]) -> dict[str, Any]:
        item = item | {"question": (item.get("question") or "").strip() or None}  # 공백뿐인 질문은 틀 읽기가 거절함
        if item["question"] and len(re.findall(r"[?？]", item["question"])) >= 2:
            # 「…체납 중인가요? 단, … 예외에 해당하면 신청할 수 있나요?」: 두 질문의 답 방향이 달라 한 답으로 읽을 수 없음(리뷰 2026-10-23).
            # 첫 질문만 남기고 예외는 아래 criterion()이 원문 예외 문장과 답 방향을 붙임
            item = item | {"question": re.split(r"(?<=[?？])", item["question"], maxsplit=1)[0].strip()}
            reasons = [*reasons, MERGED_QUESTION]
        if item.get("question") and not item.get("metWhen") and item["kind"] not in EXCLUDING_KINDS:
            reasons = [*reasons, NO_DIRECTION]  # AI가 쓴 질문의 답 방향을 모름(「신청 제외 대상에 해당하나요?」가 YES로 채워지면 뜻이 뒤집힘)
        met = item.get("metWhen") or ("NO" if item["kind"] in EXCLUDING_KINDS else "YES")
        question = item.get("question") or (f"다음 신청 제외 대상에 해당하나요? 「{quote}」" if met == "NO" else f"다음 조건에 해당하나요? 「{quote}」")
        return self.flag(self.base("ASK", quote) | {"question": question, "metWhen": met}, reasons)

    def reference(self) -> date | None:
        """판정 기준일: 「공고일 기준」이면 공고일, 찍힌 기준일이면 그 날, 문구가 없으면 None. 근거 문장에 그 날짜가 있어야 씁니다."""
        rule = self.answer["referenceRule"]
        found = self.answer["announcedOn"] if rule == "ANNOUNCEMENT" else self.answer["referenceDate"] if rule == "EXPLICIT" else None
        return self._checked_date(found)

    def announced(self) -> date | None:
        return self._checked_date(self.answer["announcedOn"])

    def _checked_date(self, found: dict[str, Any] | None) -> date | None:
        if not found or not found.get("date") or not _quoted(found.get("quote"), self.text) or not _has_date(found["quote"], found["date"]):
            return None
        try:
            return date.fromisoformat(found["date"])
        except ValueError:
            return None

    def region_codes(self, names: list[str]) -> list[str] | None:
        codes = []
        for name in names:
            match = self.regions.lookup(name) if self.regions is not None else None
            if match is None or match.code is None or match.note:
                return None
            codes.append(match.code)
        return list(dict.fromkeys(codes)) or None

    def criterion(self, item: dict[str, Any], reference: date | None, *, exception: bool = True) -> dict[str, Any]:
        """AI 조건 하나 → 틀 조건 하나. 근거가 목록 정보에만 있거나, 본문 나이가 목록 정보와 다르거나, 예외 단서가 있거나(exception이
        False면 같은 문장의 다른 조건이 그 예외를 가져감), 제외 문장인데 「예」가 충족이거나, 첨부·미정의 용어에 기대면 확인 필요."""
        made = self._criterion(item, reference)
        reasons = []
        if self.meta.only(item["quote"]):
            reasons.append(META_ONLY)
        elif made["kind"] == "AGE" and (ages := self.meta.age_range()) is not None and ages != (made["minAge"], made["maxAge"]):
            reasons.append(META_CONFLICT)
        if (
            made["kind"] == "ASK"
            and made["metWhen"] == "YES"
            and not _negated(made["question"])
            and (item["kind"] in EXCLUDING_KINDS or excluding_quote(item["quote"], self.text))
        ):
            reasons.append(DIRECTION)  # 뒤집지 않음: 질문이 정말 제외 상태를 묻는지 코드가 알 수 없음
        if item["kind"] in _MEMBERSHIP_KINDS and made["kind"] != "INDUSTRY":
            said = f"{item.get('question') or ''}\n{item['quote']}\n{_quote_lines(item['quote'], self.text)}"
            if _ATTACHED.search(unicodedata.normalize("NFKC", said)):
                reasons.append(ATTACHED)
            reasons += _scope_reasons(item, made, _continued(item["quote"], self.text))
        if self.date_reason and _date_dependent(item, made):
            reasons.append(self.date_reason)
        if made["kind"] == "ASK":
            made = made | {"question": with_list(made["question"], _continued(item["quote"], self.text))}
        if exception and (clause := exception_clause(item["quote"], self.text)) is not None:
            reasons.append(EXCEPTION)
            if made["kind"] == "ASK":
                # 답 방향을 한쪽으로: 예외로 신청할 수 있는 사람이 어느 답을 해야 하는지 질문의 충족 방향에 맞춰 적음(리뷰 2026-10-23)
                answer = "아니오" if made["metWhen"] == "NO" else "예"
                made = made | {"question": f"{made['question']} (공고의 예외: 「{clause}」 — 이 예외로 신청할 수 있으면 '{answer}')"}
        return self.flag(made, reasons) if reasons else made

    def _criterion(self, item: dict[str, Any], reference: date | None) -> dict[str, Any]:
        """AI 조건 하나 → 틀 조건 하나(못 담으면 질문)."""
        quote, kind = item["quote"], item["kind"]
        reasons = [] if _quoted(quote, self.text) else [QUOTE_MISSING]
        if self.truncated:
            reasons.append(TRUNCATED)
        if item["group"] is not None and item["group"] not in self.keys:
            reasons.append("대상군을 정하지 못했습니다")  # 없는 대상군을 가리킨 조건은 공통으로 두되 확인 필요
        if kind == "AGE" and (item["minAge"] is not None or item["maxAge"] is not None):
            if item["minAge"] is not None and item["maxAge"] is not None and item["minAge"] > item["maxAge"]:
                return self.ask(item, quote, reasons + [INVERTED])
            seen = _has_number(quote, item["minAge"]) and (_has_number(quote, item["maxAge"]) or _has_number(quote, (item["maxAge"] or 0) + 1))
            seen = seen and (item["minAge"] is None or bool(LOWER.search(quote))) and (item["maxAge"] is None or bool(UPPER.search(quote)))
            if seen and _age_half_range(quote, item["minAge"], item["maxAge"]):
                reasons = [*reasons, RANGE_PART]  # 값은 근거 문장에 있지만 범위·여러 구간 중 한쪽만 읽음(리뷰 2026-10-23: 사유가 「값이 없음」으로 나갔음)
            elif not seen:
                reasons = [*reasons, VALUE_MISSING]
            return self.flag(self.base("AGE", quote) | {"minAge": item["minAge"], "maxAge": item["maxAge"]}, reasons)
        if kind == "REGION" and moving_place(quote):
            reasons = [*reasons, INTENT_REGION]  # 앞으로 둘·옮길 곳은 지금의 지역 요건으로 확정하지 않음(리뷰 2026-10-23)
        if kind == "REGION" and _JURISDICTION.search(quote or "") and (made := self.jurisdiction_region(item, quote, reasons)) is not None:
            return made
        if kind == "REGION" and item["regionNames"] and item["regionBasis"]:
            codes = self.region_codes(item["regionNames"])
            if codes is None:
                return self.ask(item, quote, reasons + [NO_REGION])
            missing = [t for n in item["regionNames"] for t in str(n).split() if not region_named(t, quote)]
            if missing:  # 사유에 빠진 이름을 적음(「경기도」를 AI가 더했는지 원문에서 바로 볼 수 있게)
                reasons = [*reasons, f"{VALUE_MISSING}: 근거 문장에 「{', '.join(missing)}」이 없습니다"]
            return self.flag(self.base("REGION", quote) | {"basis": item["regionBasis"], "regionCodes": codes}, reasons)
        if kind in ("PRE_FOUNDER", "REGISTERED"):
            made = self.base("BUSINESS_REGISTRATION", quote) | {"require": "NOT_REGISTERED" if kind == "PRE_FOUNDER" else "REGISTERED"}
            return self.flag(made if self.startup else made | {"closedWithinYears": None}, reasons)
        if kind == "BUSINESS_AGE" and self.startup:
            return self.business_age(item, quote, reasons, reference)
        if kind == "BUSINESS_AGE" and _sane_years(item["years"]) and item["yearsRule"] and not item["question"]:
            # 사업공간 틀에는 업력 칸이 「N개월 이상」뿐이라 질문으로. 문장 전체 대신 업력만 묻습니다
            years = f"{item['years']:g}"
            question = {
                "WITHIN": f"사업을 시작한 날(법인은 설립등기일)부터 {years}년 이내인가요?",
                "UNDER": f"사업을 시작한 날(법인은 설립등기일)부터 {years}년이 지나지 않았나요?",
                "AT_LEAST": f"사업을 시작한 날(법인은 설립등기일)부터 {years}년 이상 지났나요?",
                "OVER": f"사업을 시작한 날(법인은 설립등기일)부터 {years}년이 넘게 지났나요?",
            }[item["yearsRule"]]
            seen = _has_number(quote, item["years"]) and bool(YEARS_WORDS[item["yearsRule"]].search(quote))
            reasons = reasons + ([] if seen else [VALUE_MISSING]) + ([YEAR_COUNT] if _year_count(quote, item["years"]) else [])
            return self.ask(item | {"question": question, "metWhen": "YES"}, quote, reasons)
        if kind in ("NO_RECENT_CLOSURE", "CLOSURE_REQUIRED") and self.startup:
            return self.closure(item, quote, reasons, reference)
        if kind == "CLOSURE_REQUIRED" and not self.startup and _sane_years(item["closedYears"]):
            seen = _has_number(quote, item["closedYears"])
            made = self.base("BUSINESS_REGISTRATION", quote) | {"require": "CLOSED", "closedWithinYears": int(item["closedYears"])}
            return self.flag(made, reasons + ([] if seen else [VALUE_MISSING]))
        if (
            kind == "REVENUE"
            and self.startup
            and isinstance(item["revenueYear"], int)
            and item["revenueYear"] >= 2000
            and (item["revenueMinWon"] or item["revenueMaxWon"])
        ):
            if any(isinstance(w, int) and w < 0 for w in (item["revenueMinWon"], item["revenueMaxWon"])):
                return self.ask(item, quote, reasons + [VALUE_MISSING])
            if item["revenueMinWon"] and item["revenueMaxWon"] and item["revenueMinWon"] > item["revenueMaxWon"]:
                return self.ask(item, quote, reasons + [INVERTED])
            seen = _has_won(quote, item["revenueMinWon"]) and _has_won(quote, item["revenueMaxWon"])
            seen = seen and (not item["revenueMinWon"] or bool(LOWER.search(quote))) and (not item["revenueMaxWon"] or bool(UPPER.search(quote)))
            if seen and _won_half_range(quote, item["revenueMinWon"] or None, item["revenueMaxWon"] or None):
                reasons = [*reasons, RANGE_PART]
            # 「전년도」면 기준일 연도 − 1, 숫자 연도면 근거 문장에 그 연도가 있어야 함
            prior = "전년도" in quote and reference is not None and item["revenueYear"] == reference.year - 1
            seen = seen and (prior or str(item["revenueYear"]) in quote or str(item["revenueYear"] % 100) in _numbers(quote))
            made = self.base("REVENUE", quote) | {"year": item["revenueYear"], "minWon": item["revenueMinWon"], "maxWon": item["revenueMaxWon"]}
            return self.flag(made, reasons + ([] if seen else [VALUE_MISSING]))
        if kind in ("INDUSTRY_EXCLUDE", "INDUSTRY_ONLY") and item["industryCodes"]:
            codes = list(dict.fromkeys(item["industryCodes"]))
            if all(re.fullmatch(r"[0-9]{2,5}", c) and c in _numbers(quote) for c in codes):
                mode = "EXCLUDE" if kind == "INDUSTRY_EXCLUDE" else "ONLY"
                return self.flag(self.base("INDUSTRY", quote) | {"mode": mode, "revision": 11, "codes": codes, "maybeCodes": []}, reasons)
        if kind in ("STATUS", "EXCLUDED_STATUS") and item["statusCodes" if kind == "STATUS" else "excludedCodes"]:
            allowed = (STARTUP_STATUS if kind == "STATUS" else STARTUP_EXCLUDED) if self.startup else (SPACE_STATUS if kind == "STATUS" else SPACE_EXCLUDED)
            codes = list(dict.fromkeys(item["statusCodes" if kind == "STATUS" else "excludedCodes"]))
            if all(c in allowed for c in codes):
                return self.flag(self.base(kind, quote) | {"anyOf": codes}, reasons)
            if not (item["question"] or "").strip():
                # 틀에 없는 코드가 섞임: 문장 통째 질문 대신 코드의 한국어 이름으로 묻는 질문 하나(리뷰 2026-10-23: 통째 질문이 같은 문장으로
                # 이미 만든 조건·다른 길과 겹쳤음)
                names = ", ".join((STATUS_NAMES if kind == "STATUS" else EXCLUDED_NAMES)[c] for c in codes)
                if kind == "STATUS":
                    question = f"{names}에 해당하나요?" if len(codes) == 1 else f"다음 중 하나에 해당하나요? {names}"
                    return self.ask(item | {"question": question, "metWhen": "YES"}, quote, reasons)
                question = f"다음 신청 제외 대상({names})에 해당하나요?" if len(codes) == 1 else f"다음 신청 제외 대상 중 하나에 해당하나요? {names}"
                return self.ask(item | {"question": question, "metWhen": "NO"}, quote, reasons)
        return self.ask(item, quote, reasons)

    def jurisdiction_region(self, item: dict[str, Any], quote: str, reasons: list[str]) -> dict[str, Any] | None:
        """지명 없이 「관내」「관할」만 있는 신청자 지역 근거: 기관 관할 시군구(agency_sigungu)가 하나로 정해지고 AI가 적은 지역도 그곳이면(또는
        적지 않았으면) 그 시군구로 확정. 정하지 못하면 확인 필요(사유 「관내가 어디인지 정하지 못함」). 근거에 지명이 있으면 None(보통 길로)
        (리뷰 2026-10-23: 「관내 주소지」를 「AI가 값을 바꿨을 수 있음」으로 걸었음)."""
        names = item["regionNames"] or []
        if names and all(region_named(t, quote) for n in names for t in str(n).split()):
            return None
        basis = item["regionBasis"]
        codes = self.region_codes(names) if names else None
        if basis and self.jurisdiction is not None and (not names or codes == [self.jurisdiction]):
            return self.flag(self.base("REGION", quote) | {"basis": basis, "regionCodes": [self.jurisdiction]}, reasons)
        if basis and codes is not None:
            return self.flag(self.base("REGION", quote) | {"basis": basis, "regionCodes": codes}, reasons + [JURISDICTION_UNKNOWN])
        return self.ask(item, quote, reasons + [JURISDICTION_UNKNOWN])

    def business_age(self, item: dict[str, Any], quote: str, reasons: list[str], reference: date | None) -> dict[str, Any]:
        if item["openedFrom"] or item["openedTo"]:
            if not (_valid_day(item["openedFrom"]) and _valid_day(item["openedTo"])):
                return self.ask(item, quote, reasons + [VALUE_MISSING])  # 「2023.10.07」처럼 형식이 틀리면 틀 검사에 걸려 틀 전체가 버려짐
            if _after(item["openedFrom"], item["openedTo"]):
                return self.ask(item, quote, reasons + [INVERTED])
            seen = _has_date(quote, item["openedFrom"]) and _has_date(quote, item["openedTo"])
            made = self.base("BUSINESS_AGE", quote) | {"openedFrom": item["openedFrom"], "openedTo": item["openedTo"]}
            return self.flag(made, reasons + ([] if seen else [VALUE_MISSING]))
        years, rule = item["years"], item["yearsRule"]
        if not _sane_years(years) or not rule:
            return self.ask(item, quote, reasons)
        if reference is None:
            return self.ask(item, quote, reasons + [NO_REFERENCE])
        opened_from, opened_to = opened_range(reference, int(years), rule)
        made = self.base("BUSINESS_AGE", quote) | {"openedFrom": opened_from, "openedTo": opened_to}
        seen = _has_number(quote, years) and bool(YEARS_WORDS[rule].search(quote))
        return self.flag(made, reasons + ([] if seen else [VALUE_MISSING]) + ([YEAR_COUNT] if _year_count(quote, years) else []))

    def closure(self, item: dict[str, Any], quote: str, reasons: list[str], reference: date | None) -> dict[str, Any]:
        mode = "NONE" if item["kind"] == "NO_RECENT_CLOSURE" else "ANY"
        if item["closedFrom"] or item["closedTo"]:
            if not (_valid_day(item["closedFrom"]) and _valid_day(item["closedTo"])):
                return self.ask(item, quote, reasons + [VALUE_MISSING])
            if _after(item["closedFrom"], item["closedTo"]):
                return self.ask(item, quote, reasons + [INVERTED])
            seen = _has_date(quote, item["closedFrom"]) and _has_date(quote, item["closedTo"])
            made = self.base("CLOSURE", quote) | {"mode": mode, "closedFrom": item["closedFrom"], "closedTo": item["closedTo"]}
            return self.flag(made, reasons + ([] if seen else [VALUE_MISSING]))
        years = item["closedYears"]
        if _sane_years(years) and reference is not None:
            made = self.base("CLOSURE", quote) | {"mode": mode, "closedFrom": _years_ago(reference, int(years)).isoformat(), "closedTo": None}
            return self.flag(made, reasons + ([] if _has_number(quote, years) else [VALUE_MISSING]))
        if years is None and mode == "ANY":
            return self.flag(self.base("CLOSURE", quote) | {"mode": "ANY", "closedFrom": None, "closedTo": None}, reasons)
        return self.ask(item, quote, reasons + ([] if reference is not None else [NO_REFERENCE]))

    def criteria(self, items: list[dict[str, Any]], reference: date | None) -> list[dict[str, Any]]:
        """같은 anyOf 묶음은 ANY_OF 하나로, 그 안에서 같은 option끼리는 한 길(모두 갖춰야 함). 길이 하나뿐이면 그 조건들 그대로."""
        made: list[dict[str, Any]] = []
        bundles: dict[str, list[dict[str, Any]]] = {}
        items = _without_echo(items)
        unexcepted = self.exception_bystanders(items)

        def convert(item: dict[str, Any]) -> dict[str, Any]:
            return self.criterion(item, reference, exception=id(item) not in unexcepted)

        # 제외 사유끼리 묶은 anyOf는 「또는」을 길로 잘못 읽은 것: 「A 또는 B인 자 제외」는 A도 B도 아니어야 해요(실측 2026-10-26
        # 관광기업지원센터: 「채무불이행으로 규제 중인 자 또는 휴/폐업 중인 사업자」가 「셋 중 하나만 아니면 됨」이 되어 채무불이행이어도 충족).
        # 길이 모두 제외 조건이면 묶지 않고 하나하나 공통으로 둡니다
        exclusion_only = {key for key in {i["anyOf"] for i in items if i["anyOf"]} if all(_exclusion(i) for i in items if i["anyOf"] == key)}
        for item in items:
            if _nationwide(item) and not item["anyOf"]:
                continue  # 「전국 소재」 지역 조건은 제한이 아님(실측 2026-10-22 서초: 지역 코드로 못 바꿔 의미 없는 확인 필요 질문이 됨)
            if item["anyOf"] and item["anyOf"] not in exclusion_only:
                if item["anyOf"] not in bundles:
                    bundles[item["anyOf"]] = []
                    made.append({"_bundle": item["anyOf"]})
                bundles[item["anyOf"]].append(item)
            else:
                made.append(convert(item))
        out = []
        for entry in made:
            if "_bundle" not in entry:
                out.append(entry)
                continue
            paths: dict[str, list[dict[str, Any]]] = {}
            for n, member in enumerate(bundles[entry["_bundle"]]):
                paths.setdefault(member.get("option") or f"_{n}", []).append(member)
            if len(paths) == 1:
                out.extend(convert(m) for m in next(iter(paths.values())))
                continue
            options = [{"label": _path_label(path, n), "criteria": [convert(m) for m in path]} for n, path in enumerate(paths.values(), 1)]
            out.append(self.base("ANY_OF", None) | {"options": options})
        return _without_repeats(_merge_closure_questions(_merge_exclusions(out)))

    def exception_bystanders(self, items: list[dict[str, Any]]) -> set[int]:
        """같은 근거 문장으로 만든 조건이 여럿이고 예외 단서가 그중 일부 조건만 말하면, 나머지 조건(id)은 예외 표시를 받지 않습니다."""
        shared: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            if len(_norm(item["quote"])) >= 4:
                shared.setdefault(_norm(item["quote"]), []).append(item)
        out: set[int] = set()
        for same in shared.values():
            if len(same) < 2 or (clause := exception_clause(same[0]["quote"], self.text)) is None:
                continue
            owners = {id(i) for i in same if _exception_topic(i, clause)}
            if owners:
                out |= {id(i) for i in same if id(i) not in owners}
        return out

    def build(self, reference: date | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        keys = {g["key"]: g for g in self.answer["groups"]}
        group_ids = {key: self.new_id(f"group-{key}") for key in keys}
        conditions, moved_notes = [], []
        for c in self.answer["conditions"]:
            if c["kind"] == "AGE" and self.meta.only(c["quote"]):
                continue  # 목록 정보에만 있는 나이는 아래에서 목록 정보 구간으로 한 번만(공고마다 다르게 나오지 않게)
            if c["kind"] == "REGION" and not c["anyOf"] and not _nationwide(c) and future_place(c["quote"]):
                # 앞으로 둘·옮길 곳(「사업장을 두고자 하는」「입주 후 전입」)은 지금의 지역 요건이 아님: 입주 뒤 의무 안내로
                moved_notes.append(
                    {
                        "kind": "OBLIGATION",
                        "groupId": group_ids.get(c["group"]),
                        "text": f"입주 뒤 의무일 수 있어 신청 자격(지금 있는 곳)으로 보지 않았습니다: {_clip(c['quote'])}",
                        "quote": c["quote"] if _quoted(c["quote"], self.text) else None,
                        "page": None,
                    }
                )
                continue
            conditions.append(c)
        common_items = [c for c in conditions if c["group"] not in keys]
        groups = [
            {
                "id": group_ids[key],
                "name": group["name"].strip() or key,
                "criteria": self.criteria([c for c in conditions if c["group"] == key], reference),
            }
            for key, group in keys.items()
        ] or [{"id": self.new_id("all"), "name": "전체", "criteria": []}]
        common = self.criteria(common_items, reference)
        if (age := self.meta_age([*common, *(c for g in groups for c in g["criteria"])])) is not None:
            common.insert(0, age)
        common += self.criteria_from_notes(common)
        common = check_directions(check_placement(common, groups, self.text), groups, self.text)
        common += self.attached_criteria([*common, *(c for g in groups for c in g["criteria"])])
        self.fill_empty_groups(groups, group_ids)
        self.add_registration(groups, group_ids)
        if self.truncated:
            # 뒷부분에 자격 조건이 있을 수 있음(리뷰 2026-10-22: 조건 0개면 자동 통과로 나갔음)
            question = "공고 글이 길어 뒷부분을 읽지 못했습니다. 원문의 나머지 신청 자격도 갖추었나요?"
            common.append(self.flag(self.base("ASK", None) | {"question": question, "metWhen": "YES"}, [TRUNCATED]))
        preferences = []
        for item in self.answer["preferences"]:
            quote = item["quote"]
            reasons = [] if _quoted(quote, self.text) else [QUOTE_MISSING]
            points = item["points"] if item["effect"] == "BONUS_POINTS" and isinstance(item["points"], int | float) and item["points"] > 0 else None
            if item["effect"] == "BONUS_POINTS" and points is None:
                continue  # 점수 없는 가점은 틀에 담을 수 없어 안내로
            if points is not None and not _has_number(quote, points):
                reasons = [*reasons, VALUE_MISSING]  # 근거 문장은 「가점 3점」인데 점수가 다름
            question = (item["question"] or "").strip() or f"다음에 해당하나요? 「{quote}」"  # 공백뿐인 질문은 틀 읽기가 거절함
            ask = self.flag(self.base("ASK", quote) | {"question": question, "metWhen": "YES"}, reasons)
            preferences.append(
                {
                    "id": self.new_id("pref"),
                    "label": _short(item["label"].strip() or quote.strip() or "우대", 80),
                    "groupId": self.preference_group(item, keys, group_ids),
                    "effect": item["effect"],
                    "points": points,
                    "criteria": [ask],
                    "quote": quote,
                    "page": None,
                }
            )
        notes = [
            {
                "kind": n["kind"],
                "groupId": group_ids.get(n["group"]),
                "text": n["text"],
                "quote": n["quote"] if _quoted(n["quote"], self.text) else None,
                "page": None,
            }
            for n in self.answer["notes"]
            if n["text"].strip()
        ] + moved_notes
        return common, groups, _merged_preferences(preferences), notes

    def meta_age(self, made: list[dict[str, Any]]) -> dict[str, Any] | None:
        """본문 나이가 없을 때 목록 정보 나이 하나(확인 필요). 온통청년 나이 제한 여부가 「제한 없음」인데 나이 값이 있으면 버리지 않고
        엇갈림 사유를 더해 둡니다(사용자 결정 2026-10-23: 제목이 「청년농」인데 나이가 빠져 49세 초과도 통과로 보였음)."""
        if any(c["kind"] == "AGE" for c in _every(made)):
            return None
        reasons = [META_ONLY]
        if (ages := self.meta.age_range()) is None:
            if (ages := self.meta.youth_unflagged) is None:
                return None
            reasons.append(AGE_FLAG_CONFLICT)
        youth = [line for line in self.meta.age_lines if "지원" in line]  # 온통청년은 최소·최대 두 줄, K-Startup은 첫 줄 하나
        youth_center = self.meta.youth is not None or self.meta.youth_unflagged is not None
        quote = "\n".join(youth) if youth_center and youth else (self.meta.age_lines or [None])[0]
        age = self.base("AGE", quote) | {"minAge": ages[0], "maxAge": ages[1]}
        return self.flag(age, [*reasons, *([self.date_reason] if self.date_reason else [])])

    def attached_criteria(self, made: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """「참여 제한 대상: 붙임파일 참조」처럼 제외·자격 칸의 값이 첨부를 가리키기만 하면 확인 필요 질문 하나(안내로만 두지 않음,
        리뷰 2026-10-23). 같은 줄로 이미 만든 조건이 있으면 더하지 않습니다."""
        quotes = [_norm(c.get("quote") or "") for c in _every(made)]
        out, seen = [], set()
        for line in self.meta.body.splitlines():
            found = _ATTACHED_LINE.match(unicodedata.normalize("NFKC", line))
            if found is None:
                continue
            head = re.sub(r"\s+", " ", found.group("head")).strip()
            exclusion = bool(_ATTACHED_EXCLUDE.search(head))
            if not exclusion and not _ATTACHED_ELIGIBLE.search(head):
                continue
            flat = _norm(line)
            if _norm(head) in seen or any(q and (q in flat or flat in q) for q in quotes):
                continue
            seen.add(_norm(head))
            question = f"붙임파일에 적힌 {head}에 해당하나요?"
            ask = self.base("ASK", line.strip()) | {"question": question, "metWhen": "NO" if exclusion else "YES"}
            out.append(self.flag(ask, [ATTACHED]))
        return out

    def fill_empty_groups(self, groups: list[dict[str, Any]], group_ids: dict[str, str]) -> None:
        """조건이 하나도 없는 대상군은 누구나 통과하는 길이라 「〈대상군〉에 해당하나요?」 확인 필요 질문으로 채웁니다(제자리에서).
        대상군이 둘 이상이면 언제나, 하나면 원문이 그 대상을 분명히 말할 때만(근거 문장이 원문에 있고 대상군 이름이 원문에 있음).
        AI가 대상군을 나누지 않아 만든 「전체」는 건드리지 않습니다(리뷰 2026-10-23: 「초기창업자」 대상군이 비어 업력과 상관없이 통과)."""
        sources = {group_ids[g["key"]]: g for g in self.answer["groups"] if g["key"] in group_ids}
        many = len(sources) >= 2
        for group in groups:
            source = sources.get(group["id"])
            if group["criteria"] or source is None:
                continue
            quote = source.get("quote") if _quoted(source.get("quote"), self.text) else None
            name = re.sub(r"\s+", " ", group["name"]).strip()
            named = quote is not None and len(_norm(name)) >= 2 and _norm(name) in _norm(self.text)
            if not many and not named:
                continue
            ask = self.base("ASK", quote) | {"question": f"{_short(name, 60)}에 해당하나요?", "metWhen": "YES"}
            group["criteria"] = [self.flag(ask, [EMPTY_GROUP])]

    def add_registration(self, groups: list[dict[str, Any]], group_ids: dict[str, str]) -> None:
        """기창업·창업기업 대상군에 사업자 조건이 없는데 원문이 사업자 등록을 요구하면 사업자(REGISTERED) 조건을 더합니다(제자리에서).
        대상군 근거 문장이 사업자 등록을 말하면 확정, 제출 서류(사업자등록증)로만 짐작하면 확인 필요. 예비창업자 대상군·예비창업자에게만
        걸린 서류 문장(「예비창업자의 경우 3개월 이내 창업(사업자등록증 제출)」)은 보지 않습니다."""
        sources = {group_ids[g["key"]]: g for g in self.answer["groups"] if g["key"] in group_ids}
        documents = next((line.strip() for line in self.meta.body.splitlines() if _registration_document(line)), None)
        for group in groups:
            source = sources.get(group["id"])
            name = group["name"]
            if source is None or not _BUSINESS_GROUP.search(name) or _PRE_FOUNDER_GROUP.search(name) or _RESTART_GROUP.search(name):
                continue
            if any(c["kind"] == "BUSINESS_REGISTRATION" for c in _every(group["criteria"])):
                continue
            stated = _quoted(source.get("quote"), self.text) and _REGISTERED_WORDS.search(unicodedata.normalize("NFKC", source["quote"]))
            if stated:
                quote, reasons = source["quote"], []
            elif documents is not None:
                quote, reasons = documents, [REGISTRATION_FROM_DOCUMENTS]
            else:
                continue
            made = self.base("BUSINESS_REGISTRATION", quote) | {"require": "REGISTERED"}
            made = made if self.startup else made | {"closedWithinYears": None}
            group["criteria"] = [*group["criteria"], self.flag(made, reasons) if reasons else made]

    def criteria_from_notes(self, common: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """안내(notes)에만 적힌 소득·자산 기준(「소득·자산 기준 적용」 「2025년 기준 적용」)은 금액을 몰라도 자격 기준이 있다는 뜻이라
        확인 필요 질문 하나로 공통에 둡니다(안내는 그대로). 이미 소득·자산을 묻는 조건이 있거나 「기준 없음」이면 두지 않습니다
        (리뷰 2026-10-23: 소득·자산 기준이 안내로만 들어가 중요 누락이 될 뻔했음)."""
        asked = any(_INCOME.search(_text_of(c)) for c in _every(common))
        asked = asked or any(_INCOME.search(f"{c.get('question') or ''} {c['quote']}") for c in self.answer["conditions"])
        for note in self.answer["notes"]:
            said = unicodedata.normalize("NFKC", f"{note['text']} {note['quote']}")
            if asked or not _INCOME_RULE.search(said) or _NO_RULE.search(said):
                continue
            quote = note["quote"] if _quoted(note["quote"], self.text) else None
            question = "공고에 적힌 소득·자산 기준을 충족하나요?"
            return [self.flag(self.base("ASK", quote) | {"question": question, "metWhen": "YES"}, [INCOME_RULE])]
        return []

    @staticmethod
    def preference_group(item: dict[str, Any], keys: dict[str, Any], group_ids: dict[str, str]) -> str | None:
        """우대가 걸릴 대상군: 우대 문장(이름·근거·질문)이 그 대상군 이름이나 대상군 낱말을 말할 때만. 아니면 공통(null)
        (리뷰 2026-10-23: 「본교 재학생·졸업생 창업기업」 우대가 근거 없이 기창업 대상군에만 걸렸음)."""
        key = item["group"]
        if key not in group_ids:
            return None
        name = _norm(keys[key]["name"])
        said = _norm(f"{item['label']} {item['quote']} {item.get('question') or ''}")
        if len(name) >= 2 and name in said:
            return group_ids[key]
        return group_ids[key] if any(w in name and w in said for w in _PREFERENCE_GROUP_WORDS) else None


# 제외·자격 칸의 값이 첨부만 가리킴(「참여 제한 대상: 붙임파일 참조」「신청 자격은 별첨 참고」)
_ATTACHED_LINE = re.compile(
    r"^[\s\-·•*※\d.)]*(?P<head>[^:：\n]{2,20}?)\s*(?:[:：]|(?:은|는)\s)\s*(?:붙임|첨부|별첨)\s*(?:\d+\s*)?(?:파일|문서|자료|공고문?)?\s*"
    r"(?:\d+\s*)?(?:을|를)?\s*(?:참조|참고|확인)[\s.)]*(?:바랍니다|하시기\s*바랍니다|요망)?[\s.]*$"
)
_ATTACHED_EXCLUDE = re.compile(r"제외|제한|결격|불가")
_ATTACHED_ELIGIBLE = re.compile(r"자격|요건|^(?:신청|지원|모집|입주|참여)\s*대상$")

# 사업 중인 대상군 이름(기창업자·창업기업·「5년 이내 창업자」·「7년 이내인 기업」)과 사업자 등록 요구
_BUSINESS_GROUP = re.compile(r"기\s*창업|창업\s*기업|창업자|기업|사업자")
_REGISTERED_WORDS = re.compile(
    r"사업자\s*등록\s*(?:을|이)?\s*(?:한|된|되어|마친|완료|필|필수|있는|보유)|사업자\s*등록\s*(?:기업|사업자)|(?:개인|법인)\s*사업자"
)
_RESTART_GROUP = re.compile(r"재\s*창업")  # 재창업자는 폐업 뒤 사업자가 없을 수 있음
_REGISTRATION_DOCUMENT = re.compile(r"사업자\s*등록\s*증")
_DOCUMENT_WORDS = re.compile(r"사본|서류|제출|구비|원본")  # 내야 할 서류로 적힌 줄(「사업자등록증 주소 변경」 같은 안내는 아님)
_LATER_DUTY = re.compile(r"이내\s*(?:에\s*)?창업|창업\s*(?:후|필수)|(?:입주|선정|협약|계약)\s*(?:후|뒤|이후|시)")


def _registration_document(line: str) -> bool:
    """사업자등록증을 서류로 내라는 줄인데 예비창업자에게만 걸리거나 입주·선정 뒤 할 일이 아닌지."""
    plain = unicodedata.normalize("NFKC", line)
    if not _REGISTRATION_DOCUMENT.search(plain) or not _DOCUMENT_WORDS.search(plain):
        return False
    return not (_PRE_FOUNDER_WORDS.search(plain) or _PRE_FOUNDER_SCOPE.search(plain) or _LATER_DUTY.search(plain))


# 소득·자산 기준이 있다는 문장(안내에만 있을 때 조건으로)
_INCOME = re.compile(r"소득|자산|재산")
_INCOME_RULE = re.compile(r"(?:소득|자산|재산)[^\n]{0,12}?기준")
_NO_RULE = re.compile(r"기준\s*(?:이\s*)?(?:없|무관|미적용|적용\s*(?:하지\s*)?않)|제한\s*(?:이\s*)?없")

_PREFERENCE_GROUP_WORDS = ("예비", "기창업", "재창업", "초기", "도약", "성장", "법인", "개인사업자", "대학생", "청년", "여성")

# 지명 없이 기관 관할을 가리키는 말(「관내 주소지」「관할 지역에 사업장」)
_JURISDICTION = re.compile(r"관내|관할")


def agency_sigungu(payload: dict[str, Any], regions: Any) -> str | None:
    """기관이 시군구(「○○도 ○○군」「○○구청」)이고 지역표로 그 시군구 하나가 정해지면 그 10자리 코드. 수집기 지역 코드가 있으면 그 코드도
    같은 시군구 하나여야 합니다(다르거나 여럿이면 None — 관내가 어디인지 모름)."""
    tokens = str(payload.get("agency") or "").split()
    if regions is None or not tokens:
        return None
    last = re.sub(r"(?<=[시군구])청$", "", tokens[-1])
    if not SIGUNGU_SUFFIX.fullmatch(last):
        return None
    match = regions.lookup(" ".join([*tokens[:-1], last]))
    if match.code is None or match.level != "SIGUNGU" or match.note:
        return None
    collected = {str(c) for c in payload.get("regionCodes") or [] if re.fullmatch(r"[0-9]{5}", str(c))}
    if collected and collected != {match.code[:5]}:
        return None
    return match.code


# 앞으로 둘·옮길 곳: 사업장·주소를 「두고자」「이전하고자」, 「입주 후」「선정 후」, 「전입 예정」(이 말이 있으면 지역 요건이 아니라 의무)
_FUTURE_PLACE = re.compile(
    r"(?:사업장|본점|본사|주소지?|소재지|사무실|사업자\s*등록)[^\n]{0,8}?(?:두고자|두려는|두고\s*싶|이전하고자|이전하려는|이전\s*(?:가능|예정|할)|"
    r"옮기고자|옮기려는|옮길|등록할\s*(?:예정|수)|등록\s*예정)|(?:입주|선정|협약|계약)\s*(?:후|뒤|이후|시)|전입\s*(?:예정|할|가능)|이전\s*(?:예정|가능)"
)
# 「전입」「이전」만: 지금의 요건일 수도 있어(「전입일로부터 6개월 이상 거주」) 옮기지 않고 확인 필요
_MOVE_PLACE = re.compile(r"전입|이전")


def future_place(quote: str | None) -> bool:
    """근거 문장이 앞으로 둘·옮길 곳을 말하는지(지금의 거주·소재 요건이 아님)."""
    return bool(_FUTURE_PLACE.search(unicodedata.normalize("NFKC", quote or "")))


def moving_place(quote: str | None) -> bool:
    """근거 문장에 앞으로 둘·옮길 곳이나 전입·이전 말이 있는지(지역 요건으로 확정하지 않음)."""
    plain = unicodedata.normalize("NFKC", quote or "")
    return future_place(plain) or bool(_MOVE_PLACE.search(plain))


def _exclusion_side(item: dict[str, Any], made: dict[str, Any]) -> bool:
    return (made["kind"] == "ASK" and made.get("metWhen") == "NO") or item["kind"] in EXCLUDING_KINDS


def _scope_reasons(item: dict[str, Any], made: dict[str, Any], context: str) -> list[str]:
    """질문이 기대는 범위가 본문에 정해져 있는지 규칙으로: 범위 없는 말(「각종」「자격을 충족」), 법령 조항으로만 정한 범위,
    자격 쪽 「… 등」 열린 목록, 심사 판단 말은 확인 필요. 제외 쪽에 예시 목록(「유흥업 등」「소음·진동 등」)이 있으면 법령 참조나
    AI의 정의 없음(defined false)으로 잡지 않습니다(예시로 답할 수 있음). 법령·목록·심사 규칙은 질문(ASK)에만.
    context는 근거 문장(바로 다음 줄의 괄호 목록까지, _continued)."""
    asked = unicodedata.normalize("NFKC", f"{item.get('question') or ''}\n{item['quote']}")
    quote = _BULLET.sub("", unicodedata.normalize("NFKC", context or ""))  # 머리 글머리표(「·」)는 목록 구분 기호가 아님
    exclusion = _exclusion_side(item, made)
    examples = exclusion and bool(_EXAMPLES.search(quote))
    reasons = []
    if _VAGUE.search(asked) or (item.get("defined") is False and not examples):
        reasons.append(UNDEFINED)
    if made["kind"] != "ASK":
        return reasons
    # 법령·심사 판단은 신청자가 답할 질문에 있을 때만(근거 문장이 법령을 이유로 들어도 질문이 구체적이면 답할 수 있음).
    # 질문이 「제외 업종」처럼 다른 곳을 가리키면 근거 문장의 법령이 범위
    question = unicodedata.normalize("NFKC", made.get("question") or "")
    if (_LAW.search(question) or (_REFERS.search(question) and _LAW.search(quote))) and not examples:
        reasons.append(LAW_SCOPE)
    if not exclusion and _OPEN_LIST.search(quote):
        reasons.append(OPEN_LIST)
    if not exclusion and _EVALUATIVE.search(question):
        reasons.append(EVALUATIVE)
    return reasons


_DATE_ITEM_KINDS = {"AGE", "BUSINESS_AGE", "NO_RECENT_CLOSURE", "CLOSURE_REQUIRED", "REVENUE"}


def _date_dependent(item: dict[str, Any], made: dict[str, Any]) -> bool:
    """기준일에 따라 답이 달라지는 조건인지(나이·업력·폐업 기간·매출 연도, 영업 경력, 폐업 N년 이내)."""
    return item["kind"] in _DATE_ITEM_KINDS or made["kind"] in ("AGE", "BUSINESS_CAREER", "CLOSURE") or made.get("closedWithinYears") is not None


def _merge_exclusions(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 자리에서 같은 근거 문장으로 만든 제외 유형(EXCLUDED_STATUS)은 하나로 합칩니다(하나라도 해당하면 제외라 뜻이 같음).
    확인 필요 여부·사유가 다르면 합치지 않습니다."""
    first: dict[tuple[str, bool, str | None], dict[str, Any]] = {}
    out = []
    for criterion in criteria:
        if criterion["kind"] == "EXCLUDED_STATUS" and _norm(criterion.get("quote") or ""):
            key = (_norm(criterion["quote"]), criterion["inReview"], criterion["reviewReason"])
            if key in first:
                kept = first[key]
                kept["anyOf"] = list(dict.fromkeys([*kept["anyOf"], *criterion["anyOf"]]))
                continue
            first[key] = criterion
        out.append(criterion)
    return out


# 휴업과 폐업을 함께 말하는 문장(「휴·폐업 중인 자」「휴업 또는 폐업 중인 기업」)
_SUSPENDED_AND_CLOSED = re.compile(r"휴\s*[·ㆍ/,∙]?\s*폐업|휴업\s*(?:또는|이나|및|·|ㆍ|/|,)?\s*폐업|폐업\s*(?:또는|이나|및|·|ㆍ|/|,)?\s*휴업")
_SUSPENDED_OR_CLOSED_QUESTION = re.compile(r"휴업|폐업")
MERGED_SUSPENSION = "지금 휴업이나 폐업 상태인가요?"


def _merge_closure_questions(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 자리에서 같은 근거 문장(휴업과 폐업을 함께 말함)으로 휴업 제외 유형(BUSINESS_SUSPENDED)과 휴업·폐업을 묻는 제외 질문(「예」면
    탈락)이 함께 나오면 질문 하나(「지금 휴업이나 폐업 상태인가요?」)로 합칩니다. 제외 유형은 휴업만이라 질문이 폐업까지 맡습니다
    (리뷰 2026-10-23: 「휴업」 제외와 「폐업 상태인가요?」를 따로 물었음). 합친 쪽의 확인 필요 사유는 남은 질문에 옮깁니다."""
    asks = {}
    for criterion in criteria:
        quote = _norm(criterion.get("quote") or "")
        if (
            criterion["kind"] == "ASK"
            and criterion.get("metWhen") == "NO"
            and quote
            and _SUSPENDED_OR_CLOSED_QUESTION.search(criterion["question"] or "")
            and _SUSPENDED_AND_CLOSED.search(unicodedata.normalize("NFKC", criterion["quote"]))
        ):
            asks.setdefault(quote, criterion)
    out = []
    merged: dict[int, list[str]] = {}
    for criterion in criteria:
        ask = asks.get(_norm(criterion.get("quote") or ""))
        if criterion["kind"] == "EXCLUDED_STATUS" and ask is not None and "BUSINESS_SUSPENDED" in criterion["anyOf"]:
            merged.setdefault(id(ask), []).extend(r for r in (criterion.get("reviewReason") or "").split("; ") if r)
            rest = [c for c in criterion["anyOf"] if c != "BUSINESS_SUSPENDED"]
            if rest:
                out.append(criterion | {"anyOf": rest})
            continue
        out.append(criterion)
    fixed = []
    for criterion in out:
        if id(criterion) in merged:
            question = criterion["question"]
            if not (re.search("휴업", question) and re.search("폐업", question)):
                question = MERGED_SUSPENSION
            criterion = _Builder.flag(criterion | {"question": question}, merged[id(criterion)])
        fixed.append(criterion)
    return fixed


def _merged_preferences(preferences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 근거 문장·같은 효과·같은 대상군·같은 질문·같은 점수의 우대는 한 번만."""
    seen: set[tuple[Any, ...]] = set()
    out = []
    for preference in preferences:
        ask = preference["criteria"][0]
        key = (_norm(preference.get("quote") or ""), preference["effect"], preference["groupId"], _norm(ask.get("question") or ""), preference["points"])
        if key[0] and key in seen:
            continue
        seen.add(key)
        out.append(preference)
    return out


def _sane_years(value: Any) -> bool:
    """1~100년의 정수만(「5000년」은 날짜 계산에서 예외, 0년은 틀 스키마 위반)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and float(value).is_integer() and 1 <= value <= 100


def _nationwide(item: dict[str, Any]) -> bool:
    names = [re.sub(r"\s+", "", n) for n in item.get("regionNames") or []]
    return item["kind"] == "REGION" and bool(names) and all(n == "전국" for n in names)


def _path_label(path: list[dict[str, Any]], number: int) -> str:
    """길 이름: 조건 종류를 이어 붙인 짧은 이름(근거 문장은 길마다 같을 수 있어 쓰지 않음). 내부 코드는 보여 주지 않습니다
    (리뷰 2026-10-23: 「예비창업자 + NO_RECENT_CLOSURE」가 그대로 나갔음)."""
    parts = []
    for item in path:
        kind = item["kind"]
        question = (item.get("question") or "").strip()
        if kind == "BUSINESS_AGE" and _sane_years(item.get("years")):
            parts.append(f"업력 {item['years']:g}년")
        elif kind == "STATUS" and item.get("statusCodes"):
            parts.append("/".join(STATUS_NAMES.get(c, "유형") for c in item["statusCodes"]))
        elif kind == "OTHER" and question:
            parts.append(_short(question, 24))
        else:
            parts.append(KIND_NAMES.get(kind, "조건"))
    return f"{number}번째 길: " + " + ".join(dict.fromkeys(parts))


def _exclusion(item: dict[str, Any]) -> bool:
    """제외 조건인지: 신청 제외 사유(EXCLUDED_STATUS) 또는 「예」면 신청 불가인 질문(OTHER, metWhen NO)."""
    return item["kind"] == "EXCLUDED_STATUS" or (item["kind"] == "OTHER" and item.get("metWhen") == "NO")


def _without_echo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """질문 없는 기타 조건(OTHER)이 같은 길에서 같은 근거 문장으로 이미 나눈 조건과 겹치면 뺍니다. 빼지 않으면 문장 통째 질문이 되어
    나눠 만든 조건을 사용자가 두 번 답합니다(리뷰 2026-10-23)."""

    def echo(item: dict[str, Any]) -> bool:
        return item["kind"] == "OTHER" and not (item.get("question") or "").strip()

    split = {(i["group"], i["anyOf"], i["option"], _norm(i["quote"])) for i in items if not echo(i) and _norm(i["quote"])}
    return [i for i in items if not (echo(i) and (i["group"], i["anyOf"], i["option"], _norm(i["quote"])) in split)]


def _without_repeats(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 자리에서 근거 문장·질문·답 방향이 모두 같은 질문은 한 번만 둡니다(같은 내용을 두 번 묻지 않게)."""
    seen: set[tuple[str, str, str]] = set()
    out = []
    for criterion in criteria:
        if criterion["kind"] == "ASK":
            key = (_norm(criterion.get("quote") or ""), _norm(criterion["question"]), criterion["metWhen"])
            if key in seen:
                continue
            seen.add(key)
        out.append(criterion)
    return out


def _every(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for c in criteria for x in [c, *_every([i for o in c.get("options") or [] for i in o["criteria"]])]]


def _coded_exclusion(criterion: dict[str, Any], text: str) -> bool:
    """제외로 읽은 조건: 제외 유형·폐업 이력 없음·제외 업종, 또는 제외 문장으로 만든 「예」면 탈락 질문. 「직장보험 가입자가 아닌 자」처럼
    자격 문장 안의 부정 조건으로 만든 「예」면 탈락 질문은 제외가 아님(같은 문장의 다른 자격 질문과 방향이 달라도 맞음)."""
    if criterion["kind"] == "ASK":
        return criterion.get("metWhen") == "NO" and excluding_quote(criterion.get("quote"), text)
    return _excluding(criterion)


def check_directions(common: list[dict[str, Any]], groups: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """같은 근거 문장으로 제외 조건을 만들었는데 그 문장의 다른 질문은 「예」가 충족(부정 질문이 아님)이면 답 방향이 엇갈린 것이라
    확인 필요로 둡니다(뒤집지 않음). groups는 제자리에서 고치고 공통을 돌려줍니다."""
    every = _every([*common, *(c for g in groups for c in g["criteria"])])
    excluded = {_norm(c.get("quote") or "") for c in every if _coded_exclusion(c, text)}
    excluded.discard("")

    def fix(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for c in criteria:
            if c.get("options"):
                c = c | {"options": [o | {"criteria": fix(o["criteria"])} for o in c["options"]]}
            if c["kind"] == "ASK" and c["metWhen"] == "YES" and not _negated(c["question"]) and _norm(c.get("quote") or "") in excluded:
                c = _Builder.flag(c, [DIRECTION_CONFLICT])
            out.append(c)
        return out

    for group in groups:
        group["criteria"] = fix(group["criteria"])
    return fix(common)


# 대상군 배치 검사(리뷰 2026-10-23: 「본사·연구소·지점·졸업기업 중 하나」가 공통에 있어 예비창업자 길이 늘 떨어졌고,
# 예비창업자에게만 해당하는 폐업 단서가 법인 길에도 걸렸음)
_BUSINESS_WORDS = re.compile(r"본사|본점|지점|연구소|졸업\s*기업|법인\s*사업자|개인\s*사업자|업력|매출|영위|기\s*창업|창업\s*기업|사업\s*개시|설립\s*등기")
_PRE_FOUNDER_WORDS = re.compile(r"예비\s*창업|창업\s*예정|창업\s*준비|사업자\s*등록\s*(?:전|예정|이\s*없|을\s*하지\s*않)")
_PRE_FOUNDER_SCOPE = re.compile(r"예비\s*창업자?\s*(?:의|는|은)?\s*경우|창업\s*예정")
_PRE_FOUNDER_GROUP = re.compile(r"예비(?!\s*사회적)")


def _text_of(criterion: dict[str, Any]) -> str:
    return f"{criterion.get('question') or ''} {criterion.get('quote') or ''}"


def _not_registered(criterion: dict[str, Any]) -> bool:
    return criterion["kind"] == "BUSINESS_REGISTRATION" and criterion.get("require") == "NOT_REGISTERED"


def _pre_founder_path(criteria: list[dict[str, Any]]) -> bool:
    """예비창업자(사업자 아님) 길이 있는지: 사업자 아님 조건이 바로 있거나 택1의 한 길에 있음."""
    return any(_not_registered(c) or any(_pre_founder_path(o["criteria"]) for o in c.get("options") or []) for c in criteria)


def _presumes_business(criterion: dict[str, Any]) -> bool:
    """이미 사업 중인 기업이어야 갖출 수 있는 조건인지(업력·사업자·매출·영업 경력, 기업 유형, 본사·지점 같은 기업 형태를 묻는 질문)."""
    kind = criterion["kind"]
    if kind in ("BUSINESS_AGE", "REVENUE", "BUSINESS_CAREER"):
        return True
    if kind == "BUSINESS_REGISTRATION":
        return criterion.get("require") == "REGISTERED"
    if kind == "STATUS":
        return bool(criterion.get("anyOf")) and set(criterion["anyOf"]) <= BUSINESS_STATUS
    if kind == "INDUSTRY":
        return criterion.get("mode") == "ONLY" and "영위" in (criterion.get("quote") or "")
    if kind == "ASK":
        text = _text_of(criterion)
        return criterion.get("metWhen") == "YES" and bool(_BUSINESS_WORDS.search(text)) and not _PRE_FOUNDER_WORDS.search(text)
    if kind == "ANY_OF":
        return all(any(_presumes_business(c) for c in o["criteria"]) for o in criterion.get("options") or [])
    return False


def _excluding(criterion: dict[str, Any]) -> bool:
    kind = criterion["kind"]
    return (
        kind == "EXCLUDED_STATUS"
        or (kind == "ASK" and criterion.get("metWhen") == "NO")
        or (kind == "CLOSURE" and criterion.get("mode") == "NONE")
        or (kind == "INDUSTRY" and criterion.get("mode") == "EXCLUDE")
    )


# 「예비창업자 또는 1인 창조기업으로 …」「예비~창업 7년 이내」처럼 예비창업자와 다른 신청자를 함께 지목한 문장(리뷰 2026-10-23: 예비창업자
# 전용으로 보고 공통 조건을 확인 필요로 둔 오경보)
_PRE_FOUNDER_AND_OTHERS = re.compile(r"예비\s*(?:창업자?|창업\s*기업)?\s*(?:또는|및|이나|와|과|[,·ㆍ/~∼])\s*\S|\S\s*(?:또는|및|이나|[,·ㆍ/])\s*예비\s*창업")


def _pre_founder_only(criterion: dict[str, Any]) -> bool:
    """예비창업자에게만 해당할 수 있는 문장(「예비창업자의 경우 …」「창업 예정」)으로 만든 제외·질문 조건인지. 예비창업자와 다른 신청자를
    함께 지목한 문장(「예비창업자 또는 X」)은 「…의 경우」로 범위를 좁히지 않았으면 예비창업자 전용이 아닙니다."""
    text = _text_of(criterion)
    if _PRE_FOUNDER_AND_OTHERS.search(text) and not _PRE_FOUNDER_SCOPE.search(text):
        return False
    if _excluding(criterion):
        return bool(_PRE_FOUNDER_WORDS.search(text))
    return criterion["kind"] == "ASK" and bool(_PRE_FOUNDER_SCOPE.search(text))


def _pre_founder_group(group: dict[str, Any]) -> bool:
    return bool(_PRE_FOUNDER_GROUP.search(group["name"])) or any(_not_registered(c) for c in group["criteria"])


_GROUP_WORDS = re.compile(r"예비|기\s*창업|창업\s*기업|초기|도약|성장|재창업|법인|개인\s*사업자|분야|트랙|부문|유형")


def _common_exclusion(criterion: dict[str, Any], text: str, group_names: list[str]) -> bool:
    """제외 조건의 근거가 대상군을 지목하지 않는 제외 머리말 아래에 있고, 문장 자체도 대상군(이름·대상군 낱말)을 지목하지 않는지."""
    heading = exclusion_heading(criterion.get("quote"), text)
    if heading is None or _GROUP_WORDS.search(heading) or any(n in _norm(heading) for n in group_names if len(n) >= 2):
        return False
    quote = _without_term_names(_norm(criterion.get("quote") or ""), group_names)
    return not any(n in quote for n in group_names if len(n) >= 2) and not _GROUP_WORDS.search(quote)


# 대상군 이름 뒤에 이 말이 붙으면 그 대상군을 지목한 것이 아니라 다른 것의 이름(「1인 창조기업 지원센터」「1인창조기업 제외 업종」)
_TERM_AFTER_NAME = "(?=지원센터|센터|제외업종|지원사업|업종|법)"


def _without_term_names(quote: str, group_names: list[str]) -> str:
    """공백을 뺀 근거 문장에서 대상군 이름이 다른 것의 이름 앞부분으로만 쓰인 곳을 지웁니다(대상군을 지목한 것이 아님)."""
    for name in group_names:
        if len(name) >= 2:
            quote = re.sub(re.escape(name) + _TERM_AFTER_NAME, "", quote)
    return quote


def check_placement(common: list[dict[str, Any]], groups: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """조립한 틀의 대상군 배치를 검사해 확신이 없는 조건을 확인 필요로 둡니다(옮기지 않음). groups는 제자리에서 고치고 공통을 돌려줍니다.
    - 예비창업자 길이 있는데 공통 조건이 사업 중인 기업을 전제하면 확인 필요
    - 예비창업자에게만 해당할 수 있는 제외·질문이 다른 신청자도 받는 자리(공통·섞인 대상군)에 있으면 확인 필요
    - 대상군이 둘 이상일 때 한 대상군의 제외 문장(또는 그 예외 문장)이 다른 대상군 이름을 말하면 확인 필요
    - 대상군이 둘 이상일 때 한 대상군에 걸린 제외 조건이 원문의 공통 제외 단락(머리말이 대상군을 지목하지 않음) 문장이고 문장도 대상군을
      지목하지 않으면 공통으로 옮김(리뷰 2026-10-23 3차: 확인 필요로만 두면 다른 대상군 신청자에게 그 제외가 걸리지 않았음).
      업력·연수 제외(「업력 7년 초과 기업」)와 예비창업자 전용 문장은 그 대상군에 남기고, 택1 길 안에 있으면 옮기지 않고 확인 필요"""
    common = _moved_common_exclusions(common, groups, text)
    pre_founder = _pre_founder_path(common) or any(_pre_founder_group(g) or _pre_founder_path(g["criteria"]) for g in groups)
    every_group_pre = bool(groups) and all(_pre_founder_group(g) for g in groups)
    checked = []
    for criterion in common:
        reasons = []
        if pre_founder and _presumes_business(criterion) and not _pre_founder_path([criterion]):
            reasons.append(PLACEMENT)
        if not every_group_pre and _pre_founder_only(criterion):
            reasons.append(SCOPE)
        checked.append(_Builder.flag(criterion, reasons) if reasons else criterion)
    names = {g["id"]: _norm(g["name"]) for g in groups}
    for group in groups:
        own = names[group["id"]]
        others = [n for gid, n in names.items() if gid != group["id"] and len(n) >= 2 and n not in own and own not in n]
        fixed = []
        for criterion in group["criteria"]:
            reasons = []
            if not _pre_founder_group(group) and _pre_founder_only(criterion):
                reasons.append(SCOPE)
            if _excluding(criterion):
                said = _norm(f"{criterion.get('quote') or ''} {exception_clause(criterion.get('quote'), text) or ''}")
                if any(n in said for n in others):
                    reasons.append(OTHER_GROUP)
            if criterion.get("options") and len(groups) >= 2:
                options = [o | {"criteria": _held_in_option(o["criteria"], text, list(names.values()))} for o in criterion["options"]]
                criterion = criterion | {"options": options}
            fixed.append(_Builder.flag(criterion, reasons) if reasons else criterion)
        group["criteria"] = fixed
    return checked


# 업력·연수로 거르는 제외(기창업자에게만 뜻이 있음): 대상군에 남김
# 「2년간 입주한 이력」처럼 업력이 아닌 기간은 빼고, 연수에 방향 말(초과·이상·이내·미만·넘·경과)이 붙은 것만
_PERIOD_WORDS = re.compile(r"업력|창업\s*(?:후|한\s*지)|설립|개업|사업\s*개시|\d+\s*년\s*(?:이\s*|을\s*|가\s*)?(?:초과|이상|이내|미만|넘|경과|지난|지나지|차)")


def _period_exclusion(criterion: dict[str, Any]) -> bool:
    return criterion["kind"] in ("BUSINESS_CAREER", "BUSINESS_AGE") or bool(_PERIOD_WORDS.search(_text_of(criterion)))


def _movable_exclusion(criterion: dict[str, Any], text: str, group_names: list[str]) -> bool:
    return _excluding(criterion) and _common_exclusion(criterion, text, group_names) and not _period_exclusion(criterion) and not _pre_founder_only(criterion)


def _same_key(criterion: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in criterion.items() if k != "id"}, ensure_ascii=False, sort_keys=True)


def _moved_common_exclusions(common: list[dict[str, Any]], groups: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    """대상군이 둘 이상일 때 대상군을 지목하지 않는 공통 제외 단락의 제외 조건을 대상군에서 공통으로 옮깁니다(같은 것은 한 번만).
    groups는 제자리에서 고치고 새 공통을 돌려줍니다."""
    if len(groups) < 2:
        return common
    names = [_norm(g["name"]) for g in groups]
    moved = []
    for group in groups:
        kept = []
        for criterion in group["criteria"]:
            (moved if _movable_exclusion(criterion, text, names) else kept).append(criterion)
        group["criteria"] = kept
    seen = {_same_key(c) for c in common}
    out = list(common)
    for criterion in moved:
        if _same_key(criterion) not in seen:
            seen.add(_same_key(criterion))
            out.append(criterion)
    return out


def _held_in_option(criteria: list[dict[str, Any]], text: str, group_names: list[str]) -> list[dict[str, Any]]:
    """택1 길 안의 공통 제외 단락 문장: 길을 바꾸면 뜻이 달라질 수 있어 옮기지 않고 확인 필요."""
    return [_Builder.flag(c, [COMMON_EXCLUSION]) if _movable_exclusion(c, text, group_names) else c for c in criteria]


def startup_frame(payload: dict[str, Any], reading: Any, regions: Any) -> dict[str, Any] | None:
    """AI 읽기 → 창업지원 틀. 창업 지원이 아니라고 읽었으면 None."""
    if not reading.answer["relevant"]:
        return None
    text = str(payload.get("text") or "")
    builder = _Builder(reading, text, regions, startup=True, record=payload.get("record"), jurisdiction=agency_sigungu(payload, regions))
    reference = builder.reference()
    common, groups, preferences, notes = builder.build(reference)
    return repair(
        {
            "schema": "startup-support-judgment.v1",
            "rawPolicyId": payload["rawPolicyId"],
            "rawVersion": payload["version"],
            "referenceDate": reference.isoformat() if reference else None,
            "common": common,
            "groups": groups,
            "preferences": preferences,
            "notes": notes,
        }
    )


KST = timezone(timedelta(hours=9))  # 한국은 일광 절약 시간이 없어 고정 시차


def uses_judging_date(frame: dict[str, Any] | None) -> bool:
    """기준일을 대신 정한 틀인지(접수 시작일·판정일·접수 마감일, 또는 「신청일 기준」 — 안내 문장 머리말로 표시). 이런 틀은 검수 전 자동
    통과로 내보내지 않습니다."""
    return bool(frame) and any(n["kind"] == "OTHER" and n["text"].startswith(JUDGING_DATE_NOTE) for n in frame.get("notes") or [])


def judging_day() -> date:
    """판정일: 처리하는 순간의 한국 날짜."""
    return datetime.now(KST).date()


_DATE = r"(20\d{2})[-.]?(\d{2})[-.]?(\d{2})"
# 신청 기간 칸 글자가 기간 하나뿐일 때만(「20260123 ~ 20260202」, 기업마당 「2026-10-16 ~ 2026-11-03」). 여러 구간·「예산 소진 시까지」는 모름
_ONE_PERIOD = re.compile(rf"\s*{_DATE}\s*~\s*{_DATE}\s*")
PERIOD_TEXT_FIELDS = ("aplyYmd", "reqstBeginEndDe")  # 온통청년·기업마당 신청 기간 칸


def _day(value: Any) -> str | None:
    text = str(value or "")
    return _real_day(text[:4], text[4:6], text[6:8]) if re.fullmatch(r"20\d{6}", text) else None


def _real_day(year: str, month: str, day: str) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def policy_apply_period(policy: dict[str, Any]) -> tuple[str | None, str | None]:
    """접수 기간(시작일, 마감일). K-Startup 날짜 칸이 있으면 그것, 없으면 온통청년(aplyYmd)·기업마당(reqstBeginEndDe) 신청 기간 칸이
    기간 하나뿐일 때 그 두 날. 여러 구간이거나 날짜가 아닌 글이면 모름(None) — 틀린 날짜보다 모름이 낫습니다.
    이벤트 schedule과 기준일 대체(fallback_reference)가 같은 값을 씁니다."""
    record = policy.get("record") or {}
    start, end = _day(record.get("pbanc_rcpt_bgng_dt")), _day(record.get("pbanc_rcpt_end_dt"))
    if start or end:
        return start, end
    for key in PERIOD_TEXT_FIELDS:
        if (found := _ONE_PERIOD.fullmatch(str(record.get(key) or ""))) is not None:
            first, last = _real_day(*found.groups()[:3]), _real_day(*found.groups()[3:])
            if first and last and first <= last:
                return first, last
    return None, None


def fallback_reference(payload: dict[str, Any], today: date | None = None) -> tuple[date, str]:
    """원문에 공고일·기준일이 없을 때 대신 쓸 기준일과 그 설명: 접수 시작일 → 판정일(판정일이 접수 마감 뒤면 접수 마감일).
    (리뷰 2026-10-23: 접수 기간이 이벤트 schedule에 있는데 틀은 「기준일 없음, 판정일」이라고 말했고, 마감 뒤 판정일을 썼음)"""
    start, end = policy_apply_period(payload)
    if start:
        day = date.fromisoformat(start)
        return day, f"접수 시작일({day.isoformat()})"
    day = today or judging_day()
    if end and day > date.fromisoformat(end):
        last = date.fromisoformat(end)
        return last, f"판정일이 접수 마감 뒤라 접수 마감일({last.isoformat()})"
    return day, f"판정일({day.isoformat()})"


# 「신청일 기준」「신청일 현재」「접수일 기준」: 자격 기준일이 신청하는 날(사람마다 다름)
_APPLICATION_DAY = re.compile(r"(?:신청|접수)\s*일\s*(?:현재|기준)")


def _application_rule(reading: Any, text: str) -> bool:
    """자격 기준일이 신청일인지: AI가 APPLICATION으로 읽었거나, 기준일 문구 없음(NONE)으로 읽었는데 원문에 「신청일 기준」류 말이 있음
    (policy/v7 이전 읽기에는 APPLICATION 값이 없음)."""
    rule = reading.answer["referenceRule"]
    return rule == "APPLICATION" or (rule == "NONE" and bool(_APPLICATION_DAY.search(unicodedata.normalize("NFKC", text))))


def space_frame(payload: dict[str, Any], reading: Any, regions: Any, *, today: date | None = None) -> dict[str, Any] | None:
    """AI 읽기 → 사업공간 틀. 사업공간 틀은 기준일이 필수입니다.
    - 기준일·공고일을 근거와 함께 읽었으면 그 날
    - 원문에 공고일·기준일이 없으면(온통청년처럼 공고일 칸이 없는 출처) 접수 시작일 → 판정일(today, 기본은 지금 한국 날짜, 접수 마감
      뒤면 마감일) 순서로 대신 정하고, 어느 날짜를 썼는지 안내(OTHER)로 남기며, 기준일에 기대는 조건(나이·업력·폐업 기간 등)은 모두
      확인 필요(사용자 결정 2026-10-23, 선택 B)
    - 「신청일 기준」이면 같은 순서(공고일 → 접수 시작일 → 판정일)의 날짜를 쓰고, 기준일에 기대는 조건은 확인 필요(사유 「신청일 기준」)
    - 찍힌 기준일(EXPLICIT)이 있다거나 AI가 공고일·기준일 날짜를 적었는데 근거 문장으로 확인하지 못했으면 None: 원문에 날짜가 있을
      가능성이 높아 판정일로 바꾸면 틀린 값이 됨(보내지 않음, 지금과 같음)"""
    if not reading.answer["relevant"]:
        return None
    text = str(payload.get("text") or "")
    builder = _Builder(reading, text, regions, startup=False, record=payload.get("record"), jurisdiction=agency_sigungu(payload, regions))
    application = _application_rule(reading, text)
    reference = builder.reference()
    used = None  # 대신 정한 날짜의 설명
    if reference is None and reading.answer["referenceRule"] != "EXPLICIT":
        reference = builder.announced()  # 「공고일 기준」이나 문구 없음: 공고일. 찍힌 기준일을 확인하지 못했으면 공고일로 바꾸지 않음(리뷰 2026-10-22)
        if reference is not None and application:
            used = f"공고일({reference.isoformat()})"
    claimed = any((reading.answer.get(k) or {}).get("date") for k in ("announcedOn", "referenceDate"))
    if reference is None and (reading.answer["referenceRule"] == "EXPLICIT" or claimed):
        return None
    if reference is None:
        reference, used = fallback_reference(payload, today)
    note = None
    if application and used:
        builder.date_reason = f"{APPLICATION_DAY}: 신청하는 날이 사람마다 달라 {used}을 기준일로 썼습니다. {NO_REFERENCE_DATE}"
        note = f"{JUDGING_DATE_NOTE} 원문이 「신청일 기준」이라 신청하는 날마다 결과가 달라질 수 있어 {used}을 기준일로 썼습니다."
    elif used:
        builder.date_reason = f"원문에 공고일·기준일이 없어 {used}을 기준일로 썼습니다. {NO_REFERENCE_DATE}"
        note = f"{JUDGING_DATE_NOTE} 원문에 공고일·기준일이 없어 {used}을 기준일로 썼습니다."
    common, groups, preferences, notes = builder.build(reference)
    if note:
        notes.append(
            {
                "kind": "OTHER",
                "groupId": None,
                "text": f"{note} 나이·업력·폐업 기간처럼 기준일에 따라 달라지는 조건은 확인이 필요합니다.",
                "quote": None,
                "page": None,
            }
        )
    return repair(
        {
            "schema": "business-space-judgment.v1",
            "rawPostId": payload["rawPolicyId"],
            "rawVersion": payload["version"],
            "referenceDate": reference.isoformat(),
            "common": common,
            "groups": groups,
            "preferences": preferences,
            "notes": notes,
        }
    )
