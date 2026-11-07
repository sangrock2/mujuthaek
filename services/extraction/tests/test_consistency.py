"""정답표 없이 하는 검사(V6 표 위치·V7 일관성·V8 누락). 실측 공고 모양을 줄인 작은 원문과 후보로 확인합니다."""

from mujuthaek_extraction.recheck import RECHECK_NOTE_CODES
from mujuthaek_extraction.verify.consistency import check_consistency, omitted_document_rows
from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.verifier import is_note

# 경북개발공사 천원주택 목록 표 모양: 1순위 / 2, 3순위 보증금이 같은 행의 다른 열
TABLE = "\n".join(
    [
        "--- 3쪽 ---",
        "[표 3-1]",
        "| 주택명 | 호 | 1순위 |  | 2, 3순위 |  |",
        "|  |  | 임대보증금(원) | 월임대료(원) | 임대보증금(원) | 월임대료(원) |",
        "| 로얄 | 302 | 1,000,000 | 192,300 | 2,000,000 | 232,200 |",
        "| 39A | 101 | 9,330,000 | 82,630 | 9,330,000 | 82,630 |",
    ]
)
ROW = "| 로얄 | 302 | 1,000,000 | 192,300 | 2,000,000 | 232,200 |"


def scope(*groups):
    return {"level": "SUPPLY_GROUP", "locationIds": [], "supplyGroupIds": [], "targetGroups": list(groups), "supplyCategory": "ALL"}


def price(kind, amount, *groups, plan=None, evidence="ev-row"):
    return {"kind": kind, "sourceAmount": f"{amount:,}", "amountKrw": amount, "pricePlanId": plan, "scope": scope(*groups), "evidenceIds": [evidence]}


def candidate(text=TABLE, prices=(), **overrides):
    start = text.index(ROW)
    base = {
        "evidence": [{"id": "ev-row", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + len(ROW)}, "quote": ROW}],
        "notice": {"counts": []},
        "locations": [],
        "supplyGroups": [
            {
                "housingTypeCode": None,
                "unitLabel": "302호",
                "exclusiveAreaSqm": 44.01,
                "itemKind": "HOUSING_UNIT",
                "scope": scope(),
                "prices": list(prices),
                "counts": [],
            }
        ],
        "schedules": [],
        "eligibility": [],
        "selectionRules": [],
        "requiredDocuments": [],
        "quality": {"coverage": {s: {"status": "EXTRACTED"} for s in ("eligibility", "requiredDocuments", "schedules")}},
    }
    return base | overrides


PRICE_TABLE_CODES = {"PRICE_VALUES_UNUSED", "PRICE_ROWS_UNUSED"}


def codes(c, text=TABLE, price_tables=False):
    """price_tables=False: 가격 일부만 넣은 후보로 다른 검사를 보는 시험에서 가격표 사용 검사(아래 따로 시험)는 뺍니다."""
    found = [(f.code, f.target) for f in check_consistency(c, SourceBundle(texts={"pdf-text": text}))]
    return found if price_tables else [f for f in found if f[0] not in PRICE_TABLE_CODES]


def test_value_from_other_rank_column_is_suspected():
    c = candidate(prices=[price("DEPOSIT", 2_000_000, "1순위", plan="r1")])  # 2,000,000은 "2, 3순위" 열의 값
    assert codes(c) == [("VALUE_POSITION_SUSPECTED", "/supplyGroups/0/prices/0")]


def test_value_in_matching_rank_column_passes():
    c = candidate(prices=[price("DEPOSIT", 1_000_000, "1순위", plan="r1"), price("DEPOSIT", 2_000_000, "2·3순위", plan="r23")])
    assert codes(c) == []


def test_same_value_in_two_columns_or_no_rank_label_is_not_judged():
    row = "| 39A | 101 | 9,330,000 | 82,630 | 9,330,000 | 82,630 |"
    c = candidate(prices=[price("DEPOSIT", 9_330_000, "1순위")])
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": TABLE.index(row), "end": TABLE.index(row) + len(row)}}
    assert codes(c) == []  # 어느 칸인지 모름
    assert codes(candidate(prices=[price("DEPOSIT", 2_000_000)])) == []  # 결과에 순위 표시가 없음


def test_row_naming_several_types_fits_each_of_them():
    # 2026-11-07 23건 대조 umca-4439: 「19A/B/C」 행 가격을 19B·19C 묶음에 붙였는데 행의 주택형을 19A로만 읽어 위치 의심으로 보류
    row = "| 19A/B/C | 25,120,000 | 140,000 |"
    text = "\n".join([TABLE, "[표 4-2]", "| 주택형 | 임대보증금(원) | 월임대료(원) |", row])

    def found(housing_type):
        c = candidate(text=text, prices=[price("DEPOSIT", 25_120_000)])
        c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
        c["supplyGroups"][0]["housingTypeCode"] = housing_type
        return [code for code, _ in codes(c, text)]

    assert found("19B") == [] and found("19C") == []
    assert found("26B") == ["VALUE_POSITION_SUSPECTED"]


def test_contract_and_balance_must_add_up_to_the_deposit():
    # 실측(2026-11-07 jbdc-16011): 계약금 「18,400.000」을 18,400원으로 읽어 보증금 92,000,000 = 18,400,000 + 잔금 73,600,000이 어긋난 채 게시됨
    def parts(contract, *extra, whole="DEPOSIT", plan="p"):
        return [price(whole, 92_000_000, plan="p"), price("CONTRACT_PAYMENT", contract, plan=plan), price("BALANCE", 73_600_000, plan=plan), *extra]

    def mismatches(prices):
        return [target for code, target in codes(candidate(prices=prices)) if code == "PRICE_PARTS_MISMATCH"]

    assert mismatches(parts(18_400)) == ["/supplyGroups/0/prices"]
    assert mismatches(parts(18_400, whole="SALE_PRICE")) == ["/supplyGroups/0/prices"]
    assert not is_note({"code": "PRICE_PARTS_MISMATCH", "target": "/supplyGroups/0/prices"})  # 메모가 아니라 가격 보류
    assert mismatches(parts(18_400_000)) == []
    assert mismatches(parts(9_200_000, price("OTHER", 9_200_000, plan="p"))) == []  # 중도금일 수 있는 금액이 있으면 보지 않음
    assert mismatches(parts(18_400, plan="q")) == []  # 다른 요금안의 금액끼리는 더하지 않음
    assert mismatches(parts(18_400, price("CONTRACT_PAYMENT", 18_400_000, plan="p"))) == []  # 같은 종류가 둘이면 어느 것을 더할지 모름


def test_value_from_other_housing_type_row_is_suspected():
    row = "| 39A | 101 | 9,330,000 | 82,630 | 9,330,000 | 82,630 |"
    c = candidate(prices=[price("MONTHLY_RENT", 82_630)])
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": TABLE.index(row), "end": TABLE.index(row) + len(row)}}
    c["supplyGroups"][0]["housingTypeCode"] = "46B"
    assert codes(c) == []  # 같은 값이 두 칸이라 판단하지 않음
    c["supplyGroups"][0]["prices"] = [price("DEPOSIT", 9_330_000)]
    assert codes(c) == []
    c["evidence"][0]["quote"] = row
    c["supplyGroups"][0]["prices"] = []
    c["supplyGroups"][0]["counts"] = [{"kind": "OFFERED", "value": 101, "scope": scope(), "evidenceIds": ["ev-row"]}]
    assert codes(c) == [("VALUE_POSITION_SUSPECTED", "/supplyGroups/0/counts/0")]


