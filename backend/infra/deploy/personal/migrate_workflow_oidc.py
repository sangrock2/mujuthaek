"""Coordinate existing project roles and GitHub's subject template without an authentication gap."""
import copy
import json
import subprocess

from aws_personal import AWS
from setup_github_release import (PLAN_ROLE, RELEASE_ROLE, SUB_CLAIM_KEYS, ensure_role,
                                 plan_policy, release_policy, subject_prefix, trust_policy)

REPO = 'sangrock2/mujuthaek'
OPERATIONS = 'mujuthaek-github-operations'


def canonical_trust(policy):
    result = copy.deepcopy(policy)
    for statement in result.get('Statement', []):
        conditions = statement.get('Condition', {}).get('StringEquals', {})
        key = 'token.actions.githubusercontent.com:sub'
        if isinstance(conditions.get(key), str):
            conditions[key] = [conditions[key]]
        if isinstance(conditions.get(key), list):
            conditions[key] = sorted(conditions[key])
    return result


def gh(*args, body=None):
    result = subprocess.run(['gh', *args], input=body, capture_output=True, text=True, encoding='utf-8', check=True)
    return result.stdout


def main():
    aws = AWS('mujuthaek', '659355919826')
    if aws.call('sts', 'get-caller-identity')['Account'] != aws.account:
        raise RuntimeError('Wrong account')
    original = json.loads(gh('api', f'repos/{REPO}/actions/oidc/customization/sub'))
    prefix = subject_prefix(original)
    saved = {name: aws.call('iam', 'get-role', '--role-name', name)['Role']
             for name in (RELEASE_ROLE, OPERATIONS)}
    for role in saved.values():
        if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in role.get('Tags', []):
            raise RuntimeError('Role not owned by project')
    running = json.loads(gh('api', f'repos/{REPO}/actions/runs?per_page=100'))['workflow_runs']
    if any(run['status'] != 'completed' for run in running):
        raise RuntimeError('Wait for active workflows to finish')
    targets = {RELEASE_ROLE: trust_policy(prefix, ('production.yml', 'workers.yml')),
               OPERATIONS: trust_policy(prefix, ('operations.yml',), environment='vercel-production')}
    # Keep deployment disabled until reviewed source and dependency checks are ready.
    gh('variable', 'set', 'PRODUCTION_DEPLOY_ENABLED', '--repo', REPO, '--body', 'false')
    switched = False
    try:
        for name, target in targets.items():
            transition = copy.deepcopy(target)
            transition['Statement'] += saved[name]['AssumeRolePolicyDocument']['Statement']
            aws.call('iam', 'update-assume-role-policy', '--role-name', name,
                     '--policy-document', json.dumps(transition))
        roles = aws.call('iam', 'list-roles')['Roles']
        plan_arn, _ = ensure_role(aws, roles, PLAN_ROLE, trust_policy(prefix, ('production.yml',)),
                                  'ReleaseStateReadOnly', plan_policy(), True)
        aws.call('iam', 'put-role-policy', '--role-name', RELEASE_ROLE, '--policy-name',
                 'ReleasePrefixOnly', '--policy-document', json.dumps(release_policy()))
        gh('api', '--method', 'PUT', f'repos/{REPO}/actions/oidc/customization/sub', '--input', '-',
           body=json.dumps({'use_default': False, 'include_claim_keys': SUB_CLAIM_KEYS}))
        switched = True
        for name, target in targets.items():
            aws.call('iam', 'update-assume-role-policy', '--role-name', name,
                     '--policy-document', json.dumps(target))
        gh('variable', 'set', 'AWS_PLAN_ROLE_ARN', '--repo', REPO, '--body', plan_arn)
        observed = json.loads(gh('api', f'repos/{REPO}/actions/oidc/customization/sub'))
        if observed.get('use_default') or observed.get('include_claim_keys') != SUB_CLAIM_KEYS:
            raise RuntimeError('Subject template mismatch')
        expected = dict(targets, **{PLAN_ROLE: trust_policy(prefix, ('production.yml',))})
        for name, target in expected.items():
            actual = aws.call('iam', 'get-role', '--role-name', name)['Role']['AssumeRolePolicyDocument']
            if canonical_trust(actual) != canonical_trust(target):
                raise RuntimeError('Role trust mismatch')
    except Exception:
        # Restore both halves of the authentication boundary. Do not re-enable deployment.
        for name, role in saved.items():
            aws.call('iam', 'update-assume-role-policy', '--role-name', name,
                     '--policy-document', json.dumps(role['AssumeRolePolicyDocument']))
        if switched:
            body = {'use_default': original['use_default']}
            if not original['use_default']:
                body['include_claim_keys'] = original['include_claim_keys']
            gh('api', '--method', 'PUT', f'repos/{REPO}/actions/oidc/customization/sub',
               '--input', '-', body=json.dumps(body))
        raise
    print(json.dumps({'ok': True, 'workflow_claim': 'workflow_ref', 'roles_verified': 3,
                      'deployment_enabled': False, 'live_token_exchange_tested': False}))


if __name__ == '__main__':
    main()
