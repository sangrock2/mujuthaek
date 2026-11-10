"""Python·Java가 함께 사용하는 수신 경계 사례를 생성합니다. 합성 예시만 사용하며 API를 호출하지 않습니다."""

import copy
import json
from pathlib import Path

import validate_contracts as contract

ROOT = Path(__file__).resolve().parents[1]
BASE = contract.load(ROOT / "examples/extraction.completed.json")
CASES = []


def case(name, operations=(), *, valid=False, code=None):
    value = copy.deepcopy(BASE)
    patches = []
    for path, replacement in operations:
        parent, _, key = path.rpartition("/")
        node = contract.resolve(value, parent)
        if replacement is REMOVE:
            del node[int(key) if isinstance(node, list) else key]
            patches.append({"path": path, "remove": True})
        else:
            node[int(key) if isinstance(node, list) else key] = copy.deepcopy(replacement)
            patches.append({"path": path, "value": replacement})
    errors = contract.validate(value, "events/extraction.completed.v1.json")
    assert (not errors) == valid, (name, errors)
    if code:
        assert any(e.startswith(code + " ") for e in errors), (name, errors)
    CASES.append({"name": name, "operations": patches, "valid": valid, "errorCode": code})


REMOVE = object()
P = "/payload"
D = P + "/notice"
case("valid_legacy_without_condition_scope", valid=True)
case("integer_envelope_number_spelling", [("/schemaVersion", 1.0)], valid=True)
case("integer_raw_version_number_spelling", [(P + "/rawVersion", float(BASE["payload"]["rawVersion"]))], valid=True)
case("wrong_producer", [("/producer", "collector")], code="SCHEMA")
case("wrong_envelope_version", [("/schemaVersion", 999)], code="SCHEMA")
case("raw_version_exceeds_db_integer", [(P + "/rawVersion", 4294967297)], code="SCHEMA")
case("invalid_occurred_at", [("/occurredAt", "not-a-date")], code="SCHEMA")
case("wrong_optional_array_type", [(P + "/heldItems", {})], code="SCHEMA")
case("wrong_reprocess_type", [(P + "/reprocess", "false")], code="SCHEMA")
case("raw_version_conflict", [(P + "/rawVersion", 99)], code="EVENT_NOTICE_IDENTITY_CONFLICT")
case("title_conflict", [(P + "/title", "다른 제목")], code="EVENT_TITLE_CONFLICT")
case("reprocess_conflict", [(P + "/reprocess", True)], code="EVENT_REPROCESS_CONFLICT")
case("region_conflict", [(P + "/regionCode", "41110")], code="EVENT_REGION_CONFLICT")
case("ready_without_detail", [(D, REMOVE)], code="SCHEMA")
case("review_without_detail", [(D, REMOVE), (P + "/reviewStatus", "IN_REVIEW")], valid=True)
case("policy_without_notice_detail", [(D, REMOVE), (P + "/field", "POLICY")], valid=True)
case("optional_schedule_omitted", [(P + "/schedule", REMOVE), (P + "/applicationWindows", REMOVE)], valid=True)
case("source_version_conflict", [(P + "/rawVersion", 99), (D + "/input/rawVersion", 99)], code="INPUT_REFERENCE_MISMATCH")
case("dangling_evidence", [(D + "/notice/evidenceIds", ["unknown-evidence"])], code="DANGLING_EVIDENCE")
case("wrong_evidence_document", [(D + "/evidence/0/sourceId", "unknown-doc")], code="DANGLING_SOURCE")
case("duplicate_id", [(D + "/schedules/0/id", BASE["payload"]["notice"]["locations"][0]["id"])], code="DUPLICATE_ID")
case("dangling_quality_pointer", [(D + "/quality/notes", [{"code": "X", "target": "/schedules/9999", "description": "확인이 필요합니다."}])], code="DANGLING_FIELD_POINTER")
case("secret_in_malformed_url", [(D + "/documents/0/originalUrl", "not-an-absolute-url?serviceKey=review-placeholder-not-a-real-key")], code="SCHEMA")
case("secret_in_valid_url", [(D + "/documents/0/originalUrl", "https://example.com/file?serviceKey=review-placeholder-not-a-real-key")], code="PRIVATE_URL")