def test_schedule_order_and_reversed_rent_are_suspected():
    def schedule(kind, start, end=None):
        day = {"precision": "DAY", "value": start}
        return {"kinds": [kind], "rawLabel": kind, "startsAt": day, "endsAt": {"precision": "DAY", "value": end} if end else None}

    c = candidate(
        prices=[price("DEPOSIT", 30_000, plan="p"), price("MONTHLY_RENT", 1_000_000, plan="p")],
        schedules=[schedule("ANNOUNCEMENT", "2026-07-28"), schedule("APPLICATION", "2026-08-10", "2026-08-05"), schedule("CONTRACT", "2026-07-01")],
    )
    found = codes(c)
    assert ("RENT_EXCEEDS_DEPOSIT", "/supplyGroups/0/prices/1") in found
    assert ("SCHEDULE_ORDER_SUSPECTED", "/schedules/1") in found  # 끝이 시작보다 이름
    assert ("SCHEDULE_ORDER_SUSPECTED", "/schedules/2") in found  # 계약이 접수보다 이름 (당첨 발표가 없으면 접수와 비교하지 않으므로 공고와)


def test_values_out_of_range_are_suspected():
    age = {"kind": "ATOMIC", "attribute": "AGE_YEARS", "value": 390, "evidenceIds": []}
    c = candidate(eligibility=[{"rule": {"expression": age}, "scope": scope(), "evidenceIds": []}])
    c["supplyGroups"][0]["exclusiveAreaSqm"] = 4401
    assert set(codes(c)) == {("VALUE_OUT_OF_RANGE", "/eligibility/0/rule/expression"), ("VALUE_OUT_OF_RANGE", "/supplyGroups/0/exclusiveAreaSqm")}


def test_section_claimed_complete_but_empty_while_source_has_heading():
    text = TABLE + "\n4. 제출서류\n주민등록표등본 1부"
    found = codes(candidate(text=text), text)
    assert ("SECTION_OMISSION_SUSPECTED", "/requiredDocuments") in found
    c = candidate(text=text)
    c["quality"]["coverage"]["requiredDocuments"]["status"] = "FAILED"  # 실패는 이미 따로 보고됨
    assert ("SECTION_OMISSION_SUSPECTED", "/requiredDocuments") not in codes(c, text)


def test_scoring_table_without_scoring_rules_is_suspected():
    text = TABLE + "\n[표 5-1]\n| 평가항목 | 평가요소 | 배점 |\n| 자녀 수 | 3명 이상 | 3점 |\n| | 2명 | 2점 |\n| | 1명 | 1점 |"
    assert ("SCORING_OMISSION_SUSPECTED", "/selectionRules") in codes(candidate(text=text), text)


def test_attached_listing_with_far_fewer_homes_extracted_is_suspected():
    sheet = "\n".join(
        ["=== 첨부 엑셀 목록.xlsx ===", "[엑셀 시트 주택목록]", "| 소재구 | 임대대상명 | 세대수 |"] + [f"| 대덕구 | 중리동 {n} | 6 |" for n in range(10)]
    )
    text = TABLE + "\n" + sheet
    assert ("LIST_OMISSION_SUSPECTED", "/locations") in codes(candidate(text=text), text)
    c = candidate(text=text, locations=[{}] * 10)
    assert ("LIST_OMISSION_SUSPECTED", "/locations") not in codes(c, text)


def test_headerless_rank_table_uses_row_label_not_first_row():
    # LH 국민임대 실측: 머리글 행 없이 | 1순위 | ... | / | 2순위 | ... | 로 이어지는 소득 기준 표 (오탐이었음)
    row = "| 2순위 | 100% | 국민임대 |"
    text = "\n".join(["[표 4-1]", "| 1순위 | 70% | 국민임대 |", row])
    atom = {"kind": "ATOMIC", "attribute": "INCOME_BENCHMARK_PERCENT", "value": 100, "evidenceIds": ["ev-row"]}
    c = candidate(text=text + "\n" + ROW, eligibility=[{"rule": {"expression": atom}, "scope": scope("2순위"), "evidenceIds": []}])
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    assert codes(c, text + "\n" + ROW) == []
    atom |= {"attribute": "HOUSEHOLD_SIZE", "value": 2}  # 가구원 수 2가 제목 칸 "2순위"의 숫자와 맞춰지던 오탐
    assert codes(c, text + "\n" + ROW) == []
    atom |= {"attribute": "INCOME_BENCHMARK_PERCENT", "value": 100}
    c["eligibility"][0]["scope"] = scope("1순위")
    assert codes(c, text + "\n" + ROW) == [("VALUE_POSITION_SUSPECTED", "/eligibility/0/rule/expression")]


def test_listing_title_and_header_rows_are_not_counted_as_homes():
    # 경북개발공사 실측: 제목 행(날짜 포함)·머리글 행(1순위·2, 3순위)을 주택으로 세던 오탐
    sheet = [
        "=== 첨부 엑셀 목록.xlsx ===",
        "[엑셀 시트 Sheet1]",
        "| 칠곡군 천원주택 공급대상 주택 목록(2026.07.28 공고) |  |  |  |",
        "| 구분 | 주소 | 호 | 1순위 |",
        "|  |  |  | 임대보증금(원) |",
        *[f"| {n} | 칠곡군 왜관읍 달오길 {n} | 30{n} | 1000000 |" for n in range(1, 6)],
    ]
    text = TABLE + "\n" + "\n".join(sheet)
    assert codes(candidate(text=text, locations=[{}] * 5), text) == []


def test_count_total_compares_only_same_scope_and_is_a_note_target():
    # 검토 지적: 신규만 센 전체 수와 재공급이 섞인 묶음 합을 비교했고, 공고 섹션 대상이라 사람 확인으로 막혔음
    def count(value, category="ALL"):
        return {"kind": "OFFERED", "value": value, "scope": scope() | {"supplyCategory": category}, "evidenceIds": []}

    def groups(*counts):
        return [{"housingTypeCode": None, "unitLabel": None, "exclusiveAreaSqm": None, "scope": scope(), "prices": [], "counts": [c]} for c in counts]

    c = candidate(notice={"counts": [count(10, "NEW")]}, supplyGroups=groups(count(6, "NEW"), count(4, "RESUPPLY")))
    assert ("COUNT_TOTAL_SUSPECTED", "/supplyGroups") not in codes(c)  # 범위가 달라 비교하지 않음
    c = candidate(notice={"counts": [count(10)]}, supplyGroups=groups(count(6), count(3)))
    assert ("COUNT_TOTAL_SUSPECTED", "/supplyGroups") in codes(c)


