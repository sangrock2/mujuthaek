from datetime import date

import pytest
from jsonschema import ValidationError

from mujuthaek_collector.area.events import event_id, ready_event, record
from mujuthaek_platform.contracts import validate_event

SHA = "6505ddc859141a3c7526f2c3e0aec101afc4d7fdc52bb38a2bd7f54b67f917dd"


def stores_event():
    return ready_event("STORES", "강원", "area/STORES/2026-06-30/stores_gangwon.csv", SHA, date(2026, 6, 30), "원본.csv", 110206)


def test_event_follows_the_contract():
    validate_event(stores_event())
    validate_event(ready_event("BUS_STOP", "ALL", "area/BUS_STOP/2025-10-31/bus_stop.csv", SHA, date(2025, 10, 31)))


def test_boundary_event_follows_the_contract_and_its_file_name_is_fixed():
    sha = "8033c0936030653bbcc77077370034e84dc0c7e87c642d6e5fe2bc4ae38ae34c"
    event = ready_event("REGION_BOUNDARY_SIG", "ALL", "area/REGION_BOUNDARY_SIG/2026-09-30/boundary_sig.csv", sha, date(2026, 9, 30), "boundary_sig.csv", 256)
    validate_event(event)
    # contracts/examples/area.source.ready.boundary.json의 eventId와 같아야 해요
    assert event["eventId"] == "f66e2851-938c-5910-a73a-b12cfade1956"
    event["payload"]["s3Key"] = "area/REGION_BOUNDARY_SIG/2026-09-30/boundary_emd.csv"
    with pytest.raises(ValidationError):
        validate_event(event)


def test_event_id_is_fixed_by_source_scope_and_fingerprint():
    # contracts/examples/area.source.ready.json의 eventId와 같아야 해요 (같은 규칙)
    assert stores_event()["eventId"] == "1591c7fa-581b-5e5a-9ffe-2d28b6300247"
    assert stores_event()["eventId"] == stores_event()["eventId"]
    assert event_id("STORES", "경기", SHA) != event_id("STORES", "강원", SHA)


def test_contract_catches_a_wrong_scope():
    event = stores_event()
    event["payload"]["scope"] = "ALL"
    with pytest.raises(ValidationError):
        validate_event(event)


class FakeConn:
    def __init__(self):
        self.ids = set()

    def execute(self, sql, params):
        assert "on conflict (event_id) do nothing" in sql
        new = params[0] not in self.ids
        self.ids.add(params[0])
        return type("Cursor", (), {"rowcount": 1 if new else 0})()


def test_record_writes_each_event_once():
    conn = FakeConn()
    assert record(conn, stores_event()) is True
    assert record(conn, stores_event()) is False


class UpsertConn:
    """같은 eventId면 다시 보내도록 되돌리는지 (published_at = null)만 봐요"""

    def __init__(self):
        self.sql = []

    def execute(self, sql, params):
        self.sql.append(sql)
        return type("Cursor", (), {"rowcount": 1})()


def test_resend_puts_an_already_recorded_event_back_to_unpublished():
    # 실측 2026-10-29: RabbitMQ 컨테이너가 다시 만들어지며 큐가 비어 적재 요청이 사라짐 → 이미 기록한 이벤트를 다시 보내요
    conn = UpsertConn()
    assert record(conn, stores_event(), resend=True) is True
    assert "on conflict (event_id) do update set payload = excluded.payload, published_at = null" in conn.sql[0]
