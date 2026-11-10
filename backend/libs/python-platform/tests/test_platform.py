import json
import logging
import uuid
from contextlib import contextmanager

import pytest
from jsonschema import ValidationError

from mujuthaek_platform import outbox
from mujuthaek_platform.contracts import events_dir, validate_event
from mujuthaek_platform.events import new_event
from mujuthaek_platform.ids import uuid7
from mujuthaek_platform.logging import JsonFormatter


def test_uuid7_version_variant_and_order():
    ids = [uuid7() for _ in range(2000)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids, key=lambda i: i.int)  # 같은 밀리초 안에서도 만든 순서대로
    assert len(set(ids)) == len(ids)


def test_new_event_envelope():
    event = new_event("raw.notice.collected", "collector", {"a": 1})
    assert uuid.UUID(event["eventId"]).version == 7
    assert event["schemaVersion"] == 1 and event["producer"] == "collector" and event["payload"] == {"a": 1}
    assert event["occurredAt"].endswith("Z")


class FakeConn:
    """outbox.relay_once가 쓰는 만큼만: transaction(), execute().fetchall()"""

    def __init__(self, rows):
        self.rows = rows
        self.updated = []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        if sql.startswith("update"):
            self.updated.append(params[0])
        return self

    def fetchall(self):
        return self.rows


class FakeChannel:
    def __init__(self, fail_on=None):
        self.declared, self.sent = [], []
        self.confirming = False
        self.fail_on = fail_on  # 이 eventId를 보낼 때 브로커가 거부한 것처럼 예외

    def confirm_delivery(self):
        self.confirming = True

    def exchange_declare(self, *args, **kwargs):
        self.declared.append(kwargs)

    def basic_publish(self, exchange, routing_key, body, properties, mandatory=False):
        if properties.message_id == self.fail_on:
            raise RuntimeError("unroutable")
        self.sent.append((exchange, routing_key, json.loads(body), properties.message_id, mandatory))


class FakeConnection:
    def __init__(self):
        self.opened = FakeChannel()

    def channel(self):
        return self.opened


def test_open_channel_turns_on_confirm_and_declares_exchange():
    channel = outbox.open_channel(FakeConnection())
    assert channel.confirming
    assert channel.declared[0]["exchange"] == "mujuthaek.events" and channel.declared[0]["durable"]


def test_relay_once_publishes_envelope_with_routing_key():
    event = new_event("raw.notice.collected", "collector", {"title": "공고"})
    conn = FakeConn([(event["eventId"], event["eventType"], event)])
    channel = FakeChannel()
    assert outbox.relay_once(conn, channel) == 1
    exchange, key, body, message_id, mandatory = channel.sent[0]
    assert (exchange, key, message_id) == ("mujuthaek.events", "raw.notice.collected", event["eventId"])
    assert mandatory  # 받을 큐가 없으면 조용히 버려지지 않게
    assert body == event and conn.updated == [event["eventId"]]


def test_relay_once_stops_without_marking_when_publish_fails():
    first, second = (new_event("raw.notice.collected", "collector", {"n": n}) for n in (1, 2))
    conn = FakeConn([(e["eventId"], e["eventType"], e) for e in (first, second)])
    with pytest.raises(RuntimeError):
        outbox.relay_once(conn, FakeChannel(fail_on=second["eventId"]))
    assert conn.updated == [first["eventId"]]  # 실패한 이벤트는 표시하지 않아요 (실제 DB에서는 첫 번째도 되돌려져요)


