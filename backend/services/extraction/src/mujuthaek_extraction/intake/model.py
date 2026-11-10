"""수집 입력 → 추출 입력 어댑터의 결과 자료형.

신뢰 문맥(TrustedContext)은 프로그램이 확정하고, 추출 자료(ExtractionMaterial)만 AI에 전달합니다.
AI는 이벤트 ID·원본 ID·해시·API 대조 상태를 만들거나 바꾸지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntakeStatus(Enum):
    """심각도 순서입니다. 여러 문제가 겹치면 가장 심각한 상태를 결과로 사용합니다."""

    READY = 0
    WAITING_SOURCE = 1  # 자료가 아직 없음. job 정책의 제한 재시도 대상
    REVIEW_REQUIRED = 2  # 자료가 서로 맞지 않음. 검수 전 추출하지 않음
    REJECTED = 3  # 이벤트 형식 자체가 잘못됨. 재시도하지 않음


@dataclass(frozen=True)
class IntakeIssue:
    code: str
    status: IntakeStatus
    path: str
    message: str


@dataclass(frozen=True)
class RawFile:
    index: int
    name: str
    download_url: str
    sha256: str
    file_type: str  # pdf, hwp, hwpx, xlsx, xlsm, xls
    role: str  # NOTICE_DOC 공고문, UNIT_LIST 주택목록
    s3_key: str | None  # S3 버킷 안 경로(raw/…). 보관 기한이 지나 파일을 지운 뒤 재처리하면 None
    s3_key_given: bool = True  # False: s3Key 칸이 없는 이전 형식 이벤트(위치를 모름)


@dataclass(frozen=True)
class RawNoticeCollected:
    """collector가 보낸 raw.notice.collected 이벤트에서 읽어 낸 공고 1건의 수집 내용입니다."""

    event_id: str
    raw_post_id: str
    version: int
    source_code: str
    provider: str | None
    region_code: str | None
    field: str
    kind: str
    title: str
    posted_on: str | None
    detail_url: str | None
    supersedes_post_id: str | None
    text: str
    text_key: str | None
    units: tuple[dict[str, Any], ...]
    files: tuple[RawFile, ...]
    reprocess: bool
    api_data: Any = None  # 기관 API 응답 JSON (선택, 모양 자유). 추출 원문이 아니라 대조 기준으로만 씁니다


@dataclass(frozen=True)
class ApiReference:
    """같은 공고·같은 버전에 대해 수집 시점에 저장한 기관 API 응답 원본입니다."""

    source_code: str
    source_notice_id: str  # raw v1에 대응 값이 없어 대조하지 못합니다. 조회 구현(담당자 4 연결)을 신뢰합니다
    raw_post_id: str
    raw_version: int
    sha256: str
    body: bytes


@dataclass(frozen=True)
class MaterialFile:
    document_id: str
    name: str
    data: bytes
    # 이벤트의 fileType(pdf, hwp, hwpx, xlsx, xlsm, xls). PDF·엑셀 읽기는 이름 끝이 아니라 이 값으로 정합니다
    # (이름 끝에 공백이 있거나 확장자가 없는 첨부도 있음). 빈 값은 형식을 모름
    file_type: str = ""


@dataclass(frozen=True)
class ExtractionMaterial:
    """AI에 보여 줄 자료입니다. 식별자·해시·API 기대값을 넣지 않습니다."""

    text: str
    text_document_id: str
    units: tuple[dict[str, Any], ...]
    units_document_id: str | None
    files: tuple[MaterialFile, ...]
    pdf_pages: tuple[dict[str, Any], ...] = ()  # 첨부 PDF의 쪽·표 구조 JSON (저장·확인용, AI에는 render 글자로 전달)
    # 첨부 엑셀 시트: {"documentId", "name", "sheet", "rows"}. 행은 원문(text)에 붙인 「| … |」 줄과 같은 칸이라 공급표 해석기가 그대로 옮깁니다
    sheets: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class TrustedContext:
    """extracted-notice.v1의 input·sourceReferences·documents에 그대로 들어갈 값과 API 대조 준비 상태입니다."""

    input: dict[str, Any]
    source_references: tuple[dict[str, Any], ...]
    documents: tuple[dict[str, Any], ...]
    api_comparison_status: str  # SKIPPED_NO_API_REFERENCE 또는 NOT_RUN(기준 있음, 대조 전)
    api_reference: ApiReference | None
    forced_review: tuple[tuple[str, str], ...] = ()  # (코드, 설명): 추출은 하되 사람 확인을 강제할 입력 문제 (예: 공고 PDF 없음)


@dataclass(frozen=True)
class IntakeResult:
    status: IntakeStatus
    issues: tuple[IntakeIssue, ...] = ()
    raw: RawNoticeCollected | None = None
    context: TrustedContext | None = None
    material: ExtractionMaterial | None = field(default=None)

    @property
    def ready(self) -> bool:
        return self.status is IntakeStatus.READY
