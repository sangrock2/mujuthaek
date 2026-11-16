"""Prepare service isolation artifacts and check operator-supplied snapshots, without cloud/broker calls.

Default deployment is unchanged. `prepare` creates unprovisioned MQ passwords locally;
IAM access keys must be issued separately by the operator. No install or credential
revocation is performed here, and offline readiness is not live permission attestation.
"""
import argparse
import base64
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path

from private_files import write_private_file

VERSION = 1
VHOST = '/'
EVENTS = 'mujuthaek.events'
DLX = 'mujuthaek.dlx'
RETRY = 'mujuthaek.extraction.retry'
SERVICES = ('api', 'notification', 'collector', 'extraction')
USERS = {service: 'mujuthaek-' + service for service in SERVICES}
PUBLISH = {
    'api': ('notification.requested', 'user.withdrawn'),
    'notification': ('push.subscription.expired',),
    'collector': ('raw.notice.collected', 'raw.policy.collected', 'area.source.ready'),
    'extraction': ('extraction.completed', 'policy.extracted'),
}
RETRIES = ('mujuthaek.raw.collected', 'mujuthaek.raw.policy', 'mujuthaek.raw.policy.dlq')
# name -> (runtime consumer, event bindings, dead-letter routing key; None means no DLX argument)
QUEUES = {
    'mujuthaek.area.source-ready': ('api', ('area.source.ready',), 'area.source.ready'),
    'mujuthaek.policy.extracted': ('api', ('policy.extracted',), 'policy.extracted'),
    'mujuthaek.extraction.completed': ('api', ('extraction.completed',), 'extraction.completed'),
    'mujuthaek.api.push-subscription-expired': ('api', ('push.subscription.expired',), 'push.subscription.expired'),
    'mujuthaek.notification': ('notification', ('notification.requested', 'user.withdrawn'), 'notification.dead'),
    'mujuthaek.raw.collected': ('extraction', ('raw.notice.collected',), 'raw.notice.collected'),
    'mujuthaek.raw.policy': ('extraction', ('raw.policy.collected',), None),
}
AWS_PREFIX = {'api': 'API_READER', 'extraction': 'EXTRACTION_READER', 'collector': 'COLLECTOR_WRITER'}
POLICY_NAMES = {'api': 'ApiReadSourcesOnly', 'extraction': 'ExtractionReadRawOnly', 'collector': 'CollectorWriteSourcesOnly'}
BOUNDARY_NAMES = {service: 'MujuthaekIsolation' + service.title() + 'Boundary' for service in AWS_PREFIX}


def exact(values):
    return '^(' + '|'.join(re.escape(value) for value in values) + ')$' if values else '^$'


def resource_permissions(service):
    # Runtime declarations are disabled. In particular no app can delete/rebind the common exchange,
    # or bypass topic rules by publishing to amq.default (the permission name for exchange="").
    read = [queue for queue, (owner, _, _) in QUEUES.items() if owner == service]
    if service == 'extraction':
        read += [queue + '.dlq' for queue in read]
    return {'user': USERS[service], 'vhost': VHOST, 'configure': '^$',
            'write': exact((EVENTS, RETRY) if service == 'extraction' else (EVENTS,)), 'read': exact(read)}


def topic_permissions(service):
    return [
        {'user': USERS[service], 'vhost': VHOST, 'exchange': EVENTS, 'write': exact(PUBLISH[service]), 'read': '^$'},
        {'user': USERS[service], 'vhost': VHOST, 'exchange': DLX, 'write': '^$', 'read': '^$'},
        {'user': USERS[service], 'vhost': VHOST, 'exchange': RETRY,
         'write': exact(RETRIES) if service == 'extraction' else '^$', 'read': '^$'},
    ]


def password_hash(password, salt=None):
    salt = secrets.token_bytes(4) if salt is None else salt
    return base64.b64encode(salt + hashlib.sha256(salt + password.encode('utf-8')).digest()).decode('ascii')


def matches_password(encoded, password):
    try:
        data = base64.b64decode(encoded, validate=True)
        return len(data) == 36 and hmac.compare_digest(encoded, password_hash(password, data[:4]))
    except (ValueError, TypeError):
        return False


