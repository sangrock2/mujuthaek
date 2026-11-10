"""V4 API 원본 대조. 추출이 끝난 뒤에만 API 값을 사용합니다(추출 입력에 넣지 않음).

- 같은 공고·같은 버전의 API 원본인지(원천·기관 공고 ID·rawPostId·rawVersion·해시) 먼저 확인합니다.
- 대조표(mappings/*.json)에 있는 겹치는 필드만 비교합니다. API에 없는 상세 조건은 일치했다고 하지 않습니다.
- 계약상 MATCH는 기대값과 추출값이 완전히 같아야 합니다. API가 날짜만 주고 추출값이 시각까지 있으면 날짜가 같아도
  NOT_COMPARABLE(사유: 날짜는 같음)로 남깁니다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Any

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.model import ApiReference
from mujuthaek_extraction.verify.model import Finding

KST = timezone(timedelta(hours=9))
EMPTY_API_VALUES = {"", "공고문참조", "-"}


@cache
def mapping_registry() -> dict[str, dict[str, Any]]:
    """원천 코드 → 대조표. 파일 이름은 <원천>.v<버전>.json이고, 원천 코드 "*"는 공통 대조표입니다."""
    registry = {}
    for path in sorted(Path(__file__).with_name("mappings").glob("*.json")):
        table = json.loads(path.read_text(encoding="utf-8"))
        registry[table["sourceCode"]] = table
    return registry


def _find_key(node: Any, key: str, path: str = "") -> tuple[Any, str] | None:
    """JSON 안에서 key가 처음 나오는 곳의 (값, JSON Pointer). 비어 있는 값은 건너뜁니다."""
    if isinstance(node, dict):
        if key in node and node[key] not in (None, ""):
            return node[key], f"{path}/{key}"
        children = [(f"{path}/{k}", v) for k, v in node.items()]
    elif isinstance(node, list):
        children = [(f"{path}/{i}", v) for i, v in enumerate(node)]
    else:
        return None
    for child_path, child in children:
        found = _find_key(child, key, child_path)
        if found is not None:
            return found
    return None


def _find_all(node: Any, key: str, path: str = "") -> list[tuple[Any, str]]:
    """JSON 안에서 key가 나오는 모든 곳의 (값, JSON Pointer)."""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                found.append((v, f"{path}/{k}"))
            found.extend(_find_all(v, key, f"{path}/{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(_find_all(v, key, f"{path}/{i}"))
    return found


def _api_sum(api: Any, key: str) -> tuple[int | None, str]:
    """지역·주택군별 행으로 나뉜 값의 합계. 숫자로 읽히는 행이 하나도 없으면 None(비교하지 않음)."""
    rows = [(int(str(v).replace(",", "").strip()), p) for v, p in _find_all(api, key) if re.fullmatch(r"\d+", str(v).replace(",", "").strip())]
    if not rows:
        return None, f"합계({key})"
    return sum(v for v, _ in rows), f"합계({key}, {len(rows)}행: {rows[0][1]} …)"


def _api_value(api: Any, mapping: dict[str, Any]) -> tuple[Any, str]:
    """대조표 한 줄 → (API 값, 찾은 위치). apiSumKey(키가 나오는 모든 행의 합), apiKeys(키 이름, 앞 순서 우선) 또는 apiPointer(고정 경로)."""
    if mapping.get("apiSumKey"):
        return _api_sum(api, mapping["apiSumKey"])
    for key in mapping.get("apiKeys", []):
        found = _find_key(api, key)
        if found is not None:
            return found
    pointer = mapping.get("apiPointer")
    if pointer:
        try:
            return tools().resolve(api, pointer), pointer
        except (KeyError, IndexError, TypeError, ValueError):
            pass
    return None, pointer or "/" + "|".join(mapping.get("apiKeys", []))


TITLE_KEY = re.compile(r"(?i)(^|_)(PAN_NM|PBLANC_NM|PBLANCNM|NM|TITLE|NAME)$|공고명|제목")


def _title_texts(node: Any) -> list[str]:
    """API 응답에서 공고 이름 칸의 글자만. 본문·안내 글 어딘가의 "정정"까지 보면 정정공고가 아닌데도 날짜 대조를 건너뜁니다."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and TITLE_KEY.search(str(key)):
                out.append(value)
            else:
                out.extend(_title_texts(value))
    elif isinstance(node, list):
        for value in node:
            out.extend(_title_texts(value))
    return out


