"""판정 틀의 뜻 검사: JSON Schema로는 못 잡지만 판정 담당의 틀 읽기(FrameReader)가 틀 전체를 거절하는 경우.

- 최소가 최대보다 큰 범위(나이·매출·가산 조건 min·max), 시작이 끝보다 뒤인 날짜(개업일·폐업일)
- 공백뿐인 필수 글자(id·종류·대상군 이름·우대·길 이름·안내 글·질문). 스키마는 minLength 1만 봐서 「 」는 통과합니다
- 둘 다 비면 안 되는 칸, 같이 쓰면 안 되는 칸, 없는 대상군을 가리키는 groupId 같은 칸 사이 규칙

AI 값 하나가 틀어져 틀 전체를 못 읽게 되면 안 되므로(틀린 값이 누락보다 나쁨), 내보내기 전에 repair로 고칠 수 있는 것은
그 조건만 원문 질문(ASK, 확인 필요)으로 바꾸거나 빈 글자를 빼고, 그래도 남은 것은 frame_errors가 semantic_errors로 잡습니다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

INVERTED = "범위가 거꾸로입니다(최소가 최대보다 크거나 시작일이 끝일보다 뒤): 값을 쓰지 않고 원문을 질문으로 보냅니다"
NO_BOUND = "범위의 최소·최대가 둘 다 비어 값을 쓰지 않고 원문을 질문으로 보냅니다"
BLANK_QUESTION = "질문 문장이 비어 원문을 질문으로 보냅니다"
KIND_NAMES = {"AGE": "나이", "REVENUE": "매출", "BUSINESS_AGE": "업력", "CLOSURE": "폐업", "INCOME": "소득", "ASSET": "자산", "CAR": "자동차"}
# 범위 칸: (최소 칸, 최대 칸, 둘 다 비면 안 되는지, 날짜인지)
RANGES = {
    "AGE": ("minAge", "maxAge", True, False),
    "REVENUE": ("minWon", "maxWon", True, False),
    "BUSINESS_AGE": ("openedFrom", "openedTo", True, True),
    "CLOSURE": ("closedFrom", "closedTo", False, True),
}
STRING_LISTS = {"countryCodes": r"[A-Z]{2}", "regionCodes": r"\d{10}", "anyOf": r"[A-Z_]+", "codes": r"\d{2,5}", "maybeCodes": r"\d{2,5}"}


def _blank(value: Any) -> bool:
    return isinstance(value, str) and not value.strip()


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _inverted(low: Any, high: Any, dates: bool) -> bool:
    if dates:
        low, high = _day(low), _day(high)
        return low is not None and high is not None and low > high
    return _number(low) and _number(high) and low > high


def _whens(criterion: dict[str, Any]) -> list[dict[str, Any]]:
    """소득 가산(bonuses)·자산 한도 상향(overrides)의 조건(when)."""
    parts = [*(criterion.get("bonuses") or []), *(criterion.get("overrides") or [])]
    return [p["when"] for p in parts if isinstance(p, dict) and isinstance(p.get("when"), dict)]


def range_problem(criterion: dict[str, Any]) -> str | None:
    """조건의 범위 값이 틀 읽기에서 거절될 모양이면 그 이유(아니면 None)."""
    kind = criterion.get("kind")
    if kind in RANGES:
        low_key, high_key, need_one, dates = RANGES[kind]
        low, high = criterion.get(low_key), criterion.get(high_key)
        if need_one and low is None and high is None:
            return NO_BOUND
        if _inverted(low, high, dates):
            return INVERTED
    if any(_inverted(w.get("min"), w.get("max"), False) for w in _whens(criterion)):
        return INVERTED
    return None


def as_question(criterion: dict[str, Any], reason: str) -> dict[str, Any]:
    """틀 조건 하나 → 같은 ID·근거의 원문 질문(ASK, 확인 필요). 범위가 틀어진 조건을 확정 값 대신 사람이 보게 합니다."""
    quote = criterion.get("quote") if isinstance(criterion.get("quote"), str) and criterion["quote"].strip() else None
    name = KIND_NAMES.get(str(criterion.get("kind")), "")
    question = f"다음 조건에 해당하나요? 「{quote.strip()}」" if quote else f"공고 원문의 {name} 조건을 갖추었나요?".replace("  ", " ")
    reasons = [r for r in str(criterion.get("reviewReason") or "").split("; ") if r.strip()]
    made = {
        "id": criterion["id"],
        "kind": "ASK",
        "quote": quote,
        "page": criterion.get("page"),
        "inReview": True,
        "reviewReason": "; ".join(dict.fromkeys([*reasons, reason])),
    }
    if "asOf" in criterion:
        made["asOf"] = criterion["asOf"]
    return made | {"question": question, "metWhen": "YES"}


def _repair_criteria(criteria: list[Any]) -> list[Any]:
    out = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            out.append(criterion)
            continue
        for key in ("quote", "reviewReason"):
            if _blank(criterion.get(key)):
                criterion[key] = None
        problem = range_problem(criterion)
        if problem is not None and isinstance(criterion.get("id"), str) and criterion["id"].strip():
            criterion = as_question(criterion, problem)
        elif criterion.get("kind") == "ASK" and (criterion.get("question") is None or _blank(criterion.get("question"))):
            criterion = as_question(criterion, BLANK_QUESTION) | {"metWhen": criterion.get("metWhen") or "YES"}
        for n, option in enumerate(criterion.get("options") or [], start=1):
            if isinstance(option, dict):
                if _blank(option.get("label")):
                    option["label"] = f"{n}번째 길"
                option["criteria"] = _repair_criteria(option.get("criteria") or [])
        out.append(criterion)
    return out


def repair(frame: dict[str, Any] | None) -> dict[str, Any] | None:
    """내보내기 전 마지막 손질(제자리에서 고치고 같은 틀을 돌려줌): 거꾸로 된 범위·빈 질문 → 확인 필요 질문, 빈 이름 → 대신할 이름,
    빈 선택 글자(quote·reviewReason) → None, 글이 빈 안내 → 근거 문장으로(근거도 없으면 뺌)."""
    if frame is None:
        return None
    frame["common"] = _repair_criteria(frame.get("common") or [])
    for n, group in enumerate(frame.get("groups") or [], start=1):
        if _blank(group.get("name")):
            group["name"] = f"대상군 {n}"
        group["criteria"] = _repair_criteria(group.get("criteria") or [])
    for preference in frame.get("preferences") or []:
        for key in ("quote",):
            if _blank(preference.get(key)):
                preference[key] = None
        if _blank(preference.get("label")):
            preference["label"] = (preference.get("quote") or "우대").strip()[:80]
        preference["criteria"] = _repair_criteria(preference.get("criteria") or [])
    notes = []
    for item in frame.get("notes") or []:
        if _blank(item.get("quote")):
            item["quote"] = None
        if _blank(item.get("text")) or item.get("text") is None:
            if not item.get("quote"):
                continue
            item["text"] = item["quote"].strip()
        notes.append(item)
    frame["notes"] = notes
    return frame


# ── 검사(틀 읽기와 같은 규칙) ─────────────────────────────


def semantic_errors(frame: dict[str, Any]) -> list[str]:
    """틀 읽기(FrameReader)가 거절하는데 스키마로는 못 잡는 것. 값은 메시지에 넣지 않고 위치만 적습니다."""
    errors: list[str] = []

    def problem(at: str, what: str) -> None:
        errors.append(f"{at}: {what}")

    def required_text(node: dict[str, Any], key: str, at: str) -> None:
        if _blank(node.get(key)):
            problem(f"{at}/{key}", "공백뿐인 글자")

    for key in ("schema", "rawPolicyId", "rawPostId"):
        required_text(frame, key, "")
    groups = [g for g in frame.get("groups") or [] if isinstance(g, dict)]
    if not groups:
        problem("/groups", "대상군이 없음")
    group_ids = {g.get("id") for g in groups}

    def group_ref(node: dict[str, Any], at: str) -> None:
        if node.get("groupId") is not None and node.get("groupId") not in group_ids:
            problem(f"{at}/groupId", "없는 대상군")

    def when(node: dict[str, Any], at: str) -> None:
        factor, low, high = node.get("factor"), node.get("min"), node.get("max")
        if _inverted(low, high, False):
            problem(at, "min이 max보다 큼")
        newborn = factor == "NEWBORN_CHILDREN"
        if newborn and (node.get("since") is None or node.get("countRule") is None):
            problem(at, "출생 자녀는 since·countRule이 있어야 함")
        if not newborn and (node.get("since") is not None or node.get("countRule") is not None):
            problem(at, "since·countRule은 출생 자녀일 때만")
        if factor == "DUAL_INCOME" and (low is not None or high is not None):
            problem(at, "맞벌이는 min·max 없음")

    def criteria(nodes: Any, at: str, non_empty: bool) -> None:
        nodes = nodes if isinstance(nodes, list) else []
        if non_empty and not nodes:
            problem(at, "조건이 없음")
        for i, node in enumerate(nodes):
            if isinstance(node, dict):
                criterion(node, f"{at}/{i}")

    def criterion(node: dict[str, Any], at: str) -> None:
        required_text(node, "id", at)
        required_text(node, "kind", at)
        kind = node.get("kind")
        if kind in RANGES:
            low_key, high_key, need_one, dates = RANGES[kind]
            if need_one and node.get(low_key) is None and node.get(high_key) is None:
                problem(at, f"{low_key}·{high_key}가 둘 다 비어 있음")
            if _inverted(node.get(low_key), node.get(high_key), dates):
                problem(at, f"{low_key}가 {high_key}보다 큼")
        if kind == "CHILDREN" and node.get("minCount") is None and node.get("youngestMaxAge") is None:
            problem(at, "minCount·youngestMaxAge가 둘 다 비어 있음")
        if kind == "SAVINGS" and node.get("minBalanceWon") is not None and node.get("depositAreaM2") is not None:
            problem(at, "minBalanceWon과 depositAreaM2를 같이 씀")
        if kind == "BUSINESS_REGISTRATION" and node.get("closedWithinYears") is not None and node.get("require") != "CLOSED":
            problem(f"{at}/closedWithinYears", "폐업 기간은 CLOSED일 때만")
        if kind == "INDUSTRY" and node.get("revision") not in (10, 11):
            problem(f"{at}/revision", "차수는 10 또는 11")
        if kind == "INCOME":
            standard, year, percent = node.get("standard"), node.get("year"), node.get("percent")
            if standard is None and (year is not None or percent is not None):
                problem(at, "standard가 없으면 year·percent도 없어야 함")
            if standard is None and not node.get("printedTable"):
                problem(f"{at}/printedTable", "standard가 없으면 금액표가 있어야 함")
            if standard is not None and (year is None or percent is None):
                problem(at, "standard가 있으면 year·percent가 있어야 함")
            for i, bonus in enumerate(node.get("bonuses") or []):
                if isinstance(bonus, dict) and bonus.get("addPercent") is None:
                    problem(f"{at}/bonuses/{i}/addPercent", "값이 없음")
        for key in ("bonuses", "overrides"):
            for i, part in enumerate(node.get(key) or []):
                if isinstance(part, dict) and isinstance(part.get("when"), dict):
                    when(part["when"], f"{at}/{key}/{i}/when")
        if kind == "ASK":
            if node.get("question") is None or _blank(node.get("question")):
                problem(f"{at}/question", "공백뿐인 글자")
        for key, pattern in STRING_LISTS.items():
            values = node.get(key)
            if not isinstance(values, list) or (key == "anyOf" and kind not in ("STATUS", "EXCLUDED_STATUS")):
                continue
            if any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in values):
                problem(f"{at}/{key}", "형식이 맞지 않음")
            if len(set(map(str, values))) != len(values):
                problem(f"{at}/{key}", "같은 값이 두 번")
        if kind == "ANY_OF":
            options = [o for o in node.get("options") or [] if isinstance(o, dict)]
            if len(options) < 2:
                problem(f"{at}/options", "길이 둘 미만")
            for i, option in enumerate(options):
                required_text(option, "label", f"{at}/options/{i}")
                criteria(option.get("criteria"), f"{at}/options/{i}/criteria", True)

    criteria(frame.get("common"), "/common", False)
    for i, group in enumerate(groups):
        required_text(group, "id", f"/groups/{i}")
        required_text(group, "name", f"/groups/{i}")
        criteria(group.get("criteria"), f"/groups/{i}/criteria", False)
    for i, preference in enumerate(p for p in frame.get("preferences") or [] if isinstance(p, dict)):
        at = f"/preferences/{i}"
        required_text(preference, "id", at)
        required_text(preference, "label", at)
        group_ref(preference, at)
        if preference.get("points") is not None and preference.get("effect") != "BONUS_POINTS":
            problem(f"{at}/points", "점수는 가점일 때만")
        criteria(preference.get("criteria"), f"{at}/criteria", True)
    for i, item in enumerate(n for n in frame.get("notes") or [] if isinstance(n, dict)):
        required_text(item, "text", f"/notes/{i}")
        group_ref(item, f"/notes/{i}")
    return errors