def topology(passwords):
    result = {
        'users': [{'name': USERS[service], 'password_hash': password_hash(passwords[service]),
                   'hashing_algorithm': 'rabbit_password_hashing_sha256', 'tags': []} for service in SERVICES],
        'vhosts': [{'name': VHOST}],
        'permissions': [resource_permissions(service) for service in SERVICES],
        'topic_permissions': [item for service in SERVICES for item in topic_permissions(service)],
        'exchanges': [{'name': name, 'vhost': VHOST, 'type': 'topic', 'durable': True,
                       'auto_delete': False, 'internal': False, 'arguments': {}} for name in (EVENTS, DLX, RETRY)],
        'queues': [], 'bindings': [],
    }

    def bind(queue, exchange, key):
        result['bindings'].append({'source': exchange, 'vhost': VHOST, 'destination': queue,
                                   'destination_type': 'queue', 'routing_key': key, 'arguments': {}})

    for name, (_, keys, dead_key) in QUEUES.items():
        arguments = {'x-dead-letter-exchange': DLX} if dead_key else {}
        if name == 'mujuthaek.notification':
            arguments['x-dead-letter-routing-key'] = dead_key
        result['queues'] += [
            {'name': name, 'vhost': VHOST, 'durable': True, 'auto_delete': False, 'arguments': arguments},
            {'name': name + '.dlq', 'vhost': VHOST, 'durable': True, 'auto_delete': False, 'arguments': {}},
        ]
        for key in keys:
            bind(name, EVENTS, key)
        if dead_key:
            bind(name + '.dlq', DLX, dead_key)
    for queue in RETRIES:
        bind(queue, RETRY, queue)
    return result


def storage_policy(service, bucket):
    bucket_arn = 'arn:aws:s3:::' + bucket
    prefixes = ('raw',) if service == 'extraction' else ('raw', 'area')
    statements = [
        {'Effect': 'Allow', 'Action': 's3:GetBucketLocation', 'Resource': bucket_arn},
        {'Effect': 'Allow', 'Action': 's3:ListBucket', 'Resource': bucket_arn,
         'Condition': {'StringLike': {'s3:prefix': [item for prefix in prefixes for item in (prefix, prefix + '/*')]}}},
        {'Effect': 'Allow', 'Action': 's3:GetObject', 'Resource': [bucket_arn + '/' + prefix + '/*' for prefix in prefixes]},
    ]
    if service == 'collector':
        statements += [
            {'Effect': 'Allow', 'Action': ['s3:PutObject', 's3:AbortMultipartUpload'],
             'Resource': [bucket_arn + '/raw/*', bucket_arn + '/area/*']},
            {'Effect': 'Allow', 'Action': 's3:DeleteObject', 'Resource': bucket_arn + '/raw/*'},
        ]
    return {'Version': '2012-10-17', 'Statement': statements}


def identity_plan(account, bucket, collector_user):
    if not re.fullmatch(r'[0-9]{12}', account):
        raise ValueError('Invalid AWS account')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket):
        raise ValueError('Invalid private bucket name')
    if len(collector_user) > 64 or not re.fullmatch(r'mujuthaek-personal-runtime-[a-z0-9-]+', collector_user):
        raise ValueError('Use the existing project collector writer identity')
    names = {'api': 'mujuthaek-personal-api-reader', 'extraction': 'mujuthaek-personal-extraction-reader', 'collector': collector_user}
    return {'version': VERSION, 'account': account, 'bucket': bucket, 'roles': {
        service: {'user_name': names[service], 'user_arn': f'arn:aws:iam::{account}:user/{names[service]}',
                  'policy_name': POLICY_NAMES[service], 'policy': storage_policy(service, bucket),
                  'boundary_name': BOUNDARY_NAMES[service],
                  'boundary_arn': f'arn:aws:iam::{account}:policy/{BOUNDARY_NAMES[service]}',
                  'boundary_policy': storage_policy(service, bucket)} for service in AWS_PREFIX}}


