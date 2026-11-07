"""공급·가격 표를 코드가 행 단위로 옮기기(supply_tables, 구조 방식 2026-10-17). AI는 표마다 열 의미만 답합니다."""

import copy
import json
from dataclasses import replace

from events import raw_event
from helpers import ai_part, example
from test_pdf_reader import attachment, merged_table_pdf

from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.extract import run_extraction
from mujuthaek_extraction.intake import InMemorySourceReader, build_intake
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.rules.housing_notice import RULES
from mujuthaek_extraction.verify.verifier import DROPPED_VALUE_CODES, is_note


def column(n, meaning, ck=None, pk=None, unit=None, plan=None, stage=None, group=None):
    return {"column": n, "meaning": meaning, "countKind": ck, "priceKind": pk, "unit": unit, "plan": plan, "priceStage": stage, "targetGroup": group}


def material():
    data = merged_table_pdf()
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    return build_intake(event, InMemorySourceReader(files={"raw/x/notice.pdf": data}), table_labels=True).material


MAPPING = {
    "tables": [
        {
            "table": "1-1",
            "role": "SUPPLY",
            "rowUnit": "HOUSING_TYPE",
            "complex": None,
            "columns": [
                column(1, "HOUSING_TYPE"),
                column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
                column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
                column(4, "COUNT", ck="TOTAL_HOUSING"),
            ],
        }
    ]
}


def test_rows_are_copied_by_code_from_cells_with_merged_labels_and_row_quotes():
    source = material()
    [table] = st.candidates(source)
    assert table.label == "1-1" and table.columns[:2] == ("Type", "Deposit › Total")
    part = st.build_part([table], MAPPING, source.text_document_id)
    groups = part["supplyGroups"]
    assert [g["housingTypeCode"] for g in groups] == ["39A", "46B"]  # 세로 병합 「39A」 두 행은 한 묶음
    assert [(p["kind"], p["sourceAmount"], p["sourceUnit"]) for p in groups[0]["prices"]] == [
        ("DEPOSIT", "9,330", "천원"),
        ("MONTHLY_RENT", "82,630", "원"),
        ("DEPOSIT", "10,100", "천원"),
        ("MONTHLY_RENT", "90,000", "원"),
    ]
    assert [(c["kind"], c["value"]) for c in groups[0]["counts"]] == [("TOTAL_HOUSING", 25)] and groups[1]["counts"][0]["value"] == 7
    assert all(q["text"] in source.text and q["text"].startswith("| ") for q in part["quotes"])  # 인용은 원문 표 행 그대로
    assert part["coverage"] == {"supplyGroups": {"status": "EXTRACTED", "reason": None}}


def test_shared_count_cell_becomes_one_pool_and_conversion_rows_split_by_sign():
    # 실측(인천 행복주택): 대학생·청년이 한 칸의 「금회 모집 20」을 함께 쓰고, 전환안은 한도 칸의 부호로 증액·감액이 나뉨
    rows = (
        ("형", "대상", "금회 모집", "보증금", "월세", "전환 한도", "전환 보증금", "전환 월세"),
        ("18", "대학생", "20", "21,062", "87,600", "(+)5,000", "26,062", "62,600"),
        ("", "", "", "", "", "(-)16,000", "5,062", "134,200"),
        ("", "청년", "", "22,302", "92,800", "(+)6,000", "28,302", "62,800"),
    )
    cells = ((0, 1, 2, 3, 4, 5, 6, 7), (8, 9, 10, 11, 12, 13, 14, 15), (8, 9, 10, 11, 12, 16, 17, 18), (8, 19, 10, 20, 21, 22, 23, 24))
    table = st.Table("3-1", 3, "□ 임대조건", rows[0], rows, cells)
    mapping = {
        "tables": [
            {
                "table": "3-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "화수정원마을 1단지",
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "TARGET_GROUP"),
                    column(3, "COUNT", ck="OFFERED"),
                    column(4, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
                    column(5, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
                    column(6, "CONVERSION_LIMIT"),
                    column(7, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
                    column(8, "PRICE", pk="MONTHLY_RENT", unit="원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
                ],
            }
        ]
    }
    part = st.build_part([table], mapping, "pdf-text")
    student, youth = part["supplyGroups"]
    assert student["scope"]["targetGroups"] == ["대학생"] and youth["scope"]["targetGroups"] == ["청년"]
    [a], [b] = student["counts"], youth["counts"]
    assert (a["value"], b["value"]) == (20, 20) and a["allocationPoolId"] == b["allocationPoolId"] is not None  # 한 물량, 합산하지 않음
    stages = [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in student["prices"]]
    assert stages == [
        ("DEPOSIT", "21,062", "STANDARD"),
        ("MONTHLY_RENT", "87,600", "STANDARD"),
        ("DEPOSIT", "26,062", "CONVERSION_DEPOSIT_UP"),
        ("MONTHLY_RENT", "62,600", "CONVERSION_DEPOSIT_UP"),
        ("DEPOSIT", "5,062", "CONVERSION_DEPOSIT_DOWN"),  # 위 행의 기본 가격을 되풀이하지 않음
        ("MONTHLY_RENT", "134,200", "CONVERSION_DEPOSIT_DOWN"),
    ]
    assert not any("(+)" in p["sourceAmount"] or "5,000" == p["sourceAmount"] for p in student["prices"])  # 전환 한도 칸은 가격 아님
    up, down = {p["pricePlanId"] for p in student["prices"][2:4]}, {p["pricePlanId"] for p in student["prices"][4:]}
    assert len(up) == len(down) == 1 and up != down  # 같은 안의 보증금·월세는 같은 요금안 ID
    st.link_locations(
        part,
        [
            {"id": "loc-1", "kind": "COMPLEX", "complexName": "화수정원마을1단지", "buildingName": None},
            {"id": "loc-2", "kind": "COMPLEX", "complexName": "만부마을", "buildingName": None},
        ],
    )
    assert student["locationId"] == youth["locationId"] == "loc-1" and "_complex" not in student


def structure_answer(source, sections=("notice", "locations")):
    part = ai_part(example("housing"), sections)
    for quote in part["quotes"]:
        quote["documentId"] = source.text_document_id  # 인용 문서 ID는 이 자료의 ID만 허용됩니다
    return json.dumps(part, ensure_ascii=False)


def test_merged_type_cell_with_two_area_rows_makes_two_groups_and_building_column_is_not_the_complex():
    # 실측(2026-10-18 LH 철원갈말): 「24A」 한 칸 아래 24.59㎡ 8호·24.66㎡ 12호, 「해당동 101 102」 열, 가격표는 24A 한 행
    rows = (
        ("형", "건설 호수", "전용", "대기", "모집", "해당동"),
        ("24A", "8", "24.59", "0", "20", "101 102"),
        ("", "12", "24.66", "", "", ""),
    )
    cells = ((0, 1, 2, 3, 4, 5), (6, 7, 8, 9, 10, 11), (6, 12, 13, 9, 10, 11))
    supply = st.Table("1-3", 1, "■ 형별 공급계획", rows[0], rows, cells)
    price_rows = (("형", "보증금", "월세"), ("24A", "2,343,000", "46,630"))
    prices = st.Table("2-1", 2, "■ 임대조건", price_rows[0], price_rows, ((0, 1, 2), (3, 4, 5)))
    mapping = {
        "tables": [
            {
                "table": "1-3",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "철원갈말",
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "COUNT", ck="TOTAL_HOUSING"),
                    column(3, "AREA_EXCLUSIVE"),
                    column(4, "COUNT", ck="WAITLIST"),
                    column(5, "COUNT", ck="OFFERED"),
                    column(6, "BUILDING"),
                ],
            },
            {
                "table": "2-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "철원갈말",
                "columns": [column(1, "HOUSING_TYPE"), column(2, "PRICE", pk="DEPOSIT", unit="원"), column(3, "PRICE", pk="MONTHLY_RENT", unit="원")],
            },
        ]
    }
    groups = st.build_part([supply, prices], mapping, "pdf-text")["supplyGroups"]
    assert [(g["exclusiveAreaSqm"], [c["value"] for c in g["counts"] if c["kind"] == "TOTAL_HOUSING"]) for g in groups] == [(24.59, [8]), (24.66, [12])]
    assert all([p["sourceAmount"] for p in g["prices"]] == ["2,343,000", "46,630"] for g in groups)  # 가격표 한 행이 두 묶음 모두에
    offered = [c for g in groups for c in g["counts"] if c["kind"] == "OFFERED"]
    assert len(offered) == 2 and offered[0]["allocationPoolId"] == offered[1]["allocationPoolId"] is not None  # 병합 칸 한 물량


