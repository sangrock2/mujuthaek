"""자격 조건 AI 재확인: 고친 결과가 검증에서 더 나을 때만 채택합니다. 녹화 응답만 씁니다."""

import copy
import json
from datetime import UTC, datetime

from helpers import ai_part, example, source_for, to_ai

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.recheck import _improved, _keep_verified_dates, _problem_keys, problem_items, recheck_problems
from mujuthaek_extraction.rules.housing_notice import RULES
from mujuthaek_extraction.verify import SourceBundle, VerificationReport, verify_extraction


def setup():
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))  # ai_part는 예시 데이터와 목록을 공유합니다
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 무주택 문장입니다"})
    part["eligibility"][1]["quoteRefs"].append("fake")  # 근거 하나는 맞고 하나는 원문에 없음 → 조건은 남고 이슈만 붙음

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    return data, source, [part], evaluate


def answer(item, quotes):
    return json.dumps({"quotes": quotes, "eligibility": [item], "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}}}, ensure_ascii=False)


def test_fixed_condition_is_accepted_when_verification_improves():
    data, source, parts, evaluate = setup()
    assert any(i["target"] == "/eligibility/1" for i in evaluate(parts).candidate["quality"]["reviewIssues"])
    fixed = json.loads(json.dumps(to_ai(data["eligibility"][1])).replace('"e1"', '"q1"'))  # 조건식 안의 근거까지 새 인용을 가리킴
    model = RecordedModel({"recheck": [answer(fixed, [{"ref": "q1", "documentId": "text1", "text": data["evidence"][0]["quote"]}])]})

    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.accepted and result.rechecked == ["eligibility/" + data["eligibility"][1]["id"]]
    assert result.report.passed
    # 재확인 요청에는 문제 설명과 원래 인용문이 들어갑니다
    request = model.requests[0]
    assert "EVIDENCE_QUOTE_NOT_FOUND" in request.instructions and "원문에 없는 무주택 문장입니다" in request.instructions


def test_recheck_that_does_not_help_is_discarded():
    data, source, parts, evaluate = setup()
    unchanged = copy.deepcopy(parts[0]["eligibility"][1])
    quotes = [q for q in parts[0]["quotes"] if q["ref"] in unchanged["quoteRefs"]]
    model = RecordedModel({"recheck": [answer(unchanged, quotes)]})

    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert not result.accepted and result.parts is parts and not result.report.passed


def test_no_condition_problem_means_no_call():
    data = example("housing")
    source = source_for("housing", data)
    model = RecordedModel({})

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    result = recheck_problems(RULES, source.material, model, [ai_part(data)], evaluate)
    assert result.rechecked == [] and model.requests == []


def test_recheck_answer_still_breaking_the_schema_is_not_merged():
    # 검토 지적: 재확인 호출이 형식 위반 응답을 (수정 호출 뒤에도) 돌려주면 그대로 섞일 수 있었음
    data, source, parts, evaluate = setup()
    broken = copy.deepcopy(parts[0]["eligibility"][1])
    broken["category"] = "NOT_A_CATEGORY"
    quotes = [q for q in parts[0]["quotes"] if q["ref"] in broken["quoteRefs"]]
    model = RecordedModel({"recheck": [answer(broken, quotes), answer(broken, quotes)]})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert not result.accepted and result.parts is parts


def partial_scoring_setup():
    # 선정 기준 하나를 빠뜨리고 AI가 PARTIAL로 적은 응답
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))
    missing = part["selectionRules"].pop()
    part["coverage"]["selectionRules"] = {"status": "PARTIAL", "reason": "선정 기준 일부를 옮기지 못했습니다."}

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    quotes = [q for q in part["quotes"] if q["ref"] in json.dumps(missing)]
    return source, [part], evaluate, missing, quotes


def scoring_answer(items, quotes):
    return json.dumps({"quotes": quotes, "selectionRules": items, "coverage": {"selectionRules": {"status": "EXTRACTED", "reason": None}}}, ensure_ascii=False)


def test_missing_items_of_a_partial_section_are_added_back():
    source, parts, evaluate, missing, quotes = partial_scoring_setup()
    assert not evaluate(parts).passed
    model = RecordedModel({"recheck": [scoring_answer([missing], quotes)]})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.accepted and "selectionRules" in result.rechecked
    assert result.report.passed
    assert missing["id"] in {r["id"] for r in result.report.candidate["selectionRules"]}
    # 요청에는 이미 있는 항목 id만 보냅니다(목록 전체를 다시 보내지 않음)
    assert "existingIds" in model.requests[0].instructions


