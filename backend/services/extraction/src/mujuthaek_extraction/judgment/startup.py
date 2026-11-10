"""창업지원 판정 틀(startup-support-judgment.v1) 가공: 수집 이벤트(raw.policy.collected)에서 코드로만 만듭니다(AI 호출 없음).

지금은 K-Startup만 합니다. K-Startup API는 창업 기간·대상 연령·신청 대상을 정해진 구간 값으로 줘서 규칙으로 옮길 수 있어요
(틀 문서 「K-Startup 구조화 칸 옮기는 법」, 예시 14). 기업마당은 구간 칸이 없어 글을 읽어야 하므로 None(틀 없음)입니다.

- 창업 기간(biz_enyy): 예비창업자만 → 사업자 아님, N년미만만 → 사업자 + 업력, 둘 다 → ANY_OF, 모든 구간 → 조건 없음
- 대상 연령(biz_trgt_age): 고른 구간을 합친 나이 범위, 세 구간 모두 → 조건 없음
- 신청 대상(aply_trgt): 「일반인」이 있으면 조건 없음, 대학생·1인 창조기업만 → STATUS, 그 밖의 조합 → 질문
- 지원 지역(supt_regin): 지원 지역이라 자격으로 쓰지 않음
- 신청 대상 내용·신청 제외 대상(글): 코드로 나누지 못해 원문 질문 + 확인 필요, 우대 사항(글): 안내

기준일: K-Startup 응답에는 공고일이 없고 접수 시작일은 기준일로 쓰지 않으므로(틀 문서) referenceDate는 null(판정하는 날 기준)입니다.
그래서 「N년미만」의 개업일 범위(BUSINESS_AGE)를 날짜로 정할 수 없어 업력은 질문 + 확인 필요로 둡니다.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "startup-support-judgment.v1"

# K-Startup 창업 기간 구간(전체). 모두 고르면 업력 조건이 없습니다
STAGES = ("예비창업자", "1년미만", "2년미만", "3년미만", "5년미만", "7년미만", "10년미만")
PRE_FOUNDER = "예비창업자"
# K-Startup 대상 연령 구간 → (최소, 최대) 만 나이
AGE_BANDS = {"만 20세 미만": (None, 19), "만 20세 이상 ~ 만 39세 이하": (20, 39), "만 40세 이상": (40, None)}
# K-Startup 신청 대상 중 틀의 유형 코드가 있는 것
TARGET_STATUS = {"대학생": "STUDENT", "1인 창조기업": "ONE_PERSON_CREATIVE"}
NO_LIMIT_TARGET = "일반인"
NO_REFERENCE_DATE = "공고에 기준일이 없어(판정하는 날 기준) 창업 기간을 개업일 범위로 정할 수 없습니다"
UNREAD_TEXT = "글로 적힌 조건을 코드로 나누지 못했습니다"


def _criterion(new_id: str, kind: str, quote: str | None) -> dict[str, Any]:
    return {"id": new_id, "kind": kind, "quote": quote, "page": None, "inReview": False, "reviewReason": None, "asOf": None}


# 틀마다 다른 부분: 조건 공통 칸(창업지원 틀만 asOf), 신청 대상의 유형 코드, 「N년미만」 질문을 확인 필요로 둘 이유,
# 사업자 등록 조건의 틀별 칸(사업공간 틀은 closedWithinYears)
class Profile:
    def __init__(self, base: Any, statuses: dict[str, str], under_reason: str | None, registration: dict[str, Any] | None = None):
        self.base, self.statuses, self.under_reason, self.registration = base, statuses, under_reason, registration or {}

    def ask(self, new_id: str, question: str, quote: str | None, met_when: str) -> dict[str, Any]:
        return self.base(new_id, "ASK", quote) | {"question": question, "metWhen": met_when}


def _flag(criterion: dict[str, Any], reason: str) -> dict[str, Any]:
    return criterion | {"inReview": True, "reviewReason": reason}


def _values(raw: Any) -> list[str] | None:
    """「예비창업자,1년미만,3년미만」 → 목록. 칸이 비었으면 None(구간을 고르지 않음)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    return [v.strip() for v in raw.split(",") if v.strip()]


