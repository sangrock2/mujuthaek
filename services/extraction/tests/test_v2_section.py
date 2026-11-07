"""V2 섹션 담당 에이전트: 쓰기 도구가 넣는 즉시 형식·근거를 검사하고, 검증 미들웨어가 바뀐 차례마다 결과를 알리고,
담당들이 같은 앞부분(지시·도구·원문)으로 도구로 쌓은 항목이 V1과 같은 결과로 게시됨. 유료 호출 없음."""

import json
from types import SimpleNamespace

from events import raw_event
from helpers import ai_part, example
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from test_pipeline import answers, run
from test_v2_contract import sparse
from test_v2_document import TEXT, ToolCallingFake
from test_v2_llm import FlakyFake

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.model.pricing import Budget
from mujuthaek_extraction.v2 import graph
from mujuthaek_extraction.v2.agents import section
from mujuthaek_extraction.v2.agents.verify import VerifyMiddleware
from mujuthaek_extraction.v2.agents.verify import report as verify_report
from mujuthaek_extraction.v2.contract import NOTICE_SCOPE
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.llm import retry
from mujuthaek_extraction.v2.tools.typed import add_tool
from mujuthaek_extraction.v2.tools.typed import item_schema as typed_item_schema
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
    assert draft.version == 4  # 넣기·거절된 넣기·상태·누락 기록마다 판이 바뀜(실패한 고치기는 그대로)
    assert list(draft.rejected) == [("schedules", "bad")]  # 거절된 항목은 다시 넣을 때까지 남음
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


def test_original_text_inside_parts_is_checked_when_added_and_the_refusal_names_the_part_and_the_closest_source_line():
    # 2026-11-06 5건 재측정 bmc-72: 원문 한 줄을 예외 둘로 나누며 가운데를 뺀 글을 예외 originalText로 적음. 넣을 때는 하위 칸을 보지 않았고,
    # 검증 결과는 「exceptions/3」 순번만 알려 담당이 다른 예외를 고친 뒤 그만둠 → 소득·자산 기준이 사람 확인으로
    text = "\n".join(["--- 1쪽 ---", "■ 소득 : 70% 이하", "- 자녀별 가산 : 1명 10%p, 2명 이상 20%p"])
    income = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][2].items() if k not in ("quoteRefs", "originalText")})

    def item(item_id, written):
        exception = {**income["exceptions"][0], "id": f"{item_id}-two", "originalText": written, "evidence": ["p1.2"]}
        return {**income, "id": item_id, "evidence": ["p1.1"], "exceptions": [exception]}

    turn = AIMessage(content="", tool_calls=[call("add_eligibility", items=[item("joined", "- 자녀별 가산 : 2명 이상 20%p"), item("part", "2명 이상 20%p")])])
    draft = SectionDraft(("eligibility",))
    context = SectionContext(document=parse(text), draft=draft, documents=("text",))
    agent = create_agent(
        ToolCallingFake(messages=iter([turn, AIMessage(content="끝")])), tools=[add_tool("eligibility", ("text",))], context_schema=SectionContext
    )
    result = agent.invoke({"messages": [HumanMessage("자격 담당")]}, context=context)
    answer = json.loads(next(m.content for m in result["messages"] if m.type == "tool"))
    assert answer["added"] == ["part"]  # 한 줄의 이어진 일부는 원문 그대로
    failed = answer["failed"][0]
    assert failed["id"] == "joined" and failed["errors"][0].startswith("/exceptions/0/originalText(joined-two): 「- 자녀별 가산 : 2명 이상 20%p」")
    assert "가장 비슷한 원문 p1.2 「- 자녀별 가산 : 1명 10%p, 2명 이상 20%p」" in failed["errors"][0]
    assert draft.rejected == {("eligibility", "joined"): failed["errors"]}


