import socket
import time

import httpcore
import httpx
import pytest

from mujuthaek_collector.core import public_http
from mujuthaek_collector.core.http_client import PoliteClient
from mujuthaek_collector.core.public_http import (
    MAX_CONNECT_ADDRESSES,
    PublicHTTPTransport,
    PublicNetworkBackend,
    deadline_passed,
    remaining,
    request_deadline,
    validate_public_url,
)
from mujuthaek_collector.errors import BlockedError


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "http://10.0.0.1/a",
        "http://169.254.169.254/a",
        "http://[::1]/a",
        "http://[::ffff:127.0.0.1]/a",
        "http://[64:ff9b::7f00:1]/a",
        "http://[fd00::1]/a",
        "http://[fec0::1]/a",  # 폐기된 site-local: ipaddress가 사설로 보지 않아요
        "http://224.0.0.1/a",
        "http://localhost/a",
        "file:///etc/passwd",
        "ftp://public.example/a",
        "https://user:password@public.example/a",
    ],
)
def test_unsafe_url_is_rejected_without_any_request(url):
    seen = []
    with PoliteClient(transport=httpx.MockTransport(lambda request: seen.append(request))) as client:
        with pytest.raises(BlockedError):
            client.download(url)
    assert not seen


@pytest.mark.parametrize("robots_redirect", [False, True])
def test_redirect_to_internal_network_is_blocked_before_request(robots_redirect):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt" and not robots_redirect:
            return httpx.Response(404)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/secret"})

    with PoliteClient(delay_seconds=0, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BlockedError):
            client.download("https://public.example/file.pdf")
    assert seen and all(url.startswith("https://public.example/") for url in seen)


def answer(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (address, 443))


class RecordingStream(httpcore.NetworkStream):
    def __init__(self):
        self.sni = None
        self.written = b""
        self.response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"

    def read(self, max_bytes, timeout=None):
        data, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return data

    def write(self, buffer, timeout=None):
        self.written += buffer

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        assert ssl_context.check_hostname
        self.sni = server_hostname
        return self

    def close(self):
        pass


class RecordingBackend(httpcore.NetworkBackend):
    def __init__(self):
        self.hosts = []
        self.stream = RecordingStream()

    def connect_tcp(self, host, port, **kwargs):
        self.hosts.append(host)
        return self.stream


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["169.254.169.254"], ["93.184.216.34", "10.0.0.1"], ["::1"], []])
def test_dns_private_mixed_and_empty_answers_are_blocked(addresses):
    network = RecordingBackend()
    backend = PublicNetworkBackend(network, lambda *args, **kwargs: [answer(ip) for ip in addresses])
    with pytest.raises(BlockedError):
        backend.connect_tcp("public.example", 443)
    assert network.hosts == []


@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "0177.0.0.1", "127.1", "metadata.example"])
def test_noncanonical_or_named_private_target_never_connects(host):
    network = RecordingBackend()
    transport = PublicHTTPTransport(network_backend=PublicNetworkBackend(network, lambda *args, **kwargs: [answer("127.0.0.1")]))
    with httpx.Client(transport=transport, trust_env=False) as client, pytest.raises((BlockedError, httpx.InvalidURL)):
        client.get(f"http://{host}/not-sent")
    assert network.hosts == []


def test_connection_uses_checked_numeric_ip_and_preserves_tls_name_and_host():
    network = RecordingBackend()
    resolutions = []

    def resolver(host, port, **kwargs):
        resolutions.append(host)
        return [answer("93.184.216.34")] if len(resolutions) == 1 else [answer("127.0.0.1")]

    transport = PublicHTTPTransport(network_backend=PublicNetworkBackend(network, resolver))
    with httpx.Client(transport=transport, trust_env=False) as client:
        assert client.get("https://public.example/file.pdf").text == "ok"
    assert resolutions == ["public.example"]
    assert network.hosts == ["93.184.216.34"]
    assert network.stream.sni == "public.example"
    assert b"Host: public.example\r\n" in network.stream.written


class DrippingStream(RecordingStream):
    """읽기마다의 시한 안쪽으로 한 바이트씩 아주 천천히 보내는 서버."""

    def __init__(self):
        super().__init__()
        self.timeouts = []

    def read(self, max_bytes, timeout=None):
        self.timeouts.append(timeout)
        time.sleep(0.05)
        return b"H"


def test_deadline_budget_is_exact_at_large_clock_values(monkeypatch):
    now = [10**18]
    monkeypatch.setattr(public_http.time, "monotonic_ns", lambda: now[0])
    with request_deadline(0.3):
        assert remaining(None) == 0.3
        now[0] += 50_000_000
        assert remaining(None) == 0.25
        assert remaining(0.1) == 0.1
        with request_deadline(10):
            assert remaining(None) == 0.25
        with request_deadline(0.1):
            assert remaining(None) == 0.1
        assert remaining(None) == 0.25
        now[0] += 250_000_000
        assert deadline_passed()
        with pytest.raises(httpcore.ReadTimeout):
            remaining(None)
    assert not deadline_passed()
    assert remaining(2) == 2


def test_a_server_dripping_bytes_cannot_outlive_the_request_deadline():
    # 보안 감사 M-7: 읽기마다 시한이 새로 시작해서, 시한 안쪽으로 한 바이트씩 보내면 요청이 끝나지 않았어요
    network = RecordingBackend()
    network.stream = DrippingStream()
    transport = PublicHTTPTransport(network_backend=PublicNetworkBackend(network, lambda *args, **kwargs: [answer("93.184.216.34")]))
    started = time.monotonic()
    with httpx.Client(transport=transport, trust_env=False) as client, request_deadline(0.3):
        with pytest.raises(httpx.ReadTimeout):
            client.get("http://public.example/slow")
    assert time.monotonic() - started < 2
    assert network.stream.timeouts and all(t is not None and t <= 0.3 for t in network.stream.timeouts)


def test_only_the_first_dns_answers_are_tried():
    attempts = []

    class Unreachable(httpcore.NetworkBackend):
        def connect_tcp(self, host, port, **kwargs):
            attempts.append(host)
            raise httpcore.ConnectError("black hole")

    addresses = [f"93.184.216.{n}" for n in range(1, 21)]
    backend = PublicNetworkBackend(Unreachable(), lambda *args, **kwargs: [answer(ip) for ip in addresses])
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("public.example", 443)
    assert attempts == addresses[:MAX_CONNECT_ADDRESSES]


def test_dns_rebinding_is_rechecked_for_new_connections():
    replies = iter([[answer("93.184.216.34")], [answer("127.0.0.1")]])
    network = RecordingBackend()
    backend = PublicNetworkBackend(network, lambda *args, **kwargs: next(replies))
    backend.connect_tcp("public.example", 443)
    with pytest.raises(BlockedError):
        backend.connect_tcp("public.example", 443)
    assert network.hosts == ["93.184.216.34"]


def test_public_url_and_cross_domain_robots_redirect_still_work():
    validate_public_url("https://93.184.216.34/file.pdf")

    def handler(request):
        if request.url.path == "/robots.txt" and request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "https://cdn.example/robots.txt"})
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, content=b"%PDF-public")

    with PoliteClient(delay_seconds=0, transport=httpx.MockTransport(handler)) as client:
        assert client.download("https://public.example/file.pdf") == b"%PDF-public"
