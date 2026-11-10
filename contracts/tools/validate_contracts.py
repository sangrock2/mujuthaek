"""Offline contract checks. Source authenticity is the extraction verifier's responsibility."""

from __future__ import annotations

import argparse
import calendar
import json
import re
from datetime import datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://mujuthaek.kr/contracts/"
SCHEMAS = {}
for folder in ("schemas", "events"):
    for path in (ROOT / folder).glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if "$schema" in value:
            SCHEMAS[f"{folder}/{path.name}"] = value
REGISTRY = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS.values())
# Per-attribute unit/operator/value rules live in the shared dictionary, not in eligibility.v1.json.
ATTRIBUTE_DICTIONARY = json.loads((ROOT / "schemas/eligibility-attributes.v1.json").read_text(encoding="utf-8"))
ATTRIBUTES = {a["code"]: a for a in ATTRIBUTE_DICTIONARY["attributes"]}
CONDITION_FIELDS = json.loads((ROOT / "mappings/extraction-projection.v1.json").read_text(encoding="utf-8"))["conditionFields"]
LIST_OPERATORS = {"IN", "NOT_IN", "BETWEEN"}
KST = timezone(timedelta(hours=9))
SECTIONS = ("notice", "locations", "schedules", "supplyGroups", "eligibility", "selectionRules", "requiredDocuments", "guidance")
CRITICAL_SECTIONS = {"notice", "eligibility"}  # 판정·목록에 직접 쓰는 섹션 (2026-10-15 검수 등급 결정)
# Source claims with field-level confidence/evidence, excluding IDs and operational metadata.
CLAIM_KEYS = {
    "title",
    "publisher",
    "field",
    "supplyType",
    "announcedOn",
    "description",
    "targetGroups",
    "region",
    "buildingName",
    "complexName",
    "address",
    "regionCode",
    "rawLabel",
    "channels",
    "startsAt",
    "endsAt",
    "endCondition",
    "applicationUrl",
    "applicationMode",
    "priorityRank",
    "value",
    "amountKrw",
    "sourceAmount",
    "sourceUnit",
    "taxTreatment",
    "vatRate",
    "billingPeriod",
    "housingTypeCode",
    "buildingUse",
    "exclusiveAreaSqm",
    "exclusiveAreaRange",
    "amountRangeKrw",
    "unitLabel",
    "floor",
    "commonAreaSqm",
    "initialMonths",
    "renewalMonths",
    "maxMonths",
    "originalText",
    "appliesTo",
    "referenceTime",
    "points",
    "maxPoints",
    "order",
    "name",
    "submissionTime",
    "basis",
    "phone",
    "url",
    "places",
    "applicationEmail",
    "dailyHours",
    "breaks",
    "excludedDays",
    "timeNote",
    "copies",
    "issuer",
}
# 신청 방법의 정해진 순서(notice-common applicationChannel). 공고 전체 신청 방법(notice.applicationChannels)은 이 순서로 적습니다
APPLICATION_CHANNELS = ("ONLINE", "ONSITE", "EMAIL", "MAIL", "FAX")



def _section(entry):
    return entry["target"].lstrip("/").split("/", 1)[0]


READY_STATUSES = {"PASSED", "PARTIALLY_PASSED"}
SETTLED_REASONS = {"NOT_IN_SOURCE", "NOT_APPLICABLE", "TO_BE_ANNOUNCED"}  # 원문이 없다·해당 없다·추후 통보라고 확인된 빈칸
# 부분 완료로도 보류할 수 없는 곳: 공고 정체성·입력·원본 문서. 여기에 문제가 있으면 공고 전체가 검수입니다
BLOCKING_TOP = {"notice", "input", "documents", "sourceReferences", "evidence", "quality", ""}
# 공고 기본 정보(/notice) 중 칸 단위로 보류할 수 있는 것(2026-10-20 결정). 제목·기관·분야는 공고를 알아보는 정체성이라 보류할 수 없습니다.
# 실측: 남은 공고 전체 검수 7건 중 4건이 API 공고일 불일치(API 쪽이 틀림)였고, 공고일 하나 때문에 공고 전체가 게시되지 않았습니다.
# 보류한 칸은 받는 쪽이 목록·중복 판단·알림에 쓰지 않습니다.
NOTICE_HOLDABLE = {"announcedOn", "supplyType", "description", "targetGroups", "counts"}


def under_held(path, held):
    return any(path == target or path.startswith(target + "/") for target in held)


def overlaps_held(path, held):
    """path가 보류 범위와 겹치는지: 같거나, 보류 범위 안이거나, 보류 범위를 품는 경우(조건의 rule만 보류해도 그 조건은 보류)."""
    return under_held(path, held) or any(target.startswith(path + "/") for target in held)


def holdable(target):
    """보류할 수 있는 위치인지: 공고 전체 문제가 되는 곳(BLOCKING_TOP)이 아니거나, 공고 기본 정보 중 보류 가능한 칸(NOTICE_HOLDABLE) 안."""
    parts = target.lstrip("/").split("/")
    if parts[0] == "notice":
        return len(parts) >= 2 and parts[1] in NOTICE_HOLDABLE
    return parts[0] not in BLOCKING_TOP


def held_target_errors(items, base):
    """보류할 수 없는 곳(BLOCKING_TOP)이나 JSON Pointer가 아닌 대상을 고릅니다."""
    errors = []
    for index, item in enumerate(items):
        target = item["target"]
        if not target.startswith("/") or not holdable(target):
            errors.append(f"HELD_TARGET_NOT_ALLOWED {base}/{index}")
    return errors


