import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import backup_security as backup
import setup_resources as setup
import storage_security as storage
from backup_upload import upload_command

ACCOUNT = '123456789012'
BUCKET = f'mujuthaek-personal-{ACCOUNT}-raw'
OWNED = [{'Key': 'Project', 'Value': 'mujuthaek-personal'}]
RUNTIME_USER = 'mujuthaek-personal-runtime-20261113'


class FakeAWS:
    """Answers only the calls a path makes and records every inline IAM policy it writes."""

    def __init__(self, responses):
        self.responses, self.policies, self.actions = responses, {}, []

    def verify(self, require_credits=True):
        return {}

    def call(self, service, action, *args, region=None):
        self.actions.append(action)
        if action == 'put-user-policy':
            options = dict(zip(args[::2], args[1::2]))
            self.policies[options['--policy-name']] = json.loads(options['--policy-document'])
            return {}
        response = self.responses.get(action, {})
        if isinstance(response, Exception):
            raise response
        return response


def fresh_install(runtime):
    aws = FakeAWS({
        'get-instance': {'instance': {'tags': [{'key': 'Project', 'value': 'mujuthaek-personal'}]}},
        'get-static-ips': {'staticIps': [{'name': setup.STATIC_IP_NAME, 'ipAddress': '192.0.2.10', 'attachedTo': setup.INSTANCE}]},
        'list-buckets': {'Buckets': [{'Name': BUCKET}]},
        'get-bucket-tagging': {'TagSet': OWNED},
        'get-bucket-policy': RuntimeError('An error occurred (NoSuchBucketPolicy)'),
        'create-access-key': {'AccessKey': {'AccessKeyId': 'AKIAEXAMPLEEXAMPLE00', 'SecretAccessKey': 'example-only'}},
    })
    argv = ['setup_resources.py', '--profile', 'personal-example', '--account', ACCOUNT]
    with patch.object(setup, 'AWS', return_value=aws), patch.object(setup, 'RUNTIME', runtime), \
            patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
        setup.main()
    return aws


def live_hardening(runtime):
    """The live host's path: backup separation finalize, then the storage boundary installer."""
    arn, key = f'arn:aws:iam::{ACCOUNT}:user/mujuthaek-personal-backup', 'AKIABACKUPEXAMPLE000'
    private = runtime / '.env.backup-isolated'
    private.write_text(f'AWS_ACCESS_KEY_ID={key}\nBACKUP_IDENTITY_ARN={arn}\n')
    # An existing snapshot skips the owner-only file helper (icacls on Windows).
    (runtime / 'app-storage-policy-before-backup-separation.json').write_text('{}')
    receipt = {'ok': True, 'get_put_verified': True, 'overwrite_blocked': True,
               'bucket_fingerprint': hashlib.sha256(BUCKET.encode()).hexdigest(),
               'identity_fingerprint': hashlib.sha256(arn.encode()).hexdigest(),
               'key_fingerprint': hashlib.sha256(key.encode()).hexdigest()}
    config = {'account': ACCOUNT, 'bucket': BUCKET, 'iam_users': [RUNTIME_USER]}
    finalize = FakeAWS({
        'get-user': {'User': {'Tags': OWNED}},
        'list-attached-user-policies': {'AttachedPolicies': []},
        'list-groups-for-user': {'Groups': []},
        'get-user-policy': {'PolicyDocument': {'Version': '2012-10-17', 'Statement': []}},
    })
    with patch.object(backup, 'PRIVATE', private), patch.object(backup, 'RUNTIME', runtime), \
            contextlib.redirect_stdout(io.StringIO()):
        backup.finalize(finalize, config, receipt)
    boundary = FakeAWS({
        'get-bucket-tagging': {'TagSet': OWNED},
        'get-user': {'User': {'Tags': OWNED}},
        'get-bucket-policy': RuntimeError('An error occurred (NoSuchBucketPolicy)'),
        'get-user-policy': RuntimeError('An error occurred (NoSuchEntity)'),
    })
    (runtime / 'config.json').write_text(json.dumps(config))
    with patch.object(storage, 'AWS', return_value=boundary), \
            patch.object(sys, 'argv', ['storage_security.py', '--config', str(runtime / 'config.json')]), \
            contextlib.redirect_stdout(io.StringIO()):
        storage.main()
    return {**finalize.policies, **boundary.policies}


