"""정답표 채점 (회귀 시험, 유료 호출 없음). 정답표 형식: docs/extraction/answer-key-instructions.md

추출 결과(표준 공고 후보)를 정답표와 같은 중립 형식으로 바꾼 뒤 정답표끼리처럼 비교합니다.
같은 비교로 정답표 두 벌(예: 서로 다른 두 AI가 만든 것)이 서로 얼마나 같은지도 봅니다.

  # 추출 결과 채점: 정답표 폴더(<공고>/key.json) ↔ 추출 작업 폴더(<공고>/outcome.json)
  python scripts/score_answer_keys.py --keys <정답표 폴더> --outcomes <추출 폴더>
  # 정답표끼리 비교: 기준 정답표 ↔ 다른 정답표(<공고>/key.json 또는 <공고>.json)
  python scripts/score_answer_keys.py --keys <폴더 A> --other-keys <폴더 B>
  # 원문 확인 목록(정답표에 없지만 원문과 대조해 맞다고 확인한 자동 게시 값)도 함께
  python scripts/score_answer_keys.py --keys <정답표 폴더> --outcomes <추출 폴더> --verified <원문 확인 목록.json>

항목마다 "정답표에 있는 것 중 몇 개를 찾았나(재현율)"를 셉니다. 가격·서류는 "찾은 것 중 몇 개가 정답표에 있나(정밀도)"도 셉니다.
값이 같아도 뜻이 바뀐 것은 맞음으로 세지 않습니다: 자격 기준은 방향(이하·이상 …)과 대상 계층, 가격은 단지까지 봅니다.
한쪽에 그 칸이 없어 값만 보고 맞음으로 센 수는 「확인 못 한 차원」 줄로 따로 알립니다.
대상 계층 이름이 달라도(「청년」↔「3순위 19세 이상 39세 이하인 사람」) 원문이 같은 문장이면 같은 조건으로 세고 그 줄에 함께 알립니다.

  # 채점 스크립트 자체 시험
  python -m pytest scripts/test_score_answer_keys.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ATTRIBUTES = {
    "AGE": "AGE_YEARS",
    "INCOME_PERCENT": "INCOME_BENCHMARK_PERCENT",
    "INCOME_KRW": "MONTHLY_INCOME_KRW",
    "TOTAL_ASSETS": "TOTAL_ASSETS_KRW",
    "CAR_ASSETS": "CAR_ASSETS_KRW",
    "CHILDREN": "CHILD_COUNT",
    "HOMELESS": "HOMELESS",
}
CRITERION_OF = {v: k for k, v in ATTRIBUTES.items()} | {
    "HOUSEHOLD_MEMBER_COUNT": "HOUSEHOLD",
    "MARITAL_STATUS": "MARITAL",
    "RESIDENCE_REGION_CODE": "RESIDENCE",
}
PRICE_KINDS = {"DEPOSIT", "MONTHLY_RENT", "SALE_PRICE", "CONTRACT_PAYMENT", "BALANCE"}
# 정답표 지시문의 일정 종류. 계약에는 더 자세한 종류(DOCUMENT_REVIEW_RESULT 등)가 있어 그 밖의 것은 OTHER로 봅니다
SCHEDULE_KINDS = {"ANNOUNCEMENT", "APPLICATION", "DOCUMENT_SUBMISSION", "WINNER_ANNOUNCEMENT", "CONTRACT", "MOVE_IN", "OTHER"}
# 「배우자의 신분증」의 「의」(낱말 끝의 소유격만). 괄호 뒤도 봅니다: 「직계존속(피부양자)의 주민등록표초본」(괄호를 지우면 「직계존속의…」가 남았음)
POSSESSIVE = re.compile(r"(?<=[가-힣)\]])의\s")
DOC_NOISE = re.compile(r"\s|\(.*?\)|\[.*?\]|사본|원본|각?\s*\d+\s*부|1부|등\b|및|[·․‧∙･・ㆍ]|,|\.|'|\"")
# 같은 서류의 연도·한자 표기 차이(2026-11-07 23건 서류 「V1·V2 둘 다 놓침」 38개 중 다수가 이름 표기 차이): 「’22년」 = 「2022년」,
# 「2024년도」 = 「2024년」, 「통지서 內」 = 「통지서 내」
SHORT_YEAR = re.compile(r"[’'‘`]\s*(\d{2})\s*년")
YEAR_DO = re.compile(r"(\d{4})\s*년도")
# 정답표가 이름 없는 첨부 증빙을 상황 이름으로 적은 서류(「비상장주식 증빙」): 추출은 원문의 서류 이름(「증권사 조회내역」「주식보관증」)에
# 그 상황을 적용 대상(appliesTo, 「비상장주식을 자산으로 신고하는 경우」)으로 둡니다
SITUATION_EVIDENCE = re.compile(r"^(.+?)\s*증빙(?:\s*서류|\s*자료)?$")
DOC_SUFFIX = re.compile(r"(?:서|증|본|부|내역|자료|원|표|카드|명단)$")  # 서류 이름의 끝(증명서·등록증·등본·등기부·조회내역·신청원·통지표 등)
# 같은 증명서를 풀어 쓴 이름(2026-11-09 23건 서류 놓침 3개): 원문 「소득 신고한 사실이 없음을 확인하는 사실증명서」 = 정답표 「소득신고 사실
# 없음 사실증명서」. 공백을 지운 뒤 「…한 사실」은 「… 사실」로, 「사실이 없음을 확인하는」은 「사실 없음」으로 봅니다.
# 끝말 「확인서」와 「증명서」도 같은 서류로 봅니다(원문 「차상위계층 확인서」 = 정답표 「차상위계층 증명서」, gbdc-a909)
SPELLED_OUT = ((re.compile(r"한사실"), "사실"), (re.compile(r"(?<=사실)[이가]?없음을(?:확인|증명)하는"), "없음"), (re.compile(r"확인서"), "증명서"))


# ---------- 추출 결과 → 중립 형식 ----------


def _atoms(expression: Any):
    if isinstance(expression, dict):
        if expression.get("kind") == "ATOMIC":
            yield expression
        for child in expression.get("children") or []:
            yield from _atoms(child)


def _day(value: dict[str, str] | None) -> str | None:
    if not value:
        return None
    return value["value"][:7] if value.get("precision") == "MONTH" else value["value"][:10]


def _location_name(location: dict[str, Any]) -> str | None:
    """계약의 위치 이름 칸(complexName·buildingName). 예전 형식의 name도 받습니다(이 칸을 안 읽어 단지가 늘 비어 있었음)."""
    return location.get("complexName") or location.get("buildingName") or location.get("name")


def neutral_from_candidate(candidate: dict[str, Any], notice_id: str) -> dict[str, Any]:
    notice = candidate["notice"]
    locations = {loc["id"]: loc for loc in candidate["locations"]}
    # 예비입주자 모집 공고는 모집 수를 RESERVE로 적습니다. 정답표 지시문은 그 수를 offeredCount에 적게 해 같은 값으로 봅니다.
    # 공고의 대상 계층을 모두 덮는 수(대상이 「청년」뿐인 공고의 「청년 50명」)도 공고 전체 수입니다(2026-11-09 umca-4439)
    every = set(notice.get("targetGroups") or [])
    notice_counts = [c for c in notice.get("counts") or [] if not c["scope"]["targetGroups"] or every and every <= set(c["scope"]["targetGroups"])]
    offered = [c["value"] for c in notice_counts if c["kind"] == "OFFERED"]
    reserve = [c["value"] for c in notice_counts if c["kind"] == "RESERVE"]
    if len(offered) == 1 and len(reserve) == 1 and all(isinstance(v, int) for v in (*offered, *reserve)):
        # 즉시 입주자와 함께 뽑는 새 예비자(RESERVE)도 모집 수입니다. 정답표 채점 정책: 「거북이집 5명·17명은 즉시 입주와 공동 예비인원을
        # 합친 원문 수치」, 기존 대기자(WAITLIST)는 넣지 않음(2026-11-09 gndc 2건: 「모집인원 17명(우선 입주자 2명, 예비 입주자 15명)」)
        total = [offered[0] + reserve[0]]
    else:
        total = offered or [c["value"] for c in notice_counts if c["kind"] in ("RESERVE", "WAITLIST")]
    supply = []
    for group in candidate["supplyGroups"]:
        counts = {c["kind"]: c["value"] for c in group["counts"]}
        # 한 묶음에 같은 종류 수량이 여럿이면(우선공급 5·일반공급 28) 모두 봅니다. 사전에 담으면 마지막 값만 남습니다(인천석남 4행을 놓침으로 셈)
        offered_kind = next((k for k in ("OFFERED", "RESERVE", "WAITLIST") if k in counts), None)
        offered_values = [c["value"] for c in group["counts"] if c["kind"] == offered_kind]
        location = locations.get(group.get("locationId")) or {}
        supply.append(
            {
                "complex": _location_name(location),
                "type": group.get("housingTypeCode") or group.get("unitLabel"),
                "targetGroup": ", ".join(group["scope"]["targetGroups"]) or None,
                "exclusiveAreaSqm": group.get("exclusiveAreaSqm"),
                "areaRange": group.get("exclusiveAreaRange"),  # 「39.70 ~ 39.87」처럼 범위로만 적힌 면적(정답표는 끝값을 행마다 적음)
                "offeredCount": counts.get("OFFERED", counts.get("RESERVE", counts.get("WAITLIST"))),
                "offeredCounts": offered_values,
                "targetHousingCount": counts.get("TOTAL_HOUSING"),  # 대상 주택 수(정답표 지시문, 2026-10-17 사용자 결정: 모집 수와 따로)
                "reserveCount": counts.get("RESERVE") or counts.get("WAITLIST"),
                # 범위 가격(amountRangeKrw, 「44,000~51,000」)은 하한·상한 두 값으로 봅니다(정답표는 층별 하한·상한을 따로 적음)
                "prices": [
                    {
                        "kind": p["kind"] if p["kind"] in PRICE_KINDS else "OTHER",
                        "amountKrw": amount,
                        "plan": p.get("pricePlanId"),
                        "targetGroup": ", ".join(p["scope"]["targetGroups"]) or None,
                    }
                    for p in group["prices"]
                    for amount in (
                        [p["amountKrw"]] if p.get("amountKrw") is not None or not p.get("amountRangeKrw") else sorted(set(p["amountRangeKrw"].values()))
                    )
                ],
            }
        )
    schedules = [
        {
            "label": s["rawLabel"],
            "kind": kind if kind in SCHEDULE_KINDS else "OTHER",
            "start": _day(s["startsAt"]),
            "end": _day(s["endsAt"]) or _day(s["startsAt"]),  # 하루짜리 일정은 끝을 비워 둡니다. 정답표는 시작일을 다시 적습니다
            "rank": s.get("priorityRank"),
            "targetGroup": ", ".join(s["scope"]["targetGroups"]) or None,
        }
        for s in candidate["schedules"]
        for kind in s["kinds"]
    ]
    eligibility = []
    quote_of = {e["id"]: e.get("quote") or "" for e in candidate.get("evidence") or []}
    for item in candidate["eligibility"]:
        groups = ", ".join(item["scope"]["targetGroups"]) or None
        quotes = " ".join(quote_of.get(i, "") for i in item.get("evidenceIds") or [])
        atoms = [(atom, None) for atom in _atoms(item["rule"]["expression"])]
        for exception in item.get("exceptions") or []:
            # 예외의 기준값은 그 예외가 붙는 경우(「2023.3.28. 이후 출생 자녀 1인」「맞벌이」)를 condition에 남깁니다.
            # 정답표는 그런 경우를 targetGroup에 적기도 해서, 대상 계층 비교 때 이 글과도 맞춰 봅니다
            for atom in [*_atoms((exception.get("when") or {}).get("expression")), *_atoms(exception.get("effectExpression"))]:
                atoms.append((atom, " ".join(str(t) for t in (exception.get("description"), atom.get("basis")) if t)))
        for atom, condition in atoms:
            eligibility.append(
                {
                    "targetGroup": groups,
                    "criterion": CRITERION_OF.get(atom.get("attribute"), "OTHER"),
                    "operator": atom.get("operator"),
                    "value": atom.get("value"),
                    "text": item.get("originalText"),
                    "quotes": quotes,  # 근거 인용 글(가구원수별 금액 표 줄 등). 비율 기준과 금액 기준을 맞출 때만 봅니다
                    "category": item.get("category"),
                    "condition": condition,
                }
            )
        if not atoms:
            eligibility.append(
                {
                    "targetGroup": groups,
                    "criterion": "OTHER",
                    "operator": None,
                    "value": None,
                    "text": item.get("originalText"),
                    "category": item.get("category"),
                }
            )
    selection = [
        {"kind": r["kind"], "rank": r.get("priorityRank"), "points": r.get("points"), "text": r.get("originalText") or r.get("description")}
        for r in candidate["selectionRules"]
    ]
    documents = [{"name": d["name"], "appliesTo": d.get("appliesTo")} for d in candidate["requiredDocuments"]]
    # 전화가 있는 안내는 종류와 상관없이 문의처로 보고, 한 칸에 여러 번호(「051-810-1433, 051-810-1438」「☎ 064) 720-1035 ☎ 064) 720-3901」)는
    # 번호마다 나눕니다(정답표를 만든 AI마다 0/2·10/20으로 다르게 셌음)
    contacts = [{"name": g.get("title"), "phone": phone} for g in candidate.get("guidance") or [] if g.get("phone") for phone in _phones(g["phone"])]
    return {
        "noticeId": notice_id,
        "title": notice.get("title"),
        "announcedOn": notice.get("announcedOn"),
        "locations": [{"name": _location_name(loc), "address": loc.get("address"), "sigungu": loc.get("region")} for loc in candidate["locations"]],
        "totalOffered": total[0] if len(total) == 1 else None,
        "totalTargetHousing": next(iter([c["value"] for c in notice_counts if c["kind"] == "TOTAL_HOUSING"][:1]), None),
        "supplyTypes": supply,
        "schedules": schedules,
        "eligibility": eligibility,
        "selection": selection,
        "documents": documents,
        "contacts": contacts,
    }


# ---------- 비교 ----------


def _norm(text: Any) -> str:
    return re.sub(r"[\s()\[\],.·\-]", "", str(text or ""))


def _labels_overlap(a: Any, b: Any) -> bool:
    """일정 이름이 같은 일을 가리키는지: 괄호를 뺀 이름이 서로 포함되거나 두 글자 이상 낱말이 겹칩니다."""
    left, right = _norm(re.sub(r"\([^)]*\)", "", str(a or ""))), _norm(re.sub(r"\([^)]*\)", "", str(b or "")))
    if left and right and (left in right or right in left):
        return True
    words = lambda text: {w for w in re.split(r"[\s·,/()]+", str(text or "")) if len(w) >= 2}  # noqa: E731
    return bool(words(a) & words(b))


def _close(a: Any, b: Any, tolerance: float = 0.01) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


def _same_area(area: Any, row: dict[str, Any]) -> bool:
    """정답표 면적이 추출 행의 면적(범위로 적었으면 그 범위)과 같은지."""
    span = row.get("areaRange")
    if span and isinstance(area, int | float):
        return span["min"] - 0.01 <= area <= span["max"] + 0.01  # 범위로 적은 면적(실측 부산당감 39.70 ~ 39.87)
    return _close(area, row.get("exclusiveAreaSqm"))


PHONE = re.compile(r"(?:\d{2,4}\s*[)\-.]\s*)?\d{3,4}\s*-\s*\d{4}")


def _phones(text: Any) -> list[str]:
    """한 칸의 전화번호들. 번호 모양이 없으면 칸 전체를 한 번호로 봅니다."""
    found = PHONE.findall(str(text or ""))
    return found or ([str(text)] if _digits(text) else [])


def _digits(text: Any) -> str:
    return re.sub(r"\D", "", str(text or ""))


def _values(value: Any) -> list[float]:
    items = value if isinstance(value, list) else [value]
    return [float(v) for v in items if isinstance(v, int | float) and not isinstance(v, bool)]


# ---------- 뜻을 바꾸는 차원(방향·대상 계층·단지) ----------
# 값만 같고 뜻이 바뀐 결과(청년 「소득 100% 이하」 → 고령자 「소득 100% 이상」, A단지 보증금 → B단지)를 맞음으로 세지 않으려고 봅니다.
# 한쪽에 칸이 없으면(예전 정답표, 위치 없는 추출) 예전처럼 값만 비교하되 「확인 못 함」으로 따로 셉니다.

OPERATOR_ALIASES = {
    "LTE": "LTE", "이하": "LTE", "<=": "LTE", "≤": "LTE",
    "LT": "LT", "미만": "LT", "<": "LT",
    "GTE": "GTE", "이상": "GTE", ">=": "GTE", "≥": "GTE",
    "GT": "GT", "초과": "GT", ">": "GT",
    "EQ": "EQ", "=": "EQ", "==": "EQ", "같음": "EQ",
    "NE": "NE", "!=": "NE", "아님": "NE",
    "BETWEEN": "BETWEEN", "사이": "BETWEEN", "~": "BETWEEN",
}  # fmt: skip
# TRUE(「해당해야 함」)·IN 등은 숫자 기준의 방향이 아니어서 비교하지 않습니다(확인 못 함으로 셈)


def _operator(value: Any) -> str | None:
    text = str(value or "").strip()
    return OPERATOR_ALIASES.get(text.upper()) or OPERATOR_ALIASES.get(text)


# 대상 계층 이름에서 계층을 가리지 않는 말(「청년 계층」↔「고령자 계층」이 「계층」으로 겹쳐 같다고 보지 않게)
GROUP_NOISE = {"계층", "가구", "세대", "대상", "대상자", "공급", "특별공급", "일반공급", "우선공급", "유형", "등", "및", "자격", "신청자"}


def _group_parts(text: Any) -> list[str]:
    return [part.strip() for part in re.split(r"[,·/]|\s및\s", str(text or "")) if part.strip()]


CLAUSE = "가나다라마바사아자차카타파하"  # 법령 목 표시(가목·나목 …)
RANK_OR_CLAUSE = re.compile(rf"\d+순위|[{CLAUSE}]목|[{CLAUSE}]\.|「[{CLAUSE}]」")
# 계층이 아니라 조건을 가리는 낱말(정답표가 「출생자녀 1인」「소득 50%이하」「맞벌이」처럼 조건을 targetGroup에 적기도 함)
QUALIFIER = re.compile(r"\d|%|소득|자산|이하|이상|초과|미만|경우|출생|출산|맞벌이|외벌이|충족|기준|태아|이후|이전|^자녀")


# 낱말 끝 조사: 소유격 「의」와 「에서·에게·으로」(「아동복지시설에서 퇴소하는 사람」 ↔ 정답표 「아목 아동복지시설 퇴소자」, bmc-106)
PARTICLE = re.compile(r"(?<=[가-힣]{2})(?:에서|에게|으로|의)$")


def _words(part: str) -> set[str]:
    words = {PARTICLE.sub("", w) for w in re.split(r"[\s()~'‘’「」]+", part)}
    return {w for w in words if len(w) >= 2}


# 계층 이름에 흔한 말. 이것이 있거나 조건 낱말이 하나도 없으면 계층 이름으로 봅니다
POPULATION = (
    "청년", "대학생", "취업준비생", "고령자", "노인", "신혼부부", "한부모", "신생아", "다자녀", "장애인", "국가유공자", "수급자",
    "차상위", "북한이탈", "탈북", "주거급여", "노부모", "주거약자", "예술인", "중소기업", "산업단지", "아동", "철거민", "제대군인", "일반",
    "생애최초",  # 2026-11-09 jbdc-16011: 「생애최초 특별공급 / 추첨공급 / 외벌이」가 조건만 적은 이름으로 보여 「신혼부부」 기준과 짝지어졌음
)  # fmt: skip


def _names_population(text: Any) -> bool:
    """정답표 targetGroup이 계층 이름인지(「청년」「맞벌이 신혼부부」), 조건만 적은 것인지(「출생자녀 1인」「소득 50%이하 및 자산기준 충족」)."""
    text = str(text or "")
    if any(term in text for term in POPULATION):
        return True
    words = {w for part in _group_parts(text) for w in _words(part)} - GROUP_NOISE
    return bool(words) and not QUALIFIER.search(text)  # 「우선공급」처럼 일반 낱말뿐이면 계층 이름이 아님


def _condition_overlap(expected: Any, condition: Any) -> bool:
    """정답표 targetGroup이 예외 기준값이 붙는 경우의 글(「2023.3.28. 이후 출생 자녀가 1인 있으면 …」)과 같은 경우를 가리키는지: 낱말이 둘 이상 겹칩니다."""
    left = _words(str(expected or "")) - GROUP_NOISE
    shared = left & _words(str(condition or ""))
    return len(shared) >= 2 or bool(shared) and len(left) == 1


def _group_words(part: str) -> set[str]:
    """비교할 낱말. 소유격 「의」는 떼고(「노부모부양의」), 일반 낱말·순위·목 표시·조건 낱말은 빼고 봅니다
    (「청년 1순위」↔「고령자 1순위」, 「청년 소득 100% 이하」↔「고령자 소득 100% 이하」가 겹치지 않게).
    그것뿐인 이름(「일반공급」「출생자녀 1인」)은 그 낱말로 비교합니다."""
    words = _words(part)
    return {w for w in words if w not in GROUP_NOISE and not RANK_OR_CLAUSE.fullmatch(w) and not QUALIFIER.search(w)} or words


def _ranks(text: Any) -> set[str]:
    """「1순위」「1·2·3·4·5 순위」의 순위 숫자."""
    return {n for found in re.findall(r"((?:\d+\s*[·,]\s*)*\d+)\s*순위", str(text or "")) for n in re.findall(r"\d+", found)}


def _clauses(text: Any) -> set[str]:
    """법령 목 표시: 「나목·마목」「나. 국가유공자」「「나」 국가유공자」「일반입주자(차목)」 → 나·마·차."""
    text = str(text or "")
    return set(re.findall(rf"([{CLAUSE}])목", text)) | set(re.findall(rf"(?:^|[,·]\s*)([{CLAUSE}])\.\s", text)) | set(re.findall(rf"「([{CLAUSE}])」", text))


def _marks_only(text: Any, clauses: bool = False) -> bool:
    """순위 표시(clauses면 목 표시도) 말고는 계층을 가리는 낱말이 없는 이름(「1순위」「1·2·3 순위」「나목·마목」)."""
    rest = re.sub(r"(?:\d+\s*[·,]\s*)*\d+\s*순위", " ", str(text or ""))
    if clauses:
        rest = re.sub(rf"[{CLAUSE}]목|「[{CLAUSE}]」|(?:^|[,·]\s*)[{CLAUSE}]\.", " ", rest)
    return not {w for part in _group_parts(rest) for w in _words(part)} - GROUP_NOISE


def _groups_overlap(expected: Any, actual: Any) -> bool:
    """대상 계층이 같은 사람들을 가리키는지: 계층마다 괄호를 뺀 이름이 서로 포함되거나 계층을 가리는 낱말이 겹칩니다.
    법령 목 표시(「나목」↔「나. 국가유공자」)가 겹치면 같은 계층으로 봅니다(목 표시는 그 계층의 이름).
    순위(「1순위」↔「1·2·3 순위」)는 한쪽이 순위뿐일 때만 봅니다(「청년 1순위」↔「고령자 1순위」는 다른 계층)."""
    if _clauses(expected) & _clauses(actual):
        return True
    if _ranks(expected) & _ranks(actual) and (_marks_only(expected) or _marks_only(actual)):
        return True
    for left in _group_parts(expected):
        for right in _group_parts(actual):
            a = _norm(re.sub(r"\([^)]*\)", "", left))
            b = _norm(re.sub(r"\([^)]*\)", "", right))
            if a and b and (a in b or b in a) and (min(a, b, key=len) not in GROUP_NOISE or a == b):
                return True
            if _group_words(left) & _group_words(right):
                return True
            # 계층 낱말이 다른 말에 붙어 낱말로는 안 겹치는 같은 계층(정답표 「바목 등록장애인」 ↔ 추출 「장애인등록증이 교부된 자」,
            # 2026-11-09 bmc-72): 추출 쪽 계층 낱말이 모두 정답표 쪽에도 있으면 같은 계층입니다
            terms = _population_terms(b)
            if terms and terms <= _population_terms(a):
                return True
    return False


def _population_terms(text: str) -> set[str]:
    """이름 속 계층 낱말(POPULATION). 「일반」은 공급 단계 이름(「일반공급」)에도 흔해 빼고 봅니다."""
    return {term for term in POPULATION if term in text} - {"일반"}


def _complex_marks(text: str) -> set[str]:
    """단지를 가르는 표시: 숫자(「1단지」「101동」)와 로마자(「A단지」)."""
    return set(re.findall(r"\d+|[A-Za-z]+", text))


def _complex_variants(name: Any) -> set[str]:
    text = str(name or "")
    found = {_norm(text), _norm(re.sub(r"\([^)]*\)", "", text))} | {_norm(inner) for inner in re.findall(r"\(([^)]*)\)", text)}
    return {v.replace("@", "").upper() for v in found if len(v.replace("@", "")) >= 2}


def _same_complex(expected: Any, actual: Any) -> bool:
    """같은 단지인지: 이름(또는 괄호 안 이름)이 서로 포함되고, 단지를 가르는 숫자·로마자가 다르지 않습니다(「1단지」≠「11단지」, 「A단지」≠「B단지」)."""
    for a in _complex_variants(expected):
        for b in _complex_variants(actual):
            if a in b or b in a:
                left, right = _complex_marks(a), _complex_marks(b)
                if not left or not right or left == right:
                    return True
    return False


def _complex_relation(expected_rows: list[dict[str, Any]], actual_rows: list[dict[str, Any]]):
    """정답표 행 단지와 추출 행 단지의 관계를 돌려주는 함수: 같은 단지면 True, 다른 단지면 False, 알 수 없으면 None.

    알 수 없음: 한쪽 이름이 없거나, 두 쪽이 단지를 다른 단위로 적어 서로 대응하는 이름이 없을 때
    (정답표 「1동」「3동」 ↔ 추출 건물 「여기家」 하나, 정답표 「1차」「2차」 ↔ 추출 단지 하나). 이 경우 다른 단지라고 단정하지 않습니다.
    """
    expected_names = [r.get("complex") for r in expected_rows if r.get("complex")]
    actual_names = [a.get("complex") for a in actual_rows if a.get("complex")]

    def relation(expected_name: Any, actual_name: Any) -> bool | None:
        if not expected_name or not actual_name:
            return None
        if _same_complex(expected_name, actual_name):
            return True
        if any(_same_complex(name, actual_name) for name in expected_names) or any(_same_complex(expected_name, name) for name in actual_names):
            return False  # 이름은 서로 알아볼 수 있는데 다른 단지를 가리킴(A단지 ↔ B단지)
        return None

    return relation


def _match(edges: dict[int, list[int]], capacity: dict[int, int]) -> dict[int, int]:
    """기대 항목 → 추출 항목 짝짓기(증가 경로). 추출 항목 하나는 capacity만큼만 쓰입니다."""
    used: dict[int, list[int]] = {}
    pair: dict[int, int] = {}

    def place(e: int, seen: set[int]) -> bool:
        for a in edges.get(e, []):
            if a in seen:
                continue
            seen.add(a)
            holders = used.setdefault(a, [])
            if len(holders) < capacity.get(a, 1):
                holders.append(e)
                pair[e] = a
                return True
            for other in list(holders):
                if place(other, seen):
                    holders.remove(other)
                    holders.append(e)
                    pair[e] = a
                    return True
        return False

    for e in edges:
        place(e, set())
    return pair


class Score:
    def __init__(self) -> None:
        self.found: Counter[str] = Counter()
        self.total: Counter[str] = Counter()
        self.misses: dict[str, list[str]] = {}
        # 칸이 없어 보지 못한 차원: 섹션 → {차원: 수}. 맞음으로 센 것 중 그 차원을 확인하지 못한 수입니다
        self.unchecked: dict[str, Counter[str]] = {}
        # 정답표에 없지만 사람이 원문과 대조해 맞다고 확인한 값(원문 확인 목록): 섹션 → 수. 맞음으로 셉니다
        self.verified: Counter[str] = Counter()

    def check(self, section: str, ok: bool, label: str, unchecked: tuple[str, ...] = ()) -> None:
        self.total[section] += 1
        if ok:
            self.found[section] += 1
            for dimension in unchecked:
                self.unchecked.setdefault(section, Counter())[dimension] += 1
        else:
            self.misses.setdefault(section, []).append(label)

    def verify(self, section: str, labels: set[str]) -> None:
        """놓친 것 중 원문 확인 목록에 이름표가 글자 그대로 있는 것을 맞음으로 옮깁니다.
        값·대상·단지가 하나라도 바뀌면 이름표가 달라져 다시 후보로 남습니다."""
        misses = self.misses.get(section, [])
        kept = [label for label in misses if label not in labels]
        self.found[section] += len(misses) - len(kept)
        self.verified[section] += len(misses) - len(kept)
        if misses:
            self.misses[section] = kept

    def merge(self, other: Score, prefix: str = "") -> None:
        self.found.update(other.found)
        self.total.update(other.total)
        for section, labels in other.misses.items():
            self.misses.setdefault(section, []).extend(f"{prefix}{label}" for label in labels)
        for section, dims in other.unchecked.items():
            self.unchecked.setdefault(section, Counter()).update(dims)
        self.verified.update(other.verified)


def _text_tokens(text: Any) -> list[str]:
    """원문 비교용 낱말(한글·영문·숫자 두 글자 이상). 표 칸 구분(「|」)·괄호·기호는 버립니다."""
    return [w for w in re.findall(r"[가-힣A-Za-z0-9]+", str(text or "")) if len(w) >= 2]


def _same_source_text(expected: Any, actual: Any) -> bool:
    """정답표 원문(text)과 추출 원문이 같은 문장인지: 양쪽 낱말이 서로 60% 이상 겹칩니다(한쪽만 보면
    「전년도 도시근로자 가구원수별 가구당 월평균소득의 140%」 같은 상투 문구로 다른 계층의 문장도 겹침, 실측 전북 신생아 ↔ 생애최초).
    짧은 원문(낱말 4개 미만)은 흔한 말(「소득 100% 이하」)일 수 있어 보지 않습니다."""
    wanted, got = _text_tokens(expected), _text_tokens(actual)
    if len(wanted) < 4 or len(got) < 4:
        return False

    def covered(words: list[str], others: set[str]) -> float:
        return sum(w in others for w in words) / len(words)

    return covered(wanted, set(got)) >= 0.6 and covered(got, set(wanted)) >= 0.6


# 계층 이름은 아니지만 공급 종류를 가르는 이름. 원문이 같아도 추출이 정답표에 없는 이 이름을 적었으면 다른 조건으로 봅니다
SUPPLY_NAMES = ("생애최초", "노부모부양", "기관추천", "이전기관", "외국인", "특별공급", "일반공급", "우선공급", "추첨공급", "잔여공급")


def _key_ranks(rank: Any) -> set[str]:
    """정답표 rank 칸(3 또는 「3순위」「주거약자 1순위」)의 순위 숫자."""
    return set(re.findall(r"\d+", str(rank))) if rank not in (None, "") else set()


def _same_target_by_source(e: dict[str, Any], a: dict[str, Any]) -> bool:
    """대상 계층 이름이 겹치지 않아도 같은 조건임을 따로 보여 주는 근거가 있는지(기준·방향·값은 이미 같음).

    - 원문이 같은 문장이어야 합니다(정답표 「청년」 ↔ 추출 「3순위 19세 이상 39세 이하인 사람」, 원문은 「② 19세 이상 39세 이하인 사람 …」로 같음).
    - 추출 계층이 정답표에 없는 계층 이름(「고령자」「신혼부부」)을 적었으면 바뀐 계층으로 봅니다(한 원문이 두 계층을 함께 적은 표 칸 대비).
    - 정답표 순위와 추출 계층의 순위가 둘 다 있으면 같아야 합니다(「청년 3순위」 ↔ 「1순위 …」는 다른 조건).
    """
    group = str(a.get("targetGroup") or "")
    if any(term in group and term not in str(e.get("targetGroup") or "") for term in (*POPULATION, *SUPPLY_NAMES)):
        return False
    wanted, written = _key_ranks(e.get("rank")), _ranks(group)
    if wanted and written and not wanted & written:
        return False
    return _same_source_text(e.get("text"), a.get("text"))


def _eligibility_fit(e: dict[str, Any], a: dict[str, Any], criterion: str | None = None) -> tuple[str, ...] | None:
    """추출 기준 a가 정답표 기준 e와 같은 뜻인지. 다르면 None, 같으면 확인하지 못한 차원들(빈 튜플이면 모두 확인).

    - 방향: 양쪽 다 숫자 비교 연산자(이하·미만·이상·초과·같음·사이)면 같아야 합니다. 「이하」와 「미만」도 경계가 달라 다른 뜻으로 봅니다.
      다만 「0 이하」와 「0」은 같은 뜻입니다(채점하는 기준은 금액·비율·나이라 음수가 없음). 계약 속성 사전에 EQ가 없는 자동차가액은
      「자동차 없음」을 LTE 0으로 적습니다(2026-11-09 유료 확인 gh-809: 정답표 EQ 0 ↔ 추출 LTE 0이 틀린 값 후보로 세어졌음).
    - 대상 계층: 정답표가 계층을 적었고 추출에도 계층이 있으면 겹쳐야 합니다(정답표가 「모두」면 보지 않음).
    """
    if a.get("criterion") != (criterion or e.get("criterion")):
        return None
    unchecked = []
    left, right = _operator(e.get("operator")), _operator(a.get("operator"))
    if left and right:
        zero = {left, right} == {"LTE", "EQ"} and _values(e.get("value")) == [0] and _values(a.get("value")) == [0]
        if left != right and not zero:
            return None
    else:
        unchecked.append("방향(연산자)")
    if e.get("targetGroup"):
        if not (a.get("targetGroup") or a.get("condition")):
            unchecked.append("대상 계층")
        elif not (_groups_overlap(e["targetGroup"], a.get("targetGroup")) or _condition_overlap(e["targetGroup"], a.get("condition"))):
            # 계층도, 예외 기준값이 붙는 경우의 글도 겹치지 않음. 계층 이름끼리 다르면(「청년」↔「고령자」) 다른 뜻입니다.
            # 다만 정답표가 계층 대신 조건만 적었거나(「출생자녀 1인」) 추출이 순위로만 적었으면(「1순위」) 서로 견줄 수 없어 확인 못 함으로 셉니다
            group = a.get("targetGroup")
            if not _names_population(e["targetGroup"]):
                unchecked.append("대상 계층(정답표가 조건으로 적음)")
            elif group and _marks_only(group) and not _ranks(e["targetGroup"]):
                unchecked.append("대상 계층(순위·목 표시로만 적음)")  # 추출 「1순위」 ↔ 정답표 「장애인」
            elif group and _marks_only(e["targetGroup"], clauses=True) and not (_clauses(group) or _ranks(group)):
                unchecked.append("대상 계층(순위·목 표시로만 적음)")  # 정답표 「나목·마목」 ↔ 추출 「국가유공자 등, 북한이탈주민」
            elif _same_target_by_source(e, a):
                unchecked.append("대상 계층(다른 이름, 같은 원문)")  # 정답표 「청년」 ↔ 추출 「3순위 19세 이상 39세 이하인 사람」
            elif group and QUALIFIER.search(group) and not _names_population(group):
                # 추출이 계층 대신 조건을 이름으로 적음: 정답표 「연령 자격으로 신청」 ↔ 추출 「① 19세 이상 39세 이하인 사람」(2026-11-09 gbdc-a909).
                # 계층이 없는 추출 기준처럼 견줄 수 없어 확인 못 함으로 셉니다(「우선공급」처럼 조건 낱말도 없는 이름은 그대로 다른 뜻)
                unchecked.append("대상 계층(추출이 조건으로 적음)")
            else:
                return None
    return tuple(unchecked)


def _score_numeric_eligibility(score: Score, expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> None:
    """숫자 자격 기준(나이·소득·자산 등)을 기준·값·방향·대상 계층으로 맞춥니다.

    추출 기준 하나가 정답표 기준을 끝없이 채우지 않게 짝을 짓습니다: 계층이 적힌 추출 기준 하나는 그 계층 수만큼만 씁니다
    (「신혼부부」 기준 하나가 정답표의 「출생자녀 1인」「출생자녀 2인」 같은 값 두 행을 함께 채우지 않게).
    계층이 없는 추출 기준(모든 신청자에게 적용)은 정답표의 계층별 행 여럿과 짝지을 수 있되, 계층을 확인하지 못했으므로
    그 짝마다 「확인 못 함: 대상 계층」으로 셉니다(정답표 「일반공급 90%」「신혼부부 우선공급 90%」 ↔ 추출 「모두 90%」).
    정답표가 똑같은 기준(계층·기준·방향·값이 같음, 예: 순위만 다른 행)을 되풀이해 적은 것은 한 번 짝지어 같은 결과로 셉니다.
    """
    items = [e for e in expected if e.get("criterion") in ATTRIBUTES and _values(e.get("value"))]

    def signature(e: dict[str, Any]) -> tuple:
        return e.get("criterion"), _operator(e.get("operator")), tuple(_values(e.get("value"))), _norm(e.get("targetGroup"))

    unique: dict[tuple, dict[str, Any]] = {}
    for e in items:
        unique.setdefault(signature(e), e)
    keys = list(unique)
    edges: dict[int, list[int]] = {}
    gaps: dict[tuple[int, int], tuple[str, ...]] = {}
    for i, sig in enumerate(keys):
        e = unique[sig]
        wanted = _values(e["value"])
        for j, a in enumerate(actual):
            fit = _eligibility_fit(e, a)
            if fit is not None and all(any(_close(w, v, 0.001) for v in _values(a.get("value"))) for w in wanted):
                pass
            elif e["criterion"] == "INCOME_PERCENT" and len(wanted) == 1:
                # 「소득 120% 이하 | 1인 4,576,036원 …」처럼 가구원수별 금액으로 옮긴 기준도 같은 기준입니다(원문 비율이 근거에 있어야 함)
                percent = re.compile(rf"(?<![\d.]){wanted[0]:g}\s*(?:%|퍼센트)")
                fit = _eligibility_fit(e, a, "INCOME_KRW")
                if fit is None or not percent.search(str(a.get("text") or "")):
                    continue
            elif e["criterion"] == "INCOME_KRW" and len(wanted) == 1:
                # 반대 방향: 정답표는 금액(「1인 가구 4,576,000원 이하」), 추출은 비율(「120% 이하」)로 적은 같은 기준. 그 금액이 추출 기준의
                # 원문이나 근거 인용에 있어야 합니다(2026-11-09 sh-311005 표 줄 「4,576,000원이하 | 7,039,000원이하 …」, gndc-1239 「100%(3,018,496원)」)
                amount = re.compile(rf"(?<![\d,]){round(wanted[0]):,}\s*원")
                fit = _eligibility_fit(e, a, "INCOME_PERCENT")
                if fit is None or not amount.search(f"{a.get('text') or ''} {a.get('quotes') or ''}"):
                    continue
            else:
                continue
            edges.setdefault(i, []).append(j)
            gaps[(i, j)] = fit
    # 모든 차원을 확인한 짝을 먼저 고르도록 확인 못 한 차원이 적은 후보부터 둡니다
    for i, candidates in edges.items():
        candidates.sort(key=lambda j, i=i: len(gaps[(i, j)]))
    capacity = {j: len(_group_parts(a.get("targetGroup"))) or len(keys) for j, a in enumerate(actual)}
    pair = _match(edges, capacity)
    index = {sig: i for i, sig in enumerate(keys)}
    for e in items:
        i = index[signature(e)]
        label = f"{e.get('targetGroup') or '모두'} {e['criterion']} {_operator(e.get('operator')) or e.get('operator') or ''} {e.get('value')}"
        score.check(f"자격: {e['criterion']}", i in pair, label, gaps.get((i, pair[i]), ()) if i in pair else ())


def compare(expected: dict[str, Any], actual: dict[str, Any]) -> Score:
    score = Score()
    if expected.get("announcedOn"):
        score.check("공고일", str(actual.get("announcedOn") or "")[:10] == expected["announcedOn"][:10], expected["announcedOn"])

    # 주소는 괄호 설명(「(당감주공1단지)」「(당감4동)」)을 뺀 글자로도 비교합니다(실측 부산당감: 단지명이 주소 중간에 끼어 놓침으로 셈)
    def bare(text: Any) -> str:
        return _norm(re.sub(r"\([^)]*\)", "", str(text or "")))

    actual_addresses = [(_norm(loc.get("address")), bare(loc.get("address"))) for loc in actual.get("locations") or []]
    for loc in expected.get("locations") or []:
        address, plain = _norm(loc.get("address")), bare(loc.get("address"))
        if address:
            ok = any(a and (address in a or a in address) or (b and plain and (plain in b or b in plain)) for a, b in actual_addresses)
            score.check("위치 주소", ok, loc.get("address"))

    if isinstance(expected.get("totalOffered"), int):
        score.check("전체 모집 수", actual.get("totalOffered") == expected["totalOffered"], str(expected["totalOffered"]))
    if isinstance(expected.get("totalTargetHousing"), int):
        score.check("전체 대상 주택 수", actual.get("totalTargetHousing") == expected["totalTargetHousing"], str(expected["totalTargetHousing"]))

    actual_supply = actual.get("supplyTypes") or []
    same_area = _same_area

    for row in expected.get("supplyTypes") or []:
        label = f"{row.get('complex') or ''} {row.get('type') or ''} {row.get('targetGroup') or ''}".strip()
        if row.get("exclusiveAreaSqm") is not None:
            score.check("전용면적", any(same_area(row["exclusiveAreaSqm"], a) for a in actual_supply), f"{label} {row['exclusiveAreaSqm']}")
        if isinstance(row.get("offeredCount"), int):
            in_area = [a for a in actual_supply if same_area(row.get("exclusiveAreaSqm"), a)] or actual_supply
            score.check(
                "모집 수(행)",
                any(row["offeredCount"] in (a.get("offeredCounts") or [a.get("offeredCount")]) for a in in_area),
                f"{label} {row['offeredCount']}",
            )
        if isinstance(row.get("targetHousingCount"), int):
            in_area = [a for a in actual_supply if same_area(row.get("exclusiveAreaSqm"), a)] or actual_supply
            score.check(
                "대상 주택 수(행)", any(a.get("targetHousingCount") == row["targetHousingCount"] for a in in_area), f"{label} {row['targetHousingCount']}"
            )

    # 가격은 정답표의 행마다, 같은 단지·같은 주택형 코드의 추출 행들에서 찾습니다(코드가 맞는 행이 없으면 같은 단지의 모든 행에서).
    # 정답표와 추출 모두 단지 이름이 있으면 다른 단지의 행은 보지 않습니다(A단지 59A 보증금을 B단지 59A 행에 적으면 틀림).
    # 한쪽에 단지 이름이 없으면 예전처럼 모든 행에서 찾고 「확인 못 함: 단지」로 셉니다.
    # 추출 금액 하나가 정답표 여러 행을 채우는 것은 그대로 둡니다: 정답표가 같은 금액을 우선공급·일반공급 행에 되풀이해 적기 때문입니다
    # (금액 개수로 세던 방식은 인천석남에서 그 되풀이 64개를 놓침으로 셈). 단지 확인이 다른 단지로 새는 것을 막습니다.
    def _amounts(row: dict[str, Any]) -> set[tuple[str, int]]:
        return {(p["kind"], p["amountKrw"]) for p in row.get("prices") or [] if p.get("kind") in PRICE_KINDS and isinstance(p.get("amountKrw"), int)}

    expected_rows = expected.get("supplyTypes") or []
    _complex_ok = _complex_relation(expected_rows, actual_supply)
    for row in expected_rows:
        code = _norm(row.get("type")).upper()
        compatible = [a for a in actual_supply if _complex_ok(row.get("complex"), a.get("complex")) is not False]
        same_type = [a for a in compatible if code and _norm(a.get("type")).upper() == code]
        pool = same_type or compatible
        for p in row.get("prices") or []:
            if p.get("kind") in PRICE_KINDS and isinstance(p.get("amountKrw"), int):
                wanted = (p["kind"], p["amountKrw"])
                hits = [a for a in pool if wanted in _amounts(a)]
                unchecked = () if any(_complex_ok(row.get("complex"), a.get("complex")) for a in hits) else ("단지",)
                score.check("가격", bool(hits), f"{row.get('complex') or ''} {row.get('type') or ''} {p['kind']} {p['amountKrw']:,}".strip(), unchecked)
    precision = "가격(찾은 것 중 정답표에 없는 것)"
    for a in actual_supply:
        for p in a.get("prices") or []:
            if p.get("kind") in PRICE_KINDS and isinstance(p.get("amountKrw"), int):
                matches = [r for r in expected_rows if (p["kind"], p["amountKrw"]) in _amounts(r)]
                checked = [_complex_ok(r.get("complex"), a.get("complex")) for r in matches]
                ok = any(c is not False for c in checked)
                score.check(
                    precision,
                    ok,
                    f"{a.get('complex') or ''} {a.get('type') or ''} {p['kind']} {p['amountKrw']:,}".strip(),
                    () if True in checked else ("단지",),
                )

    actual_schedules = actual.get("schedules") or []
    for s in expected.get("schedules") or []:
        for key in ("start", "end"):
            if s.get(key):
                same_day = [a for a in actual_schedules if str(a.get(key) or "")[: len(s[key])] == s[key]]
                ok = any(a.get("kind") == s.get("kind") for a in same_day) or any(
                    # 공고(ANNOUNCEMENT)와 기타(OTHER) 사이의 분류 차이는 이름이 겹치면 같은 일정으로 봅니다
                    # (실측 전북 매입임대 「대상주택 게시」: 정답표 OTHER, 추출 ANNOUNCEMENT, 날짜는 같음). 접수·계약 같은 종류는 그대로 엄격히
                    {a.get("kind"), s.get("kind")} <= {"ANNOUNCEMENT", "OTHER"} and _labels_overlap(a.get("label"), s.get("label"))
                    for a in same_day
                )
                score.check(f"일정 {'시작' if key == 'start' else '끝'}", ok, f"{s.get('label')} {s[key]}")

    actual_eligibility = actual.get("eligibility") or []
    _score_numeric_eligibility(score, expected.get("eligibility") or [], actual_eligibility)
    for e in expected.get("eligibility") or []:
        criterion = e.get("criterion")
        label = f"{e.get('targetGroup') or '모두'} {criterion} {e.get('value')}"
        if criterion == "HOMELESS":
            # 「주택소유여부 … 불문」처럼 무주택 요건을 두지 않는 공고는 주택 소유(HOME_OWNERSHIP) 항목으로 적힙니다(실측 청주지북)
            ok = any(
                a.get("criterion") == "HOMELESS" or a.get("category") == "HOME_OWNERSHIP" or re.search(r"무주택|주택\s*소유", str(a.get("text") or ""))
                for a in actual_eligibility
            )
            score.check("자격: 무주택", ok, label)

    expected_scoring = [s for s in expected.get("selection") or [] if s.get("kind") == "SCORING"]
    actual_points = Counter(a.get("points") for a in actual.get("selection") or [] if a.get("kind") == "SCORING")
    for s, n in Counter(s.get("points") for s in expected_scoring).items():
        hit = min(n, actual_points.get(s, 0))
        for i in range(n):
            score.check("가점 행", i < hit, f"{s}점")

    # 정답표는 순위를 "1순위"·"주거약자 1순위"처럼 글로 적기도 합니다. 순위 숫자만 비교합니다
    def rank_of(value: Any) -> int | None:
        digits = re.search(r"\d+", str(value or ""))
        return int(digits[0]) if digits else None

    expected_ranks = Counter(rank_of(s.get("rank")) for s in expected.get("selection") or [] if s.get("kind") == "PRIORITY" and rank_of(s.get("rank")))
    actual_ranks = Counter(rank_of(a.get("rank")) for a in actual.get("selection") or [] if a.get("kind") == "PRIORITY")
    for rank, n in sorted(expected_ranks.items()):
        for i in range(n):
            score.check("선정 순위", i < actual_ranks.get(rank, 0), f"{rank}순위")

    def doc(name: Any) -> str:
        text = YEAR_DO.sub(r"\1년", SHORT_YEAR.sub(r"20\1년", str(name or ""))).replace("內", "내")
        plain = DOC_NOISE.sub("", POSSESSIVE.sub(" ", text))
        for pattern, short in SPELLED_OUT:
            plain = pattern.sub(short, plain)
        return plain

    def variants(raw: Any) -> set[str]:
        """한 서류 이름을 비교할 글자들: 이름 전체, 괄호 안을 살린 이름, 괄호 안에 나열한 서류마다, 첫 쉼표 앞,
        「A 또는 B」로 적은 서류마다(정답표 「인감증명서 또는 본인서명사실확인서」 ↔ 둘을 따로 넣은 추출)."""
        text = str(raw or "")
        found = {doc(text), doc(text.replace("(", " ").replace(")", " ")), doc(text.split(",")[0])}
        for inner in re.findall(r"\(([^)]*)\)", text):
            found |= {doc(part) for part in re.split(r"[,·/]|\s또는\s", inner)}
        # 나눈 조각은 서류 이름 꼴만(「예금인장 또는 본인 서명」의 「본인 서명」이 「본인서명사실확인서」에 글자로 들어 있어 맞은 것으로 세지 않게)
        found |= {p for p in (doc(part) for part in re.split(r"\s또는\s", re.sub(r"\([^)]*\)", " ", text))) if DOC_SUFFIX.search(p)}
        return {v for v in found if len(v) >= 3}

    def situation(raw: Any) -> str | None:
        """「비상장주식 증빙」 → 「비상장주식」(짧은 상황 이름 「소득 증빙」은 보지 않음)."""
        match = SITUATION_EVIDENCE.match(str(raw or "").strip())
        return doc(match[1]) if match and len(doc(match[1])) >= 3 else None

    def joined_parts(raw: Any) -> list[str]:
        """「본인(신청자) 및 배우자의 신분증」 → 「본인 신분증」「배우자 신분증」: 대상마다 나눠 적은 추출과 맞춥니다."""
        plain = re.sub(r"\([^)]*\)", "", POSSESSIVE.sub(" ", str(raw or "")))
        match = re.fullmatch(r"\s*(.+?)\s*및\s*(.+?)\s+(\S+)\s*", plain)
        return [doc(f"{match[1]} {match[3]}"), doc(f"{match[2]} {match[3]}")] if match else []

    def same(a: str, b: str) -> bool:
        return bool(a and b) and (a in b or b in a)

    actual_raw = [d.get("name") for d in actual.get("documents") or []]
    actual_sets = [variants(r) for r in actual_raw]
    actual_applies = [doc(d.get("appliesTo")) for d in actual.get("documents") or []]
    expected_raw = [d.get("name") for d in expected.get("documents") or []]
    expected_sets = [variants(r) for r in expected_raw]
    situations = [s for s in (situation(r) for r in expected_raw) if s]

    def for_situation(key: str, got: set[str], applies: str) -> bool:
        return any(key in a for a in got) or key in applies

    for raw, wanted in zip(expected_raw, expected_sets, strict=True):
        if wanted:
            # 정답표와 추출이 같은 서류를 다르게 적은 경우(「배우자의 신분증」↔「배우자 신분증」, 묶어 적은 이름 ↔ 나눠 적은 이름,
            # 괄호 속 나열)도 같은 서류로 봅니다(실측: 서류 11개가 이름 차이로만 놓침으로 셈)
            found = any(same(w, a) for w in wanted for got in actual_sets for a in got)
            parts = joined_parts(raw)
            found = found or bool(parts) and all(any(same(part, a) for got in actual_sets for a in got) for part in parts)
            key = situation(raw)
            found = found or bool(key) and any(for_situation(key, got, applies) for got, applies in zip(actual_sets, actual_applies, strict=True))
            score.check("서류", found, raw)
    for got, applies in zip(actual_sets, actual_applies, strict=True):
        if got:
            ok = (
                any(same(a, e) for a in got for wanted in expected_sets for e in wanted)
                or any(same(a, part) for a in got for raw in expected_raw for part in joined_parts(raw))
                or any(for_situation(key, got, applies) for key in situations)
            )
            score.total["서류(찾은 것 중 정답표에 없는 것)"] += 1
            score.found["서류(찾은 것 중 정답표에 없는 것)"] += ok

    actual_phones = {_digits(p) for c in actual.get("contacts") or [] for p in _phones(c.get("phone"))}
    for c in expected.get("contacts") or []:
        first = next(iter(_phones(c.get("phone"))), None)  # 정답표 「054)280-4750, 4763」은 첫 번호로 봅니다
        if first:
            score.check("문의처 전화", _digits(first) in actual_phones, c.get("phone"))
    return score


# ---------- 자동 게시 값의 오류 (2026-10-17 설계 검토: 검수를 줄이면 '틀린 채 자동 게시된 값'을 따로 재야 함) ----------

HELD_SECTIONS = ("supplyGroups", "schedules", "eligibility", "selectionRules", "requiredDocuments", "locations", "guidance")
_HELD = object()  # 칸 보류로 뺄 목록 원소 표시


def _drop_held_field(root: dict[str, Any], target: str) -> None:
    """항목 안 칸의 보류(「/supplyGroups/1/counts」「/supplyGroups/0/prices/2」): 목록 칸은 비우고, 목록 원소는 표시해 두었다가 뺍니다."""
    tokens = target.strip("/").split("/")
    node: Any = root
    for token in tokens[:-1]:
        if isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        elif isinstance(node, dict) and token in node:
            node = node[token]
        else:
            return
    last = tokens[-1]
    if isinstance(node, dict) and last in node:
        node[last] = [] if isinstance(node[last], list) else None
    elif isinstance(node, list) and last.isdigit() and int(last) < len(node):
        node[int(last)] = _HELD


def _without_held(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_held(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_without_held(v) for v in value if v is not _HELD]
    return value


def auto_published(candidate: dict[str, Any], status: str | None) -> dict[str, Any] | None:
    """사람 확인 없이 쓰이는 부분. 완료(COMPLETED)는 전부, 부분 완료(PARTIAL)는 보류 항목·섹션·칸을 뺀 나머지, 검수(IN_REVIEW)는 없음.
    항목 안 칸의 보류(「/supplyGroups/1/counts」)도 뺍니다: 판정·화면은 보류 위치 아래 값을 「확인 필요」로 보여 줍니다(judgment.common.unsure).
    2026-11-07 전에는 항목·섹션 보류만 빼서, 보류한 수량·가격이 「검수 없이 게시」와 틀린 값 후보에 섞여 세어졌음."""
    if status == "COMPLETED":
        return candidate
    if status != "PARTIAL":
        return None
    kept = json.loads(json.dumps(candidate))
    held = [h["target"] for h in (candidate.get("quality") or {}).get("heldItems") or []]
    for target in held:
        if len(target.strip("/").split("/")) >= 3 and target.strip("/").split("/")[0] in HELD_SECTIONS:
            _drop_held_field(kept, target)
    kept = _without_held(kept)
    for section in HELD_SECTIONS:
        if f"/{section}" in held:
            kept[section] = []
        else:
            kept[section] = [item for i, item in enumerate(kept.get(section) or []) if f"/{section}/{i}" not in held]
    return kept


# 정답표가 나이 기준을 행으로 두지 않고 대상 이름에만 적은 경우(「자목 65세 이상 수급권자 또는 차상위계층」)의 나이·방향과 그 나이의 주인.
# 나이 바로 뒤에 가족이 오면(「65세 이상 직계존속」) 그 가족의 나이이고, 없으면 신청자의 나이입니다
NAME_AGE = re.compile(r"(?:만\s*)?(\d{1,3})\s*세\s*(이상|초과|이하|미만)\s*(?:인|의)?\s*(직계존속|부모|자녀)?")
NAME_AGE_SUBJECT = {"직계존속": "PARENTS", "부모": "PARENTS", "자녀": "CHILDREN"}


def _age_in_group_name(expected: dict[str, Any], a: dict[str, Any]) -> bool:
    """추출 나이 기준이 정답표 대상 이름 속 나이와 같은지. 나이·방향과 나이의 주인(신청자·부모·자녀)이 같고 대상이 겹쳐야 합니다.
    2026-11-08: 정답표가 「65세 이상 수급권자」를 대상 이름으로만 적어, 원문과 같은 「65세 이상」이 틀린 값 후보로 세어졌음."""
    values, operator = _values(a.get("value")), _operator(a.get("operator"))
    if a.get("criterion") != "AGE" or len(values) != 1 or operator is None:
        return False
    for name in {e["targetGroup"] for e in expected.get("eligibility") or [] if e.get("targetGroup")}:
        for number, word, owner in NAME_AGE.findall(name):
            same = (float(number), OPERATOR_ALIASES[word]) == (values[0], operator)
            if same and NAME_AGE_SUBJECT.get(owner, "APPLICANT") == a.get("subject") and _groups_overlap(name, a.get("targetGroup")):
                return True
    return False


def wrong_values(expected: dict[str, Any], actual: dict[str, Any]) -> Score:
    """자동 게시 값 중 정답표에 없는 값(가격·모집 수·자격 기준값·접수 일정). found=정답표에 있음, total=게시한 값."""
    score = Score()
    expected_rows = expected.get("supplyTypes") or []
    relation = _complex_relation(expected_rows, actual.get("supplyTypes") or [])
    for r in actual.get("supplyTypes") or []:
        for p in r.get("prices") or []:
            if isinstance(p.get("amountKrw"), int) and p.get("kind") in PRICE_KINDS:
                # 같은 금액이 정답표에 있어도 다른 단지(compare와 같은 기준)에 있으면 틀린 값입니다
                same = [relation(e.get("complex"), r.get("complex"))
                        for e in expected_rows if (p["kind"], p["amountKrw"]) in {(q.get("kind"), q.get("amountKrw")) for q in e.get("prices") or []}]  # fmt: skip
                label = f"{r.get('complex') or ''} {p['kind']} {p['amountKrw']:,}".strip()
                score.check("자동 게시: 가격", any(s is not False for s in same), label, () if True in same else ("단지",))
    # 모집 수(2026-11-07 추가: gndc-ddb1 입주완료 호실 세 곳의 모집 1이 게시됐는데 수량을 보지 않아 틀린 값 후보에 없었음).
    # 게시된 묶음의 모집 수(없으면 예비·대기 수, 0은 빼고)마다 같은 면적의 정답표 행(없으면 같은 주택형, 그것도 없으면 모든 행, 다른 단지는 빼고)에
    # 그 수가 모집 수나 예비 수로 있는지 봅니다. 정답표에 행별 모집 수가 하나도 없는 공고는 판단하지 않습니다(정답표가 다루지 않은 것)
    if any(isinstance(e.get("offeredCount"), int) for e in expected_rows):
        for r in actual.get("supplyTypes") or []:
            code = _norm(r.get("type")).upper()
            rows = [e for e in expected_rows if relation(e.get("complex"), r.get("complex")) is not False]
            pool = [e for e in rows if _same_area(e.get("exclusiveAreaSqm"), r)] or [e for e in rows if code and _norm(e.get("type")).upper() == code] or rows
            for value in sorted({v for v in r.get("offeredCounts") or [] if isinstance(v, int) and v > 0}):
                ok = any(value in (e.get("offeredCount"), e.get("reserveCount")) for e in pool)
                score.check("자동 게시: 모집 수", ok, f"{r.get('complex') or ''} {r.get('type') or ''} {value}".strip())
    # 조건의 본 기준값만 봅니다(예외의 가구원수별·출산 가산 값은 정답표가 대표 기준 하나만 적어 비교할 수 없음).
    # 정답표에 그 종류의 기준이 하나도 없는 공고는 판단하지 않습니다(정답표가 다루지 않은 것). 방향·대상 계층은 compare와 같이 봅니다
    expected_rules = [e for e in expected.get("eligibility") or [] if _values(e.get("value"))]
    covered = {e.get("criterion") for e in expected_rules}
    for a in actual.get("rules") or []:
        if a.get("criterion") in ATTRIBUTES and a["criterion"] in covered and _values(a.get("value")):
            fits = [_eligibility_fit(e, a) for e in expected_rules if any(_close(w, v, 0.001) for w in _values(e.get("value")) for v in _values(a["value"]))]
            fits = [f for f in fits if f is not None]
            if not fits and _age_in_group_name(expected, a):
                fits = [("나이(정답표가 대상 이름에만 적음)",)]
            label = f"{a.get('targetGroup') or '모두'} {a['criterion']} {a.get('operator') or ''} {a.get('value')}"
            score.check("자동 게시: 자격 기준값", bool(fits), label, min(fits, key=len) if fits else ())
    starts = {(s.get("kind"), str(s.get("start") or "")[:10]) for s in expected.get("schedules") or [] if s.get("start")}
    for s in actual.get("schedules") or []:
        if s.get("kind") == "APPLICATION" and s.get("start"):
            score.check("자동 게시: 접수 시작일", (s["kind"], str(s["start"])[:10]) in starts, f"{s.get('label')} {s['start']}")
    return score


def published_view(outcome: dict[str, Any], notice: str) -> dict[str, Any] | None:
    """사람 확인 없이 쓰이는 부분을 채점 모양으로(자격 기준값은 조건식의 원자마다 rules에). 검수(IN_REVIEW) 결과는 None."""
    auto = auto_published(outcome["candidate"], outcome.get("status"))
    if auto is None:
        return None
    neutral = neutral_from_candidate(auto, notice)
    neutral["rules"] = [
        {
            "criterion": CRITERION_OF.get(atom.get("attribute"), "OTHER"),
            "subject": atom.get("subject"),  # 나이의 주인(신청자·부모·자녀): 정답표가 대상 이름에만 적은 나이와 견줄 때 봅니다
            "operator": atom.get("operator"),
            "value": atom.get("value"),
            "targetGroup": ", ".join(item["scope"]["targetGroups"]) or None,
            "text": item.get("originalText"),  # 계층 이름이 달라도 원문이 같으면 같은 조건으로 봅니다(compare와 같은 기준)
        }
        for item in auto["eligibility"]
        for atom in _atoms(item["rule"]["expression"])
    ]
    return neutral


def score_outcome(expected: dict[str, Any], outcome: dict[str, Any], notice: str, verified: dict[str, set[str]] | None = None) -> tuple[Score, Score, Score]:
    """추출 결과 하나 채점: (재현율, 검수 없이 쓰이는 정답 값, 자동 게시 값 중 정답표에 없는 값). 후보가 있는 결과만.
    main과 LangSmith 평가 실험(langsmith_eval.py)이 같은 기준으로 씁니다.
    verified: 이 공고의 원문 확인 목록(섹션 → 이름표). 정답표에 없는 값 중 원문과 대조해 맞다고 확인한 것은 맞음으로 셉니다."""
    view = published_view(outcome, notice)
    # 검수 없이 쓰이는 정답 값(보류 밖). 재현율과의 차이가 사람 확인으로 가는 값
    released, published = (compare(expected, view), wrong_values(expected, view)) if view is not None else (Score(), Score())
    for section, labels in (verified or {}).items():
        published.verify(section, labels)
    return compare(expected, neutral_from_candidate(outcome["candidate"], notice)), released, published


def sums(score: Score) -> tuple[int, int]:
    """(맞은 수, 전체 수). 「찾은 것 중 정답표에 없는 것」 항목은 재현율에 넣지 않습니다."""
    return sum(v for k, v in score.found.items() if "찾은" not in k), sum(v for k, v in score.total.items() if "찾은" not in k)


# ---------- 실행 ----------


def _load_key(folder: Path, notice: str) -> dict[str, Any] | None:
    for path in (folder / notice / "key.json", folder / f"{notice}.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_verified(path: Path) -> dict[str, dict[str, set[str]]]:
    """원문 확인 목록({"values": [{notice, section, label, source, reason, checked}]}) → 공고 → 섹션 → 이름표.
    정답표는 고치지 않고 따로 둡니다(재현율은 그대로, 자동 게시 값 중 정답표에 없는 값에만 씀). 원문·이유가 없는 항목은 받지 않습니다."""
    verified: dict[str, dict[str, set[str]]] = {}
    for entry in json.loads(path.read_text(encoding="utf-8"))["values"]:
        if not (entry.get("source") and entry.get("reason")):
            raise ValueError(f"원문 확인 목록에 원문(source)·이유(reason)가 없는 항목: {entry}")
        verified.setdefault(entry["notice"], {}).setdefault(entry["section"], set()).add(entry["label"])
    return verified


def _print_unchecked(score: Score, section: str, indent: str) -> None:
    """칸이 없어 값만 보고 맞음으로 센 수를 차원마다 한 줄로 알립니다(조용히 맞음으로 넘기지 않게)."""
    dims = score.unchecked.get(section)
    if dims:
        detail = " · ".join(f"{dim} {n}" for dim, n in dims.items())
        print(f"{indent}(확인 못 한 차원·다른 이름 대상, 맞음으로 셈) {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--keys", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--outcomes", type=Path)
    group.add_argument("--other-keys", type=Path)
    parser.add_argument("--misses", type=int, default=5, help="항목마다 보여 줄 놓친 것 수")
    parser.add_argument("--verified", type=Path, help="원문 확인 목록(JSON): 정답표에 없지만 원문과 대조해 맞다고 확인한 자동 게시 값")
    args = parser.parse_args()
    verified = _load_verified(args.verified) if args.verified else {}

    overall, published, released = Score(), Score(), Score()
    for folder in sorted(p for p in args.keys.iterdir() if p.is_dir()):
        notice = folder.name
        expected = _load_key(args.keys, notice)
        if expected is None:
            continue
        if args.outcomes:
            outcome_path = args.outcomes / notice / "outcome.json"
            if not outcome_path.exists():
                print(f"## {notice}: 추출 결과 없음")
                continue
            outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
            if not outcome.get("candidate"):
                print(f"## {notice}: 후보 없음 ({outcome.get('status')})")
                continue
            status = outcome.get("status")
            score, notice_released, notice_published = score_outcome(expected, outcome, notice, verified.get(notice))
            published.merge(notice_published, f"{notice}: ")
            released.merge(notice_released)
        else:
            actual = _load_key(args.other_keys, notice)
            if actual is None:
                print(f"## {notice}: 비교할 정답표 없음")
                continue
            status = "정답표 비교"
            score = compare(expected, actual)
        found, total = sums(score)
        print(f"## {notice} [{status}] 합계 {found}/{total}")
        for section in score.total:
            mark = "" if score.found[section] == score.total[section] else "  ←"
            print(f"  {section:<28} {score.found[section]:>4}/{score.total[section]:<4}{mark}")
            for miss in score.misses.get(section, [])[: args.misses]:
                print(f"      - {'정답표에 없음' if '찾은' in section else '놓침'}: {miss}")
            _print_unchecked(score, section, "      ")
        overall.merge(score)
    print("\n## 전체")
    for section in overall.total:
        rate = overall.found[section] / overall.total[section] if overall.total[section] else 0
        print(f"  {section:<28} {overall.found[section]:>5}/{overall.total[section]:<5} {rate:6.1%}")
        _print_unchecked(overall, section, "    ")
    found, total = sums(overall)
    print(f"  {'합계(재현율)':<28} {found:>5}/{total:<5} {found / total if total else 0:6.1%}")
    if released.total:  # 2026-11-05: 에이전트의 값은 검수로 남는 값을 줄이는 데 있어 재현율과 함께 봅니다(검수 공고는 0으로 셈)
        got = sums(released)[0]
        print(f"  {'자동 게시 재현율(검수 없이)':<26} {got:>5}/{total:<5} {got / total if total else 0:6.1%}")
    if published.total:
        print()
        print("## 자동 게시 값 중 정답표에 없는 값 (완료 전부 + 부분 완료의 보류 밖)")
        for section in published.total:
            wrong = published.total[section] - published.found[section]
            print(f"  {section:<28} {wrong:>5}/{published.total[section]:<5} {wrong / published.total[section]:6.1%}")
            for label in published.misses.get(section, []):
                print(f"      - {label}")
            if published.verified[section]:
                print(f"      (정답표에 없지만 원문 확인 목록에 있어 맞음으로 셈) {published.verified[section]}")
            _print_unchecked(published, section, "      ")


if __name__ == "__main__":
    sys.exit(main())
