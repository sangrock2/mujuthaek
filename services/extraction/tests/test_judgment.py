"""판정 틀(housing-judgment.v1) 가공: 판정 담당이 준 틀 그대로, 코드만으로. AI 호출 없음."""

import copy

from test_publish import EVENT_SCHEMA, envelope, verified

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.judgment import build_judgment
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.publish import completed_payload

URBAN = {
    "householdMemberCount": None,
    "householdScope": "해당 세대(세대구성원 전원)",
    "referenceVersion": "전년도",
    "referenceYear": 2025,
    "standardName": "도시근로자 가구원수별 가구당 월평균소득",
}


def atom(attribute, operator, value, subject="HOUSEHOLD", benchmark=None, unit="PERCENT"):
    return {
        "kind": "ATOMIC",
        "subject": subject,
        "attribute": attribute,
        "operator": operator,
        "value": value,
        "unit": unit,
        "basis": None,
        "referenceTime": "입주자모집공고일",
        "evidenceIds": ["ev-1"],
        "benchmark": benchmark,
    }


def item(item_id, category, text, expression=None, groups=(), exceptions=(), description=None):
    return {
        "id": item_id,
        "category": category,
        "appliesTo": None,
        "description": description or text,
        "originalText": text,
        "referenceTime": "입주자모집공고일",
        "rule": {"expression": expression, "status": "STRUCTURED" if expression else "UNSTRUCTURED", "reason": None},
        "scope": {"targetGroups": list(groups)},
        "exceptions": list(exceptions),
        "exceptionsStatus": "PRESENT" if exceptions else "NONE_IN_SOURCE",
        "evidenceIds": ["ev-1"],
    }


def candidate(eligibility, target_groups=(), held=()):
    return {
        "input": {"rawPostId": "00000000-0000-7000-8000-000000000002", "rawVersion": 3, "field": "HOUSING"},
        "notice": {"targetGroups": list(target_groups), "announcedOn": "2026-10-07"},
        "schedules": [],
        "eligibility": eligibility,
        "selectionRules": [],
        "guidance": [],
        "evidence": [{"id": "ev-1", "quote": "1인가구는 20%p, 2인가구는 10%p 가산 적용한 금액임"}],
        "quality": {"reviewIssues": [], "heldItems": list(held)},
    }


def replace_income(exception_id, size, percent):
    return {
        "id": exception_id,
        "originalText": "1인가구는 20%p, 2인가구는 10%p 가산 적용한 금액임",
        "description": f"{size}인가구는 소득 기준 비율을 {percent}%로 바꿔 적용해요.",
        "when": {"expression": atom("HOUSEHOLD_MEMBER_COUNT", "EQ", size, unit="COUNT"), "status": "STRUCTURED", "reason": None},
        "effect": "REPLACE",
        "effectExpression": atom("INCOME_BENCHMARK_PERCENT", "LTE", percent, benchmark={**URBAN, "householdMemberCount": size}),
        "evidenceIds": ["ev-1"],
    }


def criteria(frame):
    out = []

    def walk(items):
        for c in items:
            out.append(c)
            for option in c.get("options") or []:
                walk(option["criteria"])

    walk(frame["common"])
    for group in frame["groups"]:
        walk(group["criteria"])
    return out


def test_completed_event_carries_the_frame_as_given_and_matches_both_contracts():
    payload = completed_payload(verified(), provider="가상주거공사")
    frame = payload["judgment"]
    assert tools().validate(envelope(payload), EVENT_SCHEMA) == [] and frame_errors(frame) == []
    assert (frame["schema"], frame["rawPostId"], frame["rawVersion"]) == ("housing-judgment.v1", payload["rawPostId"], payload["rawVersion"])
    ages = [c for c in criteria(frame) if c["kind"] == "AGE"]
    assert [(c["minAge"], c["maxAge"]) for c in ages] == [(19, 39)]  # 「19세 이상」「39세 이하」 원자 조건 둘 → 하나


def test_household_size_income_exceptions_become_bonuses():
    # 실측 LH 강원: 70% 이하 + 예외 「1인가구 90%」「2인가구 80%」 → 가산 1인 +20%p, 2인 +10%p (틀 예시 서리풀과 같은 모양)
    income = item(
        "income-70",
        "INCOME",
        "해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 70% 이하인 자",
        atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN),
        exceptions=[replace_income("ex-1", 1, 90), replace_income("ex-2", 2, 80)],
    )
    frame = build_judgment(candidate([income]))
    [made] = frame["common"]
    assert made["kind"] == "INCOME" and not made["inReview"]
    assert (made["basis"], made["standard"], made["year"], made["percent"]) == ("HOUSEHOLD", "URBAN_WORKER_INCOME", 2025, 70)
    assert [(b["when"]["factor"], b["when"]["min"], b["addPercent"]) for b in made["bonuses"]] == [("HOUSEHOLD_SIZE", 1, 20), ("HOUSEHOLD_SIZE", 2, 10)]


def test_income_without_readable_bonus_is_in_review_when_the_notice_mentions_one():
    # 가산을 빼고 보내면 1·2인 가구가 실제와 달리 불충족이 됩니다
    income = item(
        "income-70",
        "INCOME",
        "월평균소득 70% 이하인 자",
        atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN),
        description="70% 이하여야 해요. 맞벌이는 가산해요.",
    )
    [made] = build_judgment(candidate([income]))["common"]
    assert made["inReview"] and "가산" in made["reviewReason"]


def test_waived_minor_becomes_any_of_with_the_exception_as_question():
    exception = {
        "id": "age-ex-child",
        "originalText": "자녀가 있는 미성년 세대주(단, 동일한 세대별 주민등록표등본에 자녀가 등재되어야 함)",
        "description": "자녀가 있는 미성년 세대주는 신청할 수 있어요.",
        "when": {"expression": None, "status": "UNSTRUCTURED", "reason": "표현할 수 없음"},
        "effect": "WAIVE",
        "effectExpression": None,
        "evidenceIds": ["ev-1"],
    }
    age = item(
        "age",
        "AGE",
        "「민법」상 미성년자(19세 미만)는 공급 신청할 수 없습니다.",
        atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEAR"),
        exceptions=[exception],
    )
    [made] = build_judgment(candidate([age]))["common"]
    assert made["kind"] == "ANY_OF" and not made["inReview"]
    base, waived = made["options"]
    assert base["criteria"][0]["minAge"] == 19
    assert waived["criteria"][0]["kind"] == "ASK" and waived["criteria"][0]["metWhen"] == "YES"


def test_rank_items_become_their_own_groups_and_an_umbrella_group_is_asked():
    # 실측 LH 강원: 공고 대상 「저소득계층」, 자격 항목은 「1순위 일반 장애인」(70%)·「2순위」(100%). 예전엔 둘 다 공통 조건이 되어 함께 요구됨
    seventy = item("income-70", "INCOME", "70% 이하인 자", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN), groups=["1순위 일반 장애인"])
    hundred = item("income-100", "INCOME", "100% 이하인 자", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN), groups=["2순위"])
    frame = build_judgment(candidate([seventy, hundred], target_groups=["저소득계층"]))
    assert frame["common"] == []
    by_name = {g["name"]: g["criteria"] for g in frame["groups"]}
    # 신분은 닫힌 목록 밖이라 대상 해당 여부를 묻습니다(2026-10-21)
    member, income = by_name["1순위 일반 장애인"]
    assert (member["kind"], member["question"]) == ("ASK", "「1순위 일반 장애인」 대상에 해당하나요?")
    assert (income["kind"], income["percent"]) == ("INCOME", 70)
    assert [(c["kind"], c.get("percent")) for c in by_name["2순위"]] == [("INCOME", 100)]
    [umbrella] = by_name["저소득계층"]
    assert umbrella["kind"] == "ASK" and umbrella["inReview"]
    # 대상군의 신청 순위(판정 틀 rank, 2026-10-22): 순위가 없는 상위 묶음은 null
    assert {g["name"]: g["rank"] for g in frame["groups"]} == {"저소득계층": None, "1순위 일반 장애인": 1, "2순위": 2}


