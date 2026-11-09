"""정답표 없이 원문과 결과만으로 하는 검사 (2026-10-16 추가). 공고 모양과 상관없이 그 공고의 원문만 있으면 돕니다.

V6 표 위치 대조: 값이 원문에 "있는지"(V2·V3)가 아니라 "제자리에 붙었는지"를 봅니다. 값을 인용한 표 행의 행 제목과
    그 값이 든 열의 머리글이 말하는 순위·대상군·주택형이, 추출 결과가 붙인 순위·대상군·주택형과 겹치지 않으면 의심합니다.
    예: 「| 로얄 | 302 | 1,000,000 | 192,300 | 2,000,000 |」의 2,000,000은 머리글이 "2, 3순위"인데 1순위 보증금으로 붙인 경우.
    양쪽에 표시가 모두 있을 때만 비교합니다(표시가 없으면 판단하지 않음). 같은 값이 한 행에 여러 칸이면 어느 칸인지 몰라 건너뜁니다.
V7 앞뒤 일관성: 일정 순서(공고 ≤ 접수 시작 ≤ 당첨 발표 ≤ 계약 ≤ 입주, 시작 ≤ 끝), 값의 정상 범위(금액·면적·나이·소득 비율),
    월임대료가 보증금보다 큰 가격안, 주택형별 모집 수 합과 공고 전체 모집 수, 낱말 정의로 만든 자격 조건의 대상(2026-11-06).
V8 누락 탐지: AI가 "다 뽑았다(EXTRACTED)"고 한 섹션이 비었는데 원문에 그 절 제목이 있는 경우, 배점표가 있는데 가점 행이 없는 경우,
    첨부 엑셀 주택 목록의 행 수보다 위치·공급 묶음이 크게 적은 경우, 원문 서류 표의 행을 어느 서류도 인용하지 않은 경우(2026-10-23),
    원문 자격 기준표 행의 기준값을 어느 자격 조건·예외도 쓰지 않은 경우(2026-11-07).
모두 사람 확인 후보(의심)이며, 판정에 쓰는 섹션(공고·자격)이 아니면 화면 표시 메모로 갑니다(verifier.NOTE_CODES).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_extraction.assemble.quotes import normalize
from mujuthaek_extraction.assemble.values import to_krw
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.pdf_reader import image_pages
from mujuthaek_extraction.verify.exceptions import AMOUNT
from mujuthaek_extraction.verify.model import Finding, SourceBundle

IMAGE_BLOCK_HEAD = "=== 그림 판독 "  # image_reading.BLOCK_HEAD와 같음 (검증 모듈이 추출 모듈을 가져오지 않도록 따로 둡니다)

# ---- 공통: 근거 인용문이 있는 원문 줄과 그 표 ----

RANK_SPAN = re.compile(r"(\d)\s*[~∼-]\s*(\d)\s*순위")
RANK_LIST = re.compile(r"(\d(?:\s*[·․ㆍ・‧,]\s*\d)+)\s*순위")
RANK_ONE = re.compile(r"(?<![\d~∼·․ㆍ・‧,-])\s*(\d)\s*순위")
# 표에 자주 나오는 대상군 표시 → 같은 대상으로 보는 이름. 추출 결과의 targetGroups 글자에서도 같은 낱말로 찾습니다.
GROUP_WORDS = {
    "청년": "청년",
    "대학생": "대학생",
    "신혼": "신혼부부",
    "신생아": "신생아",
    "고령자": "고령자",
    "장애인": "장애인",
    "수급자": "수급자",
    "한부모": "한부모",
    "다자녀": "다자녀",
}
TYPE_TOKEN = re.compile(r"(?<![\d.])(\d{2,3}[A-Z]{1,2}\d?|\d{1,3}형)(?![\d.])")
DIGITS = re.compile(r"\D")
NUMERIC_CELL = re.compile(r"\(?\d[\d,.\s]*\)?\s*(?:원|천원|만원|%|㎡|m2|세대|호|명|개월|년|점)?")


def _ranks(text: str) -> set[int]:
    out: set[int] = set()
    for a, b in RANK_SPAN.findall(text):
        out |= set(range(int(a), int(b) + 1))
    text = RANK_SPAN.sub(" ", text)
    for group in RANK_LIST.findall(text):
        out |= {int(d) for d in re.findall(r"\d", group)}
    text = RANK_LIST.sub(" ", text)
    out |= {int(d) for d in RANK_ONE.findall(text)}
    return out


def _groups(text: str) -> set[str]:
    return {name for word, name in GROUP_WORDS.items() if word in text}


# 한 칸이 같은 번호의 주택형 여럿을 함께 적은 표기(「19A/B/C」)는 각 주택형으로도 봅니다(supply_tables.SHARED_TYPES와 같은 규칙.
# 2026-11-07 23건 대조 umca-4439: 그 행 가격을 19B·19C 묶음에 붙였는데 행의 주택형을 19A로만 읽어 위치 의심으로 보류)
SHARED_TYPE_TOKEN = re.compile(r"(?<![\d.])(\d{2,3})([A-Z]{1,2}\d?)((?:\s*[/·ㆍ,]\s*[A-Z]{1,2}\d?)+)(?![\d.A-Z])")


def _types(text: str) -> set[str]:
    shared = {
        f"{match[1]}{suffix}" for match in SHARED_TYPE_TOKEN.finditer(text) for suffix in [match[2], *re.split(r"\s*[/·ㆍ,]\s*", match[3].strip(" /·ㆍ,"))]
    }
    return {t.removesuffix("형") for t in TYPE_TOKEN.findall(text)} | shared


# 구조 방식(intake/pdf_reader.render(labeled=True))이 표에 덧붙이는 줄. 표 행(|)이 아니지만 같은 표에 속합니다
TITLE_LINE = "  [열 제목] "
AID_LINE = "  ↳ "
TITLE_NUMBER = re.compile(r"^\d+\.\s*")


def _row_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _in_table(line: str) -> bool:
    return _row_line(line) or line.startswith((TITLE_LINE, AID_LINE))


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


class _Located:
    """근거 ID → (표 행이면) 그 행의 칸과 머리글 행들."""

    def __init__(self, candidate: dict[str, Any], sources: SourceBundle) -> None:
        self.evidence = {e["id"]: e for e in candidate["evidence"]}
        self.sources = sources
        self.lines: dict[str, list[str]] = {}
        self.starts: dict[str, list[int]] = {}

    def _line_index(self, doc: str, position: int) -> int:
        starts = self.starts[doc]
        low, high = 0, len(starts) - 1
        while low < high:  # position을 포함하는 줄 (이진 탐색)
            middle = (low + high + 1) // 2
            if starts[middle] <= position:
                low = middle
            else:
                high = middle - 1
        return low

    def line_of(self, evidence_id: str) -> tuple[str, int] | None:
        """근거가 있는 (문서, 줄 번호). 위치가 인용과 어긋나면 인용을 원문에서 다시 찾습니다."""
        item = self.evidence.get(evidence_id)
        if not item or item["locator"]["kind"] != "TEXT_RANGE" or item["sourceId"] not in self.sources.texts:
            return None
        doc = item["sourceId"]
        text = self.sources.texts[doc]
        if doc not in self.lines:
            self.lines[doc] = text.split("\n")
            offsets, total = [], 0
            for line in self.lines[doc]:
                offsets.append(total)
                total += len(line) + 1
            self.starts[doc] = offsets
        start = item["locator"]["start"]
        if normalize(item["quote"]) not in normalize(text[start : item["locator"]["end"]]):
            found = text.find(item["quote"])
            if found < 0:
                return None
            start = found
        return doc, self._line_index(doc, start)

    def row(self, evidence_id: str) -> tuple[list[str], list[list[str]]] | None:
        """근거가 표 행이면 (그 행의 칸, 머리글 행들)을, 표 행이 아니거나 찾지 못하면 None을 돌려줍니다."""
        located = self.line_of(evidence_id)
        if located is None:
            return None
        doc, index = located
        lines = self.lines[doc]
        if not _row_line(lines[index]):
            return None
        top = index
        while top > 0 and _in_table(lines[top - 1]):
            top -= 1
        # 구조 방식(2026-10-17)이면 프로그램이 병합 칸을 풀어 만든 열 제목 줄을 그대로 머리글로 씁니다
        titles = next((line for line in lines[top:index] if line.startswith(TITLE_LINE)), None)
        if titles:
            named = [TITLE_NUMBER.sub("", cell) for cell in _cells(titles[len(TITLE_LINE) :])]
            return _cells(lines[index]), [["" if name == "-" else name for name in named]]
        # 머리글 행 = 표 위쪽에서 숫자만 든 칸이 없는 행들. 머리글 없는 표(| 1순위 | 70% | / | 맞벌이 | 100% |)의 첫 데이터 행을
        # 머리글로 읽어 "1순위" 열로 보던 오탐을 막습니다(검토 2026-10-16)
        headers = []
        for line in [line for line in lines[top:index] if _row_line(line)][:3]:
            cells = _cells(line)
            if any(NUMERIC_CELL.fullmatch(cell) for cell in cells):
                break
            headers.append(cells)
        return _cells(lines[index]), headers


def _column_header(headers: list[list[str]], column: int) -> str:
    """머리글 행들에서 그 열의 제목. 병합 칸은 빈칸으로 읽히므로 왼쪽의 가장 가까운 제목을 씁니다."""
    parts = []
    for row in headers:
        for c in range(min(column, len(row) - 1), -1, -1):
            if row[c]:
                parts.append(row[c])
                break
    return " ".join(parts)


def _value_column(cells: list[str], value: str | None) -> int | None:
    digits = DIGITS.sub("", value or "")
    if not digits:
        return None
    # 숫자만 든 칸(단위 허용)만 봅니다. "2순위"·"39A" 같은 제목 칸의 숫자와 맞춰지면 안 됩니다(실측 오탐: 가구원 수 2 ↔ "2순위")
    hits = [i for i, cell in enumerate(cells) if NUMERIC_CELL.fullmatch(cell) and DIGITS.sub("", cell) == digits]
    return hits[0] if len(hits) == 1 else None


# ---- V6 표 위치 대조 ----

# 모집 수 열 대조: 이번 모집 수(OFFERED)·예비자(RESERVE)를 건설 호수·현재 공가·대기 중 예비자 열에서 읽은 것.
# 실측(2026-10-16 sol 정답표 대조): 예비입주자 모집 공고에서 「건설 호수 25 | 현재 공가 1 | 대기 중 예비자 2 | 금회 모집 11」의
# 25를 모집 수로, 「세대수 143 | 대기 중 예비 4 | 금회 모집 46」의 4를 모집 수로 넣어 모집 수 재현율 47.8%
_THIS_ROUND = re.compile(r"모집|금회|이번|신규")
COUNT_KINDS_BY_HEADER = {"OFFERED": _THIS_ROUND, "RESERVE": _THIS_ROUND}
HEADER_COUNT_KINDS = [
    ("WAITLIST", re.compile(r"대기\s*(?:중|자)|기존\s*예비|잔여\s*예비")),
    ("CURRENT_VACANCIES", re.compile(r"공\s*가")),
    ("TOTAL_HOUSING", re.compile(r"건설|총\s*(?:세대|호)|전체\s*(?:세대|호)|단지\s*세대")),
]


def _count_header(found: _Located, count: dict[str, Any]) -> str | None:
    """수량 값을 읽은 표 칸의 열 제목(근거 행에서 그 값이 한 칸에만 있을 때)."""
    for evidence_id in count["evidenceIds"]:
        located = found.row(evidence_id)
        if located is None:
            continue
        cells, headers = located
        column = _value_column(cells, str(count["value"]))
        if column is not None and headers:
            return _column_header(headers, column) or None
    return None


def _context_mismatch(found: _Located, evidence_ids: list[str], value: str, labels: list[str], types: set[str]) -> str | None:
    """값이 든 표 칸의 행 제목·열 머리글이 말하는 순위·대상·주택형이 붙인 것과 겹치지 않으면 그 설명을, 아니면 None을 돌려줍니다."""
    want_ranks = set().union(*(_ranks(label) for label in labels)) if labels else set()
    want_groups = set().union(*(_groups(label) for label in labels)) if labels else set()
    own_row_without_value = False
    for n, evidence_id in enumerate(evidence_ids):
        located = found.row(evidence_id)
        if located is None:
            continue
        cells, headers = located
        column = _value_column(cells, value)
        if column is None:
            own_row_without_value = own_row_without_value or n == 0
            continue
        if own_row_without_value:
            # 첫 근거(자기 행)에는 값이 없고 뒤 근거 행에만 있음: 세로 병합 칸의 값을 그 칸이 시작한 행과 함께 인용한 것입니다
            # (supply_tables가 병합 칸 값에 원래 행을 근거로 덧붙임). 원래 행의 행 제목은 다른 대상이라 대조하지 않습니다(2026-10-24 다섯 번째 채점: 오탐 14)
            return None
        row_label = " ".join(cells[: min(column, 3)])
        header = _column_header(headers, column)
        # 행 제목에 표시가 있으면 그것만 봅니다. 머리글 행이 따로 없는 표(| 1순위 | ... | / | 2순위 | ... |)에서는
        # 첫 데이터 행이 머리글로 읽히기 때문입니다(실측: LH 국민임대 순위별 소득 기준 표).
        have_ranks = _ranks(row_label) or _ranks(header)
        have_groups = _groups(row_label) or _groups(header)
        have_types = _types(row_label)
        quoted = "| " + " | ".join(cells) + " |"
        if want_ranks and have_ranks and not want_ranks & have_ranks:
            return f"순위 {sorted(want_ranks)}로 붙였지만 원문 표의 그 칸은 {sorted(have_ranks)}순위입니다 「{quoted[:120]}」"
        if want_groups and have_groups and not want_groups & have_groups:
            return f"대상 {sorted(want_groups)}로 붙였지만 원문 표의 그 칸은 {sorted(have_groups)} 대상입니다 「{quoted[:120]}」"
        if types and have_types and not types & have_types:
            return f"주택형 {sorted(types)}에 붙였지만 원문 표의 그 행은 {sorted(have_types)}입니다 「{quoted[:120]}」"
    return None


def _check_positions(candidate: dict[str, Any], found: _Located, find) -> None:
    """V6: 공급 가격·수량과 자격 조건 숫자가 원문 표의 제자리에서 읽혔는지, 수량 종류가 열 제목과 맞는지 봅니다."""
    for g, group in enumerate(candidate["supplyGroups"]):
        types = _types(" ".join(filter(None, [group.get("housingTypeCode"), group.get("unitLabel")])))
        group_labels = group["scope"]["targetGroups"]
        for p, price in enumerate(group["prices"]):
            labels = [*price["scope"]["targetGroups"], *group_labels]
            problem = _context_mismatch(found, price["evidenceIds"], price["sourceAmount"], labels, types)
            if problem:
                find("V6", "VALUE_POSITION_SUSPECTED", f"/supplyGroups/{g}/prices/{p}", problem)
        for c, count in enumerate(group["counts"]):
            labels = [*count["scope"]["targetGroups"], *group_labels]
            problem = _context_mismatch(found, count["evidenceIds"], str(count["value"]), labels, types)
            if problem:
                find("V6", "VALUE_POSITION_SUSPECTED", f"/supplyGroups/{g}/counts/{c}", problem)
            header = _count_header(found, count) if count["kind"] in COUNT_KINDS_BY_HEADER else None
            if header and not COUNT_KINDS_BY_HEADER[count["kind"]].search(header):
                expected = next((kind for kind, pattern in HEADER_COUNT_KINDS if pattern.search(header)), None)
                if expected and expected != count["kind"]:
                    find(
                        "V6",
                        "COUNT_KIND_SUSPECTED",
                        f"/supplyGroups/{g}",
                        f"{count['kind']} {count['value']}을(를) 원문 표의 「{header}」 열에서 읽었습니다. 그 열은 {expected}입니다.",
                    )
    for e, item in enumerate(candidate["eligibility"]):
        for path, atom in _atoms(item["rule"]["expression"], f"/eligibility/{e}/rule/expression"):
            if not isinstance(atom.get("value"), int | float) or isinstance(atom["value"], bool):
                continue
            value = str(int(atom["value"])) if float(atom["value"]).is_integer() else str(atom["value"])
            problem = _context_mismatch(found, atom.get("evidenceIds") or item["evidenceIds"], value, item["scope"]["targetGroups"], set())
            if problem:
                find("V6", "VALUE_POSITION_SUSPECTED", path, problem)


def _atoms(expression: dict[str, Any] | None, path: str):
    if not expression:
        return
    if expression["kind"] == "ATOMIC":
        yield path, expression
    for i, child in enumerate(expression.get("children") or []):
        yield from _atoms(child, f"{path}/children/{i}")


# ---- V7 앞뒤 일관성 ----

# 순서가 정해진 일정 종류. 앞 종류의 가장 이른 시작이 뒤 종류의 가장 이른 시작보다 늦으면 의심합니다(빠진 종류는 건너뛰고 모든 쌍).
ORDER = ["ANNOUNCEMENT", "APPLICATION", "WINNER_ANNOUNCEMENT", "CONTRACT", "MOVE_IN"]
# (속성, 최솟값, 최댓값) — 공공 주거 공고에서 나올 수 없는 값
ATOM_RANGES = {"AGE_YEARS": (0, 120), "YOUNGEST_CHILD_AGE_YEARS": (0, 18), "INCOME_BENCHMARK_PERCENT": (10, 400), "MARRIAGE_MONTHS": (0, 600)}
AREA_RANGE = (5.0, 400.0)
MAX_AMOUNT = 5_000_000_000  # 50억
MAX_MONTHLY = 10_000_000  # 월 1천만원


def _day(value: dict[str, str] | None) -> tuple[date, bool] | None:
    """(날짜, 월만 앎). 월만 알면 그 달 1일로 두고 비교도 달 단위로 합니다."""
    if not value:
        return None
    text = value["value"]
    try:
        if value["precision"] == "MONTH":
            return date.fromisoformat(f"{text[:7]}-01"), True
        return date.fromisoformat(text[:10]), False
    except ValueError:
        return None


def _before(a: tuple[date, bool], b: tuple[date, bool]) -> bool:
    if a[1] or b[1]:
        return (a[0].year, a[0].month) <= (b[0].year, b[0].month)
    return a[0] <= b[0]


def _check_consistency(candidate: dict[str, Any], find) -> None:
    """V7: 일정 앞뒤 순서, 면적·금액·자격 값의 정상 범위, 보증금보다 큰 월임대료, 묶음 모집 수 합과 공고 전체 모집 수를 봅니다."""
    earliest: dict[str, tuple[int, tuple[date, bool]]] = {}
    for s, schedule in enumerate(candidate["schedules"]):
        start, end = _day(schedule["startsAt"]), _day(schedule["endsAt"])
        if start and end and not _before(start, end):
            find("V7", "SCHEDULE_ORDER_SUSPECTED", f"/schedules/{s}", f"{schedule['rawLabel']}: 끝({end[0]})이 시작({start[0]})보다 이릅니다.")
        if start:
            for kind in schedule["kinds"]:
                if kind not in earliest or start[0] < earliest[kind][1][0]:
                    earliest[kind] = (s, start)
    pairs = [(first, then) for i, first in enumerate(ORDER) for then in ORDER[i + 1 :]]
    flagged: set[int] = set()
    for first, then in pairs:
        if first in earliest and then in earliest and not _before(earliest[first][1], earliest[then][1]) and earliest[then][0] not in flagged:
            flagged.add(earliest[then][0])
            s = earliest[then][0]
            find(
                "V7",
                "SCHEDULE_ORDER_SUSPECTED",
                f"/schedules/{s}",
                f"{then}({earliest[then][1][0]})가 {first}({earliest[first][1][0]})보다 이릅니다.",
            )

    for g, group in enumerate(candidate["supplyGroups"]):
        area = group.get("exclusiveAreaSqm")
        if isinstance(area, int | float) and not AREA_RANGE[0] <= area <= AREA_RANGE[1]:
            find("V7", "VALUE_OUT_OF_RANGE", f"/supplyGroups/{g}/exclusiveAreaSqm", f"전용면적 {area}㎡는 주택 면적으로 보기 어렵습니다.")
        plans: dict[tuple[Any, tuple[str, ...]], dict[str, tuple[int, int]]] = {}
        for p, price in enumerate(group["prices"]):
            amount = price["amountKrw"]
            if amount is None:
                continue
            limit = MAX_MONTHLY if price["kind"] == "MONTHLY_RENT" else MAX_AMOUNT
            if not 0 <= amount <= limit:
                find("V7", "VALUE_OUT_OF_RANGE", f"/supplyGroups/{g}/prices/{p}", f"{price['kind']} {amount:,}원은 정상 범위를 벗어납니다.")
            key = (price["pricePlanId"], tuple(sorted(price["scope"]["targetGroups"])))
            plans.setdefault(key, {})[price["kind"]] = (p, amount)
        for plan in plans.values():
            if "DEPOSIT" in plan and "MONTHLY_RENT" in plan and plan["DEPOSIT"][1] > 0 and plan["MONTHLY_RENT"][1] > plan["DEPOSIT"][1]:
                find(
                    "V7",
                    "RENT_EXCEEDS_DEPOSIT",
                    f"/supplyGroups/{g}/prices/{plan['MONTHLY_RENT'][0]}",
                    f"월임대료({plan['MONTHLY_RENT'][1]:,}원)가 보증금({plan['DEPOSIT'][1]:,}원)보다 큽니다. 두 값이 바뀌었는지 확인하세요.",
                )

    for e, item in enumerate(candidate["eligibility"]):
        for path, atom in _atoms(item["rule"]["expression"], f"/eligibility/{e}/rule/expression"):
            bounds = ATOM_RANGES.get(atom.get("attribute"))
            values = atom.get("value") if isinstance(atom.get("value"), list) else [atom.get("value")]  # BETWEEN은 [아래, 위]
            numbers = [v for v in values if isinstance(v, int | float) and not isinstance(v, bool)]
            value = next((v for v in numbers if bounds and not bounds[0] <= v <= bounds[1]), None)
            if bounds and value is not None:
                find("V7", "VALUE_OUT_OF_RANGE", path, f"{atom['attribute']} {value}는 정상 범위({bounds[0]}~{bounds[1]})를 벗어납니다.")

    # 공고 전체 모집 수(대상군 없음) ↔ 공급 묶음 모집 수 합. 범위가 같은 것끼리만 비교합니다(검토 2026-10-16: 신규만 센 전체 수와
    # 재공급이 섞인 묶음 합을 비교해 오탐). 묶음마다 같은 범위의 모집 수가 정확히 하나씩일 때만 더합니다(대상군별 수는 겹칠 수 있음).
    def category(count: dict[str, Any]) -> str:
        return count["scope"].get("supplyCategory") or "ALL"

    totals = [c for c in candidate["notice"]["counts"] if c["kind"] == "OFFERED" and not c["scope"]["targetGroups"] and isinstance(c["value"], int)]
    if len(totals) == 1 and candidate["supplyGroups"]:
        total = totals[0]
        parts = [[c for c in g["counts"] if c["kind"] == "OFFERED" and not c["scope"]["targetGroups"]] for g in candidate["supplyGroups"]]
        same_scope = all(len(p) == 1 and isinstance(p[0]["value"], int) and category(p[0]) in (category(total), "ALL") for p in parts)
        mixed = category(total) == "ALL" and len({category(p[0]) for p in parts if len(p) == 1}) > 1
        if same_scope and not mixed:
            summed = sum(p[0]["value"] for p in parts)
            if summed != total["value"]:
                # 판정에 쓰지 않는 수량이라 공급 섹션 메모로 둡니다(공고 섹션에 두면 사람 확인으로 막힘)
                find("V7", "COUNT_TOTAL_SUSPECTED", "/supplyGroups", f"주택형별 모집 수 합({summed})이 공고 전체 모집 수({total['value']})와 다릅니다.")


# 호실마다 한 묶음인 공급(HOUSING_UNIT)에서 모집 1로 센 서로 다른 호실이 공고 전체 모집 수보다 많으면, 이번 모집이 아닌 호실까지 센 것입니다.
# 어느 호실이 이번 모집인지 정할 수 없어 그 묶음들의 수량을 모두 보류합니다(틀린 값보다 누락). 같은 호실이 표 두 개에 나와 묶음이 겹쳐도
# 호실 이름으로 셉니다. 2026-11-09 23건 sh-311005: 「모집 세대수 원룸1세대추가모집」인데 수량 열 없는 층별 구성표·임대료표의 호실 24행을
# 모두 모집 1로 셈(대상 「1인 가구」가 붙어 위 합계 검사는 건너뜀) — 공고 보류가 풀리면 틀린 모집 1이 16개 게시됨. 저장 결과 전체에서
# 걸린 것은 이 공고와 V1·옛 V2가 틀리게 게시한 gndc 두 공고(호실 7곳 대 모집 2, 4곳 대 1)뿐
UNIT_COUNTS = "UNIT_COUNTS_EXCEED_TOTAL"


def _check_unit_counts(candidate: dict[str, Any], find: Any) -> None:
    totals = [c for c in candidate["notice"]["counts"] if c["kind"] == "OFFERED" and not c["scope"]["targetGroups"] and isinstance(c["value"], int)]
    if len(totals) != 1:
        return
    units = [
        (g, str(group.get("unitLabel")))
        for g, group in enumerate(candidate["supplyGroups"])
        if group.get("itemKind") == "HOUSING_UNIT" and any(c["kind"] == "OFFERED" and c["value"] == 1 for c in group["counts"])
    ]
    distinct = {label for _, label in units}
    if len(distinct) <= totals[0]["value"]:
        return
    for g, _ in units:
        find(
            "V7",
            UNIT_COUNTS,
            f"/supplyGroups/{g}/counts",
            f"호실 {len(distinct)}곳을 모집 1로 셌는데 공고 전체 모집 수는 {totals[0]['value']}입니다. 어느 호실이 이번 모집인지 원문 확인이 필요합니다",
        )


# 같은 단지·주택형의 모집 수가 표 두 곳에서 다름: 대상 없이 센 주택형 모집 수가 같은 주택형의 대상별 모집 수 합과 다르면, 대상 없는 수가
# 이번 모집이 아니라 대상 주택 규모(건설·공급 호수)일 수 있어 그 수량을 보류합니다(틀린 값보다 누락). 대상별 수는 계층마다 따로 센 더 자세한 수라 둡니다.
# 2026-11-10 23건 유료 확인 dcco-24804(추가모집): 「□ 임대대상 : 64호」 아래 형별 「공급 호수」(11·28·25 = 형·계층별 표의 건설 호수 합)를
# 열 의미 답이 모집 수로 읽어 게시됨. 같은 형의 계층별 모집 수 합은 2+7·11+2·7+6. 앞선 답은 같은 열을 건설 호수로 읽었음(회차마다 흔들리는 판단)
TYPE_COUNTS = "TYPE_COUNTS_DISAGREE"


def _check_type_counts(candidate: dict[str, Any], find: Any) -> None:
    untargeted: dict[tuple[Any, str], list[tuple[int, int]]] = {}
    targeted: dict[tuple[Any, str], list[int]] = {}
    for g, group in enumerate(candidate["supplyGroups"]):
        code = str(group.get("housingTypeCode") or "").strip()
        if not code:
            continue
        key = (group.get("locationId"), code)
        for count in group["counts"]:
            if count["kind"] != "OFFERED" or not isinstance(count["value"], int):
                continue
            if count["scope"]["targetGroups"]:
                targeted.setdefault(key, []).append(count["value"])
            else:
                untargeted.setdefault(key, []).append((g, count["value"]))
    for key, counts in untargeted.items():
        summed = sum(targeted.get(key) or [])
        for g, value in counts:
            if key in targeted and value != summed:
                find(
                    "V7",
                    TYPE_COUNTS,
                    f"/supplyGroups/{g}/counts",
                    f"주택형 {key[1]} 모집 수 {value}가 같은 주택형의 대상별 모집 수 합({summed})과 다릅니다. "
                    "대상 주택 규모(건설·공급 호수)일 수 있어 원문 확인이 필요합니다",
                )


# ---- V8 누락 탐지 ----

SECTION_HEADINGS = {
    "eligibility": re.compile(r"신청\s*자격|입주\s*자격|자격\s*요건"),
    "requiredDocuments": re.compile(r"제출\s*서류|구비\s*서류|증빙\s*서류"),
    "schedules": re.compile(r"접수\s*기간|신청\s*기간|모집\s*일정|공급\s*일정|청약\s*일정|신청\s*일정"),
}
# 자격 기준 종류: (이름, 원문에서 그 기준이 "값과 함께" 적힌 모양, 결과에서 그 기준으로 인정할 속성, 결과 글자에서 인정할 낱말)
# 원문에 기준이 있는데 결과의 어느 자격 조건도 그 기준을 다루지 않으면 하나가 통째로 빠진 것으로 봅니다(검토 2026-10-16:
# 소득 70% 조건을 지워도 자동 완료되던 것). 조건식으로 못 바꾼 조건(UNSTRUCTURED)도 글자에 낱말이 있으면 다룬 것으로 칩니다.
CRITERIA = [
    ("소득 기준", re.compile(r"월\s*평균\s*소득[^\n]{0,60}?\d+(?:\.\d+)?\s*%"), {"INCOME_BENCHMARK_PERCENT", "MONTHLY_INCOME_KRW"}, ("소득",)),
    ("총자산 기준", re.compile(r"총\s*자산[^\n]{0,60}?\d[\d,]*\s*(?:억|만|백만|천만)?\s*원"), {"TOTAL_ASSETS_KRW"}, ("자산",)),
    ("자동차 가액 기준", re.compile(r"자동차[^\n]{0,40}?가액[^\n]{0,60}?\d[\d,]*\s*(?:억|만|백만|천만)?\s*원"), {"CAR_ASSETS_KRW"}, ("자동차",)),
    ("무주택 요건", re.compile(r"무주택\s*(?:세대|가구|자|요건)"), {"HOMELESS"}, ("무주택",)),
    # 나이는 신청자 기준(만 19세 이상)만: 「만 14세 미만은 보호자 서명」 같은 안내와 표 칸(청년근로자(만39세이하) 수)은 빼려고 본문 줄에서만 찾습니다
    # 「만60세 이상의 직계존속이 주택을 소유」처럼 가족의 나이를 말하는 문장은 신청자 나이 기준이 아닙니다(실측 청약홈 에코델타 무주택 설명)
    (
        "나이 기준",
        re.compile(r"^(?!\s*\|).*?만\s*(?:19|[2-9]\d)\s*세\s*(?:이상|이하|미만|초과)(?!\s*의\s*(?:직계|부모|노부모|자녀|배우자|세대원))", re.M),
        {"AGE_YEARS"},
        ("세 이상", "세 이하", "나이", "연령", "성년"),
    ),
]
# 자격 기준인 소득 비율: 「월평균소득(의) 100% 이하」. 뒤에 "초과"가 오는 할증 구간표·「1인 70%」 같은 괄호 안 가구원 수별 값은 빼고 대표 값만
INCOME_PERCENT = re.compile(r"월\s*평균\s*소득(?:의|액)?\s*(\d{2,3}(?:\.\d+)?)\s*%(?!\s*(?:를|을)?\s*초과)(?=\s*(?:\(|이하|미만|이내|\s))")
# 글로만 남기면 안 되는 자격 조건 종류와 그 기준값 모양(조건 원문·근거 인용에 있으면 조건식으로 바꿀 수 있음).
# 빈칸 양식 「( 24,500 )만원 이하」도 같은 기준값입니다(2026-11-06 23건 측정: 이 모양이라 글로만 남긴 자산·자동차 기준이 경고 없이 게시됨)
_AMOUNT_LIMIT = re.compile(r"\d[\d,]*\s*\)?\s*(?:억|천만|백만|만|천)?\s*원\s*(?:이하|미만|이내|초과|이상)")
UNSTRUCTURED_VALUE = {
    "INCOME": re.compile(r"\d{2,3}(?:\.\d+)?\s*(?:%|퍼센트)|" + _AMOUNT_LIMIT.pattern),
    "ASSETS": _AMOUNT_LIMIT,
    "CAR_ASSETS": _AMOUNT_LIMIT,
}
SHEET_START = "=== 첨부 엑셀 "
NUMBER_CELL = re.compile(r"[\d][\d,.\s]*")
TRUNCATED = "행만 보입니다"


def _check_omissions(candidate: dict[str, Any], sources: SourceBundle, find) -> None:
    """V8: 원문에 있는데 결과에 빠진 섹션·자격 기준·소득 비율·가점표·첨부 엑셀 주택 행과, 값이 있는데 글로만 남긴 자격 조건을 찾습니다."""
    text = "\n".join(sources.texts.values())
    coverage = candidate["quality"]["coverage"]
    for section, heading in SECTION_HEADINGS.items():
        if not candidate[section] and coverage[section]["status"] == "EXTRACTED":
            match = heading.search(text)
            if match:
                find("V8", "SECTION_OMISSION_SUSPECTED", f"/{section}", f"원문에 「{match[0]}」 절이 있는데 추출된 항목이 없습니다.")

    if candidate["eligibility"]:
        items = candidate["eligibility"]
        attributes = {a.get("attribute") for e in items for _, a in _atoms(e["rule"]["expression"], "")}
        for e in items:
            for exception in e.get("exceptions") or []:
                attributes |= {a.get("attribute") for _, a in _atoms((exception.get("when") or {}).get("expression"), "")}
        words = " ".join(f"{e.get('originalText') or ''} {e.get('description') or ''}" for e in items)
        for name, pattern, attrs, keywords in CRITERIA:
            match = pattern.search(text)
            if match and not attributes & attrs and not any(k in words for k in keywords):
                quoted = match[0].strip()[-80:]
                find("V8", "ELIGIBILITY_OMISSION_SUSPECTED", "/eligibility", f"원문에 {name}이 있는데 자격 조건에 없습니다 「{quoted}」")

        # 값이 적힌 소득·자산 기준을 조건식 없이 글로만 남긴 것(UNSTRUCTURED). 위 검사는 낱말만 있으면 다룬 것으로 쳐서 그대로 완료되었습니다.
        # 실측(2026-10-16 시험): 「월평균소득 100%(1인 120%…)」 표를 글로만 남긴 소득 조건이 자동 완료 → 지원 가능 판정에 쓸 수 없음
        quotes = {ev["id"]: ev["quote"] for ev in candidate.get("evidence") or []}
        for index, e in enumerate(items):
            value = UNSTRUCTURED_VALUE.get(e.get("category"))
            if value is None or e["rule"]["status"] != "UNSTRUCTURED":
                continue
            # 이번 모집에 적용하지 않는 기본 기준(규칙 19-7: 「기본 70%」 대신 「금회 완화 150%」 적용)은 일부러 글로 둡니다.
            # 같은 종류의 다른 조건이 조건식으로 있을 때만 봐줍니다(실측 2026-10-18 LH 태백장성: 적용하지 않는 70%가 보류됨)
            applied = any(o is not e and o.get("category") == e.get("category") and o["rule"]["status"] == "STRUCTURED" for o in items)
            if applied and NOT_APPLIED.search(e["rule"].get("reason") or ""):
                continue
            # 원문이 그 기준을 적용하지 않는다고 적은 조건(「자산기준 : 배제」)은 일부러 조건식 없이 둔 것입니다. 근거로 붙은 옆 행의 기준값으로
            # 걸지 않습니다(조건 원문 글에 기준값이 없을 때만). 2026-11-09 23건 jbdc-15611: 옆 행의 「345백만원 이하」로 보류됨
            original = e.get("originalText") or ""
            if WAIVED.search(original) and not value.search(original):
                continue
            cited = " ".join([original, *(quotes.get(i, "") for i in e.get("evidenceIds") or [])])
            found = value.search(cited)
            if found:
                find("V8", "CRITERION_NOT_STRUCTURED", f"/eligibility/{index}", f"기준값 「{found[0]}」이 적힌 조건을 조건식 없이 글로만 남겼습니다.")

        # 소득 기준 일부 누락: 원문의 소득 비율(「월평균소득 100% 이하」)마다 그 비율을 쓰는 자격 조건(값·예외·글자)이 있어야 합니다.
        # 검토 지적: 소득 기준이 통째로 빠진 것만 잡고, 순위별 두 기준 중 하나가 빠진 것은 못 잡았음. 「○○% 초과」(할증 구간표)는 뺍니다.
        # 선정 순위(1순위 = 소득 50% 이하)·계층별 임대 조건(수급자·소득 80% 이내 구분)에 쓰인 비율도 다룬 것으로 칩니다
        used: set[float] = set()
        for e in items:
            used |= {float(a["value"]) for _, a in _atoms(e["rule"]["expression"], "") if isinstance(a.get("value"), int | float)}
            for exception in e.get("exceptions") or []:
                for key in ("when", "effectExpression"):
                    node = exception.get(key) or {}
                    used |= {
                        float(a["value"]) for _, a in _atoms(node.get("expression") if key == "when" else node, "") if isinstance(a.get("value"), int | float)
                    }
        for rule in candidate["selectionRules"]:
            used |= {float(a["value"]) for _, a in _atoms((rule.get("rule") or {}).get("expression"), "") if isinstance(a.get("value"), int | float)}
        related = " ".join(
            [words]
            + [f"{r.get('originalText') or ''} {r.get('description') or ''}" for r in candidate["selectionRules"]]
            + [str(p["scope"].get("description") or "") + " " + " ".join(p["scope"]["targetGroups"]) for g in candidate["supplyGroups"] for p in g["prices"]]
        )
        # 신청 자격이 아닌 소득 기준(재계약·분양전환·임대조건 구분·할증)은 앞 120자에 그 말이 있으면 셈하지 않습니다.
        # 실측(107건): 남은 경보 중 실제 누락은 일부(고령 국민임대의 완화 기준 150%)라 사람 확인이 아니라 화면 메모로 둡니다(verifier.ALWAYS_NOTE_CODES).
        for match in INCOME_PERCENT.finditer(text):
            percent = float(match[1])
            if re.search(r"재계약|분양\s*전환|임대\s*조건|할증|시중\s*시세", text[max(0, match.start() - 120) : match.start()]):
                continue
            if percent not in used and not re.search(rf"(?<![\d.]){match[1]}\s*%", related):
                find(
                    "V8",
                    "INCOME_CRITERION_UNUSED",
                    "/eligibility",
                    f"원문의 소득 기준 {match[1]}%를 쓰는 자격·선정 조건이 없습니다 「{match[0].strip()[-80:]}」",
                )
                break

    lines = text.split("\n")
    scoring_rows = 0
    for i, line in enumerate(lines):
        if _row_line(line) and (i == 0 or not _in_table(lines[i - 1])):
            table = []
            for row in lines[i:]:
                if not _in_table(row):
                    break
                if _row_line(row):  # 읽기 도움 줄(↳)은 세지 않습니다
                    table.append(row)
            if any("배점" in row for row in table[:3]):
                scoring_rows += sum(1 for row in table[1:] if re.search(r"\d\s*점|\|\s*\d{1,2}\s*\|", row))
    if scoring_rows >= 3 and not any(rule["kind"] == "SCORING" for rule in candidate["selectionRules"]):
        find("V8", "SCORING_OMISSION_SUSPECTED", "/selectionRules", f"원문에 배점표({scoring_rows}행)가 있는데 가점 항목이 없습니다.")

    for block in text.split(SHEET_START)[1:]:
        body = block.split("\n=== ", 1)[0]
        if TRUNCATED in body:
            continue
        rows = [line for line in body.split("\n")[1:] if line.lstrip().startswith("|")]
        # 주택 행: 숫자만 든 칸(호수·면적·보증금 등)이 있는 행. 제목 행(날짜 든 긴 글)·머리글 행(1순위 등)은 세지 않습니다
        homes = sum(1 for row in rows if any(NUMBER_CELL.fullmatch(cell) for cell in _cells(row)) and not re.search(r"합\s*계|소\s*계", row))
        listed = max(len(candidate["locations"]), sum(1 for g in candidate["supplyGroups"] if g.get("itemKind") == "HOUSING_UNIT"))
        if homes >= 5 and listed < homes * 0.8:
            name = block.split(" ===", 1)[0]
            find("V8", "LIST_OMISSION_SUSPECTED", "/locations", f"첨부 엑셀 {name}의 주택 행은 약 {homes}개인데 위치·호실은 {listed}개입니다.")


IMAGE_BLANK_FIELD = re.compile(r"^/supplyGroups/\d+/(exclusiveAreaSqm|prices)")


# 첨부 PDF가 공고문이 아니라 Q&A·서식 모음인 경우(실측: 경남개발공사 전세임대 2차 — 첨부 PDF가 「… 관련 Q&A」인데 공고로 자동 완료).
# 수집 제목은 공고 제목이라 걸리지 않으므로 AI가 문서에서 읽은 제목을 봅니다. 수집 공고 제목 66개·추출 제목 19개에 오탐 없음
NOT_A_NOTICE = re.compile(r"Q\s*&\s*A|FAQ|질의\s*응답|자주\s*(?:묻는|하는)\s*질문|문답|(?:신청서|서식|양식|동의서)\s*(?:모음|일체|\(.*?\))?\s*$")


def _check_notice_document(candidate: dict[str, Any], find: Any) -> None:
    title = str((candidate.get("notice") or {}).get("title") or "")
    match = NOT_A_NOTICE.search(title)
    if match:
        find("V8", "NOT_A_NOTICE_SUSPECTED", "/notice", f"문서 제목 「{title[:60]}」이 공고문이 아닌 {match[0]} 문서로 보입니다. 공고문 원본을 확인하세요.")


def _evidence_ids(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node.get("evidenceIds") or []) | {i for value in node.values() for i in _evidence_ids(value)}
    if isinstance(node, list):
        return {i for value in node for i in _evidence_ids(value)}
    return set()


IMAGE_QUOTE_MIN_CHARS = 6  # 그림 밖 원문에서도 찾는 근거 글의 최소 길이(띄어쓰기 뺀 글자 수)


def _outside(text: str, ranges: list[tuple[int, int]]) -> list[str]:
    """글에서 주어진 구간(그림 판독 묶음)을 뺀 나머지 조각들. 조각끼리 잇지 않아 앞뒤 글이 붙어 새 글이 생기지 않습니다."""
    kept, at = [], 0
    for start, end in sorted(ranges):
        kept.append(text[at:start])
        at = max(at, end)
    kept.append(text[at:])
    return kept


def _check_image_evidence(candidate: dict[str, Any], sources: SourceBundle, find: Any) -> None:
    """그림 판독 글자(AI가 옮긴 글자, image_reading)를 근거로 한 값: 판정에 쓰는 자격·공고 정보는 사람 확인, 그 밖은 표시만.
    판독 글자는 원문 그림과 맞춰 본 사람이 없어서 근거 확인(V2)이 통과해도 판독 오류를 걸러 내지 못합니다."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    for source_id, text in sources.texts.items():
        for head in re.finditer(re.escape(IMAGE_BLOCK_HEAD), text):
            following = text.find("\n=== ", head.end())
            ranges.setdefault(source_id, []).append((head.start(), len(text) if following < 0 else following))
    if not ranges:
        return
    from_image = {
        e["id"]
        for e in candidate.get("evidence") or []
        if e["locator"]["kind"] == "TEXT_RANGE" and any(a <= e["locator"]["start"] < b for a, b in ranges.get(e["sourceId"], []))
    }
    # 그림 판독 글자를 근거로 했어도 같은 글이 그림 밖 원문 글자나 수집기가 읽은 게시글 제목(원본 참조 sourceTitle)에도 있으면 판독에 기대지
    # 않은 값입니다(띄어쓰기를 빼고 비교, 짧은 글은 우연히 겹칠 수 있어 그대로 그림 근거). 2026-11-09 23건 sh-311005: 표지 그림의
    # 「에어스페이스 신림3호점」을 공고 제목 근거로 써 공고 전체(찾은 값 138개)가 검수로 감. 첨부 PDF가 있으면 원문은 PDF 글자뿐이고
    # PDF 글자층에는 「신림3호점 … 에어스페이스」 순서로만 있음. 게시글 제목 「[토지지원 사회주택]에어스페이스 신림3호점_어울리 입주자 모집 공고」에 있음
    outside = [normalize(piece) for source_id, text in sources.texts.items() for piece in _outside(text, ranges.get(source_id, []))]
    outside += [normalize(str(ref.get("sourceTitle") or "")) for ref in candidate.get("sourceReferences") or [] if isinstance(ref, dict)]
    quotes = {e["id"]: normalize(e.get("quote") or "") for e in candidate.get("evidence") or []}
    from_image = {i for i in from_image if len(quotes.get(i, "")) < IMAGE_QUOTE_MIN_CHARS or not any(quotes[i] in text for text in outside)}
    if not from_image:
        return
    _check_disputed_reading(candidate, sources, from_image, find)
    if _evidence_ids(candidate["notice"]) & from_image:
        find("V8", "EVIDENCE_FROM_IMAGE", "/notice", "공고 정보의 근거가 AI가 그림에서 옮긴 글자입니다. 원문 그림과 맞는지 확인하세요.")
    for index, item in enumerate(candidate["eligibility"]):
        if _evidence_ids(item) & from_image:
            find("V8", "EVIDENCE_FROM_IMAGE", f"/eligibility/{index}", "자격 조건의 근거가 AI가 그림에서 옮긴 글자입니다. 원문 그림과 맞는지 확인하세요.")
    for section in ("supplyGroups", "locations", "schedules", "selectionRules", "requiredDocuments"):
        count = sum(1 for item in candidate.get(section) or [] if _evidence_ids(item) & from_image)
        if count:
            find("V8", "IMAGE_TRANSCRIBED_VALUES", f"/{section}", f"{count}개 항목이 AI가 그림에서 옮긴 글자를 근거로 합니다(원문 그림 확인 권장).")


