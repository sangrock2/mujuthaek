"""판정 틀의 뜻 검사(judgment/sanity.py): 틀 읽기(FrameReader)가 틀 전체를 거절하는 거꾸로 된 범위·공백뿐인 글자.

AI 값 하나가 틀어져도 틀 전체가 버려지지 않게, 그 조건만 원문 질문(확인 필요)으로 바꾸고, 남은 것은 frame_errors가 잡습니다.
"""

import copy

from test_judgment import atom, candidate, item
from test_policy_judgment import REGIONS, answer, condition, reading, tour

from mujuthaek_extraction.judgment import build_judgment
from mujuthaek_extraction.judgment.frame import merge_age
from mujuthaek_extraction.judgment.policy_frame import space_frame, startup_frame
from mujuthaek_extraction.judgment.sanity import INVERTED, NO_BOUND, repair, semantic_errors
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.publish import policy_frame

AGE_QUOTE = "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자"


def startup(conditions, **fields):
    return startup_frame(tour() | {"field": "STARTUP_SUPPORT"}, reading(answer(conditions, **fields)), REGIONS)


def asked(frame):
    return [c for c in [*frame["common"], *(c for g in frame["groups"] for c in g["criteria"])] if c["kind"] == "ASK"]


def test_inverted_ai_ranges_become_review_questions_instead_of_inverted_criteria():
    cases = (
        condition("AGE", AGE_QUOTE, minAge=40, maxAge=19),
        condition("REVENUE", AGE_QUOTE, revenueYear=2025, revenueMinWon=500_000_000, revenueMaxWon=100_000_000),
        condition("BUSINESS_AGE", AGE_QUOTE, openedFrom="2026-10-07", openedTo="2019-10-07"),
        condition("NO_RECENT_CLOSURE", AGE_QUOTE, closedFrom="2026-10-07", closedTo="2023-10-07"),
        condition("CLOSURE_REQUIRED", AGE_QUOTE, closedFrom="2026-10-07", closedTo="2023-10-07"),
    )
    for made in cases:
        frame = startup([made])
        assert frame_errors(frame) == [], made["kind"]
        [question] = asked(frame)
        assert question["inReview"] and INVERTED in question["reviewReason"], made["kind"]
        assert not [c for c in frame["common"] if c["kind"] != "ASK"], made["kind"]  # 거꾸로 된 값은 내보내지 않음
    # 신청 제외(최근 폐업 없음)는 질문 방향도 「해당하면 안 됨」
    assert asked(startup([cases[3]]))[0]["metWhen"] == "NO"


def test_ordered_ranges_are_kept_as_criteria():
    frame = startup([condition("NO_RECENT_CLOSURE", "2023년 10월 7일부터 2026년 10월 7일까지 폐업", closedFrom="2023-10-07", closedTo="2026-10-07")])
    assert frame_errors(frame) == [] and [c["kind"] for c in frame["common"]] == ["CLOSURE"]


def test_one_inverted_ai_value_keeps_the_ai_frame_instead_of_dropping_it():
    """예전엔 거꾸로 된 나이 하나 때문에 AI 틀 전체가 틀 읽기에서 거절됐음. 이제 그 조건만 확인 필요 질문이고 나머지는 그대로."""
    made = answer([condition("AGE", AGE_QUOTE, minAge=40, maxAge=19), condition("REGISTERED", AGE_QUOTE)])
    frame = policy_frame(tour() | {"field": "STARTUP_SUPPORT"}, reading(made), REGIONS)
    assert frame["schema"] == "startup-support-judgment.v1" and frame_errors(frame) == []
    assert [c["kind"] for c in frame["common"]] == ["ASK", "BUSINESS_REGISTRATION"]


def test_blank_ai_strings_are_dropped_or_replaced():
    made = answer(
        [condition("STATUS", AGE_QUOTE, question="   ")],
        groups=[{"key": " ", "name": "  "}],
        notes=[{"kind": "OTHER", "group": None, "text": "  ", "quote": "  "}],
        preferences=[{"label": " ", "group": None, "effect": "PRIORITY", "points": None, "question": "  ", "quote": " "}],
    )
    for frame in (startup_frame(tour() | {"field": "STARTUP_SUPPORT"}, reading(made), REGIONS), space_frame(tour(), reading(made), REGIONS)):
        assert frame_errors(frame) == []
        assert all(g["name"].strip() for g in frame["groups"]) and frame["notes"] == []
        assert all(p["label"].strip() and p["criteria"][0]["question"].strip() for p in frame["preferences"])
        assert all(c["question"].strip() for c in asked(frame))


