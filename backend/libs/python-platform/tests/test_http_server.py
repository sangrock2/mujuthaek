"""A single slow loopback request must not create unlimited server workers."""

import http.client
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler

from mujuthaek_platform.http_server import BoundedHTTPServer


def test_worker_limit_and_total_deadline_release_capacity():
    started = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            started.set()

        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = BoundedHTTPServer(("127.0.0.1", 0), Handler, max_workers=1, socket_timeout=2, request_timeout=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(server.server_address, timeout=2) as slow:
            slow.sendall(b"GET /health HTTP/1.1\r\n")
            assert started.wait(1)
            with socket.create_connection(server.server_address, timeout=2) as extra:
                extra.sendall(b"GET /health HTTP/1.1\r\nHost: local\r\n\r\n")
                try:
                    reply = extra.recv(1024)
                except (ConnectionResetError, ConnectionAbortedError):
                    reply = b""  # Windows may reset a refused connection with unread request bytes.
                assert not reply or b" 503 " in reply
            try:
                assert slow.recv(1024) == b""
            except (ConnectionResetError, ConnectionAbortedError):
                pass
        deadline = time.monotonic() + 2
        while True:
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            try:
                connection.request("GET", "/health")
                status = connection.getresponse().status
            finally:
                connection.close()
            if status == 200:
                break
            assert status == 503 and time.monotonic() < deadline
            time.sleep(0.01)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
