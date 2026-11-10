"""첨부 고르기. 공고문은 하나만, 주택목록은 엑셀 우선으로 최대 2개, 명단·신청서·도면은 받지 않아요."""

import re
from dataclasses import dataclass

# 사람 이름이 담긴 파일: 받지도 열지도 않음. '예비자(입주자) 모집공고문'은 공고문이라 빼요 (LH 실제 공고문 4건이 걸렸어요)
PERSONAL_FILE = re.compile(r"명부|명단|당첨자|예비자(?!\s*(?:입주자\s*)?모집)|계약\s*대상자|합격자|추첨\s*결과")
NOTICE_FILE_NAME = re.compile(r"공고문|모집\s*공고|입주자\s*모집|모집\s*안내|공급\s*공고")
STRONG_NOTICE_NAME = re.compile(r"공고문|모집\s*공고")  # '입주자모집 관련'처럼 약하게 맞는 이름보다 먼저 골라요
NOT_NOTICE_FILE = re.compile(r"안내문|커트라인|결과|위치도|평면도|배치도|도면|세대\s*내\s*구조|구조도|요약|FAQ|질의\s*응답|Q\s*&\s*A|자주\s*묻는", re.I)
FORM_FILE = re.compile(r"양식|서약서|위임장|동의서|신청서")  # 서식 파일. 단 '모집 공고문 및 신청서류'처럼 공고문이 같이 든 파일은 공고문
UNIT_LIST_FILE = re.compile(
    r"주택\s*목록|공급\s*(?:주택\s*)?목록|임대\s*조건|호별|대상\s*주택|주택\s*현황|단지\s*목록|모집\s*호수|공급\s*현황|주택\s*리스트"
    r"|공급\s*가능\s*주택|건물\s*목록"
)
FILE_EXT = re.compile(r"\.(hwpx?|pdf|zip|docx?|xlsx?|xlsm|jpe?g|png)\s*$", re.I)
DOC_EXTS = ("pdf", "hwp", "hwpx")
EXCEL_EXTS = ("xlsx", "xlsm", "xls")
UNIT_LIST_EXTS = (*EXCEL_EXTS, "pdf", "hwpx", "hwp")  # 주택목록으로 받을 형식


@dataclass
class FileRef:
    name: str
    url: str
    index: int
    size: int | None = None

    @property
    def ext(self) -> str:
        found = FILE_EXT.search(self.name)
        return found.group(1).lower() if found else ""

    @property
    def personal(self) -> bool:
        return bool(PERSONAL_FILE.search(self.name))

    @property
    def unit_list(self) -> bool:
        return bool(UNIT_LIST_FILE.search(self.name)) and not self.personal

    @property
    def notice_doc(self) -> bool:
        if self.personal or self.unit_list or NOT_NOTICE_FILE.search(self.name):
            return False
        return not FORM_FILE.search(self.name) or bool(STRONG_NOTICE_NAME.search(self.name))


def pick_notice_files(files: list[FileRef], prefer: str = "pdf") -> list[FileRef]:
    """공고문 후보를 순서대로 최대 2개: 이름(공고문·모집공고 → 입주자모집 등 → 그 밖) → 형식(PDF → HWPX → HWP) → 첨부 순서.
    첫 번째가 받기·읽기에 실패하면 두 번째를 시도해요."""
    usable = notice_candidates(files)
    order = {"pdf": 0, "hwpx": 1, "hwp": 2} if prefer == "pdf" else {"hwp": 0, "hwpx": 1, "pdf": 2}
    usable.sort(key=lambda f: (name_rank(f.name), order[f.ext], f.index))
    return usable[:2]


def name_rank(name: str) -> int:
    """0 '공고문·모집공고', 1 '입주자모집·모집안내·공급공고', 2 이름으로 알 수 없음."""
    return 0 if STRONG_NOTICE_NAME.search(name) else 1 if NOTICE_FILE_NAME.search(name) else 2


def unclear_notice(files: list[FileRef]) -> bool:
    """이름으로 공고문을 알 수 없는데 후보 문서가 여러 개예요 (첨부 순서로 고르니 잘못 골랐을 수 있음).
    같은 문서를 PDF·HWP로 함께 올린 건 하나로 쳐요."""
    usable = notice_candidates(files)
    if any(NOTICE_FILE_NAME.search(f.name) for f in usable):
        return False
    return len({_stem(f.name) for f in usable}) > 1


def notice_candidates(files: list[FileRef]) -> list[FileRef]:
    return [f for f in files if f.notice_doc and f.ext in DOC_EXTS]


def pick_unit_lists(files: list[FileRef]) -> list[FileRef]:
    """주택목록 최대 2개: '상세'가 든 목록 먼저, 같은 목록이 엑셀·PDF로 있으면 엑셀 하나만."""
    lists = [f for f in files if f.unit_list and f.ext in UNIT_LIST_EXTS]
    lists.sort(key=lambda f: ("상세" not in f.name, f.ext not in EXCEL_EXTS, f.name))
    picked, stems = [], set()
    for file in lists:
        stem = _stem(file.name)
        if stem not in stems:
            stems.add(stem)
            picked.append(file)
    return picked[:2]


def _stem(name: str) -> str:
    """앞 번호와 확장자를 뺀 이름: '1. 공급주택목록.xlsx' → '공급주택목록'."""
    return re.sub(r"^\s*[\d\-.]+\s*|\.[A-Za-z0-9]+$", "", name).strip()
