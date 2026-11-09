"""재확인 답 받기 전략: 어떤 전략이 답을 내도 채택은 같은 검증기(adopt)가 정합니다. 녹화 응답만 씁니다."""

import json

from helpers import to_ai
from test_recheck import answer, setup

from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.recheck import BATCH, RecheckAnswer, recheck_problems, select_targets
from mujuthaek_extraction.rules.housing_notice import RULES


class FixedAnswer:
    """정해 둔 답을 그대로 돌려주는 전략(모델을 부르지 않음)."""

    def __init__(self, response):
        self.response = response
        self.seen = None

    def answer(self, rules, material, model, parts, targets, sections, **run_options):
        self.seen = (targets, sections)
        return RecheckAnswer(self.response, None, targets, sections)


def test_targets_are_the_problem_items():
    data, source, parts, evaluate = setup()
    targets, sections = select_targets(parts, evaluate(parts))
    assert sections == ["eligibility"]
    assert [t["id"] for t in targets] == [data["eligibility"][1]["id"]]


def test_a_scope_limits_the_recheck_to_the_problems_of_those_sections():
    # V2: 담당 섹션은 담당이 검증 미들웨어로 스스로 고치므로 구조 단계 섹션(공고·위치·공급)의 문제만 다시 봄
    data, source, parts, evaluate = setup()
    assert select_targets(parts, evaluate(parts), ("notice", "locations", "supplyGroups")) == ([], [])
    skipped = FixedAnswer(_fixed_answer(data))
    result = recheck_problems(RULES, source.material, RecordedModel({}), parts, evaluate, strategy=skipped, scope=("supplyGroups",))
    assert skipped.seen is None and not result.rechecked and result.parts == parts
    asked = FixedAnswer(_fixed_answer(data))
    result = recheck_problems(RULES, source.material, RecordedModel({}), parts, evaluate, strategy=asked, scope=("eligibility",))
    assert asked.seen is not None and result.accepted


def test_worse_answer_from_any_strategy_is_not_adopted():
    data, source, parts, evaluate = setup()
    item = json.loads(json.dumps(parts[0]["eligibility"][1]))
    item["quoteRefs"] = ["nowhere"]  # 근거를 더 잃은 답
    strategy = FixedAnswer(json.loads(answer(item, [{"ref": "nowhere", "documentId": "text1", "text": "원문에 전혀 없는 문장"}])))
    result = recheck_problems(RULES, source.material, RecordedModel({}), parts, evaluate, strategy=strategy)
    assert strategy.seen is not None and not result.accepted
    assert result.parts == parts  # 처음 결과 그대로


def test_strategy_without_answer_keeps_first_result():
    class NoAnswer:
        def answer(self, rules, material, model, parts, targets, sections, **run_options):
            return RecheckAnswer(None, None, targets, sections, (("전체", "답 없음"),))

    data, source, parts, evaluate = setup()
    result = recheck_problems(RULES, source.material, RecordedModel({}), parts, evaluate, strategy=NoAnswer())
    assert not result.accepted and result.parts == parts and result.rejected == (("전체", "답 없음"),)


def test_batch_is_the_default_strategy():
    assert recheck_problems.__defaults__[0] is BATCH


def _fixed_answer(data):
    fixed = json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))
    return json.loads(answer(fixed, [{"ref": "q1", "documentId": "text1", "text": data["evidence"][0]["quote"]}]))


def test_an_item_that_disappears_counts_as_lost_values():
    from mujuthaek_extraction.recheck import _lost_values
    from mujuthaek_extraction.verify import VerificationReport

    def report(groups, eligibility=1):
        return VerificationReport(candidate={"supplyGroups": groups, "eligibility": [{}] * eligibility}, findings=[], contract_errors=[])

    group = {"id": "g1", "prices": [{}] * 16, "counts": [{}] * 3}
    assert _lost_values(report([group]), report([])) == ["supplyGroups/g1", "supplyGroups"]  # 묶음째 사라짐
    assert _lost_values(report([group]), report([group], eligibility=0)) == ["eligibility"]  # 자격 조건이 빠짐
    assert _lost_values(report([group]), report([group])) == []
