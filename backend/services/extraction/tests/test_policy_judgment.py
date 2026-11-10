"""정책 공고(창업지원·사업공간 모집) 판정 틀: AI 글 읽기(녹화 응답) → 코드 변환 → extraction.completed. 네트워크·유료 호출 없음."""

import copy
import json

from test_publish import EVENT_SCHEMA, envelope
from test_space_judgment import TOUR
from test_startup_judgment import WATEROUND

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.judgment.policy_frame import NO_REFERENCE, QUOTE_MISSING, RANGE_PART, VALUE_MISSING, opened_range, space_frame, startup_frame
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.publish import policy_completed_payload, policy_frame, policy_region_codes
from mujuthaek_extraction.rules.policy.reading import CALL_NAME, PolicyReading, read_policy
from mujuthaek_extraction.worker import judge_policy

REGIONS = RegionCodeTable([("1100000000", "서울특별시", True), ("2700000000", "대구광역시", True), ("2720000000", "대구광역시 남구", True)], "2026-10-01")

# 관광기업지원센터(서울) 모집 원문 화면 본문 일부(2026-10-22 수집 샘플)
TOUR_TEXT = (
    "제목: 2027년도 관광기업지원센터(서울) 신규 입주기업 모집\n기관: 한국관광공사\n"
    "신청대상\n- 관광과 관련한 창의적이고 지속가능한 사업을 영위하고 있는 공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자\n"
    "- 관광 관련 사업을 운영하는 창업 10년 이내 신산업창업분야* 법인사업자 또는 개인사업자\n"
    "제외대상\n- 공고일 기준 정부 지원사업에 참여제한으로 제재 중인 사업자\n- 금융기관으로부터 채무불이행으로 규제 중인 자 또는 휴/폐업 중인 사업자\n"
    "2026년 10월 07일\n한국관광공사\n"
    "7. 필수요건: 입주계약체결 후 3개월 이내에 관광기업지원센터 입주 사무실로 본사 주소지 이전 필수\n"
    "- (가점)중소기업기술마켓 등록인증서 : 서류평가시 가점 1점 부여\n"
)


def condition(kind, quote, **fields):
    base = {
        "group": None,
        "anyOf": None,
        "option": None,
        "kind": kind,
        "minAge": None,
        "maxAge": None,
        "regionNames": [],
        "regionBasis": None,
        "years": None,
        "yearsRule": None,
        "openedFrom": None,
        "openedTo": None,
        "closedYears": None,
        "closedFrom": None,
        "closedTo": None,
        "revenueYear": None,
        "revenueMinWon": None,
        "revenueMaxWon": None,
        "industryCodes": [],
        "statusCodes": [],
        "excludedCodes": [],
        "question": None,
        "metWhen": None,
        "quote": quote,
    }
    return base | fields


def answer(conditions, **fields):
    base = {
        "relevant": True,
        "announcedOn": {"date": "2026-10-07", "quote": "2026년 10월 07일"},
        "referenceRule": "ANNOUNCEMENT",
        "referenceDate": {"date": None, "quote": None},
        "supportRegions": {"names": [], "quote": None},
        "groups": [],
        "conditions": conditions,
        "preferences": [],
        "notes": [],
    }
    return base | fields


