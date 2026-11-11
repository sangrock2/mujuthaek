"""공급표와 가격표가 다른 표일 때 같은 단지·같은 주택형끼리만 가격을 붙입니다(supply_tables._attach_price_tables)."""

from mujuthaek_extraction import supply_tables as st


def column(n, meaning, ck=None, pk=None, unit=None, plan=None, stage=None, group=None):
    return {"column": n, "meaning": meaning, "countKind": ck, "priceKind": pk, "unit": unit, "plan": plan, "priceStage": stage, "targetGroup": group}


def two_tables(supply_rows, price_rows):
    supply = st.Table("3-4", 3, "", supply_rows[0], supply_rows, tuple(tuple(range(3 * r, 3 * r + 3)) for r in range(len(supply_rows))))
    prices = st.Table("4-1", 4, "", price_rows[0], price_rows, tuple(tuple(range(3 * r, 3 * r + 3)) for r in range(len(price_rows))))
    keys = [column(1, "COMPLEX"), column(2, "HOUSING_TYPE")]
    mapping = {
        "tables": [
            {"table": "3-4", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [*keys, column(3, "COUNT", ck="OFFERED")]},
            {"table": "4-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [*keys, column(3, "PRICE", pk="DEPOSIT", unit="원")]},
        ]
    }
    return st.build_part([supply, prices], mapping, "pdf-text")["supplyGroups"]


def summary(groups):
    return [(g["_complex"], [c["value"] for c in g["counts"]], [p["sourceAmount"] for p in g["prices"]]) for g in groups]


def test_lh_type_code_gives_area_and_price_rows_join_the_same_code_across_differently_named_complexes():
    # 실측(LH 충북혁신): 공급표 「충북혁신 A-4블록 (천년나무4)」와 가격표 「충북혁신4 (천년나무4)」는 같은 단지입니다.
    # 59A·59A-1은 면적이 같아 면적 번호로만 맞추면 서로의 가격이 섞입니다
    supply_rows = (("단지", "주택형", "모집"), ("충북혁신 A-4블록 (천년나무4)", "059.9800A (59A)", "45"), ("", "059.9800X (59A-1)", "25"))
    supply = st.Table("3-4", 3, "", supply_rows[0], supply_rows, ((0, 1, 2), (3, 4, 5), (3, 6, 7)))
    price_rows = (("단지", "주택형", "보증금"), ("충북혁신4 (천년나무4)", "059.9800A (59A)", "33,148,000"), ("", "059.9800X (59A-1)", "33,000,000"))
    prices = st.Table("4-1", 4, "", price_rows[0], price_rows, ((0, 1, 2), (3, 4, 5), (3, 6, 7)))
    keys = [column(1, "COMPLEX"), column(2, "HOUSING_TYPE")]
    mapping = {
        "tables": [
            {"table": "3-4", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [*keys, column(3, "COUNT", ck="OFFERED")]},
            {"table": "4-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [*keys, column(3, "PRICE", pk="DEPOSIT", unit="원")]},
        ]
    }
    groups = st.build_part([supply, prices], mapping, "pdf-text")["supplyGroups"]
    assert [(g["exclusiveAreaSqm"], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [(59.98, ["33,148,000"]), (59.98, ["33,000,000"])]


def test_price_row_of_a_different_complex_is_not_joined_and_is_kept():
    # 실측 재현(2026-10-20): 표마다 단지가 하나뿐이라는 이유만으로 「하늘마을 B단지」 보증금이 「가람마을 A단지」 59A에 붙고 B단지 행은 사라짐
    groups = two_tables(
        (("단지", "주택형", "모집"), ("가람마을 A단지", "59A", "45")),
        (("단지", "주택형", "보증금"), ("하늘마을 B단지", "59A", "41,000,000")),
    )
    assert summary(groups) == [("가람마을 A단지", [45], []), ("하늘마을 B단지", [], ["41,000,000"])]


def test_price_row_joins_the_supply_type_written_with_its_number_and_different_spacing():
    # 실측(2026-10-28 GH 행복주택): 공급표 「35 35A1,B1」(공급형 + 청약 구분)과 가격표 「35A1, B1」이 짝이 안 맞아 주택 표가 두 줄로 갈라짐
    groups = two_tables(
        (("단지", "주택형", "모집"), ("파주 병원 복합", "35 35A1,B1", "10")),
        (("단지", "주택형", "보증금"), ("파주 병원 복합", "35A1, B1", "30,940,000")),
    )
    assert summary(groups) == [("파주 병원 복합", [10], ["30,940,000"])]


def test_price_row_of_another_lettered_type_with_the_same_number_is_not_joined():
    groups = two_tables(
        (("단지", "주택형", "모집"), ("파주 병원 복합", "35 35A1,B1", "10")),
        (("단지", "주택형", "보증금"), ("파주 병원 복합", "35A2", "30,940,000")),
    )
    assert summary(groups) == [("파주 병원 복합", [10], []), ("파주 병원 복합", [], ["30,940,000"])]


def test_price_row_with_the_exact_same_complex_name_is_joined():
    groups = two_tables(
        (("단지", "주택형", "모집"), ("가람마을 A단지", "59A", "45")),
        (("단지", "주택형", "보증금"), ("가람마을 A단지", "59A", "41,000,000")),
    )
    assert summary(groups) == [("가람마을 A단지", [45], ["41,000,000"])]


def test_complex_names_sharing_only_a_region_or_generic_word_are_different():
    assert st._same_core("충북혁신 A-4블록 (천년나무4)", "충북혁신4 (천년나무4)")
    assert st._same_core("행복주택 가양 (가양7단지)", "가양7단지")  # 괄호 속 별칭과 다른 쪽 이름이 같음
    assert not st._same_core("가람마을 A단지", "하늘마을 B단지")
    assert not st._same_core("부산 당감", "부산 명지")  # 지역 이름만 같음
    assert not st._same_core("LH 행복주택 A단지", "LH 행복주택 B단지")  # 일반 낱말을 빼면 남는 이름이 없음


def test_price_row_matching_two_complexes_is_not_joined():
    # 「가람마을」 가격 행이 「가람마을1단지」 「가람마을2단지」 모두에 이름이 들어맞으면 어느 단지 가격인지 정할 수 없습니다
    groups = two_tables(
        (("단지", "주택형", "모집"), ("가람마을1단지", "59A", "45"), ("가람마을2단지", "59A", "30")),
        (("단지", "주택형", "보증금"), ("가람마을", "59A", "41,000,000")),
    )
    assert summary(groups) == [("가람마을1단지", [45], []), ("가람마을2단지", [30], []), ("가람마을", [], ["41,000,000"])]


def _unique_cells(rows):
    width = len(rows[0])
    return tuple(tuple(range(width * r, width * r + width)) for r in range(len(rows)))


# 2026-11-11 유료 확인 jbdc-16011 모양: 모집 표 행과 가격표 행이 둘 다 「LH 코드」·「약식 주택형」 두 칸을 적었는데, 열 의미 답이 모집 표에서는
# 약식 칸(59A)을, 가격표에서는 LH 코드 칸(059.9288A)을 주택형으로 골라 번호·코드가 맞지 않음
JBDC_SUPPLY = (
    ("번호", "주택형", "약식", "전용", "세대수"),
    ("01", "059. 9288 A", "59A", "59.9288", "83"),
    ("02", "059. 3359 B", "59B", "59.3359", "75"),
    ("03", "059. 9793 C", "59C", "59.9793", "142"),
)
JBDC_PRICE = (
    ("유형", "주택형", "약식", "보증금", "월임대료"),
    ("10년분양전환 공공임대", "059.9288A", "59A", "72,000,000", "489,000"),
    ("", "059.3359B", "59B", "72,000,000", "489,000"),
    ("", "059.9793C", "59C", "72,000,000", "489,000"),
)


def jbdc_tables(supply_rows=JBDC_SUPPLY, price_rows=JBDC_PRICE, supply_type_column=3, price_type_column=2, price_cells=None):
    supply = st.Table("4-2", 4, "", supply_rows[0], supply_rows, _unique_cells(supply_rows))
    prices = st.Table("5-1", 5, "", price_rows[0], price_rows, price_cells or _unique_cells(price_rows))
    mapping = {
        "tables": [
            {
                "table": "4-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(supply_type_column, "HOUSING_TYPE"), column(4, "AREA_EXCLUSIVE"), column(5, "COUNT", ck="OFFERED")],
            },
            {
                "table": "5-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(price_type_column, "HOUSING_TYPE"),
                    column(4, "PRICE", pk="DEPOSIT", unit="원"),
                    column(5, "PRICE", pk="MONTHLY_RENT", unit="원"),
                ],
            },
        ]
    }
    return st.build_part([supply, prices], mapping, "pdf-text")


def test_price_rows_join_count_rows_through_the_other_type_cell_of_the_row():
    # 모집 「59A」 ↔ 가격 「059.9288A」: 번호(59 ≠ 59.9288)로는 안 붙지만, 가격 행 칸 「59A」가 모집 묶음 코드와 같고(띄어쓰기만 다른
    # 「059. 9288 A」도 모집 행 칸) 맞는 모집 묶음이 하나뿐이라 그 묶음에 붙습니다. 가격의 묶음 id·scope는 모집 묶음, 근거 행은 가격표 행
    part = jbdc_tables()
    groups = part["supplyGroups"]
    assert [(g["housingTypeCode"], [c["value"] for c in g["counts"]], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [
        ("59A", [83], ["72,000,000", "489,000"]),
        ("59B", [75], ["72,000,000", "489,000"]),
        ("59C", [142], ["72,000,000", "489,000"]),
    ]
    quotes = {q["ref"]: q["text"] for q in part["quotes"]}
    first = groups[0]
    for price in first["prices"]:
        assert price["id"].startswith(first["id"] + ".price")
        assert price["scope"]["supplyGroupIds"] == [first["id"]]
        assert price["pricePlanId"].startswith(first["id"] + ".plan-")
        assert any("059.9288A" in quotes[ref] and "72,000,000" in quotes[ref] for ref in price["quoteRefs"])
    assert all(not k.startswith("_row") for g in groups for k in g)


def test_price_row_matching_two_count_rows_is_not_joined():
    # 같은 약식 「59A」를 적은 모집 행이 둘(다른 코드)이면 어느 묶음의 가격인지 몰라 잇지 않습니다(검증 V8 SUPPLY_PRICE_UNATTACHED가 검수로)
    supply_rows = (
        ("번호", "주택형", "약식", "전용", "세대수"),
        ("01", "059. 9288 A", "59A", "59.9288", "83"),
        ("02", "059. 9288 A", "59A2", "59.9288", "10"),
    )
    price_rows = (("유형", "주택형", "약식", "보증금", "월임대료"), ("공공임대", "059.9288A", "59", "72,000,000", "489,000"))
    groups = jbdc_tables(supply_rows, price_rows)["supplyGroups"]
    assert [(g["housingTypeCode"], [c["value"] for c in g["counts"]], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [
        ("59A", [83], []),
        ("59A2", [10], []),
        ("059.9288A", [], ["72,000,000", "489,000"]),
    ]


def test_price_row_is_not_mixed_into_a_count_row_that_already_has_prices():
    # 모집 묶음이 이미 제 가격을 가졌으면(같은 표의 금액 열·앞 단계에서 붙은 가격) 이 안전장치로 다른 표의 가격을 더 섞지 않습니다
    supply_rows = (("번호", "주택형", "약식", "보증금", "세대수"), ("01", "059. 9288 A", "59A", "70,000,000", "83"))
    price_rows = (("유형", "주택형", "약식", "보증금", "월임대료"), ("공공임대", "059.9288A", "59A", "72,000,000", "489,000"))
    supply = st.Table("4-2", 4, "", supply_rows[0], supply_rows, _unique_cells(supply_rows))
    prices = st.Table("5-1", 5, "", price_rows[0], price_rows, _unique_cells(price_rows))
    mapping = {
        "tables": [
            {
                "table": "4-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(3, "HOUSING_TYPE"), column(4, "PRICE", pk="DEPOSIT", unit="원"), column(5, "COUNT", ck="OFFERED")],
            },
            {
                "table": "5-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(2, "HOUSING_TYPE"), column(4, "PRICE", pk="DEPOSIT", unit="원"), column(5, "PRICE", pk="MONTHLY_RENT", unit="원")],
            },
        ]
    }
    groups = st.build_part([supply, prices], mapping, "pdf-text")["supplyGroups"]
    assert [(g["housingTypeCode"], [c["value"] for c in g["counts"]], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [
        ("59A", [83], ["70,000,000"]),
        ("059.9288A", [], ["72,000,000", "489,000"]),
    ]


def test_two_price_rows_of_one_table_for_one_count_row_are_not_joined():
    # 한 가격표의 두 행(층별 등)이 같은 모집 묶음 하나만 가리키면 어느 행이 그 묶음 가격인지 몰라 잇지 않습니다
    price_rows = (
        ("유형", "주택형", "약식", "보증금", "월임대료"),
        ("1층", "059.9288A", "59A", "70,000,000", "480,000"),
        ("2층 이상", "059.9288A-1", "59A", "72,000,000", "489,000"),
    )
    supply_rows = JBDC_SUPPLY[:2]
    groups = jbdc_tables(supply_rows, price_rows)["supplyGroups"]
    assert [(g["housingTypeCode"], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [
        ("59A", []),
        ("059.9288A", ["70,000,000", "480,000"]),
        ("059.9288A-1", ["72,000,000", "489,000"]),
    ]


def test_row_code_join_needs_the_same_type_number():
    # 칸 글이 같아도 주택형 번호의 정수 부분이 다르면(84 ↔ 59) 잇지 않습니다
    price_rows = (("유형", "주택형", "약식", "보증금", "월임대료"), ("공공임대", "084.9288A", "59A", "72,000,000", "489,000"))
    groups = jbdc_tables(JBDC_SUPPLY[:2], price_rows)["supplyGroups"]
    assert [(g["housingTypeCode"], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [("59A", []), ("084.9288A", ["72,000,000", "489,000"])]
