"""기관 사이트에 예의 있게 요청하는 클라이언트.

- 모든 요청(이동한 주소 포함) 직전에 robots.txt 확인. robots.txt는 도메인마다 24시간 캐시
  (캐시는 프로세스 전체가 같이 써요. 회차마다 클라이언트를 새로 만들어도 기관마다 하루 한 번만 받아요)
- 같은 도메인은 정해진 간격(기본 4초)을 두고 요청
- 연결 오류·5xx는 2번까지 다시 시도, 403·429와 대기실 화면은 BlockedError로 그 출처 회차 중단
- 파일 다운로드는 크기 상한, 파일 대신 웹페이지가 오면 거부
- 응답 본문(페이지·파일·robots.txt)은 압축을 직접 조금씩 풀며 푼 크기로 상한을 봐요. 예전엔 httpx가 푼 조각을 받아 셌는데,
  httpx는 `Content-Encoding: gzip, gzip`처럼 겹친 압축을 상한 없이 한 조각에 풀어서 591바이트 응답 하나가 첫 조각에서
  268MB가 됐어요(2026-11-16 보안 감사 H-5). 그래서 압축은 gzip·deflate 한 겹만 받아요
"""

import json
import ssl
import time
import urllib.parse
import zlib
from collections.abc import Iterator
from typing import Any

import httpx

from mujuthaek_collector.config import USER_AGENT
from mujuthaek_collector.core.public_http import (
    PublicHTTPTransport,
    deadline_passed,
    request_deadline,
    validate_public_url,
)
from mujuthaek_collector.core.robots import ALLOW_ALL, MAX_ROBOTS_CHARS, RobotRules
from mujuthaek_collector.errors import BlockedError, FileNotReady, FileRejected, RobotsUnavailable

ROBOTS_TTL_SECONDS = 24 * 60 * 60
MAX_REDIRECTS = 5
READ_CHUNK = 64 * 1024  # 한 번에 풀어 올리는 최대 바이트
MAX_ROBOTS_BYTES = MAX_ROBOTS_CHARS  # robots.txt는 RFC 9309가 요구하는 앞 500KiB까지만 읽어요
# 요청 하나(주소 이동·다시 시도·본문 읽기 포함)의 전체 시한. 읽기마다 20초 시한만 있으면 19초마다 1바이트씩 보내는 서버 하나가
# 그 출처의 회차를 끝없이 붙잡았어요(2026-11-16 보안 감사 M-7)
PAGE_SECONDS = 120.0
FILE_SECONDS = 600.0
ROBOTS_SECONDS = 60.0


class UnsupportedEncoding(httpx.DecodingError):
    """두 겹 이상이거나 모르는 Content-Encoding. 상한 없이 풀리는 압축 폭탄을 막으려고 받지 않아요."""


class _BodyTooLarge(Exception):
    pass


class _Inflater:
    """gzip·deflate를 READ_CHUNK씩만 풀어요(zlib max_length). 작은 조각이 수백 MB로 풀려도 한 번에 메모리에 올리지 않아요."""

    def __init__(self, coding: str):
        self._raw_fallback = coding == "deflate"  # 'deflate'라면서 zlib 머리 없이 보내는 서버도 받아요 (httpx와 같은 처리)
        self._zlib = zlib.decompressobj(zlib.MAX_WBITS if coding == "deflate" else zlib.MAX_WBITS | 16)
        self._started = False

    def feed(self, data: bytes) -> Iterator[bytes]:
        while True:
            try:
                out = self._zlib.decompress(data, READ_CHUNK)
            except zlib.error:
                if self._raw_fallback and not self._started:
                    self._raw_fallback = False
                    self._zlib = zlib.decompressobj(-zlib.MAX_WBITS)
                    continue
                raise
            self._started = True
            data = self._zlib.unconsumed_tail
            if out:
                yield out
            if not data and len(out) < READ_CHUNK:  # 넣은 것을 다 풀었어요 (꽉 찼으면 아직 남은 출력이 있을 수 있어요)
                return

    def finish(self) -> Iterator[bytes]:
        yield from self.feed(b"")
        if tail := self._zlib.flush():
            yield tail


def _inflater(response: httpx.Response) -> _Inflater | None:
    header = response.headers.get("Content-Encoding", "")
    codings = [c for c in (part.strip().lower() for part in header.split(",")) if c and c != "identity"]
    if not codings:
        return None
    if len(codings) > 1 or codings[0] not in ("gzip", "x-gzip", "deflate"):
        raise UnsupportedEncoding(f"지원하지 않는 압축 방식이에요: {header[:100]}", request=response.request)
    return _Inflater(codings[0])


