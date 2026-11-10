import pytest

from mujuthaek_collector.sources.lh.documents import Attachment, is_housing_list, select_attachments
from mujuthaek_collector.sources.lh.parse import attachments


def item(kind, name, fileid="1"):
    return {
        "SL_PAN_AHFL_DS_CD_NM": kind,
        "CMN_AHFL_NM": name,
        "AHFL_URL": f"https://apply.lh.or.kr/lhapply/lhFile.do?fileid={fileid}",
    }


def names(selection):
    return [a.name for a in selection.notice_docs], [a.name for a in selection.extras]


def test_real_detail_response_picks_only_the_pdf(detail_body):
    # 태백소도: 공고문(hwp) + 공고문(PDF) + 기타 첨부(jpg) → PDF 하나
    docs, extras = names(select_attachments(attachments(detail_body)))
    assert docs == ["260917태백시국민임대주택예비입주자상시모집공고문..pdf"]
    assert extras == []


def test_pdf_and_hwp_with_slightly_different_names_are_the_same_document():
    # 부산당감1: '1page' 꼬리가 붙은 PDF가 실제로는 전체 공고문
    sel = select_attachments(
        [
            item("공고문(PDF)", "부산당감1_공임50년_예비입주자_모집공고문(26년)1page.pdf", "1"),
            item("공고문(hwp)", "부산당감1_공임50년_예비입주자_모집공고문(26년).hwp", "2"),
        ]
    )
    assert names(sel) == (["부산당감1_공임50년_예비입주자_모집공고문(26년)1page.pdf"], [])


def test_hwp_is_taken_when_there_is_no_matching_pdf():
    sel = select_attachments([item("공고문(hwp)", "○○지구 행복주택 입주자 모집공고문.hwpx")])
    assert names(sel)[0] == ["○○지구 행복주택 입주자 모집공고문.hwpx"]


def test_correction_notice_replaces_the_original_notice():
    sel = select_attachments(
        [
            item("공고문(PDF)", "대구연호A-3블록공고문.pdf", "1"),
            item("정정공고문(PDF)", "(정정)대구연호A-3블록공고문.pdf", "2"),
        ]
    )
    assert names(sel)[0] == ["(정정)대구연호A-3블록공고문.pdf"]


def test_separate_notice_per_complex_are_all_kept():
    sel = select_attachments(
        [
            item("공고문(PDF)", "★대구연호A-2블록통합공공임대입주자모집공고문(2026.09.30.).pdf", "1"),
            item("공고문(PDF)", "★대구연호A-3블록통합공공임대입주자모집공고문(2026.09.30.).pdf", "2"),
        ]
    )
    assert len(sel.notice_docs) == 2


def test_spreadsheet_and_appendix_typed_as_notice_go_to_extras():
    # 아산배방: 엑셀 배치표가 '정정공고문(PDF)'로 올라옴 / 양산: 붙임1 가격표가 '공고문(PDF)'로 올라옴
    sel = select_attachments(
        [
            item("정정공고문(PDF)", "아산배방LH4단지오피스텔잔여세대선착순동호지정공고.pdf", "1"),
            item("정정공고문(PDF)", "아산배방오피스텔동호수배치표미분양색(26.05.21.)1.xlsx", "2"),
            item("정정공고문(PDF)", "붙임1_공급대상및공급가격(2026.05.29.기준).pdf", "3"),
        ]
    )
    assert names(sel) == (
        ["아산배방LH4단지오피스텔잔여세대선착순동호지정공고.pdf"],
        ["아산배방오피스텔동호수배치표미분양색(26.05.21.)1.xlsx", "붙임1_공급대상및공급가격(2026.05.29.기준).pdf"],
    )


def test_notice_without_the_word_notice_in_its_name_is_kept():
    # 처음 넣었던 '파일명에 공고가 있어야 함' 규칙이 진짜 공고문 7건을 빠뜨렸던 경우
    sel = select_attachments([item("공고문(PDF)", "군산시국민임대입주자상시모집.pdf")])
    assert names(sel)[0] == ["군산시국민임대입주자상시모집.pdf"]


def test_appendix_is_kept_when_it_is_the_only_document():
    sel = select_attachments([item("공고문(PDF)", "붙임_공급대상주택목록.pdf")])
    assert names(sel)[0] == ["붙임_공급대상주택목록.pdf"]


def test_personal_data_and_forms_are_never_picked_but_reserve_notices_are():
    sel = select_attachments(
        [
            item("공고문(PDF)", "예비입주자 모집공고문.pdf", "1"),
            item("공고문(PDF)", "당첨자 명단.pdf", "2"),
            item("공고문(PDF)", "예비자 발표.pdf", "3"),
            item("공고문(hwp)", "신청서 양식.hwp", "4"),
        ]
    )
    assert names(sel) == (["예비입주자 모집공고문.pdf"], [])


def test_non_notice_kinds_and_missing_urls_are_ignored():
    sel = select_attachments(
        [
            item("기타 첨부파일", "단지 사진.jpg"),
            item("팸플릿", "안내.pdf"),
            {"SL_PAN_AHFL_DS_CD_NM": "공고문(PDF)", "CMN_AHFL_NM": "주소없음.pdf", "AHFL_URL": ""},
        ]
    )
    assert names(sel) == ([], [])


