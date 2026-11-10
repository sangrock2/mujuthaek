"""정책 판정 틀 검사 4차(사업공간 4차 채점 뒤 일반 규칙): 비어 있는 대상군, 온통청년 나이 제한 표시와 값의 엇갈림, 기준일 대체 순서,
「신청일 기준」, 「관내」 풀기, 첨부만 가리키는 제외 칸, 휴·폐업 중복 질문, 기창업 대상군의 사업자 조건. 지어낸 공고 글로만 시험합니다."""

import json
from datetime import date

from test_policy_frame_checks import REGIONS, frame_of
from test_policy_judgment import TOUR_TEXT, answer, condition, reading, tour

from mujuthaek_extraction.judgment.policy_frame import (
    AGE_FLAG_CONFLICT,
    APPLICATION_DAY,
    ATTACHED,
    EMPTY_GROUP,
    JUDGING_DATE_NOTE,
    JURISDICTION_UNKNOWN,
    MERGED_SUSPENSION,
    META_ONLY,
    NO_REFERENCE_DATE,
    REGISTRATION_FROM_DOCUMENTS,
    VALUE_MISSING,
    agency_sigungu,
    space_frame,
    startup_frame,
    uses_judging_date,
)
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.publish import policy_completed_payload
from mujuthaek_extraction.rules.policy.reading import CALL_NAME, OUTPUT_SCHEMA, PROMPT_VERSION, SYSTEM, read_policy

NO_DATE = {"announcedOn": {"date": None, "quote": None}, "referenceRule": "NONE", "referenceDate": {"date": None, "quote": None}}
TODAY = date(2026, 11, 5)
LOCATED = {"spaceLocation": {"names": ["경기도 화성시"], "quote": "경기도 화성시 가상로 12"}}
SPACE_TEXT = TOUR_TEXT + "□ 입주 공간 : 경기도 화성시 가상로 12\n"
TWO_GROUPS = [
    {"key": "pre", "name": "예비창업자", "quote": "사업자 등록 전인 개인"},
    {"key": "biz", "name": "기창업자", "quote": "창업 3년 이내 기업"},
]


def undated(conditions, extra="", *, record=None, today=TODAY, **fields):
    payload = tour() | {"text": SPACE_TEXT + extra, "record": record or {}}
    read = reading(answer(conditions, **(NO_DATE | LOCATED | fields)))
    made = space_frame(payload, read, REGIONS, today=today)
    assert made is not None and frame_errors(made) == []
    return payload, read, made


def date_note(made):
    [note] = [n for n in made["notes"] if n["text"].startswith(JUDGING_DATE_NOTE)]
    return note["text"]


# 1. 비어 있는 대상군은 누구나 통과하는 길: 대상군 질문(확인 필요)으로 채움


def test_empty_group_among_several_gets_a_held_membership_question():
    groups = [
        {"key": "early", "name": "초기창업자", "quote": "초기창업자 및 예비창업자에게 공간을 빌려 줍니다"},
        {"key": "pre", "name": "예비창업자", "quote": "초기창업자 및 예비창업자에게 공간을 빌려 줍니다"},
    ]
    text = "- 초기창업자 및 예비창업자에게 공간을 빌려 줍니다\n- 사업자 등록 전인 개인\n"
    pre = condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")
    made = frame_of([pre], text, groups=groups)
    [asked] = made["groups"][0]["criteria"]
    assert (asked["kind"], asked["question"], asked["metWhen"], asked["inReview"]) == ("ASK", "초기창업자에 해당하나요?", "YES", True)
    assert EMPTY_GROUP in asked["reviewReason"] and asked["quote"] == "초기창업자 및 예비창업자에게 공간을 빌려 줍니다"
    [kept] = made["groups"][1]["criteria"]
    assert kept["kind"] == "BUSINESS_REGISTRATION" and not kept["inReview"]
    # 대상군 근거 문장을 원문에서 찾지 못해도 질문은 둠(근거 없이)
    lost = [g | {"quote": "원문에 없는 가상 문장"} for g in groups]
    assert frame_of([pre], text, groups=lost)["groups"][0]["criteria"][0]["quote"] is None
    # 창업지원 틀도 같음
    assert frame_of([pre], text, startup=True, groups=groups)["groups"][0]["criteria"][0]["inReview"]


