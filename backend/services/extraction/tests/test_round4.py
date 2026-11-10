"""네 번째 시험 채점(2026-10-24)의 일반 규칙: 대상 한정 요금표 판단 좁히기, 「(+) -」 행의 가짜 전환안, 지우기 전 앞뒤 줄 찾기.
합성 원문·합성 표만 씁니다. AI·네트워크 호출 없음."""

import copy
import dataclasses

from helpers import ai_part, example, source_for
from test_round3 import LEASE_ENTRY
from test_schedule_details import document, visit_schedule
from test_supply_round2 import COUNT_ENTRY, count_table, issues, price_entry

from mujuthaek_extraction import supply_tables as st
from mujuthaek_extraction.assemble.assembler import assemble

# ---- 1. 대상 한정 요금표 판단 ----


def price_table(heading, above=None, rows=None):
    rows = rows or (("공급형", "보증금", "월임대료"), ("31A", "3,000,000", "60,000"))
    return st.Table("3-3", 3, heading, rows[0], rows, None, above=above if above is not None else (heading,))


def test_location_note_with_law_citation_above_table_is_not_a_price_restriction():
    # 표 위 입지 설명의 괄호 단서(「…에만 해당」)는 요금의 적용 대상이 아닙니다
    note = "「가상특구의 지정에 관한 특별법」 제2조제1호에 따른 가상특구(가상근로자인 경우에만 해당)에 건설되는 주택"
    part = st.build_part(
        [count_table(), price_table("(단위: 원)", above=("(단위: 원)", note))],
        {"tables": [COUNT_ENTRY, price_entry("3-3", "HOUSING_TYPE")]},
        "pdf-text",
    )
    assert issues(part, "PRICE_SCOPE_UNCERTAIN") == []
    assert {g["housingTypeCode"]: len(g["prices"]) for g in part["supplyGroups"]}["31A"] == 2


def test_restriction_line_without_price_words_is_not_read():
    part = st.build_part(
        [count_table(), price_table("(단위: 원)", above=("(단위: 원)", "가상근로자에 한하여 신청할 수 있습니다"))],
        {"tables": [COUNT_ENTRY, price_entry("3-3", "HOUSING_TYPE")]},
        "pdf-text",
    )
    assert issues(part, "PRICE_SCOPE_UNCERTAIN") == []


def test_restricted_price_title_holds_only_prices():
    part = st.build_part(
        [count_table(), price_table("가상 급여 수급자만 해당하는 임대조건")],
        {"tables": [COUNT_ENTRY, price_entry("3-3", "HOUSING_TYPE")]},
        "pdf-text",
    )
    [issue] = [i for i in part[st.ISSUES_KEY] if i["code"] == "PRICE_SCOPE_UNCERTAIN"]
    assert issue["field"] == "prices"  # 수량은 화면에 남김


def test_rows_with_their_own_target_are_not_target_unknown():
    # 표 제목이 대상 한정처럼 보여도 행의 대상 칸이 대상을 정하면 그 대상의 요금입니다
    rows = (("공급형", "대상", "보증금", "월임대료"), ("31A", "가상청년", "3,000,000", "60,000"))
    entry = {
        "table": "3-3",
        "role": "SUPPLY",
        "rowUnit": "HOUSING_TYPE",
        "complex": None,
        "columns": [
            *price_entry("3-3", "HOUSING_TYPE")["columns"][:1],
            {"column": 2, "meaning": "TARGET_GROUP"},
            *[{**c, "column": c["column"] + 1} for c in price_entry("3-3", "HOUSING_TYPE")["columns"][1:]],
        ],
    }
    part = st.build_part([price_table("가상 급여 수급자만 해당하는 임대조건", rows=rows)], {"tables": [entry]}, "pdf-text")
    assert issues(part, "PRICE_SCOPE_UNCERTAIN") == []
    [group] = part["supplyGroups"]
    assert [p["scope"]["targetGroups"] for p in group["prices"]] == [["가상청년"], ["가상청년"]]


# ---- 2. 「(+) -」 한도 칸: 그 방향 전환이 없는 행 ----


