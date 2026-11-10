"""Regression cases for contract boundaries, incomplete extraction and unsafe handoff."""

import copy
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_contracts as contract

EVENT = "events/extraction.completed.v1.json"


def parse_error(error, with_keyword):
    """"SCHEMA <위치>: <키워드>: <메시지>" 또는 "<코드> <위치>" → (코드, 위치, 키워드)."""
    code, _, rest = error.partition(" ")
    if code == "SCHEMA":
        path, _, rest = rest.partition(": ")
        return code, path, rest.split(": ", 1)[0] if with_keyword else None
    return code, rest.split(" ", 1)[0], None


class NoticeContractTest(unittest.TestCase):
    def setUp(self):
        self.notice = contract.load(ROOT / "examples/housing.standard.json")
        self.event = contract.load(ROOT / "examples/extraction.completed.json")

    def assert_valid(self, value=None, schema="schemas/standard-notice.v1.json"):
        self.assertEqual([], contract.validate(self.notice if value is None else value, schema))

    def assert_invalid(self, code, value=None, schema="schemas/standard-notice.v1.json"):
        errors = contract.validate(self.notice if value is None else value, schema)
        self.assertTrue(any(code in error for error in errors), errors)

    def assert_error(self, code, path, keyword=None, value=None, schema="schemas/standard-notice.v1.json"):
        """코드와 위치(SCHEMA면 키워드까지)가 맞는 오류가 있어야 합니다. 상관없는 스키마 오류로 통과하지 않게 합니다."""
        errors = contract.validate(self.notice if value is None else value, schema)
        self.assertIn((code, path, keyword), [parse_error(e, keyword is not None) for e in errors], errors)

    def assert_no_error(self, code, value=None, schema="schemas/standard-notice.v1.json"):
        errors = contract.validate(self.notice if value is None else value, schema)
        self.assertFalse([e for e in errors if e.split(" ", 1)[0] == code], errors)

    def add_api_match(self):
        source = self.notice["sourceReferences"][0]
        comparison = self.notice["quality"]["verification"]["apiComparison"]
        comparison.update(
            status="MATCHED",
            referenceSha256="a" * 64,
            referenceIdentity={k: source[k] for k in ("sourceCode", "sourceNoticeId", "rawPostId", "rawVersion")},
            fields=[
                {
                    "target": "/notice/announcedOn",
                    "sourcePath": "/dsList/0/PAN_DT",
                    "expected": "2026-10-01",
                    "actual": "2026-10-01",
                    "status": "MATCH",
                    "reason": None,
                }
            ],
        )
        return comparison

    def test_schemas_examples_and_offline_references(self):
        self.assertEqual([], contract.check_all())
        ids = {s["$id"] for s in contract.SCHEMAS.values()}
        for schema in contract.SCHEMAS.values():
            for _, node in contract.walk(schema):
                if "$ref" in node and not node["$ref"].startswith("#"):  # "#/..."는 같은 파일 안 참조 (collector 스키마)
                    self.assertIn(node["$ref"].split("#")[0], ids)

    def test_examples_have_actual_fixture_hashes_quotes_and_original_text(self):
        for prefix in ("housing", "business"):
            data = contract.load(ROOT / f"examples/{prefix}.extracted.json")
            raw = (ROOT / "examples/sources" / f"{prefix}.synthetic.txt").read_bytes()
            text = raw.decode("utf-8")
            self.assertEqual(hashlib.sha256(raw).hexdigest(), data["documents"][0]["sha256"])
            for evidence in data["evidence"]:
                locator = evidence["locator"]
                self.assertIn(evidence["quote"], text[locator["start"] : locator["end"]])
            for _, node in contract.walk(data):
                if "originalText" in node:
                    self.assertIn(node["originalText"], text)

    def test_partial_correction_is_sent_only_as_in_review(self):
        partial = contract.load(ROOT / "examples/correction.partial.json")
        self.assert_valid(partial, "schemas/extracted-notice.v1.json")
        payload = self.event["payload"]
        payload.update(
            notice=partial,
            rawPostId=partial["input"]["rawPostId"],
            rawVersion=partial["input"]["rawVersion"],
            regionCode="11110",
            conditions=[
                {
                    "id": item["id"],
                    "target": item["appliesTo"],
                    "targetGroups": item["scope"]["targetGroups"],
                    "category": item["category"],
                    "description": item["description"],
                    "originalText": item["originalText"],
                    "referenceTime": item["referenceTime"],
                    "rule": item["rule"],
                    "exceptions": item["exceptions"],
                    "inReview": True,
                    "reviewReasons": ["CORRECTION_PARTIAL"],
                }
                for item in partial["eligibility"]
            ],
        )
        schema = EVENT
        # AUTO_PASSED로는 보낼 수 없음: 검수 중 조건도, 통과하지 않은 검증도 안 됨
        self.assert_error("SCHEMA", "/payload/conditions/0/inReview", "const", self.event, schema)
        self.assert_error("SCHEMA", "/payload/notice/quality/verification/status", "const", self.event, schema)
        payload["reviewStatus"] = "IN_REVIEW"
        payload["schedule"] = contract.application_schedule(partial)
        payload["applicationWindows"] = contract.application_windows(partial)
        self.assert_valid(self.event, schema)  # 검수 중 표시와 함께 보낼 수 있음

    def test_partial_correction_cannot_overwrite_approved_notice(self):
        partial = contract.load(ROOT / "examples/correction.partial.json")
        self.notice["quality"] = partial["quality"]
        self.notice["schedules"] = []
        self.assert_error("SCHEMA", "/quality/verification/status", "enum")  # 공개 공고는 PASSED·PARTIALLY_PASSED만

    def test_human_approval_keeps_automatic_verification_history(self):
        self.notice["quality"]["verification"]["status"] = "REVIEW_REQUIRED"
        self.notice["quality"]["reviewIssues"].append({"code": "MANUAL_CHECK", "target": "/eligibility/0", "description": "사람이 확인했습니다."})
        self.assert_error("SCHEMA", "/quality/verification/status", "enum")
        self.notice["reviewStatus"] = "APPROVED"
        self.assert_valid()
        self.assertEqual("REVIEW_REQUIRED", self.notice["quality"]["verification"]["status"])

    def test_api_absence_allows_independent_source_verification(self):
        self.assert_valid()
        self.assertEqual("SKIPPED_NO_API_REFERENCE", self.notice["quality"]["verification"]["apiComparison"]["status"])

    def test_matching_same_notice_api_reference_is_valid(self):
        self.add_api_match()
        self.assert_valid()

    def test_other_notice_api_response_is_rejected(self):
        self.add_api_match()["referenceIdentity"]["sourceNoticeId"] = "different-notice"
        self.assert_invalid("API_REFERENCE_IDENTITY_CONFLICT")

    def test_other_raw_version_api_response_is_rejected(self):
        self.add_api_match()["referenceIdentity"]["rawVersion"] = 2
        self.assert_invalid("API_REFERENCE_IDENTITY_CONFLICT")

    def test_false_match_does_not_pass(self):
        self.add_api_match()["fields"][0]["expected"] = "2026-10-02"
        self.assert_invalid("FALSE_API_MATCH")

    def test_comparison_actual_must_be_extracted_value(self):
        field = self.add_api_match()["fields"][0]
        field["expected"] = field["actual"] = "2026-10-02"
        self.assert_invalid("API_ACTUAL_VALUE_CONFLICT")

    def test_mismatch_requires_review(self):
        comparison = self.add_api_match()
        comparison.update(status="MISMATCH")
        comparison["fields"][0].update(status="MISMATCH", expected="2026-10-02")
        self.assert_error("SCHEMA", "/quality/verification/apiComparison/status", "enum")

    def test_completed_notice_may_omit_unverified_items_outside_judgment_sections(self):
        # 검수 등급(2026-10-15): 서류·일정·공급 등은 근거를 못 찾은 항목을 빼고 notes에 남긴 채 완료할 수 있습니다
        quality = self.notice["quality"]
        quality["coverage"]["requiredDocuments"] = {"status": "PARTIAL", "reason": "근거를 확인하지 못한 항목을 제외했습니다."}
        quality["notes"].append({"code": "ITEM_DROPPED_NO_EVIDENCE", "target": "/requiredDocuments", "description": "서류 1개를 뺐습니다."})
        self.assert_valid()
        quality["coverage"]["eligibility"] = {"status": "PARTIAL", "reason": "근거를 확인하지 못한 항목을 제외했습니다."}
        self.assert_invalid("INCOMPLETE_EXTRACTION")

    def test_note_pointer_must_resolve(self):
        self.notice["quality"]["notes"].append({"code": "EVIDENCE_QUOTE_NOT_FOUND", "target": "/requiredDocuments/9", "description": "x"})
        self.assert_invalid("DANGLING_FIELD_POINTER")

    def test_dangling_evidence_and_source_are_rejected(self):
        for target, key, value, code in [
            (self.notice["notice"], "evidenceIds", ["missing"], "DANGLING_EVIDENCE"),
            (self.notice["evidence"][0], "sourceId", "missing", "DANGLING_SOURCE"),
        ]:
            with self.subTest(code=code):
                previous = target[key]
                target[key] = value
                self.assert_invalid(code)
                target[key] = previous

    def test_duplicate_ids_are_rejected(self):
        self.notice["supplyGroups"][0]["id"] = "building-a"
        self.assert_invalid("DUPLICATE_ID")

    def test_pdf_physical_page_must_exist(self):
        self.notice["documents"][0].update(kind="PDF", pageCount=10)
        self.notice["evidence"][0]["locator"] = {"kind": "PDF_PAGE", "page": 11, "printedPage": "9"}
        self.assert_invalid("PAGE_OUT_OF_RANGE")

    def test_page_number_zero_is_rejected(self):
        self.notice["documents"][0].update(kind="PDF", pageCount=10)
        self.notice["evidence"][0]["locator"] = {"kind": "PDF_PAGE", "page": 0, "printedPage": None}
        self.assert_error("SCHEMA", "/evidence/0/locator", "oneOf")

    def test_text_range_must_be_nonempty(self):
        self.notice["evidence"][0]["locator"].update(start=10, end=5)
        self.assert_invalid("EMPTY_TEXT_RANGE")

    def test_text_range_may_carry_pdf_page(self):
        # 쪽 표시가 있는 PDF 글자의 근거는 글자 범위에 쪽 번호를 함께 실을 수 있습니다(선택)
        self.notice["evidence"][0]["locator"].update(page=3, printedPage="1")
        self.assert_valid()
        self.notice["evidence"][0]["locator"].update(printedPage=None)
        self.assert_valid()
        self.notice["evidence"][0]["locator"].pop("printedPage")
        self.assert_valid()

    def test_text_range_page_must_be_positive_and_within_document(self):
        self.notice["evidence"][0]["locator"].update(page=0)
        self.assert_error("SCHEMA", "/evidence/0/locator", "oneOf")
        self.notice["evidence"][0]["locator"].update(page=11)
        self.notice["documents"][0].update(pageCount=10)
        self.assert_invalid("PAGE_OUT_OF_RANGE")

    def test_document_and_locator_types_must_match(self):
        self.notice["documents"][0]["kind"] = "PDF"
        self.assert_invalid("LOCATOR_SOURCE_CONFLICT")

    def test_scope_must_refer_to_existing_supply_group(self):
        self.notice["supplyGroups"][0]["scope"]["supplyGroupIds"] = ["nonexistent"]
        self.assert_invalid("DANGLING_SCOPE")

    def test_building_parent_must_be_complex(self):
        self.notice["locations"][0]["parentLocationId"] = "building-a"
        self.assert_invalid("INVALID_LOCATION_PARENT")

    def test_unknown_attribute_stays_unstructured(self):
        rule = self.notice["eligibility"][0]["rule"]
        rule["expression"]["children"][0]["attribute"] = "UNSUPPORTED_ATTRIBUTE"
        self.assert_invalid("ATTRIBUTE_UNKNOWN")
        rule.update(status="UNSTRUCTURED", expression=None, reason="지원하지 않는 조건이므로 원문을 보존합니다.")
        self.assert_valid()

    def test_eligibility_unit_must_match_attribute(self):
        self.notice["eligibility"][0]["rule"]["expression"]["children"][0]["unit"] = "KRW"
        self.assert_invalid("ATTRIBUTE_UNIT_CONFLICT")

    def test_age_integer_and_nonnegative_constraints(self):
        atom = self.notice["eligibility"][0]["rule"]["expression"]["children"][0]
        # A boolean fails the operator's generic value shape in the schema; the rest fail the dictionary.
        path = "/eligibility/0/rule/expression"
        for value, expected in (
            (19.5, ("ATTRIBUTE_VALUE_INVALID", f"{path}/children/0/value", None)),
            (-1, ("ATTRIBUTE_VALUE_INVALID", f"{path}/children/0/value", None)),
            (True, ("SCHEMA", path, "oneOf")),
        ):
            with self.subTest(value=value):
                atom["value"] = value
                self.assert_error(*expected)

    def test_attribute_operator_must_be_in_dictionary(self):
        atom = self.notice["eligibility"][0]["rule"]["expression"]["children"][0]
        atom.update(operator="IN", value=[19, 20])
        self.assert_invalid("ATTRIBUTE_OPERATOR_CONFLICT")

    def test_code_attributes_use_dictionary_pattern_and_enum(self):
        atom = self.notice["eligibility"][0]["rule"]["expression"]["children"][0]
        for attribute, value in (
            ("RESIDENCE_REGION_CODE", "41110"),
            ("BUSINESS_REGION_CODE", "4100010100"),
            ("MARITAL_STATUS", "SINGLE"),
            ("INDUSTRY_CODE", ""),
        ):
            with self.subTest(attribute=attribute):
                atom.update(attribute=attribute, unit="CODE", operator="EQ", value=value)
                self.assert_invalid("ATTRIBUTE_VALUE_INVALID")
                valid = {
                    "RESIDENCE_REGION_CODE": "4111000000",
                    "BUSINESS_REGION_CODE": "4100000000",
                    "MARITAL_STATUS": "MARRIED",
                }
                atom["value"] = valid.get(attribute, "68")
                errors = contract.validate(self.notice, "schemas/standard-notice.v1.json")
                self.assertFalse(any(e.startswith("ATTRIBUTE_") for e in errors), errors)

    def test_income_ratio_requires_benchmark(self):
        self.notice["eligibility"][2]["rule"]["expression"]["benchmark"] = None
        self.assert_invalid("BENCHMARK_REQUIRED")

    def test_attribute_checks_run_on_standalone_eligibility(self):
        data = contract.load(ROOT / "examples/eligibility.json")
        schema = "schemas/eligibility.v1.json"
        self.assertEqual([], contract.validate(data, schema))
        atoms = [node for _, node in contract.walk(data) if node.get("kind") == "ATOMIC"]
        atoms[0]["unit"] = "BOOLEAN" if atoms[0]["unit"] != "BOOLEAN" else "KRW"
        self.assert_invalid("ATTRIBUTE_UNIT_CONFLICT", data, schema)

    def test_attribute_dictionary_matches_schema_enums(self):
        self.assertEqual([], contract.dictionary_errors())
        self.assertEqual(23, len(contract.ATTRIBUTES))

    def test_between_range_order_is_checked(self):
        atom = self.notice["eligibility"][0]["rule"]["expression"]["children"][0]
        atom.update(operator="BETWEEN", value=[39, 19])
        self.assert_invalid("REVERSED_RANGE")

    def test_income_ratio_requires_reference_version_and_household_scope(self):
        benchmark = self.notice["eligibility"][2]["rule"]["expression"]["benchmark"]
        benchmark.update(referenceYear=None, referenceVersion=None, householdScope=None)
        self.assert_invalid("INCOMPLETE_INCOME_BENCHMARK")

    def test_exception_replace_requires_expression(self):
        self.notice["eligibility"][2]["exceptions"][0]["effectExpression"] = None
        self.assert_error("SCHEMA", "/eligibility/2/exceptions/0/effectExpression", "oneOf")

    def test_unreviewed_exceptions_do_not_complete(self):
        self.notice["eligibility"][0]["exceptionsStatus"] = "NOT_REVIEWED"
        self.assert_invalid("EXCEPTIONS_NOT_REVIEWED")

    def test_unit_price_period_must_match_rent_type(self):
        self.notice["supplyGroups"][0]["prices"][1]["billingPeriod"] = "ANNUAL"
        self.assert_invalid("PRICE_PERIOD_CONFLICT")

    def test_unknown_amount_is_not_zero(self):
        price = self.notice["supplyGroups"][0]["prices"][0]
        price["amountKrw"] = None
        self.assert_invalid("UNKNOWN_REASON_REQUIRED")
        self.notice["quality"]["missingFields"].append(
            {
                "target": "/supplyGroups/0/prices/0/amountKrw",
                "reason": "NOT_IN_SOURCE",
                "description": "금액이 원문에 없습니다.",
            }
        )
        self.assert_valid()
        price["amountKrw"] = 0
        self.notice["quality"]["missingFields"] = []
        self.assert_valid()  # Explicit zero is representable; source verification must establish that it is truly zero.

    def test_lease_initial_term_cannot_exceed_maximum(self):
        self.notice["supplyGroups"][0]["leaseTerm"]["maxMonths"] = 12
        self.assert_invalid("LEASE_TERM_CONFLICT")

    def test_independent_numeric_total_catches_mismatch(self):
        total = self.notice["notice"]["counts"][0]
        total.update(value=2, aggregationRole="TOTAL", aggregationComplete=True)
        child = copy.deepcopy(total)
        child.update(
            id="component", value=1, aggregationRole="COMPONENT", aggregationComplete=False, parentCountId=total["id"]
        )
        self.notice["notice"]["counts"].append(child)
        self.assert_invalid("COUNT_SUM_MISMATCH")

    def test_schedule_order_uses_actual_timezone(self):
        schedule = self.notice["schedules"][0]
        schedule["startsAt"]["value"] = "2026-10-01T10:00:00+09:00"
        schedule["endsAt"]["value"] = "2026-10-01T00:59:00Z"
        self.assert_invalid("REVERSED_SCHEDULE")

    def test_unknown_application_status_does_not_become_rolling(self):
        self.notice["applicationSummary"].update(status="UNKNOWN", basisScheduleIds=[])
        self.assert_valid()
        self.notice["applicationSummary"]["status"] = "ROLLING"
        self.assert_invalid("APPLICATION_BASIS_REQUIRED")

    def test_no_explicit_rolling_mode_cannot_claim_rolling(self):
        self.notice["applicationSummary"]["status"] = "ROLLING"
        self.assert_invalid("ROLLING_WITHOUT_EXPLICIT_CONDITION")

    def test_explicit_rolling_can_also_have_fixed_end_date(self):
        self.notice["applicationSummary"]["status"] = "ROLLING"
        self.notice["schedules"][0]["applicationMode"] = "ROLLING"
        self.assert_valid()

    def test_region_code_is_10_digit_legal_dong_code(self):
        self.notice["regionCodes"] = ["11110"]
        self.assert_error("SCHEMA", "/regionCodes/0", "pattern")

    def test_region_code_zero_fill_follows_hierarchy(self):
        location = self.notice["locations"][0]
        for code in ("0011000000", "1100010100", "1111000001"):
            with self.subTest(code=code):
                location["regionCode"] = code
                self.notice["regionCodes"] = [code]
                self.assert_invalid("REGION_CODE_HIERARCHY")

    def test_region_index_contains_location_codes(self):
        self.notice["regionCodes"] = ["4111000000"]
        self.assert_invalid("LOCATION_REGION_NOT_INDEXED")

    def test_region_index_may_use_ancestor_code(self):
        self.notice["locations"][0]["regionCode"] = "1111010100"
        for index in (["1111010100"], ["1111000000"], ["1100000000"]):
            with self.subTest(index=index):
                self.notice["regionCodes"] = index
                self.assert_valid()
        self.notice["regionCodes"] = ["1111010200"]
        self.assert_invalid("LOCATION_REGION_NOT_INDEXED")

    def test_correction_link_is_collector_supplied(self):
        source = self.notice["sourceReferences"][0]
        source["kind"] = "CORRECTION"
        self.assert_invalid("UNLINKED_RELATED_NOTICE")
        source["supersedesPostId"] = "00000000-0000-7000-8000-000000000099"
        self.assert_valid()

    def test_revision_requires_previous_snapshot_and_changed_paths(self):
        self.notice.update(noticeVersion=2, previousNoticeVersion=1, changedFields=["/schedules/0/endsAt"])
        self.assert_valid()
        self.notice["previousNoticeVersion"] = None
        self.assert_invalid("NOTICE_VERSION_CONFLICT")

    def test_removed_value_pointer_is_allowed_in_changed_fields(self):
        self.notice.update(noticeVersion=2, previousNoticeVersion=1, changedFields=["/schedules/1"])
        self.assert_valid()  # The previous persisted snapshot must resolve removals.

    def test_personal_inputs_and_ai_cost_are_not_notice_fields(self):
        for key in ("userIncome", "userAge", "userWorkplace", "aiCalls", "costUsd"):
            with self.subTest(key=key):
                self.notice[key] = 1
                self.assert_error("SCHEMA", "/", "additionalProperties")
                del self.notice[key]

    def test_private_url_is_not_a_public_original_link(self):
        self.notice["documents"][0]["originalUrl"] += "?serviceKey=synthetic-only"
        self.assert_error("PRIVATE_URL", "/documents/0/originalUrl")

    def test_private_url_parameter_names_are_normalized(self):
        document = self.notice["documents"][0]
        base = document["originalUrl"]
        for suffix in (
            "?service_key=x",
            "?Service-Key=x",
            "?AUTHKEY=x",
            "?access-token=x",
            "?X-Amz-Signature=x",
            "?X-Amz-Credential=x",
            "?key=x",
            "#access_token=x",
        ):
            with self.subTest(suffix=suffix):
                document["originalUrl"] = base + suffix
                self.assert_error("PRIVATE_URL", "/documents/0/originalUrl")
        for suffix in ("?page=2&keyword=x", "#section-2"):  # key로 시작할 뿐인 이름·일반 앵커는 공개 주소
            with self.subTest(suffix=suffix):
                document["originalUrl"] = base + suffix
                self.assert_valid()

    def test_private_url_in_plain_url_field_and_text(self):
        guide = self.notice["guidance"][0]
        guide["url"] = "https://example.org/apply?apiKey=x"  # 이름이 url인 칸도 주소 칸입니다
        self.assert_error("PRIVATE_URL", "/guidance/0/url")
        guide["url"] = "https://example.org/apply"
        guide["description"] = "https://example.org/apply?Service_Key=x 에서 신청합니다."  # 주소 칸이 아닌 글자에 섞인 인증 값
        self.assert_error("PRIVATE_URL", "/guidance/0/description")

    def test_private_url_error_hides_value(self):
        self.notice["documents"][0]["originalUrl"] += "?serviceKey=secret-value-123"
        errors = contract.validate(self.notice, "schemas/standard-notice.v1.json")
        self.assertTrue(errors)
        self.assertFalse([e for e in errors if "secret-value-123" in e], errors)

    def test_schema_errors_never_echo_input_values(self):
        # 검토 지적(2026-10-20): 주소 형식부터 틀리면 스키마 오류 메시지가 입력값(인증 값)을 그대로 담았음
        secret = "synthetic-secret-987"
        cases = [
            ("/documents/0/originalUrl", lambda n: n["documents"][0].update(originalUrl=f"not-an-absolute-url?serviceKey={secret}")),
            ("/notice/title", lambda n: n["notice"].update(title={"serviceKey": secret})),  # 잘못된 타입
            ("/notice", lambda n: n["notice"].update(extra=secret)),  # 허용되지 않은 칸의 값
            ("/notice", lambda n: n["notice"].update({f"key-{secret}": 1})),  # 칸 이름에 섞인 값
        ]
        for path, change in cases:
            with self.subTest(path=path):
                notice = copy.deepcopy(self.notice)
                change(notice)
                errors = contract.validate(notice, "schemas/standard-notice.v1.json")
                self.assertTrue([e for e in errors if e.startswith(f"SCHEMA {path}")], errors)
                self.assertFalse([e for e in errors if secret in e], errors)

    def test_schema_error_names_missing_and_extra_fields(self):
        del self.notice["notice"]["title"]
        self.notice["notice"]["extraField"] = 1
        errors = contract.validate(self.notice, "schemas/standard-notice.v1.json")
        self.assertIn("SCHEMA /notice: required: 필수 칸 없음 title", errors)
        self.assertIn("SCHEMA /notice: additionalProperties: 허용되지 않은 칸 extraField", errors)

    def test_missing_collector_detail_url_stays_null(self):
        self.notice["sourceReferences"][0]["detailUrl"] = None
        self.assert_valid()
        self.notice["sourceReferences"][0]["detailUrl"] = ""
        self.assert_error("SCHEMA", "/sourceReferences/0/detailUrl", "anyOf")

    def test_event_envelope_version_is_integer_like_raw_event(self):
        schema = EVENT
        self.assert_valid(self.event, schema)
        self.event["schemaVersion"] = "1"
        self.assert_error("SCHEMA", "/schemaVersion", "const", self.event, schema)

    def test_completed_event_outer_fields_match_detail_notice(self):
        schema = "events/extraction.completed.v1.json"
        payload = self.event["payload"]
        payload["rawVersion"] = 2
        self.assert_invalid("EVENT_NOTICE_IDENTITY_CONFLICT", self.event, schema)
        payload["rawVersion"] = 1
        payload["conditions"] = payload["conditions"][1:]
        self.assert_invalid("EVENT_CONDITIONS_CONFLICT", self.event, schema)

    def test_completed_event_conditions_match_detail_contents_not_only_ids(self):
        # 검토 지적(2026-10-20): 판정용 나이 기준만 19 → 119로 바꿔도 ID가 같아 통과했음
        schema = "events/extraction.completed.v1.json"
        self.assert_valid(self.event, schema)
        age = self.event["payload"]["conditions"][0]["rule"]["expression"]["children"][0]
        age["value"] = 119 if not isinstance(age["value"], list) else [119, *age["value"][1:]]
        self.assert_error("EVENT_CONDITION_CONTENT_CONFLICT", "/payload/conditions/0", value=self.event, schema=schema)
        self.event = contract.load(ROOT / "examples/extraction.completed.json")
        self.event["payload"]["conditions"][1]["targetGroups"] = ["다른 계층"]
        self.assert_error("EVENT_CONDITION_CONTENT_CONFLICT", "/payload/conditions/1", value=self.event, schema=schema)

    def test_completed_event_review_marks_may_differ_from_detail(self):
        # 승인 때 검수 표시만 바뀌는 것은 내용 불일치가 아닙니다
        schema = "events/extraction.completed.v1.json"
        condition = self.event["payload"]["conditions"][0]
        self.event["payload"]["reviewStatus"] = "IN_REVIEW"
        condition.update(inReview=True, reviewReasons=["MANUAL_CHECK"])
        self.assert_no_error("EVENT_CONDITION_CONTENT_CONFLICT", self.event, schema)

    def test_completed_event_region_is_five_digit_prefix_of_locations(self):
        schema = EVENT
        self.event["payload"]["regionCode"] = "1111000000"
        self.assert_error("SCHEMA", "/payload/regionCode", "anyOf", self.event, schema)
        self.event["payload"]["regionCode"] = "00110"  # 시도 자리 00은 없는 코드
        self.assert_error("REGION_CODE_HIERARCHY", "/payload/regionCode", value=self.event, schema=schema)
        self.event["payload"]["regionCode"] = "11000"  # 시도 단위 코드는 형식상 맞지만 위치(종로구)와 다름
        self.assert_no_error("REGION_CODE_HIERARCHY", self.event, schema)
        self.assert_error("EVENT_REGION_CONFLICT", "/payload/regionCode", value=self.event, schema=schema)
        self.event["payload"]["regionCode"] = "41110"
        self.assert_error("EVENT_REGION_CONFLICT", "/payload/regionCode", value=self.event, schema=schema)

    def test_completed_event_region_treats_held_location_code_as_unknown(self):
        # 보류한 위치의 지역 코드는 확정 값이 아니라 코드 없는 위치로 봅니다(알림·검색 지역으로 쓰이지 않게, 2026-10-21)
        locations = [{"regionCode": "1111000000"}, {"regionCode": "1114000000"}]
        self.assertEqual("11000", contract.event_region_code(locations))
        self.assertIsNone(contract.event_region_code(locations, ["/locations/1/regionCode"]))
        self.assertIsNone(contract.event_region_code(locations, ["/locations/1"]))
        self.assertIsNone(contract.event_region_code(locations, ["/locations"]))
        self.assertEqual("11000", contract.event_region_code(locations, ["/locations/1/address"]))

    def test_completed_event_region_rule(self):
        # 앞 5자리가 하나면 그 코드, 같은 시도의 여러 시군구·시도만 아는 위치면 시도 코드(xx000), 여러 시도·코드 없는 위치면 null
        schema = EVENT
        payload = self.event["payload"]
        locations = payload["notice"]["locations"]
        self.assertEqual("11110", payload["regionCode"])
        self.assert_valid(self.event, schema)  # 시군구 하나와 같음
        payload["regionCode"] = None
        self.assert_error("EVENT_REGION_CONFLICT", "/payload/regionCode", value=self.event, schema=schema)
        second = {**copy.deepcopy(locations[0]), "id": "building-b", "regionCode": "1114000000"}
        other_sido = {**copy.deepcopy(locations[0]), "id": "building-c", "regionCode": "4111000000"}
        for case, extra, code, expected in (
            ("같은 시도의 두 시군구", [second], "1111000000", "11000"),
            ("시도만 아는 위치", [], "1100000000", "11000"),
            ("시도만 아는 위치 + 그 시도의 시군구", [second], "1100000000", "11000"),
            ("두 시도", [other_sido], "1111000000", None),
            ("코드 없는 위치", [], None, None),
        ):
            with self.subTest(case=case):
                event = copy.deepcopy(self.event)
                notice = event["payload"]["notice"]
                notice["locations"][0]["regionCode"] = code
                notice["locations"] += extra
                if code is None:
                    notice["quality"]["missingFields"].append(
                        {"target": "/locations/0/regionCode", "reason": "NOT_IN_SOURCE", "description": "주소가 원문에 없습니다."}
                    )
                event["payload"]["regionCode"] = "11110"
                self.assert_error("EVENT_REGION_CONFLICT", "/payload/regionCode", value=event, schema=schema)
                event["payload"]["regionCode"] = expected
                self.assert_no_error("EVENT_REGION_CONFLICT", event, schema)

    def test_condition_in_review_needs_reason_and_blocks_auto_pass(self):
        schema = EVENT
        condition = self.event["payload"]["conditions"][0]
        condition["inReview"] = True
        self.assert_error("SCHEMA", "/payload/conditions/0/reviewReasons", "minItems", self.event, schema)  # 사유 없음
        self.assert_error("SCHEMA", "/payload/conditions/0/inReview", "const", self.event, schema)  # AUTO_PASSED
        condition["reviewReasons"] = ["EVIDENCE_AMBIGUOUS"]
        self.assert_error("SCHEMA", "/payload/conditions/0/inReview", "const", self.event, schema)  # AUTO_PASSED와 함께 쓸 수 없음
        self.event["payload"]["reviewStatus"] = "IN_REVIEW"
        self.assert_valid(self.event, schema)
        condition["reviewReasons"] = []
        self.assert_error("SCHEMA", "/payload/conditions/0/reviewReasons", "minItems", self.event, schema)

    def test_completed_event_without_detail_notice_only_in_review(self):
        # 상세 notice는 계약을 통과하지 못했을 때 IN_REVIEW로만 뺄 수 있습니다
        payload = self.event["payload"]
        del payload["notice"]
        self.assert_error("SCHEMA", "/payload", "required", self.event, EVENT)  # AUTO_PASSED
        for status in ("PARTIALLY_PASSED", "APPROVED"):
            with self.subTest(status=status):
                payload["reviewStatus"] = status
                self.assert_error("SCHEMA", "/payload", "required", self.event, EVENT)
        payload["reviewStatus"] = "IN_REVIEW"
        self.assert_valid(self.event, EVENT)

    def test_completed_event_without_detail_notice_still_checks_held_items(self):
        payload = self.event["payload"]
        del payload["notice"]
        payload["reviewStatus"] = "IN_REVIEW"
        item = {"extent": "ITEM", "codes": ["X"], "description": "x"}
        payload["heldItems"] = [{**item, "target": "/notice"}]  # 공고 정체성은 보류할 수 없음
        self.assert_error("HELD_TARGET_NOT_ALLOWED", "/payload/heldItems/0", value=self.event, schema=EVENT)
        payload["heldItems"] = [{**item, "target": "/eligibility/0/rule"}]  # 조건을 보류하면 그 조건은 검수 중
        self.assert_error("HELD_CONDITION_NOT_IN_REVIEW", "/payload/conditions/0", value=self.event, schema=EVENT)
        payload["conditions"][0].update(inReview=True, reviewReasons=["EXCEPTION_SUSPECTED"])
        self.assert_valid(self.event, EVENT)

    def test_publication_version_and_timestamp_formats(self):
        self.notice["applicationSummary"]["calculatedAt"] = "2026-10-15T12:00:00"
        self.assert_error("SCHEMA", "/applicationSummary/calculatedAt", "format")


    def test_area_and_price_given_only_as_ranges(self):
        # 실측: 대전도시공사 청년매입임대 정정공고 — 엑셀의 단지별 면적·임대료가 「26~45㎡」처럼 범위라 계약에 담지 못해 검수로 감
        group = self.notice["supplyGroups"][0]
        price = group["prices"][0]
        group.update(exclusiveAreaSqm=None, exclusiveAreaRange={"min": 26.0, "max": 45.5})
        price.update(amountKrw=None, amountRangeKrw={"min": 12_000_000, "max": 15_000_000}, sourceAmount="1,200만~1,500만")
        missing = self.notice["quality"]["missingFields"]
        missing[:] = [m for m in missing if m["target"] != "/supplyGroups/0/exclusiveAreaSqm"]
        errors = contract.validate(self.notice, "schemas/standard-notice.v1.json")
        self.assertFalse([e for e in errors if "RANGE" in e or "amountKrw" in e], errors)

        reversed_range = copy.deepcopy(self.notice)
        reversed_range["supplyGroups"][0]["exclusiveAreaRange"] = {"min": 45.5, "max": 26.0}
        self.assert_invalid("RANGE_REVERSED", reversed_range)
        both = copy.deepcopy(self.notice)
        both["supplyGroups"][0]["prices"][0]["amountKrw"] = 12_000_000
        self.assert_invalid("RANGE_WITH_SINGLE_VALUE", both)


    def test_partial_pass_publishes_with_held_items_only(self):
        # 부분 완료(2026-10-17): 공고는 게시하고, 검수 이슈가 있는 항목만 보류합니다(공고 수천 건을 전부 사람이 보지 않기 위해)
        event = copy.deepcopy(self.event)
        payload, notice = event["payload"], event["payload"]["notice"]
        issue = {"code": "EXCEPTION_SUSPECTED", "target": "/eligibility/0", "description": "가산 기준이 예외로 빠졌을 수 있습니다."}
        held = [{"target": "/eligibility/0", "extent": "ITEM", "codes": ["EXCEPTION_SUSPECTED"], "description": "확인 전까지 판정에 쓰지 않습니다."}]
        notice["quality"].update(reviewIssues=[issue], heldItems=held)
        notice["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
        payload.update(reviewStatus="PARTIALLY_PASSED", heldItems=held)
        payload["conditions"][0].update(inReview=True, reviewReasons=["EXCEPTION_SUSPECTED"])
        self.assertEqual([], contract.validate(event, "events/extraction.completed.v1.json"))

        open_condition = copy.deepcopy(event)
        open_condition["payload"]["conditions"][0].update(inReview=False, reviewReasons=[])
        self.assertTrue(any("HELD_CONDITION_NOT_IN_REVIEW" in e for e in contract.validate(open_condition, "events/extraction.completed.v1.json")))
        identity = copy.deepcopy(event)  # 공고 정체성 문제는 보류할 수 없고 공고 전체가 검수입니다
        identity["payload"]["notice"]["quality"]["reviewIssues"].append({"code": "NOT_A_NOTICE_SUSPECTED", "target": "/notice", "description": "x"})
        self.assertTrue(any("REVIEW_ISSUE_NOT_HELD" in e for e in contract.validate(identity, "events/extraction.completed.v1.json")))
        notice_held = copy.deepcopy(event)
        notice_held["payload"]["notice"]["quality"]["heldItems"].append({"target": "/notice", "extent": "SECTION", "codes": ["X"], "description": "x"})
        notice_held["payload"]["heldItems"] = notice_held["payload"]["notice"]["quality"]["heldItems"]
        self.assertTrue(any("HELD_TARGET_NOT_ALLOWED" in e for e in contract.validate(notice_held, "events/extraction.completed.v1.json")))
        no_list = copy.deepcopy(event)
        del no_list["payload"]["heldItems"]
        self.assertTrue(contract.validate(no_list, "events/extraction.completed.v1.json"))

    def test_non_identity_notice_fields_can_be_held_but_identity_cannot(self):
        # 2026-10-20 결정: 공고일·공급 유형·설명·대상 계층·공고 전체 수량은 칸 단위로 보류(공고는 게시), 제목·기관·분야와 /notice 전체는 공고 전체 검수
        def partial_with(target):
            event = copy.deepcopy(self.event)
            payload, notice = event["payload"], event["payload"]["notice"]
            issue = {"code": "API_MISMATCH", "target": target, "description": "API 값과 다릅니다."}
            held = [{"target": target, "extent": "ITEM", "codes": ["API_MISMATCH"], "description": "확인 전까지 쓰지 않습니다."}]
            notice["quality"].update(reviewIssues=[issue], heldItems=held)
            notice["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
            payload.update(reviewStatus="PARTIALLY_PASSED", heldItems=held)
            return contract.validate(event, "events/extraction.completed.v1.json")

        for target in ("/notice/announcedOn", "/notice/supplyType", "/notice/description", "/notice/targetGroups", "/notice/counts/0"):
            with self.subTest(target=target):
                self.assertEqual([], partial_with(target))
        for target in ("/notice", "/notice/title", "/notice/publisher", "/notice/field", "/notice/evidenceIds"):
            with self.subTest(target=target):
                self.assertTrue([e for e in partial_with(target) if e.startswith("HELD_TARGET_NOT_ALLOWED")])

    def test_partial_pass_with_api_mismatch_only_when_mismatched_field_is_held(self):
        event = copy.deepcopy(self.event)
        payload, notice = event["payload"], event["payload"]["notice"]
        source = notice["sourceReferences"][0]
        comparison = notice["quality"]["verification"]["apiComparison"]
        comparison.update(
            status="MISMATCH",
            referenceSha256="a" * 64,
            referenceIdentity={k: source[k] for k in ("sourceCode", "sourceNoticeId", "rawPostId", "rawVersion")},
            fields=[{"target": "/notice/announcedOn", "sourcePath": "/목록/PAN_NT_ST_DT", "expected": "1999-01-01", "actual": notice["notice"]["announcedOn"], "status": "MISMATCH", "reason": None}],
        )
        held = [{"target": "/notice/announcedOn", "extent": "ITEM", "codes": ["API_MISMATCH"], "description": "x"}]
        notice["quality"].update(reviewIssues=[{"code": "API_MISMATCH", "target": "/notice/announcedOn", "description": "API 공고일과 다릅니다."}], heldItems=held)
        notice["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
        payload.update(reviewStatus="PARTIALLY_PASSED", heldItems=held)
        self.assertEqual([], contract.validate(event, EVENT))
        comparison["fields"][0]["target"] = "/notice/title"  # 보류 밖의 칸이 API와 다르면 부분 게시할 수 없음
        self.assert_error("API_MISMATCH_NOT_HELD", "/quality/verification/apiComparison/fields/0", value=event, schema=EVENT)

    def test_held_part_of_condition_puts_condition_in_review(self):
        # 조건의 rule·exceptions만 보류해도 그 조건은 inReview여야 합니다(보류 범위와 조건 위치를 양쪽으로 비교)
        for target in ("/eligibility/0/rule", "/eligibility/0/exceptions", "/eligibility"):
            with self.subTest(target=target):
                event = copy.deepcopy(self.event)
                payload, notice = event["payload"], event["payload"]["notice"]
                held = [{"target": target, "extent": "ITEM", "codes": ["EXCEPTION_SUSPECTED"], "description": "x"}]
                issue = {"code": "EXCEPTION_SUSPECTED", "target": target, "description": "x"}
                notice["quality"].update(reviewIssues=[issue], heldItems=held)
                notice["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
                payload.update(reviewStatus="PARTIALLY_PASSED", heldItems=held)
                self.assert_error("HELD_CONDITION_NOT_IN_REVIEW", "/payload/conditions/0", value=event, schema=EVENT)
                for condition in payload["conditions"] if target == "/eligibility" else payload["conditions"][:1]:
                    condition.update(inReview=True, reviewReasons=["EXCEPTION_SUSPECTED"])
                self.assertEqual([], contract.validate(event, EVENT))

    def count(self, count_id, value, role="COMPONENT", parent="total", complete=False, pool=None):
        base = copy.deepcopy(self.notice["notice"]["counts"][0])
        base.update(id=count_id, value=value, aggregationRole=role, aggregationComplete=complete, allocationPoolId=pool)
        base["parentCountId"] = parent if role == "COMPONENT" else None
        return base

    def test_count_sum_counts_shared_pool_once(self):
        # 대학생·청년이 함께 쓰는 21호(같은 allocationPoolId)는 TOTAL 21이지 42가 아닙니다
        counts = self.notice["notice"]["counts"]
        counts[:] = [
            self.count("total", 21, role="TOTAL", complete=True),
            self.count("student", 21, pool="pool-1"),
            self.count("youth", 21, pool="pool-1"),
        ]
        self.assert_valid()
        counts[0]["value"] = 42
        self.assert_error("COUNT_SUM_MISMATCH", "/notice/counts/0")
        counts[0]["value"] = 21
        counts.append(self.count("elderly", 4))  # 묶음 밖 구성은 따로 더합니다
        self.assert_error("COUNT_SUM_MISMATCH", "/notice/counts/0")
        counts[0]["value"] = 25
        self.assert_valid()

    def test_incomplete_total_cannot_be_smaller_than_known_components(self):
        counts = self.notice["notice"]["counts"]
        counts[:] = [self.count("total", 5, role="TOTAL"), self.count("part", 999)]
        self.assert_error("COUNT_COMPONENTS_EXCEED_TOTAL", "/notice/counts/0")
        counts[1]["value"] = 3  # 구성을 다 모르면 전체보다 작아도 됩니다
        self.assert_valid()

    def test_partially_passed_notice_can_be_published(self):
        # 부분 게시(2026-10-19): 보류 항목만 '원문 확인 필요'로 두고 공고는 공개합니다
        self.assertEqual("APPROVED", self.notice["publicationState"])
        partial = copy.deepcopy(self.notice)
        issue = {"code": "EXCEPTION_SUSPECTED", "target": "/eligibility/0", "description": "가산 기준이 예외로 빠졌을 수 있습니다."}
        held = [{"target": "/eligibility/0", "extent": "ITEM", "codes": ["EXCEPTION_SUSPECTED"], "description": "확인 전까지 판정에 쓰지 않습니다."}]
        partial["quality"].update(reviewIssues=[issue], heldItems=held)
        partial["quality"]["verification"]["status"] = "PARTIALLY_PASSED"
        self.assert_valid(partial)

        not_held = copy.deepcopy(partial)  # 보류 범위 밖의 검수 이슈가 있으면 공개할 수 없습니다
        not_held["quality"]["reviewIssues"].append({"code": "X", "target": "/schedules/0", "description": "x"})
        self.assert_error("REVIEW_ISSUE_NOT_HELD", "/quality/reviewIssues/1", value=not_held)

        not_verified = copy.deepcopy(self.notice)
        not_verified["quality"]["verification"]["status"] = "NOT_RUN"
        self.assert_error("SCHEMA", "/quality/verification/status", "enum", value=not_verified)

    def test_shared_allocation_pool_must_be_one_value(self):
        data = contract.load(ROOT / "examples/housing.extracted.json")
        group = data["supplyGroups"][0]
        base = {"kind": "OFFERED", "scope": group["scope"], "aggregationRole": "STANDALONE", "parentCountId": None, "aggregationComplete": False,
                "evidenceIds": group["evidenceIds"], "allocationPoolId": "pool-1"}
        group["counts"] = [{**base, "id": "c-pool-a", "value": 21}, {**base, "id": "c-pool-b", "value": 21}]
        self.assertEqual([], contract.validate(data, "schemas/extracted-notice.v1.json"))
        group["counts"][1]["value"] = 42
        self.assertTrue(any("ALLOCATION_POOL_CONFLICT" in e for e in contract.validate(data, "schemas/extracted-notice.v1.json")))

    def policy_event(self, field="STARTUP_SUPPORT", status="AUTO_PASSED"):
        """정책 판정 틀만 실은 이벤트(창업지원·사업공간 모집): 상세·조건·보류 없이 틀·지역·원문 주소·상시 모집 여부."""
        event = copy.deepcopy(self.event)
        payload = event["payload"]
        for key in ("notice", "heldItems"):
            payload.pop(key, None)
        startup = field == "STARTUP_SUPPORT"
        payload.update(
            field=field,
            reviewStatus=status,
            conditions=[],
            applicationWindows=[],
            regionCode=None,
            regionCodes=[] if startup else ["11000"],
            schedule={"applyStartOn": "2026-10-07", "applyEndOn": None},
            detailUrl="https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=1",
            applyAlways=True,
        )
        payload["judgment"] = {
            "schema": "startup-support-judgment.v1" if startup else "business-space-judgment.v1",
            "rawPolicyId" if startup else "rawPostId": payload["rawPostId"],
            "rawVersion": payload["rawVersion"],
            "referenceDate": None if startup else "2026-10-07",
            "common": [],
            "groups": [{"id": "all", "name": "전체", "criteria": []}],
            "preferences": [],
            "notes": [],
        }
        return event

    def test_policy_event_carries_detail_url_and_apply_always_only_for_policies(self):
        # 리뷰 2026-10-23: 판정 목록의 정책은 공고 상세 API로 찾을 수 없어 원문 주소가, 마감일 없는 정책은 상시인지가 필요함
        for field in ("STARTUP_SUPPORT", "SPACE_RECRUITMENT"):
            event = self.policy_event(field)
            self.assert_valid(event, EVENT)
            event["payload"]["detailUrl"] = None  # 원문 주소를 모르면 null
            self.assert_valid(event, EVENT)
            for key in ("detailUrl", "applyAlways"):
                missing = self.policy_event(field)
                del missing["payload"][key]
                self.assert_error("EVENT_POLICY_FRAME_SHAPE", "/payload", value=missing, schema=EVENT)
        private = self.policy_event()
        private["payload"]["detailUrl"] = "https://example.go.kr/view?serviceKey=abc"
        self.assert_error("PRIVATE_URL", "/payload/detailUrl", value=private, schema=EVENT)
        for key, value in (("detailUrl", None), ("applyAlways", False)):
            housing = copy.deepcopy(self.event)
            housing["payload"][key] = value
            self.assert_error("EVENT_POLICY_FRAME_SHAPE", f"/payload/{key}", value=housing, schema=EVENT)

    def test_policy_event_may_carry_apply_note_but_housing_may_not(self):
        # 2026-10-28 사용자 결정: 신청 기간이 「예산 소진 시까지」인 사업은 마감일이 없어도 그 글을 달아 목록에 보여 줌
        event = self.policy_event()
        self.assert_valid(event, EVENT)  # 없어도 됨
        event["payload"]["applyNote"] = "예산 소진 시까지"
        self.assert_valid(event, EVENT)
        event["payload"]["applyNote"] = None
        self.assert_valid(event, EVENT)
        housing = copy.deepcopy(self.event)
        housing["payload"]["applyNote"] = "예산 소진 시까지"
        self.assert_error("EVENT_POLICY_FRAME_SHAPE", "/payload/applyNote", value=housing, schema=EVENT)

    def test_policy_review_status_is_decided_by_the_whole_frame_without_held_items(self):
        # 사용자 결정 2026-10-23: 일부 조건만 확인 필요면 PARTIALLY_PASSED(보류 목록 없이 조건마다 inReview), 틀 전체를 못 믿으면 IN_REVIEW
        criterion = {"kind": "BUSINESS_REGISTRATION", "id": "c1", "quote": "사업자등록을 한 자", "page": None, "inReview": True,
                     "reviewReason": "확인 필요", "asOf": None, "require": "REGISTERED"}
        for status in ("PARTIALLY_PASSED", "IN_REVIEW"):
            event = self.policy_event(status=status)
            event["payload"]["judgment"]["common"] = [criterion]
            self.assert_valid(event, EVENT)
        auto = self.policy_event()
        auto["payload"]["judgment"]["common"] = [criterion]
        self.assert_error("EVENT_POLICY_REVIEW_STATUS", "/payload/reviewStatus", value=auto, schema=EVENT)
        held = self.policy_event(status="PARTIALLY_PASSED")
        held["payload"]["heldItems"] = [{"target": "/schedules/0", "extent": "ITEM", "codes": ["X"], "description": "확인 필요"}]
        self.assert_error("EVENT_POLICY_FRAME_SHAPE", "/payload", value=held, schema=EVENT)
        # 공고는 그대로 PARTIALLY_PASSED에 보류 목록이 있어야 함
        notice = copy.deepcopy(self.event)
        notice["payload"]["reviewStatus"] = "PARTIALLY_PASSED"
        notice["payload"].pop("heldItems", None)
        self.assert_error("SCHEMA", "/payload", "required", value=notice, schema=EVENT)

    def test_schedule_place_time_days_and_channels(self):
        # 프론트 요청(2026-10-23): 접수 장소·이메일·접수 시각·쉬는 시각·제외 요일, 신청 방법은 정해진 값만
        schedule = self.notice["schedules"][0]
        schedule.update(
            places=[{"name": "가상주거공사 1층 접수처", "address": "서울특별시 종로구 가상로 1", "detail": None}],
            applicationEmail={"address": "apply@example.org", "subjectFormat": "[신청] 성명_주택형"},
            dailyHours=[{"start": "10:00", "end": "17:00"}],
            breaks=[{"start": "12:00", "end": "13:00"}],
            excludedDays=["SAT", "SUN", "HOLIDAY"],
            timeNote="마감일은 16시까지예요.",
        )
        self.assert_valid()
        schedule["kinds"] = ["VIEWING"]
        schedule["applicationMode"] = "NOT_APPLICABLE"
        self.notice["notice"]["applicationChannels"] = []
        self.notice["applicationSummary"].update(status="UNKNOWN", basisScheduleIds=[])
        self.assert_no_error("SCHEMA")

    def test_schedule_time_ranges_places_and_days_are_checked(self):
        schedule = self.notice["schedules"][0]
        schedule["dailyHours"] = [{"start": "18:00", "end": "09:00"}]
        schedule["breaks"] = [{"start": "12:00", "end": "12:00"}]
        schedule["places"] = [{"name": None, "address": None, "detail": None}]
        self.assert_error("TIME_RANGE_REVERSED", "/schedules/0/dailyHours/0")
        self.assert_error("TIME_RANGE_REVERSED", "/schedules/0/breaks/0")
        self.assert_error("EMPTY_PLACE", "/schedules/0/places/0")
        schedule["dailyHours"] = [{"start": "9:00", "end": "18:00"}]
        self.assert_error("SCHEMA", "/schedules/0/dailyHours/0/start", "pattern")
        schedule["dailyHours"] = []
        schedule["excludedDays"] = ["SAT", "SAT"]
        self.assert_error("SCHEMA", "/schedules/0/excludedDays", "uniqueItems")

    def test_channels_are_enum_and_notice_channels_follow_application_schedules(self):
        schedule = self.notice["schedules"][0]
        schedule["channels"] = ["인터넷"]
        self.assert_error("SCHEMA", "/schedules/0/channels/0", "enum")
        schedule["channels"] = ["MAIL", "ONLINE"]
        self.assert_error("APPLICATION_CHANNELS_CONFLICT", "/notice/applicationChannels")
        self.notice["notice"]["applicationChannels"] = ["ONLINE", "MAIL"]  # 정해진 순서
        self.assert_valid()
        self.assertEqual(["ONLINE", "MAIL"], contract.application_channels(self.notice))

    def test_notice_channels_follow_contract_schedules_when_there_is_no_application(self):
        # 별도 접수 없이 계약으로 바로 신청받는 선착순 공고: 신청 일정이 없으면 계약 일정의 방법을 공고 전체 신청 방법으로 셉니다
        notice = copy.deepcopy(self.notice)
        for schedule in notice["schedules"]:
            if "APPLICATION" in schedule["kinds"]:
                schedule["kinds"] = ["CONTRACT"]
                schedule["applicationMode"] = "NOT_APPLICABLE"
                schedule["channels"] = ["ONSITE"]
        self.assertEqual(["ONSITE"], contract.application_channels(notice))
        notice["schedules"][0]["kinds"] = ["APPLICATION"]
        notice["schedules"][0]["channels"] = ["MAIL"]
        self.assertEqual(["MAIL"], contract.application_channels(notice))  # 신청 일정이 하나라도 있으면 그 일정만

    def test_required_document_group_copies_and_issuer(self):
        document = self.notice["requiredDocuments"][0]
        document.update(group="PROXY_SPOUSE", copies=2, issuer="주민센터")
        self.assert_valid()
        document["copies"] = 0
        self.assert_error("SCHEMA", "/requiredDocuments/0/copies", "anyOf")
        document.update(copies=None, group="SPOUSE")
        self.assert_error("SCHEMA", "/requiredDocuments/0/group", "enum")


if __name__ == "__main__":
    unittest.main()
