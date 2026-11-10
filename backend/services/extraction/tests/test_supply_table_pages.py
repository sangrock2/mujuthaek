"""PDF 공급·가격표의 머리 복원과 쪽을 넘는 이어짐(supply_tables.candidates·build_part). 실측 LH 대전대동2 분양가 표를 줄인 모양입니다."""

from types import SimpleNamespace

from mujuthaek_extraction import supply_tables as st

GIANT = "1. 공급규모 ■ 대전대동2 1블록 공공분양주택 2. 공급대상 3. 공급금액 및 납부 일정 [단위 : 원]"


def column(n, meaning, pk=None):
    return {
        "column": n,
        "meaning": meaning,
        "countKind": None,
        "priceKind": pk,
        "unit": "원" if pk else None,
        "plan": None,
        "priceStage": None,
        "targetGroup": None,
    }


def material(*pages):
    return SimpleNamespace(pdf_pages=[{"pages": [{"page": n, "blocks": blocks} for n, blocks in pages]}], sheets=())


def table(block_id, columns, rows, cells):
    return {"type": "table", "id": block_id, "columns": columns, "rows": rows, "cells": cells}


def sale_table_pages():
    # 2쪽: 열 제목이 모두 표 위 큰 제목, 첫 행이 공고 설명 한 칸, 둘째 행이 머리. 본문 빈 칸이 설명 칸(0번)과 같은 병합 번호를 받음.
    # 맨 오른쪽 열은 어디에도 글자가 없음. 3쪽: 머리 없이 이어지고 맨 왼쪽에 빈 열이 하나 더 있음
    page2 = table(
        "2-2",
        ["공급가격 등"] * 7,
        [
            [GIANT, "", "", "", "", "", ""],
            ["", "주택형", "층별", "구분", "주택가격", "계약금", ""],
            ["", "059.8900A", "1층", "기본형", "343,800,000", "10,000,000", ""],
            ["", "", "", "마이너스옵션", "313,650,000", "10,000,000", ""],
            ["", "", "2층", "기본형", "351,200,000", "10,000,000", ""],
        ],
        [[0] * 7, [0, 1, 2, 3, 4, 5, 0], [0, 10, 11, 12, 13, 14, 0], [0, 0, 0, 15, 16, 17, 0], [0, 0, 18, 19, 20, 21, 0]],
    )
    page3 = table(
        "3-1",
        [],
        [["", "", "", "", "마이너스옵션", "321,050,000", "10,000,000"], ["", "", "", "3층", "기본형", "358,700,000", "10,000,000"]],
        [[0, 1, 2, 3, 4, 5, 6], [0, 1, 2, 7, 8, 9, 10]],
    )
    return material((2, [page2]), (3, [page3]))


MAPPING = {
    "tables": [
        {
            "table": "2-2",
            "role": "SUPPLY",
            "rowUnit": "HOUSING_TYPE",
            "complex": None,
            "columns": [
                column(1, "HOUSING_TYPE"),
                column(2, "FLOOR"),
                column(3, "PLAN_NAME"),
                column(4, "PRICE", "SALE_PRICE"),
                column(5, "PRICE", "CONTRACT_PAYMENT"),
            ],
        }
    ]
}


def test_header_inside_the_table_is_recovered_and_the_wider_next_page_continues_it():
    first, second = st.candidates(sale_table_pages())
    assert first.columns == ("주택형", "층별", "구분", "주택가격", "계약금")
    assert first.rows[0] == ("059.8900A", "1층", "기본형", "343,800,000", "10,000,000")
    assert second.continues == "2-2" and second.columns == first.columns
    assert second.rows[0] == ("", "", "마이너스옵션", "321,050,000", "10,000,000")


def test_rows_split_by_plan_and_page_keep_their_housing_type_and_floor():
    tables = st.candidates(sale_table_pages())
    groups = st.build_part(tables, MAPPING, "pdf-text")["supplyGroups"]
    summary = [
        (g["housingTypeCode"], g["floor"], [(p["scope"]["description"], p["sourceAmount"]) for p in g["prices"] if p["kind"] == "SALE_PRICE"]) for g in groups
    ]
    assert summary == [
        ("059.8900A", "1층", [("기본형 요금안입니다.", "343,800,000"), ("마이너스옵션 요금안입니다.", "313,650,000")]),
        # 2층 마이너스옵션 행은 3쪽 첫 행입니다(주택형·층 칸이 쪽을 넘어 병합)
        ("059.8900A", "2층", [("기본형 요금안입니다.", "351,200,000"), ("마이너스옵션 요금안입니다.", "321,050,000")]),
        ("059.8900A", "3층", [("기본형 요금안입니다.", "358,700,000")]),
    ]
    plans = {p["pricePlanId"] for p in groups[1]["prices"] if p["kind"] == "SALE_PRICE"}
    assert len(plans) == 2


