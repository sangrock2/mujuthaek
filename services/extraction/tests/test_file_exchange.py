"""파일 교환 모델(대역)과 평가용 파일 호출 캐시. 유료 호출 없음."""

import json
import threading
from pathlib import Path

import pytest

from mujuthaek_extraction.model import ModelRequest
from mujuthaek_extraction.model.base import ModelError, ModelImage, ToolCall, ToolSpec, ToolTurn
from mujuthaek_extraction.model.call_cache import FileCallCache
from mujuthaek_extraction.model.file_exchange import FileExchangeModel

SEARCH = ToolSpec(
    "search_source", "찾기", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}
)


def request(**extra):
    base = dict(
        prompt_version="v",
        call_name="agentic:schedules:turn2",
        system="공통",
        user="원문",
        instructions="지시",
        output_schema={"type": "object"},
        max_output_tokens=10,
    )
    return ModelRequest(**{**base, **extra})


def answer_when_asked(folder, answer):
    """대역 흉내: 요청 파일이 생기면 그 answerPath에 답을 씁니다."""

    def run():
        while True:
            pending = list(folder.glob("*.request.json"))
            if pending:
                body = json.loads(pending[0].read_text(encoding="utf-8"))
                (folder / "seen.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
                Path(body["answerPath"]).write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
                return

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_tool_request_is_written_with_tools_turns_and_images_and_the_answer_becomes_tool_calls(tmp_path):
    thread = answer_when_asked(tmp_path, {"tool_calls": [{"name": "search_source", "arguments": {"query": "접수"}}]})
    turns = (ToolTurn((ToolCall("c1", "search_source", '{"query": "무주택"}'),), ('{"total": 1}',), "다시 맡김"),)
    image = ModelImage("그림 1", "image/png", b"png")
    response = FileExchangeModel(tmp_path, poll_seconds=0.01).complete(request(tools=(SEARCH,), turns=turns, forced_tool="search_source", images=(image,)))
    thread.join()
    seen = json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))
    assert seen["toolChoice"] == "search_source" and seen["turns"][0]["note"] == "다시 맡김" and seen["tools"][0]["name"] == "search_source"
    assert open(seen["images"][0], "rb").read() == b"png"
    assert [(c.name, json.loads(c.arguments)) for c in response.tool_calls] == [("search_source", {"query": "접수"})]


def test_plain_request_answer_is_the_json_text(tmp_path):
    thread = answer_when_asked(tmp_path, {"text": '{"quotes": []}'})
    response = FileExchangeModel(tmp_path, poll_seconds=0.01).complete(request())
    thread.join()
    assert response.raw_text == '{"quotes": []}' and json.loads((tmp_path / "seen.json").read_text(encoding="utf-8"))["outputSchema"] == {"type": "object"}


def test_replay_reuses_the_earlier_answer_for_the_same_request_only(tmp_path):
    """앞선 실행에 같은 요청(경로는 달라도 내용·그림이 같음)의 답이 있으면 기다리지 않고 그 답을 씁니다. 다른 요청은 대역을 기다립니다."""
    earlier, now = tmp_path / "earlier", tmp_path / "now"
    earlier.mkdir()
    image = ModelImage("그림 1", "image/png", b"png")
    thread = answer_when_asked(earlier, {"json": {"quotes": ["앞선 답"]}})
    FileExchangeModel(earlier, poll_seconds=0.01).complete(request(images=(image,)))
    thread.join()

    model = FileExchangeModel(now, replay=earlier, timeout_seconds=0.05, poll_seconds=0.01)
    response = model.complete(request(images=(image,)))
    assert json.loads(response.raw_text) == {"quotes": ["앞선 답"]}
    written = json.loads(next(now.glob("*.request.json")).read_text(encoding="utf-8"))
    assert written["replayedFrom"].startswith(str(earlier)) and written["answerPath"].startswith(str(now))
    with pytest.raises(ModelError) as waited:
        model.complete(request(images=(image,), user="다른 원문"))
    assert waited.value.code == "STANDIN_TIMEOUT"


def test_file_call_cache_keeps_the_first_answer_across_runs(tmp_path):
    first = FileCallCache(tmp_path)
    first.put("k", "gpt", "structure", {"rawText": "a"}, None)
    first.put("k", "gpt", "structure", {"rawText": "b"}, None)  # 같은 열쇠는 처음 것을 둡니다
    assert FileCallCache(tmp_path).get("k") == {"rawText": "a"} and FileCallCache(tmp_path).get("x") is None
