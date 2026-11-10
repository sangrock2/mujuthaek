"""마이홈포털 공공주택 모집공고 API (공공데이터포털 15108420): 공공임대·공공분양 공고 목록.

LH 수집에 마이홈을 같이 쓰는 이유 (2026-10-14·15 같은 공고의 LH·마이홈 원본 비교):
- LH API에 없는 값이 있어요: 필지 고유번호(pnu, 앞 5자리가 시군구 코드), 시도·시군구·도로명으로 나뉜 주소,
  주택 종류(아파트·다세대 등), 단지별 금액 숫자(공고문 표와 대조용)
- LH가 '접수마감'으로 바꾼 상시모집·선착순 공고도 마이홈에는 계속 게시돼 있어요 (LH 마감 전 목록에서는 빠짐)

응답은 받은 그대로 저장하고, 여기서는 LH 공고 ID로 묶는 데 필요한 값만 꺼내요.
마이홈 한 줄은 공고가 아니라 단지(houseSn) 하나예요. LH 공고 하나가 지역·단지별로 여러 줄이 돼요.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from mujuthaek_collector.sources.base import Fetcher
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.api import NotJson, RawResponse, fetch_json


class MyHomeApiError(Exception):
    """마이홈 API가 오류 응답을 줌 (예: 인증키에 이 API 활용신청이 안 됨)."""


def _body(data: Any) -> dict[str, Any]:
    response = data.get("response") if isinstance(data, dict) else None
    if not isinstance(response, dict):
        raise MyHomeApiError(f"마이홈 API 응답 형식이 다름: {str(data)[:300]}")
    header = response.get("header") or {}
    if header.get("resultCode") != "00":
        raise MyHomeApiError(f"마이홈 API 오류 응답: {header}")
    return response.get("body") or {}


def items(data: Any) -> list[dict[str, Any]]:
    """응답의 공고 줄. 한 줄뿐이면 목록이 아니라 객체로 올 수 있다."""
    found = _body(data).get("item") or []
    return found if isinstance(found, list) else [found]


def total_count(data: Any) -> int:
    return int(_body(data).get("totalCount") or 0)


def lh_notice_id(item: dict[str, Any]) -> str | None:
    """LH 공고 줄이면 LH 공고 ID(PAN_ID). 마이홈 url의 panId가 LH 공고 ID다."""
    if item.get("suplyInsttNm") != config.MYHOME_LH_ORG:
        return None
    return (parse_qs(urlsplit(item.get("url") or "").query).get("panId") or [None])[0]


def row_key(kind: str, item: dict[str, Any]) -> str:
    """마이홈 줄 하나를 가리키는 값: 목록 종류 + 마이홈 공고 ID + 단지 순번."""
    return f"{kind}:{item.get('pblancId')}:{item.get('houseSn')}"


class MyHomeApi:
    def __init__(self, client: Fetcher, service_key: str):
        self.client = client
        self._key = service_key

    def list_pages(self, kind: str) -> list[RawResponse]:
        """kind: 'rent'(공공임대) 또는 'sale'(공공분양). 모든 페이지를 받아요 (상한 config.MAX_LIST_PAGES)."""
        url = f"{config.MYHOME_URL}/{config.MYHOME_LISTS[kind]}"
        pages: list[RawResponse] = []
        seen = 0
        for page in range(1, config.MAX_LIST_PAGES + 1):
            try:
                raw = fetch_json(self.client, f"myhome-{kind}", url, self._key, {"numOfRows": config.MYHOME_PAGE_SIZE, "pageNo": page})
            except NotJson as error:
                raise MyHomeApiError(str(error)) from None
            rows = items(raw.body)
            pages.append(raw)
            seen += len(rows)
            if not rows or seen >= total_count(raw.body):
                break
        return pages