# 그림을 두 번 따로 읽어 글자가 다른 줄(image_reading.DISPUTED_HEAD 묶음). 이 줄을 근거로 한 값은 판독 오류일 수 있어 사람 확인입니다
# (2026-11-05 실측: 같은 가격표 그림을 실행마다 250,600·250,500으로 읽어 틀린 월임대료가 자동 게시됨). 그 묶음의 가격·수량 칸만 보류합니다
IMAGE_DISPUTED_HEAD = "=== 그림 판독 불일치 "
IMAGE_DISPUTED_LINE = "불일치 줄: "
IMAGE_DISAGREES = "IMAGE_READING_DISAGREES"


def _disputed_rows(sources: SourceBundle) -> list[str]:
    rows = []
    for text in sources.texts.values():
        at = text.find(IMAGE_DISPUTED_HEAD)
        for line in text[at:].split("\n")[1:] if at >= 0 else []:
            if line.startswith("=== "):
                break
            if line.startswith(IMAGE_DISPUTED_LINE):
                rows.append("".join(line[len(IMAGE_DISPUTED_LINE) :].replace("¦", "|").split()))
    return [r for r in rows if r]


def _check_disputed_reading(candidate: dict[str, Any], sources: SourceBundle, from_image: set[str], find: Any) -> None:
    rows = _disputed_rows(sources)
    if not rows:
        return
    disputed = set()
    for evidence in candidate.get("evidence") or []:
        quote = "".join(str(evidence.get("quote") or "").split())
        if evidence["id"] in from_image and len(quote) >= 4 and any(quote in row or row in quote for row in rows):
            disputed.add(evidence["id"])
    if not disputed:
        return
    description = "두 번 따로 읽은 그림 글자가 이 근거 줄에서 다릅니다(판독 오류일 수 있음). 원문 그림과 맞춰 확인하세요."
    for g, group in enumerate(candidate["supplyGroups"]):
        own = {k: v for k, v in group.items() if k not in ("prices", "counts")}
        if _evidence_ids(own) & disputed:
            find("V8", IMAGE_DISAGREES, f"/supplyGroups/{g}", description)
            continue
        for field in ("prices", "counts"):
            if _evidence_ids(group.get(field)) & disputed:
                find("V8", IMAGE_DISAGREES, f"/supplyGroups/{g}/{field}", description)
    for section in ("eligibility", "locations", "schedules", "selectionRules", "requiredDocuments"):
        for index, item in enumerate(candidate.get(section) or []):
            if _evidence_ids(item) & disputed:
                find("V8", IMAGE_DISAGREES, f"/{section}/{index}", description)


