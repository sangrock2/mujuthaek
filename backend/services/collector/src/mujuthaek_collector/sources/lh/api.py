"""LH 공공데이터 API 3종 (분양임대공고문 목록, 상세정보, 공급정보).

요청은 팀 공통 요청 클라이언트(Fetcher)로 보내요. 응답은 받은 그대로(RawResponse.body) 돌려주고,
요청 값은 함께 남기되 인증키(serviceKey)는 남기지 않아요. 오류 메시지에서도 인증키를 지워요.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from mujuthaek_collector.errors import BlockedError
from mujuthaek_collector.sources.base import Fetcher
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.parse import LhApiError, list_rows, merge_blocks
from mujuthaek_collector.sources.public_data import NotJson, RawResponse, fetch_json, redact

__all__ = ["LhApi", "NotJson", "RawResponse", "detail_params", "fetch_json", "redact", "title_keywords"]


# 거의 모든 공고명에 들어가서 검색어로 쓸모없는 말 (이 말이 들어간 단어는 검색어로 쓰지 않아요)
GENERIC_WORDS = ("임대주택", "분양주택", "입주자", "모집", "공고", "공급", "예비")


def title_keywords(title: str, limit: int = config.LOOKUP_KEYWORDS) -> list[str]:
    """LH 목록 검색용 공고명 단어: [정정공고]·(괄호) 안과 흔한 말을 빼고, 긴 단어(주로 단지명)부터.
    예: '태백소도 국민임대주택 예비입주자 상시모집(26.9.17 공고)' → ['태백소도']"""
    plain = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)
    words = {w for w in plain.split() if len(w) >= 4 and not any(g in w for g in GENERIC_WORDS)}
    return sorted(words, key=lambda w: (-len(w), w))[:limit]


class LhApi:
    def __init__(self, client: Fetcher, service_key: str):
        self.client = client
        self._key = service_key

    def _call(self, api: str, url: str, params: dict[str, Any]) -> RawResponse:
        try:
            raw = fetch_json(self.client, api, url, self._key, params)
            merge_blocks(raw.body)
        except (NotJson, LhApiError) as error:  # 인증키 오류 등은 다음 요청도 똑같이 실패하므로 회차를 멈춰요
            raise BlockedError(f"LH API: {error}") from None
        return raw

    def list_page(self, page: int, **params: Any) -> RawResponse:
        return self._call("list", config.LIST_URL, {"PG_SZ": config.PAGE_SIZE, "PAGE": page, **params})

    def iter_pages(self, max_pages: int = config.MAX_LIST_PAGES, **params: Any) -> Iterator[RawResponse]:
        """목록을 한 페이지씩 받아요. max_pages까지만."""
        seen = 0
        for page in range(1, max_pages + 1):
            raw = self.list_page(page, **params)
            rows = list_rows(raw.body)
            yield raw
            seen += len(rows)
            if not rows or seen >= int(rows[0].get("ALL_CNT") or 0):
                return

    def open_notice_pages(self, today: date) -> list[RawResponse]:
        """아직 마감되지 않은 공고 전부 (게시일 3년 전~오늘, 마감일 오늘 이후). 게시일이 최근인 순서로 와요."""
        start = today - timedelta(days=config.LIST_LOOKBACK_DAYS)
        return list(
            self.iter_pages(
                PAN_ST_DT=start.strftime("%Y%m%d"),
                PAN_ED_DT=today.strftime("%Y%m%d"),
                CLSG_ST_DT=today.strftime("%Y%m%d"),
            )
        )

    def find_row(self, pan_id: str, posted_on: str | None, title: str, today: date) -> tuple[dict[str, str] | None, RawResponse | None]:
        """마감 전 목록에 없는 공고의 목록 줄 찾기 (상세 API에 필요한 다섯 값 때문).

        마이홈에는 게시 중인데 LH가 '접수마감'으로 바꾼 상시모집·선착순 공고가 해당해요.
        1) 공고일 하루치 목록  2) 공고명 단어 검색 (재게시 공고는 공고일이 달라서)
        (찾은 줄, 그 줄이 있던 응답 원본)을 돌려줘요. 못 찾으면 (None, None).
        """
        queries: list[dict[str, str]] = []
        if posted_on and re.fullmatch(r"\d{8}", posted_on):
            queries.append({"PAN_ST_DT": posted_on, "PAN_ED_DT": posted_on})
        start = (today - timedelta(days=config.LIST_LOOKBACK_DAYS)).strftime("%Y%m%d")
        for word in title_keywords(title):
            queries.append({"PAN_ST_DT": start, "PAN_ED_DT": today.strftime("%Y%m%d"), "PAN_NM": word})
        for query in queries:
            for page in self.iter_pages(max_pages=config.LOOKUP_MAX_PAGES, **query):
                for row in list_rows(page.body):
                    if row.get("PAN_ID") == pan_id:
                        return row, page
        return None, None

    def detail(self, row: dict[str, str]) -> RawResponse:
        return self._call("detail", config.DETAIL_URL, detail_params(row))

    def supply(self, row: dict[str, str]) -> RawResponse:
        return self._call("supply", config.SUPPLY_URL, detail_params(row))


def detail_params(row: dict[str, str]) -> dict[str, str]:
    """상세·공급정보 API에 넘길 다섯 값. 하나라도 없으면 API가 빈 응답을 주므로 미리 막아요."""
    missing = [k for k in config.DETAIL_KEYS if not row.get(k)]
    if missing:
        raise ValueError(f"상세 조회에 필요한 값이 없음: {missing} ({row.get('PAN_ID')})")
    return {k: row[k] for k in config.DETAIL_KEYS}
