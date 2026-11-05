"""실제 공고로 운영 파이프라인(pipeline.process) 전체를 돌려 봅니다. DB·큐 없이, 모델 선택은 운영과 같은 설정(Settings.from_env)을 씁니다.

기본은 미리보기(호출 없음). --confirm-spend를 줘야 실제 모델을 부릅니다. 키·응답 원문은 출력하지 않고 --out 폴더(레포 밖 권장)에 결과만 저장합니다.
  PYTHONPATH=src uv run python scripts/pipeline_live.py --archive <아카이브> --out <결과 폴더> --lh-notice 0000061157 ... --confirm-spend
  팀원 수집 폴더: --board-root <폴더> --board sh:310653 ... (PDF만 AI 입력)
전체 상한(--total-budget-usd)을 주면 다음 공고의 최대 비용(공고당 상한)까지 더해 넘을 것 같을 때 멈춥니다.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from archive_cases import board_case, lh_case
from offline_common import FixedApi

from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.config import Settings
from mujuthaek_extraction.intake import InMemorySourceReader
from mujuthaek_extraction.model.factory import ModelFactory
from mujuthaek_extraction.pipeline import process
from mujuthaek_platform.events import new_event


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--lh-notice", action="append", default=[])
    parser.add_argument("--board-root", type=Path)
    parser.add_argument("--board", action="append", default=[], help="<출처>:<공고 번호>")
    parser.add_argument("--total-budget-usd", type=float)
    # 전체 상한 멈춤 규칙(2026-11-05): 공고당 상한(운영 $0.50)이 아니라 실제로 쓴 금액 + 다음 공고의 예상 금액으로 정합니다.
    # 전체 상한에 맞추려고 공고당 상한을 낮추면 동시 호출이 최악 비용 예약으로 거절돼(#14, 2026-11-05 에이전트 3건) 결과가 설정 탓으로 나빠짐
    parser.add_argument("--expected-per-notice-usd", type=float, default=0.08, help="다음 공고를 시작할지 정할 때 쓰는 공고당 예상 비용")
    parser.add_argument("--strategy", choices=("batch", "agent"), default="batch", help="재확인 답 받기 방법(EXTRACTION_RECHECK_STRATEGY)")
    parser.add_argument("--engine", choices=("graph", "agent"), default="graph", help="추출 방식(EXTRACTION_ENGINE): 정해진 단계·에이전트")
    parser.add_argument("--env-file", type=Path, help="유료 API 키를 읽을 파일(값은 출력하지 않음). 없으면 설정 기본 위치")
    parser.add_argument("--confirm-spend", action="store_true")
    args = parser.parse_args()
    targets = [("lh", n) for n in args.lh_notice] + [("board", b) for b in args.board]

    os.environ["EXTRACTION_RECHECK_STRATEGY"] = args.strategy
    os.environ["EXTRACTION_ENGINE"] = args.engine
    settings = Settings.from_env()
    if args.env_file is not None:
        settings = dataclasses.replace(settings, env_file=args.env_file)
    factory = ModelFactory(settings)
    print(f"모델: {factory.describe()}, 방식: {args.engine}, 재확인: {args.strategy}")
    if not args.confirm_spend:
        print(f"미리보기: {len(targets)}건, 공고당 상한 ${settings.notice_budget_usd:.2f}, 전체 상한 {args.total_budget_usd}. --confirm-spend로 실행합니다.")
        return
    regions = RegionCodeTable.from_csv(settings.region_table, settings.region_table_date)
    total = 0.0
    rows = []
    for kind, target in targets:
        if args.total_budget_usd is not None and total + args.expected_per_notice_usd > args.total_budget_usd:
            print(f"전체 상한 ${args.total_budget_usd:.2f}에 닿을 수 있어 멈춥니다(지금 ${total:.4f}). 남은 공고: {target} 외")
            break
        case = lh_case(args.archive, target) if kind == "lh" else board_case(args.board_root, *target.split(":", 1))
        notice_id = case.name if kind == "board" else target
        case.event["traceId"] = None
        case.event["payload"]["reprocess"] = False
        outcome = process(
            case.event,
            models=factory.for_notice(),
            reader=InMemorySourceReader(files=case.source_files),
            regions=regions,
            clock=lambda: datetime.now(UTC),
            new_event=new_event,
            api_provider=FixedApi(case.api_reference),
            parallel_calls=settings.parallel_calls,  # 운영 워커와 같은 동시 호출(시간 비교를 공정하게)
            parallel_stagger=settings.parallel_stagger_seconds,
        )
        total += outcome.cost_usd
        folder = args.out / notice_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "responses.json").write_text(json.dumps(outcome.responses, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "outcome.json").write_text(
            json.dumps(
                {
                    "status": outcome.status,
                    "error": outcome.error,
                    "attempts": outcome.attempts,
                    "event": outcome.event,
                    "candidate": outcome.candidate,
                    "usage": outcome.usage,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        quality = (outcome.candidate or {}).get("quality", {})
        issues = Counter(i["code"] for i in quality.get("reviewIssues", []))
        conditions = (outcome.event or {}).get("payload", {}).get("conditions", [])
        row = {
            "notice": notice_id,
            "title": case.event["payload"]["title"],
            "status": outcome.status,
            "model": outcome.model_used,
            "cost": round(outcome.cost_usd, 4),
            "calls": [a["call_name"] for a in outcome.attempts],
            "review": dict(issues),
            "notes": len(quality.get("notes", [])),
            "conditions": len(conditions),
            "structured": sum(1 for c in conditions if c["rule"]["status"] == "STRUCTURED"),
            "conditionsInReview": [c["id"] for c in conditions if c["inReview"]],
            "error": outcome.error,
            "repairs": outcome.repairs,
            "recheck": (outcome.usage or {}).get("recheck"),
            "agentic": _agentic_brief((outcome.usage or {}).get("agentic")),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    (args.out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"전체 추정 비용 ${total:.4f} ({len(rows)}건)")


def _agentic_brief(record: dict | None) -> dict | None:
    """에이전트 방식 기록 요약: 에이전트마다 차례·결말·부른 도구 순서, 받아들인·보류한 문제 수."""
    if not record:
        return None
    applied = record.get("applied") or {}
    return {
        "agents": [f"{a['name']} {a['turns']}차례 {a['outcome']}: {'→'.join(a['steps'])}" for a in record["agents"]],
        "accepted": len(applied.get("accepted") or []),
        "held": len(applied.get("held") or []),
        "verifierIssues": len(record.get("verifierIssues") or []),
    }


if __name__ == "__main__":
    main()