def lease_table(limit_cell, deposit="10,800", rent="54,540"):
    rows = (
        ("형", "대상", "모집", "보증금", "계약금", "잔금", "월임대료", "전환 한도", "전환 보증금", "전환 월임대료"),
        ("16", "가상청년", "10", "10,800", "500", "10,300", "54,540", "-", "-", "-"),
        ("", "", "", "", "", "", "", limit_cell, deposit, rent),
    )
    cells = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        (10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
        (10, 11, 12, 13, 14, 15, 16, 20, 21, 22),
    )
    return st.Table("4-1", 4, "(단위: 천원, 원)", rows[0], rows, cells)


def stages(part):
    [group] = part["supplyGroups"]
    return sorted({p["priceStage"] for p in group["prices"]})


def test_limit_cell_with_sign_but_no_amount_makes_no_conversion_plan():
    part = st.build_part([lease_table("(+) -")], {"tables": [LEASE_ENTRY]}, "pdf-text")
    assert stages(part) == ["STANDARD"]
    assert not [i for i in part.get(st.ISSUES_KEY) or [] if i["code"] == "CONVERSION_DIRECTION_UNCERTAIN"]


def test_conversion_plan_equal_to_the_base_is_dropped_not_held():
    # 한도 칸에 금액이 있어도 전환 보증금·월세가 기본과 똑같으면 전환이 아닙니다(기본 조건을 옮긴 것)
    part = st.build_part([lease_table("(+)5,000")], {"tables": [LEASE_ENTRY]}, "pdf-text")
    assert stages(part) == ["STANDARD"]
    assert not [i for i in part.get(st.ISSUES_KEY) or [] if i["code"] == "CONVERSION_DIRECTION_UNCERTAIN"]


def test_real_conversion_plan_is_kept():
    part = st.build_part([lease_table("(+)5,000", deposit="15,800", rent="30,000")], {"tables": [LEASE_ENTRY]}, "pdf-text")
    assert stages(part) == ["CONVERSION_DEPOSIT_UP", "STANDARD"]


# ---- 3. 지우기 전에 근거 인용 앞뒤 줄에서 찾기 ----


def assembled_extra(extra_lines, quotes, schedules=(), documents=()):
    data = example("housing")
    source = source_for("housing", data)
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + "\n".join(extra_lines) + "\n")
    part = copy.deepcopy(ai_part(data))
    part["quotes"] += [{"ref": ref, "documentId": "text1", "text": text} for ref, text in quotes.items()]
    part["schedules"] += list(schedules)
    part["requiredDocuments"] += list(documents)
    return assemble([part], dataclasses.replace(source, material=material))


def test_issuer_on_the_next_broken_line_is_kept():
    # 줄이 깨진 서류 표: 발급처가 서류 이름 다음 줄에 있음
    lines = ["| 가상 연금 가입증명서 | 해당자 | 1부 |", "|  | 가상연금공단 |  |"]
    doc = document(id="pension", name="가상 연금 가입증명서", copies=1, issuer="가상연금공단", quoteRefs=["pension"])
    result = assembled_extra(lines, {"pension": "가상 연금 가입증명서"}, documents=[doc])
    [kept] = [d for d in result.candidate["requiredDocuments"] if d["id"] == "pension"]
    assert kept["issuer"] == "가상연금공단"


def test_issuer_of_the_next_document_is_not_borrowed():
    lines = ["| 가상 재직증명서 | 해당자 | 1부 |", "| 가상 사업자등록증명 | 가상세무서 | 1부 |"]
    doc = document(id="work", name="가상 재직증명서", copies=1, issuer="가상세무서", quoteRefs=["work"])
    other = document(id="biz", name="가상 사업자등록증명", copies=1, issuer="가상세무서", quoteRefs=["biz"])
    result = assembled_extra(lines, {"work": "가상 재직증명서", "biz": "가상 사업자등록증명"}, documents=[doc, other])
    by_id = {d["id"]: d for d in result.candidate["requiredDocuments"]}
    assert by_id["work"]["issuer"] is None and by_id["biz"]["issuer"] == "가상세무서"


