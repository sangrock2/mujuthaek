"""그림 표 판독: 글자 없는 큰 그림이 있는 쪽만 그림으로 보내고, 옮긴 글자를 원문 끝에 붙입니다(2026-10-16 시험 후 추가)."""

import hashlib
import json

import pytest

import mujuthaek_extraction.image_reading as image_reading
from mujuthaek_extraction.intake.model import ExtractionMaterial, MaterialFile, TrustedContext
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.verify.consistency import _check_disputed_reading, check_consistency
from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.verifier import NOTE_CODES, is_note

TABLE = "| 호실 | 전용면적 | 보증금 | 월임대료 |\n| 202호 | 26.71 | 12,744,000 | 166,100 |"


@pytest.fixture
def pictured(monkeypatch):
    monkeypatch.setattr(image_reading, "image_pages", lambda data: ((1, 0.32),) if data == b"pdf" else ())
    monkeypatch.setattr(image_reading, "_render", lambda data, page: b"png")
    monkeypatch.setattr(image_reading, "_render_tiles", lambda data, page: [b"png-top", b"png-bottom"])
    material = ExtractionMaterial("--- 1쪽 ---\n m 임대조건", "pdf-text", (), None, (MaterialFile("file-1", "공고.pdf", b"pdf", "pdf"),))
    context = TrustedContext({}, (), ({"id": "pdf-text", "kind": "TEXT", "name": "첨부 PDF에서 읽은 글자", "sha256": "old"},), "SKIPPED_NO_API_REFERENCE", None)
    return material, context


def answer(text):
    return json.dumps({"pages": [{"image": 1, "text": text}]}, ensure_ascii=False)


def reads(first, second=None):
    """판독 두 번(image_text, 같은 그림을 다시 읽는 image_text_check). second가 없으면 같은 글자."""
    return RecordedModel({"image_text": [answer(first)], "image_text_check": [answer(first if second is None else second)]})


def test_transcribed_table_is_appended_and_document_hash_follows(pictured):
    material, context = pictured
    model = reads(TABLE)
    new_material, new_context, run = image_reading.read_image_tables(material, context, model)
    assert new_material.text.startswith(material.text) and "=== 그림 판독 공고.pdf 1쪽" in new_material.text and "12,744,000" in new_material.text
    assert new_context.documents[0]["sha256"] == hashlib.sha256(new_material.text.encode("utf-8")).hexdigest()
    request, check = model.requests
    assert check.call_name == "image_text_check" and "불일치" not in new_material.text  # 두 판독이 같으면 불일치 묶음 없음
    assert request.call_name == "image_text" and [i.label for i in request.images] == ["그림 1"] and "공고.pdf 1쪽" in request.user
    assert run.failed_calls == [] and context.documents[0]["sha256"] == "old"  # 입력은 바꾸지 않습니다


def test_transcribed_rows_get_the_pdf_table_line_shape(pictured):
    # 2026-11-05 sh-311087: 판독기가 「a | b」로 적은 행은 표 행(「| …」)으로 보지 않아 공급표 후보·가격 행 누락 검사가 모두 놓쳤습니다
    material, context = pictured
    plain = "임대조건\n호실 | 전용면적 | 보증금\n202호 | 26.71 | 12,744,000"
    new_material, _, _ = image_reading.read_image_tables(material, context, reads(plain))
    assert new_material.text.endswith("임대조건\n| 호실 | 전용면적 | 보증금 |\n| 202호 | 26.71 | 12,744,000 |")
    assert image_reading.bordered(TABLE) == TABLE  # 이미 표 모양인 줄은 그대로


def test_reader_failure_or_empty_picture_leaves_material_as_is(pictured):
    material, context = pictured
    down = RecordedModel({"image_text": [ModelError("timeout", transient=True)]})
    same, same_context, run = image_reading.read_image_tables(material, context, down)
    assert same is material and same_context is context and run.failed_calls
    blank = reads("   ")  # 지도·사진처럼 옮길 글자가 없는 그림
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
    model = reads("신청자 | 한지붕 | 123123-1221005\n" + TABLE)
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


def test_rows_read_differently_twice_are_listed_and_their_values_go_to_review(pictured):
    # 2026-11-05: 같은 가격표 그림을 실행마다 250,600·250,500으로 읽어 틀린 월임대료가 자동 게시됨. 두 번 읽어 다른 줄의 값은 사람 확인
    from mujuthaek_extraction import supply_tables

    material, context = pictured
    new_material, _, run = image_reading.read_image_tables(material, context, reads(TABLE, TABLE.replace("166,100", "166,700")))
    row = "| 202호 | 26.71 | 12,744,000 | 166,100 |"
    assert f"불일치 줄: {row.replace('|', '¦')}" in new_material.text and run.failed_calls == []
    assert supply_tables.image_tables(new_material)[0].rows == (("202호", "26.71", "12,744,000", "166,100"),)  # 불일치 묶음은 표 후보가 아님
    text = new_material.text
    start = text.index(row)
    evidence = [{"id": "e1", "sourceId": "pdf-text", "locator": {"kind": "TEXT_RANGE", "start": start, "end": start + len(row)}, "quote": row}]
    candidate = {"evidence": evidence, "supplyGroups": [{"prices": [{"evidenceIds": ["e1"]}], "counts": [], "evidenceIds": []}]}
    found = []
    _check_disputed_reading(candidate, SourceBundle(texts={"pdf-text": text}, pdfs={}), {"e1"}, lambda *args: found.append(args[:3]))
    assert found == [("V8", "IMAGE_READING_DISAGREES", "/supplyGroups/0/prices")]  # 그 묶음의 가격만 보류
    assert "IMAGE_READING_DISAGREES" not in NOTE_CODES  # 표시만이 아니라 사람 확인


def test_failed_second_reading_disputes_every_line(pictured):
    material, context = pictured
    model = RecordedModel({"image_text": [answer(TABLE)], "image_text_check": [ModelError("timeout", transient=True)]})
    new_material, _, run = image_reading.read_image_tables(material, context, model)
    assert new_material.text.count("불일치 줄: ") == len(TABLE.split("\n")) and run.failed_calls[0][0] == "image_text_check"


def test_second_reading_uses_larger_tiles_and_joins_them_back(pictured):
    # 2026-11-05: 같은 그림을 같은 크기로 두 번 읽으면 같은 글자를 같게 잘못 읽음(두 판독 모두 250,600 → 250,500). 다시 읽기는 크게 그린 위·아래 조각
    material, context = pictured
    top, bottom = "| 호실 | 전용면적 | 보증금 | 월임대료 |", "| 202호 | 26.71 | 12,744,000 | 166,100 |"
    pages = json.dumps({"pages": [{"image": 1, "text": top}, {"image": 2, "text": bottom}]}, ensure_ascii=False)
    model = RecordedModel({"image_text": [answer(TABLE)], "image_text_check": [pages]})
    new_material, _, _ = image_reading.read_image_tables(material, context, model)
    check = model.requests[1]
    assert [i.data for i in check.images] == [b"png-top", b"png-bottom"] and "위 부분" in check.user and "아래 부분" in check.user
    assert "불일치" not in new_material.text  # 두 조각을 이어 붙이면 처음 판독과 같음
