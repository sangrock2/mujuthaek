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


def test_a_subgroup_condition_put_on_every_applicant_is_suspected():
    # 2026-11-08 V2 유료 확인 bmc-106: 1순위 자격(가~자목 중 하나)의 계층 조건을 대상 없이 넣어 나이 65세 이상·부모 나이·나·마·바·아목만의
    # 소득 상한이 신청자 전체 조건으로 게시됨(65세 미만은 모두 「지원 불가」)
    def atom(attribute, operator, value, subject="APPLICANT"):
        return {"kind": "ATOMIC", "subject": subject, "attribute": attribute, "operator": operator, "value": value}

    def item(expression, *groups, original="원문"):
        rule = {"status": "STRUCTURED", "expression": expression}
        return {"category": "OTHER", "scope": scope(*groups), "evidenceIds": [], "originalText": original, "rule": rule}

    def flagged(*items):
        found = check_consistency(candidate(eligibility=list(items)), SourceBundle(texts={"pdf-text": TABLE}))
        return {f.target: f for f in found if f.code == "SCOPE_SUBGROUP_SUSPECTED"}

    adult, senior = item(atom("AGE_YEARS", "GTE", 19)), item(atom("AGE_YEARS", "GTE", 65), original="자. 65세 이상인 사람으로서 수급권자")
    found = flagged(adult, senior)
    assert list(found) == ["/eligibility/1"] and "만 나이" in found["/eligibility/1"].description and "19, 65" in found["/eligibility/1"].description
    assert not is_note(found["/eligibility/1"].issue())  # 사람 확인(그 조건만 보류). 경계가 더 좁은 쪽만(넓은 쪽은 판정을 바꾸지 않음)
    assert flagged(adult, item(atom("AGE_YEARS", "GTE", 65), "65세 이상 수급권자")) == {}  # 계층 대상이면 그 계층에만
    assert flagged(adult, item({"kind": "ALL", "children": [atom("AGE_YEARS", "BETWEEN", [19, 39])]})) == {}  # 하한이 같고 상한은 하나
    flipped = item({"kind": "ALL", "children": [atom("AGE_YEARS", "LTE", 19), atom("AGE_YEARS", "LTE", 39)]})
    assert flagged(flipped) == {}  # 한 항목 안의 경계 둘(뒤집힌 연산자)은 방향 대조가 봄
    assert list(flagged(*(item(atom("INCOME_BENCHMARK_PERCENT", "LTE", value)) for value in (100, 70)))) == ["/eligibility/1"]  # 상한은 작은 쪽
    parents = item(atom("AGE_YEARS", "GTE", 65, subject="PARENTS"), original="사. 65세 이상의 직계존속을 부양하는 사람")
    assert "부모 나이" in flagged(parents)["/eligibility/0"].description
    listed = item(atom("INCOME_BENCHMARK_PERCENT", "LTE", 70), original="※ 위 자격 중 ‘나’목, ‘마’목, ‘바’목, ‘아’목의 경우에는 월평균소득 70% 이하")
    assert "나목, 마목, 바목, 아목" in flagged(listed)["/eligibility/0"].description
    one = item(atom("INCOME_BENCHMARK_PERCENT", "LTE", 70), original="「공공주택 특별법 시행규칙」 별표3 사목에 따라 다음 각 목의 요건을 갖추고 목적에 맞게")
    assert flagged(one) == {}  # 목 하나·「각 목」·「목적」은 목록의 일부 계층을 가리키는 것이 아님
    # 다시 확인한 실행: 원문 글을 「총자산가액 기준 … 이하」로 좁혀 적어도 근거 인용이 일부 목을 가리키면 걸림
    line = "1. 자산기준(총자산/자동차)이 적용되는 자격 - 나목(국가유공자등), 마목(북한이탈주민), 바목(장애인)"
    text = TABLE + "\n" + line
    start = text.index(line)
    quoted = {"id": "ev-assets", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + len(line)}, "quote": line}
    assets = {**item(atom("TOTAL_ASSETS_KRW", "LTE", 245_000_000), original="총자산가액 기준 24,500만원 이하"), "evidenceIds": ["ev-assets"]}
    found = check_consistency(candidate(text=text, eligibility=[assets], evidence=[quoted]), SourceBundle(texts={"pdf-text": text}))
    assert [f.target for f in found if f.code == "SCOPE_SUBGROUP_SUSPECTED"] == ["/eligibility/0"]