def test_partial_section_is_not_cleared_by_the_ai_just_saying_it_is_complete():
    source, parts, evaluate, missing, quotes = partial_scoring_setup()
    model = RecordedModel({"recheck": [scoring_answer([], [])]})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert not result.report.passed
    assert result.report.candidate["quality"]["coverage"]["selectionRules"]["status"] == "PARTIAL"


def test_oversized_item_is_not_sent_and_request_is_split_into_lines(monkeypatch):
    # 실측(2026-10-18 LH 익산 행복주택): 호실별 가격 묶음 8개를 한 줄로 이어 45만 자 요청이 되어 모델이 읽지 못함
    import mujuthaek_extraction.recheck as recheck

    data, source, parts, evaluate = setup()
    unchanged = copy.deepcopy(parts[0]["eligibility"][1])
    quotes = [q for q in parts[0]["quotes"] if q["ref"] in unchanged["quoteRefs"]]
    model = RecordedModel({"recheck": [answer(unchanged, quotes)]})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.rechecked and "\n" in model.requests[0].instructions.split("# 다시 확인할 항목\n", 1)[1]  # 항목을 줄 단위로

    monkeypatch.setattr(recheck, "MAX_TARGET_CHARS", 10)  # 어떤 항목도 상한 안에 들지 않으면 재확인을 부르지 않습니다
    model = RecordedModel({})
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.rechecked == [] and model.requests == []


def test_count_rule_error_at_its_real_location_points_to_the_owner_item():
    # 검사기는 수량 묶음 오류를 수량의 실제 위치로 알립니다 (/counts/<id> 형식은 2026-10-20에 없어짐)
    from mujuthaek_extraction.recheck import _item_key

    data = example("housing")
    group = data["supplyGroups"][0]
    assert _item_key(data, "/notice/counts/0") == ("notice", None)
    assert _item_key(data, "/supplyGroups/0/counts/0") == ("supplyGroups", group["id"])


def age_setup():
    # 나이 조건(AGE_YEARS GTE 19 / LTE 39)에 원문에 없는 인용 하나가 붙어 근거 이슈만 난 응답
    data = example("housing")
    source = source_for("housing", data)
    part = copy.deepcopy(ai_part(data))
    part["quotes"].append({"ref": "fake", "documentId": "text1", "text": "원문에 없는 나이 문장입니다"})
    part["eligibility"][0]["quoteRefs"].append("fake")

    def evaluate(parts):
        candidate = assemble(parts, source).candidate
        return verify_extraction(candidate, SourceBundle.from_material(source.material), None, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC))

    original = to_ai(data["eligibility"][0])
    quotes = [q for q in ai_part(data)["quotes"] if q["ref"] in original["quoteRefs"]]
    return data, source, [part], evaluate, quotes


def test_quote_fix_that_flips_the_operator_is_not_accepted():
    # 실측(2026-10-20): 인용을 고치며 GTE 19를 LTE 19로 뒤집은 응답이 이슈 1→0으로 채택되어 통과됨
    data, source, parts, evaluate, quotes = age_setup()
    first = evaluate(parts)
    assert {i["code"] for i in first.candidate["quality"]["reviewIssues"] if i["target"] == "/eligibility/0"} == {"EVIDENCE_QUOTE_NOT_FOUND"}
    flipped = to_ai(data["eligibility"][0])
    flipped["rule"]["expression"]["children"][0]["operator"] = "LTE"
    model = RecordedModel({"recheck": [answer(flipped, quotes)]})

    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert not result.accepted and result.parts is parts and not result.report.passed
    operators = [c["operator"] for c in result.report.candidate["eligibility"][0]["rule"]["expression"]["children"]]
    assert operators == ["GTE", "LTE"]  # 뒤집힌 뜻이 결과에 들어가지 않음


def test_quote_fix_keeping_the_meaning_is_accepted():
    data, source, parts, evaluate, quotes = age_setup()
    fixed = to_ai(data["eligibility"][0])
    fixed["description"] = "신청일 현재 만 19세 이상 39세 이하입니다."  # 설명 글만 바뀌는 것은 뜻이 바뀐 것이 아닙니다
    model = RecordedModel({"recheck": [answer(fixed, quotes)]})

    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.accepted and result.report.passed