def test_conversion_cell_holding_up_and_down_amounts_is_split_by_both_signs():
    # 실측(2026-10-18 LH 포항 행복주택): 한도 칸 「(+) - (-) 10,000」, 전환 보증금 칸 「12,614 2,614」, 전환 월세 칸 「57,810 86,970」
    rows = (("형", "보증금", "월세", "한도", "전환 보증금", "전환 월세"), ("21A", "12,614", "57,810", "(+) - (-) 10,000", "12,614 2,614", "57,810 86,970"))
    table = st.Table("6-1", 6, "임대조건", rows[0], rows, ((0, 1, 2, 3, 4, 5), (6, 7, 8, 9, 10, 11)))
    mapping = {
        "tables": [
            {
                "table": "6-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "포항",
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
                    column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
                    column(4, "CONVERSION_LIMIT"),
                    column(5, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
                    column(6, "PRICE", pk="MONTHLY_RENT", unit="원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
                ],
            }
        ]
    }
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    # 「(+) -」 쪽 금액(12,614 / 57,810)은 기본과 같아 증액 전환이 없는 것이므로 증액안을 만들지 않습니다(2026-10-24 네 번째 채점)
    assert [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in group["prices"]] == [
        ("DEPOSIT", "12,614", "STANDARD"),
        ("MONTHLY_RENT", "57,810", "STANDARD"),
        ("DEPOSIT", "2,614", "CONVERSION_DEPOSIT_DOWN"),
        ("MONTHLY_RENT", "86,970", "CONVERSION_DEPOSIT_DOWN"),
    ]


def test_two_target_columns_are_joined_and_price_rows_attach_only_to_the_same_target():
    # 실측(2026-10-18 LH 포항 행복주택): 대상 칸 「청년」|「소득無」 중 마지막만 남고, 전세보증금 표의 계층별 행이 21A 묶음마다 모두 붙음
    supply_rows = (("형", "대상", "세부", "호수"), ("21A", "청년", "소득無", "107"), ("", "", "소득有", ""))
    supply = st.Table("6-1", 6, "임대조건", supply_rows[0], supply_rows, ((0, 1, 2, 3), (4, 5, 6, 7), (4, 5, 8, 7)))
    lease_rows = (("형", "대상", "세부", "전세보증금"), ("21A", "청년", "소득無", "24,176,000"), ("", "", "소득有", "25,598,000"))
    lease = st.Table("7-1", 7, "전세", lease_rows[0], lease_rows, ((0, 1, 2, 3), (4, 5, 6, 7), (4, 5, 8, 9)))
    target = [column(2, "TARGET_GROUP"), column(3, "TARGET_GROUP")]
    mapping = {
        "tables": [
            {
                "table": "6-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "포항",
                "columns": [column(1, "HOUSING_TYPE"), *target, column(4, "COUNT", ck="OFFERED")],
            },
            {
                "table": "7-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": "포항",
                "columns": [column(1, "HOUSING_TYPE"), *target, column(4, "PRICE", pk="DEPOSIT", unit="원", plan="전세")],
            },
        ]
    }
    groups = st.build_part([supply, lease], mapping, "pdf-text")["supplyGroups"]
    assert [g["scope"]["targetGroups"] for g in groups] == [["청년 소득無"], ["청년 소득有"]]
    assert [[p["sourceAmount"] for p in g["prices"]] for g in groups] == [["24,176,000"], ["25,598,000"]]


def test_price_rows_attach_when_the_two_tables_name_the_same_class_differently():
    # 실측(LH 인천석남 행복주택): 공급표는 「대학생」「청년」「고령자 (주거약자용外)」, 임대조건표는 「대학생· 청년(소득無)」
    # 「청년(소득有)」「고령자」라 가격이 모집 수 없는 묶음으로 따로 남음. 소득 없는 청년은 대학생 조건을 받으므로 청년 묶음에는 두 조건이 다 붙습니다
    supply_rows = (
        ("형", "계층", "호수"),
        ("21A", "대학생", "5"),
        ("", "청년", "23"),
        ("26AS", "고령자 (주거약자용)", "5"),
        ("26B", "고령자 (주거약자용外)", "1"),
    )
    supply = st.Table("1-7", 1, "임대대상", supply_rows[0], supply_rows, ((0, 1, 2), (3, 4, 5), (3, 6, 7), (8, 9, 10), (11, 12, 13)))
    lease_rows = (
        ("형", "계층", "보증금"),
        ("21A", "대학생· 청년(소득無)", "32,708,000"),
        ("", "청년(소득有)", "34,632,000"),
        ("26AS", "고령자 (주거약자용)", "45,790,000"),
        ("26B", "고령자", "45,790,000"),
    )
    lease = st.Table("2-1", 2, "임대조건", lease_rows[0], lease_rows, ((0, 1, 2), (3, 4, 5), (3, 6, 7), (8, 9, 10), (11, 12, 13)))
    mapping = {
        "tables": [
            {
                "table": "1-7",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "TARGET_GROUP"), column(3, "COUNT", ck="OFFERED")],
            },
            {
                "table": "2-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "TARGET_GROUP"), column(3, "PRICE", pk="DEPOSIT", unit="원", plan="기본")],
            },
        ]
    }
    groups = st.build_part([supply, lease], mapping, "pdf-text")["supplyGroups"]
    assert [(g["housingTypeCode"], g["scope"]["targetGroups"], sorted(p["sourceAmount"] for p in g["prices"])) for g in groups] == [
        ("21A", ["대학생"], ["32,708,000"]),
        ("21A", ["청년"], ["32,708,000", "34,632,000"]),
        ("26AS", ["고령자 (주거약자용)"], ["45,790,000"]),
        ("26B", ["고령자 (주거약자용外)"], ["45,790,000"]),
    ]


