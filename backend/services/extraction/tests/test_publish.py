"""extraction.completed payload 만들기(팀 확정 형식). 결합·검증까지 거친 후보를 씁니다. AI 호출 없음."""

import copy
from datetime import UTC, datetime

from helpers import ai_part, example, source_for

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.publish import completed_payload
from mujuthaek_extraction.verify import SourceBundle, verify_extraction

EVENT_SCHEMA = "events/extraction.completed.v1.json"


def verified(name="housing"):
    data = example(name)
    source = source_for(name, data)
    candidate = assemble([ai_part(data)], source).candidate
    return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC)).candidate


def envelope(payload):
    return {
        "eventId": "01929a3e-0000-7000-8000-0000000000c1",
        "eventType": "extraction.completed",
        "schemaVersion": 1,
        "occurredAt": "2026-10-15T00:00:00Z",
        "producer": "extraction",
        "traceId": None,
        "payload": payload,
    }


def test_passed_candidate_becomes_auto_passed_event_that_matches_contract():
    payload = completed_payload(verified(), provider="가상주거공사")
    assert tools().validate(envelope(payload), EVENT_SCHEMA) == []
    assert payload["reviewStatus"] == "AUTO_PASSED"
    assert payload["regionCode"] == "11110"  # 법정동 10자리 1111000000의 앞 5자리
    assert payload["schedule"] == {"applyStartOn": "2026-10-01", "applyEndOn": "2026-10-31"}
    assert [c["inReview"] for c in payload["conditions"]] == [False] * len(payload["conditions"])


def test_review_issue_marks_condition_and_event_in_review():
    candidate = verified()
    candidate["quality"]["reviewIssues"].append({"code": "EVIDENCE_AMBIGUOUS", "target": "/eligibility/1", "description": "검수 필요"})
    candidate["quality"]["verification"]["status"] = "REVIEW_REQUIRED"
    payload = completed_payload(candidate)
    assert payload["reviewStatus"] == "IN_REVIEW"
    assert [c["reviewReasons"] for c in payload["conditions"]] == [[], ["EVIDENCE_AMBIGUOUS"], []]
    assert tools().validate(envelope(payload), EVENT_SCHEMA) == []


def test_unverified_application_schedule_is_left_out():
    candidate = verified()
    index = next(i for i, s in enumerate(candidate["schedules"]) if "APPLICATION" in s["kinds"])
    candidate["quality"]["reviewIssues"].append({"code": "EVIDENCE_QUOTE_NOT_FOUND", "target": f"/schedules/{index}", "description": "x"})
    assert completed_payload(candidate)["schedule"] is None


def test_region_is_null_when_locations_span_several_sido():
    candidate = verified()
    extra = copy.deepcopy(candidate["locations"][0])
    extra.update(id="other", regionCode="4111000000")
    candidate["locations"].append(extra)
    assert completed_payload(candidate)["regionCode"] is None


def test_region_follows_the_contract_rule():
    # 계약 검사기와 같은 규칙: 앞 5자리가 하나면 그 코드, 시도까지만 알면 시도 코드(xx000), 코드 없는 위치가 섞이면 null
    candidate = verified()
    code = candidate["locations"][0]["regionCode"]
    assert completed_payload(candidate)["regionCode"] == code[:5]
    sido_only = copy.deepcopy(candidate)
    sido_only["locations"][0]["regionCode"] = code[:2] + "00000000"
    assert completed_payload(sido_only)["regionCode"] == code[:2] + "000"
    unknown = copy.deepcopy(candidate)
    extra = copy.deepcopy(unknown["locations"][0])
    extra.update(id="unknown", regionCode=None)
    unknown["locations"].append(extra)
    assert completed_payload(unknown)["regionCode"] is None


def test_rank_specific_application_windows_are_all_sent_for_notifications():
    # GH 국민임대 실측: 1·2·3순위 접수 기간이 따로 → schedule(하나)은 비우고 applicationWindows에 순위별로 모두 담습니다
    candidate = verified()
    base = next(s for s in candidate["schedules"] if "APPLICATION" in s["kinds"])
    ranks = []
    for rank, (start, end) in enumerate([("2026-10-01", "2026-10-02"), ("2026-10-05", "2026-10-06"), ("2026-10-07", "2026-10-08")], start=1):
        item = copy.deepcopy(base)
        item.update(id=f"apply-rank{rank}", rawLabel=f"{rank}순위 접수", priorityRank=rank)
        item["startsAt"], item["endsAt"] = {"precision": "DAY", "value": start}, {"precision": "DAY", "value": end}
        ranks.append(item)
    candidate["schedules"] = [s for s in candidate["schedules"] if s is not base] + ranks
    payload = completed_payload(candidate)
    assert payload["schedule"] is None
    windows = payload["applicationWindows"]
    assert [(w["priorityRank"], w["applyStartOn"], w["applyEndOn"]) for w in windows] == [
        (1, "2026-10-01", "2026-10-02"),
        (2, "2026-10-05", "2026-10-06"),
        (3, "2026-10-07", "2026-10-08"),
    ]
    assert tools().validate(envelope(payload), EVENT_SCHEMA) == []


