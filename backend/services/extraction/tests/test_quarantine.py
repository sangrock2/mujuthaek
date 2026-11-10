"""항목 격리: 계약 오류 종류와 상관없이 위치만 보고 문제 항목만 낮춥니다. AI 호출 없음."""

import copy

from helpers import ai_part, example, source_for

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.assemble.quarantine import quarantine
from mujuthaek_extraction.contracts import tools

SCHEMA = "schemas/extracted-notice.v1.json"


def candidate():
    data = example("housing")
    return assemble([copy.deepcopy(ai_part(data))], source_for("housing", data)).candidate


def test_broken_condition_rule_is_downgraded_not_dropped():
    c = candidate()
    c["eligibility"][1]["rule"]["expression"]["attribute"] = "UNKNOWN_ATTRIBUTE"
    errors = tools().validate(c, SCHEMA)
    assert errors
    fixed, actions = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    condition = fixed["eligibility"][1]
    assert condition["rule"]["status"] == "UNSTRUCTURED" and condition["originalText"] == c["eligibility"][1]["originalText"]
    assert [(i["code"], i["target"]) for i in fixed["quality"]["reviewIssues"]] == [("ITEM_QUARANTINED", "/eligibility/1")]
    assert actions and c["eligibility"][1]["rule"]["status"] == "STRUCTURED"  # 입력은 그대로


def test_broken_item_outside_judgment_is_removed_to_notes_and_pointers_shift():
    c = candidate()
    prices = c["supplyGroups"][0]["prices"]
    prices[0]["evidenceIds"] = ["없는-근거"]  # 처음 보는 종류라고 가정한 오류: 코드는 보지 않고 위치만 봅니다
    c["supplyGroups"][0]["prices"][1]["vatRate"] = None
    c["quality"]["missingFields"].append({"target": "/supplyGroups/0/prices/1/vatRate", "reason": "NOT_IN_SOURCE", "description": "부가세율 없음"})
    errors = tools().validate(c, SCHEMA)
    assert errors == ["DANGLING_EVIDENCE /supplyGroups/0/prices/0"]
    fixed, _ = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    assert len(fixed["supplyGroups"][0]["prices"]) == len(prices) - 1
    assert fixed["quality"]["missingFields"][-1]["target"] == "/supplyGroups/0/prices/0/vatRate"  # 앞 원소가 빠져 위치가 당겨짐
    assert [(n["code"], n["target"]) for n in fixed["quality"]["notes"]] == [("ITEM_QUARANTINED", "/supplyGroups/0/prices")]
    assert fixed["quality"]["coverage"]["supplyGroups"]["status"] == "PARTIAL"


def test_broken_count_grouping_is_ungrouped():
    c = candidate()
    count = c["notice"]["counts"][0]
    count.update(aggregationRole="TOTAL", aggregationComplete=True)
    errors = tools().validate(c, SCHEMA)
    assert any(e.startswith("INCOMPLETE_COUNT_COMPONENTS") for e in errors)
    fixed, _ = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    assert fixed["notice"]["counts"][0]["value"] == count["value"] and not fixed["notice"]["counts"][0]["aggregationComplete"]


def test_nothing_to_do_returns_same_content():
    c = candidate()
    fixed, actions = quarantine(c, [])
    assert fixed == c and actions == []


def test_missing_location_clears_reference_instead_of_deleting_supply():
    # 단지 항목이 빠져도 그 단지를 가리키던 공급(가격)은 지우지 않고 참조만 비웁니다
    c = candidate()
    c["locations"] = []
    errors = tools().validate(c, SCHEMA)
    assert any(e.startswith("DANGLING") for e in errors)
    fixed, actions = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    assert len(fixed["supplyGroups"]) == len(c["supplyGroups"]) and fixed["supplyGroups"][0]["prices"]
    assert fixed["supplyGroups"][0]["locationId"] is None and actions


def test_two_errors_in_one_condition_downgrade_it_once_instead_of_deleting_it():
    # 검토 지적: 같은 회차에 한 조건의 오류가 두 개면 첫 오류로 조건식을 내리고, 두 번째 오류가 곧바로 조건을 통째로 지웠음
    c = candidate()
    for child in c["eligibility"][0]["rule"]["expression"]["children"]:
        child["attribute"] = "UNKNOWN_ATTRIBUTE"
    errors = tools().validate(c, SCHEMA)
    assert [e.split(" ", 1)[0] for e in errors] == ["ATTRIBUTE_UNKNOWN", "ATTRIBUTE_UNKNOWN"]
    fixed, _ = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    assert [e["id"] for e in fixed["eligibility"]] == [e["id"] for e in c["eligibility"]]
    condition = fixed["eligibility"][0]
    assert condition["rule"]["status"] == "UNSTRUCTURED" and condition["originalText"] == c["eligibility"][0]["originalText"]
    assert [(i["code"], i["target"]) for i in fixed["quality"]["reviewIssues"]] == [("ITEM_QUARANTINED", "/eligibility/0")]


def test_removals_follow_records_not_positions():
    # 검토 지적: 가격을 빼며 그 안을 가리키던 누락 기록(A)이 지워지자 /quality/missingFields/2가 한 칸 밀려 멀쩡한 기록(Z)이 지워졌음
    c = candidate()
    c["supplyGroups"][0]["prices"][1]["vatRate"] = None
    c["supplyGroups"][0]["prices"][1]["evidenceIds"] = ["없는-근거"]
    healthy = {"target": "/schedules/0/priorityRank", "reason": "NOT_IN_SOURCE", "description": "Z"}
    c["quality"]["missingFields"] = [
        {"target": "/supplyGroups/0/prices/1/vatRate", "reason": "NOT_IN_SOURCE", "description": "A"},
        {"target": "/supplyGroups/0/prices/0/vatRate", "reason": "NOT_IN_SOURCE", "description": "X"},
        {"target": "/supplyGroups/0/prices/0/vatRate", "reason": "NOT_IN_SOURCE", "description": "Y"},
        healthy,
    ]
    errors = tools().validate(c, SCHEMA)
    assert sorted(errors) == ["DANGLING_EVIDENCE /supplyGroups/0/prices/1", "DUPLICATE_FIELD_RECORD /quality/missingFields/2"]
    fixed, _ = quarantine(c, errors)
    assert tools().validate(fixed, SCHEMA) == []
    assert [m["description"] for m in fixed["quality"]["missingFields"]] == ["X", "Z"]
    assert fixed["quality"]["missingFields"][-1] == healthy
    assert len(fixed["supplyGroups"][0]["prices"]) == 1
