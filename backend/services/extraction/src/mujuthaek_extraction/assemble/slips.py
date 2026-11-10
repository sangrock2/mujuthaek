"""뜻이 분명한 형식 실수 고치기. 추출 단계(다시 요청할지 정하기 전)와 결합 단계가 함께 씁니다.

OpenAI 엄격 모드는 비울 칸도 채우게 해서 다음 실수가 생깁니다(실측 OpenAI LH 대전 영구임대: 가점표 12행이 형식 오류로 빠지고
일정·선정 호출을 한 번씩 다시 요청함). 원문 사실을 지어내지 않는 고침만 둡니다.
- 구조화된 조건(조건식 있음)의 사유를 null 대신 「""」나 「조건을 구조화했어요.」 같은 글로 적음 → null
- 추첨 등 순서가 없는 선정 항목에 순서 번호를 적음 → null
- 안내·신청 링크를 「www.lh.or.kr」처럼 프로토콜 없이 적음 → 「https://」를 붙임
- 자격 조건 예외를 PRESENT로 적고 예외 목록은 비움 → NOT_REVIEWED(사람 확인). 실측 OpenAI 청약홈 에코델타: 이 실수와 링크 실수로
  일정·자격 호출을 한 번씩 다시 요청했고, 다시 받은 일정 답은 인용을 빠뜨려 6개 항목의 근거가 사라졌습니다
- 적용 범위를 공고 전체(NOTICE)로 적고 공급 묶음·위치 ID를 함께 적음 → 그 ID의 범위(SUPPLY_GROUP·LOCATION). ID를 적은 쪽이 뜻이
  분명합니다(실측 2026-10-20 LH 인천부평: 「주거약자용 주택(36AS형)은 65세 이상만」이 이 실수로 빠져 자격 섹션 전체가 보류됨)
- 일정 끝을 CONDITIONAL로 적고 끝 날짜도 적음(정해진 끝 날짜 + 조기 종료 조건) → FIXED, 조건은 시간 설명(timeNote)으로
"""

from __future__ import annotations

import re
from typing import Any

BARE_HOST = re.compile(r"^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?$", re.IGNORECASE)


def _nodes(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def fix_format_slips(part: Any) -> Any:
    """AI 출력 조각에서 모듈 설명에 적은 형식 실수만 제자리에서 고치고 같은 객체를 돌려줍니다."""
    if not isinstance(part, dict):
        return part
    for item in part.get("selectionRules") or []:
        if isinstance(item, dict) and item.get("kind") != "TIE_BREAK" and item.get("order") is not None:
            item["order"] = None
    for section in ("eligibility", "selectionRules"):
        for node in _nodes(part.get(section)):
            # 조건식이 있는 구조화 조건의 사유 칸은 계약상 비어야 합니다. 「조건을 구조화했어요.」 같은 채움 글도 원문 사실이 아니라 비웁니다
            # (2026-11-05 실측 sh-311087: 다시 요청한 선정 답의 소득·자산 배점 6행이 이 글 때문에 형식 오류로 모두 빠짐)
            reason = node.get("reason")
            if node.get("status") == "STRUCTURED" and (reason == "" or (isinstance(reason, str) and node.get("expression"))):
                node["reason"] = None
    for section, key in (("guidance", "url"), ("schedules", "applicationUrl")):
        for item in part.get(section) or []:
            url = item.get(key) if isinstance(item, dict) else None
            if isinstance(url, str) and BARE_HOST.match(url.strip()):
                item[key] = "https://" + url.strip()
    for item in part.get("schedules") or []:
        if (
            isinstance(item, dict)
            and item.get("endStatus") == "CONDITIONAL"
            and isinstance(item.get("endsAt"), dict)
            and item["endsAt"].get("value")
            and isinstance(item.get("endCondition"), str)
            and item["endCondition"].strip()
        ):
            # 정해진 끝 날짜와 그전에 끝날 수 있는 조건이 함께 적힌 기간(「10.06~11.12, 공가 소진 시 주택개방 종료」): 끝 날짜는 원문에
            # 있으므로 FIXED로 두고 조건은 시간 설명에 옮깁니다. CONDITIONAL은 끝 날짜를 받지 않아 일정이 형식 오류로 보류됐음
            # (2026-10-24 프론트 요청 6-3: 열람 일정이 화면에서 빠짐)
            condition = item["endCondition"].strip()
            note = item.get("timeNote")
            item["timeNote"] = condition if not isinstance(note, str) or not note.strip() else f"{note.strip()} {condition}"
            item["endStatus"], item["endCondition"] = "FIXED", None
    for item in part.get("eligibility") or []:
        if isinstance(item, dict) and item.get("exceptionsStatus") == "PRESENT" and item.get("exceptions") == []:
            item["exceptionsStatus"] = "NOT_REVIEWED"
    for node in _nodes({k: v for k, v in part.items() if k != "quotes"}):
        if node.get("level") == "NOTICE" and isinstance(node.get("supplyGroupIds"), list) and isinstance(node.get("locationIds"), list):
            if node["supplyGroupIds"]:
                node["level"] = "SUPPLY_GROUP"
            elif node["locationIds"]:
                node["level"] = "LOCATION"
    return part
