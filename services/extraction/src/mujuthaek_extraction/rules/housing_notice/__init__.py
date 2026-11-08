"""주거 공고 추출 규칙. 호출 순서: 구조 → 일정·안내 → 자격·선정·서류 (결정 E2).

v2(2026-10-16): 필수 항목 체크리스트, 분양 납부 조건, 미적용·불문 기준, 예외·조건식 형식, 수량 묶음 기본값, 신청 방식 규칙.
v3(2026-10-16): 서비스(판정·상세 화면·알림)에 쓰이는 항목만 뽑고 나머지는 "넣지 않음"으로 명시. 호실별 가격은 묶지 않음.
v4(2026-10-16): 주택 미정 공고(전세임대·별첨 목록 매입임대)의 공통 비용, 순위별 자격 기준 구조화, 호실이 많은 공고의 이어받기 호출(continuation).
v5(2026-10-16): 서비스 상세 화면 기준(참고: 주거나침반) — 안내(guidance: 신청 방법·주의사항·입주·거주 유의·문의처) 섹션 추가(일정 호출에서 함께),
    가점 배점표 행마다 항목, 계약·입주처럼 날짜 없는 필수 단계도 일정으로, 선착순·잔여세대의 서류 제출·계약은 신청으로도 표시, 지역은 시·군·구 접미사까지.
v6(2026-10-16): 순위·대상별 접수 기간은 APPLICATION 일정을 따로(알림을 순위별로), 누락 기록은 값이 null인 칸 하나만(값을 채운 칸·조건식 전체 금지).
v7(2026-10-16): 가점 배점표의 감점 행은 points를 음수로(실측: GH 국민임대 감점 -5·-3점이 형식 위반으로 걸려 자격·선정·서류가 빠짐).
v8(2026-10-16): 자산·소득 조사 해당자만 내는 증빙 서류 표도 서류로 넣습니다(실측: 12건 시험에서 두 정답표 모두 넣은 이 표가 여러 공고에서 통째로 빠짐).
v9(2026-10-16): 범위로만 적힌 면적은 exclusiveAreaRange, 금액은 sourceAmount에 범위 표기 그대로(계약 범위 칸 추가, 대전도시공사 정정공고).
    구조 호출: 첨부 엑셀 공급주택목록이 원문에 붙어 있으면 주택별로, 없거나 잘렸으면 공고문의 주택형별 표로.
v10(2026-10-17): sol 정답표 기준에 맞춤 — 수량 종류는 표의 열 제목으로(건설·대기·공가는 OFFERED 아님, 예비입주자 공고의 금회 모집은 OFFERED),
    한 행의 금액 칸은 계층·요금안마다 모두(평균 월임대료와 층별 범위는 다른 안), 가격이 있는 행은 모집이 없어도 공급 묶음으로,
    소수 면적 우선, 대리 신청 서류(위임장·인감증명서)와 도장도 서류로(실측: 14건 sol 대조 모집 수 47.8%, bmc 가격 절반 누락).
v20(2026-10-18): v19 + 순위는 대상(가·나·다목)마다 PRIORITY 하나(26-1), 별도 접수 기간 없는 선착순 공고는 APPLICATION 없음(사용자 결정).
v21(2026-10-18): v20 + 월까지만 적힌 입주 예정은 MONTH 정밀도로, 잔금·중도금 납부 기한은 일정 하나로(실측 v30 청약홈 에코델타).
v22(2026-10-18): v21 + 특정 상황에서만 내는 증빙(신용카드사 증빙, 기금 대출 상환 증빙 등)도 서류로(실측 v31 LH 5건).
v23(2026-10-18): v22 + 분양전환 때 기준은 자격에서 빼고, 「미성년자 불가」는 AGE_YEARS≥19로,
  주택목록이 별첨이어도 원문의 주택·호수는 공급 묶음으로(실측 v32 LH 제주 든든전세).
v24(2026-10-18): v23 + 표 행을 인용할 때 빈 칸은 넣지 않음(실측 v34 OpenAI LH 김제: 빈 칸을 반복하다 서류 호출이 잘림).
v25(2026-10-18): v24 + 계약 뒤 부가 신청(편의시설 설치 신청 등)은 접수(APPLICATION)가 아님(실측 v35 LH 인천석남: 접수 시작일로 자동 게시).
v26(2026-10-18): 섹션별로 다시 정리 — 번호 정리, 「기타서류」 지시 충돌 제거, 「틀린 값보다 빈 값」 원칙, 공고일 일정 필수,
  입주자 모집 공고의 「주택 N호」는 모집 수, 계층 정의 속 나이, 짧은 전화번호, 계약 시 서류, 다음 쪽으로 이어진 표(실측 v36 5건).
v27(2026-10-19): v26 + AI가 직접 쓰는 문장(description·reason)은 '~해요' 체로.
v28(2026-10-20): v27 + 단지·주소가 없는 공고는 대상 지역을 위치(kind AREA)로 적음 — 전국이면 「전국」, 지역이면 시도(시군구)마다.
  실측: 위치가 없어 지역 검색에서 빠지던 공고 23건(「대구경북지역」「전북지역본부」·「사업대상지역 : 전국」인 전세임대 등).
v29(2026-10-23): v28 + 프론트 요청 — 일정의 접수 방법(정해진 값)·장소·이메일·접수 시각·쉬는 시각·제외 요일·시각 설명, 주택 열람(VIEWING),
  원문에 시각이 있으면 MINUTE, 서류 묶음(group)·부수·발급 기관. 값은 프로그램이 근거 인용문으로 다시 확인합니다(assemble/details.py).
  v29 고침(2026-10-23, 게시 전이라 같은 파일을 고침. 시험 채점에서 본 일반 규칙): 「필수서류 + 대리(본인 외) 시 추가 서류」 표의 필수서류는
  COMMON(DIRECT는 본인 신청만의 묶음으로 따로 적힌 서류만), 발급처·부수를 적으면 그 표 행 전체를 인용, 장소는 주소를 옮긴 줄을 인용하고
  address에는 도로명·지번만(층·호·건물·받는 사람 문구는 detail), 일정표 아래 ※ 주석의 「주말·공휴일 접수 안 함」도 그 일정의 제외 요일
  (「매주 ○요일만」은 timeNote), 「HH:MM 이후」 발표는 시작 MINUTE·끝 null, 계층·대상별 서류 표는 마지막 행까지·칸 안 「·」 항목마다 하나,
  무보증금(보증금 0) 월세 요금안은 CONVERSION_DEPOSIT_DOWN과 「적용 대상자」 대상(공급표 열 의미 지시 supply_tables/v6도 같이).
  v29 고침 2(2026-10-24, 게시 전이라 같은 파일을 고침. 두 번째 시험 채점의 일반 규칙): 표 전체가 특정 대상(「상한 임대조건」「수급자 등」
  「적용 대상자」)의 요금이면 모든 가격에 그 대상(정할 수 없으면 비움), 표 제목에만 있는 주택형은 그 표 행의 주택형,
  dailyHours는 하루 안의 접수 시각만(첫날~마지막 날 연속 구간·야간·24시간 접수는 비움), 묶음 제목 없는 「필수/선택」 칸은
  필수→COMMON·선택→CONDITIONAL(공급표 열 의미 지시 supply_tables/v7도 같이).
  v29 고침 3(2026-10-24, 게시 전이라 같은 파일을 고침. 세 번째 시험 채점의 일반 규칙): 표는 한 행씩·인용 300자 이내·같은 행 반복 금지
  (서류 호출이 같은 꼴의 행을 되풀이하다 잘림), 원문 따옴표·「|」 그대로·인용 앞뒤 따옴표 덧붙이지 않기, 첫날 시작·마지막 날 끝 시각은
  dailyHours와 상관없이 startsAt·endsAt의 MINUTE, 칸·주석이 막은 접수 방법(「방문 및 일반우편은 접수 불가」)은 예외 상황 문구가 있어도
  channels에 넣지 않고 예외는 timeNote·설명에, 접수 방법을 정하는 문장(「현장 접수만 가능」)은 그 일정의 근거로 꼭 인용.
  서류 호출이 다시 받아도 잘리면 서류 표 묶음별로 나눠 부름(_DOCUMENTS_SUBMIT·_DOCUMENTS_VISIT, runaway_splits).
  v29 고침 4(2026-10-24, 게시 전이라 같은 파일을 고침. 네 번째 시험 채점의 일반 규칙): 서류 칸 단서가 다른 서류를 이름으로 말하면
  그 서류의 appliesTo에, 발급처 칸에 기관이 여럿이면 칸 글자 전체, 「(단, 시작일과 마감일 제외)」 기간은 dailyHours 비움,
  시각 일정은 시각이 적힌 줄을 인용, 우편·등기 제출 일정은 제출처를 places에.
  v29 고침 5(2026-10-24, 게시 전이라 같은 파일을 고침. 다섯 번째 시험 채점의 일반 규칙): 「필수」 칸 ○는 다른 행 설명보다 우선,
  배우자를 나누지 않은 대리는 PROXY_OTHER, 열람 일정도 시각·장소·방법을 채움, 정해진 날마다 같은 시간이면 dailyHours,
  한 칸만 표시된 요일표는 단정하지 않고 timeNote에 원문.
  v29 고침 6(2026-10-24, 게시 전이라 같은 파일을 고침. 여섯 번째 시험 채점의 일반 규칙): 인용은 고치거나 두 곳을 합치지 않기,
  한 칸의 날짜·장소는 원문 순서대로 짝짓기, 분양가와 계약금·잔금은 같은 요금안.
v30(2026-10-29): v29 + 순위·계층·소득 구간마다 기준이 달라도 모든 신청자에게 같은 조건(나이·거주지·무주택·국적 등)은 대상 표시를 비움.
  실측: 구로구 도전숙에서 나이·거주가 「청년창업인」에만 붙어 「월평균소득 50% 이하」 구간에는 소득만 남아 66세·부산도 지원 가능.
  (판정 틀도 소득 구간 대상군을 대상마다 「구간 중 하나」로 접어요, judgment/frame.py _fold_income_tiers)
  v30 호출 지시(2026-11-08~09, 지시 파일은 그대로 — 구조 호출·다른 담당이 같은 파일을 읽음): 서류 종류 이름 뒤 괄호에 든 예시는
  서류 하나·이름에서 증명 내용을 빼지 않음(DOCUMENT_NOTES), 월까지만 있는 공고일은 빠진 칸(범위 PARTIAL 아님), 자동차 미소유는
  CAR_ASSETS_KRW = 0, 선정 결과 발표는 WINNER_ANNOUNCEMENT·기간 일정은 시작과 끝·번호 붙은 글 줄의 날짜 단계도 일정.
v19(2026-10-18): v18 + 선착순 공고의 접수 일정은 먼저 오는 서류 제출로,
    소득은 비율과 금액표가 함께면 비율로(19-6), 기본·금회 완화 조건은 적용하는 쪽만 STRUCTURED(19-7).
v18(2026-10-18): v17 + 짧게 적힌 서류(신분증·인감도장·기타서류 등) 빠짐없이, 순위·계층 정의 속 나이(65세 이상)도 AGE 조건으로(19-5).
v17(2026-10-18): v16 + 병합 칸으로 여러 행에 한 번만 적힌 배점은 행마다 그 점수로(실측: LH 철원 영구임대 가점 5·4·3점 행이 점수 없이 빠짐).
v16(2026-10-17): v15 + 재계약·계약 갱신 때의 소득·자산 기준은 자격이 아니라 안내로(19-4, 실측: 경북 매입임대 재계약 105%가 자격으로 자동 게시).
v15(2026-10-17): v14 + 대상 계층의 자녀 요건은 CHILD_COUNT ≥ 1 조건으로(19-3), 자녀 수·출생 시기별 자산 가산 표는 행마다 REPLACE 예외(23-1).
v14(2026-10-17): v13 + 대상 주택 수(TOTAL_HOUSING)와 모집 수(OFFERED)를 따로, 예비입주자 공고의 「공급호수·세대수」는
    대상 주택 수, 지역별 호수 표는 구마다 공급 묶음(사용자 결정).
v13(2026-10-17): v12 + 분양 발코니 확장·유상옵션(합계 행) 금액을 가격으로, 서류 표의 발급기관 전화도 CONTACT로, 분양 규제 표를 안내로.
v12(2026-10-17): v11 + 가구원 수별 소득·자산 기준은 기본값 조건 + REPLACE 예외(when: HOUSEHOLD_MEMBER_COUNT)로(19-2).
v11(2026-10-17): 구조 방식 — 표 아래 열 제목 줄·행마다 읽기 도움 줄(↳)을 프로그램이 붙임(intake/pdf_reader.render). 값 종류는 ↳ 줄의 열 제목으로.
    v10은 RULES_V10으로 남김(롤백 스위치 EXTRACTION_METHOD=legacy, method.py).
프롬프트 파일은 지금 쓰는 v30, 바로 앞 v29(롤백용), 이전 방식(legacy) 롤백용 v10만 둡니다(위 이력은 무엇이 왜 바뀌었는지 기록으로 남김).
"""

