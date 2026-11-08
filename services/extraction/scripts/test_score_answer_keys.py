"""채점 스크립트 시험: 정답표가 대상 이름에만 적은 나이, 원문 확인 목록."""

import json

import pytest
import score_answer_keys as sk

KEY = {
    "eligibility": [
        {"criterion": "INCOME_PERCENT", "targetGroup": "사목 65세 이상 직계존속 부양자 중 생계·의료급여 수급자 선정 소득인정액 이하인 사람", "value": 100},
        {"criterion": "INCOME_PERCENT", "targetGroup": "자목 65세 이상 수급권자 또는 차상위계층", "value": 100},
    ]
}


def _age(subject, target, operator="GTE", value=65):
    return {"criterion": "AGE", "subject": subject, "operator": operator, "value": value, "targetGroup": target}


@pytest.mark.parametrize(
    ("rule", "same"),
    [
        (_age("PARENTS", "65세 이상의 직계존속 부양자"), True),
        (_age("APPLICANT", "65세 이상인 수급권자 또는 차상위계층"), True),
        (_age("APPLICANT", "65세 이상의 직계존속 부양자"), False),  # 이름 속 나이는 직계존속의 나이
        (_age("APPLICANT", "65세 이상인 수급권자 또는 차상위계층", operator="LTE"), False),
        (_age("APPLICANT", "65세 이상인 수급권자 또는 차상위계층", value=60), False),
        (_age("APPLICANT", "청년"), False),
        (_age("APPLICANT", None), False),
    ],
)
def test_age_written_only_in_key_group_name(rule, same):
    assert sk._age_in_group_name(KEY, rule) is same


def test_verified_list_moves_only_exact_labels(tmp_path):
    entry = {"notice": "n1", "section": "자동 게시: 가격", "label": "A단지 MONTHLY_RENT 83,060", "source": "| 36 | 83,060 |", "reason": "감면 월세"}
    path = tmp_path / "verified.json"
    path.write_text(json.dumps({"values": [entry]}, ensure_ascii=False), encoding="utf-8")
    verified = sk._load_verified(path)["n1"]

    score = sk.Score()
    score.check("자동 게시: 가격", False, "A단지 MONTHLY_RENT 83,060")
    score.check("자동 게시: 가격", False, "B단지 MONTHLY_RENT 83,060")  # 단지가 바뀌면 다시 후보
    score.verify("자동 게시: 가격", verified["자동 게시: 가격"])

    assert score.found["자동 게시: 가격"] == 1
    assert score.verified["자동 게시: 가격"] == 1
    assert score.misses["자동 게시: 가격"] == ["B단지 MONTHLY_RENT 83,060"]


