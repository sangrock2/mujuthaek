"""API 요청 클라이언트 감싸기. 인증키가 주소(serviceKey=…, apiKeyNm=…)에 들어가서,
오류 메시지에 주소가 찍히면 키가 DB(crawl_runs.error, raw_policies.last_error)와 로그에 남아요. 그래서 가려요."""

from __future__ import annotations

import urllib.parse

import httpx

from mujuthaek_collector.errors import BlockedError, CollectorError, FileRejected, ParseError
from mujuthaek_collector.sources.base import Fetcher


class ApiError(CollectorError):
    """API 요청이 실패했어요 (401이 아닌 HTTP 오류·연결 실패). 그 정책만 FAILED로 두고 다음 회차에 다시 시도해요."""


def mask(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if not secret:
            continue
        for form in {secret, urllib.parse.quote(secret, safe=""), urllib.parse.quote_plus(secret)}:
            text = text.replace(form, "***")
    return text


class MaskedFetcher:
    """Fetcher 규격 그대로, 오류 메시지에서 인증키만 가려요. 원래 예외는 이어 붙이지 않아요(traceback에도 키가 나와서)."""

    def __init__(self, inner: Fetcher, secrets: list[str]):
        self.inner = inner
        self.secrets = [s for s in secrets if s]

    def text(self, url: str, *, data: dict[str, str] | None = None, referer: str | None = None) -> str:
        try:
            return self.inner.text(url, data=data, referer=referer)
        except BlockedError as error:
            raise BlockedError(mask(str(error), self.secrets)) from None
        except (ParseError, FileRejected) as error:
            raise type(error)(mask(str(error), self.secrets)) from None
        except httpx.HTTPStatusError as error:
            # 401은 인증키 문제(보조금24는 키 오류를 HTTP 401로 줘요). 정책 탓으로 FAILED를 쌓으면 키를 고쳐도 다시 열지 않아서 회차를 멈춰요
            if error.response.status_code == 401:
                raise BlockedError(mask(f"인증키가 거부됐어요 (HTTP 401): {error}", self.secrets)) from None
            raise ApiError(mask(f"{type(error).__name__}: {error}", self.secrets)) from None
        except httpx.HTTPError as error:
            raise ApiError(mask(f"{type(error).__name__}: {error}", self.secrets)) from None

    def download(self, url: str, *, referer: str | None = None) -> bytes:
        return self.inner.download(url, referer=referer)

    def close(self) -> None:
        close = getattr(self.inner, "close", None)
        if close:
            close()
