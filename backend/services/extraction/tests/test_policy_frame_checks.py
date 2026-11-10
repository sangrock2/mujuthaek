"""정책 판정 틀 검사(사업공간 채점 뒤 일반 규칙): 지역의 뜻, 대상군 배치, 예외 단서, 목록 정보 값, 표시. 지어낸 공고 글로만 시험합니다."""

import json

from test_policy_judgment import TOUR_TEXT, answer, condition, reading, tour

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.judgment.policy_frame import (
    EXCEPTION,
    META_CONFLICT,
    META_ONLY,
    OTHER_GROUP,
    PLACEMENT,
    RANGE_PART,
    SCOPE,
    VALUE_MISSING,
    YEAR_COUNT,
    exception_clause,
    space_frame,
    startup_frame,
)
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.publish import policy_completed_payload, policy_frame, policy_region_codes
from mujuthaek_extraction.rules.policy.reading import CALL_NAME, PROMPT_VERSION, SYSTEM, read_policy

REGIONS = RegionCodeTable(
    [
        ("1100000000", "서울특별시", True),
        ("4100000000", "경기도", True),
        ("4159000000", "경기도 화성시", True),
        ("4300000000", "충청북도", True),
    ],
    "2026-10-01",
)

# 지어낸 사업공간 모집 글(공간은 경기 화성, 신청 지역 제한 없음)
SPACE_TEXT = TOUR_TEXT + ("□ 입주 공간 : 경기도 화성시 가상로 12, 별빛창업센터 3층\n□ 입주 후 1개월 이내 사업장 주소를 센터로 이전해야 함\n")
LOCATION = {"names": ["경기도 화성시"], "quote": "경기도 화성시 가상로 12, 별빛창업센터 3층"}


def space(text=SPACE_TEXT, **fields):
    return tour() | {"text": text} | fields


def frame_of(conditions, extra="", *, startup=False, record=None, **fields):
    payload = tour() | {"text": TOUR_TEXT + extra, "record": record or {}}
    if startup:
        payload["field"] = "STARTUP_SUPPORT"
    made = (startup_frame if startup else space_frame)(payload, reading(answer(conditions, **fields)), REGIONS)
    assert frame_errors(made) == []
    return made


# 1. 지역의 뜻: 사업공간 regionCodes는 공간이 있는 곳, 신청자 지역 제한은 틀의 REGION 조건으로만


def test_space_region_codes_are_where_the_space_is_even_when_the_collector_says_nationwide():
    read = reading(answer([], spaceLocation=LOCATION))
    nationwide = space(regionScope="NATIONWIDE", regionNames=[], regionCodes=[])
    assert policy_region_codes(nationwide, REGIONS, read) == ["41590"]
    # 수집기가 다른 시도(기관 소재지)를 줘도 확인한 공간 위치를 씀
    assert policy_region_codes(space(regionScope="SIDO", regionNames=["서울"], regionCodes=[]), REGIONS, read) == ["41590"]


def test_space_location_must_be_quoted_and_named_otherwise_the_collector_value_stays():
    collector = space(regionScope="SIDO", regionNames=["서울"], regionCodes=[])
    unquoted = reading(answer([], spaceLocation={"names": ["경기도 화성시"], "quote": "원문에 없는 주소 문장"}))
    assert policy_region_codes(collector, REGIONS, unquoted) == ["11000"]
    other_name = reading(answer([], spaceLocation={"names": ["충청북도"], "quote": LOCATION["quote"]}))
    assert policy_region_codes(collector, REGIONS, other_name) == ["11000"]
    assert policy_region_codes(space(regionScope="NATIONWIDE", regionNames=[], regionCodes=[]), REGIONS, reading(answer([]))) == []
    # 「전국」은 공간 위치가 아님
    nationwide = reading(answer([], spaceLocation={"names": ["전국"], "quote": "2027년도 관광기업지원센터(서울)"}))
    assert policy_region_codes(collector, REGIONS, nationwide) == ["11000"]


