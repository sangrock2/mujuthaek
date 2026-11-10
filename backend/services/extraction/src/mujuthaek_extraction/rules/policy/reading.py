"""정책 공고(창업지원·사업공간 모집) 글 읽기: AI 호출 한 번으로 자격 조건·공고일·우대·안내를 근거 문장과 함께 뽑습니다.

정책 공고는 PDF 없이 수집 이벤트의 글(payload.text: API 항목 + 원문 화면 본문)만 옵니다. AI는 판정 틀을 직접 쓰지 않고
틀보다 단순한 중간 형식으로 답하고, 틀 변환·날짜 계산·지역 코드는 코드가 합니다(judgment/policy_frame.py). AI가 적은 근거 문장이
원문에 없거나 값이 근거 문장에 없으면 그 조건은 확인 필요가 됩니다(코드가 검사).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mujuthaek_extraction.model import ExtractionModel, ModelError, ModelRequest, StopReason

# policy/v5 (2026-10-23 사업공간 10건 채점 뒤):
# - spaceLocation(입주 공간 소재지)을 따로 받음(선택 칸이라 v4 답·녹화도 그대로 읽힘). 지원 지역·신청자 지역 제한·입주 뒤 이전 의무를 구분
# - quote는 원문의 연속된 한 구간만(머리말과 항목을 잇지 않음)
# - 공통 조건에 넣기 전에 모든 대상군(특히 예비창업자)이 갖출 수 있는지 확인, 예외 단서는 질문에 넣음
# - 자격 목록 안의 우대·가점 문장은 preferences로
# policy/v6 (2026-10-23 사업공간 10건 2차 채점 뒤):
# - 제외 문장을 질문으로 만들 때는 그 상태를 묻고 metWhen NO, 질문은 하나만(물음표 하나)
# - 「부적격」「신청 불가」「지원 제외」 문장은 제출서류·유의사항 단락 안에 있어도 조건으로
# - 제외 단락 항목은 대상군을 이름으로 지목하지 않으면 공통(group null)
# - 조건에 선택 칸 defined(질문이 기대는 분야·유형·자격의 범위가 본문에 있는지)를 받음(v5 답·녹화도 그대로 읽힘)
# - spaceLocation은 공간 한 곳마다 시도부터 가장 낮은 단계까지 이름 하나
# policy/v7 (2026-10-23 사업공간 10건 3차 채점 뒤, 온통청년 요약형 글):
# - 「소득·자산 기준 적용」처럼 기준이 있다는 문장은 금액이 없어도 조건(OTHER 질문)으로. 안내(notes)로만 두지 않음
# - 「예비창업자의 경우 …」「…인 경우」처럼 대상을 나누는 문장은 대상군(groups)으로 읽고 그 조건을 그 대상군에
# - 신청자 지역(REGION)은 지금 사는 곳·지금 사업장이 있는 곳만. 「…에 사업장을 두고자 하는」「이전 가능한」「입주 후 전입」은 OBLIGATION
# - 질문은 그 질문만 읽고 답할 수 있게: 「모집분야」「제외 업종」처럼 다른 곳을 가리키면 목록을 질문에 넣음
# - 우대는 문장이 대상군을 지목할 때만 group, 아니면 null
# policy/v8 (2026-10-23 사업공간 4차 채점 뒤):
# - 「신청일 기준」「신청일 현재」「접수일 기준」은 referenceRule APPLICATION(신청하는 날이 사람마다 달라 코드가 대신 정한 날짜를 쓰고
#   기준일에 기대는 조건은 확인 필요). v7 답·녹화의 NONE·ANNOUNCEMENT·EXPLICIT도 그대로 읽힘
PROMPT_VERSION = "policy/v8"
CALL_NAME = "policy_reading"
MAX_TEXT = 60000  # 글이 이보다 길면 앞부분만 보냅니다(수집기가 20만 자까지 줌). 잘렸으면 모든 조건을 확인 필요로
MAX_OUTPUT_TOKENS = 12000

KINDS = [
    "AGE",  # 만 나이 (예비창업자는 본인, 기업은 대표자)
    "REGION",  # 주소지·사업장 소재지
    "PRE_FOUNDER",  # 사업자가 아니어야 함 (예비창업자)
    "REGISTERED",  # 사업자여야 함
    "BUSINESS_AGE",  # 업력 (창업 N년 이내·미만, 날짜 범위)
    "NO_RECENT_CLOSURE",  # 최근 폐업 이력이 없어야 함
    "CLOSURE_REQUIRED",  # 폐업 경험이 있어야 함 (재창업)
    "REVENUE",  # 매출액
    "INDUSTRY_EXCLUDE",  # 제외 업종
    "INDUSTRY_ONLY",  # 대상 업종
    "STATUS",  # 해당해야 하는 유형 (중소기업·여성·소상공인 …)
    "EXCLUDED_STATUS",  # 해당하면 안 되는 신청 제외 사유 (체납·채무불이행 …)
    "OTHER",  # 위로 못 담는 조건 (질문으로)
]
STATUS_CODES = [
    "SME",
    "WOMAN",
    "SMALL_BUSINESS",
    "VENTURE_COMPANY",
    "SOCIAL_VENTURE",
    "DISABLED",
    "ONE_PERSON_CREATIVE",
    "STUDENT",
    "SOCIAL_ENTERPRISE",
    "PRE_SOCIAL_ENTERPRISE",
    "SOCIAL_COOPERATIVE",
    "VILLAGE_ENTERPRISE",
    "SELF_SUFFICIENCY_ENTERPRISE",
    "CAREER_BREAK_WOMAN",
    "NATIONAL_MERIT",
]
EXCLUDED_CODES = [
    "CREDIT_DELINQUENT",
    "TAX_ARREARS",
    "CLAWBACK_UNPAID",
    "PROGRAM_SANCTION",
    "BUSINESS_SUSPENDED",
    "WAGE_ARREARS",
    "SUBSIDY_EXCLUDED",
]


def _nullable(kind: str) -> dict[str, Any]:
    return {"type": [kind, "null"]}


def _enum_or_null(values: list[str]) -> dict[str, Any]:
    return {"type": ["string", "null"], "enum": [*values, None]}


def _dated() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["date", "quote"],
        "properties": {"date": _nullable("string"), "quote": _nullable("string")},
    }


CONDITION = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "group",
        "anyOf",
        "option",
        "kind",
        "minAge",
        "maxAge",
        "regionNames",
        "regionBasis",
        "years",
        "yearsRule",
        "openedFrom",
        "openedTo",
        "closedYears",
        "closedFrom",
        "closedTo",
        "revenueYear",
        "revenueMinWon",
        "revenueMaxWon",
        "industryCodes",
        "statusCodes",
        "excludedCodes",
        "question",
        "metWhen",
        "quote",
    ],
    "properties": {
        "group": _nullable("string"),
        "anyOf": _nullable("string"),
        "option": _nullable("string"),
        "kind": {"type": "string", "enum": KINDS},
        "minAge": _nullable("integer"),
        "maxAge": _nullable("integer"),
        "regionNames": {"type": "array", "items": {"type": "string"}},
        "regionBasis": _enum_or_null(["RESIDENCE", "BUSINESS_SITE", "RESIDENCE_OR_BUSINESS_SITE"]),
        "years": _nullable("number"),
        "yearsRule": _enum_or_null(["WITHIN", "UNDER", "AT_LEAST", "OVER"]),
        "openedFrom": _nullable("string"),
        "openedTo": _nullable("string"),
        "closedYears": _nullable("number"),
        "closedFrom": _nullable("string"),
        "closedTo": _nullable("string"),
        "revenueYear": _nullable("integer"),
        "revenueMinWon": _nullable("integer"),
        "revenueMaxWon": _nullable("integer"),
        "industryCodes": {"type": "array", "items": {"type": "string"}},
        "statusCodes": {"type": "array", "items": {"type": "string", "enum": STATUS_CODES}},
        "excludedCodes": {"type": "array", "items": {"type": "string", "enum": EXCLUDED_CODES}},
        "question": _nullable("string"),
        "metWhen": _enum_or_null(["YES", "NO"]),
        "quote": {"type": "string"},
        # 선택 칸(v6): 필수로 두면 v5 답·녹화가 형식 검사에 걸림. false면 그 조건은 확인 필요(judgment/policy_frame.py)
        "defined": _nullable("boolean"),
    },
}

OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["relevant", "announcedOn", "referenceRule", "referenceDate", "supportRegions", "groups", "conditions", "preferences", "notes"],
    "properties": {
        "relevant": {"type": "boolean"},
        "announcedOn": _dated(),
        "referenceRule": {"type": "string", "enum": ["ANNOUNCEMENT", "EXPLICIT", "APPLICATION", "NONE"]},
        "referenceDate": _dated(),
        "supportRegions": {
            "type": "object",
            "additionalProperties": False,
            "required": ["names", "quote"],
            "properties": {"names": {"type": "array", "items": {"type": "string"}}, "quote": _nullable("string")},
        },
        # 선택 칸(v5): 필수로 두면 v4 답·녹화가 형식 검사에 걸림. 엄격 모드에서는 null 허용 필수 칸이 됨(strict_schema)
        "spaceLocation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["names", "quote"],
            "properties": {"names": {"type": "array", "items": {"type": "string"}}, "quote": _nullable("string")},
        },
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "name", "quote"],
                "properties": {"key": {"type": "string"}, "name": {"type": "string"}, "quote": {"type": "string"}},
            },
        },
        "conditions": {"type": "array", "items": CONDITION},
        "preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "group", "effect", "points", "question", "quote"],
                "properties": {
                    "label": {"type": "string"},
                    "group": _nullable("string"),
                    "effect": {"type": "string", "enum": ["PRIORITY", "BONUS_POINTS", "OTHER"]},
                    "points": _nullable("number"),
                    "question": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "group", "text", "quote"],
                "properties": {
                    "kind": {"type": "string", "enum": ["RULE", "OBLIGATION", "SELECTION", "OTHER"]},
                    "group": _nullable("string"),
                    "text": {"type": "string"},
                    "quote": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """당신은 한국 창업지원·사업공간 모집 공고에서 신청 자격을 뽑는 도구입니다. 사용자가 준 공고 글만 근거로 씁니다.