def test_single_empty_group_is_filled_only_when_the_text_names_it():
    named = [{"key": "farm", "name": "청년 농업인", "quote": "청년 농업인을 모집합니다"}]
    made = frame_of([], "- 청년 농업인을 모집합니다\n", groups=named)
    [asked] = made["groups"][0]["criteria"]
    assert asked["question"] == "청년 농업인에 해당하나요?" and asked["inReview"]
    # 원문이 그 대상을 말하지 않으면(지어낸 이름) 만들지 않음
    invented = [{"key": "x", "name": "가상 대상", "quote": "원문에 없는 가상 문장"}]
    assert frame_of([], "", groups=invented)["groups"][0]["criteria"] == []
    # AI가 대상군을 나누지 않았으면(「전체」) 그대로
    assert frame_of([], "")["groups"][0]["criteria"] == []


# 2. 온통청년 나이: 제한 여부 N인데 값이 있으면 확인 필요 나이


def test_unflagged_youth_ages_become_a_held_age_with_a_conflict_reason():
    lines = "지원 대상 최소 연령: 18\n지원 대상 최대 연령: 45\n"
    loose = {"sprtTrgtMinAge": "18", "sprtTrgtMaxAge": "45", "sprtTrgtAgeLmtYn": "N"}
    [age] = frame_of([], lines, record=loose)["common"]
    assert (age["minAge"], age["maxAge"], age["inReview"]) == (18, 45, True)
    assert META_ONLY in age["reviewReason"] and AGE_FLAG_CONFLICT in age["reviewReason"] and age["quote"] == lines.strip()
    # 제한 표시 Y면 지금처럼(엇갈림 사유 없음)
    [flagged] = frame_of([], lines, record=loose | {"sprtTrgtAgeLmtYn": "Y"})["common"]
    assert flagged["inReview"] and AGE_FLAG_CONFLICT not in flagged["reviewReason"]
    # 값도 제한 없음(0, 99 이상)이면 나이를 만들지 않음
    assert frame_of([], "", record={"sprtTrgtMinAge": "0", "sprtTrgtMaxAge": "0", "sprtTrgtAgeLmtYn": "N"})["common"] == []
    assert frame_of([], "", record={"sprtTrgtMinAge": "0", "sprtTrgtMaxAge": "99", "sprtTrgtAgeLmtYn": "N"})["common"] == []
    # 본문 나이가 있으면 더하지 않음
    body = "- 만 20세 이상 만 30세 이하\n"
    [own] = frame_of([condition("AGE", "만 20세 이상 만 30세 이하", minAge=20, maxAge=30)], lines + body, record=loose)["common"]
    assert (own["minAge"], own["maxAge"], own["inReview"]) == (20, 30, False)


# 3. 기준일 대체 순서: 공고일·기준일 → 접수 시작일 → 판정일(접수 마감 뒤면 마감일)


def test_application_start_is_the_fallback_reference_and_matches_the_schedule():
    extra = "- 만 19세 이상 만 39세 이하\n"
    age = condition("AGE", "만 19세 이상 만 39세 이하", minAge=19, maxAge=39)
    for record in ({"pbanc_rcpt_bgng_dt": "20261020", "pbanc_rcpt_end_dt": "20261030"}, {"aplyYmd": "20261020 ~ 20261030"}):
        payload, read, made = undated([age], extra, record=record)
        assert made["referenceDate"] == "2026-10-20" and uses_judging_date(made)
        assert "접수 시작일(2026-10-20)" in date_note(made) and "판정일" not in date_note(made)
        [held] = made["common"]
        assert held["inReview"] and NO_REFERENCE_DATE in held["reviewReason"] and "접수 시작일(2026-10-20)" in held["reviewReason"]
        completed = policy_completed_payload(payload, made, REGIONS, read)
        assert completed["schedule"] == {"applyStartOn": "2026-10-20", "applyEndOn": "2026-10-30"}
        assert completed["reviewStatus"] == "PARTIALLY_PASSED"


