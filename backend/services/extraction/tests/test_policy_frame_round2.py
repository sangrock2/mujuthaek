"""정책 판정 틀 검사 2차(사업공간 2차 채점 뒤 일반 규칙): 제외 문장의 답 방향, 제외 단락 배치, 첨부·미정의 용어,
예외 표시 범위·질문 합치기·「예비창업자 또는 X」. 지어낸 공고 글로만 시험합니다."""

import json

from test_policy_frame_checks import frame_of
from test_policy_judgment import answer, condition, tour

from mujuthaek_extraction.judgment.policy_frame import (
    ATTACHED,
    COMMON_EXCLUSION,
    DIRECTION,
    DIRECTION_CONFLICT,
    EMPTY_GROUP,
    EXCEPTION,
    MERGED_QUESTION,
    SCOPE,
    UNDEFINED,
    exclusion_heading,
)
from mujuthaek_extraction.model import RecordedModel
from mujuthaek_extraction.rules.policy.reading import CALL_NAME, SYSTEM, read_policy

TWO_GROUPS = [
    {"key": "pre", "name": "예비창업자", "quote": "사업자 등록 전인 개인"},
    {"key": "biz", "name": "기창업자", "quote": "창업 5년 이내 기업"},
]


def ask_of(made, part="common"):
    found = made[part] if part == "common" else [c for g in made["groups"] for c in g["criteria"]]
    return [c for c in found if c["kind"] == "ASK"]


# 1. 제외 문장의 답 방향


def test_question_from_an_exclusion_paragraph_confirmed_with_yes_is_held_and_not_flipped():
    text = "모집 제외\n- 영업을 멈춘 상태의 사업자\n- 가맹점 운영자는 신청 불가\n"
    stopped = condition("OTHER", "영업을 멈춘 상태의 사업자", question="영업을 멈춘 상태인가요?", metWhen="YES")
    [asked] = frame_of([stopped], text)["common"]
    assert asked["metWhen"] == "YES" and asked["inReview"] and DIRECTION in asked["reviewReason"]
    # 근거 문장 안의 제외 낱말(「신청 불가」)도 제외 문장
    chain = condition("OTHER", "가맹점 운영자는 신청 불가", question="가맹점을 운영하나요?", metWhen="YES")
    assert DIRECTION in frame_of([chain], text)["common"][0]["reviewReason"]
    # 부정 질문이면 「예」가 충족이어도 방향이 맞음
    negated = condition("OTHER", "영업을 멈춘 상태의 사업자", question="영업을 멈춘 상태가 아닌가요?", metWhen="YES")
    assert not frame_of([negated], text)["common"][0]["inReview"]
    # 「예」면 탈락(NO)은 그대로 확정
    right = condition("OTHER", "영업을 멈춘 상태의 사업자", question="영업을 멈춘 상태인가요?", metWhen="NO")
    assert not frame_of([right], text)["common"][0]["inReview"]


def test_question_under_an_application_heading_keeps_its_yes_direction():
    text = "응모 자격\n- 영업을 멈춘 적이 있는 재도전 사업자\n"
    retry = condition("OTHER", "영업을 멈춘 적이 있는 재도전 사업자", question="영업을 멈춘 적이 있나요?", metWhen="YES")
    assert not frame_of([retry], text)["common"][0]["inReview"]


def test_exclusion_heading_is_found_inline_or_above_until_another_heading():
    text = "응모 제외 대상: ‧ 영업을 멈춘 사업자\n‧ 세금을 미룬 사업자\n※ 단, 나눠 내는 중이면 가능\n응모 자격\n- 공방을 운영하는 사업자\n"
    assert exclusion_heading("영업을 멈춘 사업자", text) == "응모제외대상"
    assert exclusion_heading("세금을 미룬 사업자", text) == "응모제외대상"
    assert exclusion_heading("공방을 운영하는 사업자", text) is None
    # 항목처럼 보이는 줄(「각종 …대상자」)은 머리말이 아님
    assert exclusion_heading("공방 이력이 있는 회사", "제외 대상\n여러 법적 처분 대상자\n공방 이력이 있는 회사\n") == "제외대상"


def test_question_whose_quote_also_made_a_coded_exclusion_is_held_when_directions_disagree():
    text = "응모 안내\n- 휴업 또는 폐업한 사업자\n"
    conditions = [
        condition("EXCLUDED_STATUS", "휴업 또는 폐업한 사업자", excludedCodes=["BUSINESS_SUSPENDED"]),
        condition("OTHER", "휴업 또는 폐업한 사업자", question="폐업한 상태인가요?", metWhen="YES"),
    ]
    coded, asked = frame_of(conditions, text)["common"]
    assert not coded["inReview"] and asked["metWhen"] == "YES"
    assert asked["inReview"] and DIRECTION_CONFLICT in asked["reviewReason"]


