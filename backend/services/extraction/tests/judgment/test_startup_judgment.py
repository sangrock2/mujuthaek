"""창업지원 판정 틀(startup-support-judgment.v1): K-Startup 구조화 칸을 코드로만 옮깁니다. AI 호출 없음."""

import copy

from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.judgment.startup import NO_REFERENCE_DATE, UNREAD_TEXT, build_startup

# 2026-10-22 수집 샘플(pbanc_sn 179525 워터라운드 제5기)의 raw.policy.collected payload에서 판정에 쓰는 칸만
WATEROUND = {
    "rawPolicyId": "01a15220-13e2-7373-95d8-fb3fdc5277a8",
    "version": 2,
    "field": "STARTUP_SUPPORT",
    "provider": "KSTARTUP",
    "record": {
        "biz_enyy": "예비창업자,1년미만,2년미만,3년미만,5년미만,7년미만,10년미만",
        "aply_trgt": "청소년,대학생,일반인,대학,연구기관,일반기업,1인 창조기업",
        "prfn_matr": None,
        "supt_regin": "전국",
        "biz_trgt_age": "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상",
        "aply_trgt_ctnt": (
            "워터라운드(wateRound) 플랫폼을 통해 기후테크·AI 융합 혁신 솔루션(SaaS)을 개발하여 서비스하고자 하는 기업(예비창업자 포함)\r\n"
            " * 예비창업자의 경우, 공모서류 제출 마감일 전까지 사업자등록 必\r\n"
            "** 旣 선정된 워터라운드 협약파트너 기업은 중복 지원 불가\r\n\r\n※ 자세한 사항은 첨부의 공고 참조"
        ),
        "aply_excl_trgt_ctnt": None,
    },
}


def payload(**record):
    made = copy.deepcopy(WATEROUND)
    made["record"].update(record)
    return made


def test_all_bands_mean_no_stage_age_or_target_condition_and_the_text_is_asked_in_review():
    frame = build_startup(WATEROUND)
    assert frame_errors(frame) == []
    assert (frame["rawPolicyId"], frame["rawVersion"], frame["referenceDate"]) == (WATEROUND["rawPolicyId"], 2, None)
    [detail] = frame["common"]
    assert (detail["kind"], detail["metWhen"], detail["inReview"], detail["reviewReason"]) == ("ASK", "YES", True, UNREAD_TEXT)
    assert "\r" not in detail["question"] and "중복 지원 불가" in detail["question"]
    assert frame["groups"] == [{"id": "all", "name": "전체", "criteria": []}] and frame["notes"] == []


def test_pre_founder_or_under_three_years_becomes_any_of_like_example_14():
    # 틀 예시 14(pbanc_sn 179540): 예비창업자,1년미만,3년미만 → 예비창업자 또는 창업 3년 미만
    frame = build_startup(payload(biz_enyy="예비창업자,1년미만,3년미만", aply_trgt_ctnt=None))
    assert frame_errors(frame) == []
    [stage] = frame["common"]
    pre, registered = stage["options"]
    assert stage["kind"] == "ANY_OF" and pre["criteria"][0]["require"] == "NOT_REGISTERED"
    assert registered["label"] == "창업 3년 미만" and registered["criteria"][0]["require"] == "REGISTERED"
    # 기준일이 없어(판정하는 날) 개업일 범위를 날짜로 정할 수 없어 업력은 질문 + 확인 필요
    under = registered["criteria"][1]
    assert (under["kind"], under["inReview"], under["reviewReason"]) == ("ASK", True, NO_REFERENCE_DATE)


def test_only_pre_founder_or_only_years():
    [pre] = build_startup(payload(biz_enyy="예비창업자", aply_trgt_ctnt=None))["common"]
    assert (pre["kind"], pre["require"]) == ("BUSINESS_REGISTRATION", "NOT_REGISTERED")
    registered, under = build_startup(payload(biz_enyy="1년미만,7년미만", aply_trgt_ctnt=None))["common"]
    assert registered["require"] == "REGISTERED" and "7년" in under["question"]


def test_age_bands_are_merged_and_a_gap_becomes_any_of():
    [age] = build_startup(payload(biz_trgt_age="만 20세 미만,만 20세 이상 ~ 만 39세 이하", aply_trgt_ctnt=None))["common"]
    assert (age["kind"], age["minAge"], age["maxAge"]) == ("AGE", None, 39)
    frame = build_startup(payload(biz_trgt_age="만 20세 미만,만 40세 이상", aply_trgt_ctnt=None))
    assert frame_errors(frame) == []
    [either] = frame["common"]
    assert [o["criteria"][0]["minAge"] for o in either["options"]] == [None, 40]


def test_target_without_general_public():
    [status] = build_startup(payload(aply_trgt="대학생", aply_trgt_ctnt=None))["common"]
    assert (status["kind"], status["anyOf"]) == ("STATUS", ["STUDENT"])
    [ask] = build_startup(payload(aply_trgt="대학생,일반기업", aply_trgt_ctnt=None))["common"]
    assert ask["kind"] == "ASK" and not ask["inReview"] and "일반기업" in ask["question"]


def test_exclusion_text_is_a_limit_question_and_preferences_are_notes():
    frame = build_startup(payload(aply_trgt_ctnt=None, aply_excl_trgt_ctnt="국세 체납 기업", prfn_matr="여성기업 우대"))
    assert frame_errors(frame) == []
    [excluded] = frame["common"]
    assert (excluded["metWhen"], excluded["inReview"]) == ("NO", True)
    assert frame["notes"][0]["text"] == "우대 사항: 여성기업 우대"


def test_other_sources_and_unknown_band_values_have_no_frame():
    assert build_startup({**WATEROUND, "provider": "BIZINFO"}) is None  # 기업마당은 구간 칸이 없어 글을 읽어야 함
    assert build_startup({**WATEROUND, "field": "BENEFIT"}) is None
    assert build_startup(payload(biz_enyy="예비창업자,15년미만")) is None
