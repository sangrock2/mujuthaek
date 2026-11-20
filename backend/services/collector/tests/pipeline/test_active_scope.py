from dataclasses import replace
from datetime import date, timedelta

from mujuthaek_collector.core.storage import SCOPE_UNVERIFIED
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


def test_only_verified_application_period_is_published(client, store, file_store, settings, monkeypatch):
    rows = [
        ("unknown", "행복주택 입주자 모집공고", date(2020, 1, 1)),
        ("expired", "매입임대 입주자 모집공고", date(2026, 10, 1)),
        ("future", "국민임대 입주자 모집공고", date(2026, 10, 2)),
    ]
    pages(client, rows)
    client.pages["https://a.kr/view?id=unknown"] = "당첨자 발표일: 2026. 11. 1."
    client.pages["https://a.kr/view?id=expired"] = "접수기간: 2026. 10. 3. ~ 10. 12."
    client.pages["https://a.kr/view?id=future"] = "신청기간: 2026년 10월 19일 ~ 2026년 10월 21일"

    result = run(FakeSource(rows), client, store, file_store, replace(settings, active_only=True), monkeypatch)

    assert result.new_count == 1
    assert [event["payload"]["title"] for event in store.events] == [rows[2][1]]
    assert store.by_key("future").deadline_on == date(2026, 10, 21)
    assert store.by_key("unknown").last_error == store.by_key("expired").last_error == SCOPE_UNVERIFIED
    assert not any(key.startswith(("raw/dcco/unknown/", "raw/dcco/expired/")) for key in file_store.objects)


def test_notice_held_for_unknown_schedule_can_reopen_when_list_is_updated(client, store, file_store, settings, monkeypatch):
    rows = [("held", "행복주택 입주자 모집공고", date(2026, 10, 1))]

    class UpdatedSource(FakeSource):
        deadline = None

        def parse_list(self, board, body, page_url):
            return [replace(item, deadline_on=self.deadline) for item in super().parse_list(board, body, page_url)]

    source = UpdatedSource(rows)
    pages(client, rows)
    active_settings = replace(settings, active_only=True)
    assert run(source, client, store, file_store, active_settings, monkeypatch).new_count == 0
    source.deadline = date(2026, 10, 21)
    assert run(source, client, store, file_store, active_settings, monkeypatch).new_count == 1
    assert len(store.events) == 1


def test_follow_up_uses_verified_parent_schedule(client, store, file_store, settings, monkeypatch):
    rows = [
        ("follow", "2026년 행복주택 입주자 모집공고(2026. 10. 1.) 서류심사 대상자 발표", date(2026, 10, 10)),
        ("parent", "2026년 행복주택 입주자 모집공고", date(2026, 10, 1)),
    ]
    pages(client, rows)
    client.pages["https://a.kr/view?id=parent"] = "접수기간: 2026.10.10. ~ 2026.10.31."
    result = run(FakeSource(rows), client, store, file_store, replace(settings, active_only=True), monkeypatch)

    assert result.new_count == 2
    assert [event["payload"]["kind"] for event in store.events] == ["NOTICE", "FOLLOW_UP"]
