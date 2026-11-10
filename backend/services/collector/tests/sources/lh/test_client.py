"""LH 요청 클라이언트: 팀 PoliteClient 그대로 + robots 예외 경로 하나 + 공공데이터포털 API 간격."""

import httpx
import pytest

from mujuthaek_collector.errors import BlockedError, FileRejected
from mujuthaek_collector.sources import public_data
from mujuthaek_collector.sources.lh import config
from mujuthaek_collector.sources.lh.client import LhClient

LH_ROBOTS = "User-agent: *\nDisallow: /lhapply/lhFile.do\nDisallow: /lhapply/secret\n"  # 2026-10-14 실제 규칙 + 시험용 한 줄
FILE_URL = "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=1"
API_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1?PAGE=1"


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        if request.url.host == "apply.lh.or.kr":
            return httpx.Response(200, text=LH_ROBOTS)
        return httpx.Response(404)
    if request.url.path == "/lhapply/lhFile.do":
        return httpx.Response(200, content=b"%PDF-1.7 notice", headers={"Content-Type": "application/octet-stream"})
    if request.url.path == "/lhapply/html":
        return httpx.Response(200, text="<html>로그인</html>", headers={"Content-Type": "text/html"})
    return httpx.Response(200, text="[]")


@pytest.fixture
def make_client():
    def make(**kwargs):
        sleeps: list[float] = []
        client = LhClient(service_key="k", delay_seconds=4.0, transport=httpx.MockTransport(handler), sleep=sleeps.append, **kwargs)
        return client, sleeps

    return make


def test_only_the_team_decided_path_skips_robots(make_client):
    client, _ = make_client()
    assert client.download(FILE_URL) == b"%PDF-1.7 notice"
    assert client.robots_overridden == 1
    assert not client.allowed("https://apply.lh.or.kr/lhapply/secret/page")  # 다른 막힌 경로는 그대로 막아요
    with pytest.raises(BlockedError, match="robots.txt"):
        client.text("https://apply.lh.or.kr/lhapply/secret/page")
    assert list(config.ROBOTS_OVERRIDES) == ["https://apply.lh.or.kr/lhapply/lhFile.do"]


def test_file_checks_of_the_team_client_still_apply(make_client):
    client, _ = make_client()
    with pytest.raises(FileRejected, match="웹페이지"):
        client.download("https://apply.lh.or.kr/lhapply/html")
    small, _ = make_client(max_file_bytes=5)
    with pytest.raises(FileRejected, match="MB보다 커서"):
        small.download(FILE_URL)


def test_public_data_api_uses_a_short_interval(make_client):
    client, sleeps = make_client()
    client.text(API_URL)
    client.text(API_URL)
    assert sleeps and all(0 < s <= public_data.API_DELAY_SECONDS for s in sleeps)  # 공공데이터포털: 0.5초
    client.download(FILE_URL)
    client.download(FILE_URL)
    assert max(sleeps) > 3  # 기관 사이트(첨부)는 팀 기본 간격(4초)
