"""에이전트 방식 추출(EXTRACTION_ENGINE=agent): 입력 해석 → 총괄 에이전트(하위 에이전트에 섹션을 맡김) → 마무리 → 발행.

마무리는 코드입니다: 초안을 결합·검증하고(계약 오류는 지금처럼 그 항목만 정리), 총괄 에이전트의 결정을 적용합니다.
- accept: 검증기 문제 중 에이전트가 원문으로 확인해 받아들인 것 → 검수 문제에서 빼고 메모(AGENT_ACCEPTED)로 남김(그 값은 게시)
- hold: 에이전트가 보류로 지정한 위치 → 검수 문제(AGENT_HOLD)로 더함
검증기가 처음 낸 문제 목록은 작업 기록(usage.agentic.verifierIssues)에 남겨, 에이전트가 받아들인 값이 맞았는지 평가에서 대조합니다.
계약 형식(스키마)을 어기는 결과는 받아들일 수 없어 지금처럼 검수·실패로 갑니다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.agentic.agents import Decision, Env, workers_of
from mujuthaek_extraction.agentic.draft import Draft
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.extract import ExtractionRun, run_extraction
from mujuthaek_extraction.recheck import RecheckResult
from mujuthaek_extraction.rules.base import FieldRules
from mujuthaek_extraction.verify import VerificationReport
from mujuthaek_extraction.verify.verifier import API_OK, SCHEMA, _incomplete, held_target, hold_plan

ACCEPTED = "AGENT_ACCEPTED"
HELD = "AGENT_HOLD"
# 에이전트가 받아들일 수 없는 문제: 원문 그림과 맞춰야 하는데 에이전트는 옮긴 글자만 봅니다(같은 글자를 다시 봐도 판독 오류를 가려낼 수 없음)
UNACCEPTABLE = frozenset({"IMAGE_READING_DISAGREES"})


def make_env(rules: FieldRules, intake: Any, rt: pipeline.Runtime) -> Env:
    workers = workers_of(rules)
    owners = {section: name for name, spec in workers.items() for section in spec.sections}
    env = Env(
        rules=rules,
        material=intake.material,
        context=intake.context,
        model=rt.models.primary,
        evaluate=lambda parts: None,
        read_images=lambda material, context: pipeline.read_images(material, context, rt),
        extract_all=lambda calls, structure: ExtractionRun(),
        workers=workers,
        draft=Draft(owners, intake.material.text_document_id),
        stagger=rt.parallel_stagger,
    )
    env.evaluate = lambda parts: pipeline.evaluate_parts(parts, env.material, env.context, rt)

    # 지금 흐름과 같은 호출(작은 공고는 자격·선정·서류를 한 호출로). 여러 담당 섹션을 담은 조각은 extract_all이 담당별로 나눔
    def extract_all(calls: tuple[Any, ...], structure: dict[str, Any] | None) -> ExtractionRun:
        chosen = dataclasses.replace(rules, calls=calls, split_calls=(), large_text_chars=None)
        return run_extraction(chosen, env.material, env.model, structure=structure, usage=rt.usage, parallel=rt.parallel_calls, stagger=rt.parallel_stagger)

    def progress() -> dict[str, Any]:
        budget = rt.models.budget
        facts: dict[str, Any] = {"extractedWorkers": sorted(env.draft.parts)}
        if budget is not None:
            facts.update(spentUsd=round(budget.spent_usd, 4), budgetLeftUsd=round(budget.limit_usd - budget.spent_usd, 4))
        return facts

    env.extract_all, env.progress = extract_all, progress
    return env


def apply_decision(report: VerificationReport, decision: Decision | None) -> dict[str, Any]:
    """총괄 에이전트의 결정을 후보에 적용하고 검증 상태를 다시 정합니다. 적용 기록을 돌려줍니다."""
    candidate, record = report.candidate, {"accepted": [], "held": [], "unmatched": []}
    if decision is None or not (decision.accept or decision.hold):
        return record
    quality = candidate["quality"]
    wanted = {(a["code"], a["target"]): a["reason"] for a in decision.accept}
    kept = []
    for issue in quality["reviewIssues"]:
        reason = wanted.pop((issue["code"], issue["target"]), None)
        if reason is not None and issue["code"] in UNACCEPTABLE:
            record.setdefault("refused", []).append({"code": issue["code"], "target": issue["target"]})
            reason = None
        if reason is None:
            kept.append(issue)
            continue
        description = f"{issue['code']} — 에이전트가 원문으로 확인: {reason} (검증기: {issue['description']})"
        quality["notes"].append({"code": ACCEPTED, "target": issue["target"], "description": description[:1_000]})
        record["accepted"].append({"code": issue["code"], "target": issue["target"]})
    record["unmatched"] = [{"code": code, "target": target} for code, target in wanted]
    record["unmatchedHolds"] = []
    for hold in decision.hold:
        target = _pointer(candidate, hold["target"])
        if target is None:
            record["unmatchedHolds"].append(hold["target"])
            continue
        kept.append({"code": HELD, "target": target, "description": hold["reason"] or "에이전트가 확인 필요로 지정했습니다."})
        record["held"].append(target)
    quality["reviewIssues"] = kept
    verification = quality["verification"]
    quality.pop("heldItems", None)
    if not report.contract_errors and not [i for i in kept if i["code"] != HELD] and verification["sourceStatus"] != "NOT_RUN":
        verification["sourceStatus"] = "PASSED"  # 남은 근거 문제를 모두 메모로 옮김(계약 정의: notes로 옮기지 않은 V2·V3·V5 문제 없음)
    passed = (
        not report.contract_errors
        and verification["sourceStatus"] == "PASSED"
        and verification["apiComparison"]["status"] in API_OK
        and not kept
        and not any(_incomplete(section, entry["status"]) for section, entry in quality["coverage"].items())
    )
    held = None if passed else hold_plan(candidate, report.contract_errors)
    verification["status"] = "PASSED" if passed else "PARTIALLY_PASSED" if held else "REVIEW_REQUIRED"
    if held:
        quality["heldItems"] = held
    if verification["status"] != "REVIEW_REQUIRED" and (errors := tools().validate(candidate, SCHEMA)):
        verification["status"] = "REVIEW_REQUIRED"
        quality.pop("heldItems", None)
        record["contractErrors"] = errors[:5]
    return record


def _pointer(candidate: dict[str, Any], written: str) -> str | None:
    """에이전트가 적은 보류 위치를 계약 위치로: 첫 낱말만, 앞에 「/」. 후보에 있는 칸이고 보류할 수 있는 곳이어야 합니다.
    (2026-11-05 실측: 「requiredDocuments」「/eligibility 여성 신청 제한 인용」처럼 적어 계약 형식 오류로 공고 전체가 검수로 감)"""
    words = (written or "").strip().split()
    if not words:
        return None
    target = "/" + words[0].strip("/")
    try:
        tools().resolve(candidate, target)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return target if held_target(candidate, target) is not None else None


def conclude(env: Env, raw_event: dict[str, Any], rt: pipeline.Runtime) -> pipeline.Outcome:
    parts = env.draft.as_parts()
    env.run.parts = parts
    extracted = pipeline.Extracted(env.run, None, rt.models.names.get("primary", "primary"), env.model)
    report = pipeline.evaluate_parts(parts, env.material, env.context, rt)
    if report is None:
        _record(env, rt, None, {})
        return pipeline.extraction_failed_outcome(extracted, env.image_run, env.material, rt)
    recheck = RecheckResult(parts, report, [], False, None)
    repairs: list[str] = []
    if report.contract_errors:
        report, actions = pipeline.quarantine_step(report, recheck, env.material, env.context, rt)
        repairs += actions
        pipeline.note_changes(report, extracted, recheck, actions)
    before = [{"code": i["code"], "target": i["target"]} for i in report.candidate["quality"]["reviewIssues"]]
    applied = apply_decision(report, env.decision)
    _record(env, rt, before, applied)
    publication = pipeline.publish_step(report, raw_event, env.material, rt)
    return pipeline.finish(raw_event, report, recheck, publication, extracted, env.image_run, repairs, env.material, rt)


def _record(env: Env, rt: pipeline.Runtime, before: list[dict[str, str]] | None, applied: dict[str, Any]) -> None:
    decision = env.decision
    rt.usage.record(
        "agentic",
        {
            "agents": [log.summary() for log in env.logs],
            "delegations": dict(env.delegations),
            "decision": None if decision is None else {"accept": decision.accept, "hold": decision.hold, "note": decision.note},
            "verifierIssues": before,
            "applied": applied,
        },
    )
