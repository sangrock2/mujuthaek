"""공급표 금액 빈칸 채우기(요구 2-06): 표 칸이 빈 호실의 보증금·월임대료를 공고문 글에서 원문 대조로 채우고, 못 정하면 확인 필요. AI 호출 없음.

계약 예시(가상 주거 공고)에 가상의 호실 202호(표 금액 칸이 빔)와 문장을 덧붙인 합성 원문을 씁니다.
"""

import copy
import dataclasses

from helpers import ai_part, example, source_for

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.assemble.missing_prices import ISSUE_CODE, fill_missing_prices
from mujuthaek_extraction.verify.claims import check_claims
from mujuthaek_extraction.verify.model import SourceBundle

ROW = "| 202호 | 2층 | 20 |  |  |"
TABLE = f"| 호실 | 층 | 전용면적 | 임대보증금 | 월임대료 |\n{ROW}\n"


def run(extra, *, missing=()):
    """예시 공고 + 202호(가격 없는 공급 묶음, 표 행만 근거) + 덧붙인 원문 extra로 결합합니다."""
    data = example("housing")
    source = source_for("housing", data)
    text = f"{source.material.text}\n{TABLE}\n{extra}\n"
    source = dataclasses.replace(source, material=dataclasses.replace(source.material, text=text))
    part = ai_part(data)
    part["quotes"].append({"ref": "row202", "documentId": "text1", "text": ROW})
    group = copy.deepcopy(part["supplyGroups"][0])
    group.update(id="unit-202", housingTypeCode="20B", unitLabel="202호", prices=[], quoteRefs=["row202"], leaseTerm=None)
    group["scope"] = {**group["scope"], "supplyGroupIds": ["unit-202"], "description": "202호에 적용합니다."}
    part["supplyGroups"].append(group)
    part["missingFields"] = list(missing)
    result = assemble([part], source)
    return result, text


def issues(result):
    return [i for i in result.issues if i["code"] == ISSUE_CODE]


def test_empty_table_cells_are_filled_from_a_sentence_with_the_amounts_and_units():
    result, text = run("※ 202호 임대보증금 : 12,000천원, 월임대료 : 150,000원 (표 금액 누락분)")
    assert result.contract_errors == [] and issues(result) == []
    candidate = result.candidate
    prices = {p["kind"]: p for p in candidate["supplyGroups"][1]["prices"]}
    assert (prices["DEPOSIT"]["sourceAmount"], prices["DEPOSIT"]["sourceUnit"], prices["DEPOSIT"]["amountKrw"]) == ("12,000", "천원", 12_000_000)
    rent = prices["MONTHLY_RENT"]
    assert (rent["sourceAmount"], rent["amountKrw"], rent["billingPeriod"]) == ("150,000", 150_000, "MONTHLY")
    quotes = {e["id"]: e for e in candidate["evidence"]}
    deposit_quote = quotes[prices["DEPOSIT"]["evidenceIds"][0]]
    start, end = deposit_quote["locator"]["start"], deposit_quote["locator"]["end"]
    assert text[start:end] == deposit_quote["quote"] == "202호 임대보증금 : 12,000천원"
    # 채운 값도 다른 가격과 같은 값–인용 대조(V9: 금액·단위)를 통과합니다
    bundle = SourceBundle(texts={"text1": text}, pdfs={}, units={})
    assert [f for f in check_claims(candidate, bundle) if f.target.startswith("/supplyGroups/1")] == []
    assert any("공고문 글" in n for n in result.notes)


