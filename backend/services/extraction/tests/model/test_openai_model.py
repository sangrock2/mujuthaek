"""OpenAI Responses 연결부. 가짜 HTTP 응답만 쓰며 네트워크·실제 키를 사용하지 않습니다."""

import dataclasses
import io
import json
import urllib.error

import pytest
from jsonschema import Draft202012Validator

from mujuthaek_extraction.model import ModelError, StopReason
from mujuthaek_extraction.model.openai_responses import OpenAIResponsesModel, read_api_key
from mujuthaek_extraction.model.pricing import Budget, BudgetedModel, cost_usd
from mujuthaek_extraction.model.strict_schema import DROPPED_KEYWORDS, drop_null_optionals, to_strict
from mujuthaek_extraction.rules.base import call_schema
from mujuthaek_extraction.rules.housing_notice import RULES
from tests.support.helpers import ai_part, example, source_for

FAKE_KEY = "test-key-not-real"


class FakeHTTP:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.requests, self.timeouts = payload, error, [], []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.payload).encode())


def walk(node):
    if isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for child in value.values():
                    yield from walk(child)
            else:
                yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


@pytest.mark.parametrize("call", RULES.calls, ids=lambda c: c.name)
def test_strict_schema_is_all_required_and_keeps_field_names(call):
    strict, optional = to_strict(call_schema(call.sections))
    Draft202012Validator.check_schema(strict)
    for node in walk(strict):
        assert not DROPPED_KEYWORDS.intersection(node)
        assert "oneOf" not in node and "allOf" not in node and "const" not in node
        if "properties" in node:
            assert set(node["required"]) == set(node["properties"]) and node["additionalProperties"] is False
    assert "unitRow" in optional
    text = json.dumps(strict)
    assert "$ref" not in text and "$defs" not in text  # 엄격 모드가 거부한 정의 참조를 모두 펼쳤는지
    assert '"description"' in json.dumps(strict, ensure_ascii=False)  # 필드 이름 description은 남아야 합니다


def test_strict_round_trip_accepts_example_after_null_fill_and_cleanup():
    sections = RULES.calls[0].sections
    part = ai_part(example("housing"), sections)
    strict, optional = to_strict(call_schema(sections))
    # strict 모드는 선택 칸도 모두 요구합니다: 모델은 선택 칸을 null로 보내고, drop_null_optionals가 다시 뺍니다
    filled = {
        **part,
        "quotes": [{**q, "unitRow": None} for q in part["quotes"]],
        "notice": {**part["notice"], "counts": [{**c, "allocationPoolId": None} for c in part["notice"]["counts"]]},
        "supplyGroups": [
            {
                **g,
                "exclusiveAreaRange": None,
                "counts": [{**c, "allocationPoolId": None} for c in g["counts"]],
                "prices": [{**p, "priceStage": None} for p in g["prices"]],
            }
            for g in part["supplyGroups"]
        ],
    }
    assert list(Draft202012Validator(strict).iter_errors(filled)) == []
    cleaned = drop_null_optionals(filled, optional)
    assert list(Draft202012Validator(call_schema(sections)).iter_errors(cleaned)) == []


def response_payload(text, status="completed", reason=None, refusal=False, usage=None):
    content = [{"type": "refusal", "refusal": "no"}] if refusal else [{"type": "output_text", "text": text}]
    return {
        "model": "gpt-6-luna",
        "status": status,
        "incomplete_details": {"reason": reason} if reason else None,
        "output": [{"type": "reasoning"}, {"type": "message", "content": content}],
        "usage": usage or {"input_tokens": 1000, "output_tokens": 200, "input_tokens_details": {"cached_tokens": 600, "cache_write_tokens": 0}},
    }


def request_for(call_index=0):
    material = source_for("housing", example("housing")).material
    return RULES.build_request(RULES.calls[call_index], material)


def test_request_body_order_and_no_secret_in_repr():
    http = FakeHTTP(response_payload('{"quotes": []}'))
    model = OpenAIResponsesModel(FAKE_KEY, opener=http)
    model.complete(request_for())
    body = json.loads(http.requests[0].data)
    texts = [c["text"] for c in body["input"][0]["content"]]
    assert texts[0].startswith("당신은") and "<<<원문 시작>>>" in texts[1] and texts[2].startswith("# 이번 호출에서 할 일")
    assert body["store"] is False and body["text"]["format"]["strict"] is True
    assert FAKE_KEY not in repr(model) and FAKE_KEY not in json.dumps(body)
    assert http.requests[0].get_header("Authorization") == "Bearer " + FAKE_KEY


