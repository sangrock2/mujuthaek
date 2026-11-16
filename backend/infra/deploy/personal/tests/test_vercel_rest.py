import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / '.github/scripts'))
import vercel_rest as rest


class VercelRest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'VERCEL_TOKEN': 'synthetic-token'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.ready = {'id': 'dplSynthetic', 'url': 'synthetic.vercel.app', 'projectId': rest.PROJECT,
                      'ownerId': rest.TEAM, 'meta': {'githubCommitSha': 'a' * 40},
                      'target': 'production', 'readyState': 'READY', 'aliasAssigned': False}
        self.ready['id'] = 'dpl_Synthetic'
        self.project = {'targets': {'production': {'id': 'dpl_Previous'}}}

    def test_no_network_in_an_aws_job(self):
        with patch.dict(os.environ, {'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'synthetic'}), patch.object(rest.urllib.request, 'build_opener') as opened:
            with self.assertRaisesRegex(RuntimeError, 'separate job'):
                rest.api('/v13/deployments')
            opened.assert_not_called()

    def test_redirects_and_external_resource_paths_are_rejected(self):
        self.assertIsNone(rest.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://untrusted.test'))
        for path in ('https://untrusted.test', '//untrusted.test', '/v13/deployments/../users', '/v13/deployments?teamId=other'):
            with self.assertRaises(ValueError):
                rest.api(path)

    def test_api_pins_team_and_headers_and_bounds_response(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{}'
        with patch.object(rest.urllib.request, 'build_opener', return_value=opener):
            self.assertEqual(rest.api('/v13/deployments', {'synthetic': True}), {})
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.vercel.com/v13/deployments?teamId=' + rest.TEAM)
            self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-token')
            opener.open.return_value.__enter__.return_value.read.return_value = b'x' * (2 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(RuntimeError, 'limit'):
                rest.api('/v13/deployments')

    def test_provider_errors_never_expose_response_or_token(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError('https://api.vercel.com', 403, 'synthetic-token', {}, None)
        with patch.object(rest.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(RuntimeError) as error:
                rest.api('/v13/deployments')
        self.assertNotIn('synthetic-token', str(error.exception))

    def test_candidate_pins_source_and_does_not_assign_domains(self):
        with patch.object(rest, 'project', return_value=self.project), patch.object(rest, 'api', side_effect=[{'id': self.ready['id']}, self.ready]) as call:
            self.assertEqual(rest.candidate('a' * 40), self.ready)
            body = call.call_args_list[0].args[1]
            self.assertIs(body['autoAssignCustomDomains'], False)
            self.assertEqual(body['gitSource']['sha'], 'a' * 40)
            self.assertEqual(body['projectSettings']['rootDirectory'], 'frontend')

    def test_candidate_rejects_foreign_build(self):
        for change in ({'projectId': 'other'}, {'ownerId': 'other'},
                       {'meta': {'githubCommitSha': 'b' * 40}}):
            value = dict(self.ready, **change)
            with patch.object(rest, 'project', return_value=self.project), patch.object(rest, 'api', side_effect=[{'id': value['id']}, value]):
                with self.assertRaises(RuntimeError):
                    rest.candidate('a' * 40)

    def test_candidate_allows_unique_alias_but_rejects_production_target_change(self):
        value = dict(self.ready, aliasAssigned=True)
        with patch.object(rest, 'project', return_value=self.project), patch.object(rest, 'api', side_effect=[{'id': value['id']}, value]):
            self.assertEqual(rest.candidate('a' * 40), value)
        with patch.object(rest, 'project', side_effect=[self.project, {'targets': {'production': value}}]), patch.object(rest, 'api', side_effect=[{'id': value['id']}, value]):
            with self.assertRaisesRegex(RuntimeError, 'Production changed'):
                rest.candidate('a' * 40)

    def test_promote_refuses_preview_and_waits_for_production_identity(self):
        with patch.object(rest, 'api', return_value=dict(self.ready, target=None)) as call:
            with self.assertRaises(RuntimeError):
                rest.promote(self.ready['id'])
            self.assertEqual(call.call_count, 1)
        with patch.object(rest, 'api', side_effect=[self.ready, {}, {}]) as call, patch.object(rest, 'project', side_effect=[{}, {'targets': {'production': self.ready}}]):
            rest.promote(self.ready['id'])
            self.assertEqual(call.call_args_list[1].args[0], '/v10/projects/' + rest.PROJECT + '/promote/' + self.ready['id'])
            self.assertEqual(call.call_args_list[2].args[1], {'autoAssignCustomDomains': False})

    def test_project_binding_and_workflow_have_no_cli_dependencies(self):
        with patch.object(rest, 'api', return_value={'id': rest.PROJECT, 'rootDirectory': 'other'}):
            with self.assertRaises(RuntimeError):
                rest.project()
        workflow = (ROOT / '.github/workflows/production.yml').read_text(encoding='utf-8')
        self.assertNotIn('npm ', workflow)
        self.assertNotIn('actions/setup-node', workflow)
