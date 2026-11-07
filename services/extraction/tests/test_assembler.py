"""AI 출력 + 신뢰 문맥 → extracted-notice v1 후보. 계약 예시를 AI 출력으로 되돌린 fixture를 씁니다. AI 호출 없음."""

import copy
import dataclasses
import json

import pytest
from helpers import SECTIONS, ai_part, example, source_for

from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.assemble.assembler import AssemblyInput, assemble


def rename_evidence(original, candidate):
    """예시의 근거 ID(e1…)를 결합기가 만든 ID(ev-1…)로 바꿔 비교합니다.

    결합기는 인용문만큼의 범위를 계산하고, 예시는 끝 줄바꿈까지 포함한 범위를 쓰기도 합니다. 같은 문서·같은 시작 위치면 같은 근거입니다.
    """
    ours = {(e["sourceId"], e["locator"]["start"]): e for e in candidate["evidence"]}
    mapping = {}
    for e in original["evidence"]:
        mine = ours[(e["sourceId"], e["locator"]["start"])]
        assert mine["locator"]["end"] <= e["locator"]["end"] and mine["quote"] == e["quote"]
        mapping[e["id"]] = mine["id"]

    def walk(node):
        if isinstance(node, dict):
            return {k: ([mapping[x] for x in v] if k == "evidenceIds" else walk(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(original)


@pytest.mark.parametrize("name", ["housing", "business"])
def test_round_trip_reproduces_contract_example(name):
    data = example(name)
    result = assemble([ai_part(data)], source_for(name, data))

    assert result.contract_errors == [] and result.issues == []
    candidate = result.candidate
    expected = rename_evidence(data, candidate)
    for key in (*SECTIONS, "input", "sourceReferences", "documents"):
        assert candidate[key] == expected[key], key
    assert candidate["quality"]["coverage"] == data["quality"]["coverage"]
    assert candidate["quality"]["verification"]["status"] == "NOT_RUN"
    assert "fieldAssessments" not in candidate["quality"]


def test_section_calls_are_merged_like_one_call():
    data = example("housing")
    source = source_for("housing", data)
    whole = assemble([ai_part(data)], source).candidate
    parts = [
        ai_part(data, ("notice", "schedules", "guidance")),
        ai_part(data, ("locations", "supplyGroups")),
        ai_part(data, ("eligibility", "selectionRules", "requiredDocuments")),
    ]
    split = assemble(parts, source)
    assert split.contract_errors == [] and split.candidate == whole


def test_ai_cannot_supply_trusted_or_computed_fields():
    schema_text = json.dumps(ai_output.schema(), ensure_ascii=False)
    for name in ("evidenceIds", "amountKrw", "regionCode", "sourceReference", "verification", "locator"):
        assert name not in schema_text
    data = example("housing")
    part = ai_part(data)
    part["input"] = data["input"]  # 신뢰 문맥을 AI가 넣으려 하면 응답 전체를 쓰지 않습니다
    result = assemble([part], source_for("housing", data))
    assert result.candidate is None and result.issues[0]["code"] == "AI_OUTPUT_INVALID"


def test_quote_not_in_source_drops_only_that_record_and_marks_partial():
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 보증금 문장입니다"})
    part["supplyGroups"][0]["prices"][0]["quoteRefs"] = ["fake"]
    rent_id = part["supplyGroups"][0]["prices"][1]["id"]
    result = assemble([part], source_for("housing", data))

    prices = result.candidate["supplyGroups"][0]["prices"]
    assert [p["id"] for p in prices] == [rent_id]
    assert result.candidate["quality"]["coverage"]["supplyGroups"]["status"] == "PARTIAL"
    issues = {i["code"]: i for i in result.issues}
    assert issues["EVIDENCE_QUOTE_NOT_FOUND"]["target"] == issues["ITEM_DROPPED_NO_EVIDENCE"]["target"] == "/supplyGroups/0/prices"
    # 빠진 항목은 목록을 가리키므로, 어떤 항목·어떤 인용문인지 설명에 남깁니다
    dropped = data["supplyGroups"][0]["prices"][0]["id"]
    not_found = issues["EVIDENCE_QUOTE_NOT_FOUND"]["description"]
    assert dropped in not_found and "「원문에 없는 보증금 문장입니다」" in not_found
    assert issues["ITEM_DROPPED_NO_EVIDENCE"]["description"].endswith(f"1개를 뺐습니다: {dropped}")


def test_pointers_after_dropped_record_are_shifted():
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 보증금 문장입니다"})
    prices = part["supplyGroups"][0]["prices"]
    prices[0]["quoteRefs"] = ["fake"]
    prices[1]["sourceAmount"] = "공고문 참조"  # 계산 불가 → 뺀 뒤 위치(prices/0)에 누락 사유
    prices[1].update(taxTreatment="UNKNOWN", vatRate=None)
    part["missingFields"] = [{"target": "/supplyGroups/0/prices/1/vatRate", "reason": "NOT_IN_SOURCE", "description": "부가세율이 없습니다."}]
    result = assemble([part], source_for("housing", data))

    missing = {m["target"]: m["reason"] for m in result.candidate["quality"]["missingFields"]}
    assert missing == {"/supplyGroups/0/prices/0/vatRate": "NOT_IN_SOURCE", "/supplyGroups/0/prices/0/amountKrw": "NEEDS_REVIEW"}
    assert result.candidate["supplyGroups"][0]["prices"][0]["amountKrw"] is None


def test_unsupported_condition_drops_whole_eligibility_item_not_just_the_condition():
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 나이 조건입니다"})
    child = part["eligibility"][0]["rule"]["expression"]["children"][0]
    child["quoteRefs"] = ["fake"]
    before = len(part["eligibility"])
    result = assemble([part], source_for("housing", data))
    assert len(result.candidate["eligibility"]) == before - 1  # 조건 하나만 빼면 ALL의 의미가 바뀌므로 항목 전체를 뺍니다
    assert result.candidate["quality"]["coverage"]["eligibility"]["status"] == "PARTIAL"


def test_lease_term_without_evidence_becomes_null_with_reason():
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 임대기간 문장"})
    part["supplyGroups"][0]["leaseTerm"]["quoteRefs"] = ["fake"]
    result = assemble([part], source_for("housing", data))
    assert result.candidate["supplyGroups"][0]["leaseTerm"] is None
    missing = {m["target"]: m["reason"] for m in result.candidate["quality"]["missingFields"]}
    assert missing["/supplyGroups/0/leaseTerm"] == "NEEDS_REVIEW"


def test_notice_without_evidence_gives_no_candidate():
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 공고 제목"})
    part["notice"]["quoteRefs"] = ["fake"]
    result = assemble([part], source_for("housing", data))
    assert result.candidate is None and any(i["code"] == "ITEM_WITHOUT_EVIDENCE" for i in result.issues)


def test_invalid_item_is_dropped_but_section_survives():
    # 항목 격리(2026-10-16): 형식이 틀린 항목만 빼고 섹션은 살립니다. 원문 표현(rawLabel)이 틀린 일정은 고칠 수 없어 뺍니다
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    part["schedules"].append({**copy.deepcopy(part["schedules"][0]), "id": "broken", "rawLabel": ""})
    result = assemble([part], source_for("housing", data))
    assert [s["id"] for s in result.candidate["schedules"]] == [data["schedules"][0]["id"]]
    assert result.candidate["quality"]["coverage"]["schedules"]["status"] == "PARTIAL"
    assert ("AI_OUTPUT_ITEM_DROPPED", "/schedules") in {(i["code"], i["target"]) for i in result.issues}


def test_invalid_schedule_fields_are_coerced_and_item_held():
    # 프론트 요청 6-3(2026-10-23): 종류·접수 방식·시각이 틀린 일정은 빼지 않고 틀린 칸만 안전한 값으로 바꿔 「확인 필요」(보류)로 남깁니다
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    broken = copy.deepcopy(part["schedules"][0])
    broken.update(id="broken", kinds=["APPLICATION", "INTERVIEW"], applicationMode="SOMETIMES", dailyHours=[{"start": "9시", "end": "18:00"}])
    broken["endsAt"] = {"precision": "MINUTE", "value": "10월 31일"}
    part["schedules"].append(broken)
    result = assemble([part], source_for("housing", data))
    assert result.contract_errors == []
    kept = result.candidate["schedules"][1]
    assert kept["id"] == "broken" and kept["rawLabel"] == broken["rawLabel"] and kept["evidenceIds"]
    assert kept["kinds"] == ["APPLICATION"] and kept["applicationMode"] == "UNKNOWN" and kept["dailyHours"] == []
    assert (kept["endsAt"], kept["endStatus"], kept["endCondition"]) == (None, "UNKNOWN", None)
    assert result.candidate["quality"]["coverage"]["schedules"]["status"] == "EXTRACTED"
    assert ("AI_OUTPUT_ITEM_COERCED", "/schedules/1") in {(i["code"], i["target"]) for i in result.issues}


def test_schedule_with_only_unknown_kinds_becomes_other():
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    part["schedules"].append({**copy.deepcopy(part["schedules"][0]), "id": "tour", "kinds": ["TOUR"], "applicationMode": "FIXED_PERIOD"})
    result = assemble([part], source_for("housing", data))
    kept = result.candidate["schedules"][1]
    assert kept["kinds"] == ["OTHER"] and kept["applicationMode"] == "NOT_APPLICABLE"
    assert ("AI_OUTPUT_ITEM_COERCED", "/schedules/1") in {(i["code"], i["target"]) for i in result.issues}


def test_bad_extra_schedule_fields_are_only_cleared():
    # 덧붙인 칸(접수 장소·제외 요일)만 틀리면 비우고 표시 메모만 남깁니다(보류 아님). 일정 항목을 가리키면 접수 기간에서 빠지므로 섹션을 가리킵니다
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    part["schedules"][0].update(places=[{"name": "접수처"}], excludedDays=["토요일"])
    result = assemble([part], source_for("housing", data))
    schedule = result.candidate["schedules"][0]
    assert schedule["places"] == [] and schedule["excludedDays"] == [] and schedule["kinds"] == ["APPLICATION"]
    assert ("AI_OUTPUT_FIELD_CLEARED", "/schedules") in {(i["code"], i["target"]) for i in result.issues}
    assert not [i for i in result.issues if i["code"] == "AI_OUTPUT_ITEM_COERCED"]


def test_invalid_exception_is_dropped_and_condition_marked():
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    exception = part["eligibility"][2]["exceptions"][0]
    exception["effectExpression"] = None  # 실측 AI 실수: REPLACE인데 효과 조건식이 없음
    result = assemble([part], source_for("housing", data))
    condition = result.candidate["eligibility"][2]
    assert condition["exceptions"] == [] and condition["exceptionsStatus"] == "NOT_REVIEWED"
    assert ("AI_OUTPUT_ITEM_DROPPED", "/eligibility/2") in {(i["code"], i["target"]) for i in result.issues}
    assert len(result.candidate["eligibility"]) == len(data["eligibility"])


def test_unrecoverable_section_still_fails_alone():
    data = example("housing")
    part = ai_part(data)
    part["schedules"] = "일정 없음"  # 목록이 아니면 살릴 항목이 없습니다
    result = assemble([part], source_for("housing", data))
    assert result.candidate["schedules"] == []
    assert result.candidate["quality"]["coverage"]["schedules"]["status"] == "FAILED"
    assert result.candidate["supplyGroups"]


def test_missing_section_is_not_attempted():
    data = example("housing")
    result = assemble([ai_part(data, ("notice", "locations", "supplyGroups"))], source_for("housing", data))
    assert result.candidate["quality"]["coverage"]["schedules"]["status"] == "NOT_ATTEMPTED"


def test_ambiguous_and_nearest_quotes():
    data = example("housing")
    source = source_for("housing", data)
    text = source.material.text
    repeated = "입니다."
    assert text.count(repeated) > 1
    part = ai_part(data)
    part["quotes"].append({"ref": "rep", "documentId": "text1", "text": repeated})
    notice = copy.deepcopy(part["notice"])
    part["notice"]["quoteRefs"] = ["rep"]  # 단독 → 위치를 못 정함, 근거가 없어 후보 없음
    assert assemble([part], source).candidate is None

    part["notice"] = notice
    part["notice"]["quoteRefs"] = [*notice["quoteRefs"], "rep"]
    result = assemble([part], source)
    # 기준 인용(원문 전체)이 모든 후보를 덮어 거리가 같으므로 고르지 않고 검수로 남깁니다. 다른 근거로 항목은 유지됩니다.
    assert result.candidate is not None
    assert ("EVIDENCE_AMBIGUOUS", "/notice") in {(i["code"], i["target"]) for i in result.issues}
    assert ("EVIDENCE_QUOTE_TOO_SHORT", "/notice") not in {(i["code"], i["target"]) for i in result.issues}


def test_region_code_is_computed_from_original_region_and_original_is_kept():
    data = example("housing")
    result = assemble([ai_part(data)], source_for("housing", data))
    location = result.candidate["locations"][0]
    assert location["region"] == "서울특별시 종로구" and location["regionCode"] == "1111000000"

    no_table = source_for("housing", data)
    no_table = AssemblyInput(no_table.context, no_table.material, regions=None)
    result = assemble([ai_part(data)], no_table)
    assert result.candidate["locations"][0]["regionCode"] is None
    assert {m["target"] for m in result.candidate["quality"]["missingFields"]} == {"/locations/0/regionCode"}


def test_missing_field_that_has_value_becomes_review_issue():
    data = example("housing")
    part = ai_part(data)
    part["missingFields"] = [{"target": "/supplyGroups/0/prices", "reason": "NEEDS_REVIEW", "description": "조건별 호수 배분이 없습니다."}]
    result = assemble([part], source_for("housing", data))

    assert result.candidate["quality"]["missingFields"] == []
    assert [(i["code"], i["target"]) for i in result.issues] == [("MISSING_FIELD_HAS_VALUE", "/supplyGroups/0/prices")]
    assert result.contract_errors == []


def test_broken_count_grouping_is_ungrouped_but_values_kept():
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    count = part["notice"]["counts"][0]
    count.update(aggregationRole="TOTAL", aggregationComplete=True)  # 구성 수량 없이 '합계 완결' (실측 AI 실수)
    part["supplyGroups"][0]["counts"] = [{**copy.deepcopy(count), "id": "orphan", "aggregationRole": "COMPONENT", "parentCountId": "missing"}]
    result = assemble([part], source_for("housing", data))
    assert result.contract_errors == []
    fixed = result.candidate["notice"]["counts"][0]
    assert fixed["aggregationComplete"] is False and fixed["value"] == count["value"]
    orphan = result.candidate["supplyGroups"][0]["counts"][0]
    assert orphan["parentCountId"] is None and orphan["aggregationRole"] == "STANDALONE"
    # 조용히 바꾸지 않고 검수로 가는 표시를 남겨요(2026-10-26 공통 검사)
    changed = [i for i in result.issues if i["code"] == "AI_OUTPUT_VALUE_CHANGED"]
    assert {i["target"] for i in changed} == {"/notice/counts/0", "/supplyGroups/0/counts/0"}


def test_recruitment_stage_written_as_count_target_is_cleared():
    # 2026-11-07 23건 대조: 공고 수량 「OFFERED 280 [예비입주자]」「RESERVE 15 [예비 입주자]」 — 모집 단계는 수량 종류가 나타내므로
    # 대상이 아닙니다(공고 전체 모집 수가 대상을 한정한 수로 보였음)
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    base = part["notice"]["counts"][0]

    def count(count_id, kind, value, groups):
        made = {**copy.deepcopy(base), "id": count_id, "kind": kind, "value": value, "aggregationRole": "STANDALONE", "parentCountId": None}
        made.update(aggregationComplete=False, scope={**base["scope"], "targetGroups": groups})
        return made

    def targets(counts):
        part["notice"]["counts"] = counts
        result = assemble([copy.deepcopy(part)], source_for("housing", data))
        assert result.contract_errors == []
        changed = [i["target"] for i in result.issues if i["code"] == "AI_OUTPUT_VALUE_CHANGED"]
        return [c["scope"]["targetGroups"] for c in result.candidate["notice"]["counts"]], changed

    staged = [count("c1", "OFFERED", 2, ["우선 입주자"]), count("c2", "RESERVE", 15, ["예비 입주자"]), count("c3", "OFFERED", 3, ["청년"])]
    assert targets(staged) == ([[], [], ["청년"]], ["/notice/counts/0", "/notice/counts/1"])  # 신청 계층(청년)은 그대로
    # 예비입주자만 모집하는 공고는 예비자 수가 OFFERED라 비웁니다
    assert targets([count("c1", "TOTAL_HOUSING", 1650, []), count("c2", "OFFERED", 280, ["예비입주자"])])[0] == [[], []]
    # 즉시·예비를 함께 뽑으며 예비자 수를 OFFERED로 적었으면(다른 OFFERED가 있음) 대상이 두 수를 가르므로 두고,
    # 비우면 같은 종류의 대상 없는 수량과 겹칠 때도 둡니다
    assert targets([count("c1", "OFFERED", 2, []), count("c2", "OFFERED", 15, ["예비입주자"])])[0] == [[], ["예비입주자"]]
    assert targets([count("c1", "RESERVE", 15, []), count("c2", "RESERVE", 15, ["예비 입주자"])])[0] == [[], ["예비 입주자"]]


def test_missing_field_pointing_nowhere_is_dropped():
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    part["missingFields"] = [{"target": "/supplyGroups/7/prices", "reason": "NOT_IN_SOURCE", "description": "없는 공급"}]
    result = assemble([part], source_for("housing", data))
    assert result.contract_errors == [] and result.candidate["quality"]["missingFields"] == []


def test_wrong_quote_ref_falls_back_to_item_original_text():
    # 인용 참조가 원문에 없는 문장을 가리켜도, 항목의 originalText가 원문 한 곳에 있으면 그곳을 근거로 씁니다
    data = example("housing")
    part = ai_part(data)
    part["quotes"].append({"ref": "wrong", "documentId": "text1", "text": "다른 계층의 원문에 없는 문장입니다"})
    part["eligibility"][2]["quoteRefs"] = ["wrong"]
    result = assemble([part], source_for("housing", data))

    assert "income" in [e["id"] for e in result.candidate["eligibility"]]
    assert "EVIDENCE_QUOTE_NOT_FOUND" not in {i["code"] for i in result.issues}
    assert any("originalText" in n for n in result.notes)


def test_previous_year_income_benchmark_gets_year_from_announcement():
    # "전년도 도시근로자 …" 기준은 공고일 연도 - 1로 채웁니다 (청년 매입임대 실측)
    data = example("housing")
    part = ai_part(data)
    atoms = [n for e in part["eligibility"] for n in [e["rule"].get("expression")] if n and n.get("attribute") == "INCOME_BENCHMARK_PERCENT"]
    assert atoms
    atoms[0]["benchmark"].update(standardName="전년도 도시근로자 가구당 월평균소득", referenceYear=None, referenceVersion=None)
    result = assemble([part], source_for("housing", data))
    year = int(result.candidate["notice"]["announcedOn"][:4]) - 1
    found = [
        e["rule"]["expression"]["benchmark"]["referenceYear"]
        for e in result.candidate["eligibility"]
        if (e["rule"].get("expression") or {}).get("attribute") == "INCOME_BENCHMARK_PERCENT"
    ]
    assert found == [year]


def test_filled_benchmark_year_resolves_ai_missing_report():
    # AI가 연도를 누락으로 보고하고 결합기가 채우면 모순(MISSING_FIELD_HAS_VALUE)으로 검수에 보내지 않습니다 (일괄 실측 8건)
    data = example("housing")
    part = ai_part(data)
    index = next(i for i, e in enumerate(part["eligibility"]) if (e["rule"].get("expression") or {}).get("attribute") == "INCOME_BENCHMARK_PERCENT")
    part["eligibility"][index]["rule"]["expression"]["benchmark"].update(
        standardName="전년도 도시근로자 가구당 월평균소득", referenceYear=None, referenceVersion=None
    )
    target = f"/eligibility/{index}/rule/expression/benchmark/referenceYear"
    part.setdefault("missingFields", []).append({"target": target, "reason": "NOT_IN_SOURCE", "description": "연도가 없습니다."})
    result = assemble([part], source_for("housing", data))
    assert "MISSING_FIELD_HAS_VALUE" not in {i["code"] for i in result.issues}
    assert target not in {m["target"] for m in result.candidate["quality"]["missingFields"]}


def test_missing_field_records_follow_items_after_bad_ones_are_dropped():
    # 검토 지적: 형식이 틀린 항목을 빼도 누락 기록 위치를 그대로 두어, 기록이 버려지거나 다른 항목을 가리켰음
    from mujuthaek_extraction.assemble.assembler import _shift_missing

    part = {
        "missingFields": [
            {"target": "/eligibility/0/rule", "reason": "NOT_IN_SOURCE"},  # 빼낸 항목 → 지움
            {"target": "/eligibility/2/referenceTime", "reason": "NOT_IN_SOURCE"},  # 2 → 1
            {"target": "/eligibility/12", "reason": "NOT_IN_SOURCE"},  # 12 → 11 (자릿수 다른 번호)
            {"target": "/schedules/0/endsAt", "reason": "NOT_IN_SOURCE"},  # 다른 섹션은 그대로
        ]
    }
    _shift_missing(part, "eligibility", {0})
    assert [m["target"] for m in part["missingFields"]] == ["/eligibility/1/referenceTime", "/eligibility/11", "/schedules/0/endsAt"]


def test_duplicate_ids_are_renamed_and_one_day_fixed_schedule_gets_its_end():
    # 실측(OpenAI dcco-24788): 가점표 행마다 같은 id → DUPLICATE_ID로 7행이 빠짐, 공고일을 FIXED + endsAt 없음으로 적어 형식 오류로 빠짐
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    first = part["schedules"][0]
    part["schedules"].append({**copy.deepcopy(first), "endStatus": "FIXED", "endsAt": None})
    result = assemble([part], source_for("housing", data))
    schedules = result.candidate["schedules"]
    assert [s["id"] for s in schedules] == [first["id"], f"{first['id']}.2"]
    # 시작이 시각(MINUTE)이면 끝으로 복사하지 않습니다(「10:00 이후」가 「10:00~10:00」으로 보임). 끝은 원문에 없음으로
    assert first["startsAt"]["precision"] == "MINUTE"
    assert (schedules[1]["endsAt"], schedules[1]["endStatus"]) == (None, "NOT_IN_SOURCE")
    assert ("AI_OUTPUT_ID_RENAMED", "/schedules") in {(i["code"], i["target"]) for i in result.issues}
    # 날짜(DAY)만 있는 하루짜리 일정은 시작값을 끝으로 씁니다
    day = {"precision": "DAY", "value": first["startsAt"]["value"][:10]}
    part["schedules"][-1] = {**copy.deepcopy(first), "id": "one-day", "startsAt": day, "endStatus": "FIXED", "endsAt": None}
    one_day = assemble([part], source_for("housing", data)).candidate["schedules"][-1]
    assert (one_day["endsAt"], one_day["endStatus"]) == (day, "FIXED")


def test_code_part_review_issue_points_to_its_supply_group():
    # 공급표를 옮긴 코드 조각이 남긴 검수 이슈(나누지 못한 두 금액 칸)는 그 공급 묶음 자리로 갑니다(형식 오류로 조각을 버리지 않음)
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    group_id = part["supplyGroups"][-1]["id"]
    part["_reviewIssues"] = [{"supplyGroupId": group_id, "code": "SUPPLY_PRICE_MISSING", "description": "두 금액 칸을 나누지 못했습니다"}]
    result = assemble([part], source_for("housing", data))
    found = {(i["code"], i["target"]) for i in result.issues}
    assert ("SUPPLY_PRICE_MISSING", f"/supplyGroups/{len(part['supplyGroups']) - 1}") in found
    assert not any(code == "AI_OUTPUT_INVALID" for code, _ in found)


def test_strict_mode_fillers_are_cleared_instead_of_dropping_rows():
    # 실측(OpenAI LH 대전 영구임대): 구조화된 가점 조건의 사유를 「""」로, 추첨 항목에 순서 번호를 적어 가점표 12행이 형식 오류로 빠짐
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    rules = part["selectionRules"]
    structured = next(r for r in rules if isinstance(r.get("rule"), dict) and r["rule"].get("status") == "STRUCTURED")
    structured["rule"]["reason"] = ""
    other = next(r for r in rules if r.get("kind") != "TIE_BREAK")
    other["order"] = 5
    result = assemble([part], source_for("housing", data))
    kept = {r["id"]: r for r in result.candidate["selectionRules"]}
    assert structured["id"] in kept and kept[structured["id"]]["rule"]["reason"] is None
    assert other["id"] in kept and kept[other["id"]]["order"] is None
    assert "AI_OUTPUT_ITEM_DROPPED" not in {i["code"] for i in result.issues}


def test_bare_host_link_gets_https():
    from mujuthaek_extraction.assemble.slips import fix_format_slips

    part = fix_format_slips({"guidance": [{"url": "www.lh.or.kr"}, {"url": "https://apply.lh.or.kr"}, {"url": "1600-1004"}]})
    assert [g["url"] for g in part["guidance"]] == ["https://www.lh.or.kr", "https://apply.lh.or.kr", "1600-1004"]


def test_bare_application_link_and_empty_present_exceptions_are_fixed():
    # 실측(OpenAI 청약홈 에코델타): 신청 주소 「www.applyhome.co.kr」, 예외 PRESENT + [] 때문에 일정·자격을 한 번씩 다시 요청
    from mujuthaek_extraction.assemble.slips import fix_format_slips

    part = fix_format_slips({"schedules": [{"applicationUrl": "www.applyhome.co.kr"}], "eligibility": [{"exceptionsStatus": "PRESENT", "exceptions": []}]})
    assert part["schedules"][0]["applicationUrl"] == "https://www.applyhome.co.kr"
    assert part["eligibility"][0]["exceptionsStatus"] == "NOT_REVIEWED"


def test_document_name_repeated_in_two_tables_takes_the_first_place():
    # 실측(청약홈 에코델타): 서류표가 원문에 두 번(글자 덩어리·표) 나와 첫 서류 두 개가 위치를 못 정해 빠짐
    data = example("housing")
    source = source_for("housing", data)
    text = source.material.text
    name = next(d["name"] for d in data["requiredDocuments"] if text.count(d["name"]) >= 1)
    doubled = dataclasses.replace(source.material, text=text + "\n" + name + " 서류표 되풀이\n")
    part = copy.deepcopy(ai_part(data))
    for d in part["requiredDocuments"]:
        if d["name"] == name:
            part["quotes"].append({"ref": "q-dup", "documentId": source.material.text_document_id, "text": name})
            d["quoteRefs"] = ["q-dup"]
    result = assemble([part], dataclasses.replace(source, material=doubled))
    assert name in {d["name"] for d in result.candidate["requiredDocuments"]}
    assert "EVIDENCE_AMBIGUOUS" not in {i["code"] for i in result.issues if i["target"].startswith("/requiredDocuments")}


def test_schedule_quoted_by_a_bare_date_repeated_in_the_source_takes_the_first_place():
    # 실측(LH 다자녀 전세임대): 공고문 끝의 「2026. 03. 24.」만 인용한 공고일 일정이 같은 날짜가 여러 곳에 있어 통째로 빠짐
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))
    schedule = part["schedules"][0]
    year, month, day = schedule["startsAt"]["value"][:10].split("-")
    bare = f"{year}. {month}. {day}."
    doubled = dataclasses.replace(source.material, text=source.material.text + f"\n{bare}\n접수 안내\n{bare}\n")
    part["quotes"].append({"ref": "q-date", "documentId": source.material.text_document_id, "text": bare})
    schedule["quoteRefs"] = ["q-date"]
    result = assemble([part], dataclasses.replace(source, material=doubled))
    assert schedule["id"] in {s["id"] for s in result.candidate["schedules"]}
    assert "EVIDENCE_AMBIGUOUS" not in {i["code"] for i in result.issues if i["target"].startswith("/schedules")}


def _income_index(part):
    return next(i for i, e in enumerate(part["eligibility"]) if (e["rule"].get("expression") or {}).get("attribute") == "INCOME_BENCHMARK_PERCENT")


def test_previous_year_only_in_original_text_still_gets_year_and_keeps_the_phrase():
    # 검토 지적: 항목 원문의 「전년도」를 버전에 옮겨 적은 뒤에는 연도 계산을 건너뛰어 referenceYear가 계속 비었음
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    index = _income_index(part)
    item = part["eligibility"][index]
    item["originalText"] = "전년도 도시근로자 가구당 월평균소득 70% 이하여야 합니다."
    item["rule"]["expression"]["benchmark"].update(standardName="도시근로자 가구당 월평균소득", referenceYear=None, referenceVersion=None)
    result = assemble([part], source_for("housing", data))
    assert result.contract_errors == []
    benchmark = result.candidate["eligibility"][index]["rule"]["expression"]["benchmark"]
    year = int(result.candidate["notice"]["announcedOn"][:4]) - 1
    assert (benchmark["referenceYear"], benchmark["referenceVersion"]) == (year, "전년도")
    assert any("버전 '전년도'" in n and f"({year}년)" in n for n in result.notes)


def test_conflicting_relative_years_are_not_guessed():
    # 항목 원문에 「전년도」와 「당해연도」가 함께 있으면 어느 쪽인지 고르지 않습니다(틀린 연도보다 검수가 낫습니다)
    data = example("housing")
    part = copy.deepcopy(ai_part(data))
    index = _income_index(part)
    item = part["eligibility"][index]
    item["originalText"] = "전년도 도시근로자 가구당 월평균소득 70% 이하, 당해연도 자산 기준 이하여야 합니다."
    item["rule"]["expression"]["benchmark"].update(standardName="도시근로자 가구당 월평균소득", referenceYear=None, referenceVersion=None)
    result = assemble([part], source_for("housing", data))
    benchmark = result.candidate["eligibility"][index]["rule"]["expression"]["benchmark"]
    assert benchmark["referenceYear"] is None and benchmark["referenceVersion"] is None
    assert any(e.startswith("INCOMPLETE_INCOME_BENCHMARK") for e in result.contract_errors)  # 격리 단계가 조건식을 내리고 검수로 보냅니다


def test_scattered_quote_with_reversed_meaning_goes_to_review():
    # 검토 지적: 낱말 순서를 보지 않아, 소득·자산이 뒤바뀐 인용이 근거로 받아들여지고 job 메모만 남았음
    data = example("housing")
    source = source_for("housing", data)
    original = "전년도 도시근로자 월평균소득 100% 이하인 자. 단, 총자산가액 기준 초과 시 제외합니다."
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + original + "\n")
    part = copy.deepcopy(ai_part(data))
    part["quotes"].append({"ref": "rev", "documentId": "text1", "text": "총자산가액 100% 이하인 자. 단, 도시근로자 월평균소득 기준 초과 시 제외합니다."})
    index = _income_index(part)
    part["eligibility"][index]["quoteRefs"] = ["rev"]
    result = assemble([part], dataclasses.replace(source, material=material))
    assert ("EVIDENCE_SCATTERED", f"/eligibility/{index}") in {(i["code"], i["target"]) for i in result.issues}
    assert result.candidate["eligibility"][index]["evidenceIds"]  # 위치는 정했으니 항목은 남기고 사람이 확인합니다
    assert result.contract_errors == []