def test_wait_limit_is_set_per_call():
    # 실측 GH 808: 응답이 사라진 호출을 모든 호출에 같은 900초로 기다려 공고 하나가 35분 걸렸음
    model = OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(response_payload('{"quotes": []}')))
    base = request_for()
    names = ("supply_tables", "schedules", "documents", "selection", "eligibility", "structure", "recheck", "image_text", "selection-quotes")
    waits = {name: model.timeout_for(dataclasses.replace(base, call_name=name)) for name in names}
    assert waits == {
        "supply_tables": 250,
        "schedules": 500,
        "documents": 600,
        "selection": 750,
        "eligibility": 900,
        "structure": 900,
        "recheck": 900,
        "image_text": 900,
        "selection-quotes": 750,
    }
    http = FakeHTTP(response_payload('{"quotes": []}'))
    OpenAIResponsesModel(FAKE_KEY, opener=http).complete(dataclasses.replace(base, call_name="selection"))
    assert http.timeouts == [750]
    assert OpenAIResponsesModel(FAKE_KEY, timeout_seconds=300).timeout_for(dataclasses.replace(base, call_name="selection")) == 300  # 상한을 넘지 않음


def test_parse_completed_removes_null_optionals_and_reads_usage():
    payload = response_payload(json.dumps({"quotes": [{"ref": "q1", "documentId": "text1", "text": "가나다라마", "unitRow": None}]}))
    response = OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(payload)).complete(request_for())
    assert response.stop_reason is StopReason.END
    assert json.loads(response.raw_text)["quotes"][0] == {"ref": "q1", "documentId": "text1", "text": "가나다라마"}
    assert (response.input_tokens, response.cached_input_tokens, response.output_tokens) == (1000, 600, 200)


@pytest.mark.parametrize(
    ("payload", "stop"),
    [
        (response_payload("{", status="incomplete", reason="max_output_tokens"), StopReason.MAX_TOKENS),
        (response_payload("", refusal=True), StopReason.REFUSED),
        (response_payload("", status="failed"), StopReason.OTHER),
    ],
)
def test_parse_stop_reasons(payload, stop):
    assert OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(payload)).complete(request_for()).stop_reason is stop


@pytest.mark.parametrize(("status", "transient"), [(429, True), (503, True), (400, False), (401, False)])
def test_http_errors_are_classified_without_body(status, transient):
    body = io.BytesIO(json.dumps({"error": {"code": "rate_limit_exceeded", "message": "echo " + FAKE_KEY}}).encode())
    error = urllib.error.HTTPError("https://api.openai.com/v1/responses", status, "x", {}, body)
    with pytest.raises(ModelError) as caught:
        OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(error=error)).complete(request_for())
    assert caught.value.transient is transient and FAKE_KEY not in str(caught.value)


def test_network_error_is_transient():
    with pytest.raises(ModelError) as caught:
        OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(error=urllib.error.URLError("down"))).complete(request_for())
    assert caught.value.transient


def test_read_api_key_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text('OTHER=1\nOPENAI_API_KEY="abc"\n', encoding="utf-8")
    assert read_api_key(env) == "abc"
    env.write_text("OTHER=1\n", encoding="utf-8")
    assert read_api_key(env) is None


def test_cost_and_budget_guard():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "input_tokens_details": {"cached_tokens": 500_000, "cache_write_tokens": 100_000}}
    payload = response_payload("{}", usage=usage)
    response = OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(payload)).complete(request_for())
    expected = (400_000 * 0.10 + 500_000 * 0.01 + 100_000 * 0.125 + 1_000_000 * 0.50) / 1_000_000
    assert cost_usd("gpt-6-luna", response) == pytest.approx(expected)

    budget = Budget("gpt-6-luna", limit_usd=0.05)
    request = request_for()
    assert budget.allow(request)
    BudgetedModel(OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(payload)), budget).complete(request)
    assert budget.spent_usd > 0.05 and not budget.allow(request)


