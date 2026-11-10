"""V9 비교 방향 대조: 자격 조건의 연산자(LT·LTE·GT·GTE·BETWEEN)가 인용문의 방향 말(이상·이하·미만·초과 등)과 맞는지."""

from datetime import UTC, datetime

from helpers import ai_part, example, source_for

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.verify import SourceBundle, verify_extraction
from mujuthaek_extraction.verify.directions import check_directions


def atom(attribute, operator, value, unit):
    return {"kind": "ATOMIC", "subject": "APPLICANT", "attribute": attribute, "operator": operator, "value": value, "unit": unit, "evidenceIds": ["q1"]}


def candidate(quote, *expressions, exceptions=()):
    expression = expressions[0] if len(expressions) == 1 else {"kind": "ALL", "children": list(expressions)}
    item = {"rule": {"status": "STRUCTURED", "expression": expression, "reason": None}, "exceptions": list(exceptions), "evidenceIds": ["q1"]}
    return {"evidence": [{"id": "q1", "quote": quote}], "eligibility": [item]}


def found(c):
    return [(f.code, f.target) for f in check_directions(c)]


MISMATCH = [("OPERATOR_MISMATCH", "/eligibility/0")]


def test_age_flipped_from_gte_to_lte_is_flagged():
    assert found(candidate("신청자는 만 19세 이상이어야 합니다.", atom("AGE_YEARS", "LTE", 19, "YEAR"))) == MISMATCH
    assert found(candidate("신청자는 만 19세 이상이어야 합니다.", atom("AGE_YEARS", "GTE", 19, "YEAR"))) == []


def test_range_pairs_each_number_with_its_own_word():
    quote = "나이는 만 19세 이상 39세 이하인 무주택자"
    correct = (atom("AGE_YEARS", "GTE", 19, "YEAR"), atom("AGE_YEARS", "LTE", 39, "YEAR"))
    assert found(candidate(quote, *correct)) == []
    assert found(candidate(quote, atom("AGE_YEARS", "BETWEEN", [19, 39], "YEAR"))) == []
    assert found(candidate(quote, atom("AGE_YEARS", "GTE", 19, "YEAR"), atom("AGE_YEARS", "GTE", 39, "YEAR"))) == MISMATCH
    assert found(candidate("나이는 만 19세 이하 39세 이상", atom("AGE_YEARS", "BETWEEN", [19, 39], "YEAR"))) == MISMATCH


def test_one_matching_occurrence_is_enough():
    # 같은 수가 다른 곳에서 반대 말과 함께 나와도, 맞는 곳이 하나 있으면 넘어갑니다
    quote = "만 19세 미만 자녀가 있는 세대. 신청자는 만 19세 이상"
    assert found(candidate(quote, atom("AGE_YEARS", "GTE", 19, "YEAR"))) == []


def test_number_without_direction_word_is_not_judged():
    quote = "| 1인 | 70% | 3,500,000 |"
    assert found(candidate(quote, atom("INCOME_BENCHMARK_PERCENT", "GTE", 70, "PERCENT"))) == []
    assert found(candidate("나이 19~39세", atom("AGE_YEARS", "BETWEEN", [39, 19], "YEAR"))) == []


def test_strictness_differs_below_and_lte():
    assert found(candidate("만 39세 미만인 자", atom("AGE_YEARS", "LTE", 39, "YEAR"))) == MISMATCH
    assert found(candidate("만 39세 미만인 자", atom("AGE_YEARS", "LT", 39, "YEAR"))) == []