def env_values(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('Invalid private environment file')
        key, value = line.split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result or '\x00' in value:
            raise ValueError('Invalid or duplicate private setting')
        result[key] = value
    return result


def prepare(account, bucket, collector_user, directory):
    plan = identity_plan(account, bucket, collector_user)
    passwords = {service: secrets.token_hex(32) for service in SERVICES}
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Every file is exclusive and private before bytes are written, including RabbitMQ password hashes.
    write_private_file(directory / 'isolation-plan.json', json.dumps(plan, indent=2) + '\n')
    write_private_file(directory / 'broker-definitions.json', json.dumps(topology(passwords), indent=2) + '\n')
    settings = {'SERVICE_ISOLATION_READY': ''}
    settings.update({service.upper() + '_MQ_PASSWORD': passwords[service] for service in SERVICES})
    for prefix in AWS_PREFIX.values():
        settings[prefix + '_AWS_ACCESS_KEY_ID'] = ''
        settings[prefix + '_AWS_SECRET_ACCESS_KEY'] = ''
    write_private_file(directory / '.env.isolation', ''.join(f'{key}={value}\n' for key, value in settings.items()))
    for service, role in plan['roles'].items():
        write_private_file(directory / ('iam-' + service + '.json'), json.dumps(role['policy'], indent=2) + '\n')
    return {'ok': True, 'created': ['isolation-plan.json', 'broker-definitions.json', '.env.isolation',
                                  'iam-api.json', 'iam-extraction.json', 'iam-collector.json'],
            'credentials_provisioned': False, 'network_calls': 0}


def check_broker(observed, passwords):
    checks = {}
    wanted = topology(passwords)
    for service in SERVICES:
        user = USERS[service]
        users = [item for item in observed.get('users', []) if item.get('name') == user]
        checks['mq.' + service + '.credentials'] = len(users) == 1 and not users[0].get('tags') and users[0].get('hashing_algorithm') == 'rabbit_password_hashing_sha256' and matches_password(users[0].get('password_hash'), passwords[service])
        found = [item for item in observed.get('permissions', []) if item.get('user') == user]
        checks['mq.' + service + '.resources'] = found == [resource_permissions(service)]
        found = [item for item in observed.get('topic_permissions', []) if item.get('user') == user]
        checks['mq.' + service + '.topics'] = sorted(found, key=lambda item: item.get('exchange', '')) == sorted(topic_permissions(service), key=lambda item: item['exchange'])
    checks['mq.legacy_user_revoked'] = not any(item.get('name') == 'mujuthaek' for item in observed.get('users', [])) and not any(item.get('user') == 'mujuthaek' for item in observed.get('permissions', []))
    checks['mq.exact_users'] = sorted(item.get('name', '') for item in observed.get('users', [])) == sorted(USERS.values())
    for kind in ('exchanges', 'queues'):
        for item in wanted[kind]:
            matches = [value for value in observed.get(kind, []) if value.get('name') == item['name'] and value.get('vhost') == VHOST]
            checks['mq.' + kind + '.' + item['name']] = len(matches) == 1 and all(matches[0].get(key) == value for key, value in item.items())
    owned = {item['name'] for item in wanted['queues']}
    actual = [item for item in observed.get('bindings', []) if item.get('vhost') == VHOST and item.get('destination') in owned]
    # Default exchange's implicit bindings are not exportable mutable topology; reject all other extra bindings.
    actual = [item for item in actual if item.get('source') != '']
    canonical = lambda item: json.dumps(item, sort_keys=True, separators=(',', ':'))
    checks['mq.exact_bindings'] = sorted(map(canonical, actual)) == sorted(map(canonical, wanted['bindings']))
    return checks


def check_iam(plan, observed, settings):
    checks = {}
    access_keys = []
    for service, role in plan['roles'].items():
        entry = observed.get(service, {})
        prefix = AWS_PREFIX[service]
        key = settings.get(prefix + '_AWS_ACCESS_KEY_ID', '')
        secret = settings.get(prefix + '_AWS_SECRET_ACCESS_KEY', '')
        access_keys.append(key)
        checks['iam.' + service + '.credential_shape'] = bool(re.fullmatch(r'AKIA[A-Z0-9]{16}', key) and re.fullmatch(r'[A-Za-z0-9/+=]{40}', secret))
        checks['iam.' + service + '.identity'] = entry.get('user_arn') == role['user_arn'] and entry.get('access_key_id') == key
        checks['iam.' + service + '.active_key'] = entry.get('active_access_key_ids') == [key]
        checks['iam.' + service + '.least_privilege'] = (entry.get('attached_policies') == [] and entry.get('groups') == [] and
            entry.get('inline_policies') == {role['policy_name']: role['policy']} and
            entry.get('boundary_arn') == role['boundary_arn'] and entry.get('boundary_policy') == role['boundary_policy'])
    checks['iam.distinct_service_keys'] = len(set(access_keys)) == len(access_keys)
    return checks


def check_compose(config, settings):
    checks = {}
    services = config.get('services', {})
    for service in SERVICES:
        env = services.get(service, {}).get('environment', {})
        password = settings[service.upper() + '_MQ_PASSWORD']
        if service in {'api', 'notification'}:
            checks['compose.' + service + '.mq'] = env.get('RABBITMQ_USER') == USERS[service] and env.get('RABBITMQ_PASSWORD') == password
            checks['compose.' + service + '.managed_topology'] = str(env.get('SPRING_RABBITMQ_DYNAMIC')).lower() == 'false'
        else:
            checks['compose.' + service + '.mq'] = env.get('RABBITMQ_URL') == f'amqp://{USERS[service]}:{password}@rabbitmq:5672/%2F'
            checks['compose.' + service + '.managed_topology'] = str(env.get('MUJUTHAEK_MANAGED_TOPOLOGY')).lower() == 'true'
        if service in AWS_PREFIX:
            prefix = AWS_PREFIX[service]
            checks['compose.' + service + '.s3'] = all(env.get(name) == settings[prefix + '_' + name] for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')) and not env.get('AWS_SESSION_TOKEN') and not env.get('AWS_SECURITY_TOKEN')
    ses_key = services.get('notification', {}).get('environment', {}).get('AWS_ACCESS_KEY_ID')
    checks['compose.notification.ses_separate'] = not ses_key or ses_key not in [settings[prefix + '_AWS_ACCESS_KEY_ID'] for prefix in AWS_PREFIX.values()]
    return checks


def readiness(plan, settings, broker_snapshot, iam_snapshot, compose_config):
    # Recompute policies rather than trusting an edited plan's claim of read-only access.
    expected = identity_plan(plan['account'], plan['bucket'], plan['roles']['collector']['user_name'])
    checks = {'plan.unmodified': plan == expected}
    passwords = {service: settings.get(service.upper() + '_MQ_PASSWORD', '') for service in SERVICES}
    checks['mq.distinct_strong_passwords'] = all(re.fullmatch(r'[a-f0-9]{64}', value) for value in passwords.values()) and len(set(passwords.values())) == 4
    checks.update(check_broker(broker_snapshot, passwords))
    checks.update(check_iam(expected, iam_snapshot, settings))
    checks.update(check_compose(compose_config, settings))
    return {'ok': all(checks.values()), 'scope': 'offline operator-supplied snapshots only; no live attestation',
            'checks': checks, 'network_calls': 0, 'live_smoke_test_required': True}


def load(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Expected a bounded regular input file')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('prepare', help='Create local unprovisioned MQ credentials and IAM policy artifacts')
    for name in ('account', 'bucket', 'collector-user', 'out'):
        create.add_argument('--' + name, required=True)
    check = sub.add_parser('readiness', help='Check exported snapshots and write an explicit activation environment')
    for name in ('bundle', 'environment', 'broker-export', 'iam-evidence', 'compose-config', 'activation-file'):
        check.add_argument('--' + name, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.account, args.bucket, args.collector_user, args.out)
    else:
        env_path = Path(args.environment)
        if env_path.is_symlink() or not env_path.is_file() or env_path.stat().st_size > 64 * 1024:
            raise ValueError('Expected a bounded private environment input')
        settings = env_values(env_path.read_text(encoding='utf-8-sig'))
        result = readiness(load(Path(args.bundle) / 'isolation-plan.json'), settings,
                           load(args.broker_export), load(args.iam_evidence), load(args.compose_config))
        if result['ok']:
            settings['SERVICE_ISOLATION_READY'] = 'verified-v1'
            write_private_file(args.activation_file, ''.join(f'{key}={value}\n' for key, value in settings.items()))
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Service isolation input/preparation failed; private values were not displayed.') from None
