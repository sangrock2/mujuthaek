import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('submission', Path(__file__).resolve().parents[1] / 'submit_dependencies.py')
submission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submission)


class SubmissionTests(unittest.TestCase):
    def test_only_canonical_main_events_can_submit(self):
        base = {'GITHUB_REPOSITORY': submission.REPO, 'GITHUB_REF': 'refs/heads/main',
                'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': 'a' * 40,
                'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        for key, value in [('GITHUB_REPOSITORY', 'attacker/fork'), ('GITHUB_REF', 'refs/pull/1/merge'),
                           ('GITHUB_EVENT_NAME', 'pull_request_target'), ('GITHUB_SHA', '../../other')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                submission.snapshot(Path('does-not-exist'), dict(base, **{key: value}))

    def test_runtime_artifacts_include_transitives_without_inventing_edges(self):
        env = {'GITHUB_REPOSITORY': submission.REPO, 'GITHUB_REF': 'refs/heads/main',
               'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': 'a' * 40,
               'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for service in ('api', 'notification'):
                (path / f'{service}.json').write_text(json.dumps([
                    {'package': {'ecosystem': 'Maven', 'name': 'org.example:transitive'}, 'version': '1.2.3+build'}]))
            body = submission.snapshot(path, env)
            self.assertEqual(len(body['manifests']), 2)
            dep = next(iter(next(iter(body['manifests'].values()))['resolved'].values()))
            self.assertEqual(dep['package_url'], 'pkg:maven/org.example/transitive@1.2.3%2Bbuild')
            self.assertNotIn('relationship', dep)
            (path / 'api.json').write_text('[{"package":{"ecosystem":"npm","name":"unexpected"},"version":"1"}]')
            with self.assertRaises(ValueError):
                submission.snapshot(path, env)