def test_second_income_criterion_left_out_is_noted_but_does_not_block():
    # 검토 지적: 소득 기준이 통째로 빠진 것만 잡고 두 기준 중 하나가 빠진 것은 못 잡았음. 정밀도가 낮아 메모로만 둡니다
    from mujuthaek_extraction.verify.verifier import is_note

    text = TABLE + "\n1순위: 월평균소득 70% 이하\n2순위: 월평균소득 100% 이하\n※ 재계약 시 월평균소득 105% 이하"
    atom = {"kind": "ATOMIC", "attribute": "INCOME_BENCHMARK_PERCENT", "value": 70, "evidenceIds": []}
    item = {"rule": {"expression": atom}, "scope": scope("1순위"), "evidenceIds": [], "originalText": "월평균소득 70% 이하"}
    found = check_consistency(candidate(text=text, eligibility=[item]), SourceBundle(texts={"pdf-text": text}))
    unused = [f for f in found if f.code == "INCOME_CRITERION_UNUSED"]
    assert len(unused) == 1 and "100%" in unused[0].description  # 105%는 재계약 기준이라 셈하지 않음
    assert is_note(unused[0].issue())


def test_headerless_table_row_without_rank_label_is_not_judged_by_first_data_row():
    # 검토 지적: | 1순위 | 70% | / | 맞벌이 | 100% | 에서 2순위로 붙인 100%를 첫 데이터 행 때문에 "1순위 칸"으로 보던 오탐
    row = "| 맞벌이 | 100% |"
    text = "\n".join(["[표 4-1]", "| 1순위 | 70% |", row])
    atom = {"kind": "ATOMIC", "attribute": "INCOME_BENCHMARK_PERCENT", "value": 100, "evidenceIds": ["ev-row"]}
    c = candidate(text=text + "\n" + ROW, eligibility=[{"rule": {"expression": atom}, "scope": scope("2순위"), "evidenceIds": []}])
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    assert [x for x in codes(c, text + "\n" + ROW) if x[0] == "VALUE_POSITION_SUSPECTED"] == []


def test_blank_supply_prices_with_large_text_free_image_are_sent_to_review(monkeypatch):
    # 실측(2026-10-16 시험): 임대조건 표가 PDF 안의 그림이라 가격 0개로 나온 SH 청년주택 공고
    import mujuthaek_extraction.verify.consistency as consistency

    monkeypatch.setattr(consistency, "image_pages", lambda data: ((1, 0.32),) if data == b"image-pdf" else ())
    sources = SourceBundle(texts={"pdf-text": TABLE}, pdfs={"pdf-1": b"image-pdf"})
    c = candidate()  # 공급 묶음은 있는데 가격이 하나도 없음
    assert ("SOURCE_IN_IMAGE_SUSPECTED", "/supplyGroups") in [(f.code, f.target) for f in check_consistency(c, sources)]

    # 가격이 있고 빈 칸도 없으면 그림(위치도·평면도)이 있어도 걸지 않습니다
    priced = candidate(prices=[price("DEPOSIT", 1_000_000, "1순위", plan="r1")])
    assert "SOURCE_IN_IMAGE_SUSPECTED" not in [f.code for f in check_consistency(priced, sources)]
    # 그림이 없으면 가격이 없어도 이 검사로는 걸지 않습니다(전세임대처럼 주택이 정해지지 않은 공고)
    plain = SourceBundle(texts={"pdf-text": TABLE}, pdfs={"pdf-1": b"text-only-pdf"})
    assert "SOURCE_IN_IMAGE_SUSPECTED" not in [f.code for f in check_consistency(c, plain)]


def test_income_criterion_left_as_text_with_its_percent_is_not_auto_completed():
    # 실측(2026-10-16 시험): 「월평균소득 100%(1인 120%…)」를 조건식 없이 글로만 남긴 소득 조건이 자동 완료되던 것
    from mujuthaek_extraction.verify.verifier import is_note

    text = TABLE + "\n해당 세대의 월평균소득이 전년도 도시근로자 가구당 월평균소득의 100% 이하인 자"
    loose = {"category": "INCOME", "rule": {"status": "UNSTRUCTURED", "expression": None}, "scope": scope(), "evidenceIds": []}
    loose["originalText"] = "해당 세대의 월평균소득이 전년도 도시근로자 가구당 월평균소득의 100% 이하인 자"
    found = check_consistency(candidate(text=text, eligibility=[loose]), SourceBundle(texts={"pdf-text": text}))
    flagged = [f for f in found if f.code == "CRITERION_NOT_STRUCTURED"]
    assert [f.target for f in flagged] == ["/eligibility/0"] and not is_note(flagged[0].issue())

    # 값이 없는 글(「소득 기준 미적용」)이나 다른 종류의 조건은 글로 남겨도 됩니다
    waived = loose | {"originalText": "이번 공고는 소득 기준을 적용하지 않습니다"}
    other = loose | {"category": "RESIDENCE", "originalText": "공고일 현재 대전광역시 거주자 100%"}
    for item in (waived, other):
        found = check_consistency(candidate(text=text, eligibility=[item]), SourceBundle(texts={"pdf-text": text}))
        assert "CRITERION_NOT_STRUCTURED" not in [f.code for f in found]


def test_asset_limit_written_in_a_fill_in_blank_form_left_as_text_is_not_auto_completed():
    # 2026-11-06 23건 측정: 「( 24,500 )만원 이하」 빈칸 양식이라 글로만 남긴 자산·자동차 기준이 경고 없이 게시됨
    text = TABLE + "\n총 자산 가액 합산 기준 ( 24,500 )만원 이하\n개별 자동차가액 ( 4,542 )만원 이하"
    assets = {"category": "ASSETS", "rule": {"status": "UNSTRUCTURED", "expression": None}, "scope": scope(), "evidenceIds": []}
    assets["originalText"] = "총 자산 가액 합산 기준 ( 24,500 )만원 이하"
    car = assets | {"category": "CAR_ASSETS", "originalText": "개별 자동차가액 ( 4,542 )만원 이하"}
    found = check_consistency(candidate(text=text, eligibility=[assets, car]), SourceBundle(texts={"pdf-text": text}))
    flagged = [f.target for f in found if f.code == "CRITERION_NOT_STRUCTURED"]
    assert flagged == ["/eligibility/0", "/eligibility/1"]


def test_attachment_that_is_a_qna_not_the_notice_is_sent_to_review():
    # 실측: 경남개발공사 전세임대 2차 공고의 첨부 PDF가 「… 관련 Q&A」인데 공고로 자동 완료되던 것
    from mujuthaek_extraction.verify.verifier import is_note

    qna = candidate(notice={"counts": [], "title": "2026년 전세임대주택 입주자모집 관련 Q&A"})
    [found] = [f for f in check_consistency(qna, SourceBundle(texts={"pdf-text": TABLE})) if f.code == "NOT_A_NOTICE_SUSPECTED"]
    assert found.target == "/notice" and not is_note(found.issue())
    notice = candidate(notice={"counts": [], "title": "2026년 전세임대주택 입주자모집 공고"})
    assert "NOT_A_NOTICE_SUSPECTED" not in [f.code for f in check_consistency(notice, SourceBundle(texts={"pdf-text": TABLE}))]