TOUR_ANSWER = answer(
    [
        condition("REGISTERED", "창업 7년 이내의 법인사업자 또는 개인사업자"),
        condition("BUSINESS_AGE", "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자", years=7, yearsRule="WITHIN", anyOf="age"),
        condition("BUSINESS_AGE", "창업 10년 이내 신산업창업분야* 법인사업자 또는 개인사업자", years=10, yearsRule="WITHIN", anyOf="age"),
        condition("EXCLUDED_STATUS", "공고일 기준 정부 지원사업에 참여제한으로 제재 중인 사업자", excludedCodes=["PROGRAM_SANCTION"]),
        condition(
            "EXCLUDED_STATUS",
            "금융기관으로부터 채무불이행으로 규제 중인 자 또는 휴/폐업 중인 사업자",
            excludedCodes=["CREDIT_DELINQUENT", "BUSINESS_SUSPENDED"],
        ),
    ],
    preferences=[
        {
            "label": "중소기업기술마켓 등록인증서",
            "group": None,
            "effect": "BONUS_POINTS",
            "points": 1,
            "question": "중소기업기술마켓 등록인증서가 있나요?",
            "quote": "(가점)중소기업기술마켓 등록인증서 : 서류평가시 가점 1점 부여",
        }
    ],
    notes=[{"kind": "OBLIGATION", "group": None, "text": "입주 계약 후 3개월 안에 본사 주소지 이전", "quote": "입주계약체결 후 3개월 이내에"}],
)


def tour():
    made = copy.deepcopy(TOUR)
    return made | {
        "text": TOUR_TEXT,
        "title": "2027년도 관광기업지원센터(서울) 신규 입주기업 모집",
        "regionScope": "SIDO",
        "regionNames": ["서울"],
        "regionCodes": [],
    }


def reading(made, *, truncated=False):
    return PolicyReading(made, truncated)


def test_ai_reading_request_sends_only_the_policy_text_and_checks_the_answer_shape():
    model = RecordedModel({CALL_NAME: [json.dumps(TOUR_ANSWER)]})
    read = read_policy(tour(), model)
    assert read.answer == TOUR_ANSWER and not read.truncated
    assert model.requests[0].user == TOUR_TEXT  # 정책 공고는 PDF 없이 글만
    broken = RecordedModel({CALL_NAME: ['{"relevant": true}']})
    try:
        read_policy(tour(), broken)
    except ModelError as error:
        assert error.code == "BAD_SHAPE"
    else:
        raise AssertionError("형식이 틀린 답을 받았습니다")


def test_space_frame_from_reading_keeps_codes_asks_what_the_frame_cannot_hold_and_dates_from_the_posted_line():
    frame = space_frame(tour(), reading(TOUR_ANSWER), REGIONS)
    assert frame_errors(frame) == []
    assert frame["referenceDate"] == "2026-10-07"  # 「공고일 기준」 → 근거 문장이 있는 공고일
    registered, either, sanction, excluded = frame["common"]
    assert (registered["kind"], registered["require"], registered["closedWithinYears"]) == ("BUSINESS_REGISTRATION", "REGISTERED", None)
    # 사업공간 틀에는 업력 상한 칸이 없어 「7년 이내 또는 신산업 10년 이내」는 질문 두 길
    assert either["kind"] == "ANY_OF" and [o["criteria"][0]["kind"] for o in either["options"]] == ["ASK", "ASK"]
    assert (sanction["kind"], sanction["metWhen"]) == ("ASK", "NO")  # 참여제한 제재는 사업공간 틀 코드에 없음
    assert (excluded["kind"], excluded["anyOf"], excluded["inReview"]) == ("EXCLUDED_STATUS", ["CREDIT_DELINQUENT", "BUSINESS_SUSPENDED"], False)
    [bonus] = frame["preferences"]
    assert (bonus["effect"], bonus["points"], bonus["criteria"][0]["kind"]) == ("BONUS_POINTS", 1, "ASK")
    assert frame["notes"][0]["kind"] == "OBLIGATION"


def test_startup_frame_computes_business_age_dates_from_the_reference_and_uses_startup_codes():
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT"}, reading(TOUR_ANSWER), REGIONS)
    assert frame_errors(frame) == []
    registered, either, sanction, excluded = frame["common"]
    seven, ten = (o["criteria"][0] for o in either["options"])
    assert (seven["kind"], seven["openedFrom"], seven["openedTo"]) == ("BUSINESS_AGE", "2019-10-07", "2026-10-07")
    assert (ten["openedFrom"], ten["openedTo"]) == ("2016-10-07", "2026-10-07")
    assert (sanction["kind"], sanction["anyOf"]) == ("EXCLUDED_STATUS", ["PROGRAM_SANCTION"])


