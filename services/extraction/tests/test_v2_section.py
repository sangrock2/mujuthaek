"""V2 섹션 담당 에이전트: 쓰기 도구가 넣는 즉시 형식·근거를 검사하고, 담당들이 도구로 쌓은 항목이 V1과 같은 결과로 게시됨. 유료 호출 없음."""

import json

from events import raw_event
from helpers import ai_part, example
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from test_pipeline import run
from test_v2_contract import sparse
from test_v2_document import TEXT, ToolCallingFake

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.tools.write import WRITE_TOOLS, SectionContext, SectionDraft


def call(name, **args):
    return {"name": name, "args": args, "id": f"{name}-{len(json.dumps(args))}"}


def test_write_tools_check_each_item_at_once_and_keep_judged_sections():
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    turn = AIMessage(
        content="",
        tool_calls=[
            call("add_items", section="schedules", items=[{**schedule, "evidence": ["p1.2"]}, {**schedule, "id": "bad", "evidence": ["p9.9"]}]),
            call("add_items", section="eligibility", items=[]),
            call("update_item", section="schedules", item_id="nope", changes={}),
            call("set_coverage", section="schedules", status="PARTIAL", reason="표 끝 행을 못 읽었어요."),
        ],
    )
    later = AIMessage(  # 한 차례의 도구는 동시에 실행되므로 방금 넣은 항목의 누락은 다음 차례에
        content="",
        tool_calls=[call("report_missing", section="schedules", item_id="apply", field="startsAt", reason="TO_BE_ANNOUNCED", description="추후 알려요.")],
    )
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    agent = create_agent(ToolCallingFake(messages=iter([turn, later, AIMessage(content="끝")])), tools=list(WRITE_TOOLS), context_schema=SectionContext)
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    answers = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert answers[0]["added"] == ["apply"] and answers[0]["failed"][0]["id"] == "bad" and "p9.9" in answers[0]["failed"][0]["errors"][0]
    assert answers[1]["error"] == "NOT_MY_SECTION" and answers[2]["error"] == "UNKNOWN_ITEM"
    assert draft.coverage["schedules"] == {"status": "PARTIAL", "reason": "표 끝 행을 못 읽었어요."}
    assert draft.missing_for("schedules") == [{"target": "/schedules/0/startsAt", "reason": "TO_BE_ANNOUNCED", "description": "추후 알려요."}]
    judged = SectionDraft(("eligibility",))
    refused = create_agent(
        ToolCallingFake(
            messages=iter(
                [
                    AIMessage(content="", tool_calls=[call("set_coverage", section="eligibility", status="NOT_IN_SOURCE", reason="없음")]),
                    AIMessage(content="끝"),
                ]
            )
        ),
        tools=list(WRITE_TOOLS),
        context_schema=SectionContext,
    ).invoke({"messages": [HumanMessage("자격")]}, context=SectionContext(document=parse(TEXT), draft=judged, documents=("text",)))
    assert json.loads(refused["messages"][2].content)["error"] == "NOT_ALLOWED" and judged.coverage == {}


def test_section_agents_add_items_with_tools_and_the_notice_is_published_like_v1(monkeypatch):
    monkeypatch.setenv("EXTRACTION_ENGINE", "v2")
    part = ai_part(example("housing"))
    line = "p1.1"  # 예시 원문은 한 줄이고 예시의 인용은 그 줄 전체

    def items(section):
        rows = [part[section]] if section == "notice" else part[section]
        return [{**sparse({k: v for k, v in row.items() if k != "quoteRefs"}), "evidence": [line]} for row in rows]

    sections = {
        "structure": ("notice", "locations", "supplyGroups"),
        "schedules": ("schedules", "guidance"),
        "eligibility": ("eligibility",),
        "selection": ("selectionRules",),
        "documents": ("requiredDocuments",),
    }

    def script(name):
        adds = [call("add_items", section=s, items=items(s)) for s in sections[name]]
        usage = {"input_tokens": 1_000, "output_tokens": 100, "total_tokens": 1_100}
        return iter(
            [AIMessage(content="", tool_calls=adds, usage_metadata=usage), AIMessage(content="", tool_calls=[call("check")]), AIMessage(content="다 넣었어요.")]
        )

    models = NoticeModels(
        RecordedModel({}, "local"), None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=lambda name: ToolCallingFake(messages=script(name))
    )
    outcome = run(raw_event(), models)
    assert outcome.status == "COMPLETED" and outcome.error is None
    assert tools().validate(outcome.event, "events/extraction.completed.v1.json") == []
    calls = outcome.usage["v2"]["calls"]
    assert {c["agent"] for c in calls} == set(sections) and len(calls) == 3 * len(sections)  # 담당마다 모델 호출 3번
