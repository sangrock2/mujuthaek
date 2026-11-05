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
