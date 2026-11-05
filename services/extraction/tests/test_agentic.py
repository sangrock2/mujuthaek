"""에이전트 방식 추출(EXTRACTION_ENGINE=agent): 녹화한 차례로 총괄·하위 에이전트 흐름, 결정 적용, 상한을 확인합니다. 유료 호출 없음."""

import copy
import json

from events import raw_event
from test_pipeline import answers, run
from test_repair_agent import turn

from mujuthaek_extraction.agentic.agents import Decision
from mujuthaek_extraction.agentic.engine import ACCEPTED, HELD, apply_decision
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.model.factory import NoticeModels
from mujuthaek_extraction.verify import VerificationReport

WORKERS = ("structure", "schedules", "eligibility", "selection", "documents")


def supervisor(*steps):
    return {f"agentic:supervisor:turn{n}": [t] for n, t in enumerate(steps, start=1)}


def worker(name, *steps):
    return {f"agentic:{name}:turn{n}": [t] for n, t in enumerate(steps, start=1)}


def full_script(finish=None):
    calls = dict(answers())
    steps = [turn("outline")] + [turn("delegate", worker=w, brief="처음 뽑기") for w in WORKERS]
    steps += [turn("check_all"), finish or turn("finish", accept=[], hold=[], note="")]
    calls.update(supervisor(*steps))
    for name in WORKERS:
        calls.update(worker(name, turn("extract_section"), turn("done", summary=f"{name} 뽑음")))
    return calls


def run_agentic(monkeypatch, calls):
    monkeypatch.setenv("EXTRACTION_ENGINE", "agent")
    model = RecordedModel(calls, "gpt")
    return run(raw_event(), NoticeModels(model, None, names={"primary": "gpt"})), model


def test_supervisor_delegates_sections_and_the_notice_is_published(monkeypatch):
    outcome, model = run_agentic(monkeypatch, full_script())
    assert outcome.status == "COMPLETED" and tools().validate(outcome.event, "events/extraction.completed.v1.json") == []
    record = outcome.usage["agentic"]
    assert [a["name"] for a in record["agents"]] == ["supervisor", *(f"worker:{w}" for w in WORKERS)]
    assert record["agents"][0]["steps"] == ["outline", *["delegate"] * 5, "check_all", "finish"] and record["agents"][0]["outcome"] == "DONE"
    # 기존 섹션 추출기는 하위 에이전트가 고른 도구로만 불림
    assert [r.call_name for r in model.requests if not r.call_name.startswith("agentic:")] == list(WORKERS)


def test_worker_needs_structure_first_and_rejects_quotes_not_in_source(monkeypatch):
    calls = dict(answers())
    calls.update(supervisor(turn("delegate", worker="eligibility", brief="먼저"), turn("finish", accept=[], hold=[], note="")))
    item = json.dumps({"id": "x1"})
    calls.update(
        worker(
            "eligibility",
            turn("extract_section"),
            turn("upsert_item", section="eligibility", item_json=item, quotes=[{"ref": "q1", "text": "원문에 없는 글"}]),
            turn("done", summary="구조 없음"),
        )
    )
    outcome, model = run_agentic(monkeypatch, calls)
    results = [json.loads(r.turns[-1].results[0]) for r in model.requests if r.call_name.startswith("agentic:eligibility:turn") and r.turns]
    assert results[0]["error"] == "NO_STRUCTURE" and results[1]["error"] == "QUOTE_NOT_FOUND"
    assert outcome.status == "FAILED"  # 구조가 없어 결합하지 못함


def test_last_supervisor_turn_must_finish(monkeypatch):
    monkeypatch.setenv("EXTRACTION_AGENTIC_SUPERVISOR_TURNS", "2")
    calls = dict(answers())
    calls.update(supervisor(turn("outline"), turn("finish", accept=[], hold=[], note="")))
    _, model = run_agentic(monkeypatch, calls)
    last = [r for r in model.requests if r.call_name.startswith("agentic:supervisor")][-1]
    assert last.forced_tool == "finish" and last.tools == model.requests[0].tools


def report_with(issue):
    outcome = run(raw_event(), NoticeModels(RecordedModel(answers(), "local"), None, names={"primary": "local"}))
    candidate = copy.deepcopy(outcome.candidate)
    candidate["quality"]["reviewIssues"] = [issue]
    candidate["quality"]["verification"].update(status="PARTIALLY_PASSED", sourceStatus="REVIEW_REQUIRED")
    return VerificationReport(candidate=candidate, findings=[], contract_errors=[])