from dataclasses import replace
from pathlib import Path

from mujuthaek_extraction.rules.base import CallSpec, FieldRules

# 원문이 길어 자격·선정·서류를 나눠 호출할 때 덧붙이는 지시
SPLIT_NOTE = (
    "대상군(청년·신혼부부 등)별 조건은 scope.targetGroups로 구분합니다. 공고 기본 정보·위치·공급 조건·일정과 이 호출이 맡지 않은 섹션은 "
    "다시 추출하지 않습니다.\n섹션을 나눠 호출합니다. 맡은 섹션은 원문 끝까지 빠짐없이, 요약하지 말고 항목마다 넣습니다."
)

# 서류를 넣는 호출마다 덧붙이는 지시. 종류 이름 뒤 괄호 속 예시도 공통 지시의 「괄호 속에 있는 서류」「"/"·"또는"으로 함께 있으면 나눔」대로
# 서류마다 나누던 것(2026-11-08 조사: jbdc-16011 「② 부양가족임을 확인할 수 있는 서류 (주민등록표등본, 가족관계증명서 등)」를 V2 서류 담당이
# 저장된 네 실행 모두 예시 둘로 나눠 넣어 부양가족 확인이라는 목적이 사라지고 둘 다 내야 하는 것처럼 보임. 23건 원문의 같은 모양 15곳(9건)에서
# V2는 판별되는 12곳 중 8곳을 예시마다 나눴고(당첨자·대리인 신분증은 예시마다 6개), 정답표는 대부분 한 서류(「A 또는 B」)로 적음).
# 지시 파일(prompt.v30.md)이 아니라 여기에 두는 것: 구조 호출과 V2의 다른 담당도 그 파일을 읽어, 고치면 서류와 상관없는 호출의 캐시까지 바뀜
DOCUMENT_EXAMPLES_NOTE = (
    "서류 종류 이름 뒤 괄호에 예시를 든 서류(「혼인 사실을 확인할 수 있는 서류 (혼인관계증명서, 주민등록표등본 등)」「본인 신분증(주민등록증, "
    "운전면허증, 여권 중 1)」처럼 「등」「중 1」로 그 가운데 하나를 내면 되는 나열)는 예시가 「/」·「또는」으로 이어져 있어도 서류 하나입니다. "
    "이름은 종류 이름 뒤에 괄호 속 예시를 그대로 붙여 적고 예시마다 서류를 나누지 않습니다. 괄호 속 서류를 모두 내거나(「및」「각 1부」) "
    "대상·상황마다 다른 서류를 적었으면 서류마다 나눕니다."
)
# 서류 이름에서 무엇을 증명하는지 붙은 말을 빼면 뜻이 바뀝니다(2026-11-09 23건 sh-311005: 소득신고 사실이 없음을 증명하는 사실증명서를
# V2 서류 담당이 「소득신고 사실증명서」로 적어 신고한 사실의 증명서로 읽힘)
DOCUMENT_NAME_NOTE = "서류 이름은 원문 이름대로 적고, 무엇을 증명하는지 붙은 말(「소득신고 사실 없음」「무주택」「미혼」)을 빼거나 줄여 뜻을 바꾸지 않습니다."
DOCUMENT_NOTES = f"{DOCUMENT_EXAMPLES_NOTE} {DOCUMENT_NAME_NOTE}"