def test_headerless_table_at_top_of_next_page_continues_the_mapped_table():
    # 실측(LH 청주지북 공공분양): 분양가 표 55A·55A-1 행 뒤 55B~59C 행이 다음 쪽 머리 없는 표로 읽혀 분양가 55개가 빠짐
    from types import SimpleNamespace

    pages = [
        {
            "page": 2,
            "blocks": [
                {
                    "type": "table",
                    "id": "2-5",
                    "columns": ["타입", "층별", "주택가격"],
                    "rows": [["55A", "1층", "288,580"], ["", "2층", "291,650"]],
                    "cells": [[0, 1, 2], [0, 3, 4]],
                }
            ],
        },
        {
            "page": 3,
            "blocks": [
                {"type": "table", "id": "3-1", "columns": [], "rows": [["55B", "1층", "288,620"], ["", "2층", "291,690"]], "cells": [[0, 1, 2], [0, 3, 4]]}
            ],
        },
        {"page": 4, "blocks": [{"type": "table", "id": "4-1", "columns": [], "rows": [["※ 안내", "1", "비고"]]}]},  # 숫자 칸이 다르면 이어짐이 아님
    ]
    tables = st.candidates(SimpleNamespace(pdf_pages=[{"pages": pages}]))
    assert [(t.label, t.continues) for t in tables] == [("2-5", None), ("3-1", "2-5")]
    mapping = {
        "tables": [
            {
                "table": "2-5",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "FLOOR"), column(3, "PRICE", pk="SALE_PRICE", unit="천원", plan="분양가")],
            }
        ]
    }
    groups = st.build_part(tables[:2], mapping, "pdf-text")["supplyGroups"]
    assert sorted({g["housingTypeCode"] for g in groups}) == ["55A", "55B"]
    assert sorted(p["sourceAmount"] for g in groups if g["housingTypeCode"] == "55B" for p in g["prices"]) == ["288,620", "291,690"]


