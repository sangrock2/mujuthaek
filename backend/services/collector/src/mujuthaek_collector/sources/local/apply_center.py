"""GH 경기주택도시공사 · 부산도시공사 — 같은 청약·임대센터 시스템이라 설정만 다르게 한 클래스로 받아요.

목록  GH   임대     https://apply.gh.or.kr/sb/sr/sr7150/selectPbancRentHouseList.do?pageIndex=N
           매입임대 https://apply.gh.or.kr/sb/sr/sr7155/selectPbancRentHouseList.do?pageIndex=N
      부산 임대     https://apply.bmc.busan.kr/smw/smw113010/selectPbancRentHouseList.do?pageIndex=N
           매입임대 https://apply.bmc.busan.kr/smw/smw113020/selectPbancRentHouseList.do?pageIndex=N
      행: [번호, 유형, 공고명(a.text_cut data-pbancNo·data-pbancKndCd·data-bizTyNm), 지역, 첨부, 게시일, 마감일, 상태, 경쟁률, 조회수]
      data-pbancKndCd 01 일반, 02 정정. 부산은 PC·모바일용 표가 같이 있어 같은 공고가 두 번 나와요(중복 제거)
상세  목록과 같은 폴더의 selectPbancDetailView.do?pbancNo=N
      표: 공고 정보(공고상태·유형·공고일 …) / 지구별 공급정보(지구명) / 주택형별 임대조건 / 접수처. 공고 하나에 지구가 여러 개일 수 있어요
첨부  상세의 a[href*=selectFileDown.do]. GH는 파일 서버 https://apply-cdn.gh.or.kr/sr/sr7150/selectFileDown.do?pbancNo&atchFileSn&atchFileDtlSn
주의  당첨자 메뉴(GH sr7351 등)와 임대상가 메뉴(sr7170)는 받지 않아요.
"""

import re

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core.files import FileRef
from mujuthaek_collector.core.html import abs_url, parse_date, soup, table_grid, text_of
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.base import Board, Detail, ListItem, Request, Source

SITES = {
    "gh": {
        "name": "GH 경기주택도시공사",
        "provider": "GH",
        "base": "https://apply.gh.or.kr",
        "boards": [
            Board("rent", "임대", {"path": "/sb/sr/sr7150/selectPbancRentHouseList.do"}),
            Board("buy", "매입임대", {"path": "/sb/sr/sr7155/selectPbancRentHouseList.do"}),
        ],
    },
    "bmc": {
        "name": "부산도시공사",
        "provider": "BMC",
        "base": "https://apply.bmc.busan.kr",
        "boards": [
            Board("rent", "임대", {"path": "/smw/smw113010/selectPbancRentHouseList.do"}),
            Board("buy", "매입임대", {"path": "/smw/smw113020/selectPbancRentHouseList.do"}),
        ],
    },
}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATUS = re.compile(r"접수|공고|마감|예정|진행")


