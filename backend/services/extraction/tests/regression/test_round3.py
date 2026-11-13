"""세 번째 시험 채점(2026-10-24)의 일반 규칙: 칸 단위 보류(수량·가격), 병합 칸 금액·전환 방향, 반복 폭주·잘림 뒤 바꾼 요청·나눠 부르기·
끝까지 적힌 항목 살리기, 인용 찾기의 따옴표·표 읽기 줄, 시(時) 단위 시각, 접수 시각의 시작·끝 옮기기, 막은 접수 방법, 재확인 범위·채택 기록.
합성 원문·합성 표·녹화 응답만 씁니다. AI·네트워크 호출 없음."""

import copy
import dataclasses
import json

from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.assemble.ai_output import CODE_ISSUES
from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.assemble.conversion import plan_directions
from mujuthaek_extraction.assemble.details import channel_mentions, times_in
from mujuthaek_extraction.assemble.quotes import candidates
from mujuthaek_extraction.assemble.values import to_krw
from mujuthaek_extraction.extract import GUARD_NOTE, merge_split_parts, run_extraction, runaway, salvage_truncated
from mujuthaek_extraction.model import ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.recheck import RecheckResult, _lost_details, problem_items, rejection_reason
from mujuthaek_extraction.rules.housing_notice import RULES
from mujuthaek_extraction.usage import UsageRecorder
from mujuthaek_extraction.verify import SourceBundle, verify_extraction
from tests.regression.test_details_round2 import assembled as assembled_with_lines
from tests.regression.test_details_round2 import cleared
from tests.supply.test_supply_tables import column
from tests.support.helpers import ai_part, example, source_for
from tests.verify.test_verify import assembled, clock
from tests.worker.test_schedule_details import visit_schedule

# ---- 1. 칸 단위 보류 ----


def test_count_only_issue_holds_only_the_counts_of_that_group():
    candidate, sources = assembled()
    probe = copy.deepcopy(candidate)
    probe["quality"]["reviewIssues"].append({"code": "COUNT_MERGED_AMBIGUOUS", "target": "/supplyGroups/0/counts", "description": "병합 칸 수량"})
    report = verify_extraction(probe, sources, None, clock=clock)
    quality = report.candidate["quality"]
    assert quality["verification"]["status"] == "PARTIALLY_PASSED"  # 계약 완료 조건(보류 범위 안의 이슈)도 통과
    assert [h["target"] for h in quality["heldItems"]] == ["/supplyGroups/0/counts"]  # 가격은 보류하지 않음


def test_narrow_hold_is_folded_into_a_wider_hold_of_the_same_group():
    candidate, sources = assembled()
    probe = copy.deepcopy(candidate)
    probe["quality"]["reviewIssues"] += [
        {"code": "COUNT_MERGED_AMBIGUOUS", "target": "/supplyGroups/0/counts", "description": "병합 칸 수량"},
        {"code": "SUPPLY_TYPE_AMBIGUOUS", "target": "/supplyGroups/0", "description": "주택형 여럿"},
    ]
    held = verify_extraction(probe, sources, None, clock=clock).candidate["quality"]["heldItems"]
    assert [(h["target"], sorted(h["codes"])) for h in held] == [("/supplyGroups/0", ["COUNT_MERGED_AMBIGUOUS", "SUPPLY_TYPE_AMBIGUOUS"])]


def test_code_issue_with_field_points_at_that_field():
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))
    group_id = part["supplyGroups"][0]["id"]
    part[CODE_ISSUES] = [
        {"supplyGroupId": group_id, "code": "COUNT_MERGED_AMBIGUOUS", "field": "counts", "description": "병합 칸 수량"},
        {"supplyGroupId": group_id, "code": "SUPPLY_TYPE_AMBIGUOUS", "description": "주택형 여럿"},
    ]
    targets = {i["code"]: i["target"] for i in assemble([part], source).issues}
    assert targets["COUNT_MERGED_AMBIGUOUS"] == "/supplyGroups/0/counts"
    assert targets["SUPPLY_TYPE_AMBIGUOUS"] == "/supplyGroups/0"


# ---- 1·4. 병합 칸 금액, 「N (정액)」, 전환 방향 검산 ----


