"""기관별 파서 테스트. 화면 구조(선택자)를 작은 예시로 고정해요. 실제 화면 확인은 test_fixtures.py가 해요."""

import json
from datetime import date

import pytest

from mujuthaek_collector.core.classify import CORRECTION, EXCLUDED, FOLLOW_UP
from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.registry import SOURCES


def board(code, key=None):
    source = SOURCES[code]
    return source, next(b for b in source.boards if key is None or b.key == key)


def test_sh_list_and_detail():
    source, b = board("sh")
    page = """<table><tbody>
      <tr><td>공지</td><td><a href="#" onclick="getDetailView('299001')">상단 고정 안내</a></td><td>주거복지</td><td>2026-09-01</td><td>9</td></tr>
      <tr><td>120</td><td><a href="#" onclick="getDetailView('300123');return false;">2026년 행복주택 입주자 모집공고<span class="icoNew">N</span></a></td>
          <td>주거복지</td><td>2026-10-08</td><td>301</td></tr></tbody></table>"""
    items = source.parse_list(b, page, source.list_request(b, 1).url)
    assert [i.post_key for i in items] == ["299001", "300123"]
    item = items[1]
    assert item.title == "2026년 행복주택 입주자 모집공고" and item.posted_on == date(2026, 10, 8)
    assert item.fetch_url.endswith("/m_247/view.do") and item.form["seq"] == "300123"
    detail = source.parse_detail(
        item,
        """<table><tr><td colspan="2" class="cont"><p>신청 자격</p></td></tr></table>
      <a href="#" onclick="existFile('1')">모집공고문.pdf</a> <a href="/app/htmlConverter.do?brd_id=GS0401&seq=300123&data_tp=A&file_seq=1">미리보기</a>""",
    )
    assert "신청 자격" in detail.body_text
    assert detail.files[0].url == "https://www.i-sh.co.kr/app/com/file/innoFD.do?brdId=GS0401&seq=300123&fileTp=A&fileSeq=1"


def test_apply_center_dedupes_rows_and_reads_unit_table():
    source, b = board("bmc", "rent")
    row = (
        '<tr><td>1</td><td>국민임대</td><td><a class="text_cut" data-pbancNo="777" data-pbancKndCd="02" data-bizTyNm="국민임대">'
        "2026년 국민임대 입주자 모집공고</a></td><td>부산</td><td></td><td>2026-10-01</td><td>2026-10-20</td><td>접수중</td></tr>"
    )
    items = source.parse_list(b, f"<table><tbody>{row}{row}</tbody></table>", "")
    assert len(items) == 1 and items[0].post_key == "rent-777" and items[0].deadline_on == date(2026, 10, 20)
    assert source.pre_classify(items[0]) == CORRECTION  # data-pbancKndCd=02
    detail = source.parse_detail(
        items[0],
        """
      <table><caption>청약공고 상세</caption><tr><th>공고명</th><td>2026년 국민임대 입주자 모집공고</td><th>공고상태</th><td>접수중</td></tr></table>
      <table><caption>주택형별 임대조건</caption><tr><th>주택형</th><th>전용면적</th><th>임대보증금</th><th>월임대료</th></tr>
        <tr><td>36A</td><td>36.9</td><td>15,000,000</td><td>120,000</td></tr></table>
      <a href="/smw/smw113010/selectFileDown.do?pbancNo=777&atchFileSn=1&atchFileDtlSn=1">모집공고문.pdf (1024 Byte)</a>""",
    )
    assert "[주택형별 임대조건]" in detail.body_text and "36A | 36.9 | 15,000,000 | 120,000" in detail.body_text  # 해석은 extraction이 해요
    assert detail.files[0].name == "모집공고문.pdf" and detail.files[0].size == 1024


def test_ih_board_prefix_in_post_key():
    source, b = board("ih", "sale_lease")
    page = """<ul class="generalList"><li><p class="title"><a href="/main/bbs/bbsMsgDetail.do?msg_seq=55&bcd=sale_lease&cate1=a">
      영종 A44 분양 입주자 모집공고 (2026.09.30)</a></p><div><ul><li class="writer">분양팀</li><li class="date">2026.10.02</li></ul></div></li></ul>"""
    item = source.parse_list(b, page, "")[0]
    assert item.post_key == "sale_lease-55" and item.posted_on == date(2026, 10, 2)  # 제목 속 날짜가 아니라 작성일


