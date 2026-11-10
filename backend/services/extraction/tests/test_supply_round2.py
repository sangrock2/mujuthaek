"""두 번째 시험 채점(2026-10-24)의 공급표 일반 규칙: 대상 한정 요금표, 표 제목에만 있는 주택형, 병합 칸 수량. 합성 표만 씁니다. AI 호출 없음."""

from test_consistency import ROW, TABLE, candidate, codes, price
from test_supply_tables import column

from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.assemble.ai_output import CODE_ISSUES


def count_table():
    rows = (("공급형", "모집"), ("31A", "10"), ("44A", "5"))
    return st.Table("2-1", 2, "■ 공급 호수", rows[0], rows, None, above=("■ 공급 호수",))


COUNT_ENTRY = {
    "table": "2-1",
    "role": "SUPPLY",
    "rowUnit": "HOUSING_TYPE",
    "complex": None,
    "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="OFFERED")],
}


def price_entry(label, key_meaning, group=None):
    return {
        "table": label,
        "role": "SUPPLY",
        "rowUnit": "HOUSING_TYPE",
        "complex": None,
        "columns": [
            column(1, key_meaning),
            column(2, "PRICE", pk="DEPOSIT", unit="원", plan="기본", stage="STANDARD", group=group),
            column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD", group=group),
        ],
    }


def issues(part, code):
    return [i["supplyGroupId"] for i in part.get(CODE_ISSUES) or [] if i["code"] == code]


def restricted_table(heading="[가상 급여 수급자가 아닌 경우] 상한 임대조건"):
    rows = (("공급형", "보증금", "월임대료"), ("31A", "3,000,000", "60,000"))
    return st.Table("3-3", 3, heading, rows[0], rows, None, above=(heading,))


def test_restricted_price_table_without_target_is_held_not_attached_as_standard():
    part = st.build_part([count_table(), restricted_table()], {"tables": [COUNT_ENTRY, price_entry("3-3", "HOUSING_TYPE")]}, "pdf-text")
    by_type = {g["housingTypeCode"]: g for g in part["supplyGroups"] if g["counts"]}
    assert by_type["31A"]["prices"] == []  # 모집 묶음의 기본 요금 자리에 들어가지 않음
    [held] = [g for g in part["supplyGroups"] if g["prices"]]
    assert not held["counts"] and issues(part, "PRICE_SCOPE_UNCERTAIN") == [held["id"]]


def test_restricted_price_table_with_target_attaches_with_that_target():
    entry = price_entry("3-3", "HOUSING_TYPE", group="가상 급여 수급자")
    part = st.build_part([count_table(), restricted_table()], {"tables": [COUNT_ENTRY, entry]}, "pdf-text")
    by_type = {g["housingTypeCode"]: g for g in part["supplyGroups"]}
    assert [(p["sourceAmount"], p["scope"]["targetGroups"]) for p in by_type["31A"]["prices"]] == [
        ("3,000,000", ["가상 급여 수급자"]),
        ("60,000", ["가상 급여 수급자"]),
    ]
    assert issues(part, "PRICE_SCOPE_UNCERTAIN") == []


def test_sale_price_cap_words_are_not_a_target_restriction():
    table = restricted_table(heading="분양가상한제 적용 주택 공급가격")
    part = st.build_part([count_table(), table], {"tables": [COUNT_ENTRY, price_entry("3-3", "HOUSING_TYPE")]}, "pdf-text")
    assert issues(part, "PRICE_SCOPE_UNCERTAIN") == []
    assert {g["housingTypeCode"]: len(g["prices"]) for g in part["supplyGroups"]}["31A"] == 2


def tier_table(title):
    rows = (("구간", "보증금", "월임대료"), ("1구간", "1,000,000", "20,000"), ("2구간", "2,000,000", "30,000"))
    return st.Table("3-2", 3, title, rows[0], rows, None, above=("(단위: 원)", title))


def test_house_type_only_in_table_title_is_given_to_its_rows():
    part = st.build_part([count_table(), tier_table("【31A】 구간별 임대조건")], {"tables": [COUNT_ENTRY, price_entry("3-2", "TARGET_GROUP")]}, "pdf-text")
    by_type = {g["housingTypeCode"]: g for g in part["supplyGroups"]}
    assert set(by_type) == {"31A", "44A"}  # 구간 행은 따로 남지 않고 31A 모집 묶음에 붙음
    assert [(p["sourceAmount"], p["scope"]["targetGroups"]) for p in by_type["31A"]["prices"]] == [
        ("1,000,000", ["1구간"]),
        ("20,000", ["1구간"]),
        ("2,000,000", ["2구간"]),
        ("30,000", ["2구간"]),
    ]
    assert by_type["44A"]["prices"] == []