def _check_image_content(candidate: dict[str, Any], sources: SourceBundle, find: Any) -> None:
    """공급 가격·면적을 "원문에 없음"으로 비웠는데 PDF에 글자 없는 큰 그림이 있으면, 그 표가 그림으로 들어가 읽지 못한 것일 수 있습니다.
    실측(2026-10-16 시험): SH 청년주택 공고의 임대조건 표(호실별 면적·보증금·월세)가 그림이라 가격 0개로 결과가 나온 것.
    그림만으로는 걸지 않습니다(위치도·평면도가 흔함: 수집 PDF 73개 중 21개). 재확인으로는 못 고치므로(AI도 그림을 못 봄) 바로 사람 확인입니다."""
    groups = candidate["supplyGroups"]
    if not groups:
        return
    missing = candidate.get("quality", {}).get("missingFields") or []
    blank = [m["target"] for m in missing if m.get("reason") == "NOT_IN_SOURCE" and IMAGE_BLANK_FIELD.match(m.get("target", ""))]
    if any(g["prices"] for g in groups) and not blank:
        return
    if any(IMAGE_BLOCK_HEAD in text for text in sources.texts.values()):
        return  # 그림을 판독해 원문에 붙였습니다(빈 칸은 판독 글자에도 없는 것). 판독 근거는 _check_image_evidence가 따로 봅니다
    pages = [f"{document} {number}쪽({share:.0%})" for document, data in sources.pdfs.items() for number, share in image_pages(data)]
    if pages:
        what = "가격이 하나도 없고" if not any(g["prices"] for g in groups) else f"원문에 없다고 한 공급 칸이 {len(blank)}개이고"
        shown = ", ".join(pages[:5])
        find("V8", "SOURCE_IN_IMAGE_SUSPECTED", "/supplyGroups", f"{what} PDF에 글자 없는 큰 그림이 있습니다(그림으로 넣은 표일 수 있음): {shown}")


# 가격표 안 쓴 금액: 가격 근거가 있는 표의 행마다 금액 칸(1,000 이상, 쉼표 표기)이 어느 가격의 원문 금액으로 쓰였는지 봅니다.
# 실측(2026-10-16 sol 정답표 대조): 한 행에 요금안이 둘인 표에서 한 안만 넣음(가격 54/108), 8개 주택형 중 5개만 넣고 EXTRACTED로 보고(30/48)
AMOUNT_CELL = re.compile(r"\d{1,3}(?:,\d{3})+(?:\s*원)?")
AMOUNT_NUMBER = re.compile(r"\d[\d,]*")
SUBTOTAL_ROW = re.compile(r"합\s*계|소\s*계|총\s*계")


def _table_bounds(lines: list[str], index: int) -> tuple[int, int]:
    top = index
    while top > 0 and _in_table(lines[top - 1]):
        top -= 1
    bottom = index
    while bottom + 1 < len(lines) and _in_table(lines[bottom + 1]):
        bottom += 1
    return top, bottom


