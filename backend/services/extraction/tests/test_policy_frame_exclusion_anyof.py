"""제외 사유끼리 묶은 anyOf: 「A 또는 B인 자 제외」는 A도 B도 아니어야 해서 ANY_OF(하나만 아니면 됨)로 만들지 않습니다.
실측 2026-10-26 관광기업지원센터(서울). 지어낸 공고 글(TOUR_TEXT)로만 시험합니다."""

from test_policy_frame_checks import frame_of
from test_policy_judgment import condition

QUOTE = "금융기관으로부터 채무불이행으로 규제 중인 자 또는 휴/폐업 중인 사업자"


def kinds(made):
    out = []

    def walk(criteria):
        for c in criteria:
            out.append(c["kind"])
            for option in c.get("options") or []:
                walk(option["criteria"])

    walk(made["common"])
    for group in made["groups"]:
        walk(group["criteria"])
    return out


def test_exclusions_joined_by_or_are_all_required_not_any_of():
    made = frame_of(
        [
            condition("EXCLUDED_STATUS", QUOTE, anyOf="x", option="1", excludedCodes=["CREDIT_DELINQUENT"]),
            condition("EXCLUDED_STATUS", QUOTE, anyOf="x", option="2", excludedCodes=["BUSINESS_SUSPENDED"]),
            condition("OTHER", QUOTE, anyOf="x", option="3", question="지금 폐업 상태인가요?", metWhen="NO"),
        ]
    )
    assert "ANY_OF" not in kinds(made)
    assert "EXCLUDED_STATUS" in kinds(made)


def test_real_alternatives_stay_any_of():
    made = frame_of(
        [
            condition(
                "BUSINESS_AGE",
                "공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자",
                anyOf="a",
                option="1",
                years=7,
                yearsRule="WITHIN",
            ),
            condition(
                "BUSINESS_AGE",
                "관광 관련 사업을 운영하는 창업 10년 이내 신산업창업분야* 법인사업자 또는 개인사업자",
                anyOf="a",
                option="2",
                years=10,
                yearsRule="WITHIN",
            ),
            condition("EXCLUDED_STATUS", QUOTE, anyOf="a", option="2", excludedCodes=["CREDIT_DELINQUENT"]),
        ]
    )
    assert "ANY_OF" in kinds(made)
