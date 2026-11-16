"""작은 내부 HTTP 서버의 연결 수·소켓 대기·요청 전체 시한을 제한합니다."""

import socket
import threading
from http.server import ThreadingHTTPServer


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(
        self, address, handler, *, max_workers: int = 16, socket_timeout: float = 10, request_timeout: float = 60
    ):
        if max_workers < 1 or socket_timeout <= 0 or request_timeout <= 0:
            raise ValueError("HTTP server budgets must be positive")
        self._slots = threading.BoundedSemaphore(max_workers)
        self.socket_timeout = socket_timeout
        self.request_timeout = request_timeout
        super().__init__(address, handler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(self.socket_timeout)
        return request, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def finish_request(self, request, client_address):
        # 조금씩 보내며 idle timeout을 피하는 연결도 정해진 시간 뒤 닫아요.
        expired = threading.Event()
        timer = threading.Timer(self.request_timeout, self._expire, args=(request, expired))
        timer.daemon = True
        timer.start()
        try:
            super().finish_request(request, client_address)
        except OSError:
            if not expired.is_set():
                raise
        finally:
            timer.cancel()

    @staticmethod
    def _expire(request, expired):
        expired.set()
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        request.close()
