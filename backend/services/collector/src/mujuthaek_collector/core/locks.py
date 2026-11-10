"""출처마다 따로 잡는 수집 잠금. 예전엔 잠금 하나로 모든 수집(게시판 전체 · 정책 · 관리자 요청)을 줄 세워서, 한 출처가 느리면 뒤 출처와
정책 수집이 밀리거나 건너뛰었어요(2026-10-27). 이제 같은 출처만 겹치지 않게 막아요."""

from __future__ import annotations

import threading


class SourceLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._busy: set[str] = set()

    def acquire(self, code: str) -> bool:
        """이 출처를 지금 수집해도 되면 잡고 True, 이미 수집 중이면 False(기다리지 않아요)."""
        with self._guard:
            if code in self._busy:
                return False
            self._busy.add(code)
            return True

    def release(self, code: str) -> None:
        with self._guard:
            self._busy.discard(code)

    def busy(self, code: str) -> bool:
        with self._guard:
            return code in self._busy
