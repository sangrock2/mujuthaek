"""그림 표 판독: 글자 없는 큰 그림이 있는 쪽만 그림으로 보내고, 옮긴 글자를 원문 끝에 붙입니다(2026-10-16 시험 후 추가)."""

import hashlib
import json

import pytest

import mujuthaek_extraction.image_reading as image_reading
from mujuthaek_extraction.intake.model import ExtractionMaterial, MaterialFile, TrustedContext
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.verify.consistency import check_consistency
from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.verifier import is_note

TABLE = "| 호실 | 전용면적 | 보증금 | 월임대료 |\n| 202호 | 26.71 | 12,744,000 | 166,100 |"


@pytest.fixture
def pictured(monkeypatch):
    monkeypatch.setattr(image_reading, "image_pages", lambda data: ((1, 0.32),) if data == b"pdf" else ())
    monkeypatch.setattr(image_reading, "_render", lambda data, page: b"png")
    material = ExtractionMaterial("--- 1쪽 ---\n m 임대조건", "pdf-text", (), None, (MaterialFile("file-1", "공고.pdf", b"pdf", "pdf"),))
    context = TrustedContext({}, (), ({"id": "pdf-text", "kind": "TEXT", "name": "첨부 PDF에서 읽은 글자", "sha256": "old"},), "SKIPPED_NO_API_REFERENCE", None)
    return material, context


def answer(text):
    return json.dumps({"pages": [{"image": 1, "text": text}]}, ensure_ascii=False)


def test_transcribed_table_is_appended_and_document_hash_follows(pictured):
    material, context = pictured
    model = RecordedModel({"image_text": [answer(TABLE)]})
    new_material, new_context, run = image_reading.read_image_tables(material, context, model)
    assert new_material.text.startswith(material.text) and "=== 그림 판독 공고.pdf 1쪽" in new_material.text and "12,744,000" in new_material.text
    assert new_context.documents[0]["sha256"] == hashlib.sha256(new_material.text.encode("utf-8")).hexdigest()
    [request] = model.requests
    assert request.call_name == "image_text" and [i.label for i in request.images] == ["그림 1"] and "공고.pdf 1쪽" in request.user
    assert run.failed_calls == [] and context.documents[0]["sha256"] == "old"  # 입력은 바꾸지 않습니다


def test_transcribed_rows_get_the_pdf_table_line_shape(pictured):
    # 2026-11-05 sh-311087: 판독기가 「a | b」로 적은 행은 표 행(「| …」)으로 보지 않아 공급표 후보·가격 행 누락 검사가 모두 놓쳤습니다
    material, context = pictured
    plain = "임대조건\n호실 | 전용면적 | 보증금\n202호 | 26.71 | 12,744,000"
    new_material, _, _ = image_reading.read_image_tables(material, context, RecordedModel({"image_text": [answer(plain)]}))
    assert new_material.text.endswith("임대조건\n| 호실 | 전용면적 | 보증금 |\n| 202호 | 26.71 | 12,744,000 |")
    assert image_reading.bordered(TABLE) == TABLE  # 이미 표 모양인 줄은 그대로


def test_reader_failure_or_empty_picture_leaves_material_as_is(pictured):
    material, context = pictured
    down = RecordedModel({"image_text": [ModelError("timeout", transient=True)]})
    same, same_context, run = image_reading.read_image_tables(material, context, down)
    assert same is material and same_context is context and run.failed_calls
    blank = RecordedModel({"image_text": [answer("   ")]})  # 지도·사진처럼 옮길 글자가 없는 그림
    assert image_reading.read_image_tables(material, context, blank)[0] is material


def test_notice_without_pictures_makes_no_call():
    material = ExtractionMaterial("원문", "pdf-text", (), None, (MaterialFile("file-1", "공고.pdf", b"%PDF-1.4 not really", "pdf"),))
    context = TrustedContext({}, (), (), "SKIPPED_NO_API_REFERENCE", None)
    model = RecordedModel({})
    assert image_reading.read_image_tables(material, context, model) == (material, context, None) and model.requests == []


def test_values_quoted_from_transcription_are_flagged():
    text = "--- 1쪽 ---\n소득 기준은 아래 표\n=== 그림 판독 공고.pdf 1쪽 (AI가 그림 속 글자를 옮김) ===\n" + TABLE + "\n월평균소득 70% 이하"
    row, income = "| 202호 | 26.71 | 12,744,000 | 166,100 |", "월평균소득 70% 이하"

    def ev(id_, quote):
        return {
            "id": id_,
            "sourceId": "pdf-text",
            "locator": {"kind": "TEXT_RANGE", "start": text.index(quote), "end": text.index(quote) + len(quote)},
            "quote": quote,
        }

    group = {"exclusiveAreaSqm": 26.71, "prices": [], "counts": [], "scope": {"targetGroups": []}, "evidenceIds": ["ev-row"]}
    candidate = {
        "evidence": [ev("ev-row", row), ev("ev-income", income)],
        "notice": {"counts": [], "evidenceIds": []},
        "locations": [],
        "supplyGroups": [group],
        "schedules": [],
        "eligibility": [
            {"category": "INCOME", "rule": {"status": "STRUCTURED", "expression": None}, "scope": {"targetGroups": []}, "evidenceIds": ["ev-income"]}
        ],
        "selectionRules": [],
        "requiredDocuments": [],
        "quality": {"coverage": {s: {"status": "EXTRACTED"} for s in ("eligibility", "requiredDocuments", "schedules")}, "missingFields": []},
    }
    found = {(f.code, f.target): f for f in check_consistency(candidate, SourceBundle(texts={"pdf-text": text}, pdfs={"file-1": b"pdf"}))}
    assert not is_note(found[("EVIDENCE_FROM_IMAGE", "/eligibility/0")].issue())  # 판정에 쓰는 조건은 사람 확인
    assert is_note(found[("IMAGE_TRANSCRIBED_VALUES", "/supplyGroups")].issue())  # 공급 값은 표시만
    assert not any(code == "SOURCE_IN_IMAGE_SUSPECTED" for code, _ in found)  # 판독했으면 그림 표 의심은 내지 않음


def test_resident_number_shapes_in_sample_forms_are_masked(pictured):
    # 서식 예시 그림의 견본 주민등록번호도 저장하지 않습니다
    material, context = pictured
    model = RecordedModel({"image_text": [answer("신청자 | 한지붕 | 123123-1221005\n" + TABLE)]})
    new_material, _, _ = image_reading.read_image_tables(material, context, model)
    assert "1221005" not in new_material.text and "******-*******" in new_material.text and "12,744,000" in new_material.text


def test_pdf_is_chosen_by_file_type_not_by_name(monkeypatch):
    # 이름 끝 공백·확장자 없는 PDF도 fileType이 pdf면 그림을 찾고, 이름이 .pdf여도 fileType이 다르면 보지 않습니다 (검토 2026-10-20)
    monkeypatch.setattr(image_reading, "image_pages", lambda data: ((1, 0.32),))
    files = (
        MaterialFile("a", "공고문.pdf ", b"1", "pdf"),
        MaterialFile("b", "공고문", b"2", "pdf"),
        MaterialFile("c", "목록.pdf", b"3", "xlsx"),
    )
    material = ExtractionMaterial("원문", "pdf-text", (), None, files)
    assert [t[0] for t in image_reading.image_targets(material)] == ["a", "b"]
