from unittest.mock import Mock

import pytest

from mujuthaek_extraction import worker


def test_managed_worker_never_declares_or_binds_other_services_queues(monkeypatch):
    monkeypatch.setenv("MUJUTHAEK_MANAGED_TOPOLOGY", "true")
    channel = Mock()
    worker.declare(channel)
    channel.queue_bind.assert_not_called()
    assert all(call.kwargs.get("passive") is True for call in channel.exchange_declare.call_args_list)
    assert all(call.kwargs.get("passive") is True for call in channel.queue_declare.call_args_list)
    assert {call.kwargs["queue"] for call in channel.queue_declare.call_args_list} == {worker.QUEUE, worker.DLQ, worker.POLICY_QUEUE, worker.POLICY_DLQ}


def test_managed_retry_cannot_bypass_topic_permissions_using_default_exchange(monkeypatch):
    monkeypatch.setenv("MUJUTHAEK_MANAGED_TOPOLOGY", "true")
    channel = Mock()
    worker.publish_to_owned_queue(channel, worker.POLICY_DLQ, b"payload", None)
    channel.basic_publish.assert_called_once_with(exchange=worker.RETRY_EXCHANGE, routing_key=worker.POLICY_DLQ, body=b"payload", properties=None)
    with pytest.raises(ValueError):
        worker.publish_to_owned_queue(channel, "mujuthaek.notification", b"payload", None)
    assert channel.basic_publish.call_count == 1
