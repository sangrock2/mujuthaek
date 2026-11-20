import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import broker_status


class BrokerStatus(unittest.TestCase):
    def test_unknown_head_age_is_not_reported_as_zero_and_unacked_is_separate(self):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        row = {'name': 'mujuthaek.raw.collected', 'type': 'classic', 'messages_ready': 3,
               'messages_unacknowledged': 1, 'consumers': 1, 'head_message_timestamp': ''}
        value = broker_status.queues([row], now)[row['name']]
        self.assertEqual((value['ready'], value['unacked'], value['head_age_seconds']), (3, 1, None))
        row['head_message_timestamp'] = int(now.timestamp()) - 15
        self.assertEqual(broker_status.queues([row], now)[row['name']]['head_age_seconds'], 15)

    def test_queue_delta_includes_unacked_and_does_not_invent_a_processing_rate(self):
        before = datetime(2026, 11, 20, tzinfo=timezone.utc)
        previous = {'checked_at': before.isoformat(), 'queues': {'job': {'ready': 15, 'unacked': 1}}}
        current = {'checked_at': (before + timedelta(minutes=2)).isoformat(),
                   'queues': {'job': {'ready': 10, 'unacked': 2}}}
        broker_status.compare(current, previous)
        self.assertEqual(current['queues']['job']['outstanding_delta_per_minute'], -2)


if __name__ == '__main__':
    unittest.main()
