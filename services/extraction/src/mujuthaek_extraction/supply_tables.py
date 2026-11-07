"""공급·가격 표는 코드가 행 단위로 옮기고, AI는 표마다 열의 의미만 답합니다(구조 방식, 2026-10-17 설계 검토 1번).

이전에는 AI가 공급표의 모든 행을 JSON으로 다시 썼습니다. 실측(2026-10-17 시험): 가격 128개짜리 인천 행복주택 표를 유료 모델이
10개만 남기고 멈췄고, 한 행의 두 번째 요금안·호실 일부를 빠뜨리거나 칸을 잘못 붙였습니다(모집 수 재현율 43~64%).

흐름
  1. candidates(): PDF 표 중 열 제목(intake/pdf_reader가 병합 칸에서 복원)에 공급·가격 낱말이 있고 숫자 행이 있는 표,
     그리고 첨부 엑셀 공급주택목록 시트(머리 행 아래 모든 행 — AI가 행을 옮겨 적지 않아 행 수 제한이 없음, 2026-10-20)
  2. mapping_request(): AI에 표마다 열의 의미(주택형·대상·전용면적·수량 종류·가격 종류·단위·요금안)만 묻습니다. 값은 적지 않습니다
  3. build_part(): 코드가 칸 값을 그대로 옮겨 AI 출력과 같은 모양의 공급 조각을 만듭니다. 인용은 원문 표 행(| 줄) 그대로라
     근거 검증(V2)을 똑같이 거칩니다. 병합 칸(칸 번호)으로 위 행에서 이어받는 값·여러 묶음이 함께 쓰는 모집 물량을 복원합니다
  4. link_locations(): 구조 호출이 만든 단지(locations)와 표의 단지 이름을 맞춰 locationId를 붙입니다
열 의미를 받지 못하거나 공급표가 없으면 None — 이전처럼 구조 호출이 공급 묶음까지 만듭니다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from mujuthaek_extraction.assemble.ai_output import CODE_ISSUES
from mujuthaek_extraction.assemble.conversion import SAME_AS_BASE, UNCHECKED, plan_directions
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.intake.pdf_reader import NUMERIC_VALUE
from mujuthaek_extraction.model.base import ModelRequest
from mujuthaek_extraction.rules.base import output_limit

CALL_NAME = "supply_tables"
# 출력 한도: 실측 최대 2,422(인천 4358, 시도 17건). 표 수에 따라 늘어 1.3배보다 조금 넉넉히 둡니다(이전 16,000).
# 잘리면 열 의미 없이 이전 방식(구조 호출이 공급까지)으로 돌아갑니다. 설정 EXTRACTION_MAX_OUTPUT_TOKENS의 supply_tables로 바꿀 수 있습니다
MAX_OUTPUT_TOKENS = 4_000
# 표가 많으면 한도를 늘립니다(2026-10-24 일곱 번째 채점: 단지가 많은 공고의 표 10개 열 의미가 4,000토큰에서 잘려 답 전체를 버림 →
# 코드가 표를 옮기는 경로가 꺼지고 공급 묶음 72개 중 16개만 나옴). 표 하나에 약 700토큰, 상한 16,000
TOKENS_PER_TABLE = 700
MAX_OUTPUT_TOKENS_CAP = 16_000
# v8(2026-11-07 23건 대조): 요약표에만 있는 금액 열(단지별 「월평균임대료」, bmc-72·106)은 SUPPLY로 이름 칸과 금액 열만,
#   행마다 소득 구간이 다른 임대조건표(bmc-75 「[39A] 구간별 임대조건」, 첫 행 구간을 열 전체 대상으로 답해 표 4개 96값이 빠짐)는 그 칸을 TARGET_GROUP.
# v7(2026-10-24): 표 전체가 특정 대상의 요금(「상한 임대조건」「수급자 등」「적용 대상자」)이면 모든 가격 열 targetGroup에 그 대상,
#   주택형이 표 제목에만 있으면 프로그램이 그 표 행에 붙인다는 안내.
# v6(2026-10-23): 보증금을 내린 전환안·무보증금 월세 열은 CONVERSION_DEPOSIT_DOWN, 적용 대상이 적혀 있으면 targetGroup.
# v5(2026-10-20): 표마다 절 제목. v4: 주소 칸 ADDRESS. v3: 행마다 다른 요금안 칸 PLAN_NAME. v2: 첨부 엑셀 공급주택목록 표, 공고문 요약표와 중복 방지 안내
PROMPT_VERSION = "supply_tables/v8"
# 옵션 가격표의 절 제목(가장 안쪽 제목). 본 가격표 제목에도 「발코니 확장비 별도」가 붙으므로 주택가격·공급금액·별도가 있으면 아님
# (실측 2026-10-20 LH 대전대동2 「5. 발코니 확장 및 추가선택품목 › ■ 발코니 확장 안내」 표를 AI가 공급표로 답해 확장비 계약금·잔금 32개가
#  59A 등의 계약금·잔금으로 자동 게시됨. 수집 공고 72건의 후보 표 182개 중 이 규칙에 맞는 것은 옵션 표 3개뿐)
OPTION_SECTION = re.compile(r"발코니\s*확장|선택\s*품목|옵션")
MAIN_PRICE_SECTION = re.compile(r"주택\s*가격|분양\s*가격|공급\s*금액|임대\s*조건|별도")


def option_table(table: Table) -> bool:
    inner = table.section.split(" › ")[-1]
    return bool(OPTION_SECTION.search(inner)) and not MAIN_PRICE_SECTION.search(inner)


MAX_TABLES = 40
SUPPLY_HINT = re.compile(r"보증금|임대료|월세|분양|가격|전용|면적|호수|세대\s*수|모집|공급|공가|예비|deposit|rent|price|area|units", re.I)
UNIT_FLOOR = re.compile(r"(\d{1,2})\d{2}")  # 3~4자리 숫자 호수의 앞자리 = 층 (지하·문자 호수는 건드리지 않음)
SUBTOTAL = re.compile(r"^(?:합\s*계|소\s*계|총\s*계|계|합계)$")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
UNIT_IN_TITLE = re.compile(r"\((천원|만원|원)\)|(천원|만원)")
KEY_MEANINGS = ("COMPLEX", "ADDRESS", "BUILDING", "HOUSING_TYPE", "UNIT", "FLOOR", "TARGET_GROUP")
COUNT_KINDS = ["TOTAL_HOUSING", "OFFERED", "RESERVE", "CURRENT_VACANCIES", "WAITLIST"]
PRICE_KINDS = ["DEPOSIT", "MONTHLY_RENT", "SALE_PRICE", "CONTRACT_PAYMENT", "BALANCE", "OTHER"]
STAGES = ["STANDARD", "CONVERSION_DEPOSIT_UP", "CONVERSION_DEPOSIT_DOWN", "BEFORE_SUPPORT", "AFTER_SUPPORT", "OTHER"]
MEANINGS = [*KEY_MEANINGS, "AREA_EXCLUSIVE", "COUNT", "PRICE", "CONVERSION_LIMIT", "PLAN_NAME", "IGNORE"]
# 실측(2026-10-17): 열 의미 답 10건 중 9건이 표 번호를 「표 3-1」「표 3-1 (3쪽)」로 적어 표를 못 찾고 이전 방식으로 돌아갔습니다
LABEL_NOISE = re.compile(r"^\s*표\s*|\s*\(\s*\d+\s*쪽\s*\)\s*$")
SIGN_CELL = re.compile(r"\(?\s*([+\-−])\s*\)?")  # 전환 구분 칸 「(+)」「(-)」
SUPPLY_COUNT_KINDS = {"OFFERED", "RESERVE", "WAITLIST", "CURRENT_VACANCIES"}
HOUSING_NUMBER = re.compile(r"\d+(?:\.\d+)?")
SPLIT_DECIMAL = re.compile(r"(\d)\.\s+(\d)")
ABOVE_LINES = 3  # 표 위에서 볼 글 줄 수
# 표 제목에만 있는 주택형(2026-10-24 채점: 「【31A】 구간별 임대조건」 표의 구간별 가격 18묶음이 주택형 없이 따로 남음).
# 짧은 제목 줄(※·- 같은 안내 표시로 시작하지 않음)의 주택형 낱말만 봅니다. 줄에 주택형이 여럿이면 정하지 않고 검수 이슈로 둡니다
TITLE_TYPE = re.compile(r"(?<![\d.A-Za-z])(\d{2,3}[A-Z]{1,2}\d?|\d{2,3}\s*형)(?![\d.A-Za-z])")
TITLE_CHARS = 40
NOTE_MARK = re.compile(r"^\s*[※*＊\-·•▶]")
TYPE_AMBIGUOUS = "SUPPLY_TYPE_AMBIGUOUS"
# 가격 열은 있는데 행마다 어느 주택형·대상의 금액인지 정할 칸(KEY_MEANINGS)이 하나도 없는 가격표. 예전엔 표 전체를 표시 없이 건너뛰었음
# (2026-11-07 23건 대조 bmc-75: 「[39A] 구간별 임대조건」처럼 행이 소득 구간이고 주택형이 표 제목에 있는 표 4개, 가격 96개가 검수 없이 빠짐)
PRICE_TABLE_UNREAD = "SUPPLY_PRICE_TABLE_UNREAD"
# 표 전체(또는 열)가 특정 대상의 요금임을 말하는 낱말(2026-10-24 채점: 「[주거급여 수급자가 아닌 경우] 상한 임대조건」 표가 대상 없는
# 기본 요금으로 그 주택형에 붙음). 이런 표·열의 가격을 AI가 대상 없이 STANDARD로 답하면 기본 요금 자리에 두지 않고 보류합니다.
# 「분양가상한제」는 대상 낱말이 아닙니다
RESTRICTED_PRICE = re.compile(r"(?<!분양가)(?<!분양가 )상한(?!\s*제)|수급자|적용\s*대상|해당자에\s*한|에\s*한하여|에\s*한함|만\s*해당|만\s*적용")
SCOPE_UNCERTAIN = "PRICE_SCOPE_UNCERTAIN"
# 대상 한정 낱말을 찾을 표 위 글(2026-10-24 네 번째 채점: 표 위 입지 설명 「「경제자유구역…법」 제2조…(산업단지 근로자인 경우에만 해당)에
# 건설되거나」의 「만 해당」에 걸려 임대조건 12묶음이 통째로 숨음). 요금을 말하는 줄만 보고, 법령 인용 줄은 보지 않습니다
PRICE_TITLE_WORDS = re.compile(r"임대\s*조건|임대료|요금|보증금|월\s*세|가격|분양가|전환")
LAW_TEXT = re.compile(r"「[^」]*법[^」]*」|제\s*\d+\s*조")
# 병합된 한 칸의 수량을 여러 공급 행이 나눠 가짐: 행마다 그 수 전체로 보이므로(2026-10-24 채점: 49형 두 행이 「금회 모집 60」을 둘 다 가져
# 합이 120으로 보임) 표의 합계 행이 그 칸을 한 번만 센 합과 같을 때만 그대로 두고, 아니면 그 묶음들을 보류합니다
COUNT_MERGED = "COUNT_MERGED_AMBIGUOUS"
# 전환안 방향 검산(2026-10-24 세 번째 채점: 부호 「(+)」만 보고 기본 보증금보다 줄어든 감액안을 증액안으로 둠). assemble.conversion
DIRECTION_CORRECTED = "CONVERSION_DIRECTION_CORRECTED"  # 숫자로 분명해 고침(표시만)
DIRECTION_UNCERTAIN = "CONVERSION_DIRECTION_UNCERTAIN"  # 숫자로도 정할 수 없음(그 묶음 가격 보류)


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


MAPPING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tables"],
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["table", "role", "rowUnit", "complex", "columns"],
                "properties": {
                    "table": {"type": "string", "minLength": 1},
                    "role": {"enum": ["SUPPLY", "OTHER"]},
                    "rowUnit": {"enum": ["HOUSING_TYPE", "HOUSING_UNIT", "BUILDING", "OTHER"]},
                    "complex": _nullable({"type": "string", "minLength": 1}),
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["column", "meaning", "countKind", "priceKind", "unit", "plan", "priceStage", "targetGroup"],
                            "properties": {
                                "column": {"type": "integer", "minimum": 1},
                                "meaning": {"enum": MEANINGS},
                                "countKind": _nullable({"enum": COUNT_KINDS}),
                                "priceKind": _nullable({"enum": PRICE_KINDS}),
                                "unit": _nullable({"enum": ["원", "천원", "만원"]}),
                                "plan": _nullable({"type": "string", "minLength": 1}),
                                "priceStage": _nullable({"enum": STAGES}),
                                "targetGroup": _nullable({"type": "string", "minLength": 1}),
                            },
                        },
                    },
                },
            },
        }
    },
}

INSTRUCTIONS = """# 이번 호출에서 할 일 (supply_tables)
아래 표들은 공급·가격 표 후보입니다. 표마다 **각 열이 무엇인지만** 답합니다. 행의 값은 프로그램이 원문 칸에서 그대로 옮기므로 값을 적지 않습니다.
- role: 이번 공고로 공급하는 주택형·호실·주택과 그 수량·가격·면적을 담은 표면 SUPPLY.
  소득·자산 기준표, 일정표, 배점표, 면적·용어 설명표, 이미 다른 표가 담은 요약표는 OTHER.
  단, 요약표에 다른 표에 없는 금액 열(단지별 「월평균임대료」 등)이 있으면 SUPPLY로 두고 이름 칸(단지·주택형)과 금액 열만 답합니다
  (수량 열은 넣지 않음 — 같은 수량이 두 번 들어가지 않게. 금액은 프로그램이 같은 단지·주택형 묶음에 붙입니다).
- rowUnit: 한 행이 주택형이면 HOUSING_TYPE, 호실이면 HOUSING_UNIT, 주택(건물) 한 채면 BUILDING.
- complex: 표 전체가 한 단지의 것이면(표 위 제목 등) 그 단지 이름, 행마다 단지가 다르거나 모르면 null.
- columns: 의미 있는 열만 넣습니다(넣지 않은 열은 무시). 열 번호는 [열 제목] 줄의 번호입니다. meaning:
  - COMPLEX 단지·주택 이름, BUILDING 동, HOUSING_TYPE 주택형·타입·평형, UNIT 호실, FLOOR 층, TARGET_GROUP 행마다 다른 공급 대상·계층·순위
  - ADDRESS 행마다 다른 주택 주소 칸(도로명·지번 주소). 프로그램이 주소마다 위치를 만듭니다
  - AREA_EXCLUSIVE 주거전용면적(공급·계약·공용·합계 면적은 넣지 않음)
  - COUNT 수량 — countKind: 건설 호수·총 세대수 TOTAL_HOUSING, 금회 모집 OFFERED(예비입주자만 모집하는 공고면 금회 모집 예비자 수가 OFFERED),
    (예비입주자·입주대기자 공고에서 공실이 아닌 대상 주택 규모를 뜻하는 「공급호수」「세대수」 열은 TOTAL_HOUSING — 대상 주택 수와 모집 수는 따로 셉니다),
    즉시 입주자와 함께 뽑는 새 예비자 RESERVE, 이미 대기 중인 예비자 WAITLIST, 현재 공가 CURRENT_VACANCIES.
    수량 열이 공급 유형별(일반공급·우선공급·특별공급 등)로 나뉘면 targetGroup에 그 유형 이름
  - PRICE 금액 — priceKind(보증금 DEPOSIT·월임대료 MONTHLY_RENT·분양가 SALE_PRICE·계약금 CONTRACT_PAYMENT·잔금 BALANCE·그 밖 OTHER),
    unit(열 제목·표 위의 [단위] 표시), plan(요금안 이름: 기본, 보증금 최대 전환 등 — 같은 요금안의 보증금·월세는 같은 이름),
    priceStage(기본 STANDARD, 보증금을 올린 전환안 CONVERSION_DEPOSIT_UP, 보증금을 내린 전환안 CONVERSION_DEPOSIT_DOWN, 지원 전(당초) BEFORE_SUPPORT,
    지원 후(반값 등) AFTER_SUPPORT),
    targetGroup(이 열이 특정 순위·계층에만 해당하면 그 이름, 예: 1순위·수급자 등)
  - CONVERSION_LIMIT 전환 가능 보증금 한도·증감액 칸(「(+)5,000」「(-)16,000」). 가격이 아닙니다. 프로그램이 이 칸의 부호로 보증금 증액·감액 전환안을 나눕니다
  - PLAN_NAME 같은 주택형·층의 가격이 행마다 다른 안으로 나뉠 때 그 안 이름 칸(「구분」 열의 기본형·마이너스옵션 등). 가격 열이 아닙니다
