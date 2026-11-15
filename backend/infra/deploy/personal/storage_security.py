"""Storage boundaries without new credentials or changes to object retention."""
import argparse
import copy
import json
from pathlib import Path

from aws_personal import AWS


def tls_policy(bucket, existing=None):
    policy = copy.deepcopy(existing or {'Version': '2012-10-17', 'Statement': []})
    statement = {'Sid': 'DenyNonServicePlaintext', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
                 'Resource': [f'arn:aws:s3:::{bucket}', f'arn:aws:s3:::{bucket}/*'],
                 'Condition': {'Bool': {'aws:SecureTransport': 'false', 'aws:PrincipalIsAWSService': 'false'}}}
    old = next((value for value in policy['Statement'] if value.get('Sid') == statement['Sid']), None)
    if old and old != statement:
        raise ValueError('Existing transport policy differs; inspect before changing')
    if not old:
        policy['Statement'].append(statement)
    return policy


def runtime_boundary(bucket):
    # Apps can still use raw files and the existing backup identity remains valid.
    # Their shared runtime key must never modify the host's release instructions or cost reports.
    return {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Action': 's3:*',
            'Resource': [f'arn:aws:s3:::{bucket}/deployments/*', f'arn:aws:s3:::{bucket}/operations/*']}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    aws = AWS('mujuthaek', config['account'])
    aws.verify(require_credits=False)
    bucket = config['bucket']
    users = [name for name in config['iam_users'] if name.startswith('mujuthaek-personal-runtime-')]
    if len(users) != 1:
        raise RuntimeError('Expected one explicitly configured app runtime user')
    user = users[0]
    for tags in [aws.call('s3api', 'get-bucket-tagging', '--bucket', bucket)['TagSet'],
                 aws.call('iam', 'get-user', '--user-name', user)['User'].get('Tags', [])]:
        if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in tags:
            raise RuntimeError('Resource ownership mismatch; no changes made')
    try:
        existing = json.loads(aws.call('s3api', 'get-bucket-policy', '--bucket', bucket)['Policy'])
    except RuntimeError as error:
        if 'NoSuchBucketPolicy' not in str(error):
            raise
        existing = None
    policy_name = 'AppCannotAccessReleaseOrOperations'
    try:
        old_identity = aws.call('iam', 'get-user-policy', '--user-name', user, '--policy-name', policy_name)['PolicyDocument']
    except RuntimeError as error:
        if 'NoSuchEntity' not in str(error):
            raise
        old_identity = None
    identity = runtime_boundary(bucket)
    if old_identity is not None and old_identity != identity:
        raise RuntimeError('Existing runtime boundary differs; inspect before changing')
    # All validation happens before either mutation. Existing policy statements are preserved.
    transport = tls_policy(bucket, existing)
    aws.call('s3api', 'put-bucket-policy', '--bucket', bucket, '--policy', json.dumps(transport))
    aws.call('iam', 'put-user-policy', '--user-name', user, '--policy-name', policy_name,
             '--policy-document', json.dumps(identity))
    print('HTTPS-only bucket policy and app/deployment storage boundary applied; existing data and keys retained.')


if __name__ == '__main__':
    main()