def test_within_and_until_mean_lte():
    assert found(candidate("소득 70% 이내", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"))) == []
    assert found(candidate("소득 70% 이내", atom("INCOME_BENCHMARK_PERCENT", "GTE", 70, "PERCENT"))) == MISMATCH
    assert found(candidate("만 39세까지 신청", atom("AGE_YEARS", "LTE", 39, "YEAR"))) == []


def test_amount_month_and_count_forms_are_read():
    assert found(candidate("총자산 4억 5천만원 초과 시 탈락 대상", atom("ASSETS", "LTE", 450_000_000, "KRW"))) == []  # 뒤에 탈락: 판단 안 함
    assert found(candidate("총자산 34,500만원 이하", atom("ASSETS", "GTE", 345_000_000, "KRW"))) == MISMATCH
    assert found(candidate("총자산 (단위: 천원) 345,000 이하", atom("ASSETS", "GT", 345_000_000, "KRW"))) == MISMATCH
    assert found(candidate("거주 기간 2년 이상", atom("RESIDENCE_MONTHS", "GTE", 24, "MONTH"))) == []
    assert found(candidate("거주 기간 2년 이상", atom("RESIDENCE_MONTHS", "LT", 24, "MONTH"))) == MISMATCH
    assert found(candidate("자녀 2명 이상", atom("CHILD_COUNT", "LTE", 2, "COUNT"))) == MISMATCH
    assert found(candidate("소득이 70%를 넘으면 신청 불가", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"))) == []  # 부정 뒤: 판단 안 함
    assert found(candidate("소득이 70%를 넘는 세대", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"))) == MISMATCH


def test_negated_or_excluded_direction_is_not_judged():
    assert found(candidate("만 19세 미만은 신청할 수 없습니다", atom("AGE_YEARS", "GTE", 19, "YEAR"))) == []
    assert found(candidate("소득 70%를 초과하지 않는 세대", atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"))) == []


def test_equality_and_not_are_ignored():
    assert found(candidate("자녀 2명 이상", atom("CHILD_COUNT", "EQ", 2, "COUNT"))) == []
    negated = {"kind": "NOT", "child": atom("AGE_YEARS", "LT", 19, "YEAR")}
    assert found(candidate("만 19세 이상", negated)) == []


def test_exception_conditions_are_checked_and_point_to_the_item():
    exception = {
        "when": {"status": "STRUCTURED", "expression": atom("CHILD_COUNT", "LTE", 2, "COUNT"), "reason": None},
        "effectExpression": atom("INCOME_BENCHMARK_PERCENT", "LTE", 90, "PERCENT"),
        "evidenceIds": ["q1"],
    }
    quote = "소득 70% 이하. 다만 자녀 2명 이상은 90% 이하로 대체합니다."
    assert found(candidate(quote, atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"), exceptions=[exception])) == MISMATCH
    exception["when"]["expression"]["operator"] = "GTE"
    assert found(candidate(quote, atom("INCOME_BENCHMARK_PERCENT", "LTE", 70, "PERCENT"), exceptions=[exception])) == []


def test_flipped_age_condition_no_longer_passes_end_to_end():
    data = example("housing")
    source = source_for("housing", data)
    sources = SourceBundle.from_material(source.material)

    def verify(part):
        result = assemble([part], source)
        assert result.contract_errors == []
        return verify_extraction(result.candidate, sources, None, clock=lambda: datetime(2026, 10, 20, tzinfo=UTC))

    assert verify(ai_part(data)).passed  # 원래 예시(만 19세 이상 = GTE 19)는 그대로 통과

    part = ai_part(data)
    age = part["eligibility"][0]["rule"]["expression"]["children"][0]
    assert (age["attribute"], age["operator"], age["value"]) == ("AGE_YEARS", "GTE", 19)
    age["operator"] = "LTE"
    report = verify(part)
    issues = [(i["code"], i["target"]) for i in report.candidate["quality"]["reviewIssues"]]
    assert not report.passed
    assert issues == [("OPERATOR_MISMATCH", "/eligibility/0")]
    assert report.verification["sourceStatus"] == "REVIEW_REQUIRED"
    assert [h["target"] for h in report.candidate["quality"].get("heldItems", [])] == ["/eligibility/0"]
