"""여덟 번째 시험 채점(2026-10-24)의 일반 규칙: 잘린 응답들의 항목 모으기, 접수 방식 막는 말의 범위, 인용 번호표, 보류 범위,
주택형 이름 맞추기. 합성 자료만 씁니다. AI·네트워크 호출 없음."""

import json

from mujuthaek_extraction.extract import fill_from_cuts

# ---- 2. 잘린 응답들의 항목 모으기 ----


def doc(i, name):
    return {"id": f"d{i}", "name": name, "submissionTime": "계약 시", "quoteRefs": [f"q{i}"]}


def test_items_finished_in_an_earlier_cut_answer_are_added():
    quotes = [{"ref": f"q{i}", "documentId": "t", "text": t} for i, t in ((1, "가상 신분증"), (2, "가상 등본"), (3, "가상 초본"))]
    full = json.dumps({"quotes": quotes, "requiredDocuments": [doc(1, "가상 신분증"), doc(2, "가상 등본"), doc(3, "가상 초본")]}, ensure_ascii=False)
    first_cut = full[: full.index('"가상 초본", "submissionTime"')]  # 세 번째 서류 중간에서 잘림
    part = {"quotes": [{"ref": "q1", "documentId": "t", "text": "가상 신분증"}], "requiredDocuments": [doc(1, "가상 신분증")]}
    added = fill_from_cuts(part, [first_cut], ("requiredDocuments",))
    names = [d["name"] for d in part["requiredDocuments"]]
    assert names == ["가상 신분증", "가상 등본"] and added == 1
    new = part["requiredDocuments"][1]
    assert new["id"] == "d2~c1" or new["id"] == "d2"
    assert any(q["ref"] == "c1-q2" for q in part["quotes"]) and new["quoteRefs"] == ["c1-q2"]


# ---- 1. 접수 방식 막는 말의 범위 ----


def test_blocking_a_sub_method_does_not_block_the_whole_channel():
    from mujuthaek_extraction.assemble.details import channel_mentions

    assert "ONLINE" not in channel_mentions("인터넷 청약 (※모바일청약 불가)")[1]
    assert "ONSITE" not in channel_mentions("특별공급은 은행창구 접수 불가")[1]
    assert "ONLINE" in channel_mentions("인터넷 신청 불가")[1]


def test_channel_named_only_in_a_condition_is_kept():
    from test_round4 import assembled_extra
    from test_schedule_details import visit_schedule

    line = "2순위 접수: 인터넷 청약이 불가한 경우 가상 은행에서 접수 2026.10.05."
    schedule = visit_schedule(
        id="second",
        kinds=["APPLICATION"],
        rawLabel="2순위 접수",
        channels=["ONLINE"],
        places=[],
        dailyHours=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        quoteRefs=["second"],
    )
    result = assembled_extra([line], {"second": line}, schedules=[schedule])
    [kept] = [s for s in result.candidate["schedules"] if s["id"] == "second"]
    assert kept["channels"] == ["ONLINE"]


# ---- 3. 인용 번호표 ----


def test_quote_with_a_different_numbering_mark_is_found():
    from mujuthaek_extraction.assemble.quotes import NormalizedText, candidates

    text = "제출서류\n1) 가상 입주신청서 및 개인정보 동의서 각 1부\n2) 가상 자기소개서 및 활동 계획서 각 1부\n"
    index = NormalizedText(text)
    found, _ = candidates(text, "1. 가상 입주신청서 및 개인정보 동의서 각 1부", index)
    assert len(found) == 1 and text[found[0][0] : found[0][1]].startswith("가상 입주신청서")
    assert candidates(text, "① 가상 자기소개서 및 활동 계획서 각 1부", index)[0]


# ---- 4. 보류 범위: 주택형 코드에서 옮긴 면적 ----


def test_area_taken_from_the_lh_type_code_is_supported_by_the_code():
    from mujuthaek_extraction.verify.claims import TYPE_CODE_AREA

    assert float(TYPE_CODE_AREA.match("084.9079A")[1]) == 84.9
    assert TYPE_CODE_AREA.match("84A") is None


