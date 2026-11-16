import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migrate_workflow_oidc import canonical_trust
from setup_github_release import SUB_CLAIM_KEYS, trust_policy


class WorkflowOidc(unittest.TestCase):
    def test_standalone_workflows_use_workflow_ref(self):
        self.assertEqual(SUB_CLAIM_KEYS, ['repo', 'context', 'workflow_ref'])

    def test_aws_single_item_normalization_does_not_relax_the_subject(self):
        target = trust_policy('repo:example/repo', ('operations.yml',))
        observed = copy.deepcopy(target)
        key = 'token.actions.githubusercontent.com:sub'
        values = observed['Statement'][0]['Condition']['StringEquals']
        values[key] = values[key][0]
        self.assertEqual(canonical_trust(target), canonical_trust(observed))
        values[key] = values[key].replace('operations.yml', 'untrusted.yml')
        self.assertNotEqual(canonical_trust(target), canonical_trust(observed))
