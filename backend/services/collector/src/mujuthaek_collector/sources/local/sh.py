"""SH 서울주택도시공사 — 주택임대 게시판.

목록  GET  https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/list.do?multi_itm_seq=2&page=N
      행: [번호, 제목(getDetailView('글번호')), 담당부서, 등록일, 조회수]. 번호 칸이 숫자가 아니면 상단 고정 공지
상세  POST https://www.i-sh.co.kr/app/lay2/program/S48T1581C563/www/brd/m_247/view.do
      폼 값: page, seq, multi_itm_seq, multi_itm_seqsStr (목록과 같은 세션, 목록 주소를 Referer로). 본문은 td.cont
첨부  상세의 첨부 영역은 파일마다 [형식 아이콘][파일명 a onclick=existFile('n')][미리보기 a href=htmlConverter.do?...] 순서.
      미리보기 값으로 원본 주소를 만들어요:
      htmlConverter.do?brd_id=B&seq=S&data_tp=T&file_seq=N → https://www.i-sh.co.kr/app/com/file/innoFD.do?brdId=B&seq=S&fileTp=T&fileSeq=N
      (/upload 경로는 robots.txt 금지라, 그쪽으로 넘겨지면 PoliteClient가 FileRejected로 막아요)
주의  페이지에 NetFunnel 대기 스크립트가 있어요. 대기 화면만 오면 PoliteClient가 BlockedError로 회차를 멈춰요.
"""

import re
import urllib.parse

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://www.i-sh.co.kr"
BOARD_PATH = "/app/lay2/program/S48T1581C563/www/brd/m_247"
LIST_URL = f"{BASE}{BOARD_PATH}/list.do"
VIEW_URL = f"{BASE}{BOARD_PATH}/view.do"
DOWNLOAD_URL = f"{BASE}/app/com/file/innoFD.do"
SEQ = re.compile(r"getDetailView\(\s*['\"]?(\d+)|view\.do[^\"']*?[?&]seq=(\d+)")
BODY_SELECTORS = ["td.cont", "div.view_cont", "div.viewCont", "div.board_view", "div.bbs_view", "div.view_con", "div.cont_view"]


class ShSource(Source):
    code = "sh"
    name = "SH 서울주택도시공사"
    provider = "SH"
    boards = [Board("rent", "주택임대", {"multi_itm_seq": "2"})]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{LIST_URL}?" + urllib.parse.urlencode({**board.params, "page": page}))

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        tbody = doc.find("tbody")
        if tbody is None:
            raise ParseError("SH 목록 표(tbody)를 찾지 못했어요")
        items = []
        for tr in tbody.find_all("tr"):
            found = SEQ.search(str(tr))
            if not found:
                continue
            seq = found.group(1) or found.group(2)
            cells = [text_of(td) for td in tr.find_all("td")]
            anchor = tr.find("a")
            if anchor is not None:
                for badge in anchor.select("span[class*=icoNew], span[class*=new]"):
                    badge.decompose()  # 제목 옆 'NEW' 표시
            title = text_of(anchor) or (cells[1] if len(cells) > 1 else "")
            posted = next((parse_date(c) for c in cells if re.fullmatch(r"\d{4}[-.]\d{2}[-.]\d{2}", c)), None)
            items.append(
                ListItem(
                    board=board.key,
                    post_key=seq,
                    title=title,
                    posted_on=posted,
                    detail_url=f"{LIST_URL}?multi_itm_seq={board.params['multi_itm_seq']}",  # POST 전용이라 사람에게는 목록 주소로 안내
                    fetch_url=VIEW_URL,
                    form={"page": "1", "seq": seq, "multi_itm_seq": board.params["multi_itm_seq"], "multi_itm_seqsStr": ""},
                    referer=page_url,
                    meta={"담당부서": cells[2] if len(cells) > 2 else "", "상단고정": bool(cells) and not cells[0].isdigit()},
                )
            )
        return items

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        content = next((node for node in (doc.select_one(s) for s in BODY_SELECTORS) if node is not None), None)
        if content is None:
            raise ParseError(f"SH 상세 본문(td.cont)을 찾지 못했어요: {item.post_key}")
        return Detail(title=item.title, body_text=body_text(content), files=self.parse_files(doc))

    @staticmethod
    def parse_files(doc) -> list[FileRef]:
        """[파일명 existFile('n')] 다음에 오는 [미리보기 htmlConverter.do]의 값으로 원본 주소를 만들어요."""
        files: list[FileRef] = []
        pending_name: str | None = None
        for anchor in doc.find_all("a"):
            onclick, href = anchor.get("onclick") or "", anchor.get("href") or ""
            if re.search(r"existFile\(", onclick):
                pending_name = text_of(anchor)[:120]
                continue
            if "htmlConverter.do" in href and pending_name:
                query = query_of(abs_url(BASE, href))
                if all(k in query for k in ("brd_id", "seq", "file_seq")):
                    params = {"brdId": query["brd_id"], "seq": query["seq"], "fileTp": query.get("data_tp", "A"), "fileSeq": query["file_seq"]}
                    files.append(FileRef(pending_name, f"{DOWNLOAD_URL}?" + urllib.parse.urlencode(params), len(files)))
                pending_name = None
        return files
