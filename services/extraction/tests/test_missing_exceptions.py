"""V5 예외 누락 의심. 실제 군산 공고(2015122300020453)에서 AI가 출산자녀 가산을 빠뜨린 모양을 줄여 씁니다. AI 호출 없음."""

from mujuthaek_extraction.verify import SourceBundle
from mujuthaek_extraction.verify.exceptions import check_missing_exceptions

CAR_TABLE = "출산자녀 수 총자산 가액(금회 배제) 자동차가액(금회 적용)\n0명(기준) 34,500만원 4,542만원\n1명 37,900만원 4,996만원\n2명 41,300만원 5,451만원\n"
SUMMARY = "자산요건 배제(단, 자산 중 자동차가액은 4,542만원 이하일 것)\n소형·저가주택: 가격이 1억원(수도권은 1억 6천만원) 이하\n"


def atom(attribute, value, unit="KRW"):
    return {"kind": "ATOMIC", "subject": "HOUSEHOLD", "attribute": attribute, "operator": "LTE", "value": value, "unit": unit}


def condition(expression, exceptions=()):
    return {"rule": {"status": "STRUCTURED", "expression": expression, "reason": None}, "exceptions": list(exceptions)}


def check(eligibility, text):
    return check_missing_exceptions({"eligibility": eligibility}, SourceBundle(texts={"text": text}))


def test_bonus_table_next_to_threshold_is_suspected():
    [finding] = check([condition(atom("CAR_ASSETS_KRW", 45_420_000))], SUMMARY + CAR_TABLE)
    assert finding.code == "EXCEPTION_SUSPECTED" and finding.target == "/eligibility/0"
    assert "4,996만원, 5,451만원" in finding.description


def test_summary_alone_is_not_suspected():
    # 1억원·1억 6천만원은 다른 기준(주택가격)이라 크기가 달라 걸리지 않습니다
    assert check([condition(atom("CAR_ASSETS_KRW", 45_420_000))], SUMMARY) == []


def test_value_already_used_by_another_condition_is_not_suspected():
    text = "총자산가액: 34,500만원 이하 총자산가액: 25,100만원 이하\n"
    first = dict(condition(atom("TOTAL_ASSETS_KRW", 345_000_000)), scope={"level": "NOTICE", "targetGroups": ["1·2순위"]})
    second = dict(condition(atom("TOTAL_ASSETS_KRW", 251_000_000)), scope={"level": "NOTICE", "targetGroups": ["3순위"]})
    assert check([first, second], text) == []


def test_condition_with_some_exceptions_still_reports_the_missing_tier():
    # 실측(2026-10-16 시험): 출산가구 가산 구간 중 일부만 예외로 넣고 나머지가 빠진 채 완료되던 것
    def replace(value):
        return {"when": {"status": "UNSTRUCTURED", "expression": None, "reason": "x"}, "effectExpression": atom("CAR_ASSETS_KRW", value)}

    [finding] = check([condition(atom("CAR_ASSETS_KRW", 45_420_000), [replace(49_960_000)])], CAR_TABLE)
    assert "5,451만원" in finding.description and "4,996만원" not in finding.description.split("「")[0]
    assert check([condition(atom("CAR_ASSETS_KRW", 45_420_000), [replace(49_960_000), replace(54_510_000)])], CAR_TABLE) == []


def test_unit_share_after_income_criterion_is_not_suspected():
    # 「100% 우선공급 (70%)」「주택 수의 70%」는 공급 물량 몫이지 소득 가산 기준이 아닙니다(전북개발공사 분양 실측)
    text = "월평균소득의 100% 이하인 자를 대상으로 신생아 특별공급 주택 수의 70% (소득 우선)\n100% 우선공급 (70%)\n"
    assert check([condition(atom("INCOME_BENCHMARK_PERCENT", 100, "PERCENT"))], text) == []


def test_income_percent_columns_are_suspected():
    text = "가구원수 70% 80% 90%\n1인 2,669,354 3,050,690 3,432,027\n"
    [finding] = check([condition(atom("INCOME_BENCHMARK_PERCENT", 70, "PERCENT"))], text)
    assert "80%, 90%" in finding.description


