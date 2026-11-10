"""상세·공급정보·마이홈 응답 → 본문 글자·시군구 코드.

본문 글자는 '바뀐 것만 새 버전' 해시에 들어가요. 부를 때마다 바뀌는 응답 시각이 들어가면 매번 새 버전이 돼요.
"""

import copy

from mujuthaek_collector.sources.lh.detail import body_text, lh_meta, region_code
from tests.sources.lh.helpers import taebaek_myhome_row


def entry(row, kind="rent"):
    return {"list": kind, "key": f"{kind}:{row['pblancId']}:{row['houseSn']}", "fetchedAt": "2026-10-15T00:00:00+00:00", "item": row}


def set_block(body, name, rows):
    body = copy.deepcopy(body)
    for block in body:
        if name in block:
            block[name] = rows
    return body


def test_body_text_reads_detail_supply_and_myhome_with_korean_labels(detail_body, supply_body):
    text = body_text(detail_body, supply_body, [entry(taebaek_myhome_row())])
    assert "신청일시" not in text  # 값이 '~'뿐인 칸(빈 기간)은 빼요
    assert "접수기간시작일: 2026.09.28 | 접수기간종료일: 2026.10.30" in text
    assert "[단지]\n단지주소: 강원특별자치도 태백시 소도길 60(소도동,태백소도엘에이치천년나무)" in text
    assert "파일구분명: 공고문(PDF) | 첨부파일명: 260917태백시국민임대주택예비입주자상시모집공고문..pdf" in text
    assert "[공급정보 dsList01]" in text and "금회공급 세대수: 60" in text
    assert "필지번호: 5119010700100600000" in text and "임대보증금(원): 14569000" in text
    assert "조감도.jpg" not in text  # 단지 사진 목록은 빼요
    assert "lhFile.do" not in text  # 첨부 다운로드 주소는 빼요 (파일 내용은 해시로 비교)
    assert "RS_DTTM" not in text and "SPL_INF_TP_CD" not in text  # 응답 시각·요청 값은 빼요


def test_body_text_ignores_response_time_but_sees_real_changes(detail_body, supply_body):
    before = body_text(detail_body, supply_body, [])
    stamped = set_block(detail_body, "resHeader", [{"RS_DTTM": "20991231235959", "SS_CODE": "Y"}])
    assert body_text(stamped, supply_body, []) == before
    moved = set_block(detail_body, "dsSplScdl", [{"SBSC_ACP_ST_DT": "2026.09.29", "SBSC_ACP_CLSG_DT": "2026.10.30"}])
    assert body_text(moved, supply_body, []) != before
    renamed = copy.deepcopy(detail_body)
    for block in renamed:
        for f in block.get("dsAhflInfo", []):
            f["CMN_AHFL_NM"] = f["CMN_AHFL_NM"].replace("공고문", "공고문(수정)")
    assert body_text(renamed, supply_body, []) != before  # LH가 같은 공고 안에서 공고문을 바꾼 경우


def test_myhome_rows_are_in_a_fixed_order(detail_body, supply_body):
    a, b = entry(taebaek_myhome_row(1)), entry(taebaek_myhome_row(2, hsmpNm="제2단지"))
    assert body_text(detail_body, supply_body, [a, b]) == body_text(detail_body, supply_body, [b, a])


def supply(rows, labels):
    return [{"dsSch": [{}]}, {"dsList01Nm": [labels], "dsList01": rows, "resHeader": [{}]}]


def test_supply_columns_go_into_body_text_for_extraction(detail_body):
    # 호별 표(units)는 만들지 않아요 (#19). 공급정보는 칸 이름과 함께 본문 글자에 넣고, 표 해석은 extraction이 해요
    sale = supply(
        [{"BZDT_NM": "인천계양 A17", "HTY_NM": "55.9000A", "SIL_HSH_CNT": "137", "SIL_AMT": "504484000"}],
        {"BZDT_NM": "단지명", "HTY_NM": "주택형", "SIL_HSH_CNT": "금회공급세대수", "SIL_AMT": "평균분양가격(원)"},
    )
    text = body_text(detail_body, sale, [])
    assert "[공급정보 dsList01]\n단지명: 인천계양 A17 | 주택형: 55.9000A | 금회공급세대수: 137 | 평균분양가격(원): 504484000" in text


def test_region_code_comes_from_myhome_parcel_number():
    assert region_code([entry(taebaek_myhome_row())]) == "51190"
    assert region_code([entry(taebaek_myhome_row(pnu=""))]) is None
    assert region_code([]) is None


def test_lh_meta_uses_readable_names(list_body):
    assert lh_meta(list_body[1]["dsList"][0]) == {
        "공고유형": "국민임대",
        "상위유형": "임대주택",
        "지역": "강원특별자치도",
        "공고상태": "공고중",
        "마감일": "2026.10.30",
    }
