"""공공데이터포털 API로 수집하는 출처(지금은 LH)가 같이 쓰는 요청 도구.

- PublicDataClient: 팀 공통 PoliteClient 그대로에, 공공데이터 API 주소만 짧은 간격으로 불러요 (기관 사이트는 팀 기본 간격)
- fetch_json: API 한 번 호출. 응답은 받은 그대로 돌려주고, 요청 값은 남기되 인증키는 남기지 않아요.
  오류 메시지에서도 인증키를 지워요. 빈 응답은 다시 불러요.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from mujuthaek_collector.core.http_client import PoliteClient
from mujuthaek_collector.errors import BlockedError
from mujuthaek_collector.sources.base import Fetcher

API_DELAY_SECONDS = 0.5  # 공공데이터포털은 프로그램 호출용 창구라 기관 사이트보다 짧은 간격으로 불러요
EMPTY_RETRIES = 3  # 공공데이터포털은 가끔 빈 응답을 줘요. 그만큼 다시 불러요


class NotJson(ValueError):
    """JSON이 아닌 응답 (공공데이터포털은 인증키 오류를 XML로 줘요)."""


@dataclass(frozen=True)
class RawResponse:
    api: str  # 출처마다 정한 API 이름 (list, detail, models …)
    url: str
    params: dict[str, str]
    fetched_at: str
    body: Any

    def to_dict(self) -> dict[str, Any]:
        return {"api": self.api, "url": self.url, "params": self.params, "fetchedAt": self.fetched_at, "body": self.body}


def redact(text: str, secret: str) -> str:
    """메시지에 들어간 인증키(원래 값과 주소에 넣은 값)를 지워요."""
    for value in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.quote_plus(secret)}:
        if value:
            text = text.replace(value, "***")
    return text


def fetch_json(client: Fetcher, api: str, url: str, service_key: str, params: dict[str, Any]) -> RawResponse:
    """공공데이터포털 API 한 번 호출. 빈 응답은 다시 불러요.
    차단(403·429·robots)은 BlockedError, 연결 오류는 httpx.HTTPError, JSON이 아니면 NotJson."""
    full_url = f"{url}?{urllib.parse.urlencode({'serviceKey': service_key, **params})}"
    text = ""
    for _ in range(EMPTY_RETRIES):
        try:
            text = client.text(full_url)
        except BlockedError as error:
            raise BlockedError(redact(str(error), service_key)) from None
        except httpx.HTTPError as error:
            raise httpx.HTTPError(redact(str(error), service_key)) from None
        if text.strip():
            break
    else:
        raise httpx.HTTPError(f"빈 응답이 {EMPTY_RETRIES}번 왔어요: {url}")
    try:
        body = json.loads(text)
    except ValueError:
        raise NotJson(f"JSON이 아닌 응답이 왔어요 (인증키·활용신청 확인): {url} {redact(text[:200], service_key)}") from None
    return RawResponse(
        api=api,
        url=url,
        params={k: str(v) for k, v in params.items()},
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        body=body,
    )


class PublicDataClient(PoliteClient):
    """팀 공통 요청 클라이언트 + 공공데이터 API 주소(api_hosts)만 짧은 간격. 인증키를 들고 다녀요(로그·오류에는 안 남겨요).
    공통 클라이언트가 도메인별 간격을 받게 되면 이 클래스는 지워요."""

    api_hosts: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        service_key: str | None,
        delay_seconds: float = 4.0,
        max_file_bytes: int = 30 * 1024 * 1024,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ):
        super().__init__(delay_seconds=delay_seconds, max_file_bytes=max_file_bytes, transport=transport, sleep=sleep)
        self.service_key = service_key

    def _wait(self, host: str) -> None:
        if host not in self.api_hosts:
            super()._wait(host)
            return
        elapsed = time.time() - self._last_request.get(host, 0.0)
        if elapsed < API_DELAY_SECONDS:
            self._sleep(API_DELAY_SECONDS - elapsed)