def test_meaning_change_is_allowed_when_a_value_problem_was_sent():
    # 값·조건 문제를 보낸 항목은 뜻을 고치는 것이 목적이므로 뜻 비교로 막지 않습니다(채택은 같은 검증 기준)
    from mujuthaek_extraction.recheck import _keep_meaning

    data, source, parts, evaluate, quotes = age_setup()
    flipped = to_ai(data["eligibility"][0])
    flipped["rule"]["expression"]["children"][0]["operator"] = "LTE"
    reply = {"eligibility": [flipped]}
    value_target = [{"section": "eligibility", "id": "age", "problems": ["VALUE_NOT_IN_QUOTE /eligibility/0: 값이 인용에 없습니다"]}]
    quote_target = [{"section": "eligibility", "id": "age", "problems": ["EVIDENCE_QUOTE_NOT_FOUND /eligibility/0: 인용문을 찾지 못했습니다"]}]
    assert _keep_meaning(parts, reply, value_target) is reply
    assert _keep_meaning(parts, reply, quote_target)["eligibility"] == []
    other_target = [{"section": "eligibility", "id": "income", "problems": ["VALUE_NOT_IN_QUOTE /eligibility/2: 값이 인용에 없습니다"]}]
    assert _keep_meaning(parts, reply, other_target)["eligibility"] == []  # 보내지 않은 항목의 뜻도 바꾸지 않습니다


def test_recheck_that_fixes_items_but_breaks_another_is_not_accepted():
    # 개수로만 비교하면 이슈 2개를 없애고 재확인하지 않은 항목에 1개를 새로 만든 응답(2→1)이 "좋아짐"으로 채택됩니다
    data, source, parts, evaluate, quotes = age_setup()
    parts[0]["eligibility"][1]["quoteRefs"].append("fake")  # 무주택 조건에도 같은 근거 이슈
    first = evaluate(parts)
    assert {i["target"] for i in first.candidate["quality"]["reviewIssues"]} == {"/eligibility/0", "/eligibility/1"}
    fixed = [to_ai(data["eligibility"][0]), to_ai(data["eligibility"][1])]
    broken_income = to_ai(data["eligibility"][2])
    broken_income["quoteRefs"].append("bad")  # 재확인하지 않은 소득 조건에 새 근거 이슈
    reply_quotes = [*ai_part(data)["quotes"], {"ref": "bad", "documentId": "text1", "text": "원문에 없는 소득 문장입니다"}]
    reply = json.dumps(
        {"quotes": reply_quotes, "eligibility": [*fixed, broken_income], "coverage": {"eligibility": {"status": "EXTRACTED", "reason": None}}},
        ensure_ascii=False,
    )
    model = RecordedModel({"recheck": [reply]})

    # 그대로 합쳤다면 이슈는 2→1로 줄지만 소득 조건에 처음 없던 문제가 생깁니다(개수 비교만 하면 채택됨)
    merged = [{**parts[0], "eligibility": [*fixed, broken_income], "quotes": reply_quotes}]
    assert {i["target"] for i in evaluate(merged).candidate["quality"]["reviewIssues"]} == {"/eligibility/2"}
    # 보낸 항목만 받으므로(2026-10-21) 보내지 않은 소득 조건은 응답에 섞여 와도 바뀌지 않고, 고친 두 항목만 채택됩니다
    result = recheck_problems(RULES, source.material, model, parts, evaluate)
    assert result.accepted and result.report.candidate["quality"]["reviewIssues"] == []
    assert result.parts[0]["eligibility"][2] == parts[0]["eligibility"][2]


def test_recheck_changes_only_problem_fields_of_notice():
    from mujuthaek_extraction.recheck import merge_recheck, sent_scope

    parts = [{"notice": {"title": "원래 제목", "announcedOn": "2026-10-07", "supplyType": "행복주택", "quoteRefs": ["q1"]}, "quotes": []}]
    answer = {"notice": {"title": "다른 제목", "announcedOn": "2026-10-08", "supplyType": "국민임대", "quoteRefs": ["q2"]}}
    targets = [{"section": "notice", "id": None, "problems": ["API_MISMATCH /notice/announcedOn: 공고일이 다릅니다"]}]
    merged = merge_recheck(parts, answer, (), sent_scope(targets))[0]["notice"]
    assert merged["announcedOn"] == "2026-10-08" and merged["title"] == "원래 제목" and merged["supplyType"] == "행복주택"
    # 칸을 정할 수 없는 문제(공고 전체)면 전부 받습니다
    whole = [{"section": "notice", "id": None, "problems": ["NOTICE_NOT_EXTRACTED /notice: 없음"]}]
    assert merge_recheck(parts, answer, (), sent_scope(whole))[0]["notice"]["title"] == "다른 제목"


