"""서울시 청년안심주택(soco.seoul.go.kr) — 모집공고 게시판(BMSR00015).

목록  POST https://soco.seoul.go.kr/youth/pgm/home/yohome/bbsListJson.json
      폼: bbsId=BMSR00015, pageIndex=N (나머지 검색 칸은 빈 값). 응답 JSON의 resultList에 글 10개, 최신 글이 먼저.
      글마다 boardId(글 키), nttSj(제목), optn1(공고게시일), optn4(청약신청 시작일), optn2(1 공공·2 민간),
      optn5(1 최초·2 추가), optn3(담당부서·사업자), gubunCd(자치구 번호, 가나다순 01 강남~25 중랑),
      content(본문 HTML), atchFileId(첨부 묶음), modDate(수정 시각, ms)
상세  https://soco.seoul.go.kr/youth/bbs/BMSR00015/view.do?optn1=공고일&boardId=N&menuNo=400008
      첨부 목록만 읽어요. 본문은 목록 JSON의 content를 써요(상세 화면과 같은 내용).
첨부  https://soco.seoul.go.kr/coHouse/cmmn/file/fileDown.do?atchFileId=…&fileSn=K
      상세의 a[href*=fileDown.do] 중 href가 진짜 주소인 것만. 바로보기·바로듣기 버튼(onclick)은 같은 파일이라 빼요.
주의  공식 공개 API가 아니라 화면이 쓰는 내부 요청이에요. 칸이 바뀌면 ParseError로 바로 알 수 있게 필수 칸을 검사해요.
      조회수(inqireCo)는 볼 때마다 늘어서 meta에 넣지 않아요(버전 비교에 섞이면 매번 바뀐 글로 잡혀요).
      첨부의 Content-Disposition 파일 이름은 인코딩 표시 없는 UTF-8이라, 이름은 상세 화면의 링크 글자를 써요.
      robots.txt 없음(403 오류 화면) → 표준상 허용.
"""

import json
import re
from datetime import UTC, date, datetime

from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, body_text, parse_date, soup, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

BASE = "https://soco.seoul.go.kr"
BBS_ID = "BMSR00015"
MENU_NO = "400008"
LIST_URL = f"{BASE}/youth/pgm/home/yohome/bbsListJson.json"
LIST_PAGE = f"{BASE}/youth/bbs/{BBS_ID}/list.do?menuNo={MENU_NO}"
REQUIRED_KEYS = ("boardId", "nttSj")

SUPPLY_KIND = {"1": "공공", "2": "민간"}
ROUND_KIND = {"1": "최초", "2": "추가"}
# gubunCd → (자치구, 시군구 코드). 사이트 검색창의 구 목록 순서예요 (2026-10-20 실제 공고 위치로 확인)
GU = {
    "01": ("강남구", "11680"), "02": ("강동구", "11740"), "03": ("강북구", "11305"), "04": ("강서구", "11500"),
    "05": ("관악구", "11620"), "06": ("광진구", "11215"), "07": ("구로구", "11530"), "08": ("금천구", "11545"),
    "09": ("노원구", "11350"), "10": ("도봉구", "11320"), "11": ("동대문구", "11230"), "12": ("동작구", "11590"),
    "13": ("마포구", "11440"), "14": ("서대문구", "11410"), "15": ("서초구", "11650"), "16": ("성동구", "11200"),
    "17": ("성북구", "11290"), "18": ("송파구", "11710"), "19": ("양천구", "11470"), "20": ("영등포구", "11560"),
    "21": ("용산구", "11170"), "22": ("은평구", "11380"), "23": ("종로구", "11110"), "24": ("중구", "11140"),
    "25": ("중랑구", "11260"),
}  # fmt: skip
REGION_KEY = "_시군구코드"
CONTENT_KEY = "_본문HTML"  # 목록 JSON의 본문. parse_detail에서 꺼내 쓰고 Detail.meta에는 넣지 않아요

# 본문의 "■단지명 : 길동생활(B동)" 같은 줄
FIELD_LINE = re.compile(r"■\s*(단지명|주택위치|공급호수|사업주체|시공사)\s*:\s*(.+)")
# "■청약신청 : ‘26. 10. 19. (월) 09:00 ~ 10. 20. (화) 18:00" — 끝 날짜는 연도가 빠지기도 해요.
# 콜론이 있어야 해요: 본문에 "통합하여 청약 신청을 받습니다" 같은 문장도 있어서요
APPLY_LINE = re.compile(r"청약\s*신청(?:\s*기간)?\s*:\s*(?P<body>[^\n]+)")
DATE_PART = re.compile(r"(?:(?P<y>\d{2,4})\s*\.\s*)?(?P<m>\d{1,2})\s*\.\s*(?P<d>\d{1,2})\s*\.?")


