"""Configure GitHub main-branch OIDC with access only to this project's release prefix.

Trust is pinned to the repository, the main branch and the exact workflow file (workflow_ref), and the read-only
deployment plan job gets its own role. AWS only matches the `sub` claim, so the repository's OIDC subject is
customized to include workflow_ref (security audit section 4).
"""
import argparse
import json
import subprocess
from aws_personal import AWS

REPO = 'sangrock2/mujuthaek'
BUCKET = 'arn:aws:s3:::mujuthaek-personal-659355919826-raw'
PROVIDER = 'arn:aws:iam::659355919826:oidc-provider/token.actions.githubusercontent.com'
# The only deployment objects CI may replace: the host's request pointer and the last completed release pointer.
MUTABLE = ('deployments/desired.json', 'deployments/releases/current.json')
# Repository OIDC subject template: repo + context (ref:refs/heads/main) + the calling workflow file and its ref.
SUB_CLAIM_KEYS = ['repo', 'context', 'workflow_ref']
RELEASE_ROLE = 'mujuthaek-github-release'
PLAN_ROLE = 'mujuthaek-github-release-plan'
# Workflow files that may assume each role. Every job in a file shares its workflow_ref, so the plan job's
# separation from deploy comes from the role it names in production.yml, not from the trust policy.
RELEASE_WORKFLOWS = ('production.yml', 'workers.yml')
PLAN_WORKFLOWS = ('production.yml',)
IDENTITIES = ('repo:sangrock2/mujuthaek', 'repo:sangrock2@59195181/mujuthaek@1445740935')


