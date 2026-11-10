"""수신 경계와 맞춘 조건·일정·승인 투영. API 호출 없이 검증된 합성 후보로 확인합니다."""

import copy

from test_publish import envelope, verified

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.publish import approved_payload, completed_payload


def test_nested_held_schedule_is_not_projected():
    candidate = verified()
    i = next(i for i, s in enumerate(candidate["schedules"]) if "APPLICATION" in s["kinds"])
    candidate["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
    candidate["quality"]["heldItems"] = [
        {"target": f"/schedules/{i}/applicationMode", "extent": "ITEM", "codes": ["CHECK"], "description": "확인이 필요합니다."}
    ]
    payload = completed_payload(candidate)
    assert payload["applicationWindows"] == []
    assert payload["schedule"] is None
    assert tools().validate(envelope(payload), "events/extraction.completed.v1.json") == []


def test_undated_window_is_kept_for_status_calculation():
    candidate = verified()
    schedule = next(s for s in candidate["schedules"] if "APPLICATION" in s["kinds"])
    schedule.update(startsAt=None, endsAt=None, endStatus="UNKNOWN", endCondition=None)
    payload = completed_payload(candidate)
    assert payload["applicationWindows"][0]["applyStartOn"] is None
    assert payload["applicationWindows"][0]["applyEndOn"] is None


def test_human_approval_keeps_auto_record_but_releases_active_holds():
    candidate = verified()
    candidate["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
    candidate["quality"]["heldItems"] = [{"target": "/eligibility/0/rule", "extent": "ITEM", "codes": ["CHECK"], "description": "확인이 필요합니다."}]
    candidate["quality"]["reviewIssues"] = [{"target": "/eligibility/0/rule", "code": "CHECK", "description": "확인이 필요합니다."}]
    original = copy.deepcopy(candidate)
    payload = approved_payload(candidate)
    assert candidate == original
    assert "heldItems" not in payload
    assert "heldItems" not in payload["notice"]["quality"]
    assert payload["notice"]["quality"]["verification"] == candidate["quality"]["verification"]
    assert payload["notice"]["quality"]["reviewIssues"] == candidate["quality"]["reviewIssues"]
    assert all(not c["inReview"] for c in payload["conditions"])
    assert payload["conditions"][0]["scope"] == candidate["eligibility"][0]["scope"]
    assert tools().validate(envelope(payload), "events/extraction.completed.v1.json") == []
