"""iH 인천도시공사 — 임대(입주자모집공고)와 분양 게시판.

목록  임대 https://www.ih.co.kr/main/bbs/bbsMsgList.do?bcd=notice&cate1=general&pgdiv=general&pgno=N&listsz=20
      분양 https://www.ih.co.kr/main/bbs/bbsMsgList.do?bcd=sale_lease&cate1=a&pgno=N&listsz=20
      ul.generalList > li: p.title 안의 제목 링크(bbsMsgDetail.do?msg_seq=N), 첨부 아이콘 alt(파일명), 작성일, 분류(li.center)
상세  https://www.ih.co.kr/main/bbs/bbsMsgDetail.do?msg_seq=N&bcd=…&cate1=…(&pgdiv=general)
      제목 div.title, 작성일·분류 ul.data_list(dt/dd), 본문 div.detail, 첨부 div.add_file
첨부  https://www.ih.co.kr/main/bbs/bbsMsgFileDown.do?bcd=…&msg_seq=N&fileno=K (세션 없이 바로 받아져요)
주의  글번호가 게시판마다 따로 매겨져서 글 키는 'notice-123', 'sale_lease-123'처럼 게시판 코드를 붙여요.
      robots.txt가 구글 검색 로봇만 /main/bbs/를 막아둬서(검색 노출을 원치 않음) 실행 횟수를 낮게 유지해요.
"""

import re
import urllib.parse

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://www.ih.co.kr"
PAGE_SIZE = 20
DATE = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}")


class IhSource(Source):
    code = "ih"
    name = "iH 인천도시공사"
    provider = "IH"
    boards = [
        Board("notice", "임대", {"bcd": "notice", "cate1": "general", "pgdiv": "general"}),
        Board("sale_lease", "분양", {"bcd": "sale_lease", "cate1": "a"}),
    ]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{BASE}/main/bbs/bbsMsgList.do?" + urllib.parse.urlencode({**board.params, "pgno": page, "listsz": PAGE_SIZE}))

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        if doc.select_one("ul.generalList") is None and not doc.select("a[href*=bbsMsgDetail]"):
            raise ParseError("iH 목록(ul.generalList)을 찾지 못했어요")
        items, seen = [], set()
        for anchor in doc.select("p.title a[href*=bbsMsgDetail], a[href*=bbsMsgDetail]"):
            msg_seq = query_of(anchor["href"]).get("msg_seq")
            if not msg_seq or msg_seq in seen:
                continue
            seen.add(msg_seq)
            li = anchor.find_parent("li") or anchor.parent
            dates = DATE.findall(text_of(li))  # 제목에도 날짜가 있을 수 있어서 행의 마지막 날짜(작성일)를 써요
            category = text_of(li.select_one("li.center")) if li else ""
            items.append(
                ListItem(
                    board=board.key,
                    post_key=f"{board.params['bcd']}-{msg_seq}",
                    title=text_of(anchor),
                    posted_on=parse_date(dates[-1]) if dates else None,
                    detail_url=f"{BASE}/main/bbs/bbsMsgDetail.do?" + urllib.parse.urlencode({"msg_seq": msg_seq, **board.params}),
                    referer=page_url,
                    meta={
                        "분류": "" if DATE.fullmatch(category or "") else category,
                        "작성자": text_of(li.select_one("li.writer")) if li else "",
                        "첨부": [re.sub(r"\s*다운받기$", "", img.get("alt", "")) for img in (li.select("img[alt]") if li else [])],
                    },
                )
            )
        return items

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        content = doc.select_one("div.detail")
        if content is None:
            raise ParseError(f"iH 상세 본문(div.detail)을 찾지 못했어요: {item.post_key}")
        data_list = doc.select_one("ul.data_list")
        meta = {}
        if data_list is not None:
            meta = {text_of(dt): text_of(dt.find_next_sibling("dd")) for dt in data_list.find_all("dt")}
        files = []
        for anchor in doc.select("div.add_file a[href*=bbsMsgFileDown]"):
            url = abs_url(BASE, anchor["href"])
            index = int(query_of(url).get("fileno") or len(files) + 1)
            files.append(FileRef(text_of(anchor), url, index))
        return Detail(title=text_of(doc.select_one("div.title")) or item.title, body_text=body_text(content), files=files, meta=meta)