def test_verified_entry_needs_source_and_reason(tmp_path):
    path = tmp_path / "verified.json"
    path.write_text(json.dumps({"values": [{"notice": "n1", "section": "s", "label": "l"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        sk._load_verified(path)


def test_zero_or_less_is_the_same_criterion_as_zero():
    # 2026-11-09 유료 확인 gh-809: 대학생 「자동차를 소유하고 있지 않을 것」 — 정답표 EQ 0, 추출 LTE 0(속성 사전에 EQ 없음)
    key = {"criterion": "CAR_ASSETS", "operator": "EQ", "value": 0, "targetGroup": "대학생"}
    extracted = {"criterion": "CAR_ASSETS", "operator": "LTE", "value": 0, "targetGroup": "대학생"}
    assert sk._eligibility_fit(key, extracted) is not None
    assert sk._eligibility_fit(key, extracted | {"value": 1}) is None  # 0이 아니면 방향이 다른 기준
    assert sk._eligibility_fit(key | {"value": 45_420_000}, extracted | {"value": 45_420_000}) is None
    assert sk._eligibility_fit(key, extracted | {"operator": "GTE"}) is None


@pytest.mark.parametrize(
    ("extracted", "same"),
    [
        ("소득신고 사실이 없음을 확인하는 사실증명서", True),
        ("’24년도에 소득 신고한 사실이 없음을 확인하는 사실 증명서", True),  # 연도·띄어 쓴 「사실 증명서」
        ("소득금액증명원", False),
        ("소득신고 사실이 있음을 확인하는 사실증명서", False),  # 있음은 다른 증명
    ],
)
def test_spelled_out_certificate_name_is_the_same_document(extracted, same):
    # 2026-11-09 23건 서류 놓침 3개(sh-310976·gndc 2건): 추출은 원문 이름 그대로, 정답표는 줄인 이름
    score = sk.compare({"documents": [{"name": "소득신고 사실 없음 사실증명서"}]}, {"documents": [{"name": extracted}]})
    assert (score.found["서류"] == 1) is same


def _candidate(counts, targets, eligibility=(), evidence=()):
    return {
        "notice": {"title": "공고", "announcedOn": None, "targetGroups": targets, "counts": counts},
        "locations": [],
        "supplyGroups": [],
        "schedules": [],
        "eligibility": list(eligibility),
        "selectionRules": [],
        "requiredDocuments": [],
        "guidance": [],
        "evidence": list(evidence),
    }


def _count(kind, value, groups=()):
    return {"kind": kind, "value": value, "scope": {"targetGroups": list(groups)}}


def test_total_offered_counts_new_reserves_and_counts_covering_every_target():
    # 2026-11-09 gndc 2건: 「모집인원 17명(우선 입주자 2명, 예비 입주자 15명)」 — 정답표 정책: 즉시 입주와 함께 뽑는 예비인원을 합친 수
    assert sk.neutral_from_candidate(_candidate([_count("OFFERED", 2), _count("RESERVE", 15)], []), "n")["totalOffered"] == 17
    assert sk.neutral_from_candidate(_candidate([_count("OFFERED", 280), _count("WAITLIST", 197)], []), "n")["totalOffered"] == 280  # 기존 대기자는 빼고
    # umca-4439: 대상이 「청년」뿐인 공고의 「청년 50명」은 공고 전체 수
    assert sk.neutral_from_candidate(_candidate([_count("OFFERED", 50, ["청년"])], ["청년"]), "n")["totalOffered"] == 50
    assert sk.neutral_from_candidate(_candidate([_count("OFFERED", 30, ["청년"])], ["청년", "고령자"]), "n")["totalOffered"] is None


@pytest.mark.parametrize(
    ("key_group", "extracted_group", "same"),
    [
        ("바목 등록장애인(해당 중증장애인의 배우자 포함)", "장애인등록증이 교부된 자", True),  # 계층 낱말이 다른 말에 붙음(bmc-72)
        ("바목 등록장애인", "장애인 신혼부부", False),  # 추출에 정답표에 없는 계층
        ("연령 자격으로 신청", "① 19세 이상 39세 이하인 사람", True),  # 추출이 조건을 이름으로 적음(gbdc-a909) → 확인 못 함
        ("청년", "65세 이상 고령자", False),  # 조건을 적었어도 다른 계층 이름이 있으면 다른 뜻
        ("생애최초 특별공급 / 추첨공급 / 외벌이", "신혼부부", False),  # 「생애최초」도 계층 이름
    ],
)
def test_target_group_names(key_group, extracted_group, same):
    key = {"criterion": "AGE", "operator": "BETWEEN", "value": [19, 39], "targetGroup": key_group}
    extracted = {"criterion": "AGE", "operator": "BETWEEN", "value": [19, 39], "targetGroup": extracted_group}
    assert (sk._eligibility_fit(key, extracted) is not None) is same


def test_income_amount_in_key_matches_percent_criterion_quoting_that_amount():
    # 2026-11-09 sh-311005: 정답표는 가구원수별 금액, 추출은 「120% 이하」와 금액 표 줄을 근거로 인용
    key = {"eligibility": [{"criterion": "INCOME_KRW", "operator": "LTE", "value": 4_576_000, "targetGroup": "1인 가구"}]}
    item = {
        "scope": {"targetGroups": []},
        "originalText": "도시 근로자 가구원수별 가구당 월평균 소득의 120% 이하에 해당하는 자",
        "category": "INCOME",
        "rule": {"expression": {"kind": "ATOMIC", "attribute": "INCOME_BENCHMARK_PERCENT", "operator": "LTE", "value": 120}},
        "evidenceIds": ["ev-1"],
    }
    quoted = sk.neutral_from_candidate(_candidate([], [], [item], [{"id": "ev-1", "quote": "| 4,576,000원이하 | 7,039,000원이하 |"}]), "n")
    assert sk.compare(key, quoted).found["자격: INCOME_KRW"] == 1
    unquoted = sk.neutral_from_candidate(_candidate([], [], [item], [{"id": "ev-1", "quote": "| 4,000,000원이하 |"}]), "n")
    assert sk.compare(key, unquoted).found["자격: INCOME_KRW"] == 0  # 그 금액이 근거에 없으면 다른 기준


def test_certificate_and_confirmation_endings_are_the_same_document():
    score = sk.compare({"documents": [{"name": "차상위계층 증명서"}]}, {"documents": [{"name": "차상위계층 확인서"}]})
    assert score.found["서류"] == 1


def test_child_age_rows_of_the_key_match_the_youngest_child_age_attribute():
    # 2026-11-09 새 속성: 정답표는 「6세 이하 자녀를 둔 한부모가족」을 AGE ≤ 6으로 적음(신청자 나이일 수 없는 상한)
    key = sk._child_age_rows(
        {
            "eligibility": [
                {"criterion": "AGE", "operator": "LTE", "value": 6, "targetGroup": "한부모가족", "text": "6세 이하 자녀를 둔 한부모가족"},
                {"criterion": "AGE", "operator": "BETWEEN", "value": [19, 39], "targetGroup": "청년", "text": "19세 이상 39세 이하"},
            ]
        }
    )
    assert [e["criterion"] for e in key["eligibility"]] == ["CHILD_AGE", "AGE"]
    item = {
        "scope": {"targetGroups": ["한부모가족"]},
        "originalText": "6세 이하 자녀를 둔 한부모가족",
        "category": "CHILDREN",
        "rule": {"expression": {"kind": "ATOMIC", "attribute": "YOUNGEST_CHILD_AGE_YEARS", "operator": "LTE", "value": 6}},
        "evidenceIds": [],
    }
    score = sk.compare(key, sk.neutral_from_candidate(_candidate([], [], [item]), "n"))
    assert (score.found["자격: CHILD_AGE"], score.total["자격: CHILD_AGE"]) == (1, 1)