def test_rent_surcharge_band_table_is_not_suspected():
    # 재계약 임대료 할증 구간표(대구도시공사 매입임대 실측): 소득 구간 경계값이라 가산 기준이 아닙니다
    text = "소득 구간 | 70%이하까지 | 73.5%초과 77%이하 | 77%초과 91%이하 | 91%초과 105%이하\n할증 비율 | 없음 | 10% | 20% | 40%\n"
    assert check([condition(atom("INCOME_BENCHMARK_PERCENT", 70, "PERCENT"))], text) == []


def test_household_tiers_written_as_separate_conditions_are_flagged():
    # 실측(인천 행복주택): 「1인 120%, 2인 110%, 그 외 100%」를 가구원 수 조건 없이 조건 세 개로 나란히 적어 자동 게시됨
    percent = lambda v: atom("INCOME_BENCHMARK_PERCENT", v, unit="PERCENT")  # noqa: E731
    tiers = [dict(condition(percent(v)), scope={"level": "NOTICE", "supplyGroupIds": [], "targetGroups": ["대학생"]}) for v in (120, 110, 100)]
    findings = [f for f in check(tiers, "") if f.code == "TIER_CONDITION_MISSING"]
    assert [f.target for f in findings] == ["/eligibility/0", "/eligibility/1", "/eligibility/2"] and "120, 110, 100" in findings[0].description
    # 대상(계층)이 다르면 서로 다른 기준이라 걸지 않음
    other = [dict(condition(percent(v)), scope={"level": "NOTICE", "supplyGroupIds": [], "targetGroups": [g]}) for v, g in ((120, "대학생"), (100, "청년"))]
    assert not [f for f in check(other, "") if f.code == "TIER_CONDITION_MISSING"]
    # 가구원 수 조건이 조건식에 있으면 의도한 구간
    two = {"kind": "ANY", "children": [{"kind": "NOT", "child": atom("HOUSEHOLD_MEMBER_COUNT", 2, unit="COUNT") | {"operator": "EQ"}}, percent(110)]}
    fixed = [dict(condition(two), scope=tiers[0]["scope"]), tiers[2]]
    assert not [f for f in check(fixed, "") if f.code == "TIER_CONDITION_MISSING"]


def test_tiers_joined_to_the_criterion_with_and_are_held_with_the_other_conditions_on_it():
    # 2026-11-08 유료 확인 dcco-24812: 구간 조건 누락 경고를 받은 담당이 「ALL[2인, 80% 이하]」처럼 구간을 그리고로 붙인 조건을 새로 넣어
    # 자동 게시(모두 함께 적용되어 2인이 아닌 가구는 자격 없음, 구간마다 두면 아무도 자격 없음)
    percent = lambda v: atom("INCOME_BENCHMARK_PERCENT", v, unit="PERCENT")  # noqa: E731
    size = lambda n: atom("HOUSEHOLD_MEMBER_COUNT", n, unit="COUNT") | {"operator": "EQ"}  # noqa: E731
    scope = {"level": "NOTICE", "supplyGroupIds": [], "targetGroups": ["차목 일반입주자"]}
    joined = [dict(condition({"kind": "ALL", "children": [size(n), percent(v)]}), scope=scope) for n, v in ((1, 70), (2, 60))]
    base = dict(condition(percent(50)), scope=scope)
    findings = [f for f in check([*joined, base], "") if f.code.startswith("TIER_CONDITION")]
    assert [(f.code, f.target) for f in findings] == [("TIER_CONDITION_CONJOINED", f"/eligibility/{i}") for i in range(3)]
    assert "가구원 수 구간을 기준과 「그리고」로 묶은" in findings[0].description and "조건 3개" in findings[0].description
    # 구간 조건 누락으로 이미 걸린 조건(값만 다른 조건 둘)은 또 걸지 않음
    plain = [dict(condition(percent(v)), scope=scope) for v in (70, 60)]
    codes = {f.target: f.code for f in check([joined[0], *plain], "") if f.code.startswith("TIER_CONDITION")}
    assert codes == {"/eligibility/0": "TIER_CONDITION_CONJOINED", "/eligibility/1": "TIER_CONDITION_MISSING", "/eligibility/2": "TIER_CONDITION_MISSING"}
    # 그 대상에 그 기준 조건이 하나뿐인 그리고 묶음(다자녀 「미성년 자녀 3명 이상이고 소득 120% 이하」)·「그 구간이 아니거나 기준값 이하」(ANY)·
    # 기본 조건 + 구간 예외는 걸지 않음
    many = atom("CHILD_COUNT", 3, unit="COUNT") | {"operator": "GTE"}
    alone = dict(condition({"kind": "ALL", "children": [many, percent(120)]}), scope=scope)
    implied = [dict(condition({"kind": "ANY", "children": [{"kind": "NOT", "child": size(n)}, percent(v)]}), scope=scope) for n, v in ((1, 70), (2, 60))]
    replace = {"when": {"status": "STRUCTURED", "expression": size(1), "reason": None}, "effect": "REPLACE", "effectExpression": percent(70)}
    excepted = dict(condition(percent(50), [replace]), scope=scope)
    for eligibility in ([alone], [*implied, base], [excepted]):
        assert not [f for f in check(eligibility, "") if f.code.startswith("TIER_CONDITION")]


