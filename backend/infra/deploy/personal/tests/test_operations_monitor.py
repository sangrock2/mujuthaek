import contextlib
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import operations_monitor as monitor
from setup_operations import policy

FIXTURE = {'account': '111111111111', 'bucket': 'example-private-bucket', 'budget': 'example-budget',
           'recipient': 'owner@example.com', 'sender': 'sender@example.com', 'vercel_team': 'example-team',
           'vercel_project': 'example-project', 'iam_users': ['example-mail', 'example-storage'],
           'credit_levels': [100, 40, 10], 'budget_limit': 60, 'credit_expiry': '2040-01-01'}


class OperationsTests(unittest.TestCase):
    def test_verification_never_sends_mail_or_writes_state(self):
        with patch.dict('os.environ', {'OPERATIONS_CONFIG': json.dumps(FIXTURE), 'VERCEL_TOKEN': 'synthetic'}), \
                patch.object(sys, 'argv', ['monitor', '--verify-only']), \
                patch.object(monitor, 'aws', return_value={'Account': FIXTURE['account']}) as aws, \
                patch.object(monitor, 'vercel_status', return_value={'project_access': True}) as vercel, \
                patch.object(monitor, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.main(), 0)
            aws.assert_called_once_with('sts', 'get-caller-identity')
            vercel.assert_called_once_with('synthetic')
            run.assert_not_called()

    def setUp(self):
        self.now = datetime(2026, 11, 15, tzinfo=timezone.utc)
        monitor.configure(FIXTURE)

    def test_credit_threshold_and_recovery(self):
        for balance, key in [(100, 'credits:100'), (40, 'credits:40'), (10, 'credits:10'), (0, 'credits:10')]:
            alerts = monitor.evaluate({'credits_usd': balance}, self.now)
            self.assertEqual(list(alerts), [key])
            self.assertFalse(monitor.fresh_alerts(alerts, {'active': [key]}))
        recovered = monitor.evaluate({'credits_usd': 120}, self.now)
        self.assertFalse(recovered)
        self.assertTrue(monitor.fresh_alerts(monitor.evaluate({'credits_usd': 99}, self.now), {'active': list(recovered)}))

    def test_expiry_milliseconds_and_relevant_scope(self):
        expires = self.now + timedelta(days=6)
        payload = {'token': {'expiresAt': (self.now + timedelta(days=100)).timestamp() * 1000,
                             'scopes': [{'type': 'team', 'teamId': monitor.TEAM, 'expiresAt': expires.timestamp() * 1000},
                                        {'type': 'team', 'teamId': 'other-team', 'expiresAt': 1}],
                             'id': 'sensitive-id', 'suffix': 'private', 'prefix': 'private'}}
        with patch.object(monitor, 'vercel_get', side_effect=[{'id': monitor.PROJECT}, payload]):
            status = monitor.vercel_status('secret-never-log')
        self.assertEqual(status['expires_at'], expires.isoformat())
        self.assertNotIn('private', json.dumps(status))
        alerts = monitor.evaluate({'vercel': status}, self.now)
        self.assertTrue(any(key.endswith(':7') for key in alerts))

    def test_missing_expiry_is_not_invented(self):
        with patch.object(monitor, 'vercel_get', side_effect=[{'id': monitor.PROJECT}, {'token': {}}]):
            self.assertEqual(monitor.vercel_status('test')['expiry_status'], 'no_expiry_reported')

    def test_missing_budget_recipient_is_detected(self):
        notifications = [{'NotificationType': kind, 'Threshold': threshold,
                          'ComparisonOperator': 'GREATER_THAN'}
                         for kind, threshold in [('ACTUAL', 50), ('ACTUAL', 80), ('ACTUAL', 100), ('FORECASTED', 100)]]
        def call(service, action, *args, **kwargs):
            if action == 'describe-notifications-for-budget': return {'Notifications': notifications}
            return {'Subscribers': [{'SubscriptionType': 'EMAIL', 'Address': 'wrong@example.com'}]}
        self.assertFalse(monitor.budget_subscriptions(call))

    def test_unauthorized_and_provider_errors_are_distinct_and_safe(self):
        import urllib.error
        for status, expected in [(401, 'authentication'), (403, 'authentication'), (503, 'provider')]:
            error = urllib.error.HTTPError('https://api.vercel.com', status, 'private-response', {}, None)
            with patch.object(monitor.urllib.request, 'urlopen', side_effect=error):
                with self.assertRaises(monitor.CheckError) as caught: monitor.vercel_get('/test', 'do-not-log')
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn('do-not-log', str(caught.exception))
            self.assertNotIn('private-response', str(caught.exception))

    def test_inactive_and_fresh_keys_do_not_require_rotation(self):
        keys = [{'user': 'owned', 'status': 'Inactive', 'created_at': (self.now - timedelta(days=200)).isoformat()},
                {'user': 'owned', 'status': 'Active', 'created_at': self.now.isoformat()}]
        self.assertFalse(monitor.evaluate({'iam_keys': keys}, self.now))
        keys[1]['created_at'] = (self.now - timedelta(days=90)).isoformat()
        self.assertTrue(any(key.startswith('key-age:') for key in monitor.evaluate({'iam_keys': keys}, self.now)))

    def test_provider_failures_do_not_stop_other_checks(self):
        def credits(report): report['credits_usd'] = 4
        with patch.object(monitor, 'collect_credits', side_effect=credits), \
             patch.object(monitor, 'collect_budget', side_effect=monitor.CheckError('private body')), \
             patch.object(monitor, 'collect_keys'), patch.object(monitor, 'vercel_status', return_value={}):
            report = monitor.collect(self.now)
        self.assertEqual(report['credits_usd'], 4)
        self.assertEqual(report['errors'], ['AWS budget check unavailable'])
        self.assertNotIn('private body', json.dumps(report))

    def test_failed_send_does_not_commit_deduplication(self):
        with patch.object(monitor, 'aws', return_value={'Account': monitor.ACCOUNT}), \
             patch.object(monitor, 'read_state', return_value={}), \
             patch.object(monitor, 'collect', return_value={'errors': []}), \
             patch.object(monitor, 'put_json') as put, \
             patch.object(monitor, 'send_report', side_effect=monitor.CheckError('send failed')):
            with self.assertRaises(monitor.CheckError): monitor.run()
        self.assertEqual([call.args[1] for call in put.call_args_list], ['latest.json'])

    def test_public_failure_does_not_leak_provider_payload(self):
        with patch.object(sys, 'argv', ['monitor']), patch.dict(monitor.os.environ, {'OPERATIONS_CONFIG': json.dumps(FIXTURE)}), \
             patch.object(monitor, 'run', side_effect=RuntimeError('secret balance token')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(monitor.main(), 1)
        self.assertNotIn('secret', output.getvalue())
        self.assertNotIn('balance', output.getvalue())

    def test_invalid_currency_or_nonfinite_balance_is_rejected(self):
        for amount in [{'amount': 5, 'unit': 'EUR'}, {'amount': 'NaN', 'unit': 'USD'}, {'amount': -1, 'unit': 'USD'}]:
            with self.assertRaises(monitor.CheckError): monitor.usd(amount)

    def test_role_has_no_credential_creation_or_app_deployment_permissions(self):
        statements = policy()['Statement']
        actions = {action for statement in statements for action in
                   ([statement['Action']] if isinstance(statement['Action'], str) else statement['Action'])}
        self.assertEqual(actions, {'freetier:GetAccountPlanState', 'budgets:ViewBudget', 'iam:ListAccessKeys',
                                   's3:GetObject', 's3:PutObject', 'ses:SendEmail'})
        s3 = next(statement for statement in statements if statement['Action'] == ['s3:GetObject', 's3:PutObject'])
        self.assertTrue(all('/operations/monitor/' in resource and '*' not in resource for resource in s3['Resource']))
        ses = statements[-1]
        self.assertEqual(ses['Condition']['ForAllValues:StringEquals']['ses:Recipients'], [monitor.RECIPIENT])


if __name__ == '__main__':
    unittest.main()