def _apply_period(text: str) -> tuple[date | None, date | None]:
    """본문에서 청약신청 기간(시작, 끝). 끝에 연도가 없으면 시작의 연도를 써요(12월→1월이면 다음 해)."""
    parts: list[re.Match] = []
    for found in APPLY_LINE.finditer(text or ""):
        line = found.group("body").replace("‘", "").replace("’", "").replace("'", "")
        parts = []
        for m in DATE_PART.finditer(line):
            if m.group("y") is None and not parts:
                continue  # 시작 날짜는 연도가 있어야 해요 (시각 09:00 같은 숫자를 날짜로 잘못 읽지 않게)
            parts.append(m)
            if len(parts) == 2:
                break
        if parts:
            break
    if not parts:
        return None, None

    def to_date(m: re.Match, year: int | None) -> date | None:
        y = int(m.group("y")) if m.group("y") else year
        if y is None:
            return None
        y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m.group("m")), int(m.group("d")))
        except ValueError:
            return None

    start = to_date(parts[0], None)
    end = to_date(parts[1], start.year if start else None) if len(parts) > 1 else start
    if start and end and end < start:
        end = date(end.year + 1, end.month, end.day)
    return start, end


def _fields(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in FIELD_LINE.finditer(text or "")}


def _ms_to_iso(ms: object) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


class SocoSource(Source):
    code = "soco"
    name = "서울시 청년안심주택"
    provider = "SEOUL"
    boards = [Board(BBS_ID, "모집공고", {"bbsId": BBS_ID})]

    def list_request(self, board: Board, page: int) -> Request:
        form = {
            "bbsId": board.params["bbsId"],
            "pageIndex": str(page),
            "searchAdresGu": "",
            "searchCondition": "",
            "searchKeyword": "",
            "optn2": "",
            "optn5": "",
        }
        return Request(LIST_URL, data=form, referer=LIST_PAGE)

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        try:
            doc = json.loads(body)
        except json.JSONDecodeError as error:
            raise ParseError(f"청년안심주택 목록이 JSON이 아니에요: {error}") from error
        rows = doc.get("resultList") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise ParseError("청년안심주택 목록 JSON에 resultList가 없어요")
        items = []
        for row in rows:
            missing = [k for k in REQUIRED_KEYS if not row.get(k)]
            if missing:
                raise ParseError(f"청년안심주택 목록 글에 필수 칸이 없어요: {missing}")
            board_id = str(row["boardId"])
            posted = row.get("optn1") or ""
            content = row.get("content") or ""
            plain = body_text(soup(content)) if content else ""
            _, apply_end = _apply_period(plain)
            gu, region = GU.get(str(row.get("gubunCd") or ""), (None, None))
            items.append(
                ListItem(
                    board=board.key,
                    post_key=board_id,
                    title=text_of(soup(row["nttSj"])),
                    posted_on=parse_date(posted),
                    detail_url=f"{BASE}/youth/bbs/{BBS_ID}/view.do?optn1={posted}&boardId={board_id}&menuNo={MENU_NO}",
                    referer=LIST_PAGE,
                    deadline_on=apply_end,
                    meta={
                        "자치구": gu,
                        "구분": SUPPLY_KIND.get(str(row.get("optn2") or "")),
                        "모집": ROUND_KIND.get(str(row.get("optn5") or "")),
                        "청약신청일": row.get("optn4") or None,
                        "담당": row.get("optn3") or None,
                        "첨부묶음": row.get("atchFileId") or None,
                        "수정시각": _ms_to_iso(row.get("modDate")),
                        REGION_KEY: region,
                        CONTENT_KEY: content,
                    },
                )
            )
        return items

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        files: list[FileRef] = []
        seen: set[str] = set()
        for anchor in doc.select('a[href*="fileDown.do"]'):
            url = abs_url(BASE, anchor["href"])
            if url in seen:
                continue
            seen.add(url)
            files.append(FileRef(text_of(anchor), url, len(files)))

        content = item.meta.get(CONTENT_KEY) or ""
        text = body_text(soup(content)) if content else ""
        if not text:
            # 목록 JSON에 본문이 없으면 상세 화면의 본문 영역이라도 써요
            area = doc.select_one(".board-view, .view-cont, .view_cont, .bbs-view, td.contents")
            text = body_text(area)
        if not text and not files:
            raise ParseError(f"청년안심주택 상세에서 본문도 첨부도 찾지 못했어요: {item.post_key}")

        meta = {k: v for k, v in item.meta.items() if k not in (CONTENT_KEY, REGION_KEY) and v is not None}
        meta.update(_fields(text))
        start, end = _apply_period(text)
        if start:
            meta["청약신청 시작"] = start.isoformat()
        if end:
            meta["청약신청 마감"] = end.isoformat()
        return Detail(title=item.title, body_text=text, files=files, meta=meta, posted_on=item.posted_on, region_code=item.meta.get(REGION_KEY))