def lease_table(second_sign="(+)8,000"):
    """주택형·대상·모집 칸이 전환안 보조 줄까지 세로로 병합되고, 계약금 칸 「500 (정액)」은 표 전체에 병합된 합성 임대조건표."""
    rows = (
        ("형", "대상", "모집", "보증금", "계약금", "잔금", "월임대료", "전환 한도", "전환 보증금", "전환 월임대료"),
        ("16", "가상대학생", "20", "10,200", "500 (정액)", "9,700", "51,510", "-", "-", "-"),
        ("", "", "", "", "", "", "", "(-)8,000", "2,200", "74,840"),
        ("", "가상청년", "10", "10,800", "", "10,300", "54,540", "-", "-", "-"),
        ("", "", "", "", "", "", "", second_sign, "2,800", "77,870"),
    )
    cells = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
        (10, 11, 12, 20, 14, 21, 22, 23, 24, 25),
        (10, 26, 27, 28, 14, 29, 30, 31, 32, 33),
        (10, 26, 27, 34, 14, 35, 36, 37, 38, 39),
    )
    return st.Table("4-1", 4, "(단위: 천원, 원)", rows[0], rows, cells)


LEASE_ENTRY = {
    "table": "4-1",
    "role": "SUPPLY",
    "rowUnit": "HOUSING_TYPE",
    "complex": None,
    "columns": [
        column(1, "HOUSING_TYPE"),
        column(2, "TARGET_GROUP"),
        column(3, "COUNT", ck="OFFERED"),
        column(4, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
        column(5, "PRICE", pk="CONTRACT_PAYMENT", unit="천원", plan="기본", stage="STANDARD"),
        column(6, "PRICE", pk="BALANCE", unit="천원", plan="기본", stage="STANDARD"),
        column(7, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
        column(8, "CONVERSION_LIMIT"),
        column(9, "PRICE", pk="DEPOSIT", unit="천원", plan="전환", stage="CONVERSION_DEPOSIT_UP"),
        column(10, "PRICE", pk="MONTHLY_RENT", unit="원", plan="전환", stage="CONVERSION_DEPOSIT_UP"),
    ],
}


def lease_part(second_sign="(+)8,000"):
    part = st.build_part([lease_table(second_sign)], {"tables": [LEASE_ENTRY]}, "pdf-text")
    return part, {g["scope"]["targetGroups"][0]: g for g in part["supplyGroups"]}


def test_merged_contract_payment_is_added_once_per_group_with_its_own_row_quoted():
    part, groups = lease_part()
    quotes = {q["ref"]: q["text"] for q in part["quotes"]}
    for name in ("가상대학생", "가상청년"):
        contracts = [p for p in groups[name]["prices"] if p["kind"] == "CONTRACT_PAYMENT"]
        assert len(contracts) == 1 and contracts[0]["priceStage"] == "STANDARD"  # 전환안 보조 줄에 복제하지 않음
        assert any("500 (정액)" in quotes[ref] for ref in contracts[0]["quoteRefs"])  # 값이 적힌 원래 행도 근거
    assert to_krw("500 (정액)", "천원").amount_krw == 500_000
    assert to_krw("500 (만원)", "천원").amount_krw is None  # 괄호 안 단위는 떼지 않음
    assert to_krw("500 (미정)", "천원").amount_krw is None


def stages(group):
    return {p["pricePlanId"]: p["priceStage"] for p in group["prices"]}


def test_conversion_sign_that_contradicts_the_numbers_is_corrected_by_numbers():
    part, groups = lease_part("(+)8,000")  # 부호는 증액인데 보증금이 줄고 월세가 늘어난 감액안
    assert set(stages(groups["가상청년"]).values()) == {"STANDARD", "CONVERSION_DEPOSIT_DOWN"}
    assert set(stages(groups["가상대학생"]).values()) == {"STANDARD", "CONVERSION_DEPOSIT_DOWN"}
    corrected = [i for i in part[CODE_ISSUES] if i["code"] == "CONVERSION_DIRECTION_CORRECTED"]
    assert [i["supplyGroupId"] for i in corrected] == [groups["가상청년"]["id"]] and corrected[0]["field"] == "prices"
    assert all("(보증금 감액)" in p["scope"]["description"] for p in groups["가상청년"]["prices"] if p["priceStage"] != "STANDARD")


def test_conversion_numbers_that_fit_neither_direction_hold_only_prices():
    def plan_price(plan, stage, kind, amount, unit):
        scope = {"targetGroups": [], "description": "요금안입니다."}
        return {"pricePlanId": plan, "priceStage": stage, "kind": kind, "sourceAmount": amount, "sourceUnit": unit, "scope": scope}

    prices = [
        plan_price("a", "STANDARD", "DEPOSIT", "10,000", "천원"),
        plan_price("a", "STANDARD", "MONTHLY_RENT", "50,000", "원"),
        plan_price("b", "CONVERSION_DEPOSIT_UP", "DEPOSIT", "12,000", "천원"),
        plan_price("b", "CONVERSION_DEPOSIT_UP", "MONTHLY_RENT", "60,000", "원"),
    ]
    assert plan_directions(prices) == {"b": ("CONVERSION_DEPOSIT_UP", None)}  # 보증금·월세가 함께 올라 방향을 정할 수 없음
    group = {"id": "g", "prices": prices}
    [issue] = st._direction_issues(group, "16")
    assert issue["code"] == "CONVERSION_DIRECTION_UNCERTAIN" and issue["field"] == "prices"
    assert stages(group)["b"] == "CONVERSION_DEPOSIT_UP"  # 숫자로 정할 수 없으면 바꾸지 않고 보류


# ---- 2. 반복 폭주·잘림 ----


def test_runaway_is_found_inside_string_values_only():
    row = "| 본인 직접 신청할 때 | ① 본인 신분증(주민등록증, 운전면허증, 여권만 인정) ② 본인 도장 |" * 3
    looping = json.dumps({"quotes": [{"ref": "q1", "text": row * 4}]}, ensure_ascii=False)
    assert runaway(looping)
    assert runaway('{"quotes": [{"ref": "q1", "text": "' + row * 30)  # 잘려 닫히지 않은 글
    # 항목마다 같은 JSON 틀이 되풀이되는 것은 폭주가 아님
    scope = {"level": "NOTICE", "locationIds": [], "supplyGroupIds": [], "targetGroups": [], "supplyCategory": "ALL", "resolution": "RESOLVED"}
    items = [{"id": f"d{i}", "scope": scope} for i in range(40)]
    assert runaway(json.dumps({"requiredDocuments": items})) is None


def test_image_transcription_may_be_long_but_not_looping():
    # 2026-11-05: 가격표 그림 한 장을 옮긴 글(2,000자 넘음)이 길이 규칙에 걸려 그림 판독이 통째로 버려졌습니다
    table = "".join(f"| {i}동 | 59A | {i * 37 % 900 + 100},000 | {i * 53 % 700 + 300},000 |\n" for i in range(101, 201))
    page = json.dumps({"pages": [{"image": 1, "text": table}]}, ensure_ascii=False)
    assert len(table) > 2_000
    assert runaway(page) and runaway(page, "image_text") is None
    row = "| 본인 직접 신청할 때 | ① 본인 신분증(주민등록증, 운전면허증, 여권만 인정) ② 본인 도장 |" * 3
    assert runaway(json.dumps({"pages": [{"image": 1, "text": row * 4}]}, ensure_ascii=False), "image_text")  # 반복은 그대로 폭주


def documents_part(data, ids):
    part = ai_part(data, ("requiredDocuments",))
    template = part["requiredDocuments"][0]
    part["requiredDocuments"] = [{**copy.deepcopy(template), "id": i, "name": f"{template['name']} {i}"} for i in ids]  # 이름이 같으면 결합할 때 합쳐짐
    return part


def looping_cut():
    text = "| 본인 직접 신청할 때 | ① 본인 신분증 ② 본인 도장 | 배우자가 대리 신청할 때 | ① 배우자의 신분증 |" * 400
    return ModelResponse(raw_text='{"quotes": [{"ref": "q1", "documentId": "text1", "text": "' + text, model_id="m", stop_reason=StopReason.MAX_TOKENS)


def split_script(data, documents):
    sections = {call.name: call.sections for call in (*RULES.calls, *RULES.split_calls[0][1])}
    script = {name: [json.dumps(ai_part(data, s), ensure_ascii=False)] for name, s in sections.items() if name != "conditions"}
    script["documents"] = documents
    return script


def test_retry_after_runaway_changes_the_request():
    data = example("housing")
    source = source_for("housing", data)
    good = json.dumps(ai_part(data, ("requiredDocuments",)), ensure_ascii=False)
    model = RecordedModel(split_script(data, [looping_cut(), good]))
    result = run_extraction(RULES, source.material, model)
    first, second = [r for r in model.requests if r.call_name == "documents"]
    assert GUARD_NOTE not in first.instructions and GUARD_NOTE in second.instructions  # 같은 요청을 그대로 다시 보내지 않음
    assert result.failed_calls == []
    assert [a.runaway is not None for a in result.attempts if a.call_name == "documents"] == [True, False]


def test_documents_cut_twice_are_called_again_by_table_groups():
    data = example("housing")
    source = source_for("housing", data)
    script = split_script(data, [looping_cut(), looping_cut()])
    script["documents-submit"] = [json.dumps(documents_part(data, ["submit-a"]), ensure_ascii=False)]
    script["documents-visit"] = [json.dumps(documents_part(data, ["visit-a"]), ensure_ascii=False)]
    model = RecordedModel(script)
    result = run_extraction(RULES, source.material, model)
    assert [r.call_name for r in model.requests if r.call_name.startswith("documents")] == ["documents", "documents", "documents-submit", "documents-visit"]
    [merged] = [p for p in result.parts if "requiredDocuments" in p]
    assert [d["id"] for d in merged["requiredDocuments"]] == ["submit-a", "visit-a"]
    assert merged["coverage"]["requiredDocuments"]["status"] == "EXTRACTED"
    assert result.failed_calls == [] and any("나눠 부른" in n for n in result.notes)
    candidate = assemble(result.parts, source).candidate
    assert {d["id"] for d in candidate["requiredDocuments"]} >= {"submit-a", "visit-a"}


def test_one_failed_table_group_keeps_the_other_documents_as_partial():
    data = example("housing")
    parts = [documents_part(data, ["submit-a"]), {"quotes": [], "coverage": {"requiredDocuments": {"status": "FAILED", "reason": "잘림"}}}]
    merged = merge_split_parts(parts, ("requiredDocuments",))
    assert [d["id"] for d in merged["requiredDocuments"]] == ["submit-a"]
    assert merged["coverage"]["requiredDocuments"]["status"] == "PARTIAL"  # 재확인·검수로 감
    assert merge_split_parts([parts[1], parts[1]], ("requiredDocuments",)) is None


def test_complete_items_are_salvaged_from_a_cut_response():
    data = example("housing")
    whole = documents_part(data, ["a", "b"])
    text = json.dumps(whole, ensure_ascii=False)
    cut_at = text.index('"id": "b"')  # 둘째 항목을 쓰다 잘림
    salvaged = salvage_truncated(text[:cut_at], ("requiredDocuments",))
    assert [d["id"] for d in salvaged["requiredDocuments"]] == ["a"]
    assert salvaged["coverage"]["requiredDocuments"]["status"] == "PARTIAL"
    assert salvaged["quotes"] == whole["quotes"]
    # 인용 목록 안에서 잘리면 살릴 항목이 없습니다
    assert salvage_truncated(text[: text.index('"requiredDocuments"') - 30], ("requiredDocuments",)) is None


# ---- 3. 인용 찾기: 따옴표·표 읽기 줄 ----


def test_quote_marks_and_table_aid_lines_do_not_hide_a_real_quote():
    text = (
        "| 가상 서류 | · 가상 가입증명서상 ‘납부예외’, ’미가입자‘, ’지역가입자‘인 경우 | O |\n"
        "| 본인 직접 신청할 때 | ① 본인 신분증(가상 신분증만 인정) |\n"
        "  ↳ 구분: 본인 직접 신청할 때\n"
        "| 배우자가 대리 신청할 때 | ① 배우자의 신분증 |\n"
    )
    assert candidates(text, "· 가상 가입증명서상 ‘납부예외’, ’미가입자‘, ’지역가입자’인 경우")[0]  # 짝 안 맞는 따옴표를 고쳐 씀
    assert candidates(text, "| 본인 직접 신청할 때 | ① 본인 신분증(가상 신분증만 인정) |'")[0]  # 끝에 따옴표를 덧붙임
    both = "| 본인 직접 신청할 때 | ① 본인 신분증(가상 신분증만 인정) | 배우자가 대리 신청할 때 | ① 배우자의 신분증 |"
    [(start, end)] = candidates(text, both)[0]  # 두 행 사이 읽기 줄을 건너뜀
    assert text[start:end].startswith("본인 직접") and text[start:end].endswith("배우자의 신분증")  # 범위는 원문 위치(사이 읽기 줄 포함)
    # 글자(숫자·낱말)가 다르면 여전히 찾지 못합니다
    assert not candidates(text, "| 본인 직접 신청할 때 | ② 본인 신분증(가상 신분증만 인정) |")[0]


# ---- 4. 시(時) 단위 시각, 접수 시각의 시작·끝 옮기기 ----


def test_hour_only_ranges_are_times():
    assert {720, 780} <= times_in("(점심시간 12~13시 제외)")
    assert {720, 780} <= times_in("12시~13시")
    assert times_in("1~2시간 걸려요") == set()
    line = "가상 현장 접수: 2026. 10. 5.(월) ~ 10. 6.(화) 09:00~18:00 (점심시간 12~13시 제외)"
    schedule = visit_schedule(
        id="lunch",
        places=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-06"},
        dailyHours=[{"start": "09:00", "end": "18:00"}],
        breaks=[{"start": "12:00", "end": "13:00"}],
        quoteRefs=["lunch"],
    )
    result = assembled_with_lines([line], {"lunch": line}, schedules=[schedule])
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "lunch")
    assert kept["breaks"] == [{"start": "12:00", "end": "13:00"}]  # 분 없는 「12~13시」로 확인
    assert kept["startsAt"]["value"].startswith("2026-10-05T09:00") and kept["endsAt"]["value"].startswith("2026-10-06T18:00")


def test_times_cleared_from_daily_hours_move_to_start_and_end():
    line = "가상 서류 제출: 2026. 10. 5.(월) ~ 10. 7.(수) (10:00~16:00) ※ 인터넷은 24시간 접수"
    schedule = visit_schedule(
        id="docs",
        kinds=["DOCUMENT_SUBMISSION"],
        channels=["ONLINE"],
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-07"},
        dailyHours=[{"start": "10:00", "end": "16:00"}],
        quoteRefs=["docs"],
    )
    result = assembled_with_lines([line], {"docs": line}, schedules=[schedule])
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "docs")
    assert kept["dailyHours"] == []  # 「24시간」이라 매일 같은 창구 시각이 아님
    assert kept["startsAt"] == {"precision": "MINUTE", "value": "2026-10-05T10:00:00+09:00"}
    assert kept["endsAt"] == {"precision": "MINUTE", "value": "2026-10-07T16:00:00+09:00"}