def test_startup_support_keeps_support_region_meaning():
    startup = space(field="STARTUP_SUPPORT", regionScope="SIDO", regionNames=["서울"], regionCodes=[])
    assert policy_region_codes(startup, REGIONS, reading(answer([], spaceLocation=LOCATION))) == ["11000"]


def test_applicant_region_restriction_is_a_frame_condition_while_the_payload_carries_the_space_location():
    text = SPACE_TEXT + "□ 신청 자격 : 공고일 기준 서울특별시에 주소를 둔 개인\n"
    restricted = condition("REGION", "공고일 기준 서울특별시에 주소를 둔 개인", regionNames=["서울특별시"], regionBasis="RESIDENCE")
    payload = space(text, regionScope="NATIONWIDE", regionNames=[], regionCodes=[])
    read = reading(answer([restricted], spaceLocation=LOCATION))
    event = policy_completed_payload(payload, policy_frame(payload, read, REGIONS), REGIONS, read)
    assert event["regionCodes"] == ["41590"]
    [region] = event["judgment"]["common"]
    assert (region["kind"], region["basis"], region["regionCodes"], region["inReview"]) == ("REGION", "RESIDENCE", ["1100000000"], False)


def test_reading_accepts_answers_with_and_without_the_new_space_location():
    old = answer([])
    assert "spaceLocation" not in old
    for made in (old, answer([], spaceLocation=LOCATION)):
        model = RecordedModel({CALL_NAME: [json.dumps(made)]})
        assert read_policy(space(), model).answer == made


# 2. 대상군 배치


PRE_AND_EXISTING = [
    {"key": "pre", "name": "예비창업자", "quote": "(예비) 입주 후 3개월 안에 창업할 사람"},
    {"key": "biz", "name": "기창업자", "quote": "(기업) 창업 5년이 지나지 않은 기업"},
]
FORMS = "입주 형태 : 본점 또는 지점 또는 기업부설 연구소"
GROUP_TEXT = "(예비) 입주 후 3개월 안에 창업할 사람\n(기업) 창업 5년이 지나지 않은 기업\n" + FORMS + "\n세금을 내지 않고 미룬 기업은 제외\n"


def test_common_condition_that_presumes_an_existing_business_is_held_when_a_pre_founder_group_exists():
    conditions = [
        condition("PRE_FOUNDER", "(예비) 입주 후 3개월 안에 창업할 사람", group="pre"),
        condition("REGISTERED", "(기업) 창업 5년이 지나지 않은 기업", group="biz"),
        condition("OTHER", FORMS, anyOf="form", option="1", question="본점에 해당하나요?", metWhen="YES"),
        condition("OTHER", FORMS, anyOf="form", option="2", question="지점에 해당하나요?", metWhen="YES"),
        condition("OTHER", FORMS, anyOf="form", option="3", question="기업부설 연구소에 해당하나요?", metWhen="YES"),
        condition("EXCLUDED_STATUS", "세금을 내지 않고 미룬 기업은 제외", excludedCodes=["TAX_ARREARS"]),
    ]
    made = frame_of(conditions, GROUP_TEXT, groups=PRE_AND_EXISTING)
    forms, tax = made["common"]
    assert forms["kind"] == "ANY_OF" and forms["inReview"] and PLACEMENT in forms["reviewReason"]
    assert not tax["inReview"]  # 제외 조건은 예비창업자도 갖출 수 있음
    # 예비창업자 길이 없으면 같은 공통 조건을 그대로 둠
    alone = frame_of(conditions[1:], GROUP_TEXT, groups=PRE_AND_EXISTING[1:])
    assert not alone["common"][0]["inReview"]


