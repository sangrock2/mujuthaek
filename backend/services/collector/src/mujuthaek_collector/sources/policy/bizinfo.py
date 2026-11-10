"""기업마당 지원사업 공고 (중소벤처기업부, bizinfo.go.kr 정책정보 개방 API). 중앙부처·지자체·유관기관의 기업 지원 공고.

목록  https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do?crtfcKey=…&dataType=json&searchCnt=0
      {jsonArray: [{pblancId, pblancNm, pblancUrl, jrsdInsttNm, excInsttNm, pldirSportRealmLclasCodeNm(분야 대분류),
       pldirSportRealmMlsfcCodeNm(중분류), trgetNm, reqstBeginEndDe, reqstMthPapersCn, bsnsSumryCn(HTML), hashtags,
       printFlpthNm·printFileNm(본문 출력 파일), flpthNm·fileNm(첨부, '@'로 여러 개), creatPnttm, updtPnttm, inqireCo, totCnt}]}
      searchCnt=0이면 지금 게시 중인 공고 전체가 한 번에 와요 (2026-10-18 1,436건).
상세  목록 한 건에 공고 항목이 다 있어서 따로 부르지 않아요.
거름  1. 창업 공고: 분야 대분류 '창업'(60건) 또는 공고명·해시태그에 창업 단어 (2026-10-18 1,436건 중 179건).
         개요까지 보면 '창업기업 우대' 같은 문구로 공모전·수출 공고가 30건쯤 더 걸려서 보지 않아요.
      2. 그중 창업 공간·지원금·정책자금만 (base.startup_in_scope): 중분류 창업공간지원·사업화지원·예비창업자지원·재기지원,
         대분류 금융(융자·보증)이거나 이름에 공간·자금 단어. 이름에 교육·행사 단어가 있으면 빼요. 179건 중 90건.
      field STARTUP_SUPPORT. 나머지는 SKIPPED로 남겨요.
첨부  API 항목만으로는 부족해요 (개요의 약 절반이 '공고문 참조'). 본문 출력 파일(1,436건 모두, pdf·hwp·hwpx)을 꼭 받아
      글자를 뽑고, 첨부도 받아요. 파일 주소(/cmm/fms/)는 robots.txt가 허용해요.
수정일 updtPnttm
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import body_text, soup
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Request
from mujuthaek_collector.sources.policy.base import (
    NATIONWIDE,
    SIDO,
    UNKNOWN,
    PolicyDetail,
    PolicyItem,
    PolicyPage,
    PolicySource,
    build_url,
    clean,
    int_or_none,
    load_json,
    raise_if_blocking,
    startup_in_scope,
)

API = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

LABELS = {
    "pblancId": "공고 ID",
    "pblancNm": "공고명",
    "pldirSportRealmLclasCodeNm": "지원 분야",
    "pldirSportRealmMlsfcCodeNm": "지원 분야 중분류",
    "jrsdInsttNm": "소관 기관",
    "excInsttNm": "수행 기관",
    "trgetNm": "지원 대상",
    "reqstBeginEndDe": "신청 기간",
    "reqstMthPapersCn": "신청 방법",
    "bsnsSumryCn": "사업 개요",
    "refrncNm": "문의처",
    "hashtags": "해시태그",
    "pblancUrl": "공고 주소",
    "printFileNm": "본문 출력 파일",
    "printFlpthNm": "본문 출력 파일 주소",
    "fileNm": "첨부 파일",
    "flpthNm": "첨부 파일 주소",
    "creatPnttm": "등록일시",
    "updtPnttm": "수정일시",
    "inqireCo": "조회수",
    "totCnt": "전체 건수",
}
HTML_KEYS = {"bsnsSumryCn"}  # 사업 개요는 HTML로 와요. AI에 넘길 때만 글자로 바꾸고 원본은 그대로 둬요
IN_SCOPE_KINDS = {"창업공간지원", "사업화지원", "예비창업자지원", "재기지원"}  # 분야 중분류. 대분류 '금융'(융자·보증)도 넣어요
STARTUP_WORDS = re.compile(r"창업|스타트업|start-?up", re.I)
CENTRAL = re.compile(r"(?:부|처|청|위원회)$")  # 중소벤처기업부, 산업통상부, 특허청 …
REGION_PREFIX = re.compile(r"^\s*\[([^\]]+)\]")  # '[경남] 김해시 …', '[대구ㆍ경북] …'
NOT_REGIONS = {"전국", "비수도권", "수도권"}


def html_text(value: Any) -> str | None:
    if not value:
        return None
    return body_text(soup(str(value))) or None


def files_of(record: dict[str, Any]) -> list[FileRef]:
    """본문 출력 파일을 맨 앞에, 그다음 첨부 ('@'로 이어진 이름·주소를 짝지어요)."""
    pairs = [(record.get("printFileNm"), record.get("printFlpthNm"))]
    names = str(record.get("fileNm") or "").split("@")
    urls = str(record.get("flpthNm") or "").split("@")
    pairs += list(zip(names, urls, strict=False))
    files: list[FileRef] = []
    for name, url in pairs:
        name, url = (name or "").strip(), (url or "").strip()
        if url.startswith("http") and all(f.url != url for f in files):
            files.append(FileRef(name or url.rsplit("=", 1)[-1], url, len(files)))
    return files


def region_of(title: str, agency: str | None) -> tuple[str, list[str]]:
    """공고명 앞 [지역]을 써요 ('ㆍ'로 여러 시도). 없으면 소관 기관이 중앙부처일 때만 전국으로 봐요."""
    found = REGION_PREFIX.match(title or "")
    if found:
        names = [n.strip() for n in found.group(1).split("ㆍ") if n.strip()]
        if names and not NOT_REGIONS.intersection(names):
            return SIDO, names
        return (NATIONWIDE, []) if "전국" in names else (UNKNOWN, [])
    if agency and CENTRAL.search(agency.strip()):
        return NATIONWIDE, []
    return UNKNOWN, []


class BizinfoSource(PolicySource):
    code = "bizinfo"
    name = "기업마당 지원사업 공고"
    provider = "BIZINFO"
    field = "STARTUP_SUPPORT"
    page_size = 100_000  # searchCnt=0이면 한 번에 전체가 와요
    key_env = "BIZINFO_API_KEY"
    labels = LABELS
    volatile_keys = frozenset({"inqireCo", "updtPnttm", "totCnt"})
    listed_keys = ("creatPnttm",)  # 등록일 (처음 수집 개수 제한)
    # 해시태그·파일 이름과 경로·주소·문의처는 AI 입력에서 빼요. 개요의 절반이 '공고문 참조'라 본문 출력 파일(공고문)은 꼭 봐요
    ai_keys = (
        "pblancNm", "pldirSportRealmLclasCodeNm", "pldirSportRealmMlsfcCodeNm", "jrsdInsttNm", "excInsttNm",
        "trgetNm", "reqstBeginEndDe", "reqstMthPapersCn", "bsnsSumryCn",
    )  # fmt: skip

    def list_request(self, page: int, segment: str | None = None) -> Request:
        return Request(build_url(API, {"crtfcKey": self.api_key, "dataType": "json", "searchCnt": 0}))

    def parse_list(self, body: str) -> PolicyPage:
        data = load_json(body, "기업마당 목록")
        rows = data.get("jsonArray") if isinstance(data, dict) else None
        if rows is None:
            message = " ".join(str(v) for v in data.values())[:200] if isinstance(data, dict) else str(data)[:200]
            raise_if_blocking(message)
            raise ParseError(f"기업마당 목록 응답에 jsonArray가 없어요: {message}")
        items = []
        for row in rows:
            record = {k: clean(v) for k, v in row.items()}
            policy_id = record.get("pblancId")
            if not policy_id:
                continue
            marker = str(record.get("updtPnttm") or "") or self.record_marker(record)
            items.append(PolicyItem(str(policy_id), record.get("pblancNm") or str(policy_id), marker, record))
        total = int_or_none(rows[0].get("totCnt")) if rows else 0
        return PolicyPage(items, total, len(rows))

    def wanted(self, item: PolicyItem) -> bool:
        record = item.record
        kind, sub = record.get("pldirSportRealmLclasCodeNm"), record.get("pldirSportRealmMlsfcCodeNm")
        startup = kind == "창업" or bool(STARTUP_WORDS.search(" ".join(str(record.get(k) or "") for k in ("pblancNm", "hashtags"))))
        return startup and startup_in_scope(item.title, category_ok=sub in IN_SCOPE_KINDS or kind == "금융")

    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        record = dict(item.record)
        agency = record.get("jrsdInsttNm")
        scope, names = region_of(item.title, agency)
        summary = html_text(record.get("bsnsSumryCn"))
        return PolicyDetail(
            record=record,
            files=files_of(record),
            detail_url=record.get("pblancUrl"),
            agency=agency,
            region_scope=scope,
            region_names=names,
            categories=[c for c in (record.get("pldirSportRealmLclasCodeNm"), record.get("pldirSportRealmMlsfcCodeNm")) if c],
            modified_at=record.get("updtPnttm"),
            summary=summary.splitlines()[0][:300] if summary else None,
            target=record.get("trgetNm"),
            benefit=summary,
            how_to_apply=record.get("reqstMthPapersCn"),
            apply_period=record.get("reqstBeginEndDe"),
        )

    def body_text(self, record: dict[str, Any]) -> str:
        return super().body_text({k: html_text(v) if k in HTML_KEYS else v for k, v in record.items()})
