"""비용 절감 2차(2026-10-25): 큰 서류 표는 처음부터 나눠 부르기(설정 EXTRACTION_PRESPLIT_DOC_ROWS=0이면 이전 동작)."""

import json
from types import SimpleNamespace

from mujuthaek_extraction import extract
from mujuthaek_extraction.extract import document_rows


def test_document_rows_counts_document_table_rows():
    rows = "\n".join(f"| 가상 증명서 {i} | 1부 |" for i in range(70))
    text = "■ 제출서류\n| 서류 | 부수 |\n" + rows
    assert document_rows(SimpleNamespace(text=text)) == 70
    assert document_rows(SimpleNamespace(text="서류 없음")) == 0


def test_large_document_table_is_split_from_the_start(monkeypatch):
    from helpers import ai_part, example, source_for
    from test_round3 import split_script

    from mujuthaek_extraction.model import RecordedModel
    from mujuthaek_extraction.rules.housing_notice import RULES

    data = example("housing")
    source = source_for("housing", data)
    monkeypatch.setattr(extract, "PRESPLIT_ROWS", 1)
    monkeypatch.setattr(extract, "document_rows", lambda material: 5)
    from test_round3 import documents_part

    good = json.dumps(ai_part(data, ("requiredDocuments",)), ensure_ascii=False)
    script = split_script(data, [good])
    script["documents-submit"] = [json.dumps(documents_part(data, ["submit-a"]), ensure_ascii=False)]
    script["documents-visit"] = [json.dumps(documents_part(data, ["visit-a"]), ensure_ascii=False)]
    model = RecordedModel(script)
    result = extract.run_extraction(RULES, source.material, model)
    names = [r.call_name for r in model.requests]
    assert "documents" not in names and "documents-submit" in names and "documents-visit" in names
    assert any("처음부터 표 묶음별로" in n for n in result.notes)


def test_presplit_off_keeps_the_single_documents_call(monkeypatch):
    from helpers import ai_part, example, source_for
    from test_round3 import split_script

    from mujuthaek_extraction.model import RecordedModel
    from mujuthaek_extraction.rules.housing_notice import RULES

    data = example("housing")
    source = source_for("housing", data)
    monkeypatch.setattr(extract, "PRESPLIT_ROWS", 0)
    good = json.dumps(ai_part(data, ("requiredDocuments",)), ensure_ascii=False)
    model = RecordedModel(split_script(data, [good]))
    extract.run_extraction(RULES, source.material, model)
    assert "documents" in [r.call_name for r in model.requests]


def test_cut_answers_drop_strict_mode_nulls_before_salvage():
    """2026-10-25 33번: 잘린 응답은 어댑터가 엄격 모드 null 칸을 지우지 못해, 살린 인용의 「unitRow」: null이 형식 오류가 되어
    서류 전체를 버렸습니다. 살릴 때 선택 칸 null을 지웁니다."""
    import json

    from mujuthaek_extraction.assemble import ai_output
    from mujuthaek_extraction.extract import fill_from_cuts, salvage_truncated, schema_errors
    from mujuthaek_extraction.model.strict_schema import to_strict

    optional = to_strict(ai_output.schema())[1]
    assert "unitRow" in optional
    quotes = [{"ref": f"q{i}", "documentId": "t", "text": t, "unitRow": None} for i, t in ((1, "가상 신분증"), (2, "가상 등본"), (3, "가상 초본"))]
    docs = [
        {"id": f"d{i}", "name": n, "submissionTime": "계약 시", "quoteRefs": [f"q{i}"]} for i, n in ((1, "가상 신분증"), (2, "가상 등본"), (3, "가상 초본"))
    ]
    full = json.dumps({"quotes": quotes, "requiredDocuments": docs}, ensure_ascii=False)
    cut = full[: full.index('"가상 초본", "submissionTime"')]
    salvaged = salvage_truncated(cut, ("requiredDocuments",), optional)
    assert all("unitRow" not in q for q in salvaged["quotes"])
    assert len(salvaged["requiredDocuments"]) == 2
    assert "unitRow" not in (schema_errors(salvaged, ai_output.schema()) or "")
    part = {"quotes": [], "requiredDocuments": []}
    assert fill_from_cuts(part, [cut], ("requiredDocuments",), optional) == 2
    assert all("unitRow" not in q for q in part["quotes"])