def _row_amounts(line: str) -> list[str]:
    if SUBTOTAL_ROW.search(line):
        return []
    return [DIGITS.sub("", cell) for cell in _cells(line) if AMOUNT_CELL.fullmatch(cell)]


# 가격이 아닌 금액 열(전환 한도액 등): 표 위 「[열 제목]」 줄의 제목으로 찾습니다
# (실측 2026-10-18 LH 군산내흥7: 「전환가능 보증금 한도액」 3,000·9,000천원이 빠진 가격으로 걸려 공급 묶음이 보류됨)
LIMIT_TITLE = re.compile(r"한도")
COLUMN_TITLE = re.compile(r"(\d+)\.\s*([^|]*)")


def _limit_columns(lines: list[str], top: int) -> set[int]:
    """표 맨 위(열 제목 줄은 표 범위 안에 있음)의 열 제목 줄에서 제목에 「한도」가 든 열 번호(0부터). 열 제목 줄이 없으면 빈 집합."""
    for index in range(max(top - 2, 0), min(top + 3, len(lines))):
        if lines[index].startswith(TITLE_LINE):
            return {int(n) - 1 for n, title in COLUMN_TITLE.findall(lines[index][len(TITLE_LINE) :]) if LIMIT_TITLE.search(title)}
    return set()


NOT_APPLIED = re.compile(r"(?:이번|금회)\s*모집에(?:는|서는)?\s*적용하지\s*않")
WAIVED = re.compile(r"배제|미적용|적용\s*(?:하지\s*않|안\s*함|제외|없음)|불문")


PAGE_MARK = re.compile(r"^\s*(?:---.*---|-\s*\d+\s*-|\[표 [^\]]+\])\s*$")


def _continued_table(lines: list[str], top: int, bottom: int) -> tuple[int, int] | None:
    """표 바로 뒤(쪽 표시·쪽 번호·표 번호 줄만 사이에 둠)에 열 제목 줄 없이 같은 칸 수의 표가 이어지면 그 범위.
    실측(LH 청주지북 공공분양): 분양가 표의 55B~59C 행이 다음 쪽 머리 없는 표로 읽혀 통째로 빠졌는데 어떤 검사에도 걸리지 않음."""
    width = max((len(_cells(lines[i])) for i in range(top, bottom + 1) if _row_line(lines[i])), default=0)
    index, gap = bottom + 1, 0
    while index < len(lines) and gap <= 6 and not _in_table(lines[index]):
        if lines[index].strip() and not PAGE_MARK.match(lines[index]):
            return None
        index, gap = index + 1, gap + 1
    if index >= len(lines) or gap > 6 or not _row_line(lines[index]) or len(_cells(lines[index])) != width:
        return None
    return _table_bounds(lines, index)


NUMBER_IN_LABEL = re.compile(r"\d+(?:\.\d+)?")


def _check_unattached_prices(candidate: dict[str, Any], find: Any) -> None:
    """가격만 있고 수량이 없는 공급 묶음인데, 수량이 있는 다른 묶음과 주택형 번호(정수 부분)가 같으면 가격이 제 묶음에 붙지 못한 것입니다.
    실측(LH 인천석남 「21A 청년(소득有)」, LH 부산당감 「39.70」「39.87」): 가격은 맞게 뽑았지만 모집 수 없는 묶음으로 따로 남음.
    호실 묶음은 같은 호실의 모집 묶음이 따로 있을 때만 봅니다: 이번에 공급하지 않는 호실(입주완료, 공급 규모 줄에 없는 호실)은 모집 수 없이
    자기 가격만 있고, 「202-1호」「202-2호」의 202나 방 종류 「1인실」은 주택형 번호가 아닙니다(2026-11-07 gndc-ddb1·gndc-12394176)."""

    def number(group: dict[str, Any]) -> int | None:
        for text in (group.get("housingTypeCode"), group.get("unitLabel")):
            found = NUMBER_IN_LABEL.search(text or "")
            if found:
                return int(float(found.group()))
        return None

    def unit(group: dict[str, Any]) -> str:
        return normalize(str(group.get("unitLabel") or ""))

    groups = candidate["supplyGroups"]
    counted = {number(g) for g in groups if g["counts"] and g.get("itemKind") != "HOUSING_UNIT"} - {None}
    counted_units = {unit(g) for g in groups if g["counts"] and g.get("itemKind") == "HOUSING_UNIT"} - {""}
    for g, group in enumerate(groups):
        room = group.get("itemKind") == "HOUSING_UNIT"
        same = unit(group) in counted_units if room else number(group) in counted
        if group["prices"] and not group["counts"] and same:
            label = group.get("housingTypeCode") or group.get("unitLabel")
            find("V8", "SUPPLY_PRICE_UNATTACHED", f"/supplyGroups/{g}", f"「{label}」 가격이 같은 주택형의 모집 묶음에 붙지 않고 따로 남았습니다.")


# 특정 대상의 요금표(2026-10-24 채점: 「[주거급여 수급자가 아닌 경우] 상한 임대조건」 표의 가격이 대상 없는 기본 요금으로 그 주택형에 붙음).
# 가격의 근거 행이 든 표 바로 위 글 줄이나 그 값의 열 제목이 적용 대상을 정하는데 가격이 대상 없이 STANDARD면, 기본 요금으로 게시하지 않게
# 그 공급 묶음을 보류합니다(supply_tables.RESTRICTED_PRICE와 같은 낱말. 검증 모듈이 추출 모듈을 가져오지 않도록 따로 둡니다)
PRICE_SCOPE_UNCERTAIN = "PRICE_SCOPE_UNCERTAIN"
RESTRICTED_PRICE = re.compile(r"(?<!분양가)(?<!분양가 )상한(?!\s*제)|수급자|적용\s*대상|해당자에\s*한|에\s*한하여|에\s*한함|만\s*해당|만\s*적용")
PRICE_HEADING_LINES = 3  # 표 위로 볼 글 줄 수(쪽 표시·빈 줄 제외)
# 표 위 글은 요금을 말하고 법령 인용이 아닌 줄만 봅니다(2026-10-24 네 번째 채점: 입지 설명 속 「(산업단지 근로자인 경우에만 해당)」에 걸림)
PRICE_TITLE_WORDS = re.compile(r"임대\s*조건|임대료|요금|보증금|월\s*세|가격|분양가|전환")
LAW_TEXT = re.compile(r"「[^」]*법[^」]*」|제\s*\d+\s*조")


def _price_restriction(found: _Located, price: dict[str, Any]) -> str | None:
    for evidence_id in price.get("evidenceIds") or []:
        located = found.line_of(evidence_id)
        if located is None or not _row_line(found.lines[located[0]][located[1]]):
            continue
        lines = found.lines[located[0]]
        top, _ = _table_bounds(lines, located[1])
        above = [line for line in reversed(lines[max(top - 12, 0) : top]) if line.strip() and not PAGE_MARK.match(line)][:PRICE_HEADING_LINES]
        word = RESTRICTED_PRICE.search(" ".join(line for line in above if PRICE_TITLE_WORDS.search(line) and not LAW_TEXT.search(line)))
        if word:
            return word[0]
        row = found.row(evidence_id)
        column = _value_column(row[0], price.get("sourceAmount")) if row else None
        if row and column is not None and row[1]:
            word = RESTRICTED_PRICE.search(_column_header(row[1], column))
            if word:
                return word[0]
    return None


def _check_price_scope(candidate: dict[str, Any], found: _Located, find: Any) -> None:
    for g, group in enumerate(candidate["supplyGroups"]):
        if (group.get("scope") or {}).get("targetGroups"):
            continue  # 행의 대상 칸에서 대상이 정해진 묶음은 대상 미정이 아닙니다(2026-10-24 네 번째 채점)
        for price in group["prices"]:
            if price.get("priceStage") != "STANDARD" or price["scope"]["targetGroups"]:
                continue
            word = _price_restriction(found, price)
            if word:
                label = group.get("housingTypeCode") or group.get("unitLabel") or group.get("id")
                description = (
                    f"「{label}」 가격 {price.get('sourceAmount')}의 표가 특정 대상의 요금으로 보이는데(「{word}」) 대상 없이 기본 요금으로 적혔습니다. "
                    "원문에서 적용 대상을 확인해야 합니다"
                )
                find("V8", PRICE_SCOPE_UNCERTAIN, f"/supplyGroups/{g}/prices", description)  # 요금 대상만 애매: 가격만 보류
                break


def _check_price_tables(candidate: dict[str, Any], sources: SourceBundle, found: _Located, find: Any) -> None:
    """V8: 가격표로 쓴 표(이어진 표 포함)에서 가격으로 넣지 않은 금액과 어느 공급 묶음에도 없는 금액 행을 찾습니다."""
    used_by: dict[str, set[int]] = {}  # 원문 금액(숫자만) → 그 금액을 쓴 공급 묶음
    for g, group in enumerate(candidate["supplyGroups"]):
        for price in group["prices"]:
            for number in AMOUNT_NUMBER.findall(str(price.get("sourceAmount") or "")):  # 범위(「44,000~51,000」)는 양 끝 금액 모두
                used_by.setdefault(DIGITS.sub("", number), set()).add(g)
    if not used_by:
        return
    row_group: dict[tuple[str, int], int] = {}  # (문서, 줄) → 그 행을 근거로 쓴 공급 묶음
    tables: set[tuple[str, int, int]] = set()
    for g, group in enumerate(candidate["supplyGroups"]):
        for price in group["prices"]:
            for evidence_id in price["evidenceIds"]:
                located = found.line_of(evidence_id)
                if located is None or not _row_line(found.lines[located[0]][located[1]]):
                    continue
                row_group.setdefault(located, g)
                tables.add((located[0], *_table_bounds(found.lines[located[0]], located[1])))
    # 근거로 가리키지 않은 표도, 이미 쓴 금액이 두 행 이상에 있으면 가격표로 봅니다(요금안별로 표가 나뉜 공고: 근거는 한 표만 가리킴)
    for doc in sources.texts:
        if doc not in found.lines:
            continue
        lines, index = found.lines[doc], 0
        while index < len(lines):
            if not _row_line(lines[index]):
                index += 1
                continue
            top, bottom = _table_bounds(lines, index)
            hit_rows = sum(1 for i in range(top, bottom + 1) if any(a in used_by for a in _row_amounts(lines[i])))
            if hit_rows >= 2:
                tables.add((doc, top, bottom))
            index = bottom + 1
    for doc, top, bottom in sorted(tables):  # 가격표가 머리 행 없이 다음 쪽으로 이어진 표도 가격표로 봅니다
        follow = _continued_table(found.lines[doc], top, bottom)
        if follow is not None:
            tables.add((doc, *follow))
    flagged: dict[int, list[str]] = {}
    orphan_rows: list[str] = []
    for doc, top, bottom in sorted(tables):
        lines = found.lines[doc]
        limits = _limit_columns(lines, top)
        owner = None
        for index in range(top, bottom + 1):
            amounts = _row_amounts(lines[index])
            hits = [a for a in amounts if a in used_by]
            # 그 행의 쓴 금액을 모두 가진 묶음(같은 보증금이 여러 단지에 있어도 행 전체로는 하나로 정해짐)
            groups = set.intersection(*(used_by[a] for a in hits)) if hits else set()
            if (doc, index) in row_group:
                owner = row_group[(doc, index)]
            elif len(groups) == 1:
                owner = next(iter(groups))
            elif amounts and owner is not None and _cells(lines[index])[:1] == [""]:
                pass  # 병합 칸으로 앞 행의 주택형을 이어받는 행(계층별 2행 등): 앞 묶음의 행으로 봅니다
            elif amounts:
                owner = None
            # 세대수·증감액 칸 거르기(실측 오탐: 가격 앞 칸의 「1,256」세대, 전환 증감 「-1,100」): 가격으로 쓴 첫 칸보다 왼쪽 칸과
            # 같은 행에서 쓴 가장 작은 금액의 1/100보다 작은 금액은 셈하지 않습니다(월임대료는 보증금의 1/40 안팎이라 남김)
            cells = [DIGITS.sub("", cell) if AMOUNT_CELL.fullmatch(cell) and i not in limits else "" for i, cell in enumerate(_cells(lines[index]))]
            first = min((i for i, cell in enumerate(cells) if cell in used_by), default=0)
            floor = min(int(a) for a in hits) // 100 if hits else 0
            missed = [a for i, a in enumerate(cells) if a and i >= first and a not in used_by and int(a) >= floor] if amounts else []
            if not missed:
                continue
            if owner is not None:
                flagged.setdefault(owner, []).extend(missed)
            elif len(amounts) >= 2 and len(missed) == len(amounts):
                orphan_rows.append(lines[index].strip()[:100])
    for g, missed in flagged.items():
        shown = ", ".join(f"{int(a):,}" for a in missed[:4])
        description = f"근거로 쓴 가격표 행의 금액 {shown}을(를) 가격으로 넣지 않았습니다(다른 요금안·계층일 수 있음)."
        find("V8", "PRICE_VALUES_UNUSED", f"/supplyGroups/{g}", description)
    if orphan_rows:
        find(
            "V8",
            "PRICE_ROWS_UNUSED",
            "/quality/coverage/supplyGroups",
            f"가격표에 금액이 적힌 행 {len(orphan_rows)}개가 어느 공급 묶음에도 없습니다 「{orphan_rows[0]}」",
        )


# ---- V8 서류 표 행 누락 (2026-10-23) ----
# 계층·대상별 서류 표처럼 행이 많은 표를 AI가 중간에서 멈추면(잘림 없이 정상 종료) 나머지 행의 서류가 통째로 빠졌고, 잡는 검사가 없었습니다.
# 서류 표: 머리 행이나 표 바로 위 제목 줄(띄어 쓴 「구 비 서 류」 포함)에 서류 표 낱말이 있는 표, 그리고 쪽 표시만 사이에 두고 이어진 표.
# 행에 서류 낱말이 있는데 어느 서류의 근거 인용·이름도 그 행에 없으면 빠진 행으로 셉니다. 의심이라 화면 메모로 두고(verifier.NOTE_CODES),
# AI 재확인에는 서류 섹션 전체 문제로 보냅니다(recheck.RECHECK_NOTE_CODES).
DOCUMENT_OMISSION = "DOCUMENT_OMISSION_SUSPECTED"
DOCUMENT_TABLE_WORDS = re.compile(r"제출서류|구비서류|증빙서류|신청서류|확인서류|발급처|발급기관")  # 띄어쓰기를 뺀 글에서 찾음
DOCUMENT_HEADING_WORDS = re.compile(r"제출서류|구비서류|증빙서류|신청서류|확인서류")
DOCUMENT_WORD = re.compile(
    r"증명서|확인서|증명원|확인원|등본|초본|사본|신분증|동의서|신청서|위임장|인감|통장|계약서|서약서|확약서|진단서|명세서|요구서|각서|등록증|자격증|수급자증"
)
HEADING_LOOKBACK = 3  # 표 위로 볼 글 줄 수(쪽 표시·빈 줄 제외)
DOCUMENT_OMISSION_MIN_ROWS = 2  # 이만큼 빠져야 알립니다(한 행은 다른 표·글로 넣은 서류일 때가 많음)
ROW_EXCERPT_CHARS = 60  # 빠진 행마다 보여 줄 글자 수
ROW_EXCERPT_LEAD = 25  # 서류 낱말이 뒤에 있으면 그 앞 몇 글자부터 보여 줄지(서류 이름의 앞부분)
OMITTED_ROWS = re.compile(r"(?:서류 표 행|첨부 증빙) (\d+)개")
# 서류 칸 안에 「- 상황 : 서류」로 나열된 첨부 증빙(2026-11-07 23건 대조: 「자산 보유 사실 확인서」 행의 비고 칸 「- 비상장주식 : 증권사 조회내역,
# 주식보관증 …」「- 장기카드대출 : 신용카드사가 발급한 증빙서류」를 V1은 모두 상황마다 서류로 나눴는데, V2 서류 담당은 bmc-71·gh-808에서 상위 서류
# 하나만 넣고 끝냄. 그 행은 상위 서류가 인용해 행 누락으로는 잡히지 않았음). 그 증빙 서류를 이름으로 넣었거나 그 상황을 적용 대상으로 둔 서류가
# 없으면 빠진 서류로 셉니다. 23건 첨부 항목 29개 중 이렇게 걸린 8개는 모두 진짜 누락(V1 0개)
ATTACHMENT_ITEM = re.compile(r"(?:^|\s)[-–]\s*([^:：\-–•]{2,30}?)\s*[:：]\s*(.+?)(?=\s[-–]\s|\s•|$)")
ATTACHMENT_DOCUMENT = re.compile(DOCUMENT_WORD.pattern + r"|내역|증서|증빙|자료|영수증")
SITUATION_SPLIT = re.compile(r"및|/|,|·|또는")
NAME_NOTE = re.compile(r"\([^)]*\)")
# 서류 표의 머리 행(2026-10-24 오탐: 표 위 제목으로 서류 표가 된 표의 「| 구 분 | 계약서류 |」 머리 행을 빠진 서류로 셈).
# 모든 칸이 머리 낱말(구분·서류·발급처·비고 등)뿐인 행은 서류 행이 아닙니다
HEADER_CELL = re.compile(
    r"^(?:구분|항목|순번|번호|비고|대상|내용|유의사항|참고사항|제출대상|발급처|발급기관|발급기준|부수|서류유형|유형|.{0,6}서류|서류.{0,4})$"
)
# 절차 표(「5단계 | 청약신청서 작성」): 단계 이름이 첫 칸인 행이 둘 이상인 표는 서류 표가 아닙니다
STEP_CELL = re.compile(r"^(?:\d{1,2}\s*단계|STEP\s*\d{1,2}|\d{1,2}\s*step)$", re.IGNORECASE)