def read_body(response: httpx.Response, limit: int, *, truncate: bool = False) -> bytes:
    """스트리밍 응답의 본문을 압축을 직접 풀며 읽어요. 푼 크기가 limit을 넘으면 truncate면 거기까지, 아니면 _BodyTooLarge.

    응답은 닫지 않아요(부르는 쪽이 닫아요). 깨진 압축은 httpx와 같은 httpx.DecodingError예요.
    """
    if response.is_stream_consumed:  # 이미 읽힌 응답(시험용 MockTransport 등): 본문이 이미 메모리에 있어 크기만 봐요
        content = response.content
        if len(content) > limit and not truncate:
            raise _BodyTooLarge
        return content[:limit]
    inflater = _inflater(response)
    chunks: list[bytes] = []
    size = 0

    def pieces() -> Iterator[bytes]:
        # 크기를 정해 묶지 않아요(httpx가 64KB가 찰 때까지 모으면 그동안 시한·크기 검사를 못 해요). 받은 조각은 네트워크가 64KB 이하로 줘요
        for raw in response.iter_raw():
            yield from (inflater.feed(raw) if inflater else (raw,))
        if inflater:
            yield from inflater.finish()

    try:
        for piece in pieces():
            if deadline_passed():
                raise httpx.ReadTimeout("요청 전체 시간을 넘어 본문 읽기를 멈췄어요", request=response.request)
            size += len(piece)
            if size > limit:
                if truncate:
                    chunks.append(piece[: len(piece) - (size - limit)])
                    break
                raise _BodyTooLarge
            chunks.append(piece)
    except zlib.error as error:
        raise httpx.DecodingError(f"압축을 풀지 못했어요: {error}", request=response.request) from error
    return b"".join(chunks)


# (User-Agent, 도메인) → (받은 시각, 규칙). 스케줄러는 회차마다 PoliteClient를 새로 만들어서,
# 클라이언트 안에 캐시를 두면 매시 robots.txt를 다시 받아요. 그래서 프로세스 전체가 같이 써요.
_ROBOTS_CACHE: dict[tuple[str, str], tuple[float, RobotRules]] = {}


def clear_robots_cache() -> None:
    """테스트용: 저장해 둔 robots.txt 규칙을 비워요."""
    _ROBOTS_CACHE.clear()


