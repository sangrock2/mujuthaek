"""검증 모듈 자료형. 설계: docs/extraction/verification.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from mujuthaek_extraction.intake.model import ExtractionMaterial

RULES_VERSION = "verify-1.14.0"  # 검사 규칙이 바뀌면 올립니다


class PdfTextExtractor(Protocol):
    def pages(self, data: bytes) -> list[str]:
        """PDF 실제 쪽 순서대로 쪽별 텍스트."""
        ...


@dataclass(frozen=True)
class SourceBundle:
    """intake가 확인한 자료. 문서 ID → 내용."""

    texts: dict[str, str] = field(default_factory=dict)
    units: dict[str, tuple[dict[str, Any], ...]] = field(default_factory=dict)
    pdfs: dict[str, bytes] = field(default_factory=dict)

    @classmethod
    def from_material(cls, material: ExtractionMaterial) -> SourceBundle:
        units = {material.units_document_id: material.units} if material.units_document_id else {}
        return cls(texts={material.text_document_id: material.text}, units=units, pdfs={f.document_id: f.data for f in material.files})


@dataclass(frozen=True)
class Finding:
    check: str  # V1 계약 / V2 원문 근거 / V3 수치 / V4 API / V5 예외 누락 의심 / V6 표 위치 / V7 일관성 / V8 누락
    code: str
    target: str
    description: str

    def issue(self) -> dict[str, str]:
        return {"code": self.code, "target": self.target, "description": self.description}


@dataclass
class VerificationReport:
    candidate: dict[str, Any]  # quality를 갱신한 새 후보 (입력 후보는 바꾸지 않음)
    findings: list[Finding]
    contract_errors: list[str]

    @property
    def verification(self) -> dict[str, Any]:
        return self.candidate["quality"]["verification"]

    @property
    def passed(self) -> bool:
        return self.verification["status"] == "PASSED"
