"""V9 비교 방향 대조 (2026-10-20 검토 후 추가): 자격 조건의 비교 연산자가 근거 인용문의 방향 말과 맞는지 봅니다.

값–인용 대조(claims.py)는 숫자가 인용문에 있는지만 봅니다. 그래서 「만 19세 이상」을 AGE_YEARS LTE 19로 옮겨도
숫자 19는 인용문에 있으므로 자동 완료되었습니다(재현: 주택 예시의 GTE를 LTE로 바꿔도 PASSED).
여기서는 LT·LTE·GT·GTE·BETWEEN 조건마다 인용문에서 그 숫자(+단위) **바로 뒤**에 붙은 방향 말을 읽어 연산자와 비교합니다.

- 방향 말(보수적으로 이것만 읽습니다):
  LTE ← 이하·이내·까지 / LT ← 미만·미달 / GTE ← 이상·부터 / GT ← 초과·넘는·넘으면(「넘」, 단 「넘지」는 뺌)
- BETWEEN은 아래 값이 이상·초과, 위 값이 이하·미만이면 맞는 것으로 봅니다.
- 숫자 표기는 값–인용 대조와 같게 읽습니다: 쉼표·띄어쓰기, 억·만원 표기, 표 단위(천원·만원), 2년 = 24개월.
- 같은 숫자가 인용문 여러 곳에 나오면(「19세 이상 39세 이하」, 다른 문장의 같은 수) 숫자마다 자기 뒤의 말만 봅니다.
  방향 말이 붙은 곳이 **모두** 연산자와 다를 때만 OPERATOR_MISMATCH로 남깁니다. 한 곳이라도 맞으면 넘어갑니다.
- 방향 말이 없으면(표 칸의 「70%」, 「19~39세」) 판단하지 않습니다.
- 방향 말 뒤에 부정·제외 말이 붙은 곳(「19세 미만은 신청 불가」「70%를 초과하지 않는」)은 뜻이 뒤집히므로 판단하지 않습니다.
- NOT 아래 조건은 방향이 뒤집히므로 보지 않습니다. 같음·포함·참거짓(EQ·NE·IN·NOT_IN·EXISTS) 조건도 보지 않습니다.
- 대상: 자격 조건식과 예외의 적용 조건(when)·바뀐 조건식(effectExpression). 위치는 자격 항목(/eligibility/<번호>)으로 남깁니다.
"""

from __future__ import annotations

import re
from typing import Any

from mujuthaek_extraction.verify.claims import NUMBER, TABLE_SCALES, _atoms, _clean
from mujuthaek_extraction.verify.exceptions import _values as amounts_in
from mujuthaek_extraction.verify.model import Finding

DIRECTIONS = ("LT", "LTE", "GT", "GTE")
WORDS = {"이하": "LTE", "이내": "LTE", "까지": "LTE", "미만": "LT", "미달": "LT", "이상": "GTE", "부터": "GTE", "초과": "GT", "넘": "GT"}
# 숫자+단위 바로 뒤의 방향 말. 「넘」만 조사(을·를·이·가)를 사이에 둘 수 있습니다(「70%를 넘는」「39세가 넘으면」)
DIRECTION = re.compile(r"\s*(?:(이하|이내|까지|미만|미달|이상|부터|초과)|[을를이가]?\s*(넘)(?!지))")
# 방향 말 뒤 같은 마디(쉼표·마침표 전, 15자 안)에 부정·제외 말이 있으면 뜻이 뒤집혀 판단하지 않습니다
NEGATED = re.compile(r"[^.,;\n]{0,15}?(?:않|아니|아닌|제외|불가|없|못|탈락|부적격|배제|금지)")
UNITS = {
    "YEAR": r"(?:세|살|년)",
    "PERCENT": r"(?:%|％|퍼센트)",
    "COUNT": r"(?:명|인|자녀|가구|세대|개|회|호|채|건|곳|번)",
}
MONTH_UNITS = ((re.compile(r"\s*(?:개월|달)"), 1), (re.compile(r"\s*년"), 12))
TABLE_MIN = 1_000  # 단위 없는 표 칸 금액(「345,000」(단위: 천원))은 이보다 큰 수만 읽습니다(「3 이상」 같은 작은 수와 섞이지 않게)