def test_cut_shared_schema_answer_drops_sections_the_call_does_not_own():
    """같은 날 다시 돌린 33번: 공유 형식으로 받은 잘린 서류 응답의 맨 위 「eligibility」「notice」 null이 형식 오류가 되어 항목을 모두 버림."""
    import json

    from mujuthaek_extraction.extract import salvage_truncated

    own = {"properties": {"quotes": {}, "requiredDocuments": {}, "coverage": {"properties": {"requiredDocuments": {}}}}}
    quotes = [{"ref": "q1", "documentId": "t", "text": "가상 신분증"}, {"ref": "q2", "documentId": "t", "text": "가상 등본"}]
    docs = [{"id": "d1", "name": "가상 신분증", "submissionTime": "계약 시", "quoteRefs": ["q1"]}, {"id": "d2", "name": "가상 등본"}]
    full = json.dumps({"notice": None, "eligibility": None, "quotes": quotes, "requiredDocuments": docs}, ensure_ascii=False)
    cut = full[: full.index('{"id": "d2"') + 12]  # 두 번째 서류 중간에서 잘림
    salvaged = salvage_truncated(cut, ("requiredDocuments",), frozenset(), own)
    assert "notice" not in salvaged and "eligibility" not in salvaged
    assert [d["name"] for d in salvaged["requiredDocuments"]] == ["가상 신분증"]


def test_refusal_describing_people_does_not_block_the_channel():
    """같은 날 33번: 근거 인용은 「인터넷 청약」을 적었는데 AI 설명의 「인터넷 청약이 불가한 고령자·장애인 등은 창구에서」 때문에 ONLINE이
    지워져 「현장 접수만」으로 보임. 사람을 꾸미는 「불가한」은 그 방법을 막은 말이 아니라 다른 방법을 쓸 대상(조건)입니다."""
    from test_round4 import assembled_extra
    from test_schedule_details import visit_schedule

    from mujuthaek_extraction.assemble.details import channel_mentions

    assert "ONLINE" not in channel_mentions("인터넷 청약이 불가한 고령자·장애인 등은 가상 은행 창구에서 접수할 수 있어요")[1]
    assert "ONLINE" in channel_mentions("인터넷 신청 불가")[1]
    line = "1순위 접수 2026.10.05. 인터넷 청약 (가상청약홈) / 가상 은행 창구 방문 접수"
    schedule = visit_schedule(
        id="first",
        kinds=["APPLICATION"],
        rawLabel="1순위 접수",
        channels=["ONLINE", "ONSITE"],
        places=[],
        dailyHours=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        description="인터넷 접수는 가상청약홈에서 하고, 인터넷 청약이 불가한 고령자·장애인 등은 가상 은행 창구에서 접수할 수 있어요.",
        quoteRefs=["first"],
    )
    result = assembled_extra([line], {"first": line}, schedules=[schedule])
    [kept] = [s for s in result.candidate["schedules"] if s["id"] == "first"]
    assert kept["channels"] == ["ONLINE", "ONSITE"]


def test_same_document_key_keeps_targets_apart_and_ignores_trailing_si():
    """같은 날 33번: 대상을 보지 않아 일반공급 공통 서류가 같은 이름의 특별공급 서류로 여겨져 빠졌고, 「…제출 시」「…제출」만 달라 같은 서류가 두 번 들어감."""
    from mujuthaek_extraction.assemble.details import _time_key
    from mujuthaek_extraction.extract import _item_key

    special = {"name": "가상 신분증", "submissionTime": "가상 서류 제출 시", "appliesTo": "특별공급 신청자", "scope": {"targetGroups": ["특별공급"]}}
    general = {**special, "appliesTo": "일반공급 당첨자", "scope": {"targetGroups": ["일반공급"]}}
    assert _item_key("requiredDocuments", special) != _item_key("requiredDocuments", general)
    assert _item_key("requiredDocuments", special) == _item_key("requiredDocuments", {**special, "submissionTime": "가상 서류 제출"})
    assert _time_key("당첨자 서류 제출 시") == _time_key("당첨자 서류 제출") != _time_key("계약 시")
