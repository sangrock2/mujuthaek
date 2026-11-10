"""분야별 추출 규칙의 공통 틀 (2-02 프레임워크).

분야 규칙 = 프롬프트 파일 + 섹션별 호출 목록(결정 E2). 요청에는 원문·호별 표·앞 호출이 만든 구조 ID만 넣습니다.
같은 공고의 호출끼리 [공통 지시 → 원문] 앞부분이 같도록 두고, 호출마다 다른 지시는 뒤에 둡니다(프롬프트 캐시).
이벤트 ID·원본 ID·해시·API 원본 값은 요청에 넣지 않습니다(독립 대조를 위해).
"""

from __future__ import annotations

import copy
import functools
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.model.base import ModelRequest


@dataclass(frozen=True)
class CallSpec:
    name: str
    sections: tuple[str, ...]
    instructions: str
    uses_structure: bool  # 앞 호출(구조)이 만든 위치·공급 ID를 함께 줄지
    max_output_tokens: int


@dataclass(frozen=True)
class FieldRules:
    """분야 하나의 추출 규칙(프롬프트·섹션별 호출 목록·큰 공고 나누기)이며, 호출마다 모델 요청을 만들어 줍니다."""

    field: str
    prompt_version: str
    prompt_path: Path
    calls: tuple[CallSpec, ...]  # 순서대로 호출합니다. 첫 호출은 notice를 포함한 구조 호출입니다
    continuation: CallSpec | None = None  # 구조 응답이 공급 묶음을 다 담지 못했다고 표시하면 이어받는 호출 (extract._continue_supply)
    # 원문이 이 글자 수보다 긴 공고는 split_calls의 호출 이름을 그 나눈 호출들로 바꿉니다.
    # 실측(2026-10-16 시험, 원문 약 15만 자 분양 공고): 자격·가점·서류를 한 호출에 담다가 계층별 소득 기준·가점 행·서류를 요약하거나 빠뜨림
    large_text_chars: int | None = None
    split_calls: tuple[tuple[str, tuple[CallSpec, ...]], ...] = ()
    # 공급·가격 표를 코드가 행 단위로 옮길지(supply_tables, 구조 방식 2026-10-17). AI는 표마다 열 의미만 답합니다
    supply_tables: bool = False
    # 다시 받아도 출력 한도로 잘린 호출을 나눠 부를 호출들(extract.run_split, 2026-10-24 세 번째 채점: 서류 호출이 한 표에서 반복 폭주해
    # 두 번 다 잘리고 서류 45개가 모두 빠짐). 나눈 호출이 하나라도 답을 주면 그 서류는 남고, 못 받은 묶음은 PARTIAL로 재확인·검수에 갑니다
    runaway_splits: tuple[tuple[str, tuple[CallSpec, ...]], ...] = ()

    def calls_for(self, material: ExtractionMaterial) -> tuple[CallSpec, ...]:
        if self.large_text_chars is None or len(material.text) < self.large_text_chars:
            return self.calls
        split = dict(self.split_calls)
        return tuple(part for call in self.calls for part in split.get(call.name, (call,)))

    def system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").replace("{{ATTRIBUTES}}", attribute_lines())

    def build_request(
        self,
        call: CallSpec,
        material: ExtractionMaterial,
        structure: dict[str, Any] | None = None,
        repair_error: str | None = None,
    ) -> ModelRequest:
        """호출 하나의 모델 요청을 만듭니다. 원문·호별 표는 앞(캐시되는 부분)에, 호출별 지시·구조 ID·이전 오류는 뒤에 둡니다."""
        start, end = _fence(material.text, "원문")
        blocks = [f"# 문서 {material.text_document_id} (공고 원문)\n{start}\n{material.text}\n{end}"]
        if material.units:
            rows = "\n".join(f"{i}: {json.dumps(row, ensure_ascii=False, sort_keys=True)}" for i, row in enumerate(material.units))
            start, end = _fence(rows, "호별 표")
            blocks.append(f"# 문서 {material.units_document_id} (수집기가 읽은 호별 표, 행 번호: 값)\n{start}\n{rows}\n{end}")
        volatile = [f"# 이번 호출에서 할 일 ({call.name})\n맡은 섹션: {', '.join(call.sections)}\n{call.instructions}"]
        if call.uses_structure and structure is not None:
            volatile.append("# 이미 추출한 구조 (scope·locationId에는 이 ID만 사용합니다)\n" + json.dumps(structure, ensure_ascii=False, sort_keys=True))
        if repair_error is not None:
            volatile.append(
                f"# 이전 응답 오류\n이전 응답에 다음 문제가 있었습니다. 같은 지시에 따라 문제를 고친 JSON 객체 하나를 다시 출력합니다.\n{repair_error}"
            )
        return ModelRequest(
            prompt_version=f"{self.field}/{self.prompt_version}/{call.name}",
            call_name=call.name,
            system=self.system_prompt(),
            user="\n\n".join(blocks),
            instructions="\n\n".join(volatile),
            output_schema=call_schema(call.sections, document_ids(material)),
            max_output_tokens=output_limit(call.name, call.max_output_tokens),
            shared_schema=shared_schema(tuple(document_ids(material))),
        )


OUTPUT_LIMIT_ENV = "EXTRACTION_MAX_OUTPUT_TOKENS"