# ── 주택목록 엑셀 ───────────────────────────────────
def housing(selection):
    return [a.name for a in selection.housing_lists]


# 2026-10-14 수집에서 매입임대 공고에 실제로 붙어 있던 주택목록 엑셀 이름 (18건, 같은 이름 1개 포함 17종)
REAL_HOUSING_LISTS = [
    "(전북지역본부)2026년일반매입임대공급주택목록.xlsx",
    "(261001)경기북부든든전세주택공급대상주택목록.xlsx",
    "20260930청년매입임대주택공급대상주택목록(제주시-23호).xlsx",
    "붙임2.2026년2차대구경북지역든든전세주택주택목록(분양전환형).xlsx",
    "2026년하반기대구경북기존주택매입임대주택공급대상주택목록.xlsx",
    "26년_2차_비분양전환형_든든전세주택_주택목록(서울지역본부).xlsx",
    "(전북지역본부)26년3차청년매입임대공급주택목록.xlsx",
    "2026년경기남부든든전세매입임대주택주택목록(2026.09.30).xlsx",
    "붙임3.게시_26년9월공고신혼신생아1유형매입임대주택목록.xlsx",
    "(전북지역본부)26년3차신혼신생아매입임대Ⅱ(전세형)공급주택목록.xlsx",
    "2026년3차대구경북지역신혼ㆍ신생아매입임대Ⅱ(전세형)공급대상주택목록.xlsx",
    "(전북지역본부)26년3차신혼신생아Ⅰ공급주택목록.xlsx",
    "붙임2.26년2차일반매입임대공급주택목록(장기미임대).xlsx",
    "2026년3차대구경북지역신혼ㆍ신생아매입임대Ⅰ공급대상주택목록.xlsx",
    "2026년3차대구경북지역청년매입임대공급대상주택목록.xlsx",
    "2026년3차대구경북지역기숙사형청년매입임대공급대상주택목록.xlsx",
    "2_게시_26년9월대전충남신혼·신생아매입임대Ⅱ(전세형)주택목록0929.xlsx",
]
# 같은 수집에서 분양 공고에 붙어 있던, 주택목록이 아닌 엑셀
REAL_OTHER_SPREADSHEETS = [
    "아산배방오피스텔동호수배치표미분양색(26.05.21.)15세대.xlsx",
    "3.잔여세대동호배치도(26.08.14.기준).xlsx",
    "4.해약세대옵션내역(2호).xlsx",
    "익산평화잔여해약세대목록(옵션내용포함).xls",
    "A-1블록동호판(20260706기준).xlsm",
]


@pytest.mark.parametrize("name", REAL_HOUSING_LISTS)
def test_real_housing_list_names_are_recognised(name):
    assert is_housing_list(Attachment("기타 첨부파일", name, "u"))


@pytest.mark.parametrize("name", REAL_OTHER_SPREADSHEETS)
def test_other_spreadsheets_of_sale_notices_are_not_housing_lists(name):
    assert not is_housing_list(Attachment("기타 첨부파일", name, "u"))


def test_housing_list_must_be_a_spreadsheet_and_not_a_form():
    assert not is_housing_list(Attachment("기타 첨부파일", "공급대상주택목록.pdf", "u"))
    assert not is_housing_list(Attachment("기타 첨부파일", "주택목록_신청서.xlsx", "u"))
    assert is_housing_list(Attachment("기타 첨부파일", "주택내역.xls", "u"))


def test_housing_list_is_picked_besides_the_notice_whatever_its_kind():
    # 대전충남 신혼·신생아 I 매입임대(2015122300020761)의 실제 첨부 구성
    sel = select_attachments(
        [
            item("공고문(hwp)", "붙임1.게시_26년9월신혼·신생아매입임대Ⅰ입주자모집공고문_0929.hwpx", "1"),
            item("공고문(PDF)", "붙임1.게시_26년9월신혼·신생아매입임대Ⅰ입주자모집공고문_0929.pdf", "2"),
            item("기타 첨부파일", "붙임2.게시_26년9월신혼？신생아매입임대Ⅰ_QnA_0929.hwpx", "3"),
            item("기타 첨부파일", "붙임3.게시_26년9월공고신혼신생아1유형매입임대주택목록.xlsx", "4"),
        ]
    )
    assert names(sel) == (["붙임1.게시_26년9월신혼·신생아매입임대Ⅰ입주자모집공고문_0929.pdf"], [])
    assert housing(sel) == ["붙임3.게시_26년9월공고신혼신생아1유형매입임대주택목록.xlsx"]


def test_housing_list_typed_as_notice_is_not_also_an_extra():
    sel = select_attachments([item("공고문(PDF)", "모집공고문.pdf", "1"), item("공고문(PDF)", "공급대상주택목록.xlsx", "2")])
    assert names(sel) == (["모집공고문.pdf"], [])
    assert housing(sel) == ["공급대상주택목록.xlsx"]


def test_real_detail_response_has_no_housing_list(detail_body):
    assert housing(select_attachments(attachments(detail_body))) == []


def test_attachment_keeps_its_position_in_the_list(detail_body):
    # 파이프라인이 raw_files.idx와 S3 위치에 써요. 태백소도: [hwpx, pdf, jpg] → PDF는 1번
    [pdf] = select_attachments(attachments(detail_body)).notice_docs
    assert pdf.index == 1
