"""HWP 변환. pyhwp의 hwp5html로 HTML을 만들면 표 구조(합쳐진 칸 포함)가 살아 있어요."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def tool(name: str) -> str | None:
    """pyhwp 명령 경로. 가상환경을 켜지 않고 .venv/bin/python으로 실행한 경우도 찾아요."""
    sibling = os.path.join(os.path.dirname(sys.executable), name)
    return shutil.which(name) or (sibling if os.path.exists(sibling) else None)


def _last_error(stderr: bytes) -> str:
    lines = [line for line in (stderr or b"").decode("utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1].strip()[:150] if lines else ""


def hwp_to_html(path: Path) -> tuple[str | None, str]:
    """(HTML, 오류 문구). 한 번 바꾼 결과는 같은 폴더에 남겨 다시 쓰지 않아요."""
    out = path.with_suffix(path.suffix + ".html")
    if out.exists() and out.stat().st_size > 200:
        return out.read_text(encoding="utf-8", errors="replace"), ""
    command = tool("hwp5html")
    if not command:
        return None, "hwp5html 없음 (uv add pyhwp six)"
    try:
        done = subprocess.run([command, "--html", "--output", str(out), str(path)], capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return None, "HWP→HTML 변환 시간 초과"
    if done.returncode == 0 and out.exists() and out.stat().st_size > 200:
        return out.read_text(encoding="utf-8", errors="replace"), ""
    return None, _last_error(done.stderr)


def hwp_to_plain_text(path: Path) -> tuple[str | None, str]:
    """HTML 변환이 안 될 때의 예비 수단 (표 구조 없이 글자만)."""
    command = tool("hwp5txt")
    if not command:
        return None, "hwp5txt 없음 (uv add pyhwp six)"
    try:
        done = subprocess.run([command, str(path)], capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return None, "HWP 변환 시간 초과"
    text = done.stdout.decode("utf-8", errors="replace")
    if done.returncode == 0 and len(text.strip()) >= 200:
        return text, ""
    return None, _last_error(done.stderr)
