"""일곱 번째 시험 채점(2026-10-24)의 일반 규칙: 잘린 표 읽기 답 살리기와 표 수에 맞춘 한도, 인용의 표 표시 걷어내기,
재확인 항목 단위 채택, 접수 방식 낱말, 공고 전체 접수 방식, 공급 섹션 일부 보류. 합성 자료만 씁니다. AI·네트워크 호출 없음."""

from mujuthaek_extraction import supply_tables as st

# ---- 1. 잘린 표 읽기 답 ----


def test_cut_mapping_keeps_only_finished_table_answers():
    raw = '{"tables": [{"table": "1-1", "role": "SUPPLY", "columns": []}, {"table": "1-2", "role": "PRICE", "columns": [{"column": 1, "meaning": "HOUS'
    assert [e["table"] for e in st.salvage_mapping(raw)] == ["1-1"]
    assert st.salvage_mapping('{"tables": [') == []
    assert st.salvage_mapping("잘못된 답") == []


def test_output_limit_grows_with_the_number_of_tables():
    assert st.scaled_limit(2) == st.MAX_OUTPUT_TOKENS
    assert st.scaled_limit(10) == 7_000
    assert st.scaled_limit(100) == st.MAX_OUTPUT_TOKENS_CAP


def test_cut_mapping_answer_asks_again_only_for_the_tables_left():
    import json
    from dataclasses import replace

    from test_supply_tables import MAPPING, material, structure_answer

    from mujuthaek_extraction.extract import run_extraction
    from mujuthaek_extraction.model import ModelResponse, RecordedModel, StopReason
    from mujuthaek_extraction.rules.housing_notice import RULES

    source = material()
    other = {"table": "9-9", "role": "SUPPLY", "rowUnit": "HOUSING_TYPE", "complex": None, "columns": []}
    cut = ModelResponse(raw_text='{"tables": [' + json.dumps(other) + ', {"table": "1-1", "colu', model_id="m", stop_reason=StopReason.MAX_TOKENS)
    model = RecordedModel({"supply_tables": [cut, json.dumps(MAPPING)], "structure": [structure_answer(source)]})
    rules = replace(RULES, calls=RULES.calls[:1], split_calls=(), large_text_chars=None)
    run = run_extraction(rules, source, model)
    asked = [r for r in model.requests if r.call_name == "supply_tables"]
    assert len(asked) == 2 and "9-9" not in asked[1].instructions and "1-1" in asked[1].instructions
    assert [sorted(p["coverage"]) for p in run.parts] == [["locations", "notice"], ["supplyGroups"]]


# ---- 2. 표 행을 이어 쓰며 칸 일부를 빼먹은 인용 ----


def test_joined_table_rows_quote_is_found_cell_by_cell():
    from mujuthaek_extraction.assemble.quotes import NormalizedText, split_joined_quote

    text = "\n".join(
        [
            "[표 25-1]",
            "| 제출서류 | 비 고 | 부수 |",
            "| 가상 개인정보 동의서 [붙임1] | 대상자 : 가상 세대 전원 * 가상급여수급자는 가상 금융 동의서 작성 제외 동의방법 : 정자 서명 | 1통 |",
            "| 가상 금융정보 제공 동의서 [붙임2] |  | 1통 |",
        ]
    )
    quote = (
        "[표 25-1] 가상 개인정보 동의서 [붙임1] | 대상자 : 가상 세대 전원 * 가상급여수급자는 가상 금융 동의서 작성 제외 | 1통 | "
        "가상 금융정보 제공 동의서 [붙임2] |  | 1통"
    )
    assert split_joined_quote(text, quote, NormalizedText(text)) == [
        "가상 개인정보 동의서 [붙임1]",
        "대상자 : 가상 세대 전원 * 가상급여수급자는 가상 금융 동의서 작성 제외",
        "가상 금융정보 제공 동의서 [붙임2]",
    ]
    # 칸 안에서 낱말을 빼먹은 조각이 있으면 나누지 않습니다
    broken = "가상 개인정보 동의서 [붙임1] | 대상자 : 가상 세대 * 가상급여수급자는 작성 제외 | 1통"
    assert split_joined_quote(text, broken, NormalizedText(text)) is None


# ---- 3. 재확인 항목 단위 채택 ----


