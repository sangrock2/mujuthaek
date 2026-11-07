"""분야 규칙에 따라 모델을 섹션별로 호출하고 AI 출력 조각을 모읍니다 (결합 전 단계).

- 일시 오류: 제한 재시도(지수 지연 + 무작위 흔들림). 기본은 실제로 기다리고(time.sleep), 테스트는 sleep을 주입해 기다리지 않습니다.
- JSON으로 읽을 수 없는 응답: 오류를 알려 1회 재요청(결정 E7). 출력 한도로 잘린 응답·거부는 재요청하지 않습니다.
- 실패한 호출은 맡은 섹션을 FAILED로 보고하는 빈 조각으로 남겨, 다른 섹션 결과를 보존합니다.
- 구조 호출(첫 호출)이 실패하면 뒤 호출은 실행하지 않습니다(참조할 ID가 없고 비용만 듭니다).
- 응답 원문·사용량은 job 기록용으로 돌려주며 공고 계약에는 넣지 않습니다(2-10 비용 집계 입력).
- 빠진 인용문(2026-10-20, _fill_missing_quotes): 항목이 쓴 인용 ref가 quotes에 없으면 그 인용문만 한 번 더 묻습니다(<호출>-quotes).
- 병렬 호출(2026-10-20, parallel·설정 EXTRACTION_PARALLEL_CALLS): 구조 호출이 끝난 뒤 나머지 섹션 호출을 함께 보냅니다.
  호출마다 기록을 따로 모아 원래 순서대로 붙이므로, 같은 응답이면 결과가 순서대로 부른 것과 같습니다. 1이면 이전처럼 하나씩.
- 병렬 호출 간격(2026-10-20, stagger·설정 EXTRACTION_PARALLEL_STAGGER_SECONDS): 섹션 호출을 이 간격을 두고 하나씩 내보냅니다(응답은 기다리지 않음).
- 반복 폭주(2026-10-24 세 번째 채점, runaway): 응답 글자 안에 같은 긴 조각이 되풀이되거나 글 하나가 지나치게 길면 폭주로 봅니다.
  스트리밍 호출(OPENAI_STREAM, 2026-10-24)은 받는 도중에 폭주를 보면 바로 끊고 종료 사유 RUNAWAY로 돌려줘 출력 요금을 아낍니다(잘림처럼 처리).
  스트리밍이 아니면 응답을 받은 뒤 검사합니다. 잘림(MAX_TOKENS·RUNAWAY)·폭주 뒤 다시 보낼 때는 같은 요청이
  아니라 「표 한 행씩, 인용 300자 이내, 같은 행 반복 금지」 지시를 덧붙인 요청을 보냅니다(같은 요청은 같은 곳에서 다시 폭주했음).
  다시 받아도 잘리면, 나눠 부를 호출(FieldRules.runaway_splits, 주거 서류)은 서류 표 묶음별로 나눠 부르고, 그 밖에는 잘린 JSON에서
  끝까지 적힌 항목만 살립니다(salvage_truncated, 그 섹션은 PARTIAL). 정상 종료인데 폭주가 보이면 바꾼 요청으로 한 번 더 받고,
  그래도 같으면 받은 응답을 씁니다(근거를 못 찾은 항목은 결합기가 뺍니다).
"""

from __future__ import annotations

import copy
import json
import os
import random
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from mujuthaek_extraction import supply_tables
from mujuthaek_extraction.assemble.ai_output import SECTIONS
from mujuthaek_extraction.assemble.slips import fix_format_slips
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ExtractionModel, ModelError, ModelRequest, StopReason
from mujuthaek_extraction.model.runaway import MAX_STRING_CHARS, RUNAWAY_CHUNK, RUNAWAY_REPEATS, RUNAWAY_STEP, runaway  # noqa: F401 (시험·다른 모듈이 여기서 가져감)
from mujuthaek_extraction.model.strict_schema import drop_null_optionals, keep_own, to_strict
from mujuthaek_extraction.rules.base import CallSpec, FieldRules, call_schema, document_ids, output_limit, structure_summary
from mujuthaek_extraction.usage import UsageRecorder, timed


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # 일시 오류 포함 한 요청의 최대 시도 횟수
    base_delay_seconds: float = 2.0
    json_repairs: int = 1
    # 형식이 틀린 항목이 이보다 적으면(그리고 틀린 곳이 모두 섹션 항목 안이면) 다시 요청하지 않고 결합기가 그 항목만 뺍니다.
    # 다시 요청은 원문 전체를 또 보내 비용이 큽니다(실측 OpenAI: 9회 중 2회). 1이면 이전처럼 늘 다시 요청(설정 EXTRACTION_REPAIR_MIN_BAD_ITEMS)
    repair_min_bad_items: int = 1
    # 출력 한도로 잘린 응답은 같은 요청을 이만큼 다시 보냅니다. 실측 OpenAI LH 김제(19412): 서류 호출이 표 행 인용 뒤
    # 빈 칸 「|  |」을 3만 자 넘게 반복하다 24,000토큰에서 잘려 서류 34개가 모두 빠짐(원문 그 행의 빈 칸은 1개). 반복은 우연이라 다시 받으면 대개 정상입니다
    truncation_retries: int = 1


DEFAULT_POLICY = RetryPolicy(repair_min_bad_items=int(os.getenv("EXTRACTION_REPAIR_MIN_BAD_ITEMS", "3")))


def bad_items(part: Any, schema: dict[str, Any]) -> int | None:
    """형식이 틀린 섹션 항목 수. 섹션 항목 밖(맨 위·인용·coverage 등)이 틀렸으면 None(다시 요청해야 함)."""
    found: set[tuple[str, int]] = set()
    for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(part):
        path = list(error.absolute_path)
        if len(path) < 2 or path[0] not in SECTIONS or path[0] == "notice" or not isinstance(path[1], int):
            return None
        found.add((path[0], path[1]))
    return len(found)


