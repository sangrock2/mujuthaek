import gzip
import time
import tracemalloc
import zlib

import httpx
import pytest

from mujuthaek_collector.core.http_client import PoliteClient, clear_robots_cache
from mujuthaek_collector.errors import BlockedError, FileNotReady, FileRejected


def make_client(handler, **options):
    return PoliteClient(delay_seconds=0, transport=httpx.MockTransport(handler), sleep=lambda _: None, **options)


def streamed(raw: bytes, **headers) -> httpx.Response:
    """실제 전송처럼 본문을 아직 읽지 않은(압축된 그대로의) 응답. content=로 만들면 httpx가 미리 풀어 버려요."""
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(raw))


def robots(body="User-agent: *\nDisallow: /upload/\n"):
    return httpx.Response(200, text=body)


def test_redirect_to_disallowed_path_is_rejected():
    def handler(request):
        if request.url.path == "/robots.txt":
            return robots()
        if request.url.path == "/app/com/file/innoFD.do":
            return httpx.Response(302, headers={"Location": "/upload/secret.pdf"})
        return httpx.Response(200, content=b"%PDF")

    with make_client(handler) as client, pytest.raises(FileRejected):
        client.download("https://www.i-sh.co.kr/app/com/file/innoFD.do?seq=1")


def test_forbidden_stops_the_run():
    def handler(request):
        return robots() if request.url.path == "/robots.txt" else httpx.Response(429)

    with make_client(handler) as client, pytest.raises(BlockedError):
        client.text("https://a.kr/list.do")


def test_waiting_room_is_blocked_but_normal_page_with_script_is_fine():
    waiting = "<html><script src='netfunnel.js'></script><p>잠시만 기다려 주세요</p></html>"
    normal = "<html><script src='netfunnel.js'></script><table><tbody><tr><td>공고</td></tr></tbody></table></html>"

    def handler(request):
        if request.url.path == "/robots.txt":
            return robots()
        return httpx.Response(200, text=waiting if request.url.path == "/wait" else normal)

    with make_client(handler) as client:
        assert "공고" in client.text("https://a.kr/list")
        with pytest.raises(BlockedError):
            client.text("https://a.kr/wait")


def test_html_instead_of_file_is_rejected():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)  # robots.txt가 없으면 전체 허용
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<html>로그인</html>")

    with make_client(handler) as client, pytest.raises(FileNotReady):  # 점검 화면일 수 있어 다시 받을 수 있는 거절
        client.download("https://a.kr/download.do?id=1")