ASSET_ROW = "| 자산 | 자녀가 없거나, 2023.3.27. 구분 이전 출생한 자녀만 있는 경우 총자산가액 345,000,000원 이하 |"


def _scattered_asset_quote(quote):
    data = example("housing")
    source = source_for("housing", data)
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + ASSET_ROW + "\n")
    part = copy.deepcopy(ai_part(data))
    part["quotes"].append({"ref": "row", "documentId": "text1", "text": quote})
    index = _income_index(part)
    part["eligibility"][index]["quoteRefs"] = ["row"]
    return index, assemble([part], dataclasses.replace(source, material=material))


def test_scattered_quote_in_source_order_with_only_a_header_cell_between_is_accepted():
    # 실측 live-perf LH 9550: 표 머리 칸 「구분」이 문장 사이에 섞여 읽혀, 그것만 뺀 인용이 흩어진 근거로 검수에 감(자격 조건 2개)
    index, result = _scattered_asset_quote("| 자산 | 자녀가 없거나, 2023.3.27. 이전 출생한 자녀만 있는 경우 총자산가액 345,000,000원 이하 |")
    assert not [i for i in result.issues if i["code"] == "EVIDENCE_SCATTERED"]
    assert result.candidate["eligibility"][index]["evidenceIds"]
    assert any(n.startswith(f"/eligibility/{index}") and "「구분」" in n for n in result.notes)


