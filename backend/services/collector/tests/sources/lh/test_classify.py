"""LH 분류: 공고 유형 칸으로 나누고, 파이프라인 종류(NOTICE·CORRECTION·EXCLUDED)로 바꿔요."""

import pytest

from mujuthaek_collector.core import classify as team
from mujuthaek_collector.sources.lh.classify import classify, classify_title


def row(title, upper="임대주택", kind="국민임대"):
    return {"PAN_NM": title, "UPP_AIS_TP_NM": upper, "AIS_TP_CD_NM": kind}


@pytest.mark.parametrize(
    ("r", "kind", "category"),
    [
        (row("태백소도 국민임대주택 예비입주자 상시모집"), "모집공고", "임대"),
        (row("[정정공고]대구연호 A-2BL 통합공공임대주택 입주자 모집"), "정정공고", "임대"),
        (row("[취소공고]태백철암1 국민임대주택 예비입주자 모집 공고"), "취소공고", "임대"),
        (row("청주지북B1블록 공공분양 잔여세대", "분양주택", "분양주택"), "모집공고", "분양"),
        (row("창녕영산 1BL 행복주택 예비입주자 모집", "분양주택", "행복주택"), "모집공고", "임대"),
        (row("양산시 매입임대 잔여주택 일반매각 공고", "임대주택", "매입임대"), "모집공고", "분양"),
        (row("광주선운2 신혼희망타운", "공공분양(신혼희망)", "공공분양(신혼희망)"), "모집공고", "분양"),
    ],
)
def test_housing_notices(r, kind, category):
    c = classify(r)
    assert (c.kind, c.category) == (kind, category)


@pytest.mark.parametrize(
    ("r", "reason"),
    [
        (row("○○지구 공동주택용지 공급", "토지", "공동주택용지"), "택지·용지 공급"),
        (row("○○ 임대상가 입찰", "상가", "임대상가"), "사업공간(상가) - 수집 범위 밖 (INCLUDE_BUSINESS=False)"),
        (row("2026년 기존주택 매입 신청 공고"), "제목 '주택 매입 신청'"),
        (row("○○ 운영자 모집"), "제목 '운영자 모집'"),
        (row("기타 공고", "기타", "기타"), "공고 유형 '기타'"),
    ],
)
def test_excluded_notices(r, reason):
    c = classify(r)
    assert (c.kind, c.reason, c.pipeline_kind) == ("제외", reason, team.EXCLUDED)


def test_pipeline_kind_opens_only_recruitment_and_correction():
    assert classify(row("모집공고")).pipeline_kind == team.NOTICE
    assert classify(row("[정정공고] 모집")).pipeline_kind == team.CORRECTION
    assert classify(row("[취소공고] 모집")).pipeline_kind == team.EXCLUDED  # 이벤트 계약에 취소 종류가 없어서 열지 않아요


def test_business_space_can_be_switched_on():
    c = classify(row("○○ 임대상가 입찰", "상가", "임대상가"), include_business=True)
    assert (c.kind, c.category) == ("모집공고", "사업공간")


def test_myhome_only_notices_are_classified_by_title():
    assert classify_title("[정정공고][선착순 동·호지정] 영천문외 센트럴타운 공공분양주택 추가입주자").pipeline_kind == team.CORRECTION
    assert classify_title("[청년신혼부부매입임대리츠주택] 충남당진 송산청광플러스원 입주자격완화 상시").pipeline_kind == team.NOTICE


@pytest.mark.parametrize(
    ("title", "upper", "team_kind"),
    [
        ("구미화성파크드림 미분양매입 잔여세대 선착순 일반매각 공고", "분양주택", team.EXCLUDED),
        ("인천영종 A33·37·60블록 공공분양 잔여세대 입주자모집공고(순번추첨 동호지정)", "분양주택", team.FOLLOW_UP),
    ],
)
def test_why_lh_does_not_use_the_title_only_classifier(title, upper, team_kind):
    # 공통 분류기(제목만 봄)는 LH 매각 공고를 제외로, '순번추첨'이 든 모집공고를 후속 안내로 봐요
    assert team.classify(title) == team_kind
    assert classify(row(title, upper, upper)).pipeline_kind == team.NOTICE
