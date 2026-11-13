"""그림 표 판독: 글자 없는 큰 그림이 있는 쪽만 그림으로 보내고, 옮긴 글자를 원문 끝에 붙입니다(2026-10-16 시험 후 추가)."""

import hashlib
import json
from collections import Counter

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
    monkeypatch.setattr(image_reading, "_render_tiles", lambda data, page: [b"png-top", b"png-middle", b"png-bottom"])
    monkeypatch.setattr(image_reading, "_ocr_numbers", lambda data, page: None)  # OCR 시험은 따로(아래)
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
    assert [i.data for i in check.images] == [b"png-top", b"png-middle", b"png-bottom"]
    assert "위 부분" in check.user and "가운데 부분" in check.user and "아래 부분" in check.user
    assert "불일치" not in new_material.text  # 두 조각을 이어 붙이면 처음 판독과 같음


def test_rows_are_compared_by_cells_so_spacing_or_a_missing_label_is_not_a_dispute():
    from collections import Counter

    first = "| 청년안테나 (상암로81길10) | 201 | 31.69 | 19,240,000 | 250,600 |"
    assert image_reading._agrees(first, "| 청년안테나(상암로 81길10) | 201 | 31.69 | 19,240,000 | 250,600 |", None)  # 띄어쓰기만 다름
    assert image_reading._agrees(first, "|  | 201 | 31.69 | 19,240,000 | 250,600 |", None)  # 다시 읽기에서 합친 칸 이름이 빠짐
    assert not image_reading._agrees(first, "| 청년안테나 (상암로81길10) | 201 | 31.69 | 19,240,000 | 250,500 |", None)  # 숫자가 다름
    assert not image_reading._agrees(first, "| 청년예가 (천중로50길 43) | 201 | 31.69 | 19,240,000 | 250,600 |", None)  # 단지 이름이 다름
    # 글 칸만 다르면 공고 본문 글자로 정함(2026-11-06 SH 「암사도전숙」·「암사도전축」): 처음 판독 쪽만 본문에 있으면 맞음
    known = "".join("※ 신청 시, 청년안테나 1동/2동 구분에 유의할 것".split())
    misread = "| 청년안테니 (상암로81길10) | 201 | 31.69 | 19,240,000 | 250,600 |"
    assert image_reading._agrees(first, misread, None, known)
    assert not image_reading._agrees(misread, first, None, known)  # 처음 판독(원문에 붙이는 쪽)이 본문에 없으면 불일치
    assert not image_reading._agrees(first, misread, None, known + "청년안테니")  # 둘 다 본문에 있으면 정할 수 없음
    assert not image_reading._agrees(first, misread.replace("250,600", "250,500"), None, known)  # 숫자가 다르면 그대로 불일치
    # 낱말은 띄어쓰기가 남은 칸 글자에서 나눔: 본문 「성내도전숙 가동/나동」에 「성내도전숙나동」은 붙어 있지 않음
    row = "| 성내도전숙 나동 (성안로 64) | 304 | 35.99 | 27,680,000 |"
    assert image_reading._agrees(row, row.replace("도전숙", "도전축"), None, "".join("성내도전숙 가동/나동".split()))
    assert not image_reading._agrees(row, row.replace("나동", "가동"), None, "".join("성내도전숙 가동/나동".split()))  # 둘 다 본문에 있음
    # 두 판독이 같게 틀려도(250,500) OCR 숫자에 없으면 불일치
    wrong = first.replace("250,600", "250,500")
    ocr = Counter(["201", "31.69", "19240000", "250600"])
    assert not image_reading._agrees(wrong, wrong, ocr) and image_reading._agrees(first, first, ocr)


