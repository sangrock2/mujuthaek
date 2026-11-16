"""Escrow the newly generated recovery key off-host, accessible only to the verified account root."""
import hashlib
import json

from aws_personal import AWS, RUNTIME
from private_files import write_private_file

BUCKET = 'mujuthaek-personal-659355919826-raw'
PREFIX = 'recovery-keys/backup-20261116/'


def main():
    aws = AWS('mujuthaek', '659355919826')
    root_arn = 'arn:aws:iam::659355919826:root'
    identity = aws.call('sts', 'get-caller-identity')
    if identity['Account'] != aws.account or identity['Arn'] != root_arn:
        raise RuntimeError('The verified account owner must prepare recovery escrow')
    directory = RUNTIME / 'backup-crypto-20261116'
    for name in ('recovery-private.pem', 'recovery-public.pem'):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Expected the newly generated task recovery files')
    policy = json.loads(aws.call('s3api', 'get-bucket-policy', '--bucket', BUCKET,
                                '--expected-bucket-owner', aws.account)['Policy'])
    saved = RUNTIME / 'bucket-policy-before-recovery-escrow.json'
    if not saved.exists():
        write_private_file(saved, json.dumps(policy, indent=2))
    statement = {'Sid': 'OwnerOnlyBackupRecoveryKeys', 'Effect': 'Deny', 'Principal': '*',
                 'Action': 's3:*', 'Resource': 'arn:aws:s3:::' + BUCKET + '/recovery-keys/*',
                 'Condition': {'ArnNotEquals': {'aws:PrincipalArn': root_arn}}}
    existing = [item for item in policy['Statement'] if item.get('Sid') == statement['Sid']]
    if existing and existing != [statement]:
        raise RuntimeError('Existing recovery boundary differs; no replacement allowed')
    if not existing:
        policy['Statement'].append(statement)
        aws.call('s3api', 'put-bucket-policy', '--bucket', BUCKET, '--expected-bucket-owner', aws.account,
                 '--policy', json.dumps(policy))
    observed = json.loads(aws.call('s3api', 'get-bucket-policy', '--bucket', BUCKET,
                                   '--expected-bucket-owner', aws.account)['Policy'])
    if statement not in observed['Statement']:
        raise RuntimeError('Recovery boundary verification failed; no keys uploaded')
    user_arn = 'arn:aws:iam::659355919826:user/mujuthaek-personal-backup'
    simulation = aws.call('iam', 'simulate-principal-policy', '--policy-source-arn', user_arn,
        '--action-names', 's3:GetObject', '--resource-arns', 'arn:aws:s3:::' + BUCKET + '/' + PREFIX + 'recovery-private.pem',
        '--resource-policy', json.dumps(observed), '--caller-arn', user_arn, '--resource-owner', aws.account,
        '--context-entries', 'ContextKeyName=aws:PrincipalArn,ContextKeyType=string,ContextKeyValues=' + user_arn)
    if simulation['EvaluationResults'][0]['EvalDecision'] != 'explicitDeny':
        raise RuntimeError('Backup identity not explicitly denied; no keys uploaded')
    for name in ('recovery-private.pem', 'recovery-public.pem'):
        path = directory / name
        key = PREFIX + name
        # These task-specific keys are create-only. A repeated invocation must not replace escrow.
        aws.call('s3api', 'put-object', '--bucket', BUCKET, '--expected-bucket-owner', aws.account,
                 '--key', key, '--body', str(path), '--if-none-match', '*', '--server-side-encryption', 'AES256')
        downloaded = directory / ('escrow-verified-' + name)
        aws.call('s3api', 'get-object', '--bucket', BUCKET, '--expected-bucket-owner', aws.account,
                 '--key', key, str(downloaded))
        if hashlib.sha256(downloaded.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
            raise RuntimeError('Escrow roundtrip mismatch; do not enable backup encryption')
        downloaded.unlink()
    print(json.dumps({'recovery_escrow': 'verified', 'owner_only_resource_policy': True,
                      'backup_identity_explicitly_denied': True, 'private_key_on_server': False,
                      'existing_backup_objects_changed': False}))


if __name__ == '__main__':
    main()
