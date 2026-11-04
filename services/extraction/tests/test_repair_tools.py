"""재확인 에이전트 도구: 원문 찾기·쪽 읽기·인용 확인·항목 검사·제출. 원문 고정본과 검증기만 씁니다(모델 호출 없음)."""

import json

from helpers import example, to_ai
from test_recheck import setup

from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ToolCall
from mujuthaek_extraction.repair.tools import RESULT_CHARS, SPECS, RepairTools, item_check

PAGED = "머리말\n--- 1쪽 ---\n신청자격: 무주택세대구성원\n소득 기준 100% 이하\n--- 2쪽 ---\n제출서류: 주민등록등본\n=== 첨부 목록.pdf ===\n첨부 글\n"


def material(text):
    return ExtractionMaterial(text=text, text_document_id="text1", units=(), units_document_id=None, files=())


def call(tools, name, **args):
    return json.loads(tools.run(ToolCall("c", name, json.dumps(args, ensure_ascii=False))))


def no_check(item, quotes):
    return []


def test_search_finds_text_with_page_and_ignores_spacing():
    tools = RepairTools(material(PAGED), no_check)
    found = call(tools, "search_source", query="소득기준", limit=3)
    assert found["total"] == 1 and found["hits"][0]["page"] == 1 and "100% 이하" in found["hits"][0]["snippet"]
    assert call(tools, "search_source", query="첨부 글", limit=3)["hits"][0]["page"] is None  # 첨부 경계 뒤는 쪽을 정하지 않음
    assert call(tools, "search_source", query="가", limit=3)["error"] == "BAD_QUERY"


def test_read_page_returns_one_page_and_reports_missing_pages():
    tools = RepairTools(material(PAGED), no_check)
    page = call(tools, "read_page", page=2, from_char=0)
    assert "주민등록등본" in page["text"] and "무주택" not in page["text"]
    assert call(tools, "read_page", page=9, from_char=0)["error"] == "NO_SUCH_PAGE"
    assert call(RepairTools(material("쪽 표시 없는 글"), no_check), "read_page", page=1, from_char=0)["error"] == "NO_PAGES"


def test_check_quote_uses_extraction_matching_and_suggests_near_lines():
    tools = RepairTools(material(PAGED), no_check)
    assert call(tools, "check_quote", quote="신청자격: 무주택세대구성원") == {"found": True, "places": 1, "exact": True, "page": 1}
    spaced = call(tools, "check_quote", quote="신청자격:무주택 세대구성원")  # 공백 차이는 추출과 같이 찾음(정확 일치는 아님)
    assert spaced["found"] is True and spaced["exact"] is False
    missing = call(tools, "check_quote", quote="신청자격: 무주택 세대주")
    assert missing["found"] is False and missing["near"][0]["text"].startswith("신청자격")


def test_validate_item_reports_remaining_problems_from_the_verifier():
    data, source, parts, evaluate = setup()
    item_id = data["eligibility"][1]["id"]
    tools = RepairTools(source.material, item_check(parts, evaluate, "eligibility", item_id, "text1"))
    broken = parts[0]["eligibility"][1]
    quotes = [{"ref": q["ref"], "text": q["text"]} for q in parts[0]["quotes"]]
    problems = call(tools, "validate_item", item_json=json.dumps(broken, ensure_ascii=False), quotes=quotes)["problems"]
    assert any("EVIDENCE_QUOTE_NOT_FOUND" in p for p in problems)

    fixed = json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))
    good = [{"ref": "q1", "text": data["evidence"][0]["quote"]}]
    assert call(tools, "validate_item", item_json=json.dumps(fixed, ensure_ascii=False), quotes=good)["problems"] == []
    renamed = {**fixed, "id": "other"}
    assert call(tools, "validate_item", item_json=json.dumps(renamed), quotes=good)["problems"][0].startswith("ID_CHANGED")


def test_submit_records_the_fix_or_the_reason_to_give_up():
    tools = RepairTools(material(PAGED), no_check)
    assert call(tools, "submit_fix", item_json='{"id": "e1"}', quotes=[{"ref": "q1", "text": "소득 기준"}], give_up="") == {"received": True}
    assert tools.submission.item == {"id": "e1"} and tools.submission.quotes == [{"ref": "q1", "text": "소득 기준"}]
    call(tools, "submit_fix", item_json="", quotes=[], give_up="원문에서 찾지 못함")
    assert tools.submission.item is None and tools.submission.give_up == "원문에서 찾지 못함"
    assert call(tools, "submit_fix", item_json="[1]", quotes=[], give_up="")["error"] == "BAD_ITEM"


def test_bad_calls_return_errors_instead_of_raising():
    tools = RepairTools(material(PAGED), no_check)
    assert json.loads(tools.run(ToolCall("c", "delete_everything", "{}")))["error"] == "UNKNOWN_TOOL"
    assert json.loads(tools.run(ToolCall("c", "search_source", "not json")))["error"] == "BAD_ARGUMENTS"
    assert json.loads(tools.run(ToolCall("c", "search_source", '{"q": 1}')))["error"] == "BAD_ARGUMENTS"
    assert tools.calls == {"delete_everything": 1, "search_source": 2}


def test_long_results_are_cut_to_the_limit():
    text = "\n".join(f"--- {n}쪽 ---\n" + "소득 기준 " * 400 for n in range(1, 4))
    tools = RepairTools(material(text), no_check)
    assert len(tools.run(ToolCall("c", "search_source", '{"query": "소득 기준", "limit": 5}'))) <= RESULT_CHARS


def test_tool_inputs_are_strict_objects():
    for spec in SPECS:
        assert spec.parameters["additionalProperties"] is False and set(spec.parameters["required"]) == set(spec.parameters["properties"])


def test_example_material_is_searchable():
    data = example("housing")
    _, source, _, _ = setup()
    quote = data["evidence"][0]["quote"]
    assert call(RepairTools(source.material, no_check), "check_quote", quote=quote)["found"] is True
