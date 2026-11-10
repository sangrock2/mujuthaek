"""주거·이주 혜택(BENEFIT) 정제 → policy.extracted (2026-10-25, 담당자3 초안 모양). 합성 자료와 녹화 응답만 씁니다. AI·네트워크 호출 없음."""

import json
from contextlib import contextmanager

import pytest

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.benefit.build import build_payload, has_won, quoted, same_value, won_amounts
from mujuthaek_extraction.benefit.codes import rules_for, youth_rules
from mujuthaek_extraction.benefit.reading import BenefitReading, read_benefit
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import ModelError, RecordedModel

REGIONS = RegionCodeTable(
    [
        ("2700000000", "대구광역시", True),
        ("2711000000", "대구광역시 중구", True),
        ("2714000000", "대구광역시 동구", True),
        ("5200000000", "전북특별자치도", True),
        ("5273000000", "전북특별자치도 무주군", True),
    ],
    "2026-10-01",
)

TEXT = """제목: 가상 청년 전월세 보증금 이자 지원
기관: 가상광역시 주택과
지역: 시군구
분야: 주거, 전월세 및 주거급여 지원
[항목]
정책 설명: 목돈 마련이 어려운 가상 청년을 위해 전월세 임차보증금 대출이자 지원
지원 내용: 대출금 최대 1억원(임차보증금의 90% 이내)의 최대 연 3.5% 이자지원
지원 대상 최소 연령: 19
지원 대상 최대 연령: 39
추가 신청 자격: 19 ~ 39세 대구시 거주 무주택 청년
 - (물건기준) 전세보증금 2.5억원 이하 주거용 주택
 - (소득기준) 연소득 6천만원(부부합산 8천만원)이하
신청 방법: 가상 누리집 온라인 신청
사업 시작일: 20260107
사업 종료일: 20261231"""

RECORD = {
    "jobCd": "0013010",
    "zipCd": "27110,27140",
    "plcyNo": "20261021000000000001",
    "sbizCd": "0014010",
    "aplyYmd": None,
    "schoolCd": "0049010",
    "mrgSttsCd": "0055003",
    "earnCndSeCd": "0043001",
    "earnMaxAmt": "0",
    "earnMinAmt": "0",
    "aplyPrdSeCd": "0057002",
    "bizPrdBgngYmd": "20260107",
    "bizPrdEndYmd": "20261231",
    "sprtTrgtMaxAge": "39",
    "sprtTrgtMinAge": "19",
    "sprtTrgtAgeLmtYn": "N",
}


def payload(**changes):
    base = {
        "rawPolicyId": "01929a3e-0000-7000-8000-0000000b0001",
        "version": 1,
        "sourceCode": "youth",
        "provider": "YOUTHCENTER",
        "field": "BENEFIT",
        "policyId": "20261021000000000001",
        "title": "가상 청년 전월세 보증금 이자 지원",
        "agency": "가상광역시 주택과",
        "regionScope": "SIGUNGU",
        "regionNames": [],
        "regionCodes": ["27110", "27140"],
        "categories": ["주거", "전월세 및 주거급여 지원"],
        "detailUrl": "https://example.test/policy/1",
        "applyUrl": None,
        "sourceModifiedAt": None,
        "text": TEXT,
        "textKey": None,
        "record": RECORD,
        "hasDocument": False,
        "hasOriginText": False,
        "documentStatus": "NONE",
        "originStatus": "NONE",
        "files": [],
        "reprocess": False,
    }
    return base | changes


def condition(type_, evidence, **fields):
    empty = {
        "group": 1,
        "type": type_,
        "rawText": evidence,
        "evidence": evidence,
        "confidence": 0.9,
        "min": None,
        "max": None,
        "values": [],
        "basis": None,
        "regionNames": [],
        "months": None,
        "amountMinWon": None,
        "amountMaxWon": None,
        "amountPer": None,
        "assetKind": None,
        "leaseKinds": [],
        "depositMaxWon": None,
        "monthlyMaxWon": None,
    }
    return empty | fields


def answer(conditions=None, supports=None, **changes):
    base = {
        "relevant": True,
        "relevanceReason": "가상 청년의 전월세 보증금 대출 이자를 지원하는 주거 혜택",
        "summary": "가상 청년 전월세 보증금 대출 이자 최대 연 3.5% 지원",
        "supports": supports
        if supports is not None
        else [
            {
                "kind": "DEPOSIT_LOAN",
                "amountMaxWon": None,
                "amountPer": None,
                "months": None,
                "ratePct": 3.5,
                "rawText": "대출금 최대 1억원의 최대 연 3.5% 이자지원",
                "evidence": "대출금 최대 1억원(임차보증금의 90% 이내)의 최대 연 3.5% 이자지원",
            }
        ],
        "schedule": {"applyStart": None, "applyEnd": None, "applyAlways": True, "businessStart": "2026-01-07", "businessEnd": "2026-12-31", "rawText": None},
        "howToApply": "가상 누리집 온라인 신청",
        "documents": [],
        "contact": None,
        "conditions": conditions or [],
    }
    return base | changes


def built(conditions=None, **kw):
    reading = BenefitReading(answer(conditions, **kw), truncated=False, model="recorded")
    data = payload()
    return build_payload(data, reading, rules_for("youth", data["record"], data["text"]), REGIONS)


# ---- 규칙 (온통청년 코드 칸) ----