def test_two_amounts_for_one_label_are_not_chosen_and_go_to_review():
    result, _ = run("202호 임대보증금은 12,000천원(일반) 또는 9,000천원(청년)이며, 월임대료는 150,000원입니다.")
    group = result.candidate["supplyGroups"][1]
    assert [p["kind"] for p in group["prices"]] == ["MONTHLY_RENT"]  # 월임대료는 하나라 채우고 보증금은 비움
    [issue] = issues(result)
    assert issue["target"] == "/supplyGroups/1" and "보증금" in issue["description"]
    # 같은 이름이 두 곳에서 다른 금액으로 나와도 고르지 않습니다
    result, _ = run("202호 임대보증금 : 12,000천원\n\n(변경) 202호 임대보증금 : 13,000천원")
    assert not any(p["kind"] == "DEPOSIT" for p in result.candidate["supplyGroups"][1]["prices"])
    assert any("여럿" in i["description"] for i in issues(result))


def test_no_sentence_leaves_the_cell_empty_with_review_unless_the_ai_said_why():
    result, _ = run("그 밖의 호실은 추후 공지합니다.")
    assert result.candidate["supplyGroups"][1]["prices"] == []
    found = issues(result)
    assert {i["target"] for i in found} == {"/supplyGroups/1"} and all("찾지 못했습니다" in i["description"] for i in found)
    # AI가 「원문에 없음」으로 적었으면 그 기록을 두고 새 이슈는 만들지 않습니다
    noted = {"target": "/supplyGroups/1/prices", "reason": "NOT_IN_SOURCE", "description": "202호 금액 칸이 비어 있어요."}
    result, _ = run("그 밖의 호실은 추후 공지합니다.", missing=[noted])
    assert issues(result) == []


def test_unclear_amounts_are_not_used():
    # 단위 없는 숫자, 한도·이하, 다른 호실과 한 줄, 입찰보증금은 쓰지 않음(후보가 있었으니 확인 필요)
    for extra in (
        "202호 임대보증금 12,000 / 월임대료 150",
        "202호 임대보증금 최대 12,000천원, 월임대료 150,000원 이하",
        "202호와 203호 임대보증금 각 12,000천원, 월임대료 각 150,000원",
    ):
        result, _ = run(extra.replace("203호", "201호"))
        assert result.candidate["supplyGroups"][1]["prices"] == [], extra
        assert issues(result), extra


def test_amounts_written_with_eok_and_man_are_read_and_announced_or_attached_prices_are_kept_empty():
    group = {
        "id": "unit-7",
        "itemKind": "HOUSING_UNIT",
        "unitLabel": "7호",
        "housingTypeCode": None,
        "counts": [],
        "prices": [{"id": "unit-7.sale", "kind": "SALE_PRICE", "amountKrw": None, "sourceAmount": None, "sourceUnit": None, "scope": {"targetGroups": []}}],
    }
    text = "101동 7호 : 분양가격 1억 2,000만원(발코니 확장비 별도)\n"
    groups = [copy.deepcopy(group)]
    made = fill_missing_prices(groups, text, "text1", [])
    price = groups[0]["prices"][0]
    assert (price["sourceAmount"], price["sourceUnit"], price["amountKrw"], price["evidenceIds"]) == ("1억 2,000만", "원", 120_000_000, ["ev-1"])
    assert made.evidence[0]["quote"] == "7호 : 분양가격 1억 2,000만원" and made.issues == []
    # AI가 「추후 안내」로 비운 금액은 글에 숫자가 있어도 채우지 않습니다
    groups = [copy.deepcopy(group)]
    made = fill_missing_prices(groups, text, "text1", [], {"/supplyGroups/0/prices/0/sourceAmount": "TO_BE_ANNOUNCED"})
    assert groups[0]["prices"][0]["amountKrw"] is None and made.filled == [] and made.issues == []


def test_missing_price_issue_does_not_trigger_a_paid_recheck_call():
    from mujuthaek_extraction.recheck import problem_items
    from mujuthaek_extraction.verify.model import VerificationReport

    result, _ = run("그 밖의 호실은 추후 공지합니다.")
    assert issues(result)
    assert problem_items(VerificationReport(candidate=result.candidate, findings=[], contract_errors=[])) == {}
