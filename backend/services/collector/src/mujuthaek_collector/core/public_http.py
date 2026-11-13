"""Public-web transport: validate URLs and pin each connection to checked DNS answers."""

import ipaddress
import socket
import ssl
from contextlib import contextmanager

import httpcore
import httpx

from mujuthaek_collector.errors import BlockedError


def public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Do not let IPv4-in-IPv6 transition mechanisms reach a private IPv4 target.
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if address in ipaddress.ip_network("64:ff9b::/96") or address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return True


def validate_public_url(url: str) -> None:
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in ("http", "https") or not parsed.host or parsed.userinfo:
            raise ValueError
        # Numeric and noncanonical IP spellings still go through DNS validation at connect time.
        try:
            ipaddress.ip_address(parsed.host)
        except ValueError:
            if parsed.host.lower().rstrip(".") == "localhost" or "%" in parsed.host:
                raise ValueError from None
        else:
            if not public_ip(parsed.host):
                raise ValueError
    except (ValueError, httpx.InvalidURL) as error:
        # Never echo URL queries (institution API keys) into errors/logs.
        raise BlockedError("공개 HTTP(S) 주소가 아니어서 요청하지 않아요") from error


class PublicNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, backend=None, resolver=None):
        self.backend = backend if backend is not None else httpcore.SyncBackend()
        self.resolver = resolver if resolver is not None else socket.getaddrinfo

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            answers = self.resolver(host, port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise httpcore.ConnectError("기관 주소를 해석하지 못했어요") from error
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses or any(not public_ip(address) for address in addresses):
            raise BlockedError("공개 IP가 아닌 목적지라 요청하지 않아요")
        last_error = None
        for address in addresses:
            try:
                # Connect to the checked numeric IP, never re-resolve the original hostname.
                # httpcore retains the original hostname for TLS SNI/certificate validation and pooling.
                return self.backend.connect_tcp(
                    str(ipaddress.ip_address(address)),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last_error = error
        raise last_error


@contextmanager
def map_errors():
    try:
        yield
    except (httpcore.TimeoutException, httpcore.NetworkError, httpcore.ProtocolError, httpcore.ProxyError, httpcore.UnsupportedProtocol) as error:
        target = getattr(httpx, type(error).__name__, httpx.TransportError)
        raise target(str(error)) from error


class PublicResponseStream(httpx.SyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        with map_errors():
            yield from self.stream

    def close(self):
        with map_errors():
            self.stream.close()


class PublicHTTPTransport(httpx.BaseTransport):
    def __init__(self, ssl_context: ssl.SSLContext | None = None, network_backend=None):
        self.pool = httpcore.ConnectionPool(
            ssl_context=ssl_context if ssl_context is not None else httpcore.default_ssl_context(),
            network_backend=network_backend if network_backend is not None else PublicNetworkBackend(),
        )

    def handle_request(self, request):
        validate_public_url(str(request.url))
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host, port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with map_errors():
            response = self.pool.handle_request(core_request)
        return httpx.Response(response.status, headers=response.headers, stream=PublicResponseStream(response.stream), extensions=response.extensions)

    def close(self):
        self.pool.close()
