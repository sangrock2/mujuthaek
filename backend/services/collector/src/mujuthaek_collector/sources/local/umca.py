"""울산도시공사 — 분양·임대 게시판.

목록  분양 https://www.umca.co.kr/umca/bbs/list.do?bbsId=BBS_0000000000000003&mId=001001003000000000&page=N
      임대 https://www.umca.co.kr/umca/bbs/list.do?bbsId=BBS_0000000000000004&mId=001001004000000000&page=N
      행: 제목 링크 view.do?…&dataId=N, 첨부 아이콘 img alt(파일명), 작성일
상세  https://www.umca.co.kr/umca/bbs/view.do?mId=…&bbsId=…&dataId=N
      table.tbl_bd_view: 항목 th[scope=row]+td(제목·작성일자·유형 …), 본문은 마지막 td[colspan=2]
첨부  화면은 HHBbs.DownFile('/umca', bbsId, atchFileId, fileSn) 스크립트로 받지만, 인자를 읽어 원본 주소를 직접 만들어요:
      https://www.umca.co.kr/umca/bbs/FileDown.do?bbsId=…&atchFileId=…&fileSn=K
"""

import re
import urllib.parse

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import body_text, js_args, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://www.umca.co.kr"
SIZE_SUFFIX = re.compile(r"\s*\(\s*[\d.,]+\s*[KMG]?Byte\)\s*$")


class UmcaSource(Source):
    code = "umca"
    name = "울산도시공사"
    provider = "UMCA"
    boards = [
        Board("sale", "분양", {"bbsId": "BBS_0000000000000003", "mId": "001001003000000000"}),
        Board("rent", "임대", {"bbsId": "BBS_0000000000000004", "mId": "001001004000000000"}),
    ]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{BASE}/umca/bbs/list.do?" + urllib.parse.urlencode({**board.params, "page": page}))

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        if doc.find("table") is None:
            raise ParseError("울산 목록 표를 찾지 못했어요")
        items = []
        for tr in doc.find_all("tr"):
            anchor = tr.find("a", href=re.compile(r"view\.do\?.*dataId=\d+"))
            if anchor is None:
                continue
            data_id = query_of(anchor["href"])["dataId"]
            found = re.search(r"\d{4}-\d{2}-\d{2}", text_of(tr))
            items.append(
                ListItem(
                    board=board.key,
                    post_key=f"{board.key}-{data_id}",
                    title=text_of(anchor),
                    posted_on=parse_date(found.group(0)) if found else None,
                    detail_url=f"{BASE}/umca/bbs/view.do?"
                    + urllib.parse.urlencode({"mId": board.params["mId"], "bbsId": board.params["bbsId"], "dataId": data_id}),
                    referer=page_url,
                    meta={"첨부": [img["alt"] for img in tr.select("img[alt]") if re.search(r"\.[A-Za-z0-9]{2,5}$", img["alt"])]},
                )
            )
        return items

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        table = doc.select_one('table[class*="tbl_bd_view"]')
        if table is None:
            raise ParseError(f"울산 상세 표(table.tbl_bd_view)를 찾지 못했어요: {item.post_key}")
        meta = {}
        for th in table.select('th[scope="row"]'):
            label = text_of(th)
            if label not in ("첨부파일", "조회수"):
                meta[label] = text_of(th.find_next_sibling("td"))
        files = []
        for node in table.find_all(["a", "button"]):
            script = (node.get("onclick") or "") + " " + (node.get("href") or "")
            args = js_args(script, "HHBbs.DownFile")
            if not args or len(args) < 4:
                continue
            context, bbs_id, file_id, sn = args[:4]
            name = SIZE_SUFFIX.sub("", text_of(node)).strip()
            url = f"{BASE}{context}/bbs/FileDown.do?" + urllib.parse.urlencode({"bbsId": bbs_id, "atchFileId": file_id, "fileSn": sn})
            files.append(FileRef(name, url, len(files)))
        bodies = table.select('td[colspan="2"]')
        return Detail(
            title=meta.get("제목") or item.title,
            body_text=body_text(bodies[-1]) if bodies else "",
            files=files,
            meta=meta,
            posted_on=parse_date(meta.get("작성일자")),
        )