def test_price_cells_left_out_of_a_used_row_or_whole_rows_are_suspected():
    # 실측(sol 정답표 대조): 한 행의 두 계층 중 한 계층 가격만 넣음(bmc 가격 54/108), 8개 주택형 중 5개만 넣고 EXTRACTED 보고
    from mujuthaek_extraction.verify.verifier import is_note

    first_rank = [price("DEPOSIT", 1_000_000, "1순위", plan="r1"), price("MONTHLY_RENT", 192_300, "1순위", plan="r1")]
    found = codes(candidate(prices=first_rank), price_tables=True)
    assert ("PRICE_VALUES_UNUSED", "/supplyGroups/0") in found  # 같은 행의 2·3순위 2,000,000·232,200
    assert ("PRICE_ROWS_UNUSED", "/quality/coverage/supplyGroups") in found  # 39A 행은 어느 묶음에도 없음
    [unused] = [f for f in check_consistency(candidate(prices=first_rank), SourceBundle(texts={"pdf-text": TABLE})) if f.code == "PRICE_VALUES_UNUSED"]
    assert "2,000,000" in unused.description and not is_note(unused.issue())  # 공급 섹션이어도 재확인 → 사람 확인

    whole_row = [*first_rank, price("DEPOSIT", 2_000_000, "2·3순위", plan="r23"), price("MONTHLY_RENT", 232_200, "2·3순위", plan="r23")]
    assert codes(candidate(prices=whole_row), price_tables=True) == [("PRICE_ROWS_UNUSED", "/quality/coverage/supplyGroups")]


def test_price_table_check_reads_ranges_and_skips_count_and_adjustment_cells():
    text = "\n".join(
        [
            "| 단지 | 세대수 | 임대보증금(원) | 월임대료 범위(원) | 전환 증감(원) |",
            "| 한마음 | 1,256 | 20,475,000 | 240,820 | 250,000 | 1,100 |",
        ]
    )
    row = "| 한마음 | 1,256 | 20,475,000 | 240,820 | 250,000 | 1,100 |"
    c = candidate(prices=[price("DEPOSIT", 20_475_000, plan="p"), price("MONTHLY_RENT", 240_820, plan="p")])
    c["supplyGroups"][0]["prices"][1]["sourceAmount"] = "240,820~250,000"  # 범위는 양 끝 금액을 모두 쓴 것으로 봅니다
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    # 가격 앞 칸의 세대수 1,256과 쓴 가격 중 가장 작은 금액의 1/100보다 작은 증감액 1,100은 가격 칸으로 보지 않습니다
    assert codes(c, text=text, price_tables=True) == []


def test_conversion_limit_column_is_not_counted_as_an_unused_price():
    # 실측(2026-10-18 LH 군산내흥7): 「전환가능 보증금 한도액」 칸의 3,000(천원)이 빠진 가격으로 걸려 공급 묶음이 보류됨
    title = "  [열 제목] 1. 형 | 2. 임대보증금(천원) | 3. 월임대료(원) | 4. 전환 구분 | "
    title += "5. 전환가능 보증금 한도액(천원) | 6. 최대전환 보증금(천원) | 7. 최대전환 월임대료(원)"
    row = "| 16 | 12,308 | 76,920 | (+) | 3,000 | 15,308 | 61,920 |"
    text = "\n".join(["[표 3-2]", title, "| 형 | 임대보증금 | 월임대료 | 구분 | 한도액 | 보증금 | 월임대료 |", row, "안내문", ROW])  # 도우미 후보가 쓰는 행
    used = [
        price("DEPOSIT", 12_308, plan="p"),
        price("MONTHLY_RENT", 76_920, plan="p"),
        price("DEPOSIT", 15_308, plan="c"),
        price("MONTHLY_RENT", 61_920, plan="c"),
    ]
    c = candidate(text=text, prices=used)
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    assert not [f for f in codes(c, text=text, price_tables=True) if f[0] in PRICE_TABLE_CODES]
    # 열 제목 줄이 없으면 예전처럼 빠진 금액으로 봅니다
    bare = "\n".join(["| 형 | 임대보증금 | 월임대료 | 구분 | 한도액 | 보증금 | 월임대료 |", row, "안내문", ROW])  # 도우미 후보가 쓰는 행
    c2 = candidate(text=bare, prices=used)
    c2["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": bare.index(row), "end": bare.index(row) + len(row)}}
    assert ("PRICE_VALUES_UNUSED", "/supplyGroups/0") in codes(c2, text=bare, price_tables=True)


def test_count_read_from_built_or_waiting_column_is_suspected():
    # 실측: 대전도시공사 예비입주자 모집 표 「건설 호수 25 | 현재 공가 1 | 대기 중인 예비자 2 | 금회 모집 예비자 11」의 25를 모집 수로
    text = "\n".join(
        [
            "| 공급 유형 | 공급 대상 | 건설 호수 | 현재 공가 수 | 대기 중인 예비 자수 | 금회 모집 예비 자수 |",
            "| 26 | 대학생 | 25 | 1 | 2 | 11 |",
        ]
    )
    row = "| 26 | 대학생 | 25 | 1 | 2 | 11 |"

    def with_count(kind, value):
        c = candidate()
        c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
        c["supplyGroups"][0]["counts"] = [{"kind": kind, "value": value, "scope": scope(), "evidenceIds": ["ev-row"]}]
        return [f for f in check_consistency(c, SourceBundle(texts={"pdf-text": text})) if f.code == "COUNT_KIND_SUSPECTED"]

    [built] = with_count("OFFERED", 25)
    assert built.target == "/supplyGroups/0" and "TOTAL_HOUSING" in built.description
    assert "WAITLIST" in with_count("RESERVE", 2)[0].description
    assert with_count("OFFERED", 11) == [] and with_count("TOTAL_HOUSING", 25) == [] and with_count("WAITLIST", 2) == []


