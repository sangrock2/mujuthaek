"""정책 판정 이벤트의 원문 주소·상시 모집 여부·접수 기간·검수 상태(리뷰 2026-10-23, PR #70). 합성 값만 씁니다."""

import json

from test_policy_judgment import REGIONS, TOUR_ANSWER, FakeStore, reading, tour
from test_publish import EVENT_SCHEMA, envelope

from mujuthaek_extraction.contracts import tools
from mujuthaek_extraction.judgment.policy_frame import JUDGING_DATE_NOTE
from mujuthaek_extraction.model import ModelError, RecordedModel
from mujuthaek_extraction.publish import (
    policy_apply_always,
    policy_apply_note,
    policy_apply_period,
    policy_completed_payload,
    policy_detail_url,
    policy_frame,
    policy_frame_detail,
    policy_review_status,
)
from mujuthaek_extraction.rules.policy.reading import CALL_NAME
from mujuthaek_extraction.worker import judge_policy


def youth(**record):
    """온통청년 사업공간 모집(합성): K-Startup 날짜 칸 없이 신청 기간(aplyYmd)·신청 기간 구분(aplyPrdSeCd)만."""
    return tour() | {"provider": "YOUTHCENTER", "sourceCode": "youth", "record": record}


def frame(*criteria, notes=()):
    return {"common": list(criteria), "groups": [{"id": "all", "name": "전체", "criteria": []}], "preferences": [], "notes": list(notes)}


def criterion(in_review, **more):
    return {"kind": "BUSINESS_REGISTRATION", "id": "c1", "inReview": in_review, **more}


def test_detail_url_is_the_collected_original_link_unless_private_or_not_a_uri():
    assert policy_detail_url(tour() | {"detailUrl": "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch/ythPlcyDetail/R1"}).endswith("/R1")
    for bad in (
        None,
        "",
        "javascript:alert(1)",
        "/relative/path",
        "https://example.go.kr/view?serviceKey=abc",
        "https://user:pw@example.go.kr/",
        "https://example.go.kr/공고 1",
    ):
        assert policy_detail_url(tour() | {"detailUrl": bad}) is None, bad


def test_apply_period_reads_youth_and_bizinfo_period_text_only_when_it_is_one_range():
    assert policy_apply_period(youth(aplyYmd="20261012 ~ 20261130")) == ("2026-10-12", "2026-11-30")
    assert policy_apply_period(youth(reqstBeginEndDe="2026-10-16 ~ 2026-11-03")) == ("2026-10-16", "2026-11-03")
    # K-Startup 날짜 칸이 있으면 그것
    assert policy_apply_period(youth(pbanc_rcpt_bgng_dt="20261019", pbanc_rcpt_end_dt="20261102", aplyYmd="20260101 ~ 20260102")) == (
        "2026-10-19",
        "2026-11-02",
    )
    # 여러 구간·날짜 아닌 글·없는 날짜·거꾸로 된 기간은 모름(틀린 날짜보다 모름)
    for text in ("20260101 ~ 20260131\n20260301 ~ 20260331", "예산 소진 시까지", "20261340 ~ 20261401", "20261130 ~ 20261001", "상시"):
        assert policy_apply_period(youth(aplyYmd=text)) == (None, None), text
    assert policy_apply_period(youth()) == (None, None)


def test_apply_always_only_when_the_source_says_so_in_its_period_fields():
    assert policy_apply_always(youth(aplyPrdSeCd="0057002"))
    for text in ("상시", "상시 접수", "연중 수시 모집", "(상시모집)"):
        assert policy_apply_always(youth(aplyYmd=text)), text
    assert policy_apply_always(youth(reqstBeginEndDe="수시 접수"))
    assert not policy_apply_always(youth(aplyPrdSeCd="0057001", aplyYmd="20261012 ~ 20261130"))
    assert not policy_apply_always(youth(aplyPrdSeCd="0057003"))  # 기간 칸 없음(계속·별도 안내)은 상시가 아님
    assert not policy_apply_always(youth(aplyYmd="예산 소진 시까지"))
    assert not policy_apply_always(youth(aplyYmd="상시 모집 후 20261130 마감"))
    # 제목의 「상시 모집」은 쓰지 않음(일부 모집·지난 안내일 수 있음)
    assert not policy_apply_always(youth() | {"title": "2026년 공유형 공간 신규 입주기업 상시 모집"})


