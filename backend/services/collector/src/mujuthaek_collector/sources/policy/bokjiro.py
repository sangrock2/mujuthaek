"""한국사회보장정보원 복지서비스 — 복지로. 중앙부처 복지서비스(data.go.kr 15090532)와 지자체 복지서비스(15108347).

중앙  목록 https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001?callTp=L&pageNo=N&numOfRows=…
      상세 …/NationalWelfaredetailedV001?callTp=D&servId=WLF…
지자체 목록 https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist?pageNo=N&numOfRows=…
      상세 …/LcgvWelfaredetailed?servId=WLF…
응답  XML. 목록은 <totalCount>와 <servList> 여러 개, 상세는 servId·지원대상·선정기준·지원내용과 목록 태그들
      basfrmList(관련 서식), inqplHmpgReldList(관련 홈페이지), baslawList(근거 법령)
      목록 태그의 하위 이름: 중앙 servSeDetailNm(이름)·servSeDetailLink(주소), 지자체 wlfareInfoReldNm·wlfareInfoReldCn
오류  게이트웨이는 <OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR…
첨부  basfrmList 관련 서식 중 안내문·지침만 받아요 (신청서는 받지 않아요). 서식뿐이거나 없으면 관련 홈페이지(원문)에서 공고문을 찾아요.
거름  중앙·지자체 모두 이주 혜택(주거·전입·정착) 단어가 이름·요약에 있는 정책만 상세를 열어요 (base.SETTLE_WORDS). 나머지는 SKIPPED
"""

from __future__ import annotations

from typing import Any

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Request
from mujuthaek_collector.sources.policy.base import (
    NATIONWIDE,
    SIDO,
    SIGUNGU,
    UNKNOWN,
    PolicyDetail,
    PolicyItem,
    PolicyPage,
    PolicySource,
    as_list,
    build_url,
    int_or_none,
    parse_xml,
    settle_related,
    split_names,
    xml_to_dict,
)

API = "https://apis.data.go.kr/B554287"
BOKJIRO_VIEW = "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do"
RESULT_KEYS = {"resultCode", "resultMessage", "totalCount", "pageNo", "numOfRows"}

LABELS = {
    "servId": "서비스ID",
    "servNm": "서비스명",
    "servDgst": "서비스 요약",
    "servDtlLink": "상세 주소",
    "wlfareInfoOutlCn": "서비스 개요",
    "jurMnofNm": "소관부처",
    "jurOrgNm": "소관조직",
    "ctpvNm": "시도",
    "sggNm": "시군구",
    "bizChrDeptNm": "담당부서",
    "inqNum": "조회수",
    "svcfrstRegTs": "최초 등록일",
    "lastModYmd": "최종 수정일",
    "crtrYr": "기준연도",
    "enfcBgngYmd": "시행 시작일",
    "enfcEndYmd": "시행 종료일",
    "lifeArray": "생애주기",
    "lifeNmArray": "생애주기",
    "trgterIndvdlArray": "가구 유형",
    "trgterIndvdlNmArray": "가구 유형",
    "intrsThemaArray": "관심 주제",
    "intrsThemaNmArray": "관심 주제",
    "sprtCycNm": "지원 주기",
    "srvPvsnNm": "제공 유형",
    "onapPsbltYn": "온라인 신청 가능",
    "rprsCtadr": "대표 문의",
    "tgtrDtlCn": "지원 대상",
    "sprtTrgtCn": "지원 대상",
    "slctCritCn": "선정 기준",
    "alwServCn": "지원 내용",
    "aplyMtdCn": "신청 방법",
    "aplyMtdNm": "신청 방법",
    "aplyMtdDc": "신청 방법 설명",
    "applmetList": "신청 방법 상세",
    "basfrmList": "관련 서식",
    "baslawList": "근거 법령",
    "inqplCtadrList": "문의처",
    "inqplHmpgReldList": "관련 홈페이지",
}


def read_list(body: str, what: str) -> tuple[PolicyPage, list[dict[str, Any]]]:
    root = parse_xml(body, what)
    rows = [xml_to_dict(e) for e in root.iter("servList")]
    if not rows and root.find(".//totalCount") is None:
        raise ParseError(f"{what} 응답에 servList·totalCount가 없어요 (응답 모양이 바뀌었는지 확인)")
    return PolicyPage([], int_or_none(root.findtext(".//totalCount")), len(rows)), rows


