"""두 번째 시험 채점(2026-10-24)의 일반 규칙: 요일 가운뎃점류, 확인한 제외 요일만 남기기, 이어지는 기간의 접수 시각, 「필수/선택」 칸 서류 묶음.
합성 원문만 씁니다. AI 호출 없음."""

import copy
import dataclasses

from helpers import ai_part, example, source_for
from test_schedule_details import document, visit_schedule

from mujuthaek_extraction.assemble.assembler import assemble
from mujuthaek_extraction.assemble.details import DAY_PATTERNS, continuous_hours, required_mark_group


def assembled(lines, quotes, schedules=(), documents=()):
    data = example("housing")
    source = source_for("housing", data)
    material = dataclasses.replace(source.material, text=source.material.text + "\n" + "\n".join(lines))
    part = copy.deepcopy(ai_part(data))
    part["quotes"] += [{"ref": ref, "documentId": "text1", "text": text} for ref, text in quotes.items()]
    part["schedules"] += list(schedules)
    part["requiredDocuments"] += list(documents)
    return assemble([part], dataclasses.replace(source, material=material))


def cleared(result):
    return [i["description"] for i in result.issues if i["code"] == "DETAIL_UNVERIFIED_CLEARED"]


def day_schedule(quote_ref, excluded, **changes):
    return visit_schedule(
        id=f"days-{quote_ref}",
        places=[],
        dailyHours=[],
        breaks=[],
        timeNote=None,
        excludedDays=excluded,
        startsAt={"precision": "DAY", "value": "2026-10-05"},
        endsAt={"precision": "DAY", "value": "2026-10-06"},
        quoteRefs=[quote_ref],
        **changes,
    )


def test_day_words_joined_by_any_middle_dot():
    for dot in ("·", "․", "ㆍ", "・", "‧"):
        text = f"토{dot}일요일 및 공휴일에는 접수하지 않아요"
        found = {code for code, pattern in DAY_PATTERNS.items() if pattern.search(text)}
        assert found == {"SAT", "SUN"}, dot
    assert not DAY_PATTERNS["MON"].search("3월 임대료")  # 낱말 속 「월」은 요일이 아님


def test_unverified_day_is_dropped_but_verified_days_are_kept():
    line = "가상 접수는 토․일요일 및 공휴일에는 받지 않아요."
    schedules = [day_schedule("days", ["SAT", "SUN", "HOLIDAY", "MON"])]
    result = assembled([line], {"days": line}, schedules=schedules)
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "days-days")
    assert kept["excludedDays"] == ["SAT", "SUN", "HOLIDAY"]  # 근거에 없는 MON만 뺌(확인 못 한 요일을 남기지 않음)
    assert any("MON" in d for d in cleared(result))


def test_daily_hours_need_a_same_day_window():
    same_day = [{"start": "10:00", "end": "17:00"}]
    assert continuous_hours("접수 시간: 매일 10:00~17:00", same_day) is None
    assert continuous_hours("10시부터 17시까지 접수", same_day) is None
    # 첫날 시작 ~ 마지막 날 끝의 이어지는 기간
    assert continuous_hours("가상 신청 포기: 2026.10.22.(목) 10:00 ~ 23(금) 17:00", same_day)
    assert continuous_hours("가상 접수: 10.22.(목) 10:00 ~ 10.23.(금) 17:00", same_day)
    # 야간·24시간·다음 날 접수
    assert continuous_hours("신청시간 10:00~17:00 ※ 기간 중 야간(17:00~10:00)에도 신청 가능", same_day)
    assert continuous_hours("10:00부터 다음 날 17:00까지", same_day)
    # 끝이 시작보다 이른 구간
    assert continuous_hours("17:00~10:00", [{"start": "17:00", "end": "10:00"}])
    # 같은 날 구간과 연속 구간이 함께 있으면 같은 날 구간으로 확인됩니다
    assert continuous_hours("매일 10:00~17:00 (마지막 날 10.23.(금) 10:00 ~ 10.24.(토) 17:00)", same_day) is None


def test_continuous_period_does_not_become_daily_hours():
    line = "가상 신청 포기는 2026.10.05.(월) 10:00 ~ 06(화) 18:00 사이에 인터넷으로 해요."
    schedule = visit_schedule(
        id="giveup",
        channels=["ONLINE"],
        places=[],
        breaks=[],
        excludedDays=[],
        timeNote=None,
        dailyHours=[{"start": "10:00", "end": "18:00"}],
        quoteRefs=["giveup"],
    )
    result = assembled([line], {"giveup": line}, schedules=[schedule])
    kept = next(s for s in result.candidate["schedules"] if s["id"] == "giveup")
    assert kept["dailyHours"] == []
    assert kept["startsAt"]["precision"] == kept["endsAt"]["precision"] == "MINUTE"  # 시작·끝 시각은 그대로
    assert any("이어지는 기간" in d for d in cleared(result))


def test_required_mark_group_from_table_cells():
    assert required_mark_group("| 가상 확인서 | 필수 | 발급일 기준 |") == "COMMON"
    assert required_mark_group("| 가상 증명서 | [선택] | 해당자 |") == "CONDITIONAL"
    assert required_mark_group("가상 동의서 [필수]") == "COMMON"
    assert required_mark_group("| 가상 확인서 | 필수 선택 필수 | |") is None  # 한 칸에 몰린 표시는 짝을 모름
    assert required_mark_group("| 가상 확인서 | 필수 |\n| 가상 증명서 | 선택 |") is None  # 섞이면 정하지 않음
    assert required_mark_group("| 가상 확인서 | 필수 제출 서류 |") is None  # 칸 전체가 표시일 때만


def test_document_group_from_required_optional_column():
    header = "| 해당서류 | 서류유형 | 발급기준 |"
    must = "| 가상 등록증 사본 | 필수 | 공고일 이후 |"
    may = "| 가상 확인서 | 선택 | 해당자 |"
    documents = [
        document(id="must", name="가상 등록증 사본", group=None, copies=None, issuer=None, quoteRefs=["must"]),
        document(id="may", name="가상 확인서", group=None, copies=None, issuer=None, quoteRefs=["may"]),
        document(id="given", name="가상 서약서", group="PROXY_OTHER", copies=None, issuer=None, quoteRefs=["may"]),  # AI 값은 그대로
    ]
    result = assembled(["[표 9-1]", header, must, may], {"must": "가상 등록증 사본", "may": "가상 확인서"}, documents=documents)
    by_id = {d["id"]: d["group"] for d in result.candidate["requiredDocuments"]}
    assert by_id["must"] == "COMMON" and by_id["may"] == "CONDITIONAL" and by_id["given"] == "PROXY_OTHER"
