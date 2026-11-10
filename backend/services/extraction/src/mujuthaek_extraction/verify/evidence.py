"""V2 원문 근거: 문서 해시, 위치 범위, 인용문 포함, 근거 없는 주장, 원문 그대로 적은 조건.

결합기가 계산한 위치를 믿지 않고 완성된 후보를 원문과 다시 맞춰 봅니다(검수자가 고친 결과도 같은 검사를 거칩니다).
"""

from __future__ import annotations

import hashlib
from typing import Any

from mujuthaek_extraction.assemble.quotes import MIN_QUOTE_CHARS, NormalizedText, find_scattered, normalize, strip_markers
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.adapter import units_bytes
from mujuthaek_extraction.verify.model import Finding, PdfTextExtractor, SourceBundle


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_evidence(candidate: dict[str, Any], sources: SourceBundle, pdf_text: PdfTextExtractor | None = None) -> list[Finding]:
    """근거마다 문서 해시·위치·인용문을 원문과 다시 맞춰 보고, 확인된 근거가 없는 항목과 원문에 없는 originalText를 V2 결과로 돌려줍니다."""
    findings: list[Finding] = []
    documents = {d["id"]: d for d in candidate["documents"]}
    verified: set[str] = set()
    indexes: dict[str, NormalizedText] = {}
    pdf_pages: dict[str, list[str] | None] = {}

    def find(code: str, target: str, description: str) -> None:
        findings.append(Finding("V2", code, target, description))

    hash_ok: dict[str, bool] = {}
    for doc_id, document in documents.items():
        if doc_id in sources.texts:
            hash_ok[doc_id] = _sha(sources.texts[doc_id].encode("utf-8")) == document["sha256"]
        elif doc_id in sources.units:
            hash_ok[doc_id] = _sha(units_bytes(sources.units[doc_id])) == document["sha256"]
        elif doc_id in sources.pdfs:
            hash_ok[doc_id] = _sha(sources.pdfs[doc_id]) == document["sha256"]

    for index, item in enumerate(candidate["evidence"]):
        target = f"/evidence/{index}"
        source_id, locator, quote = item["sourceId"], item["locator"], item["quote"]
        if source_id not in documents:
            find("EVIDENCE_SOURCE_UNKNOWN", target, f"후보 문서 목록에 없는 문서입니다: {source_id}")
            continue
        if source_id not in hash_ok:
            find("EVIDENCE_SOURCE_UNAVAILABLE", target, "근거 문서 내용이 전달되지 않아 확인할 수 없습니다.")
            continue
        if not hash_ok[source_id]:
            find("EVIDENCE_SOURCE_HASH_MISMATCH", target, "근거 문서의 해시가 후보 기록과 다릅니다.")
            continue
        if len(normalize(quote)) < MIN_QUOTE_CHARS:
            # 확인된 근거로 치지 않습니다. 예전에는 메모만 남기고 확인된 근거로 쳐서, 「39」 한 줄 근거의 자격 조건도 자동 완료됐습니다(검토 2026-10-16)
            find("EVIDENCE_QUOTE_TOO_SHORT", target, "인용문이 너무 짧아 우연히 일치했을 수 있습니다.")
            continue
        holder = {"TEXT_RANGE": sources.texts, "UNIT_ROW": sources.units}.get(locator["kind"], sources.pdfs)
        if source_id not in holder:
            # 위치 종류와 문서 종류가 다름(글자 범위로 호별 표를 가리키는 등). 검수자가 고친 후보에서 생길 수 있고, 예전엔 여기서 멈췄습니다
            find("EVIDENCE_LOCATOR_KIND_MISMATCH", target, f"{locator['kind']} 위치로 이 문서({source_id})를 가리킬 수 없습니다.")
            continue

        if locator["kind"] == "TEXT_RANGE":
            text = sources.texts[source_id]
            start, end = locator["start"], locator["end"]
            if not 0 <= start < end <= len(text):
                find("EVIDENCE_LOCATOR_OUT_OF_RANGE", target, "근거 위치가 원문 길이를 벗어납니다.")
                continue
            if normalize(quote) in normalize(text[start:end]):
                verified.add(item["id"])
                continue
            elsewhere = indexes.setdefault(source_id, NormalizedText(text)).find_all(normalize(quote))
            if elsewhere:
                spans = ", ".join(f"[{s},{e})" for s, e in elsewhere[:5])
                find("EVIDENCE_LOCATOR_MISMATCH", target, f"인용문이 표시한 위치에는 없고 다른 위치에 있습니다: {spans}")
            else:
                find("EVIDENCE_QUOTE_NOT_FOUND", target, "인용문을 원문에서 찾지 못했습니다.")
        elif locator["kind"] == "UNIT_ROW":
            try:
                row = tools().resolve(list(sources.units[source_id]), locator["pointer"])
            except (KeyError, IndexError, TypeError, ValueError):
                row = None
            if not isinstance(row, dict):
                find("EVIDENCE_LOCATOR_OUT_OF_RANGE", target, "호별 표에 없는 행입니다.")
            elif any(normalize(quote) in normalize(str(v)) for k, v in row.items() if k != "checks"):
                verified.add(item["id"])
            else:
                find("EVIDENCE_QUOTE_NOT_FOUND", target, "인용문이 호별 표 행에 없습니다.")
        else:  # PDF_PAGE
            if source_id not in pdf_pages:
                pdf_pages[source_id] = pdf_text.pages(sources.pdfs[source_id]) if pdf_text else None
            pages = pdf_pages[source_id]
            if pages is None:
                find("EVIDENCE_SOURCE_UNAVAILABLE", target, "PDF 텍스트 추출기가 없어 쪽 근거를 확인할 수 없습니다.")
            elif not 1 <= locator["page"] <= len(pages):
                find("EVIDENCE_LOCATOR_OUT_OF_RANGE", target, "PDF 쪽 범위를 벗어납니다.")
            elif normalize(quote) in normalize(pages[locator["page"] - 1]):
                verified.add(item["id"])
            else:
                find("EVIDENCE_QUOTE_NOT_FOUND", target, "인용문이 표시한 PDF 쪽에 없습니다.")

    contract = tools()
    # 주장 값마다가 아니라 항목마다 한 번 보고합니다(근거 하나가 틀리면 같은 항목의 값 전체가 영향을 받으므로).
    for item_pointer in sorted({p.rsplit("/", 1)[0] for p in contract.claim_paths(candidate)}):
        node = contract.resolve(candidate, item_pointer)
        if not verified.intersection(node.get("evidenceIds", [])):
            find("CLAIM_UNSUPPORTED", item_pointer, "확인된 원문 근거가 없는 항목입니다.")

    joined = "\n".join(sources.texts.values())
    all_text = normalize(joined)
    scatter_index: NormalizedText | None = None
    for path, node in contract.walk(candidate):
        original = node.get("originalText")
        if not isinstance(original, str) or normalize(strip_markers(original)) in all_text:
            continue
        # 순서도·칸 없는 표처럼 글자 순서가 뒤섞인 곳은 결합 단계와 같은 기준(낱말이 가까이 모여 있음)으로 인정합니다
        scatter_index = scatter_index or NormalizedText(joined)
        if not find_scattered(scatter_index, original):
            find("ORIGINAL_TEXT_NOT_FOUND", f"{path}/originalText", "원문 그대로여야 하는 문장이 원문에 없습니다.")
    return findings