@pytest.mark.parametrize(
    "quote",
    [
        "| 자산 | 자녀가 없거나, 2023.3.27. 출생한 자녀만 있는 경우 총자산가액 345,000,000원 이하 |",  # 「구분 이전」을 빼면 뜻이 달라짐
        "| 자산 | 2023.3.27. 이전 출생한 자녀가 없거나, 자녀만 있는 경우 총자산가액 345,000,000원 이하 |",  # 낱말 순서가 바뀜
    ],
    ids=["skips-meaning-word", "reordered"],
)
def test_scattered_quote_missing_a_meaning_word_or_reordered_still_goes_to_review(quote):
    index, result = _scattered_asset_quote(quote)
    assert ("EVIDENCE_SCATTERED", f"/eligibility/{index}") in {(i["code"], i["target"]) for i in result.issues}


def test_scrambled_flowchart_quote_locates_evidence_but_judgment_items_are_reviewed():
    # 순서도처럼 뒤섞인 원문(남해창선 실측)은 낱말로 위치를 찾되, 일정은 판정에 쓰므로 검수로, 안내는 메모만 남깁니다
    data = example("housing")
    source = source_for("housing", data)
    flowchart = "■ 동일순위 내 경쟁 시 선정순서\n배점 합산\n전입일자가 세대구성원 신청자\n(아래 배점기준표 추첨\n오래된 자 수가 많은 자 연령 높은 자\n참조)\n"
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + flowchart)
    part = copy.deepcopy(ai_part(data))
    part["quotes"].append({"ref": "flow", "documentId": "text1", "text": "동일순위 내 경쟁 시 선정순서 배점 합산 (아래 배점기준표 참조) 전입일자가 오래된 자"})
    part["schedules"][0]["quoteRefs"] = ["flow"]
    part["guidance"][0]["quoteRefs"] = ["flow"]
    result = assemble([part], dataclasses.replace(source, material=material))
    candidate = result.candidate
    [evidence_id] = candidate["schedules"][0]["evidenceIds"]
    [evidence] = [e for e in candidate["evidence"] if e["id"] == evidence_id]
    assert evidence["quote"].startswith("동일순위") and candidate["guidance"][0]["evidenceIds"] == [evidence_id]
    assert [(i["code"], i["target"]) for i in result.issues if i["code"] != "DETAIL_UNVERIFIED_CLEARED"] == [("EVIDENCE_SCATTERED", "/schedules/0")]
    assert any(n.startswith("/guidance/0") and "뒤섞여" in n for n in result.notes)
    # 바뀐 근거에는 신청 방법(온라인)·시각이 없어 그 값은 비웁니다(날짜만 남김)
    schedule = candidate["schedules"][0]
    assert schedule["channels"] == [] and schedule["startsAt"]["precision"] == "DAY" and candidate["notice"]["applicationChannels"] == []


