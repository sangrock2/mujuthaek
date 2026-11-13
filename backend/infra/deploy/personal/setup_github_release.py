"""Configure GitHub main-branch OIDC with access only to this project's release prefix."""
import json
import subprocess
from aws_personal import AWS

aws = AWS('mujuthaek', '659355919826')
aws.verify(require_credits=False)
oidc = json.loads(subprocess.run(['gh', 'api', 'repos/sangrock2/mujuthaek/actions/oidc/customization/sub'],
                                  check=True, capture_output=True, text=True).stdout)
if not oidc.get('use_default'):
    raise RuntimeError('Inspect custom OIDC claims before configuring trust')
prefix = oidc.get('sub_claim_prefix', 'repo:sangrock2/mujuthaek')
if oidc.get('use_immutable_subject') and prefix != 'repo:sangrock2@59195181/mujuthaek@1445740935':
    raise RuntimeError('Unexpected immutable repository identity')
provider = 'arn:aws:iam::659355919826:oidc-provider/token.actions.githubusercontent.com'
providers = aws.call('iam', 'list-open-id-connect-providers')['OpenIDConnectProviderList']
if not any(p['Arn'] == provider for p in providers):
    aws.call('iam', 'create-open-id-connect-provider', '--url', 'https://token.actions.githubusercontent.com',
             '--client-id-list', 'sts.amazonaws.com')
trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Federated': provider},
         'Action': 'sts:AssumeRoleWithWebIdentity', 'Condition': {'StringEquals': {
             'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
             'token.actions.githubusercontent.com:sub': prefix + ':ref:refs/heads/main'}}}]}
role = 'mujuthaek-github-release'
roles = aws.call('iam', 'list-roles')['Roles']
if any(r['RoleName'] == role for r in roles):
    raise RuntimeError('Role already exists; inspect it before changing permissions')
result = aws.call('iam', 'create-role', '--role-name', role, '--assume-role-policy-document', json.dumps(trust),
                  '--tags', 'Key=Project,Value=mujuthaek-personal')
bucket = 'arn:aws:s3:::mujuthaek-personal-659355919826-raw'
policy = {'Version': '2012-10-17', 'Statement': [
    {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': bucket + '/deployments/*'},
    {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': [bucket + '/deployments/releases/*', bucket + '/deployments/desired.json']},
    {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': bucket,
     'Condition': {'StringLike': {'s3:prefix': ['deployments/*']}}},
]}
aws.call('iam', 'put-role-policy', '--role-name', role, '--policy-name', 'ReleasePrefixOnly', '--policy-document', json.dumps(policy))
subprocess.run(['gh', 'variable', 'set', 'AWS_DEPLOY_ROLE_ARN', '--repo', 'sangrock2/mujuthaek',
                '--body', result['Role']['Arn']], check=True)
# Deliberately disabled until current local/deployed source is aligned through reviewed PRs.
subprocess.run(['gh', 'variable', 'set', 'PRODUCTION_DEPLOY_ENABLED', '--repo', 'sangrock2/mujuthaek', '--body', 'false'], check=True)
print('Configured main-only GitHub OIDC and release-prefix permissions; deployment activation is pending source alignment')