def test_recheck_keeps_the_fixed_item_even_if_another_item_got_worse():
    import copy
    import json as _json

    from helpers import to_ai
    from test_recheck import setup

    from mujuthaek_extraction.model import RecordedModel
    from mujuthaek_extraction.recheck import recheck_problems
    from mujuthaek_extraction.rules.housing_notice import RULES

    data, source, parts, evaluate = setup()
    other = parts[0]["eligibility"][2]
    other["quoteRefs"].append("fake")  # 두 번째 문제 항목
    fixed = _json.loads(_json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))
    worse = copy.deepcopy(other)
    worse["quoteRefs"] = ["q9"]  # 원문에 없는 인용만 남겨 항목이 빠짐(새 문제)
    quotes = [
        {"ref": "q1", "documentId": "text1", "text": data["evidence"][0]["quote"]},
        {"ref": "q9", "documentId": "text1", "text": "원문에 전혀 없는 가상 문장입니다"},
    ]
    answer = {"quotes": quotes, "eligibility": [fixed, worse], "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}}}
    model = RecordedModel({"recheck": [_json.dumps(answer, ensure_ascii=False)], "recheck-quotes": [_json.dumps({"quotes": []})]})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.accepted
    assert f"eligibility/{data['eligibility'][1]['id']}" in result.adopted_sections
    assert f"eligibility/{other['id']}" not in result.adopted_sections


# ---- 4. 접수 방식 낱말 ----


def test_channel_words_for_mail_address_and_exceptions():
    from mujuthaek_extraction.assemble.details import channel_mentions

    assert "EMAIL" in channel_mentions("서류는 메일 (gasang@gh.or.kr)로 송부")[0]
    assert "EMAIL" in channel_mentions("gasang@example.com 으로 보내 주세요")[0]
    positive, negative = channel_mentions("등기우편 접수만 가능 (고령자 제외)")
    assert "MAIL" in positive and "MAIL" not in negative
    positive, negative = channel_mentions("점심시간과 휴일에는 현장접수를 하지 않아요")
    assert "ONSITE" not in negative
    assert "ONSITE" in channel_mentions("방문 접수 불가")[1]  # 진짜로 막은 말은 그대로
    assert "MAIL" in channel_mentions("우편 접수는 받지 않습니다")[1]


# ---- 재실행(A)에서 본 것: 증감 구분 칸, 병합 칸 수량 근거, 원문에 없는 합계 ----


def test_sign_only_column_keeps_conversion_plans():
    assert st._direction_amounts("(+)") == {}
    assert st._direction_amounts("(+) -") == {"(+)": False}
    assert st._direction_amounts("(+) - (-) 10,000") == {"(+)": False, "(-)": True}


def test_sign_column_with_amounts_beside_it_makes_conversion_plans():
    from test_round5 import limit_part

    prices = limit_part("(+)", "61,920", "91,170")
    assert ("DEPOSIT", "61,920", "CONVERSION_DEPOSIT_UP") in prices


def test_notice_partial_only_for_a_total_not_in_the_source_is_extracted():
    from mujuthaek_extraction.assemble.assembler import _total_not_written

    assert _total_not_written(
        {"status": "PARTIAL", "reason": "주택형별 모집호수는 표에 있지만 공고 전체 모집호수 합계는 따로 적혀 있지 않아 합산하지 않았어요."}
    )
    assert not _total_not_written({"status": "PARTIAL", "reason": "공급 대상 일부를 읽지 못했어요"})


def test_price_row_of_a_lettered_type_does_not_attach_to_another_lettered_type():
    from test_supply_tables import column

    count_rows = (("주택형", "모집"), ("26AB", "10"))
    counts = st.Table("1-1", 1, "공급", count_rows[0], count_rows, None)
    price_rows = (("주택형", "보증금"), ("26C", "57,760"))
    prices = st.Table("2-1", 2, "임대조건", price_rows[0], price_rows, None)
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
                "columns": [column(1, "HOUSING_TYPE"), column(2, "PRICE", pk="DEPOSIT", unit="천원", plan="기본", stage="STANDARD")],
            },
        ]
    }
    part = st.build_part([counts, prices], mapping, "pdf-text")
    by_code = {g["housingTypeCode"]: g for g in part["supplyGroups"]}
    assert by_code["26AB"]["prices"] == [] and [p["sourceAmount"] for p in by_code["26C"]["prices"]] == ["57,760"]