def test_price_rows_named_only_by_complex_attach_to_the_one_count_group_of_that_complex():
    # 2026-11-06 V2 5건 재측정 bmc-106: 단지별 모집표와 단지별 임대조건표가 나뉘어(주택형·면적 칸 없음) 모집 묶음은 가격 없이,
    # 가격 묶음은 모집 수 없이 남아 가격 빈칸 8개로 보류됨. 같은 이름의 모집 묶음이 둘 이상이면 어느 주택형 가격인지 몰라 붙이지 않습니다
    def tables(count_rows):
        counts = st.Table("1-1", 1, "모집 현황", count_rows[0], count_rows, tuple(tuple(range(3 * r, 3 * r + 3)) for r in range(len(count_rows))))
        lease_rows = (("단지명", "임대보증금(원)", "월임대료(원)"), ("동삼2", "2,160,000", "42,800 ~49,600"), ("다대4", "2,150,000", "47,900"))
        lease = st.Table("2-1", 2, "임대조건", lease_rows[0], lease_rows, tuple(tuple(range(3 * r, 3 * r + 3)) for r in range(len(lease_rows))))
        return [counts, lease]

    mapping = {
        "tables": [
            {"table": "1-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [column(1, "COMPLEX"), column(3, "COUNT", ck="OFFERED")]},
            {
                "table": "2-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "COMPLEX"), column(2, "PRICE", pk="DEPOSIT", unit="원"), column(3, "PRICE", pk="MONTHLY_RENT", unit="원")],
            },
        ]
    }
    one_each = (("단지명", "주택형", "모집 세대수"), ("동삼2", "-", "300"), ("다대4", "-", "600"))
    groups = st.build_part(tables(one_each), mapping, "pdf-text")["supplyGroups"]
    assert [(g["_complex"], [c["value"] for c in g["counts"]], [p["sourceAmount"] for p in g["prices"]]) for g in groups] == [
        ("동삼2", [300], ["2,160,000", "42,800 ~49,600"]),
        ("다대4", [600], ["2,150,000", "47,900"]),
    ]
    assert all(p["scope"]["description"] and "전용" not in p["scope"]["description"] for g in groups for p in g["prices"])  # 면적으로 나누지 않음
    two_types = (("단지명", "주택형", "모집 세대수"), ("동삼2", "A", "100"), ("동삼2", "B", "200"), ("다대4", "-", "600"))
    mapping["tables"][0]["columns"].insert(1, column(2, "HOUSING_TYPE"))
    groups = st.build_part(tables(two_types), mapping, "pdf-text")["supplyGroups"]
    offered = [g for g in groups if g["counts"]]
    assert [len(g["prices"]) for g in offered] == [0, 0, 2]  # 동삼2는 주택형이 둘이라 붙이지 않음(다대4만 붙음)
    assert [g["_complex"] for g in groups if not g["counts"]] == ["동삼2"]


def test_price_row_listing_several_types_or_with_split_decimal_attaches_to_its_count_groups():
    # 2026-11-07 23건 대조: umca-4439 가격 행 「19A/B/C」가 19A·19B·19C 모집 묶음에 붙지 않고 따로 남아 가격 48개가 빠졌고,
    # jbdc-16011 모집 표 「059. 9288 A」(PDF 글자 사이 공백)가 59로 읽혀 가격표 「059.9288A」 행이 모집 묶음에 붙지 않음
    def build(count_types, price_type):
        count_rows = (("주택형", "모집"), *((t, "10") for t in count_types))
        lease_rows = (("주택형", "임대보증금(원)", "월임대료(원)"), (price_type, "25,120,000", "140,000"))
        tables = [st.Table("1-1", 1, "", count_rows[0], count_rows, None), st.Table("2-1", 2, "", lease_rows[0], lease_rows, None)]
        prices = [column(2, "PRICE", pk="DEPOSIT", unit="원"), column(3, "PRICE", pk="MONTHLY_RENT", unit="원")]
        mapping = {
            "tables": [
                {
                    "table": "1-1",
                    "role": "SUPPLY",
                    "rowUnit": "HOUSING_TYPE",
                    "complex": None,
                    "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="OFFERED")],
                },
                {"table": "2-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [column(1, "HOUSING_TYPE"), *prices]},
            ]
        }
        return [(g["housingTypeCode"], len(g["prices"])) for g in st.build_part(tables, mapping, "pdf-text")["supplyGroups"]]

    assert build(("19A", "19B", "19C", "26A"), "19A/B/C") == [("19A", 2), ("19B", 2), ("19C", 2), ("26A", 0)]
    assert build(("19A", "19B", "19C"), "19A·B") == [("19A", 2), ("19B", 2), ("19C", 0)]
    assert build(("059. 9288 A",), "059.9288A") == [("059. 9288 A", 2)]


def test_income_presence_in_its_own_column_is_a_qualifier_not_a_class():
    # 2026-11-07 23건 대조 umca-4439: 모집 표 대상은 「청년」, 가격표는 대상 칸 둘 「청 년」|「소득 有」·「소득 無」라 대상이 「청 년 소득 有」로
    # 이어져 「청년」과 다른 계층으로 보고 붙이지 않음(괄호로 적은 「청년(소득有)」은 이미 맞춤)
    count_rows = (("주택형", "계층", "모집"), ("19A", "청년", "6"), ("19B", "청년", "15"))
    lease_rows = (("주택형", "계층", "소득", "임대보증금(원)"), ("19A/B", "청 년", "소득 有", "25,120,000"), ("", "", "소득 無", "23,720,000"))
    counts = st.Table("1-1", 1, "", count_rows[0], count_rows, None)
    lease = st.Table("2-1", 2, "", lease_rows[0], lease_rows, ((0, 1, 2, 3), (4, 5, 6, 7), (4, 5, 8, 9)))
    mapping = {
        "tables": [
            {
                "table": "1-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "TARGET_GROUP"), column(3, "COUNT", ck="OFFERED")],
            },
            {
                "table": "2-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "TARGET_GROUP"), column(3, "TARGET_GROUP"), column(4, "PRICE", pk="DEPOSIT", unit="원")],
            },
        ]
    }
    groups = st.build_part([counts, lease], mapping, "pdf-text")["supplyGroups"]
    assert [(g["housingTypeCode"], g["scope"]["targetGroups"], sorted(p["sourceAmount"] for p in g["prices"])) for g in groups] == [
        ("19A", ["청년"], ["23,720,000", "25,120,000"]),
        ("19B", ["청년"], ["23,720,000", "25,120,000"]),
    ]
    assert not st._classes_match({"고령자 소득 有"}, {"청년"})


def test_price_table_without_row_names_is_reported_instead_of_skipped_silently():
    # 2026-11-07 23건 대조 bmc-75: 「[39A] 구간별 임대조건」(행 = 소득 구간, 주택형은 표 제목)에 열 해석이 가격 열만 답해 표 4개, 가격 96개가
    # 표시 없이 빠짐. 읽은 다른 표는 그대로 두고, 읽지 못한 가격표를 공급 섹션 이슈로 남깁니다(메모 + 검수 대기열)
    count_rows = (("주택형", "모집"), ("39A", "19"))
    tier_rows = (("구간", "임대보증금(원)", "월임대료(원)"), ("1구간 (~30%)", "16,240,000", "130,700"), ("2구간 (~50%)", "18,560,000", "149,300"))
    tables = [st.Table("3-1", 3, "", count_rows[0], count_rows, None), st.Table("9-2", 9, "[ 39A ] 구간별 임대조건", tier_rows[0], tier_rows, None)]
    mapping = {
        "tables": [
            {
                "table": "3-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="OFFERED")],
            },
            {
                "table": "9-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(2, "PRICE", pk="DEPOSIT", unit="원"), column(3, "PRICE", pk="MONTHLY_RENT", unit="원")],
            },
        ]
    }
    part = st.build_part(tables, mapping, "pdf-text")
    assert [(g["housingTypeCode"], [c["value"] for c in g["counts"]], g["prices"]) for g in part["supplyGroups"]] == [("39A", [19], [])]
    [issue] = part[st.ISSUES_KEY]
    assert issue["code"] == "SUPPLY_PRICE_TABLE_UNREAD" and issue["supplyGroupId"] is None and "9-2" in issue["description"]
    assert is_note({"code": issue["code"], "target": "/supplyGroups"}) and issue["code"] in DROPPED_VALUE_CODES  # 게시 유지, 검수 대기열

    # 지시 v8대로 구간 칸을 TARGET_GROUP으로 답하면 구간마다 요금안이 나뉘어 표 제목의 주택형(39A) 모집 묶음에 붙습니다
    tables[1] = st.Table("9-2", 9, "[ 39A ] 구간별 임대조건", tier_rows[0], tier_rows, None, above=("◾[ 39A ] 구간별 임대조건",))
    mapping["tables"][1]["columns"].insert(0, column(1, "TARGET_GROUP"))
    part = st.build_part(tables, mapping, "pdf-text")
    [group] = part["supplyGroups"]
    assert (group["housingTypeCode"], [c["value"] for c in group["counts"]]) == ("39A", [19]) and st.ISSUES_KEY not in part
    plans = {}
    for p in group["prices"]:
        plans.setdefault(p["pricePlanId"], []).append((p["scope"]["targetGroups"], p["kind"], p["sourceAmount"]))
    assert sorted(plans.values()) == [
        [(["1구간 (~30%)"], "DEPOSIT", "16,240,000"), (["1구간 (~30%)"], "MONTHLY_RENT", "130,700")],
        [(["2구간 (~50%)"], "DEPOSIT", "18,560,000"), (["2구간 (~50%)"], "MONTHLY_RENT", "149,300")],
    ]

    # 2026-11-07 v8 유료 확인 bmc-75: 이어진 「상호전환 시 임대조건」 표는 (-)·(+)·(+) 세 줄이 칸마다 금액 셋으로 읽히고 제목에 주택형이 없어,
    # 주택형·수량·가격 없는 빈 묶음마다 가격 빈칸 이슈가 붙었음 → 빈 묶음은 두지 않고 읽지 못한 가격표 메모 하나로
    switch_rows = (("구간", "임대보증금(원)", "월임대료(원)"), ("1 구 간", "11,360,000 21,110,000 27,600,000", "144,900 106,300 73,900"))
    tables.append(st.Table("9-3", 9, "상호전환 시 임대조건", switch_rows[0], switch_rows, None))
    prices = [column(2, "PRICE", pk="DEPOSIT", unit="원", stage="CONVERSION_DEPOSIT_UP"), column(3, "PRICE", pk="MONTHLY_RENT", unit="원")]
    mapping["tables"].append({"table": "9-3", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [column(1, "TARGET_GROUP"), *prices]})
    part = st.build_part(tables, mapping, "pdf-text")
    assert [g["housingTypeCode"] for g in part["supplyGroups"]] == ["39A"] and len(part["supplyGroups"][0]["prices"]) == 4
    [issue] = part[st.ISSUES_KEY]
    assert issue["code"] == "SUPPLY_PRICE_TABLE_UNREAD" and issue["supplyGroupId"] is None and "9-3" in issue["description"]


def test_price_rows_split_by_area_attach_to_the_type_whose_area_range_holds_them():
    # 실측(LH 부산당감 50년 공공임대): 공급표 「39 | 39.70 ~ 39.87 | 100」, 임대조건표는 면적 「39.70」「39.87」 행마다 보증금
    supply_rows = (("주택형", "전용", "모집"), ("39", "39.70 ~ 39.87", "100"))
    supply = st.Table("2-3", 2, "", supply_rows[0], supply_rows, None)
    lease_rows = (("주택형", "보증금"), ("39.70", "19,217,000"), ("39.87", "19,284,000"))
    lease = st.Table("3-1", 3, "", lease_rows[0], lease_rows, None)
    mapping = {
        "tables": [
            {
                "table": "2-3",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "AREA_EXCLUSIVE"), column(3, "COUNT", ck="OFFERED")],
            },
            {
                "table": "3-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "PRICE", pk="DEPOSIT", unit="원", plan="기본")],
            },
        ]
    }
    [group] = st.build_part([supply, lease], mapping, "pdf-text")["supplyGroups"]
    assert group["housingTypeCode"] == "39" and group["exclusiveAreaRange"] == {"min": 39.7, "max": 39.87}
    assert [(p["sourceAmount"], p["scope"]["description"].split(" ")[1]) for p in group["prices"]] == [("19,217,000", "39.7㎡"), ("19,284,000", "39.87㎡")]
    assert len({p["pricePlanId"] for p in group["prices"]}) == 2