def test_youth_rules_move_age_and_schedule_and_skip_no_limit_codes_and_policy_region():
    rules = youth_rules(RECORD, TEXT)
    by_type = {c["type"]: c for c in rules.conditions}
    # 취업·학력·특화·결혼은 「제한없음」 코드라 줄 없음. zipCd는 정책 지역이라 거주 조건으로 옮기지 않음
    assert set(by_type) == {"AGE"}
    assert by_type["AGE"]["value"] == {"min": 19, "max": 39} and by_type["AGE"]["evidence"] == "지원 대상 최대 연령: 39"
    assert all(c["origin"] == "RULE" and c["confidence"] == 1 for c in rules.conditions)
    assert rules.schedule == {"applyAlways": True, "rawText": "상시", "businessStart": "2026-01-07", "businessEnd": "2026-12-31"}


def test_youth_codes_with_several_values_become_one_or_group():
    record = RECORD | {
        "jobCd": "0013001,0013008",
        "mrgSttsCd": "0055001",
        "earnCndSeCd": "0043002",
        "earnMaxAmt": "5000",
        "aplyPrdSeCd": "0057001",
        "aplyYmd": "20260123 ~ 20260202",
    }
    rules = youth_rules(record, TEXT)
    jobs = [c for c in rules.conditions if c["type"] in ("EMPLOYMENT", "OCCUPATION")]
    assert [(c["type"], c["value"]) for c in jobs] == [("EMPLOYMENT", {"in": ["EMPLOYED"]}), ("OCCUPATION", {"in": ["FARMER"]})]
    assert len({c["group"] for c in jobs}) == 1  # 「재직자 또는 영농종사자」
    assert {"type": "MARITAL", "value": {"in": ["MARRIED"]}}.items() <= next(c for c in rules.conditions if c["type"] == "MARITAL").items()
    income = next(c for c in rules.conditions if c["type"] == "INCOME_AMOUNT")
    # 본인·부부 기준을 몰라 값은 비우고 금액만 조립에 넘김
    assert (income["known"], income["value"], income["rawText"]) == (False, None, "연소득 5000만 원 이하")
    assert rules.income == {"max": 5000}
    assert rules.schedule["applyStart"] == "2026-01-23" and rules.schedule["applyEnd"] == "2026-02-02" and rules.schedule["applyAlways"] is False


def test_other_sources_have_no_rules_yet():
    assert rules_for("gov24", {"JA0110": "Y"}, TEXT).conditions == []


# ---- 금액·근거 ----


@pytest.mark.parametrize(
    ("quote", "won"),
    [
        ("연소득 6천만원 이하", 60_000_000),
        ("전세보증금 2.5억원 이하", 250_000_000),
        ("최대 1억 5천만원", 150_000_000),
        ("5,000만 원", 50_000_000),
        ("월 20만원", 200_000),
        ("연소득 4천 5백만 원 이하", 45_000_000),
        ("재산 122백만원 이하", 122_000_000),
        ("보증금 6.5천만원", 65_000_000),
    ],
)
def test_korean_amounts_are_read(quote, won):
    assert has_won(quote, won)


def test_numbers_without_money_unit_are_not_amounts():
    assert won_amounts("만 19~39세, 2026년") == set()


def test_quote_must_be_in_the_source():
    assert quoted("연소득 6천만원(부부합산 8천만원)이하", [TEXT])
    assert not quoted("연소득 7천만원 이하", [TEXT])
    assert not quoted("청년", [TEXT])  # 너무 짧은 인용


# ---- 조립 ----


def test_ai_conditions_are_checked_and_converted_to_manwon():
    data = built(
        [
            condition("HOMELESS", "대구시 거주 무주택 청년", basis="PERSON", group=1),
            condition("INCOME_AMOUNT", "연소득 6천만원(부부합산 8천만원)이하", group=2, amountMaxWon=60_000_000, amountPer="YEAR", basis="PERSONAL"),
            condition("INCOME_AMOUNT", "연소득 6천만원(부부합산 8천만원)이하", group=2, amountMaxWon=80_000_000, amountPer="YEAR", basis="HOUSEHOLD"),
            condition("LEASE", "전세보증금 2.5억원 이하 주거용 주택", group=3, leaseKinds=["JEONSE"], depositMaxWon=250_000_000),
        ]
    )
    ai = [c for c in data["conditions"] if c["origin"] == "AI"]
    assert [(c["type"], c["value"]) for c in ai] == [
        ("HOMELESS", {"basis": "PERSON"}),
        ("INCOME_AMOUNT", {"unit": "MANWON_PER_YEAR", "basis": "PERSONAL", "max": 6000}),
        ("INCOME_AMOUNT", {"unit": "MANWON_PER_YEAR", "basis": "HOUSEHOLD", "max": 8000}),
        ("LEASE", {"unit": "MANWON", "kind": ["JEONSE"], "depositMax": 25000}),
    ]
    rule_groups = {c["group"] for c in data["conditions"] if c["origin"] == "RULE"}
    assert min(c["group"] for c in ai) > max(rule_groups)  # AI 묶음 번호는 규칙 뒤로
    assert ai[1]["group"] == ai[2]["group"]  # 본인 또는 부부 기준
    assert data["supports"][0]["ratePct"] == 3.5 and data["supports"][0]["amountMax"] is None
    # 「본인 6천 또는 부부 8천」은 기혼자의 본인 소득만 6천 이하여도 맞아 너그럽게 틀릴 수 있어 확인 필요(2026-10-26 공통 규칙)
    assert data["quality"]["needsReview"] is True and data["quality"]["reviewReasons"] == ["LOW_CONFIDENCE", "NO_DOCUMENT"]
    assert (
        tools().validate(
            {
                "eventId": "01929a3e-0000-7000-8000-000000000e01",
                "eventType": "policy.extracted",
                "schemaVersion": 1,
                "occurredAt": "2026-10-25T00:00:00Z",
                "producer": "extraction",
                "payload": data,
            },
            "events/policy.extracted.v1.json",
        )
        == []
    )


