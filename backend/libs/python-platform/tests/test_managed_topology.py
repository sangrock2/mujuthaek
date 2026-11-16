from unittest.mock import Mock

import pytest

from mujuthaek_platform import broker, outbox


def test_managed_publisher_only_checks_existing_exchange(monkeypatch):
    monkeypatch.setenv("MUJUTHAEK_MANAGED_TOPOLOGY", "true")
    connection = Mock()
    outbox.open_channel(connection)
    connection.channel.return_value.exchange_declare.assert_called_once_with(exchange=outbox.EXCHANGE, passive=True)
    connection.channel.return_value.confirm_delivery.assert_called_once_with()


def test_invalid_topology_mode_fails_instead_of_acquiring_declaration_rights(monkeypatch):
    monkeypatch.setenv("MUJUTHAEK_MANAGED_TOPOLOGY", "typo")
    with pytest.raises(ValueError):
        broker.managed_topology()
