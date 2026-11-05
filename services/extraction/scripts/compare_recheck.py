"""재확인 전략 비교: 같은 첫 추출 결과 위에서 batch와 agent를 각각 돌립니다 (2026-11-05).

AI 응답은 실행마다 달라, 두 전략을 따로 처음부터 돌리면 재확인 대상부터 달라집니다(첫 비교에서 8개 vs 4개).
그래서 공고마다 첫 추출(그림 판독 포함)을 한 번만 하고 결과를 <out>/<공고>/extraction.pkl에 저장한 뒤,
같은 조각에 전략마다 재확인 → 정리 → 발행 준비를 돌려 <out>/<전략>/<공고>/outcome.json에 씁니다(score_answer_keys.py로 채점).
--reuse를 주면 저장한 첫 추출을 다시 써서 추출 비용 없이 재확인만 다시 돌립니다.

기본은 미리보기(호출 없음). --confirm-spend를 줘야 유료 모델을 부릅니다. 키·응답 원문은 출력하지 않습니다.
  PYTHONPATH="src;scripts" uv run python scripts/compare_recheck.py --board-root <수집 폴더> --board bmc:106 \\
      --out <결과 폴더> --env-file <키 파일> --total-budget-usd 0.5 --confirm-spend
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from archive_cases import board_case
from offline_common import FixedApi

from mujuthaek_extraction import pipeline
from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.extract import ExtractionRun
from mujuthaek_extraction.intake import InMemorySourceReader
from mujuthaek_extraction.model.factory import ModelFactory, NoticeModels
from mujuthaek_extraction.usage import MeteredModel, UsageRecorder
from mujuthaek_platform.events import new_event

STRATEGIES = ("batch", "agent")  # 기본 비교 대상. --strategies로 바꿈(예: batch,agent,hybrid)


def metered(models: NoticeModels, usage: UsageRecorder) -> NoticeModels:
    names = models.names
    primary = MeteredModel(models.primary, usage, names.get("primary", "primary"))
    fallback = MeteredModel(models.fallback, usage, names.get("fallback", "fallback")) if models.fallback is not None else None
    return NoticeModels(primary, fallback, models.budget, names)


def runtime(factory: ModelFactory, reader, regions, api) -> tuple[pipeline.Runtime, UsageRecorder]:
    """운영 워커와 같은 설정(섹션 병렬 호출 수·간격)으로 실행 문맥을 만듭니다."""
    usage = UsageRecorder()
    settings = factory.settings
    rt = pipeline.Runtime(
        metered(factory.for_notice(), usage),
        usage,
        reader,
        regions,
        lambda: datetime.now(UTC),
        new_event,
        api,
        parallel_calls=settings.parallel_calls,
        parallel_stagger=settings.parallel_stagger_seconds,
    )
    return rt, usage


def extract_once(case, factory, regions, folder: Path, reuse: bool) -> dict[str, Any] | None:
    """첫 추출(그림 판독 포함)을 한 번 하고 저장합니다. 저장본이 있고 reuse면 그대로 읽습니다."""
    saved = folder / "extraction.pkl"
    if reuse and saved.exists():
        return pickle.loads(saved.read_bytes())
    reader, api = InMemorySourceReader(files=case.source_files), FixedApi(case.api_reference)
    rt, usage = runtime(factory, reader, regions, api)
    intake = pipeline.read_intake(case.event, "structured", rt)
    if not intake.ready:
        print(f"{case.name}: 입력 해석 {intake.status}")
        return None
    rules = pipeline.RULES_BY_METHOD["structured"][intake.raw.field]
    material, context, _ = pipeline.read_images(intake.material, intake.context, rt)
    extracted = pipeline.extract_parts(rules, material, rt)
    data = {
        "field": intake.raw.field,
        "material": material,
        "context": context,
        "parts": extracted.run.parts,
        "failedCalls": extracted.run.failed_calls,
        "modelUsed": extracted.model_used,
        "costUsd": rt.cost(),
        "usage": usage.summary(),
    }
    folder.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(pickle.dumps(data))
    return data


def recheck_with(strategy: str, case, data: dict[str, Any], factory, regions) -> tuple[pipeline.Outcome, float]:
    """저장한 첫 추출 조각 위에서 한 전략으로 재확인부터 발행 준비까지 돌립니다(조각·후보는 전략마다 새로 복사)."""
    os.environ["EXTRACTION_RECHECK_STRATEGY"] = strategy
    reader, api = InMemorySourceReader(files=case.source_files), FixedApi(case.api_reference)
    rt, usage = runtime(factory, reader, regions, api)
    rules = pipeline.RULES_BY_METHOD["structured"][data["field"]]
    material, context = data["material"], data["context"]
    run = ExtractionRun(parts=copy.deepcopy(data["parts"]), failed_calls=list(data["failedCalls"]))
    extracted = pipeline.Extracted(run, None, data["modelUsed"], rt.models.primary)
    first = pipeline.first_report(extracted, material, context, rt)
    if first is None:
        return pipeline.extraction_failed_outcome(extracted, None, material, rt), rt.cost()
    recheck, repairs = pipeline.recheck_step(rules, material, context, extracted, first, rt)
    report, actions = pipeline.quarantine_step(recheck.report, recheck, material, context, rt)
    repairs += actions
    pipeline.note_changes(report, extracted, recheck, actions)
    publication = pipeline.publish_step(report, case.event, material, rt)
    outcome = pipeline.finish(case.event, report, recheck, publication, extracted, None, repairs, material, rt)
    outcome.usage = usage.summary()
    return outcome, rt.cost()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board-root", type=Path, required=True)
    parser.add_argument("--board", action="append", default=[], help="<출처>:<공고 번호>")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, help="유료 API 키를 읽을 파일(값은 출력하지 않음)")
    parser.add_argument("--total-budget-usd", type=float, required=True)
    parser.add_argument("--reuse", action="store_true", help="저장한 첫 추출을 다시 씀(추출 비용 없음)")
    parser.add_argument("--strategies", default=",".join(STRATEGIES), help="쉼표로 구분한 재확인 전략(batch·agent·hybrid)")
    parser.add_argument("--confirm-spend", action="store_true")
    args = parser.parse_args()
    strategies = tuple(s.strip() for s in args.strategies.split(",") if s.strip())

    settings = Settings.from_env()
    if args.env_file is not None:
        settings = dataclasses.replace(settings, env_file=args.env_file)
    factory = ModelFactory(settings)
    print(f"모델: {factory.describe()}, 공고 {len(args.board)}건 × 전략 {'·'.join(strategies)}, 전체 상한 ${args.total_budget_usd:.2f}")
    if not args.confirm_spend:
        print("미리보기입니다. --confirm-spend로 실행합니다.")
        return
    regions = RegionCodeTable.from_csv(settings.region_table, settings.region_table_date)
    total, rows = 0.0, []

    def stage_budget() -> bool:
        """단계마다 공고당 상한은 운영 값 그대로 두고, 남은 전체 상한이 더 작으면 그만큼만 씁니다. 남은 것이 없으면 False.
        (2026-11-05: 공고당 상한을 $0.05로 낮췄더니 병렬 호출이 최악 비용을 함께 잡아 자격·선정·서류 호출이 보내지지도 않고 거절됐음)"""
        remaining = args.total_budget_usd - total
        if remaining <= 0.01:
            return False
        factory.settings = dataclasses.replace(settings, notice_budget_usd=min(settings.notice_budget_usd, remaining))
        return True

    for board in args.board:
        source, notice_id = board.split(":", 1)
        if not stage_budget():
            print(f"전체 상한에 닿아 멈춥니다(지금 ${total:.4f}). 남은 공고: {board} 외")
            break
        case = board_case(args.board_root, source, notice_id)
        case.event["payload"]["reprocess"] = False
        data = extract_once(case, factory, regions, args.out / case.name, args.reuse)
        if data is None:
            continue
        reused = args.reuse and (args.out / case.name / "extraction.pkl").exists()
        total += 0.0 if reused else data["costUsd"]
        complete = not data["failedCalls"]
        if not complete:  # 섹션이 빠진 첫 추출: 두 전략은 같은 조각이라 비교는 되지만 재확인 대상이 적어 대표성이 떨어집니다
            print(f"경고: {case.name} 첫 추출 실패 호출 {[name for name, _ in data['failedCalls']]} — 비교 결과에 extractionComplete=false로 남깁니다")
        row: dict[str, Any] = {"notice": case.name, "extractionCostUsd": round(data["costUsd"], 4), "reused": reused, "extractionComplete": complete}
        for strategy in strategies:
            if not stage_budget():
                print(f"전체 상한에 닿아 {case.name}의 {strategy} 재확인을 건너뜁니다(지금 ${total:.4f})")
                continue
            outcome, cost = recheck_with(strategy, case, data, factory, regions)
            total += cost
            folder = args.out / strategy / case.name
            folder.mkdir(parents=True, exist_ok=True)
            body = {
                "status": outcome.status,
                "error": outcome.error,
                "attempts": outcome.attempts,
                "event": outcome.event,
                "candidate": outcome.candidate,
                "usage": outcome.usage,
                "recheckCostUsd": cost,
                # 재확인 응답 원문(에이전트는 차례마다 도구 호출과 입력). 왜 채택·포기했는지 다시 돌리지 않고 보려고 남깁니다
                "recheckResponses": [r for r in outcome.responses if r[0] == "recheck" or r[0].startswith("repair:")],
            }
            (folder / "outcome.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            recheck = (outcome.usage or {}).get("recheck") or {}
            issues = (outcome.candidate or {}).get("quality", {}).get("reviewIssues", [])
            row[strategy] = {
                "status": outcome.status,
                "recheckCostUsd": round(cost, 4),
                "rechecked": len(recheck.get("rechecked") or []),
                "accepted": recheck.get("accepted"),
                "adopted": recheck.get("adoptedSections") or [],
                "reviewIssues": len(issues),
                "agent": recheck.get("agent"),
            }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"전체 추정 비용 ${total:.4f} ({len(rows)}건)")


if __name__ == "__main__":
    main()
