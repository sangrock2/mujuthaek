import json

import pytest

from mujuthaek_collector.errors import BlockedError
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.myhome import (
    MyHomeApi,
    MyHomeApiError,
    items,
    lh_notice_id,
    row_key,
    total_count,
)


class FakeText:
    """요청마다 정해둔 글자를 차례로 줘요 (팀 Fetcher 규격의 text만)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.urls = []

    def text(self, url, *, data=None, referer=None):
        self.urls.append(url)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def body(rows, total=None):
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
            "body": {"totalCount": str(len(rows) if total is None else total), "item": rows},
        }
    }


def test_real_rent_response_row_is_an_lh_notice(myhome_rent_body):
    [row] = items(myhome_rent_body)
    assert lh_notice_id(row) == "2015122300020904"  # 창녕영산 행복주택: url의 panId가 LH 공고 ID
    assert row["pnu"] == "4874038021101750000" and row["signguNm"] == "창녕군"  # LH API에 없는 값
    assert total_count(myhome_rent_body) == 286


def test_real_sale_response_points_correction_row_to_the_original_notice(myhome_sale_body):
    [row] = items(myhome_sale_body)
    # 마이홈 정정공고 줄인데 링크는 원공고(청주지북B1) ID를 가리킨다. 정정 연결 때 beforePblancId를 같이 봐야 함
    assert row["sttusNm"] == "정정공고" and row["beforePblancId"] == "1451"
    assert lh_notice_id(row) == "0000061143"


def test_single_row_can_come_as_an_object_and_empty_body_as_nothing():
    assert items(body({"pblancId": "1"})) == [{"pblancId": "1"}]
    assert items({"response": {"header": {"resultCode": "00"}, "body": {"totalCount": "0"}}}) == []


@pytest.mark.parametrize(
    "data",
    [
        {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}},
        {"resultCode": "99"},
        ["unexpected"],
    ],
)
def test_error_or_unknown_shape_raises(data):
    with pytest.raises(MyHomeApiError):
        items(data)


def test_only_lh_rows_with_a_pan_id_are_lh_notices():
    assert lh_notice_id({"suplyInsttNm": "LH", "url": "https://apply.lh.or.kr/x.do?panId=123&a=1"}) == "123"
    assert lh_notice_id({"suplyInsttNm": "경상북도개발공사", "url": "https://x.test/?panId=123"}) is None
    assert lh_notice_id({"suplyInsttNm": "LH", "url": "https://apply.lh.or.kr/x.do"}) is None
    assert lh_notice_id({"suplyInsttNm": "LH"}) is None


def test_row_key_is_list_notice_and_complex():
    assert row_key("rent", {"pblancId": "21401", "houseSn": 2}) == "rent:21401:2"


def test_list_pages_reads_every_page_and_never_keeps_the_key():
    client = FakeText([body([{"pblancId": "1"}, {"pblancId": "2"}], total=3), body([{"pblancId": "3"}], total=3)])
    pages = MyHomeApi(client, "SECRET").list_pages("sale")
    assert [p.params["pageNo"] for p in pages] == ["1", "2"]
    assert client.urls[0].startswith(f"{config.MYHOME_URL}/{config.MYHOME_LISTS['sale']}?") and "serviceKey=SECRET" in client.urls[0]
    assert all("SECRET" not in json.dumps(p.to_dict(), ensure_ascii=False) for p in pages)
    assert pages[0].api == "myhome-sale"


def test_non_json_is_a_myhome_error_but_a_block_stops_the_run():
    with pytest.raises(MyHomeApiError):
        MyHomeApi(FakeText(["<OpenAPI_ServiceResponse>"]), "k").list_pages("rent")
    with pytest.raises(BlockedError):
        MyHomeApi(FakeText([BlockedError("HTTP 429")]), "k").list_pages("rent")
