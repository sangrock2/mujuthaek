"""상세정보 API 첨부 목록(dsAhflInfo)에서 받을 파일(공고문, 주택목록 엑셀)을 골라요.

여기서 고른 파일만 파이프라인에 넘겨요(Detail.files). 파이프라인은 그중에서 공통 규칙으로 공고문 하나와
주택목록을 다시 골라 받아요. LH는 첨부 종류 칸(공고문·정정공고문)이 있어서 파일명만 보는 것보다 정확하게 골라요.

POC(2026-10-14, 주택 공고 106건)에서 실제로 나온 경우를 규칙으로 만들었어요.
- 같은 공고문이 PDF·HWP로 함께 올라오고, 파일명이 조금씩 달라요 ('…(26년)1page.pdf' / '…(26년).hwp')
- 종류가 '공고문'인데 실제로는 엑셀 배치표이거나 '붙임1_공급가격표'인 파일이 있어요
- 이름에 '공고'가 없는 진짜 공고문도 있어요 ('군산시국민임대입주자상시모집.pdf')
- 단지별 공고문이 따로 올라오는 공고가 있어요 (대구연호 A-2BL·A-3BL)
- 매입임대 공고는 주택별 주소·면적·보증금·월임대료가 공고문이 아니라 '기타 첨부파일'의 주택목록 엑셀에만 있어요
  (공고문에는 "첨부 '주택내역' 참조"라고만 있음. 2026-10-14 매입임대 21건 중 18건에 있음)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

DOC_EXTS = (".pdf", ".hwp", ".hwpx")
# 종류는 '공고문'으로 올라오지만 본문이 아닌 붙임 파일
ATTACHMENT_NAME = re.compile(r"^\s*(붙임|별첨)|배치표|가격표|공급대상\s*및\s*공급가격|주택\s*목록")
# 개인정보·서식 파일: 받지 않아요. '예비자 모집공고문'은 공고문이라 명단 형태일 때만 걸러요
SKIP_FILE = re.compile(
    r"명부|명단|(당첨자|예비자|대상자|선정자)\s*(발표|현황|순번)"
    r"|신청서|양식|동의서|위임장|서약서|각서|도면|팸플릿|카탈로그|확인서|제출서류"
)
SAME_DOC_RATIO = 0.8  # PDF와 HWP 파일명이 이만큼 비슷하면 같은 공고문으로 봐요
SPREADSHEET_EXTS = (".xlsx", ".xls", ".xlsm")
# 주택목록 엑셀 이름. 분양 공고의 '동호배치표'·'해약세대목록'·'동호판' 엑셀은 해당하지 않아요
HOUSING_LIST_NAME = re.compile(r"주택\s*목록|공급\s*대상\s*주택|주택\s*내역")


@dataclass(frozen=True)
class Attachment:
    kind: str  # 첨부 종류 (SL_PAN_AHFL_DS_CD_NM, 예: 공고문(PDF), 정정공고문(PDF))
    name: str  # 파일명 (CMN_AHFL_NM)
    url: str  # 다운로드 주소 (AHFL_URL)
    index: int = 0  # 첨부 목록에서의 순서 (raw_files.idx, S3 위치에 써요)

    @classmethod
    def from_api(cls, item: dict[str, str], index: int = 0) -> Attachment:
        return cls(item.get("SL_PAN_AHFL_DS_CD_NM", ""), item.get("CMN_AHFL_NM", ""), item.get("AHFL_URL", ""), index)


@dataclass(frozen=True)
class Selection:
    notice_docs: list[Attachment]  # 받을 공고문
    housing_lists: list[Attachment]  # 받을 주택목록 엑셀
    extras: list[Attachment]  # 종류는 공고문이지만 본문이 아닌 첨부: 받지 않고 주소만 남겨요


def _stem(name: str) -> str:
    """파일명 비교용: 확장자·기호·'1page' 같은 꼬리를 빼고 글자만 남긴다."""
    lower = name.lower()
    stem = name.rsplit(".", 1)[0] if lower.endswith(DOC_EXTS) else name
    return re.sub(r"[^0-9A-Za-z가-힣]", "", stem.replace("1page", "")).lower()


def _is_pdf(a: Attachment) -> bool:
    return a.name.lower().endswith(".pdf")


def is_housing_list(a: Attachment) -> bool:
    """주택목록 엑셀인지. 첨부 종류는 보지 않는다 (대부분 '기타 첨부파일'로 올라옴)."""
    return a.name.lower().endswith(SPREADSHEET_EXTS) and bool(HOUSING_LIST_NAME.search(a.name)) and not SKIP_FILE.search(a.name)


def select_attachments(items: list[dict[str, str]]) -> Selection:
    """주택목록 엑셀: 종류와 상관없이 이름이 주택목록인 엑셀 모두.
    공고문: 1) 종류가 '공고문'인 것만 2) 개인정보·서식 제외 3) 정정공고문이 있으면 그것만
    4) 문서 형식(PDF·HWP·HWPX)만, 붙임·배치표·가격표는 부속 첨부로 5) PDF 우선, HWP는 비슷한 PDF가 없을 때만."""
    attached = [a for a in (Attachment.from_api(item, i) for i, item in enumerate(items)) if a.url]
    housing_lists = [a for a in attached if is_housing_list(a)]
    files = [a for a in attached if "공고문" in a.kind and not SKIP_FILE.search(a.name) and a not in housing_lists]
    corrected = [a for a in files if "정정" in a.kind]
    files = corrected or files
    docs = [a for a in files if a.name.lower().endswith(DOC_EXTS)]
    # 다 걸러지면 거르지 않는다: 붙임 이름이어도 공고문 자리에 그것 하나뿐이면 받는다
    main = [a for a in docs if not ATTACHMENT_NAME.search(a.name)] or docs
    extras = [a for a in files if a not in main]
    pdfs = [a for a in main if _is_pdf(a)]
    hwps = [a for a in main if not _is_pdf(a) and not any(SequenceMatcher(None, _stem(a.name), _stem(p.name)).ratio() >= SAME_DOC_RATIO for p in pdfs)]
    return Selection(pdfs + hwps, housing_lists, extras)
