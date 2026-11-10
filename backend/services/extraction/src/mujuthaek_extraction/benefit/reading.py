"""혜택 정책 글 읽기: AI 호출 한 번으로 관련성·요약·지원 내용·일정·신청 방법·서류·문의처·자격 조건을 근거 문장과 함께 뽑습니다.

AI는 계약 모양(policy.extracted)을 직접 쓰지 않고 칸이 고정된 중간 형식으로 답합니다. 금액은 원 단위 정수로 받고 만 원 변환·
지역 이름 → 코드·근거 확인은 코드가 합니다(benefit/build.py). 근거 문장이 원문에 없거나 값이 근거에 없으면 그 값을 쓰지 않습니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mujuthaek_extraction.model import ExtractionModel, ModelError, ModelRequest, StopReason

PROMPT_VERSION = "benefit/v5"  # v5(2026-10-29): 무주택(주택 소유)과 노숙(홈리스)을 나눔
CALL_NAME = "benefit_reading"
MAX_TEXT = 60000  # 글이 이보다 길면 앞부분만 보냅니다. 잘렸으면 TEXT_TRUNCATED
MAX_OUTPUT_TOKENS = 8000

TYPES = [
    "AGE",
    "MARITAL",
    "NEWLYWED_YEARS",
    "CHILDREN",
    "PREGNANCY",
    "HOUSEHOLD_TYPE",
    "WELFARE_STATUS",
    "SPECIAL_STATUS",
    "INCOME_MEDIAN_PCT",
    "INCOME_AMOUNT",
    "ASSET_AMOUNT",
    "RESIDENCE",
    "RESIDENCE_MONTHS",
    "MOVE_IN",
    "HOMELESS",
    "HOMELESS_YEARS",
    "LEASE",
    "FIRST_HOME",
    "EMPLOYMENT",
    "EDUCATION",
    "OCCUPATION",
    "WORKPLACE",
    "EXCLUSIVE",
    "PRIORITY",
    "OTHER",
]
SUPPORT_KINDS = ["RENT", "DEPOSIT_LOAN", "PURCHASE_LOAN", "HOUSING_SUPPLY", "MOVE_IN_GRANT", "CASH", "OTHER"]


def _n(kind: str) -> dict[str, Any]:
    return {"type": [kind, "null"]}


def _strings() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


CONDITION = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "group",
        "type",
        "rawText",
        "evidence",
        "confidence",
        "min",
        "max",
        "values",
        "basis",
        "regionNames",
        "months",
        "amountMinWon",
        "amountMaxWon",
        "amountPer",
        "assetKind",
        "leaseKinds",
        "depositMaxWon",
        "monthlyMaxWon",
    ],
    "properties": {
        "group": {"type": "integer", "minimum": 1},
        "type": {"enum": TYPES},
        "rawText": {"type": "string"},
        "evidence": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "min": _n("number"),
        "max": _n("number"),
        "values": _strings(),
        "basis": {"enum": ["HOUSEHOLD", "PERSONAL", "PERSON", None]},
        "regionNames": _strings(),
        "months": _n("integer"),
        "amountMinWon": _n("integer"),
        "amountMaxWon": _n("integer"),
        "amountPer": {"enum": ["YEAR", "MONTH", None]},
        "assetKind": {"enum": ["TOTAL", "CAR", "REAL_ESTATE", "FINANCIAL", None]},
        "leaseKinds": _strings(),
        "depositMaxWon": _n("integer"),
        "monthlyMaxWon": _n("integer"),
    },
}
SUPPORT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "amountMaxWon", "amountPer", "months", "ratePct", "rawText", "evidence"],
    "properties": {
        "kind": {"enum": SUPPORT_KINDS},
        "amountMaxWon": _n("integer"),
        "amountPer": {"enum": ["ONCE", "MONTH", "YEAR", None]},
        "months": _n("integer"),
        "ratePct": _n("number"),
        "rawText": {"type": "string"},
        "evidence": {"type": "string"},
    },
}
OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relevant", "relevanceReason", "summary", "supports", "schedule", "howToApply", "documents", "contact", "conditions"],
    "properties": {
        "relevant": {"type": "boolean"},
        "relevanceReason": {"type": "string"},
        "summary": _n("string"),
        "supports": {"type": "array", "items": SUPPORT},
        "schedule": {
            "type": "object",
            "additionalProperties": False,
            "required": ["applyStart", "applyEnd", "applyAlways", "businessStart", "businessEnd", "rawText"],
            "properties": {
                "applyStart": _n("string"),
                "applyEnd": _n("string"),
                "applyAlways": {"type": "boolean"},
                "businessStart": _n("string"),
                "businessEnd": _n("string"),
                "rawText": _n("string"),
            },
        },
        "howToApply": _n("string"),
        "documents": _strings(),
        "contact": _n("string"),
        "conditions": {"type": "array", "items": CONDITION},
    },
}

SYSTEM = """당신은 한국 공공 지원 정책(청년·신혼·주거 지원 등) 글에서 서비스에 보여 줄 값을 뽑는 도우미입니다.
이 서비스는 이사·주거 혜택(월세·보증금·이자·주택 구입·임대주택·전입 정착 지원)을 찾는 사람에게 정책을 보여 줍니다.
글에 적힌 것만 씁니다. 짐작하지 않습니다. 모르면 null·빈 목록으로 둡니다.