- 관리비·선납 할인·옵션 비용 열은 넣지 않습니다. 확실하지 않은 열은 넣지 않습니다.
- 표마다 하나씩, table에는 아래 「표 번호」 값만 씁니다(예: "3-1". 「표」 글자·쪽 번호는 붙이지 않음).
- 수량·가격이 표 여러 개에 나뉘어 있으면(호수 표와 임대료 표) 표마다 답합니다. 프로그램이 같은 단지·같은 면적 묶음에 가격을 붙입니다.
- 전환안 열은 priceStage를 반드시 적습니다. 한 행에 증액·감액이 「(+)」「(-)」 칸으로 나뉘면 그 칸을 CONVERSION_LIMIT로 넣습니다.
- 보증금 없이 월세만 내는 요금안 열(「무보증금 월세」「무보증 전환 임대료」)은 보증금을 내린 전환안이라 priceStage CONVERSION_DEPOSIT_DOWN입니다.
  공고문이 그 요금안의 적용 대상을 정해 두었으면(「적용 대상자」「○○만 해당」) targetGroup에 그 대상 이름을 적습니다(STANDARD로 두지 않음).
- 표 전체가 특정 대상의 요금이면(절·앞 글·열 제목이 「상한 임대조건」「수급자 등의 임대조건」「○○인 경우」「적용 대상자」「○○에 한하여」)
  그 표의 **모든 가격 열** targetGroup에 그 대상 이름을 적습니다(행마다 「1인」「2인」 같은 대상 칸이 있어도 적음).
  대상을 정할 수 없으면 targetGroup을 비워 둡니다. 프로그램이 그 가격을 기본 요금으로 게시하지 않고 사람 확인으로 보냅니다.
- 주택형이 열에 없고 표 제목(앞 글의 「【31A】 구간별 임대조건」)에만 있으면 주택형 열을 만들지 않습니다. 프로그램이 제목의 주택형을 그 표 행에 붙입니다.
- 행마다 소득 구간·계층이 다른 임대조건표(「1구간 (~30%)」「2구간 (~50%)」 행)는 그 칸을 TARGET_GROUP으로 답하고 금액 열의 targetGroup은 비웁니다
  (첫 행의 구간을 열 전체의 대상으로 적지 않음).
