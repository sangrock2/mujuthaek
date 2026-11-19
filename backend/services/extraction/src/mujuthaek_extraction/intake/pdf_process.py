"""PDF 파서는 별도 프로세스에서 실행해 검수 HTTP 처리와 자원을 분리합니다."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
TIMEOUT_SECONDS = 180
_slots = threading.BoundedSemaphore(1)
_PASSED_ENV = ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONUTF8", "PYTHONIOENCODING")


def run_pdf(data: bytes, mode: str, max_pages: int) -> Any:
    """시간·입출력 한도를 넘거나 손상된 PDF는 읽기 실패(None)로 처리합니다."""
    if len(data) > MAX_INPUT_BYTES or mode not in {"document", "images"} or not 0 <= max_pages <= 300:
        return None
    if not _slots.acquire(timeout=TIMEOUT_SECONDS):
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="mujuthaek-pdf-") as folder:
            work = Path(folder)
            source, output = work / "source.pdf", work / "result.json"
            source.write_bytes(data)
            env = {key: os.environ[key] for key in _PASSED_ENV if key in os.environ}
            env.update(HOME=folder, TMPDIR=folder, TEMP=folder, TMP=folder)
            command = [sys.executable, "-I", str(Path(__file__).with_name("pdf_worker.py")), str(source), mode, str(max_pages)]
            with output.open("wb") as target:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=target, stderr=subprocess.DEVNULL, cwd=folder, env=env)
                deadline = time.monotonic() + TIMEOUT_SECONDS
                try:
                    while process.poll() is None:
                        if time.monotonic() >= deadline or output.stat().st_size > MAX_OUTPUT_BYTES:
                            return None
                        try:
                            process.wait(timeout=0.1)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()  # 자식을 반드시 회수해 PID가 쌓이지 않게 합니다
            if process.returncode != 0 or output.stat().st_size > MAX_OUTPUT_BYTES:
                return None
            return json.loads(output.read_bytes())
    except (OSError, ValueError):
        return None
    finally:
        _slots.release()
