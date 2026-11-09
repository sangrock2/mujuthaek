"""V3 수치 검산: 금액 단위 재계산, 가격안 섞임, collector 호별 표와의 대조.

수량 합계(TOTAL = 구성 합)는 계약 의미 검사(V1, COUNT_SUM_MISMATCH)가 확인하므로 여기서 다시 하지 않습니다.
호별 표는 collector 규칙으로 읽은 파생 자료라 어느 쪽이 맞는지 정하지 않고, 다르면 두 값을 함께 검수 이슈로 남깁니다.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby
from typing import Any

from mujuthaek_extraction.assemble.values import point_readings, to_krw
from mujuthaek_extraction.verify.model import Finding, SourceBundle

PLAN_KINDS = {"DEPOSIT", "MONTHLY_RENT", "ANNUAL_RENT"}


def _targets(price: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(price["scope"]["targetGroups"]))


def _same_number(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def check_numbers(candidate: dict[str, Any], sources: SourceBundle) -> list[Finding]:
    """공급 묶음마다 금액 환산을 다시 계산하고, 가격안 섞임과 호별 표와 다른 값을 V3 결과로 돌려줍니다."""
    findings: list[Finding] = []
    evidence = {e["id"]: e for e in candidate["evidence"]}

    def find(code: str, target: str, description: str) -> None:
        findings.append(Finding("V3", code, target, description))

    for g, group in enumerate(candidate["supplyGroups"]):
        prices = group["prices"]
        for p, price in enumerate(prices):
            if price["amountKrw"] is None:
                continue
            recomputed = to_krw(price["sourceAmount"], price["sourceUnit"]).amount_krw
            if recomputed is None and price["amountKrw"] in point_readings(price["sourceAmount"], price["sourceUnit"]):
                continue  # 모호한 「18,400.000」을 결합기가 같은 요금안의 합으로 정한 읽기(합이 맞는지는 V7 PRICE_PARTS_MISMATCH가 봄)
            if recomputed != price["amountKrw"]:
                find(
                    "PRICE_UNIT_MISMATCH",
                    f"/supplyGroups/{g}/prices/{p}/amountKrw",
                    f"원문 {price['sourceAmount']!r} {price['sourceUnit']!r}의 환산값({recomputed})과 다릅니다.",
                )

        # 대상 계층(순위·대학생 등)이 다른 가격은 전환안이 아니라 계층별 가격입니다(프롬프트 규칙).
        # 실측: 청년매입임대 "1순위 보증금 100만원 / 2·3순위 200만원"이 전환안 섞임으로 검수에 가던 것(일괄 8건)
        for _, same_targets in groupby(
            sorted((p for p in prices if p["kind"] in PLAN_KINDS), key=_targets),
            key=_targets,
        ):
            plan_prices = list(same_targets)
            plans = {p["pricePlanId"] for p in plan_prices}
            per_plan = Counter((p["pricePlanId"], p["kind"]) for p in plan_prices)
            if (len(plans) > 1 and None in plans) or any(n > 1 for n in per_plan.values()):
                find("PRICE_PLAN_MIXED", f"/supplyGroups/{g}/prices", "보증금·임대료 전환안이 구분되지 않아 다른 안의 금액이 섞였을 수 있습니다.")
                break
        # 분양가도 한 가격안·대상에 하나입니다. 둘이면 행마다 다른 안(기본형·마이너스옵션 등)이 한 안으로 합쳐진 것입니다
        # (2026-10-20 LH 대전대동2: 「구분」 칸을 안 이름으로 답하지 않으면 같은 층의 기본형·마이너스옵션 분양가가 한 안에 둘)
        sales = Counter((p["pricePlanId"], _targets(p)) for p in prices if p["kind"] == "SALE_PRICE")
        if any(n > 1 for n in sales.values()):
            find("PRICE_PLAN_MIXED", f"/supplyGroups/{g}/prices", "한 가격안에 분양가가 둘 이상이라 다른 안의 금액이 섞였을 수 있습니다.")

        for unit_doc, units in sources.units.items():
            for evidence_id in group["evidenceIds"]:
                item = evidence.get(evidence_id)
                if not item or item["sourceId"] != unit_doc or item["locator"]["kind"] != "UNIT_ROW":
                    continue
                try:
                    row = units[int(item["locator"]["pointer"].lstrip("/"))]
                except (ValueError, IndexError):
                    continue
                offered = [c["value"] for c in group["counts"] if c["kind"] == "OFFERED"]
                # 이 묶음 전체의 가격안으로 판단합니다. 예전엔 위 대상 계층 반복문에 남은 변수(plans)를 써서 다른 계층의 가격안과
                # 비교하거나, 가격안 가격이 없으면 정의되지 않은 변수로 멈췄습니다(검토 2026-10-16). 대상 계층별 가격은 호별 표와 비교하지 않습니다.
                group_plans = {p["pricePlanId"] for p in prices if p["kind"] in PLAN_KINDS}
                by_kind = {p["kind"]: p["amountKrw"] for p in prices if not p["scope"]["targetGroups"] and (p["pricePlanId"] is None or len(group_plans) == 1)}
                pairs = [
                    ("areaM2", group["exclusiveAreaSqm"], "전용면적"),
                    ("depositWon", by_kind.get("DEPOSIT"), "임대보증금"),
                    ("rentWon", by_kind.get("MONTHLY_RENT"), "월임대료"),
                    ("supplyCount", offered[0] if len(offered) == 1 else None, "공급 수"),
                ]
                for key, ours, label in pairs:
                    if key in row and ours is not None and not _same_number(row[key], ours):
                        find("UNITS_DISAGREE", f"/supplyGroups/{g}", f"{label}: 추출 {ours}, 수집기 호별 표 {row[key]} (어느 쪽이 맞는지 원문 확인 필요)")
    return findings
