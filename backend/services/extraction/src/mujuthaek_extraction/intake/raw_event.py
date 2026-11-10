"""raw.notice.collected v1 이벤트 해석.

계약 원문은 collector가 소유합니다(contracts/events/raw.notice.collected.v1.json, 담당자 1 PR).
이 모듈은 어댑터가 안전하게 사용할 최소 형식만 확인하고, 전체 JSON Schema 검사는 소비자 쪽 공통 검사에 맡깁니다.
"""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from mujuthaek_extraction.intake.model import RawFile, RawNoticeCollected

EVENT_TYPE = "raw.notice.collected"
SCHEMA_VERSION = 1
KINDS = {"NOTICE", "CORRECTION", "FOLLOW_UP"}
FIELDS = {"HOUSING", "BUSINESS_SPACE"}  # 정책·창업지원은 raw.policy.collected로 따로 옵니다
# 모두 fullmatch로 사용합니다(끝의 줄바꿈 허용 안 함). UUID는 JSON Schema format: uuid와 같은 하이픈 표기만 받습니다.
SHA256 = re.compile(r"[0-9a-f]{64}")
SOURCE_CODE = re.compile(r"[a-z][a-z0-9_]*")  # 예: sh, lh_myhome (팀 이벤트 흐름 문서 2026-10-15)
REGION_CODE = re.compile(r"[0-9]{5}")
UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
# 첨부 칸 (팀 문서 「공고 원본 파일 S3 저장 구조와 전달 흐름」, 2026-10-19 계약에 필수로 추가)
S3_KEY = re.compile(r"raw/[a-z]+/.+")  # raw/{출처}/{글 키}/v{버전}/{순번}-{파일명}
FILE_TYPES = {"pdf", "hwp", "hwpx", "xlsx", "xlsm", "xls"}
FILE_ROLES = {"NOTICE_DOC", "UNIT_LIST"}
FILE_EXT = re.compile(r"\.([0-9a-z]+)\s*$", re.IGNORECASE)  # fileType 칸이 없는 이전 형식 이벤트에서 이름으로 형식을 읽을 때만 씁니다


