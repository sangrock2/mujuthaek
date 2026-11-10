"""UUID v7 (RFC 9562). 앞 48비트가 밀리초 시각이라 만든 순서대로 정렬돼요. DB 기본 키에 써요.

파이썬 3.12 표준 라이브러리에는 uuid7이 없어서 직접 만들어요. 같은 밀리초 안에서도 순서가 지켜지게
rand_a(12비트)를 1씩 늘리고, 넘치면 다음 밀리초로 넘겨요.
"""

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = 0
_counter = 0


def uuid7() -> uuid.UUID:
    global _last_ms, _counter
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms > _last_ms:
            _last_ms, _counter = now_ms, int.from_bytes(os.urandom(2), "big") & 0x7FF  # 위쪽 절반은 여유로 남겨요
        else:
            _counter += 1
            if _counter > 0xFFF:  # 같은 밀리초에 4096개를 넘으면 다음 밀리초 값으로 넘어가요
                _last_ms, _counter = _last_ms + 1, 0
        ms, counter = _last_ms, _counter
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | rand_b
    return uuid.UUID(int=value)