def test_child_age_on_every_applicant_and_an_age_boundary_day_go_to_review():
    # 2026-11-09 유료 측정 jbdc-16011: 「6세 이하(만7세미만) 의 자녀를 둔」(신혼부부 정의의 일부)을 대상 없이 넣어 모두에게 자녀 요건이 걸림.
    # 신생아 「2세 미만(2세가 되는 날을 포함)」은 만 나이 조건식으로 그날을 담지 못함(사용자 결정: 확인 필요)
    def child(operator, value, *groups, original="6세 이하(만7세미만 2019.10.09일 이후 출생자) 의 자녀를 둔"):
        expression = {"kind": "ATOMIC", "subject": "HOUSEHOLD", "attribute": "YOUNGEST_CHILD_AGE_YEARS", "operator": operator, "value": value}
        return {
            "category": "CHILDREN",
            "scope": scope(*groups),
            "evidenceIds": [],
            "originalText": original,
            "rule": {"status": "STRUCTURED", "expression": expression},
        }

    def found(*items, targets=("신혼부부", "신생아")):
        c = candidate(eligibility=list(items), notice={"counts": [], "targetGroups": list(targets)})
        return [f for f in check_consistency(c, SourceBundle(texts={"pdf-text": TABLE})) if f.code in ("SCOPE_SUBGROUP_SUSPECTED", "AGE_BOUNDARY_DAY")]

    [scoped] = found(child("LT", 7))
    assert (scoped.code, scoped.target) == ("SCOPE_SUBGROUP_SUSPECTED", "/eligibility/0") and "자녀 나이" in scoped.description
    assert found(child("LT", 7, "신혼부부")) == []  # 그 대상에만
    assert found(child("LT", 2), targets=("신생아 가구",)) == []  # 공고 대상이 하나뿐이면 그 대상의 요건이 곧 모두의 요건
    newborn = child("LT", 2, "신생아", original="① 입주자모집공고일 현재 2세 미만(2세가 되는 날을 포함)의 자녀(태아 포함)가 있는 무주택세대구성원")
    [day] = found(newborn)
    assert (day.code, day.target) == ("AGE_BOUNDARY_DAY", "/eligibility/0") and "「2세가 되는 날을 포함」" in day.description
    assert not is_note(day.issue())  # 사람 확인(그 조건만 보류)


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


def test_documents_of_a_whole_table_merged_into_one_row_are_checked_by_name():
    # 2026-11-09 유료 측정 jbdc-16011: 앞 표 마지막 칸에 합쳐진 <표9>(재직증명서·건강보험자격득실확인서 …)를 묶음 서류 「소득세납부 입증서류
    # (아래 <표9> 참고)」 하나가 인용해, 행은 인용된 것으로 보여 서류 8개가 빠져도 안 잡혔음
    row = (
        "| 공통 | ※ 직인 날인 서류만 인정합니다. <표9> 소득세납부 입증 제출서류 ① 재직증명서 근로자 ② 건강보험자격득실확인서 ① 사업자등록증 "
        "자영업자 ② 원천징수영수증 ③ 소득금액증명원 ④ 납부증명서 | 세무서 |"
    )
    text = TABLE + "\n" + "\n".join(["5. 제출서류", "[표 9-1]", "| 구 분 | 제 출 서 류 | 발급처 |", row])
    umbrella = "소득세납부 입증서류 (아래 <표9> 참고)"

    def note(*names):
        found = document_omission(text, list(names))
        return found.description if found else ""

    assert "서류 이름이 여럿 든 표 행의 서류 6개가 서류 목록에 없습니다" in note(umbrella) and "「재직증명서」" in note(umbrella)
    listed = [umbrella, "재직증명서", "건강보험자격득실확인서", "사업자등록증 사본", "원천징수영수증 또는 소득금액증명원", "납부증명서"]
    assert "여럿 든 표 행" not in note(*listed)  # 이름마다 넣었으면(이름을 품은 서류 포함) 없음
    assert "여럿 든 표 행" not in note(umbrella, "재직증명서", "건강보험자격득실확인서", "사업자등록증")  # 빠진 이름이 3개면 다른 이름일 수 있어 보지 않음


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