def test_checks_read_structured_tables_with_title_and_aid_lines():
    # 구조 방식 글자: 표 아래 [열 제목] 줄과 행마다 ↳ 줄이 끼어도 같은 표로 보고, 머리글은 [열 제목] 줄에서 읽습니다
    text = "\n".join(
        [
            "[표 3-2]",
            "  [열 제목] 1. 공급 유형 | 2. 공급 대상 | 3. 건설 호수 | 4. 현재 공가 수 | 5. 금회 모집 예비 자수 | "
            "6. 임대조건 › 임대보증금(천원) | 7. 임대조건 › 월 임대료(원)",
            "| 공급 유형 | 공급 대상 | 건설 호수 | 현재 공가 수 | 금회 모집 예비 자수 | 임대조건 |  |",
            "|  |  |  |  |  | 임대보증금(천원) | 월 임대료(원) |",
            "| 26 | 대학생 | 25 | 1 | 11 | 22,100 | 103,130 |",
            "  ↳ 대학생 — 공급 유형 26 · 건설 호수 25 · 현재 공가 수 1 · 금회 모집 예비 자수 11 · 임대보증금(천원) 22,100 · 월 임대료(원) 103,130",
            "| 36 | 신혼부부 | 13 | 2 | 7 | 35,600 | 166,130 |",
            "  ↳ 신혼부부 — 공급 유형 36 · 건설 호수 13 · 현재 공가 수 2 · 금회 모집 예비 자수 7 · 임대보증금(천원) 35,600 · 월 임대료(원) 166,130",
        ]
    )
    row = "| 26 | 대학생 | 25 | 1 | 11 | 22,100 | 103,130 |"
    c = candidate(prices=[price("DEPOSIT", 22_100), price("MONTHLY_RENT", 103_130)])
    c["evidence"][0] |= {"quote": row, "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    c["supplyGroups"][0]["counts"] = [{"kind": "OFFERED", "value": 25, "scope": scope(), "evidenceIds": ["ev-row"]}]
    found = codes(c, text=text, price_tables=True)
    assert ("COUNT_KIND_SUSPECTED", "/supplyGroups/0") in found  # 25는 「건설 호수」 열
    assert ("PRICE_ROWS_UNUSED", "/quality/coverage/supplyGroups") in found  # ↳ 줄을 건너 같은 표의 신혼부부 행까지 봄
    c["supplyGroups"][0]["counts"][0]["value"] = 11
    assert ("COUNT_KIND_SUSPECTED", "/supplyGroups/0") not in codes(c, text=text, price_tables=True)


def test_base_criterion_not_applied_this_time_is_not_held_when_the_applied_one_is_structured():
    # 실측(2026-10-18 LH 태백장성): 기본 「소득 70%」는 이번 모집에 적용하지 않고 완화 「150%」를 적용(규칙 19-7)
    text = TABLE + "\n전년도 월평균소득 70% 이하"
    base = {"category": "INCOME", "scope": scope(), "evidenceIds": [], "originalText": "전년도 월평균소득 70% 이하"}
    base["rule"] = {"status": "UNSTRUCTURED", "expression": None, "reason": "이번 모집에는 적용하지 않습니다"}
    applied = {"category": "INCOME", "scope": scope(), "evidenceIds": [], "originalText": "소득 150% 이하"}
    applied["rule"] = {"status": "STRUCTURED", "expression": {"kind": "ATOMIC", "attribute": "INCOME_BENCHMARK_PERCENT", "operator": "LTE", "value": 150}}
    held = [
        f
        for f in check_consistency(candidate(text=text, eligibility=[base, applied]), SourceBundle(texts={"pdf-text": text}))
        if f.code == "CRITERION_NOT_STRUCTURED"
    ]
    assert held == []
    # 적용하는 조건이 따로 없으면 「적용하지 않는다」고 적어도 검수로 보냅니다
    alone = [
        f for f in check_consistency(candidate(text=text, eligibility=[base]), SourceBundle(texts={"pdf-text": text})) if f.code == "CRITERION_NOT_STRUCTURED"
    ]
    assert [f.target for f in alone] == ["/eligibility/0"]


def test_family_member_age_is_not_an_applicant_age_criterion():
    # 실측(청약홈 에코델타): 무주택 설명 「만60세 이상의 직계존속이 주택…을 소유」를 신청자 나이 기준으로 보고 누락 의심을 냄
    from mujuthaek_extraction.verify.consistency import CRITERIA

    age = next(pattern for name, pattern, *_ in CRITERIA if name == "나이 기준")
    assert not age.search("6. 만60세 이상의 직계존속(배우자의 직계존속을 포함한다)이 주택을 소유하고 있는 경우")
    assert age.search("신청자는 만 19세 이상이어야 합니다")


def test_condition_made_from_one_definition_entry_and_put_on_a_wider_target_is_suspected():
    # 2026-11-06 V2 5건 재측정 dcco-24812: 「주거약자란 … ① 고령자(만 65세 이상인 자) ② 장애인」의 한 갈래로 만 65세 이상 조건을 만들어
    # 대상 「주거약자용 주택 신청자」 전체에 붙여 게시됨(장애인 등 다른 주거약자에게는 나이 기준이 없음)
    line = "① 고령자(만 65세 이상인 자)"
    text = TABLE + f"\n“주거약자” 란? 아래의 자를 말합니다.\n{line}\n② 장애인"
    start = text.index(line)
    quoted = {"id": "ev-def", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + len(line)}, "quote": line}
    age = {"kind": "ATOMIC", "subject": "APPLICANT", "attribute": "AGE_YEARS", "operator": "GTE", "value": 65}

    def item(*groups, original="고령자(만 65세 이상인 자)", evidence=()):
        rule = {"status": "STRUCTURED", "expression": age}
        return {"category": "AGE", "scope": scope(*groups), "evidenceIds": list(evidence), "originalText": original, "rule": rule}

    def flagged(*items):
        found = check_consistency(candidate(text=text, eligibility=list(items), evidence=[quoted]), SourceBundle(texts={"pdf-text": text}))
        return [f for f in found if f.code == "DEFINITION_SCOPE_SUSPECTED"]

    found = flagged(item("주거약자용 주택 신청자"))
    assert [f.target for f in found] == ["/eligibility/0"] and "「고령자」에게만" in found[0].description and not is_note(found[0].issue())
    assert len(flagged(item("주거약자용 주택 신청자", original="주거약자만 신청할 수 있어요", evidence=["ev-def"]))) == 1  # 근거 줄이 정의
    assert flagged(item("주거약자용 주택 신청자 중 고령자")) == []  # 대상이 그 낱말
    assert flagged(item()) == []  # 대상이 비면 신청자 전체의 요건(「성년자(만 19세 이상)」처럼 정의가 곧 모두의 요건)
    assert flagged(item("주거약자용 주택 신청자", original="고령자(만 65세 이상인 자) 및 장애인")) == []  # 정의만으로 된 줄이 아님
    assert flagged(item("주거약자용 주택 신청자", original="고령자(주택 소유와 무관)")) == []  # 정의에 조건식 값이 없음


def test_price_table_continued_on_next_page_without_header_is_checked_too():
    # 실측(LH 청주지북 공공분양): 분양가 표가 다음 쪽 머리 없는 표로 이어져 55개가 빠졌는데 어떤 검사에도 걸리지 않음
    all_rows = [
        price("DEPOSIT", 1_000_000, "1순위", plan="r1"),
        price("MONTHLY_RENT", 192_300, "1순위", plan="r1"),
        price("DEPOSIT", 2_000_000, "2·3순위", plan="r23"),
        price("MONTHLY_RENT", 232_200, "2·3순위", plan="r23"),
        price("DEPOSIT", 9_330_000, plan="a"),
        price("MONTHLY_RENT", 82_630, plan="a"),
    ]
    assert codes(candidate(prices=all_rows), price_tables=True) == []
    text = TABLE + "\n- 3 -\n--- 4쪽 ---\n[표 4-1]\n| 로얄 | 303 | 1,100,000 | 193,000 | 2,100,000 | 233,000 |"
    assert codes(candidate(text, prices=all_rows), text=text, price_tables=True) == [("PRICE_ROWS_UNUSED", "/quality/coverage/supplyGroups")]
    other = TABLE + "\n안내문 한 줄\n[표 4-1]\n| 로얄 | 303 | 1,100,000 | 193,000 | 2,100,000 | 233,000 |"  # 사이에 본문이 있으면 다른 표
    assert codes(candidate(other, prices=all_rows), text=other, price_tables=True) == []