공통 규칙
- evidence는 원문에서 그대로 복사한 이어진 한 구간입니다(바꾸거나 잇거나 줄이지 않음). rawText는 화면에 보여 줄 짧은 원문 표현입니다.
- 금액은 원 단위 정수로 씁니다(「20만원」→ 200000, 「1억원」→ 100000000, 「6천만원」→ 60000000, 「2.5억원」→ 250000000).
- 날짜는 YYYY-MM-DD로 씁니다. 연도가 없으면 null입니다.

relevant: 주거·이주 혜택(월세·임대료, 전월세 보증금·대출 이자, 주택 구입 대출·이자, 임대주택·빈집 제공, 전입·정착·이사 지원금)이면 true.
상담·교육·정보 안내뿐이거나 주거와 관계없는 지원이면 false. relevanceReason에 한 문장으로 이유를 씁니다.
summary: 화면에 보일 한 줄 요약(80자 안, 「누구에게 무엇을 얼마나」).

supports: 지원 내용 하나씩. kind는 RENT(월세·임대료), DEPOSIT_LOAN(전월세 보증금 대출·이자), PURCHASE_LOAN(주택 구입 대출·이자),
HOUSING_SUPPLY(임대주택·빈집 등 집 제공), MOVE_IN_GRANT(전입·정착·이사 지원금), CASH(그 밖의 현금), OTHER(그 밖).
amountMaxWon은 한 번에 받는 최대 금액(원), amountPer는 그 금액의 기간(ONCE 한 번, MONTH 매월, YEAR 매년), months는 지원 개월 수,
ratePct는 지원 비율(이자·임대료의 50%면 50, 「연 3.5% 이자 지원」이면 3.5). 대출 상품(DEPOSIT_LOAN·PURCHASE_LOAN)은 대출 한도를
amountMaxWon에 넣습니다(「구입자금 최대 4억원」→ 400000000, amountPer ONCE). 한도가 여러 개면(구입 4억·전세 2.4억) 지원 하나씩.

schedule: 신청 시작·마감(applyStart·applyEnd), 상시 모집이거나 「예산 소진 시까지」면 applyAlways true, 사업 기간(businessStart·businessEnd),
rawText는 기간 원문. howToApply는 신청 방법 요약 한 문장, documents는 제출 서류 이름 목록, contact는 문의처(기관·전화).