def test_title_with_several_house_types_is_left_unattached_with_issue():
    part = st.build_part([count_table(), tier_table("【31A·44A】 구간별 임대조건")], {"tables": [COUNT_ENTRY, price_entry("3-2", "TARGET_GROUP")]}, "pdf-text")
    loose = [g for g in part["supplyGroups"] if not g["counts"]]
    assert len(loose) == 2 and all(g["housingTypeCode"] is None for g in loose)
    assert sorted(issues(part, "SUPPLY_TYPE_AMBIGUOUS")) == sorted(g["id"] for g in loose)
    assert all(g["prices"] == [] for g in part["supplyGroups"] if g["counts"])


def test_long_note_line_above_table_is_not_a_title():
    note = "※ 가상 31A형은 발코니 확장이 되어 있으며 임대조건은 아래 구간표에 따라 정해집니다"
    table = st.Table("3-2", 3, note, tier_table("x").columns, tier_table("x").rows, None, above=(note,))
    part = st.build_part([count_table(), table], {"tables": [COUNT_ENTRY, price_entry("3-2", "TARGET_GROUP")]}, "pdf-text")
    assert all(g["housingTypeCode"] != "31A" or g["counts"] for g in part["supplyGroups"])  # 안내 문장의 주택형은 쓰지 않음


def merged_count_table(total=None):
    rows = [("형", "구분", "건설", "모집"), ("49", "복도식", "150", "60"), ("", "중앙", "178", "")]
    cells = [(0, 1, 2, 3), (4, 5, 6, 7), (4, 8, 9, 7)]
    if total is not None:
        rows.append(("합계", "", "328", total))
        cells.append((10, 11, 12, 13))
    return st.Table("1-1", 1, "", rows[0], tuple(rows), tuple(cells))


MERGED_ENTRY = {
    "table": "1-1",
    "role": "SUPPLY",
    "rowUnit": "HOUSING_TYPE",
    "complex": None,
    "columns": [column(1, "HOUSING_TYPE"), column(2, "TARGET_GROUP"), column(3, "COUNT", ck="TOTAL_HOUSING"), column(4, "COUNT", ck="OFFERED")],
}


def test_merged_count_cell_shared_by_rows_is_held():
    part = st.build_part([merged_count_table()], {"tables": [MERGED_ENTRY]}, "pdf-text")
    groups = part["supplyGroups"]
    assert len(groups) == 2 and sorted(issues(part, "COUNT_MERGED_AMBIGUOUS")) == sorted(g["id"] for g in groups)


def test_merged_count_cell_confirmed_by_table_total_is_kept():
    part = st.build_part([merged_count_table(total="60")], {"tables": [MERGED_ENTRY]}, "pdf-text")
    assert issues(part, "COUNT_MERGED_AMBIGUOUS") == []
    wrong = st.build_part([merged_count_table(total="120")], {"tables": [MERGED_ENTRY]}, "pdf-text")
    assert len(issues(wrong, "COUNT_MERGED_AMBIGUOUS")) == 2


def test_structure_answer_standard_price_under_restricted_heading_is_suspected():
    text = TABLE.replace("[표 3-1]", "가상 생계급여 수급자 등의 상한 임대조건\n[표 3-1]")
    standard = price("DEPOSIT", 1_000_000) | {"priceStage": "STANDARD"}
    c = candidate(text=text, prices=[standard])
    c["evidence"][0]["locator"]["start"] = text.index(ROW)
    c["evidence"][0]["locator"]["end"] = text.index(ROW) + len(ROW)
    assert ("PRICE_SCOPE_UNCERTAIN", "/supplyGroups/0/prices") in codes(c, text=text)  # 가격만 보류(2026-10-24 네 번째 채점)
    targeted = candidate(text=text, prices=[price("DEPOSIT", 1_000_000, "1순위") | {"priceStage": "STANDARD"}])
    targeted["evidence"] = c["evidence"]
    assert "PRICE_SCOPE_UNCERTAIN" not in {code for code, _ in codes(targeted, text=text)}
    plain = candidate(prices=[price("DEPOSIT", 1_000_000) | {"priceStage": "STANDARD"}])
    assert "PRICE_SCOPE_UNCERTAIN" not in {code for code, _ in codes(plain)}
