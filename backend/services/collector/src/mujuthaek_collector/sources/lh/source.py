"""LH 출처 (담당자4). 팀 공통 파이프라인 위에서 돌아요.

게시판 출처와 다른 점
- 목록·상세를 화면이 아니라 공공데이터포털 API로 받아요 (fetch_list·fetch_detail을 바꿔 써요)
- 게시판이 둘이에요
    open    LH 분양임대공고문 API의 마감 전 공고 (게시일 3년 전~오늘, 마감일 오늘 이후)
    myhome  마이홈 모집공고 API 중 LH 공고. LH가 '접수마감'으로 바꿔 open에 없는 상시모집·선착순 공고를 잡아요
  같은 공고는 LH 공고 ID(PAN_ID)가 글 키라서, 두 게시판에 다 있어도 한 번만 저장해요 (역할 분담 4-04)
- 목록은 한 번에 전부 1페이지로 돌려줘요. LH는 마감일이 바뀌면 게시일이 오래된 공고도 목록에 다시 들어와서,
  1페이지만 보고 끝내면 그런 공고를 놓쳐요
- 목록은 오래된 공고부터 돌려줘요. 파이프라인은 목록 순서대로 등록하면서 정정공고의 원래 공고를 찾는데,
  LH API 순서(최신 먼저) 그대로면 정정공고가 원래 공고보다 먼저 등록돼 연결되지 않아요 (2026-10-16 실측: 17건 중 0건)
- 상세는 상세정보 API + 공급정보 API + 같은 공고의 마이홈 줄을 합쳐 원본 하나로 만들어요
- 분류는 공고 유형 칸으로 해요 (classify.py). 첨부는 첨부 종류 칸으로 공고문·주택목록을 골라요 (documents.py)
- 원본 응답은 항목(meta)의 '_raw'에 그대로 넣어요. '_'로 시작하는 항목은 AI 추출 글자에 들어가지 않아요
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from mujuthaek_collector.config import Settings
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.errors import BlockedError, ParseError
from mujuthaek_collector.sources.base import Board, Detail, Fetcher, ListItem, Request, Source
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.api import LhApi
from mujuthaek_collector.sources.lh.classify import classify, classify_title
from mujuthaek_collector.sources.lh.client import LhClient
from mujuthaek_collector.sources.lh.detail import body_text, lh_meta, region_code
from mujuthaek_collector.sources.lh.documents import select_attachments
from mujuthaek_collector.sources.lh.myhome import MyHomeApi, MyHomeApiError, lh_notice_id, row_key
from mujuthaek_collector.sources.lh.myhome import items as myhome_items
from mujuthaek_collector.sources.lh.parse import LhApiError, attachments, list_rows

log = logging.getLogger(__name__)

OPEN, MYHOME = "open", "myhome"


def parse_day(value: str | None) -> date | None:
    """'2026.09.17' 또는 '20260917' → 날짜."""
    text = (value or "").strip()
    for fmt in ("%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def group_myhome_rows(pages: list[tuple[str, str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """마이홈 목록 응답들 [(임대·분양, 받은 시각, 응답)] → LH 공고 ID별 마이홈 줄. 다른 기관 줄과 겹친 줄은 빼요."""
    groups: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for kind, fetched_at, body in pages:
        for item in myhome_items(body):
            pan_id, key = lh_notice_id(item), row_key(kind, item)
            if pan_id and key not in seen:
                seen.add(key)
                groups.setdefault(pan_id, []).append({"list": kind, "key": key, "fetchedAt": fetched_at, "item": item})
    return groups


def oldest_first(items: list[ListItem]) -> list[ListItem]:
    """게시일이 오래된 공고부터. 같은 날이면 공고 ID 순서예요 (나중에 올린 공고일수록 ID가 커요)."""
    return sorted(items, key=lambda item: (item.posted_on or date.max, item.post_key))


# 회차마다 바뀌는 목록 칸(줄 번호·전체 건수, 마이홈 받은 시각). 목록 줄(list_item)에 두면 같은 글도 회차마다 줄이 달라, 목록에 있는 LH 글이
# 매시 모두 UPDATE됐어요(2026-11-10 재검토). 상세 조회·분류는 이 칸을 쓰지 않아요(전체 건수는 목록 API가 쪽을 넘길 때만 씀)
PAGING_KEYS = frozenset({"RNUM", "ALL_CNT"})


def steady_row(row: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in row.items() if key not in PAGING_KEYS}


class LhSource(Source):
    code = "lh"
    name = "LH 한국토지주택공사"
    provider = "LH"
    boards = [Board(OPEN, "LH 마감 전 공고"), Board(MYHOME, "마이홈에만 보이는 LH 공고")]
    prefer_doc = "pdf"

    def __init__(self, today: Callable[[], date] = date.today, clock: Callable[[], float] = time.monotonic):
        self._today = today
        self._clock = clock
        self._myhome_cache: tuple[float, dict[str, list[dict[str, Any]]]] | None = None

    # ── 요청 클라이언트 ────────────────────────────────────────
    def make_client(self, settings: Settings) -> Fetcher:
        # 포털 화면에는 인증키가 URL 인코딩된 채로만 보이기도 해요. 요청할 때 다시 인코딩하므로 한 번 풀어 둬요
        # (+가 공백으로 바뀌지 않게 unquote_plus가 아니라 unquote)
        key = urllib.parse.unquote(os.environ.get(config.API_KEY_ENV) or "") or None
        return LhClient(service_key=key, delay_seconds=settings.delay_seconds, max_file_bytes=settings.max_file_bytes)

    def _apis(self, client: Fetcher) -> tuple[LhApi, MyHomeApi]:
        key = getattr(client, "service_key", None)
        if not key:
            raise BlockedError(f"환경 변수 {config.API_KEY_ENV}(공공데이터포털 인증키)가 없어서 LH 수집을 멈춰요")
        return LhApi(client, key), MyHomeApi(client, key)

    # ── 게시판 규격의 세 함수는 쓰지 않아요 (목록·상세를 API로 받아요) ─────────
    def list_request(self, board: Board, page: int) -> Request:
        raise NotImplementedError("LH는 목록을 API로 받아요 (fetch_list)")

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        """목록 API 응답(JSON) 한 페이지 → 글 목록. JSON이 아니거나 오류 응답이면 ParseError (구조 변경 신호)."""
        try:
            data = json.loads(body)
            if board.key == OPEN:
                return self._open_items(board, list_rows(data))
            kind = next((k for k, endpoint in config.MYHOME_LISTS.items() if f"/{endpoint}" in page_url), "rent")
            return self._myhome_items(board, group_myhome_rows([(kind, "", data)]))
        except (ValueError, LhApiError, MyHomeApiError) as error:
            raise ParseError(f"LH 목록 응답을 읽지 못했어요 (구조 변경 확인 필요): {str(error)[:200]}") from None

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        raise NotImplementedError("LH는 상세를 API로 받아요 (fetch_detail)")

    # ── 목록 ──────────────────────────────────────────────────
    def fetch_list(self, client: Fetcher, board: Board, page: int) -> list[ListItem]:
        if page > 1:
            return []  # 1페이지에 전부 담아요 (위 설명)
        lh, myhome = self._apis(client)
        if board.key == OPEN:
            return self._open_items(board, [row for raw in lh.open_notice_pages(self._today()) for row in list_rows(raw.body)])
        try:
            groups = self._myhome_groups(myhome)
        except MyHomeApiError as error:
            raise ParseError(f"마이홈 목록을 읽지 못했어요: {error}") from None
        return self._myhome_items(board, groups)

    def _open_items(self, board: Board, rows: list[dict[str, str]]) -> list[ListItem]:
        return oldest_first([self._open_item(board, row) for row in rows if row.get("PAN_ID")])

    def _myhome_items(self, board: Board, groups: dict[str, list[dict[str, Any]]]) -> list[ListItem]:
        return oldest_first([self._myhome_item(board, pan_id, entries) for pan_id, entries in groups.items()])

    def _open_item(self, board: Board, row: dict[str, str]) -> ListItem:
        return ListItem(
            board=board.key,
            post_key=row["PAN_ID"],
            title=(row.get("PAN_NM") or "").strip(),
            posted_on=parse_day(row.get("PAN_NT_ST_DT")),
            detail_url=row.get("DTL_URL"),
            list_status=row.get("PAN_SS") or None,
            deadline_on=parse_day(row.get("CLSG_DT")),
            meta={**lh_meta(row), "_lhRow": steady_row(row)},
        )

    def _myhome_item(self, board: Board, pan_id: str, entries: list[dict[str, Any]]) -> ListItem:
        first = entries[0]["item"]
        return ListItem(
            board=board.key,
            post_key=pan_id,
            title=(first.get("pblancNm") or "").strip(),
            posted_on=parse_day(first.get("rcritPblancDe")),
            detail_url=first.get("url"),
            # 상태·마감일은 비워요. LH 목록에도 있는 공고의 LH 값을 마이홈 값으로 덮지 않게 (목록 갱신은 빈 값을 무시해요)
            list_status=None,
            deadline_on=None,
            meta={"_myhome": [{key: value for key, value in entry.items() if key != "fetchedAt"} for entry in entries]},
        )

    def _myhome_groups(self, myhome: MyHomeApi) -> dict[str, list[dict[str, Any]]]:
        """마이홈 임대·분양 목록 중 LH 줄을 LH 공고 ID별로. 한 회차 안에서는 한 번만 받아요
        (open 게시판의 상세를 처리하며 처음 받고, myhome 게시판은 그걸 그대로 써요)."""
        now = self._clock()
        if self._myhome_cache and now - self._myhome_cache[0] < config.MYHOME_CACHE_SECONDS:
            return self._myhome_cache[1]
        pages = [(kind, page.fetched_at, page.body) for kind in config.MYHOME_LISTS for page in myhome.list_pages(kind)]
        groups = group_myhome_rows(pages)
        self._myhome_cache = (now, groups)
        return groups

    # ── 분류 ──────────────────────────────────────────────────
    def pre_classify(self, item: ListItem) -> str | None:
        row = item.meta.get("_lhRow")
        return (classify(row) if row else classify_title(item.title)).pipeline_kind

    # ── 상세 ──────────────────────────────────────────────────
    def fetch_detail(self, client: Fetcher, item: ListItem) -> Detail:
        lh, myhome = self._apis(client)
        row, lookup = item.meta.get("_lhRow"), None
        if row is None:  # 마이홈에만 보이는 공고: 상세 API에 필요한 값을 얻으려고 LH 목록에서 찾아요
            first = item.meta["_myhome"][0]["item"]
            row, page = lh.find_row(item.post_key, first.get("rcritPblancDe"), first.get("pblancNm") or "", self._today())
            if row is None:
                raise ParseError("마이홈에만 있는 LH 공고를 LH 목록에서 찾지 못했어요 (다음 회차에 다시 찾아요)")
            lookup = page.to_dict()
        try:
            detail, supply = lh.detail(row), lh.supply(row)
        except ValueError as error:  # 상세 조회 값이 빠진 목록 줄
            raise ParseError(str(error)) from None
        try:
            entries = self._myhome_groups(myhome).get(item.post_key, [])
        except MyHomeApiError as error:  # 마이홈이 안 돼도 LH 원본은 받아요 (마이홈 줄은 다음 정정 확인 때 들어가요)
            log.warning("마이홈 목록을 읽지 못해 마이홈 줄 없이 저장해요", extra={"source": self.code, "post": item.post_key, "error": str(error)})
            entries = []
        selection = select_attachments(attachments(detail.body))
        files = [FileRef(a.name, a.url, a.index) for a in selection.notice_docs + selection.housing_lists]
        raw = {
            "lhRow": row,
            "lookup": lookup,
            "detail": detail.to_dict(),
            "supply": supply.to_dict(),
            "myhome": entries,
            "extraAttachments": [asdict(a) for a in selection.extras],
        }
        return Detail(
            title=(row.get("PAN_NM") or item.title).strip(),
            body_text=body_text(detail.body, supply.body, entries),
            files=files,
            meta={**lh_meta(row), "_raw": raw},
            posted_on=parse_day(row.get("PAN_NT_ST_DT")),
            region_code=region_code(entries),
        )
