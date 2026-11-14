import importlib.util
import unittest
import tempfile
import subprocess
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('configure_collection', Path(__file__).resolve().parents[1] / 'configure_collection.py')
collection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collection)

VALUES = {name: ('sk-example-personal-only' if name == 'OPENAI_API_KEY' else 'example-key%2Bvalue==') for name in collection.KEYS}

publication_spec = importlib.util.spec_from_file_location('set_collection_publication', Path(__file__).resolve().parents[1] / 'set_collection_publication.py')
publication = importlib.util.module_from_spec(publication_spec)
with patch.dict(sys.modules, {'configure_collection': collection}):
    publication_spec.loader.exec_module(publication)


class CollectionConfiguration(unittest.TestCase):
    def test_automatic_publication_requires_real_sample_review_before_reading_secrets(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('must not read secrets')):
            for mode in ('verified', 'legacy', 'invalid'):
                with self.assertRaises(ValueError):
                    publication.switch(mode)

    def test_blank_values_cannot_consume_following_comment_or_next_key(self):
        text = '\n'.join(f'{name}={value}' for name, value in VALUES.items())
        self.assertEqual(collection.credentials(text), VALUES)
        for invalid in [text.replace('LH_API_KEY=' + VALUES['LH_API_KEY'], 'LH_API_KEY=\n# explanation'),
                        text + '\nOPENAI_API_KEY=duplicate', text.replace('sk-example-personal-only', '${OTHER_SECRET}')]:
            with self.assertRaises(ValueError) as failure:
                collection.credentials(invalid)
            self.assertNotIn('example', str(failure.exception))
            self.assertNotIn('OTHER_SECRET', str(failure.exception))

    def test_merging_preserves_other_credentials_and_does_not_enable_auto_publication(self):
        original = 'KAKAO_CLIENT_SECRET=existing-oauth\nEXTRACTION_MONTHLY_BUDGET_USD=0\n'
        merged = collection.merge(original, {**VALUES, **collection.SETTINGS})
        self.assertIn('KAKAO_CLIENT_SECRET=existing-oauth', merged)
        self.assertEqual(merged.count('EXTRACTION_MONTHLY_BUDGET_USD='), 1)
        self.assertIn('EXTRACTION_MONTHLY_BUDGET_USD=10', merged)
        self.assertIn('EXTRACTION_PUBLICATION_MODE=manual', merged)

    def test_migration_failure_stops_only_workers_and_restores_previous_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            original = 'S3_BUCKET=mujuthaek-personal-659355919826-raw\nKAKAO_CLIENT_SECRET=keep-existing\n'
            (base / '.env').write_text(original)
            config = {'services': {
                'collector': {'image': 'collector:test', 'environment': {k: v for k, v in VALUES.items() if k != 'OPENAI_API_KEY'}},
                'extraction': {'image': 'extraction:test', 'environment': {'OPENAI_API_KEY': VALUES['OPENAI_API_KEY'],
                               'EXTRACTION_MONTHLY_BUDGET_USD': '10', 'EXTRACTION_PUBLICATION_MODE': 'manual'}}}}
            count = 0

            def private_file(text):
                nonlocal count
                count += 1
                path = base / f'pending-{count}'
                path.write_text(text)
                return path

            def compose(_env, *args):
                if args[:1] == ('config',):
                    return SimpleNamespace(stdout=json.dumps(config))
                if args[:1] == ('run',):
                    raise subprocess.CalledProcessError(1, ['migration'])
                return SimpleNamespace(stdout='')

            with patch.object(collection, 'BASE', base), patch.object(collection, 'private_file', side_effect=private_file), \
                    patch.object(collection, 'compose', side_effect=compose) as calls, patch.object(collection.subprocess, 'run'):
                with self.assertRaises(RuntimeError):
                    collection.apply(VALUES, 'a' * 40)
            self.assertEqual((base / '.env').read_text(), original)
            self.assertTrue(any(call.args[1:] == ('stop', 'collector', 'extraction') for call in calls.call_args_list))
            self.assertFalse(any('api' in call.args[1:] or 'notification' in call.args[1:] for call in calls.call_args_list))


if __name__ == '__main__':
    unittest.main()