# 자산·소득 산정 기준 표의 행(2026-10-24 네 번째 채점: 「총 자 산 | 부 동 산 • 사회보장정보시스템에서…」「기타 자산 • 「지방세법」 제104조…」가
# 서류 표에 이어진 표로 읽혀 빠진 서류로 셈 — 4건 모두 재확인 자리 하나를 늘 차지함). 첫 칸이 자산·소득 항목 이름이면 서류 행이 아닙니다
ASSET_CELL = re.compile(r"^(?:총자산|자산|부동산|토지|건축물|자동차|금융자산|일반자산|기타자산|부채|소득|근로소득|사업소득|재산소득|기타소득|연금소득)\S{0,4}$")


def _asset_row(row: str) -> bool:
    first = next((c for c in _cells(row) if c.strip()), "")
    plain = "".join(first.split())
    return bool(ASSET_CELL.match(plain.split("•")[0]))


def _header_row(row: str) -> bool:
    cells = ["".join(c.split()) for c in _cells(row) if c.strip()]
    return bool(cells) and all(HEADER_CELL.match(c) for c in cells)


def _step_row(row: str) -> bool:
    first = next((c for c in _cells(row) if c.strip()), "")
    return bool(STEP_CELL.match(first.strip()))


def omitted_document_rows(description: str) -> int:
    """DOCUMENT_OMISSION_SUSPECTED 설명의 빠진 행·첨부 증빙 수(재확인이 일부만 채웠는지 비교하는 데 씀). 없으면 1."""
    found = OMITTED_ROWS.findall(description or "")
    return sum(map(int, found)) if found else 1


def _document_table_rows(text: str) -> list[str]:
    """원문 서류 표의 행(머리 행 제외)."""
    lines = text.split(SHEET_START, 1)[0].split("\n")
    out: list[str] = []
    previous_end: int | None = None  # 바로 앞 서류 표가 끝난 줄
    i = 0
    while i < len(lines):
        if not (_row_line(lines[i]) and (i == 0 or not _in_table(lines[i - 1]))):
            i += 1
            continue
        start = i
        rows = []
        while i < len(lines) and _in_table(lines[i]):
            if _row_line(lines[i]):
                rows.append(lines[i])
            i += 1
        above = [line for line in reversed(lines[:start]) if line.strip() and not PAGE_MARK.match(line)][:HEADING_LOOKBACK]
        header = bool(rows) and bool(DOCUMENT_TABLE_WORDS.search("".join(rows[0].split())))
        titled = any(DOCUMENT_HEADING_WORDS.search("".join(line.split())) for line in above)
        continued = previous_end is not None and all(not line.strip() or PAGE_MARK.match(line) for line in lines[previous_end:start])
        if (header or titled or continued) and sum(map(_step_row, rows)) < 2:
            out += [row for row in (rows[1:] if header else rows) if not _header_row(row) and not _asset_row(row)]
            previous_end = i
        else:
            previous_end = None
    return out


def _unhandled_attachments(documents: list[dict[str, Any]], rows: list[str]) -> list[str]:
    """서류 표 행의 칸 안에 「- 상황 : 서류」로 나열된 첨부 증빙 가운데, 그 증빙 서류를 이름으로 넣었거나 그 상황을 적용 대상(appliesTo)으로 둔
    서류가 하나도 없는 것."""
    names = [n for n in (normalize(NAME_NOTE.sub("", str(d.get("name") or ""))) for d in documents) if len(n) >= 3]
    applies = [normalize(str(d.get("appliesTo") or "")) for d in documents]
    missed = []
    for row in rows:
        for cell in _cells(row):
            for situation, docs in ATTACHMENT_ITEM.findall(cell):
                if not ATTACHMENT_DOCUMENT.search(docs):
                    continue
                plain = normalize(NAME_NOTE.sub("", docs))
                words = [w for w in (normalize(x) for x in SITUATION_SPLIT.split(NAME_NOTE.sub("", situation))) if len(w) >= 2]
                if any(n in plain for n in names) or any(w in a for w in words for a in applies):
                    continue
                missed.append(f"- {situation.strip()} : {docs.strip()}"[:60])
    return missed


def _row_excerpt(row: str) -> str:
    """빠진 행을 알릴 때 보여 줄 부분(60자): 서류 낱말이 앞 60자 안에 없으면 처음 나오는 곳 조금 앞부터.
    2026-11-08 최종 비교 jbdc-16011: 원문 변환에서 소득세 납부 입증 서류 표(<표9>, 재직증명서 등 서류 8개)가 앞 표의 마지막 칸 하나에 합쳐졌는데,
    행 앞 60자 「※ 직인날인이 없거나 직인 날인된 서류를…」 주의 문구만 보여 V2 서류 담당이 서류 행으로 보지 않고 넘김(앞 실행들은 8개를 넣음)."""
    text = " ".join(c for c in _cells(row) if c)
    found = DOCUMENT_WORD.search(text)
    if found is None or found.end() <= ROW_EXCERPT_CHARS:
        return text[:ROW_EXCERPT_CHARS]
    start = max(found.start() - ROW_EXCERPT_LEAD, 0)
    start = text.rfind(" ", 0, start) + 1 or start  # 낱말 가운데서 시작하지 않게
    return "…" + text[start : start + ROW_EXCERPT_CHARS]


# 원문이 별지 서식으로 이름을 정해 둔 서류(「입주 신청서(별지 1호)」「자기소개서(별지 제3호 서식)」). 표가 아니라 글 속에 있으면 서류 표 행 검사가
# 보지 못함(2026-11-09 23건 sh-311005: 「입주 신청서(별지 1호), 개인 정보 동의서(별지 2호), 자기소개서(별지 3호) 작성 후 …」를 V2 서류 담당이
# 넣지 않음, V1은 넣음). 이름이 서·증·표로 끝나는 것만 봅니다
FORM_NAME = re.compile(r"([가-힣][가-힣A-Za-z0-9·ㆍ ]{0,24}?[서증표])\s*[(\[]\s*별지\s*(?:제\s*)?\d+\s*호(?:\s*서식)?\s*[)\]]")


def _unlisted_forms(documents: list[dict[str, Any]], text: str) -> list[str]:
    """별지 서식으로 든 서류 가운데, 이름이 겹치는(한쪽이 다른 쪽을 품는) 서류가 목록에 없는 것."""
    names = [n for n in (normalize(NAME_NOTE.sub("", str(d.get("name") or ""))) for d in documents) if len(n) >= 2]
    missed = []
    for match in FORM_NAME.finditer(text):
        name = " ".join(match[1].split()[-3:])  # 서식 이름은 길어야 세 낱말: 앞 문장 글(「서류를 작성하여 …」)까지 잡지 않게
        form = normalize(name)
        shown = f"{name}{match[0][len(match[1]) :]}".strip()
        if len(form) >= 3 and not any(form in n or n in form for n in names) and shown not in missed:
            missed.append(shown)
    return missed


# 글 속에서 내라고 한 서류(「신청 시 희망주택목록을 함께 제출」「입주대기 취소 신청서 제출 후 신청 가능」「입주신청확인서제출」). 표·별지 서식이
# 아니라 위 검사들이 보지 못함(2026-11-09 23건 남은 서류 놓침 gbdc-a909·jbdc-15611·sh-310976: V2 서류 담당이 넣지 않음).
# 서류 이름 끝말 바로 뒤의 「제출」만 보고, 「받아서 제출」처럼 동사는 서류가 아닙니다. 「제출하더라도」「제출 전에 …」「제출 후 … 수정 불가」 같은
# 주의 문장, 소명·이의신청 글, 절차 표의 단계 행(「8단계 | 청약신청서 제출」)은 뺍니다. 저장 결과 102개 실행(23건)에서 걸린 것은 실제로 내는 서류뿐.
# 「구비」「지참」도 내라는 말입니다(2026-11-09 jbdc-16011 「2020.12.21. 이후 발급한 여권은 여권정보증명서를 함께 구비해야 인정」을 서류 담당이
# 넣지 않음). 「공동인증서·카카오톡인증서 구비」는 인터넷 청약 로그인용 전자 인증서라 서류가 아님. 저장 결과 1,126개 실행에서 넓혀서 새로 걸린 것은
# 이 셋뿐(인증서 둘은 뺌)
SUBMITTED = re.compile(
    r"([가-힣A-Za-z0-9·ㆍ]+(?:서|목록|명단|사본|등본|초본))\s*(?:을|를)?\s*(?:함께\s*|반드시\s*|별도로\s*|추가로\s*|각각\s*)?(?:제출|구비|지참)"
    r"(?!\s*(?:하더라도|하지\s*않|할\s*필요|불필요|않아도|여부|전))"
)
SUBMITTED_VERB = re.compile(r"(?:아|어|해|여|와|워|라|려|에|로|면|져|쳐|켜)서$")  # 「받아서」「작성하여서」
SUBMITTED_GENERIC = re.compile(r"^(?:서류|관련서류|구비서류|제출서류|증빙서류|서류일체|각종서류|증명서류|확인서류|첨부서류|신청서류|.*인증서)$")
SENTENCE_END = re.compile(r"\n|다\.|\.\s")
SUBMITTED_CAUTION = re.compile(r"^\s*후\S{0,3}\s.*?(?:수정|취소|변경|삭제|불가)|소명|이의\s*신청")  # 「제출 후 … 수정 불가」, 소명 절차
# 이름이 짧으면(「신청서」「동의서」) 앞 낱말까지 이름으로 봅니다(「입주대기 취소 신청서」). 조사로 끝나거나 가리키는 말(「이 동의서」)은 이름이 아님
SUBMITTED_SHORT = 3
LEAD_PARTICLE = re.compile(r"(?:의|에|를|을|가|는|은|와|과|로|도|만|고|며|면|서|여|해|한|된|른|던|할|운|및|등)$")
LEAD_POINTER = {"그", "저", "동", "각", "해당", "위", "아래", "본", "추후", "다음", "기타"}


def _submitted_name(text: str, match: re.Match[str]) -> str | None:
    name = match[1].strip("()")
    if SUBMITTED_VERB.search(name) or SUBMITTED_GENERIC.match(name):
        return None
    if len(name) <= SUBMITTED_SHORT:
        lead: list[str] = []
        for word in reversed(text[max(0, match.start(1) - 40) : match.start(1)].split()[-2:]):
            if len(word) < 2 or word in LEAD_POINTER or LEAD_PARTICLE.search(word) or not re.fullmatch(r"[가-힣A-Za-z0-9·ㆍ]+", word):
                break
            lead.insert(0, word)
        name = " ".join([*lead, name])
    return name


def _unlisted_submissions(documents: list[dict[str, Any]], text: str) -> list[str]:
    """글 속에서 내라고 한 서류 가운데, 이름이 겹치는(한쪽이 다른 쪽을 품는) 서류가 목록에 없는 것."""
    names = [n for n in (normalize(NAME_NOTE.sub("", str(d.get("name") or ""))) for d in documents) if len(n) >= 2]
    found: list[str] = []
    for match in SUBMITTED.finditer(text):
        end = text.find("\n", match.end())
        line = text[text.rfind("\n", 0, match.start()) + 1 : end if end >= 0 else len(text)]
        rest = SENTENCE_END.split(text[match.end() : match.end() + 80], maxsplit=1)[0]  # 그 문장 끝까지(다음 줄의 「신청불가」는 보지 않음)
        if (_row_line(line) and _step_row(line)) or SUBMITTED_CAUTION.search(rest):
            continue
        name = _submitted_name(text, match)
        form = normalize(name or "")
        if len(form) >= 3 and not any(form in n or n in form for n in names) and name not in found:
            found.append(name)
    # 「신청서」와 「입주신청서」가 함께 걸리면 긴 이름만
    return [name for name in found if not any(normalize(name) in normalize(other) and name != other for other in found)]


# 서류 이름이 여럿 든 서류 표 행(앞 표 칸에 합쳐진 다음 표 포함)을 묶음 서류 하나(「소득세납부 입증서류 (아래 <표9> 참고)」)가 인용하면 행은 인용된
# 것으로 보여 그 안의 서류가 빠져도 안 잡혔음(2026-11-09 유료 측정 jbdc-16011: <표9>의 재직증명서·건강보험자격득실확인서 등 서류 8개가 빠짐).
# 서류 이름이 MULTI_NAMES개 이상 든 행(표 하나가 통째로 든 행)에서 이름 MISSING_NAMES개 이상이 서류 목록에 없을 때만 봅니다. 목록 이름은
# 괄호 속 예시까지 봅니다(「본인 신분증(주민등록증, 운전면허증 …)」). 저장 결과 892개 실행: 이 경계에서 걸린 것은 <표9>를 놓친 jbdc-16011
# 실행(이름 10개 중 10개 빠짐)뿐이고, 경계를 낮추면 「주민등록등본」(목록은 「주민등록표등본」)·「임신확인서」 같은 다른 이름·예시가 수백 번 걸림
ROW_DOCUMENT_NAME = re.compile(
    r"[가-힣A-Za-z0-9]{2,20}?(?:증명서|확인서|증명원|확인원|등본|초본|신분증|동의서|신청서|위임장|명세서|영수증|각서|서약서|확약서|진단서|등록증)"
)
MULTI_NAMES = 6
MISSING_NAMES = 4


def _unlisted_row_names(documents: list[dict[str, Any]], rows: list[str]) -> list[str]:
    names = [n for n in (normalize(str(d.get("name") or "")) for d in documents) if len(n) >= 3]
    missed: list[str] = []
    for row in rows:
        found = list(dict.fromkeys(match[0] for match in ROW_DOCUMENT_NAME.finditer(row)))
        if len(found) < MULTI_NAMES:
            continue
        absent = [name for name in found if len(normalize(name)) >= 4 and not any(normalize(name) in n or n in normalize(name) for n in names)]
        if len(absent) >= MISSING_NAMES:
            missed += [name for name in absent if name not in missed]
    return missed


def _check_document_rows(candidate: dict[str, Any], sources: SourceBundle, find) -> None:
    documents = candidate.get("requiredDocuments") or []
    if not documents:
        return  # 서류가 하나도 없으면 섹션 누락 검사(SECTION_OMISSION_SUSPECTED)가 봅니다
    quotes = {ev["id"]: normalize(ev["quote"]) for ev in candidate.get("evidence") or []}
    cited = [quotes[i] for d in documents for i in d.get("evidenceIds") or [] if len(quotes.get(i, "")) >= 4]
    names = [n for n in (normalize(str(d.get("name") or "")) for d in documents) if len(n) >= 2]
    rows = _document_table_rows("\n".join(sources.texts.values()))
    missed = []
    for row in rows:
        if not DOCUMENT_WORD.search(row):
            continue
        plain = normalize(row)
        if any(q in plain or plain in q for q in cited) or any(n in plain for n in names):
            continue
        missed.append(_row_excerpt(row))
    parts = []
    forms = _unlisted_forms(documents, "\n".join(sources.texts.values()))
    if forms:  # 별지 서식은 원문이 이름으로 정해 둔 서류라 하나만 빠져도 알립니다
        parts.append(f"원문이 별지 서식으로 든 서류 {len(forms)}개가 서류 목록에 없습니다: {', '.join(f'「{form}」' for form in forms[:3])}")
    submitted = [name for name in _unlisted_submissions(documents, "\n".join(sources.texts.values())) if name not in " ".join(forms)]
    if submitted:  # 글로 내라고 한 서류도 원문이 이름을 적은 서류라 하나만 빠져도 알립니다
        shown = ", ".join(f"「{name}」" for name in submitted[:3])
        parts.append(f"원문 글에서 내라고 한 서류 {len(submitted)}개가 서류 목록에 없습니다: {shown}{' …' if len(submitted) > 3 else ''}")
    listed = _unlisted_row_names(documents, rows)
    if listed:
        shown = ", ".join(f"「{name}」" for name in listed[:4])
        parts.append(
            f"서류 이름이 여럿 든 표 행의 서류 {len(listed)}개가 서류 목록에 없습니다(묶음 서류 하나로 인용하지 않고 이름마다 넣음): "
            f"{shown}{' …' if len(listed) > 4 else ''}"
        )
    attachments = _unhandled_attachments(documents, rows)
    if attachments:  # 행 누락보다 먼저 적습니다(V2 담당에게 가는 설명은 앞부분만 감)
        shown = ", ".join(f"「{item}」" for item in attachments[:2])
        parts.append(
            f"서류 칸에 나열된 첨부 증빙 {len(attachments)}개를 다룬 서류가 없습니다(상황마다 증빙 서류로): {shown}{' …' if len(attachments) > 2 else ''}"
        )
    if len(missed) >= DOCUMENT_OMISSION_MIN_ROWS:
        shown = ", ".join(f"「{row}」" for row in missed[:3])
        parts.append(f"원문 서류 표 행 {len(missed)}개를 근거로 쓴 서류가 없습니다(빠진 서류 의심): {shown}{' …' if len(missed) > 3 else ''}")
    if parts:
        find("V8", DOCUMENT_OMISSION, "/quality/coverage/requiredDocuments", " ".join(parts))


