"""온통청년 청년정책 API (한국고용정보원, data.go.kr 15143273). 중앙부처·지자체의 등록 청년정책.

목록  https://www.youthcenter.go.kr/go/ythip/getPlcy?apiKeyNm=…&rtnType=json&pageType=1&pageNum=N&pageSize=500
      {resultCode: 200, resultMessage, result: {pagging: {totCount, pageNum, pageSize}, youthPolicyList: [{plcyNo, plcyNm,
       lclsfNm, mclsfNm, plcySprtCn, sprtTrgtMinAge, sprtTrgtMaxAge, earnCndSeCd, aplyYmd, plcyAplyMthdCn, aplyUrlAddr,
       sbmsnDcmntCn, refUrlAddr1, refUrlAddr2, zipCd, inqCnt, frstRegDt, lastMdfcnDt …}]}}
상세  목록 한 건에 상세 항목이 다 있어서 따로 부르지 않아요 (plcyNo로 한 건 검색도 같은 모양).
분류  분류 조건 없이 전체(약 3,300건)를 500건씩 받아요. 서버의 분류 검색은 믿기 어려워요 (2026-10-15):
      대분류 이름이 예전·새 이름으로 섞여 있고(복지문화 / 금융･복지･문화, 교육 / 교육･직업훈련 …),
      mclsfNm='취약계층 및 금융지원' 검색은 실제 332건인데 0건이 와요. POLICY_YOUTH_CATEGORIES로 대분류를 좁힐 수는 있어요.
거름  주거: 대분류 '주거' 또는 이름·설명에 이주 혜택 단어 (base.SETTLE_WORDS) → field BENEFIT
      창업: 중분류 '창업' 중 창업 공간·지원금·정책자금 정책 → field STARTUP_SUPPORT (base.startup_in_scope, 이름 + 지원 내용).
            교육·컨설팅·경진대회·세제 정책은 빼요. 이름에만 창업이 들어간 다른 중분류도 빼요. 388건 중 276건
      마감: 신청 기간(aplyYmd)이 오늘 전에 끝난 정책은 SKIPPED (상시·기간 칸 없음은 넣어요). 2026-10-19 거름 통과 827건 중 349건.
            SKIPPED도 회차마다 다시 판단해서, 기관이 새 신청 기간으로 고치면 PENDING으로 돌아와요.
첨부  API에 첨부가 없어요. 참고 주소(refUrlAddr1·2, 대부분 기관 원문 공고)를 열어 첨부 링크를 찾아요.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Request
from mujuthaek_collector.sources.policy.base import (
    BENEFIT,
    NATIONWIDE,
    SIGUNGU,
    STARTUP_SUPPORT,
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
    settle_related,
    split_names,
    startup_in_scope,
)

API = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
VIEW = "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail"
ALWAYS_OPEN = "0057002"  # 신청 기간 구분: 0057001 특정 기간, 0057002 상시, 0057003 기간 칸 없음(계속·별도 안내 등)
APPLY_END = re.compile(r"~\s*(\d{8})")

LABELS = {
    "plcyNo": "정책번호",
    "plcyNm": "정책명",
    "plcyKywdNm": "정책 키워드",
    "plcyExplnCn": "정책 설명",
    "lclsfNm": "정책 대분류",
    "mclsfNm": "정책 중분류",
    "plcySprtCn": "지원 내용",
    "sprvsnInstCdNm": "주관기관",
    "operInstCdNm": "운영기관",
    "rgtrInstCdNm": "등록기관",
    "rgtrUpInstCdNm": "등록 상위기관",
    "sprtTrgtMinAge": "지원 대상 최소 연령",
    "sprtTrgtMaxAge": "지원 대상 최대 연령",
    "sprtTrgtAgeLmtYn": "연령 제한 여부",
    "earnCndSeCd": "소득 조건 구분",
    "earnMinAmt": "소득 최소 금액",
    "earnMaxAmt": "소득 최대 금액",
    "earnEtcCn": "소득 기타 조건",
    "mrgSttsCd": "결혼 상태",
    "jobCd": "취업 상태",
    "schoolCd": "학력",
    "plcyMajorCd": "전공",
    "sbizCd": "특화 분야",
    "addAplyQlfcCndCn": "추가 신청 자격",
    "ptcpPrpTrgtCn": "참여 제한 대상",
    "aplyPrdSeCd": "신청 기간 구분",
    "aplyYmd": "신청 기간",
    "bizPrdBgngYmd": "사업 시작일",
    "bizPrdEndYmd": "사업 종료일",
    "bizPrdEtcCn": "사업 기간 기타",
    "plcyAplyMthdCn": "신청 방법",
    "srngMthdCn": "심사 방법",
    "aplyUrlAddr": "신청 주소",
    "sbmsnDcmntCn": "제출 서류",
    "etcMttrCn": "기타 사항",
    "refUrlAddr1": "참고 주소 1",
    "refUrlAddr2": "참고 주소 2",
    "zipCd": "법정 시군구 코드",
    "inqCnt": "조회수",
    "frstRegDt": "최초 등록일",
    "lastMdfcnDt": "최종 수정일",
}


NATIONWIDE_CODES = 200  # 시군구는 전국에 약 250개. 이만큼 넘게 적힌 정책은 전국 사업이에요 (국토교통부 정책 등)


def has_class(value: Any, name: str) -> bool:
    """'주거,주거' · '취업,창업'처럼 쉼표로 여러 개인 분류 값에 name이 있는지."""
    return name in split_names(value)


def age_range(record: dict[str, Any]) -> tuple[int | None, int | None]:
    """나이 하한·상한. 0~0은 '제한 없음'이라 비워요 (sprtTrgtAgeLmtYn은 실제 값과 맞지 않아 쓰지 않아요)."""
    low, high = int_or_none(record.get("sprtTrgtMinAge")), int_or_none(record.get("sprtTrgtMaxAge"))
    return (low or None, high or None)


def apply_ended(record: dict[str, Any], today: date) -> bool:
    """신청 기간(aplyYmd '20260123 ~ 20260202', 여러 구간이면 가장 늦은 마감)이 오늘 전에 끝났는지.
    상시(0057002)나 기간 칸이 없는 정책(0057003, '계속'·'별도 안내' 등)은 끝났다고 보지 않아요."""
    if record.get("aplyPrdSeCd") == ALWAYS_OPEN:
        return False
    ends = APPLY_END.findall(str(record.get("aplyYmd") or ""))
    return bool(ends) and max(ends) < today.strftime("%Y%m%d")


def region_scope(codes: list[str]) -> str:
    if len(codes) >= NATIONWIDE_CODES:
        return NATIONWIDE
    return SIGUNGU if codes else UNKNOWN


def region_codes(value: Any) -> list[str]:
    """zipCd '2818500000,28237…'(법정동 코드) → 시군구 코드 5자리 목록."""
    codes = {code[:5] for code in re.findall(r"\d{5,10}", str(value or ""))}
    return sorted(codes)


class YouthSource(PolicySource):
    code = "youth"
    name = "온통청년 청년정책"
    provider = "YOUTHCENTER"
    key_env = "YOUTHCENTER_API_KEY"
    labels = LABELS
    volatile_keys = frozenset({"inqCnt", "lastMdfcnDt"})
    listed_keys = ("frstRegDt",)  # 등록일 (처음 수집 개수 제한)
    # 결혼·취업·학력·특화·지역 코드(zipCd는 시군구 코드 수백 개)는 규칙으로 옮겨서 AI 입력에서 빼요. 나이·소득 숫자는 짧아서 둬요
    ai_keys = (
        "plcyNm", "lclsfNm", "mclsfNm", "plcyKywdNm", "plcyExplnCn", "plcySprtCn", "sprtTrgtMinAge", "sprtTrgtMaxAge",
        "earnMinAmt", "earnMaxAmt", "earnEtcCn", "addAplyQlfcCndCn", "ptcpPrpTrgtCn", "srngMthdCn", "plcyAplyMthdCn",
        "aplyYmd", "bizPrdBgngYmd", "bizPrdEndYmd", "bizPrdEtcCn", "sprtSclCnt", "etcMttrCn",
    )  # fmt: skip
    page_size = 500

    def __init__(self, api_key: str | None, categories: list[str] | None = None):
        super().__init__(api_key)
        self.categories = categories or []  # 빈 목록이면 전체 분류

    def segments(self) -> list[str | None]:
        return list(self.categories) or [None]  # 빈 목록이면 전체 분류

    def list_request(self, page: int, segment: str | None = None) -> Request:
        params = {"apiKeyNm": self.api_key, "rtnType": "json", "pageType": "1", "pageNum": page, "pageSize": self.page_size, "lclsfNm": segment}
        return Request(build_url(API, params))

    def parse_list(self, body: str) -> PolicyPage:
        data = load_json(body, "온통청년 목록")
        if not isinstance(data, dict):
            raise ParseError("온통청년 목록 응답 모양이 달라요")
        code = data.get("resultCode")
        if code not in (None, 200, "200", 0, "0", "00"):
            message = f"resultCode={code} {data.get('resultMessage', '')}"
            raise_if_blocking(message)
            raise ParseError(f"온통청년 API 오류: {message}")
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        rows = result.get("youthPolicyList")
        if rows is None:
            raise ParseError("온통청년 목록 응답에 youthPolicyList가 없어요 (응답 모양이 바뀌었는지 확인)")
        items = []
        for row in rows:
            record = {k: clean(v) for k, v in row.items()}
            if not record.get("plcyNo"):
                continue
            marker = str(record.get("lastMdfcnDt") or "") or self.record_marker(record)
            items.append(PolicyItem(str(record["plcyNo"]), record.get("plcyNm") or str(record["plcyNo"]), marker, record))
        paging = result.get("pagging") or result.get("paging") or {}
        return PolicyPage(items, int_or_none(paging.get("totCount")), len(rows))

    def wanted(self, item: PolicyItem) -> bool:
        record = item.record
        return has_class(record.get("lclsfNm"), "주거") or self.startup(record) or settle_related(record.get("plcyNm"), record.get("plcyExplnCn"))

    def closed(self, item: PolicyItem, today: date) -> bool:
        return apply_ended(item.record, today)

    def startup(self, record: dict[str, Any]) -> bool:
        return has_class(record.get("mclsfNm"), "창업") and startup_in_scope(record.get("plcyNm"), record.get("plcySprtCn"))

    def field_of(self, record: dict[str, Any]) -> str:
        return STARTUP_SUPPORT if self.startup(record) else BENEFIT

    def parse_detail(self, item: PolicyItem, bodies: list[str]) -> PolicyDetail:
        record = dict(item.record)
        refs = [record.get(k) for k in ("refUrlAddr1", "refUrlAddr2")]
        origins = list(dict.fromkeys(u for u in refs if isinstance(u, str) and u.startswith("http")))
        codes = region_codes(record.get("zipCd"))
        ages = age_range(record)
        return PolicyDetail(
            record=record,
            origin_urls=origins,
            detail_url=f"{VIEW}/{item.policy_id}",
            apply_url=record.get("aplyUrlAddr"),
            agency=record.get("sprvsnInstCdNm") or record.get("rgtrInstCdNm") or record.get("operInstCdNm"),
            region_scope=region_scope(codes),
            region_codes=[] if region_scope(codes) == NATIONWIDE else codes,
            categories=[c for c in (*split_names(record.get("lclsfNm")), *split_names(record.get("mclsfNm"))) if c],
            modified_at=record.get("lastMdfcnDt"),
            summary=record.get("plcyExplnCn"),
            target=record.get("addAplyQlfcCndCn"),  # 추가 신청 자격 (나이·소득·결혼·취업은 코드 칸으로 따로 와요)
            criteria=record.get("srngMthdCn"),  # 심사 방법
            benefit=record.get("plcySprtCn"),
            how_to_apply=record.get("plcyAplyMthdCn"),
            apply_period=record.get("aplyYmd") or record.get("bizPrdEtcCn"),
            documents=record.get("sbmsnDcmntCn"),
            age_min=ages[0],
            age_max=ages[1],
        )
