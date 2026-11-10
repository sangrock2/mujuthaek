"""정책 판정 틀 검사 3차(사업공간 3차 채점 뒤 일반 규칙): 기준일 없는 공고(판정일 기준, 선택 B), 앞으로 둘·옮길 곳은 지역 요건 아님,
공통 제외 단락 항목의 공통 배치, 범위 정의 규칙, 질문 목록·우대 대상군·중복·목록 정보 나이·길 이름. 지어낸 공고 글로만 시험합니다."""

import json
import logging
from datetime import date

from test_policy_frame_checks import REGIONS, frame_of
from test_policy_judgment import TOUR_TEXT, FakeStore, answer, condition, reading, tour

from mujuthaek_extraction.judgment.policy_frame import (
    AGE_FLAG_CONFLICT,
    EVALUATIVE,
    INTENT_REGION,
    JUDGING_DATE_NOTE,
    LAW_SCOPE,
    META_ONLY,
    NO_REFERENCE_DATE,
    OPEN_LIST,
    UNDEFINED,
    VALUE_MISSING,
    _short,
    judging_day,
    space_frame,
    uses_judging_date,
)
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.publish import (
    DATE_UNVERIFIED,
    REGION_UNDECIDED,
    not_sent_reason,
    policy_completed_payload,
    policy_frame,
    policy_frame_with_reason,
)
from mujuthaek_extraction.rules.policy.reading import CALL_NAME, PROMPT_VERSION, SYSTEM
from mujuthaek_extraction.worker import judge_policy

NO_DATE = {"announcedOn": {"date": None, "quote": None}, "referenceRule": "NONE", "referenceDate": {"date": None, "quote": None}}
TODAY = date(2026, 11, 5)
LOCATED = {"spaceLocation": {"names": ["경기도 화성시"], "quote": "경기도 화성시 가상로 12"}}
SPACE_TEXT = TOUR_TEXT + "□ 입주 공간 : 경기도 화성시 가상로 12\n"


def undated(conditions, extra="", **fields):
    payload = tour() | {"text": SPACE_TEXT + extra, "record": {}}
    made = space_frame(payload, reading(answer(conditions, **(NO_DATE | LOCATED | fields))), REGIONS, today=TODAY)
    assert made is not None and frame_errors(made) == []
    return payload, made


def everything(made):
    def walk(criteria):
        return [x for c in criteria for x in [c, *walk([i for o in c.get("options") or [] for i in o["criteria"]])]]

    return walk([*made["common"], *(c for g in made["groups"] for c in g["criteria"])])


# 1. 기준일 없는 공고(선택 B): 판정일을 기준일로, 기준일에 기대는 조건은 확인 필요, 검수 대기로 보냄


def test_space_notice_without_any_date_uses_the_judging_date_and_holds_date_dependent_conditions():
    extra = "- 만 19세 이상 만 39세 이하\n- 창업 3년 이내 기업\n- 최근 2년 이내 폐업한 재창업자\n- 국세 체납자는 신청 불가\n"
    conditions = [
        condition("AGE", "만 19세 이상 만 39세 이하", minAge=19, maxAge=39),
        condition("BUSINESS_AGE", "창업 3년 이내 기업", years=3, yearsRule="WITHIN"),
        condition("CLOSURE_REQUIRED", "최근 2년 이내 폐업한 재창업자", closedYears=2),
        condition("EXCLUDED_STATUS", "국세 체납자는 신청 불가", excludedCodes=["TAX_ARREARS"]),
    ]
    payload, made = undated(conditions, extra)
    assert made["referenceDate"] == "2026-11-05"
    [note] = [n for n in made["notes"] if n["text"].startswith(JUDGING_DATE_NOTE)]
    assert note["kind"] == "OTHER" and "2026-11-05" in note["text"] and uses_judging_date(made)
    age, years, closed, arrears = made["common"]
    for held in (age, years, closed):
        assert held["inReview"] and NO_REFERENCE_DATE in held["reviewReason"]
    assert closed["kind"] == "BUSINESS_REGISTRATION" and closed["closedWithinYears"] == 2
    assert not arrears["inReview"]  # 기준일과 상관없는 조건은 그대로
    completed = policy_completed_payload(payload, made, REGIONS, reading(answer(conditions, **(NO_DATE | LOCATED))))
    # 일부 조건만 확인 필요: 틀은 쓰고(PARTIALLY_PASSED) 그 조건만 판정에서 확인 필요로(사용자 결정 2026-10-23)
    assert completed["reviewStatus"] == "PARTIALLY_PASSED" and completed["regionCodes"] == ["41590"]


