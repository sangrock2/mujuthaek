"""V2 구조 단계를 담당 앞부분으로(v2/agents/structure.py): 데우기 뒤에 공급표 열 의미·공고·위치를 담당과 같은 앞부분으로 묻고,
표는 코드가 옮기고, 받지 못하면 V1 방식으로 돌아감. 유료 호출 없음."""

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from mujuthaek_extraction.intake import InMemorySourceReader
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.pipeline import process
from mujuthaek_extraction.v2 import graph
from mujuthaek_extraction.v2.agents import section, structure
from mujuthaek_extraction.v2.contract import to_part
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.tools.write import SectionContext, SectionDraft
from mujuthaek_platform.events import new_event
from tests.intake.test_pdf_reader import attachment, merged_table_pdf
from tests.supply.test_supply_tables import MAPPING, structure_answer
from tests.support.events import raw_event
from tests.support.helpers import REGIONS
from tests.v2.test_v2_document import TEXT, ToolCallingFake

NOTICE = {"title": "Rental notice for test housing", "field": "HOUSING", "evidence": [{"id": "p1.1", "part": "Rental notice for test housing"}]}
LOCATION = {"id": "loc-1", "kind": "COMPLEX", "complexName": "test housing", "evidence": [{"id": "p1.1", "part": "test housing"}]}
# 엄격 출력 형식이 아니라 null 칸을 생략하고 표 번호를 원문 메시지의 표 id로 적은 답
LOOSE_MAPPING = {
    "tables": [
        {
            "table": "t1-1",
            "role": "SUPPLY",
            "rowUnit": "HOUSING_TYPE",
            "columns": [
                {"column": 1, "meaning": "HOUSING_TYPE"},
                {"column": 2, "meaning": "PRICE", "priceKind": "DEPOSIT", "unit": "천원", "plan": "기본", "priceStage": "STANDARD"},
                {"column": 3, "meaning": "PRICE", "priceKind": "MONTHLY_RENT", "unit": "원", "plan": "기본", "priceStage": "STANDARD"},
                {"column": 4, "meaning": "COUNT", "countKind": "TOTAL_HOUSING"},
            ],
        }
    ]
}


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr(graph, "AGENTS", {})


def table_notice(models):
    data = merged_table_pdf()
    event = copy.deepcopy(raw_event())
    event["payload"]["files"] = [attachment("notice.pdf", data)]
    clock = lambda: datetime(2026, 10, 15, tzinfo=UTC)  # noqa: E731
    reader = InMemorySourceReader(files={"raw/x/notice.pdf": data})
    return process(event, models=models, reader=reader, regions=REGIONS, clock=clock, new_event=new_event, require_pdf=False)


def recording_chat(scripts):
    """담당 이름마다 녹화한 답을 차례로 내는 가짜 채팅 모델. 받은 요청(지시·첫 메시지·도구·tool_choice·메시지 수)을 적어 둡니다."""
    seen = []

    class Recording(ToolCallingFake):
        def bind_tools(self, tools, **kwargs):
            self.__dict__["tools"] = tuple(getattr(t, "name", None) or t["function"]["name"] for t in tools)
            self.__dict__["tool_choice"] = kwargs.get("tool_choice")
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            entry = (self.__dict__["agent"], messages[0].content, messages[1].content, self.__dict__.get("tools"), self.__dict__.get("tool_choice"))
            seen.append((*entry, len(messages)))
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def chat(name, **kwargs):
        answers = scripts.get(name) or [AIMessage(content="끝")]
        model = Recording(messages=iter([answers.pop(0) if len(answers) > 1 else answers[0]]))
        model.__dict__["agent"] = name
        return model

    return chat, seen