def output_limit(call_name: str, default: int) -> int:
    """호출의 출력 한도. 설정 EXTRACTION_MAX_OUTPUT_TOKENS(예: "selection=32000,documents=24000")에 그 호출이 있으면 그 값을 씁니다.
    형식이 틀리거나 0 이하인 값은 무시하고 기본값을 씁니다(한도는 성공한 호출 다시 쓰기의 요청 열쇠에도 들어갑니다)."""
    for entry in os.getenv(OUTPUT_LIMIT_ENV, "").split(","):
        name, _, value = entry.partition("=")
        if name.strip() == call_name and value.strip().isdigit() and int(value) > 0:
            return int(value)
    return default


def _fence(text: str, label: str) -> tuple[str, str]:
    """원문을 감싸는 표시. 원문 안에 같은 표시가 있으면(PDF에 「<<<원문 끝>>>」을 적어 데이터 밖으로 나가려는 경우) 원문에 없는
    번호 붙은 표시를 씁니다. 원문 글자는 바꾸지 않습니다(인용문이 원문 그대로여야 하므로). 보통 공고는 표시가 늘 같습니다(캐시 유지)."""
    number = 1
    while True:
        suffix = "" if number == 1 else f" {number}"
        start, end = f"<<<{label} 시작{suffix}>>>", f"<<<{label} 끝{suffix}>>>"
        if start not in text and end not in text:
            return start, end
        number += 1


# 공통 지시(system prompt)의 속성 목록에 넣지 않고, 그 속성을 쓰는 호출의 지시에만 적는 속성. 공통 지시는 모든 호출의 앞부분이라
# 바꾸면 구조 호출·다른 담당의 캐시까지 모두 바뀝니다(2026-11-09 막내 자녀 나이: 자격 호출 지시 CHILD_AGE_NOTE에 적음)
CALL_ONLY_ATTRIBUTES = frozenset({"YOUNGEST_CHILD_AGE_YEARS"})


def attribute_line(spec: dict[str, Any]) -> str:
    extra = f", 형식 {spec['pattern']}" if "pattern" in spec else ""
    extra += f", 값 {'/'.join(spec['enum'])}" if "enum" in spec else ""
    extra += ", benchmark 필수" if spec.get("benchmarkRequired") else ""
    return f"- {spec['code']}: {spec['meaning']} (단위 {spec['unit']}, 값 {spec['valueType']}, 연산자 {'/'.join(spec['operators'])}{extra})"


def attribute_lines(codes: frozenset[str] | None = None) -> str:
    """속성 사전의 줄들. codes를 주면 그 속성만(호출 지시용), 없으면 CALL_ONLY_ATTRIBUTES를 뺀 전부(공통 지시용)."""
    specs = tools().ATTRIBUTE_DICTIONARY["attributes"]
    chosen = [s for s in specs if (s["code"] in codes if codes is not None else s["code"] not in CALL_ONLY_ATTRIBUTES)]
    return "\n".join(attribute_line(spec) for spec in chosen)


def document_ids(material: ExtractionMaterial) -> list[str]:
    return [material.text_document_id, *([material.units_document_id] if material.units_document_id else [])]


def call_schema(sections: tuple[str, ...], documents: list[str] | None = None) -> dict[str, Any]:
    """AI 출력 형식에서 이번 호출이 맡은 섹션만 남기고 필수로 만듭니다. documents를 주면 인용의 문서 ID를 그 목록으로 제한합니다."""
    schema = copy.deepcopy(ai_output.schema())
    if documents:  # 실측: 문서 ID를 문자열로만 두면 모델이 'notice'나 공고번호를 지어 씁니다
        schema["$defs"]["quote"]["properties"]["documentId"] = {"enum": list(documents)}
    properties = schema["properties"]
    schema["properties"] = {key: properties[key] for key in ("quotes", *sections, "missingFields")}
    schema["properties"]["coverage"] = {
        "type": "object",
        "additionalProperties": False,
        "required": list(sections),
        "properties": {section: {"$ref": "#/$defs/coverageItem"} for section in sections},
    }
    schema["required"] = ["quotes", *sections, "coverage"]
    return schema


@functools.lru_cache(maxsize=8)
def shared_schema(documents: tuple[str, ...]) -> dict[str, Any]:
    """모든 호출이 함께 쓰는 출력 형식: 모든 섹션·공급표 열 의미(tables)를 선택 칸으로 둡니다. 호출마다 맡은 섹션만 채웁니다."""
    from mujuthaek_extraction.supply_tables import MAPPING_SCHEMA  # 순환 import 피함

    schema = call_schema(tuple(ai_output.SECTIONS), list(documents))
    schema["required"] = []
    schema["properties"]["coverage"]["required"] = []
    schema["properties"]["tables"] = copy.deepcopy(MAPPING_SCHEMA["properties"]["tables"])
    return schema


def structure_summary(part: Any) -> dict[str, Any] | None:
    """구조 호출 응답에서 뒤 호출이 참조할 ID와 이름만 뽑습니다. AI 자신의 출력이며 신뢰 문맥이 아닙니다."""
    if not isinstance(part, dict):
        return None
    keep = {
        "locations": ("id", "kind", "parentLocationId", "complexName", "buildingName", "region"),
        "supplyGroups": ("id", "locationId", "itemKind", "housingTypeCode", "unitLabel", "floor"),
    }
    summary: dict[str, Any] = {}
    for section, keys in keep.items():
        items = part.get(section)
        if isinstance(items, list):
            summary[section] = [{k: item.get(k) for k in keys} for item in items if isinstance(item, dict)]
    notice = part.get("notice")
    if isinstance(notice, dict) and isinstance(notice.get("targetGroups"), list):
        summary["targetGroups"] = notice["targetGroups"]
    return summary
