"""Issue tracked project service keys privately; retain the old writer key until verified cutover."""
import json
import os

from aws_personal import AWS, RUNTIME
from private_files import create_private_file, write_private_file
from service_isolation import AWS_PREFIX, env_values, identity_plan


def main():
    aws = AWS('mujuthaek', '659355919826')
    if aws.call('sts', 'get-caller-identity')['Arn'] != 'arn:aws:iam::659355919826:root':
        raise RuntimeError('Expected the verified account owner')
    folder = RUNTIME / 'service-isolation-20261116'
    settings = env_values((folder / '.env.isolation').read_text())
    plan = identity_plan(aws.account, 'mujuthaek-personal-659355919826-raw', 'mujuthaek-personal-runtime-20261113')
    for service, role in plan['roles'].items():
        name = role['user_name']
        user = aws.call('iam', 'get-user', '--user-name', name)['User']
        if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in user.get('Tags', []):
            raise RuntimeError('Unexpected identity ownership')
        if aws.call('iam', 'list-attached-user-policies', '--user-name', name)['AttachedPolicies'] or aws.call('iam', 'list-groups-for-user', '--user-name', name)['Groups']:
            raise RuntimeError('Unexpected identity permissions')
        # Snapshot exact previous inline policies before adding a boundary or a new allow.
        snapshot = folder / (service + '-iam-before.json')
        if not snapshot.exists():
            policies = {policy: aws.call('iam', 'get-user-policy', '--user-name', name, '--policy-name', policy)['PolicyDocument']
                        for policy in aws.call('iam', 'list-user-policies', '--user-name', name)['PolicyNames']}
            write_private_file(snapshot, json.dumps({'policies': policies, 'boundary': user.get('PermissionsBoundary')}))
        managed = {item['Arn'] for item in aws.call('iam', 'list-policies', '--scope', 'Local')['Policies']}
        if role['boundary_arn'] not in managed:
            aws.call('iam', 'create-policy', '--policy-name', role['boundary_name'], '--policy-document', json.dumps(role['boundary_policy']),
                     '--tags', 'Key=Project,Value=mujuthaek-personal')
        else:
            meta = aws.call('iam', 'get-policy', '--policy-arn', role['boundary_arn'])['Policy']
            actual = aws.call('iam', 'get-policy-version', '--policy-arn', role['boundary_arn'], '--version-id', meta['DefaultVersionId'])['PolicyVersion']['Document']
            if actual != role['boundary_policy']:
                raise RuntimeError('Existing boundary differs')
        aws.call('iam', 'put-user-permissions-boundary', '--user-name', name, '--permissions-boundary', role['boundary_arn'])
        aws.call('iam', 'put-user-policy', '--user-name', name, '--policy-name', role['policy_name'], '--policy-document', json.dumps(role['policy']))
        key_file = folder / (service + '-issued-key.json')
        keys = aws.call('iam', 'list-access-keys', '--user-name', name)['AccessKeyMetadata']
        if key_file.exists():
            if key_file.is_symlink():
                raise RuntimeError('Unexpected private key link')
            key = json.loads(key_file.read_text())
            if not any(item['AccessKeyId'] == key['AccessKeyId'] and item['Status'] == 'Active' for item in keys):
                raise RuntimeError('Tracked key is not active')
        else:
            maximum = 1 if service == 'collector' else 0
            if len(keys) > maximum:
                raise RuntimeError('Untracked existing access keys; no key issued')
            descriptor = create_private_file(key_file)
            key = None
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
                    key = aws.call('iam', 'create-access-key', '--user-name', name)['AccessKey']
                    json.dump(key, out, default=str)
            except BaseException:
                if key:
                    aws.call('iam', 'delete-access-key', '--user-name', name, '--access-key-id', key['AccessKeyId'])
                key_file.unlink(missing_ok=True)
                raise
        prefix = AWS_PREFIX[service]
        settings[prefix + '_AWS_ACCESS_KEY_ID'] = key['AccessKeyId']
        settings[prefix + '_AWS_SECRET_ACCESS_KEY'] = key['SecretAccessKey']
    output = folder / '.env.credentials'
    text = ''.join(f'{key}={value}\n' for key, value in settings.items())
    if output.exists():
        if output.is_symlink() or output.read_text() != text:
            raise RuntimeError('Existing credential bundle differs')
    else:
        write_private_file(output, text)
    print(json.dumps({'service_keys': 'privately_tracked', 'old_writer_key_revoked': False, 'applications_changed': False}))


if __name__ == '__main__':
    main()
