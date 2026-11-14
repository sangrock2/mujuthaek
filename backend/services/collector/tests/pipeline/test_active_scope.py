from dataclasses import replace
from datetime import date, timedelta

from mujuthaek_collector.pipeline import active_notice
from mujuthaek_collector.sources.base import ListItem
from tests.pipeline.test_pipeline import FakeSource, pages, run


def test_open_ended_future_and_deadline_day_are_not_excluded():
    today = date(2026, 11, 14)
    item = ListItem("rent", "1", "상시모집", date(2020, 1, 1), None)
    assert active_notice(item, today)
    assert active_notice(replace(item, list_status="접수예정", deadline_on=today + timedelta(days=30)), today)
    assert active_notice(replace(item, list_status="마감임박", deadline_on=today), today)
    assert not active_notice(replace(item, deadline_on=today - timedelta(days=1)), today)
    assert not active_notice(replace(item, list_status="접수 마감"), today)


def test_old_open_notice_is_collected_in_active_only_mode(client, store, file_store, settings, monkeypatch):
    rows = [("old-open", "상시 행복주택 입주자 모집공고", date(2020, 1, 1))]
    pages(client, rows)
    result = run(FakeSource(rows), client, store, file_store, replace(settings, active_only=True), monkeypatch)
    assert result.new_count == 1
    assert store.by_key("old-open").status == "DONE"
    assert store.events[0]["payload"]["title"] == rows[0][1]
    assert all(file.stored_until > date(2026, 10, 14) for file in store.versions[0].files)
