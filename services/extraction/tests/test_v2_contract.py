"""V2 작업 항목 → V1 AI 조각: 빠진 칸 채우기, 형식 오류 「위치: 이유」, 근거 id → 원문 인용. 유료 호출 없음."""

import copy

import pytest
from helpers import ai_part, example, source_for
from test_v2_document import TEXT

from mujuthaek_extraction.rules.base import document_ids
from mujuthaek_extraction.v2.contract import LIST_SECTIONS, EvidenceError, complete, errors, quote_text, to_part
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