conditions: 신청 자격 조건 하나씩. 조건이 없으면 빈 목록(「제한 없음」 줄을 만들지 않음).
- group: 같은 번호끼리는 「또는」, 다른 번호끼리는 「그리고」. 「신혼부부 또는 한부모가족」은 두 조건을 같은 번호로.
  글에 「또는」 관계가 없는 조건은 모두 서로 다른 번호입니다(모든 조건을 같은 번호로 두지 않음).
- 전형·유형마다 조건이 다르면(「청년 전형은 미혼·연소득 4,500만 원 이하, 부부 전형은 부부합산 1억 원 이하」, 「구입은 순자산 5억,
  전세는 3억」) 전형별 값도 type으로 담고, 같은 type끼리는 같은 group에 둡니다(「미혼 또는 기혼」, 「4,500만 또는 1억」).
  rawText에 어느 전형의 값인지 적습니다(「청년 전형: 연소득 4,500만 원 이하」).
- 나이·거주·무주택·혼인·소득·자산은 판정에 꼭 필요한 값입니다. 원문에 있으면 빠뜨리지 말고 type으로 담습니다.
- confidence: 이 조건을 맞게 읽었다고 보는 정도(0~1).
- type별로 채울 칸(나머지는 null·빈 목록):
  AGE: min·max (만 나이. 「만 19~39세」→ 19, 39. 「만 40세 미만」→ max 39)
  MARITAL: values (SINGLE 미혼, MARRIED 기혼, NEWLYWED 신혼부부, ENGAGED 예비 신혼부부). NEWLYWED_YEARS: max (혼인 N년 이내)
  CHILDREN: min(자녀 수 이상)·max(막내 나이 이하). PREGNANCY: values (PRE_PARENT 예비부모·난임, PREGNANT 임신 중, BIRTH 출산·입양), months(출산 후 N개월 안)
  HOUSEHOLD_TYPE: values (SINGLE_PERSON, SINGLE_PARENT 한부모, GRANDPARENT 조손, MULTI_CHILD 다자녀,
    MULTICULTURAL 다문화, NK_DEFECTOR 북한이탈주민, EXTENDED 확대가족)
  WELFARE_STATUS: values (BASIC_LIVELIHOOD 기초생활수급, NEAR_POOR 차상위).
  SPECIAL_STATUS: values (DISABLED, VETERAN, ILLNESS, PROTECTED_YOUTH 자립준비청년, SOLDIER)
  INCOME_MEDIAN_PCT: max (기준중위소득 N% 이하), basis (HOUSEHOLD 가구, PERSONAL 본인)
  INCOME_AMOUNT: amountMinWon·amountMaxWon(원), amountPer (YEAR 연소득, MONTH 월소득), basis (HOUSEHOLD·PERSONAL. 「부부합산」은 HOUSEHOLD)
    「연소득 6천만원(부부합산 8천만원) 이하」처럼 기준이 둘이면 조건 두 개로(본인 PERSONAL 6천만, 부부 HOUSEHOLD 8천만) 같은 group에
  ASSET_AMOUNT: amountMaxWon, assetKind (TOTAL 총자산, CAR 자동차, REAL_ESTATE 부동산, FINANCIAL 금융)
  RESIDENCE: regionNames (지금 살아야 하는 지역 이름, 「대구광역시」「전북특별자치도 무주군」). RESIDENCE_MONTHS: months(거주 개월 이상), regionNames
  MOVE_IN: regionNames(전입할 지역), months(전입 후 N개월 안 신청). 지금 다른 곳에 살아도 전입하면 대상인 경우
  HOMELESS: basis (PERSON 본인 무주택, HOUSEHOLD 세대원 모두 무주택). HOMELESS_YEARS: min (무주택 N년 이상). FIRST_HOME: 생애 최초 주택 구입
    HOMELESS·HOMELESS_YEARS·FIRST_HOME은 주택 소유 여부(무주택·주택 보유·생애 최초 구입)를 말할 때만 씁니다.
    노숙·거리 생활·「일정한 주거 없이」·행려자·부랑인·쉼터나 시설 거주·주거 취약 같은 상태는 주택 소유가 아니므로 OTHER로 담습니다
    (영어 homeless는 노숙인 뜻이라 헷갈리기 쉬워요)
  LEASE: leaseKinds (MONTHLY 월세, JEONSE 전세), depositMaxWon(임차 보증금 상한), monthlyMaxWon(월세 상한)
    보증부 월세(보증금이 있는 월세)는 MONTHLY만. 글에 전세와 월세가 모두 대상이라고 적혀 있을 때만 둘 다 넣습니다
  EMPLOYMENT: values (EMPLOYED 재직, SELF_EMPLOYED 자영업, UNEMPLOYED 미취업, FREELANCER, DAILY_WORKER 일용, SHORT_TERM 단기, STARTUP 창업, OTHER)
  EDUCATION: values (BELOW_HIGH, HIGH_ENROLLED, HIGH_GRAD_EXPECTED, HIGH_GRAD, UNIV_ENROLLED, UNIV_GRAD_EXPECTED, UNIV_GRAD, GRADUATE, OTHER)
  OCCUPATION: values (FARMER, FISHER, LIVESTOCK, FORESTRY). WORKPLACE: values (SME 중소기업 재직), regionNames (직장 소재지)
  EXCLUSIVE: 중복 수혜 불가(rawText만). PRIORITY: 선정 우선순위·가점(rawText만, 자격 아님). OTHER: 위로 못 담는 조건(rawText만)
