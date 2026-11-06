"""V2 섹션 담당 에이전트: 쓰기 도구가 넣는 즉시 형식·근거를 검사하고, 검증 미들웨어가 바뀐 차례마다 결과를 알리고,
담당들이 같은 앞부분(지시·도구·원문)으로 도구로 쌓은 항목이 V1과 같은 결과로 게시됨. 유료 호출 없음."""

import json
from types import SimpleNamespace

from events import raw_event
from helpers import ai_part, example
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from test_pipeline import answers, run
from test_v2_contract import sparse
from test_v2_document import TEXT, ToolCallingFake

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.v2 import graph
from mujuthaek_extraction.v2.agents import section
from mujuthaek_extraction.v2.agents.verify import VerifyMiddleware
from mujuthaek_extraction.v2.agents.verify import report as verify_report
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.tools.typed import add_tool
from mujuthaek_extraction.v2.tools.write import WRITE_TOOLS, SectionContext, SectionDraft


def call(name, **args):
    return {"name": name, "args": args, "id": f"{name}-{len(json.dumps(args))}"}


def test_write_tools_check_each_item_at_once_and_keep_judged_sections():
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    turn = AIMessage(
        content="",
        tool_calls=[
            call("add_schedules", items=[{**schedule, "evidence": ["p1.2"]}, {**schedule, "id": "bad", "evidence": ["p9.9"]}]),
            call("update_item", section="eligibility", item_id="x", changes={}),
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
    tools = [add_tool("schedules", ("text",)), *WRITE_TOOLS]
    agent = create_agent(ToolCallingFake(messages=iter([turn, later, AIMessage(content="끝")])), tools=tools, context_schema=SectionContext)
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    answers = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert answers[0]["added"] == ["apply"] and answers[0]["failed"][0]["id"] == "bad" and "p9.9" in answers[0]["failed"][0]["errors"][0]
    assert answers[1]["error"] == "NOT_MY_SECTION" and answers[2]["error"] == "UNKNOWN_ITEM"
    assert draft.coverage["schedules"] == {"status": "PARTIAL", "reason": "표 끝 행을 못 읽었어요."}
    assert draft.missing_for("schedules") == [{"target": "/schedules/0/startsAt", "reason": "TO_BE_ANNOUNCED", "description": "추후 알려요."}]
    assert draft.version == 3  # 넣기·상태·누락 기록마다 판이 바뀜(실패한 고치기는 그대로)
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


def test_original_text_must_be_the_source_as_written_and_is_filled_when_left_out():
    condition = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][0].items() if k not in ("quoteRefs", "originalText")})
    turn = AIMessage(
        content="",
        tool_calls=[
            call("add_eligibility", items=[{**condition, "id": "filled", "evidence": ["p1.3"]}]),
            call("add_eligibility", items=[{**condition, "id": "rewritten", "originalText": "소득이 150% 이하인 사람", "evidence": ["p1.3"]}]),
        ],
    )
    draft = SectionDraft(("eligibility",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    agent = create_agent(
        ToolCallingFake(messages=iter([turn, AIMessage(content="끝")])), tools=[add_tool("eligibility", ("text",))], context_schema=SectionContext
    )
    result = agent.invoke({"messages": [HumanMessage("자격 담당")]}, context=context)
    answers = {m.tool_call_id: json.loads(m.content) for m in result["messages"] if m.type == "tool"}
    assert [row["originalText"] for row in draft.items["eligibility"]] == ["■ 소득 : 150% 이하"]  # 비운 것은 첫 근거의 원문으로
    rejected = answers[turn.tool_calls[1]["id"]]["failed"][0]
    assert rejected["id"] == "rewritten" and rejected["errors"][0].startswith("/originalText: 원문에 그대로 있는 글이 아닙니다")


def test_verification_is_reported_after_each_turn_that_changed_the_draft_and_a_problem_left_after_a_fix_is_marked_again():
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    turns = [
        AIMessage(
            content="", tool_calls=[call("add_schedules", items=[{**schedule, "id": "first", "evidence": ["p1.2"]}, {**schedule, "evidence": ["p1.2"]}])]
        ),
        AIMessage(content="", tool_calls=[call("remove_item", section="schedules", item_id="first")]),  # 앞 항목을 빼 순번이 바뀜
        AIMessage(content="", tool_calls=[call("update_item", section="schedules", item_id="nope", changes={})]),  # 실패: 초안 그대로
        AIMessage(content="끝"),
    ]
    checked = []
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))

    def check():
        checked.append(draft.version)
        index = next(i for i, row in enumerate(draft.items["schedules"]) if row["id"] == "apply")
        return [{"code": "VALUE_NOT_IN_QUOTE", "target": f"/schedules/{index}/startsAt", "item": "apply", "description": "값이 인용에 없어요."}]

    context.check = check
    agent = create_agent(
        ToolCallingFake(messages=iter(turns)),
        tools=[add_tool("schedules", ("text",)), *WRITE_TOOLS],
        middleware=[VerifyMiddleware()],
        context_schema=SectionContext,
    )
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    reports = [m.content for m in result["messages"] if m.type == "human" and m.content.startswith("# 검증 결과")]
    assert checked == [2, 3] and len(reports) == 2  # 바뀐 차례 다음에만(실패한 고치기 뒤에는 다시 보지 않음)
    assert '"schedules": 2' in reports[0] and '"item": "apply"' in reports[0] and '"다시"' not in reports[0]
    assert '"schedules": 1' in reports[1] and '"다시": true' in reports[1]  # 순번이 바뀌어도 같은 항목의 같은 문제
    assert "## 고칠 것 1개" in reports[0] and "다른 방법으로 한 번 더" in reports[0]  # 값이 인용에 없음 = 근거 오류(고칠 것)
    traced = section._trace(result["messages"])
    assert "VALUE_NOT_IN_QUOTE" in traced[0]["verify"] and "verify" in traced[1] and "verify" not in traced[2]


