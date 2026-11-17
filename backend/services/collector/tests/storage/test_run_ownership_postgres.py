"""Real separate DB sessions: exclusion, crash takeover, legacy protection and rollback."""

import os
from uuid import uuid4

import pytest

from mujuthaek_collector.core import run_ownership
from mujuthaek_collector.core.run_ownership import RECOVERY_REASON, SourceAlreadyRunning
from mujuthaek_collector.core.storage import PostgresStore

DB_URL = os.getenv("COLLECTOR_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Disposable native PostgreSQL required")


@pytest.fixture
def stores():
    a, b = PostgresStore(DB_URL), PostgresStore(DB_URL)
    try:
        assert a.conn.info.dbname == "collector_test", "Refusing to mutate a non-test database"
        a.conn.execute("truncate crawl_runs cascade")
        yield a, b
    finally:
        a.close()
        b.close()


def test_live_owner_excludes_another_session_and_preserves_current_run(stores):
    a, b = stores
    run = a.start_run("gh")
    with pytest.raises(SourceAlreadyRunning):
        b.start_run("gh")
    from mujuthaek_collector.admin_api import Runner
    from mujuthaek_collector.core.locks import SourceLocks

    runner = Runner(SourceLocks(), None, None, [], None)
    assert runner.start(b.conn, "gh")[0] == 409
    assert b.conn.execute("select id,status,finished_at from crawl_runs").fetchall() == [(run, "RUNNING", None)]
    other = b.start_run("sh")  # separate sources remain independent
    b.finish_run(other, "SUCCESS", 0, [])
    a.finish_run(run, "SUCCESS", 7, [])
    new = b.start_run("gh")
    assert b.conn.execute("select status,new_count from crawl_runs where id=%s", (run,)).fetchone() == ("SUCCESS", 7)
    b.finish_run(new, "SUCCESS", 0, [])


def test_connection_crash_recovers_managed_run_but_preserves_legacy_and_other_source(stores):
    a, b = stores
    legacy, unrelated = uuid4(), uuid4()
    b.conn.execute("insert into crawl_runs(id,source_code) values(%s,'gh')", (legacy,))
    b.conn.execute("insert into crawl_runs(id,source_code,owner_instance) values(%s,'sh',%s)", (unrelated, uuid4()))
    interrupted = a.start_run("gh")
    b.conn.execute("update crawl_runs set new_count=9 where id=%s", (interrupted,))
    before = b.conn.execute("select id,source_code,started_at,new_count from crawl_runs where id=%s", (interrupted,)).fetchone()
    a.close()  # no finish_run: simulate process/session loss
    current = b.start_run("gh")
    assert before == b.conn.execute("select id,source_code,started_at,new_count from crawl_runs where id=%s", (interrupted,)).fetchone()
    status, finished, error = b.conn.execute("select status,finished_at,error from crawl_runs where id=%s", (interrupted,)).fetchone()
    assert status == "FAILED" and finished and error == RECOVERY_REASON
    assert b.conn.execute("select id,status,finished_at from crawl_runs where id=any(%s) order by id", ([legacy, unrelated],)).fetchall() == [
        (r, "RUNNING", None) for r in sorted([legacy, unrelated])
    ]
    b.finish_run(current, "SUCCESS", 0, [])


def test_excessive_recovery_scope_rolls_back_and_releases_lock(stores, monkeypatch):
    a, b = stores
    monkeypatch.setattr(run_ownership, "MAX_ORPHANS", 1)
    for _ in range(2):
        a.conn.execute("insert into crawl_runs(id,source_code,owner_instance) values(%s,'gh',%s)", (uuid4(), uuid4()))
    with pytest.raises(RuntimeError, match="scope exceeds"):
        a.start_run("gh")
    assert b.conn.execute("select count(*) from crawl_runs where status='RUNNING' and finished_at is null").fetchone() == (2,)
    monkeypatch.setattr(run_ownership, "MAX_ORPHANS", 2)
    current = b.start_run("gh")  # failed recovery must not keep the session lock
    b.finish_run(current, "SUCCESS", 0, [])


def test_failed_insert_restores_orphan_record_and_releases_lock(stores, monkeypatch):
    a, b = stores
    existing = uuid4()
    a.conn.execute("insert into crawl_runs(id,source_code,owner_instance) values(%s,'gh',%s)", (existing, uuid4()))
    monkeypatch.setattr(run_ownership, "uuid7", lambda: existing)  # force PK failure after recovery UPDATE
    import psycopg

    with pytest.raises(psycopg.errors.UniqueViolation):
        a.start_run("gh")
    assert b.conn.execute("select status,finished_at,error from crawl_runs where id=%s", (existing,)).fetchone() == ("RUNNING", None, None)
    monkeypatch.undo()
    current = b.start_run("gh")
    with pytest.raises(RuntimeError, match="not owned"):
        a.finish_run(current, "SUCCESS", 0, [])
    b.finish_run(current, "SUCCESS", 0, [])
