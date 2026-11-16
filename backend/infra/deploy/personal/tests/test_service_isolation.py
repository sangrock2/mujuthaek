"""Exercise offline policy boundaries; these do not attest live IAM or RabbitMQ."""
import copy
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service_isolation as isolation


class ServiceIsolation(unittest.TestCase):
    def setUp(self):
        self.passwords = {name: str(i + 1) * 64 for i, name in enumerate(isolation.SERVICES)}
        self.definitions = isolation.topology(self.passwords)

    def test_generated_topology_passes_but_extra_binding_is_rejected(self):
        self.assertTrue(all(isolation.check_broker(self.definitions, self.passwords).values()))
        changed = copy.deepcopy(self.definitions)
        binding = copy.deepcopy(changed['bindings'][0])
        binding['routing_key'] = '#'
        changed['bindings'].append(binding)
        self.assertFalse(isolation.check_broker(changed, self.passwords)['mq.exact_bindings'])

    def test_no_service_can_publish_to_default_exchange_or_configure_resources(self):
        for service in isolation.SERVICES:
            policy = isolation.resource_permissions(service)
            self.assertIsNone(re.fullmatch(policy['write'], 'amq.default'))
            self.assertIsNone(re.fullmatch(policy['configure'], isolation.EVENTS))
        collector = isolation.topic_permissions('collector')[0]
        self.assertIsNone(re.fullmatch(collector['write'], 'notification.requested'))
        self.assertIsNotNone(re.fullmatch(collector['write'], 'raw.notice.collected'))

    def test_legacy_shared_permissions_and_wrong_password_fail(self):
        changed = copy.deepcopy(self.definitions)
        changed['permissions'].append({'user': 'mujuthaek', 'vhost': '/'})
        self.assertFalse(isolation.check_broker(changed, self.passwords)['mq.legacy_user_revoked'])
        wrong = dict(self.passwords, api='f' * 64)
        self.assertFalse(isolation.check_broker(self.definitions, wrong)['mq.api.credentials'])

    def test_readers_cannot_write_or_read_backups(self):
        for service in ('api', 'extraction'):
            policy = isolation.storage_policy(service, 'synthetic-bucket')
            text = str(policy)
            self.assertNotIn('PutObject', text)
            self.assertNotIn('DeleteObject', text)
            self.assertNotIn('/backups', text)
        self.assertNotIn('/area', str(isolation.storage_policy('extraction', 'synthetic-bucket')))

    def test_unused_legacy_admin_and_unknown_users_also_fail(self):
        changed = copy.deepcopy(self.definitions)
        changed['users'].append({'name': 'mujuthaek', 'tags': ['administrator']})
        checks = isolation.check_broker(changed, self.passwords)
        self.assertFalse(checks['mq.legacy_user_revoked'])
        self.assertFalse(checks['mq.exact_users'])

    def test_duplicate_env_settings_fail_closed(self):
        with self.assertRaises(ValueError):
            isolation.env_values('API_MQ_PASSWORD=a\nAPI_MQ_PASSWORD=b\n')


if __name__ == '__main__':
    unittest.main()