def test_prices_left_in_a_group_without_counts_next_to_the_same_type_are_flagged():
    # 실측(LH 부산당감): 공급표 「39」(면적 39.70~39.87)와 임대조건표 「39.70」「39.87」 행이 따로 남아 가격 12개가 모집 수 없는 묶음에
    c = candidate()
    counted = {
        **c["supplyGroups"][0],
        "itemKind": "HOUSING_TYPE",
        "housingTypeCode": "39",
        "unitLabel": None,
        "counts": [{"kind": "OFFERED", "value": 100, "scope": scope(), "evidenceIds": []}],
    }
    loose = {**counted, "housingTypeCode": "39.70", "counts": [], "prices": [price("DEPOSIT", 1_000_000, plan="p")]}
    other_type = {**loose, "housingTypeCode": "46"}  # 다른 주택형의 가격만 있는 행(입주 완료 등)은 걸지 않습니다
    c["supplyGroups"] = [counted, loose, other_type]
    assert [f for f in codes(c) if f[0] == "SUPPLY_PRICE_UNATTACHED"] == [("SUPPLY_PRICE_UNATTACHED", "/supplyGroups/1")]
    # 호실 묶음은 같은 호실의 모집 묶음이 따로 있을 때만 봅니다(2026-11-07 gndc-ddb1 「202-1호」·gndc-12394176 방 종류 「1인실」:
    # 이번에 공급하지 않는 호실은 모집 수 없이 자기 가격만 있음)
    for kind in (None, "1인실"):
        rooms = [{**group, "itemKind": "HOUSING_UNIT", "housingTypeCode": kind} for group in (counted, loose)]
        rooms[0]["unitLabel"], rooms[1]["unitLabel"] = "202-2호", "202-1호"
        c["supplyGroups"] = rooms
        assert [f for f in codes(c) if f[0] == "SUPPLY_PRICE_UNATTACHED"] == []
    rooms[1]["unitLabel"] = "202-2호"  # 같은 호실의 모집 묶음이 다른 표에 따로 있으면 붙지 못한 가격
    assert [f for f in codes(c) if f[0] == "SUPPLY_PRICE_UNATTACHED"] == [("SUPPLY_PRICE_UNATTACHED", "/supplyGroups/1")]


DOCUMENT_TABLE = "\n".join(
    [
        "5. 제출서류",
        "[표 9-1]",
        "| 구 분 | 제 출 서 류 | 발급처 |",
        "| 공통 | 가상 신청서 | 가상공사 |",
        "| 청년 | · 가상 재직증명서 · 가상 소득확인서 | 회사 |",
        "| 신혼 | · 가상 혼인관계증명서 | 행정복지센터 |",
        "- 9 -",
        "--- 10쪽 ---",
        "[표 10-1]",
        "| 수급자 | · 가상 수급자증명서 | 행정복지센터 |",
        "6. 유의사항",
        "[표 10-2]",
        "| 안내 | 신분증을 지참하세요 |",
    ]
)


def document_item(name, evidence):
    return {"name": name, "scope": scope(), "evidenceIds": [evidence]}


def document_candidate(text, names):
    evidence = [{"id": "ev-row", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 1}, "quote": ROW}]
    documents = []
    for n, name in enumerate(names):
        evidence.append({"id": f"ev-doc{n}", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 1}, "quote": name})
        documents.append(document_item(name, f"ev-doc{n}"))
    return candidate(text=text, evidence=evidence, requiredDocuments=documents)


def test_document_table_rows_not_cited_by_any_document_are_suspected():
    text = TABLE + "\n" + DOCUMENT_TABLE
    findings = check_consistency(document_candidate(text, ["가상 신청서"]), SourceBundle(texts={"pdf-text": text}))
    [finding] = [f for f in findings if f.code == "DOCUMENT_OMISSION_SUSPECTED"]
    # 머리 행(띄어 쓴 「제 출 서 류」)으로 찾은 표 3행 + 쪽 표시만 사이에 둔 이어진 표 1행. 다른 절의 표(유의사항)는 세지 않습니다
    assert finding.target == "/quality/coverage/requiredDocuments"
    assert omitted_document_rows(finding.description) == 3
    assert "가상 재직증명서" in finding.description and "신분증" not in finding.description
    # 행마다 서류가 있으면(이름이나 근거 인용이 그 행에 있으면) 알리지 않습니다
    complete = document_candidate(text, ["가상 신청서", "가상 재직증명서", "가상 혼인관계증명서", "가상 수급자증명서"])
    assert ("DOCUMENT_OMISSION_SUSPECTED", "/quality/coverage/requiredDocuments") not in codes(complete, text)
    # 한 행만 빠지면 알리지 않습니다(다른 곳에서 넣은 서류일 때가 많음)
    one_missing = document_candidate(text, ["가상 신청서", "가상 재직증명서", "가상 혼인관계증명서"])
    assert ("DOCUMENT_OMISSION_SUSPECTED", "/quality/coverage/requiredDocuments") not in codes(one_missing, text)


ASSET_DOCUMENT_TABLE = "\n".join(
    [
        "5. 제출서류",
        "[표 9-1]",
        "| 구 분 | 제 출 서 류 | 비 고 |",
        "| 공통 | 가상 자산 보유 사실 확인서 | • 관련 증빙을 첨부하여 제출함 - 임차보증금 및 임대보증금 : 임대차계약서 사본(확정일자 표시 필수) "
        "- 비상장주식 : 증권사 조회내역, 주식보관증 등 가액을 증명할 수 있는 자료 - 장기카드대출(카드론) : 신용카드사가 발급한 증빙서류 |",
    ]
)


def document_omission(text, names):
    found = [f for f in check_consistency(document_candidate(text, names), SourceBundle(texts={"pdf-text": text})) if f.code == "DOCUMENT_OMISSION_SUSPECTED"]
    return found[0] if found else None


def test_attached_evidence_listed_in_a_cited_document_row_is_checked_too():
    # 2026-11-07 23건 대조: 「자산 보유 사실 확인서」 행 비고 칸의 「- 비상장주식 : 증권사 조회내역 …」을 V2 서류 담당이 두 공고에서 나누지 않음.
    # 그 행은 상위 서류가 인용해 행 누락으로는 잡히지 않았습니다
    text = TABLE + "\n" + ASSET_DOCUMENT_TABLE
    finding = document_omission(text, ["가상 자산 보유 사실 확인서"])
    assert finding.target == "/quality/coverage/requiredDocuments" and omitted_document_rows(finding.description) == 3
    assert finding.description.startswith("서류 칸에 나열된 첨부 증빙 3개") and "임대차계약서" in finding.description
    # 증빙 서류를 이름으로 넣었거나(임대차계약서 사본·증권사 조회내역), 그 상황을 적용 대상으로 둔 서류가 있으면(장기카드대출) 다룬 것입니다
    split = document_candidate(text, ["가상 자산 보유 사실 확인서", "임대차계약서 사본", "증권사 조회내역", "카드사 발급 서류"])
    split["requiredDocuments"][3]["appliesTo"] = "장기카드대출이 있는 경우"
    assert ("DOCUMENT_OMISSION_SUSPECTED", "/quality/coverage/requiredDocuments") not in codes(split, text)
    # 서류 표 행 누락과 함께 있으면 한 메모에 둘 다 세고(재확인이 줄었는지 비교), 첨부 증빙을 먼저 적습니다
    both = text + "\n" + "\n".join(DOCUMENT_TABLE.split("\n")[3:6])
    finding = document_omission(both, ["가상 자산 보유 사실 확인서"])
    assert omitted_document_rows(finding.description) == 3 + 3 and "서류 표 행 3개" in finding.description


def test_document_omission_is_a_note_that_is_still_rechecked():
    issue = {"code": "DOCUMENT_OMISSION_SUSPECTED", "target": "/quality/coverage/requiredDocuments", "description": "서류 표 행 3개"}
    assert is_note(issue)
    assert "DOCUMENT_OMISSION_SUSPECTED" in RECHECK_NOTE_CODES


