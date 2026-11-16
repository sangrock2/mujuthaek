"""Configure GitHub main-branch OIDC with access only to this project's release prefix."""
import argparse
import json
import subprocess
from aws_personal import AWS

BUCKET = 'arn:aws:s3:::mujuthaek-personal-659355919826-raw'
# The only deployment objects CI may replace: the host's request pointer and the last completed release pointer.
MUTABLE = ('deployments/desired.json', 'deployments/releases/current.json')


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-policy', action='store_true',
                        help='Print the role permissions for operator review; calls neither AWS nor GitHub')
    if parser.parse_args().print_policy:
        print(json.dumps(release_policy(), indent=2))
        return
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
    aws.call('iam', 'put-role-policy', '--role-name', role, '--policy-name', 'ReleasePrefixOnly',
             '--policy-document', json.dumps(release_policy()))
    subprocess.run(['gh', 'variable', 'set', 'AWS_DEPLOY_ROLE_ARN', '--repo', 'sangrock2/mujuthaek',
                    '--body', result['Role']['Arn']], check=True)
    # Deliberately disabled until current local/deployed source is aligned through reviewed PRs.
    subprocess.run(['gh', 'variable', 'set', 'PRODUCTION_DEPLOY_ENABLED', '--repo', 'sangrock2/mujuthaek', '--body', 'false'], check=True)
    print('Configured main-only GitHub OIDC and release-prefix permissions; deployment activation is pending source alignment')


if __name__ == '__main__':
    main()