def test_an_exception_left_without_original_text_is_filled_from_its_own_evidence_when_added_or_changed():
    # 2026-11-07 유료 확인 dudc-8934: 가산표 행을 예외로 넣으며 originalText를 「2인 1인 120%」처럼 줄여 적어 거절 → 고치는 데 차례 2번을 써 호출 상한에 끊김
    text = "\n".join(["--- 1쪽 ---", "■ 소득 : 70% 이하", "- 자녀별 가산 : 1명 10%p, 2명 이상 20%p"])
    income = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][2].items() if k not in ("quoteRefs", "originalText")})
    bare = {k: v for k, v in income["exceptions"][0].items() if k != "originalText"}
    added = {**income, "id": "added", "evidence": ["p1.1"], "exceptions": [{**bare, "id": "own", "evidence": ["p1.2"]}]}
    orphan = {**income, "id": "orphan", "evidence": ["p1.1"], "exceptions": [{**bare, "id": "none"}]}  # 예외 근거가 없으면 항목 근거로 채우지 않음
    turns = [
        AIMessage(content="", tool_calls=[call("add_eligibility", items=[added, orphan])]),
        AIMessage(
            content="",
            tool_calls=[call("update_item", section="eligibility", item_id="added", changes={"exceptions": [{**bare, "id": "later", "evidence": ["p1.2"]}]})],
        ),
        AIMessage(content="끝"),
    ]
    draft = SectionDraft(("eligibility",))
    context = SectionContext(document=parse(text), draft=draft, documents=("text",))
    tools = [add_tool("eligibility", ("text",)), *WRITE_TOOLS]
    agent = create_agent(ToolCallingFake(messages=iter(turns)), tools=tools, context_schema=SectionContext)
    result = agent.invoke({"messages": [HumanMessage("자격 담당")]}, context=context)
    answers = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert answers[0]["added"] == ["added"] and [f["id"] for f in answers[0]["failed"]] == ["orphan"]
    assert "'originalText' is a required property" in answers[0]["failed"][0]["errors"][0]
    assert answers[1] == {"ok": "eligibility/added 고침"}  # 고치며 넣은 예외도 채움
    [exception] = draft.items["eligibility"][0]["exceptions"]
    assert exception["id"] == "later" and exception["originalText"] == "- 자녀별 가산 : 1명 10%p, 2명 이상 20%p"


def test_a_problem_inside_a_part_of_an_item_names_the_part_too():
    candidate = {"eligibility": [{"id": "income", "exceptions": [{"id": "one"}, {"id": "two", "when": {"status": "STRUCTURED"}}]}]}
    assert section._item_of(candidate, "/eligibility/0/exceptions/1/originalText") == {"item": "income", "inner": "two"}
    assert section._item_of(candidate, "/eligibility/0/exceptions/1/when/status") == {"item": "income", "inner": "two"}
    assert section._item_of(candidate, "/eligibility/0/rule") == {"item": "income"}
    assert section._item_of(candidate, "/eligibility/0/exceptions/9") == {"item": "income"}


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
    monkeypatch.setattr(section.pipeline, "evaluate_parts", lambda *args: SimpleNamespace(candidate=candidate, contract_errors=[]))
    spec = SimpleNamespace(name="selection", sections=("selectionRules",))
    state = {"document": parse(TEXT), "material": None, "context": None, "parts": []}
    found = section._issues(spec, SectionDraft(("selectionRules",)), state, None, ("text",))
    assert [(f["code"], f.get("item")) for f in found] == [("VALUE_NOT_IN_QUOTE", "score-1"), ("ITEM_DROPPED_NO_EVIDENCE", None)]


def test_contract_errors_that_the_last_cleanup_would_act_on_are_reported_to_fix_with_how(monkeypatch):
    # 2026-11-07 23건 재조립 sh-310976: 담당이 넣은 소득 70% 조건식이 기준 연도·버전이 비어 마지막 계약 정리에서 원문만 남음(담당은 받지 못했음)
    candidate = {"eligibility": [{"id": "income", "rule": {}}], "quality": {"reviewIssues": [], "notes": []}}
    errors = ["INCOMPLETE_INCOME_BENCHMARK /eligibility/0/rule/expression", "UNRESOLVED_SCOPE /schedules/0/scope"]
    monkeypatch.setattr(section.pipeline, "evaluate_parts", lambda *args: SimpleNamespace(candidate=candidate, contract_errors=errors))
    spec = SimpleNamespace(name="eligibility", sections=("eligibility",))
    state = {"document": parse(TEXT), "material": None, "context": None, "parts": []}
    found = section._issues(spec, SectionDraft(("eligibility",)), state, None, ("text",))
    assert [(f["code"], f["target"], f.get("item")) for f in found] == [("CONTRACT_INCOMPLETE_INCOME_BENCHMARK", "/eligibility/0/rule/expression", "income")]
    text = verify_report(SectionDraft(("eligibility",)), found)
    assert "## 고칠 것 1개" in text and "referenceVersion에 원문의 기준 표현" in text


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