def read_detail(body: str, what: str) -> dict[str, Any]:
    root = parse_xml(body, what)
    data = xml_to_dict(root)
    if "servId" not in data:  # <response><wantedDtl>…</wantedDtl></response> 처럼 한 번 더 감싼 경우
        inner = next((v for v in data.values() if isinstance(v, dict) and "servId" in v), None)
        if inner is None:
            raise ParseError(f"{what} 응답에 servId가 없어요")
        data = inner
    return {k: v for k, v in data.items() if k not in RESULT_KEYS}


def join_names(*parts: Any) -> str | None:
    """'교육부 학생지원총괄과' + '학생지원총괄과'처럼 겹치는 이름은 한 번만 (소관부처 값에 조직 이름이 이미 들어 있기도 해요)."""
    words: list[str] = []
    for part in parts:
        for word in str(part or "").split():
            if word not in words:
                words.append(word)
    return " ".join(words) or None


def link_items(record: dict[str, Any], key: str) -> list[tuple[str, str]]:
    """basfrmList·inqplHmpgReldList → [(이름, 주소)]. 주소가 http로 시작하지 않는 항목은 빼요.
    하위 태그 이름이 API마다 달라요: 중앙 servSeDetailNm·servSeDetailLink, 지자체 wlfareInfoReldNm·wlfareInfoReldCn."""
    out = []
    for entry in as_list(record.get(key)):
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("servSeDetailLink") or entry.get("wlfareInfoReldCn") or "").strip()
        if url.startswith("http"):
            out.append((entry.get("servSeDetailNm") or entry.get("wlfareInfoReldNm") or "", url))
    return out


def apply_methods(record: dict[str, Any]) -> str | None:
    """중앙 applmetList: 이름은 servSeDetailLink지만 주소가 아니라 '거주지 읍/면/동 주민센터 …' 같은 글이에요."""
    texts = [str(e.get("servSeDetailLink") or "").strip() for e in as_list(record.get("applmetList")) if isinstance(e, dict)]
    return "\n".join(t for t in dict.fromkeys(texts) if t) or None


class BokjiroSource(PolicySource):
    provider = "BOKJIRO"
    key_env = "DATA_GO_KR_SERVICE_KEY"
    labels = LABELS
    volatile_keys = frozenset({"inqNum", "lastModYmd"})
    listed_keys = ("svcfrstRegTs", "lastModYmd")  # 등록일 (처음 수집 개수 제한)
    list_path = ""
    detail_path = ""
    list_params: dict[str, str] = {}
    detail_params: dict[str, str] = {}
    page_size = 500  # 최대 500 (활용가이드)
    reld_code = "01"  # 복지로 화면 주소의 구분 (01 중앙, 02 지자체)

    def list_request(self, page: int, segment: str | None = None) -> Request:
        return Request(build_url(f"{API}/{self.list_path}", {"serviceKey": self.api_key, **self.list_params, "pageNo": page, "numOfRows": self.page_size}))

    def parse_list(self, body: str) -> PolicyPage:
        page, rows = read_list(body, f"{self.name} 목록")
        for record in rows:
            if not record.get("servId"):
                continue
            page.items.append(PolicyItem(str(record["servId"]), record.get("servNm") or str(record["servId"]), self.marker(record), record))
        return page

    def marker(self, record: dict[str, Any]) -> str:
        return self.record_marker(record)

    def wanted(self, item: PolicyItem) -> bool:
        return settle_related(item.record.get("servNm"), item.record.get("servDgst"))

    def detail_requests(self, item: PolicyItem) -> list[Request]:
        return [Request(build_url(f"{API}/{self.detail_path}", {"serviceKey": self.api_key, **self.detail_params, "servId": item.policy_id}))]

    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        record = {**item.record, **read_detail(bodies[0], f"{self.name} 상세")}
        files = [FileRef(name or url.rsplit("/", 1)[-1], url, i) for i, (name, url) in enumerate(link_items(record, "basfrmList"))]
        detail_url = record.get("servDtlLink") or f"{BOKJIRO_VIEW}?wlfareInfoId={item.policy_id}&wlfareInfoReldBztpCd={self.reld_code}"
        homepages = [url for _, url in link_items(record, "inqplHmpgReldList")]
        return PolicyDetail(
            record=record,
            files=files,
            origin_urls=[*homepages, detail_url],
            detail_url=detail_url,
            agency=self.agency(record),
            region_scope=self.scope(record),
            region_names=self.regions(record),
            categories=split_names(record.get("intrsThemaArray") or record.get("intrsThemaNmArray")),
            modified_at=record.get("lastModYmd"),
            summary=record.get("servDgst") or record.get("wlfareInfoOutlCn"),
            target=record.get("tgtrDtlCn") or record.get("sprtTrgtCn"),
            criteria=record.get("slctCritCn"),
            benefit=record.get("alwServCn"),
            how_to_apply=record.get("aplyMtdCn") or apply_methods(record),
        )

    def agency(self, record: dict[str, Any]) -> str | None:
        return join_names(record.get("jurMnofNm"), record.get("jurOrgNm"))

    def scope(self, record: dict[str, Any]) -> str:
        return NATIONWIDE  # 중앙부처 사업

    def regions(self, record: dict[str, Any]) -> list[str]:
        return []