def test_wrong_number_or_missing_quote_leaves_the_value_empty():
    data = built(
        [
            condition("INCOME_AMOUNT", "연소득 6천만원(부부합산 8천만원)이하", amountMaxWon=70_000_000, amountPer="YEAR", basis="PERSONAL"),
            condition("HOMELESS", "주택을 소유하지 않은 세대주", basis="HOUSEHOLD", group=2),
        ]
    )
    ai = [c for c in data["conditions"] if c["origin"] == "AI"]
    assert [(c["type"], c["known"], c["value"]) for c in ai] == [("INCOME_AMOUNT", False, None), ("HOMELESS", False, None)]
    assert ai[1]["confidence"] <= 0.3
    assert "EVIDENCE_NOT_FOUND" in data["quality"]["reviewReasons"] and data["quality"]["needsReview"] is True


def test_age_is_always_filled_and_the_text_value_wins_over_the_code_field():
    same = built([condition("AGE", "19 ~ 39세 대구시 거주 무주택 청년", min=19, max=39)])
    assert [(c["origin"], c["known"]) for c in same["conditions"]] == [("RULE", True)]  # AI의 나이는 규칙 줄로 대신
    assert "RULE_AI_CONFLICT" not in same["quality"]["reviewReasons"]
    differ = built([condition("AGE", "19 ~ 39세 대구시 거주 무주택 청년", min=19, max=34)])
    assert "RULE_AI_CONFLICT" not in differ["quality"]["reviewReasons"]  # 34가 근거에 없어 값이 비므로 비교하지 않음
    other = built_text(TEXT + "\n신청 자격: 만 19세 이상 34세 이하", [condition("AGE", "만 19세 이상 34세 이하", min=19, max=34)])
    # 원문 「만 19세 이상 34세 이하」가 코드 칸 19~39와 다름 → 원문 값을 채우고 확인 필요(나이는 비우지 않음, 2026-10-25 사용자 결정)
    assert [(c["origin"], c["known"], c["value"]) for c in other["conditions"]] == [("AI", True, {"min": 19, "max": 34})]
    assert "RULE_AI_CONFLICT" in other["quality"]["reviewReasons"] and other["quality"]["needsReview"] is True


def test_same_value_treats_region_containment_as_same():
    assert same_value("RESIDENCE", {"regions": ["27110", "27140"]}, {"regions": ["27"]})
    assert not same_value("RESIDENCE", {"regions": ["27110"]}, {"regions": ["52"]})


def test_homeless_needs_a_quote_about_owning_a_house_not_living_on_the_street():
    # 2026-10-29: 「일정한 주거 없이 노숙…」(행려자·부랑인)을 무주택(HOMELESS)으로 읽어 노숙인 혜택이 무주택자 혜택이 됐어요.
    # 근거가 주택 소유를 말하지 않으면 비우고 검수로, 주택 소유를 말하면 그대로
    text = TEXT + "\n지원 대상: 일정한 주거 없이 노숙생활을 하는 것으로 확인된 자\n모집 대상: 관내 청년 누구나"
    data = payload(text=text)

    def build(conditions):
        reading = BenefitReading(answer(conditions), truncated=False, model="recorded")
        return build_payload(data, reading, rules_for("youth", data["record"], data["text"]), REGIONS)

    street = build([condition("HOMELESS", "일정한 주거 없이 노숙생활을 하는 것으로 확인된 자", basis="PERSON")])
    [row] = [c for c in street["conditions"] if c["origin"] == "AI"]
    assert (row["type"], row["known"], row["value"]) == ("HOMELESS", False, None)
    assert "LOW_CONFIDENCE" in street["quality"]["reviewReasons"] and street["quality"]["needsReview"] is True

    # 「모집」 속 「집」은 주택 이야기가 아니에요
    recruit = build([condition("HOMELESS", "모집 대상: 관내 청년 누구나", basis="PERSON")])
    assert [c["known"] for c in recruit["conditions"] if c["origin"] == "AI"] == [False]

    owner = build([condition("HOMELESS", "19 ~ 39세 대구시 거주 무주택 청년", basis="PERSON")])
    [row] = [c for c in owner["conditions"] if c["origin"] == "AI" and c["type"] == "HOMELESS"]
    assert (row["known"], row["value"]) == (True, {"basis": "PERSON"})


def test_text_only_conditions_are_unknown_and_source_regions_are_filled():
    data = build_payload(
        payload(regionCodes=[], regionNames=["전북특별자치도 무주군"], sourceCode="gov24", provider="GOV24", record={}),
        BenefitReading(answer([condition("EXCLUSIVE", "대구시 거주 무주택 청년")]), truncated=True, model="recorded"),
        rules_for("gov24", {}, TEXT),
        REGIONS,
    )
    assert data["conditions"][0]["known"] is False and data["conditions"][0]["value"] is None
    assert data["source"]["regionCodes"] == ["52730"]
    assert {"TEXT_TRUNCATED", "LOW_CONFIDENCE"} <= set(data["quality"]["reviewReasons"]) and data["quality"]["confidence"] <= 0.5


# ---- AI 읽기·worker ----


