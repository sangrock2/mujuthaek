"""HWP 변환. pyhwp의 hwp5html로 HTML을 만들면 표 구조(합쳐진 칸 포함)가 살아 있어요.

변환기는 외부에서 받은 파일을 읽는 별도 프로세스라서(2026-11-16 보안 감사 4장)
- 환경변수는 변환에 필요한 것(PATH·임시 폴더·로캘)만 넘겨요. 수집기 환경에는 DB·AWS·API 비밀값이 들어 있어요
- 표준 출력·오류와 만든 HTML 파일의 크기를 한도까지만 받고, 넘으면 프로세스를 끝내요
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_SECONDS = 180
MAX_TEXT_BYTES = 50 * 1024 * 1024  # hwp5txt 출력·hwp5html 파일. HWPX 해제 상한(MAX_HWPX_BYTES)과 같아요
MAX_ERROR_BYTES = 64 * 1024  # 오류 출력은 마지막 줄만 써요
READ_CHUNK = 64 * 1024
WATCH_SECONDS = 0.2  # 만드는 HTML 파일 크기를 이 간격으로 확인해요
# 변환기에 넘기는 환경변수. Windows에서 파이썬을 띄우려면 SYSTEMROOT가 필요해요
PASSED_ENV = ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONUTF8", "PYTHONIOENCODING")


class OutputTooLarge(Exception):
    """변환기 출력이 한도를 넘어 프로세스를 끝냈어요."""


@dataclass(frozen=True)
class Finished:
    returncode: int
    stdout: bytes
    stderr: bytes


def tool(name: str) -> str | None:
    """pyhwp 명령 경로. 가상환경을 켜지 않고 .venv/bin/python으로 실행한 경우도 찾아요."""
    sibling = os.path.join(os.path.dirname(sys.executable), name)
    return shutil.which(name) or (sibling if os.path.exists(sibling) else None)


def converter_env(work_dir: Path) -> dict[str, str]:
    """변환기 환경변수: 허용한 것만 남기고, 홈·임시 폴더는 이번 변환의 임시 폴더로 둬요."""
    env = {key: os.environ[key] for key in PASSED_ENV if key in os.environ}
    folder = str(work_dir)
    env.update(HOME=folder, TMPDIR=folder, TEMP=folder, TMP=folder)
    return env


def _drain(stream, limit: int, chunks: list[bytes], overflow: threading.Event | None, process: subprocess.Popen) -> None:
    """파이프를 끝까지 비워요. overflow가 있으면 한도를 넘을 때 프로세스를 끝내고, 없으면 마지막 limit바이트만 남겨요(오류 출력)."""
    size = 0
    try:
        while chunk := stream.read1(READ_CHUNK):
            size += len(chunk)
            chunks.append(chunk)
            if size <= limit:
                continue
            if overflow is not None:
                overflow.set()
                process.kill()
                return
            tail = b"".join(chunks)[-limit:]
            chunks[:] = [tail]
            size = len(tail)
    except (OSError, ValueError):  # 프로세스를 끝내 파이프가 닫힌 경우
        return


def run_converter(
    command: list[str],
    work_dir: Path,
    *,
    timeout: float = TIMEOUT_SECONDS,
    max_stdout: int = MAX_TEXT_BYTES,
    max_stderr: int = MAX_ERROR_BYTES,
    watch: Path | None = None,
    max_watch_bytes: int = MAX_TEXT_BYTES,
) -> Finished:
    """변환기를 실행하고 출력을 한도까지만 받아요. 시간을 넘기면 subprocess.TimeoutExpired, 표준 출력·watch 파일이 크면 OutputTooLarge.
    오류 출력은 경고가 많아도 변환을 멈추지 않고 마지막 max_stderr바이트만 남겨요."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=work_dir,
        env=converter_env(work_dir),
    )
    overflow = threading.Event()
    out, err = [], []
    readers = [
        threading.Thread(target=_drain, args=(process.stdout, max_stdout, out, overflow, process), daemon=True),
        threading.Thread(target=_drain, args=(process.stderr, max_stderr, err, None, process), daemon=True),
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if overflow.is_set():
                break
            if watch is not None and watch.exists() and watch.stat().st_size > max_watch_bytes:
                overflow.set()
                break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                process.wait(WATCH_SECONDS)
            except subprocess.TimeoutExpired:
                pass
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for reader in readers:
            reader.join(5)
        for stream in (process.stdout, process.stderr):
            stream.close()
    if overflow.is_set():
        raise OutputTooLarge(command[0])
    return Finished(process.returncode, b"".join(out), b"".join(err))


def _last_error(stderr: bytes) -> str:
    lines = [line for line in (stderr or b"").decode("utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1].strip()[:150] if lines else ""


def _read_html(out: Path) -> str | None:
    if out.exists() and 200 < out.stat().st_size <= MAX_TEXT_BYTES:
        return out.read_text(encoding="utf-8", errors="replace")
    return None


def hwp_to_html(path: Path) -> tuple[str | None, str]:
    """(HTML, 오류 문구). 한 번 바꾼 결과는 같은 폴더에 남겨 다시 쓰지 않아요."""
    out = path.with_suffix(path.suffix + ".html")
    if (cached := _read_html(out)) is not None:
        return cached, ""
    command = tool("hwp5html")
    if not command:
        return None, "hwp5html 없음 (uv add pyhwp six)"
    try:
        done = run_converter([command, "--html", "--output", str(out), str(path)], path.parent, watch=out)
    except subprocess.TimeoutExpired:
        return None, "HWP→HTML 변환 시간 초과"
    except OutputTooLarge:
        out.unlink(missing_ok=True)
        return None, "HWP→HTML 변환 결과가 너무 큼"
    if done.returncode == 0 and (html := _read_html(out)) is not None:
        return html, ""
    return None, _last_error(done.stderr)


def hwp_to_plain_text(path: Path) -> tuple[str | None, str]:
    """HTML 변환이 안 될 때의 예비 수단 (표 구조 없이 글자만)."""
    command = tool("hwp5txt")
    if not command:
        return None, "hwp5txt 없음 (uv add pyhwp six)"
    try:
        done = run_converter([command, str(path)], path.parent)
    except subprocess.TimeoutExpired:
        return None, "HWP 변환 시간 초과"
    except OutputTooLarge:
        return None, "HWP 변환 결과가 너무 큼"
    text = done.stdout.decode("utf-8", errors="replace")
    if done.returncode == 0 and len(text.strip()) >= 200:
        return text, ""
    return None, _last_error(done.stderr)