def test_narrower_next_page_line_is_not_padded_into_a_continuation():
    # 실측 LH 송산: 다음 쪽 소제목 「2 | 신청자격 및 입주자 선정기준」을 왼쪽을 채워 맞추면 「2」가 모집 수 칸에 들어갑니다
    supply = table(
        "5-2",
        ["단지", "동·호", "모집"],
        [["단지", "동·호", "모집"], ["송산", "104동 102호", "1"]],
        [[0, 1, 2], [3, 4, 5]],
    )
    heading = table("6-1", [], [["2", "신청자격 및 입주자 선정기준"]], [[0, 1]])
    assert [t.label for t in st.candidates(material((5, [supply]), (6, [heading])))] == ["5-2"]


def test_zero_price_cell_is_no_plan_and_two_housing_type_cells_are_joined():
    # 실측 LH 대구경북 엑셀: 무보증월세여부 N 행의 무보증전환임대료 「0」은 그 안이 없는 행(월임대료 0원으로 게시되면 틀린 값).
    # 실측 대전대동2: 주택형 칸 「059.8900A」와 타입 칸 「59A」를 둘 다 주택형으로 답하면 이어 써야 코드의 면적(59.89)이 남음
    rows = (("주택형", "타입", "보증금", "무보증전환임대료"), ("059.8900A", "59A", "8,831,000", "0"))
    table = st.Table("엑셀1", 0, "", rows[0], rows[1:], None)
    mapping = {
        "tables": [
            {
                "table": "엑셀1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_UNIT",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "HOUSING_TYPE"), column(3, "PRICE", "DEPOSIT"), column(4, "PRICE", "MONTHLY_RENT")],
            }
        ]
    }
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert group["housingTypeCode"] == "059.8900A 59A" and group["exclusiveAreaSqm"] == 59.89
    assert [(p["kind"], p["sourceAmount"]) for p in group["prices"]] == [("DEPOSIT", "8,831,000")]


def unit_list(rows):
    header = ("주소", "호", "보증금")
    table = st.Table("엑셀1", 0, "", header, rows, None)
    mapping = {
        "tables": [
            {
                "table": "엑셀1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_UNIT",
                "complex": None,
                "columns": [column(1, "ADDRESS"), column(2, "UNIT"), column(3, "PRICE", "DEPOSIT")],
            }
        ]
    }
    return st.build_part([table], mapping, "pdf-text")


def test_address_cells_become_one_location_per_address_and_split_same_unit_numbers():
    # 실측 LH 대구경북 엑셀 565호·주소 258곳: AI 구조 호출은 위치를 10곳만 만들어 호실이 지역에 이어지지 않음
    part = unit_list(
        (
            ("경상북도 경산시 경안로 261-1", "201", "8,831,000"),
            ("경상북도 경산시 경안로 261-1", "202", "8,900,000"),
            ("대구광역시 북구 대학로 1", "201", "9,000,000"),
        )
    )
    assert [(loc["id"], loc["address"], loc["kind"]) for loc in part["locations"]] == [
        ("loc-addr1", "경상북도 경산시 경안로 261-1", "BUILDING"),
        ("loc-addr2", "대구광역시 북구 대학로 1", "BUILDING"),
    ]
    # 호 번호가 같아도 주소가 다르면 다른 호실입니다
    assert [(g["unitLabel"], g["locationId"]) for g in part["supplyGroups"]] == [("201", "loc-addr1"), ("202", "loc-addr1"), ("201", "loc-addr2")]


