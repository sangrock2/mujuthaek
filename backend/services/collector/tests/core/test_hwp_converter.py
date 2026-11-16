"""HWP 변환기 실행: 넘기는 환경변수와 출력 크기 한도 (2026-11-16 보안 감사 4장)."""

import json
import subprocess
import sys

import pytest

from mujuthaek_collector.core.documents import hwp


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_converter_gets_only_allowed_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("COLLECTOR_TEST_PRIVATE_VALUE", "placeholder")
    monkeypatch.setenv("LANG", "C.UTF-8")
    done = hwp.run_converter(python("import json, os; print(json.dumps(dict(os.environ)))"), tmp_path)
    env = json.loads(done.stdout)
    assert done.returncode == 0
    assert "COLLECTOR_TEST_PRIVATE_VALUE" not in env
    assert env["LANG"] == "C.UTF-8" and env["HOME"] == env["TMPDIR"] == str(tmp_path)
    assert set(env) <= set(hwp.PASSED_ENV) | {"HOME", "TMPDIR", "TEMP", "TMP"} | {"__PYVENV_LAUNCHER__", "PYTHONHOME"}


def test_large_standard_output_stops_converter(tmp_path):
    with pytest.raises(hwp.OutputTooLarge):
        hwp.run_converter(python("import sys; sys.stdout.write('x' * 3_000_000)"), tmp_path, max_stdout=1_000_000)


def test_error_output_keeps_only_the_tail(tmp_path):
    code = "import sys; sys.stderr.write('warning\\n' * 50_000 + 'last problem\\n')"
    done = hwp.run_converter(python(code), tmp_path, max_stderr=4096)
    assert done.returncode == 0 and len(done.stderr) <= 4096
    assert hwp._last_error(done.stderr) == "last problem"


def test_large_output_file_stops_converter(tmp_path):
    out = tmp_path / "source.hwp.html"
    code = f"import time\nwith open({str(out)!r}, 'wb') as f:\n    f.write(b'x' * 2_000_000)\n    f.flush()\n    time.sleep(10)"
    with pytest.raises(hwp.OutputTooLarge):
        hwp.run_converter(python(code), tmp_path, watch=out, max_watch_bytes=1_000_000, timeout=8)


def test_slow_converter_times_out(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        hwp.run_converter(python("import time; time.sleep(10)"), tmp_path, timeout=0.5)


def test_plain_text_fallback_reports_large_output(tmp_path, monkeypatch):
    source = tmp_path / "source.hwp"
    source.write_bytes(b"not really hwp")
    monkeypatch.setattr(hwp, "tool", lambda name: sys.executable)
    monkeypatch.setattr(hwp, "MAX_TEXT_BYTES", 10)

    def fake_run(command, work_dir, **kwargs):
        raise hwp.OutputTooLarge(command[0])

    monkeypatch.setattr(hwp, "run_converter", fake_run)
    assert hwp.hwp_to_plain_text(source) == (None, "HWP 변환 결과가 너무 큼")
    assert hwp.hwp_to_html(source) == (None, "HWP→HTML 변환 결과가 너무 큼")