def test_judging_date_is_used_without_a_period_and_capped_at_the_application_end():
    age = condition("AGE", "만 19세 이상 만 39세 이하", minAge=19, maxAge=39)
    _, _, made = undated([age], "- 만 19세 이상 만 39세 이하\n")
    assert made["referenceDate"] == "2026-11-05" and "판정일(2026-11-05)" in date_note(made)
    # 시작일 없이 마감일만 있고 판정일이 마감 뒤면 마감일
    record = {"pbanc_rcpt_end_dt": "20261030"}
    _, _, closed = undated([age], "- 만 19세 이상 만 39세 이하\n", record=record)
    assert closed["referenceDate"] == "2026-10-30" and "접수 마감일(2026-10-30)" in date_note(closed)
    _, _, early = undated([age], "- 만 19세 이상 만 39세 이하\n", record=record, today=date(2026, 10, 25))
    assert early["referenceDate"] == "2026-10-25"
    # 공고일이 있으면 지금처럼 그 날(확정)
    payload = tour() | {"text": SPACE_TEXT + "- 만 19세 이상 만 39세 이하\n", "record": {"pbanc_rcpt_bgng_dt": "20261020"}}
    dated = space_frame(payload, reading(answer([age], **LOCATED)), REGIONS, today=TODAY)
    assert dated["referenceDate"] == "2026-10-07" and not uses_judging_date(dated) and not dated["common"][0]["inReview"]


# 4. 「신청일 기준」: 같은 대체 날짜, 기준일에 기대는 조건은 확인 필요(사유 「신청일 기준」)


def test_application_day_rule_holds_date_dependent_conditions():
    extra = "- 신청일 기준 만 19세 이상 만 39세 이하인 사람\n- 국세 체납자는 신청 불가\n"
    age = condition("AGE", "신청일 기준 만 19세 이상 만 39세 이하인 사람", minAge=19, maxAge=39)
    arrears = condition("EXCLUDED_STATUS", "국세 체납자는 신청 불가", excludedCodes=["TAX_ARREARS"])
    # 이전 읽기(NONE)라도 원문에 「신청일 기준」이 있으면
    _, _, made = undated([age, arrears], extra, record={"aplyYmd": "20261020 ~ 20261030"})
    held, kept = made["common"]
    assert held["inReview"] and held["reviewReason"].startswith(APPLICATION_DAY) and "접수 시작일(2026-10-20)" in held["reviewReason"]
    assert not kept["inReview"] and "신청일 기준" in date_note(made)
    # AI가 APPLICATION으로 읽고 공고일이 있으면 공고일을 쓰되 확인 필요
    payload = tour() | {"text": SPACE_TEXT + extra, "record": {}}
    by_rule = space_frame(payload, reading(answer([age, arrears], referenceRule="APPLICATION", **LOCATED)), REGIONS, today=TODAY)
    assert by_rule["referenceDate"] == "2026-10-07" and uses_judging_date(by_rule)
    assert by_rule["common"][0]["inReview"] and "공고일(2026-10-07)" in by_rule["common"][0]["reviewReason"]
    # 「공고일 기준」으로 읽은 공고는 그대로(신청일 말이 있어도)
    announced = space_frame(payload, reading(answer([age, arrears], **LOCATED)), REGIONS, today=TODAY)
    assert not announced["common"][0]["inReview"] and not uses_judging_date(announced)


def test_prompt_v8_reads_the_application_day_rule():
    assert PROMPT_VERSION == "policy/v8" and "APPLICATION" in SYSTEM and "신청일 기준" in SYSTEM
    assert "APPLICATION" in OUTPUT_SCHEMA["properties"]["referenceRule"]["enum"]
    model = RecordedModel({CALL_NAME: [json.dumps(answer([], referenceRule="APPLICATION"))]})
    assert read_policy(tour(), model).answer["referenceRule"] == "APPLICATION"


# 5. 「관내」: 기관이 시군구이고 그 시군구가 하나로 정해질 때만 확정


def region_frame(item, *, agency="경기도 화성시", codes=("41590",)):
    text = SPACE_TEXT + f"- {item['quote']}\n"
    payload = tour() | {"text": text, "record": {}, "agency": agency, "regionScope": "SIGUNGU", "regionCodes": list(codes)}
    made = space_frame(payload, reading(answer([item], **LOCATED)), REGIONS, today=TODAY)
    assert frame_errors(made) == []
    return made["common"][0]