공통 규칙
- 글에 없는 내용은 만들지 않습니다. 모르면 null이나 빈 목록으로 둡니다.
- 모든 항목의 quote에는 그 내용이 적힌 문장을 공고 글에서 글자 그대로 복사합니다(줄임·요약·고침 금지). 한 줄을 넘지 않게 필요한 부분만 복사합니다.
- quote는 원문에서 이어진 한 구간입니다. 제목 줄과 그 아래 항목, 떨어진 두 줄을 이어 붙이거나 「:」 등으로 합쳐 만들지 않습니다
  (「입주기업」 줄 아래 「- 창업 3년 이내 기업」이 있으면 quote는 「창업 3년 이내 기업」).
- 날짜는 YYYY-MM-DD로 씁니다. 금액은 원 단위 정수입니다(10억원 → 1000000000).
- 같은 내용을 여러 번 쓰지 않습니다. API 항목 줄과 원문 화면 본문에 같은 조건이 있으면 한 번만 씁니다.

relevant: 실제로 창업 지원(자금·공간·보육 등)이나 사업 공간 입주 모집 공고면 true, 아니면 false.

announcedOn: 공고 게시일(모집공고일). 본문 끝·머리의 「2026년 10월 07일」 같은 공고 날짜. 접수 시작일은 공고일이 아닙니다. 없으면 null.
referenceRule / referenceDate: 자격 판단 기준일 문구.
- 「공고일 기준」「모집공고일 현재」 → ANNOUNCEMENT (referenceDate는 null)
- 「기준일: '26.1.22.」처럼 다른 날짜가 찍혀 있으면 → EXPLICIT, referenceDate에 그 날짜
- 「신청일 기준」「신청일 현재」「접수일 기준」처럼 신청하는 날이 기준이면 → APPLICATION (referenceDate는 null)
- 기준일 문구가 없으면 → NONE