def decode(response: httpx.Response, content: bytes) -> str:
    """응답 문자 인코딩: 헤더에 있으면 그대로(모르는 이름이면 httpx처럼 UTF-8), 없으면 UTF-8 → CP949(EUC-KR) 순서로."""
    if response.charset_encoding:
        return content.decode(response.encoding or "utf-8", errors="replace")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp949", errors="replace")


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
        max_page_bytes: int = 20 * 1024 * 1024,
        page_seconds: float = PAGE_SECONDS,
        file_seconds: float = FILE_SECONDS,
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
            # 직접 풀 수 있는 압축만 청해요(설치된 확장에 따라 br·zstd가 붙지 않게)
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
            verify=verify,
            follow_redirects=False,  # 이동하는 주소마다 robots.txt를 확인하려고 직접 따라감
            transport=transport if transport is not None else PublicHTTPTransport(verify if isinstance(verify, ssl.SSLContext) else None),
            trust_env=False,  # 환경 proxy가 목적지 DNS/IP 검사를 우회하지 못하게 해요
        )
        self._user_agent = user_agent
        self._delay = delay_seconds
        self._max_file_bytes = max_file_bytes
        self._max_page_bytes = max_page_bytes
        self._page_seconds = page_seconds
        self._file_seconds = file_seconds
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
        """페이지를 글자로 받아요. data가 있으면 폼 POST로 보내요. 압축을 푼 크기가 상한을 넘으면 그 페이지만 실패(httpx.DecodingError).
        전체 시한(page_seconds)을 넘으면 httpx.ReadTimeout이에요."""
        with request_deadline(self._page_seconds):
            response = self._send("POST" if data is not None else "GET", url, data=data, referer=referer)
            try:
                body = decode(response, read_body(response, self._max_page_bytes))
            except _BodyTooLarge:
                limit = self._max_page_bytes // 1024 // 1024
                raise httpx.DecodingError(f"페이지가 {limit}MB보다 커서 읽지 않아요: {url}", request=response.request) from None
            finally:
                response.close()
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
        """공고문 원본 파일. robots 허용 경로만, 크기 상한, 웹페이지가 오면 거부. 전체 시한(file_seconds)을 넘으면 httpx.ReadTimeout."""
        with request_deadline(self._file_seconds):
            return self._download(url, referer=referer)

    def _download(self, url: str, *, referer: str | None) -> bytes:
        try:
            response = self._send("GET", url, referer=referer)
        except RobotsUnavailable as error:  # 첨부 도메인의 robots.txt를 잠시 못 받음: 그 파일만 다음에 다시
            raise FileNotReady(str(error)) from error
        except BlockedError as error:
            if "robots.txt" in str(error):
                raise FileRejected(str(error)) from error
            raise
        too_large = f"파일이 {self._max_file_bytes // 1024 // 1024}MB보다 커서 받지 않아요"
        try:
            if "text/html" in (response.headers.get("Content-Type") or "").lower():
                raise FileNotReady("파일 대신 웹페이지가 왔어요 (점검 중이거나 주소·권한 확인 필요)")
            if int(response.headers.get("Content-Length") or 0) > self._max_file_bytes:
                raise FileRejected(too_large)
            return read_body(response, self._max_file_bytes)
        except _BodyTooLarge:
            raise FileRejected(too_large) from None
        except UnsupportedEncoding as error:
            raise FileRejected(f"{error} (받지 않아요)") from None
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
        with request_deadline(ROBOTS_SECONDS):  # 바깥 요청의 시한보다 늦어지지 않아요
            return self._fetch_rules(parts, host)

    def _fetch_rules(self, parts: urllib.parse.SplitResult, host: str) -> RobotRules:
        self._wait(host)
        robots_url = f"{parts.scheme or 'https'}://{host}/robots.txt"
        try:
            for _ in range(MAX_REDIRECTS + 1):
                validate_public_url(robots_url)
                response = self._client.send(self._client.build_request("GET", robots_url), stream=True)
                if not response.is_redirect:
                    break
                location = urllib.parse.urljoin(robots_url, response.headers.get("Location", ""))
                response.close()
                robots_url = location
            else:
                raise RobotsUnavailable("robots.txt 주소 이동이 너무 많아요")
            try:  # 앞 500KiB만 읽어요(넘으면 거기서 자름). 겹친 압축·깨진 압축은 받지 못한 것으로 봐요
                body = read_body(response, MAX_ROBOTS_BYTES, truncate=True) if response.status_code < 400 else b""
            finally:
                response.close()
        except httpx.HTTPError as error:
            raise RobotsUnavailable(f"robots.txt를 받지 못해 이 도메인은 요청하지 않아요: {host} ({error})") from error
        finally:
            self._last_request[host] = time.time()
        if 400 <= response.status_code < 500:
            rules = ALLOW_ALL  # robots.txt가 없으면(4xx) 표준상 전체 허용
        elif response.status_code >= 500:
            raise RobotsUnavailable(f"robots.txt 서버 오류({response.status_code})라 이 도메인은 요청하지 않아요: {host}")
        else:
            rules = RobotRules(decode(response, body), self._user_agent)
        _ROBOTS_CACHE[(self._user_agent, host)] = (time.time(), rules)
        return rules

    def _wait(self, host: str) -> None:
        elapsed = time.time() - self._last_request.get(host, 0.0)
        if elapsed < self._delay:
            self._sleep(self._delay - elapsed)

    def _send(self, method: str, url: str, *, data=None, referer=None, retries=2) -> httpx.Response:
        """스트리밍 응답을 돌려줘요. 본문은 read_body로 읽고 부르는 쪽이 닫아요."""
        for _ in range(MAX_REDIRECTS + 1):
            if not self.allowed(url):
                raise BlockedError(f"robots.txt가 막은 주소라 요청하지 않아요: {url}")
            response = self._send_once(method, url, data=data, referer=referer, retries=retries)
            if response.is_redirect:
                location = urllib.parse.urljoin(url, response.headers.get("Location", ""))
                response.close()
                if response.status_code in (301, 302, 303):
                    method, data = "GET", None
                referer, url = url, location
                continue
            return response
        raise BlockedError(f"주소 이동이 너무 많아요: {url}")

    def _send_once(self, method, url, *, data, referer, retries) -> httpx.Response:
        validate_public_url(url)
        host = urllib.parse.urlsplit(url).netloc
        headers = {"Referer": referer} if referer else {}
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._wait(host)
            try:
                request = self._client.build_request(method, url, data=data, headers=headers)
                response = self._client.send(request, stream=True)
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
