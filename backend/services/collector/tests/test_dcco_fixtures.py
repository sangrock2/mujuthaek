"""대전 실제 화면(tests/fixtures/dcco, 2026-10-15 저장)으로 분류·첨부 고르기를 고정해요."""

from pathlib import Path

import pytest

from mujuthaek_collector.core import classify as cls
from mujuthaek_collector.core.files import pick_notice_files, pick_unit_lists
from mujuthaek_collector.sources.base import ListItem
from mujuthaek_collector.sources.registry import SOURCES

FIXTURES = Path(__file__).parent / "fixtures" / "dcco"
pytestmark = pytest.mark.skipif(not (FIXTURES / "43-list.html").exists(), reason="대전 저장 화면이 없어요")
SOURCE = SOURCES["dcco"]


def kinds(board_key):
    board = next(b for b in SOURCE.boards if b.key == board_key)
    items = SOURCE.parse_list(board, (FIXTURES / f"{board_key}-list.html").read_text(encoding="utf-8"), "")
    return {i.post_key: SOURCE.pre_classify(i) or cls.classify(i.title) for i in items}


def test_rent_board_kinds():
    found = kinds("43")
    assert found["43-24812"] == cls.NOTICE  # 2026년 2차 영구임대아파트 예비입주자 모집공고
    assert found["43-24807"] == cls.EXCLUDED  # 기존주택(청년임대) 3차 매입공고 — [모집공고] 머리말이 있어도 제외
    assert found["43-24810"] == cls.FOLLOW_UP  # [공고결과]


def test_sale_board_has_only_land_and_shops():
    assert set(kinds("37").values()) == {cls.EXCLUDED}  # 분양 게시판은 지금 토지·상가 글뿐이에요


def test_notice_detail_picks_one_document_and_no_result_lists():
    detail = SOURCE.parse_detail(ListItem("43", "43-24812", "", None, None), (FIXTURES / "43-detail-43-24812.html").read_text(encoding="utf-8"))
    assert [f.ext for f in pick_notice_files(detail.files)] == ["pdf", "hwp"]  # PDF 먼저, 실패하면 HWP
    result = SOURCE.parse_detail(ListItem("43", "43-24809", "", None, None), (FIXTURES / "43-detail-43-24809.html").read_text(encoding="utf-8"))
    assert pick_notice_files(result.files) == [] and pick_unit_lists(result.files) == []
    assert "조회" not in detail.body_text  # 본문에 매번 바뀌는 값이 없어야 다시 확인할 때 새 버전이 안 생겨요
