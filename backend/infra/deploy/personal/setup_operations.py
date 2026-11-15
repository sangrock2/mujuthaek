"""Install main-only operations OIDC using an owner-only configuration file."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from aws_personal import AWS
import operations_monitor as settings

ROLE = 'mujuthaek-github-operations'
REPO = 'sangrock2/mujuthaek'


def policy():
    return {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 'freetier:GetAccountPlanState', 'Resource': '*'},
        {'Effect': 'Allow', 'Action': 'budgets:ViewBudget',
         'Resource': f'arn:aws:budgets::{settings.ACCOUNT}:budget/{settings.BUDGET}'},
        {'Effect': 'Allow', 'Action': 'iam:ListAccessKeys',
         'Resource': [f'arn:aws:iam::{settings.ACCOUNT}:user/{user}' for user in settings.USERS]},
        {'Effect': 'Allow', 'Action': ['s3:GetObject', 's3:PutObject'],
         'Resource': [f'arn:aws:s3:::{settings.BUCKET}/{settings.PREFIX}{name}' for name in ('state.json', 'latest.json')]},
        {'Effect': 'Allow', 'Action': 'ses:SendEmail',
         'Resource': f'arn:aws:ses:{settings.REGION}:{settings.ACCOUNT}:identity/{settings.SENDER.split("@")[1]}',
         'Condition': {'StringEquals': {'ses:FromAddress': settings.SENDER},
                       'ForAllValues:StringEquals': {'ses:Recipients': [settings.RECIPIENT]},
                       'Null': {'ses:Recipients': 'false'}}},
    ]}


def secret(name, value):
    subprocess.run(['gh', 'secret', 'set', name, '--repo', REPO], input=value,
                   check=True, capture_output=True, text=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Owner-only Git-ignored JSON file')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    settings.configure(config)
    aws = AWS('mujuthaek', settings.ACCOUNT)
    aws.verify(require_credits=False)
    budget = aws.call('budgets', 'describe-budget', '--account-id', settings.ACCOUNT, '--budget-name', settings.BUDGET,
                      region='us-east-1')['Budget']
    if settings.usd(budget['BudgetLimit']) != settings.BUDGET_LIMIT or budget['CostTypes']['IncludeCredit']:
        raise RuntimeError('Existing budget differs from the approved gross limit; inspect before changing')
    if not settings.budget_subscriptions(aws.call):
        raise RuntimeError('Expected owner budget subscriptions are missing')
    oidc = json.loads(subprocess.run(['gh', 'api', f'repos/{REPO}/actions/oidc/customization/sub'],
                                     capture_output=True, text=True, check=True, timeout=60).stdout)
    prefix = oidc.get('sub_claim_prefix', f'repo:{REPO}')
    if not oidc.get('use_default') or prefix not in ('repo:sangrock2/mujuthaek', 'repo:sangrock2@59195181/mujuthaek@1445740935'):
        raise RuntimeError('Unexpected repository OIDC identity')
    trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
             'Principal': {'Federated': f'arn:aws:iam::{settings.ACCOUNT}:oidc-provider/token.actions.githubusercontent.com'},
             'Action': 'sts:AssumeRoleWithWebIdentity', 'Condition': {'StringEquals': {
                 'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
                 'token.actions.githubusercontent.com:sub': prefix + ':ref:refs/heads/main'}}}]}
    roles = aws.call('iam', 'list-roles')['Roles']
    if any(role['RoleName'] == ROLE for role in roles):
        existing = aws.call('iam', 'get-role', '--role-name', ROLE)['Role']
        if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in existing.get('Tags', []) or existing['AssumeRolePolicyDocument'] != trust:
            raise RuntimeError('Existing role ownership/trust differs; no changes made')
        arn = existing['Arn']
    else:
        arn = aws.call('iam', 'create-role', '--role-name', ROLE, '--assume-role-policy-document', json.dumps(trust),
                       '--tags', 'Key=Project,Value=mujuthaek-personal')['Role']['Arn']
    aws.call('iam', 'put-role-policy', '--role-name', ROLE, '--policy-name', 'PrivateOperationsOnly',
             '--policy-document', json.dumps(policy()))
    # Seed only absent state: no ListBucket permission is needed by the monitor.
    key = settings.PREFIX + 'state.json'
    objects = aws.call('s3api', 'list-objects-v2', '--bucket', settings.BUCKET, '--prefix', key).get('Contents', [])
    if not any(item['Key'] == key for item in objects):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text(json.dumps({'version': 1, 'active': []}), encoding='utf-8')
            aws.call('s3api', 'put-object', '--bucket', settings.BUCKET, '--key', key, '--body', str(path),
                     '--if-none-match', '*', '--server-side-encryption', 'AES256', '--content-type', 'application/json')
    secret('OPERATIONS_CONFIG', json.dumps(config))
    secret('AWS_OPERATIONS_ACCOUNT_ID', settings.ACCOUNT)
    secret('AWS_OPERATIONS_ROLE_ARN', arn)
    print('Operations OIDC role configured; owner budget alerts verified; private Actions settings installed.')


if __name__ == '__main__':
    main()
