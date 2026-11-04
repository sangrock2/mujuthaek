"""재확인 에이전트가 쓰는 도구 5개. 모두 공고 원문과 검증기만 읽고 아무것도 저장·발행하지 않습니다.

- search_source: 원문에서 낱말·숫자로 구간 찾기(쪽 번호·앞뒤 글자)
- read_page: PDF 한 쪽의 글자(「--- N쪽 ---」 표시 기준)
- check_quote: 인용문이 원문에 있는지(추출과 같은 찾기 규칙), 없으면 비슷한 줄 제안
- validate_item: 고친 항목을 넣어 결합·검증했을 때 그 항목에 남는 문제
- submit_fix: 고친 항목 제출 또는 포기(끝내기). 채택 여부는 알려 주지 않습니다(recheck.adopt가 정함)

결과는 JSON 글자이고 RESULT_CHARS를 넘으면 자릅니다. 잘못된 입력은 예외가 아니라 {"error": 코드, "message": …}로 돌려줘
AI가 다른 방법을 고르게 합니다. 엄격 형식(strict)에 맞게 입력 칸은 모두 필수이고, 자유 형식인 항목은 JSON 글자로 받습니다.
"""

from __future__ import annotations

import bisect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from mujuthaek_extraction.assemble.quotes import NormalizedText, candidates, loose, normalize
from mujuthaek_extraction.intake.model import ExtractionMaterial
from mujuthaek_extraction.judgment.pages import FILE_MARK, PAGE_MARK
from mujuthaek_extraction.model.base import ToolCall, ToolSpec
from mujuthaek_extraction.recheck import DROPPED_PROBLEM, merge_recheck, problem_items
from mujuthaek_extraction.verify import VerificationReport

RESULT_CHARS = 2_000  # 도구 결과 한 번의 글자 상한(다음 차례 입력이 되므로 비용)
SNIPPET_CHARS = 120  # 찾은 구간 앞뒤로 보여 줄 글자
PAGE_CHARS = 1_800  # read_page가 한 번에 돌려줄 글자
MAX_HITS = 5
NEAR_MIN_SCORE = 70  # check_quote 제안의 최소 유사도(0~100)


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


SPECS = (
    ToolSpec(
        "search_source",
        "공고 원문에서 낱말·숫자(2~60자)로 구간을 찾습니다. 근거가 원문 어디에 있는지 모를 때 먼저 씁니다. 공백·표 칸 구분(|)은 무시합니다.",
        _object({"query": {"type": "string"}, "limit": {"type": "integer"}}),
    ),
    ToolSpec(
        "read_page",
        "PDF 원문의 한 쪽 글자를 읽습니다. 찾은 구간의 앞뒤 문맥이 더 필요할 때 씁니다. 긴 쪽은 from_char부터 이어 읽습니다.",
        _object({"page": {"type": "integer"}, "from_char": {"type": "integer"}}),
    ),
    ToolSpec(
        "check_quote",
        "인용문이 원문에 글자 그대로 있는지 확인합니다. 없으면 원문에서 가장 비슷한 줄을 보여 줍니다. 제출 전에 인용문마다 확인합니다.",
        _object({"quote": {"type": "string"}}),
    ),
    ToolSpec(
        "validate_item",
        "고친 항목을 넣어 검증기를 돌리고 그 항목에 남는 문제를 돌려줍니다. item_json은 바꿀 칸만 적은 JSON(나머지는 처음 값), "
        "quotes는 새로 쓴 인용(ref·text)입니다.",
        _object(
            {
                "item_json": {"type": "string"},
                "quotes": {"type": "array", "items": _object({"ref": {"type": "string"}, "text": {"type": "string"}})},
            }
        ),
    ),
    ToolSpec(
        "submit_fix",
        "고친 항목을 제출하고 끝냅니다. item_json은 바꿀 칸만 적은 JSON입니다(나머지는 처음 값). "
        "원문으로 확인하지 못했으면 give_up에 이유를 적고 item_json은 빈 글자로 둡니다(처음 값이 유지됩니다).",
        _object(
            {
                "item_json": {"type": "string"},
                "quotes": {"type": "array", "items": _object({"ref": {"type": "string"}, "text": {"type": "string"}})},
                "give_up": {"type": "string"},
            }
        ),
    ),
)
FINAL_SPECS = tuple(spec for spec in SPECS if spec.name == "submit_fix")  # 마지막 차례에 쓸 수 있는 도구