def test_night_window_is_not_moved_to_start_and_end():
    line = "가상 신청: 2026. 10. 5.(월) ~ 10. 7.(수) 17:00~10:00"
    schedule = visit_schedule(
        id="night",
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-07"},
        dailyHours=[{"start": "17:00", "end": "10:00"}],
        quoteRefs=["night"],
    )
    result = assembled_with_lines([line], {"night": line}, schedules=[schedule])
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "night")
    assert kept["startsAt"]["precision"] == "DAY" and kept["endsAt"]["precision"] == "DAY"


# ---- 6. 막은 접수 방법 ----


def test_blocked_channel_is_removed_even_if_an_exception_mentions_it():
    assert channel_mentions("※ 분실의 우려로 방문 및 일반우편은 접수 불가") == (set(), {"ONSITE"})  # 일반우편 불가는 등기 우편을 막지 않음
    assert channel_mentions("인터넷 접수가 불가능한 경우 방문 접수") == ({"ONSITE"}, set())  # 조건 말: 인터넷을 막은 것이 아님
    lines = [
        "가상 서류 제출: 2026. 10. 5.(월) ~ 10. 7.(수) 인터넷 제출 또는 등기우편 ※ 분실의 우려로 방문 및 일반우편은 접수 불가",
        "※ 시스템 장애로 인터넷 접수가 중단될 경우 현장접수 또는 등기우편으로 제출",
    ]
    schedule = visit_schedule(
        id="submit",
        kinds=["DOCUMENT_SUBMISSION"],
        channels=["ONLINE", "ONSITE", "MAIL"],
        places=[],
        dailyHours=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-07"},
        quoteRefs=["l1", "l2"],
    )
    result = assembled_with_lines(lines, {"l1": lines[0], "l2": lines[1]}, schedules=[schedule])
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "submit")
    assert kept["channels"] == ["ONLINE", "MAIL"]
    assert any("ONSITE" in d for d in cleared(result))