@dataclass(frozen=True)
class CallAttempt:
    call_name: str
    prompt_version: str
    repair: bool
    model_id: str | None
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None
    error: str | None
    cache_write_tokens: int | None = None
    runaway: str | None = None  # 응답에서 본 반복 폭주(extract.runaway). 이 시도 뒤 바꾼 요청으로 다시 보냈거나 나눠 불렀습니다


@dataclass
class ExtractionRun:
    parts: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[CallAttempt] = field(default_factory=list)
    failed_calls: list[tuple[str, str]] = field(default_factory=list)
    raw_responses: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # 잘림 뒤 나눠 부르기·항목 살리기처럼 결과를 만든 방법 (로그·작업 기록용)
    # 뒤 호출에 넘긴 구조 요약(코드가 주소마다 만든 위치는 뺀 것). 에이전트 방식이 같은 요약을 담당에게 줍니다
    structure: dict[str, Any] | None = None
    table_mapping: tuple[list[Any], dict[str, Any]] | None = None  # 공급표 후보와 AI 열 해석(기관 기억 그림자 모드가 맞춰 봄, format_memory)


GUARD_NOTE = (
    "# 다시 요청하는 이유\n앞 응답이 같은 표 행을 되풀이하거나 인용 하나를 지나치게 길게 쓰다 출력 한도에 닿았습니다. "
    "이번에는 표를 한 행씩 인용하고(인용 하나는 표 한 행 또는 한 줄, 300자 이내), 같은 행·같은 글을 두 번 쓰지 않습니다. "
    "긴 칸은 값이 든 부분만 인용하되, 서류 표 행은 그 행의 발급처·부수 칸까지 함께 인용합니다(빠지면 그 값을 확인하지 못해 지웁니다). "
    "나머지 지시는 그대로 따릅니다."
)


def guarded(request: ModelRequest) -> ModelRequest:
    """잘림·폭주 뒤 다시 보낼 요청: 같은 요청 대신 짧게 인용하라는 지시를 덧붙입니다(이미 붙였으면 그대로)."""
    if GUARD_NOTE in request.instructions:
        return request
    return replace(request, instructions=f"{request.instructions}\n\n{GUARD_NOTE}")