def test_judging_date_frame_is_partially_passed_even_without_date_conditions():
    arrears = condition("EXCLUDED_STATUS", "국세 체납자는 신청 불가", excludedCodes=["TAX_ARREARS"])
    payload, made = undated([arrears], "- 국세 체납자는 신청 불가\n")
    assert not any(c["inReview"] for c in everything(made))
    assert policy_completed_payload(payload, made, REGIONS, reading(answer([arrears], **(NO_DATE | LOCATED))))["reviewStatus"] == "PARTIALLY_PASSED"
    # 기준일이 있는 같은 공고는 자동 통과
    dated = space_frame(payload, reading(answer([arrears], **LOCATED)), REGIONS, today=TODAY)
    assert dated["referenceDate"] == "2026-10-07" and not uses_judging_date(dated)
    assert policy_completed_payload(payload, dated, REGIONS, reading(answer([arrears], **LOCATED)))["reviewStatus"] == "AUTO_PASSED"


def test_judging_date_defaults_to_the_korean_date_now():
    made = space_frame(tour() | {"text": SPACE_TEXT}, reading(answer([], **NO_DATE)), REGIONS)
    assert made["referenceDate"] in {judging_day().isoformat(), date.today().isoformat()}


def test_dates_the_ai_claimed_but_could_not_be_verified_still_send_nothing_with_a_precise_reason():
    claimed = answer([], announcedOn={"date": "2026-10-09", "quote": "2026년 10월 07일"}, referenceRule="NONE")
    explicit = answer([], referenceRule="EXPLICIT", referenceDate={"date": None, "quote": None}, announcedOn={"date": None, "quote": None})
    for made in (claimed, explicit):
        # 온통청년처럼 구간 칸 규칙이 없는 출처(K-Startup이면 게시일 줄로 규칙 틀을 만듦)
        frame, reason = policy_frame_with_reason(tour() | {"text": SPACE_TEXT, "provider": "YOUTHCENTER"}, reading(made), REGIONS, today=TODAY)
        assert frame is None and reason.startswith(DATE_UNVERIFIED)
    # 틀은 만들었는데 지역(공간 위치)을 정하지 못함
    lost = tour() | {"text": SPACE_TEXT, "regionScope": "UNKNOWN", "regionNames": [], "regionCodes": []}
    frame = policy_frame(lost, reading(answer([], **NO_DATE)), REGIONS, today=TODAY)
    assert frame is not None and policy_completed_payload(lost, frame, REGIONS) is None
    assert not_sent_reason(lost, frame, None, REGIONS) == REGION_UNDECIDED