def test_format_errors_that_make_the_assembler_drop_items_or_the_whole_answer_are_reported():
    draft = SectionDraft(("schedules",), items={"schedules": [{"id": "apply"}]})
    part = {
        "quotes": [{"ref": "q1", "documentId": "text", "text": ""}],
        "schedules": [{"id": "apply", "kind": "NOT_A_KIND"}],
        "coverage": {"schedules": {"status": "EXTRACTED", "reason": None}},
        "missingFields": [],
    }
    found = section._format_problems([part], draft)
    whole = [f for f in found if f["target"].startswith("/quotes")]
    assert whole and all("응답 전체를" in f["description"] for f in whole)
    item = [f for f in found if f["target"].startswith("/schedules/0")]
    assert item and all(f["item"] == "apply" and "이 항목을" in f["description"] for f in item)


def test_section_agents_share_one_prefix_add_items_with_typed_tools_and_the_notice_is_published_like_v1(monkeypatch):
    monkeypatch.setenv("EXTRACTION_ENGINE", "v2")
    recorded = answers()
    # 구조(공고·위치·공급)는 V1 방식(공급표 코드 + 한 번 호출)이라 시험에서는 그 결과를 꽂음
    monkeypatch.setattr(graph, "AGENTS", {"structure": lambda spec, state, rt: ([json.loads(recorded["structure"][0])], [])})
    part = ai_part(example("housing"))
    line = "p1.1"  # 예시 원문은 한 줄이고 예시의 인용은 그 줄 전체

    def items(name):
        rows = [part[name]] if name == "notice" else part[name]
        return [{**sparse({k: v for k, v in row.items() if k != "quoteRefs"}), "evidence": [line]} for row in rows]

    sections = {
        "schedules": ("schedules", "guidance"),
        "eligibility": ("eligibility",),
        "selection": ("selectionRules",),
        "documents": ("requiredDocuments",),
    }
    prefixes, lengths = [], {}

    class Recording(ToolCallingFake):
        """받은 앞부분(지시·첫 메시지·도구 이름)을 적어 두는 가짜 모델."""

        def bind_tools(self, tools, **kwargs):
            self.__dict__["tool_names"] = tuple(getattr(t, "name", None) or t["function"]["name"] for t in tools)
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            prefixes.append((messages[0].content, messages[1].content, self.__dict__.get("tool_names", ())))
            lengths.setdefault(self.__dict__.get("agent"), len(messages))
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def script(name):
        if name == section.PRIME:  # 데우기가 도구를 불러도 실행하지 않고 끝냄
            return iter([AIMessage(content="", tool_calls=[call("add_schedules", items=[])])])
        adds = [call(f"add_{s}", **({"item": items(s)[0]} if s == "notice" else {"items": items(s)})) for s in sections[name]]
        usage = {"input_tokens": 1_000, "output_tokens": 100, "total_tokens": 1_100}
        return iter([AIMessage(content="", tool_calls=adds, usage_metadata=usage), AIMessage(content="다 넣었어요.")])

    def chat(name, **kwargs):
        model = Recording(messages=script(name))
        model.__dict__["agent"] = name
        return model

    models = NoticeModels(RecordedModel({}, "local"), None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat)
    outcome = run(raw_event(), models)
    assert outcome.status == "COMPLETED" and outcome.error is None
    assert tools().validate(outcome.event, "events/extraction.completed.v1.json") == []
    calls = outcome.usage["v2"]["calls"]
    assert [c["agent"] for c in calls].count(section.PRIME) == 1 and {c["agent"] for c in calls} == {*sections, section.PRIME}
    assert len(calls) == 2 * len(sections) + 1  # 캐시 데우기 1번 + 담당마다 넣기·끝 2번(검증은 미들웨어가 차례를 쓰지 않고)
    # 데우기와 모든 담당이 같은 앞부분: 지시·첫 메시지(원문 전체)·도구 목록(모든 담당 섹션의 add 도구 + 쓰기 도구)
    assert len(set(prefixes)) == 1 and prefixes[0][1].startswith("# 원문") and "p1.1 " in prefixes[0][1]
    # 데우기 요청은 원문 메시지에서 끝남(OpenAI 캐시는 앞 요청이 끝난 곳까지 다시 씀), 담당은 그 뒤에 맡은 일
    assert lengths[section.PRIME] == 2 and {lengths[name] for name in sections} == {3}
    assert prefixes[0][2][:5] == ("add_schedules", "add_guidance", "add_eligibility", "add_selectionRules", "add_requiredDocuments")
    traces = {t["agent"]: t for t in outcome.usage["v2"]["traces"]}
    assert set(traces) == set(sections) and traces["eligibility"]["turns"][0]["calls"][0]["name"] == "add_eligibility"
    assert "남은 문제가 없습니다" in traces["eligibility"]["turns"][0]["verify"]  # 넣은 차례 다음 검증 결과(문제 없음)
    assert traces["eligibility"]["draft"]["items"]["eligibility"][0]["evidence"] == [line]  # 마지막 초안을 기록