def test_an_agent_that_keeps_failing_stops_alone_and_the_notice_goes_on(monkeypatch):
    # 2026-11-06 23건 측정: 담당 하나의 시간 초과가 그래프·공고·측정 전체를 멈춤 → 재시도로도 안 되면 그 담당만 멈추고 섹션은 사람 확인으로
    monkeypatch.setenv("EXTRACTION_ENGINE", "v2")
    monkeypatch.setattr(retry, "FIRST_DELAY_SECONDS", 0.0)
    recorded = answers()
    monkeypatch.setattr(graph, "AGENTS", {"structure": lambda spec, state, rt: ([json.loads(recorded["structure"][0])], [])})

    def chat(name, **kwargs):
        if name == "eligibility":
            model = FlakyFake(messages=iter([]))
            model.__dict__["fail_times"] = 99
            return model
        return ToolCallingFake(messages=iter([AIMessage(content="끝")]))

    outcome = run(raw_event(), NoticeModels(RecordedModel({}, "local"), None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat))
    assert outcome.status in ("PARTIAL", "IN_REVIEW") and outcome.candidate is not None
    traces = {t["agent"]: t for t in outcome.usage["v2"]["traces"]}
    assert traces["eligibility"]["stopped"].startswith("APITimeoutError") and traces["schedules"]["stopped"] is None
    failed = [c for c in outcome.usage["v2"]["calls"] if c.get("agent") == "eligibility" and "error" in c]
    assert len(failed) == 1 + retry.RETRIES  # 처음 + 재시도, 시도마다 최악 비용을 예산에 셈


def test_an_agent_cut_off_by_the_call_limit_before_finishing_sends_its_section_to_review(monkeypatch):
    # 2026-11-07 유료 확인 dudc-8934: 자격 담당이 기준표 가산 행을 넣다 8번째 호출에서 끊겼는데 범위가 비어 「다 넣음」이 되어 항목 13개가 빠진 채 게시됨
    monkeypatch.setenv("EXTRACTION_ENGINE", "v2")
    assert section.MODEL_CALLS["eligibility"] == 10 > section.MAX_MODEL_CALLS  # 자격 담당만 상한이 큼(기준표 행 예외)
    monkeypatch.setattr(section, "MODEL_CALLS", {"eligibility": 2})
    recorded = answers()
    monkeypatch.setattr(graph, "AGENTS", {"structure": lambda spec, state, rt: ([json.loads(recorded["structure"][0])], [])})
    rows = [{**sparse({k: v for k, v in row.items() if k != "quoteRefs"}), "evidence": ["p1.1"]} for row in ai_part(example("housing"))["eligibility"]]

    def outcome_with(*turns):
        def chat(name, **kwargs):
            if name == "eligibility":
                return ToolCallingFake(messages=iter([AIMessage(content="", tool_calls=[call("add_eligibility", items=rows)]), *turns]))
            return ToolCallingFake(messages=iter([AIMessage(content="끝")]))

        outcome = run(raw_event(), NoticeModels(RecordedModel({}, "local"), None, Budget("gpt-6-luna", 0.5), {"primary": "local"}, chat=chat))
        return outcome, {t["agent"]: t for t in outcome.usage["v2"]["traces"]}

    def fix(n):
        return call("update_item", section="eligibility", item_id=rows[0]["id"], changes={"description": f"고침 {n}"})

    outcome, traces = outcome_with(*(AIMessage(content="", tool_calls=[fix(n)]) for n in range(3)))  # 넣고 고치다 상한에 닿음(끝내기 없음)
    assert traces["eligibility"]["stopped"] == "모델 호출 상한(2번)" and traces["schedules"]["stopped"] is None
    coverage = outcome.candidate["quality"]["coverage"]["eligibility"]
    assert coverage["status"] == "PARTIAL" and "끝내기 전에 멈췄어요" in coverage["reason"] and outcome.candidate["eligibility"]  # 넣은 항목은 남김
    # 마지막 호출에서 끝내기까지 불렀으면 상한 답이 붙어도 끝낸 것입니다
    outcome, traces = outcome_with(AIMessage(content="", tool_calls=[fix(0), call("finish", summary="다 넣었어요.")]))
    assert traces["eligibility"]["stopped"] is None and outcome.candidate["quality"]["coverage"]["eligibility"]["status"] == "EXTRACTED"
    assert traces["eligibility"]["turns"][-1]["text"].startswith(section.CALL_LIMIT_MESSAGE)  # 상한 답은 붙었음


