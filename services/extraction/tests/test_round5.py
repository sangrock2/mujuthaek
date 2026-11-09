"""다섯 번째 시험 채점(2026-10-24)의 일반 규칙: 전환안 검산 기준, 방향별 한도 금액, 한도 칸 앞 금액 쌍은 기본 조건,
가로 병합으로 복제된 두 금액 칸, 붙인 가격의 중복 거르기·층 이름. 합성 표만 씁니다. AI·네트워크 호출 없음."""

from test_round4 import assembled_extra
from test_schedule_details import document
from test_supply_tables import column

from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.assemble.conversion import SAME_AS_BASE, plan_directions

# ---- 1. 전환안 검산 기준 ----


def price(plan, stage, kind, amount, unit="원"):
    return {"pricePlanId": plan, "priceStage": stage, "kind": kind, "sourceAmount": amount, "sourceUnit": unit, "scope": {"targetGroups": []}}


def test_deposit_only_standard_plan_is_not_a_base():
    # 전세 요금안(보증금만)이 기본안으로 같이 붙어도 보증금·월세가 다 있는 기본안으로 검산합니다
    prices = [
        price("a", "STANDARD", "DEPOSIT", "12,614"),
        price("a", "STANDARD", "MONTHLY_RENT", "57,810"),
        price("jeonse", "STANDARD", "DEPOSIT", "40,000"),
        price("up", "CONVERSION_DEPOSIT_UP", "DEPOSIT", "12,614"),
        price("up", "CONVERSION_DEPOSIT_UP", "MONTHLY_RENT", "57,810"),
    ]
    assert plan_directions(prices) == {"up": ("CONVERSION_DEPOSIT_UP", SAME_AS_BASE)}


def test_group_without_base_borrows_the_base_of_the_same_type():
    own = [price("d", "CONVERSION_DEPOSIT_DOWN", "DEPOSIT", "47,891"), price("d", "CONVERSION_DEPOSIT_DOWN", "MONTHLY_RENT", "27,880")]
    sibling = [price("s", "STANDARD", "DEPOSIT", "47,891"), price("s", "STANDARD", "MONTHLY_RENT", "27,880")]
    assert plan_directions(own) == {"d": ("CONVERSION_DEPOSIT_DOWN", "UNCHECKED")}
    assert plan_directions(own, sibling) == {"d": ("CONVERSION_DEPOSIT_DOWN", SAME_AS_BASE)}


# ---- 2·10. 한도 칸 ----

LIMIT_COLUMNS = [
    column(1, "HOUSING_TYPE"),
    column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD"),
    column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="기본", stage="STANDARD"),
    column(4, "CONVERSION_LIMIT"),
    column(5, "PRICE", pk="DEPOSIT", unit="천원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
    column(6, "PRICE", pk="MONTHLY_RENT", unit="원", plan="최대 전환", stage="CONVERSION_DEPOSIT_UP"),
]