# 호출별 출력 한도 근거: 저장된 실제 유료 응답(gpt-6-luna, 정상 종료 END) 중 최대 출력 토큰 (2026-10-20 집계, 시도 446건:
# eval/live-v10~v40·extract-v*·paid-v6·pipeline*·live-perf). 반복으로 폭주해 한도까지 간 응답은 빼고 셉니다.
MEASURED_MAX_OUTPUT = {
    "structure": 45_000,  # 정상 종료 최대 39,073(SH 310653). 이전 방식의 SH 213행 공고가 약 4.5만 토큰을 썼다는 기록이 있어 그 값으로
    "schedules": 13_813,  # 0815(live-v40). 이전 기록 11,818(GH 783)
    "eligibility": 27_818,  # LH 양주 영구임대 0727(live-v34)
    "selection": 21_505,  # GH 783(live-v34)
    "documents": 16_116,  # 인천 4358(live-v11). LH 김제 19412의 24,000(빈 칸 「|  |」 반복으로 잘림)은 제외
    "conditions": 23_488,  # 나눠 부르지 않던 때(pipeline5 0854)
}
# 출력 한도 = 실측 최대의 약 1.3배(반올림). 한도가 넉넉하면 반복으로 폭주한 응답이 한도까지 가며 시간·비용을 다 씁니다.
# 실측(live-perf 0839, 2026-10-20): 선정 호출이 빈 칸 「|  |」을 반복하다 48,000토큰에서 잘림(294초, $0.030 = 그 공고 비용의 54%),
# 다시 받으니 5,547토큰. 새 한도 28,000이면 같은 폭주의 출력·시간이 약 40% 줄어듭니다. 설정 EXTRACTION_MAX_OUTPUT_TOKENS로 호출별로 바꿀 수 있습니다.
OUTPUT_LIMITS = {
    "structure": 64_000,  # 낮추지 않음: 호별 표가 많은 공고(SH 213행 약 4.5만)를 담아야 합니다(1.3배 ≈ 5.9만보다 조금 넉넉히)
    "supply_more": 64_000,  # 이어받기: 실측 없음. 구조 호출과 같은 공급 묶음을 담으므로 같은 한도
    "schedules": 18_000,  # 이전 32,000
    "eligibility": 36_000,  # 이전 64,000
    "selection": 28_000,  # 이전 48,000
    "documents": 21_000,  # 이전 48,000
    "conditions": 64_000,  # 나눠 부르지 않을 때만(기본은 나눔). 자격·선정·서류 세 섹션 최댓값의 합(약 6.5만)을 담게 그대로
}