- 첨부 엑셀 공급주택목록(표 번호 「엑셀1」 등)이 있으면 호실·주택별 공급은 그 엑셀 표로 답합니다. 같은 주택을 주택형·지역별로 다시 센
  공고문 요약표는 role OTHER로 둡니다(같은 공급이 두 번 들어가지 않게)."""


@dataclass(frozen=True)
class Table:
    label: str  # 요청·조각 ID에 쓰는 표 번호(첨부 PDF가 여럿이면 「2:3-1」)
    page: int
    heading: str  # 표 바로 위 글(표 제목·단위 표시)
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    cells: tuple[tuple[int, ...], ...] | None
    continues: str | None = None  # 앞 쪽 표가 머리 행 없이 이어진 표면 그 표 번호(열 의미를 물려받음)
    section: str = ""  # 표가 속한 절 제목(「5. 발코니 확장 및 추가선택품목 › ■ 발코니 확장 안내」). 쪽을 넘어 이어집니다
    above: tuple[str, ...] = ()  # 표 바로 위 글 줄(가까운 줄부터 최대 ABOVE_LINES개). 표 제목의 주택형(「【31A】 구간별 임대조건」)을 찾습니다
    # 같은 쪽 바로 앞 표와 짧은 이음말만 사이에 둔 표면 그 표 번호. 행이 하나씩 같으면 그 표의 행 이름·제목 주택형을 이어받습니다(build_part)
    beside: str | None = None


# 절 제목 줄: 「5. 발코니 확장…」 「■ 분양가격 납부조건」 「Ⅲ. 공급대상」. 「※」 안내·「- 4 -」 쪽 번호는 아님
SECTION_LINE = re.compile(r"^\s*(?:(?P<top>\d{1,2}\s*[.)]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\s*\.?)|(?P<sub>[■□◆◇▶]))\s*\S")
SECTION_CHARS = 60
# 두 표 사이 이음말의 글자 수 상한(공백 빼고). 실측 2026-11-07 bmc-75: 「[39A] 구간별 임대조건」 표 오른쪽에 화살표와 「임차인 선택사항」(8자)을
# 사이에 두고 같은 구간 행의 「상호전환 시 임대조건」 표가 따로 읽혀, 오른쪽 표는 제목의 주택형을 몰랐음
CONNECTOR_CHARS = 20


def _connector(texts: list[str]) -> bool:
    """두 표 사이 글이 짧은 이음말뿐인지: 공백 뺀 글자 CONNECTOR_CHARS자 이하이고 주택형 낱말·절 제목 줄이 없습니다."""
    text = "\n".join(texts)
    return len(re.sub(r"\s", "", text)) <= CONNECTOR_CHARS and not TITLE_TYPE.search(text) and not any(SECTION_LINE.match(line) for line in text.split("\n"))


def _section(text: str, top: str, sub: str) -> tuple[str, str]:
    """글 블록의 절 제목 줄로 (큰 절, 작은 절)을 갱신합니다. 큰 절이 바뀌면 작은 절은 비웁니다."""
    for line in text.split("\n"):
        match = SECTION_LINE.match(line)
        if not match or len(line.strip()) > SECTION_CHARS:
            continue
        if match.group("top"):
            top, sub = line.strip(), ""
        else:
            sub = line.strip()
    return top, sub


def _numeric(cell: str) -> bool:
    return bool(cell) and NUMERIC_VALUE.fullmatch(cell) is not None


def candidates(material: ExtractionMaterial) -> list[Table]:
    """첨부 엑셀 공급주택목록 시트와, 첨부 PDF의 표 중 공급·가격 표 후보(열 제목에 공급 단서가 있고 숫자 칸이 있는 표)와 그 이어지는 표를
    최대 MAX_TABLES개 고릅니다. 엑셀은 행이 많아도 표 하나입니다."""
    found: list[Table] = sheet_tables(material)
    many = len(material.pdf_pages) > 1
    for number, document in enumerate(material.pdf_pages, start=1):
        last: Table | None = None  # 이 문서에서 마지막으로 고른 표(다음 쪽 첫 표가 그 표의 이어짐인지 봅니다)
        top = sub = ""
        for page in document.get("pages") or []:
            heading = ""
            above: tuple[str, ...] = ()
            first_table = True
            between: list[str] = []  # 바로 앞 표 블록 뒤의 글
            neighbor: Table | None = None  # 이 쪽의 바로 앞 표 블록이 고른 표였으면 그 표
            for block in page.get("blocks") or []:
                if block.get("type") == "text":
                    heading = " ".join(block.get("text", "").strip().split("\n")[-2:])[-160:]
                    above = tuple(line.strip() for line in reversed(block.get("text", "").split("\n")) if line.strip())[:ABOVE_LINES]
                    top, sub = _section(block.get("text", ""), top, sub)
                    between.append(block.get("text", ""))
                    continue
                beside = neighbor.label if neighbor is not None and _connector(between) else None
                between, neighbor = [], None
                section = " › ".join(x for x in (top, sub) if x)
                columns = tuple(block.get("columns") or ())
                rows = tuple(tuple(r) for r in block.get("rows") or ())
                cells = block.get("cells")
                label = f"{number}:{block['id']}" if many else str(block["id"])
                page_number = int(page.get("page") or 0)
                numeric = any(_numeric(c) for r in rows for c in r)
                if first_table and last is not None and not columns:
                    aligned, aligned_cells = _aligned(rows, cells, len(last.columns))
                    if _continues(last, page_number, columns, aligned):
                        rows, cells = aligned, aligned_cells
                continues = first_table and _continues(last, page_number, columns, rows) and numeric
                first_table = False
                table_above, above = above, ()  # 다음 표는 그 사이 글 줄만 봅니다
                if not continues and columns and len(set(c for c in columns if c)) == 1:
                    columns, rows, cells = _recovered(columns, rows, cells)
                if continues and last is not None:
                    # 머리 행 없이 다음 쪽 맨 위로 이어진 표(실측 LH 청주지북 분양가 표: 55A·55A-1 뒤 55B~59C 행이 다음 쪽
                    # 머리 없는 표로 읽혀 매핑되지 않음 — 분양가 55개 빠짐). 앞 표의 열 제목을 쓰고 매핑은 앞 표를 따릅니다
                    last = Table(
                        label,
                        page_number,
                        heading,
                        last.columns,
                        rows,
                        tuple(tuple(r) for r in cells) if cells else None,
                        last.continues or last.label,
                        last.section,
                        last.above,
                    )
                    found.append(last)
                elif columns and any(SUPPLY_HINT.search(c) for c in columns) and numeric:
                    last = Table(
                        label, page_number, heading, columns, rows, tuple(tuple(r) for r in cells) if cells else None, None, section, table_above, beside
                    )
                    found.append(last)
                else:
                    last = None
                    continue
                neighbor = last
                if len(found) >= MAX_TABLES:
                    return found
    return (found + image_tables(material))[:MAX_TABLES]


IMAGE_BLOCK_HEAD = "=== 그림 판독 "  # image_reading.BLOCK_HEAD와 같음 (image_reading이 extract를 가져와 순환 import를 피함)
IMAGE_LABEL = "그림"


def image_tables(material: ExtractionMaterial) -> list[Table]:
    """그림 판독 글(원문 끝에 붙은 「=== 그림 판독 …」 묶음)의 표도 공급표 후보로: 이어진 「| … |」 줄 묶음마다 맨 위 머리 행
    (여러 줄이면 이어 붙임)을 열 제목, 그 아래 숫자가 있는 행을 행으로. 열 제목에 공급 단서가 있는 표만 고릅니다.
    (2026-11-05 sh-311087: 가격표가 그림이라 판독 글에만 있어 후보가 없었고, 구조 호출이 37행을 인용만 하고 공급 묶음은 1개만 만듦 — 가격 4/148)"""
    found: list[Table] = []
    for block in (getattr(material, "text", "") or "").split(IMAGE_BLOCK_HEAD)[1:]:
        head, _, body = block.partition("\n")
        runs: list[list[tuple[str, ...]]] = [[]]
        for line in body.split("\n"):
            stripped = line.strip()
            if len(stripped) > 1 and stripped.startswith("|") and stripped.endswith("|"):
                runs[-1].append(tuple(c.strip() for c in stripped[1:-1].split("|")))
            elif runs[-1]:
                runs.append([])
        for rows in (tuple(run) for run in runs):
            if not rows or not _header_like(rows[0]):
                continue
            columns, first = _merged_header(rows, 0)
            body_rows = tuple(r for r in rows[first:] if any(_numeric(c) for c in r))
            if body_rows and any(SUPPLY_HINT.search(c) for c in columns):
                found.append(Table(f"{IMAGE_LABEL}{len(found) + 1}", 0, f"{IMAGE_BLOCK_HEAD}{head}"[:160], columns, body_rows, None))
    return found


SHEET_HEADER_SCAN = 10  # 시트 맨 위 몇 행에서 머리 행을 찾을지(제목·안내 행이 먼저 올 수 있음)
SHEET_LABEL = "엑셀"


def _sheet_header(rows: tuple[tuple[str, ...], ...]) -> int | None:
    """시트의 머리 행 번호: 맨 위 몇 행 중 숫자가 아닌 칸이 셋 이상이고 공급 낱말이 있는 첫 행. 없으면 None."""
    for index, row in enumerate(rows[:SHEET_HEADER_SCAN]):
        words = [c for c in row if c and not _numeric(c)]
        if len(words) >= 3 and any(SUPPLY_HINT.search(c) or re.search(r"주소|소재지|주택|호", c) for c in words):
            return index
    return None


SHEET_HEADER_DEPTH = 3  # 묶음 제목 줄(「주택정보」「임대조건」) 아래 실제 칸 이름 줄이 오는 머리 행 수


def _header_like(row: tuple[str, ...]) -> bool:
    return not any(_numeric(c) for c in row) and sum(1 for c in row if c) >= 3


def _merged_header(rows: tuple[tuple[str, ...], ...], start: int) -> tuple[tuple[str, ...], int]:
    """머리 행이 여러 줄이면(묶음 제목 줄 + 칸 이름 줄) 칸마다 위아래 글을 이어 하나의 열 제목으로. (열 제목, 머리 다음 행 번호)."""
    end = start + 1
    while end < len(rows) and end - start < SHEET_HEADER_DEPTH and _header_like(rows[end]):
        end += 1
    width = max(len(r) for r in rows[start:end])
    titles = []
    for i in range(width):
        parts: list[str] = []
        for row in rows[start:end]:
            cell = row[i] if i < len(row) else ""
            if cell and cell not in parts:
                parts.append(cell)
        titles.append(" ".join(parts))
    return tuple(titles), end


def sheet_tables(material: ExtractionMaterial) -> list[Table]:
    """첨부 엑셀 시트를 공급표 후보로: 머리 행(여러 줄이면 이어 붙임)을 열 제목, 그 아래 숫자가 있는 행 전부를 행으로.
    행 줄은 원문에 붙인 「| … |」 줄과 같습니다(실측: LH 공급대상주택 목록은 제목·안내 줄 다음에 「주택정보」「임대조건」 묶음 줄과 칸 이름 줄)."""
    found: list[Table] = []
    for number, sheet in enumerate(getattr(material, "sheets", ()), start=1):
        rows = tuple(tuple(r) for r in sheet.get("rows") or ())
        header = _sheet_header(rows)
        if header is None:
            continue
        columns, first = _merged_header(rows, header)
        body = tuple(r for r in rows[first:] if any(_numeric(c) for c in r))
        if body:
            heading = f"첨부 엑셀 {sheet.get('name') or ''} · 시트 {sheet.get('sheet') or ''} ({len(body)}행)"
            found.append(Table(f"{SHEET_LABEL}{number}", 0, heading, columns, body, None))
    return found


def _continues(last: Table | None, page: int, columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> bool:
    """머리 행 없는 표가 앞 쪽 마지막 공급 표의 이어짐인지: 바로 다음 쪽의 첫 표이고, 칸 수가 같고, 숫자가 있는 칸이
    앞 표에서도 숫자가 있던 칸이며 그 칸의 절반 이상을 채웁니다(제목 없는 안내 표를 잘못 잇지 않게)."""
    if last is None or columns or page != last.page + 1 or not rows or any(len(r) != len(last.columns) for r in rows):
        return False
    before = {c for r in last.rows for c, v in enumerate(r) if _numeric(v)}
    now = {c for r in rows for c, v in enumerate(r) if _numeric(v)}
    return bool(now) and now <= before and 2 * len(now) >= len(before)


HEADER_CELL_CHARS = 30  # 표 안 머리 행의 칸 글자 수 상한(표 위 설명 글이 한 칸에 통째로 읽힌 행은 머리가 아님)

Cells = tuple[tuple[int, ...], ...] | None


def _recovered(columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...], cells: Any) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...], Cells]:
    """열 제목이 모두 한 가지 글자면(표 위 큰 제목 칸이 표 전체 머리로 읽힘) 표 안 맨 위 행들에서 머리 행을 찾아 열 제목으로 쓰고,
    머리 위 행은 빼고, 머리·본문 어디에도 글자가 없는 열은 뺍니다(실측 2026-10-20 LH 대전대동2 분양가 표: 열 제목 55칸이 모두
    「공급규모․공급대상 및 공급가격 등」, 셋째 행이 공고 설명 전체, 넷째 행이 「주택형 | … | 주택가격 | 계약금」 머리라 후보에서 빠지고
    옵션 가격표만 매핑됨 — 분양가 576개 미추출). 머리 행을 못 찾으면 그대로 돌려줍니다."""
    cells = tuple(tuple(r) for r in cells) if cells else None
    for index, row in enumerate(rows[:SHEET_HEADER_SCAN]):
        words = [c for c in row if c]
        if not (_header_like(row) and max(len(c) for c in words) <= HEADER_CELL_CHARS and any(SUPPLY_HINT.search(c) for c in words)):
            continue
        titles, first = _merged_header(rows, index)
        body = rows[first:]
        keep = [i for i in range(len(titles)) if titles[i] or any(i < len(r) and r[i] for r in body)]
        if len(keep) < 3:
            break
        return (
            _pick(titles, keep, ""),
            tuple(_pick(r, keep, "") for r in body),
            tuple(_pick(r, keep, -1) for r in _body_cells(cells, first, body)) if cells else None,
        )
    return columns, rows, cells


def _pick(line: Any, keep: list[int], pad: Any) -> tuple[Any, ...]:
    return tuple(line[i] if i < len(line) else pad for i in keep)


def _body_cells(cells: tuple[tuple[int, ...], ...], first: int, body: tuple[tuple[str, ...], ...]) -> list[tuple[int, ...]]:
    """머리 위 설명 칸이 표 전체로 읽히면 본문 칸 여럿이 그 칸과 같은 병합 번호를 받습니다(실측 LH 대전대동2: 본문 빈 칸이 모두 51번 —
    마이너스옵션·2층 행의 주택형이 비어 이름 없는 묶음이 됨). 머리 쪽 번호를 받은 본문 칸은 비었으면 바로 위 칸과 병합된 것으로,
    글자가 있으면 병합 없는 칸으로 고칩니다."""
    above = {cid for line in cells[:first] for cid in line}
    fixed: list[tuple[int, ...]] = []
    for r, line in enumerate(cells[first:]):
        row = body[r] if r < len(body) else ()
        fixed.append(
            tuple(
                cid if cid not in above else (fixed[-1][c] if fixed and c < len(fixed[-1]) and not (row[c] if c < len(row) else "") else -1)
                for c, cid in enumerate(line)
            )
        )
    return fixed


def _aligned(rows: tuple[tuple[str, ...], ...], cells: Any, width: int) -> tuple[tuple[tuple[str, ...], ...], Cells]:
    """머리 없는 이어지는 표가 앞 표보다 칸이 많고 넘치는 왼쪽 열이 모든 행에서 비면 그 열을 뺍니다(실측 LH 대전대동2: 앞 표 10열,
    다음 쪽 이어짐 11열(맨 왼쪽 빈 열)). 칸이 모자란 표는 어느 열이 빠졌는지 알 수 없어 그대로 둡니다(실측 LH 송산: 다음 쪽 소제목
    「2 | 신청자격 및 입주자 선정기준」을 왼쪽을 채워 맞추면 「2」가 모집 수 칸에 들어감)."""
    cells = tuple(tuple(r) for r in cells) if cells else None
    widths = {len(r) for r in rows}
    if len(widths) != 1 or (extra := widths.pop() - width) <= 0 or any(c for r in rows for c in r[:extra]):
        return rows, cells
    return tuple(r[extra:] for r in rows), tuple(r[extra:] for r in cells) if cells else None


def _row_line(row: tuple[str, ...]) -> str:
    return "| " + " | ".join(row) + " |"  # intake/pdf_reader.render와 같은 모양(원문 글자 그대로)


def mapping_request(base: ModelRequest, tables: list[Table], max_output_tokens: int | None = None) -> ModelRequest:
    """base: 구조 호출 요청. 같은 [공통 지시 → 원문] 앞부분을 그대로 써서 입력 캐시를 함께 쓰고, 지시·출력 형식만 바꿉니다."""
    listing = []
    for table in tables:
        if table.continues:
            continue  # 이어진 표는 앞 표의 답을 따릅니다
        sample = next((r for r in table.rows if any(_numeric(c) for c in r)), table.rows[0] if table.rows else ())
        titles = " | ".join(f"{i + 1}. {t or '-'}" for i, t in enumerate(table.columns))
        where = "첨부 엑셀" if table.label.startswith(SHEET_LABEL) else f"{table.page}쪽"
        listing.append(
            f"## 표 번호 {table.label} — {where}\n절: {table.section or '-'}\n앞 글: {table.heading or '-'}\n[열 제목] {titles}\n예시 행: {_row_line(sample)}"
        )
    return replace(
        base,
        prompt_version=PROMPT_VERSION,
        call_name=CALL_NAME,
        instructions=INSTRUCTIONS + "\n\n" + "\n\n".join(listing),
        output_schema=MAPPING_SCHEMA,
        max_output_tokens=max_output_tokens or output_limit(CALL_NAME, scaled_limit(len(listing))),
    )


def scaled_limit(table_count: int) -> int:
    """표 수에 맞춘 출력 한도: 기본 MAX_OUTPUT_TOKENS, 표가 많으면 표마다 TOKENS_PER_TABLE(상한 MAX_OUTPUT_TOKENS_CAP)."""
    return min(MAX_OUTPUT_TOKENS_CAP, max(MAX_OUTPUT_TOKENS, table_count * TOKENS_PER_TABLE))


def salvage_mapping(raw: str) -> list[dict[str, Any]]:
    """출력 한도로 잘린 열 의미 답에서 끝까지 적힌 표 답만 꺼냅니다(「tables」 배열의 완성된 객체들)."""
    text = raw.strip().removeprefix("```json").removeprefix("```")
    start = text.find('"tables"')
    if start < 0:
        return []
    at = text.find("[", start)
    if at < 0:
        return []
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    at += 1
    while True:
        while at < len(text) and text[at] in " \t\r\n,":
            at += 1
        if at >= len(text) or text[at] != "{":
            return found
        try:
            value, at = decoder.raw_decode(text, at)
        except ValueError:
            return found  # 잘린 마지막 객체
        if isinstance(value, dict):
            found.append(value)


def _filled(table: Table, seed: dict[int, str] | None = None) -> tuple[list[list[str]], list[list[int]]]:
    """병합 칸 복원: 같은 칸 번호의 빈 자리를 그 칸의 첫 자리 글자로. 둘째 값은 자리마다 그 글자가 처음 나온 행 번호.
    seed: 앞 쪽에서 이어진 표면 앞 조각 마지막 행의 이름 칸 글자(칸 번호 → 글자). 첫 행에서 시작하는 빈 병합 칸은 앞 쪽 칸이
    쪽을 넘어 이어진 것이라 그 글자로 채우고 처음 나온 행을 -1(앞 조각)로 둡니다."""
    first: dict[int, tuple[int, str]] = {}
    filled, origin = [], []
    for r, row in enumerate(table.rows):
        line, source = [], []
        for c, value in enumerate(row):
            cid = table.cells[r][c] if table.cells and r < len(table.cells) and c < len(table.cells[r]) else -1
            if cid >= 0 and cid in first and not value:
                line.append(first[cid][1])
                source.append(first[cid][0])
            elif r == 0 and not value and seed and seed.get(c):
                if cid >= 0:
                    first[cid] = (-1, seed[c])
                line.append(seed[c])
                source.append(-1)
            else:
                if cid >= 0 and cid not in first:
                    first[cid] = (r, value)
                line.append(value)
                source.append(r)
        filled.append(line)
        origin.append(source)
    return filled, origin


def _cell_id(table: Table, r: int, c: int) -> int:
    return table.cells[r][c] if table.cells and r < len(table.cells) and c < len(table.cells[r]) else -1


def _number(text: str, last: bool = False) -> float | None:
    found = NUMBER.findall(text.replace(" ", ""))
    if not found:
        return None
    return float((found[-1] if last else found[0]).replace(",", ""))


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", text.lower()).strip("-") or "t"


def _unit(column: dict[str, Any], title: str) -> str:
    if column.get("unit"):
        return column["unit"]
    match = UNIT_IN_TITLE.search(title)
    return (match.group(1) or match.group(2)) if match else "원"


def _title_types(table: Table) -> list[str]:
    """표 위 글 줄 중 가장 가까운 짧은 제목 줄의 주택형 낱말들(겹침 없이). 주택형이 적힌 제목 줄이 없으면 빈 목록."""
    for line in table.above:
        if len(line) > TITLE_CHARS or NOTE_MARK.match(line):
            continue
        found = list(dict.fromkeys(re.sub(r"\s+", "", t).removesuffix("형") for t in TITLE_TYPE.findall(line)))
        if found:
            return found
    return []


def _names(values: dict[int, str], keys: list[dict[str, Any]]) -> dict[str, str]:
    """행의 이름 칸 글자(의미 → 글자). 같은 의미 칸이 둘이면 이어 씁니다(실측 대전대동2 「059.8900A」|「59A」: 뒤 칸만 남아 주택형 코드의
    면적이 빠짐). 대상 칸이 둘 이상(「청년」|「소득無」)이어도 이어 씁니다(예전엔 마지막 칸만 남아 「소득無」가 대상이 됨, 실측: LH 포항 행복주택)."""
    named: dict[str, str] = {}
    for c in keys:
        value = values[c["column"] - 1]
        if value and value not in named.get(c["meaning"], "").split(" "):
            named[c["meaning"]] = f"{named[c['meaning']]} {value}" if c["meaning"] in named else value
    parts = list(dict.fromkeys(values[c["column"] - 1] for c in keys if c["meaning"] == "TARGET_GROUP" and values[c["column"] - 1]))
    if parts:
        named["TARGET_GROUP"] = " ".join(parts)
    return named


def _row_names(filled: list[list[str]], columns: list[dict[str, Any]], keys: list[dict[str, Any]], first_data: int) -> list[tuple[int, dict[str, str]]]:
    """표의 공급 행마다 (행 번호, 이름 칸 글자). build_part처럼 합계 행과 읽는 칸에 숫자가 없는 행은 뺍니다."""
    out = []
    for r in range(first_data, len(filled)):
        row = filled[r]
        values = {c["column"] - 1: row[c["column"] - 1] if c["column"] - 1 < len(row) else "" for c in columns}
        if any(SUBTOTAL.match(values[c["column"] - 1] or "") for c in keys) or not any(_numeric(v) for v in values.values()):
            continue
        out.append((r, _names(values, keys)))
    return out


def _label_core(text: str) -> str:
    return _norm(CLASS_NOTE.sub("", text))


def _same_rows(mine: list[tuple[int, dict[str, str]]], theirs: list[tuple[int, dict[str, str]]]) -> bool:
    """옆 표의 행이 앞 표의 행과 하나씩 같은지: 행 수가 같고(둘 이상), 행마다 이 표의 이름 칸 글자가 앞 표의 같은 의미 칸과
    괄호 설명·띄어쓰기를 빼고 같습니다(세로 글자 「1 구 간」 = 「1구간 (~30%)」)."""
    return len(mine) == len(theirs) >= 2 and all(
        names and all(_label_core(value) == _label_core(other.get(meaning, "")) for meaning, value in names.items())
        for (_, names), (_, other) in zip(mine, theirs, strict=True)
    )


def _table_label(group: dict[str, Any]) -> str:
    return group["id"].rsplit("-r", 1)[0].removeprefix("sg-t")


def _restricted(text: str) -> str | None:
    found = RESTRICTED_PRICE.search(text or "")
    return found[0] if found else None


def _table_restriction(table: Table) -> str | None:
    """표 전체가 특정 대상의 요금임을 말하는 낱말. 표 제목·바로 위 글 중 요금을 말하고 법령 인용이 아닌 줄과 절 제목에서만 찾습니다."""
    lines = [line for line in (table.heading, *table.above) if PRICE_TITLE_WORDS.search(line or "") and not LAW_TEXT.search(line or "")]
    return _restricted(" ".join([*lines, table.section.split(" › ")[-1]]))


def _scope(group_id: str, groups: list[str], description: str) -> dict[str, Any]:
    return {
        "level": "SUPPLY_GROUP",
        "locationIds": [],
        "supplyGroupIds": [group_id],
        "targetGroups": groups,
        "supplyCategory": "ALL",
        "resolution": "RESOLVED",
        "description": description,
    }


def build_part(tables: list[Table], mapping: dict[str, Any], document_id: str) -> dict[str, Any] | None:
    """열 의미 → AI 출력과 같은 모양의 공급 조각(quotes·supplyGroups·coverage). 공급표가 하나도 없으면 None."""
    by_label = {t.label: t for t in tables}
    quotes: list[dict[str, Any]] = []
    quote_of: dict[str, str] = {}
    groups: list[dict[str, Any]] = []
    shared: dict[tuple[str, int, str], set[str]] = {}  # (표, 칸 번호, 수량 종류) → 그 칸의 수량을 쓰는 공급 묶음
    pending_pools: list[tuple[dict[str, Any], tuple[str, int, str]]] = []
    pool_column: dict[tuple[str, int, str], tuple[str, int, str]] = {}  # 병합 칸 → (첫 표, 열, 수량 종류)
    column_values: dict[tuple[str, int, str], dict[tuple[str, Any], int]] = {}  # (첫 표, 열, 종류) → 칸마다 한 번씩 센 수량
    subtotals: dict[tuple[str, int, str], int] = {}  # (첫 표, 열, 종류) → 합계 행의 수

    def quote(line: str) -> str:
        if line not in quote_of:
            quote_of[line] = f"t{len(quote_of) + 1}"
            quotes.append({"ref": quote_of[line], "documentId": document_id, "text": line})
        return quote_of[line]

    entries = [dict(e) for e in mapping.get("tables") or [] if isinstance(e, dict)]  # 이름 칸을 빌려 고칠 수 있어 사본으로
    supply_of = {str(e.get("table")): e for e in entries if e.get("role") == "SUPPLY"}
    for table in tables:  # 이어진 표는 앞 표와 같은 열 의미로 읽습니다
        if table.continues and table.continues in supply_of and table.label not in supply_of:
            entries.append({**supply_of[table.continues], "table": table.label})
    _borrow_keys(entries, by_label)
    order = {t.label: i for i, t in enumerate(tables)}
    resolved = []
    for entry in entries:
        table = by_label.get(str(entry.get("table"))) or by_label.get(LABEL_NOISE.sub("", str(entry.get("table") or "")))
        if table is not None and entry.get("role") == "SUPPLY":
            resolved.append((order[table.label], table, entry))
    previous: tuple[Table, list[str]] | None = None  # 바로 앞에 읽은 표와 그 마지막 행(병합 복원)
    current: dict[str, Any] | None = None
    current_key: tuple[str, ...] | None = None
    unread: list[str] = []  # 행 이름 칸이 없어 읽지 못한 가격표
    read: dict[str, tuple[list[str], list[tuple[int, dict[str, str]]], str | None]] = {}  # 읽은 표 → (제목 주택형, 행 이름, 대상 한정 낱말)
    for _, table, entry in sorted(resolved, key=lambda item: item[0]):  # 표 순서대로(쪽을 넘어 이어진 표가 앞 조각 바로 뒤에 오게)
        width = len(table.columns)
        columns = [c for c in entry.get("columns") or [] if 1 <= int(c.get("column") or 0) <= width and c.get("meaning") != "IGNORE"]
        keys = [c for c in columns if c["meaning"] in KEY_MEANINGS]
        if not keys or not any(c["meaning"] in ("PRICE", "COUNT", "AREA_EXCLUSIVE") for c in columns):
            if not keys and any(c["meaning"] == "PRICE" for c in columns) and not option_table(table):
                unread.append(table.label)
            continue
        root = table.continues or table.label
        title_types = [] if any(c["meaning"] == "HOUSING_TYPE" for c in keys) else _title_types(table)
        table_restriction = _table_restriction(table)
        if option_table(table) and not any(c["meaning"] in ("COUNT", "AREA_EXCLUSIVE") for c in columns):
            continue  # 발코니 확장·선택품목 가격표는 주택 가격이 아닙니다(AI가 공급표로 답해도)
        # 앞 쪽에서 이어진 표는 앞 조각의 마지막 묶음을 이어 갑니다(쪽 첫 행이 앞 쪽 주택형·층의 둘째 행일 수 있음: 실측 LH 대전대동2
        # 3쪽 첫 행 「| | | | 마이너스옵션 | 321,050,000 |」은 2쪽 끝 「059.8900A 59A 2층」의 마이너스옵션). 이어지지 않으면 새로 시작합니다
        at = order[table.label]
        carried = previous is not None and table.continues is not None and at > 0 and tables[at - 1] is previous[0]
        seed = {c["column"] - 1: previous[1][c["column"] - 1] for c in keys if c["column"] - 1 < len(previous[1])} if carried and previous else None
        if not carried:
            current, current_key = None, None
        filled, origin = _filled(table, seed)
        if filled:
            previous = (table, filled[-1])
        # 호실마다 한 행인 모집 표(동·호·면적·보증금)에 수량 열이 없으면 한 행이 모집 1호입니다(실측 LH 김포 장애인 자립주택: 모집 수 0/4)
        unit_rows = entry.get("rowUnit") == "HOUSING_UNIT" and not any(c["meaning"] == "COUNT" for c in columns)
        first_data = next((r for r, row in enumerate(filled) if any(_numeric(c) for c in row)), None)
        if first_data is None:
            continue
        row_names = _row_names(filled, columns, keys, first_data)
        side = read.get(table.beside or "")
        inherited: dict[int, dict[str, str]] = {}
        if (
            side
            and not title_types
            and not any(c["meaning"] == "HOUSING_TYPE" for c in keys)
            and (side[0] or any("HOUSING_TYPE" in names for _, names in side[1]))
            and _same_rows(row_names, side[1])
        ):
            # 바로 앞 표의 행을 오른쪽에 이어 적은 표(실측 bmc-75 「[39A] 구간별 임대조건」 옆 「상호전환 시 임대조건」 표, 구간 행 6개가 같음):
            # 그 표의 제목 주택형·행 이름(「1 구 간」 대신 「1구간 (~30%)」)·대상 한정을 이어받아 같은 묶음·같은 대상의 요금안이 됩니다
            title_types = side[0]
            table_restriction = table_restriction or side[2]
            inherited = {r: names for (r, _), (_, names) in zip(row_names, side[1], strict=True)}
        read[table.label] = (title_types, row_names, table_restriction)
        for c in columns:  # 한도 열로 답했지만 제목에 한도가 없고 금액 종류까지 적은 열은 전환 후 금액입니다(실측: LH 양산 「① 감액 › 임대보증금」)
            if c["meaning"] == "CONVERSION_LIMIT" and c.get("priceKind") and not LIMIT_WORDS.search(table.columns[c["column"] - 1]):
                c["meaning"] = "PRICE"
        limit_column = next((c["column"] - 1 for c in columns if c["meaning"] == "CONVERSION_LIMIT"), None)
        after_limit_kinds = {
            (c.get("priceKind"), True) for c in columns if c["meaning"] == "PRICE" and limit_column is not None and c["column"] - 1 > limit_column
        }
        # 같은 가격 열을 전환 방향마다 여러 번 답한 경우(칸 하나에 여러 줄의 금액): 열마다 (답, 방향)을 답한 순서대로
        stacked: dict[tuple[int, Any], list[tuple[dict[str, Any], str]]] = {}
        for c in columns:
            way = _entry_direction(c, table.columns[c["column"] - 1]) if c["meaning"] == "PRICE" else None
            if way:
                stacked.setdefault((c["column"], c.get("priceKind")), []).append((c, way))
        first_price = min((c["column"] for c in columns if c["meaning"] == "PRICE"), default=0)
        for c in columns:  # 종류를 비운 수량 열은 열 제목으로 정합니다(실측: 인천 「호수」 열을 COUNT로만 답해 대상 주택 수가 모두 빠짐)
            if c["meaning"] != "COUNT":
                continue
            title = table.columns[c["column"] - 1]
            parts = [_count_kind_from_title(t) for t in title.split("/")] if title.count("/") == 1 else []
            if len(parts) == 2 and all(parts) and (not c.get("countKind") or c["countKind"] in parts):
                c["splitKinds"] = parts  # 「현재 공가 호수 / 전체 호수」 칸의 「7/8」 → 공가 7, 대상 주택 8 (답이 둘 중 하나만 골라도 나눔)
            if not c.get("countKind"):
                c["countKind"] = parts[0] if c.get("splitKinds") else _count_kind_from_title(title)
        same_kind = Counter(c.get("countKind") for c in columns if c["meaning"] == "COUNT" and not c.get("targetGroup"))
        for c in columns:  # 같은 종류 수량 열이 둘 이상인데 대상을 비워 답하면(실측: SH 일반공급·우선공급) 열 제목 끝 이름을 대상으로
            if c["meaning"] == "COUNT" and not c.get("targetGroup") and same_kind[c.get("countKind")] > 1:
                c["targetGroup"] = table.columns[c["column"] - 1].split("›")[-1].strip() or None
        current_rows: set[int] = set()
        for r in range(first_data, len(filled)):
            row = filled[r]
            values = {c["column"] - 1: row[c["column"] - 1] if c["column"] - 1 < len(row) else "" for c in columns}
            key = tuple(values[c["column"] - 1] for c in keys)
            if any(SUBTOTAL.match(v or "") for v in key):
                for c in columns:  # 합계 행의 수량: 병합 칸 수량을 한 번만 센 합과 맞는지 봅니다
                    total = _number(values[c["column"] - 1] or "") if c["meaning"] == "COUNT" and c.get("countKind") else None
                    if total is not None:
                        subtotals[(root, c["column"] - 1, c["countKind"])] = int(total)
                continue
            if not any(_numeric(v) for v in values.values()):
                continue
            if not any(key):
                key = current_key or key  # 이름 칸이 비어 있으면(병합 정보 없는 이어지는 행) 앞 묶음의 행
            _split_shifted_pairs(values, columns)
            line = _row_line(table.rows[r])
            ref = quote(line)
            # 주택형 칸이 세로로 병합되어 이름이 같아도 그 행의 전용면적이 다르면 다른 공급 행입니다
            # (실측 2026-10-18 LH 철원갈말: 「24A」 한 칸 아래 24.59㎡ 8호·24.66㎡ 12호 두 행이 한 묶음으로 합쳐져 둘째 행이 빠짐)
            own_area = next(
                (values[c["column"] - 1] for c in columns if c["meaning"] == "AREA_EXCLUSIVE" and origin[r][c["column"] - 1] == r and values[c["column"] - 1]),
                None,
            )
            area = _number(own_area) if own_area else None
            new_area = current is not None and area is not None and current.get("exclusiveAreaSqm") not in (None, area)
            # 이름·면적 칸이 위 행과 병합된 이어지는 행이라도 자기 수량 칸에 다른 수가 있으면 다른 공급 행입니다
            # (실측: LH 아산읍내 「26.37」 한 칸 아래 건설 세대수 478·596 두 행 중 596이 빠짐). 같은 수의 되풀이는 같은 행
            had = {(cnt["kind"], cnt["value"]) for cnt in current["counts"]} if current is not None else set()
            own_count = (
                current is not None
                and key == current_key
                and any(
                    c["meaning"] == "COUNT"
                    and origin[r][c["column"] - 1] == r
                    and _number(values[c["column"] - 1] or "") is not None
                    and any(kind == c.get("countKind") for kind, _ in had)
                    and (c.get("countKind"), int(_number(values[c["column"] - 1]) or 0)) not in had
                    for c in columns
                )
            )
            if key != current_key or current is None or new_area or own_count:
                named = {**_names(values, keys), **inherited.get(r, {})}
                if len(title_types) == 1:  # 주택형 열이 없고 표 제목에 주택형 하나: 이 표의 행은 그 주택형
                    named = {"HOUSING_TYPE": title_types[0], **named}
                group_id = f"sg-t{_slug(table.label)}-r{r}"
                target = named.get("TARGET_GROUP")
                name = " ".join(v for m, v in named.items() if m != "TARGET_GROUP") or table.label
                current = {
                    "id": group_id,
                    "locationId": None,
                    "housingTypeCode": named.get("HOUSING_TYPE"),
                    "buildingUse": None,
                    "exclusiveAreaSqm": None,
                    "exclusiveAreaRange": None,
                    "scope": _scope(group_id, [target] if target else [], f"{name}{' ' + target if target else ''} 공급 묶음에 적용합니다."),
                    "counts": [],
                    "prices": [],
                    "quoteRefs": [ref],
                    "itemKind": {"HOUSING_TYPE": "HOUSING_TYPE", "HOUSING_UNIT": "HOUSING_UNIT"}.get(entry.get("rowUnit"), "UNKNOWN"),
                    "unitLabel": _unit_label(named, entry.get("rowUnit")),
                    "floor": named.get("FLOOR"),
                    "_unit": named.get("UNIT"),
                    "commonAreaSqm": None,
                    "leaseTerm": None,
                    # 표 전체의 단지 이름이 있으면 「해당동 101 102」 같은 동 칸보다 먼저 씁니다(실측: 철원 공급표의 동 번호가 단지로 쓰여 가격표가 안 붙음)
                    "_complex": named.get("COMPLEX") or entry.get("complex") or named.get("BUILDING"),
                    "_address": named.get("ADDRESS"),
                    "_plans": {},
                    "_anonymous": not set(named) - {"TARGET_GROUP"},  # 행에 대상 칸 말고는 이름(주택형·호·단지·동·주소·층)이 없음
                }
                if len(title_types) > 1:
                    current["_type_ambiguous"] = title_types
                groups.append(current)
                current_key, current_rows = key, set()
                if unit_rows:
                    current["counts"].append(
                        {
                            "id": f"{group_id}.count1",
                            "kind": "OFFERED",
                            "value": 1,
                            "scope": _scope(group_id, current["scope"]["targetGroups"], current["scope"]["description"]),
                            "aggregationRole": "STANDALONE",
                            "parentCountId": None,
                            "aggregationComplete": False,
                            "quoteRefs": [ref],
                        }
                    )
                for column in columns:
                    c = column["column"] - 1
                    value = values[c]
                    if column["meaning"] == "AREA_EXCLUSIVE" and value:
                        span = re.findall(r"\d+(?:\.\d+)?", value)
                        if len(span) == 2 and re.search(r"[~∼～〜]", value):
                            current["exclusiveAreaRange"] = {"min": float(span[0]), "max": float(span[1])}
                        elif span:
                            current["exclusiveAreaSqm"] = float(span[0])
                    if column["meaning"] == "COUNT" and column.get("countKind") and value:
                        pieces = value.split("/") if column.get("splitKinds") and value.count("/") == 1 else [value]
                        kinds = column["splitKinds"] if len(pieces) == 2 else [column["countKind"]]
                        for kind, piece in zip(kinds, pieces, strict=True):
                            number = 0 if piece.strip() in {"-", "−", "–"} else _number(piece, last=kind == "TOTAL_HOUSING" and "/" in piece)
                            if number is None:
                                continue
                            count = {
                                "id": f"{group_id}.count{len(current['counts']) + 1}",
                                "kind": kind,
                                "value": int(number),
                                "scope": _scope(
                                    group_id,
                                    [column["targetGroup"]] if column.get("targetGroup") else current["scope"]["targetGroups"],
                                    current["scope"]["description"],
                                ),
                                "aggregationRole": "STANDALONE",
                                "parentCountId": None,
                                "aggregationComplete": False,
                                # 세로 병합 칸의 수량은 자기 행과 칸이 시작한 행을 함께 인용합니다(2026-10-24 일곱 번째 채점: 시작한 행만 인용해
                                # 그 행의 주택형과 달라 위치 의심 151건). 가격의 병합 칸과 같은 방식입니다
                                "quoteRefs": list(dict.fromkeys([ref, quote(_row_line(table.rows[origin[r][c]]))]))
                                if origin[r][c] != r and origin[r][c] >= 0
                                else [quote(_row_line(table.rows[origin[r][c]]))],
                            }
                            current["counts"].append(count)
                            cell = (table.label, _cell_id(table, origin[r][c], c), kind)  # 「7/8」처럼 한 칸의 두 수는 종류별로 따로 묶음
                            once = (table.label, cell[1] if cell[1] >= 0 else f"r{origin[r][c]}")
                            column_values.setdefault((root, c, kind), {})[once] = int(number)
                            if cell[1] >= 0:
                                shared.setdefault(cell, set()).add(group_id)
                                pending_pools.append((count, cell))
                                pool_column[cell] = (root, c, kind)
            current_rows.add(r)
            sign = _sign(row, limit_column)
            row_plan = " ".join(dict.fromkeys(values[c["column"] - 1] for c in columns if c["meaning"] == "PLAN_NAME" and values[c["column"] - 1]))
            line_plans: dict[int, str] = {}  # 여러 줄 칸의 줄 번호 → 요금안 이름
            for column in columns:
                c = column["column"] - 1
                if column["meaning"] != "PRICE" or not column.get("priceKind"):
                    continue
                value = values[c].strip()
                if not value or value in {"-", "−", "–"} or _number(value) is None or _number(value) == 0:
                    # 0원 칸은 그 안이 없는 행입니다(실측 2026-10-20 LH 대구경북 기존주택매입 엑셀: 무보증월세여부 N인 140호의
                    # 무보증전환임대료 「0」이 월임대료 0원으로 게시됨). 진짜 0원이어도 빠진 가격으로 검수하는 쪽이 안전합니다
                    continue
                if origin[r][c] != r and origin[r][c] in current_rows:
                    continue  # 같은 묶음의 위 행에서 세로로 이어진 값: 이미 넣음
                price_refs = [ref]
                if origin[r][c] != r:
                    # 다른 행에서 세로로 병합된 칸의 값(2026-10-24 세 번째 채점: 표 전체에 병합된 계약금 「500 (정액)」이 전환안 줄·거주기간 줄
                    # 같은 보조 줄마다 다시 붙어 묶음마다 계약금이 셋까지 생기고, 그 줄 인용에 「500」이 없어 묶음 전체가 보류됨).
                    # 한 묶음에는 병합 칸 하나의 값을 한 번만 붙이고, 값이 적힌 원래 행도 근거로 함께 인용합니다
                    used = current.setdefault("_merged_cells", set())
                    if (c, origin[r][c]) in used:
                        continue
                    used.add((c, origin[r][c]))
                    if origin[r][c] >= 0:
                        price_refs.append(quote(_row_line(table.rows[origin[r][c]])))
                base_plan = f"{row_plan} {column['plan']}" if row_plan and column.get("plan") else row_plan or column.get("plan") or "기본"
                base_stage = column.get("priceStage") or _guess_stage(column, base_plan, limit_column, first_price, sign)
                if base_stage in ("STANDARD", "CONVERSION_DEPOSIT_UP", "CONVERSION_DEPOSIT_DOWN"):
                    # 열 제목·요금안 이름이 보증금을 올리는지 내리는지 말하면 그 방향을 씁니다(아래 부호 칸이 있으면 부호가 우선)
                    base_stage = _stage_words(f"{table.columns[c]} {base_plan}") or base_stage
                if limit_column is not None and c < limit_column and (column.get("priceKind"), True) in after_limit_kinds:
                    # 전환 금액 칸이 한도 칸 뒤에 따로 있으면 한도 칸 앞의 금액은 전환 전 기본 조건입니다(2026-10-24 다섯 번째 채점:
                    # 「임대보증금 감액시 임대조건 › 임대보증금·월임대료 | 한도 | 전환보증금 | 전환임대료」의 앞 두 칸이 감액안으로 게시됨)
                    base_stage, base_plan = "STANDARD", row_plan or "기본"
                amounts = AMOUNT_IN_CELL.findall(value) if SPACED_AMOUNTS.search(value) else [value]  # 범위(「1,000~2,000」)는 한 값
                lines: list[tuple[int | None, str, str]] = [(None, value, sign)]  # (칸 안 줄 번호, 금액, 그 줄의 증감 표시)
                if len(amounts) > 1:
                    # 칸 하나에 여러 줄의 금액(점선으로 나뉜 줄이 한 칸으로 읽힘): 전환 칸이고 한도 칸의 증감 표시가 줄 수만큼 있으면 적힌 순서대로
                    # 한 줄씩 짝짓습니다(실측: LH 포항 행복주택 「(+) - (-) 10,000」 | 「12,614 2,614」, 2026-11-07 bmc-75 「(-) 4,880,000 (+) 4,870,000
                    # (+) 11,360,000」 | 「11,360,000 21,110,000 27,600,000」. 화살표 「↑ … ↓ …」·「증액 … 감액 …」도 같은 표시).
                    # 그 밖에는 어느 안의 값인지 몰라 넣지 않고, 조용히 버리지 않도록 검수 이슈로 남깁니다(그 묶음 보류)
                    marks = _sign_lines(sign)
                    picked = _pick_lines(column, stacked.get((column["column"], column.get("priceKind")), []), [mark for mark, _ in marks])
                    if not base_stage.startswith("CONVERSION") or len(marks) != len(amounts) or picked is None:
                        current.setdefault("_unsplit", []).append(f"{table.columns[c] or column.get('plan') or '가격'} 칸 「{value}」")
                        continue
                    lines = [(i, amounts[i], marks[i][0]) for i in picked if marks[i][1] is not False]  # 한도 칸이 「-」로 적은 줄은 전환 없음
                restriction = table_restriction or _restricted(table.columns[c])
                for line, cell_value, cell_sign in lines:
                    plan, stage = base_plan, base_stage
                    if stage.startswith("CONVERSION") and cell_sign:
                        down = cell_sign.startswith(("(-)", "-", "−", "(−)"))
                        stage = "CONVERSION_DEPOSIT_DOWN" if down else "CONVERSION_DEPOSIT_UP"
                        if _stage_words(plan) != stage:  # 요금안 이름이 이미 그 방향이면(「보증금 감액」) 되풀이하지 않습니다
                            plan = f"{plan} (보증금 {'감액' if down else '증액'})"
                    direction = "(-)" if stage == "CONVERSION_DEPOSIT_DOWN" else "(+)"
                    if line is None and stage.startswith("CONVERSION") and limit_column is not None and _direction_amounts(sign).get(direction) is False:
                        # 한도 칸이 그 방향을 「-」로 적었으면(「(+) -」「(+) - (-) 10,000」) 그 방향 전환이 없는 행입니다. 옆 칸에는 기본 조건이
                        # 그대로 적혀 있어 전환안으로 넣으면 기본과 같은 가짜 전환안이 됩니다(2026-10-24 네·다섯 번째 채점).
                        # 부호만 적는 「증감 구분」 칸(「(+)」)은 금액이 옆 칸에 있으므로 빼지 않습니다(일곱 번째 채점: 전환안 전부가 빠짐)
                        continue
                    if restriction and stage == "STANDARD" and not column.get("targetGroup") and not current["scope"]["targetGroups"]:
                        # 특정 대상의 요금표인데 대상 없이 기본 요금으로 답함: 다른 표의 모집 묶음에 붙이지 않고 보류합니다.
                        # 행의 대상 칸에서 대상이 이미 정해진 묶음은 대상 미정이 아닙니다(2026-10-24 네 번째 채점)
                        current.setdefault("_scope_uncertain", {})[f"{table.columns[c] or plan} 칸"] = restriction
                    if line is not None:
                        # 여러 줄 칸은 줄이 요금안입니다: 같은 줄의 보증금·월세를 한 요금안으로 묶고(열마다 답한 요금안 이름이 달라도 줄로),
                        # 이름은 그 줄을 처음 읽은 열의 것, 다른 줄과 이름이 같으면(같은 방향 둘) 번호를 붙입니다
                        if line not in line_plans:
                            name, n = plan, 1
                            while name in line_plans.values():
                                n += 1
                                name = f"{plan} {n}"
                            line_plans[line] = name
                        plan = line_plans[line]
                    _add_price(current, column, table.columns[c], price_refs, cell_value, plan, stage, None if line is None else (r, line))
    for group in groups:  # 전용면적 열이 없거나 비면 LH 주택형 코드(「059.9800A」 → 59.98)로 채웁니다(실측: LH 충북혁신)
        code = TYPE_CODE_AREA.match(group.get("housingTypeCode") or "")
        if code and group["exclusiveAreaSqm"] is None and group["exclusiveAreaRange"] is None:
            group["exclusiveAreaSqm"] = float(code[1])
    # 층 열이 없고 호 칸만 있으면 호수 앞자리가 층(「214」 → 2층, 「1005」 → 10층)
    # 실측 2026-10-26 LH 청년 매입임대 주택목록은 층 열이 없어 31호 모두 층이 비었어요
    for group in groups:
        unit = UNIT_FLOOR.fullmatch((group.get("_unit") or "").strip().removesuffix("호"))
        if group["itemKind"] == "HOUSING_UNIT" and not group.get("floor") and unit and int(unit[1]) > 0:
            group["floor"] = f"{int(unit[1])}층"
    groups = _attach_price_tables(groups)
    # 수량도 읽은 가격도 없이 금액 여럿이 붙은 칸만 남은 행은 빈 공급 묶음으로 두지 않고 읽지 못한 가격표로 알립니다(2026-11-07 지시 v8 유료 확인
    # bmc-75: 「상호전환 시 임대조건」 표의 (-)·(+)·(+) 세 줄이 칸마다 「11,360,000 21,110,000 27,600,000」로 읽혀, 주택형 없는 빈 묶음 12개마다
    # 가격 빈칸 이슈가 붙음. 지금은 한도 칸의 증감 표시로 줄을 나누고, 나누지 못한 칸만 여기로)
    blank = [g for g in groups if not g["counts"] and not g["prices"] and g.get("_unsplit")]
    crammed = list(dict.fromkeys(_table_label(g) for g in blank))
    # 모집 묶음이 따로 있는데 행에 대상(구간·계층) 말고는 이름이 없어 어디에도 붙지 못한 가격 묶음(제목에도 옆 표에도 주택형이 없는 구간별
    # 가격표 등)은 어느 묶음의 가격인지 몰라 게시하지 않고 읽지 못한 가격표로 알립니다. 단지 이름 칸으로 나눈 행은 그 단지의 가격이라 두고,
    # 대상·주택형 미정으로 보류할 묶음도 그대로 둡니다
    counted = any(g["counts"] for g in groups)
    nameless = [
        g
        for g in groups
        if counted and g["prices"] and not g["counts"] and g.get("_anonymous") and not g.get("_type_ambiguous") and not g.get("_scope_uncertain")
    ]
    unread += [label for label in dict.fromkeys(_table_label(g) for g in nameless) if label not in unread]
    groups = [g for g in groups if g not in blank and g not in nameless]
    if not groups:
        return None
    merged_counts: dict[str, list[str]] = {}  # 공급 묶음 → 여러 행이 나눠 가진 병합 칸 수량
    complex_totals: list[dict[str, Any]] = []
    for count, cell in pending_pools:  # 병합된 한 칸의 수량을 여러 묶음이 쓰면 함께 쓰는 모집 물량입니다(합산하지 않음)
        if len(shared.get(cell, ())) > 1:
            if cell[2] == "TOTAL_HOUSING":
                # 여러 행에 병합된 건설·총 세대수는 단지 전체 수라 행(묶음)마다의 수가 아닙니다. 묶음 수량 칸 전체를 보류하지 않고 이 수만
                # 뺍니다(2026-10-24 여덟 번째 채점: 단지 총 세대수 때문에 행마다 따로 적힌 모집 호수까지 숨음)
                complex_totals.append(count)
                continue
            count["allocationPoolId"] = f"pool-t{_slug(cell[0])}-c{cell[1]}-{cell[2].lower()}"
            where = pool_column[cell]
            if count["value"] > 0 and subtotals.get(where) != sum(column_values.get(where, {}).values()):
                for group_id in sorted(shared[cell]):
                    shown_values = merged_counts.setdefault(group_id, [])
                    if str(count["value"]) not in shown_values:
                        shown_values.append(str(count["value"]))
    if complex_totals:
        dropped = {id(count) for count in complex_totals}
        for group in groups:
            group["counts"] = [count for count in group["counts"] if id(count) not in dropped]
    groups = _join_type_tables(groups)
    issues = []
    if unread:
        # 묶음을 가리키지 않아 공급 섹션 이슈가 됩니다. 판정 섹션이 아니라 메모로 내려가고 공고는 공개한 채 검수 대기열에 오릅니다
        # (verifier.NOTE_CODES·DROPPED_VALUE_CODES): 읽은 가격은 그대로 두고 빠진 가격만 사람이 채웁니다
        issues.append(
            {
                "supplyGroupId": None,
                "code": PRICE_TABLE_UNREAD,
                "description": f"가격표 {', '.join(unread[:4])}에 행마다 어느 주택형·대상의 금액인지 정할 칸이 없어(예: 소득 구간별 임대조건) "
                "가격을 넣지 못했습니다. 원문의 가격을 확인해야 합니다",
            }
        )
    if crammed:
        issues.append(
            {
                "supplyGroupId": None,
                "code": PRICE_TABLE_UNREAD,
                "description": f"가격표 {', '.join(crammed[:4])}의 금액 칸에 금액이 여럿 붙어 있어(위아래 행이 한 칸으로 읽힘) 어느 행의 가격인지 "
                "정하지 못해 넣지 못했습니다. 원문의 가격을 확인해야 합니다",
            }
        )
    for group in groups:
        _merge_payment_parts(group)
        for price in group["prices"]:
            price.pop("_attached", None)
        group.pop("_plans")
        group.pop("_merged_cells", None)
        group.pop("_unit", None)
        group.pop("_anonymous", None)
        name = group.get("unitLabel") or group.get("housingTypeCode") or group["id"]
        uncertain = group.pop("_scope_uncertain", None)
        if uncertain:
            shown = ", ".join(f"{where}(「{word}」)" for where, word in list(uncertain.items())[:3])
            issues.append(
                {
                    "supplyGroupId": group["id"],
                    "code": SCOPE_UNCERTAIN,
                    "field": "prices",  # 요금의 적용 대상만 애매하므로 가격만 보류합니다(수량은 그대로 게시)
                    "description": f"「{name}」 가격표 {shown}가 특정 대상의 요금으로 보이는데 대상이 정해지지 않아 기본 요금으로 게시하지 않았습니다. "
                    "원문에서 적용 대상을 확인해야 합니다",
                }
            )
        types = group.pop("_type_ambiguous", None)
        if types:
            issues.append(
                {
                    "supplyGroupId": group["id"],
                    "code": TYPE_AMBIGUOUS,
                    "description": f"「{name}」 표 제목에 주택형이 여럿({', '.join(types)})이라 이 행의 주택형을 정하지 못했습니다. 원문 확인이 필요합니다",
                }
            )
        if group["id"] in merged_counts:
            issues.append(
                {
                    "supplyGroupId": group["id"],
                    "code": COUNT_MERGED,
                    "field": "counts",  # 수량만 애매하므로 그 묶음의 수량 칸만 보류합니다(가격은 그대로 게시)
                    "description": f"「{name}」 수량 {', '.join(merged_counts[group['id']])}은(는) 병합된 한 칸을 여러 행이 나눠 가진 값이라 "
                    "이 행만의 수인지 정하지 못했습니다(표 합계로도 확인되지 않음). 원문 확인이 필요합니다",
                }
            )
        siblings = [
            g for g in groups if g is not group and _norm(g.get("housingTypeCode")) == _norm(group.get("housingTypeCode")) and group.get("housingTypeCode")
        ]
        issues += _direction_issues(group, name, [p for g in siblings for p in g["prices"]])
        cells = group.pop("_unsplit", None)
        if cells:
            issues.append(
                {
                    "supplyGroupId": group["id"],
                    "code": UNSPLIT_ISSUE,
                    "field": "prices",  # 못 나눈 금액은 가격만 보류합니다(수량은 게시, 2026-10-24 다섯 번째 채점)
                    "description": f"「{name}」 {', '.join(cells[:3])}에 금액이 여럿인데 어느 요금안(보증금 증액·감액)의 값인지 정하지 못해 넣지 않았습니다. "
                    "원문 확인이 필요합니다",
                }
            )
    part: dict[str, Any] = {
        "quotes": quotes,
        "supplyGroups": groups,
        "missingFields": [],
        "coverage": {"supplyGroups": {"status": "EXTRACTED", "reason": None}},
    }
    if issues:
        part[ISSUES_KEY] = issues
    locations = _address_locations(groups)
    if locations:
        part["locations"] = locations
    return part


def _direction_issues(group: dict[str, Any], name: str, fallback: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """전환안 방향을 기본 요금과 숫자로 검산합니다(assemble.conversion). 부호와 숫자가 어긋나고 숫자로 방향이 분명하면 숫자를 따르고
    표시 메모(CONVERSION_DIRECTION_CORRECTED)를, 숫자로도 정할 수 없으면 그 묶음의 가격만 보류하는 검수 이슈를 남깁니다."""
    issues = []
    for plan_id, (stage, numeric) in plan_directions(group["prices"], fallback).items():
        if numeric == UNCHECKED or numeric == stage:
            continue
        if numeric == SAME_AS_BASE:  # 기본 조건을 그대로 옮긴 가짜 전환안: 보류하지 않고 뺍니다(같은 묶음의 맞는 가격까지 숨기지 않게)
            group["prices"] = [p for p in group["prices"] if p.get("pricePlanId") != plan_id]
            continue
        if numeric is None:
            issues.append(
                {
                    "supplyGroupId": group["id"],
                    "code": DIRECTION_UNCERTAIN,
                    "field": "prices",
                    "description": f"「{name}」 전환안({plan_id})의 보증금·월세가 기본 요금과 비교해 증액·감액 어느 쪽으로도 맞지 않습니다. "
                    "원문 확인이 필요합니다",
                }
            )
            continue
        down = numeric == "CONVERSION_DEPOSIT_DOWN"
        for price in group["prices"]:
            if price.get("pricePlanId") == plan_id:
                price["priceStage"] = numeric
                scope = price["scope"]
                scope["description"] = re.sub(r"\(보증금 (?:증액|감액)\)", f"(보증금 {'감액' if down else '증액'})", scope["description"])
        issues.append(
            {
                "supplyGroupId": group["id"],
                "code": DIRECTION_CORRECTED,
                "field": "prices",
                "description": f"「{name}」 전환안({plan_id})의 표 부호는 {'증액' if down else '감액'}이지만 기본 요금보다 보증금이 "
                f"{'줄고 월세가 늘어' if down else '늘고 월세가 줄어'} 보증금 {'감액' if down else '증액'}안으로 고쳤습니다",
            }
        )
    return issues


def _address_locations(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """주소 칸이 있으면 주소마다 위치 하나를 만들고 묶음에 잇습니다(실측 2026-10-20 LH 대구경북 엑셀 565호·주소 258곳:
    AI 구조 호출은 위치를 10곳만 만들어 호실이 위치·지역에 이어지지 않음). 지역 코드는 결합기가 주소로 정합니다."""
    locations: list[dict[str, Any]] = []
    by_address: dict[str, dict[str, Any]] = {}
    names: dict[str, set[str]] = {}  # 주소 → 그 주소 행들의 단지 이름(주택군 칸)
    for group in groups:
        address = group.pop("_address", None)
        if not address:
            continue
        key = _norm(address)
        if key not in by_address:
            by_address[key] = {
                "id": f"loc-addr{len(by_address) + 1}",
                "kind": "BUILDING",
                "parentLocationId": None,
                "complexName": None,
                "buildingName": None,
                "address": address,
                "region": None,
                "quoteRefs": group["quoteRefs"][:1],
            }
            locations.append(by_address[key])
        if group.get("_complex"):
            names.setdefault(key, set()).add(group["_complex"])
        group["locationId"] = by_address[key]["id"]
    # 한 주소의 행이 모두 같은 단지 이름이면 위치에도 그 이름을 둡니다. 구조 호출이 같은 단지를 이름만으로 따로 만들었을 때
    # merge_into_structure가 이름으로 합쳐요(실측 2026-10-26 LH 청년 매입임대: 단지 3곳이 이름 위치·주소 위치로 두 번씩 나옴)
    for key, location in by_address.items():
        if len(names.get(key, ())) == 1:
            location["complexName"] = next(iter(names[key]))
    return locations


AMOUNT_IN_CELL = re.compile(r"\d[\d,]*(?:\.\d+)?")
LIMIT_WORDS = re.compile(r"한도|가능\s*금|전환\s*금")
TYPE_CODE_AREA = re.compile(r"\s*0*(\d{1,3}\.\d{2})\d{2}[A-Z]")  # LH 주택형 코드: 전용면적(소수 넷째 자리까지) + 형 문자
SPACED_AMOUNTS = re.compile(r"\d[\d,.]*\s+\d")  # 공백으로 떨어진 두 금액(위아래 두 줄이 한 칸)
# 전환 한도 칸의 증액·감액 표시(2026-10-23). 「(+)」「(-)」만 보던 것을 화살표·낱말까지 넓혔습니다(「↑ 2,000 ↓ 1,000」「증액 2,000 감액 1,000」.
# 예전엔 이런 한도 칸 옆의 두 금액 칸을 조용히 버렸음). 맨 「-」은 금액 앞에 붙을 때만 감액 표시입니다(「(+) - (-) 10,000」의 가운데 「-」는 빈 값)
SIGN_MARK = re.compile(r"(?P<up>\(\s*\+\s*\)|\+|[↑▲△]|증액|상향)|(?P<down>\(\s*[-−–]\s*\)|[-−–](?=\s*\d)|[↓▼▽]|감액|하향)")
UNSPLIT_ISSUE = "SUPPLY_PRICE_MISSING"  # 못 나눈 두 금액 칸: 금액 빈칸과 같은 검수 이슈(그 묶음 보류, AI 재확인 안 함)
ISSUES_KEY = CODE_ISSUES  # 코드 조각이 결합기에 넘기는 검수 이슈(공급 묶음 id로 가리킴). 계약 칸이 아니라 결합기가 꺼내 씁니다


def _sign_lines(sign: str) -> list[tuple[str, bool | None]]:
    """한도 칸의 증액·감액 표시를 적힌 순서대로, 표시마다 바로 뒤에 금액이 있는지(있으면 True, 「-」(없음)이면 False, 아무것도 없으면 None).
    「(-) 4,880,000 (+) 4,870,000 (+) 11,360,000」 → [((-), True), ((+), True), ((+), True)], 「(+) - (-) 10,000」 → [((+), False), ((-), True)]."""
    marks = list(SIGN_MARK.finditer(sign or ""))
    out: list[tuple[str, bool | None]] = []
    for n, mark in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else len(sign)
        rest = sign[mark.end() : end].strip()
        out.append(("(+)" if mark["up"] else "(-)", True if AMOUNT_IN_CELL.search(rest) else False if re.fullmatch(r"[-−–]+", rest) else None))
    return out


def _direction_amounts(sign: str) -> dict[str, bool]:
    """한도 칸의 부호마다 그 방향 전환이 있는지: 바로 뒤에 금액이 있으면 True, 「-」(없음)이면 False, 아무것도 없으면(부호만 적는
    「증감 구분」 칸) 정하지 않습니다(사전에 넣지 않음). 「(+) - (-) 10,000」 → {「(+)」: False, 「(-)」: True}, 「(+)」 → {}."""
    out: dict[str, bool] = {}
    for key, has_amount in _sign_lines(sign):
        if has_amount:
            out[key] = True
        elif has_amount is False and key not in out:
            out[key] = False
    return out


def _entry_direction(column: dict[str, Any], title: str) -> str | None:
    """가격 열 답이 말하는 전환 방향(「(+)」 증액, 「(-)」 감액). build_part의 요금 단계처럼 열 제목·요금안 이름의 방향 낱말이 답의 priceStage보다
    먼저입니다. 전환안이 아니면 None."""
    stage = column.get("priceStage")
    if stage in (None, "STANDARD", "CONVERSION_DEPOSIT_UP", "CONVERSION_DEPOSIT_DOWN"):
        stage = _stage_words(f"{title} {column.get('plan') or ''}") or stage
    return {"CONVERSION_DEPOSIT_UP": "(+)", "CONVERSION_DEPOSIT_DOWN": "(-)"}.get(stage or "")


def _pick_lines(column: dict[str, Any], peers: list[tuple[dict[str, Any], str]], marks: list[str]) -> list[int] | None:
    """여러 줄 칸에서 이 가격 열 답이 가져갈 줄 번호. 같은 열을 전환 방향마다 여러 번 답했으면(bmc-75: 감액·증액·최대 증액) 같은 방향 답의
    순서대로 그 방향 줄을 하나씩, 그 방향 답이 하나면 그 방향 줄을 모두 가져갑니다. 같은 방향 답과 줄의 수가 맞지 않으면 None(나누지 않음).
    한 번만 답한 열은 모든 줄을 가져가고 줄마다 증감 표시로 방향을 정합니다."""
    way = next((w for p, w in peers if p is column), None)
    if len(peers) < 2 or way is None:
        return list(range(len(marks)))
    mine = [i for i, mark in enumerate(marks) if mark == way]
    same_way = [p for p, w in peers if w == way]
    if len(same_way) == len(mine):
        return [mine[next(n for n, p in enumerate(same_way) if p is column)]]
    return mine if len(same_way) == 1 else None


def _borrow_keys(entries: list[dict[str, Any]], by_label: dict[str, Table]) -> None:
    """이름 칸 없이 답한 공급표가 열 제목이 글자까지 같은 다른 공급표의 답과 같다면 그 표의 이름 칸(호·주택형 등)을 빌립니다.
    실측 2026-10-20 LH 김해·양산 일반매각: 단지마다 「1.호 | 2.주거 전용 | … | 7.분양가격 계」 표 13개 중 하나만 1열을 호실로 답해
    나머지 12개 표(140호, 가격 420개)가 묶음 없이 빠짐. 이름 칸 밖의 열 의미가 같을 때만 빌립니다(다른 모양의 표에는 쓰지 않음)."""

    def table_of(entry: dict[str, Any]) -> Table | None:
        return by_label.get(str(entry.get("table"))) or by_label.get(LABEL_NOISE.sub("", str(entry.get("table") or "")))

    def others(entry: dict[str, Any]) -> list[tuple[int, str, str | None]]:
        return sorted(
            (int(c.get("column") or 0), c.get("meaning"), c.get("priceKind")) for c in entry.get("columns") or [] if c.get("meaning") not in KEY_MEANINGS
        )

    keyed = [e for e in entries if e.get("role") == "SUPPLY" and any(c.get("meaning") in KEY_MEANINGS for c in e.get("columns") or [])]
    for entry in entries:
        table = table_of(entry)
        if table is None or entry.get("role") != "SUPPLY" or any(c.get("meaning") in KEY_MEANINGS for c in entry.get("columns") or []):
            continue
        donors = [d for d in keyed if (t := table_of(d)) is not None and t.columns == table.columns and others(d) == others(entry)]
        keys = {json.dumps([c for c in d["columns"] if c.get("meaning") in KEY_MEANINGS], sort_keys=True) for d in donors}
        if len(keys) == 1:  # 빌려 줄 답들이 서로 같을 때만
            entry["columns"] = [*json.loads(keys.pop()), *entry["columns"]]
            if donors[0].get("rowUnit") and entry.get("rowUnit") != donors[0]["rowUnit"]:
                entry["rowUnit"] = donors[0]["rowUnit"]


def _split_shifted_pairs(values: dict[int, str], columns: list[dict[str, Any]]) -> None:
    """한 칸에 금액 둘이 붙고 바로 오른쪽 가격 칸이 비면 칸이 밀린 것입니다: 둘째 금액을 오른쪽 칸으로 옮깁니다
    (실측: LH 양산 「4,551 154,980」 | 「」 — 감액 보증금과 월임대료)."""
    prices = {c["column"] - 1 for c in columns if c["meaning"] in ("PRICE", "CONVERSION_LIMIT")}
    for c in sorted(prices):
        value = values.get(c) or ""
        amounts = AMOUNT_IN_CELL.findall(value)
        right = (values.get(c + 1) or "").strip()
        # 옆 칸이 같은 값의 복제(가로 병합 칸이 풀려 두 칸에 같은 글이 들어감, 2026-10-24 다섯 번째 채점)여도 빈칸으로 봅니다
        if len(amounts) == 2 and SPACED_AMOUNTS.search(value) and c + 1 in prices and (not right or right == value.strip()):
            values[c], values[c + 1] = amounts[0], amounts[1]


def _add_price(
    group: dict[str, Any], column: dict[str, Any], title: str, refs: list[str], value: str, plan: str, stage: str, line: tuple[int, int] | None = None
) -> None:
    """공급 묶음에 표 칸 하나의 가격을 붙입니다. 같은 요금안·단계·대상이면 같은 요금안 ID를 쓰고(여러 줄 칸의 금액은 같은 행·같은 줄이면),
    금액 앞 증감 부호는 뗍니다."""
    groups_for_price = [column["targetGroup"]] if column.get("targetGroup") else group["scope"]["targetGroups"]
    key = (plan, stage, tuple(groups_for_price)) if line is None else (line, tuple(groups_for_price))
    plan_id = group["_plans"].setdefault(key, f"{group['id']}.plan{len(group['_plans']) + 1}")
    amount = re.sub(r"^\(?[+\-−]\)?\s*", "", value.strip())
    kind = column["priceKind"]
    group["prices"].append(
        {
            "id": f"{group['id']}.price{len(group['prices']) + 1}",
            "kind": kind,
            "scope": _scope(group["id"], list(groups_for_price), f"{plan} 요금안입니다."),
            "sourceAmount": amount,
            "sourceUnit": _unit(column, title),
            "quoteRefs": list(dict.fromkeys(refs)),
            "taxTreatment": "UNKNOWN",
            "vatRate": None,
            "billingPeriod": "MONTHLY" if kind == "MONTHLY_RENT" else "ONCE",
            "pricePlanId": plan_id,
            "priceStage": stage,
        }
    )


COUNT_TITLE_KINDS = (  # 앞에서부터 먼저 맞는 것. 「모집」이 없는 「호수·세대수」는 대상 주택 수(사용자 결정 2026-10-17: 대상 주택 수와 모집 수를 따로 셈)
    (re.compile(r"대기"), "WAITLIST"),
    (re.compile(r"공가"), "CURRENT_VACANCIES"),
    (re.compile(r"모집|금회|공급\s*세대|예비"), "OFFERED"),
    (re.compile(r"호\s*수|세대\s*수|건설|총\s*세대"), "TOTAL_HOUSING"),
)


def _count_kind_from_title(title: str) -> str | None:
    """열 의미 답이 countKind를 비웠을 때 열 제목으로 고르는 수량 종류. 정할 수 없으면 None(그 열은 쓰지 않음)."""
    for pattern, kind in COUNT_TITLE_KINDS:
        if pattern.search(title or ""):
            return kind
    return None


def _sign(row: list[str], limit_column: int | None) -> str:
    """전환 증감 부호: 한도 칸이 있으면 그 칸, 없으면 「(+)」「(-)」만 적힌 칸(전환 구분)."""
    if limit_column is not None and limit_column < len(row):
        return row[limit_column].strip()
    return next((v.strip() for v in row if v and SIGN_CELL.fullmatch(v.strip())), "")


# 전환 방향 낱말(2026-10-23 전환 보증금 점검). 예전엔 priceStage를 비워 답한 전환 열을 이름에 「전환」만 보고 모두 증액(UP)으로 두어,
# 「보증금 감액 시 월임대료」 같은 열이 증액안으로, 「감액」이라고만 적힌 열(「전환」 낱말 없음)은 기본(STANDARD)으로 게시될 수 있었습니다
DEPOSIT_DOWN_WORDS = re.compile(
    r"보증금\s*(?:을|를)?\s*(?:감액|하향|인하|낮)|(?:감액|하향)\s*(?:전환|시|형|안)|전환\s*\(?\s*(?:감액|하향)|최소\s*보증금|보증금\s*최소"
    # 보증금 없이 월세만 내는 안(「무보증금 월세」「무보증전환 임대료」)도 보증금을 내린 전환안입니다(2026-10-23: STANDARD로 답해 기본 요금처럼 보였음)
    r"|무\s*보증"
)
DEPOSIT_UP_WORDS = re.compile(
    r"보증금\s*(?:을|를)?\s*(?:증액|상향|인상|올)|(?:증액|상향)\s*(?:전환|시|형|안)|전환\s*\(?\s*(?:증액|상향)|최대\s*보증금|보증금\s*최대"
)


def _stage_words(text: str) -> str | None:
    """열 제목·요금안 이름이 말하는 전환 방향. 두 방향 낱말이 함께 있으면(「보증금 증액·감액」) 정하지 않습니다(None)."""
    down, up = bool(DEPOSIT_DOWN_WORDS.search(text)), bool(DEPOSIT_UP_WORDS.search(text))
    if down == up:
        return None
    return "CONVERSION_DEPOSIT_DOWN" if down else "CONVERSION_DEPOSIT_UP"


def _guess_stage(column: dict[str, Any], plan: str, limit_column: int | None, first_price: int, sign: str) -> str:
    """priceStage를 비워 답한 열(실측: 인천 행복주택 「최대전환」 열): 한도 칸 오른쪽·이름에 「전환」·첫 가격 열이 아니면서 부호 행이면 전환안."""
    after_limit = limit_column is not None and column["column"] - 1 > limit_column
    if after_limit or "전환" in plan or (sign and column["column"] != first_price and "기본" not in plan and "기준" not in plan):
        return "CONVERSION_DEPOSIT_UP"  # 부호가 있으면 아래에서 증액·감액으로 나눕니다
    return "STANDARD"


def _with_suffix(value: str, suffix: str) -> str:
    return f"{value}{suffix}" if re.fullmatch(r"[\dA-Za-z-]+", value) else value


def _unit_label(named: dict[str, str], row_unit: Any) -> str | None:
    """호실 이름. 호실 행에 동 칸도 있으면 「301동 402호」(2026-10-24 여섯 번째 채점: 동마다 같은 호 번호 「402」가 4개 나와 어느 집인지 구분 못 함)."""
    unit, building = named.get("UNIT"), named.get("BUILDING")
    if unit and building and building not in unit:
        return f"{_with_suffix(building, '동')} {_with_suffix(unit, '호')}"
    return unit or (named.get("COMPLEX") if row_unit == "BUILDING" else None)


# 금액 구성(2026-10-24 여섯 번째 채점: 분양가는 「기본 요금안」, 계약금·잔금은 「분양대금 납부 요금안」으로 나뉘어 한 집의 금액이 두 안처럼 보임).
# 같은 묶음·같은 대상에서 계약금·중도금·잔금의 합이 분양가(또는 보증금)와 같으면 그 금액들을 분양가 요금안으로 옮깁니다
PART_KINDS = ("CONTRACT_PAYMENT", "BALANCE")
WHOLE_KINDS = ("SALE_PRICE", "DEPOSIT")


def _merge_payment_parts(group: dict[str, Any]) -> bool:
    plans: dict[str, list[dict[str, Any]]] = {}
    for price in group["prices"]:
        plans.setdefault(price.get("pricePlanId") or "", []).append(price)

    def amount(price: dict[str, Any]) -> tuple[float, str] | None:
        found = AMOUNT_IN_CELL.findall(str(price.get("sourceAmount") or ""))
        return (float(found[0].replace(",", "")), str(price.get("sourceUnit") or "")) if len(found) == 1 else None

    moved = False
    for part_id, parts in plans.items():
        if not parts or any(p.get("kind") not in PART_KINDS for p in parts):
            continue
        values = [amount(p) for p in parts]
        if any(v is None for v in values) or len({v[1] for v in values}) != 1:
            continue
        total, unit = sum(v[0] for v in values), values[0][1]
        stage, targets = parts[0].get("priceStage"), parts[0]["scope"]["targetGroups"]
        wholes = [
            plan_id
            for plan_id, items in plans.items()
            if plan_id != part_id
            and not any(p.get("kind") in PART_KINDS for p in items)
            and any(
                p.get("kind") in WHOLE_KINDS and p.get("priceStage") == stage and p["scope"]["targetGroups"] == targets and amount(p) == (total, unit)
                for p in items
            )
        ]
        if len(wholes) == 1:
            for price in parts:
                price["pricePlanId"] = wholes[0]
            moved = True
    return moved


# 한 행이 같은 번호의 주택형 여럿을 함께 적은 표기(「19A/B/C」「26A·B」)
SHARED_TYPES = re.compile(r"(\d+)([A-Za-z][A-Za-z0-9]*)((?:\s*[/·ㆍ,]\s*[A-Za-z][A-Za-z0-9]*)+)")
TYPE_SEPARATOR = re.compile(r"\s*[/·ㆍ,]\s*")


def _type_names(group: dict[str, Any]) -> set[str]:
    """주택형 이름들: 코드가 칸 둘을 이어 쓴 것(「24 24ABC」 = 공급형 + 청약 구분)이면 글자가 든 낱말(「24ABC」)도 따로 봅니다.
    앞의 공급형 숫자를 뗀 나머지도 공백·쉼표를 빼고 봅니다. 공급표 「35 35A1,B1」과 가격표 「35A1, B1」은 같은 주택형인데
    낱말로만 나누면 「35A1,B1」과 「35A1,」·「B1」이 되어 짝이 안 맞았음(2026-10-28 GH 행복주택 파주 병원 복합).
    「19A/B/C」처럼 여럿을 함께 적은 표기는 각 주택형(19A·19B·19C)으로도 봅니다(2026-11-07 23건 대조 umca-4439: 가격 행 「19A/B/C」가
    19A·19B·19C 모집 묶음에 붙지 않고 따로 남아 가격 48개가 빠짐)."""
    raw = str(group.get("housingTypeCode") or "")
    words = raw.split()
    lettered = {w.upper() for w in words if re.search(r"[A-Za-z]", w)}
    rest = _norm(" ".join(words[1:])).upper() if len(words) > 1 and re.fullmatch(r"\d+", words[0]) else ""
    shared = {f"{match[1]}{suffix}".upper() for match in SHARED_TYPES.finditer(raw) for suffix in [match[2], *TYPE_SEPARATOR.split(match[3].strip(" /·ㆍ,"))]}
    return {_norm(raw).upper(), *lettered, rest, *shared} - {""}


def _same_type(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """같은 주택형인지: 코드가 같거나, 글자가 든 주택형 이름이 겹침(2026-10-24 여덟 번째 채점: 「24 24ABC」 수량 묶음과 「24ABC」 가격 행이 짝이 안 맞음)."""
    return bool(_type_names(a) & _type_names(b))


def _housing_number(group: dict[str, Any]) -> float | None:
    for text in (group.get("housingTypeCode"), group.get("unitLabel")):
        # 소수점 뒤에 공백이 낀 번호(PDF 글자 사이 공백)는 한 숫자입니다(2026-11-07 23건 대조 jbdc-16011: 모집 표 「059. 9288 A」가 59로 읽혀
        # 가격표 「059.9288A」(59.9288) 행이 모집 묶음에 붙지 않음)
        found = HOUSING_NUMBER.findall(SPLIT_DECIMAL.sub(r"\1.\2", text or ""))
        if found:
            return float(found[0])  # 「0039 (복층형)」「39㎡」「39 (일반형)」 → 39
    return group.get("exclusiveAreaSqm")


def _within_area_range(group: dict[str, Any], number: float) -> bool:
    """가격표가 주택형 대신 전용면적(39.70·39.87)으로 행을 나눴고, 공급표는 주택형 39에 면적 범위(39.70 ~ 39.87)를 적은 경우
    (실측 LH 부산당감 50년 공공임대: 가격 12개가 모집 수 없는 묶음으로 따로 남음). 범위 안이고 정수 부분이 주택형 번호와 같아야 합니다."""
    span = group.get("exclusiveAreaRange")
    own = _housing_number(group)
    return bool(span) and own is not None and int(own) == int(number) and span["min"] <= number <= span["max"]


def _attach_price_tables(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """모집 수량 없는 가격표 행(실측: SH 「신정도시마을 39㎡」 임대료 표 한 행)을 다른 표의 같은 단지·같은 면적 번호 모집 묶음 모두에 붙입니다.
    그 행의 총 세대수(단지 전체 수)는 묶음마다 붙이면 겹치므로 붙이지 않습니다. 맞는 모집 묶음이 없으면 그 행은 그대로 둡니다."""

    def offered(group: dict[str, Any]) -> bool:
        return any(c["kind"] in SUPPLY_COUNT_KINDS for c in group["counts"])

    def table_of(group: dict[str, Any]) -> str:
        return group["id"].rsplit("-r", 1)[0]

    with_counts = [g for g in groups if offered(g)]
    complexes = {_norm(g.get("_complex")) for g in groups} - {""}
    per_table: dict[str, set[str]] = {}
    for g in groups:
        per_table.setdefault(table_of(g), set()).add(_norm(g.get("_complex")))

    def same_complex(a: str, b: str) -> bool:
        return len(complexes) <= 1 or not a or not b or a in b or b in a  # 이름 칸이 빈 행(병합 정보 없음)은 어느 단지와도 맞춤

    def single_complex(a: dict[str, Any], b: dict[str, Any]) -> bool:
        # 표가 둘이고 각각 단지 하나뿐이면 이름이 조금 달라도 같은 단지(실측: 「충북혁신 A-4블록 (천년나무4)」 ↔ 「충북혁신4 (천년나무4)」).
        # 단, 이름의 핵심이 같아야 합니다. 표마다 단지가 하나뿐이라는 이유만으로 「하늘마을 B단지」 가격이 「가람마을 A단지」에 붙었음(재현 2026-10-20)
        return (
            len(per_table) == 2
            and len(per_table[table_of(a)] - {""}) == 1
            and len(per_table[table_of(b)] - {""}) == 1
            and _same_core(a.get("_complex"), b.get("_complex"))
        )

    kept: list[dict[str, Any]] = []
    for group in groups:
        # 대상이 정해지지 않은 대상 한정 요금표·주택형을 정하지 못한 행은 다른 표의 모집 묶음에 붙이지 않습니다(따로 남아 보류)
        if offered(group) or not group["prices"] or group.get("_scope_uncertain") or group.get("_type_ambiguous"):
            kept.append(group)
            continue
        number, name = _housing_number(group), _norm(group.get("_complex"))
        groups_of = set(group["scope"]["targetGroups"])
        targets = [
            g
            for g in with_counts
            if table_of(g) != table_of(group)
            and number is not None
            and (_housing_number(g) == number or _within_area_range(g, number))
            and (same_complex(name, _norm(g.get("_complex"))) or single_complex(group, g))
            # 대상 계층이 둘 다 적혀 있으면 맞아야 합니다(실측: 포항 전세보증금 표의 계층별 5행이 21A 묶음마다 모두 붙음)
            and _classes_match(groups_of, set(g["scope"]["targetGroups"]))
        ]
        if number is None and name:
            # 주택형·면적 없이 단지 이름으로만 행을 나눈 가격표: 다른 표에 같은 이름의 모집 묶음이 딱 하나면 그 묶음의 가격입니다
            # (2026-11-06 V2 5건 재측정 bmc-106: 단지별 모집표와 단지별 임대조건표가 나뉘어, 모집 묶음 4개는 가격 없이·가격 묶음 4개는 모집 수 없이
            #  남아 가격 빈칸 8개로 보류 — V1·V2 같음). 같은 이름의 모집 묶음이 둘 이상이면 어느 주택형인지 몰라 붙이지 않습니다
            same_name = [
                g
                for g in with_counts
                if table_of(g) != table_of(group) and _norm(g.get("_complex")) == name and _classes_match(groups_of, set(g["scope"]["targetGroups"]))
            ]
            targets = same_name if len(same_name) == 1 else []
        code = _norm(group.get("housingTypeCode")).upper()
        exact = [g for g in targets if code and _same_type(group, g)]
        if not exact and re.search(r"[A-Z]", code):
            # 가격 행이 글자까지 있는 주택형(「26C」)인데 똑같은 코드의 모집 묶음이 없으면, 숫자만 같은 다른 주택형(「26AB」)에는 붙이지 않습니다
            # (2026-10-24 일곱 번째 채점: 26C 고령자 가격이 26AB 묶음들에 붙어 위치 의심 156건). 코드가 숫자뿐인 묶음에는 붙입니다
            targets = [g for g in targets if not re.search(r"[A-Z]", _norm(g.get("housingTypeCode")).upper())]
        targets = exact or targets  # 주택형 코드가 똑같은 행이 있으면 그 행에만(59A·59A-1·59C가 모두 59.98)
        same = [g for g in targets if {_norm(x) for x in groups_of} == {_norm(x) for x in g["scope"]["targetGroups"]}]
        targets = same or targets  # 계층 이름이 똑같은 행이 있으면 그 행에만
        if len({_norm(g.get("_complex")) for g in targets} - {""}) > 1:
            targets = []  # 맞는 단지가 둘 이상이면 어느 단지 가격인지 정할 수 없어 붙이지 않습니다(가격 행은 따로 남아 사람이 확인)
        if not targets:
            kept.append(group)
            continue
        for target in targets:
            # 면적 범위 안의 행: 면적마다 다른 임대 조건이므로 요금안을 면적으로 나눕니다. 단지 이름으로만 붙인 행(번호 없음)은 나누지 않습니다
            by_range = number is not None and _housing_number(target) != number
            # 그 묶음의 원래 가격과 같은 값만 거릅니다. 다른 행(층)에서 붙인 가격과 비교하면 층마다 같은 융자금이 둘째 층부터 빠졌음
            # (2026-10-24 다섯 번째 채점: 층별 5행 가격표의 융자금 16개 누락)
            seen = {(p["kind"], p["sourceAmount"], p["priceStage"], tuple(p["scope"]["targetGroups"])) for p in target["prices"] if not p.get("_attached")}
            floor = group.get("floor") or group.get("unitLabel")
            plans: dict[str, str] = {}
            for price in group["prices"]:
                groups_for_price = price["scope"]["targetGroups"] or target["scope"]["targetGroups"]
                if (price["kind"], price["sourceAmount"], price["priceStage"], tuple(groups_for_price)) in seen:
                    continue  # 기본 임대 조건이 두 표에 되풀이된 경우
                suffix = f"-{_slug(str(number))}" if by_range else ""
                plan_id = plans.setdefault(price["pricePlanId"], f"{target['id']}.plan-{_slug(price['pricePlanId'])}{suffix}")
                description = f"전용 {number:g}㎡ {price['scope']['description']}" if by_range else price["scope"]["description"]
                if floor and floor not in description:
                    description = f"{floor} {description}"  # 층·호 구간이 다른 요금안을 구분합니다
                target["prices"].append(
                    {
                        **price,
                        "_attached": True,
                        "id": f"{target['id']}.price{len(target['prices']) + 1}",
                        "scope": _scope(target["id"], list(groups_for_price), description),
                        "pricePlanId": plan_id,
                    }
                )
            target["quoteRefs"] = list(dict.fromkeys([*target["quoteRefs"], *group["quoteRefs"]]))
            if group.get("_unsplit"):
                target.setdefault("_unsplit", []).extend(group["_unsplit"])
    return kept


def _join_type_tables(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 주택형을 두 표가 나눠 적은 공고(「주택형·전용면적·세대수」 표와 「주택형 × 계층별 모집 수」 표)의 묶음을 잇습니다
    (2026-11-07 23건 대조 dcco-24791·24804: 계층 묶음에 전용면적이 없어 21A가 면적·세대수 묶음과 계층별 모집 묶음으로 두 번 나오고,
    계층별 모집 수 15개가 같은 면적의 주택형 행과 이어지지 않음).
    - 면적: 면적 없는 묶음과 주택형 코드가 똑같은 다른 표 묶음(같은 단지)의 면적이 하나뿐이면 그 면적을 쓰고, 면적이 적힌 그 행도 인용합니다
    - 합계 묶음: 대상 없이 대상 주택 수만 적힌 묶음은, 같은 주택형의 다른 표 계층 묶음들이 모두 대상 주택 수를 따로 적었고 그 합이 같으면
      뺍니다(계층 묶음들이 같은 수를 나눠 가짐). 합이 다르거나 계층 묶음에 대상 주택 수가 없으면 그대로 둡니다"""
    complexes = {_norm(g.get("_complex")) for g in groups} - {""}

    def code(group: dict[str, Any]) -> str:
        return _norm(group.get("housingTypeCode")).upper()

    def has_area(group: dict[str, Any]) -> bool:
        return group.get("exclusiveAreaSqm") is not None or bool(group.get("exclusiveAreaRange"))

    def related(a: dict[str, Any], b: dict[str, Any]) -> bool:  # 다른 표의 같은 주택형(같은 단지)
        same_place = len(complexes) <= 1 or _norm(a.get("_complex")) == _norm(b.get("_complex"))
        return a is not b and _table_label(a) != _table_label(b) and bool(code(a)) and code(a) == code(b) and same_place

    for group in groups:
        if has_area(group):
            continue
        donors = [d for d in groups if related(group, d) and has_area(d)]
        if len({(d.get("exclusiveAreaSqm"), json.dumps(d.get("exclusiveAreaRange"), sort_keys=True)) for d in donors}) == 1:
            group["exclusiveAreaSqm"], group["exclusiveAreaRange"] = donors[0].get("exclusiveAreaSqm"), donors[0].get("exclusiveAreaRange")
            group["quoteRefs"] = list(dict.fromkeys([*group["quoteRefs"], donors[0]["quoteRefs"][0]]))
    kept = []
    for group in groups:
        totals = group["counts"]
        flagged = group.get("_unsplit") or group.get("_type_ambiguous") or group.get("_scope_uncertain")
        if totals and all(c["kind"] == "TOTAL_HOUSING" for c in totals) and not group["scope"]["targetGroups"] and not group["prices"] and not flagged:
            parts = [p for p in groups if related(group, p) and p["scope"]["targetGroups"]]
            shares = [[c["value"] for c in p["counts"] if c["kind"] == "TOTAL_HOUSING" and not c.get("allocationPoolId")] for p in parts]
            if parts and all(len(s) == 1 for s in shares) and sum(s[0] for s in shares) == sum(c["value"] for c in totals):
                continue
        kept.append(group)
    return kept