def test_common_business_age_is_held_when_a_path_inside_any_of_is_for_pre_founders():
    text = "예비창업자 또는 법인 설립 전인 개인\n창업 후 4년 이내인 기업\n"
    conditions = [
        condition("PRE_FOUNDER", "예비창업자 또는 법인 설립 전인 개인", anyOf="who", option="1"),
        condition("REGISTERED", "창업 후 4년 이내인 기업", anyOf="who", option="2"),
        condition("BUSINESS_AGE", "창업 후 4년 이내인 기업", years=4, yearsRule="WITHIN"),
    ]
    either, years = frame_of(conditions, text, startup=True)["common"]
    assert not either["inReview"] and years["inReview"] and PLACEMENT in years["reviewReason"]


def test_pre_founder_only_exclusion_on_a_mixed_group_is_held_but_kept_on_a_pre_founder_group():
    text = "법인 창업 6년 이내 기업\n사업자 등록이 없는 개인\n예비창업자의 경우 최근 6개월 안에 폐업한 이력이 있으면 신청 불가\n"
    rule = "예비창업자의 경우 최근 6개월 안에 폐업한 이력이 있으면 신청 불가"
    mixed = [
        condition("REGISTERED", "법인 창업 6년 이내 기업", group="member", anyOf="who", option="1"),
        condition("PRE_FOUNDER", "사업자 등록이 없는 개인", group="member", anyOf="who", option="2"),
        condition("OTHER", rule, group="member", question="최근 6개월 안에 폐업했나요?", metWhen="NO"),
    ]
    groups = [{"key": "member", "name": "회원기업", "quote": "법인 창업 6년 이내 기업"}]
    [asked] = [c for c in frame_of(mixed, text, groups=groups)["groups"][0]["criteria"] if c["kind"] == "ASK"]
    assert asked["inReview"] and SCOPE in asked["reviewReason"]
    pre = [
        condition("PRE_FOUNDER", "사업자 등록이 없는 개인", group="pre"),
        condition("OTHER", rule, group="pre", question="최근 6개월 안에 폐업했나요?", metWhen="NO"),
    ]
    kept = frame_of(pre, text, groups=[{"key": "pre", "name": "예비창업자", "quote": "사업자 등록이 없는 개인"}])["groups"][0]["criteria"]
    assert not any(c["inReview"] for c in kept)


def test_group_exclusion_that_names_another_group_is_held():
    text = "이 센터에 입주했던 기업은 신청 불가\n※ 다만, 공유석 기업으로 지원받은 기업은 전용실 기업으로 지원 가능\n공유석 기업 자격\n전용실 기업 자격\n"
    groups = [{"key": "room", "name": "전용실 기업", "quote": "전용실 기업 자격"}, {"key": "desk", "name": "공유석 기업", "quote": "공유석 기업 자격"}]
    conditions = [condition("OTHER", "이 센터에 입주했던 기업은 신청 불가", group="room", question="이 센터에 입주한 적이 있나요?", metWhen="NO")]
    [asked] = frame_of(conditions, text, groups=groups)["groups"][0]["criteria"]
    assert asked["inReview"] and OTHER_GROUP in asked["reviewReason"] and EXCEPTION in asked["reviewReason"]


# 3. 예외 단서


def test_exclusion_with_an_exception_on_the_next_line_is_held_and_the_question_carries_it():
    text = "- 국세·지방세를 체납 중인 자\n※ 다만, 분할 납부를 승인받아 성실히 내고 있는 경우 신청 가능\n- 휴업 중인 기업\n"
    coded = frame_of([condition("EXCLUDED_STATUS", "국세·지방세를 체납 중인 자", excludedCodes=["TAX_ARREARS"])], text)["common"][0]
    assert coded["kind"] == "EXCLUDED_STATUS" and coded["inReview"] and EXCEPTION in coded["reviewReason"]
    asked = frame_of([condition("OTHER", "국세·지방세를 체납 중인 자", question="세금을 체납 중인가요?", metWhen="NO")], text)["common"][0]
    assert asked["inReview"] and "분할 납부를 승인받아" in asked["question"]
    plain = frame_of([condition("EXCLUDED_STATUS", "휴업 중인 기업", excludedCodes=["BUSINESS_SUSPENDED"])], text)["common"][0]
    assert not plain["inReview"]  # 다음 줄이 다른 항목이면 예외가 아님