def _clean(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    text = text.replace("\r\n", "\n").strip()
    return text or None


def _stage(record: dict[str, Any], profile: Profile) -> list[dict[str, Any]] | None:
    """창업 기간 → 조건. 모르는 구간 값이 있으면 None(틀을 만들지 않음)."""
    raw = record.get("biz_enyy")
    values = _values(raw)
    if values is None or set(STAGES) <= set(values):
        return []
    if any(v not in STAGES for v in values):
        return None
    years = [int(v.removesuffix("년미만")) for v in values if v != PRE_FOUNDER]
    pre = profile.base("stage-pre", "BUSINESS_REGISTRATION", raw) | {"require": "NOT_REGISTERED"} | profile.registration
    if not years:
        return [pre]
    n = max(years)
    under = profile.ask(f"stage-under-{n}y", f"사업을 시작한 날(법인은 설립등기일)부터 {n}년이 지나지 않았나요?", raw, "YES")
    registered = [
        profile.base("stage-registered", "BUSINESS_REGISTRATION", raw) | {"require": "REGISTERED"} | profile.registration,
        _flag(under, profile.under_reason) if profile.under_reason else under,
    ]
    if PRE_FOUNDER not in values:
        return registered
    options = [{"label": "예비창업자", "criteria": [pre]}, {"label": f"창업 {n}년 미만", "criteria": registered}]
    return [profile.base("stage", "ANY_OF", raw) | {"options": options}]


def _age(record: dict[str, Any], profile: Profile) -> list[dict[str, Any]] | None:
    """대상 연령 → 조건. 이어지지 않는 구간(20세 미만 + 40세 이상)은 ANY_OF."""
    raw = record.get("biz_trgt_age")
    values = _values(raw)
    if values is None or set(AGE_BANDS) <= set(values):
        return []
    if any(v not in AGE_BANDS for v in values):
        return None
    bands = sorted((AGE_BANDS[v] for v in dict.fromkeys(values)), key=lambda b: -1 if b[0] is None else b[0])
    merged: list[list[int | None]] = []
    for low, high in bands:
        if merged and merged[-1][1] is not None and low is not None and low == merged[-1][1] + 1:
            merged[-1][1] = high
        else:
            merged.append([low, high])
    ages = [profile.base(f"age-{i + 1}" if len(merged) > 1 else "age", "AGE", raw) | {"minAge": lo, "maxAge": hi} for i, (lo, hi) in enumerate(merged)]
    if len(ages) == 1:
        return ages
    options = [{"label": _age_label(a["minAge"], a["maxAge"]), "criteria": [a]} for a in ages]
    return [profile.base("age", "ANY_OF", raw) | {"options": options}]


def _age_label(low: int | None, high: int | None) -> str:
    if low is None:
        return f"만 {high}세 이하"
    return f"만 {low}세 이상" if high is None else f"만 {low}세 이상 {high}세 이하"


def _target(record: dict[str, Any], profile: Profile) -> list[dict[str, Any]]:
    """신청 대상 → 조건. 「일반인」이 있으면 누구나라 조건 없음."""
    raw = record.get("aply_trgt")
    values = _values(raw)
    if values is None or NO_LIMIT_TARGET in values:
        return []
    if all(v in profile.statuses for v in values):
        return [profile.base("target", "STATUS", raw) | {"anyOf": list(dict.fromkeys(profile.statuses[v] for v in values))}]
    return [profile.ask("target", f"다음 신청 대상 중 하나에 해당하나요? 「{raw}」", raw, "YES")]


STARTUP = Profile(_criterion, TARGET_STATUS, NO_REFERENCE_DATE)


def kstartup_parts(record: dict[str, Any], profile: Profile) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """K-Startup 응답 → (공통 조건, 안내). 모르는 구간 값이 있으면 None. 창업지원·사업공간 틀이 함께 씁니다."""
    stage, age = _stage(record, profile), _age(record, profile)
    if stage is None or age is None:
        return None
    common = [*stage, *age, *_target(record, profile)]
    content = _clean(record.get("aply_trgt_ctnt"))
    if content:
        # 「…기업(예비창업자 포함)」「旣 선정된 … 중복 지원 불가」처럼 대상 설명·제한·안내가 한 글에 섞여 있어 원문 전체를 묻습니다
        common.append(_flag(profile.ask("target-detail", f"다음 신청 대상 내용에 맞나요? 「{content}」", content, "YES"), UNREAD_TEXT))
    excluded = _clean(record.get("aply_excl_trgt_ctnt"))
    if excluded:
        common.append(_flag(profile.ask("excluded", f"다음 신청 제외 대상에 해당하나요? 「{excluded}」", excluded, "NO"), UNREAD_TEXT))
    preference = _clean(record.get("prfn_matr"))
    notes = [{"kind": "OTHER", "groupId": None, "text": f"우대 사항: {preference}", "quote": preference, "page": None}] if preference else []
    return common, notes


def build_startup(payload: dict[str, Any]) -> dict[str, Any] | None:
    """raw.policy.collected payload → 창업지원 판정 틀. K-Startup 창업지원이 아니거나 모르는 구간 값이 있으면 None."""
    if payload.get("field") != "STARTUP_SUPPORT" or payload.get("provider") != "KSTARTUP":
        return None
    parts = kstartup_parts(payload.get("record") or {}, STARTUP)
    if parts is None:
        return None
    common, notes = parts
    return {
        "schema": SCHEMA,
        "rawPolicyId": payload["rawPolicyId"],
        "rawVersion": payload["version"],
        "referenceDate": None,
        "common": common,
        "groups": [{"id": "all", "name": "전체", "criteria": []}],
        "preferences": [],
        "notes": notes,
    }
