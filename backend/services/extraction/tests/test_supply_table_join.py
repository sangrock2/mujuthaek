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
