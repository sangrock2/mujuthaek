"""수집 입력(raw.notice.collected) → 추출 입력 어댑터.

같은 입력에는 항상 같은 결과를 냅니다. 시계·UUID 생성·네트워크·AI 호출을 사용하지 않습니다.
불완전하거나 서로 맞지 않는 입력은 READY가 아닌 상태와 이유로 남기고 추출 자료를 만들지 않습니다.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from mujuthaek_extraction.intake.model import (
    ApiReference,
    ExtractionMaterial,
    IntakeIssue,
    IntakeResult,
    IntakeStatus,
    MaterialFile,
    TrustedContext,
)
from mujuthaek_extraction.intake.pdf_reader import MAX_PAGES, PdfDocument, read_pdf
from mujuthaek_extraction.intake.raw_event import InvalidRawEvent, parse_raw_event
from mujuthaek_extraction.intake.sources import ApiReferenceProvider, NoApiReference, SourceReader
from mujuthaek_extraction.intake.xlsx_reader import read_xlsx

# contracts/tools/validate_contracts.py의 PRIVATE_URL 검사와 같은 목록입니다.
SECRET_QUERY_KEYS = {"servicekey", "apikey", "token", "access_token", "signature", "x-amz-signature"}
SHA256 = re.compile(r"[0-9a-f]{64}")
# 첨부 확장자 → 계약 문서 종류. xlsx·xlsm은 extraction이 직접 읽어 공급주택목록으로 씁니다(옛 xls는 읽지 않음).
ATTACHMENT_KINDS = {"pdf": "PDF", "xlsx": "SPREADSHEET", "xlsm": "SPREADSHEET", "xls": "SPREADSHEET"}
TEXT_DOCUMENT_ID = "text"
PDF_TEXT_DOCUMENT_ID = "pdf-text"  # 첨부 PDF·엑셀을 extraction이 직접 읽어 만든 글자 (쪽·표 구분)
UNITS_DOCUMENT_ID = "units"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def units_bytes(units: tuple[dict[str, Any], ...]) -> bytes:
    """호별 표의 해시 기준이 되는 정규화 직렬화입니다."""
    return json.dumps(list(units), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def public_url(value: str | None) -> str | None:
    """사용자에게 보여 줄 수 있는 http(s) 링크만 남깁니다. 인증 정보가 섞인 링크는 계약에 넣지 않습니다."""
    if value is None or not value.startswith(("http://", "https://")) or any(c.isspace() for c in value):
        return None
    parts = urlsplit(value)
    params = {name.lower() for name, _ in parse_qsl(parts.query)}
    if not parts.netloc or parts.username or parts.password or params & SECRET_QUERY_KEYS:
        return None
    return value


# 기관 공고 ID로 보이는 키를 ID 체계별로 둡니다. LH 공고 ID(PAN_ID·panId)와 마이홈 공고 ID(pblancId)는 같은 공고를 가리키는
# 서로 다른 번호라 한 응답에 함께 옵니다(실측 2026-10-20: PAN_ID 2015122300020815와 pblancId 21360). 앞 체계부터 보고 값이 있는 첫 체계만 씁니다
API_NOTICE_ID_KEYS = (("PAN_ID", "panId"), ("pblancId",))


def api_notice_ids(api_data: Any) -> list[str]:
    """apiData 어디에 있든 기관 공고 ID 값을 모읍니다. 값이 있는 첫 ID 체계(API_NOTICE_ID_KEYS)의 값만, 같은 값은 한 번, 처음 나온 순서입니다.
    같은 체계 안에서 서로 다른 값이 둘 이상이면 목록 응답처럼 여러 공고가 섞인 것이라 호출하는 쪽이 충돌로 봅니다."""
    found: dict[int, list[str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for group, keys in enumerate(API_NOTICE_ID_KEYS):
                for key in keys:
                    value = node.get(key)
                    if isinstance(value, str | int) and not isinstance(value, bool) and (text := str(value).strip()):
                        values = found.setdefault(group, [])
                        if text not in values:
                            values.append(text)
            node = list(node.values())
        if isinstance(node, list):
            for child in node:
                walk(child)

    walk(api_data)
    return next((found[group] for group in range(len(API_NOTICE_ID_KEYS)) if found.get(group)), [])


def api_reference_from_event(raw: Any, notice_id: str) -> ApiReference:
    """이벤트에 담겨 온 API 응답 JSON(apiData, 선택) → 대조 기준. 모양은 고정하지 않고 받은 그대로 둡니다.
    기관 공고 ID는 apiData에서 찾은 값만 씁니다(내부 rawPostId로 채우지 않음, build_intake에서 확인)."""
    body = json.dumps(raw.api_data, ensure_ascii=False).encode("utf-8")
    return ApiReference(raw.source_code, notice_id, raw.raw_post_id, raw.version, sha256_hex(body), body)


def build_intake(
    event: Any,
    reader: SourceReader,
    api_provider: ApiReferenceProvider | None = None,
    *,
    require_pdf: bool = True,
    table_labels: bool = False,
) -> IntakeResult:
    """require_pdf: 공고는 PDF가 반드시 온다는 규칙(2026-10-16). PDF가 없으면 수집 글자로 추출하되 사람 확인을 강제하고,
    PDF 원본 위치(s3Key)가 없거나 보관 기한이 지났으면 수집 글자로 진행하고(ATTACHMENT_NOT_STORED), S3에서 읽지 못한 일시 오류만
    자료 대기(WAITING_SOURCE)로 둡니다. 글자만 있는 시험 이벤트에서만 끕니다.
    table_labels: 표에 열 제목 줄·행 읽기 도움 줄을 붙입니다(구조 방식, method.py). 기본 False는 이전 글자 모양."""
    try:
        raw = parse_raw_event(event)
    except InvalidRawEvent as error:
        issue = IntakeIssue("INVALID_EVENT", IntakeStatus.REJECTED, error.path or "/", error.message)
        return IntakeResult(IntakeStatus.REJECTED, (issue,))

    issues: list[IntakeIssue] = []

    def issue(code: str, status: IntakeStatus, path: str, message: str) -> None:
        issues.append(IntakeIssue(code, status, path, message))

    review, waiting, ready = IntakeStatus.REVIEW_REQUIRED, IntakeStatus.WAITING_SOURCE, IntakeStatus.READY

    # 정정·후속 관계는 collector가 연결한 값만 확인합니다. 제목 유사도 등으로 다시 추정하지 않습니다.
    if raw.supersedes_post_id is not None and raw.supersedes_post_id == raw.raw_post_id:
        issue("RELATION_INCONSISTENT", review, "/payload/supersedesPostId", "공고가 자기 자신을 가리킵니다.")
    elif raw.kind == "NOTICE" and raw.supersedes_post_id is not None:
        issue("RELATION_INCONSISTENT", review, "/payload/supersedesPostId", "일반 공고에 원 공고 연결이 있습니다.")
    elif raw.kind != "NOTICE" and raw.supersedes_post_id is None:
        issue("RELATION_UNRESOLVED", review, "/payload/supersedesPostId", "정정·후속 공고의 원 공고가 연결되지 않았습니다.")

    text = raw.text
    if raw.text_key is not None:
        full = reader.read_text(raw.text_key)
        if full is None:
            issue("SOURCE_TEXT_UNAVAILABLE", waiting, "/payload/textKey", "잘린 원문의 전체 텍스트를 읽지 못했습니다.")
        elif not full.startswith(raw.text):
            issue("SOURCE_TEXT_MISMATCH", review, "/payload/textKey", "전체 텍스트가 이벤트의 앞부분과 다릅니다.")
        else:
            text = full

    material_files: list[MaterialFile] = []
    file_documents: list[dict[str, Any]] = []
    for file in raw.files:
        path = f"/payload/files/{file.index}"
        document_id = f"file-{file.index + 1}"
        kind = ATTACHMENT_KINDS.get(file.file_type)
        if kind is None:
            if file.role == "NOTICE_DOC":  # 공고문이 HWP·HWPX뿐인 출처(대구·울산 등): collector가 뽑은 글자(text)로 추출합니다
                issue("NOTICE_DOC_NOT_PDF", ready, path, f"공고문이 {file.file_type.upper()} 형식이라 collector가 뽑은 글자로 추출합니다.")
            else:
                issue("ATTACHMENT_TYPE_UNSUPPORTED", ready, path, "PDF·엑셀이 아닌 첨부는 근거 문서로 사용하지 않습니다.")
            continue
        file_documents.append(
            {
                "id": document_id,
                "kind": kind,
                "name": file.name,
                "sha256": file.sha256,
                "originalUrl": public_url(file.download_url),
                "pageCount": None,  # PDF를 열어 확인하기 전에는 추정하지 않습니다(엑셀은 쪽 개념 없음)
            }
        )
        if file.s3_key is None:
            # s3Key가 null이면 보관 기한이 지나 S3에서 지운 원본입니다(재처리). 칸이 없으면 위치를 보내지 않는 이전 형식 이벤트입니다.
            # 어느 쪽이든 기다려도 오지 않으므로 수집 글자로 추출합니다(공고문이면 아래에서 사람 확인을 강제)
            if file.s3_key_given:
                issue("ATTACHMENT_NOT_STORED", ready, path, "첨부 원본이 S3에 없어(보관 기한 지남) 수집 글자로 추출합니다.")
            else:
                issue("ATTACHMENT_NOT_STORED", ready, path, "첨부 원본 위치(s3Key)가 없는 이벤트라 수집 글자로 추출합니다.")
            continue
        data = reader.read_file(file.s3_key)
        if data is None:
            issue("ATTACHMENT_UNAVAILABLE", waiting, path, "첨부 원본을 읽지 못했습니다.")
        elif sha256_hex(data) != file.sha256:
            issue("FILE_HASH_MISMATCH", review, path, "첨부 원본의 해시가 이벤트와 다릅니다.")
        else:
            material_files.append(MaterialFile(document_id, file.name, data, file.file_type))

    # 서비스 흐름 3단계: 전달된 PDF를 직접 읽어 쪽·표 구조로 바꿉니다. 읽을 수 있으면 이 글자를 추출 원문으로 씁니다.
    # 형식은 이벤트의 fileType으로 정합니다. 이름 끝으로 정하면 「공고문.pdf 」·확장자 없는 이름의 PDF를 읽지 않고 조용히 넘어갔습니다
    pdf_documents: list[tuple[MaterialFile, PdfDocument]] = []
    unreadable_pdfs: list[str] = []  # 글자를 읽지 못한 PDF 이름 (사람 확인 설명용)
    scanned_pages: list[str] = []  # 「파일 이름 3, 4, 5쪽」: 글자가 거의 없는 쪽 (사람 확인 설명용)
    for file in material_files:
        if file.file_type != "pdf":
            continue
        parsed = read_pdf(file.data)
        if parsed is None:
            index = int(file.document_id.split("-")[1]) - 1
            issue("PDF_TEXT_UNREADABLE", ready, f"/payload/files/{index}", "PDF에서 글자를 읽지 못해(스캔본 등) 수집 글자로 추출합니다.")
            unreadable_pdfs.append(file.name.strip())
        else:
            pdf_documents.append((file, parsed))
            if parsed.page_count > MAX_PAGES:
                index = int(file.document_id.split("-")[1]) - 1
                issue("PDF_TOO_LONG", ready, f"/payload/files/{index}", f"PDF가 {parsed.page_count}쪽이라 앞 {MAX_PAGES}쪽만 읽었습니다.")
            empty = parsed.empty_pages()
            if parsed.page_count >= 2 and len(empty) * 2 >= parsed.page_count:
                index = int(file.document_id.split("-")[1]) - 1
                pages = ", ".join(map(str, empty[:10])) + (f" 외 {len(empty) - 10}쪽" if len(empty) > 10 else "")
                scanned_pages.append(f"{file.name.strip()} {pages}쪽")
                issue(
                    "PDF_PAGES_UNREADABLE",
                    ready,
                    f"/payload/files/{index}",
                    f"PDF {parsed.page_count}쪽 중 {len(empty)}쪽에 글자가 거의 없습니다(스캔·그림 쪽: {pages}).",
                )
    for document in file_documents:
        for file, parsed in pdf_documents:
            if document["id"] == file.document_id:
                document["pageCount"] = parsed.page_count
    # 공고문(NOTICE_DOC)은 PDF로 읽지 못했는데(HWP·스캔본·S3에 없음) 목록 PDF는 읽힌 경우: 예전엔 목록 PDF 글자가 원문을 통째로 바꿔
    # 수집 글자에 있던 공고 본문(자격·일정·서류)이 빠졌습니다(2026-11-10 코드 검토). 수집 글자를 본문으로 두고 읽힌 PDF를 뒤에 붙입니다
    notices = {index for index, file in enumerate(raw.files) if file.role == "NOTICE_DOC"}
    text_led = bool(pdf_documents) and bool(notices) and not any(int(file.document_id.split("-")[1]) - 1 in notices for file, _ in pdf_documents)
    pdf_text = None
    if pdf_documents:
        rendered = [
            parsed.render(table_labels) if len(pdf_documents) == 1 and not text_led else f"=== 첨부 {file.name} ===\n{parsed.render(table_labels)}"
            for file, parsed in pdf_documents
        ]
        pdf_text = "\n".join([text, *rendered] if text_led else rendered)

    # 공급주택목록 엑셀이 있으면 원문 뒤에 붙여 AI가 주택별 공급 묶음으로 옮깁니다. 없으면 공고문 표에서 읽습니다(사용자 결정 2026-10-16).
    sheets: list[str] = []
    sheet_tables: list[dict[str, Any]] = []
    for file in material_files:
        index = int(file.document_id.split("-")[1]) - 1
        if file.file_type == "xls":
            issue("SPREADSHEET_UNREADABLE", ready, f"/payload/files/{index}", "옛 엑셀(xls) 형식은 읽지 않아 공고문에서 공급 목록을 읽습니다.")
            continue
        if file.file_type not in ("xlsx", "xlsm"):
            continue
        listing = read_xlsx(file.data)
        if listing is None:
            issue("SPREADSHEET_UNREADABLE", ready, f"/payload/files/{index}", "첨부 엑셀을 읽지 못해 공고문에서 공급 목록을 읽습니다.")
            continue
        if listing.truncated:
            message = f"첨부 엑셀이 {listing.rows}행이라 주택별로 넣지 않고 공고문의 주택형별 표로 읽습니다."
            issue("SPREADSHEET_TOO_LARGE", ready, f"/payload/files/{index}", message)
        if listing.hidden:  # 숨긴 행·열은 넘기지 않았음(이번 공고가 아닌 호실일 수 있음, xlsx_reader)
            issue("SPREADSHEET_HIDDEN_PARTS", ready, f"/payload/files/{index}", f"첨부 엑셀의 숨긴 행·열 {listing.hidden}개는 넘기지 않았습니다.")
        sheets.append(f"=== 첨부 엑셀 {file.name} ===\n{listing.text}")
        sheet_tables.extend({"documentId": file.document_id, "name": file.name, "sheet": name, "rows": rows} for name, rows in listing.sheets)
    attachment_text = pdf_text
    if sheets:
        attachment_text = "\n".join([pdf_text if pdf_text is not None else text, *sheets])

    forced: list[tuple[str, str]] = []
    # collector는 목록 원본만 전달합니다. 읽지 못한 목록을 공고문이 전부 대신한다고 가정하면
    # PDF에 없는 호별 조건이 빠진 채 자동 완료될 수 있어, 추출은 계속하되 검수를 남깁니다.
    for code in ("SPREADSHEET_UNREADABLE", "SPREADSHEET_TOO_LARGE", "SPREADSHEET_HIDDEN_PARTS", "ATTACHMENT_NOT_STORED", "ATTACHMENT_TYPE_UNSUPPORTED"):
        affected = [
            raw.files[int(i.path.rsplit("/", 1)[-1])].name for i in issues if i.code == code and raw.files[int(i.path.rsplit("/", 1)[-1])].role == "UNIT_LIST"
        ]
        if affected:
            forced.append((code, f"공급주택목록({', '.join(affected)})을 끝까지 읽지 못했습니다. 원본 목록과 추출 결과를 대조해야 합니다."))
    if pdf_text is None and not text.strip():
        issue("SOURCE_TEXT_EMPTY", review, "/payload/text", "추출할 원문(PDF·수집 글자)이 없습니다.")
    if require_pdf and (pdf_text is None or text_led):
        has_pdf = any(d["kind"] == "PDF" for d in file_documents)
        if any(i.code == "NOTICE_DOC_NOT_PDF" for i in issues) and (text_led or not has_pdf):
            forced.append(("PDF_MISSING", "공고문이 PDF가 아니라(HWP 등) 수집 글자로 추출했습니다. 원문 공고문으로 확인해야 합니다."))
        elif not has_pdf:
            forced.append(("PDF_MISSING", "공고 PDF가 첨부 목록에 없어 수집 글자로 추출했습니다. 원문 PDF로 확인해야 합니다."))
        elif any(i.code == "ATTACHMENT_NOT_STORED" for i in issues):
            forced.append(
                ("PDF_NOT_STORED", "공고 PDF 원본을 S3에서 받지 못해(위치 없음·보관 기한 지남) 수집 글자로 추출했습니다. 원문 PDF로 확인해야 합니다.")
            )
        elif any(i.code == "PDF_TEXT_UNREADABLE" for i in issues):
            names = ", ".join(unreadable_pdfs)
            forced.append(("PDF_TEXT_UNREADABLE", f"공고 PDF({names})에서 글자를 읽지 못해(스캔본 등) 수집 글자로 추출했습니다. 원문 PDF로 확인해야 합니다."))
    elif any(i.code == "PDF_TEXT_UNREADABLE" for i in issues):
        # PDF가 여럿인데 일부만 읽힘: 읽지 못한 쪽이 본문 공고일 수 있으므로 사람 확인 (예전엔 읽힌 신청서 PDF만으로 자동 완료될 수 있었음)
        names = ", ".join(unreadable_pdfs)
        forced.append(("PDF_TEXT_UNREADABLE", f"첨부 PDF 중 일부({names})를 읽지 못했습니다(스캔본 등). 읽지 못한 PDF가 공고 본문인지 확인해야 합니다."))
    if any(i.code == "PDF_TOO_LONG" for i in issues):
        forced.append(("PDF_TOO_LONG", f"공고 PDF가 너무 길어 앞 {MAX_PAGES}쪽만 읽었습니다. 뒤쪽 내용을 원문으로 확인해야 합니다."))
    if scanned_pages:
        # 어느 쪽인지 적어야 검수자가 그 쪽만 원문으로 봅니다 (쪽 번호는 PDF_PAGES_UNREADABLE 문제와 같은 목록, 앞 10쪽까지)
        pages = "; ".join(scanned_pages)
        forced.append(("PDF_PAGES_UNREADABLE", f"공고 PDF의 많은 쪽이 그림(스캔)이라 글자로 읽지 못했습니다({pages}). 원문 PDF의 그 쪽을 확인해야 합니다."))

    for index, unit in enumerate(raw.units):
        if unit.get("checks"):
            issue("UNIT_VALUES_CLEARED", ready, f"/payload/units/{index}/checks", "collector가 비운 값이 있어 원문 확인이 필요합니다.")

    api_reference = None
    notice_ids = api_notice_ids(raw.api_data) if raw.api_data is not None else []
    if len(notice_ids) > 1:
        shown = ", ".join(notice_ids[:3]) + (f" 외 {len(notice_ids) - 3}개" if len(notice_ids) > 3 else "")
        issue(
            "API_REFERENCE_IDENTITY_CONFLICT",
            review,
            "/payload/apiData",
            f"API 응답에 서로 다른 기관 공고 ID가 여럿 있어({shown}) 어느 공고의 응답인지 정할 수 없습니다.",
        )
    elif notice_ids:
        api_reference = api_reference_from_event(raw, notice_ids[0])
    else:
        if raw.api_data is not None:
            # 공고 ID 없는 응답은 어느 공고 것인지 확인할 수 없어 대조 기준으로 쓰지 않습니다. 추출은 막지 않고 조회 구현(있으면)으로 넘어갑니다
            issue("API_REFERENCE_ID_MISSING", ready, "/payload/apiData", "API 응답에서 기관 공고 ID를 찾지 못해 대조 기준으로 쓰지 않습니다.")
        api_reference = (api_provider or NoApiReference()).find(raw)
    if api_reference is not None:
        same = api_reference.source_code == raw.source_code and api_reference.raw_post_id == raw.raw_post_id and api_reference.raw_version == raw.version
        if not same or not api_reference.source_notice_id.strip():
            issue("API_REFERENCE_IDENTITY_CONFLICT", review, "/apiReference", "다른 공고·버전의 API 응답이거나 기관 공고 ID가 비어 있습니다.")
            api_reference = None
        elif not SHA256.fullmatch(api_reference.sha256) or sha256_hex(api_reference.body) != api_reference.sha256:
            issue("API_REFERENCE_HASH_MISMATCH", review, "/apiReference", "API 응답 원본의 해시가 기록과 다릅니다.")
            api_reference = None

    status = max((i.status for i in issues), key=lambda s: s.value, default=ready)
    if status is not ready:
        return IntakeResult(status, tuple(issues), raw)

    documents = [
        {
            "id": TEXT_DOCUMENT_ID,
            "kind": "TEXT",
            "name": "수집 원문 텍스트",
            "sha256": sha256_hex(text.encode("utf-8")),
            "originalUrl": None,  # collector가 합친 텍스트라 기관 원문 링크가 따로 없습니다
            "pageCount": None,
        }
    ]
    if raw.units:
        documents.append(
            {
                "id": UNITS_DOCUMENT_ID,
                "kind": "UNITS",
                "name": "수집 호별 표",
                "sha256": sha256_hex(units_bytes(raw.units)),
                "originalUrl": None,
                "pageCount": None,
            }
        )
    documents.extend(file_documents)
    if attachment_text is not None:
        documents.append(
            {
                "id": PDF_TEXT_DOCUMENT_ID,
                "kind": "TEXT",
                "name": ("수집 원문 텍스트 + " if text_led else "")
                + ("첨부 PDF·엑셀에서 읽은 글자 (쪽·표 구분)" if sheets else "첨부 PDF에서 읽은 글자 (쪽·표 구분)"),
                "sha256": sha256_hex(attachment_text.encode("utf-8")),
                "originalUrl": None,
                "pageCount": None,
            }
        )

    context = TrustedContext(
        input={
            "eventId": raw.event_id,
            "rawPostId": raw.raw_post_id,
            "rawVersion": raw.version,
            "field": raw.field,
            "reprocess": raw.reprocess,
        },
        source_references=(
            {
                "sourceCode": raw.source_code,
                "sourceNoticeId": api_reference.source_notice_id if api_reference else None,
                "rawPostId": raw.raw_post_id,
                "rawVersion": raw.version,
                "kind": raw.kind,
                "supersedesPostId": raw.supersedes_post_id,
                "detailUrl": public_url(raw.detail_url),
                "sourceTitle": raw.title,
                "sourceStatusText": None,  # raw v1에 목록 상태가 없습니다
                "postedOn": raw.posted_on,
            },
        ),
        documents=tuple(documents),
        api_comparison_status="NOT_RUN" if api_reference else "SKIPPED_NO_API_REFERENCE",
        api_reference=api_reference,
        forced_review=tuple(forced),
    )
    material = ExtractionMaterial(
        text=attachment_text if attachment_text is not None else text,
        text_document_id=PDF_TEXT_DOCUMENT_ID if attachment_text is not None else TEXT_DOCUMENT_ID,
        units=raw.units,
        units_document_id=UNITS_DOCUMENT_ID if raw.units else None,
        files=tuple(material_files),
        pdf_pages=tuple({"documentId": file.document_id, "name": file.name, **parsed.to_json()} for file, parsed in pdf_documents),
        sheets=tuple(sheet_tables),
    )
    return IntakeResult(ready, tuple(issues), raw, context, material)
