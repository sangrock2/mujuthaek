"""Enable scoped S3 version recovery after pausing writers; no object contents are touched."""
import copy
import json

from aws_personal import AWS

BUCKET = 'mujuthaek-personal-659355919826-raw'


def main():
    aws = AWS('mujuthaek', '659355919826')
    if aws.call('sts', 'get-caller-identity')['Account'] != aws.account:
        raise RuntimeError('Wrong account')

    def s3(operation, *args):
        return aws.call('s3api', operation, '--bucket', BUCKET, '--expected-bucket-owner', aws.account, *args)

    tags = s3('get-bucket-tagging')['TagSet']
    if {'Key': 'Project', 'Value': 'mujuthaek-personal'} not in tags:
        raise RuntimeError('Bucket not project owned')
    rules = copy.deepcopy(s3('get-bucket-lifecycle-configuration')['Rules'])
    backups = [rule for rule in rules if rule.get('Filter') == {'Prefix': 'backups/'}]
    if len(backups) != 1 or backups[0].get('Expiration') != {'Days': 30}:
        raise RuntimeError('Existing backup retention differs; inspect before applying')
    backups[0]['NoncurrentVersionExpiration'] = {'NoncurrentDays': 1}
    additions = [
        {'ID': 'RecoverPreviousRaw7Days', 'Status': 'Enabled', 'Filter': {'Prefix': 'raw/'},
         'NoncurrentVersionExpiration': {'NoncurrentDays': 7}},
        {'ID': 'RecoverPreviousArea7Days', 'Status': 'Enabled', 'Filter': {'Prefix': 'area/'},
         'NoncurrentVersionExpiration': {'NoncurrentDays': 7}},
    ]
    for addition in additions:
        existing = [rule for rule in rules if rule.get('ID') == addition['ID']]
        if existing and existing != [addition]:
            raise RuntimeError('Existing recovery rule differs; not overwritten')
        if not existing:
            rules.append(addition)
    versioning = s3('get-bucket-versioning')
    if versioning.get('MFADelete') == 'Enabled':
        raise RuntimeError('MFA deletion is enabled; do not change without owner')
    s3('put-bucket-lifecycle-configuration', '--lifecycle-configuration', json.dumps({'Rules': rules}))
    s3('put-bucket-versioning', '--versioning-configuration', 'Status=Enabled')
    if s3('get-bucket-versioning').get('Status') != 'Enabled':
        raise RuntimeError('Versioning not enabled')
    observed = s3('get-bucket-lifecycle-configuration')['Rules']
    if sorted(observed, key=lambda rule: rule['ID']) != sorted(rules, key=lambda rule: rule['ID']):
        raise RuntimeError('Lifecycle verification differs')
    print(json.dumps({'ok': True, 'versioning': 'Enabled', 'raw_area_previous_versions_days': 7,
                      'current_backup_expiration_days': 30, 'deleted_backup_version_extra_days': 1,
                      'writes_must_remain_paused_minutes': 15, 'object_lock_changed': False}))


if __name__ == '__main__':
    main()