def test_an_attachment_domain_whose_robots_txt_fails_is_tried_again_later():
    # 2026-11-10 재검토: 첨부 도메인의 robots.txt를 받다 연결 오류·5xx가 나면 영구 거절(FileRejected)이 되어 그 파일 없이 새 버전이 생겼음
    def failing(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        return httpx.Response(200, content=b"%PDF")

    with make_client(failing) as client, pytest.raises(FileNotReady):
        client.download("https://flaky-robots.kr/f.pdf")
    with make_client(failing) as client, pytest.raises(BlockedError):  # 목록·상세는 그대로 회차를 멈춤
        client.text("https://flaky-robots.kr/list.do")

    def disallowed(request):
        return robots() if request.url.path == "/robots.txt" else httpx.Response(200, content=b"%PDF")

    with make_client(disallowed) as client, pytest.raises(FileRejected) as rejected:  # robots.txt가 막은 경로는 그대로 영구 거절
        client.download("https://strict-robots.kr/upload/a.pdf")
    assert not isinstance(rejected.value, FileNotReady)


def test_robots_txt_is_fetched_once_across_clients():
    """스케줄러는 회차마다 클라이언트를 새로 만들어요. 그래도 robots.txt는 도메인마다 하루 한 번만 받아요."""
    robots_requests = []

    def handler(request):
        if request.url.path == "/robots.txt":
            robots_requests.append(request.url.host)
            return robots()
        return httpx.Response(200, text="<table><tr><td>공고</td></tr></table>")

    for _ in range(3):  # 매시 회차 3번
        with make_client(handler) as client:
            client.text("https://a.kr/list.do")
    assert robots_requests == ["a.kr"]


def test_stacked_compression_is_refused_before_inflating():
    # 2026-11-16 보안 감사 H-5: httpx는 'gzip, gzip'을 상한 없이 한 조각에 풀어 591바이트가 268MB가 됐어요
    bomb = gzip.compress(gzip.compress(b"\0" * 1_000_000))

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return streamed(bomb, **{"Content-Type": "application/pdf", "Content-Encoding": "gzip, gzip"})

    with make_client(handler) as client:
        with pytest.raises(FileRejected, match="압축"):
            client.download("https://bomb.example/notice.pdf")
        with pytest.raises(httpx.DecodingError):
            client.text("https://bomb.example/list.do")


def test_gzip_body_is_inflated_in_small_pieces_and_capped():
    bomb = gzip.compress(b"\0" * 30 * 1024 * 1024)  # 약 30KB가 30MB로 풀려요
    plain = "공고 목록 " * 1000

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/list.do":
            return streamed(gzip.compress(plain.encode()), **{"Content-Encoding": "gzip", "Content-Type": "text/html; charset=utf-8"})
        return streamed(bomb, **{"Content-Type": "application/pdf", "Content-Encoding": "gzip"})

    with make_client(handler, max_file_bytes=1024 * 1024) as client:
        assert client.text("https://zip.example/list.do") == plain
        tracemalloc.start()
        try:
            with pytest.raises(FileRejected, match="1MB"):
                client.download("https://zip.example/notice.pdf")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert peak < 8 * 1024 * 1024  # 한 조각에 30MB를 풀던 예전과 달리 상한 근처에서 멈춰요


def test_deflate_with_or_without_zlib_header_and_page_cap():
    text = "청년 매입임대 " * 200
    raw_deflate = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw_body = raw_deflate.compress(text.encode()) + raw_deflate.flush()

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/zlib":
            return streamed(zlib.compress(text.encode()), **{"Content-Encoding": "deflate"})
        if request.url.path == "/raw":
            return streamed(raw_body, **{"Content-Encoding": "deflate"})
        return streamed(b"x" * 5000)

    with make_client(handler, max_page_bytes=4096) as client:
        assert client.text("https://deflate.example/zlib") == text
        assert client.text("https://deflate.example/raw") == text
        with pytest.raises(httpx.DecodingError, match="0MB"):
            client.text("https://deflate.example/big")


class SlowStream(httpx.SyncByteStream):
    def __iter__(self):
        for _ in range(100):
            time.sleep(0.02)
            yield b"x" * 10


def test_slow_body_is_cut_at_the_request_deadline():
    # 보안 감사 M-7: 본문을 조금씩 끝없이 보내도 페이지 하나가 전체 시한을 넘기지 못해요
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, stream=SlowStream())

    started = time.monotonic()
    with make_client(handler, page_seconds=0.2) as client, pytest.raises(httpx.ReadTimeout):
        client.text("https://slow.example/list.do")
    assert time.monotonic() - started < 1.5


def test_robots_txt_with_stacked_compression_is_unavailable_and_long_one_is_cut():
    clear_robots_cache()

    def stacked(request):
        if request.url.path == "/robots.txt":
            return streamed(gzip.compress(gzip.compress(b"User-agent: *\nDisallow:\n")), **{"Content-Encoding": "gzip, gzip"})
        return streamed(b"%PDF")

    with make_client(stacked) as client:
        with pytest.raises(BlockedError):
            client.text("https://stacked-robots.example/list.do")
        with pytest.raises(FileNotReady):
            client.download("https://stacked-robots.example/a.pdf")

    def long_robots(request):
        if request.url.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /early\n#" + b"x" * (600 * 1024) + b"\nDisallow: /late\n"
            return streamed(gzip.compress(body), **{"Content-Encoding": "gzip"})
        return streamed("<table><tr><td>공고</td></tr></table>".encode())

    with make_client(long_robots) as client:
        assert "공고" in client.text("https://long-robots.example/late/list.do")
        with pytest.raises(BlockedError):
            client.text("https://long-robots.example/early/list.do")