CLASS_NOTE = re.compile(r"\([^)]*\)")
# 같은 계층 안의 소득 유무 구분. 괄호 없이 칸을 나눠 적으면(「청 년」|「소득 有」) 대상이 「청 년 소득 有」로 이어져 계층 이름에 붙음
# (2026-11-07 23건 대조 umca-4439: 모집 표 「청년」과 맞지 않아 「19A/B/C」 가격 16개가 모집 묶음에 붙지 않음)
INCOME_PRESENCE = re.compile(r"소득\s*[有無]")


def _class_words(name: str) -> set[str]:
    """계층 이름의 낱말. 괄호 설명·소득 유무 구분은 빼고 「·」「,」「/」로 나눕니다: 「대학생· 청년(소득無)」 → {대학생, 청년}."""
    return {_norm(w) for w in re.split(r"[·․ㆍ・‧,/]", INCOME_PRESENCE.sub("", CLASS_NOTE.sub("", name))) if _norm(w)}


def _classes_match(a: set[str], b: set[str]) -> bool:
    """공급표와 임대조건표가 같은 계층을 다르게 적은 경우를 맞춥니다(실측 LH 인천석남 행복주택: 공급표 「대학생」「청년」
    「고령자 (주거약자용外)」 ↔ 임대조건표 「대학생· 청년(소득無)」「청년(소득有)」「고령자」라 가격 56개가 모집 수 없는 묶음으로 남음)."""
    if not a or not b:
        return True
    words_a = set().union(*(_class_words(x) for x in a))
    words_b = set().union(*(_class_words(x) for x in b))
    return bool(words_a & words_b)


