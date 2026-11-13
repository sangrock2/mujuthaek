"""테스트 공용: 계약 예시를 AI 출력 조각과 결합 입력으로 바꿉니다."""

import json
from pathlib import Path

from mujuthaek_extraction.assemble import ai_output
from mujuthaek_extraction.assemble.assembler import AssemblyInput
from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.intake.model import ExtractionMaterial, TrustedContext

CONTRACTS = next(p for p in Path(__file__).resolve().parents if (p / "contracts" / "examples").is_dir()) / "contracts"
REGIONS = RegionCodeTable([("1100000000", "서울특별시", True), ("1111000000", "서울특별시 종로구", True)], reference_date="test")
SECTIONS = ai_output.SECTIONS


def example(name):
    return json.loads((CONTRACTS / "examples" / f"{name}.extracted.json").read_text(encoding="utf-8"))


def to_ai(node):
    """v1 → AI 출력: 근거는 quoteRefs로, 계산값은 제거."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "evidenceIds":
                out["quoteRefs"] = value
            elif key not in ("amountKrw", "regionCode", "applicationChannels"):
                out[key] = to_ai(value)
        return out
    if isinstance(node, list):
        return [to_ai(x) for x in node]
    return node


def ai_part(data, sections=SECTIONS):
    return {
        "quotes": [{"ref": e["id"], "documentId": e["sourceId"], "text": e["quote"]} for e in data["evidence"]],
        **{s: to_ai(data[s]) for s in sections},
        "coverage": {s: data["quality"]["coverage"][s] for s in sections},
        "missingFields": data["quality"]["missingFields"],
    }


def source_for(name, data):
    # 바이트 그대로 읽습니다. read_text()는 줄바꿈을 바꿔 문서 해시가 달라집니다.
    text = (CONTRACTS / "examples" / "sources" / f"{name}.synthetic.txt").read_bytes().decode("utf-8")
    context = TrustedContext(
        input=data["input"],
        source_references=tuple(data["sourceReferences"]),
        documents=tuple(data["documents"]),
        api_comparison_status="SKIPPED_NO_API_REFERENCE",
        api_reference=None,
    )
    material = ExtractionMaterial(text=text, text_document_id="text1", units=(), units_document_id=None, files=())
    return AssemblyInput(context=context, material=material, regions=REGIONS)


def every_call(rules):
    """나눠 부르는 호출(split_calls)까지 포함한 모든 호출. 녹화 응답을 호출 이름마다 준비할 때 씁니다."""
    return (*rules.calls, *(call for _, calls in rules.split_calls for call in calls))
