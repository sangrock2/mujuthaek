"""검증까지 끝난 후보 → extraction.completed payload (팀 이벤트 흐름 문서 4·8절, 2026-10-15 확정 형식).

- 필수: rawPostId, rawVersion, field, title, conditions, reviewStatus(AUTO_PASSED/PARTIALLY_PASSED/IN_REVIEW)
- 부분 완료(PARTIALLY_PASSED, 2026-10-17): 공고는 게시하고 heldItems의 항목·섹션만 보류(보류한 자격 조건은 inReview)
- 선택: provider, regionCode(시군구 5자리), schedule(applyStartOn/applyEndOn), applicationWindows(순위·대상별 접수 기간 — 알림용),
  summary, reprocess, notice(표준 공고 전체 — 상세 화면용), judgment(판정 틀 — 판정 담당이 정한 형식 그대로, judgment/)
- 검수 중이어도 내보내며, 자격 조건마다 inReview로 표시합니다. 검증을 통과하지 못한 접수 일정은 schedule에 넣지 않습니다.
봉투(eventId 등)는 공통 라이브러리 new_event로 만듭니다. 이 함수는 시계·UUID를 쓰지 않습니다.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.judgment import build_judgment
from mujuthaek_extraction.judgment.policy_frame import (
    PERIOD_TEXT_FIELDS,
    policy_apply_period,
    region_named,
    space_frame,
    startup_frame,
    uses_judging_date,
)
from mujuthaek_extraction.judgment.sanity import repair
from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.judgment.space import build_space
from mujuthaek_extraction.judgment.startup import build_startup

log = logging.getLogger(__name__)


def _issue_targets(candidate: dict[str, Any], *, with_notes: bool = False) -> list[tuple[str, str]]:
    quality = candidate["quality"]
    return [(i["target"], i["code"]) for i in [*quality["reviewIssues"], *(quality["notes"] if with_notes else [])]]


def _codes_under(issues: list[tuple[str, str]], prefix: str) -> list[str]:
    return sorted({code for target, code in issues if target == prefix or target.startswith(prefix + "/")})


def _held_codes(candidate: dict[str, Any], pointer: str) -> list[str]:
    """부분 완료로 보류한 범위가 pointer와 겹치면(같음·안·품음, 계약 overlaps_held) 그 보류 사유.
    /schedules/i/applicationMode만 보류해도 그 일정은 쓰지 않습니다."""
    return sorted({code for h in candidate["quality"].get("heldItems", []) if tools().overlaps_held(pointer, [h["target"]]) for code in h["codes"]})


def conditions(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """자격 조건마다 payload 조건을 만듭니다. 검수 이슈·보류·예외 미검토가 있으면 inReview와 그 사유를 붙입니다."""
    issues = _issue_targets(candidate)
    out = []
    for index, item in enumerate(candidate["eligibility"]):
        reasons = sorted({*_codes_under(issues, f"/eligibility/{index}"), *_held_codes(candidate, f"/eligibility/{index}")})
        if item["exceptionsStatus"] == "NOT_REVIEWED":
            reasons.append("EXCEPTIONS_NOT_REVIEWED")
        out.append(
            {
                **tools().condition_fields(item),
                "inReview": bool(reasons),
                "reviewReasons": reasons,
            }
        )
    return out


def application_schedule(candidate: dict[str, Any]) -> dict[str, str | None] | None:
    """공통 계약의 동일한 일정 투영을 사용합니다."""
    return tools().application_schedule(candidate)


def application_windows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """날짜 미정 구간을 포함한 검증된 신청 일정. 보류·검수 범위는 제외합니다."""
    return tools().application_windows(candidate)


def sigungu_code(candidate: dict[str, Any]) -> str | None:
    """이벤트 regionCode: 계약 검사기(event_region_code)와 같은 규칙. 모든 위치가 한 시군구면 그 코드, 여러 시군구지만 한 시도면 xx000,
    여러 시도·코드 없는 위치·보류한 위치 지역·위치 없음이면 null.
    예전엔 코드 없는 위치를 건너뛰고 수집기 값으로 대신 채워 계약과 어긋났습니다(검토 2026-10-20)."""
    held = [h["target"] for h in candidate["quality"].get("heldItems") or []]
    return tools().event_region_code(candidate["locations"], held)


def completed_payload(candidate: dict[str, Any], *, provider: str | None = None, regions: Any = None, pages: dict[str, int] | None = None) -> dict[str, Any]:
    """검증 결과로 reviewStatus를 정해 extraction.completed payload를 만듭니다. 검증 통과에 검수 중인 조건이 없을 때만 AUTO_PASSED입니다."""
    status = candidate["quality"]["verification"]["status"]
    items = conditions(candidate)
    if status == "PASSED" and not any(c["inReview"] for c in items):
        review = "AUTO_PASSED"
    elif status == "PARTIALLY_PASSED":
        review = "PARTIALLY_PASSED"
    else:
        review = "IN_REVIEW"
    return {
        "rawPostId": candidate["input"]["rawPostId"],
        "rawVersion": candidate["input"]["rawVersion"],
        "field": candidate["input"]["field"],
        "title": candidate["notice"]["title"] or candidate["sourceReferences"][0]["sourceTitle"],
        "conditions": items,
        "reviewStatus": review,
        **({"heldItems": candidate["quality"]["heldItems"]} if candidate["quality"].get("heldItems") else {}),
        "provider": provider,
        "regionCode": sigungu_code(candidate),
        "schedule": application_schedule(candidate),
        "applicationWindows": application_windows(candidate),
        # 보류한 공고 설명은 목록 요약에 쓰지 않습니다(공고 기본 정보 칸 보류, 2026-10-20)
        "summary": None if _held_codes(candidate, "/notice/description") else candidate["notice"]["description"],
        "reprocess": candidate["input"]["reprocess"],
        "notice": candidate,
        # 판정 틀(사용자 결정 2026-10-20: 이 이벤트에 칸을 더해 틀 객체를 그대로 담음). 틀이 없는 분야·틀 검사 실패면 null
        "judgment": build_judgment(candidate, regions, pages=pages),
    }


def approved_payload(candidate: dict[str, Any], *, provider: str | None = None, regions: Any = None) -> dict[str, Any]:
    """검수자가 승인한 결과. 사람이 보류 항목까지 확인했으므로 보류(heldItems)를 풀고, 조건의 inReview를 모두 내리고,
    보류 때문에 빠졌던 접수 일정도 다시 내보냅니다(계약 application_schedule(approved=True)). reviewStatus는 APPROVED입니다.
    예전엔 승인용 사본에서 보류 목록을 찾다 KeyError로 멈췄고, 고쳐도 상세에 보류 목록이 남아 계약 위반(EVENT_HELD_ITEMS_CONFLICT)이었습니다."""
    # 자동 검증 기록·이슈는 유지합니다. 현재 보류만 해제하고 원 후보는 검수 작업 기록에 보존합니다.
    quality = {k: v for k, v in candidate["quality"].items() if k != "heldItems"}
    reviewed = {**candidate, "quality": quality}
    payload = completed_payload(reviewed, provider=provider, regions=regions)
    for condition in payload["conditions"]:
        condition.update(inReview=False, reviewReasons=[])
    payload.update(
        reviewStatus="APPROVED",
        notice=reviewed,
        # 조건(conditions)의 inReview를 내린 것과 같게, 판정 틀도 추출 검수 사유로는 확인 필요를 붙이지 않습니다(2026-10-21)
        judgment=build_judgment(reviewed, regions, approved=True),
        schedule=tools().application_schedule(reviewed, approved=True),
        applicationWindows=tools().application_windows(reviewed, approved=True),
    )
    payload.pop("heldItems", None)
    return payload


def _in_review(criteria: list[dict[str, Any]]) -> bool:
    return any(c["inReview"] or _in_review([i for o in c.get("options") or [] for i in o["criteria"]]) for c in criteria)


POLICY_FIELDS = ("STARTUP_SUPPORT", "SPACE_RECRUITMENT")


# 권역 이름 → 시도 이름(지역표로 코드를 찾으므로 통합·개편된 시도도 지역표를 따름)
REGION_GROUPS = {
    "수도권": ("서울", "인천", "경기"),
    "충청권": ("대전", "세종", "충북", "충남"),
    "호남권": ("광주", "전북", "전남"),
    "영남권": ("부산", "대구", "울산", "경북", "경남"),
    "동남권": ("부산", "울산", "경남"),
    "대경권": ("대구", "경북"),
    "강원권": ("강원",),
    "제주권": ("제주",),
}


def _codes_of(names: list[str], regions: Any) -> list[str] | None:
    """지역 이름(권역 포함) → 시군구 5자리. 하나라도 못 찾으면 None."""
    if not names or regions is None:
        return None
    found = []
    for name in names:
        name = re.sub(r"[\[\]()]", "", str(name)).strip()
        for part in REGION_GROUPS.get(name, (name,)):
            match = regions.lookup(part)
            if match.code is None or match.note:
                return None
            found.append(match.code[:5])
    return list(dict.fromkeys(found))


def _quoted_region_codes(found: dict[str, Any], policy: dict[str, Any], regions: Any) -> list[str] | None:
    """AI가 글에서 읽은 지역(names·quote) → 시군구 5자리. 근거 문장이 원문에 있고 그 문장에 지역 이름이 모두 있을 때만. 「전국」이면 빈 목록."""
    names, quote = found.get("names") or [], found.get("quote")
    text = re.sub(r"\s+", "", str(policy.get("text") or ""))
    plain = re.sub(r"\s+", "", quote or "")
    if len(plain) < 2 or plain not in text or not names or not all(region_named(n, quote) or n in REGION_GROUPS and n in plain for n in names):
        return None
    if names == ["전국"]:
        return []
    return _codes_of(names, regions)


def narrowest(codes: list[str]) -> list[str]:
    """같은 지역의 상위 코드를 뺍니다: 같은 시도의 시군구가 있으면 시도 전체(xx000), 같은 시의 일반구(41285)가 있으면 그 시(41280).
    xx000은 그 시도의 모든 시군구로 검색되므로, AI가 「경기도」「고양시」「일산동구」로 나눠 적으면 공간이 경기 전체로 넓어졌음(리뷰 2026-10-23)."""

    def covered(code: str) -> bool:
        if code.endswith("000"):
            return any(other != code and other[:2] == code[:2] for other in codes)
        return code[4] == "0" and any(other[:4] == code[:4] and other[4] != "0" for other in codes)

    return [c for c in dict.fromkeys(codes) if not covered(c)]


NEAR_LINES = 3  # 공간이 여럿이면 주소가 줄마다 따로 있음: 근거 문장 줄 앞뒤 이만큼의 줄에서도 이름을 찾음


def _located_near(name: str, quote: str, text: str) -> bool:
    """공간 이름이 근거 문장에, 아니면 원문에서 근거 문장이 있는 줄 앞뒤 NEAR_LINES줄 중 한 줄에 통째로 있는지."""
    if region_named(name, quote):
        return True
    target = re.sub(r"\s+", "", quote)
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if target in re.sub(r"\s+", "", line):
            if any(region_named(name, other) for other in lines[max(0, n - NEAR_LINES) : n + NEAR_LINES + 1]):
                return True
    return False


def space_location_codes(found: dict[str, Any], policy: dict[str, Any], regions: Any) -> tuple[list[str] | None, bool]:
    """AI가 읽은 입주 공간 소재지 → (시군구 5자리, AI가 공간 위치를 읽었는지). 근거 문장이 원문에 있어야 하고, 이름은 하나씩 확인해
    (근거 문장이나 그 앞뒤 줄) 확인된 이름만 씁니다. 같은 시도·시의 상위 코드는 뺍니다. 하나도 못 정하면 코드는 None."""
    names = [str(n) for n in found.get("names") or [] if str(n).strip()]
    quote = str(found.get("quote") or "")
    claimed = bool(names) and [re.sub(r"\s+", "", n) for n in names] != ["전국"]
    text = str(policy.get("text") or "")
    plain = re.sub(r"\s+", "", quote)
    if not claimed or len(plain) < 2 or plain not in re.sub(r"\s+", "", text):
        return None, claimed
    codes = [c for n in names if _located_near(n, quote, text) for c in _codes_of([n], regions) or []]
    return narrowest(codes) or None, True


def policy_region_codes(policy: dict[str, Any], regions: Any, reading: Any = None) -> list[str] | None:
    """정책의 지역 → 시군구 5자리 목록(xx000은 시도 전체). 전국이면 빈 목록, 정하지 못하면 None(빈 목록은 전국으로 읽혀 틀림).
    뜻은 분야마다 다릅니다(사용자 결정 2026-10-23).
    - STARTUP_SUPPORT: 지원 지역(사업 대상 지역)
    - SPACE_RECRUITMENT: 입주 공간이 있는 곳(검색·필터용). 신청자 거주지·사업장 소재지 요건은 판정 틀의 REGION 조건으로만 나타냅니다.
      AI가 글에서 읽은 공간 소재지(spaceLocation)를 근거 문장과 지역 이름을 확인한 뒤 먼저 쓰고(수집기가 전국이라고 해도 —
      전국 기관이 운영하는 공간도 한 곳에 있음), 없으면 아래 수집기 값 순서로 갑니다.
      AI가 공간 위치를 읽었는데 확인하지 못했으면 빈 목록(전국)을 내지 않고 None(보내지 않음)입니다. 공간은 한 곳에 있으므로
      「전국」은 틀린 값이고, 틀린 값이 누락보다 나쁩니다(리뷰 2026-10-23: 청주 공간이 전국으로 나갔음). 수집기가 시도·시군구를 주면 그 값을 씁니다.
    수집기 값(코드, 없으면 이름 — K-Startup은 「서울」처럼 이름만, 기업마당은 「충청권」 같은 권역도 줌)을 먼저 쓰고, 수집기가 지역을 모르면
    AI가 글에서 읽은 지원 지역을 씁니다. AI 값은 근거 문장이 원문에 있고 그 문장에 지역 이름이 있을 때만 씁니다."""
    claimed = False
    if policy.get("field") == "SPACE_RECRUITMENT" and reading is not None:
        located, claimed = space_location_codes(reading.answer.get("spaceLocation") or {}, policy, regions)
        if located:
            return located
    scope = policy.get("regionScope")
    if scope == "NATIONWIDE":
        return None if claimed else []
    codes = [str(c) for c in policy.get("regionCodes") or [] if re.fullmatch(r"[0-9]{5}", str(c))]
    if codes:
        return list(dict.fromkeys(codes))
    if scope in ("SIDO", "SIGUNGU") and (found := _codes_of(policy.get("regionNames") or [], regions)) is not None:
        return found
    if reading is None:
        return None
    support = _quoted_region_codes(reading.answer.get("supportRegions") or {}, policy, regions)
    return None if claimed and support == [] else support


# 보내지 않은 까닭(로그용). 「틀 검사 실패」 한 문구로 뭉치면 기준일 없음·지역 미정과 구별되지 않았음(리뷰 2026-10-23)
NOT_RELEVANT = "AI가 창업지원·사업공간 공고가 아니라고 읽음"
DATE_UNVERIFIED = "기준일 확인 실패: AI가 적은 공고일·기준일(찍힌 기준일)을 근거 문장에서 확인하지 못함"
FRAME_INVALID = "틀 검사 실패"
NO_AI = "AI 읽기 없음"
NO_FALLBACK = "구간 칸 규칙으로도 틀을 만들지 못함(K-Startup 칸·게시일 없음)"
REGION_UNDECIDED = "지역 미정(사업공간은 공간 위치, 창업지원은 지원 지역)"


def policy_frame_detail(policy: dict[str, Any], reading: Any, regions: Any, *, today: Any = None) -> tuple[dict[str, Any] | None, str | None, bool]:
    """policy_frame_with_reason에 더해, 보낼 틀이 구간 칸 규칙 틀(AI 틀이 아님)인지를 함께 돌려줍니다.
    구간 칸 규칙 틀은 원문 글을 읽지 않아 글에만 적힌 조건이 빠져 있을 수 있으므로 틀 전체를 검수 대기(IN_REVIEW)로 보냅니다."""
    startup = policy.get("field") == "STARTUP_SUPPORT"
    if reading is not None and not reading.answer["relevant"]:
        return None, NOT_RELEVANT, False
    reason = NO_AI
    if reading is not None:
        frame = startup_frame(policy, reading, regions) if startup else space_frame(policy, reading, regions, today=today)
        errors = frame_errors(frame) if frame is not None else []
        if frame is not None and not errors:
            return frame, None, False
        if errors:  # 틀 검사에 걸린 AI 틀: 위치만 남기고 구간 칸 규칙으로(값은 남기지 않음)
            log.warning("정책 AI 판정 틀이 틀 검사에 걸렸습니다", extra={"rawPolicyId": policy.get("rawPolicyId"), "errors": errors[:5]})
        reason = FRAME_INVALID if errors else DATE_UNVERIFIED  # 관련 공고인데 space_frame이 None이면 날짜 확인 실패뿐
    fallback = repair(build_startup(policy) if startup else build_space(policy))
    if fallback is not None and not frame_errors(fallback):
        return fallback, None, True
    return None, f"{reason}; {NO_FALLBACK}", False


def policy_frame_with_reason(policy: dict[str, Any], reading: Any, regions: Any, *, today: Any = None) -> tuple[dict[str, Any] | None, str | None]:
    """policy_frame과 같고, 틀을 만들지 못했으면 그 까닭(위 문구)을 함께 돌려줍니다."""
    frame, reason, _ = policy_frame_detail(policy, reading, regions, today=today)
    return frame, reason


def policy_frame(policy: dict[str, Any], reading: Any, regions: Any, *, today: Any = None) -> dict[str, Any] | None:
    """정책 판정 틀: AI 읽기가 있으면 그것으로, 없거나 틀 검사를 통과하지 못하면 K-Startup 구간 칸 규칙으로(startup·space).
    AI가 창업 지원·사업공간 모집이 아니라고 읽었으면 None(보내지 않음). today는 사업공간 공고에 기준일이 없을 때 쓰는 판정일(시험용, 기본은 지금)."""
    return policy_frame_with_reason(policy, reading, regions, today=today)[0]


def not_sent_reason(policy: dict[str, Any], frame: dict[str, Any] | None, frame_reason: str | None, regions: Any, reading: Any = None) -> str:
    """policy_completed_payload가 None일 때 그 까닭."""
    if frame is None:
        return frame_reason or FRAME_INVALID
    if policy.get("field") not in POLICY_FIELDS:
        return "판정 틀이 없는 분야"
    return REGION_UNDECIDED if policy_region_codes(policy, regions, reading) is None else "알 수 없음"


# 신청 기간 칸 글자 전체가 상시·수시·연중 모집이라는 말뿐일 때(「상시」, 「상시 접수」, 「연중 수시 모집」)
_ALWAYS_TEXT = re.compile(r"[\s(]*(?:(?:상시|수시|연중)\s*)+(?:모집|접수|신청)?[\s)]*")
YOUTH_ALWAYS_OPEN = "0057002"  # 온통청년 신청 기간 구분(aplyPrdSeCd): 0057002 상시
# 계약 detailUrl은 format uri: 받는 쪽 검사기가 거절하지 않게 RFC 3986 글자만(한글·공백이 그대로 든 주소는 보내지 않음)
URI_CHARS = re.compile(r"[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")


def policy_apply_always(policy: dict[str, Any]) -> bool:
    """상시 모집인지. 출처가 칸으로 분명히 알려 준 경우만 true: 온통청년 신청 기간 구분이 상시(0057002)이거나, 신청 기간 칸 글자 전체가
    상시·수시·연중 모집이라는 말뿐일 때. 제목·본문의 「상시 모집」은 일부 모집이나 지난 안내일 수 있어 쓰지 않습니다(모르면 false)."""
    record = policy.get("record") or {}
    if str(record.get("aplyPrdSeCd") or "") == YOUTH_ALWAYS_OPEN:
        return True
    return any(_ALWAYS_TEXT.fullmatch(text) for key in PERIOD_TEXT_FIELDS if (text := str(record.get(key) or "")).strip())


# 신청 기간 칸 글자 전체가 「예산(자금) 소진 시까지」뿐일 때. 상시 모집은 아니지만(언제든 끝날 수 있음) 지금 열려 있어 목록에 보여 줘요
_UNTIL_BUDGET_TEXT = re.compile(r"[\s(]*(?:예산|자금|재원|사업비)\s*(?:소진|소요)\s*시\s*(?:까지|마감)\s*(?:모집|접수|신청)?[\s)]*")
UNTIL_BUDGET = "예산 소진 시까지"


def policy_apply_note(policy: dict[str, Any]) -> str | None:
    """마감일 대신 쓰는 신청 기간 안내. 출처의 신청 기간 칸 글자 전체가 「예산 소진 시까지」류일 때만 「예산 소진 시까지」, 아니면 None.
    날짜가 있거나 상시 모집이면 None(그 칸으로 충분해요)."""
    if policy_apply_always(policy) or any(policy_apply_period(policy)):
        return None
    record = policy.get("record") or {}
    texts = [str(record.get(key) or "") for key in PERIOD_TEXT_FIELDS]
    return UNTIL_BUDGET if any(_UNTIL_BUDGET_TEXT.fullmatch(t) for t in texts if t.strip()) else None


def policy_detail_url(policy: dict[str, Any]) -> str | None:
    """사람이 열어볼 원문 주소(raw.policy.collected의 detailUrl). http(s) 주소가 아니거나, URI 글자가 아닌 글자가 있거나,
    인증 값·사용자 정보가 든 주소(계약 PRIVATE_URL)면 None."""
    url = str(policy.get("detailUrl") or "").strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc or not URI_CHARS.fullmatch(url) or tools().private_url(url):
        return None
    return url


# 요약 글의 지원 금액 구절: 「최대 1억 원」「최고 5,000만원」「한도 3천만 원」
_AMOUNT = re.compile(r"(?:최대|최고|한도|기업당|팀당|과제당)\s*[0-9][0-9,.]*\s*(?:억|천만|백만|만|천)?\s*원")
_TAGS = re.compile(r"<[^>]+>")
# 「10,000천원」처럼 천 원 단위로 적은 금액(기업마당). 10으로 나눠떨어질 때만 만 원으로 바꿔요(「최대 10,000천원」 → 「최대 1,000만원」)
_THOUSANDS = re.compile(r"([0-9][0-9,]*)\s*천\s*원")


def _readable_amount(text: str) -> str:
    """금액 구절의 천 원 단위를 만 원으로. 값은 그대로이고, 10으로 나눠떨어지지 않으면(「1,005천원」) 원문 그대로 둬요."""

    def to_man(found: re.Match[str]) -> str:
        value = int(found.group(1).replace(",", ""))
        return f"{value // 10:,}만원" if value and value % 10 == 0 else found.group(0)

    return _THOUSANDS.sub(to_man, text)


POLICY_INFO_TEXT_MAX = 1000


def _text(value: Any, limit: int = POLICY_INFO_TEXT_MAX) -> str | None:
    """HTML 태그 · 이어진 빈칸을 정리한 글. 비었으면 None, 길면 limit 글자까지."""
    if value is None:
        return None
    lines = re.sub(r"(?i)</p>|<br\s*/?>", "\n", str(value))
    cleaned = re.sub(r"[ \t]+", " ", _TAGS.sub(" ", lines).replace("&nbsp;", " "))
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned).strip()
    return cleaned[:limit] or None


def _url(value: Any) -> str | None:
    """http(s) 주소만 (policy_detail_url과 같은 검사). 「dvic.dongguk.edu/…」처럼 scheme이 없으면 https를 붙여 봐요."""
    url = str(value or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    return policy_detail_url({"detailUrl": url}) if url else None


def policy_info(policy: dict[str, Any]) -> dict[str, Any] | None:
    """출처 API 칸을 그대로 옮긴 안내(계약 policyInfo): 지원 분야 · 요약 · 기관 · 문의처 · 접수 방법 · 신청/안내 주소 · 지원 금액 구절.
    판정 틀(AI)에 없는 값을 화면에 보여 주려고 씁니다. K-Startup · 기업마당만, 그 밖의 출처나 칸이 하나도 없으면 None."""
    record = policy.get("record") if isinstance(policy.get("record"), dict) else {}
    source = policy.get("sourceCode")
    if source == "kstartup":
        methods = [
            ("온라인", record.get("aply_mthd_onli_rcpt_istc")),
            ("이메일", record.get("aply_mthd_eml_rcpt_istc")),
            ("방문", record.get("aply_mthd_vst_rcpt_istc")),
            ("우편", record.get("aply_mthd_pssr_rcpt_istc")),
            ("팩스", record.get("aply_mthd_fax_rcpt_istc")),
            ("기타", record.get("aply_mthd_etc_istc")),
        ]
        info = {
            "supportArea": _text(record.get("supt_biz_clsfc"), 100),
            "summary": _text(record.get("pbanc_ctnt")),
            "organization": _text(record.get("pbanc_ntrp_nm"), 100),
            "contact": _text(" ".join(filter(None, [record.get("biz_prch_dprt_nm"), record.get("prch_cnpl_no")])), 200),
            "applyMethod": _text(" · ".join(f"{name} {_text(value, 200)}" for name, value in methods if _text(value)), 500),
            "applyUrl": _url(record.get("biz_aply_url")),
            "guideUrl": _url(record.get("biz_gdnc_url")),
        }
    elif source == "bizinfo":
        info = {
            "supportArea": _text(record.get("pldirSportRealmMlsfcCodeNm") or record.get("pldirSportRealmLclasCodeNm"), 100),
            "summary": _text(record.get("bsnsSumryCn")),
            "organization": _text(record.get("excInsttNm") or record.get("jrsdInsttNm"), 100),
            "contact": _text(record.get("refrncNm"), 200),
            "applyMethod": _text(record.get("reqstMthPapersCn"), 500),
            "applyUrl": None,
            "guideUrl": None,
        }
    else:
        return None
    found = _AMOUNT.search(info["summary"] or "") or _AMOUNT.search(str(policy.get("text") or ""))
    info["amountText"] = _readable_amount(re.sub(r"\s+", " ", found.group(0))) if found else None
    return info if any(info.values()) else None


def policy_review_status(frame: dict[str, Any], *, by_rules: bool = False) -> str:
    """정책 판정 틀의 검수 상태(사용자 결정 2026-10-23).
    - IN_REVIEW: 틀 전체를 믿을 수 없음 — 구간 칸 규칙 틀(AI 틀이 틀 검사·기준일 확인에 걸렸거나 AI가 읽지 못함). 받는 쪽은 이전 공개본을 유지하고,
      첫 버전이면 승인(APPROVED) 전까지 공개하지 않습니다.
    - PARTIALLY_PASSED: 틀은 쓰되 일부 조건만 확인 필요 — 확인 필요(inReview) 조건이 있거나, 원문에 기준일이 없어 판정일을 기준일로 쓴 틀(선택 B).
      판정은 inReview 조건을 확인 필요로 다룹니다. 정책 이벤트는 heldItems가 없습니다(보류는 조건마다 inReview로).
    - AUTO_PASSED: 확인 필요 조건이 없음."""
    if by_rules:
        return "IN_REVIEW"
    every = [*frame["common"], *(c for g in frame["groups"] for c in g["criteria"]), *(c for p in frame["preferences"] for c in p["criteria"])]
    return "PARTIALLY_PASSED" if _in_review(every) or uses_judging_date(frame) else "AUTO_PASSED"


def policy_completed_payload(
    policy: dict[str, Any], frame: dict[str, Any] | None, regions: Any, reading: Any = None, *, by_rules: bool = False
) -> dict[str, Any] | None:
    """정책 판정 틀 → extraction.completed payload(판정 요청안 2026-10-22: 틀은 이 이벤트의 judgment, rawPostId는 rawPolicyId).
    상세(notice)·자격 조건(conditions)은 주거 공고용이라 없습니다. 틀이 없거나 지역(policy_region_codes: 창업지원은 지원 지역,
    사업공간은 공간 소재지)을 정하지 못하면 None(보내지 않음).
    검수 상태는 policy_review_status(by_rules: 구간 칸 규칙 틀이면 IN_REVIEW). 접수 기간은 policy_apply_period,
    원문 주소는 policy_detail_url, 상시 모집 여부는 policy_apply_always, 「예산 소진 시까지」는 policy_apply_note."""
    codes = policy_region_codes(policy, regions, reading)
    if frame is None or codes is None or policy.get("field") not in POLICY_FIELDS:
        return None
    start, end = policy_apply_period(policy)
    return {
        "rawPostId": policy["rawPolicyId"],
        "rawVersion": policy["version"],
        "field": policy["field"],
        "title": policy["title"],
        "conditions": [],
        "reviewStatus": policy_review_status(frame, by_rules=by_rules),
        "provider": policy.get("agency"),
        "regionCode": None,
        "regionCodes": codes,
        "schedule": {"applyStartOn": start, "applyEndOn": end} if start or end else None,
        "applicationWindows": [],
        "summary": None,
        "reprocess": bool(policy.get("reprocess")),
        "detailUrl": policy_detail_url(policy),
        "applyAlways": policy_apply_always(policy),
        "applyNote": policy_apply_note(policy),
        "policyInfo": policy_info(policy),
        "judgment": frame,
    }