def complex_names(part: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(g["_complex"] for g in part["supplyGroups"] if g.get("_complex")))


def has_counts(part: dict[str, Any]) -> bool:
    """코드가 옮긴 공급 묶음에 수량이 하나라도 있는지. 없으면(가격표만 옮김) 구조 호출이 주택형별 수량 묶음을 만듭니다."""
    return any(g["counts"] for g in part["supplyGroups"])


def structure_note(part: dict[str, Any]) -> str:
    names = complex_names(part)
    shown = ", ".join(names[:30]) or "(표에 단지 이름 칸 없음)"
    if has_counts(part):
        note = "공급 묶음(supplyGroups)은 프로그램이 공급표에서 직접 옮겼으므로 이 호출에서는 만들지 않습니다. "
    else:
        # 실측 2026-10-20 LH 대전대동2: 주택형별 공급 호수 표가 PDF에서 설명 칸에 섞여 읽혀 코드는 층별 분양가 표만 옮김(호수 0/8)
        note = (
            "공급·가격 표의 금액은 프로그램이 직접 옮겼습니다. 이 호출의 공급 묶음(supplyGroups)에는 원문의 주택형별 공급 호수·전용면적만 넣고 "
            "prices는 빈 배열로 둡니다. "
        )
    addresses = len(part.get("locations") or [])
    if addresses:
        note += f"첨부 목록의 주소 {addresses}곳은 프로그램이 위치로 만들었으므로 그 주소들의 위치는 만들지 않고, 목록 밖 위치(대상 지역 AREA 등)만 만듭니다. "
    return note + f"위치(locations)는 원문의 단지·주택마다 만들고, 단지 이름은 공급표의 이름을 그대로 씁니다: {shown}"


