"""운영 모델 정책 (결정 C12): 로컬 AI를 먼저 쓰고, 연결이 실패하거나 결과가 기준에 못 미치면 gpt-6-luna로 다시 추출합니다.

로컬 AI는 아직 구축 전이라 지금은 primary 자리에 gpt-6-luna를 둡니다. 로컬 AI가 준비되면 같은 ExtractionModel 인터페이스로 끼웁니다.
- 연결 실패(일시·영구 오류)는 호출 단위로 바로 대체 모델에 넘깁니다.
- 결과 부족(실패한 호출이 남거나 계약 규칙 위반이 남음)은 공고 단위로 대체 모델이 처음부터 다시 추출합니다.
  원문에서 못 찾은 인용은 기준에 넣지 않습니다(2026-10-15 결정). 검수로 넘기면 되고, 넣으면 비용만 두 배가 됩니다.
비용 상한(공고당)은 실행 쪽 Budget이 지킵니다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mujuthaek_extraction.extract import ExtractionRun, run_extraction, schema_errors
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, ModelResponse
from mujuthaek_extraction.rules.base import FieldRules, call_schema, document_ids


class FallbackOnErrorModel:
    """호출이 오류로 실패하면 같은 요청을 대체 모델로 보냅니다."""

    def __init__(self, primary: ExtractionModel, fallback: ExtractionModel):
        self.primary = primary
        self.fallback = fallback
        self.fallback_calls: list[str] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            return self.primary.complete(request)
        except ModelError:
            self.fallback_calls.append(request.call_name)
            return self.fallback.complete(request)


def acceptable(run: ExtractionRun, rules: FieldRules, material: ExtractionMaterial) -> bool:
    """대체 모델로 다시 돌릴 필요가 없는 결과인지: 실패한 호출이 없고 모든 조각이 계약 규칙을 지킴."""
    if run.failed_calls:
        return False
    documents = document_ids(material)
    # 조각마다 자기가 보고한 섹션(coverage 키)의 형식으로 검사합니다. 표에서 코드가 만든 공급 조각(supply_tables)은 호출과 짝이 없습니다
    return all(schema_errors(part, call_schema(tuple(part.get("coverage") or ()), documents)) is None for part in run.parts)


@dataclass
class FallbackResult:
    run: ExtractionRun
    used: str  # "primary" 또는 "fallback"
    primary_run: ExtractionRun | None = None  # 대체 모델로 다시 돌렸을 때 처음 결과 (job 기록용)


def extract_with_fallback(
    rules: FieldRules,
    material: ExtractionMaterial,
    primary: ExtractionModel,
    fallback: ExtractionModel,
    *,
    judge: Callable[[ExtractionRun, FieldRules, ExtractionMaterial], bool] = acceptable,
    **run_options,
) -> FallbackResult:
    """기본 모델로 추출하고(호출 오류는 그 호출만 대체 모델로), 결과가 judge 기준에 못 미치면 대체 모델로 처음부터 다시 추출합니다."""
    chain = FallbackOnErrorModel(primary, fallback)
    first = run_extraction(rules, material, chain, **run_options)
    if judge(first, rules, material):
        return FallbackResult(first, "primary")
    if len(chain.fallback_calls) >= len(first.attempts):  # 모든 호출이 이미 대체 모델로 갔으면 다시 돌려도 같은 모델이라 비용만 듭니다
        return FallbackResult(first, "fallback")
    second = run_extraction(rules, material, fallback, **run_options)
    return FallbackResult(second, "fallback", primary_run=first)
