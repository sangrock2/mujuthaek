"""오프라인 사례 스크립트 공용: 과거 실험 출력을 변환한 ai-output 조각으로 intake → 결합 → 검증 → 보고서.

일회성 확인용이며 서비스 코드가 아닙니다. 네트워크·AI 호출이 없고 입력 파일은 읽기만 합니다.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mujuthaek_extraction.assemble.assembler import AssemblyInput, AssemblyResult, assemble
from mujuthaek_extraction.assemble.quotes import NormalizedText, normalize
from mujuthaek_extraction.assemble.regions import RegionCodeTable
from mujuthaek_extraction.intake import ApiReference, InMemorySourceReader, IntakeResult, build_intake
from mujuthaek_extraction.verify import SourceBundle, VerificationReport, verify_extraction

CHECKED_AT = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)  # 보고서 재현용 고정 시각
SECTIONS = ("notice", "locations", "schedules", "supplyGroups", "eligibility", "selectionRules", "requiredDocuments", "guidance")


def scope(level: str, *, locations=(), groups=(), category: str = "ALL", description: str = "공고 전체에 적용합니다.") -> dict[str, Any]:
    return {
        "level": level,
        "locationIds": list(locations),
        "supplyGroupIds": list(groups),
        "targetGroups": [],
        "supplyCategory": category,
        "resolution": "RESOLVED",
        "description": description,
    }


class QuoteBook:
    """과거 출력의 인용문 → ai-output quotes[]의 ref. 같은 문장은 ref 하나를 씁니다."""

    def __init__(self, document_id: str = "text"):
        self.document_id = document_id
        self.refs: dict[str, str] = {}

    def __call__(self, sources: list[dict[str, Any]]) -> list[str]:
        out = []
        for source in sources:
            text = source["quote"]
            if text not in self.refs:
                self.refs[text] = f"q{len(self.refs) + 1}"
            out.append(self.refs[text])
        return list(dict.fromkeys(out))

    def quotes(self) -> list[dict[str, str]]:
        return [{"ref": ref, "documentId": self.document_id, "text": text} for text, ref in self.refs.items()]


class FixedApi:
    def __init__(self, reference: ApiReference | None):
        self.reference = reference

    def find(self, raw):
        return self.reference


@dataclass
class CaseResult:
    intake: IntakeResult
    assembled: AssemblyResult
    report: VerificationReport | None

    @property
    def candidate(self) -> dict[str, Any] | None:
        return self.report.candidate if self.report else self.assembled.candidate


def run_case(
    event: dict[str, Any],
    part: dict[str, Any],
    *,
    api_reference: ApiReference | None,
    regions: RegionCodeTable | None = None,
    default_sido: str | None = None,
    out_dir: Path | None = None,
) -> CaseResult:
    intake = build_intake(event, InMemorySourceReader(), FixedApi(api_reference))
    if not intake.ready:
        raise SystemExit(f"intake가 READY가 아닙니다: {intake.issues}")
    assembled = assemble([part], AssemblyInput(intake.context, intake.material, regions=regions, default_sido=default_sido))
    report = None
    if assembled.candidate is not None:
        sources = SourceBundle.from_material(intake.material)
        report = verify_extraction(assembled.candidate, sources, intake.context.api_reference, clock=lambda: CHECKED_AT)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "ai-output.json").write_text(json.dumps(part, ensure_ascii=False, indent=2), encoding="utf-8")
        if report:
            (out_dir / "verified-candidate.json").write_text(json.dumps(report.candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    return CaseResult(intake, assembled, report)


NEARBY_WINDOW = 120  # 정규화 글자 수. 인용의 단어들이 이 안에 모두 있으면 표·줄 배치 차이로 봅니다(진단용)
SCATTERED = "원문에 그대로는 없음 — 단어가 가까이 흩어져 있음 (표 칸·줄 순서 차이 가능)"
ABSENT = "원문에 없음 — 근처에서도 찾지 못함"


def _scattered(index: NormalizedText, quote: str) -> bool:
    tokens = [normalize(t) for t in re.split(r"[\s()]+", quote) if normalize(t)]
    if not tokens:
        return False
    for match in re.finditer(re.escape(tokens[0]), index.value):
        window = index.value[match.start() : match.start() + NEARBY_WINDOW]
        if all(token in window for token in tokens):
            return True
    return False


def classify_quotes(part: dict[str, Any], text: str) -> dict[str, list[str]]:
    """보고서 진단용 분류. 결합·검증 규칙과는 별개이며 근거 인정 여부를 바꾸지 않습니다."""
    index = NormalizedText(text)
    groups: dict[str, list[str]] = {"생략 부호(...) 포함": [], "원문 한 곳": [], "원문 여러 곳 (같은 문장 반복)": [], SCATTERED: [], ABSENT: []}
    for quote in part["quotes"]:
        value = quote["text"]
        hits = len(index.find_all(normalize(value)))
        if "..." in value or "…" in value:
            groups["생략 부호(...) 포함"].append(value)
        elif hits == 1:
            groups["원문 한 곳"].append(value)
        elif hits > 1:
            groups["원문 여러 곳 (같은 문장 반복)"].append(value)
        elif _scattered(index, value):
            groups[SCATTERED].append(value)
        else:
            groups[ABSENT].append(value)
    return groups


def render(
    *,
    title: str,
    inputs: str,
    result: CaseResult,
    part: dict[str, Any],
    legacy_counts: dict[str, Any],
    interpretation: list[str],
    skipped: list[str],
    extra_sections: list[tuple[str, list[str]]] = (),
    list_limit: int = 15,
) -> str:
    candidate = result.candidate
    lines = [
        f"# 오프라인 사례 보고서 — {title}",
        "",
        "생성: `services/extraction/scripts/` 오프라인 사례 스크립트 (네트워크·AI 호출 없음, 입력 파일 읽기 전용).",
        f"입력: {inputs}",
        "**eventId·rawPostId는 가상 값**이며 실제 수집 기록이 아닙니다. 과거 실험 출력은 정답표가 아닙니다.",
        "",
        "## 1. 결과 요약",
        "",
    ]
    if candidate is None:
        lines += ["결합 결과 후보를 만들지 못했습니다.", ""]
        issues = result.assembled.issues
    else:
        verification = candidate["quality"]["verification"]
        issues = candidate["quality"]["reviewIssues"]
        errors = result.report.contract_errors if result.report else result.assembled.contract_errors
        lines += [
            "| 항목 | 값 |",
            "|---|---|",
            f"| 최종 검증 상태 | **{verification['status']}** |",
            f"| 원문 근거 상태 (V2·V3) | {verification['sourceStatus']} (결합 후 남은 항목 기준. 근거를 못 찾아 빠진 항목은 아래 이슈 참고) |",
            f"| API 대조 상태 (V4) | {verification['apiComparison']['status']} |",
            f"| 검수 이슈 수 | {len(issues)} |",
            f"| 계약 검사 오류 | {len(errors)} |",
            "",
        ]

    lines += ["## 2. 섹션별 항목 수", "", "| 섹션 | 과거 출력 | 변환 | 결합 후 (근거 확인) | coverage |", "|---|---:|---:|---:|---|"]
    for section in SECTIONS:
        converted = (1 if section == "notice" else len(part[section])) if section in part else 0
        after = "-" if candidate is None else (1 if section == "notice" else len(candidate[section]))
        coverage = "-" if candidate is None else candidate["quality"]["coverage"][section]["status"]
        lines.append(f"| {section} | {legacy_counts.get(section, 0)} | {converted} | {after} | {coverage} |")

    if candidate is not None:
        lines += ["", "## 3. API 대조 (V4)", ""]
        fields = candidate["quality"]["verification"]["apiComparison"]["fields"]
        if fields:
            lines += ["| API 경로 | 기대값 | 추출값 | 결과 | 사유 |", "|---|---|---|---|---|"]
            lines += [f"| `{f['sourcePath']}` | {f['expected']} | {f['actual']} | {f['status']} | {f['reason'] or ''} |" for f in fields]
        else:
            lines.append(f"비교한 필드가 없습니다 (`{candidate['quality']['verification']['apiComparison']['status']}`).")

    counts = Counter(issue["code"] for issue in issues)
    lines += ["", "## 4. 검수 이슈 (코드별)", "", "| 코드 | 건수 | 예시 위치 |", "|---|---:|---|"]
    for code, n in counts.most_common():
        example = next(i["target"] for i in issues if i["code"] == code)
        lines.append(f"| {code} | {n} | `{example}` |")
    notes = Counter(note.split(": ", 1)[1] if ": " in note else note for note in result.assembled.notes)
    if notes:
        lines += ["", "결합 메모 (완료를 막지 않음):", *[f"- {text} ({n}건)" for text, n in notes.most_common(8)]]

    groups = classify_quotes(part, result.intake.material.text)
    lines += ["", "## 5. 인용문 분류 (과거 출력 인용 → 원문 텍스트)", "", "| 분류 | 개수 |", "|---|---:|"]
    lines += [f"| {name} | {len(values)} |" for name, values in groups.items()]
    for name in ("원문 여러 곳 (같은 문장 반복)", SCATTERED, ABSENT):
        values = groups[name]
        if values:
            shown = values[:list_limit]
            lines += ["", f"{name} (최대 {list_limit}개 표시):", *[f"- `{v}`" for v in shown]]
            if len(values) > list_limit:
                lines.append(f"- … 외 {len(values) - list_limit}개")

    lines += ["", "## 6. 해석", "", *[f"- {item}" for item in interpretation]]
    for heading, body in extra_sections:
        lines += ["", f"## {heading}", "", *body]
    lines += ["", "## 변환하지 못했거나 되살린 항목", "", *[f"- {item}" for item in skipped], ""]
    return "\n".join(lines)
