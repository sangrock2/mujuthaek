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
