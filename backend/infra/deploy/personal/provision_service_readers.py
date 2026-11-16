"""Provision only the two project S3 reader identities. No keys, app restarts or writer-policy changes."""
import json

from aws_personal import AWS
from service_isolation import identity_plan


def main():
    aws = AWS('mujuthaek', '659355919826')
    if aws.call('sts', 'get-caller-identity')['Account'] != aws.account:
        raise RuntimeError('Wrong account')
    plan = identity_plan(aws.account, 'mujuthaek-personal-659355919826-raw', 'mujuthaek-personal-runtime-20261113')
    users = {user['UserName'] for user in aws.call('iam', 'list-users')['Users']}
    policies = {p['Arn'] for p in aws.call('iam', 'list-policies', '--scope', 'Local')['Policies']}
    results = {}
    for service in ('api', 'extraction'):
        role = plan['roles'][service]
        name = role['user_name']
        if name in users:
            user = aws.call('iam', 'get-user', '--user-name', name)['User']
            if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in user.get('Tags', []):
                raise RuntimeError('Existing identity is not project owned')
            if aws.call('iam', 'list-attached-user-policies', '--user-name', name)['AttachedPolicies'] or aws.call('iam', 'list-groups-for-user', '--user-name', name)['Groups']:
                raise RuntimeError('Existing identity has unexpected permissions')
        if role['boundary_arn'] not in policies:
            aws.call('iam', 'create-policy', '--policy-name', role['boundary_name'],
                     '--policy-document', json.dumps(role['boundary_policy']), '--tags', 'Key=Project,Value=mujuthaek-personal')
        else:
            metadata = aws.call('iam', 'get-policy', '--policy-arn', role['boundary_arn'])['Policy']
            actual = aws.call('iam', 'get-policy-version', '--policy-arn', role['boundary_arn'],
                              '--version-id', metadata['DefaultVersionId'])['PolicyVersion']['Document']
            if actual != role['boundary_policy']:
                raise RuntimeError('Existing boundary differs; not overwritten')
        if name not in users:
            aws.call('iam', 'create-user', '--user-name', name, '--permissions-boundary', role['boundary_arn'],
                     '--tags', 'Key=Project,Value=mujuthaek-personal')
        else:
            aws.call('iam', 'put-user-permissions-boundary', '--user-name', name, '--permissions-boundary', role['boundary_arn'])
        existing = aws.call('iam', 'list-user-policies', '--user-name', name)['PolicyNames']
        if any(policy != role['policy_name'] for policy in existing):
            raise RuntimeError('Unexpected inline policy; not removed')
        aws.call('iam', 'put-user-policy', '--user-name', name, '--policy-name', role['policy_name'],
                 '--policy-document', json.dumps(role['policy']))
        keys = aws.call('iam', 'list-access-keys', '--user-name', name)['AccessKeyMetadata']
        results[service] = {'read_only_policy_installed': True, 'boundary_installed': True,
                            'existing_key_count': len(keys), 'keys_created': 0, 'app_changes': 0}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