지역은 세 가지를 구분합니다.
1) supportRegions: 이 사업을 지원하는 지역(사업 대상 지역). names는 「부산광역시」「대구광역시 남구」「충청권」처럼 글에 적힌 지역 이름,
   quote는 그 지역이 적힌 문장. 「전국」이라고 적혀 있으면 names ["전국"]. 지역이 적혀 있지 않으면 names 빈 목록·quote null(짐작 금지).
   입주 공간·센터의 주소, 주관 기관이 있는 곳, 입주 뒤 옮겨야 할 주소는 지원 지역이 아닙니다.
2) spaceLocation: 사업공간 모집이면 입주할 공간(센터·건물)이 있는 곳. names는 「경기도 화성시」「충청북도 청주시 흥덕구」처럼 글에 적힌
   공간 주소의 시도·시군구 이름, quote는 그 주소가 적힌 문장. 공간 주소가 없거나 사업공간 모집이 아니면 names 빈 목록·quote null.
   공간 한 곳은 시도부터 가장 낮은 단계까지 이름 하나로 씁니다(「경기도 고양시 일산동구」. 「경기도」「고양시」「일산동구」로 나누지 않음).
   공간이 여러 곳이면 공간마다 이름 하나씩(「서울특별시 광진구」「서울특별시 강남구」), quote는 첫 공간 주소 문장.