conditions = BASE["payload"]["notice"]["eligibility"]
first = conditions[0]
case("condition_description_conflict", [(P + "/conditions/0/description", "다른 설명입니다.")], code="EVENT_CONDITION_CONTENT_CONFLICT")
case("condition_target_conflict", [(P + "/conditions/0/target", "다른 대상")], code="EVENT_CONDITION_CONTENT_CONFLICT")
case("condition_scope_present", [(P + "/conditions/0/scope", first["scope"])], valid=True)
scope = {**first["scope"], "targetGroups": ["different"]}
case("condition_scope_conflict", [(P + "/conditions/0/scope", scope)], code="EVENT_CONDITION_CONTENT_CONFLICT")
atom_path, atom = next((path, n) for path, n in contract.walk(first["rule"], "/rule") if n.get("attribute") == "AGE_YEARS")
case("condition_age_119_conflict", [(P + "/conditions/0" + atom_path + "/value", 119)], code="EVENT_CONDITION_CONTENT_CONFLICT")
case("attribute_unit_conflict", [(P + "/conditions/0" + atom_path + "/unit", "KRW"), (D + "/eligibility/0" + atom_path + "/unit", "KRW")], code="ATTRIBUTE_UNIT_CONFLICT")
percent_path, percent = next((path, n) for path, n in contract.walk(conditions, "/conditions") if n.get("attribute") == "INCOME_BENCHMARK_PERCENT")
case("equal_percentage_number_spelling", [(P + percent_path + "/value", float(percent["value"]))], valid=True)

schedules = BASE["payload"]["notice"]["schedules"]
idx = next(i for i, s in enumerate(schedules) if "APPLICATION" in s["kinds"])
sp = D + "/schedules/" + str(idx)
case("schedule_projection_conflict", [(P + "/schedule/applyEndOn", "2026-11-01")], code="EVENT_SCHEDULE_CONFLICT")
case("window_projection_conflict", [(P + "/applicationWindows/0/applyEndOn", "2026-11-01")], code="EVENT_WINDOWS_CONFLICT")
case("reversed_schedule", [(sp + "/startsAt", {"precision": "DAY", "value": "2026-12-31"}), (P + "/schedule", REMOVE), (P + "/applicationWindows", REMOVE)], code="REVERSED_SCHEDULE")
case("invalid_application_mode", [(sp + "/applicationMode", "NOT_APPLICABLE")], code="APPLICATION_MODE_CONFLICT")
case("month_window_kept", [(sp + "/startsAt", {"precision": "MONTH", "value": "2026-10"}), (sp + "/endsAt", {"precision": "MONTH", "value": "2026-10"}), (P + "/schedule", REMOVE), (P + "/applicationWindows", REMOVE)], valid=True)
held = [{"target": f"/schedules/{idx}/applicationMode", "extent": "ITEM", "codes": ["X"], "description": "확인이 필요합니다."}]
case("nested_schedule_hold", [(P + "/reviewStatus", "PARTIALLY_PASSED"), (P + "/heldItems", held), (D + "/quality/heldItems", held), (D + "/quality/verification/status", "PARTIALLY_PASSED"), (P + "/schedule", None), (P + "/applicationWindows", [])], valid=True)
case("held_condition_without_review", [(P + "/reviewStatus", "PARTIALLY_PASSED"), (P + "/heldItems", [{**held[0], "target": "/eligibility/0/rule"}]), (D + "/quality/heldItems", [{**held[0], "target": "/eligibility/0/rule"}]), (D + "/quality/verification/status", "PARTIALLY_PASSED")], code="HELD_CONDITION_NOT_IN_REVIEW")
case("human_approval_preserves_auto_verification", [(P + "/reviewStatus", "APPROVED"), (D + "/quality/verification/status", "REVIEW_REQUIRED"), (D + "/quality/reviewIssues", [{"code": "MANUAL_CHECK", "target": "/eligibility/0", "description": "사람이 확인했습니다."}])], valid=True)
case("human_approval_requires_notice_identity", [(P + "/reviewStatus", "APPROVED"), (D + "/quality/verification/status", "REVIEW_REQUIRED"), (D + "/notice/publisher", None)], code="SCHEMA")

# 지역 코드(2026-10-20 결정): 서비스는 앞 5자리만 쓰고, 시군구 자리 000은 시도 단위(11000 = 서울특별시)
location = BASE["payload"]["notice"]["locations"][0]
sido = location["regionCode"][:2]
other_gu = {**location, "id": "boundary-other-gu", "regionCode": sido + "14000000"}
case("region_sido_level_location", [(D + "/locations/0/regionCode", sido + "00000000"), (P + "/regionCode", sido + "000")], valid=True)
case("region_two_sigungu_same_sido", [(D + "/locations", [location, other_gu]), (P + "/regionCode", sido + "000")], valid=True)
case("region_two_sigungu_needs_sido_code", [(D + "/locations", [location, other_gu])], code="EVENT_REGION_CONFLICT")
case("region_sido_zero_invalid", [(P + "/regionCode", "00110")], code="REGION_CODE_HIERARCHY")