def test_business_age_rules_follow_the_frame_document():
    from datetime import date

    reference = date(2026, 1, 23)
    assert opened_range(reference, 3, "WITHIN") == ("2023-01-23", "2026-01-23")
    assert opened_range(reference, 3, "UNDER") == ("2023-01-24", "2026-01-23")
    assert opened_range(reference, 7, "AT_LEAST") == (None, "2019-01-23")
    assert opened_range(reference, 7, "OVER") == (None, "2019-01-22")
    assert opened_range(date(2024, 2, 29), 1, "WITHIN") == ("2023-02-28", "2024-02-29")


def test_unchecked_ai_values_are_in_review_and_missing_reference_turns_years_into_a_question():
    made = answer(
        [
            condition("AGE", "만 39세 이하인 자", maxAge=29),  # 근거 문장에 없는 값
            condition("REGISTERED", "원문에 없는 문장입니다"),
            condition("BUSINESS_AGE", "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자", years=7, yearsRule="WITHIN"),
            condition("REGION", "대구광역시 남구 소재 기업", regionNames=["대구광역시 남구"], regionBasis="BUSINESS_SITE"),
        ],
        referenceRule="NONE",
    )
    text = TOUR_TEXT + "만 39세 이하인 자\n대구광역시 남구 소재 기업\n"
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT", "text": text}, reading(made), REGIONS)
    assert frame_errors(frame) == [] and frame["referenceDate"] is None
    age, registered, years, region = frame["common"]
    assert age["inReview"] and VALUE_MISSING in age["reviewReason"]
    assert registered["inReview"] and QUOTE_MISSING in registered["reviewReason"]
    assert years["kind"] == "ASK" and NO_REFERENCE in years["reviewReason"]
    assert (region["kind"], region["regionCodes"], region["inReview"]) == ("REGION", ["2720000000"], False)


def test_space_frame_needs_a_reference_date_from_the_text():
    made = answer([condition("REGISTERED", "창업 7년 이내의 법인사업자 또는 개인사업자")], announcedOn={"date": "2026-10-08", "quote": "2026년 10월 07일"})
    assert space_frame(tour(), reading(made), REGIONS) is None  # 근거 문장과 날짜가 다르면 기준일로 쓰지 않음


def test_policy_event_carries_the_frame_and_support_regions_and_falls_back_to_band_rules():
    event = policy_completed_payload(tour(), policy_frame(tour(), reading(TOUR_ANSWER), REGIONS), REGIONS)
    assert tools().validate(envelope(event), EVENT_SCHEMA) == []
    assert (event["field"], event["rawPostId"], event["regionCodes"]) == ("SPACE_RECRUITMENT", TOUR["rawPolicyId"], ["11000"])
    assert event["schedule"] == {"applyStartOn": None, "applyEndOn": None} or event["schedule"] is None
    assert event["judgment"]["schema"] == "business-space-judgment.v1"
    # AI 읽기가 없으면 K-Startup 구간 칸 규칙으로(창업지원)
    startup = WATEROUND | {"title": "워터라운드", "agency": "K-water", "regionScope": "NATIONWIDE", "regionNames": [], "regionCodes": []}
    startup["record"] = startup["record"] | {"pbanc_rcpt_bgng_dt": "20261019", "pbanc_rcpt_end_dt": "20261102"}
    fallback = policy_completed_payload(startup, policy_frame(startup, None, REGIONS), REGIONS)
    assert tools().validate(envelope(fallback), EVENT_SCHEMA) == []
    assert fallback["regionCodes"] == [] and fallback["schedule"] == {"applyStartOn": "2026-10-19", "applyEndOn": "2026-11-02"}
    # AI가 창업 지원·사업공간 모집이 아니라고 읽으면 보내지 않음
    assert policy_frame(tour(), reading(TOUR_ANSWER | {"relevant": False}), REGIONS) is None