3) 신청자 지역 제한(거주지·사업장 소재지가 그 지역이어야 신청 가능)은 conditions의 REGION입니다. REGION은 지금 사는 곳·지금
   사업장이 있는 곳을 요구하는 문장만입니다. 공간 소재지나 「입주 후 본점(사업장)을 센터 주소로 이전」 같은 입주 뒤 이전 의무,
   「○○시 내 사업장을 두고자 하는」「본점을 이전 가능한」「입주 후 전입」처럼 앞으로 둘·옮길 곳은 지역 제한이 아니라 notes(OBLIGATION)입니다.

groups: 신청 분야·부문이 나뉘면(예비창업자 / 초기 창업기업, 일반 / 여성 분야, 4인실 / 6인실은 자격이 같으면 나누지 않음) 하나씩. key는 짧은 영문 소문자.
자격이 나뉘지 않으면 빈 목록.

conditions: 신청 자격 조건 하나씩. group은 그 조건이 속한 groups의 key, 모두에게 공통이면 null.
- 「A 또는 B」처럼 여러 길 중 하나면 그 길들의 조건에 anyOf로 같은 문자열을 넣고, 길마다 option에 다른 문자열을 넣습니다.
  한 길이 조건 여러 개로 이뤄지면(「10년 이내 신산업 분야 창업기업」 = 업력 10년 이내 그리고 신산업 분야) 그 조건들의 option을 같게 둡니다.
  예: 「7년 이내 창업기업 또는 10년 이내 신산업 분야 창업기업」 → (anyOf "a", option "1") 7년 이내 / (anyOf "a", option "2") 10년 이내 /
  (anyOf "a", option "2") 신산업 분야. 여러 길이 아니면 anyOf·option 모두 null.
  모집 대상이 쉼표·「및」·「또는」으로 서로 다른 대상을 나열하면(「7년 이내 스타트업, 「벤처기업법」에 따른 벤처기업」) 그 대상 하나하나가
  다른 길입니다. 나열된 대상 하나만의 조건을 모든 신청자에게 거는 공통 조건으로 두지 않습니다.
- 「제외대상」「신청 제외 대상」 같은 제외 단락의 항목은 문장이 특정 대상군을 이름으로 지목하지 않으면 group null(공통)입니다
  (「…이력이 있는 기업」처럼 「기업」이라는 말만으로 기창업자 대상군에 넣지 않음).
- 「부적격」「신청 불가」「지원 제외」「입주 불가」 문장은 제출서류·유의사항·안내 단락 안에 있어도 신청 자격 조건으로 읽습니다
  (「확인서를 발급받을 수 없는 기업은 입주 부적격」 → 그 대상군의 조건).
- group을 null(공통)로 두기 전에 모든 대상군, 특히 예비창업자(사업자 등록 전)가 그 조건을 갖출 수 있는지 확인합니다. 업력·매출·
  사업자 등록·본사·지점·연구소·졸업기업처럼 이미 사업 중인 기업만 갖출 수 있는 조건은 그 대상군(기창업자 등)에 넣습니다.
  「예비창업자의 경우 …」처럼 한 대상군에만 해당한다고 적힌 문장은 그 대상군에 넣습니다.