def test_structure_reads_the_warmed_agent_prefix_with_tools_off_and_supply_rows_are_copied_by_code(v2):
    first = {"notice": NOTICE, "locations": [{**LOCATION, "evidence": ["p9.9"]}], "coverage": {"supplyGroups": {"status": "PARTIAL", "reason": "x"}}}
    scripts = {
        section.PRIME: [AIMessage(content="")],
        structure.MAPPING: [AIMessage(content=json.dumps(LOOSE_MAPPING))],
        structure.STRUCTURE: [AIMessage(content=json.dumps(first)), AIMessage(content="```json\n" + json.dumps({"locations": [LOCATION]}) + "\n```")],
    }
    chat, seen = recording_chat(scripts)
    v1 = RecordedModel({"recheck": ['{"quotes": []}'] * 3}, "local")
    outcome = table_notice(NoticeModels(v1, None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat))

    order = [entry[0] for entry in seen]
    assert order[:4] == [section.PRIME, structure.MAPPING, structure.STRUCTURE, structure.STRUCTURE]  # 데우기가 끝난 뒤 같은 앞부분으로
    assert set(order[4:]) == {"schedules", "eligibility", "selection", "documents"} and order.count(section.PRIME) == 1
    assert len({entry[1:4] for entry in seen}) == 1  # 지시·원문 메시지·도구 목록이 데우기·구조·담당 모두 같음
    assert {entry[0]: entry[4] for entry in seen[:4]} == {section.PRIME: None, structure.MAPPING: "none", structure.STRUCTURE: "none"}
    assert seen[0][5] == 2 and seen[3][5] == 5  # 데우기는 원문 메시지에서 끝나고, 고쳐 받기는 앞 대화에 이어서
    assert not [r.call_name for r in v1.requests if r.call_name in ("supply_tables", "structure")]  # V1 호출 층은 쓰지 않음

    candidate = outcome.candidate
    assert candidate["notice"]["title"] == "Rental notice for test housing"
    assert [g["housingTypeCode"] for g in candidate["supplyGroups"]] == ["39A", "46B"]  # 공급 묶음은 코드가 표에서 옮김
    assert [loc["id"] for loc in candidate["locations"]] == ["loc-1"]  # 근거가 틀려 거절된 위치를 고쳐 받음
    calls = outcome.usage["v2"]["calls"]
    assert [c["agent"] for c in calls][:4] == [section.PRIME, structure.MAPPING, structure.STRUCTURE, structure.STRUCTURE]
    trace = next(t for t in outcome.usage["v2"]["traces"] if t["agent"] == structure.STRUCTURE)
    assert trace["problems"] == [] and trace["draft"]["coverage"] == {}  # 공급 묶음 상태는 답이 아니라 코드가 정함


def test_without_a_usable_mapping_the_structure_falls_back_to_the_v1_calls_after_the_warmup(v2):
    scripts = {section.PRIME: [AIMessage(content="")], structure.MAPPING: [AIMessage(content='{"tables": "표 없음"}')]}
    chat, seen = recording_chat(scripts)
    source_like = SimpleNamespace(text_document_id="pdf-text")
    v1 = RecordedModel({"supply_tables": [json.dumps(MAPPING)], "structure": [structure_answer(source_like)], "recheck": ['{"quotes": []}'] * 3}, "local")
    outcome = table_notice(NoticeModels(v1, None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat))

    assert [entry[0] for entry in seen][:3] == [section.PRIME, structure.MAPPING, structure.MAPPING]  # 형식 문제를 알려 한 번 더 받음
    assert [entry[0] for entry in seen].count(section.PRIME) == 1  # 계획 노드는 데우기를 보내지 않음(구조가 이미 보냄)
    assert [r.call_name for r in v1.requests][:2] == ["supply_tables", "structure"]  # 녹화 답의 공고는 이 PDF 글이 아니라 결과는 실패
    calls = outcome.usage["v2"]["calls"]
    assert [c["agent"] for c in calls][:3] == [section.PRIME, structure.MAPPING, structure.MAPPING]  # 받지 못한 시도의 기록도 남김
    trace = next(t for t in outcome.usage["v2"]["traces"] if t["agent"] == structure.MAPPING)
    assert "tables" in trace["problem"]


def test_switched_off_the_structure_uses_the_v1_calls_and_the_plan_warms_the_cache(v2, monkeypatch):
    monkeypatch.setenv(structure.SHARED_ENV, "false")
    chat, seen = recording_chat({section.PRIME: [AIMessage(content="")]})
    source_like = SimpleNamespace(text_document_id="pdf-text")
    v1 = RecordedModel({"supply_tables": [json.dumps(MAPPING)], "structure": [structure_answer(source_like)], "recheck": ['{"quotes": []}'] * 3}, "local")
    table_notice(NoticeModels(v1, None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat))
    assert structure.MAPPING not in {entry[0] for entry in seen} and [entry[0] for entry in seen].count(section.PRIME) == 1
    assert [r.call_name for r in v1.requests][:2] == ["supply_tables", "structure"]


@pytest.mark.parametrize(
    ("answered", "labels", "expected"),
    [
        ("t1-1", ["1-1"], "1-1"),
        ("1-1", ["1-1"], "1-1"),
        ("t4-1", ["1:4-1", "2:3-1"], "1:4-1"),
        ("d2.t3-1", ["1:4-1", "2:3-1"], "2:3-1"),
        ("t9-9", ["1-1"], "t9-9"),  # 모르는 표는 그대로(코드가 표를 찾지 못해 버림)
        ("엑셀1", ["엑셀1"], "엑셀1"),
    ],
)
def test_table_ids_of_the_agent_document_are_read_as_v1_table_labels(answered, labels, expected):
    assert structure._v1_label(answered, labels) == expected


