import subprocess
import sys
from pathlib import Path

from mujuthaek_extraction.intake import pdf_process

REAL_POPEN = subprocess.Popen


def replace_child(monkeypatch, script):
    children = []
    folders = []

    def spawn(command, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert "DATABASE_URL" not in kwargs["env"]
        folders.append(Path(kwargs["cwd"]))
        child = REAL_POPEN([sys.executable, "-I", "-c", script], **kwargs)
        children.append(child)
        return child

    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("DATABASE_URL", "test-not-a-real-database")
    monkeypatch.setattr(pdf_process.subprocess, "Popen", spawn)
    return children, folders


def test_runaway_child_is_killed_reaped_and_next_job_can_run(monkeypatch):
    children, folders = replace_child(monkeypatch, "import time; time.sleep(30)")
    monkeypatch.setattr(pdf_process, "TIMEOUT_SECONDS", 0.2)
    assert pdf_process.run_pdf(b"%PDF", "document", 1) is None
    assert children[0].poll() is not None
    assert not folders[0].exists()
    replace_child(monkeypatch, "print('{\"ok\":true}')")
    assert pdf_process.run_pdf(b"%PDF", "document", 1) == {"ok": True}


def test_oversized_output_is_killed_and_removed(monkeypatch):
    children, folders = replace_child(monkeypatch, "import sys,time; sys.stdout.write('x'*65536); sys.stdout.flush(); time.sleep(30)")
    monkeypatch.setattr(pdf_process, "MAX_OUTPUT_BYTES", 1024)
    assert pdf_process.run_pdf(b"%PDF", "document", 1) is None
    assert children[0].poll() is not None
    assert not folders[0].exists()


def test_invalid_child_output_fails_closed(monkeypatch):
    replace_child(monkeypatch, "print('not JSON')")
    assert pdf_process.run_pdf(b"%PDF", "document", 1) is None


def test_large_input_is_rejected_before_starting_child(monkeypatch):
    children, _ = replace_child(monkeypatch, "raise AssertionError('must not run')")
    monkeypatch.setattr(pdf_process, "MAX_INPUT_BYTES", 3)
    assert pdf_process.run_pdf(b"1234", "document", 1) is None
    assert children == []
