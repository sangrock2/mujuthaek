"""큰 자격 기준표 나누기(v2/criteria.py)와 맡은 행만 세는 기준표 행 누락 검사. 유료 호출 없음."""

from mujuthaek_extraction.v2 import criteria
from mujuthaek_extraction.v2.criteria import criteria_chunks
from mujuthaek_extraction.v2.document import parse
from mujuthaek_extraction.verify.consistency import missed_criteria_rows

GROUPS = ("일반공급", "다자녀가구 특별공급", "노부모부양 특별공급", "신혼부부 특별공급", "신생아 특별공급")
METHODS = (("우선공급", 100, 140), ("추첨공급", 120, 200))


def criteria_text(groups=GROUPS, methods=METHODS):
    """공급유형×공급방식×외벌이·맞벌이 소득표(jbdc-16011 모양, 대상·방식 칸은 병합이라 맞벌이 행 줄이 대상마다 똑같음)와
    임대조건 표·작은 기준표. methods는 모든 대상에 같은 방식들이거나 {대상: 방식들}."""
    rows = []
    for group in groups:
        for m, (method, single, double) in enumerate(methods[group] if isinstance(methods, dict) else methods):
            rows.append(f"| {group if m == 0 else ''} | {method} | 외벌이 | 월평균소득 {single}% 이하 |")
            rows.append(f"|  |  | 맞벌이 | 월평균소득 {double}% 이하 |")
    return "\n".join(
        [
            "--- 1쪽 ---",
            "가. 공급유형별 소득 기준",
            "[표 1-1]",
            "  [열 제목] 1. 공급유형 | 2. 공급방식 | 3. 구분 | 4. 소득기준",
            *rows,
            "",
            "나. 임대조건",
            "[표 1-2]",
            "  [열 제목] 1. 주택형 | 2. 임대보증금 | 3. 월임대료",
            *[f"| {n}A | {n},000,000원 | {n}0,000원 |" for n in range(10, 24)],
            "",
            "다. 계층별 소득 기준",
            "[표 1-3]",
            "  [열 제목] 1. 구분 | 2. 소득기준",
            "| 청년 | 월평균소득 100% 이하 |",
            "| 고령자 | 월평균소득 120% 이하 |",
        ]
    )


def condition(group, value, exceptions=()):
    def atom(v):
        return {"kind": "ATOMIC", "subject": "HOUSEHOLD", "attribute": "INCOME_BENCHMARK_PERCENT", "operator": "LTE", "value": v, "unit": "PERCENT"}

    return {
        "id": group,
        "scope": {"targetGroups": [group]},
        "rule": {"status": "STRUCTURED", "expression": atom(value)},
        "exceptions": [{"when": {"status": "UNSTRUCTURED"}, "effectExpression": atom(v)} for v in exceptions],
        "originalText": "",
    }


def test_big_criteria_tables_are_split_where_the_row_target_changes():
    # 2026-11-10 유료 확인 jbdc-16011: 32행 소득표를 자격 담당 혼자 넣으며 회차마다 27값·15값만 넣음. 기준 행 12개 이상·대상 2개 이상인 표만
    # 나누고(임대조건 표·작은 기준표는 그대로 자격 담당), 대상이 바뀌는 곳에서 16행 이하로 끊음
    document = parse(criteria_text())
    chunks = criteria_chunks(document)
    assert [(c.table, c.label, len(c.rows)) for c in chunks] == [("t1-1", "t1-1 행 r0~r15", 16), ("t1-1", "t1-1 행 r16~r19", 4)]
    assert chunks[0].groups == GROUPS[:4] and chunks[1].groups == GROUPS[4:]
    source = document.source.split("\n")
    assert [source[spot] for spot in chunks[1].spots] == [document.text(f"t1-1.r{r}") for r in range(16, 20)]  # 검증기가 세는 원문 줄

    # 대상 하나가 16행을 넘으면 그 대상을 고르게 나누되(18행 → 8 + 10) 한 공급방식의 외벌이·맞벌이 행(위 칸이 병합된 이어진 행)은 떼지 않고,
    # 남은 조각은 다음 대상과 묶음
    many = {"일반공급": tuple((f"{n}단계", 100 + n, 140 + n) for n in range(9)), "신생아 특별공급": METHODS}
    document = parse(criteria_text(groups=("일반공급", "신생아 특별공급"), methods=many))
    chunks = criteria_chunks(document)
    assert [(len(c.rows), c.groups) for c in chunks] == [(8, ("일반공급",)), (14, ("일반공급", "신생아 특별공급"))]
    assert all("외벌이" in document.text(f"t1-1.r{c.rows[0]}") and "맞벌이" in document.text(f"t1-1.r{c.rows[-1]}") for c in chunks)

    # 행이 적은 표는 나누지 않음
    assert criteria_chunks(parse(criteria_text(groups=GROUPS[:2]))) == []
    assert criteria.BIG_TABLE_ROWS == 12 and criteria.CHUNK_ROWS == 16


def test_a_method_longer_than_a_chunk_is_split_again_inside_and_no_chunk_is_over_the_limit():
    # 2026-11-10 재검토: 1행 방식과 18행 방식이 [1, 18]로 나뉘어 묶음 하나가 16행을 넘었음(출력 한도에 걸릴 수 있음)
    from types import SimpleNamespace

    leads = [0, 0, *([1, 2] * 8), 1]  # 1행 방식, 18행 방식(그 안은 외벌이·맞벌이 두 행씩 + 마지막 1행)
    rows = [SimpleNamespace(lead=lead) for lead in leads]
    pieces = criteria._pieces(list(range(len(rows))), rows)
    assert all(len(piece) <= criteria.CHUNK_ROWS for piece in pieces) and [i for piece in pieces for i in piece] == list(range(len(rows)))
    assert not any(rows[piece[0]].lead == 2 for piece in pieces)  # 맞벌이 행이 앞 행과 떨어지지 않음
    # 단위 크기가 고르지 않아도(15·2·15행) 상한을 넘지 않음
    uneven = [SimpleNamespace(lead=0)] + [SimpleNamespace(lead=1 if i in (0, 15, 17) else 2) for i in range(32)]
    assert all(len(piece) <= criteria.CHUNK_ROWS for piece in criteria._pieces(list(range(len(uneven))), uneven))


def test_missing_rows_can_be_counted_only_among_the_rows_a_helper_was_given():
    # 맞벌이 행 줄(「|  |  | 맞벌이 | 월평균소득 140% 이하 |」)이 대상마다 똑같아 줄 글자가 아니라 줄 번호로 맡은 행을 가림
    document = parse(criteria_text())
    _, newborn = criteria_chunks(document)
    candidate = {"eligibility": [condition("일반공급", 100, exceptions=[140]), condition("신생아 특별공급", 100)], "selectionRules": []}
    missed, _ = missed_criteria_rows(candidate, document.source, frozenset(newborn.spots))
    assert [(gone, group) for _, gone, group in missed] == [(["140%"], "신생아특별공급"), (["120%"], "신생아특별공급"), (["200%"], "신생아특별공급")]
    everything, lacking = missed_criteria_rows(candidate, document.source)
    # 맡은 행을 주지 않으면 지금 검사와 같음: 작은 기준표(고령자 120%)까지 모든 기준표의 행
    assert len(everything) == 2 + 4 * 3 + 3 + 1 and set(lacking.values()) == set(GROUPS[1:4])