def test_structure_location_with_the_same_address_is_merged_into_the_code_location():
    table_part = unit_list((("경상북도 경산시 경안로 261-1", "201", "8,831,000"),))
    ai = {
        "quotes": [{"ref": "q1", "documentId": "pdf-text", "text": "경안로 261-1"}],
        "locations": [
            {
                "id": "loc-ai",
                "kind": "BUILDING",
                "parentLocationId": None,
                "complexName": None,
                "buildingName": None,
                "address": "경상북도 경산시 경안로 261-1",
                "region": None,
                "quoteRefs": ["q1"],
            },
            {
                "id": "loc-area",
                "kind": "AREA",
                "parentLocationId": "loc-ai",
                "complexName": None,
                "buildingName": None,
                "address": None,
                "region": "경상북도",
                "quoteRefs": ["q1"],
            },
        ],
        "coverage": {"locations": {"status": "PARTIAL", "reason": "목록 일부만"}},
    }
    made = st.merge_into_structure(table_part, ai)
    assert made == {"loc-addr1"} and "locations" not in table_part
    assert [loc["id"] for loc in ai["locations"]] == ["loc-area", "loc-addr1"]
    assert ai["locations"][0]["parentLocationId"] == "loc-addr1"
    code = ai["locations"][1]
    assert all(any(q["ref"] == ref for q in ai["quotes"]) for ref in code["quoteRefs"]) and code["quoteRefs"][0].startswith("tbl-")


def named_unit_list(rows):
    header = ("주소", "호", "주택군", "보증금")
    table = st.Table("엑셀1", 0, "", header, rows, None)
    columns = [column(1, "ADDRESS"), column(2, "UNIT"), column(3, "COMPLEX"), column(4, "PRICE", "DEPOSIT")]
    mapping = {"tables": [{"table": "엑셀1", "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": None, "columns": columns}]}
    return st.build_part([table], mapping, "pdf-text")


def ai_location(id_, name, address=None):
    return {
        "id": id_,
        "kind": "COMPLEX",
        "parentLocationId": None,
        "complexName": name,
        "buildingName": None,
        "address": address,
        "region": None,
        "quoteRefs": ["q1"],
    }


def test_structure_location_with_only_the_complex_name_is_merged_into_the_code_location():
    # 실측 2026-10-26 LH 청년 매입임대 김포·포천: 구조 호출은 「김포시 구래동(더럭스나인)」(주택군 칸 이름)을 주소 없이,
    # 코드는 주소 칸으로 위치를 만들어 단지 3곳이 6곳으로 나왔어요 → 주택군 이름이 같은 코드 위치가 하나면 합칩니다
    table_part = named_unit_list(
        (
            ("경기도 김포시 김포한강10로133번길 126", "214", "김포시 구래동(더럭스나인)", "1,000,000"),
            ("경기도 김포시 김포한강10로133번길 126", "243", "김포시 구래동(더럭스나인)", "1,000,000"),
            ("경기도 포천시 포천로1585번길 8", "301", "포천시 신읍동(헤리센트)", "1,000,000"),
        )
    )
    assert [loc["complexName"] for loc in table_part["locations"]] == ["김포시 구래동(더럭스나인)", "포천시 신읍동(헤리센트)"]
    ai = {
        "quotes": [{"ref": "q1", "documentId": "pdf-text", "text": "더럭스나인"}],
        "locations": [ai_location("complex-deoreuxnine", "김포시 구래동(더럭스나인)"), ai_location("complex-hericent", "포천시 신읍동(헤리센트)")],
        "schedules": [{"id": "s1", "scope": {"locationIds": ["complex-deoreuxnine"]}}],
    }
    made = st.merge_into_structure(table_part, ai)
    assert [(loc["id"], loc["kind"], loc["address"]) for loc in ai["locations"]] == [
        ("loc-addr1", "COMPLEX", "경기도 김포시 김포한강10로133번길 126"),
        ("loc-addr2", "COMPLEX", "경기도 포천시 포천로1585번길 8"),
    ]
    assert ai["schedules"][0]["scope"]["locationIds"] == ["loc-addr1"]  # 이름 위치를 가리키던 곳도 따라와요
    assert "q1" in ai["locations"][0]["quoteRefs"]
    assert made == set()  # 합친 위치는 뒤 호출의 구조 요약에 남겨요


def test_complex_name_shared_by_two_addresses_is_not_merged():
    table_part = named_unit_list(
        (
            ("경기도 김포시 가상로 1", "101", "김포 행복단지", "1,000,000"),
            ("경기도 김포시 가상로 2", "102", "김포 행복단지", "1,000,000"),
        )
    )
    ai = {"quotes": [{"ref": "q1", "documentId": "pdf-text", "text": "김포"}], "locations": [ai_location("complex-a", "김포 행복단지")]}
    made = st.merge_into_structure(table_part, ai)
    assert [loc["id"] for loc in ai["locations"]] == ["complex-a", "loc-addr1", "loc-addr2"] and made == {"loc-addr1", "loc-addr2"}