def test_loose_mapping_answers_get_their_omitted_nulls_and_wrong_values_are_reported():
    mapping, problem = structure._read_mapping(json.dumps(LOOSE_MAPPING), ["1-1"])
    assert problem is None and mapping["tables"][0]["table"] == "1-1" and mapping["tables"][0]["complex"] is None
    assert mapping["tables"][0]["columns"][0] == {"column": 1, "meaning": "HOUSING_TYPE", **dict.fromkeys(structure.NULLABLE_COLUMN_KEYS)}
    bad = copy.deepcopy(LOOSE_MAPPING)
    bad["tables"][0]["columns"][1]["priceKind"] = "RENT"
    assert structure._read_mapping("앞 설명 " + json.dumps(bad), ["1-1"])[1] is not None
    assert structure._read_mapping("열 의미를 모르겠어요", ["1-1"])[1].startswith("JSON으로 읽을 수 없습니다")


def test_answer_items_go_through_the_agent_checks_and_only_structure_sections_take_status_and_missing_records():
    draft = SectionDraft(structure.SECTIONS)
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    answer = {
        "notice": {"title": "x", "evidence": ["p1.1"]},
        "locations": {"id": "loc-1"},  # 목록이 아님
        "coverage": {"notice": {"status": "NOT_IN_SOURCE", "reason": "없음"}, "supplyGroups": {"status": "PARTIAL", "reason": "x"}},
        "missing": [{"section": "notice", "id": None, "field": "announcedOn", "reason": "NOT_IN_SOURCE", "description": "공고일이 없어요."}],
    }
    problems = structure._apply(context, answer)
    assert draft.items["notice"][0]["title"] == "x" and "locations" not in draft.items
    assert problems[0] == "locations: 항목 목록이어야 합니다." and problems[1].startswith("coverage notice:") and len(problems) == 2
    assert draft.coverage == {} and draft.missing_for("notice") == [
        {"target": "/notice/announcedOn", "reason": "NOT_IN_SOURCE", "description": "공고일이 없어요."}
    ]


def test_locations_left_rejected_after_the_repair_send_the_section_to_review(monkeypatch):
    replies = iter([{"notice": {"title": "x", "evidence": ["p1.1"]}, "locations": [{**LOCATION, "evidence": ["p9.9"]}]}, {}])
    monkeypatch.setattr(
        structure, "_ask", lambda name, state, rt, documents, messages, tokens, usage: [*messages, AIMessage(content=json.dumps(next(replies)))]
    )
    state = {"document": parse(TEXT), "rules": SimpleNamespace(system_prompt=lambda: "")}
    rt = SimpleNamespace(models=SimpleNamespace(budget=None))
    spec = SimpleNamespace(instructions="구조")
    traces = []
    draft = structure._notice_and_locations(spec, state, rt, ("text",), "메모", [], traces)
    assert draft.coverage == {"locations": {"status": "PARTIAL", "reason": structure.NOT_ADDED}} and draft.items["notice"]
    assert traces[0]["problems"] == []  # 고칠 수 없다는 빈 답({}): 남은 거절은 섹션 상태로
    replies = iter([{"locations": [LOCATION]}, {"locations": []}])
    assert structure._notice_and_locations(spec, state, rt, ("text",), "메모", [], []) is None  # 공고가 없으면 V1 방식으로


def test_image_and_too_short_evidence_is_dropped_from_the_notice_when_usable_source_text_evidence_is_there():
    # 2026-11-10 23건 유료 확인: sh-311005 본문에도 있는 공고 정보에 표지 그림 판독 줄을 함께 근거로 씀, sh-310672 떨어진 조각 줄 「06」을 근거로 씀
    # — 둘 다 공고 전체가 검수로 감. 쓸 만한 원문 근거가 함께 있으면 그 근거만 남김
    doc = parse("\n".join(["--- 1쪽 ---", "공실세대 입주자 모집 공고", "[표 1-1]", "| 06 |", "--- 2쪽 ---", "06", "--- 3쪽 ---", "06"]))
    notice = [{"title": "x", "evidence": ["g1.3", "p1.1", {"id": "g1.4", "part": "어울리"}, "p2.1"], "counts": [{"value": 1, "evidence": ["g1.t1.r2"]}]}]
    structure._text_evidence_first(notice, doc)
    assert notice[0]["evidence"] == ["p1.1"] and notice[0]["counts"][0]["evidence"] == ["g1.t1.r2"]  # 그림 근거뿐이면 그대로


def test_a_too_short_source_line_is_joined_with_its_neighbor_lines_in_the_structure_stage():
    # 2026-11-10 23건 유료 확인 sh-310672: 공고 근거 줄 하나가 날짜 조각 「06」뿐이라 「인용문이 너무 짧음」으로 공고 전체가 사람 확인
    doc = parse("\n".join(["--- 1쪽 ---", "공고일 2026. 09.", "06", "공실세대 입주자 모집", "--- 2쪽 ---", "06"]))
    notice = {"title": "공실세대 입주자 모집", "evidence": ["p1.2", "p1.3"]}
    plain = to_part("notice", [notice], doc, ("text",))
    joined = to_part("notice", [notice], doc, ("text",), anchors=True)
    assert "06" in [q["text"] for q in plain["quotes"]]
    assert [q["text"] for q in joined["quotes"]][0] == "공고일 2026. 09.\n06"