def test_shared_schema_keeps_one_format_with_cache_breakpoint_and_light_effort():
    # 실측(OpenAI): 호출마다 출력 형식이 달라 원문 캐시 읽기가 9회 모두 0건(쓰기 요금만 냄). 같은 형식 + 원문 끝 캐시 지점
    http = FakeHTTP(response_payload(json.dumps({"quotes": [], "schedules": None, "notice": {"x": 1}, "coverage": {"notice": None, "schedules": None}})))
    model = OpenAIResponsesModel(FAKE_KEY, opener=http, shared_schema=True, light_calls=frozenset({"structure"}), light_effort="low")
    first, second = request_for(0), request_for(1)
    model.complete(first)
    response = model.complete(second)
    bodies = [json.loads(r.data) for r in http.requests]
    assert bodies[0]["text"]["format"] == bodies[1]["text"]["format"] and bodies[0]["text"]["format"]["name"] == "extraction_shared"
    assert all(b["prompt_cache_options"] == {"mode": "explicit"} for b in bodies)
    assert bodies[0]["prompt_cache_key"] == bodies[1]["prompt_cache_key"] and bodies[0]["prompt_cache_key"].startswith("notice-")
    assert all(b["input"][0]["content"][1]["prompt_cache_breakpoint"] == {"mode": "explicit"} for b in bodies)
    assert "prompt_cache_breakpoint" not in bodies[0]["input"][0]["content"][2]  # 호출별 지시는 캐시 뒤
    assert [b["reasoning"]["effort"] for b in bodies] == ["low" if first.call_name == "structure" else "medium", "medium"]
    kept = json.loads(response.raw_text)  # 맡지 않은 섹션(notice)과 그 coverage는 걸러 냄
    assert set(kept) <= set(second.output_schema["properties"]) and set(kept["coverage"]) <= set(second.output_schema["properties"]["coverage"]["properties"])


def test_shared_schema_off_keeps_per_call_format():
    http = FakeHTTP(response_payload('{"quotes": []}'))
    OpenAIResponsesModel(FAKE_KEY, opener=http).complete(request_for())
    body = json.loads(http.requests[0].data)
    assert body["text"]["format"]["name"] != "extraction_shared" and "prompt_cache_options" not in body


def test_shared_schema_null_section_with_coverage_becomes_empty_list():
    # 실측(OpenAI LH 제주 든든전세): 맡은 supplyGroups를 null로 두고 coverage에 PARTIAL 사유만 적어 구조 호출을 다시 요청함
    from mujuthaek_extraction.model.openai_responses import _keep_own

    schema = {
        "required": ["quotes", "supplyGroups", "coverage"],
        "properties": {"quotes": {"type": "array"}, "supplyGroups": {"type": "array"}, "coverage": {"properties": {"supplyGroups": {}}}},
    }
    kept = _keep_own({"quotes": [], "coverage": {"supplyGroups": {"status": "PARTIAL", "reason": "첨부 없음"}}}, schema)
    assert kept["supplyGroups"] == []
    assert "supplyGroups" not in _keep_own({"quotes": [], "coverage": {}}, schema)  # 사유도 없으면 그대로(다시 요청)


def test_shared_schema_keeps_required_nulls_of_the_call_own_schema():
    # 실측 2026-10-20: 공급표 열 의미 답의 필수 칸 priceStage: null이, 공유 형식에서 가격 항목의 선택 칸 이름과 같아 지워져
    # 답이 형식 위반으로 버려졌음(공급표를 코드가 옮기는 방식이 유료 실행에서 늘 꺼짐)
    from mujuthaek_extraction import supply_tables as st
    from mujuthaek_extraction.extract import schema_errors

    base = request_for()
    table = st.Table("3-1", 3, "", ("주택형", "임대보증금"), (("16A", "31,994,000"),), None)
    request = st.mapping_request(base, [table])
    assert request.shared_schema is not None  # 원문 캐시를 함께 쓰려고 공유 형식으로 보냄
    answer = {
        "tables": [
            {
                "table": "3-1",
                "role": "SUPPLY",
                "rowUnit": "HOUSING_TYPE",
                "complex": None,
                "columns": [
                    {
                        "column": 1,
                        "meaning": "HOUSING_TYPE",
                        "countKind": None,
                        "priceKind": None,
                        "unit": None,
                        "plan": None,
                        "priceStage": None,
                        "targetGroup": None,
                    },
                    {
                        "column": 2,
                        "meaning": "PRICE",
                        "countKind": None,
                        "priceKind": "DEPOSIT",
                        "unit": "원",
                        "plan": "기본",
                        "priceStage": "STANDARD",
                        "targetGroup": None,
                    },
                ],
            }
        ]
    }
    model = OpenAIResponsesModel(FAKE_KEY, opener=FakeHTTP(response_payload(json.dumps(answer, ensure_ascii=False))), shared_schema=True)
    mapping = json.loads(model.complete(request).raw_text)
    assert mapping["tables"][0]["columns"][0]["priceStage"] is None
    assert schema_errors(mapping, st.MAPPING_SCHEMA) is None