def test_housing_inverted_age_span_and_contradicting_ages_become_review_questions():
    flipped = item("age", "AGE", "만 19세 이상 39세 이하인 자", atom("AGE_YEARS", "BETWEEN", [39, 19], subject="APPLICANT", unit="YEAR"))
    older, younger = atom("AGE_YEARS", "GTE", 40, subject="APPLICANT", unit="YEAR"), atom("AGE_YEARS", "LTE", 39, subject="APPLICANT", unit="YEAR")
    both = {"kind": "ALL", "children": [older, younger]}
    clash = item("age", "AGE", "만 40세 이상, 만 39세 이하인 자", both)
    for made in (flipped, clash):
        frame = build_judgment(candidate([made]))
        assert frame is not None and frame_errors(frame) == []
        [criterion] = frame["common"]
        assert criterion["kind"] == "ASK" and criterion["inReview"] and INVERTED in criterion["reviewReason"]
    ages = [
        {"id": "a", "kind": "AGE", "quote": "q", "page": None, "inReview": False, "reviewReason": None, "minAge": 19, "maxAge": None},
        {"id": "b", "kind": "AGE", "quote": "q", "page": None, "inReview": False, "reviewReason": None, "minAge": None, "maxAge": 39},
    ]
    assert [(c["kind"], c.get("minAge"), c.get("maxAge")) for c in merge_age(copy.deepcopy(ages))] == [("AGE", 19, 39)]


def valid_startup():
    frame = startup([condition("AGE", "만 19세 이상 39세 이하", minAge=19, maxAge=39), condition("REGISTERED", AGE_QUOTE)])
    assert frame_errors(frame) == []
    return frame


def test_frame_errors_catches_what_the_frame_reader_rejects():
    """틀 읽기(FrameReader)의 뜻 규칙: 스키마는 통과해도 틀 전체가 거절되는 것들. 내보내기 전 마지막 안전망."""
    when = {"factor": "HOUSEHOLD_SIZE", "min": 3, "max": 1, "since": None, "countRule": None}
    dual = when | {"factor": "DUAL_INCOME", "min": 1, "max": None}
    cases = {
        "나이 거꾸로": lambda f: f["common"][0].update(minAge=40, maxAge=19),
        "나이 둘 다 비움": lambda f: f["common"][0].update(minAge=None, maxAge=None),
        "공백 이름": lambda f: f["groups"][0].update(name="  "),
        "공백 id": lambda f: f["common"][0].update(id=" "),
        "없는 대상군": lambda f: f["notes"].append({"kind": "OTHER", "groupId": "nope", "text": "안내", "quote": None, "page": None}),
        "공백 안내": lambda f: f["notes"].append({"kind": "OTHER", "groupId": None, "text": " ", "quote": None, "page": None}),
    }
    for name, mutate in cases.items():
        frame = valid_startup()
        mutate(frame)
        assert frame_errors(frame), name
    rules = [
        ({"kind": "REVENUE", "year": 2025, "minWon": 2, "maxWon": 1}, "minWon"),
        ({"kind": "BUSINESS_AGE", "openedFrom": "2026-01-02", "openedTo": "2026-01-01"}, "openedFrom"),
        ({"kind": "CLOSURE", "mode": "ANY", "closedFrom": "2026-01-02", "closedTo": "2026-01-01"}, "closedFrom"),
        (
            {"kind": "INCOME", "basis": "HOUSEHOLD", "standard": "MEDIAN_INCOME", "year": 2025, "percent": 100, "bonuses": [{"when": when, "addPercent": 1}]},
            "min",
        ),
        ({"kind": "ASSET", "basis": "HOUSEHOLD", "maxWon": 1, "overrides": [{"when": dual, "maxWon": 2}]}, "맞벌이"),
        ({"kind": "ASK", "question": " ", "metWhen": "YES"}, "question"),
        ({"kind": "SAVINGS", "minBalanceWon": 1, "depositAreaM2": 85}, "depositAreaM2"),
        ({"kind": "BUSINESS_REGISTRATION", "require": "REGISTERED", "closedWithinYears": 3}, "closedWithinYears"),
        ({"kind": "CHILDREN", "minCount": None, "youngestMaxAge": None}, "minCount"),
        ({"kind": "REGION", "basis": "RESIDENCE", "regionCodes": ["1100000000", "1100000000"]}, "regionCodes"),
        ({"kind": "ANY_OF", "options": [{"label": " ", "criteria": []}]}, "options"),
    ]
    for fields, word in rules:
        frame = {"schema": "x", "groups": [{"id": "g", "name": "전체", "criteria": [{"id": "c"} | fields]}], "notes": []}
        assert any(word in e for e in semantic_errors(frame)), fields["kind"]


def test_repair_turns_leftover_inverted_ranges_into_review_questions_and_passes_the_check():
    frame = valid_startup()
    frame["common"][0].update(minAge=40, maxAge=19)
    frame["groups"][0]["name"] = " "
    repaired = repair(frame)
    assert frame_errors(repaired) == []
    assert repaired["common"][0]["kind"] == "ASK" and INVERTED in repaired["common"][0]["reviewReason"]
    frame = valid_startup()
    frame["common"][0].update(minAge=None, maxAge=None)
    assert NO_BOUND in repair(frame)["common"][0]["reviewReason"]