- 「예비창업자의 경우 …」「법인인 경우 …」「…에 해당하는 경우」처럼 대상을 나누는 문장이 있으면 그 대상을 groups에 하나씩 두고
  (다른 대상이 따로 적혀 있지 않으면 나머지 신청자도 대상군 하나로) 그 문장의 조건을 그 대상군에 넣습니다. 안내(notes)로만 두지 않습니다.
  그 문장이 입주 뒤 할 일(「입주 후 15일 이내 사업자등록」)이면 그 대상군의 notes(OBLIGATION)이고, 대상군 나눔은 그대로 둡니다.
- 「소득·자산 기준 적용」「소득 기준 충족자」「○○년 기준 적용(금액 변동 가능)」처럼 소득·자산·자격 기준이 있다고만 적고 금액이
  없어도 그 기준은 조건입니다. OTHER로 두고 question에 「공고의 소득·자산 기준을 충족하나요?」처럼 묻습니다(metWhen YES,
  defined false). 안내(notes)로만 두지 않습니다.
- 조건 문장에 예외 단서(「다만 …은 신청 가능」「단, …」「…의 경우 신청 가능」)가 붙어 있으면 그 조건은 OTHER로 두고, question에
  예외를 넣어 묻습니다(예: 「국세·지방세를 체납 중인가요? 분납을 성실히 하고 있으면 '아니오'」). 예외를 빼고 코드로만 담지 않습니다.
- kind별로 채울 칸(나머지는 null·빈 목록):
  AGE: minAge, maxAge (만 나이, 「만 39세 이하」→ maxAge 39, 「만 40세 미만」→ maxAge 39)
  REGION: regionNames(「서울특별시」「대구광역시 남구」처럼 지역 이름),
    regionBasis(주소지 RESIDENCE / 사업장 BUSINESS_SITE / 둘 중 하나 RESIDENCE_OR_BUSINESS_SITE)
  PRE_FOUNDER: 사업자 등록이 없어야 함(예비창업자). REGISTERED: 사업자(개인·법인)여야 함
  BUSINESS_AGE: 업력. 공고에 날짜 범위가 찍혀 있으면 openedFrom·openedTo에 그대로. 연수만 있으면 years와 yearsRule
    (「N년 이내」 WITHIN, 「N년 미만」「N년이 지나지 않은」 UNDER, 「N년 이상」 AT_LEAST, 「N년 초과」 OVER)
  NO_RECENT_CLOSURE: 「최근 N년 이내 폐업한 자 제외」 → closedYears 또는 closedFrom·closedTo
  CLOSURE_REQUIRED: 폐업 경험이 있어야 하는 재창업 → closedYears 또는 closedFrom·closedTo
  REVENUE: revenueYear(「전년도」면 공고 연도 − 1), revenueMinWon, revenueMaxWon
  INDUSTRY_EXCLUDE / INDUSTRY_ONLY: industryCodes는 공고에 한국표준산업분류 숫자 코드가 적혀 있을 때만. 업종 이름만 있으면 OTHER로
  STATUS: statusCodes. 대상이 그 유형이어야 할 때만(SME 중소기업, WOMAN 여성, SMALL_BUSINESS 소상공인, VENTURE_COMPANY 벤처기업,
    SOCIAL_VENTURE 소셜벤처, DISABLED 장애인, ONE_PERSON_CREATIVE 1인 창조기업, STUDENT 대학생·대학원생, SOCIAL_ENTERPRISE 사회적기업,
    PRE_SOCIAL_ENTERPRISE 예비사회적기업, SOCIAL_COOPERATIVE 사회적협동조합, VILLAGE_ENTERPRISE 마을기업, SELF_SUFFICIENCY_ENTERPRISE 자활기업,
    CAREER_BREAK_WOMAN 경력단절여성, NATIONAL_MERIT 국가유공자)
  EXCLUDED_STATUS: excludedCodes. 신청 제외 대상 중 코드가 있는 것(CREDIT_DELINQUENT 채무불이행, TAX_ARREARS 국세·지방세 체납,
    CLAWBACK_UNPAID 환수금 미반환, PROGRAM_SANCTION 정부·창업지원사업 참여제한 제재, BUSINESS_SUSPENDED 휴업, WAGE_ARREARS 임금 체불 명단,
    SUBSIDY_EXCLUDED 보조사업 수행 배제). 「신청 제외」「신청 불가」로 적힌 문장에서만 고릅니다(「적격여부 검토」 같은 심사 절차 목록에서
    뽑지 않음). 한 문장에 코드가 있는 사유와 없는 사유가 섞이면 있는 것만 코드로, 나머지는 OTHER로. 코드가 없는 제외 사유는 OTHER로
  OTHER: 위로 못 담는 조건. question에 예/아니오로 답할 질문, metWhen은 「예」면 충족 YES, 「예」면 신청 불가 NO.
    제외 문장(제외 단락 항목, 「…은 제외」「신청 불가」)을 질문으로 만들 때는 그 제외 상태를 그대로 묻고 metWhen NO입니다
    (「신청일 현재 휴업 또는 폐업 중인 기업」(제외대상) → 「지금 휴업이나 폐업 상태인가요?」 NO. 「폐업 상태인가요?」 YES로 쓰지 않음).
    질문은 하나만 씁니다(물음표 하나). 「…인가요? 단, …이면 신청할 수 있나요?」처럼 두 질문을 잇지 않고 예외는 답 방향으로 적습니다.
    질문만 읽고 답할 수 있게 씁니다. 「모집분야에 해당하나요?」「지원 제외 업종인가요?」처럼 다른 곳을 가리키면 그 분야·업종 목록을
    질문에 넣습니다(「모집분야(AI, 전기전자, 콘텐츠 등)에 해당하나요?」).
  defined: OTHER·STATUS 질문이 기대는 분야·업종·유형·자격 이름(「신산업 분야」「유망업종」「입점자격」)의 범위가 공고 글에 적혀 있으면 true,
    첨부·별도 공고문에만 있거나(「공고문 4page 참조」) 어디에도 적혀 있지 않으면 false. 법령 조항이 적혀 있으면 true. 그 밖의 조건은 null