# ---- 5. 주택형 이름 맞추기·병합된 총 세대수 ----


def test_joined_type_code_matches_its_lettered_name():
    from mujuthaek_extraction import supply_tables as st

    assert st._same_type({"housingTypeCode": "24 24ABC"}, {"housingTypeCode": "24ABC"})
    assert not st._same_type({"housingTypeCode": "26 26AB"}, {"housingTypeCode": "26C"})


def test_total_housing_merged_over_rows_is_dropped_not_held():
    from test_supply_tables import column

    from mujuthaek_extraction import supply_tables as st

    rows = (("단지", "주택형", "모집", "총 세대수"), ("가상단지", "24A", "5", "204"), ("", "36A", "7", ""))
    cells = ((0, 1, 2, 3), (4, 5, 6, 7), (4, 8, 9, 7))  # 총 세대수 칸이 두 행에 병합
    table = st.Table("1-1", 1, "공급", rows[0], rows, cells)
    entry = {
        "table": "1-1",
        "role": "SUPPLY",
        "rowUnit": "HOUSING_TYPE",
        "complex": None,
        "columns": [column(1, "COMPLEX"), column(2, "HOUSING_TYPE"), column(3, "COUNT", ck="OFFERED"), column(4, "COUNT", ck="TOTAL_HOUSING")],
    }
    part = st.build_part([table], {"tables": [entry]}, "pdf-text")
    assert [[(c["kind"], c["value"]) for c in g["counts"]] for g in part["supplyGroups"]] == [[("OFFERED", 5)], [("OFFERED", 7)]]
    assert not [i for i in part.get(st.ISSUES_KEY) or [] if i["code"] == "COUNT_MERGED_AMBIGUOUS"]


# ---- 프론트 요청 6-3: 정해진 끝 날짜 + 조기 종료 조건 ----


def test_fixed_end_date_with_an_early_end_condition_stays_fixed():
    from mujuthaek_extraction.assemble.slips import fix_format_slips

    schedule = {
        "kinds": ["VIEWING"],
        "endsAt": {"precision": "MINUTE", "value": "2026-11-12T16:00:00+09:00"},
        "endStatus": "CONDITIONAL",
        "endCondition": "공가 소진 시 주택개방이 종료돼요.",
        "timeNote": None,
    }
    fixed = fix_format_slips({"schedules": [schedule]})["schedules"][0]
    assert (fixed["endStatus"], fixed["endCondition"], fixed["endsAt"]["value"]) == ("FIXED", None, "2026-11-12T16:00:00+09:00")
    assert fixed["timeNote"] == "공가 소진 시 주택개방이 종료돼요."
    # 끝 날짜가 없는 조건부 종료는 그대로입니다
    open_ended = {"endsAt": None, "endStatus": "CONDITIONAL", "endCondition": "예산 소진 시 마감", "timeNote": None}
    assert fix_format_slips({"schedules": [open_ended]})["schedules"][0]["endStatus"] == "CONDITIONAL"


def test_filler_reason_on_a_structured_rule_is_cleared():
    # 2026-11-05 실측 sh-311087: 다시 요청한 선정 답이 구조화한 배점 6행의 사유에 「조건을 구조화했어요.」를 적어 형식 오류로 모두 빠짐
    from mujuthaek_extraction.assemble.slips import fix_format_slips

    structured = {"id": "s1", "rule": {"status": "STRUCTURED", "reason": "조건을 구조화했어요.", "expression": {"kind": "ATOMIC"}}}
    unstructured = {"id": "s2", "rule": {"status": "UNSTRUCTURED", "reason": "조건식으로 표현할 수 없어요.", "expression": None}}
    fixed = fix_format_slips({"selectionRules": [structured, unstructured]})["selectionRules"]
    assert fixed[0]["rule"]["reason"] is None and fixed[1]["rule"]["reason"] == "조건식으로 표현할 수 없어요."
