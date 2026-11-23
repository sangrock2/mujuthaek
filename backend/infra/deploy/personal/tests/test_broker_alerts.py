import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import broker_alerts

QUEUE = 'mujuthaek.raw.collected'


def snapshot(depth, consumers=1, age=None, dead=0):
    return {'queues': {
        QUEUE: {'ready': depth, 'consumers': consumers, 'head_age_seconds': age, 'unacked': 1},
        QUEUE + '.dlq': {'ready': dead},
        QUEUE + '.notice.hold': {'ready': 1000},
    }, 'outboxes': {}}


class BrokerAlerts(unittest.TestCase):
    def test_aged_queue_alerts_once_per_incident_and_ignores_manual_hold(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(broker_alerts.slack_alerts, 'send') as send, \
             patch.object(broker_alerts.broker_status, 'collect', side_effect=[
                 snapshot(3, age=930), snapshot(3, age=1230), snapshot(2, age=1500),
                 snapshot(0), snapshot(1, consumers=0), snapshot(1, consumers=0),
             ]):
            state = Path(tmp) / 'state.json'
            broker_alerts.run(state, 'synthetic')
            send.assert_not_called()
            broker_alerts.run(state, 'synthetic')
            broker_alerts.run(state, 'synthetic')
            self.assertEqual(send.call_count, 1)
            broker_alerts.run(state, 'synthetic')
            self.assertEqual(json.loads(state.read_text())['active'], [])
            broker_alerts.run(state, 'synthetic')
            broker_alerts.run(state, 'synthetic')
            self.assertEqual(send.call_count, 2)

    def test_dead_letter_delivery_failure_leaves_state_available_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(broker_alerts.broker_status, 'collect', return_value=snapshot(0, dead=2)), \
             patch.object(broker_alerts.slack_alerts, 'send', side_effect=broker_alerts.slack_alerts.SlackError):
            state = Path(tmp) / 'state.json'
            with self.assertRaises(broker_alerts.slack_alerts.SlackError):
                broker_alerts.run(state, 'synthetic')
            self.assertFalse(state.exists())