def test_exception_inside_the_quote_and_requirement_notes_that_are_not_exceptions():
    assert exception_clause("휴업 중인 기업(단, 재개업 신고를 마친 경우 제외)", "휴업 중인 기업(단, 재개업 신고를 마친 경우 제외)")
    assert exception_clause("최근 1년 안에 폐업한 자. 이종 업종으로 창업하는 경우 신청 가능", "최근 1년 안에 폐업한 자. 이종 업종으로 창업하는 경우 신청 가능")
    note = "* 예비창업자의 경우 입주 후 4개월 이내 사업자 등록이 가능한 자"
    assert exception_clause(note, note) is None
    assert exception_clause("단체 숙소 운영 업종", "단체 숙소 운영 업종") is None


# 4. 목록 정보에만 있는 값·본문과 다른 값, 「N년차」


META_TEXT = (
    "[항목]\n신청 대상: 일반기업,1인 창조기업\n대상 연령: 만 20세 이상 ~ 만 39세 이하\n창업 기간: 3년미만\n"
    "[원문 화면: https://example.invalid/x]\n대상연령\n만 20세 이상 ~ 만 39세 이하\n"
)
META_RECORD = {"aply_trgt": "일반기업,1인 창조기업", "biz_trgt_age": "만 20세 이상 ~ 만 39세 이하", "biz_enyy": "3년미만"}


def test_values_only_in_list_metadata_are_held():
    age = frame_of([condition("AGE", "만 20세 이상 ~ 만 39세 이하", minAge=20, maxAge=39)], META_TEXT, record=META_RECORD)["common"][0]
    assert age["inReview"] and META_ONLY in age["reviewReason"]
    kinds = frame_of([condition("STATUS", "일반기업,1인 창조기업", statusCodes=["ONE_PERSON_CREATIVE"])], META_TEXT, record=META_RECORD, startup=True)
    assert kinds["common"][0]["inReview"] and META_ONLY in kinds["common"][0]["reviewReason"]
    # 같은 값이 본문에도 있으면 목록 정보만의 값이 아님
    body = META_TEXT + "모집 대상 : 만 20세 이상 ~ 만 39세 이하 청년 창업자\n"
    assert not frame_of([condition("AGE", "만 20세 이상 ~ 만 39세 이하 청년 창업자", minAge=20, maxAge=39)], body, record=META_RECORD)["common"][0]["inReview"]


def test_body_age_that_differs_from_list_metadata_is_held():
    body = META_TEXT + "모집 대상 : 공고일 기준 만 17세 이상 39세 이하 청년\n"
    age = frame_of([condition("AGE", "공고일 기준 만 17세 이상 39세 이하 청년", minAge=17, maxAge=39)], body, record=META_RECORD)["common"][0]
    assert age["inReview"] and META_CONFLICT in age["reviewReason"]
    # 목록 정보가 세 구간 모두(제한 없음 기본값)면 비교하지 않음
    every = META_RECORD | {"biz_trgt_age": "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상"}
    plain = "[항목]\n대상 연령: 만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상\n모집 대상 : 공고일 기준 만 17세 이상 39세 이하 청년\n"
    assert not frame_of([condition("AGE", "공고일 기준 만 17세 이상 39세 이하 청년", minAge=17, maxAge=39)], plain, record=every)["common"][0]["inReview"]


def test_year_count_wording_is_not_taken_as_within_years():
    quote = "사업 개시일부터 5년차 이하인 중소기업"
    for startup in (False, True):
        made = frame_of([condition("BUSINESS_AGE", quote, years=5, yearsRule="WITHIN")], quote + "\n", startup=startup)["common"][0]
        assert made["inReview"] and YEAR_COUNT in made["reviewReason"]
    within = "사업 개시일부터 5년 이내인 중소기업"
    assert not frame_of([condition("BUSINESS_AGE", within, years=5, yearsRule="WITHIN")], within + "\n", startup=True)["common"][0]["inReview"]