def test_unknown_tool_arguments_and_tool_errors_come_back_as_errors_and_the_agent_goes_on():
    # 2026-11-06 23건 측정: 넣기 도구에 evidence를 항목 밖에 적어 TypeError → 도구 실행기가 오류를 올려 측정 전체가 멈춤
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}

    @tool
    def broken(note: str) -> str:
        """시험용: 늘 실패하는 도구."""
        raise RuntimeError("도구 결함")

    turns = [
        AIMessage(content="", tool_calls=[call("add_schedules", items=[schedule], evidence=["p1.2"]), call("broken", note="x")]),
        AIMessage(content="", tool_calls=[call("add_schedules", items=[{**schedule, "evidence": ["p1.2"]}])]),
        AIMessage(content="끝"),
    ]
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    agent = create_agent(
        ToolCallingFake(messages=iter(turns)),
        tools=[add_tool("schedules", ("text",)), broken],
        middleware=[section.ToolErrorMiddleware()],
        context_schema=SectionContext,
    )
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    answers = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert answers[0]["error"] == "BAD_ARGS" and "evidence" in answers[0]["message"]
    assert answers[1] == {"error": "TOOL_FAILED", "message": "RuntimeError: 도구 결함"}
    assert answers[2]["added"] == ["apply"] and result["messages"][-1].content == "끝"  # 다음 차례에 고쳐 넣고 끝냄


def test_items_refused_when_added_are_reported_to_fix_until_they_are_added_again():
    # 2026-11-06 23건 측정: 첫 차례에 근거 없이 거절된 자산·자동차 기준을 담당이 다시 넣지 않고 「등록했어요」로 끝내 16값이 빠짐
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    kept, later = {**schedule, "id": "kept", "evidence": ["p1.2"]}, {**schedule, "id": "later"}
    turns = [
        AIMessage(content="", tool_calls=[call("add_schedules", items=[kept])]),
        # 거절만 있는 차례에 끝내기를 함께 불러도 끝나지 않음(이미 있는 id의 거절은 빠진 것이 아님)
        AIMessage(content="", tool_calls=[call("add_schedules", items=[kept, later]), call("finish", summary="다 넣었어요.")]),
        AIMessage(content="", tool_calls=[call("add_schedules", items=[{**later, "evidence": ["p1.2"]}]), call("finish", summary="고쳐 넣었어요.")]),
        AIMessage(content="불리면 안 됨"),
    ]
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    context.check = lambda: section._not_added(draft)
    agent = create_agent(
        ToolCallingFake(messages=iter(turns)),
        tools=[add_tool("schedules", ("text",)), *WRITE_TOOLS],
        middleware=[VerifyMiddleware()],
        context_schema=SectionContext,
    )
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    reports = [m.content for m in result["messages"] if m.type == "human" and m.content.startswith("# 검증 결과")]
    assert len(reports) == 2 and "남은 문제가 없습니다" in reports[0]
    assert "## 고칠 것 1개" in reports[1] and '"code": "ITEM_NOT_ADDED"' in reports[1] and '"item": "later"' in reports[1] and "update_item" in reports[1]
    assert [row["id"] for row in draft.items["schedules"]] == ["kept", "later"] and draft.rejected == {} and draft.finished == "고쳐 넣었어요."
    assert len([m for m in result["messages"] if m.type == "ai"]) == 3