def test_accepted_issue_becomes_a_note_and_the_notice_passes():
    issue = {"code": "EVIDENCE_AMBIGUOUS", "target": "/schedules/0", "description": "근거가 여러 곳"}
    report = report_with(issue)
    applied = apply_decision(report, Decision(accept=[{"code": issue["code"], "target": issue["target"], "reason": "1쪽 접수 기간 표로 확인"}]))
    quality = report.candidate["quality"]
    assert applied["accepted"] == [{"code": issue["code"], "target": issue["target"]}] and quality["reviewIssues"] == []
    assert quality["verification"]["status"] == "PASSED" and any(n["code"] == ACCEPTED and "1쪽" in n["description"] for n in quality["notes"])


def test_held_target_is_kept_for_review_and_unknown_accepts_are_reported():
    report = report_with({"code": "EVIDENCE_AMBIGUOUS", "target": "/schedules/0", "description": "근거가 여러 곳"})
    decision = Decision(accept=[{"code": "X", "target": "/nowhere", "reason": "?"}], hold=[{"target": "/eligibility/0", "reason": "예외 확인 필요"}])
    applied = apply_decision(report, decision)
    quality = report.candidate["quality"]
    assert applied["unmatched"] == [{"code": "X", "target": "/nowhere"}] and applied["held"] == ["/eligibility/0"]
    assert {i["code"] for i in quality["reviewIssues"]} == {"EVIDENCE_AMBIGUOUS", HELD}
    assert quality["verification"]["status"] == "PARTIALLY_PASSED" and {h["target"] for h in quality["heldItems"]} == {"/schedules/0", "/eligibility/0"}


def test_structure_parts_from_code_tables_are_kept_together():
    # 2026-11-05 첫 유료 실행: 구조 추출이 낸 두 조각(공고·위치 + 코드가 표에서 옮긴 공급) 중 첫 조각만 초안에 넣어 공급 묶음이 모두 빠짐
    from mujuthaek_extraction.agentic.draft import Draft

    draft = Draft({"notice": "structure", "locations": "structure", "supplyGroups": "structure"}, "text")
    draft.put_parts("structure", [{"quotes": [], "notice": {"title": "t"}, "locations": []}, {"quotes": [], "supplyGroups": [{"id": "g1"}]}])
    assert draft.summary(("supplyGroups",))["supplyGroups"]["ids"] == ["g1"] and len(draft.as_parts()) == 2
    assert draft.as_parts()[0]["notice"] == {"title": "t"} and draft.item("supplyGroups", "g1") == {"id": "g1"}


def test_item_in_wrong_format_is_returned_before_it_enters_the_draft(monkeypatch):
    calls = full_script()
    bad = json.dumps({"id": "x1", "itemKind": "NOT_A_KIND"})
    calls.update(worker("structure", turn("extract_section"), turn("upsert_item", section="supplyGroups", item_json=bad, quotes=[]), turn("done", summary="")))
    _, model = run_agentic(monkeypatch, calls)
    result = json.loads(next(r for r in model.requests if r.call_name == "agentic:structure:turn3").turns[-1].results[0])
    assert result["error"] == "BAD_FORMAT" and result["errors"]


def test_hold_locations_written_loosely_are_normalized_or_dropped():
    report = report_with({"code": "EVIDENCE_AMBIGUOUS", "target": "/schedules/0", "description": "근거가 여러 곳"})
    holds = [{"target": "eligibility", "reason": "a"}, {"target": "/selectionRules 순위 인용", "reason": "b"}, {"target": "schedules/guidance", "reason": "c"}]
    applied = apply_decision(report, Decision(hold=holds))
    assert applied["held"] == ["/eligibility", "/selectionRules"] and applied["unmatchedHolds"] == ["schedules/guidance"]
    assert tools().validate(report.candidate, "schemas/extracted-notice.v1.json") == []


def test_agent_cannot_accept_a_disputed_image_reading():
    # 원문 그림과 맞춰야 하는 문제인데 에이전트는 옮긴 글자만 봅니다
    issue = {"code": "IMAGE_READING_DISAGREES", "target": "/schedules/0", "description": "두 판독이 다름"}
    report = report_with(issue)
    applied = apply_decision(report, Decision(accept=[{"code": issue["code"], "target": issue["target"], "reason": "확인함"}]))
    assert applied["refused"] == [{"code": issue["code"], "target": issue["target"]}] and report.candidate["quality"]["reviewIssues"] == [issue]


