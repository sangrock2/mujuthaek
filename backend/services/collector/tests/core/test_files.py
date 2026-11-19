from mujuthaek_collector.core.files import FileRef, pick_notice_files, pick_unit_lists, unclear_notice


def refs(*names):
    return [FileRef(name, f"https://a.kr/f/{i}", i) for i, name in enumerate(names)]


def test_notice_doc_prefers_named_pdf_and_skips_personal_files():
    files = refs("신청서 양식.hwp", "입주자 모집공고문.hwp", "입주자 모집공고문.pdf", "당첨자 명단.pdf", "위치도.pdf")
    picked = pick_notice_files(files)
    assert [f.name for f in picked] == ["입주자 모집공고문.pdf", "입주자 모집공고문.hwp"]


def test_notice_doc_format_order_pdf_then_hwpx_then_hwp():
    assert pick_notice_files(refs("모집공고문.hwp", "모집공고문.hwpx", "모집공고문.pdf"))[0].name == "모집공고문.pdf"
    assert [f.name for f in pick_notice_files(refs("모집공고문.hwp", "모집공고문.hwpx"))] == ["모집공고문.hwpx", "모집공고문.hwp"]


def test_hwp_first_when_preferred():
    assert pick_notice_files(refs("모집공고문.pdf", "모집공고문.hwp"), prefer="hwp")[0].name == "모집공고문.hwp"


def test_unit_list_takes_excel_once():
    files = refs("공급주택목록.pdf", "공급주택목록.xlsx", "예비자 명단.xlsx", "모집공고문.pdf")
    assert [f.name for f in pick_unit_lists(files)] == ["공급주택목록.xlsx"]


def test_draw_result_files_are_personal():
    """대전 결과 공고의 '추첨결과_….xlsx'에는 신청자 정보가 있을 수 있어서 받지 않아요."""
    files = refs("2026년 상반기 청년매입임대주택 입주대기자 선정 결과 발표.pdf", "추첨결과_2026-09-03-10-00-23.xlsx")
    assert files[1].personal and pick_unit_lists(files) == [] and pick_notice_files(files) == []


def test_notice_name_variants_and_summary_files():
    files = refs("신청자격 요약.pdf", "FAQ.pdf", "2026 행복주택 입주자모집.pdf")
    assert pick_notice_files(files)[0].name == "2026 행복주택 입주자모집.pdf" and not unclear_notice(files)


def test_unclear_notice_when_no_name_matches():
    assert unclear_notice(refs("붙임1 신청자격.pdf", "2026 청년주택.pdf"))
    assert not unclear_notice(refs("2026 청년주택.pdf", "2026 청년주택.hwp"))  # 같은 문서를 형식만 달리 올린 것


def test_old_excel_unit_list_is_picked_over_pdf():
    files = refs("모집공고문.pdf", "공급주택목록.pdf", "공급주택목록.xls")
    assert [f.name for f in pick_unit_lists(files)] == ["공급주택목록.xls"]


def test_notice_with_forms_in_name_beats_floor_plan():
    """부산 실제 첨부 (2026-10-19, rent-87): 공고문이 신청서류와 한 파일이고, 평면도는 '세대 내 구조'."""
    files = refs(
        "[첨부1]2026 남부민풀리페 국민임대 입주자(예비입주자) 모집 공고문 및 신청서류.hwp",
        "[첨부1]2026 남부민풀리페 국민임대 입주자(예비입주자) 모집 공고문 및 신청서류.pdf",
        "[첨부2]남부민풀리페 국민임대 세대 내 구조.hwp",
    )
    assert [f.name for f in pick_notice_files(files)] == [
        "[첨부1]2026 남부민풀리페 국민임대 입주자(예비입주자) 모집 공고문 및 신청서류.pdf",
        "[첨부1]2026 남부민풀리페 국민임대 입주자(예비입주자) 모집 공고문 및 신청서류.hwp",
    ]
    assert not refs("입주 신청서.hwp")[0].notice_doc  # 공고문이 아닌 서식은 그대로 제외


def test_strong_notice_name_beats_preferred_format():
    """경남 실제 첨부 (2026-10-19): '…공고문.hwpx'가 '…입주자모집 관련.pdf'보다 먼저."""
    files = refs(
        "(붙임3) 2026년 전세임대주택 입주자모집 관련.pdf",
        "(붙임2) 2026년 전세임대주택 제출서류.hwp",
        "(붙임1) 2026년 전세임대주택 입주자모집(제2차) 공고문.hwpx",
    )
    assert pick_notice_files(files)[0].name == "(붙임1) 2026년 전세임대주택 입주자모집(제2차) 공고문.hwpx"


def test_reserve_tenant_notice_is_not_a_name_list():
    # '예비자 모집공고문'은 공고문이에요. 이름만 보고 명단으로 거르면 공고문을 못 받아요 (LH 실제 4건)
    files = refs("행복주택 예비자 모집공고문.pdf", "영구임대 예비자입주자모집공고문.pdf", "예비자 명단.xlsx", "예비자 발표.pdf")
    assert [f.personal for f in files] == [False, False, True, True]
    assert [f.name for f in pick_notice_files(files)] == ["행복주택 예비자 모집공고문.pdf", "영구임대 예비자입주자모집공고문.pdf"]


def test_reviewed_supplementary_attachments_are_not_notice_fallbacks():
    """운영 검수에서 본문으로 잘못 읽은 서식·이용안내·기준 자료는 단독이어도 고르지 않아요."""
    names = (
        "(별첨)예비신혼부부 세대구성확인서.pdf",
        "2_ [전자계약] 부동산거래 전자계약시스템 이용안내.pdf",
        "[별지1호] 성북구 연극인주택 입주지원서.pdf",
        "7_청년 매입임대주택 부모 범위 기준(2순위 전체 및 부모무주택 가점 선택자 필독).pdf",
    )
    for name in names:
        assert pick_notice_files(refs(name)) == [], name


def test_translation_with_notice_title_never_replaces_primary_notice():
    primary = "(수정)2026년 1-2인가구 도시형생활주택 잔여세대 입주자 모집공고.pdf"
    translation = "(수정)생활언어 번역본 (2026년 도시형생활주택 입주자 모집공고).pdf"
    assert pick_notice_files(refs(translation)) == []
    assert [f.name for f in pick_notice_files(refs(translation, primary))] == [primary]