# ---- V8 일정 누락 (2026-11-09) ----
# 일정 단계 낱말 바로 뒤에 날짜가 적힌 글(「나. 계약체결: 2027. 1. 20.(수) ~ …」「라. 입주기간: 2027. 2~4월 중」)인데 그 날짜로 시작하거나 끝나는
# 일정이 없으면 빠진 일정 의심입니다. 2026-11-09 23건: V2 일정 담당이 sh-311087의 번호 붙은 글 줄로 적힌 계약체결·입주기간을 넣지 않음(V1은 넣음).
# 빠진 값이지 틀린 값이 아니라 메모로 두고(verifier.NOTE_CODES), V2 일정 담당에게는 「확인할 것」으로 알립니다.
# 임대차 계약기간은 단계가 아니라 빼고, 날짜 바로 뒤가 「기준·현재·이전·당시」면 기준일이라 뺍니다. 「입주자·입주민」은 사람이고, 공고일보다
# 한 달 넘게 앞선 날짜는 이번 모집의 단계가 아닙니다(같은 날 저장 결과: 단지 표의 「입주월 … 2012. 8.」, 「입주자격 … 임대개시일(2022년 9월)」)
SCHEDULE_OMISSION = "SCHEDULE_OMISSION_SUSPECTED"
SCHEDULE_STEP = re.compile(
    r"계약\s*체결|계약(?!\s*(?:기간|금\s*반환))|입주(?!\s*(?:자|민))\s*(?:기간|지정|예정|시기|가능)?|발표|통보|접수|서류\s*제출|제출|열람|공개|조사|심사|소명|교육|추첨|게시"
)
SCHEDULE_DATE = re.compile(r"(?<!\d)(20\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})(?:\s*(?:[.\-/]|월)\s*(\d{1,2})(?!\d))?")
STEP_TO_DATE_CHARS = 20  # 단계 낱말 끝에서 날짜 시작까지(「계약체결: 2027. 1. 20.」「입주기간 : 2027. 2~4월」)
REFERENCE_DATE = re.compile(r"^\D{0,4}(?:기준|현재|이전|당시)")
SCHEDULE_EXCERPT_CHARS = 50
STEP_BEFORE_NOTICE_DAYS = 31
# 연도 없이 적은 날짜(「서류심사 (7.10. ~ 7.14.)」): 일 뒤에 마침표가 있거나 요일 괄호·물결표가 오는 「월.일」만(면적 「36.29㎡」·배수 「2.5배」는 아님).
# 공고일의 연도로 보고, 공고일보다 한 달 넘게 앞서면 다음 해로 봅니다(2026-11-09 23건 gndc-1239 서류심사를 V1·V2 모두 넣지 않음)
YEARLESS_DATE = re.compile(r"(?<![\d.])(\d{1,2})\s*[./]\s*(\d{1,2})(?:\s*\.(?!\d)|(?=\s*[(~∼〜]))")
# 순서도·표가 글로 풀린 일정: 단계 낱말이 둘 이상인 머리 줄 아래(빈 줄 빼고 이만큼 안)에 날짜만 이어 적은 줄(2026-11-09 23건 umca-4439:
# 「입주자격 조사 소명 심사 확정명단 발표」 다음 「2026. 7. 10. 2026. 7. 22. ~ 24. 2026. 7. 27. ~ 2026. 8. ~ 2026. 9.」의 조사·소명 단계를 V2가 넣지 않음)
TIMELINE_LOOKBACK = 4
# 날짜만 적은 줄에 남아도 되는 말(요일·시각·「예정」「이후」「말」 등). 날짜·숫자·기호를 지운 뒤 이 말을 빼고 남은 글자가 이만큼 이하면 날짜 줄입니다
TIMELINE_FILLER = re.compile(r"[월화수목금토일]|예정|이후|부터|까지|경|말|초|중|순")
TIMELINE_REST_CHARS = 2


def _schedule_dates(candidate: dict[str, Any]) -> set[str]:
    """추출 일정의 시작·끝 날짜(「2027-01-20」「2027-02」)와 공고일."""
    found = {str((candidate.get("notice") or {}).get("announcedOn") or "")}
    for schedule in candidate.get("schedules") or []:
        for key in ("startsAt", "endsAt"):
            found.add(str((schedule.get(key) or {}).get("value") or "")[:10])
    return {value for value in found if value}


def _first_day(value: str) -> date | None:
    """「2026-10-08」「2026-10」(월 정밀도는 그달 1일)을 날짜로. 읽지 못하면 None."""
    try:
        return date.fromisoformat(value if len(value) == 10 else f"{value[:7]}-01")
    except ValueError:
        return None


def _notice_day(candidate: dict[str, Any], known: set[str]) -> date | None:
    """공고일: 공고 정보의 공고일, 없으면 공고(ANNOUNCEMENT) 일정의 시작, 그것도 없으면 가장 이른 일정 날짜."""
    announced = _first_day(str((candidate.get("notice") or {}).get("announcedOn") or ""))
    if announced:
        return announced
    for schedule in candidate.get("schedules") or []:
        if "ANNOUNCEMENT" in (schedule.get("kinds") or []):
            start = _first_day(str((schedule.get("startsAt") or {}).get("value") or "")[:10])
            if start:
                return start
    days = [day for day in map(_first_day, known) if day]
    return min(days) if days else None


def _date_only(line: str, dates: list[re.Match[str]]) -> bool:
    """날짜만 이어 적은 줄인지(풀린 순서도의 날짜 줄): 날짜를 지우고 숫자·기호·요일·「예정」 같은 말을 빼면 거의 남지 않습니다."""
    rest = line
    for match in reversed(dates):
        rest = rest[: match.start()] + rest[match.end() :]
    rest = TIMELINE_FILLER.sub("", re.sub(r"[\d\s.,~∼〜()\[\]:/|\-]", "", rest))
    return len(rest) <= TIMELINE_REST_CHARS


def _check_schedule_rows(candidate: dict[str, Any], sources: SourceBundle, find) -> None:
    if not candidate.get("schedules"):
        return  # 일정이 하나도 없으면 섹션 누락 검사가 봅니다
    known = _schedule_dates(candidate)
    notice_day = _notice_day(candidate, known)
    missed: list[str] = []
    flagged: set[str] = set()  # 알린 날짜(같은 날짜를 여러 규칙이 보더라도 한 번만)

    def excerpt(line: str, start: int, end: int) -> str:
        start = max(line.rfind(" ", 0, start), line.rfind("|", 0, start)) + 1  # 단계 낱말이 든 낱말 처음부터(「서류심사」)
        return " ".join(line[start:end].split())[:SCHEDULE_EXCERPT_CHARS]

    def check(year: int, month: int, day: int | None, shown: str) -> None:
        if not 1 <= month <= 12 or (day is not None and not 1 <= day <= 31):
            return
        wanted = f"{year:04d}-{month:02d}" + (f"-{day:02d}" if day else "")
        if wanted in flagged or any(value.startswith(wanted) for value in known):
            return
        when = _first_day(wanted)
        if notice_day and when and (notice_day - when).days > STEP_BEFORE_NOTICE_DAYS:
            return
        flagged.add(wanted)
        missed.append(shown)

    lines = "\n".join(sources.texts.values()).split("\n")
    for line in lines:
        dated = [m.span() for m in SCHEDULE_DATE.finditer(line)]
        for step in SCHEDULE_STEP.finditer(line):
            date_match = SCHEDULE_DATE.search(line, step.end(), step.end() + STEP_TO_DATE_CHARS + 12)
            if date_match is None or date_match.start() - step.end() > STEP_TO_DATE_CHARS:
                short = YEARLESS_DATE.search(line, step.end(), step.end() + STEP_TO_DATE_CHARS + 8)
                if notice_day is None or short is None or short.start() - step.end() > STEP_TO_DATE_CHARS or any(a <= short.start() < b for a, b in dated):
                    continue
                month, day = int(short[1]), int(short[2])
                year = notice_day.year
                if 1 <= month <= 12 and (notice_day - date(year, month, 1)).days > STEP_BEFORE_NOTICE_DAYS:
                    year += 1  # 12월 공고의 「1.5.」는 다음 해
                check(year, month, day, excerpt(line, step.start(), short.end() + 8))
                continue
            if REFERENCE_DATE.search(line[date_match.end() :]):
                continue
            shown = excerpt(line, step.start(), date_match.end() + 8)
            check(int(date_match[1]), int(date_match[2]), int(date_match[3]) if date_match[3] else None, shown)
    # 일정 표: 단계 낱말이 든 칸이 둘 이상이고 날짜는 없는 머리 행 바로 아래 행의 날짜(2026-11-09 유료 확인 gh-809: 「| 신청접수 | | 적격여부 검수 |
    # | 당첨자 발표 | | 계약체결 |」 아래 「2026.07.27(월) ~ 2026.08.17(월)」을 V2가 넣지 않음. 그 행에 다른 글도 있어 날짜 줄 규칙은 못 봄).
    # 칸 이름을 보여 줄 수 있어 날짜 줄 규칙보다 먼저 봅니다
    for index, line in enumerate(lines):
        if not _row_line(line) or SCHEDULE_DATE.search(line):
            continue
        heads = _cells(line)
        if sum(1 for cell in heads if SCHEDULE_STEP.search(cell)) < 2:
            continue
        row = next((text for text in lines[index + 1 : index + 3] if _row_line(text)), None)
        for column, cell in enumerate(_cells(row) if row else []):
            head = heads[column] if column < len(heads) and heads[column] else " ".join(line.split())[:30]
            for match in SCHEDULE_DATE.finditer(cell):
                check(int(match[1]), int(match[2]), int(match[3]) if match[3] else None, f"{head} … {' '.join(match[0].split())}")
    for index, line in enumerate(lines):
        dates = list(SCHEDULE_DATE.finditer(line))
        if len(dates) < 2 or not _date_only(line, dates):
            continue
        above = []  # 바로 위 글 줄들(가까운 줄부터, 빈 줄 빼고)
        for text in reversed(lines[:index]):
            if len(above) == TIMELINE_LOOKBACK:
                break
            if text.strip():
                above.append(text)
        header = next((text for text in above if len(SCHEDULE_STEP.findall(text)) >= 2 and not SCHEDULE_DATE.search(text)), None)
        if header is None:
            continue
        head = " ".join(header.split())[:30]
        for match in dates:
            check(int(match[1]), int(match[2]), int(match[3]) if match[3] else None, f"{head} … {' '.join(match[0].split())}")
    if missed:
        shown = ", ".join(f"「{item}」" for item in missed[:3])
        find(
            "V8",
            SCHEDULE_OMISSION,
            "/quality/coverage/schedules",
            f"원문에 날짜가 적힌 단계 {len(missed)}개가 일정에 없습니다(빠진 일정 의심): {shown}{' …' if len(missed) > 3 else ''}",
        )


# ---- V8 자격 기준표 행 누락 (2026-11-07) ----
# 23건 원인 분석: 계층×가구원 수×출생자녀 수 가산 소득·자산 기준표(dudc-8934·dcco-24804), 공급유형×공급방식×맞벌이 여부 소득표(jbdc-16011)의
# 행 일부를 자격 조건으로 옮기지 않았는데 잡는 검사가 없었음(V1·V2가 함께 놓친 자격 값 40개). 기준표 행의 기준값(소득 %·자산 금액)을
# 어느 자격 조건·예외·선정 조건식도 쓰지 않으면 빠진 행으로 셉니다.
# 기준표: 소득 % 칸(칸이나 열 제목에 「소득」)이나 자산 금액 칸(열 제목 마지막 단계에 자산·자동차)이 두 행 이상이고, 대상 칸(계층·공급유형·
# 가구원 수·자녀 수)이 행마다 바뀌는 표. 단계별 참고 소득표(「80% | 3,050,690 | …」)는 대상 칸이 하나뿐이라 빠지고, 임대조건·할증·배점·
# 신청서·일정 표는 낱말로 뺍니다. 글로만 남긴 조건의 원문에 있는 값은 다룬 것으로 칩니다(조건식 없음은 CRITERION_NOT_STRUCTURED가 봄).
# 행의 대상(계층·공급유형)을 조건 대상 이름과 맞춘 표는 그 대상 조건의 값으로만 셉니다(_row_owners). 23건 저장 결과에서 걸린 공고는
# V1 bmc-106·dcco-24804·dudc-8934·jbdc-16011, V2 dcco-24804·dudc-8934·jbdc-16011(+ 다시 산 초안의 bmc-72·jbdc)이고 모두 실제 누락
# (잘못 잡은 것 없음). 빠진 값이지 틀린 값이 아니라 서류 표 행 누락처럼 화면 메모로 두고(verifier.NOTE_CODES),
# V2 자격 담당에게는 「확인할 것」으로 알립니다
CRITERIA_OMISSION = "CRITERIA_TABLE_OMISSION_SUSPECTED"
# 기준표 행이 하나도 조건에 없는 대상(공급유형·계층이 통째로 빠짐). 행 일부가 빠진 것과 따로 알려 V2 자격 담당에게 「고칠 것」으로 보냅니다
# (2026-11-07 유료 확인 jbdc-16011: 「일반 공급, 노부모 부양 특별 공급」을 「확인할 것」 18개 속 메모로 받고 「이미 한 차례 고친 경고」로 넘김)
CRITERIA_GROUP_OMISSION = "CRITERIA_GROUP_OMISSION_SUSPECTED"
CRITERIA_OMISSION_MIN_ROWS = 2  # 이만큼 빠져야 알립니다(서류 표 행 누락과 같음)
CRITERIA_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|퍼센트)")
INCOME_WORD = re.compile(r"소\s*득")
ASSET_WORD = re.compile(r"자\s*산|자\s*동\s*차|차\s*량|부\s*동\s*산")
LETTER = re.compile(r"[가-힣A-Za-z]")
# 기준표가 아닌 표: 임대조건·전환·할증(재계약) 표, 배점표, 공급신청서 양식. 열 제목·첫 행들·표 위 세 줄에서 찾습니다.
# 「공급 가」로 줄이면 「특별공급 가점항목」에 걸리므로 공급가격·공급가액만 씁니다
NOT_CRITERIA_TABLE = re.compile(
    r"보증금|임대료|월\s*세|분양\s*가|계약금|잔금|중도금|전환|관리비|임대\s*조건|공급\s*가[격액]|신청서|접수\s*번호|서식|양식|배\s*점|점\s*수|가\s*점|재계약|갱신|할증"
)
# 일정 표(접수 시각·요일). 「’23년 3월 28일 이후 출생」 같은 자격 문구의 날짜, 「기준 중위소득 (월)」의 월은 일정이 아닙니다
SCHEDULE_CELL = re.compile(r"\d{1,2}\s*:\s*\d{2}|\d\s*\.?\s*\((?:월|화|수|목|금|토|일)\)")
CRITERIA_CAPTION_LINES = 3
# 기준값 칸의 최대 길이. 문단을 통째로 담은 칸(bmc-71 「소득 | 2024년도 … 70% 80% 90% … 1인 20%, 2인 10%」)의 비율은 기준표 값이 아닙니다.
# 가장 긴 기준값 칸은 「도시근로자 가구원수별 가구당 월평균소득액의 140% (본인 및 배우자가 모두 소득이 있는 경우)」(jbdc-16011) 정도
CRITERIA_CELL_CHARS = 80
# 금액 칸에 단위가 없으면 열 제목의 단위(「적용 자산기준금액(원) › 총자산가액 | 237,000,000」, bmc-72)로 읽습니다
TITLE_UNIT = re.compile(r"\(\s*(천원|만원|원)\s*\)")
# 행의 대상(계층·공급유형)과 조건 대상 이름 맞추기(2026-11-07 유료 확인 jbdc-16011: 소득표 32행 중 일반공급·노부모부양 등 16값이 조건에 없는데
# 같은 비율을 다른 공급이 써서 값만으로는 다룬 것으로 셈). 가구원 수·자녀 수·맞벌이 표시 칸은 대상이 아님
CONDITION_CELL = re.compile(r"^(?:\d+\s*(?:인|명)(?:\s*(?:이상|이하|초과|미만))?|[○●×xXoO\-–]|해당\s*없음)$")
LIST_MARK = re.compile(r"(?:^|\s)(?:[가-하]\.|\d+\)|[①-⑳])\s*")
LETTER_MARK = re.compile(r"(?:^|\s)([가-하])\.\s")  # 표 대상의 목록 기호(「차. 일반입주자」) ↔ 조건 대상의 목(「2순위 차목」)
NAME_SPLIT = re.compile(r"[·ㆍ‧・･∙,/+]|\s및\s|\s또는\s")
PARENTHESES = re.compile(r"\([^)]*\)|\[[^\]]*\]")
AMOUNT_NAME = re.compile(r"[\d,.%]+(?:만원|원)?(?:이하|이상|미만|초과)?")  # 대상 칸 자리에 든 금액(「4,576,036원 이하」)은 이름이 아님