def test_missing_records_of_values_the_recheck_filled_are_dropped_and_a_whole_notice_answer_brings_its_coverage():
    # 2026-11-06 V2 5건 재측정 sh-310672: 재확인 답이 공급 기관·모집 수를 채우고 범위를 EXTRACTED로 고쳤는데, 처음 답의 「원문에 없음」 기록과
    # PARTIAL이 그대로 남아 「누락이라면서 값이 있음」 새 문제로 답이 버려지고 공고 전체가 검수로 감
    from mujuthaek_extraction.recheck import merge_recheck, sent_scope

    notice = {"title": "공실세대 입주자 모집", "publisher": None, "counts": [{"id": "offered", "value": None}], "quoteRefs": ["q1"]}
    missing = [
        {"target": "/notice/publisher", "reason": "NOT_IN_SOURCE", "description": "공급 기관명이 없어요."},
        {"target": "/notice/counts/0/value", "reason": "NOT_IN_SOURCE", "description": "모집 수가 없어요."},
        {"target": "/notice/announcedOn", "reason": "NOT_IN_SOURCE", "description": "공고일이 없어요."},
    ]
    partial = {"notice": {"status": "PARTIAL", "reason": "모집 수를 확정하지 못했어요."}}
    parts = [{"notice": notice, "quotes": [], "missingFields": missing, "coverage": partial}]
    filled = {**notice, "publisher": "가상협동조합", "counts": [{"id": "offered", "value": 1}], "quoteRefs": ["q2"]}
    answer = {"notice": filled, "coverage": {"notice": {"status": "EXTRACTED", "reason": None}}}
    whole = sent_scope([{"section": "notice", "id": None, "problems": ["MISSING_NOTICE_CORE /notice"]}])
    merged = merge_recheck(parts, answer, (), whole)[0]
    assert [m["target"] for m in merged["missingFields"]] == ["/notice/announcedOn"]  # 아직 빈 칸의 기록은 둠
    assert merged["coverage"]["notice"] == {"status": "EXTRACTED", "reason": None}
    assert parts[0]["missingFields"] == missing and parts[0]["coverage"] == partial  # 처음 조각은 그대로
    # 누락으로 적힌 칸을 하나도 채우지 않은 답은 범위 상태를 바꾸지 않습니다(「다 넣었다」고 적기만 해서 통과되지 않게)
    retitled = merge_recheck(parts, {**answer, "notice": {**notice, "title": "다른 제목"}}, (), whole)[0]
    assert retitled["missingFields"] == missing and retitled["coverage"] == partial
    # 칸 일부만 받으면 그 칸의 기록만 지우고 범위 상태는 두지 않습니다(응답의 범위 상태는 받지 않은 칸까지 말함)
    one = sent_scope([{"section": "notice", "id": None, "problems": ["API_MISMATCH /notice/publisher: 공급 기관이 다릅니다"]}])
    narrow = merge_recheck(parts, answer, (), one)[0]
    assert [m["target"] for m in narrow["missingFields"]] == ["/notice/counts/0/value", "/notice/announcedOn"] and narrow["coverage"] == partial