def _occurrences(text: str, unit: str) -> list[tuple[set[float], int]]:
    """(그 자리에서 읽을 수 있는 값들, 숫자+단위가 끝나는 위치). text는 _clean을 거친 문자열."""
    out: list[tuple[set[float], int]] = []
    if unit == "KRW":
        out += [({value}, pos + len(raw)) for pos, value, raw in amounts_in(text, "KRW")]
    for m in NUMBER.finditer(text):
        try:
            number = float(m[0].replace(",", ""))
        except ValueError:
            continue
        if unit == "KRW":
            if number >= TABLE_MIN:  # 「원」이 붙은 금액은 위에서 읽었습니다. 여기서는 단위 없는 표 칸만
                out.append(({number * scale for scale in TABLE_SCALES}, m.end()))
        elif unit == "MONTH":
            out += [({number * factor}, u.end()) for pattern, factor in MONTH_UNITS if (u := pattern.match(text, m.end()))]
        elif unit in UNITS and (u := re.compile(r"\s*" + UNITS[unit]).match(text, m.end())):
            out.append(({number}, u.end()))
    return out


def _directions(texts: list[str], value: float, unit: str) -> list[str]:
    """인용문에서 value가 나오는 곳마다 바로 뒤에 붙은 방향(LT·LTE·GT·GTE). 방향 말이 없거나 부정된 곳은 뺍니다."""
    found = []
    tolerance = 0.5 if unit == "KRW" else 0.005
    for raw in texts:
        text = _clean(raw)
        for values, end in _occurrences(text, unit):
            if not any(abs(v - value) < tolerance for v in values):
                continue
            word = DIRECTION.match(text, end)
            if word and not NEGATED.match(text, word.end()):
                found.append(WORDS[word[1] or word[2]])
    return found


def _expected(atom: dict[str, Any]) -> list[tuple[float, set[str]]]:
    """(값, 맞는 방향들). 방향을 볼 수 없는 조건이면 빈 목록."""
    operator, value = atom.get("operator"), atom.get("value")
    numeric = isinstance(value, int | float) and not isinstance(value, bool)
    if operator in DIRECTIONS and numeric:
        return [(float(value), {operator})]
    if operator == "BETWEEN" and isinstance(value, list) and len(value) == 2 and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value):
        return [(float(value[0]), {"GTE", "GT"}), (float(value[1]), {"LTE", "LT"})]
    return []


def check_directions(candidate: dict[str, Any]) -> list[Finding]:
    """자격 조건의 비교 연산자가 인용문의 방향 말(이상·이하·미만·초과 등)과 반대인 조건마다 OPERATOR_MISMATCH를 돌려줍니다."""
    quotes = {e["id"]: e["quote"] for e in candidate["evidence"]}
    findings: list[Finding] = []

    def texts(*id_lists: list[str] | None) -> list[str]:
        return [quotes[i] for ids in id_lists if ids for i in ids if i in quotes]

    for e, item in enumerate(candidate["eligibility"]):
        expressions = [(item["rule"]["expression"], f"/eligibility/{e}/rule/expression", item["evidenceIds"])]
        for x, exception in enumerate(item.get("exceptions") or []):
            base = f"/eligibility/{e}/exceptions/{x}"
            expressions.append(((exception.get("when") or {}).get("expression"), f"{base}/when/expression", exception.get("evidenceIds")))
            expressions.append((exception.get("effectExpression"), f"{base}/effectExpression", exception.get("evidenceIds")))
        for expression, root, evidence_ids in expressions:
            for path, atom in _atoms(expression, root):
                unit = atom.get("unit")
                if unit not in ("YEAR", "KRW", "PERCENT", "MONTH", "COUNT"):
                    continue
                cited = texts(atom.get("evidenceIds"), evidence_ids, item["evidenceIds"])
                for value, allowed in _expected(atom):
                    seen = _directions(cited, value, unit)
                    if seen and not set(seen) & allowed:
                        shown = ", ".join(sorted(set(seen)))
                        findings.append(
                            Finding(
                                "V9",
                                "OPERATOR_MISMATCH",
                                f"/eligibility/{e}",
                                f"{path}: {atom.get('attribute', '값')} {atom['operator']} {value:g}이지만 인용문에서 그 값 뒤의 방향 말은 {shown}입니다",
                            )
                        )
                        break
    return findings