def test_read_benefit_refuses_bad_shape():
    with pytest.raises(ModelError) as caught:
        read_benefit(payload(), RecordedModel({"benefit_reading": ['{"relevant": true}']}))
    assert caught.value.code == "BAD_SHAPE"


class FakeStore:
    def __init__(self):
        self.saved = []

    def judged(self, raw_event):
        return False

    def save_benefit(self, raw_event, event):
        self.saved.append(event)
        return True


def raw_event(**changes):
    return {"eventId": "01929a3e-0000-7000-8000-00000000e0b1", "eventType": "raw.policy.collected", "payload": payload(**changes)}


def test_judge_benefit_publishes_a_contract_valid_policy_extracted():
    from mujuthaek_extraction.worker import judge_benefit

    store = FakeStore()
    model = RecordedModel({"benefit_reading": [json.dumps(answer([condition("HOMELESS", "대구시 거주 무주택 청년", basis="PERSON")]), ensure_ascii=False)]})
    event_id = judge_benefit(store, raw_event(), model, REGIONS)
    [event] = store.saved
    assert event_id == event["eventId"] and event["eventType"] == "policy.extracted"
    assert tools().validate(event, "events/policy.extracted.v1.json") == []
    assert judge_benefit(store, raw_event(field="STARTUP_SUPPORT"), model, REGIONS) is None


def test_judge_benefit_maps_model_failures():
    from mujuthaek_extraction.worker import AiFailed, judge_benefit

    with pytest.raises(AiFailed):
        judge_benefit(FakeStore(), raw_event(), RecordedModel({"benefit_reading": ["not json"]}), REGIONS)


def test_benefit_is_skipped_unless_enabled(monkeypatch):
    from mujuthaek_extraction import worker

    called = []
    monkeypatch.setattr(worker, "judge_benefit", lambda *a: called.append("benefit"))
    monkeypatch.setattr(worker, "judge_policy", lambda *a: called.append("policy"))

    class Settings:
        benefit_enabled = False
        notice_budget_usd = 1.0

    class Models:
        fallback = None

        def for_notice(self, ledger=None):
            return self

        primary = None

    class Processor:
        models = Models()
        regions = None

        def open_ledger(self, raw_event):
            return None

    @contextmanager
    def session(settings):
        yield FakeStore()

    monkeypatch.setattr(worker, "store_session", session)
    retries = worker.RetryCounter(3) if hasattr(worker, "RetryCounter") else None
    assert worker.judge_message(Settings(), Processor(), raw_event(), retries) == "ack" and called == []
    Settings.benefit_enabled = True
    assert worker.judge_message(Settings(), Processor(), raw_event(), retries) == "ack" and called == ["benefit"]


# ---- 묶음(group): 같은 번호 = 「또는」 (2026-10-25 첫 유료 시험에서 판정이 틀어진 경우) ----

OR_TEXT = TEXT + "\n신청 자격: 대구광역시에 주소를 두거나 대구시 소재 대학 또는 직장에 재학, 재직하는 청년\n - 쉐어하우스 입주자는 신청 불가"


def built_text(text, conditions, record=RECORD):
    data = payload(text=text, record=record)
    reading = BenefitReading(answer(conditions), truncated=False, model="recorded")
    return build_payload(data, reading, rules_for("youth", data["record"], text), REGIONS)


EMPLOYED = RECORD | {"jobCd": "0013001"}


def test_rule_row_joins_the_ai_or_group_it_replaces():
    quote = "대구광역시에 주소를 두거나 대구시 소재 대학 또는 직장에 재학, 재직하는 청년"
    data = built_text(
        OR_TEXT,
        [
            condition("RESIDENCE", quote, group=1, regionNames=["대구광역시"]),
            condition("EDUCATION", quote, group=1, values=["UNIV_ENROLLED"]),
            condition("EMPLOYMENT", quote, group=1, values=["EMPLOYED"]),
        ],
        EMPLOYED,
    )
    groups = {c["type"]: c["group"] for c in data["conditions"]}
    assert groups["RESIDENCE"] == groups["EDUCATION"] == groups["EMPLOYMENT"]  # 「거주 또는 재학 또는 재직」
    assert groups["AGE"] != groups["RESIDENCE"]
    assert [c["origin"] for c in data["conditions"] if c["type"] == "EMPLOYMENT"] == ["RULE"]


def test_rule_row_stays_alone_when_the_ai_group_has_nothing_else():
    data = built_text(OR_TEXT, [condition("EMPLOYMENT", "직장에 재학, 재직하는 청년", group=1, values=["EMPLOYED"])], EMPLOYED)
    assert sorted(c["group"] for c in data["conditions"]) == [1, 2]


def test_text_only_rows_get_their_own_group_and_rule_lines_are_not_repeated():
    data = built_text(
        OR_TEXT,
        [
            condition("LEASE", "전세보증금 2.5억원 이하 주거용 주택", group=1, leaseKinds=["JEONSE"], depositMaxWon=250_000_000),
            condition("OTHER", "쉐어하우스 입주자는 신청 불가", group=1),
            condition("OTHER", "지원 대상 최대 연령: 39", group=1),  # 규칙 줄(AGE)의 근거를 다시 낸 줄
        ],
    )
    ai = [c for c in data["conditions"] if c["origin"] == "AI"]
    assert [c["type"] for c in ai] == ["LEASE", "OTHER"]
    assert ai[0]["group"] != ai[1]["group"]
    assert len({c["group"] for c in data["conditions"]}) == len(data["conditions"])


