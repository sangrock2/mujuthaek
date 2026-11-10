"""관리자 「추출 과정 보기」의 근거 id → 원문 PDF 위치 대응표 (2026-11-11).

담당의 도구 인자·결과·검증 메시지에는 문서 모델 id(줄 p3.12 · 표 행 t4-1.r3 · 칸 t4-1.r3.c2 · 둘째 PDF d2.p3.12)가 들어 있어요.
화면이 그 id를 누르면 원문 PDF의 그 쪽을 열고 그 글을 찾아 강조하도록, 작업 기록(usage.v2.sources)에 쓰인 id만 골라 남깁니다.
- 위치는 문서 모델이 쪽 표시(「--- 3쪽 ---」) 아래에서 읽은 줄·표만 정합니다. 수집 글자·엑셀·그림 판독 묶음의 id는 넣지 않아요(틀린 쪽을 가리키지 않게).
- 문서는 원문 글자에 들어간 PDF 차례(material.pdf_pages)와 같은 차례예요. 공개 공고 원문만 담고 사용자 정보는 없어요.
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.v2.document import DocumentModel

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")
TEXT_CHARS = 300  # id마다 남기는 원문 글(화면이 PDF 글자 층에서 찾아 강조)
MAX_REFS = 2_000  # 기록이 너무 커지지 않게


def cited_sources(document: DocumentModel, material: ExtractionMaterial, traces: Any) -> dict[str, Any]:
    """{documents: [{id, name, pageCount}], refs: {id: {documentId, page, text}}}. documents는 PDF 차례 순서예요."""
    documents = [
        {"id": str(p.get("documentId")), "name": str(p.get("name") or ""), "pageCount": p.get("pageCount")} for p in material.pdf_pages if isinstance(p, dict)
    ]
    refs: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for text in _strings(traces):
        for token in TOKEN.findall(text):
            ref = token.rstrip(".-")
            if ref in seen or len(refs) >= MAX_REFS:
                continue
            seen.add(ref)
            located = document.locate(ref)
            if located is None or not 1 <= located[0] <= len(documents):
                continue
            order, page = located
            refs[ref] = {"documentId": documents[order - 1]["id"], "page": page, "text": document.text(ref)[:TEXT_CHARS]}
    return {"documents": documents, "refs": refs}


def _strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _strings(value)