# 5. 표시


def test_path_labels_never_show_internal_codes():
    text = "사업자 등록이 없는 개인\n최근 2년 안에 폐업한 적이 없는 자\n창업 3년 이내 기업\n"
    conditions = [
        condition("PRE_FOUNDER", "사업자 등록이 없는 개인", anyOf="who", option="1"),
        condition("NO_RECENT_CLOSURE", "최근 2년 안에 폐업한 적이 없는 자", anyOf="who", option="1", closedYears=2),
        condition("BUSINESS_AGE", "창업 3년 이내 기업", anyOf="who", option="2", years=3, yearsRule="WITHIN"),
    ]
    for startup in (False, True):
        [either] = frame_of(conditions, text, startup=startup)["common"]
        labels = [o["label"] for o in either["options"]]
        assert labels[0] == "1번째 길: 예비창업자 + 최근 폐업 이력 없음" and not any(c.isascii() and c.isupper() for label in labels for c in label)


def test_status_the_frame_cannot_hold_becomes_one_question_with_its_korean_name():
    quote = "일반 법인, 1인 창조기업 모두 신청 가능"
    conditions = [
        condition("OTHER", quote, anyOf="kind", option="1", question="일반 법인인가요?", metWhen="YES"),
        condition("STATUS", quote, anyOf="kind", option="2", statusCodes=["ONE_PERSON_CREATIVE"]),
    ]
    [either] = frame_of(conditions, quote + "\n")["common"]
    second = either["options"][1]["criteria"]
    assert [(c["kind"], c["question"]) for c in second] == [("ASK", "1인 창조기업에 해당하나요?")]
    assert either["options"][1]["label"] == "2번째 길: 1인 창조기업"


def test_whole_sentence_question_is_not_added_next_to_conditions_split_from_the_same_sentence():
    quote = "창업 6년 미만의 소상공인으로 사업자 등록을 한 기업"
    conditions = [
        condition("BUSINESS_AGE", quote, years=6, yearsRule="UNDER"),
        condition("REGISTERED", quote),
        condition("OTHER", quote),  # 질문 없는 같은 문장 → 문장 통째 질문이 되어 두 번 묻게 됨
    ]
    made = frame_of(conditions, quote + "\n", startup=True)["common"]
    assert [c["kind"] for c in made] == ["BUSINESS_AGE", "BUSINESS_REGISTRATION"]
    # 다른 문장의 질문 없는 조건은 남김
    other = frame_of(
        [*conditions[:2], condition("OTHER", "본 센터 운영 규정을 지킬 수 있는 자")], quote + "\n본 센터 운영 규정을 지킬 수 있는 자\n", startup=True
    )
    assert [c["kind"] for c in other["common"]] == ["BUSINESS_AGE", "BUSINESS_REGISTRATION", "ASK"]


def test_age_review_reason_names_the_real_cause():
    quote = "공고일 기준 만 18세 이상 만 34세 이하"
    half = frame_of([condition("AGE", quote, maxAge=34)], quote + "\n")["common"][0]
    assert RANGE_PART in half["reviewReason"] and VALUE_MISSING not in half["reviewReason"]
    wrong = frame_of([condition("AGE", quote, maxAge=30)], quote + "\n")["common"][0]
    assert VALUE_MISSING in wrong["reviewReason"]


# 6. 프롬프트


def test_prompt_version_and_rules_for_quotes_regions_and_preferences():
    assert PROMPT_VERSION == "policy/v8"
    for rule in ("spaceLocation", "이어진 한 구간", "입주 뒤 이전 의무", "예비창업자(사업자 등록 전)", "preferences에 넣습니다"):
        assert rule in SYSTEM
