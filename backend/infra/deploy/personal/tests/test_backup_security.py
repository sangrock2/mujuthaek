import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup_security as backup
from backup_upload import upload_command


class BackupSecurityTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
