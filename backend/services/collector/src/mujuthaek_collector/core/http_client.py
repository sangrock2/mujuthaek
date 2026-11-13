"""기관 사이트에 예의 있게 요청하는 클라이언트.

- 모든 요청(이동한 주소 포함) 직전에 robots.txt 확인. robots.txt는 도메인마다 24시간 캐시
  (캐시는 프로세스 전체가 같이 써요. 회차마다 클라이언트를 새로 만들어도 기관마다 하루 한 번만 받아요)
- 같은 도메인은 정해진 간격(기본 4초)을 두고 요청
- 연결 오류·5xx는 2번까지 다시 시도, 403·429와 대기실 화면은 BlockedError로 그 출처 회차 중단
- 파일 다운로드는 크기 상한, 파일 대신 웹페이지가 오면 거부
"""

import json
import ssl
import time
import urllib.parse
from typing import Any

import httpx

from mujuthaek_collector.config import USER_AGENT
from mujuthaek_collector.core.public_http import PublicHTTPTransport, validate_public_url
from mujuthaek_collector.core.robots import ALLOW_ALL, RobotRules
from mujuthaek_collector.errors import BlockedError, FileNotReady, FileRejected, RobotsUnavailable

ROBOTS_TTL_SECONDS = 24 * 60 * 60
MAX_REDIRECTS = 5

# (User-Agent, 도메인) → (받은 시각, 규칙). 스케줄러는 회차마다 PoliteClient를 새로 만들어서,
# 클라이언트 안에 캐시를 두면 매시 robots.txt를 다시 받아요. 그래서 프로세스 전체가 같이 써요.
_ROBOTS_CACHE: dict[tuple[str, str], tuple[float, RobotRules]] = {}


def clear_robots_cache() -> None:
    """테스트용: 저장해 둔 robots.txt 규칙을 비워요."""
    _ROBOTS_CACHE.clear()


def decode(response: httpx.Response) -> str:
    """응답 문자 인코딩: 헤더에 있으면 그대로, 없으면 UTF-8 → CP949(EUC-KR) 순서로."""
    if response.charset_encoding:
        return response.text
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        return response.content.decode("cp949", errors="replace")


def looks_like_waiting_room(html: str) -> bool:
    """대기실(NetFunnel 등) 화면인지. SH는 정상 페이지에도 NetFunnel 스크립트가 들어 있어서,
    스크립트가 있어도 표나 충분한 본문이 있으면 정상 페이지로 봐요."""
    lower = html.lower()
    if "netfunnel" not in lower:
        return False
    if "<tbody" in lower or "<table" in lower:
        return False
    visible = len("".join(part for part in lower.split("<") if ">" in part))
    return visible < 1500