# validate_item이 부르는 검사: (항목, 인용 목록) → 그 항목에 남는 문제 문구들
ItemCheck = Callable[[Any, list[dict[str, str]]], list[str]]


@dataclass
class Submission:
    item: Any | None  # 고친 항목(포기면 None)
    quotes: list[dict[str, str]]
    give_up: str | None = None


@dataclass
class RepairTools:
    """한 항목을 고치는 동안 쓰는 도구 묶음입니다. 원문 색인은 처음 쓸 때 한 번 만듭니다.

    base_item·base_quotes(2026-11-05 첫 비교: 큰 공급 묶음·자격 항목을 통째로 다시 내다 다른 칸을 깨뜨려 버려짐):
      item_json은 바꿀 칸만 적은 조각이어도 되고, 처음 항목에 덮어써 합칩니다(객체는 칸마다, 목록·값은 통째로).
      합친 항목이 가리키는 처음 인용(quoteRefs)은 제출 인용에 자동으로 붙입니다.
    known_codes: 처음부터 있던 문제 코드. 제출한 항목에 처음에 없던 문제가 생기면 한 번은 받지 않고 문제를 돌려줘 고칠 기회를 줍니다
      (마지막 차례면 그대로 받습니다. 채택은 어차피 recheck.adopt가 정합니다).
    final: 마지막 차례. 이때는 submit_fix만 쓸 수 있습니다(검색만 하다 끝나지 않게)."""

    material: ExtractionMaterial
    check: ItemCheck
    base_item: Any | None = None
    base_quotes: dict[str, str] = field(default_factory=dict)
    known_codes: frozenset[str] = frozenset()
    final: bool = False
    submission: Submission | None = None
    calls: dict[str, int] = field(default_factory=dict)  # 도구별 호출 수(기록용)
    rejected_submissions: int = 0  # 새 문제로 한 번 돌려보낸 제출 수(기록용)
    _index: NormalizedText | None = None
    _pages: tuple[list[int], list[int], list[int]] | None = None

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return FINAL_SPECS if self.final else SPECS

    def run(self, call: ToolCall) -> str:
        """도구 하나를 실행해 JSON 글자를 돌려줍니다. 어떤 입력에도 예외를 내지 않습니다."""
        self.calls[call.name] = self.calls.get(call.name, 0) + 1
        handler = getattr(self, "_" + call.name, None)
        if call.name not in {spec.name for spec in SPECS} or handler is None:
            return _error("UNKNOWN_TOOL", f"없는 도구입니다: {call.name[:40]}")
        if call.name not in {spec.name for spec in self.specs}:
            return _error("FINAL_TURN", "마지막 차례입니다. submit_fix로 고친 항목을 내거나 give_up에 이유를 적습니다.")
        try:
            args = json.loads(call.arguments)
        except ValueError:
            return _error("BAD_ARGUMENTS", "도구 입력이 JSON이 아닙니다.")
        if not isinstance(args, dict):
            return _error("BAD_ARGUMENTS", "도구 입력은 객체여야 합니다.")
        try:
            return _limit(handler(**args))
        except TypeError:
            return _error("BAD_ARGUMENTS", "도구 입력 칸이 맞지 않습니다.")

    # ── 도구 ──────────────────────────────────────────────────────────────

    def _search_source(self, query: str, limit: int) -> dict[str, Any]:
        query = (query or "").strip()
        if not 2 <= len(query) <= 60:
            return {"error": "BAD_QUERY", "message": "검색어는 2~60자입니다."}
        index = self._text_index()
        spans = index.find_all(normalize(query)) or index.loose_index().find_all(loose(query))
        hits = [self._hit(start, end) for start, end in spans[: max(1, min(int(limit or MAX_HITS), MAX_HITS))]]
        return {"total": len(spans), "hits": hits}

    def _read_page(self, page: int, from_char: int) -> dict[str, Any]:
        positions, numbers, _ = self._page_marks()
        if not positions:
            return {"error": "NO_PAGES", "message": "쪽 표시가 없는 원문입니다. search_source로 찾습니다."}
        starts = [p for p, n in zip(positions, numbers, strict=True) if n == page]
        if not starts:
            return {"error": "NO_SUCH_PAGE", "message": f"{page}쪽이 없습니다. 쪽은 {min(numbers)}~{max(numbers)}입니다."}
        text = self.material.text
        pieces = []
        for start in starts:  # 2단 쪽(왼쪽·오른쪽)은 이어서 돌려줍니다
            after = bisect.bisect_right(positions, start)
            end = positions[after] if after < len(positions) else len(text)
            pieces.append(text[start:end])
        whole = "".join(pieces)
        offset = max(0, int(from_char or 0))
        chunk = whole[offset : offset + PAGE_CHARS]
        return {"page": page, "from_char": offset, "text": chunk, "more": offset + len(chunk) < len(whole)}

    def _check_quote(self, quote: str) -> dict[str, Any]:
        quote = (quote or "").strip()
        if not quote:
            return {"error": "EMPTY_QUOTE", "message": "인용문이 비었습니다."}
        spans, exact = candidates(self.material.text, quote, self._text_index())
        if spans:
            return {"found": True, "places": len(spans), "exact": exact, "page": self._page_at(spans[0][0])}
        return {"found": False, "near": self._near(quote)}

    def _validate_item(self, item_json: str, quotes: list[dict[str, str]]) -> dict[str, Any]:
        merged = self._merged(item_json, quotes)
        if isinstance(merged, str):
            return {"error": "BAD_ITEM", "message": merged}
        return {"problems": self.check(*merged)[:10]}

    def _submit_fix(self, item_json: str, quotes: list[dict[str, str]], give_up: str) -> dict[str, Any]:
        if give_up and give_up.strip():
            self.submission = Submission(None, [], give_up.strip()[:300])
            return {"received": True}
        merged = self._merged(item_json, quotes)
        if isinstance(merged, str):
            return {"error": "BAD_ITEM", "message": merged}
        item, all_quotes = merged
        new = [p for p in self.check(item, all_quotes) if problem_code(p) not in self.known_codes]
        if new and not self.final and self.rejected_submissions == 0:
            self.rejected_submissions += 1
            message = "제출한 항목에 처음에 없던 문제가 생겼습니다. 고쳐서 다시 내거나, 원문으로 확인하지 못했으면 give_up합니다."
            return {"received": False, "error": "NEW_PROBLEMS", "problems": new[:5], "message": message}
        self.submission = Submission(item, all_quotes)
        return {"received": True}

    def _merged(self, item_json: str, quotes: list[dict[str, str]]) -> tuple[Any, list[dict[str, str]]] | str:
        """제출 조각을 처음 항목에 합치고, 합친 항목이 가리키는 처음 인용을 붙입니다. 잘못되면 이유 글자."""
        patch = _parse_item(item_json)
        if isinstance(patch, str):
            return patch
        item = _merge(self.base_item, patch) if isinstance(self.base_item, dict) else patch
        cleaned = _clean_quotes(quotes)
        given = {q["ref"] for q in cleaned}
        inherited = [{"ref": ref, "text": self.base_quotes[ref]} for ref in _refs(item) if ref not in given and ref in self.base_quotes]
        return item, [*cleaned, *inherited]

    # ── 내부 ──────────────────────────────────────────────────────────────

    def _text_index(self) -> NormalizedText:
        if self._index is None:
            self._index = NormalizedText(self.material.text)
        return self._index

    def _page_marks(self) -> tuple[list[int], list[int], list[int]]:
        if self._pages is None:
            text = self.material.text
            found = [(m.start(), int(m.group(1))) for m in PAGE_MARK.finditer(text)]
            self._pages = ([p for p, _ in found], [n for _, n in found], [m.start() for m in FILE_MARK.finditer(text)])
        return self._pages

    def _page_at(self, position: int) -> int | None:
        positions, numbers, files = self._page_marks()
        at = bisect.bisect_right(positions, position) - 1
        if at < 0:
            return None
        boundary = bisect.bisect_right(files, position) - 1
        if boundary >= 0 and files[boundary] > positions[at]:
            return None  # 쪽 표시 뒤에 다른 첨부가 시작됨
        return numbers[at]

    def _hit(self, start: int, end: int) -> dict[str, Any]:
        text = self.material.text
        return {"page": self._page_at(start), "start": start, "end": end, "snippet": text[max(0, start - SNIPPET_CHARS) : end + SNIPPET_CHARS]}

    def _near(self, quote: str) -> list[dict[str, Any]]:
        """원문 줄(이웃한 두 줄 묶음 포함) 가운데 인용문과 가장 비슷한 것 3개."""
        lines = [line for line in self.material.text.split("\n") if line.strip()]
        windows = [*lines, *(a + "\n" + b for a, b in zip(lines, lines[1:], strict=False))]
        scored = sorted(((fuzz.partial_ratio(quote, w), w) for w in windows), key=lambda pair: -pair[0])
        near = []
        for score, window in scored:
            if score < NEAR_MIN_SCORE or len(near) >= 3:
                break
            if window not in (n["text"] for n in near):
                near.append({"text": window[:300], "score": round(score)})
        return near


