import importlib.util
import json
import re
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = load('release_host', Path(__file__).resolve().parents[1] / 'release_host.py')
guard = load('pr_direction', ROOT / '.github/scripts/pr_direction.py')
frontend = load('frontend_release', ROOT / '.github/scripts/frontend_release.py')
publisher = load('backend_release', ROOT / '.github/scripts/backend_release.py')
release_role = load('setup_github_release', Path(__file__).resolve().parents[1] / 'setup_github_release.py')


def image_archive(path, tags, extra=()):
    """A minimal `docker save` style archive: manifest.json with RepoTags, gzip-compressed. Returns its bytes."""
    import io
    import tarfile
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, content in [*extra, ('manifest.json', json.dumps([{'RepoTags': [tag]} for tag in tags]).encode())]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    Path(path).write_bytes(buffer.getvalue())
    return buffer.getvalue()


def manifest(release='release-123'):
    return {'release': release, 'archive_sha256': 'a' * 64,
            'images': {s: {'tag': f'mujuthaek-personal-{s}:{release}', 'id': 'sha256:' + 'b' * 64}
                       for s in ('api', 'notification')}}


class ReleaseSafety(unittest.TestCase):



    def test_deploy_role_can_create_but_never_replace_release_objects(self):
        # Security audit L-17: a replaced archive or manifest would make a later "rollback to a good release" redeploy
        # whatever a stolen deploy token stored there.
        statements = release_role.release_policy()['Statement']
        puts = [statement for statement in statements if statement['Action'] == 's3:PutObject']
        create_only = [statement for statement in puts if 'Condition' in statement]
        self.assertEqual([statement['Resource'] for statement in create_only],
                         [release_role.BUCKET + '/deployments/releases/*'])
        self.assertEqual(create_only[0]['Condition'], {'StringEquals': {'s3:if-none-match': '*'}})
        replaceable = [resource for statement in puts if 'Condition' not in statement for resource in statement['Resource']]
        # Exactly the pointers the release scripts rewrite; nothing else is replaceable.
        self.assertEqual(replaceable, [release_role.BUCKET + '/deployments/' + key for key in publisher.MUTABLE])
        self.assertNotIn('Delete', json.dumps(statements))

    def test_release_publisher_refuses_to_replace_anything_but_the_pointers(self):
        with patch.object(publisher, 'aws') as command:
            publisher.put('releases/release-123/manifest.json', 'manifest.json', immutable=True)
            self.assertEqual(command.call_args.args[-2:], ('--if-none-match', '*'))
            publisher.put('releases/current.json', 'production-current.json')
            publisher.put('desired.json', 'desired.json')
            for key in ('releases/release-123/manifest.json', 'releases/release-123/images.tar.gz', 'states/current.json'):
                with self.assertRaises(ValueError):
                    publisher.put(key, 'manifest.json')
            self.assertEqual(command.call_count, 3)

    def test_workflows_upload_release_objects_only_as_create_only_puts(self):
        uploads = 0
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            text = path.read_text(encoding='utf-8').replace('\\\n', ' ')
            for line in text.splitlines():
                if 'deployments/releases/' not in line or line.strip().startswith('#'):
                    continue
                if re.search(r'\bs3api\s+(head-object|get-object)\b', line):
                    continue  # reads only (a re-run keeps an already stored pair)
                with self.subTest(workflow=path.name, line=line.strip()):
                    self.assertNotRegex(line, r'\baws\s+s3\s+(cp|mv|sync)\b')
                    self.assertIn('s3api put-object', line)
                    self.assertIn("--if-none-match '*'", line)
                    uploads += 1
        self.assertGreater(uploads, 0)


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
        obj.worker_cpu_budget = nullcontext
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
                data = manifest()
                tags = [image['tag'] for image in data['images'].values()]
                body = image_archive(obj.runtime / 'images.tar.gz', tags)
                import hashlib
                data['archive_sha256'] = hashlib.sha256(body).hexdigest()
                (obj.runtime / 'candidate.json').write_text(json.dumps(data))
                schemas = iter(['schema-a', 'schema-b' if changed else 'schema-a'])
                obj.schema = lambda: next(schemas)
                selected = []
                def select(release):
                    selected.append(release)
                    if release == 'release-123':
                        raise RuntimeError('unhealthy')
                obj.select = select
                loaded = ''.join(f'Loaded image: {tag}\n' for tag in tags)
                def run(args, **kwargs):
                    return SimpleNamespace(stdout=loaded if args[:2] == ['docker', 'load'] else 'sha256:' + 'b' * 64)
                with patch.object(host.subprocess, 'run', side_effect=run):
                    with self.assertRaises(RuntimeError):
                        obj.apply({'release': 'release-123', 'mode': 'deploy'})
                self.assertEqual(selected, ['release-123'] if changed else ['release-123', 'release-old'])


if __name__ == '__main__':
    unittest.main()