class PoliteClient:
    def __init__(
        self,
        *,
        delay_seconds: float = 4.0,
        legacy_tls: bool = False,
        timeout: float = 20.0,
        max_file_bytes: int = 30 * 1024 * 1024,
        user_agent: str = USER_AGENT,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ):
        verify: ssl.SSLContext | bool = True
        if legacy_tls:  # 예전 보안 연결만 받는 기관용. 인증서 확인은 유지하고 예전 암호 방식만 추가로 허용
            context = ssl.create_default_context()
            context.set_ciphers("DEFAULT:@SECLEVEL=1")
            context.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
            verify = context
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            verify=verify,
            follow_redirects=False,  # 이동하는 주소마다 robots.txt를 확인하려고 직접 따라감
            transport=transport if transport is not None else PublicHTTPTransport(verify if isinstance(verify, ssl.SSLContext) else None),
            trust_env=False,  # 환경 proxy가 목적지 DNS/IP 검사를 우회하지 못하게 해요
        )
        self._user_agent = user_agent
        self._delay = delay_seconds
        self._max_file_bytes = max_file_bytes
        self._last_request: dict[str, float] = {}
        self._sleep = sleep

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── 공개 메서드 ──────────────────────────────────────────────────────
    def allowed(self, url: str) -> bool:
        return self._rules_for(url).can_fetch(url)

    def text(self, url: str, *, data: dict[str, str] | None = None, referer: str | None = None) -> str:
        """페이지를 글자로 받아요. data가 있으면 폼 POST로 보내요."""
        response = self._send("POST" if data is not None else "GET", url, data=data, referer=referer)
        body = decode(response)
        if looks_like_waiting_room(body):
            raise BlockedError(f"대기실 화면이 와서 이번 회차를 멈춰요: {url}")
        return body

    def json(self, url: str, *, referer: str | None = None) -> Any:
        body = self.text(url, referer=referer)
        try:
            return json.loads(body)
        except ValueError as error:
            raise BlockedError(f"JSON 대신 다른 응답이 왔어요 (구조 변경 또는 차단): {url}") from error

    def download(self, url: str, *, referer: str | None = None) -> bytes:
        """공고문 원본 파일. robots 허용 경로만, 크기 상한, 웹페이지가 오면 거부."""
        try:
            response = self._send("GET", url, referer=referer, stream=True)
        except RobotsUnavailable as error:  # 첨부 도메인의 robots.txt를 잠시 못 받음: 그 파일만 다음에 다시
            raise FileNotReady(str(error)) from error
        except BlockedError as error:
            if "robots.txt" in str(error):
                raise FileRejected(str(error)) from error
            raise
        try:
            if "text/html" in (response.headers.get("Content-Type") or "").lower():
                raise FileNotReady("파일 대신 웹페이지가 왔어요 (점검 중이거나 주소·권한 확인 필요)")
            if int(response.headers.get("Content-Length") or 0) > self._max_file_bytes:
                raise FileRejected(f"파일이 {self._max_file_bytes // 1024 // 1024}MB보다 커서 받지 않아요")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self._max_file_bytes:
                    raise FileRejected(f"파일이 {self._max_file_bytes // 1024 // 1024}MB보다 커서 받지 않아요")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            response.close()

    # ── 내부 ──────────────────────────────────────────────────────────
    def _rules_for(self, url: str) -> RobotRules:
        validate_public_url(url)
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc
        cached = _ROBOTS_CACHE.get((self._user_agent, host))
        if cached and time.time() - cached[0] < ROBOTS_TTL_SECONDS:
            return cached[1]
        self._wait(host)
        robots_url = f"{parts.scheme or 'https'}://{host}/robots.txt"
        try:
            for _ in range(MAX_REDIRECTS + 1):
                validate_public_url(robots_url)
                response = self._client.get(robots_url)
                if not response.is_redirect:
                    break
                location = urllib.parse.urljoin(robots_url, response.headers.get("Location", ""))
                response.close()
                robots_url = location
            else:
                raise RobotsUnavailable("robots.txt 주소 이동이 너무 많아요")
        except httpx.HTTPError as error:
            raise RobotsUnavailable(f"robots.txt를 받지 못해 이 도메인은 요청하지 않아요: {host} ({error})") from error
        finally:
            self._last_request[host] = time.time()
        if 400 <= response.status_code < 500:
            rules = ALLOW_ALL  # robots.txt가 없으면(4xx) 표준상 전체 허용
        elif response.status_code >= 500:
            raise RobotsUnavailable(f"robots.txt 서버 오류({response.status_code})라 이 도메인은 요청하지 않아요: {host}")
        else:
            rules = RobotRules(decode(response), self._user_agent)
        _ROBOTS_CACHE[(self._user_agent, host)] = (time.time(), rules)
        return rules

    def _wait(self, host: str) -> None:
        elapsed = time.time() - self._last_request.get(host, 0.0)
        if elapsed < self._delay:
            self._sleep(self._delay - elapsed)

    def _send(self, method: str, url: str, *, data=None, referer=None, stream=False, retries=2) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            if not self.allowed(url):
                raise BlockedError(f"robots.txt가 막은 주소라 요청하지 않아요: {url}")
            response = self._send_once(method, url, data=data, referer=referer, stream=stream, retries=retries)
            if response.is_redirect:
                location = urllib.parse.urljoin(url, response.headers.get("Location", ""))
                response.close()
                if response.status_code in (301, 302, 303):
                    method, data = "GET", None
                referer, url = url, location
                continue
            return response
        raise BlockedError(f"주소 이동이 너무 많아요: {url}")

    def _send_once(self, method, url, *, data, referer, stream, retries) -> httpx.Response:
        validate_public_url(url)
        host = urllib.parse.urlsplit(url).netloc
        headers = {"Referer": referer} if referer else {}
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._wait(host)
            try:
                request = self._client.build_request(method, url, data=data, headers=headers)
                response = self._client.send(request, stream=stream)
            except httpx.TransportError as error:
                last_error = error
                self._last_request[host] = time.time()
                self._sleep(self._delay * (2**attempt))
                continue
            self._last_request[host] = time.time()
            if response.status_code in (403, 429):
                response.close()
                raise BlockedError(f"HTTP {response.status_code} 응답이라 이번 회차를 멈춰요: {url}")
            if response.status_code >= 500 and attempt < retries:
                response.close()
                self._sleep(self._delay * (2**attempt))
                continue
            if response.status_code >= 400:
                response.close()
                raise httpx.HTTPStatusError(f"HTTP {response.status_code}: {url}", request=request, response=response)
            return response
        raise httpx.ConnectError(f"연결 실패: {url} ({last_error})")