def test_application_window_with_review_issue_is_left_out():
    candidate = verified()
    index = next(i for i, s in enumerate(candidate["schedules"]) if "APPLICATION" in s["kinds"])
    assert len(completed_payload(candidate)["applicationWindows"]) == 1
    candidate["quality"]["reviewIssues"].append({"code": "EVIDENCE_QUOTE_NOT_FOUND", "target": f"/schedules/{index}", "description": "x"})
    assert completed_payload(candidate)["applicationWindows"] == []


def test_field_level_hold_marks_the_whole_condition_and_schedule():
    # 검토 지적(2026-10-20): 보류 범위를 "같거나 상위"만 봐서 /eligibility/0/rule, /schedules/i/applicationMode 같은 하위 보류를 놓쳤음
    candidate = verified()
    application = next(i for i, s in enumerate(candidate["schedules"]) if "APPLICATION" in s["kinds"])
    candidate["quality"]["heldItems"] = [
        {"target": "/eligibility/0/rule", "extent": "ITEM", "codes": ["VALUE_NOT_IN_QUOTE"], "description": "원문 확인 필요"},
        {"target": f"/schedules/{application}/applicationMode", "extent": "ITEM", "codes": ["EVIDENCE_SCATTERED"], "description": "원문 확인 필요"},
    ]
    candidate["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
    payload = completed_payload(candidate)
    assert payload["conditions"][0]["inReview"] and "VALUE_NOT_IN_QUOTE" in payload["conditions"][0]["reviewReasons"]
    assert payload["schedule"] is None
    assert all(w["scheduleId"] != candidate["schedules"][application]["id"] for w in payload["applicationWindows"])


def test_held_notice_description_is_not_used_as_list_summary():
    candidate = verified()
    candidate["quality"]["heldItems"] = [{"target": "/notice/description", "extent": "ITEM", "codes": ["VALUE_NOT_IN_QUOTE"], "description": "원문 확인 필요"}]
    candidate["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
    payload = completed_payload(candidate)
    assert payload["summary"] is None and payload["notice"]["notice"]["description"]


def test_partial_result_marks_only_the_held_condition_in_review():
    # 문제가 특정 조건에만 있으면 공고는 게시하고 그 조건만 판정 보류(검증은 test_verify)
    from test_verify import NOW, assembled, clock

    candidate, sources = assembled()
    candidate["quality"]["reviewIssues"].append({"code": "EXCEPTION_SUSPECTED", "target": "/eligibility/0", "description": "가산 기준이 빠졌을 수 있습니다."})
    report = verify_extraction(candidate, sources, None, clock=clock)
    payload = completed_payload(report.candidate)
    assert payload["reviewStatus"] == "PARTIALLY_PASSED" and payload["heldItems"] == report.candidate["quality"]["heldItems"]
    assert payload["conditions"][0]["inReview"] and "EXCEPTION_SUSPECTED" in payload["conditions"][0]["reviewReasons"]
    event = {
        "eventId": "00000000-0000-4000-8000-000000000001",
        "eventType": "extraction.completed",
        "schemaVersion": 1,
        "occurredAt": NOW.isoformat(),
        "producer": "extraction",
        "traceId": None,
        "payload": payload,
    }
    assert tools().validate(event, "events/extraction.completed.v1.json") == []


def test_held_eligibility_section_marks_every_condition_in_review():
    from test_verify import assembled, clock

    candidate, sources = assembled()
    partial = copy.deepcopy(candidate)
    partial["quality"]["coverage"]["eligibility"] = {"status": "PARTIAL", "reason": "일부만 추출했습니다."}
    report = verify_extraction(partial, sources, None, clock=clock)
    assert all(c["inReview"] for c in completed_payload(report.candidate)["conditions"])
