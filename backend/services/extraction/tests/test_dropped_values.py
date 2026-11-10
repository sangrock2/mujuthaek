"""공통 검사(2026-10-26 사용자 결정 「모두 검수, 공개 유지」): AI·원본 값을 비우거나 빼거나 바꾼 공고는 공개한 채 검수 대기열로.
합성 자료만 씁니다. AI·네트워크 호출 없음."""

from mujuthaek_extraction.recheck import lost_by_recheck
from mujuthaek_extraction.store import _dropped_reasons


def candidate(notes=(), issues=()):
    return {"quality": {"notes": list(notes), "reviewIssues": list(issues), "heldItems": []}}


def test_any_dropped_value_code_sends_the_notice_to_review_wherever_it_is():
    dropped = candidate(notes=[{"code": "ITEM_DROPPED_NO_EVIDENCE", "target": "/supplyGroups/0/prices/1", "description": "근거 없음"}])
    assert _dropped_reasons(dropped) == ["ITEM_DROPPED_NO_EVIDENCE /supplyGroups/0/prices/1"]
    changed = candidate(issues=[{"code": "AI_OUTPUT_VALUE_CHANGED", "target": "/notice/counts/0", "description": "묶음 풀기"}])
    assert _dropped_reasons(changed) == ["AI_OUTPUT_VALUE_CHANGED /notice/counts/0"]
    # 값을 버리지 않은 메모(근거 위치 고르기 등)는 검수로 보내지 않아요
    assert _dropped_reasons(candidate(notes=[{"code": "EVIDENCE_AMBIGUOUS", "target": "/schedules/0", "description": "x"}])) == []
    assert _dropped_reasons(None) == []


def test_values_lost_when_a_recheck_answer_replaces_an_item_are_reported():
    before = [
        {"supplyGroups": [{"id": "g1", "houseType": "26A", "areaM2": 26.3, "quoteRefs": ["q1"]}], "notice": {"title": "가상 공고", "postedOn": "2026-10-01"}}
    ]
    after = [{"supplyGroups": [{"id": "g1", "houseType": "26A", "areaM2": None, "quoteRefs": ["r1"]}], "notice": {"title": "가상 공고"}}]
    lost = dict(lost_by_recheck(before, after))
    assert "/supplyGroups" in lost and "areaM2" in lost["/supplyGroups"]
    assert "/notice" in lost and "postedOn" in lost["/notice"]
    # 근거 참조만 바뀌거나 값이 그대로면 아무것도 없어요
    assert lost_by_recheck(before, before) == []
