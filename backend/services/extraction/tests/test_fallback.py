"""운영 모델 정책: 로컬 AI 우선, 실패·결과 부족이면 gpt-6-luna. 녹화 응답만 씁니다."""

import json

from helpers import ai_part, every_call, example, source_for

from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.model.fallback import extract_with_fallback
from mujuthaek_extraction.rules.housing_notice import RULES


def good_script(data):
    return {call.name: [json.dumps(ai_part(data, call.sections), ensure_ascii=False)] for call in every_call(RULES)}


def material():
    return source_for("housing", example("housing")).material


def test_primary_good_result_is_used_without_fallback():
    data = example("housing")
    local, luna = RecordedModel(good_script(data), "local"), RecordedModel({}, "gpt-6-luna")
    result = extract_with_fallback(RULES, material(), local, luna)
    assert result.used == "primary" and luna.requests == []


def test_connection_failure_falls_back_per_call():
    data = example("housing")
    script = good_script(data)
    local = RecordedModel({**script, "schedules": [ModelError("connection refused", transient=False)]}, "local")
    luna = RecordedModel({"schedules": script["schedules"]}, "gpt-6-luna")
    result = extract_with_fallback(RULES, material(), local, luna)
    assert result.used == "primary" and [r.call_name for r in luna.requests] == ["schedules"]
    assert {a.model_id for a in result.run.attempts if a.model_id} == {"local", "gpt-6-luna"}


def test_low_quality_result_is_reextracted_by_fallback():
    data = example("housing")
    bad_part = ai_part(data, RULES.calls[0].sections)
    bad_part["quotes"] = [{**q, "documentId": "notice"} for q in bad_part["quotes"]]
    bad = json.dumps(bad_part, ensure_ascii=False)
    local = RecordedModel({**good_script(data), "structure": [bad, bad]}, "local")  # 재요청 후에도 규칙 위반
    luna = RecordedModel(good_script(data), "gpt-6-luna")
    result = extract_with_fallback(RULES, material(), local, luna)
    assert result.used == "fallback" and result.primary_run is not None
    assert {r.call_name for r in luna.requests} == {"structure", "schedules", "eligibility", "selection", "documents"}


def test_low_quality_result_is_not_rerun_when_every_call_already_used_fallback():
    data = example("housing")
    bad_part = ai_part(data, RULES.calls[0].sections)
    bad_part["quotes"] = [{**q, "documentId": "notice"} for q in bad_part["quotes"]]
    bad = json.dumps(bad_part, ensure_ascii=False)
    down = ModelError("connection refused", transient=False)
    local = RecordedModel({call.name: [down, down] for call in every_call(RULES)}, "local")
    luna = RecordedModel({**good_script(data), "structure": [bad, bad]}, "gpt-6-luna")
    result = extract_with_fallback(RULES, material(), local, luna)
    assert result.used == "fallback" and result.primary_run is None
    assert [r.call_name for r in luna.requests].count("structure") == 2  # 형식 재요청 1번뿐, 공고 전체 재추출 없음