def test_negative_part_of_a_qualification_sentence_is_not_an_exclusion():
    quote = "공유오피스 회원이면서 다른 센터에 입주하지 않은 자"
    conditions = [
        condition("OTHER", quote, question="공유오피스 회원인가요?", metWhen="YES"),
        condition("OTHER", quote, question="다른 센터에 입주해 있나요?", metWhen="NO"),
    ]
    made = frame_of(conditions, "응모 자격\n- " + quote + "\n")["common"]
    assert [c["inReview"] for c in made] == [False, False]


def test_same_question_from_the_same_quote_is_asked_once():
    quote = "공방을 운영하는 사업자"
    same = condition("OTHER", quote, question="공방을 운영하나요?", metWhen="YES")
    assert len(frame_of([same, same], "응모 자격\n" + quote + "\n")["common"]) == 1


# 2. 제외 단락 항목의 대상군 배치


def test_exclusion_item_from_a_common_paragraph_attached_to_one_group_moves_to_common():
    # 3차(리뷰 2026-10-23): 확인 필요로만 두면 다른 대상군 신청자에게 그 제외가 걸리지 않아 공통으로 옮김
    text = "사업자 등록 전인 개인\n창업 5년 이내 기업\n지원 제외 대상\n- 이 센터를 졸업한 이력이 있는 회사\n"
    item = condition("OTHER", "이 센터를 졸업한 이력이 있는 회사", group="biz", question="이 센터를 졸업했나요?", metWhen="NO")
    pre = condition("PRE_FOUNDER", "사업자 등록 전인 개인", group="pre")
    made = frame_of([pre, item], text, groups=TWO_GROUPS)
    # 제외를 옮겨 비게 된 대상군은 누구나 통과하지 않게 대상군 질문(확인 필요)으로 채움(4차)
    [asked] = made["groups"][1]["criteria"]
    assert (asked["kind"], asked["metWhen"], asked["inReview"]) == ("ASK", "YES", True) and EMPTY_GROUP in asked["reviewReason"]
    [moved] = made["common"]
    assert (moved["question"], moved["metWhen"], moved["inReview"]) == ("이 센터를 졸업했나요?", "NO", False)
    # 택1 길 안이면 옮기지 않고 확인 필요
    paths = [item | {"anyOf": "a", "option": "1"}, condition("REGISTERED", "창업 5년 이내 기업", group="biz", anyOf="a", option="2")]
    [either] = frame_of([pre, *paths], text, groups=TWO_GROUPS)["groups"][1]["criteria"]
    held = either["options"][0]["criteria"][0]
    assert held["inReview"] and COMMON_EXCLUSION in held["reviewReason"]
    # 머리말이나 문장이 대상군을 지목하면 그대로
    scoped = text.replace("지원 제외 대상", "기창업자 제외 대상")
    assert not frame_of([pre, item], scoped, groups=TWO_GROUPS)["groups"][1]["criteria"][0]["inReview"]
    # 대상군이 하나면 대상군과 공통이 같음
    assert not frame_of([item], text, groups=TWO_GROUPS[1:])["groups"][0]["criteria"][0]["inReview"]


# 3. 첨부·미정의 용어


def test_terms_defined_only_in_attachments_or_nowhere_are_held():
    text = "응모 자격\n- 미래 분야(붙임 2 참조) 기업\n- 모집 자격을 충족하는 회원사\n- 녹색 업종 기업 (공고문 3쪽 참조)\n- 공방을 운영하는 사업자\n"
    future = condition("OTHER", "미래 분야(붙임 2 참조) 기업", question="미래 분야 기업인가요?", metWhen="YES")
    assert ATTACHED in frame_of([future], text)["common"][0]["reviewReason"]
    # 근거 밖 같은 줄의 「(공고문 3쪽 참조)」도 봄
    green = condition("OTHER", "녹색 업종 기업", question="녹색 업종 기업인가요?", metWhen="YES")
    assert ATTACHED in frame_of([green], text)["common"][0]["reviewReason"]
    member = condition("OTHER", "모집 자격을 충족하는 회원사", question="모집 자격을 충족하는 회원사인가요?", metWhen="YES")
    assert UNDEFINED in frame_of([member], text)["common"][0]["reviewReason"]
    # AI가 정의 없음으로 읽은 분야
    craft = condition("OTHER", "공방을 운영하는 사업자", question="공방을 운영하나요?", metWhen="YES", defined=False)
    assert UNDEFINED in frame_of([craft], text)["common"][0]["reviewReason"]
    assert not frame_of([craft | {"defined": True}], text)["common"][0]["inReview"]
    # 값 조건(업력)은 같은 줄에 첨부 참조가 있어도 이 사유로 잡지 않음
    years = condition("BUSINESS_AGE", "녹색 업종 기업 (공고문 3쪽 참조)", years=3, yearsRule="WITHIN")
    reason = frame_of([years], text + "녹색 업종 기업 (공고문 3쪽 참조) 창업 3년 이내\n")["common"][0]["reviewReason"] or ""
    assert ATTACHED not in reason


