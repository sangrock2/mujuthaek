"""LH API 호출: 응답을 그대로 두고, 인증키는 기록·오류 어디에도 남기지 않아요."""

import json
import urllib.parse
from datetime import date

import httpx
import pytest

from mujuthaek_collector.errors import BlockedError
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.api import LhApi, detail_params, redact, title_keywords
from tests.sources.lh.helpers import KEY

TODAY = date(2026, 10, 14)


class Replies:
    """요청마다 정해둔 답을 차례로 줘요. 답이 함수면 요청 값으로 답을 만들어요."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.urls: list[str] = []

    def params(self, n=-1) -> dict:
        return dict(urllib.parse.parse_qsl(self.urls[n].partition("?")[2]))

    def text(self, url, *, data=None, referer=None):
        self.urls.append(url)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if callable(reply):
            reply = reply(self.params())
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def page(rows, total):
    return [{"dsSch": [{}]}, {"dsList": [{**r, "ALL_CNT": str(total)} for r in rows], "resHeader": [{}]}]


def test_open_list_reads_every_page_and_never_keeps_the_key():
    client = Replies(page([{"PAN_ID": "1"}, {"PAN_ID": "2"}], 3), page([{"PAN_ID": "3"}], 3))
    pages = LhApi(client, KEY).open_notice_pages(TODAY)
    assert [p.params["PAGE"] for p in pages] == ["1", "2"]
    assert pages[0].params["PAN_ST_DT"] == "20231015"  # 3년 전부터 (기간을 안 주면 2개월만 와요)
    assert pages[0].params["CLSG_ST_DT"] == "20261014"  # 마감일 오늘 이후
    assert client.params(0)["serviceKey"] == KEY  # 요청에는 넣어요
    for p in pages:
        dumped = json.dumps(p.to_dict(), ensure_ascii=False)
        assert "serviceKey" not in p.params and KEY not in dumped and urllib.parse.quote_plus(KEY) not in dumped


def test_list_stops_on_empty_page_and_at_max_pages():
    assert len(LhApi(Replies(page([], 0)), KEY).open_notice_pages(TODAY)) == 1
    endless = Replies(lambda p: page([{"PAN_ID": p["PAGE"]}] * 2, 10_000))
    assert len(list(LhApi(endless, KEY).iter_pages(max_pages=3))) == 3


def test_detail_and_supply_keep_the_body_untouched(list_body, detail_body, supply_body):
    row = list_body[1]["dsList"][0]
    client = Replies(detail_body, supply_body)
    api = LhApi(client, KEY)
    detail, supply = api.detail(row), api.supply(row)
    assert detail.body == detail_body and supply.body == supply_body
    assert detail.params == {k: row[k] for k in config.DETAIL_KEYS}
    assert client.urls[0].startswith(config.DETAIL_URL) and client.urls[1].startswith(config.SUPPLY_URL)


def test_empty_body_is_retried_then_given_up():
    client = Replies("", "  ", page([], 0))
    assert LhApi(client, KEY).list_page(1).body == page([], 0)
    with pytest.raises(httpx.HTTPError, match="빈 응답"):
        LhApi(Replies(""), KEY).list_page(1)


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ({"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}, "오류 응답"),
        ("<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>", "JSON이 아닌"),
    ],
)
def test_key_or_api_errors_stop_the_run(reply, message):
    with pytest.raises(BlockedError, match=message):
        LhApi(Replies(reply), KEY).list_page(1)


def test_errors_from_the_client_never_carry_the_key():
    quoted = urllib.parse.quote_plus(KEY)
    blocked = BlockedError(f"HTTP 429 응답이라 이번 회차를 멈춰요: {config.LIST_URL}?serviceKey={quoted}")
    with pytest.raises(BlockedError) as caught:
        LhApi(Replies(blocked), KEY).list_page(1)
    assert quoted not in str(caught.value) and "***" in str(caught.value) and caught.value.__cause__ is None
    failed = httpx.ConnectError(f"연결 실패: {config.LIST_URL}?serviceKey={quoted}")
    with pytest.raises(httpx.HTTPError) as caught:
        LhApi(Replies(failed), KEY).list_page(1)
    assert quoted not in str(caught.value)
    assert redact(f"a {KEY} b {urllib.parse.quote(KEY, safe='')}", KEY) == "a *** b ***"


def test_detail_needs_all_five_keys():
    with pytest.raises(ValueError, match="SPL_INF_TP_CD"):
        detail_params({"PAN_ID": "1", "CCR_CNNT_SYS_DS_CD": "03", "UPP_AIS_TP_CD": "06", "AIS_TP_CD": "07"})


# ── 마감 전 목록에 없는 공고 다시 찾기 ─────────────────
TITLE = "[재게시] 효천LH천년나무2단지(효천하우스디) 잔여세대 일반매각"


def test_find_row_by_posting_date_first():
    client = Replies(page([{"PAN_ID": "X"}, {"PAN_ID": "TARGET"}], 2))
    row, found = LhApi(client, KEY).find_row("TARGET", "20260817", TITLE, TODAY)
    assert row["PAN_ID"] == "TARGET"
    assert found.params["PAN_ST_DT"] == found.params["PAN_ED_DT"] == "20260817"
    assert len(client.urls) == 1


def test_find_row_falls_back_to_title_words():
    client = Replies(lambda p: page([{"PAN_ID": "TARGET"}], 1) if p.get("PAN_NM") == "효천LH천년나무2단지" else page([], 0))
    row, found = LhApi(client, KEY).find_row("TARGET", "20260817", TITLE, TODAY)
    assert row["PAN_ID"] == "TARGET" and found.params["PAN_ST_DT"] == "20231015"
    assert [client.params(i).get("PAN_NM") for i in range(len(client.urls))] == [None, "효천LH천년나무2단지"]


def test_find_row_gives_up_and_reads_only_a_few_pages_per_word():
    client = Replies(lambda p: page([{"PAN_ID": "OTHER"}] * 2, 1000))
    assert LhApi(client, KEY).find_row("TARGET", "bad-date", TITLE, TODAY) == (None, None)
    assert len(client.urls) == len(title_keywords(TITLE)) * config.LOOKUP_MAX_PAGES  # 날짜가 이상하면 날짜 검색은 건너뛰어요


@pytest.mark.parametrize(
    ("title", "words"),
    [
        ("태백소도 국민임대주택 예비입주자 상시모집(26.9.17 공고)", ["태백소도"]),
        ("[정정공고][선착순 동·호지정] 영천문외 센트럴타운 공공분양주택 추가입주자", ["센트럴타운", "영천문외"]),
        (TITLE, ["효천LH천년나무2단지", "일반매각", "잔여세대"]),
        ("국민임대주택 예비입주자 모집공고", []),
    ],
)
def test_title_keywords_prefer_complex_names_over_common_words(title, words):
    assert title_keywords(title) == words
