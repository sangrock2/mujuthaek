"""항목이 쓴 인용 ref가 quotes에 없을 때 빠진 인용문만 한 번 더 묻는 호출(<호출>-quotes). 녹화 응답만 씁니다(네트워크 없음)."""

import json

import pytest
from helpers import ai_part, every_call, example, source_for

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.extract import missing_quote_refs, run_extraction
from mujuthaek_extraction.model import ModelResponse, RecordedModel, StopReason
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel
from mujuthaek_extraction.rules.housing_notice import RULES

SCHEDULE_SECTIONS = ("schedules", "guidance")


def good_script(data):
    return {call.name: [json.dumps(ai_part(data, call.sections), ensure_ascii=False)] for call in every_call(RULES)}


def schedules_missing(data, count=3):
    """일정 응답의 앞 항목 몇 개가 새 ref(q26~)를 쓰고 그 인용문은 quotes에 없는 모양(실측 0815). (응답, 빠진 인용문)"""
    part = ai_part(data, SCHEDULE_SECTIONS)
    quotes = {q["ref"]: q for q in part["quotes"]}
    items = [*part["schedules"], *part["guidance"]]
    first = [item["quoteRefs"][0] for item in items]
    fresh: list[list[str]] = [[] for _ in items]
    lost = []
    for k in range(count):  # 항목을 돌아가며 새 ref를 붙입니다(한 항목이 여러 ref를 쓸 수 있음)
        ref = f"q{26 + k}"
        lost.append({**quotes[first[k % len(items)]], "ref": ref})
        fresh[k % len(items)].append(ref)
    for item, refs in zip(items, fresh, strict=True):
        if refs:
            item["quoteRefs"] = [*refs, *item["quoteRefs"][1:]]
    return part, lost


def run(script, parallel=1, model=None):
    data = example("housing")
    source = source_for("housing", data)
    model = model or RecordedModel(script)
    result = run_extraction(RULES, source.material, model, parallel=parallel, sleep=lambda seconds: None)
    return source, model, result


def codes(result, source):
    return [issue["code"] for issue in assemble(result.parts, source).issues]


@pytest.mark.parametrize("parallel", [1, 4])
def test_missing_quotes_are_asked_once_and_items_are_kept(parallel):
    data = example("housing")
    broken, lost = schedules_missing(data)
    assert sorted(missing_quote_refs(broken)) == ["q26", "q27", "q28"]
    script = good_script(data) | {"schedules": [json.dumps(broken, ensure_ascii=False)], "schedules-quotes": [json.dumps({"quotes": lost}, ensure_ascii=False)]}
    source, model, result = run(script, parallel)

    follow = [r for r in model.requests if r.call_name == "schedules-quotes"]
    assert len(follow) == 1
    schedules = next(r for r in model.requests if r.call_name == "schedules")
    assert (follow[0].system, follow[0].user) == (schedules.system, schedules.user)  # 같은 앞부분(입력 캐시)
    assert "빠진 ref: q26, q28, q27" in follow[0].instructions and follow[0].max_output_tokens <= 8_000
    assert follow[0].output_schema["required"] == ["quotes"] and list(follow[0].output_schema["properties"]) == ["quotes"]
    assert [a.call_name for a in result.attempts].count("schedules-quotes") == 1
    assert ("schedules-quotes", json.dumps({"quotes": lost}, ensure_ascii=False)) in result.raw_responses

    assert "QUOTE_REF_UNKNOWN" not in codes(result, source)
    baseline = run(good_script(data))[2]
    fixed, expected = assemble(result.parts, source).candidate, assemble(baseline.parts, source).candidate
    assert fixed["schedules"] == expected["schedules"] and fixed["guidance"] == expected["guidance"]


@pytest.mark.parametrize(
    "answer",
    [
        "{깨진 JSON",
        json.dumps({"quotes": [{"ref": "q99", "documentId": "text1", "text": "다른 ref"}]}),
        json.dumps({"quotes": [{"ref": "q26", "documentId": "지어낸 문서", "text": "형식 틀림"}]}),
        ModelResponse('{"quotes": [', "m", StopReason.MAX_TOKENS),
    ],
)
def test_failed_follow_up_behaves_like_before(answer):
    data = example("housing")
    broken, _ = schedules_missing(data)
    before_script = good_script(data) | {"schedules": [json.dumps(broken, ensure_ascii=False)], "schedules-quotes": [answer]}
    source, model, result = run(before_script)
    assert [r.call_name for r in model.requests].count("schedules-quotes") == 1  # 한 번만 묻고 다시 묻지 않음
    assert result.failed_calls == []
    assert codes(result, source).count("QUOTE_REF_UNKNOWN") >= 3  # 이전처럼 결합기가 표시
    schedule_part = next(p for p in result.parts if "schedules" in p)
    assert {q["ref"] for q in schedule_part["quotes"]}.isdisjoint({"q26", "q27", "q28"})


def test_partial_follow_up_keeps_what_it_got():
    data = example("housing")
    broken, lost = schedules_missing(data)
    script = good_script(data) | {
        "schedules": [json.dumps(broken, ensure_ascii=False)],
        "schedules-quotes": [json.dumps({"quotes": lost[:1]}, ensure_ascii=False)],
    }
    _, _, result = run(script)
    schedule_part = next(p for p in result.parts if "schedules" in p)
    assert sorted(missing_quote_refs(schedule_part)) == ["q27", "q28"]


def test_no_missing_refs_means_no_extra_call():
    _, model, result = run(good_script(example("housing")), parallel=4)
    assert not any(r.call_name.endswith("-quotes") for r in model.requests)
    assert not any(a.call_name.endswith("-quotes") for a in result.attempts)


def test_budget_can_block_the_follow_up():
    data = example("housing")
    broken, lost = schedules_missing(data)
    script = good_script(data) | {"schedules": [json.dumps(broken, ensure_ascii=False)], "schedules-quotes": [json.dumps({"quotes": lost})]}
    source = source_for("housing", data)
    model = RecordedModel(script)
    blocked = lambda request: not request.call_name.endswith("-quotes")  # noqa: E731
    result = run_extraction(RULES, source.material, model, budget=blocked, sleep=lambda seconds: None)
    assert not any(r.call_name == "schedules-quotes" for r in model.requests)
    assert "QUOTE_REF_UNKNOWN" in codes(result, source)


def test_shared_schema_request_tells_the_model_to_fill_only_quotes():
    data = example("housing")
    broken, lost = schedules_missing(data)
    script = good_script(data) | {"schedules": [json.dumps(broken, ensure_ascii=False)], "schedules-quotes": [json.dumps({"quotes": lost})]}
    _, model, _ = run(script)
    follow = next(r for r in model.requests if r.call_name == "schedules-quotes")
    schedules = next(r for r in model.requests if r.call_name == "schedules")
    adapter = OpenAIResponsesModel("test-key", shared_schema=True)
    body, base = adapter.body(follow), adapter.body(schedules)
    assert "이번 호출은 quotes만 채웁니다" in body["input"][0]["content"][2]["text"]
    # 같은 공유 형식·원문·캐시 열쇠라 앞 호출이 쓴 입력 캐시를 읽습니다
    assert body["text"] == base["text"] and body["prompt_cache_key"] == base["prompt_cache_key"]
    assert body["input"][0]["content"][:2] == base["input"][0]["content"][:2]