def test_unrelated_rows_in_one_ai_group_are_split_and_rules_stay_put():
    # AI가 관계없는 조건을 모두 1번으로 줌: 나이(규칙으로 대신)·임대·무주택은 근거 문장이 달라 「또는」이 아님
    data = built_text(
        OR_TEXT,
        [
            condition("AGE", "지원 대상 최대 연령: 39", group=1, min=19, max=39),
            condition("LEASE", "전세보증금 2.5억원 이하 주거용 주택", group=1, leaseKinds=["JEONSE"], depositMaxWon=250_000_000),
            condition("HOMELESS", "대구시 거주 무주택 청년", group=1, basis="PERSON"),
        ],
    )
    assert len({c["group"] for c in data["conditions"]}) == len(data["conditions"])


def test_core_values_split_by_track_become_one_or_group_and_need_review():
    # 「청년 전형은 미혼, 부부 전형은 기혼」을 「미혼 그리고 기혼」으로 담으면 아무도 못 맞추므로 「미혼 또는 기혼」으로 모으고 확인 필요
    text = TEXT + "\n신청 자격: 청년 전형은 미혼 청년\n청년부부 전형은 혼인한 부부"
    data = built_text(
        text,
        [
            condition("MARITAL", "청년 전형은 미혼 청년", group=1, values=["SINGLE"]),
            condition("MARITAL", "청년부부 전형은 혼인한 부부", group=2, values=["MARRIED"]),
            condition("HOMELESS", "대구시 거주 무주택 청년", group=3, basis="PERSON"),
        ],
    )
    marital = [c for c in data["conditions"] if c["type"] == "MARITAL"]
    assert [(c["known"], c["value"]) for c in marital] == [(True, {"in": ["SINGLE"]}), (True, {"in": ["MARRIED"]})]
    assert marital[0]["group"] == marital[1]["group"]
    assert next(c for c in data["conditions"] if c["type"] == "HOMELESS")["known"] is True
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"] and data["quality"]["needsReview"] is True


INCOME_RECORD = RECORD | {"earnCndSeCd": "0043002", "earnMaxAmt": "6000"}
INCOME_QUOTE = "연소득 6천만원(부부합산 8천만원)이하"


def test_source_income_is_replaced_by_the_ai_rows_that_read_the_same_amount_with_its_basis():
    data = built_text(
        TEXT,
        [
            condition("INCOME_AMOUNT", INCOME_QUOTE, amountMaxWon=60_000_000, amountPer="YEAR", basis="PERSONAL"),
            condition("INCOME_AMOUNT", INCOME_QUOTE, amountMaxWon=80_000_000, amountPer="YEAR", basis="HOUSEHOLD"),
        ],
        INCOME_RECORD,
    )
    income = [(c["origin"], c["value"]) for c in data["conditions"] if c["type"] == "INCOME_AMOUNT"]
    assert income == [
        ("AI", {"unit": "MANWON_PER_YEAR", "basis": "PERSONAL", "max": 6000}),
        ("AI", {"unit": "MANWON_PER_YEAR", "basis": "HOUSEHOLD", "max": 8000}),
    ]
    assert "RULE_AI_CONFLICT" not in data["quality"]["reviewReasons"]


def test_source_income_without_a_text_basis_is_filled_as_household_and_a_text_amount_wins():
    alone = built_text(TEXT, [], INCOME_RECORD)  # 원문에 기준이 없으면 가구(부부합산) 기준으로 채우고 확인 필요
    assert [(c["origin"], c["value"]) for c in alone["conditions"] if c["type"] == "INCOME_AMOUNT"] == [
        ("RULE", {"unit": "MANWON_PER_YEAR", "basis": "HOUSEHOLD", "max": 6000})
    ]
    assert alone["quality"]["needsReview"] is True and "LOW_CONFIDENCE" in alone["quality"]["reviewReasons"]
    guessed = built_text(  # 출처 칸 줄을 근거로 기준을 지어낸 줄은 세지 않음
        TEXT + "\n소득 최대 금액: 6000",
        [condition("INCOME_AMOUNT", "소득 최대 금액: 6000", amountMaxWon=60_000_000, amountPer="YEAR", basis="PERSONAL")],
        INCOME_RECORD,
    )
    assert [(c["origin"], c["value"]["basis"]) for c in guessed["conditions"] if c["type"] == "INCOME_AMOUNT"] == [("RULE", "HOUSEHOLD")]
    other = built_text(  # 원문 금액(부부합산 8천만)이 코드 칸(5천만)과 다르면 원문 줄을 쓰고 확인 필요
        TEXT,
        [condition("INCOME_AMOUNT", INCOME_QUOTE, amountMaxWon=80_000_000, amountPer="YEAR", basis="HOUSEHOLD")],
        RECORD | {"earnCndSeCd": "0043002", "earnMaxAmt": "5000"},
    )
    assert [(c["origin"], c["value"]) for c in other["conditions"] if c["type"] == "INCOME_AMOUNT"] == [
        ("AI", {"unit": "MANWON_PER_YEAR", "basis": "HOUSEHOLD", "max": 8000})
    ]
    assert "RULE_AI_CONFLICT" in other["quality"]["reviewReasons"]


