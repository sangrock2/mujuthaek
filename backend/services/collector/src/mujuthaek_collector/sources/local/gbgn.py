"""경상북도개발공사 · 경상남도개발공사 — 같은 게시판 시스템이라 설정만 다르게 한 클래스로 받아요.

게시판 화면  경북 https://www.gbdc.co.kr/boardlist.do?seqId=0000003638
             경남 https://www.gndc.co.kr/boardlist.do?seqId=0000006202
목록 (JSON)  경북 https://www.gbdc.co.kr/getBbsArticleList.do?BBS_ID=4c9b3e75-2935-4bcd-96be-62fb07903949&BBS_TYPE=L&CURRENT_PAGE=N
             경남 https://www.gndc.co.kr/getBbsArticleList.do?BBS_ID=B491A490314446318099F9D828047900&BBS_TYPE=L&CURRENT_PAGE=N
                  &ATTR01=COLM1_CD%26notice_06%7CCOLM3_CD&ATTR02=COLM3_CD
             화면은 자바스크립트로 그리지만 목록은 이 주소가 JSON(resultList)으로 줘요. 게시판 화면 주소를 Referer로 보내요.
             항목: IPDS_IDX(글번호), CPDS_SUBJECT(제목), CPDS_WDATE(작성일), COLM1_VAL(분류), COLM2_VAL(상태), COLM3_VAL(지역),
                   COLM4_VAL(유형), sysFileNameStr·orgFileNameStr(첨부 경로·이름, '|'로 구분)
상세         https://www.gbdc.co.kr/boardview/boardview.do?seqId=0000003638&BBS_ID=…&IPDS_IDX=N&BBS_TYPE=L (경남도 같은 모양)
             제목 p.title 또는 div.board-head h3, 항목 div.board-(view-)head의 dt/dd, 본문 div.board-view-body 또는 div.board-body
첨부         https://www.gbdc.co.kr/common/download.do?fileVirtualPath=경로&fileOrgName=이름
             (목록 JSON에 없으면 상세의 pdfViewr('이름','형식','경로','다운로드주소')와 a[href^=/common/download.do]에서)
주의         경북은 보상·분양(토지)·임대 공고가 한 게시판이라 분류가 '임대공고'인 글만 열어요. robots.txt 없음(404) → 표준상 허용.
"""

import json
import re
import urllib.parse

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

SITES = {
    "gbdc": {
        "name": "경상북도개발공사",
        "provider": "GBDC",
        "base": "https://www.gbdc.co.kr",
        "board": Board("rent", "임대", {"bbs_id": "4c9b3e75-2935-4bcd-96be-62fb07903949", "seq_id": "0000003638", "categories": "임대공고"}),
    },
    "gndc": {
        "name": "경상남도개발공사",
        "provider": "GNDC",
        "base": "https://www.gndc.co.kr",
        "board": Board(
            "rent",
            "임대",
            {"bbs_id": "B491A490314446318099F9D828047900", "seq_id": "0000006202", "ATTR01": "COLM1_CD&notice_06|COLM3_CD", "ATTR02": "COLM3_CD"},
        ),
    },
}
PDF_VIEWER = re.compile(r"pdfViewr\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'")


def val(value) -> str:
    return "" if value in (None, "N", "-") else str(value).strip()


class GbgnSource(Source):
    def __init__(self, site: str):
        config = SITES[site]
        self.code, self.name, self.provider = site, config["name"], config["provider"]
        self.base, self.boards = config["base"], [config["board"]]

    def board_url(self, board: Board) -> str:
        return f"{self.base}/boardlist.do?seqId={board.params['seq_id']}"

    def list_request(self, board: Board, page: int) -> Request:
        attrs = {k: v for k, v in board.params.items() if k.startswith("ATTR")}
        query = {"BBS_ID": board.params["bbs_id"], "BBS_TYPE": "L", "CURRENT_PAGE": page, **attrs}
        return Request(f"{self.base}/getBbsArticleList.do?" + urllib.parse.urlencode(query), referer=self.board_url(board))

    def download_url(self, path: str, name: str) -> str:
        return f"{self.base}/common/download.do?" + urllib.parse.urlencode({"fileVirtualPath": path, "fileOrgName": name})

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        try:
            rows = json.loads(body).get("resultList")
        except (ValueError, AttributeError) as error:
            raise ParseError(f"{self.name} 목록 응답이 JSON이 아니에요 (구조 변경 확인 필요)") from error
        if rows is None:
            raise ParseError(f"{self.name} 목록 JSON에 resultList가 없어요")
        items = []
        for row in rows:
            seq = str(row["IPDS_IDX"])
            paths = [p for p in (row.get("sysFileNameStr") or "").split("|") if p]
            names = [n for n in (row.get("orgFileNameStr") or "").split("|") if n]
            files = [FileRef(n, self.download_url(p, n), i) for i, (p, n) in enumerate(zip(paths, names))] if len(paths) == len(names) else []
            category = val(row.get("COLM1_VAL"))
            wanted = board.params.get("categories")
            items.append(
                ListItem(
                    board=board.key,
                    post_key=seq,
                    title=re.sub(r"\s+", " ", row.get("CPDS_SUBJECT") or "").strip(),
                    posted_on=parse_date((row.get("CPDS_WDATE") or "")[:10]),
                    detail_url=f"{self.base}/boardview/boardview.do?"
                    + urllib.parse.urlencode({"seqId": board.params["seq_id"], "BBS_ID": board.params["bbs_id"], "IPDS_IDX": seq, "BBS_TYPE": "L"}),
                    referer=self.board_url(board),
                    list_status=val(row.get("COLM2_VAL")) or None,
                    meta={
                        "분류": category,
                        "지역": val(row.get("COLM3_VAL")),
                        "유형": val(row.get("COLM4_VAL")),
                        "범위밖": bool(wanted) and category != wanted,
                    },
                    files=files,
                )
            )
        return items

    def pre_classify(self, item: ListItem) -> str | None:
        return cls.EXCLUDED if item.meta.get("범위밖") else None  # 경북: 임대공고가 아닌 보상·분양(토지) 글

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        content = doc.select_one('div[class^="board-view-body"]') or doc.select_one("div.board-body")
        if content is None:
            raise ParseError(f"{self.name} 상세 본문(div.board-view-body)을 찾지 못했어요: {item.post_key}")
        title = text_of(doc.select_one("p.title")) or text_of(doc.select_one("div.board-head h3")) or item.title
        head = doc.select_one("div.board-view-head") or doc.select_one("div.board-head")
        meta = {text_of(dt): text_of(dt.find_next_sibling("dd")) for dt in head.find_all("dt")} if head else {}
        files, seen = [], set()
        for name, _ext, path, down in PDF_VIEWER.findall(body):
            if path not in seen:
                seen.add(path)
                files.append(FileRef(name, abs_url(self.base, down), len(files)))
        for anchor in doc.select('a[href^="/common/download.do"]'):
            query = query_of(anchor["href"])
            if query.get("fileVirtualPath") and query["fileVirtualPath"] not in seen:
                seen.add(query["fileVirtualPath"])
                files.append(FileRef(query.get("fileOrgName", text_of(anchor)), abs_url(self.base, anchor["href"]), len(files)))
        return Detail(title=title, body_text=body_text(content), files=files or item.files, meta=meta, posted_on=parse_date(meta.get("작성일")))