def _is_correction(candidate: dict[str, Any], api: Any) -> bool:
    """정정공고인지: collector가 알려 준 종류(CORRECTION)가 가장 믿을 만하고, 다음은 공고 제목·API 공고명의 "정정"."""
    references = candidate.get("sourceReferences") or []
    if any(r.get("kind") == "CORRECTION" for r in references):
        return True
    titles = [str((candidate.get("notice") or {}).get("title") or ""), *(str(r.get("sourceTitle") or "") for r in references), *_title_texts(api)]
    return any("정정" in title for title in titles)


def _skipped(status: str) -> dict[str, Any]:
    return {"status": status, "referenceSha256": None, "referenceIdentity": None, "fields": []}


def _api_date(value: Any) -> str:
    compact = re.sub(r"[.\-/\s]", "", str(value))
    if not re.fullmatch(r"\d{8}", compact):
        raise ValueError("날짜가 아닙니다")
    return date(int(compact[:4]), int(compact[4:6]), int(compact[6:])).isoformat()


def _api_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("숫자가 아닙니다")
    text = str(value).replace(",", "").strip()
    if not re.fullmatch(r"\d+", text):
        raise ValueError("정수가 아닙니다")
    return int(text)


def _select(candidate: dict[str, Any], spec: dict[str, Any]) -> list[tuple[str, Any]]:
    resolve = tools().resolve
    try:
        collection = resolve(candidate, spec["collection"])
    except (KeyError, IndexError, TypeError, ValueError):
        return []
    rows = [(f"{spec['collection']}/{i}", row) for i, row in enumerate(collection)] if isinstance(collection, list) else [(spec["collection"], collection)]
    found = []
    for pointer, row in rows:
        try:
            if all(resolve(row, p) == v for p, v in spec["where"].items()) and all(v in resolve(row, p) for p, v in spec["contains"].items()):
                found.append((pointer + spec["valuePath"], resolve(row, spec["valuePath"])))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return found


def _fallback_field(
    mapping: dict[str, Any], candidate: dict[str, Any], selected: list[tuple[str, Any]], raw_api: Any, source_path: str
) -> dict[str, Any] | None:
    """원래 대상 값이 원문에 없을 때(항목이 없거나 값이 비어 있음) 대신 비교할 대상(fallbackTarget)과 비교한 결과. 대신 비교할 값이 없으면 None.

    LH 공급정보 API의 공급호수는 입주자 모집 공고에서는 모집 수(OFFERED)지만, 예비입주자·매입임대 공고에서는 전체 주택 수(TOTAL_HOUSING)였습니다
    (실측 2026-10-20 LH 0815: API 41 = 전체 41, 0843: 56 = 56, 둘 다 모집 수는 원문에 없음). 같으면 일치로 남기고, 다르면 전체 주택 수가
    단지 규모일 수도 있어 불일치로 보지 않습니다(틀린 값이 게시되는 경우가 아니므로 공고 전체를 검수로 보내지 않음)."""
    spec = mapping.get("fallbackTarget")
    if spec is None or (len(selected) == 1 and selected[0][1] is not None) or len(selected) > 1:
        return None
    alternatives = [(pointer, value) for pointer, value in _select(candidate, spec) if value is not None]
    if len(alternatives) != 1:
        return None
    pointer, actual = alternatives[0]
    field = {"target": pointer, "sourcePath": source_path, "expected": None, "actual": actual, "status": "NOT_COMPARABLE", "reason": None}
    try:
        field["expected"], status, _ = _compare(mapping["normalization"], raw_api, actual)
    except ValueError as error:
        field["reason"] = f"API 값을 해석할 수 없습니다: {error}"
        return field
    other = mapping.get("fallbackNote", "대신 비교할 값")
    if status == "MATCH":
        field["status"], field["reason"] = "MATCH", f"{mapping['field']}이(가) 원문에 없어 {other}과(와) 비교했습니다."
    else:
        field["reason"] = f"{mapping['field']}이(가) 원문에 없고 {other}은(는) API와 달라 비교하지 않습니다(규모가 다른 수일 수 있음)."
    return field