def item_check(
    parts: list[dict[str, Any]],
    evaluate: Callable[[list[dict[str, Any]]], VerificationReport | None],
    section: str,
    item_id: str | None,
    document_id: str,
) -> ItemCheck:
    """validate_item의 검사: 고친 항목만 처음 조각에 바꿔 넣고(재확인 합치기와 같은 규칙) 결합·검증해, 그 항목에 남는 문제를 돌려줍니다."""

    def check(item: Any, quotes: list[dict[str, str]]) -> list[str]:
        if section != "notice" and item.get("id") != item_id:
            return [f"ID_CHANGED: 항목 id는 {item_id}로 그대로 둡니다."]
        answer = {"quotes": [{"ref": q["ref"], "documentId": document_id, "text": q["text"]} for q in quotes], section: item if section == "notice" else [item]}
        sent = {"items": {section: {item_id}} if section != "notice" else {}, "notice": None if section == "notice" else set()}
        report = evaluate(merge_recheck(parts, answer, (), sent))
        if report is None:
            return ["ASSEMBLY_FAILED: 이 항목을 넣으면 공고를 결합하지 못합니다."]
        problems = problem_items(report).get((section, item_id), [])
        if section != "notice" and item_id not in {x.get("id") for x in report.candidate.get(section) or []}:
            problems = [DROPPED_PROBLEM, *problems]
        return problems

    return check


