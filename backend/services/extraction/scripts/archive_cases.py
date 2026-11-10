"""아카이브 자료 → 가상 raw.notice.collected 이벤트 (실험용). 식별자는 가상 값이며 실제 수집 기록이 아닙니다.

첨부 PDF는 S3 키가 정해지기 전이라 시험용 위치(s3Key: raw/...)를 붙이고 source_files로 내용을 넘깁니다.
읽는 쪽은 InMemorySourceReader(files=case.source_files)를 쓰면 S3에서 읽은 것과 같은 경로로 처리됩니다.

API 원본은 대조용 ApiReference로만 넘기고 AI 입력(원문·호별 표)에는 넣지 않습니다.
`lh_units`는 LH 공급정보 API 응답(dsList02)이므로 collector 호별 표로 쓰지 않습니다(API 값이 AI 입력에 섞이지 않게).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mujuthaek_extraction.intake import ApiReference


@dataclass(frozen=True)
class Case:
    name: str
    event: dict[str, Any]
    api_reference: ApiReference | None
    default_sido: str | None
    legacy_quotes: list[str] | None  # 과거 실험 출력의 인용문 (비교용)
    source_files: dict[str, bytes] = field(default_factory=dict)  # 시험용 PDF (S3 키 대신 쓰는 위치 → 내용)


def file_fields(name: str, key: str) -> dict:
    """이벤트 첨부의 계약 칸: 파일 형식·역할·S3 경로."""
    file_type = name.rsplit(".", 1)[-1].lower()
    return {"fileType": file_type, "role": "UNIT_LIST" if file_type.startswith("xls") else "NOTICE_DOC", "s3Key": key}


def _event(raw_post_id: str, source: str, provider: str, title: str, posted_on: str | None, detail_url, text: str, files) -> dict[str, Any]:
    return {
        "eventId": raw_post_id[:-4] + "e000",
        "eventType": "raw.notice.collected",
        "schemaVersion": 1,
        "occurredAt": "2026-10-15T00:00:00Z",
        "producer": "collector",
        "payload": {
            "rawPostId": raw_post_id,
            "version": 1,
            "sourceCode": source,
            "provider": provider,
            "regionCode": None,
            "field": "HOUSING",
            "kind": "NOTICE",
            "title": title,
            "postedOn": posted_on,
            "detailUrl": detail_url,
            "supersedesPostId": None,
            "text": text,
            "textKey": None,
            "units": [],
            "files": files,
            "reprocess": True,
        },
    }


def _quotes(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("quote"), str):
            found.append(value["quote"])
        for child in value.values():
            found += _quotes(child)
    elif isinstance(value, list):
        for child in value:
            found += _quotes(child)
    return found


def lh_case(archive: Path, notice_id: str) -> Case:
    text = (archive / "lh_text" / f"{notice_id}.txt").read_bytes().decode("utf-8")
    api_bytes = (archive / "lh_raw" / f"{notice_id}.json").read_bytes()
    listing = json.loads(api_bytes.decode("utf-8-sig"))["목록"]
    pdf = next((archive / "lh_files" / notice_id).glob("*.pdf"))
    key = f"raw/lh/{notice_id}/{pdf.name}"  # S3 키가 정해지기 전 시험용 위치 (collector가 S3에 둔 PDF 대신)
    raw_post_id = f"00000000-0000-7000-8000-{int(notice_id[-8:]):012d}"  # 가상
    posted = listing.get("PAN_NT_ST_DT", "").replace(".", "-") or None
    event = _event(
        raw_post_id,
        "lh",
        "LH",
        listing.get("PAN_NM") or notice_id,
        posted,
        listing.get("DTL_URL"),
        text,
        [{"name": pdf.name, "downloadUrl": "https://apply.lh.or.kr/", "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), **file_fields(pdf.name, key)}],
    )
    event["payload"]["apiData"] = json.loads(api_bytes.decode("utf-8-sig"))  # 선택 칸: API 응답 JSON을 이벤트에 그대로 담음
    reference = ApiReference("lh", notice_id, raw_post_id, 1, hashlib.sha256(api_bytes).hexdigest(), api_bytes)
    legacy_path = archive / "lh_extraction_test" / notice_id / "extraction.json"
    legacy = _quotes(json.loads(legacy_path.read_text(encoding="utf-8"))) if legacy_path.exists() else None
    return Case(f"lh-{notice_id}", event, reference, None, legacy, {key: pdf.read_bytes()})


BOARD_PROVIDERS = {
    "sh": "SH",
    "gh": "GH",
    "ih": "iH",
    "bmc": "부산도시공사",
    "dudc": "대구도시개발공사",
    "dcco": "대전도시공사",
    "umca": "울산도시공사",
    "gbdc": "경상북도개발공사",
    "gndc": "경상남도개발공사",
    "jbdc": "전북개발공사",
}


def board_case(root: Path, source: str, notice_id: str) -> Case:
    """팀원 수집 폴더(<출처>_files/<공고>_<n>.pdf, <출처>_notices.json)의 공고 하나.

    PDF만 믿습니다. 목록의 제목·날짜·주소와 <출처>_text 글자는 틀릴 수 있어 AI 입력에 쓰지 않습니다:
    수집 글자 자리에는 제목만 넣고(PDF를 읽으면 PDF 글자로 추출), 제목·날짜는 원본 참조 표시에만 씁니다.
    """
    pdfs = sorted((root / f"{source}_files").glob(f"{notice_id}_*.pdf"), key=lambda p: p.stem)
    if not pdfs:
        raise FileNotFoundError(f"{source}_files/{notice_id}_*.pdf")
    listing: dict[str, Any] = {}
    meta = root / f"{source}_notices.json"
    if meta.exists():
        listing = (json.loads(meta.read_text(encoding="utf-8")) or {}).get(notice_id) or {}
    title = (listing.get("title") or "").strip() or pdfs[0].stem
    posted = listing.get("date") if isinstance(listing.get("date"), str) and len(listing["date"]) == 10 else None
    url = listing.get("url") or "https://example.invalid/"
    digest = hashlib.sha256(f"{source}/{notice_id}".encode()).hexdigest()
    raw_post_id = f"00000000-0000-7000-8000-{digest[:12]}"  # 가상
    # 기관 원본 첨부 엑셀(공급주택목록)도 함께 넘깁니다(사용자 결정 2026-10-16: 엑셀이 있으면 바로 읽음)
    sheets = sorted((root / f"{source}_files").glob(f"{notice_id}_*.xlsx"), key=lambda p: p.stem)
    files, contents = [], {}
    for path in sorted([*pdfs, *sheets], key=lambda p: p.stem):
        key = f"raw/{source}/{notice_id}/{path.name}"
        data = path.read_bytes()
        files.append({"name": path.name, "downloadUrl": url, "sha256": hashlib.sha256(data).hexdigest(), **file_fields(path.name, key)})
        contents[key] = data
    event = _event(raw_post_id, source, BOARD_PROVIDERS.get(source, source), title, posted, listing.get("url"), title, files)
    return Case(f"{source}-{notice_id}", event, None, None, None, contents)


def sh_youth_case(archive: Path) -> Case:
    folder = archive / "lh_extraction_test" / "youth-purchased-rental-2026-01"
    pages = json.loads((folder / "source-pages.json").read_text(encoding="utf-8"))
    legacy = json.loads((folder / "extraction.json").read_text(encoding="utf-8"))
    pdf = json.loads((folder / "source.json").read_text(encoding="utf-8"))
    text = "\n".join(page["text"] for page in sorted(pages, key=lambda p: p["page"]))
    event = _event(
        "00000000-0000-7000-8000-000002026010",
        "sh",
        "SH",
        legacy["notice"]["title"],
        legacy["notice"]["announcedOn"],
        None,
        text,
        [
            {
                "name": "공고문.pdf",
                "downloadUrl": "https://www.i-sh.co.kr/",
                "sha256": pdf["sha256"],
                **file_fields("공고문.pdf", "raw/sh/youth-2026-01/공고문.pdf"),
            }
        ],
    )
    source = Path(pdf["path"])
    files = {"raw/sh/youth-2026-01/공고문.pdf": source.read_bytes()} if source.exists() else {}
    return Case("sh-youth-2026-01", event, None, "서울특별시", _quotes(legacy), files)


def all_cases(archive: Path) -> dict[str, Case]:
    cases = [lh_case(archive, "0000061143"), sh_youth_case(archive), lh_case(archive, "0000061176")]
    return {case.name: case for case in cases}