def test_conditional_core_amounts_stay_as_or_and_need_review():
    text = TEXT + "\n(소득) 부부합산 연소득 1.3억원 이하 (단, 맞벌이 가구는 2억원 이하)"
    quote = "부부합산 연소득 1.3억원 이하 (단, 맞벌이 가구는 2억원 이하)"
    data = built_text(
        text,
        [
            condition("INCOME_AMOUNT", quote, amountMaxWon=130_000_000, amountPer="YEAR", basis="HOUSEHOLD"),
            condition("INCOME_AMOUNT", quote, amountMaxWon=200_000_000, amountPer="YEAR", basis="HOUSEHOLD"),
        ],
    )
    assert [c["value"]["max"] for c in data["conditions"] if c["type"] == "INCOME_AMOUNT"] == [13000, 20000]  # 「1.3억 또는 (맞벌이) 2억」
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]


def test_an_unused_amount_in_the_quote_leaves_the_amount_unknown():
    text = TEXT + "\n전세: 보증금 5억원(지방 4억원 이하)"
    data = built_text(text, [condition("LEASE", "전세: 보증금 5억원(지방 4억원 이하)", leaseKinds=["JEONSE"], depositMaxWon=500_000_000)])
    assert [(c["known"], c["value"]) for c in data["conditions"] if c["type"] == "LEASE"] == [(False, None)]
    both = built_text(  # 보증금·월세 두 금액을 한 줄이 다 씀
        TEXT + "\n보증금 6.5천만원, 월세금 70만원 이하",
        [condition("LEASE", "보증금 6.5천만원, 월세금 70만원 이하", leaseKinds=["MONTHLY"], depositMaxWon=65_000_000, monthlyMaxWon=700_000)],
    )
    assert [c["value"] for c in both["conditions"] if c["type"] == "LEASE"] == [{"unit": "MANWON", "kind": ["MONTHLY"], "depositMax": 6500, "monthlyMax": 70}]


def test_age_from_the_text_with_under_and_over_wording():
    text = TEXT + "\n(대상)관내 거주 청년농업인 - 만18세이상, 만40세미만"
    data = built_text(text, [condition("AGE", "만18세이상, 만40세미만", min=18, max=39)])
    age = next(c for c in data["conditions"] if c["type"] == "AGE")
    assert (age["value"], age["rawText"]) == ({"min": 18, "max": 39}, "만18세이상, 만40세미만")
    assert "RULE_AI_CONFLICT" in data["quality"]["reviewReasons"]


def test_ages_split_into_and_groups_are_merged_into_one_range():
    text = TEXT + "\n(19세 ~ 34세) 복지로 신청\n(35세 ~ 39세) 인천청년포털 신청"
    no_age = RECORD | {"sprtTrgtMinAge": "0", "sprtTrgtMaxAge": "0"}
    data = built_text(
        text,
        [condition("AGE", "(19세 ~ 34세) 복지로 신청", group=1, min=19, max=34), condition("AGE", "(35세 ~ 39세) 인천청년포털 신청", group=2, min=35, max=39)],
        no_age,
    )
    assert [(c["known"], c["value"]) for c in data["conditions"] if c["type"] == "AGE"] == [(True, {"min": 19, "max": 39})]


def test_core_values_without_a_basis_get_the_default_basis_and_need_review():
    text = TEXT + "\n추가 신청 자격: 무주택 및 자산요건 충족\n소득 기타 조건: 기준 중위소득 150% 이하"
    data = built_text(
        text,
        [
            condition("INCOME_MEDIAN_PCT", "기준 중위소득 150% 이하", max=150),
            condition("HOMELESS", "무주택 및 자산요건 충족", group=2),
        ],
    )
    values = {c["type"]: c["value"] for c in data["conditions"] if c["origin"] == "AI"}
    assert values == {"INCOME_MEDIAN_PCT": {"max": 150, "basis": "HOUSEHOLD"}, "HOMELESS": {"basis": "PERSON"}}
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]


def test_documents_how_to_apply_and_contact_come_from_the_source_fields():
    record = RECORD | {
        "sbmsnDcmntCn": "□ 공통 제출 서류\n1. 지원신청서\n2. 주민등록등본\n신분증, 확정일자부 임대차(전세)계약서 사본\n9. 기타 추가서류 ※ 공고에 따름",
        "plcyAplyMthdCn": "□ 온라인 신청: 가상 누리집\n※ 지점마다 다름",
        "sprvsnInstCdNm": "가상광역시 주택과",
        "sprvsnInstPicNm": "홍길동",
    }
    data = built_text(TEXT, [], record)
    assert data["documents"] == ["지원신청서", "주민등록등본", "신분증", "확정일자부 임대차(전세)계약서 사본", "기타 추가서류"]
    assert data["howToApply"] == "가상 누리집 온라인 신청"  # AI 답이 있으면 AI 요약
    assert data["contact"] == "가상광역시 주택과"  # AI 답이 없으면 주관 기관 이름만(담당자 실명 제외)
    empty = build_payload(payload(record=record), BenefitReading(answer(howToApply=None), False, "recorded"), rules_for("youth", record, TEXT), REGIONS)
    assert empty["howToApply"] == "온라인 신청: 가상 누리집"


def test_a_district_name_without_its_city_uses_the_registering_city():
    table = RegionCodeTable(
        [
            ("2700000000", "대구광역시", True),
            ("2723000000", "대구광역시 북구", True),
            ("2900000000", "광주광역시", True),
            ("2917000000", "광주광역시 북구", True),
        ],
        "2026-10-01",
    )
    record = RECORD | {"rgtrHghrkInstCdNm": "대구광역시"}
    text = TEXT + "\n북구에 주소를 둔 청년"
    data = build_payload(
        payload(text=text, record=record),
        BenefitReading(answer([condition("RESIDENCE", "북구에 주소를 둔 청년", regionNames=["북구"])]), False, "recorded"),
        rules_for("youth", record, text),
        table,
    )
    assert [c["value"] for c in data["conditions"] if c["type"] == "RESIDENCE"] == [{"regions": ["27230"]}]
    vague = build_payload(  # 「관내」는 지역 이름이 아니므로 시도 전체로 잡지 않음
        payload(text=text, record=record),
        BenefitReading(answer([condition("RESIDENCE", "북구에 주소를 둔 청년", regionNames=["관내"])]), False, "recorded"),
        rules_for("youth", record, text),
        table,
    )
    assert [c["known"] for c in vague["conditions"] if c["type"] == "RESIDENCE"] == [False]


