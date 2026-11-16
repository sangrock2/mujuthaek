"""Install main-only operations OIDC using an owner-only configuration file.

Trust is pinned to operations.yml on main through workflow_ref in the OIDC subject; setup_github_release.py
switches the repository subject template once every project role accepts it (security audit section 4).
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from aws_personal import AWS
import operations_monitor as settings
from setup_github_release import PROVIDER, subject_prefix, trust_policy

ROLE = 'mujuthaek-github-operations'
WORKFLOWS = ('operations.yml',)
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


def operations_trust(prefix):
    provider = PROVIDER.replace('659355919826', settings.ACCOUNT)
    return trust_policy(prefix, WORKFLOWS, provider=provider, environment='vercel-production')


def secret(name, value):
    subprocess.run(['gh', 'secret', 'set', name, '--repo', REPO, '--env', 'vercel-production'], input=value,
                   check=True, capture_output=True, text=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Owner-only Git-ignored JSON file')
    parser.add_argument('--update-trust', action='store_true',
                        help='Re-pin the existing project role to the workflow-scoped subject (after review)')
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
    trust = operations_trust(subject_prefix(oidc))
    roles = aws.call('iam', 'list-roles')['Roles']
    if any(role['RoleName'] == ROLE for role in roles):
        existing = aws.call('iam', 'get-role', '--role-name', ROLE)['Role']
        if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in existing.get('Tags', []):
            raise RuntimeError('Existing role ownership differs; no changes made')
        if existing['AssumeRolePolicyDocument'] != trust:
            if not args.update_trust:
                raise RuntimeError('Existing role trust differs; review it, then rerun with --update-trust')
            aws.call('iam', 'update-assume-role-policy', '--role-name', ROLE, '--policy-document', json.dumps(trust))
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
