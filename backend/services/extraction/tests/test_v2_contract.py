"""V2 작업 항목 → V1 AI 조각: 빠진 칸 채우기, 형식 오류 「위치: 이유」, 근거 id → 원문 인용. 유료 호출 없음."""

import copy

import pytest
from helpers import ai_part, example, source_for
from test_v2_document import TEXT

from mujuthaek_extraction.rules.base import document_ids
from mujuthaek_extraction.v2.contract import (
    EXPRESSION_HINT,
    LIST_SECTIONS,
    EvidenceError,
    complete,
    errors,
    fill_original_text,
    located_text,
    quote_text,
    to_part,
)
from mujuthaek_extraction.v2.document import parse

SECTIONS = ("notice", *LIST_SECTIONS)


def sparse(value):
    """에이전트가 넘길 모양: null 칸과 빈 목록, 인용 ref(quoteRefs, 모든 깊이)를 뺌."""
    if isinstance(value, dict):
        return {k: sparse(v) for k, v in value.items() if v is not None and v != [] and k != "quoteRefs"}
    if isinstance(value, list):
        return [sparse(v) for v in value]
    return value


def drop_refs(value):
    if isinstance(value, dict):
        return {k: drop_refs(v) for k, v in value.items() if k != "quoteRefs"}
    if isinstance(value, list):
        return [drop_refs(v) for v in value]
    return value


def test_quote_comes_from_the_id_or_a_part_of_it():
    doc = parse(TEXT)
    assert quote_text(doc, "p1.3") == "■ 소득 : 150% 이하"
    assert quote_text(doc, {"id": "t1-1.r0", "part": "14,202,000"}) == "14,202,000"
    with pytest.raises(EvidenceError):
        quote_text(doc, "p9.9")
    with pytest.raises(EvidenceError):
        quote_text(doc, {"id": "p1.3", "part": "200%"})
    # 합쳐진 빈 칸은 근거가 아님: 빈 인용이 되면 결합기가 그 담당 응답 전체를 버림(2026-11-06 선정 규칙 21개 → 0개)
    with pytest.raises(EvidenceError, match="빈 칸"):
        quote_text(doc, "t1-1.r1.c2")


def test_original_text_is_filled_from_the_first_evidence_and_never_rewritten():
    doc = parse(TEXT)
    row = fill_original_text("selectionRules", {"id": "s", "evidence": ["t1-1.r0", "p1.3"]}, doc)
    assert row["originalText"] == "기준 14,202,000 105,200" and doc.contains(row["originalText"])  # 표 행은 칸 글자를 이음
    line = fill_original_text("eligibility", {"id": "e", "evidence": [{"id": "p1.3", "part": "150% 이하"}]}, doc)
    assert line["originalText"] == "150% 이하"
    written = {"id": "e", "originalText": "소득 150% 이하", "evidence": ["p1.3"]}
    assert fill_original_text("eligibility", written, doc) is written  # 적은 것은 그대로(원문 그대로인지는 넣기 검사가 봄)
    assert "originalText" not in fill_original_text("schedules", {"id": "a", "evidence": ["p1.3"]}, doc)  # 그 칸이 없는 섹션
    assert "originalText" not in fill_original_text("eligibility", {"id": "e", "evidence": ["p9.9"]}, doc)  # 근거 오류는 넣기 검사가


def test_original_text_shortened_with_an_ellipsis_becomes_the_source_span():
    # 2026-11-07 유료 확인 jbdc-16011: 담당이 originalText를 「...」로 가운데를 줄여 적어 원문에 없다고 거절됨 → 고치는 데 차례를 씀
    line = "신청자의 가구원수가 1인인 경우 20%p, 2인인 경우 10%p를 추가 완화된 기준으로 적용"
    doc = parse("\n".join(["--- 1쪽 ---", line, "다른 줄 20%p 기준"]))

    def written(original):
        return fill_original_text("eligibility", {"id": "e", "originalText": original, "evidence": ["p1.1"]}, doc)["originalText"]

    assert written("신청자의 가구원수가 1인인 경우 20%p ... 추가 완화된 기준으로 적용") == line
    assert written("신청자의 가구원수가 1인인 경우 20%p…") == "신청자의 가구원수가 1인인 경우 20%p"  # 뒤만 줄였으면 남은 조각
    assert written("20%p ... 기준") == "20%p ... 기준"  # 두 줄에서 다른 글이 되면 정할 수 없어 그대로(넣기 검사가 거절)
    assert written("10%p ... 1인인") == "10%p ... 1인인"  # 조각 차례가 원문과 다르면 그대로


