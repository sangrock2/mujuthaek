"""두 번째 시험 채점(2026-10-24)의 재확인·서류 누락 검사 규칙: 섹션별 채택, 세부 값을 잃은 일정 재확인, 합친 서류 제외,
서류 표 머리 행·절차 표 오탐. 합성 원문과 녹화 응답만 씁니다. AI 호출 없음."""

import copy
import dataclasses
import json
from datetime import UTC, datetime

from helpers import ai_part, example, source_for, to_ai
from test_consistency import TABLE, document_candidate
from test_schedule_details import visit_schedule

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.recheck import problem_items, recheck_problems
from mujuthaek_extraction.rules.housing_notice import RULES
from mujuthaek_extraction.verify import SourceBundle, verify_extraction
from mujuthaek_extraction.verify.consistency import check_consistency, omitted_document_rows

LINE = "가상 현장 접수: 2026. 10. 5.(월) ~ 10. 6.(화) 매일 10:00~16:00, 가상주거센터 2층"
DATES = "가상 현장 접수: 2026. 10. 5.(월) ~ 10. 6.(화)"


def setup():
    data = example("housing")
    source = source_for("housing", data)
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + LINE)
    source = dataclasses.replace(source, material=material)
    part = copy.deepcopy(ai_part(data))
    part["quotes"] += [
        {"ref": "dates", "documentId": "text1", "text": DATES},
        {"ref": "fake-hours", "documentId": "text1", "text": "매일 10:00~16:00 가상주거센터"},  # 원문에 없는 이어 붙인 인용
        {"ref": "fake", "documentId": "text1", "text": "원문에 없는 무주택 문장입니다"},
    ]
    part["eligibility"][1]["quoteRefs"].append("fake")  # 자격 조건에도 근거 이슈 하나
    schedule = visit_schedule(
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-06"},
        dailyHours=[{"start": "10:00", "end": "16:00"}],
        quoteRefs=["dates", "fake-hours"],
    )
    part["schedules"].append(schedule)

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    return data, material, [part], evaluate, schedule


def test_schedule_that_lost_details_by_a_missing_quote_is_rechecked():
    _, _, parts, evaluate, _ = setup()
    first = evaluate(parts)
    visit = next(s for s in first.candidate["schedules"] if s["id"] == "visit")
    assert visit["dailyHours"] == []  # 남은 인용(날짜 줄)에 시각이 없어 지워짐
    problems = problem_items(first)
    assert any(p.startswith("DETAIL_UNVERIFIED_CLEARED") and "접수 시각" in p for p in problems[("schedules", "visit")])


def test_improved_section_is_adopted_even_if_another_section_gets_worse():
    data, material, parts, evaluate, schedule = setup()
    fixed_schedule = {**copy.deepcopy(schedule), "quoteRefs": ["line"]}
    worse = to_ai(data["eligibility"][1])
    worse["quoteRefs"] = ["bad"]  # 자격 조건은 근거를 모두 잃음(새 문제)
    reply = {
        "quotes": [
            *ai_part(data)["quotes"],  # 조건식 안의 근거 참조(e1)
            {"ref": "line", "documentId": "text1", "text": LINE},
            {"ref": "bad", "documentId": "text1", "text": "원문에 없는 다른 문장입니다"},
        ],
        "notice": parts[0]["notice"],  # 원문을 늘려 공고 쪽 문제도 함께 보냄(그대로 돌려줌)
        "schedules": [fixed_schedule],
        "eligibility": [worse],
        "coverage": {s: {"status": "EXTRACTED", "reason": None} for s in ("notice", "schedules", "eligibility")},
    }
    model = RecordedModel({"recheck": [json.dumps(reply, ensure_ascii=False)]})
    result = recheck_problems(RULES, material, model, parts, evaluate)
    assert result.accepted and result.adopted_sections == ("schedules",)
    visit = next(s for s in result.report.candidate["schedules"] if s["id"] == "visit")
    assert visit["dailyHours"] == [{"start": "10:00", "end": "16:00"}]  # 다시 인용해 되찾음
    assert result.parts[0]["eligibility"][1] == parts[0]["eligibility"][1]  # 나빠진 섹션은 처음 것


def test_merged_duplicate_document_is_not_sent_as_a_dropped_item():
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))
    twin = {**copy.deepcopy(part["requiredDocuments"][0]), "id": "twin-document"}  # 같은 이름·묶음·제출 시점: 결합할 때 합쳐짐
    part["requiredDocuments"].append(twin)

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    assert "twin-document" not in {d["id"] for d in evaluate([part]).candidate["requiredDocuments"]}
    model = RecordedModel({})
    result = recheck_problems(RULES, source.material, model, [part], evaluate)
    assert result.rechecked == [] and model.requests == []  # 빠진 항목으로 재확인 자리를 차지하지 않음


def omission(text, names):
    findings = check_consistency(document_candidate(text, names), SourceBundle(texts={"pdf-text": text}))
    return [f for f in findings if f.code == "DOCUMENT_OMISSION_SUSPECTED"]


def test_document_header_rows_and_procedure_tables_are_not_counted_as_missing_documents():
    titled = "\n".join(["가상 계약 시 구비서류", "[표 11-1]", "| 구 분 | 계약서류 |", "| 본인 | 가상 확인서 |", "| 대리 | 가상 위임장 |"])
    [finding] = omission(TABLE + "\n" + titled, ["가상 신청서"])
    assert omitted_document_rows(finding.description) == 2 and "구 분" not in finding.description
    rows = ["| 5단계 | 가상 청약신청서 작성 |", "| 6단계 | 가상 동의서 확인 |", "| 7단계 | 가상 청약신청서 제출 |"]
    steps = "\n".join(["가상 신청 절차(제출서류 작성 안내)", "[표 12-1]", *rows])
    assert omission(TABLE + "\n" + steps, ["가상 신청서"]) == []
