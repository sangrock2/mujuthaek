"""그래프 노드가 주고받는 처리 상태입니다.

체크포인트를 켜지 않는 동안(1·2단계)은 객체를 그대로 담습니다. 처리 중 상태를 저장하게 되면(3단계)
intake·material처럼 큰 값은 S3 키·해시로 바꿔야 합니다.
"""

from __future__ import annotations

from typing import Any, TypedDict

from mujuthaek_extraction.extract import ExtractionRun
from mujuthaek_extraction.intake import IntakeResult
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext
from mujuthaek_extraction.pipeline import Extracted, Outcome, Publication
from mujuthaek_extraction.recheck import RecheckResult
from mujuthaek_extraction.rules.base import FieldRules
from mujuthaek_extraction.verify import VerificationReport


class ExtractionState(TypedDict, total=False):
    raw_event: dict[str, Any]
    method: str
    intake: IntakeResult
    rules: FieldRules
    material: ExtractionMaterial  # 그림 판독 글자를 붙인 뒤의 원문
    context: TrustedContext
    image_run: ExtractionRun | None
    extracted: Extracted
    first: VerificationReport
    recheck: RecheckResult
    report: VerificationReport
    repairs: list[str]
    quarantine_actions: list[str]
    publication: Publication
    outcome: Outcome  # 이 값이 생기면 끝입니다