def test_missing_nullable_fields_and_lists_are_filled_back_exactly_for_every_section():
    data = example("housing")
    part = ai_part(data)
    documents = tuple(document_ids(source_for("housing", data).material))
    for section in SECTIONS:
        items = [part[section]] if section == "notice" else part[section]
        for item in items:
            original = {k: v for k, v in item.items() if k != "quoteRefs"}
            filled = complete(section, sparse(original), documents)
            assert drop_refs(filled) == drop_refs(original), section  # quoteRefs는 to_part가 붙임(하위 항목은 위 근거를 이어받음)
            assert errors(section, {**original, "quoteRefs": []}, documents) == [], section


def test_wrong_fields_are_reported_as_location_and_reason():
    data = example("housing")
    documents = tuple(document_ids(source_for("housing", data).material))
    schedule = copy.deepcopy(ai_part(data)["schedules"][0])
    schedule["startsAt"] = 123
    found = errors("schedules", schedule, documents)
    assert found and found[0].startswith("/startsAt: ")


def test_missing_and_misplaced_fields_and_condition_kinds_are_told_how_to_fix():
    # 2026-11-09 저장 기록 401개 담당이 받은 영어 원문 오류: 필수 칸 없음 65번, 칸 위치 틀림 40여 번, 조건 하나(ATOMIC)에 children 12번.
    # 유료 확인 jbdc-16011 자격 담당은 「{'kind': 'ATOMIC', 'children': …」로 시작해 240자에서 잘린 오류를 두 번 받고 그 항목을 뺌
    data = example("housing")
    documents = tuple(document_ids(source_for("housing", data).material))
    base = ai_part(data)["eligibility"][2]
    expression = base["rule"]["expression"]

    def found(change):
        item = copy.deepcopy(base)
        change(item)
        return errors("eligibility", item, documents)

    joined = found(lambda item: item["rule"].update(expression={"kind": "ATOMIC", "children": [expression, expression]}))
    assert joined == [f"/rule/expression: {EXPRESSION_HINT}"]  # 칸 형식과 조건부 규칙이 같은 안내를 두 번 주지 않음
    assert found(lambda item: item["rule"].update(expression={**expression, "kind": "ALL"})) == joined
    moved = found(lambda item: item["rule"].update(exceptionsStatus=item.pop("exceptionsStatus")))
    assert "/rule: 이 자리에 없는 칸입니다: exceptionsStatus(항목 바로 아래에 적음)" in moved and "/: 'exceptionsStatus' 칸이 필요합니다" in moved
    assert found(lambda item: item.update(reason="글로 남김")) == ["/: 이 자리에 없는 칸입니다: reason(rule 안에 적음)"]
    assert found(lambda item: item["exceptions"][0].pop("originalText")) == [
        "/exceptions/0: 'originalText' 칸이 필요합니다(이 예외에 evidence를 붙이면 비워 둬도 그 근거의 원문으로 채움)"
    ]
    assert found(lambda item: item["scope"].update(supplyGroups=["a"])) == ["/scope: 이 자리에 없는 칸입니다: supplyGroups(형식에 없는 칸이라 적지 않음)"]
    # 예외가 없다고 한 항목에 넣은 예외(2026-11-09 유료 확인 jbdc-16011·23건 측정 gh-808): 목록 값 전체 대신 비우거나 조건 칸을 바꾸라고
    assert found(lambda item: item.update(exceptionsStatus="NONE_IN_SOURCE")) == [
        "/exceptions: exceptionsStatus가 NONE_IN_SOURCE·NOT_REVIEWED 중 하나이면 이 목록은 비워야 합니다(지금 1개): "
        "넣은 것이 맞으면 exceptionsStatus를 바꿉니다"
    ]


def test_quotes_handed_to_the_assembler_are_widened_until_they_occur_once_in_the_source():
    # V1 결합기는 인용 글을 원문에서 다시 찾아 위치를 정함: 짧거나 여러 곳에 있는 칸 글자는 그 행으로, 일부 글자는 그 줄로 넓힘
    lines = ["--- 1쪽 ---", "배점은 아래 표와 같다", "[표 1-1]", "| 소득 50% 이하 | 50점 |", "| 자산 1억 이하 | 50점 |", "합계 100점, 50점 만점 항목 둘"]
    doc = parse("\n".join(lines))
    assert located_text(doc, "t1-1.r0.c1") == "| 소득 50% 이하 | 50점 |"  # 「50점」은 원문 3곳 + 너무 짧음
    assert located_text(doc, "t1-1.r0.c0") == "소득 50% 이하"  # 한 곳뿐이고 충분히 길면 그대로
    assert located_text(doc, {"id": "p1.2", "part": "50점"}) == "합계 100점, 50점 만점 항목 둘"  # 일부 글자도 그 줄로
    assert located_text(doc, {"id": "p1.2", "part": "100점"}) == "100점"
    assert located_text(doc, "p1.1") == "배점은 아래 표와 같다"
    built = to_part("selectionRules", [{"id": "s", "kind": "SCORING", "evidence": ["t1-1.r0.c0", "t1-1.r0.c1"]}], doc, ("text",))
    assert [q["text"] for q in built["quotes"]] == ["소득 50% 이하", "| 소득 50% 이하 | 50점 |"]
    # 칸 글자가 V1이 표 행 아래 붙인 읽기 도움 줄(↳)에도 있으면 결합기는 두 곳을 찾으므로 그 행으로 넓힘
    # (2026-11-06 5건 재측정 sh-310672: 입주가능일 칸만 근거로 단 일정이 「위치를 정하지 못함」으로 빠짐)
    aided = parse("\n".join(["--- 1쪽 ---", "[표 1-1]", "| 505 호 | 2026년 11월 27일 부터 |", "  ↳ 2026년 11월 27일 부터 — 공실호수 505 호"]))
    assert located_text(aided, "t1-1.r0.c1") == "| 505 호 | 2026년 11월 27일 부터 |"


