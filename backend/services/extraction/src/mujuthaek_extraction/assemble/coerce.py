"""형식이 틀린 AI 출력 항목을 빼지 않고 틀린 칸만 안전한 값으로 바꿉니다(프론트 요청 6-3, 2026-10-23).

예전에는 일정 하나의 칸 하나가 틀려도(종류 오타, 시각 형식 등) 그 일정을 통째로 뺐습니다(AI_OUTPUT_ITEM_DROPPED). 화면에서는 일정이
사라져 원문을 다시 보라는 표시도 할 수 없었습니다. 이제 일정은 원문 표현(rawLabel)·설명·근거를 그대로 두고 틀린 칸만 바꿔 남기며,
뜻이 있는 칸(종류·날짜·범위·순위·접수 방식)을 바꿨으면 보류(heldItems)로 「확인 필요」를 보여 줍니다. 원문 사실을 지어내지 않습니다:
- 종류(kinds): 맞는 값만 남기고, 없으면 OTHER
- 날짜·마감: 시작이 틀리면 null, 끝·마감 상태·마감 조건 중 하나라도 틀리면 셋 다 「모름」(UNKNOWN, null, null)
- 범위(scope): 공고 전체·확인 필요(NEEDS_REVIEW)
- 순위: null, 접수 방식(applicationMode): 종류에 신청이 있으면 UNKNOWN, 없으면 NOT_APPLICABLE
- 덧붙인 칸(접수 방법·장소·이메일·시각·요일·링크·설명): 빈 값(null·빈 목록)
- id가 틀리면 겹치지 않는 새 id. 원문 표현·인용 참조가 틀리면 바꿀 수 없어 뺍니다
서류는 덧붙인 칸(묶음·부수·발급 기관·설명·제출 시점)만 비우고, 이름·대상·범위가 틀리면 예전처럼 뺍니다.
"""

from __future__ import annotations

from typing import Any

from mujuthaek_extraction.assemble import ai_output

COERCIBLE = ("schedules", "requiredDocuments")
SCHEDULE_EXTRAS = {
    "channels": [],
    "places": [],
    "applicationEmail": None,
    "dailyHours": [],
    "breaks": [],
    "excludedDays": [],
    "timeNote": None,
    "applicationUrl": None,
    "description": None,
}
DOCUMENT_EXTRAS = {"group": None, "copies": None, "issuer": None, "description": None, "submissionTime": None}
END_FIELDS = {"endsAt", "endStatus", "endCondition"}
UNFIXABLE = {"rawLabel", "quoteRefs", "name", "appliesTo"}
UNKNOWN_SCOPE = {
    "level": "NOTICE",
    "locationIds": [],
    "supplyGroupIds": [],
    "targetGroups": [],
    "supplyCategory": "ALL",
    "resolution": "NEEDS_REVIEW",
    "description": "적용 범위를 읽지 못했어요(원문 확인 필요)",
}
DEF_NAMES = {"schedules": "schedule", "requiredDocuments": "requiredDocument"}


def _definition(section: str) -> dict[str, Any]:
    return ai_output.schema()["$defs"][DEF_NAMES[section]]


def _bad_fields(item: dict[str, Any], errors: list[Any], allowed: set[str]) -> set[str] | None:
    """오류가 난 칸 이름들. 항목 자체가 틀렸으면(객체가 아님 등) None."""
    fields: set[str] = set()
    for error in errors:
        path = list(error.absolute_path)
        if len(path) >= 3 and isinstance(path[2], str):
            fields.add(path[2])
        elif error.validator == "required":
            fields |= {name for name in error.validator_value if name not in item}
        elif error.validator == "additionalProperties":
            fields |= {name for name in item if name not in allowed}
        else:
            return None
    return fields


def _new_id(part: dict[str, Any], section: str) -> str:
    used = {x.get("id") for x in part.get(section) or [] if isinstance(x, dict)}
    number = 1
    while f"{section}-unchecked-{number}" in used:
        number += 1
    return f"{section}-unchecked-{number}"


def coerce_item(section: str, item: dict[str, Any], errors: list[Any], part: dict[str, Any]) -> tuple[list[str], bool] | None:
    """틀린 칸만 바꿔 항목을 그 자리에서 고칩니다. (바꾼 칸 이름, 뜻 있는 칸을 바꿨는지). 고칠 수 없으면 None(항목을 뺌)."""
    definition = _definition(section)
    allowed = set(definition["properties"])
    fields = _bad_fields(item, errors, allowed)
    if not fields or fields & UNFIXABLE:
        return None
    extras = SCHEDULE_EXTRAS if section == "schedules" else DOCUMENT_EXTRAS
    meaningful = False
    for name in sorted(fields):
        if name not in allowed:
            item.pop(name, None)
        elif name in extras:
            value = extras[name]
            item[name] = list(value) if isinstance(value, list) else value
        elif name == "id":
            item["id"] = _new_id(part, section)
        elif section != "schedules":
            return None  # 서류의 이름·대상·범위는 바꾸지 않습니다
        else:
            meaningful = True
            if name == "kinds":
                enum = set(definition["properties"]["kinds"]["items"]["enum"])
                kinds = item.get("kinds") if isinstance(item.get("kinds"), list) else []
                item["kinds"] = list(dict.fromkeys(k for k in kinds if isinstance(k, str) and k in enum)) or ["OTHER"]
            elif name == "scope":
                item["scope"] = dict(UNKNOWN_SCOPE)
            elif name == "startsAt":
                item["startsAt"] = None
            elif name in END_FIELDS:
                item.update(endsAt=None, endStatus="UNKNOWN", endCondition=None)
            elif name == "priorityRank":
                item["priorityRank"] = None
            elif name != "applicationMode":
                return None
    if section == "schedules" and ({"kinds", "applicationMode"} & fields):
        applying = "APPLICATION" in item["kinds"]
        mode = item.get("applicationMode")
        if "applicationMode" in fields or applying == (mode == "NOT_APPLICABLE"):
            item["applicationMode"] = "UNKNOWN" if applying else "NOT_APPLICABLE"
    return sorted(fields), meaningful