def test_jurisdiction_word_resolves_to_the_agency_sigungu():
    named = condition("REGION", "관내 주소지를 둔 사람", regionNames=["화성시"], regionBasis="RESIDENCE")
    region = region_frame(named)
    assert (region["kind"], region["regionCodes"], region["inReview"]) == ("REGION", ["4159000000"], False)
    # AI가 지역 이름을 적지 않아도 기관 관할로
    bare = region_frame(condition("REGION", "관할 지역에 사업장이 있는 기업", regionBasis="BUSINESS_SITE"))
    assert (bare["regionCodes"], bare["basis"], bare["inReview"]) == (["4159000000"], "BUSINESS_SITE", False)
    # 「○○시청」 기관 이름, 수집기 코드가 없어도
    assert region_frame(named, agency="화성시청", codes=())["inReview"] is False
    assert agency_sigungu({"agency": "경기도", "regionCodes": []}, REGIONS) is None  # 시도 기관


def test_jurisdiction_that_cannot_be_pinned_down_is_held_with_a_clear_reason():
    named = condition("REGION", "관내 주소지를 둔 사람", regionNames=["화성시"], regionBasis="RESIDENCE")
    for agency, codes in (("가상관광공사", ("41590",)), ("경기도 화성시", ("41590", "11000"))):
        region = region_frame(named, agency=agency, codes=codes)
        assert region["inReview"] and JURISDICTION_UNKNOWN in region["reviewReason"] and VALUE_MISSING not in region["reviewReason"]
    # AI가 적은 지역이 기관 관할과 다르면 확인 필요
    other = region_frame(condition("REGION", "관내 주소지를 둔 사람", regionNames=["충청북도"], regionBasis="RESIDENCE"))
    assert other["inReview"] and JURISDICTION_UNKNOWN in other["reviewReason"]
    # 기관 관할을 모르고 지역 이름도 없으면 확인 필요 질문
    asked = region_frame(condition("REGION", "관내 주소지를 둔 사람", regionBasis="RESIDENCE"), agency="가상관광공사")
    assert asked["kind"] == "ASK" and asked["inReview"] and JURISDICTION_UNKNOWN in asked["reviewReason"]
    # 근거에 지명이 있으면 보통 길(확정)
    plain = region_frame(condition("REGION", "화성시 관내 주소지를 둔 사람", regionNames=["화성시"], regionBasis="RESIDENCE"), agency="가상관광공사")
    assert plain["kind"] == "REGION" and not plain["inReview"]


# 6. 남은 정리: 첨부만 가리키는 제외 칸, 휴·폐업 중복 질문, 기창업 대상군의 사업자 조건


def test_exclusion_field_pointing_only_to_an_attachment_becomes_one_held_question():
    extra = "참여 제한 대상: 붙임파일 참조\n그 밖의 자세한 사항은 붙임파일 참조\n신청 자격: 별첨 2 참고\n"
    made = frame_of([], extra)
    limited, eligible = made["common"]
    assert (limited["kind"], limited["metWhen"], limited["inReview"]) == ("ASK", "NO", True) and ATTACHED in limited["reviewReason"]
    assert limited["question"] == "붙임파일에 적힌 참여 제한 대상에 해당하나요?" and limited["quote"] == "참여 제한 대상: 붙임파일 참조"
    assert (eligible["metWhen"], eligible["inReview"]) == ("YES", True)
    # AI가 같은 줄로 이미 조건을 만들었으면 더하지 않음
    item = condition("OTHER", "참여 제한 대상: 붙임파일 참조", question="붙임파일의 참여 제한 대상인가요?", metWhen="NO")
    assert len(frame_of([item], "참여 제한 대상: 붙임파일 참조\n")["common"]) == 1


