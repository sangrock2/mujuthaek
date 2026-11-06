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
        "housingTypeCode": "39",
        "unitLabel": None,
        "counts": [{"kind": "OFFERED", "value": 100, "scope": scope(), "evidenceIds": []}],
    }
    loose = {**c["supplyGroups"][0], "housingTypeCode": "39.70", "unitLabel": None, "prices": [price("DEPOSIT", 1_000_000, plan="p")]}
    other_type = {**loose, "housingTypeCode": "46"}  # 다른 주택형의 가격만 있는 행(입주 완료 등)은 걸지 않습니다
    c["supplyGroups"] = [counted, loose, other_type]
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


def test_document_omission_is_a_note_that_is_still_rechecked():
    issue = {"code": "DOCUMENT_OMISSION_SUSPECTED", "target": "/quality/coverage/requiredDocuments", "description": "서류 표 행 3개"}
    assert is_note(issue)
    assert "DOCUMENT_OMISSION_SUSPECTED" in RECHECK_NOTE_CODES
