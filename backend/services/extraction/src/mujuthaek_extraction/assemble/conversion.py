"""전환안 방향을 숫자로 검산합니다(2026-10-24 세 번째 채점).

공급표 전환 칸의 부호 「(+)」「(-)」만 보고 보증금 증액·감액을 정하면, 원문 부호가 잘못 적힌 행(「(+)8,000 | 2,800 | 77,870」 —
기본 보증금 10,800보다 줄고 월세는 늘어난 감액안)이 증액안(CONVERSION_DEPOSIT_UP)으로 게시됩니다.
같은 공급 묶음·같은 대상의 기본(STANDARD) 요금과 전환안 금액을 비교해 방향을 정합니다:
- 보증금이 늘고 월세가 줄면 증액안(UP), 보증금이 줄고 월세가 늘면 감액안(DOWN)
- 기본·전환안 모두 보증금·월세가 있어야 하고 단위가 같아야 합니다. 둘이 같은 방향으로 움직이거나 그대로면 방향을 정할 수 없습니다(None)
- 비교할 기본 요금이 없거나 대상별 기본 요금이 둘 이상이면 검산하지 않습니다(UNCHECKED)
"""

from __future__ import annotations

import re
from typing import Any

UP, DOWN = "CONVERSION_DEPOSIT_UP", "CONVERSION_DEPOSIT_DOWN"
UNCHECKED = "UNCHECKED"
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _amount(price: dict[str, Any]) -> tuple[float, str] | None:
    """원문 금액의 숫자(부호·꼬리말 뺌)와 단위. 숫자가 하나가 아니면(범위·두 금액) None."""
    found = NUMBER.findall(str(price.get("sourceAmount") or ""))
    if len(found) != 1:
        return None
    return float(found[0].replace(",", "")), str(price.get("sourceUnit") or "")


def _pair(prices: list[dict[str, Any]]) -> dict[str, tuple[float, str]] | None:
    """요금안 하나의 보증금·월세. 같은 종류가 둘 이상이거나 하나라도 없으면 None."""
    out: dict[str, tuple[float, str]] = {}
    for price in prices:
        if price.get("kind") not in ("DEPOSIT", "MONTHLY_RENT"):
            continue
        amount = _amount(price)
        if amount is None or price["kind"] in out:
            return None
        out[price["kind"]] = amount
    return out if len(out) == 2 else None


def numeric_direction(base: dict[str, tuple[float, str]], plan: dict[str, tuple[float, str]]) -> str | None:
    """기본 요금 대비 전환안 방향. 단위가 다르거나 방향을 정할 수 없으면 None."""
    if any(base[kind][1] != plan[kind][1] for kind in ("DEPOSIT", "MONTHLY_RENT")):
        return None
    deposit = plan["DEPOSIT"][0] - base["DEPOSIT"][0]
    rent = plan["MONTHLY_RENT"][0] - base["MONTHLY_RENT"][0]
    if deposit > 0 and rent < 0:
        return UP
    if deposit < 0 and rent > 0:
        return DOWN
    return None


SAME_AS_BASE = "SAME_AS_BASE"


def plan_directions(prices: list[dict[str, Any]], fallback: list[dict[str, Any]] | None = None) -> dict[str, tuple[str, str | None]]:
    """공급 묶음 가격 → 전환안 요금안마다 (적힌 단계, 숫자로 본 방향 또는 None). 검산할 수 없는 요금안은 (단계, UNCHECKED).
    보증금·월세가 기본 요금과 똑같은 전환안은 (단계, SAME_AS_BASE): 전환이 없는 행의 기본 조건을 옮긴 것입니다(2026-10-24 네 번째 채점)."""
    plans: dict[str, list[dict[str, Any]]] = {}
    for price in prices:
        if isinstance(price, dict) and price.get("pricePlanId"):
            plans.setdefault(price["pricePlanId"], []).append(price)

    def targets(items: list[dict[str, Any]]) -> tuple[str, ...]:
        return tuple(sorted({t for p in items for t in (p.get("scope") or {}).get("targetGroups") or []}))

    def bases(source: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, ...], list[dict[str, tuple[float, str]]]]:
        # 기준 기본안은 보증금·월세가 모두 있는 STANDARD 요금안만(전세·분납처럼 월세가 없는 안은 빼요, 2026-10-24 다섯 번째 채점)
        out: dict[tuple[str, ...], list[dict[str, tuple[float, str]]]] = {}
        for items in source.values():
            pair = _pair(items) if all(p.get("priceStage") == "STANDARD" for p in items) else None
            if pair is not None and pair not in out.setdefault(targets(items), []):
                out[targets(items)].append(pair)
        return out

    standards = bases(plans)
    others: dict[str, list[dict[str, Any]]] = {}
    for price in fallback or []:
        if isinstance(price, dict) and price.get("pricePlanId"):
            others.setdefault(price["pricePlanId"], []).append(price)
    borrowed = bases(others)  # 묶음에 기본안이 없으면 같은 주택형 다른 묶음의 기본안과 비교합니다
    out: dict[str, tuple[str, str | None]] = {}
    for plan_id, items in plans.items():
        stages = {p.get("priceStage") for p in items}
        if len(stages) != 1 or next(iter(stages)) not in (UP, DOWN):
            continue
        stage = next(iter(stages))
        found = standards.get(targets(items)) or borrowed.get(targets(items)) or []
        own = _pair(items)
        if own is None or not found:
            out[plan_id] = (stage, UNCHECKED)
            continue
        if any(all(base[kind] == own[kind] for kind in ("DEPOSIT", "MONTHLY_RENT")) for base in found):
            out[plan_id] = (stage, SAME_AS_BASE)  # 기본안 어느 것과든 같으면 전환이 아닙니다
            continue
        out[plan_id] = (stage, numeric_direction(found[0], own) if len(found) == 1 else UNCHECKED)
    return out