RULES_V10 = FieldRules(  # 이전 방식(EXTRACTION_METHOD=legacy): 표 행 글자만 받음. 지우지 말고 롤백용으로 둡니다
    field="housing_notice",
    prompt_version="v10",
    prompt_path=Path(__file__).with_name("prompt.v10.md"),
    calls=(
        CallSpec(
            name="structure",
            sections=("notice", "locations", "supplyGroups"),
            instructions=(
                "공고 기본 정보(notice), 단지·건물·주소(locations), 주택형·호실별 공급 조건(supplyGroups: 면적·수량·가격·임대기간)을 추출합니다.\n"
                "공통 지시 1장의 '공통·위치·공급' 항목을 모두 확인합니다. 가격은 임대면 모든 전환안과 전세형까지, 분양·매각이면 층·타입별 가격과 "
                "계약금·중도금·잔금·융자금·할부금 같은 납부 조건까지 넣습니다. 호실별 표가 있으면 가격이 같아도 호실마다 하나씩 넣습니다.\n"
                "원문 끝에 '=== 첨부 엑셀 ... ===' 공급주택목록이 있으면 목록의 주택마다 위치(locations, 주소)를 넣습니다. "
                "목록에 주택·호실별 보증금·임대료가 있으면 공급 묶음도 호실마다 만들고, 없으면 공고문의 주택형별 표로 공급 묶음과 가격을 만듭니다. "
                "엑셀이 없거나 '머리 행만 보입니다'로 잘렸으면 공고문 표만 씁니다.\n"
                "공급표·임대조건표의 행을 끝까지 세어 모두 넣고, 한 행의 금액 칸은 계층·요금안마다 모두 가격으로 넣습니다. "
                "수량 종류는 표의 열 제목으로 고릅니다.\n"
                "공용면적·선납 할인·옵션 비용·관리비 예치금은 넣지 않습니다.\n"
                "단지 안의 건물은 parentLocationId로 단지를 가리킵니다.\n"
                "공고 전체 수량은 notice.counts, 주택형·호실별 수량은 supplyGroups[].counts에 적습니다.\n"
                "여기서 정한 위치·공급 ID를 다음 호출들이 그대로 사용합니다."
            ),
            uses_structure=False,
            max_output_tokens=OUTPUT_LIMITS["structure"],
        ),
        CallSpec(
            name="schedules",
            sections=("schedules", "guidance"),
            instructions=(
                "공고·신청·주택 열람·서류 제출·서류심사 결과·당첨자 발표·계약·입주·입찰·개찰 일정(schedules)과 "
                "신청 방법·주의사항·입주 안내·거주 유의사항·문의처(guidance)를 추출합니다.\n"
                "계약·입주처럼 신청자가 꼭 거치는 단계는 날짜가 '개별 안내'여도 일정으로 넣고, 내부 절차의 소요 기간·이의신청·세금 기한은 넣지 않습니다. "
                "별도 접수 기간 없이 방문 서류 제출·계약으로 바로 신청받는 공고(선착순 동·호 지정 등)는 APPLICATION 일정을 만들지 않고 "
                "CONTRACT·DOCUMENT_SUBMISSION으로 둡니다(공통 지시와 같음, 사용자 결정 2026-10-18).\n"
                "같은 구간이 신청과 입찰을 겸하면 kinds에 둘 다 적습니다. 대상·순위별로 일정이 다르면 각각 따로 적고 scope와 priorityRank로 구분합니다.\n"
                "공고 기본 정보·위치·공급 조건·자격·서류는 다시 추출하지 않습니다."
            ),
            uses_structure=True,
            max_output_tokens=OUTPUT_LIMITS["schedules"],
        ),
        CallSpec(
            name="conditions",
            sections=("eligibility", "selectionRules", "requiredDocuments"),
            instructions=(
                "신청 자격(eligibility), 선정 방식·순위·가점·동점 처리(selectionRules), 제출 서류(requiredDocuments)를 추출합니다.\n"
                "공통 지시 1장의 '자격·선정·서류' 항목을 모두 확인합니다. '이번에는 적용하지 않음'·'불문' 기준도 조건으로 남기고, "
                "다른 곳의 가산·완화 표는 해당 조건의 예외로 넣습니다.\n"
                "선정은 순위·방식·동점 처리·예비입주자 배수와 가점 배점표의 행마다 하나(그 행의 점수와 항목 최고점)를 넣습니다. "
                "서류는 이름마다 하나(대상은 appliesTo, 서류별 조건은 description)이며, 대리 신청 서류도 대상을 적어 넣고 발급 방법 설명은 넣지 않습니다.\n"
                "대상군(청년·신혼부부 등)별 조건은 scope.targetGroups로 구분합니다. 공고 기본 정보·위치·공급 조건·일정은 다시 추출하지 않습니다."
            ),
            uses_structure=True,
            max_output_tokens=OUTPUT_LIMITS["conditions"],
        ),
    ),
    continuation=CallSpec(
        name="supply_more",
        sections=("supplyGroups",),
        instructions=(
            "앞 응답이 공급 묶음을 다 담지 못했습니다. '이미 추출한 구조'에 있는 공급 묶음은 다시 넣지 않고, "
            "그 다음 단지·호실부터 이어서 공급 묶음(supplyGroups)만 넣습니다.\n"
            "인용은 이 응답의 quotes에 새로 적습니다. 다 넣었으면 coverage.supplyGroups를 EXTRACTED로, "
            "아직 남았으면 PARTIAL과 '이어서: <마지막 id>'로 적습니다."
        ),
        uses_structure=True,
        max_output_tokens=OUTPUT_LIMITS["supply_more"],
    ),
    # 모든 공고에서 자격·선정·서류를 따로 호출합니다(호출 2번 추가, 같은 원문이라 입력 캐시로 공고당 약 $0.005~0.01).
    # 실측(2026-10-16 시험): 나눠 호출한 대형 공고에서 서류 22→43/60·가점 10→43/43·소득 기준 0→17/17. 서류는 여러 공고에서 4할가량 빠짐
    large_text_chars=0,
    split_calls=(
        (
            "conditions",
            (
                CallSpec(
                    name="eligibility",
                    sections=("eligibility",),
                    instructions=(
                        "신청 자격(eligibility)을 추출합니다. 공통 지시 1장의 '자격' 항목을 모두 확인합니다. "
                        "'이번에는 적용하지 않음'·'불문' 기준도 조건으로 남기고, 다른 곳의 가산·완화 표는 해당 조건의 예외로 넣습니다. "
                        "특별공급·일반공급 등 공급 유형별·계층별 소득·자산 기준은 유형마다 따로 넣습니다.\n" + SPLIT_NOTE
                    ),
                    uses_structure=True,
                    max_output_tokens=OUTPUT_LIMITS["eligibility"],
                ),
                CallSpec(
                    name="selection",
                    sections=("selectionRules",),
                    instructions=(
                        "선정 방식·순위·가점·동점 처리(selectionRules)를 추출합니다. 순위·방식·동점 처리·예비입주자 배수와 "
                        "가점 배점표의 행마다 하나(그 행의 점수와 항목 최고점)를 넣습니다. 공급 유형별 배점표가 따로 있으면 표마다 모든 행을 넣습니다.\n"
                        + SPLIT_NOTE
                    ),
                    uses_structure=True,
                    max_output_tokens=OUTPUT_LIMITS["selection"],
                ),
                CallSpec(
                    name="documents",
                    sections=("requiredDocuments",),
                    instructions=(
                        "제출 서류(requiredDocuments)를 추출합니다. 서류는 이름마다 하나(대상은 appliesTo, 서류별 조건은 description)이며, "
                        "공급 유형별 서류 표가 따로 있으면 표마다 넣습니다. 대리 신청 서류(위임장·인감증명서 등)도 appliesTo에 대상을 적어 넣고, "
                        "발급 방법 설명은 넣지 않습니다.\n" + SPLIT_NOTE
                    ),
                    uses_structure=True,
                    max_output_tokens=OUTPUT_LIMITS["documents"],
                ),
            ),
        ),
    ),
)

