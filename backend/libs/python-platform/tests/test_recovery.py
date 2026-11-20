from types import SimpleNamespace
from unittest.mock import Mock

import pika
import pytest

from mujuthaek_platform import recovery


def source(deliveries=1, count=0):
    channel = Mock()
    channel.queue_declare.return_value.method.message_count = deliveries
    props = pika.BasicProperties(headers={recovery.REPLAY_HEADER: count}, message_id="stable-id")
    channel.basic_get.return_value = SimpleNamespace(delivery_tag=3), props, b"event"
    return channel, props


def replay(channel):
    return recovery.replay(channel, exchange="retry", dlq="failed", queue="original", limit=10)


def test_confirmed_replay_retains_id_and_acks_only_after_publish():
    channel, original = source()
    assert replay(channel) == recovery.ReplayResult(replayed=1)
    assert [call[0] for call in channel.method_calls] == [
        "confirm_delivery",
        "queue_declare",
        "basic_get",
        "basic_publish",
        "basic_ack",
    ]
    publish = channel.basic_publish.call_args.kwargs
    assert publish["exchange"] == "retry" and publish["routing_key"] == "original" and publish["mandatory"]
    props = publish["properties"]
    assert props.message_id == original.message_id and props.delivery_mode == 2
    assert props.headers[recovery.REPLAY_HEADER] == 1 and original.headers[recovery.REPLAY_HEADER] == 0


@pytest.mark.parametrize("failure", [pika.exceptions.UnroutableError([]), pika.exceptions.NackError([])])
def test_return_or_nack_leaves_original_in_dlq(failure):
    channel, _ = source()
    channel.basic_publish.side_effect = failure
    with pytest.raises(type(failure)):
        replay(channel)
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(3, requeue=True)


def test_connection_loss_leaves_original_unacked():
    channel, _ = source()
    channel.basic_publish.side_effect = pika.exceptions.StreamLostError()
    with pytest.raises(pika.exceptions.StreamLostError):
        replay(channel)
    channel.basic_ack.assert_not_called()


def test_exhausted_replay_is_rotated_in_dlq_once_per_snapshot():
    channel, _ = source(count=3)
    assert replay(channel) == recovery.ReplayResult(parked=1)
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "failed"
    assert channel.basic_get.call_count == 1
