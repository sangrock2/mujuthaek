"""Runtime selection and mixed-version snapshots must preserve untouched services."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / '.github/scripts'))
import backend_release as backend
import deployment_plan as planner
import production_release as production
import frontend_release as frontend

spec = importlib.util.spec_from_file_location('selective_host', Path(__file__).resolve().parents[1] / 'release_host.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def image(service, release):
    return {'tag': f'mujuthaek-personal-{service}:{release}', 'id': 'sha256:' + 'a' * 64}


def snapshot(release='release-old'):
    return {'format': 2, 'release': release, 'commit': 'a' * 40,
            'images': {s: image(s, release) for s in host.SERVICES},
            'archive_services': [], 'archive_sha256': None,
            'frontend': {'id': 'dpl_old', 'url': 'old.vercel.app', 'commit': 'b' * 40}}


@contextmanager
def workspace():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(previous)


class Selection(unittest.TestCase):
    def test_runtime_and_shared_dependencies(self):
        cases = [
            (['frontend/src/app/page.tsx'], ['frontend']),
            (['frontend/pnpm-lock.yaml'], ['frontend']),
            (['backend/services/api/src/main/java/Api.java'], ['api']),
            (['backend/services/api/Dockerfile'], ['api']),
            (['backend/services/notification/src/main/resources/application.yml'], ['notification']),
            (['backend/contracts/events/notice.v1.json'], ['api', 'notification']),
            (['backend/services/extraction/data/legal-dong-codes/codes.csv'], ['api']),
            (['backend/.dockerignore'], ['api', 'notification']),
            (['README.md', 'docs/deployment.md', 'frontend/README.md'], []),
            (['backend/services/api/src/test/java/Test.java', '.github/workflows/checks.yml'], []),
            (['backend/services/collector/src/main.py', 'backend/libs/python-platform/pyproject.toml'], []),
            (['backend/services/api/Old.java', 'backend/services/notification/New.java'], ['api', 'notification']),
            (['new-shared-build-input.json'], list(planner.COMPONENTS)),
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(planner.affected(paths), expected)

    def test_diff_uses_last_completed_commit_not_previous_main_commit(self):
        with patch.object(planner.subprocess, 'run', return_value=SimpleNamespace(stdout=b'frontend/deleted.ts\0backend/services/api/moved.java\0')) as run:
            self.assertEqual(planner.changed_paths('last-completed', 'new-main'),
                             ['frontend/deleted.ts', 'backend/services/api/moved.java'])
            self.assertEqual(run.call_args_list[-1].args[0],
                             ['git', 'diff', '--no-renames', '--name-only', '-z', 'last-completed', 'new-main'])

    def test_uncertain_server_state_blocks_new_plan(self):
        with patch.object(backend, 'get', side_effect=[{'release': 'release-old'}, snapshot(),
                                                     {'release': 'release-partial', 'protocol': 2}]):
            with self.assertRaisesRegex(RuntimeError, 'reconcile'):
                planner.plan('c' * 40)


class HostSelection(unittest.TestCase):
    def fake(self, directory, target):
        obj = host.Host.__new__(host.Host)
        obj.runtime = Path(directory)
        old = snapshot()
        obj.current = lambda: {'release': old['release'], 'images': old['images']}
        obj.schema = lambda: 'same-schema'
        obj.download = Mock(side_effect=lambda key, name: obj.runtime / name)
        obj.upload = Mock()
        obj.select = Mock()
        obj.ensure_images = Mock()
        (obj.runtime / 'candidate.json').write_text(json.dumps(target))
        return obj

    def test_frontend_only_never_restarts_or_backs_up_backend(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host.subprocess, 'run') as command:
            obj = self.fake(directory, snapshot('release-new'))
            target = snapshot('release-new')
            target['images'] = snapshot()['images']
            (obj.runtime / 'candidate.json').write_text(json.dumps(target))
            result = obj.apply({'release': 'release-new', 'mode': 'deploy', 'expected_base': 'release-old'})
            self.assertEqual(result['changed_services'], [])
            self.assertEqual(result['images'], snapshot()['images'])
            obj.select.assert_not_called()
            obj.ensure_images.assert_not_called()
            command.assert_not_called()
            self.assertIn(('state.json', 'states/current.json'), [call.args for call in obj.upload.call_args_list])

    def test_api_only_and_mixed_snapshot_rollback_leave_notification_untouched(self):
        for mode in ['deploy', 'rollback']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, patch.object(host.subprocess, 'run'):
                target = snapshot('release-new')
                target['images']['notification'] = snapshot()['images']['notification']
                obj = self.fake(directory, target)
                (obj.runtime / 'target-state.json').write_text(json.dumps({'schema': 'same-schema'}))
                result = obj.apply({'release': 'release-new', 'mode': mode})
                self.assertEqual(result['changed_services'], ['api'])
                obj.select.assert_called_once_with('release-new', target['images'], ['api'])
                obj.ensure_images.assert_called_once_with(target, ['api'])

    def test_health_failure_restores_only_changed_service(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host.subprocess, 'run'):
            target = snapshot('release-new')
            target['images']['notification'] = snapshot()['images']['notification']
            obj = self.fake(directory, target)
            obj.select.side_effect = [RuntimeError('unhealthy'), None]
            with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                obj.apply({'release': 'release-new', 'mode': 'deploy'})
            self.assertEqual(obj.select.call_args_list[-1].args,
                             ('release-old', snapshot()['images'], ['api']))

    def test_stale_plan_never_changes_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = self.fake(directory, snapshot('release-new'))
            with self.assertRaisesRegex(RuntimeError, 'planned base'):
                obj.apply({'release': 'release-new', 'mode': 'deploy', 'expected_base': 'release-other'})
            obj.download.assert_not_called()
            obj.select.assert_not_called()

    def test_compose_up_names_only_selected_service(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(host, 'BASE', Path(directory)):
            obj = host.Host.__new__(host.Host)
            obj.compose, obj.healthy = Mock(), Mock()
            (Path(directory) / 'versions.env').write_text('RELEASE=release-initial\n')
            data = snapshot('release-new')
            data['images']['notification'] = snapshot()['images']['notification']
            obj.select('release-new', data['images'], ['api'])
            up = [call.args for call in obj.compose.call_args_list if call.args[0] == 'up'][0]
            self.assertEqual(up[-1], 'api')
            self.assertNotIn('notification', up)
            self.assertIn('NOTIFICATION_RELEASE=release-old', (Path(directory) / 'versions.env').read_text())

    def test_missing_inherited_image_is_loaded_from_its_origin_release(self):
        with tempfile.TemporaryDirectory() as directory:
            target = snapshot('release-new')
            target['images']['notification'] = image('notification', 'release-origin')
            obj = self.fake(directory, target)
            origin = snapshot('release-origin')
            origin['archive_services'] = ['notification']
            origin['archive_sha256'] = 'a' * 64
            (Path(directory) / 'origin-release-origin.json').write_text(json.dumps(origin))
            obj.load_archive = Mock()
            command = [SimpleNamespace(returncode=1, stdout=''), SimpleNamespace(stdout=target['images']['notification']['id'])]
            with patch.object(host.subprocess, 'run', side_effect=command):
                host.Host.ensure_images(obj, target, ['notification'])
            obj.load_archive.assert_called_once_with(origin, 'images-release-origin.tar.gz')


class Coordinator(unittest.TestCase):
    def test_result_timeout_does_not_issue_competing_rollback(self):
        with workspace():
            base = snapshot()
            Path('base-release.json').write_text(json.dumps(base))
            def remember():
                Path('frontend-before.json').write_text(json.dumps(base['frontend']))
            environment = {'GITHUB_REPOSITORY': 'sangrock2/mujuthaek', 'GITHUB_REF': 'refs/heads/main',
                           'GITHUB_SHA': 'c' * 40, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
                           'ROLLBACK_RELEASE': ''}
            with patch.dict(os.environ, environment), \
                    patch.object(planner, 'plan', return_value={'components': ['api']}), \
                    patch.object(frontend, 'remember_current', side_effect=remember), \
                    patch.object(frontend, 'promote') as promote, \
                    patch.object(production, 'archive_images'), patch.object(backend, 'publish'), \
                    patch.object(backend, 'request', side_effect=TimeoutError('uncertain')) as request, \
                    patch.object(production, 'complete') as complete:
                with self.assertRaises(TimeoutError):
                    production.main()
                self.assertEqual(request.call_count, 1)
                promote.assert_not_called()
                complete.assert_not_called()

    def test_rollback_of_api_only_snapshot_does_not_rebuild_frontend(self):
        with workspace():
            base, target = snapshot(), snapshot('release-target')
            target['commit'] = 'd' * 40
            target['images']['notification'] = base['images']['notification']
            Path('base-release.json').write_text(json.dumps(base))
            def remember():
                Path('frontend-before.json').write_text(json.dumps(base['frontend']))
            def request(*args, **kwargs):
                Path('deployment-result.json').write_text(json.dumps({'release': args[0]}))
            environment = {'GITHUB_REPOSITORY': 'sangrock2/mujuthaek', 'GITHUB_REF': 'refs/heads/main',
                           'GITHUB_SHA': 'c' * 40, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
                           'ROLLBACK_RELEASE': 'release-target'}
            with patch.dict(os.environ, environment), patch.object(planner, 'plan', return_value={'components': []}), \
                    patch.object(frontend, 'remember_current', side_effect=remember), \
                    patch.object(frontend, 'restore_candidate') as candidate, \
                    patch.object(frontend, 'promote') as promote, \
                    patch.object(backend, 'get', return_value=target), \
                    patch.object(backend, 'request', side_effect=request) as apply, \
                    patch.object(production, 'smoke'), patch.object(production, 'complete'):
                production.main()
                candidate.assert_not_called()
                promote.assert_not_called()
                self.assertEqual(apply.call_args.args[:2], ('release-target', 'rollback'))
                self.assertEqual(json.loads(Path('deployment-plan.json').read_text())['components'], ['api'])

    def test_frontend_restore_uses_component_commit_not_snapshot_commit(self):
        with workspace():
            Path('.vercelignore').write_text('backend\n')
            Path('target-release.json').write_text(json.dumps(snapshot()))
            with patch.object(frontend.subprocess, 'run', return_value=SimpleNamespace(stdout=b'')) as command, \
                    patch.object(frontend, 'candidate') as candidate:
                frontend.restore_candidate()
                self.assertEqual(command.call_args_list[0].args[0],
                                 ['git', 'merge-base', '--is-ancestor', 'b' * 40, 'origin/main'])
                candidate.assert_called_once()

    def test_frontend_only_and_api_only_do_not_deploy_other_components(self):
        for selected in [['frontend'], ['api'], ['notification'], []]:
            with self.subTest(selected=selected), workspace():
                base = snapshot()
                Path('base-release.json').write_text(json.dumps(base))
                def remember():
                    Path('frontend-before.json').write_text(json.dumps(base['frontend']))
                def candidate():
                    Path('frontend-deployment.json').write_text(json.dumps({'id': 'dpl_new', 'url': 'new.vercel.app'}))
                def request(*args, **kwargs):
                    Path('deployment-result.json').write_text(json.dumps({'release': args[0]}))
                environment = {'GITHUB_REPOSITORY': 'sangrock2/mujuthaek', 'GITHUB_REF': 'refs/heads/main',
                               'GITHUB_SHA': 'c' * 40, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
                               'ROLLBACK_RELEASE': ''}
                with patch.dict(os.environ, environment), \
                        patch.object(planner, 'plan', return_value={'components': selected}), \
                        patch.object(production.frontend, 'remember_current', side_effect=remember) as read, \
                        patch.object(production.frontend, 'candidate', side_effect=candidate) as build, \
                        patch.object(production.frontend, 'promote') as promote, \
                        patch.object(production, 'archive_images') as archive, \
                        patch.object(backend, 'publish') as publish, \
                        patch.object(backend, 'request', side_effect=request) as apply, \
                        patch.object(production, 'smoke'), patch.object(production, 'complete'):
                    production.main()
                    self.assertEqual(build.call_count, int('frontend' in selected))
                    self.assertEqual(promote.call_count, int('frontend' in selected))
                    if selected:
                        services = [s for s in host.SERVICES if s in selected]
                        archive.assert_called_once_with('c' * 40 + '-123-1', services)
                        self.assertEqual(publish.call_args.kwargs['services'], services)
                        if 'frontend' not in selected:
                            self.assertEqual(publish.call_args.kwargs['frontend']['commit'], 'b' * 40)
                        self.assertEqual(apply.call_args.kwargs['expected_base'], 'release-old')
                    else:
                        read.assert_not_called()
                        archive.assert_not_called()
                        apply.assert_not_called()

    def test_snapshot_commit_does_not_replace_inherited_frontend_source(self):
        old = snapshot()
        new = snapshot('release-new')
        new['commit'] = 'c' * 40
        self.assertEqual(production.frontend_source(old), production.frontend_source(new))

    def test_frontend_only_manifest_has_no_image_archive_and_preserves_tags(self):
        with workspace(), patch.object(backend, 'put') as put, patch.object(backend.subprocess, 'run') as command:
            base = snapshot()
            data = backend.publish('release-new', 'c' * 40, base=base, services=[], frontend=base['frontend'])
            self.assertEqual(data['images'], base['images'])
            self.assertIsNone(data['archive_sha256'])
            put.assert_called_once_with('releases/release-new/manifest.json', 'manifest.json', immutable=True)
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