# 호출 지시: 공통 지시의 절 이름(2장 「공고」「공급」「일정」「자격」「선정」「서류」「안내」)을 가리킵니다.
# RULES_V10의 호출 지시는 이전 방식(legacy) 롤백용이라 그대로 둡니다.
_STRUCTURE = CallSpec(
    name="structure",
    sections=("notice", "locations", "supplyGroups"),
    instructions=(
        "공고(notice), 단지·건물·주소(locations), 주택형·호실별 공급 조건(supplyGroups: 면적·수량·가격·임대기간)을 추출합니다.\n"
        "공통 지시 2장의 「공고」「위치」「공급」 절을 모두 따릅니다. 표의 행은 다음 쪽으로 이어진 행까지 끝까지 넣고, 한 행의 금액 칸은 "
        "계층·요금안마다 모두 가격으로 넣습니다. 수량 종류는 열 제목과 원문 표현으로 고릅니다.\n"
        "원문 끝에 '=== 첨부 엑셀 ... ===' 공급주택목록이 있으면 목록의 주택마다 위치(주소)를 넣고, 목록에 주택·호실별 보증금·임대료가 있으면 "
        "공급 묶음도 호실마다 만듭니다. 없거나 '머리 행만 보입니다'로 잘렸으면 공고문의 표만 씁니다.\n"
        # 2026-11-09 23건 sh-311005: 「2026년 10월」로만 적힌 공고일 때문에 공고 범위를 PARTIAL로 적어 공고 전체(찾은 값 138개)가 검수로 감
        "공고일이 「2026년 10월」처럼 일(日)까지 적혀 있지 않으면 announcedOn은 null로 두고 missingFields에 적습니다. 원문에 그 정밀도의 값이 "
        "없을 뿐이라 범위(coverage)를 PARTIAL로 두지 않습니다(PARTIAL은 원문에 있는데 옮기지 못한 값이 있을 때만).\n"
        "여기서 정한 위치·공급 ID를 다음 호출들이 그대로 사용합니다."
    ),
    uses_structure=False,
    max_output_tokens=OUTPUT_LIMITS["structure"],
)
_SCHEDULES = CallSpec(
    name="schedules",
    sections=("schedules", "guidance"),
    instructions=(
        "일정(schedules)과 신청 안내·주의사항·입주 안내·거주 유의사항·문의처(guidance)를 추출합니다.\n"
        "공통 지시 2장의 「일정」「안내」 절을 따릅니다. 공고일 일정을 반드시 넣고, APPLICATION은 입주자 모집에 신청하는 기간에만 씁니다"
        "(별도 접수 없이 계약으로 바로 신청받는 공고는 CONTRACT·DOCUMENT_SUBMISSION). 대상·순위별 일정은 각각 따로 적습니다.\n"
        # 2026-11-09 23건: 「계약 대상자 및 예비 대상자 발표」를 OTHER로(sh-310672), 「입주시기 10~11월 중 협의 가능」의 끝을 빼고(sh-310976),
        # 일정표 밖 「나. 계약체결: 2027. 1. 20.(수) ~」「라. 입주기간: 2027. 2~4월 중」을 넣지 않음(sh-311087)
        "선정 결과를 알리는 발표·통보(당첨자·계약 대상자·예비입주자·최종 입주자)는 WINNER_ANNOUNCEMENT입니다. 「10~11월」「2~4월 중」처럼 "
        "기간으로 적힌 일정은 변동·협의 가능이어도 시작과 끝을 모두 적습니다. 일정표 밖에 「나. 계약체결: 2027. 1. 20.」처럼 번호 붙은 글 줄로 "
        "적힌 날짜 단계도 넣습니다.\n"
        "문의처는 공고 끝뿐 아니라 서류 표·안내문의 ☎ 번호(짧은 번호 포함)까지 기관마다 넣습니다.\n"
        "접수 방법·장소·이메일·접수 시각·쉬는 시각·제외 요일은 「접수 방법·장소·시각」 절대로 원문에 있는 것만 넣고, "
        "그 값이 적힌 문장도 그 일정의 근거로 인용합니다.\n"
        "공고 기본 정보·위치·공급 조건·자격·서류는 다시 추출하지 않습니다."
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["schedules"],
)
_ELIGIBILITY = CallSpec(
    name="eligibility",
    sections=("eligibility",),
    instructions=(
        "신청 자격(eligibility)을 추출합니다. 공통 지시 2장의 「자격」 절을 모두 따릅니다.\n"
        "빠뜨리기 쉬운 것: 계층·순위 정의 안의 나이·자녀 요건(「고령자(만 65세 이상)」 등은 그 계층의 조건), '이번에는 적용하지 않음'·'불문' 기준, "
        "다른 곳의 가산·완화 표(그 조건의 예외), 공급 유형별·계층별로 다른 소득·자산 기준(유형마다 따로).\n"
        # 2026-11-09 23건: 대학생 「자동차가액 산출대상 자동차를 소유하고 있지 않을 것」 4건을 조건식 없이 글로 남겨 보류됨(정답표는 모두 자동차가액 0)
        "「자동차가액 산출대상 자동차를 소유하고 있지 않을 것」처럼 자동차가 없어야 하는 기준은 CAR_ASSETS_KRW EQ 0 조건식입니다"
        "(같은 줄의 총자산 기준은 따로 조건).\n" + SPLIT_NOTE
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["eligibility"],
)
_SELECTION = CallSpec(
    name="selection",
    sections=("selectionRules",),
    instructions=(
        "선정 방식·순위·가점·동점 처리(selectionRules)를 추출합니다. 공통 지시 2장의 「선정」 절을 따릅니다. 순위는 순위 안의 대상마다, "
        "가점은 배점표의 행마다(병합 칸의 점수는 행마다), 공급 유형별 배점표는 표마다 모든 행을 넣습니다.\n" + SPLIT_NOTE
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["selection"],
)
_DOCUMENTS = CallSpec(
    name="documents",
    sections=("requiredDocuments",),
    instructions=(
        "제출 서류(requiredDocuments)를 추출합니다. 공통 지시 2장의 「서류」 절을 따릅니다. 서류는 이름마다 하나(대상은 appliesTo)이며, "
        "서류 표를 다 넣은 뒤 「빠뜨리기 쉬운 곳」(방문·대리 신청 상자, 계약 시 구비서류, ※ 주석, 신분증·도장·인감 낱말)을 다시 훑습니다. "
        "서류 표가 공통·해당자·본인 방문·대리 신청으로 묶음을 나눴으면 group을, 부수·발급 기관이 적혀 있으면 copies·issuer를 적습니다. "
        + DOCUMENT_NOTES
        + "\n"
        + SPLIT_NOTE
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["documents"],
)
# 서류 호출이 다시 받아도 잘리면 서류 표 묶음별로 나눠 부릅니다(FieldRules.runaway_splits). 평소에는 부르지 않습니다(비용).
# 실측(2026-10-24 세 번째 채점): 「현장신청시 대리인 확인서류」 표의 세 행을 되풀이하는 폭주가 5건 중 3건의 첫 서류 호출에서 났고,
# 한 건은 두 번 모두 잘려 신청 서류 45개가 모두 빠짐. 나눠 부르면 한 묶음이 폭주해도 다른 묶음의 서류는 남습니다
_DOCUMENTS_SUBMIT = CallSpec(
    name="documents-submit",
    sections=("requiredDocuments",),
    instructions=(
        "제출 서류(requiredDocuments) 가운데 **신청·서류 제출 단계에서 내는 서류 표**(공통 제출서류, 해당자·계층별 추가 서류, 소득·자산 증빙)만 "
        "추출합니다. 공통 지시 2장의 「서류」 절을 따릅니다. 현장(방문)·대리 신청 때 확인하는 신분증·도장·위임장 상자와 계약·입주 때 내는 서류는 "
        "다른 호출이 맡으므로 넣지 않습니다. " + DOCUMENT_NOTES + "\n" + SPLIT_NOTE
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["documents"],
)
_DOCUMENTS_VISIT = CallSpec(
    name="documents-visit",
    sections=("requiredDocuments",),
    instructions=(
        "제출 서류(requiredDocuments) 가운데 **현장(방문)·대리 신청 때 확인하는 서류**(본인·배우자·기타 대리인별 신분증·도장·인감·위임장 상자), "
        "**계약·입주 때 내는 서류**, ※ 주석에만 적힌 서류만 추출합니다. 공통 지시 2장의 「서류」 절을 따릅니다. 신청·서류 제출 단계의 공통·해당자·"
        "계층별 서류 표는 다른 호출이 맡으므로 넣지 않습니다. " + DOCUMENT_NOTES + "\n" + SPLIT_NOTE
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["documents"],
)
_CONDITIONS = CallSpec(  # 나눠 부르지 않을 때(large_text_chars 설정)만 씁니다
    name="conditions",
    sections=("eligibility", "selectionRules", "requiredDocuments"),
    instructions=(
        "신청 자격(eligibility), 선정 방식(selectionRules), 제출 서류(requiredDocuments)를 추출합니다. 공통 지시 2장의 「자격」「선정」「서류」 "
        "절을 모두 따릅니다. 대상군별 조건은 scope.targetGroups로 구분하고, 공고 기본 정보·위치·공급 조건·일정은 다시 추출하지 않습니다.\n" + DOCUMENT_NOTES
    ),
    uses_structure=True,
    max_output_tokens=OUTPUT_LIMITS["conditions"],
)

# 구조 방식(EXTRACTION_METHOD=structured, 기본): 표에 열 제목 줄·행 읽기 도움 줄(↳)이 붙은 글자를 받습니다.
RULES = replace(
    RULES_V10,
    prompt_version="v30",
    prompt_path=Path(__file__).with_name("prompt.v30.md"),
    calls=(_STRUCTURE, _SCHEDULES, _CONDITIONS),
    split_calls=(("conditions", (_ELIGIBILITY, _SELECTION, _DOCUMENTS)),),
    supply_tables=True,
    runaway_splits=(("documents", (_DOCUMENTS_SUBMIT, _DOCUMENTS_VISIT)),),
)

# 자동 등록(rules/__init__.py): 수집 이벤트 field가 HOUSING이면 위 규칙, 이전 방식이면 v10
FIELD = "HOUSING"
RULES_LEGACY = RULES_V10