def _expected(normalization: str, raw_api: Any) -> Any:
    """비교하지 않을 때 기록만 하는 API 기대값. 해석할 수 없으면 None."""
    try:
        return _api_int(raw_api) if normalization == "INTEGER" else _api_date(raw_api) if normalization == "DATE" else " ".join(str(raw_api).split())
    except ValueError:
        return None


def _compare(normalization: str, raw_api: Any, actual: Any) -> tuple[Any, str, str | None]:
    """(기대값, 상태, 사유)."""
    if normalization == "INTEGER":
        expected = _api_int(raw_api)
        return expected, ("MATCH" if actual == expected and not isinstance(actual, bool) else "MISMATCH"), None
    if normalization == "DATE":
        expected = _api_date(raw_api)
        if actual == expected:
            return expected, "MATCH", None
        if isinstance(actual, str) and "T" in actual:
            day = datetime.fromisoformat(actual).astimezone(KST).date().isoformat()
            if day == expected:
                return expected, "NOT_COMPARABLE", "API는 날짜만 있어 시각까지 비교할 수 없습니다. 날짜는 같습니다."
        if isinstance(actual, str) and re.fullmatch(r"\d{4}-\d{2}", actual):
            return expected, "NOT_COMPARABLE", "추출값이 월 단위라 날짜와 비교할 수 없습니다."
        return expected, "MISMATCH", None
    expected = " ".join(str(raw_api).split())
    if actual == expected:
        return expected, "MATCH", None
    if isinstance(actual, str) and " ".join(actual.split()) == expected:
        return expected, "NOT_COMPARABLE", "띄어쓰기만 다르고 내용은 같습니다."
    return expected, "MISMATCH", None