def test_independent_workers_run_together_after_structure(monkeypatch):
    calls = dict(answers())
    rest = ("schedules", "eligibility", "selection", "documents")
    many = turn("delegate_many", tasks=[{"worker": w, "brief": "처음 뽑기"} for w in rest])
    early = turn("delegate_many", tasks=[{"worker": "schedules", "brief": "구조 전"}])
    calls.update(supervisor(early, turn("delegate", worker="structure", brief="처음"), many, turn("finish", accept=[], hold=[], note="")))
    for name in ("structure", *rest):
        calls.update(worker(name, turn("extract_section"), turn("done", summary=name)))
    outcome, model = run_agentic(monkeypatch, calls)
    first = json.loads(next(r for r in model.requests if r.call_name == "agentic:supervisor:turn2").turns[-1].results[0])
    assert first["error"] == "NO_STRUCTURE" and outcome.status == "COMPLETED"
    assert sorted(a["name"] for a in outcome.usage["agentic"]["agents"]) == sorted(["supervisor", *(f"worker:{w}" for w in ("structure", *rest))])


def test_long_delegation_results_are_kept_not_replaced_by_an_error(monkeypatch):
    # 2026-11-05 gh-809: 동시에 맡긴 담당 넷의 결과가 길다는 오류로 버려져 같은 일을 다시 맡김
    calls = dict(answers())
    rest = ("schedules", "eligibility", "selection", "documents")
    calls.update(
        supervisor(
            turn("delegate", worker="structure", brief="처음"),
            turn("delegate_many", tasks=[{"worker": w, "brief": "처음"} for w in rest]),
            turn("finish", accept=[], hold=[], note=""),
        )
    )
    for name in ("structure", *rest):
        calls.update(worker(name, turn("extract_section"), turn("done", summary="가" * 3_000)))
    _, model = run_agentic(monkeypatch, calls)
    result = json.loads(next(r for r in model.requests if r.call_name == "agentic:supervisor:turn3").turns[-1].results[0])
    assert len(result["results"]) == 4 and all(len(r["summary"]) <= 700 and isinstance(r["draft"], dict) for r in result["results"])


def test_extract_all_fills_every_worker_like_the_fixed_flow_and_workers_get_the_issues_up_front(monkeypatch):
    calls = dict(answers())
    calls.update(
        supervisor(
            turn("extract_all"), turn("check_all"), turn("delegate", worker="selection", brief="문제 고치기"), turn("finish", accept=[], hold=[], note="")
        )
    )
    calls.update(worker("selection", turn("done", summary="고칠 것 없음")))
    outcome, model = run_agentic(monkeypatch, calls)
    assert outcome.status == "COMPLETED"
    # 기존 흐름과 같은 호출로 뽑아(test_pipeline과 같은 호출 목록) 담당별로 초안에 넣음
    assert [r.call_name for r in model.requests if not r.call_name.startswith("agentic:")] == list(WORKERS)
    first = next(r for r in model.requests if r.call_name == "agentic:selection:turn1")
    assert "남은 문제" in json.loads(first.user) and "outline" not in {t.name for t in first.tools}
    assert "원문 차례" in json.loads(next(r for r in model.requests if r.call_name == "agentic:supervisor:turn1").user)


def test_part_with_several_workers_sections_is_split_by_owner():
    from mujuthaek_extraction.agentic.draft import split_by_owner

    owners = {"eligibility": "eligibility", "selectionRules": "selection", "requiredDocuments": "documents"}
    part = {
        "quotes": [{"ref": "q1"}],
        "eligibility": [{"id": "e"}],
        "selectionRules": [{"id": "s"}],
        "requiredDocuments": [],
        "coverage": {"eligibility": {"status": "EXTRACTED"}, "selectionRules": {"status": "PARTIAL"}, "requiredDocuments": {"status": "NOT_IN_SOURCE"}},
        "missingFields": [{"target": "/selectionRules/0/points"}],
    }
    pieces = split_by_owner(part, owners)
    assert set(pieces) == {"eligibility", "selection", "documents"} and pieces["selection"]["selectionRules"] == [{"id": "s"}]
    assert "eligibility" not in pieces["selection"] and pieces["selection"]["quotes"] == [{"ref": "q1"}]
    assert pieces["selection"]["missingFields"] == [{"target": "/selectionRules/0/points"}] and pieces["eligibility"]["missingFields"] == []