def release_policy(bucket=BUCKET):
    return {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': bucket + '/deployments/*'},
        {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': [f'{bucket}/{key}' for key in MUTABLE]},
        # Release archives and manifests can be created but never overwritten, so a stolen deploy token cannot
        # swap a known-good release that a later rollback would trust (security audit L-17).
        {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': bucket + '/deployments/releases/*',
         'Condition': {'StringEquals': {'s3:if-none-match': '*'}}},
        {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': bucket,
         'Condition': {'StringLike': {'s3:prefix': ['deployments/*']}}},
    ]}


def plan_policy(bucket=BUCKET):
    """deployment_plan.py reads releases/current.json, a release manifest and states/current.json; nothing else."""
    return {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Allow', 'Action': 's3:GetObject',
         'Resource': [bucket + '/deployments/releases/*', bucket + '/deployments/states/*']},
    ]}


def subject(prefix, workflow, repo=REPO):
    return f'{prefix}:ref:refs/heads/main:workflow_ref:{repo}/.github/workflows/{workflow}@refs/heads/main'


def trust_policy(prefix, workflows, provider=PROVIDER):
    return {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Federated': provider},
            'Action': 'sts:AssumeRoleWithWebIdentity', 'Condition': {'StringEquals': {
                'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
                'token.actions.githubusercontent.com:sub': [subject(prefix, workflow) for workflow in workflows]}}}]}


def subject_prefix(oidc):
    """Repository part of the subject, from GitHub's OIDC customization; refuses templates it does not recognize."""
    if not oidc.get('use_default') and oidc.get('include_claim_keys') != SUB_CLAIM_KEYS:
        raise RuntimeError('Inspect custom OIDC claims before configuring trust')
    prefix = 'repo:sangrock2@59195181/mujuthaek@1445740935' if oidc.get('use_immutable_subject') else 'repo:' + REPO
    if oidc.get('sub_claim_prefix', prefix) not in IDENTITIES:
        raise RuntimeError('Unexpected repository OIDC identity')
    return prefix


def require_workflow_subject(oidc):
    """The role trust only matches once GitHub emits workflow_ref in `sub`; set that template if still default."""
    if oidc.get('use_default'):
        body = json.dumps({'use_default': False, 'include_claim_keys': SUB_CLAIM_KEYS})
        subprocess.run(['gh', 'api', '--method', 'PUT', f'repos/{REPO}/actions/oidc/customization/sub', '--input', '-'],
                       input=body, check=True, capture_output=True, text=True, timeout=60)


def ensure_role(aws, roles, name, trust, policy_name, policy, update_trust):
    existing = next((role for role in roles if role['RoleName'] == name), None)
    if existing is None:
        arn = aws.call('iam', 'create-role', '--role-name', name, '--assume-role-policy-document', json.dumps(trust),
                       '--tags', 'Key=Project,Value=mujuthaek-personal')['Role']['Arn']
        aws.call('iam', 'put-role-policy', '--role-name', name, '--policy-name', policy_name,
                 '--policy-document', json.dumps(policy))
        return arn, True
    if not update_trust:
        raise RuntimeError(f'Role {name} already exists; review it, then rerun with --update-trust')
    role = aws.call('iam', 'get-role', '--role-name', name)['Role']
    if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in role.get('Tags', []):
        raise RuntimeError(f'Role {name} is not owned by this project; no changes made')
    aws.call('iam', 'update-assume-role-policy', '--role-name', name, '--policy-document', json.dumps(trust))
    aws.call('iam', 'put-role-policy', '--role-name', name, '--policy-name', policy_name,
             '--policy-document', json.dumps(policy))
    return role['Arn'], False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-policy', action='store_true',
                        help='Print the role permissions and trust for operator review; calls neither AWS nor GitHub')
    parser.add_argument('--update-trust', action='store_true',
                        help='Re-pin existing project roles to the workflow-scoped subjects (after review)')
    args = parser.parse_args()
    if args.print_policy:
        prefix = 'repo:' + REPO
        print(json.dumps({'oidc_subject_template': SUB_CLAIM_KEYS,
                          RELEASE_ROLE: {'permissions': release_policy(), 'trust': trust_policy(prefix, RELEASE_WORKFLOWS)},
                          PLAN_ROLE: {'permissions': plan_policy(), 'trust': trust_policy(prefix, PLAN_WORKFLOWS)}},
                         indent=2))
        return
    aws = AWS('mujuthaek', '659355919826')
    aws.verify(require_credits=False)
    oidc = json.loads(subprocess.run(['gh', 'api', f'repos/{REPO}/actions/oidc/customization/sub'],
                                      check=True, capture_output=True, text=True).stdout)
    prefix = subject_prefix(oidc)
    providers = aws.call('iam', 'list-open-id-connect-providers')['OpenIDConnectProviderList']
    if not any(p['Arn'] == PROVIDER for p in providers):
        aws.call('iam', 'create-open-id-connect-provider', '--url', 'https://token.actions.githubusercontent.com',
                 '--client-id-list', 'sts.amazonaws.com')
    roles = aws.call('iam', 'list-roles')['Roles']
    release_arn, created = ensure_role(aws, roles, RELEASE_ROLE, trust_policy(prefix, RELEASE_WORKFLOWS),
                                       'ReleasePrefixOnly', release_policy(), args.update_trust)
    plan_arn, _ = ensure_role(aws, roles, PLAN_ROLE, trust_policy(prefix, PLAN_WORKFLOWS),
                              'ReleaseStateReadOnly', plan_policy(), args.update_trust)
    # Switch the subject template only after the trust policies accept it.
    require_workflow_subject(oidc)
    subprocess.run(['gh', 'variable', 'set', 'AWS_PLAN_ROLE_ARN', '--repo', REPO, '--body', plan_arn], check=True)
    if created:
        subprocess.run(['gh', 'variable', 'set', 'AWS_DEPLOY_ROLE_ARN', '--repo', REPO, '--body', release_arn], check=True)
        # Deliberately disabled until current local/deployed source is aligned through reviewed PRs.
        subprocess.run(['gh', 'variable', 'set', 'PRODUCTION_DEPLOY_ENABLED', '--repo', REPO, '--body', 'false'], check=True)
    print('Configured workflow-pinned main-only GitHub OIDC: release role and read-only plan role'
          + ('; deployment activation is pending source alignment' if created else ''))


if __name__ == '__main__':
    main()