def test_an_item_refused_when_added_is_fixed_by_changing_only_the_wrong_fields():
    # 2026-11-07 23건 측정: 거절된 항목을 통째로 다시 보내는 데 출력 토큰의 7%(자격 담당 12%)를 씀. 거절된 항목은 남겨 두고 틀린 칸만 고침
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k != "quoteRefs"}), "id": "apply"}
    turns = [
        AIMessage(content="", tool_calls=[call("add_schedules", items=[schedule])]),
        AIMessage(content="", tool_calls=[call("update_item", section="schedules", item_id="apply", changes={"evidence": ["p9.9"]})]),
        AIMessage(content="", tool_calls=[call("update_item", section="schedules", item_id="apply", changes={"evidence": ["p1.2"]})]),
        AIMessage(content="끝"),
    ]
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    agent = create_agent(ToolCallingFake(messages=iter(turns)), tools=[add_tool("schedules", ("text",)), *WRITE_TOOLS], context_schema=SectionContext)
    result = agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    added, still, fixed = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert added["added"] == [] and added["failed"][0]["id"] == "apply" and "update_item" in added["hint"]
    assert still["error"] == "BAD_ITEM" and "p9.9" in still["errors"][0] and "아직 넣지 않았습니다" in still["message"]
    assert fixed == {"ok": "schedules/apply 고쳐 넣음"}
    assert [row["id"] for row in draft.items["schedules"]] == ["apply"] and draft.items["schedules"][0]["evidence"] == ["p1.2"]
    assert draft.rejected == {} and draft.pending == {}


def test_changing_a_rule_status_clears_the_field_the_new_status_must_leave_empty():
    # 2026-11-07 3건 표본: 조건을 「글로 남김」으로 바꾸며 조건식을 지우지 않아(칸마다 합치므로 앞 값이 남음) 거절 5번, 고치는 차례가 늘어남
    document = parse(TEXT)
    age = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][0].items() if k != "quoteRefs"})
    age = {**age, "evidence": ["p1.2"], "originalText": document.text("p1.2")}
    structured = age["rule"]
    text_only = {"status": "UNSTRUCTURED", "reason": "글로 남겨요."}
    turns = [
        AIMessage(content="", tool_calls=[call("add_eligibility", items=[age, {**age, "id": "later", "evidence": []}])]),
        AIMessage(
            content="",
            tool_calls=[
                call("update_item", section="eligibility", item_id="age", changes={"rule": text_only}),
                call("update_item", section="eligibility", item_id="later", changes={"evidence": ["p1.2"], "rule": {**text_only, "status": "UNSTRUCTURED"}}),
            ],
        ),
        AIMessage(content="", tool_calls=[call("update_item", section="eligibility", item_id="later", changes={"rule": structured})]),
        AIMessage(content="끝"),
    ]
    draft = SectionDraft(("eligibility",))
    context = SectionContext(document=document, draft=draft, documents=("text",))
    agent = create_agent(ToolCallingFake(messages=iter(turns)), tools=[add_tool("eligibility", ("text",)), *WRITE_TOOLS], context_schema=SectionContext)
    result = agent.invoke({"messages": [HumanMessage("자격 담당")]}, context=context)
    answers = [json.loads(m.content) for m in result["messages"] if m.type == "tool"]
    assert (
        answers[1] == {"ok": "eligibility/age 고침"} and answers[2] == {"ok": "eligibility/later 고쳐 넣음"} and answers[3] == {"ok": "eligibility/later 고침"}
    )
    rules = {row["id"]: row["rule"] for row in draft.items["eligibility"]}
    assert rules["age"] == {**text_only, "expression": None}  # 글로 남기면 조건식을 비움
    assert rules["later"]["status"] == "STRUCTURED" and rules["later"]["reason"] is None  # 조건식으로 바꾸면 남김 이유를 비움