def limit_part(limit, deposits, rents, columns=LIMIT_COLUMNS, titles=None):
    titles = titles or ("형", "보증금", "월세", "한도", "전환 보증금", "전환 월세")
    rows = (titles, ("21A", "12,614", "57,810", limit, deposits, rents))
    table = st.Table("6-1", 6, "임대조건", rows[0], rows, ((0, 1, 2, 3, 4, 5), (6, 7, 8, 9, 10, 11)))
    mapping = {"tables": [{"table": "6-1", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": columns}]}
    [group] = st.build_part([table], mapping, "pdf-text")["supplyGroups"]
    return [(p["kind"], p["sourceAmount"], p["priceStage"]) for p in group["prices"]]


def test_direction_without_amount_in_a_two_sign_limit_cell_makes_no_plan():
    prices = limit_part("(+) - (-) 10,000", "12,614 2,614", "57,810 86,970")
    assert [p for p in prices if p[2] == "CONVERSION_DEPOSIT_UP"] == []
    assert ("DEPOSIT", "2,614", "CONVERSION_DEPOSIT_DOWN") in prices


def test_direction_amounts_reads_each_sign():
    assert st._direction_amounts("(+) - (-) 10,000") == {"(+)": False, "(-)": True}
    assert st._direction_amounts("(+) 5,000 (-) 10,000") == {"(+)": True, "(-)": True}


def test_amount_pair_before_the_limit_is_the_base_when_converted_amounts_follow():
    # 「감액시 임대조건 › 임대보증금·월임대료 | 한도 | 전환보증금 | 전환임대료」: 앞 두 칸은 전환 전 기본 조건
    columns = [
        column(1, "HOUSING_TYPE"),
        column(2, "PRICE", pk="DEPOSIT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
        column(3, "PRICE", pk="MONTHLY_RENT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
        column(4, "CONVERSION_LIMIT"),
        column(5, "PRICE", pk="DEPOSIT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
        column(6, "PRICE", pk="MONTHLY_RENT", unit="원", plan="감액", stage="CONVERSION_DEPOSIT_DOWN"),
    ]
    titles = ("평형", "감액시 임대조건 › 임대보증금", "감액시 임대조건 › 월임대료", "전환가능 보증금 한도액", "전환보증금", "전환임대료")
    prices = limit_part("-44,000,000", "3,891,000", "156,210", columns, titles)
    assert ("DEPOSIT", "12,614", "STANDARD") in prices and ("MONTHLY_RENT", "57,810", "STANDARD") in prices
    assert ("DEPOSIT", "3,891,000", "CONVERSION_DEPOSIT_DOWN") in prices


# ---- 6. 가로 병합으로 복제된 두 금액 칸 ----


def test_duplicated_two_amount_cell_is_split_into_the_next_column():
    values = {4: "4,551 154,980", 5: "4,551 154,980"}
    st._split_shifted_pairs(values, LIMIT_COLUMNS)
    assert values == {4: "4,551", 5: "154,980"}


def test_unsplit_amounts_hold_only_prices():
    columns = [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="OFFERED"), column(3, "PRICE", pk="DEPOSIT", unit="원", plan="기본", stage="STANDARD")]
    rows = (("형", "모집", "보증금"), ("21A", "5", "4,551 154,980"))
    table = st.Table("6-2", 6, "임대조건", rows[0], rows, None)
    part = st.build_part([table], {"tables": [{"table": "6-2", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": columns}]}, "pdf-text")
    [issue] = [i for i in part[st.ISSUES_KEY] if i["code"] == st.UNSPLIT_ISSUE]
    assert issue["field"] == "prices"


# ---- 7. 붙인 가격의 중복 거르기·층 이름 ----


def test_same_amount_on_each_floor_row_is_attached_once_per_floor_with_the_floor_name():
    count_rows = (("주택형", "모집"), ("55A", "10"))
    counts = st.Table("1-1", 1, "공급", count_rows[0], count_rows, None)
    price_rows = (("주택형", "층", "분양가", "융자금"), ("55A", "1층", "200,000", "55,000"), ("55A", "2층", "205,000", "55,000"))
    prices = st.Table("2-1", 2, "분양가격", price_rows[0], price_rows, None)
    mapping = {
        "tables": [
            {
                "table": "1-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [column(1, "HOUSING_TYPE"), column(2, "COUNT", ck="OFFERED")],
            },
            {
                "table": "2-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    column(1, "HOUSING_TYPE"),
                    column(2, "FLOOR"),
                    column(3, "PRICE", pk="SALE_PRICE", unit="천원", plan="기본", stage="STANDARD"),
                    column(4, "PRICE", pk="OTHER", unit="천원", plan="기본", stage="STANDARD"),
                ],
            },
        ]
    }
    part = st.build_part([counts, prices], mapping, "pdf-text")
    [group] = [g for g in part["supplyGroups"] if g["counts"]]
    loans = [p for p in group["prices"] if p["kind"] == "OTHER"]
    assert len(loans) == 2
    assert {p["scope"]["description"].split(" ")[0] for p in loans} == {"1층", "2층"}
    assert not any("_attached" in p for p in group["prices"])


# ---- 3. 공고 기본 정보 근거 이슈는 칸 단위로 ----


def test_short_quote_issue_on_notice_points_at_the_field_it_supports():
    from mujuthaek_extraction.verify.verifier import held_target, narrow_notice_issues

    candidate = {
        "notice": {"targetGroups": ["가상청년", "가상신혼부부"], "supplyType": "가상행복주택"},
        "quality": {
            "reviewIssues": [
                {
                    "code": "EVIDENCE_QUOTE_TOO_SHORT",
                    "target": "/notice",
                    "description": "가상공고: 인용문이 너무 짧아 우연히 일치했을 수 있습니다 「① 가상청년」",
                }
            ]
        },
        "supplyGroups": [],
    }
    narrow_notice_issues(candidate)
    [issue] = candidate["quality"]["reviewIssues"]
    assert issue["target"] == "/notice/targetGroups"
    assert held_target(candidate, issue["target"]) == ("/notice/targetGroups", "ITEM")


def test_notice_issue_that_supports_no_single_field_stays_on_the_notice():
    from mujuthaek_extraction.verify.verifier import narrow_notice_issues

    candidate = {
        "notice": {"targetGroups": ["가상청년"], "supplyType": "가상행복주택"},
        "quality": {"reviewIssues": [{"code": "EVIDENCE_QUOTE_TOO_SHORT", "target": "/notice", "description": "가상공고: 짧음 「가상 공고」"}]},
    }
    narrow_notice_issues(candidate)
    assert candidate["quality"]["reviewIssues"][0]["target"] == "/notice"


# ---- 5. 병합 칸 값은 위치 의심에서 빼기 ----


def test_merged_cell_value_cited_with_its_first_row_is_not_position_suspected():
    from test_consistency import codes, scope

    first = "| 가상청년 | 소득무 | 500 | 12,000 |"
    own = "| 가상고령자 |  |  | 14,000 |"
    text = "\n".join(["[표 6-1]", "| 대상 | 구분 | 계약금 | 보증금 |", first, own])
    evidence = [
        {"id": "ev-own", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": text.index(own), "end": text.index(own) + len(own)}, "quote": own},
        {
            "id": "ev-first",
            "sourceId": "pdf-text",
            "locator": {"kind": "TEXT_RANGE", "start": text.index(first), "end": text.index(first) + len(first)},
            "quote": first,
        },
    ]
    contract = {
        "kind": "CONTRACT_PAYMENT",
        "sourceAmount": "500",
        "amountKrw": 500,
        "pricePlanId": "p",
        "scope": scope("가상고령자"),
        "evidenceIds": ["ev-own", "ev-first"],
    }
    candidate = {
        "evidence": evidence,
        "notice": {"counts": []},
        "locations": [],
        "supplyGroups": [
            {
                "housingTypeCode": None,
                "unitLabel": None,
                "exclusiveAreaSqm": None,
                "itemKind": "HOUSING_TYPE",
                "scope": scope("가상고령자"),
                "prices": [contract],
                "counts": [],
            }
        ],
        "schedules": [],
        "eligibility": [],
        "selectionRules": [],
        "requiredDocuments": [],
        "quality": {"coverage": {s: {"status": "EXTRACTED"} for s in ("eligibility", "requiredDocuments", "schedules")}},
    }
    assert [c for c in codes(candidate, text) if c[0] == "VALUE_POSITION_SUSPECTED"] == []


# ---- 4. 재확인 채택 기준 ----


def test_recheck_answer_that_drops_values_is_detected():
    from mujuthaek_extraction.recheck import _lost_values
    from mujuthaek_extraction.verify.model import VerificationReport

    def report(prices):
        candidate = {"supplyGroups": [{"id": "g1", "prices": [{}] * prices, "counts": []}], "requiredDocuments": [{}], "schedules": []}
        return VerificationReport(candidate=candidate, findings=[], contract_errors=[])

    assert _lost_values(report(3), report(2)) == ["supplyGroups/g1"]
    assert _lost_values(report(2), report(3)) == []


def test_format_violation_only_drops_the_broken_section():
    from mujuthaek_extraction.recheck import _broken_sections

    schema = {
        "type": "object",
        "properties": {
            "quotes": {"type": "array"},
            "schedules": {"type": "array", "items": {"type": "object", "required": ["id"]}},
            "notice": {"type": "object"},
        },
    }
    assert _broken_sections({"quotes": [], "schedules": [{}], "notice": {}}, schema) == {"schedules"}
    assert _broken_sections({"quotes": "x", "schedules": [], "notice": {}}, schema) is None


# ---- 9·8. 서류 묶음 ----


def test_required_column_mark_decides_the_group():
    from mujuthaek_extraction.assemble.details import marked_group

    text = "\n".join(
        [
            "| 필수 | 추가 | 서류명 | 비고 |",
            "| ○ |  | 가상 등본 | 확인 불가 시 가상 초본 추가 제출 |",
            "| ○ |  | 가상 초본 | 전부 포함 |",
            "|  | ○ | 가상 확인서 | 해당자 |",
        ]
    )
    assert marked_group(text, text.index("가상 초본 |")) == "COMMON"
    assert marked_group(text, text.index("가상 확인서")) == "CONDITIONAL"
    assert marked_group("가상 초본을 냅니다", 0) is None


def test_required_mark_conflict_sets_common_and_holds_the_document():
    lines = ["| 필수 | 추가 | 서류명 | 비고 |", "| ○ |  | 가상 초본 | 전부 포함 발급 |"]
    doc = document(id="cho", name="가상 초본", group="CONDITIONAL", appliesTo="가상 등본으로 확인 불가한 신청자", copies=None, issuer=None, quoteRefs=["cho"])
    result = assembled_extra(lines, {"cho": "| ○ |  | 가상 초본 | 전부 포함 발급 |"}, documents=[doc])
    index = {d["id"]: n for n, d in enumerate(result.candidate["requiredDocuments"])}
    assert result.candidate["requiredDocuments"][index["cho"]]["group"] == "COMMON"
    assert ("DOCUMENT_GROUP_CONFLICT", f"/requiredDocuments/{index['cho']}") in {(i["code"], i["target"]) for i in result.issues}


def test_proxy_document_without_spouse_split_is_proxy_other():
    lines = ["■ 대리 신청 시(배우자 포함 본인 외 모두) 추가 서류", "| 가상 위임장 | 1부 |"]
    doc = document(id="proxy", name="가상 위임장", group=None, appliesTo="대리인이 신청하는 경우", copies=None, issuer=None, quoteRefs=["proxy"])
    result = assembled_extra(lines, {"proxy": "■ 대리 신청 시(배우자 포함 본인 외 모두) 추가 서류"}, documents=[doc])
    [kept] = [d for d in result.candidate["requiredDocuments"] if d["id"] == "proxy"]
    assert kept["group"] == "PROXY_OTHER"


# ---- 6차 채점: 동·호 이름, 금액 구성, 날짜–장소 짝, 계약 일정의 방문 ----


def test_unit_label_has_building_when_both_cells_exist():
    assert st._unit_label({"UNIT": "402", "BUILDING": "301"}, "HOUSING_UNIT") == "301동 402호"
    assert st._unit_label({"UNIT": "402호"}, "HOUSING_UNIT") == "402호"


def test_contract_and_balance_summing_to_the_sale_price_join_its_plan():
    def p(plan, kind, amount):
        return {"pricePlanId": plan, "priceStage": "STANDARD", "kind": kind, "sourceAmount": amount, "sourceUnit": "원", "scope": {"targetGroups": []}}

    group = {"prices": [p("base", "SALE_PRICE", "172,150,000"), p("pay", "CONTRACT_PAYMENT", "17,215,000"), p("pay", "BALANCE", "154,935,000")]}
    assert st._merge_payment_parts(group)
    assert {x["pricePlanId"] for x in group["prices"]} == {"base"}
    other = {"prices": [p("base", "SALE_PRICE", "172,150,000"), p("pay", "CONTRACT_PAYMENT", "17,215,000"), p("pay", "BALANCE", "100,000,000")]}
    assert not st._merge_payment_parts(other)


def test_place_written_next_to_the_schedule_date_wins():
    from mujuthaek_extraction.assemble.details import place_pair_conflict

    text = "| 2026.03.25.(수) (14:00 ~ 17:00) 가상본부 주택계약실 | 2026.03.26.(목) (10:00 ~ 17:00) 가상본부 임대공급운영팀 |"
    wrong = {"name": "가상본부", "detail": "9층 임대공급운영팀"}
    right = {"name": "가상본부 임대공급운영팀", "detail": "9층"}
    assert place_pair_conflict(text, "2026-03-25", wrong) == "주택계약실"
    assert place_pair_conflict(text, "2026-03-26", right) is None
    assert place_pair_conflict("계약 장소: 가상본부 임대공급운영팀", "2026-03-25", wrong) is None


def test_contract_with_a_verified_place_keeps_onsite():
    from test_schedule_details import visit_schedule

    line = "계약체결 : 2026.03.26.(목) 10:00 ~ 17:00 가상본부 임대공급운영팀 (가상시 가상로 91, 9층)"
    schedule = visit_schedule(
        id="contract",
        kinds=["CONTRACT"],
        rawLabel="계약체결",
        channels=["ONSITE"],
        places=[{"name": "가상본부 임대공급운영팀", "address": "가상시 가상로 91", "detail": "9층"}],
        startsAt={"precision": "MINUTE", "value": "2026-03-26T10:00:00+09:00"},
        endsAt={"precision": "MINUTE", "value": "2026-03-26T17:00:00+09:00"},
        dailyHours=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        quoteRefs=["contract"],
    )
    result = assembled_extra([line], {"contract": line}, schedules=[schedule])
    [kept] = [s for s in result.candidate["schedules"] if s["id"] == "contract"]
    assert kept["channels"] == ["ONSITE"]


def test_quote_joined_from_two_places_is_split_into_found_parts():
    from mujuthaek_extraction.assemble.quotes import NormalizedText, split_joined_quote

    filler = "가상 안내 문장입니다.\n" * 20  # 두 문장은 원문에서 멀리 떨어져 있음(1쪽·3쪽)
    text = f"1쪽 머리말\n신청자격 : 공고일 현재 만19세 이상인 가상 성년자\n{filler}3쪽\n가상 주택을 소유하지 않은 세대의 구성원이어야 합니다.\n"
    quote = "신청자격 : 공고일 현재 만19세 이상인 가상 성년자 가상 주택을 소유하지 않은 세대의 구성원이어야 합니다."
    index = NormalizedText(text)
    assert split_joined_quote(text, quote, index) is None  # 문장 경계가 없으면 나누지 않음
    joined = "신청자격 : 공고일 현재 만19세 이상인 가상 성년자\n가상 주택을 소유하지 않은 세대의 구성원이어야 합니다."
    assert split_joined_quote(text, joined, index) == [
        "신청자격 : 공고일 현재 만19세 이상인 가상 성년자",
        "가상 주택을 소유하지 않은 세대의 구성원이어야 합니다.",
    ]
    assert split_joined_quote(text, "신청자격 : 공고일 현재 만19세 이상인 가상 성년자", index) is None  # 이미 원문에 있음


def test_long_notice_quote_not_found_without_core_values_holds_only_the_description():
    # 2026-11-09 유료 확인 sh-311005: 구조 호출이 표의 여러 칸을 이은 인용 하나를 원문에서 찾지 못해 공고 전체가 검수로 감
    from mujuthaek_extraction.verify.verifier import held_target, narrow_notice_issues

    stitched = "가상 용도 다세대주택 (도시형 생활주택) 근린생활시설 * 무주택자로 전년도 소득의 120% 이하에 해당하는…"

    def issue(code, quote):
        return {"code": code, "target": "/notice", "description": f"가상공고: 인용문 1개를 원문에서 찾지 못했습니다 「{quote}」"}

    notice = {"title": "가상스페이스 입주자 모집공고", "publisher": "가상기업", "targetGroups": ["청년"], "supplyType": "사회주택", "counts": []}
    cases = [
        (issue("EVIDENCE_QUOTE_NOT_FOUND", stitched), "/notice/description"),
        (issue("EVIDENCE_QUOTE_NOT_FOUND", "가상스페이스 입주자 모집공고 안내 문구가 이어진 긴 인용문입니다"), "/notice"),  # 제목을 담음
        (issue("EVIDENCE_QUOTE_NOT_FOUND", "모집 세대수 원룸 1세대 추가모집 안내 문구가 이어진 긴 인용"), "/notice"),  # 수량을 담음
        (issue("EVIDENCE_QUOTE_TOO_SHORT", stitched), "/notice"),  # 찾은 인용이 짧은 것은 그대로
    ]
    for found, target in cases:
        candidate = {"notice": notice, "quality": {"reviewIssues": [found]}, "supplyGroups": []}
        narrow_notice_issues(candidate)
        assert candidate["quality"]["reviewIssues"][0]["target"] == target
    assert held_target({"notice": notice, "supplyGroups": []}, "/notice/description") == ("/notice/description", "ITEM")


def test_ambiguous_amount_is_read_by_the_plan_whole_equal_to_contract_plus_balance():
    # 2026-11-09 23건: jbdc-16011 계약금 칸 「18,400.000」(합계 92,000,000 · 잔금 73,600,000) 24개를 V1은 18,400원으로 게시, V2는 비워 둠
    from mujuthaek_extraction.assemble.assembler import _read_by_parts
    from mujuthaek_extraction.verify.model import SourceBundle
    from mujuthaek_extraction.verify.numbers import check_numbers

    def p(kind, amount, source=None, plan="기본"):
        return {
            "pricePlanId": plan,
            "priceStage": "STANDARD",
            "kind": kind,
            "sourceAmount": source or f"{amount:,}",
            "sourceUnit": "원",
            "amountKrw": amount,
            "scope": {"targetGroups": []},
        }

    readings = (18_400_000, 18_400)
    contract = p("CONTRACT_PAYMENT", None, "18,400.000")
    plan = [p("DEPOSIT", 92_000_000), contract, p("BALANCE", 73_600_000), p("MONTHLY_RENT", 389_000)]
    assert _read_by_parts(plan, 1, readings) == 18_400_000
    assert _read_by_parts([p("DEPOSIT", 73_618_400), contract, p("BALANCE", 73_600_000)], 1, readings) == 18_400  # 소수점 읽기가 맞으면 그쪽
    # 합이 어느 읽기로도 안 맞거나, 잔금을 모르거나, 다른 금액(OTHER)이 섞였거나, 같은 요금안이 아니면 정하지 않습니다
    assert _read_by_parts([p("DEPOSIT", 90_000_000), contract, p("BALANCE", 73_600_000)], 1, readings) is None
    assert _read_by_parts([p("DEPOSIT", 92_000_000), contract, p("BALANCE", None, "73,600.000")], 1, readings) is None
    assert _read_by_parts([*plan, p("OTHER", 1_000)], 1, readings) is None
    assert _read_by_parts([p("DEPOSIT", 92_000_000, plan="다른안"), contract, p("BALANCE", 73_600_000)], 1, readings) is None

    # 다시 계산 검사: 두 읽기 가운데 하나면 받고, 아닌 값은 그대로 잡습니다
    resolved = [*plan[:1], contract | {"amountKrw": 18_400_000}, *plan[2:]]
    candidate = {"evidence": [], "supplyGroups": [{"prices": resolved, "counts": [], "scope": {"targetGroups": []}}]}
    assert not [f for f in check_numbers(candidate, SourceBundle()) if f.code == "PRICE_UNIT_MISMATCH"]
    resolved[1] = contract | {"amountKrw": 1_840_000}
    assert [f.target for f in check_numbers(candidate, SourceBundle()) if f.code == "PRICE_UNIT_MISMATCH"] == ["/supplyGroups/0/prices/1/amountKrw"]
