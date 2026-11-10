"""저장된 추출 결과를 정답표로 채점해 LangSmith 평가 실험으로 올립니다(모델 호출 없음).

- 데이터셋: 정답표(공고마다 key.json) 가운데 결과 폴더에 결과가 있는 공고를 LangSmith 데이터셋으로(입력 notice, 기대 출력 key).
  같은 이름의 데이터셋이 있으면 없는 공고만 더합니다.
- 실험: 실험 대상은 결과 폴더의 outcome.json을 채점 모양(score_answer_keys.neutral_from_candidate·published_view)으로 내고,
  평가기가 데이터셋의 정답표와 맞댑니다(score_answer_keys와 같은 기준). 결과 파일 전체는 올리지 않습니다.
  공고마다 재현율·검수 없이 게시·자동 게시 틀린 값·검수 없는 공고·비용, 전체는 로컬 채점처럼 합계 기준(예: 재현율 410/419)으로 냅니다.
- LangSmith 실험 화면에서 V1·V2 실험을 나란히 비교합니다. 키는 .env에서 읽고(Settings.export_tracing) 출력하지 않습니다.

python scripts/langsmith_eval.py --keys <정답표 폴더> --outcomes <결과 폴더> --experiment V1-기준 [--dataset 이름] [--env-file .env]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path
from typing import Any

from langsmith import Client, evaluate
from score_answer_keys import _load_key, compare, neutral_from_candidate, published_view, sums, wrong_values

from mujuthaek_extraction.config import Settings

DATASET = "mujuthaek-answer-keys"


def cost_usd(outcome: dict[str, Any]) -> float:
    """V1 호출(구조·그림 판독 포함)과 V2 담당 호출의 유료 비용 합."""
    usage = outcome.get("usage") or {}
    calls = [*usage.get("calls", []), *(usage.get("v2") or {}).get("calls", [])]
    return round(sum(c.get("costUsd") or 0 for c in calls), 6)


def target_for(outcomes: Path):
    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        notice = inputs["notice"]
        outcome = json.loads((outcomes / notice / "outcome.json").read_text(encoding="utf-8"))
        candidate = outcome.get("candidate")
        return {
            "status": outcome.get("status"),
            "costUsd": cost_usd(outcome),
            "seconds": (outcome.get("usage") or {}).get("totalSeconds"),
            "actual": neutral_from_candidate(candidate, notice) if candidate else None,
            "published": published_view(outcome, notice) if candidate else None,
        }

    return target


def recall(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    found, total = sums(compare(reference_outputs["key"], outputs["actual"])) if outputs["actual"] else (0, _total(reference_outputs))
    return {"key": "재현율", "score": found / total if total else 0, "comment": f"{found}/{total}"}


def released(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """검수 없이 게시되는 정답 값의 비율(검수 공고는 0)."""
    total = _total(reference_outputs)
    found = sums(compare(reference_outputs["key"], outputs["published"]))[0] if outputs["published"] else 0
    return {"key": "검수 없이 게시", "score": found / total if total else 0, "comment": f"{found}/{total}"}


def wrong(outputs: dict[str, Any], reference_outputs: dict[str, Any]) -> dict[str, Any]:
    """자동 게시 값 중 정답표에 없는 값(틀린 값 후보) 수. 0이어야 함."""
    if not outputs["published"]:
        return {"key": "틀린 값 후보", "score": 0}
    score = wrong_values(reference_outputs["key"], outputs["published"])
    labels = [label for misses in score.misses.values() for label in misses]
    return {"key": "틀린 값 후보", "score": sum(score.total.values()) - sum(score.found.values()), "comment": "; ".join(labels)[:500] or None}


def completed(outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "검수 없는 공고", "score": int(outputs["status"] == "COMPLETED")}


def cost(outputs: dict[str, Any]) -> dict[str, Any]:
    return {"key": "비용(USD)", "score": outputs["costUsd"]}


def totals(outputs: list[dict[str, Any]], reference_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """로컬 채점과 같은 합계 기준(공고마다 평균이 아님)."""
    found = released_found = total = 0
    for out, ref in zip(outputs, reference_outputs, strict=True):
        total += _total(ref)
        found += sums(compare(ref["key"], out["actual"]))[0] if out["actual"] else 0
        released_found += sums(compare(ref["key"], out["published"]))[0] if out["published"] else 0
    return [
        {"key": "전체 재현율", "score": found / total if total else 0, "comment": f"{found}/{total}"},
        {"key": "전체 검수 없이 게시", "score": released_found / total if total else 0, "comment": f"{released_found}/{total}"},
    ]


def _total(reference_outputs: dict[str, Any]) -> int:
    """그 공고 정답표의 값 수(아무것도 못 찾은 결과와 비교해 셈)."""
    return sums(compare(reference_outputs["key"], {}))[1]


def ensure_dataset(client: Client, name: str, keys: Path, outcomes: Path) -> list[Any]:
    """데이터셋을 만들거나 없는 공고만 더하고, 결과 폴더에 결과가 있는 공고의 예제를 돌려줍니다."""
    dataset = (
        client.read_dataset(dataset_name=name)
        if client.has_dataset(dataset_name=name)
        else client.create_dataset(name, description="무주택자들 공고 추출 정답표")
    )
    existing = {example.inputs["notice"]: example for example in client.list_examples(dataset_id=dataset.id)}
    notices = sorted(p.name for p in keys.iterdir() if p.is_dir() and (outcomes / p.name / "outcome.json").exists())
    new = [n for n in notices if n not in existing]
    if new:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[{"inputs": {"notice": n}, "outputs": {"key": _load_key(keys, n)}, "metadata": {"source": n.split("-")[0]}} for n in new],
        )
        existing = {example.inputs["notice"]: example for example in client.list_examples(dataset_id=dataset.id)}
    return [existing[n] for n in notices if n in existing]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--experiment", required=True, help="실험 이름 앞부분(예: V1-기준, V2)")
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--description", default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.env_file is not None:
        settings = dataclasses.replace(settings, env_file=args.env_file)
    settings.export_tracing()
    client = Client()
    examples = ensure_dataset(client, args.dataset, args.keys, args.outcomes)
    results = evaluate(
        target_for(args.outcomes),
        data=examples,
        evaluators=[recall, released, wrong, completed, cost],
        summary_evaluators=[totals],
        experiment_prefix=args.experiment,
        description=args.description,
        metadata={"outcomes": args.outcomes.name, "notices": len(examples)},
        max_concurrency=4,
        client=client,
    )
    print(f"실험 {results.experiment_name}: 공고 {len(examples)}건")


if __name__ == "__main__":
    main()