def test_structure_call_skips_supply_when_tables_are_mapped_and_falls_back_otherwise():
    source = material()
    model = RecordedModel({"supply_tables": [json.dumps(MAPPING)], "structure": [structure_answer(source)]})
    rules = replace(RULES, calls=RULES.calls[:1], split_calls=(), large_text_chars=None)  # 구조 호출까지만 봅니다
    run = run_extraction(rules, source, model)
    names = [r.call_name for r in model.requests]
    assert names == ["supply_tables", "structure"]
    structure_request = model.requests[1]
    assert "supplyGroups" not in structure_request.output_schema["properties"] and "프로그램이 공급표에서 직접 옮겼으므로" in structure_request.instructions
    assert model.requests[0].user == structure_request.user  # 같은 원문 앞부분(입력 캐시 공유)
    assert [sorted(p["coverage"]) for p in run.parts] == [["locations", "notice"], ["supplyGroups"]]

    broken = RecordedModel({"supply_tables": ['{"tables": "not a list"}'], "structure": [structure_answer(source, RULES.calls[0].sections)]})
    run = run_extraction(rules, source, broken)
    assert "supplyGroups" in broken.requests[1].output_schema["properties"] and len(run.parts) == 1  # 이전 방식으로


def test_price_table_rows_attach_to_count_groups_and_loose_answers_still_map():
    # 실측(SH 신정도시마을): 호수 표(일반형·복층형)와 임대료·전환 표(「39㎡」 한 행)가 나뉨. AI는 표 번호를 「표 4-2」로,
    # 전환 열의 priceStage를 비워 답했고, 같은 종류 수량 열 두 개(일반공급·우선공급)에 대상을 적지 않았습니다
    counts = st.Table(
        "3-1",
        3,
        "",
        ("단지", "주택형", "금회 공급호수 › 일반공급", "금회 공급호수 › 우선공급"),
        (("단지", "주택형", "금회 공급호수", ""), ("신정도시마을", "39 (일반형)", "6", "2"), ("", "0039 (복층형)", "4", "1")),
        None,
    )
    rents = st.Table(
        "4-2",
        4,
        "",
        ("단지", "신청 유형", "임대보증금(천원)", "월임대료 (원)", "총 세대수"),
        (("단지", "신청 유형", "임대보증금(천원)", "월임대료 (원)", "총 세대수"), ("신정도시마을", "39㎡", "44,000", "335,000", "92세대")),
        None,
    )
    conversion = st.Table(
        "5-1",
        5,
        "",
        ("단지", "신청 유형", "전환 구분", "최대 전환 › 보증금(천원)", "최대 전환 › 월 임대료(원)"),
        (("단지", "신청 유형", "전환 구분", "보증금", "월세"), ("신정도시마을", "39㎡", "(+)", "80,000", "134,000"), ("", "", "(-)", "17,600", "390,000")),
        ((0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (5, 6, 10, 11, 12)),
    )
    mapping = {
        "tables": [
            {
                "table": "표 3-1 (3쪽)",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "COMPLEX"), column(2, "HOUSING_TYPE"), column(3, "COUNT", ck="OFFERED"), column(4, "COUNT", ck="OFFERED")],
            },
            {
                "table": "표 4-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(1, "COMPLEX"),
                    column(2, "HOUSING_TYPE"),
                    column(3, "PRICE", pk="DEPOSIT", unit="천원"),
                    column(4, "PRICE", pk="MONTHLY_RENT", unit="원"),
                    column(5, "COUNT", ck="TOTAL_HOUSING"),
                ],
            },
            {
                "table": "5-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(1, "COMPLEX"),
                    column(2, "HOUSING_TYPE"),
                    column(4, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환"),
                    column(5, "PRICE", pk="MONTHLY_RENT", unit="원", plan="최대 전환"),
                ],
            },
        ]
    }
    part = st.build_part([counts, rents, conversion], mapping, "pdf-text")
    flat, duplex = part["supplyGroups"]  # 가격표 행은 따로 남지 않고 두 모집 묶음에 붙음
    assert [(c["value"], c["scope"]["targetGroups"]) for c in flat["counts"]] == [(6, ["일반공급"]), (2, ["우선공급"])]  # 총 세대수 92는 붙이지 않음
    for group in (flat, duplex):
        assert [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in group["prices"]] == [
            ("DEPOSIT", "44,000", "STANDARD"),
            ("MONTHLY_RENT", "335,000", "STANDARD"),
            ("DEPOSIT", "80,000", "CONVERSION_DEPOSIT_UP"),
            ("MONTHLY_RENT", "134,000", "CONVERSION_DEPOSIT_UP"),
            ("DEPOSIT", "17,600", "CONVERSION_DEPOSIT_DOWN"),
            ("MONTHLY_RENT", "390,000", "CONVERSION_DEPOSIT_DOWN"),
        ]
        plans = [p["pricePlanId"] for p in group["prices"]]
        assert len(set(plans)) == 3 and all(p.startswith(group["id"]) for p in plans)  # 묶음마다 자기 요금안 ID
    assert {q["ref"] for q in part["quotes"]} >= set(flat["quoteRefs"])