def test_dcco_tags_decide_kind():
    source, b = board("dcco", "43")
    page = """<table><tr><td><a href="view.do?mId=43&brdIdx=9"><span class="part">[공고결과]</span>매입임대 입주자 모집공고(2026. 9. 1.) 결과</a></td>
      <td class="part">모집종료</td><td>2026-10-05</td></tr></table>"""
    item = source.parse_list(b, page, "")[0]
    assert item.post_key == "43-9" and item.title.startswith("매입임대") and source.pre_classify(item) == FOLLOW_UP


def test_dudc_excludes_land():
    source, b = board("dudc")
    page = """<table><tr><td class="bgbar">토지</td><td><a href="/ko/page.do?appId=sale&mnu_uid=101&board_idx=31&cmd=2">용지 공급</a></td>
      <td class="date">2026-10-01</td></tr></table>"""
    assert source.pre_classify(source.parse_list(b, page, "")[0]) == EXCLUDED


def test_umca_builds_download_url_from_script():
    source, b = board("umca", "rent")
    item = source.parse_list(
        b,
        '<table><tr><td><a href="view.do?mId=1&bbsId=BBS_0000000000000004&dataId=88">국민임대 예비입주자 모집공고</a></td><td>2026-10-01</td></tr></table>',
        "",
    )[0]
    detail = source.parse_detail(
        item,
        """<table class="tbl_bd_view"><tr><th scope="row">제목</th><td>국민임대 예비입주자 모집공고</td></tr>
      <tr><th scope="row">첨부파일</th><td>
        <a href="#" onclick="HHBbs.DownFile('/umca','BBS_0000000000000004','FILE_0001','0')">모집공고문.hwp (120 KByte)</a></td></tr>
      <tr><td colspan="2"><p>본문</p></td></tr></table>""",
    )
    assert detail.files[0].name == "모집공고문.hwp"
    assert detail.files[0].url == "https://www.umca.co.kr/umca/bbs/FileDown.do?bbsId=BBS_0000000000000004&atchFileId=FILE_0001&fileSn=0"


def test_gbgn_json_list_filters_category():
    source, b = board("gbdc")
    body = json.dumps(
        {
            "resultList": [
                {
                    "IPDS_IDX": 10,
                    "CPDS_SUBJECT": "2026 국민임대 입주자 모집공고",
                    "CPDS_WDATE": "2026-10-01 10:00",
                    "COLM1_VAL": "임대공고",
                    "sysFileNameStr": "/a/b.pdf",
                    "orgFileNameStr": "모집공고문.pdf",
                },
                {"IPDS_IDX": 11, "CPDS_SUBJECT": "보상계획 공고", "CPDS_WDATE": "2026-10-02", "COLM1_VAL": "보상공고"},
            ]
        }
    )
    items = source.parse_list(b, body, "")
    assert (
        items[0].files[0].url
        == "https://www.gbdc.co.kr/common/download.do?fileVirtualPath=%2Fa%2Fb.pdf&fileOrgName=%EB%AA%A8%EC%A7%91%EA%B3%B5%EA%B3%A0%EB%AC%B8.pdf"
    )
    assert source.pre_classify(items[0]) is None and source.pre_classify(items[1]) == EXCLUDED


def test_gndc_list_request_encodes_attrs():
    source, b = board("gndc")
    assert "ATTR01=COLM1_CD%26notice_06%7CCOLM3_CD" in source.list_request(b, 2).url


@pytest.mark.parametrize("code", sorted(SOURCES))
def test_missing_list_structure_is_parse_error(code):
    source = SOURCES[code]
    with pytest.raises(ParseError):
        source.parse_list(source.boards[0], "<html><body>점검 중</body></html>", "")


def test_dcco_purchase_notice_is_excluded_even_with_recruit_tag():
    """대전은 공사가 집을 사는 매입공고에도 [모집공고] 머리말을 붙여요 (2026-10-15 실제 화면, 43-24807)."""
    source, b = board("dcco", "43")
    page = """<table><tr><td><a href="view.do?mId=43&brdIdx=24807"><span class="part">[모집공고][주택임대]</span>
      2026년 기존주택(청년임대) 3차 매입공고</a></td><td class="part">모집종료</td><td>2026-08-27</td></tr></table>"""
    item = source.parse_list(b, page, "")[0]
    assert source.pre_classify(item) == EXCLUDED