def test_worker_logs_why_a_policy_was_not_sent(caplog):
    lost = tour() | {"text": SPACE_TEXT, "regionScope": "UNKNOWN", "regionNames": [], "regionCodes": []}
    model = RecordedModel({CALL_NAME: [json.dumps(answer([], **NO_DATE))]})
    with caplog.at_level(logging.INFO, logger="mujuthaek_extraction.worker"):
        assert judge_policy(FakeStore(), {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1003", "payload": lost}, model, REGIONS) is None
    assert [r.reason for r in caplog.records if hasattr(r, "reason")] == [REGION_UNDECIDED]


# 2. 프롬프트 v7


def test_prompt_v7_reads_criteria_sentences_and_target_cases_as_conditions_and_groups():
    assert PROMPT_VERSION == "policy/v8"
    for rule in ("소득·자산 기준 적용", "「예비창업자의 경우 …」「법인인 경우 …」", "두고자 하는", "질문만 읽고 답할 수 있게", "대상군을 이름으로 지목할 때만"):
        assert rule in SYSTEM


# 3. 앞으로 둘·옮길 곳은 지역 요건이 아님


def test_place_the_applicant_intends_to_use_becomes_an_obligation_note_not_a_region_requirement():
    quote = "화성시 내 사업장을 두고자 하는 창업자"
    made = frame_of([condition("REGION", quote, regionNames=["경기도 화성시"], regionBasis="BUSINESS_SITE")], f"- {quote}\n")
    assert not [c for c in everything(made) if c["kind"] == "REGION"]
    [note] = [n for n in made["notes"] if quote in n["text"]]
    assert note["kind"] == "OBLIGATION" and note["quote"] == quote and "입주 뒤 의무일 수 있어" in note["text"]
    # 「입주 후 전입」도 같음
    after = "입주 후 화성시로 전입하는 자"
    assert not [
        c
        for c in everything(frame_of([condition("REGION", after, regionNames=["경기도 화성시"], regionBasis="RESIDENCE")], f"- {after}\n"))
        if c["kind"] == "REGION"
    ]


def test_region_with_only_move_words_or_inside_a_path_is_held_with_the_real_reason():
    moved = "화성시 전입일로부터 6개월 이상 거주한 자"
    [held] = frame_of([condition("REGION", moved, regionNames=["경기도 화성시"], regionBasis="RESIDENCE")], f"- {moved}\n")["common"]
    assert held["kind"] == "REGION" and held["inReview"] and INTENT_REGION in held["reviewReason"]
    intent = "화성시 내 사업장을 두고자 하는 창업자"
    paths = [
        condition("REGION", intent, regionNames=["경기도 화성시"], regionBasis="BUSINESS_SITE", anyOf="a", option="1"),
        condition("REGISTERED", "창업 7년 이내의 법인사업자 또는 개인사업자", anyOf="a", option="2"),
    ]
    [either] = frame_of(paths, f"- {intent}\n")["common"]
    region = either["options"][0]["criteria"][0]
    assert region["inReview"] and INTENT_REGION in region["reviewReason"]
    # 지금 있는 곳 요건은 그대로 확정, 상위 지역 이름이 근거 문장에 없으면 그 이름을 사유에 적음
    now = "화성시에 사업장이 있는 기업"
    [kept] = frame_of([condition("REGION", now, regionNames=["화성시"], regionBasis="BUSINESS_SITE")], f"- {now}\n")["common"]
    assert kept["kind"] == "REGION" and not kept["inReview"]
    [named] = frame_of([condition("REGION", now, regionNames=["경기도 화성시"], regionBasis="BUSINESS_SITE")], f"- {now}\n")["common"]
    assert VALUE_MISSING in named["reviewReason"] and "「경기도」" in named["reviewReason"] and INTENT_REGION not in named["reviewReason"]


# 4. 공통 제외 단락 항목의 배치

GROUPS = [
    {"key": "pre", "name": "예비창업자", "quote": "사업자 등록 전인 개인"},
    {"key": "biz", "name": "기창업자", "quote": "창업 5년 이내 기업"},
]
EXCLUSION_TEXT = "사업자 등록 전인 개인\n창업 5년 이내 기업\n신청 제외 대상\n- 도박 관련 업을 하는 기업\n- 업력이 9년을 넘은 기업\n"


def test_period_exclusions_stay_in_their_group_and_a_shared_exclusion_moves_once():
    pre = condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")
    gamble = {"kind": "OTHER", "quote": "도박 관련 업을 하는 기업", "question": "도박 관련 업을 하나요?", "metWhen": "NO"}
    period = condition("OTHER", "업력이 9년을 넘은 기업", group="biz", question="업력이 9년을 넘었나요?", metWhen="NO")
    made = frame_of([pre, condition(**gamble, group="biz"), condition(**gamble, group="pre"), period], EXCLUSION_TEXT, groups=GROUPS)
    assert [c["question"] for c in made["common"]] == ["도박 관련 업을 하나요?"]
    assert [c["question"] for c in made["groups"][1]["criteria"]] == ["업력이 9년을 넘었나요?"]
    assert [c["kind"] for c in made["groups"][0]["criteria"]] == ["BUSINESS_REGISTRATION"]


# 5. 범위 정의 규칙


def test_open_lists_law_references_and_evaluative_words_on_the_eligibility_side_are_held():
    text = "응모 자격\n- 모집분야 : 인공지능, 전자, 콘텐츠 등\n- 「가상산업법」에 따른 대상 업종을 영위하는 자\n- 우수한 기술을 보유한 기업\n"
    field = condition("OTHER", "모집분야 : 인공지능, 전자, 콘텐츠 등", question="모집분야에 해당하나요?", metWhen="YES", defined=True)
    [asked] = frame_of([field], text)["common"]
    assert asked["inReview"] and OPEN_LIST in asked["reviewReason"]
    assert asked["question"] == "모집분야에 해당하나요? (원문 목록: 인공지능, 전자, 콘텐츠 등)"
    law = condition("OTHER", "「가상산업법」에 따른 대상 업종을 영위하는 자", question="가상산업법의 대상 업종인가요?", metWhen="YES", defined=True)
    assert LAW_SCOPE in frame_of([law], text)["common"][0]["reviewReason"]
    good = condition("OTHER", "우수한 기술을 보유한 기업", question="우수한 기술을 보유했나요?", metWhen="YES")
    assert EVALUATIVE in frame_of([good], text)["common"][0]["reviewReason"]


def test_exclusion_side_example_lists_stay_confirmed_consistently():
    text = (
        "신청 제외 대상\n- 소음, 진동, 매연 등 공해를 일으키는 업종\n- 「가상법 시행령」 제4조에 따른 제외 업종(숙박업, 주점업 등)\n"
        "- 별난 업종\n- 기타 부적합하다고 인정되는 경우\n"
    )
    noise = condition("OTHER", "소음, 진동, 매연 등 공해를 일으키는 업종", question="공해를 일으키는 업종인가요?", metWhen="NO")
    for defined in (True, False, None):
        assert not frame_of([noise | {"defined": defined}], text)["common"][0]["inReview"]
    law = condition("OTHER", "「가상법 시행령」 제4조에 따른 제외 업종(숙박업, 주점업 등)", question="지원 제외 업종에 해당하나요?", metWhen="NO")
    [listed] = frame_of([law], text)["common"]
    assert not listed["inReview"] and listed["question"] == "지원 제외 업종에 해당하나요? (원문 목록: 숙박업, 주점업 등)"
    # 예시 없는 제외 쪽은 AI의 정의 없음을 따름, 법령만 있으면 확인 필요
    odd = condition("OTHER", "별난 업종", question="별난 업종인가요?", metWhen="NO", defined=False)
    assert UNDEFINED in frame_of([odd], text)["common"][0]["reviewReason"]
    bare = condition("OTHER", "「가상법 시행령」 제4조에 따른 제외 업종", question="제외 업종인가요?", metWhen="NO")
    assert LAW_SCOPE in frame_of([bare], text + "- 「가상법 시행령」 제4조에 따른 제외 업종\n")["common"][0]["reviewReason"]
    # 「부적합」은 제외 쪽 문장이라 심사 판단 규칙으로 잡지 않음
    unfit = condition("OTHER", "기타 부적합하다고 인정되는 경우", question="부적합하다고 인정되는 경우인가요?", metWhen="NO")
    assert not frame_of([unfit], text)["common"][0]["inReview"]


def test_coded_status_from_a_law_reference_is_not_held_by_the_question_rules():
    quote = "「사회적기업 육성법」에 따른 사회적기업"
    [status] = frame_of([condition("STATUS", quote, statusCodes=["SOCIAL_ENTERPRISE"])], f"- {quote}\n")["common"]
    assert status["kind"] == "STATUS" and not status["inReview"]


# 6. 질문 목록 · 우대 대상군 · 중복 · 목록 정보 나이 · 길 이름


def preference(label, quote, group=None, question=None):
    return {"label": label, "group": group, "effect": "PRIORITY", "points": None, "question": question or f"{label}인가요?", "quote": quote}


def test_preferences_not_naming_a_group_are_common_and_duplicates_are_merged():
    text = "- 본교 졸업생이 세운 회사 우대\n- 기창업자 중 고용 우수 기업 우대\n"
    prefs = [
        preference("본교 졸업생 회사", "본교 졸업생이 세운 회사 우대", group="biz"),
        preference("본교 졸업생 회사", "본교 졸업생이 세운 회사 우대", group="biz"),
        preference("고용 우수", "기창업자 중 고용 우수 기업 우대", group="biz"),
    ]
    made = frame_of([condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")], text + "사업자 등록 전인 개인\n", groups=GROUPS, preferences=prefs)
    assert [(p["label"], p["groupId"]) for p in made["preferences"]] == [("본교 졸업생 회사", None), ("고용 우수", "group-biz")]


def test_same_quote_exclusion_codes_are_merged_into_one():
    quote = "신용불량자 또는 휴업 중인 자"
    conditions = [
        condition("EXCLUDED_STATUS", quote, excludedCodes=["CREDIT_DELINQUENT"]),
        condition("EXCLUDED_STATUS", quote, excludedCodes=["BUSINESS_SUSPENDED"]),
    ]
    [merged] = frame_of(conditions, f"신청 제외 대상\n- {quote}\n")["common"]
    assert merged["anyOf"] == ["CREDIT_DELINQUENT", "BUSINESS_SUSPENDED"]


def test_list_only_age_is_handled_one_way_from_the_list_information():
    record = {"biz_trgt_age": "만 20세 이상 ~ 만 39세 이하"}
    line = "대상 연령: 만 20세 이상 ~ 만 39세 이하\n"
    meta_age = condition("AGE", "만 20세 이상 ~ 만 39세 이하", minAge=20)
    for conditions in ([meta_age], []):  # AI가 목록 칸으로 나이를 만들었든 안 만들었든 같은 결과
        [age] = frame_of(conditions, line, record=record)["common"]
        assert (age["minAge"], age["maxAge"], age["inReview"]) == (20, 39, True) and META_ONLY in age["reviewReason"]
        assert age["quote"] == line.strip()
    # 세 구간 모두(제한 없음)면 나이 조건 없음
    every = {"biz_trgt_age": "만 20세 미만, 만 20세 이상 ~ 만 39세 이하, 만 40세 이상"}
    assert frame_of([meta_age], "대상 연령: " + every["biz_trgt_age"] + "\n", record=every)["common"] == []
    # 본문 나이가 있으면 목록 정보로 나이를 더하지 않음
    body = "- 만 19세 이상 만 34세 이하인 자\n"
    [own] = frame_of([condition("AGE", "만 19세 이상 만 34세 이하인 자", minAge=19, maxAge=34)], line + body, record=record)["common"]
    assert (own["minAge"], own["maxAge"]) == (19, 34)


def test_youth_center_age_fields_make_one_held_age_and_no_limit_makes_none():
    lines = "지원 대상 최소 연령: 15\n지원 대상 최대 연령: 39\n"
    record = {"sprtTrgtMinAge": "15", "sprtTrgtMaxAge": "39", "sprtTrgtAgeLmtYn": "Y"}
    ai_ages = [condition("AGE", "지원 대상 최소 연령: 15", minAge=15), condition("AGE", "지원 대상 최대 연령: 39", maxAge=39)]
    [age] = frame_of(ai_ages, lines + "- 15일 이내 사업자 등록\n", record=record)["common"]
    assert (age["minAge"], age["maxAge"], age["inReview"]) == (15, 39, True) and META_ONLY in age["reviewReason"]
    assert age["quote"] == lines.strip()  # 최소·최대 두 줄 그대로
    # 제한 여부가 「제한 없음」(N)인데 나이 값이 있으면 버리지 않고 확인 필요 나이로(사용자 결정 2026-10-23, 4차)
    [loose] = frame_of(ai_ages, lines, record=record | {"sprtTrgtAgeLmtYn": "N"})["common"]
    assert (loose["minAge"], loose["maxAge"], loose["inReview"]) == (15, 39, True) and AGE_FLAG_CONFLICT in loose["reviewReason"]


def test_labels_are_cut_outside_brackets():
    assert _short("정보통신(IT) 또는 바이오(BT) 관련 기업인가요?", 10) == "정보통신(IT)…"
    assert _short("정보통신(IT) 또는 바이오(BT) 관련 기업인가요?", 7) == "정보통신…"
    assert _short("짧은 이름", 10) == "짧은 이름"
    paths = [
        condition(
            "OTHER", "가나다라마바사 정보통신(IT) 관련 기업", question="가나다라마바사 정보통신(IT, ICT) 관련 기업인가요?", metWhen="YES", anyOf="a", option="1"
        ),
        condition("REGISTERED", "창업 7년 이내의 법인사업자 또는 개인사업자", anyOf="a", option="2"),
    ]
    [either] = frame_of(paths, "- 가나다라마바사 정보통신(IT) 관련 기업\n")["common"]
    label = either["options"][0]["label"]
    assert label.count("(") == label.count(")")


def test_list_on_the_next_bracket_line_counts_for_questions_and_examples():
    text = "신청 제외 대상: ￭ 가상법 시행령 제4조에서 정하는 지원 제외 업종\n(숙박업, 주점업, 부동산업 등)\n"
    law = condition("OTHER", "￭ 가상법 시행령 제4조에서 정하는 지원 제외 업종", question="지원 제외 업종에 해당하나요?", metWhen="NO")
    [asked] = frame_of([law], text)["common"]
    assert not asked["inReview"] and asked["question"].endswith("(원문 목록: 숙박업, 주점업, 부동산업 등)")
    # 글머리표(「·」)는 예시 목록이 아님: 법령만 있으면 확인 필요
    bare = condition("OTHER", "· 가상법 시행령 제4조의 지원에서 제외되는 업종 불가", question="제외 업종인가요?", metWhen="NO")
    held = frame_of([bare], "신청자격 제한\n· 가상법 시행령 제4조의 지원에서 제외되는 업종 불가\n")["common"][0]
    assert held["inReview"] and LAW_SCOPE in held["reviewReason"]


def test_income_criteria_written_only_as_a_note_become_a_held_question():
    quote = "소득·자산 기준 2025년 기준 적용(금액 변동 가능)"
    note = {"kind": "OTHER", "group": None, "text": "소득·자산 기준은 2025년 기준을 적용합니다.", "quote": quote}
    made = frame_of([], f"- {quote}\n", notes=[note])
    [asked] = made["common"]
    assert asked["question"] == "공고에 적힌 소득·자산 기준을 충족하나요?" and asked["inReview"] and asked["quote"] == quote
    assert [n["text"] for n in made["notes"]] == [note["text"]]  # 안내는 그대로
    # 기준이 없다는 안내, 이미 소득 조건이 있으면 더하지 않음
    none = note | {"text": "소득 기준 없음", "quote": "소득 기준 없음"}
    assert frame_of([], "- 소득 기준 없음\n", notes=[none])["common"] == []
    income = condition("OTHER", quote, question="소득·자산 기준을 충족하나요?", metWhen="YES")
    assert len(frame_of([income], f"- {quote}\n", notes=[note])["common"]) == 1


def test_law_given_only_as_the_reason_does_not_hold_a_concrete_question():
    quote = "가상건축법 시행령 제3조에 따른 시설이 아니므로 공장 등록이 필요한 업종은 입주 불가"
    concrete = condition("OTHER", quote, question="공장 등록이 필요한 업종인가요?", metWhen="NO")
    assert not frame_of([concrete], f"- {quote}\n")["common"][0]["inReview"]
    vague = condition("OTHER", quote, question="가상건축법 시행령 제3조에 따른 시설이 아닌 업종인가요?", metWhen="NO")
    assert LAW_SCOPE in frame_of([vague], f"- {quote}\n")["common"][0]["reviewReason"]


def test_group_name_used_as_part_of_another_name_does_not_pin_the_exclusion_to_that_group():
    text = "사업자 등록 전인 개인\n창업 5년 이내 기업\n신청 제외 대상\n- 다른 기창업자 지원센터에 2년간 입주한 이력이 있는 기업\n"
    pre = condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")
    stay = condition("OTHER", "다른 기창업자 지원센터에 2년간 입주한 이력이 있는 기업", group="biz", question="다른 지원센터에 2년간 입주했나요?", metWhen="NO")
    made = frame_of([pre, stay], text, groups=GROUPS)
    assert [c["question"] for c in made["common"]] == ["다른 지원센터에 2년간 입주했나요?"]
    assert [(c["question"], c["inReview"]) for c in made["groups"][1]["criteria"]] == [("기창업자에 해당하나요?", True)]  # 비게 된 대상군(4차)