def test_count_column_without_kind_takes_kind_from_title():
    # 실측(인천 행복주택): 「호수」 열을 COUNT로만 답해(countKind 없음) 대상 주택 수가 모두 버려졌음
    assert st._count_kind_from_title("호수") == "TOTAL_HOUSING" and st._count_kind_from_title("총 세대수") == "TOTAL_HOUSING"
    assert st._count_kind_from_title("금회 모집 호수") == "OFFERED" and st._count_kind_from_title("대기자 수") == "WAITLIST"
    assert st._count_kind_from_title("비고") is None
    table = st.Table("3-1", 3, "", ("형", "호수", "금회 모집"), (("형", "호수", "금회 모집"), ("18", "8", "20")), None)
    mapping = {
        "tables": [
            {
                "table": "3-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT"), column(3, "COUNT", ck="OFFERED")],
            }
        ]
    }
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [(c["kind"], c["value"]) for c in group["counts"]] == [("TOTAL_HOUSING", 8), ("OFFERED", 20)]


def test_combined_vacancy_and_total_cell_is_split_into_two_counts():
    # 실측(인천 행복주택): 열 제목 「현재 공가 호수 / 전체 호수」, 칸 「7/8」
    table = st.Table("3-1", 3, "", ("형", "현재 공가 호수 / 전체 호수"), (("형", "현재 공가 호수 / 전체 호수"), ("18", "7/8")), None)
    mapping = {
        "tables": [{"table": "3-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT")]}]
    }
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [(c["kind"], c["value"]) for c in group["counts"]] == [("CURRENT_VACANCIES", 7), ("TOTAL_HOUSING", 8)]


def test_lh_type_code_gives_area_and_price_rows_join_the_same_code_across_differently_named_complexes():
    # 실측(LH 충북혁신): 전용면적 열을 답하지 않았고, 공급표 「충북혁신 A-4블록 (천년나무4)」와 가격표 「충북혁신4 (천년나무4)」의
    # 이름이 달라 가격이 붙지 않음. 59A·59A-1은 면적이 같아 면적 번호로만 맞추면 서로의 가격이 섞임
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


def test_continuation_row_with_its_own_different_count_is_its_own_group():
    # 실측(LH 아산읍내): 「26.37」 칸 아래 건설 세대수 478·596 두 행. 596 행이 앞 묶음에 묻혀 빠짐
    rows = (("형", "건설", "모집"), ("26.37", "478", "200"), ("", "596", ""), ("31.32", "149", "40"))
    table = st.Table("1-2", 1, "", rows[0], rows, ((0, 1, 2), (3, 4, 5), (3, 6, 5), (7, 8, 9)))
    mapping = {
        "tables": [
            {
                "table": "1-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="TOTAL_HOUSING"), column(3, "COUNT", ck="OFFERED")],
            }
        ]
    }
    groups = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [[(c["kind"], c["value"]) for c in g["counts"]] for g in groups] == [
        [("TOTAL_HOUSING", 478), ("OFFERED", 200)],
        [("TOTAL_HOUSING", 596), ("OFFERED", 200)],
        [("TOTAL_HOUSING", 149), ("OFFERED", 40)],
    ]
    assert groups[1]["counts"][1].get("allocationPoolId")  # 병합된 모집 200은 두 묶음이 함께 쓰는 물량


def test_shifted_amount_pair_moves_right_and_deposit_answered_as_limit_is_a_price():
    # 실측(LH 양산): 「① 감액 › 임대보증금」을 한도로 답했고, 그 칸에 「4,551 154,980」이 붙고 오른쪽 월임대료 칸이 빔
    rows = (("형", "기본 › 보증금", "① 감액 › 임대보증금", "① 감액 › 월임대료(원)"), ("55", "18,551", "4,551 154,980", ""))
    table = st.Table("2-4", 2, "", rows[0], rows, None)
    mapping = {
        "tables": [
            {
                "table": "2-4",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
                    column(3, "CONVERSION_LIMIT", pk="DEPOSIT", unit="천원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
                    column(4, "PRICE", pk="MONTHLY_RENT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
                ],
            }
        ]
    }
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in group["prices"]] == [
        ("DEPOSIT", "18,551", "STANDARD"),
        ("DEPOSIT", "4,551", "CONVERSION_DEPOSIT_DOWN"),
        ("MONTHLY_RENT", "154,980", "CONVERSION_DEPOSIT_DOWN"),
    ]


def test_unit_rows_without_count_column_are_one_offered_unit_each():
    # 실측(LH 김포 장애인 자립주택): 동·호·모집유형·면적·보증금 표에 수량 열이 없어 모집 수가 모두 빠짐
    rows = (("동", "호", "면적", "보증금"), ("1동", "401", "26.5", "1,000,000"), ("1동", "404", "26.5", "1,000,000"))
    table = st.Table("3-2", 3, "", rows[0], rows, None)
    mapping = {
        "tables": [
            {
                "table": "3-2",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_UNIT",
                "complex": "여기",
                "columns": [column(1, "BUILDING"), column(2, "UNIT"), column(3, "AREA_EXCLUSIVE"), column(4, "PRICE", pk="DEPOSIT", unit="원")],
            }
        ]
    }
    groups = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [[(c["kind"], c["value"]) for c in g["counts"]] for g in groups] == [[("OFFERED", 1)], [("OFFERED", 1)]]
    housing = {"tables": [{**mapping["tables"][0], "rowUnit": "HOUSING_TYPE"}]}
    assert all(g["counts"] == [] for g in st.build_part([table], housing, "pdf-text")["supplyGroups"])  # 주택형 행은 그대로