def test_the_whole_notice_scope_can_be_left_out_and_defaults_are_filled():
    # 2026-11-07 23건 측정: 넣기 인자 글자의 35~47%(서류·안내·일정·선정)가 공고 전체 범위를 그대로 적은 scope
    item = typed_item_schema("requiredDocuments", ("text",))
    assert "scope" not in item["required"] and {"supplyCategory", "resolution"}.isdisjoint(item["properties"]["scope"]["required"])
    # 2026-11-07 3건 표본: 「모든 공급」 문구 뒤 공급 묶음 id 없이 SUPPLY_GROUP으로 적어 거절 5번(이전 38건 0) → 대상만 다르면 NOTICE + targetGroups
    assert "targetGroups만" in item["properties"]["scope"]["description"]
    schedule = {**sparse({k: v for k, v in ai_part(example("housing"))["schedules"][0].items() if k not in ("quoteRefs", "scope")}), "evidence": ["p1.2"]}
    youth = {"level": "NOTICE", "targetGroups": ["청년"], "description": "청년에게 적용돼요."}
    draft = SectionDraft(("schedules",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    turn = AIMessage(content="", tool_calls=[call("add_schedules", items=[{**schedule, "id": "all"}, {**schedule, "id": "youth", "scope": youth}])])
    agent = create_agent(
        ToolCallingFake(messages=iter([turn, AIMessage(content="끝")])), tools=[add_tool("schedules", ("text",)), *WRITE_TOOLS], context_schema=SectionContext
    )
    agent.invoke({"messages": [HumanMessage("일정 담당")]}, context=context)
    whole, partial = draft.items["schedules"]
    assert whole["scope"] == NOTICE_SCOPE
    assert partial["scope"] == {**youth, "supplyCategory": "ALL", "resolution": "RESOLVED"}


def test_an_item_citing_only_in_its_parts_is_told_to_fill_its_own_evidence_with_what_the_parts_cite():
    # 2026-11-06 5건 재측정 bmc-106: 조건식·예외에만 근거를 붙이고 항목 자체 evidence를 비운 성년·무주택·소득·자산·자동차 기준이
    # 「근거 id를 1개 이상 붙입니다」만 두 번 받고 거절된 채 끝남
    age = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][0].items() if k != "quoteRefs"})
    age["rule"]["expression"]["evidence"] = ["p1.2"]
    draft = SectionDraft(("eligibility",))
    context = SectionContext(document=parse(TEXT), draft=draft, documents=("text",))
    turn = AIMessage(content="", tool_calls=[call("add_eligibility", items=[age])])
    agent = create_agent(
        ToolCallingFake(messages=iter([turn, AIMessage(content="끝")])), tools=[add_tool("eligibility", ("text",)), *WRITE_TOOLS], context_schema=SectionContext
    )
    result = agent.invoke({"messages": [HumanMessage("자격 담당")]}, context=context)
    failed = json.loads(next(m.content for m in result["messages"] if m.type == "tool"))["failed"]
    assert failed[0]["id"] == "age" and "항목 자체의 evidence" in failed[0]["errors"][0] and "하위 칸에 붙인 근거: p1.2" in failed[0]["errors"][0]
    assert draft.rejected == {("eligibility", "age"): failed[0]["errors"]}


def test_a_warning_comes_with_how_to_fix_it_from_the_common_rules():
    # 2026-11-06 23건 측정: 출생자녀 수에 따라 한도가 달라지는 자산 기준을 「하나의 조건식으로 표현할 수 없다」며 글로만 남기고 경고도 넘김
    draft = SectionDraft(("eligibility",), items={"eligibility": [{"id": "a"}]})
    issue = {"code": "CRITERION_NOT_STRUCTURED", "target": "/eligibility/0", "item": "a", "description": "기준값 「24,500 )만원 이하」"}
    shown = verify_report(draft, [issue, {**issue, "target": "/eligibility/1", "item": "b"}])
    assert shown.index("## 확인할 것 2개") < shown.index("## 고치는 법") and shown.count("- CRITERION_NOT_STRUCTURED:") == 1
    assert "exceptions(REPLACE" in shown and "그대로 둡니다" in shown
    assert "## 고치는 법" not in verify_report(draft, [{**issue, "code": "EXCEPTION_SUSPECTED"}])
    scoped = verify_report(draft, [{**issue, "code": "DEFINITION_SCOPE_SUSPECTED"}])  # 낱말 정의로 만든 조건의 대상(2026-11-06 dcco-24812)
    assert "## 확인할 것 1개" in scoped and "- DEFINITION_SCOPE_SUSPECTED:" in scoped and "scope.targetGroups" in scoped