def test_renewal_income_criterion_in_eligibility_is_flagged():
    # 실측(경북 매입임대 2026-10-17): 「재계약 시 소득 105% 이하」가 신청 자격 조건으로 자동 게시됨
    renewal = dict(
        condition(atom("INCOME_BENCHMARK_PERCENT", 105, "PERCENT")),
        appliesTo="재계약 대상 세대",
        originalText="해당 세대의 월평균 소득이 105% 이하이고, 국민임대주택 자산기준을 충족한 경우 재계약이 가능합니다",
    )
    assert [f.target for f in check([renewal], "") if f.code == "RENEWAL_CRITERION_IN_ELIGIBILITY"] == ["/eligibility/0"]
    # 신청 자격 문장 안에서 재계약을 언급하는 것은 걸지 않음
    applying = dict(condition(atom("INCOME_BENCHMARK_PERCENT", 100, "PERCENT")), appliesTo="신청자", originalText="신청자는 소득 100% 이하(재계약 시에도 유지)")
    assert not [f for f in check([applying], "") if f.code == "RENEWAL_CRITERION_IN_ELIGIBILITY"]


def test_lower_bound_of_a_stage_band_in_eligibility_is_held():
    # 2026-11-07 유료 확인(jbdc-16011): 「(2단계) 추첨공급 : … 130% 초과 200% 이하 * 1단계 낙첨자를 포함」을 자격 하한으로 옮겨 게시됨
    from mujuthaek_extraction.verify.verifier import is_note

    percent = lambda v, op="LTE": atom("INCOME_BENCHMARK_PERCENT", v, unit="PERCENT") | {"operator": op}  # noqa: E731
    band = condition({"kind": "ALL", "children": [percent(130, "GT"), percent(200)]})
    [finding] = [f for f in check([condition(percent(120)), band], "") if f.code == "LOWER_BOUND_IN_ELIGIBILITY"]
    assert finding.target == "/eligibility/1" and "130% 초과" in finding.description and not is_note(finding.issue())
    # 범위(BETWEEN)의 아래 끝, NOT 안의 이하, 예외의 바뀐 기준에 있는 하한도 하한입니다
    between = condition(atom("TOTAL_ASSETS_KRW", [100_000_000, 200_000_000]) | {"operator": "BETWEEN"})
    negated = condition({"kind": "NOT", "child": percent(100)})  # 계약의 NOT은 child 하나
    replaced = condition(percent(100), [{"when": {"status": "UNSTRUCTURED", "expression": None}, "effectExpression": percent(120, "GTE")}])
    flagged = [f for f in check([between, negated, replaced], "") if f.code == "LOWER_BOUND_IN_ELIGIBILITY"]
    assert [f.target for f in flagged] == ["/eligibility/0", "/eligibility/1", "/eligibility/2"]
    assert "100,000,000원 이상" in flagged[0].description and "100% 초과" in flagged[1].description and "120% 이상" in flagged[2].description
    # 상한만 있거나, 하한이 예외의 발동 조건(when)·다른 기준(나이)이면 걸지 않습니다
    trigger = condition(percent(100), [{"when": {"status": "STRUCTURED", "expression": percent(100, "GT")}, "effectExpression": percent(90)}])
    age = condition(atom("AGE_YEARS", 19, unit="YEAR") | {"operator": "GTE"})
    assert not [f for f in check([condition(percent(100)), trigger, age], "") if f.code == "LOWER_BOUND_IN_ELIGIBILITY"]