- 선정 뒤에 할 일(입주 후 본점 이전, 협약 기간 안 창업)과 마감·입주 전까지 하면 되는 일(「마감일 전까지 사업자등록 必」)은
  지금 갖춰야 하는 자격이 아니라 notes(OBLIGATION)입니다. 질문으로 만들면 아직 하지 않은 사람이 떨어집니다.

preferences: 가점·우선 선정·서류평가 면제. 자격이 아닙니다. question은 「예」면 우대에 해당하는 질문. 점수가 적혀 있으면 points.
group은 우대 문장이 대상군을 이름으로 지목할 때만 넣고, 아니면 null(모든 신청자). 같은 우대를 두 번 쓰지 않습니다.
신청 자격 목록 안에 섞여 있어도 「우대」「가점」「우선 선정」 문장은 conditions가 아니라 preferences에 넣습니다.
notes: 판정하지 않고 보여 줄 문장(신청 방법·중복 신청 금지 RULE, 선정 의무 OBLIGATION, 평가 절차 SELECTION, 그 밖의 OTHER)."""


@dataclass(frozen=True)
class PolicyReading:
    answer: dict[str, Any]
    truncated: bool  # 글이 MAX_TEXT보다 길어 앞부분만 읽음


def read_policy(payload: dict[str, Any], model: ExtractionModel) -> PolicyReading:
    """수집 이벤트 payload의 글을 AI로 읽습니다. 답이 형식에 맞지 않으면 ModelError(transient=False)."""
    text = str(payload.get("text") or "")
    truncated = len(text) > MAX_TEXT or bool(payload.get("textKey"))
    request = ModelRequest(
        prompt_version=PROMPT_VERSION,
        call_name=CALL_NAME,
        system=SYSTEM,
        user=text[:MAX_TEXT],
        instructions=f"분류: {payload.get('field')}. 위 공고 글에서 신청 자격·공고일·우대·안내를 형식대로 뽑아 주세요.",
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
    return PolicyReading(answer, truncated)