def test_criteria_table_rows_left_out_reach_the_eligibility_agent_as_a_check_with_how_to():
    # 2026-11-07 23건 원인 분석: 기준표 행 누락은 화면 메모(자격 섹션을 막지 않음)지만 자격 담당은 고치는 법과 함께 받아야 합니다
    code, target = "CRITERIA_TABLE_OMISSION_SUSPECTED", "/quality/coverage/eligibility"
    assert code in section.LOST_VALUE_NOTES and section._belongs(target, "eligibility") and not section._belongs(target, "requiredDocuments")
    draft = SectionDraft(("eligibility",), items={"eligibility": [{"id": "a"}]})
    shown = verify_report(draft, [{"code": code, "target": target, "description": "원문 자격 기준표 2행의 기준값 119,000,000원"}])
    assert "## 확인할 것 1개" in shown and f"- {code}:" in shown and "행마다 exceptions(REPLACE" in shown


def test_a_lower_bound_in_eligibility_reaches_the_agent_as_a_check_with_how_to():
    # 2026-11-07 유료 확인 jbdc-16011: 「(2단계) … 130% 초과 200% 이하 * 1단계 낙첨자를 포함」을 자격 하한으로 옮김
    draft = SectionDraft(("eligibility",), items={"eligibility": [{"id": "a"}]})
    issue = {"code": "LOWER_BOUND_IN_ELIGIBILITY", "target": "/eligibility/0", "item": "a", "description": "자격 기준에 하한(130% 초과)이 있습니다."}
    shown = verify_report(draft, [issue])
    assert "## 확인할 것 1개" in shown and "- LOWER_BOUND_IN_ELIGIBILITY:" in shown and "낙첨자" in shown and "그대로 둡니다" in shown


def test_the_resolver_rewrites_only_warned_items_and_its_draft_is_used_only_when_verification_improves(monkeypatch):
    # 4단계 해결 에이전트(2026-11-07 23건 재조립: 남은 검토 이슈의 절반이 담당이 경고를 받고도 글로 남긴 자격 기준)
    age = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][0].items() if k != "quoteRefs"})
    document = parse(TEXT)
    structured = age["rule"]
    text_only = {**age, "rule": {"status": "UNSTRUCTURED", "reason": "글로 남겨요.", "expression": None}, "evidence": ["p1.2"]}
    text_only["originalText"] = document.text("p1.2")
    other = {**text_only, "id": "other"}  # 경고 없는 항목

    def issues(spec, draft, state, rt, documents):
        rows = draft.items["eligibility"]
        return [
            {"code": "CRITERION_NOT_STRUCTURED", "target": f"/eligibility/{i}/rule", "item": row["id"], "description": "조건식 없이 글로만 남겼습니다."}
            for i, row in enumerate(rows)
            if row["id"] == "age" and row["rule"]["status"] == "UNSTRUCTURED"
        ]

    def resolve_with(*calls):
        turns = iter([AIMessage(content="", tool_calls=[*calls, call("finish", summary="봤어요.")])])
        tools_ = [add_tool("eligibility", ("text",)), *WRITE_TOOLS]
        monkeypatch.setattr(
            section,
            "_agent",
            lambda model, name, state, documents, middleware: create_agent(
                ToolCallingFake(messages=turns), tools=tools_, middleware=middleware, context_schema=SectionContext
            ),
        )
        draft = SectionDraft(("eligibility",), items={"eligibility": [dict(text_only), dict(other)]})
        spec = SimpleNamespace(name="eligibility", sections=("eligibility",), max_output_tokens=1000)
        rt = SimpleNamespace(models=SimpleNamespace(budget=None))
        resolved, record = section._resolve(spec, draft, {"document": document}, rt, ("text",), lambda name, max_output_tokens=None: None, [])
        return draft, resolved, record

    monkeypatch.setattr(section, "_issues", issues)
    draft, resolved, record = resolve_with(call("update_item", section="eligibility", item_id="age", changes={"rule": {**structured, "reason": None}}))
    assert record["adopted"] and (record["targets"], record["before"], record["after"]) == (1, 1, 0)
    assert resolved.items["eligibility"][0]["rule"] == {**structured, "reason": None} and draft.items["eligibility"][0]["rule"]["status"] == "UNSTRUCTURED"
    draft, resolved, record = resolve_with(call("remove_item", section="eligibility", item_id="age"))  # 경고를 없애려고 뺌
    assert resolved is None and record["adopted"] is False
    draft, resolved, record = resolve_with(  # 경고 없는 항목까지 바꿈
        call("update_item", section="eligibility", item_id="age", changes={"rule": {**structured, "reason": None}}),
        call("update_item", section="eligibility", item_id="other", changes={"description": "바꿨어요."}),
    )
    assert resolved is None and record["adopted"] is False
    monkeypatch.setattr(section, "_issues", lambda *args: [])
    assert resolve_with() == (resolve_with()[0], None, {})  # 경고가 없으면 부르지 않음