class BokjiroCentralSource(BokjiroSource):
    code = "bokjiro_central"
    name = "복지로 중앙부처 복지서비스"
    list_path = "NationalWelfareInformationsV001/NationalWelfarelistV001"
    detail_path = "NationalWelfareInformationsV001/NationalWelfaredetailedV001"
    list_params = {"callTp": "L", "srchKeyCode": "003"}  # 003: 서비스명+내용 검색 (검색어를 비우면 전체)
    detail_params = {"callTp": "D"}
    weekly_recheck = True  # 중앙부처 목록에는 수정일이 없어요
    # 대상·선정기준·지원내용 칸이 길어서(중앙값 약 3,400자) API만으로 추출해요. 첨부는 수백 쪽짜리 사업 안내 지침서예요
    attachments = "NEVER"
    ai_keys = (
        "servNm", "servDgst", "lifeArray", "trgterIndvdlArray", "intrsThemaArray", "srvPvsnNm", "sprtCycNm",
        "tgtrDtlCn", "slctCritCn", "alwServCn", "applmetList",
    )  # fmt: skip


class BokjiroLocalSource(BokjiroSource):
    code = "bokjiro_local"
    name = "복지로 지자체 복지서비스"
    list_path = "LocalGovernmentWelfareInformations/LcgvWelfarelist"
    detail_path = "LocalGovernmentWelfareInformations/LcgvWelfaredetailed"
    reld_code = "02"
    # 설명 칸이 짧거나 '공고문 참조'인 정책만 첨부·원문을 봐요 (2026-10-19 첨부가 있던 266건 중 약 190건)
    attachments = "WHEN_THIN"
    ai_keys = (
        "servNm", "servDgst", "ctpvNm", "sggNm", "lifeNmArray", "trgterIndvdlNmArray", "intrsThemaNmArray", "srvPvsnNm", "sprtCycNm",
        "sprtTrgtCn", "slctCritCn", "alwServCn", "aplyMtdNm", "aplyMtdCn", "enfcBgngYmd", "enfcEndYmd",
    )  # fmt: skip

    def marker(self, record: dict[str, Any]) -> str:
        return str(record.get("lastModYmd") or "") or self.record_marker(record)

    def agency(self, record: dict[str, Any]) -> str | None:
        return join_names(record.get("ctpvNm"), record.get("sggNm"), record.get("bizChrDeptNm"))

    def scope(self, record: dict[str, Any]) -> str:
        if record.get("sggNm"):
            return SIGUNGU
        return SIDO if record.get("ctpvNm") else UNKNOWN  # 시도만 있으면 시도 전체 사업 (4,822건 중 731건)

    def regions(self, record: dict[str, Any]) -> list[str]:
        """'충청남도' 또는 '부산광역시 해운대구'. 시군구가 쉼표로 여러 개면 하나씩."""
        sido = (record.get("ctpvNm") or "").strip()
        sgg = split_names(record.get("sggNm"))
        if sgg:
            return [f"{sido} {name}".strip() for name in sgg]
        return [sido] if sido else []