# 대구도시개발공사 행복주택 「대학생 계층 출생자녀 수에 따른 가산 소득·자산 기준」 표 모양(줄임)
CRITERIA_TABLE = "\n".join(
    [
        "《 대학생 계층 출생자녀 수에 따른 가산 소득·자산 기준 》",
        "[표 7-2]",
        "  [열 제목] 1. 구분 | 2. 가구원 수 | 3. 출생자녀 수 (태아포함) | 4. 최종 소득 · 자산기준 › 적용 소득기준 | "
        "5. 최종 소득 · 자산기준 › 적용 자산기준 › 총자산가액",
        "| 구분 | 가구원 수 | 출생자녀 수 (태아포함) | 최종 소득 · 자산기준 |  |",
        "|  |  |  | 적용 소득기준 | 총자산가액 |",
        "| 대학생 | 1인 | 0인 | 120% | 108,000,000원 |",
        "  ↳ 대학생 1인 0인 — 적용 소득기준 120% · 총자산가액 108,000,000원",
        "|  | 2인 | 0인 | 110% | 108,000,000원 |",
        "  ↳ 대학생 2인 0인 — 적용 소득기준 110% · 총자산가액 108,000,000원",
        "|  |  | 1인 | 120% | 119,000,000원 |",
        "  ↳ 대학생 2인 1인 — 적용 소득기준 120% · 총자산가액 119,000,000원",
        "|  | 3인 이상 | 0인 | 100% | 108,000,000원 |",
        "  ↳ 대학생 3인 이상 0인 — 적용 소득기준 100% · 총자산가액 108,000,000원",
        "|  |  | 2인 이상 | 120% | 130,000,000원 |",
        "  ↳ 대학생 3인 이상 2인 이상 — 적용 소득기준 120% · 총자산가액 130,000,000원",
    ]
)


def limit(attribute, value, unit):
    return {"kind": "ATOMIC", "attribute": attribute, "operator": "LTE", "value": value, "unit": unit, "evidenceIds": []}


def criterion(category, attribute, value, unit, *replaced, groups=("대학생",)):
    """기본 기준 조건식과, 값만 바꾸는 예외(발동 조건은 글로만)."""
    exceptions = [{"when": {"status": "UNSTRUCTURED", "expression": None}, "effectExpression": limit(attribute, v, unit)} for v in replaced]
    rule = {"status": "STRUCTURED", "expression": limit(attribute, value, unit)}
    return {"category": category, "rule": rule, "scope": scope(*groups), "evidenceIds": [], "exceptions": exceptions}


def criteria_omission(text, eligibility):
    found = check_consistency(candidate(text=text, eligibility=eligibility), SourceBundle(texts={"pdf-text": text}))
    flagged = [f for f in found if f.code == "CRITERIA_TABLE_OMISSION_SUSPECTED"]
    return flagged[0] if flagged else None


def test_criteria_table_rows_whose_values_no_condition_uses_are_noted():
    # 2026-11-07 23건 원인 분석(dudc-8934): 출생자녀 가산 행의 총자산 기준을 예외로 넣지 않아 V1·V2가 함께 놓쳤는데 잡는 검사가 없었음
    text = TABLE + "\n" + CRITERIA_TABLE
    income = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 120, 110)
    assets = criterion("ASSETS", "TOTAL_ASSETS_KRW", 108_000_000, "KRW")
    finding = criteria_omission(text, [income, assets])
    assert finding.target == "/quality/coverage/eligibility" and is_note(finding.issue())
    assert "2행의 기준값 119,000,000원, 130,000,000원" in finding.description and "「대학생 2인 1인 — 적용 소득기준 120%" in finding.description
    # 가산 행을 예외로 넣었으면 다룬 것입니다
    full = criterion("ASSETS", "TOTAL_ASSETS_KRW", 108_000_000, "KRW", 119_000_000, 130_000_000)
    assert criteria_omission(text, [income, full]) is None


def test_asset_amounts_take_their_unit_from_the_column_title():
    # bmc-72: 금액 칸에 단위가 없고 열 제목 「적용 자산기준금액(원)」에 있음. 재조립한 초안이 자산 조건을 통째로 뺐는데 비율만 보면 못 잡음
    text = "\n".join(
        [
            "[표 8-1]",
            "  [열 제목] 1. 입주자격구분 | 2. 우대항목 › 가구원수 | 3. 최종 소득,자산기준 (한도) › 적용 소득기준 | "
            "4. 최종 소득,자산기준 (한도) › 적용 자산기준금액(원) › 총자산가액",
            "| 나. 국가유공자 등 | 1인 | 90% | 237,000,000 |",
            "|  | 2인 | 90% | 261,000,000 |",
            "|  | 3인 이상 | 90% | 285,000,000 |",
        ]
    )
    income = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 90, "PERCENT")
    finding = criteria_omission(TABLE + "\n" + text, [income, criterion("ASSETS", "TOTAL_ASSETS_KRW", 237_000_000, "KRW")])
    assert "2행의 기준값 261,000,000, 285,000,000" in finding.description
    assert criteria_omission(TABLE + "\n" + text, [income, criterion("ASSETS", "TOTAL_ASSETS_KRW", 237_000_000, "KRW", 261_000_000, 285_000_000)]) is None


# 전북개발공사 분양 공고 「<표3> 전년도 도시근로자 가구원수별 가구당 월평균소득 기준」 모양(공급유형 × 공급방식 × 외벌이·맞벌이, 줄임)
MATRIX_TABLE = "\n".join(
    [
        "(표3) 전년도 도시근로자 가구원수별 가구당 월평균소득 기준 (단위 : 원)",
        "[표 10-1]",
        "  [열 제목] 1. 공급유형 | 2. 공급유형 | 3. 구분 | 4. 1인 | 5. 2인",
        "| 공급유형 |  | 구분 | 1인 | 2인 |",
        "| 일반 공급 | 우선공급 (30%) | 도시근로자 가구원수별 가구당 월평균소득액의 100% | 4,576,036 | 6,452,897 |",
        "  ↳ 일반 공급 우선공급 (30%) 도시근로자 가구원수별 가구당 월평균소득액의 100% — 1인 4,576,036 · 2인 6,452,897",
        "|  |  | 도시근로자 가구원수별 가구당 월평균소득액의 140% (본인 및 배우자가 모두 소득이 있는 경우) |  | 8,799,405 |",
        "  ↳ 일반 공급 우선공급 (30%) 도시근로자 가구원수별 가구당 월평균소득액의 140% (본인 및 배우자가 모두 소득이 있는 경우) — 2인 8,799,405",
        "| 다자녀 가구 특별 공급 | 우선공급(90%) | 도시근로자 가구원수별 가구당 월평균소득액의 120% |  | 9,802,115 |",
        "  ↳ 다자녀 가구 특별 공급 우선공급(90%) 도시근로자 가구원수별 가구당 월평균소득액의 120% — 2인 9,802,115",
        "|  |  | 도시근로자 가구원수별 가구당 월평균소득액의 130% (본인 및 배우자가 모두 소득이 있는 경우) |  | 10,618,958 |",
        "  ↳ 다자녀 가구 특별 공급 우선공급(90%) 도시근로자 가구원수별 가구당 월평균소득액의 130% (본인 및 배우자가 모두 소득이 있는 경우) — 2인 10,618,958",
    ]
)


