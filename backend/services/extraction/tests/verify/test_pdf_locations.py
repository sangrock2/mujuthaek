"""원문 PDF 위치 (2026-11-11): 근거의 쪽이 어느 첨부 PDF인지, 상세 이벤트의 PDF S3 위치, 문서 모델 id → PDF 쪽, 「추출 과정 보기」 대응표."""

from contextlib import contextmanager

from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.judgment.pages import attach_locator_pages, evidence_pages, page_documents
from mujuthaek_extraction.publish import source_files
from mujuthaek_extraction.review_api import ReviewService
from mujuthaek_extraction.trace_view import trace_view
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.v2.sources import cited_sources

SHA_A, SHA_B = "a" * 64, "b" * 64


def _evidence(text, *quotes):
    return {
        "evidence": [
            {"id": f"ev-{i}", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": text.index(q), "end": text.index(q) + len(q)}, "quote": q}
            for i, q in enumerate(quotes)
        ]
    }


def test_single_pdf_without_headers_is_the_page_document():
    text = "--- 1쪽 ---\n공고 개요\n--- 2쪽 ---\n만 19세 이상\n=== 첨부 엑셀 목록.xlsx ===\n| 101 | 1001 |"
    made = _evidence(text, "공고 개요", "만 19세 이상", "| 101 | 1001 |")
    pages = evidence_pages(made, {"pdf-text": text})
    documents = page_documents(made, pages, text, "pdf-text", [("file-1", "공고문.pdf")])
    assert documents == {"ev-0": "file-1", "ev-1": "file-1"}  # 엑셀 묶음 안 근거는 쪽이 없어 문서도 없음
    attach_locator_pages(made, pages, "pdf-text", documents)
    locators = [e["locator"] for e in made["evidence"]]
    assert locators[1]["page"] == 2 and locators[1]["pageDocumentId"] == "file-1"
    assert "page" not in locators[2] and "pageDocumentId" not in locators[2]


def test_several_pdfs_use_the_attachment_header_before_the_quote():
    text = "\n".join(["=== 첨부 공고문.pdf ===", "--- 1쪽 ---", "공고 개요", "--- 2쪽 ---", "소득 기준", "=== 첨부 정정.pdf ===", "--- 1쪽 ---", "정정 내용"])
    made = _evidence(text, "공고 개요", "소득 기준", "정정 내용")
    pages = evidence_pages(made, {"pdf-text": text})
    pdfs = [("file-1", "공고문.pdf"), ("file-3", "정정.pdf")]
    assert page_documents(made, pages, text, "pdf-text", pdfs) == {"ev-0": "file-1", "ev-1": "file-1", "ev-2": "file-3"}
    # 머리의 차례와 이름이 맞지 않으면(다른 PDF일 수 있음) 정하지 않아요
    assert page_documents(made, pages, text, "pdf-text", [("file-1", "공고문.pdf"), ("file-3", "다른.pdf")]) == {"ev-0": "file-1", "ev-1": "file-1"}
    # 머리가 없는데 PDF가 여럿이면 어느 것인지 몰라요
    plain = "--- 1쪽 ---\n공고 개요"
    made = _evidence(plain, "공고 개요")
    assert page_documents(made, evidence_pages(made, {"pdf-text": plain}), plain, "pdf-text", pdfs) == {}


def test_collected_text_before_the_pdf_has_no_page_document():
    text = "\n".join(["수집 글자 본문", "=== 첨부 목록.pdf ===", "--- 1쪽 ---", "목록 첫 줄"])
    made = _evidence(text, "수집 글자 본문", "목록 첫 줄")
    pages = evidence_pages(made, {"pdf-text": text})
    assert pages == {"ev-1": 1}
    assert page_documents(made, pages, text, "pdf-text", [("file-2", "목록.pdf")]) == {"ev-1": "file-2"}


def test_source_files_copy_s3_keys_of_pdf_documents_with_the_same_hash():
    raw = {
        "files": [
            {"name": "공고문.pdf", "fileType": "pdf", "s3Key": "raw/lh/123/v1/00-공고문.pdf", "sha256": SHA_A},
            {"name": "목록.xlsx", "fileType": "xlsx", "s3Key": "raw/lh/123/v1/01-목록.xlsx", "sha256": SHA_B},
            {"name": "옛.pdf", "fileType": "pdf", "s3Key": None, "sha256": SHA_B},
            {"name": "다른.pdf", "fileType": "pdf", "s3Key": "raw/lh/123/v1/03-다른.pdf", "sha256": SHA_A},
            {"name": "이상.pdf", "fileType": "pdf", "s3Key": "raw/lh/../area/x.pdf", "sha256": SHA_A},
        ]
    }
    candidate = {
        "documents": [
            {"id": "text", "kind": "TEXT", "sha256": SHA_A},
            {"id": "file-1", "kind": "PDF", "sha256": SHA_A},
            {"id": "file-2", "kind": "SPREADSHEET", "sha256": SHA_B},
            {"id": "file-3", "kind": "PDF", "sha256": SHA_B},  # 보관 기한이 지나 위치 없음
            {"id": "file-4", "kind": "PDF", "sha256": SHA_B},  # 해시가 다름
            {"id": "file-5", "kind": "PDF", "sha256": SHA_A},  # 경로가 raw/ 밖으로
            {"id": "file-9", "kind": "PDF", "sha256": SHA_A},  # 수집 이벤트에 없는 첨부
            {"id": "pdf-text", "kind": "TEXT", "sha256": SHA_A},
        ]
    }
    assert source_files(raw, candidate) == [{"documentId": "file-1", "s3Key": "raw/lh/123/v1/00-공고문.pdf"}]
    assert source_files({}, candidate) == []


TEXT = "\n".join(
    [
        "수집 글자 줄",
        "=== 첨부 공고문.pdf ===",
        "--- 1쪽 ---",
        "1. 신청자격",
        "[표 1-1]",
        "| 기준 | 14,202,000 |",
        "--- 2쪽 ---",
        "2. 일정",
        "=== 첨부 정정.pdf ===",
        "--- 1쪽 ---",
        "정정 줄",
        "=== 첨부 엑셀 목록.xlsx ===",
        "[엑셀 시트 공급]",
        "| 동 | 호 |",
        "=== 그림 판독 3쪽 ===",
        "판독 끝",
    ]
)


def test_document_model_locates_ids_under_page_marks_only():
    doc = parse(TEXT)
    assert doc.locate("p1.2") == (1, 1) and doc.locate("p2.1") == (1, 2)
    assert doc.locate("t1-1") == (1, 1) and doc.locate("t1-1.r0.c1") == (1, 1)
    assert doc.locate("d2.p1.1") == (2, 1)
    # 쪽 표시 앞의 수집 글자 줄(p1.1)·엑셀·그림 판독 묶음은 PDF 쪽이 아니에요. 없는 행·id도 없음
    assert doc.locate("p1.1") is None and doc.locate("x1.t1.r0") is None and doc.locate("g1.1") is None
    assert doc.locate("t1-1.r9") is None and doc.locate("p9.1") is None


def test_cited_sources_keep_only_ids_used_in_the_trace():
    doc = parse(TEXT)
    material = ExtractionMaterial(
        TEXT,
        "pdf-text",
        (),
        None,
        (),
        pdf_pages=({"documentId": "file-1", "name": "공고문.pdf", "pageCount": 2}, {"documentId": "file-3", "name": "정정.pdf", "pageCount": 1}),
    )
    traces = [
        {"agent": "eligibility", "turns": [{"calls": [{"name": "add_eligibility", "args": '{"evidence": ["t1-1.r0.c1", "p1.1", "x1.t1.r0"]}'}]}]},
        {"agent": "schedules", "turns": [{"results": [{"result": '{"hits": [{"id": "d2.p1.1"}]}'}], "verify": "p2.1."}]},
    ]
    sources = cited_sources(doc, material, traces)
    assert [d["id"] for d in sources["documents"]] == ["file-1", "file-3"]
    assert sources["refs"] == {
        "t1-1.r0.c1": {"documentId": "file-1", "page": 1, "text": "14,202,000"},
        "d2.p1.1": {"documentId": "file-3", "page": 1, "text": "정정 줄"},
        "p2.1": {"documentId": "file-1", "page": 2, "text": "2. 일정"},
    }


def _usage(traces, sources=None):
    v2 = {"workers": [], "calls": [], "traces": traces}
    if sources is not None:
        v2["sources"] = sources
    return {"totals": {}, "v2": v2}


def test_trace_view_passes_recorded_sources_or_guesses_pages_for_old_jobs():
    recorded = {"documents": [{"id": "file-1", "name": "공고문.pdf", "pageCount": 2}], "refs": {"p1.2": {"documentId": "file-1", "page": 1, "text": "x"}}}
    view = trace_view(_usage([], recorded))
    assert view["documents"] == recorded["documents"] and view["refs"] == recorded["refs"]

    args = '["p1.3", "p2.4", "t3-1.r2.c1", "d2.p1.1", "p9.1", "x1.t1.r0", "d3.p1.1"]'
    traces = [{"agent": "eligibility", "turns": [{"calls": [{"name": "add", "args": args}]}]}]
    pdfs = [{"id": "file-1", "name": "공고문.pdf", "pageCount": 3}, {"id": "file-2", "name": "정정.pdf", "pageCount": 1}]
    view = trace_view(_usage(traces), pdfs)
    assert view["refs"] == {
        "p1.3": {"documentId": "file-1", "page": 1, "text": None},
        "p2.4": {"documentId": "file-1", "page": 2, "text": None},
        "t3-1.r2.c1": {"documentId": "file-1", "page": 3, "text": None},
        "d2.p1.1": {"documentId": "file-2", "page": 1, "text": None},
    }  # 쪽 수를 넘는 쪽·엑셀 묶음·없는 PDF는 빼요
    # 수집 글자 뒤에 PDF를 붙인 작업: 수집 글자 줄도 p1.N이라 첫 PDF 1쪽 줄은 정하지 않아요
    assert "p1.3" not in trace_view(_usage(traces), pdfs, text_led=True)["refs"]
    assert trace_view(_usage(traces))["refs"] == {}  # PDF가 없는 작업


class FakeStore:
    def __init__(self, files):
        self.files = files

    def job_files(self, job_id):
        return self.files


def test_review_service_files_gives_s3_locations_or_404():
    @contextmanager
    def session(files):
        yield FakeStore(files)

    files = [{"documentId": "file-1", "name": "공고문.pdf", "fileType": "pdf", "s3Key": "raw/lh/1/v1/00-a.pdf", "sha256": SHA_A}]
    assert ReviewService(lambda: session(files), lambda *a: {}).files("j-1") == (200, {"files": files})
    assert ReviewService(lambda: session(None), lambda *a: {}).files("j-1")[0] == 404


def test_payload_with_source_files_and_page_documents_passes_the_event_contract():
    from mujuthaek_extraction.contracts import tools
    from mujuthaek_extraction.publish import approved_payload, completed_payload
    from tests.worker.test_publish import EVENT_SCHEMA, envelope, verified

    candidate = verified()
    pdf = {**candidate["documents"][0], "id": "file-1", "kind": "PDF", "name": "공고문.pdf", "pageCount": 3}
    candidate["documents"].append(pdf)
    ranges = [e for e in candidate["evidence"] if e["locator"]["kind"] == "TEXT_RANGE"]
    attach_locator_pages(candidate, {e["id"]: 2 for e in ranges}, ranges[0]["sourceId"], {ranges[0]["id"]: "file-1"})
    raw = {"files": [{"name": "공고문.pdf", "fileType": "pdf", "s3Key": "raw/lh/9/v1/00-a.pdf", "sha256": pdf["sha256"]}]}
    payload = completed_payload(candidate, provider="가상주거공사", files=source_files(raw, candidate))
    assert payload["sourceFiles"] == [{"documentId": "file-1", "s3Key": "raw/lh/9/v1/00-a.pdf"}]
    assert ranges[0]["locator"]["pageDocumentId"] == "file-1"
    assert tools().validate(envelope(payload), EVENT_SCHEMA) == []
    approved = approved_payload(candidate, provider="가상주거공사", files=source_files(raw, candidate))
    assert approved["sourceFiles"] == payload["sourceFiles"]
    assert "sourceFiles" not in completed_payload(candidate, provider="가상주거공사")  # PDF 위치가 없으면 칸을 빼요
