"""Prepare a backup-only identity, then restrict app storage only after verified host cutover."""
import argparse
import csv
import hashlib
import json
import os
import subprocess
from pathlib import Path

from aws_personal import AWS, RUNTIME

BACKUP_USER = 'mujuthaek-personal-backup'
PRIVATE = RUNTIME / '.env.backup-isolated'


def backup_policy(bucket):
    arn = f'arn:aws:s3:::{bucket}'
    return {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 's3:GetBucketLocation', 'Resource': arn},
        {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': arn,
         'Condition': {'StringLike': {'s3:prefix': ['backups', 'backups/*']}}},
        {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': arn + '/backups/*'},
        {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': arn + '/backups/*',
         'Condition': {'StringEquals': {'s3:if-none-match': '*'}}},
    ]}


def app_policy(bucket):
    arn = f'arn:aws:s3:::{bucket}'
    return {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 's3:GetBucketLocation', 'Resource': arn},
        {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': arn,
         'Condition': {'StringLike': {'s3:prefix': ['raw', 'raw/*']}}},
        {'Effect': 'Allow', 'Action': ['s3:GetObject', 's3:PutObject', 's3:DeleteObject', 's3:AbortMultipartUpload'],
         'Resource': arn + '/raw/*'},
        {'Effect': 'Deny', 'Action': 's3:*', 'Resource': arn + '/backups/*'},
    ]}


def private_file(path):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    if os.name == 'nt':
        response = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, check=True)
        sid = next(csv.reader(response.stdout.strip().splitlines()))[1]
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(F)'],
                       check=True, capture_output=True)


def values(path):
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() if '=' in line)


def owned(tags):
    if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in tags:
        raise RuntimeError('Resource ownership mismatch; no credentials or policies changed')


def prepare(aws, config):
    users = aws.call('iam', 'list-users')['Users']
    if not any(user['UserName'] == BACKUP_USER for user in users):
        aws.call('iam', 'create-user', '--user-name', BACKUP_USER, '--tags', 'Key=Project,Value=mujuthaek-personal')
    user = aws.call('iam', 'get-user', '--user-name', BACKUP_USER)['User']
    owned(user.get('Tags', []))
    if aws.call('iam', 'list-attached-user-policies', '--user-name', BACKUP_USER)['AttachedPolicies']:
        raise RuntimeError('Unexpected managed permissions on backup identity')
    if aws.call('iam', 'list-groups-for-user', '--user-name', BACKUP_USER)['Groups']:
        raise RuntimeError('Unexpected group membership on backup identity')
    policies = aws.call('iam', 'list-user-policies', '--user-name', BACKUP_USER)['PolicyNames']
    if set(policies) - {'BackupPrefixOnly'}:
        raise RuntimeError('Unexpected inline permissions on backup identity')
    expected = backup_policy(config['bucket'])
    if policies and aws.call('iam', 'get-user-policy', '--user-name', BACKUP_USER, '--policy-name', 'BackupPrefixOnly')['PolicyDocument'] != expected:
        raise RuntimeError('Existing backup policy differs; inspect before replacing')
    keys = aws.call('iam', 'list-access-keys', '--user-name', BACKUP_USER)['AccessKeyMetadata']
    if keys:
        saved = values(PRIVATE) if PRIVATE.exists() else {}
        if len(keys) != 1 or keys[0]['Status'] != 'Active' or saved.get('AWS_ACCESS_KEY_ID') != keys[0]['AccessKeyId']:
            raise RuntimeError('Existing backup key does not match the owner-only local file; no new key created')
    aws.call('iam', 'put-user-policy', '--user-name', BACKUP_USER, '--policy-name', 'BackupPrefixOnly',
             '--policy-document', json.dumps(expected))
    if not keys:
        if PRIVATE.exists() and PRIVATE.stat().st_size:
            raise RuntimeError('Refusing to overwrite an existing private configuration')
        if not PRIVATE.exists():
            private_file(PRIVATE)
        key = aws.call('iam', 'create-access-key', '--user-name', BACKUP_USER)['AccessKey']
        try:
            data = {'AWS_ACCESS_KEY_ID': key['AccessKeyId'], 'AWS_SECRET_ACCESS_KEY': key['SecretAccessKey'],
                    'AWS_REGION': 'ap-northeast-2', 'S3_BUCKET': config['bucket'], 'BACKUP_IDENTITY_ARN': user['Arn']}
            PRIVATE.write_text(''.join(f'{name}={value}\n' for name, value in data.items()), encoding='utf-8')
        except Exception:
            # This newly created key has never been installed on the server.
            aws.call('iam', 'delete-access-key', '--user-name', BACKUP_USER, '--access-key-id', key['AccessKeyId'])
            raise
    print('Backup-only identity prepared; app permissions unchanged; values not printed.')


def finalize(aws, config, receipt):
    saved = values(PRIVATE)
    required = {'ok': True, 'get_put_verified': True, 'overwrite_blocked': True,
                'bucket_fingerprint': hashlib.sha256(config['bucket'].encode()).hexdigest(),
                'identity_fingerprint': hashlib.sha256(saved['BACKUP_IDENTITY_ARN'].encode()).hexdigest(),
                'key_fingerprint': hashlib.sha256(saved['AWS_ACCESS_KEY_ID'].encode()).hexdigest()}
    if any(receipt.get(name) != value for name, value in required.items()):
        raise RuntimeError('Verified host cutover receipt required; app permissions unchanged')
    users = [user for user in config['iam_users'] if user.startswith('mujuthaek-personal-runtime-')]
    if len(users) != 1:
        raise RuntimeError('Expected exactly one app runtime identity')
    owned(aws.call('iam', 'get-user', '--user-name', users[0])['User'].get('Tags', []))
    if aws.call('iam', 'list-attached-user-policies', '--user-name', users[0])['AttachedPolicies']:
        raise RuntimeError('Unexpected managed permissions on app identity')
    if aws.call('iam', 'list-groups-for-user', '--user-name', users[0])['Groups']:
        raise RuntimeError('Unexpected group membership on app identity')
    old = aws.call('iam', 'get-user-policy', '--user-name', users[0], '--policy-name', 'PersonalBucketOnly')['PolicyDocument']
    snapshot = RUNTIME / 'app-storage-policy-before-backup-separation.json'
    if not snapshot.exists():
        private_file(snapshot)
        snapshot.write_text(json.dumps(old), encoding='utf-8')
    aws.call('iam', 'put-user-policy', '--user-name', users[0], '--policy-name', 'PersonalBucketOnly',
             '--policy-document', json.dumps(app_policy(config['bucket'])))
    print('App storage restricted to raw files; backup objects explicitly denied; existing app key retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'finalize'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    aws = AWS('mujuthaek', config['account'])
    aws.verify(require_credits=False)
    owned(aws.call('s3api', 'get-bucket-tagging', '--bucket', config['bucket'])['TagSet'])
    if args.stage == 'prepare':
        prepare(aws, config)
    else:
        if args.receipt is None:
            raise RuntimeError('Host receipt required')
        finalize(aws, config, json.loads(args.receipt.read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
