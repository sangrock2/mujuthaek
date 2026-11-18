from pathlib import Path
import re
import unittest

from deployment_gate import STAGES, verify


class DeploymentExecutionGate(unittest.TestCase):
    def evidence(self, result='success'):
        return {name: {'result': 'success' if name in ('guard', 'plan') else result}
                for name in ('guard', 'plan', *STAGES)}

    def test_candidate_only_run_cannot_be_reported_as_deployed(self):
        # 2026-11-18: upstream optional checks were skipped, and implicit success()
        # skipped actual deployment despite a successful frontend candidate.
        value = self.evidence('skipped')
        value['frontend-prepare']['result'] = 'success'
        with self.assertRaises(ValueError):
            verify('true', value)

    def test_all_required_release_phases_succeed(self):
        verify('true', self.evidence())

    def test_any_failed_cancelled_or_skipped_phase_blocks_completion(self):
        for name in STAGES:
            for result in ('failure', 'cancelled', 'skipped'):
                with self.subTest(name=name, result=result):
                    value = self.evidence()
                    value[name]['result'] = result
                    with self.assertRaises(ValueError):
                        verify('true', value)

    def test_no_runtime_change_allows_skipped_release_phases(self):
        verify('false', self.evidence('skipped'))
        with self.assertRaises(ValueError):
            verify('false', self.evidence())

    def test_missing_guard_plan_phase_or_selection_fails_closed(self):
        for name in ('guard', 'plan', *STAGES):
            value = self.evidence()
            del value[name]
            with self.assertRaises(ValueError):
                verify('true', value)
        for value in (None, '', 'TRUE', True):
            with self.assertRaises(ValueError):
                verify(value, self.evidence())

    def test_apply_and_promote_override_skip_propagation_without_bypassing_success(self):
        workflow = (Path(__file__).resolve().parents[3] / '.github/workflows/production.yml').read_text(encoding='utf-8')
        for stage, prerequisite in (('backend-apply', 'frontend-prepare'), ('frontend-promote', 'backend-apply')):
            block = re.search(r'^  ' + stage + r':\n(.*?)(?=^  [a-z][a-z-]*:|\Z)', workflow, re.M | re.S).group(1)
            self.assertIn('always()', block)
            self.assertIn('!cancelled()', block)
            self.assertIn("needs." + prerequisite + ".result == 'success'", block)
            self.assertIn("needs.plan.outputs.deploy == 'true'", block)
        self.assertIn('backend/infra/ci/deployment_gate.py', workflow)


if __name__ == '__main__':
    unittest.main()
