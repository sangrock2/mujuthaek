import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load('release_host', Path(__file__).resolve().parents[1] / 'release_host.py')
guard = load('pr_direction', ROOT / '.github/scripts/pr_direction.py')
frontend = load('frontend_release', ROOT / '.github/scripts/frontend_release.py')


def manifest(release='release-123'):
    return {'release': release, 'archive_sha256': 'a' * 64,
            'images': {s: {'tag': f'mujuthaek-personal-{s}:{release}', 'id': 'sha256:' + 'b' * 64}
                       for s in ('api', 'notification')}}


class ReleaseSafety(unittest.TestCase):
    def test_vercel_cli_errors_redact_credentials(self):
        with patch.dict('os.environ', {'VERCEL_TOKEN': 'synthetic-vercel-secret'}):
            failed = SimpleNamespace(returncode=1, stdout='', stderr='Rejected synthetic-vercel-secret')
            with patch.object(frontend.subprocess, 'run', return_value=failed):
                with self.assertRaises(RuntimeError) as error:
                    frontend.vercel('deploy')
                self.assertNotIn('synthetic-vercel-secret', str(error.exception))
                self.assertIn('[REDACTED]', str(error.exception))

    def test_vercel_candidate_is_bound_to_existing_team_and_project(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'VERCEL_TOKEN': 'synthetic-token'}):
            with patch.object(frontend, 'vercel', return_value={'deployment': {'id': 'dpl_example', 'url': 'https://example.vercel.app', 'readyState': 'READY'}}) as command:
                with patch.object(frontend.Path, 'write_text') as write:
                    frontend.candidate(cwd=directory)
                    self.assertIn(frontend.PROJECT, write.call_args_list[0].args[0])
                    self.assertIn(frontend.TEAM, write.call_args_list[0].args[0])
                command.assert_called_once_with('deploy', '--prod', '--skip-domain', cwd=directory)

    def test_exact_repository_dev_to_main_only(self):
        for base, head, repo, expected in [
            ('main', 'dev', 'sangrock2/mujuthaek', True),
            ('main', 'dev', 'attacker/mujuthaek', False),
            ('main', 'feat/x', 'sangrock2/mujuthaek', False),
            ('dev', 'feat/x', 'sangrock2/mujuthaek', True),
            ('other', 'dev', 'sangrock2/mujuthaek', False),
        ]:
            event = {'pull_request': {'base': {'ref': base}, 'head': {'ref': head, 'repo': {'full_name': repo}}}}
            self.assertEqual(guard.allowed(event, 'sangrock2/mujuthaek'), expected)

    def test_reject_path_and_shell_injection(self):
        for value in ['../release', 'x;whoami', 'release/123', '$(id)', '', 'A' * 40]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                host.release_id(value)

    def test_require_exact_service_tags_and_digests(self):
        self.assertEqual(host.manifest(manifest())['release'], 'release-123')
        for field, value in [('tag', 'other/api:latest'), ('id', 'latest')]:
            data = manifest()
            data['images']['api'][field] = value
            with self.assertRaises(ValueError):
                host.manifest(data)

    def fake(self, directory):
        obj = host.Host.__new__(host.Host)
        obj.runtime = Path(directory)
        obj.current = lambda: {'release': 'release-old'}
        obj.schema = lambda: 'schema-a'
        obj.download = lambda key, name: obj.runtime / name
        (obj.runtime / 'candidate.json').write_text(json.dumps(manifest()))
        return obj

    def test_same_release_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            obj = self.fake(d)
            self.assertEqual(obj.apply({'release': 'release-old'})['release'], 'release-old')

    def test_schema_mismatch_blocks_historical_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            obj = self.fake(d)
            (obj.runtime / 'target-state.json').write_text(json.dumps({'schema': 'different'}))
            with self.assertRaisesRegex(RuntimeError, 'DB schema differs'):
                obj.apply({'release': 'release-123', 'mode': 'rollback'})

    def test_bad_archive_never_loads_or_changes_containers(self):
        with tempfile.TemporaryDirectory() as d, patch.object(host.subprocess, 'run') as run:
            obj = self.fake(d)
            (obj.runtime / 'images.tar.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                obj.apply({'release': 'release-123', 'mode': 'deploy'})
            run.assert_not_called()

    def test_failed_health_restores_old_app_only_when_schema_unchanged(self):
        for changed in [False, True]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as d:
                obj = self.fake(d)
                (obj.runtime / 'images.tar.gz').write_bytes(b'archive')
                data = manifest()
                import hashlib
                data['archive_sha256'] = hashlib.sha256(b'archive').hexdigest()
                (obj.runtime / 'candidate.json').write_text(json.dumps(data))
                schemas = iter(['schema-a', 'schema-b' if changed else 'schema-a'])
                obj.schema = lambda: next(schemas)
                selected = []
                def select(release):
                    selected.append(release)
                    if release == 'release-123':
                        raise RuntimeError('unhealthy')
                obj.select = select
                with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(stdout='sha256:' + 'b' * 64)):
                    with self.assertRaises(RuntimeError):
                        obj.apply({'release': 'release-123', 'mode': 'deploy'})
                self.assertEqual(selected, ['release-123'] if changed else ['release-123', 'release-old'])


if __name__ == '__main__':
    unittest.main()