def test_suspension_code_and_closure_question_from_one_sentence_become_one_question():
    quote = "국세 체납자 또는 휴·폐업 중인 자"
    items = [
        condition("EXCLUDED_STATUS", quote, excludedCodes=["TAX_ARREARS", "BUSINESS_SUSPENDED"]),
        condition("OTHER", quote, question="지금 폐업 상태인가요?", metWhen="NO"),
    ]
    made = frame_of(items, f"- {quote}\n")
    codes, asked = made["common"]
    assert codes["anyOf"] == ["TAX_ARREARS"]
    assert (asked["question"], asked["metWhen"]) == (MERGED_SUSPENSION, "NO")
    # 휴업 코드뿐이면 제외 유형은 빠지고 질문 하나
    alone = [condition("EXCLUDED_STATUS", "휴업 또는 폐업 중인 기업", excludedCodes=["BUSINESS_SUSPENDED"]), items[1] | {"quote": "휴업 또는 폐업 중인 기업"}]
    [one] = frame_of(alone, "- 휴업 또는 폐업 중인 기업\n")["common"]
    assert one["kind"] == "ASK" and one["question"] == MERGED_SUSPENSION
    # 폐업만 말하는 문장이면 합치지 않음
    closed = [condition("EXCLUDED_STATUS", "폐업 중인 기업", excludedCodes=["BUSINESS_SUSPENDED"]), items[1] | {"quote": "폐업 중인 기업"}]
    assert len(frame_of(closed, "- 폐업 중인 기업\n")["common"]) == 2


def test_running_business_group_gets_a_registration_condition_when_the_text_requires_it():
    text = "- 사업자 등록 전인 개인\n- 창업 3년 이내 기업\n□ 제출 서류: 신청서, 사업자등록증 사본 1부\n"
    pre = condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")
    years = condition("BUSINESS_AGE", "창업 3년 이내 기업", group="biz", years=3, yearsRule="WITHIN")
    made = frame_of([pre, years], text, groups=TWO_GROUPS)
    added = made["groups"][1]["criteria"][-1]
    assert (added["kind"], added["require"], added["inReview"]) == ("BUSINESS_REGISTRATION", "REGISTERED", True)
    assert REGISTRATION_FROM_DOCUMENTS in added["reviewReason"] and added["quote"] == "□ 제출 서류: 신청서, 사업자등록증 사본 1부"
    assert len(made["groups"][0]["criteria"]) == 1  # 예비창업자 대상군에는 더하지 않음
    # 대상군 근거 문장이 사업자 등록을 말하면 확정
    stated = [TWO_GROUPS[0], {"key": "biz", "name": "기창업자", "quote": "사업자 등록을 마친 창업 3년 이내 기업"}]
    text2 = "- 사업자 등록 전인 개인\n- 사업자 등록을 마친 창업 3년 이내 기업\n"
    years2 = years | {"quote": "사업자 등록을 마친 창업 3년 이내 기업"}
    sure = frame_of([pre, years2], text2, groups=stated)["groups"][1]["criteria"][-1]
    assert (sure["kind"], sure["inReview"]) == ("BUSINESS_REGISTRATION", False)
    # 예비창업자에게만 걸린 서류 문장이나 원문에 요구가 없으면 더하지 않음
    only_pre = "- 사업자 등록 전인 개인\n- 창업 3년 이내 기업\n※ 예비창업자의 경우 3개월 이내 창업(사업자등록증 제출)\n"
    notice = "- 사업자 등록 전인 개인\n- 창업 3년 이내 기업\n- 사업자등록증의 주소를 센터로 옮긴 뒤 알려 주세요\n"  # 서류가 아닌 안내
    for extra in (only_pre, notice, "- 사업자 등록 전인 개인\n- 창업 3년 이내 기업\n"):
        assert [c["kind"] for c in frame_of([pre, years], extra, groups=TWO_GROUPS)["groups"][1]["criteria"]] == ["ASK"]
    # 창업지원 틀(closedWithinYears 칸 없음)
    startup = frame_of([pre, years], text, startup=True, groups=TWO_GROUPS)["groups"][1]["criteria"][-1]
    assert startup["kind"] == "BUSINESS_REGISTRATION" and "closedWithinYears" not in startup


def test_startup_frame_uses_the_agency_jurisdiction_too():
    payload = tour() | {
        "field": "STARTUP_SUPPORT",
        "text": TOUR_TEXT + "- 관내에 사업장이 있는 기업\n",
        "record": {},
        "agency": "경기도 화성시",
        "regionCodes": ["41590"],
    }
    item = condition("REGION", "관내에 사업장이 있는 기업", regionBasis="BUSINESS_SITE")
    made = startup_frame(payload, reading(answer([item])), REGIONS)
    assert frame_errors(made) == [] and made["common"][0]["regionCodes"] == ["4159000000"] and not made["common"][0]["inReview"]
