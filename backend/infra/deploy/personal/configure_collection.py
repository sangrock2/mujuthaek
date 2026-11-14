"""Install owner-supplied personal collection keys; never display values or enable automatic publication."""
import json
import hashlib
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path('/opt/mujuthaek-source/backend/infra/deploy/personal')
INPUT = Path('/home/ubuntu/.env.collection')
KEYS = ('OPENAI_API_KEY', 'LH_API_KEY', 'DATA_GO_KR_SERVICE_KEY', 'YOUTHCENTER_API_KEY', 'BIZINFO_API_KEY')
SETTINGS = {'EXTRACTION_MONTHLY_BUDGET_USD': '10', 'EXTRACTION_DAILY_BUDGET_USD': '1',
            'EXTRACTION_PUBLICATION_MODE': 'manual'}


def credentials(text):
    values = {}
    for line in text.lstrip('\ufeff').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        name, sep, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if not sep or name not in KEYS or name in values or not re.fullmatch(r'[A-Za-z0-9._%/+=-]+', value):
            raise ValueError('Missing, duplicate or invalid collection entry; values were not displayed')
        values[name] = value
    if set(values) != set(KEYS) or not values['OPENAI_API_KEY'].startswith('sk-'):
        raise ValueError('All five personal collection credentials are required')
    return values


def merge(original, values):
    names = set(values)
    lines = [line for line in original.splitlines() if line.partition('=')[0].strip() not in names]
    return '\n'.join(lines + [f'{name}={value}' for name, value in values.items()]) + '\n'


def private_file(text):
    descriptor, name = tempfile.mkstemp(prefix='.env.collection-', dir=BASE)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(text)
    return Path(name)


def compose(env, *args):
    return subprocess.run(['docker', 'compose', '--env-file', str(env), '--env-file', 'versions.env',
                           '--profile', 'workers', '-f', 'compose.prod.yml', *args], cwd=BASE,
                          check=True, capture_output=True, text=True)


def verify_schema(env, database, tables):
    query = 'select ' + ' and '.join(f"to_regclass('public.{table}') is not null" for table in tables)
    result = compose(env, 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', database, '-Atc', query)
    if result.stdout.strip() != 't':
        raise RuntimeError('Worker database schema is incomplete; workers were not started')


def apply(values, release):
    if not re.fullmatch(r'[0-9a-f]{40}', release):
        raise ValueError('Worker release must be a full commit ID')
    original_path = BASE / '.env'
    original = original_path.read_text(encoding='utf-8')
    old = dict(line.split('=', 1) for line in original.splitlines() if line and not line.startswith('#') and '=' in line)
    if old.get('S3_BUCKET') != 'mujuthaek-personal-659355919826-raw':
        raise RuntimeError('Not the personal collection environment')
    updates = {**values, **SETTINGS, 'COLLECTOR_RELEASE': release, 'EXTRACTION_RELEASE': release}
    pending = private_file(merge(original, updates))
    changed = False
    try:
        config = json.loads(compose(pending, 'config', '--format', 'json').stdout)
        services = config['services']
        if any(services['collector']['environment'].get(k) != values[k] for k in KEYS if k != 'OPENAI_API_KEY'):
            raise RuntimeError('Collector credential forwarding failed')
        if services['extraction']['environment'].get('OPENAI_API_KEY') != values['OPENAI_API_KEY']:
            raise RuntimeError('Extraction credential forwarding failed')
        if str(services['extraction']['environment'].get('EXTRACTION_MONTHLY_BUDGET_USD')) != '10':
            raise RuntimeError('Monthly budget was not bound')
        if services['extraction']['environment'].get('EXTRACTION_PUBLICATION_MODE') != 'manual':
            raise RuntimeError('Initial review gate is not enabled')
        for name in ('collector', 'extraction'):
            subprocess.run(['docker', 'image', 'inspect', services[name]['image']], check=True, capture_output=True)
        os.replace(pending, original_path)
        changed = True
        # Run schema changes sequentially before starting workers; do not restart core applications.
        subprocess.run(['bash', str(BASE / 'backup.sh')], cwd=BASE, check=True, capture_output=True, text=True)
        for name in ('migrate-collector', 'migrate-extraction'):
            compose(original_path, 'run', '--rm', '--no-deps', name)
        verify_schema(original_path, 'collector', ('flyway_schema_history', 'raw_posts', 'raw_policies', 'outbox'))
        verify_schema(original_path, 'extraction', ('flyway_schema_history', 'extraction_jobs', 'publication_holds', 'outbox'))
        compose(original_path, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'extraction')
        for _ in range(40):
            ids = compose(original_path, 'ps', '-q', 'extraction').stdout.strip()
            actual = json.loads(subprocess.run(['docker', 'inspect', ids], check=True, capture_output=True, text=True).stdout)[0]
            if actual.get('State', {}).get('Health', {}).get('Status') == 'healthy':
                break
            time.sleep(3)
        else:
            raise RuntimeError('Extraction worker did not become healthy')
        compose(original_path, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'collector')
    except Exception:
        if changed:
            try:
                compose(original_path, 'stop', 'collector', 'extraction')
            finally:
                restore = private_file(original)
                os.replace(restore, original_path)
        raise RuntimeError('Collection setup failed; workers stopped and previous settings retained or restored') from None
    finally:
        pending.unlink(missing_ok=True)


def main():
    import argparse
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0 or Path(__file__).resolve().parent != BASE:
        raise RuntimeError('Run only as root on the verified personal host')
    if INPUT.is_symlink() or not INPUT.is_file() or INPUT.stat().st_mode & 0o077:
        raise RuntimeError('Collection input must be a private regular file')
    try:
        values = credentials(INPUT.read_text(encoding='utf-8-sig'))
        if not re.fullmatch(r'[0-9a-f]{40}', args.release):
            raise ValueError('Worker release must be a full commit ID')
        with (BASE / 'runtime/releases/lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            from release_host import Host
            host = Host()
            checksum_file = host.download(f'releases/workers/{args.release}/worker-images.sha256', f'workers-{args.release}.sha256')
            checksum = checksum_file.read_text().split()[0]
            if not re.fullmatch(r'[0-9a-f]{64}', checksum):
                raise RuntimeError('Invalid worker archive checksum')
            archive = host.download(f'releases/workers/{args.release}/worker-images.tar.gz', f'workers-{args.release}.tar.gz')
            with archive.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                    raise RuntimeError('Worker archive checksum mismatch')
            subprocess.run(['docker', 'load', '-i', str(archive)], check=True, capture_output=True)
            apply(values, args.release)
            (BASE / 'runtime/worker-current.json').write_text(json.dumps({'commit': args.release, 'archive_sha256': checksum,
                                                                       'publication_mode': 'manual', 'monthly_budget_usd': 10}))
    finally:
        INPUT.unlink(missing_ok=True)
    print(json.dumps({'ok': True, 'workers': ['collector', 'extraction'], 'monthly_budget_usd': 10,
                      'publication_mode': 'manual', 'core_services_restarted': False, 'credential_values_printed': False}))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