def onsite(**changes):
    return visit_schedule(
        id="onsite",
        rawLabel="가상 현장접수",
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "MINUTE", "value": "2026-10-27T10:00:00+09:00"},
        endsAt={"precision": "MINUTE", "value": "2026-10-27T16:00:00+09:00"},
        dailyHours=[],
        quoteRefs=["onsite"],
        **changes,
    )


def test_time_on_the_next_line_is_kept_when_only_this_schedule_times_are_there():
    lines = ["■ 가상 현장 안내", "가상 안내문을 읽어 주세요", "가상 현장접수는 하루만 받으니 늦지 않게 오세요", "'26.10.27.(화) 10:00~16:00"]
    result = assembled_extra(lines, {"onsite": "가상 현장접수는 하루만 받으니 늦지 않게 오세요"}, schedules=[onsite()])
    [schedule] = [s for s in result.candidate["schedules"] if s["id"] == "onsite"]
    assert schedule["startsAt"]["precision"] == "MINUTE" and schedule["endsAt"]["precision"] == "MINUTE"


def test_time_is_not_taken_from_lines_with_other_times():
    lines = [
        "■ 가상 현장 안내",
        "가상 안내문을 읽어 주세요",
        "가상 현장접수는 하루만 받으니 늦지 않게 오세요",
        "'26.10.27.(화) 10:00~16:00, 서류 확인은 09:00부터",
    ]
    result = assembled_extra(lines, {"onsite": "가상 현장접수는 하루만 받으니 늦지 않게 오세요"}, schedules=[onsite()])
    [schedule] = [s for s in result.candidate["schedules"] if s["id"] == "onsite"]
    assert schedule["startsAt"]["precision"] == "DAY"


# ---- 4. 「시작일과 마감일 제외」는 이어지는 기간 ----


def test_first_and_last_day_exception_means_a_continuous_period():
    from mujuthaek_extraction.assemble.details import continuous_hours

    window = [{"start": "10:00", "end": "16:00"}]
    for text in ("'26.11.17.(화)~'26.11.19.(목) 10:00~16:00 (단, 시작일과 마감일제외)", "10:00~16:00(첫날 및 마지막 날 제외)"):
        assert continuous_hours(text, window) is not None
    assert continuous_hours("'26.11.17.(화)~'26.11.19.(목) 10:00~16:00 (토·일 제외)", window) is None


# ---- 5. 서류 칸의 단서가 다른 서류를 이름으로 가리킴 ----


def test_exclusion_clue_naming_another_document_holds_the_document_it_was_attached_to():
    lines = [
        "| 가상 개인정보 이용 동의서 | 동의서를 내지 않으면 접수가 거부됨. "
        "가상급여 수급자로 신청하는 경우에는 ‘가상 금융정보 등 제공 동의서’ 작성 제외 | O | 1통 |",
        "| 가상 금융정보 등 (금융·신용) 제공 동의서 |  | O | 1통 |",
    ]
    wrong = document(
        id="privacy", name="가상 개인정보 이용 동의서", appliesTo="신청자 전원(가상급여 수급자 제외)", copies=1, issuer=None, quoteRefs=["privacy"]
    )
    other = document(id="finance", name="가상 금융정보 등 (금융·신용) 제공 동의서", appliesTo="신청자 전원", copies=1, issuer=None, quoteRefs=["finance"])
    quotes = {"privacy": "가상 개인정보 이용 동의서", "finance": "가상 금융정보 등 (금융·신용) 제공 동의서"}
    result = assembled_extra(lines, quotes, documents=[wrong, other])
    flagged = [i["target"] for i in result.issues if i["code"] == "DOCUMENT_CLUE_FOR_OTHER_DOCUMENT"]
    index = {d["id"]: n for n, d in enumerate(result.candidate["requiredDocuments"])}
    assert flagged == [f"/requiredDocuments/{index['privacy']}"]


