import copy
import contextlib
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage_security import runtime_boundary, tls_policy
from update_worker_images import updated_settings
import update_worker_images as workers


class StorageSecurityTests(unittest.TestCase):
    def test_worker_update_preserves_every_other_runtime_setting(self):
        original = 'EXTRACTION_PUBLICATION_MODE=verified\nEXTRACTION_DAILY_BUDGET_USD=7\nOPENAI_API_KEY=example-only\nCOLLECTOR_RELEASE=old\n'
        value = updated_settings(original, 'a' * 40)
        self.assertIn('EXTRACTION_PUBLICATION_MODE=verified\n', value)
        self.assertIn('EXTRACTION_DAILY_BUDGET_USD=7\n', value)
        self.assertIn('OPENAI_API_KEY=example-only\n', value)
        self.assertIn('COLLECTOR_RELEASE=' + 'a' * 40, value)
        self.assertIn('EXTRACTION_RELEASE=' + 'a' * 40, value)
        with self.assertRaises(ValueError): updated_settings(original, 'main; command')

    def test_transport_deny_covers_bucket_and_objects_but_preserves_service_principals(self):
        policy = tls_policy('example-bucket')
        statement = policy['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
        self.assertEqual(statement['Resource'], ['arn:aws:s3:::example-bucket', 'arn:aws:s3:::example-bucket/*'])
        self.assertEqual(statement['Condition']['Bool'], {'aws:SecureTransport': 'false', 'aws:PrincipalIsAWSService': 'false'})

    def test_existing_statements_are_preserved_and_reapplication_is_idempotent(self):
        original = {'Version': '2012-10-17', 'Statement': [{'Sid': 'Existing', 'Effect': 'Deny'}]}
        saved = copy.deepcopy(original)
        policy = tls_policy('example-bucket', original)
        self.assertEqual(original, saved)
        self.assertEqual(policy['Statement'][0], saved['Statement'][0])
        self.assertEqual(tls_policy('example-bucket', policy), policy)

    def test_apps_are_denied_release_and_operations_objects_without_disabling_raw_and_backups(self):
        statement = runtime_boundary('example-bucket')['Statement'][0]
        self.assertEqual(statement['Effect'], 'Deny')
        self.assertEqual(statement['Action'], 's3:*')
        self.assertEqual(statement['Resource'], ['arn:aws:s3:::example-bucket/deployments/*',
                                                 'arn:aws:s3:::example-bucket/operations/*'])

    def test_failed_worker_readiness_restores_previous_settings_and_restarts_old_images(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original = 'EXTRACTION_PUBLICATION_MODE=verified\nCOLLECTOR_RELEASE=old\n'
            (base / '.env').write_text(original)
            archive = base / 'images.tar.gz'
            archive.write_bytes(b'example archive')
            checksum = base / 'images.sha256'
            checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
            old = {name: {'image': f'mujuthaek-personal-{name}:old', 'environment': {'mode': 'verified'}} for name in workers.WORKERS}
            new = {name: {'image': f'mujuthaek-personal-{name}:' + 'a' * 40, 'environment': {'mode': 'verified'}} for name in workers.WORKERS}
            calls = []
            configs = iter([old, new])
            def compose(host, *args):
                if args[0] == 'config': return SimpleNamespace(stdout=json.dumps({'services': next(configs)}))
                calls.append((base / '.env').read_text())
            def private(text):
                path = base / 'pending'
                path.write_text(text)
                return path
            host = SimpleNamespace(download=lambda key, name: checksum if name.endswith('.sha256') else archive,
                                   worker_cpu_budget=contextlib.nullcontext)
            with patch.object(workers, 'BASE', base), patch.object(workers, 'compose', side_effect=compose), \
                 patch.object(workers, 'private_file', side_effect=private), patch.object(workers, 'migration_hash', return_value='b' * 64), \
                 patch.object(workers.subprocess, 'run'), \
                 patch.object(workers, 'wait_worker', side_effect=[RuntimeError('not healthy'), None, None]):
                with self.assertRaises(RuntimeError): workers.update(host, 'a' * 40)
            self.assertEqual((base / '.env').read_text(), original)
            self.assertEqual(calls[-2:], [original, original])


if __name__ == '__main__':
    unittest.main()
