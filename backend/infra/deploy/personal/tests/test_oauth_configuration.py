import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('configure_oauth', Path(__file__).resolve().parents[1] / 'configure_oauth.py')
oauth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oauth)

VALUES = {'KAKAO_CLIENT_ID': 'example-kakao-id', 'KAKAO_CLIENT_SECRET': 'example-kakao-secret',
          'GOOGLE_CLIENT_ID': 'example.apps.googleusercontent.com', 'GOOGLE_CLIENT_SECRET': 'example-google-secret'}


class OAuthConfiguration(unittest.TestCase):
    def test_rejects_missing_duplicate_and_interpolated_values_without_echoing(self):
        valid = '\n'.join(f'{name}={value}' for name, value in VALUES.items())
        self.assertEqual(oauth.credentials(valid), VALUES)
        self.assertEqual(oauth.credentials('\ufeff' + valid), VALUES)
        for text in [valid + '\nKAKAO_CLIENT_ID=duplicate', valid.replace('example-kakao-secret', '${OTHER_SECRET}'),
                     valid.replace('example-google-secret', ''), 'KAKAO_CLIENT_ID=example']:
            with self.subTest(case=text.splitlines()[0]), self.assertRaises(ValueError) as failure:
                oauth.credentials(text)
            self.assertNotIn('example', str(failure.exception))
            self.assertNotIn('OTHER_SECRET', str(failure.exception))

    def test_merging_preserves_existing_settings_and_replaces_old_oauth_values(self):
        original = 'S3_BUCKET=existing\nJWT_SECRET=keep-this-value\nKAKAO_CLIENT_ID=old-value\n'
        merged = oauth.merge(original, VALUES)
        self.assertIn('JWT_SECRET=keep-this-value', merged)
        self.assertIn('S3_BUCKET=existing', merged)
        self.assertNotIn('old-value', merged)
        self.assertEqual(merged.count('KAKAO_CLIENT_ID='), 1)

    def run_apply(self, directory, fail_restart=False, bind=True):
        root = Path(directory)
        original = 'S3_BUCKET=mujuthaek-personal-659355919826-raw\nOAUTH_REDIRECT_BASE_URL=https://mujuthaek.vercel.app\nJWT_SECRET=synthetic-original\n'
        (root / '.env').write_text(original)
        count = 0
        def private(content):
            nonlocal count
            count += 1
            path = root / f'.pending-{count}'
            path.write_text(content)
            return path
        environment = VALUES if bind else {}
        compose = Mock(side_effect=[SimpleNamespace(stdout=json.dumps({'services': {'api': {'environment': environment}}})),
                                    SimpleNamespace(stdout='example-container')])
        inspect = SimpleNamespace(stdout=json.dumps([{'Config': {'Env': [f'{k}={v}' for k, v in VALUES.items()]}}]))
        restart = Mock(side_effect=[RuntimeError('synthetic failure'), None] if fail_restart else None)
        with patch.object(oauth, 'BASE', root), patch.object(oauth, 'private_file', side_effect=private), \
                patch.object(oauth, 'compose', compose), patch.object(oauth, 'restart', restart), \
                patch.object(oauth.subprocess, 'run', return_value=inspect):
            if fail_restart or not bind:
                with self.assertRaises(RuntimeError) as failure:
                    oauth.apply(VALUES)
                for value in VALUES.values():
                    self.assertNotIn(value, str(failure.exception))
                self.assertEqual((root / '.env').read_text(), original)
            else:
                oauth.apply(VALUES)
                self.assertEqual((root / '.env').read_text(), oauth.merge(original, VALUES))
        return restart

    def test_missing_compose_bindings_does_not_replace_environment_or_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            restart = self.run_apply(directory, bind=False)
            restart.assert_not_called()

    def test_failed_restart_restores_original_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            restart = self.run_apply(directory, fail_restart=True)
            self.assertEqual(restart.call_count, 2)

    def test_success_checks_container_receives_values(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_apply(directory).assert_called_once()

    def test_restart_names_api_only_and_never_builds_images(self):
        with patch.object(oauth, 'compose') as compose, patch.object(oauth, 'healthy'):
            oauth.restart(Path('.env'))
        self.assertEqual(compose.call_args_list[0].args,
                         (Path('.env'), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'api'))


if __name__ == '__main__':
    unittest.main()
