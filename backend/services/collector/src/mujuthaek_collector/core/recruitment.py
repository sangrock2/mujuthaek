"""Evidence that a source notice is accepting applications or scheduled to do so."""

from __future__ import annotations

import re
from datetime import date

_CLOSED = frozenset({"마감", "종료", "취소", "철회", "접수마감", "모집마감", "모집종료", "공고종료", "공고취소", "공고마감", "접수종료"})
_OPEN = frozenset({"접수중", "모집중", "청약중", "접수예정", "모집예정", "청약예정", "마감임박", "상시모집", "상시접수"})
_ROLLING = re.compile(
    r"상시\s*(?:(?:행복주택|국민임대|장기전세|영구임대|매입임대|공공임대|임대주택|입주자|예비입주자)\s*){0,4}"
    r"(?:모집|접수)"
)
_STOPPED_TITLE = re.compile(r"(?:모집|접수|공고)\s*(?:종료|마감\s*(?:안내|공지)|취소|철회)")
_LABEL = re.compile(r"(?:(?:청약\s*)?(?:신청|접수)|모집)\s*(?:기간|일정|일시|일자)")
_DATE = re.compile(
    r"(?<!\d)(?:[‘’']?(?P<year>20\d{2}|\d{2})\s*[년./-]\s*)?"
    r"(?P<month>\d{1,2})\s*[월./-]\s*(?P<day>\d{1,2})(?!\d)"
)
_RANGE = re.compile(r"(?:~|∼|～|–|—|부터)")


def normalize_status(status: str | None) -> str:
    return "".join((status or "").split())


def is_closed(status: str | None, deadline: date | None, today: date) -> bool:
    return normalize_status(status) in _CLOSED or (deadline is not None and deadline < today)


def confirmed(title: str, status: str | None, deadline: date | None, today: date) -> bool:
    if is_closed(status, deadline, today) or _STOPPED_TITLE.search(title):
        return False
    return deadline is not None or normalize_status(status) in _OPEN or bool(_ROLLING.search(title))


def _date(match: re.Match[str], year: int | None) -> date | None:
    if match["year"]:
        year = int(match["year"])
        if year < 100:
            year += 2000
    if year is None:
        return None
    try:
        return date(year, int(match["month"]), int(match["day"]))
    except ValueError:
        return None


def application_deadline(*texts: str | None) -> date | None:
    """Read dates next to application headings, excluding unrelated dates elsewhere in a document."""
    deadlines = []
    for text in texts:
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            label = _LABEL.match(line.lstrip("■□▪•- *"))
            if label is None:
                continue
            suffix = label.string[label.end() :].lstrip(" :：|")
            if not suffix and idx + 1 < len(lines):
                suffix = lines[idx + 1]
            if not (start_match := _DATE.match(suffix)) or (start := _date(start_match, None)) is None:
                continue
            if not (separator := _RANGE.search(suffix, start_match.end())):
                # A second date with no clear range delimiter is ambiguous.
                if not _DATE.search(suffix, start_match.end()):
                    deadlines.append(start)
                continue
            stop_match = _DATE.search(suffix, separator.end())
            if stop_match is None or (stop := _date(stop_match, start.year)) is None:
                continue
            if stop >= start:
                deadlines.append(stop)
            elif stop_match["year"] is None and start.month == 12 and stop.month == 1:
                deadlines.append(stop.replace(year=start.year + 1))
    return max(deadlines, default=None)