def _merge(base: Any, patch: Any) -> Any:
    """객체는 칸마다 덮어쓰고(없는 칸은 처음 값 유지), 목록·값은 통째로 바꿉니다."""
    if isinstance(base, dict) and isinstance(patch, dict):
        return {**base, **{key: _merge(base.get(key), value) for key, value in patch.items()}}
    return patch


def _refs(node: Any) -> list[str]:
    """항목 안의 모든 quoteRefs(중첩 포함), 처음 나온 순서."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "quoteRefs" and isinstance(value, list):
                found += [r for r in value if isinstance(r, str)]
            else:
                found += _refs(value)
    elif isinstance(node, list):
        for value in node:
            found += _refs(value)
    return list(dict.fromkeys(found))


def problem_code(problem: str) -> str:
    """문제 문구의 앞 코드(「CODE /위치: 설명」 또는 「CODE: 설명」)."""
    return problem.split(" ", 1)[0].split(":", 1)[0]


def _parse_item(item_json: str) -> Any:
    """항목 JSON을 읽습니다. 잘못되면 이유 글자를 돌려줍니다."""
    try:
        item = json.loads(item_json)
    except ValueError:
        return "item_json이 JSON이 아닙니다."
    if not isinstance(item, dict):
        return "item_json은 객체여야 합니다."
    return item


def _clean_quotes(quotes: Any) -> list[dict[str, str]]:
    return [
        {"ref": str(q["ref"])[:40], "text": str(q["text"])}
        for q in quotes or []
        if isinstance(q, dict) and isinstance(q.get("ref"), str) and isinstance(q.get("text"), str) and q["text"].strip()
    ]


def _error(code: str, message: str) -> str:
    return json.dumps({"error": code, "message": message}, ensure_ascii=False)


def _limit(result: dict[str, Any]) -> str:
    """결과를 JSON으로. 너무 길면 긴 글 칸부터 줄여 RESULT_CHARS 안에 맞춥니다."""
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= RESULT_CHARS:
        return text
    shrunk = json.loads(text)
    for budget in (600, 300, 120, 40):
        _shrink(shrunk, budget)
        text = json.dumps({**shrunk, "truncated": True}, ensure_ascii=False)
        if len(text) <= RESULT_CHARS:
            return text
    return json.dumps({"error": "RESULT_TOO_LONG", "message": "결과가 너무 깁니다. 범위를 좁혀 다시 찾습니다."}, ensure_ascii=False)


def _shrink(node: Any, budget: int) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and len(value) > budget:
                node[key] = value[:budget] + "…"
            else:
                _shrink(value, budget)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, str) and len(value) > budget:
                node[index] = value[:budget] + "…"
            else:
                _shrink(value, budget)
