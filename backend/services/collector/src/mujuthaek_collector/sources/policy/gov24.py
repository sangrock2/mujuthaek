"""행정안전부 대한민국 공공서비스(혜택) 정보 — 정부24 보조금24. 중앙부처·지자체·공공기관의 등록 혜택.

명세  https://infuser.odcloud.kr/api/stages/44436/api-docs (Swagger 2.0, data.go.kr 15113968)
목록  https://api.odcloud.kr/api/gov24/v3/serviceList?page=N&perPage=1000&serviceKey=… (1000건씩 11페이지)
      {page, perPage, totalCount, currentCount, matchCount, data: [{서비스ID, 서비스명, 지원대상, 선정기준, 지원내용,
       신청방법, 신청기한, 상세조회URL, 소관기관명, 소관기관유형, 서비스분야, 조회수, 등록일시, 수정일시 …}]}
상세  /gov24/v3/serviceDetail?cond[서비스ID::EQ]=…   구비서류, 법령·자치법규, 온라인신청사이트URL, 문의처
조건  /gov24/v3/supportConditions?cond[서비스ID::EQ]=… JA0101(남성)~JA2299 Y/N 표시와 대상연령
      상세·조건은 cond 없이 부르면 전체가 페이지로 와요. 열 정책이 많으면 1000건씩 받아 둬요 (정책마다 2번 대신 모두 합쳐 22번)
거름  서비스명·서비스목적요약에 이주 혜택 단어가 있는 정책만 상세를 열어요 (base.SETTLE_WORDS). 서비스분야는 쓰지 않아요
오류  {"code": -401, "msg": "인증키는 필수 항목 입니다."} (HTTP 401)
첨부  보지 않아요 (attachments = NEVER, 이벤트 documentStatus NOT_NEEDED). API에 첨부가 없고, 원문(상세조회URL, www.gov.kr)은
      robots.txt가 막아서(Disallow: /) 요청하지 않아요. 내용은 목록·상세·지원조건 API 칸으로 채워요. 상세조회URL은 사람이 볼 링크(detailUrl)로만 보내요.
"""

from __future__ import annotations

from typing import Any

from mujuthaek_collector.errors import BlockedError, ParseError
from mujuthaek_collector.sources.base import Fetcher, Request
from mujuthaek_collector.sources.policy.base import (
    NATIONWIDE,
    SIDO,
    SIGUNGU,
    UNKNOWN,
    PolicyDetail,
    PolicyItem,
    PolicyPage,
    PolicySource,
    build_url,
    clean,
    load_json,
    raise_if_blocking,
    settle_related,
    split_names,
)

BASE = "https://api.odcloud.kr/api/gov24/v3"

# supportConditions 항목 (Swagger의 설명 그대로)
SUPPORT_CONDITIONS = {
    "JA0101": "남성",
    "JA0102": "여성",
    "JA0201": "중위소득 0~50%",
    "JA0202": "중위소득 51~75%",
    "JA0203": "중위소득 76~100%",
    "JA0204": "중위소득 101~200%",
    "JA0205": "중위소득 200% 초과",
    "JA0301": "예비부모/난임",
    "JA0302": "임산부",
    "JA0303": "출산/입양",
    "JA0313": "농업인",
    "JA0314": "어업인",
    "JA0315": "축산업인",
    "JA0316": "임업인",
    "JA0317": "초등학생",
    "JA0318": "중학생",
    "JA0319": "고등학생",
    "JA0320": "대학생/대학원생",
    "JA0322": "해당사항없음(학생·직업)",
    "JA0326": "근로자/직장인",
    "JA0327": "구직자/실업자",
    "JA0328": "장애인",
    "JA0329": "국가보훈대상자",
    "JA0330": "질병/질환자",
    "JA0401": "다문화가족",
    "JA0402": "북한이탈주민",
    "JA0403": "한부모가정/조손가정",
    "JA0404": "1인가구",
    "JA0410": "해당사항없음(가구)",
    "JA0411": "다자녀가구",
    "JA0412": "무주택세대",
    "JA0413": "신규전입",
    "JA0414": "확대가족",
    "JA1101": "예비창업자",
    "JA1102": "영업중",
    "JA1103": "생계곤란/폐업예정자",
    "JA1201": "음식점업",
    "JA1202": "제조업(소상공인)",
    "JA1299": "기타업종(소상공인)",
    "JA2101": "중소기업",
    "JA2102": "사회복지시설",
    "JA2103": "기관/단체",
    "JA2201": "제조업(법인)",
    "JA2202": "농업,임업 및 어업",
    "JA2203": "정보통신업",
    "JA2299": "기타업종(법인)",
}
AGE_FROM, AGE_TO = "JA0110", "JA0111"
BULK_PAGE = 1000
BULK_MIN = 20  # 열 정책이 이보다 적으면 정책마다 받는 게 호출이 적어요 (한꺼번에는 상세·조건 합쳐 22번)