def test_unit_floor_comes_from_unit_number_when_there_is_no_floor_column():
    # 실측 2026-10-26 LH 청년 매입임대 주택목록: 층 열이 없고 호 칸(214·1005)만 있어 31호 모두 층이 비었어요
    rows = (
        ("동", "호", "면적", "보증금"),
        ("A", "214", "21.6", "1,000,000"),
        ("A", "1005호", "21.6", "1,000,000"),
        ("A", "B01", "21.6", "1,000,000"),
        ("A", "7", "21.6", "1,000,000"),
    )
    table = st.Table("3-2", 3, "", rows[0], rows, None)
    columns = [column(1, "BUILDING"), column(2, "UNIT"), column(3, "AREA_EXCLUSIVE"), column(4, "PRICE", pk="DEPOSIT", unit="원")]
    mapping = {"tables": [{"table": "3-2", "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": "여기", "columns": columns}]}
    groups = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [g["floor"] for g in groups] == ["2층", "10층", None, None]  # 지하·한 자리 호수는 층을 정하지 않아요
    assert all("_unit" not in g for g in groups)
    housing = {"tables": [{**mapping["tables"][0], "rowUnit": "HOUSING_TYPE"}]}
    assert all(g["floor"] is None for g in st.build_part([table], housing, "pdf-text")["supplyGroups"])  # 주택형 행은 그대로


def test_large_unit_list_spreadsheet_rows_are_all_copied_by_code():
    # 실측 2026-10-20 LH 실제 수집: 엑셀 공급주택목록 15건 중 8건(233~570행)이 200행 제한에 걸려 주택별로 쓰이지 않았고,
    # 쓰인 87행짜리도 AI가 행을 옮겨 적느라 이어받기 호출이 4번(11분) 돌았음 → 엑셀 시트를 공급표로 보고 코드가 모든 행을 옮김
    from test_pdf_reader import make_pdf
    from test_xlsx_reader import HEADER, make_xlsx

    rows = [HEADER, *([n, f"춘천시 가상로 {n}", f"{100 + n}호", "0000", 20.0 + n / 100, 1000000 + n] for n in range(1, 301))]
    sheet = make_xlsx(rows)
    pdf = make_pdf([["구분", "내용"], ["공급", "첨부 목록 참조"]])
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", pdf), {**attachment("주택목록.xlsx", sheet), "role": "UNIT_LIST"}]
    reader = InMemorySourceReader(files={"raw/x/notice.pdf": pdf, "raw/x/주택목록.xlsx": sheet})
    intake = build_intake(event, reader, table_labels=True)
    assert intake.ready and "SPREADSHEET_TOO_LARGE" not in {i.code for i in intake.issues}
    tables = [t for t in st.candidates(intake.material) if t.label.startswith(st.SHEET_LABEL)]
    assert len(tables) == 1 and len(tables[0].rows) == 300
    request = st.mapping_request(RULES.build_request(RULES.calls[0], intake.material), tables)
    assert "첨부 엑셀" in request.instructions and "춘천시 가상로 300" not in request.instructions  # 열 의미만 묻고 행은 보내지 않음

    assert "공동현관 비밀번호" not in tables[0].columns  # 비밀번호 열은 읽을 때 빠짐 → 열 번호: 연번·주소·호·전용면적·임대보증금
    columns = [column(2, "COMPLEX"), column(3, "UNIT"), column(4, "AREA_EXCLUSIVE"), column(5, "PRICE", pk="DEPOSIT", unit="원")]
    mapping = {"tables": [{"table": tables[0].label, "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": None, "columns": columns}]}
    part = st.build_part(tables, mapping, intake.material.text_document_id)
    groups = part["supplyGroups"]
    assert len(groups) == 300
    assert [p["sourceAmount"] for p in groups[-1]["prices"]] == ["1000300"]
    quotes = {q["ref"]: q["text"] for q in part["quotes"]}
    assert all(quotes[ref] in intake.material.text for g in groups for ref in g["quoteRefs"])  # 근거가 원문 행 그대로


def test_conversion_direction_comes_from_column_and_plan_words():
    # 전환 보증금 점검(2026-10-23): 열 의미 답이 전환안의 방향을 비워 두거나(「전환」만 보고 모두 증액으로 봄) 기본안으로 적어도,
    # 열 제목·요금안 이름의 「보증금 증액·감액」으로 방향을 정합니다. 부호 칸이 없는 표
    head = ("형", "임대보증금", "월임대료", "보증금 증액 시 보증금", "보증금 증액 시 월임대료", "보증금 감액 시 보증금", "보증금 감액 시 월임대료")
    rows = (head, ("26A", "20,000", "300,000", "40,000", "200,000", "10,000", "350,000"))
    table = st.Table("8-1", 8, "임대조건", head, rows, (tuple(range(7)), tuple(range(7, 14))))
    columns = [
        column(1, "HOUSING_TYPE"),
        column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
        column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
        column(4, "PRICE", pk="DEPOSIT", unit="천원", plan="증액 전환"),
        column(5, "PRICE", pk="MONTHLY_RENT", unit="원", plan="증액 전환"),
        column(6, "PRICE", pk="DEPOSIT", unit="천원", plan="감액", stage="STANDARD"),
        column(7, "PRICE", pk="MONTHLY_RENT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_UP"),
    ]
    mapping = {"tables": [{"table": "8-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": columns}]}
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    assert [(p["sourceAmount"], p["priceStage"]) for p in group["prices"]] == [
        ("20,000", "STANDARD"),
        ("300,000", "STANDARD"),
        ("40,000", "CONVERSION_DEPOSIT_UP"),
        ("200,000", "CONVERSION_DEPOSIT_UP"),
        ("10,000", "CONVERSION_DEPOSIT_DOWN"),
        ("350,000", "CONVERSION_DEPOSIT_DOWN"),
    ]
    plans = {p["priceStage"]: p["pricePlanId"] for p in group["prices"]}
    assert len(set(plans.values())) == 3  # 기본·증액·감액은 서로 다른 요금안


def test_conversion_direction_words():
    assert st._stage_words("보증금 감액 시 월임대료") == "CONVERSION_DEPOSIT_DOWN"
    assert st._stage_words("전환(증액) 보증금") == "CONVERSION_DEPOSIT_UP"
    assert st._stage_words("최대 전환") is None  # 방향 낱말 없음: 부호 칸·답을 따름
    assert st._stage_words("보증금 증액·감액 전환 한도") is None


def conversion_mapping(label, conversion_columns):
    return {
        "tables": [
            {
                "table": label,
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
                    column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
                    column(4, "CONVERSION_LIMIT"),
                    *conversion_columns,
                ],
            }
        ]
    }