def test_rows_of_a_supply_type_matrix_left_out_are_noted_but_rows_left_as_text_count():
    # jbdc-16011(V1): 공급유형×공급방식×맞벌이 소득표에서 다자녀 행만 옮김. 공급 물량 몫 「(30%)」은 소득 기준이 아닙니다
    text = TABLE + "\n" + MATRIX_TABLE
    many = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 120, "PERCENT", 130, groups=("다자녀가구 특별공급 우선공급",))
    finding = criteria_omission(text, [many])
    assert "2행의 기준값 100%, 140%" in finding.description and "30%" not in finding.description.split("「")[0]
    # 조건식 없이 글로만 남긴 조건의 원문에 그 비율이 있으면 다룬 것으로 칩니다(조건식 없음은 CRITERION_NOT_STRUCTURED가 따로 봄)
    loose = {"category": "INCOME", "rule": {"status": "UNSTRUCTURED", "expression": None}, "scope": scope("일반공급 우선공급"), "evidenceIds": []}
    loose["originalText"] = "월평균소득의 100% 이하인 자(본인 및 배우자가 모두 소득이 있는 경우 140%)"
    assert criteria_omission(text, [many, loose]) is None


def test_rows_of_a_supply_type_are_missing_even_when_another_type_uses_the_same_percents():
    # 2026-11-07 유료 확인 jbdc-16011: 일반공급·노부모부양 소득 행이 조건에 없는데 같은 100%·140%를 신혼부부 조건이 써서 값만으로는 다룬 것이 됨
    text = TABLE + "\n" + MATRIX_TABLE
    many = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 120, "PERCENT", 130, groups=("다자녀가구 특별공급 우선공급",))
    newlywed = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 140, groups=("신혼부부 특별공급 우선공급",))
    finding = criteria_omission(text, [many, newlywed])
    assert "2행의 기준값 100%, 140%" in finding.description and "기준표 행이 하나도 조건에 없는 대상: 일반 공급." in finding.description
    # 그 공급의 조건이면 다룬 것입니다
    general = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 140, groups=("일반공급 1순위 우선공급",))
    assert criteria_omission(text, [many, general]) is None
    # 「신혼부부 특별공급 일반공급」처럼 다른 공급의 공급방식 이름은, 같은 표에 그 공급이 있으면 이름에서 먼저 나오는 공급(신혼부부)의 조건
    newlywed_rows = "\n".join(
        [
            "| 신혼 부부 특별 공급 | 일반공급(20%) | 도시근로자 가구원수별 가구당 월평균소득액의 100% |  | 8,168,429 |",
            "|  |  | 도시근로자 가구원수별 가구당 월평균소득액의 140% (본인 및 배우자가 모두 소득이 있는 경우) |  | 11,435,801 |",
        ]
    )
    method = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 140, groups=("신혼부부 특별공급 일반공급(20%)",))
    finding = criteria_omission(text + "\n" + newlywed_rows, [many, method])
    assert "2행의 기준값 100%, 140%" in finding.description and "조건에 없는 대상: 일반 공급." in finding.description


def test_list_marks_and_a_one_target_table_tie_rows_to_their_conditions():
    # dcco-24812: 표 「차. 일반입주자」 ↔ 조건 「일반공급 2순위 차목」(이름이 달라 목록 기호로만 이어짐)
    marked = "\n".join(
        [
            "[표 8-1]",
            "  [열 제목] 1. 입주자격 | 2. 가구원수 | 3. 적용 소득기준",
            "| 차. 일반입주자 | 1인 | 70% |",
            "|  | 2인 | 60% |",
            "| 타. 장애인 | 1인 | 120% |",
            "|  | 2인 | 100% |",
        ]
    )
    ta = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 120, groups=("일반공급 2순위 타목 장애인",))
    cha = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 50, "PERCENT", 70, 60, groups=("일반공급 2순위 차목 소득 50% 이하",))
    assert criteria_omission(TABLE + "\n" + marked, [ta, cha]) is None
    unmarked = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 50, "PERCENT", 70, 60, groups=("일반공급 2순위 소득 50% 이하",))
    assert "조건에 없는 대상: 차. 일반입주자." in criteria_omission(TABLE + "\n" + marked, [ta, unmarked]).description
    # dudc-8934·bmc-75: 청년 표의 「세대원(본인)」 행. 표에서 맞춰진 대상 이름이 「청년」 하나면 그 표의 행은 모두 청년 조건으로 봅니다
    youth = "\n".join(
        [
            "[표 10-1]",
            "  [열 제목] 1. 구분 | 2. 가구원 수 | 3. 적용 소득기준",
            "| 세대주인 청년 (세대기준) | 1인 | 120% |",
            "|  | 2인 | 110% |",
            "| 세대원(본인) | 1인 | 120% |",
            "|  | 2인 | 110% |",
        ]
    )
    young = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 120, 110, groups=("청년",))
    student = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", groups=("대학생",))
    assert criteria_omission(TABLE + "\n" + youth, [young, student]) is None


def test_reference_rent_prose_and_schedule_tables_are_not_criteria_tables():
    tables = "\n".join(
        [
            # 단계별 참고 소득표: 대상 칸이 하나뿐
            "[표 11-2]",
            "  [열 제목] 1. 구분 | 2. 소득기준 | 3. 1인 | 4. 2인",
            "| 구분 | 소득기준 | 1인 | 2인 |",
            "| 도시근로자 월평균소득 | 80% | 3,050,690 | 4,693,016 |",
            "|  | 90% | 3,432,027 | 5,279,643 |",
            "",
            # 소득 구간별 임대조건
            "[표 12-1]",
            "  [열 제목] 1. 소득 구간 | 2. 임대보증금 | 3. 월임대료",
            "| 소득 50% 이하 | 10,000,000 | 100,000 |",
            "| 소득 70% 이하 | 12,000,000 | 120,000 |",
            "",
            # 문단을 칸에 담은 표(bmc-71)
            "[표 6-1]",
            "| 구분 | 소득 및 자산보유 기준 |",
            "| 소득 | 2024년도 도시근로자 가구원수별 가구당 월평균 소득(원) 가구원수 70% 80% 90% 참고사항 1인 2,518,715 2,878,531 "
            "3,238,348 2인 3,833,902 4,381,602 4,929,303 (1인 20%, 2인 10% 가산) |",
            "| 자산 | 세대 구성원 전원이 보유한 총자산의 합산 금액이 3억 3,700만원 이하일 것 ※ 총자산: 부동산, 자동차, 금융자산, "
            "일반 자산을 합산한 금액에서 부채를 차감한 금액(소득 50% 이하 가구 포함) |",
            "",
            # 접수 일정(gh-808)
            "[표 4-1]",
            "| 신청자격 | 신청접수 |",
            "| 진건B1블록 월평균소득100%이하 1순위 | ‘26.8.24.(월) 10:00~18:00 |",
            "| 진건B1블록 월평균소득100%이하 2·3순위 | ‘26.8.25.(화) 10:00~18:00 |",
        ]
    )
    income = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 120, "PERCENT")
    assert criteria_omission(TABLE + "\n" + tables, [income]) is None