def region_of(agency_type: str | None, agency: str | None) -> tuple[str, list[str]]:
    """소관기관유형 → 지역 범위. 실제 값: 시군구, 광역시도, 교육청, 중앙행정기관, 공공기관, 지방공기업, 지방출자_출연기관.
    지방공기업·출연기관은 이름(천안도시공사, 재단법인안산인재육성재단)에 지역이 섞여 있어서 여기서는 모름으로 두고 정제 단계에서 정해요."""
    kind, name = (agency_type or "").strip(), (agency or "").strip()
    if kind in ("중앙행정기관", "공공기관"):
        return NATIONWIDE, []
    if kind == "시군구" and name:
        return SIGUNGU, [name]  # '경상북도 성주군'
    if kind == "광역시도" and name:
        return SIDO, [name]  # '부산광역시'
    if kind == "교육청" and name.endswith("교육청"):
        return SIDO, [name.removesuffix("교육청").strip()]  # '경상북도교육청' → '경상북도'
    return UNKNOWN, []


def age_or_none(value: Any) -> int | None:
    """지원조건의 나이. 120처럼 사람 나이를 넘는 값은 '제한 없음'이라 비워요."""
    try:
        age = int(value)
    except (TypeError, ValueError):
        return None
    return age if 0 <= age < 100 else None


def read_data(body: str, what: str) -> dict[str, Any]:
    data = load_json(body, what)
    if not isinstance(data, dict) or "data" not in data:
        code = data.get("code") if isinstance(data, dict) else None
        message = f"{code} {data.get('msg', '')}" if isinstance(data, dict) else str(data)[:120]
        raise_if_blocking(message)
        if isinstance(code, int) and -500 < code <= -400:  # -401 인증키 없음·틀림 등
            raise BlockedError(f"보조금24 API가 요청을 거부했어요: {message}")
        raise ParseError(f"보조금24 {what} 응답에 data가 없어요: {message}")
    return data


def conditions(row: dict[str, Any]) -> dict[str, Any]:
    """supportConditions 한 건 → {"대상": [...], "대상연령": "19~39"}. Y로 표시된 항목만 남겨요."""
    picked = [label for code, label in SUPPORT_CONDITIONS.items() if str(row.get(code) or "").upper() == "Y"]
    out: dict[str, Any] = {}
    if picked:
        out["대상"] = picked
    low, high = row.get(AGE_FROM), row.get(AGE_TO)
    if low not in (None, "") or high not in (None, ""):
        out["대상연령"] = f"{low if low not in (None, '') else ''}~{high if high not in (None, '') else ''}"
    return out