def test_a_missed_row_whose_documents_come_after_a_long_note_shows_the_documents():
    # 2026-11-08 최종 비교 jbdc-16011: 원문 변환에서 서류 표(<표9>, 재직증명서 등 8개)가 앞 표의 마지막 칸 하나에 합쳐졌는데, 행 앞 60자
    # 「※ 직인날인이 없거나…」 주의 문구만 보여 V2 서류 담당이 서류 행으로 보지 않고 넘김
    merged = (
        "| ※ 직인 날인이 없거나 직인 날인된 서류를 팩스로 받은 경우에도 정당한 서류로 인정받지 않으니 유의하시기 바랍니다. "
        "<표9> 소득세 납부 입증 서류 해당여부 서류구분 ① 가상 근로증명서 근로자 ② 가상 보험확인서 |"
    )
    lines = DOCUMENT_TABLE.split("\n")
    finding = document_omission(TABLE + "\n" + "\n".join([*lines[:4], merged, lines[5]]), ["가상 신청서"])
    assert omitted_document_rows(finding.description) == 2
    assert "…" in finding.description and "① 가상 근로증명서" in finding.description and "※ 직인" not in finding.description
    assert "「신혼 · 가상 혼인관계증명서 행정복지센터」" in finding.description  # 서류 낱말이 앞에 있는 행은 그대로 앞부분


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


def criteria_findings(text, eligibility):
    found = check_consistency(candidate(text=text, eligibility=eligibility), SourceBundle(texts={"pdf-text": text}))
    return {f.code: f for f in found if f.code in ("CRITERIA_GROUP_OMISSION_SUSPECTED", "CRITERIA_TABLE_OMISSION_SUSPECTED")}


def criteria_omission(text, eligibility):
    """기준표 누락 알림 하나: 대상이 통째로 빠진 것(CRITERIA_GROUP_OMISSION_SUSPECTED)이 있으면 그것, 없으면 행 일부가 빠진 것."""
    flagged = criteria_findings(text, eligibility)
    return flagged.get("CRITERIA_GROUP_OMISSION_SUSPECTED") or flagged.get("CRITERIA_TABLE_OMISSION_SUSPECTED")


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
    assert finding.code == "CRITERIA_GROUP_OMISSION_SUSPECTED" and "30%" not in finding.description.split("「")[0]
    assert finding.description.startswith("원문 자격 기준표에서 조건이 하나도 없는 대상: 일반 공급(2행, 기준값 100%, 140%)")
    # 조건식 없이 글로만 남긴 조건의 원문에 그 비율이 있으면 다룬 것으로 칩니다(조건식 없음은 CRITERION_NOT_STRUCTURED가 따로 봄)
    loose = {"category": "INCOME", "rule": {"status": "UNSTRUCTURED", "expression": None}, "scope": scope("일반공급 우선공급"), "evidenceIds": []}
    loose["originalText"] = "월평균소득의 100% 이하인 자(본인 및 배우자가 모두 소득이 있는 경우 140%)"
    assert criteria_omission(text, [many, loose]) is None