class FakeStream:
    """스트리밍 응답(server-sent events). 읽은 줄 수를 세어 도중에 멈췄는지 봅니다."""

    def __init__(self, events):
        self.lines = [f"data: {json.dumps(e, ensure_ascii=False)}\n".encode() for e in events]
        self.read = 0
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for line in self.lines:
            self.read += 1
            yield line


def deltas(text, size=500):
    return [{"type": "response.output_text.delta", "delta": text[i : i + size]} for i in range(0, len(text), size)]


def test_stream_reads_completed_response_and_sends_stream_flag():
    text = json.dumps({"quotes": []})
    events = [*deltas(text), {"type": "response.completed", "response": response_payload(text)}]
    http = FakeStream(events)
    model = OpenAIResponsesModel(FAKE_KEY, opener=http, stream=True, runaway_check=lambda raw, name: None)
    response = model.complete(request_for(0))
    assert response.stop_reason is StopReason.END and response.input_tokens == 1000
    assert json.loads(http.requests[0].data)["stream"] is True
    # 호출 캐시 열쇠는 받는 방식과 상관없이 같습니다
    plain = OpenAIResponsesModel(FAKE_KEY, opener=http)
    assert model.cache_identity(request_for(0)) == plain.cache_identity(request_for(0))


def test_stream_stops_reading_when_runaway_appears():
    # 실측 4차: 서류 호출이 같은 표 행을 되풀이해 3만 자 넘게 쓴 뒤에야 잘렸습니다. 받는 도중 보이면 바로 끊습니다
    from mujuthaek_extraction.model.runaway import runaway

    looping = '{"quotes":[{"id":"q1","text":"' + "가" * 30_000 + '"}]}'
    events = [*deltas(looping), {"type": "response.completed", "response": response_payload(looping)}]
    http = FakeStream(events)
    model = OpenAIResponsesModel(FAKE_KEY, opener=http, stream=True, runaway_check=runaway)
    response = model.complete(request_for(0))
    assert response.stop_reason is StopReason.RUNAWAY
    assert http.read < len(events) // 4  # 나머지는 읽지 않음
    assert response.usage["estimated"] is True and response.output_tokens < 4_000 and response.input_tokens > 0


def test_stream_aborted_call_reuses_cached_input_of_the_same_source():
    from mujuthaek_extraction.model.runaway import runaway

    usage = {"input_tokens": 70_000, "output_tokens": 10, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 69_000}}
    ok = FakeStream([{"type": "response.completed", "response": response_payload(json.dumps({"quotes": []}), usage=usage)}])
    model = OpenAIResponsesModel(FAKE_KEY, opener=ok, stream=True, shared_schema=True, runaway_check=runaway)
    model.complete(request_for(0))
    looping = '{"quotes":[{"id":"q1","text":"' + "가" * 30_000
    model._opener = FakeStream(deltas(looping))
    response = model.complete(request_for(1))
    assert response.stop_reason is StopReason.RUNAWAY
    assert (response.input_tokens, response.cached_input_tokens) == (70_000, 69_000)


def test_stream_failed_event_and_missing_end_are_transient_errors():
    failed = FakeStream([{"type": "response.failed", "response": {"error": {"code": "server_error", "message": "x"}}}])
    with pytest.raises(ModelError) as error:
        OpenAIResponsesModel(FAKE_KEY, opener=failed, stream=True).complete(request_for(0))
    assert error.value.transient and error.value.code == "STREAM_FAILED"
    cut = FakeStream(deltas('{"quotes":['))
    with pytest.raises(ModelError) as error:
        OpenAIResponsesModel(FAKE_KEY, opener=cut, stream=True).complete(request_for(0))
    assert error.value.transient and error.value.code == "INCOMPLETE_READ"


def test_stream_whole_call_wait_limit():
    ticks = iter(range(0, 10_000, 400))
    http = FakeStream(deltas("x" * 5_000))
    model = OpenAIResponsesModel(FAKE_KEY, opener=http, stream=True, clock=lambda: next(ticks))
    with pytest.raises(ModelError) as error:
        model.complete(request_for(0))
    assert error.value.code == "TIMEOUT"