def test_ocr_counts_how_often_a_value_is_used_when_ocr_shows_a_misread_and_also_checks_lines_that_are_not_table_rows():
    # 2026-11-10 코드 검토: OCR이 그림 어디엔가 있는지만 봐서, 두 판독이 같게 잘못 읽은 값이 다른 행 값과 같으면 지나갔고 표 행이 아닌 줄은 OCR을 건너뜀
    from collections import Counter

    rows = "| 101 | 31.69 | 250,600 |\n| 102 | 31.69 | 250,600 |"  # 102호는 실제 250,500인데 두 판독 모두 250,600으로 읽음
    ocr = Counter(["101", "102", "31.69", "31.69", "250600", "250500"])
    counted = image_reading.counted_numbers(image_reading.reading_numbers(rows), ocr)
    assert counted == Counter({"250600": 2})  # OCR에만 있는 250500(여섯 자리)이 오독 흔적 → 여섯 자리 판독 숫자를 셈
    assert [image_reading._agrees(line, rows, ocr, "", counted) for line in rows.split("\n")] == [False, False]  # 어느 행인지 몰라 둘 다
    # 2026-11-10 재검토: 판독 지시가 합친 칸 값을 행마다 되풀이해 적게 해서, OCR은 한 번 본 값을 판독은 행마다 적음 → 흔적이 없으면 「있는지」만
    merged = Counter(["101", "102", "31.69", "250600"])
    counted = image_reading.counted_numbers(image_reading.reading_numbers(rows), merged)
    assert counted == Counter() and all(image_reading._agrees(line, rows, merged, "", counted) for line in rows.split("\n"))
    # 흔적이 있어도 자릿수가 다른 합친 칸(31.69, 네 자리)은 세지 않음
    counted = image_reading.counted_numbers(image_reading.reading_numbers(rows), merged + Counter(["250500"]))
    assert counted == Counter({"250600": 2}) and not image_reading._agrees("| 101 | 31.69 | 250,600 |", rows, merged + Counter(["250500"]), "", counted)
    assert image_reading._agrees("| 101 | 31.69 | 250,600 |", rows, Counter(["101", "31.69", "250600", "250600", "250500"]), "", counted)
    # 작은 숫자(층·호수)는 되풀이되고 OCR이 놓치기 쉬워 흔적이 있어도 「있는지」만 봄
    small = image_reading.reading_numbers("| 2 | 250,600 |\n| 2 | 250,700 |")
    ocr = Counter(["2", "250600", "250700", "250500"])
    assert image_reading._agrees("| 2 | 250,600 |", "| 2 | 250,600 |", ocr, "", image_reading.counted_numbers(small, ocr))
    prose = "※ 신혼부부 월평균소득 70% 이하"
    counted = image_reading.counted_numbers(image_reading.reading_numbers(prose), Counter(["100"]))
    assert not image_reading._agrees(prose, prose, Counter(["100"]), "", counted)
    assert image_reading._agrees(prose, prose, Counter(["70"]), "", counted)


def test_ocr_is_skipped_when_turned_off(monkeypatch):
    monkeypatch.setenv("EXTRACTION_IMAGE_OCR", "false")
    assert image_reading._ocr_numbers(b"not a pdf", 1) is None


ROW = "| 202호 | 26.71 | 12,744,000 | 166,100 |"
BOXES = [("26.71", 100.0, 120.0), ("12744000", 100.0, 120.0), ("166100", 101.0, 121.0)]  # OCR 숫자와 그 위·아래(그 행)


def third_reading(monkeypatch, ocr, boxes=BOXES):
    monkeypatch.setenv(image_reading.THIRD_ENV, "true")
    monkeypatch.setattr(image_reading, "_ocr_numbers", lambda data, page: ocr)
    monkeypatch.setattr(image_reading, "_ocr_number_boxes", lambda data, page: boxes)
    monkeypatch.setattr(image_reading, "_render_band", lambda data, page, band: b"band")


def three(first, second, close_up):
    return RecordedModel({"image_text": [answer(first)], "image_text_check": [answer(second)], "image_text_third": [answer(close_up)]})


def test_a_close_up_third_reading_settles_a_disputed_row_when_it_and_ocr_agree_with_the_first(pictured, monkeypatch):
    # V2 5단계: 두 판독이 다른 행을 OCR로 위치를 찾아 크게 잘라 한 번 더 읽음
    material, context = pictured
    third_reading(monkeypatch, Counter({"26.71": 1, "12744000": 1, "166100": 1}))
    model = three(TABLE, TABLE.replace("166,100", "166,700"), ROW)
    new_material, _, run = image_reading.read_image_tables(material, context, model)
    assert "불일치 줄" not in new_material.text and ROW in new_material.text and model.requests[-1].call_name == "image_text_third"
    assert any("처음 판독" in note for note in run.notes)


def test_the_row_is_rewritten_from_the_second_reading_only_when_ocr_never_saw_the_first_readings_number(pictured, monkeypatch):
    material, context = pictured
    third_reading(monkeypatch, Counter({"26.71": 1, "12744000": 1, "166100": 1}))
    new_material, _, _ = image_reading.read_image_tables(material, context, three(TABLE.replace("166,100", "166,700"), TABLE, ROW))
    assert ROW in new_material.text and "166,700" not in new_material.text and "불일치 줄" not in new_material.text


def test_a_row_stays_disputed_when_ocr_cannot_tell_or_is_missing_or_the_reading_is_off(pictured, monkeypatch):
    material, context = pictured
    wrong = TABLE.replace("166,100", "166,700")
    third_reading(monkeypatch, Counter({"26.71": 1, "12744000": 1, "166100": 1, "166700": 1}))  # OCR이 두 숫자를 다 봄
    assert "불일치 줄" in image_reading.read_image_tables(material, context, three(wrong, TABLE, ROW))[0].text
    third_reading(monkeypatch, None, None)  # OCR 없음: 세 번째 판독을 하지 않음
    model = three(wrong, TABLE, ROW)
    assert "불일치 줄" in image_reading.read_image_tables(material, context, model)[0].text
    assert "image_text_third" not in [r.call_name for r in model.requests]
    third_reading(monkeypatch, Counter({"26.71": 1, "12744000": 1, "166100": 1}))
    monkeypatch.delenv(image_reading.THIRD_ENV)  # 기본은 꺼짐
    model = three(wrong, TABLE, ROW)
    assert "불일치 줄" in image_reading.read_image_tables(material, context, model)[0].text
    assert "image_text_third" not in [r.call_name for r in model.requests]