def _criteria_titles(block: list[str]) -> list[str]:
    """표의 열 제목: 구조 방식이면 열 제목 줄, 아니면 기준값 칸이 나오기 전 머리글 행들을 열마다 이은 것."""
    title = next((line for line in block if line.startswith(TITLE_LINE)), None)
    if title:
        return [TITLE_NUMBER.sub("", cell) for cell in _cells(title[len(TITLE_LINE) :])]
    headers = []
    for line in [line for line in block if _row_line(line)][:3]:
        cells = _cells(line)
        if any(NUMERIC_CELL.fullmatch(cell) or CRITERIA_PERCENT.search(cell) for cell in cells):
            break
        headers.append(cells)
    return [_column_header(headers, c) for c in range(max(map(len, headers), default=0))]


def _criteria_values(cells: list[str], titles: list[str]) -> list[tuple[str, float, str]]:
    """행의 기준값 (PERCENT·KRW, 값, 원문 표기): 소득 %는 칸이나 열 제목에 「소득」이 있을 때(「○○% 초과」 구간 칸 제외),
    자산 금액은 열 제목 마지막 단계(「최종 소득 · 자산기준 › 적용 자산기준 › 총자산가액」의 「총자산가액」)에 자산·자동차가 있을 때."""
    found = []
    for c, cell in enumerate(cells):
        if len(cell) > CRITERIA_CELL_CHARS:
            continue
        title = titles[c] if c < len(titles) else ""
        leaf = title.split("›")[-1]
        leaf = leaf if INCOME_WORD.search(leaf) or ASSET_WORD.search(leaf) else title
        if CRITERIA_PERCENT.search(cell) and (INCOME_WORD.search(cell) or INCOME_WORD.search(title)) and "초과" not in cell:
            found += [("PERCENT", float(m[1]), m[0]) for m in CRITERIA_PERCENT.finditer(cell)]
        elif ASSET_WORD.search(leaf) and not INCOME_WORD.search(leaf):
            unit = TITLE_UNIT.search(title)
            amounts = [(m[0], None) for m in AMOUNT.finditer(cell)] or [(m[0], unit[1]) for m in AMOUNT_CELL.finditer(cell) if unit]
            for raw, scale in amounts:
                krw = to_krw(re.sub(r"\s", "", raw), scale).amount_krw
                if krw:
                    found.append(("KRW", float(krw), raw))
    return found


def _varies(labels: list[list[str]]) -> bool:
    """대상 칸 가운데 행마다 값이 바뀌는 열이 있는지. 병합 칸은 빈칸으로 읽히므로 위 행 값을 이어받습니다."""
    for c in range(max(map(len, labels), default=0)):
        seen, last = set(), ""
        for row in labels:
            last = (row[c] if c < len(row) else "") or last
            if last:
                seen.add(last)
        if len(seen) >= 2:
            return True
    return False


def _criteria_tables(text: str) -> list[list[tuple[str, list[tuple[str, float, str]], str | None]]]:
    """원문 자격 기준표마다 행 → (보여 줄 행 글, 기준값들, 행의 대상). 행 글은 병합 칸을 채운 읽기 도움 줄(↳)이 있으면 그것을 씁니다.
    행의 대상은 기준값이 아닌 글자 칸 가운데 가구원 수·자녀 수·맞벌이 표시가 아닌 첫 칸(병합 칸은 위 행 것을 이어받음)."""
    lines = text.split(SHEET_START, 1)[0].split("\n")
    found = []
    i = 0
    while i < len(lines):
        if not _in_table(lines[i]) or (i > 0 and _in_table(lines[i - 1])):
            i += 1
            continue
        start = i
        while i < len(lines) and _in_table(lines[i]):
            i += 1
        block = lines[start:i]
        rows = [n for n, line in enumerate(block) if _row_line(line)]
        if any(SCHEDULE_CELL.search(block[n]) for n in rows):
            continue
        titles = _criteria_titles(block)
        above: list[str] = []  # 표 위 글 줄(바로 위가 다른 표면 그 표의 행은 넣지 않음)
        for line in reversed(lines[:start]):
            if _in_table(line) or len(above) == CRITERIA_CAPTION_LINES:
                break
            if line.strip() and not PAGE_MARK.match(line):
                above.append(line)
        if NOT_CRITERIA_TABLE.search(" ".join([*titles, *block[:3], *above])):
            continue
        data, labels, carry = [], [], []
        for n in rows:
            cells = _cells(block[n])
            values = _criteria_values(cells, titles)
            if not values:
                continue
            aid = block[n + 1][len(AID_LINE) :] if n + 1 < len(block) and block[n + 1].startswith(AID_LINE) else None
            label = [cell if LETTER.search(cell) and not any(raw in cell for _, _, raw in values) else "" for cell in cells]
            carry = carry + [""] * (len(cells) - len(carry))
            for c, cell in enumerate(label):
                if cell:  # 글자 칸이 바뀌면 그 오른쪽의 이어받은 칸은 끊음
                    carry[c] = cell
                    carry[c + 1 :] = [""] * (len(carry) - c - 1)
            group = next((cell for cell in carry[: len(cells)] if cell and not CONDITION_CELL.match(cell)), None)
            data.append((aid or " ".join(cell for cell in cells if cell), values, group))
            labels.append(label)
        if len(data) >= 2 and _varies(labels):
            found.append(data)
    return found


def _criteria_rows(text: str) -> list[tuple[str, list[tuple[str, float, str]]]]:
    """원문 자격 기준표의 행 → (보여 줄 행 글, 기준값들)."""
    return [(shown, values) for table in _criteria_tables(text) for shown, values, _ in table]


def _name_parts(name: str) -> list[str]:
    """대상 이름 → 맞춰 볼 부분: 괄호를 빼고 목록 기호(「나.」「1)」)·「·」「,」로 나눈 뒤 공백을 뺀 2글자 이상(숫자·금액 칸은 뺌)."""
    parts = []
    for piece in LIST_MARK.split(PARENTHESES.sub(" ", name)):
        for part in NAME_SPLIT.split(piece):
            plain = normalize(part)
            if len(plain) >= 2 and not AMOUNT_NAME.fullmatch(plain):
                parts.append(plain)
    return parts


def _row_owners(groups: list[str], named: list[tuple[dict[str, Any], list[str]]]) -> dict[str, list[dict[str, Any]]] | None:
    """표의 대상 → 그 대상의 자격 조건. 조건 대상 이름의 부분마다, 서로 포함되거나 목록 기호가 같은(표 「차.」 ↔ 조건 「차목」) 표 대상에 붙이고,
    여럿이면 이름에서 먼저 나오는 대상에 붙입니다(「신혼부부 특별공급 일반공급」은 일반공급이 아니라 신혼부부). 표에서 맞춰진 이름이 하나뿐이면
    맞추지 못한 대상도 그 이름의 조건으로 봅니다(청년 표의 「세대원(본인)」 행). 어느 대상도 맞추지 못하면 None(값만 대조)."""
    parts = {group: _name_parts(group) for group in groups}
    marks = {group: set(LETTER_MARK.findall(f" {group}")) for group in groups}
    by_part: dict[str, list[dict[str, Any]]] = {}
    for item, names in named:
        for part in dict.fromkeys(names):
            by_part.setdefault(part, []).append(item)
    owners: dict[str, list[dict[str, Any]]] = {group: [] for group in groups}
    matched: set[str] = set()
    for part, items in by_part.items():
        best: list[str] = []
        at = None
        for group in groups:
            hits = [part.find(q) for q in parts[group] if q in part] + [0 for q in parts[group] if part in q]
            hits += [part.find(f"{mark}목") for mark in marks[group] if f"{mark}목" in part]
            if not hits:
                continue
            if at is None or min(hits) < at:
                best, at = [group], min(hits)
            elif min(hits) == at:
                best.append(group)
        for group in best:
            owners[group] += items
            matched.add(part)
    if not matched:
        return None
    if len(matched) == 1:
        only = by_part[next(iter(matched))]
        owners = {group: items or list(only) for group, items in owners.items()}
    return owners


def _used_criteria(candidate: dict[str, Any]) -> tuple[set[float], set[float]]:
    """(비율, 금액): 자격 조건·예외(발동 조건·바뀐 기준)·선정 조건식의 값과, 글로만 남긴 자격 조건 원문에 적힌 소득 %·금액."""
    percents: set[float] = set()
    amounts: set[float] = set()
    expressions = [(rule.get("rule") or {}).get("expression") for rule in candidate["selectionRules"]]
    for item in candidate["eligibility"]:
        expressions.append(item["rule"].get("expression"))
        for exception in item.get("exceptions") or []:
            expressions += [(exception.get("when") or {}).get("expression"), exception.get("effectExpression")]
        if item["rule"].get("status") != "STRUCTURED":
            text = item.get("originalText") or ""
            percents |= {float(m[1]) for m in CRITERIA_PERCENT.finditer(text)}
            amounts |= {float(krw) for krw in (to_krw(re.sub(r"\s", "", m[0]), None).amount_krw for m in AMOUNT.finditer(text)) if krw}
    for expression in expressions:
        for _, atom in _atoms(expression, ""):
            values = atom.get("value") if isinstance(atom.get("value"), list) else [atom.get("value")]
            for value in values:
                if isinstance(value, int | float) and not isinstance(value, bool):
                    if atom.get("unit") == "PERCENT":
                        percents.add(float(value))
                    elif atom.get("unit") == "KRW":
                        amounts.add(float(value))
    return percents, amounts


def _check_criteria_rows(candidate: dict[str, Any], sources: SourceBundle, find: Any) -> None:
    """기준표 행의 기준값을 쓰는 조건이 없는 행. 행의 대상을 조건 대상 이름과 맞춘 표는 그 대상의 조건(과 대상을 정하지 않은 조건·선정
    조건식)의 값으로만 셉니다(다른 공급이 같은 비율을 써도 그 공급의 조건이 없으면 빠진 행). 맞추지 못한 표는 모든 조건의 값으로 셉니다."""
    if not candidate["eligibility"]:
        return  # 자격이 하나도 없으면 섹션 누락 검사(SECTION_OMISSION_SUSPECTED)가 봅니다
    used = _used_criteria(candidate)
    named = [(item, [part for name in (item.get("scope") or {}).get("targetGroups") or [] for part in _name_parts(name)]) for item in candidate["eligibility"]]
    everyone = {"eligibility": [item for item, names in named if not names], "selectionRules": candidate["selectionRules"]}
    pools: dict[tuple[int, ...], tuple[set[float], set[float]]] = {}

    def pool(items: list[dict[str, Any]]) -> tuple[set[float], set[float]]:
        key = tuple(sorted(id(item) for item in items))
        if key not in pools:
            pools[key] = _used_criteria({**everyone, "eligibility": [*everyone["eligibility"], *items]})
        return pools[key]

    missed: list[tuple[str, list[str], str | None]] = []
    lacking: dict[str, str] = {}  # 기준표 행이 하나도 다뤄지지 않은 대상(공백을 뺀 이름 → 원문 이름)
    for table in _criteria_tables("\n".join(sources.texts.values())):
        owners = _row_owners(list(dict.fromkeys(group for _, _, group in table if group)), named)
        covered: dict[str, bool] = {}
        for shown, values, group in table:
            percents, amounts = used if owners is None or group is None else pool(owners[group])
            gone = [raw for kind, value, raw in values if value not in (percents if kind == "PERCENT" else amounts)]
            if gone:
                missed.append((shown, gone, normalize(group) if owners is not None and group is not None else None))
            if owners is not None and group is not None:
                covered[group] = covered.get(group, False) or not gone
        for group, any_row in covered.items():
            if not any_row:
                lacking.setdefault(normalize(group), group)
    whole = [row for row in missed if row[2] in lacking]
    partial = [row for row in missed if row[2] not in lacking] if len(whole) >= CRITERIA_OMISSION_MIN_ROWS else missed
    # V2 담당에게는 설명 앞 220자만 가므로 대상·빠진 값·첫 행을 앞에 둡니다
    if len(whole) >= CRITERIA_OMISSION_MIN_ROWS:
        names = list(dict.fromkeys(lacking[key] for _, _, key in whole))
        description = (
            f"원문 자격 기준표에서 조건이 하나도 없는 대상: {', '.join(names[:3])}{' 등' if len(names) > 3 else ''}"
            f"({len(whole)}행, 기준값 {_shown_values(whole)}). 그 대상마다 조건으로 넣어야 합니다(빠진 기준 의심): {_shown_rows(whole)}"
        )
        find("V8", CRITERIA_GROUP_OMISSION, "/quality/coverage/eligibility", description)
    if len(partial) >= CRITERIA_OMISSION_MIN_ROWS:
        description = (
            f"원문 자격 기준표 {len(partial)}행의 기준값 {_shown_values(partial)}을 쓰는 자격 조건·예외가 없습니다(빠진 기준 의심): {_shown_rows(partial)}"
        )
        find("V8", CRITERIA_OMISSION, "/quality/coverage/eligibility", description)


def _shown_values(rows: list[tuple[str, list[str], str | None]]) -> str:
    values = list(dict.fromkeys(raw for _, gone, _ in rows for raw in gone))
    return f"{', '.join(values[:4])}{' 등' if len(values) > 4 else ''}"


def _shown_rows(rows: list[tuple[str, list[str], str | None]]) -> str:
    return ", ".join(f"「{shown[:70]}」" for shown, _, _ in rows[:2]) + (" …" if len(rows) > 2 else "")


def check_consistency(candidate: dict[str, Any], sources: SourceBundle) -> list[Finding]:
    """정답표 없이 원문과 결과만으로 하는 V6·V7·V8 검사를 모두 돌려 결과를 돌려줍니다."""
    findings: list[Finding] = []

    def find(check: str, code: str, target: str, description: str) -> None:
        findings.append(Finding(check, code, target, description))

    found = _Located(candidate, sources)
    _check_positions(candidate, found, find)
    _check_price_tables(candidate, sources, found, find)
    _check_unattached_prices(candidate, find)
    _check_price_scope(candidate, found, find)
    _check_consistency(candidate, find)
    _check_unit_counts(candidate, find)
    _check_type_counts(candidate, find)
    _check_payment_parts(candidate, find)
    _check_omissions(candidate, sources, find)
    _check_document_rows(candidate, sources, find)
    _check_schedule_rows(candidate, sources, find)
    _check_criteria_rows(candidate, sources, find)
    _check_image_content(candidate, sources, find)
    _check_image_evidence(candidate, sources, find)
    _check_notice_document(candidate, find)
    _check_income_tiers(candidate, find)
    _check_definition_scope(candidate, find)
    _check_subgroup_scope(candidate, find)
    _check_age_boundary_day(candidate, find)
    _check_child_age_limit(candidate, find)
    return findings


# 원문이 나이 경계일을 따로 정한 조건(「2세 미만(2세가 되는 날을 포함)」 「만 39세가 되는 날까지」): 조건식의 나이는 만 나이 정수라 그날을
# 정확히 담지 못합니다(「미만」으로 옮기면 그날이 빠지고 「이하」로 옮기면 그 나이 한 해가 통째로 들어감). 사람 확인으로 보냅니다.
# 2026-11-09 유료 측정 jbdc-16011 신생아 「2세 미만(2세가 되는 날을 포함)」: 추출 LT 2, 정답표 LTE 2 — 사용자 결정: 확인 필요
AGE_BOUNDARY = "AGE_BOUNDARY_DAY"
AGE_ATTRIBUTES = {"AGE_YEARS", "YOUNGEST_CHILD_AGE_YEARS"}
BOUNDARY_DAY = re.compile(r"\d+\s*세가?\s*되는\s*날")


def _check_age_boundary_day(candidate: dict[str, Any], find: Any) -> None:
    quotes = {e["id"]: e["quote"] for e in candidate.get("evidence") or []}
    for index, item in enumerate(candidate.get("eligibility") or []):
        if not any(atom.get("attribute") in AGE_ATTRIBUTES for _, atom in _atoms((item.get("rule") or {}).get("expression"), "")):
            continue
        for text in (item.get("originalText") or "", *(quotes.get(i, "") for i in item.get("evidenceIds") or [])):
            day = BOUNDARY_DAY.search(text)
            if day:
                shown = " ".join(text[day.start() : day.end() + len(re.match(r"[^)\]」]{0,6}", text[day.end() :])[0])].split())  # 닫는 괄호 앞까지
                why = f"원문이 나이 경계일(「{shown}」)을 따로 정해, 만 나이 조건식으로는 그날을 정확히 담지 못합니다. 원문 확인이 필요합니다"
                find("V7", AGE_BOUNDARY, f"/eligibility/{index}", why)
                break


