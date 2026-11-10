"""사업공간 판정 틀(business-space-judgment.v1) 가공: 사업공간 모집 수집 이벤트(raw.policy.collected, field SPACE_RECRUITMENT)에서
코드로만 만듭니다(AI 호출 없음). 수집기가 사업공간으로 분류한 정책은 사업공간 틀로 갑니다(사용자 확인 2026-10-22).

지금은 K-Startup만 합니다. 창업 기간·대상 연령·신청 대상 칸은 창업지원 틀과 같은 규칙으로 옮기고(startup.kstartup_parts), 틀에 맞는
칸이 없는 것은 질문으로 둡니다.
- 「N년미만」: 사업공간 틀의 업력(BUSINESS_CAREER)은 「영업 경력 N개월 이상」만 나타내서 상한은 질문(사업자 등록은 조건으로)
- 신청 대상 「대학생」「1인 창조기업」: 사업공간 틀에 유형 코드가 없어 질문
- 기준일(referenceDate, 필수): K-Startup 응답에는 공고일이 없어 원문 화면 본문의 게시일(「2026년 10월 07일」 바로 다음 줄이 주관기관 이름)을
  씁니다. 찾지 못하면 틀을 만들지 않습니다(None, 공고일 없는 공고와 같음). 접수 시작일로 채우지 않습니다.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from mujuthaek_extraction.judgment.startup import Profile, kstartup_parts

SCHEMA = "business-space-judgment.v1"


def _criterion(new_id: str, kind: str, quote: str | None) -> dict[str, Any]:
    return {"id": new_id, "kind": kind, "quote": quote, "page": None, "inReview": False, "reviewReason": None}


SPACE = Profile(_criterion, {}, None, {"closedWithinYears": None})


def posted_on(text: str, agency: str | None) -> str | None:
    """원문 화면 본문의 게시일: 「2026년 10월 07일」 줄 바로 다음 줄이 주관기관 이름일 때만. 하나가 아니면 None."""
    if not agency:
        return None
    pattern = r"(?:^|\n)\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*\n\s*" + re.escape(agency.strip()) + r"\s*(?:\n|$)"
    found = set()
    for year, month, day in re.findall(pattern, text):
        try:
            found.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            return None
    return found.pop() if len(found) == 1 else None


def build_space(payload: dict[str, Any]) -> dict[str, Any] | None:
    """raw.policy.collected payload → 사업공간 판정 틀. K-Startup 사업공간 모집이 아니거나, 게시일을 찾지 못하거나, 모르는 구간 값이 있으면 None."""
    if payload.get("field") != "SPACE_RECRUITMENT" or payload.get("provider") != "KSTARTUP":
        return None
    reference = posted_on(payload.get("text") or "", payload.get("agency"))
    parts = kstartup_parts(payload.get("record") or {}, SPACE)
    if reference is None or parts is None:
        return None
    common, notes = parts
    return {
        "schema": SCHEMA,
        "rawPostId": payload["rawPolicyId"],
        "rawVersion": payload["version"],
        "referenceDate": reference,
        "common": common,
        "groups": [{"id": "all", "name": "전체", "criteria": []}],
        "preferences": [],
        "notes": notes,
    }