def test_lost_values_the_verifier_moved_to_notes_are_reported_to_the_agent(monkeypatch):
    # 판정 섹션 밖의 근거 문제는 검증기가 메모로 내리고 항목을 뺌 → 담당에게는 검토 이슈처럼 알림(고칠 수 없는 표시는 빼고)
    quality = {
        "reviewIssues": [{"code": "VALUE_NOT_IN_QUOTE", "target": "/selectionRules/0/points", "description": "값이 인용에 없어요."}],
        "notes": [
            {"code": "ITEM_DROPPED_NO_EVIDENCE", "target": "/selectionRules", "description": "근거를 확인하지 못한 항목 1개를 뺐습니다: 50점"},
            {"code": "IMAGE_TRANSCRIBED_VALUES", "target": "/selectionRules", "description": "그림 판독 글자를 근거로 썼어요."},
            {"code": "EVIDENCE_AMBIGUOUS", "target": "/schedules/0", "description": "다른 담당의 섹션"},
        ],
    }
    candidate = {"selectionRules": [{"id": "score-1"}], "quality": quality}
    monkeypatch.setattr(section.pipeline, "evaluate_parts", lambda *args: SimpleNamespace(candidate=candidate))
    spec = SimpleNamespace(name="selection", sections=("selectionRules",))
    state = {"document": parse(TEXT), "material": None, "context": None, "parts": []}
    found = section._issues(spec, SectionDraft(("selectionRules",)), state, None, ("text",))
    assert [(f["code"], f.get("item")) for f in found] == [("VALUE_NOT_IN_QUOTE", "score-1"), ("ITEM_DROPPED_NO_EVIDENCE", None)]