def test_exclusion_clue_about_the_document_itself_is_fine():
    from mujuthaek_extraction.assemble.details import clue_for_other

    doc = {"name": "가상 금융정보 제공 동의서", "appliesTo": "가상급여 수급자 제외"}
    text = "| 가상 금융정보 제공 동의서 | 가상급여 수급자는 ‘가상 금융정보 제공 동의서’ 작성 제외 |"
    assert clue_for_other(doc, text, ["가상 개인정보 이용 동의서"]) is None
    assert clue_for_other({**doc, "appliesTo": "신청자 전원"}, "가상 개인정보 이용 동의서 제외", ["가상 개인정보 이용 동의서"]) is None


# ---- 6. 서류 누락 의심: 자산 산정 표 행은 서류 행이 아님 ----


def test_asset_criteria_rows_after_a_document_table_are_not_document_rows():
    from mujuthaek_extraction.verify.consistency import _document_table_rows

    text = "\n".join(
        [
            "■ 제출서류",
            "| 서류 | 발급처 |",
            "| 가상 소득 확인서 | 가상센터 |",
            "",
            "- 3 -",
            "| 총 자 산 | 부 동 산 • 가상시스템에서 조회한 건축물·토지 가액(가상 확인서 기준) |",
            "| 기타 자산 • 「가상세법」 제104조에 따른 가상 증명서 금액 |",
        ]
    )
    rows = _document_table_rows(text)
    assert rows == ["| 가상 소득 확인서 | 가상센터 |"]


# ---- 7. 재확인 순서: 섹션마다 번갈아 ----


def test_recheck_order_puts_whole_section_first_then_alternates_sections():
    from mujuthaek_extraction.recheck import ordered_problems

    problems = {("eligibility", f"e{n}"): ["x"] for n in range(6)}
    problems[("schedules", "s1")] = ["x"]
    problems[("requiredDocuments", None)] = ["x"]
    problems[("requiredDocuments", "d1")] = ["x"]
    order = [key for key, _ in ordered_problems(problems)]
    assert order[:4] == [("requiredDocuments", None), ("schedules", "s1"), ("requiredDocuments", "d1"), ("eligibility", "e0")]
    assert len(order) == len(problems)


# ---- 8. 두 금액 칸 뒤에 다른 표가 와도 표 순서가 깨지지 않음 ----


def test_two_amount_conversion_cell_followed_by_another_table():
    # 실측 5차(2026-10-24): 두 금액 칸을 나눈 뒤 다음 표에서 표 순서 변수가 덮여 공고 처리 전체가 실패함
    rows = (("형", "보증금", "월세", "한도", "전환 보증금", "전환 월세"), ("21A", "12,614", "57,810", "(+) 5,000 (-) 10,000", "17,614 2,614", "40,000 86,970"))
    first = st.Table("6-1", 6, "임대조건", rows[0], rows, ((0, 1, 2, 3, 4, 5), (6, 7, 8, 9, 10, 11)))
    second = st.Table("6-2", 6, "임대조건", rows[0], (rows[0], ("26A", "15,000", "70,000", "-", "-", "-")), None)
    columns = [
        {"column": 1, "meaning": "HOUSING_TYPE"},
        {"column": 2, "meaning": "PRICE", "priceKind": "DEPOSIT", "unit": "천원", "plan": "기본", "priceStage": "STANDARD"},
        {"column": 3, "meaning": "PRICE", "priceKind": "MONTHLY_RENT", "unit": "원", "plan": "기본", "priceStage": "STANDARD"},
        {"column": 4, "meaning": "CONVERSION_LIMIT"},
        {"column": 5, "meaning": "PRICE", "priceKind": "DEPOSIT", "unit": "천원", "plan": "최대 전환", "priceStage": "CONVERSION_DEPOSIT_UP"},
        {"column": 6, "meaning": "PRICE", "priceKind": "MONTHLY_RENT", "unit": "원", "plan": "최대 전환", "priceStage": "CONVERSION_DEPOSIT_UP"},
    ]
    mapping = {"tables": [{"table": t, "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": columns} for t in ("6-1", "6-2")]}
    part = st.build_part([first, second], mapping, "pdf-text")
    assert {g["housingTypeCode"] for g in part["supplyGroups"]} == {"21A", "26A"}