- 「…은 제외」「…인 자는 신청 불가」처럼 제외 문장은 뒤집어 담을 수 있으면 뒤집습니다(「주택을 소유한 자」 제외 → HOMELESS PERSON).
  뒤집을 수 없으면 OTHER로 두고 rawText에 「… 제외」로 씁니다.
- 「소득 기준 적용」처럼 기준이 있다고만 하고 숫자가 없으면 OTHER입니다. 숫자를 짐작하지 않습니다."""


@dataclass(frozen=True)
class BenefitReading:
    answer: dict[str, Any]
    truncated: bool
    model: str = "unknown"  # 답한 모델 (quality.model)


def read_benefit(payload: dict[str, Any], model: ExtractionModel) -> BenefitReading:
    """수집 이벤트 payload의 글을 AI로 읽습니다. 답이 형식에 맞지 않으면 ModelError(transient=False)."""
    text = str(payload.get("text") or "")
    truncated = len(text) > MAX_TEXT or bool(payload.get("textKey"))
    request = ModelRequest(
        prompt_version=PROMPT_VERSION,
        call_name=CALL_NAME,
        system=SYSTEM,
        user=text[:MAX_TEXT],
        instructions="위 정책 글에서 관련성·요약·지원 내용·일정·신청 방법·서류·문의처·자격 조건을 형식대로 뽑아 주세요.",
        output_schema=OUTPUT_SCHEMA,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    response = model.complete(request)
    if response.stop_reason is not StopReason.END:
        raise ModelError(f"정책 글 읽기가 끝나지 않았습니다: {response.stop_reason.value}", transient=False, code="INCOMPLETE")
    try:
        answer = json.loads(response.raw_text)
    except json.JSONDecodeError as error:
        raise ModelError("정책 글 읽기 답이 JSON이 아닙니다", transient=False, code="BAD_JSON") from error
    from jsonschema import Draft202012Validator

    errors = sorted(Draft202012Validator(OUTPUT_SCHEMA).iter_errors(answer), key=lambda e: list(e.absolute_path))
    if errors:
        raise ModelError(f"정책 글 읽기 답이 형식에 맞지 않습니다: {errors[0].message[:200]}", transient=False, code="BAD_SHAPE")
    return BenefitReading(answer, truncated, response.model_id or "unknown")
