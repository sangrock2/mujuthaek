"""공급표 금액 빈칸 채우기(요구 2-06): 공급 묶음(주택형·호실)에 보증금·월임대료·분양가가 비면, 공고문 글(표 밖 문장)에서
그 주택형·호실 이름 가까이 적힌 금액을 코드가 찾아 채웁니다. AI를 다시 부르지 않습니다.

채우는 조건(틀린 값보다 빈 값):
- 묶음 이름(호실 unitLabel·주택형 housingTypeCode)이 공고 안에서 그 묶음에만 쓰이고, 이름이 나온 글 줄과 바로 이어지는 줄
  (빈 줄·표 행·다른 묶음 이름·새 절 머리 전까지, 최대 WINDOW_LINES줄)에서만 찾습니다. 표 행(| 줄)은 보지 않습니다(빈 칸의 표에서
  다른 칸 금액을 잘못 가져오지 않도록).
- 금액 낱말(보증금·월임대료·분양가) 바로 뒤에 단위(원·천원·만원·억)가 붙은 금액이 그 종류로 한 값만 있어야 합니다.
  단위 없는 숫자, 범위·한도(「이하」「최대」), 전환 금액, 입찰·계약 보증금, 낱말 사이에 다른 금액 낱말이 낀 금액
  (「보증금 및 월임대료 : …」), 금액 뒤에 다음 금액 낱말 전까지 금액이 또 있는 경우(「12,000천원(일반) 또는 9,000천원(청년)」),
  다른 묶음 이름과 한 줄에 있는 금액은 후보로 세되 쓰지 않습니다(그런 후보만 있으면 확인 필요).
- 계층·요금안별로 나뉜 가격이 이미 있는 묶음, AI가 「추후 안내」「별첨」「해당 없음」으로 비운 금액은 채우지 않습니다.
- 채운 금액은 원문 위치를 근거로 붙이므로, 다른 가격과 똑같이 검증(V9 값–인용 대조·단위 확인, V3 환산)을 거칩니다.
못 채우면 비워 두고 검수 이슈(SUPPLY_PRICE_MISSING, 그 묶음만 보류)를 남깁니다: 글에 후보가 있는데 하나로 정하지 못했을 때, 그리고
값 없는 가격 칸이 있거나 모집하는 묶음인데 다른 묶음에는 있는 금액이 비었고 AI가 「원문에 없음」으로 적지도 않았을 때입니다.
공고 전체에 금액이 없거나(별첨 등) 같은 이름의 다른 묶음에 금액이 있으면(수량 표·가격 표가 따로 묶임) 지금처럼 둡니다.
이 이슈는 AI 재확인으로 보내지 않습니다(recheck.NO_RECHECK_CODES).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mujuthaek_extraction.assemble.values import to_krw

ISSUE_CODE = "SUPPLY_PRICE_MISSING"
MAIN_KINDS = ("DEPOSIT", "MONTHLY_RENT", "SALE_PRICE")
KIND_WORDS = {
    "DEPOSIT": re.compile(r"(?:임대\s*)?보증금"),
    "MONTHLY_RENT": re.compile(r"월\s*(?:임대료|사용료|세(?!대))|임대료\s*\(\s*월\s*\)"),
    "SALE_PRICE": re.compile(r"분양\s*(?:가격|금액|가)|공급\s*(?:가격|금액)|매각\s*(?:예정\s*)?(?:가격|가)"),
}
KIND_NAMES = {"DEPOSIT": "보증금", "MONTHLY_RENT": "월임대료", "SALE_PRICE": "분양가"}
ANY_KIND_WORD = re.compile("|".join(p.pattern for p in KIND_WORDS.values()))
# 보증금이지만 가격이 아닌 것(입찰·계약·하자 보증금)과 전환 금액
NOT_PRICE_BEFORE = re.compile(r"(?:입찰|계약|하자|이행|낙찰|전환)\s*$")
# 낱말과 금액 사이(최대 12자): 숫자·줄바꿈·표 칸·「/」·「;」 없이
GAP = r"(?P<gap>[^\d\n|/;]{0,12}?)"
AMOUNT = re.compile(
    r"(?P<amount>\d[\d,]*(?:\.\d+)?\s*억(?:\s*\d[\d,]*\s*(?:천\s*)?만)?|\d[\d,]*(?:\.\d+)?)\s*(?P<unit>백\s*만\s*원|천\s*만\s*원|천\s*원|만\s*원|억\s*원|원)"
)
AFTER_WORD = re.compile(GAP + AMOUNT.pattern)  # 금액 낱말 바로 뒤의 금액
BARE_NUMBER = re.compile(GAP + r"\d")
# 금액 뒤에서 이 금액 설명이 끝나는 곳: 다른 금액 낱말(보증금·월임대료·분양가·관리비·계약금 등)이나 면적·기간 낱말
NEXT_WORD = re.compile(ANY_KIND_WORD.pattern + r"|관리비|계약금|중도금|잔금|부가(?:가치)?세|공용|전용|면적|기간|입찰|예정\s*가격")
UNCLEAR_GAP = re.compile(r"최대|최고|최저|한도|약|평균|전환|기준|합계|총")
UNCLEAR_TAIL = re.compile(r"\s*(?:이하|이내|미만|초과|이상|까지|한도|[~∼～〜]|-\s*\d|부터)")
# AI가 원문을 보고 비운 사유 중 채우지 않는 것: 추후 안내·별첨·해당 없음(「원문에 없음」은 표 칸이 빈 경우가 많아 글에서 찾아 봅니다)
KEEP_REASONS = {"TO_BE_ANNOUNCED", "SOURCE_ATTACHMENT_REQUIRED", "NOT_APPLICABLE"}
EXPLAINED_REASONS = {*KEEP_REASONS, "NOT_IN_SOURCE"}  # AI가 원문을 확인하고 비운 사유(못 채워도 새 검수 이슈를 만들지 않음)
WINDOW_LINES = 4  # 이름이 나온 줄 뒤로 더 볼 줄 수
NEW_SECTION = re.compile(r"^\s*(?:\d{1,2}\s*[.)]\s|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]|[■□◆◇▶])")
TABLE_AIDS = ("  [열 제목] ", "  ↳ ")  # 구조 방식이 표에 덧붙이는 줄(verify.consistency와 같음)


@dataclass
class Found:
    """한 종류의 금액 후보: 쓸 수 있는 값(원 단위 → (원문 금액, 단위, 근거 범위))과 쓰지 않은 후보 수."""

    values: dict[int, tuple[str, str, tuple[int, int]]] = field(default_factory=dict)
    unclear: int = 0


@dataclass
class FillResult:
    evidence: list[dict[str, Any]]  # 새로 만든 근거
    filled: list[str]  # 채운 칸(JSON Pointer)
    notes: list[str]
    issues: list[tuple[list[str | int], str, str]]  # (경로, 코드, 설명)


def _table_line(line: str) -> bool:
    return line.lstrip().startswith("|") or line.startswith(TABLE_AIDS)


def _label_pattern(label: str) -> re.Pattern[str]:
    core = r"\s*".join(re.escape(part) for part in label.split())
    if re.fullmatch(r"\d+", label):  # 숫자만인 이름은 「115호」「84형」처럼 붙어 나올 때만
        return re.compile(rf"(?<![\d,.])0*{core}\s*(?:호|형)")
    return re.compile(rf"(?<![0-9A-Za-z.,\-]){core}(?![0-9A-Za-z])")


def labels_of(group: dict[str, Any]) -> list[str]:
    return [str(v).strip() for v in (group.get("unitLabel"), group.get("housingTypeCode")) if isinstance(v, str) and v.strip()]


def _has_value(price: dict[str, Any]) -> bool:
    return price.get("amountKrw") is not None or price.get("amountRangeKrw") is not None


def _windows(text: str, label: str, others: list[re.Pattern[str]]) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]]]:
    """(쓸 범위들, 섞인 줄들). 쓸 범위는 이름이 나온 글 줄부터 이어지는 줄까지 (시작, 끝, 이름 위치)입니다.
    이름이 나온 줄에 다른 묶음 이름도 있으면 금액이 어느 묶음 것인지 정할 수 없어 그 줄은 쓰지 않고 섞인 줄로 돌려줍니다."""
    pattern = _label_pattern(label)
    lines, offset = [], 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1
    out, shared = [], []
    for i, (start, line) in enumerate(lines):
        match = pattern.search(line)
        if not match or _table_line(line):
            continue
        if any(o.search(line) for o in others):
            shared.append((start, start + len(line), start + match.start()))
            continue
        end = start + len(line)
        for nxt_start, nxt in lines[i + 1 : i + 1 + WINDOW_LINES]:
            if not nxt.strip() or _table_line(nxt) or NEW_SECTION.match(nxt) or pattern.search(nxt) or any(o.search(nxt) for o in others):
                break
            end = nxt_start + len(nxt)
        out.append((start, end, start + match.start()))
    return out, shared


def _amounts(text: str, span: tuple[int, int, int]) -> dict[str, Found]:
    start, end, label_at = span
    found = {kind: Found() for kind in MAIN_KINDS}
    piece = text[start:end]
    for kind, word in KIND_WORDS.items():
        for m in word.finditer(piece):
            amount = AFTER_WORD.match(piece, m.end())
            if amount is None:
                if BARE_NUMBER.match(piece, m.end()):
                    found[kind].unclear += 1  # 단위 없는 숫자(「보증금 12,000」): 단위를 짐작하지 않습니다
                continue
            gap = amount["gap"]
            if NOT_PRICE_BEFORE.search(piece[: m.start()][-6:]) or UNCLEAR_GAP.search(gap) or ANY_KIND_WORD.search(gap):
                found[kind].unclear += 1
                continue
            if UNCLEAR_TAIL.match(piece, amount.end()):
                found[kind].unclear += 1
                continue
            # 다음 금액 낱말 전까지 금액이 또 있으면(「보증금 12,000천원(일반) 또는 9,000천원(청년)」) 어느 것인지 정하지 않습니다
            rest = piece[amount.end() :]
            stop = NEXT_WORD.search(rest)
            if AMOUNT.search(rest[: stop.start() if stop else len(rest)]):
                found[kind].unclear += 1
                continue
            source, unit = amount["amount"].strip(), re.sub(r"\s+", "", amount["unit"])
            krw = to_krw(source, unit).amount_krw
            if krw is None or krw == 0:
                found[kind].unclear += 1
                continue
            # 근거: 이름이 같은 줄에 있으면 이름부터 금액 끝까지(한 줄), 아니면 금액 낱말부터
            first = start + m.start()
            same_line = "\n" not in text[label_at:first]
            quote_start = label_at if same_line and label_at <= first else first
            found[kind].values.setdefault(krw, (source, unit, (quote_start, start + amount.end())))
    return found


def _numbers(label: str) -> int | None:
    found = re.search(r"\d+(?:\.\d+)?", label)
    return int(float(found.group())) if found else None


def _explained(groups: list[dict[str, Any]], missing: dict[str, str], g: int) -> dict[str, str]:
    """AI 누락 기록이 이 묶음 가격에 적은 사유: 종류 → 사유. 묶음 전체·가격 전체를 가리키면 모든 종류."""
    prices = groups[g].get("prices") or []
    out: dict[str, str] = {}
    for target, reason in missing.items():
        parts = target.lstrip("/").split("/")
        if parts[:2] != ["supplyGroups", str(g)]:
            continue
        if len(parts) == 2 or (len(parts) == 3 and parts[2] == "prices"):
            out.update({kind: reason for kind in MAIN_KINDS})
        elif len(parts) >= 4 and parts[2] == "prices" and parts[3].isdigit() and int(parts[3]) < len(prices):
            out[prices[int(parts[3])]["kind"]] = reason
    return out


def fill_missing_prices(
    groups: list[dict[str, Any]], text: str, document_id: str, evidence: list[dict[str, Any]], missing: dict[str, str] | None = None
) -> FillResult:
    """groups를 그 자리에서 고칩니다. evidence는 지금까지의 근거(새 근거 ID를 겹치지 않게 짓는 데 씁니다),
    missing은 AI 누락 기록(항목을 뺀 뒤 경로 → 사유)입니다.
    - 「추후 안내」「별첨」「해당 없음」으로 적은 금액은 채우지 않습니다(AI가 원문을 보고 정한 것).
    - 「원문에 없음」(표 칸이 빔)은 글에서 찾아 채우고, 못 찾으면 그 기록을 그대로 둡니다."""
    result = FillResult([], [], [], [])
    missing = missing or {}
    used_ids = {e["id"] for e in evidence}
    label_count: dict[str, int] = {}
    for group in groups:
        for label in set(labels_of(group)):
            label_count[label] = label_count.get(label, 0) + 1
    # 가격만 따로 남은 묶음(수량 없음)의 주택형 번호: 같은 번호의 수량만 있는 묶음은 가격이 거기 따로 있으므로 빈칸으로 보지 않습니다
    # (V8 SUPPLY_PRICE_UNATTACHED와 같은 기준)
    priced_apart = {_numbers(label) for g in groups if g.get("prices") and not g.get("counts") for label in labels_of(g)} - {None}

    def new_evidence(span: tuple[int, int]) -> str:
        number = len(used_ids) + 1
        while f"ev-{number}" in used_ids:
            number += 1
        evidence_id = f"ev-{number}"
        used_ids.add(evidence_id)
        locator = {"kind": "TEXT_RANGE", "start": span[0], "end": span[1]}
        result.evidence.append({"id": evidence_id, "sourceId": document_id, "locator": locator, "quote": text[span[0] : span[1]]})
        return evidence_id

    for g, group in enumerate(groups):
        prices = group.get("prices") or []
        labels = labels_of(group)
        have = {p["kind"] for p in prices if _has_value(p)} & set(MAIN_KINDS)
        blank = {p["kind"] for p in prices if not _has_value(p) and p.get("sourceAmount") in (None, "")} & set(MAIN_KINDS)
        others_have = {
            p["kind"]
            for other in groups
            if other is not group and other.get("itemKind") == group.get("itemKind")
            for p in other.get("prices") or []
            if _has_value(p) and p["kind"] in MAIN_KINDS
        }
        # 같은 이름의 다른 묶음에 금액이 있으면(수량 표와 가격 표가 따로 묶임) 이 묶음의 빈칸이 아닙니다
        priced_twin = any(
            set(labels) & set(labels_of(other)) and any(_has_value(p) and p["kind"] in MAIN_KINDS for p in other.get("prices") or [])
            for other in groups
            if other is not group
        )
        if priced_twin or (not prices and group.get("counts") and any(_numbers(label) in priced_apart for label in labels)):
            continue
        explained = _explained(groups, missing, g)
        # 찾을 종류: 값 없는 가격 칸, 다른 묶음에 있는 종류(이 묶음에 금액이 하나도 없을 때), 공고 어디에도 금액이 없으면 세 종류 모두
        searched = blank | ((others_have if not have else set()) - have)
        if not prices and not others_have:
            searched = set(MAIN_KINDS)
        searched -= {kind for kind, reason in explained.items() if reason in KEEP_REASONS}
        if not searched:
            continue
        offered = group.get("itemKind") in ("HOUSING_UNIT", "BUSINESS_UNIT") or any(c.get("kind") == "OFFERED" for c in group.get("counts") or [])
        name = labels[0] if labels else group.get("id")
        unique = [label for label in labels if label_count.get(label) == 1]
        others = [_label_pattern(label) for other in groups if other is not group for label in labels_of(other) if label not in labels]
        spans, mixed = [], []
        for label in unique:
            found_spans, shared_lines = _windows(text, label, others)
            spans += found_spans
            mixed += shared_lines
        per_kind = {kind: Found() for kind in MAIN_KINDS}
        for span in spans:
            for kind, found in _amounts(text, span).items():
                per_kind[kind].unclear += found.unclear
                for krw, value in found.values.items():
                    per_kind[kind].values.setdefault(krw, value)
        for span in mixed:  # 다른 묶음 이름과 한 줄에 있는 금액은 쓰지 않고 확인 필요의 근거로만 셉니다
            for kind, found in _amounts(text, span).items():
                per_kind[kind].unclear += found.unclear + len(found.values)
        plans = {p.get("pricePlanId") for p in prices}
        stages = {p.get("priceStage") for p in prices if _has_value(p)}
        layered = any(p["scope"].get("targetGroups") for p in prices) or len(plans - {None}) > 1
        for kind in sorted(searched, key=MAIN_KINDS.index):
            found = per_kind[kind]
            word = KIND_NAMES[kind]
            reason = None
            if len(found.values) > 1:
                shown = ", ".join(f"{v[0]}{v[1]}" for v in list(found.values.values())[:3])
                reason = f"공고문 글에 {word} 후보 금액이 여럿이라 고르지 않았습니다({shown})"
            elif not found.values and found.unclear:
                reason = f"공고문 글의 {word} 금액이 범위·한도·단위 없는 숫자이거나 다른 묶음과 한 줄에 섞여 있어 쓰지 않았습니다"
            elif not found.values:
                reason = f"공고문 글에서 이 묶음의 {word} 금액을 찾지 못했습니다" if unique else "묶음 이름이 없거나 다른 묶음과 같아 글에서 찾을 수 없습니다"
            elif layered:
                reason = f"이 묶음 가격이 계층·요금안별로 나뉘어 있어 글의 {word} 하나를 어느 안에 넣을지 정할 수 없습니다"
            if reason is not None:
                # 확인 필요로 남기는 경우: 글에 후보가 있는데 고르지 못함, 또는 값 없는 가격 칸이나 (모집하는 묶음인데) 다른 묶음에는 있는 금액이
                # 비었고 AI도 「원문에 없음」으로 적지 않음. 공고 전체에 금액이 없거나(별첨) AI가 사유를 적은 빈칸은 지금처럼 둡니다
                evidence_seen = bool(found.values or found.unclear)
                unexplained = explained.get(kind) not in EXPLAINED_REASONS and (kind in blank or (not have and offered and kind in others_have))
                if evidence_seen or unexplained:
                    result.issues.append((["supplyGroups", g], ISSUE_CODE, f"「{name}」 {word}이(가) 비었습니다: {reason}. 원문 확인이 필요합니다"))
                continue
            [(krw, (source, unit, span))] = found.values.items()
            evidence_id = new_evidence(span)
            nulls = [p for p in prices if p["kind"] == kind and not _has_value(p) and p.get("sourceAmount") in (None, "")]
            if len(nulls) == 1:
                price, p = nulls[0], prices.index(nulls[0])
                price.update(sourceAmount=source, sourceUnit=unit, amountKrw=krw)
                price["evidenceIds"] = list(dict.fromkeys([*(price.get("evidenceIds") or []), evidence_id]))
            else:
                p = len(prices)
                price = {
                    "id": f"{group['id']}.text-{kind.lower().replace('_', '-')}",
                    "kind": kind,
                    "amountKrw": krw,
                    "scope": {
                        "level": "SUPPLY_GROUP",
                        "locationIds": [],
                        "supplyGroupIds": [group["id"]],
                        "targetGroups": [],
                        "supplyCategory": "ALL",
                        "resolution": "RESOLVED",
                        "description": f"공급표 금액이 비어 공고문 글에서 「{name}」의 {word}을(를) 찾아 채웠습니다.",
                    },
                    "sourceAmount": source,
                    "sourceUnit": unit,
                    "evidenceIds": [evidence_id],
                    "taxTreatment": "UNKNOWN",
                    "vatRate": None,
                    "billingPeriod": "MONTHLY" if kind == "MONTHLY_RENT" else "ONCE",
                    "pricePlanId": next(iter(plans - {None}), None),
                    "priceStage": next(iter(stages)) if len(stages) == 1 else None,
                }
                prices.append(price)
                group["prices"] = prices
            pointer = f"/supplyGroups/{g}/prices/{p}"
            result.filled += [pointer, f"{pointer}/sourceAmount", f"{pointer}/sourceUnit", f"{pointer}/amountKrw"]
            result.notes.append(f"{pointer}: 공급표에 「{name}」 {word}이(가) 비어 공고문 글 「{text[span[0] : span[1]][:60]}」에서 채웠습니다")
    return result