def test_tool_results_carry_progress_and_extract_all_skips_what_is_already_drafted(monkeypatch):
    # 2026-11-05 jbdc: 담당이 각자 뽑은 뒤 총괄이 extract_all을 또 불러 같은 추출을 두 번 — 순서를 정해 주는 대신 진행 사실을 알림
    calls = dict(answers())
    steps = [turn("delegate", worker="structure", brief="처음"), turn("extract_all"), turn("extract_all"), turn("finish", accept=[], hold=[], note="")]
    calls.update(supervisor(*steps))
    calls.update(worker("structure", turn("extract_section"), turn("done", summary="구조")))
    outcome, model = run_agentic(monkeypatch, calls)
    second = json.loads(next(r for r in model.requests if r.call_name == "agentic:supervisor:turn3").turns[-1].results[0])
    third = json.loads(next(r for r in model.requests if r.call_name == "agentic:supervisor:turn4").turns[-1].results[0])
    assert second["skipped"] == ["structure"] and second["extracted"] == ["schedules", "eligibility", "selection", "documents"]
    assert "모든 섹션이 이미" in third["message"] and "progress" in third and "extractedWorkers" in third["progress"]
    # 구조 호출은 한 번만(두 번째 extract_all은 구조 요약을 받아 나머지만)
    assert [r.call_name for r in model.requests if not r.call_name.startswith("agentic:")] == list(WORKERS) and outcome.status == "COMPLETED"


# ── 2026-11-05 점검으로 찾은 결함(유료 실행 없이 재현) ──────────────────────────────────────────


def bare_env(extract=None):
    """도구 단위 시험용 공유 상태(모델 호출 없음)."""
    from helpers import example, source_for

    from mujuthaek_extraction.agentic.agents import Env, workers_of
    from mujuthaek_extraction.agentic.draft import Draft
    from mujuthaek_extraction.extract import ExtractionRun
    from mujuthaek_extraction.rules.housing_notice import RULES

    source = source_for("housing", example("housing"))
    workers = workers_of(RULES)
    owners = {s: name for name, spec in workers.items() for s in spec.sections}
    return Env(
        rules=RULES,
        material=source.material,
        context=source.context,
        model=RecordedModel({}),
        evaluate=lambda parts: None,
        read_images=lambda m, c: (m, c, None),
        extract_all=extract or (lambda calls, structure: ExtractionRun()),
        workers=workers,
        draft=Draft(owners, source.material.text_document_id),
    )


def test_extract_all_does_not_overwrite_a_section_a_worker_already_fixed():
    # 합쳐진 호출(작은 공고의 자격·선정·서류 한 호출)을 다시 돌려도 이미 있던 담당 몫은 그대로
    from mujuthaek_extraction.agentic.agents import SupervisorTools
    from mujuthaek_extraction.extract import ExtractionRun

    combined = {"quotes": [], "eligibility": [{"id": "new-e"}], "selectionRules": [{"id": "new-s"}], "requiredDocuments": [], "coverage": {}}
    env = bare_env(lambda calls, structure: ExtractionRun(parts=[combined]))
    env.draft.put_parts("selection", [{"quotes": [], "selectionRules": [{"id": "fixed-by-worker"}], "coverage": {}}])
    SupervisorTools(env)._extract_all()
    assert env.draft.summary(("selectionRules",))["selectionRules"]["ids"] == ["fixed-by-worker"]
    assert env.draft.summary(("eligibility",))["eligibility"]["ids"] == ["new-e"]


