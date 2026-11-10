"""대전도시공사 — 분양(mId=37)·임대(mId=43) 게시판.

목록  분양 https://www.dcco.kr/web/board/list.do?mId=37&page=N
      임대 https://www.dcco.kr/web/board/list.do?mId=43&page=N
      행: 제목 링크 view.do?mId=…&brdIdx=N, 제목 앞 span.part에 [모집공고]·[공고결과] 머리말, td.part에 모집중·모집종료
상세  https://www.dcco.kr/web/board/view.do?mId=43&brdIdx=N (분양은 mId=37). 제목 th.viewTlt, 항목 th[scope=row]+td, 본문 td.contents
첨부  https://www.dcco.kr/web/board/download.do?mId=43&brdIdx=N&fidx=K&itId=file (상세의 a[href^=download.do])
주의  매입임대 공고의 건물 목록 엑셀(주소·승강기·주차)은 주택목록으로 받아요. robots.txt 없음(400) → 표준상 허용.
"""

import re

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, query_of, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://www.dcco.kr"


class DccoSource(Source):
    code = "dcco"
    name = "대전도시공사"
    provider = "DCCO"
    boards = [Board("37", "분양", {"mId": "37"}), Board("43", "임대", {"mId": "43"})]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{BASE}/web/board/list.do?mId={board.params['mId']}&page={page}")

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        if doc.find("table") is None:
            raise ParseError("대전 목록 표를 찾지 못했어요")
        items = []
        for tr in doc.find_all("tr"):
            anchor = tr.find("a", href=re.compile(r"view\.do\?.*brdIdx=\d+"))
            if anchor is None:
                continue
            brd_idx = query_of(anchor["href"])["brdIdx"]
            part = anchor.select_one("span.part")
            tags = re.findall(r"\[([^\]]+)\]", text_of(part))
            if part is not None:
                part.decompose()
            found = re.search(r"\d{4}-\d{2}-\d{2}", text_of(tr))
            items.append(
                ListItem(
                    board=board.key,
                    post_key=f"{board.key}-{brd_idx}",
                    title=text_of(anchor),
                    posted_on=parse_date(found.group(0)) if found else None,
                    detail_url=f"{BASE}/web/board/view.do?mId={board.params['mId']}&brdIdx={brd_idx}",
                    referer=page_url,
                    list_status=text_of(tr.select_one("td.part")) or None,
                    meta={"머리말": tags, "게시판": board.name},
                )
            )
        return items

    def pre_classify(self, item: ListItem) -> str | None:
        """제목 머리말: [공고결과]는 후속 안내, [모집공고]는 모집공고(정정 표시가 있으면 정정).
        대전은 공사가 집을 사는 '매입공고'에도 [모집공고]를 붙여서, 제목이 제외 대상이면 머리말보다 먼저 제외해요."""
        if cls.out_of_scope(item.title):
            return cls.EXCLUDED
        tags = item.meta.get("머리말") or []
        if any("결과" in t for t in tags):
            return cls.FOLLOW_UP
        if "모집공고" in tags:
            return cls.CORRECTION if cls.CORRECTION_MARK.search(item.title) else cls.NOTICE
        return None

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        content = doc.select_one("td.contents")
        if content is None:
            raise ParseError(f"대전 상세 본문(td.contents)을 찾지 못했어요: {item.post_key}")
        head = doc.select_one("th.viewTlt")
        if head is not None:
            for part in head.select("span.part"):
                part.decompose()
        meta = {}
        for th in doc.select('th[scope="row"]'):
            label = text_of(th)
            if "첨부" not in label:
                meta[label] = text_of(th.find_next_sibling("td"))
        files = [FileRef(text_of(a), abs_url(f"{BASE}/web/board/", a["href"]), i) for i, a in enumerate(doc.select('a[href^="download.do"]'))]
        return Detail(title=text_of(head) or item.title, body_text=body_text(content), files=files, meta=meta, posted_on=parse_date(meta.get("등록일")))