def test_later_broken_section_keeps_coverage_of_the_earlier_good_one():
    # 검토 지적: 앞 응답이 제대로 준 섹션을 뒤 응답이 깨진 채 다시 주면 범위가 FAILED로 덮이고 AI가 적은 PARTIAL 사유도 사라졌음
    data = example("housing")
    source = source_for("housing", data)
    good = ai_part(data, ("notice", "schedules"))
    good["coverage"]["schedules"] = {"status": "PARTIAL", "reason": "신청 일정만 옮겼습니다."}
    broken = ai_part(data, ("schedules", "guidance"))
    broken["schedules"] = "일정 없음"
    result = assemble([good, broken], source)
    assert result.candidate["quality"]["coverage"]["schedules"] == {"status": "PARTIAL", "reason": "신청 일정만 옮겼습니다."}
    assert result.candidate["schedules"] and result.candidate["guidance"]
    assert ("AI_OUTPUT_INVALID", "/schedules") in {(i["code"], i["target"]) for i in result.issues}


def test_earlier_broken_section_takes_coverage_of_the_later_good_one():
    data = example("housing")
    source = source_for("housing", data)
    broken = ai_part(data, ("notice", "schedules"))
    broken["schedules"] = "일정 없음"
    good = ai_part(data, ("schedules",))
    result = assemble([broken, good], source)
    assert result.candidate["quality"]["coverage"]["schedules"] == data["quality"]["coverage"]["schedules"]
    assert [s["id"] for s in result.candidate["schedules"]] == [s["id"] for s in data["schedules"]]
    assert result.contract_errors == []