def test_rows_of_a_supply_type_are_missing_even_when_another_type_uses_the_same_percents():
    # 2026-11-07 유료 확인 jbdc-16011: 일반공급·노부모부양 소득 행이 조건에 없는데 같은 100%·140%를 신혼부부 조건이 써서 값만으로는 다룬 것이 됨
    text = TABLE + "\n" + MATRIX_TABLE
    many = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 120, "PERCENT", 130, groups=("다자녀가구 특별공급 우선공급",))
    newlywed = criterion("INCOME", "INCOME_BENCHMARK_PERCENT", 100, "PERCENT", 140, groups=("신혼부부 특별공급 우선공급",))
    found = criteria_findings(text, [many, newlywed])
    assert list(found) == ["CRITERIA_GROUP_OMISSION_SUSPECTED"]  # 행 일부만 빠진 대상은 없음
    assert "조건이 하나도 없는 대상: 일반 공급(2행, 기준값 100%, 140%)" in found["CRITERIA_GROUP_OMISSION_SUSPECTED"].description
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
    assert "조건이 하나도 없는 대상: 일반 공급(2행, 기준값 100%, 140%)" in finding.description


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
    assert "조건이 하나도 없는 대상: 차. 일반입주자(2행" in criteria_omission(TABLE + "\n" + marked, [ta, unmarked]).description
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


def test_image_quotes_also_written_outside_the_reading_are_not_image_evidence():
    # 2026-11-09 23건 sh-311005: 표지 그림의 제목 글을 공고 근거로 써 공고 전체가 검수로 감. 같은 제목이 게시글 제목(그림 밖 글)에 있음
    head = "=== 그림 판독 공고.pdf 1쪽 (AI가 그림 속 글자를 옮김) ===\n"
    title = "[제목] [가상 사회주택]가상스페이스 신림3호점_가상 입주자 모집 공고"
    text = f"{title}\n--- 1쪽 ---\n{head}가상스페이스 신림3호점\n입주자 모집공고\n월평균소득 70% 이하\n공고"

    def ev(id_, quote):
        at = text.index(quote, text.index(head))  # 그림 판독 묶음 안의 글
        return {"id": id_, "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": at, "end": at + len(quote)}, "quote": quote}

    income = {"category": "INCOME", "rule": {"status": "STRUCTURED", "expression": None}, "scope": scope(), "evidenceIds": ["ev-income"]}
    base = {
        "evidence": [ev("ev-title", "가상스페이스 신림3호점"), ev("ev-kind", "입주자 모집공고"), ev("ev-income", "월평균소득 70% 이하")],
        "notice": {"counts": [], "evidenceIds": ["ev-title", "ev-kind"]},
        "locations": [],
        "supplyGroups": [],
        "schedules": [],
        "eligibility": [income],
        "selectionRules": [],
        "requiredDocuments": [],
        "quality": {"coverage": {s: {"status": "EXTRACTED"} for s in ("eligibility", "requiredDocuments", "schedules")}, "missingFields": []},
    }
    found = {(f.code, f.target) for f in check_consistency(base, SourceBundle(texts={"pdf-text": text}, pdfs={"file-1": b"pdf"}))}
    assert ("EVIDENCE_FROM_IMAGE", "/notice") not in found  # 띄어쓰기만 다른 같은 글이 그림 밖에 있음
    assert ("EVIDENCE_FROM_IMAGE", "/eligibility/0") in found  # 그림에만 있는 글은 그대로 사람 확인
    short = base | {"evidence": [*base["evidence"], ev("ev-short", "공고")], "notice": {"counts": [], "evidenceIds": ["ev-short"]}}
    found = {(f.code, f.target) for f in check_consistency(short, SourceBundle(texts={"pdf-text": text}, pdfs={"file-1": b"pdf"}))}
    assert ("EVIDENCE_FROM_IMAGE", "/notice") in found  # 짧은 글은 우연히 겹칠 수 있어 그림 근거로 봄

    # 첨부 PDF가 있으면 원문은 PDF 글자뿐이라 게시글 제목이 원문에 없음: 수집기가 읽은 게시글 제목(원본 참조)으로 확인합니다
    pdf_only = text.replace(title + "\n", "")
    located = [
        {**e, "locator": {**e["locator"], "start": pdf_only.index(e["quote"]), "end": pdf_only.index(e["quote"]) + len(e["quote"])}} for e in base["evidence"]
    ]
    moved = base | {"evidence": located}
    alone = {(f.code, f.target) for f in check_consistency(moved, SourceBundle(texts={"pdf-text": pdf_only}, pdfs={"file-1": b"pdf"}))}
    assert ("EVIDENCE_FROM_IMAGE", "/notice") in alone
    titled = moved | {"sourceReferences": [{"sourceTitle": title.removeprefix("[제목] ")}]}
    found = {(f.code, f.target) for f in check_consistency(titled, SourceBundle(texts={"pdf-text": pdf_only}, pdfs={"file-1": b"pdf"}))}
    assert ("EVIDENCE_FROM_IMAGE", "/notice") not in found