class InvalidRawEvent(ValueError):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def _get(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise InvalidRawEvent(f"{path}/{key}", "필수 값이 없습니다.")
    return data[key]


def _str(data: Mapping[str, Any], key: str, path: str, *, nullable: bool = False, pattern: re.Pattern[str] | None = None) -> str | None:
    value = _get(data, key, path)
    if value is None and nullable:
        return None
    if not isinstance(value, str) or (pattern is not None and not pattern.fullmatch(value)):
        raise InvalidRawEvent(f"{path}/{key}", "문자열 형식이 맞지 않습니다.")
    return value


def _uuid(data: Mapping[str, Any], key: str, path: str, *, nullable: bool = False) -> str | None:
    value = _str(data, key, path, nullable=nullable)
    if value is not None and not UUID_TEXT.fullmatch(value):
        raise InvalidRawEvent(f"{path}/{key}", "UUID가 아닙니다.")
    return value


def _date(data: Mapping[str, Any], key: str, path: str) -> str | None:
    value = _str(data, key, path, nullable=True)
    if value is None:
        return None
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise InvalidRawEvent(f"{path}/{key}", "YYYY-MM-DD 날짜가 아닙니다.") from None
    return value


def _unit_value_ok(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(isinstance(x, str) for x in value)
    return isinstance(value, str | int | bool)


def _int(data: Mapping[str, Any], key: str, path: str, minimum: int) -> int:
    value = _get(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InvalidRawEvent(f"{path}/{key}", f"{minimum} 이상의 정수가 아닙니다.")
    return value


# 팀 이벤트 흐름 문서(2026-10-15): 필수는 rawPostId·version·sourceCode·field·title·text뿐이고 나머지는 선택입니다.
OPTIONAL_DEFAULTS: dict[str, Any] = {
    "kind": "NOTICE",
    "provider": None,
    "regionCode": None,
    "postedOn": None,
    "detailUrl": None,
    "supersedesPostId": None,
    "textKey": None,
    "units": [],
    "files": [],
    "reprocess": False,
    "apiData": None,  # 선택: 기관 API 응답 JSON (모양은 API마다 다름, 받은 그대로). 칸 이름은 collector와 확정 전 임시
}


def parse_raw_event(event: Any) -> RawNoticeCollected:
    """공통 봉투와 payload를 불변 객체로 바꿉니다. 형식이 틀리면 InvalidRawEvent를 냅니다."""
    if not isinstance(event, Mapping):
        raise InvalidRawEvent("", "이벤트가 객체가 아닙니다.")
    if _get(event, "eventType", "") != EVENT_TYPE:
        raise InvalidRawEvent("/eventType", f"{EVENT_TYPE} 이벤트가 아닙니다.")
    version = _get(event, "schemaVersion", "")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise InvalidRawEvent("/schemaVersion", f"지원하는 봉투 버전은 정수 {SCHEMA_VERSION}입니다.")
    event_id = _uuid(event, "eventId", "")
    trace_id = event.get("traceId")
    if trace_id is not None and not isinstance(trace_id, str):
        raise InvalidRawEvent("/traceId", "문자열이나 null이 아닙니다.")
    payload = _get(event, "payload", "")
    if not isinstance(payload, Mapping):
        raise InvalidRawEvent("/payload", "payload가 객체가 아닙니다.")
    payload = {**OPTIONAL_DEFAULTS, **payload}

    p = "/payload"
    kind = _str(payload, "kind", p)
    if kind not in KINDS:
        raise InvalidRawEvent(f"{p}/kind", "알 수 없는 공고 종류입니다.")
    field = _str(payload, "field", p)
    if field not in FIELDS:
        raise InvalidRawEvent(f"{p}/field", "알 수 없는 공고 분야입니다.")
    title = _str(payload, "title", p)
    if not title.strip():
        raise InvalidRawEvent(f"{p}/title", "제목이 비어 있습니다.")
    provider = _str(payload, "provider", p, nullable=True)
    if provider is not None and not provider.strip():
        raise InvalidRawEvent(f"{p}/provider", "공급 기관이 비어 있습니다.")
    reprocess = _get(payload, "reprocess", p)
    if not isinstance(reprocess, bool):
        raise InvalidRawEvent(f"{p}/reprocess", "true/false가 아닙니다.")
    units = _get(payload, "units", p)
    if not isinstance(units, list) or not all(isinstance(u, Mapping) for u in units):
        raise InvalidRawEvent(f"{p}/units", "객체 배열이 아닙니다.")
    for index, unit in enumerate(units):
        for key, value in unit.items():
            if not isinstance(key, str) or not _unit_value_ok(value):
                raise InvalidRawEvent(f"{p}/units/{index}/{key}", "문자열·숫자·true/false·문자열 배열 값이 아닙니다.")
    files = _get(payload, "files", p)
    if not isinstance(files, list):
        raise InvalidRawEvent(f"{p}/files", "배열이 아닙니다.")
    api_data = payload["apiData"]
    if api_data is not None and not isinstance(api_data, Mapping | list):
        raise InvalidRawEvent(f"{p}/apiData", "JSON 객체나 배열이 아닙니다.")

    return RawNoticeCollected(
        event_id=event_id,
        raw_post_id=_uuid(payload, "rawPostId", p),
        version=_int(payload, "version", p, 1),
        source_code=_str(payload, "sourceCode", p, pattern=SOURCE_CODE),
        provider=provider,
        region_code=_str(payload, "regionCode", p, nullable=True, pattern=REGION_CODE),
        field=field,
        kind=kind,
        title=title,
        posted_on=_date(payload, "postedOn", p),
        detail_url=_str(payload, "detailUrl", p, nullable=True),
        supersedes_post_id=_uuid(payload, "supersedesPostId", p, nullable=True),
        text=_str(payload, "text", p),
        text_key=_str(payload, "textKey", p, nullable=True),
        units=tuple(copy.deepcopy(dict(u)) for u in units),
        files=tuple(_file(f, i) for i, f in enumerate(files)),
        reprocess=reprocess,
        api_data=copy.deepcopy(api_data),
    )


def _file(value: Any, index: int) -> RawFile:
    path = f"/payload/files/{index}"
    if not isinstance(value, Mapping):
        raise InvalidRawEvent(path, "객체가 아닙니다.")
    name = _str(value, "name", path)
    # 새 칸(fileType·role·s3Key)은 있으면 계약대로 엄격히 검사하고, 없으면(칸을 추가하기 전 collector의 이전 형식) 이름으로 채웁니다
    if "fileType" in value:
        file_type = _str(value, "fileType", path)
        if file_type not in FILE_TYPES:
            raise InvalidRawEvent(f"{path}/fileType", "지원하지 않는 파일 형식입니다.")
    else:
        # collector(core/files.py FILE_EXT)처럼 이름 끝 공백을 허용해 확장자를 읽습니다(「모집공고문.pdf 」)
        found = FILE_EXT.search(name.strip())
        file_type = found.group(1).lower() if found else ""
    if "role" in value:
        role = _str(value, "role", path)
        if role not in FILE_ROLES:
            raise InvalidRawEvent(f"{path}/role", "지원하지 않는 첨부 역할입니다.")
    else:
        role = "UNIT_LIST" if file_type.startswith("xls") else "NOTICE_DOC"
    return RawFile(
        index=index,
        name=name,
        download_url=_str(value, "downloadUrl", path),
        sha256=_str(value, "sha256", path, pattern=SHA256),
        file_type=file_type,
        role=role,
        s3_key=_str(value, "s3Key", path, nullable=True, pattern=S3_KEY) if "s3Key" in value else None,
        s3_key_given="s3Key" in value,
    )
