"""일정의 접수 방법·장소·시각과 서류 묶음을 원문 근거로 확인합니다(프론트 요청 6-1~6-5, 2026-10-23).

AI가 적은 값은 그 항목의 근거 인용문(원문 글자)에서 확인될 때만 둡니다. 틀린 값보다 빈 값이 낫습니다.
- 접수 장소(places)·이메일(applicationEmail)·발급 기관(issuer): 근거에 그대로 있는 글자만(공백·표 칸 구분자는 무시). 아니면 null
  접수 장소·발급 기관·제출 부수는 인용문이 걸친 원문 **표 행 전체**(같은 행의 다른 칸)에서 찾습니다(2026-10-23: 설명 칸만 인용하고
  같은 행의 발급처 칸을 인용하지 않아 맞는 발급처가 지워졌음). 표 행이 아닌 글 줄은 인용문만 봅니다. 글자 그대로 있어야 하는 것은 같습니다.
  주소는 시도 이름의 정식 이름·약칭을 같게 봅니다(「충청남도」↔「충남」, regions.SIDO_NAMES)
- 이름·주소가 모두 비는 장소는 뺍니다(층·호만 남은 장소는 어디인지 알 수 없음)
- 접수 시각(dailyHours·breaks)·시각 설명(timeNote)·시작/끝 시각(startsAt·endsAt의 MINUTE): 근거에 그 시각이 있어야 합니다.
  아니면 칸을 비우고(시작/끝은 날짜만 남김) 표시 메모를 남깁니다
- 제외 요일(excludedDays): 근거에 그 요일 낱말이 있어야 합니다
- 신청 방법(channels): 근거에 그 방법의 낱말이 막는 말(불가·제외 등) 없이 있어야 합니다. AI가 비워 두었으면 신청·서류 제출 일정만
  근거 낱말로 정합니다(인터넷·온라인·홈페이지→ONLINE, 방문·현장·창구→ONSITE, 이메일→EMAIL, 우편·등기 우편→MAIL, 팩스→FAX)
- 제출 부수(copies): 근거에 「1부」「2통」처럼 그 수가 있어야 합니다
- 같은 이름·같은 묶음·같은 제출 시점의 서류는 하나로 합칩니다(근거·대상 범위를 합침). 부수·발급 기관은 둘 다 값이 있고 다를 때만 비웁니다
- 공고 전체 신청 방법(notice.applicationChannels)은 계약 검사기와 같은 규칙으로 프로그램이 계산합니다

지운 값의 메모 위치: 일정은 섹션(/schedules)을 가리킵니다. 일정 항목을 가리키는 메모는 그 일정을 접수 기간(applicationWindows)에서
빼므로(계약 application_items), 값을 비워 안전해진 일정까지 빠지지 않게 합니다. 서류는 그 항목을 가리킵니다.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from mujuthaek_extraction.assemble.quotes import normalize
from mujuthaek_extraction.assemble.regions import SIDO_NAMES
from mujuthaek_extraction.contracts import tools

CLEARED = "DETAIL_UNVERIFIED_CLEARED"
KST = timezone(timedelta(hours=9))

# 신청 방법 낱말. 이메일을 먼저 찾아 지운 뒤 우편을 찾습니다(「전자우편」이 우편으로 읽히지 않게)
CHANNEL_WORDS = (
    # 「메일로 송부」·전자우편 주소도 이메일입니다(2026-10-24 일곱 번째 채점: 「메일 (gh@…)로 송부」를 못 알아봄)
    ("EMAIL", re.compile(r"이\s*메일|e\s*-?\s*mail|전자\s*우편|(?<![가-힣])메일|[\w.+-]+@[\w-]+\.[\w.]+", re.IGNORECASE)),
    ("FAX", re.compile(r"팩스|팩시밀리|fax", re.IGNORECASE)),
    ("ONLINE", re.compile(r"인터넷|온라인|홈페이지|누리집|모바일|웹\s*사이트|on\s*-?\s*line", re.IGNORECASE)),
    ("ONSITE", re.compile(r"방문|현장|창구|내방")),
    # 「등기부등본」「등기사항증명서」는 서류 이름이라 등기 뒤에 우편·발송 낱말이 올 때만, 「우편번호」는 빼고
    ("MAIL", re.compile(r"우편(?!\s*번호)|등기\s*(?:우편|로|접수|발송|송부|제출)")),
)
# 낱말 바로 뒤(같은 구절 안)에 오면 그 방법을 막는 말
NEGATION = re.compile(r"^[^.。\n;:]{0,12}?(?:불가|안\s*됨|안\s*됩|받지\s*않|하지\s*않|않습니다|않음|불인정|제외|금지)")
# 막는 말 바로 뒤의 조건 말(「인터넷 접수가 불가능한 경우 방문」「우편 접수가 안 될 때」): 그 방법을 막은 것이 아니라 다른 방법의 조건입니다
CONDITION_AFTER = re.compile(r"^[^.。\n;:]{0,6}?(?:경우|때|시에|시\s)")
# 막는 말이 사람을 꾸미는 꼴(「인터넷 청약이 불가한 고령자·장애인은 창구에서」): 그 방법을 막은 것이 아니라 다른 방법을 쓸 대상입니다
# (2026-10-25 33번: AI 설명의 이 말 때문에 신청 일정 3개의 ONLINE이 지워져 「현장 접수만」으로 보임)
CONDITION_PERSON = re.compile(r"^(?:능)?한\s*(?:고령자|장애인|정보\s*취약|취약\s*계층|분|사람|신청자|대상자)")
# 「일반우편 접수 불가」는 일반 우편만 막고 등기 우편(MAIL)은 막지 않습니다(2026-10-24 세 번째 채점: 「방문 및 일반우편은 접수 불가」, 등기우편 접수)
GENERAL_MAIL = re.compile(r"일반\s*$")
APPLYING_KINDS = {"APPLICATION", "DOCUMENT_SUBMISSION"}
ONSITE_KINDS = {"CONTRACT", "VIEWING"}

# 시각: 「10:00」「10시」「10시 30분」「오후 6시」「6시 반」. 「24시간」「1시간」 같은 길이는 빼고, 「2026.10.」 뒤 숫자는 보지 않습니다
TIME = re.compile(r"(오전|오후|아침|낮|저녁|밤)?\s*(?<![\d.])(\d{1,2})\s*(?::\s*(\d{2})|시(?!\s*간)(?:\s*(\d{1,2})\s*분|\s*(반))?)")
EVENING = {"오후", "저녁", "밤"}
# 「12~13시」처럼 뒤 시각에만 「시」가 붙은 시 단위 범위의 앞 시각(2026-10-24 세 번째 채점: 「점심시간 12~13시 제외」의 12를 시각으로
# 읽지 못해 맞는 쉬는 시각 12:00~13:00이 지워짐). 「1~2시간」 같은 길이와 날짜(「10.12~13」) 뒤 숫자는 보지 않습니다
HOUR_RANGE_START = re.compile(r"(오전|오후|아침|낮|저녁|밤)?\s*(?<![\d.:])(\d{1,2})\s*(?=[~∼～〜\-–]\s*(?:오전|오후|아침|낮|저녁|밤)?\s*\d{1,2}\s*시(?!\s*간))")
DAY_WORDS = {
    "MON": "월",
    "TUE": "화",
    "WED": "수",
    "THU": "목",
    "FRI": "금",
    "SAT": "토",
    "SUN": "일",
}
HOLIDAY = re.compile(r"공휴일|휴일|국경일|명절|연휴")
WEEKEND = re.compile(r"주말")
# 「1부」「각 2통씩」「1매」. 「1부터」「제1장」은 아님
COPIES = re.compile(r"(?<![제\d])(\d{1,2})\s*(?:부|통|매|장)(?=$|[^가-힣]|씩|을|를|만|및|와|과|이|로)")


# 요일을 잇는 가운뎃점류: 「·」(U+00B7) 말고도 공고에 「․」(U+2024)「ㆍ」(U+318D)「・」(U+30FB)「‧」(U+2027)가 흔합니다
# (2026-10-24 채점: 「토․일요일」의 「토」를 못 찾아 맞는 제외 요일이 모두 지워졌음)
MIDDLE_DOTS = "·․ㆍ・‧"
DAY_JOINERS = rf"{MIDDLE_DOTS},/~∼\-、"


def _day_word(day: str) -> re.Pattern[str]:
    """요일 낱말: 「월요일」, 또는 한 글자 요일이 다른 요일·괄호와 붙어 있을 때(「(월)」「토·일」「토․일요일」). 「3월」「31일」「월 임대료」는 아님."""
    after, before = rf"[)）{DAY_JOINERS}]", rf"[(（{DAY_JOINERS}]"
    return re.compile(rf"{day}\s*요일|(?<![가-힣\d]){day}(?=\s*{after}|\s*$)|(?<={before}){day}(?![가-힣\d])|(?<={before}\s){day}(?![가-힣\d])")


DAY_PATTERNS = {code: _day_word(word) for code, word in DAY_WORDS.items()}


# 막는 말처럼 보이지만 방법을 막지 않는 꼴(2026-10-24 일곱 번째 채점): 괄호 안의 예외 대상(「우편접수만 가능 (고령자 제외)」), 앞에 「가능」이
# 있는 말, 시간·날 조건(「점심시간과 휴일에는 현장접수를 하지 않아요」 — 그 시간만 안 받음)
# 방법 전체가 아니라 그 일부(모바일 앱, 은행 창구)를 가리키는 낱말(2026-10-24 여덟 번째 채점: 「(※모바일청약 불가)」가 인터넷 접수 전체를,
# 특별공급의 「은행창구 접수 불가」가 방문 접수 전체를 막은 것으로 읽혀 맞는 ONLINE·ONSITE가 지워짐)
SUB_METHOD = re.compile(r"모바일|창구")
TIME_CONDITION = re.compile(r"점심|휴일|공휴일|주말|야간|토요일|일요일|시간\s*외")


def _not_a_block(text: str, start: int, between: str) -> bool:
    if "(" in between or "（" in between or "가능" in between:
        return True
    before = re.split(r"[.。\n;]", text[max(0, start - 20) : start])[-1]  # 같은 문장 안에서만 봅니다
    return bool(TIME_CONDITION.search(before))


def mentioned_channels(text: str) -> set[str]:
    """글에 낱말이 나온 방법(막는 말·조건 말과 함께여도)."""
    return {channel for channel, pattern in CHANNEL_WORDS if pattern.search(text)}


def channel_mentions(text: str) -> tuple[set[str], set[str]]:
    """글에서 찾은 신청 방법: (막는 말 없이 나온 방법, 막는 말과 함께 나온 방법).
    막는 말 뒤에 조건 말이 오면(「…불가한 경우」) 막은 것이 아니므로 그 낱말은 어느 쪽에도 넣지 않습니다.
    「일반우편 … 불가」는 등기 우편까지 막은 것이 아니라 MAIL을 막은 쪽에 넣지 않습니다."""
    positive: set[str] = set()
    negative: set[str] = set()
    for channel, pattern in CHANNEL_WORDS:
        for match in pattern.finditer(text):
            blocked = NEGATION.match(text[match.end() :])
            if blocked is not None and SUB_METHOD.fullmatch(match[0].strip()):
                continue  # 「(※모바일청약 불가)」「은행창구 접수 불가」는 그 방법의 일부만 막은 말입니다(인터넷·방문 전체를 막지 않음)
            if blocked is not None and _not_a_block(text, match.start(), text[match.end() : match.end() + blocked.end()]):
                positive.add(channel)  # 「우편접수만 가능 (고령자 제외)」「점심시간·휴일에는 현장접수 안 함」은 그 방법을 막은 말이 아닙니다
                continue
            if blocked is None:
                positive.add(channel)
            elif CONDITION_AFTER.match(rest := text[match.end() + blocked.end() :]) or CONDITION_PERSON.match(rest):
                continue
            elif not (channel == "MAIL" and GENERAL_MAIL.search(text[: match.start()])):
                negative.add(channel)
        text = pattern.sub(lambda m: " " * len(m[0]), text)
    return positive, negative


def ordered_channels(channels: set[str] | list[str]) -> list[str]:
    return [c for c in tools().APPLICATION_CHANNELS if c in set(channels)]


def channels_from_words(values: list[Any]) -> list[str]:
    """이전 v1의 자유 글자 신청 방법(「이메일」「방문접수」 등)을 정해진 값으로. 이미 정해진 값이면 그대로, 낱말이 없으면 버립니다."""
    found: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        if value in tools().APPLICATION_CHANNELS:
            found.add(value)
            continue
        positive, _ = channel_mentions(value)
        found |= positive
    return ordered_channels(found)


def _readings(marker: str | None, hour: int, minute: int) -> set[int] | None:
    """시각 하나로 읽을 수 있는 값들(자정부터 분). 시각이 아니면 None."""
    if hour > 24 or minute > 59 or (hour == 24 and minute):
        return None
    if marker in EVENING and hour < 12:
        return {(hour + 12) * 60 + minute}
    if marker:
        return {(0 if hour == 12 and marker in {"오전", "아침"} else hour) * 60 + minute}
    return {hour * 60 + minute, (hour + 12) * 60 + minute} if 1 <= hour < 12 else {hour * 60 + minute}


def time_tokens(text: str) -> list[set[int]]:
    """글에 적힌 시각마다 그 시각으로 읽을 수 있는 값들(자정부터 분), 글에 나온 순서대로.
    오전·오후 표시가 없는 1~11시는 오후일 수도 있어 둘 다 넣습니다(「6시」 = 06:00 또는 18:00).
    「12~13시」처럼 뒤에만 「시」가 붙은 범위의 앞 숫자도 시각(12:00)으로 읽습니다."""
    found: list[tuple[int, set[int]]] = []
    for match in TIME.finditer(text):
        readings = _readings(match[1], int(match[2]), int(match[3] or match[4] or (30 if match[5] else 0)))
        if readings is not None:
            found.append((match.start(), readings))
    for match in HOUR_RANGE_START.finditer(text):
        readings = _readings(match[1], int(match[2]), 0)
        if readings is not None:
            found.append((match.start(), readings))
    return [readings for _, readings in sorted(found, key=lambda item: item[0])]


def times_in(text: str) -> set[int]:
    """글에 적힌 시각으로 읽을 수 있는 모든 값(자정부터 분)."""
    return set().union(*time_tokens(text))


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


# 매일 같은 시각 창구가 아니라 이어지는 기간·밤낮 없는 접수를 말하는 낱말(2026-10-24 채점: 「야간(17:00~10:00)에도 청약 가능」인
# 신청 일정과 「10:00 ~ 23(금) 17:00」 연속 구간이 「매일 10~17시」로 읽힘). 이런 근거로는 dailyHours를 두지 않습니다
# 「(단, 시작일과 마감일 제외)」(2026-10-24 네 번째 채점): 첫날·마지막 날만 시각이 정해지고 가운데 날은 종일 받는 기간이라 매일 같은 시각이 아닙니다
CONTINUOUS_WORDS = re.compile(
    r"다음\s*날|익일|야간|24\s*시간|철야"
    r"|(?:시작|첫)\s*(?:일|날)\s*(?:과|와|및|[,·ㆍ])?\s*(?:마감|마지막|종료)\s*(?:일|날)?\s*(?:은|는)?\s*제외"
)
# 두 시각 사이의 글: 「~」「부터」로 이어지고(시각 없는) 짧은 글만 낀 경우
RANGE_GAP = re.compile(r"^\s*(?:[~∼～〜\-–]|부터|에서)\s*(?P<between>[^~∼～〜:\n]{0,24}?)\s*$")
# 두 시각 사이에 날짜가 끼면(「10:00 ~ 23(금) 17:00」「10.22.(목) 10:00 ~ 10.23.(금) 17:00」) 첫날 시작~마지막 날 끝의 연속 구간입니다
DATE_MARK = re.compile(r"\(\s*[월화수목금토일]\s*\)|\d{1,2}\s*일(?!\s*간)|\d{1,2}\s*월\s*\d|\d{1,2}\s*[./]\s*\d{1,2}")


def _time_windows(text: str) -> tuple[list[tuple[set[int], set[int]]], list[tuple[set[int], set[int]]]]:
    """글의 「시각 ~ 시각」 구간: (같은 날 구간들, 날짜가 끼어 이어지는 구간들). 구간마다 (시작으로 읽을 수 있는 값, 끝으로 읽을 수 있는 값)."""
    matches = [(m, time_tokens(m[0])) for m in TIME.finditer(text)]
    same: list[tuple[set[int], set[int]]] = []
    spanning: list[tuple[set[int], set[int]]] = []
    for (first, start), (second, end) in zip(matches, matches[1:], strict=False):
        gap = RANGE_GAP.match(text[first.end() : second.start()])
        if gap is None or not start or not end:
            continue
        (spanning if DATE_MARK.search(gap["between"]) else same).append((start[0], end[0]))
    return same, spanning


def continuous_hours(text: str, spans: list[dict[str, str]]) -> str | None:
    """dailyHours를 둘 수 없는 이유(없으면 None). 하루 안의 구간(시작 < 끝)이고, 근거가 이어지는 기간·야간·24시간 접수를 말하지 않으며,
    그 시각이 날짜가 낀 연속 구간(「10:00 ~ 23(금) 17:00」)으로만 적혀 있지 않아야 합니다."""
    if not spans:
        return None
    if any(_minutes(span["start"]) >= _minutes(span["end"]) for span in spans):
        return "끝 시각이 시작 시각보다 늦지 않아 하루 안의 접수 시각이 아니에요"
    word = CONTINUOUS_WORDS.search(text)
    if word:
        return f"근거가 「{word[0]}」 접수를 말해 매일 같은 시각에만 받는 것이 아니에요"
    same, spanning = _time_windows(text)
    for span in spans:
        start, end = _minutes(span["start"]), _minutes(span["end"])
        if any(start in a and end in b for a, b in spanning) and not any(start in a and end in b for a, b in same):
            return "그 시각이 첫날 시작~마지막 날 끝의 이어지는 기간으로만 적혀 있어요"
    return None


# 서류 표의 「필수/선택」 칸(2026-10-24 채점: 「공통/해당자」 묶음 제목 없이 「서류유형: 필수/선택」 칸만 있는 표의 서류가 모두 null).
# 칸 전체가 「필수」「선택」이거나 괄호 표시(「[필수]」)일 때만 봅니다. 「필수 선택 필수」처럼 한 칸에 몰린 깨진 행은 정하지 않습니다
REQUIRED_CELL = re.compile(r"^[\[［(（【]?\s*(필수|선택)\s*[\]］)）】]?$")
REQUIRED_TAG = re.compile(r"[\[［(（【]\s*(필수|선택)\s*[\]］)）】]")
REQUIRED_GROUPS = {"필수": "COMMON", "선택": "CONDITIONAL"}


# 「필수」「추가(선택·해당자)」 열에 ○ 표시를 하는 서류 표(2026-10-24 다섯 번째 채점: 「| ○ |  | 주민등록표초본 |」의 필수 ○를 두고
# 바로 위 등본 행의 「확인 불가 시 초본 추가 제출」 단서를 붙여 해당자 서류로 게시됨). 표 머리 행에서 열을 찾아 그 행의 표시를 읽습니다
MARK = re.compile(r"^[○◯●OoVv✓✔]$")
REQUIRED_HEAD = re.compile(r"^필수$")
OPTIONAL_HEAD = re.compile(r"^(?:선택|추가|해당자?|해당시)$")
CONFLICT = "DOCUMENT_GROUP_CONFLICT"


def _cells_of(line: str) -> list[str]:
    return ["".join(c.split()) for c in line.strip().strip("|").split("|")]


def marked_group(text: str, start: int) -> str | None:
    """원문 start가 든 표 행의 「필수」 열 ○ → COMMON, 「추가·선택·해당」 열 ○ → CONDITIONAL. 표 머리에 그 열이 없거나 둘 다·둘 다 아니면 None."""
    first = text.rfind("\n", 0, start) + 1
    end = text.find("\n", start)
    row = text[first : len(text) if end < 0 else end]
    if not row.lstrip().startswith("|"):
        return None
    cursor, header = first - 1, None
    while cursor > 0:  # 표의 첫 행(머리)까지 올라갑니다
        begin = text.rfind("\n", 0, cursor) + 1
        line = text[begin:cursor]
        if not line.lstrip().startswith("|"):
            break
        header, cursor = line, begin - 1
    if header is None:
        return None
    heads, cells = _cells_of(header), _cells_of(row)
    required = [i for i, h in enumerate(heads) if REQUIRED_HEAD.match(h)]
    optional = [i for i, h in enumerate(heads) if OPTIONAL_HEAD.match(h)]
    if len(required) != 1 or len(cells) != len(heads):
        return None
    on_required = bool(MARK.match(cells[required[0]]))
    on_optional = any(MARK.match(cells[i]) for i in optional)
    if on_required == on_optional:
        return None
    return "COMMON" if on_required else "CONDITIONAL"


# 대리 신청 서류 묶음(2026-10-24 다섯 번째 채점: 「본인 외(배우자 포함) 모두 대리」 서류 12개가 묶음 없이 게시됨). 배우자를 따로 나누지 않은
# 대리면 기타 대리(PROXY_OTHER)입니다
PROXY_WORD = re.compile(r"대리")
PROXY_ANY = re.compile(r"배우자\s*포함|본인\s*(?:외|이외)|제3자|직계")


def required_mark_group(text: str) -> str | None:
    """서류 근거(표 행 전체)의 「필수」→COMMON, 「선택」→CONDITIONAL. 두 표시가 섞이거나 없으면 None."""
    marks: set[str] = set()
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            marks |= {m[1] for m in (REQUIRED_CELL.match(c) for c in cells) if m}
            line = " ".join(c for c in cells if not REQUIRED_CELL.match(c))
        marks |= {m[1] for m in REQUIRED_TAG.finditer(line)}
    return REQUIRED_GROUPS[marks.pop()] if len(marks) == 1 else None


def _contains(text: str, value: Any) -> bool:
    return isinstance(value, str) and bool(normalize(value)) and normalize(value) in normalize(text)


# 시도 이름(긴 것부터): 주소 앞머리의 시도를 찾아 정식 이름·약칭을 바꿔 봅니다
_SIDO_PREFIXES = sorted(SIDO_NAMES, key=len, reverse=True)
TABLE_AIDS = ("  [열 제목] ", "  ↳ ")  # 구조 방식이 표에 덧붙이는 줄(verify.consistency와 같음)


def _address_found(text: str, address: Any) -> bool:
    """주소가 근거에 그대로 있는지. 시도 이름은 정식 이름·약칭 어느 쪽이든 같게 봅니다(「충남 아산시 …」 ↔ 「충청남도 아산시 …」).
    시도 뒤의 시군구·도로명·번지는 글자 그대로 있어야 합니다."""
    if _contains(text, address):
        return True
    if not isinstance(address, str):
        return False
    plain, haystack = normalize(address), normalize(text)
    sido = next((name for name in _SIDO_PREFIXES if plain.startswith(normalize(name))), None)
    if sido is None or len(plain) <= len(normalize(sido)):
        return False
    rest = plain[len(normalize(sido)) :]
    return any(normalize(same) + rest in haystack for same in SIDO_NAMES[sido] if same != sido)


def table_rows(text: str, start: int, end: int) -> str | None:
    """원문 [start, end) 범위가 걸친 줄들이 모두 표 행(| 줄, 표 읽기 도움 줄 포함)이면 그 줄들 전체, 아니면 None."""
    if not 0 <= start < end <= len(text):
        return None
    first = text.rfind("\n", 0, start) + 1
    last = text.find("\n", end - 1)
    lines = text[first : len(text) if last < 0 else last]
    rows = [line for line in lines.split("\n") if line.strip()]
    if not rows or not all(line.lstrip().startswith("|") or line.startswith(TABLE_AIDS) for line in rows):
        return None
    return lines


# 근거 인용 앞뒤 줄(2026-10-24 네 번째 채점: AI가 시각·발급처·장소 이름이 적힌 바로 옆 줄을 인용하지 않아 맞는 값이 지워짐 — 현장접수 시각,
# 줄이 깨진 서류 표의 발급처, 접수 장소 이름). 인용에서 확인하지 못한 값은 지우기 전에 인용 앞뒤 NEAR_LINES줄에서 한 번 더 찾습니다.
# 다른 일정·서류의 이름이 나오는 줄에서 멈추고(옆 항목의 값을 가져오지 않게), 시각은 그 줄들의 시각이 모두 이 일정의 시각일 때만 인정합니다
NEAR_LINES = 2
WEAK_EVIDENCE = {"EVIDENCE_SCATTERED", "EVIDENCE_AMBIGUOUS"}


def nearby_lines(text: str, start: int, end: int, stop: Any) -> str:
    """원문 [start, end)가 걸친 줄과 그 앞뒤 NEAR_LINES줄(빈 줄 제외). stop(줄)이 참인 줄에서 그쪽 방향을 멈춥니다(그 줄은 빼고)."""
    first = text.rfind("\n", 0, start) + 1
    last = text.find("\n", max(end - 1, start))
    last = len(text) if last < 0 else last
    before: list[str] = []
    cursor = first - 1
    while cursor > 0 and len(before) < NEAR_LINES:
        begin = text.rfind("\n", 0, cursor) + 1
        line = text[begin:cursor]
        cursor = begin - 1
        if not line.strip():
            continue
        if stop(line):
            break
        before.append(line)
    after: list[str] = []
    cursor = last + 1
    while cursor < len(text) and len(after) < NEAR_LINES:
        finish = text.find("\n", cursor)
        finish = len(text) if finish < 0 else finish
        line = text[cursor:finish]
        cursor = finish + 1
        if not line.strip():
            continue
        if stop(line):
            break
        after.append(line)
    return "\n".join([*reversed(before), text[first:last], *after])


def _evidence_texts(candidate: dict[str, Any]) -> dict[str, str]:
    return {e["id"]: e["quote"] for e in candidate.get("evidence") or []}


ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


# 서류 칸의 단서가 다른 서류를 이름으로 가리킴(2026-10-24 네 번째 채점: 개인정보 동의서 칸에 적힌 「주거급여수급자로 신청하는 경우에는
# ‘금융정보 등 제공 동의서’ 작성 제외」를 개인정보 동의서의 적용 대상에 붙여, 접수가 거부되는 서류를 수급자는 안 내도 되는 것처럼 보임).
# 적용 대상에 제외·면제를 적은 서류의 근거 행에서 제외 단서가 다른 서류의 이름을 말하면 그 서류를 확인 전까지 보류합니다
CLUE_FOR_OTHER = "DOCUMENT_CLUE_FOR_OTHER_DOCUMENT"
EXCLUSION_WORDS = re.compile(r"제외|면제|제출\s*하지\s*않|작성\s*하지\s*않|생략")
CLAUSE_BREAK = re.compile(r"[.。\n※•▪◦|]|(?<=[다음함])\s")
NAME_ASIDES = re.compile(r"\([^)]*\)|[‘’'\"“”「」『』]")


def _name_key(name: str) -> str:
    """서류 이름 비교 열쇠: 괄호 안 설명·따옴표를 빼고 정규화(「금융정보 등 (금융·신용·보험정보) 제공 동의서」 ↔ 「‘금융정보 등 제공 동의서’」)."""
    return normalize(NAME_ASIDES.sub("", name or ""))


def clue_for_other(document: dict[str, Any], text: str, others: list[str]) -> str | None:
    """적용 대상에 제외를 적은 서류의 근거 글에서, 제외 단서가 이 서류가 아닌 다른 서류의 이름을 말하면 그 이름."""
    if not EXCLUSION_WORDS.search(str(document.get("appliesTo") or "")):
        return None
    own = _name_key(str(document.get("name") or ""))
    keys = [(name, _name_key(name)) for name in others]
    keys = [(name, key) for name, key in keys if len(key) >= 4 and key not in own and own not in key]
    for clause in CLAUSE_BREAK.split(NAME_ASIDES.sub("", text)):
        if not EXCLUSION_WORDS.search(clause):
            continue
        flat = normalize(clause)
        if own and own in flat:
            continue
        named = next((name for name, key in keys if key in flat), None)
        if named:
            return named
    return None


# 날짜–장소 짝(2026-10-24 여섯 번째 채점: 한 표 칸에 「03.25.(수) (14:00~17:00) …주택계약실 | 03.26.(목) … 임대공급운영팀」처럼 날짜·장소가
# 여럿 섞여 3.25 계약 장소가 3.26 장소로 게시됨). 근거에서 그 일정 날짜 바로 뒤(다음 날짜·칸 구분 전까지)에 장소 낱말이 있는데 결과 장소의
# 이름 낱말이 그 안에 없고 다른 장소 낱말이 있으면 장소를 비웁니다(틀린 장소보다 빈 장소)
PLACE_WORD = re.compile(r"[가-힣A-Za-z0-9]+(?:실|팀|지사|센터|본부|사무소|사무실|관리소|접수처|주민센터|세대)")
DATE_TOKEN = re.compile(r"\d{1,4}\s*[./]\s*\d{1,2}\s*[./]\s*\d{1,2}|\d{1,2}\s*월\s*\d{1,2}\s*일")


def _date_forms(day: str) -> list[re.Pattern[str]]:
    year, month, date = (int(x) for x in day.split("-"))
    return [
        re.compile(rf"(?<!\d){month:02d}\s*[./]\s*{date:02d}(?!\d)"),
        re.compile(rf"(?<![\d.]){month}\s*[./]\s*{date}(?!\d)"),
        re.compile(rf"(?<!\d){month}\s*월\s*{date}\s*일"),
    ]


def place_pair_conflict(text: str, day: str, place: dict[str, Any]) -> str | None:
    """근거에서 그 날짜 바로 뒤에 적힌 장소가 결과 장소와 다르면 그 장소 글자. 확인할 수 없으면 None."""
    words = {w for key in ("name", "detail") for w in PLACE_WORD.findall(str(place.get(key) or ""))}
    if not words:
        return None
    for pattern in _date_forms(day):
        for found in pattern.finditer(text):
            rest = text[found.end() :]
            stop = min([m.start() for m in DATE_TOKEN.finditer(rest)] + [i for i in (rest.find("|"), rest.find("\n")) if i >= 0] + [len(rest)])
            segment = rest[:stop]
            there = set(PLACE_WORD.findall(segment))
            # 결과 장소 낱말 중 그 자리에 없는 것이 있고, 그 자리에 결과에 없는 다른 장소 낱말이 있으면 다른 장소입니다(같은 본부의 다른 실·팀)
            missing = [w for w in words if not any(w in t or t in w for t in there)]
            extra = [t for t in there if not any(w in t or t in w for w in words)]
            if there and missing and extra:
                return " ".join(sorted(extra))
    return None


def _place_found(place: dict[str, Any], key: str, text: str) -> bool:
    return _address_found(text, place[key]) if key == "address" else _contains(text, place[key])


def _minute_times(schedule: dict[str, Any]) -> set[int]:
    """시작·끝을 시각까지(MINUTE) 적었으면 그 시각들(분)."""
    times = set()
    for key in ("startsAt", "endsAt"):
        value = schedule.get(key)
        if isinstance(value, dict) and value.get("precision") == "MINUTE":
            try:
                moment = datetime.fromisoformat(value["value"]).astimezone(KST)
            except (TypeError, ValueError):
                continue
            times.add(moment.hour * 60 + moment.minute)
    return times


class _Checker:
    def __init__(self, candidate: dict[str, Any], text: str | None = None, text_source: str | None = None):
        self.candidate = candidate
        self.quotes = _evidence_texts(candidate)
        # 근거 id → 인용문이 걸친 원문 표 행 전체(표 행이 아니거나 원문을 모르면 인용문)
        self.rows: dict[str, str] = {}
        self.text = text or ""
        self.spans: dict[str, tuple[int, int]] = {}  # 근거 id → 원문 위치(앞뒤 줄 찾기)
        for evidence in candidate.get("evidence") or []:
            locator = evidence.get("locator") or {}
            expanded = None
            if text is not None and evidence.get("sourceId") == text_source and locator.get("kind") == "TEXT_RANGE":
                start, end = int(locator.get("start", -1)), int(locator.get("end", -1))
                expanded = table_rows(text, start, end)
                if 0 <= start < end <= len(text):
                    self.spans[evidence["id"]] = (start, end)
            self.rows[evidence["id"]] = expanded if expanded is not None else evidence["quote"]
        self.notes: list[str] = []

    def nearby(self, item: dict[str, Any], own: str, others: list[str], pointer: str) -> str:
        """항목 근거 인용의 앞뒤 줄. 다른 항목 이름(others, 이 항목 이름과 겹치는 이름은 빼고)이 나오는 줄에서 멈춥니다.
        근거 위치가 불확실한 항목(흩어진 낱말·여러 곳)은 앞뒤 줄도 믿을 수 없어 빈 글을 돌려줍니다."""
        for issue in self.candidate["quality"].get("reviewIssues") or []:
            target = str(issue.get("target") or "")
            if issue.get("code") in WEAK_EVIDENCE and (target == pointer or target.startswith(pointer + "/")):
                return ""
        mine = normalize(own or "")
        names = [n for n in (normalize(o or "") for o in others) if len(n) >= 3 and n not in mine and mine not in n]

        def stop(line: str) -> bool:
            flat = normalize(line)
            return any(n in flat for n in names)

        return "\n".join(nearby_lines(self.text, *self.spans[i], stop) for i in item.get("evidenceIds") or [] if i in self.spans)

    def found_nearby(self, label: str, target: str, what: str) -> None:
        self.notes.append(f"{target} {label}: {what} 근거 인용 앞뒤 줄에서 확인해 남겼어요")

    def cited(self, item: dict[str, Any], rows: bool = False) -> str:
        """항목의 근거 글. rows=True면 인용문이 걸친 원문 표 행 전체(같은 행의 다른 칸까지)."""
        source = self.rows if rows else self.quotes
        return "\n".join(source.get(i, "") for i in item.get("evidenceIds") or [])

    def clear(self, target: str, label: str, what: str) -> None:
        # 후보의 검수 이슈 목록에 바로 넣습니다. 서류를 합칠 때(_remove_merged) 위치가 함께 맞춰집니다
        self.candidate["quality"]["reviewIssues"].append(
            {"code": CLEARED, "target": target, "description": f"{label}: {what} 근거 인용문에서 확인하지 못해 비웠어요(원문 확인 필요)"}
        )

    # 일정
    def schedules(self) -> None:
        schedules = self.candidate.get("schedules") or []
        for s, schedule in enumerate(schedules):
            text = self.cited(schedule)
            label = f"{schedule.get('rawLabel') or schedule.get('id')}({schedule.get('id')})"
            others = [str(s.get("rawLabel") or "") for s in schedules if s is not schedule]
            near = self.nearby(schedule, str(schedule.get("rawLabel") or ""), others, f"/schedules/{s}")
            self.places(schedule, self.cited(schedule, rows=True), label, near)
            self.place_pairs(schedule, f"{self.cited(schedule, rows=True)}\n{near}", label)
            self.channels(schedule, text, label)
            self.email(schedule, text, label)
            self.hours(schedule, text, label, near)
            self.days(schedule, text, label)
            self.minute_bounds(schedule, text, label, near)

    def own_times(self, schedule: dict[str, Any]) -> set[int]:
        """이 일정이 적은 시각 전부(접수·쉬는 시각, 시작·끝 MINUTE)."""
        times = {_minutes(span[end]) for key in ("dailyHours", "breaks") for span in schedule.get(key) or [] for end in ("start", "end")}
        return times | _minute_times(schedule)

    def times_nearby(self, schedule: dict[str, Any], near: str, wanted: set[int]) -> bool:
        """찾는 시각이 앞뒤 줄에 모두 있고, 그 줄들의 시각이 모두 이 일정이 적은 시각일 때만 참(다른 일정 시각이 섞인 곳에서는 인정하지 않음)."""
        own = self.own_times(schedule)
        return bool(near) and wanted <= times_in(near) and all(token & own for token in time_tokens(near))

    def place_pairs(self, schedule: dict[str, Any], text: str, label: str) -> None:
        start = schedule.get("startsAt")
        if not isinstance(start, dict) or not ISO_DAY.match(str(start.get("value") or "")):
            return
        day = str(start["value"])[:10]
        kept = []
        for place in schedule.get("places") or []:
            other = place_pair_conflict(text, day, place)
            if other:
                self.clear("/schedules", label, f"접수 장소를(근거에서 그 날짜 옆 장소는 「{other}」)")
            else:
                kept.append(place)
        schedule["places"] = kept

    def channels(self, schedule: dict[str, Any], text: str, label: str) -> None:
        positive, negative = channel_mentions(f"{schedule.get('rawLabel') or ''}\n{text}")
        # 일정 설명·시각 설명(AI가 쓴 글)에서 막았다고 한 방법도 뺍니다. 빼는 데만 쓰고 더하는 데는 쓰지 않습니다
        _, said_blocked = channel_mentions(f"{schedule.get('description') or ''}\n{schedule.get('timeNote') or ''}")
        # 근거 어디서든 막은 방법(「방문 및 일반우편은 접수 불가」)은 다른 줄에 예외 상황으로 나와도(「시스템 장애 시 현장접수」) 그 일정의
        # 신청 방법이 아닙니다(2026-10-24 세 번째 채점: 서류제출 일정에 ONSITE가 남음). 예외 상황은 timeNote·설명에 적습니다
        blocked = negative | said_blocked
        given = list(schedule.get("channels") or [])
        if ONSITE_KINDS & set(schedule.get("kinds") or []) and schedule.get("places"):
            # 계약·열람처럼 그 장소에 가야 하는 일정은 근거로 확인한 장소가 있으면 방문 접수입니다(2026-10-24 여섯 번째 채점: 인용에 「방문」 낱말이
            # 없다고 계약 일정의 ONSITE를 지움). 위 장소 확인을 거친 뒤라 장소는 근거가 있는 값입니다
            positive = positive | {"ONSITE"}
        # 막는 말과만 나온 방법(「인터넷 신청 불가」)은 positive에 없습니다. 조건 말(「인터넷 청약이 불가한 경우」)로만 나온 방법은 막은 것이
        # 아니므로 AI가 적은 값을 둡니다(2026-10-24 여덟 번째 채점: 2순위 접수의 ONLINE이 지워짐)
        said = mentioned_channels(f"{schedule.get('rawLabel') or ''}\n{text}")
        kept = [c for c in given if (c in positive or c in said) and c not in blocked]
        if given and kept != given:
            dropped = ", ".join(c for c in given if c not in kept)
            self.clear("/schedules", label, f"신청 방법 {dropped}을(를)")
        if not given and APPLYING_KINDS & set(schedule.get("kinds") or []) and positive - blocked:
            kept = list(positive - blocked)
            self.notes.append(f"/schedules {label}: 신청 방법을 근거의 낱말로 정했어요({', '.join(ordered_channels(kept))})")
        schedule["channels"] = ordered_channels(kept)

    def places(self, schedule: dict[str, Any], text: str, label: str, near: str = "") -> None:
        kept = []
        for place in schedule.get("places") or []:
            cleared = [key for key in ("name", "address", "detail") if place.get(key) is not None and not _place_found(place, key, text)]
            for key in [k for k in cleared if near and _place_found(place, k, near)]:
                cleared.remove(key)
                self.found_nearby(label, "/schedules", f"접수 장소의 {key}를")
            for key in cleared:
                place[key] = None
            if cleared:
                self.clear("/schedules", label, f"접수 장소의 {'·'.join(cleared)}를")
            # 이름·주소가 둘 다 없으면 층·호(detail)만으로는 어디인지 알 수 없어 장소를 뺍니다
            if place.get("name") is not None or place.get("address") is not None:
                kept.append(place)
            elif place.get("detail") is not None:
                self.clear("/schedules", label, f"이름·주소 없이 층·호({place['detail']})만 남은 접수 장소를")
        schedule["places"] = kept

    def email(self, schedule: dict[str, Any], text: str, label: str) -> None:
        email = schedule.get("applicationEmail")
        if not isinstance(email, dict):
            return
        if not _contains(text.lower(), str(email.get("address") or "").lower()):
            schedule["applicationEmail"] = None
            self.clear("/schedules", label, "접수 이메일 주소를")
        elif email.get("subjectFormat") is not None and not _contains(text, email["subjectFormat"]):
            email["subjectFormat"] = None
            self.clear("/schedules", label, "이메일 제목 형식을")

    def hours(self, schedule: dict[str, Any], text: str, label: str, near: str = "") -> None:
        stated = times_in(text)
        for key, name in (("dailyHours", "접수 시각"), ("breaks", "쉬는 시각")):
            spans = schedule.get(key) or []
            missing = {_minutes(span[end]) for span in spans for end in ("start", "end")} - stated
            if missing and self.times_nearby(schedule, near, missing):
                self.found_nearby(label, "/schedules", f"{name}을")
                stated = stated | missing
            elif missing:
                schedule[key] = []
                self.clear("/schedules", label, f"{name}을")
        window = schedule.get("dailyHours") or []
        why = continuous_hours(text, window)
        if why:
            schedule["dailyHours"] = []
            self.candidate["quality"]["reviewIssues"].append(
                {"code": CLEARED, "target": "/schedules", "description": f"{label}: 접수 시각을 비웠어요 — {why}(원문 확인 필요)"}
            )
        self.window_bounds(schedule, window, label)
        note = schedule.get("timeNote")
        if isinstance(note, str) and any(not token & stated for token in time_tokens(note)):
            schedule["timeNote"] = None
            self.clear("/schedules", label, "시각 설명을")

    def window_bounds(self, schedule: dict[str, Any], window: list[dict[str, str]], label: str) -> None:
        """시작·끝을 날짜(DAY)로만 적고 시각을 접수 시각(dailyHours)에만 적은 일정: 근거로 확인한 접수 시각이 하나이면 첫날 시작 시각·
        마지막 날 끝 시각을 시작·끝(MINUTE)에 옮깁니다(2026-10-24 세 번째 채점: 「11.2.(월) ~ 11.4.(수) (10:00~16:00)」의 접수 시각을
        「24시간」 근거로 지운 뒤 시각이 어디에도 남지 않았음). 접수 시각을 지웠든 남겼든 같고, 끝이 시작보다 이른 구간(야간)은 옮기지 않습니다.
        window: 근거 시각 확인을 통과한 접수 시각(연속 구간이라 지우기 전)."""
        starts, ends = schedule.get("startsAt"), schedule.get("endsAt")
        if len(window) != 1 or not all(isinstance(v, dict) and v.get("precision") == "DAY" for v in (starts, ends)):
            return
        start, end = window[0]["start"], window[0]["end"]
        days = (str(starts["value"]), str(ends["value"]))
        if _minutes(start) >= _minutes(end) or not all(ISO_DAY.fullmatch(d) for d in days) or days[0] > days[1]:
            return
        schedule["startsAt"] = {"precision": "MINUTE", "value": f"{starts['value']}T{start}:00+09:00"}
        schedule["endsAt"] = {"precision": "MINUTE", "value": f"{ends['value']}T{end}:00+09:00"}
        self.notes.append(f"/schedules {label}: 근거의 접수 시각({start}~{end})으로 첫날 시작·마지막 날 끝 시각을 적었어요")

    def days(self, schedule: dict[str, Any], text: str, label: str) -> None:
        days = schedule.get("excludedDays") or []
        weekend = bool(WEEKEND.search(text))
        found = {code for code, pattern in DAY_PATTERNS.items() if pattern.search(text)}
        found |= {"SAT", "SUN"} if weekend else set()
        found |= {"HOLIDAY"} if HOLIDAY.search(text) else set()
        # 확인한 요일은 남기고 확인하지 못한 요일만 뺍니다(2026-10-24: 한 요일을 못 찾아 맞는 제외 요일까지 모두 지웠음)
        dropped = [day for day in days if day not in found]
        if dropped:
            schedule["excludedDays"] = [day for day in days if day in found]
            self.clear("/schedules", label, f"제외 요일 {', '.join(dropped)}을(를)")

    def minute_bounds(self, schedule: dict[str, Any], text: str, label: str, near: str = "") -> None:
        """시각까지 적은 시작·끝(MINUTE)의 시각이 근거에 없으면 날짜(DAY)만 남깁니다(앞뒤 줄에서 확인되면 남김). 날짜는 다른 검사(V9)가 따로 봅니다."""
        stated = times_in(text)
        missing = _minute_times(schedule) - stated
        if missing and self.times_nearby(schedule, near, missing):
            self.found_nearby(label, "/schedules", "시작·끝 시각을")
            stated = stated | missing
        for key in ("startsAt", "endsAt"):
            value = schedule.get(key)
            if not isinstance(value, dict) or value.get("precision") != "MINUTE":
                continue
            try:
                moment = datetime.fromisoformat(value["value"]).astimezone(KST)
            except (TypeError, ValueError):
                continue
            if moment.hour * 60 + moment.minute not in stated:
                schedule[key] = {"precision": "DAY", "value": moment.date().isoformat()}
                self.clear("/schedules", label, f"{'시작' if key == 'startsAt' else '끝'} 시각({moment:%H:%M})을")

    # 서류
    def documents(self) -> None:
        documents = self.candidate.get("requiredDocuments") or []
        for d, document in enumerate(documents):
            text = self.cited(document, rows=True)
            label = str(document.get("name") or document.get("id"))
            if document.get("group") is None:
                group = required_mark_group(text)
                if group is not None:
                    document["group"] = group
                    self.notes.append(f"/requiredDocuments/{d}: 서류 표의 「필수/선택」 칸으로 묶음을 {group}(으)로 정했어요({label})")
            marks = {marked_group(self.text, self.spans[i][0]) for i in document.get("evidenceIds") or [] if i in self.spans} - {None}
            if len(marks) == 1 and document.get("group") in (None, "COMMON", "CONDITIONAL"):
                mark = marks.pop()
                if document.get("group") is None:
                    document["group"] = mark
                    self.notes.append(f"/requiredDocuments/{d}: 서류 표의 필수·추가 열 표시로 묶음을 {mark}(으)로 정했어요({label})")
                elif document["group"] != mark:
                    # 표 표시와 AI 묶음이 다름: 표 표시를 따르고, 적용 대상도 다른 행 단서에서 왔을 수 있어 확인 전까지 보류합니다
                    document["group"] = mark
                    self.candidate["quality"]["reviewIssues"].append(
                        {
                            "code": CONFLICT,
                            "target": f"/requiredDocuments/{d}",
                            "description": f"{label}: 서류 표의 표시는 {mark}인데 다르게 읽어 적용 대상을 확인해야 해요(원문 확인 필요)",
                        }
                    )
            if document.get("group") is None and PROXY_WORD.search(f"{text} {document.get('appliesTo') or ''}"):
                if PROXY_ANY.search(f"{text} {document.get('appliesTo') or ''}"):
                    document["group"] = "PROXY_OTHER"
                    self.notes.append(f"/requiredDocuments/{d}: 배우자를 따로 나누지 않은 대리 서류라 기타 대리로 정했어요({label})")
            named = clue_for_other(document, text, [str(o.get("name") or "") for o in documents if o is not document])
            if named:
                self.candidate["quality"]["reviewIssues"].append(
                    {
                        "code": CLUE_FOR_OTHER,
                        "target": f"/requiredDocuments/{d}",
                        "description": f"{label}: 적용 대상의 제외 단서가 다른 서류(「{named}」)를 말하는 것 같아 확인 전까지 쓰지 않아요(원문 확인 필요)",
                    }
                )
            copies = document.get("copies")
            if copies is not None and copies not in {int(m[1]) for m in COPIES.finditer(text)}:
                document["copies"] = None
                self.clear(f"/requiredDocuments/{d}", label, "제출 부수를")
            if document.get("issuer") is not None and not _contains(text, document["issuer"]):
                others = [str(o.get("name") or "") for o in documents if o is not document]
                if _contains(self.nearby(document, label, others, f"/requiredDocuments/{d}"), document["issuer"]):
                    self.found_nearby(label, f"/requiredDocuments/{d}", "발급 기관을")
                else:
                    document["issuer"] = None
                    self.clear(f"/requiredDocuments/{d}", label, "발급 기관을")
        self.merge_documents()

    def merge_documents(self) -> None:
        documents = self.candidate.get("requiredDocuments") or []
        # 묶음이 빈 서류(원문 표에 묶음 표시가 없는 줄)는 같은 이름 서류가 한 묶음에만 있으면 그 묶음 서류와 같은 것으로 봅니다
        # (실측 2026-10-26 홍성·SH: 「본인(신청자) 신분증」이 공통 묶음과 묶음 없음으로 두 번)
        named_groups: dict[str, set[str]] = {}
        for document in documents:
            if document.get("group"):
                named_groups.setdefault(document_name_key(document.get("name")), set()).add(document["group"])

        def group_of(document: dict[str, Any]) -> Any:
            found = named_groups.get(document_name_key(document.get("name")), set())
            return document.get("group") or (next(iter(found)) if len(found) == 1 else None)

        # 제출 시점이 빈 서류(재확인 답 등)는 같은 이름·묶음 서류의 제출 시점이 하나뿐이면 그 서류와 같은 것으로 봅니다(2026-10-25 33번:
        # 잘린 응답 두 개와 재확인 답이 같은 서류 표를 「…제출 시」「…제출」「(빈칸)」으로 적어 같은 서류가 세 번 보임)
        times: dict[tuple, set[str]] = {}
        for document in documents:
            if document.get("submissionTime"):
                times.setdefault((document_name_key(document.get("name")), group_of(document)), set()).add(_time_key(document["submissionTime"]))
        first: dict[tuple, int] = {}
        index = 0
        while index < len(documents):
            document = documents[index]
            name_group = (document_name_key(document.get("name")), group_of(document))
            time = _time_key(document.get("submissionTime"))
            if not time and len(times.get(name_group, ())) == 1:
                time = next(iter(times[name_group]))
            key = (*name_group, time)
            kept = first.get(key)
            merged = _merge_document(documents[kept], document) if kept is not None else None
            if merged is None:
                first.setdefault(key, index)
                index += 1
                continue
            for key, what in (("copies", "부수를"), ("issuer", "발급 기관을")):
                if documents[kept].get(key) is not None and document.get(key) is not None and merged[key] is None:
                    self.clear(f"/requiredDocuments/{kept}", str(merged.get("name")), f"같은 서류를 합치며 값이 달라 {what}")
            merged["group"] = documents[kept].get("group") or document.get("group")
            documents[kept] = merged
            _remove_merged(self.candidate, "requiredDocuments", index, kept)
            self.notes.append(f"/requiredDocuments/{kept}: 같은 이름·묶음·제출 시점의 서류를 합쳤어요({merged['name']})")


# 같은 서류의 다른 표기(비교용으로만 맞추고 표시 이름은 그대로): 「주민등록표 등본」 = 「주민등록등본」
DOCUMENT_SPELLINGS = (("주민등록표등본", "주민등록등본"), ("주민등록표초본", "주민등록초본"), ("가족관계증명서(일반)", "가족관계증명서"))


def document_name_key(name: Any) -> str:
    """서류 이름 비교용 글: 띄어쓰기·괄호 종류를 맞추고 같은 서류의 다른 표기를 하나로."""
    key = normalize(str(name or "")).replace("[", "(").replace("]", ")").replace("〔", "(").replace("〕", ")")
    for spelled, same in DOCUMENT_SPELLINGS:
        key = key.replace(spelled, same)
    return key


def _time_key(value: Any) -> str:
    """서류 제출 시점 비교용 글: 띄어쓰기와 끝의 「시」「때」를 뺍니다(「당첨자 서류 제출 시」 = 「당첨자 서류 제출」)."""
    return re.sub(r"(?:시|때)$", "", normalize(str(value or "")))


def _join(a: Any, b: Any, sep: str) -> Any:
    if a == b or b is None:
        return a
    if a is None:
        return b
    return sep.join(dict.fromkeys([*str(a).split(sep), *str(b).split(sep)]))


def _merge_scope(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    """두 서류의 대상 범위를 합칩니다. 단계(공고·위치·공급 묶음)나 신규/재공급 구분이 다르면 합치지 않습니다(None)."""
    if a == b:
        return dict(a)
    if a["level"] != b["level"] or a["supplyCategory"] != b["supplyCategory"]:
        return None
    union = lambda x, y: list(dict.fromkeys([*x, *y]))  # noqa: E731
    return {
        "level": a["level"],
        "locationIds": union(a["locationIds"], b["locationIds"]),
        "supplyGroupIds": union(a["supplyGroupIds"], b["supplyGroupIds"]),
        # 대상 계층이 빈 범위는 모든 계층이라 합치면 모든 계층입니다
        "targetGroups": [] if not a["targetGroups"] or not b["targetGroups"] else union(a["targetGroups"], b["targetGroups"]),
        "supplyCategory": a["supplyCategory"],
        "resolution": "RESOLVED" if a["resolution"] == b["resolution"] == "RESOLVED" else "NEEDS_REVIEW",
        "description": _join(a["description"], b["description"], " / "),
    }


def _keep_one(a: Any, b: Any) -> Any:
    if a is None:
        return b
    if b is None or a == b:
        return a
    return None


def _merge_document(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    scope = _merge_scope(a["scope"], b["scope"])
    if scope is None:
        return None
    return {
        **a,
        "submissionTime": a.get("submissionTime") or b.get("submissionTime"),
        "scope": scope,
        "appliesTo": _join(a["appliesTo"], b["appliesTo"], ", "),
        "description": _join(a.get("description"), b.get("description"), " / "),
        # 부수·발급 기관은 둘 다 값이 있고 다를 때만 비웁니다(한쪽만 원문에 적힌 같은 서류의 값은 남김)
        "copies": _keep_one(a.get("copies"), b.get("copies")),
        "issuer": _keep_one(a.get("issuer"), b.get("issuer")),
        "evidenceIds": list(dict.fromkeys([*a["evidenceIds"], *b["evidenceIds"]])),
    }


def _remove_merged(candidate: dict[str, Any], section: str, index: int, into: int) -> None:
    """합쳐 없앤 항목을 빼고, quality의 위치 기록을 맞춥니다: 없앤 항목을 가리키던 기록은 합친 항목으로, 뒤 항목은 한 칸 앞으로."""
    del candidate[section][index]
    prefix = re.compile(rf"^/{re.escape(section)}/(\d+)(?=/|$)")
    quality = candidate["quality"]
    for collection in ("missingFields", "reviewIssues", "notes"):
        seen: set[str] = set()
        kept = []
        for entry in quality.get(collection) or []:
            match = prefix.match(entry["target"])
            if match:
                position = int(match[1])
                position = into if position == index else position - (position > index)
                entry["target"] = f"/{section}/{position}{entry['target'][match.end() :]}"
            if collection == "missingFields" and (entry["target"] in seen or _has_value(candidate, entry["target"])):
                continue  # 합친 항목의 같은 칸 누락 기록은 하나만, 합쳐서 값이 생긴 칸의 누락 기록은 뺌
            seen.add(entry["target"])
            kept.append(entry)
        quality[collection][:] = kept


def _has_value(candidate: dict[str, Any], pointer: str) -> bool:
    try:
        value = tools().resolve(candidate, pointer)
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return value is not None and value != []


def refresh_application_channels(candidate: dict[str, Any]) -> None:
    """공고 전체 신청 방법을 신청 일정에서 다시 계산합니다(계약 application_channels와 같은 규칙). 항목을 빼거나 고친 뒤 부릅니다."""
    if isinstance(candidate.get("notice"), dict) and isinstance(candidate.get("schedules"), list):
        try:
            candidate["notice"]["applicationChannels"] = tools().application_channels(candidate)
        except (KeyError, TypeError):
            return  # 형식이 깨진 후보는 계약 검사가 따로 알립니다


def check_details(candidate: dict[str, Any], text: str | None = None, text_source: str | None = None) -> list[str]:
    """결합한 후보의 일정·서류 세부 값을 근거로 확인하고(그 자리에서 고침) 공고 전체 신청 방법을 계산합니다.
    text·text_source: 원문 글과 그 문서 id(근거 위치 TEXT_RANGE가 가리키는 글). 주면 장소·발급 기관·부수를 인용문이 걸친 표 행 전체에서 찾습니다.
    지운 값은 후보의 검수 이슈(quality.reviewIssues, 검증기가 표시 메모로 옮김)에 넣고, 작업 메모를 돌려줍니다."""
    checker = _Checker(candidate, text, text_source)
    checker.schedules()
    checker.documents()
    refresh_application_channels(candidate)
    return checker.notes


SCHEDULE_DEFAULTS = {"places": [], "applicationEmail": None, "dailyHours": [], "breaks": [], "excludedDays": [], "timeNote": None}
DOCUMENT_DEFAULTS = {"group": None, "copies": None, "issuer": None}


def upgrade_stored(candidate: dict[str, Any]) -> dict[str, Any]:
    """2026-10-23 이전에 저장한 후보(검수 대기)를 새 계약 형식으로 옮깁니다. 이미 새 형식이면 바꾸지 않습니다(여러 번 불러도 같음).
    자유 글자 신청 방법은 낱말로 정해진 값으로 바꾸고(「서초구」처럼 방법이 아닌 글자는 버림), 새 칸은 빈 값으로 둡니다."""
    for schedule in candidate.get("schedules") or []:
        if not isinstance(schedule, dict):
            continue
        for key, value in SCHEDULE_DEFAULTS.items():
            schedule.setdefault(key, list(value) if isinstance(value, list) else value)
        if isinstance(schedule.get("channels"), list):
            schedule["channels"] = channels_from_words(schedule["channels"])
    for document in candidate.get("requiredDocuments") or []:
        if isinstance(document, dict):
            for key, value in DOCUMENT_DEFAULTS.items():
                document.setdefault(key, value)
    refresh_application_channels(candidate)
    return candidate