# 4. 예외 표시 범위 · 질문 합치기 · 「예비창업자 또는 X」


def test_exception_mark_stays_on_the_condition_the_exception_talks_about():
    quote = "창업 5년 이내 법인 (단, 업력 2년 초과는 별도 심사)"
    conditions = [condition("REGISTERED", quote), condition("BUSINESS_AGE", quote, years=5, yearsRule="WITHIN")]
    registered, years = frame_of(conditions, quote + "\n", startup=True)["common"]
    assert not registered["inReview"]
    assert years["inReview"] and EXCEPTION in years["reviewReason"]
    # 예외가 어느 조건도 말하지 않으면 모두에
    vague = "창업 5년 이내 법인 (단, 센터장이 인정하면 가능)"
    both = frame_of([condition("REGISTERED", vague), condition("BUSINESS_AGE", vague, years=5, yearsRule="WITHIN")], vague + "\n", startup=True)
    assert all(EXCEPTION in c["reviewReason"] for c in both["common"])


def test_two_questions_joined_into_one_keep_the_first_and_one_answer_direction():
    text = "응모 제외 대상\n- 세금을 미룬 사업자\n※ 단, 나눠 내는 중이면 신청 가능\n"
    joined = condition("OTHER", "세금을 미룬 사업자", question="세금을 미뤘나요? 단, 나눠 내는 중이면 신청할 수 있나요?", metWhen="NO")
    [asked] = frame_of([joined], text)["common"]
    assert asked["question"].count("?") == 1 and asked["question"].startswith("세금을 미뤘나요?")
    assert "나눠 내는 중이면" in asked["question"] and "'아니오'" in asked["question"]
    assert MERGED_QUESTION in asked["reviewReason"] and EXCEPTION in asked["reviewReason"]


def test_sentence_naming_pre_founders_and_another_applicant_is_not_pre_founder_only():
    quote = "예비창업자 또는 협동조합으로 다른 일을 겸하지 않는 자"
    groups = [{"key": "pre", "name": "예비창업자", "quote": quote}, {"key": "coop", "name": "협동조합", "quote": quote}]
    conditions = [
        condition("PRE_FOUNDER", quote, group="pre"),
        condition("OTHER", quote, question="다른 일을 겸하고 있나요?", metWhen="NO"),
    ]
    [asked] = frame_of(conditions, "응모 자격\n" + quote + "\n", groups=groups)["common"]
    assert not asked["inReview"]
    scoped = "예비창업자의 경우 다른 일을 겸하지 않는 자"
    narrow = [condition("PRE_FOUNDER", quote, group="pre"), condition("OTHER", scoped, question="다른 일을 겸하고 있나요?", metWhen="NO")]
    [held] = frame_of(narrow, "응모 자격\n" + quote + "\n" + scoped + "\n", groups=groups)["common"]
    assert held["inReview"] and SCOPE in held["reviewReason"]


# 5. 프롬프트 v6


def test_prompt_v6_rules_and_answers_with_or_without_defined():
    for rule in ("metWhen NO입니다", "물음표 하나", "제출서류·유의사항", "group null(공통)입니다", "가장 낮은 단계까지 이름 하나", "defined"):
        assert rule in SYSTEM
    with_field = answer([condition("OTHER", "공방을 운영하는 사업자", question="공방을 운영하나요?", metWhen="YES", defined=False)])
    for made in (answer([condition("OTHER", "공방을 운영하는 사업자", question="공방을 운영하나요?", metWhen="YES")]), with_field):
        model = RecordedModel({CALL_NAME: [json.dumps(made)]})
        assert read_policy(tour() | {"text": "공방을 운영하는 사업자\n"}, model).answer == made
