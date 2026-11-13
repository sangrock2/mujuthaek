"""Separate host release credentials from application S3 credentials; never print keys."""
import json
import argparse
import os
from pathlib import Path
from aws_personal import AWS, RUNTIME

aws = AWS('mujuthaek', '659355919826')
aws.verify(require_credits=False)
path = RUNTIME / 'release-host.env'
user = 'mujuthaek-personal-release-host'
bucket = 'arn:aws:s3:::mujuthaek-personal-659355919826-raw'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--block-app-access', action='store_true', help='Run after the host-only credentials are installed and verified')
args = parser.parse_args()
if args.block_app_access:
    deny = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Action': 's3:*', 'Resource': bucket + '/deployments/*'}]}
    aws.call('iam', 'put-user-policy', '--user-name', 'mujuthaek-personal-runtime-20261113',
             '--policy-name', 'NoReleaseAccess', '--policy-document', json.dumps(deny))
    raise SystemExit('Application credentials cannot access deployment objects')
if path.exists():
    raise SystemExit('Host credentials already exist; do not create another key')
users = aws.call('iam', 'list-users')['Users']
if any(u['UserName'] == user for u in users):
    raise RuntimeError('Inspect existing host user before creating credentials')
aws.call('iam', 'create-user', '--user-name', user, '--tags', 'Key=Project,Value=mujuthaek-personal')
policy = {'Version': '2012-10-17', 'Statement': [
    {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': bucket + '/deployments/*'},
    {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': [bucket + '/deployments/states/*', bucket + '/deployments/results/*']},
    {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': bucket,
     'Condition': {'StringLike': {'s3:prefix': ['deployments/*']}}},
]}
aws.call('iam', 'put-user-policy', '--user-name', user, '--policy-name', 'HostReleaseResultsOnly', '--policy-document', json.dumps(policy))
key = aws.call('iam', 'create-access-key', '--user-name', user)['AccessKey']
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(f"AWS_ACCESS_KEY_ID={key['AccessKeyId']}\nAWS_SECRET_ACCESS_KEY={key['SecretAccessKey']}\nAWS_REGION=ap-northeast-2\n")
print('Created root-host-only S3 release credentials in ignored runtime; values not printed')