def test_support_region_must_be_known_because_an_empty_list_means_nationwide():
    assert policy_region_codes({"regionScope": "NATIONWIDE"}, REGIONS) == []
    assert policy_region_codes({"regionScope": "SIGUNGU", "regionCodes": ["27200"]}, REGIONS) == ["27200"]
    assert policy_region_codes({"regionScope": "SIDO", "regionNames": ["서울"], "regionCodes": []}, REGIONS) == ["11000"]
    assert policy_region_codes({"regionScope": "UNKNOWN", "regionNames": [], "regionCodes": []}, REGIONS) is None
    assert policy_region_codes({"regionScope": "SIDO", "regionNames": ["없는도"], "regionCodes": []}, REGIONS) is None


class FakeStore:
    def __init__(self):
        self.saved, self.seen = [], set()

    def judged(self, raw_event):
        return raw_event["eventId"] in self.seen

    def save_judgment(self, raw_event, event):
        if raw_event["eventId"] in self.seen:
            return False
        self.seen.add(raw_event["eventId"])
        self.saved.append(event)
        return True


def test_worker_reads_with_ai_once_per_collected_event_and_ignores_benefit():
    store = FakeStore()
    model = RecordedModel({CALL_NAME: [json.dumps(TOUR_ANSWER)]})
    collected = {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa187e", "payload": tour()}
    assert judge_policy(store, collected, model, REGIONS)
    assert store.saved[0]["payload"]["judgment"]["common"][0]["kind"] == "BUSINESS_REGISTRATION"
    assert judge_policy(store, collected, model, REGIONS) is None and len(model.requests) == 1  # 같은 수집 이벤트는 AI를 다시 부르지 않음
    benefit = {"eventId": "01a151da-ca63-72ad-8c83-af6d043b2597", "payload": tour() | {"field": "BENEFIT"}}
    assert judge_policy(store, benefit, model, REGIONS) is None and len(store.saved) == 1


def test_worker_retries_temporary_ai_failures_and_falls_back_on_permanent_ones():
    import pytest

    from mujuthaek_extraction.worker import AiUnavailable

    store = FakeStore()
    collected = {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1871", "payload": tour()}
    temporary = RecordedModel({CALL_NAME: [ModelError("연결 실패", transient=True, code="NETWORK")]})
    with pytest.raises(AiUnavailable):  # 큐로 되돌려 나중에 AI로 다시(리뷰 2026-10-22)
        judge_policy(store, collected, temporary, REGIONS)
    assert store.saved == []
    model = RecordedModel({CALL_NAME: [ModelError("형식이 틀린 답", transient=False, code="BAD_SHAPE")]})
    assert judge_policy(store, collected, model, REGIONS)
    frame = store.saved[0]["payload"]["judgment"]
    assert frame["referenceDate"] == "2026-10-07" and frame["common"][0]["kind"] == "BUSINESS_REGISTRATION"  # 원문 게시일 줄 규칙


def test_conditions_of_one_path_stay_together_inside_any_of():
    # 실측 2026-10-22 오픈이노베이션: 「7년 이내 창업기업 또는 10년 이내 신산업 분야 창업기업」이 세 길(7년 / 10년 / 신산업)로 나뉘어
    # 신산업이 아닌 9년차 기업도 통과했음. 같은 option은 한 길로 묶습니다
    text = TOUR_TEXT + "② 창업기업 : 1) 공고일 기준 창업 7년 이내 창업기업 또는 2) 10년 이내 신산업 분야 창업기업\n"
    quote = "1) 공고일 기준 창업 7년 이내 창업기업 또는 2) 10년 이내 신산업 분야 창업기업"
    made = answer(
        [
            condition("BUSINESS_AGE", quote, years=7, yearsRule="WITHIN", anyOf="a", option="1"),
            condition("BUSINESS_AGE", quote, years=10, yearsRule="WITHIN", anyOf="a", option="2"),
            condition("OTHER", quote, anyOf="a", option="2", question="신산업 분야 창업기업인가요?", metWhen="YES"),
        ]
    )
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT", "text": text}, reading(made), REGIONS)
    assert frame_errors(frame) == []
    [either] = frame["common"]
    first, second = either["options"]
    assert [c["kind"] for c in first["criteria"]] == ["BUSINESS_AGE"]
    assert [c["kind"] for c in second["criteria"]] == ["BUSINESS_AGE", "ASK"] and second["label"].startswith("2번째 길: 업력 10년")


def test_unknown_collector_region_uses_the_quoted_region_from_the_text_and_region_groups_expand():
    # 실측 2026-10-22 기업마당: 수집기 지역 「모름」(강원 특구)·「충청권」이라 지원 지역을 정하지 못해 틀을 보내지 못했음
    regions = RegionCodeTable(
        [(c, n, True) for c, n in [("3000000000", "대전광역시"), ("3611000000", "세종특별자치시"), ("4300000000", "충청북도"), ("4400000000", "충청남도")]]
        + [("5100000000", "강원특별자치도", True)],
        "2026-10-01",
    )
    group = {"regionScope": "SIDO", "regionNames": ["충청권"], "regionCodes": []}
    assert policy_region_codes(group, regions) == ["30000", "36110", "43000", "44000"]
    unknown = {"regionScope": "UNKNOWN", "regionNames": [], "regionCodes": [], "text": "□ 지원대상 : 강원특별자치도 소재 창업기업"}
    quoted = reading(answer([], supportRegions={"names": ["강원특별자치도"], "quote": "강원특별자치도 소재 창업기업"}))
    assert policy_region_codes(unknown, regions, quoted) == ["51000"]
    # 근거 문장이 원문에 없거나 문장에 그 지역이 없으면 쓰지 않음(빈 목록은 전국으로 읽혀 틀림)
    assert policy_region_codes(unknown, regions, reading(answer([], supportRegions={"names": ["강원특별자치도"], "quote": "강원 전역"}))) is None
    assert policy_region_codes(unknown, regions, reading(answer([], supportRegions={"names": ["충청북도"], "quote": "강원특별자치도 소재 창업기업"}))) is None
    assert policy_region_codes(unknown, regions, reading(answer([]))) is None


def test_nationwide_region_condition_is_not_a_restriction():
    # 실측 2026-10-22 서초창업스테이션: 「전국 소재」가 지역 코드로 못 바꾼 확인 필요 질문으로 들어갔음
    text = TOUR_TEXT + "모집대상 : 전국 소재 업력 7년 이내 스타트업\n"
    made = answer([condition("REGION", "모집대상 : 전국 소재 업력 7년 이내 스타트업", regionNames=["전국"], regionBasis="BUSINESS_SITE")])
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT", "text": text}, reading(made), REGIONS)
    assert frame_errors(frame) == [] and frame["common"] == []


def first_of(conditions, extra_text, regions=REGIONS):
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT", "text": TOUR_TEXT + extra_text}, reading(answer(conditions)), regions)
    assert frame_errors(frame) == []
    return frame["common"][0]


def test_reviewed_wrong_values_are_held_for_review():
    # 리뷰 2026-10-22 재현: 시군구가 다른데 시도 두 글자만 맞음 / 방향이 반대인 나이·업력 / 답 방향 없는 질문
    daegu = RegionCodeTable(
        [("2700000000", "대구광역시", True), ("2720000000", "대구광역시 남구", True), ("2723000000", "대구광역시 북구", True)], "2026-10-01"
    )
    region = first_of(
        [condition("REGION", "대구광역시 북구 소재 기업", regionNames=["대구광역시 남구"], regionBasis="BUSINESS_SITE")], "대구광역시 북구 소재 기업\n", daegu
    )
    assert region["inReview"] and VALUE_MISSING in region["reviewReason"]
    age = first_of([condition("AGE", "대표자 만 40세 이상", maxAge=39)], "대표자 만 40세 이상\n")
    assert age["inReview"]
    years = first_of([condition("BUSINESS_AGE", "공고일 기준 창업 3년 이상 기업", years=3, yearsRule="WITHIN")], "공고일 기준 창업 3년 이상 기업\n")
    assert years["inReview"]
    asked = first_of([condition("OTHER", "신청 제외 대상 기업", question="신청 제외 대상에 해당하나요?")], "신청 제외 대상 기업\n")
    assert asked["inReview"]
    kept = first_of([condition("AGE", "만 19세 이상 39세 이하", minAge=19, maxAge=39)], "만 19세 이상 39세 이하\n")
    assert not kept["inReview"]  # 방향이 맞으면 확정


def test_values_the_frame_cannot_hold_become_questions_instead_of_dropping_the_frame():
    # 리뷰 2026-10-22: 형식이 틀린 날짜·터무니없는 연수 하나로 AI 틀 전체가 버려지거나 예외가 났음
    bad_date = first_of([condition("BUSINESS_AGE", "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자", openedFrom="2019.10.07")], "")
    assert (bad_date["kind"], bad_date["inReview"]) == ("ASK", True)
    huge = first_of([condition("BUSINESS_AGE", "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자", years=5000, yearsRule="WITHIN")], "")
    assert huge["kind"] == "ASK"


def test_truncated_text_is_never_auto_passed_and_unverified_explicit_date_is_not_replaced():
    # 리뷰 2026-10-22: 글이 잘렸는데 조건이 0개면 자동 통과였고, 찍힌 기준일을 확인하지 못하면 공고일로 조용히 바뀌었음
    frame = startup_frame(tour() | {"field": "STARTUP_SUPPORT"}, reading(answer([]), truncated=True), REGIONS)
    assert frame_errors(frame) == [] and [c["inReview"] for c in frame["common"]] == [True]
    explicit = answer([], referenceRule="EXPLICIT", referenceDate={"date": "2026-01-22", "quote": "원문에 없는 기준일 문장"})
    assert space_frame(tour(), reading(explicit), REGIONS) is None


def test_same_policy_version_with_a_new_event_id_is_not_read_again():
    class VersionStore(FakeStore):
        def judged(self, raw_event):
            return (raw_event["payload"]["rawPolicyId"], raw_event["payload"]["version"]) in self.versions

        def save_judgment(self, raw_event, event):
            self.versions.add((raw_event["payload"]["rawPolicyId"], raw_event["payload"]["version"]))
            return super().save_judgment(raw_event, event)

    store = VersionStore()
    store.versions = set()
    model = RecordedModel({CALL_NAME: [json.dumps(TOUR_ANSWER)]})
    assert judge_policy(store, {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1001", "payload": tour()}, model, REGIONS)
    assert judge_policy(store, {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1002", "payload": tour()}, model, REGIONS) is None
    assert len(model.requests) == 1


def revenue(quote, **won):
    return first_of([condition("REVENUE", quote, revenueYear=2025, **won)], quote + "\n")


def test_amount_must_match_with_its_unit():
    # 리뷰 2026-10-22 재현: 「1억원」에서 「1」만 보고 1만 원(10000)이 확정됐음
    assert revenue("2025년 매출액 1억원 이상인 기업", revenueMinWon=10000)["inReview"]
    assert revenue("2025년 매출액 1억원 이상인 기업", revenueMinWon=1)["inReview"]
    assert not revenue("2025년 매출액 1억원 이상인 기업", revenueMinWon=100000000)["inReview"]
    assert not revenue("2025년 매출액 100,000,000원 이상인 기업", revenueMinWon=100000000)["inReview"]
    assert not revenue("2025년 매출액 5,000만 원 이하인 기업", revenueMaxWon=50000000)["inReview"]
    assert revenue("2025년 매출액 5,000만 원 이하인 기업", revenueMaxWon=5000)["inReview"]
    assert not revenue("2025년 매출액 1.5억원 이상인 기업", revenueMinWon=150000000)["inReview"]
    # 섞인 표기는 맞는 값이어도 확정하지 않음(검수로)
    assert revenue("2025년 매출액 1억 5천만원 이상인 기업", revenueMinWon=150000000)["inReview"]
    assert revenue("2025년 매출액 1억 5000만원 이상인 기업", revenueMinWon=50000000)["inReview"]


def test_range_with_only_one_bound_is_held_for_review():
    # 리뷰 2026-10-22 재현: 「만 19~39세」에서 maxAge 39만(또는 minAge 19만) 뽑아도 확정됐음
    quote = "공고일 기준 만 19~39세인 자"
    for bound in ({"maxAge": 39}, {"minAge": 19}):
        age = first_of([condition("AGE", quote, **bound)], quote + "\n")
        assert age["inReview"] and RANGE_PART in age["reviewReason"]  # 실제 이유(한쪽 경계만 읽음)를 적음
        spaced = space_frame(tour() | {"text": TOUR_TEXT + quote + "\n"}, reading(answer([condition("AGE", quote, **bound)])), REGIONS)
        assert frame_errors(spaced) == [] and spaced["common"][0]["inReview"]
    assert first_of([condition("AGE", "만 19세 이상 39세 이하", maxAge=39)], "만 19세 이상 39세 이하\n")["inReview"]
    assert not first_of([condition("AGE", quote, minAge=19, maxAge=39)], quote + "\n")["inReview"]
    assert not first_of([condition("AGE", "대표자 만 39세 이하", maxAge=39)], "대표자 만 39세 이하\n")["inReview"]
    assert not first_of([condition("AGE", "대표자 만 40세 미만", maxAge=39)], "대표자 만 40세 미만\n")["inReview"]
    assert revenue("2025년 매출액 1억원 이상 10억원 미만인 기업", revenueMinWon=100000000)["inReview"]
    assert revenue("2025년 매출액 1억원~10억원인 기업", revenueMaxWon=1000000000)["inReview"]
    assert not revenue("2025년 매출액 1억원 이상 10억원 이하인 기업", revenueMinWon=100000000, revenueMaxWon=1000000000)["inReview"]


def test_permanent_ai_failure_without_a_band_rule_frame_is_not_dropped_silently():
    # 리뷰 2026-10-22: 영구 오류 + 구간 칸 규칙도 없음(기업마당)이면 None을 돌려 ack되어 기록이 남지 않았음
    import pytest

    from mujuthaek_extraction.worker import AiFailed, AiUnavailable

    store = FakeStore()
    bizinfo = {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1901", "payload": tour() | {"provider": "BIZINFO", "field": "STARTUP_SUPPORT"}}
    assert policy_frame(bizinfo["payload"], None, REGIONS) is None
    for code in ("BAD_SHAPE", "HTTP_400", "NOT_CONFIGURED"):
        with pytest.raises(AiFailed):
            judge_policy(store, bizinfo, RecordedModel({CALL_NAME: [ModelError("x", transient=False, code=code)]}), REGIONS)
    # 로컬 AI 연결 실패는 정책 판정에서만 일시 실패(큐로 되돌림)
    for code in ("CONNECTION", "SKIPPED_DOWN"):
        with pytest.raises(AiUnavailable):
            judge_policy(store, bizinfo, RecordedModel({CALL_NAME: [ModelError("x", transient=False, code=code)]}), REGIONS)
    assert store.saved == []
