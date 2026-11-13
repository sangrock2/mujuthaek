"""V9 값–인용 대조: 인용문은 진짜인데 값을 잘못 옮긴 결과가 자동 완료되지 않아야 합니다(검토 2026-10-16)."""

import copy

from mujuthaek_extraction.verify import verify_extraction
from mujuthaek_extraction.verify.claims import _count_bound, _has_date, _has_number, _krw_found, _price_unit_ok, check_claims
from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.tables import place_of
from tests.verify.test_verify import assembled, clock


def age_atoms(candidate):
    stack = [candidate["eligibility"]]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("kind") == "ATOMIC" and node.get("attribute") == "AGE_YEARS":
                yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def test_wrong_age_with_real_quote_is_not_auto_passed():
    candidate, sources = assembled()
    assert verify_extraction(candidate, sources, None, clock=clock).passed
    wrong = copy.deepcopy(candidate)
    next(a for a in age_atoms(wrong) if a["value"] == 39)["value"] = 45  # 원문은 「39세 이하」
    report = verify_extraction(wrong, sources, None, clock=clock)
    assert not report.passed
    assert any(i["code"] == "VALUE_NOT_IN_QUOTE" for i in report.candidate["quality"]["reviewIssues"])


def test_clean_examples_have_no_findings():
    for name in ("housing", "business"):
        candidate, sources = assembled(name)
        assert check_claims(candidate, sources) == []


def test_number_forms_written_differently_still_match():
    assert _has_number(["총자산가액 합산기준 ( 337 )백만원 이하"], 337_000_000, "KRW")
    assert _has_number(["신혼부부, 고령자, 일반 1인 가구 | 3억3,700만 원 이하"], 337_000_000, "KRW")
    assert _has_number(["자동차가액 4,542만 원 이하"], 45_420_000, "KRW")
    assert _has_number(["총 자산기준 2억4천5백만원 이하"], 245_000_000, "KRW")
    assert _has_number(["총자산 34,500만원 이하"], 345_000_000, "KRW")
    assert _has_number(["보증금 1 ,000,000원"], 1_000_000)
    assert _has_number(["혼인 기간 2년 이내"], 24, "MONTH")
    assert _has_number(["두 자녀 이상"], 2, "COUNT")
    assert _has_number(["자동차를 소유하고 있지 않아야 합니다"], 0, "KRW")
    assert _has_number(["월평균소득 50%(1인 70%, 2인 60%) 이하"], 3, "COUNT", at_least=True, attribute="HOUSEHOLD_MEMBER_COUNT")
    assert not _has_number(["만 19세 이상 39세 이하"], 45, "YEAR")


def test_date_forms_written_differently_still_match():
    def day(value):
        return {"precision": "DAY", "value": value}

    assert _has_date(["2026. 8. 10.(월) ~ 14.(금)"], day("2026-08-10"))
    assert _has_date(["2026. 8. 10.(월) ~ 14.(금)"], day("2026-08-14"), end=True)
    assert _has_date(["2026년 10월 1일 10시부터 31일 17시까지"], day("2026-10-31"), end=True)
    assert _has_date(["’26. 08. 중"], {"precision": "MONTH", "value": "2026-08"})
    assert not _has_date(["2026. 8. 10.(월) ~ 14.(금)"], day("2026-08-21"))


def test_date_year_must_match_when_written_or_be_the_notice_year():
    """월·일만 맞추던 대조(2026-10-21 검토): 「2026. 10. 7.」과 2025-10-07이 통과하면 접수 상태가 틀어집니다."""

    def day(value):
        return {"precision": "DAY", "value": value}

    assert _has_date(["2026. 10. 7.(수)"], day("2026-10-07"))
    assert not _has_date(["2026. 10. 7.(수)"], day("2025-10-07"))
    assert not _has_date(["’26. 10. 7."], day("2025-10-07"))
    # 연도 없이 적힌 기간: 공고일 연도(와 다음 해)여야 합니다
    assert _has_date(["10. 7.(수) ~ 10. 9.(금)"], day("2026-10-09"), end=True, years={2026, 2027})
    assert not _has_date(["10. 7.(수) ~ 10. 9.(금)"], day("2025-10-09"), end=True, years={2026, 2027})
    assert not _has_date(["10. 7.(수) ~ 9.(금)"], day("2025-10-09"), end=True, years={2026, 2027})
    # 같은 월·일이 다른 해로 적힌 것은 연도 없는 표기로 세지 않습니다
    assert not _has_date(["2025. 10. 7. 기준"], day("2026-10-07"), years={2026, 2027})
    # 공고일을 모르면 연도는 보지 않습니다(이전과 같음)
    assert _has_date(["10. 7.(수)"], day("2025-10-07"))


