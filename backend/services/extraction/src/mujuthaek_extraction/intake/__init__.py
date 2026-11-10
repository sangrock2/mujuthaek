"""수집 입력 → 추출 입력 어댑터."""

from mujuthaek_extraction.intake.adapter import build_intake
from mujuthaek_extraction.intake.model import (
    ApiReference,
    ExtractionMaterial,
    IntakeIssue,
    IntakeResult,
    IntakeStatus,
    TrustedContext,
)
from mujuthaek_extraction.intake.sources import ApiReferenceProvider, InMemorySourceReader, LocalDirSourceReader, NoApiReference, SourceReader

__all__ = [
    "ApiReference",
    "ApiReferenceProvider",
    "ExtractionMaterial",
    "InMemorySourceReader",
    "LocalDirSourceReader",
    "IntakeIssue",
    "IntakeResult",
    "IntakeStatus",
    "NoApiReference",
    "SourceReader",
    "TrustedContext",
    "build_intake",
]
