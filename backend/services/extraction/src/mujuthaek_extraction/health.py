"""워커 각 부분(큐 소비·이벤트 발행·다시 처리)의 생존 신호. /health가 이것으로 판단합니다.

예전 /health는 검수 API 스레드만 살아 있으면 정상이라, 큐 소비가 멈추거나 발행기가 계속 다시 연결해도
컨테이너는 정상으로 보였습니다(검토 2026-10-16). 이제 부분마다 정해진 시간 안에 신호가 없으면 503입니다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class Health:
    """워커 부분별 마지막 신호 시각을 스레드 안전하게 모아 두고, 정해진 시간 안에 신호가 왔는지 보고합니다."""

    def __init__(self, limits: dict[str, float], clock: Callable[[], float] = time.monotonic):
        """limits: 부분 이름 → 이 초 안에 신호가 있어야 정상. 시작 직후에는 같은 시간만큼 기다려 줍니다."""
        self.limits = limits
        self.clock = clock
        self.started = clock()
        self.beats: dict[str, float] = {}
        self._lock = threading.Lock()

    def beat(self, name: str) -> None:
        with self._lock:
            self.beats[name] = self.clock()

    def report(self) -> tuple[bool, dict[str, str]]:
        now = self.clock()
        parts = {}
        with self._lock:
            for name, limit in self.limits.items():
                last = self.beats.get(name)
                if last is None:
                    parts[name] = "starting" if now - self.started <= limit else "no signal"
                else:
                    parts[name] = "ok" if now - last <= limit else f"stale {int(now - last)}s"
        return all(state in ("ok", "starting") for state in parts.values()), parts