def test_income_tier_groups_fold_into_each_target_group_instead_of_standing_alone():
    # 실측 2026-10-29 구로구 도전숙: 나이·거주는 「청년창업인」에, 소득·자산은 「월평균소득 50% 이하 …」 구간 대상군에만 있어
    # 부산 거주 66세 세대원도 소득만 맞으면 공고 전체 「지원 가능」. 구간은 대상이 아니라 대상이 갖출 소득 기준 중 하나예요
    youth = "청년창업인"
    low = "월평균소득 50% 이하 및 자산·자동차 기준 충족"
    mid = "월평균소득 50% 초과 ~100% 이하"
    items = [
        item("age", "AGE", "만 19세 이상 39세 이하", atom("AGE_YEARS", "BETWEEN", [19, 39], subject="APPLICANT", unit="YEARS"), groups=[youth]),
        item("income-50", "INCOME", "월평균소득 50% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 50, benchmark=URBAN), groups=[low]),
        item("assets", "ASSETS", "총자산 2억4천5백만원 이하", atom("TOTAL_ASSETS_KRW", "LTE", 245_000_000, unit="KRW"), groups=[low]),
        item("car", "CAR_ASSETS", "자동차 4,542만원 이하", atom("CAR_ASSETS_KRW", "LTE", 45_420_000, unit="KRW"), groups=[low]),
        item("income-100", "INCOME", "월평균소득 50% 초과 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN), groups=[mid]),
    ]
    frame = build_judgment(candidate(items, target_groups=[youth]))

    assert [g["name"] for g in frame["groups"]] == [youth]  # 구간 대상군은 없어지고
    [group] = frame["groups"]
    age, tiers = group["criteria"]
    assert age["kind"] == "AGE"
    assert tiers["kind"] == "ANY_OF"  # 대상마다 「구간 중 하나」로 붙어요
    assert [(o["label"], [c["kind"] for c in o["criteria"]]) for o in tiers["options"]] == [
        (low, ["INCOME", "ASSET", "CAR"]),
        (mid, ["INCOME"]),
    ]
    ids = [c["id"] for c in criteria(frame)]
    assert len(ids) == len(set(ids))
    assert frame_errors(frame) == []


def test_single_income_tier_becomes_a_plain_condition_of_each_target():
    youth = item("age", "AGE", "만 19~39세", atom("AGE_YEARS", "BETWEEN", [19, 39], subject="APPLICANT", unit="YEARS"), groups=["청년"])
    newly = item("married", "MARRIAGE", "혼인 7년 이내", groups=["신혼부부"])
    income = item("income", "INCOME", "소득 70% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN), groups=["소득 70% 이하"])
    frame = build_judgment(candidate([youth, newly, income], target_groups=["청년", "신혼부부"]))

    by_name = {g["name"]: [c["kind"] for c in g["criteria"]] for g in frame["groups"]}
    assert set(by_name) == {"청년", "신혼부부"}
    assert by_name["청년"][-1] == "INCOME" and by_name["신혼부부"][-1] == "INCOME"
    assert frame_errors(frame) == []


def test_group_rank_comes_only_from_one_clear_rank_in_the_name():
    from mujuthaek_extraction.judgment.frame import rank_of

    assert rank_of("1순위") == 1
    assert rank_of("일반공급 제2순위 장애인") == 2
    assert rank_of("1순위 우선 수급자 (그 밖의 주택형·단지)") == 1
    assert rank_of("신혼부부") is None
    assert rank_of("1·2순위") is None  # 여러 순위를 묶은 대상군
    assert rank_of("1~3순위 공통") is None
    assert rank_of("1순위 및 2순위") is None


def test_sentences_that_are_not_requirements_become_notes():
    # 실측 LH 대전대동2 「거주지역」(따지지 않아요), 인천 정의 문장, 순위 문장
    items = [
        item("res", "RESIDENCE", "거주지역", description="거주지역은 따지지 않아요."),
        item("def", "HOUSEHOLD", "다음의 세대구성원에 해당하는 사람 전원이 주택을 소유하고 있지 않는 세대의 구성원을 말합니다."),
        item("rank", "RESIDENCE", "1순위 | 인천광역시 거주자 / 2순위 | 그 밖의 지역"),
        item("dup", "OTHER", "1세대 1주택 신청하여야 하며, 중복 신청하는 경우 전부 무효 처리합니다"),
    ]
    frame = build_judgment(candidate(items))
    assert frame["common"] == [] and [n["kind"] for n in frame["notes"]] == ["OTHER", "OTHER", "SELECTION", "RULE"]


def test_limit_sentence_is_a_question_answered_no():
    limit = item("foreign", "NATIONALITY", "외국인의 경우 본 아파트 청약신청이 불가합니다.")
    [made] = build_judgment(candidate([limit]))["common"]
    assert (made["kind"], made["metWhen"], made["inReview"]) == ("ASK", "NO", False)


def test_benefit_list_definition_is_asked_as_written_in_housing():
    text = "「국민기초생활보장법」 제7조제1항제1호~제7조제1항제4호에 따른 생계·주거· 의료·교육급여 수급자"
    frame = build_judgment(candidate([item("recipient", "OTHER", text, groups=["수급자"])], target_groups=["수급자"]))
    [made] = {g["name"]: g for g in frame["groups"]}["수급자"]["criteria"]
    # 주거 틀은 신분을 코드로 판정하지 않고 원문 그대로 묻습니다(닫힌 목록, 2026-10-21). 급여 종류가 다 적혀 있어 확인 필요는 아님
    assert made["kind"] == "ASK" and text in made["question"] and not made["inReview"]


def test_held_eligibility_is_sent_in_review_not_dropped():
    held = [{"target": "/eligibility", "extent": "SECTION", "codes": ["CRITERION_NOT_STRUCTURED"], "description": "확인 전까지 보류"}]
    age = item("age", "AGE", "만 19세 이상", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEAR"))
    [made] = build_judgment(candidate([age], held=held))["common"]
    assert made["kind"] == "AGE" and made["inReview"] and "CRITERION_NOT_STRUCTURED" in made["reviewReason"]


def test_no_reference_date_or_other_field_gives_no_frame():
    undated = candidate([])
    undated["notice"]["announcedOn"] = None
    assert build_judgment(undated) is None
    policy = candidate([])
    policy["input"]["field"] = "POLICY"
    assert build_judgment(policy) is None


def test_contract_rejects_a_frame_of_another_notice_or_with_duplicate_ids():
    payload = completed_payload(verified(), provider="가상주거공사")
    other = copy.deepcopy(payload)
    other["judgment"]["rawVersion"] += 1
    assert "EVENT_JUDGMENT_IDENTITY_CONFLICT /payload/judgment" in tools().judgment_errors(other)
    duplicated = copy.deepcopy(payload)
    duplicated["judgment"]["common"].append(copy.deepcopy(duplicated["judgment"]["common"][0]))
    assert "JUDGMENT_DUPLICATE_ID /payload/judgment" in tools().judgment_errors(duplicated)


def business(eligibility, target_groups=(), selection=()):
    made = candidate(eligibility, target_groups)
    made["input"]["field"] = "BUSINESS_SPACE"
    made["selectionRules"] = list(selection)
    return made


def test_business_space_frame_follows_its_own_schema_with_statuses_regions_and_limits():
    # 실측 틀 예시(LH 양산사송 희망상가)의 모양: 대상군 이름이 유형, 주소지 또는 사업장 지역, 신청 제한 사유
    either = {
        "kind": "ANY",
        "children": [
            atom("RESIDENCE_REGION_CODE", "EQ", "4133000000", "APPLICANT", unit="CODE"),
            atom("BUSINESS_REGION_CODE", "EQ", "4133000000", "BUSINESS", unit="CODE"),
        ],
    }
    items = [
        item("region", "BUSINESS_REGION", "주소지 또는 사업장 소재지가 양산시인 자", either),
        item("limits", "OTHER", "피성년후견인 또는 피한정후견인, 국세·지방세 체납자는 신청할 수 없습니다."),
        item("social", "OTHER", "「사회적기업법」에 따라 사회적기업 인증을 받은 자ㆍ예비사회적기업으로 지정된 자", groups=["사회적기업"]),
    ]
    frame = build_judgment(business(items, target_groups=["소상공인", "사회적기업"]))
    assert frame["schema"] == "business-space-judgment.v1" and frame_errors(frame) == [] and frame["preferences"] == []
    region, limits = frame["common"]
    assert (region["kind"], region["basis"], region["regionCodes"]) == ("REGION", "RESIDENCE_OR_BUSINESS_SITE", ["4133000000"])
    assert (limits["kind"], limits["anyOf"], limits["inReview"]) == ("EXCLUDED_STATUS", ["ADULT_WARD", "TAX_ARREARS"], False)
    by_name = {g["name"]: g["criteria"] for g in frame["groups"]}
    assert [(c["kind"], c["anyOf"]) for c in by_name["소상공인"]] == [("STATUS", ["SMALL_BUSINESS"])]
    assert [(c["kind"], c["anyOf"]) for c in by_name["사회적기업"]] == [("STATUS", ["PRE_SOCIAL_ENTERPRISE", "SOCIAL_ENTERPRISE"])]


def test_business_space_scoring_rule_becomes_a_bonus_preference_and_industry_limit_is_kept():
    scoring = {
        "id": "local-bonus",
        "kind": "SCORING",
        "points": 5,
        "maxPoints": None,
        "description": "업체 소재지가 성동구인 경우 5점",
        "originalText": "업체 소재지가 성동구인 경우 5점",
        "rule": {"expression": atom("BUSINESS_REGION_CODE", "EQ", "1120000000", "BUSINESS", unit="CODE"), "status": "STRUCTURED", "reason": None},
        "scope": {"targetGroups": []},
    }
    industry = atom("INDUSTRY_CODE", "NOT_IN", ["56", "64"], "BUSINESS", benchmark={"standardName": "한국표준산업분류 11차"}, unit="CODE")
    frame = build_judgment(business([item("industry", "INDUSTRY", "음식점업·금융업은 입점할 수 없습니다", industry)], selection=[scoring]))
    assert frame_errors(frame) == []
    [limit] = frame["common"]
    assert (limit["mode"], limit["revision"], limit["codes"]) == ("EXCLUDE", 11, ["56", "64"])
    [preference] = frame["preferences"]
    assert (preference["effect"], preference["points"], preference["criteria"][0]["basis"]) == ("BONUS_POINTS", 5, "BUSINESS_SITE")


def test_term_definitions_bonus_notes_and_rules_are_not_asked_as_requirements():
    # 실측 2026-10-21 광주선운2·든든전세·김해 매각: 정의·가산 안내·신청 규칙·입주 후 의무가 「자격을 갖추었나요?」 질문으로 나감
    income = item("income", "INCOME", "월평균소득 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN))
    items = [
        item("def", "HOUSEHOLD", "※ 무주택세대구성원 : 아래 표의 세대구성원 전원이 주택을 소유하고 있지 않은 세대의 구성원"),
        item("bonus", "OTHER", "* 가산 적용 : 출산자녀 2인 이상 20% 가산, 출산자녀 1인 10% 가산"),
        item("dup", "OTHER", "A-1블록, A-3블록 중 반드시 한 개 블록만 지정하여 신청하셔야 하며, 두 개 블록에 중복으로 신청하는 경우 모두 무효"),
        item("keep", "OTHER", "신청자격은 입주자 모집공고일부터 입주 시까지 계속 유지하고 있어야 합니다."),
        income,
    ]
    frame = build_judgment(candidate(items))
    assert [n["kind"] for n in frame["notes"]] == ["OTHER", "OTHER", "RULE", "OBLIGATION"]
    [made] = frame["common"]
    assert made["kind"] == "INCOME" and made["inReview"] and "가산" in made["reviewReason"]  # 가산 안내를 못 옮겨 소득은 확인 필요


def test_group_requirement_written_as_a_term_definition_stays_a_question():
    # 「사회초년생 : …」은 사회초년생 대상의 실제 요건이라 안내로 넘기면 그 대상이 요건 없이 지원 가능이 됨
    text = "사회초년생 : 소득이 있는 업무에 종사한 기간이 총 5년 이내인 사람"
    frame = build_judgment(candidate([item("rookie", "OTHER", text, groups=["사회초년생"])], target_groups=["사회초년생"]))
    [made] = {g["name"]: g for g in frame["groups"]}["사회초년생"]["criteria"]
    assert made["kind"] == "ASK" and made["metWhen"] == "YES"


def test_cannot_apply_or_be_selected_sentences_are_limits():
    text = "재당첨 제한 기간 중에 있는 분은 청약할 수 없습니다."
    [made] = build_judgment(candidate([item("rewin", "OTHER", text)]))["common"]
    assert (made["kind"], made["metWhen"], made["inReview"]) == ("ASK", "NO", False)


def test_question_direction_is_decided_only_for_clear_qualification_endings():
    # 2026-10-22 방향 미정 959건 분류: 대상 명사(끝 괄호 부연은 빼고)·「갖추어야 합니다」로 끝나면 자격, 그 밖에는 그대로 확인 필요
    clear = [
        "매각공고일(2026.09.30.) 기준 국내에 거주하는 만19세 이상 성년자인 무주택세대구성원(주민등록표등본 기준)",
        "신청일로부터 최근 2년이내 출산한 자녀(태아, 2년이내 출생한 입양자를 포함)가 있는 가구",
        "신청자는 무주택세대구성원, 소득·자산기준을 충족하고, 다음의 입주자격 구분별 신청자격을 갖추어야합니다.",
    ]
    for text in clear:
        [made] = build_judgment(candidate([item("who", "OTHER", text)]))["common"]
        assert (made["metWhen"], made["inReview"]) == ("YES", False), text
    unclear = [
        "세대구성원(자격검증대상)",  # 머리글
        "또한 배우자가 국내 거주하지 않는 재외국민이거나 외국인 등록을 하지 않은 외국인인 경우(국내거소신고를 하지 않은 외국국적동포 포함)",
        "본 공고에 따라 신청하여 서류제출까지 완료한 경우, 예비입주자 순번 발표 시까지",
    ]
    for text in unclear:
        [made] = build_judgment(candidate([item("who", "OTHER", text)]))["common"]
        assert made["inReview"] and "자격인지 신청 제한인지" in made["reviewReason"], text


def test_duties_after_selection_and_household_scope_are_notes_and_disqualifications_are_limits():
    duties = [
        "현재 임대주택에 거주하고 있는 자는 이 주택에 입주하기 전에 기존 임대주택을 명도하여야 합니다.",
        "기 대출받은 주택도시기금이 있을 경우에는 전세임대주택 입주 전까지 상환하여야 함",
        "선정되면 종전에 동일한 공급유형에 선정된 예비입주자 지위는 자동 상실됩니다.",
        "신청자격은 공고일부터 입주 시까지 유지하여야 합니다.",
        "입주 전에 세대 분리를 해야 합니다.",
    ]
    scope = [
        "신청자 및 배우자 신청자와 세대 분리되어 있는 배우자도 세대구성원에 포함",
        "단, 아래에 해당하는 사람은 자격검증대상(세대구성원)에 포함합니다.",
        "제2호 나목(국군귀환포로)의 경우 관련 신분 증빙자료 제출하면 소득자산 검증이 생략됩니다.",
    ]
    frame = build_judgment(candidate([item(f"t{i}", "OTHER", t) for i, t in enumerate([*duties, *scope])]))
    assert frame["common"] == []
    assert [n["kind"] for n in frame["notes"]] == ["OBLIGATION"] * len(duties) + ["OTHER"] * len(scope)
    for text in ["※ 주거약자 아닌 자가 주거약자용을 신청할 경우 탈락처리 됨", "다만, 세대 구성원 중 유주택자인 부모님이 포함될 경우 부적격자로 처리됩니다."]:
        [made] = build_judgment(candidate([item("no", "OTHER", text)]))["common"]
        assert (made["kind"], made["metWhen"], made["inReview"]) == ("ASK", "NO", False), text


def test_dual_income_option_equal_to_the_base_bonuses_is_not_a_separate_option():
    # 2026-10-22 실측: 「맞벌이 2인 가구 130%」가 기본 100% + 맞벌이 20%p + 2인 10%p와 같은데 선택지로 또 들어감
    def replace(ex_id, text, value):
        return {
            "id": ex_id,
            "originalText": text,
            "description": text,
            "when": {"expression": None, "status": "UNSTRUCTURED", "reason": "맞벌이 여부는 속성 사전에 없습니다."},
            "effect": "REPLACE",
            "effectExpression": atom("INCOME_BENCHMARK_PERCENT", "LTE", value, benchmark=URBAN),
            "evidenceIds": ["ev-1"],
        }

    text = "월평균소득 100% 이하(맞벌이 120%, 2인 110%)"
    base = atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN)
    same = replace("ex-dual", "맞벌이 2인 가구는 130% 이하", 130)
    [made] = build_judgment(candidate([item("income", "INCOME", text, base, exceptions=[same])]))["common"]
    assert made["kind"] == "INCOME" and made["percent"] == 100
    child = replace("ex-child", "자녀가 있는 맞벌이 가구는 140% 이하", 140)
    [made] = build_judgment(candidate([item("income", "INCOME", text, base, exceptions=[same, child])]))["common"]
    assert made["kind"] == "ANY_OF" and [o["label"] for o in made["options"]] == ["기본 기준", "자녀가 있는 맞벌이 가구는 140% 이하"]


def test_income_below_percent_keeps_source_value_and_review():
    """「100% 미만」을 「99% 이하」로 바꾸면 99.5%가 떨어집니다. 원문 값과 확인 필요로 둡니다."""
    income = item("e1", "INCOME", "월평균소득 100% 미만", atom("INCOME_BENCHMARK_PERCENT", "LT", 100, benchmark=URBAN))
    frame = build_judgment(candidate([income]))
    made = frame["common"][0]
    assert made["kind"] == "INCOME" and made["percent"] == 100 and made["inReview"] and "미만" in made["reviewReason"]
    assert frame_errors(frame) == []


def test_supply_group_condition_becomes_its_own_group():
    """주택형 하나에만 붙은 조건은 판정 담당 문서대로 그 주택형 대상군으로 나눕니다(「대상군을 단지별로 나눠 주세요」)."""
    age = item("e1", "AGE", "만 19세 이상인 자", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEARS"))
    limited = item("e2", "INCOME", "전용 59㎡ 주택형은 소득 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN))
    limited["scope"] = {"level": "SUPPLY_GROUP", "supplyGroupIds": ["sg-59A"], "locationIds": [], "targetGroups": [], "description": "59A"}
    base = candidate([age, limited])
    base["supplyGroups"] = [{"id": "sg-59A", "housingTypeCode": "59A", "unitLabel": None}, {"id": "sg-84B", "housingTypeCode": "84B", "unitLabel": None}]
    frame = build_judgment(base)
    assert [c["kind"] for c in frame["common"]] == ["AGE"]  # 공통 조건에는 주택형 한정 조건이 없음
    groups = {g["name"]: [c["kind"] for c in g["criteria"]] for g in frame["groups"]}
    assert groups == {"그 밖의 주택형·단지": [], "59A": ["INCOME"]}
    assert frame_errors(frame) == []
    # 모든 주택형에 한정 조건이 있으면 「그 밖의」 대상군은 만들지 않습니다
    other = item("e3", "INCOME", "전용 84㎡ 주택형은 소득 120% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 120, benchmark=URBAN))
    other["scope"] = {**limited["scope"], "supplyGroupIds": ["sg-84B"], "description": "84B"}
    base["eligibility"].append(other)
    assert [g["name"] for g in build_judgment(base)["groups"]] == ["59A", "84B"]


def test_supply_group_condition_for_one_target_group_is_split_with_that_group():
    youth = item("e1", "AGE", "청년: 만 19~39세", atom("AGE_YEARS", "BETWEEN", [19, 39], subject="APPLICANT", unit="YEARS"), groups=["청년"])
    limited = item("e2", "INCOME", "청년 59A형은 소득 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN), groups=["청년"])
    limited["scope"] = {"level": "SUPPLY_GROUP", "supplyGroupIds": ["sg-59A"], "locationIds": [], "targetGroups": ["청년"], "description": "59A"}
    base = candidate([youth, limited], target_groups=["청년", "신혼부부"])
    base["supplyGroups"] = [{"id": "sg-59A", "housingTypeCode": "59A", "unitLabel": None}, {"id": "sg-84B", "housingTypeCode": "84B", "unitLabel": None}]
    frame = build_judgment(base)
    groups = {g["name"]: [c["kind"] for c in g["criteria"]] for g in frame["groups"]}
    assert groups["59A 청년"] == ["AGE", "INCOME"] and groups["청년 (그 밖의 주택형·단지)"] == ["AGE"]
    assert "59A 신혼부부" not in groups
    assert frame_errors(frame) == []


def test_not_required_sentence_with_other_requirement_stays_a_question():
    """「거주지역 불문, 만 19세 이상 39세 이하」를 안내로 넘기면 나이 요건이 사라집니다."""
    for text, description in (
        ("거주지역 불문, 만 19세 이상 39세 이하인 자", None),
        ("만 19세 이상 39세 이하인 자", "거주지역은 따지지 않고 만 19~39세면 돼요"),
    ):
        frame = build_judgment(candidate([item("e3", "AGE", text, description=description)]))
        assert [c["kind"] for c in frame["common"]] == ["ASK"] and frame["notes"] == []
    only = build_judgment(candidate([item("e4", "RESIDENCE", "거주지역 불문")]))
    assert only["common"] == [] and [n["kind"] for n in only["notes"]] == ["OTHER"]


def test_held_announcement_date_is_not_the_reference_date():
    """보류한 공고일(API와 다름 등)을 판정 기준일로 쓰면 소득 기준 연도까지 틀립니다. 쓸 날짜가 없으면 틀을 보내지 않습니다."""
    income = item("e1", "INCOME", "월평균소득 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 100, benchmark=URBAN))
    held = candidate([income], held=[{"target": "/notice/announcedOn", "codes": ["API_MISMATCH"]}])
    assert build_judgment(held) is None
    issue = candidate([income])
    issue["quality"]["reviewIssues"] = [{"code": "VALUE_NOT_IN_QUOTE", "target": "/notice/announcedOn", "description": "x"}]
    assert build_judgment(issue) is None
    assert build_judgment(candidate([income]))["referenceDate"] == "2026-10-07"


def test_held_notice_target_groups_are_not_used_as_groups():
    age = item("e1", "AGE", "만 19세 이상", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEARS"))
    frame = build_judgment(candidate([age], target_groups=["청년"], held=[{"target": "/notice/targetGroups", "codes": ["X"]}]))
    assert [g["name"] for g in frame["groups"]] == ["전체"]


def test_approved_frame_drops_extraction_review_reasons_but_keeps_its_own():
    """승인한 결과는 조건의 inReview를 내리는 것과 같게, 추출 검수 사유로는 확인 필요를 붙이지 않습니다."""
    age = item("e1", "AGE", "만 19세 이상인 자", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEARS"))
    base = candidate([age])
    base["quality"]["reviewIssues"] = [{"code": "VALUE_NOT_IN_QUOTE", "target": "/eligibility/0/rule", "description": "x"}]
    assert build_judgment(base)["common"][0]["inReview"]
    approved = build_judgment(base, approved=True)["common"][0]
    assert approved["kind"] == "AGE" and not approved["inReview"]
    # 틀 자체의 사유(코드로 정하지 못함)는 승인해도 남습니다
    vague = candidate([item("e2", "OTHER", "그 밖에 공사가 정하는 요건")])
    assert build_judgment(vague, approved=True)["common"][0]["inReview"]


def test_page_numbers_come_from_pdf_page_marks():
    """판정 틀의 page: 근거 위치 앞의 가장 가까운 「--- N쪽 ---」 표시. 첨부 경계를 넘거나 쪽 표시가 없으면 비웁니다."""
    from mujuthaek_extraction.judgment.pages import evidence_pages

    text = "머리말\n--- 1쪽 ---\n공고 개요\n--- 2쪽 왼쪽 ---\n만 19세 이상인 자\n=== 첨부 b.pdf ===\n표지\n--- 1쪽 ---\n소득 기준"
    at = {name: text.index(name) for name in ("머리말", "공고 개요", "만 19세", "표지", "소득 기준")}
    located = {
        "evidence": [{"id": f"ev-{k}", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": v, "end": v + 2}} for k, v in at.items()]
        + [{"id": "ev-other", "sourceId": "text", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 2}}]
    }
    pages = evidence_pages(located, {"pdf-text": text, "text": "수집 글자"})
    assert pages == {"ev-공고 개요": 1, "ev-만 19세": 2, "ev-소득 기준": 1}

    age = item("e1", "AGE", "만 19세 이상인 자", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEARS"))
    frame = build_judgment(candidate([age]), pages={"ev-1": 2})
    assert frame["common"][0]["page"] == 2
    assert build_judgment(candidate([age]))["common"][0]["page"] is None


class _Regions:
    def lookup(self, name):
        class Found:
            code, level = ("1100000000", "SIDO") if "서울" in name else (None, None)

        return Found()


def test_group_name_with_other_targets_is_asked_not_narrowed_to_one_status():
    # 2026-10-21 리뷰: 「장애인 등 주거약자」를 장애인 신분만 요구함
    income = item("income", "INCOME", "70% 이하인 자", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN), groups=["장애인 등 주거약자"])
    plain = item(
        "income-2", "INCOME", "70% 이하인 자", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN), groups=["1순위 월평균소득 70% 이하 장애인"]
    )
    by_name = {g["name"]: g["criteria"] for g in build_judgment(candidate([income, plain]))["groups"]}
    first = by_name["장애인 등 주거약자"][0]
    assert first["kind"] == "ASK" and "장애인 등 주거약자" in first["question"]
    assert not any(c["kind"] == "STATUS" for c in by_name["장애인 등 주거약자"])
    assert by_name["1순위 월평균소득 70% 이하 장애인"][0]["question"] == "「1순위 월평균소득 70% 이하 장애인」 대상에 해당하나요?"


def test_child_count_with_an_age_limit_is_asked_whole():
    # 2026-10-21 리뷰·실측 10곳: 「미성년 자녀 2명 이상」이 나이 제한 없는 「자녀 2명 이상」이 됨
    minors = item("kids", "CHILDREN", "2명 이상의 미성년자인 자녀를 둔 사람", atom("CHILD_COUNT", "GTE", 2, unit="COUNT"))
    [made] = build_judgment(candidate([minors]))["common"]
    assert made["kind"] == "ASK" and made["inReview"] and "미성년자인 자녀" in made["question"]
    young = item("young", "CHILDREN", "6세 이하 자녀가 있는 혼인가구", atom("CHILD_COUNT", "GTE", 1, unit="COUNT"))
    # 자녀 조건은 닫힌 목록 밖이라 원문 질문입니다. 칸으로 정확히 담을 수 있는 「6세 이하 자녀가 있는」은 확인 필요가 아닙니다
    [kept] = build_judgment(candidate([young]))["common"]
    assert (kept["kind"], kept["inReview"]) == ("ASK", False) and "6세 이하 자녀" in kept["question"]


def test_youngest_child_age_attribute_is_a_child_question_not_a_review():
    # 2026-11-09 새 속성: 「6세 이하 자녀를 둔 한부모가족」의 자녀 나이를 담을 속성이 없어 조건식 없이 글로 남았음(정답표 자녀 나이 8개를 V1·V2 모두 놓침)
    young = item("young", "CHILDREN", "6세 이하 자녀(태아 포함)를 둔 한부모가족", atom("YOUNGEST_CHILD_AGE_YEARS", "LTE", 6, unit="YEAR"))
    [made] = build_judgment(candidate([young]))["common"]
    assert (made["kind"], made["inReview"]) == ("ASK", False) and "6세 이하 자녀" in made["question"]


def test_age_of_another_family_member_is_not_the_applicant_age():
    # 실측 2026-10-21: 「65세 이상 직계존속 부양자」가 신청자 65세 이상이 됨
    parent = item("parent", "AGE", "65세 이상 직계존속(배우자의 직계존속 포함)을 부양하는 자", atom("AGE_YEARS", "GTE", 65, subject="APPLICANT", unit="YEAR"))
    [made] = build_judgment(candidate([parent]))["common"]
    assert made["kind"] == "ASK" and made["inReview"]


def test_residence_sentence_with_other_conditions_is_asked_whole():
    # 2026-10-21 리뷰: 「서울 거주 만 19~39세 무주택자」를 거주지로만 체크함
    text = "서울특별시에 거주하는 만 19세 이상 39세 이하 무주택자"
    [made] = build_judgment(candidate([item("res", "RESIDENCE", text)]), _Regions())["common"]
    assert made["kind"] == "ASK" and made["inReview"] and text in made["question"]
    [simple] = build_judgment(candidate([item("res", "RESIDENCE", "서울특별시에 거주하는 사람")]), _Regions())["common"]
    assert simple["kind"] == "RESIDENCE" and simple["regionCodes"] == ["1100000000"]


def test_qualification_with_a_bracketed_limit_is_not_asked_as_a_limit():
    # 실측 2026-10-21 부산: 자격 문장을 「신청 제한에 해당하나요?」로 물어 자격을 갖춘 사람이 떨어지게 됨
    text = "부산광역시에 거주하는 무주택세대구성원인 성년자 [외국인 청약불가]"
    [made] = build_judgment(candidate([item("who", "RESIDENCE", text)]))["common"]
    assert made["kind"] == "ASK" and made["metWhen"] == "YES" and made["inReview"]


def test_list_items_in_one_group_are_in_review():
    # 실측 2026-10-21: 우선공급 ㉮·㉯ 항목이 「고령자」 대상의 필수 조건으로 모두 들어가 아무도 자격이 안 됨
    kids = item("a", "CHILDREN", "㉮ 자녀가 2명 이상인 사람", atom("CHILD_COUNT", "GTE", 2, unit="COUNT"), groups=["고령자"])
    merit = item("b", "OTHER", "㉯ 「국가유공자 등 예우 및 지원에 관한 법률」에 따른 국가유공자 또는 그 유족", groups=["고령자"])
    frame = build_judgment(candidate([kids, merit], target_groups=["고령자"]))
    made = {g["name"]: g["criteria"] for g in frame["groups"]}["고령자"]
    assert len(made) == 2 and all(c["inReview"] for c in made)


def test_one_household_bonus_does_not_clear_the_review_of_another():
    # 2026-10-21 리뷰: 1인 가산 하나만 받아도 「가산」 사유를 모두 지워 2인 가산 문제도 사라졌음
    text = "월평균소득 70% 이하. 가구원수가 1인인 경우 20%p, 2인인 경우 10%p 가산"
    one = item("income", "INCOME", text, atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN), exceptions=[replace_income("ex-1", 1, 90)])
    [made] = build_judgment(candidate([one]))["common"]
    assert made["inReview"]
    both = item(
        "income",
        "INCOME",
        text,
        atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN),
        exceptions=[replace_income("ex-1", 1, 90), replace_income("ex-2", 2, 80)],
    )
    [done] = build_judgment(candidate([both]))["common"]
    assert not done["inReview"] and "_bonusKeys" not in done


def test_generic_recipient_in_a_status_list_is_in_review():
    # 실측 2026-10-21: 「수급자가구 또는 차상위계층, 지원대상 한부모가족인 자」에서 급여 종류 없는 수급자가 빠지고 차상위·한부모만 요구함
    text = "수급자가구 또는 차상위계층, 지원대상 한부모가족인 자"
    frame = build_judgment(candidate([item("rank1", "OTHER", text, groups=["1순위 신생아가구"])], target_groups=["1순위 신생아가구"]))
    [made] = {g["name"]: g for g in frame["groups"]}["1순위 신생아가구"]["criteria"]
    assert made["kind"] == "ASK" and made["inReview"] and "수급자" in made["reviewReason"]


def test_only_main_conditions_are_judged_by_code_and_others_are_asked():
    # 닫힌 목록(2026-10-21): 나이·거주·무주택·소득·자산·자동차만 코드로 판정. 혼인·청약통장·자녀는 원문 질문
    married = item("married", "MARRIAGE", "혼인기간 7년 이내인 신혼부부", atom("MARRIAGE_MONTHS", "LTE", 84, unit="MONTH"))
    kids = item("kids", "CHILDREN", "자녀가 1명 이상인 자", atom("CHILD_COUNT", "GTE", 1, unit="COUNT"))
    age = item("age", "AGE", "만 19세 이상 39세 이하인 자", atom("AGE_YEARS", "BETWEEN", [19, 39], subject="APPLICANT", unit="YEAR"))
    made = build_judgment(candidate([married, kids, age]))["common"]
    assert [c["kind"] for c in made] == ["ASK", "ASK", "AGE"]
    assert made[0]["question"] == "다음 조건에 해당하나요? 「혼인기간 7년 이내인 신혼부부」" and not made[2]["inReview"]


def test_main_condition_is_confirmed_only_when_code_reads_the_same_value():
    # 두 방법 일치(2026-10-21): AI 값과 코드가 원문에서 읽은 값이 같을 때만 확정
    wrong = item("age", "AGE", "만 19세 이상 39세 이하인 자", atom("AGE_YEARS", "BETWEEN", [19, 45], subject="APPLICANT", unit="YEAR"))
    [made] = build_judgment(candidate([wrong]))["common"]
    assert made["kind"] == "AGE" and made["inReview"] and "다릅니다" in made["reviewReason"]
    car = item("car", "CAR_ASSETS", "총자산 3억 4,500만원 이하, 자동차 3,708만원 이하", atom("CAR_ASSETS_KRW", "LTE", 3_708_000, unit="KRW"))
    [made] = build_judgment(candidate([car]))["common"]
    assert made["kind"] == "CAR" and made["inReview"]  # 리뷰 사례: 3,708만원을 370만 8천원으로
    right = item("car", "CAR_ASSETS", "총자산 3억 4,500만원 이하, 자동차 3,708만원 이하", atom("CAR_ASSETS_KRW", "LTE", 37_080_000, unit="KRW"))
    assert not build_judgment(candidate([right]))["common"][0]["inReview"]
    two = item("income", "INCOME", "70% 이하 또는 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN))
    assert build_judgment(candidate([two]))["common"][0]["inReview"]  # 코드가 하나로 못 읽음


def test_approved_frame_does_not_need_the_code_reading():
    # 검수자가 원문과 대조해 승인한 값은 두 방법 일치 사유로 막지 않습니다
    two = item("income", "INCOME", "70% 이하 또는 100% 이하", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN))
    [made] = build_judgment(candidate([two]), approved=True)["common"]
    assert not made["inReview"]


def test_code_reading_handles_common_written_forms():
    from mujuthaek_extraction.judgment.readback import ages, amounts, percents

    assert ages("「민법」상 미성년자(만 19세 미만)는 신청하실 수 없습니다.") == (19, None)  # 금지 문장은 방향 반대
    assert ages("만 19세 이상 성년자와 법인(단, 외국인 신청불가)") == (19, None)  # 괄호 안 금지는 이 문장의 방향이 아님
    assert ages("65세 이상의 직계존속을 부양하는 만 19세 이상인 자") == (19, None)  # 가족의 나이는 뺌
    assert percents("월평균소득의 100% (【완화조건】120%(2순위),150%(3순위)) 이하") == {100.0}
    assert percents("70%(1인 90%, 2인 80%) 이하") == {70.0}
    assert amounts("총자산 3억 4,500만원 이하, 자동차 3,708만원 이하") == {"ASSET": {345_000_000}, "CAR": {37_080_000}, "ANY": set()}
    assert amounts("총 자산기준 2억4천5백만원 이하")["ASSET"] == {245_000_000}
    assert amounts("4,542만원 이하 일 것")["ANY"] == {45_420_000}


def test_household_bonus_must_match_its_own_size_in_the_exception_text():
    # 리뷰 2026-10-22: 원문 「1인 20%p, 2인 10%p」인데 2인 예외를 90%(+20)로 잘못 뽑아도 확정으로 나갔음
    income = item(
        "income-70",
        "INCOME",
        "해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 70% 이하인 자",
        atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN),
        exceptions=[replace_income("ex-1", 1, 90), replace_income("ex-2", 2, 90)],
    )
    [made] = build_judgment(candidate([income]))["common"]
    assert made["inReview"] and "같은 가구원 수·값으로 확인하지 못했습니다" in made["reviewReason"]


def test_qualification_with_an_excluded_group_is_asked_yes_and_unavoidable_is_not_a_limit():
    # 리뷰 2026-10-22: 「…를 제외하고는 무주택이어야」가 「신청 제한(아니오)」로, 「불가피한 사유」가 제한으로 나갔음
    [excepted] = build_judgment(candidate([item("x", "OTHER", "만 65세 이상인 경우를 제외하고는 무주택이어야 합니다")]))["common"]
    assert (excepted["metWhen"], excepted["inReview"]) == ("YES", True)
    [unavoidable] = build_judgment(candidate([item("x", "OTHER", "질병 등 불가피한 사유로 해외에 체류 중인 사람은 거주한 것으로 봅니다")]))["common"]
    assert unavoidable["metWhen"] == "YES"


def test_duty_wording_does_not_hide_a_current_requirement_or_a_limit():
    # 리뷰 2026-10-22: 「공고일 현재 … 거주하고 … 유지하여야」(거주 요건), 「입주 이후 … 신청 불가」(제한)가 안내로 빠졌음
    for text in [
        "공고일 현재 부산광역시에 거주하고 계약 시까지 거주를 유지하여야 합니다",
        "공공임대주택에 입주 이후 계약을 해지한 지 1년이 지나지 않은 자는 신청 불가",
    ]:
        frame = build_judgment(candidate([item("x", "OTHER", text)]))
        assert frame["notes"] == [] and len(frame["common"]) == 1, text
    duty = build_judgment(candidate([item("x", "OTHER", "현재 임대주택에 거주하고 있는 자는 이 주택에 입주하기 전에 기존 임대주택을 명도하여야 합니다.")]))
    assert [n["kind"] for n in duty["notes"]] == ["OBLIGATION"]


def test_income_readback_cannot_agree_when_the_text_has_a_lower_bound():
    from mujuthaek_extraction.judgment.readback import mismatch

    income = {"kind": "INCOME", "percent": 70, "quote": "기준중위소득 50% 초과 70% 이하인 가구"}
    assert mismatch(income) is not None  # 하한이 빠진 값을 「같다」고 확정하지 않음


def test_readback_does_not_agree_with_waived_homeless_or_excluded_regions():
    # 리뷰 2026-10-22: 「무주택자가 아니어도 신청 가능」을 무주택 요건과 같다고, 「(김해 거주자는 제외)」의 김해도 맞는 지역으로 봤음
    from mujuthaek_extraction.assemble.regions import RegionCodeTable
    from mujuthaek_extraction.judgment.readback import mismatch

    assert mismatch({"kind": "HOMELESS", "quote": "무주택자가 아니어도 신청 가능합니다"}) is not None
    assert mismatch({"kind": "HOMELESS", "quote": "무주택세대구성원일 것"}) is None
    regions = RegionCodeTable([("2600000000", "부산광역시", True), ("4800000000", "경상남도", True), ("4825000000", "경상남도 김해시", True)], "2026-10-01")
    quote = "부산광역시 거주자(경상남도 김해시 거주자는 제외)"
    assert mismatch({"kind": "RESIDENCE", "quote": quote, "regionCodes": ["4825000000"]}, regions) is not None
    assert mismatch({"kind": "RESIDENCE", "quote": quote, "regionCodes": ["2600000000"]}, regions) is None


def test_merged_duplicate_question_keeps_the_review_mark_and_rank_zero_is_not_a_rank():
    from mujuthaek_extraction.judgment.frame import rank_of

    text = "신청자는 무주택세대구성원, 소득·자산기준을 충족하고, 다음의 입주자격 구분별 신청자격을 갖추어야합니다."
    clean, held = item("a", "OTHER", text), item("b", "OTHER", text)
    frame = build_judgment(
        candidate([clean, held]) | {"quality": {"reviewIssues": [{"target": "/eligibility/1", "code": "EXCEPTION_SUSPECTED"}], "heldItems": []}}
    )
    [made] = frame["common"]
    assert made["inReview"]  # 둘 중 하나만 검수여도 합친 질문은 확인 필요
    assert rank_of("0순위 우선공급") is None and rank_of("1순위") == 1


def test_evidence_inside_the_image_reading_block_gets_no_pdf_page():
    # 리뷰 2026-10-22: 원문 끝 「=== 그림 판독 … ===」 묶음 안 근거가 앞 PDF의 마지막 쪽 번호를 받았음
    from mujuthaek_extraction.judgment.pages import evidence_pages

    text = "--- 7쪽 ---\n본문\n=== 그림 판독 공고문.pdf 3쪽 ===\n판독 글자"
    start = text.index("판독 글자")
    made = {"evidence": [{"id": "ev-1", "sourceId": "pdf", "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + 5}}]}
    assert evidence_pages(made, {"pdf": text}) == {}


def test_pdf_text_evidence_locator_carries_the_pdf_page():
    # 요구 2-07: 공고 상세 API가 근거 쪽수를 보이도록 PDF 글자 원문 근거의 글자 범위에 쪽 번호를 함께 싣습니다
    from mujuthaek_extraction.judgment.pages import attach_locator_pages, evidence_pages

    text = "--- 1쪽 ---\n공고 개요\n--- 2쪽 오른쪽 ---\n만 19세 이상인 자\n=== 그림 판독 공고문.pdf 3쪽 ===\n판독 글자"
    at = {name: text.index(name) for name in ("공고 개요", "만 19세", "판독 글자")}
    made = {
        "evidence": [{"id": f"ev-{k}", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": v, "end": v + 2}} for k, v in at.items()]
        + [
            {"id": "ev-collected", "sourceId": "text", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 2}},
            {"id": "ev-row", "sourceId": "units", "locator": {"kind": "UNIT_ROW", "pointer": "/0"}},
        ]
    }
    made["evidence"][2]["locator"]["page"] = 9  # 예전 값은 지웁니다
    attach_locator_pages(made, evidence_pages(made, {"pdf-text": text, "text": "--- 5쪽 ---\n수집 글자"}), "pdf-text")
    locators = {e["id"]: e["locator"] for e in made["evidence"]}
    assert locators["ev-공고 개요"]["page"] == 1 and locators["ev-만 19세"]["page"] == 2
    assert "page" not in locators["ev-판독 글자"]  # 그림 판독 묶음 안
    assert "page" not in locators["ev-collected"] and "page" not in locators["ev-row"]  # PDF 글자가 아닌 원문
    assert all("printedPage" not in locator for locator in locators.values())


def test_locator_page_passes_the_event_contract():
    from mujuthaek_extraction.judgment.pages import attach_locator_pages

    candidate = verified()
    ranges = [e for e in candidate["evidence"] if e["locator"]["kind"] == "TEXT_RANGE"]
    assert ranges
    attach_locator_pages(candidate, {e["id"]: 1 for e in ranges}, ranges[0]["sourceId"])
    assert ranges[0]["locator"]["page"] == 1
    assert tools().validate(envelope(completed_payload(candidate, provider="가상주거공사")), EVENT_SCHEMA) == []


def _youth(item_id, text, low, high):
    return item(item_id, "AGE", text, atom("AGE_YEARS", "BETWEEN", [low, high], "APPLICANT", unit="YEAR"))


def test_list_items_under_one_of_lead_become_one_choice_not_all_required():
    # AI가 「다음 중 어느 하나」 목록의 줄을 따로 낸 경우: 모두 갖춰야 하는 조건으로 두지 않고 선택지 하나로 묶고 확인 필요
    items = [
        item("lead", "OTHER", "신청자는 공고일 현재 다음 중 어느 하나에 해당하는 자이어야 합니다."),
        _youth("young", "① 만 19세 이상 만 39세 이하인 자", 19, 39),
        item("old", "AGE", "② 만 65세 이상인 자", atom("AGE_YEARS", "GTE", 65, "APPLICANT", unit="YEAR")),
    ]
    frame = build_judgment(candidate(items))
    assert frame_errors(frame) == []
    [either] = frame["common"]
    assert either["kind"] == "ANY_OF" and either["inReview"] and "하나만" in either["reviewReason"]
    assert [[(c["kind"], c["minAge"], c["maxAge"]) for c in o["criteria"]] for o in either["options"]] == [[("AGE", 19, 39)], [("AGE", 65, None)]]
    assert [o["label"] for o in either["options"]] == ["만 19세 이상 만 39세 이하인 자", "만 65세 이상인 자"]


def test_one_of_list_that_cannot_be_structured_becomes_one_question():
    items = [
        item("lead", "OTHER", "이번 모집은 아래 직군 종사자에 한하여 공급합니다."),
        item("a", "OTHER", "- 산업단지 입주기업에 재직 중인 근로자"),
        item("b", "OTHER", "- 공공의료기관 소속 간호 인력"),
        item("c", "OTHER", "- 군 복무 중인 부사관"),
    ]
    frame = build_judgment(candidate(items))
    assert frame_errors(frame) == []
    [asked] = frame["common"]
    assert asked["kind"] == "ASK" and asked["metWhen"] == "YES" and asked["inReview"]
    assert asked["question"].startswith("다음 중 하나에 해당하나요?") and "공공의료기관" in asked["question"] and "부사관" in asked["question"]


def test_all_required_list_and_limit_list_stay_separate():
    required = [
        item("lead", "OTHER", "다음 요건을 모두 갖춘 자"),
        item("home", "OTHER", "- 무주택세대구성원일 것"),
        _youth("young", "- 만 19세 이상 만 39세 이하인 자", 19, 39),
    ]
    frame = build_judgment(candidate(required))
    assert frame_errors(frame) == [] and len(frame["common"]) >= 2
    assert not any(c["kind"] == "ANY_OF" or str(c["id"]).endswith("one-of") for c in criteria(frame))
    # 「아래 중 하나에 해당하면 신청 불가」는 줄마다 「해당하면 안 됨」으로 따로 묻는 것이 맞음
    limits = [
        item("lead", "OTHER", "아래 중 어느 하나에 해당하는 자는 신청할 수 없습니다."),
        item("a", "OTHER", "- 공공임대주택에 거주 중인 자는 신청할 수 없습니다"),
        item("b", "OTHER", "- 분양전환 공공임대주택 당첨자는 신청할 수 없습니다"),
    ]
    frame = build_judgment(candidate(limits))
    assert not any(str(c["id"]).endswith("one-of") for c in criteria(frame))


def test_list_lead_saying_both_one_and_all_is_one_question_in_review():
    items = [
        item("lead", "OTHER", "아래 중 하나에 해당하고 아래 요건을 모두 갖춘 자"),
        item("a", "OTHER", "- 대학 재학생"),
        item("b", "OTHER", "- 취업 준비 중인 졸업생"),
    ]
    [asked] = build_judgment(candidate(items))["common"]
    assert asked["kind"] == "ASK" and asked["inReview"] and "정하지 못해" in asked["reviewReason"]
    # 머리 문장과 목록을 한 항목에 담은 경우(계약이 허락하는 모양)는 「하나에 해당하나요?」로 묻습니다
    single = item("one", "OTHER", "다음 중 하나에 해당하는 자\n- 대학 재학생\n- 취업 준비 중인 졸업생")
    [asked] = build_judgment(candidate([single]))["common"]
    assert asked["question"].startswith("다음 중 하나에 해당하나요?") and not asked["inReview"]


def test_list_lines_far_from_the_lead_or_in_another_scope_are_not_joined():
    items = [
        item("lead", "OTHER", "이번 모집은 아래 직군 종사자에 한하여 공급합니다."),
        item("a", "OTHER", "- 산업단지 입주기업에 재직 중인 근로자"),
        item("b", "OTHER", "- 공공의료기관 소속 간호 인력", groups=["신혼부부"]),
    ]
    made = candidate(items, ["신혼부부"])
    made["evidence"] = [
        {"id": "ev-1", "sourceId": "text", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 30}, "quote": "x"},
        {"id": "ev-2", "sourceId": "text", "locator": {"kind": "TEXT_RANGE", "start": 2000, "end": 2030}, "quote": "y"},
    ]
    made["eligibility"][1]["evidenceIds"] = ["ev-2"]  # 머리 문장에서 멀리 떨어진 줄
    frame = build_judgment(made)
    assert not any(str(c["id"]).endswith("one-of") for c in criteria(frame))


def test_group_left_without_criteria_asks_membership_instead_of_passing_everyone():
    # 실측 2026-10-26 LH 청년 매입임대: 「수급자 가구」를 가리킨 자격 문장이 모두 안내(순위·정의)로 빠져 조건 0개 →
    # 판정이 공통 조건만 보고 누구나 「지원 가능」. 빈 대상군은 해당 여부를 묻고 검수 표시해요
    youth = item("age", "AGE", "19세 이상 39세 이하인 사람", atom("AGE_YEARS", "GTE", 19, subject="APPLICANT", unit="YEAR"), groups=["청년"])
    for text in ("수급자 가구는 1순위로 공급합니다", "수급자 가구란 생계급여 수급자를 말합니다"):
        recipient = item("recipient", "OTHER", text, groups=["수급자 가구"])
        frame = build_judgment(candidate([recipient, youth], target_groups=["청년"]))
        [member] = next(g for g in frame["groups"] if g["name"] == "수급자 가구")["criteria"]
        assert (member["kind"], member["question"], member["inReview"]) == ("ASK", "「수급자 가구」 대상에 해당하나요?", True)


def test_outline_marks_are_dropped_and_same_groups_merge():
    # 실측 홍성·대전 영구임대: 같은 대상이 「1순위 나목 국가유공자 등」·「일반공급 1순위 나목 국가유공자 등」, 「타. 장애인(2순위)」·「타목 장애인(2순위)」
    from mujuthaek_extraction.judgment.frame import clean_group_name

    assert clean_group_name("1순위 나목 국가유공자 등") == "1순위 국가유공자 등"
    assert clean_group_name("타. 장애인(2순위)") == "장애인(2순위)"
    assert clean_group_name("타목 장애인(2순위)") == "장애인(2순위)"
    assert clean_group_name("「가」군 일본군위안부 피해자") == "일본군위안부 피해자"
    assert clean_group_name("1순위 일반 장애인") == "1순위 일반 장애인"  # 목차 표기가 아닌 말은 그대로
    assert clean_group_name("나목") == "나목"  # 다 빠지면 원래 이름

    income = atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, benchmark=URBAN)
    merit = item("merit", "INCOME", "70% 이하", income, groups=["1순위 나목 국가유공자 등"])
    merit2 = item("merit2", "INCOME", "70% 이하", income, groups=["일반공급 1순위 나목 국가유공자 등"])
    disabled = item("disabled", "INCOME", "70% 이하", income, groups=["타. 장애인(2순위)"])
    frame = build_judgment(candidate([merit, merit2, disabled], target_groups=["타목 장애인(2순위)"]))
    names = [g["name"] for g in frame["groups"]]
    assert names.count("장애인(2순위)") == 1 and "1순위 국가유공자 등" in names and len(names) == 2
    assert frame_errors(frame) == []


def test_housing_frame_does_not_copy_selection_rules_and_guidance_into_notes():
    # 실측 2026-10-26 홍성 영구임대: 틀 안내 98개 중 선정 규칙 77·안내 19가 selectionRules·guidance 복사본. 상세 화면은 원래 칸을 쓰므로
    # 주거 틀에는 옮기지 않아요(사업공간은 우대·안내로 계속 써요)
    made = verified()
    assert made["selectionRules"] and made["guidance"]
    frame = build_judgment(made)
    texts = {n["text"] for n in frame["notes"]}
    assert not texts & {r["description"] for r in made["selectionRules"]}
    assert not texts & {g["description"] for g in made["guidance"]}
    assert all(n["kind"] != "SELECTION" for n in frame["notes"])