def test_missing_records_of_sections_not_taken_from_that_response_are_dropped():
    # 검토 지적: 중복이라 버린 섹션의 누락 기록이 앞 응답 항목에 붙어 엉뚱한 MISSING_FIELD_HAS_VALUE를 만들었음
    data = example("housing")
    source = source_for("housing", data)
    first = ai_part(data, ("notice", "schedules"))
    first["missingFields"] = [{"target": "/schedules/0/priorityRank", "reason": "NOT_IN_SOURCE", "description": "순위 없음"}]
    second = ai_part(data, ("schedules", "guidance"))
    second["missingFields"] = [{"target": "/schedules/0/description", "reason": "NOT_IN_SOURCE", "description": "설명 없음"}]
    result = assemble([first, second], source)
    assert [m["target"] for m in result.candidate["quality"]["missingFields"]] == ["/schedules/0/priorityRank"]
    assert "MISSING_FIELD_HAS_VALUE" not in {i["code"] for i in result.issues}
    assert ("SECTION_DUPLICATED", "/schedules") in {(i["code"], i["target"]) for i in result.issues}
    assert any(n.startswith("/schedules/0/description") for n in result.notes)


def test_notice_level_scope_with_ids_takes_the_level_of_its_ids():
    # 실측 LH 인천부평: 「주거약자용 주택(36AS형)은 65세 이상만」을 범위 NOTICE + 공급 묶음 ID로 적어 형식 오류로 빠지고 자격 섹션이 보류됨
    from mujuthaek_extraction.assemble.slips import fix_format_slips

    def scope(level, groups=(), locations=()):
        return {"level": level, "supplyGroupIds": list(groups), "locationIds": list(locations)}

    part = fix_format_slips(
        {"eligibility": [{"scope": scope("NOTICE", groups=["sg-36as"])}, {"scope": scope("NOTICE", locations=["loc-1"])}, {"scope": scope("NOTICE")}]}
    )
    assert [item["scope"]["level"] for item in part["eligibility"]] == ["SUPPLY_GROUP", "LOCATION", "NOTICE"]