def compare_api(candidate: dict[str, Any], reference: ApiReference | None) -> tuple[dict[str, Any], list[Finding]]:
    """후보를 API 원본과 대조해 계약의 apiComparison 값과 V4 검사 결과를 돌려줍니다.
    원본이 같은 공고·버전이 아니거나 해시가 다르거나 읽을 수 없으면 대조하지 않습니다(NOT_RUN)."""
    if reference is None:
        return _skipped("SKIPPED_NO_API_REFERENCE"), []
    findings: list[Finding] = []

    def find(code: str, target: str, description: str) -> None:
        findings.append(Finding("V4", code, target, description))

    identity = {
        "sourceCode": reference.source_code,
        "sourceNoticeId": reference.source_notice_id,
        "rawPostId": reference.raw_post_id,
        "rawVersion": reference.raw_version,
    }
    target = "/quality/verification/apiComparison"
    if not any(all(r.get(k) == v for k, v in identity.items()) for r in candidate["sourceReferences"]):
        find("API_REFERENCE_IDENTITY_CONFLICT", target, "다른 공고·버전의 API 원본입니다.")
        return _skipped("NOT_RUN"), findings
    if hashlib.sha256(reference.body).hexdigest() != reference.sha256:
        find("API_REFERENCE_HASH_MISMATCH", target, "API 원본의 해시가 기록과 다릅니다.")
        return _skipped("NOT_RUN"), findings
    try:
        api = json.loads(reference.body.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        find("API_REFERENCE_UNREADABLE", target, "API 원본을 JSON으로 읽을 수 없습니다.")
        return _skipped("NOT_RUN"), findings

    comparison = {"status": "NO_COMPARABLE_FIELDS", "referenceSha256": reference.sha256, "referenceIdentity": identity, "fields": []}
    table = mapping_registry().get(reference.source_code) or mapping_registry().get("*")
    if table is None:
        find("API_MAPPING_MISSING", target, f"{reference.source_code} API 대조표가 없어 비교하지 못했습니다.")
        return comparison, findings

    for mapping in table["mappings"]:
        raw_api, source_path = _api_value(api, mapping)
        empty = EMPTY_API_VALUES | set(mapping.get("emptyValues", []))  # 예: 공급 수 0은 '미정'(전세임대·상시모집 실측)
        has_api_value = raw_api is not None and re.sub(r"\s", "", str(raw_api)) not in empty
        selected = _select(candidate, mapping["target"])
        fallback = _fallback_field(mapping, candidate, selected, raw_api, source_path) if has_api_value else None
        if fallback is not None:
            comparison["fields"].append(fallback)
            continue
        if not selected:
            if has_api_value:
                find("API_TARGET_MISSING", mapping["target"]["collection"], f"API에는 {mapping['field']} 값이 있는데 대응하는 추출 항목이 없습니다.")
            continue
        if len(selected) > 1:
            find("API_SCOPE_AMBIGUOUS", mapping["target"]["collection"], f"{mapping['field']}에 대응하는 추출 항목이 여러 개라 범위를 확인해야 합니다.")
            continue
        pointer, actual = selected[0]
        field = {"target": pointer, "sourcePath": source_path, "expected": None, "actual": actual, "status": "NOT_COMPARABLE", "reason": None}
        if not has_api_value:
            field["reason"] = "API 값이 없습니다(공고문 참조 등)."
        elif actual is None:
            # 추출값이 비어 있으면(누락) 틀린 값이 게시되지 않으므로 불일치가 아닙니다. API 값으로 채우지도 않습니다:
            # 실측 3건(LH 매입임대·든든전세)에서 API '이번 모집 수'는 공급 호수(TOTAL_HOUSING)였고 모집 인원은 원문에 없었습니다
            field["expected"] = _expected(mapping["normalization"], raw_api)
            field["reason"] = "추출값이 비어 있어(누락) 비교하지 않습니다. API 값으로 채우지 않습니다."
            find("API_VALUE_NOT_EXTRACTED", pointer, f"{mapping['field']}: API에는 {raw_api!r}이(가) 있는데 추출값이 비어 있습니다(누락).")
        else:
            try:
                field["expected"], field["status"], field["reason"] = _compare(mapping["normalization"], raw_api, actual)
            except ValueError as error:
                field["reason"] = f"API 값을 해석할 수 없습니다: {error}"
        corrected = _is_correction(candidate, api)  # 검토 2026-10-16: API JSON 전체의 "정정"이 아니라 종류·제목만
        if field["status"] == "MISMATCH" and mapping["normalization"] == "DATE" and corrected:
            # 정정공고: API의 공고 날짜는 정정일인 경우가 많습니다(실측 3건: 원문 공고일 2025-03-05, API 2026-08-12 = 정정공고일)
            field["status"], field["reason"] = "NOT_COMPARABLE", "정정공고라 API 날짜가 정정일일 수 있어 비교하지 않습니다."
        if field["status"] == "MISMATCH":
            find("API_MISMATCH", pointer, f"{mapping['field']}: API {field['expected']!r}, 추출 {actual!r}")
        comparison["fields"].append(field)

    statuses = {f["status"] for f in comparison["fields"]}
    comparison["status"] = "MISMATCH" if "MISMATCH" in statuses else "MATCHED" if "MATCH" in statuses else "NO_COMPARABLE_FIELDS"
    return comparison, findings
