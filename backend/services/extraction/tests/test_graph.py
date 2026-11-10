"""추출 그래프: 상황별로 어느 길로 끝나는지와 분기를 확인합니다. 녹화 응답만 씁니다.

기존 순차 경로(_process)와 결과가 같음은 지우기 전 비교 시험(#2)으로 확인했습니다. 아래 기대값은 그때 두 경로가 같이 낸 값입니다.
녹화 모델에는 채팅 모델이 없어 V2 그래프(v2/graph.py)가 V1 방식 추출 전체로 돕니다(2026-11-10 V1 정해진 단계 그래프를 걷어낸 뒤에도 같은 값).
"""

import dataclasses
import json

import pytest
from helpers import example, to_ai
from test_pipeline import answers, raw_event, run

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels

FAKE_QUOTE = "원문에 없는 무주택 문장입니다"


def _broken_answers():
    """자격 조건 하나에 원문에 없는 인용을 섞어 검증 문제가 생기게 합니다(재확인이 불림)."""
    script = answers()
    part = json.loads(script["eligibility"][0])
    part["quotes"].append({"ref": "fake", "documentId": "text", "text": FAKE_QUOTE})
    part["eligibility"][1]["quoteRefs"].append("fake")
    script["eligibility"] = [json.dumps(part, ensure_ascii=False)]
    return script, part


def _recheck_answer(item, quotes):
    return json.dumps({"quotes": quotes, "eligibility": [item], "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}}}, ensure_ascii=False)


def _fixed_recheck():
    script, _ = _broken_answers()
    data = example("housing")
    fixed = json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))
    quote = {"ref": "q1", "documentId": "text", "text": data["evidence"][0]["quote"]}
    script["recheck"] = [_recheck_answer(fixed, [quote])]
    return script


def _unhelpful_recheck():
    script, part = _broken_answers()
    script["recheck"] = [_recheck_answer(part["eligibility"][1], part["quotes"])]
    return script


def _models(name):
    down = ModelError("로컬 AI 연결 실패", transient=False)
    if name == "clean":
        return NoticeModels(RecordedModel(answers(), "local"), None, names={"primary": "local"})
    if name == "fallback":
        local = RecordedModel({call: [down] for call in answers()}, "local")
        return NoticeModels(local, RecordedModel(answers(), "paid"), names={"primary": "local", "fallback": "paid"})
    if name == "all_down":
        return NoticeModels(RecordedModel({call: [down] for call in answers()}), None)
    if name == "recheck_accepted":
        return NoticeModels(RecordedModel(_fixed_recheck()), None)
    if name == "recheck_rejected":
        return NoticeModels(RecordedModel(_unhelpful_recheck()), None)
    return NoticeModels(RecordedModel({}), None)


# 상황 → (이벤트, 상태, 발행 검수 상태, 모델 호출 수, 수정 기록 첫 줄)
SCENARIOS = {
    "clean": (lambda: raw_event(), "COMPLETED", "AUTO_PASSED", 5, None),
    "fallback": (lambda: raw_event(), "COMPLETED", "AUTO_PASSED", 5, None),
    "all_down": (lambda: raw_event(), "FAILED", None, 1, None),
    "recheck_accepted": (lambda: raw_event(), "COMPLETED", "AUTO_PASSED", 6, "재확인 채택: eligibility/"),
    "recheck_rejected": (lambda: raw_event(), "PARTIAL", "PARTIALLY_PASSED", 6, "재확인 미채택: eligibility/"),
    "rejected": (lambda: raw_event(rawPostId="not-a-uuid"), "REJECTED", None, 0, None),
    "unsupported": (lambda: raw_event(field="BUSINESS_SPACE"), "UNSUPPORTED", None, 0, None),
    "waiting_source": (lambda: raw_event(textKey="text/virtual/1/v1.txt"), "WAITING_SOURCE", None, 0, None),
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_each_situation_ends_on_its_path(scenario):
    event, status, review_status, attempts, first_repair = SCENARIOS[scenario]
    outcome = run(event(), _models(scenario))
    assert outcome.status == status
    assert ((outcome.event or {}).get("payload") or {}).get("reviewStatus") == review_status
    assert len(outcome.attempts) == attempts
    if first_repair is None:
        assert outcome.repairs == []
    else:
        assert outcome.repairs[0].startswith(first_repair)
    assert outcome.usage["stages"]  # 단계 시간 기록이 그래프에서도 남음


def test_recheck_results_are_recorded():
    accepted = run(raw_event(), _models("recheck_accepted"))
    rejected = run(raw_event(), _models("recheck_rejected"))
    assert accepted.usage["recheck"]["accepted"] is True
    assert rejected.usage["recheck"]["accepted"] is False


def test_contract_errors_left_after_recheck_go_through_quarantine(monkeypatch):
    # 마무리(v2/graph.conclude)는 재확인 뒤에도 계약 오류가 남으면 계약 정리를 거쳐 게시합니다(V1 그래프의 quarantine 분기와 같음)
    recheck_step, seen = pipeline.recheck_step, []

    def broken_recheck(*args, **kwargs):
        result, repairs = recheck_step(*args, **kwargs)
        result.report = dataclasses.replace(result.report, contract_errors=["/eligibility/0 오류"])
        return result, repairs

    def quarantine_step(report, recheck, material, context, rt):
        seen.append(report.contract_errors)
        return dataclasses.replace(report, contract_errors=[]), ["계약 정리: /eligibility/0"]

    monkeypatch.setattr(pipeline, "recheck_step", broken_recheck)
    monkeypatch.setattr(pipeline, "quarantine_step", quarantine_step)
    outcome = run(raw_event(), _models("clean"))
    assert seen == [["/eligibility/0 오류"]] and "계약 정리: /eligibility/0" in outcome.repairs