def test_apply_note_only_when_the_whole_period_field_says_until_budget_runs_out():
    # 실측(2026-10-28 기업마당 연천군 중소기업 육성자금): 신청 기간 칸이 「예산 소진시까지」라 마감일이 없고 상시도 아니어서 목록에서 빠졌음
    for text in ("예산 소진시까지", "예산 소진 시까지", "(자금 소진 시 마감)", "예산 소진 시까지 접수"):
        assert policy_apply_note(youth(reqstBeginEndDe=text)) == "예산 소진 시까지", text
    assert policy_apply_note(youth(aplyYmd="예산 소진 시까지")) == "예산 소진 시까지"
    assert not policy_apply_always(youth(aplyYmd="예산 소진 시까지"))  # 상시 모집은 아님(언제든 끝날 수 있음)
    for text in ("20261012 ~ 20261130", "상시", "예산 소진 시까지, 20261130 마감", ""):
        assert policy_apply_note(youth(aplyYmd=text)) is None, text
    assert policy_apply_note(youth(aplyPrdSeCd="0057002", aplyYmd="예산 소진 시까지")) is None  # 상시면 상시로


def test_review_status_follows_the_whole_frame():
    assert policy_review_status(frame(criterion(False))) == "AUTO_PASSED"
    assert policy_review_status(frame(criterion(True))) == "PARTIALLY_PASSED"
    nested = criterion(False, options=[{"criteria": [criterion(True)]}])
    assert policy_review_status(frame(nested)) == "PARTIALLY_PASSED"
    judging = {"kind": "OTHER", "group": None, "text": f"{JUDGING_DATE_NOTE} 2026-11-05", "quote": None}
    assert policy_review_status(frame(criterion(False), notes=[judging])) == "PARTIALLY_PASSED"  # 선택 B: 판정일을 기준일로
    assert policy_review_status(frame(criterion(False)), by_rules=True) == "IN_REVIEW"  # 구간 칸 규칙 틀은 틀 전체를 믿을 수 없음


def test_policy_event_carries_detail_url_apply_always_and_youth_period():
    payload = youth(aplyYmd="20261012 ~ 20261130", aplyPrdSeCd="0057001") | {"detailUrl": "https://www.youthcenter.go.kr/youthPolicy/R1"}
    event = policy_completed_payload(payload, policy_frame(payload, reading(TOUR_ANSWER), REGIONS), REGIONS)
    assert tools().validate(envelope(event), EVENT_SCHEMA) == []
    assert event["detailUrl"] == "https://www.youthcenter.go.kr/youthPolicy/R1" and event["applyAlways"] is False
    assert event["schedule"] == {"applyStartOn": "2026-10-12", "applyEndOn": "2026-11-30"}
    always = youth(aplyPrdSeCd="0057002") | {"detailUrl": None}
    event = policy_completed_payload(always, policy_frame(always, reading(TOUR_ANSWER), REGIONS), REGIONS)
    assert tools().validate(envelope(event), EVENT_SCHEMA) == []
    assert event["detailUrl"] is None and event["applyAlways"] is True and event["schedule"] is None


def test_band_rule_frame_after_ai_failure_is_in_review_and_ai_frame_is_not():
    made, reason, by_rules = policy_frame_detail(tour(), reading(TOUR_ANSWER), REGIONS)
    assert made is not None and reason is None and not by_rules
    made, _, by_rules = policy_frame_detail(tour(), None, REGIONS)  # AI 읽기 없음 → 구간 칸 규칙 틀
    assert made is not None and by_rules
    store = FakeStore()
    failed = RecordedModel({CALL_NAME: [ModelError("형식이 틀린 답", transient=False, code="BAD_SHAPE")]})
    assert judge_policy(store, {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1881", "payload": tour()}, failed, REGIONS)
    assert store.saved[-1]["payload"]["reviewStatus"] == "IN_REVIEW"
    read = RecordedModel({CALL_NAME: [json.dumps(TOUR_ANSWER)]})
    assert judge_policy(store, {"eventId": "01a16146-b9b3-704f-8da4-54c2dcfa1882", "payload": tour()}, read, REGIONS)
    assert store.saved[-1]["payload"]["reviewStatus"] in ("AUTO_PASSED", "PARTIALLY_PASSED")