class ApplyCenterSource(Source):
    def __init__(self, site: str):
        config = SITES[site]
        self.code, self.name, self.provider = site, config["name"], config["provider"]
        self.base, self.boards = config["base"], config["boards"]

    def list_request(self, board: Board, page: int) -> Request:
        return Request(f"{self.base}{board.params['path']}?pageIndex={page}")

    def detail_url(self, board: Board, pbanc_no: str) -> str:
        folder = board.params["path"].rsplit("/", 1)[0]
        return f"{self.base}{folder}/selectPbancDetailView.do?pbancNo={pbanc_no}"

    def parse_list(self, board: Board, body: str, page_url: str) -> list[ListItem]:
        doc = soup(body)
        if doc.find("tbody") is None:
            raise ParseError(f"{self.name} 목록 표(tbody)를 찾지 못했어요")
        items, seen = [], set()
        for tr in doc.select("tbody tr"):
            anchor = tr.select_one("a.text_cut")
            if anchor is None:
                continue
            data = {k.lower(): v for k, v in anchor.attrs.items() if k.lower().startswith("data-")}
            pbanc_no = data.get("data-pbancno")
            if not pbanc_no or pbanc_no in seen:
                continue
            seen.add(pbanc_no)
            cells = [text_of(td) for td in tr.find_all("td")]
            dates = [c for c in cells if DATE.fullmatch(c)]
            status = next((c for c in cells if STATUS.search(c) and len(c) <= 8), "")
            items.append(
                ListItem(
                    board=board.key,
                    post_key=f"{board.key}-{pbanc_no}",
                    title=text_of(anchor),
                    posted_on=parse_date(dates[0]) if dates else None,
                    detail_url=self.detail_url(board, pbanc_no),
                    referer=page_url,
                    list_status=status if status != "-" else None,
                    deadline_on=parse_date(dates[1]) if len(dates) > 1 else None,
                    meta={
                        "공고번호": pbanc_no,
                        "공고종류": "정정" if data.get("data-pbanckndcd") == "02" else "일반",
                        "유형": data.get("data-biztynm", ""),
                        "지역": cells[3] if len(cells) > 3 and cells[3] != "-" else "",
                    },
                )
            )
        return items

    def pre_classify(self, item: ListItem) -> str | None:
        """목록에 정정 표시(data-pbancKndCd=02)가 있으면 제목과 상관없이 정정공고."""
        if item.meta.get("공고종류") == "정정" and cls.classify(item.title) in (cls.NOTICE, cls.CORRECTION):
            return cls.CORRECTION
        return None

    def parse_detail(self, item: ListItem, body: str) -> Detail:
        doc = soup(body)
        info: dict[str, str] = {}
        districts: list[dict[str, str]] = []
        office: dict[str, str] = {}
        unit_tables: list[list[list[str]]] = []
        for table in doc.find_all("table"):
            caption = text_of(table.find("caption"))
            pairs = key_values(table)
            labels = {text_of(th) for th in table.find_all("th")}
            rows = table.find_all("tr")
            first = rows[0].find_all(["th", "td"], recursive=False) if rows else []
            grid_table = len(rows) > 1 and first and all(c.name == "th" for c in first)
            if "공고상태" in labels or "청약공고 상세" in caption:
                info.update(pairs)
            elif "지구명" in labels:
                if pairs not in districts:
                    districts.append(pairs)
            elif grid_table and ("주택형" in caption or "주택형" in labels):
                unit_tables.append(table_grid(table))  # 모바일용(항목: 값) 표는 첫 행이 머리글이 아니라서 빠짐
            elif "접수처" in caption:
                office.update(pairs)
        if not (info or districts or unit_tables):
            raise ParseError(f"{self.name} 상세의 공고 정보 표를 찾지 못했어요: {item.post_key}")

        rows: list[list[str]] = []  # 지구가 여러 개면 주택형 표를 지구와 순서대로 짝지어 '지구명' 칸을 붙여요
        for number, grid in enumerate(unit_tables):
            name = districts[number].get("지구명", "") if len(unit_tables) == len(districts) > 1 else ""
            if not rows:
                rows.append((["지구명"] if name else []) + grid[0])
            rows += [([name] if name else []) + row for row in grid[1:]]

        title = info.get("공고명") or text_of(doc.select_one("h3.tit")) or item.title
        lines = [f"{k}: {v}" for k, v in info.items()]
        for district in districts:
            lines.append("[지구] " + ", ".join(f"{k}: {v}" for k, v in district.items()))
        if rows:
            lines += ["[주택형별 임대조건]"] + [" | ".join(r) for r in rows]
        if office:
            lines.append("[접수처] " + ", ".join(f"{k}: {v}" for k, v in office.items()))
        meta = {**info, **{f"접수처 {k}": v for k, v in office.items()}}
        return Detail(title=title, body_text="\n".join(lines), files=self.parse_files(doc), meta=meta, posted_on=parse_date(info.get("공고일")))

    def parse_files(self, doc) -> list[FileRef]:
        files, seen = [], set()
        for anchor in doc.select("a[href*=selectFileDown]"):
            url = abs_url(self.base, anchor["href"])
            if url in seen:
                continue  # PC용·모바일용 화면에 같은 링크가 두 번
            seen.add(url)
            label = text_of(anchor)
            size = re.search(r"\((\d+)\s*Byte\)", label)
            name = re.sub(r"\s*\(\d+\s*Byte\)\s*$", "", label)
            files.append(FileRef(name, url, len(files), int(size.group(1)) if size else None))
        return files


def key_values(table) -> dict[str, str]:
    """[항목 th][값 td] 짝을 모아요. 한 행에 짝이 여러 개여도 돼요."""
    pairs: dict[str, str] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        for left, right in zip(cells, cells[1:]):
            if left.name == "th" and right.name == "td":
                pairs[text_of(left)] = text_of(right)
    return pairs