def test_supply_value_found_nowhere_in_source_is_held_not_noted():
    """공급 가격이 원문 어디에도 없으면 메모로 두지 않고 그 공급 묶음의 가격만 보류합니다(틀린 값보다 누락이 낫다).
    2026-10-24부터 가격 칸의 문제는 그 묶음의 가격 목록(/supplyGroups/N/prices)만 보류하고 수량·주택형은 게시합니다."""
    candidate, sources = assembled()
    wrong = copy.deepcopy(candidate)
    group = next(g for g in wrong["supplyGroups"] if g["prices"])
    index = wrong["supplyGroups"].index(group)
    group["prices"][0]["sourceAmount"] = "987,654,321"
    report = verify_extraction(wrong, sources, None, clock=clock)
    quality = report.candidate["quality"]
    assert not report.passed
    assert any(i["code"] == "VALUE_NOT_IN_QUOTE" and i["target"].startswith(f"/supplyGroups/{index}/") for i in quality["reviewIssues"])
    assert not any(n["code"] == "VALUE_NOT_IN_QUOTE" for n in quality["notes"])
    assert quality["verification"]["status"] == "PARTIALLY_PASSED"
    assert any(h["target"] == f"/supplyGroups/{index}/prices" for h in quality["heldItems"])
    assert not any(h["target"] == f"/supplyGroups/{index}" for h in quality["heldItems"])


def test_dropped_eligibility_condition_is_not_auto_passed():
    # 검토 지적: 소득 70% 조건과 무주택 조건을 지우고 나이만 남겨도 자동 완료되던 것 (V8 자격 기준 누락)
    candidate, sources = assembled()
    kept = copy.deepcopy(candidate)
    kept["eligibility"] = [e for e in kept["eligibility"] if any(True for _ in age_atoms({"eligibility": [e]}))]
    assert kept["eligibility"] and len(kept["eligibility"]) < len(candidate["eligibility"])
    report = verify_extraction(kept, sources, None, clock=clock)
    assert not report.passed
    assert any(i["code"] == "ELIGIBILITY_OMISSION_SUSPECTED" for i in report.candidate["quality"]["reviewIssues"])