# 공고 기본 정보 중 공고일·공급 유형·설명·대상 계층·공고 전체 수량은 칸 단위 보류, 제목·기관·분야는 보류 불가(2026-10-20 결정)
partial = [(P + "/reviewStatus", "PARTIALLY_PASSED"), (D + "/quality/verification/status", "PARTIALLY_PASSED")]


def notice_hold(target, code="API_MISMATCH"):
    item = [{"target": target, "extent": "ITEM", "codes": [code], "description": "확인이 필요합니다."}]
    issue = [{"code": code, "target": target, "description": "확인이 필요합니다."}]
    return [*partial, (P + "/heldItems", item), (D + "/quality/heldItems", item), (D + "/quality/reviewIssues", issue)]


case("notice_announced_on_held", notice_hold("/notice/announcedOn"), valid=True)
case("notice_title_cannot_be_held", notice_hold("/notice/title"), code="HELD_TARGET_NOT_ALLOWED")
reference = BASE["payload"]["notice"]["sourceReferences"][0]
mismatch = {
    "status": "MISMATCH",
    "referenceSha256": "a" * 64,
    "referenceIdentity": {k: reference[k] for k in ("sourceCode", "sourceNoticeId", "rawPostId", "rawVersion")},
    "fields": [{"target": "/notice/announcedOn", "sourcePath": "/목록/PAN_NT_ST_DT", "expected": "1999-01-01", "actual": BASE["payload"]["notice"]["notice"]["announcedOn"], "status": "MISMATCH", "reason": None}],
}
case("api_mismatch_on_held_field", [*notice_hold("/notice/announcedOn"), (D + "/quality/verification/apiComparison", mismatch)], valid=True)
case("api_mismatch_outside_hold", [*notice_hold("/notice/supplyType"), (D + "/quality/verification/apiComparison", mismatch)], code="API_MISMATCH_NOT_HELD")

# 섹션 전체를 가리키는 메모(빠진 다른 일정의 「/schedules」 메모)는 접수 일정을 빼지 않음 — 실측 LH 인천부평(2026-10-20)
section_note = [{"code": "ITEM_DROPPED_NO_EVIDENCE", "target": "/schedules", "description": "근거를 확인하지 못한 항목 1개를 뺐습니다."}]
case("section_note_keeps_application_windows", [(D + "/quality/notes", section_note)], valid=True)
# 일정 하나를 가리키는 표시 메모(근거 인용이 짧음 등)도 접수 일정을 빼지 않음 — 메모는 값이 틀렸다는 신호가 아님(2026-11-10 재검토, 저장된 gbdc-a909:
# 인용 하나가 짧다는 메모로 하나뿐인 접수 일정이 빠져 마감일을 잃었음)
item_note = [{"code": "EVIDENCE_QUOTE_TOO_SHORT", "target": "/schedules/0/endsAt", "description": "근거 인용이 짧습니다."}]
case("item_note_keeps_application_windows", [(D + "/quality/notes", item_note)], valid=True)

# 일정 장소·시각·제외 요일·신청 방법, 서류 묶음(2026-10-23). 신청 방법은 정해진 값만, 공고 전체 신청 방법은 신청 일정에서 계산한 값과 같아야 함
place = [{"name": "가상주거공사 1층 접수처", "address": None, "detail": None}]
case(
    "schedule_place_hours_and_days",
    [(D + "/schedules/0/places", place), (D + "/schedules/0/dailyHours", [{"start": "10:00", "end": "17:00"}]), (D + "/schedules/0/excludedDays", ["SAT", "SUN", "HOLIDAY"])],
    valid=True,
)
case("free_text_channel_rejected", [(D + "/schedules/0/channels", ["인터넷"])], code="SCHEMA")
case("invalid_application_email", [(D + "/schedules/0/applicationEmail", {"address": "접수 메일", "subjectFormat": None})], code="SCHEMA")
case("application_channels_conflict", [(D + "/notice/applicationChannels", ["ONLINE", "FAX"])], code="APPLICATION_CHANNELS_CONFLICT")
case("document_group_and_copies", [(D + "/requiredDocuments/0/group", "COMMON"), (D + "/requiredDocuments/0/copies", 1)], valid=True)

output = ROOT / "tests/fixtures/extraction-boundaries.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"base": "extraction.completed.json", "cases": CASES}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(CASES)} shared boundary cases")