def test_channel_the_description_says_is_refused_is_removed():
    line = "가상 서류 제출: 2026. 10. 5.(월) ~ 10. 7.(수) 인터넷 제출, 현장 제출"
    schedule = visit_schedule(
        id="said",
        kinds=["DOCUMENT_SUBMISSION"],
        channels=["ONLINE", "ONSITE"],
        description="방문 접수는 받지 않아요.",
        places=[],
        dailyHours=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-07"},
        quoteRefs=["said"],
    )
    result = assembled_with_lines([line], {"said": line}, schedules=[schedule])
    assert next(s for s in result.candidate["schedules"] if s["id"] == "said")["channels"] == ["ONLINE"]


# ---- 5. 재확인 범위·채택 기록 ----


def test_schedule_with_cleared_detail_is_rechecked_even_if_its_quote_was_found():
    line = "가상 현장 접수: 2026. 10. 5.(월) ~ 10. 6.(화) 가상주거센터"
    schedule = visit_schedule(
        id="found",
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-06"},
        dailyHours=[{"start": "10:00", "end": "16:00"}],  # 인용에 시각이 없어 지워짐(인용 자체는 찾음)
        quoteRefs=["found"],
    )
    data = example("housing")
    source = source_for("housing", data)
    material = dataclasses.replace(source.material, text=f"{source.material.text}\n{line}")
    part = copy.deepcopy(ai_part(data))
    part["quotes"].append({"ref": "found", "documentId": "text1", "text": line})
    part["schedules"].append(schedule)
    candidate = assemble([part], dataclasses.replace(source, material=material)).candidate
    assert not any(i["code"] == "EVIDENCE_QUOTE_NOT_FOUND" for i in candidate["quality"]["reviewIssues"])  # 인용은 찾음
    assert "found" in _lost_details(candidate)
    report = verify_extraction(candidate, SourceBundle.from_material(material), None, clock=clock)
    assert any(p.startswith("DETAIL_UNVERIFIED_CLEARED") for p in problem_items(report)[("schedules", "found")])


