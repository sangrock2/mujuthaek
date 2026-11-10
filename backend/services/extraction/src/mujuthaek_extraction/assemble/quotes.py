"""AI가 낸 인용문을 원문에서 찾아 위치(코드 포인트 [start, end))를 계산합니다.

AI는 위치를 세지 않습니다. 정확히 일치하는 곳을 먼저 찾고, 없으면 NFKC·공백 제거로 정규화해 찾은 뒤 원문 위치로 되돌립니다.
같은 인용문이 여러 곳에 있으면 같은 항목의 다른 인용과 가장 가까운 곳을 고릅니다(결정 E3). 기준이 없을 때 충분히 긴 인용은
요약·본문에 같은 문장이 반복된 경우로 보고 첫 위치를 고르며, 짧은 인용은 AMBIGUOUS로 남깁니다(E3 보완, LH 사례).
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass, replace
from enum import Enum

MIN_QUOTE_CHARS = 4  # 정규화 후 이보다 짧으면 우연 일치 가능성이 커서 검수 메모를 남깁니다
LONG_QUOTE_CHARS = 15  # 정규화 후 이 이상이면 여러 곳에 있어도 같은 문장의 반복으로 보고 첫 위치를 씁니다


class QuoteStatus(Enum):
    FOUND = "FOUND"  # 한 곳에서만 찾음
    CHOSEN_NEAREST = "CHOSEN_NEAREST"  # 여러 곳 중 같은 항목의 다른 인용과 가장 가까운 곳
    CHOSEN_FIRST = "CHOSEN_FIRST"  # 기준이 없지만 긴 인용이라 첫 위치를 씀 (요약·본문 반복)
    AMBIGUOUS = "AMBIGUOUS"  # 여러 곳이고 고를 근거가 없음
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class QuoteResolution:
    quote: str
    status: QuoteStatus
    span: tuple[int, int] | None  # 원문 코드 포인트 [start, end). AMBIGUOUS·NOT_FOUND면 None
    candidates: tuple[tuple[int, int], ...]
    exact: bool  # 원문 그대로 일치했는지(정규화 없이)
    too_short: bool
    scattered: bool = False  # 이어진 문장으로는 없고, 낱말들이 가까운 곳에 흩어져 있어 찾음(find_scattered). 낱말 순서는 보지 않습니다


def normalize(text: str) -> str:
    """NFKC + 공백 제거 + PDF 표 칸 구분자(|) 제거. AI가 같은 행의 칸을 구분자 없이 이어 인용해도 찾을 수 있게 합니다(2026-10-16 실측)."""
    return "".join(unicodedata.normalize("NFKC", text).split()).replace("|", "")


def _clusters(text: str) -> list[tuple[int, int]]:
    """정규화 단위가 되는 글자 묶음. 결합 문자와 분해된 한글 자모(초성+중성+종성)는 앞 글자와 묶습니다."""
    spans: list[tuple[int, int]] = []
    for index, char in enumerate(text):
        code = ord(char)
        joins = unicodedata.combining(char) or 0x1160 <= code <= 0x11FF or 0xD7B0 <= code <= 0xD7FF
        if spans and joins:
            spans[-1] = (spans[-1][0], index + 1)
        else:
            spans.append((index, index + 1))
    return spans


# 따옴표류(2026-10-24 세 번째 채점: 원문 「’미가입자‘, ’지역가입자‘」의 짝 안 맞는 따옴표를 AI가 「’지역가입자’」로 고쳐 쓰거나
# 인용 끝에 「'」를 덧붙여, 글자는 같은데 서류 10여 개가 근거를 못 찾아 빠짐). 느슨한 찾기에서만 빼고 봅니다
QUOTE_MARKS = "「」『』“”‘’‚‛„‟\"'＂＇`´′″〈〉《》"
_DROP_QUOTE_MARKS = str.maketrans("", "", QUOTE_MARKS)
TABLE_AID_LINES = ("  [열 제목] ", "  ↳ ")  # 구조 방식이 표에 덧붙이는 줄(details.TABLE_AIDS와 같음)


def loose(text: str) -> str:
    """느슨한 정규화: normalize에 더해 따옴표류를 뺍니다. 근거 위치를 찾을 때만 쓰고, 값 확인(claims·details)에는 쓰지 않습니다."""
    return normalize(text).translate(_DROP_QUOTE_MARKS)


class NormalizedText:
    """정규화한 글자마다 원문 위치를 기억해 두고, 정규화 문자열에서 찾은 위치를 원문 위치로 되돌립니다.
    relaxed=True면 따옴표류를 빼고(loose) 표 읽기 도움 줄(↳·[열 제목])을 건너뛴 색인입니다: 표 두 행을 이어 인용했는데 원문에서는
    두 행 사이에 프로그램이 붙인 읽기 줄이 끼어 있어도 찾습니다. 찾은 범위는 원문 위치(그 사이 줄 포함)입니다."""

    def __init__(self, text: str, *, relaxed: bool = False):
        self.text = text
        chars: list[str] = []
        starts: list[int] = []
        ends: list[int] = []
        skip = _aid_line_spans(text) if relaxed else []
        at = 0
        for start, end in _clusters(text):
            while at < len(skip) and skip[at][1] <= start:
                at += 1
            if at < len(skip) and skip[at][0] <= start < skip[at][1]:
                continue
            piece = text[start:end]
            for char in loose(piece) if relaxed else normalize(piece):
                chars.append(char)
                starts.append(start)
                ends.append(end)
        self.value = "".join(chars)
        self._starts = starts
        self._ends = ends
        self._loose: NormalizedText | None = None

    def loose_index(self) -> NormalizedText:
        """같은 원문의 느슨한 색인(처음 쓸 때 한 번 만듭니다)."""
        if self._loose is None:
            self._loose = NormalizedText(self.text, relaxed=True)
        return self._loose

    def find_all(self, needle: str) -> list[tuple[int, int]]:
        found = []
        position = self.value.find(needle)
        while needle and position >= 0:
            found.append((self._starts[position], self._ends[position + len(needle) - 1]))
            position = self.value.find(needle, position + 1)
        return sorted(set(found))


def _aid_line_spans(text: str) -> list[tuple[int, int]]:
    """표 읽기 도움 줄(줄바꿈 포함)의 원문 범위들."""
    spans, offset = [], 0
    for line in text.split("\n"):
        if line.startswith(TABLE_AID_LINES):
            spans.append((offset, offset + len(line) + 1))
        offset += len(line) + 1
    return spans


def _exact_all(text: str, quote: str) -> list[tuple[int, int]]:
    found = []
    position = text.find(quote)
    while quote and position >= 0:
        found.append((position, position + len(quote)))
        position = text.find(quote, position + 1)
    return found


# PDF를 글자로 바꿀 때 프로그램이 붙인 표시. 원문 내용이 아니므로 AI가 인용에 넣어도 빼고 찾습니다(실측: "[표 6-3] | 서류 | …")
LAYOUT_MARKER = re.compile(r"\[표\s*\d+-\d+\]|---\s*\d+쪽[^\n]*?---")


def strip_markers(quote: str) -> str:
    return LAYOUT_MARKER.sub(" ", quote).strip()


# 줄 머리 글머리표. AI가 문장 중간부터 인용하면서 앞 문장의 글머리표를 붙이는 경우가 있어, 못 찾으면 떼고 다시 찾습니다
# (실측: 원문 "• 공고문은 … 있으며, 금회 모집 공고는 …" → 인용 "• 금회 모집 공고는 …")
LEADING_BULLET = re.compile(r"^\s*[•·▪■□○●◦※\-*]+\s*")
# 줄 머리 번호표(2026-10-24 여덟 번째 채점: 원문 「1) 입주신청서」를 AI가 「1. 입주신청서」로 적어 서류 2개가 빠짐). 번호 모양만 다르면 떼고 찾습니다
LEADING_NUMBER = re.compile(r"^\s*(?:\d{1,2}\s*[.)]|\(\s*\d{1,2}\s*\)|[①-⑳]|[가-하]\s*[.)])\s*")


def candidates(text: str, quote: str, index: NormalizedText | None = None) -> tuple[list[tuple[int, int]], bool]:
    quote = strip_markers(quote)
    exact = _exact_all(text, quote)
    if exact:
        return exact, True
    index = index or NormalizedText(text)
    found = index.find_all(normalize(quote))
    bare = LEADING_NUMBER.sub("", LEADING_BULLET.sub("", quote))
    if not found and bare != quote and len(normalize(bare)) >= LONG_QUOTE_CHARS:
        found = index.find_all(normalize(bare))
    if not found and JOIN_MARK in quote:
        found = _joined_lines(index, quote)
    if not found and TABLE_ROW.match(quote):
        found = _merged_row(text, quote)
    if not found:
        # 표기 차이만 흡수합니다: 따옴표류를 빼고, 표 행 사이 읽기 도움 줄을 건너뜁니다(「|」·공백은 normalize가 이미 뺌).
        # 글자(숫자·낱말)는 하나도 바꾸지 않으므로 다른 값을 근거로 받지 않습니다. 너무 짧아진 인용은 쓰지 않습니다
        needle = loose(quote)
        if len(needle) >= LONG_QUOTE_CHARS:
            found = index.loose_index().find_all(needle)
    return found, False


# AI가 원문의 이어진 줄을 「 / 」로 이어 붙여 인용함(줄 머리 글머리표는 빠뜨림). 조각마다 원문에 있고, 순서대로 글머리표·문장 부호만
# 사이에 두고 붙어 있으면 그 범위입니다(실측 2026-10-20 LH 인천부평: 「- 대학생 : … 사람 / 취업준비생 : …」 원문은 두 줄
# 「- 대학생 : … 사람⏎- 취업준비생 : …」 — 근거를 못 찾아 자격 항목이 빠지고 자격 섹션 전체가 보류됨)
JOIN_MARK = " / "
JOIN_GAP = re.compile(r"[•·▪■□○●◦※\-*.,;:)\]」』]*")


def _joined_lines(index: NormalizedText, quote: str) -> list[tuple[int, int]]:
    parts = [normalize(LEADING_BULLET.sub("", p)) for p in quote.split(JOIN_MARK)]
    if len(parts) < 2 or any(len(p) < MIN_QUOTE_CHARS for p in parts):
        return []
    found = []
    position = index.value.find(parts[0])
    while position >= 0:
        at = position + len(parts[0])
        for part in parts[1:]:
            nxt = index.value.find(part, at)
            if nxt < 0 or not JOIN_GAP.fullmatch(index.value[at:nxt]):
                break
            at = nxt + len(part)
        else:
            found.append((index._starts[position], index._ends[at - 1]))
        position = index.value.find(parts[0], position + 1)
    return sorted(set(found))


# 표 한 행 인용 「| … |」. AI가 위 행과 병합된 빈 칸에 그 값을 채워 인용함(실측 LH 인천부평 자산 기준표: 원문 「|  |  | 1인 | 120% |…」,
# 인용 「| | 2인 | | 1인 | 120% |…」 — 근거가 흩어진 것으로 보아 자격 조건 76개가 검수로 감). 원문 행의 값은 하나도 빠지지 않고,
# 더 적힌 값은 모두 그 행의 빈 칸에 병합 복원한 값(같은 표에서 바로 위 행들의 같은 칸)일 때만 그 행입니다.
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.S)


def _cells(line: str) -> list[str]:
    return [normalize(c) for c in line.strip().strip("|").split("|")]


def _merged_row(text: str, quote: str) -> list[tuple[int, int]]:
    wanted = [c for c in _cells(quote) if c]
    if len(wanted) < 2:
        return []
    found = []
    above: dict[int, list[str]] = {}  # 칸 수 → 같은 표에서 바로 위 행까지 칸마다 마지막 값
    offset = 0
    for line in text.split("\n"):
        start, offset = offset, offset + len(line) + 1
        stripped = line.strip()
        if not stripped.startswith("|"):
            if not stripped.startswith("↳"):  # 행 읽기 줄은 표 안, 그 밖의 줄이 나오면 표가 끝남
                above.clear()
            continue
        cells = _cells(stripped)
        last = above.get(len(cells))
        filled = [c or (last[i] if last else "") for i, c in enumerate(cells)]
        above[len(cells)] = filled
        if _explains(wanted, cells, filled):
            found.append((start + len(line) - len(line.lstrip()), start + len(line.rstrip())))
    return found


def _explains(wanted: list[str], own: list[str], filled: list[str]) -> bool:
    """인용 값(wanted)이 순서대로 원문 행의 칸 값과 같고, 원문 행에 있는 값은 모두 쓰였으며, 그 밖의 값은 병합 복원 값인지."""
    at = 0
    for own_cell, value in zip(own, filled, strict=True):
        if at < len(wanted) and value and wanted[at] == value:
            at += 1
        elif own_cell:
            return False  # 원문 행의 값을 인용이 빠뜨림
    return at == len(wanted) and any(own)


SCATTER_MIN_CHARS = 20  # 낱말 단위로 찾을 인용의 최소 길이(정규화 후)
SCATTER_MIN_WORDS = 4


def _quote_words(quote: str) -> list[str]:
    return [w for w in (normalize(t) for t in re.split(r"[\s|]+", strip_markers(quote))) if w]


def find_scattered(index: NormalizedText, quote: str) -> list[tuple[int, int]]:
    """인용의 낱말이 모두 가까운 범위(인용 길이의 약 2배) 안에 있으면 그 범위를 돌려줍니다.
    PDF의 순서도·칸 없는 표는 글자가 줄 단위로 뒤섞여 읽혀, AI가 읽기 순서대로 이은 인용이 그대로는 없습니다
    (실측: 남해창선 "동일순위 내 경쟁 시 선정순서 … 전입일자가 오래된 자 세대구성원 수가 많은 자 …")."""
    words = _quote_words(quote)
    length = sum(len(w) for w in words)
    if length < SCATTER_MIN_CHARS or len(words) < SCATTER_MIN_WORDS:
        return []
    anchor = max(words, key=len)
    reach = 2 * length
    found = set()
    position = index.value.find(anchor)
    while position >= 0:
        lo, hi = max(0, position - reach), position + len(anchor) + reach
        starts, ends = [], []
        for word in words:
            hits = []
            at = index.value.find(word, lo)
            while 0 <= at and at + len(word) <= hi:
                hits.append(at)
                at = index.value.find(word, at + 1)
            if not hits:
                break
            best = min(hits, key=lambda h: abs(h - position))
            starts.append(best)
            ends.append(best + len(word))
        else:
            if max(ends) - min(starts) <= reach + len(anchor):
                found.add((index._starts[min(starts)], index._ends[max(ends) - 1]))
        position = index.value.find(anchor, position + 1)
    return sorted(found)


# 흩어진 근거 중 인용 낱말이 원문과 같은 순서로 있고 사이에 짧은 글자만 끼어 있는 경우(표 머리 칸이 문장 사이에 섞여 읽힘)는
# 낱말 순서가 그대로라 뜻이 뒤집힐 수 없습니다. 끼어든 글자에 숫자나 뜻을 바꾸는 말이 있으면 인정하지 않습니다(빠지면 뜻이 달라짐).
# 실측 live-perf LH 9550(2026-10-20): 자산 기준표 인용이 원문 「2023.3.27. 구분 이전 출생한」에서 표 머리 칸 「구분」만 빠져 자격 조건 2개가 검수로 감
ORDER_GAP_MAX_CHARS = 6  # 끼어든 글자 하나의 최대 길이(정규화 후)
ORDER_GAP_MAX_COUNT = 2  # 끼어든 곳의 최대 수
MEANING_MARKERS = re.compile(r"\d|이상|이하|초과|미만|제외|제한|않|아니|아닌|불가|없|단,|한함|한하|이전|이후|부터|까지|외")


def find_in_order(index: NormalizedText, quote: str, span: tuple[int, int]) -> tuple[tuple[int, int], tuple[str, ...]] | None:
    """흩어진 근거 span 둘레(앞뒤로 인용 길이만큼)에서 인용 낱말이 원문과 같은 순서로 나오고 끼어든 글자가 짧고 뜻이 없으면
    (그 원문 범위, 끼어든 글자들)을, 아니면 None을 돌려줍니다. find_scattered의 범위는 낱말마다 기준 낱말에 가장 가까운 곳으로 정해
    같은 낱말이 앞뒤에 또 있으면(「자산」과 「총자산가액」) 인용 첫 낱말이 범위 밖에 있을 수 있어 둘레까지 봅니다."""
    words = _quote_words(quote)
    if not words:
        return None
    reach = sum(len(w) for w in words)
    lo = max(0, bisect_left(index._starts, span[0]) - reach)
    hi = min(len(index.value), bisect_left(index._starts, span[1]) + reach)
    region = index.value[lo:hi]
    start = region.find(words[0])
    while start >= 0:
        gaps, at = [], start + len(words[0])
        for word in words[1:]:
            found = region.find(word, at)
            if found < 0:
                return None  # 이보다 뒤에서 시작해도 이 낱말은 없습니다
            if found > at:
                gaps.append(region[at:found])
            at = found + len(word)
        if len(gaps) <= ORDER_GAP_MAX_COUNT and all(len(g) <= ORDER_GAP_MAX_CHARS and not MEANING_MARKERS.search(g) for g in gaps):
            return (index._starts[lo + start], index._ends[lo + at - 1]), tuple(gaps)
        start = region.find(words[0], start + 1)
    return None


def _distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, max(a[0], b[0]) - min(a[1], b[1]))


# 이어 붙인 인용(2026-10-24 여섯 번째 채점: AI가 1쪽·3쪽 두 문장을 한 인용으로 이어 써 원문에서 못 찾아 「만 19세 이상」 자격이 빠지고
# 자격 섹션 전체가 보류됨). 인용이 원문에 없으면 문장·줄 단위로 나눠, 조각마다 원문에 한 곳씩 있으면 조각들을 각각 근거로 씁니다
SPLIT_JOINED = re.compile(r"(?<=[가-힣][.。!?])\s+|(?<=다)\s+|\s*\n\s*|\s+/\s+|\s*(?:…|\.\.\.)\s*")
SPLIT_PART_CHARS = 8  # 정규화 뒤 이보다 짧은 조각이 있으면 나누지 않습니다(우연 일치)
# 조각들이 원문에서 이만큼 떨어져 있어야(다른 곳) 나눕니다. 가까우면 한 문장의 낱말을 빼먹은 것일 수 있어 흩어진 근거 검사로 보냅니다
SPLIT_APART_CHARS = 200


def split_joined_quote(text: str, quote: str, index: NormalizedText) -> list[str] | None:
    """원문에 없는 인용이 원문에 한 곳씩 있는 문장 조각들을 이어 붙인 것이면 그 조각들, 아니면 None."""
    if candidates(text, quote, index)[0]:
        return None
    return _split_sentences(text, quote, index) or _split_cells(text, quote, index)


def _split_sentences(text: str, quote: str, index: NormalizedText) -> list[str] | None:
    parts = [p.strip() for p in SPLIT_JOINED.split(quote) if p and p.strip()]
    if len(parts) < 2 or any(len(normalize(strip_markers(p))) < SPLIT_PART_CHARS for p in parts):
        return None
    spans = [candidates(text, part, index)[0] for part in parts]
    if not all(len(found) == 1 for found in spans):
        return None
    places = [found[0] for found in spans]
    if any(b[0] >= a[0] and b[0] - a[1] < SPLIT_APART_CHARS for a, b in zip(places, places[1:], strict=False)):
        return None
    return parts


def _split_cells(text: str, quote: str, index: NormalizedText) -> list[str] | None:
    """표 여러 행·칸을 이어 쓰며 칸 일부를 빼먹은 인용(2026-10-24 일곱 번째 채점: 「[표 25-1] 동의서 [붙임1] | 대상자 : … 작성 제외 | 1통 | …」가
    원문 칸의 뒷부분 「동의방법 : …」을 빼고 이어져 서류 5개가 빠짐). 「|」 칸 경계마다 나눠, 짧은 칸(「1통」)은 빼고 나머지 칸이 모두 원문에
    한 곳씩 있으면 그 칸들을 근거로 씁니다. 칸 경계는 원문의 구분이라 칸끼리 가까워도 됩니다(칸 안 글자는 이어진 그대로여야 함)."""
    if quote.count("|") < 1:
        return None
    parts = [p.strip() for p in strip_markers(quote).split("|") if len(normalize(p)) >= SPLIT_PART_CHARS]
    if len(parts) < 2:
        return None
    if not all(len(candidates(text, part, index)[0]) == 1 for part in parts):
        return None
    return parts


def resolve_item_quotes(text: str, quotes: list[str], index: NormalizedText | None = None) -> list[QuoteResolution]:
    """한 항목(예: 자격 조건 하나)의 인용문들을 함께 풀어 위치를 정합니다. 결과 순서는 입력 순서와 같습니다."""
    index = index or NormalizedText(text)
    found = [candidates(text, quote, index) for quote in quotes]
    scattered = [not spans and bool(find_scattered(index, quote)) for quote, (spans, _) in zip(quotes, found, strict=True)]
    found = [(find_scattered(index, quote), False) if flag else pair for quote, pair, flag in zip(quotes, found, scattered, strict=True)]
    anchors = [spans[0] for spans, _ in found if len(spans) == 1]
    results = []
    for quote, (spans, exact), flag in zip(quotes, found, scattered, strict=True):
        length = len(normalize(strip_markers(quote)))
        short = length < MIN_QUOTE_CHARS
        status, span = QuoteStatus.NOT_FOUND, None
        if len(spans) == 1:
            status, span = QuoteStatus.FOUND, spans[0]
        elif spans and anchors:
            ranked = sorted(spans, key=lambda s: min(_distance(s, a) for a in anchors))
            best = min(_distance(ranked[0], a) for a in anchors)
            second = min(_distance(ranked[1], a) for a in anchors)
            if best < second:
                status, span = QuoteStatus.CHOSEN_NEAREST, ranked[0]
            elif length >= LONG_QUOTE_CHARS:
                status, span = QuoteStatus.CHOSEN_FIRST, spans[0]
            else:
                status = QuoteStatus.AMBIGUOUS
        elif spans and length >= LONG_QUOTE_CHARS:
            status, span = QuoteStatus.CHOSEN_FIRST, spans[0]
        elif spans:
            status = QuoteStatus.AMBIGUOUS
        results.append(QuoteResolution(quote, status, span, tuple(spans), exact, short, flag))
    return results


def quote_in_unit_row(row: dict, quote: str) -> bool:
    """호별 표 한 행의 값 중에 인용문이 들어 있는지 확인합니다(정규화 비교)."""
    needle = normalize(quote)
    return bool(needle) and any(needle in normalize(str(value)) for key, value in row.items() if key != "checks")


GROUP_LOOKBACK = 3000  # 대상 계층 이름을 찾아볼 앞쪽 글자 수
GROUP_MARGIN = 0.5  # 가장 가까운 후보가 두 번째보다 이 비율 이하로 가까워야 고릅니다


def choose_by_target_groups(text: str, resolution: QuoteResolution, groups: list[str]) -> QuoteResolution:
    """같은 문장이 계층마다 반복될 때(예: 행복주택 대학생·청년 부분의 "② 혼인 중이 아닐 것"),
    항목의 대상 계층 이름(scope.targetGroups)이 바로 앞에 가장 가깝게 나오는 위치를 고릅니다. 뚜렷하지 않으면 그대로 둡니다."""
    # 긴 인용이라 첫 위치를 고른 경우(CHOSEN_FIRST)도 다시 봅니다. 예전엔 15자 이상 반복 문장이 대상 계층을 보기 전에 첫 위치로 정해져,
    # 신혼부부 조건의 근거가 청년 부분을 가리켰습니다(검토 2026-10-16). 계층 이름으로 뚜렷이 못 고르면 첫 위치 그대로 둡니다.
    if resolution.status not in (QuoteStatus.AMBIGUOUS, QuoteStatus.CHOSEN_FIRST) or not groups or len(resolution.candidates) < 2:
        return resolution
    names = [n for g in groups for n in {g, re.sub(r"\(.*?\)", "", g).strip()} if n]

    def distance(span: tuple[int, int]) -> int:
        window = text[max(0, span[0] - GROUP_LOOKBACK) : span[0]]
        found = [window.rfind(n) for n in names]
        best = max(found)
        return len(window) - best if best >= 0 else GROUP_LOOKBACK + 1

    ranked = sorted(resolution.candidates, key=distance)
    first, second = distance(ranked[0]), distance(ranked[1])
    if first <= GROUP_LOOKBACK and first <= second * GROUP_MARGIN:
        return replace(resolution, status=QuoteStatus.CHOSEN_NEAREST, span=ranked[0])
    if len(groups) >= 2 and all(distance(span) <= GROUP_LOOKBACK for span in resolution.candidates):
        # 여러 계층에 함께 걸린 항목이고 반복된 곳마다 그 계층 이름이 앞에 있음: 어느 곳이든 같은 조건이라 첫 위치를 씁니다
        # (실측: 대학생·청년 부분에 똑같이 있는 "③ 【완화조건】 소득요건 배제")
        return replace(resolution, status=QuoteStatus.CHOSEN_FIRST, span=resolution.candidates[0])
    return resolution


NEAR_MARGIN = 0.5  # 가장 가까운 후보가 두 번째보다 이 비율 이하로 가까워야 고릅니다


def choose_near(resolution: QuoteResolution, previous: tuple[int, int] | None) -> QuoteResolution:
    """위치를 못 정한(AMBIGUOUS) 인용을 같은 섹션 바로 앞 항목의 근거 위치에 가장 가까운 후보로 정합니다. 뚜렷하지 않으면 그대로 둡니다."""
    if resolution.status is not QuoteStatus.AMBIGUOUS or previous is None or len(resolution.candidates) < 2:
        return resolution
    ranked = sorted(resolution.candidates, key=lambda span: _distance(span, previous))
    first, second = _distance(ranked[0], previous), _distance(ranked[1], previous)
    # 거리가 같으면(예: 앞 항목 근거가 두 후보를 모두 덮어 둘 다 0) 고를 근거가 없으므로 AMBIGUOUS로 둡니다.
    # 예전엔 「0 <= 0 * 0.5」가 참이라 첫 후보를 골랐습니다(검토 2026-10-20)
    if first < second and first <= second * NEAR_MARGIN:
        return replace(resolution, status=QuoteStatus.CHOSEN_NEAREST, span=ranked[0])
    return resolution
