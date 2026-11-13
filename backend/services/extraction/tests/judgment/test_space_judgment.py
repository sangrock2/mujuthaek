"""사업공간 판정 틀(business-space-judgment.v1): 수집기가 사업공간으로 분류한 K-Startup 모집을 코드로만 옮깁니다. AI 호출 없음."""

import copy

from mujuthaek_extraction.judgment.schema import frame_errors
from mujuthaek_extraction.judgment.space import build_space, posted_on
from mujuthaek_extraction.judgment.startup import UNREAD_TEXT

# 2026-10-22 수집 샘플(pbanc_sn 179465 관광기업지원센터(서울) 입주기업 모집)의 payload에서 판정에 쓰는 칸만
TOUR = {
    "rawPolicyId": "01a15220-1414-77c6-bd19-d459f8ad3c7b",
    "version": 2,
    "field": "SPACE_RECRUITMENT",
    "provider": "KSTARTUP",
    "agency": "한국관광공사",
    "text": (
        "제목: 2027년도 관광기업지원센터(서울) 신규 입주기업 모집\n기관: 한국관광공사\n[항목]\n접수 시작일: 20261007\n"
        "[원문 화면: https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179465]\n"
        "아래 내용과 붙임파일 참고하시어 많은 관심 부탁 드립니다.\n2026년 10월 07일\n한국관광공사\n신청방법 및 대상\n"
    ),
    "record": {
        "biz_enyy": "7년미만",
        "aply_trgt": "일반기업",
        "prfn_matr": None,
        "supt_regin": "서울",
        "biz_trgt_age": "만 20세 미만,만 20세 이상 ~ 만 39세 이하,만 40세 이상",
        "aply_trgt_ctnt": "- 관광과 관련한 창의적이고 지속가능한 사업을 영위하고 있는 공고일 기준 창업 7년 이내의 법인사업자 또는 개인사업자",
        "aply_excl_trgt_ctnt": (
            "- 공고일 기준 정부 지원사업에 참여제한으로 제재 중인 사업자\r\n- 금융기관으로부터 채무불이행으로 규제 중인 자 또는 휴/폐업 중인 사업자"
        ),
    },
}


def payload(**record):
    made = copy.deepcopy(TOUR)
    made["record"].update(record)
    return made


def test_tour_center_sample_becomes_a_business_space_frame():
    frame = build_space(TOUR)
    assert frame_errors(frame) == []
    assert (frame["rawPostId"], frame["rawVersion"], frame["referenceDate"]) == (TOUR["rawPolicyId"], 2, "2026-10-07")
    registered, under, target, detail, excluded = frame["common"]
    assert (registered["kind"], registered["require"]) == ("BUSINESS_REGISTRATION", "REGISTERED")
    # 사업공간 틀의 업력 칸은 「N개월 이상」뿐이라 「7년 미만」은 질문(틀이 정한 방법이라 확인 필요는 아님)
    assert (under["kind"], under["metWhen"], under["inReview"]) == ("ASK", "YES", False) and "7년" in under["question"]
    assert target["kind"] == "ASK" and "일반기업" in target["question"]
    assert (detail["inReview"], detail["reviewReason"], excluded["metWhen"], excluded["inReview"]) == (True, UNREAD_TEXT, "NO", True)
    assert "asOf" not in registered  # 사업공간 틀에는 asOf 칸이 없음


def test_reference_date_comes_only_from_the_posted_line_above_the_agency():
    assert posted_on("본문\n2026년 10월 07일\n한국관광공사\n", "한국관광공사") == "2026-10-07"
    assert posted_on("접수 시작일: 20261007\n신청기간 2026.10.07(수)", "한국관광공사") is None  # 접수 시작일로 채우지 않음
    assert posted_on("2026년 10월 07일\n다른기관\n", "한국관광공사") is None
    assert build_space({**TOUR, "text": "게시일 없음"}) is None  # 기준일이 없으면 틀을 만들지 않음


def test_student_target_has_no_space_status_code_so_it_is_asked():
    frame = build_space(payload(aply_trgt="대학생", aply_trgt_ctnt=None, aply_excl_trgt_ctnt=None, biz_enyy=None))
    assert frame_errors(frame) == []
    [target] = frame["common"]
    assert target["kind"] == "ASK" and "대학생" in target["question"]


def test_only_kstartup_space_recruitment():
    assert build_space({**TOUR, "field": "STARTUP_SUPPORT"}) is None
    assert build_space({**TOUR, "provider": "BIZINFO"}) is None