def salvage_truncated(
    raw: str, sections: tuple[str, ...], optional_names: frozenset[str] = frozenset(), own_schema: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """출력 한도로 잘린 JSON에서 끝까지 적힌 항목만 살립니다. 인용(quotes) 목록이 끝까지 적혀 있고 맡은 섹션 목록 안에서 잘렸을 때만
    살립니다(인용 안에서 잘리면 항목이 없어 None). 잘린 섹션은 coverage PARTIAL(AI가 다 옮기지 못한 것과 같이 재확인·검수로),
    끝까지 적힌 섹션은 EXTRACTED, 시작도 못 한 섹션은 FAILED입니다.

    optional_names는 엄격 모드가 null로 채운 선택 칸 이름입니다. 모델 어댑터는 정상 종료 응답에서만 이 null을 지우므로(잘린 응답은
    JSON이 아님) 여기서 지웁니다. 2026-10-25 33번: 잘린 서류 응답 인용의 「unitRow」: null 59개가 형식 오류가 되어 서류 전체를 버림.
    own_schema(이번 호출의 형식)를 주면 공유 형식 응답에서 맡지 않은 섹션(null)도 지웁니다(어댑터의 keep_own과 같음. 같은 날 다시 돌린 33번:
    맨 위 「eligibility」「notice」 null이 형식 오류가 되어 잘린 서류 제출 응답의 66개 항목을 또 버림)"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    stack: list[str] = []  # 열린 괄호들
    keys: list[str | None] = []  # 열린 괄호마다 그 값의 키(객체 안의 값일 때)
    last_string: str | None = None  # 바로 앞에 닫힌 문자열(다음 글자가 「:」이면 키)
    pending_key: str | None = None
    last_item_end: tuple[int, str] | None = None  # (자른 위치, 섹션 이름)
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char == '"':
            end = i + 1
            while end < n and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            if end >= n:
                break  # 닫히지 않은 문자열에서 잘림
            last_string = text[i + 1 : end]
            i = end + 1
            continue
        if char == ":":
            pending_key, last_string = last_string, None
        elif char in "{[":
            keys.append(pending_key if stack and stack[-1] == "{" else None)
            pending_key = None
            stack.append(char)
        elif char in "}]":
            if not stack:
                return None
            stack.pop()
            keys.pop()
            # 맨 위 객체 안 섹션 목록 안의 항목 하나가 닫힘
            if char == "}" and stack == ["{", "["] and keys[1] in sections:
                last_item_end = (i + 1, str(keys[1]))
        elif char == ",":
            pending_key = None
        i += 1
    if last_item_end is None or not stack:
        return None
    cut, truncated = last_item_end
    try:
        part = drop_null_optionals(json.loads(text[:cut] + "]}"), optional_names)
        if own_schema is not None:
            part = keep_own(part, own_schema)
    except ValueError:
        return None
    if not isinstance(part, dict) or not isinstance(part.get("quotes"), list):
        return None
    coverage = {}
    for section in sections:
        if section == truncated:
            coverage[section] = {"status": "PARTIAL", "reason": "출력 한도로 응답이 잘려 끝까지 적힌 항목만 받았어요."}
        elif isinstance(part.get(section), list) and section != truncated:
            coverage[section] = {"status": "EXTRACTED", "reason": None}
        else:
            part[section] = []
            coverage[section] = {"status": "FAILED", "reason": "출력 한도로 응답이 잘려 이 섹션을 받지 못했어요."}
    part["coverage"] = coverage
    part.setdefault("missingFields", [])
    return part


SHORT_QUOTES = "인용은 표 한 행씩(한 행 또는 한 줄, 300자 이내) 적고, 같은 행·같은 글을 두 번 쓰지 않습니다."
SPLIT_PARTIAL = "서류를 표 묶음별로 나눠 다시 불렀지만 일부 묶음을 받지 못했어요."


def _item_key(section: str, item: dict[str, Any]) -> str:
    """같은 항목인지 볼 열쇠: 서류는 이름·제출 시점·대상, 일정은 이름·시작, 그 밖에는 이름·설명 글.
    서류 대상(appliesTo·대상 계층·공급 구분)을 넣는 까닭: 2026-10-25 33번에서 일반공급 공통 서류 14개가 이름이 같은 특별공급 서류와 같은 것으로
    여겨져 모두 빠짐. 제출 시점 끝의 「시」「때」는 뺍니다(잘린 두 응답이 「…제출 시」「…제출」로만 달라 같은 서류가 두 번 들어감)."""
    if section == "requiredDocuments":
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        time = re.sub(r"\s*(?:시|때)\s*$", "", str(item.get("submissionTime") or ""))
        parts = [item.get("name"), time, item.get("appliesTo"), json.dumps(scope.get("targetGroups"), ensure_ascii=False), scope.get("supplyCategory")]
    elif section == "schedules":
        parts = [item.get("rawLabel"), json.dumps(item.get("startsAt"), sort_keys=True)]
    else:
        parts = [item.get("name") or item.get("rawLabel") or item.get("title") or item.get("description") or item.get("originalText")]
    return "|".join(re.sub(r"\s+", "", str(p or "")) for p in parts)


# 처음부터 나눠 부를 서류 표 행 수(설정 EXTRACTION_PRESPLIT_DOC_ROWS, 0이면 끔 = 이전처럼 잘린 뒤에만 나눠 부름)
PRESPLIT_ROWS = int(os.getenv("EXTRACTION_PRESPLIT_DOC_ROWS", "60"))


def document_rows(material: ExtractionMaterial) -> int:
    """원문 서류 표에서 서류 낱말이 든 행 수(검증의 서류 누락 검사와 같은 기준)."""
    from mujuthaek_extraction.verify.consistency import DOCUMENT_WORD, _document_table_rows

    return sum(1 for row in _document_table_rows(material.text or "") if DOCUMENT_WORD.search(row))


def fill_from_cuts(
    part: dict[str, Any],
    cut_raws: list[str],
    sections: tuple[str, ...],
    optional_names: frozenset[str] = frozenset(),
    own_schema: dict[str, Any] | None = None,
) -> int:
    """잘린 응답들에서 끝까지 적힌 항목 중 part에 없는 것을 더합니다(2026-10-24 여덟 번째 채점: 서류 호출 첫 응답은 일반공급 서류까지
    읽고 잘렸는데, 나중 응답(더 앞에서 잘림)·나눠 부른 결과만 써서 서류 11개가 빠짐). 인용 ref는 응답마다 앞머리(c1-, c2-)를 붙입니다.
    더한 항목 수를 돌려줍니다. 형식이 틀린 항목은 결합기가 뺍니다."""
    added = 0
    for number, raw in enumerate(cut_raws, start=1):
        salvaged = salvage_truncated(raw, sections, optional_names, own_schema)
        if not salvaged:
            continue
        prefix = f"c{number}-"
        rename = {q["ref"]: prefix + q["ref"] for q in salvaged.get("quotes") or [] if isinstance(q, dict) and isinstance(q.get("ref"), str)}
        used: set[str] = set()
        for section in sections:
            if not isinstance(part.get(section), list) or not isinstance(salvaged.get(section), list):
                continue
            have = {_item_key(section, item) for item in part[section] if isinstance(item, dict)}
            ids = {item.get("id") for item in part[section] if isinstance(item, dict)}
            for item in copy.deepcopy(salvaged[section]):
                if not isinstance(item, dict) or _item_key(section, item) in have:
                    continue
                _rename_quote_refs(item, rename)
                used |= set(_used_refs(item))
                if item.get("id") in ids:
                    item["id"] = f"{item['id']}~c{number}"
                ids.add(item.get("id"))
                have.add(_item_key(section, item))
                part[section].append(item)
                added += 1
        part.setdefault("quotes", [])
        part["quotes"] += [{**q, "ref": rename[q["ref"]]} for q in salvaged.get("quotes") or [] if isinstance(q, dict) and rename.get(q.get("ref")) in used]
    return added


def merge_split_parts(parts: list[dict[str, Any]], sections: tuple[str, ...]) -> dict[str, Any] | None:
    """나눠 부른 호출들의 조각을 한 조각으로 합칩니다. 인용 ref는 조각마다 앞머리(s1-, s2-)를 붙이고, 겹치는 항목 id는 뒤에 「~s2」를 붙이며,
    누락 기록 위치는 붙인 자리만큼 옮깁니다. 섹션 범위: 모두 EXTRACTED면 EXTRACTED, 하나라도 받지 못했거나 PARTIAL이면 PARTIAL(재확인·검수로),
    모두 원문에 없음이면 그대로. 받은 조각이 하나도 없으면 None."""
    merged: dict[str, Any] = {"quotes": [], **{s: [] for s in sections}, "missingFields": [], "coverage": {}}
    statuses: dict[str, list[dict[str, Any]]] = {s: [] for s in sections}
    received = False
    for number, part in enumerate(parts, start=1):
        coverage = part.get("coverage") or {}
        for section in sections:
            statuses[section].append(coverage.get(section) or {"status": "FAILED", "reason": None})
        if not part.get("quotes") and not any(part.get(s) for s in sections):
            continue
        received = True
        prefix = f"s{number}-"
        rename = {q["ref"]: prefix + q["ref"] for q in part.get("quotes") or [] if isinstance(q, dict) and isinstance(q.get("ref"), str)}
        merged["quotes"] += [{**q, "ref": rename[q["ref"]]} for q in part.get("quotes") or [] if isinstance(q, dict) and q.get("ref") in rename]
        for section in sections:
            offset = len(merged[section])
            taken = {item.get("id") for item in merged[section] if isinstance(item, dict)}
            for item in copy.deepcopy(part.get(section) or []):
                if isinstance(item, dict):
                    _rename_quote_refs(item, rename)
                    if item.get("id") in taken:
                        item["id"] = f"{item['id']}~s{number}"
                    taken.add(item.get("id"))
                merged[section].append(item)
            for entry in part.get("missingFields") or []:
                found = re.match(rf"^/{section}/(\d+)", str(entry.get("target", ""))) if isinstance(entry, dict) else None
                if found:
                    target = f"/{section}/{int(found[1]) + offset}{entry['target'][found.end() :]}"
                    merged["missingFields"].append({**entry, "target": target})
    if not received:
        return None
    for section, found in statuses.items():
        kinds = {entry.get("status") for entry in found}
        if kinds <= {"EXTRACTED", "NOT_IN_SOURCE", "NOT_APPLICABLE"} and "EXTRACTED" in kinds:
            merged["coverage"][section] = {"status": "EXTRACTED", "reason": None}
        elif len(kinds) == 1 and kinds <= {"NOT_IN_SOURCE", "NOT_APPLICABLE"}:
            merged["coverage"][section] = dict(found[0])
        else:
            merged["coverage"][section] = {"status": "PARTIAL", "reason": SPLIT_PARTIAL}
    return merged


def _rename_quote_refs(node: Any, rename: dict[str, str]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("quoteRefs"), list):
            node["quoteRefs"] = [rename.get(ref, ref) for ref in node["quoteRefs"]]
        for value in node.values():
            _rename_quote_refs(value, rename)
    elif isinstance(node, list):
        for value in node:
            _rename_quote_refs(value, rename)


def _failed_part(call: CallSpec, reason: str) -> dict[str, Any]:
    return {"quotes": [], "coverage": {section: {"status": "FAILED", "reason": reason} for section in call.sections}}


def _parse(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):  # 지시를 어기고 코드 블록으로 감싼 경우만 벗깁니다
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("JSON 객체가 아닙니다")
    return value


def retry_delay(policy: RetryPolicy, attempt: int) -> float:
    """attempt번째 시도 실패 뒤 기다릴 초. 지수 지연에 ±20% 흔들림을 더해 여러 작업이 같은 순간에 다시 몰리지 않게 합니다."""
    return policy.base_delay_seconds * 2 ** (attempt - 1) * random.uniform(0.8, 1.2)


def schema_errors(part: Any, schema: dict[str, Any], limit: int = 8) -> str | None:
    """원래 계약 규칙(조건부·형식 포함)으로 검사합니다. 제공자의 엄격 모드는 이 규칙 일부를 빼고 보내므로 여기서 다시 확인합니다."""
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(part), key=lambda e: list(map(str, e.absolute_path)))
    if not errors:
        return None
    lines = [f"/{'/'.join(map(str, e.absolute_path))}: {e.message[:160]}" for e in errors[:limit]]
    more = f" 외 {len(errors) - limit}건" if len(errors) > limit else ""
    return f"형식 규칙 위반 {len(errors)}건{more}\n" + "\n".join(lines)


def run_extraction(
    rules: FieldRules,
    material: ExtractionMaterial,
    model: ExtractionModel,
    *,
    policy: RetryPolicy = DEFAULT_POLICY,
    sleep: Callable[[float], None] | None = None,
    budget: Callable[[ModelRequest], bool] | None = None,
    structure: dict[str, Any] | None = None,
    usage: UsageRecorder | None = None,
    parallel: int = 1,
    stagger: float = 0.0,
) -> ExtractionRun:
    """structure: 이미 추출한 구조 요약(재확인 호출처럼 구조 호출 없이 부를 때). 없으면 첫 호출 응답에서 만듭니다.
    sleep: 일시 오류 뒤 기다리는 함수. 없으면 실제로 기다립니다(이전 기본값은 기다리지 않아 429·5xx 재시도가 바로 다시 나갔음).
    usage: 있으면 공급표(supply_tables)·섹션 호출(sections) 단계 시간을 더합니다.
    parallel: 구조 호출 뒤 나머지 섹션 호출을 동시에 보낼 수(1이면 이전처럼 하나씩). 모델·예산 감싸기는 여러 스레드에서 불려도 됩니다.
    stagger: 병렬로 보낼 때 섹션 호출을 내보내는 간격(초). 0이면 한꺼번에. 기다리기는 sleep으로 합니다(테스트는 가짜 sleep)."""
    run = ExtractionRun()
    wait = sleep or time.sleep  # 부를 때 찾습니다(테스트가 time.sleep을 바꿔 기록할 수 있게)

    def call_model(request: ModelRequest, repair: bool, sink: ExtractionRun):
        """요청을 보내고 (응답, None) 또는 (None, 실패 사유)를 돌려줍니다. 일시 오류만 지수 지연으로 다시 시도하고, 시도마다 sink에 기록합니다."""
        for attempt in range(1, policy.max_attempts + 1):
            try:
                response = model.complete(request)
            except ModelError as error:
                sink.attempts.append(CallAttempt(request.call_name, request.prompt_version, repair, None, None, None, None, None, str(error)))
                if not error.transient or attempt == policy.max_attempts:
                    return None, f"모델 호출 실패: {error}"
                wait(retry_delay(policy, attempt))
                continue
            sink.attempts.append(
                CallAttempt(
                    request.call_name,
                    request.prompt_version,
                    repair,
                    response.model_id,
                    response.stop_reason.value,
                    response.input_tokens,
                    response.output_tokens,
                    response.cached_input_tokens,
                    None,
                    response.cache_write_tokens,
                )
            )
            sink.raw_responses.append((request.call_name, response.raw_text))
            return response, None
        return None, "모델 호출 실패"

    def into(sink: ExtractionRun):
        return lambda request, repair: call_model(request, repair, sink)

    calls = list(rules.calls_for(material))
    # 구조 방식: 공급·가격 표는 코드가 옮기고(supply_tables) 구조 호출은 공고·위치만 맡습니다. 열 의미를 못 받으면 이전처럼 구조 호출이 공급까지
    table_part = None
    if rules.supply_tables and structure is None and calls and (material.pdf_pages or getattr(material, "sheets", ())):
        with timed(usage, "supply_tables"):
            table_part = _supply_from_tables(rules, material, calls[0], into(run), budget, run)
        if table_part is not None:
            first = calls[0]
            # 코드 묶음에 수량이 없으면(가격표만 옮김) 구조 호출이 주택형별 수량 묶음을 만들고, 받은 뒤 코드 묶음 앞에 둡니다
            sections = tuple(s for s in first.sections if s != "supplyGroups" or not supply_tables.has_counts(table_part))
            note = supply_tables.structure_note(table_part)
            calls[0] = replace(first, sections=sections, instructions=f"{first.instructions}\n{note}")

    def one_call(number: int, call: CallSpec, known: dict[str, Any] | None, sink: ExtractionRun) -> dict[str, Any] | None:
        """호출 하나를 끝까지(일시 오류 재시도·잘림 재요청·형식 재요청·이어받기) 처리해 sink에 기록합니다.
        구조 호출(첫 호출, 구조를 아직 모를 때)이 성공하면 만든 구조 요약을 돌려줍니다."""
        if number > 0 and known is None:
            reason = "구조 호출이 실패해 실행하지 않았습니다."
            sink.failed_calls.append((call.name, reason))
            sink.parts.append(_failed_part(call, reason))
            return None
        request = rules.build_request(call, material, known)
        if budget is not None and not budget(request):
            reason = "추출 예산 한도로 호출하지 않았습니다."
            sink.failed_calls.append((call.name, reason))
            sink.parts.append(_failed_part(call, reason))
            return None

        part, reason, repairs, truncations = None, None, 0, 0
        presplit = dict(rules.runaway_splits).get(call.name)
        if presplit and number > 0 and PRESPLIT_ROWS and document_rows(material) >= PRESPLIT_ROWS:
            # 서류 표 행이 많으면 한 번에 부르면 출력 한도로 잘려 두세 번 다시 부르게 됩니다(2026-10-25 비용: 잘려 버린 출력이
            # 전체의 8%). 처음부터 표 묶음별로 나눠 부르고, 받지 못하면 아래 한 번에 부르기로 돌아갑니다
            part = run_split(number, call, presplit, known, sink)
            if part is not None:
                sink.notes.append(f"{call.name}: 서류 표 행이 많아 처음부터 표 묶음별로 나눠 불렀습니다")
        unrepaired = None  # 형식 위반이 있는 첫 응답. 수정 호출이 실패하면(예산 한도 등) 이것을 넘깁니다
        truncated_raw: str | None = None  # 다시 받아도 잘린 마지막 응답(나눠 부르기·끝까지 적힌 항목 살리기에 씀)
        cut_raws: list[str] = []  # 이 호출에서 잘린 응답 전부(앞 응답이 더 멀리 읽었을 수 있어 모두 모읍니다)
        while part is None and reason is None:
            response, reason = call_model(request, repairs > 0, sink)
            if response is None:
                break
            cut = response.stop_reason in (StopReason.MAX_TOKENS, StopReason.RUNAWAY)
            loop = runaway(response.raw_text) if cut or response.stop_reason is StopReason.END else None
            if loop is not None:
                sink.attempts[-1] = replace(sink.attempts[-1], runaway=loop)
            if cut:
                cut_raws.append(response.raw_text)
            if cut or loop is not None:
                # 잘렸거나 폭주한 응답: 짧게 인용하라는 지시를 덧붙인 요청으로 다시 받습니다(같은 요청은 같은 곳에서 다시 폭주했음)
                if truncations < policy.truncation_retries and (budget is None or budget(guarded(request))):
                    truncations += 1
                    request = guarded(request)
                    continue
                if cut:
                    truncated_raw = response.raw_text
                    reason = "출력 한도로 응답이 잘렸습니다."
                    continue
                # 정상 종료인데 폭주가 보이고 다시 받을 수 없으면 받은 응답을 씁니다(근거를 못 찾은 항목은 결합기가 뺍니다)
            if response.stop_reason is StopReason.REFUSED:
                reason = "모델이 응답을 거부했습니다."
            else:
                try:
                    part = fix_format_slips(_parse(response.raw_text))
                    problem = schema_errors(part, request.output_schema)
                except ValueError as error:  # json.JSONDecodeError 포함
                    part, problem = None, f"JSON으로 읽을 수 없는 응답입니다: {str(error)[:200]}"
                if problem is not None:
                    few = part is not None and (count := bad_items(part, request.output_schema)) is not None and count < policy.repair_min_bad_items
                    if repairs >= policy.json_repairs or few:
                        if part is None:
                            reason = problem
                        # 형식 위반이 남은 조각은 그대로 넘기고, 결합기가 위반한 섹션만 FAILED로 처리합니다
                    else:
                        repairs += 1
                        unrepaired = unrepaired if part is None else part
                        part = None
                        request = rules.build_request(call, material, known, repair_error=problem)
                        request = guarded(request) if truncations else request

        if part is None and unrepaired is not None:
            # 수정 호출이 어떤 이유로든(예산 차단·출력 한도로 잘림·거부·호출 실패) 답을 못 주면 첫 응답을 넘깁니다.
            # 실측(GH 800 유료): 감점 행 2개의 형식 위반 때문에 자격·선정·서류가 통째로 사라졌습니다.
            # 결합기가 위반한 섹션만 FAILED로 처리하므로 나머지 섹션은 살립니다.
            part, reason = unrepaired, None
        if part is None and truncated_raw is not None:
            # 다시 받아도 잘림: 나눠 부를 호출이면 표 묶음별로 나눠 부르고(한 조각이 폭주해도 나머지는 남음), 아니면(또는 모두 실패하면)
            # 잘린 응답에서 끝까지 적힌 항목만 살립니다. 살린 섹션은 PARTIAL이라 재확인·검수로 갑니다
            splits = dict(rules.runaway_splits).get(call.name)
            how = None
            if splits and number > 0:
                part = run_split(number, call, splits, known, sink)
                how = "표 묶음별로 나눠 부른 결과" if part is not None else None
            optional = to_strict(request.output_schema)[1]  # 잘린 응답은 어댑터가 null 칸을 지우지 못했습니다
            if part is None:
                salvaged = salvage_truncated(truncated_raw, call.sections, optional, request.output_schema)
                if salvaged is not None and (schema_errors(salvaged, request.output_schema) is None or bad_items(salvaged, request.output_schema) is not None):
                    part, how = fix_format_slips(salvaged), "잘린 응답에서 끝까지 적힌 항목"
            if part is not None:
                reason = None
                added = fill_from_cuts(part, cut_raws, call.sections, optional, request.output_schema)
                more = f", 앞서 잘린 응답에서 끝까지 적힌 항목 {added}개를 더했습니다" if added else ""
                sink.notes.append(f"{call.name}: 다시 받아도 출력 한도로 잘려 {how}를 썼습니다{more}")
        if part is None:
            sink.failed_calls.append((call.name, reason))
            sink.parts.append(_failed_part(call, reason))
            return None
        _fill_missing_quotes(rules, material, call, known, part, into(sink), budget)
        if number == 0 and known is None and rules.continuation is not None and table_part is None:
            _continue_supply(rules, material, part, into(sink), budget)
        sink.parts.append(part)
        if number == 0 and known is None:
            if table_part is not None:
                made = supply_tables.merge_into_structure(table_part, part)
                supply_tables.link_locations(table_part, part.get("locations") or [])
                sink.parts.append(table_part)
                # 코드가 주소마다 만든 위치(수백 곳일 수 있음)는 뒤 호출에 넘기지 않습니다. 뒤 호출은 단지·지역 위치만 가리킵니다
                shown = [loc for loc in part.get("locations") or [] if not (isinstance(loc, dict) and loc.get("id") in made)]
                return structure_summary({**part, "locations": shown, "supplyGroups": table_part["supplyGroups"]})
            return structure_summary(part)
        return None

    def run_split(number: int, call: CallSpec, splits: tuple[CallSpec, ...], known: dict[str, Any] | None, sink: ExtractionRun) -> dict[str, Any] | None:
        """잘린 호출을 나눠 부를 호출들(splits)로 다시 불러 한 조각으로 합칩니다. 하나도 받지 못하면 None.
        나눈 호출마다 잘림 재요청·형식 재요청·끝까지 적힌 항목 살리기를 따로 거칩니다(더 나누지는 않음)."""
        sub = ExtractionRun()
        for spec in splits:
            one_call(number, replace(spec, instructions=f"{spec.instructions}\n{SHORT_QUOTES}"), known, sub)
        sink.attempts.extend(sub.attempts)
        sink.raw_responses.extend(sub.raw_responses)
        sink.failed_calls.extend(sub.failed_calls)
        sink.notes.extend(sub.notes)
        return merge_split_parts(sub.parts, call.sections)

    def run_calls() -> None:
        nonlocal structure
        if not calls:
            return
        # 첫 호출(구조)은 혼자 먼저 끝냅니다: 뒤 호출이 그 구조 ID를 받고, 원문 앞부분의 프롬프트 캐시도 이 호출이 만듭니다
        made = one_call(0, calls[0], structure, run)
        structure = structure if structure is not None else made
        rest = list(enumerate(calls))[1:]
        if parallel <= 1 or len(rest) <= 1 or structure is None:
            for number, call in rest:
                one_call(number, call, structure, run)
            return
        # 나머지 호출은 서로 기대지 않아(같은 구조 요약만 받음) 함께 보냅니다. 기록은 호출마다 따로 모았다가 원래 순서대로 붙여,
        # 같은 응답이면 순서대로 부른 것과 결과(조각·시도·응답 원문 순서)가 같습니다
        sinks = [ExtractionRun() for _ in rest]
        with ThreadPoolExecutor(max_workers=min(parallel, len(rest)), thread_name_prefix="extract-call") as pool:
            # 한꺼번에 보내면 실측(live-perf 0815·0843·0839, 2026-10-20) 공고마다 섹션 호출 4개 중 정확히 1개가 구조 호출이 써 둔
            # 원문 캐시를 읽지 못하고(캐시 읽기 0) 원문 전체를 다시 캐시에 썼습니다(호출당 약 $0.0035~0.004 더 듦). 나머지 3개는 읽음.
            # 그래서 stagger초 간격으로 하나씩 내보냅니다. 응답을 기다리지 않으므로 늘어나는 시간은 마지막 호출의 출발 지연((호출 수-1)×간격,
            # 기본 4.5초)뿐이고, 섹션 단계(실측 70~90초)는 가장 긴 호출이 정하므로 대개 그보다 덜 늘어납니다.
            futures = []
            for index, ((number, call), sink) in enumerate(zip(rest, sinks, strict=True)):
                if index and stagger > 0:
                    wait(stagger)
                futures.append(pool.submit(one_call, number, call, structure, sink))
        for future in futures:
            future.result()  # 예상 못 한 오류는 호출 순서대로 다시 냅니다
        for sink in sinks:
            run.parts.extend(sink.parts)
            run.attempts.extend(sink.attempts)
            run.failed_calls.extend(sink.failed_calls)
            run.raw_responses.extend(sink.raw_responses)
            run.notes.extend(sink.notes)

    with timed(usage, "sections"):
        run_calls()
    run.structure = structure
    return run


def _supply_from_tables(
    rules: FieldRules, material: ExtractionMaterial, first: CallSpec, call_model, budget, sink: ExtractionRun | None = None
) -> dict[str, Any] | None:
    """공급표 열 의미를 AI에 묻고 코드가 행을 옮긴 공급 조각. 표가 없거나 답이 형식에 맞지 않으면 None(이전 방식으로).
    형식에 맞는 열 해석은 sink.table_mapping에 남깁니다(기관 기억 그림자 모드)."""
    tables = supply_tables.candidates(material)
    if not tables:
        return None
    base = rules.build_request(first, material)
    request = supply_tables.mapping_request(base, tables)
    if budget is not None and not budget(request):
        return None
    response, _ = call_model(request, repair=False)
    if response is None:
        return None
    if response.stop_reason in (StopReason.MAX_TOKENS, StopReason.RUNAWAY):
        # 잘린 답: 끝까지 적힌 표 답은 쓰고 남은 표만 한 번 더 묻습니다(2026-10-24 일곱 번째 채점: 잘린 답 전체를 버려 표 옮기기가 꺼짐)
        done = supply_tables.salvage_mapping(response.raw_text)
        answered = {str(e.get("table")) for e in done}
        rest = [t for t in tables if t.label not in answered and not t.continues]
        more: list[dict[str, Any]] = []
        if done and rest:
            follow = supply_tables.mapping_request(base, rest)
            if budget is None or budget(follow):
                again, _ = call_model(follow, repair=False)
                if again is not None and again.stop_reason is StopReason.END:
                    parsed = supply_tables.parse_mapping(again.raw_text)
                    more = list(parsed["tables"]) if parsed else []
                elif again is not None:
                    more = supply_tables.salvage_mapping(again.raw_text)
        mapping = {"tables": [*done, *more]} if done else None
    elif response.stop_reason is StopReason.END:
        mapping = supply_tables.parse_mapping(response.raw_text)
    else:
        return None
    if mapping is None or schema_errors(mapping, supply_tables.MAPPING_SCHEMA) is not None:
        return None
    if sink is not None:
        sink.table_mapping = (tables, mapping)
    part = supply_tables.build_part(tables, mapping, material.text_document_id, offered=supply_tables.offered_units(material.text))
    if part is None:
        return None
    # 주소 위치는 구조 호출 조각으로 옮겨 그쪽에서 검사하고, 코드가 남긴 검수 이슈는 결합기가 꺼내 씁니다(계약 칸 아님)
    check = {k: v for k, v in part.items() if k not in ("locations", supply_tables.ISSUES_KEY)}
    check["supplyGroups"] = [{k: v for k, v in g.items() if k != "_complex"} for g in part["supplyGroups"]]
    if schema_errors(check, call_schema(("supplyGroups",), document_ids(material))) is not None:
        return None
    return part


QUOTES_SUFFIX = "-quotes"  # 빠진 인용문만 다시 묻는 호출 이름: <호출 이름>-quotes
QUOTES_PROMPT_VERSION = "quotes/v1"
QUOTE_ITEM_CHARS = 600  # 빠진 ref를 쓴 항목을 보여 줄 때 항목 하나의 글자 상한


def missing_quote_refs(part: Any) -> list[str]:
    """섹션 항목의 quoteRefs가 가리키지만 이 응답의 quotes에 없는 ref(처음 나온 순서)."""
    if not isinstance(part, dict) or not isinstance(part.get("quotes", []), list):
        return []  # quotes 자체가 틀린 응답은 결합기가 처리합니다
    defined = {q.get("ref") for q in part.get("quotes", []) if isinstance(q, dict)}
    return [ref for ref in dict.fromkeys(_used_refs({k: v for k, v in part.items() if k != "quotes"})) if ref not in defined]


def _used_refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        own = [r for r in node["quoteRefs"] if isinstance(r, str)] if isinstance(node.get("quoteRefs"), list) else []
        return own + [r for value in node.values() for r in _used_refs(value)]
    if isinstance(node, list):
        return [r for value in node for r in _used_refs(value)]
    return []


def _items_using(node: Any, refs: set[str]) -> list[str]:
    """빠진 ref를 직접 쓴 항목(그 ref가 붙은 가장 안쪽 객체)을 짧은 JSON으로."""
    found: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("quoteRefs"), list) and refs.intersection(r for r in node["quoteRefs"] if isinstance(r, str)):
            text = json.dumps(node, ensure_ascii=False, sort_keys=True)
            found.append(text if len(text) <= QUOTE_ITEM_CHARS else text[:QUOTE_ITEM_CHARS] + "…")
        for value in node.values():
            found.extend(_items_using(value, refs))
    elif isinstance(node, list):
        for value in node:
            found.extend(_items_using(value, refs))
    return found


def quotes_request(base: ModelRequest, call_name: str, part: dict[str, Any], missing: list[str]) -> ModelRequest:
    """빠진 인용문만 다시 묻는 요청. base(그 호출의 요청)의 [공통 지시 → 원문] 앞부분을 그대로 써서 입력 캐시를 함께 씁니다."""
    schema = copy.deepcopy(base.output_schema)
    schema["properties"] = {"quotes": schema["properties"]["quotes"]}
    schema["required"] = ["quotes"]
    items = _items_using({k: v for k, v in part.items() if k != "quotes"}, set(missing))
    instructions = (
        f"# 이번 호출에서 할 일 ({call_name}{QUOTES_SUFFIX})\n"
        f"앞 응답({call_name})의 항목이 아래 인용 ref를 썼지만 quotes에 그 인용문을 적지 않았습니다. "
        "ref마다 그 항목의 근거인 원문 구절을 quotes에 하나씩 넣습니다: ref는 아래 이름 그대로, documentId는 원문 머리의 문서 ID, "
        "text는 원문 글자 그대로(고치거나 요약하지 않음). 다른 섹션은 넣지 않고, 근거를 원문에서 찾을 수 없는 ref는 넣지 않습니다.\n"
        f"빠진 ref: {', '.join(missing)}\n\n# 그 ref를 쓴 항목\n" + "\n".join(items)
    )
    limit = output_limit(call_name + QUOTES_SUFFIX, min(8_000, 2_000 + 400 * len(missing)))
    return replace(
        base,
        prompt_version=QUOTES_PROMPT_VERSION,
        call_name=call_name + QUOTES_SUFFIX,
        instructions=instructions,
        output_schema=schema,
        max_output_tokens=limit,
    )


def _fill_missing_quotes(rules: FieldRules, material: ExtractionMaterial, call: CallSpec, known: dict[str, Any] | None, part: Any, call_model, budget) -> None:
    """섹션 항목이 쓴 인용 ref가 quotes에 없으면 그 인용문만 한 번 더 묻고 받은 것을 같은 조각에 붙입니다.
    실측(live-perf 0815, 2026-10-20): 일정 응답이 quotes에 q1~q25만 적고 항목은 q26~q35를 가리켜 QUOTE_REF_UNKNOWN 9건,
    근거를 잃은 일정 항목이 모두 빠짐. 묻는 호출이 실패하거나 여전히 빠지면 이전처럼 결합기가 빼거나 표시합니다."""
    missing = missing_quote_refs(part)
    if not missing:
        return
    request = quotes_request(rules.build_request(call, material, known), call.name, part, missing)
    if budget is not None and not budget(request):
        return
    response, _ = call_model(request, repair=False)
    if response is None or response.stop_reason is not StopReason.END:
        return
    try:
        answer = _parse(response.raw_text)
    except ValueError:
        return
    wanted = set(missing)
    validator = Draft202012Validator(request.output_schema["properties"]["quotes"]["items"] | {"$defs": request.output_schema.get("$defs", {})})
    for quote in answer.get("quotes") if isinstance(answer.get("quotes"), list) else []:
        # 받은 인용문은 하나씩 확인합니다: 형식이 틀리거나 묻지 않은 ref는 버리고 나머지만 붙입니다
        if isinstance(quote, dict) and quote.get("ref") in wanted and not any(validator.iter_errors(quote)):
            part.setdefault("quotes", []).append(quote)
            wanted.discard(quote["ref"])


CONTINUE_MARK = "이어서:"  # 구조 응답이 공급 묶음을 다 담지 못했다는 표시 (coverage.supplyGroups.reason 머리)
MAX_CONTINUATIONS = 10  # 공고 하나의 비용 상한(BudgetedModel)이 먼저 막을 수 있습니다


def _wants_more(part: dict[str, Any]) -> bool:
    coverage = (part.get("coverage") or {}).get("supplyGroups") or {}
    return coverage.get("status") == "PARTIAL" and str(coverage.get("reason") or "").startswith(CONTINUE_MARK)


def _continue_supply(rules: FieldRules, material: ExtractionMaterial, part: dict[str, Any], call_model, budget) -> None:
    """호실이 많아 한 번의 출력 한도에 공급 묶음을 다 담지 못한 공고: 이어받기 호출로 나머지를 받아 같은 조각에 붙입니다.
    실측: 김해·양산 다세대 일반매각 153호 — 한 번에 담지 못해 첫 단지 3호만 넣고 끝남(나머지 150호 가격 누락)."""
    call = rules.continuation
    for round_number in range(1, MAX_CONTINUATIONS + 1):
        if not _wants_more(part):
            return
        request = rules.build_request(call, material, structure_summary(part))
        if budget is not None and not budget(request):
            return
        response, _ = call_model(request, repair=False)
        if response is None or response.stop_reason is not StopReason.END:
            return
        try:
            more = _parse(response.raw_text)
        except ValueError:
            return
        if schema_errors(more, request.output_schema) is not None:
            return
        _merge_more(part, more, round_number)


def _ids(node: Any) -> list[str]:
    if isinstance(node, dict):
        own = [node["id"]] if isinstance(node.get("id"), str) else []
        return own + [i for value in node.values() for i in _ids(value)]
    if isinstance(node, list):
        return [i for value in node for i in _ids(value)]
    return []


def _rename_clashing_ids(part: dict[str, Any], groups: list[Any], round_number: int) -> None:
    """이어받기 응답이 앞에서 쓴 ID(공급 묶음·가격·수량)를 다시 쓰면 새 ID로 바꿉니다.
    그대로 붙이면 계약의 ID 중복 검사에 걸려 격리 단계가 뒤쪽 호실과 그 가격을 메모만 남기고 지웁니다(검토 2026-10-16).
    이어받기 호출은 앞 묶음의 ID만 보고 그 안의 가격·수량 ID는 모르므로 겹치기 쉽습니다."""
    taken = set(_ids({k: v for k, v in part.items() if k != "quotes"}))
    rename: dict[str, str] = {}
    for old in _ids(groups):
        if old in taken or old in rename:
            new, n = f"{old}~m{round_number}", 2
            while new in taken:
                new, n = f"{old}~m{round_number}-{n}", n + 1
            rename[old] = new
            taken.add(new)
        else:
            taken.add(old)
    if not rename:
        return
    stack: list[Any] = [groups]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("id") in rename:
                node["id"] = rename[node["id"]]
            if node.get("parentCountId") in rename:
                node["parentCountId"] = rename[node["parentCountId"]]
            if isinstance(node.get("supplyGroupIds"), list):
                node["supplyGroupIds"] = [rename.get(i, i) for i in node["supplyGroupIds"]]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _merge_more(part: dict[str, Any], more: dict[str, Any], round_number: int) -> None:
    """이어받기 응답을 구조 조각에 붙입니다. 인용 ref와 겹치는 ID는 새 이름으로, 누락 기록 위치는 붙인 자리만큼 옮깁니다."""
    rename = {q["ref"]: f"m{round_number}-{q['ref']}" for q in more.get("quotes", [])}
    for quote in more.get("quotes", []):
        part.setdefault("quotes", []).append({**quote, "ref": rename[quote["ref"]]})
    groups = more.get("supplyGroups") or []
    stack: list[Any] = [groups]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "quoteRefs" in node:
                node["quoteRefs"] = [rename.get(ref, ref) for ref in node["quoteRefs"]]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    _rename_clashing_ids(part, groups, round_number)
    offset = len(part.setdefault("supplyGroups", []))
    part["supplyGroups"].extend(groups)
    for entry in more.get("missingFields", []):
        target = re.sub(r"^/supplyGroups/(\d+)", lambda m: f"/supplyGroups/{int(m.group(1)) + offset}", entry.get("target", ""))
        part.setdefault("missingFields", []).append({**entry, "target": target})
    coverage = (more.get("coverage") or {}).get("supplyGroups")
    if coverage:
        part.setdefault("coverage", {})["supplyGroups"] = coverage