# 원문 조건 글의 자녀 나이 한정(「6세 이하 자녀를 둔」)이 조건식에 없는 조건: 자녀 수(CHILD_COUNT GTE 1)만 남아 원문보다 넓게 판정됩니다
# (나이 많은 자녀만 둔 신청자도 지원 가능으로). 2026-11-09 저장 결과 1,123개 실행에서 조건식이 있는데 이렇게 빠진 조건은 6가지(dcco-24804
# 「만6세 이하(태아포함)자녀를 둔 사람」을 자녀 수만으로, jbdc-16011 한부모·신생아, dudc-8934 신혼부부, gbdc-e544 한부모·유자녀 혼인가구)로
# 모두 진짜였음(막내 자녀 나이 속성이 생기기 전 실행). 12세 이하만 봅니다(「만19세 미만 자녀 2명 이상」은 자녀 수 기준의 미성년 정의).
# 조건식이 없는 조건은 조건식 없음 검사가 봅니다. 사람 확인으로 보냅니다(그 조건만 보류)
CHILD_AGE_LIMIT = "CHILD_AGE_LIMIT_MISSING"
CHILD_AGE_PHRASE = re.compile(
    r"(?:만\s*)?(\d{1,2})\s*세\s*(?:이하|미만)(?:\s*\([^)]{0,30}\))?\s*(?:의\s*)?(?:자녀|아동|영유아)|자녀\s*\(\s*(?:만\s*)?(\d{1,2})\s*세\s*(?:이하|미만)"
)
YOUNG_CHILD_AGE = 12


def _check_child_age_limit(candidate: dict[str, Any], find: Any) -> None:
    for index, item in enumerate(candidate.get("eligibility") or []):
        rule = item.get("rule") or {}
        if rule.get("status") != "STRUCTURED" or not rule.get("expression"):
            continue
        text = item.get("originalText") or ""
        phrase = next((m for m in CHILD_AGE_PHRASE.finditer(text) if int(m.group(1) or m.group(2)) <= YOUNG_CHILD_AGE), None)
        if phrase is None:
            continue
        expressions = [rule["expression"]]
        for exception in item.get("exceptions") or []:
            expressions += [exception.get("effectExpression"), (exception.get("when") or {}).get("expression")]
        if any(atom.get("attribute") == "YOUNGEST_CHILD_AGE_YEARS" for expression in expressions for _, atom in _atoms(expression, "")):
            continue
        shown = " ".join(phrase.group(0).split())
        why = f"원문 조건 글의 자녀 나이 한정(「{shown}」)이 조건식에 없어 조건이 원문보다 넓습니다. 원문 확인이 필요합니다"
        find("V7", CHILD_AGE_LIMIT, f"/eligibility/{index}", why)


# 보증금(또는 분양가) = 계약금 + 잔금. 실측(2026-11-07 23건 대조, jbdc-16011): 원문 계약금 「18,400.000」을 18,400원으로 읽어
# 보증금 92,000,000 = 18,400,000 + 73,600,000인 행의 계약금이 틀린 채 자동 게시됨. 같은 요금안·같은 대상에 전체 금액 하나와
# 계약금·잔금이 하나씩 있고 다른 금액(중도금일 수 있는 OTHER)이 없을 때만 봅니다. 저장된 23건 결과의 90개 요금안 중 걸린 것은 이 행들뿐
PRICE_PARTS_MISMATCH = "PRICE_PARTS_MISMATCH"
WHOLE_NAMES = {"DEPOSIT": "보증금", "SALE_PRICE": "분양가"}


def _check_payment_parts(candidate: dict[str, Any], find: Any) -> None:
    for g, group in enumerate(candidate["supplyGroups"]):
        plans: dict[tuple[Any, tuple[str, ...]], dict[str, list[dict[str, Any]]]] = {}
        for price in group["prices"]:
            key = (price.get("pricePlanId"), tuple(sorted(price["scope"]["targetGroups"])))
            plans.setdefault(key, {}).setdefault(price["kind"], []).append(price)
        for kinds in plans.values():
            wholes = [kind for kind in WHOLE_NAMES if kind in kinds]
            if len(wholes) != 1 or "OTHER" in kinds or any(len(kinds.get(kind, [])) != 1 for kind in (wholes[0], "CONTRACT_PAYMENT", "BALANCE")):
                continue
            whole, contract, balance = (kinds[kind][0].get("amountKrw") for kind in (wholes[0], "CONTRACT_PAYMENT", "BALANCE"))
            if None in (whole, contract, balance) or whole == contract + balance:
                continue
            label = group.get("housingTypeCode") or group.get("unitLabel") or group.get("id")
            parts = f"계약금({contract:,}원)과 잔금({balance:,}원)의 합이 {WHOLE_NAMES[wholes[0]]}({whole:,}원)와 다릅니다"
            find("V7", PRICE_PARTS_MISMATCH, f"/supplyGroups/{g}/prices", f"「{label}」 {parts}. 원문 금액을 확인해야 합니다.")


# 임대료 소득 구간을 자격으로 넣음(2026-11-05 실측 sh-311087: 「소득 50% 이하」「50% 초과 70% 이하」 임대료 구간이 자격 조건 둘로 들어가
# 자동 게시됨 — 자격은 「70% 이하」 하나). 소득 비율 자격이 둘 이상이고 그 기준값이 모두 가격의 소득 구간 비율이며 상한이 서로 다르면,
# 구간을 자격으로 나눈 것일 수 있어 그 자격들을 사람 확인으로 보냅니다(어느 것이 진짜 자격인지 코드는 정할 수 없음)
INCOME_TIER = "ELIGIBILITY_FROM_PRICE_TIER"
PERCENT_WORD = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _income_percents(node: Any) -> list[float]:
    found: list[float] = []
    if isinstance(node, dict):
        if node.get("attribute") == "INCOME_BENCHMARK_PERCENT":
            value = node.get("value")
            found += [float(v) for v in (value if isinstance(value, list) else [value]) if isinstance(v, int | float)]
        for child in node.values():
            found += _income_percents(child)
    elif isinstance(node, list):
        for child in node:
            found += _income_percents(child)
    return found


def _check_income_tiers(candidate: dict[str, Any], find: Any) -> None:
    tiers: set[float] = set()
    for group in candidate.get("supplyGroups") or []:
        for price in group.get("prices") or []:
            scope = price.get("scope") or {}
            words = [*(scope.get("targetGroups") or []), scope.get("description") or "", price.get("pricePlanId") or ""]
            tiers |= {float(x) for word in words for x in PERCENT_WORD.findall(str(word))}
    if len(tiers) < 2:
        return
    eligibility = candidate.get("eligibility") or []
    items = [(i, values) for i, item in enumerate(eligibility) if (values := _income_percents((item.get("rule") or {}).get("expression")))]
    if len(items) < 2 or not all(set(values) <= tiers for _, values in items) or len({max(values) for _, values in items}) < 2:
        return
    for index, values in items:
        shown = ", ".join(f"{v:g}%" for v in sorted(set(values)))
        description = f"소득 기준 {shown}이(가) 가격표의 소득 구간과 같습니다. 임대료 구간을 자격으로 나눈 것인지 확인하세요."
        find("V8", INCOME_TIER, f"/eligibility/{index}", description)


# 낱말 정의로 만든 조건이 그 낱말이 아닌 대상에 붙음(2026-11-06 V2 5건 재측정 dcco-24812: 「주거약자」 정의의 한 갈래 「① 고령자(만 65세 이상인 자)」로
# 만 65세 이상 조건을 만들어 대상 「주거약자용 주택 신청자」 전체에 붙여 게시됨 — 장애인 등 다른 주거약자에게는 나이 기준이 없음).
# 근거 원문 한 줄이 「[번호] 낱말(정의)」뿐이고 정의 안에 조건식의 값이 있는데 대상(scope.targetGroups)에 그 낱말이 없으면, 그 낱말에 해당하는
# 사람만의 기준을 대상 전체에 붙였을 수 있어 사람 확인으로 보냅니다. 대상이 비어 있으면(신청자 전체) 보지 않습니다: 「성년자(만 19세 이상)」처럼
# 정의가 곧 모두의 요건인 경우입니다. 「소득 : 70% 이하」 같은 콜론 줄은 기준 이름 줄과 섞여 보지 않습니다
# (저장된 V1·V2 후보 155개 중 이 공고의 V2 두 회차만 걸림)
DEFINITION_SCOPE = "DEFINITION_SCOPE_SUSPECTED"
DEFINITION_ENTRY = re.compile(
    r"^\s*(?:[①-⑳]|\(\s*\d{1,2}\s*\)|\d{1,2}\s*[.)]|[가-하]\s*[.)]|[-•·▪○◦※*])?\s*([가-힣·ㆍ]{2,12})\s*\(([^()]{1,80})\)\s*[.,;]?\s*$"
)
DEFINED_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _check_definition_scope(candidate: dict[str, Any], find: Any) -> None:
    quotes = {e["id"]: e["quote"] for e in candidate.get("evidence") or []}
    for index, item in enumerate(candidate["eligibility"]):
        groups = [g for g in (item.get("scope") or {}).get("targetGroups") or [] if g]
        values = {
            float(v)
            for _, atom in _atoms(item["rule"]["expression"], "")
            for v in (atom.get("value") if isinstance(atom.get("value"), list) else [atom.get("value")])
            if isinstance(v, int | float) and not isinstance(v, bool)
        }
        if not groups or not values:
            continue
        texts = [item.get("originalText") or "", *(quotes.get(i, "") for i in item.get("evidenceIds") or [])]
        for line in (line for text in texts for line in text.split("\n")):
            entry = DEFINITION_ENTRY.match(line)
            if not entry or any(normalize(entry.group(1)) in normalize(group) for group in groups):
                continue
            if values & {float(n.replace(",", "")) for n in DEFINED_NUMBER.findall(entry.group(2))}:
                term = entry.group(1)
                description = (
                    f"「{line.strip()}」는 「{term}」의 정의인데, 이 조건의 대상({', '.join(groups)})에는 「{term}」이(가) 없습니다. "
                    f"대상 전체의 기준인지, 그중 「{term}」에게만 적용되는 기준인지 확인하세요."
                )
                find("V7", DEFINITION_SCOPE, f"/eligibility/{index}", description)
                break


# 일부 계층의 기준을 대상 없이 넣음(2026-11-08 V2 유료 확인 bmc-106: 1순위 자격은 가~자목 계층 중 하나에 해당하면 되는데, 자격 담당이 계층
# 조건의 대상(scope.targetGroups)을 비우고 적용 대상 글(appliesTo)에만 계층 이름을 적어, 자목 「65세 이상 수급권자·차상위계층」의 나이 65세 이상,
# 사목 「65세 이상 직계존속 부양」의 부모 나이, 나·마·바·아목만의 소득·자산·자동차 상한이 신청자 전체 조건으로 자동 게시됨 — 65세 미만은 모두
# 「지원 불가」. 앞 실행은 같은 조건을 계층 대상으로 넣었음). 대상·공급 묶음·위치·공급 구분 어디에도 한정되지 않은 조건식 가운데
# ① 서로 다른 조건 항목이 같은 주체·기준에 다른 경계를 걸면 더 좁은 쪽(모두 함께 적용되어 넓은 쪽은 뜻이 없어짐: 한쪽은 일부 계층의 기준으로 봄).
#    한 항목 안의 경계 둘(「이상」을 「이하」로 뒤집어 상한이 둘이 된 나이 등)은 이 꼴이 아니라 보지 않습니다(방향 대조 OPERATOR_MISMATCH가 봄)
# ② 부모·그 밖의 가족(자녀 등)의 나이(막내 자녀 나이 속성 포함. 공고 대상이 하나뿐인 공고의 자녀 나이는 빼고 봄)
# ③ 원문 글이나 근거 인용 하나가 목록의 목을 둘 이상 가리킴(「나목, 마목」 「‘나’목, ‘마’목의 경우에는」). 근거도 봅니다: 다시 확인한 실행에서
#    담당이 같은 총자산·자동차 조건의 원문 글을 「총자산가액 기준 … 이하」로 좁혀 적어 원문 글로는 안 걸렸고, 근거에는 「자산기준이 적용되는 자격
#    - 나목(국가유공자등), 마목(북한이탈주민) …」이 그대로 있었음
# 을 사람 확인으로 보냅니다. 저장된 V1·V2 결과 전체(대상 없는 조건식 1,746개)에서 걸린 것은 이 공고의 이 조건들뿐이었음(적용 대상 글이나
# 「~의 경우에는」 같은 한정 표현으로 보면 40개 넘게 걸리고 대부분 신청자 전체의 기준이라 쓰지 않음)
SUBGROUP_SCOPE = "SCOPE_SUBGROUP_SUSPECTED"
FAMILY_SUBJECTS = {"PARENTS": "부모", "OTHER": "가족"}
LIST_ITEM_REFERENCE = re.compile(r"(?<![가-힣])[‘'「“\"]?([가나다라마바사아자차카타파하])[’'」”\"]?\s?목(?!적)")
BOUND_SIDES = {"GT": "low", "GTE": "low", "LT": "high", "LTE": "high"}


def _check_subgroup_scope(candidate: dict[str, Any], find: Any) -> None:
    quotes = {e["id"]: e["quote"] for e in candidate.get("evidence") or []}
    flagged: dict[int, str] = {}
    bounds: dict[tuple[str, str, str], dict[int, float]] = {}  # (주체, 기준, low·high) → 항목 → 그 항목의 가장 좁은 경계
    # 공고 대상이 하나뿐이면(신생아 가구만 모집) 그 대상의 자녀 요건이 곧 신청자 전체의 요건일 수 있어 자녀 나이는 보지 않습니다
    several = len((candidate.get("notice") or {}).get("targetGroups") or []) != 1
    for index, item in enumerate(candidate.get("eligibility") or []):
        if not _applies_to_everyone(item):
            continue
        expression = item["rule"].get("expression")
        for key, value in _top_bounds(expression):
            kept = bounds.setdefault(key, {})
            kept[index] = (max if key[2] == "low" else min)(kept.get(index, value), value)
        for _, atom in _atoms(expression, ""):
            if atom.get("attribute") == "AGE_YEARS" and atom.get("subject") in FAMILY_SUBJECTS:
                flagged.setdefault(index, f"{FAMILY_SUBJECTS[atom['subject']]} 나이 기준이 대상 없이 신청자 전체에 걸립니다")
            elif atom.get("attribute") == "YOUNGEST_CHILD_AGE_YEARS" and several:
                # 2026-11-09 유료 측정 jbdc-16011: 「6세 이하(만7세미만) 의 자녀를 둔」(신혼부부 정의의 일부)을 대상 없이 넣어 모두에게 자녀 요건이 걸림
                flagged.setdefault(index, "자녀 나이 기준이 대상 없이 신청자 전체에 걸립니다")
        for text in (item.get("originalText") or "", *(quotes.get(i, "") for i in item.get("evidenceIds") or [])):
            letters = list(dict.fromkeys(LIST_ITEM_REFERENCE.findall(text)))
            if len(letters) >= 2:
                items = ", ".join(f"{letter}목" for letter in letters[:4])
                flagged.setdefault(index, f"원문이 목록의 일부 목({items})만 가리키는데 대상 없이 신청자 전체에 걸립니다")
                break
    for (_, attribute, side), per_item in bounds.items():
        if len(set(per_item.values())) < 2:
            continue
        strict = max(per_item.values()) if side == "low" else min(per_item.values())
        shown = ", ".join(f"{value:g}" for value in sorted(set(per_item.values())))
        for index, value in per_item.items():
            if value == strict:
                why = f"대상 없는 조건들이 같은 기준({_meaning(attribute)})에 서로 다른 경계({shown})를 걸어 더 좁은 {value:g}이(가) 신청자 전체에 걸립니다"
                flagged.setdefault(index, why)
    for index, why in sorted(flagged.items()):
        find("V7", SUBGROUP_SCOPE, f"/eligibility/{index}", f"{why}. 일부 계층(자격 목·공급유형·순위)의 기준이면 그 대상에만 적용해야 합니다.")


def _applies_to_everyone(item: dict[str, Any]) -> bool:
    """대상·공급 묶음·위치·공급 구분 어디에도 한정되지 않은 조건식 항목(공고의 모든 신청자에게 함께 적용)."""
    scope = item.get("scope") or {}
    limited = scope.get("targetGroups") or scope.get("supplyGroupIds") or scope.get("locationIds") or scope.get("supplyCategory") not in (None, "ALL")
    return (item.get("rule") or {}).get("status") == "STRUCTURED" and not limited


def _top_bounds(expression: dict[str, Any] | None) -> list[tuple[tuple[str, str, str], float]]:
    """조건식 맨 위(원자 하나 또는 ALL의 원자들)의 숫자 경계 ((주체, 기준, low·high), 값). ANY·NOT 안의 경계는 함께 적용되는 경계가 아니라 뺍니다."""
    if not isinstance(expression, dict):
        return []
    kind = expression.get("kind")
    atoms = [expression] if kind == "ATOMIC" else [c for c in expression.get("children") or [] if c.get("kind") == "ATOMIC"] if kind == "ALL" else []
    found = []
    for atom in atoms:
        subject, attribute, value, operator = atom.get("subject"), atom.get("attribute"), atom.get("value"), atom.get("operator")
        if operator == "BETWEEN" and isinstance(value, list) and len(value) == 2 and all(map(_number, value)):
            found += [((subject, attribute, "low"), float(value[0])), ((subject, attribute, "high"), float(value[1]))]
        elif operator in BOUND_SIDES and _number(value):
            found.append(((subject, attribute, BOUND_SIDES[operator]), float(value)))
    return found


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _meaning(attribute: str) -> str:
    """속성 사전의 뜻(「만 나이」 「총자산」). 사전에 없으면 코드 그대로."""
    return next((spec["meaning"] for spec in tools().ATTRIBUTE_DICTIONARY["attributes"] if spec["code"] == attribute), attribute)