class BackupSecurityTests(unittest.TestCase):
    def prepared_issuer(self, issue=None):
        calls = []
        def call(service, action, *args):
            calls.append(action)
            if action == 'create-access-key' and issue:
                issue()
            return {
                'list-users': {'Users': [{'UserName': backup.BACKUP_USER}]},
                'get-user': {'User': {'Arn': 'synthetic-user', 'Tags': OWNED}},
                'list-attached-user-policies': {'AttachedPolicies': []},
                'list-groups-for-user': {'Groups': []},
                'list-user-policies': {'PolicyNames': []},
                'list-access-keys': {'AccessKeyMetadata': []},
                'create-access-key': {'AccessKey': {'AccessKeyId': 'synthetic-key', 'SecretAccessKey': 'synthetic-secret'}},
            }.get(action, {})
        return SimpleNamespace(call=call), calls

    def test_preexisting_empty_file_cannot_receive_new_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.env'
            path.write_bytes(b'')
            aws, calls = self.prepared_issuer()
            with patch.object(backup, 'PRIVATE', path), self.assertRaises(RuntimeError):
                backup.prepare(aws, {'bucket': 'example-bucket'})
            self.assertNotIn('create-access-key', calls)
            self.assertEqual(path.read_bytes(), b'')

    def test_secret_is_written_through_the_original_creation_handle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.env'
            aws, calls = self.prepared_issuer()
            def create(target):
                return os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with patch.object(backup, 'PRIVATE', path), patch.object(backup, 'create_private_file', side_effect=create), \
                    patch.object(Path, 'write_text', side_effect=AssertionError('Must not reopen a secret pathname')):
                backup.prepare(aws, {'bucket': 'example-bucket'})
            self.assertIn('synthetic-secret', path.read_text())
            self.assertNotIn('delete-access-key', calls)

    @unittest.skipIf(os.name == 'nt', 'POSIX rename of an open inode')
    def test_replaced_path_revokes_new_key_without_leaking_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.env'
            original = Path(folder) / 'original.env'
            def swap():
                path.rename(original)
                path.write_bytes(b'')
            aws, calls = self.prepared_issuer(swap)
            with patch.object(backup, 'PRIVATE', path), self.assertRaises(RuntimeError):
                backup.prepare(aws, {'bucket': 'example-bucket'})
            self.assertIn('delete-access-key', calls)
            self.assertEqual(path.read_bytes(), b'')
            self.assertEqual(original.read_bytes(), b'')

    def test_backup_identity_cannot_delete_or_access_raw_release_or_operations_objects(self):
        policy = backup.backup_policy('example-bucket')
        objects = [statement for statement in policy['Statement'] if statement['Action'] in ('s3:GetObject', 's3:PutObject')]
        self.assertTrue(all(statement['Resource'] == 'arn:aws:s3:::example-bucket/backups/*' for statement in objects))
        put = next(statement for statement in objects if statement['Action'] == 's3:PutObject')
        self.assertEqual(put['Condition']['StringEquals']['s3:if-none-match'], '*')
        self.assertNotIn('s3:DeleteObject', json.dumps(policy))
        listing = next(statement for statement in policy['Statement'] if statement['Action'] == 's3:ListBucket')
        self.assertEqual(listing['Condition']['StringLike']['s3:prefix'], ['backups', 'backups/*'])

    def test_app_identity_has_only_raw_object_allows_and_explicitly_denies_backups(self):
        policy = backup.app_policy('example-bucket')
        allow = next(statement for statement in policy['Statement'] if isinstance(statement['Action'], list))
        self.assertEqual(allow['Resource'], 'arn:aws:s3:::example-bucket/raw/*')
        self.assertEqual(policy['Statement'][-1], {'Effect': 'Deny', 'Action': 's3:*',
                                                 'Resource': 'arn:aws:s3:::example-bucket/backups/*'})

    def test_invalid_host_receipt_prevents_any_app_permission_change(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / 'example.env'
            private.write_text('AWS_ACCESS_KEY_ID=example\nBACKUP_IDENTITY_ARN=example-user\n')
            calls = []
            aws = SimpleNamespace(call=lambda *args: calls.append(args))
            with patch.object(backup, 'PRIVATE', private):
                with self.assertRaises(RuntimeError): backup.finalize(aws, {'bucket': 'example-bucket'}, {'ok': True})
            self.assertFalse(calls)

    def test_upload_never_recreates_backup_credentials_from_the_app_key(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'runtime/backups').mkdir(parents=True)
            source = base / 'runtime/backups/example.dump'
            source.write_bytes(b'example backup')
            (base / '.env').write_text('S3_BUCKET=example-bucket\nAWS_ACCESS_KEY_ID=app-example\n')
            with self.assertRaises(FileNotFoundError): upload_command(base, source)
            credentials = base / 'runtime/backup-aws.env'
            credentials.write_text('AWS_ACCESS_KEY_ID=backup-example\nBACKUP_IDENTITY_ARN=example:user/mujuthaek-personal-backup\n')
            before = credentials.read_bytes()
            command = upload_command(base, source)
            self.assertEqual(credentials.read_bytes(), before)
            self.assertEqual(command[-2:], ['--if-none-match', '*'])
            self.assertNotIn('app-example', command)
            outside = base / 'outside.dump'
            outside.write_bytes(b'outside')
            with self.assertRaises(ValueError): upload_command(base, outside)

    def test_an_untracked_existing_key_gets_no_new_backup_permissions(self):
        calls = []
        def call(service, action, *args):
            calls.append(action)
            return {
                'list-users': {'Users': [{'UserName': backup.BACKUP_USER}]},
                'get-user': {'User': {'Arn': 'example-user', 'Tags': [{'Key': 'Project', 'Value': 'mujuthaek-personal'}]}},
                'list-attached-user-policies': {'AttachedPolicies': []},
                'list-groups-for-user': {'Groups': []},
                'list-user-policies': {'PolicyNames': []},
                'list-access-keys': {'AccessKeyMetadata': [{'AccessKeyId': 'untracked', 'Status': 'Active'}]},
            }[action]
        with tempfile.TemporaryDirectory() as directory, patch.object(backup, 'PRIVATE', Path(directory) / 'missing.env'):
            with self.assertRaises(RuntimeError): backup.prepare(SimpleNamespace(call=call), {'bucket': 'example-bucket'})
        self.assertNotIn('put-user-policy', calls)
        self.assertNotIn('create-access-key', calls)


class FreshInstallTests(unittest.TestCase):
    def test_fresh_install_starts_with_the_permissions_a_finalized_live_host_has(self):
        # Security audit L-19: a new install or disaster recovery must not give the app key backup access until a
        # separate manual finalize step runs.
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            fresh = fresh_install(Path(first))
            live = live_hardening(Path(second))
        self.assertEqual(fresh.policies, live)
        self.assertEqual(set(fresh.policies), {backup.APP_POLICY, storage.BOUNDARY_POLICY})
        app = json.dumps(fresh.policies[backup.APP_POLICY])
        self.assertNotIn(f'"arn:aws:s3:::{BUCKET}/*"', app)
        self.assertIn(f'arn:aws:s3:::{BUCKET}/backups/*', app)
        # The access key is created only once its final permissions are in place.
        last_policy = max(index for index, action in enumerate(fresh.actions) if action == 'put-user-policy')
        self.assertGreater(fresh.actions.index('create-access-key'), last_policy)

    def test_fresh_install_generates_every_required_and_new_runtime_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            fresh_install(Path(directory))
            lines = (Path(directory) / '.env').read_text(encoding='ascii').splitlines()
            versions = (Path(directory) / 'versions.env').read_text(encoding='ascii')
        values = dict(line.split('=', 1) for line in lines)
        # Security audit L-1/L-15: a private IP-hash salt and a dedicated unsubscribe-link key.
        for name in ('TRAFFIC_IP_SALT', 'EMAIL_UNSUBSCRIBE_KEY'):
            self.assertRegex(values[name], r'^[0-9a-f]{64}$')
        self.assertEqual(len({values[name] for name in setup.SECRETS}), len(setup.SECRETS))
        required = set(re.findall(r'\$\{(\w+):\?', (BASE / 'compose.prod.yml').read_text(encoding='ascii')))
        self.assertEqual(required - set(values), {'RELEASE'})
        self.assertRegex(versions, r'(?m)^RELEASE=\S+$')


if __name__ == '__main__':
    unittest.main()
