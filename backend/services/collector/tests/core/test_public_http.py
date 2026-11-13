import socket

import httpcore
import httpx
import pytest

from mujuthaek_collector.core.http_client import PoliteClient
from mujuthaek_collector.core.public_http import PublicHTTPTransport, PublicNetworkBackend, validate_public_url
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