def test_finish_ends_without_another_model_call_unless_verification_finds_a_new_problem():
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    add = call("add_schedules", items=[{**schedule, "evidence": ["p1.2"]}])

    def agent_run(turns, issues_by_version):
        draft = SectionDraft(("schedules",))
        context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
        context.check = lambda: issues_by_version.get(draft.version, [])
        agent = create_agent(
            ToolCallingFake(messages=iter(turns)),
            tools=[add_tool("schedules", ("text",)), *WRITE_TOOLS],
            middleware=[VerifyMiddleware()],
            context_schema=SectionContext,
        )
        result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
        return draft, [m for m in result["messages"] if m.type == "ai"]

    # 넣기와 끝내기를 한 차례에: 검증에 문제가 없으면 모델을 다시 부르지 않음
    draft, said = agent_run([AIMessage(content="", tool_calls=[add, call("finish", summary="일정 1개를 넣었어요.")]), AIMessage(content="불리면 안 됨")], {})
    assert len(said) == 1 and draft.finished == "일정 1개를 넣었어요." and len(draft.items["schedules"]) == 1
    # 새 문제가 나오면 끝내기를 거두고 알림 → 고친 뒤 다시 끝내기: 남은 문제가 앞서 알린 것(「다시」)뿐이면 끝
    issue = {"code": "VALUE_NOT_IN_QUOTE", "target": "/schedules/0/startsAt", "item": "apply", "description": "값이 인용에 없어요."}
    turns = [
        AIMessage(content="", tool_calls=[add, call("finish", summary="다 넣었어요.")]),
        AIMessage(
            content="", tool_calls=[call("update_item", section="schedules", item_id="apply", changes={"label": "접수"}), call("finish", summary="고쳤어요.")]
        ),
        AIMessage(content="불리면 안 됨"),
    ]
    draft, said = agent_run(turns, {1: [issue], 2: [issue]})
    assert len(said) == 2 and draft.finished == "고쳤어요."


def test_verification_separates_defects_to_fix_from_warnings_to_check():
    draft = SectionDraft(("eligibility",), items={"eligibility": [{"id": "a"}]})
    report = verify_report(
        draft,
        [
            {"code": "CONTRACT_DUPLICATE_ID", "target": "/eligibility/0/exceptions/0", "item": "a", "description": "DUPLICATE_ID", "다시": True},
            {"code": "EXCEPTION_SUSPECTED", "target": "/eligibility/0", "item": "a", "description": "기준값 뒤 다른 기준값"},
        ],
    )
    fix, check = report.index("## 고칠 것 1개"), report.index("## 확인할 것 1개")
    assert fix < report.index("CONTRACT_DUPLICATE_ID") < check < report.index("EXCEPTION_SUSPECTED")
    assert "다른 방법으로 한 번 더" in report and "원문상 맞으면 그대로" in report