class Gov24Source(PolicySource):
    code = "gov24"
    name = "정부24 보조금24 (행정안전부 공공서비스 혜택)"
    provider = "GOV24"
    page_size = BULK_PAGE
    key_env = "DATA_GO_KR_SERVICE_KEY"
    attachments = "NEVER"  # 원문(www.gov.kr)은 robots.txt 금지, API에는 첨부가 없어요
    volatile_keys = frozenset({"조회수", "수정일시"})
    listed_keys = ("등록일시",)  # 등록일 (처음 수집 개수 제한)
    # 지원조건(체크 목록)은 규칙으로 옮기고, 구비서류·문의처·주소·법령은 화면에 원본 그대로 써서 AI 입력에서 빼요
    ai_keys = ("서비스명", "서비스분야", "서비스목적요약", "지원유형", "사용자구분", "지원대상", "선정기준", "지원내용", "신청기한", "신청방법")

    def __init__(self, api_key: str | None):
        super().__init__(api_key)
        self.details: dict[str, dict[str, Any]] = {}  # prefetch로 받아 둔 상세 (서비스ID → 행)
        self.conditions: dict[str, dict[str, Any]] = {}

    def list_request(self, page: int, segment: str | None = None) -> Request:
        return Request(build_url(f"{BASE}/serviceList", {"page": page, "perPage": self.page_size, "serviceKey": self.api_key}))

    def parse_list(self, body: str) -> PolicyPage:
        data = read_data(body, "목록")
        items = []
        for row in data.get("data") or []:
            record = {k: clean(v) for k, v in row.items()}
            policy_id = record.get("서비스ID")
            if not policy_id:
                continue
            marker = str(record.get("수정일시") or "") or self.record_marker(record)
            items.append(PolicyItem(str(policy_id), record.get("서비스명") or str(policy_id), marker, record))
        return PolicyPage(items, data.get("totalCount"), len(data.get("data") or []))

    def wanted(self, item: PolicyItem) -> bool:
        return settle_related(item.record.get("서비스명"), item.record.get("서비스목적요약"))

    def prefetch(self, client: Fetcher, policy_ids: list[str]) -> None:
        self.details, self.conditions = {}, {}
        if len(policy_ids) < BULK_MIN:
            return
        wanted = set(policy_ids)
        details = self.bulk(client, "serviceDetail", "상세", wanted)
        self.conditions = self.bulk(client, "supportConditions", "지원조건", wanted)
        self.details = details  # 상세를 다 받은 뒤에 써요 (중간에 실패하면 정책마다 받아요)

    def bulk(self, client: Fetcher, endpoint: str, what: str, wanted: set[str]) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        fetched = 0
        for page in range(1, 100):
            data = read_data(client.text(build_url(f"{BASE}/{endpoint}", {"page": page, "perPage": BULK_PAGE, "serviceKey": self.api_key})), what)
            batch = data.get("data") or []
            for row in batch:
                if str(row.get("서비스ID")) in wanted:
                    rows[str(row["서비스ID"])] = row
            fetched += len(batch)
            if len(batch) < BULK_PAGE or fetched >= (data.get("totalCount") or 0):
                break
        return rows

    def detail_requests(self, item: PolicyItem) -> list[Request]:
        if item.policy_id in self.details:
            return []  # prefetch로 받아 둠
        params = {"page": 1, "perPage": 1, "cond[서비스ID::EQ]": item.policy_id, "serviceKey": self.api_key}
        return [Request(build_url(f"{BASE}/serviceDetail", params)), Request(build_url(f"{BASE}/supportConditions", params))]

    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        if bodies:
            detail_rows = read_data(bodies[0], "상세").get("data") or []
            condition_rows = (read_data(bodies[1], "지원조건").get("data") or []) if len(bodies) > 1 else []
        else:
            detail_rows = [self.details[item.policy_id]] if item.policy_id in self.details else []
            condition_rows = [self.conditions[item.policy_id]] if item.policy_id in self.conditions else []
        if not detail_rows:
            raise ParseError(f"보조금24 상세가 비어 있어요: {item.policy_id}")
        record = {**item.record, **{k: clean(v) for k, v in detail_rows[0].items()}}
        if condition_rows:
            record["지원조건"] = conditions(condition_rows[0])
        detail_url = record.get("상세조회URL")
        agency = record.get("소관기관명")
        scope, names = region_of(record.get("소관기관유형"), agency)
        return PolicyDetail(
            record=record,
            detail_url=detail_url,  # 사람이 볼 링크로만. 원문은 열지 않아요 (robots.txt 금지)
            apply_url=record.get("온라인신청사이트URL"),
            agency=agency,
            region_scope=scope,
            region_names=names,
            categories=split_names(record.get("서비스분야")),
            modified_at=item.record.get("수정일시") or record.get("수정일시"),  # 목록은 '20260129201825', 상세는 '2026-01-29'라 목록 값을 써요
            summary=record.get("서비스목적요약") or record.get("서비스목적"),
            target=record.get("지원대상"),
            criteria=record.get("선정기준"),
            benefit=record.get("지원내용"),
            how_to_apply=record.get("신청방법"),  # 상세 값(설명 글)이 목록 값(분류)을 덮어써요
            apply_period=record.get("신청기한"),
            documents=record.get("구비서류"),
            age_min=age_or_none(condition_rows[0].get(AGE_FROM)) if condition_rows else None,
            age_max=age_or_none(condition_rows[0].get(AGE_TO)) if condition_rows else None,
        )