def test_structure_supply_counts_are_kept_beside_price_only_code_groups():
    # 실측 LH 대전대동2: 코드는 층별 분양가 표만 옮겨 수량이 없고, 주택형별 공급 호수는 구조 호출이 원문에서 뽑음.
    # 구조 호출 묶음의 금액이 코드가 옮긴 금액과 같으면 겹치므로 뺍니다
    tables = st.candidates(sale_table_pages())
    table_part = st.build_part(tables, MAPPING, "pdf-text")
    assert not st.has_counts(table_part) and "주택형별 공급 호수" in st.structure_note(table_part)
    ai = {
        "quotes": [{"ref": "q1", "documentId": "pdf-text", "text": "059.8900A 59A 59.89 110 97 13"}],
        "supplyGroups": [
            {
                "id": "sg-59a",
                "housingTypeCode": "059.8900A",
                "counts": [{"id": "sg-59a.c1", "kind": "OFFERED", "value": 13, "quoteRefs": ["q1"]}],
                "prices": [{"id": "sg-59a.p1", "kind": "SALE_PRICE", "sourceAmount": "343,800,000", "quoteRefs": ["q1"]}],
                "quoteRefs": ["q1"],
            }
        ],
        "coverage": {"supplyGroups": {"status": "EXTRACTED", "reason": None}},
    }
    st.merge_into_structure(table_part, ai)
    assert "supplyGroups" not in ai and "supplyGroups" not in ai["coverage"]
    first = table_part["supplyGroups"][0]
    assert first["id"] == "sg-59a" and first["prices"] == [] and first["counts"][0]["quoteRefs"] == ["ai-q1"]
    assert any(q["ref"] == "ai-q1" for q in table_part["quotes"]) and len(table_part["supplyGroups"]) == 4


def test_balcony_option_price_table_is_not_supply_even_if_answered_so():
    # 실측 LH 대전대동2: 「5. 발코니 확장 및 추가선택품목 › ■ 발코니 확장 안내」 표를 AI가 공급표로 답해 확장비 계약금·잔금이
    # 주택의 계약금·잔금으로 자동 게시됨. 본 가격표 제목에 붙는 「발코니 확장비 별도」는 옵션 표가 아님
    text = {"type": "text", "text": "5. 발코니 확장 및 추가선택품목\n■ 발코니 확장 안내\n[단위 : 원]"}
    option = table(
        "5-1", ["주택형", "구분", "공급가격", "계약금"], [["주택형", "구분", "공급가격", "계약금"], ["059.8900A", "기본형", "6,500,000", "1,000,000"]], None
    )
    [found] = st.candidates(material((5, [text, option])))
    assert found.section == "5. 발코니 확장 및 추가선택품목 › ■ 발코니 확장 안내" and st.option_table(found)
    mapping = {
        "tables": [
            {
                "table": "5-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "PLAN_NAME"), column(3, "PRICE", "OTHER"), column(4, "PRICE", "CONTRACT_PAYMENT")],
            }
        ]
    }
    assert st.build_part([found], mapping, "pdf-text") is None
    main = st.Table("2-2", 2, "", (), (), None, None, "3. 분양가격, 발코니 확장비용 › ■ 주택분양가격(발코니 확장비, 추가선택품목 비용은 별도)")
    assert not st.option_table(main)


def test_table_without_name_column_borrows_it_from_an_identical_table():
    # 실측 LH 김해·양산 일반매각: 단지마다 같은 모양의 가격표 13개 중 하나만 1열(호)을 호실로 답해 나머지 12개 표가 빠짐
    header = ("호", "주거 전용", "분양가격 계")
    first = st.Table("2-1", 2, "", header, (("101", "58.89", "74,350,000"),), None)
    second = st.Table("3-1", 3, "", header, (("201", "59.88", "75,900,000"),), None)
    other = st.Table("4-1", 4, "", ("동", "주거 전용", "분양가격 계"), (("가동", "49.60", "60,050,000"),), None)
    values = [column(2, "AREA_EXCLUSIVE"), column(3, "PRICE", "SALE_PRICE")]
    mapping = {
        "tables": [
            {"table": "2-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": values},
            {"table": "3-1", "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": None, "columns": [column(1, "UNIT"), *values]},
            {"table": "4-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": values},  # 열 제목이 달라 빌리지 않음
        ]
    }
    groups = st.build_part([first, second, other], mapping, "pdf-text")["supplyGroups"]
    assert [(g["unitLabel"], g["prices"][0]["sourceAmount"]) for g in groups] == [("101", "74,350,000"), ("201", "75,900,000")]