def test_criterion_the_source_waives_is_not_held_for_a_value_in_a_neighbouring_row():
    # 2026-11-09 23건 jbdc-15611: 「자산기준 : 배제」가 근거로 붙은 옆 행의 「345백만원 이하」 때문에 조건식 없음으로 보류됨
    text = TABLE + "\n| 총자산 | 345백만원 이하 |\n| 자산기준 : 배제 |"
    row = "| 총자산 | 345백만원 이하 |"
    evidence = {"id": "ev-assets", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": text.index(row), "end": text.index(row) + len(row)}}
    waived = {"category": "ASSETS", "rule": {"status": "UNSTRUCTURED", "expression": None}, "scope": scope(), "evidenceIds": ["ev-assets"]}
    waived["originalText"] = "자산기준 : 배제"
    written = waived | {"originalText": "총자산 345백만원 이하(단, 수급자는 배제)"}
    for item, held in ((waived, False), (written, True)):
        c = candidate(text=text, eligibility=[item], evidence=[evidence | {"quote": row}])
        found = [f.target for f in check_consistency(c, SourceBundle(texts={"pdf-text": text})) if f.code == "CRITERION_NOT_STRUCTURED"]
        assert found == (["/eligibility/0"] if held else [])


def test_forms_named_as_attached_sheets_in_prose_must_be_in_the_document_list():
    # 2026-11-09 23건 sh-311005: 글 속 「입주 신청서(별지 1호), 개인 정보 동의서(별지 2호), 자기소개서(별지 3호) 작성 후 …」를 V2 서류 담당이 넣지 않음
    text = TABLE + "\n가상 서류를 작성하여 입주 신청서(별지 1호), 개인 정보 동의서(별지 2호), 자기소개서(별지 3호) 작성 후 이메일로 제출"
    finding = document_omission(text, ["가상 신청서"])
    assert finding is not None and "별지 서식으로 든 서류 3개" in finding.description and "개인 정보 동의서(별지 2호)" in finding.description
    assert is_note(finding.issue())  # 빠진 값이라 표시만(담당에게는 알림)
    assert document_omission(text, ["입주신청서", "개인정보 동의서(별지 2호)", "자기소개서"]) is None


def test_documents_asked_for_in_prose_must_be_in_the_document_list():
    # 2026-11-09 23건 남은 서류 놓침: gbdc-a909 「신청 시 희망주택목록을 함께⏎제출」, jbdc-15611 「입주대기 취소 신청서 제출 후 신청 가능」,
    # sh-310976 「• 입주신청확인서제출」을 V2 서류 담당이 넣지 않음
    asked = [
        "해당 모집단위 내 주택을 사전 열람하여 신청 시 희망주택목록을 함께",
        "제출해야 하며, 순번에 따라 배정합니다.",
        "다만 현재 입주대기자는 입주대기 취소 신청서 제출 후 신청 가능합니다.",
        "※ 외국인은 신청불가 합니다.",  # 다음 문장의 「불가」는 앞 문장의 제출과 상관없음
        "선정된예비입주자는정해진일정까지아래절차이행 • 입주신청확인서제출 • 입주신청확인금입금",
    ]
    not_asked = [
        "공고문을 해당 지자체(시·군·자치구)로부터 받아서 제출",  # 「받아서」는 서류가 아님
        "하는 자가 이 동의서 제출을 2회 거부하면",  # 이미 넣은 「동의서」
        "추후 청약신청납입확인서를 제출하더라도 인정하지 않습니다.",
        "✅ 신청서 제출 전에 신청자격기준을 확인하시기 바랍니다.",
        "▫ 청약신청서 제출 후 신청당일 마감시간 전까지만 온라인 신청내용 취소 및 삭제 후 재신청 가능",
        "| 8단계 | 청약신청서 제출 |",  # 절차 표의 단계
        "자료를 수정한 후 동 기관의 확인서를 제출하여 소명",
    ]
    text = TABLE + "\n" + "\n".join([*asked, *not_asked])
    finding = document_omission(text, ["개인정보 수집·이용 동의서"])
    assert finding is not None and "글에서 내라고 한 서류 3개" in finding.description
    for name in ("희망주택목록", "입주대기 취소 신청서", "입주신청확인서"):
        assert f"「{name}」" in finding.description
    assert document_omission(text, ["개인정보 수집·이용 동의서", "계약 희망 주택 목록", "입주대기 취소 신청서", "입주신청확인서"]) is None


def schedule_item(kind, start, end=None):
    return {
        "kinds": [kind],
        "startsAt": {"precision": "DAY" if len(start) == 10 else "MONTH", "value": start},
        "endsAt": {"precision": "DAY" if len(end) == 10 else "MONTH", "value": end} if end else None,
        "scope": scope(),
        "evidenceIds": [],
    }


def test_dated_steps_written_as_numbered_lines_must_be_in_the_schedules():
    # 2026-11-09 23건 sh-311087: 일정표 밖 「나. 계약체결: 2027. 1. 20.(수) ~」「라. 입주기간: 2027. 2~4월 중」을 V2 일정 담당이 넣지 않음
    text = TABLE + "\n".join(
        [
            "",
            "가. 당첨자 발표: 2026. 12. 30.(수)",
            "나. 계약체결: 2027. 1. 20.(수) ~ 2027. 1. 22.(금) (변동가능)",
            "라. 입주기간: 2027. 2~4월 중 (변동 가능)",
            "| 가상단지 | 입주월 2012. 8. | 30년 임대 |",  # 단지가 처음 입주한 달: 이번 모집의 단계가 아님
            "입주자모집공고일(2026.10.08) 현재 만19세 이상",  # 「입주자」는 사람
            "임대차 계약기간: 2027. 2. 1. ~ 2029. 1. 31.",  # 임대 기간은 단계가 아님
            "소득은 2025. 12. 31. 기준으로 산정",
        ]
    )
    listed = [schedule_item("ANNOUNCEMENT", "2026-10-08"), schedule_item("WINNER_ANNOUNCEMENT", "2026-12-30")]

    def omission(schedules):
        found = [
            f
            for f in check_consistency(candidate(text=text, schedules=schedules), SourceBundle(texts={"pdf-text": text}))
            if f.code == "SCHEDULE_OMISSION_SUSPECTED"
        ]
        return found[0] if found else None

    finding = omission(listed)
    assert finding.target == "/quality/coverage/schedules" and is_note(finding.issue())
    assert "단계 2개" in finding.description and "계약체결: 2027. 1. 20." in finding.description and "입주기간: 2027. 2~4월" in finding.description
    complete = [*listed, schedule_item("CONTRACT", "2027-01-20", "2027-01-22"), schedule_item("MOVE_IN", "2027-02", "2027-04")]
    assert omission(complete) is None


def test_dated_steps_in_unrolled_timelines_tables_and_yearless_dates_must_be_in_the_schedules():
    # 2026-11-09 23건 남은 일정 놓침: umca-4439 순서도가 풀려 단계 이름 줄과 날짜 줄이 따로(입주자격 조사·소명 심사), gndc-1239 연도 없는
    # 「서류심사 (7.10. ~ 7.14.)」, gh-809 일정 표의 「적격여부 검수」 칸(단계 낱말이 아닌 칸도 같은 표라 봄)
    timeline = ["입주자격 조사 소명 심사 확정명단 발표", "(개별통보)", "2026. 7. 10. 2026. 7. 22. ~ 24. 2026. 7. 27. ~ 2026. 8. ~ 2026. 9."]
    yearless = ["| 서류심사 (7.30. ~ 7.31.) | - 서류검토 및 적격여부판단 |"]
    table = [
        "| 신청접수 |  | 적격여부 검수 |  | 당첨자 발표 |",
        "| 2026.07.22.(수) ~ 2026.07.24.(금) |  | 2026.08.03(월) ~ 2026.08.17(월) |  | 2026.09.15.(화) 이후 |",
    ]
    noise = [
        "전용 36.29㎡, 접수 인원은 공급 호수의 2.5배수",  # 면적·배수는 연도 없는 날짜가 아님
        "1985.11.07 ~ 2007.11.06 출생자",  # 날짜 줄이 아니고 공고일보다 한참 앞섬
    ]
    listed = [
        schedule_item("ANNOUNCEMENT", "2026-07-10"),
        schedule_item("APPLICATION", "2026-07-22", "2026-07-24"),
        schedule_item("WINNER_ANNOUNCEMENT", "2026-09"),
    ]

    def omission(lines):
        text = TABLE + "\n".join(["", *lines])
        found = [
            f
            for f in check_consistency(candidate(text=text, schedules=listed), SourceBundle(texts={"pdf-text": text}))
            if f.code == "SCHEDULE_OMISSION_SUSPECTED"
        ]
        return found[0].description if found else ""

    assert "단계 2개" in omission(timeline) and "입주자격 조사 소명 심사 확정명단 발표 … 2026. 7. 27" in omission(timeline)  # 7.10·7.22·9월은 있음
    assert "단계 1개" in omission(yearless) and "서류심사 (7.30." in omission(yearless)
    assert "단계 3개" in omission(table) and "적격여부 검수 … 2026.08.03" in omission(table)  # 칸 이름으로 보여 줌
    assert omission(noise) == ""
    assert "단계 6개" in omission(timeline + yearless + table + noise)  # 표 행이 날짜만 있는 줄이어도 같은 날짜는 한 번만


def unit_group(label, value=1, kind="HOUSING_UNIT"):
    counts = [{"kind": "OFFERED", "value": value, "scope": scope("1인 가구"), "evidenceIds": []}]
    return {"housingTypeCode": None, "unitLabel": label, "exclusiveAreaSqm": 24.83, "itemKind": kind, "scope": scope(), "prices": [], "counts": counts}


def test_rooms_counted_one_each_beyond_the_notice_total_are_held():
    # 2026-11-09 23건 sh-311005: 「모집 세대수 원룸1세대추가모집」인데 수량 열 없는 호실 표 두 개의 24행을 모두 모집 1로 셈(대상 「1인 가구」가 붙어
    # 합계 검사는 건너뜀). 어느 호실이 이번 모집인지 정할 수 없어 그 수량을 보류합니다
    total = {"kind": "OFFERED", "value": 1, "scope": {"targetGroups": [], "supplyCategory": "ALL"}}
    rooms = [unit_group(label) for label in ("201", "202", "203", "201", "202", "203")]  # 같은 호실이 표 두 개에 나옴
    found = check_consistency(candidate(notice={"counts": [total]}, supplyGroups=rooms), SourceBundle(texts={"pdf-text": TABLE}))
    held = [f for f in found if f.code == "UNIT_COUNTS_EXCEED_TOTAL"]
    assert [f.target for f in held] == [f"/supplyGroups/{g}/counts" for g in range(6)] and not is_note(held[0].issue())
    assert "호실 3곳" in held[0].description
    # 서로 다른 호실 수가 공고 전체 모집 수 이하이거나(같은 호실이 두 표에 나온 것뿐), 주택형 묶음이면 보지 않습니다
    for notice_total, groups in ((total | {"value": 3}, rooms), (total, [unit_group("59A", 10, "HOUSING_TYPE"), unit_group("59B", 5, "HOUSING_TYPE")])):
        found = check_consistency(candidate(notice={"counts": [notice_total]}, supplyGroups=groups), SourceBundle(texts={"pdf-text": TABLE}))
        assert not [f for f in found if f.code == "UNIT_COUNTS_EXCEED_TOTAL"]
