"""수집 입력 → 추출 입력 어댑터. 가상 이벤트만 사용하고 네트워크·AI를 호출하지 않습니다."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from mujuthaek_extraction.intake import ApiReference, InMemorySourceReader, IntakeStatus, adapter, build_intake, pdf_reader
from mujuthaek_extraction.intake.pdf_reader import PdfDocument, PdfPage

RAW_POST_ID = "01929a3e-0000-7000-8000-000000000001"
PARENT_POST_ID = "01929a3e-0000-7000-8000-000000000002"
PDF = b"%PDF-1.7 synthetic"
PDF_SHA = hashlib.sha256(PDF).hexdigest()
PDF_KEY = "raw/dcco/1/v2/00-모집공고문.pdf"


def fields(file_type: str, role: str) -> dict:
    """계약의 첨부 칸 중 파일 형식·역할."""
    return {"fileType": file_type, "role": role}


def make_event(**payload_overrides):
    payload = {
        "rawPostId": RAW_POST_ID,
        "version": 2,
        "sourceCode": "dcco",
        "provider": "DCCO",
        "regionCode": None,
        "field": "HOUSING",
        "kind": "NOTICE",
        "title": "2026년 국민임대 입주자 모집공고",
        "postedOn": "2026-10-01",
        "detailUrl": "https://www.dcco.kr/web/board/view.do?mId=43&brdIdx=1",
        "supersedesPostId": None,
        "text": "제목: 2026년 국민임대 입주자 모집공고\n신청자격: 무주택세대구성원",
        "textKey": None,
        "units": [{"houseType": "26A", "areaM2": 26.37, "depositWon": 12_000_000, "rentWon": 150_000}],
        "files": [
            {
                "name": "모집공고문.pdf",
                "downloadUrl": "https://www.dcco.kr/web/board/download.do?fidx=1",
                "sha256": PDF_SHA,
                "fileType": "pdf",
                "role": "NOTICE_DOC",
                "s3Key": PDF_KEY,
            }
        ],
        "reprocess": False,
    }
    payload.update(payload_overrides)
    return {
        "eventId": "01929a3e-0000-7000-8000-0000000000e1",
        "eventType": "raw.notice.collected",
        "schemaVersion": 1,
        "occurredAt": "2026-10-15T01:23:45.678Z",
        "producer": "collector",
        "payload": payload,
    }


def codes(result):
    return {i.code for i in result.issues}


@pytest.fixture
def reader():
    return InMemorySourceReader(texts={}, files={"raw/dcco/1/v2/00-모집공고문.pdf": PDF})


def contract_validator(pointer):
    root = next(p for p in Path(__file__).resolve().parents if (p / "contracts" / "schemas").is_dir()) / "contracts" / "schemas"
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in root.glob("*.v1.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas if "$id" in s)
    base = "https://mujuthaek.kr/contracts/schemas/"
    return Draft202012Validator({"$ref": base + pointer}, registry=registry, format_checker=FormatChecker())


def test_ready_separates_trusted_context_from_ai_material(reader):
    result = build_intake(make_event(), reader)

    assert result.status is IntakeStatus.READY
    assert result.context.input == {
        "eventId": "01929a3e-0000-7000-8000-0000000000e1",
        "rawPostId": RAW_POST_ID,
        "rawVersion": 2,
        "field": "HOUSING",
        "reprocess": False,
    }
    assert result.context.api_comparison_status == "SKIPPED_NO_API_REFERENCE"
    assert [d["id"] for d in result.context.documents] == ["text", "units", "file-1"]
    text = make_event()["payload"]["text"]
    assert result.context.documents[0]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    # AI 자료에는 식별자·해시가 들어가지 않습니다.
    material = repr(result.material)
    for secret in (RAW_POST_ID, "0000000000e1", PDF_SHA):
        assert secret not in material


def test_context_matches_extracted_notice_contract(reader):
    context = build_intake(make_event(), reader).context
    errors = list(contract_validator("extracted-notice.v1.json#/properties/input").iter_errors(context.input))
    for ref in context.source_references:
        errors += contract_validator("notice-common.v1.json#/$defs/sourceReference").iter_errors(ref)
    for document in context.documents:
        errors += contract_validator("notice-common.v1.json#/$defs/document").iter_errors(document)
    assert [e.message for e in errors] == []


def test_same_input_gives_same_result(reader):
    assert build_intake(make_event(), reader) == build_intake(make_event(), reader)


@pytest.mark.parametrize(
    "url",
    [
        "HTTPS://www.dcco.kr/web/board/view.do",
        "https://apis.data.go.kr/notice?serviceKey=synthetic",
        "https://user:pw@www.dcco.kr/view.do",
        "https://www.dcco.kr/view do",
        "javascript:alert(1)",
    ],
)
def test_unsafe_or_nonstandard_links_become_null(reader, url):
    event = make_event(detailUrl=url)
    event["payload"]["files"][0]["downloadUrl"] = url
    result = build_intake(event, reader)
    assert result.ready
    assert result.context.source_references[0]["detailUrl"] is None
    assert result.context.documents[-1]["originalUrl"] is None
    assert "synthetic" not in repr(result.context)


def test_no_attachments_and_no_units(reader):
    result = build_intake(make_event(files=[], units=[]), reader)
    assert result.ready and [d["id"] for d in result.context.documents] == ["text"]
    assert result.material.units_document_id is None and result.material.files == ()


def test_non_pdf_attachment_is_noted_and_excluded(reader):
    files = [{"name": "주택목록.hwp", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, **fields("hwp", "UNIT_LIST"), "s3Key": "raw/x/주택목록.hwp"}]
    result = build_intake(make_event(files=files), reader)
    assert result.ready and "ATTACHMENT_TYPE_UNSUPPORTED" in codes(result)
    assert [d["id"] for d in result.context.documents] == ["text", "units"]


def test_excel_attachment_is_registered_and_hash_checked():
    data = b"PK synthetic xlsx"
    sha = hashlib.sha256(data).hexdigest()
    files = [{"name": "주택목록.xlsx", "downloadUrl": "https://x.kr/f", "sha256": sha, **fields("xlsx", "UNIT_LIST"), "s3Key": "raw/x/주택목록.xlsx"}]
    result = build_intake(make_event(files=files), InMemorySourceReader(files={"raw/x/주택목록.xlsx": data}))
    assert result.ready and result.context.documents[-1]["kind"] == "SPREADSHEET"
    assert result.material.files[0].data == data

    files[0]["sha256"] = "0" * 64
    bad = build_intake(make_event(files=files), InMemorySourceReader(files={"raw/x/주택목록.xlsx": data}))
    assert bad.status is IntakeStatus.REVIEW_REQUIRED and "FILE_HASH_MISMATCH" in codes(bad)


def test_material_units_do_not_share_state_with_event(reader):
    event = make_event(units=[{"houseType": "26A", "checks": ["deposit_won=100"]}])
    result = build_intake(event, reader)
    event["payload"]["units"][0]["checks"].append("changed")
    assert result.material.units[0]["checks"] == ["deposit_won=100"]


def test_missing_detail_url_stays_null(reader):
    result = build_intake(make_event(detailUrl=None), reader)
    assert result.ready and result.context.source_references[0]["detailUrl"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.update(eventType="raw.policy.collected"),
        lambda e: e.update(schemaVersion="1"),
        lambda e: e.update(schemaVersion=True),
        lambda e: e["payload"].update(version=0),
        lambda e: e["payload"].update(rawPostId="not-a-uuid"),
        lambda e: e["payload"].update(kind="EXCLUDED"),
        lambda e: e["payload"].pop("text"),
        lambda e: e["payload"].update(files=None),
        lambda e: e.update(traceId=123),
        lambda e: e["payload"]["files"][0].update(sha256="AB" * 32),
        lambda e: e["payload"]["files"][0].update(sha256="ab" * 32 + "\n"),
        # JSON Schema format: uuid가 거부하는 표기는 어댑터도 거부합니다.
        lambda e: e["payload"].update(rawPostId=RAW_POST_ID.replace("-", "")),
        lambda e: e["payload"].update(rawPostId="{" + RAW_POST_ID + "}"),
        lambda e: e.update(eventId="urn:uuid:" + RAW_POST_ID),
        lambda e: e["payload"].update(postedOn="2026-02-30"),
        lambda e: e["payload"].update(sourceCode="dcco\n"),
        lambda e: e["payload"].update(provider=" "),
        lambda e: e["payload"].update(units=[{"areaM2": float("nan")}]),
        lambda e: e["payload"].update(units=[{"raw": {"주택형": "26A"}}]),
    ],
)
def test_malformed_event_is_rejected(reader, mutate):
    event = make_event()
    mutate(event)
    result = build_intake(event, reader)
    assert result.status is IntakeStatus.REJECTED and codes(result) == {"INVALID_EVENT"}
    assert result.context is None and result.material is None


def test_minimal_event_with_only_required_fields_is_ready(reader):
    """팀 이벤트 흐름 문서(2026-10-15): 필수는 rawPostId·version·sourceCode·field·title·text."""
    event = make_event()
    required = {"rawPostId", "version", "sourceCode", "field", "title", "text"}
    event["payload"] = {k: v for k, v in event["payload"].items() if k in required}
    event["payload"]["sourceCode"] = "lh_myhome"
    event["traceId"] = None
    result = build_intake(event, reader)
    assert result.ready
    reference = result.context.source_references[0]
    assert reference["sourceCode"] == "lh_myhome" and reference["kind"] == "NOTICE" and reference["detailUrl"] is None
    assert result.context.input["reprocess"] is False and [d["id"] for d in result.context.documents] == ["text"]


def test_business_space_field_is_accepted(reader):
    assert build_intake(make_event(field="BUSINESS_SPACE"), reader).context.input["field"] == "BUSINESS_SPACE"


def test_truncated_text_is_read_in_full():
    head = "가" * 10
    event = make_event(text=head, textKey="text/dcco/1/v2.txt")
    result = build_intake(event, InMemorySourceReader(texts={"text/dcco/1/v2.txt": head + "나머지"}, files={PDF_KEY: PDF}))
    assert result.ready and result.material.text == head + "나머지"


def test_truncated_text_unavailable_waits(reader):
    result = build_intake(make_event(textKey="text/dcco/1/v2.txt"), reader)
    assert result.status is IntakeStatus.WAITING_SOURCE and "SOURCE_TEXT_UNAVAILABLE" in codes(result)
    assert result.material is None


def test_full_text_that_does_not_extend_event_text_needs_review():
    event = make_event(text="앞부분", textKey="text/dcco/1/v2.txt")
    result = build_intake(event, InMemorySourceReader(texts={"text/dcco/1/v2.txt": "다른 공고"}))
    assert result.status is IntakeStatus.REVIEW_REQUIRED and "SOURCE_TEXT_MISMATCH" in codes(result)


def test_pdf_removed_from_s3_is_extracted_from_text_and_forced_to_review(reader):
    # s3Key가 null이면 보관 기한이 지나 S3에서 지운 원본입니다(재처리): 기다리지 않고 수집 글자로 추출하되 사람 확인
    files = [{"name": "모집공고문.pdf", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, **fields("pdf", "NOTICE_DOC"), "s3Key": None}]
    result = build_intake(make_event(files=files), reader)
    assert result.ready and "ATTACHMENT_NOT_STORED" in codes(result) and result.material.files == ()
    assert [code for code, _ in result.context.forced_review] == ["PDF_NOT_STORED"]


def test_hwp_notice_document_is_extracted_from_text_and_forced_to_review(reader):
    # 공고문이 HWP뿐인 출처(대구·울산 등): collector가 뽑은 글자로 추출하고 사람 확인
    files = [
        {
            "name": "모집공고.hwp",
            "downloadUrl": "https://x.kr/f",
            "sha256": PDF_SHA,
            "fileType": "hwp",
            "role": "NOTICE_DOC",
            "s3Key": "raw/dudc/1/v1/00-모집공고.hwp",
        }
    ]
    result = build_intake(make_event(files=files), reader)
    assert result.ready and "NOTICE_DOC_NOT_PDF" in codes(result) and result.material.text_document_id == "text"
    assert [code for code, description in result.context.forced_review] == ["PDF_MISSING"]
    assert "HWP" in result.context.forced_review[0][1]


@pytest.mark.parametrize(
    ("change", "path"),
    [({"s3Key": "k/a.pdf"}, "/payload/files/0/s3Key"), ({"fileType": "doc"}, "/payload/files/0/fileType"), ({"role": "FORM"}, "/payload/files/0/role")],
)
def test_attachment_fields_follow_the_contract(reader, change, path):
    files = [{"name": "a.pdf", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, **fields("pdf", "NOTICE_DOC"), "s3Key": "raw/x/a.pdf", **change}]
    result = build_intake(make_event(files=files), reader)
    assert result.status is IntakeStatus.REJECTED and result.issues[0].path == path


def test_previous_event_format_without_new_file_fields_is_accepted(reader):
    # fileType·role·s3Key 칸을 추가하기 전 collector의 이벤트: 이름으로 형식·역할을 채우고, 위치가 없어 수집 글자로 추출 + 사람 확인
    files = [
        {"name": "모집공고문.pdf", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA},
        {"name": "주택목록.xlsx", "downloadUrl": "https://x.kr/g", "sha256": PDF_SHA},
    ]
    result = build_intake(make_event(files=files), reader)
    assert result.ready and [i.code for i in result.issues].count("ATTACHMENT_NOT_STORED") == 2 and result.material.files == ()
    assert [(f.file_type, f.role, f.s3_key) for f in result.raw.files] == [("pdf", "NOTICE_DOC", None), ("xlsx", "UNIT_LIST", None)]
    assert {code for code, _ in result.context.forced_review} == {"ATTACHMENT_NOT_STORED", "PDF_NOT_STORED"}


def test_notice_without_pdf_is_extracted_from_text_but_forced_to_review(reader):
    result = build_intake(make_event(files=[]), reader)
    assert result.ready and result.material.text_document_id == "text"
    assert [code for code, _ in result.context.forced_review] == ["PDF_MISSING"]


def test_unreadable_pdf_forces_review(reader):
    result = build_intake(make_event(), reader)  # 시험 PDF 바이트는 진짜 PDF가 아니라 읽을 수 없음
    assert result.ready and "PDF_TEXT_UNREADABLE" in codes(result)
    assert [code for code, _ in result.context.forced_review] == ["PDF_TEXT_UNREADABLE"]


def test_api_json_in_event_becomes_comparison_reference(reader):
    api_data = [{"dsList": [{"PAN_ID": "2015122300020793", "PAN_NT_ST_DT": "2026.09.17"}]}]
    result = build_intake(make_event(apiData=api_data), reader)
    reference = result.context.api_reference
    assert reference.source_notice_id == "2015122300020793" and json.loads(reference.body) == api_data
    assert result.context.api_comparison_status == "NOT_RUN" and "2015122300020793" not in repr(result.material)


def test_delivered_attachment_is_hash_checked(reader):
    files = [
        {
            "name": "모집공고문.pdf",
            "downloadUrl": "https://x.kr/f",
            "sha256": PDF_SHA,
            "fileType": "pdf",
            "role": "NOTICE_DOC",
            "s3Key": "raw/dcco/1/v2/00-모집공고문.pdf",
        }
    ]
    result = build_intake(make_event(files=files), reader)
    assert result.ready and result.material.files[0].data == PDF and result.material.files[0].document_id == "file-1"

    files[0]["sha256"] = "0" * 64
    result = build_intake(make_event(files=files), reader)
    assert result.status is IntakeStatus.REVIEW_REQUIRED and "FILE_HASH_MISMATCH" in codes(result)


def test_delivered_attachment_missing_waits(reader):
    files = [{"name": "a.pdf", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, **fields("pdf", "NOTICE_DOC"), "s3Key": "raw/x/missing.pdf"}]
    result = build_intake(make_event(files=files), reader)
    assert result.status is IntakeStatus.WAITING_SOURCE and "ATTACHMENT_UNAVAILABLE" in codes(result)


@pytest.mark.parametrize(
    ("kind", "supersedes", "code"),
    [
        ("CORRECTION", None, "RELATION_UNRESOLVED"),
        ("FOLLOW_UP", None, "RELATION_UNRESOLVED"),
        ("NOTICE", PARENT_POST_ID, "RELATION_INCONSISTENT"),
        ("CORRECTION", RAW_POST_ID, "RELATION_INCONSISTENT"),
    ],
)
def test_relation_problems_need_review(reader, kind, supersedes, code):
    result = build_intake(make_event(kind=kind, supersedesPostId=supersedes), reader)
    assert result.status is IntakeStatus.REVIEW_REQUIRED and code in codes(result)


def test_linked_correction_keeps_collector_relation(reader):
    result = build_intake(make_event(kind="CORRECTION", supersedesPostId=PARENT_POST_ID), reader)
    assert result.ready
    assert result.context.source_references[0]["supersedesPostId"] == PARENT_POST_ID


def test_unit_checks_are_kept_as_notes_without_changing_values(reader):
    units = [{"houseType": "26A", "checks": ["deposit_won=100"]}]
    result = build_intake(make_event(units=units), reader)
    assert result.ready and "UNIT_VALUES_CLEARED" in codes(result)
    assert result.material.units == tuple(units)


class FixedApi:
    def __init__(self, reference):
        self.reference = reference

    def find(self, raw):
        return self.reference


def api_reference(**overrides):
    body = b'{"PAN_ID":"0000061143"}'
    values = dict(
        source_code="dcco",
        source_notice_id="0000061143",
        raw_post_id=RAW_POST_ID,
        raw_version=2,
        sha256=hashlib.sha256(body).hexdigest(),
        body=body,
    )
    values.update(overrides)
    return ApiReference(**values)


def test_same_version_api_reference_is_kept_out_of_ai_material(reader):
    result = build_intake(make_event(), reader, FixedApi(api_reference()))
    assert result.ready and result.context.api_comparison_status == "NOT_RUN"
    assert result.context.source_references[0]["sourceNoticeId"] == "0000061143"
    assert "PAN_ID" not in repr(result.material)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"raw_version": 1}, "API_REFERENCE_IDENTITY_CONFLICT"),
        ({"raw_post_id": PARENT_POST_ID}, "API_REFERENCE_IDENTITY_CONFLICT"),
        ({"sha256": "0" * 64}, "API_REFERENCE_HASH_MISMATCH"),
        ({"sha256": "not-a-hash"}, "API_REFERENCE_HASH_MISMATCH"),
        ({"source_code": "lh"}, "API_REFERENCE_IDENTITY_CONFLICT"),
        ({"source_notice_id": " "}, "API_REFERENCE_IDENTITY_CONFLICT"),
    ],
)
def test_wrong_api_reference_is_not_used(reader, overrides, code):
    result = build_intake(make_event(), reader, FixedApi(api_reference(**overrides)))
    assert result.status is IntakeStatus.REVIEW_REQUIRED and code in codes(result)
    assert result.context is None


def test_input_event_is_not_modified(reader):
    event = make_event()
    before = copy.deepcopy(event)
    build_intake(event, reader)
    assert event == before


PDF_BODY = "제1장 모집 대상 주택과 신청 자격 안내 " * 10  # read_pdf가 읽었다고 보는 쪽 글자 (빈 쪽 기준보다 김)


def fake_pdf(*empty: int, pages: int = 1) -> PdfDocument:
    return PdfDocument(pages, [PdfPage(n, [] if n in empty else [{"type": "text", "text": PDF_BODY}]) for n in range(1, pages + 1)])


def pdf_file(name: str, **extra) -> dict:
    return {"name": name, "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, "s3Key": PDF_KEY, **extra}


def test_scanned_pages_are_named_in_forced_review(reader, monkeypatch):
    # 검수자가 어느 쪽을 원문으로 봐야 하는지 알 수 있게 사람 확인 설명에 쪽 번호를 넣습니다
    monkeypatch.setattr(adapter, "read_pdf", lambda data: fake_pdf(2, 3, 4, pages=4))
    result = build_intake(make_event(), reader)
    assert result.ready and "PDF_PAGES_UNREADABLE" in codes(result)
    [(code, description)] = result.context.forced_review
    assert code == "PDF_PAGES_UNREADABLE" and "모집공고문.pdf 2, 3, 4쪽" in description


def test_unreadable_pdf_is_named_in_forced_review(reader):
    result = build_intake(make_event(), reader)  # 시험 PDF 바이트는 진짜 PDF가 아니라 읽을 수 없음
    assert "모집공고문.pdf" in result.context.forced_review[0][1]


@pytest.mark.parametrize("name", ["공고문.pdf ", "공고문"])
def test_pdf_is_read_by_file_type_not_by_name(reader, monkeypatch, name):
    # 이름 끝 공백·확장자 없는 이름이라도 fileType이 pdf면 PDF로 읽습니다 (예전엔 조용히 수집 글자로 추출)
    monkeypatch.setattr(adapter, "read_pdf", lambda data: fake_pdf())
    result = build_intake(make_event(files=[pdf_file(name, **fields("pdf", "NOTICE_DOC"))]), reader)
    assert result.ready and result.material.text_document_id == "pdf-text" and PDF_BODY.strip() in result.material.text
    assert result.material.files[0].file_type == "pdf" and result.context.forced_review == ()


def test_notice_body_from_text_is_kept_when_only_the_unit_list_is_a_pdf(reader, monkeypatch):
    # 2026-11-10 코드 검토: 공고문이 HWP이고 목록만 PDF면 목록 PDF 글자가 원문을 통째로 바꿔 수집 글자의 공고 본문(자격 등)이 빠졌음
    monkeypatch.setattr(adapter, "read_pdf", lambda data: fake_pdf())
    files = [
        {"name": "모집공고.hwp", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA, **fields("hwp", "NOTICE_DOC"), "s3Key": "raw/x/a.hwp"},
        pdf_file("주택목록.pdf", **fields("pdf", "UNIT_LIST")),
    ]
    result = build_intake(make_event(files=files), reader)
    text = result.material.text
    assert result.ready and result.material.text_document_id == "pdf-text"
    assert text.startswith(make_event()["payload"]["text"]) and "=== 첨부 주택목록.pdf ===\n" in text and PDF_BODY.strip() in text
    assert [code for code, _ in result.context.forced_review] == ["PDF_MISSING"] and "HWP" in result.context.forced_review[0][1]
    document = next(d for d in result.context.documents if d["id"] == "pdf-text")
    assert document["name"].startswith("수집 원문 텍스트 + ") and document["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_previous_event_format_reads_extension_despite_trailing_space(reader):
    result = build_intake(make_event(files=[{"name": "모집공고문.PDF  ", "downloadUrl": "https://x.kr/f", "sha256": PDF_SHA}]), reader)
    assert [(f.file_type, f.role) for f in result.raw.files] == [("pdf", "NOTICE_DOC")]


def test_spreadsheet_with_trailing_space_in_name_is_read(monkeypatch):
    data = b"PK synthetic xlsx"
    sha = hashlib.sha256(data).hexdigest()
    files = [{"name": "주택목록.xlsx ", "downloadUrl": "https://x.kr/f", "sha256": sha, **fields("xlsx", "UNIT_LIST"), "s3Key": "raw/x/a.xlsx"}]
    listing = SimpleNamespace(truncated=False, rows=1, text="주택형 | 임대보증금\n26A | 12,000,000", sheets=())
    monkeypatch.setattr(adapter, "read_xlsx", lambda data: listing)
    result = build_intake(make_event(files=files), InMemorySourceReader(files={"raw/x/a.xlsx": data}), require_pdf=False)
    assert result.ready and result.material.text_document_id == "pdf-text"
    assert "=== 첨부 엑셀 주택목록.xlsx  ===\n주택형 | 임대보증금" in result.material.text


def test_api_json_without_notice_id_is_not_used_as_reference(reader):
    # 기관 공고 ID가 없으면 내부 rawPostId로 채우지 않고 대조 기준으로 쓰지 않습니다
    result = build_intake(make_event(apiData={"dsList": [{"PAN_NT_ST_DT": "2026.09.17"}]}), reader)
    assert result.ready and "API_REFERENCE_ID_MISSING" in codes(result)
    assert result.context.api_reference is None and result.context.api_comparison_status == "SKIPPED_NO_API_REFERENCE"
    assert result.context.source_references[0]["sourceNoticeId"] is None


def test_api_json_with_several_notice_ids_needs_review(reader):
    # 목록 응답처럼 여러 공고가 섞이면 처음 찾은 ID를 고르지 않고 충돌로 봅니다
    api_data = {"dsList": [{"PAN_ID": "2015122300020793"}, {"PAN_ID": "2015122300020794"}]}
    result = build_intake(make_event(apiData=api_data), reader)
    assert result.status is IntakeStatus.REVIEW_REQUIRED and "API_REFERENCE_IDENTITY_CONFLICT" in codes(result)
    assert result.context is None


def test_api_json_repeating_the_same_notice_id_is_kept(reader):
    api_data = {"head": {"panId": "2015122300020793"}, "dsList": [{"PAN_ID": "2015122300020793"}]}
    result = build_intake(make_event(apiData=api_data), reader)
    assert result.ready and result.context.api_reference.source_notice_id == "2015122300020793"


def test_lh_and_myhome_notice_ids_are_different_numbering_not_a_conflict(reader):
    # 실측(2026-10-20 실제 API 시험): LH 공고 ID(PAN_ID)와 마이홈 공고 ID(pblancId)가 한 응답에 함께 옵니다. 같은 공고라 충돌이 아닙니다
    api_data = {"dsSch": [{"PAN_ID": "2015122300020815"}], "myhome": [{"pblancId": "21360", "houseSn": "1"}, {"pblancId": "21360", "houseSn": "2"}]}
    result = build_intake(make_event(apiData=api_data), reader)
    assert result.ready and result.context.api_reference.source_notice_id == "2015122300020815"
    myhome_only = build_intake(make_event(apiData={"item": [{"pblancId": "21360"}]}), reader)
    assert myhome_only.ready and myhome_only.context.api_reference.source_notice_id == "21360"
    two_lh = build_intake(make_event(apiData={"dsSch": [{"PAN_ID": "A"}], "x": [{"panId": "B"}, {"pblancId": "21360"}]}), reader)
    assert "API_REFERENCE_IDENTITY_CONFLICT" in codes(two_lh)


def test_image_pages_cache_keeps_results_not_pdf_bytes(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_reader, "_image_cache", type(pdf_reader._image_cache)())
    monkeypatch.setattr(pdf_reader, "_find_image_pages", lambda data: calls.append(data) or ((1, 0.5),))
    data = b"%PDF-1.7 image"
    assert pdf_reader.image_pages(data) == pdf_reader.image_pages(bytes(data)) == ((1, 0.5),) and len(calls) == 1
    assert list(pdf_reader._image_cache) == [hashlib.sha256(data).hexdigest()]
    for n in range(pdf_reader.IMAGE_CACHE_SIZE + 5):
        pdf_reader.image_pages(b"pdf-%d" % n)
    assert len(pdf_reader._image_cache) == pdf_reader.IMAGE_CACHE_SIZE
