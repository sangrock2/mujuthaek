"""공통 검사(2026-10-26 원문 대조): AI가 쓴 글에 원문에 없는 가나·한자가 섞이면 그 칸의 항목을 검수로 보냅니다.
합성 자료만 씁니다. AI·네트워크 호출 없음."""

from mujuthaek_extraction.verify.model import SourceBundle
from mujuthaek_extraction.verify.verifier import check_foreign_script, held_target


def candidate():
    return {
        "notice": {"title": "가상 행복주택 모집"},
        "schedules": [{"id": "s1", "description": "入주 개시일은 따로 알려요"}],
        "requiredDocuments": [
            {"id": "d1", "name": "주민등록표등본", "description": "수령내역など 증빙する 서류"},
            {"id": "d2", "name": "가족관계증명서", "description": "國家 유공자 확인"},
        ],
        "evidence": [{"id": "e1", "quote": "原文 인용은 보지 않아요"}],
        "quality": {"notes": [{"description": "検査 기록은 보지 않아요"}]},
    }


def test_foreign_letters_absent_from_the_source_are_flagged_where_they_are():
    sources = SourceBundle(texts={"t": "가상 행복주택 모집 공고. 국가유공자(國家有功者) 확인 서류"})
    found = {(f.code, f.target) for f in check_foreign_script(candidate(), sources)}
    assert found == {
        ("AI_TEXT_FOREIGN_SCRIPT", "/schedules/0/description"),
        ("AI_TEXT_FOREIGN_SCRIPT", "/requiredDocuments/0/description"),
    }


def test_the_flag_holds_only_the_item_that_has_the_text():
    c = candidate()
    for f in check_foreign_script(c, SourceBundle(texts={"t": "國家"})):
        assert held_target(c, f.target) in {("/schedules/0", "ITEM"), ("/requiredDocuments/0", "ITEM")}


def test_korean_only_text_is_not_flagged():
    c = {"notice": {"title": "가상 공고"}, "schedules": [{"description": "접수 기간: 11월 3일 ~ 11월 4일 (09:00~16:00)"}]}
    assert check_foreign_script(c, SourceBundle(texts={"t": ""})) == []