def test_workplace_is_an_sme_only_when_the_quote_says_so():
    text = TEXT + "\n대구시 소재 직장에 재직하는 청년"
    data = built_text(text, [condition("WORKPLACE", "대구시 소재 직장에 재직하는 청년", values=["SME"], regionNames=["대구광역시"])])
    assert [c["value"] for c in data["conditions"] if c["type"] == "WORKPLACE"] == [{"regions": ["27"]}]


def test_a_loan_limit_on_another_line_is_filled_and_needs_review():
    text = TEXT + "\n(보증금) 연 1.3%\n(보증금) 최대 4,500만원 이내"
    support = {
        "kind": "DEPOSIT_LOAN",
        "amountMaxWon": 45_000_000,
        "amountPer": "ONCE",
        "months": None,
        "ratePct": 1.3,
        "rawText": "보증금 최대 4,500만원, 연 1.3%",
        "evidence": "(보증금) 연 1.3%",
    }
    data = build_payload(payload(text=text), BenefitReading(answer(supports=[support]), False, "recorded"), rules_for("youth", RECORD, text), REGIONS)
    assert (data["supports"][0]["amountMax"], data["supports"][0]["ratePct"]) == (4500, 1.3)
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]
    nowhere = {**support, "amountMaxWon": 55_000_000}  # 원문 어디에도 없는 금액은 비움
    data = build_payload(payload(text=text), BenefitReading(answer(supports=[nowhere]), False, "recorded"), rules_for("youth", RECORD, text), REGIONS)
    assert data["supports"][0]["amountMax"] is None


def test_counts_with_small_units_are_not_amounts():
    """「청년 5천명」「3백 가구」는 금액이 아닙니다. 천·백·십만 붙은 숫자는 「원」이 있어야 금액(2026-10-25 검토)."""
    assert won_amounts("청년 5천명 지원, 최대 2억원") == {200_000_000}
    assert won_amounts("3백 가구 모집") == set()
    assert won_amounts("월 5천원 지원") == {5_000}


def test_parts_of_one_sentence_share_used_amounts():
    """같은 문장 전체와 그 일부를 근거로 두 조건이 금액을 나눠 쓰면 남는 금액이 없습니다."""
    from mujuthaek_extraction.benefit.build import _leftover_amounts

    whole = {"type": "INCOME_AMOUNT", "evidence": "연소득 6천만원(부부합산 8천만원)이하", "amountMaxWon": 60_000_000}
    part = {"type": "INCOME_AMOUNT", "evidence": "부부합산 8천만원", "amountMaxWon": 80_000_000}
    assert _leftover_amounts([whole, part]) == set()
    # 정말 남는 금액(조건부 금액일 수 있음)은 그대로 잡습니다
    alone = {"type": "LEASE", "evidence": "전세 보증금 5억원(지방 4억원 이하)", "depositMaxWon": 500_000_000}
    assert _leftover_amounts([alone]) == {"전세보증금5억원(지방4억원이하)"}


def test_ai_dates_must_be_written_as_dates():
    """연·월·일 숫자가 원문에 따로따로 있는 것만으로는 날짜로 인정하지 않습니다(2026-10-25 검토)."""
    from mujuthaek_extraction.benefit.build import _date

    assert _date("2026-12-31", "2026년 사업 · 만 31세 이하 · 12개월 거주") is None
    assert _date("2026-12-31", "신청 기간: 2026. 11. 1. ~ 2026. 12. 31.", end=True) == "2026-12-31"
    assert _date("2026-01-07", "사업 시작일: 20260107") == "2026-01-07"
    assert _date("2025-11-01", "신청 기간: 2026. 11. 1.") is None  # 연도가 다름


def test_separate_age_ranges_stay_as_or_and_need_review():
    """이어지지 않는 나이 범위(19~24, 30~34)는 지우지 않고 「또는」으로 남기고 확인 필요(2026-10-25 검토)."""
    from mujuthaek_extraction.benefit.build import _merge_ages

    rows = [
        {"type": "AGE", "value": {"min": 19, "max": 24}, "group": 1, "known": True, "rawText": "19~24세"},
        {"type": "AGE", "value": {"min": 30, "max": 34}, "group": 2, "known": True, "rawText": "30~34세"},
    ]
    assert _merge_ages(rows) is True
    assert [(r["value"], r["group"]) for r in rows] == [({"min": 19, "max": 24}, 1), ({"min": 30, "max": 34}, 1)]
    joined = [
        {"type": "AGE", "value": {"min": 19, "max": 34}, "group": 1, "known": True, "rawText": "19~34세"},
        {"type": "AGE", "value": {"min": 35, "max": 39}, "group": 2, "known": True, "rawText": "35~39세"},
    ]
    assert _merge_ages(joined) is False
    assert [r["value"] for r in joined] == [{"min": 19, "max": 39}]


