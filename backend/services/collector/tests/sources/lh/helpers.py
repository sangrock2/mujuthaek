"""LH 테스트 도우미: 실제 LH·마이홈 응답(fixtures/lh)과 가짜 요청 클라이언트."""

import copy
import itertools
import json
import urllib.parse
from pathlib import Path

from mujuthaek_collector.errors import FileRejected
from mujuthaek_collector.sources.lh import config

FIXTURES = Path(__file__).parents[2] / "fixtures" / "lh"
KEY = "SECRET-KEY+/="  # 주소에 넣으면 인코딩되는 글자까지 넣어서, 어떤 모양으로도 새지 않는지 봐요
PAN = "2015122300020793"  # fixtures의 실제 공고 (태백소도 국민임대)
PDF_URL = "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=68635057"
EMPTY_LIST = [{"dsSch": [{}]}, {"dsList": []}]


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def with_rows(list_body, rows):
    """실제 목록 응답의 태백소도 줄을 바탕으로 값만 바꾼 목록."""
    body = copy.deepcopy(list_body)
    base = body[1]["dsList"][0]
    body[1]["dsList"] = [{**base, **r, "ALL_CNT": str(len(rows))} for r in rows]
    return body


def myhome_body(base_body, rows):
    """실제 마이홈 응답(창녕영산 줄)을 바탕으로 값만 바꾼 목록."""
    body = copy.deepcopy(base_body)
    base = body["response"]["body"]["item"][0]
    body["response"]["body"]["item"] = [{**base, **r} for r in rows]
    body["response"]["body"]["totalCount"] = str(len(rows))
    return body


def taebaek_myhome_row(house_sn=1, **changes):
    row = {
        "pblancId": "30001",
        "houseSn": house_sn,
        "pblancNm": "태백소도 국민임대주택 예비입주자 상시모집(26.9.17 공고)",
        "rcritPblancDe": "20260917",
        "url": f"https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId={PAN}&ccrCnntSysDsCd=03",
        "pnu": "5119010700100600000",
        "rentGtn": 14569000,
        "mtRntchrg": 87920,
    }
    return {**row, **changes}


class FakeLhClient:
    """공공데이터포털 API·LH 첨부 주소를 흉내 내요 (팀 Fetcher 규격: text·download).

    open_list: 마감 전 목록 응답 / lookup(params): 목록 다시 찾기 응답(없으면 None)
    myhome: {'rent': [줄], 'sale': [줄]} / files: 주소 → 바이트·예외
    응답 시각(resHeader.RS_DTTM)은 부를 때마다 바뀌어요. 이 값으로 '바뀜'을 판단하면 안 돼요.
    """

    def __init__(self, list_body, detail_body, supply_body, myhome_base):
        self.service_key = KEY
        self.open_list = list_body
        self.lookup = lambda params: None
        self.detail_body, self.supply_body = detail_body, supply_body
        self.myhome_base = myhome_base
        self.myhome: dict[str, list[dict]] = {"rent": [], "sale": []}
        self.myhome_error: dict | str | None = None
        self.files: dict[str, object] = {PDF_URL: b"%PDF-1.7 fake notice"}
        self.calls: list[str] = []
        self.params: list[dict] = []
        self._clock = itertools.count(20261014120000)

    def _stamp(self, body):
        body = copy.deepcopy(body)
        for block in body if isinstance(body, list) else []:
            if "resHeader" in block:
                block["resHeader"] = [{"RS_DTTM": str(next(self._clock)), "SS_CODE": "Y"}]
        return body

    def text(self, url, *, data=None, referer=None):
        base, _, query = url.partition("?")
        params = dict(urllib.parse.parse_qsl(query))
        assert params.pop("serviceKey", None) == KEY, "인증키가 주소에 없어요"
        self.calls.append(base)
        self.params.append(params)
        if base == config.LIST_URL:
            body = self.open_list if "CLSG_ST_DT" in params else (self.lookup(params) or EMPTY_LIST)
        elif base == config.DETAIL_URL:
            body = self.detail_body
        elif base == config.SUPPLY_URL:
            body = self.supply_body
        elif base.startswith(config.MYHOME_URL):
            if self.myhome_error is not None:
                return self.myhome_error if isinstance(self.myhome_error, str) else json.dumps(self.myhome_error)
            kind = "rent" if base.endswith(config.MYHOME_LISTS["rent"]) else "sale"
            return json.dumps(myhome_body(self.myhome_base, self.myhome[kind]), ensure_ascii=False)
        else:
            raise AssertionError(f"예상하지 않은 요청: {base}")
        return json.dumps(self._stamp(body), ensure_ascii=False)

    def download(self, url, *, referer=None):
        self.calls.append(url)
        reply = self.files.get(url)
        if reply is None:
            raise FileRejected(f"없는 파일: {url}")
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self):
        pass
