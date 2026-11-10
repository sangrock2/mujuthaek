"""대구도시공사 — 분양·임대가 한 게시판.

목록  https://www.dudc.or.kr/ko/page.do?appId=sale&mnu_uid=101&pageNo=N
      행: 제목 링크(board_idx=N), td.bgbar에 임대·분양·토지·상가 구분, td.date에 등록일
상세  https://www.dudc.or.kr/ko/page.do?appId=sale&mnu_uid=101&board_idx=N&cmd=2
      div.boardView 안의 h4(제목), dt/dd(항목), 본문 div#bbs_content
첨부  https://www.dudc.or.kr/dudc/boardDownload/N.do (공급가능주택 목록 엑셀은 주택목록으로 받아요)
주의  토지·상가 글은 주거가 아니라서 열지 않아요.
꺼 둠  robots.txt가 사이트 전체를 막아요(Disallow: /, 2026-10-19). 마이그레이션으로 sources.enabled = false
"""

import re
import urllib.parse

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://www.dudc.or.kr"
NOT_HOUSING = re.compile(r"토지|상가")


class DudcSource(Source):
    code = "dudc"
    name = "대구도시공사"
    provider = "DUDC"
    boards = [Board("sale", "분양·임대", {"appId": "sale", "mnu_uid": "101"})]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{BASE}/ko/page.do?" + urllib.parse.urlencode({**board.params, "pageNo": page}))

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        if doc.find("table") is None:
            raise ParseError("대구 목록 표를 찾지 못했어요")
        items = []
        for tr in doc.find_all("tr"):
            anchor = tr.find("a", href=re.compile(r"board_idx=\d+"))
            if anchor is None:
                continue
            idx = query_of(anchor["href"])["board_idx"]
            items.append(
                ListItem(
                    board=board.key,
                    post_key=idx,
                    title=text_of(anchor),
                    posted_on=parse_date(text_of(tr.select_one("td.date"))),
                    detail_url=f"{BASE}/ko/page.do?" + urllib.parse.urlencode({**board.params, "board_idx": idx, "cmd": "2"}),
                    referer=page_url,
                    meta={"구분": text_of(tr.select_one("td.bgbar"))},
                )
            )
        return items

    def pre_classify(self, item: ListItem) -> str | None:
        return cls.EXCLUDED if NOT_HOUSING.search(item.meta.get("구분") or "") else None

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        content = doc.select_one("div#bbs_content")
        if content is None:
            raise ParseError(f"대구 상세 본문(div#bbs_content)을 찾지 못했어요: {item.post_key}")
        view = doc.select_one("div.boardView") or doc
        meta = {text_of(dt): text_of(dt.find_next_sibling("dd")) for dt in view.find_all("dt")}
        files = [FileRef(text_of(a), abs_url(BASE, a["href"]), i) for i, a in enumerate(view.select('a[href^="/dudc/boardDownload/"]'))]
        return Detail(
            title=text_of(view.find("h4")) or item.title, body_text=body_text(content), files=files, meta=meta, posted_on=parse_date(meta.get("등록일"))
        )