QUOTE_PREFIX = "tbl-"  # 코드 조각의 인용을 구조 호출 조각으로 옮길 때 붙이는 ref 머리(인용 ref는 조각 안에서만 유효)
AI_QUOTE_PREFIX = "ai-"
DIGITS = re.compile(r"\D")


def merge_into_structure(table_part: dict[str, Any], part: dict[str, Any]) -> set[str]:
    """코드가 만든 위치를 구조 호출 조각으로 옮기고(같은 주소의 AI 위치는 코드 위치로 합침), 구조 호출이 만든 수량 묶음은
    코드 조각의 공급 묶음 앞으로 옮깁니다(코드가 이미 옮긴 금액은 그 묶음에서 뺌). 인용도 함께 옮깁니다.
    돌려주는 값: 코드가 만든 위치 ID(뒤 호출에 넘기는 구조 요약에서는 뺍니다)."""
    code_locations = table_part.pop("locations", None) or []
    if code_locations and isinstance(part.get("locations"), list):
        known = {_norm(loc["address"]): loc["id"] for loc in code_locations}
        rename = {
            loc["id"]: known[_norm(loc["address"])]
            for loc in part["locations"]
            if isinstance(loc, dict) and isinstance(loc.get("address"), str) and _norm(loc["address"]) in known
        }
        # 주소 없이 이름만 있는 AI 위치: 그 이름의 코드 위치(주택군 칸 이름)가 하나뿐이면 같은 단지로 합칩니다
        by_name: dict[str, list[dict[str, Any]]] = {}
        named: set[str] = set()  # 이름으로 합친 코드 위치: 뒤 호출의 구조 요약에 남겨 그 id를 쓰게 해요(AI 위치 id는 사라짐)
        for loc in code_locations:
            if _norm(loc.get("complexName")):
                by_name.setdefault(_norm(loc["complexName"]), []).append(loc)
        for loc in part["locations"]:
            if not isinstance(loc, dict) or loc.get("id") in rename or isinstance(loc.get("address"), str) and loc["address"].strip():
                continue
            hits = {id(c): c for n in {_norm(loc.get("complexName")), _norm(loc.get("buildingName"))} - {""} for c in by_name.get(n, [])}
            if len(by_name.get(_norm(loc.get("complexName")), [])) > 1 or len(hits) != 1:
                continue
            [code] = hits.values()
            rename[loc["id"]] = code["id"]
            named.add(code["id"])
            code["kind"] = loc.get("kind") or code["kind"]
            code["buildingName"] = code.get("buildingName") or loc.get("buildingName")
            code["quoteRefs"] = list(dict.fromkeys([*code.get("quoteRefs", []), *(loc.get("quoteRefs") or [])]))
        part["locations"] = [loc for loc in part["locations"] if not (isinstance(loc, dict) and loc.get("id") in rename)]
        _rename_locations(part, rename)
        _move_quotes(table_part, part, code_locations, QUOTE_PREFIX)
        part["locations"].extend(code_locations)
        coverage = part.get("coverage")
        if isinstance(coverage, dict) and (coverage.get("locations") or {}).get("status") not in ("EXTRACTED", "PARTIAL"):
            coverage["locations"] = {"status": "EXTRACTED", "reason": None}
    else:
        code_locations, named = [], set()
    counted = has_counts(table_part)
    groups = part.pop("supplyGroups", None)  # 수량을 코드가 옮겼으면 이 호출에 묶음을 맡기지 않았으므로 버립니다(겹침 방지)
    if isinstance(groups, list) and groups and not counted:
        amounts = {DIGITS.sub("", p["sourceAmount"]) for g in table_part["supplyGroups"] for p in g["prices"]}
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("prices"), list):
                group["prices"] = [p for p in group["prices"] if not (isinstance(p, dict) and DIGITS.sub("", str(p.get("sourceAmount"))) in amounts)]
        _move_quotes(part, table_part, groups, AI_QUOTE_PREFIX)
        table_part["supplyGroups"] = [*groups, *table_part["supplyGroups"]]
        coverage = part.get("coverage")
        if isinstance(coverage, dict):
            coverage.pop("supplyGroups", None)
    return {loc["id"] for loc in code_locations} - named


