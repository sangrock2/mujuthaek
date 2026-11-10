"""서울시 청년안심주택 실제 응답(tests/fixtures/soco: 목록 JSON, 상세 화면)으로 목록·상세 읽기를 고정해요."""

import json
from datetime import date
from pathlib import Path

import pytest

from mujuthaek_collector.errors import ParseError
from mujuthaek_collector.sources.local.soco import CONTENT_KEY, REGION_KEY, _apply_period
from mujuthaek_collector.sources.registry import SOURCES

FIX = Path(__file__).parent / "fixtures" / "soco"
SRC = SOURCES["soco"]
BOARD = SRC.boards[0]


def list_items():
    body = (FIX / "BMSR00015-list.json").read_text(encoding="utf-8")
    return SRC.parse_list(BOARD, body, "https://soco.seoul.go.kr/youth/pgm/home/yohome/bbsListJson.json")


def test_list_request_is_form_post():
    request = SRC.list_request(BOARD, 3)
    assert request.url.endswith("/youth/pgm/home/yohome/bbsListJson.json")
    assert request.data["bbsId"] == "BMSR00015"
    assert request.data["pageIndex"] == "3"
    assert request.referer.endswith("list.do?menuNo=400008")


def test_parse_list_reads_rows():
    items = list_items()
    assert [i.post_key for i in items] == ["6702", "6701"]
    first = items[0]
    assert first.title == "[민간임대] 길동역 길동생활(B동) 추가모집공고"
    assert first.posted_on == date(2026, 10, 15)
    assert first.deadline_on == date(2026, 10, 20)
    assert first.detail_url == "https://soco.seoul.go.kr/youth/bbs/BMSR00015/view.do?optn1=2026-10-15&boardId=6702&menuNo=400008"
    assert first.meta["구분"] == "민간"
    assert first.meta["모집"] == "추가"
    assert first.meta["청약신청일"] == "2026-10-19"
    assert first.meta["첨부묶음"] == "5025ff882999490b947aecacef706c3e"


def test_view_count_is_not_kept():
    """조회수는 볼 때마다 바뀌어서 버전 비교에 섞이면 안 돼요."""
    item = list_items()[0]
    assert "inqireCo" not in json.dumps(item.to_json(), ensure_ascii=False)
    assert 8560 not in item.meta.values()


def test_list_item_survives_json_round_trip():
    item = list_items()[0]
    again = type(item).from_json(json.loads(json.dumps(item.to_json(), ensure_ascii=False)))
    assert again == item


def test_parse_detail_takes_only_real_download_link():
    item = list_items()[0]
    detail = SRC.parse_detail(item, (FIX / "BMSR00015-detail-6702.html").read_text(encoding="utf-8"))
    assert len(detail.files) == 1  # 바로보기·바로듣기 버튼은 같은 파일이라 빼요
    f = detail.files[0]
    assert f.name == "민간_261015_길동역_길동생활B동_청년안심주택 추가모집공고문.pdf"
    assert f.url == "https://soco.seoul.go.kr/coHouse/cmmn/file/fileDown.do?atchFileId=5025ff882999490b947aecacef706c3e&fileSn=1"
    assert f.ext == "pdf"


def test_parse_detail_body_and_fields():
    item = list_items()[0]
    detail = SRC.parse_detail(item, (FIX / "BMSR00015-detail-6702.html").read_text(encoding="utf-8"))
    assert "길동생활(B동) 청년안심주택" in detail.body_text
    assert "■청약신청 : ‘26. 10. 19." in detail.body_text
    assert detail.meta["단지명"] == "길동생활(B동)"
    assert detail.meta["주택위치"].startswith("서울특별시 강동구 길동 368-7")
    assert detail.meta["사업주체"] == "(주)대한제37호위탁관리부동산투자회사"
    assert detail.meta["청약신청 시작"] == "2026-10-19"
    assert detail.meta["청약신청 마감"] == "2026-10-20"
    assert CONTENT_KEY not in detail.meta  # 본문 HTML은 meta로 내보내지 않아요
    assert detail.posted_on == date(2026, 10, 15)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("■청약신청 : ‘26. 10. 19. (월) 09:00 ~ 10. 20. (화) 18:00", (date(2026, 10, 19), date(2026, 10, 20))),
        ("■청약신청 : 2026. 12. 30.(수) ~ 1. 2.(토)", (date(2026, 12, 30), date(2027, 1, 2))),
        ("■청약신청 : ‘26. 11. 3. (화) 10:00 ~ 17:00", (date(2026, 11, 3), date(2026, 11, 3))),
        ("청약신청 일정은 추후 안내", (None, None)),
    ],
)
def test_apply_period(text, expected):
    assert _apply_period(text) == expected


def test_list_errors_when_shape_changes():
    with pytest.raises(ParseError):
        SRC.parse_list(BOARD, "<html>오류</html>", "u")
    with pytest.raises(ParseError):
        SRC.parse_list(BOARD, json.dumps({"pagingInfo": {}}), "u")
    with pytest.raises(ParseError):
        SRC.parse_list(BOARD, json.dumps({"resultList": [{"nttSj": "제목만"}]}), "u")


def test_empty_list_is_not_an_error():
    assert SRC.parse_list(BOARD, json.dumps({"resultList": []}), "u") == []


def test_apply_period_skips_sentence_without_colon():
    """본문 앞의 '통합하여 청약 신청을 받습니다' 문장이 아니라 날짜 줄을 읽어야 해요."""
    text = "※ A동,B동 단지는 통합하여 청약 신청을 받습니다.\n■청약신청 : ‘26. 10. 19. (월) 09:00 ~ 10. 20. (화) 18:00"
    assert _apply_period(text) == (date(2026, 10, 19), date(2026, 10, 20))


def test_district_number_becomes_region_code():
    """gubunCd 02 = 강동구(11740). 본문의 주택위치와 같은 구예요."""
    item = list_items()[0]
    assert item.meta["자치구"] == "강동구" and item.meta[REGION_KEY] == "11740"
    detail = SRC.parse_detail(item, (FIX / "BMSR00015-detail-6702.html").read_text(encoding="utf-8"))
    assert detail.region_code == "11740" and "강동구" in detail.meta["주택위치"]
    assert REGION_KEY not in detail.meta


def test_unknown_district_number_leaves_region_empty():
    doc = json.loads((FIX / "BMSR00015-list.json").read_text(encoding="utf-8"))
    doc["resultList"] = doc["resultList"][:1]
    doc["resultList"][0]["gubunCd"] = "99"
    item = SRC.parse_list(BOARD, json.dumps(doc), "u")[0]
    assert item.meta["자치구"] is None and SRC.parse_detail(item, "<html></html>").region_code is None