def test_rejection_reason_names_new_problems_and_is_recorded_in_usage():
    candidate, sources = assembled()
    first = verify_extraction(candidate, sources, None, clock=clock)
    worse = copy.deepcopy(candidate)
    worse["quality"]["reviewIssues"].append({"code": "VALUE_NOT_IN_QUOTE", "target": "/eligibility/0/rule", "description": "x"})
    second = verify_extraction(worse, sources, None, clock=clock)
    reason = rejection_reason(first, second, ["eligibility"])
    assert reason.startswith("새 문제: VALUE_NOT_IN_QUOTE eligibility/")
    assert rejection_reason(first, first, ["schedules"]) == "다시 본 섹션(schedules)의 문제가 줄지 않음"
    result = RecheckResult([], first, ["eligibility/x", "schedules/y"], True, None, ("schedules",), (("전체", reason), ("eligibility", reason)))
    usage = UsageRecorder()
    usage.record("recheck", result.summary())
    recorded = usage.summary()["recheck"]
    assert recorded["adoptedSections"] == ["schedules"] and [r["scope"] for r in recorded["rejected"]] == ["전체", "eligibility"]


def test_stream_aborted_runaway_is_retried_like_a_cut():
    # 스트리밍 호출이 받는 도중 끊은 응답(RUNAWAY)도 잘림처럼 바꾼 요청으로 다시 받습니다
    data = example("housing")
    source = source_for("housing", data)
    good = json.dumps(ai_part(data, ("requiredDocuments",)), ensure_ascii=False)
    aborted = dataclasses.replace(looping_cut(), stop_reason=StopReason.RUNAWAY)
    model = RecordedModel(split_script(data, [aborted, good]))
    result = run_extraction(RULES, source.material, model)
    first, second = [r for r in model.requests if r.call_name == "documents"]
    assert GUARD_NOTE not in first.instructions and GUARD_NOTE in second.instructions
    assert result.failed_calls == []