def test_missing_record_of_a_list_item_value_the_recheck_filled_is_dropped():
    from mujuthaek_extraction.recheck import merge_recheck, sent_scope

    group = {"id": "g1", "prices": [{"kind": "DEPOSIT", "amountKrw": None}], "quoteRefs": ["q1"]}
    other = {"id": "g2", "prices": [{"kind": "DEPOSIT", "amountKrw": None}], "quoteRefs": ["q1"]}
    missing = [
        {"target": "/supplyGroups/0/prices/0/amountKrw", "reason": "UNREADABLE", "description": "보증금 칸을 읽지 못했어요."},
        {"target": "/supplyGroups/1/prices/0/amountKrw", "reason": "UNREADABLE", "description": "보증금 칸을 읽지 못했어요."},
    ]
    parts = [{"supplyGroups": [group, other], "quotes": [], "missingFields": missing}]
    answer = {
        "supplyGroups": [{**group, "prices": [{"kind": "DEPOSIT", "amountKrw": 1_000_000}]}, {**other, "prices": [{"kind": "DEPOSIT", "amountKrw": 2_000_000}]}]
    }
    sent = sent_scope([{"section": "supplyGroups", "id": "g1", "problems": ["SUPPLY_PRICE_MISSING /supplyGroups/0: 없음"]}])
    merged = merge_recheck(parts, answer, (), sent)[0]
    assert merged["supplyGroups"][0]["prices"][0]["amountKrw"] == 1_000_000 and merged["supplyGroups"][1] == other  # 보낸 항목만 받음
    assert merged["missingFields"] == missing[1:]  # 받은 항목의 채운 칸 기록만 지움


def schedule_part(ends_at, quote_ref="q-end", quote="등기우편 신청: 2026. 11. 3.(화) 도착분까지"):
    item = {"id": "mail-apply", "kinds": ["APPLICATION"], "startsAt": None, "endsAt": ends_at, "quoteRefs": [quote_ref]}
    return {"quotes": [{"ref": quote_ref, "documentId": "text1", "text": quote}], "schedules": [item]}


def test_recheck_answer_that_loses_a_verified_schedule_date_keeps_the_first_item():
    first = [schedule_part({"precision": "DAY", "value": "2026-11-03"})]
    # 재확인 답이 확인된 마감일을 비움 → 그 일정은 응답에서 빠져 처음 것이 남습니다
    nulled = schedule_part(None)
    assert _keep_verified_dates(first, nulled)["schedules"] == []
    # 근거에 없는 시각(16:00)을 붙임 → 처음 것
    timed = schedule_part({"precision": "MINUTE", "value": "2026-11-03T16:00:00+09:00"})
    assert _keep_verified_dates(first, timed)["schedules"] == []
    # 근거에 그 시각이 있으면 받습니다
    stated = schedule_part({"precision": "MINUTE", "value": "2026-11-03T16:00:00+09:00"}, quote="2026. 11. 3.(화) 16:00 도착분까지")
    assert _keep_verified_dates(first, stated) is stated
    # 처음 날짜가 근거로 확인되지 않으면(인용에 그 날짜 없음) 재확인 답을 막지 않습니다
    unverified = [schedule_part({"precision": "DAY", "value": "2026-11-05"})]
    assert _keep_verified_dates(unverified, nulled) is nulled


def test_rechecked_note_is_sent_and_counted_by_omitted_rows():
    candidate = {
        "requiredDocuments": [],
        "quality": {
            "reviewIssues": [],
            "notes": [
                {"code": "DOCUMENT_OMISSION_SUSPECTED", "target": "/quality/coverage/requiredDocuments", "description": "원문 서류 표 행 5개를 …"},
                {"code": "DETAIL_UNVERIFIED_CLEARED", "target": "/requiredDocuments", "description": "표시만"},
            ],
        },
    }
    report = VerificationReport(candidate=candidate, findings=[], contract_errors=[])
    assert list(problem_items(report)) == [("requiredDocuments", None)]  # 서류 섹션 전체를 다시 봅니다
    _, issues = _problem_keys(report)
    assert issues[("DOCUMENT_OMISSION_SUSPECTED", ("requiredDocuments", None))] == 5
    fewer = copy.deepcopy(candidate)
    fewer["quality"]["notes"][0]["description"] = "원문 서류 표 행 2개를 …"
    # 빠진 행이 줄면 나아진 것으로 봅니다(일부만 채운 재확인도 채택될 수 있음)
    assert _improved(report, VerificationReport(candidate=fewer, findings=[], contract_errors=[]), ["requiredDocuments"])


def test_part_with_empty_sections_does_not_stop_the_recheck():
    # 2026-10-25 로컬 실제 흐름: AI 답의 한 묶음이 eligibility·quotes를 null로 주자 재확인이 TypeError로 멈춰 공고 처리가 FAILED가 됨
    data, source, parts, evaluate = setup()
    empty = {"quotes": None, "eligibility": None}
    model = RecordedModel({"recheck": []})
    result = recheck_problems(RULES, source.material, model, [empty, *parts], evaluate)
    assert result is not None
