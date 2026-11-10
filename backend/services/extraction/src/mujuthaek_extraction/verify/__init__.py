"""추출 결과 독립 검증. 설계: docs/extraction/verification.md.

V1 계약 · V2 원문 근거 · V3 수치 · V4 API 대조 · V5 예외 누락 · V6 표 위치 · V7 일관성 · V8 누락
"""

from mujuthaek_extraction.verify.model import RULES_VERSION, Finding, PdfTextExtractor, SourceBundle, VerificationReport
from mujuthaek_extraction.verify.verifier import verify_extraction

__all__ = ["RULES_VERSION", "Finding", "PdfTextExtractor", "SourceBundle", "VerificationReport", "verify_extraction"]
