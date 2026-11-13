"""원문 안 충돌(2026-10-26 원문 대조): 같은 자격의 판단 기준일이 원문에서 엇갈리면 공개한 채 검수로 보냅니다.
합성 자료만 씁니다. AI·네트워크 호출 없음."""

from mujuthaek_extraction.store import _dropped_reasons
from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.verifier import check_basis_date_conflict, is_note

CANDIDATE = {"eligibility": [{"id": "e1", "description": "무주택세대구성원"}]}


def check(text: str):
    return check_basis_date_conflict(CANDIDATE, SourceBundle(texts={"t": text}))


def test_two_basis_dates_for_the_same_criterion_are_flagged():
    text = (
        "• (기준일) 입주자 모집공고일(2026.08.21.)이 입주자격 판단 기준일이 됩니다.\n"
        "• (신청자격) 신청일 현재 무주택세대구성원으로서 소득·자산 기준을 충족하여야 합니다.\n"
    )
    [finding] = check(text)
    assert finding.code == "SOURCE_BASIS_DATE_CONFLICT" and finding.target == "/eligibility"
    assert "무주택: 공고일·신청일" in finding.description
    # 공개는 유지하고(보류하지 않는 메모) 검수 대기열에는 올라가요
    issue = finding.issue()
    assert is_note(issue)
    assert _dropped_reasons({"quality": {"notes": [issue], "reviewIssues": []}}) == ["SOURCE_BASIS_DATE_CONFLICT /eligibility"]


def test_different_dates_for_different_items_are_not_a_conflict():
    text = (
        "• 임대보증금 및 월 임대료는 입주자모집공고일 현재 기준입니다.\n"
        "• 중소기업기본법에 따른 중소기업이고, 신청일 기준 연천군에 있어야 합니다.\n"
        "• 공고일 현재 무주택세대구성원이어야 합니다.\n"
    )
    assert check(text) == []


def test_notices_without_eligibility_are_skipped():
    assert check_basis_date_conflict({"eligibility": []}, SourceBundle(texts={"t": "공고일 현재 무주택. 신청일 현재 무주택."})) == []
