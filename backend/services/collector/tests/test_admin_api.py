"""관리자 수집 현황 API (admin_api.py). HTTP 처리는 가짜 연결로, 상태 계산은 로컬 DB가 있을 때만 실제 테이블로 확인해요.

COLLECTOR_TEST_DB_URL=postgresql://collector_app:collector-pass@localhost:5432/collector_test uv run pytest tests/test_admin_api.py
"""

import json
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from mujuthaek_collector import admin_api
from mujuthaek_collector.core.locks import SourceLocks


class FakeConn:
    closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def server(monkeypatch):
    conns = []
    monkeypatch.setattr(admin_api, "sources_status", lambda conn: {"sources": [], "summary": {}})
    monkeypatch.setattr(admin_api, "set_enabled", lambda conn, code, enabled: code == "sh")

    def connect():
        conns.append(FakeConn())
        return conns[-1]

    def start(token=None):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), admin_api.handler_for(connect, token))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"

    started = []

    def make(token=None):
        httpd, url = start(token)
        started.append(httpd)
        return url, conns

    yield make
    for httpd in started:
        httpd.shutdown()


def call(url, method="GET", token=None):
    request = Request(url, method=method, data=b"" if method == "POST" else None)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_status_and_pause_resume(server):
    url, conns = server()
    assert call(url + "/sources") == (200, {"sources": [], "summary": {}})
    assert call(url + "/sources/sh/pause", "POST") == (200, {"code": "sh", "enabled": False})
    assert call(url + "/sources/sh/resume", "POST") == (200, {"code": "sh", "enabled": True})
    assert call(url + "/sources/nope/pause", "POST")[0] == 404
    assert call(url + "/other")[0] == 404
    assert all(c.closed for c in conns)  # 요청마다 연 연결은 닫아요


def test_token_is_required_when_configured(server):
    url, _ = server(token="t0ken")
    assert call(url + "/sources")[0] == 401
    assert call(url + "/sources", token="wrong")[0] == 401
    assert call(url + "/sources", token="t0ken")[0] == 200


DB_URL = os.getenv("COLLECTOR_TEST_DB_URL")


@pytest.mark.skipif(not DB_URL, reason="COLLECTOR_TEST_DB_URL이 없어요 (로컬 DB 테스트)")
def test_status_counts_runs_from_the_tables():
    from mujuthaek_collector.core.storage import PostgresStore

    store = PostgresStore(DB_URL)
    conn = store.conn
    a, b = "tadm_" + uuid.uuid4().hex[:6], "tadm_" + uuid.uuid4().hex[:6]  # 이 시험만의 출처(다른 시험 자료는 건드리지 않음)
    try:
        for code in (a, b):
            conn.execute("insert into sources (code, name) values (%s, %s)", (code, "시험 출처 " + code))
        now = datetime(2026, 10, 25, 5, 0, tzinfo=UTC)

        def run(code, hours_ago, status, new_count, error=None):
            started = now - timedelta(hours=hours_ago)
            conn.execute(
                "insert into crawl_runs (id, source_code, started_at, finished_at, status, new_count, error) values (%s, %s, %s, %s, %s, %s, %s)",
                (uuid.uuid4(), code, started, started + timedelta(minutes=1), status, new_count, error),
            )

        run(a, 30, "SUCCESS", 3)
        run(a, 2, "SUCCESS", 0)
        run(a, 1, "SUCCESS", 0)
        run(b, 3, "SUCCESS", 4)
        run(b, 1, "FAILED", 0, "목록 표를 못 찾음")
        status = admin_api.sources_status(conn, now)
        by_code = {s["code"]: s for s in status["sources"]}
        assert by_code[a]["state"] == "ok" and by_code[a]["consecutiveEmpty"] == 2
        assert by_code[b]["state"] == "fail" and by_code[b]["consecutiveFailures"] == 1
        assert by_code[b]["lastRun"]["error"] == "목록 표를 못 찾음"
        assert len(by_code[a]["recentRuns"]) == 3

        assert admin_api.set_enabled(conn, b, False)
        assert {s["code"]: s["state"] for s in admin_api.sources_status(conn, now)["sources"]}[b] == "paused"
        assert not admin_api.set_enabled(conn, "nope_" + a, False)
    finally:
        conn.execute("delete from crawl_runs where source_code in (%s, %s)", (a, b))
        conn.execute("delete from sources where code in (%s, %s)", (a, b))
        store.close()


class Rows:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class RunConn:
    """sources·crawl_runs 조회만 흉내 내요."""

    def __init__(self, enabled=True, running=False):
        self.enabled, self.running = enabled, running

    def execute(self, sql, params):
        if "from sources" in sql:
            return Rows(None if params[0] == "nope" else (self.enabled,))
        return Rows((1,) if self.running else None)


def make_runner(calls):
    done = threading.Event()

    def collect(code, settings):
        calls.append(("board", code))
        done.set()

    def collect_policy(code, settings):
        calls.append(("policy", code))
        done.set()

    return admin_api.Runner(SourceLocks(), collect, collect_policy, ["gov24"], settings=None), done


def test_run_now_uses_the_source_lock_and_the_right_collector():
    calls = []
    runner, done = make_runner(calls)
    assert runner.start(RunConn(), "sh") == (202, {"code": "sh", "started": True})
    assert done.wait(5)
    for _ in range(50):  # 끝나면 그 출처 잠금을 돌려줘요
        if not runner.locks.busy("sh"):
            break
        threading.Event().wait(0.02)
    assert not runner.locks.busy("sh")
    done.clear()
    assert runner.start(RunConn(), "gov24")[0] == 202 and done.wait(5)
    assert calls == [("board", "sh"), ("policy", "gov24")]


def test_run_now_is_refused_when_busy_paused_running_or_unknown():
    runner, _ = make_runner([])
    assert runner.start(RunConn(), "nope")[0] == 404
    assert runner.start(RunConn(enabled=False), "sh")[0] == 409
    assert runner.start(RunConn(running=True), "sh")[0] == 409
    runner.locks.acquire("sh")  # 스케줄러가 이 출처를 수집하는 중
    try:
        status, body = runner.start(RunConn(), "sh")
        assert status == 409 and "수집 중" in body["error"]
        # 다른 출처가 도는 건 막지 않아요
        assert runner.start(RunConn(), "gov24")[0] == 202
    finally:
        runner.locks.release("sh")


def test_run_route_without_runner_says_not_available(server):
    url, _ = server()
    assert call(url + "/sources/sh/run", "POST")[0] == 501
