"""Release phases use mocked providers only; uncertain outcomes never publish rival requests."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / '.github/scripts'))
import release_phases as phases


def image(service, release):
    return {'tag': f'mujuthaek-personal-{service}:{release}', 'id': 'sha256:' + 'a' * 64}


def snapshot(release='release-old', frontend_commit='b' * 40):
    return {'release': release, 'commit': 'a' * 40,
            'images': {service: image(service, release) for service in ('api', 'notification')},
            'frontend': {'id': 'dpl_old', 'url': 'old.vercel.app', 'commit': frontend_commit}}


class ReleasePhases(unittest.TestCase):
    def setUp(self):
        self.old_directory = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.old_directory)
        self.enterContext(patch.dict(os.environ, {
            'GITHUB_REPOSITORY': 'sangrock2/mujuthaek', 'GITHUB_REF': 'refs/heads/main',
            'GITHUB_SHA': 'c' * 40, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
        }, clear=True))
        self.base = snapshot()
        self.plan = {'base_release': self.base['release'], 'commit': 'c' * 40,
                     'release': 'release-new', 'rollback': False, 'components': ['frontend', 'api']}
        self.candidate = {'id': 'dpl_new', 'url': 'new.vercel.app', 'commit': 'c' * 40}
        phases.write('base-release.json', self.base)
        self.save_plan()
        phases.write('frontend-before.json', self.base['frontend'])
        phases.write('frontend-deployment.json', self.candidate)
        self.request = self.enterContext(patch.object(phases.backend, 'request'))
        self.publish = self.enterContext(patch.object(phases.backend, 'publish'))
        self.archive = self.enterContext(patch.object(phases.production, 'archive_images'))
        self.complete = self.enterContext(patch.object(phases.production, 'complete'))
        self.smoke = self.enterContext(patch.object(phases.production, 'smoke'))
        self.promote = self.enterContext(patch.object(phases.frontend, 'promote'))
        self.restore = self.enterContext(patch.object(phases.frontend, 'restore_before'))
        self.restore_candidate = self.enterContext(patch.object(phases.frontend, 'restore_candidate'))
        self.candidate_command = self.enterContext(patch.object(phases.frontend, 'candidate'))
        self.remember = self.enterContext(patch.object(phases.frontend, 'remember_current'))
        self.get = self.enterContext(patch.object(phases.backend, 'get'))
        self.planner = self.enterContext(patch.object(phases.planner, 'plan', return_value=dict(self.plan)))

    def save_plan(self):
        phases.write('deployment-plan.json', self.plan)

    def ack(self, info=None):
        phases.write('backend-applied.json', {'release': self.plan['release'], 'request': 'run-123-1',
                                             'frontend': self.candidate if info is None else info})

    def outcome(self, ok=False, restored=True):
        phases.write('frontend-outcome.json', {'release': self.plan['release'], 'ok': ok,
                                              'frontend_restored': restored})

    def test_frontend_jobs_reject_aws_and_oidc_credentials_before_any_provider_call(self):
        for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
                     'ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'ACTIONS_ID_TOKEN_REQUEST_URL'):
            with self.subTest(variable=name), patch.dict(os.environ, {name: 'synthetic-only'}):
                with self.assertRaisesRegex(RuntimeError, 'without AWS or OIDC'):
                    phases.prepare_frontend()
        self.remember.assert_not_called()
        self.candidate_command.assert_not_called()

    def test_aws_jobs_do_not_receive_frontend_token(self):
        with patch.dict(os.environ, {'VERCEL_TOKEN': 'synthetic-only'}):
            with self.assertRaisesRegex(RuntimeError, 'must not receive'):
                phases.apply_backend()
        self.publish.assert_not_called()
        self.request.assert_not_called()

    def test_only_trusted_main_can_mutate_release_state(self):
        for change in ({'GITHUB_REF': 'refs/heads/dev'}, {'GITHUB_REPOSITORY': 'other/repo'}):
            with self.subTest(change=change), patch.dict(os.environ, change):
                with self.assertRaises(RuntimeError):
                    phases.finalize_release()
        self.complete.assert_not_called()
        self.request.assert_not_called()

    def test_workflow_keeps_frontend_jobs_outside_the_aws_permission_boundary(self):
        workflow = (ROOT / '.github/workflows/production.yml').read_text(encoding='utf-8')
        def job(name):
            return re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [a-z][a-z-]*:|\Z)',
                             workflow, re.M | re.S).group(1)
        for name in ('frontend-prepare', 'frontend-promote'):
            with self.subTest(job=name):
                body = job(name)
                self.assertNotIn('id-token: write', body)
                self.assertNotIn('configure-aws-credentials', body)
                self.assertNotIn('npm ', body)
        for name in ('backend-apply', 'finalize'):
            with self.subTest(job=name):
                body = job(name)
                self.assertIn('id-token: write', body)
                self.assertNotIn('VERCEL_TOKEN:', body)
                self.assertNotIn('npm ci', body)
        self.assertIn('role-to-assume: ${{ vars.AWS_PLAN_ROLE_ARN }}', job('plan'))
        self.assertNotIn('AWS_DEPLOY_ROLE_ARN', job('plan'))

    def test_rejects_deployment_shell_url_dns_and_source_inputs(self):
        invalid = [None, [], {'id': '--help', 'url': 'safe.vercel.app'},
                   {'id': 'dpl_ok;id', 'url': 'safe.vercel.app'},
                   {'id': 'dpl_ok', 'url': 'https://safe.vercel.app'},
                   {'id': 'dpl_ok', 'url': 'safe.vercel.app/anything'},
                   {'id': 'dpl_ok', 'url': 'safe.vercel.app.evil.example'},
                   {'id': 'dpl_ok', 'url': 'bad..vercel.app'},
                   {'id': 'dpl_ok', 'url': '-bad.vercel.app'},
                   {'id': 'dpl_ok', 'url': 'bad-.vercel.app'},
                   {'id': 'dpl_ok', 'url': 'x' * 64 + '.vercel.app'},
                   {'id': 'dpl_ok', 'url': 'safe.vercel.app', 'commit': 'main'},
                   {'id': 'dpl_ok', 'url': 'safe.vercel.app', 'extra': 'unexpected'}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                phases.deployment(value)
        with self.assertRaisesRegex(ValueError, 'source disagrees'):
            phases.deployment(self.candidate, 'd' * 40)

    def test_context_requires_boolean_rollback_and_valid_component_list(self):
        for value in (None, 'false', 0, 1):
            self.plan['rollback'] = value
            self.save_plan()
            with self.subTest(value=value), self.assertRaises(ValueError):
                phases.context()
        self.plan['rollback'] = False
        for value in (None, ['api', 'api'], ['worker'], [{}]):
            self.plan['components'] = value
            self.save_plan()
            with self.subTest(value=value), self.assertRaises(ValueError):
                phases.context()

    def test_wrong_plan_base_or_commit_is_rejected_before_publishing(self):
        for field, value in (('base_release', 'release-other'), ('commit', 'd' * 40)):
            old = self.plan[field]
            self.plan[field] = value
            self.save_plan()
            with self.subTest(field=field), self.assertRaises(ValueError):
                phases.apply_backend()
            self.plan[field] = old
        self.publish.assert_not_called()
        self.request.assert_not_called()

    def test_rollback_without_image_changes_still_advances_the_selected_snapshot(self):
        os.environ.update(ROLLBACK_RELEASE='release-previous', GITHUB_OUTPUT='outputs.txt')
        target = dict(self.base, release='release-previous')
        self.get.return_value = target
        phases.plan_release()
        self.assertEqual(phases.read('deployment-plan.json')['components'], [])
        self.assertIn('deploy=true', Path('outputs.txt').read_text())
        self.assertIn('frontend=false', Path('outputs.txt').read_text())

    def test_rollback_selects_only_changed_components_and_never_builds_new_images(self):
        target = snapshot('release-target')
        target['images']['notification'] = self.base['images']['notification']
        self.plan.update(rollback=True, release=target['release'], components=['api'])
        self.save_plan()
        phases.write('target-release.json', target)
        phases.apply_backend()
        self.archive.assert_not_called()
        self.publish.assert_not_called()
        self.request.assert_called_once_with('release-target', 'rollback', 'run-123-1', expected_base='release-old')
        self.assertEqual(phases.read('backend-applied.json')['frontend'], self.base['frontend'])

    def test_prepare_retains_base_frontend_commit_when_no_frontend_change(self):
        self.plan['components'] = ['api']
        self.save_plan()
        phases.prepare_frontend()
        self.candidate_command.assert_not_called()
        self.assertEqual(phases.read('frontend-deployment.json'), self.base['frontend'])

    def test_legacy_frontend_without_own_commit_inherits_base_commit(self):
        self.base['frontend'].pop('commit')
        phases.write('base-release.json', self.base)
        phases.write('frontend-before.json', self.base['frontend'])
        self.plan['components'] = ['notification']
        self.save_plan()
        phases.prepare_frontend()
        phases.apply_backend()
        expected = dict(self.base['frontend'], commit=self.base['commit'])
        self.assertEqual(phases.read('frontend-before.json'), expected)
        self.assertEqual(phases.read('backend-applied.json')['frontend'], expected)

    def test_frontend_drift_blocks_candidate_and_backend_changes(self):
        phases.write('frontend-before.json', dict(self.base['frontend'], id='dpl_outside'))
        for phase in (phases.prepare_frontend, phases.apply_backend):
            with self.subTest(phase=phase.__name__), self.assertRaisesRegex(RuntimeError, 'reconcile'):
                phase()
        self.candidate_command.assert_not_called()
        self.publish.assert_not_called()
        self.request.assert_not_called()

    def test_wrong_historical_manifest_is_rejected_before_frontend_tools_run(self):
        self.plan.update(rollback=True, release='release-target')
        self.save_plan()
        phases.write('target-release.json', snapshot('release-other'))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            phases.prepare_frontend()
        self.restore_candidate.assert_not_called()

    def test_apply_preserves_untouched_service_and_frontend_sources(self):
        self.plan['components'] = ['api']
        self.save_plan()
        phases.apply_backend()
        self.archive.assert_called_once_with('release-new', ['api'])
        self.publish.assert_called_once_with('release-new', 'c' * 40, base=self.base,
                                             services=['api'], frontend=self.base['frontend'])
        self.assertEqual(phases.read('backend-applied.json')['frontend'], self.base['frontend'])

    def test_backend_timeout_never_publishes_competing_rollback_or_ack(self):
        self.request.side_effect = TimeoutError('uncertain acknowledgement')
        with self.assertRaises(TimeoutError):
            phases.apply_backend()
        self.assertEqual(self.request.call_count, 1)
        self.assertFalse(Path('backend-applied.json').exists())
        self.complete.assert_not_called()
        self.restore.assert_not_called()

    def test_mismatched_candidate_or_ack_never_promotes(self):
        for changed in ({'id': 'dpl_other'}, {'request': 'run-other-1'}, {'release': 'release-other'}):
            self.ack()
            data = phases.read('backend-applied.json')
            if 'id' in changed:
                data['frontend'] = dict(data['frontend'], **changed)
            else:
                data.update(changed)
            phases.write('backend-applied.json', data)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                phases.promote_frontend()
        self.promote.assert_not_called()
        self.smoke.assert_not_called()

    def test_success_promotes_checks_then_completes_only_selected_release(self):
        self.ack()
        phases.promote_frontend()
        self.promote.assert_called_once_with()
        self.smoke.assert_called_once_with(check_notice_journey=True)
        self.assertTrue(phases.read('frontend-outcome.json')['ok'])
        phases.finalize_release()
        self.complete.assert_called_once_with('release-new', self.candidate)
        self.request.assert_not_called()

    def test_api_only_success_never_calls_frontend_promotion(self):
        self.plan['components'] = ['api']
        self.save_plan()
        self.ack(self.base['frontend'])
        phases.promote_frontend()
        self.promote.assert_not_called()
        self.smoke.assert_called_once_with(check_notice_journey=True)
        phases.finalize_release()
        self.complete.assert_called_once_with('release-new', self.base['frontend'])

    def test_frontend_only_release_keeps_basic_smoke_checks(self):
        self.plan['components'] = ['frontend']
        self.save_plan()
        self.ack()
        phases.promote_frontend()
        self.smoke.assert_called_once_with(check_notice_journey=False)

    def test_known_frontend_failure_and_recovery_restores_both_then_base_pointer(self):
        self.ack()
        self.promote.side_effect = RuntimeError('known promotion failure')
        with self.assertRaisesRegex(RuntimeError, 'known promotion'):
            phases.promote_frontend()
        self.assertEqual(phases.read('frontend-outcome.json'),
                         {'release': 'release-new', 'ok': False, 'frontend_restored': True})
        with self.assertRaisesRegex(RuntimeError, 'previous frontend and backend restored'):
            phases.finalize_release()
        self.request.assert_called_once_with('release-old', 'rollback', 'run-123-1-recovery', expected_base='release-new')
        self.complete.assert_called_once_with('release-old', self.base['frontend'])

    def test_smoke_failure_after_promotion_restores_known_previous_frontend_before_backend_recovery(self):
        self.ack()
        self.smoke.side_effect = TimeoutError('public smoke timed out')
        with self.assertRaises(TimeoutError):
            phases.promote_frontend()
        self.promote.assert_called_once_with()
        self.restore.assert_called_once_with()
        self.assertTrue(phases.read('frontend-outcome.json')['frontend_restored'])
        with self.assertRaisesRegex(RuntimeError, 'previous frontend and backend restored'):
            phases.finalize_release()
        self.request.assert_called_once_with('release-old', 'rollback', 'run-123-1-recovery', expected_base='release-new')

    def test_uncertain_frontend_recovery_leaves_release_mismatch_to_block_next_plan(self):
        self.ack()
        self.promote.side_effect = RuntimeError('promotion failed')
        self.restore.side_effect = TimeoutError('restore uncertain')
        with self.assertRaises(TimeoutError):
            phases.promote_frontend()
        self.assertFalse(phases.read('frontend-outcome.json')['frontend_restored'])
        with self.assertRaisesRegex(RuntimeError, 'backend remains applied; reconcile'):
            phases.finalize_release()
        self.request.assert_not_called()
        self.complete.assert_not_called()

    def test_backend_recovery_timeout_does_not_mark_a_completed_release(self):
        self.ack()
        self.outcome()
        self.request.side_effect = TimeoutError('recovery uncertain')
        with self.assertRaises(TimeoutError):
            phases.finalize_release()
        self.assertEqual(self.request.call_count, 1)
        self.complete.assert_not_called()

    def test_completion_write_timeout_does_not_issue_a_competing_recovery(self):
        self.ack()
        self.outcome(ok=True, restored=False)
        self.complete.side_effect = TimeoutError('completion pointer write uncertain')
        with self.assertRaises(TimeoutError):
            phases.finalize_release()
        self.complete.assert_called_once_with('release-new', self.candidate)
        self.request.assert_not_called()

    def test_invalid_outcome_is_data_error_not_a_rollback_instruction(self):
        self.ack()
        for changed in ({'ok': 'false'}, {'ok': None}, {'frontend_restored': 1}, {'release': 'release-other'}, {'extra': True}):
            self.outcome()
            outcome = phases.read('frontend-outcome.json')
            outcome.update(changed)
            phases.write('frontend-outcome.json', outcome)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                phases.finalize_release()
        self.request.assert_not_called()
        self.complete.assert_not_called()


if __name__ == '__main__':
    unittest.main()