def test_a_row_that_repeats_in_the_source_gets_a_unique_neighbor_row_to_place_it():
    # 2026-11-10 23건 유료 확인 jbdc-16011: 공고 수량의 근거 합계 행이 원문 두 표에 똑같이 있어 결합기가 그 수량을 빼고 공고 전체가 사람 확인으로 감.
    # 같은 표에서 한 곳뿐인 행(위 행부터)을 함께 붙이면 결합기가 그 근처를 고름(구조 단계만, anchors=True)
    lines = ["--- 1쪽 ---", "[표 1-1]", "| 기관추천 | 국가유공자 | 30 |", "| 합 계 | | 30 |", "[표 1-2]", "| 다자녀 | 신혼부부 | 30 |", "| 합 계 | | 30 |"]
    doc = parse("\n".join(lines))
    count = {"kind": "OFFERED", "value": 30, "evidence": ["t1-2.r1"]}
    notice = {"title": "공고", "counts": [count], "evidence": ["t1-2.r0"]}
    plain = to_part("notice", [notice], doc, ("text",))
    anchored = to_part("notice", [notice], doc, ("text",), anchors=True)
    assert [q["text"] for q in plain["quotes"]] == ["| 다자녀 | 신혼부부 | 30 |", "| 합 계 | | 30 |"]
    refs = {q["ref"]: q["text"] for q in anchored["quotes"]}
    assert [refs[r] for r in anchored["notice"]["counts"][0]["quoteRefs"]] == ["| 합 계 | | 30 |", "| 다자녀 | 신혼부부 | 30 |"]
    assert doc.neighbors("t1-2.r1") == ["| 다자녀 | 신혼부부 | 30 |"] and doc.neighbors("p9.9") == []


def test_items_with_evidence_ids_become_the_same_v1_part():
    data = example("housing")
    source = source_for("housing", data)
    doc = parse(source.material.text)
    part = ai_part(data)
    documents = tuple(document_ids(source_for("housing", data).material))
    texts = {q["ref"]: q["text"] for q in part["quotes"]}

    def evidence(refs):
        found = []
        for ref in refs:
            hit = next(h for h in doc.search(texts[ref]) if texts[ref] in h["text"])
            found.append(hit["id"] if hit["text"] == texts[ref] else {"id": hit["id"], "part": texts[ref]})
        return found

    for section in ("schedules", "eligibility", "requiredDocuments"):
        items = [{**sparse({k: v for k, v in item.items() if k != "quoteRefs"}), "evidence": evidence(item["quoteRefs"])} for item in part[section]]
        built = to_part(section, items, doc, documents)
        assert {q["text"] for q in built["quotes"]} == {texts[r] for item in part[section] for r in item["quoteRefs"]}
        quote = {q["ref"]: q["text"] for q in built["quotes"]}
        rebuilt = [{**drop_refs(item), "quoteRefs": [quote[r] for r in item["quoteRefs"]]} for item in built[section]]
        expected = [{**drop_refs(item), "quoteRefs": [texts[r] for r in item["quoteRefs"]]} for item in part[section]]
        assert rebuilt == expected, section


def test_inner_ids_that_collide_get_their_item_id_in_front():
    # 청년·고령자 소득 조건의 자녀 가산 예외에 같은 id → 계약 DUPLICATE_ID로 한쪽 조건이 격리됨(2026-11-06).
    # 겹치는 하위 id만 앞에 항목 id를 붙임
    doc = parse(TEXT)
    child = {"id": "child-uplift", "evidence": ["p1.3"]}
    items = [
        {"id": "youth", "exceptions": [dict(child)], "evidence": ["p1.3"]},
        {"id": "elderly", "exceptions": [dict(child), {"id": "youth"}], "evidence": ["p1.3"]},
    ]
    built = to_part("eligibility", items, doc, ("text",))["eligibility"]
    assert [e["id"] for e in built[0]["exceptions"]] == ["child-uplift"]
    assert [e["id"] for e in built[1]["exceptions"]] == ["elderly.child-uplift", "elderly.youth"]