CONVERSION_HEAD = ("형", "보증금", "월세", "전환 한도", "전환 보증금", "전환 월세")
UP_COLUMNS = [
    column(5, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
    column(6, "PRICE", pk="MONTHLY_RENT", unit="원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
]


def conversion_prices(limit, deposit_cell, rent_cell, columns=UP_COLUMNS):
    rows = (CONVERSION_HEAD, ("26A", "20,000", "300,000", limit, deposit_cell, rent_cell))
    table = st.Table("9-1", 9, "임대조건", CONVERSION_HEAD, rows, (tuple(range(6)), tuple(range(6, 12))))
    part = st.build_part([table], conversion_mapping("9-1", columns), "pdf-text")
    [group] = part["supplyGroups"]
    return [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in group["prices"][2:]], part


def test_two_amount_cell_is_split_by_arrow_and_word_signs_in_written_order():
    # 한도 칸의 증액·감액 표시가 「(+)」「(-)」가 아니라 화살표·낱말이어도 나눕니다(2026-10-23, 합성 표)
    expected = [
        ("DEPOSIT", "30,000", "CONVERSION_DEPOSIT_UP"),
        ("DEPOSIT", "15,000", "CONVERSION_DEPOSIT_DOWN"),
        ("MONTHLY_RENT", "250,000", "CONVERSION_DEPOSIT_UP"),
        ("MONTHLY_RENT", "350,000", "CONVERSION_DEPOSIT_DOWN"),
    ]
    assert conversion_prices("↑ 10,000 ↓ 5,000", "30,000 15,000", "250,000 350,000")[0] == expected
    assert conversion_prices("▲10,000 ▼5,000", "30,000 15,000", "250,000 350,000")[0] == expected
    assert conversion_prices("+10,000 -5,000", "30,000 15,000", "250,000 350,000")[0] == expected
    # 감액이 먼저 적혀 있으면 첫 금액이 감액안입니다
    reversed_order = conversion_prices("감액 5,000 증액 10,000", "15,000 30,000", "350,000 250,000")[0]
    assert sorted(reversed_order) == sorted(expected)
    assert st._sign_order("(+) - (-) 10,000") == ["(+)", "(-)"]  # 가운데 맨 「-」는 빈 값이라 표시가 아님
    assert st._sign_order("10,000") is None and st._sign_order("↑ 10,000") is None


def test_column_answered_twice_as_up_and_down_takes_only_its_own_amount():
    columns = [
        column(5, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환 증액", stage="CONVERSION_DEPOSIT_UP"),
        column(5, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환 감액", stage="CONVERSION_DEPOSIT_DOWN"),
    ]
    prices, _ = conversion_prices("↑ 10,000 ↓ 5,000", "30,000 15,000", "", columns)
    assert prices == [("DEPOSIT", "30,000", "CONVERSION_DEPOSIT_UP"), ("DEPOSIT", "15,000", "CONVERSION_DEPOSIT_DOWN")]


def test_two_amount_cell_without_both_signs_is_reported_not_dropped_silently():
    prices, part = conversion_prices("10,000", "30,000 15,000", "250,000")
    assert prices == [("MONTHLY_RENT", "250,000", "CONVERSION_DEPOSIT_UP")]  # 나누지 못한 칸은 넣지 않음
    [issue] = part[st.ISSUES_KEY]
    assert issue["code"] == "SUPPLY_PRICE_MISSING" and issue["supplyGroupId"] == part["supplyGroups"][0]["id"]
    assert "30,000 15,000" in issue["description"]
    # 나눌 수 있으면 이슈가 없습니다
    assert st.ISSUES_KEY not in conversion_prices("↑ 10,000 ↓ 5,000", "30,000 15,000", "250,000 350,000")[1]


def test_no_deposit_rent_column_is_a_deposit_down_plan():
    # 보증금 없이 월세만 내는 요금안을 기본안(STANDARD)으로 답해도 열 제목·요금안 이름으로 보증금을 내린 전환안으로 둡니다
    head = ("호", "임대보증금", "월임대료", "무보증 전환 임대료")
    rows = (head, ("101", "5,000,000", "100,000", "120,000"))
    table = st.Table("엑셀1", 0, "", head, rows, None)
    columns = [
        column(1, "UNIT"),
        column(2, "PRICE", pk="DEPOSIT", unit="원", plan="기본", stage="STANDARD"),
        column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
        column(4, "PRICE", pk="MONTHLY_RENT", unit="원", plan="무보증금 월세", stage="STANDARD", group="수급자"),
    ]
    mapping = {"tables": [{"table": "엑셀1", "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": None, "columns": columns}]}
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    rent = group["prices"][-1]
    assert (rent["sourceAmount"], rent["priceStage"], rent["scope"]["targetGroups"]) == ("120,000", "CONVERSION_DEPOSIT_DOWN", ["수급자"])
    assert st._stage_words("무보증금 월세") == "CONVERSION_DEPOSIT_DOWN"


def test_transcribed_picture_table_is_a_candidate_and_every_row_is_copied():
    # 2026-11-05 sh-311087: 임대조건 표가 그림이라 판독 글에만 있었고 후보가 없어, 구조 호출이 37행 중 1행만 공급 묶음으로 만듦(가격 4/148)
    text = "\n".join(
        [
            "--- 1쪽 ---\n임대조건은 아래 그림 참고",
            "=== 그림 판독 공고.pdf 1쪽 (AI가 그림 속 글자를 옮김, 원문 그림으로 확인 필요) ===",
            "임대조건",
            "| 구분 | 호수 | 전용면적 (㎡) | 소득 50% 이하 | 소득 50% 이하 |",
            "| 구분 | 호수 | 전용면적 (㎡) | 보증금(원) | 월임대료(원) |",
            "| 가동 (성안로 64) | 202 | 36.29 | 27,490,000 | 358,100 |",
            "| 가동 (성안로 64) | 302 | 36.29 | 28,181,000 | 367,100 |",
            "| 나동 (성안로 64) | 304 | 35.99 | 27,680,000 | 360,600 |",
            "",
            "| 순위 | 내용 |",
            "| 1순위 | 수급자 |",
        ]
    )
    [table] = st.image_tables(replace(material(), text=text, sheets=()))
    assert table.label == "그림1" and table.columns[3:] == ("소득 50% 이하 보증금(원)", "소득 50% 이하 월임대료(원)") and len(table.rows) == 3
    group = "소득 50% 이하"
    columns = [column(1, "COMPLEX"), column(2, "UNIT"), column(3, "AREA_EXCLUSIVE")]
    columns += [column(4, "PRICE", pk="DEPOSIT", unit="원", plan=group, stage="STANDARD", group=group)]
    columns += [column(5, "PRICE", pk="MONTHLY_RENT", unit="원", plan=group, stage="STANDARD", group=group)]
    mapping = {"tables": [{"table": "그림1", "role": "SUPPLY", "rowUnit": "HOUSING_UNIT", "complex": None, "columns": columns}]}
    part = st.build_part([table], mapping, "pdf-text")
    assert len(part["supplyGroups"]) == 3 and sum(len(g["prices"]) for g in part["supplyGroups"]) == 6
    assert all(q["text"] in text for q in part["quotes"])  # 인용은 판독 글의 표 줄 그대로
