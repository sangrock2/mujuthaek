import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gate import verify
from plan import FLAGS, affected, changed, deployment_selection, python_locks, validate


class SelectionTests(unittest.TestCase):
    def selected(self, paths):
        return {k for k, v in affected(paths).items() if v}

    def test_service_isolation(self):
        cases = {
            'backend/services/api/src/main/java/Api.java': {'api', 'e2e'},
            'backend/services/api/src/test/java/ApiTest.java': {'api'},
            'backend/services/notification/src/main/java/Mail.java': {'notification'},
            'backend/services/collector/src/worker.py': {'collector'},
            'backend/services/extraction/src/review.py': {'extraction'},
            'backend/services/extraction/src/rules/prompt.v30.md': {'extraction'},
            'frontend/src/content/privacy.md': {'frontend', 'e2e'},
            'frontend/src/app/page.tsx': {'frontend', 'e2e'},
            'frontend/tests/ui.test.ts': {'frontend'},
            'frontend/e2e/login.spec.ts': {'e2e'},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.selected([path]), expected)

    def test_shared_inputs_and_dependencies(self):
        self.assertEqual(self.selected(['backend/libs/python-platform/src/logging.py']), {'platform', 'collector', 'extraction'})
        self.assertEqual(self.selected(['backend/libs/java-common/build.gradle.kts']), {'api', 'notification', 'e2e', 'dependencies'})
        self.assertEqual(self.selected(['backend/services/collector/uv.lock']), {'collector', 'dependencies'})
        contracts = self.selected(['backend/contracts/events/notice.v1.json'])
        self.assertEqual(contracts, {'contracts', 'api', 'notification', 'platform', 'collector', 'extraction', 'broker', 'e2e'})
        self.assertEqual(self.selected(['backend/services/extraction/data/legal-dong-codes/codes.csv']), {'api', 'extraction', 'e2e'})

    def test_docs_and_workflow_only_changes_do_not_run_applications(self):
        self.assertEqual(self.selected(['README.md', 'docs/security/report.md']), set())
        self.assertEqual(self.selected(['.github/workflows/checks.yml']), {'workflows', 'infra', 'dependencies'})
        self.assertEqual(self.selected(['backend/infra/ci/plan.py']), {'infra'})
        self.assertEqual(self.selected(['backend/infra/deploy/personal/operations_monitor.py']), {'infra'})
        self.assertEqual(self.selected(['.github/workflows/web.yml']), {'workflows', 'infra', 'dependencies', 'frontend'})

    def test_only_changed_python_dependency_manifests_are_audited(self):
        self.assertEqual(python_locks(['backend/services/collector/src/a.py', '.github/workflows/ci.yml']), [])
        self.assertEqual(python_locks(['backend/services/collector/pyproject.toml']), ['backend/services/collector/uv.lock'])

    def test_production_inventory_and_initial_deployment_fail_closed(self):
        self.assertEqual(deployment_selection({'paths': [], 'components': []}), affected([]))
        self.assertTrue(all(deployment_selection({'paths': [], 'components': ['api']}).values()))
        api = deployment_selection({'paths': ['backend/services/api/src/main/java/A.java'], 'components': ['api']})
        self.assertEqual({k for k, v in api.items() if v}, {'api', 'e2e'})
        for value in ({}, {'paths': [], 'components': ['unknown']}):
            with self.assertRaises(ValueError):
                deployment_selection(value)

    def test_filenames_are_data_not_workflow_or_shell_commands(self):
        path = 'frontend/src/a\n::warning::synthetic.ts'
        with patch('plan.subprocess.check_output', side_effect=['a' * 40, (path + '\0').encode()]):
            paths, _ = changed('a' * 40, 'b' * 40)
        self.assertEqual(paths, [path])
        self.assertEqual(self.selected(paths), {'frontend', 'e2e'})

    def test_gateway_secret_settings_and_unknown_inputs(self):
        self.assertEqual(self.selected(['backend/infra/deploy/personal/nginx.conf']), {'infra', 'gateway'})
        self.assertEqual(self.selected(['.gitleaks.toml']), {'infra', 'full_secrets'})
        self.assertEqual(self.selected(['new-shared-build-input.json']), set(FLAGS))

    def test_union_and_invalid_input(self):
        self.assertEqual(self.selected(['backend/services/collector/a.py', 'backend/services/notification/a.java']), {'collector', 'notification'})
        for value in (['../outside'], ['/absolute'], [''], [None]):
            with self.assertRaises(ValueError):
                affected(value)
        for value in ({}, dict.fromkeys(FLAGS, 'false'), {**dict.fromkeys(FLAGS, False), 'unknown': False}):
            with self.assertRaises(ValueError):
                validate(value)

    def test_git_diff_uses_both_sides_of_renames(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.check_output(['git', '-C', folder, *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-q')
            git('config', 'user.email', 'ci-test@example.invalid')
            git('config', 'user.name', 'CI test')
            p = Path(folder) / 'backend/services/collector/worker.py'
            p.parent.mkdir(parents=True)
            p.write_text('synthetic')
            git('add', '.')
            git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD')
            target = Path(folder) / 'backend/services/extraction/worker.py'
            target.parent.mkdir(parents=True)
            p.rename(target)
            git('add', '-A')
            git('commit', '-qm', 'move')
            head = git('rev-parse', 'HEAD')
            real = subprocess.check_output
            def inside(command, **kwargs):
                return real(['git', '-C', folder, *command[1:]], **kwargs)
            with patch('plan.subprocess.check_output', side_effect=inside):
                paths, actual_base = changed(base, head)
            self.assertEqual(actual_base, base)
            self.assertEqual(self.selected(paths), {'collector', 'extraction'})
        with self.assertRaises(ValueError):
            changed('--all', 'a' * 40)


class GateTests(unittest.TestCase):
    def test_production_api_only_requires_api_backend_and_browser_but_not_web_or_contracts(self):
        s = affected(['backend/services/api/src/main/java/Api.java'])
        r = {'plan': {'result': 'success'}, 'web-check': {'result': 'skipped'},
             'backend-check': {'result': 'success'}, 'contracts-check': {'result': 'skipped'},
             'e2e-check': {'result': 'success'}}
        verify(s, r, production=True)
        with self.assertRaises(ValueError):
            verify(s, {**r, 'backend-check': {'result': 'skipped'}}, production=True)

    def test_docs_only_passes_and_cannot_hide_missing_or_cancelled_secret_scan(self):
        s = affected(['README.md'])
        r = {name: {'result': 'skipped'} for name in ('dependencies', 'web', 'backend', 'contracts', 'e2e', 'workflows')}
        r.update(plan={'result': 'success'}, secrets={'result': 'success'})
        verify(s, r)
        for status in ('skipped', 'failure', 'cancelled', None):
            with self.assertRaises(ValueError):
                verify(s, {**r, 'secrets': {'result': status}})

    def test_selected_failures_and_unexpected_skips_are_rejected(self):
        s = affected(['backend/services/collector/worker.py'])
        r = {name: {'result': 'skipped'} for name in ('java', 'extraction', 'platform', 'infra', 'gateway', 'broker')}
        r.update(plan={'result': 'success'}, collector={'result': 'success'})
        verify(s, r, backend=True)
        for status in ('skipped', 'failure', 'cancelled'):
            with self.assertRaises(ValueError):
                verify(s, {**r, 'collector': {'result': status}}, backend=True)
        with self.assertRaises(ValueError):
            verify(s, {**r, 'plan': {'result': 'failure'}}, backend=True)
        with self.assertRaises(ValueError):
            verify(s, {**r, 'java': {'result': 'success'}}, backend=True)


if __name__ == '__main__':
    unittest.main()