def sample_event(**payload):
    data = {
        "rawPostId": str(uuid7()),
        "version": 1,
        "sourceCode": "dcco",
        "provider": "DCCO",
        "regionCode": None,
        "field": "HOUSING",
        "kind": "NOTICE",
        "title": "2026년 국민임대 입주자 모집공고",
        "postedOn": "2026-10-01",
        "detailUrl": "https://www.dcco.kr/web/board/view.do?mId=43&brdIdx=1",
        "supersedesPostId": None,
        "text": "제목: …",
        "textKey": None,
        "units": [{"houseType": "26A", "areaM2": 26.37, "depositWon": 12_000_000, "rentWon": 150_000}],
        "files": [
            {
                "name": "모집공고문.pdf",
                "fileType": "pdf",
                "role": "NOTICE_DOC",
                "s3Key": "raw/dcco/43-1/v1/00-모집공고문.pdf",
                "downloadUrl": "https://a.kr/f/1",
                "sha256": "ab" * 32,
            }
        ],
        "reprocess": False,
    }
    data.update(payload)
    return new_event("raw.notice.collected", "collector", data)


def test_contract_accepts_valid_event():
    validate_event(sample_event())


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "SOMETHING"},
        {"units": [{"depositWon": "12,000"}]},  # 금액은 원 단위 정수
        {"files": [dict(name="a.pdf", fileType="pdf", role="NOTICE_DOC", s3Key=None, downloadUrl="x", sha256="short")]},
        {"files": [{"name": "a.pdf", "downloadUrl": "x", "sha256": "ab" * 32}]},  # 파일 형식·역할·S3 위치는 필수
        {"regionCode": "123"},  # 시군구 코드는 5자리
        {"extraField": 1},
    ],
)
def test_contract_rejects_invalid_payload(payload):
    with pytest.raises(ValidationError):
        validate_event(sample_event(**payload))


def completed_example():
    return json.loads((events_dir().parent / "examples" / "extraction.completed.json").read_text(encoding="utf-8"))


def test_contract_resolves_references_to_other_schema_files():
    """extraction.completed는 schemas/의 다른 파일을 $id로 가리켜요. 참조를 못 풀면 Unresolvable로 멈췄어요."""
    validate_event(completed_example())


def test_contract_checks_values_inside_referenced_schemas():
    event = completed_example()
    event["payload"]["conditions"][0]["category"] = "NOT_A_CATEGORY"  # eligibility.v1.json의 category 목록에 없음
    with pytest.raises(ValidationError):
        validate_event(event)


def area_ready_example(name="area.source.ready.json"):
    return json.loads((events_dir().parent / "examples" / name).read_text(encoding="utf-8"))


def test_area_source_ready_example_passes():
    validate_event(area_ready_example())
    validate_event(area_ready_example("area.source.ready.address.json"))


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "ALL"},  # 상가는 시도 이름이 있어야 해요
        {"source": "BUS_STOP"},  # 시설은 ALL만
        {"s3Key": "raw/STORES/2026-06-30/stores_gangwon.csv"},  # area/ 경로만
        {"s3Key": "area/STORES/2026-06-30/상가_강원.csv"},  # 영문 파일 이름만
        {"sha256": "AB" * 32},
        {"s3Key": "area/STORES/2026-06-30/stores_gangwon.txt"},  # .txt는 도로명주소만
    ],
)
def test_area_source_ready_rejects_invalid_payload(payload):
    event = area_ready_example()
    event["payload"].update(payload)
    with pytest.raises(ValidationError):
        validate_event(event)


@pytest.mark.parametrize(
    "payload",
    [
        {"scope": "ALL"},  # 도로명주소는 시도 코드가 있어야 해요
        {"scope": "세종"},  # 시도 이름이 아니라 코드
        {"scope": "36110"},  # 두 자리
        {"s3Key": "area/ADDRESS_ENTRANCE/2026-09-30/address_entrance_36110.csv"},  # 원본 그대로 .txt
    ],
)
def test_area_source_ready_rejects_invalid_address_payload(payload):
    event = area_ready_example("area.source.ready.address.json")
    event["payload"].update(payload)
    with pytest.raises(ValidationError):
        validate_event(event)


def test_json_log_includes_extra_fields():
    record = logging.LogRecord("collector", logging.INFO, __file__, 1, "수집 끝", None, None)
    record.source, record.new = "dcco", 3
    line = json.loads(JsonFormatter("collector").format(record))
    assert line["message"] == "수집 끝" and line["service"] == "collector"
    assert line["source"] == "dcco" and line["new"] == 3