def _rename_locations(node: Any, rename: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("locationId", "parentLocationId") and value in rename:
                node[key] = rename[value]
            elif key == "locationIds" and isinstance(value, list):
                node[key] = list(dict.fromkeys(rename.get(v, v) for v in value))
            else:
                _rename_locations(value, rename)
    elif isinstance(node, list):
        for value in node:
            _rename_locations(value, rename)


def _move_quotes(source: dict[str, Any], target: dict[str, Any], items: list[Any], prefix: str) -> None:
    """items가 쓰는 source 조각의 인용을 target 조각으로 복사하고 items의 ref에 prefix를 붙입니다."""
    quotes = {q.get("ref"): q for q in source.get("quotes") or [] if isinstance(q, dict)}
    target_quotes = target.setdefault("quotes", [])
    have = {q.get("ref") for q in target_quotes if isinstance(q, dict)}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("quoteRefs"), list):
                refs = []
                for ref in node["quoteRefs"]:
                    if ref in quotes:
                        if prefix + ref not in have:
                            target_quotes.append({**quotes[ref], "ref": prefix + ref})
                            have.add(prefix + ref)
                        ref = prefix + ref
                    refs.append(ref)
                node["quoteRefs"] = refs
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(items)


def _norm(text: str | None) -> str:
    return re.sub(r"[\s·․ㆍ・‧.,()\[\]\-~]", "", text or "")