def _held_path(data, path):
    """검사 위치 → 보류 범위와 비교할 위치. 섹션 coverage는 그 섹션, 누락 기록은 그 누락이 가리키는 칸."""
    path = path.split(" ", 1)[0]
    if path.startswith("/quality/coverage/"):
        return "/" + path.split("/")[3]
    if path.startswith("/quality/missingFields/"):
        try:
            return resolve(data, path)["target"]
        except (KeyError, IndexError, TypeError, ValueError):
            return path
    return path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def walk(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk(child, f"{path}/{key.replace('~', '~0').replace('/', '~1')}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}/{index}")


def resolve(value, pointer):
    if pointer == "":
        return value
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise KeyError(pointer)
            value = value[int(token)]
        else:
            value = value[token]
    return value


def claim_paths(data):
    result = set()
    for section in SECTIONS:
        for path, node in walk(data[section], f"/{section}"):
            if "evidenceIds" not in node:
                continue
            for key, value in node.items():
                if key in CLAIM_KEYS and value is not None and value != []:
                    result.add(f"{path}/{key}")
    return result


def temporal_bounds(value):
    if value is None:
        return None
    precision, raw = value["precision"], value["value"]
    if precision == "MINUTE":
        point = datetime.fromisoformat(raw)
        return point, point
    if precision == "MONTH":
        year, month = map(int, raw.split("-"))
        start = datetime(year, month, 1, tzinfo=KST)
        end = start + timedelta(days=calendar.monthrange(year, month)[1]) - timedelta(microseconds=1)
    else:
        start = datetime.fromisoformat(raw).replace(tzinfo=KST)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start, end


@cache
def schema_validator(schema_name):
    return Draft202012Validator(SCHEMAS[schema_name], registry=REGISTRY, format_checker=FormatChecker())


def validate(data, schema_name):
    # 입력 값이 포함되는 jsonschema의 error.message는 쓰지 않습니다(schema_message: 칸 이름만, 값은 넣지 않음).
    # 형식: "SCHEMA <위치>: <키워드>: <설명>". 기존 코드가 읽는 오류 코드·JSON Pointer·키워드는 유지합니다
    errors = [f"SCHEMA {schema_path(error)}: {error.validator}: {schema_message(error)}" for error in schema_validator(schema_name).iter_errors(data)]
    if errors:
        return errors
    if schema_name == "events/raw.notice.collected.v1.json":
        return []  # 수집 원본의 자유 형식 API 데이터에 공고 상세의 의미 규칙을 적용하지 않습니다.
    nodes = tuple(walk(data))
    errors = attribute_errors(data, nodes) + region_errors(data, nodes) + secret_errors(data, nodes)
    if schema_name in {"schemas/eligibility.v1.json", "schemas/notice-common.v1.json", "schemas/public-notice-content.v1.json"}:
        return errors  # References require a complete enclosing notice; use extracted/standard validation for those.
    if schema_name == "events/extraction.completed.v1.json":
        return errors + event_errors(data["payload"])
    if schema_name.startswith("events/"):
        return errors
    ready = data.get("reviewStatus") != "APPROVED" and (
        data.get("publicationState") == "APPROVED" or data["quality"]["verification"]["status"] in READY_STATUSES
    )
    return errors + semantic_errors(data, ready)


SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")


def schema_message(error):
    """스키마 오류 설명. jsonschema 메시지는 잘못된 입력값(URL의 인증 값 등)을 그대로 담으므로 쓰지 않고,
    스키마에 적힌 칸 이름이나 입력의 칸 이름(형식이 칸 이름다울 때만)만 남깁니다. 값은 어떤 경우에도 넣지 않습니다."""
    if error.validator == "required" and isinstance(error.instance, dict):
        missing = [name for name in error.validator_value if name not in error.instance]
        return "필수 칸 없음 " + ", ".join(missing)
    if error.validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = set(error.schema.get("properties", {}))
        extra = [name for name in error.instance if name not in allowed]
        shown = [name if SAFE_KEY.fullmatch(name) else "<이름 숨김>" for name in extra]
        return "허용되지 않은 칸 " + ", ".join(shown)
    return "값이 형식에 맞지 않습니다(값은 남기지 않음)"


def schema_path(error):
    return "/" + "/".join(str(x).replace("~", "~0").replace("/", "~1") for x in error.absolute_path)


def event_errors(payload):
    """extraction.completed: 바깥 칸과 상세 notice가 같은 공고·버전·조건을 가리키는지, AUTO_PASSED면 완료 조건을 만족하는지.
    상세 notice가 없는 IN_REVIEW 이벤트도 payload만으로 볼 수 있는 보류 규칙은 검사합니다."""
    errors = []
    notice = payload.get("notice")
    payload_held = payload.get("heldItems", [])
    if notice is None:
        errors += held_target_errors(payload_held, "/payload/heldItems")
        held = [h["target"] for h in payload_held]
    else:
        errors += semantic_errors(notice, ready=payload["reviewStatus"] in {"AUTO_PASSED", "PARTIALLY_PASSED"})
        held = [h["target"] for h in notice["quality"].get("heldItems", [])]
        if payload_held != notice["quality"].get("heldItems", []):
            errors.append("EVENT_HELD_ITEMS_CONFLICT /payload/heldItems")
    errors += judgment_errors(payload)
    # 조건 i = notice.eligibility[i] (EVENT_CONDITIONS_CONFLICT로 순서를 맞춥니다)
    for index, condition in enumerate(payload["conditions"]):
        if overlaps_held(f"/eligibility/{index}", held) and not condition["inReview"]:
            errors.append(f"HELD_CONDITION_NOT_IN_REVIEW /payload/conditions/{index}")
    if notice is None:
        return errors
    incoming = notice["input"]
    if (payload["rawPostId"], payload["rawVersion"], payload["field"]) != (
        incoming["rawPostId"],
        incoming["rawVersion"],
        incoming["field"],
    ):
        errors.append("EVENT_NOTICE_IDENTITY_CONFLICT /payload")
    if [c["id"] for c in payload["conditions"]] != [e["id"] for e in notice["eligibility"]]:
        errors.append("EVENT_CONDITIONS_CONFLICT /payload/conditions")
    else:
        for index, (condition, item) in enumerate(zip(payload["conditions"], notice["eligibility"], strict=True)):
            expected = condition_fields(item)
            # scope는 이전 v1 발행본에 없을 수 있습니다. 상세가 있으면 수신부가 복원합니다.
            if any(condition.get(key) != value for key, value in expected.items() if key != "scope" or key in condition):
                errors.append(f"EVENT_CONDITION_CONTENT_CONFLICT /payload/conditions/{index}")
    if payload["title"] != (notice["notice"]["title"] or notice["sourceReferences"][0]["sourceTitle"]):
        errors.append("EVENT_TITLE_CONFLICT /payload/title")
    if payload.get("reprocess", False) != incoming["reprocess"]:
        errors.append("EVENT_REPROCESS_CONFLICT /payload/reprocess")
    held_targets = [h["target"] for h in notice["quality"].get("heldItems") or []]
    if payload.get("regionCode") != event_region_code(notice["locations"], held_targets):
        errors.append("EVENT_REGION_CONFLICT /payload/regionCode")
    # 승인에서는 자동 검수 이슈를 보존하지만, 사람이 확인한 일정의 투영은 다시 사용합니다.
    approved = payload["reviewStatus"] == "APPROVED"
    if "schedule" in payload and payload["schedule"] != application_schedule(notice, approved=approved):
        errors.append("EVENT_SCHEDULE_CONFLICT /payload/schedule")
    if "applicationWindows" in payload and payload["applicationWindows"] != application_windows(notice, approved=approved):
        errors.append("EVENT_WINDOWS_CONFLICT /payload/applicationWindows")
    return errors


# 분야별 판정 틀(판정 담당이 준 원본 그대로, contracts/schemas/*-judgment.v1.json). 정책(POLICY)은 틀이 없습니다
JUDGMENT_SCHEMAS = {
    "HOUSING": "housing-judgment.v1",
    "BUSINESS_SPACE": "business-space-judgment.v1",
    "STARTUP_SUPPORT": "startup-support-judgment.v1",
    "SPACE_RECRUITMENT": "business-space-judgment.v1",
}
# 정책 수집에서 만든 판정 틀만 실어 오는 분야: 틀과 지원 지역(regionCodes)이 있어야 하고 상세(notice)는 없습니다
POLICY_FRAME_FIELDS = {"STARTUP_SUPPORT", "SPACE_RECRUITMENT"}
# 틀이 가리키는 원본 칸: 창업지원 틀은 수집 이벤트 raw.policy.collected의 rawPolicyId를 씁니다
JUDGMENT_SOURCE_KEY = {"STARTUP_SUPPORT": "rawPolicyId"}
# 정책 이벤트에만 있고 반드시 있는 칸: 원문 주소(없으면 null)와 상시 모집 여부. 공고 분야에는 넣지 않습니다
POLICY_ONLY_KEYS = ("regionCodes", "detailUrl", "applyAlways")


def _any_in_review(node):
    """판정 틀 어디든(안내 notes 제외) inReview가 true인 조건이 있는지."""
    if isinstance(node, dict):
        return node.get("inReview") is True or any(_any_in_review(v) for k, v in node.items() if k != "notes")
    if isinstance(node, list):
        return any(_any_in_review(v) for v in node)
    return False


def _judgment_ids(node):
    if isinstance(node, dict):
        own = [node["id"]] if isinstance(node.get("id"), str) else []
        return own + [i for key, value in node.items() if key != "notes" for i in _judgment_ids(value)]
    if isinstance(node, list):
        return [i for value in node for i in _judgment_ids(value)]
    return []


def judgment_errors(payload):
    """판정 틀(judgment): 분야에 맞는 틀인지, 같은 공고·버전인지, 스키마로 못 잡는 ID 유일성(group·조건·우대)."""
    judgment = payload.get("judgment")
    policy = payload["field"] in POLICY_FRAME_FIELDS
    if policy and (
        judgment is None
        or any(key not in payload for key in POLICY_ONLY_KEYS)
        or "notice" in payload
        or "heldItems" in payload
        or payload["conditions"]
    ):
        return ["EVENT_POLICY_FRAME_SHAPE /payload"]
    if not policy and (extra := [key for key in (*POLICY_ONLY_KEYS, "applyNote") if key in payload]):
        return [f"EVENT_POLICY_FRAME_SHAPE /payload/{extra[0]}"]
    if judgment is None:
        return []
    errors = []
    # 정책 틀의 검수 상태는 틀 전체로 정합니다(heldItems 없음): 확인 필요 조건이 있는 틀은 자동 통과가 아님(PARTIALLY_PASSED 이상)
    if policy and payload["reviewStatus"] == "AUTO_PASSED" and _any_in_review(judgment):
        errors.append("EVENT_POLICY_REVIEW_STATUS /payload/reviewStatus")
    if judgment.get("schema") != JUDGMENT_SCHEMAS.get(payload["field"]):
        errors.append("EVENT_JUDGMENT_FIELD_CONFLICT /payload/judgment/schema")
    source_key = JUDGMENT_SOURCE_KEY.get(payload["field"], "rawPostId")
    if (judgment.get(source_key), judgment.get("rawVersion")) != (payload["rawPostId"], payload["rawVersion"]):
        errors.append("EVENT_JUDGMENT_IDENTITY_CONFLICT /payload/judgment")
    ids = _judgment_ids({k: v for k, v in judgment.items() if k != "notes"})
    if len(ids) != len(set(ids)):
        errors.append("JUDGMENT_DUPLICATE_ID /payload/judgment")
    return errors


def condition_fields(item):
    """상세 자격 조건 → 판정 이벤트의 의미 필드. 검수 표시와 별도로 동일성을 확인합니다."""
    return {name: resolve(item, pointer) for name, pointer in CONDITION_FIELDS.items()}


def application_items(notice, *, approved=False):
    """접수 기간으로 내보낼 신청 일정. 보류 범위와 겹치면(같음·안·품음) 빼고, 검수 이슈는 그 일정 자신이나 그 안을 가리킬 때만 뺍니다.
    섹션 전체를 가리키는 이슈로 모든 일정을 빼지 않습니다
    (실측 2026-10-20 LH 인천부평 행복주택: 근거 없는 발표 일정 하나가 빠진 메모 때문에 접수 기간이 모두 비어 접수 상태를 계산하지 못함).
    표시 메모(notes)로는 빼지 않습니다: 메모는 값이 틀렸다는 신호가 아닌 것만 담는데, 근거 인용 하나가 짧다는 메모(EVIDENCE_QUOTE_TOO_SHORT)
    때문에 하나뿐인 접수 일정이 빠져 마감일을 잃고 마감·D-day 알림이 나가지 않았어요(2026-11-10 재검토, 저장된 gbdc-a909)."""
    quality = notice["quality"]
    held = [h["target"] for h in quality.get("heldItems", [])]
    marked = [] if approved else [x["target"] for x in quality["reviewIssues"]]

    def blocked(path):
        return overlaps_held(path, held) or any(t == path or t.startswith(path + "/") for t in marked)

    return [s for i, s in enumerate(notice["schedules"]) if "APPLICATION" in s["kinds"] and not blocked(f"/schedules/{i}")]


def application_channels(data):
    """공고 전체 신청 방법(notice.applicationChannels)의 정답: 신청(APPLICATION) 일정들의 channels를 합쳐 정해진 순서로.
    신청 일정이 없는 공고(별도 접수 없이 계약으로 바로 신청받는 선착순 공고)는 계약(CONTRACT) 일정들의 channels로 셉니다.
    AI가 쓰지 않고 프로그램이 계산합니다(2026-10-23). 보류 여부와 상관없이 모든 일정을 봅니다(보류에 따라 값이 바뀌지 않게)."""
    applying = [s for s in data["schedules"] if "APPLICATION" in s["kinds"]]
    if not applying:
        applying = [s for s in data["schedules"] if "CONTRACT" in s["kinds"]]
    found = {c for s in applying for c in s["channels"]}
    return [c for c in APPLICATION_CHANNELS if c in found]


def application_day(value):
    if not value or value["precision"] == "MONTH":
        return None
    if value["precision"] == "DAY":
        return value["value"]
    return datetime.fromisoformat(value["value"]).astimezone(KST).date().isoformat()


def application_schedule(notice, *, approved=False):
    # 보류를 제외하기 전에도 공고 전체 일정이 하나여야 합니다.
    whole = [s for s in notice["schedules"]
             if "APPLICATION" in s["kinds"] and s["scope"]["level"] == "NOTICE" and s["scope"]["resolution"] == "RESOLVED"]
    if len(whole) != 1 or whole[0] not in application_items(notice, approved=approved):
        return None
    start, end = application_day(whole[0]["startsAt"]), application_day(whole[0]["endsAt"])
    return {"applyStartOn": start, "applyEndOn": end} if start or end else None


def application_windows(notice, *, approved=False):
    # 날짜 미정 구간도 보존합니다. 이를 버리면 다른 구간의 종료만으로 CLOSED가 됩니다.
    return [{"scheduleId": s["id"], "label": s["rawLabel"],
             "applyStartOn": application_day(s["startsAt"]), "applyEndOn": application_day(s["endsAt"]),
             "priorityRank": s["priorityRank"], "targetGroups": s["scope"]["targetGroups"],
             "scopeDescription": s["scope"]["description"]} for s in application_items(notice, approved=approved)]


def event_region_code(locations, held=()):
    """이벤트 regionCode(5자리 = 시도 2 + 시군구 3)의 정답. 서비스는 앞 5자리(시군구)까지만 씁니다(2026-10-20 결정).
    - 모든 위치의 앞 5자리가 하나면 그 코드(시도까지만 아는 위치면 시도 코드 xx000 = 그 시도)
    - 여러 시군구지만 모두 같은 시도면 그 시도의 xx000 (예: 강남구·서초구 → 11000)
    - 여러 시도에 걸치거나, 코드 없는 위치가 있거나, 위치가 없으면 null
    held(보류 범위 목록)에 걸린 위치·지역 코드는 확정 값이 아니라 코드 없는 위치로 봅니다(2026-10-21: 보류한 지역이 알림·검색 지역으로 쓰이지 않게)."""
    codes = [None if overlaps_held(f"/locations/{i}/regionCode", list(held)) else loc["regionCode"] for i, loc in enumerate(locations)]
    if not codes or any(code is None or not sigungu_code_ok(code[:5]) for code in codes):
        return None
    prefixes = {code[:5] for code in codes}
    if len(prefixes) == 1:
        return prefixes.pop()
    sido = {code[:2] for code in prefixes}
    return sido.pop() + "000" if len(sido) == 1 else None


def sigungu_code_ok(code):
    """5자리 지역 코드 = 시도 2 + 시군구 3. 시군구 자리가 000이면 시도 단위(그 시도 전체 또는 시군구를 모름, 예: 11000 = 서울특별시)입니다.
    시도 자리 00은 없는 코드입니다."""
    return re.fullmatch(r"(?!00)[0-9]{5}", code) is not None


def region_code_ok(code):
    """법정동코드 10자리 = 시도 2 + 시군구 3 + 읍면동 3 + 리 2. 모르는 하위 단계는 0으로 채우고, 0 뒤에 다시 값이 올 수 없습니다."""
    parts = (code[:2], code[2:5], code[5:8], code[8:])
    if parts[0] == "00":
        return False
    zero_seen = False
    for part in parts[1:]:
        if set(part) == {"0"}:
            zero_seen = True
        elif zero_seen:
            return False
    return True


def region_prefix(code):
    """하위 단계 0을 뺀 의미 있는 앞부분. 조상 코드의 앞부분은 자손 코드의 앞부분입니다."""
    for start, end in ((8, 10), (5, 8), (2, 5)):
        if code[start:end] != "0" * (end - start):
            return code[:end]
    return code[:2]


def region_errors(data, nodes=None):
    errors = []
    for path, node in walk(data) if nodes is None else nodes:
        values = [("regionCode", node.get("regionCode"))]
        values += [(f"regionCodes/{i}", c) for i, c in enumerate(node.get("regionCodes") or [])]
        for key, code in values:
            # 자리 수는 스키마가 정합니다: 5자리는 이벤트의 시군구 코드, 10자리는 법정동코드
            ok = sigungu_code_ok if isinstance(code, str) and len(code) == 5 else region_code_ok
            if isinstance(code, str) and not ok(code):
                errors.append(f"REGION_CODE_HIERARCHY {path}/{key}")
    return errors


SECRET_PARAM_PARTS = ("servicekey", "apikey", "authkey", "accesstoken", "token", "signature", "credential")
SECRET_IN_TEXT = re.compile(r"service[_-]*key\s*=", re.IGNORECASE)


def secret_param(name):
    """매개변수 이름을 소문자로 바꾸고 _·-를 뺀 뒤 인증 값 이름인지 봅니다(serviceKey, service_key, X-Amz-Signature …)."""
    name = name.lower().replace("_", "").replace("-", "")
    return name == "key" or any(part in name for part in SECRET_PARAM_PARTS)


def private_url(value):
    try:
        parsed = urlsplit(value)
        names = [n for part in (parsed.query, parsed.fragment) for n, _ in parse_qsl(part, keep_blank_values=True)]
        return bool(parsed.username or parsed.password) or any(secret_param(n) for n in names)
    except ValueError:
        return False


def secret_errors(data, nodes=None):
    """공개 주소 칸(url·…Url)에 사용자 정보나 인증 값 매개변수가 있거나, 어느 글자 값이든 serviceKey= 가 있으면 오류.
    오류에는 위치만 남기고 값은 남기지 않습니다."""
    errors = []
    for path, node in walk(data) if nodes is None else nodes:
        for key, value in node.items():
            values = [(key, value)] if isinstance(value, str) else []
            values += [(f"{key}/{i}", x) for i, x in enumerate(value) if isinstance(x, str)] if isinstance(value, list) else []
            for sub, text in values:
                if ((key == "url" or key.endswith("Url")) and private_url(text)) or SECRET_IN_TEXT.search(text):
                    errors.append(f"PRIVATE_URL {path}/{sub}")
    return errors


def region_covers(ancestor, code):
    return code.startswith(region_prefix(ancestor))


def value_matches(spec, value):
    kind = spec["valueType"]
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "string":
        if not isinstance(value, str) or not value:
            return False
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            return False
        if spec.get("regionCode") and not region_code_ok(value):
            return False
        return "enum" not in spec or value in spec["enum"]
    if isinstance(value, bool) or not isinstance(value, int if kind == "integer" else (int, float)):
        return False
    return "minimum" not in spec or value >= spec["minimum"]


def attribute_errors(data, nodes=None):
    errors = []
    for path, node in walk(data) if nodes is None else nodes:
        if node.get("kind") != "ATOMIC":
            continue
        spec = ATTRIBUTES.get(node["attribute"])
        if spec is None:
            errors.append(f"ATTRIBUTE_UNKNOWN {path}/attribute")
            continue
        if node["unit"] != spec["unit"]:
            errors.append(f"ATTRIBUTE_UNIT_CONFLICT {path}/unit")
        if node["operator"] not in spec["operators"]:
            errors.append(f"ATTRIBUTE_OPERATOR_CONFLICT {path}/operator")
        value = node["value"]
        values = value if node["operator"] in LIST_OPERATORS and isinstance(value, list) else [value]
        if not all(value_matches(spec, x) for x in values):
            errors.append(f"ATTRIBUTE_VALUE_INVALID {path}/value")
        if spec["benchmarkRequired"] and node["benchmark"] is None:
            errors.append(f"BENCHMARK_REQUIRED {path}/benchmark")
    return errors


def dictionary_errors():
    errors = []
    atomic = SCHEMAS["schemas/eligibility.v1.json"]["$defs"]["atomic"]["properties"]
    codes = [a["code"] for a in ATTRIBUTE_DICTIONARY["attributes"]]
    if len(set(codes)) != len(codes):
        errors.append("DICTIONARY_DUPLICATE_CODE")
    for spec in ATTRIBUTE_DICTIONARY["attributes"]:
        if not re.fullmatch(atomic["attribute"]["pattern"], spec["code"]):
            errors.append(f"DICTIONARY_CODE_FORMAT {spec['code']}")
        if spec["unit"] not in atomic["unit"]["enum"]:
            errors.append(f"DICTIONARY_UNIT {spec['code']}")
        if not set(spec["operators"]) <= set(atomic["operator"]["enum"]):
            errors.append(f"DICTIONARY_OPERATOR {spec['code']}")
        if spec["valueType"] not in {"integer", "number", "string", "boolean"}:
            errors.append(f"DICTIONARY_VALUE_TYPE {spec['code']}")
    return errors


def pooled_sum(counts):
    """구성 수량의 합. 같은 allocationPoolId는 함께 쓰는 한 물량이라 한 번만 셉니다(대학생·청년 공동 21호는 42호가 아님)."""
    pools = {c["allocationPoolId"]: c["value"] for c in counts if c.get("allocationPoolId")}
    return sum(c["value"] for c in counts if not c.get("allocationPoolId")) + sum(pools.values())


def semantic_errors(data, ready=False):
    errors = []
    quality = data["quality"]
    partial = quality["verification"]["status"] == "PARTIALLY_PASSED"
    held = [h["target"] for h in quality.get("heldItems", [])] if partial else []

    def error(code, path):
        errors.append(f"{code} {path or '/'}")

    def ready_error(code, path):
        """완료 조건 위반. 부분 완료(PARTIALLY_PASSED)면 보류한 항목·섹션 안의 위반은 허용합니다(그 범위는 쓰지 않음)."""
        if not under_held(_held_path(data, path), held):
            error(code, path)

    nodes = list(walk(data))
    ids = {}
    for path, node in nodes:
        if "id" in node:
            if node["id"] in ids:
                error("DUPLICATE_ID", path)
            ids[node["id"]] = path
    locations = {x["id"]: x for x in data["locations"]}
    groups = {x["id"]: x for x in data["supplyGroups"]}
    documents = {x["id"]: x for x in data["documents"]}
    evidence = {x["id"]: x for x in data["evidence"]}
    counts = {node["id"]: node for _, node in nodes if "aggregationRole" in node}
    count_paths = {node["id"]: path for path, node in nodes if "aggregationRole" in node}
    count_children = {}
    for count in counts.values():
        count_children.setdefault(count["parentCountId"], []).append(count)
    schedules = {x["id"]: x for x in data["schedules"]}
    for path, node in nodes:
        for evidence_id in node.get("evidenceIds", []):
            if evidence_id not in evidence:
                error("DANGLING_EVIDENCE", path)
        if "locationId" in node and node["locationId"] is not None and node["locationId"] not in locations:
            error("DANGLING_LOCATION", path)
        if "parentLocationId" in node:
            parent_id = node["parentLocationId"]
            if parent_id is not None and (
                parent_id not in locations
                or node["kind"] != "BUILDING"
                or locations.get(parent_id, {}).get("kind") != "COMPLEX"
            ):
                error("INVALID_LOCATION_PARENT", path)
        if "scope" in node:
            scope = node["scope"]
            if any(x not in locations for x in scope["locationIds"]) or any(
                x not in groups for x in scope["supplyGroupIds"]
            ):
                error("DANGLING_SCOPE", path)
            for group_id in scope["supplyGroupIds"]:
                location_id = groups.get(group_id, {}).get("locationId")
                if scope["locationIds"] and location_id not in scope["locationIds"]:
                    error("SCOPE_LOCATION_CONFLICT", path)
            if ready and scope["resolution"] != "RESOLVED":
                ready_error("UNRESOLVED_SCOPE", path)
        if node.get("kind") == "ATOMIC":
            value = node["value"]
            if node["operator"] == "BETWEEN" and value[0] > value[1]:
                error("REVERSED_RANGE", path)
            benchmark = node["benchmark"]
            if (
                node["attribute"] == "INCOME_BENCHMARK_PERCENT"
                and benchmark
                and (
                    benchmark["householdScope"] is None
                    or (benchmark["referenceYear"] is None and benchmark["referenceVersion"] is None)
                )
            ):
                error("INCOMPLETE_INCOME_BENCHMARK", path)
        if "startsAt" in node:
            is_application = "APPLICATION" in node["kinds"]
            if is_application == (node["applicationMode"] == "NOT_APPLICABLE"):
                error("APPLICATION_MODE_CONFLICT", path)
            start, end = temporal_bounds(node["startsAt"]), temporal_bounds(node["endsAt"])
            if start and end and start[0] > end[1]:
                error("REVERSED_SCHEDULE", path)
            # 하루 안의 시각 구간(HH:MM)은 글자 비교가 곧 시각 비교입니다
            for key in ("dailyHours", "breaks"):
                for index, span in enumerate(node.get(key) or []):
                    if span["start"] >= span["end"]:
                        error("TIME_RANGE_REVERSED", f"{path}/{key}/{index}")
            for index, place in enumerate(node.get("places") or []):
                if all(place[k] is None for k in ("name", "address", "detail")):
                    error("EMPTY_PLACE", f"{path}/places/{index}")
        # 범위 값(선택 칸): 원문이 범위로만 적었을 때만 쓰고 단일 값과 함께 쓰지 않습니다
        for single, ranged in (("exclusiveAreaSqm", "exclusiveAreaRange"), ("amountKrw", "amountRangeKrw")):
            span = node.get(ranged) if single in node else None
            if span is not None:
                if span["min"] > span["max"]:
                    error("RANGE_REVERSED", f"{path}/{ranged}")
                if node[single] is not None:
                    error("RANGE_WITH_SINGLE_VALUE", f"{path}/{ranged}")
        if "amountKrw" in node:
            expected_period = {"MONTHLY_RENT": "MONTHLY", "ANNUAL_RENT": "ANNUAL"}.get(node["kind"])
            if expected_period and node["billingPeriod"] not in {expected_period, "UNKNOWN"}:
                error("PRICE_PERIOD_CONFLICT", path)
            if node["taxTreatment"] in {"EXEMPT", "NOT_APPLICABLE", "UNKNOWN"} and node["vatRate"] is not None:
                error("VAT_CONFLICT", path)
        if (
            "initialMonths" in node
            and node["initialMonths"]
            and node["maxMonths"]
            and node["initialMonths"] > node["maxMonths"]
        ):
            error("LEASE_TERM_CONFLICT", path)
        if (
            node.get("kind") == "SCORING"
            and node["points"] is not None
            and node["maxPoints"] is not None
            and node["points"] > node["maxPoints"]
        ):
            error("SCORE_EXCEEDS_MAX", path)
        if ready and node.get("exceptionsStatus") == "NOT_REVIEWED":
            ready_error("EXCEPTIONS_NOT_REVIEWED", path)
    for index, item in enumerate(data["evidence"]):
        path = f"/evidence/{index}"
        document = documents.get(item["sourceId"])
        if document is None:
            error("DANGLING_SOURCE", path)
            continue
        locator = item["locator"]
        expected_kind = {"PDF_PAGE": "PDF", "TEXT_RANGE": "TEXT", "UNIT_ROW": "UNITS"}[locator["kind"]]
        if document["kind"] != expected_kind:
            error("LOCATOR_SOURCE_CONFLICT", path)
        if locator["kind"] == "PDF_PAGE":
            if document["pageCount"] is not None and locator["page"] > document["pageCount"]:
                error("PAGE_OUT_OF_RANGE", path)
            if ready and document["pageCount"] is None:
                error("PAGE_COUNT_REQUIRED", path)
        if locator["kind"] == "TEXT_RANGE":
            if locator["start"] >= locator["end"]:
                error("EMPTY_TEXT_RANGE", path)
            # 쪽 표시가 있는 PDF 글자의 쪽 번호(선택): 문서 쪽 수를 알면 그 안이어야 합니다
            page = locator.get("page")
            if page is not None and document["pageCount"] is not None and page > document["pageCount"]:
                error("PAGE_OUT_OF_RANGE", path)
    for count_id, count in counts.items():
        count_path = count_paths[count_id]
        parent_id = count["parentCountId"]
        if parent_id is not None:
            parent = counts.get(parent_id)
            if parent is None or parent["aggregationRole"] != "TOTAL" or parent_id == count_id:
                error("INVALID_COUNT_PARENT", count_path)
            elif parent["kind"] != count["kind"]:
                error("COUNT_CONCEPT_CONFLICT", count_path)
        children = count_children.get(count_id, [])
        if count["aggregationComplete"]:
            if (
                count["aggregationRole"] != "TOTAL"
                or not children
                or count["value"] is None
                or any(c["value"] is None for c in children)
            ):
                error("INCOMPLETE_COUNT_COMPONENTS", count_path)
            elif pooled_sum(children) != count["value"]:
                error("COUNT_SUM_MISMATCH", count_path)
        # 구성을 다 모르는 전체(aggregationComplete=false)라도 아는 구성의 합이 전체보다 클 수는 없습니다
        elif count["value"] is not None and pooled_sum([c for c in children if c["value"] is not None]) > count["value"]:
            error("COUNT_COMPONENTS_EXCEED_TOTAL", count_path)
    references = data["sourceReferences"]
    ref_keys = [(r["sourceCode"], r["rawPostId"], r["rawVersion"]) for r in references]
    if len(set(ref_keys)) != len(ref_keys):
        error("DUPLICATE_SOURCE_REFERENCE", "/sourceReferences")
    for index, item in enumerate(references):
        if item["supersedesPostId"] == item["rawPostId"]:
            error("SELF_SUPERSEDES", f"/sourceReferences/{index}")
        if item["kind"] == "NOTICE" and item["supersedesPostId"] is not None:
            error("NOTICE_HAS_SUPERSEDES", f"/sourceReferences/{index}")
        if ready and item["kind"] != "NOTICE" and item["supersedesPostId"] is None:
            error("UNLINKED_RELATED_NOTICE", f"/sourceReferences/{index}")
    if data["notice"]["applicationChannels"] != application_channels(data):
        error("APPLICATION_CHANNELS_CONFLICT", "/notice/applicationChannels")
    if "input" in data:
        incoming = data["input"]
        if not any(
            r["rawPostId"] == incoming["rawPostId"] and r["rawVersion"] == incoming["rawVersion"] for r in references
        ):
            error("INPUT_REFERENCE_MISMATCH", "/input")
        if data["notice"]["field"] is not None and incoming["field"] != data["notice"]["field"]:
            error("INPUT_FIELD_MISMATCH", "/input/field")
    if "noticeVersion" in data:
        expected_previous = data["noticeVersion"] - 1 if data["noticeVersion"] > 1 else None
        if data["previousNoticeVersion"] != expected_previous:
            error("NOTICE_VERSION_CONFLICT", "/previousNoticeVersion")
        if data["noticeVersion"] == 1 and data["changedFields"]:
            error("INITIAL_VERSION_HAS_CHANGES", "/changedFields")
        if data["noticeVersion"] > 1 and not data["changedFields"]:
            error("UPDATED_VERSION_WITHOUT_CHANGES", "/changedFields")
        summary = data["applicationSummary"]
        basis = summary["basisScheduleIds"]
        if any(x not in schedules or "APPLICATION" not in schedules[x]["kinds"] for x in basis):
            error("INVALID_APPLICATION_BASIS", "/applicationSummary")
        if summary["startsOn"] and summary["endsOn"] and summary["startsOn"] > summary["endsOn"]:
            error("REVERSED_APPLICATION_SUMMARY", "/applicationSummary")
        if summary["status"] in {"UPCOMING", "OPEN", "ROLLING"} and not basis:
            error("APPLICATION_BASIS_REQUIRED", "/applicationSummary")
        if summary["status"] == "ROLLING" and not any(
            schedules[x]["applicationMode"] == "ROLLING" for x in basis if x in schedules
        ):
            error("ROLLING_WITHOUT_EXPLICIT_CONDITION", "/applicationSummary")
        codes = set(data["regionCodes"])
        # 위치 코드는 색인의 같은 코드나 상위 코드(예: 서울 전체 1100000000)로 찾을 수 있어야 합니다.
        if any(
            x["regionCode"] is not None and not any(region_covers(c, x["regionCode"]) for c in codes)
            for x in data["locations"]
        ):
            error("LOCATION_REGION_NOT_INDEXED", "/regionCodes")
        if data["regionScope"] == "UNKNOWN" and codes:
            error("UNKNOWN_REGION_WITH_CODES", "/regionCodes")
    for key, entry in quality["coverage"].items():
        if key != "notice":
            if entry["status"] == "EXTRACTED" and not data[key]:
                error("EMPTY_EXTRACTED_SECTION", f"/quality/coverage/{key}")
            if entry["status"] in {"NOT_APPLICABLE", "NOT_IN_SOURCE", "NOT_ATTEMPTED", "FAILED"} and data[key]:
                error("COVERAGE_CONTENT_CONFLICT", f"/quality/coverage/{key}")
        # 판정에 쓰는 섹션은 완전해야 합니다. 그 밖의 섹션은 근거를 못 찾은 항목을 빼고(PARTIAL) quality.notes에 남긴 채 완료할 수 있습니다
        incomplete = {"PARTIAL", "NOT_ATTEMPTED", "FAILED"} if key in CRITICAL_SECTIONS else {"NOT_ATTEMPTED", "FAILED"}
        if ready and entry["status"] in incomplete:
            ready_error("INCOMPLETE_EXTRACTION", f"/quality/coverage/{key}")
    for collection in ["missingFields", "reviewIssues", "notes"]:
        seen = set()
        for index, entry in enumerate(quality[collection]):
            if collection == "missingFields" and entry["target"] in seen:
                error("DUPLICATE_FIELD_RECORD", f"/quality/{collection}/{index}")
            seen.add(entry["target"])
            try:
                target_value = resolve(data, entry["target"])
            except (KeyError, IndexError, TypeError, ValueError):
                error("DANGLING_FIELD_POINTER", f"/quality/{collection}/{index}")
                continue
            if collection == "missingFields" and target_value is not None and target_value != []:
                error("MISSING_FIELD_HAS_VALUE", f"/quality/{collection}/{index}")
            if ready and collection == "missingFields" and entry["reason"] not in SETTLED_REASONS and _section(entry) in CRITICAL_SECTIONS:
                ready_error("UNRESOLVED_MISSING_FIELD", f"/quality/{collection}/{index}")
    comparison = quality["verification"]["apiComparison"]
    identity = comparison["referenceIdentity"]
    if identity is not None and not any(all(r[k] == identity[k] for k in identity) for r in references):
        error("API_REFERENCE_IDENTITY_CONFLICT", "/quality/verification/apiComparison/referenceIdentity")
    statuses = [x["status"] for x in comparison["fields"]]
    if comparison["status"] == "MATCHED" and ("MATCH" not in statuses or "MISMATCH" in statuses):
        error("INVALID_API_MATCH", "/quality/verification/apiComparison")
    if comparison["status"] == "MISMATCH" and "MISMATCH" not in statuses:
        error("INVALID_API_MISMATCH", "/quality/verification/apiComparison")
    if comparison["status"] == "NO_COMPARABLE_FIELDS" and any(s != "NOT_COMPARABLE" for s in statuses):
        error("API_COMPARABLE_FIELD_FOUND", "/quality/verification/apiComparison")
    for index, field in enumerate(comparison["fields"]):
        if field["status"] == "MATCH" and (
            field["expected"] is None
            or type(field["expected"]) is not type(field["actual"])
            or field["expected"] != field["actual"]
        ):
            error("FALSE_API_MATCH", f"/quality/verification/apiComparison/fields/{index}")
        if field["status"] == "MISMATCH" and field["expected"] == field["actual"]:
            error("FALSE_API_MISMATCH", f"/quality/verification/apiComparison/fields/{index}")
        if field["status"] == "NOT_COMPARABLE" and field["reason"] is None:
            error("COMPARISON_REASON_REQUIRED", f"/quality/verification/apiComparison/fields/{index}")
        try:
            if resolve(data, field["target"]) != field["actual"]:
                error("API_ACTUAL_VALUE_CONFLICT", field["target"])
        except (KeyError, IndexError, TypeError, ValueError):
            error("DANGLING_API_TARGET", field["target"])
    for index, item in enumerate(quality.get("heldItems", [])):
        try:
            resolve(data, item["target"])
        except (KeyError, IndexError, TypeError, ValueError):
            error("DANGLING_HELD_TARGET", f"/quality/heldItems/{index}")
    errors += held_target_errors(quality.get("heldItems", []), "/quality/heldItems")
    # 함께 쓰는 모집 물량(allocationPoolId): 같은 ID는 같은 종류·값이어야 합니다(합산하지 않는 한 물량)
    pools = {}
    for path, node in nodes:
        if "aggregationRole" in node and node.get("allocationPoolId"):
            first = pools.setdefault(node["allocationPoolId"], (node["kind"], node["value"]))
            if first != (node["kind"], node["value"]):
                error("ALLOCATION_POOL_CONFLICT", path)
    if ready:
        if quality["verification"]["status"] not in READY_STATUSES:
            error("VERIFICATION_REQUIRED", "/quality/verification")
        if partial and not held:
            error("HELD_ITEMS_REQUIRED", "/quality/heldItems")
        for index, issue in enumerate(quality["reviewIssues"]):
            if not partial:
                error("UNRESOLVED_REVIEW_ISSUES", "/quality/reviewIssues")
                break
            if not under_held(_held_path(data, issue["target"]), held):
                error("REVIEW_ISSUE_NOT_HELD", f"/quality/reviewIssues/{index}")
        if partial:  # API 불일치로 부분 게시하려면 불일치한 칸이 모두 보류돼 있어야 합니다(보류 밖이면 틀린 값이 게시됨)
            for index, field in enumerate(quality["verification"]["apiComparison"]["fields"]):
                if field["status"] == "MISMATCH" and not under_held(field["target"], held):
                    error("API_MISMATCH_NOT_HELD", f"/quality/verification/apiComparison/fields/{index}")
        if any(data["notice"][k] is None for k in ("title", "publisher", "field", "supplyType")):
            error("MISSING_NOTICE_CORE", "/notice")
        critical_unknowns = ["/notice/announcedOn"]
        critical_unknowns += [f"/locations/{i}/regionCode" for i in range(len(data["locations"]))]
        critical_unknowns += [
            f"/supplyGroups/{i}/prices/{j}/amountKrw"
            for i, group in enumerate(data["supplyGroups"])
            for j, price in enumerate(group["prices"])
            if price.get("amountRangeKrw") is None  # 범위로 적은 가격은 그 범위가 값입니다
        ]
        explained = {x["target"] for x in quality["missingFields"]}
        for pointer in critical_unknowns:
            if resolve(data, pointer) is None and pointer not in explained:
                ready_error("UNKNOWN_REASON_REQUIRED", pointer)
    return errors


def check_all():
    failures = dictionary_errors()
    for schema in SCHEMAS.values():
        Draft202012Validator.check_schema(schema)
    manifest = load(ROOT / "examples" / "manifest.json")
    for case in manifest["examples"]:
        data = load(ROOT / "examples" / case["file"])
        errors = validate(data, case["schema"])
        if errors:
            failures.extend(f"{case['file']}: {e}" for e in errors)
        else:
            print(f"PASS {case['file']}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?")
    parser.add_argument("--schema", choices=sorted(SCHEMAS), default="schemas/standard-notice.v1.json")
    args = parser.parse_args()
    failures = validate(load(args.file), args.schema) if args.file else check_all()
    for error in failures:
        print(error)
    if not failures:
        print("Contract validation passed (offline; no API calls).")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