def test_draft_can_be_read_while_other_workers_write():
    import threading

    env = bare_env()
    errors = []

    def write():
        for n in range(300):
            env.draft.put_parts(f"w{n}", [{"quotes": [], "schedules": [{"id": str(n)}]}])

    def read():
        try:
            for _ in range(300):
                env.draft.as_parts()
                env.draft.summary()
        except RuntimeError as error:  # dictionary changed size during iteration
            errors.append(error)

    threads = [threading.Thread(target=write), threading.Thread(target=read), threading.Thread(target=read)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_bad_tool_input_is_returned_as_an_error_not_a_crash():
    from mujuthaek_extraction.agentic.agents import SupervisorTools
    from mujuthaek_extraction.model.base import ToolCall

    tools_ = SupervisorTools(bare_env())
    result = json.loads(tools_.run(ToolCall("c", "read_page", json.dumps({"page": "첫쪽", "from_char": "처음"}))))
    assert result["error"] in ("TOOL_ERROR", "NO_PAGES", "NO_SUCH_PAGE")
    result = json.loads(tools_.run(ToolCall("c", "search_source", json.dumps({"query": "무주택", "limit": "다섯"}))))
    assert result["error"] == "TOOL_ERROR"


def test_transient_error_in_an_agent_turn_is_retried():
    from mujuthaek_extraction.agentic.loop import AgentLog, run_loop
    from mujuthaek_extraction.extract import ExtractionRun
    from mujuthaek_extraction.model import ModelError, ModelRequest

    class Box:
        specs, finish_tool, done = (), "done", False

        def run(self, call):
            self.done = True
            return json.dumps({"received": True})

    model = RecordedModel({"agentic:x:turn1": [ModelError("429", transient=True), turn("done", summary="")]})
    base = ModelRequest("v", "agentic:x", "s", "u", "i", {"type": "object"}, 100)
    log, waits = AgentLog("x"), []
    run_loop(model, base, Box(), 3, ExtractionRun(), log, sleep=waits.append)
    assert log.outcome == "DONE" and len(waits) == 1


def test_workers_see_section_level_issues():
    from mujuthaek_extraction.agentic.agents import _issue_section

    candidate = {"quality": {"missingFields": [{"target": "/supplyGroups/2/prices/0/amountKrw"}]}}
    assert _issue_section(candidate, "/quality/coverage/supplyGroups") == "supplyGroups"
    assert _issue_section(candidate, "/quality/missingFields/0") == "supplyGroups"
    assert _issue_section(candidate, "/eligibility/3/rule") == "eligibility"


def test_upsert_pointing_at_a_quote_that_does_not_exist_is_returned(monkeypatch):
    calls = full_script()
    bad = json.dumps({"id": "sch-x", "quoteRefs": ["nowhere"]})
    calls.update(worker("schedules", turn("extract_section"), turn("upsert_item", section="schedules", item_json=bad, quotes=[]), turn("done", summary="")))
    _, model = run_agentic(monkeypatch, calls)
    result = json.loads(next(r for r in model.requests if r.call_name == "agentic:schedules:turn3").turns[-1].results[0])
    assert result["error"] in ("UNKNOWN_QUOTE_REF", "BAD_FORMAT")


def test_items_pointing_at_ids_that_disappear_are_listed():
    env = bare_env()
    env.draft.put_parts("structure", [{"quotes": [], "notice": {}, "locations": [{"id": "loc-1"}], "supplyGroups": [{"id": "g-1"}]}])
    env.draft.put_parts("eligibility", [{"quotes": [], "eligibility": [{"id": "e1", "scope": {"supplyGroupIds": ["g-1"], "locationIds": []}}]}])
    assert env.draft.referencing({"g-1"}, "structure") == ["eligibility/e1"] and env.draft.structure_ids() == {"loc-1", "g-1"}


def test_model_without_tools_or_an_agent_crash_falls_back_to_the_fixed_flow(monkeypatch):
    import mujuthaek_extraction.agentic.agents as agents

    class NoTools(RecordedModel):
        supports_tools = False

    monkeypatch.setenv("EXTRACTION_ENGINE", "agent")
    outcome = run(raw_event(), NoticeModels(NoTools(answers(), "local"), None, names={"primary": "local"}))
    assert outcome.status == "COMPLETED" and "도구" in outcome.usage["agenticFallback"]

    def broken(env):
        raise RuntimeError("bug")

    monkeypatch.setattr(agents, "run_supervisor", broken)
    import mujuthaek_extraction.graph.agentic as agentic_graph

    monkeypatch.setattr(agentic_graph, "run_supervisor", broken)
    outcome = run(raw_event(), NoticeModels(RecordedModel(answers(), "gpt"), None, names={"primary": "gpt"}))
    assert outcome.status == "COMPLETED" and "RuntimeError" in outcome.usage["agenticFallback"]