def test_a_looser_row_without_amount_does_not_wipe_the_amount():
    """금액 없는 넓은 줄(「전월세 임차보증금」)이 금액 있는 같은 type 줄과 다른 묶음에 있어도 금액을 잃지 않습니다(2026-10-26)."""
    from mujuthaek_extraction.benefit.build import _drop_looser_rows

    strict = {"type": "LEASE", "group": 5, "known": True, "value": {"kind": ["JEONSE", "MONTHLY"], "unit": "MANWON", "depositMax": 25000}}
    loose = {"type": "LEASE", "group": 6, "known": True, "value": {"kind": ["JEONSE", "MONTHLY"], "unit": "MANWON"}}
    rows = [strict, loose]
    _drop_looser_rows(rows)
    assert strict["known"] is True and strict["value"]["depositMax"] == 25000
    assert loose["known"] is False and loose["value"] is None
    # 넓기만 한 게 아니라 다른 조건(월세만)이면 그대로 둡니다(전형별 조건 규칙이 판단)
    monthly = {"type": "LEASE", "group": 7, "known": True, "value": {"kind": ["MONTHLY"], "unit": "MANWON"}}
    rows = [dict(strict), monthly]
    _drop_looser_rows(rows)
    assert monthly["known"] is True


@pytest.mark.parametrize(
    "conditions, supports",
    [
        # 같은 종류(핵심 아님)가 서로 다른 묶음에 다른 조건으로 나뉨 → 비워짐
        (
            [
                condition("LEASE", "전세보증금 2.5억원 이하 주거용 주택", group=5, leaseKinds=["JEONSE"], depositMaxWon=250_000_000),
                condition("LEASE", "전월세 임차보증금 대출이자 지원", group=6, leaseKinds=["MONTHLY"]),
            ],
            None,
        ),
        # 지원 금액이 원문 어디에도 없음 → 비워짐
        (
            [],
            [
                {
                    "kind": "DEPOSIT_LOAN",
                    "amountMaxWon": 70_000_000,
                    "amountPer": "ONCE",
                    "months": None,
                    "ratePct": None,
                    "rawText": "대출금 최대 7천만원",
                    "evidence": "대출금 최대 1억원(임차보증금의 90% 이내)의 최대 연 3.5% 이자지원",
                }
            ],
        ),
    ],
)
def test_any_value_emptied_by_any_rule_goes_to_review(conditions, supports):
    """공통 검사(2026-10-26): AI·출처가 준 값이 어떤 규칙으로든 비워지면 이유와 상관없이 확인 필요."""
    data = build_payload(payload(), BenefitReading(answer(conditions, supports), False, "recorded"), rules_for("youth", RECORD, TEXT), REGIONS)
    emptied = [c for c in data["conditions"] if c["origin"] == "AI" and not c["known"] and c["type"] == "LEASE"] or [
        s for s in data["supports"] if s["amountMax"] is None
    ]
    assert emptied, "시험 전제: 값이 비워져야 함"
    assert data["quality"]["needsReview"] is True and "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]


# ---- 원문과 어긋나는 값은 값을 두고 확인 필요 (2026-10-26 원문 대조, 공통 규칙) ----


def test_always_open_with_application_dates_needs_review():
    text = TEXT + "\n신청 기간: 2026. 11. 1. ~ 2026. 11. 30."
    data = build_payload(
        payload(text=text),
        BenefitReading(
            answer(
                schedule={
                    "applyStart": "2026-11-01",
                    "applyEnd": "2026-11-30",
                    "applyAlways": True,
                    "businessStart": None,
                    "businessEnd": None,
                    "rawText": None,
                }
            ),
            False,
            "recorded",
        ),
        rules_for("youth", RECORD, text),
        REGIONS,
    )
    assert data["schedule"]["applyAlways"] is True and data["schedule"]["applyStart"] == "2026-11-01"
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]
    assert "LOW_CONFIDENCE" not in built()["quality"]["reviewReasons"]  # 상시이고 기간이 없으면 그대로


@pytest.mark.parametrize("line", ["지원 대상: 1987년~2006년 출생자", "만 65세 이하(1959. 1. 1 이후 출생)인 자", "나이 제한 없음"])
def test_an_age_that_the_text_sets_by_birth_year_or_does_not_limit_needs_review(line):
    data = built_text(TEXT + "\n" + line, [])
    assert [c["value"] for c in data["conditions"] if c["type"] == "AGE"] == [{"min": 19, "max": 39}]  # 값은 그대로
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]


def test_amounts_for_different_tracks_in_one_or_group_need_review():
    text = TEXT + "\n(소득) 외벌이 가구 연소득 7천만원 이하, 맞벌이 가구 본인 연소득 5천만원 이하"
    data = built_text(
        text,
        [
            condition("INCOME_AMOUNT", "외벌이 가구 연소득 7천만원 이하", amountMaxWon=70_000_000, amountPer="YEAR", basis="HOUSEHOLD"),
            condition("INCOME_AMOUNT", "맞벌이 가구 본인 연소득 5천만원 이하", amountMaxWon=50_000_000, amountPer="YEAR", basis="PERSONAL"),
        ],
    )
    assert sorted(c["value"]["max"] for c in data["conditions"] if c["type"] == "INCOME_AMOUNT") == [5000, 7000]
    assert "LOW_CONFIDENCE" in data["quality"]["reviewReasons"]


def test_the_source_age_field_does_not_claim_international_age():
    age = next(c for c in youth_rules(RECORD, TEXT).conditions if c["type"] == "AGE")
    assert age["rawText"] == "19~39세"