def test_two_character_quote_does_not_support_an_eligibility_condition():
    # 검토 지적: 너무 짧은 인용문도 확인된 근거로 쳐서 「39」 한 줄 근거의 자격 조건이 자동 완료되던 것
    candidate, sources = assembled()
    short = copy.deepcopy(candidate)
    text = next(iter(sources.texts.values()))
    start = text.index("39")
    short["evidence"].append(
        {"id": "ev-short", "sourceId": next(iter(sources.texts)), "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + 2}, "quote": "39"}
    )
    item = next(e for e in short["eligibility"] if any(True for _ in age_atoms({"eligibility": [e]})))
    item["evidenceIds"] = ["ev-short"]
    for atom in age_atoms({"eligibility": [item]}):
        atom["evidenceIds"] = ["ev-short"]
    report = verify_extraction(short, sources, None, clock=clock)
    assert not report.passed


def test_locator_pointing_at_wrong_kind_of_document_is_reported_not_crashing():
    candidate, sources = assembled()
    broken = copy.deepcopy(candidate)
    broken["evidence"][0]["locator"] = {"kind": "UNIT_ROW", "pointer": "/0"}
    report = verify_extraction(broken, sources, None, clock=clock)
    assert "EVIDENCE_LOCATOR_KIND_MISMATCH" in {f.code for f in report.findings} and not report.passed


def test_null_count_and_between_ages_do_not_crash_and_are_range_checked():
    from mujuthaek_extraction.verify.consistency import check_consistency

    candidate, sources = assembled()
    odd = copy.deepcopy(candidate)
    odd["supplyGroups"][0]["counts"] = [{**c, "value": None} for c in odd["supplyGroups"][0]["counts"]]
    atom = next(age_atoms(odd))
    atom |= {"operator": "BETWEEN", "value": [19, 390]}
    found = {(f.code, f.target.split("/")[1]) for f in check_consistency(odd, sources)}
    assert ("VALUE_OUT_OF_RANGE", "eligibility") in found


def test_adult_age_19_from_adult_wording_is_not_flagged_but_other_ages_are():
    # 실측: 「성년자」를 프롬프트 규칙대로 AGE_YEARS ≥ 19로 옮긴 값이 매번 값–인용 불일치로 걸려 재확인 호출을 씀
    candidate, _ = assembled()
    atom = next(age_atoms(candidate))
    quote_id = atom.get("evidenceIds", [None])[0] or candidate["eligibility"][0]["evidenceIds"][0]
    evidence = next(e for e in candidate["evidence"] if e["id"] == quote_id)
    evidence["quote"] = "신청자는 공고일 현재 성년자인 무주택세대구성원"
    atom["value"] = 19
    assert not [f for f in check_claims(candidate) if f.code == "VALUE_NOT_IN_QUOTE" and "AGE" in f.description]
    atom["value"] = 20
    assert [f for f in check_claims(candidate) if f.code == "VALUE_NOT_IN_QUOTE" and "AGE" in f.description]


# ---------- 공고일: 인용문 대신 다른 곳에서 값 확인 (2026-10-20) ----------


def notice_only(announced, quote="서울지역본부 든든전세주택 입주자 모집공고"):
    return {
        "evidence": [{"id": "ev-1", "quote": quote}],
        "notice": {"announcedOn": announced, "evidenceIds": ["ev-1"]},
        "eligibility": [],
        "schedules": [],
        "supplyGroups": [],
    }


def finding_codes(candidate, text, **kwargs):
    from mujuthaek_extraction.verify import SourceBundle

    return [(f.code, f.target) for f in check_claims(candidate, SourceBundle(texts={"t": text}), **kwargs)]


def test_labeled_announcement_dates_are_read_in_written_forms():
    from datetime import date

    from mujuthaek_extraction.verify.claims import labeled_announcement_dates

    assert labeled_announcement_dates(["• (기준일) 모집공고일은 2026.10.01.(목)이며"]) == {date(2026, 10, 1)}
    assert labeled_announcement_dates(["(입주자 모집공고일 : 2026. 04. 24.)"]) == {date(2026, 4, 24)}
    assert labeled_announcement_dates(["본 단지 공고일(‘26.04.24.) 현재"]) == {date(2026, 4, 24)}
    assert labeled_announcement_dates(["공고일은 2026년 10월 1일입니다."]) == {date(2026, 10, 1)}
    # 표기 바로 뒤가 아니면 보지 않습니다
    assert labeled_announcement_dates(["공고일 이후(2026.04.24. 포함) 발급분", "공고일로부터 10일 이내인 2026.05.04"]) == set()


def test_announced_on_cited_with_title_line_is_confirmed_by_source_label():
    candidate = notice_only("2026-10-01")
    text = "서울지역본부 든든전세주택 입주자 모집공고\n• (기준일) 모집공고일은 2026.10.01.(목)이며, 이는 입주자격 판단 기준일이 됩니다."
    assert finding_codes(candidate, text) == [("VALUE_CONFIRMED_IN_SOURCE", "/notice/announcedOn")]


def test_announced_on_not_confirmed_when_source_labels_differ_or_disagree():
    text = "모집공고일은 2026.10.01.(목)이며\n정정공고일 : 2026.10.05."
    assert finding_codes(notice_only("2026-10-01"), text) == [("VALUE_NOT_IN_QUOTE", "/notice/announcedOn")]
    # 원문 표기와 다른 값은 API가 같다고 해도 확인하지 않습니다(원문이 우선)
    text = "모집공고일은 2026.10.01.(목)이며"
    matched = frozenset({"/notice/announcedOn"})
    assert finding_codes(notice_only("2026-10-02"), text, api_matched=matched) == [("VALUE_NOT_IN_QUOTE", "/notice/announcedOn")]


def test_announced_on_without_source_label_is_confirmed_only_by_api_match():
    text = "서울지역본부 든든전세주택 입주자 모집공고\n2026. 10. 1.\n한국토지주택공사"
    assert finding_codes(notice_only("2026-10-01"), text) == [("VALUE_NOT_IN_QUOTE", "/notice/announcedOn")]
    matched = frozenset({"/notice/announcedOn"})
    assert finding_codes(notice_only("2026-10-01"), text, api_matched=matched) == [("VALUE_CONFIRMED_BY_API", "/notice/announcedOn")]


def test_confirmed_announced_on_is_note_and_does_not_block():
    candidate, sources = assembled()
    evidence = next(e for e in candidate["evidence"] if e["id"] == candidate["notice"]["evidenceIds"][0])
    title = "가상주거 청년 매입임대 입주자 모집 공고."
    start = evidence["quote"].index(title)
    begin = evidence["locator"]["start"] + start
    locator = {"kind": "TEXT_RANGE", "start": begin, "end": begin + len(title)}
    candidate["evidence"].append({"id": "ev-title", "sourceId": evidence["sourceId"], "locator": locator, "quote": title})
    candidate["notice"]["evidenceIds"] = ["ev-title"]
    report = verify_extraction(candidate, sources, None, clock=clock)
    assert report.passed, report.findings
    assert "VALUE_CONFIRMED_IN_SOURCE" in {n["code"] for n in report.candidate["quality"]["notes"]}

    wrong = copy.deepcopy(candidate)  # 원문 공고일과 다른 값은 사람 확인. 공고일만 보류하고 공고는 게시(2026-10-20 결정)
    wrong["notice"]["announcedOn"] = "2026-10-02"
    report = verify_extraction(wrong, sources, None, clock=clock)
    assert report.verification["status"] == "PARTIALLY_PASSED"
    assert [h["target"] for h in report.candidate["quality"]["heldItems"]] == ["/notice/announcedOn"]
    assert any(i["code"] == "VALUE_NOT_IN_QUOTE" and i["target"] == "/notice/announcedOn" for i in report.candidate["quality"]["reviewIssues"])


def test_household_bracket_rule_is_not_used_for_child_counts():
    # 2026-10-21 리뷰: 「값 − 1」 규칙이 자녀 수에도 적용되어 「자녀 2명 이상」을 3명 이상으로 뽑아도 통과했음
    assert not _has_number(["자녀가 2명 이상인 경우 90% 완화"], 3, "COUNT", at_least=True, attribute="CHILD_COUNT")


def test_amount_must_match_its_written_unit():
    # 2026-10-21 리뷰: 「3,708만원」을 3,708,000원으로 뽑아도 「천원 표일 수 있다」로 통과했음
    assert not _krw_found([("자동차가액 3,708만원 이하", None)], 3_708_000)
    assert _krw_found([("자동차가액 3,708만원 이하", None)], 37_080_000)
    assert _krw_found([("개별 자동차가액 ( 4,563 )만원 이하", None)], 45_630_000)
    table = "(단위: 만원)\n| 출생자녀수 | 총자산 | 자동차 |\n| 1명 | 37,900 | 4,996 |"
    row = "| 1명 | 37,900 | 4,996 |"
    assert _krw_found([(row, place_of(table, table.index(row)))], 379_000_000)  # 같은 표 위 단위 표시
    assert not _krw_found([(row, None)], 379_000_000)  # 단위 근거 없음
    # 2026-11-09 유료 확인 gh-809: 「자동차가액이 4,542」 다음 줄 「만원 이하」를 담당이 검증할 수 없다며 조건식을 비움. 이어 인용하면 한 금액으로 읽음
    assert _krw_found([("총 자산 중 자동차가액이 4,542\n만원 이하 일 것", None)], 45_420_000)


def test_price_unit_must_come_from_the_same_column_or_table():
    # 2026-10-21 리뷰: 원 단위 칸을 천원으로 읽어 보증금 100만원이 10억이 됨
    assert not _price_unit_ok("1,000,000", "천원", [("임대보증금 1,000,000원", None)])
    table = "| 주택형 | 임대보증금(천원) | 임대료(원) |\n| 52C | 38,025 | 391,800 |"
    row = "| 52C | 38,025 | 391,800 |"
    place = place_of(table, table.index(row))
    assert _price_unit_ok("38,025", "천원", [(row, place)])
    assert not _price_unit_ok("391,800", "천원", [(row, place)])  # 옆 칸 머리글의 단위를 쓰지 않음


def test_child_and_household_counts_must_be_tied_to_their_column_or_words():
    # 2026-10-21 리뷰: txt 「3인 이상 2인 이상 120%」에서 가구원 수 3을 자녀 수로 뽑아도 숫자 3이 있어 통과했음
    assert not _count_bound("CHILD_COUNT", 3, [("3인 이상 2인 이상 120% 301,000,000원", None)])
    assert not _count_bound("CHILD_COUNT", 2, [("3인 이상 2인 이상 120% 301,000,000원", None)])  # 칸 구분이 없으면 어느 쪽인지 모름
    table = "| 가구원수 | 출생자녀수 | 비율 |\n| 3인 이상 | 2인 이상 | 120% |"
    row = "| 3인 이상 | 2인 이상 | 120% |"
    place = place_of(table, table.index(row))
    assert _count_bound("CHILD_COUNT", 2, [(row, place)]) and not _count_bound("CHILD_COUNT", 3, [(row, place)])
    assert _count_bound("HOUSEHOLD_MEMBER_COUNT", 3, [(row, place)])
    assert _count_bound("CHILD_COUNT", 2, [("2023. 3. 28. 이후 출생한 자녀가 2명 이상인 경우", None)])
    assert _count_bound("HOUSEHOLD_MEMBER_COUNT", 1, [("70%(1인 90%, 2인 80%) 이하", None)])


def test_exception_values_are_checked_like_the_base_condition():
    # 2026-10-21 리뷰: 예외 조건의 값은 원문과 대조하지 않았음
    quote = "2023. 3. 28. 이후 출생한 자녀가 2명 이상인 경우 자동차가액 5,451만원 이하"
    child = {"kind": "ATOMIC", "attribute": "CHILD_COUNT", "operator": "GTE", "value": 3, "unit": "COUNT", "evidenceIds": ["ev-1"]}
    car = {"kind": "ATOMIC", "attribute": "CAR_ASSETS_KRW", "operator": "LTE", "value": 5_451_000, "unit": "KRW", "evidenceIds": ["ev-1"]}
    base = {"kind": "ATOMIC", "attribute": "CAR_ASSETS_KRW", "operator": "LTE", "value": 45_420_000, "unit": "KRW", "evidenceIds": ["ev-2"]}
    candidate = {
        "evidence": [
            {"id": "ev-1", "sourceId": "t", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": len(quote)}, "quote": quote},
            {"id": "ev-2", "sourceId": "t", "locator": {"kind": "TEXT_RANGE", "start": 0, "end": 1}, "quote": "자동차가액 4,542만원 이하"},
        ],
        "eligibility": [
            {
                "rule": {"expression": base},
                "evidenceIds": ["ev-2"],
                "exceptions": [{"when": {"expression": child}, "effectExpression": car, "evidenceIds": ["ev-1"]}],
            }
        ],
        "notice": {},
        "schedules": [],
        "supplyGroups": [],
    }
    targets = {f.target for f in check_claims(candidate, SourceBundle(texts={"t": quote}))}
    assert targets == {"/eligibility/0/exceptions/0/when/expression/value", "/eligibility/0/exceptions/0/effectExpression/value"}