ALIAS = re.compile(r"\(([^)]*)\)")
# 단지 이름에 흔히 붙는 일반 낱말. 이것만 같으면 같은 단지로 보지 않습니다
GENERIC_COMPLEX_WORDS = re.compile(r"단지|마을|아파트|주택|블록|지구|행복|공공|임대|국민|영구|매입|전세")


def _core(name: str) -> str:
    """괄호 밖 이름의 한글만 남기고 일반 낱말을 뺍니다: 「충북혁신 A-4블록」 → 충북혁신, 「가람마을 A단지」 → 가람."""
    return GENERIC_COMPLEX_WORDS.sub("", re.sub(r"[^가-힣]", "", ALIAS.sub("", name)))


def _same_core(a: str | None, b: str | None) -> bool:
    """다르게 적은 두 단지 이름이 같은 단지인지. 괄호 속 별칭이 같거나(천년나무4 = 천년나무4),
    일반 낱말을 뺀 한글 이름이 2자 이상이고 한쪽이 다른 쪽에 들어 있어야 합니다(충북혁신 ⊂ 충북혁신).
    공통 글자만 보면 「부산당감」 「부산명지」처럼 지역 이름이 같은 다른 단지가 붙으므로 포함 관계로만 봅니다."""
    a, b = a or "", b or ""
    names_a = {_norm(x) for x in ALIAS.findall(a)} | {_norm(ALIAS.sub("", a))}
    names_b = {_norm(x) for x in ALIAS.findall(b)} | {_norm(ALIAS.sub("", b))}
    aliases = {_norm(x) for x in ALIAS.findall(a)} | {_norm(x) for x in ALIAS.findall(b)}
    if any(len(x) >= 2 and x in names_a and x in names_b for x in aliases):
        return True
    core_a, core_b = _core(a), _core(b)
    short, long = sorted((core_a, core_b), key=len)
    return len(short) >= 2 and short in long


def link_locations(part: dict[str, Any], locations: list[dict[str, Any]]) -> None:
    """표의 단지 이름 ↔ 구조 호출의 위치. 이름이 맞는 곳이 하나면 그 위치, 단지가 하나뿐이면 모두 그 단지."""
    complexes = [loc for loc in locations if isinstance(loc, dict) and loc.get("kind") != "BUILDING"] or [loc for loc in locations if isinstance(loc, dict)]
    for group in part["supplyGroups"]:
        name = _norm(group.pop("_complex", None))
        if group.get("locationId"):
            continue  # 주소 칸으로 정한 위치, 구조 호출이 정한 위치
        found = [
            loc["id"]
            for loc in locations
            if isinstance(loc, dict) and name and any(n and (n in name or name in n) for n in (_norm(loc.get("complexName")), _norm(loc.get("buildingName"))))
        ]
        if len(set(found)) == 1:
            group["locationId"] = found[0]
        elif len(complexes) == 1:
            group["locationId"] = complexes[0]["id"]


def parse_mapping(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
    except ValueError:
        return None
    return value if isinstance(value, dict) and isinstance(value.get("tables"), list) else None
