"""PostgresStore를 실제 collector 데이터베이스 테이블로 확인해요.

로컬 DB가 떠 있을 때만 돌아요 (없으면 건너뜀):
  COLLECTOR_TEST_DB_URL=postgresql://collector_app:collector-pass@localhost:5432/collector_test uv run pytest tests/test_storage_postgres.py
테스트용 데이터베이스(collector_test)는 저장소 루트에서 make migrate-collector-test로 만들고 테이블을 적용해요. 테스트가 테이블을 비워요.
"""

import os
from datetime import date

import pytest

from mujuthaek_collector import pipeline
from mujuthaek_collector.core.storage import PostgresStore
from tests.test_pipeline import ROWS, TODAY, FakeSource, pages

DB_URL = os.getenv("COLLECTOR_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="COLLECTOR_TEST_DB_URL이 없어요 (로컬 DB 테스트)")


@pytest.fixture
def pg():
    store = PostgresStore(DB_URL)
    # cascade: 정책 수집 표(raw_policy_versions 등)가 crawl_runs를 가리켜 나열한 표만 비우면 실패했어요
    store.conn.execute("truncate outbox, raw_units, raw_texts, raw_files, raw_post_versions, raw_posts, crawl_runs, source_boards cascade")
    # 처음 수집 개수 제한(2026-10-27)은 고른 것으로 둬요: 고르기 전이면 새 글이 HELD라 이 시험들의 흐름(PENDING → DONE)이 돌지 않았어요
    store.conn.execute(
        "insert into intake_decisions (group_code, limit_count, kept, ignored) values ('HOUSING_LH', 0, 0, 0), ('HOUSING_OTHER', 0, 0, 0)"
        " on conflict (group_code) do update set cutoff_on = null"
    )
    yield store
    store.close()


def run(source, client, store, file_store, settings, monkeypatch, **kwargs):
    monkeypatch.setattr(pipeline, "extract_text", lambda data, ext: ("공고문 글자 " * 30, "PDF 텍스트·표"))
    return pipeline.run_source(source, client, store, file_store, settings, today=TODAY, **kwargs)


def test_full_run_writes_all_tables(pg, client, file_store, settings, monkeypatch):
    pages(client, ROWS)
    result = run(FakeSource(ROWS), client, pg, file_store, settings, monkeypatch)
    assert result.status == "SUCCESS" and result.new_count == 2

    statuses = dict(pg.conn.execute("select post_key, status from raw_posts").fetchall())
    assert statuses == {"1": "DONE", "2": "DONE", "3": "SKIPPED", "4": "SKIPPED"}
    parent = pg.conn.execute("select p.post_key from raw_posts c join raw_posts p on p.id = c.parent_post_id where c.post_key = '2'").fetchone()
    assert parent == ("1",)
    assert pg.conn.execute("select count(*) from raw_files where s3_key like 'raw/dcco/%'").fetchone() == (2,)
    assert pg.conn.execute("select count(*) from raw_texts").fetchone() == (2,)
    assert pg.conn.execute("select count(*) from raw_units").fetchone() == (0,)  # 호별 표는 extraction이 읽어요
    assert pg.conn.execute("select count(*) from outbox where published_at is null").fetchone() == (2,)
    assert pg.conn.execute("select status, new_count from crawl_runs").fetchone() == ("SUCCESS", 2)


def test_recheck_and_relay(pg, client, file_store, settings, monkeypatch):
    rows = ROWS[:1]
    pages(client, rows)
    run(FakeSource(rows), client, pg, file_store, settings, monkeypatch)
    client.pages["https://a.kr/view?id=1"] = "정정된 본문"
    assert run(FakeSource(rows), client, pg, file_store, settings, monkeypatch, recheck=True).new_count == 1
    assert pg.conn.execute("select latest_version from raw_posts where post_key = '1'").fetchone() == (2,)

    from mujuthaek_platform import outbox

    class Channel:  # RabbitMQ 대신 보낸 메시지를 모아요
        def __init__(self):
            self.sent = []

        def basic_publish(self, exchange, routing_key, body, properties, mandatory=False):
            self.sent.append((exchange, routing_key))

    channel = Channel()
    assert outbox.relay_once(pg.conn, channel) == 2
    assert channel.sent == [("mujuthaek.events", "raw.notice.collected")] * 2
    assert pg.conn.execute("select count(*) from outbox where published_at is null").fetchone() == (0,)


def test_failed_post_and_expired_files(pg, client, file_store, settings, monkeypatch):
    rows = ROWS[:1] + [("5", "2026년 국민임대 입주자 모집공고", date(2026, 10, 5))]
    pages(client, rows)
    client.pages["https://a.kr/view?id=5"] = "BROKEN"
    run(FakeSource(rows), client, pg, file_store, settings, monkeypatch)
    assert pg.conn.execute("select status, attempts from raw_posts where post_key = '5'").fetchone() == ("FAILED", 1)
    assert len(pg.queued_posts("dcco", "43", 10)) == 1  # FAILED는 3번까지 다시 시도 대상

    expired = pg.expired_files(date(2030, 1, 1))
    assert len(expired) == 1
    pg.mark_file_deleted(expired[0][0])
    assert pg.expired_files(date(2030, 1, 1)) == []


def test_flaky_attachment_carries_the_earlier_file_and_spent_posts_are_requeued(pg, client, file_store, settings, monkeypatch):
    """2026-11-10 재검토: 첨부를 끝내 못 받으면 이전 버전 것을 이어 쓰고(원본·글자·보관 기한 그대로), 성공하면 실패 횟수를 되돌리고,
    새벽 정정 확인은 횟수를 다 쓴 FAILED 글도 다시 열어요."""
    import httpx

    from mujuthaek_collector.core.storage import MAX_ATTEMPTS

    rows = ROWS[:1]
    pages(client, rows)
    run(FakeSource(rows), client, pg, file_store, settings, monkeypatch)
    client.files["https://a.kr/f/1.pdf"] = httpx.ConnectError("연결 끊김")
    client.pages["https://a.kr/view?id=1"] = "정정된 본문"
    run(FakeSource(rows), client, pg, file_store, settings, monkeypatch, recheck=True)
    run(FakeSource(rows), client, pg, file_store, settings, monkeypatch)
    assert pg.conn.execute("select status, attempts from raw_posts where post_key = '1'").fetchone() == ("FAILED", 2)
    assert run(FakeSource(rows), client, pg, file_store, settings, monkeypatch).new_count == 1
    files = pg.conn.execute(
        "select v.version, f.s3_key, f.stored_until, t.text is not null from raw_files f join raw_post_versions v on v.id = f.version_id "
        "left join raw_texts t on t.file_id = f.id order by v.version"
    ).fetchall()
    assert len(files) == 2 and files[0][1:] == files[1][1:] and files[1][3]
    assert pg.conn.execute("select status, attempts from raw_posts where post_key = '1'").fetchone() == ("DONE", 0)

    post_id = pg.find_post("dcco", "1").id
    pg.conn.execute("update raw_posts set attempts = 2 where id = %s", (post_id,))
    pg.mark_done(post_id)
    assert pg.conn.execute("select attempts from raw_posts where id = %s", (post_id,)).fetchone() == (0,)
    pg.conn.execute("update raw_posts set status = 'FAILED', attempts = %s where id = %s", (MAX_ATTEMPTS, post_id))
    assert pg.requeue_open_posts("dcco", TODAY, 60) == 1
    assert pg.conn.execute("select status from raw_posts where id = %s", (post_id,)).fetchone() == ("PENDING",)