def test_the_resolver_looks_at_each_warned_item_in_its_own_conversation_at_the_same_time(monkeypatch):
    # 2026-11-07 3건 표본 dcco-24812: 경고 항목 3개를 한 대화에서 고쳐 첫 차례 출력 8천 토큰·55초, 모두 112초가 자격 담당 뒤에 더해짐.
    # 항목마다 따로 동시에 보고, 항목마다 고른 결과만 합침(한 항목의 해결 담당이 경고를 없애려고 항목을 빼도 다른 항목의 고침은 씀)
    age = sparse({k: v for k, v in ai_part(example("housing"))["eligibility"][0].items() if k != "quoteRefs"})
    document = parse(TEXT)
    text_only = {**age, "rule": {"status": "UNSTRUCTURED", "reason": "글로 남겨요.", "expression": None}, "evidence": ["p1.2"]}
    text_only["originalText"] = document.text("p1.2")

    def issues(spec, draft, state, rt, documents):
        return [
            {"code": "CRITERION_NOT_STRUCTURED", "target": f"/eligibility/{i}/rule", "item": row["id"], "description": "조건식 없이 글로만 남겼습니다."}
            for i, row in enumerate(draft.items["eligibility"])
            if row["rule"]["status"] == "UNSTRUCTURED"
        ]

    replies = {
        "age": [call("update_item", section="eligibility", item_id="age", changes={"rule": {**age["rule"], "reason": None}})],
        "age2": [call("remove_item", section="eligibility", item_id="age2")],
    }

    class ByItem(ToolCallingFake):
        """해결 담당 과제 글에 든 항목 id로 답을 고르는 가짜 모델(동시에 도는 대화마다 다른 답)."""

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            task = next(str(m.content) for m in messages if isinstance(m, HumanMessage) and "해결 담당" in str(m.content))
            item = next(item for item in replies if f'"id": "{item}"' in task)
            reply = AIMessage(content="", tool_calls=[*replies[item], call("finish", summary="봤어요.")])
            return ChatResult(generations=[ChatGeneration(message=reply)])

    conversations = []

    def agent(model, name, state, documents, middleware):
        conversations.append(name)
        tools_ = [add_tool("eligibility", ("text",)), *WRITE_TOOLS]
        return create_agent(ByItem(messages=iter([])), tools=tools_, middleware=middleware, context_schema=SectionContext)

    monkeypatch.setattr(section, "_agent", agent)
    monkeypatch.setattr(section, "_issues", issues)
    draft = SectionDraft(("eligibility",), items={"eligibility": [dict(text_only), {**text_only, "id": "age2"}]})
    spec = SimpleNamespace(name="eligibility", sections=("eligibility",), max_output_tokens=1000)
    rt = SimpleNamespace(models=SimpleNamespace(budget=None))
    resolved, record = section._resolve(spec, draft, {"document": document}, rt, ("text",), lambda name, max_output_tokens=None: None, [])
    assert conversations == ["resolver", "resolver"]  # 항목마다 새 대화
    assert record["adopted"] and (record["targets"], record["before"], record["after"]) == (2, 2, 1)
    assert {item: run["adopted"] for item, run in record["items"].items()} == {"age": True, "age2": False}
    assert [(row["id"], row["rule"]["status"]) for row in resolved.items["eligibility"]] == [("age", "STRUCTURED"), ("age2", "UNSTRUCTURED")]
    assert [row["rule"]["status"] for row in draft.items["eligibility"]] == ["UNSTRUCTURED", "UNSTRUCTURED"]  # 담당 초안은 그대로
